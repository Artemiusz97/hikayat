from __future__ import annotations
from typing import Optional, Any
import db
import json
import logging
import time

log = logging.getLogger(__name__)
import sqlite3
import character_data as cd
from .core import *
from .core import _delete_session_records, _to_str, _sanitize_npcs_list, _json_dataclass_default
from .registry import get_purge_specs, get_simple_rollback_specs

def create_session(host_user_id: int, mode: str, capacity: int, verbosity: str,
                    dialogue_mode: str, image_gen_enabled: int | bool = 0, choices_style: str = "dropdown",
                    channel_id: int = 0, scenario: str = "fantasy",
                    result_display: str = "detailed", combat_ui_style: str = "battle_deck",
                    show_percentages: int = 1, language: str = "en",
                    narration_language: str = None,
                    character_id: int = None, slot: int = 1,
                    schema_epoch: int = 2,
                    narrative_pacing: Optional[str] = None,
                    show_enemy_hp: int = 1,
                    show_enemy_intent: int = 1) -> int:
    status = "active" if capacity <= 1 else "waiting"
    eff_narr_lang = narration_language or language or "en"
    eff_pacing = narrative_pacing if narrative_pacing is not None else (
        "concise" if str(verbosity or "").strip().lower() in ("concise", "direct") else "balanced"
    )
    if isinstance(image_gen_enabled, bool):
        eff_img_gen = 1 if image_gen_enabled else 0
    elif isinstance(image_gen_enabled, str):
        s_mode = image_gen_enabled.strip().lower()
        if s_mode in ("2", "on_demand", "ondemand"):
            eff_img_gen = 2
        elif s_mode in ("1", "auto", "true", "yes", "on"):
            eff_img_gen = 1
        else:
            eff_img_gen = 0
    else:
        try:
            parsed_img = int(image_gen_enabled)
        except (TypeError, ValueError):
            parsed_img = 0
        eff_img_gen = parsed_img if parsed_img in (0, 1, 2) else (1 if parsed_img else 0)
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO sessions (mode, capacity, status, turn_order, current_turn_index,
                                      choices_json, history_json, pending_picks_json,
                                      current_location, nearby_enemies_json, current_npcs_json,
                                      verbosity, narrative_pacing, dialogue_mode, image_gen_enabled, choices_style, combat_ui_style,
                                      result_display, scenario, channel_id, host_user_id, created_at, updated_at,
                                      show_percentages, show_enemy_hp, show_enemy_intent,
                                      language, narration_language, character_id, slot, schema_epoch)
               VALUES (?,?,?,?,0,'[]','[]','{}','','[]','[]',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (mode, capacity, status, json.dumps([host_user_id]), verbosity, eff_pacing,
             dialogue_mode, eff_img_gen, choices_style, combat_ui_style,
             result_display, scenario, channel_id, host_user_id, time.time(), time.time(),
             1 if show_percentages else 0, 1 if show_enemy_hp else 0, 1 if show_enemy_intent else 0,
             language or eff_narr_lang, eff_narr_lang, character_id, slot, schema_epoch),
        )
        session_id = cur.lastrowid
        conn.execute("INSERT INTO session_members (session_id, user_id, joined_at) VALUES (?,?,?)",
                      (session_id, host_user_id, time.time()))
        if character_id:
            conn.execute("UPDATE characters SET active_session_id=? WHERE id=?",
                          (session_id, character_id))
        else:
            conn.execute("UPDATE characters SET active_session_id=? WHERE user_id=? AND is_active=1",
                          (session_id, host_user_id))
    return session_id

def join_session(session_id: int, user_id: int) -> dict:
    session = db.get_session(session_id)
    if not session:
        raise ValueError("That session no longer exists.")
    if session["status"] != "waiting":
        raise ValueError("That game is no longer accepting players.")
    members = get_session_members(session_id)
    if user_id in members:
        raise ValueError("You're already in this game.")
    if len(members) >= session["capacity"]:
        raise ValueError("That game is already full.")

    turn_order = list(session["turn_order"])
    turn_order.append(user_id)
    new_status = "active" if len(turn_order) >= session["capacity"] else "waiting"

    with get_conn() as conn:
        conn.execute("INSERT INTO session_members (session_id, user_id, joined_at) VALUES (?,?,?)",
                      (session_id, user_id, time.time()))
        conn.execute("UPDATE sessions SET turn_order=?, status=?, updated_at=? WHERE id=?",
                      (json.dumps(turn_order), new_status, time.time(), session_id))
        conn.execute("UPDATE characters SET active_session_id=? WHERE user_id=? AND is_active=1",
                      (session_id, user_id))
    return db.get_session(session_id)

def get_session(session_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["turn_order"] = json.loads(d["turn_order"] or "[]")
        d["choices"] = json.loads(d.pop("choices_json") or "[]")
        d["history"] = json.loads(d.pop("history_json") or "[]")
        d["pending_picks"] = json.loads(d.pop("pending_picks_json") or "{}")
        enemies_raw = d.pop("nearby_enemies_json", None) or "[]"
        d["nearby_enemies"] = json.loads(enemies_raw if isinstance(enemies_raw, str) else json.dumps(enemies_raw))
        d["current_npcs"] = json.loads(d.pop("current_npcs_json") or "[]")
        d["merchant"] = json.loads(d.pop("merchant_json") or "{}")
        raw_phys_str = d.pop("physical_state_json", None) or "{}"
        try:
            from mechanics.social.physical_state import materialize_session_physical_state
            mat_phys = materialize_session_physical_state(session_id, conn=conn)
            d["physical_state"] = mat_phys if mat_phys else json.loads(raw_phys_str)
        except Exception:
            d["physical_state"] = json.loads(raw_phys_str)
        d["last_turn_snapshot"] = json.loads(d.pop("last_turn_snapshot_json", None) or "{}")
        d["combat_threat_ledger"] = json.loads(d.pop("combat_threat_ledger_json", None) or "{}")
        d["combat_boss_telegraph"] = json.loads(d.pop("combat_boss_telegraph_json", None) or "{}")
        d["party_npcs"] = json.loads(d.pop("party_npcs_json", None) or "[]")
        d["party_recruit_cooldowns"] = json.loads(d.pop("party_recruit_cooldowns_json", None) or "{}")
        d["confession_cooldowns"] = json.loads(d.pop("confession_cooldowns_json", None) or "{}")
        d["phone_social_state"] = json.loads(d.pop("phone_social_state_json", None) or "{}")
        d["scenario"] = d.get("scenario") or "fantasy"
        d["schema_epoch"] = int(d.get("schema_epoch") or 1)
        if not d.get("verbosity"):
            d["verbosity"] = "vivid"
        if not d.get("narrative_pacing"):
            d["narrative_pacing"] = (
                "concise" if str(d.get("verbosity") or "").strip().lower() in ("concise", "direct") else "balanced"
            )
        if not d.get("dialogue_mode"):
            d["dialogue_mode"] = "adaptive"
        d.setdefault("show_enemy_hp", 1)
        d.setdefault("show_enemy_intent", 1)
        d["dialogue_partners"] = []
        raw_dp = d.get("dialogue_partner")
        if raw_dp:
            try:
                parsed_dp = json.loads(raw_dp)
                if isinstance(parsed_dp, list):
                    d["dialogue_partners"] = [str(x) for x in parsed_dp if x]
                elif isinstance(parsed_dp, str):
                    d["dialogue_partners"] = [parsed_dp]
                else:
                    d["dialogue_partners"] = [str(raw_dp)]
            except Exception:
                d["dialogue_partners"] = [str(raw_dp)]
        d["dialogue_partner"] = d["dialogue_partners"][0] if d["dialogue_partners"] else None

        # Enrich with Spatial Graph Node data
        node_id = d.get("current_node_id")
        if node_id:
            from .world import get_world_node, get_node_ancestors
            node = get_world_node(session_id, node_id)
            if node:
                d["current_world_node"] = node
                if not d.get("current_location"):
                    ancestors = get_node_ancestors(session_id, node_id)
                    chain = [a["name"] for a in reversed(ancestors)] + [node["name"]]
                    d["current_location"] = " ➔ ".join(chain)

        if "extra_json" in d:
            extra_raw = d.pop("extra_json", None) or "{}"
            try:
                extra_dict = json.loads(extra_raw if isinstance(extra_raw, str) else json.dumps(extra_raw))
                if isinstance(extra_dict, dict):
                    d.update(extra_dict)
            except Exception:
                pass
        from .dossiers import hydrate_session_anomaly_records
        hydrate_session_anomaly_records(session_id, d, conn=conn)
        if "daily_incursions" in d and "daily_breaches" not in d:
            d["daily_breaches"] = d["daily_incursions"]
        if "stealth_state" not in d or not isinstance(d["stealth_state"], dict):
            from mechanics.stealth import init_stealth_state
            d["stealth_state"] = init_stealth_state(False)
        else:
            from mechanics.stealth.core import _normalize_stealth_state
            _normalize_stealth_state(d["stealth_state"])
        return d


def get_session_members(session_id: int) -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT user_id FROM session_members WHERE session_id=?",
                             (session_id,)).fetchall()
        return [r["user_id"] for r in rows]

def add_session_member(session_id: int, user_id: int):
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO session_members (session_id, user_id, joined_at) VALUES (?,?,?)",
                     (session_id, user_id, time.time()))

def set_session_active(session_id: int, turn_order: list = None):
    kwargs = {"status": "active"}
    if turn_order is not None:
        kwargs["turn_order"] = json.dumps(turn_order, default=str) if isinstance(turn_order, list) else str(turn_order)
    update_session(session_id, **kwargs)


def get_character_sessions(character_id: int) -> list[dict]:
    """Returns all active/waiting sessions belonging to a character, ordered by slot (1..6)."""
    if not character_id:
        return []
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM sessions 
               WHERE character_id = ? AND status IN ('active', 'waiting')
               ORDER BY slot ASC, id DESC""",
            (character_id,)
        ).fetchall()
        return [dict(r) for r in rows]

def get_character_session_in_slot(character_id: int, slot: int) -> dict | None:
    """Returns the active session for a character in a specific slot (1..6)."""
    if not character_id or not slot:
        return None
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM sessions 
               WHERE character_id = ? AND slot = ? AND status IN ('active', 'waiting')
               ORDER BY id DESC LIMIT 1""",
            (character_id, slot)
        ).fetchone()
        return dict(row) if row else None

