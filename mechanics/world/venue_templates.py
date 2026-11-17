"""
Static Venue Staff Role Templates, Role Slot-Fill Compatibility Rules, and Crowd Flavor Tables.

Pure data module with zero DB calls, zero RNG, and zero side effects.
All runtime orchestration and persistence live in `mechanics/world/venue_seeder.py`.
"""
from __future__ import annotations

import json
import re
from typing import Any, Mapping


NON_STAFFABLE_EXACT_IDS: frozenset[str] = frozenset({"zone_residential_abstract"})

PRIVATE_RESIDENCE_KEYWORDS: tuple[str, ...] = (
    "your apartment", "player residence", "your home", "your house",
    "your bedroom", "private residence", "family apartment", "parental home",
    "safehouse", "player room", "dorm room", "your quarters", "bedroom",
)

WILDERNESS_DUNGEON_KEYWORDS: tuple[str, ...] = (
    "dungeon", "lair", "cavern", "crypt", "abyss", "wasteland", "dense forest",
    "deep woods", "wilderness", "open road", "mountain pass", "swamp", "marsh",
    "desert trail", "crater", "monster nest", "abandoned ruin", "ruins",
    "trailhead", "highway", "backroad", "forest trail", "empty road",
)

UNSTAFFED_SUBAREA_KEYWORDS: tuple[str, ...] = (
    "alley", "alleyway", "rooftop", "bathroom", "restroom", "locker room",
    "stairwell", "basement", "storage closet", "vacant lot", "park bench",
    "hallway", "corridor", "bedroom", "loft", "dormitory", "dormitories",
    "rest quarters", "sub-cellar", "evidence vault", "quarantine", "containment",
)

HOSPITALITY_OUTPOST_OVERRIDE_KEYWORDS: tuple[str, ...] = (
    "tavern", "inn", "hostel", "hotel", "motel", "ryokan", "lodge",
    "ranger station", "trading post", "outpost", "caravan camp", "roadhouse",
)

STAFFED_VENUE_OVERRIDE_KEYWORDS: tuple[str, ...] = (
    "shop", "store", "market", "bazaar", "plaza", "mall", "kiosk", "vending",
    "cafe", "café", "bakery", "library", "clinic", "hospital", "infirmary",
    "pharmacy", "guild", "guardhouse", "watchpost", "security desk", "tavern",
    "inn", "bar", "pub", "club", "shrine", "temple", "office", "station",
    "blacksmith", "smithy", "forge", "apothecary", "restaurant", "diner",
    "konbini", "convenience", "cafeteria",
    "armory", "ordnance", "requisition", "quartermaster", "outfitter",
    "tailoring", "cleansing bay", "dispensary", "canteen", "espresso",
    "taproom", "boutique",
)

KIOSK_BYPASS_KEYWORDS: tuple[str, ...] = (
    "vending", "automat", "self-checkout", "supply terminal", "kiosk",
)

SEED_24H_KEYWORDS: tuple[str, ...] = (
    "24h", "24-hour", "24 hour", "konbini", "convenience", "vending",
    "automat", "supply terminal", "kiosk", "watchpost", "guardhouse",
    "security desk", "emergency", "er ",
)

SLOT_FILL_24H_KEYWORDS: tuple[str, ...] = SEED_24H_KEYWORDS + (
    "tavern", "inn", "pub", "hostel", "hotel", "nightclub",
)

ROAMER_HUB_KEYWORDS: tuple[str, ...] = (
    "plaza", "bazaar", "market", "crossroads", "outpost", "caravan",
    "town square", "commercial district", "trade", "harbor", "dock", "pier",
    "gate", "junction", "trading post", "central",
)

ROAMER_EXCLUDE_KEYWORDS: tuple[str, ...] = (
    "bedroom", "apartment", "residence", "dorm", "classroom", "bathroom",
    "restroom", "dungeon", "lair", "crypt", "clinic", "hospital", "infirmary",
    "library", "blacksmith", "smithy", "apothecary", "tailor", "general store",
    "potion shop", "magic shop", "weapon shop", "armor shop",
    "hq", "headquarters", "bureau", "precinct", "watchpost", "guardhouse",
    "lobby", "atrium", "vault", "containment", "quarantine", "sub-cellar",
    "school", "academy", "campus",
)

FESTIVAL_EVENT_SUBTYPES: frozenset[str] = frozenset({
    "festival", "market", "bazaar", "night_market", "street_fair", "fair", "carnival",
})

SCHOOL_SCENARIOS: frozenset[str] = frozenset({
    "high_school_drama", "slice_of_life", "anomalous_high_school",
})

CYBER_SCENARIOS: frozenset[str] = frozenset({"cyberpunk", "sci_fi"})


def _staff_spec(
    role: str,
    occupation: str,
    shift_profile: str,
    merchant_archetypes: tuple[str, ...] = (),
    is_unique_proprietor: bool = False,
    is_24h_station: bool = False,
) -> dict[str, Any]:
    return {
        "role": role,
        "occupation": occupation,
        "shift_profile": shift_profile,
        "merchant_archetypes": tuple(merchant_archetypes),
        "is_unique_proprietor": bool(is_unique_proprietor),
        "is_24h_station": bool(is_24h_station),
    }


