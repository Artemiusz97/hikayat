from __future__ import annotations
from typing import Any, Callable, Optional
import db
import asyncio
import json
import logging
import time
from contextlib import contextmanager
import re
import sqlite3
from config import DB_PATH
import character_data as cd
from .core import *
from .core import _delete_session_records, _to_str, _is_suspicious_entity_text, _safe_int_db, _sanitize_npcs_list, _json_dataclass_default
from .registry import SessionTableSpec, get_load_specs, get_save_specs

_log = logging.getLogger(__name__)
MAX_SAVE_SLOTS_PER_CHAR = 6

def _remap_single_proof_ref(raw_ref: str, clue_id_map: dict[int, int], inv_id_map: dict[int, int]) -> str:
    ref = str(raw_ref or "").strip()
    if ":" not in ref:
        return ref
    prefix, rest = ref.split(":", 1)
    prefix_low = prefix.strip().lower()
    if prefix_low == "clue":
        try:
            mapped = clue_id_map.get(int(rest.strip()))
            if mapped is not None:
                return f"clue:{mapped}"
        except (TypeError, ValueError):
            pass
    elif prefix_low in ("inv", "photo"):
        try:
            mapped = inv_id_map.get(int(rest.strip()))
            if mapped is not None:
                return f"{prefix_low}:{mapped}"
        except (TypeError, ValueError):
            pass
    return ref


