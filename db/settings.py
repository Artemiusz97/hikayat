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
            if not d.get("verbosity"):
                d["verbosity"] = "vivid"
            if not d.get("narrative_pacing"):
                d["narrative_pacing"] = (
                    "concise"
                    if str(d.get("verbosity") or "").strip().lower() in ("concise", "direct")
                    else "balanced"
                )
            if not d.get("dialogue_mode"):
                d["dialogue_mode"] = "adaptive"
            d.setdefault("show_percentages", 1)
            d.setdefault("show_enemy_hp", 1)
            d.setdefault("show_enemy_intent", 1)
            d.setdefault("combat_ui_style", "battle_deck")
            d.setdefault("debug_stat_mode", "off")
            d.setdefault("debug_check_mode", "off")
            d.setdefault("debug_reveal_all_info", 0)
            d.setdefault("stream_narrative", 1)
            d.setdefault("language", "en")
            d.setdefault("ui_language", d.get("language") or "en")
            d.setdefault("narration_language", d.get("language") or "en")
            return d
        conn.execute("INSERT INTO user_settings (user_id) VALUES (?)", (user_id,))
        return {
            "user_id": user_id,
            "verbosity": "vivid",
            "narrative_pacing": "balanced",
            "dialogue_mode": "adaptive",
            "image_gen_enabled": 0, "image_model": None, "choices_style": "dropdown",
            "combat_ui_style": "battle_deck",
            "result_display": "detailed", "show_percentages": 1,
            "show_enemy_hp": 1, "show_enemy_intent": 1,
            "stream_narrative": 1,
            "debug_stat_mode": "off", "debug_check_mode": "off",
            "debug_reveal_all_info": 0,
            "language": "en",
            "ui_language": "en",
            "narration_language": "en"
        }

def get_user_settings(user_id: int) -> dict:
    return db.get_settings(user_id)

def save_user_settings(user_id: int, **fields):
    filtered = {k: v for k, v in fields.items() if v is not None}
    if filtered:
        update_settings(user_id, **filtered)

def update_settings(user_id: int, **fields):
    cur_settings = db.get_settings(user_id)  # ensure row exists
    if "narrative_style" in fields:
        style_val = fields.pop("narrative_style")
        if style_val is not None:
            fields.setdefault("verbosity", style_val)
    if "narrative_pacing" in fields:
        if "verbosity" in fields:
            if str(fields.get("verbosity") or "").strip().lower() in ("concise", "direct"):
                fields["verbosity"] = "normal"
        elif str(cur_settings.get("verbosity") or "").strip().lower() in ("concise", "direct"):
            fields["verbosity"] = "normal"
    elif (
        "verbosity" in fields
        and str(fields.get("verbosity") or "").strip().lower() in ("concise", "direct")
    ):
        fields["narrative_pacing"] = "concise"
    if not fields:
        return
    if "narration_language" in fields and "language" not in fields:
        fields["language"] = fields["narration_language"]
    elif "language" in fields and "narration_language" not in fields:
        fields["narration_language"] = fields["language"]
    with get_conn() as conn:
        u_cur = conn.execute("PRAGMA table_info(user_settings)")
        user_cols = {row["name"] if isinstance(row, sqlite3.Row) else row[1] for row in u_cur.fetchall()}
        valid_user_fields = {k: v for k, v in fields.items() if k in user_cols}
        if valid_user_fields:
            cols = ", ".join(f"{k}=?" for k in valid_user_fields)
            conn.execute(f"UPDATE user_settings SET {cols} WHERE user_id=?",
                         (*valid_user_fields.values(), user_id))
        
        session_id = db.get_active_session_id_for_user(user_id)
        if session_id:
            session_fields = {k: v for k, v in valid_user_fields.items() if k in (
                "language", "narration_language", "verbosity", "narrative_pacing", "dialogue_mode",
                "image_gen_enabled", "choices_style", "combat_ui_style", "result_display",
                "show_percentages", "show_enemy_hp", "show_enemy_intent"
            )}
            if session_fields:
                try:
                    cur = conn.execute("PRAGMA table_info(sessions)")
                    existing_cols = {row["name"] if isinstance(row, sqlite3.Row) else row[1] for row in cur.fetchall()}
                    valid_fields = {k: v for k, v in session_fields.items() if k in existing_cols}
                    if valid_fields:
                        s_cols = ", ".join(f"{k}=?" for k in valid_fields)
                        conn.execute(
                            f"UPDATE sessions SET {s_cols} WHERE id=? AND (capacity <= 1 OR host_user_id=?)",
                            (*valid_fields.values(), session_id, user_id),
                        )
                except Exception:
                    pass


def sync_user_settings_to_session(user_id: int, session_id: int) -> None:
    """Synchronizes the user's global user_settings onto a target session when solo or host."""
    if not user_id or not session_id:
        return
    user_cfg = get_settings(user_id)
    sync_keys = (
        "language",
        "narration_language",
        "verbosity",
        "narrative_pacing",
        "dialogue_mode",
        "image_gen_enabled",
        "choices_style",
        "combat_ui_style",
        "result_display",
        "show_percentages",
        "show_enemy_hp",
        "show_enemy_intent",
    )
    with get_conn() as conn:
        cur = conn.execute("PRAGMA table_info(sessions)")
        sess_cols = {row["name"] if isinstance(row, sqlite3.Row) else row[1] for row in cur.fetchall()}
        payload = {k: user_cfg[k] for k in sync_keys if k in user_cfg and k in sess_cols}
        if not payload:
            return
        s_cols = ", ".join(f"{k}=?" for k in payload)
        conn.execute(
            f"UPDATE sessions SET {s_cols} WHERE id=? AND (capacity <= 1 OR host_user_id=?)",
            (*payload.values(), session_id, user_id),
        )

