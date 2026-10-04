from __future__ import annotations
from .constants import *
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import db
from .seeds import *
from .seeds import _load_seeds, _slugify, _SEED_PATH

def get_clean_leaf_location(location_str: str) -> str:

    """Returns the concise 3rd tier sub-location name from a tiered location string."""

    if not location_str:

        return "Local Area"

    loc = str(location_str).strip()

    if "➔" in loc:

        parts = [p.strip() for p in loc.split("➔") if p.strip()]

        return parts[-1] if parts else loc

    if "->" in loc:

        parts = [p.strip() for p in loc.split("->") if p.strip()]

        return parts[-1] if parts else loc

    return loc

def get_zone_location_name(location_str: str) -> str:

    """Returns the Tier 1 Zone name from a tiered location string."""

    if not location_str:

        return "Local Area"

    loc = str(location_str).strip()

    if "➔" in loc:

        parts = [p.strip() for p in loc.split("➔") if p.strip()]

        return parts[0] if parts else loc

    if "->" in loc:

        parts = [p.strip() for p in loc.split("->") if p.strip()]

        return parts[0] if parts else loc

    return loc

def get_primary_location_name(location_str: str) -> str:

    """Returns the Tier 2 Primary Place name from a tiered location string."""

    if not location_str:

        return "Local Area"

    loc = str(location_str).strip()

    if "➔" in loc:

        parts = [p.strip() for p in loc.split("➔") if p.strip()]

        return parts[1] if len(parts) >= 2 else (parts[0] if parts else loc)

    if "->" in loc:

        parts = [p.strip() for p in loc.split("->") if p.strip()]

        return parts[1] if len(parts) >= 2 else (parts[0] if parts else loc)

    return loc

def get_clean_zone_short_name(zone_name: str) -> str:

    """Extracts a short, punchy region name (e.g. 'Forest of Sunlit Vale' -> 'Sunlit Vale')."""

    if not zone_name:

        return "Regional"

    z = str(zone_name).strip()

    if " & " in z:

        z = z.split(" & ")[0].strip()

    for pfx in ("Forest of ", "Woods of ", "Kingdom of ", "Empire of ", "Plains of ", "Mountains of ", "Hills of ", "Valley of ", "City of ", "Royal Capital of ", "Imperial Capital of ", "Central "):

        if z.startswith(pfx):

            z = z[len(pfx):].strip()

            break

    for sfx in (" Forest", " Woodlands", " Mountain", " Mountains", " Plains", " Farmlands", " Harbor", " Capital", " Range"):

        if z.endswith(sfx) and len(z) > len(sfx):

            z = z[:-len(sfx)].strip()

            break

    return z or zone_name

def resolve_session_location_tokens(session_id: int = 0, template: str = "", scenario_key: str = "fantasy", char_name: str = "") -> str:

    """Replaces procedural tokens like {session_kingdom}, {session_school}, etc. with unique session-seeded names."""

    if not template or "{" not in template:

        return template or ""

    

    res = str(template)

    if "{session_kingdom}" in res:

        k_name = get_session_kingdom_name(session_id, scenario_key)

        if "fantasy" in scenario_key or "isekai" in scenario_key or "grimdark" in scenario_key:

            res = res.replace("{session_kingdom}", f"Royal Capital of {k_name}")

        else:

            res = res.replace("{session_kingdom}", k_name)

    if "{session_capital}" in res:

        k_name = get_session_kingdom_name(session_id, scenario_key)

        res = res.replace("{session_capital}", f"Royal Capital of {k_name}")

    if "{session_forest}" in res:

        res = res.replace("{session_forest}", get_session_forest_name(session_id, scenario_key))

    if "{session_ancient_forest}" in res:

        res = res.replace("{session_ancient_forest}", get_session_ancient_forest_name(session_id, scenario_key))

    if "{session_mountain}" in res:

        res = res.replace("{session_mountain}", get_session_mountain_name(session_id, scenario_key))

    if "{session_desert}" in res:

        res = res.replace("{session_desert}", get_session_desert_name(session_id, scenario_key))

    if "{session_caves}" in res:

        res = res.replace("{session_caves}", get_session_caves_name(session_id, scenario_key))

    if "{session_school}" in res:

        res = res.replace("{session_school}", get_session_school_name(session_id, scenario_key))

    if "{session_classroom}" in res:

        res = res.replace("{session_classroom}", get_session_classroom_name(session_id, scenario_key))

    if "{session_park}" in res:

        res = res.replace("{session_park}", get_session_park_name(session_id, scenario_key))

    if "{session_cafe}" in res:

        res = res.replace("{session_cafe}", get_session_cafe_name(session_id, scenario_key))

    if "{session_arcade}" in res:

        res = res.replace("{session_arcade}", get_session_arcade_name(session_id, scenario_key))

    if "{session_cyber_city}" in res:

        res = res.replace("{session_cyber_city}", get_session_cyber_city_name(session_id, scenario_key))

    if "{session_ripperdoc}" in res:

        res = res.replace("{session_ripperdoc}", get_session_ripperdoc_name(session_id, scenario_key))

    if "{session_station}" in res:

        res = res.replace("{session_station}", get_session_station_name(session_id))

    if "{session_planet}" in res:

        res = res.replace("{session_planet}", get_session_planet_name(session_id))

    if "{session_airship}" in res:

        res = res.replace("{session_airship}", get_session_airship_name(session_id, scenario_key))

    if "{session_seaside}" in res:

        res = res.replace("{session_seaside}", get_session_seaside_name(session_id, scenario_key))

    if "{session_recreation_park}" in res:

        res = res.replace("{session_recreation_park}", get_session_recreation_park_name(session_id, scenario_key))

    if "{session_commercial}" in res:

        res = res.replace("{session_commercial}", get_session_commercial_district_name(session_id, scenario_key))

    if "{session_residential}" in res:

        res = res.replace("{session_residential}", get_session_residential_neighborhood_name(session_id, scenario_key))

    if "{session_player_house}" in res:

        res = res.replace("{session_player_house}", get_session_player_house_name(session_id, char_name, scenario_key))

    if "{session_player_desk}" in res:

        res = res.replace("{session_player_desk}", get_session_player_desk_name(session_id, char_name))

    return res