def _remap_epistemic_proof_refs(
    conn: sqlite3.Connection,
    new_session_id: int,
    clue_id_map: dict[int, int],
    inv_id_map: dict[int, int],
) -> int:
    """Remaps `clue:<id>`, `inv:<id>`, and `photo:<inv_id>` references inside loaded `epistemic_facts` (`D-2`)."""
    if not clue_id_map and not inv_id_map:
        return 0
    try:
        rows = conn.execute(
            "SELECT id, proof_artifact_ref, metadata_json FROM epistemic_facts WHERE session_id = ?",
            (new_session_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return 0
    updated = 0
    for r in rows:
        cur_ref = str(r["proof_artifact_ref"] or "").strip()
        new_ref = _remap_single_proof_ref(cur_ref, clue_id_map, inv_id_map)
        dirty = new_ref != cur_ref
        raw_meta = r["metadata_json"] or "{}"
        try:
            meta = json.loads(raw_meta) if isinstance(raw_meta, str) else dict(raw_meta)
        except Exception:
            meta = {}
        if isinstance(meta, dict):
            snaps = meta.get("_turn_snapshots")
            if isinstance(snaps, dict):
                for snap in snaps.values():
                    if isinstance(snap, dict) and snap.get("proof_artifact_ref"):
                        remapped_snap = _remap_single_proof_ref(str(snap["proof_artifact_ref"]), clue_id_map, inv_id_map)
                        if remapped_snap != snap["proof_artifact_ref"]:
                            snap["proof_artifact_ref"] = remapped_snap
                            dirty = True
            if isinstance(meta.get("proof_refs"), list):
                new_list = [_remap_single_proof_ref(str(x), clue_id_map, inv_id_map) for x in meta["proof_refs"]]
                if new_list != meta["proof_refs"]:
                    meta["proof_refs"] = new_list
                    dirty = True
        if dirty:
            conn.execute(
                "UPDATE epistemic_facts SET proof_artifact_ref = ?, metadata_json = ? WHERE id = ?",
                (new_ref, json.dumps(meta), r["id"]),
            )
            updated += 1
    return updated


def _rewrite_session_key_id(key_str: str, old_session_id: int | None, new_session_id: int) -> str:
    """Safely rewrites the embedded session_id segment in household_key / commitment_key without corrupting timestamps."""
    if not key_str or not old_session_id:
        return key_str or ""
    old_tok = re.escape(str(int(old_session_id)))
    return re.sub(rf"(?:(?<=^)|(?<=[:_\-])){old_tok}(?=$|[:_\-])", str(int(new_session_id)), str(key_str), count=1)


def _rewrite_spine_embedded_ids(val: object, old_session_id: int | None, new_session_id: int) -> object:
    """Recursively rewrites session-prefixed entity keys (`lt_<sid>_*`, `nem_<sid>_*`, `bible_<sid>_*`, etc.) inside campaign_spines JSON payloads."""
    if not old_session_id:
        return val
    if isinstance(val, dict):
        return {k: _rewrite_spine_embedded_ids(v, old_session_id, new_session_id) for k, v in val.items()}
    if isinstance(val, list):
        return [_rewrite_spine_embedded_ids(item, old_session_id, new_session_id) for item in val]
    if isinstance(val, str) and re.match(r"^(?:lt|nem|hh|rv|cm|we|bible|rendezvous|promise|pact|grudge)_\d+(?:_|$)", val):
        return _rewrite_session_key_id(val, old_session_id, new_session_id)
    return val


_CONTACT_ID_FIELDS = (
    "contact_id",
    "implicated_contact_id",
    "npc_contact_id",
    "informant_id",
    "client_id",
    "target_id",
    "accomplice_id",
)


def _apply_char_id_policy(row_dict: dict[str, Any], policy: str, load_ctx: dict[str, Any]) -> None:
    """Applies declarative character_id remapping policy during save-slot restoration."""
    char_id = load_ctx["char_id"]
    old_host = load_ctx["old_host_char_id"]
    if policy == "always_host":
        row_dict["character_id"] = char_id
    elif policy == "if_host_or_empty":
        if row_dict.get("character_id") in (None, 0, old_host):
            row_dict["character_id"] = char_id
    elif policy == "if_host_exact":
        if old_host is not None and row_dict.get("character_id") in (old_host,):
            row_dict["character_id"] = char_id
    elif policy == "dossier_zero_default":
        cur_cid = row_dict.get("character_id")
        if cur_cid is None:
            row_dict["character_id"] = 0
        elif old_host and cur_cid == old_host:
            row_dict["character_id"] = char_id


def _rewrite_snapshot_json_list_fields(
    row_dict: dict[str, Any],
    cols_and_key_fields: tuple[tuple[str, Optional[str]], ...],
    load_ctx: dict[str, Any],
    *,
    remap_null_or_zero_char: bool,
) -> None:
    """Rewrites session_id, character_id, and embedded session keys inside JSON array columns."""
    old_sid = load_ctx["old_session_id"]
    new_sid = load_ctx["new_session_id"]
    char_id = load_ctx["char_id"]
    old_host = load_ctx["old_host_char_id"]
    for col_name, key_field in cols_and_key_fields:
        raw_val = row_dict.get(col_name)
        if not raw_val:
            continue
        try:
            parsed = json.loads(raw_val) if isinstance(raw_val, str) else list(raw_val)
            if not isinstance(parsed, list):
                continue
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                item["session_id"] = new_sid
                if old_sid and key_field and item.get(key_field):
                    item[key_field] = _rewrite_session_key_id(item[key_field], old_sid, new_sid)
                if remap_null_or_zero_char:
                    if item.get("character_id") in (None, 0, old_host):
                        item["character_id"] = char_id
                elif old_host is not None and item.get("character_id") in (old_host,):
                    item["character_id"] = char_id
            row_dict[col_name] = json.dumps(parsed)
        except Exception:
            pass


def _hook_restore_contact_row(row_dict: dict[str, Any], load_ctx: dict[str, Any]) -> dict[str, Any]:
    household_id_map: dict[int, int] = load_ctx["id_maps"]["households"]
    household_surname_map: dict[str, int] = load_ctx["household_surname_map"]
    old_hid = row_dict.get("household_id")
    if old_hid is not None:
        mapped_hid = None
        try:
            mapped_hid = household_id_map.get(int(old_hid))
        except (TypeError, ValueError):
            mapped_hid = None
        if mapped_hid is None:
            import namegen
            c_name = str(row_dict.get("name") or "").strip()
            _, ex_last = namegen.extract_first_and_last_name(c_name)
            c_last = namegen.normalize_base_surname(ex_last).lower() if ex_last else (c_name.split()[-1].lower() if c_name else "")
            mapped_hid = household_surname_map.get(c_last) or (household_surname_map.get(ex_last.lower()) if ex_last else None)
        row_dict["household_id"] = mapped_hid
    if row_dict.get("household_id") and row_dict.get("relations_json"):
        try:
            rel_obj = json.loads(row_dict["relations_json"]) if isinstance(row_dict["relations_json"], str) else dict(row_dict["relations_json"])
            if isinstance(rel_obj, dict):
                rel_obj["household_id"] = row_dict["household_id"]
                row_dict["relations_json"] = json.dumps(rel_obj)
        except Exception:
            pass
    row_dict.setdefault("household_role", "child")
    return row_dict


def _hook_remap_social_turn_snapshot_json(row_dict: dict[str, Any], load_ctx: dict[str, Any]) -> dict[str, Any]:
    _rewrite_snapshot_json_list_fields(
        row_dict,
        (("daily_json", None), ("topic_states_json", None)),
        load_ctx,
        remap_null_or_zero_char=True,
    )
    return row_dict


def _hook_remap_entity_contract_holder(row_dict: dict[str, Any], load_ctx: dict[str, Any]) -> dict[str, Any]:
    if row_dict.get("holder_type") == "player" and row_dict.get("character_id") in (None, 0, load_ctx["old_host_char_id"]):
        row_dict["character_id"] = load_ctx["char_id"]
    return row_dict


def _hook_remap_contract_turn_snapshot_json(row_dict: dict[str, Any], load_ctx: dict[str, Any]) -> dict[str, Any]:
    _rewrite_snapshot_json_list_fields(
        row_dict,
        (("contracts_json", "contract_key"), ("grudges_json", "grudge_key")),
        load_ctx,
        remap_null_or_zero_char=False,
    )
    return row_dict


def _hook_rewrite_quest_remediation_scar(row_dict: dict[str, Any], load_ctx: dict[str, Any]) -> dict[str, Any]:
    old_sid = load_ctx["old_session_id"]
    new_sid = load_ctx["new_session_id"]
    if old_sid and "remediation_scar:" in str(row_dict.get("quest_notes") or ""):
        old_scar_tok = f"remediation_scar:scar_{int(old_sid)}_"
        new_scar_tok = f"remediation_scar:scar_{int(new_sid)}_"
        row_dict["quest_notes"] = str(row_dict["quest_notes"]).replace(old_scar_tok, new_scar_tok)
    return row_dict


def _hook_remap_world_event_contact_id(row_dict: dict[str, Any], load_ctx: dict[str, Any]) -> dict[str, Any]:
    contact_id_map: dict[int, int] = load_ctx["id_maps"]["contacts"]
    old_imp = row_dict.get("implicated_contact_id")
    if old_imp is not None:
        try:
            row_dict["implicated_contact_id"] = contact_id_map.get(int(old_imp))
        except (TypeError, ValueError):
            pass
    return row_dict


def _hook_rewrite_campaign_spine_session_keys(row_dict: dict[str, Any], load_ctx: dict[str, Any]) -> dict[str, Any]:
    old_sid = load_ctx["old_session_id"]
    new_sid = load_ctx["new_session_id"]
    if old_sid:
        for sp_col in (
            "mastermind_profile_json",
            "lieutenants_roster_json",
            "chapters_blueprint_json",
            "nemeses_json",
            "hidden_bible_json",
            "ending_axes_json",
            "chronicle_tapestry_json",
            "state_events_json",
        ):
            raw_sp = row_dict.get(sp_col)
            if not raw_sp:
                continue
            try:
                parsed_sp = json.loads(raw_sp) if isinstance(raw_sp, str) else raw_sp
                row_dict[sp_col] = json.dumps(_rewrite_spine_embedded_ids(parsed_sp, old_sid, new_sid))
            except Exception:
                pass
    return row_dict


def _hook_normalize_world_roster_row(row_dict: dict[str, Any], load_ctx: dict[str, Any]) -> dict[str, Any]:
    raw_wr_id = str(row_dict.get("npc_id") or row_dict.get("name") or "").strip().lower()
    clean_wr_id = re.sub(r"[^a-z0-9]+", "_", raw_wr_id).strip("_")
    if clean_wr_id:
        row_dict["npc_id"] = clean_wr_id
    try:
        row_dict["affinity_score"] = max(-100, min(300, int(row_dict.get("affinity_score") or 0)))
    except (TypeError, ValueError):
        row_dict["affinity_score"] = 0
    for wr_col, wr_default in (
        ("roaming_route_json", "[]"),
        ("traits_json", "[]"),
        ("discovered_slots_json", "{}"),
        ("basic_info_json", "{}"),
        ("appearance_json", "{}"),
        ("turn_snapshots_json", "{}"),
    ):
        wr_val = row_dict.get(wr_col)
        if wr_val is None:
            row_dict[wr_col] = wr_default
        elif isinstance(wr_val, (dict, list)):
            row_dict[wr_col] = json.dumps(wr_val)
        elif isinstance(wr_val, str):
            try:
                json.loads(wr_val)
            except (json.JSONDecodeError, TypeError, ValueError):
                row_dict[wr_col] = wr_default
    return row_dict


def _remap_nested_contact_ids(obj: Any, contact_id_map: dict[int, int]) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in _CONTACT_ID_FIELDS and v is not None:
                try:
                    out[k] = contact_id_map.get(int(v))
                except (TypeError, ValueError):
                    out[k] = v
            else:
                out[k] = _remap_nested_contact_ids(v, contact_id_map)
        return out
    if isinstance(obj, list):
        return [_remap_nested_contact_ids(x, contact_id_map) for x in obj]
    return obj


def _remap_nested_session_keys(obj: Any, old_sid: int | None, new_sid: int) -> Any:
    if not old_sid or not obj:
        return obj
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in ("key", "lieutenant_key", "nemesis_id", "seed_key", "node_id", "dossier_key", "quest_key") and isinstance(v, str):
                out[k] = _rewrite_session_key_id(v, old_sid, new_sid)
            else:
                out[k] = _remap_nested_session_keys(v, old_sid, new_sid)
        return out
    if isinstance(obj, list):
        return [_remap_nested_session_keys(x, old_sid, new_sid) for x in obj]
    if isinstance(obj, str) and re.match(r"^(?:lt|nem|hh|rv|cm|we|scar|bible|rendezvous|promise|pact|grudge)_\d+(?:_|$)", obj):
        return _rewrite_session_key_id(obj, old_sid, new_sid)
    return obj


def _remap_nested_clue_ids(obj: Any, clue_id_map: dict[int, int]) -> Any:
    if not obj:
        return obj
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in ("clue_id", "synthesized_clue_id", "paired_with_clue_id", "clue_a_id", "clue_b_id") and v is not None:
                try:
                    out[k] = clue_id_map.get(int(v))
                except (TypeError, ValueError):
                    out[k] = v
            elif k in ("paired_with", "pairs_with", "consumed_clue_ids"):
                if isinstance(v, int):
                    out[k] = clue_id_map.get(v)
                elif isinstance(v, str) and v.strip().isdigit():
                    mapped_str = clue_id_map.get(int(v.strip()))
                    out[k] = str(mapped_str) if mapped_str is not None else None
                elif isinstance(v, list):
                    remapped_list = []
                    for p in v:
                        if isinstance(p, int):
                            mp = clue_id_map.get(p)
                            if mp is not None:
                                remapped_list.append(mp)
                        elif isinstance(p, str) and p.strip().isdigit():
                            mp = clue_id_map.get(int(p.strip()))
                            if mp is not None:
                                remapped_list.append(str(mp))
                        else:
                            remapped_list.append(p)
                    out[k] = remapped_list
                else:
                    out[k] = v
            else:
                out[k] = _remap_nested_clue_ids(v, clue_id_map)
        return out
    if isinstance(obj, list):
        return [_remap_nested_clue_ids(x, clue_id_map) for x in obj]
    return obj


def _post_sync_loaded_player_properties(load_ctx: dict[str, Any]) -> None:
    conn = load_ctx["conn"]
    new_sid = load_ctx["new_session_id"]
    child_data = load_ctx["child_data"]
    try:
        from mechanics.world.locations.realty_catalog import is_anomalous_realty_scenario
        from .properties import grant_or_relocate_starter_quarters, _set_facility_unlock_state
        conn.execute(
            "UPDATE player_properties SET buyer_character_id = ? WHERE session_id = ? AND buyer_character_id IS NOT NULL",
            (int(load_ctx["char_id"]), new_sid),
        )
        load_scen_row = conn.execute("SELECT scenario FROM sessions WHERE id = ?", (new_sid,)).fetchone()
        load_scen = str((load_scen_row["scenario"] if load_scen_row else "") or "")
        if is_anomalous_realty_scenario(load_scen):
            if not child_data.get("player_properties"):
                grant_or_relocate_starter_quarters(new_sid, conn=conn)
            else:
                for pr in conn.execute(
                    "SELECT facility_node_id, is_starter FROM player_properties WHERE session_id = ?",
                    (new_sid,),
                ).fetchall():
                    m_key = "starter_unlocked" if int(pr["is_starter"] or 0) == 1 else "deed_owned"
                    _set_facility_unlock_state(conn, new_sid, str(pr["facility_node_id"]), unlocked=True, marker_key=m_key)
    except Exception:
        pass


def _post_rebuild_session_digests_fts(load_ctx: dict[str, Any]) -> None:
    from .memory import rebuild_session_digests_fts
    rebuild_session_digests_fts(load_ctx["conn"], load_ctx["new_session_id"])


def _post_remap_clue_deduction_parents(load_ctx: dict[str, Any]) -> None:
    clue_id_map: dict[int, int] = load_ctx["id_maps"]["session_clues"]
    conn = load_ctx["conn"]
    new_sid = load_ctx["new_session_id"]
    cl_rows = conn.execute("SELECT id, deduction_parents_json FROM session_clues WHERE session_id = ?", (new_sid,)).fetchall()
    for cl_r in cl_rows:
        try:
            raw_parents = json.loads(cl_r["deduction_parents_json"] or "[]")
            if isinstance(raw_parents, list) and raw_parents:
                remapped_parents = []
                for pid in raw_parents:
                    if pid is None:
                        continue
                    try:
                        mapped_pid = clue_id_map.get(int(pid))
                        if mapped_pid is not None:
                            remapped_parents.append(mapped_pid)
                    except (TypeError, ValueError):
                        pass
                conn.execute(
                    "UPDATE session_clues SET deduction_parents_json = ? WHERE id = ?",
                    (json.dumps(remapped_parents), cl_r["id"]),
                )
        except Exception:
            pass


def _post_remap_commitments_conflicting_ids(load_ctx: dict[str, Any]) -> None:
    commitment_id_map: dict[int, int] = load_ctx["id_maps"]["commitments_ledger"]
    conn = load_ctx["conn"]
    new_sid = load_ctx["new_session_id"]
    cm_rows = conn.execute("SELECT id, metadata_json FROM commitments_ledger WHERE session_id = ?", (new_sid,)).fetchall()
    for cm_r in cm_rows:
        try:
            cm_meta = json.loads(cm_r["metadata_json"] or "{}")
            if isinstance(cm_meta, dict) and isinstance(cm_meta.get("conflicting_ids"), list):
                remapped_conflicts = []
                for cid in cm_meta["conflicting_ids"]:
                    if cid is None:
                        continue
                    try:
                        mapped_cid = commitment_id_map.get(int(cid))
                        if mapped_cid is not None:
                            remapped_conflicts.append(mapped_cid)
                    except (TypeError, ValueError):
                        pass
                cm_meta["conflicting_ids"] = remapped_conflicts
                conn.execute("UPDATE commitments_ledger SET metadata_json = ? WHERE id = ?", (json.dumps(cm_meta), cm_r["id"]))
        except Exception:
            pass


def _post_remap_campaign_spines_nested_ids(load_ctx: dict[str, Any]) -> None:
    conn = load_ctx["conn"]
    old_sid = load_ctx["old_session_id"]
    new_sid = load_ctx["new_session_id"]
    contact_id_map: dict[int, int] = load_ctx["id_maps"]["contacts"]
    sp_rows = conn.execute(
        "SELECT id, lieutenants_roster_json, nemeses_json, state_events_json FROM campaign_spines WHERE session_id = ?",
        (new_sid,),
    ).fetchall()
    for sp_r in sp_rows:
        try:
            lts = json.loads(sp_r["lieutenants_roster_json"] or "[]")
            nems = json.loads(sp_r["nemeses_json"] or "[]")
            sp_events = json.loads(sp_r["state_events_json"] or "[]")
            if isinstance(lts, list):
                lts = _remap_nested_session_keys(_remap_nested_contact_ids(lts, contact_id_map), old_sid, new_sid)
            if isinstance(nems, list):
                nems = _remap_nested_session_keys(_remap_nested_contact_ids(nems, contact_id_map), old_sid, new_sid)
            if isinstance(sp_events, list):
                sp_events = _remap_nested_session_keys(_remap_nested_contact_ids(sp_events, contact_id_map), old_sid, new_sid)
            conn.execute(
                "UPDATE campaign_spines SET lieutenants_roster_json = ?, nemeses_json = ?, state_events_json = ? WHERE id = ?",
                (json.dumps(lts), json.dumps(nems), json.dumps(sp_events), sp_r["id"]),
            )
        except Exception:
            pass


def _post_remap_quest_dossiers_nested_ids(load_ctx: dict[str, Any]) -> None:
    conn = load_ctx["conn"]
    old_sid = load_ctx["old_session_id"]
    new_sid = load_ctx["new_session_id"]
    contact_id_map: dict[int, int] = load_ctx["id_maps"]["contacts"]
    clue_id_map: dict[int, int] = load_ctx["id_maps"]["session_clues"]
    qd_rows = conn.execute(
        """SELECT id, cast_bindings_json, clue_graph_json, leads_graph_json,
                  twist_spec_json, climax_spec_json, state_events_json
           FROM quest_dossiers WHERE session_id = ?""",
        (new_sid,),
    ).fetchall()
    for qd_r in qd_rows:
        try:
            cast_b = _remap_nested_session_keys(_remap_nested_contact_ids(json.loads(qd_r["cast_bindings_json"] or "{}"), contact_id_map), old_sid, new_sid)
            clue_g = _remap_nested_session_keys(_remap_nested_clue_ids(json.loads(qd_r["clue_graph_json"] or "[]"), clue_id_map), old_sid, new_sid)
            leads_g = _remap_nested_session_keys(_remap_nested_clue_ids(_remap_nested_contact_ids(json.loads(qd_r["leads_graph_json"] or "[]"), contact_id_map), clue_id_map), old_sid, new_sid)
            twist_s = _remap_nested_session_keys(_remap_nested_contact_ids(json.loads(qd_r["twist_spec_json"] or "{}"), contact_id_map), old_sid, new_sid)
            climax_s = _remap_nested_session_keys(_remap_nested_clue_ids(_remap_nested_contact_ids(json.loads(qd_r["climax_spec_json"] or "{}"), contact_id_map), clue_id_map), old_sid, new_sid)
            qd_events = json.loads(qd_r["state_events_json"] or "[]")
            if isinstance(qd_events, list):
                qd_events = _remap_nested_session_keys(_remap_nested_clue_ids(_remap_nested_contact_ids(qd_events, contact_id_map), clue_id_map), old_sid, new_sid)
            conn.execute(
                """UPDATE quest_dossiers
                   SET cast_bindings_json = ?, clue_graph_json = ?, leads_graph_json = ?,
                       twist_spec_json = ?, climax_spec_json = ?, state_events_json = ?
                   WHERE id = ?""",
                (
                    json.dumps(cast_b),
                    json.dumps(clue_g),
                    json.dumps(leads_g),
                    json.dumps(twist_s),
                    json.dumps(climax_s),
                    json.dumps(qd_events),
                    qd_r["id"],
                ),
            )
        except Exception:
            pass


def _post_rematerialize_contacts_relations(load_ctx: dict[str, Any]) -> None:
    conn = load_ctx["conn"]
    new_sid = load_ctx["new_session_id"]
    sess_dict = load_ctx["sess_dict"]
    try:
        import mechanics.social.relationship_graph as rg
        import mechanics.social.genealogy as gen
        from .social import _parse_household_row
        scen_key = str(sess_dict.get("scenario") or "fantasy")
        hh_by_id: dict[int, dict[str, Any]] = {}
        try:
            for hh_row in conn.execute("SELECT * FROM households WHERE session_id = ?", (new_sid,)).fetchall():
                parsed_hh = _parse_household_row(hh_row)
                if parsed_hh.get("id") is not None:
                    hh_by_id[int(parsed_hh["id"])] = parsed_hh
        except sqlite3.OperationalError as hh_exc:
            if "no such table" not in str(hh_exc).lower():
                raise
        cloned_contacts = conn.execute("SELECT * FROM contacts WHERE session_id = ?", (new_sid,)).fetchall()
        for cr in cloned_contacts:
            cd_item = dict(cr)
            for j_col, out_col in (
                ("basic_info_json", "basic_info"),
                ("appearance_json", "appearance"),
                ("relations_json", "relations"),
            ):
                try:
                    cd_item[out_col] = json.loads(cd_item.get(j_col) or "{}")
                except Exception:
                    cd_item[out_col] = {}
            mat_rel = rg.materialize_relations(new_sid, cd_item, conn=conn)
            if cd_item.get("household_id"):
                try:
                    hh_key_id = int(cd_item["household_id"])
                except (TypeError, ValueError):
                    hh_key_id = 0
                hh_obj = hh_by_id.get(hh_key_id)
                if hh_obj is None and hh_key_id:
                    hh_obj = db.get_household_by_id(hh_key_id)
                if hh_obj:
                    hh_hydrated = gen._hydrate_household_entity(hh_obj, cd_item, scen_key)
                    mat_rel["family"] = gen.build_family_tree_for_member(
                        hh_hydrated,
                        cd_item.get("name", ""),
                        scenario=scen_key,
                        member_role=cd_item.get("household_role") or "child",
                    )
                    mat_rel["household_id"] = cd_item["household_id"]
                    orig_rel = cd_item.get("relations") if isinstance(cd_item.get("relations"), dict) else {}
                    if orig_rel.get("cohabiting_family") is False:
                        mat_rel["cohabiting_family"] = False
                        if orig_rel.get("residence_location"):
                            mat_rel["residence_location"] = orig_rel["residence_location"]
                        if orig_rel.get("residence_node_id"):
                            mat_rel["residence_node_id"] = orig_rel["residence_node_id"]
                    elif hh_hydrated.get("residence_location"):
                        mat_rel["residence_location"] = hh_hydrated["residence_location"]
            conn.execute(
                "UPDATE contacts SET relations_json = ? WHERE id = ?",
                (json.dumps(mat_rel), cd_item["id"]),
            )
    except Exception as exc:
        _log.warning("Post-load contacts relation rematerialization failed for session %s: %s", new_sid, exc)


def _post_inv_remap_quest_dossiers_inventory_ids(load_ctx: dict[str, Any]) -> None:
    conn = load_ctx["conn"]
    new_sid = load_ctx["new_session_id"]
    char_id = load_ctx["char_id"]
    user_id = load_ctx["user_id"]
    inv_id_map: dict[int, int] = load_ctx["inv_id_map"]
    qd_rows = conn.execute(
        "SELECT id, quest_id, tangible_item_json, state_events_json FROM quest_dossiers WHERE session_id = ?",
        (new_sid,),
    ).fetchall()
    for qd_row in qd_rows:
        try:
            t_item = json.loads(qd_row["tangible_item_json"] or "{}")
            t_changed = False
            if isinstance(t_item, dict) and t_item.get("has_item"):
                old_inv_id = t_item.get("inventory_id")
                new_inv_id = inv_id_map.get(old_inv_id) if old_inv_id is not None else None
                if not new_inv_id:
                    q_name = t_item.get("name")
                    inv_match = conn.execute(
                        "SELECT id FROM inventory WHERE (character_id = ? OR user_id = ?) AND name = ? ORDER BY id DESC LIMIT 1",
                        (char_id, user_id, q_name),
                    ).fetchone()
                    if inv_match:
                        new_inv_id = inv_match["id"]
                if new_inv_id and new_inv_id != old_inv_id:
                    t_item["inventory_id"] = new_inv_id
                    t_changed = True
            ev_list = json.loads(qd_row["state_events_json"] or "[]")
            ev_changed = False
            if isinstance(ev_list, list):
                for ev in ev_list:
                    if isinstance(ev, dict) and ev.get("kind") == "tangible_item":
                        for side in ("prev", "next"):
                            snap = ev.get(side)
                            if isinstance(snap, dict) and snap.get("inventory_id") in inv_id_map:
                                snap["inventory_id"] = inv_id_map[snap["inventory_id"]]
                                ev_changed = True
            if t_changed or ev_changed:
                conn.execute(
                    "UPDATE quest_dossiers SET tangible_item_json = ?, state_events_json = ? WHERE id = ?",
                    (json.dumps(t_item), json.dumps(ev_list), qd_row["id"]),
                )
        except Exception:
            pass


def _post_inv_remap_epistemic_proof_refs(load_ctx: dict[str, Any]) -> None:
    _remap_epistemic_proof_refs(
        load_ctx["conn"],
        load_ctx["new_session_id"],
        load_ctx["id_maps"]["session_clues"],
        load_ctx["inv_id_map"],
    )


_ROW_TRANSFORM_HOOKS: dict[str, Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]] = {
    "restore_contact_row": _hook_restore_contact_row,
    "remap_social_turn_snapshot_json": _hook_remap_social_turn_snapshot_json,
    "remap_entity_contract_holder": _hook_remap_entity_contract_holder,
    "remap_contract_turn_snapshot_json": _hook_remap_contract_turn_snapshot_json,
    "rewrite_quest_remediation_scar": _hook_rewrite_quest_remediation_scar,
    "remap_world_event_contact_id": _hook_remap_world_event_contact_id,
    "rewrite_campaign_spine_session_keys": _hook_rewrite_campaign_spine_session_keys,
    "normalize_world_roster_row": _hook_normalize_world_roster_row,
}

_POST_LOAD_HOOKS: dict[str, Callable[[dict[str, Any]], None]] = {
    "sync_loaded_player_properties": _post_sync_loaded_player_properties,
    "rematerialize_contacts_relations": _post_rematerialize_contacts_relations,
    "rebuild_session_digests_fts": _post_rebuild_session_digests_fts,
    "remap_clue_deduction_parents": _post_remap_clue_deduction_parents,
    "remap_commitments_conflicting_ids": _post_remap_commitments_conflicting_ids,
    "remap_campaign_spines_nested_ids": _post_remap_campaign_spines_nested_ids,
    "remap_quest_dossiers_nested_ids": _post_remap_quest_dossiers_nested_ids,
}

_POST_INVENTORY_HOOKS: dict[str, Callable[[dict[str, Any]], None]] = {
    "remap_quest_dossiers_inventory_ids": _post_inv_remap_quest_dossiers_inventory_ids,
    "remap_epistemic_proof_refs": _post_inv_remap_epistemic_proof_refs,
}


def _fallback_lookup_existing_row_id(
    spec: SessionTableSpec,
    row_dict: dict[str, Any],
    load_ctx: dict[str, Any],
) -> Optional[int]:
    conn = load_ctx["conn"]
    new_sid = load_ctx["new_session_id"]
    if spec.name == "households":
        existing = conn.execute(
            "SELECT id FROM households WHERE session_id = ? AND household_key = ?",
            (new_sid, row_dict.get("household_key")),
        ).fetchone()
        return int(existing["id"]) if existing else None
    if spec.name == "contacts":
        existing = conn.execute(
            "SELECT id FROM contacts WHERE session_id = ? AND character_id = ? AND npc_id = ?",
            (new_sid, load_ctx["char_id"], row_dict.get("npc_id")),
        ).fetchone()
        return int(existing["id"]) if existing else None
    return None


def _record_loaded_row_identity(
    spec: SessionTableSpec,
    row_dict: dict[str, Any],
    orig_id: Any,
    lastrowid: int,
    load_ctx: dict[str, Any],
) -> None:
    new_id = lastrowid or _fallback_lookup_existing_row_id(spec, row_dict, load_ctx)
    if orig_id is not None and new_id and spec.name in load_ctx["id_maps"]:
        try:
            load_ctx["id_maps"][spec.name][int(orig_id)] = int(new_id)
        except (TypeError, ValueError):
            pass
    if spec.name == "households" and new_id:
        sname = str(row_dict.get("surname") or "").strip().lower()
        if sname:
            load_ctx["household_surname_map"][sname] = int(new_id)


def count_character_adventure_saves(character_id: int) -> int:
    """Returns the total number of saved checkpoints for a specific character."""
    if not character_id:
        return 0
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM adventure_saves WHERE character_id = ?",
            (character_id,)
        ).fetchone()
        return row["cnt"] if row else 0

