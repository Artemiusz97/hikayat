"""Quest dossier mutations, state-event rebasing, and turn-rollback handlers."""
from __future__ import annotations

import copy
import json
import re
import sqlite3
import time
from typing import Any, Optional

from ..core import get_conn
from .profiles import (
    _deserialize_json_field,
    _enrich_dossier_dict,
    _enrich_spine_dict,
    _json_str,
    get_effective_session_turn,
    get_quest_dossier,
    normalize_clue_graph_nodes,
)

_TRACKED_DOSSIER_STATE_FIELDS = (
    "alert_level",
    "rescue_shield_used",
    "engaged_flag",
    "burned_approaches",
    "leads_graph",
    "clue_graph",
    "climax_spec",
    "twist_spec",
    "tangible_item",
    "outcome_tier",
)


def _merge_dedup_state_event(
    events: list[dict[str, Any]],
    turn: int,
    kind: str,
    prev: Any,
    next_: Any,
) -> list[dict[str, Any]]:
    """Insert or coalesce a `(turn, kind)` event, keeping initial `prev` and dropping no-ops."""
    t_int = int(turn)
    k_str = str(kind)
    out = [dict(e) for e in (events or []) if isinstance(e, dict)]
    for idx in range(len(out) - 1, -1, -1):
        ev = out[idx]
        if int(ev.get("turn", -1)) == t_int and str(ev.get("kind") or "") == k_str:
            orig_prev = ev.get("prev")
            if orig_prev == next_:
                del out[idx]
            else:
                out[idx] = {
                    "turn": t_int,
                    "kind": k_str,
                    "prev": orig_prev,
                    "next": copy.deepcopy(next_),
                }
            return out
    if prev != next_:
        out.append(
            {
                "turn": t_int,
                "kind": k_str,
                "prev": copy.deepcopy(prev),
                "next": copy.deepcopy(next_),
            }
        )
    return out


def _rebase_climax_snapshot(snap: Any, new_climax: Any) -> Any:
    if not isinstance(snap, dict) or not isinstance(new_climax, dict):
        return snap
    out = copy.deepcopy(snap)
    for top_key in ("main_objective_text", "title", "objective", "masked_climax_teaser"):
        if new_climax.get(top_key):
            out[top_key] = new_climax[top_key]
    if isinstance(new_climax.get("earned_clearance_locations"), list):
        existing_cl = [str(x) for x in (out.get("earned_clearance_locations") or []) if x]
        for loc_c in new_climax["earned_clearance_locations"]:
            if loc_c and str(loc_c) not in existing_cl:
                existing_cl.append(str(loc_c))
        out["earned_clearance_locations"] = existing_cl
    new_stages = {
        int(s.get("stage_index", idx + 1)): s
        for idx, s in enumerate(new_climax.get("main_stages") or [])
        if isinstance(s, dict)
    }
    snap_stages = out.get("main_stages")
    if isinstance(snap_stages, list):
        for idx, st in enumerate(snap_stages):
            if not isinstance(st, dict):
                continue
            s_idx = int(st.get("stage_index", idx + 1))
            src_st = new_stages.get(s_idx)
            if not src_st or st.get("completed") or str(st.get("status") or "").lower() == "completed":
                continue
            for field in (
                "stage_label",
                "label",
                "beat_contract",
                "target_location",
                "target_npc",
                "key_clue",
                "clue_sources",
            ):
                if field in src_st and src_st[field] is not None:
                    st[field] = copy.deepcopy(src_st[field])
    return out


def _rebase_clue_graph_snapshot(snap: Any, new_cg: Any) -> Any:
    if not isinstance(snap, list) or not isinstance(new_cg, list):
        return snap
    out: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for idx, raw in enumerate(new_cg):
        if isinstance(raw, dict):
            ck = str(raw.get("clue_key") or raw.get("clue_id") or idx)
            by_key[ck] = raw
    seen: set[str] = set()
    for idx, raw in enumerate(snap):
        if not isinstance(raw, dict):
            continue
        node = copy.deepcopy(raw)
        ck = str(node.get("clue_key") or node.get("clue_id") or idx)
        seen.add(ck)
        src = by_key.get(ck)
        if src:
            for field in (
                "title",
                "lead_text",
                "description",
                "location",
                "clue_tier",
                "corroboration_group",
                "stage_index",
                "is_optional",
                "is_red_herring",
            ):
                if field in src and src[field] is not None:
                    node[field] = copy.deepcopy(src[field])
        out.append(node)
    for idx, raw in enumerate(new_cg):
        if not isinstance(raw, dict):
            continue
        ck = str(raw.get("clue_key") or raw.get("clue_id") or idx)
        if ck not in seen:
            add_node = copy.deepcopy(raw)
            add_node["discovered"] = False
            add_node["checked"] = False
            out.append(add_node)
    return out


