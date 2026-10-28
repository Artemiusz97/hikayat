from __future__ import annotations
"""
mechanics/world/locations/graph_seeder.py
Spatial Graph Seeder & Migration Pipeline:
Populates `world_nodes` and `world_edges` from scenario seeds and procedural session data,
and migrates existing sessions to the Relational Spatial Graph model.
"""
import json
import logging
import re
import time
from typing import Dict, Any, List, Optional, Tuple

import db
from .seeds import (
    get_scenario_seed_data,
    _slugify,
    get_facility_contextual_sublocations,
    is_entrance_sublocation,
    get_facility_entrance_name,
    get_contextual_interior_name,
    is_urban_anomalous_scenario,
    get_session_urban_zone_name,
    get_session_urban_facility_name,
    inject_anomalous_faction_hq_facilities,
)
from .seeding import (
    is_school_scenario,
    get_session_school_name,
    get_session_classroom_name,
    get_session_player_desk_name,
    get_session_player_house_name,
    get_session_park_name,
    get_session_cafe_name,
    get_session_arcade_name,
    get_session_commercial_district_name,
    get_session_residential_neighborhood_name,
    get_session_ripperdoc_name,
    get_session_kingdom_name,
    get_session_forest_name,
    get_session_ancient_forest_name,
    get_session_mountain_name,
    get_session_desert_name,
    get_session_swamp_name,
    get_session_plains_name,
    get_session_harbor_name,
    get_session_tundra_name,
    get_session_volcano_name,
    get_session_shadowlands_name,
    get_session_caves_name,
    get_session_chasm_name,
    get_session_dungeon_name,
    get_session_cyber_city_name,
    get_session_airship_name,
    get_session_station_name,
    get_session_seaside_name,
    get_session_recreation_park_name,
    get_session_athletics_complex_name,
    get_session_student_commons_name,
    get_session_cultural_arts_name,
    get_session_abandoned_campus_name,
    get_session_agency_hq_name,
    get_session_planet_name,
)
from .hierarchy import resolve_session_location_tokens

log = logging.getLogger("hikayat.world.graph_seeder")


def infer_node_category(z_id: str, p_id: str, name: str, parent_category: str = "") -> str:
    """Classifies a location node into an immutable semantic domain."""
    low = f"{z_id} {p_id} {name}".lower()
    if z_id in ("zone_commercial", "zone_downtown") or p_id.lower() in (
        "loc_cafe", "loc_arcade", "loc_karaoke", "loc_convenience_store",
        "loc_restaurant", "loc_clothing_store", "loc_brand_clothing_store",
        "loc_accessories_store", "loc_gift_store", "loc_night_market",
        "loc_nightclub", "loc_adult_store", "loc_love_hotel"
    ):
        return "commercial"
    is_school_zone = z_id in ("zone_school", "zone_school_main", "zone_school_campus", "zone_campus") or any(w in low for w in ("school", "academy", "classroom", "homeroom", "campus"))
    if is_school_zone and any(k in low for k in (
        "school", "academy", "classroom", "homeroom", "library", "lab", "gym", "field",
        "arts", "commons", "greenhouse", "glasshouse", "auditorium", "dojo", "campus",
        "council", "faculty", "dorm", "infirmary", "restroom", "shower"
    )):
        return "academic"
    if any(k in low for k in ("commercial", "downtown", "cafe", "arcade", "store", "shop", "boutique", "emporium", "bazaar", "nightclub", "hotel", "karaoke", "shopping", "bakery", "restaurant", "diner", "bar", "tavern")):
        return "commercial"
    if any(k in low for k in ("residential", "house", "apartment", "neighborhood", "home")) and not any(k in low for k in ("glasshouse", "greenhouse", "boathouse", "treehouse", "powerhouse", "lighthouse", "clubhouse", "courthouse", "homeroom", "coffeehouse", "teahouse", "bakehouse", "steakhouse")):
        return "residential"
    if any(k in low for k in ("theme_park", "theme park", "amusement", "carnival", "midway", "boardwalk", "pier", "civic", "park", "beach", "sakura", "picnic")) and not any(k in low for k in ("dungeon", "tundra", "swamp", "desert", "cave", "ruins", "wilds", "frontier")):
        return "civic"
    if any(k in low for k in ("seaside", "coast", "mountain", "recreational_park", "hilltop", "lookout", "forest", "woods", "lake", "swamp", "desert", "cave", "dungeon", "summit", "ruins", "tundra", "campsite")):
        return "wilderness"
    return parent_category or "civic"


def infer_node_privacy(node_type: str, p_id: str, name: str, explicit_meta: dict | None = None) -> str:
    """Infers default privacy level: 'public', 'semi_private', or 'private'."""
    meta = explicit_meta or {}
    if meta.get("is_private_intimate"):
        return "private"
    if meta.get("is_discreet"):
        return "semi_private"
    low = f"{p_id} {name}".lower()
    if any(k in low for k in ("player_house", "bedroom", "safe", "archive", "staff room", "teachers' staff", "private", "secret", "boarded", "love_hotel_mirrored", "love_hotel_jacuzzi", "nsfw_faction_hq", "velvet basement", "fitting_room")):
        return "private"
    if any(k in low for k in ("empty_class", "behind", "storage", "rooftop", "stairwell", "greenhouse", "glasshouse", "music room", "studio", "council", "alcove", "shed", "aisle", "aisles", "stacks", "corner", "balcony", "restroom", "shower_room", "infirmary", "underpass")):
        return "semi_private"
    return "public"