def save_adventure_slot(user_id: int, slot_name: str, overwrite: bool = False) -> dict:
    """Creates or overwrites a named checkpoint save slot for the user's active character."""
    cleaned_slot = (slot_name or "").strip()
    if not cleaned_slot or len(cleaned_slot) > 32:
        raise ValueError("Save slot name must be between 1 and 32 characters.")
    if not re.match(r"^[\w\s\-]+$", cleaned_slot, re.UNICODE):
        raise ValueError("Slot name contains invalid characters. Use letters, numbers, spaces, hyphens, or underscores.")

    with UnitOfWork() as conn:
        char = db.get_character(user_id)
        if not char:
            raise ValueError("You don't have an active character. Create one with `/character create` first.")
        char_id = char["id"]

        session_id = db.get_active_session_id_for_user(user_id)
        if not session_id:
            raise ValueError("You are not currently in an active adventure to save.")

        sess_row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not sess_row or sess_row["status"] != "active":
            raise ValueError("Your current adventure session is not active.")
        sess_dict = dict(sess_row)

        existing = conn.execute(
            "SELECT id, slot_name FROM adventure_saves WHERE character_id = ? AND LOWER(slot_name) = LOWER(?)",
            (char_id, cleaned_slot)
        ).fetchone()

        if existing and not overwrite:
            return {
                "status": "exists",
                "slot_name": existing["slot_name"],
                "message": f"Save slot **{existing['slot_name']}** already exists. Overwrite?"
            }

        total_saves = conn.execute(
            "SELECT COUNT(*) as cnt FROM adventure_saves WHERE character_id = ?",
            (char_id,)
        ).fetchone()["cnt"]
        if not existing and total_saves >= MAX_SAVE_SLOTS_PER_CHAR:
            raise ValueError(f"Maximum save slots reached ({MAX_SAVE_SLOTS_PER_CHAR} slots per character). Delete an older save first.")

        # Gather all child table data declaratively from SESSION_TABLE_REGISTRY
        child_data = {}
        for spec in get_save_specs():
            try:
                if spec.save_row_limit_by_turn and spec.save_order_col:
                    rows = conn.execute(
                        f"SELECT * FROM {spec.name} WHERE session_id = ? ORDER BY {spec.save_order_col} DESC LIMIT ?",
                        (session_id, int(spec.save_row_limit_by_turn)),
                    ).fetchall()
                    rows = list(reversed(rows))
                else:
                    rows = conn.execute(
                        f"SELECT * FROM {spec.name} WHERE session_id = ?",
                        (session_id,),
                    ).fetchall()
                cleaned_rows = []
                for r in rows:
                    rd = dict(r)
                    if spec.orig_id_alias:
                        rd[spec.orig_id_alias] = rd.get("id")
                    rd.pop("id", None)
                    cleaned_rows.append(rd)
                child_data[spec.name] = cleaned_rows
            except sqlite3.OperationalError as exc:
                if spec.optional_table and "no such table" in str(exc).lower():
                    child_data[spec.name] = []
                else:
                    raise

        # Gather character adventure inventory (including session-scoped quest items where character_id IS NULL)
        inv_rows = conn.execute(
            "SELECT * FROM inventory WHERE character_id = ? OR (character_id IS NULL AND user_id = ?)",
            (char_id, user_id),
        ).fetchall()
        cleaned_inv = []
        for r in inv_rows:
            rd = dict(r)
            orig_id = rd.pop("id", None)
            if orig_id is not None:
                rd["_orig_inventory_id"] = orig_id
            cleaned_inv.append(rd)

        # Character adventure vitals & 3-axis resonance snapshot
        char_state = {
            "hp": char["hp"],
            "mp": char["mp"],
            "gold": char["gold"],
            "status_effects": char.get("status_effects", "[]"),
            "days_adventured": char.get("days_adventured", 1),
            "attribute": char.get("attribute"),
            "combat_archetype": char.get("combat_archetype"),
            "ability_medium": char.get("ability_medium"),
            "skill_progress": char.get("skill_progress", "{}"),
            "learned_spells": char.get("learned_spells", "[]"),
            "joined_faction_id": char.get("joined_faction_id", ""),
            "faction_rank": char.get("faction_rank", 0),
            "faction_title": char.get("faction_title", ""),
        }

        # Eagerly capture world_ending_anomaly in extra_json if scenario is anomalous incursions
        try:
            from scenario_data import is_anomalous_incursions_scenario
            if is_anomalous_incursions_scenario(sess_dict.get("scenario", "")):
                extra_raw = sess_dict.get("extra_json") or "{}"
                extra_dict = json.loads(extra_raw) if isinstance(extra_raw, str) else dict(extra_raw or {})
                if "world_ending_anomaly" not in extra_dict:
                    import namegen
                    extra_dict["world_ending_anomaly"] = namegen.generate_world_ending_anomaly_profile(hash_val=int(session_id or 1))
                    sess_dict["extra_json"] = json.dumps(extra_dict)
                    conn.execute("UPDATE sessions SET extra_json = ? WHERE id = ?", (sess_dict["extra_json"], session_id))
        except Exception:
            pass

        # Sanitize mid-combat ephemeral constructs and summons before saving snapshot
        try:
            curr_npcs_raw = sess_dict.get("current_npcs_json") or "[]"
            curr_npcs_list = json.loads(curr_npcs_raw) if isinstance(curr_npcs_raw, str) else list(curr_npcs_raw or [])
            cleaned_npcs = [
                n for n in curr_npcs_list
                if not (isinstance(n, dict) and (n.get("is_summon") or n.get("is_autonomous_construct")))
            ]
            sess_dict["current_npcs_json"] = json.dumps(cleaned_npcs)
        except Exception:
            pass

        snapshot = {
            "version": 1,
            "session": sess_dict,
            "child_tables": child_data,
            "character_state": char_state,
            "inventory": cleaned_inv
        }
        snapshot_json = json.dumps(snapshot, default=_json_dataclass_default)

        scenario = sess_dict.get("scenario", "fantasy")
        scene_title = sess_dict.get("scene_title") or "Adventure Continues"
        narrative_snippet = (sess_dict.get("narrative") or "")[:250].strip()
        current_location = sess_dict.get("current_location") or ""
        now = time.time()

        if existing:
            conn.execute(
                """UPDATE adventure_saves
                   SET slot_name = ?, scenario = ?, scene_title = ?, narrative_snippet = ?,
                       current_location = ?, saved_at = ?, snapshot_data = ?
                   WHERE id = ?""",
                (cleaned_slot, scenario, scene_title, narrative_snippet, current_location, now, snapshot_json, existing["id"])
            )
            save_id = existing["id"]
        else:
            cur = conn.execute(
                """INSERT INTO adventure_saves (user_id, character_id, slot_name, scenario, scene_title,
                                               narrative_snippet, current_location, saved_at, snapshot_data)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, char_id, cleaned_slot, scenario, scene_title, narrative_snippet, current_location, now, snapshot_json)
            )
            save_id = cur.lastrowid

    return {
        "status": "saved",
        "save_id": save_id,
        "slot_name": cleaned_slot,
        "scenario": scenario,
        "scene_title": scene_title,
        "narrative_snippet": narrative_snippet,
        "current_location": current_location,
        "saved_at": now
    }

def load_adventure_slot(user_id: int, slot_name: str) -> dict:
    """Restores an adventure save slot into a fresh active session for the character."""
    with UnitOfWork() as conn:
        char = db.get_character(user_id)
        if not char:
            raise ValueError("You don't have an active character. Create one with `/character create` first.")
        char_id = char["id"]

        row = conn.execute(
            "SELECT * FROM adventure_saves WHERE character_id = ? AND LOWER(slot_name) = LOWER(?)",
            (char_id, (slot_name or "").strip())
        ).fetchone()

        if not row:
            raise ValueError(f"No save slot found named '{slot_name}'. Use `/adventure saves` to view available saves.")

        snapshot = json.loads(row["snapshot_data"])
        sess_dict = snapshot["session"]
        child_data = snapshot.get("child_tables", {})
        char_state = snapshot.get("character_state", {})
        saved_inv = snapshot.get("inventory", [])

        # If user has an active session in progress, retire it
        active_sess_id = char.get("active_session_id")
        if active_sess_id:
            conn.execute("UPDATE sessions SET status='finished', updated_at=? WHERE id=?", (time.time(), active_sess_id))
            conn.execute("UPDATE characters SET active_session_id=NULL WHERE id=?", (char_id,))

        # Restore session with fresh ID, timestamp, and active status
        now = time.time()
        to = sess_dict.get("turn_order")
        if isinstance(to, str):
            try:
                to = json.loads(to)
            except Exception:
                to = [user_id]
        if not to or user_id not in to:
            to = [user_id]

        sess_data = dict(sess_dict)
        sess_data.pop("id", None)
        sess_data["character_id"] = char_id
        sess_data.setdefault("schema_epoch", 1)
        sess_data.setdefault("mode", "solo")
        sess_data.setdefault("capacity", 1)
        if "turn_count" not in sess_data or sess_data.get("turn_count") is None:
            raw_hist = sess_data.get("history_json") or "[]"
            try:
                hist_obj = json.loads(raw_hist) if isinstance(raw_hist, str) else list(raw_hist)
                if isinstance(hist_obj, list):
                    action_turns = [h for h in hist_obj if not (isinstance(h, dict) and h.get("type") == "scene")]
                    sess_data["turn_count"] = len(action_turns)
                else:
                    sess_data["turn_count"] = 0
            except Exception:
                sess_data["turn_count"] = 0
        sess_data.setdefault("last_digested_turn", 0)
        sess_data["status"] = "active"
        sess_data["created_at"] = now
        sess_data["updated_at"] = now
        sess_data["turn_order"] = json.dumps(to)

        # Sanitize mid-combat ephemeral constructs and summons on load
        try:
            curr_npcs_raw = sess_data.get("current_npcs_json") or "[]"
            curr_npcs_list = json.loads(curr_npcs_raw) if isinstance(curr_npcs_raw, str) else list(curr_npcs_raw or [])
            cleaned_npcs = [
                n for n in curr_npcs_list
                if not (isinstance(n, dict) and (n.get("is_summon") or n.get("is_autonomous_construct")))
            ]
            sess_data["current_npcs_json"] = json.dumps(cleaned_npcs)
        except Exception:
            pass

        # Preserve origin session provenance for folklore codex turn-gating and strip legacy anomaly JSON keys
        from .dossiers import SESSION_ANOMALY_KEY_TO_RECORD_TYPE, sync_session_anomaly_records_from_extra

        old_session_id = sess_dict.get("id")
        has_rel_anom = bool(child_data.get("session_anomaly_records"))
        raw_extra = sess_data.get("extra_json")
        if isinstance(raw_extra, str):
            try:
                ex_obj = json.loads(raw_extra) if raw_extra.strip() else {}
            except Exception:
                ex_obj = {}
        elif isinstance(raw_extra, dict):
            ex_obj = dict(raw_extra)
        else:
            ex_obj = {}
        if not isinstance(ex_obj, dict):
            ex_obj = {}

        if old_session_id is not None:
            try:
                old_sid_int = int(old_session_id)
                origin_ids: list[int] = []
                for _osid in (ex_obj.get("_origin_session_ids") or []):
                    try:
                        _iv = int(_osid)
                        if _iv not in origin_ids:
                            origin_ids.append(_iv)
                    except (TypeError, ValueError):
                        pass
                if old_sid_int not in origin_ids:
                    origin_ids.append(old_sid_int)
                ex_obj["_origin_session_ids"] = origin_ids
            except (TypeError, ValueError):
                pass

        legacy_anom_patch: dict[str, list] = {}
        for anom_key in SESSION_ANOMALY_KEY_TO_RECORD_TYPE:
            popped_val = ex_obj.pop(anom_key, None) if anom_key in ex_obj else None
            if not has_rel_anom:
                cand_val = popped_val if isinstance(popped_val, list) and popped_val else sess_dict.get(anom_key)
                if isinstance(cand_val, list) and cand_val:
                    legacy_anom_patch[anom_key] = cand_val
        sess_data["extra_json"] = ex_obj

        legacy_phys_patch: dict | None = None
        raw_phys = sess_data.get("physical_state_json")
        if raw_phys:
            try:
                p_obj = json.loads(raw_phys) if isinstance(raw_phys, str) else dict(raw_phys)
                if isinstance(p_obj, dict) and isinstance(p_obj.get("actors"), dict) and p_obj["actors"]:
                    legacy_phys_patch = dict(p_obj)
                    clean_room_meta = {k: v for k, v in p_obj.items() if k != "actors"}
                    sess_data["physical_state_json"] = json.dumps(clean_room_meta) if clean_room_meta else "{}"
            except Exception:
                legacy_phys_patch = None

        # Filter strictly to columns present in live sessions table
        valid_session_cols = {
            r["name"] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        sess_data.setdefault("combat_threat_ledger_json", "{}")
        sess_data.setdefault("combat_boss_telegraph_json", "{}")
        sess_data.setdefault("show_enemy_hp", 1)
        sess_data.setdefault("show_enemy_intent", 1)
        if not sess_data.get("narrative_pacing"):
            sess_data["narrative_pacing"] = (
                "concise"
                if str(sess_data.get("verbosity") or "").strip().lower() in ("concise", "direct")
                else "balanced"
            )
        if str(sess_data.get("verbosity") or "").strip().lower() in ("concise", "direct"):
            sess_data["verbosity"] = "normal"
        sess_data = {k: v for k, v in sess_data.items() if k in valid_session_cols}

        # Make sure any dict/list fields are serialized
        for k, v in sess_data.items():
            if isinstance(v, (dict, list)):
                sess_data[k] = json.dumps(v)

        cols = list(sess_data.keys())
        placeholders = ",".join("?" * len(cols))
        col_str = ",".join(cols)
        cur = conn.execute(f"INSERT INTO sessions ({col_str}) VALUES ({placeholders})", list(sess_data.values()))
        new_session_id = cur.lastrowid

        # Register session_members
        conn.execute(
            "INSERT OR IGNORE INTO session_members (session_id, user_id, joined_at) VALUES (?, ?, ?)",
            (new_session_id, user_id, now)
        )

        # Restore session child tables in declarative registry load_tier order
        load_specs = get_load_specs()
        load_ctx: dict[str, Any] = {
            "conn": conn,
            "user_id": user_id,
            "char_id": char_id,
            "old_session_id": sess_dict.get("id"),
            "new_session_id": new_session_id,
            "old_host_char_id": sess_dict.get("character_id"),
            "sess_dict": sess_dict,
            "child_data": child_data,
            "id_maps": {
                "households": {},
                "contacts": {},
                "commitments_ledger": {},
                "session_clues": {},
            },
            "household_surname_map": {},
            "inv_id_map": {},
        }

        table_cols_cache: dict[str, set[str]] = {}

        def _valid_cols(t_name: str) -> set[str]:
            if t_name not in table_cols_cache:
                table_cols_cache[t_name] = {
                    r["name"] for r in conn.execute(f"PRAGMA table_info({t_name})").fetchall()
                }
            return table_cols_cache[t_name]

        old_session_id = load_ctx["old_session_id"]
        for spec in load_specs:
            rows = child_data.get(spec.name, [])
            if not rows:
                continue
            t_valid = _valid_cols(spec.name)
            if not t_valid:
                continue
            row_hook = _ROW_TRANSFORM_HOOKS.get(spec.row_transform_hook) if spec.row_transform_hook else None
            for r in rows:
                orig_id = r.get(spec.orig_id_alias) if spec.orig_id_alias else None
                if orig_id is None and spec.name == "session_clues":
                    orig_id = r.get("id")
                row_dict = {k: v for k, v in dict(r).items() if not str(k).startswith("_orig_")}
                row_dict["session_id"] = new_session_id
                if spec.char_id_policy != "none":
                    _apply_char_id_policy(row_dict, spec.char_id_policy, load_ctx)
                if old_session_id and spec.session_key_cols:
                    for key_col in spec.session_key_cols:
                        key_val = row_dict.get(key_col, "")
                        if key_val:
                            row_dict[key_col] = _rewrite_session_key_id(key_val, old_session_id, new_session_id)
                if row_hook is not None:
                    row_dict = row_hook(row_dict, load_ctx)
                row_dict = {
                    k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
                    for k, v in row_dict.items()
                    if k in t_valid and k != "id"
                }
                if not row_dict:
                    continue
                c_names = ",".join(row_dict.keys())
                qmarks = ",".join("?" * len(row_dict))
                cur = conn.execute(
                    f"INSERT OR IGNORE INTO {spec.name} ({c_names}) VALUES ({qmarks})",
                    list(row_dict.values()),
                )
                if spec.orig_id_alias or spec.name == "households":
                    inserted_id = int(cur.lastrowid or 0) if cur.rowcount else 0
                    _record_loaded_row_identity(spec, row_dict, orig_id, inserted_id, load_ctx)

        # Backfill normalized session_anomaly_records when loading a pre-v45 save slot
        if legacy_anom_patch and not child_data.get("session_anomaly_records"):
            sync_session_anomaly_records_from_extra(new_session_id, legacy_anom_patch, conn=conn)

        # Backfill normalized actor_physical_states when loading a pre-v30 save slot
        if legacy_phys_patch and not child_data.get("actor_physical_states"):
            from mechanics.social import physical_state as ps
            ps.sync_state_dict_to_db(new_session_id, legacy_phys_patch, conn=conn)

        # Backfill Migration 49 zone split & hidden folklore villages when loading a pre-v49 save slot
        try:
            import scenario_data as _save_sd
            _load_scen_row = conn.execute("SELECT scenario FROM sessions WHERE id = ?", (new_session_id,)).fetchone()
            _load_scen = str((_load_scen_row["scenario"] if _load_scen_row else "") or "")
            if (
                _save_sd.is_anomalous_incursions_scenario(_load_scen)
                or _save_sd.is_anomalous_high_school_scenario(_load_scen)
                or "urban_anomalies" in _load_scen.lower()
            ):
                _has_sanc = conn.execute(
                    "SELECT 1 FROM world_nodes WHERE session_id = ? AND node_id = 'zone_eastern_sanctuary' LIMIT 1",
                    (new_session_id,),
                ).fetchone()
                if not _has_sanc:
                    from mechanics.world.locations.folklore_veil_lifecycle import backfill_zone_split_and_hidden_villages_v49
                    backfill_zone_split_and_hidden_villages_v49(conn, session_id=new_session_id)
        except Exception:
            pass

        # Backfill Migration 50 contact dossier discoveries on pre-v50 save slots & sync kin/companion/romance exemptions
        try:
            from .social_pacing import backfill_exempt_and_legacy_contact_discoveries
            _is_pre_v50_save = "contact_dossier_discoveries" not in child_data
            backfill_exempt_and_legacy_contact_discoveries(
                conn,
                session_id=new_session_id,
                is_legacy_migration=_is_pre_v50_save,
            )
        except Exception:
            pass

        # Backfill Migration 57 anomalous locations integrity on save load
        try:
            from mechanics.world.anomalous_sites.lifecycle import (
                backfill_anomalous_locations_integrity_v57,
                backfill_outlaw_faction_hqs_and_residences_v60,
            )
            backfill_anomalous_locations_integrity_v57(conn, session_id=new_session_id)
            backfill_outlaw_faction_hqs_and_residences_v60(conn, session_id=new_session_id)
        except Exception:
            pass

        # Run registered post-load hooks (FTS5 rebuild, ID remaps, relations materialization, properties)
        ran_post_hooks: set[str] = set()
        for spec in load_specs:
            if spec.post_load_hook and spec.post_load_hook not in ran_post_hooks:
                ran_post_hooks.add(spec.post_load_hook)
                _POST_LOAD_HOOKS[spec.post_load_hook](load_ctx)

        # Restore character inventory (including session-scoped quest items where character_id IS NULL)
        inv_valid = _valid_cols("inventory")
        conn.execute(
            "DELETE FROM inventory WHERE character_id = ? OR (character_id IS NULL AND user_id = ?)",
            (char_id, user_id),
        )
        inv_id_map = load_ctx["inv_id_map"]
        for item in saved_inv:
            item_dict = dict(item)
            orig_inv_id = item_dict.pop("_orig_inventory_id", None)
            item_dict["character_id"] = char_id
            item_dict["user_id"] = user_id
            linked_ckey = str(item_dict.get("linked_contract_key") or "").strip()
            if linked_ckey and old_session_id:
                linked_ckey = _rewrite_session_key_id(linked_ckey, old_session_id, new_session_id)
                item_dict["linked_contract_key"] = linked_ckey
                raw_eff = str(item_dict.get("effect") or "")
                if raw_eff.startswith("[GEAR_JSON]"):
                    try:
                        eff_meta = json.loads(raw_eff[len("[GEAR_JSON]"):].strip())
                        if isinstance(eff_meta, dict) and eff_meta.get("linked_contract_key"):
                            eff_meta["linked_contract_key"] = linked_ckey
                            item_dict["effect"] = "[GEAR_JSON]" + json.dumps(eff_meta, separators=(",", ":"))
                    except Exception:
                        pass
            item_dict = {
                k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
                for k, v in item_dict.items()
                if k in inv_valid and k != "id"
            }
            if not item_dict:
                continue
            c_names = ",".join(item_dict.keys())
            qmarks = ",".join("?" * len(item_dict))
            cur_inv = conn.execute(f"INSERT INTO inventory ({c_names}) VALUES ({qmarks})", list(item_dict.values()))
            if orig_inv_id is not None and cur_inv.lastrowid:
                try:
                    inv_id_map[int(orig_inv_id)] = int(cur_inv.lastrowid)
                except (TypeError, ValueError):
                    pass
            if linked_ckey and cur_inv.lastrowid:
                try:
                    conn.execute(
                        "UPDATE session_entity_contracts SET bound_gear_item_id = ? WHERE session_id = ? AND contract_key = ?",
                        (int(cur_inv.lastrowid), new_session_id, linked_ckey),
                    )
                except Exception:
                    pass

        # Run registered post-inventory hooks (MacGuffin inventory_id & epistemic proof_artifact_ref remaps)
        ran_post_inv_hooks: set[str] = set()
        for spec in load_specs:
            if spec.post_inventory_hook and spec.post_inventory_hook not in ran_post_inv_hooks:
                ran_post_inv_hooks.add(spec.post_inventory_hook)
                _POST_INVENTORY_HOOKS[spec.post_inventory_hook](load_ctx)

        # Restore character vitals, 3-axis resonance, spell progress, and link active_session_id
        raw_status = char_state.get("status_effects", "[]")
        status_effects_val = json.dumps(raw_status) if isinstance(raw_status, (list, dict)) else str(raw_status or "[]")
        restored_attr = char_state.get("attribute")
        restored_arch = char_state.get("combat_archetype")
        restored_med = char_state.get("ability_medium")
        raw_prog = char_state["skill_progress"] if "skill_progress" in char_state else char.get("skill_progress", "{}")
        prog_val = json.dumps(raw_prog) if isinstance(raw_prog, (list, dict)) else str(raw_prog or "{}")
        raw_spells = char_state["learned_spells"] if "learned_spells" in char_state else char.get("learned_spells", "[]")
        spells_val = json.dumps(raw_spells) if isinstance(raw_spells, (list, dict)) else str(raw_spells or "[]")
        conn.execute(
            """UPDATE characters
               SET hp = ?, mp = ?, gold = ?, status_effects = ?, days_adventured = ?,
                   attribute = ?, combat_archetype = ?, ability_medium = ?,
                   skill_progress = ?, learned_spells = ?, active_session_id = ?,
                   joined_faction_id = ?, faction_rank = ?, faction_title = ?
               WHERE id = ?""",
            (
                char_state.get("hp", char["max_hp"]),
                char_state.get("mp", char["max_mp"]),
                char_state.get("gold", char["gold"]),
                status_effects_val,
                char_state.get("days_adventured", 1),
                restored_attr,
                restored_arch,
                restored_med,
                prog_val,
                spells_val,
                new_session_id,
                char_state.get("joined_faction_id", ""),
                char_state.get("faction_rank", 0),
                char_state.get("faction_title", ""),
                char_id,
            )
        )

        try:
            with savepoint(conn, "sp_load_heal_1"):
                from scenario_data import is_anomalous_incursions_scenario
                if is_anomalous_incursions_scenario(sess_data.get("scenario", "")):
                    from mechanics.combat.items.anomalous_gear import sync_equipped_anomalous_spells
                    sync_equipped_anomalous_spells(user_id)
        except Exception as exc:
            _log.warning("Post-load anomalous gear sync failed for session %s: %s", new_session_id, exc)

        try:
            with savepoint(conn, "sp_load_heal_2"):
                from mechanics.world.locations import _heal_agency_residence_and_entrances
                _heal_agency_residence_and_entrances(new_session_id, sess_data.get("scenario", ""))
        except Exception as exc:
            _log.warning("Post-load agency residence heal failed for session %s: %s", new_session_id, exc)

        try:
            with savepoint(conn, "sp_load_heal_3"):
                import game_engine
                game_engine.heal_session_quests_on_load(new_session_id)
        except Exception as exc:
            _log.warning("Post-load quest heal failed for session %s: %s", new_session_id, exc)

    return db.get_session(new_session_id)

def list_adventure_saves(user_id: int) -> list[dict]:
    """Returns metadata for all save slots owned by the user's active character."""
    char = db.get_character(user_id)
    if not char:
        return []
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, user_id, character_id, slot_name, scenario, scene_title,
                      narrative_snippet, current_location, saved_at
               FROM adventure_saves
               WHERE character_id = ?
               ORDER BY saved_at DESC""",
            (char["id"],)
        ).fetchall()
        return [dict(r) for r in rows]

def get_adventure_save_metadata(user_id: int, slot_name: str) -> dict | None:
    """Returns metadata for a specific save slot owned by the user's active character."""
    char = db.get_character(user_id)
    if not char:
        return None
    with get_conn() as conn:
        row = conn.execute(
            """SELECT id, user_id, character_id, slot_name, scenario, scene_title,
                      narrative_snippet, current_location, saved_at
               FROM adventure_saves
               WHERE character_id = ? AND LOWER(slot_name) = LOWER(?)""",
            (char["id"], (slot_name or "").strip())
        ).fetchone()
        return dict(row) if row else None

def delete_adventure_save(user_id: int, slot_name: str) -> bool:
    """Permanently deletes a save slot for the user's active character."""
    char = db.get_character(user_id)
    if not char:
        return False
    with get_conn() as conn:
        res = conn.execute(
            "DELETE FROM adventure_saves WHERE character_id = ? AND LOWER(slot_name) = LOWER(?)",
            (char["id"], (slot_name or "").strip())
        )
        return res.rowcount > 0