def _build_session_zone_index(session_id: int = 0, scenario_key: str = "fantasy") -> dict:

    zones = {}

    school_name = get_session_school_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""

    residential_name = get_session_residential_neighborhood_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""

    commercial_name = get_session_commercial_district_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""

    

    scen_data = get_scenario_seed_data(scenario_key)

    for z in scen_data.get("zones", []):

        z_name = z.get("name", "")

        if school_name and z_name in ("Main Academy Campus", "Main Academy Building"):

            z_name = school_name

        elif residential_name and z_name in ("Residential Neighborhood", "Residential Area"):

            z_name = residential_name

        elif commercial_name and z_name in ("Commercial District", "Shopping District"):

            z_name = commercial_name

            

        primaries = z.get("primary_locations", [])

        gateway_p = "Main Area"

        if primaries:

            foyer = next((p for p in primaries if "foyer" in p.get("name", "").lower() or "entrance" in p.get("name", "").lower()), None)

            gateway_p = foyer.get("name") if foyer else primaries[0].get("name", "Main Area")

        if gateway_p in ("Homeroom Classroom", "loc_homeroom"):

            gateway_p = get_session_classroom_name(session_id, scenario_key)

        

        if z_name:

            zones[z_name.strip().lower()] = (z_name, gateway_p, "Main Area")

            short = get_clean_zone_short_name(z_name).lower()

            if short and short != z_name.strip().lower():

                zones[short] = (z_name, gateway_p, "Main Area")

    return zones

def _build_session_spatial_index(session_id: int = 0, scenario_key: str = "fantasy") -> tuple[dict, dict]:

    """

    Builds maps of lower_name -> (zone_name, primary_name) and lower_name -> (zone_name, primary_name, sub_name)

    from session_locations (ignoring corrupted entries) and seed data.

    """

    primaries = {}

    subs = {}



    school_name = get_session_school_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""

    residential_name = get_session_residential_neighborhood_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""

    commercial_name = get_session_commercial_district_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""



    # 1. From Seed Data

    scen_data = get_scenario_seed_data(scenario_key)

    for z in scen_data.get("zones", []):

        z_name = z.get("name", "")

        if school_name and z_name in ("Main Academy Campus", "Main Academy Building"):

            z_name = school_name

        elif residential_name and z_name in ("Residential Neighborhood", "Residential Area"):

            z_name = residential_name

        elif commercial_name and z_name in ("Commercial District", "Shopping District"):

            z_name = commercial_name



        for p in z.get("primary_locations", []):

            p_name = p.get("name", "")

            if p_name:

                primaries[p_name.strip().lower()] = (z_name, p_name)

                for s in p.get("sub_locations", []):

                    s_name = s.get("name", "")

                    if s_name:

                        subs[s_name.strip().lower()] = (z_name, p_name, s_name)



    zones_index = _build_session_zone_index(session_id, scenario_key)

    # 2. From SQLite session_locations

    if session_id:

        try:

            existing = db.get_session_locations(session_id)

            for r in existing:

                z_name = r.get("zone_name", "")

                p_name = r.get("primary_name", "")

                s_name = r.get("sub_name", "")

                s_lower = s_name.strip().lower()

                # Skip known corrupted school entries

                if z_name in ("Westlake Academy", "Main Academy Building", "Main Academy Campus") and p_name.strip().lower() in ("bedroom", "maya's room", "living room", "kitchen", "front porch", "your bedroom", "bathroom"):

                    continue

                # Skip known corrupted residential entries (school facilities under residential or commercial zone)

                if ("residential" in z_name.lower() or "commercial" in z_name.lower()) and any(k in p_name.lower() for k in ("classroom", "homeroom", "science lab", "library", "staff room", "student council", "gymnasium")):

                    continue

                # Skip incongruous containers or tier demotions in dynamic entries

                if r.get("is_dynamic"):

                    if p_name.strip().lower() in primaries:

                        continue

                    if s_lower in zones_index or s_lower in primaries:

                        continue

                    if is_incongruous_container(p_name, s_name, session_id=0, scenario_key=scenario_key):

                        continue



                if z_name and p_name:

                    primaries[p_name.strip().lower()] = (z_name, p_name)

                    if s_name and s_lower != "main area":

                        subs[s_lower] = (z_name, p_name, s_name)

        except Exception:

            pass



    return primaries, subs

