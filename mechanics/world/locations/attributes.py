from __future__ import annotations
from .constants import *
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import db
from .seeds import *
from .seeds import _load_seeds, _slugify, _SEED_PATH

def is_hub_location(location_str: str) -> bool:

    """Checks if a location string contains hub/safe-zone keywords."""

    if not location_str:

        return False

    location_lower = location_str.lower()

    keywords = [

        "town", "city", "village", "outpost", "market", "bazaar", "camp", "tavern", "inn",

        "station", "haven", "trading post", "merchant", "academy", "school", "campus",

        "plaza", "promenade", "shelter", "vault", "sanctuary", "residential", "residence",

        "starship", "vanguard", "airship", "zeppelin", "hub", "leviathan", "sovereign",

        "dreadnought", "hms", "ironclad", "zephyr", "aether", "celestial", "capital"

    ]

    return any(keyword in location_lower for keyword in keywords)

def is_location_engine_enabled(scenario_key: str) -> bool:

    """Checks if the tiered location engine is enabled for a given scenario."""

    if not scenario_key:

        return False

    # The location engine is now enabled globally for all scenarios.

    return True

def get_zone_emoji(zone_name: str, scen_key: str = "") -> str:

    """

    Returns an intuitive, thematic biome/district emoji for a Tier 1 Zone.

    Used on the Game Dashboard and World Map to instantly signal the environment type.

    """

    if not zone_name:

        return "📍"

    z_lower = zone_name.lower()



    # Space & Planets

    if any(k in z_lower for k in ("planet", "world)", "colony", "asteroid")):

        return "🪐"

    # Space Stations & Starships

    if any(k in z_lower for k in ("station", "starship", "vanguard", "orbital", "gateway", "nexus", "satellite")):

        return "🚀"

    # Airships & Zeppelins

    if any(k in z_lower for k in ("airship", "zeppelin", "leviathan", "sovereign", "ironclad", "kraken", "dreadnought", "titan", "swallow", "hms", "zephyr", "aether", "aerodrome")):

        return "🎈"

    # Cultural Arts & Student Union

    if any(k in z_lower for k in ("cultural arts", "student union", "creative arts", "arts & union", "club annex")):

        return "🎭"

    # Student Commons & Central Plaza

    if any(k in z_lower for k in ("commons", "central plaza", "courtyard & dining", "promenade & commons")):

        return "🌸"

    # Athletics / Sports Grounds

    if any(k in z_lower for k in ("athletics", "sports", "stadium", "gymnasium", "running track")):

        return "🏟️"

    # High School & Modern Campus

    if any(k in z_lower for k in ("academy", "school", "campus", "institute", "high school")):

        return "🏫"

    # Royal Capitals & Great Citadels

    if any(k in z_lower for k in ("royal capital", "capital city", "citadel", "imperial palace", "palace")):

        return "🏰"

    # Volcanic, Ashlands & Foundries

    if any(k in z_lower for k in ("volcanic", "ashland", "caldera", "foundry", "magma", "lava", "cinder", "pyre", "crater basin")):

        return "🌋"

    # Mountains, Peaks & Alpine Highlands

    if any(k in z_lower for k in ("mountain", "mountains", "range", "peak", "peaks", "crag", "crags", "cliff", "highland", "ridge", "alpine", "dragonspine", "skyreach", "cloudspire")):

        return "⛰️"

    # Snow, Ice & Freezing Tundra

    if any(k in z_lower for k in ("tundra", "snow", "ice", "frost", "glacial", "frozen", "cryo", "everwinter", "rimewind", "glaciem", "frostfell", "frostbite", "winterveil", "shiverstone")):

        return "❄️"

    # Swamps, Marshes & Bogs

    if any(k in z_lower for k in ("swamp", "marsh", "bog", "fen", "mire", "bayou", "mangrove", "blighted marsh")):

        return "🌿"

    # Cursed / Undead / Catacombs / Shadowlands

    if any(k in z_lower for k in ("cursed", "shadowland", "shadowveil", "dreadfall", "soul-grave", "necropolis", "graveyard", "gallows")):

        return "💀"

    # Underworld, Abyss & Chasms

    if any(k in z_lower for k in ("underworld", "chasm", "abyss", "underdark", "trench", "rift", "void", "fissure")):

        return "🕳️"

    # Caves & Caverns

    if any(k in z_lower for k in ("cave", "cavern", "grotto", "subterranean", "mine", "shaft", "stalactite")):

        return "🦇"

    # Dungeons & Strongholds

    if any(k in z_lower for k in ("dungeon", "labyrinth", "catacomb", "crypt", "tomb", "stronghold", "fortress", "keep", "vaults", "gauntlet", "ancient citadel")):

        return "⚔️"

    # Deserts, Badlands & Dunes

    if any(k in z_lower for k in ("desert", "dune", "sand", "oasis", "badland", "arid", "sunscorched", "wasteland")):

        return "🏜️"

    # Harbor Ports & Docks

    if any(k in z_lower for k in ("harbor", "port", "dock", "quay", "pier", "tidehaven", "blackanchor", "silverwind")):

        return "⚓"

    # Seaside, Beach & Coastal Bays

    if any(k in z_lower for k in ("seaside", "beach", "coast", "bay", "shore", "waterfront")):

        return "🏖️"

    # Ancient / Primeval Deep Woods

    if any(k in z_lower for k in ("ancient wood", "ancient forest", "primeval", "elderwood", "deep wood", "withered wood", "canopy")):

        return "🌳"

    # Standard Woods & Forests

    if any(k in z_lower for k in ("wood", "forest", "thicket", "grove", "timber", "copse", "taiga", "trees", "sylvan", "greenvale", "briarwood")):

        return "🌲"

    # Farmlands, Plains & Valleys

    if any(k in z_lower for k in ("farmland", "plain", "field", "valley", "pasture", "meadow", "prairie", "rural", "amberfield", "sunreach", "harvest-vale")):

        return "🌾"

    # Megacity Districts & Commercial Cores

    if any(k in z_lower for k in ("city center", "downtown", "uptown", "commercial", "shopping", "megacorp", "plaza", "promenade", "metropolis")):

        return "🏙️"

    # Residential & Suburbs & Slums

    if any(k in z_lower for k in ("residential", "neighborhood", "slum", "ward", "district", "suburb", "scrap-town", "settlement")):

        return "🏘️"

    # Fallout Shelters & Vaults

    if any(k in z_lower for k in ("fallout vault", "shelter", "fallout", "bunker", "irradiated", "radiation")):

        return "☢️"

    # Recreational Parks & Mountain Parks

    if any(k in z_lower for k in ("mountain park", "recreation", "nature reserve", "botanical")):

        return "🌲"

    # Abandoned / Haunted flavor sites

    if any(k in z_lower for k in ("abandoned", "haunted", "manor", "ruin", "colliery")):

        return "🏚️"



    return "📍"

