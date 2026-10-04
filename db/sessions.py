import db
import asyncio
import json
import time
from contextlib import contextmanager
import re
import sqlite3
from config import DB_PATH
import character_data as cd
from .core import *
from .core import _delete_session_records, _to_str, _is_suspicious_entity_text, _safe_int_db, _sanitize_npcs_list

def create_session(host_user_id: int, mode: str, capacity: int, verbosity: str,
                    dialogue_mode: str, image_gen_enabled: bool, choices_style: str = "dropdown",
                    channel_id: int = 0, scenario: str = "fantasy",
                    result_display: str = "detailed", combat_ui_style: str = "battle_deck",
                    show_percentages: int = 1) -> int:
    status = "active" if capacity <= 1 else "waiting"
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO sessions (mode, capacity, status, turn_order, current_turn_index,
                                      choices_json, history_json, pending_picks_json,
                                      current_location, nearby_enemies_json, current_npcs_json,
                                      verbosity, dialogue_mode, image_gen_enabled, choices_style, combat_ui_style,
                                      result_display, scenario, channel_id, host_user_id, created_at, updated_at,
                                      show_percentages)
               VALUES (?,?,?,?,0,'[]','[]','{}','','[]','[]',?,?,?,?,?,?,?,?,?,?,?,?)""",
            (mode, capacity, status, json.dumps([host_user_id]), verbosity,
             dialogue_mode, 1 if image_gen_enabled else 0, choices_style, combat_ui_style,
             result_display, scenario, channel_id, host_user_id, time.time(), time.time(),
             1 if show_percentages else 0),
        )
        session_id = cur.lastrowid
        conn.execute("INSERT INTO session_members (session_id, user_id, joined_at) VALUES (?,?,?)",
                      (session_id, host_user_id, time.time()))
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
        d["physical_state"] = json.loads(d.pop("physical_state_json", None) or "{}")
        d["last_turn_snapshot"] = json.loads(d.pop("last_turn_snapshot_json", None) or "{}")
        d["party_npcs"] = json.loads(d.pop("party_npcs_json", None) or "[]")
        d["party_recruit_cooldowns"] = json.loads(d.pop("party_recruit_cooldowns_json", None) or "{}")
        d["confession_cooldowns"] = json.loads(d.pop("confession_cooldowns_json", None) or "{}")
        d["phone_social_state"] = json.loads(d.pop("phone_social_state_json", None) or "{}")
        d["scenario"] = d.get("scenario") or "fantasy"
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
        else:
            d["dialogue_partners"] = []
        d["dialogue_partner"] = d["dialogue_partners"][0] if d["dialogue_partners"] else None

        if "extra_json" in d:
            extra_raw = d.pop("extra_json", None) or "{}"
            try:
                extra_dict = json.loads(extra_raw if isinstance(extra_raw, str) else json.dumps(extra_raw))
                if isinstance(extra_dict, dict):
                    d.update(extra_dict)
            except Exception:
                pass
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
                        dialogue_partner: str = "__NOOP__"):
    clean_narrative = _to_str(narrative)
    if clean_narrative:
        from game_engine.keywords import sanitize_meta_objective_leaks
        clean_narrative = sanitize_meta_objective_leaks(clean_narrative)

    fields = {
        "scene_title": _to_str(scene_title),
        "narrative": clean_narrative,
        "choices_json": json.dumps(choices, default=str) if not isinstance(choices, str) else choices,
        "history_json": json.dumps(history, default=str) if not isinstance(history, str) else history,
        "updated_at": time.time(),
    }

    if location is not None:
        fields["current_location"] = _to_str(location)
    if nearby_enemies is not None:
        json_str = json.dumps(nearby_enemies, default=str) if not isinstance(nearby_enemies, str) else nearby_enemies
        fields["nearby_enemies_json"] = json_str
    if current_npcs is not None:
        sanitized_npcs = _sanitize_npcs_list(session_id, current_npcs)
        fields["current_npcs_json"] = json.dumps(sanitized_npcs, default=str)
    if physical_state is not None:
        fields["physical_state_json"] = json.dumps(physical_state, default=str) if not isinstance(physical_state, str) else physical_state
    if dialogue_partner != "__NOOP__":
        if isinstance(dialogue_partner, list):
            fields["dialogue_partner"] = json.dumps(dialogue_partner, default=str) if dialogue_partner else None
        else:
            fields["dialogue_partner"] = dialogue_partner if dialogue_partner else None

    cols = ", ".join(f"{k}=?" for k in fields)
    with get_conn() as conn:
        conn.execute(f"UPDATE sessions SET {cols} WHERE id=?", (*fields.values(), session_id))

def update_session(session_id: int, **kwargs):
    """Dynamically updates one or more fields on a session record in the database.

    Accepts direct column names (e.g. pending_picks_json, history_json, narrative)
    or friendly aliases (e.g. choices, history, current_npcs, nearby_enemies, location, extra).
    """
    if not kwargs:
        return

    # Handle 'extra' dictionary if supplied (e.g. pending_promotion)
    extra_update = kwargs.pop("extra", None)
    if extra_update and isinstance(extra_update, dict):
        try:
            with get_conn() as conn:
                row = conn.execute("SELECT extra_json FROM sessions WHERE id=?", (session_id,)).fetchone()
                existing_extra = {}
                if row and row["extra_json"]:
                    try:
                        existing_extra = json.loads(row["extra_json"])
                    except Exception:
                        existing_extra = {}
                existing_extra.update(extra_update)
                # Filter out None values so callers can delete keys by setting them to None
                cleaned_extra = {k: v for k, v in existing_extra.items() if v is not None}
                kwargs["extra_json"] = json.dumps(cleaned_extra, default=str)
        except Exception:
            pass

    column_aliases = {
        "history": "history_json",
        "choices": "choices_json",
        "current_npcs": "current_npcs_json",
        "nearby_enemies": "nearby_enemies_json",
        "location": "current_location",
        "physical_state": "physical_state_json",
        "party_npcs": "party_npcs_json",
        "last_turn_snapshot": "last_turn_snapshot_json",
    }

    fields = {}
    for k, v in kwargs.items():
        col = column_aliases.get(k, k)
        if col == "current_npcs_json" and not isinstance(v, str):
            sanitized = _sanitize_npcs_list(session_id, v)
            v = json.dumps(sanitized, default=str)
        elif col.endswith("_json") and not isinstance(v, str):
            v = json.dumps(v, default=str)
        elif col in ("scene_title", "narrative", "current_location") and v is not None:
            v = _to_str(v)
        elif col == "dialogue_partner":
            if isinstance(v, list):
                v = json.dumps(v, default=str) if v else None
            elif not v:
                v = None
        fields[col] = v


    fields["updated_at"] = time.time()

    cols = ", ".join(f"{k}=?" for k in fields)
    with get_conn() as conn:
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
    with get_conn() as conn:
        row = conn.execute("SELECT physical_state_json FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row or not row["physical_state_json"]:
            return {}
        try:
            return json.loads(row["physical_state_json"])
        except Exception:
            return {}

def update_session_physical_state(session_id: int, physical_state: dict):
    with get_conn() as conn:
        conn.execute("UPDATE sessions SET physical_state_json=?, updated_at=? WHERE id=?",
                     (json.dumps(physical_state) if isinstance(physical_state, dict) else str(physical_state), time.time(), session_id))

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

def reset_session_room_props(session_id: int):
    """Purges location-bound room furniture/props while preserving actor postures, garments, and personal gear."""
    state = get_session_physical_state(session_id)
    if state and isinstance(state, dict):
        state["props"] = {}
        state["room_layout"] = ""
        update_session_physical_state(session_id, state)

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

def get_session_party_npcs(session_id: int) -> list[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT party_npcs_json FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row or not row["party_npcs_json"]:
            return []
        try:
            return json.loads(row["party_npcs_json"])
        except Exception:
            return []

def set_session_party_npcs(session_id: int, party_npcs: list[dict]):
    with get_conn() as conn:
        conn.execute("UPDATE sessions SET party_npcs_json=?, updated_at=? WHERE id=?",
                     (json.dumps(party_npcs or []), time.time(), session_id))

def add_session_party_npc(session_id: int, npc_dict: dict) -> bool:
    """Adds an NPC to party_npcs if total party size (humans + companions) is under 4."""
    party = get_session_party_npcs(session_id)
    sess = db.get_session(session_id)
    human_count = len(sess.get("turn_order", [])) if sess else 1
    if human_count + len(party) >= 4:
        return False
    name_clean = str(npc_dict.get("name", "")).strip().lower()
    if any(str(p.get("name", "")).strip().lower() == name_clean for p in party):
        return False
    party.append(npc_dict)
    set_session_party_npcs(session_id, party)
    return True

def remove_session_party_npc(session_id: int, npc_name: str) -> dict | None:
    party = get_session_party_npcs(session_id)
    name_clean = str(npc_name).strip().lower()
    removed = None
    new_party = []
    for p in party:
        if str(p.get("name", "")).strip().lower() == name_clean and removed is None:
            removed = p
        else:
            new_party.append(p)
    if removed is not None:
        set_session_party_npcs(session_id, new_party)
    return removed

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

def reset_character_for_new_adventure(user_id: int, new_scenario: str = None):
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
    max_hp = char["max_hp"]
    max_mp = char["max_mp"]
    scenario = new_scenario or char.get("scenario", "fantasy")
    char_class = char.get("char_class", "")

    with get_conn() as conn:
        # Wipe entire inventory (items + equipment, equipped flags are part of these rows)
        conn.execute(
            "DELETE FROM inventory WHERE character_id=? OR (character_id IS NULL AND user_id=?)",
            (char_id, user_id)
        )
        # Reset vitals, gold, and status effects on the character row
        conn.execute(
            "UPDATE characters SET hp=?, mp=?, gold=?, status_effects='[]' WHERE id=?",
            (max_hp, max_mp, cd.STARTING_GOLD, char_id)
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
    # Collect all members before we clear their active_session_id
    members = get_session_members(session_id)
    with get_conn() as conn:
        conn.execute("UPDATE sessions SET status='finished', updated_at=? WHERE id=?",
                      (time.time(), session_id))
        conn.execute("UPDATE characters SET active_session_id=NULL WHERE active_session_id=?", (session_id,))
    # Reset each member's transient state so it doesn't bleed into the next adventure
    for uid in members:
        reset_character_for_new_adventure(uid)

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

            for tbl in SESSION_CHILD_TABLES:
                if dry_run:
                    cnt = conn.execute(f"SELECT count(*) FROM {tbl} WHERE session_id IN ({placeholders})", chunk).fetchone()[0]
                    counts["deleted_by_table"][tbl] = counts["deleted_by_table"].get(tbl, 0) + cnt
                else:
                    cur = conn.execute(f"DELETE FROM {tbl} WHERE session_id IN ({placeholders})", chunk)
                    counts["deleted_by_table"][tbl] = counts["deleted_by_table"].get(tbl, 0) + cur.rowcount

            if dry_run:
                cnt = conn.execute(f"SELECT count(*) FROM sessions WHERE id IN ({placeholders})", chunk).fetchone()[0]
                counts["deleted_by_table"]["sessions"] = counts["deleted_by_table"].get("sessions", 0) + cnt
            else:
                cur = conn.execute(f"DELETE FROM sessions WHERE id IN ({placeholders})", chunk)
                counts["deleted_by_table"]["sessions"] = counts["deleted_by_table"].get("sessions", 0) + cur.rowcount

        # Also purge any child records whose session was already deleted directly
        for tbl in SESSION_CHILD_TABLES:
            if dry_run:
                cnt = conn.execute(f"SELECT count(*) FROM {tbl} WHERE session_id NOT IN (SELECT id FROM sessions)").fetchone()[0]
                if cnt > 0:
                    counts["deleted_by_table"][tbl] = counts["deleted_by_table"].get(tbl, 0) + cnt
            else:
                cur = conn.execute(f"DELETE FROM {tbl} WHERE session_id NOT IN (SELECT id FROM sessions)")
                if cur.rowcount > 0:
                    counts["deleted_by_table"][tbl] = counts["deleted_by_table"].get(tbl, 0) + cur.rowcount

        return counts

def set_pending_pick(session_id: int, user_id: int, pick: dict):
    session = db.get_session(session_id)
    picks = dict(session["pending_picks"])
    picks[str(user_id)] = pick
    with get_conn() as conn:
        conn.execute("UPDATE sessions SET pending_picks_json=? WHERE id=?",
                      (json.dumps(picks), session_id))

def clear_pending_picks(session_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE sessions SET pending_picks_json='{}' WHERE id=?", (session_id,))

