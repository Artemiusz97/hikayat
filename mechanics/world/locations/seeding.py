from __future__ import annotations
from .constants import *
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import db
from .seeds import *
import sqlite3
from .seeds import _load_seeds, _slugify, _SEED_PATH, _is_school_campus_hq, _SCHOOL_CAMPUS_HQ_KEYWORDS

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
            elif p_id == "fac_agency_residence" or p_name == "Public Agency Residential Hall" or "{session_agency_residence}" in p_name:
                p_name = get_session_agency_residence_name(session_id, scenario_key)

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
                if p.get("is_hidden"):
                    continue

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
                elif p_id == "fac_agency_residence" or p_name == "Public Agency Residential Hall" or "{session_agency_residence}" in p_name:
                    p_name = get_session_agency_residence_name(session_id, scenario_key)

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

        candidates = hazard_candidates or [(z, p, s) for (z, p, s, h) in seeded_triples if not h] or [(z, p, s) for (z, p, s, _) in seeded_triples]

    elif archetype == "delve_threshold":

        candidates = delve_candidates or [(z, p, s) for (z, p, s, h) in seeded_triples if not h] or [(z, p, s) for (z, p, s, _) in seeded_triples]

    else:

        candidates = hub_candidates or [(z, p, s) for (z, p, s, _) in seeded_triples]



    chosen = random.choice(candidates)
    cz, cp, cs = chosen[0], chosen[1], chosen[2]
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

        from .seeds import _is_school_campus_hq, is_major_school_club

        # Remove any legacy standalone Tier 2 facilities belonging to Minor School Clubs when Tier 3 campus rooms exist
        legacy_minor_tier2_names = {
            "behind gym storage sheds",
            "old storage room 3-b",
            "esports & gaming clubroom",
            "esports clubroom & media lab",
            "abandoned wing boiler-room den",
            "occult & mystery club",
            "esports & gaming club",
        }
        with db.get_conn() as conn:
            for lname in legacy_minor_tier2_names:
                conn.execute(
                    "DELETE FROM session_locations WHERE session_id = ? AND lower(primary_name) = ? AND lower(sub_name) != ?",
                    (session_id, lname, lname),
                )
            conn.commit()

        existing_locs = db.get_session_locations(session_id) or []
        existing_primaries = (
            {(r.get("primary_name") or "").strip().lower() for r in existing_locs}
            | {(r.get("sub_name") or "").strip().lower() for r in existing_locs}
        )
        existing_ids = {(r.get("location_id") or "").strip().lower() for r in existing_locs}

        for fac in factions:
            hq_raw = (fac.get("hq_location_id") or "").strip()
            if not hq_raw:
                continue

            if any(d in hq_raw for d in ("➔", "->", ">", "|")):
                orig_hq_raw = hq_raw
                fz, fp, fs = parse_tiered_location(hq_raw, scenario_key, session_id=session_id)
                candidate_hq = (fs or fp).strip()
                is_minor_candidate = (
                    (
                        _is_school_campus_hq(fac.get("name", ""), candidate_hq, scenario_key, session_id=session_id)
                        or _is_school_campus_hq(fac.get("name", ""), orig_hq_raw, scenario_key, session_id=session_id)
                    )
                    and not is_major_school_club(fac.get("name", ""), candidate_hq)
                    and not is_major_school_club(fac.get("name", ""), orig_hq_raw)
                )
                hq_raw = candidate_hq if (is_minor_candidate and candidate_hq) else fp
                with db.get_conn() as conn:
                    conn.execute("UPDATE factions SET hq_location_id = ? WHERE id = ?", (hq_raw, fac["id"]))
                    conn.commit()

            hq_lower = hq_raw.lower()
            is_minor_school = (
                _is_school_campus_hq(fac.get("name", ""), hq_raw, scenario_key, session_id=session_id)
                and not is_major_school_club(fac.get("name", ""), hq_raw)
            )
            if hq_lower in existing_primaries or hq_lower in existing_ids:
                continue

            if world_nodes_present:
                resolved_nid = db.resolve_node_id_from_location(session_id, hq_raw)
                if resolved_nid:
                    continue

            if is_minor_school:
                # Attach minor school club as Tier 3 room instead of Tier 2 standalone facility
                provision_faction_hq_tier2_location(
                    session_id,
                    fac.get("name", "Faction"),
                    scenario_key,
                    hq_raw,
                )
                existing_primaries.add(hq_lower)
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

