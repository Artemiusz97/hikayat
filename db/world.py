import db
import asyncio
import json
import time
from contextlib import contextmanager
import re
import sqlite3
from config import DB_PATH
import character_data as cd
import heapq
from collections import defaultdict
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
                            race: str = "", appearance: dict = None, status: str = "active",
                            gender: str = ""):
    name = (name or "").strip()
    if not name:
        return
    race = (race or "").strip()
    gender = (gender or "").strip().lower()
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
    if entity_type.lower() == "person":
        if namegen.is_collective_entity_name(name):
            return
        if namegen.is_generic_role_name(name) or not namegen.is_valid_entity_name(name):
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
            sess = None
            try:
                with get_conn() as conn:
                    s_row = conn.execute("SELECT scenario FROM sessions WHERE id=?", (session_id,)).fetchone()
                    scen = s_row["scenario"] if s_row and s_row["scenario"] else "fantasy"
            except Exception:
                scen = "fantasy"
            name = matched_name or namegen.generate_person_name(scen, gender=gender)
            if role_title.lower() not in (description or "").lower():
                description = f"{role_title} — {description or ''}".strip(" —")

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id, race, appearance_json, status, gender FROM lorebook WHERE session_id=? AND lower(name)=lower(?)",
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
                                        gender=COALESCE(NULLIF(?, ''), gender),
                                        race=?,
                                        appearance_json=?,
                                        status=?,
                                        updated_at=? WHERE id=?""",
                (description, disposition, faction, traits_json, traits_json, motivation, mannerisms, gender, final_race, final_app_json, final_status, time.time(), existing["id"]))
        else:
            conn.execute(
                """INSERT INTO lorebook (session_id, entity_type, name, description, disposition,
                                          faction, traits, motivation, mannerisms, gender, race, appearance_json, status, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (session_id, entity_type, name, description, disposition or "neutral",
                 faction, traits_json, motivation or "", mannerisms or "", gender, race or "", app_json, status, time.time()))

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
    try:
        _sync_location_to_spatial_graph(
            session_id, location_id, zone_name, primary_name, sub_name,
            atmosphere=atmosphere, is_dynamic=is_dynamic
        )
    except Exception:
        pass
    return True

def format_node_tiered_location(session_id: int, node_id: str, fallback_zone: str = "World Region") -> str:
    """Formats a world_nodes node_id into its canonical 'Zone ➔ Facility ➔ Room' string in <1ms."""
    if not session_id or not node_id:
        return ""
    nodes = get_session_world_nodes(session_id)
    if not nodes:
        return ""
    node_map = {n["node_id"]: n for n in nodes}
    target = node_map.get(node_id)
    if not target:
        return ""
    n_type = target.get("node_type", "ROOM")
    if n_type == "ZONE":
        return f"{target['name']} ➔ Main Area ➔ Main Area"
    if n_type == "FACILITY":
        parent = node_map.get(target.get("parent_id")) if target.get("parent_id") else None
        z_name = parent["name"] if parent else fallback_zone
        return f"{z_name} ➔ {target['name']} ➔ Main Area"
    # ROOM node
    fac = node_map.get(target.get("parent_id")) if target.get("parent_id") else None
    zone = node_map.get(fac.get("parent_id")) if (fac and fac.get("parent_id")) else fac
    z_name = zone["name"] if zone else fallback_zone
    p_name = fac["name"] if fac else target["name"]
    s_name = target["name"]
    return f"{z_name} ➔ {p_name} ➔ {s_name}"


