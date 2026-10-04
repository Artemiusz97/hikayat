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

def save_adventure_slot(user_id: int, slot_name: str, overwrite: bool = False) -> dict:
    """Creates or overwrites a named checkpoint save slot for the user's active character."""
    import re
    cleaned_slot = (slot_name or "").strip()
    if not cleaned_slot or len(cleaned_slot) > 32:
        raise ValueError("Save slot name must be between 1 and 32 characters.")
    if not re.match(r"^[\w\s\-]+$", cleaned_slot, re.UNICODE):
        raise ValueError("Slot name contains invalid characters. Use letters, numbers, spaces, hyphens, or underscores.")

    char = db.get_character(user_id)
    if not char:
        raise ValueError("You don't have an active character. Create one with `/character create` first.")
    char_id = char["id"]

    session_id = db.get_active_session_id_for_user(user_id)
    if not session_id:
        raise ValueError("You are not currently in an active adventure to save.")

    with get_conn() as conn:
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
        if not existing and total_saves >= 10:
            raise ValueError("Maximum save slots reached (10 slots per character). Delete an older save first.")

        # Gather all child table data
        child_data = {}
        for tbl in SESSION_CHILD_TABLES:
            if tbl == "session_members":
                continue
            try:
                rows = conn.execute(f"SELECT * FROM {tbl} WHERE session_id = ?", (session_id,)).fetchall()
                cleaned_rows = []
                for r in rows:
                    rd = dict(r)
                    rd.pop("id", None)
                    cleaned_rows.append(rd)
                child_data[tbl] = cleaned_rows
            except Exception:
                child_data[tbl] = []

        # Gather character adventure inventory
        inv_rows = conn.execute("SELECT * FROM inventory WHERE character_id = ?", (char_id,)).fetchall()
        cleaned_inv = []
        for r in inv_rows:
            rd = dict(r)
            rd.pop("id", None)
            cleaned_inv.append(rd)

        # Character adventure vitals snapshot
        char_state = {
            "hp": char["hp"],
            "mp": char["mp"],
            "gold": char["gold"],
            "status_effects": char.get("status_effects", "[]"),
            "days_adventured": char.get("days_adventured", 1)
        }

        snapshot = {
            "version": 1,
            "session": sess_dict,
            "child_tables": child_data,
            "character_state": char_state,
            "inventory": cleaned_inv
        }
        snapshot_json = json.dumps(snapshot)

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
    char = db.get_character(user_id)
    if not char:
        raise ValueError("You don't have an active character. Create one with `/character create` first.")
    char_id = char["id"]

    with get_conn() as conn:
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
        sess_data["status"] = "active"
        sess_data["created_at"] = now
        sess_data["updated_at"] = now
        sess_data["turn_order"] = json.dumps(to)

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

        # Restore child tables with remapped session_id
        for tbl, rows in child_data.items():
            for r in rows:
                row_dict = dict(r)
                row_dict["session_id"] = new_session_id
                if tbl == "contacts":
                    row_dict["character_id"] = char_id
                for k, v in row_dict.items():
                    if isinstance(v, (dict, list)):
                        row_dict[k] = json.dumps(v)
                c_names = ",".join(row_dict.keys())
                qmarks = ",".join("?" * len(row_dict))
                conn.execute(f"INSERT OR IGNORE INTO {tbl} ({c_names}) VALUES ({qmarks})", list(row_dict.values()))

        # Restore character inventory
        conn.execute("DELETE FROM inventory WHERE character_id = ?", (char_id,))
        for item in saved_inv:
            item_dict = dict(item)
            item_dict["character_id"] = char_id
            item_dict["user_id"] = user_id
            for k, v in item_dict.items():
                if isinstance(v, (dict, list)):
                    item_dict[k] = json.dumps(v)
            c_names = ",".join(item_dict.keys())
            qmarks = ",".join("?" * len(item_dict))
            conn.execute(f"INSERT INTO inventory ({c_names}) VALUES ({qmarks})", list(item_dict.values()))

        # Restore character vitals and link active_session_id
        conn.execute(
            """UPDATE characters
               SET hp = ?, mp = ?, gold = ?, status_effects = ?, days_adventured = ?, active_session_id = ?
               WHERE id = ?""",
            (
                char_state.get("hp", char["max_hp"]),
                char_state.get("mp", char["max_mp"]),
                char_state.get("gold", char["gold"]),
                char_state.get("status_effects", "[]"),
                char_state.get("days_adventured", 1),
                new_session_id,
                char_id
            )
        )

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

