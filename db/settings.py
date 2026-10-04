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

def get_settings(user_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM user_settings WHERE user_id=?", (user_id,)).fetchone()
        if row:
            d = dict(row)
            d.setdefault("show_percentages", 1)
            d.setdefault("combat_ui_style", "battle_deck")
            d.setdefault("debug_stat_mode", "off")
            d.setdefault("debug_check_mode", "off")
            d.setdefault("debug_reveal_all_info", 0)
            d.setdefault("stream_narrative", 1)
            return d
        conn.execute("INSERT INTO user_settings (user_id) VALUES (?)", (user_id,))
        return {
            "user_id": user_id, "verbosity": "vivid", "dialogue_mode": "balanced",
            "image_gen_enabled": 0, "image_model": None, "choices_style": "dropdown",
            "combat_ui_style": "battle_deck",
            "result_display": "detailed", "show_percentages": 1,
            "stream_narrative": 1,
            "debug_stat_mode": "off", "debug_check_mode": "off",
            "debug_reveal_all_info": 0
        }

def get_user_settings(user_id: int) -> dict:
    return db.get_settings(user_id)

def save_user_settings(user_id: int, **fields):
    filtered = {k: v for k, v in fields.items() if v is not None}
    if filtered:
        update_settings(user_id, **filtered)

def update_settings(user_id: int, **fields):
    db.get_settings(user_id)  # ensure row exists
    cols = ", ".join(f"{k}=?" for k in fields)
    with get_conn() as conn:
        conn.execute(f"UPDATE user_settings SET {cols} WHERE user_id=?",
                     (*fields.values(), user_id))
        
        session_id = db.get_active_session_id_for_user(user_id)
        if session_id:
            session_fields = {k: v for k, v in fields.items() if k in (
                "verbosity", "dialogue_mode", "image_gen_enabled",
                "choices_style", "combat_ui_style", "result_display", "show_percentages"
            )}
            if session_fields:
                try:
                    cur = conn.execute("PRAGMA table_info(sessions)")
                    existing_cols = {row["name"] if isinstance(row, sqlite3.Row) else row[1] for row in cur.fetchall()}
                    valid_fields = {k: v for k, v in session_fields.items() if k in existing_cols}
                    if valid_fields:
                        s_cols = ", ".join(f"{k}=?" for k in valid_fields)
                        conn.execute(f"UPDATE sessions SET {s_cols} WHERE id=?",
                                     (*valid_fields.values(), session_id))
                except Exception:
                    pass