def get_location_scout_description(session_id: int, location_str: str, scen_key: str = "fantasy", char_name: str = "") -> str:

    """

    Generates a rich, atmospheric layout and sensory scouting description for a location.

    Pulls structured sub-locations, zone theme, and environmental features from seed data

    without outputting raw database dumps or prop lists.

    """

    ensure_session_locations_seeded(session_id, scen_key, char_name=char_name)

    z_name, p_name, s_name = parse_tiered_location(location_str, scen_key, session_id=session_id, char_name=char_name)



    seeds = _load_seeds()

    scen_data = seeds.get(scen_key) or seeds.get("fantasy") or {}

    zone_list = scen_data.get("zones", [])



    matched_zone = None

    matched_primary = None

    for z in zone_list:

        if z.get("name", "").lower() == z_name.lower() or z_name.lower() in z.get("name", "").lower():

            matched_zone = z

            for p in z.get("primary_locations", []):

                if p.get("name", "").lower() == p_name.lower() or p_name.lower() in p.get("name", "").lower():

                    matched_primary = p

                    break

            break



    if matched_primary is None:

        for z in zone_list:

            for p in z.get("primary_locations", []):

                if p.get("name", "").lower() == p_name.lower() or p_name.lower() in p.get("name", "").lower():

                    matched_primary = p

                    if not matched_zone:

                        matched_zone = z

                    break

            if matched_primary:

                break



    sub_names = []

    if matched_primary:

        sub_names = [sub.get("name") for sub in matched_primary.get("sub_locations", []) if sub.get("name")]

    

    if not sub_names and session_id:

        existing = db.get_session_locations(session_id)

        for r in existing:

            if r.get("primary_name", "").lower() == p_name.lower() and r.get("sub_locations_json"):

                try:

                    subs = json.loads(r["sub_locations_json"])

                    if isinstance(subs, list):

                        sub_names = [s.get("name") if isinstance(s, dict) else str(s) for s in subs]

                except Exception:

                    pass



    lines = []

    lines.append(f"**📍 Scouting Area: {p_name} ({z_name})**\n")



    if matched_zone:

        if matched_zone.get("sensory"):

            lines.append(f"*{matched_zone['sensory']}*\n")

        elif matched_zone.get("features"):

            lines.append(f"*{matched_zone['features']}*\n")



    if sub_names:

        clean_subs = ", ".join(f"**{s}**" for s in sub_names[:5])

        lines.append(f"• **Key Sections & Layout**: {clean_subs}")



    # Check for active quest waypoints at this location

    from mechanics.world.waypoints import check_location_matches_waypoint

    active_wps = db.get_all_session_active_waypoints(session_id)

    local_wps = [wp for wp in active_wps if check_location_matches_waypoint(location_str, wp.get("target_location", ""))]

    if local_wps:

        for wp in local_wps:

            wp_label = wp.get("stage_label", "")

            is_story = bool(wp.get("is_story_quest") or "SQ-" in str(wp.get("quest_id", "")))

            tag = "Story Lead" if is_story else "Bounty Lead"

            lines.append(f"• **⭐ {tag}**: Notable interest centered around *\"{wp_label}\"*.")



    return "\n".join(lines)