def _resolve_reverse_hierarchy(parts: list[str], scenario_key: str = "fantasy", session_id: int = 0, char_name: str = "") -> Optional[Tuple[str, str, str]]:

    if not parts:

        return None



    school_name = get_session_school_name(session_id, scenario_key) if is_school_scenario(scenario_key) else "Westlake Academy"

    residential_name = get_session_residential_neighborhood_name(session_id, scenario_key) if is_school_scenario(scenario_key) else "Sakura Hill Residential Town"

    commercial_name = get_session_commercial_district_name(session_id, scenario_key) if is_school_scenario(scenario_key) else "Chuo Commercial Shopping Arcade"

    player_house = get_session_player_house_name(session_id, char_name, scenario_key)



    DOMESTIC_ROOMS = {

        "bedroom", "your bedroom", "my bedroom", "player bedroom", "player's bedroom",

        "maya's room", "maya's bedroom", "sofia's bedroom",

        "living room", "kitchen", "front porch", "bathroom"

    }



    primaries, subs = _build_session_spatial_index(session_id, scenario_key)



    # Case 1: 1-part string (e.g. "Bedroom", "Maya's Room", "Student Council Office")

    if len(parts) == 1:

        raw_token = parts[0].strip()

        raw_low = raw_token.lower()



        # Check domestic rooms first - they belong strictly to residential zone

        if raw_low in DOMESTIC_ROOMS or any(raw_low == k or raw_low.endswith(" " + k) for k in DOMESTIC_ROOMS):

            if "maya" in raw_low:

                return (residential_name, "Anderson Residence", "Maya's Room")

            if "sofia" in raw_low:

                return (residential_name, "Anderson Residence", "Sofia's Bedroom")

            sub_lbl = "Your Bedroom" if "bedroom" in raw_low else raw_token.title()

            return (residential_name, player_house, sub_lbl)



        # Check if it matches a known Primary Place (e.g. "Student Council Office")

        if raw_low in primaries:

            z_found, p_found = primaries[raw_low]

            return (z_found, p_found, "Main Area")



        # Check if it matches a known Sub-location

        if raw_low in subs:

            z_found, p_found, s_found = subs[raw_low]

            return (z_found, p_found, s_found)



        return None



    # Case 2: 2-part string (e.g. "Artemiusz's House ➔ Bedroom", "Student Council Office ➔ Meeting Table")

    if len(parts) == 2:

        p0 = parts[0].strip()

        p1 = parts[1].strip()

        p0_low = p0.lower()

        p1_low = p1.lower()



        # Check if domestic room in Part 1

        if p1_low in DOMESTIC_ROOMS:

            if "anderson" in p0_low or "maya" in p0_low:

                return (residential_name, "Anderson Residence", "Maya's Room" if "maya" in p1_low else p1)

            return (residential_name, player_house, "Your Bedroom" if "bedroom" in p1_low else p1)



        zones_index = _build_session_zone_index(session_id, scenario_key)

        

        # Tier 1 Zone Demotion Guard (e.g. Artem's House -> St. Michael Academy)

        if p1_low in zones_index:

            return zones_index[p1_low]

            

        # Tier 2 Primary Demotion Guard

        if p0_low in primaries and p1_low in primaries:

            return (primaries[p1_low][0], primaries[p1_low][1], "Main Area")



        # If Part 0 is actually a Primary Location (not a Zone):

        # e.g. "Student Council Office ➔ Meeting Table" or "Artemiusz's House ➔ Living Room"

        if p0_low in primaries:

            z_found, p_found = primaries[p0_low]

            return (z_found, p_found, p1)



        # If Part 1 is a known Primary Place inside Zone Part 0:
        # e.g. "Westlake Academy ➔ Student Council Office" or "Wakaba Residential Town ➔ Class 2-2"
        if is_school_scenario(scenario_key):
            p1_is_academic_room = any(k in p1_low for k in ("homeroom", "classroom", "class "))
            if p1_low in primaries or p1_is_academic_room:
                if p1_low in primaries:
                    z_found, p_found = primaries[p1_low]
                else:
                    z_found, p_found = school_name, p1

                from .constants import CAMPUS_FACILITY_KEYWORDS, RESIDENTIAL_PLACE_KEYWORDS, COMMERCIAL_PLACE_KEYWORDS

                p1_is_campus = any(k in p1_low for k in CAMPUS_FACILITY_KEYWORDS) or p1_is_academic_room
                p1_is_residence = (
                    any(k in p1_low for k in RESIDENTIAL_PLACE_KEYWORDS) or
                    bool(re.search(r"\bhome\b", p1_low)) or
                    any(k in z_found.lower() for k in ("residential", "suburban", "quarter", "neighborhood", "heights"))
                )
                p1_is_commercial = (
                    any(k in p1_low for k in COMMERCIAL_PLACE_KEYWORDS) or
                    any(k in z_found.lower() for k in ("commercial", "shopping", "arcade", "market", "promenade", "strip", "avenue"))
                )

                p0_is_school = any(k in p0_low for k in ("academy", "school", "campus", "high school", "university", "institute", "college")) or p0_low == school_name.lower()
                p0_is_non_campus = (
                    (residential_name and residential_name.lower() in p0_low) or
                    (commercial_name and commercial_name.lower() in p0_low) or
                    any(k in p0_low for k in ("residential", "commercial", "town", "quarter", "neighborhood", "suburban", "campsite", "forest", "harbor", "bay", "arcade", "shopping"))
                )

                if p1_is_campus:
                    chosen_z = z_found if p0_is_non_campus else (p0 if p0 else z_found)
                elif p1_is_residence:
                    if p0_is_school or (commercial_name and commercial_name.lower() in p0_low) or any(k in p0_low for k in ("commercial", "shopping", "arcade", "market")):
                        chosen_z = residential_name if residential_name else z_found
                    else:
                        chosen_z = p0 if p0 else (residential_name or z_found)
                elif p1_is_commercial:
                    if p0_is_school or (residential_name and residential_name.lower() in p0_low) or any(k in p0_low for k in ("residential", "suburban", "town", "neighborhood")):
                        chosen_z = commercial_name if commercial_name else z_found
                    else:
                        chosen_z = p0 if p0 else (commercial_name or z_found)
                else:
                    chosen_z = p0 if p0 else z_found

                return (chosen_z, p_found, "Main Area")
        else:
            if p1_low in primaries:
                z_found, p_found = primaries[p1_low]
                chosen_z = p0 if p0 else z_found
                return (chosen_z, p_found, "Main Area")

        # If Part 1 is in subs:
        if p1_low in subs:
            z_found, p_found = subs[p1_low]
            chosen_z = p0 if p0 else z_found
            return (chosen_z, p_found, s_found)

        return None

    # Case 3: 3-part or more string (e.g. "Westlake Academy ➔ Academic Wing ➔ Class 2-2")
    if len(parts) >= 3:
        p0 = parts[0].strip()
        p1 = parts[1].strip()
        p2 = parts[2].strip()
        p0_low = p0.lower()
        p1_low = p1.lower()
        p2_low = p2.lower()

        zones_index = _build_session_zone_index(session_id, scenario_key)
        
        # 4+ Part String Normalization and Tier Demotion Guards
        if p1_low in zones_index:
            return zones_index[p1_low]
        if p2_low in zones_index:
            return zones_index[p2_low]
        if p1_low in primaries and p2_low in primaries:
            return (primaries[p2_low][0], primaries[p2_low][1], "Main Area")

        # Check if Part 0 is actually a Primary Residence / Establishment (e.g. "Anderson Residence ➔ Maya's Room ➔ Main Area" or "Artemiusz's House ➔ Bedroom ➔ Desk")
        if (p0_low in primaries and "residence" in p0_low) or (
            any(k in p0_low for k in ("residence", "house", "apartment"))
            and not any(k in p0_low for k in ("town", "district", "neighborhood", "campus", "school", "grounds", "park", "pier", "bay", "strip", "promenade", "quarter"))
        ):
            z_found = primaries.get(p0_low, (residential_name, p0))[0] if p0_low in primaries else residential_name
            p_found = primaries.get(p0_low, (residential_name, p0))[1] if p0_low in primaries else p0
            sub_lbl = p1 if p2_low in ("main area", "") else (p2 if p1_low in ("main area", "") else p1)
            return (z_found, p_found, sub_lbl)

        # Domestic room check for 3-part string (e.g. "Westlake Academy -> Artemiusz's House -> Bedroom")
        if p2_low in DOMESTIC_ROOMS and p0_low in (school_name.lower(), "westlake academy", "main academy campus"):
            return (residential_name, player_house, "Your Bedroom" if "bedroom" in p2_low else p2)

        # If Part 1 is a known Primary Place (or academic room) inside Zone Part 0:
        if is_school_scenario(scenario_key):
            p1_is_academic_room = any(k in p1_low for k in ("homeroom", "classroom", "class "))
            if p1_low in primaries or p1_is_academic_room:
                if p1_low in primaries:
                    z_found, p_found = primaries[p1_low]
                else:
                    z_found, p_found = school_name, p1

                s_clean = "Main Area" if any(w in p2_low for w in ("wing", "administration", "faculty", "science", "academic", "media center")) else p2

                from .constants import CAMPUS_FACILITY_KEYWORDS, RESIDENTIAL_PLACE_KEYWORDS, COMMERCIAL_PLACE_KEYWORDS

                p1_is_campus = any(k in p1_low for k in CAMPUS_FACILITY_KEYWORDS) or p1_is_academic_room
                p1_is_residence = (
                    any(k in p1_low for k in RESIDENTIAL_PLACE_KEYWORDS) or
                    bool(re.search(r"\bhome\b", p1_low)) or
                    any(k in z_found.lower() for k in ("residential", "suburban", "quarter", "neighborhood", "heights"))
                )
                p1_is_commercial = (
                    any(k in p1_low for k in COMMERCIAL_PLACE_KEYWORDS) or
                    any(k in z_found.lower() for k in ("commercial", "shopping", "arcade", "market", "promenade", "strip", "avenue"))
                )

                p0_is_school = any(k in p0_low for k in ("academy", "school", "campus", "high school", "university", "institute", "college")) or p0_low == school_name.lower()
                p0_is_non_campus = (
                    (residential_name and residential_name.lower() in p0_low) or
                    (commercial_name and commercial_name.lower() in p0_low) or
                    any(k in p0_low for k in ("residential", "commercial", "town", "quarter", "neighborhood", "suburban", "campsite", "forest", "harbor", "bay", "arcade", "shopping"))
                )

                if p1_is_campus:
                    chosen_z = z_found if p0_is_non_campus else (p0 if p0 else z_found)
                elif p1_is_residence:
                    if p0_is_school or (commercial_name and commercial_name.lower() in p0_low) or any(k in p0_low for k in ("commercial", "shopping", "arcade", "market")):
                        chosen_z = residential_name if residential_name else z_found
                    else:
                        chosen_z = p0 if p0 else (residential_name or z_found)
                elif p1_is_commercial:
                    if p0_is_school or (residential_name and residential_name.lower() in p0_low) or any(k in p0_low for k in ("residential", "suburban", "town", "neighborhood")):
                        chosen_z = commercial_name if commercial_name else z_found
                    else:
                        chosen_z = p0 if p0 else (commercial_name or z_found)
                else:
                    chosen_z = p0 if p0 else z_found

                return (chosen_z, p_found, s_clean)
        else:
            if p1_low in primaries:
                z_found, p_found = primaries[p1_low]
                s_clean = p2
                chosen_z = p0 if p0 else z_found
                return (chosen_z, p_found, s_clean)

        # Inversion check: if Part 2 is a known Primary Place (or matches a canonical primary place), but Part 1 is an intermediate wing/container:
        # (e.g. "Westlake Academy ➔ Administration Wing ➔ Student Council Office")
        if p2_low not in ("main area", "", "none") and not p2_low.endswith("desk"):
            matched_primary = None
            if p2_low in primaries:
                matched_primary = primaries[p2_low]
            else:
                tokens2 = set(p2_low.replace("&", " ").replace("'", "").split())
                for pk, (pz, pp) in primaries.items():
                    if pk in ("main area", "hallways"):
                        continue
                    if pk in p2_low or p2_low in pk:
                        matched_primary = (pz, pp)
                        break
                    pk_tokens = set(pk.replace("&", " ").replace("'", "").split())
                    overlap = tokens2 & pk_tokens
                    if overlap - {"main", "area", "desk", "room", "hall", "spot", "office", "lab", "the", "and", "center", "entrance", "foyer", "residential", "street", (char_name.lower() if char_name else "")}:
                        matched_primary = (pz, pp)
                        break

            is_intermediate_wing = any(w in p1_low for w in ("wing", "media center", "administration", "faculty", "academic"))
            if matched_primary and (p1_low not in primaries or is_intermediate_wing):
                z_found, p_found = matched_primary
                sub_lbl = p1 if not is_intermediate_wing else "Main Area"
                if is_school_scenario(scenario_key):
                    from .constants import CAMPUS_FACILITY_KEYWORDS, RESIDENTIAL_PLACE_KEYWORDS, COMMERCIAL_PLACE_KEYWORDS
                    p_found_low = p_found.lower()
                    p_is_campus = any(k in p_found_low for k in CAMPUS_FACILITY_KEYWORDS) or any(k in p_found_low for k in ("homeroom", "classroom", "class "))
                    p_is_residence = (
                        any(k in p_found_low for k in RESIDENTIAL_PLACE_KEYWORDS) or
                        bool(re.search(r"\bhome\b", p_found_low)) or
                        any(k in z_found.lower() for k in ("residential", "suburban", "quarter", "neighborhood", "heights"))
                    )
                    p_is_commercial = (
                        any(k in p_found_low for k in COMMERCIAL_PLACE_KEYWORDS) or
                        any(k in z_found.lower() for k in ("commercial", "shopping", "arcade", "market", "promenade", "strip", "avenue"))
                    )

                    p0_is_school = any(k in p0_low for k in ("academy", "school", "campus", "high school", "university", "institute", "college")) or p0_low == school_name.lower()
                    p0_is_non_campus = (
                        (residential_name and residential_name.lower() in p0_low) or
                        (commercial_name and commercial_name.lower() in p0_low) or
                        any(k in p0_low for k in ("residential", "commercial", "town", "quarter", "neighborhood", "suburban", "campsite", "forest", "harbor", "bay", "arcade", "shopping"))
                    )

                    if p_is_campus:
                        chosen_z = z_found if p0_is_non_campus else (p0 if p0 else z_found)
                    elif p_is_residence:
                        if p0_is_school or (commercial_name and commercial_name.lower() in p0_low) or any(k in p0_low for k in ("commercial", "shopping", "arcade", "market")):
                            chosen_z = residential_name if residential_name else z_found
                        else:
                            chosen_z = p0 if p0 else (residential_name or z_found)
                    elif p_is_commercial:
                        if p0_is_school or (residential_name and residential_name.lower() in p0_low) or any(k in p0_low for k in ("residential", "suburban", "town", "neighborhood")):
                            chosen_z = commercial_name if commercial_name else z_found
                        else:
                            chosen_z = p0 if p0 else (commercial_name or z_found)
                    else:
                        chosen_z = p0 if p0 else z_found
                else:
                    chosen_z = p0 if p0 else z_found

                return (chosen_z, p_found, sub_lbl)

            if is_intermediate_wing and p0_low in (school_name.lower(), "westlake academy", "main academy campus"):
                return (p0, p2, "Main Area")

        return None

