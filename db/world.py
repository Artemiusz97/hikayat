from __future__ import annotations

import db
import json
import logging
import time
import re
import heapq
from collections import defaultdict
from contextlib import nullcontext
from typing import Any
from .core import *
from .core import _to_str, _find_anomalous_agent_entry

log = logging.getLogger(__name__)

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
            if not gender and session_id:
                try:
                    p_gen = db.get_session_player_gender(session_id)
                    from scenario_data import should_skew_female_npcs
                    if should_skew_female_npcs(scen, p_gen):
                        import random
                        gender = "female" if random.random() < (2.0 / 3.0) else "male"
                except Exception:
                    pass
            name = matched_name or namegen.generate_person_name(scen, gender=gender)
            if role_title.lower() not in (description or "").lower():
                description = f"{role_title} — {description or ''}".strip(" —")

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id, race, appearance_json, status, gender FROM lorebook WHERE session_id=? AND lower(name)=lower(?)",
            (session_id, name)).fetchone()
        if existing:
            existing_race = existing["race"]
            canonical_gender = ""
            canonical_race = ""
            if entity_type.lower() == "person" and name:
                name_low = str(name).strip().lower()
                npc_slug = name_low.replace(" ", "_")
                try:
                    sd_row = conn.execute(
                        "SELECT gender, race FROM school_directory WHERE session_id=? AND (lower(name)=? OR npc_id=?) LIMIT 1",
                        (session_id, name_low, npc_slug)
                    ).fetchone()
                    if sd_row:
                        if sd_row["gender"] and str(sd_row["gender"]).strip().lower() not in ("", "unknown", "none"):
                            canonical_gender = str(sd_row["gender"]).strip().lower()
                        if sd_row["race"] and str(sd_row["race"]).strip().lower() not in ("", "unknown", "none"):
                            canonical_race = str(sd_row["race"]).strip()
                except Exception:
                    pass
                if not canonical_gender or not canonical_race:
                    try:
                        ar_row = _find_anomalous_agent_entry(conn, session_id, name_low, npc_slug)
                        if ar_row:
                            if not canonical_gender and ar_row.get("gender") and str(ar_row.get("gender")).strip().lower() not in ("", "unknown", "none"):
                                canonical_gender = str(ar_row.get("gender")).strip().lower()
                            if not canonical_race and ar_row.get("race") and str(ar_row.get("race")).strip().lower() not in ("", "unknown", "none"):
                                canonical_race = str(ar_row.get("race")).strip()
                    except Exception:
                        pass
            if canonical_race:
                existing_race = canonical_race
            existing_gender = str(existing["gender"] or "").strip()
            if canonical_gender:
                gender = canonical_gender
            elif existing_gender and existing_gender.lower() not in ("", "unknown", "none"):
                gender = existing_gender
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
    is_dynamic: int = 0,
    preferred_realm_id: str = "",
):
    """Upserts a discovered or seed location into the session map."""
    with UnitOfWork() as conn:
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
            with savepoint(conn, "sp_sync_spatial"):
                _sync_location_to_spatial_graph(
                    session_id, location_id, zone_name, primary_name, sub_name,
                    atmosphere=atmosphere, is_dynamic=is_dynamic,
                    preferred_realm_id=preferred_realm_id,
                )
        except Exception as exc:
            log.warning(
                "Spatial graph sync failed in save_session_location for session %s (%s): %s",
                session_id,
                location_id,
                exc,
            )
    return True

