from __future__ import annotations
from .constants import *
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import db
from .seeds import *
from .seeds import _load_seeds, _slugify, _SEED_PATH

def get_default_tiered_location(scenario_key: str = "fantasy", session_id: int = 0, char_name: str = "") -> Tuple[str, str, str]:

    """Returns the starting (Zone, Primary, Sub) for a scenario from seeds."""

    scen_data = get_scenario_seed_data(scenario_key)

    zones = inject_anomalous_faction_hq_facilities(scen_data.get("zones") or [], session_id=session_id, scenario_key=scenario_key)

    if zones:

        z_name = zones[0].get("name", "World Region")

        if z_name == "Main Academy Building" or zones[0].get("id") == "zone_school_main" or is_school_scenario(scenario_key):

            z_name = get_session_school_name(session_id, scenario_key)

        primaries = zones[0].get("primary_locations") or []

        if primaries:

            p_id = primaries[0].get("id", "")
            p_name = primaries[0].get("name", "Main Area")

            if p_name == "Homeroom Classroom" or p_id == "loc_homeroom":

                p_name = get_session_classroom_name(session_id, scenario_key)

            elif p_name == "Player's House" or p_id == "loc_player_house":

                p_name = get_session_player_house_name(session_id, char_name, scenario_key)

            elif p_name == "Neighborhood Park" or p_id == "loc_local_park":

                p_name = get_session_park_name(session_id, scenario_key)
            elif p_id == "loc_agency_hq" or "{session_agency_hq}" in p_name:
                p_name = get_session_agency_hq_name(session_id, scenario_key)

            if is_urban_anomalous_scenario(scenario_key):
                z_name = get_session_urban_zone_name(session_id, zones[0].get("id", ""), z_name, scenario_key)
                p_name = get_session_urban_facility_name(session_id, zones[0].get("id", ""), p_id, p_name, scenario_key, char_name)

            subs = primaries[0].get("sub_locations") or []
            from .hierarchy import resolve_session_location_tokens, resolve_default_sublocation

            if subs:

                s_id = subs[0].get("id", "")
                s_name = subs[0].get("name") or resolve_default_sublocation(p_name, z_name, session_id=session_id, scenario_key=scenario_key, char_name=char_name)

                if s_name == "Homeroom Classroom" or s_id == "loc_homeroom":
                    s_name = get_session_classroom_name(session_id, scenario_key)
                elif (s_name == "Player's Desk" or s_id == "sub_player_desk") and (p_id == "loc_homeroom" or "homeroom" in p_name.lower()):

                    s_name = get_session_player_desk_name(session_id, char_name)
                elif is_urban_anomalous_scenario(scenario_key) and s_id.startswith("loc_hq_"):
                    s_name = get_session_urban_facility_name(session_id, "zone_agency_hq", s_id, s_name, scenario_key, char_name)

            else:

                s_name = resolve_default_sublocation(p_name, z_name, session_id=session_id, scenario_key=scenario_key, char_name=char_name)

            return (
                resolve_session_location_tokens(session_id, z_name, scenario_key, char_name),
                resolve_session_location_tokens(session_id, p_name, scenario_key, char_name),
                resolve_session_location_tokens(session_id, s_name, scenario_key, char_name)
            )

        from .hierarchy import resolve_session_location_tokens, resolve_default_sublocation
        z_res = resolve_session_location_tokens(session_id, z_name, scenario_key, char_name)
        return (
            z_res,
            z_res,
            resolve_default_sublocation(z_res, z_res, session_id=session_id, scenario_key=scenario_key, char_name=char_name)
        )

    return ("World Region", "Central District", "Central Concourse")