def _lead_key(raw: dict[str, Any], idx: int) -> str:
    for field in ("lead_id", "hook_id", "id"):
        val = raw.get(field)
        if val is not None and val != "":
            return str(val)
    return str(idx)


def _rebase_leads_graph_snapshot(snap: Any, new_lg: Any) -> Any:
    if not isinstance(snap, list) or not isinstance(new_lg, list):
        return snap
    out: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    for idx, raw in enumerate(new_lg):
        if isinstance(raw, dict):
            lk = _lead_key(raw, idx)
            by_key[lk] = raw
    seen: set[str] = set()
    for idx, raw in enumerate(snap):
        if not isinstance(raw, dict):
            continue
        lead = copy.deepcopy(raw)
        lk = _lead_key(lead, idx)
        seen.add(lk)
        src = by_key.get(lk)
        if (
            src
            and not lead.get("engaged")
            and not lead.get("completed")
            and str(lead.get("status") or "").lower() not in ("completed", "resolved", "failed")
        ):
            for k, v in src.items():
                if k not in ("engaged", "completed", "status", "checked"):
                    lead[k] = copy.deepcopy(v)
        out.append(lead)
    for idx, raw in enumerate(new_lg):
        if not isinstance(raw, dict):
            continue
        lk = _lead_key(raw, idx)
        if lk not in seen:
            out.append(copy.deepcopy(raw))
    return out