def _is_school_hq_primary(primary_name: str, location_id: str = "") -> bool:
    """Return True for facilities/HQs that belong strictly on a school campus."""
    p_low = (primary_name or "").strip().lower()
    lid_low = (location_id or "").strip().lower()
    if not p_low:
        return False
    if lid_low.startswith("loc_ct_") or p_low == "grand martial arts dojo & training courtyard":
        return False
    if p_low == "student council office":
        return True
    return any(kw in p_low for kw in _SCHOOL_CAMPUS_HQ_KEYWORDS)


def _heal_misplaced_school_hq_locations(session_id: int, scenario_key: str = "high_school_drama") -> None:
    """Move misplaced school-campus faction HQs (e.g. Student Council Office) out of downtown/urban zones into the school zone."""
    if not session_id:
        return
    scen_low = str(scenario_key or "").strip().lower()
    wnodes = db.get_session_world_nodes(session_id) or []

    school_z_node = None
    for n in wnodes:
        if n.get("node_type") == "ZONE" and n.get("node_id") in (
            "zone_school_campus", "zone_school_main", "zone_school", "zone_campus"
        ):
            school_z_node = n
            break
    if not school_z_node:
        for n in wnodes:
            if n.get("node_type") == "ZONE" and any(
                k in (n.get("name") or "").lower()
                for k in ("academy", "high school", "school campus", "university", "college", "campus")
            ):
                school_z_node = n
                break

    school_z_id = school_z_node["node_id"] if school_z_node else ""
    school_zone_name = (school_z_node.get("name") or "").strip() if school_z_node else ""
    if not school_zone_name and (is_school_scenario(scenario_key) or "anomalous_high_school" in scen_low):
        school_zone_name = get_session_school_name(session_id, scenario_key)
    if not school_zone_name:
        return

    non_school_zone_kws = (
        "downtown", "city center", "commercial", "residential",
        "uptown", "industrial", "docks", "undercity",
    )

    existing_locs = db.get_session_locations(session_id) or []
    misplaced_loc_ids: list[str] = []
    misplaced_primaries: dict[str, tuple[str, str]] = {}
    for r in existing_locs:
        z_cur = (r.get("zone_name") or "").strip()
        p_cur = (r.get("primary_name") or "").strip()
        lid_cur = (r.get("location_id") or "").strip()
        if not z_cur or not p_cur:
            continue
        if z_cur.lower() == school_zone_name.lower():
            continue
        if not any(zk in z_cur.lower() for zk in non_school_zone_kws):
            continue
        if _is_school_hq_primary(p_cur, lid_cur):
            if lid_cur:
                misplaced_loc_ids.append(lid_cur)
            misplaced_primaries.setdefault(p_cur.lower(), (z_cur, p_cur))

    node_map = {n["node_id"]: n for n in wnodes}
    misplaced_fac_nodes: list[dict] = []
    if school_z_id:
        for n in wnodes:
            if n.get("node_type") != "FACILITY":
                continue
            parent_id = n.get("parent_id") or ""
            if parent_id == school_z_id:
                continue
            parent_node = node_map.get(parent_id)
            parent_z_name = (parent_node.get("name") or "").strip() if parent_node else ""
            parent_low = f"{parent_id} {parent_z_name}".lower()
            if not any(zk in parent_low for zk in non_school_zone_kws):
                continue
            n_name = (n.get("name") or "").strip()
            if n_name.lower() in misplaced_primaries or _is_school_hq_primary(n_name, n.get("node_id") or ""):
                misplaced_fac_nodes.append(n)
                if parent_z_name:
                    misplaced_primaries.setdefault(n_name.lower(), (parent_z_name, n_name))

    if not misplaced_loc_ids and not misplaced_fac_nodes:
        return

    patterns = [
        (
            re.compile(re.escape(old_z) + r"\s*(?:➔|->)\s*" + re.escape(orig_p), re.IGNORECASE),
            f"{school_zone_name} ➔ {orig_p}",
        )
        for old_z, orig_p in misplaced_primaries.values()
        if old_z and orig_p
    ]

    moved_fac_ids: list[str] = []
    with db.get_conn() as conn:
        for lid_cur in misplaced_loc_ids:
            conn.execute(
                "UPDATE session_locations SET zone_name=? WHERE session_id=? AND location_id=?",
                (school_zone_name, session_id, lid_cur),
            )

        if school_z_id and misplaced_fac_nodes:
            for fac_node in misplaced_fac_nodes:
                fac_nid = fac_node["node_id"]
                old_z_id = fac_node.get("parent_id") or ""
                conn.execute(
                    "UPDATE world_nodes SET parent_id=?, category='academic', curfew_start_min=1200, curfew_end_min=420 WHERE session_id=? AND node_id=?",
                    (school_z_id, session_id, fac_nid),
                )
                conn.execute(
                    "UPDATE world_nodes SET category='academic', curfew_start_min=1200, curfew_end_min=420 WHERE session_id=? AND parent_id=?",
                    (session_id, fac_nid),
                )
                old_fac_ids = [
                    n["node_id"] for n in wnodes
                    if n.get("node_type") == "FACILITY"
                    and n.get("parent_id") == old_z_id
                    and n.get("node_id") != fac_nid
                ]
                for old_fid in old_fac_ids:
                    conn.execute(
                        "DELETE FROM world_edges WHERE session_id=? AND ((from_node_id=? AND to_node_id=?) OR (from_node_id=? AND to_node_id=?))",
                        (session_id, fac_nid, old_fid, old_fid, fac_nid),
                    )
                moved_fac_ids.append(fac_nid)

        if patterns:
            try:
                wp_rows = conn.execute(
                    "SELECT id, target_location FROM quest_waypoints WHERE session_id=? AND target_location IS NOT NULL",
                    (session_id,),
                ).fetchall()
                for wp in wp_rows:
                    tl = str(wp["target_location"] or "")
                    new_tl = tl
                    for pat, repl in patterns:
                        new_tl = pat.sub(repl, new_tl)
                    if new_tl != tl:
                        conn.execute(
                            "UPDATE quest_waypoints SET target_location=? WHERE id=? AND session_id=?",
                            (new_tl, wp["id"], session_id),
                        )
            except sqlite3.OperationalError:
                pass

    if school_z_id and moved_fac_ids:
        school_siblings = [
            n["node_id"] for n in wnodes
            if n.get("node_type") == "FACILITY"
            and n.get("parent_id") == school_z_id
            and n.get("node_id") not in moved_fac_ids
        ][:3]
        for fac_nid in moved_fac_ids:
            for sf_id in school_siblings:
                db.save_world_edge(
                    session_id,
                    fac_nid,
                    sf_id,
                    travel_minutes=5,
                    edge_type="pathway",
                    is_bidirectional=1,
                )

    if patterns:
        sess_cur = db.get_session(session_id)
        if sess_cur and sess_cur.get("current_location"):
            cur_loc = str(sess_cur["current_location"])
            new_cur_loc = cur_loc
            for pat, repl in patterns:
                new_cur_loc = pat.sub(repl, new_cur_loc)
            if new_cur_loc != cur_loc:
                db.update_session(session_id, current_location=new_cur_loc)