def infer_is_enclosed(node_type: str, node_id: str, name: str) -> int:
    """Infers whether a node is an indoor/enclosed structure (1) or outdoor/open-air (0)."""
    low = f"{node_id} {name}".lower()
    if any(k in low for k in ("cabin interior", "boathouse", "storage shed", "changing cabanas", "underpass")):
        return 1
    outdoor_keywords = (
        "courtyard", "fountain", "gate", "park", "field", "track", "rooftop", "street",
        "grounds", "garden", "terrace", "patio", "plaza", "city square", "night market",
        "sakura grove", "hilltop", "lookout", "campsite", "picnic", "avenue", "pier",
        "boardwalk", "trail", "path", "beach", "forest", "woods", "mountain", "lake", "dunes"
    )
    if any(k in low for k in outdoor_keywords):
        return 0
    return 1


def infer_is_transit_hub(node_type: str, z_id: str, p_id: str, name: str, is_zone_hub: bool = False) -> int:
    """Flags nodes that permit World Map Fast Travel."""
    low = f"{z_id} {p_id} {name}".lower()
    if node_type == "ZONE":
        return 1 if is_zone_hub else 0
    if node_type == "FACILITY":
        if any(k in low for k in ("gates", "gate", "courtyard", "fountain", "station", "terminal", "shuttle", "central plaza", "city square", "loc_city_square", "entrance foyer", "town square", "harbor pier", "corridor", "annex", "lobby", "atrium", "hallway")):
            return 1
    return 0


def infer_access_tier(node_type: str, z_id: str, node_id: str, name: str, category: str, explicit_tier: str = "") -> str:
    """Infers access restriction tier: 'open', 'restricted', or 'private'."""
    if explicit_tier:
        return explicit_tier
    low = f"{z_id} {node_id} {name}".lower()
    if "nsfw_faction_hq" in low or "velvet basement" in low:
        return "restricted"
    # Special Condition: Abandoned School Building zone is always accessible 24/7
    # (nobody bothers to lock the doors or check the area for anyone)
    if any(k in low for k in (
        "zone_abandoned_school", "bld_abandoned_school", "abandoned old campus", "loc_old_storage_3b",
        "loc_derelict_gym", "loc_clock_tower", "loc_old_infirmary", "loc_ruined_hallway",
        "overgrown hallway", "dark_equipment_room"
    )):
        return "open"
    if category == "commercial" or z_id in ("zone_commercial", "zone_downtown"):
        return "open"
    # Private homes/residences/bedrooms
    if any(k in low for k in ("player_house", "player_bedroom", "friend_house", "residence", "bedroom", "apartment", "guest quarters", "home")) and not any(k in low for k in ("glasshouse", "greenhouse", "boathouse", "treehouse", "powerhouse", "lighthouse", "clubhouse", "courthouse", "homeroom", "coffeehouse", "teahouse", "bakehouse", "steakhouse")):
        return "private"
    if category == "residential" and not any(k in low for k in ("park", "street", "sidewalk", "avenue")):
        return "private"
    # Restricted spaces
    if any(k in low for k in (
        "loc_staff_room", "staff room", "teachers' staff", "teacher's desk", "print room",
        "council_archives", "archive files", "chemical_closet", "chemical storage",
        "soundproof_closet", "loc_rooftop", "school rooftop", "barracks",
        "arcane archives", "fume hood", "safe"
    )):
        return "restricted"
    return "open"


def infer_curfew_window(node_type: str, z_id: str, node_id: str, name: str, category: str, explicit_start: int | None = None, explicit_end: int | None = None) -> tuple[int | None, int | None]:
    """Infers curfew minutes window (start, end) where access is locked/restricted."""
    if explicit_start is not None and explicit_end is not None:
        return explicit_start, explicit_end
    low = f"{z_id} {node_id} {name}".lower()
    # Special Condition: Abandoned School Building zone has no curfew or lock checks
    if any(k in low for k in (
        "zone_abandoned_school", "bld_abandoned_school", "abandoned old campus", "loc_old_storage_3b",
        "loc_derelict_gym", "loc_clock_tower", "loc_old_infirmary", "loc_ruined_hallway",
        "overgrown hallway", "dark_equipment_room"
    )):
        return None, None
    # Academic facilities (High School campus) have after-hours lockdown/curfew 20:00 (1200) to 07:00 (420),
    # except exterior main gates and open University campuses in urban anomalous scenarios.
    if category == "academic" and not any(k in low for k in ("school_gate", "front gate", "entrance path", "notice board", "bike racks", "zone_university", "university")):
        return 1200, 420
    return None, None