def get_active_session_id_for_user(user_id: int):
    char = db.get_character(user_id)
    if not char:
        return None
    session_id = char.get("active_session_id")
    if session_id:
        session = db.get_session(session_id)
        if session and session.get("status") in ("active", "waiting"):
            return session_id
        # Session is finished or missing -- clear stale reference on active character
        with get_conn() as conn:
            conn.execute("UPDATE characters SET active_session_id=NULL WHERE id=?", (char["id"],))
    return None

def save_session_scene(session_id: int, scene_title: str, narrative: str, choices: list, history: list,
                        location: str = None, nearby_enemies: list = None, current_npcs: list = None,
                        physical_state: dict = None,
                        dialogue_partner: str = "__NOOP__",
                        current_node_id: str = None,
                        focal_point: str = None,
                        scene_image_url: str = None,
                        combat_threat_ledger: dict = None,
                        combat_boss_telegraph: dict = None):
    clean_narrative = _to_str(narrative)
    if clean_narrative:
        from game_engine.keywords import (
            sanitize_internal_tags_and_raw_stats,
            sanitize_meta_objective_leaks,
        )
        clean_narrative = sanitize_meta_objective_leaks(
            sanitize_internal_tags_and_raw_stats(clean_narrative)
        )

    fields = {
        "scene_title": _to_str(scene_title),
        "narrative": clean_narrative,
        "choices_json": json.dumps(choices, default=_json_dataclass_default) if not isinstance(choices, str) else choices,
        "history_json": json.dumps(history, default=_json_dataclass_default) if not isinstance(history, str) else history,
        "scene_image_url": scene_image_url,
        "updated_at": time.time(),
    }

    with UnitOfWork() as conn:
        if current_node_id:
            fields["current_node_id"] = current_node_id
            if location is None:
                from .world import get_world_node, get_node_ancestors
                node = get_world_node(session_id, current_node_id)
                if node:
                    ancestors = get_node_ancestors(session_id, current_node_id)
                    chain = [a["name"] for a in reversed(ancestors)] + [node["name"]]
                    fields["current_location"] = " ➔ ".join(chain)

        if focal_point is not None:
            fields["focal_point"] = _to_str(focal_point)

        if location is not None:
            clean_loc = _to_str(location)
            if isinstance(location, dict) or (clean_loc.startswith("{") and ("tier" in clean_loc.lower() or "zone" in clean_loc.lower())):
                try:
                    from mechanics.world.locations.hierarchy import parse_tiered_location, format_tiered_location_string
                    z, p, s = parse_tiered_location(location if isinstance(location, dict) else clean_loc)
                    clean_loc = format_tiered_location_string(z, p, s)
                except Exception:
                    pass
            fields["current_location"] = clean_loc

        if nearby_enemies is not None:
            json_str = json.dumps(nearby_enemies, default=_json_dataclass_default) if not isinstance(nearby_enemies, str) else nearby_enemies
            fields["nearby_enemies_json"] = json_str
        if current_npcs is not None:
            sanitized_npcs = _sanitize_npcs_list(session_id, current_npcs)
            fields["current_npcs_json"] = json.dumps(sanitized_npcs, default=_json_dataclass_default)
            try:
                enemy_set = set()
                raw_enemies = nearby_enemies if isinstance(nearby_enemies, list) else []
                for en in raw_enemies:
                    en_name = str(en.get("name") if isinstance(en, dict) else en or "").strip().lower()
                    if en_name:
                        enemy_set.add(en_name)
                scene_met_names = []
                for sn in (sanitized_npcs or []):
                    sn_name = str(sn.get("name") if isinstance(sn, dict) else sn or "").strip()
                    if sn_name and sn_name.lower() != "none" and sn_name.lower() not in enemy_set:
                        scene_met_names.append(sn_name)
                ex_row = conn.execute("SELECT extra_json FROM sessions WHERE id=?", (session_id,)).fetchone()
                ex_dict = {}
                if ex_row and ex_row["extra_json"]:
                    try:
                        ex_dict = json.loads(ex_row["extra_json"])
                    except Exception:
                        ex_dict = {}
                is_fresh_opening = isinstance(history, list) and len(history) == 0
                prev_met = [] if is_fresh_opening else list(ex_dict.get("met_npc_names") or [])
                seen_low = {str(m).strip().lower() for m in prev_met if isinstance(m, str) and m.strip()}
                for sm in scene_met_names:
                    if sm.lower() not in seen_low:
                        prev_met.append(sm)
                        seen_low.add(sm.lower())
                if is_fresh_opening or scene_met_names:
                    ex_dict["met_npc_names"] = prev_met
                    fields["extra_json"] = json.dumps(ex_dict, default=str)
            except Exception:
                pass
        is_fresh_opening_scene = isinstance(history, list) and len(history) == 0
        phys_dict_to_sync: dict | None = None
        if physical_state is not None:
            if isinstance(physical_state, dict):
                if "actors" in physical_state:
                    phys_dict_to_sync = physical_state
                scene_meta = {k: v for k, v in physical_state.items() if k != "actors"}
                fields["physical_state_json"] = json.dumps(scene_meta, default=str)
            elif isinstance(physical_state, str):
                try:
                    parsed_ps = json.loads(physical_state)
                    if isinstance(parsed_ps, dict):
                        if "actors" in parsed_ps:
                            phys_dict_to_sync = parsed_ps
                        fields["physical_state_json"] = json.dumps({k: v for k, v in parsed_ps.items() if k != "actors"}, default=str)
                    else:
                        fields["physical_state_json"] = physical_state
                except Exception:
                    fields["physical_state_json"] = physical_state
            else:
                fields["physical_state_json"] = json.dumps(physical_state, default=str)
        if dialogue_partner != "__NOOP__":
            if isinstance(dialogue_partner, list):
                fields["dialogue_partner"] = json.dumps(dialogue_partner, default=str) if dialogue_partner else None
            else:
                fields["dialogue_partner"] = dialogue_partner if dialogue_partner else None

        if combat_threat_ledger is not None:
            fields["combat_threat_ledger_json"] = json.dumps(combat_threat_ledger, default=_json_dataclass_default) if not isinstance(combat_threat_ledger, str) else combat_threat_ledger
        if combat_boss_telegraph is not None:
            fields["combat_boss_telegraph_json"] = json.dumps(combat_boss_telegraph, default=_json_dataclass_default) if not isinstance(combat_boss_telegraph, str) else combat_boss_telegraph

        cols = ", ".join(f"{k}=?" for k in fields)
        if phys_dict_to_sync is not None:
            try:
                import mechanics.social.physical_state as ps
                ps.sync_state_dict_to_db(session_id, phys_dict_to_sync, conn=conn)
            except Exception:
                pass
        conn.execute(f"UPDATE sessions SET {cols} WHERE id=?", (*fields.values(), session_id))
        if is_fresh_opening_scene:
            try:
                from .social import snapshot_session_physical_state_for_turn
                snapshot_session_physical_state_for_turn(session_id, 0, conn=conn)
            except Exception:
                pass

def update_session(session_id: int, **kwargs):
    """Dynamically updates one or more fields on a session record in the database.

    Accepts direct column names (e.g. pending_picks_json, history_json, narrative)
    or friendly aliases (e.g. choices, history, current_npcs, nearby_enemies, location, extra).
    """
    if not kwargs:
        return

    # Handle 'extra' dictionary and stealth_state if supplied
    st_val = kwargs.pop("stealth_state", None)
    extra_update = kwargs.pop("extra", None)
    if st_val is not None:
        if extra_update is None or not isinstance(extra_update, dict):
            extra_update = {}
        extra_update["stealth_state"] = st_val

    column_aliases = {
        "history": "history_json",
        "choices": "choices_json",
        "current_npcs": "current_npcs_json",
        "nearby_enemies": "nearby_enemies_json",
        "location": "current_location",
        "node_id": "current_node_id",
        "focal_point": "focal_point",
        "physical_state": "physical_state_json",
        "party_npcs": "party_npcs_json",
        "last_turn_snapshot": "last_turn_snapshot_json",
        "combat_threat_ledger": "combat_threat_ledger_json",
        "combat_boss_telegraph": "combat_boss_telegraph_json",
    }

    with UnitOfWork() as conn:
        if extra_update and isinstance(extra_update, dict):
            try:
                from .dossiers import SESSION_ANOMALY_KEY_TO_RECORD_TYPE, sync_session_anomaly_records_from_extra
                synced_anom = sync_session_anomaly_records_from_extra(session_id, extra_update, conn=conn)
                row = conn.execute("SELECT extra_json FROM sessions WHERE id=?", (session_id,)).fetchone()
                existing_extra = {}
                if row and row["extra_json"]:
                    try:
                        existing_extra = json.loads(row["extra_json"])
                    except Exception:
                        existing_extra = {}
                existing_extra.update(extra_update)
                if synced_anom:
                    for anom_k in SESSION_ANOMALY_KEY_TO_RECORD_TYPE:
                        existing_extra.pop(anom_k, None)
                # Filter out None values so callers can delete keys by setting them to None
                cleaned_extra = {k: v for k, v in existing_extra.items() if v is not None}
                kwargs["extra_json"] = json.dumps(cleaned_extra, default=str)
            except Exception:
                pass

        fields = {}
        phys_update_to_sync: dict | None = None
        for k, v in kwargs.items():
            col = column_aliases.get(k, k)
            if col == "current_npcs_json" and not isinstance(v, str):
                sanitized = _sanitize_npcs_list(session_id, v)
                v = json.dumps(sanitized, default=str)
            elif col == "physical_state_json":
                if isinstance(v, dict):
                    if "actors" in v:
                        phys_update_to_sync = v
                    v = json.dumps({pk: pv for pk, pv in v.items() if pk != "actors"}, default=_json_dataclass_default)
                elif isinstance(v, str):
                    try:
                        parsed_pv = json.loads(v)
                        if isinstance(parsed_pv, dict):
                            if "actors" in parsed_pv:
                                phys_update_to_sync = parsed_pv
                            v = json.dumps({pk: pv for pk, pv in parsed_pv.items() if pk != "actors"}, default=_json_dataclass_default)
                    except Exception:
                        pass
            elif col.endswith("_json") and not isinstance(v, str):
                v = json.dumps(v, default=_json_dataclass_default)
            elif col in ("scene_title", "narrative", "current_location") and v is not None:
                clean_v = _to_str(v)
                if col == "current_location" and (isinstance(v, dict) or (clean_v.startswith("{") and ("tier" in clean_v.lower() or "zone" in clean_v.lower()))):
                    try:
                        from mechanics.world.locations.hierarchy import parse_tiered_location, format_tiered_location_string
                        z, p, s = parse_tiered_location(v if isinstance(v, dict) else clean_v)
                        clean_v = format_tiered_location_string(z, p, s)
                    except Exception:
                        pass
                v = clean_v
            elif col == "dialogue_partner":
                if isinstance(v, list):
                    v = json.dumps(v, default=str) if v else None
                elif not v:
                    v = None
            fields[col] = v

        fields["updated_at"] = time.time()

        cols = ", ".join(f"{k}=?" for k in fields)
        if phys_update_to_sync is not None:
            try:
                import mechanics.social.physical_state as ps
                ps.sync_state_dict_to_db(session_id, phys_update_to_sync, conn=conn)
            except Exception:
                pass
        try:
            conn.execute(f"UPDATE sessions SET {cols} WHERE id=?", (*fields.values(), session_id))
        except sqlite3.OperationalError as e:
            err_msg = str(e).lower()
            if "no such column: extra_json" in err_msg:
                try:
                    from .core import run_schema_migrations
                    run_schema_migrations(conn)
                    conn.execute(f"UPDATE sessions SET {cols} WHERE id=?", (*fields.values(), session_id))
                except Exception:
                    fields.pop("extra_json", None)
                    if fields:
                        cols2 = ", ".join(f"{k}=?" for k in fields)
                        conn.execute(f"UPDATE sessions SET {cols2} WHERE id=?", (*fields.values(), session_id))
            else:
                raise