VENUE_ROLE_TEMPLATES: dict[str, tuple[dict[str, Any], ...]] = {
    "bazaar_hub": (
        _staff_spec("Arms & Gear Vendor", "Merchant", "day", ("weapon_merchant", "armor_merchant")),
        _staff_spec("Apothecary Vendor", "Apothecary", "day", ("potion_merchant", "magic_merchant")),
        _staff_spec("Provisions Trader", "Trader", "evening", ("general_merchant", "food_merchant")),
        _staff_spec("Lantern Stall Keeper", "Night Vendor", "night", ("night_market_merchant", "accessories_merchant", "gift_merchant")),
    ),
    "bazaar_hub_school": (
        _staff_spec("Boutique Clerk", "Clerk", "day", ("clothes_merchant", "brand_clothes_merchant")),
        _staff_spec("Snack & Café Vendor", "Barista", "day", ("cafe_merchant", "food_merchant")),
        _staff_spec("Stationery & Gift Clerk", "Clerk", "evening", ("school_merchant", "gift_merchant")),
        _staff_spec("Evening Stall Vendor", "Vendor", "night", ("night_market_merchant", "accessories_merchant")),
    ),
    "smithy_armory": (
        _staff_spec("Blacksmith", "Blacksmith", "day", ("weapon_merchant", "armor_merchant")),
        _staff_spec("Apprentice Armorer", "Armorer", "evening", ("armor_merchant", "weapon_merchant")),
    ),
    "apothecary_alchemy": (
        _staff_spec("Apothecary", "Apothecary", "day", ("potion_merchant", "magic_merchant")),
    ),
    "magic_arcane": (
        _staff_spec("Arcane Merchant", "Enchanter", "day", ("magic_merchant", "spellbook_merchant")),
    ),
    "shrine_temple": (
        _staff_spec("Shrine Keeper", "Priest", "day", ("kitsune_spirit_merchant", "potion_merchant")),
        _staff_spec("Shrine Acolyte", "Acolyte", "evening", ("gift_merchant", "potion_merchant")),
    ),
    "clinic_hospital": (
        _staff_spec("Attending Healer", "Physician", "day", ("potion_merchant",)),
        _staff_spec("Clinic Nurse", "Nurse", "evening", ("potion_merchant",)),
        _staff_spec("Night Medic", "Medic", "night", ()),
    ),
    "library_archive": (
        _staff_spec("Head Archivist", "Archivist", "day", ()),
        _staff_spec("Evening Librarian", "Librarian", "evening", ()),
    ),
    "guild_civic": (
        _staff_spec("Guildmaster", "Guildmaster", "day", ("weapon_merchant", "general_merchant")),
        _staff_spec("Receptionist", "Receptionist", "day", ()),
        _staff_spec("Quartermaster", "Quartermaster", "evening", ("armor_merchant", "general_merchant")),
    ),
    "civic_hq": (
        _staff_spec("Operations Supervisor", "Duty Officer", "day", ()),
        _staff_spec("Front Desk Receptionist", "Receptionist", "day", ()),
        _staff_spec("Evening Duty Officer", "Duty Officer", "evening", ()),
    ),
    "tactical_outfitter": (
        _staff_spec("Field Outfitter", "Quartermaster", "day", ("armor_merchant", "clothes_merchant")),
        _staff_spec("Evening Outfitter", "Quartermaster", "evening", ("armor_merchant", "clothes_merchant")),
    ),
    "tavern_inn": (
        _staff_spec("Innkeeper", "Innkeeper", "day", ("food_merchant", "general_merchant")),
        _staff_spec("Bartender", "Bartender", "evening", ("food_merchant", "nightclub_merchant")),
        _staff_spec("Night Steward", "Server", "night", ("food_merchant", "nightclub_merchant")),
    ),
    "cafe_restaurant": (
        _staff_spec("Barista", "Barista", "day", ("cafe_merchant", "food_merchant", "restaurant_merchant")),
        _staff_spec("Evening Server", "Server", "evening", ("cafe_merchant", "restaurant_merchant")),
    ),
    "convenience_konbini": (
        _staff_spec("Day Cashier", "Cashier", "day", ("convenience_merchant", "food_merchant"), is_24h_station=True),
        _staff_spec("Night Clerk", "Clerk", "night", ("convenience_merchant", "food_merchant"), is_24h_station=True),
    ),
    "clothing_boutique": (
        _staff_spec("Head Clothier", "Tailor", "day", ("clothes_merchant", "brand_clothes_merchant", "accessories_merchant", "gift_merchant")),
        _staff_spec("Evening Stylist", "Stylist", "evening", ("clothes_merchant", "accessories_merchant", "gift_merchant")),
    ),
    "school_campus": (
        _staff_spec("Campus Store Clerk", "Clerk", "student", ("school_merchant", "student_merchant", "food_merchant")),
        _staff_spec("After-School Clerk", "Clerk", "evening", ("school_merchant", "cafe_merchant")),
    ),
    "ranger_outpost": (
        _staff_spec("Outpost Quartermaster", "Quartermaster", "day", ("ranger_station_outfitter", "general_merchant", "food_merchant")),
        _staff_spec("Evening Outfitter", "Quartermaster", "evening", ("ranger_station_outfitter", "general_merchant")),
    ),
    "general_shop": (
        _staff_spec("Shopkeeper", "Shopkeeper", "day", ("general_merchant", "food_merchant", "potion_merchant")),
    ),
}


