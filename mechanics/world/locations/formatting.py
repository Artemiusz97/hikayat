from __future__ import annotations
from .constants import *
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import db
from .seeds import *
from .seeds import _load_seeds, _slugify, _SEED_PATH

def format_llm_location_context(session_id: int, current_location_raw: str, scenario_key: str, char_name: str = "") -> str:

    """Formats the location context string and real-time movement rules for the LLM prompt."""

    if not is_location_engine_enabled(scenario_key):

        return ""



    ensure_session_locations_seeded(session_id, scenario_key, char_name=char_name)

    zone, primary, sub = parse_tiered_location(current_location_raw, scenario_key, session_id=session_id, char_name=char_name)

    formatted_current = format_tiered_location_string(zone, primary, sub)



    existing = db.get_session_locations(session_id)

    atm_raw = ""

    for r in existing:

        if r.get("zone_name") == zone and r.get("atmosphere"):

            atm_raw = r.get("atmosphere")

            break



    env_data = parse_zone_environment_data(atm_raw)

    env_lines = []

    if env_data.get("theme"):

        env_lines.append(f"- Zone Theme: {env_data['theme']}")

    if env_data.get("features"):

        env_lines.append(f"- Environmental Features: {env_data['features']}")

    if env_data.get("sensory"):

        env_lines.append(f"- Ambient Sensory: {env_data['sensory']}")



    env_text = ("\n" + "\n".join(env_lines)) if env_lines else ""



    arch_label, _ = get_location_archetype(primary, zone_name=zone, scen_key=scenario_key)



    campus_name = get_session_school_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""

    athletics_name = get_session_athletics_complex_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""

    commons_name = get_session_student_commons_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""

    arts_name = get_session_cultural_arts_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""

    abandoned_name = get_session_abandoned_campus_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""

    comm_name = get_session_commercial_district_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""

    res_name = get_session_residential_neighborhood_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""



    district_lines = []

    if is_school_scenario(scenario_key):

        if campus_name:

            district_lines.append(f"- [Campus - Academic Wing & Entrance Gate]: '{campus_name}' (Classrooms, Homeroom, Teachers' Staff Room, Library, Chemistry Lab, Rooftop, Shoe Lockers & Main Gate)")

        if athletics_name:

            district_lines.append(f"- [Campus - Athletics Complex]: '{athletics_name}' (Main Gymnasium, 400m Running Track, Stadium Field, Swimming Pool Facility, Martial Arts Dojo, Behind Gym Sheds)")

        if commons_name:

            district_lines.append(f"- [Campus - Social Commons & Dining]: '{commons_name}' (Central Courtyard Fountain, Cherry Tree, Campus Dining Hall & Cafeteria, Vending Machine Pavilion, Botanical Glasshouse)")

        if arts_name:

            district_lines.append(f"- [Campus - Cultural Arts & Student Union]: '{arts_name}' (Student Council Office, School Auditorium Stage, Music Wing Rehearsal Hall, Fine Arts Studio, Broadcasting Room, Clubrooms)")

        if abandoned_name:

            district_lines.append(f"- [Campus - Abandoned Old Campus]: '{abandoned_name}' (Decaying Clock Tower, Old Storage Room 3-B, Derelict Old Gymnasium, Boarded Old Infirmary, Overgrown Wings)")

    elif campus_name:

        district_lines.append(f"- [Campus]: '{campus_name}' (Classrooms, Facilities, School Grounds)")



    if comm_name:

        district_lines.append(f"- [Commercial]: '{comm_name}' (Shops, Cafés, Entertainment & Arcades)")

    if res_name:

        district_lines.append(f"- [Residential]: '{res_name}' (Family Residences, Houses, Apartments, Neighborhood Parks)")



    regional_block = ("REGIONAL DISTRICT HIGHLIGHTS:\n" + "\n".join(district_lines) + "\n\n") if district_lines else ""



    res_rule = f"- RESIDENTIAL ZONE RULE: All NPC and Player houses, family residences, apartments, and residential cul-de-sacs MUST ALWAYS be placed in the zone tagged [Residential] ('{res_name}'). NEVER place a character's house inside the Commercial District or School Campus.\n- HOUSEHOLD NAMING CONVENTION: Use the family surname for character residences (e.g. '{res_name} ➔ Anderson Residence ➔ Living Room'). Sibling/family characters share the same household.\n" if res_name else ""



    campus_rules = ""

    if is_school_scenario(scenario_key):

        campus_rules = (

            f"- CAMPUS ZONE TOPOGRAPHY: The school campus is divided into 5 distinct zones: '{campus_name}' (Academic & Main Gate), '{athletics_name}' (Athletics), '{commons_name}' (Social & Dining), '{arts_name}' (Cultural Arts & Clubs), and '{abandoned_name}' (Old Campus & Mystery). When characters move to a clubroom, student council, or auditorium, use '{arts_name}'. When eating lunch or gathering in the plaza/courtyard, use '{commons_name}'. When doing sports or physical training, use '{athletics_name}'.\n"

            f"- CHARACTER'S DESK RULE: A student character's personal desk (e.g. 'Player's Desk' / '<Name>'s Desk') ONLY exists in their designated homeroom classroom (e.g. '{campus_name} ➔ Classroom 2-B (Homeroom) ➔ <Name>'s Desk'). In the Student Council Office, use 'President's Desk', 'Meeting Table', or 'Archive Files & Safe'—NEVER place or generate a student's personal homeroom desk in the council office or other rooms.\n"

        )



    # Format established nearby destinations catalog

    nearby_blocks = []

    curr_zone_places: Dict[str, List[str]] = {}

    for r in existing:

        if r.get("zone_name", "").strip().lower() == zone.strip().lower():

            p_name = r.get("primary_name", "")

            s_name = r.get("sub_name", "")

            if p_name:

                curr_zone_places.setdefault(p_name, [])

                if s_name and s_name not in ("Main Area", "") and s_name not in curr_zone_places[p_name]:

                    curr_zone_places[p_name].append(s_name)



    if curr_zone_places:

        p_lines = []

        for p_k, p_subs in list(curr_zone_places.items())[:6]:

            subs_str = f" ({', '.join(p_subs[:3])})" if p_subs else ""

            p_lines.append(f"  * {p_k}{subs_str}")

        nearby_blocks.append(f"- [Current Zone: {zone}]:\n" + "\n".join(p_lines))



    # Connected zones (e.g. Student Commons if in Arts, Academic, Athletics, Abandoned)

    connected_zones = []

    if is_school_scenario(scenario_key):

        if zone.strip().lower() == arts_name.strip().lower() and commons_name:

            connected_zones.append(commons_name)

        elif zone.strip().lower() == athletics_name.strip().lower() and commons_name:

            connected_zones.append(commons_name)

        elif zone.strip().lower() == abandoned_name.strip().lower() and commons_name:

            connected_zones.append(commons_name)

        elif zone.strip().lower() == campus_name.strip().lower() and commons_name:

            connected_zones.append(commons_name)

        elif zone.strip().lower() == commons_name.strip().lower():

            connected_zones.extend([z for z in (arts_name, campus_name, athletics_name) if z])



    for cz in connected_zones:

        cz_places: Dict[str, List[str]] = {}

        for r in existing:

            if r.get("zone_name", "").strip().lower() == cz.strip().lower():

                p_name = r.get("primary_name", "")

                s_name = r.get("sub_name", "")

                if p_name:

                    cz_places.setdefault(p_name, [])

                    if s_name and s_name not in ("Main Area", "") and s_name not in cz_places[p_name]:

                        cz_places[p_name].append(s_name)

        if cz_places:

            p_lines = []

            for p_k, p_subs in list(cz_places.items())[:5]:

                subs_str = f" ({', '.join(p_subs[:3])})" if p_subs else ""

                p_lines.append(f"  * {p_k}{subs_str}")

            nearby_blocks.append(f"- [Connected Zone (5m walk): {cz}]:\n" + "\n".join(p_lines))



    nearby_dest_section = ""

    if nearby_blocks:

        nearby_dest_section = (

            "ESTABLISHED NEARBY DESTINATIONS (PREFER MATCHING THESE BEFORE CREATING NEW PLACES):\n"

            + "\n".join(nearby_blocks)

            + "\n\n"

        )



    return (

        f"CURRENT SCENE LOCATION (Tiered 3-Level Spatial System):\n"

        f"- Current Position: {formatted_current}{env_text}\n"

        f"- Current Breakdown: [Tier 1: Zone/Biome] = '{zone}' | [Tier 2: Physical Place ({arch_label})] = '{primary}' | [Tier 3: Sub-Location/Spot] = '{sub}'\n\n"

        f"{regional_block}"

        f"{nearby_dest_section}"

        f"SPATIAL SYSTEM RULES:\n"

        f"- Instruction: Report `location` in your JSON response as `Zone Name ➔ Primary Place ➔ Sub-Location`.\n"

        f"- GROUNDED PHYSICAL RULE FOR TIER 2: Tier 2 (Primary Place) MUST ALWAYS be a concrete physical structure, settlement, building, establishment, or distinct geographical feature (e.g. 'Hunter\'s Outpost', 'Old Timber Mill', 'Gnarled Root Archway', 'Bramble-Choked Den', 'Class 1-A (Homeroom)'). NEVER output poetic event titles or abstract phrases (e.g. 'The Blue Flame Beyond the Roots', 'A Quiet Moment', 'The Meeting') as Tier 2.\n"

        f"- EXISTING-LOCATION-FIRST DIRECTIVE: When characters leave an enclosed room to talk privately, seek fresh air, go to gardens/courtyard, or visit a terrace, YOU MUST ALWAYS MATCH AN ESTABLISHED NEARBY VENUE from the catalog above (e.g. use 'Old Garden Terrace', 'Botanical Glasshouse', 'Central Courtyard', or 'Student Clubroom Corridor'). NEVER fabricate a duplicate location or nest outdoor environments inside an indoor room.\n"

        f"- PHYSICAL CONTAINER COMPATIBILITY RULE: Enclosed interior rooms (e.g. '{primary}', 'Homeroom Classroom', 'Teachers\' Staff Room', 'Chemistry Lab') CAN NEVER physically contain outdoor or transitional spaces like a terrace, garden, courtyard, balcony, or rooftop as Tier 3. If characters step out to a terrace or garden, Tier 2 MUST change to that terrace or garden!\n"

        f"- HIERARCHY CONTINUITY RULE: ONLY keep Tier 2 identical if characters remain physically inside '{primary}' (e.g. sitting at a desk, looking through files, walking to the window). As soon as characters leave '{primary}' (e.g. walking through halls, heading out to a terrace or courtyard), Tier 2 MUST be updated to the new place.\n"

        f"{campus_rules}"

        f"{res_rule}"

        f"- REAL-TIME MOVEMENT DIRECTIVE: If the narration describes characters leaving a room/building, walking into a hallway/corridor, traveling to another building, or visiting someone's house, you MUST update `location` in your output to reflect their new setting (e.g. '{zone} ➔ 2F Hallway ➔ Secluded Alcove' or '{res_name or 'Residential Area'} ➔ Anderson Residence ➔ Living Room'). NEVER leave `location` pointing to the previous room if the characters have exited it.\n"

    )