def format_node_tiered_location(
    session_id: int,
    node_id: str,
    fallback_zone: str = "World Region",
    conn: Any = None,
) -> str:
    """Formats a world_nodes node_id into its canonical 'Zone ➔ Facility ➔ Room' string in <1ms (role-based for variable depth)."""
    if not session_id or not node_id:
        return ""
    nodes = get_session_world_nodes(session_id, conn=conn)
    if not nodes:
        return ""
    node_map = {n["node_id"]: n for n in nodes}
    target = node_map.get(node_id)
    if not target:
        return ""
    from mechanics.world.locations.hierarchy import resolve_default_sublocation
    from mechanics.world.locations.realms import get_node_hierarchy_roles_in_memory

    roles = get_node_hierarchy_roles_in_memory(node_id, node_map)
    realm_node = roles.get("realm")
    zone_node = roles.get("zone")
    fac_node = roles.get("facility")
    n_type = str(target.get("node_type") or "ROOM").upper()

    if n_type == "REALM":
        first_zone = next((n for n in nodes if n.get("node_type") == "ZONE" and n.get("parent_id") == node_id), None)
        if first_zone:
            return format_node_tiered_location(session_id, first_zone["node_id"], fallback_zone=fallback_zone, conn=conn)
        first_fac = next((n for n in nodes if n.get("node_type") == "FACILITY" and n.get("parent_id") == node_id), None)
        if first_fac:
            return format_node_tiered_location(session_id, first_fac["node_id"], fallback_zone=fallback_zone, conn=conn)
        first_room = next((n for n in nodes if n.get("node_type") == "ROOM" and n.get("parent_id") == node_id), None)
        if first_room:
            return format_node_tiered_location(session_id, first_room["node_id"], fallback_zone=fallback_zone, conn=conn)
        r_name = target.get("name") or fallback_zone
        return f"{r_name} ➔ {r_name} ➔ Central Area"

    if n_type == "ZONE":
        z_name = target["name"]
        fac = next((n for n in nodes if n.get("node_type") == "FACILITY" and n.get("parent_id") == node_id), None)
        p_name = fac["name"] if fac else z_name
        child_room = next((n for n in nodes if n.get("node_type") == "ROOM" and n.get("parent_id") == (fac["node_id"] if fac else node_id) and (n.get("name") or "").strip().lower() != "main area"), None)
        s_name = child_room["name"] if child_room else resolve_default_sublocation(p_name, z_name, session_id=session_id)
        return f"{z_name} ➔ {p_name} ➔ {s_name}"

    if n_type == "FACILITY":
        z_name = zone_node["name"] if zone_node else (realm_node["name"] if realm_node else fallback_zone)
        p_name = target["name"]
        child_room = next((n for n in nodes if n.get("node_type") == "ROOM" and n.get("parent_id") == node_id and (n.get("name") or "").strip().lower() != "main area"), None)
        s_name = child_room["name"] if child_room else resolve_default_sublocation(p_name, z_name, session_id=session_id)
        return f"{z_name} ➔ {p_name} ➔ {s_name}"

    # ROOM node
    z_name = zone_node["name"] if zone_node else (realm_node["name"] if realm_node else (fac_node["name"] if fac_node else fallback_zone))
    p_name = fac_node["name"] if fac_node else (realm_node["name"] if realm_node else target["name"])
    s_name = target["name"]
    if not s_name or s_name.strip().lower() == "main area":
        s_name = resolve_default_sublocation(p_name, z_name, session_id=session_id)
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
    from mechanics.world.locations.realms import get_node_hierarchy_roles_in_memory
    node_map = {n["node_id"]: n for n in nodes}
    synthesized: list[dict] = []
    for n in nodes:
        if n.get("node_type") == "ROOM":
            roles = get_node_hierarchy_roles_in_memory(n["node_id"], node_map)
            zone = roles.get("zone")
            fac = roles.get("facility")
            realm = roles.get("realm")
            z_name = zone["name"] if zone else (realm["name"] if realm else "World Region")
            p_name = fac["name"] if fac else (realm["name"] if realm else n["name"])
            synthesized.append({
                "location_id": n["node_id"],
                "zone_name": z_name,
                "primary_name": p_name,
                "sub_name": n["name"],
                "atmosphere": n.get("atmosphere") or (fac.get("atmosphere") if fac else "") or "",
                "is_dynamic": int(n.get("is_dynamic") or 0),
            })
    return synthesized


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


_SCHOOL_CLUB_NODE_ID_FALLBACKS: dict[str, tuple[str, ...]] = {
    "loc_sports_club_facility": ("loc_school_athletics", "bld_school_athletics"),
    "sub_student_council": ("loc_student_council",),
    "loc_auditorium": ("loc_auditorium_stage",),
    "sub_old_storage_3b": ("loc_old_storage_3b",),
    "sub_occult_clubroom": ("loc_old_storage_3b",),
    "sub_custodian_boiler_locker": ("loc_delinquent_boiler_den",),
    "sub_gym_foyer": ("loc_athletics_foyer",),
    "sub_gym_court": ("loc_gymnasium",),
}


def _resolve_school_fallback_row(conn, session_id: int, node_id: str, select_cols: str = "*"):
    candidates = _SCHOOL_CLUB_NODE_ID_FALLBACKS.get(str(node_id or "").lower())
    if not candidates:
        return None, ""
    for cand in candidates:
        row = conn.execute(
            f"SELECT {select_cols} FROM world_nodes WHERE session_id = ? AND node_id = ?",
            (session_id, cand),
        ).fetchone()
        if row:
            return row, cand
    return None, ""


def get_world_node(session_id: int, node_id: str, conn: Any = None) -> dict | None:
    """Retrieves a single world_node row by node_id."""
    if not node_id:
        return None
    ctx = nullcontext(conn) if conn is not None else get_conn()
    with ctx as c:
        row = c.execute(
            "SELECT * FROM world_nodes WHERE session_id = ? AND node_id = ?",
            (session_id, node_id)
        ).fetchone()
        if not row and node_id in _LEGACY_NODE_ID_ALIASES:
            row = c.execute(
                "SELECT * FROM world_nodes WHERE session_id = ? AND node_id = ?",
                (session_id, _LEGACY_NODE_ID_ALIASES[node_id])
            ).fetchone()
        if not row:
            row, _ = _resolve_school_fallback_row(c, session_id, node_id, select_cols="*")
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
        if not row:
            row, _ = _resolve_school_fallback_row(conn, session_id, node_id, select_cols="state_json")
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
    with UnitOfWork() as conn:
        target_id = node_id
        row = conn.execute(
            "SELECT state_json FROM world_nodes WHERE session_id = ? AND node_id = ?",
            (session_id, node_id),
        ).fetchone()
        if row is None and node_id in _LEGACY_NODE_ID_ALIASES:
            target_id = _LEGACY_NODE_ID_ALIASES[node_id]
            row = conn.execute(
                "SELECT state_json FROM world_nodes WHERE session_id = ? AND node_id = ?",
                (session_id, target_id),
            ).fetchone()
        elif row is None:
            fb_row, fb_id = _resolve_school_fallback_row(conn, session_id, node_id, select_cols="state_json")
            if fb_row and fb_id:
                target_id = fb_id
                row = fb_row
        cur_state: dict = {}
        if row and row["state_json"]:
            try:
                cur_state = json.loads(row["state_json"]) if isinstance(row["state_json"], str) else dict(row["state_json"])
            except Exception:
                cur_state = {}
        cur_state.update(updates or {})
        conn.execute(
            "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
            (json.dumps(cur_state), session_id, target_id),
        )
    return cur_state