def get_archetype_starting_location(

    session_id: int = 0,

    scenario_key: str = "fantasy",

    archetype: str = "hub_launchpad",

    char_name: str = "",

    preferred_hint: str = ""

) -> Tuple[str, str, str]:

    """

    Selects a guaranteed-valid 3-tiered location (Zone, Primary, Sub) directly from

    the session's seeded map in SQLite (or scenario seed definitions), categorized

    by Starting Archetype:



    - 'hub_launchpad': Selects a lively safe hub location (is_hub == True / primary hub zones).

    - 'in_media_res': Selects a high-action, hazard, perimeter, or dynamic incident location from the seeded map.

    - 'delve_threshold': Selects a mystery, frontier, ruin, or exploration threshold from the seeded map.



    Returns (zone_name, primary_name, sub_name).

    """

    if session_id:

        ensure_session_locations_seeded(session_id, scenario_key, char_name=char_name)

        rows = db.get_session_locations(session_id)

    else:

        rows = []



    seeded_triples: List[Tuple[str, str, str, bool]] = []

    if rows:

        for r in rows:

            z = r.get("zone_name") or ""

            p = r.get("primary_name") or ""

            s = r.get("sub_name") or ""

            is_dynamic = bool(r.get("is_dynamic", 0))

            if z and p and s and not is_dynamic:

                is_hub = is_hub_location(z) or is_hub_location(p)

                seeded_triples.append((z, p, s, is_hub))



    if not seeded_triples:

        scen_data = get_scenario_seed_data(scenario_key)

        zones = scen_data.get("zones") or []

        for z in zones:

            z_id = z.get("id", "")

            z_name = z.get("name", "World Region")

            if z_name in ("Main Academy Building", "Main Academy Campus") or z_id == "zone_school_main":

                z_name = get_session_school_name(session_id, scenario_key) if session_id else "Suimei Institute"

            elif (z_name == "Residential Neighborhood" or z_id == "zone_residential") and is_school_scenario(scenario_key):

                z_name = get_session_residential_neighborhood_name(session_id, scenario_key)

            elif (z_name in ("Commercial District", "Downtown") or z_id in ("zone_commercial", "zone_downtown")) and is_school_scenario(scenario_key):

                z_name = get_session_commercial_district_name(session_id, scenario_key)

            elif (z_name in ("Recreational Mountain Park", "Recreational Park") or z_id in ("zone_mountain_park", "zone_recreational_park")) and is_school_scenario(scenario_key):

                z_name = get_session_recreation_park_name(session_id, scenario_key)

            z_hub = bool(z.get("is_hub", False))

            for p in z.get("primary_locations", []):

                p_id = p.get("id", "")

                p_name = p.get("name", "Main Area")

                if p_name == "Homeroom Classroom" or p_id == "loc_homeroom":

                    p_name = get_session_classroom_name(session_id, scenario_key) if session_id else "Homeroom Classroom"

                elif p_id == "bld_school_athletics" or p_name == "School Grounds & Athletics":
                    p_name = get_session_athletics_complex_name(session_id, scenario_key)
                elif p_id == "bld_school_commons" or p_name == "Student Commons & Central Plaza":
                    p_name = get_session_student_commons_name(session_id, scenario_key)
                elif p_id == "bld_school_arts" or p_name == "Cultural Arts & Student Union":
                    p_name = get_session_cultural_arts_name(session_id, scenario_key)
                elif p_id == "bld_abandoned_school" or p_name == "Abandoned Old Campus Building":
                    p_name = get_session_abandoned_campus_name(session_id, scenario_key)
                elif p_id == "loc_agency_hq" or "{session_agency_hq}" in p_name:
                    p_name = get_session_agency_hq_name(session_id, scenario_key)

                elif p_name == "Player's House" or p_id == "loc_player_house":

                    p_name = get_session_player_house_name(session_id, char_name, scenario_key)

                elif p_name == "Neighborhood Park" or p_id == "loc_local_park":

                    p_name = get_session_park_name(session_id, scenario_key)

                subs = p.get("sub_locations", [])
                from .hierarchy import resolve_default_sublocation

                if subs:

                    for s in subs:

                        s_id = s.get("id", "")
                        s_name = s.get("name") or resolve_default_sublocation(p_name, z_name, session_id=session_id, scenario_key=scenario_key, char_name=char_name)

                        if s_name == "Homeroom Classroom" or s_id == "loc_homeroom":
                            s_name = get_session_classroom_name(session_id, scenario_key) if session_id else "Homeroom Classroom"
                        elif (s_name == "Player's Desk" or s_id == "sub_player_desk") and (p_id == "loc_homeroom" or "homeroom" in p_name.lower()):

                            s_name = get_session_player_desk_name(session_id, char_name)

                        seeded_triples.append((z_name, p_name, s_name, z_hub))

                else:

                    seeded_triples.append((z_name, p_name, resolve_default_sublocation(p_name, z_name, session_id=session_id, scenario_key=scenario_key, char_name=char_name), z_hub))



    if not seeded_triples:

        return get_default_tiered_location(scenario_key, session_id=session_id, char_name=char_name)



    # If preferred_hint is provided, check for a match

    if preferred_hint:

        hint_clean = preferred_hint.lower().strip()

        hint_parts = [hp.strip() for hp in re.split(r"[➔\->|/]", hint_clean) if hp.strip()]



        # Priority 0: Match both primary place AND sub-location when both are present in hint_parts
        matching_hint = [
            (z, p, s) for (z, p, s, h) in seeded_triples
            if any(hp == p.lower() or (len(hp) >= 5 and (hp in p.lower() or p.lower() in hp)) for hp in hint_parts)
            and any(hs == s.lower() or (len(hs) >= 4 and (hs in s.lower() or s.lower() in hs)) for hs in hint_parts)
        ]

        # Priority 1: Match primary place specifically (e.g. 'School Rooftop')
        if not matching_hint:
            matching_hint = [

                (z, p, s) for (z, p, s, h) in seeded_triples

                if any(hp == p.lower() or (len(hp) >= 5 and (hp in p.lower() or p.lower() in hp)) for hp in hint_parts)

            ]

        # Priority 2: Match sub-location specifically (e.g. 'Behind Water Tank' or 'Rooftop Benches')

        if not matching_hint:

            matching_hint = [

                (z, p, s) for (z, p, s, h) in seeded_triples

                if any(hp == s.lower() or (len(hp) >= 5 and (hp in s.lower() or s.lower() in hp)) for hp in hint_parts)

            ]

        # Priority 3: Fallback bidirectional containment

        if not matching_hint:

            matching_hint = [

                (z, p, s) for (z, p, s, h) in seeded_triples

                if (hint_clean in z.lower() or hint_clean in p.lower() or hint_clean in s.lower() or

                    (len(p) >= 5 and p.lower() in hint_clean) or

                    (len(s) >= 5 and s.lower() in hint_clean))

            ]

        if matching_hint:

            import random

            cz, cp, cs = random.choice(matching_hint)
            from .hierarchy import resolve_session_location_tokens
            return (
                resolve_session_location_tokens(session_id, cz, scenario_key, char_name),
                resolve_session_location_tokens(session_id, cp, scenario_key, char_name),
                resolve_session_location_tokens(session_id, cs, scenario_key, char_name)
            )



    hub_candidates = [(z, p, s) for (z, p, s, h) in seeded_triples if h]

    if not hub_candidates:

        hub_candidates = [(z, p, s) for (z, p, s, h) in seeded_triples if is_hub_location(z) or is_hub_location(p)]



    hazard_keywords = (

        "pass", "gate", "lab", "gym", "hangar", "engineering", "boiler", "cargo", "crater",

        "overpass", "arena", "ambush", "ridge", "trench", "dock", "corridor", "hallway",

        "badlands", "outpost", "palisade", "foundry", "furnace", "airlock", "reactor"

    )

    hazard_candidates = [

        (z, p, s) for (z, p, s, h) in seeded_triples

        if any(k in z.lower() or k in p.lower() or k in s.lower() for k in hazard_keywords)

    ]



    delve_keywords = (

        "ruin", "abandoned", "haunted", "manor", "catacomb", "crypt", "sanctuary", "grotto",

        "dungeon", "subway", "vault", "lookout", "observatory", "tree", "woods", "forest",

        "tomb", "shrine", "spire", "crag", "station", "planet", "colliery", "graveyard", "rooftop"

    )

    delve_candidates = [

        (z, p, s) for (z, p, s, h) in seeded_triples

        if any(k in z.lower() or k in p.lower() or k in s.lower() for k in delve_keywords)

    ]



    import random

    if archetype == "in_media_res":

        candidates = hazard_candidates or [(z, p, s) for (z, p, s, h) in seeded_triples if not h] or seeded_triples

    elif archetype == "delve_threshold":

        candidates = delve_candidates or [(z, p, s) for (z, p, s, h) in seeded_triples if not h] or seeded_triples

    else:

        candidates = hub_candidates or seeded_triples



    cz, cp, cs = random.choice(candidates)
    from .hierarchy import resolve_session_location_tokens
    return (
        resolve_session_location_tokens(session_id, cz, scenario_key, char_name),
        resolve_session_location_tokens(session_id, cp, scenario_key, char_name),
        resolve_session_location_tokens(session_id, cs, scenario_key, char_name)
    )