def get_discovered_location_tree(session_id: int, scenario_key: str = "high_school_drama") -> Dict[str, Dict[str, List[str]]]:

    """

    Returns discovered locations grouped by Zone ➔ Primary Place ➔ Sub-Locations.

    Useful for building /map commands and detailed location queries.

    """

    ensure_session_locations_seeded(session_id, scenario_key)

    rows = db.get_session_locations(session_id)



    tree: Dict[str, Dict[str, List[str]]] = {}

    for r in rows:

        z = r.get("zone_name") or "Starting Zone"

        p = r.get("primary_name") or "Starting Location"

        s = r.get("sub_name") or "Focal Spot"



        if z not in tree:

            tree[z] = {}

        if p not in tree[z]:

            tree[z][p] = []

        if s not in tree[z][p]:

            tree[z][p].append(s)



    return tree

def get_discovered_primary_locations(session_id: int, scenario_key: str = "high_school_drama") -> Dict[str, List[str]]:

    """

    Returns unique Primary Locations grouped by Zone.

    Used for the 'Move Location' button dropdown so players select rooms/buildings rather than micro-spots.

    """

    tree = get_discovered_location_tree(session_id, scenario_key)

    result: Dict[str, List[str]] = {}

    for zone_name, primaries in tree.items():

        result[zone_name] = list(primaries.keys())

    return result