def _heal_agency_residence_and_entrances(session_id: int, scenario_key: str = "anomalous_incursions") -> None:
    """Self-heals legacy static Public Agency Residential Hall names, bogus rooms, mixed-case IDs, and Tier 2/3 transit hub flags."""
    if not session_id:
        return
    res_name = get_session_agency_residence_name(session_id, scenario_key or "anomalous_incursions")
    eff_res_name = res_name or "Public Agency Residential Hall"
    with db.get_conn() as conn:
        # Unconditionally purge bogus 'Tavern Heavy Oak Door' leaked by old "pub" in "public" substring bug
        conn.execute(
            "DELETE FROM session_locations WHERE session_id = ? AND sub_name = 'Tavern Heavy Oak Door' "
            "AND (primary_name = 'Public Agency Residential Hall' OR primary_name = ? OR lower(primary_name) LIKE '%residential hall%')",
            (session_id, eff_res_name),
        )
        bogus_rows = conn.execute(
            "SELECT wn.node_id FROM world_nodes wn "
            "LEFT JOIN world_nodes pn ON pn.session_id = wn.session_id AND pn.node_id = wn.parent_id "
            "WHERE wn.session_id = ? AND wn.node_type = 'ROOM' AND wn.name = 'Tavern Heavy Oak Door' "
            "AND (wn.parent_id = 'fac_agency_residence' OR lower(wn.parent_id) LIKE '%residen%' "
            "OR lower(COALESCE(pn.name, '')) LIKE '%residential hall%')",
            (session_id,),
        ).fetchall()
        for row in bogus_rows:
            bnid = row[0] if not isinstance(row, dict) else row.get("node_id")
            if bnid:
                conn.execute(
                    "DELETE FROM world_edges WHERE session_id = ? AND (from_node_id = ? OR to_node_id = ?)",
                    (session_id, bnid, bnid),
                )
                conn.execute(
                    "DELETE FROM world_nodes WHERE session_id = ? AND node_id = ?",
                    (session_id, bnid),
                )

        # Normalize mixed-case legacy loc_nsfw_Boiler_stair -> loc_nsfw_boiler_stair
        old_stair = conn.execute(
            "SELECT 1 FROM world_nodes WHERE session_id = ? AND node_id = 'loc_nsfw_Boiler_stair'",
            (session_id,),
        ).fetchone()
        if old_stair:
            new_stair = conn.execute(
                "SELECT 1 FROM world_nodes WHERE session_id = ? AND node_id = 'loc_nsfw_boiler_stair'",
                (session_id,),
            ).fetchone()
            if not new_stair:
                conn.execute(
                    "UPDATE world_nodes SET node_id = 'loc_nsfw_boiler_stair' WHERE session_id = ? AND node_id = 'loc_nsfw_Boiler_stair'",
                    (session_id,),
                )
                conn.execute(
                    "UPDATE world_edges SET from_node_id = 'loc_nsfw_boiler_stair' WHERE session_id = ? AND from_node_id = 'loc_nsfw_Boiler_stair'",
                    (session_id,),
                )
                conn.execute(
                    "UPDATE world_edges SET to_node_id = 'loc_nsfw_boiler_stair' WHERE session_id = ? AND to_node_id = 'loc_nsfw_Boiler_stair'",
                    (session_id,),
                )
            else:
                conn.execute(
                    "DELETE FROM world_edges WHERE session_id = ? AND (from_node_id = 'loc_nsfw_Boiler_stair' OR to_node_id = 'loc_nsfw_Boiler_stair')",
                    (session_id,),
                )
                conn.execute(
                    "DELETE FROM world_nodes WHERE session_id = ? AND node_id = 'loc_nsfw_Boiler_stair'",
                    (session_id,),
                )

        if res_name and res_name != "Public Agency Residential Hall":
            conn.execute(
                "UPDATE session_locations SET primary_name = ? WHERE session_id = ? AND primary_name = 'Public Agency Residential Hall'",
                (res_name, session_id),
            )
            conn.execute(
                "UPDATE world_nodes SET name = ? WHERE session_id = ? AND (node_id = 'fac_agency_residence' OR name = 'Public Agency Residential Hall')",
                (res_name, session_id),
            )
            wp_rows = conn.execute(
                "SELECT id, target_location FROM quest_waypoints WHERE session_id = ? AND target_location LIKE '%Public Agency Residential Hall%'",
                (session_id,),
            ).fetchall()
            for wrow in wp_rows:
                wid = wrow[0] if not isinstance(wrow, dict) else wrow.get("id")
                wloc = wrow[1] if not isinstance(wrow, dict) else wrow.get("target_location")
                if wid and wloc:
                    updated_wloc = str(wloc).replace("Public Agency Residential Hall", res_name).replace("Tavern Heavy Oak Door", "Residential Security Lobby & Mailboxes")
                    if updated_wloc != wloc:
                        conn.execute("UPDATE quest_waypoints SET target_location = ? WHERE id = ? AND session_id = ?", (updated_wloc, wid, session_id))
            # Heal real normalized & text columns across persisted session tables
            conn.execute(
                "UPDATE households SET residence_location = REPLACE(residence_location, 'Public Agency Residential Hall', ?) "
                "WHERE session_id = ? AND residence_location LIKE '%Public Agency Residential Hall%'",
                (res_name, session_id),
            )
            conn.execute(
                "UPDATE contacts SET basic_info_json = REPLACE(basic_info_json, 'Public Agency Residential Hall', ?) "
                "WHERE session_id = ? AND basic_info_json LIKE '%Public Agency Residential Hall%'",
                (res_name, session_id),
            )
            conn.execute(
                "UPDATE contacts SET relations_json = REPLACE(relations_json, 'Public Agency Residential Hall', ?) "
                "WHERE session_id = ? AND relations_json LIKE '%Public Agency Residential Hall%'",
                (res_name, session_id),
            )
            conn.execute(
                "UPDATE session_clues SET source_location = REPLACE(source_location, 'Public Agency Residential Hall', ?), "
                "lead_text = REPLACE(lead_text, 'Public Agency Residential Hall', ?) "
                "WHERE session_id = ? AND (source_location LIKE '%Public Agency Residential Hall%' OR lead_text LIKE '%Public Agency Residential Hall%')",
                (res_name, res_name, session_id),
            )
            conn.execute(
                "UPDATE quests SET client_location = REPLACE(client_location, 'Public Agency Residential Hall', ?), "
                "objective = REPLACE(objective, 'Public Agency Residential Hall', ?), "
                "sub_objectives_json = REPLACE(sub_objectives_json, 'Public Agency Residential Hall', ?), "
                "quest_notes = REPLACE(quest_notes, 'Public Agency Residential Hall', ?) "
                "WHERE session_id = ? AND (client_location LIKE '%Public Agency Residential Hall%' OR objective LIKE '%Public Agency Residential Hall%' OR sub_objectives_json LIKE '%Public Agency Residential Hall%' OR quest_notes LIKE '%Public Agency Residential Hall%')",
                (res_name, res_name, res_name, res_name, session_id),
            )
            conn.execute(
                "UPDATE lorebook SET name = REPLACE(name, 'Public Agency Residential Hall', ?), "
                "description = REPLACE(description, 'Public Agency Residential Hall', ?) "
                "WHERE session_id = ? AND (name LIKE '%Public Agency Residential Hall%' OR description LIKE '%Public Agency Residential Hall%')",
                (res_name, res_name, session_id),
            )
            conn.execute(
                "UPDATE sessions SET extra_json = REPLACE(extra_json, 'Public Agency Residential Hall', ?) "
                "WHERE id = ? AND extra_json LIKE '%Public Agency Residential Hall%'",
                (res_name, session_id),
            )
        conn.commit()

    sess_cur = db.get_session(session_id)
    if sess_cur and sess_cur.get("current_location"):
        cur_loc = str(sess_cur["current_location"])
        new_loc = cur_loc.replace("Public Agency Residential Hall", res_name) if (res_name and res_name != "Public Agency Residential Hall") else cur_loc
        if ("Residential Hall" in new_loc or (res_name and res_name in new_loc)) and "Tavern Heavy Oak Door" in new_loc:
            new_loc = new_loc.replace("Tavern Heavy Oak Door", "Residential Security Lobby & Mailboxes")
        if new_loc != cur_loc:
            db.update_session(session_id, current_location=new_loc)

    # Reconcile accurate Tier 2 Facility and Tier 3 Room transit hub flags on static nodes
    from .graph_seeder import infer_is_transit_hub
    def _row_val(r, key: str, idx: int, default=None):
        if isinstance(r, dict):
            return r.get(key, default)
        try:
            return r[key]
        except Exception:
            return r[idx] if len(r) > idx else default

    with db.get_conn() as conn:
        wn_rows = conn.execute(
            "SELECT node_id, parent_id, name, node_type, is_transit_hub, state_json "
            "FROM world_nodes WHERE session_id = ? AND is_dynamic = 0 AND node_type IN ('FACILITY', 'ROOM')",
            (session_id,),
        ).fetchall()
        fac_parent_map = {
            str(_row_val(r, "node_id", 0, "")): str(_row_val(r, "parent_id", 1, "") or "")
            for r in wn_rows
            if _row_val(r, "node_type", 3, "") == "FACILITY"
        }
        hub_updates = []
        for r in wn_rows:
            nid = str(_row_val(r, "node_id", 0, "") or "")
            n_low = nid.lower()
            raw_st = _row_val(r, "state_json", 5, "") or ""
            if "veil_village_key" in str(raw_st) or "kitsune" in n_low or "bunian" in n_low:
                continue
            st_meta: dict[str, Any] = {}
            if raw_st:
                try:
                    st_meta = json.loads(raw_st) if isinstance(raw_st, str) else dict(raw_st)
                except Exception:
                    st_meta = {}
            ntype = str(_row_val(r, "node_type", 3, "") or "")
            pid = str(_row_val(r, "parent_id", 1, "") or "")
            z_id = pid if ntype == "FACILITY" else fac_parent_map.get(pid, "")
            expected_hub = infer_is_transit_hub(
                ntype,
                z_id,
                nid,
                str(_row_val(r, "name", 2, "") or ""),
                explicit_meta=st_meta,
            )
            cur_hub = int(_row_val(r, "is_transit_hub", 4, 0) or 0)
            if cur_hub != int(expected_hub):
                hub_updates.append((int(expected_hub), session_id, nid))
        if hub_updates:
            conn.executemany(
                "UPDATE world_nodes SET is_transit_hub = ? WHERE session_id = ? AND node_id = ?",
                hub_updates,
            )
            conn.commit()