def upsert_quest_dossier(
    session_id: int,
    quest_id_or_dict: str | dict = "",
    engine: Optional[str] = None,
    family_tier: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
    *,
    auto_state_events: bool = True,
    turn_number: Optional[int] = None,
    is_baseline_enrichment: bool = False,
    sync_projection: bool = False,
    **kwargs: Any,
) -> dict | None:
    now = time.time()
    src = dict(quest_id_or_dict) if isinstance(quest_id_or_dict, dict) else {}
    qid = (
        (quest_id_or_dict if isinstance(quest_id_or_dict, str) and quest_id_or_dict else None)
        or kwargs.get("quest_id")
        or src.get("quest_id")
        or ""
    )
    if not qid:
        raise ValueError("upsert_quest_dossier requires a non-empty quest_id")

    def _pick(key: str, json_key: str = "", default: Any = None) -> Any:
        for k in (key, json_key):
            if not k:
                continue
            if k in kwargs and kwargs[k] is not None:
                return kwargs[k]
            if k in src and src[k] is not None:
                return src[k]
        return default

    def _run(c: sqlite3.Connection) -> dict | None:
        existing = get_quest_dossier(session_id, str(qid), conn=c) or {}
        eff_engine = str(engine or _pick("engine", "", existing.get("engine") or "MYSTERY_CASE"))
        eff_family = str(family_tier or _pick("family_tier", "", existing.get("family_tier") or "bounty"))
        danger_tier = int(_pick("danger_tier", "", existing.get("danger_tier", 1)) or 1)
        status_stage = str(_pick("status_stage", "", existing.get("status_stage", "pitch")) or "pitch")
        compiled_at_turn = int(_pick("compiled_at_turn", "", existing.get("compiled_at_turn", 0)) or 0)
        pitch_stub = (
            kwargs["pitch_card"]
            if "pitch_card" in kwargs and kwargs["pitch_card"] is not None
            else (
                src["pitch_card"]
                if "pitch_card" in src and src["pitch_card"] is not None
                else _pick("pitch_stub", "pitch_stub_json", existing.get("pitch_stub", {}))
            )
        )
        cast_bindings = _pick("cast_bindings", "cast_bindings_json", existing.get("cast_bindings", {}))
        leads_graph = _pick("leads_graph", "leads_graph_json", existing.get("leads_graph", []))
        clue_graph = _pick("clue_graph", "clue_graph_json", existing.get("clue_graph", []))
        climax_spec = _pick("climax_spec", "climax_spec_json", existing.get("climax_spec", {}))
        twist_spec = _pick("twist_spec", "twist_spec_json", existing.get("twist_spec", {}))
        tangible_item = _pick("tangible_item", "tangible_item_json", existing.get("tangible_item", {}))
        contract_economy = _pick("contract_economy", "contract_economy_json", existing.get("contract_economy", {}))
        turn_in_rules = _pick("turn_in_rules", "turn_in_rules_json", existing.get("turn_in_rules", {}))
        outcomes_matrix = _pick("outcomes_matrix", "outcomes_matrix_json", existing.get("outcomes_matrix", {}))
        alert_level = int(_pick("alert_level", "", existing.get("alert_level", 0)) or 0)
        max_alert = int(_pick("max_alert", "", existing.get("max_alert", 4)) or 4)
        rescue_shield_used = int(bool(_pick("rescue_shield_used", "", existing.get("rescue_shield_used", 0))))
        engaged_flag = int(bool(_pick("engaged_flag", "", existing.get("engaged_flag", 0))))
        burned_approaches = _pick("burned_approaches", "burned_approaches_json", existing.get("burned_approaches", {}))
        state_events_raw = _pick("state_events", "state_events_json", existing.get("state_events", []))
        state_events = (
            list(state_events_raw)
            if isinstance(state_events_raw, (list, tuple))
            else _deserialize_json_field(state_events_raw, [])
        )
        outcome_tier = str(_pick("outcome_tier", "", existing.get("outcome_tier", "")) or "")
        if isinstance(clue_graph, (list, tuple, dict)):
            clue_graph = normalize_clue_graph_nodes(clue_graph, str(qid))

        explicit_state_events = (
            ("state_events" in kwargs and kwargs["state_events"] is not None)
            or ("state_events_json" in kwargs and kwargs["state_events_json"] is not None)
            or ("state_events" in src and src["state_events"] is not None)
            or ("state_events_json" in src and src["state_events_json"] is not None)
        )
        if existing:
            if is_baseline_enrichment:
                rebased_events: list[dict[str, Any]] = []
                for ev in state_events:
                    if not isinstance(ev, dict):
                        continue
                    ev_copy = dict(ev)
                    ek = str(ev_copy.get("kind") or "")
                    if ek == "climax_spec":
                        ev_copy["prev"] = _rebase_climax_snapshot(ev_copy.get("prev"), climax_spec)
                        ev_copy["next"] = _rebase_climax_snapshot(ev_copy.get("next"), climax_spec)
                    elif ek == "clue_graph":
                        ev_copy["prev"] = _rebase_clue_graph_snapshot(ev_copy.get("prev"), clue_graph)
                        ev_copy["next"] = _rebase_clue_graph_snapshot(ev_copy.get("next"), clue_graph)
                    elif ek == "leads_graph":
                        ev_copy["prev"] = _rebase_leads_graph_snapshot(ev_copy.get("prev"), leads_graph)
                        ev_copy["next"] = _rebase_leads_graph_snapshot(ev_copy.get("next"), leads_graph)
                    rebased_events.append(ev_copy)
                state_events = rebased_events
            elif (
                auto_state_events
                and not explicit_state_events
                and str(existing.get("status_stage") or "") == "compiled"
                and status_stage == "compiled"
            ):
                eff_turn = (
                    int(turn_number)
                    if turn_number is not None
                    else int(get_effective_session_turn(session_id, conn=c))
                )
                new_values = {
                    "alert_level": alert_level,
                    "rescue_shield_used": rescue_shield_used,
                    "engaged_flag": engaged_flag,
                    "burned_approaches": burned_approaches,
                    "leads_graph": leads_graph,
                    "clue_graph": clue_graph,
                    "climax_spec": climax_spec,
                    "twist_spec": twist_spec,
                    "tangible_item": tangible_item,
                    "outcome_tier": outcome_tier,
                }
                for fk in _TRACKED_DOSSIER_STATE_FIELDS:
                    old_v = existing.get(fk)
                    new_v = new_values[fk]
                    if fk in ("alert_level", "rescue_shield_used", "engaged_flag"):
                        old_v = int(old_v or 0)
                    elif fk == "outcome_tier":
                        old_v = str(old_v or "")
                    if old_v == new_v:
                        continue
                    if turn_number is None:
                        same_kind = [
                            e for e in state_events if isinstance(e, dict) and str(e.get("kind") or "") == fk
                        ]
                        last_turn_val = same_kind[-1].get("turn") if same_kind else None
                        if (
                            same_kind
                            and int(last_turn_val if last_turn_val is not None else -1) == eff_turn
                            and same_kind[-1].get("prev") == old_v
                            and same_kind[-1].get("next") == new_v
                        ):
                            continue
                    state_events = _merge_dedup_state_event(state_events, eff_turn, fk, old_v, new_v)

        c.execute(
            """INSERT INTO quest_dossiers (
                session_id, quest_id, engine, family_tier, danger_tier, status_stage,
                compiled_at_turn, pitch_stub_json, cast_bindings_json, leads_graph_json,
                clue_graph_json, climax_spec_json, twist_spec_json, tangible_item_json,
                contract_economy_json, turn_in_rules_json, outcomes_matrix_json,
                alert_level, max_alert, rescue_shield_used, engaged_flag,
                burned_approaches_json, state_events_json, outcome_tier, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, quest_id) DO UPDATE SET
                engine = excluded.engine,
                family_tier = excluded.family_tier,
                danger_tier = excluded.danger_tier,
                status_stage = excluded.status_stage,
                compiled_at_turn = excluded.compiled_at_turn,
                pitch_stub_json = excluded.pitch_stub_json,
                cast_bindings_json = excluded.cast_bindings_json,
                leads_graph_json = excluded.leads_graph_json,
                clue_graph_json = excluded.clue_graph_json,
                climax_spec_json = excluded.climax_spec_json,
                twist_spec_json = excluded.twist_spec_json,
                tangible_item_json = excluded.tangible_item_json,
                contract_economy_json = excluded.contract_economy_json,
                turn_in_rules_json = excluded.turn_in_rules_json,
                outcomes_matrix_json = excluded.outcomes_matrix_json,
                alert_level = excluded.alert_level,
                max_alert = excluded.max_alert,
                rescue_shield_used = excluded.rescue_shield_used,
                engaged_flag = excluded.engaged_flag,
                burned_approaches_json = excluded.burned_approaches_json,
                state_events_json = excluded.state_events_json,
                outcome_tier = excluded.outcome_tier,
                updated_at = excluded.updated_at""",
            (
                session_id,
                str(qid),
                eff_engine,
                eff_family,
                danger_tier,
                status_stage,
                compiled_at_turn,
                _json_str(pitch_stub, "{}"),
                _json_str(cast_bindings, "{}"),
                _json_str(leads_graph, "[]"),
                _json_str(clue_graph, "[]"),
                _json_str(climax_spec, "{}"),
                _json_str(twist_spec, "{}"),
                _json_str(tangible_item, "{}"),
                _json_str(contract_economy, "{}"),
                _json_str(turn_in_rules, "{}"),
                _json_str(outcomes_matrix, "{}"),
                alert_level,
                max_alert,
                rescue_shield_used,
                engaged_flag,
                _json_str(burned_approaches, "{}"),
                _json_str(state_events, "[]"),
                outcome_tier,
                now,
                now,
            ),
        )
        saved = get_quest_dossier(session_id, str(qid), conn=c)
        if sync_projection and saved is not None:
            from ..quests import sync_quest_projection_from_dossier

            sync_quest_projection_from_dossier(session_id, str(qid), dossier=saved, conn=c)
        return saved

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def append_dossier_state_event(
    session_id: int,
    quest_id: str,
    turn: int,
    kind: str,
    prev: Any,
    next_: Any,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    now = time.time()

    def _run(c: sqlite3.Connection) -> None:
        row = c.execute(
            "SELECT state_events_json FROM quest_dossiers WHERE session_id = ? AND quest_id = ?",
            (session_id, quest_id),
        ).fetchone()
        if not row:
            return
        events = _deserialize_json_field(row["state_events_json"], [])
        events = _merge_dedup_state_event(events, int(turn), kind, prev, next_)
        c.execute(
            "UPDATE quest_dossiers SET state_events_json = ?, updated_at = ? WHERE session_id = ? AND quest_id = ?",
            (json.dumps(events), now, session_id, quest_id),
        )

    if conn is not None:
        _run(conn)
    else:
        with get_conn() as c:
            _run(c)


def append_spine_state_event(
    session_id: int,
    turn: int,
    kind: str,
    prev: Any,
    next_: Any,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    now = time.time()
    event_entry = {"turn": int(turn), "kind": kind, "prev": prev, "next": next_}

    def _run(c: sqlite3.Connection) -> None:
        row = c.execute(
            "SELECT state_events_json FROM campaign_spines WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return
        events = _deserialize_json_field(row["state_events_json"], [])
        events.append(event_entry)
        c.execute(
            "UPDATE campaign_spines SET state_events_json = ?, updated_at = ? WHERE session_id = ?",
            (json.dumps(events), now, session_id),
        )

    if conn is not None:
        _run(conn)
    else:
        with get_conn() as c:
            _run(c)


def rollback_quest_dossiers_after_turn(
    session_id: int,
    turn_number: int,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, int]:
    t_num = int(turn_number)
    now = time.time()

    def _run(c: sqlite3.Connection) -> dict[str, int]:
        dossiers_rolled = 0
        spines_rolled = 0

        d_rows = c.execute("SELECT * FROM quest_dossiers WHERE session_id = ?", (session_id,)).fetchall()
        for dr in d_rows:
            d = _enrich_dossier_dict(dr)
            if not d:
                continue
            qid = d["quest_id"]
            compiled_turn = int(d.get("compiled_at_turn") or 0)

            fam = str(d.get("family_tier") or "bounty").lower()
            climax_cur = d.get("climax_spec") or {}
            pitch_cur = d.get("pitch_stub") or {}
            chap_num = int(
                climax_cur.get("chapter")
                or pitch_cur.get("chapter")
                or 1
            )
            is_ch1_story = fam == "story" and chap_num <= 1
            spawned_turn = int(pitch_cur.get("spawned_at_turn") or 0)
            is_new_pitch = spawned_turn > t_num and not is_ch1_story

            if is_new_pitch or (compiled_turn > t_num and not is_ch1_story):
                is_non_pitch_family = (
                    fam in ("rumor", "minor", "dispatch", "story", "loyalty", "world_event")
                    or str(qid).upper().startswith(("CLR-", "LIB-"))
                )
                if is_new_pitch or is_non_pitch_family:
                    c.execute("DELETE FROM quest_dossiers WHERE session_id = ? AND quest_id = ?", (session_id, qid))
                    c.execute("DELETE FROM quests WHERE session_id = ? AND quest_id = ?", (session_id, qid))
                    c.execute("DELETE FROM quest_waypoints WHERE session_id = ? AND quest_id = ?", (session_id, qid))
                    c.execute("DELETE FROM session_clues WHERE session_id = ? AND quest_id = ?", (session_id, qid))
                    dossiers_rolled += 1
                else:
                    c.execute(
                        """UPDATE quest_dossiers
                           SET status_stage = 'pitch', compiled_at_turn = 0, alert_level = 0, rescue_shield_used = 0,
                               engaged_flag = 0, cast_bindings_json = '{}', leads_graph_json = '[]',
                               clue_graph_json = '[]', climax_spec_json = '{}', twist_spec_json = '{}',
                               tangible_item_json = '{}', contract_economy_json = '{}', turn_in_rules_json = '{}',
                               outcomes_matrix_json = '{}', burned_approaches_json = '{}', state_events_json = '[]',
                               outcome_tier = '', updated_at = ?
                           WHERE session_id = ? AND quest_id = ?""",
                        (now, session_id, qid),
                    )
                    c.execute(
                        "UPDATE quests SET status = 'Available', dossier_stage = 'pitch', sub_objectives_json = '[]', reward_claimed = 0, strikes = 0, resolution_approach = '', updated_at = ? WHERE session_id = ? AND quest_id = ?",
                        (now, session_id, qid),
                    )
                    c.execute(
                        "DELETE FROM quest_waypoints WHERE session_id = ? AND quest_id = ? AND (stage_index >= 2 OR sub_obj_id > 0)",
                        (session_id, qid),
                    )
                    c.execute(
                        "UPDATE quest_waypoints SET sub_obj_id = NULL, status = 'active', updated_at = ? WHERE session_id = ? AND quest_id = ? AND sub_obj_id = 0",
                        (now, session_id, qid),
                    )
                    dossiers_rolled += 1
            else:
                events = list(d.get("state_events") or [])
                future_events = [e for e in events if int(e.get("turn", 0)) > t_num]
                surviving_events = [e for e in events if int(e.get("turn", 0)) <= t_num]
                if future_events:
                    alert_level = d["alert_level"]
                    rescue_shield = d["rescue_shield_used"]
                    engaged_flag = d["engaged_flag"]
                    burned_approaches = dict(d["burned_approaches"] or {})
                    cast_bindings = dict(d.get("cast_bindings") or {})
                    leads_graph = list(d["leads_graph"] or [])
                    twist_spec = dict(d["twist_spec"] or {})
                    climax_spec = dict(d["climax_spec"] or {})
                    tangible_item = dict(d["tangible_item"] or {})
                    raw_cg_r = d.get("clue_graph")
                    if isinstance(raw_cg_r, dict):
                        cg_items_r = raw_cg_r.get("nodes") if isinstance(raw_cg_r.get("nodes"), (list, tuple)) else list(raw_cg_r.values())
                        clue_graph = [n for n in cg_items_r if isinstance(n, dict)]
                    elif isinstance(raw_cg_r, (list, tuple)):
                        clue_graph = list(raw_cg_r)
                    else:
                        clue_graph = []
                    outcome_tier = str(d.get("outcome_tier") or "")

                    for ev in reversed(future_events):
                        k = str(ev.get("kind") or "")
                        prev_val = ev.get("prev")
                        if k in ("alert_level", "alert_bump"):
                            alert_level = int(prev_val or 0)
                        elif k == "rescue_shield_used":
                            rescue_shield = int(prev_val or 0)
                        elif k == "engaged_flag":
                            engaged_flag = int(prev_val or 0)
                        elif k == "burned_approaches":
                            burned_approaches = dict(prev_val or {})
                        elif k == "cast_bindings":
                            cast_bindings = dict(prev_val or {})
                        elif k == "leads_graph":
                            leads_graph = list(prev_val or [])
                        elif k == "clue_graph":
                            clue_graph = list(prev_val or [])
                        elif k == "twist_spec":
                            twist_spec = dict(prev_val or {})
                        elif k == "climax_spec":
                            climax_spec = dict(prev_val or {})
                        elif k == "tangible_item":
                            tangible_item = dict(prev_val or {})
                        elif k == "outcome_tier":
                            outcome_tier = str(prev_val or "")
                        elif k == "quest_status" and prev_val:
                            prev_st_str = str(prev_val)
                            if prev_st_str != "Completed":
                                c.execute(
                                    "UPDATE quests SET status = ?, reward_claimed = 0, updated_at = ? WHERE session_id = ? AND quest_id = ?",
                                    (prev_st_str, now, session_id, qid),
                                )
                            else:
                                c.execute(
                                    "UPDATE quests SET status = ?, updated_at = ? WHERE session_id = ? AND quest_id = ?",
                                    (prev_st_str, now, session_id, qid),
                                )
                        elif k == "quest_strikes":
                            restored_strikes = int(prev_val or 0)
                            if restored_strikes <= 0:
                                q_prog_r = c.execute(
                                    "SELECT progress FROM quests WHERE session_id = ? AND quest_id = ?",
                                    (session_id, qid),
                                ).fetchone()
                                clean_p_r = (
                                    re.sub(
                                        r"\s*\[⚠️ \d+/\d+ Strikes: Target Alerted\]",
                                        "",
                                        str(q_prog_r["progress"] or ""),
                                    ).strip()
                                    if q_prog_r
                                    else ""
                                )
                                c.execute(
                                    "UPDATE quests SET strikes = ?, progress = ?, updated_at = ? WHERE session_id = ? AND quest_id = ?",
                                    (restored_strikes, clean_p_r, now, session_id, qid),
                                )
                            else:
                                c.execute(
                                    "UPDATE quests SET strikes = ?, updated_at = ? WHERE session_id = ? AND quest_id = ?",
                                    (restored_strikes, now, session_id, qid),
                                )
                        elif k == "resolution_approach":
                            c.execute(
                                "UPDATE quests SET resolution_approach = ?, updated_at = ? WHERE session_id = ? AND quest_id = ?",
                                (str(prev_val or ""), now, session_id, qid),
                            )

                    c.execute(
                        """UPDATE quest_dossiers
                           SET alert_level = ?, rescue_shield_used = ?, engaged_flag = ?,
                               burned_approaches_json = ?, cast_bindings_json = ?, leads_graph_json = ?, twist_spec_json = ?,
                               climax_spec_json = ?, tangible_item_json = ?, clue_graph_json = ?,
                               outcome_tier = ?, state_events_json = ?, updated_at = ?
                           WHERE session_id = ? AND quest_id = ?""",
                        (
                            alert_level,
                            rescue_shield,
                            engaged_flag,
                            json.dumps(burned_approaches),
                            json.dumps(cast_bindings),
                            json.dumps(leads_graph),
                            json.dumps(twist_spec),
                            json.dumps(climax_spec),
                            json.dumps(tangible_item),
                            json.dumps(clue_graph),
                            outcome_tier,
                            json.dumps(surviving_events),
                            now,
                            session_id,
                            qid,
                        ),
                    )
                    from ..quests import sync_quest_projection_from_dossier

                    sync_quest_projection_from_dossier(session_id, qid, conn=c, is_rollback=True)
                    dossiers_rolled += 1

        s_row = c.execute("SELECT * FROM campaign_spines WHERE session_id = ?", (session_id,)).fetchone()
        if s_row:
            s = _enrich_spine_dict(s_row) or {}
            nemeses = list(s.get("nemeses") or [])
            surviving_nemeses = [n for n in nemeses if int(n.get("spawned_at_turn", 0)) <= t_num]

            spine_events = list(s.get("state_events") or [])
            future_s_events = [e for e in spine_events if int(e.get("turn", 0)) > t_num]
            surviving_s_events = [e for e in spine_events if int(e.get("turn", 0)) <= t_num]

            if len(surviving_nemeses) != len(nemeses) or future_s_events:
                climax_status = str(s.get("climax_status") or "pending")
                epilogue_status = str(s.get("epilogue_status") or "pending")
                lieutenants = list(s.get("lieutenants_roster") or [])
                chapters_bp = dict(s.get("chapters_blueprint") or {})
                ending_axes = dict(s.get("ending_axes") or {})
                chronicle_tapestry = dict(s.get("chronicle_tapestry") or {})
                mastermind_profile = dict(s.get("mastermind_profile") or {})
                for ev in reversed(future_s_events):
                    k = str(ev.get("kind") or "")
                    prev_val = ev.get("prev")
                    if k == "climax_status":
                        climax_status = str(prev_val or "pending")
                    elif k == "epilogue_status":
                        epilogue_status = str(prev_val or "pending")
                    elif k == "lieutenants_roster" and isinstance(prev_val, list):
                        lieutenants = list(prev_val)
                    elif k == "chapters_blueprint" and isinstance(prev_val, dict):
                        chapters_bp = dict(prev_val)
                    elif k == "ending_axes" and isinstance(prev_val, dict):
                        ending_axes = dict(prev_val)
                    elif k == "chronicle_tapestry" and isinstance(prev_val, dict):
                        chronicle_tapestry = dict(prev_val)
                    elif k == "mastermind_profile" and isinstance(prev_val, dict):
                        mastermind_profile = dict(prev_val)
                    elif k == "nemeses" and isinstance(prev_val, list):
                        surviving_nemeses = list(prev_val)

                c.execute(
                    """UPDATE campaign_spines
                       SET mastermind_profile_json = ?, nemeses_json = ?, lieutenants_roster_json = ?, chapters_blueprint_json = ?,
                           ending_axes_json = ?, chronicle_tapestry_json = ?,
                           climax_status = ?, epilogue_status = ?, state_events_json = ?, updated_at = ?
                       WHERE session_id = ?""",
                    (
                        json.dumps(mastermind_profile),
                        json.dumps(surviving_nemeses),
                        json.dumps(lieutenants),
                        json.dumps(chapters_bp),
                        json.dumps(ending_axes),
                        json.dumps(chronicle_tapestry),
                        climax_status,
                        epilogue_status,
                        json.dumps(surviving_s_events),
                        now,
                        session_id,
                    ),
                )
                spines_rolled += 1

        return {"dossiers_rolled_back": dossiers_rolled, "spines_rolled_back": spines_rolled}

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)