ROLE_SLOT_FILL_SPECS: dict[str, dict[str, Any]] = {
    "apothecary": {
        "aliases": ("apothecary", "alchemist", "herbalist", "potion maker"),
        "role": "Apothecary", "occupation": "Apothecary",
        "merchant_archetypes": ("potion_merchant", "magic_merchant"),
        "default_shift": "day", "allow_24h_station": False,
        "allowed_keywords": ("apothecary", "alchemist", "potion", "herb", "clinic", "hospital", "pharmacy", "market", "bazaar", "plaza", "shop", "store", "shrine", "temple"),
        "forbidden_keywords": ("classroom", "bedroom", "residence", "apartment", "dorm", "dungeon", "forest", "wilderness", "open road", "blacksmith", "nightclub"),
        "forbidden_scenarios": frozenset({"high_school_drama"}),
    },
    "archivist": {
        "aliases": ("archivist", "librarian", "bookkeeper", "curator"),
        "role": "Archivist", "occupation": "Archivist",
        "merchant_archetypes": (),
        "default_shift": "day", "allow_24h_station": False,
        "allowed_keywords": ("library", "archive", "academy", "school", "university", "guild", "temple", "shrine", "museum", "bookstore", "bookshop", "office"),
        "forbidden_keywords": ("tavern", "nightclub", "bar", "pub", "blacksmith", "forest", "wilderness", "open road", "bedroom", "apartment", "residence", "dungeon"),
        "forbidden_scenarios": frozenset(),
    },
    "bartender": {
        "aliases": ("bartender", "barkeep", "barman", "barmaid", "mixologist"),
        "role": "Bartender", "occupation": "Bartender",
        "merchant_archetypes": ("food_merchant", "nightclub_merchant"),
        "default_shift": "evening", "allow_24h_station": True,
        "allowed_keywords": ("tavern", "inn", "pub", "bar", "nightclub", "club", "lounge", "alehouse", "roadhouse"),
        "forbidden_keywords": ("library", "classroom", "clinic", "hospital", "infirmary", "shrine", "temple", "blacksmith", "bedroom", "residence", "apartment", "forest", "dungeon", "open road"),
        "forbidden_scenarios": frozenset(),
    },
    "blacksmith": {
        "aliases": ("blacksmith", "smith", "armorer", "weaponsmith", "forgemaster", "gunsmith"),
        "role": "Blacksmith", "occupation": "Blacksmith",
        "merchant_archetypes": ("weapon_merchant", "armor_merchant"),
        "default_shift": "day", "allow_24h_station": False,
        "allowed_keywords": ("blacksmith", "smithy", "forge", "armory", "weapon", "guild", "market", "bazaar", "plaza", "outpost", "workshop", "gunsmith"),
        "forbidden_keywords": ("classroom", "school", "academy", "library", "clinic", "hospital", "tavern", "cafe", "bakery", "bedroom", "residence", "apartment", "dorm", "forest", "dungeon", "open road", "bunker"),
        "forbidden_scenarios": frozenset({"high_school_drama", "slice_of_life"}),
    },
    "nurse": {
        "aliases": ("nurse", "healer", "doctor", "medic", "physician", "pharmacist"),
        "role": "Clinic Nurse", "occupation": "Medic",
        "merchant_archetypes": ("potion_merchant",),
        "default_shift": "day", "allow_24h_station": True,
        "allowed_keywords": ("clinic", "hospital", "infirmary", "nurse", "medbay", "medical", "pharmacy", "apothecary", "shrine", "temple", "sanctuary", "outpost"),
        "forbidden_keywords": ("classroom", "blacksmith", "smithy", "tavern", "nightclub", "bar", "bedroom", "residence", "apartment", "dungeon", "open road", "forest"),
        "forbidden_scenarios": frozenset(),
    },
    "waitress": {
        "aliases": ("waitress", "waiter", "server", "barista", "chef", "cook"),
        "role": "Server", "occupation": "Server",
        "merchant_archetypes": ("cafe_merchant", "food_merchant", "restaurant_merchant"),
        "default_shift": "day", "allow_24h_station": True,
        "allowed_keywords": ("cafe", "café", "coffee", "bakery", "bistro", "diner", "restaurant", "ramen", "tea house", "tavern", "inn", "pub", "bar", "club", "cafeteria", "canteen"),
        "forbidden_keywords": ("classroom", "blacksmith", "smithy", "library", "clinic", "hospital", "bedroom", "residence", "apartment", "dungeon", "forest", "open road"),
        "forbidden_scenarios": frozenset(),
    },
    "receptionist": {
        "aliases": ("receptionist", "concierge", "attendant", "front desk"),
        "role": "Receptionist", "occupation": "Receptionist",
        "merchant_archetypes": (),
        "default_shift": "day", "allow_24h_station": True,
        "allowed_keywords": ("guild", "clinic", "hospital", "hotel", "inn", "hostel", "office", "library", "academy", "school", "salon", "station", "precinct", "bureau", "hall", "lobby"),
        "forbidden_keywords": ("classroom", "bedroom", "residence", "apartment", "dungeon", "forest", "open road", "wilderness", "bunker"),
        "forbidden_scenarios": frozenset(),
    },
    "guard": {
        "aliases": ("guard", "watchman", "security", "bouncer", "warden", "sentinel"),
        "role": "Security Guard", "occupation": "Guard",
        "merchant_archetypes": (),
        "default_shift": "day", "allow_24h_station": True,
        "allowed_keywords": ("watchpost", "guardhouse", "security desk", "gate", "guild", "bank", "nightclub", "tavern", "inn", "precinct", "station", "plaza", "bazaar", "market", "outpost", "campus gate", "facility"),
        "forbidden_keywords": ("apartment", "your home", "your house", "bedroom", "residence", "dorm", "classroom", "bathroom", "wilderness", "forest trail", "open road"),
        "forbidden_scenarios": frozenset(),
    },
    "cashier": {
        "aliases": ("cashier", "clerk", "shopkeeper", "merchant", "vendor", "teller"),
        "role": "Shop Clerk", "occupation": "Clerk",
        "merchant_archetypes": ("general_merchant", "food_merchant"),
        "default_shift": "day", "allow_24h_station": True,
        "allowed_keywords": ("shop", "store", "market", "bazaar", "plaza", "mall", "konbini", "convenience", "cafe", "café", "bakery", "bookstore", "pharmacy", "campus store", "school store", "cafeteria", "stall", "boutique", "bank"),
        "forbidden_keywords": ("classroom", "bedroom", "residence", "apartment", "dorm", "dungeon", "forest", "wilderness", "open road"),
        "forbidden_scenarios": frozenset(),
    },
}