def has_player_nsfw_salon_membership_or_standing(
    session_id: int,
    session: dict[str, Any] | None = None,
    current_day: int | None = None,
    for_atlas_visibility: bool = False,
) -> bool:
    """
    Returns True if the player holds active membership, an invite, or high standing (>= 25 Rep)
    with the NSFW club (Velvet Basement Salon). Reads real DB character/session membership
    since `db.get_factions()` rows do not include `is_member`/`player_rank`.
    """
    if not session_id:
        return False
    sess = dict(session) if isinstance(session, dict) else (db.get_session(session_id) or {})
    if sess.get("nsfw_faction_member"):
        return True
    invited_day = int(sess.get("nsfw_faction_invited_day") or 0)
    if for_atlas_visibility and invited_day > 0:
        return True
    if not for_atlas_visibility and current_day is not None and invited_day >= int(current_day):
        return True

    joined_fids: set[str] = set()
    uid = sess.get("host_user_id")
    if uid:
        char = db.get_character(int(uid))
        jf = str((char or {}).get("joined_faction_id") or "").strip().lower()
        if jf:
            joined_fids.add(jf)
    else:
        for mid in (db.get_session_members(session_id) or []):
            char = db.get_character(int(mid))
            jf = str((char or {}).get("joined_faction_id") or "").strip().lower()
            if jf:
                joined_fids.add(jf)
    anom_state = sess.get("anomalous_faction_state") if isinstance(sess.get("anomalous_faction_state"), dict) else {}
    joined_club = str(anom_state.get("joined_club_name") or "").strip().lower().replace(" ", "_")
    if joined_club:
        joined_fids.add(joined_club)

    for fac in (db.get_factions(session_id) or []):
        f_id = str(fac.get("faction_id") or "").strip().lower()
        f_name = str(fac.get("name") or "").strip().lower()
        f_cat = str(fac.get("category") or "").strip().lower()
        f_hq = str(fac.get("hq_location_id") or "").strip().lower()
        f_hq_nid = str(fac.get("hq_node_id") or "").strip().lower()
        is_nsfw_club = (
            f_cat == "nsfw_club"
            or f_hq_nid in ("loc_nsfw_club_facility", "loc_nsfw_faction_hq")
            or "velvet basement" in f_hq
            or "loc_nsfw_" in f_hq
            or f_id == "velvet_basement_salon"
        )
        if not is_nsfw_club:
            continue
        f_rep = int(fac.get("reputation_score") or fac.get("reputation") or 0)
        p_rank = int(fac.get("player_rank") or 0)
        f_rank = str(fac.get("player_title") or fac.get("member_rank") or "").strip().lower()
        if (
            (f_id and f_id in joined_fids)
            or (f_name and f_name.replace(" ", "_") in joined_fids)
            or bool(fac.get("is_member"))
            or p_rank > 0
            or f_rank not in ("", "none", "outsider", "non-member")
            or f_rep >= 25
        ):
            return True
    return False