def get_regional_guild_name(zone_name: str, scenario_key: str = "fantasy") -> str:

    """

    Returns the distinct name for an Adventurers' Guild building in a given zone:

    - Capital / Major City: 'Adventurers' Guild Headquarters' (or 'Adventurers' Guild Hall')

    - Frontier / Wilderness / Dangerous Zone: 'Guild Outpost: [Area]'

    - Regional Hub / Town / Farmlands: 'Guild Branch: [Area]'

    """

    z_low = str(zone_name or "").lower()

    short_z = get_clean_zone_short_name(zone_name)



    # Capital / Central Metropolis

    if any(k in z_low for k in ("capital", "imperial", "solaria", "highspire", "lunaria", "aethelgard", "metropolis", "grand city")):

        return "Adventurers' Guild Headquarters"



    # Wilderness / Frontier / Forest

    if any(k in z_low for k in ("forest", "woods", "mountain", "mountains", "peak", "frontier", "vale", "swamp", "marsh", "desert", "tundra", "crag", "ruins", "wilds")):

        return f"Guild Outpost: {short_z}"



    return f"Guild Branch: {short_z}"

def get_location_archetype(primary_name: str, zone_name: str = "", scen_key: str = "") -> tuple[str, str]:

    """

    Returns (archetype_name, emoji) for a Tier 2 primary place.

    Provides concrete spatial anchoring and distinct gameplay/narrative flavor across all scenarios.

    """

    if not primary_name:

        return ("Landmark / Area", "🗺️")

    p_lower = str(primary_name).strip().lower()



    # Specialized thematic archetypes for School / Slice-of-Life / Modern scenarios

    if is_school_scenario(scen_key):

        # 1. Disused & Abandoned / Rumored

        if re.search(r"\b(abandoned|derelict|haunted|decaying|dilapidated|ruin|ruins)\b", p_lower):

            return ("Disused & Rumored", "🏚️")



        # 2. Secluded & Club / Secret Hangout

        if any(k in p_lower for k in ("storage room", "music room", "behind gym", "sheds", "club room", "secret hangout", "hideout")):

            return ("Secluded & Club", "🤫")



        # 3. Campus Administration & Faculty

        if any(k in p_lower for k in ("student council", "council office", "staff room", "teachers' staff", "faculty", "principal", "guidance", "infirmary", "nurse")):

            return ("Campus Administration", "🏛️")



        # 4. Social & Hangout (Cafés, Bakeries, Diners, Lounges)

        if (

            re.search(r"\b(café|cafe|coffee|bakery|restaurant|diner|boba|ramen|canteen|cafeteria|snack shack)\b", p_lower)

            or any(k in p_lower for k in ("tea lounge", "tea house", "tea room", "tea shop", "coffee & tea"))

        ) and "karaoke" not in p_lower:

            return ("Social & Hangout", "☕")



        # 5. Entertainment & Leisure (Arcades, Karaoke, Game Lounges)

        if re.search(r"\b(arcade|karaoke|bowling|cinema|theater|theatre)\b", p_lower) or any(k in p_lower for k in ("game center", "game lounge", "game bar")):

            return ("Entertainment & Leisure", "🎮")



        # 6. Retail & Shopping (Convenience stores, boutiques, shopping strips)

        if re.search(r"\b(convenience|store|shop|market|boutique|bookstore|stationery|mall|shopping|promenade|strip)\b", p_lower):

            return ("Retail & Shopping", "🛍️")



        # 7. Classroom & Study

        if any(k in p_lower for k in ("classroom", "homeroom", "library", "lab", "laboratory", "science lab", "chemistry", "study", "lecture", "auditorium", "stage")):

            return ("Classroom & Study", "🏫")



        # 8. Sports & Athletics

        if any(k in p_lower for k in ("gymnasium", "gym", "swimming pool", "pool", "athletic field", "field", "track", "running track", "bleachers", "court", "basketball", "dojo", "tennis", "soccer")):

            return ("Sports & Athletics", "⚽")



        # 9. Home & Residence

        if "house" in p_lower or "bedroom" in p_lower or "residence" in p_lower or "apartment" in p_lower or "dorm" in p_lower or "living quarters" in p_lower:

            return ("Home & Residence", "🏠")



        # 10. Campus Circulation & Common Walkways

        if any(k in p_lower for k in ("hallway", "hallways", "corridor", "foyer", "shoe lockers", "lockers", "stair", "stairs", "entrance", "lobby", "courtyard", "skywalk", "rooftop")):

            return ("Campus Circulation", "🚶")



        # 11. Parks & Outdoors / Scenic Landmarks

        if any(k in p_lower for k in ("park", "beach", "pier", "coastline", "lake", "mountain", "lookout", "campsite", "cabin", "summit", "trail", "reserve", "nature", "garden", "cherry tree")):

            return ("Parks & Outdoors", "🌳")



        return ("Campus Area", "🏫")



    # 1. Monster Lairs / Dens / Hideouts / Smuggler Nests (Word-boundary matching prevents "student" matching "den")

    if re.search(r"\b(lair|lairs|den|dens|nest|nests|nesting|chop-shop|smuggler|hideout|hideouts|coven|mutant|spider|bone tent|war-den)\b", p_lower):

        return ("Monster Lair / Den", "🦇")



    # 2. Forgotten Ruins / Catacombs / Abandoned Sites / Tombs

    if re.search(r"\b(ruin|ruins|ruined|abandoned|derelict|haunted|catacomb|catacombs|ossuary|tomb|tombs|crypt|crypts|colliery|graveyard|scrap-titan|sunken|desecrated|overgrown|collapsed|withered|corrupted|hollowed|dusty|dilapidated)\b", p_lower):

        return ("Ruins / Abandoned", "🏚️")



    # 3. Historic Battlegrounds / Barrow Mounds / Memorials

    if re.search(r"\b(warfield|battlefield|barrow|mound|mounds|cairn|cairns|hanging tree)\b", p_lower):

        return ("Historic Battleground", "🪦")



    # 4. Arcane Anomalies / Natural Rifts / Craters

    if re.search(r"\b(rift|rifts|anomaly|anomalies|distortion|caldera|crater|craters|quantum core)\b", p_lower):

        return ("Arcane / Natural Anomaly", "🌀")



    # 5. Natural Grottos / Caverns / Springs

    if re.search(r"\b(spring|springs|geode|thermal|cavern|caverns)\b", p_lower):

        return ("Natural Grotto", "💧")



    # 6. Infrastructure / Worksites / Facilities / Laboratories

    if any(k in p_lower for k in (

        "mill", "quarry", "mine", "foundry", "refinery", "furnace", "lab", "laboratory",

        "workshop", "drydock", "facility", "gymnasium", "gym", "swimming pool", "pool",

        "boiler", "engine room", "airlock", "hangar", "terminal", "cargo",

        "power plant", "purification", "solar", "bio-dome", "clinic", "ripperdoc"

    )):

        return ("Infrastructure / Facility", "🛠️")



    # 7. Campsites / Forward Encampments / Bivouacs (Word-boundary matching prevents "campus" matching "camp")

    if re.search(r"\b(campsite|campsites|bivouac|encampment|camp|camps|tent|tents)\b", p_lower):

        return ("Campsite / Encampment", "🏕️")



    # 8. Solitary Dwellings / Hermitages / Retreats

    if re.search(r"\b(hut|huts|cabin|cabins|bothy|shack|shacks|hermitage|nurse)\b", p_lower):

        return ("Solitary Retreat", "🛖")



    # 9. Sacred Sites / Shrines / Altars / Temples

    if re.search(r"\b(shrine|shrines|altar|altars|moonwell|monolith|temple|temples|chapel|cathedral|nave|sanctum|leyline|summoning chamber)\b", p_lower):

        return ("Sacred / Mystical", "🔮")



    # 10. Havens / Settlements / Community Centers / Commercial Hubs / Guilds / Administrative Offices

    if (

        any(k in p_lower for k in (

            "village", "town", "hamlet", "settlement", "outpost", "sanctuary", "haven",

            "guild", "market", "bazaar", "plaza", "tavern", "inn", "canteen", "saloon", "lodge",

            "café", "cafe", "arcade", "karaoke", "homeroom", "classroom", "library",

            "residence", "apartment", "living quarters", "dormitory", "penthouse",

            "convenience", "student council", "council office", "staff room", "teachers' staff",

            "office", "faculty", "lounge", "hab", "enclave", "promenade"

        )) or ("house" in p_lower and "lighthouse" not in p_lower)

    ):

        return ("Haven / Settlement", "🏡")



    # 11. Strongholds / Fortresses / Bastions / Guard Keeps

    if any(k in p_lower for k in (

        "fortress", "fort", "stronghold", "bastion", "keep", "watchtower", "watchpost",

        "citadel", "palisade", "barricade", "garrison", "precinct", "black site",

        "command bridge", "overseer", "armory", "gladiator"

    )):

        return ("Stronghold / Fort", "⚔️")



    # 12. Transit Crossings / Chokepoints / Circulation

    if any(k in p_lower for k in (

        "bridge", "gate", "tollgate", "crossing", "ferry", "pier", "boardwalk",

        "hallway", "hallways", "corridor", "foyer", "lockers", "stairs", "skywalk",

        "turnstile", "skybridge", "dock", "docks", "waypoint", "portal", "checkpoint",

        "lighthouse"

    )):

        return ("Transit Crossing", "🌉")



    # 13. Geographical Landmarks / Natural Overlooks / Grounds

    if any(k in p_lower for k in (

        "pass", "overlook", "summit", "peak", "canyon", "gorge", "valley", "archway",

        "lake", "beach", "shoreline", "field", "courtyard", "garden", "park", "clearing",

        "meadow", "bluff", "ridge", "rooftop"

    )):

        return ("Geographical Landmark", "🗺️")



    return ("Landmark / Area", "🗺️")