def get_session_locations(session_id: int) -> list[dict]:
    """Retrieve all locations registered for a session (synthesizing from world_nodes when session_locations is empty)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT location_id, zone_name, primary_name, sub_name, atmosphere, is_dynamic FROM session_locations WHERE session_id = ? ORDER BY id ASC",
            (session_id,)
        ).fetchall()
        if rows:
            return [dict(r) for r in rows]

    # Fallback: synthesize 3-tier location records directly from world_nodes
    nodes = get_session_world_nodes(session_id)
    if not nodes:
        return []
    node_map = {n["node_id"]: n for n in nodes}
    synthesized: list[dict] = []
    for n in nodes:
        if n.get("node_type") == "ROOM":
            fac = node_map.get(n.get("parent_id")) if n.get("parent_id") else None
            zone = node_map.get(fac.get("parent_id")) if (fac and fac.get("parent_id")) else fac
            z_name = zone["name"] if zone else "World Region"
            p_name = fac["name"] if fac else n["name"]
            synthesized.append({
                "location_id": n["node_id"],
                "zone_name": z_name,
                "primary_name": p_name,
                "sub_name": n["name"],
                "atmosphere": n.get("atmosphere") or (fac.get("atmosphere") if fac else "") or "",
                "is_dynamic": int(n.get("is_dynamic") or 0),
            })
    return synthesized


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


# =========================================================================
# Spatial Graph (world_nodes and world_edges) CRUD Operations
# =========================================================================

def save_world_node(
    session_id: int,
    node_id: str,
    parent_id: str | None,
    name: str,
    node_type: str,
    category: str = "academic",
    privacy_level: str = "public",
    is_enclosed: int = 1,
    is_transit_hub: int = 0,
    access_tier: str = "open",
    curfew_start_min: int | None = None,
    curfew_end_min: int | None = None,
    atmosphere: str = "",
    is_dynamic: int = 0,
    state_json: str | dict | None = None
) -> bool:
    """Upserts a spatial graph node into world_nodes, preserving state_json if not provided."""
    s_json_val = json.dumps(state_json) if isinstance(state_json, dict) else state_json
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO world_nodes
               (session_id, node_id, parent_id, name, node_type, category, privacy_level,
                is_enclosed, is_transit_hub, access_tier, curfew_start_min, curfew_end_min,
                atmosphere, is_dynamic, state_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id, node_id) DO UPDATE SET
               parent_id=excluded.parent_id,
               name=excluded.name,
               node_type=excluded.node_type,
               category=excluded.category,
               privacy_level=excluded.privacy_level,
               is_enclosed=excluded.is_enclosed,
               is_transit_hub=excluded.is_transit_hub,
               access_tier=excluded.access_tier,
               curfew_start_min=excluded.curfew_start_min,
               curfew_end_min=excluded.curfew_end_min,
               atmosphere=excluded.atmosphere,
               is_dynamic=excluded.is_dynamic,
               state_json=CASE WHEN excluded.state_json IS NOT NULL THEN excluded.state_json ELSE COALESCE(world_nodes.state_json, '{}') END""",
            (
                session_id, node_id, parent_id, name, node_type, category, privacy_level,
                is_enclosed, is_transit_hub, access_tier, curfew_start_min, curfew_end_min,
                atmosphere, is_dynamic, s_json_val, time.time()
            )
        )
    return True


def get_world_node(session_id: int, node_id: str) -> dict | None:
    """Retrieves a single node by node_id for a session."""
    if not node_id:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM world_nodes WHERE session_id = ? AND node_id = ?",
            (session_id, node_id)
        ).fetchone()
        return dict(row) if row else None


def get_world_node_state(session_id: int, node_id: str) -> dict:
    """Retrieves state_json for a node as a dict (default {})."""
    if not session_id or not node_id:
        return {}
    with get_conn() as conn:
        row = conn.execute(
            "SELECT state_json FROM world_nodes WHERE session_id = ? AND node_id = ?",
            (session_id, node_id)
        ).fetchone()
        if not row or not row["state_json"]:
            return {}
        try:
            return json.loads(row["state_json"]) if isinstance(row["state_json"], str) else dict(row["state_json"])
        except Exception:
            return {}


def update_world_node_state(session_id: int, node_id: str, updates: dict) -> dict:
    """Merges updates into state_json for a node and returns the updated state dict."""
    if not session_id or not node_id:
        return {}
    cur_state = get_world_node_state(session_id, node_id)
    cur_state.update(updates or {})
    new_json = json.dumps(cur_state)
    with get_conn() as conn:
        conn.execute(
            "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
            (new_json, session_id, node_id)
        )
    return cur_state


