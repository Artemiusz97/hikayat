from __future__ import annotations

from contextlib import contextmanager
import inspect
import json
import re
import sqlite3
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..registry import get_purge_specs, get_snapshot_prune_specs
from .module_proxy import unwrap_callable_target
from .connection import (
    ReadUnitOfWork,
    _advance_maintenance_counter,
    _get_independent_conn,
    _resolve_db_path,
    close_all_connections,
    get_conn,
    set_db_path,
)
from .migrations import init_db
from .schema import (
    DEFAULT_SNAPSHOT_KEEP_LAST,
    DISCORD_SNOWFLAKE_MIN,
    WAL_MAINTENANCE_TURN_INTERVAL,
)

def _call_get_character_compat(
    get_char_fn: Callable[..., Any],
    user_id: int,
    *,
    session_id: Any = None,
    settings: Optional[Dict[str, Any]] = None,
) -> Any:
    """Invokes db.get_character (or a monkeypatched test spy) passing only accepted optional kwargs."""
    target = unwrap_callable_target(get_char_fn)
    try:
        sig = inspect.signature(target)
    except (TypeError, ValueError):
        return get_char_fn(user_id)
    params = sig.parameters
    has_varkw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    kwargs: Dict[str, Any] = {}
    if session_id is not None and (
        ("session_id" in params and params["session_id"].kind != inspect.Parameter.POSITIONAL_ONLY)
        or has_varkw
    ):
        kwargs["session_id"] = session_id
    if ("settings" in params and params["settings"].kind != inspect.Parameter.POSITIONAL_ONLY) or has_varkw:
        kwargs["settings"] = settings
    return get_char_fn(user_id, **kwargs)

def preload_prepare_action_bundle(
    session_id: int,
    user_id: int,
    *,
    session: Optional[Dict[str, Any]] = None,
    char: Optional[Dict[str, Any]] = None,
    include_world_events: bool = True,
    include_inventory: bool = True,
) -> Dict[str, Any]:
    """Hydrates session, character, settings, world_events_snapshot, and inventory in one ReadUnitOfWork."""
    db_mod = __import__("db")
    with ReadUnitOfWork():
        eff_sess = session
        if eff_sess is None:
            sess_row = db_mod.get_session(session_id)
            eff_sess = dict(sess_row) if sess_row else None
        settings = db_mod.get_settings(user_id) or {}
        eff_char = char
        if eff_char is None:
            eff_sid = session_id or (eff_sess.get("id") if isinstance(eff_sess, dict) else None)
            char_row = _call_get_character_compat(
                db_mod.get_character,
                user_id,
                session_id=eff_sid,
                settings=settings,
            )
            eff_char = dict(char_row) if char_row else None
        else:
            eff_char = dict(eff_char)
        we_snap: Any = None
        if include_world_events and isinstance(eff_sess, dict) and eff_sess.get("id") and "_world_events_snapshot" not in eff_sess:
            try:
                we_snap = db_mod.get_world_events_snapshot(int(eff_sess["id"]))
            except Exception:
                we_snap = {}
        inv = (
            db_mod.get_inventory(user_id, char=eff_char)
            if isinstance(eff_char, dict) and eff_char.get("id") is not None
            else []
        ) if include_inventory else None
    return {
        "session": eff_sess,
        "char": eff_char,
        "settings": settings,
        "inventory": inv,
        "world_events_snapshot": we_snap,
    }

def preload_turn_party_bundle(
    session_id: int,
) -> Tuple[Optional[Dict[str, Any]], List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]]:
    """Hydrates session and batch-loaded party (character, inventory) pairs in one ReadUnitOfWork."""
    db_mod = __import__("db")
    with ReadUnitOfWork():
        session = db_mod.get_session(session_id)
        if not session:
            return None, []
        members = list(db_mod.get_session_members(session_id) or [])
        if not members:
            return session, []
        party_chars = list(db_mod.get_session_characters(session_id) or [])
        char_by_uid: Dict[int, Dict[str, Any]] = {}
        for pc in party_chars:
            if isinstance(pc, dict) and pc.get("user_id") is not None:
                char_by_uid[int(pc["user_id"])] = dict(pc)
        for uid in members:
            if int(uid) not in char_by_uid:
                mc = db_mod.get_character(uid)
                if mc:
                    char_by_uid[int(uid)] = dict(mc)
        inv_by_cid = (
            db_mod.get_inventories_for_characters(list(char_by_uid.values()))
            if char_by_uid
            else {}
        )
        party: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]] = []
        for uid in members:
            c_dict = char_by_uid.get(int(uid))
            if not c_dict:
                continue
            cid = c_dict.get("id")
            if cid is not None and int(cid) in inv_by_cid:
                inv = inv_by_cid[int(cid)]
            else:
                inv = db_mod.get_inventory(uid, char=c_dict)
            party.append((c_dict, list(inv or [])))
        return session, party

