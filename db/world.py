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
        if not row and node_id in _LEGACY_NODE_ID_ALIASES:
            row = conn.execute(
                "SELECT * FROM world_nodes WHERE session_id = ? AND node_id = ?",
                (session_id, _LEGACY_NODE_ID_ALIASES[node_id])
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
        if not row and node_id in _LEGACY_NODE_ID_ALIASES:
            row = conn.execute(
                "SELECT state_json FROM world_nodes WHERE session_id = ? AND node_id = ?",
                (session_id, _LEGACY_NODE_ID_ALIASES[node_id])
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
    target_id = node_id
    with get_conn() as conn:
        exists = conn.execute(
            "SELECT 1 FROM world_nodes WHERE session_id = ? AND node_id = ?",
            (session_id, node_id)
        ).fetchone()
        if not exists and node_id in _LEGACY_NODE_ID_ALIASES:
            target_id = _LEGACY_NODE_ID_ALIASES[node_id]
    cur_state = get_world_node_state(session_id, target_id)
    cur_state.update(updates or {})
    new_json = json.dumps(cur_state)
    with get_conn() as conn:
        conn.execute(
            "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
            (new_json, session_id, target_id)
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
        if not rows and from_node_id in _LEGACY_NODE_ID_ALIASES:
            from_node_id = _LEGACY_NODE_ID_ALIASES[from_node_id]
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
    if _LEGACY_NODE_ID_ALIASES.get(node_id) == ancestor_id or node_id == _LEGACY_NODE_ID_ALIASES.get(ancestor_id):
        return True
    ancestors = get_node_ancestors(session_id, node_id)
    anc_target = _LEGACY_NODE_ID_ALIASES.get(ancestor_id, ancestor_id)
    return any(a["node_id"] in (ancestor_id, anc_target) for a in ancestors)


def is_node_or_parent_transit_hub(session_id: int, node_id: str) -> bool:
    """Checks if the node itself or any of its parent facilities/zones is a transit hub."""
    if not session_id or not node_id:
        return False
    curr = get_world_node(session_id, node_id)
    if curr and curr.get("is_transit_hub"):
        return True
    ancestors = get_node_ancestors(session_id, node_id)
    return any(bool(a.get("is_transit_hub")) for a in ancestors)


_LEGACY_NODE_ID_ALIASES: dict[str, str] = {
    "zone_school_athletics": "bld_school_athletics",
    "zone_school_commons": "bld_school_commons",
    "zone_school_arts": "bld_school_arts",
    "zone_abandoned_school": "bld_abandoned_school",
    "zone_agency_hq": "loc_agency_hq",
    "sub_player_desk": "loc_homeroom",
    "sub_friend_desk": "loc_homeroom",
    "sub_podium": "loc_homeroom",
    "sub_back_window": "loc_homeroom",
    "sub_front_row": "loc_empty_class",
    "sub_back_corner": "loc_empty_class",
    "sub_stairwell": "loc_school_hallway",
    "sub_locker_row": "loc_school_hallway",
    "sub_outside_door": "loc_school_hallway",
    "sub_teacher_desk": "loc_staff_room",
    "sub_print_room": "loc_staff_room",
    "sub_counselor_corner": "loc_staff_room",
    "sub_study_tables": "loc_library",
    "sub_book_aisles": "loc_library",
    "sub_librarian_counter": "loc_library",
    "sub_lab_bench": "loc_science_lab",
    "sub_chemical_closet": "loc_science_lab",
    "sub_fume_hood": "loc_science_lab",
    "sub_roof_benches": "loc_rooftop",
    "sub_behind_tank": "loc_rooftop",
    "sub_fence_line": "loc_rooftop",
    "sub_entrance_path": "loc_school_gate",
    "sub_gate_checkpoint": "loc_school_gate",
    "sub_notice_board": "loc_school_gate",
    "sub_bike_racks": "loc_school_gate",
    "sub_shoe_lockers": "loc_entrance_foyer",
    "sub_main_lobby": "loc_entrance_foyer",
    "sub_announcement_board": "loc_entrance_foyer",
    "sub_basketball_court": "loc_gymnasium",
    "sub_gym_storage": "loc_gymnasium",
    "sub_locker_room": "loc_gymnasium",
    "sub_gym_bleachers": "loc_gymnasium",
    "sub_running_track": "loc_sports_field",
    "sub_bleachers": "loc_sports_field",
    "sub_goal_posts": "loc_sports_field",
    "sub_under_bleachers": "loc_sports_field",
    "sub_pool_deck": "loc_pool",
    "sub_starting_blocks": "loc_pool",
    "sub_swim_clubroom": "loc_pool",
    "sub_tatami_mat": "loc_martial_arts_dojo",
    "sub_weapon_rack": "loc_martial_arts_dojo",
    "sub_dojo_altar": "loc_martial_arts_dojo",
    "sub_delinquent_benches": "loc_behind_gym_sheds",
    "sub_behind_shed": "loc_behind_gym_sheds",
    "sub_graffiti_wall": "loc_behind_gym_sheds",
    "sub_fountain_bench": "loc_courtyard",
    "sub_cherry_trees": "loc_courtyard",
    "sub_clock_tower_plaza": "loc_courtyard",
    "sub_dining_tables": "loc_cafeteria",
    "sub_lunch_line": "loc_cafeteria",
    "sub_bakery_counter": "loc_cafeteria",
    "sub_corner_booth": "loc_cafeteria",
    "sub_drinks_vending": "loc_vending_pavilion",
    "sub_snack_vending": "loc_vending_pavilion",
    "sub_pavilion_benches": "loc_vending_pavilion",
    "sub_greenhouse_path": "loc_greenhouse",
    "sub_potting_bench": "loc_greenhouse",
    "sub_fern_corner": "loc_greenhouse",
    "sub_botanical_glasshouse_entrance": "loc_greenhouse",
    "sub_president_desk": "loc_student_council",
    "sub_pres_desk": "loc_student_council",
    "sub_meeting_table": "loc_student_council",
    "campus promenade & student commons": "bld_school_commons",
    "student commons & central plaza": "bld_school_commons",
    "central courtyard & dining plaza": "bld_school_commons",
    "sunlit commons & central plaza": "bld_school_commons",
    "student plaza & dining pavilion": "bld_school_commons",
    "cultural arts & student union": "bld_school_arts",
    "school grounds & athletics": "bld_school_athletics",
    "abandoned old campus building": "bld_abandoned_school",
    "sub_council_archives": "loc_student_council",
    "sub_club_corridor": "loc_clubroom_corridor",
    "sub_literature_corner": "loc_clubroom_corridor",
    "sub_gaming_table": "loc_clubroom_corridor",
    "sub_shared_storage": "loc_clubroom_corridor",
    "sub_stage_center": "loc_auditorium_stage",
    "sub_backstage_wings": "loc_auditorium_stage",
    "sub_prop_room": "loc_auditorium_stage",
    "sub_seating_rows": "loc_auditorium_stage",
    "sub_piano_alcove": "loc_old_east_music_room",
    "sub_sheet_music_shelves": "loc_old_east_music_room",
    "sub_soundproof_closet": "loc_old_east_music_room",
    "sub_velvet_couch": "loc_old_east_music_room",
    "sub_easel_circle": "loc_fine_arts_studio",
    "sub_kiln_corner": "loc_fine_arts_studio",
    "sub_supply_sink": "loc_fine_arts_studio",
    "sub_mic_booth": "loc_broadcasting_room",
    "sub_newspaper_desk": "loc_broadcasting_room",
    "sub_photo_darkroom": "loc_broadcasting_room",
    "sub_boarded_corridor": "loc_ruined_hallway",
    "sub_broken_staircase": "loc_ruined_hallway",
    "sub_trophy_case": "loc_ruined_hallway",
    "sub_ritual_table": "loc_old_storage_3b",
    "sub_tarot_corner": "loc_old_storage_3b",
    "sub_cursed_shelves": "loc_old_storage_3b",
    "sub_cracked_court": "loc_derelict_gym",
    "sub_broken_stage": "loc_derelict_gym",
    "sub_dark_equipment_room": "loc_derelict_gym",
    "sub_spiral_stairs": "loc_clock_tower",
    "sub_clockwork_gears": "loc_clock_tower",
    "sub_belfry_ledge": "loc_clock_tower",
    "sub_rusted_beds": "loc_old_infirmary",
    "sub_medicine_cabinet": "loc_old_infirmary",
    "sub_curtain_divider": "loc_old_infirmary",
    "loc_art_studio": "loc_fine_arts_studio",
    "loc_vending_alcove": "loc_vending_pavilion",
    "loc_clubroom_wing": "loc_clubroom_corridor",
    "loc_auditorium": "loc_auditorium_stage",
    "loc_old_music_room": "loc_old_east_music_room",
    "loc_broadcast_room": "loc_broadcasting_room",
    "zone_hospital": "loc_general_hospital",
    "zone_theme_park": "loc_theme_park",
    "zone_eastern_temple": "loc_eastern_temple",
    "zone_botanical_zoo": "loc_botanical_zoo",
    "zone_desecrated_cathedral": "loc_desecrated_cathedral",
    "zone_haunted_manor": "loc_haunted_manor",
    "loc_botanical_conservatory": "loc_botanical_zoo",
    "loc_bz_biodome": "loc_bz_glass_biodomes",
    "sub_front_porch": "sub_player_front_porch",
    "sub_living_room": "sub_player_living_room",
    "sub_kitchen": "sub_player_kitchen",
    "sub_bedroom": "sub_player_bedroom",
    "sub_private_1_lobby": "sub_priv1_entrance",
    "sub_private_1_vault": "sub_priv1_dispatch",
    "sub_private_1_exchange": "sub_priv1_armory",
    "sub_private_2_lobby": "sub_priv2_entrance",
    "sub_private_2_vault": "sub_priv2_dispatch",
    "sub_private_2_exchange": "sub_priv2_armory",
    "sub_priv1_lobby": "sub_priv1_entrance",
    "sub_priv2_lobby": "sub_priv2_entrance",
    "sub_cult_vestibule": "sub_cult_entrance",
    "sub_syndicate_front": "sub_synd_entrance",
    "sub_syndicate_exchange": "sub_synd_floor",
    "sub_syndicate_vault": "sub_synd_vault",
    "sub_local_caf\u00e9_entrance": "loc_cafe",
    "sub_window_seat": "loc_cafe",
    "sub_cafe_counter": "loc_cafe",
    "sub_staff_breakroom": "loc_cafe",
    "sub_game_arcade_entrance": "loc_arcade",
    "sub_fighting_games": "loc_arcade",
    "sub_crane_games": "loc_arcade",
    "sub_photo_booth": "loc_arcade",
    "sub_karaoke_lounge_entrance": "loc_karaoke",
    "sub_room_4": "loc_karaoke",
    "sub_magazine_rack": "loc_convenience_store",
    "sub_cash_register": "loc_convenience_store",
    "sub_store_front": "loc_convenience_store",
    "sub_neighborhood_park_entrance": "loc_local_park",
    "sub_park_swings": "loc_local_park",
    "sub_park_bench": "loc_local_park",
    "sub_sandbox": "loc_local_park",
    "sub_sandy_beach_coastline_entrance": "loc_sandy_beach",
    "sub_towel_spot": "loc_sandy_beach",
    "sub_shoreline_waves": "loc_sandy_beach",
    "sub_lifeguard_tower": "loc_sandy_beach",
    "sub_boardwalk_pier_lighthouse_entrance": "loc_coastal_pier",
    "sub_pier_railings": "loc_coastal_pier",
    "sub_seaside_beach_shack_entrance": "loc_seaside_cafe",
    "sub_patio_table": "loc_seaside_cafe",
    "sub_shave_ice_stand": "loc_seaside_cafe",
    "sub_campfire_pit": "loc_campsite",
    "zone_commercial": "zone_downtown",
    "commercial district": "zone_downtown",
    "loc_transit_plaza": "loc_city_square",
    "commuter station & civic plaza": "loc_city_square",
    "zone_mountain_park": "zone_recreational_park",
    "recreational mountain park": "zone_recreational_park",
    "loc_mountain_lake": "loc_park_lake",
    "mountain lake & pier": "loc_park_lake",
    "loc_summit_lookout": "loc_hilltop_lookout",
    "mountain summit lookout": "loc_hilltop_lookout",
    "sub_mountain_lake_pier_entrance": "loc_park_lake",
    "sub_boat_dock": "loc_park_lake",
    "sub_lakeside_bench": "loc_park_lake",
    "sub_mountain_summit_lookout_entrance": "loc_hilltop_lookout",
    "sub_lookout_telescope": "loc_hilltop_lookout",
    "sub_ridge_trail": "loc_hilltop_lookout",
    "sub_grand_dusty_foyer_entrance": "loc_manor_foyer",
    "sub_winding_staircase": "loc_manor_foyer",
    "sub_fireplace_hearth": "loc_manor_foyer",
    "loc_manor_garden": "sub_manor_grounds",
    "sub_weeping_willow": "sub_manor_grounds",
    "sub_iron_gate": "sub_manor_grounds",
    "sub_adventurers_guild_hall_entrance": "loc_guild_hall_isekai",
    "sub_quest_board": "loc_guild_hall",
    "sub_guild_counter": "loc_guild_hall",
    "sub_cobblestone_market_plaza_entrance": "loc_market_district_isekai",
    "sub_blacksmith": "loc_market_district",
    "sub_alchemy_shop": "loc_market_district",
    "sub_general_store": "loc_market_district",
    "sub_imperial_palace_grounds_entrance": "loc_imperial_palace",
    "sub_royal_armory": "loc_imperial_palace",
    "sub_lumbermill_timber_camp_entrance": "loc_lumber_camp_isekai",
    "sub_log_staging": "loc_lumber_camp",
    "sub_hunters_trail_outpost_entrance": "loc_hunters_trail_isekai",
    "sub_trailhead_clearing": "loc_hunters_trail",
    "sub_hunter_campfire": "loc_hunters_trail",
    "sub_sunlit_forest_clearing_entrance": "loc_forest_clearing",
    "sub_grassy_meadow": "loc_forest_clearing",
    "sub_berry_bushes": "loc_forest_clearing",
    "sub_druidic_tree_sanctuary_entrance": "loc_forest_outpost",
    "sub_moonwell": "loc_forest_outpost",
    "sub_gnarled_root_archway_entrance": "loc_gnarled_archway_isekai",
    "sub_intertwined_arch": "loc_gnarled_archway",
    "sub_standing_stones": "loc_gnarled_archway",
    "sub_western_root_bridge": "loc_gnarled_archway",
    "sub_den_entrance": "loc_monster_lair",
    "sub_chieftain_tent": "loc_monster_lair",
    "sub_farming_village_entrance": "loc_farming_village_isekai",
    "sub_country_inn": "loc_farming_village",
    "sub_highland_windmills_entrance": "loc_grain_windmills",
    "sub_mill_grindstone": "loc_grain_windmills",
    "sub_granary_silo": "loc_grain_windmills",
    "sub_harbor_docks_quays_entrance": "loc_harbor_docks",
    "sub_pier_master": "loc_harbor_docks",
    "sub_merchant_galleon": "loc_harbor_docks",
    "sub_sailors_haven_tavern_entrance": "loc_sailor_tavern",
    "sub_rum_bar": "loc_sailor_tavern",
    "sub_gambling_table": "loc_sailor_tavern",
    "sub_great_gates": "loc_mountain_outpost",
    "sub_deep_forge": "loc_mountain_outpost",
    "sub_treacherous_mountain_pass_entrance": "loc_windy_pass",
    "sub_rope_bridge": "loc_windy_pass",
    "sub_cliff_cave": "loc_windy_pass",
    "sub_stilt_walker_settlement_entrance": "loc_stilt_village",
    "sub_stilt_pier": "loc_stilt_village",
    "sub_witch_hut": "loc_stilt_village",
    "sub_sunken_temple_ruins_entrance": "loc_sunken_ruins",
    "sub_submerged_altar": "loc_sunken_ruins",
    "sub_mossy_colonnade": "loc_sunken_ruins",
    "sub_palm_oasis_bazaar_entrance": "loc_oasis_bazaar_isekai",
    "sub_spring_pool": "loc_oasis_bazaar",
    "sub_nomad_tents": "loc_oasis_bazaar",
    "sub_tomb_entrance": "loc_buried_pyramid",
    "sub_hieroglyph_chamber": "loc_buried_pyramid",
    "sub_frontier_hunter_camp_entrance": "loc_tundra_camp",
    "sub_meat_rack": "loc_tundra_camp",
    "sub_glacial_ice_caverns_entrance": "loc_ice_cavern",
    "sub_frozen_chasm": "loc_ice_cavern",
    "sub_obsidian_watchpost_entrance": "loc_ash_outpost",
    "sub_magma_overlook": "loc_ash_outpost",
    "sub_reinforced_bunker": "loc_ash_outpost",
    "sub_great_caldera_crater_entrance": "loc_caldera_core",
    "sub_lava_lake": "loc_caldera_core",
    "sub_fire_elemental_spire": "loc_caldera_core",
    "sub_necromancers_ruined_keep_entrance": "loc_blighted_keep",
    "sub_dark_altar": "loc_blighted_keep",
    "sub_bone_crypt": "loc_blighted_keep",
    "sub_deep_underworld_enclave_entrance": "loc_subterranean_city",
    "sub_fungal_bazaar": "loc_subterranean_city",
    "sub_stalactite_haven": "loc_subterranean_city",
    "sub_dungeon_grand_antechamber_entrance": "loc_dungeon_antechamber",
    "sub_iron_gate_entrance": "loc_dungeon_antechamber",
    "sub_adventurer_camp": "loc_dungeon_antechamber",
    "sub_depths_boss_chamber_entrance": "loc_boss_chamber",
    "sub_treasury_chest": "loc_boss_chamber",
    "sub_boss_dais": "loc_boss_chamber",
    "sub_crystal_geode_grotto_entrance": "loc_crystal_grotto",
    "sub_geode_cluster": "loc_crystal_grotto",
    "sub_subterranean_river": "loc_crystal_grotto",
    "sub_quest_board_isekai": "loc_guild_hall_isekai",
    "sub_guild_counter_isekai": "loc_guild_hall_isekai",
    "sub_guild_tavern_isekai": "loc_guild_hall_isekai",
    "sub_royal_summoning_chamber_entrance": "loc_summoning_chamber",
    "sub_summoning_circle": "loc_summoning_chamber",
    "sub_priestess_altar": "loc_summoning_chamber",
    "sub_blacksmith_isekai": "loc_market_district_isekai",
    "sub_alchemy_shop_isekai": "loc_market_district_isekai",
    "sub_sawmill_shed_isekai": "loc_lumber_camp_isekai",
    "sub_log_staging_isekai": "loc_lumber_camp_isekai",
    "sub_trailhead_clearing_isekai": "loc_hunters_trail_isekai",
    "sub_hunter_campfire_isekai": "loc_hunters_trail_isekai",
    "sub_elven_tree_sanctuary_entrance": "loc_elven_sanctuary_isekai",
    "sub_moonwell_isekai": "loc_elven_sanctuary_isekai",
    "sub_elder_hollow_isekai": "loc_elven_sanctuary_isekai",
    "sub_intertwined_arch_isekai": "loc_gnarled_archway_isekai",
    "sub_western_root_bridge_isekai": "loc_gnarled_archway_isekai",
    "sub_village_square_isekai": "loc_farming_village_isekai",
    "sub_country_inn_isekai": "loc_farming_village_isekai",
    "sub_great_gates_isekai": "loc_mountain_outpost_isekai",
    "sub_deep_forge_isekai": "loc_mountain_outpost_isekai",
    "sub_spring_pool_isekai": "loc_oasis_bazaar_isekai",
    "sub_spiked_barricade": "loc_demon_outpost",
    "sub_blood_portal": "loc_demon_outpost",
    "sub_10th_floor_safe_zone_entrance": "loc_dungeon_safe_zone",
    "sub_teleport_crystal": "loc_dungeon_safe_zone",
    "sub_torturers_dungeon_keep_entrance": "loc_dungeon_keep",
    "sub_oubliette": "loc_dungeon_keep",
    "sub_shattered_stained_glass_nave_entrance": "loc_stained_nave",
    "sub_desecrated_pulpit": "loc_stained_nave",
    "sub_relic_vault": "loc_stained_nave",
    "sub_sunken_bone_chapel_entrance": "loc_bone_chapel",
    "sub_sacrifice_altar": "loc_bone_chapel",
    "sub_catacombs": "loc_bone_chapel",
    "sub_witch_tree_coven_hollow_entrance": "loc_witch_coven",
    "sub_effigy_grove": "loc_witch_coven",
    "sub_bog_hut": "loc_witch_coven",
    "sub_the_weeping_hound_tavern_entrance": "loc_grim_tavern",
    "sub_dark_hearth": "loc_grim_tavern",
    "sub_mercenary_corner": "loc_grim_tavern",
    "sub_hanging_tree_square_entrance": "loc_town_square",
    "sub_gibbet_tree": "loc_town_square",
    "sub_plague_cart": "loc_town_square",
    "sub_grand_ossuary_hall_entrance": "loc_ossuary_hall",
    "sub_skull_pillar": "loc_ossuary_hall",
    "sub_sealed_sarcophagus": "loc_ossuary_hall",
    "sub_ruined_sentinel_watchpost_entrance": "loc_crag_watchpost",
    "sub_signal_beacon": "loc_crag_watchpost",
    "sub_gibbet_cliff": "loc_crag_watchpost",
    "sub_heretic_altar": "loc_cathedral_ruins",
    "sub_crypt_entrance": "loc_cathedral_ruins",
    "sub_corrupted_hunter_encampment_entrance": "loc_cannibal_camp",
    "sub_bone_totem": "loc_cannibal_camp",
    "sub_gutting_trough": "loc_cannibal_camp",
    "sub_blast_door_console": "loc_vault_airlock",
    "sub_decon_chamber": "loc_vault_airlock",
    "sub_overseers_command_office_entrance": "loc_overseer_office",
    "sub_terminal_desk": "loc_overseer_office",
    "sub_security_lockbox": "loc_overseer_office",
    "sub_barter_market_plaza_entrance": "loc_scavenger_bazaar",
    "sub_water_purifier": "loc_scavenger_bazaar",
    "sub_barter_stand": "loc_scavenger_bazaar",
    "sub_weapon_tinkerer": "loc_scavenger_bazaar",
    "sub_rusty_canteen_saloon_entrance": "loc_saloon",
    "sub_oil_drum_bar": "loc_saloon",
    "sub_gambling_corner": "loc_saloon",
    "sub_ground_zero_crater_rim_entrance": "loc_ground_zero",
    "sub_slurry_pool": "loc_ground_zero",
    "sub_shattered_warhead": "loc_ground_zero",
    "sub_highway_overpass_outpost_entrance": "loc_overpass_camp",
    "sub_sniper_nest": "loc_overpass_camp",
    "sub_wrecked_bus": "loc_overpass_camp",
    "sub_subway_car": "loc_subway_terminal",
    "sub_ticket_hall": "loc_subway_terminal",
    "sub_scrap_metal_gladiator_pit_entrance": "loc_gladiator_pit",
    "sub_overboss_throne": "loc_gladiator_pit",
    "sub_arena_cage": "loc_gladiator_pit",
    "sub_submerged_refinery_rig_entrance": "loc_refinery_rig",
    "sub_pipe_walkway": "loc_refinery_rig",
    "sub_valve_station": "loc_refinery_rig",
    "sub_lobby_security": "loc_corp_tower",
    "sub_exec_boardroom": "loc_corp_tower",
    "sub_sky_high_vip_lounge_entrance": "loc_sky_lounge",
    "sub_bar_terrace": "loc_sky_lounge",
    "sub_helipad": "loc_sky_lounge",
    "sub_commercial_plaza_center_entrance": "loc_downtown_plaza",
    "sub_holo_fountain": "loc_downtown_plaza",
    "sub_cyber_store": "loc_downtown_plaza",
    "sub_neon_pulse_nightclub_entrance": "loc_nightclub",
    "sub_dance_floor": "loc_nightclub",
    "sub_vip_booth": "loc_nightclub",
    "sub_luxury_penthouse_suite_entrance": "loc_luxury_penthouse",
    "sub_penthouse_balcony": "loc_luxury_penthouse",
    "sub_private_bar": "loc_luxury_penthouse",
    "sub_street_noodle_bar_entrance": "loc_noodle_bar",
    "sub_bar_counter": "loc_noodle_bar",
    "sub_ripperdoc_clinic_entrance": "loc_ripperdoc_clinic",
    "sub_operating_chair": "loc_ripperdoc_clinic",
    "sub_parts_storage": "loc_ripperdoc_clinic",
    "sub_backstreet_neon_alley_entrance": "loc_neon_alley",
    "sub_dumpster": "loc_neon_alley",
    "sub_smuggler_van": "loc_neon_alley",
    "sub_safehouse_entry": "loc_player_safehouse",
    "sub_safehouse_bed": "loc_player_safehouse",
    "sub_safehouse_couch": "loc_player_safehouse",
    "sub_automated_cargo_terminal_entrance": "loc_cargo_dock",
    "sub_container_stack": "loc_cargo_dock",
    "sub_crane_control": "loc_cargo_dock",
    "sub_nomad_clan_encampment_entrance": "loc_nomad_camp",
    "sub_comm_radio_tower": "loc_nomad_camp",
    "sub_highway_roadside_diner_entrance": "loc_rural_diner",
    "sub_diner_booth": "loc_rural_diner",
    "sub_jukebox": "loc_rural_diner",
    "sub_bio_dome_central_pavilion_entrance": "loc_dome_pavilion",
    "sub_waterfall_deck": "loc_dome_pavilion",
    "sub_research_kiosk": "loc_dome_pavilion",
    "sub_airship_docking_terminal_entrance": "loc_aerodrome",
    "sub_airship_dock": "loc_aerodrome",
    "sub_ticket_booth": "loc_aerodrome",
    "sub_alchemists_guild_hall_entrance": "loc_alchemist_guild",
    "sub_brewing_station": "loc_alchemist_guild",
    "sub_archive_library": "loc_alchemist_guild",
    "sub_mechanists_archive_vaults_entrance": "loc_mechanist_vaults",
    "sub_blueprint_hall": "loc_mechanist_vaults",
    "sub_pneumatic_tube_hub": "loc_mechanist_vaults",
    "sub_command_bridge_pilot_helm_entrance": "loc_airship_bridge",
    "sub_helm_wheel": "loc_airship_bridge",
    "sub_engine_telegraph": "loc_airship_bridge",
    "sub_nav_table": "loc_airship_bridge",
    "sub_panoramic_observation_deck_entrance": "loc_observation_deck",
    "sub_glass_deck_railing": "loc_observation_deck",
    "sub_lounge_armchairs": "loc_observation_deck",
    "sub_engine_boiler_room_entrance": "loc_airship_engine_room",
    "sub_steam_piston_core": "loc_airship_engine_room",
    "sub_pressure_valves": "loc_airship_engine_room",
    "sub_grand_passenger_salon_dining_hall_entrance": "loc_passenger_salon",
    "sub_dining_table": "loc_passenger_salon",
    "sub_airship_bar": "loc_passenger_salon",
    "sub_cargo_bay_armory_hold_entrance": "loc_cargo_armory",
    "sub_harpoon_cannon": "loc_cargo_armory",
    "sub_cargo_crane": "loc_cargo_armory",
    "sub_bow_lookout_platform_entrance": "loc_bow_lookout",
    "sub_spotlight_rig": "loc_bow_lookout",
    "sub_windscreen_perch": "loc_bow_lookout",
    "sub_stateroom_entry": "loc_airship_quarters",
    "sub_captain_berth": "loc_airship_quarters",
    "sub_officer_divan": "loc_airship_quarters",
    "sub_inventors_society_club_entrance": "loc_gentlemans_club",
    "sub_smoking_room": "loc_gentlemans_club",
    "sub_exhibit_hall": "loc_gentlemans_club",
    "sub_great_blast_furnace_entrance": "loc_furnace_complex",
    "sub_lower_valve_basin": "loc_furnace_complex",
    "sub_furnace_core": "loc_furnace_complex",
    "sub_hidden_waterway_pier_entrance": "loc_smuggler_dock",
    "sub_clandestine_dock": "loc_smuggler_dock",
    "sub_contraband_depot": "loc_smuggler_dock",
    "sub_scrap_titan_graveyard_entrance": "loc_scrap_graveyard",
    "sub_titan_cockpit": "loc_scrap_graveyard",
    "sub_salvager_camp": "loc_scrap_graveyard",
    "sub_abandoned_coal_mine_colliery_entrance": "loc_moor_mine",
    "sub_engine_shed": "loc_moor_mine",
    "sub_trading_kiosk": "loc_station_promenade",
    "sub_security_checkpoint": "loc_station_promenade",
    "sub_player_ship": "loc_ship_dock",
    "sub_refueling_station": "loc_ship_dock",
    "sub_command_bridge_entrance": "loc_bridge",
    "sub_captains_chair": "loc_bridge",
    "sub_helm_console": "loc_bridge",
    "sub_engineering_bay_entrance": "loc_engineering",
    "sub_hyperdrive_core": "loc_engineering",
    "sub_workbench": "loc_engineering",
    "sub_quarters_entry": "loc_crew_quarters",
    "sub_captain_bunk": "loc_crew_quarters",
    "sub_crew_rec_couch": "loc_crew_quarters",
    "sub_planetary_senate_plaza_entrance": "loc_senate_plaza",
    "sub_senate_chamber": "loc_senate_plaza",
    "sub_diplomatic_lounge": "loc_senate_plaza",
    "sub_planetary_gateway_spaceport_entrance": "loc_spaceport_central",
    "sub_customs_terminal": "loc_spaceport_central",
    "sub_freighter_pad": "loc_spaceport_central",
    "sub_crawler_mining_outpost_entrance": "loc_mining_outpost",
    "sub_harvester_deck": "loc_mining_outpost",
    "sub_moisture_vault": "loc_mining_outpost",
    "sub_cryo_research_station_entrance": "loc_research_base",
    "sub_thermal_dome": "loc_research_base",
    "sub_ice_drill": "loc_research_base",
    "sub_canopy_research_platform_entrance": "loc_canopy_platform",
    "sub_observation_kiosk": "loc_canopy_platform",
    "sub_ropeway_gondola": "loc_canopy_platform",
    "sub_geothermal_core_refinery_entrance": "loc_core_refinery",
    "sub_lava_catwalk": "loc_core_refinery",
    "sub_extraction_core": "loc_core_refinery",
    "sub_floating_platform_city_entrance": "loc_floating_platform",
    "sub_submersible_dock": "loc_floating_platform",
    "sub_open_deck": "loc_floating_platform",
    "sub_hollow_asteroid_hab_entrance": "loc_asteroid_colony",
    "sub_zero_g_dock": "loc_asteroid_colony",
    "sub_miner_cantina": "loc_asteroid_colony",
    "sub_roastery_artisanal_caf\u00e9_entrance": "loc_sol_roastery",
    "sub_sol_window_booth": "loc_sol_roastery",
    "sub_sol_espresso_bar": "loc_sol_roastery",
    "sub_sol_patio_terrace": "loc_sol_roastery",
    "sub_secondhand_bookstore_vinyl_shop_entrance": "loc_sol_bookstore",
    "sub_sol_listening_station": "loc_sol_bookstore",
    "sub_sol_rare_stacks": "loc_sol_bookstore",
    "sub_late_night_ramen_izakaya_counter_entrance": "loc_sol_ramen_counter",
    "sub_sol_chef_bar": "loc_sol_ramen_counter",
    "sub_sol_back_tatami": "loc_sol_ramen_counter",
    "sub_creative_studio_co_working_loft_entrance": "loc_sol_cowork_loft",
    "sub_sol_editing_desk": "loc_sol_cowork_loft",
    "sub_sol_rooftop_lounge": "loc_sol_cowork_loft",
    "sub_walk_up_studio_apartments_entrance": "loc_sol_studio_apt",
    "sub_sol_player_studio": "loc_sol_studio_apt",
    "sub_sol_exterior_balcony": "loc_sol_studio_apt",
    "sub_24_hour_corner_convenience_store_entrance": "loc_sol_konbini",
    "sub_sol_magazine_rack": "loc_sol_konbini",
    "sub_sol_parking_curb": "loc_sol_konbini",
    "sub_neighborhood_coin_laundry_entrance": "loc_sol_coin_laundry",
    "sub_sol_dryer_row": "loc_sol_coin_laundry",
    "sub_sol_vending_bench": "loc_sol_coin_laundry",
    "sub_local_hilltop_shrine_park_entrance": "loc_sol_hilltop_shrine",
    "sub_sol_city_overlook": "loc_sol_hilltop_shrine",
    "sub_basement_jazz_cocktail_bar_entrance": "loc_sol_jazz_bar",
    "sub_sol_mahogany_bar": "loc_sol_jazz_bar",
    "sub_sol_velvet_stage": "loc_sol_jazz_bar",
    "sub_underground_indie_live_house_entrance": "loc_sol_live_house",
    "sub_sol_crowd_floor": "loc_sol_live_house",
    "sub_sol_green_room": "loc_sol_live_house",
    "sub_24_hour_arcade_billiards_hall_entrance": "loc_sol_billiards_arcade",
    "sub_sol_pool_tables": "loc_sol_billiards_arcade",
    "sub_sol_fighting_cabs": "loc_sol_billiards_arcade",
    "sub_neighborhood_boxing_martial_arts_gym_entrance": "loc_sol_boxing_gym",
    "sub_sol_sparring_ring": "loc_sol_boxing_gym",
    "sub_sol_heavy_bags": "loc_sol_boxing_gym",
    "sub_neon_back_alley_entrance": "loc_sol_neon_alley",
    "sub_sol_dead_end": "loc_sol_neon_alley",
    "sub_waterfront_boardwalk_night_market_entrance": "loc_sol_boardwalk",
    "sub_sol_sea_railing": "loc_sol_boardwalk",
    "sub_sol_food_stalls": "loc_sol_boardwalk",
    "sub_sol_busker_fountain": "loc_sol_transit_plaza",
    "sub_sol_ticket_concourse": "loc_sol_transit_plaza",
    "sub_sol_padlocked_gate": "loc_sol_warehouse_pier",
    "sub_sol_shipping_containers": "loc_sol_warehouse_pier",
    "sub_sol_warehouse_interior": "loc_sol_warehouse_pier",
    "sub_jazz_counter": "loc_downtown_jazz_bar",
    "sub_jazz_vip_booth": "loc_downtown_jazz_bar",
    "sub_ramen_lanterns": "loc_downtown_ramen_alley",
    "sub_ramen_stall": "loc_downtown_ramen_alley",
    "sub_izakaya_patio": "loc_downtown_ramen_alley",
    "sub_conservatory_foyer": "loc_botanical_zoo",
    "sub_conservatory_canopy": "loc_botanical_zoo",
    "sub_conservatory_nightshade": "loc_botanical_zoo",
    "sub_dive_door": "loc_rusty_pipe_bar",
    "sub_dive_counter": "loc_rusty_pipe_bar",
    "sub_dive_alley": "loc_rusty_pipe_bar",
    "sub_konbini_doors": "loc_suburb_konbini",
    "sub_konbini_parking": "loc_suburb_konbini",
    "sub_laundry_door": "loc_suburb_laundry",
    "sub_laundry_vending": "loc_suburb_laundry",
    "sub_rooftop_stairwell": "loc_school_rooftop",
    "sub_rooftop_fence": "loc_school_rooftop",
    "sub_rooftop_water_tank": "loc_school_rooftop",
    "sub_beach_cafe_deck": "loc_seaside_cafe",
    "sub_beach_cafe_bar": "loc_seaside_cafe",
    "sub_surf_rental": "loc_seaside_cafe",
    "sub_tp_turnstiles": "loc_tp_main_midway",
    "sub_tp_prize_alley": "loc_tp_main_midway",
    "sub_tp_food_plaza": "loc_tp_main_midway",
    "sub_tp_coaster_queue": "loc_tp_coaster_plaza",
    "sub_tp_launch_track": "loc_tp_coaster_plaza",
    "sub_tp_photo_kiosk": "loc_tp_coaster_plaza",
    "sub_tp_wheel_deck": "loc_tp_ferris_wheel",
    "sub_tp_glass_gondola": "loc_tp_ferris_wheel",
    "sub_tp_wheel_motor_room": "loc_tp_ferris_wheel",
    "sub_tp_cabana_entry": "loc_tp_water_lagoon",
    "sub_tp_wave_pool": "loc_tp_water_lagoon",
    "sub_tp_lazy_river": "loc_tp_water_lagoon",
    "sub_tp_mansion_foyer": "loc_tp_haunted_mansion",
    "sub_tp_doom_buggy_track": "loc_tp_haunted_mansion",
    "sub_tp_backstage_catwalk": "loc_tp_haunted_mansion",
    "sub_tp_mirror_curtain": "loc_tp_mirror_labyrinth",
    "sub_tp_delayed_glass": "loc_tp_mirror_labyrinth",
    "sub_tp_inverted_midway": "loc_tp_mirror_labyrinth",
    "sub_tp_carousel_gate": "loc_tp_midnight_carousel",
    "sub_tp_porcelain_steeds": "loc_tp_midnight_carousel",
    "sub_tp_calliope_core": "loc_tp_midnight_carousel",
    "sub_et_torii_steps": "loc_et_torii_approach",
    "sub_et_chozuya": "loc_et_torii_approach",
    "sub_et_talisman_counter": "loc_et_torii_approach",
    "sub_et_incense_courtyard": "loc_et_main_sanctuary",
    "sub_et_deity_altar": "loc_et_main_sanctuary",
    "sub_et_exorcist_quarters": "loc_et_main_sanctuary",
    "sub_et_pagoda_doors": "loc_et_five_story_pagoda",
    "sub_et_sutra_library": "loc_et_five_story_pagoda",
    "sub_et_pagoda_reliquary": "loc_et_five_story_pagoda",
    "sub_et_bamboo_gate": "loc_et_zen_tea_garden",
    "sub_et_matcha_tatami": "loc_et_zen_tea_garden",
    "sub_et_koi_bridge": "loc_et_zen_tea_garden",
    "sub_et_onsen_noren": "loc_et_onsen_bathhouse",
    "sub_et_cypress_bath": "loc_et_onsen_bathhouse",
    "sub_et_rotenburo": "loc_et_onsen_bathhouse",
    "sub_et_shimenawa_cordon": "loc_et_weeping_statues",
    "sub_et_jizo_labyrinth": "loc_et_weeping_statues",
    "sub_et_blood_altar": "loc_et_weeping_statues",
    "sub_et_kitsune_gate": "loc_et_fox_torii_tunnel",
    "sub_et_endless_torii": "loc_et_fox_torii_tunnel",
    "sub_et_spirit_sanctum": "loc_et_fox_torii_tunnel",
    "sub_hosp_er_doors": "loc_hosp_emergency_triage",
    "sub_hosp_trauma_bay": "loc_hosp_emergency_triage",
    "sub_hosp_pharmacy": "loc_hosp_emergency_triage",
    "sub_hosp_nurses_station": "loc_hosp_inpatient_wing",
    "sub_hosp_private_room": "loc_hosp_inpatient_wing",
    "sub_hosp_rooftop_garden": "loc_hosp_inpatient_wing",
    "sub_hosp_psych_airlock": "loc_hosp_psych_ward",
    "sub_hosp_cognitive_rooms": "loc_hosp_psych_ward",
    "sub_hosp_therapy_lounge": "loc_hosp_psych_ward",
    "sub_hosp_morgue_vestibule": "loc_hosp_morgue",
    "sub_hosp_cold_lockers": "loc_hosp_morgue",
    "sub_hosp_autopsy_suite": "loc_hosp_morgue",
    "sub_hosp_welded_stairs": "loc_hosp_floor_13",
    "sub_hosp_iv_corridor": "loc_hosp_floor_13",
    "sub_hosp_patient_zero": "loc_hosp_floor_13",
    "sub_hosp_scrub_room": "loc_hosp_theater_zero",
    "sub_hosp_surgical_pit": "loc_hosp_theater_zero",
    "sub_hosp_shadow_gallery": "loc_hosp_theater_zero",
    "sub_ct_herb_counter": "loc_ct_herbal_apothecary",
    "sub_ct_thousand_drawers": "loc_ct_herbal_apothecary",
    "sub_ct_elixir_backroom": "loc_ct_herbal_apothecary",
    "sub_bz_dome_rotunda": "loc_bz_glass_biodomes",
    "sub_bz_canopy_walk": "loc_bz_glass_biodomes",
    "sub_bz_orchid_pavilion": "loc_bz_glass_biodomes",
    "sub_bz_aquarium_foyer": "loc_bz_abyssal_aquarium",
    "sub_bz_shark_tunnel": "loc_bz_abyssal_aquarium",
    "sub_bz_jellyfish_hall": "loc_bz_abyssal_aquarium",
    "sub_bz_zoo_gates": "loc_bz_nocturnal_zoo",
    "sub_bz_predator_overlook": "loc_bz_nocturnal_zoo",
    "sub_bz_geodesic_aviary": "loc_bz_nocturnal_zoo",
    "sub_bz_terrace_pergola": "loc_bz_terrace_gift_cafe",
    "sub_bz_plush_shop": "loc_bz_terrace_gift_cafe",
    "sub_bz_garden_cafe": "loc_bz_terrace_gift_cafe",
    "sub_bz_airlock_breach": "loc_bz_carnivorous_dome",
    "sub_bz_mimic_canopy": "loc_bz_carnivorous_dome",
    "sub_bz_corpse_flower": "loc_bz_carnivorous_dome",
    "sub_bz_sublevel_bulkhead": "loc_bz_tank_nine",
    "sub_bz_ballistic_glass": "loc_bz_tank_nine",
    "sub_bz_impossible_trench": "loc_bz_tank_nine",
}


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

    alias_id = _LEGACY_NODE_ID_ALIASES.get(loc_clean.lower())
    if alias_id:
        aliased = get_world_node(session_id, alias_id)
        if aliased:
            return aliased["node_id"]

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
                if "homeroom" in leaf_name:
                    child = next((rn for rn in nodes if rn.get("parent_id") == prim_node["node_id"] and rn["node_id"] == "loc_homeroom"), None)
                    if child:
                        return child["node_id"]
        return prim_node["node_id"]

    # 2b. Check if prim_name (middle tier of legacy 3-part string e.g. 'Zone ➔ Room ➔ Prop') matches a ROOM node directly
    if prim_name and len(parts) >= 2:
        for n in nodes:
            if n.get("node_type") == "ROOM" and n["name"].lower() == prim_name:
                return n["node_id"]
        if "homeroom" in prim_name:
            hr = next((n for n in nodes if n["node_id"] == "loc_homeroom"), None)
            if hr:
                return hr["node_id"]
        for n in nodes:
            if n.get("node_type") == "ROOM" and len(prim_name) >= 4 and (prim_name in n["name"].lower() or n["name"].lower() in prim_name):
                return n["node_id"]

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

    node_ids_set = {n["node_id"] for n in nodes}
    if from_node_id not in node_ids_set and from_node_id in _LEGACY_NODE_ID_ALIASES:
        from_node_id = _LEGACY_NODE_ID_ALIASES[from_node_id]
    if to_node_id not in node_ids_set and to_node_id in _LEGACY_NODE_ID_ALIASES:
        to_node_id = _LEGACY_NODE_ID_ALIASES[to_node_id]
    if from_node_id == to_node_id:
        return 2

    adj = defaultdict(list)
    for e in edges:
        u = e.get("from_node_id")
        v = e.get("to_node_id")
        w = max(1, int(e.get("travel_minutes") or 2))
        if u and v:
            adj[u].append((v, w))
            if e.get("is_bidirectional", 1):
                adj[v].append((u, w))

    _mega_complex_ids = {
        "loc_agency_hq", "loc_private_hq_1", "loc_private_hq_2",
        "loc_general_hospital", "loc_theme_park", "loc_eastern_temple",
        "loc_botanical_zoo", "loc_cult_sanctum_hq", "loc_clandestine_syndicate_hq",
    }
    # Add implicit parent-child transitions (1 minute between facility and room; or zone if directly queried)
    for n in nodes:
        pid = n.get("parent_id")
        nid = n.get("node_id")
        if pid and nid:
            if (n.get("node_type") == "ROOM" and pid not in _mega_complex_ids) or pid in (from_node_id, to_node_id):
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