def get_session_world_nodes(session_id: int) -> list[dict]:
    """Retrieves all spatial graph nodes for a session ordered by hierarchy."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM world_nodes WHERE session_id = ? ORDER BY id ASC",
            (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def save_world_edge(
    session_id: int,
    from_node_id: str,
    to_node_id: str,
    travel_minutes: int = 2,
    edge_type: str = "hallway",
    is_bidirectional: int = 1,
    is_locked: int = 0,
    lock_key_item: str = "",
    skill_check_type: str = "",
    skill_check_dc: int = 0
) -> bool:
    """Upserts a directional navigation edge between two nodes."""
    with get_conn() as conn:
        now = time.time()
        conn.execute(
            """INSERT INTO world_edges
               (session_id, from_node_id, to_node_id, travel_minutes, edge_type,
                is_bidirectional, is_locked, lock_key_item, skill_check_type, skill_check_dc, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id, from_node_id, to_node_id) DO UPDATE SET
               travel_minutes=excluded.travel_minutes,
               edge_type=excluded.edge_type,
               is_bidirectional=excluded.is_bidirectional,
               is_locked=excluded.is_locked,
               lock_key_item=excluded.lock_key_item,
               skill_check_type=excluded.skill_check_type,
               skill_check_dc=excluded.skill_check_dc""",
            (
                session_id, from_node_id, to_node_id, travel_minutes, edge_type,
                is_bidirectional, is_locked, lock_key_item, skill_check_type, skill_check_dc, now
            )
        )
        if is_bidirectional and from_node_id != to_node_id:
            conn.execute(
                """INSERT INTO world_edges
                   (session_id, from_node_id, to_node_id, travel_minutes, edge_type,
                    is_bidirectional, is_locked, lock_key_item, skill_check_type, skill_check_dc, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(session_id, from_node_id, to_node_id) DO UPDATE SET
                   travel_minutes=excluded.travel_minutes,
                   edge_type=excluded.edge_type,
                   is_bidirectional=excluded.is_bidirectional,
                   is_locked=excluded.is_locked,
                   lock_key_item=excluded.lock_key_item,
                   skill_check_type=excluded.skill_check_type,
                   skill_check_dc=excluded.skill_check_dc""",
                (
                    session_id, to_node_id, from_node_id, travel_minutes, edge_type,
                    is_bidirectional, is_locked, lock_key_item, skill_check_type, skill_check_dc, now
                )
            )
    return True


def _sync_location_to_spatial_graph(
    session_id: int,
    location_id: str,
    zone_name: str,
    primary_name: str,
    sub_name: str,
    atmosphere: str = "",
    is_dynamic: int = 0
):
    """Ensures a location saved to session_locations also exists in world_nodes and world_edges."""
    if not session_id or not zone_name or not primary_name:
        return
    existing_nodes = get_session_world_nodes(session_id)
    if not existing_nodes and not is_dynamic:
        # Initial bulk seed will seed the full graph
        return

    from mechanics.world.locations.graph_seeder import (
        _slugify, infer_node_category, infer_node_privacy,
        infer_is_enclosed, infer_is_transit_hub, infer_access_tier,
        infer_curfew_window
    )

    z_id = next((n["node_id"] for n in existing_nodes if n["node_type"] == "ZONE" and n["name"].lower() == zone_name.lower()), None)
    if not z_id:
        z_id = f"zone_dyn_{_slugify(zone_name)}"
        z_cat = infer_node_category(z_id, "", zone_name)
        z_acc = infer_access_tier("ZONE", z_id, z_id, zone_name, z_cat)
        z_cs, z_ce = infer_curfew_window("ZONE", z_id, z_id, zone_name, z_cat)
        save_world_node(
            session_id=session_id, node_id=z_id, parent_id=None, name=zone_name,
            node_type="ZONE", category=z_cat,
            privacy_level="public", is_enclosed=0, is_transit_hub=1,
            access_tier=z_acc, curfew_start_min=z_cs, curfew_end_min=z_ce,
            atmosphere=atmosphere, is_dynamic=is_dynamic
        )

    p_id = next((n["node_id"] for n in existing_nodes if n["node_type"] == "FACILITY" and n["name"].lower() == primary_name.lower()), None)
    if not p_id:
        p_id = f"loc_dyn_{_slugify(zone_name)}_{_slugify(primary_name)}"
        cat = infer_node_category(z_id, p_id, primary_name)
        p_acc = infer_access_tier("FACILITY", z_id, p_id, primary_name, cat)
        p_cs, p_ce = infer_curfew_window("FACILITY", z_id, p_id, primary_name, cat)
        save_world_node(
            session_id=session_id, node_id=p_id, parent_id=z_id, name=primary_name,
            node_type="FACILITY", category=cat,
            privacy_level=infer_node_privacy("FACILITY", p_id, primary_name),
            is_enclosed=infer_is_enclosed("FACILITY", p_id, primary_name),
            is_transit_hub=infer_is_transit_hub("FACILITY", z_id, p_id, primary_name),
            access_tier=p_acc, curfew_start_min=p_cs, curfew_end_min=p_ce,
            atmosphere=atmosphere, is_dynamic=is_dynamic
        )
        # Link to sibling facilities in the same zone (5 mins) or any existing hub (15 mins across zones)
        same_zone_facs = [n["node_id"] for n in existing_nodes if n["node_type"] == "FACILITY" and n.get("parent_id") == z_id and n["node_id"] != p_id]
        for sf_id in same_zone_facs[:3]:
            save_world_edge(session_id, p_id, sf_id, travel_minutes=5, edge_type="pathway", is_bidirectional=1)
        if not same_zone_facs:
            any_hub = next((n["node_id"] for n in existing_nodes if n["node_type"] == "FACILITY" and n.get("is_transit_hub")), None)
            if any_hub and any_hub != p_id:
                save_world_edge(session_id, p_id, any_hub, travel_minutes=15, edge_type="Cross-Zone", is_bidirectional=1)

    s_clean = (sub_name or "Main Area").strip()
    r_id = next((n["node_id"] for n in existing_nodes if n["node_type"] == "ROOM" and n.get("parent_id") == p_id and n["name"].lower() == s_clean.lower()), None)
    if not r_id:
        r_id = location_id if str(location_id).startswith("sub_") else f"sub_dyn_{_slugify(primary_name)}_{_slugify(s_clean)}"
        cat = infer_node_category(z_id, p_id, primary_name)
        r_acc = infer_access_tier("ROOM", z_id, r_id, s_clean, cat)
        r_cs, r_ce = infer_curfew_window("ROOM", z_id, r_id, s_clean, cat)
        save_world_node(
            session_id=session_id, node_id=r_id, parent_id=p_id, name=s_clean,
            node_type="ROOM", category=cat,
            privacy_level=infer_node_privacy("ROOM", r_id, s_clean),
            is_enclosed=infer_is_enclosed("ROOM", r_id, s_clean),
            is_transit_hub=0, access_tier=r_acc, curfew_start_min=r_cs, curfew_end_min=r_ce,
            atmosphere=atmosphere, is_dynamic=is_dynamic
        )
        save_world_edge(session_id, p_id, r_id, travel_minutes=1, edge_type="internal", is_bidirectional=1)
        sibling_rooms = [n["node_id"] for n in existing_nodes if n["node_type"] == "ROOM" and n.get("parent_id") == p_id and n["node_id"] != r_id]
        for sr_id in sibling_rooms:
            save_world_edge(session_id, r_id, sr_id, travel_minutes=1, edge_type="internal", is_bidirectional=1)


def get_outgoing_edges(session_id: int, from_node_id: str, include_parent_pathways: bool = True) -> list[dict]:
    """Retrieves all traversable outgoing edges from a specific node, optionally inheriting parent pathways."""
    if not from_node_id:
        return []
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT e.*, n.name as to_node_name, n.node_type as to_node_type,
                      n.category as to_category, n.is_transit_hub as to_is_transit_hub
               FROM world_edges e
               JOIN world_nodes n ON e.session_id = n.session_id AND e.to_node_id = n.node_id
               WHERE e.session_id = ? AND e.from_node_id = ?
               ORDER BY e.travel_minutes ASC""",
            (session_id, from_node_id)
        ).fetchall()
        edges = [dict(r) for r in rows]

    if include_parent_pathways:
        curr_node = get_world_node(session_id, from_node_id)
        if curr_node and curr_node.get("node_type") == "ROOM" and curr_node.get("parent_id"):
            parent_id = curr_node["parent_id"]
            parent_edges = get_outgoing_edges(session_id, parent_id, include_parent_pathways=False)
            existing_targets = {e["to_node_id"] for e in edges} | {from_node_id, parent_id}
            for pe in parent_edges:
                if pe.get("edge_type") in ("pathway", "cross_zone", "Cross-Zone") and pe["to_node_id"] not in existing_targets:
                    inherited = dict(pe)
                    inherited["from_node_id"] = from_node_id
                    inherited["travel_minutes"] = int(pe.get("travel_minutes", 2)) + 1
                    edges.append(inherited)
                    existing_targets.add(pe["to_node_id"])
            edges.sort(key=lambda x: x.get("travel_minutes", 0))

    return edges


