from __future__ import annotations
"""
Smart Campus Mobility & NPC Presence Mechanics for Hikayat.

Provides:
1. Campus Quad / Co-located zone grouping for high school & campus scenarios.
2. Mobile character vs stationary fixture classification.
3. Intentional travel & quest waypoint rendezvous target detection.
4. Active physical presence validation (distinguishing physical presence from passive rumors).
5. Automatic contact location synchronization upon scene arrival.
"""
import json
import re
from typing import Dict, Any, List, Optional, Set, Tuple

import db


CAMPUS_SCENARIOS = {
    "high_school_drama",
    "nsfw_high_school_drama",
    "furry_high_school_drama",
    "nsfw_furry_high_school_drama",
    "modern",
    "academy",
}

def is_campus_scenario(scen_key: str = "") -> bool:
    """Checks if the scenario is a high school, academy, or campus scenario."""
    if not scen_key:
        return False
    s_low = str(scen_key).lower().strip()
    return s_low in CAMPUS_SCENARIOS or any(k in s_low for k in ("school", "academy", "campus", "high_school"))


# Connected campus zones that form a single shared campus realm
CAMPUS_ZONE_KEYWORDS = {
    "academy", "school", "campus", "high school", "high", "institute", "grounds", "athletics",
    "fieldhouse", "quad", "courtyard", "faculty", "dormitory", "dorms",
    "stadium", "sports complex", "gym", "commons", "plaza", "cultural arts",
    "student union", "arts & union", "club wing", "old campus", "clock tower",
    "derelict", "wing"
}

# ---------------------------------------------------------------- Campus Topological Graph & Area Links
CAMPUS_NODE_ACADEMIC = "academic"       # Gateway / Main Entrance
CAMPUS_NODE_COMMONS = "commons"         # Central Hub of the Cross
CAMPUS_NODE_ATHLETICS = "athletics"     # Sports Complex & Stadium
CAMPUS_NODE_ARTS = "arts"               # Cultural Arts & Student Union
CAMPUS_NODE_ABANDONED = "abandoned"     # Old Campus & Clock Tower

CAMPUS_ADJACENCY: Dict[str, Set[str]] = {
    CAMPUS_NODE_COMMONS: {CAMPUS_NODE_ACADEMIC, CAMPUS_NODE_ATHLETICS, CAMPUS_NODE_ARTS, CAMPUS_NODE_ABANDONED},
    CAMPUS_NODE_ACADEMIC: {CAMPUS_NODE_COMMONS},
    CAMPUS_NODE_ATHLETICS: {CAMPUS_NODE_COMMONS},
    CAMPUS_NODE_ARTS: {CAMPUS_NODE_COMMONS},
    CAMPUS_NODE_ABANDONED: {CAMPUS_NODE_COMMONS},
}

CAMPUS_NODE_DISPLAY_NAMES: Dict[str, str] = {
    CAMPUS_NODE_ACADEMIC: "Main Academic Building",
    CAMPUS_NODE_COMMONS: "Student Commons & Central Plaza",
    CAMPUS_NODE_ATHLETICS: "Varsity Athletics Complex",
    CAMPUS_NODE_ARTS: "Cultural Arts & Student Union",
    CAMPUS_NODE_ABANDONED: "Abandoned Old Campus Building",
}


def classify_campus_zone_node(zone_name: str, scen_key: str = "high_school_drama") -> Optional[str]:
    """Classifies a zone name into one of the 5 campus topological nodes, or None if off-campus."""
    if not zone_name or not is_campus_scenario(scen_key):
        return None
    z = zone_name.lower().strip()

    if any(k in z for k in ("old campus", "clock tower", "heritage wing")) or (
        ("abandoned" in z or "derelict" in z)
        and not any(off in z for off in ("port", "warehouse", "dock", "pier", "factory", "industrial"))
    ):
        return CAMPUS_NODE_ABANDONED
    if any(k in z for k in ("cultural arts", "student union", "creative arts", "arts & union", "club annex")):
        return CAMPUS_NODE_ARTS
    if any(k in z for k in ("commons", "central plaza", "courtyard & dining", "promenade & commons", "courtyard")):
        return CAMPUS_NODE_COMMONS
    if any(k in z for k in ("athletics", "sports", "grounds", "gymnasium", "fieldhouse", "stadium", "pool", "dojo", "sheds")):
        return CAMPUS_NODE_ATHLETICS
    if any(k in z for k in ("academy", "school", "campus", "academic", "institute", "high school", "high")):
        return CAMPUS_NODE_ACADEMIC

    return None


def find_campus_travel_path(from_zone: str, to_zone: str, scen_key: str = "high_school_drama") -> List[str]:
    """
    Finds the shortest topological sequence of zones between two zones using BFS on the campus graph.
    Returns a list of zone node identifiers or zone display names.
    """
    node_from = classify_campus_zone_node(from_zone, scen_key)
    node_to = classify_campus_zone_node(to_zone, scen_key)

    # 1. Intra-campus BFS
    if node_from and node_to:
        if node_from == node_to:
            return [node_from]
        queue = [[node_from]]
        visited = {node_from}
        while queue:
            path = queue.pop(0)
            curr = path[-1]
            if curr == node_to:
                return path
            for neighbor in CAMPUS_ADJACENCY.get(curr, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])
        return [node_from, node_to]

    # 2. Campus to Off-Campus: Route through Academic Gateway
    if node_from and not node_to:
        campus_path = find_campus_travel_path(from_zone, "academic", scen_key)
        return campus_path + [to_zone]

    # 3. Off-Campus to Campus: Route through Academic Gateway
    if not node_from and node_to:
        campus_path = find_campus_travel_path("academic", to_zone, scen_key)
        return [from_zone] + campus_path

    # 4. Off-Campus to Off-Campus
    return [from_zone, to_zone]


URBAN_DISTRICT_EDGES: List[Tuple[str, str, int]] = [
    ("zone_agency_hq", "zone_city_center", 10),
    ("zone_agency_hq", "zone_downtown", 12),
    ("zone_agency_hq", "zone_uptown", 12),
    ("zone_agency_hq", "zone_hospital", 10),
    ("zone_city_center", "zone_downtown", 10),
    ("zone_city_center", "zone_uptown", 10),
    ("zone_city_center", "zone_low_cost_wards", 12),
    ("zone_city_center", "zone_suburbs", 15),
    ("zone_city_center", "zone_hospital", 10),
    ("zone_city_center", "zone_chinatown", 10),
    ("zone_downtown", "zone_chinatown", 8),
    ("zone_downtown", "zone_low_cost_wards", 10),
    ("zone_downtown", "zone_city_docks", 15),
    ("zone_downtown", "zone_industrial", 15),
    ("zone_downtown", "zone_theme_park", 12),
    ("zone_chinatown", "zone_low_cost_wards", 10),
    ("zone_chinatown", "zone_eastern_temple", 12),
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
    ("zone_uptown", "zone_botanical_zoo", 12),
    ("zone_uptown", "zone_hospital", 10),
    ("zone_university", "zone_school_campus", 10),
    ("zone_university", "zone_botanical_zoo", 10),
    ("zone_suburbs", "zone_school_campus", 10),
    ("zone_suburbs", "zone_theme_park", 12),
    ("zone_suburbs", "zone_botanical_zoo", 12),
    ("zone_suburbs", "zone_seaside_beach", 20),
    ("zone_city_docks", "zone_seaside_beach", 20),
    ("zone_city_docks", "zone_airport", 15),
    ("zone_theme_park", "zone_seaside_beach", 15),
    ("zone_suburbs", "zone_woods_reserve", 22),
    ("zone_uptown", "zone_woods_reserve", 25),
    ("zone_uptown", "zone_eastern_temple", 15),
    ("zone_eastern_temple", "zone_woods_reserve", 15),
]