def _reconcile_faction_hq_locations(session_id: int, scenario_key: str = "high_school_drama", school_name: str = ""):
    """Ensures every faction recorded in the database has a grounded physical HQ location in session_locations."""
    if not session_id:
        return
    try:
        factions = db.get_factions(session_id)
        if not factions:
            return

        existing_locs = db.get_session_locations(session_id) or []
        existing_primaries = (
            {(r.get("primary_name") or "").strip().lower() for r in existing_locs}
            | {(r.get("sub_name") or "").strip().lower() for r in existing_locs}
        )
        existing_ids = {(r.get("location_id") or "").strip().lower() for r in existing_locs}
        world_nodes_present = bool(db.get_session_world_nodes(session_id))

        for fac in factions:
            hq_raw = (fac.get("hq_location_id") or "").strip()
            if not hq_raw:
                continue

            if any(d in hq_raw for d in ("➔", "->", ">", "|")):
                fz, fp, fs = parse_tiered_location(hq_raw, scenario_key, session_id=session_id)
                hq_raw = fp
                with db.get_conn() as conn:
                    conn.execute("UPDATE factions SET hq_location_id = ? WHERE id = ?", (fp, fac["id"]))
                    conn.commit()

            hq_lower = hq_raw.lower()
            if hq_lower in existing_primaries or hq_lower in existing_ids:
                continue

            if world_nodes_present:
                resolved_nid = db.resolve_node_id_from_location(session_id, hq_raw)
                if resolved_nid:
                    continue

            if any(hq_lower in ep or ep in hq_lower for ep in existing_primaries if len(ep) >= 6):
                continue

            provisioned = provision_faction_hq_tier2_location(
                session_id,
                fac.get("name", "Faction"),
                scenario_key,
                hq_raw,
            )
            existing_primaries.add(provisioned.lower())
    except Exception:
        pass