CROWD_FLAVOR_TEMPLATES: dict[str, dict[str, dict[str, str]]] = {
    "fantasy": {
        "market": {
            "morning": "Merchants unlatch wooden shutters and sweep cobblestones while bakers carry warm loaves past canvas awnings.",
            "lunch": "Pack-mules, hawkers, and townsfolk crowd between spiced braziers and cloth-draped stalls under midday banners.",
            "afternoon": "Bartering voices rise over clinking scales as couriers weave past linen canopies and stacked crates.",
            "evening": "Oil lanterns flicker along stall beams while shopkeepers tally copper coin and fold away bright silks.",
            "night": "Stray lanternlight washes over shuttered booths and quiet flagstones as the last watch boots echo past.",
        },
        "tavern": {
            "morning": "Chairs rest stacked on scrubbed oak tables while hearth embers crackle beneath an iron kettle.",
            "lunch": "Porters and craftsmen trade quiet gossip over bowls of barley stew and tankards of cider.",
            "afternoon": "Warm spice and roasted malt drift through slatted shutters as quiet dice clatter in a corner booth.",
            "evening": "Lute strings, laughter, and amber hearthlight fill the timbered hall as tankards clink along the rail.",
            "night": "Low murmurs linger beneath heavy ceiling beams as candle stubs gutter beside the hearth.",
        },
        "default": {
            "morning": "A crisp morning draft stirs banner hems and polished brass along freshly swept stone thresholds.",
            "lunch": "Townsfolk and errands-runners move steadily along the corridor under high daylight.",
            "afternoon": "Unrushed afternoon footsteps echo lightly beside sunlit archways and neatly stacked wares.",
            "evening": "Warm sconces cast amber pools across carved woodwork as evening foot traffic thins out.",
            "night": "Deep midnight stillness settles over latched doors, shuttered panes, and cool stone.",
        },
    },
    "cyberpunk": {
        "market": {
            "morning": "Damp concrete steams beneath holo-tarps as street vendors boot up portable price displays.",
            "lunch": "Synth-noodle smoke, courier drones, and dense foot traffic surge beneath flickering neon kanji.",
            "afternoon": "Static crackles over chrome kiosks while commuters shoulder past modular stall racks.",
            "evening": "Rain-slick asphalt mirrors magenta signage as crowded night-stalls hum over pulsing sub-bass.",
            "night": "Buzzing vending glass and stray diagnostic LEDs glow along near-empty neon walkways.",
        },
        "tavern": {
            "morning": "Ozone and bitter synth-caffeine linger under dimmed strip-lights while bots scrub chrome rails.",
            "lunch": "Fixers in damp jackets nurse espresso beneath muted holographic tickers.",
            "afternoon": "Low synthwave hums softly through frosted glass booths while terminals blink in standby.",
            "evening": "Amber fiber-optics gleam off brushed steel as regulars trade whispers over iced cocktails.",
            "night": "Neon spill cuts across black tabletops while a stray ceiling fan turns slowly overhead.",
        },
        "default": {
            "morning": "Cool recycled air vents softly over brushed aluminum while early commuters scan past.",
            "lunch": "Brisk footsteps and soft scanner chimes punctuate the midday bustle under bright panels.",
            "afternoon": "Muted street traffic vibrates through reinforced glass while indoor screens cycle calmly.",
            "evening": "City signage paints tinted streaks across tiled corridors as after-hours traffic rolls in.",
            "night": "Dim security strips hum over quiet chrome shutters and empty transit bays.",
        },
    },
    "high_school_drama": {
        "market": {
            "morning": "Early commuters check bus times past freshly stocked windows and stacked morning papers.",
            "lunch": "Students and neighborhood regulars queue cheerfully beside sunlit shopfronts and clinking coolers.",
            "afternoon": "After-school chatter fills crosswalks as club bags brush past bright storefront banners.",
            "evening": "Warm streetlamps glow above half-full bike racks and steaming convenience-store counters.",
            "night": "Cicadas fade into quiet suburban darkness beneath solitary porch lamps and shuttered awnings.",
        },
        "tavern": {
            "morning": "Freshly wiped booths gleam in slant morning sun beside the hum of espresso grinders.",
            "lunch": "Trays clatter lightly while classmates crowd corner tables over shared fries and iced tea.",
            "afternoon": "Quiet acoustic music drifts above study notebooks and condensation-beaded glasses.",
            "evening": "Warm pendant lamps light relaxed dinner chatter as coats drape over booth backs.",
            "night": "Chairs sit tucked neatly along clean linoleum beneath softly humming cooler doors.",
        },
        "default": {
            "morning": "Freshly polished hallway floors catch crisp morning light as lockers click open down the wing.",
            "lunch": "Breezy chatter and hurried footsteps echo past bulletin boards during the midday break.",
            "afternoon": "Slanted golden sun stretches across desks while club echoes carry faintly from the courtyard.",
            "evening": "Long twilight shadows soften the brickwork as the last lingering steps fade toward the gate.",
            "night": "Cool moonlight strips across locked windows and silent corridors long after last bell.",
        },
    },
    "nuclear_post_apocalypse": {
        "market": {
            "morning": "Tarp seams snap in dusty wind as scavengers lay brass, filters, and ration tins across crates.",
            "lunch": "Canteen guards watch bartering knots under corrugated tin roofs while water drums clang steadily.",
            "afternoon": "Grit swirls around canvas sandbags as mechanics test refurbished battery packs beside scrap.",
            "evening": "Barrel fires crackle beneath salvaged string-bulbs while traders tally bottle-caps and bolt locks.",
            "night": "Diesel generators mutter behind bolted sheet-metal shutters under a cold, dust-veiled sky.",
        },
        "tavern": {
            "morning": "Cold grease and woodsmoke hang above scarred plywood tables while tin mugs dry upside down.",
            "lunch": "Caravan scouts spoon thick grain mush in wary silence near the warmth of a patched drum-stove.",
            "afternoon": "Dry air settles through tarped windows while salvaged radio static crackles softly in the corner.",
            "evening": "Amber kerosene lanterns catch weathered faces and clinking tin cups around the rusted bar.",
            "night": "Embers glow red behind iron grates while heavy timber bars seal the outer door.",
        },
        "default": {
            "morning": "Thin grey daylight filters past welded grates while wind scrapes dry grit across cracked tile.",
            "lunch": "Bootsteps crunch cautiously across concrete dust beside chalk-marked supply lockers.",
            "afternoon": "Patchwork tarps ripple slowly over silent steel beams in the dry afternoon haze.",
            "evening": "Low orange sun bleeds through dust clouds as watchfires spark behind sandbags.",
            "night": "Stark quiet grips bolted bulkheads, broken only by distant wind against sheet iron.",
        },
    },
    "urban_anomalies": {
        "market": {
            "morning": "Dewy mist clings to brick awnings while delivery vans idle softly beside misted corner windows.",
            "lunch": "Umbrellas and coats weave along damp sidewalks while faint static prickles near brass lampposts.",
            "afternoon": "Cloud-filtered light glints off grates as shoppers hurry past strangely silent alley mouths.",
            "evening": "Sodium streetlights halo damp pavement while shop bells chime faintly at phantom drafts.",
            "night": "Fog curls thick around shuttered glass and humming tram wires under unnaturally still eaves.",
        },
        "tavern": {
            "morning": "Dark mahogany booths gleam beneath overcast skylight glass and the quiet hiss of a kettle.",
            "lunch": "Low voices linger over thick ceramic mugs while rain beads quietly on leaded windowpanes.",
            "afternoon": "Brass sconces burn warm against shadowed brick as newspapers rustle in corner booths.",
            "evening": "Clinking glassware and murmured rumors warm the smoky air behind velvet-curtained glass.",
            "night": "Candlelight trembles near frost-edged panes while distant sirens fade down the avenue.",
        },
        "default": {
            "morning": "Pale mist drifts across wet stone steps while sparrows scatter from quiet eaves.",
            "lunch": "Brisk city footsteps pass outside muffled masonry walls under flat silver daylight.",
            "afternoon": "Faint drafts stir bulletin notices along muted corridors lined with dark oak trim.",
            "evening": "Long sodium shadows stretch past wet railings as commuter crowds thin out toward dusk.",
            "night": "Eerie stillness settles across darkened windows while lone streetlights flicker outside.",
        },
    },
}