def ensure_session_spatial_graph_seeded(session_id: int, scenario_key: str = "high_school_drama", char_name: str = "") -> None:
    """
    Populates `world_nodes` and `world_edges` from scenario seeds with personalized names,
    semantic categories, and navigation edges. Idempotent.
    """
    existing_nodes = db.get_session_world_nodes(session_id)
    if existing_nodes:
        return

    scen_data = get_scenario_seed_data(scenario_key)
    zones = inject_anomalous_faction_hq_facilities(scen_data.get("zones") or [], session_id=session_id, scenario_key=scenario_key)
    if not zones:
        return

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

    transit_hubs: list[str] = []
    facility_entrance_map: dict[str, str] = {}
    zone_gateway_map: dict[str, str] = {}

    for zone in zones:
        z_id = zone.get("id") or f"zone_{_slugify(zone.get('name', 'region'))}"
        zone_name = zone.get("name", "World Region")

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
        elif z_id in ("zone_cave_network", "zone_deep_caves", "zone_deep_caves_isekai") or zone_name == "Deep Cave Network":
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
        elif z_id == "zone_seaside_bay" or zone_name == "Seaside & Coastal Bay":
            zone_name = seaside_name
        elif z_id in ("zone_mountain_park", "zone_recreational_park") or zone_name in ("Recreational Mountain Park", "Recreational Park"):
            zone_name = rec_park_name
        elif z_id == "zone_commercial" or zone_name == "Commercial District" or ((z_id == "zone_downtown" or zone_name == "Downtown") and is_school_scenario(scenario_key)):
            zone_name = commercial_name
        elif z_id == "zone_residential" or zone_name == "Residential Neighborhood":
            zone_name = residential_name

        if is_urban_anomalous_scenario(scenario_key):
            zone_name = get_session_urban_zone_name(session_id, z_id, zone_name, scenario_key)
        zone_name = resolve_session_location_tokens(session_id, zone_name, scenario_key, char_name)

        atmosphere = ""
        if "theme" in zone or "features" in zone:
            atmosphere = json.dumps({
                "theme": resolve_session_location_tokens(session_id, zone.get("theme", ""), scenario_key, char_name),
                "features": resolve_session_location_tokens(session_id, zone.get("features", ""), scenario_key, char_name),
                "sensory": resolve_session_location_tokens(session_id, zone.get("sensory", zone.get("atmosphere", "")), scenario_key, char_name)
            })

        is_zone_hub = bool(zone.get("is_hub"))
        z_category = infer_node_category(z_id, "", zone_name)
        z_access = infer_access_tier("ZONE", z_id, z_id, zone_name, z_category, zone.get("access_tier", ""))
        z_curfew_start, z_curfew_end = infer_curfew_window("ZONE", z_id, z_id, zone_name, z_category, zone.get("curfew_start_min"), zone.get("curfew_end_min"))

        # 1. Insert Zone Node
        db.save_world_node(
            session_id=session_id,
            node_id=z_id,
            parent_id=None,
            name=zone_name,
            node_type="ZONE",
            category=z_category,
            privacy_level="public",
            is_enclosed=0,
            is_transit_hub=infer_is_transit_hub("ZONE", z_id, "", zone_name, is_zone_hub),
            access_tier=z_access,
            curfew_start_min=z_curfew_start,
            curfew_end_min=z_curfew_end,
            atmosphere=atmosphere,
            is_dynamic=0
        )

        zone_facility_nodes: list[str] = []

        for primary in zone.get("primary_locations") or []:
            p_id = primary.get("id") or f"fac_{_slugify(primary.get('name', 'facility'))}"
            primary_name = primary.get("name", "Main Area")

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
                continue

            if is_urban_anomalous_scenario(scenario_key):
                primary_name = get_session_urban_facility_name(session_id, z_id, p_id, primary_name, scenario_key, char_name)
            primary_name = resolve_session_location_tokens(session_id, primary_name, scenario_key, char_name)

            p_seed_meta = {
                k: primary[k]
                for k in ("is_discreet", "is_private_intimate", "gender_restriction", "grade_exclusive", "suite_fee", "nsfw_only")
                if k in primary
            }
            p_category = infer_node_category(z_id, p_id, primary_name, parent_category=z_category)
            p_privacy = infer_node_privacy("FACILITY", p_id, primary_name, explicit_meta=p_seed_meta)
            p_enclosed = infer_is_enclosed("FACILITY", p_id, primary_name)
            p_transit = infer_is_transit_hub("FACILITY", z_id, p_id, primary_name)
            p_access = infer_access_tier("FACILITY", z_id, p_id, primary_name, p_category, primary.get("access_tier", ""))
            p_curfew_start, p_curfew_end = infer_curfew_window("FACILITY", z_id, p_id, primary_name, p_category, primary.get("curfew_start_min"), primary.get("curfew_end_min"))
            if p_transit:
                transit_hubs.append(p_id)

            # 2. Insert Facility Node
            db.save_world_node(
                session_id=session_id,
                node_id=p_id,
                parent_id=z_id,
                name=primary_name,
                node_type="FACILITY",
                category=p_category,
                privacy_level=p_privacy,
                is_enclosed=p_enclosed,
                is_transit_hub=p_transit,
                access_tier=p_access,
                curfew_start_min=p_curfew_start,
                curfew_end_min=p_curfew_end,
                atmosphere=atmosphere,
                is_dynamic=0,
                state_json=p_seed_meta if p_seed_meta else None
            )
            zone_facility_nodes.append(p_id)

            # 3. Insert Room Nodes
            raw_subs = primary.get("sub_locations") or []
            subs = get_facility_contextual_sublocations(primary_name, raw_subs)

            room_nodes: list[str] = []
            entrance_node_id = None
            room_access_map: dict[str, str] = {}
            room_locked_map: dict[str, bool] = {}

            for sub in subs:
                s_id = sub.get("id") or f"sub_{_slugify(primary_name)}_{_slugify(sub.get('name', 'room'))}"
                sub_name = sub.get("name", "Main Area")

                if classroom_name and (sub_name == "Homeroom Classroom" or s_id == "loc_homeroom"):
                    sub_name = classroom_name
                elif (sub_name == "Player's Desk" or s_id == "sub_player_desk") and (p_id == "loc_homeroom" or "homeroom" in primary_name.lower()):
                    sub_name = player_desk
                elif is_urban_anomalous_scenario(scenario_key) and s_id.startswith(("loc_hq_", "sub_priv1_", "sub_priv2_")):
                    sub_name = get_session_urban_facility_name(session_id, "zone_agency_hq", s_id, sub_name, scenario_key, char_name)
                sub_name = resolve_session_location_tokens(session_id, sub_name, scenario_key, char_name)

                if (sub.get("is_entrance") or is_entrance_sublocation(sub_name)) and not entrance_node_id:
                    entrance_node_id = s_id

                s_seed_meta = {
                    k: sub[k]
                    for k in ("is_discreet", "is_private_intimate", "gender_restriction", "grade_exclusive", "suite_fee", "nsfw_only")
                    if k in sub
                }
                s_privacy = infer_node_privacy("ROOM", s_id, sub_name, explicit_meta=s_seed_meta) or p_privacy
                s_access = infer_access_tier("ROOM", z_id, s_id, sub_name, p_category, sub.get("access_tier", ""))
                if s_access == "open" and p_access in ("restricted", "private"):
                    s_access = p_access
                s_curfew_start, s_curfew_end = infer_curfew_window("ROOM", z_id, s_id, sub_name, p_category, sub.get("curfew_start_min"), sub.get("curfew_end_min"))
                if s_curfew_start is None and p_curfew_start is not None and not p_id.startswith("bld_school_") and p_id not in ("loc_agency_hq", "loc_private_hq_1", "loc_private_hq_2"):
                    s_curfew_start, s_curfew_end = p_curfew_start, p_curfew_end

                mega_complex_ids = {
                    "loc_agency_hq", "loc_private_hq_1", "loc_private_hq_2",
                    "loc_general_hospital", "loc_theme_park", "loc_eastern_temple", "loc_botanical_zoo",
                }
                if p_id.startswith("bld_school_") or p_id in mega_complex_ids:
                    s_enclosed = infer_is_enclosed("ROOM", s_id, sub_name)
                else:
                    r_enc = infer_is_enclosed("ROOM", s_id, sub_name)
                    if r_enc == 0:
                        s_enclosed = 0
                    elif any(k in f"{s_id} {sub_name}".lower() for k in ("cabin interior", "boathouse", "storage shed", "changing cabanas", "underpass")):
                        s_enclosed = 1
                    else:
                        s_enclosed = p_enclosed

                room_access_map[s_id] = s_access
                room_locked_map[s_id] = bool(sub.get("is_locked", False))

                db.save_world_node(
                    session_id=session_id,
                    node_id=s_id,
                    parent_id=p_id,
                    name=sub_name,
                    node_type="ROOM",
                    category=p_category,
                    privacy_level=s_privacy,
                    is_enclosed=s_enclosed,
                    is_transit_hub=0,
                    access_tier=s_access,
                    curfew_start_min=s_curfew_start,
                    curfew_end_min=s_curfew_end,
                    atmosphere=atmosphere,
                    is_dynamic=0,
                    state_json=s_seed_meta if s_seed_meta else None
                )
                room_nodes.append(s_id)

            if not entrance_node_id and room_nodes:
                entrance_node_id = room_nodes[0]
            if entrance_node_id:
                facility_entrance_map[p_id] = entrance_node_id

            # Connect Facility to Entrance Room (all external traffic funnels into the entrance threshold)
            if entrance_node_id:
                db.save_world_edge(session_id, p_id, entrance_node_id, travel_minutes=1, edge_type="door")

            is_mega_complex = p_id in {
                "loc_agency_hq", "loc_private_hq_1", "loc_private_hq_2",
                "loc_general_hospital", "loc_theme_park", "loc_eastern_temple", "loc_botanical_zoo",
            }
            ent_to_room_mins = 3 if is_mega_complex else 1
            room_to_room_mins = 3 if is_mega_complex else 2
            room_edge_type = "hallway" if is_mega_complex else "door"

            # Connect Entrance Room to each interior room
            for r_id in room_nodes:
                if r_id != entrance_node_id:
                    is_edge_locked = 1 if room_locked_map.get(r_id) else 0
                    check_type = "AGI" if is_edge_locked else ""
                    check_dc = 12 if is_edge_locked else 0
                    db.save_world_edge(session_id, entrance_node_id, r_id, travel_minutes=ent_to_room_mins, edge_type=room_edge_type, is_locked=is_edge_locked, skill_check_type=check_type, skill_check_dc=check_dc)

            # Connect interior rooms to each other
            interior_rooms = [r for r in room_nodes if r != entrance_node_id]
            for i in range(len(interior_rooms)):
                for j in range(i + 1, len(interior_rooms)):
                    db.save_world_edge(session_id, interior_rooms[i], interior_rooms[j], travel_minutes=room_to_room_mins, edge_type=room_edge_type)

        # Connect Facilities within the same zone to adjacent facilities
        is_vessel_zone = z_id in ("zone_airship_cruiser", "zone_starship_vanguard")
        if z_id == "zone_agency_hq":
            intra_fac_mins, intra_ent_mins, e_type = 3, 3, "hallway"
        elif is_vessel_zone:
            intra_fac_mins, intra_ent_mins, e_type = 3, 2, "hallway"
        else:
            intra_fac_mins, intra_ent_mins, e_type = 5, 4, "pathway"

        has_agency_hq_in_cc = (
            z_id == "zone_city_center"
            and len(zone_facility_nodes) >= 2
            and zone_facility_nodes[0] == "loc_agency_hq"
        )
        hub_fac_idx = 1 if has_agency_hq_in_cc else 0

        if has_agency_hq_in_cc:
            # Connect Agency HQ (index 0) to City Center Metro Transit Terminal (index 1) with 10-min transit link
            db.save_world_edge(session_id, zone_facility_nodes[0], zone_facility_nodes[1], travel_minutes=10, edge_type="transit")
            ent_hq = facility_entrance_map.get(zone_facility_nodes[0])
            ent_cc = facility_entrance_map.get(zone_facility_nodes[1])
            if ent_hq and ent_cc:
                db.save_world_edge(session_id, ent_hq, ent_cc, travel_minutes=10, edge_type="transit")

        for i in range(hub_fac_idx, len(zone_facility_nodes)):
            for j in range(i + 1, len(zone_facility_nodes)):
                # If zone has a hub facility (e.g. gates, lobby, or courtyard), connect all facilities to that hub
                # or connect sequential facilities
                if j == i + 1 or zone_facility_nodes[hub_fac_idx] in (zone_facility_nodes[i], zone_facility_nodes[j]):
                    db.save_world_edge(session_id, zone_facility_nodes[i], zone_facility_nodes[j], travel_minutes=intra_fac_mins, edge_type=e_type)
                    # Connect entrances directly between adjacent facilities so characters walk entrance-to-entrance
                    ent_i = facility_entrance_map.get(zone_facility_nodes[i])
                    ent_j = facility_entrance_map.get(zone_facility_nodes[j])
                    if ent_i and ent_j:
                        db.save_world_edge(session_id, ent_i, ent_j, travel_minutes=intra_ent_mins, edge_type=e_type)

        # Ensure at least one facility per zone acts as an inter-zone transit connection point
        if zone_facility_nodes:
            gw_node = zone_facility_nodes[hub_fac_idx]
            zone_gateway_map[z_id] = gw_node
            if not any(f in transit_hubs for f in zone_facility_nodes):
                transit_hubs.append(gw_node)

    # Connect Transit Hubs across zones using Genre-Weighted Transit Graphs
    scen_low = str(scenario_key or "").lower()
    is_urban_anomalous_graph = any(k in scen_low for k in ("anomalous", "incursion", "urban_anomalies", "urban_fantasy"))
    connected_zones: set[str] = set()

    if "zone_agency_hq" in zone_gateway_map or (is_urban_anomalous_graph and "zone_city_center" in zone_gateway_map):
        urban_district_edges = [
            # Core Hub & Inner Ring (8-16 mins)
            ("zone_agency_hq", "zone_city_center", 10),
            ("zone_agency_hq", "zone_downtown", 12),
            ("zone_agency_hq", "zone_uptown", 12),
            ("zone_city_center", "zone_downtown", 10),
            ("zone_city_center", "zone_uptown", 10),
            ("zone_city_center", "zone_low_cost_wards", 12),
            ("zone_city_center", "zone_suburbs", 15),
            ("zone_city_center", "zone_chinatown", 10),
            ("zone_city_center", "zone_seaside_beach", 16),
            # Mid-Ring Connections (10-18 mins)
            ("zone_downtown", "zone_chinatown", 8),
            ("zone_downtown", "zone_low_cost_wards", 10),
            ("zone_downtown", "zone_city_docks", 15),
            ("zone_downtown", "zone_industrial", 15),
            ("zone_downtown", "zone_seaside_beach", 14),
            ("zone_chinatown", "zone_low_cost_wards", 10),
            ("zone_low_cost_wards", "zone_industrial", 10),
            ("zone_low_cost_wards", "zone_city_docks", 15),
            ("zone_low_cost_wards", "zone_undercity", 10),
            ("zone_industrial", "zone_city_docks", 12),
            ("zone_industrial", "zone_undercity", 12),
            ("zone_industrial", "zone_airport", 15),
            ("zone_uptown", "zone_ultra_rich", 12),
            ("zone_uptown", "zone_suburbs", 12),
            ("zone_uptown", "zone_school_campus", 12),
            ("zone_uptown", "zone_university", 10),
            ("zone_university", "zone_school_campus", 10),
            ("zone_suburbs", "zone_school_campus", 10),
            # Outskirts & Nature Reserves (18-25 mins from mid-ring)
            ("zone_suburbs", "zone_seaside_beach", 18),
            ("zone_city_docks", "zone_seaside_beach", 18),
            ("zone_city_docks", "zone_airport", 15),
            ("zone_suburbs", "zone_woods_reserve", 22),
            ("zone_uptown", "zone_woods_reserve", 25),
        ]
        for z_a, z_b, mins in urban_district_edges:
            gw_a = zone_gateway_map.get(z_a) or ("loc_agency_hq" if z_a == "zone_agency_hq" else None)
            gw_b = zone_gateway_map.get(z_b) or ("loc_agency_hq" if z_b == "zone_agency_hq" else None)
            if gw_a and gw_b and gw_a != gw_b:
                db.save_world_edge(session_id, gw_a, gw_b, travel_minutes=mins, edge_type="transit")
                connected_zones.add(z_a)
                connected_zones.add(z_b)

        # Direct Mountain Shrine Funicular link from Uptown to Eastern Grand Temple inside Woods Reserve
        gw_uptown = zone_gateway_map.get("zone_uptown")
        if gw_uptown and "loc_eastern_temple" in facility_entrance_map:
            db.save_world_edge(session_id, gw_uptown, "loc_eastern_temple", travel_minutes=16, edge_type="transit")
    else:
        genre_zone_edges_table: list[tuple[str, str, int, str]] = [
            # High School Drama (15-30m local & suburban rail/bus)
            ("zone_school_main", "zone_residential", 15, "transit"),
            ("zone_school_main", "zone_downtown", 15, "transit"),
            ("zone_residential", "zone_downtown", 15, "transit"),
            ("zone_downtown", "zone_seaside_bay", 25, "transit"),
            ("zone_residential", "zone_seaside_bay", 25, "transit"),
            ("zone_residential", "zone_recreational_park", 30, "transit"),
            ("zone_downtown", "zone_recreational_park", 30, "transit"),
            # Legacy High School Zone IDs (for older migrated sessions)
            ("zone_school_main", "zone_commercial", 15, "transit"),
            ("zone_residential", "zone_commercial", 15, "transit"),
            ("zone_commercial", "zone_seaside_bay", 25, "transit"),
            ("zone_residential", "zone_mountain_park", 30, "transit"),
            ("zone_commercial", "zone_mountain_park", 30, "transit"),
            # Slice of Life (15-25m urban tram/walk)
            ("zone_sol_residential", "zone_sol_shopping_arcade", 15, "transit"),
            ("zone_sol_shopping_arcade", "zone_sol_nightlife", 15, "transit"),
            ("zone_sol_shopping_arcade", "zone_sol_harbor_pier", 20, "transit"),
            ("zone_sol_nightlife", "zone_sol_harbor_pier", 15, "transit"),
            ("zone_sol_residential", "zone_sol_harbor_pier", 25, "transit"),
            # Cyberpunk (15-30m mag-lev & badlands highway)
            ("zone_city_center", "zone_downtown", 15, "transit"),
            ("zone_city_center", "zone_uptown_heights", 15, "transit"),
            ("zone_downtown", "zone_slums_lower_wards", 15, "transit"),
            ("zone_downtown", "zone_industrial_docks", 20, "transit"),
            ("zone_slums_lower_wards", "zone_industrial_docks", 15, "transit"),
            ("zone_uptown_heights", "zone_nature_reserve", 25, "transit"),
            ("zone_city_center", "zone_nature_reserve", 25, "transit"),
            ("zone_slums_lower_wards", "zone_city_outskirts", 25, "transit"),
            ("zone_industrial_docks", "zone_city_outskirts", 25, "transit"),
            ("zone_city_outskirts", "zone_rural_outpost", 30, "transit"),
            # Steampunk (10m docking mast, 15-20m steam tram, 30-40m moorland rail/cruiser)
            ("zone_airship_cruiser", "zone_clocktower_center", 10, "transit"),
            ("zone_airship_cruiser", "zone_upper_promenade", 12, "transit"),
            ("zone_airship_cruiser", "zone_rust_outskirts", 30, "transit"),
            ("zone_airship_cruiser", "zone_smog_moors", 35, "transit"),
            ("zone_clocktower_center", "zone_upper_promenade", 15, "transit"),
            ("zone_clocktower_center", "zone_boiler_foundries", 15, "transit"),
            ("zone_clocktower_center", "zone_subterranean_canals", 20, "transit"),
            ("zone_boiler_foundries", "zone_subterranean_canals", 15, "transit"),
            ("zone_boiler_foundries", "zone_rust_outskirts", 30, "transit"),
            ("zone_rust_outskirts", "zone_smog_moors", 40, "pathway"),
            # Sci-Fi (10m docking airlock, 25m orbital shuttle, 35-60m hyperspace jump)
            ("zone_starship_vanguard", "zone_orbital_station", 10, "transit"),
            ("zone_orbital_station", "zone_homeworld_capital", 25, "transit"),
            ("zone_starship_vanguard", "zone_homeworld_capital", 25, "transit"),
            ("zone_starship_vanguard", "zone_desert_planet", 35, "transit"),
            ("zone_starship_vanguard", "zone_jungle_planet", 40, "transit"),
            ("zone_starship_vanguard", "zone_ocean_planet", 40, "transit"),
            ("zone_starship_vanguard", "zone_asteroid_belt", 45, "transit"),
            ("zone_starship_vanguard", "zone_ice_planet", 50, "transit"),
            ("zone_starship_vanguard", "zone_volcanic_planet", 55, "transit"),
            ("zone_orbital_station", "zone_desert_planet", 40, "transit"),
            ("zone_orbital_station", "zone_jungle_planet", 45, "transit"),
            ("zone_orbital_station", "zone_ocean_planet", 45, "transit"),
            ("zone_orbital_station", "zone_asteroid_belt", 50, "transit"),
            ("zone_orbital_station", "zone_ice_planet", 55, "transit"),
            ("zone_orbital_station", "zone_volcanic_planet", 60, "transit"),
            # High Fantasy (60-150m overland roads & wilderness marches)
            ("zone_capital_city", "zone_central_plains", 60, "pathway"),
            ("zone_capital_city", "zone_coastal_harbor", 75, "pathway"),
            ("zone_capital_city", "zone_woodlands_forest", 75, "pathway"),
            ("zone_central_plains", "zone_woodlands_forest", 60, "pathway"),
            ("zone_central_plains", "zone_coastal_harbor", 75, "pathway"),
            ("zone_central_plains", "zone_mountain_range", 90, "pathway"),
            ("zone_woodlands_forest", "zone_ancient_woods", 90, "pathway"),
            ("zone_woodlands_forest", "zone_swamp_marshes", 90, "pathway"),
            ("zone_coastal_harbor", "zone_desert_dunes", 120, "pathway"),
            ("zone_mountain_range", "zone_cave_network", 75, "pathway"),
            ("zone_mountain_range", "zone_frozen_tundra", 120, "pathway"),
            ("zone_mountain_range", "zone_volcanic_ashlands", 120, "pathway"),
            ("zone_ancient_woods", "zone_ancient_dungeon", 90, "pathway"),
            ("zone_swamp_marshes", "zone_cursed_shadowlands", 120, "pathway"),
            ("zone_desert_dunes", "zone_volcanic_ashlands", 120, "pathway"),
            ("zone_cave_network", "zone_underworld_chasm", 120, "pathway"),
            ("zone_cursed_shadowlands", "zone_ancient_dungeon", 90, "pathway"),
            ("zone_cursed_shadowlands", "zone_underworld_chasm", 150, "pathway"),
            # Isekai Fantasy (60-120m guild roads & frontier marches)
            ("zone_capital_city_isekai", "zone_central_plains_isekai", 60, "pathway"),
            ("zone_capital_city_isekai", "zone_woodlands_forest_isekai", 75, "pathway"),
            ("zone_central_plains_isekai", "zone_woodlands_forest_isekai", 60, "pathway"),
            ("zone_central_plains_isekai", "zone_mountain_range_isekai", 90, "pathway"),
            ("zone_central_plains_isekai", "zone_desert_dunes_isekai", 120, "pathway"),
            ("zone_woodlands_forest_isekai", "zone_ancient_woods_isekai", 90, "pathway"),
            ("zone_ancient_woods_isekai", "zone_ancient_dungeon_isekai", 90, "pathway"),
            ("zone_mountain_range_isekai", "zone_cursed_shadowlands_isekai", 120, "pathway"),
            ("zone_cursed_shadowlands_isekai", "zone_ancient_dungeon_isekai", 90, "pathway"),
            # Dark Fantasy (60-120m cursed roads & blighted marches)
            ("zone_gallows_settlement", "zone_withered_woods", 60, "pathway"),
            ("zone_gallows_settlement", "zone_blighted_marshes", 75, "pathway"),
            ("zone_gallows_settlement", "zone_sunken_catacombs", 60, "pathway"),
            ("zone_gallows_settlement", "zone_black_citadel", 90, "pathway"),
            ("zone_withered_woods", "zone_blood_ash_crags", 120, "pathway"),
            ("zone_blighted_marshes", "zone_sunken_catacombs", 90, "pathway"),
            ("zone_black_citadel", "zone_blood_ash_crags", 120, "pathway"),
            ("zone_black_citadel", "zone_sunken_catacombs", 90, "pathway"),
            # Nuclear Post-Apocalypse (60-120m wasteland treks)
            ("zone_underground_vault", "zone_scavenger_market", 60, "pathway"),
            ("zone_underground_vault", "zone_highway_badlands", 75, "pathway"),
            ("zone_scavenger_market", "zone_highway_badlands", 60, "pathway"),
            ("zone_scavenger_market", "zone_megacity_ruins", 90, "pathway"),
            ("zone_scavenger_market", "zone_toxic_swamp", 90, "pathway"),
            ("zone_highway_badlands", "zone_raider_fortress", 90, "pathway"),
            ("zone_highway_badlands", "zone_megacity_ruins", 90, "pathway"),
            ("zone_megacity_ruins", "zone_irradiated_crater", 120, "pathway"),
            ("zone_toxic_swamp", "zone_irradiated_crater", 120, "pathway"),
        ]
        for z_a, z_b, mins, edge_kind in genre_zone_edges_table:
            gw_a = zone_gateway_map.get(z_a)
            gw_b = zone_gateway_map.get(z_b)
            if gw_a and gw_b and gw_a != gw_b:
                db.save_world_edge(session_id, gw_a, gw_b, travel_minutes=mins, edge_type=edge_kind)
                connected_zones.add(z_a)
                connected_zones.add(z_b)

    # Fallback connectivity guarantee for any custom/dynamic zone not in static tables
    is_modern_or_tech = any(
        k in scen_low
        for k in ("school", "slice_of_life", "cyberpunk", "steampunk", "sci_fi", "space", "anomalous", "urban")
    )
    fallback_mins = 25 if is_modern_or_tech else 90
    fallback_edge_type = "transit" if is_modern_or_tech else "pathway"
    all_zone_ids = list(zone_gateway_map.keys())
    if len(all_zone_ids) >= 2:
        anchor_z = next((z for z in all_zone_ids if z in connected_zones), all_zone_ids[0])
        anchor_gw = zone_gateway_map[anchor_z]
        for z_other in all_zone_ids:
            if z_other != anchor_z and z_other not in connected_zones:
                other_gw = zone_gateway_map[z_other]
                if other_gw and other_gw != anchor_gw:
                    db.save_world_edge(session_id, anchor_gw, other_gw, travel_minutes=fallback_mins, edge_type=fallback_edge_type)