def _classify_urban_district_node(zone_name: str) -> Optional[str]:
    if not zone_name:
        return None
    z = zone_name.lower().strip()
    if any(k in z for k in ("headquarters", "operations facility", "command complex", "central spire", "citadel &", "containment", "agency_hq")):
        return "zone_agency_hq"
    if "city center" in z:
        return "zone_city_center"
    if "downtown" in z:
        return "zone_downtown"
    if "uptown" in z:
        return "zone_uptown"
    if any(k in z for k in ("sovereign hills", "sky-estates", "ultra-rich")):
        return "zone_ultra_rich"
    if any(k in z for k in ("lower wards", "tenements", "slums")):
        return "zone_low_cost_wards"
    if "industrial" in z:
        return "zone_industrial"
    if any(k in z for k in ("docks", "harbor")):
        return "zone_city_docks"
    if any(k in z for k in ("suburban", "suburb", "residential")):
        return "zone_suburbs"
    if any(k in z for k in ("theme park", "amusement")):
        return "zone_theme_park"
    if any(k in z for k in ("grand temple", "eastern temple")):
        return "zone_eastern_temple"
    if any(k in z for k in ("airport", "airfield")):
        return "zone_airport"
    if any(k in z for k in ("hospital", "medical center")):
        return "zone_hospital"
    if any(k in z for k in ("university", "parapsychology")):
        return "zone_university"
    if any(k in z for k in ("eastern quarter", "night market", "chinatown")):
        return "zone_chinatown"
    if any(k in z for k in ("under-city", "catacombs", "undercity")):
        return "zone_undercity"
    if any(k in z for k in ("botanical", "aquarium", "zoo")):
        return "zone_botanical_zoo"
    if any(k in z for k in ("high school", "academy", "school", "institute", "campus")):
        return "zone_school_campus"
    if any(k in z for k in ("seaside", "beach", "coastal")):
        return "zone_seaside_beach"
    if any(k in z for k in ("woods", "mountain reserve", "forest")):
        return "zone_woods_reserve"
    return None