def location_has_bounty_board(location_str: str, scen_key: str = None) -> bool:

    """Checks if a location string contains notice board, guild hall, student council, or bounty hub keywords."""

    if not location_str:

        return False

    loc_lower = location_str.lower()

    keywords = [

        "guild", "board", "bulletin", "notice", "bounty", "kiosk", "terminal", "precinct",

        "outpost", "cantina", "lodge", "tavern", "inn", "saloon", "headquarters", "station",

        "student council", "entrance", "lockers", "lobby", "courtyard", "foyer", "library",

        "archive", "hallway", "town square", "dispatch", "aerodrome", "hangar", "depot",

        "village", "settlement", "market", "bazaar", "plaza", "sanctuary", "haven"

    ]

    return any(k in loc_lower for k in keywords)

def get_available_merchant_types_for_location(location_str: str, scen_key: str = None) -> list[dict]:

    """

    Returns a list of available specialist merchant stores for the current location.

    Each entry is a dict: {"type": str, "title": str, "emoji": str, "description": str}.

    """

    from mechanics.combat.merchant import MERCHANT_ARCHETYPES

    from scenario_data import is_nsfw_scenario



    if not location_str:

        return [{"type": "general_merchant", **MERCHANT_ARCHETYPES["general_merchant"]}]



    loc_lower = str(location_str).lower()

    is_nsfw = is_nsfw_scenario(scen_key) if scen_key else False



    # 1. Non-Combat / High School Scenarios

    if scen_key and is_school_scenario(scen_key):

        stores = []

        if any(k in loc_lower for k in ["co-op", "bookstore", "school store", "stationery"]):

            stores.append({"type": "school_merchant", **MERCHANT_ARCHETYPES["school_merchant"]})

        if any(k in loc_lower for k in ["cafe", "café", "boba", "bakery", "diner", "coffee", "canteen", "cafeteria", "tea house"]):

            stores.append({"type": "cafe_merchant", **MERCHANT_ARCHETYPES["cafe_merchant"]})

        if any(k in loc_lower for k in ["boutique", "clothing", "apparel", "fashion", "mall"]):

            stores.append({"type": "clothes_merchant", **MERCHANT_ARCHETYPES["clothes_merchant"]})

        if any(k in loc_lower for k in ["gift", "merchandise", "souvenir", "shrine shop", "merch", "toy shop"]):

            stores.append({"type": "gift_merchant", **MERCHANT_ARCHETYPES["gift_merchant"]})

        if any(k in loc_lower for k in ["hallway", "lockers", "rooftop", "behind the gym", "quiet alley", "courtyard"]):

            stores.append({"type": "student_merchant", **MERCHANT_ARCHETYPES["student_merchant"]})

        if any(k in loc_lower for k in ["club room", "gang", "hideout", "hangout", "clubhouse"]):

            stores.append({"type": "club_merchant", **MERCHANT_ARCHETYPES["club_merchant"]})

        if is_nsfw and any(k in loc_lower for k in ["adult", "novelty", "afterdark", "secret boutique", "lingerie"]):

            stores.append({"type": "adult_store_merchant", **MERCHANT_ARCHETYPES["adult_store_merchant"]})



        # Downtown Mall / Commercial Arcade hub

        if any(k in loc_lower for k in ["downtown", "commercial", "shopping mall", "arcade", "plaza"]):

            hub_stores = [

                {"type": "cafe_merchant", **MERCHANT_ARCHETYPES["cafe_merchant"]},

                {"type": "clothes_merchant", **MERCHANT_ARCHETYPES["clothes_merchant"]},

                {"type": "gift_merchant", **MERCHANT_ARCHETYPES["gift_merchant"]}

            ]

            if is_nsfw:

                hub_stores.append({"type": "adult_store_merchant", **MERCHANT_ARCHETYPES["adult_store_merchant"]})

            return hub_stores



        if stores:

            return stores

        return [{"type": "school_merchant", **MERCHANT_ARCHETYPES["school_merchant"]}]



    # 2. Combat / Fantasy / Sci-Fi / Cyberpunk Scenarios

    # Major Capitals, Grand Bazaars, Promenades, Central Plazas -> Full Bazaar Directory

    bazaar_hub_keywords = [

        "capital", "grand bazaar", "bazaar", "central market", "market district", "promenade",

        "trade quarter", "commercial district", "metropolis", "citadel plaza", "harbor market",

        "starport concourse", "neon arcade"

    ]

    if any(k in loc_lower for k in bazaar_hub_keywords):

        hub_stores = [

            {"type": "weapon_merchant", **MERCHANT_ARCHETYPES["weapon_merchant"]},

            {"type": "armor_merchant", **MERCHANT_ARCHETYPES["armor_merchant"]},

            {"type": "potion_merchant", **MERCHANT_ARCHETYPES["potion_merchant"]},

            {"type": "magic_merchant", **MERCHANT_ARCHETYPES["magic_merchant"]},

            {"type": "spellbook_merchant", **MERCHANT_ARCHETYPES["spellbook_merchant"]},

            {"type": "food_merchant", **MERCHANT_ARCHETYPES["food_merchant"]},

            {"type": "general_merchant", **MERCHANT_ARCHETYPES["general_merchant"]},

        ]

        if is_nsfw:

            hub_stores.append({"type": "adult_store_merchant", **MERCHANT_ARCHETYPES["adult_store_merchant"]})

        return hub_stores



    # Specific dedicated shops

    stores = []

    if any(k in loc_lower for k in ["forge", "smithy", "blacksmith", "weaponsmith", "armory"]):

        stores.append({"type": "weapon_merchant", **MERCHANT_ARCHETYPES["weapon_merchant"]})

        stores.append({"type": "armor_merchant", **MERCHANT_ARCHETYPES["armor_merchant"]})

    if any(k in loc_lower for k in ["apothecary", "alchemist", "herbalist", "potion", "pharmacy"]):

        stores.append({"type": "potion_merchant", **MERCHANT_ARCHETYPES["potion_merchant"]})

    if any(k in loc_lower for k in ["arcane", "magic", "mystic", "enchanter", "sorcery", "grimoire", "scribe", "library"]):

        stores.append({"type": "magic_merchant", **MERCHANT_ARCHETYPES["magic_merchant"]})

        stores.append({"type": "spellbook_merchant", **MERCHANT_ARCHETYPES["spellbook_merchant"]})

    if any(k in loc_lower for k in ["bakery", "tavern", "inn", "saloon", "canteen", "mess hall", "food stall", "diner"]):

        stores.append({"type": "food_merchant", **MERCHANT_ARCHETYPES["food_merchant"]})

    if is_nsfw and any(k in loc_lower for k in ["adult", "brothel", "pleasure", "cyber-den", "erotic", "novelty"]):

        stores.append({"type": "adult_store_merchant", **MERCHANT_ARCHETYPES["adult_store_merchant"]})



    if stores:

        return stores



    # Small towns, roadside camps, and outposts -> General Merchant

    return [{"type": "general_merchant", **MERCHANT_ARCHETYPES["general_merchant"]}]