def reveal_hidden_club_facility(
    session_id: int,
    node_id: str = "loc_nsfw_club_facility",
    turn_number: int | None = None,
) -> bool:
    """Marks a hidden club facility (e.g. Velvet Basement Salon) as discovered and turn-stamps it for rollback."""
    if not session_id or not node_id:
        return False
    cur_state = db.get_world_node_state(session_id, node_id)
    if cur_state.get("discovered") and not cur_state.get("is_hidden"):
        return True
    eff_turn = turn_number
    if eff_turn is None:
        sess = db.get_session(session_id) or {}
        eff_turn = int(sess.get("turn_count") or 0)
    patch: dict[str, Any] = {
        "discovered": True,
        "is_hidden": False,
        "discovered_turn": cur_state["discovered_turn"] if "discovered_turn" in cur_state else int(eff_turn),
    }
    updated = db.update_world_node_state(session_id, node_id, patch)
    return bool(updated.get("discovered"))


def rollback_hidden_club_discoveries_after_turn(
    session_id: int,
    turn_number: int,
    conn: Any = None,
) -> int:
    """Re-hides hidden club facilities and clears post-turn node unlocks when rolling back after `turn_number`."""
    if not session_id:
        return 0
    from contextlib import nullcontext
    t_num = int(turn_number)
    reverted = 0
    reverted_fac_ids: set[str] = set()
    ctx = nullcontext(conn) if conn is not None else db.get_conn()
    with ctx as c:
        rows = c.execute(
            "SELECT node_id, parent_id, state_json FROM world_nodes WHERE session_id = ? "
            "AND (node_id = 'loc_nsfw_club_facility' OR state_json LIKE '%discovered_turn%' OR state_json LIKE '%unlocked_turn%')",
            (int(session_id),),
        ).fetchall()
        for r in rows:
            nid = r["node_id"] if isinstance(r, dict) or hasattr(r, "keys") else r[0]
            raw_st = (r["state_json"] if isinstance(r, dict) or hasattr(r, "keys") else r[2]) or ""
            try:
                st = json.loads(raw_st) if isinstance(raw_st, str) else dict(raw_st)
            except Exception:
                st = {}
            if not isinstance(st, dict):
                continue
            changed = False
            if "discovered_turn" in st:
                try:
                    if int(st.get("discovered_turn")) > t_num:
                        st["discovered"] = False
                        st["is_hidden"] = True
                        st.pop("discovered_turn", None)
                        for uk in ("unlocked_until_day", "unlocked_permanent", "last_unlock_reason", "unlocked_turn"):
                            st.pop(uk, None)
                        reverted_fac_ids.add(str(nid))
                        reverted += 1
                        changed = True
                except (TypeError, ValueError):
                    pass
            if not changed and "unlocked_turn" in st:
                try:
                    if int(st.get("unlocked_turn")) > t_num:
                        for uk in ("unlocked_until_day", "unlocked_permanent", "last_unlock_reason", "unlocked_turn"):
                            st.pop(uk, None)
                        changed = True
                except (TypeError, ValueError):
                    pass
            if changed:
                c.execute(
                    "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
                    (json.dumps(st), int(session_id), nid),
                )
        for fac_id in reverted_fac_ids:
            child_rows = c.execute(
                "SELECT node_id, state_json FROM world_nodes WHERE session_id = ? AND parent_id = ?",
                (int(session_id), fac_id),
            ).fetchall()
            for cr in child_rows:
                cnid = cr["node_id"] if isinstance(cr, dict) or hasattr(cr, "keys") else cr[0]
                raw_cst = (cr["state_json"] if isinstance(cr, dict) or hasattr(cr, "keys") else cr[1]) or ""
                try:
                    cst = json.loads(raw_cst) if isinstance(raw_cst, str) else dict(raw_cst)
                except Exception:
                    cst = {}
                if isinstance(cst, dict) and any(uk in cst for uk in ("unlocked_until_day", "unlocked_permanent", "last_unlock_reason", "unlocked_turn")):
                    for uk in ("unlocked_until_day", "unlocked_permanent", "last_unlock_reason", "unlocked_turn"):
                        cst.pop(uk, None)
                    c.execute(
                        "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
                        (json.dumps(cst), int(session_id), cnid),
                    )
        if conn is None and (reverted > 0 or reverted_fac_ids):
            c.commit()
    return reverted


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

    _heal_misplaced_school_hq_locations(session_id, scenario_key)
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
    agency_res_name = get_session_agency_residence_name(session_id, scenario_key)
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
            if p_id == "fac_suburbs_townhouse":
                from mechanics.social.origin_mode import is_student_operative
                if not is_student_operative(session_id):
                    continue

            primary_name = primary.get("name", "Main Area")



            # Procedurally personalize Primary place names

            if classroom_name and (primary_name == "Homeroom Classroom" or p_id == "loc_homeroom"):

                primary_name = classroom_name

            elif primary_name == "School Grounds & Athletics":
                primary_name = athletics_name or "Varsity Athletic Directorate & Gymnasium"
            elif p_id == "bld_school_commons" or primary_name == "Student Commons & Central Plaza":
                primary_name = commons_name or "Student Commons & Central Plaza"
            elif primary_name == "Cultural Arts & Student Union":
                primary_name = arts_name or "Cultural & Student Clubroom Wing"
            elif p_id == "bld_abandoned_school" or primary_name == "Abandoned Old Campus Building":
                primary_name = abandoned_name or "Abandoned Old Campus Building"
            elif p_id == "loc_agency_hq" or "{session_agency_hq}" in primary_name:
                primary_name = agency_hq_name
            elif p_id == "fac_agency_residence" or primary_name == "Public Agency Residential Hall" or "{session_agency_residence}" in primary_name:
                primary_name = agency_res_name

            elif primary_name == "Player's House" or p_id == "loc_player_house":
                from .realty_catalog import is_anomalous_realty_scenario
                from mechanics.social.origin_mode import is_student_operative
                primary_name = "Tree-Lined Suburban House" if (is_anomalous_realty_scenario(scenario_key) and not is_student_operative(session_id)) else player_house

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

            from .realty_catalog import ALL_STATIC_RESIDENTIAL_FACILITY_IDS
            if is_urban_anomalous_scenario(scenario_key) and p_id not in ALL_STATIC_RESIDENTIAL_FACILITY_IDS:
                primary_name = get_session_urban_facility_name(session_id, z_id, p_id, primary_name, scenario_key, char_name)
            if primary.get("is_hidden") and primary.get("mundane_name"):
                primary_name = str(primary["mundane_name"])
            primary_name = resolve_session_location_tokens(session_id, primary_name, scenario_key, char_name)

            from .graph_seeder import infer_facility_atmosphere
            fac_atmosphere = infer_facility_atmosphere(
                p_id, primary_name, z_id, primary,
                session_id=session_id, scenario_key=scenario_key, char_name=char_name
            ) or atmosphere

            for sub in primary.get("sub_locations") or []:

                if sub.get("is_hidden"):
                    continue
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

                    "atmosphere": fac_atmosphere,

                    "is_dynamic": 0

                })

                existing_loc_ids.add(loc_id)

                existing_tuples.add((primary_name.lower(), sub_name.lower()))

    if to_insert:
        with db.UnitOfWork():
            for item in to_insert:
                db.save_session_location(**item)

    # Spatial graph is seeded before faction HQ reconciliation below
    try:
        from .graph_seeder import ensure_session_spatial_graph_seeded
        ensure_session_spatial_graph_seeded(session_id, scenario_key, char_name=char_name)
        _reconcile_faction_hq_locations(session_id, scenario_key, school_name)
        _heal_misplaced_school_hq_locations(session_id, scenario_key)
        _heal_agency_residence_and_entrances(session_id, scenario_key)
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