def update_session_dialogue_partner(session_id: int, partner: str | list | None):

    if isinstance(partner, list):
        val = json.dumps(partner) if partner else None
    else:
        val = partner if partner else None
    with get_conn() as conn:
        conn.execute("UPDATE sessions SET dialogue_partner=?, updated_at=? WHERE id=?",
                     (val, time.time(), session_id))

def get_turn_snapshot(session_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT last_turn_snapshot_json FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row or not row["last_turn_snapshot_json"]:
            return {}
        try:
            return json.loads(row["last_turn_snapshot_json"])
        except json.JSONDecodeError:
            return {}

def set_turn_snapshot(session_id: int, snapshot: dict):
    update_session(session_id, last_turn_snapshot=snapshot)

def get_session_physical_state(session_id: int) -> dict:
    """Materializes session physical state from normalized actor_physical_states + actor_garments and room metadata."""
    if not session_id:
        return {}
    import mechanics.social.physical_state as ps
    with get_conn() as conn:
        return ps.materialize_session_physical_state(session_id, conn=conn)


def update_session_physical_state(session_id: int, physical_state: dict, sync_tables: bool = True):
    """Persists actor physical state & garments exclusively to normalized tables, storing only scene-level room metadata on sessions."""
    if not session_id:
        return
    import mechanics.social.physical_state as ps
    with get_conn() as conn:
        if isinstance(physical_state, dict):
            if sync_tables:
                ps.sync_state_dict_to_db(session_id, physical_state, conn=conn)
            scene_meta = {k: v for k, v in physical_state.items() if k != "actors"}
            conn.execute(
                "UPDATE sessions SET physical_state_json=?, updated_at=? WHERE id=?",
                (json.dumps(scene_meta), time.time(), session_id),
            )
        else:
            conn.execute(
                "UPDATE sessions SET physical_state_json=?, updated_at=? WHERE id=?",
                ("{}", time.time(), session_id),
            )

def get_actor_physical_state(session_id: int, canonical_key: str) -> Optional[dict]:
    """Returns normalized physical state dict for an actor including garments."""
    import mechanics.social.physical_state as ps
    return ps.get_actor_physical_state(session_id, canonical_key)

def get_all_actor_physical_states(session_id: int) -> list[dict]:
    """Returns all normalized actor physical states for a session."""
    import mechanics.social.physical_state as ps
    return ps.get_all_actor_physical_states(session_id)

def get_actor_garments(session_id: int, actor_key: str) -> list[dict]:
    """Returns garments for a specific actor in a session."""
    import mechanics.social.physical_state as ps
    return ps.get_actor_garments(session_id, actor_key)

def get_session_time(session_id: int) -> tuple[int, int, int]:
    """Returns (current_day, current_minute, consecutive_days_awake)."""
    try:
        with get_conn() as conn:
            row = conn.execute("SELECT current_day, current_minute, consecutive_days_awake FROM sessions WHERE id=?", (session_id,)).fetchone()
            if not row:
                return 1, 480, 0
            c_day = int(row["current_day"]) if row["current_day"] is not None else 1
            c_min = int(row["current_minute"]) if row["current_minute"] is not None else 480
            c_awake = int(row["consecutive_days_awake"]) if row["consecutive_days_awake"] is not None else 0
            return c_day, c_min, c_awake
    except Exception:
        return 1, 480, 0

def update_session_time(session_id: int, current_day: int, current_minute: int, consecutive_days_awake: int = 0):
    try:
        with get_conn() as conn:
            conn.execute("UPDATE sessions SET current_day=?, current_minute=?, consecutive_days_awake=?, updated_at=? WHERE id=?",
                         (int(current_day), int(current_minute), int(consecutive_days_awake), time.time(), session_id))
    except Exception:
        pass

def increment_days_adventured(user_id: int, delta: int = 1):
    try:
        char = db.get_character(user_id)
        if not char:
            return
        with get_conn() as conn:
            conn.execute("UPDATE characters SET days_adventured = COALESCE(days_adventured, 1) + ? WHERE id=?",
                         (delta, char["id"]))
    except Exception:
        pass

def update_session_npcs(session_id: int, npcs: list):
    sanitized_npcs = _sanitize_npcs_list(session_id, npcs)
    with get_conn() as conn:
        conn.execute("UPDATE sessions SET current_npcs_json=?, updated_at=? WHERE id=?",
                     (json.dumps(sanitized_npcs), time.time(), session_id))

def update_session_enemies(session_id: int, enemies: list):
    json_str = json.dumps(enemies) if not isinstance(enemies, str) else enemies
    with get_conn() as conn:
        conn.execute("UPDATE sessions SET nearby_enemies_json=?, updated_at=? WHERE id=?",
                     (json_str, time.time(), session_id))

def get_session_party_npcs(session_id: int, conn: Optional[sqlite3.Connection] = None) -> list[dict]:
    if conn is not None:
        row = conn.execute("SELECT party_npcs_json FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row or not row["party_npcs_json"]:
            return []
        try:
            return json.loads(row["party_npcs_json"])
        except Exception:
            return []
    with get_conn() as conn:
        row = conn.execute("SELECT party_npcs_json FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row or not row["party_npcs_json"]:
            return []
        try:
            return json.loads(row["party_npcs_json"])
        except Exception:
            return []

def set_session_party_npcs(
    session_id: int,
    party_npcs: list[dict],
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    payload = json.dumps(party_npcs or [], default=_json_dataclass_default)
    if conn is not None:
        conn.execute("UPDATE sessions SET party_npcs_json=?, updated_at=? WHERE id=?",
                     (payload, time.time(), session_id))
        return
    with get_conn() as conn:
        conn.execute("UPDATE sessions SET party_npcs_json=?, updated_at=? WHERE id=?",
                     (payload, time.time(), session_id))

def add_session_party_npc(
    session_id: int,
    npc_dict: dict,
    conn: Optional[sqlite3.Connection] = None,
) -> bool:
    """Adds an NPC to party_npcs if total party size (humans + companions) is under 4."""
    party = get_session_party_npcs(session_id, conn=conn)
    sess = db.get_session(session_id)
    human_count = len(sess.get("turn_order", [])) if sess else 1
    if human_count + len(party) >= 4:
        return False
    name_clean = str(npc_dict.get("name", "")).strip().lower()
    if any(str(p.get("name", "")).strip().lower() == name_clean for p in party):
        return False
    party.append(npc_dict)
    set_session_party_npcs(session_id, party, conn=conn)
    return True

def remove_session_party_npc(
    session_id: int,
    npc_name: str,
    conn: Optional[sqlite3.Connection] = None,
) -> dict | None:
    party = get_session_party_npcs(session_id, conn=conn)
    name_clean = str(npc_name).strip().lower()
    removed = None
    new_party = []
    for p in party:
        if str(p.get("name", "")).strip().lower() == name_clean and removed is None:
            removed = p
        else:
            new_party.append(p)
    if removed is not None:
        set_session_party_npcs(session_id, new_party, conn=conn)
    return removed

def get_temporary_companions(session_id: int) -> list[dict]:
    """Returns the list of active temporary hangout/walking companions (max 3)."""
    with get_conn() as conn:
        row = conn.execute("SELECT temporary_companions_json FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row or not row["temporary_companions_json"]:
            return []
        try:
            return json.loads(row["temporary_companions_json"])
        except Exception:
            return []

def set_temporary_companions(session_id: int, companions: list[dict]):
    """Saves the list of temporary hangout/walking companions."""
    with get_conn() as conn:
        conn.execute("UPDATE sessions SET temporary_companions_json=?, updated_at=? WHERE id=?",
                     (json.dumps(companions or []), time.time(), session_id))

def add_temporary_companion(session_id: int, npc_info: dict | str, activity: str = "walking_together") -> bool:
    """Adds an NPC to temporary_companions if under the 3-companion cap."""
    comps = get_temporary_companions(session_id)
    if len(comps) >= 3:
        return False
    if isinstance(npc_info, str):
        npc_name = npc_info.strip()
        comp_obj = {"name": npc_name, "activity": activity, "joined_at": time.time()}
    else:
        npc_name = str(npc_info.get("name", "")).strip()
        comp_obj = dict(npc_info)
        comp_obj.setdefault("activity", activity)
        comp_obj.setdefault("joined_at", time.time())
    if not npc_name:
        return False
    name_clean = npc_name.lower()
    if any(str(c.get("name", "")).strip().lower() == name_clean for c in comps):
        return True
    comps.append(comp_obj)
    set_temporary_companions(session_id, comps)
    return True

def remove_temporary_companion(session_id: int, npc_name: str) -> dict | None:
    """Removes a specific temporary companion by name."""
    comps = get_temporary_companions(session_id)
    name_clean = str(npc_name).strip().lower()
    removed = None
    new_comps = []
    for c in comps:
        if str(c.get("name", "")).strip().lower() == name_clean and removed is None:
            removed = c
        else:
            new_comps.append(c)
    if removed is not None:
        set_temporary_companions(session_id, new_comps)
    return removed

def clear_temporary_companions(session_id: int):
    """Clears all temporary companions (e.g. at end of day, parting ways, or private rendezvous)."""
    set_temporary_companions(session_id, [])

def advance_turn(session_id: int):
    session = db.get_session(session_id)
    if not session or len(session["turn_order"]) <= 1:
        return
    next_index = (session["current_turn_index"] + 1) % len(session["turn_order"])
    with get_conn() as conn:
        conn.execute("UPDATE sessions SET current_turn_index=? WHERE id=?", (next_index, session_id))

def current_turn_user_id(session: dict):
    if not session["turn_order"]:
        return None
    return session["turn_order"][session["current_turn_index"] % len(session["turn_order"])]

def reset_character_for_new_adventure(
    user_id: int,
    new_scenario: str = None,
    regrant_loadout: bool = True,
    scenario: str = None,
):
    """Resets a character's transient adventure state when leaving or starting a new adventure.
    
    Cleared & Regenerated:
      - Old adventure inventory & equipment wiped and regenerated with fresh class starter gear
        matching the new adventure's scenario (or custom tags)
      - Status effects (reset to empty list)
      - HP/MP restored to max
      - Gold reset to STARTING_GOLD
    
    Preserved (unaffected):
      - Level, XP
      - Stats (STR, PER, END, CHA, INT, AGI, LUK)
      - Pending (unspent) stat points
    """
    char = db.get_character(user_id)
    if not char:
        return
    char_id = char["id"]
    max_hp = int(char.get("_base_max_hp") or char["max_hp"])
    max_mp = char["max_mp"]
    scenario = new_scenario or scenario or char.get("scenario", "fantasy")
    char_class = char.get("char_class", "")
    from scenario_data import is_anomalous_incursions_scenario
    is_anom_scen = is_anomalous_incursions_scenario(scenario)

    with get_conn() as conn:
        # Wipe entire inventory (items + equipment, equipped flags are part of these rows)
        conn.execute(
            "DELETE FROM inventory WHERE character_id=? OR (character_id IS NULL AND user_id=?)",
            (char_id, user_id)
        )
        # Reset vitals, gold, status effects, scenario, and unlink stale active session
        if not is_anom_scen:
            conn.execute(
                "UPDATE characters SET hp=?, mp=?, gold=?, status_effects='[]', scenario=?, active_session_id=NULL, attribute=NULL, combat_archetype=NULL, ability_medium=NULL WHERE id=?",
                (max_hp, max_mp, cd.STARTING_GOLD, scenario, char_id)
            )
        else:
            conn.execute(
                "UPDATE characters SET hp=?, mp=?, gold=?, status_effects='[]', scenario=?, active_session_id=NULL WHERE id=?",
                (max_hp, max_mp, cd.STARTING_GOLD, scenario, char_id)
            )

    # Clear transient scenario-specific spell state on reset before re-granting loadout
    try:
        if not is_anom_scen:
            prog = db.get_skill_progress(char)
            old_anom_spells = set(prog.get("innate_spells") or []) | set(prog.get("equipped_granted_spells") or [])
            if "innate_spells" in prog or "equipped_granted_spells" in prog or "empowered_granted_spells" in prog:
                prog.pop("innate_spells", None)
                prog.pop("equipped_granted_spells", None)
                prog.pop("empowered_granted_spells", None)
                db.set_skill_progress(user_id, prog)
            cur_learned = db.get_learned_spells(user_id) or []
            filtered_spells = [
                sp_id for sp_id in cur_learned
                if sp_id not in old_anom_spells and not str(sp_id).startswith(("anom_", "awk_"))
            ]
            if len(filtered_spells) != len(cur_learned):
                db.set_learned_spells(user_id, filtered_spells)
    except Exception:
        pass
    if not regrant_loadout:
        return

    from scenario_data import is_non_combat_scenario, is_school_scenario
    if is_non_combat_scenario(scenario):
        scen_classes = cd.get_class_templates(scenario) or {}
        if char_class not in scen_classes:
            char_class = (
                "Student"
                if is_school_scenario(scenario)
                else (next(iter(scen_classes.keys())) if scen_classes else "Student")
            )

    # Re-grant starting items and starter gear matching the character's class template
    starting_items = cd.get_starting_items(scenario, char_class)
    gear_map = cd.get_starter_gear_by_class(scenario, char_class, gender=char.get("gender", "Male"), race=char.get("race", "Human"))
    db.apply_adventure_loadout(
        user_id=user_id,
        scenario=scenario,
        char_class=char_class,
        class_description=char.get("class_description", ""),
        gear_map=gear_map,
        starting_items=starting_items
    )

def finish_session(session_id: int):
    with UnitOfWork() as conn:
        # Collect all members before we clear their active_session_id
        members = get_session_members(session_id)
        sess = get_session(session_id)
        sess_scenario = sess.get("scenario") if sess else None
        conn.execute("UPDATE sessions SET status='finished', updated_at=? WHERE id=?",
                      (time.time(), session_id))
        conn.execute("UPDATE characters SET active_session_id=NULL WHERE active_session_id=?", (session_id,))
        # Reset each member's transient state so it doesn't bleed into the next adventure
        for uid in members:
            reset_character_for_new_adventure(uid, new_scenario=sess_scenario)

def delete_session(session_id: int):
    """Permanently removes a session and all its associated child records."""
    with get_conn() as conn:
        _delete_session_records(conn, session_id)
        conn.execute("UPDATE characters SET active_session_id=NULL WHERE active_session_id=?", (session_id,))

def prune_orphaned_and_finished_sessions(dry_run: bool = False, include_finished: bool = True) -> dict:
    """Finds and permanently deletes:
    1. Orphaned ghost sessions where no valid character exists in characters table.
    2. Finished sessions (from /adventure leave or runs superseded by new adventures).

    CRITICAL SAFETY GUARANTEE:
    Active sessions belonging to existing characters are NEVER touched, ensuring
    players who return after days or months retain 100% of their progress.
    """
    with get_conn() as conn:
        conditions = []
        if include_finished:
            conditions.append("s.status = 'finished'")

        # Sessions where none of the session_members exist in characters table
        conditions.append("""
            NOT EXISTS (
                SELECT 1 FROM session_members sm
                JOIN characters c ON sm.user_id = c.user_id
                WHERE sm.session_id = s.id
            )
        """)

        # Sessions where capacity=1 or solo, but host_user has no character
        conditions.append("""
            s.host_user_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM characters c WHERE c.user_id = s.host_user_id
            )
        """)

        where_clause = " OR ".join(conditions)
        query = f"SELECT id FROM sessions s WHERE {where_clause}"
        stale_rows = conn.execute(query).fetchall()
        stale_ids = [r["id"] for r in stale_rows]

        counts = {
            "sessions_identified": len(stale_ids),
            "dry_run": dry_run,
            "deleted_by_table": {}
        }

        if not stale_ids:
            return counts

        chunk_size = 500
        for i in range(0, len(stale_ids), chunk_size):
            chunk = stale_ids[i:i + chunk_size]
            placeholders = ",".join("?" * len(chunk))

            for spec in get_purge_specs():
                try:
                    if dry_run:
                        cnt = conn.execute(
                            f"SELECT count(*) FROM {spec.name} WHERE session_id IN ({placeholders})",
                            chunk,
                        ).fetchone()[0]
                        counts["deleted_by_table"][spec.name] = counts["deleted_by_table"].get(spec.name, 0) + cnt
                    else:
                        cur = conn.execute(
                            f"DELETE FROM {spec.name} WHERE session_id IN ({placeholders})",
                            chunk,
                        )
                        counts["deleted_by_table"][spec.name] = counts["deleted_by_table"].get(spec.name, 0) + cur.rowcount
                except sqlite3.OperationalError:
                    if not spec.optional_table:
                        raise

            if dry_run:
                cnt = conn.execute(f"SELECT count(*) FROM sessions WHERE id IN ({placeholders})", chunk).fetchone()[0]
                counts["deleted_by_table"]["sessions"] = counts["deleted_by_table"].get("sessions", 0) + cnt
            else:
                cur = conn.execute(f"DELETE FROM sessions WHERE id IN ({placeholders})", chunk)
                counts["deleted_by_table"]["sessions"] = counts["deleted_by_table"].get("sessions", 0) + cur.rowcount

        # Also purge any child records whose session was already deleted directly
        for spec in get_purge_specs():
            try:
                if dry_run:
                    cnt = conn.execute(
                        f"SELECT count(*) FROM {spec.name} WHERE session_id NOT IN (SELECT id FROM sessions)"
                    ).fetchone()[0]
                    if cnt > 0:
                        counts["deleted_by_table"][spec.name] = counts["deleted_by_table"].get(spec.name, 0) + cnt
                else:
                    cur = conn.execute(
                        f"DELETE FROM {spec.name} WHERE session_id NOT IN (SELECT id FROM sessions)"
                    )
                    if cur.rowcount > 0:
                        counts["deleted_by_table"][spec.name] = counts["deleted_by_table"].get(spec.name, 0) + cur.rowcount
            except sqlite3.OperationalError:
                pass

        return counts


def set_pending_pick(session_id: int, user_id: int, pick: dict):
    session = db.get_session(session_id)
    picks = dict(session["pending_picks"])
    picks[str(user_id)] = pick
    with get_conn() as conn:
        conn.execute("UPDATE sessions SET pending_picks_json=? WHERE id=?",
                      (json.dumps(picks, default=_json_dataclass_default), session_id))

def clear_pending_picks(session_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE sessions SET pending_picks_json='{}' WHERE id=?", (session_id,))


def reset_session_for_opening_retry(session_id: int, user_id: int = 0) -> None:
    """Purges Turn 0 child rows and any previously granted opening starting_prop before regenerating Turn 0."""
    if not session_id:
        return
    from .core import _delete_session_child_records_only
    with UnitOfWork() as conn:
        sess_row = conn.execute(
            "SELECT extra_json, host_user_id, character_id FROM sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        eff_uid = int(user_id or (sess_row["host_user_id"] if sess_row and sess_row["host_user_id"] else 0))
        extra_dict: dict = {}
        if sess_row and sess_row["extra_json"]:
            try:
                extra_dict = json.loads(sess_row["extra_json"]) or {}
            except Exception:
                extra_dict = {}
        prop_name = str(extra_dict.pop("opening_starting_prop_name", "") or "").strip()
        extra_dict.pop("stealth_state", None)
        extra_dict.pop("player_resonance_pips", None)
        extra_dict.pop("telemetry_calibrations_used", None)
        extra_dict.pop("anomaly_field_log", None)
        extra_dict.pop("retired_folklore_ids", None)
        extra_dict.pop("folklore_cooldowns", None)
        extra_dict.pop("contained_anomalies_log", None)
        extra_dict.pop("anomalous_vault_log", None)
        extra_dict.pop("anomalous_vault_requisitions", None)
        extra_dict.pop("daily_incursions", None)
        extra_dict.pop("daily_breaches", None)
        extra_dict.pop("anomalous_faction_state", None)
        extra_dict.pop("anomalous_starting_faction", None)
        extra_dict.pop("anomalous_starting_location", None)
        extra_dict.pop("starter_hook_id", None)
        extra_dict.pop("folklore_villager_roster", None)
        extra_dict.pop("folklore_roster_pc_bucket", None)
        extra_dict.pop("folklore_free_tokens_granted", None)
        extra_dict.pop("leyline_spirit_passage_unlocked", None)
        extra_dict.pop("leyline_unlocked_turn", None)
        extra_dict.pop("leyline_unlock_reason", None)
        extra_dict.pop("prompt_epoch", None)
        if prop_name:
            char_id = sess_row["character_id"] if sess_row and sess_row["character_id"] else None
            if not char_id and eff_uid:
                char_row = conn.execute(
                    "SELECT id FROM characters WHERE user_id=? AND is_active=1 ORDER BY id DESC LIMIT 1",
                    (eff_uid,),
                ).fetchone()
                char_id = char_row["id"] if char_row else None
            if char_id:
                inv_row = conn.execute(
                    "SELECT id FROM inventory WHERE character_id=? AND LOWER(name)=LOWER(?) ORDER BY id DESC LIMIT 1",
                    (char_id, prop_name),
                ).fetchone()
                if inv_row:
                    conn.execute("DELETE FROM inventory WHERE id=?", (inv_row["id"],))

        _delete_session_child_records_only(conn, session_id, preserve_members=True)
        conn.execute(
            """UPDATE sessions
               SET history_json='[]', narrative=NULL, choices_json='[]',
                   last_turn_snapshot_json='{}', merchant_json='{}', party_npcs_json='[]',
                   combat_threat_ledger_json='{}', combat_boss_telegraph_json='{}',
                   current_npcs_json='[]', nearby_enemies_json='[]', dialogue_partner=NULL,
                   physical_state_json='{}', current_location='', current_node_id=NULL, focal_point='',
                   scene_title=NULL, scene_image_url=NULL,
                   temporary_companions_json='[]', phone_social_state_json='{}',
                   current_day=1, current_minute=480,
                   event_pity_counter=0.0, rumor_pity_counter=0.0, minor_event_pity_counter=0.0,
                   player_scandal_cooldown_until_day=0,
                   recent_witness_catches_json='[]', npc_gossip_shared_today_json='{}',
                   campaign_end_goals_json='[]',
                   chapter_digest_json='[]', turn_count=0, last_digested_turn=0,
                   extra_json=?, updated_at=?
               WHERE id=?""",
            (json.dumps(extra_dict), time.time(), session_id),
        )


def rollback_session_normalized_state_after_turn(session_id: int, turn_number: int) -> dict:
    """Atomically rolls back social_ties, intimate_events, commitments_ledger, world_events, quest_dossiers, campaign_spines, npc_memories, and session_digests after turn_number."""
    if not session_id:
        return {
            "ties_rolled_back": 0,
            "intimate_events_deleted": 0,
            "commitments_deleted": 0,
            "world_events_rolled_back": 0,
            "dossiers_rolled_back": 0,
            "spines_rolled_back": 0,
            "npc_memories_deleted": 0,
            "digests_deleted": 0,
            "chronicles_deleted": 0,
            "session_clues_deleted": 0,
            "physical_actors_restored": 0,
            "garments_restored": 0,
            "properties_deleted": 0,
            "spare_keys_pruned": 0,
            "folklore_villages_reverted": 0,
            "leyline_reverted": 0,
            "folklore_hydrations_reverted": 0,
            "folklore_forms_reverted": 0,
            "folklore_tokens_reverted": 0,
            "folklore_companions_pruned": 0,
            "contracts_restored": 0,
            "grudges_restored": 0,
            "pact_gear_pruned": 0,
            "world_roster_rolled_back": 0,
            "epistemic_rolled_back": 0,
        }
    import mechanics.social.relationship_graph as rg
    from mechanics.social.persona.intimacy.ledger import delete_intimate_events_after_turn
    from .world_events import rollback_world_events_after_turn
    from .dossiers import rollback_quest_dossiers_after_turn, rollback_session_anomaly_logs_after_turn
    from .memory import MAX_ROLLING_DIGEST_BULLETS, rebuild_session_digests_fts
    from .social import rollback_actor_physical_state_after_turn
    from .social_pacing import rollback_social_pacing_state_after_turn
    from .properties import rollback_player_properties_after_turn, grant_or_relocate_starter_quarters
    from .contracts import rollback_entity_contracts_after_turn
    from .roster import rollback_world_roster_after_turn
    from .epistemic import rollback_epistemic_state_after_turn

    t_num = int(turn_number)
    restore_quarters_arch: str | None = None
    with UnitOfWork() as conn:
        we_res = rollback_world_events_after_turn(session_id, t_num, conn=conn)
        dos_res = rollback_quest_dossiers_after_turn(session_id, t_num, conn=conn)
        rollback_session_anomaly_logs_after_turn(session_id, t_num, conn=conn)
        ties_cnt = rg.rollback_ties_after_turn(session_id, t_num, conn=conn)
        phys_res = rollback_actor_physical_state_after_turn(session_id, t_num, conn=conn)
        soc_pacing_res = rollback_social_pacing_state_after_turn(session_id, t_num, conn=conn)
        prop_res = rollback_player_properties_after_turn(session_id, t_num, conn=conn)
        pact_res = rollback_entity_contracts_after_turn(session_id, t_num, conn=conn)
        roster_res = rollback_world_roster_after_turn(session_id, t_num, conn=conn)
        ep_res = rollback_epistemic_state_after_turn(session_id, t_num, conn=conn)
        from mechanics.world.locations.folklore_veil import rollback_folklore_veil_state_after_turn
        veil_res = rollback_folklore_veil_state_after_turn(session_id, t_num, conn=conn)
        from mechanics.world.locations import rollback_hidden_club_discoveries_after_turn
        hidden_clubs_reverted = rollback_hidden_club_discoveries_after_turn(session_id, t_num, conn=conn)
        from mechanics.world.anomalous_sites.lifecycle import rollback_anomalous_sites_after_turn
        anomalous_sites_reverted = rollback_anomalous_sites_after_turn(session_id, t_num, conn=conn)
        intimate_cnt = delete_intimate_events_after_turn(session_id, t_num, conn=conn)
        simple_counts: dict[str, int] = {}
        for spec in get_simple_rollback_specs():
            if not spec.rollback_turn_col or not spec.rollback_result_key:
                continue
            cur_simple = conn.execute(
                f"DELETE FROM {spec.name} WHERE session_id = ? AND {spec.rollback_turn_col} > ?",
                (session_id, t_num),
            )
            simple_counts[spec.rollback_result_key] = int(cur_simple.rowcount or 0)

        conn.execute(
            """DELETE FROM inventory
               WHERE is_quest_locked = 1
                 AND linked_quest_id != ''
                 AND linked_quest_id NOT IN (SELECT quest_id FROM quests WHERE session_id = ?)
                 AND (
                     character_id IN (SELECT id FROM characters WHERE active_session_id = ? OR user_id IN (SELECT user_id FROM session_members WHERE session_id = ?))
                     OR user_id IN (SELECT user_id FROM session_members WHERE session_id = ?)
                 )""",
            (session_id, session_id, session_id, session_id),
        )
        conn.execute(
            """UPDATE inventory
               SET is_quest_locked = 0, linked_quest_id = ''
               WHERE is_quest_locked = 1
                 AND linked_quest_id != ''
                 AND (
                     linked_quest_id IN (SELECT quest_id FROM quest_dossiers WHERE session_id = ? AND status_stage = 'pitch')
                     OR linked_quest_id IN (SELECT quest_id FROM quests WHERE session_id = ? AND dossier_stage = 'pitch')
                 )
                 AND (
                     character_id IN (SELECT id FROM characters WHERE active_session_id = ? OR user_id IN (SELECT user_id FROM session_members WHERE session_id = ?))
                     OR user_id IN (SELECT user_id FROM session_members WHERE session_id = ?)
                 )""",
            (session_id, session_id, session_id, session_id, session_id),
        )

        cur_ch = conn.execute(
            "DELETE FROM session_chronicles WHERE session_id = ? AND (turn_end > ? OR (created_turn > 0 AND created_turn > ?))",
            (session_id, t_num, t_num),
        )
        ch_cnt = cur_ch.rowcount

        cur_dg = conn.execute(
            "DELETE FROM session_digests WHERE session_id = ? AND turn_end > ?",
            (session_id, t_num),
        )
        dg_cnt = cur_dg.rowcount

        conn.execute(
            "UPDATE session_digests SET compacted_count = 0, compacted_at_turn = 0, is_compacted = 0 WHERE session_id = ?",
            (session_id,),
        )
        surv_chronicles = conn.execute(
            "SELECT bullet_count, created_turn, turn_end FROM session_chronicles WHERE session_id = ? ORDER BY chapter_number ASC, id ASC",
            (session_id,),
        ).fetchall()
        rem_to_mark = sum(max(0, int(sc["bullet_count"] or 15)) for sc in surv_chronicles)
        last_compacted_turn = max(
            [int(sc["created_turn"] or sc["turn_end"] or 0) for sc in surv_chronicles],
            default=0,
        )
        if rem_to_mark > 0:
            dg_rows = conn.execute(
                "SELECT id, summary_bullets_json FROM session_digests WHERE session_id = ? ORDER BY turn_end ASC, id ASC",
                (session_id,),
            ).fetchall()
            for dr in dg_rows:
                if rem_to_mark <= 0:
                    break
                try:
                    dr_bullets = json.loads(dr["summary_bullets_json"] or "[]")
                except Exception:
                    dr_bullets = []
                if not isinstance(dr_bullets, list) or not dr_bullets:
                    continue
                take = min(rem_to_mark, len(dr_bullets))
                is_comp = 1 if take >= len(dr_bullets) else 0
                conn.execute(
                    "UPDATE session_digests SET compacted_count = ?, compacted_at_turn = ?, is_compacted = ? WHERE id = ?",
                    (take, last_compacted_turn, is_comp, dr["id"]),
                )
                rem_to_mark -= take

        rebuild_session_digests_fts(conn, session_id)

        rem_rows = conn.execute(
            "SELECT summary_bullets_json, compacted_count FROM session_digests WHERE session_id = ? AND is_compacted = 0 ORDER BY turn_end ASC, id ASC",
            (session_id,),
        ).fetchall()
        rem_bullets: list[str] = []
        for rr in rem_rows:
            try:
                b_list = json.loads(rr["summary_bullets_json"] or "[]")
                if isinstance(b_list, list):
                    cc = int(rr["compacted_count"] or 0)
                    for b in b_list[cc:]:
                        if isinstance(b, str) and b.strip():
                            rem_bullets.append(b.strip())
            except Exception:
                pass
        conn.execute(
            """UPDATE sessions
               SET chapter_digest_json = ?,
                   turn_count = MIN(COALESCE(turn_count, 0), ?),
                   last_digested_turn = MIN(COALESCE(last_digested_turn, 0), ?),
                   updated_at = ?
               WHERE id = ?""",
            (json.dumps(rem_bullets[-MAX_ROLLING_DIGEST_BULLETS:]), t_num, t_num, time.time(), session_id),
        )

        # Recompute sessions.current_chapter from surviving active story quest after turn T (Decision D3)
        surv_sq = conn.execute(
            """SELECT q.quest_id, qd.climax_spec_json, qd.pitch_stub_json
               FROM quests q
               LEFT JOIN quest_dossiers qd ON q.session_id = qd.session_id AND q.quest_id = qd.quest_id
               WHERE q.session_id = ? AND (q.is_story_quest = 1 OR LOWER(q.quest_type) IN ('story quest', 'main quest') OR q.quest_id LIKE 'SQ-%')
                 AND q.status = 'Active'
               ORDER BY q.id DESC LIMIT 1""",
            (session_id,),
        ).fetchone()
        rev_ch = None
        if surv_sq:
            try:
                c_spec = json.loads(surv_sq["climax_spec_json"] or "{}")
                if isinstance(c_spec, dict) and c_spec.get("chapter"):
                    rev_ch = int(c_spec["chapter"])
            except Exception:
                pass
            if rev_ch is None:
                try:
                    p_stub = json.loads(surv_sq["pitch_stub_json"] or "{}")
                    if isinstance(p_stub, dict) and p_stub.get("chapter"):
                        rev_ch = int(p_stub["chapter"])
                except Exception:
                    pass
        if rev_ch is not None and rev_ch >= 1:
            conn.execute("UPDATE sessions SET current_chapter = ? WHERE id = ?", (rev_ch, session_id))
        c_rows = conn.execute("SELECT * FROM contacts WHERE session_id = ?", (session_id,)).fetchall()
        for cr in c_rows:
            cd_item = dict(cr)
            try:
                cd_item["relations"] = json.loads(cd_item.get("relations_json") or "{}")
            except Exception:
                cd_item["relations"] = {}
            mat = rg.materialize_relations(session_id, cd_item, conn=conn)
            basic_changed = False
            basic_obj = None
            try:
                basic_raw = cd_item.get("basic_info_json") or "{}"
                basic_obj = json.loads(basic_raw) if isinstance(basic_raw, str) else dict(basic_raw or {})
                if isinstance(basic_obj, dict):
                    pend_req = basic_obj.get("pending_outfit_request")
                    if isinstance(pend_req, dict):
                        if int(pend_req.get("turn_requested") or 0) > t_num:
                            basic_obj.pop("pending_outfit_request", None)
                            basic_changed = True
                        elif str(pend_req.get("status") or "") == "fulfilled" and int(pend_req.get("turn_fulfilled") or 0) > t_num:
                            pend_req["status"] = "deferred_to_venue_or_date"
                            pend_req.pop("turn_fulfilled", None)
                            basic_changed = True
            except Exception:
                basic_changed = False
            if basic_changed and isinstance(basic_obj, dict):
                conn.execute(
                    "UPDATE contacts SET relations_json = ?, basic_info_json = ? WHERE id = ?",
                    (json.dumps(mat), json.dumps(basic_obj), cd_item["id"]),
                )
            else:
                conn.execute("UPDATE contacts SET relations_json = ? WHERE id = ?", (json.dumps(mat), cd_item["id"]))

        snap_row = conn.execute(
            "SELECT last_turn_snapshot_json, extra_json FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        cur_extra: dict[str, Any] = {}
        extra_dirty = False
        try:
            parsed_extra = json.loads((snap_row["extra_json"] if snap_row else None) or "{}")
            if isinstance(parsed_extra, dict):
                cur_extra = parsed_extra
        except Exception:
            cur_extra = {}
        # Clean up stale chapter transition metadata in extra_json if transition happened after turn T
        try:
            if int(cur_extra.get("_last_transition_turn") or -1) > t_num:
                cur_extra.pop("_last_transition_quest_id", None)
                cur_extra.pop("_last_transition_turn", None)
                extra_dirty = True
        except Exception:
            pass

        if snap_row and snap_row["last_turn_snapshot_json"]:
            try:
                snap_obj = json.loads(snap_row["last_turn_snapshot_json"] or "{}")
                pre_t = snap_obj.get("pre_turn") if isinstance(snap_obj, dict) else None
                if isinstance(pre_t, dict):
                    if any(k in pre_t for k in ("event_pity_counter", "rumor_pity_counter", "minor_event_pity_counter")):
                        conn.execute(
                            """UPDATE sessions
                               SET event_pity_counter = COALESCE(?, event_pity_counter),
                                   rumor_pity_counter = COALESCE(?, rumor_pity_counter),
                                   minor_event_pity_counter = COALESCE(?, minor_event_pity_counter),
                                   updated_at = ?
                               WHERE id = ?""",
                            (
                                float(pre_t["event_pity_counter"]) if pre_t.get("event_pity_counter") is not None else None,
                                float(pre_t["rumor_pity_counter"]) if pre_t.get("rumor_pity_counter") is not None else None,
                                float(pre_t["minor_event_pity_counter"]) if pre_t.get("minor_event_pity_counter") is not None else None,
                                time.time(),
                                session_id,
                            ),
                        )
                    if "enemies" in pre_t or "nearby_enemies" in pre_t:
                        pre_enemies = pre_t.get("enemies") if "enemies" in pre_t else pre_t.get("nearby_enemies")
                        if isinstance(pre_enemies, list):
                            conn.execute(
                                "UPDATE sessions SET nearby_enemies_json = ?, updated_at = ? WHERE id = ?",
                                (json.dumps(pre_enemies, default=str), time.time(), session_id),
                            )
                    if "party_npcs" in pre_t and isinstance(pre_t["party_npcs"], list):
                        conn.execute(
                            "UPDATE sessions SET party_npcs_json = ?, updated_at = ? WHERE id = ?",
                            (json.dumps(pre_t["party_npcs"], default=str), time.time(), session_id),
                        )
                    if "combat_threat_ledger" in pre_t or "combat_threat_ledger_json" in pre_t:
                        tl = pre_t.get("combat_threat_ledger") if "combat_threat_ledger" in pre_t else pre_t.get("combat_threat_ledger_json")
                        tl_str = tl if isinstance(tl, str) else json.dumps(tl or {}, default=str)
                        conn.execute(
                            "UPDATE sessions SET combat_threat_ledger_json = ?, updated_at = ? WHERE id = ?",
                            (tl_str, time.time(), session_id),
                        )
                    if "combat_boss_telegraph" in pre_t or "combat_boss_telegraph_json" in pre_t:
                        bt = pre_t.get("combat_boss_telegraph") if "combat_boss_telegraph" in pre_t else pre_t.get("combat_boss_telegraph_json")
                        bt_str = bt if isinstance(bt, str) else json.dumps(bt or {}, default=str)
                        conn.execute(
                            "UPDATE sessions SET combat_boss_telegraph_json = ?, updated_at = ? WHERE id = ?",
                            (bt_str, time.time(), session_id),
                        )
                    if (
                        "player_resonance_pips" in pre_t
                        or "telemetry_calibrations_used" in pre_t
                        or "anomalous_faction_state" in pre_t
                        or ("daily_incursions" in pre_t and pre_t.get("daily_incursions") is not None and int(pre_t.get("pre_turn_count", -1)) == t_num)
                    ):
                        for _tk in ("_last_transition_turn", "_last_transition_quest_id", "_chapter_transition_marker"):
                            cur_extra.pop(_tk, None)
                        if "player_resonance_pips" in pre_t:
                            raw_pre_pips = pre_t.get("player_resonance_pips")
                            cur_extra["player_resonance_pips"] = (
                                dict(raw_pre_pips) if isinstance(raw_pre_pips, dict) else int(raw_pre_pips or 0)
                            )
                        if "telemetry_calibrations_used" in pre_t and isinstance(pre_t["telemetry_calibrations_used"], dict):
                            cur_extra["telemetry_calibrations_used"] = dict(pre_t["telemetry_calibrations_used"])
                        if "anomalous_faction_state" in pre_t and isinstance(pre_t["anomalous_faction_state"], dict):
                            pre_afs = dict(pre_t["anomalous_faction_state"])
                            post_afs = cur_extra.get("anomalous_faction_state") if isinstance(cur_extra.get("anomalous_faction_state"), dict) else {}
                            pre_arch = str(pre_afs.get("faction_archetype_key") or "").strip().lower()
                            post_arch = str((post_afs or {}).get("faction_archetype_key") or "").strip().lower()
                            cur_extra["anomalous_faction_state"] = pre_afs
                            if pre_arch != post_arch:
                                restore_quarters_arch = pre_arch or (
                                    "student_freelancer"
                                    if str(pre_afs.get("origin_mode") or "").strip().lower() == "student"
                                    else "freelancer"
                                )
                        if "daily_incursions" in pre_t and pre_t.get("daily_incursions") is not None and int(pre_t.get("pre_turn_count", -1)) == t_num:
                            cur_extra["daily_incursions"] = list(pre_t["daily_incursions"])
                            cur_extra["daily_breaches"] = list(pre_t["daily_incursions"])
                        extra_dirty = True
                    if "party_factions" in pre_t and isinstance(pre_t["party_factions"], dict):
                        for pf_uid_raw, pf_data in pre_t["party_factions"].items():
                            if not isinstance(pf_data, dict):
                                continue
                            try:
                                pf_uid = int(pf_uid_raw)
                            except (TypeError, ValueError):
                                continue
                            jf_id = str(pf_data.get("joined_faction_id") or "")
                            if "faction_rank" in pf_data or "faction_title" in pf_data:
                                conn.execute(
                                    "UPDATE characters SET joined_faction_id = ?, faction_rank = ?, faction_title = ? WHERE user_id = ? AND (active_session_id = ? OR is_active = 1)",
                                    (
                                        jf_id,
                                        int(pf_data.get("faction_rank") or 0),
                                        str(pf_data.get("faction_title") or ""),
                                        pf_uid,
                                        session_id,
                                    ),
                                )
                            else:
                                conn.execute(
                                    "UPDATE characters SET joined_faction_id = ? WHERE user_id = ? AND (active_session_id = ? OR is_active = 1)",
                                    (jf_id, pf_uid, session_id),
                                )
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        if extra_dirty:
            conn.execute(
                "UPDATE sessions SET extra_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(cur_extra, default=str), time.time(), session_id),
            )
        if restore_quarters_arch:
            try:
                grant_or_relocate_starter_quarters(session_id, restore_quarters_arch, conn=conn)
            except Exception as exc:
                log.warning(
                    "Starter quarters rollback failed for session %s -> %s: %s",
                    session_id,
                    restore_quarters_arch,
                    exc,
                )
    from services.examine_service import invalidate_examine_cache
    invalidate_examine_cache(int(session_id))
    return {
        "ties_rolled_back": ties_cnt,
        "intimate_events_deleted": intimate_cnt,
        "commitments_deleted": simple_counts.get("commitments_deleted", 0),
        "world_events_rolled_back": we_res.get("total_rolled_back", 0),
        "dossiers_rolled_back": dos_res.get("dossiers_rolled_back", 0),
        "spines_rolled_back": dos_res.get("spines_rolled_back", 0),
        "npc_memories_deleted": simple_counts.get("npc_memories_deleted", 0),
        "digests_deleted": dg_cnt,
        "chronicles_deleted": ch_cnt,
        "session_clues_deleted": simple_counts.get("session_clues_deleted", 0),
        "physical_actors_restored": phys_res.get("physical_actors_restored", 0),
        "garments_restored": phys_res.get("garments_restored", 0),
        "social_discoveries_deleted": soc_pacing_res.get("discoveries_deleted", 0),
        "social_composure_restored": soc_pacing_res.get("composure_restored", 0),
        "social_daily_restored": soc_pacing_res.get("daily_restored", 0),
        "social_topics_restored": soc_pacing_res.get("topics_restored", 0),
        "properties_deleted": prop_res.get("properties_deleted", 0),
        "spare_keys_pruned": prop_res.get("spare_keys_pruned", 0),
        "folklore_villages_reverted": veil_res.get("villages_reverted", 0),
        "leyline_reverted": veil_res.get("leyline_reverted", 0),
        "folklore_hydrations_reverted": veil_res.get("hydrations_reverted", 0),
        "folklore_forms_reverted": veil_res.get("forms_reverted", 0),
        "folklore_tokens_reverted": veil_res.get("tokens_reverted", 0),
        "folklore_companions_pruned": veil_res.get("companions_pruned", 0),
        "hidden_clubs_reverted": hidden_clubs_reverted,
        "anomalous_sites_reverted": anomalous_sites_reverted,
        "contracts_restored": pact_res.get("contracts_restored", 0),
        "grudges_restored": pact_res.get("grudges_restored", 0),
        "pact_gear_pruned": pact_res.get("pact_gear_pruned", 0),
        "world_roster_rolled_back": (
            roster_res.get("roster_deleted", 0)
            + roster_res.get("roster_restored", 0)
            + roster_res.get("promoted_contacts_reverted", 0)
        ),
        "epistemic_rolled_back": (
            ep_res.get("facts_deleted", 0)
            + ep_res.get("facts_restored", 0)
            + ep_res.get("knowledge_deleted", 0)
            + ep_res.get("knowledge_restored", 0)
        ),
    }


def get_session_characters(session_id: int | dict) -> list[dict]:
    """Batch-loads all active party member characters for a session in a single JOIN query (no N+1)."""
    if isinstance(session_id, dict):
        session_id = session_id.get("id")
    if not session_id:
        return []
    from .characters import _apply_debug_stat_override
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT c.*
               FROM session_members sm
               JOIN characters c ON c.id = (
                   SELECT c2.id
                   FROM characters c2
                   LEFT JOIN sessions s ON s.id = ?
                   WHERE c2.user_id = sm.user_id
                   ORDER BY
                       CASE
                           WHEN s.character_id = c2.id THEN 0
                           WHEN c2.active_session_id = ? THEN 1
                           WHEN c2.is_active = 1 THEN 2
                           ELSE 3
                       END ASC,
                       c2.id DESC
                   LIMIT 1
               )
               WHERE sm.session_id = ?
               ORDER BY sm.joined_at ASC, c.id ASC""",
            (session_id, session_id, session_id),
        ).fetchall()
        if not rows:
            rows = conn.execute(
                """SELECT c.*
                   FROM characters c
                   JOIN sessions s ON (s.character_id = c.id OR c.active_session_id = s.id OR (s.host_user_id = c.user_id AND c.is_active = 1))
                   WHERE s.id = ?
                   ORDER BY
                       CASE
                           WHEN s.character_id = c.id THEN 0
                           WHEN c.active_session_id = s.id THEN 1
                           ELSE 2
                       END ASC,
                       c.is_active DESC,
                       c.id DESC
                   LIMIT 1""",
                (session_id,),
            ).fetchall()
        r_uids = list(dict.fromkeys(int(r["user_id"]) for r in rows if r and r["user_id"] is not None))
        settings_by_uid: dict[int, dict] = {}
        if r_uids:
            s_rows = conn.execute(
                "SELECT * FROM user_settings WHERE user_id IN (SELECT value FROM json_each(?))",
                (json.dumps(r_uids),),
            ).fetchall()
            settings_by_uid = {int(sr["user_id"]): dict(sr) for sr in s_rows if sr and sr["user_id"] is not None}
        from .contracts import get_session_pacts_batch
        pacts_by_uid = get_session_pacts_batch(int(session_id), holder_type="player", conn=conn)
    seen_ids: set[int] = set()
    out: list[dict] = []
    for r in rows:
        u_int = int(r["user_id"]) if r["user_id"] is not None else None
        d = _apply_debug_stat_override(
            dict(r),
            settings=settings_by_uid.get(u_int, {}) if u_int is not None else None,
            session_id=int(session_id),
            active_pacts=pacts_by_uid.get(str(u_int), []) if u_int is not None else [],
        )
        if d and d.get("id") not in seen_ids:
            seen_ids.add(int(d["id"]))
            out.append(d)
    return out


def list_open_lobbies_with_members(limit: int = 20) -> list[dict[str, Any]]:
    """Return open multiplayer lobbies with batched member counts and host names."""
    lim = max(1, int(limit or 20))
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, mode, capacity, host_user_id, scenario, scene_title, current_location, status, created_at
               FROM sessions
               WHERE status IN ('waiting', 'active') AND (mode IN ('turn', 'sync', 'multi') OR capacity > 1)
               ORDER BY updated_at DESC LIMIT ?""",
            (lim,),
        ).fetchall()
        if not rows:
            return []
        sids = [int(r["id"]) for r in rows]
        host_uids = list(dict.fromkeys(int(r["host_user_id"]) for r in rows if r["host_user_id"] is not None))
        member_counts: dict[int, int] = {}
        for mr in conn.execute(
            "SELECT session_id, COUNT(*) AS cnt FROM session_members WHERE session_id IN (SELECT value FROM json_each(?)) GROUP BY session_id",
            (json.dumps(sids),),
        ).fetchall():
            member_counts[int(mr["session_id"])] = int(mr["cnt"] or 0)
        host_names: dict[int, str] = {}
        if host_uids:
            for hr in conn.execute(
                """SELECT user_id, name FROM characters
                   WHERE user_id IN (SELECT value FROM json_each(?))
                   ORDER BY is_active DESC, id DESC""",
                (json.dumps(host_uids),),
            ).fetchall():
                u = int(hr["user_id"])
                if u not in host_names and hr["name"]:
                    host_names[u] = str(hr["name"])
        lobbies: list[dict[str, Any]] = []
        for r in rows:
            sid = int(r["id"])
            h_uid = int(r["host_user_id"]) if r["host_user_id"] is not None else 0
            lobbies.append({
                "id": sid,
                "mode": r["mode"],
                "capacity": r["capacity"],
                "member_count": member_counts.get(sid, 0),
                "host_user_id": r["host_user_id"],
                "host_name": host_names.get(h_uid) or f"User {r['host_user_id']}",
                "scenario": r["scenario"],
                "scene_title": r["scene_title"] or "",
                "current_location": r["current_location"] or "",
                "status": r["status"],
            })
        return lobbies


def join_multiplayer_session(
    session_id: int,
    user_id: int,
    char_id: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """Atomically join an active/waiting multiplayer session inside one UnitOfWork."""
    with UnitOfWork() as conn:
        s_cur = get_session(session_id)
        if not s_cur or s_cur.get("status") not in ("waiting", "active"):
            return None, "not_found"
        cur_members = list(get_session_members(session_id) or [])
        turn_order = [int(u) for u in (s_cur.get("turn_order") or []) if u is not None]
        participants = {int(u) for u in cur_members} | set(turn_order)
        if s_cur.get("host_user_id") is not None:
            participants.add(int(s_cur["host_user_id"]))
        cap = max(1, int(s_cur.get("capacity") or 1))
        if int(user_id) not in participants and len(participants) >= cap:
            return None, "full"
        add_session_member(session_id, int(user_id))
        if int(user_id) not in turn_order:
            turn_order.append(int(user_id))
        new_status = (
            "active"
            if s_cur.get("status") == "active" or len(turn_order) >= cap
            else "waiting"
        )
        conn.execute(
            "UPDATE sessions SET turn_order=?, status=?, updated_at=? WHERE id=?",
            (json.dumps(turn_order), new_status, time.time(), int(session_id)),
        )
        db.set_character_active_session(int(char_id), int(session_id))
        return get_session(session_id), None


def finalize_overwritten_slot_session(
    old_session_id: int,
    new_session_id: int,
    host_user_id: int,
) -> None:
    """Finalize a superseded save-slot session without resetting the newly embarked host."""
    if not old_session_id or int(old_session_id) == int(new_session_id or 0):
        return
    with UnitOfWork() as conn:
        sess_row = conn.execute(
            "SELECT scenario FROM sessions WHERE id=?",
            (int(old_session_id),),
        ).fetchone()
        sess_scenario = sess_row["scenario"] if sess_row else None
        stale_guest_uids = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT user_id FROM characters WHERE active_session_id=? AND user_id!=?",
                (int(old_session_id), int(host_user_id)),
            ).fetchall()
        ]
        conn.execute(
            "UPDATE sessions SET status='finished', updated_at=? WHERE id=?",
            (time.time(), int(old_session_id)),
        )
        conn.execute(
            "UPDATE characters SET active_session_id=NULL WHERE active_session_id=?",
            (int(old_session_id),),
        )
        for uid in stale_guest_uids:
            reset_character_for_new_adventure(uid, new_scenario=sess_scenario)


def snapshot_embark_rollback_state(char_id: int) -> dict[str, Any] | None:
    """Capture raw character and inventory rows before Turn-0 embark mutates them."""
    if not char_id:
        return None
    with ReadUnitOfWork() as conn:
        char_row = conn.execute(
            "SELECT * FROM characters WHERE id=?",
            (int(char_id),),
        ).fetchone()
        if not char_row:
            return None
        user_id = char_row["user_id"]
        inv_rows = conn.execute(
            "SELECT * FROM inventory WHERE character_id=? OR (character_id IS NULL AND user_id=?) ORDER BY id ASC",
            (int(char_id), user_id),
        ).fetchall()
        return {
            "character_id": int(char_id),
            "character": dict(char_row),
            "inventory": [dict(r) for r in inv_rows],
        }


def restore_embark_rollback_state(snapshot: dict[str, Any] | None) -> None:
    """Restore raw character and inventory rows after a failed Turn-0 embark."""
    if not isinstance(snapshot, dict) or not snapshot.get("character"):
        return
    char_dict = dict(snapshot["character"])
    cid = int(snapshot.get("character_id") or char_dict.get("id") or 0)
    if not cid:
        return
    with UnitOfWork() as conn:
        valid_char_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(characters)").fetchall()
        } - {"id"}
        cols = [k for k in char_dict.keys() if k in valid_char_cols]
        if cols:
            assignments = ", ".join(f"{col}=?" for col in cols)
            conn.execute(
                f"UPDATE characters SET {assignments} WHERE id=?",
                (*[char_dict[col] for col in cols], cid),
            )
        user_id = char_dict.get("user_id")
        if user_id is not None:
            conn.execute(
                "DELETE FROM inventory WHERE character_id=? OR (character_id IS NULL AND user_id=?)",
                (cid, user_id),
            )
        else:
            conn.execute("DELETE FROM inventory WHERE character_id=?", (cid,))
        valid_inv_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(inventory)").fetchall()
        } - {"id"}
        for item in snapshot.get("inventory") or []:
            if not isinstance(item, dict):
                continue
            item_cols = [k for k in item.keys() if k in valid_inv_cols]
            if not item_cols:
                continue
            placeholders = ", ".join("?" for _ in item_cols)
            col_list = ", ".join(item_cols)
            vals = [
                None
                if (k == "character_id" and item.get("character_id") is None)
                else (cid if k == "character_id" else item[k])
                for k in item_cols
            ]
            conn.execute(
                f"INSERT INTO inventory ({col_list}) VALUES ({placeholders})",
                vals,
            )


def snapshot_opening_retry_state(session_id: int) -> dict[str, Any] | None:
    """Capture session row, registry child rows, and starting prop before Turn-0 retry resets them."""
    if not session_id:
        return None
    sid = int(session_id)
    with ReadUnitOfWork() as conn:
        sess_row = conn.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        if not sess_row:
            return None
        sess_dict = dict(sess_row)
        child_tables: dict[str, list[dict[str, Any]]] = {}
        for spec in get_purge_specs(preserve_members=True):
            try:
                rows = conn.execute(
                    f"SELECT * FROM {spec.name} WHERE session_id=?",
                    (sid,),
                ).fetchall()
                if rows:
                    child_tables[spec.name] = [dict(r) for r in rows]
            except sqlite3.OperationalError:
                pass
        removed_prop: dict[str, Any] | None = None
        try:
            extra_dict = json.loads(sess_dict.get("extra_json") or "{}") or {}
        except Exception:
            extra_dict = {}
        prop_name = str(extra_dict.get("opening_starting_prop_name") or "").strip()
        char_id = sess_dict.get("character_id")
        if prop_name and not char_id:
            eff_uid = sess_dict.get("host_user_id")
            if eff_uid:
                char_row = conn.execute(
                    "SELECT id FROM characters WHERE user_id=? AND is_active=1 ORDER BY id DESC LIMIT 1",
                    (eff_uid,),
                ).fetchone()
                char_id = char_row["id"] if char_row else None
        if prop_name and char_id:
            inv_row = conn.execute(
                "SELECT * FROM inventory WHERE character_id=? AND LOWER(name)=LOWER(?) ORDER BY id DESC LIMIT 1",
                (int(char_id), prop_name),
            ).fetchone()
            if inv_row:
                removed_prop = dict(inv_row)
        return {
            "session_id": sid,
            "session": sess_dict,
            "child_tables": child_tables,
            "removed_prop": removed_prop,
        }


def restore_opening_retry_state(snapshot: dict[str, Any] | None) -> None:
    """Restore pre-retry Turn-0 session and child rows when opening regeneration fails."""
    if not isinstance(snapshot, dict) or not snapshot.get("session"):
        return
    sid = int(snapshot.get("session_id") or 0)
    sess_dict = dict(snapshot["session"])
    if not sid:
        return
    from .core import _delete_session_child_records_only

    with UnitOfWork() as conn:
        _delete_session_child_records_only(conn, sid, preserve_members=True)
        child_tables = snapshot.get("child_tables") or {}
        ordered_names = [
            s.name
            for s in reversed(get_purge_specs(preserve_members=True))
            if s.name in child_tables
        ]
        ordered_names.extend(k for k in child_tables if k not in ordered_names)
        for table_name in ordered_names:
            rows = child_tables[table_name]
            if not rows:
                continue
            try:
                valid_cols = {
                    r[1] for r in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
                }
            except sqlite3.OperationalError:
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                cols = [k for k in row.keys() if k in valid_cols]
                if not cols:
                    continue
                placeholders = ", ".join("?" for _ in cols)
                col_list = ", ".join(cols)
                conn.execute(
                    f"INSERT OR IGNORE INTO {table_name} ({col_list}) VALUES ({placeholders})",
                    [row[c] for c in cols],
                )
        removed_prop = snapshot.get("removed_prop")
        if isinstance(removed_prop, dict) and removed_prop.get("character_id") and removed_prop.get("name"):
            exists_inv = conn.execute(
                "SELECT 1 FROM inventory WHERE character_id=? AND LOWER(name)=LOWER(?) LIMIT 1",
                (int(removed_prop["character_id"]), str(removed_prop["name"])),
            ).fetchone()
            if not exists_inv:
                valid_inv_cols = {
                    r[1] for r in conn.execute("PRAGMA table_info(inventory)").fetchall()
                } - {"id"}
                icols = [k for k in removed_prop.keys() if k in valid_inv_cols]
                if icols:
                    placeholders = ", ".join("?" for _ in icols)
                    col_list = ", ".join(icols)
                    conn.execute(
                        f"INSERT INTO inventory ({col_list}) VALUES ({placeholders})",
                        [removed_prop[c] for c in icols],
                    )
        valid_sess_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(sessions)").fetchall()
        } - {"id"}
        scols = [k for k in sess_dict.keys() if k in valid_sess_cols]
        if scols:
            assignments = ", ".join(f"{c}=?" for c in scols)
            conn.execute(
                f"UPDATE sessions SET {assignments} WHERE id=?",
                (*[sess_dict[c] for c in scols], sid),
            )