def parse_tiered_location(raw_location: str, scenario_key: str = "fantasy", session_id: int = 0, char_name: str = "") -> Tuple[str, str, str]:

    """

    Parses a location string into (Zone, Primary Place, Sub-Location).

    Accepts formats separated by '➔', '>', '->', or '|'.

    """

    school_name = get_session_school_name(session_id, scenario_key) if (is_school_scenario(scenario_key) or "Main Academy Building" in str(raw_location or "")) else None

    classroom_name = get_session_classroom_name(session_id, scenario_key) if (is_school_scenario(scenario_key) or "Homeroom" in str(raw_location or "")) else None

    player_desk = get_session_player_desk_name(session_id, char_name)

    player_house = get_session_player_house_name(session_id, char_name, scenario_key)

    park_name = get_session_park_name(session_id, scenario_key)



    commercial_name = get_session_commercial_district_name(session_id, scenario_key) if is_school_scenario(scenario_key) else None

    residential_name = get_session_residential_neighborhood_name(session_id, scenario_key) if is_school_scenario(scenario_key) else None



    if not raw_location or not str(raw_location).strip():

        return get_default_tiered_location(scenario_key, session_id=session_id, char_name=char_name)



    delimiters = ["➔", "->", ">", "|"]

    parts = [raw_location]

    for d in delimiters:

        if d in raw_location:

            parts = [p.strip() for p in raw_location.split(d) if p.strip()]

            break



    # Reverse spatial hierarchy resolution: check session_locations / seed data before blind fallback

    rev = _resolve_reverse_hierarchy(parts, scenario_key=scenario_key, session_id=session_id, char_name=char_name)

    if rev:

        z, p, s = rev

    elif len(parts) >= 3:

        z, p, s = parts[0], parts[1], parts[2]

    elif len(parts) == 2:

        # In a 2-part string (e.g., Zone ➔ Primary Location), part 0 is Zone, part 1 is Primary.

        z, p, s = parts[0], parts[1], "Main Area"

    else:

        # 1 part provided: treat as Primary Location within scenario's default Zone

        z_default, _, _ = get_default_tiered_location(scenario_key, session_id=session_id, char_name=char_name)

        z, p, s = z_default, parts[0], "Main Area"



    if school_name and (z == "Main Academy Building" or z == "Academy" or z == "School"):

        z = school_name

    elif commercial_name and (z == "Commercial District" or z.lower() == "commercial district"):

        z = commercial_name

    elif residential_name and (z == "Residential Neighborhood" or z.lower() == "residential neighborhood"):

        z = residential_name



    # RESIDENTIAL ZONE GUARD:

    # Character residences (e.g. "Anderson Residence", "Vance Residence", "Maya's House") are Tier 2 physical places,

    # NEVER Tier 1 zones. If an LLM put a residence in the Tier 1 position:

    if is_school_scenario(scenario_key) and residential_name:

        z_low = str(z or "").lower().strip()

        if z_low in ("anderson residence", (player_house or "").lower()) or (

            any(k in z_low for k in ("residence", "house", "apartment"))

            and not any(k in z_low for k in ("town", "district", "neighborhood", "campus", "school", "grounds", "park", "pier", "bay", "strip", "promenade", "quarter"))

        ):

            correct_primary = z

            correct_sub = p if p and p not in ("Main Area", "") else (s if s not in ("Main Area", "") else "Living Room")

            z = residential_name

            p = correct_primary

            s = correct_sub



    if classroom_name and (p == "Homeroom Classroom" or p == "Homeroom" or p == "loc_homeroom"):

        p = classroom_name

    if is_school_scenario(scenario_key):

        from .constants import CAMPUS_FACILITY_KEYWORDS
        p_low = str(p or "").lower().strip()
        z_low = str(z or "").lower().strip()

        is_campus_fac = any(k in p_low for k in CAMPUS_FACILITY_KEYWORDS)
        is_residence_place = any(k in p_low for k in ("residence", "house", "apartment", "cottage", "manor", "villa")) or bool(re.search(r"home", p_low))
        is_commercial_place = any(k in p_low for k in ("café", "cafe", "arcade", "store", "diner", "bakery", "restaurant", "bookstore", "boba", "mall", "shopping", "boutique", "market", "game center"))

        primaries_idx, _ = _build_session_spatial_index(session_id, scenario_key)

        if is_campus_fac:
            is_non_campus_zone = (
                (residential_name and residential_name.lower() in z_low) or
                (commercial_name and commercial_name.lower() in z_low) or
                any(k in z_low for k in ("residential", "commercial", "town", "quarter", "neighborhood", "campsite", "forest", "harbor", "bay"))
            )
            if is_non_campus_zone:
                if p_low in primaries_idx:
                    z = primaries_idx[p_low][0]
                elif school_name:
                    z = school_name
        elif is_residence_place:
            is_non_res_zone = (
                (school_name and school_name.lower() in z_low) or
                (commercial_name and commercial_name.lower() in z_low) or
                any(k in z_low for k in ("academy", "school", "campus", "high school", "athletics", "gymnasium", "commercial", "arcade", "shopping"))
            )
            if is_non_res_zone:
                if p_low in primaries_idx and any(k in primaries_idx[p_low][0].lower() for k in ("residential", "suburban", "quarter", "neighborhood")):
                    z = primaries_idx[p_low][0]
                elif residential_name:
                    z = residential_name
        elif is_commercial_place:
            is_non_comm_zone = (
                (school_name and school_name.lower() in z_low) or
                (residential_name and residential_name.lower() in z_low) or
                any(k in z_low for k in ("academy", "school", "campus", "high school", "athletics", "gymnasium", "residential", "town", "quarter", "neighborhood"))
            )
            if is_non_comm_zone:
                if p_low in primaries_idx and any(k in primaries_idx[p_low][0].lower() for k in ("commercial", "shopping", "arcade", "market")):
                    z = primaries_idx[p_low][0]
                elif commercial_name:
                    z = commercial_name

    if p in ("Player's House", "Player House", "loc_player_house", "My House", "Your House"):

        p = player_house

    if p in ("Neighborhood Park", "Local Park", "loc_local_park", "Park"):

        p = park_name

    is_in_homeroom = bool(classroom_name and p == classroom_name) or ("homeroom" in str(p or "").lower())

    if is_in_homeroom:

        if s in ("Player's Desk", "sub_player_desk", "Player Desk", "My Desk", "Your Desk") or (char_name and s.endswith("'s Desk") and s != player_desk and not any(role in s for role in ("Friend", "Teacher", "President", "Principal", "Librarian"))):

            s = player_desk

    elif s == player_desk or (char_name and s.lower() == f"{char_name.lower()}'s desk"):

        if "council" in str(p or "").lower():

            s = "President's Desk"

        else:

            s = "Main Area"



    if session_id:

        try:

            kingdom_name = get_session_kingdom_name(session_id, scenario_key)

            if kingdom_name and z.strip().lower() == kingdom_name.strip().lower():

                if "fantasy" in scenario_key or "isekai" in scenario_key or "grimdark" in scenario_key:

                    z = f"Royal Capital of {kingdom_name}"

        except Exception:

            pass



    # Auto-qualify generic Guild Hall names in non-capital zones

    p_clean = p.strip()

    if p_clean in ("Adventurers' Guild Hall", "Adventurers' Guild", "Guild Hall", "Adventurer Guild Hall", "Adventurers Guild Hall"):

        z_low = str(z or "").lower()

        if not any(k in z_low for k in ("capital", "imperial", "solaria", "highspire", "lunaria", "aethelgard", "metropolis", "grand city")):

            p = get_regional_guild_name(z, scenario_key)



    # Detect and auto-correct accidental Tier 2 / Tier 3 inversions by the LLM

    if session_id and len(parts) >= 3:

        try:

            existing = db.get_session_locations(session_id)

            known_primaries_in_z = {

                r["primary_name"].strip().lower(): r["primary_name"]

                for r in existing

                if r.get("zone_name", "").strip().lower() == z.strip().lower() and r.get("primary_name")

            }

            p_lower = p.strip().lower()

            s_lower = s.strip().lower()

            if s_lower in known_primaries_in_z and p_lower not in known_primaries_in_z:

                # LLM placed the known Primary place in the Sub-location slot and a new landmark in the Primary slot.

                # Auto-correct to preserve Tier 2 Primary stability:

                canonical_p = known_primaries_in_z[s_lower]

                s = p

                p = canonical_p

        except Exception:

            pass



    # PHYSICAL CONTAINER COMPATIBILITY GUARD:

    from .movement import is_incongruous_container
    if is_incongruous_container(p, s, session_id=session_id, scenario_key=scenario_key):

        z, p, s = auto_heal_incongruous_location(z, p, s, session_id=session_id, scenario_key=scenario_key)



    # POST-PARSE TIER 1 ZONE INVARIANT:

    # A Tier 1 Zone name can NEVER reside in Tier 2 (primary) or Tier 3 (sub).

    # If it does, promote it to Tier 1 and resolve gateway defaults.

    if session_id:

        try:

            _zi = _build_session_zone_index(session_id, scenario_key)

            p_low_inv = p.strip().lower()

            s_low_inv = s.strip().lower()

            if p_low_inv in _zi and p_low_inv != z.strip().lower():

                # Primary is a Zone — promote it

                z, p, s = _zi[p_low_inv]

            elif s_low_inv in _zi and s_low_inv != z.strip().lower():

                # Sub is a Zone — promote it

                z, p, s = _zi[s_low_inv]

        except Exception:

            pass



    return (z, p, s)