def location_has_merchant_shop(location_str: str, scen_key: str = None) -> bool:

    """Checks if a location is an actual commercial shop, store, market, café, canteen, or merchant establishment."""

    if not location_str:

        return False



    # Extract Tier 2 Primary place if full string is passed

    target = location_str

    if "➔" in location_str:

        parts = [p.strip() for p in location_str.split("➔") if p.strip()]

        if len(parts) >= 2:

            target = parts[1]

    elif "->" in location_str:

        parts = [p.strip() for p in location_str.split("->") if p.strip()]

        if len(parts) >= 2:

            target = parts[1]



    p_lower = target.lower()



    # School & Modern Academic Scenarios: only legitimate commercial/food spots

    if scen_key and is_school_scenario(scen_key):

        non_shop_school_places = (

            "classroom", "homeroom", "library", "office", "council",

            "lockers", "gym", "gymnasium", "rooftop", "lounge", "staff room",

            "infirmary", "dorm", "desk", "corridor", "foyer", "stairs", "alcove"

        )

        if any(nsp in p_lower for nsp in non_shop_school_places):

            return False



        school_shop_keywords = (

            "cafeteria", "canteen", "café", "cafe", "convenience", "store", "bakery",

            "kiosk", "vending", "co-op", "food court", "shopping", "bakeshop",

            "sweet shop", "restaurant", "diner", "conbini", "stall", "market", "boutique", "gift"

        )

        return any(k in p_lower for k in school_shop_keywords)



    # General Scenarios (Fantasy, Cyberpunk, Sci-Fi, etc.)

    shop_keywords = (

        "shop", "store", "market", "bazaar", "emporium", "café", "cafe", "pharmacy",

        "armory", "blacksmith", "weaponsmith", "quartermaster", "convenience", "boutique",

        "bakery", "stall", "merchant", "trader", "noodle bar", "canteen", "saloon", "tavern",

        "inn", "trading post", "general store", "guild shop", "alchemist", "herbalist", "forge"

    )

    return any(k in p_lower for k in shop_keywords)