def get_zone_summary_tree(session_id: int, scen_key: str = "fantasy", current_loc: str = "", char_name: str = "") -> list[dict]:

    """

    Returns an aggregated list of discovered Zones with their metadata, primary locations,

    atmosphere, tags, and waypoint markers. Used by the interactive World Map UI.

    """

    ensure_session_locations_seeded(session_id, scen_key, char_name=char_name)

    tree = get_discovered_location_tree(session_id, scen_key)

    from mechanics.world.waypoints import get_location_waypoint_markers

    waypoint_markers = get_location_waypoint_markers(session_id)



    curr_z, _, _ = parse_tiered_location(current_loc, scen_key, session_id=session_id, char_name=char_name) if current_loc else ("", "", "")



    # Fetch atmosphere for each zone from session_locations

    rows = db.get_session_locations(session_id)

    zone_atm_map: dict[str, str] = {}

    for r in rows:

        z = r.get("zone_name")

        atm = r.get("atmosphere")

        if z and atm and z not in zone_atm_map:

            zone_atm_map[z] = atm



    summary_list = []

    for zone_name in sorted(tree.keys()):

        primaries_dict = tree[zone_name]

        primary_items = []

        zone_tags_set = set()



        for primary_name in sorted(primaries_dict.keys()):

            val_str = f"{zone_name} ➔ {primary_name}"

            emoji = get_location_emoji(primary_name, zone_name=zone_name, waypoint_markers=waypoint_markers, session_id=session_id, scen_key=scen_key, char_name=char_name)

            

            # Check waypoint tags
            wp_tags = waypoint_markers.get(val_str)
            if not wp_tags:
                val_low = val_str.lower()
                for mk_k, mk_v in waypoint_markers.items():
                    if mk_k.lower() == val_low:
                        wp_tags = mk_v
                        break
            if not wp_tags:
                wp_tags = waypoint_markers.get(primary_name) or []

            desc_parts = []
            if wp_tags:
                for t in wp_tags:
                    clean_t = t.split("]", 1)[-1].strip() if "]" in t else t
                    if clean_t and clean_t not in desc_parts:
                        desc_parts.append(clean_t)

            loc_badges = []
            if wp_tags:
                if any("⚡" in t or "[Story Climax]" in t for t in wp_tags):
                    loc_badges.append("⚡")
                    zone_tags_set.add("⚡ Story Climax")
                if any("⭐" in t or "[Story]" in t for t in wp_tags):
                    loc_badges.append("⭐")
                    zone_tags_set.add("⭐ Story Quest")
                if any("🎯" in t or "[Bounty]" in t for t in wp_tags):
                    loc_badges.append("🎯")
                    zone_tags_set.add("🎯 Bounty Target")
                if any("💌" in t or "[Meetup]" in t for t in wp_tags):
                    loc_badges.append("💌")
                    zone_tags_set.add("💌 Meetup")

            if location_has_bounty_board(primary_name, scen_key=scen_key):
                nb_label, nb_emoji = get_notice_board_label(scen_key)
                loc_badges.append(nb_emoji)

            if location_has_merchant_shop(primary_name, scen_key=scen_key):
                loc_badges.append("🛍️")

            if location_has_faction_hq(primary_name, session_id=session_id):
                loc_badges.append("🏛️")
                zone_tags_set.add("🏛️ Faction HQ")

            try:
                p_house = get_session_player_house_name(session_id, char_name=char_name, scenario_key=scen_key)
                if primary_name == p_house:
                    loc_badges.append("🏠")
                    zone_tags_set.add("🏠 Home")
            except Exception:
                pass

            arch_label, arch_emoji = get_location_archetype(primary_name, zone_name=zone_name, scen_key=scen_key)
            final_emoji = "🏠" if emoji == "🏠" else (arch_emoji or emoji)
            badge_str = " ".join(loc_badges)

            primary_items.append({
                "name": primary_name,
                "emoji": final_emoji,
                "archetype": arch_label,
                "archetype_emoji": arch_emoji,
                "badges": badge_str,
                "quest_tag": "⚡ Story Climax" if "⚡" in loc_badges else ("⭐ Story Quest" if "⭐" in loc_badges else ("🎯 Bounty Target" if "🎯" in loc_badges else ("💌 Meetup" if "💌" in loc_badges else ""))),
                "quest_markers": list(wp_tags),
                "value": val_str,
                "description": badge_str,
                "sub_locations": primaries_dict[primary_name]
            })

        # Check hazard and frontier tags based on zone name / theme
        z_lower = zone_name.lower()
        if any(k in z_lower for k in (
            "frontier", "chasm", "crag", "crags", "badlands", "waste", "wasteland", "cursed", "dungeon", "crater", "ruins",
            "swamp", "marsh", "planet", "world)", "asteroid", "tundra", "ashland", "moors", "catacombs",
            "caldera", "lava", "magma", "cinder", "pyre", "volcanic", "volcano", "abyss", "fissure", "trench", "rift", "crypt",
            "vault", "labyrinth", "mire", "bog", "fen", "permafrost", "dreadfall", "shadowveil", "void"
        )):
            if not is_hub_location(zone_name):
                zone_tags_set.add("🧭 Frontier")

        if any(k in z_lower for k in ("volcanic", "ashland", "caldera", "foundry", "desert", "dunes", "sands", "magma", "lava", "cinder", "infernal", "pyre", "sunscorched")):
            zone_tags_set.add("🌋 Extreme Heat")
        elif any(k in z_lower for k in ("ice", "tundra", "frost", "snow", "glacial", "cryo", "everwinter", "permafrost", "blizzard", "rimewind")):
            zone_tags_set.add("❄️ Freezing Tundra")
        elif any(k in z_lower for k in ("irradiated", "toxic", "radiation", "fallout")):
            zone_tags_set.add("☢️ Radiation Hazard")
        elif any(k in z_lower for k in ("seaside", "coastal", "beach", "harbor", "ocean", "bay", "port", "quay", "pier", "tidehaven")):
            zone_tags_set.add("🌊 Coastal")
        elif any(k in z_lower for k in ("airship", "zeppelin", "leviathan", "sovereign", "ironclad", "kraken", "dreadnought", "titan", "swallow", "hms", "zephyr", "aether", "celestial", "gargantuan")):
            zone_tags_set.add("🎈 Airship")

        from scenario_data import is_mechanic_enabled
        combat_enabled = is_mechanic_enabled(scen_key, "tactical_combat")

        if is_hub_location(zone_name) and combat_enabled:
            zone_tags_set.add("🛡️ Safe Hub")

        is_curr = bool(curr_z and zone_name.strip().lower() == curr_z.strip().lower())
        atm_raw = zone_atm_map.get(zone_name, "")
        env_data = parse_zone_environment_data(atm_raw)
        theme_tagline = env_data.get("theme") or (env_data.get("sensory") if not env_data.get("features") else "")
        if not theme_tagline:
            theme_tagline = infer_zone_theme_fallback(zone_name, scen_key)

        zone_quest_markers = []
        for p_item in primary_items:
            for qm in (p_item.get("quest_markers") or []):
                zone_quest_markers.append({
                    "place_name": p_item["name"],
                    "value": p_item["value"],
                    "marker": qm,
                    "quest_tag": p_item.get("quest_tag", ""),
                })

        summary_list.append({
            "zone_name": zone_name,
            "emoji": get_zone_emoji(zone_name, scen_key),
            "theme": theme_tagline,
            "atmosphere": env_data.get("sensory") or atm_raw,
            "is_current": is_curr,
            "is_hub": is_hub_location(zone_name) if combat_enabled else False,
            "places_count": len(primary_items),
            "primary_locations": primary_items,
            "active_tags": sorted(list(zone_tags_set)),
            "quest_markers": zone_quest_markers,
            "quest_count": len(zone_quest_markers),
        })

    return summary_list


from .seeding import ensure_session_locations_seeded
from .hierarchy import format_tiered_location_string, infer_zone_theme_fallback, parse_tiered_location, parse_zone_environment_data
from .attributes import (
    get_location_archetype, get_location_emoji, get_notice_board_label,
    get_zone_emoji, is_hub_location, is_location_engine_enabled,
    location_has_bounty_board, location_has_faction_hq, location_has_merchant_shop
)