def migrate_session_to_spatial_graph(session_id: int) -> dict[str, Any]:
    """
    Migrates a single session's legacy string location, active quest waypoints,
    and phone appointments into the spatial graph model.
    """
    with db.get_conn() as conn:
        s_row = conn.execute("SELECT id, scenario, current_location, current_node_id FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not s_row:
            return {"status": "not_found", "session_id": session_id}

    scenario_key = s_row["scenario"] or "high_school_drama"
    ensure_session_spatial_graph_seeded(session_id, scenario_key=scenario_key)

    nodes = db.get_session_world_nodes(session_id)
    if not nodes:
        return {"status": "no_nodes", "session_id": session_id}

    curr_loc_str = str(s_row["current_location"] or "").strip()
    target_node = None

    # Parse tiers from curr_loc_str
    parts = [p.strip() for p in re.split(r"\s*(?:➔|->|>)\s*", curr_loc_str) if p.strip()]
    leaf_name = parts[-1].lower() if parts else ""
    primary_name = parts[1].lower() if len(parts) >= 2 else (parts[0].lower() if parts else "")
    zone_name = parts[0].lower() if parts else ""

    # 1. Exact match on leaf name among ROOM nodes (skip generic "main area")
    room_nodes = [n for n in nodes if n["node_type"] == "ROOM"]
    if leaf_name and leaf_name not in ("main area", "area", "main"):
        for rn in room_nodes:
            if rn["name"].lower() == leaf_name:
                target_node = rn
                break

    # 1b. Legacy 3-part string where middle tier (primary_name) is now a ROOM node and leaf is a prop
    if not target_node and primary_name:
        for rn in room_nodes:
            if rn["name"].lower() == primary_name:
                target_node = rn
                break
        if not target_node and "homeroom" in primary_name:
            target_node = next((rn for rn in room_nodes if rn["node_id"] == "loc_homeroom"), None)

    # 2. Match on primary name among FACILITY nodes
    if not target_node and primary_name:
        fac_nodes = [n for n in nodes if n["node_type"] == "FACILITY"]
        for fn in fac_nodes:
            if fn["name"].lower() == primary_name:
                ent_room = next((rn for rn in room_nodes if rn["parent_id"] == fn["node_id"] and is_entrance_sublocation(rn["name"])), None)
                child_room = ent_room or next((rn for rn in room_nodes if rn["parent_id"] == fn["node_id"]), None)
                target_node = child_room or fn
                break

    # 3. Fallback: match any node by name containment
    if not target_node and leaf_name:
        for n in nodes:
            if leaf_name in n["name"].lower() or n["name"].lower() in leaf_name:
                target_node = n
                break

    # Default to first room node or starting node
    if not target_node:
        target_node = room_nodes[0] if room_nodes else nodes[0]

    current_node_id = target_node["node_id"]

    # Update session pointer
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET current_node_id=?, focal_point='' WHERE id=?",
            (current_node_id, session_id)
        )

        # Migrate quest waypoints target_node_id
        wps = conn.execute("SELECT id, target_location FROM quest_waypoints WHERE session_id=?", (session_id,)).fetchall()
        for wp in wps:
            wp_target = str(wp["target_location"] or "").strip()
            wp_parts = [p.strip() for p in re.split(r"\s*(?:➔|->|>)\s*", wp_target) if p.strip()]
            wp_leaf = wp_parts[-1].lower() if wp_parts else ""
            wp_prim = wp_parts[1].lower() if len(wp_parts) >= 2 else (wp_parts[0].lower() if wp_parts else "")

            matched_wp_node = None
            for n in nodes:
                n_low = n["name"].lower()
                if wp_leaf and n_low == wp_leaf:
                    matched_wp_node = n["node_id"]
                    break
                if wp_prim and n_low == wp_prim:
                    matched_wp_node = n["node_id"]
                    break
            if not matched_wp_node and wp_prim:
                for n in nodes:
                    if wp_prim in n["name"].lower() or n["name"].lower() in wp_prim:
                        matched_wp_node = n["node_id"]
                        break
            if matched_wp_node:
                conn.execute("UPDATE quest_waypoints SET target_node_id=? WHERE id=?", (matched_wp_node, wp["id"]))

        # Migrate rendezvous commitments target_node_id
        appts = conn.execute(
            "SELECT id, target_location FROM commitments_ledger WHERE session_id=? AND commitment_type='rendezvous'",
            (session_id,),
        ).fetchall()
        for a in appts:
            a_loc = str(a["target_location"] or "").strip()
            a_parts = [p.strip() for p in re.split(r"\s*(?:➔|->|>)\s*", a_loc) if p.strip()]
            a_leaf = a_parts[-1].lower() if a_parts else ""
            a_prim = a_parts[1].lower() if len(a_parts) >= 2 else (a_parts[0].lower() if a_parts else "")

            matched_a_node = None
            for n in nodes:
                n_low = n["name"].lower()
                if a_leaf and n_low == a_leaf:
                    matched_a_node = n["node_id"]
                    break
                if a_prim and n_low == a_prim:
                    matched_a_node = n["node_id"]
                    break
            if matched_a_node:
                conn.execute("UPDATE commitments_ledger SET target_node_id=? WHERE id=?", (matched_a_node, a["id"]))

    return {
        "status": "migrated",
        "session_id": session_id,
        "current_node_id": current_node_id,
        "node_name": target_node["name"],
        "node_type": target_node["node_type"]
    }


def migrate_all_active_sessions_to_spatial_graph() -> list[dict[str, Any]]:
    """Migrates all active sessions in SQLite to the spatial graph model."""
    results = []
    with db.get_conn() as conn:
        sessions = conn.execute("SELECT id FROM sessions").fetchall()
    for s in sessions:
        res = migrate_session_to_spatial_graph(s["id"])
        results.append(res)
    return results


def resolve_hierarchy_to_node_id(
    session_id: int,
    zone_name: str = "",
    primary_name: str = "",
    sub_name: str = "",
    scen_key: str = "high_school_drama",
    char_name: str = ""
) -> str | None:
    """
    Resolves a tiered location hierarchy into its corresponding spatial graph node_id.
    Delegates to db.resolve_node_id_from_location.
    """
    loc_parts = [p for p in (zone_name, primary_name, sub_name) if p and p != "Main Area"]
    loc_str = " ➔ ".join(loc_parts) if loc_parts else (primary_name or zone_name)
    return db.resolve_node_id_from_location(session_id, loc_str)