def ensure_session_locations_seeded(session_id: int, scenario_key: str = "high_school_drama", char_name: str = ""):

    """Ensures seed locations exist in SQLite for the session."""

    if not is_location_engine_enabled(scenario_key):

        return



    existing = db.get_session_locations(session_id)

    from .hierarchy import resolve_session_location_tokens, resolve_default_sublocation, format_tiered_location_string

    # Retroactive self-healing: fix any existing unrendered session tokens OR legacy "Main Area" sublocations in SQLite
    if existing and any(
        '{' in (r.get('zone_name') or '')
        or '{' in (r.get('primary_name') or '')
        or (r.get('sub_name') or '').strip().lower() == 'main area'
        for r in existing
    ):
        with db.get_conn() as conn:
            for r in existing:
                z_cur = r.get('zone_name') or ''
                p_cur = r.get('primary_name') or ''
                s_cur = r.get('sub_name') or ''
                z_fixed = resolve_session_location_tokens(session_id, z_cur, scenario_key, char_name)
                p_fixed = resolve_session_location_tokens(session_id, p_cur, scenario_key, char_name)
                s_fixed = resolve_session_location_tokens(session_id, s_cur, scenario_key, char_name)
                if s_fixed.strip().lower() == 'main area':
                    s_fixed = resolve_default_sublocation(p_fixed, z_fixed, session_id=session_id, scenario_key=scenario_key, char_name=char_name)
                if z_fixed != z_cur or p_fixed != p_cur or s_fixed != s_cur:
                    conn.execute(
                        'UPDATE session_locations SET zone_name=?, primary_name=?, sub_name=? WHERE session_id=? AND location_id=?',
                        (z_fixed, p_fixed, s_fixed, session_id, r['location_id'])
                    )
        existing = db.get_session_locations(session_id)

    # Also self-heal any world_nodes ROOM rows named "Main Area" and current_location on the session
    try:
        wnodes = db.get_session_world_nodes(session_id)
        if wnodes:
            node_map = {n["node_id"]: n for n in wnodes}
            dirty_nodes = [n for n in wnodes if (n.get("name") or "").strip().lower() == "main area"]
            if dirty_nodes:
                with db.get_conn() as conn:
                    for dn in dirty_nodes:
                        parent = node_map.get(dn.get("parent_id")) if dn.get("parent_id") else None
                        gparent = node_map.get(parent.get("parent_id")) if (parent and parent.get("parent_id")) else None
                        p_lbl = parent["name"] if parent else dn["name"]
                        z_lbl = gparent["name"] if gparent else (parent["name"] if parent else "")
                        healed_sub = resolve_default_sublocation(p_lbl, z_lbl, session_id=session_id, scenario_key=scenario_key, char_name=char_name)
                        if healed_sub and healed_sub.lower() != "main area":
                            conn.execute(
                                "UPDATE world_nodes SET name=? WHERE session_id=? AND node_id=?",
                                (healed_sub, session_id, dn["node_id"])
                            )
        sess_cur = db.get_session(session_id)
        if sess_cur:
            cur_loc_str = str(sess_cur.get("current_location") or "")
            if "main area" in cur_loc_str.lower():
                cz, cp, cs = parse_tiered_location(cur_loc_str, scenario_key=scenario_key, session_id=session_id, char_name=char_name)
                if cs.strip().lower() == "main area":
                    cs = resolve_default_sublocation(cp, cz, session_id=session_id, scenario_key=scenario_key, char_name=char_name)
                healed_loc = format_tiered_location_string(cz, cp, cs)
                if healed_loc != cur_loc_str:
                    db.update_session(session_id, current_location=healed_loc)
    except Exception:
        pass

    school_name = get_session_school_name(session_id, scenario_key) if is_school_scenario(scenario_key) else None

    classroom_name = get_session_classroom_name(session_id, scenario_key) if is_school_scenario(scenario_key) else None

    player_desk = get_session_player_desk_name(session_id, char_name)

    player_house = get_session_player_house_name(session_id, char_name, scenario_key)

    park_name = get_session_park_name(session_id, scenario_key)



    scen_data = get_scenario_seed_data(scenario_key)

    zones = inject_anomalous_faction_hq_facilities(scen_data.get("zones") or [], session_id=session_id, scenario_key=scenario_key)



    school_name = get_session_school_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""

    classroom_name = get_session_classroom_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""

    player_desk = get_session_player_desk_name(session_id, char_name=char_name) if is_school_scenario(scenario_key) else ""

    player_house = get_session_player_house_name(session_id, char_name=char_name, scenario_key=scenario_key)

    park_name = get_session_park_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""

    cafe_name = get_session_cafe_name(session_id, scenario_key)

    arcade_name = get_session_arcade_name(session_id, scenario_key)

    commercial_name = get_session_commercial_district_name(session_id, scenario_key)

    residential_name = get_session_residential_neighborhood_name(session_id, scenario_key)

    ripperdoc_name = get_session_ripperdoc_name(session_id, scenario_key)

    kingdom_name = get_session_kingdom_name(session_id, scenario_key)

    forest_name = get_session_forest_name(session_id, scenario_key)

    ancient_forest_name = get_session_ancient_forest_name(session_id, scenario_key)

    mountain_name = get_session_mountain_name(session_id, scenario_key)

    desert_name = get_session_desert_name(session_id, scenario_key)

    swamp_name = get_session_swamp_name(session_id, scenario_key)

    plains_name = get_session_plains_name(session_id, scenario_key)

    harbor_name = get_session_harbor_name(session_id, scenario_key)

    tundra_name = get_session_tundra_name(session_id, scenario_key)

    volcano_name = get_session_volcano_name(session_id, scenario_key)

    shadowlands_name = get_session_shadowlands_name(session_id, scenario_key)

    caves_name = get_session_caves_name(session_id, scenario_key)

    chasm_name = get_session_chasm_name(session_id, scenario_key)

    dungeon_name = get_session_dungeon_name(session_id, scenario_key)

    cyber_city = get_session_cyber_city_name(session_id, scenario_key)

    airship_name = get_session_airship_name(session_id, scenario_key)

    station_name = get_session_station_name(session_id)

    seaside_name = get_session_seaside_name(session_id, scenario_key)

    rec_park_name = get_session_recreation_park_name(session_id, scenario_key)

    athletics_name = get_session_athletics_complex_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""

    commons_name = get_session_student_commons_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""

    arts_name = get_session_cultural_arts_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""

    abandoned_name = get_session_abandoned_campus_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""

    agency_hq_name = get_session_agency_hq_name(session_id, scenario_key)
    agency_name = get_session_agency_name(session_id, scenario_key)

    existing_loc_ids = {r.get("location_id") for r in existing if r.get("location_id")}

    existing_tuples = {(r.get("primary_name", "").lower(), r.get("sub_name", "").lower()) for r in existing}

    to_insert = []

    for zone in zones:

        z_id = zone.get("id", "")

        zone_name = zone.get("name", "World Region")



        # Procedurally personalize Zone names

        if school_name and (zone_name in ("Main Academy Campus", "Main Academy Building") or z_id == "zone_school_main"):

            zone_name = school_name

        elif z_id == "zone_school_athletics" or zone_name == "School Grounds & Athletics":

            zone_name = athletics_name or "School Grounds & Athletics"

        elif z_id == "zone_school_commons" or zone_name == "Student Commons & Central Plaza":

            zone_name = commons_name or "Student Commons & Central Plaza"

        elif z_id == "zone_school_arts" or zone_name == "Cultural Arts & Student Union":

            zone_name = arts_name or "Cultural Arts & Student Union"

        elif z_id == "zone_abandoned_school" or zone_name == "Abandoned Old Campus Building":

            zone_name = abandoned_name or "Abandoned Old Campus Building"

        elif z_id in ("zone_capital_city", "zone_capital_city_isekai") or zone_name == "Capital City":

            zone_name = f"Royal Capital of {kingdom_name}"

        elif z_id in ("zone_ancient_woods", "zone_ancient_woods_isekai") or zone_name == "Ancient Woods":

            zone_name = ancient_forest_name

        elif z_id in ("zone_woodlands_forest", "zone_woodlands_forest_isekai") or zone_name == "Woodlands & Forest":

            zone_name = forest_name

        elif z_id in ("zone_mountain_range", "zone_mountain_range_isekai") or zone_name == "High Mountain Range":

            zone_name = mountain_name

        elif z_id in ("zone_desert_dunes", "zone_desert_dunes_isekai") or zone_name == "Desert Dunes & Oasis":

            zone_name = desert_name

        elif z_id in ("zone_swamp_marshes", "zone_swamp_marshes_isekai") or zone_name == "Swamp & Marshes":

            zone_name = swamp_name

        elif z_id in ("zone_central_plains", "zone_central_plains_isekai") or zone_name == "Central Farmlands & Plains":

            zone_name = plains_name

        elif z_id in ("zone_coastal_harbor", "zone_coastal_harbor_isekai") or zone_name == "Coastal Harbor Town":

            zone_name = harbor_name

        elif z_id in ("zone_frozen_tundra", "zone_frozen_tundra_isekai") or zone_name == "Frozen Snow & Tundra":

            zone_name = tundra_name

        elif z_id in ("zone_volcanic_ashlands", "zone_volcanic_ashlands_isekai") or zone_name == "Volcanic Ashlands":

            zone_name = volcano_name

        elif z_id in ("zone_cursed_shadowlands", "zone_cursed_shadowlands_isekai") or zone_name == "Cursed Shadowlands":

            zone_name = shadowlands_name

        elif z_id in ("zone_deep_caves", "zone_deep_caves_isekai") or zone_name == "Deep Cave Network":

            zone_name = caves_name

        elif z_id in ("zone_underworld_chasm", "zone_underworld_chasm_isekai") or zone_name == "Underworld Chasm":

            zone_name = chasm_name

        elif z_id in ("zone_ancient_dungeon", "zone_ancient_dungeon_isekai") or zone_name == "Ancient Dungeon Complex":

            zone_name = dungeon_name

        elif zone_name == "City Center & Megacorp Plaza":

            zone_name = f"{cyber_city} - City Center"

        elif zone_name == "Downtown Commercial Core":

            zone_name = f"{cyber_city} - Downtown"

        elif z_id == "zone_slums_lower_wards" or zone_name == "Slums & Lower Wards":

            zone_name = f"{cyber_city} - Slums & Wards"

        elif z_id == "zone_airship_cruiser" or zone_name == "Grand Zeppelin Cruiser":

            zone_name = airship_name

        elif z_id == "zone_orbital_station" or zone_name == "Central Orbital Station":

            zone_name = station_name

        elif z_id == "zone_desert_planet":

            zone_name = f"{get_session_planet_name(session_id, 'desert')} (Desert World)"

        elif z_id == "zone_ice_planet":

            zone_name = f"{get_session_planet_name(session_id, 'ice')} (Ice World)"

        elif z_id == "zone_jungle_planet":

            zone_name = f"{get_session_planet_name(session_id, 'jungle')} (Jungle World)"

        elif z_id == "zone_volcanic_planet":

            zone_name = f"{get_session_planet_name(session_id, 'volcanic')} (Volcanic World)"

        elif z_id == "zone_ocean_planet":

            zone_name = f"{get_session_planet_name(session_id, 'ocean')} (Ocean World)"

        elif z_id == "zone_seaside_bay" or zone_name == "Seaside & Coastal Bay":

            zone_name = seaside_name

        elif z_id in ("zone_mountain_park", "zone_recreational_park") or zone_name in ("Recreational Mountain Park", "Recreational Park"):

            zone_name = rec_park_name

        elif z_id == "zone_commercial" or zone_name == "Commercial District" or ((z_id == "zone_downtown" or zone_name == "Downtown") and is_school_scenario(scenario_key)):

            zone_name = commercial_name

        elif z_id == "zone_residential" or zone_name == "Residential Neighborhood":

            zone_name = residential_name

        elif z_id == "zone_agency_hq" or "{session_agency_hq}" in zone_name:

            zone_name = agency_hq_name

        elif "{session_agency}" in zone_name:

            zone_name = agency_name

        if is_urban_anomalous_scenario(scenario_key):
            zone_name = get_session_urban_zone_name(session_id, z_id, zone_name, scenario_key)
        zone_name = resolve_session_location_tokens(session_id, zone_name, scenario_key, char_name)

        if "theme" in zone or "features" in zone:

            env_dict = {

                "theme": resolve_session_location_tokens(session_id, zone.get("theme", ""), scenario_key, char_name),

                "features": resolve_session_location_tokens(session_id, zone.get("features", ""), scenario_key, char_name),

                "sensory": resolve_session_location_tokens(session_id, zone.get("sensory", zone.get("atmosphere", "")), scenario_key, char_name)

            }

            atmosphere = json.dumps(env_dict)

        else:

            atmosphere = resolve_session_location_tokens(session_id, zone.get("atmosphere", ""), scenario_key, char_name)



        for primary in zone.get("primary_locations") or []:

            p_id = primary.get("id", "")

            primary_name = primary.get("name", "Main Area")



            # Procedurally personalize Primary place names

            if classroom_name and (primary_name == "Homeroom Classroom" or p_id == "loc_homeroom"):

                primary_name = classroom_name

            elif p_id == "bld_school_athletics" or primary_name == "School Grounds & Athletics":
                primary_name = athletics_name or "School Grounds & Athletics"
            elif p_id == "bld_school_commons" or primary_name == "Student Commons & Central Plaza":
                primary_name = commons_name or "Student Commons & Central Plaza"
            elif p_id == "bld_school_arts" or primary_name == "Cultural Arts & Student Union":
                primary_name = arts_name or "Cultural Arts & Student Union"
            elif p_id == "bld_abandoned_school" or primary_name == "Abandoned Old Campus Building":
                primary_name = abandoned_name or "Abandoned Old Campus Building"
            elif p_id == "loc_agency_hq" or "{session_agency_hq}" in primary_name:
                primary_name = agency_hq_name

            elif primary_name == "Player's House" or p_id == "loc_player_house":

                primary_name = player_house

            elif park_name and (primary_name == "Neighborhood Park" or p_id == "loc_local_park"):

                primary_name = park_name

            elif primary_name in ("Local Café", "Sunny Days Café") or p_id == "loc_cafe":

                primary_name = cafe_name

            elif primary_name in ("Game Arcade", "Pixel Paradise Arcade") or p_id == "loc_arcade":

                primary_name = arcade_name

            elif primary_name == "Ripperdoc Clinic" or p_id == "loc_ripperdoc_clinic":

                primary_name = ripperdoc_name

            elif primary_name == "Friend's House" or p_id == "loc_friend_house":

                # Do not seed static friend's house

                continue

            if is_urban_anomalous_scenario(scenario_key):
                primary_name = get_session_urban_facility_name(session_id, z_id, p_id, primary_name, scenario_key, char_name)
            primary_name = resolve_session_location_tokens(session_id, primary_name, scenario_key, char_name)

            for sub in primary.get("sub_locations") or []:

                s_id = sub.get("id", "")

                sub_name = sub.get("name") or resolve_default_sublocation(primary_name, zone_name, session_id=session_id, scenario_key=scenario_key, char_name=char_name)

                if classroom_name and (sub_name == "Homeroom Classroom" or s_id == "loc_homeroom"):
                    sub_name = classroom_name
                elif (sub_name == "Player's Desk" or s_id == "sub_player_desk") and (p_id == "loc_homeroom" or "homeroom" in primary_name.lower()):

                    sub_name = player_desk
                elif is_urban_anomalous_scenario(scenario_key) and s_id.startswith(("loc_hq_", "sub_priv1_", "sub_priv2_")):
                    sub_name = get_session_urban_facility_name(session_id, "zone_agency_hq", s_id, sub_name, scenario_key, char_name)

                sub_name = resolve_session_location_tokens(session_id, sub_name, scenario_key, char_name)

                loc_id = s_id or f"loc_{_slugify(zone_name)}_{_slugify(primary_name)}_{_slugify(sub_name)}"



                if loc_id in existing_loc_ids or (primary_name.lower(), sub_name.lower()) in existing_tuples:

                    continue



                to_insert.append({

                    "session_id": session_id,

                    "location_id": loc_id,

                    "zone_name": zone_name,

                    "primary_name": primary_name,

                    "sub_name": sub_name,

                    "atmosphere": atmosphere,

                    "is_dynamic": 0

                })

                existing_loc_ids.add(loc_id)

                existing_tuples.add((primary_name.lower(), sub_name.lower()))

    if to_insert:
        with db.UnitOfWork():
            for item in to_insert:
                db.save_session_location(**item)

    _reconcile_faction_hq_locations(session_id, scenario_key, school_name)
    try:
        from .graph_seeder import ensure_session_spatial_graph_seeded
        ensure_session_spatial_graph_seeded(session_id, scenario_key, char_name=char_name)
        sess = db.get_session(session_id)
        if sess and not sess.get("current_node_id") and sess.get("current_location"):
            init_nid = db.resolve_node_id_from_location(session_id, sess["current_location"])
            if init_nid:
                db.update_session(session_id, current_node_id=init_nid)
    except Exception:
        pass

