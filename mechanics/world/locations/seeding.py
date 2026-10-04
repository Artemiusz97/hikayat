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

    zones = scen_data.get("zones") or []

    if zones:

        z_name = zones[0].get("name", "World Region")

        if z_name == "Main Academy Building" or zones[0].get("id") == "zone_school_main" or is_school_scenario(scenario_key):

            z_name = get_session_school_name(session_id, scenario_key)

        primaries = zones[0].get("primary_locations") or []

        if primaries:

            p_name = primaries[0].get("name", "Main Area")

            if p_name == "Homeroom Classroom" or primaries[0].get("id") == "loc_homeroom" or is_school_scenario(scenario_key):

                p_name = get_session_classroom_name(session_id, scenario_key)

            elif p_name == "Player's House" or primaries[0].get("id") == "loc_player_house":

                p_name = get_session_player_house_name(session_id, char_name, scenario_key)

            elif p_name == "Neighborhood Park" or primaries[0].get("id") == "loc_local_park":

                p_name = get_session_park_name(session_id, scenario_key)



            subs = primaries[0].get("sub_locations") or []

            if subs:

                s_name = subs[0].get("name", "Main Area")

                p_id = primaries[0].get("id", "")

                if (s_name == "Player's Desk" or subs[0].get("id") == "sub_player_desk") and (p_id == "loc_homeroom" or "homeroom" in p_name.lower()):

                    s_name = get_session_player_desk_name(session_id, char_name)

            else:

                s_name = "Main Area"

            return (z_name, p_name, s_name)

        return (z_name, "Main Area", "Main Area")

    return ("World Region", "Main Area", "Main Area")

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

            if z_name == "Main Academy Building" or z_id == "zone_school_main" or is_school_scenario(scenario_key):

                z_name = get_session_school_name(session_id, scenario_key) if session_id else "Suimei Institute"

            z_hub = bool(z.get("is_hub", False))

            for p in z.get("primary_locations", []):

                p_id = p.get("id", "")

                p_name = p.get("name", "Main Area")

                if p_name == "Homeroom Classroom" or p_id == "loc_homeroom" or is_school_scenario(scenario_key):

                    p_name = get_session_classroom_name(session_id, scenario_key) if session_id else "Homeroom Classroom"

                elif p_name == "Player's House" or p_id == "loc_player_house":

                    p_name = get_session_player_house_name(session_id, char_name, scenario_key)

                elif p_name == "Neighborhood Park" or p_id == "loc_local_park":

                    p_name = get_session_park_name(session_id, scenario_key)



                subs = p.get("sub_locations", [])

                if subs:

                    for s in subs:

                        s_name = s.get("name", "Main Area")

                        if (s_name == "Player's Desk" or s.get("id") == "sub_player_desk") and (p_id == "loc_homeroom" or "homeroom" in p_name.lower()):

                            s_name = get_session_player_desk_name(session_id, char_name)

                        seeded_triples.append((z_name, p_name, s_name, z_hub))

                else:

                    seeded_triples.append((z_name, p_name, "Main Area", z_hub))



    if not seeded_triples:

        return get_default_tiered_location(scenario_key, session_id=session_id, char_name=char_name)



    # If preferred_hint is provided, check for a match

    if preferred_hint:

        hint_clean = preferred_hint.lower().strip()

        hint_parts = [hp.strip() for hp in re.split(r"[➔\->|/]", hint_clean) if hp.strip()]



        # Priority 1: Match primary place specifically (e.g. 'School Rooftop')

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

            return random.choice(matching_hint)



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



    return random.choice(candidates)

