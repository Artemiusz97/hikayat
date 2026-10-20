from __future__ import annotations
from .constants import *
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import db
from .seeds import *
from .seeds import _load_seeds, _slugify, _SEED_PATH

def build_node_sensory_and_memory_block(session_id: int, curr_node: dict, current_day: int, current_minute: int, scen_key: str = "") -> str:
    """Synthesizes indoor/outdoor time-of-day lighting, acoustics, curfew tension, and persistent room memory."""
    from mechanics.world.schedules import get_time_block_key
    from mechanics.world.locations.access_gate import is_curfew_active, get_node_effective_access_info
    from mechanics.world.world_schedule import is_abandoned_school_node, is_weekend, is_high_school_setting

    if not scen_key and session_id:
        try:
            sess_row = db.get_session(session_id)
            scen_key = (sess_row or {}).get("scenario") or "high_school_drama"
        except Exception:
            scen_key = "high_school_drama"
    elif not scen_key:
        scen_key = "high_school_drama"

    is_hs = is_high_school_setting(scen_key)
    safe_min = int(current_minute or 0) % 1440
    time_block = get_time_block_key(current_minute)
    is_enc = int(curr_node.get("is_enclosed", 1))
    is_academic = curr_node.get("category") == "academic"
    is_after_hours_campus = is_hs and is_academic and not is_abandoned_school_node(curr_node) and (safe_min >= 1200 or safe_min < 420)
    is_weekend_day = is_weekend(current_day)

    # Time-of-day sensory profiles (respecting 20:00-07:00 campus lockdown & weekend quiet)
    if is_after_hours_campus:
        lighting = "Darkened interior illuminated only by pale moonlight or dim dawn light through glass and security fixtures" if is_enc else "Quiet campus grounds under dim twilight or pale early-dawn sky"
        acoustics = "Hushed, empty after-hours stillness where every whisper and footstep reverberates" if is_enc else "Still, deserted campus air and distant town hum"
    elif time_block == "morning":
        lighting = "Crisp morning sunlight slanting through window panes onto dust motes" if is_enc else "Cool, refreshing morning air under bright early daylight"
        if is_hs and is_academic and is_weekend_day:
            acoustics = "Quiet, empty weekend stillness with only distant practice sounds outside" if is_enc else "Peaceful weekend morning breeze with sparse club activity in the distance"
        else:
            acoustics = "Quiet morning murmur with rhythmic hallway footsteps in the distance" if is_enc else "Chirping birds and gentle breeze blowing across open paths"
    elif time_block == "lunch":
        lighting = "Bright midday illumination casting sharp shadows" if is_enc else "Warm overhead sun shining brightly"
        if is_hs and is_academic and is_weekend_day:
            acoustics = "Calm weekend midday quiet indoors" if is_enc else "Relaxed weekend midday breeze and distant athletic training"
        else:
            acoustics = "Lively laughter, chatter, and clatter of lunch trays echoing throughout" if is_enc else "Bustling social activity and pleasant midday breeze"
    elif time_block == "afternoon":
        lighting = "Warm afternoon light turning golden along polished floors" if is_enc else "Warm golden rays and lengthening afternoon shadows"
        acoustics = "Subtle hum of academic or club activities, turning pages, and focused dialogue" if is_enc else "Distant shouts from practice fields and rustling leaves"
    elif time_block == "evening":
        lighting = "Amber dusk glow outside fading into soft fluorescent corridor lighting" if is_enc else "Crimson-violet sunset twilight sky with streetlamps flickering on"
        acoustics = "Footsteps of late departures echoing in increasingly quiet spaces" if is_enc else "Cooling evening breeze and ambient dusk quiet"
    else:  # night
        lighting = "Darkened interior illuminated only by pale moonlight through glass or dim security fixtures" if is_enc else "Dark night sky under stars, quiet moonlight casting long deep shadows"
        acoustics = "Hushed, secretive acoustics where every whisper and footstep reverberates" if is_enc else "Nocturnal stillness, chilly night wind, and distant city hum"

    lines = [
        f"- Physical Environment & Atmosphere: {'Enclosed Interior' if is_enc else 'Open-Air Exterior'} | {lighting} | {acoustics}."
    ]

    # Curfew & After-Hours Trespassing tension check
    c_start = curr_node.get("curfew_start_min")
    c_end = curr_node.get("curfew_end_min")
    if is_hs and is_abandoned_school_node(curr_node):
        lines.append(
            "- [ABANDONED SCHOOL BUILDING — UNRESTRICTED 24/7]: "
            "Nobody bothers to lock the doors or patrol this derelict wing. It remains accessible at all hours."
        )
    elif is_hs and (is_curfew_active(c_start, c_end, current_minute) or safe_min >= 1200 or safe_min < 420) and is_academic:
        lines.append(
            "- [CAMPUS CURFEW & AFTER-HOURS TRESPASSING (20:00–07:00) — AFTER-HOURS TENSION]: "
            "All students and teachers have returned home, main corridor lights are dark, exterior doors are locked from the outside (exit remains unobstructed), "
            "and security footsteps echo down distant halls. Staying on campus during these hours is considered trespassing; maintain a hushed, illicit after-hours atmosphere."
        )

    # Room memory / scene residue check
    access_info = get_node_effective_access_info(session_id, curr_node["node_id"], current_day=current_day, current_minute=current_minute, scen_key=scen_key)
    res_log = access_info.get("scene_residue_log") or []
    if res_log:
        lines.append("- PERSISTENT ROOM MEMORY (Past Moments Recorded in this Space):")
        for m in res_log:
            lines.append(f"  * {m['text']}")
        lines.append("  (Subtly weave this history or emotional residue into your narration when relevant.)")
    elif access_info.get("scene_residue"):
        lines.append(f"- PERSISTENT ROOM MEMORY: \"{access_info['scene_residue']}\" (Subtly acknowledge this history/atmosphere when relevant).")

    if access_info.get("is_unlocked") and access_info.get("access_tier") in ("restricted", "private"):
        lines.append("- ACCESS PERMISSION: Door unlocked (access granted for this session/day).")

    return "\n".join(lines)


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

    session = db.get_session(session_id) if session_id else None
    curr_node_id = session.get("current_node_id") if session else None
    curr_node = db.get_world_node(session_id, curr_node_id) if (session_id and curr_node_id) else None
    curr_day, curr_min, _ = db.get_session_time(session_id) if session_id else (1, 480, "morning")

    graph_section = ""
    if session_id and curr_node:
        outgoing = db.get_outgoing_edges(session_id, curr_node_id)
        edge_lines = []
        for e in outgoing:
            to_id = e.get("to_node_id")
            to_name = e.get("to_node_name") or to_id
            t_min = e.get("travel_minutes", 1)
            is_locked = e.get("is_locked", 0)
            lock_desc = " [LOCKED]" if is_locked else ""
            edge_lines.append(f"  * Node [{to_id}] '{to_name}' ({t_min}m travel{lock_desc})")

        edges_text = "\n".join(edge_lines) if edge_lines else "  * (No outgoing paths; enclosed dead-end)"
        sample_node_id = outgoing[0]['to_node_id'] if outgoing else 'node_id'
        is_thub = db.is_node_or_parent_transit_hub(session_id, curr_node_id)
        thub_note = " [Transit Hub Fast-Travel Enabled]" if is_thub else ""

        sensory_memory_text = build_node_sensory_and_memory_block(session_id, curr_node, curr_day, curr_min, scen_key=scenario_key)

        graph_section = (
            f"SPATIAL GRAPH TOPOGRAPHY & DIRECTLY CONNECTED EDGES:\n"
            f"- Current Spatial Node: [{curr_node['node_id']}] '{curr_node['name']}' (Type: {curr_node['node_type']}, Privacy: {curr_node.get('privacy_level', 'semi_private')}, Access: {curr_node.get('access_tier', 'open')}){thub_note}\n"
            f"{sensory_memory_text}\n"
            f"- Directly Traversable Adjacent Pathways (Edges):\n{edges_text}\n\n"
            f"- SPATIAL MOVEMENT & DIALOGUE GATING RULE:\n"
            f"  1. If the player's choice is a TRAVEL / MOVEMENT action: select one of the adjacent nodes above and output its node ID in `destination_node_id` (e.g. '{sample_node_id}').\n"
            f"  2. If the player is NOT traveling (dialogue, social chat, skill check, observation, romantic/intimate encounter, sitting down): leave `destination_node_id` as null/empty, keep `location` identical, and update `focal_point` for micro-positioning (e.g. 'Leaning against the glass panes', 'At the teacher\\'s desk'). The macro location will strictly NOT change.\n\n"
        )

    return (
        f"CURRENT SCENE LOCATION (Tiered 3-Level Spatial System):\n"
        f"- Current Position: {formatted_current}{env_text}\n"
        f"- Current Breakdown: [Tier 1: Zone/Biome] = '{zone}' | [Tier 2: Physical Place ({arch_label})] = '{primary}' | [Tier 3: Sub-Location/Spot] = '{sub}'\n\n"
        f"{graph_section}"
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

    if session_id:
        try:
            from mechanics.world.schedules import get_npc_scheduled_node_id
            from mechanics.world.locations.access_gate import get_node_effective_access_info

            curr_day, curr_min, _ = db.get_session_time(session_id)
            contacts = db.get_contacts(session_id) or []
            roster = db.get_school_roster(session_id) if hasattr(db, "get_school_roster") else []
            all_nodes = db.get_session_world_nodes(session_id) or []

            occ_by_node: dict[str, dict] = {}
            def _get_occ(nid: str):
                if nid not in occ_by_node:
                    occ_by_node[nid] = {"known_npcs": [], "unmet_count": 0}
                return occ_by_node[nid]

            appts = []
            if hasattr(db, "get_phone_appointments"):
                appts = (db.get_phone_appointments(session_id, status="pending") or []) + (db.get_phone_appointments(session_id, status="arrived") or [])
            for appt in appts:
                tgt = appt.get("target_node_id")
                if not tgt and appt.get("rendezvous_location"):
                    tgt = db.resolve_node_id_from_location(session_id, appt["rendezvous_location"], prefer_facility=True)
                if tgt:
                    tgt_n = next((n for n in all_nodes if n["node_id"] == tgt), None)
                    fac_id = tgt_n.get("parent_id") if (tgt_n and tgt_n.get("node_type") == "ROOM") else tgt
                    if fac_id:
                        occ = _get_occ(fac_id)
                        an = appt.get("npc_name", "")
                        if an and not any(kn["name"].lower() == an.lower() for kn in occ["known_npcs"]):
                            occ["known_npcs"].append({"name": an, "status": "Rendezvous"})

            c_names_lower = set()
            for c in contacts:
                cn = (c.get("name") or "").strip()
                if not cn: continue
                c_names_lower.add(cn.lower())
                snid = get_npc_scheduled_node_id(c, current_minute=curr_min, scen_key=scen_key, current_day=curr_day)
                if snid:
                    sn = next((n for n in all_nodes if n["node_id"] == snid), None)
                    fac_id = sn.get("parent_id") if (sn and sn.get("node_type") == "ROOM") else snid
                    if fac_id:
                        occ = _get_occ(fac_id)
                        if not any(kn["name"].lower() == cn.lower() for kn in occ["known_npcs"]):
                            occ["known_npcs"].append({"name": cn, "status": "Routine"})

            for r in roster:
                rn = (r.get("name") or "").strip()
                if not rn or rn.lower() in c_names_lower: continue
                snid = get_npc_scheduled_node_id(r, current_minute=curr_min, scen_key=scen_key, current_day=curr_day)
                if snid:
                    sn = next((n for n in all_nodes if n["node_id"] == snid), None)
                    fac_id = sn.get("parent_id") if (sn and sn.get("node_type") == "ROOM") else snid
                    if fac_id:
                        _get_occ(fac_id)["unmet_count"] += 1

            for z_item in summary_list:
                z_nm = z_item["zone_name"]
                for p_item in z_item.get("primary_locations", []):
                    p_nm = p_item["name"]
                    val_str = f"{z_nm} ➔ {p_nm}"
                    pnid = db.resolve_node_id_from_location(session_id, val_str, prefer_facility=True)
                    if pnid:
                        acc = get_node_effective_access_info(session_id, pnid, current_day=curr_day, current_minute=curr_min, scen_key=scen_key)
                        p_occ = occ_by_node.get(pnid, {"known_npcs": [], "unmet_count": 0})
                        p_item["node_id"] = pnid
                        p_item["access_tier"] = acc.get("access_tier", "open")
                        p_item["access_badge"] = acc.get("status_badge", "Open")
                        p_item["is_curfew_active"] = acc.get("curfew_active", False)
                        p_item["schedule_locked"] = acc.get("schedule_locked", False)
                        p_item["is_trespassing"] = acc.get("is_trespassing", False)
                        p_item["is_unlocked"] = acc.get("is_unlocked", False)
                        p_item["scene_residue"] = acc.get("scene_residue")
                        p_item["known_npcs_here"] = p_occ["known_npcs"][:3]
                        p_item["unmet_activity_count"] = p_occ["unmet_count"]
        except Exception:
            pass

    return summary_list


from .seeding import ensure_session_locations_seeded
from .hierarchy import format_tiered_location_string, infer_zone_theme_fallback, parse_tiered_location, parse_zone_environment_data
from .attributes import (
    get_location_archetype, get_location_emoji, get_notice_board_label,
    get_zone_emoji, is_hub_location, is_location_engine_enabled,
    location_has_bounty_board, location_has_faction_hq, location_has_merchant_shop
)
