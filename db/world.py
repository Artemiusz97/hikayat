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

def save_merchant_state(session_id: int, merchant: dict):
    """Persists the full merchant encounter/shop blob for a session -- see
    cogs/adventure.py's merchant classes for the shape (available/active
    flags, stock, rumors, haggle_attempts, discount_pct, pending_vote).
    A single JSON column, same pattern as choices_json/pending_picks_json
    above, so this survives bot restarts like everything else session-side."""
    with get_conn() as conn:
        conn.execute("UPDATE sessions SET merchant_json=? WHERE id=?",
                      (json.dumps(merchant), session_id))

def upsert_lorebook_entity(session_id: int, entity_type: str, name: str,
                            description: str = "", disposition: str = "neutral", faction: str = "",
                            traits: list | str = None, motivation: str = "", mannerisms: str = "",
                            race: str = "", appearance: dict = None, status: str = "active"):
    name = (name or "").strip()
    if not name:
        return
    race = (race or "").strip()
    status = (status or "active").strip().lower()
    # Defensively coerce string fields — the LLM can sometimes return a dict
    # instead of a plain string (e.g. disposition={"mood": "friendly"}).
    description = _to_str(description)
    disposition = _to_str(disposition, "neutral")
    faction     = _to_str(faction)
    motivation  = _to_str(motivation)
    mannerisms  = _to_str(mannerisms)
    traits_json = json.dumps(traits) if isinstance(traits, (list, tuple)) else (traits or "[]")
    app_json = json.dumps(appearance) if isinstance(appearance, dict) else (appearance or "{}")

    import namegen
    if entity_type.lower() == "person" and namegen.is_generic_role_name(name):
        role_title = name
        matched_name = None
        with get_conn() as conn:
            fac_rows = conn.execute("SELECT leadership_roster_json FROM factions WHERE session_id=?", (session_id,)).fetchall()
            for fr in fac_rows:
                try:
                    r_list = json.loads(fr["leadership_roster_json"] or "[]")
                    for r in r_list:
                        if r.get("title", "").lower() == role_title.lower() or role_title.lower() in r.get("title", "").lower():
                            matched_name = r.get("name")
                            break
                    if matched_name: break
                except Exception:
                    pass
        if matched_name:
            name = matched_name
        if role_title.lower() not in (description or "").lower():
            description = f"{role_title} — {description or ''}".strip(" —")

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id, race, appearance_json, status FROM lorebook WHERE session_id=? AND lower(name)=lower(?)",
            (session_id, name)).fetchone()
        if existing:
            existing_race = existing["race"]
            if existing_race and str(existing_race).strip().lower() not in ("", "unknown", "human"):
                final_race = existing_race
            elif race and str(race).strip().lower() not in ("", "unknown", "human"):
                final_race = race
            elif existing_race and str(existing_race).strip().lower() not in ("", "unknown"):
                final_race = existing_race
            else:
                final_race = race or existing_race or ""

            import mechanics.social.persona as persona
            existing_app = json.loads(existing["appearance_json"] or "{}")
            incoming_app = appearance if isinstance(appearance, dict) else (json.loads(app_json) if app_json and app_json != "{}" else {})
            merged_app = persona.merge_appearance_safely(existing_app, incoming_app)
            final_app_json = json.dumps(merged_app)

            # If existing status is something terminal like 'deceased', usually it shouldn't be blindly overwritten
            # by a casual 'active' update unless explicitly meant. 
            final_status = existing["status"]
            if final_status != "deceased" or status == "deceased":
                final_status = status

            conn.execute(
                """UPDATE lorebook SET description=COALESCE(NULLIF(?, ''), description),
                                        disposition=COALESCE(NULLIF(?, ''), disposition),
                                        faction=COALESCE(NULLIF(?, ''), faction),
                                        traits=COALESCE(NULLIF(?, '[]'), NULLIF(?, ''), traits),
                                        motivation=COALESCE(NULLIF(?, ''), motivation),
                                        mannerisms=COALESCE(NULLIF(?, ''), mannerisms),
                                        race=?,
                                        appearance_json=?,
                                        status=?,
                                        updated_at=? WHERE id=?""",
                (description, disposition, faction, traits_json, traits_json, motivation, mannerisms, final_race, final_app_json, final_status, time.time(), existing["id"]))
        else:
            conn.execute(
                """INSERT INTO lorebook (session_id, entity_type, name, description, disposition,
                                          faction, traits, motivation, mannerisms, race, appearance_json, status, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (session_id, entity_type, name, description, disposition or "neutral",
                 faction, traits_json, motivation or "", mannerisms or "", race or "", app_json, status, time.time()))

def get_lorebook(session_id: int) -> dict:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM lorebook WHERE session_id=? ORDER BY updated_at",
                             (session_id,)).fetchall()
    grouped = {"person": [], "place": [], "faction": []}
    for r in rows:
        d = dict(r)
        traits_val = d.get("traits", "[]")
        if isinstance(traits_val, str):
            try:
                d["traits"] = json.loads(traits_val)
            except Exception:
                d["traits"] = []
        elif not isinstance(traits_val, list):
            d["traits"] = []
        try:
            d["appearance"] = json.loads(d.get("appearance_json") or "{}")
        except Exception:
            d["appearance"] = {}
        grouped.setdefault(r["entity_type"], []).append(d)
    return grouped

def get_lorebook_entity(session_id: int, name: str) -> dict | None:
    """Returns a specific lorebook entity by name (case-insensitive) for a session."""
    if not name or not session_id:
        return None
    clean_name = str(name).strip().lower()
    with get_conn() as conn:
        r = conn.execute(
            """SELECT * FROM lorebook WHERE session_id=? AND (
                   lower(name)=? OR
                   lower(name) LIKE ? OR
                   ? LIKE (lower(name) || '%')
               ) ORDER BY id DESC LIMIT 1""",
            (session_id, clean_name, f"%{clean_name}%", clean_name)
        ).fetchone()
        if not r:
            return None
        d = dict(r)
        traits_val = d.get("traits", "[]")
        if isinstance(traits_val, str):
            try:
                d["traits"] = json.loads(traits_val)
            except Exception:
                d["traits"] = []
        elif not isinstance(traits_val, list):
            d["traits"] = []
        try:
            d["appearance"] = json.loads(d.get("appearance_json") or "{}")
        except Exception:
            d["appearance"] = {}
        return d

def get_known_world_data(session_id: int) -> dict:
    """Batches fetching of lorebook, contacts, and factions
    in a single database connection pass for optimal prompt building performance."""
    with get_conn() as conn:
        lore_rows = conn.execute(
            "SELECT entity_type, name, description, disposition, race, traits, motivation, mannerisms, appearance_json, embedding_json FROM lorebook WHERE session_id=? ORDER BY updated_at DESC",
            (session_id,)
        ).fetchall()
        
        contact_rows = conn.execute(
            "SELECT * FROM contacts WHERE session_id=? ORDER BY updated_at DESC",
            (session_id,)
        ).fetchall()
        
        faction_rows = conn.execute(
            "SELECT * FROM factions WHERE session_id=? ORDER BY updated_at DESC",
            (session_id,)
        ).fetchall()

    lore = {"place": [], "person": [], "faction": []}
    for r in lore_rows:
        d = dict(r)
        if d.get("traits"):
            try:
                d["traits"] = json.loads(d["traits"]) if isinstance(d["traits"], str) else d["traits"]
            except Exception:
                d["traits"] = []
        try:
            d["appearance"] = json.loads(d.get("appearance_json") or "{}")
        except Exception:
            d["appearance"] = {}
        etype = d.get("entity_type")
        if etype in lore:
            lore[etype].append(d)

    contacts = []
    import mechanics.social.persona as persona
    for r in contact_rows:
        d = dict(r)
        try:
            d["basic_info"] = json.loads(d.get("basic_info_json") or "{}")
        except Exception:
            d["basic_info"] = {}
        try:
            raw_traits = json.loads(d.get("unlocked_traits_json") or "[]")
        except Exception:
            raw_traits = []
        try:
            raw_prefs = json.loads(d.get("preferences_json") or "[]")
        except Exception:
            raw_prefs = []

        clean_traits, clean_prefs = persona.split_traits_and_preferences(raw_traits, raw_prefs)
        d["unlocked_traits"] = clean_traits
        d["preferences"] = clean_prefs

        if d.get("basic_info") and isinstance(d["basic_info"], dict) and d["basic_info"].get("description"):
            d["basic_info"]["description"] = persona.sanitize_npc_description(d["basic_info"]["description"], d.get("appearance"))

        try:
            d["appearance"] = json.loads(d.get("appearance_json") or "{}")
        except Exception:
            d["appearance"] = {}
        contacts.append(d)

    factions = [db._parse_faction_row(dict(r)) for r in faction_rows]

    return {
        "lore": lore,
        "contacts": contacts,
        "factions": factions,
    }

def save_session_location(
    session_id: int,
    location_id: str,
    zone_name: str,
    primary_name: str,
    sub_name: str,
    atmosphere: str = "",
    is_dynamic: int = 0
):
    """Upserts a discovered or seed location into the session map."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO session_locations
               (session_id, location_id, zone_name, primary_name, sub_name, atmosphere, is_dynamic, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id, location_id) DO UPDATE SET
               zone_name=excluded.zone_name,
               primary_name=excluded.primary_name,
               sub_name=excluded.sub_name,
               atmosphere=excluded.atmosphere,
               is_dynamic=excluded.is_dynamic""",
            (session_id, location_id, zone_name, primary_name, sub_name, atmosphere, is_dynamic, time.time())
        )
    return True

def get_session_locations(session_id: int) -> list[dict]:
    """Retrieve all locations registered for a session."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT location_id, zone_name, primary_name, sub_name, atmosphere, is_dynamic FROM session_locations WHERE session_id = ? ORDER BY id ASC",
            (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]


async def update_missing_lorebook_embeddings(session_id: int):
    """Asynchronously batch embed any lorebook entries that lack embeddings."""
    with get_conn() as conn:
        rows = conn.execute("SELECT id, name, description FROM lorebook WHERE session_id=? AND (embedding_json IS NULL OR embedding_json = '[]')", (session_id,)).fetchall()
        
    if not rows:
        return
        
    import asyncio
    from llm_client import get_embedding
    import json
    import logging
    
    log = logging.getLogger("hikayat.db.world")
    
    async def embed_row(r):
        text = f"{r['name']}: {r['description']}"
        emb = await get_embedding(text)
        return r['id'], emb
        
    results = await asyncio.gather(*(embed_row(r) for r in rows))
    
    with get_conn() as conn:
        for row_id, emb in results:
            if emb:
                conn.execute("UPDATE lorebook SET embedding_json=? WHERE id=?", (json.dumps(emb), row_id))
        conn.commit()