def nullify_orphaned_implicated_contacts(conn: sqlite3.Connection, session_id: int | None = None) -> int:
    """Safely nulls out any dangling soft FK references from world_events.implicated_contact_id."""
    try:
        if session_id is not None:
            cur = conn.execute(
                """UPDATE world_events
                   SET implicated_contact_id = NULL
                   WHERE session_id = ?
                     AND implicated_contact_id IS NOT NULL
                     AND implicated_contact_id NOT IN (SELECT id FROM contacts WHERE session_id = ?)""",
                (int(session_id), int(session_id)),
            )
        else:
            cur = conn.execute(
                """UPDATE world_events
                   SET implicated_contact_id = NULL
                   WHERE implicated_contact_id IS NOT NULL
                     AND implicated_contact_id NOT IN (SELECT id FROM contacts)"""
            )
        return cur.rowcount
    except sqlite3.OperationalError:
        return 0

def _delete_session_child_records_only(conn, session_id: int, preserve_members: bool = False):
    """Deletes all child records belonging to a session without deleting the sessions row itself (useful for Turn 0 retry)."""
    try:
        conn.execute("UPDATE contacts SET household_id=NULL WHERE session_id=?", (session_id,))
    except sqlite3.OperationalError:
        pass
    nullify_orphaned_implicated_contacts(conn, session_id)
    try:
        conn.execute("""
            UPDATE user_patron_compendium SET is_currently_contracted = 0
            WHERE (user_id, patron_id) IN (
                SELECT CAST(holder_id AS INTEGER), patron_id
                FROM session_entity_contracts WHERE session_id = ? AND holder_type = 'player'
            )
            AND NOT EXISTS (
                SELECT 1 FROM session_entity_contracts sec
                WHERE sec.session_id != ? AND sec.holder_type = 'player'
                  AND CAST(sec.holder_id AS INTEGER) = user_patron_compendium.user_id
                  AND sec.patron_id = user_patron_compendium.patron_id
                  AND sec.status = 'active'
            )
        """, (session_id, session_id))
        conn.execute("""
            DELETE FROM inventory WHERE is_pact_locked = 1 AND linked_contract_key IN (
                SELECT contract_key FROM session_entity_contracts WHERE session_id = ?
            )
        """, (session_id,))
    except sqlite3.OperationalError:
        pass
    for spec in get_purge_specs(preserve_members=preserve_members):
        try:
            conn.execute(f"DELETE FROM {spec.name} WHERE session_id=?", (session_id,))
        except sqlite3.OperationalError:
            pass

def _delete_session_records(conn, session_id: int):
    """Deletes a session and all its related child records on an existing connection."""
    _delete_session_child_records_only(conn, session_id, preserve_members=False)
    conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))

def prune_session_turn_snapshots(
    conn: sqlite3.Connection,
    session_id: int,
    keep_last: int = DEFAULT_SNAPSHOT_KEEP_LAST,
) -> dict[str, int]:
    """Trims turn-indexed snapshot tables to the most recent `keep_last` turns for a session."""
    deleted: dict[str, int] = {}
    if not session_id:
        return deleted
    sid = int(session_id)
    for spec in get_snapshot_prune_specs():
        tcol = spec.snapshot_table_turn_col
        if not tcol:
            continue
        effective_keep = max(2, int(keep_last if keep_last != DEFAULT_SNAPSHOT_KEEP_LAST else spec.snapshot_keep_last))
        try:
            cur = conn.execute(
                f"""DELETE FROM {spec.name}
                    WHERE session_id = ?
                      AND {tcol} NOT IN (
                          SELECT {tcol} FROM {spec.name}
                          WHERE session_id = ?
                          ORDER BY {tcol} DESC
                          LIMIT ?
                      )""",
                (sid, sid, effective_keep),
            )
            deleted[spec.name] = int(cur.rowcount or 0)
        except sqlite3.OperationalError:
            deleted[spec.name] = 0
    return deleted