def get_world_node_props_state(session_id: int, node_id: str) -> dict[str, dict]:
    """Retrieves sparse props_state dictionary for a node from world_nodes.state_json."""
    st = get_world_node_state(session_id, node_id)
    props_st = st.get("props_state")
    if isinstance(props_st, dict):
        return props_st
    return {}


def update_world_node_prop_delta(session_id: int, node_id: str, prop_name: str, delta: dict) -> dict:
    """Merges a delta into props_state for a prop in world_nodes.state_json.
    Normalizes prop key via _slugify to prevent casing and whitespace desynchronization.
    """
    if not session_id or not node_id or not prop_name:
        return {}
    from mechanics.world.locations.seeds import slugify_location
    prop_key = slugify_location(prop_name)
    with UnitOfWork():
        cur_state = get_world_node_state(session_id, node_id)
        props_state = dict(cur_state.get("props_state") or {})
        prop_cur = dict(props_state.get(prop_key) or {})
        prop_cur.update(delta or {})
        props_state[prop_key] = prop_cur
        cur_state["props_state"] = props_state
        update_world_node_state(session_id, node_id, cur_state)
    return prop_cur


def get_session_schema_epoch(session_id: int) -> int:
    """Returns the schema_epoch for a session.
    If the session exists in DB and has schema_epoch set, returns it.
    If no session row exists (e.g. synthetic test session), defaults to 2 (current epoch).
    """
    if not session_id:
        return 2
    with get_conn() as conn:
        row = conn.execute("SELECT schema_epoch FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is not None:
            return int(row["schema_epoch"] or 1)
    return 2


def set_session_schema_epoch(session_id: int, epoch: int = 2) -> None:
    """Sets schema_epoch for a session."""
    if not session_id:
        return
    with get_conn() as conn:
        conn.execute("UPDATE sessions SET schema_epoch = ? WHERE id = ?", (epoch, session_id))


def get_session_world_nodes(session_id: int, conn: Any = None) -> list[dict]:
    """Retrieves all spatial graph nodes for a session ordered by hierarchy."""
    ctx = nullcontext(conn) if conn is not None else get_conn()
    with ctx as c:
        rows = c.execute(
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
    is_dynamic: int = 0,
    preferred_realm_id: str = "",
):
    """Ensures a location saved to session_locations also exists in world_nodes and world_edges (scoped to realm)."""
    if not session_id or not zone_name or not primary_name:
        return
    existing_nodes = get_session_world_nodes(session_id)
    if not existing_nodes and not is_dynamic:
        # Initial bulk seed will seed the full graph
        return

    from mechanics.world.locations.seeds import slugify_location as _slugify
    from mechanics.world.locations.graph_seeder import (
        infer_node_category, infer_node_privacy,
        infer_is_enclosed, infer_is_transit_hub, infer_access_tier,
        infer_curfew_window
    )
    from mechanics.world.locations.realms import (
        get_node_realm_id_in_memory,
        get_primary_realm_in_memory,
    )

    nodes_by_id = {n["node_id"]: n for n in existing_nodes if n.get("node_id")}
    if location_id and str(location_id) in nodes_by_id:
        return
    eff_realm_id = str(preferred_realm_id or "").strip()
    has_realm_nodes = any(str(n.get("node_type") or "").upper() == "REALM" for n in existing_nodes)
    if not is_dynamic and eff_realm_id and has_realm_nodes and eff_realm_id not in nodes_by_id:
        return
    if not eff_realm_id:
        sess_row = db.get_session(session_id)
        curr_nid = str((sess_row or {}).get("current_node_id") or "").strip()
        if curr_nid and curr_nid in nodes_by_id:
            eff_realm_id = get_node_realm_id_in_memory(curr_nid, nodes_by_id)
    if not eff_realm_id:
        prim_r = get_primary_realm_in_memory(nodes_by_id)
        eff_realm_id = str(prim_r["node_id"]) if prim_r else ""

    def _in_eff_realm(n: dict) -> bool:
        if not eff_realm_id:
            return True
        return get_node_realm_id_in_memory(n["node_id"], nodes_by_id) == eff_realm_id

    realm_nodes = [n for n in existing_nodes if _in_eff_realm(n)]

    z_id = next((n["node_id"] for n in realm_nodes if n["node_type"] == "ZONE" and n["name"].lower() == zone_name.lower()), None)
    if not z_id:
        # Check if zone_name actually names a compact REALM itself
        matching_realm = next((n for n in existing_nodes if n["node_type"] == "REALM" and n["name"].lower() == zone_name.lower()), None)
        if matching_realm and (not eff_realm_id or matching_realm["node_id"] == eff_realm_id):
            z_id = matching_realm["node_id"]
    if not z_id:
        z_id = f"zone_dyn_{_slugify(zone_name)}"
        if z_id in nodes_by_id and not _in_eff_realm(nodes_by_id[z_id]) and eff_realm_id:
            z_id = f"zone_dyn_{_slugify(eff_realm_id)}_{_slugify(zone_name)}"
        z_cat = infer_node_category(z_id, "", zone_name)
        z_acc = infer_access_tier("ZONE", z_id, z_id, zone_name, z_cat)
        z_cs, z_ce = infer_curfew_window("ZONE", z_id, z_id, zone_name, z_cat)
        save_world_node(
            session_id=session_id, node_id=z_id, parent_id=eff_realm_id or None, name=zone_name,
            node_type="ZONE", category=z_cat,
            privacy_level="public", is_enclosed=0, is_transit_hub=1,
            access_tier=z_acc, curfew_start_min=z_cs, curfew_end_min=z_ce,
            atmosphere=atmosphere, is_dynamic=is_dynamic
        )
        nodes_by_id[z_id] = {"node_id": z_id, "parent_id": eff_realm_id or None, "node_type": "ZONE", "name": zone_name}

    p_id = next((n["node_id"] for n in realm_nodes if n["node_type"] == "FACILITY" and n["name"].lower() == primary_name.lower()), None)
    if not p_id:
        p_id = f"loc_dyn_{_slugify(zone_name)}_{_slugify(primary_name)}"
        if p_id in nodes_by_id and not _in_eff_realm(nodes_by_id[p_id]) and eff_realm_id:
            p_id = f"loc_dyn_{_slugify(eff_realm_id)}_{_slugify(zone_name)}_{_slugify(primary_name)}"
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
        # Link to sibling facilities in the same zone (5 mins) or same-realm hub (15 mins across zones)
        same_zone_facs = [n["node_id"] for n in realm_nodes if n["node_type"] == "FACILITY" and n.get("parent_id") == z_id and n["node_id"] != p_id]
        for sf_id in same_zone_facs[:3]:
            save_world_edge(session_id, p_id, sf_id, travel_minutes=5, edge_type="pathway", is_bidirectional=1)
        if not same_zone_facs:
            any_hub = next((n["node_id"] for n in realm_nodes if n["node_type"] == "FACILITY" and n.get("is_transit_hub")), None)
            if any_hub and any_hub != p_id:
                save_world_edge(session_id, p_id, any_hub, travel_minutes=15, edge_type="Cross-Zone", is_bidirectional=1)

    from mechanics.world.locations.hierarchy import resolve_default_sublocation
    s_clean = (sub_name or "").strip()
    if not s_clean or s_clean.lower() == "main area":
        s_clean = resolve_default_sublocation(primary_name, zone_name, session_id=session_id)
    r_id = next((n["node_id"] for n in realm_nodes if n["node_type"] == "ROOM" and n.get("parent_id") == p_id and n["name"].lower() == s_clean.lower()), None)
    if not r_id:
        r_id = location_id if str(location_id).startswith("sub_") else f"sub_dyn_{_slugify(primary_name)}_{_slugify(s_clean)}"
        if r_id in nodes_by_id and not _in_eff_realm(nodes_by_id[r_id]) and eff_realm_id:
            r_id = f"sub_dyn_{_slugify(eff_realm_id)}_{_slugify(primary_name)}_{_slugify(s_clean)}"
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
        sibling_rooms = [n["node_id"] for n in realm_nodes if n["node_type"] == "ROOM" and n.get("parent_id") == p_id and n["node_id"] != r_id]
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
    if not session_id or not node_id:
        return []
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM world_nodes WHERE session_id = ?",
            (session_id,),
        ).fetchall()
    by_id = {str(r["node_id"]): dict(r) for r in rows if r["node_id"]}

    def _lookup(nid: str) -> dict | None:
        if not nid:
            return None
        hit = by_id.get(nid)
        if hit is not None:
            return hit
        alias = _LEGACY_NODE_ID_ALIASES.get(nid)
        if alias and alias in by_id:
            return by_id[alias]
        for cand in _SCHOOL_CLUB_NODE_ID_FALLBACKS.get(str(nid).lower(), ()):
            if cand in by_id:
                return by_id[cand]
        return None

    ancestors: list[dict] = []
    curr = _lookup(node_id)
    visited: set[str] = set()
    while curr and curr.get("parent_id"):
        p_id = curr["parent_id"]
        if p_id in visited:
            break
        visited.add(p_id)
        p_node = _lookup(p_id)
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
    """Checks if the node itself or any of its non-zone/non-realm parent facilities is a transit hub."""
    if not session_id or not node_id:
        return False
    curr = get_world_node(session_id, node_id)
    if curr and curr.get("is_transit_hub"):
        return True
    ancestors = get_node_ancestors(session_id, node_id)
    return any(bool(a.get("is_transit_hub")) for a in ancestors if a.get("node_type") not in ("ZONE", "REALM"))