def _calculate_urban_district_travel_time(old_z: str, new_z: str) -> Optional[int]:
    import heapq
    from collections import defaultdict
    u_start = _classify_urban_district_node(old_z)
    u_end = _classify_urban_district_node(new_z)
    if not u_start or not u_end:
        return None
    if u_start == u_end:
        return 5
    adj = defaultdict(list)
    for a, b, w in URBAN_DISTRICT_EDGES:
        adj[a].append((b, w))
        adj[b].append((a, w))
    dist = {u_start: 0}
    pq = [(0, u_start)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == u_end:
            return d
        if d > dist.get(u, 9999):
            continue
        for v, w in adj[u]:
            if d + w < dist.get(v, 9999):
                dist[v] = d + w
                heapq.heappush(pq, (d + w, v))
    return 25


def _classify_genre_zone_node(zone_name: str, scen_key: str = "") -> Optional[str]:
    """Classifies a zone display name into a canonical genre zone_id when both match seeded zone archetypes."""
    if not zone_name:
        return None
    z = zone_name.lower().strip()
    s = str(scen_key or "").lower().strip()

    if "slice_of_life" in s:
        if any(k in z for k in ("shopping arcade", "commercial")):
            return "zone_sol_shopping_arcade"
        if any(k in z for k in ("residential", "apartment", "neighborhood")):
            return "zone_sol_residential"
        if any(k in z for k in ("nightlife", "entertainment", "alley")):
            return "zone_sol_nightlife"
        if any(k in z for k in ("harbor", "pier", "waterfront")):
            return "zone_sol_harbor_pier"
        return None

    if "cyberpunk" in s:
        if "city center" in z or "megacorp" in z:
            return "zone_city_center"
        if "downtown" in z:
            return "zone_downtown"
        if "uptown" in z:
            return "zone_uptown_heights"
        if any(k in z for k in ("slums", "lower wards")):
            return "zone_slums_lower_wards"
        if any(k in z for k in ("industrial", "docks")):
            return "zone_industrial_docks"
        if "outskirts" in z:
            return "zone_city_outskirts"
        if "rural" in z:
            return "zone_rural_outpost"
        if "nature reserve" in z or "biodome" in z:
            return "zone_nature_reserve"
        return None

    if "steampunk" in s:
        if any(k in z for k in ("airship", "zeppelin", "cruiser", "leviathan", "sovereign", "ironclad", "dreadnought", "hms", "zephyr", "aether")):
            return "zone_airship_cruiser"
        if "clocktower" in z:
            return "zone_clocktower_center"
        if "promenade" in z:
            return "zone_upper_promenade"
        if any(k in z for k in ("boiler", "foundries", "foundry")):
            return "zone_boiler_foundries"
        if "canal" in z:
            return "zone_subterranean_canals"
        if "rust outskirts" in z or "scrap" in z:
            return "zone_rust_outskirts"
        if "smog" in z or "moor" in z:
            return "zone_smog_moors"
        return None

    if any(k in s for k in ("sci_fi", "scifi", "space")):
        if any(k in z for k in ("starship", "vanguard")):
            return "zone_starship_vanguard"
        if any(k in z for k in ("orbital", "station", "gateway", "nexus")):
            return "zone_orbital_station"
        if "homeworld" in z or "capital" in z:
            return "zone_homeworld_capital"
        if "desert" in z:
            return "zone_desert_planet"
        if "ice" in z or "cryo" in z or "glacial" in z:
            return "zone_ice_planet"
        if "jungle" in z:
            return "zone_jungle_planet"
        if "volcanic" in z or "magma" in z:
            return "zone_volcanic_planet"
        if "ocean" in z or "aquatic" in z:
            return "zone_ocean_planet"
        if "asteroid" in z:
            return "zone_asteroid_belt"
        return None

    if "dark_fantasy" in s or "grimdark" in s:
        if "black citadel" in z:
            return "zone_black_citadel"
        if "blighted marsh" in z:
            return "zone_blighted_marshes"
        if "gallows" in z:
            return "zone_gallows_settlement"
        if "sunken catacomb" in z:
            return "zone_sunken_catacombs"
        if "blood-ash" in z or "blood ash" in z or "crags" in z:
            return "zone_blood_ash_crags"
        if "withered wood" in z:
            return "zone_withered_woods"
        return None

    if "apocalypse" in s or "fallout" in s:
        if "underground vault" in z or "fallout vault" in z:
            return "zone_underground_vault"
        if "scavenger market" in z:
            return "zone_scavenger_market"
        if "irradiated crater" in z:
            return "zone_irradiated_crater"
        if "highway badlands" in z:
            return "zone_highway_badlands"
        if "megacity ruins" in z:
            return "zone_megacity_ruins"
        if "raider fortress" in z:
            return "zone_raider_fortress"
        if "toxic swamp" in z:
            return "zone_toxic_swamp"
        return None

    if "isekai" in s or "fantasy" in s:
        sfx = "_isekai" if "isekai" in s else ""
        if "royal capital" in z or z == "capital city":
            return f"zone_capital_city{sfx}"
        if "central farmland" in z or "central plains" in z:
            return f"zone_central_plains{sfx}"
        if "ancient wood" in z or "primeval" in z:
            return f"zone_ancient_woods{sfx}"
        if "woodlands" in z:
            return f"zone_woodlands_forest{sfx}"
        if "mountain range" in z:
            return f"zone_mountain_range{sfx}"
        if "desert dune" in z:
            return f"zone_desert_dunes{sfx}"
        if "cursed shadowland" in z:
            return f"zone_cursed_shadowlands{sfx}"
        if "ancient dungeon" in z:
            return f"zone_ancient_dungeon{sfx}"
        if not sfx:
            if "coastal harbor" in z:
                return "zone_coastal_harbor"
            if "swamp" in z or "marshes" in z:
                return "zone_swamp_marshes"
            if "frozen" in z or "tundra" in z:
                return "zone_frozen_tundra"
            if "volcanic" in z or "ashland" in z:
                return "zone_volcanic_ashlands"
            if "underworld chasm" in z:
                return "zone_underworld_chasm"
            if "cave network" in z or "deep cave" in z:
                return "zone_cave_network"
    return None


_GENRE_STATELESS_EDGES: List[Tuple[str, str, int]] = [
    # Slice of Life
    ("zone_sol_residential", "zone_sol_shopping_arcade", 15),
    ("zone_sol_shopping_arcade", "zone_sol_nightlife", 15),
    ("zone_sol_shopping_arcade", "zone_sol_harbor_pier", 20),
    ("zone_sol_nightlife", "zone_sol_harbor_pier", 15),
    ("zone_sol_residential", "zone_sol_harbor_pier", 25),
    # Cyberpunk
    ("zone_city_center", "zone_downtown", 15),
    ("zone_city_center", "zone_uptown_heights", 15),
    ("zone_downtown", "zone_slums_lower_wards", 15),
    ("zone_downtown", "zone_industrial_docks", 20),
    ("zone_slums_lower_wards", "zone_industrial_docks", 15),
    ("zone_uptown_heights", "zone_nature_reserve", 25),
    ("zone_city_center", "zone_nature_reserve", 25),
    ("zone_slums_lower_wards", "zone_city_outskirts", 25),
    ("zone_industrial_docks", "zone_city_outskirts", 25),
    ("zone_city_outskirts", "zone_rural_outpost", 30),
    # Steampunk
    ("zone_airship_cruiser", "zone_clocktower_center", 10),
    ("zone_airship_cruiser", "zone_upper_promenade", 12),
    ("zone_airship_cruiser", "zone_rust_outskirts", 30),
    ("zone_airship_cruiser", "zone_smog_moors", 35),
    ("zone_clocktower_center", "zone_upper_promenade", 15),
    ("zone_clocktower_center", "zone_boiler_foundries", 15),
    ("zone_clocktower_center", "zone_subterranean_canals", 20),
    ("zone_boiler_foundries", "zone_subterranean_canals", 15),
    ("zone_boiler_foundries", "zone_rust_outskirts", 30),
    ("zone_rust_outskirts", "zone_smog_moors", 40),
    # Sci-Fi
    ("zone_starship_vanguard", "zone_orbital_station", 10),
    ("zone_orbital_station", "zone_homeworld_capital", 25),
    ("zone_starship_vanguard", "zone_homeworld_capital", 25),
    ("zone_starship_vanguard", "zone_desert_planet", 35),
    ("zone_starship_vanguard", "zone_jungle_planet", 40),
    ("zone_starship_vanguard", "zone_ocean_planet", 40),
    ("zone_starship_vanguard", "zone_asteroid_belt", 45),
    ("zone_starship_vanguard", "zone_ice_planet", 50),
    ("zone_starship_vanguard", "zone_volcanic_planet", 55),
    ("zone_orbital_station", "zone_desert_planet", 40),
    ("zone_orbital_station", "zone_jungle_planet", 45),
    ("zone_orbital_station", "zone_ocean_planet", 45),
    ("zone_orbital_station", "zone_asteroid_belt", 50),
    ("zone_orbital_station", "zone_ice_planet", 55),
    ("zone_orbital_station", "zone_volcanic_planet", 60),
    # Fantasy
    ("zone_capital_city", "zone_central_plains", 60),
    ("zone_capital_city", "zone_coastal_harbor", 75),
    ("zone_capital_city", "zone_woodlands_forest", 75),
    ("zone_central_plains", "zone_woodlands_forest", 60),
    ("zone_central_plains", "zone_coastal_harbor", 75),
    ("zone_central_plains", "zone_mountain_range", 90),
    ("zone_woodlands_forest", "zone_ancient_woods", 90),
    ("zone_woodlands_forest", "zone_swamp_marshes", 90),
    ("zone_coastal_harbor", "zone_desert_dunes", 120),
    ("zone_mountain_range", "zone_cave_network", 75),
    ("zone_mountain_range", "zone_frozen_tundra", 120),
    ("zone_mountain_range", "zone_volcanic_ashlands", 120),
    ("zone_ancient_woods", "zone_ancient_dungeon", 90),
    ("zone_swamp_marshes", "zone_cursed_shadowlands", 120),
    ("zone_desert_dunes", "zone_volcanic_ashlands", 120),
    ("zone_cave_network", "zone_underworld_chasm", 120),
    ("zone_cursed_shadowlands", "zone_ancient_dungeon", 90),
    ("zone_cursed_shadowlands", "zone_underworld_chasm", 150),
    # Isekai
    ("zone_capital_city_isekai", "zone_central_plains_isekai", 60),
    ("zone_capital_city_isekai", "zone_woodlands_forest_isekai", 75),
    ("zone_central_plains_isekai", "zone_woodlands_forest_isekai", 60),
    ("zone_central_plains_isekai", "zone_mountain_range_isekai", 90),
    ("zone_central_plains_isekai", "zone_desert_dunes_isekai", 120),
    ("zone_woodlands_forest_isekai", "zone_ancient_woods_isekai", 90),
    ("zone_ancient_woods_isekai", "zone_ancient_dungeon_isekai", 90),
    ("zone_mountain_range_isekai", "zone_cursed_shadowlands_isekai", 120),
    ("zone_cursed_shadowlands_isekai", "zone_ancient_dungeon_isekai", 90),
    # Dark Fantasy
    ("zone_gallows_settlement", "zone_withered_woods", 60),
    ("zone_gallows_settlement", "zone_blighted_marshes", 75),
    ("zone_gallows_settlement", "zone_sunken_catacombs", 60),
    ("zone_gallows_settlement", "zone_black_citadel", 90),
    ("zone_withered_woods", "zone_blood_ash_crags", 120),
    ("zone_blighted_marshes", "zone_sunken_catacombs", 90),
    ("zone_black_citadel", "zone_blood_ash_crags", 120),
    ("zone_black_citadel", "zone_sunken_catacombs", 90),
    # Post-Apocalypse
    ("zone_underground_vault", "zone_scavenger_market", 60),
    ("zone_underground_vault", "zone_highway_badlands", 75),
    ("zone_scavenger_market", "zone_highway_badlands", 60),
    ("zone_scavenger_market", "zone_megacity_ruins", 90),
    ("zone_scavenger_market", "zone_toxic_swamp", 90),
    ("zone_highway_badlands", "zone_raider_fortress", 90),
    ("zone_highway_badlands", "zone_megacity_ruins", 90),
    ("zone_megacity_ruins", "zone_irradiated_crater", 120),
    ("zone_toxic_swamp", "zone_irradiated_crater", 120),
]


def _calculate_genre_zone_travel_time(old_z: str, new_z: str, scen_key: str) -> Optional[int]:
    import heapq
    from collections import defaultdict
    g_start = _classify_genre_zone_node(old_z, scen_key)
    g_end = _classify_genre_zone_node(new_z, scen_key)
    if not g_start or not g_end:
        return None
    if g_start == g_end:
        return 5
    adj = defaultdict(list)
    for a, b, w in _GENRE_STATELESS_EDGES:
        adj[a].append((b, w))
        adj[b].append((a, w))
    dist = {g_start: 0}
    pq = [(0, g_start)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == g_end:
            return d
        if d > dist.get(u, 99999):
            continue
        for v, w in adj[u]:
            if d + w < dist.get(v, 99999):
                dist[v] = d + w
                heapq.heappush(pq, (d + w, v))
    return None


def calculate_route_travel_time(
    old_loc: str,
    new_loc: str,
    scen_key: str = "high_school_drama",
    session_id: int = 0
) -> int:
    """
    Calculates exact setting-aware travel time in minutes.
    - Same room / Sub-location move: 2 minutes (3 minutes in mega-complexes).
    - Same zone, different Primary Place: 5 minutes (3 minutes on vessels / HQ complexes).
    - Intra-campus travel: 5 minutes per graph link (e.g. Academic ➔ Commons ➔ Athletics = 10 mins).
    - Campus to Off-Campus (or vice-versa): 5 mins per inner campus link + 25 mins from gateway = 25..35 mins.
    - Genre-weighted inter-zone transit graph when seeded or matching canonical zone archetypes.
    - Stateless fallback: 25 minutes (Modern) or 120 minutes (Fantasy).
    """
    if not old_loc or not new_loc or old_loc == new_loc:
        return 2

    if session_id:
        try:
            from_nid = db.resolve_node_id_from_location(session_id, old_loc)
            to_nid = db.resolve_node_id_from_location(session_id, new_loc)
            if from_nid and to_nid:
                graph_mins = db.find_shortest_graph_path_minutes(session_id, from_nid, to_nid)
                if graph_mins is not None:
                    return graph_mins
        except Exception:
            pass

    from mechanics.world.locations import get_zone_location_name, get_primary_location_name
    old_z = get_zone_location_name(old_loc).strip()
    new_z = get_zone_location_name(new_loc).strip()
    old_p = get_primary_location_name(old_loc).strip()
    new_p = get_primary_location_name(new_loc).strip()

    # Same zone
    if old_z.lower() == new_z.lower():
        if old_p.lower() != new_p.lower():
            if any(k in old_z.lower() for k in (
                "headquarters", "operations facility", "command complex", "central spire",
                "containment", "agency_hq", "airship", "zeppelin", "starship", "vanguard",
            )):
                return 3
            return 5
        if any(k in old_p.lower() for k in (
            "tower hq", "operations hq", "operations spire hq", "headquarters", "agency hq",
            "theme park", "amusement", "grand temple", "eastern temple", "hospital",
            "medical center", "botanical",
        )):
            return 3
        return 2

    # Different zone: Multi-Tier Urban Transit Graph for Anomalous Incursions / Urban Fantasy
    if any(k in str(scen_key or "").lower() for k in ("anomalous", "incursion", "urban_anomalies", "urban_fantasy")):
        urban_mins = _calculate_urban_district_travel_time(old_z, new_z)
        if urban_mins is not None:
            return urban_mins

    # Different zone
    is_campus = is_campus_scenario(scen_key)
    if is_campus:
        node_from = classify_campus_zone_node(old_z, scen_key)
        node_to = classify_campus_zone_node(new_z, scen_key)

        # 1. Both on-campus
        if node_from and node_to:
            path = find_campus_travel_path(old_z, new_z, scen_key)
            hops = max(1, len(path) - 1)
            return hops * 5

        # 2. Campus to Off-Campus
        if node_from and not node_to:
            campus_path = find_campus_travel_path(old_z, "academic", scen_key)
            campus_hops = max(0, len(campus_path) - 1)
            base_off = 30 if "mountain park" in new_z.lower() else 25
            return (campus_hops * 5) + base_off

        # 3. Off-Campus to Campus
        if not node_from and node_to:
            campus_path = find_campus_travel_path("academic", new_z, scen_key)
            campus_hops = max(0, len(campus_path) - 1)
            base_off = 30 if "mountain park" in old_z.lower() else 25
            return base_off + (campus_hops * 5)

        # 4. Off-Campus to Off-Campus
        return 30 if ("mountain park" in old_z.lower() or "mountain park" in new_z.lower()) else 25

    genre_mins = _calculate_genre_zone_travel_time(old_z, new_z, scen_key)
    if genre_mins is not None:
        return genre_mins

    # Non-campus modern / sci-fi / steampunk fallback
    from mechanics.system.time_engine import is_modern_setting
    if is_modern_setting(scen_key) or any(k in str(scen_key or "").lower() for k in ("steampunk", "sci_fi", "scifi", "space")):
        return 30 if any(k in str(scen_key or "").lower() for k in ("sci_fi", "scifi", "space")) else 25

    # Fantasy / Wilderness interzone travel
    return 120


def format_travel_route_breadcrumb(
    old_loc: str,
    new_loc: str,
    scen_key: str = "high_school_drama"
) -> str:
    """Formats an evocative travel route string showing intermediate traversal areas."""
    from mechanics.world.locations import get_zone_location_name, get_primary_location_name
    old_z = get_zone_location_name(old_loc)
    new_z = get_zone_location_name(new_loc)
    old_p = get_primary_location_name(old_loc)
    new_p = get_primary_location_name(new_loc)

    total_mins = calculate_route_travel_time(old_loc, new_loc, scen_key=scen_key)

    if old_z.lower() == new_z.lower():
        if old_p.lower() != new_p.lower():
            return f"Route: {old_p} ➔ {new_p} ({total_mins} mins)"
        return f"Route: Local Movement ({total_mins} mins)"

    if is_campus_scenario(scen_key):
        path = find_campus_travel_path(old_z, new_z, scen_key)
        rendered_steps = []
        for step in path:
            if step in CAMPUS_NODE_DISPLAY_NAMES:
                rendered_steps.append(CAMPUS_NODE_DISPLAY_NAMES[step])
            else:
                rendered_steps.append(step)
        route_str = " ➔ ".join(rendered_steps)
        return f"Route: {route_str} ({total_mins} mins)"

    return f"Route: {old_z} ➔ {new_z} ({total_mins} mins)"


def is_campus_co_located(zone_a: str, zone_b: str, scen_key: str = "high_school_drama") -> bool:
    """
    Checks if two zones belong to the same connected school campus quad.
    For example: 'Westlake Academy' and 'School Grounds & Athletics' are
    adjacent facilities of the same school campus.
    """
    if not zone_a or not zone_b:
        return False
    za = zone_a.lower().strip()
    zb = zone_b.lower().strip()
    if za == zb:
        return True

    if not is_campus_scenario(scen_key):
        return False

    node_a = classify_campus_zone_node(za, scen_key)
    node_b = classify_campus_zone_node(zb, scen_key)
    if node_a is not None and node_b is not None:
        return True

    has_a = any(k in za for k in CAMPUS_ZONE_KEYWORDS)
    has_b = any(k in zb for k in CAMPUS_ZONE_KEYWORDS)
    return has_a and has_b
STATIONARY_ROLES = {
    "nurse",
    "school nurse",
    "librarian",
    "head librarian",
    "shopkeeper",
    "merchant",
    "storekeeper",
    "vendor",
    "bartender",
    "barista",
    "barkeep",
    "innkeeper",
    "clerk",
    "curator",
    "cashier",
    "receptionist",
    "statue",
    "fixture",
    "spirit",
    "guardian",
    "blacksmith",
    "armorer",
    "gatekeeper",
}


def is_character_mobile(npc_name: str, contact_data: dict = None, scen_key: str = "high_school_drama") -> bool:
    """
    Determines if an NPC is a mobile character (student, club president, roaming peer)
    or a stationary fixture (librarian at desk, bound ancient spirit, shop counter keeper).
    """
    if not npc_name:
        return False

    contact_data = contact_data or {}
    basic = contact_data.get("basic_info") or {}
    role = str(basic.get("role", "") or contact_data.get("role", "")).lower().strip()
    desc = str(basic.get("description", "") or contact_data.get("description", "")).lower().strip()

    # Check if explicitly a stationary role
    if any(sr in role for sr in STATIONARY_ROLES) or any(sr in desc for sr in ("bound to", "rooted to", "anchored to", "ancient spirit")):
        return False

    # In campus scenarios, students, club heads, and peer characters are naturally mobile
    if is_campus_scenario(scen_key):
        return True

    # Check for general mobile markers
    mobile_roles = {"companion", "ally", "adventurer", "traveler", "scout", "ranger", "mercenary", "messenger", "diplomat"}
    return any(mr in role for mr in mobile_roles)


def is_rendezvous_target(npc_name: str, actions: list = None, session_id: int = None, new_loc: str = "") -> bool:
    """
    Checks if an NPC is the intended target of:
    1. A player travel/meetup action (e.g. 'Travel to gym to meet Sofia Anderson')
    2. An active Story Quest or Side Bounty waypoint at new_loc (e.g. 'Convene meeting with Sofia')
    3. A phone appointment at new_loc
    """
    if not npc_name:
        return False

    import namegen
    n_low = npc_name.lower().strip()
    n_first = n_low.split()[0] if n_low else ""
    n_given = namegen.extract_first_and_last_name(npc_name)[0].lower().strip()
    first_candidates = {tok for tok in (n_first, n_given) if len(tok) >= 3 and tok not in namegen.NAME_PARTICLES_AND_HONORIFICS}

    # 1. Inspect player actions (travel-to-meet actions ONLY)
    travel_meetup_verbs = (
        "meet ", "meet with ", "convene with ", "convene meeting with ",
        "rendezvous with ", "catch up with "
    )
    from mechanics.world.locations import is_movement_action
    for a in (actions or []):
        lbl = (a.get("label") if isinstance(a, dict) else str(a)).lower()
        if is_movement_action(lbl) or any(k in lbl for k in ("travel to", "head to", "walk to", "go to", "visit")):
            if n_low in lbl or any(f" {fc}" in f" {lbl}" for fc in first_candidates):
                if any(mv in lbl for mv in travel_meetup_verbs) or "meet" in lbl or "rendezvous" in lbl:
                    return True

    # 2. Inspect active Story Quest and Side Quests in database
    if session_id:
        try:
            from mechanics.world.waypoints import check_location_matches_waypoint
            sess = db.get_session(session_id)
            sess_node = sess.get("current_node_id", "") if sess else ""

            def _check_loc_or_node_match(target_location_str: str, target_node: str = "") -> bool:
                if not target_location_str and not target_node:
                    return True
                resolved_node = target_node or (db.resolve_node_id_from_location(session_id, target_location_str) if target_location_str else "")
                if sess_node and resolved_node:
                    return db.is_descendant_of(session_id, sess_node, resolved_node) or db.is_descendant_of(session_id, resolved_node, sess_node)
                if not new_loc or not target_location_str:
                    return True
                return check_location_matches_waypoint(new_loc, target_location_str) or check_location_matches_waypoint(target_location_str, new_loc)

            # Check all active quest waypoints
            active_wps = db.get_all_session_active_waypoints(session_id)
            for wp in active_wps:
                wp_text = f"{wp.get('title', '')} {wp.get('objective', '')} {wp.get('notes', '')} {wp.get('stage_label', '')} {wp.get('target_npc', '')}".lower()
                wp_loc = wp.get("target_location") or wp.get("location") or ""
                wp_node = wp.get("target_node_id") or ""
                if _check_loc_or_node_match(wp_loc, wp_node):
                    if n_low in wp_text or any(f" {fc}" in f" {wp_text}" for fc in first_candidates):
                        return True

            # Check active story quest sub-objectives
            sq = db.get_active_story_quest(session_id)
            if sq:
                sq_loc = sq.get("target_location") or sq.get("location") or ""
                sq_node = sq.get("target_node_id") or ""
                sub_objs = sq.get("sub_objectives") or []
                has_active_sub = False
                for so in sub_objs:
                    if isinstance(so, dict) and not so.get("completed"):
                        has_active_sub = True
                        so_text = f"{so.get('text', '')} {so.get('stage_label', '')} {so.get('target_npc', '')}".lower()
                        so_loc = so.get("target_location") or so.get("location") or sq_loc
                        so_node = so.get("target_node_id") or sq_node
                        if _check_loc_or_node_match(so_loc, so_node):
                            if n_low in so_text or any(f" {fc}" in f" {so_text}" for fc in first_candidates):
                                return True

                if not has_active_sub:
                    if _check_loc_or_node_match(sq_loc, sq_node):
                        sq_text = f"{sq.get('title', '')} {sq.get('objective', '')}".lower()
                        if n_low in sq_text or any(f" {fc}" in f" {sq_text}" for fc in first_candidates):
                            return True

            # 3. Inspect phone appointments (only pending appointments or ongoing arrived meetups)
            pending_appts = db.get_phone_appointments(session_id, status="pending")
            arrived_appts = [
                a for a in db.get_phone_appointments(session_id, status="arrived")
                if any(str((x.get("name") or x.get("npc_name")) if isinstance(x, dict) else x).strip().lower() == a.get("npc_name", "").strip().lower() for x in (sess.get("current_npcs") or []))
                or str(sess.get("dialogue_partner") or "").strip().lower() == a.get("npc_name", "").strip().lower()
            ] if sess else []
            for appt in (pending_appts + arrived_appts):
                a_npc = str(appt.get("npc_name", "")).lower().strip()
                a_loc = str(appt.get("rendezvous_location", ""))
                a_node = str(appt.get("target_node_id", "") or "")
                if (n_low in a_npc or a_npc in n_low) and _check_loc_or_node_match(a_loc, a_node):
                    return True
        except Exception:
            pass

    return False


import unicodedata

def _norm_name(text: str) -> str:
    if not text:
        return ""
    return unicodedata.normalize('NFKD', str(text)).encode('ASCII', 'ignore').decode('utf-8').strip().lower()


def get_session_dialogue_partners(session: dict | None) -> list[str]:
    """
    Consolidates the legacy string 'dialogue_partner' and the list/JSON 'dialogue_partners'
    into a canonical, deduplicated list of partner name strings.
    Guards against character-by-character iteration bugs when a string is evaluated.
    """
    if not session or not isinstance(session, dict):
        return []

    partners: list[str] = []

    dps = session.get("dialogue_partners")
    if dps:
        if isinstance(dps, str):
            try:
                parsed = json.loads(dps)
                if isinstance(parsed, list):
                    partners.extend(str(x).strip() for x in parsed if x and str(x).strip())
                elif parsed and str(parsed).strip():
                    partners.append(str(parsed).strip())
            except Exception:
                # If it looks like JSON structure, discard on error rather than treating as NPC name
                cleaned = dps.strip()
                if cleaned and not cleaned.startswith(("{", "[")):
                    partners.append(cleaned)
        elif isinstance(dps, list):
            for p in dps:
                if isinstance(p, list):
                    partners.extend(str(x).strip() for x in p if x and str(x).strip())
                elif p and str(p).strip():
                    partners.append(str(p).strip())

    dp = session.get("dialogue_partner")
    if dp and isinstance(dp, str):
        dp_clean = dp.strip()
        if dp_clean and not any(dp_clean.lower() == existing.lower() for existing in partners):
            if dp_clean.startswith("[") and dp_clean.endswith("]"):
                try:
                    parsed = json.loads(dp_clean)
                    if isinstance(parsed, list):
                        for x in parsed:
                            if x and str(x).strip() and not any(str(x).strip().lower() == existing.lower() for existing in partners):
                                partners.append(str(x).strip())
                except Exception:
                    partners.append(dp_clean)
            else:
                partners.append(dp_clean)

    # Deduplicate while preserving order (case-insensitive)
    seen = set()
    result = []
    for p in partners:
        plow = p.lower()
        if plow not in seen:
            seen.add(plow)
            result.append(p)
    return result


def is_dialogue_partner(name: str, dialogue_partners: list | str = None, session: dict = None) -> bool:
    """Checks if a character name matches any active dialogue partner."""
    if not name:
        return False
    if dialogue_partners is None and session:
        partners_list = get_session_dialogue_partners(session)
    elif not dialogue_partners:
        return False
    elif isinstance(dialogue_partners, str):
        try:
            parsed = json.loads(dialogue_partners)
            partners_list = parsed if isinstance(parsed, list) else [dialogue_partners]
        except Exception:
            partners_list = [dialogue_partners]
    elif isinstance(dialogue_partners, list):
        partners_list = []
        for p in dialogue_partners:
            if isinstance(p, list):
                partners_list.extend(str(x) for x in p if x)
            elif p:
                partners_list.append(str(p))
    else:
        partners_list = [str(dialogue_partners)]

    n_raw = name.strip().lower()
    n_clean = _norm_name(name)
    title_words = {
        "the", "elder", "lord", "lady", "sir", "madam", "madame", "captain", "dr", "mr", "ms", "mrs", "miss", "mx",
        "prof", "professor", "scholar", "guardian", "druid", "student", "council", "president", "vice", "secretary",
        "representative", "officer", "member", "guildmaster", "archivist", "warden",
        "coach", "trainer", "instructor", "principal", "headmaster", "headmistress", "referee", "sensei", "chef", "bartender", "nurse", "clerk", "vendor",
        "bin", "binti", "ibn", "bint", "van", "von", "der", "den", "het", "ten", "ter", "del", "della", "degli", "das", "dos"
    }
    n_tokens = [t for t in n_clean.split() if len(t) > 2 and t not in title_words]
    if not n_tokens and len(n_clean) > 2:
        n_tokens = [n_clean]

    import namegen
    n_stripped = " ".join(w for w in name.split() if w.lower().strip(".,") not in title_words) or name
    n_first, n_last = namegen.extract_first_and_last_name(n_stripped)
    n_first_low = n_first.lower().strip() if n_first else ""
    n_last_low = n_last.lower().strip() if n_last else ""

    male_titles = {"mr", "mr.", "sir", "lord", "father"}
    fem_titles = {"ms", "ms.", "mrs", "mrs.", "lady", "madam", "sister"}
    n_words = set(n_raw.split())

    for p in partners_list:
        p_raw = str(p).strip().lower()
        p_clean = _norm_name(p)
        if not p_clean:
            continue
        if p_raw == n_raw or p_clean == n_clean:
            return True
        p_words = set(p_raw.split())

        # Check gender/title conflict
        if (n_words & male_titles and p_words & fem_titles) or (n_words & fem_titles and p_words & male_titles):
            continue

        p_stripped = " ".join(w for w in str(p).split() if w.lower().strip(".,") not in title_words) or str(p)
        p_first, p_last = namegen.extract_first_and_last_name(p_stripped)
        p_first_low = p_first.lower().strip() if p_first else ""
        p_last_low = p_last.lower().strip() if p_last else ""

        n_first_norm = _norm_name(n_first_low)
        n_last_norm = _norm_name(n_last_low)
        p_first_norm = _norm_name(p_first_low)
        p_last_norm = _norm_name(p_last_low)

        # Detect when a single-word reference (e.g. "Rootspeaker" or "Mr. Kobayashi") refers to the other side's surname/epithet
        p_is_surname_only = (not p_first_norm and bool(p_last_norm)) or (
            bool(p_first_norm) and not p_last_norm and bool(n_last_norm) and p_first_norm in n_last_norm.split()
        )
        n_is_surname_only = (not n_first_norm and bool(n_last_norm)) or (
            bool(n_first_norm) and not n_last_norm and bool(p_last_norm) and n_first_norm in p_last_norm.split()
        )

        # If both entities have explicit given names (neither is a bare surname/epithet reference), they MUST match
        if n_first_norm and p_first_norm and not p_is_surname_only and not n_is_surname_only:
            if n_first_norm != p_first_norm:
                continue

        # If one entity has a gendered title + surname only (e.g. "Mr. Kobayashi") and the other has an opposite-gender given name, reject
        if (p_words & male_titles and p_is_surname_only and n_first_low) or (n_words & male_titles and n_is_surname_only and p_first_low):
            check_given = n_first_low if p_is_surname_only else p_first_low
            if check_given in namegen._ALL_FEMALE_NAMES and check_given not in namegen._ALL_MALE_NAMES:
                continue
        if (p_words & fem_titles and p_is_surname_only and n_first_low) or (n_words & fem_titles and n_is_surname_only and p_first_low):
            check_given = n_first_low if p_is_surname_only else p_first_low
            if check_given in namegen._ALL_MALE_NAMES and check_given not in namegen._ALL_FEMALE_NAMES:
                continue

        if re.search(rf"\b{re.escape(p_clean)}\b", n_clean) or re.search(rf"\b{re.escape(n_clean)}\b", p_clean):
            return True
        p_tokens = {t for t in p_clean.split() if len(t) > 2 and t not in title_words}
        for t in n_tokens:
            if t in p_tokens or re.search(rf"\b{re.escape(t)}\b", p_clean) or re.search(rf"\b{re.escape(t)}\b", p_raw):
                return True
    return False


THIRD_PLACE_KEYWORDS = {
    "cafe", "café", "coffee", "bakery", "tea", "diner", "bistro", "restaurant",
    "park", "gardens", "plaza", "courtyard", "commons", "mall", "arcade",
    "lounge", "bar", "pub", "tavern", "commercial", "strip", "bookstore"
}

MEETUP_INTENT_KEYWORDS = (
    "meet", "meetup", "date", "hangout", "hang out", "catch up",
    "rendezvous", "coffee", "lunch", "dinner", "walk together",
    "walk home", "walk back", "study together", "go together",
    "accompany", "come with", "join me", "tag along", "head out together"
)

def _extract_history_text(h: Any) -> str:
    """Extract narrative and dialogue text from a history entry, ignoring system metadata keys."""
    if isinstance(h, dict):
        parts = [
            h.get("narrative") or "",
            h.get("outcome_narrative") or "",
            h.get("next_narrative") or "",
            h.get("action") or "",
            h.get("player_action") or "",
            h.get("label") or "",
            h.get("content") or "",
        ]
        return " ".join(str(p) for p in parts if p)
    elif isinstance(h, str):
        return h
    return ""


def _has_meetup_intent_keyword(text: str) -> bool:
    """Check if text contains any meetup intent keyword using whole-word boundaries."""
    if not text:
        return False
    t_low = text.lower()
    for kw in MEETUP_INTENT_KEYWORDS:
        pattern = r"\b" + re.escape(kw) + r"\b"
        if re.search(pattern, t_low):
            return True
    return False

SOLO_TRAVEL_PHRASES = (
    "go alone", "going alone", "travel alone", "head alone", "walk alone", "leave alone",
    "by myself", "on my own", "without you", "without her", "without him",
    "stay here", "stay behind", "wait for me", "wait here",
    "i'll go alone", "i want to go alone", "just me", "just myself",
    "don't come", "don't follow", "leave you here"
)

ACCOMPANIED_TRAVEL_PHRASES = (
    "together", "with her", "with him", "with them", "both of us",
    "hand in hand", "holding hands", "walk together", "head out together",
    "our walk", "leave together", "step out together", "join me", "accompany",
    "come with", "tag along",
    "carry her things", "carry his things", "carry their things", "carry things",
    "help carry", "help her carry", "help him carry", "help them carry",
    "walk her to", "walk him to", "walk them to", "walk to class", "walk to homeroom",
    "escort her", "escort him", "escort them", "escort to", "guide her", "guide him", "guide them",
    "bring her", "bring him", "bring them", "to class with", "to homeroom with", "head with", "walk with",
    "moving to a quieter spot", "move to a quieter spot", "quieter spot", "quiet spot", "secluded spot",
    "propose moving to", "suggest moving to", "pull aside", "step aside",
    "speak in private", "talk in private", "private conversation", "private meeting"
)

_SOLO_TRAVEL_REGEX = re.compile(
    r"\b(?:go|going|travel|traveling|head|heading|walk|walking|leave|leaving|depart|departing|return|returning|step|stepping|excuse|excusing)\b[^.!?]*\balone\b",
    re.IGNORECASE,
)


def is_solo_travel_intent(actions: list = None) -> bool:
    """Returns True if the player's action explicitly expresses intent to travel or leave alone."""
    if not actions:
        return False
    for a in actions:
        lbl = (
            (str(a.get("label", "")) + " " + str(a.get("text", "")))
            if isinstance(a, dict)
            else str(a)
        ).lower()
        
        # Guard 1: Accompanied Travel (Keywords or RegEx)
        if (
            any(term in lbl for term in ACCOMPANIED_TRAVEL_PHRASES)
            or re.search(r"\b(?:with|accompany|follow)\s+[a-z]+", lbl)
            or re.search(r"\b(?:together|both of us)\b", lbl)
            or re.search(r"\b(?:carry|walk|escort|guide|lead|take|bring|help)\b.*\b(?:her|him|them)\b", lbl)
        ):
            continue
            
        # Guard 2: Conversational Privacy / Intimacy
        if re.search(r"\b(?:where we can be alone|be alone with|spend some time alone|speak with .* alone|talk to .* alone|confer with .* alone|time alone)\b", lbl):
            continue
            
        # Guard 3: Protective / Defensive
        if re.search(r"\b(?:leave\s+(?:[a-z]+|her|him|them)\s+alone)\b", lbl):
            continue
            
        # Guard 4: Negation
        if re.search(r"\b(?:not\s+alone|don't\s+go\s+alone|won't\s+leave\s+alone|never\s+alone)\b", lbl):
            continue

        if any(p in lbl for p in SOLO_TRAVEL_PHRASES) or _SOLO_TRAVEL_REGEX.search(lbl):
            return True
    return False


def is_social_third_place(loc_str: str) -> bool:
    """Checks if a location is a public social third place (cafe, mall, park, diner, etc.)."""
    if not loc_str:
        return False
    l_low = str(loc_str).lower()
    return any(tp in l_low for tp in THIRD_PLACE_KEYWORDS)


def has_narrative_continuity_bridge(npc_name: str, session: dict = None, actions: list = None, new_loc: str = "") -> bool:
    """
    Checks if an NPC has a verifiable conversational or narrative link to appear at new_loc:
    1. Within the same primary venue (or no location change): active dialogue partner or co-located NPC.
    2. Across different primary venues/zones:
       - Explicit invitation or accompanied travel in current action, OR
       - Recent history (last 1-3 turns) shows a proposal/agreement to meet up, hang out, date, or travel.
    """
    if not npc_name:
        return False

    if is_solo_travel_intent(actions):
        return False

    from mechanics.world.locations import get_primary_location_name
    import namegen

    n_low = npc_name.lower().strip()
    n_given = namegen.get_given_name(npc_name).lower().strip()
    peer_pool = (session.get("current_npcs") or []) if isinstance(session, dict) else None
    n_disambig = namegen.get_unique_person_tokens(npc_name, peer_names=peer_pool, min_len=2)
    first_candidates = {
        tok for tok in ({n_given} | n_disambig)
        if len(tok) >= 2 and tok != n_low and tok not in namegen.NAME_PARTICLES_AND_HONORIFICS
    }

    old_loc = (session.get("current_location") or "") if session else ""
    old_primary = get_primary_location_name(old_loc) if old_loc else ""
    new_primary = get_primary_location_name(new_loc) if new_loc else ""
    is_different_primary = bool(old_primary and new_primary and old_primary.lower() != new_primary.lower())


    is_dp = is_dialogue_partner(npc_name, session=session) if session else False

    # 1. Location changed: Strict spatial boundary.
    # An NPC NEVER follows automatically across rooms or facilities based on dialogue continuity or prose history.
    # They can ONLY move if in party_npcs, temporary_companions, or explicitly accompanied in current action.
    if old_loc and new_loc and old_loc.lower() != new_loc.lower():
        if session:
            party = session.get("party_npcs") or []
            temp_comps = session.get("temporary_companions") or []
            formal_party = session.get("party") or []
            all_party_entries = party + temp_comps + formal_party
            party_names = set()
            party_raw_list = []
            for p in all_party_entries:
                p_obj = p[0] if isinstance(p, (tuple, list)) else p
                p_n = str(p_obj.get("name") if isinstance(p_obj, dict) else p_obj).strip()
                if p_n:
                    party_raw_list.append(p_n)
            all_party_and_scene = party_raw_list + [
                str(x.get("name") if isinstance(x, dict) else x) for x in (peer_pool or []) if x
            ]
            for p_n in party_raw_list:
                party_names.add(p_n.lower())
                party_names |= namegen.get_unique_person_tokens(p_n, peer_names=all_party_and_scene, min_len=2)
            if n_low in party_names or any(fc in party_names for fc in first_candidates):
                return True

        if actions:
            for a in actions:
                lbl = (
                    (str(a.get("label", "")) + " " + str(a.get("text", "")))
                    if isinstance(a, dict)
                    else str(a)
                ).lower()
                if is_dp and (
                    any(term in lbl for term in ACCOMPANIED_TRAVEL_PHRASES)
                    or re.search(r"\b(?:carry|walk|escort|guide|lead|take|bring|help|accompany)\b.*\b(?:her|him|them)\b", lbl)
                    or (isinstance(a, dict) and str(a.get("target_npc") or "").strip().lower() in ({n_low} | first_candidates))
                ):
                    return True
                if n_low in lbl or any(f" {fc}" in f" {lbl}" for fc in first_candidates):
                    if any(k in lbl for k in ("invite", "bring", "escort", "take with", "come with", "with me", "follow")) or re.search(
                        rf"\b(?:with|accompany)\s+(?:{re.escape(n_low)}" + ("".join(rf"|{re.escape(fc)}" for fc in first_candidates)) + r")\b",
                        lbl,
                    ):
                        return True

        # Allow cross-zone / destination arrival ONLY if the NPC was NOT an uninvited patron in old_npcs
        # and recent history (last 3 turns) records an explicit meetup/hangout/date agreement with them.
        if session:
            was_in_old_npcs = any(
                str((on.get("name") or on.get("npc_name")) if isinstance(on, dict) else on).strip().lower() == n_low
                for on in (session.get("current_npcs") or [])
            )
            if not was_in_old_npcs:
                hist_raw = session.get("history") or session.get("history_json") or []
                if isinstance(hist_raw, str):
                    try:
                        hist_list = json.loads(hist_raw)
                    except Exception:
                        hist_list = [hist_raw]
                elif isinstance(hist_raw, list):
                    hist_list = hist_raw
                else:
                    hist_list = []
                recent_hist = hist_list[-3:] if len(hist_list) > 3 else hist_list
                split_patterns = (
                    r"\b(?:split|separate|divide)\s+(?:up|the|our|tasks?|investigation)\b",
                    r"\bgo\s+(?:our\s+)?separate\s+ways\b",
                )
                has_split_up = any(
                    any(re.search(pat, _extract_history_text(h).lower()) for pat in split_patterns)
                    for h in recent_hist
                )
                if not has_split_up:
                    name_pat = r"\b" + re.escape(n_low) + r"\b"
                    for fc in first_candidates:
                        name_pat += r"|\b" + re.escape(fc) + r"\b"
                    for h in recent_hist:
                        h_text = _extract_history_text(h).lower()
                        if h_text and re.search(name_pat, h_text) and _has_meetup_intent_keyword(h_text):
                            return True
        return False

    # 2. Same location (no movement): dialogue partner or co-located bystander retains continuity
    if session and (not old_loc or not new_loc or old_loc.lower() == new_loc.lower()):
        if is_dp:
            return True
        old_npcs = session.get("current_npcs") or []
        for on in old_npcs:
            on_name = str((on.get("name") or on.get("npc_name")) if isinstance(on, dict) else on).strip().lower()
            if on_name and (on_name == n_low or any(on_name.startswith(fc) or f" {fc}" in f" {on_name}" for fc in first_candidates)):
                return True

    return False



def is_mentioned_only_in_dialogue(npc_name: str, text: str) -> bool:
    """Checks if an NPC is mentioned exclusively inside spoken dialogue (in quotation marks)."""
    if not npc_name or not text:
        return False
    import namegen
    n_lower = npc_name.lower().strip()
    first_name = n_lower.split()[0] if len(n_lower.split()) > 1 else n_lower
    given_name = namegen.extract_first_and_last_name(npc_name)[0].lower().strip()

    # Strip paired double quotes and curly quotes
    without_quotes = re.sub(r'["“][^"”]*["”]', ' ', text)
    without_quotes = re.sub(r'‘[^’]*’', ' ', without_quotes)
    without_quotes = re.sub(r'「[^」]*」', ' ', without_quotes)

    pattern = r'\b' + re.escape(n_lower) + r'\b'
    for fc in {first_name, given_name}:
        if len(fc) >= 3 and fc != n_lower and fc not in namegen.NAME_PARTICLES_AND_HONORIFICS:
            pattern += r'|\b' + re.escape(fc) + r'\b'

    in_full = bool(re.search(pattern, text, re.IGNORECASE))
    in_outside = bool(re.search(pattern, without_quotes, re.IGNORECASE))
    return in_full and not in_outside


def has_active_physical_presence(npc_name: str, result: dict, narrative_text: str = "", ignore_departures: bool = False) -> bool:
    """
    Determines if an NPC is physically present in the scene (speaking aloud,
    physically described as present in entity_audit, or acting in narrative),
    distinguishing real presence from passive conversational rumors or departures.
    """
    if not npc_name:
        return False

    import namegen
    n_low = npc_name.lower().strip()
    n_first = n_low.split()[0] if n_low else ""
    first_last = namegen.extract_first_and_last_name(npc_name)
    n_given = first_last[0].lower().strip() if first_last else ""
    n_surname = first_last[1].lower().strip() if len(first_last) > 1 else ""

    name_candidates = {tok for tok in (n_first, n_given, n_surname) if len(tok) >= 3 and tok not in namegen.NAME_PARTICLES_AND_HONORIFICS}
    if n_surname and n_first in namegen.NAME_PARTICLES_AND_HONORIFICS:
        name_candidates.add(f"{n_first} {n_surname}")
        name_candidates.add(f"{n_first.rstrip('.')} {n_surname}")

    # Check if explicitly departed
    if not ignore_departures:
        departures = [str(x).lower().strip() for x in (result.get("npc_departures") or [])]
        entity_audit = result.get("entity_audit") or {}
        if isinstance(entity_audit, dict):
            departures.extend(str(x).lower().strip() for x in (entity_audit.get("departed_characters") or []))
        if any(n_low in d or any(fc in d for fc in name_candidates) for d in departures):
            return False

    # If mentioned ONLY inside spoken dialogue quotes, they are being talked about, NOT present
    if narrative_text and is_mentioned_only_in_dialogue(npc_name, narrative_text):
        return False

    # 1. Check physical state actors, entity_audit speaking_characters & present_named_characters
    phys_actors = (result.get("_physical_state") or {}).get("actors") or {}
    if isinstance(phys_actors, dict):
        for pa_name in phys_actors:
            pa_low = pa_name.lower().strip()
            if pa_low == n_low or pa_low in name_candidates or (n_low in pa_low or pa_low in n_low):
                return True

    entity_audit = result.get("entity_audit") or {}
    if isinstance(entity_audit, dict):
        speaking = [str(x).lower().strip() for x in (entity_audit.get("speaking_characters") or [])]
        if any(n_low == s or s in name_candidates or (n_low in s or s in n_low) for s in speaking if s):
            return True

        present = [str(x).lower().strip() for x in (entity_audit.get("present_named_characters") or [])]
        if any(n_low == p or p in name_candidates or (n_low in p or p in n_low) for p in present if p):
            return True

    # 2. Check speaking characters and physical action in narrative
    if narrative_text:
        nar_norm = narrative_text.lower()
        nar_without_dialogue = re.sub(r'["“][^"”]*["”]', ' ', nar_norm)
        nar_without_dialogue = re.sub(r'‘[^’]*’', ' ', nar_without_dialogue)
        nar_without_dialogue = re.sub(r'「[^」]*」', ' ', nar_without_dialogue)
        nar_without_dialogue = re.sub(r'[—–]', ' ', nar_without_dialogue)

        pattern = r'\b' + re.escape(n_low) + r'\b'
        for fc in name_candidates:
            if fc != n_low:
                pattern += r'|\b' + re.escape(fc) + r'\b'

        has_in_prose = bool(re.search(pattern, nar_without_dialogue))

        if has_in_prose:
            # Check if mentioned in thought, recollection, or hypothetical contemplation
            thought_pattern = (
                r'\b(?:thought\s+(?:about|of)?|thinking\s+(?:about|of)?|wondered\s+(?:about|if|what|how)?|'
                r'wonders\s+(?:about|if|what|how)?|wondering\s+(?:about|if|what|how)?|remembered|imagined|'
                r'recalled|wished\s+(?:that)?|hoped\s+(?:that)?|news\s+of|heard\s+(?:about|from))\b[^.!?\n]*?(?:' + pattern + r')\b'
            )
            is_in_thought = bool(re.search(thought_pattern, nar_norm))

            action_verbs = {
                "says", "said", "asks", "asked", "replies", "replied", "greets", "greeted",
                "pushes", "stands", "stood", "standing", "leans", "leaned", "leaning", "looks", "looked", "shifts",
                "shifted", "smiles", "smiled", "smirks", "smirked", "steps", "stepped",
                "waves", "waved", "nods", "nodded", "sits", "sat", "sitting", "takes", "took", "waits",
                "waited", "waiting", "arrives", "arrived", "watches", "watched", "watch",
                "laughs", "laughed", "remarks", "remarked", "sips", "sipped", "orders",
                "ordered", "pauses", "paused", "tilts", "tilted", "cuts", "walks", "walked",
                "joins", "joined", "listen", "listens", "listened", "gathers", "gathered",
                "glances", "glanced", "turns", "turned", "approaches", "approached", "whispers",
                "whispered", "clutches", "clutched", "holds", "held", "carries", "carried",
                "scans", "scanning", "reads", "writes", "scribbles", "scribbled", "scribbling",
                "gestures", "gestured", "gesturing", "seated", "speaks", "spoke",
                "catches", "caught", "catching", "frowns", "frowned", "frowning",
                "pulls", "pulled", "pulling", "retrieves", "retrieved", "retrieving",
                "releases", "released", "releasing", "snaps", "snapped", "snapping",
                "sighs", "sighed", "sighing", "hunched", "working", "works", "worked",
                "secures", "secured", "securing", "struggles", "struggled", "struggling",
                "trembles", "trembled", "trembling", "tries", "tried", "trying",
                "examines", "examined", "examining", "inspects", "inspected", "inspecting",
                "adjusts", "adjusted", "adjusting", "fiddling", "pouring", "pours", "poured"
            }

            # 1. Direct subject + (optional adverb) + action verb: "Sofia smiled", "Maya slowly walked"
            subj_verb_re = re.compile(
                r'\b(?:' + pattern + r')\s+(?:(?:quietly|softly|calmly|slowly|suddenly|gently|warmly|nervously|confidently|playfully|curiously|brightly|coldly|silently|hesitantly|abruptly)\s+)?(?:' +
                '|'.join(action_verbs) + r')\b',
                re.IGNORECASE
            )
            if subj_verb_re.search(nar_without_dialogue):
                return True

            # 2. Inverted speech attribution: "said Sofia", "asked Maya"
            speech_attr_re = re.compile(
                r'\b(?:said|asks|asked|replied|replies|remarks|remarked|whispered|whispers|called|called out)\s+(?:by\s+)?(?:' + pattern + r')\b',
                re.IGNORECASE
            )
            if speech_attr_re.search(nar_norm):
                return True

            # 3. Inverted verb-subject positioning: "stands Sofia", "sits Maya", "approaches Rachel"
            inv_verb_re = re.compile(
                r'\b(?:stands|stood|sits|sat|waits|waited|approaches|approached|enters|entered|arrives|arrived)\s+(?:' + pattern + r')\b',
                re.IGNORECASE
            )
            if inv_verb_re.search(nar_without_dialogue):
                return True

            # 4. Explicit physical copresence / positioning: "beside Sofia", "accompanied by Maya", "seated next to Sofia"
            positioning_re = re.compile(
                r'\b(?:beside|next to|near|behind|in front of|approaching|facing|flanked by|accompanied by|seated with)\s+(?:' + pattern + r')\b',
                re.IGNORECASE
            )
            if positioning_re.search(nar_without_dialogue) and not is_in_thought:
                return True

            # 5. Sentence-bounded clause check: If not in thought, check if any action verb is in the sentence
            if not is_in_thought:
                sentences = re.split(r'[.!?\n]+', nar_without_dialogue)
                for sent in sentences:
                    if re.search(pattern, sent):
                        if any(re.search(r'\b' + re.escape(v) + r'\b', sent) for v in action_verbs):
                            return True

    return False



def sync_contact_locations(final_npcs: list, new_loc: str, session_id: int):
    """
    Automatically synchronizes and updates the canonical 'location' field in contacts
    for all NPCs verified to be physically present in the scene.
    """
    if not final_npcs or not new_loc or not session_id:
        return

    try:
        known_contacts = db.get_contacts(session_id)
        for npc in final_npcs:
            if not isinstance(npc, dict):
                continue
            n_name = (npc.get("name") or "").strip()
            if not n_name:
                continue
            n_low = n_name.lower()

            matched_c = next((
                c for c in known_contacts
                if str(c.get("name", "")).strip().lower() == n_low or
                str(c.get("npc_id", "")).strip().lower() == n_low.replace(" ", "_")
            ), None)

            if matched_c:
                basic = dict(matched_c.get("basic_info") or {})
                curr_c_loc = basic.get("location", "")
                if curr_c_loc != new_loc:
                    basic["location"] = new_loc
                    db.upsert_contact(
                        session_id=session_id,
                        character_id=matched_c.get("character_id", 0),
                        npc_id=matched_c.get("npc_id") or n_name,
                        name=n_name,
                        basic_info=basic,
                        track=matched_c.get("track", "platonic")
                    )
    except Exception:
        pass