def format_tiered_location_string(zone: str, primary: str, sub: str) -> str:

    """Returns a clean 3-tiered location string."""

    return f"{zone} ➔ {primary} ➔ {sub}"

def parse_zone_environment_data(atm_data: Any) -> dict:

    """

    Normalizes zone environmental data into a structured dict with:

    'theme', 'features', 'sensory'.

    Handles dicts, JSON strings, and legacy plain-text strings seamlessly.

    """

    if not atm_data:

        return {"theme": "", "features": "", "sensory": ""}



    if isinstance(atm_data, dict):

        return {

            "theme": str(atm_data.get("theme") or "").strip(),

            "features": str(atm_data.get("features") or "").strip(),

            "sensory": str(atm_data.get("sensory") or atm_data.get("atmosphere") or "").strip()

        }



    if isinstance(atm_data, str):

        atm_data = atm_data.strip()

        if atm_data.startswith("{"):

            import json

            try:

                parsed = json.loads(atm_data)

                if isinstance(parsed, dict):

                    return {

                        "theme": str(parsed.get("theme") or "").strip(),

                        "features": str(parsed.get("features") or "").strip(),

                        "sensory": str(parsed.get("sensory") or parsed.get("atmosphere") or "").strip()

                    }

            except Exception:

                pass

        return {"theme": "", "features": "", "sensory": atm_data}



    return {"theme": "", "features": "", "sensory": ""}