from .world_constants import _LEGACY_NODE_ID_ALIASES


def resolve_node_id_from_location(
    session_id: int,
    location_str: str,
    prefer_facility: bool = False,
    preferred_realm_id: str | None = None,
) -> str | None:
    """
    Deterministically resolves a location string (e.g. 3-tier string, primary name,
    leaf name, or raw node_id) to its corresponding node_id in the session's spatial graph.
    If prefer_facility is True, prefers matching FACILITY nodes over child ROOM nodes.
    If preferred_realm_id is given, matches inside that realm first to prevent cross-realm name collisions.
    """
    if not session_id or not location_str:
        return None
    loc_clean = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u2793\u2795-\u27BF\uFE0F\u200D]+", "", str(location_str or ""))
    loc_clean = re.sub(r"\s{2,}", " ", loc_clean).strip()
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

    fb_candidates = _SCHOOL_CLUB_NODE_ID_FALLBACKS.get(loc_clean.lower())
    if fb_candidates:
        for fb_id in fb_candidates:
            fb_node = get_world_node(session_id, fb_id)
            if fb_node:
                return fb_node["node_id"]

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
    tier0_name = parts[0].lower() if parts else ""

    from mechanics.world.locations.realms import get_node_realm_id_in_memory
    nodes_by_id = {n["node_id"]: n for n in nodes if n.get("node_id")}

    _legacy_display_aliases = {
        "torii-crowned spirit courtyard": "sub_kitsune_inner_plaza",
        "laman beringin diraja": "sub_bunian_inner_plaza",
        "sato-no-inari — hidden kitsune village": "loc_hidden_kitsune_village",
        "kampung kayangan — hidden bunian village": "loc_hidden_bunian_village",
    }
    if not prefer_facility and leaf_name in _legacy_display_aliases and _legacy_display_aliases[leaf_name] in nodes_by_id:
        return _legacy_display_aliases[leaf_name]
    if prim_name in _legacy_display_aliases and _legacy_display_aliases[prim_name] in nodes_by_id:
        return _legacy_display_aliases[prim_name]

    # If tier0 explicitly names a REALM (e.g. "The Abyssal Underworld ➔ ..."), prefer that realm if preferred_realm_id wasn't forced
    eff_pref_realm = str(preferred_realm_id or "").strip()
    if len(parts) >= 2 and tier0_name:
        explicit_realm = next((n for n in nodes if n.get("node_type") == "REALM" and n["name"].lower() == tier0_name), None)
        if explicit_realm:
            eff_pref_realm = explicit_realm["node_id"]

    def _resolve_against_pool(pool: list[dict]) -> str | None:
        if not pool:
            return None
        prim_node = None
        if prim_name:
            for n in pool:
                if n.get("node_type") in ("FACILITY", "ZONE") and n["name"].lower() == prim_name:
                    prim_node = n
                    break
            if not prim_node:
                for n in pool:
                    if n.get("node_type") in ("FACILITY", "ZONE") and (prim_name in n["name"].lower() or n["name"].lower() in prim_name):
                        prim_node = n
                        break

        if prim_node:
            if prefer_facility:
                return prim_node["node_id"]
            if leaf_name and leaf_name != prim_name:
                child = next((rn for rn in pool if rn.get("parent_id") == prim_node["node_id"] and rn["name"].lower() == leaf_name), None)
                if child:
                    return child["node_id"]
                if leaf_name not in ("main area", "area", "main"):
                    child = next((rn for rn in pool if rn.get("parent_id") == prim_node["node_id"] and (leaf_name in rn["name"].lower() or rn["name"].lower() in leaf_name)), None)
                    if child:
                        return child["node_id"]
                    if ("gate path" in leaf_name or "entrance path" in leaf_name or "front gate" in leaf_name) and prim_node["node_id"] == "loc_school_gate":
                        child = next((rn for rn in pool if rn.get("parent_id") == prim_node["node_id"] and rn["node_id"] == "sub_entrance_path"), None)
                        if child:
                            return child["node_id"]
                    if "homeroom" in leaf_name:
                        child = next((rn for rn in pool if rn.get("parent_id") == prim_node["node_id"] and rn["node_id"] == "loc_homeroom"), None)
                        if child:
                            return child["node_id"]
            return prim_node["node_id"]

        if prim_name and len(parts) >= 2:
            for n in pool:
                if n.get("node_type") == "ROOM" and n["name"].lower() == prim_name:
                    return n["node_id"]
            if "homeroom" in prim_name:
                hr = next((n for n in pool if n["node_id"] == "loc_homeroom"), None)
                if hr:
                    return hr["node_id"]
            for n in pool:
                if n.get("node_type") == "ROOM" and len(prim_name) >= 4 and (prim_name in n["name"].lower() or n["name"].lower() in prim_name):
                    return n["node_id"]

        if leaf_name and leaf_name not in ("main area", "area", "main"):
            type_order = ("FACILITY", "ZONE", "ROOM") if prefer_facility else ("ROOM", "FACILITY", "ZONE")
            for n_type in type_order:
                for n in pool:
                    if n.get("node_type") == n_type and n["name"].lower() == leaf_name:
                        return n["node_id"]

        if leaf_name and len(leaf_name) >= 4 and leaf_name not in ("main area", "area", "main"):
            for n in pool:
                if n.get("node_type") == "REALM":
                    continue
                n_low = n["name"].lower()
                if leaf_name in n_low or n_low in leaf_name:
                    return n["node_id"]

        if prim_name and len(prim_name) >= 4:
            for n in pool:
                if n.get("node_type") == "REALM":
                    continue
                n_low = n["name"].lower()
                if prim_name in n_low or n_low in prim_name:
                    return n["node_id"]
        return None

    if eff_pref_realm:
        in_realm = [n for n in nodes if get_node_realm_id_in_memory(n["node_id"], nodes_by_id) == eff_pref_realm]
        hit = _resolve_against_pool(in_realm)
        if hit:
            return hit
        other_nodes = [n for n in nodes if get_node_realm_id_in_memory(n["node_id"], nodes_by_id) != eff_pref_realm]
        return _resolve_against_pool(other_nodes)

    return _resolve_against_pool(nodes)