def get_session_world_edges(session_id: int) -> list[dict]:
    """Retrieves all edges defined for a session."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM world_edges WHERE session_id = ? ORDER BY id ASC",
            (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_node_ancestors(session_id: int, node_id: str) -> list[dict]:
    """Traverses parent_id pointers up to the root zone node."""
    ancestors = []
    curr = get_world_node(session_id, node_id)
    visited = set()
    while curr and curr.get("parent_id"):
        p_id = curr["parent_id"]
        if p_id in visited:
            break
        visited.add(p_id)
        p_node = get_world_node(session_id, p_id)
        if p_node:
            ancestors.append(p_node)
            curr = p_node
        else:
            break
    return ancestors


def is_descendant_of(session_id: int, node_id: str, ancestor_id: str) -> bool:
    """Returns True if node_id is equal to ancestor_id or has ancestor_id anywhere in its parent chain."""
    if not node_id or not ancestor_id:
        return False
    if node_id == ancestor_id:
        return True
    ancestors = get_node_ancestors(session_id, node_id)
    return any(a["node_id"] == ancestor_id for a in ancestors)


def is_node_or_parent_transit_hub(session_id: int, node_id: str) -> bool:
    """Checks if the node itself or any of its parent facilities/zones is a transit hub."""
    if not session_id or not node_id:
        return False
    curr = get_world_node(session_id, node_id)
    if curr and curr.get("is_transit_hub"):
        return True
    ancestors = get_node_ancestors(session_id, node_id)
    return any(bool(a.get("is_transit_hub")) for a in ancestors)


def resolve_node_id_from_location(session_id: int, location_str: str, prefer_facility: bool = False) -> str | None:
    """
    Deterministically resolves a location string (e.g. 3-tier string, primary name,
    leaf name, or raw node_id) to its corresponding node_id in the session's spatial graph.
    If prefer_facility is True, prefers matching FACILITY nodes over child ROOM nodes.
    """
    if not session_id or not location_str:
        return None
    loc_clean = str(location_str).strip()
    if not loc_clean:
        return None

    # 1. Exact node_id match
    direct = get_world_node(session_id, loc_clean)
    if direct:
        return direct["node_id"]

    nodes = get_session_world_nodes(session_id)
    if not nodes:
        return None

    # Check if exact node_id match exists in nodes
    for n in nodes:
        if n["node_id"].lower() == loc_clean.lower():
            return n["node_id"]

    parts = [p.strip() for p in re.split(r"\s*(?:➔|->|>|/)\s*", loc_clean) if p.strip()]
    leaf_name = parts[-1].lower() if parts else ""
    prim_name = parts[1].lower() if len(parts) >= 2 else (parts[0].lower() if parts else "")

    # 2. If prim_name exists, resolve within the primary facility/zone first
    prim_node = None
    if prim_name:
        for n in nodes:
            if n.get("node_type") in ("FACILITY", "ZONE") and n["name"].lower() == prim_name:
                prim_node = n
                break
        if not prim_node:
            for n in nodes:
                if n.get("node_type") in ("FACILITY", "ZONE") and (prim_name in n["name"].lower() or n["name"].lower() in prim_name):
                    prim_node = n
                    break

    if prim_node:
        if prefer_facility:
            return prim_node["node_id"]
        if leaf_name and leaf_name != prim_name:
            # Check exact child under prim_node
            child = next((rn for rn in nodes if rn.get("parent_id") == prim_node["node_id"] and rn["name"].lower() == leaf_name), None)
            if child:
                return child["node_id"]
            if leaf_name not in ("main area", "area", "main"):
                child = next((rn for rn in nodes if rn.get("parent_id") == prim_node["node_id"] and (leaf_name in rn["name"].lower() or rn["name"].lower() in leaf_name)), None)
                if child:
                    return child["node_id"]
                if ("gate path" in leaf_name or "entrance path" in leaf_name or "front gate" in leaf_name) and prim_node["node_id"] == "loc_school_gate":
                    child = next((rn for rn in nodes if rn.get("parent_id") == prim_node["node_id"] and rn["node_id"] == "sub_entrance_path"), None)
                    if child:
                        return child["node_id"]
        return prim_node["node_id"]

    # 3. Match on leaf name (only non-generic)
    if leaf_name and leaf_name not in ("main area", "area", "main"):
        type_order = ("FACILITY", "ZONE", "ROOM") if prefer_facility else ("ROOM", "FACILITY", "ZONE")
        for n_type in type_order:
            for n in nodes:
                if n.get("node_type") == n_type and n["name"].lower() == leaf_name:
                    return n["node_id"]

    # 4. Containment / Substring match on leaf name (only non-generic)
    if leaf_name and len(leaf_name) >= 4 and leaf_name not in ("main area", "area", "main"):
        for n in nodes:
            n_low = n["name"].lower()
            if leaf_name in n_low or n_low in leaf_name:
                return n["node_id"]

    # 5. Containment / Substring match on primary name
    if prim_name and len(prim_name) >= 4:
        for n in nodes:
            n_low = n["name"].lower()
            if prim_name in n_low or n_low in prim_name:
                return n["node_id"]

    return None


def find_shortest_graph_path_minutes(session_id: int, from_node_id: str, to_node_id: str) -> int | None:
    """
    Computes shortest-path travel time in minutes between two nodes using Dijkstra's algorithm
    over world_edges plus implicit 1-minute parent-child transitions.
    Returns travel minutes (>= 2 for distinct nodes) or None if unreachable.
    """
    if not session_id or not from_node_id or not to_node_id:
        return None
    if from_node_id == to_node_id:
        return 2

    edges = get_session_world_edges(session_id)
    nodes = get_session_world_nodes(session_id)
    if not edges and not nodes:
        return None

    adj = defaultdict(list)
    for e in edges:
        u = e.get("from_node_id")
        v = e.get("to_node_id")
        w = max(1, int(e.get("travel_minutes") or 2))
        if u and v:
            adj[u].append((v, w))
            if e.get("is_bidirectional", 1):
                adj[v].append((u, w))

    # Add implicit parent-child transitions (1 minute between facility and room)
    for n in nodes:
        pid = n.get("parent_id")
        nid = n.get("node_id")
        if pid and nid:
            adj[pid].append((nid, 1))
            adj[nid].append((pid, 1))

    dist = {from_node_id: 0}
    pq = [(0, from_node_id)]

    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, float('inf')):
            continue
        if u == to_node_id:
            return max(2, d)
        for v, w in adj.get(u, []):
            if d + w < dist.get(v, float('inf')):
                dist[v] = d + w
                heapq.heappush(pq, (d + w, v))

    return max(2, dist[to_node_id]) if to_node_id in dist else None