def maybe_run_wal_maintenance(
    conn: sqlite3.Connection | None = None,
    *,
    force: bool = False,
) -> bool:
    """Periodically runs PRAGMA optimize and passive WAL checkpointing outside active write transactions."""
    if not _advance_maintenance_counter(WAL_MAINTENANCE_TURN_INTERVAL, force=force):
        return False

    def _run_maint(c: sqlite3.Connection) -> None:
        try:
            c.execute("PRAGMA optimize")
        except sqlite3.Error:
            pass
        try:
            c.execute("PRAGMA wal_checkpoint(PASSIVE)")
        except sqlite3.Error:
            pass

    if conn is not None:
        _run_maint(conn)
    else:
        with _get_independent_conn() as c:
            _run_maint(c)
    return True

def vacuum_database() -> None:
    """Reclaims unused disk space by rebuilding the database file."""
    with get_conn() as conn:
        try:
            conn.execute("PRAGMA optimize")
        except sqlite3.Error:
            pass
        conn.execute("VACUUM")

def _to_str(val, default: str = "") -> str:
    if val is None:
        return default
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        if any("tier" in str(k).lower() for k in val.keys()):
            try:
                from mechanics.world.locations.hierarchy import parse_structured_location_dict, format_tiered_location_string
                parsed = parse_structured_location_dict(val)
                if parsed:
                    return format_tiered_location_string(*parsed)
            except Exception:
                pass
        return str(val.get("name") or val.get("title") or val.get("location") or val.get("text") or json.dumps(val))
    if isinstance(val, (list, tuple)):
        return json.dumps(val)
    return str(val)

def _json_dataclass_default(obj):
    import dataclasses
    if hasattr(obj, "model_dump") and not isinstance(obj, type):
        return obj.model_dump()
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    return str(obj)

_JS_DECL_RE = re.compile(r"\b(?:const|let|var)\s+[A-Za-z_$][A-Za-z0-9_$]*\s*=")

def _is_suspicious_entity_text(text: str) -> bool:
    if not text or len(text) > 80:
        return True
    t_lower = text.lower()
    suspicious = ("return result", "function(", "function ", "javascript", "this.", "=>", "};", "});", "//", "/*", ")),-1")
    if any(s in t_lower for s in suspicious):
        return True
    return bool(_JS_DECL_RE.search(t_lower))

def _safe_int_db(val, default=None) -> int | None:
    if val is None:
        return default
    if isinstance(val, int) and not isinstance(val, bool):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        cleaned = val.strip().lstrip("+")
        try:
            return int(cleaned)
        except (ValueError, TypeError):
            pass
    return default