def find_shortest_graph_path_minutes(
    session_id: int,
    from_node_id: str,
    to_node_id: str,
    allow_cross_realm: bool = False,
) -> int | None:
    """
    Computes shortest-path travel time in minutes between two nodes using Dijkstra's algorithm
    over world_edges plus implicit 1-minute parent-child transitions (never through REALM roots).
    Cross-realm travel is blocked by default (`allow_cross_realm=False`) and otherwise restricted
    strictly to `PORTAL_EDGE_TYPES`.
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

    from mechanics.world.locations.realms import PORTAL_EDGE_TYPES, get_node_realm_id_in_memory
    nodes_by_id = {n["node_id"]: n for n in nodes if n.get("node_id")}
    from_realm = get_node_realm_id_in_memory(from_node_id, nodes_by_id)
    to_realm = get_node_realm_id_in_memory(to_node_id, nodes_by_id)
    if not allow_cross_realm and from_realm and to_realm and from_realm != to_realm:
        return None

    explicit_directed_edges = {
        (e.get("from_node_id"), e.get("to_node_id"))
        for e in edges
        if e.get("from_node_id") and e.get("to_node_id")
    }
    adj = defaultdict(list)
    for e in edges:
        u = e.get("from_node_id")
        v = e.get("to_node_id")
        w = max(1, int(e.get("travel_minutes") or 2))
        etype = str(e.get("edge_type") or "")
        if etype == "leyline_spirit_passage" and int(e.get("is_locked") or 0) == 1:
            continue
        if (
            etype in PORTAL_EDGE_TYPES
            and int(e.get("is_locked") or 0) == 1
            and not e.get("lock_key_item")
            and not e.get("skill_check_type")
        ):
            continue
        if not u or not v:
            continue
        u_realm = get_node_realm_id_in_memory(u, nodes_by_id)
        v_realm = get_node_realm_id_in_memory(v, nodes_by_id)
        if u_realm and v_realm and u_realm != v_realm:
            if not allow_cross_realm or etype not in PORTAL_EDGE_TYPES:
                continue
        adj[u].append((v, w))
        if e.get("is_bidirectional", 1) and (v, u) not in explicit_directed_edges:
            adj[v].append((u, w))

    _mega_complex_ids = {
        "loc_agency_hq", "loc_private_hq_1", "loc_private_hq_2",
        "loc_general_hospital", "loc_theme_park", "loc_eastern_temple",
        "loc_botanical_zoo", "loc_cult_sanctum_hq", "loc_clandestine_syndicate_hq",
        "loc_hidden_kitsune_village", "loc_hidden_bunian_village",
    }
    # Add implicit parent-child transitions (1 minute between facility and room; NEVER through REALM root)
    for n in nodes:
        pid = n.get("parent_id")
        nid = n.get("node_id")
        if not pid or not nid:
            continue
        p_node = nodes_by_id.get(pid)
        if (p_node and str(p_node.get("node_type") or "").upper() == "REALM") or str(n.get("node_type") or "").upper() == "REALM":
            continue
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


def get_session_world_nodes_tx(session_id: int, conn: Any = None) -> list[dict]:
    """Transaction-aware world_nodes fetch reusing `conn` if provided."""
    if not session_id:
        return []
    if conn is not None:
        rows = conn.execute(
            "SELECT * FROM world_nodes WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    return get_session_world_nodes(session_id)


def get_world_node_tx(session_id: int, node_id: str, conn: Any = None) -> dict | None:
    """Transaction-aware single world_node fetch reusing `conn` if provided."""
    if not session_id or not node_id:
        return None
    if conn is not None:
        row = conn.execute(
            "SELECT * FROM world_nodes WHERE session_id = ? AND node_id = ?",
            (session_id, node_id),
        ).fetchone()
        return dict(row) if row else None
    return get_world_node(session_id, node_id)


def get_session_scenario_tx(session_id: int, conn: Any = None) -> str:
    """Fetches a session's scenario string within `conn` or a pooled connection."""
    if not session_id:
        return "fantasy"
    if conn is not None:
        s_row = conn.execute("SELECT scenario FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return str((s_row["scenario"] if s_row else "") or "fantasy")
    with get_conn() as c:
        s_row = c.execute("SELECT scenario FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return str((s_row["scenario"] if s_row else "") or "fantasy")


def update_world_node_state_json(
    session_id: int,
    node_id: str,
    state: dict | str,
    conn: Any = None,
) -> None:
    """Overwrites world_nodes.state_json for a node inside an optional connection/UoW."""
    if not session_id or not node_id:
        return
    payload = state if isinstance(state, str) else json.dumps(state)
    if conn is not None:
        conn.execute(
            "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
            (payload, session_id, node_id),
        )
        return
    with UnitOfWork() as c:
        c.execute(
            "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
            (payload, session_id, node_id),
        )


def upsert_world_node_tx(
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
    state_json: str | dict | None = None,
    overwrite_on_conflict: bool = False,
    conn: Any = None,
) -> None:
    """Transaction-aware world_nodes insert/upsert reusing an active connection when provided."""
    if not session_id or not node_id:
        return
    s_json_val = json.dumps(state_json) if isinstance(state_json, dict) else (state_json or "{}")
    now = time.time()
    sql = (
        """INSERT INTO world_nodes
           (session_id, node_id, parent_id, name, node_type, category, privacy_level,
            is_enclosed, is_transit_hub, access_tier, curfew_start_min, curfew_end_min,
            atmosphere, is_dynamic, state_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(session_id, node_id) DO UPDATE SET
           parent_id=excluded.parent_id, name=excluded.name, node_type=excluded.node_type,
           atmosphere=excluded.atmosphere, is_dynamic=excluded.is_dynamic, state_json=excluded.state_json"""
        if overwrite_on_conflict
        else """INSERT INTO world_nodes
                (session_id, node_id, parent_id, name, node_type, category, privacy_level,
                 is_enclosed, is_transit_hub, access_tier, curfew_start_min, curfew_end_min,
                 atmosphere, is_dynamic, state_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, node_id) DO NOTHING"""
    )
    params = (
        session_id,
        node_id,
        parent_id,
        name,
        node_type,
        category,
        privacy_level,
        is_enclosed,
        is_transit_hub,
        access_tier,
        curfew_start_min,
        curfew_end_min,
        atmosphere,
        is_dynamic,
        s_json_val,
        now,
    )
    if conn is not None:
        conn.execute(sql, params)
        return
    with UnitOfWork() as c:
        c.execute(sql, params)


def reparent_orphan_zones_to_realm(session_id: int, realm_id: str, conn: Any = None) -> int:
    """Attaches orphan ZONE nodes (parent_id IS NULL or '') under `realm_id`."""
    if not session_id or not realm_id:
        return 0
    sql = "UPDATE world_nodes SET parent_id = ? WHERE session_id = ? AND node_type = 'ZONE' AND (parent_id IS NULL OR parent_id = '')"
    if conn is not None:
        return int(conn.execute(sql, (realm_id, session_id)).rowcount or 0)
    with UnitOfWork() as c:
        return int(c.execute(sql, (realm_id, session_id)).rowcount or 0)


def upsert_world_edge_tx(
    session_id: int,
    from_node_id: str,
    to_node_id: str,
    travel_minutes: int = 2,
    edge_type: str = "hallway",
    is_bidirectional: int = 1,
    is_locked: int = 0,
    lock_key_item: str = "",
    skill_check_type: str = "",
    skill_check_dc: int = 0,
    update_on_conflict: bool = False,
    conn: Any = None,
) -> None:
    """Transaction-aware world_edges insert/upsert reusing `conn` if provided."""
    if not session_id or not from_node_id or not to_node_id:
        return
    now = time.time()
    sql = (
        """INSERT INTO world_edges
           (session_id, from_node_id, to_node_id, travel_minutes, edge_type, is_bidirectional, is_locked, lock_key_item, skill_check_type, skill_check_dc, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(session_id, from_node_id, to_node_id) DO UPDATE SET
           travel_minutes=excluded.travel_minutes, edge_type=excluded.edge_type,
           is_bidirectional=excluded.is_bidirectional, is_locked=excluded.is_locked,
           lock_key_item=excluded.lock_key_item, skill_check_type=excluded.skill_check_type,
           skill_check_dc=excluded.skill_check_dc"""
        if update_on_conflict
        else """INSERT INTO world_edges
                (session_id, from_node_id, to_node_id, travel_minutes, edge_type, is_bidirectional, is_locked, lock_key_item, skill_check_type, skill_check_dc, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, from_node_id, to_node_id) DO NOTHING"""
    )
    params = (
        session_id,
        from_node_id,
        to_node_id,
        travel_minutes,
        edge_type,
        is_bidirectional,
        is_locked,
        lock_key_item,
        skill_check_type,
        skill_check_dc,
        now,
    )
    if conn is not None:
        conn.execute(sql, params)
        return
    with UnitOfWork() as c:
        c.execute(sql, params)


def delete_world_edges_by_node_type(
    session_id: int,
    edge_type: str,
    node_id: str,
    conn: Any = None,
) -> int:
    """Deletes edges of `edge_type` incident to `node_id`."""
    if not session_id or not edge_type or not node_id:
        return 0
    sql = "DELETE FROM world_edges WHERE session_id = ? AND edge_type = ? AND (from_node_id = ? OR to_node_id = ?)"
    if conn is not None:
        return int(conn.execute(sql, (session_id, edge_type, node_id, node_id)).rowcount or 0)
    with UnitOfWork() as c:
        return int(c.execute(sql, (session_id, edge_type, node_id, node_id)).rowcount or 0)


def unlock_realm_edges_by_types(
    session_id: int,
    member_node_ids: list[str],
    edge_types: tuple[str, ...],
    *,
    lock_return_only: bool = False,
    conn: Any = None,
) -> None:
    """Unlocks portal edges for realm members or re-locks outgoing return edges on rollback."""
    if not session_id or not member_node_ids or not edge_types:
        return
    ph_m = ",".join("?" for _ in member_node_ids)
    ph_e = ",".join("?" for _ in edge_types)

    def _run(c: Any) -> None:
        if lock_return_only:
            c.execute(
                f"UPDATE world_edges SET is_locked = 1, is_bidirectional = 0 WHERE session_id = ? AND from_node_id IN ({ph_m}) AND edge_type IN ({ph_e})",
                (session_id, *member_node_ids, *edge_types),
            )
            c.execute(
                f"UPDATE world_edges SET is_bidirectional = 0 WHERE session_id = ? AND to_node_id IN ({ph_m}) AND edge_type IN ({ph_e})",
                (session_id, *member_node_ids, *edge_types),
            )
        else:
            c.execute(
                f"UPDATE world_edges SET is_locked = 0, is_bidirectional = 1 WHERE session_id = ? AND (from_node_id IN ({ph_m}) OR to_node_id IN ({ph_m})) AND edge_type IN ({ph_e})",
                (session_id, *member_node_ids, *member_node_ids, *edge_types),
            )

    if conn is not None:
        _run(conn)
        return
    with UnitOfWork() as c:
        _run(c)


def delete_realm_nodes_and_edges(
    session_id: int,
    node_ids: list[str],
    realm_id: str,
    conn: Any = None,
) -> dict[str, int]:
    """Deletes `node_ids`, incident edges, session_locations, and dangling portal metadata."""
    if not session_id or not node_ids:
        return {"deleted_nodes": 0, "deleted_edges": 0}
    to_del_set = set(node_ids)
    ph = ",".join("?" for _ in node_ids)

    def _run(c: Any) -> dict[str, int]:
        del_edges = c.execute(
            f"DELETE FROM world_edges WHERE session_id = ? AND (from_node_id IN ({ph}) OR to_node_id IN ({ph}))",
            (session_id, *node_ids, *node_ids),
        ).rowcount or 0
        c.execute(
            f"DELETE FROM session_locations WHERE session_id = ? AND location_id IN ({ph})",
            (session_id, *node_ids),
        )
        del_nodes = c.execute(
            f"DELETE FROM world_nodes WHERE session_id = ? AND node_id IN ({ph})",
            (session_id, *node_ids),
        ).rowcount or 0
        rem_rows = c.execute(
            "SELECT node_id, state_json FROM world_nodes WHERE session_id = ? AND state_json LIKE '%portals%'",
            (session_id,),
        ).fetchall()
        for r in rem_rows:
            nid = str(r["node_id"])
            if nid in to_del_set or not r["state_json"]:
                continue
            try:
                st = json.loads(r["state_json"]) if isinstance(r["state_json"], str) else dict(r["state_json"])
            except Exception:
                continue
            if not isinstance(st, dict):
                continue
            portals = st.get("portals")
            if isinstance(portals, dict):
                pruned = {
                    k: v
                    for k, v in portals.items()
                    if k not in to_del_set and not (isinstance(v, dict) and v.get("target_realm_id") == realm_id)
                }
                if len(pruned) != len(portals):
                    st["portals"] = pruned
                    c.execute(
                        "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
                        (json.dumps(st), session_id, nid),
                    )
        return {"deleted_nodes": int(del_nodes), "deleted_edges": int(del_edges)}

    if conn is not None:
        return _run(conn)
    with UnitOfWork() as c:
        return _run(c)


def restore_session_location_node_tx(
    session_id: int,
    node_id: str,
    location_str: str,
    conn: Any = None,
) -> None:
    """Restores sessions.current_node_id and sessions.current_location inside an optional connection."""
    if not session_id:
        return
    sql = "UPDATE sessions SET current_node_id = ?, current_location = ?, updated_at = ? WHERE id = ?"
    params = (node_id, location_str, time.time(), session_id)
    if conn is not None:
        conn.execute(sql, params)
        return
    with UnitOfWork() as c:
        c.execute(sql, params)


def fix_dangling_session_node_after_collapse(
    session_id: int,
    fallback_node_ids: list[str] | tuple[str, ...] = (),
    conn: Any = None,
) -> bool:
    """Relocates sessions.current_node_id if it references a node deleted during dynamic realm collapse."""
    if not session_id:
        return False

    def _run(c: Any) -> bool:
        s_row = c.execute(
            "SELECT current_node_id, extra_json FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not s_row:
            return False
        curr_nid = str(s_row["current_node_id"] or "").strip()
        if not curr_nid:
            return False
        exists = c.execute(
            "SELECT 1 FROM world_nodes WHERE session_id = ? AND node_id = ?",
            (session_id, curr_nid),
        ).fetchone()
        if exists:
            return False

        rows = c.execute("SELECT * FROM world_nodes WHERE session_id = ? ORDER BY id ASC", (session_id,)).fetchall()
        nodes = [dict(r) for r in rows]
        nodes_by_id = {str(n["node_id"]): n for n in nodes if n.get("node_id")}
        chosen_nid = ""
        for cand in (fallback_node_ids or ()):
            c_str = str(cand or "").strip()
            if c_str and c_str in nodes_by_id:
                chosen_nid = c_str
                break
        from mechanics.world.locations.realms import (
            format_tiered_location_in_memory,
            get_node_realm_id_in_memory,
            get_node_realm_in_memory,
            get_primary_realm_in_memory,
            get_realm_rules,
            is_node_or_realm_hidden_in_memory,
        )
        if not chosen_nid and nodes:
            prim = get_primary_realm_in_memory(nodes_by_id)
            prim_id = str((prim or {}).get("node_id") or "")
            room_cands = [
                n for n in nodes
                if str(n.get("node_type") or "").upper() == "ROOM"
                and (not prim_id or get_node_realm_id_in_memory(str(n["node_id"]), nodes_by_id) == prim_id)
                and not is_node_or_realm_hidden_in_memory(str(n["node_id"]), nodes_by_id)
            ]
            hub_pick = next(
                (
                    n for n in room_cands
                    if int(n.get("is_transit_hub") or 0) == 1
                    or int((nodes_by_id.get(str(n.get("parent_id") or "")) or {}).get("is_transit_hub") or 0) == 1
                ),
                room_cands[0] if room_cands else None,
            )
            if hub_pick:
                chosen_nid = str(hub_pick["node_id"])
            loc_str = format_tiered_location_in_memory(chosen_nid, nodes_by_id) if chosen_nid else ""
        else:
            loc_str = format_tiered_location_in_memory(chosen_nid, nodes_by_id) if chosen_nid else ""

        dest_realm = get_node_realm_in_memory(chosen_nid, nodes_by_id) if chosen_nid else None
        dest_rules = get_realm_rules(dest_realm) if dest_realm else {}
        extra_sql = ""
        params: list[Any] = [chosen_nid, loc_str, time.time()]
        if not dest_rules.get("restrict_companions"):
            try:
                ex_obj = json.loads(s_row["extra_json"] or "{}") if s_row["extra_json"] else {}
            except Exception:
                ex_obj = {}
            if isinstance(ex_obj, dict) and ex_obj.get("waiting_outside_companions"):
                ex_obj["waiting_outside_companions"] = []
                extra_sql = ", extra_json = ?"
                params.append(json.dumps(ex_obj, default=str))
        params.append(session_id)

        c.execute(
            f"UPDATE sessions SET current_node_id = ?, current_location = ?, focal_point = '', updated_at = ?{extra_sql} WHERE id = ?",
            tuple(params),
        )
        return True

    if conn is not None:
        return _run(conn)
    with UnitOfWork() as c:
        return _run(c)