def infer_zone_theme_fallback(zone_name: str, scen_key: str = "fantasy") -> str:

    """Infers an evocative environment Type/theme for dynamically created or unseeded zones."""

    if not zone_name:

        return "Discovered Region"

    z_lower = zone_name.lower()

    if any(k in z_lower for k in ("expanse", "verdant", "meadow", "grassland", "pasture", "prairie", "plains", "farmland")):

        return "Sprawling Wild Greens & Fertile Plains"

    if any(k in z_lower for k in ("chasm", "abyss", "rift", "underworld", "underdark", "trench")):

        return "Bioluminescent Subterranean Abyssal Realm"

    if any(k in z_lower for k in ("volcanic", "ashland", "caldera", "foundry", "magma", "lava")):

        return "Molten Caldera & Black Ash Wasteland"

    if any(k in z_lower for k in ("tundra", "frozen", "ice", "frost", "snow", "glacial", "cryo")):

        return "Frigid Permafrost & Glacial Expanse"

    if any(k in z_lower for k in ("ancient", "primeval", "elderwood", "deep wood", "great canopy")):

        return "Primeval Enchanted Old-Growth Forest"

    if any(k in z_lower for k in ("wood", "forest", "canopy", "grove", "timber", "thicket", "copse", "wilds")):

        return "Dense Temperate Woodlands & Forester Trails"

    if any(k in z_lower for k in ("mountain", "range", "peak", "crag", "cliff", "highland", "ridge")):

        return "Towering Alpine Peaks & Treacherous Crags"

    if any(k in z_lower for k in ("desert", "dune", "sand", "oasis", "badland", "wastes")):

        return "Arid Sand Ocean & Sun-Scorched Dunes"

    if any(k in z_lower for k in ("swamp", "marsh", "bog", "fen", "mire", "bayou")):

        return "Murky Wetland Swamps & Blighted Marshes"

    if any(k in z_lower for k in ("dungeon", "catacomb", "crypt", "labyrinth", "ruin", "tomb", "shadowland")):

        return "Multi-Level Stone Labyrinth & Trap Chambers"

    if any(k in z_lower for k in ("harbor", "port", "dock", "seaside", "coast", "bay", "beach", "shore")):

        return "Salty Maritime Trading Port & Coastal Bay"

    if any(k in z_lower for k in ("capital", "city", "citadel", "palace", "metropolis", "district", "core", "downtown")):

        return "Fortified Stone Citadel & Bustling Streets"

    if any(k in z_lower for k in ("cave", "cavern", "grotto", "subterranean")):

        return "Natural Crystal Caverns & Subterranean Tunnels"

    if any(k in z_lower for k in ("academy", "school", "campus", "institute")):

        return "Modern Multi-Wing Academic Campus"

    if any(k in z_lower for k in ("airship", "zeppelin", "leviathan", "sovereign", "ironclad", "kraken")):

        return "Majestic Sky Vessel & Aether Flight Decks"

    

    scen = str(scen_key or "").lower()

    if "sci_fi" in scen or "space" in scen or "cyberpunk" in scen:

        return "Unmapped Sector & Outer Rim Outpost"

    if is_school_scenario(scen):

        return "Township District & Scenic Grounds"

    return "Uncharted Wilderness & Frontier Realm"


from .movement import auto_heal_incongruous_location, is_incongruous_container
from .seeding import get_default_tiered_location
from .attributes import get_regional_guild_name