def _sanitize_npcs_list(session_id: int, npcs: list) -> list:
    """Ensure any NPC in current_npcs has a proper character name instead of a generic role title,
    and filter out malformed or code-injected artifacts. Deduplicates by name (case-insensitive),
    merging stat data from later occurrences into the first so no HP/status info is lost."""
    if not isinstance(npcs, list):
        return []
    import namegen
    clean_list = []
    fac_map = {}
    try:
        with get_conn() as conn:
            fac_rows = conn.execute("SELECT leadership_roster_json FROM factions WHERE session_id=?", (session_id,)).fetchall()
            for fr in fac_rows:
                r_list = json.loads(fr["leadership_roster_json"] or "[]")
                for r in r_list:
                    if r.get("title") and r.get("name"):
                        fac_map[r["title"].lower()] = r["name"]
    except Exception:
        pass

    scen = "fantasy"
    try:
        with get_conn() as conn:
            s_row = conn.execute("SELECT scenario FROM sessions WHERE id=?", (session_id,)).fetchone()
            if s_row and s_row["scenario"]:
                scen = s_row["scenario"]
    except Exception:
        pass

    for npc in npcs:
        if isinstance(npc, dict):
            raw_name = str(npc.get("name", "")).strip()
            if not raw_name or _is_suspicious_entity_text(raw_name):
                continue
            if npc.get("is_summon"):
                proper_name = raw_name[:60]
                role_val = str(npc.get("role") or "Construct")[:60]
            elif namegen.is_generic_role_name(raw_name) or not namegen.is_valid_entity_name(raw_name):
                matched = fac_map.get(raw_name.lower())
                proper_name = matched or namegen.generate_person_name(scen)
                role_val = str(npc.get("role") or raw_name)[:60]
            else:
                proper_name = raw_name[:60]
                role_val = str(npc.get("role", ""))[:60]

            clean_entry = {
                "name": proper_name,
                "role": role_val,
                "level": _safe_int_db(npc.get("level")),
                "hp": _safe_int_db(npc.get("hp")),
                "max_hp": _safe_int_db(npc.get("max_hp")),
                "mp": _safe_int_db(npc.get("mp")),
                "max_mp": _safe_int_db(npc.get("max_mp")),
                "status_effects": [str(s.get("name", s)) if isinstance(s, dict) else str(s) for s in (npc.get("status_effects") or []) if s and not _is_suspicious_entity_text(str(s))]
            }
            if npc.get("temp_hp") is not None:
                clean_entry["temp_hp"] = _safe_int_db(npc.get("temp_hp"), 0)
            if npc.get("is_summon"):
                clean_entry["is_summon"] = True
                clean_entry["in_party"] = bool(npc.get("in_party", True))
                clean_entry["hostile"] = bool(npc.get("hostile", False))
                if npc.get("is_autonomous_construct"):
                    clean_entry["is_autonomous_construct"] = True
                if npc.get("owner_user_id") is not None:
                    clean_entry["owner_user_id"] = _safe_int_db(npc.get("owner_user_id"), 0)
                if npc.get("summoner_key") is not None:
                    clean_entry["summoner_key"] = str(npc["summoner_key"]).strip()[:60]
                if npc.get("summoner_name"):
                    clean_entry["summoner_name"] = str(npc["summoner_name"]).strip()[:60]
                if npc.get("atk") is not None:
                    clean_entry["atk"] = _safe_int_db(npc.get("atk"), 10)
                if npc.get("taunt_weight") is not None:
                    try:
                        clean_entry["taunt_weight"] = float(npc["taunt_weight"])
                    except (TypeError, ValueError):
                        pass
                if isinstance(npc.get("queued_windup"), dict):
                    clean_entry["queued_windup"] = dict(npc["queued_windup"])
                if isinstance(npc.get("queued_construct_action"), dict):
                    clean_entry["queued_construct_action"] = dict(npc["queued_construct_action"])
            if npc.get("mood"):
                clean_entry["mood"] = str(npc["mood"]).strip()[:40]
            if isinstance(npc.get("micro_blocking"), dict):
                clean_entry["micro_blocking"] = dict(npc["micro_blocking"])
            for k in (
                "composure_state", "stage_role", "attention_ring", "gender", "race", "age_group",
                "club", "grade", "clique", "faction", "activity", "public_role",
                "attribute", "combat_archetype", "ability_medium", "anomalous_npc_tag",
                "npc_type", "social_role_type", "sapience", "temperament",
                "quest_id", "incursion_id", "disposition",
                "activity_key", "activity_id", "activity_tag", "activity_mode",
                "secondary_tag", "npc_id", "person_key",
                "paired_with", "paired_with_name", "spotted_fact_key", "epistemic_tag",
            ):
                if npc.get(k):
                    clean_entry[k] = str(npc[k]).strip()[:80]
            for bool_k in (
                "is_anomalous_entity", "is_anomalous", "anomalous", "is_disguised", "uncanny_presence",
                "non_hostile_anomaly", "talkable", "pattern_observable", "dossier_revealed",
                "activity_is_telltale", "telltale_revealed",
            ):
                if bool_k in npc and npc.get(bool_k) is not None:
                    clean_entry[bool_k] = bool(npc.get(bool_k))
            bi = npc.get("basic_info")
            if isinstance(bi, dict):
                if not clean_entry.get("anomalous_npc_tag") and bi.get("anomalous_npc_tag"):
                    clean_entry["anomalous_npc_tag"] = str(bi["anomalous_npc_tag"]).strip()[:80]
                if not clean_entry.get("is_anomalous_entity") and (
                    bi.get("is_anomalous_entity") or bi.get("is_anomalous") or bi.get("anomalous")
                ):
                    clean_entry["is_anomalous_entity"] = True
            if npc.get("visible_tell_text"):
                clean_entry["visible_tell_text"] = str(npc["visible_tell_text"]).strip()[:200]
            if npc.get("focus_dc_mod") is not None:
                clean_entry["focus_dc_mod"] = _safe_int_db(npc.get("focus_dc_mod"), 0)
            if isinstance(npc.get("join_activity_seed"), dict) and npc["join_activity_seed"]:
                clean_entry["join_activity_seed"] = dict(npc["join_activity_seed"])
            raw_pose_tags = npc.get("sdxl_pose_tags")
            if isinstance(raw_pose_tags, list):
                pose_str = ", ".join(str(x).strip() for x in raw_pose_tags if str(x or "").strip())
                if pose_str:
                    clean_entry["sdxl_pose_tags"] = pose_str[:200]
            elif isinstance(raw_pose_tags, str) and raw_pose_tags.strip():
                clean_entry["sdxl_pose_tags"] = raw_pose_tags.strip()[:200]
            if npc.get("sub_obj_id") is not None:
                clean_entry["sub_obj_id"] = _safe_int_db(npc.get("sub_obj_id"))
            if npc.get("description"):
                clean_entry["description"] = str(npc["description"]).strip()[:300]
            if isinstance(npc.get("appearance"), dict) and npc["appearance"]:
                clean_entry["appearance"] = dict(npc["appearance"])
            if npc.get("composure_ttl") is not None:
                clean_entry["composure_ttl"] = _safe_int_db(npc.get("composure_ttl"), 0)
            clean_list.append(clean_entry)
        elif isinstance(npc, str):
            raw_str = str(npc).strip()
            if not raw_str or _is_suspicious_entity_text(raw_str):
                continue
            if namegen.is_generic_role_name(raw_str) or not namegen.is_valid_entity_name(raw_str):
                matched = fac_map.get(raw_str.lower())
                proper_name = matched or namegen.generate_person_name(scen)
                clean_list.append({"name": proper_name, "role": raw_str[:60]})
            else:
                clean_list.append({"name": raw_str[:60], "role": ""})

    # Deduplicate by name (case-insensitive), preserving order.
    # If a later entry has hp/status data that the first lacks, merge it in.
    seen: dict[str, int] = {}  # name_lower -> index in deduped
    deduped: list[dict] = []
    for entry in clean_list:
        key = entry["name"].lower()
        if key in seen:
            existing = deduped[seen[key]]
            # Merge: prefer non-None values from the later entry for stat fields
            for field in (
                "level", "hp", "max_hp", "mp", "max_mp", "temp_hp", "mood", "micro_blocking",
                "composure_state", "composure_ttl", "stage_role", "attention_ring",
                "gender", "race", "age_group", "club", "grade", "clique", "faction", "activity",
                "public_role", "description", "appearance", "is_summon", "is_autonomous_construct", "in_party",
                "owner_user_id", "summoner_key", "summoner_name", "atk", "taunt_weight",
                "queued_windup", "queued_construct_action",
                "attribute", "combat_archetype", "ability_medium", "anomalous_npc_tag",
                "npc_type", "social_role_type", "sapience", "temperament",
                "quest_id", "sub_obj_id", "incursion_id", "disposition",
                "is_anomalous_entity", "is_anomalous", "anomalous", "is_disguised", "uncanny_presence",
                "non_hostile_anomaly", "talkable", "pattern_observable", "dossier_revealed",
                "activity_key", "activity_id", "activity_tag", "activity_mode",
                "secondary_tag", "npc_id", "person_key",
                "activity_is_telltale", "telltale_revealed", "visible_tell_text",
                "paired_with", "paired_with_name",
                "join_activity_seed", "focus_dc_mod", "sdxl_pose_tags",
                "spotted_fact_key", "epistemic_tag",
            ):
                if existing.get(field) in (None, "") and entry.get(field) not in (None, ""):
                    existing[field] = entry[field]

            # Merge status_effects: union without duplicates (handles dict or str)
            existing_se_names = {
                (x["name"].lower() if isinstance(x, dict) else str(x).split("[")[0].strip().lower())
                for x in (existing.get("status_effects") or [])
                if x
            }
            for se in (entry.get("status_effects") or []):
                if not se:
                    continue
                se_name = se["name"].lower() if isinstance(se, dict) else str(se).split("[")[0].strip().lower()
                if se_name not in existing_se_names:
                    existing.setdefault("status_effects", []).append(se)
                    existing_se_names.add(se_name)
        else:
            seen[key] = len(deduped)
            deduped.append(entry)
    return deduped