def resolve_companion_origin_location(session_id: int, current_location: str, scen_key: str = "fantasy") -> str:

    """

    Determines the canonical home/origin location where a companion resides and returns to upon dismissal.

    1. If current_location is already a safe hub (town, tavern, village, guild, academy), returns current_location.

    2. If in a wilderness / non-safe zone, looks for a discovered safe hub in the same Zone.

    3. Fallback: returns default safe hub for the scenario.

    """

    if not current_location:

        current_location = "Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table"

    

    if is_hub_location(current_location):

        return current_location



    z_name = get_zone_location_name(current_location)

    

    # Check known lorebook places in the session for a hub in the same zone

    try:

        lore = db.get_lorebook(session_id)

        for pl in lore.get("place", []):

            pl_name = pl.get("name", "")

            if is_hub_location(pl_name) and z_name.lower() in pl_name.lower():

                return pl_name

        for pl in lore.get("place", []):

            pl_name = pl.get("name", "")

            if is_hub_location(pl_name):

                return pl_name

    except Exception:

        pass



    # Scenario-specific default safe hub fallback

    scen = str(scen_key).lower()

    if is_school_scenario(scen):

        return "Oakhaven Private Academy ➔ Main Courtyard ➔ Central Plaza"

    elif "cyberpunk" in scen:

        return "Neo-Arcadia ➔ The Neon Den Tavern ➔ Main Bar"

    elif "sci_fi" in scen:

        return "Aegis Station ➔ Promenade Commons ➔ Cantina"

    elif "steampunk" in scen:

        return "Aethelgard ➔ Copper Kettle Tavern ➔ Common Room"

    elif "apocalypse" in scen:

        return "The Outpost ➔ Sanctuary Shelter ➔ Common Hall"

    else:

        return "Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table"


from .hierarchy import get_zone_location_name, parse_tiered_location
from .attributes import is_hub_location, is_location_engine_enabled