def _reconcile_faction_hq_locations(session_id: int, scenario_key: str = "high_school_drama", school_name: str = ""):

    """Ensures every faction recorded in the database has a grounded physical HQ location in session_locations."""

    if not session_id:

        return

    try:

        factions = db.get_factions(session_id)

        if not factions:

            return



        existing_locs = db.get_session_locations(session_id) or []

        existing_primaries = {(r.get("primary_name") or "").strip().lower() for r in existing_locs}

        existing_ids = {(r.get("location_id") or "").strip().lower() for r in existing_locs}



        arts_zone = get_session_cultural_arts_name(session_id, scenario_key)

        abandoned_zone = get_session_abandoned_campus_name(session_id, scenario_key)

        athletics_zone = get_session_athletics_complex_name(session_id, scenario_key)

        commons_zone = get_session_student_commons_name(session_id, scenario_key)

        academic_zone = school_name or get_session_school_name(session_id, scenario_key) or "Westlake Academy"



        # Preset sub-locations mapping for known starter HQs in high school drama

        preset_hqs = {

            "school auditorium stage": {

                "zone": arts_zone,

                "name": "School Auditorium Stage",

                "subs": ["Auditorium Stage", "Backstage Dressing Area", "Prop & Costume Storeroom"]

            },

            "old storage room 3-b": {

                "zone": abandoned_zone,

                "name": "Old Storage Room 3-B",

                "subs": ["Club Meeting Table", "Tarot & Divination Corner", "Archive Bookshelves"]

            },

            "old east wing music room": {

                "zone": arts_zone,

                "name": "Old East Wing Music Room",

                "subs": ["Upright Piano Alcove", "Velvet Lounge Couch", "Soundproof Storage Closet"]

            },

            "behind gym storage sheds": {

                "zone": athletics_zone,

                "name": "Behind Gym Storage Sheds",

                "subs": ["Brawler Hangout Benches", "Behind Equipment Shed", "Graffiti Brick Wall"]

            },

            "student council office": {

                "zone": arts_zone,

                "name": "Student Council Office",

                "subs": ["President's Desk", "Meeting Table", "Archive Files & Safe"]

            },

            "main gymnasium": {

                "zone": athletics_zone,

                "name": "Main Gymnasium",

                "subs": ["Basketball Court", "Upper Concourse Bleachers", "Locker & Shower Room"]

            }

        }



        for fac in factions:

            hq_raw = (fac.get("hq_location_id") or "").strip()

            if not hq_raw:

                continue



            # If hq_raw contains tiered delimiters, parse into clean atomic primary name

            if any(d in hq_raw for d in ("➔", "->", ">", "|")):

                fz, fp, fs = parse_tiered_location(hq_raw, scenario_key, session_id=session_id)

                hq_raw = fp

                with db.get_conn() as conn:

                    conn.execute("UPDATE factions SET hq_location_id = ? WHERE id = ?", (fp, fac["id"]))

                    conn.commit()



            hq_lower = hq_raw.lower()

            if hq_lower in existing_primaries or hq_lower in existing_ids:

                continue



            if hq_lower in preset_hqs:

                cfg = preset_hqs[hq_lower]

                target_z = cfg["zone"]

                p_name = cfg["name"]

                sub_list = cfg["subs"]

            else:

                if is_school_scenario(scenario_key):

                    if any(k in hq_lower for k in ("gym", "field", "shed", "track", "outdoor", "court", "sheds", "brawler", "delinquent", "sports", "martial", "tatami")):

                        target_z = athletics_zone

                    elif any(k in hq_lower for k in ("commons", "cafeteria", "canteen", "vending", "greenhouse", "courtyard", "garden")):

                        target_z = commons_zone

                    elif any(k in hq_lower for k in ("council", "stuco", "drama", "auditorium", "music", "piano", "art", "media", "broadcast", "club", "esport", "gaming")):

                        target_z = arts_zone

                    elif any(k in hq_lower for k in ("occult", "mystery", "abandoned", "clock tower", "derelict", "storage room 3")):

                        target_z = abandoned_zone

                    else:

                        target_z = academic_zone

                else:

                    target_z = "World Region"

                p_name = hq_raw

                sub_list = [f"{p_name} Entrance", f"{p_name} Main Area", f"{p_name} Inner Room"]



            for sub in sub_list:

                loc_id = f"loc_{_slugify(target_z)}_{_slugify(p_name)}_{_slugify(sub)}"

                db.save_session_location(

                    session_id=session_id,

                    location_id=loc_id,

                    zone_name=target_z,

                    primary_name=p_name,

                    sub_name=sub,

                    atmosphere="",

                    is_dynamic=0

                )

            existing_primaries.add(p_name.lower())

    except Exception:

        pass

def ensure_session_locations_seeded(session_id: int, scenario_key: str = "high_school_drama", char_name: str = ""):

    """Ensures seed locations exist in SQLite for the session."""

    if not is_location_engine_enabled(scenario_key):

        return



    existing = db.get_session_locations(session_id)

    school_name = get_session_school_name(session_id, scenario_key) if is_school_scenario(scenario_key) else None

    classroom_name = get_session_classroom_name(session_id, scenario_key) if is_school_scenario(scenario_key) else None

    player_desk = get_session_player_desk_name(session_id, char_name)

    player_house = get_session_player_house_name(session_id, char_name, scenario_key)

    park_name = get_session_park_name(session_id, scenario_key)



    scen_data = get_scenario_seed_data(scenario_key)

    zones = scen_data.get("zones") or []



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

        elif z_id == "zone_city_center" or zone_name == "City Center & Megacorp Plaza":

            zone_name = f"{cyber_city} - City Center"

        elif z_id == "zone_downtown" or zone_name == "Downtown Commercial Core":

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

        elif z_id == "zone_mountain_park" or zone_name == "Recreational Mountain Park":

            zone_name = rec_park_name

        elif z_id == "zone_commercial" or zone_name == "Commercial District":

            zone_name = commercial_name

        elif z_id == "zone_residential" or zone_name == "Residential Neighborhood":

            zone_name = residential_name



        if "theme" in zone or "features" in zone:

            env_dict = {

                "theme": zone.get("theme", ""),

                "features": zone.get("features", ""),

                "sensory": zone.get("sensory", zone.get("atmosphere", ""))

            }

            atmosphere = json.dumps(env_dict)

        else:

            atmosphere = zone.get("atmosphere", "")



        for primary in zone.get("primary_locations") or []:

            p_id = primary.get("id", "")

            primary_name = primary.get("name", "Main Area")



            # Procedurally personalize Primary place names

            if classroom_name and (primary_name == "Homeroom Classroom" or p_id == "loc_homeroom"):

                primary_name = classroom_name

            elif primary_name == "Player's House" or p_id == "loc_player_house":

                primary_name = player_house

            elif primary_name == "Neighborhood Park" or p_id == "loc_local_park":

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



            for sub in primary.get("sub_locations") or []:

                s_id = sub.get("id", "")

                sub_name = sub.get("name", "Main Area")

                if (sub_name == "Player's Desk" or s_id == "sub_player_desk") and (p_id == "loc_homeroom" or "homeroom" in primary_name.lower()):

                    sub_name = player_desk

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