def is_discord_snowflake(user_id: Any) -> bool:
    """Returns True if the ID falls in the 64-bit Discord snowflake range (17-19 digits)."""
    try:
        val = int(str(user_id).strip())
        return val >= DISCORD_SNOWFLAKE_MIN
    except (ValueError, TypeError):
        return False

def _find_anomalous_agent_entry(
    conn: sqlite3.Connection,
    session_id: int,
    name_low: str,
    npc_slug: str,
) -> dict[str, Any] | None:
    """Looks up an anomalous special-agent entry from `sessions.extra_json['anomalous_agent_roster']`."""
    if not session_id or (not name_low and not npc_slug):
        return None
    s_row = conn.execute("SELECT extra_json FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not s_row or not s_row["extra_json"]:
        return None
    try:
        extra_data = json.loads(s_row["extra_json"]) if isinstance(s_row["extra_json"], str) else s_row["extra_json"]
    except Exception:
        return None
    if not isinstance(extra_data, dict):
        return None
    raw_ar = extra_data.get("anomalous_agent_roster")
    if not isinstance(raw_ar, list):
        return None
    for ar in raw_ar:
        if not isinstance(ar, dict):
            continue
        ar_name = str(ar.get("name") or "").strip().lower()
        ar_nid = str(ar.get("npc_id") or "").strip().lower()
        if (name_low and (ar_name == name_low or ar_nid == name_low)) or (
            npc_slug and (ar_nid == npc_slug or ar_name == npc_slug)
        ):
            return ar
    return None

def create_database_snapshot(tag: str = "auto", max_backups: int = 5, custom_dir: str = "backups") -> str:
    """Creates a non-blocking SQLite online backup using SQLite's backup API.
    Maintains a rolling window of the last `max_backups` snapshot files.
    """
    import os

    if not os.path.isabs(custom_dir):
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        custom_dir = os.path.join(project_root, custom_dir)

    os.makedirs(custom_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_filename = f"hikayat_{tag}_{timestamp}.db"
    backup_path = os.path.join(custom_dir, backup_filename)

    with get_conn() as src:
        try:
            src.execute("PRAGMA optimize")
        except sqlite3.Error:
            pass
        dest = sqlite3.connect(backup_path)
        try:
            src.backup(dest)
        finally:
            dest.close()

    # Rolling retention: purge oldest snapshots if exceeding max_backups
    try:
        existing = [
            os.path.join(custom_dir, f)
            for f in os.listdir(custom_dir)
            if f.startswith("hikayat_") and f.endswith(".db")
        ]
        existing.sort(key=lambda p: os.path.getmtime(p))
        if len(existing) > max_backups:
            to_remove = existing[: len(existing) - max_backups]
            for old_path in to_remove:
                for ext in ["", "-wal", "-shm", "-journal"]:
                    try:
                        p = old_path + ext if ext else old_path
                        if os.path.exists(p):
                            os.remove(p)
                    except OSError:
                        pass
    except Exception:
        pass

    return backup_path

_ISOLATED_PREV_DB_PATHS: dict[str, str] = {}

def isolate_simulation_db(explicit_path: str | None = None, prefix: str = "hikayat_sim_") -> tuple[str, bool]:
    """Switches the active database to an isolated database for simulation/testing.
    Returns:
        (db_path, is_temporary)
    """
    import tempfile

    prev_path = _resolve_db_path()
    if explicit_path:
        target_path = explicit_path
        is_temp = False
    else:
        tf = tempfile.NamedTemporaryFile(prefix=prefix, suffix=".db", delete=False)
        target_path = tf.name
        tf.close()
        is_temp = True

    if is_temp and prev_path and prev_path != target_path:
        _ISOLATED_PREV_DB_PATHS[target_path] = prev_path

    set_db_path(target_path)
    init_db()
    return target_path, is_temp

def cleanup_simulation_db(target_path: str, keep: bool = False, is_temp: bool = True):
    """Safely closes connections and cleans up temporary simulation database files on disk."""
    import os
    import gc

    prev_path = _ISOLATED_PREV_DB_PATHS.pop(target_path, None)
    active_path = _resolve_db_path()
    if is_temp and not keep and prev_path and active_path == target_path:
        set_db_path(prev_path)
    else:
        close_all_connections()
    gc.collect()
    if is_temp and not keep:
        for ext in ["", "-wal", "-shm", "-journal"]:
            f_path = target_path + ext if ext else target_path
            if os.path.exists(f_path):
                for _ in range(5):
                    try:
                        os.unlink(f_path)
                        break
                    except (PermissionError, OSError):
                        time.sleep(0.05)

@contextmanager
def use_temporary_db(custom_path: str | None = None, keep_on_exit: bool = False, prefix: str = "hikayat_sim_"):
    """Context manager for running tests or simulations against an isolated SQLite database."""
    old_path = _resolve_db_path()
    target_path, is_temp = isolate_simulation_db(explicit_path=custom_path, prefix=prefix)
    try:
        yield target_path
    finally:
        set_db_path(old_path)
        cleanup_simulation_db(target_path, keep=keep_on_exit, is_temp=is_temp)