def location_has_faction_hq(location_str: str, session_id: int = None) -> bool:

    """Checks if the given location is registered as a Faction HQ."""

    if not location_str:

        return False

    if session_id:

        try:

            faction = db.get_faction_by_hq(session_id, location_str)

            if faction:

                return True

        except Exception:

            pass

    loc_lower = location_str.lower()

    keywords = ["faction hq", "headquarters", "council office", "command center", "guild master"]

    return any(k in loc_lower for k in keywords)

def get_location_emoji(location_name: str, zone_name: str = "", waypoint_markers: dict = None, session_id: int = None, scen_key: str = None, char_name: str = "") -> str:

    """

    Determines the single clean emoji for a location in the travel dropdown:

    1. ⭐ if Story Quest Waypoint

    2. 🎯 if Accepted Active Bounty Waypoint

    3. 🏛️ if Faction HQ

    4. 📋 if Notice Board / Bounty Hub

    5. 🛍️ if Merchant / Shop

    6. 🏠 if Player Residence

    7. 📍 Standard Location

    """

    value_str = f"{zone_name} ➔ {location_name}" if zone_name else location_name



    if waypoint_markers:

        wp_tags = waypoint_markers.get(value_str) or waypoint_markers.get(location_name)

        if wp_tags:

            if any("⚡" in tag for tag in wp_tags):

                return "⚡"

            if any("⭐" in tag for tag in wp_tags):

                return "⭐"

            return "🎯"



    if location_has_faction_hq(location_name, session_id=session_id) or (zone_name and location_has_faction_hq(zone_name, session_id=session_id)):

        return "🏛️"

    if location_has_bounty_board(location_name, scen_key=scen_key):

        return "📋"

    if location_has_merchant_shop(location_name, scen_key=scen_key):

        return "🛍️"



    # Check if player residence

    if session_id or char_name:

        try:

            p_house = get_session_player_house_name(session_id or 0, char_name=char_name, scenario_key=scen_key or "fantasy")

            if location_name == p_house or (p_house and p_house in location_name):

                return "🏠"

        except Exception:

            pass



    return "📍"

def get_notice_board_label(scen_key: str = None) -> tuple[str, str]:

    """Returns (button_label, emoji) for the Notice Board button based on scenario."""

    scen = str(scen_key or "").lower()

    if is_school_scenario(scen):

        return ("Campus Bulletin", "📋")

    if "cyberpunk" in scen or "sci_fi" in scen:

        return ("Job Terminal", "💾")

    if "steampunk" in scen:

        return ("Dispatch Board", "📻")

    if "apocalypse" in scen:

        return ("Radio Dispatch", "📻")

    return ("Notice Board", "📋")


from .seeding import ensure_session_locations_seeded
from .hierarchy import get_clean_zone_short_name, parse_tiered_location