_SCENARIO_FLAVOR_ALIASES: dict[str, str] = {
    "fantasy": "fantasy", "isekai_fantasy": "fantasy", "dark_fantasy": "fantasy",
    "steampunk": "cyberpunk", "cyberpunk": "cyberpunk", "sci_fi": "cyberpunk",
    "high_school_drama": "high_school_drama", "slice_of_life": "high_school_drama",
    "anomalous_high_school": "high_school_drama",
    "nuclear_post_apocalypse": "nuclear_post_apocalypse",
    "urban_anomalies": "urban_anomalies", "anomalous_incursions": "urban_anomalies",
}


def parse_node_state(node: dict[str, Any] | None) -> dict[str, Any]:
    """Decode `node['state_json']` (str or dict) cleanly into a dict."""
    if not isinstance(node, dict):
        return {}
    raw = node.get("state_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except (ValueError, TypeError):
            pass
    alt = node.get("state")
    return alt if isinstance(alt, dict) else {}


def _check_node_kw_flag(location_name: str, node: dict[str, Any] | None, state_keys: tuple[str, ...], keywords: tuple[str, ...]) -> bool:
    state_json = parse_node_state(node)
    if any(bool(state_json.get(k)) for k in state_keys):
        return True
    node_name = str((node or {}).get("name") or "").strip().lower()
    combined = f"{node_name} {str(location_name or '').strip().lower()}"
    return any(kw in combined for kw in keywords)


def is_kiosk_location(location_name: str, node: dict[str, Any] | None = None) -> bool:
    """Return True if the node or location string describes an automated kiosk/vending unit."""
    return _check_node_kw_flag(location_name, node, ("is_kiosk", "automated_kiosk"), KIOSK_BYPASS_KEYWORDS)


def is_24h_venue_for_seeding(location_name: str, node: dict[str, Any] | None = None) -> bool:
    """Return True if a facility should mark seeded venue staff with `is_24h_station=True`."""
    return _check_node_kw_flag(location_name, node, ("is_24h_station",), SEED_24H_KEYWORDS)


def is_24h_venue_for_slot_fill(location_name: str, node: dict[str, Any] | None = None) -> bool:
    """Return True if custom role slot-fill allows off-hours presence (tavern/inn/24h clinic/konbini/security desk)."""
    return _check_node_kw_flag(location_name, node, ("is_24h_station",), SLOT_FILL_24H_KEYWORDS)


def is_node_staffable(node: dict[str, Any] | None, scen_key: str = "fantasy") -> bool:
    """Determine whether a world_nodes row represents a staffable venue rather than wilderness or private housing."""
    _ = scen_key
    if not isinstance(node, dict):
        return False
    node_id = str(node.get("node_id") or "").strip().lower()
    name = str(node.get("name") or "").strip().lower()
    category = str(node.get("category") or "").strip().lower()
    node_type = str(node.get("node_type") or "").strip().upper()
    state_json = parse_node_state(node)

    if not node_id or node_id in NON_STAFFABLE_EXACT_IDS:
        return False
    if bool(state_json.get("is_player_residence") or state_json.get("unstaffed")):
        return False
    if any(kw in name for kw in PRIVATE_RESIDENCE_KEYWORDS):
        return False

    # Never seed mundane shopkeepers/staff inside quarantined anomalous sites, Hostile HQs,
    # or cordoned Theme Park epicenter rides (protecting AHS minor club dens).
    from mechanics.world.anomalous_sites.catalog import (
        AHS_PROTECTED_SUB_IDS,
        SAFE_EXCLUSION_SITE_IDS,
        THEME_PARK_EPICENTER_IDS,
        resolve_anomalous_site,
    )
    parent_id = str(node.get("parent_id") or "").strip().lower()
    if not state_json.get("is_minor_club_hq"):
        if (
            node_id in AHS_PROTECTED_SUB_IDS
            or parent_id == "loc_abandoned_school_wing"
            or any(
                tok in name
                for tok in ("boarded old infirmary", "old infirmary", "derelict old gymnasium", "overgrown hallway")
            )
        ):
            return False
        if node_id not in SAFE_EXCLUSION_SITE_IDS:
            if node_id in THEME_PARK_EPICENTER_IDS:
                return False
            if bool(state_json.get("is_anomalous")):
                return False
            spec = resolve_anomalous_site(node_id=node_id, parent_id=parent_id, location_str=name, curr_node=node)
            if spec is not None and spec.get("site_type") != "theme_park_night":
                return False

    has_hospitality = any(kw in name for kw in HOSPITALITY_OUTPOST_OVERRIDE_KEYWORDS)
    has_staffed_kw = any(kw in name for kw in STAFFED_VENUE_OVERRIDE_KEYWORDS)

    if any(kw in name for kw in WILDERNESS_DUNGEON_KEYWORDS) and not (has_hospitality or has_staffed_kw):
        return False
    if category in ("wilderness", "residential") and not (has_hospitality or has_staffed_kw):
        return False
    if any(kw in name for kw in UNSTAFFED_SUBAREA_KEYWORDS) and not has_staffed_kw:
        return False
    if node_type == "ZONE" and not (has_staffed_kw or category == "commercial"):
        return False
    return category in ("commercial", "civic", "academic") or has_hospitality or has_staffed_kw or node_type == "FACILITY"


def _adapt_archetypes_for_scenario(archetypes: tuple[str, ...], scen_key: str, venue_name: str) -> tuple[str, ...]:
    if not archetypes:
        return ()
    sk = str(scen_key or "fantasy").strip().lower()
    v_low = str(venue_name or "").strip().lower()
    if sk in ("high_school_drama", "slice_of_life"):
        mapped: list[str] = []
        for arch in archetypes:
            if arch in ("weapon_merchant", "armor_merchant"):
                mapped.append("clothes_merchant" if any(k in v_low for k in ("mall", "plaza", "district", "boutique")) else "school_merchant")
            elif arch in ("potion_merchant", "magic_merchant", "spellbook_merchant"):
                mapped.append("cafe_merchant" if "cafe" in v_low or "cafeteria" in v_low else "school_merchant")
            else:
                mapped.append(arch)
        return tuple(dict.fromkeys(mapped))
    if sk in CYBER_SCENARIOS and "kitsune_spirit_merchant" in archetypes:
        return ("magic_merchant", "general_merchant")
    return archetypes


def select_venue_template(
    location_name: str,
    category: str = "",
    scen_key: str = "fantasy",
    node: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Select matching static role template list for a venue and adapt archetypes/24h flags."""
    low = str(location_name or "").strip().lower()
    cat = str(category or "").strip().lower()
    sk = str(scen_key or "fantasy").strip().lower()
    force_24h = is_24h_venue_for_seeding(location_name, node=node)

    template_key = "general_shop"
    if any(k in low for k in ("bazaar", "grand market", "central market", "market plaza", "shopping mall", "commercial district", "town square", "trade hub", "marketplace", "plaza", "mall")):
        template_key = "bazaar_hub_school" if sk in ("high_school_drama", "slice_of_life") else "bazaar_hub"
    elif any(k in low for k in ("konbini", "convenience", "mini-mart", "minimart")):
        template_key = "convenience_konbini"
    elif any(k in low for k in ("ranger station", "trading post", "outpost", "caravan camp")):
        template_key = "ranger_outpost"
    elif any(k in low for k in ("blacksmith", "smithy", "forge", "armory", "ordnance", "gunsmith", "weaponsmith", "weapon shop", "cyberware")):
        template_key = "smithy_armory"
    elif any(k in low for k in ("outfitter", "tactical rigging", "fitted armor")):
        template_key = "tactical_outfitter"
    elif any(k in low for k in ("apothecary", "alchemist", "potion shop", "herb shop", "alchemy")):
        template_key = "apothecary_alchemy"
    elif any(k in low for k in ("magic shop", "arcane", "enchant", "spellbook", "curio shop", "relic shop", "occult shop")):
        template_key = "magic_arcane"
    elif any(k in low for k in ("shrine", "temple", "sanctuary", "chapel", "cathedral")):
        template_key = "shrine_temple"
    elif (
        any(k in low for k in ("clinic", "hospital", "infirmary", "pharmacy", "medbay", "nurse", "cleansing bay", "psychic detox", "neural recovery", "dispensary", "medical"))
        and not any(d in low for d in ("boarded", "old infirmary", "derelict", "abandoned"))
    ):
        template_key = "clinic_hospital"
    elif any(k in low for k in ("library", "archive", "bookshop", "bookstore", "scriptorium")):
        template_key = "library_archive"
    elif any(k in low for k in ("cafe", "café", "coffee", "bakery", "bistro", "diner", "restaurant", "ramen", "tea house", "cafeteria", "canteen", "espresso", "pour-over", "roastery", "kitchenette")):
        template_key = "cafe_restaurant"
    elif any(k in low for k in ("tavern", "inn", "pub", "alehouse", "nightclub", "lounge", "roadhouse", "taproom")) or " bar" in f" {low}":
        template_key = "tavern_inn"
    elif any(k in low for k in ("tailor", "clothing", "clothes", "boutique", "fashion", "apparel", "accessories", "gift shop")):
        template_key = "clothing_boutique"
    elif any(k in low for k in ("campus store", "school store", "student shop", "co-op", "academy", "school", "campus")) or cat == "academic":
        template_key = "school_campus"
    elif any(k in low for k in ("watchpost", "guardhouse", "precinct", "town hall", "council", "bureau", "headquarters")) or bool(re.search(r"\bhq\b", low)):
        template_key = "civic_hq"
    elif "guild" in low:
        import scenario_data as _sc_data
        template_key = "civic_hq" if _sc_data.is_anomalous_incursions_scenario(sk) else "guild_civic"
    elif "market" in low or "arcade" in low:
        template_key = "bazaar_hub_school" if sk in ("high_school_drama", "slice_of_life") else "bazaar_hub"

    raw_specs = VENUE_ROLE_TEMPLATES.get(template_key, VENUE_ROLE_TEMPLATES["general_shop"])
    resolved: list[dict[str, Any]] = []
    for spec in raw_specs:
        entry = dict(spec)
        if template_key == "library_archive" and any(k in low for k in ("bookshop", "bookstore")):
            entry["merchant_archetypes"] = ("spellbook_merchant", "gift_merchant")
        entry["merchant_archetypes"] = _adapt_archetypes_for_scenario(tuple(entry.get("merchant_archetypes") or ()), sk, low)
        if sk in SCHOOL_SCENARIOS and template_key == "clinic_hospital" and entry["shift_profile"] == "day":
            entry["role"] = "School Nurse"
            entry["occupation"] = "Nurse"
            entry["shift_profile"] = "student"
            entry["merchant_archetypes"] = ("school_merchant",) if sk == "high_school_drama" else ("potion_merchant",)
        if force_24h:
            entry["is_24h_station"] = True
        resolved.append(entry)
    return template_key, resolved


MULTI_WING_HUB_NODE_IDS: frozenset[str] = frozenset({
    "loc_agency_hq", "loc_private_hq_1", "loc_private_hq_2",
    "loc_general_hospital", "loc_theme_park", "loc_eastern_temple",
    "loc_botanical_zoo", "loc_cult_sanctum_hq", "loc_clandestine_syndicate_hq",
    "fac_agency_residence", "fac_temple_residence",
    "loc_hidden_kitsune_village", "loc_hidden_bunian_village",
})


def is_civic_or_multi_wing_hub_node(
    node: Mapping[str, Any] | None,
    scen_key: str = "fantasy",
) -> bool:
    """Return True if a world node is a multi-wing complex or civic HQ whose rooms must never inherit parent shop counters."""
    if not isinstance(node, Mapping):
        return False
    nid = str(node.get("node_id") or "").strip().lower()
    if nid in MULTI_WING_HUB_NODE_IDS or nid.startswith("bld_school_"):
        return True
    ntype = str(node.get("node_type") or "").strip().upper()
    if ntype != "FACILITY":
        return False
    name = str(node.get("name") or "").strip()
    cat = str(node.get("category") or "").strip()
    tpl_key, _ = select_venue_template(name, category=cat, scen_key=scen_key, node=dict(node))
    return tpl_key == "civic_hq"


def resolve_slot_fill_role_spec(
    requested_role: str,
    location_name: str,
    category: str = "",
    scen_key: str = "fantasy",
    node: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Validate role plausibility against venue name/category/scenario and return role spec or None."""
    req_low = str(requested_role or "").strip().lower()
    loc_low = str(location_name or "").strip().lower()
    cat_low = str(category or "").strip().lower()
    sk = str(scen_key or "fantasy").strip().lower()
    if not req_low or not loc_low:
        return None

    matched_key = ""
    matched_spec: dict[str, Any] | None = None
    for role_key, spec in ROLE_SLOT_FILL_SPECS.items():
        if req_low == role_key or any(alias in req_low or req_low in alias for alias in spec["aliases"]):
            matched_key = role_key
            matched_spec = spec
            break
    if matched_spec is None or sk in matched_spec.get("forbidden_scenarios", frozenset()):
        return None

    if any(bad in loc_low for bad in matched_spec.get("forbidden_keywords", ())):
        if not (matched_key == "nurse" and any(ok in loc_low for ok in ("clinic", "infirmary", "nurse", "hospital"))):
            return None
    if any(bad in loc_low for bad in PRIVATE_RESIDENCE_KEYWORDS):
        return None
    if cat_low == "wilderness" and not any(k in loc_low for k in ("outpost", "ranger station", "tavern", "inn")):
        return None
    if cat_low == "residential" and not any(k in loc_low for k in ("inn", "tavern", "hotel", "hostel", "motel")):
        return None
    if not any(ok in loc_low for ok in matched_spec.get("allowed_keywords", ())):
        if not (cat_low == "commercial" and matched_key == "cashier"):
            return None

    is_24h = bool(matched_spec.get("allow_24h_station")) and is_24h_venue_for_slot_fill(location_name, node=node)
    shift_profile = str(matched_spec.get("default_shift") or "day")
    if sk in SCHOOL_SCENARIOS and shift_profile == "day" and any(k in loc_low for k in ("school", "academy", "campus", "infirmary", "library", "cafeteria")):
        shift_profile = "student"

    return {
        "role_key": matched_key,
        "role": matched_spec["role"],
        "occupation": matched_spec["occupation"],
        "merchant_archetypes": _adapt_archetypes_for_scenario(tuple(matched_spec.get("merchant_archetypes") or ()), sk, loc_low),
        "shift_profile": shift_profile,
        "is_24h_station": is_24h,
    }


def get_crowd_flavor_text(location_str: str, scen_key: str, block_key: str, category: str = "") -> str:
    """Return concise unnamed atmospheric background prose with zero stats, DCs, or JSON tags."""
    from mechanics.world.anomalous_sites.catalog import (
        get_site_crowd_stillness_text,
        resolve_anomalous_site,
    )
    import scenario_data as _sc_data

    eff_scen_raw = str(scen_key or "fantasy").strip().lower()
    sc_norm = _SCENARIO_FLAVOR_ALIASES.get(eff_scen_raw, "fantasy")
    low = str(location_str or "").strip().lower()
    cat = str(category or "").strip().lower()

    if _sc_data.is_anomalous_incursions_scenario(eff_scen_raw):
        spec = resolve_anomalous_site(location_str=location_str)
        if spec:
            if spec.get("site_type") == "theme_park_night":
                if block_key == "night" or any(t in low for t in ("hall of mirrors", "mirror labyrinth", "reversed calliope", "midnight carousel")):
                    still = str(spec.get("crowd_stillness_prose") or "").strip()
                    if still:
                        return still
            else:
                probe_min = 1380 if block_key == "night" else 720
                still = get_site_crowd_stillness_text(location_str=location_str, scen_key=eff_scen_raw, current_minute=probe_min)
                if still:
                    return still

    bucket = "default"
    if any(k in low for k in ("market", "bazaar", "plaza", "mall", "shop", "store", "konbini", "alley", "street", "district")) or cat == "commercial":
        bucket = "market"
    elif any(k in low for k in ("tavern", "inn", "pub", "cafe", "café", "bar", "club", "diner", "restaurant", "cafeteria")):
        bucket = "tavern"

    scen_map = CROWD_FLAVOR_TEMPLATES.get(sc_norm, CROWD_FLAVOR_TEMPLATES["fantasy"])
    bucket_map = scen_map.get(bucket, scen_map["default"])
    valid_block = block_key if block_key in ("morning", "lunch", "afternoon", "evening", "night") else "afternoon"
    return bucket_map.get(valid_block, bucket_map["afternoon"])
