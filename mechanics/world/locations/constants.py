"""Static spatial keyword catalogs, zone/archetype rules, and compiled shop/gate patterns."""
from __future__ import annotations

from pathlib import Path
import re

LOCATION_SCENARIOS = {
    "furry_high_school_drama",
    "nsfw_high_school_drama",
    "nsfw_furry_high_school_drama",
    "high_school_drama",
}
TAG_TO_LOCATION_SEED_KEY = {
    "space": "sci_fi",
    "sci_fi": "sci_fi",
    "dark_fantasy": "dark_fantasy",
    "isekai": "isekai_fantasy",
    "isekai_fantasy": "isekai_fantasy",
    "high_school": "high_school_drama",
    "high_school_drama": "high_school_drama",
    "slice_of_life": "slice_of_life",
    "post_apocalypse": "nuclear_post_apocalypse",
    "nuclear_post_apocalypse": "nuclear_post_apocalypse",
    "cyberpunk": "cyberpunk",
    "steampunk": "steampunk",
    "fantasy": "fantasy",
    "urban_fantasy": "anomalous_incursions",
    "urban_anomalies": "anomalous_incursions",
    "anomalous_incursions": "anomalous_incursions",
    "anomalous_high_school": "anomalous_high_school",
    "nsfw_gore_anomalous_high_school": "anomalous_high_school",
    "furry_anomalous_high_school": "anomalous_high_school",
    "nsfw_furry_gore_anomalous_high_school": "anomalous_high_school",
}
_SEED_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "locations_seed.json"

ENCLOSED_ROOM_KEYWORDS = {
    "room", "office", "classroom", "lab", "clinic", "library", "hall", "dorm",
    "apartment", "house", "shop", "store", "inn", "tavern", "bedroom", "kitchen", "bathroom",
}
INCONGRUOUS_EXTERIOR_SUB_KEYWORDS = {
    "street", "alley", "courtyard", "garden", "park", "road", "path", "forest",
    "field", "bridge", "exterior", "outside", "plaza", "square", "terrace", "balcony", "rooftop", "roof",
}
CAMPUS_FACILITY_KEYWORDS = {
    "classroom", "homeroom", "class ", "library", "staff room", "staff_room", "faculty",
    "science lab", "chemistry lab", "biology lab", "physics lab", "computer lab",
    "gymnasium", "gym", "auditorium", "student council", "clubroom", "rooftop",
    "athletics", "track", "stadium", "swimming pool", "pool", "dojo", "archery range", "tennis court",
    "cafeteria", "canteen", "courtyard", "foyer & shoe lockers", "shoe lockers",
    "getabako", "infirmary", "nurse's office", "nurse", "health room",
    "music wing", "art studio", "rehearsal hall", "lecture hall", "empty classroom",
    "dormitory", "principal's office", "principal", "vice principal", "headmaster",
    "guidance counselor", "counselor", "broadcast", "av room", "audio-visual",
    "bike shed", "bicycle racks", "locker room", "equipment shed", "prep room", "science wing", "academic wing",
    "school gate", "main gate", "entrance gate", "school entrance", "front gate", "campus gate", "school main gates", "entrance path", "gate checkpoint", "main gates",
    "glasshouse", "greenhouse", "botanical", "botanical glasshouse", "conservatory", "arboretum", "vending machine pavilion", "dining hall", "campus promenade", "student commons",
}
RESIDENTIAL_PLACE_KEYWORDS = {
    "residence", "house", "apartment", "cottage", "manor", "villa", "home",
    "player house", "player's house", "living room", "bedroom", "front porch", "backyard",
}
COMMERCIAL_PLACE_KEYWORDS = {
    "café", "cafe", "arcade", "convenience store", "diner", "bakery", "restaurant",
    "bookstore", "boba", "mall", "shopping", "boutique", "market", "game center",
}

HUB_LOCATION_KEYWORDS = (
    "town", "city", "village", "outpost", "market", "bazaar", "camp", "tavern", "inn",
    "station", "haven", "trading post", "merchant", "academy", "school", "campus",
    "plaza", "promenade", "shelter", "vault", "sanctuary", "residential", "residence",
    "starship", "vanguard", "airship", "zeppelin", "hub", "leviathan", "sovereign",
    "dreadnought", "hms", "ironclad", "zephyr", "aether", "celestial", "capital",
    "headquarters", "operations facility", "command complex", "directorate",
    "uptown", "downtown", "suburb", "city center", "theme park", "amusement",
    "grand temple", "mountain sanctuary", "onsen quarter", "airport", "hospital",
    "university", "night market", "botanical",
)

ZONE_EMOJI_KEYWORD_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("headquarters", "operations facility", "command complex", "central spire", "citadel &", "containment", " hq", "_hq"), "🏢"),
    (("sovereign hills", "sky-estates", "penthouse", "billionaire"), "💎"),
    (("industrial zone", "industrial", "refinery", "smelting", "factory"), "🏭"),
    (("uptown",), "🏛️"),
    (("theme park", "amusement"), "🎡"),
    (("grand temple", "eastern temple", "mountain sanctuary", "onsen quarter", "torii"), "⛩️"),
    (("airport", "airfield"), "✈️"),
    (("hospital", "medical center"), "🏥"),
    (("university", "parapsychology"), "🎓"),
    (("eastern quarter", "night market", "chinatown"), "🏮"),
    (("botanical", "aquarium", "zoo"), "🌿"),
    (("planet", "world)", "colony", "asteroid"), "🪐"),
    (("station", "starship", "vanguard", "orbital", "gateway", "nexus", "satellite"), "🚀"),
    (("airship", "zeppelin", "leviathan", "sovereign", "ironclad", "kraken", "dreadnought", "titan", "swallow", "hms", "zephyr", "aether", "aerodrome"), "🎈"),
    (("cultural arts", "student union", "creative arts", "arts & union", "club annex"), "🎭"),
    (("commons", "central plaza", "courtyard & dining", "promenade & commons"), "🌸"),
    (("athletics", "sports", "stadium", "gymnasium", "running track"), "🏟️"),
    (("academy", "school", "campus", "institute", "high school"), "🏫"),
    (("royal capital", "capital city", "citadel", "imperial palace", "palace"), "🏰"),
    (("volcanic", "ashland", "caldera", "foundry", "magma", "lava", "cinder", "pyre", "crater basin"), "🌋"),
    (("mountain", "mountains", "range", "peak", "peaks", "crag", "crags", "cliff", "highland", "ridge", "alpine", "dragonspine", "skyreach", "cloudspire"), "⛰️"),
    (("tundra", "snow", "ice", "frost", "glacial", "frozen", "cryo", "everwinter", "rimewind", "glaciem", "frostfell", "frostbite", "winterveil", "shiverstone"), "❄️"),
    (("swamp", "marsh", "bog", "fen", "mire", "bayou", "mangrove", "blighted marsh"), "🌿"),
    (("cursed", "shadowland", "shadowveil", "dreadfall", "soul-grave", "necropolis", "graveyard", "gallows"), "💀"),
    (("underworld", "chasm", "abyss", "underdark", "trench", "rift", "void", "fissure"), "🕳️"),
    (("cave", "cavern", "grotto", "subterranean", "mine", "shaft", "stalactite"), "🦇"),
    (("dungeon", "labyrinth", "catacomb", "crypt", "tomb", "stronghold", "fortress", "keep", "vaults", "gauntlet", "ancient citadel"), "⚔️"),
    (("desert", "dune", "sand", "oasis", "badland", "arid", "sunscorched", "wasteland"), "🏜️"),
    (("harbor", "port", "dock", "quay", "pier", "tidehaven", "blackanchor", "silverwind"), "⚓"),
    (("seaside", "beach", "coast", "bay", "shore", "waterfront"), "🏖️"),
    (("ancient wood", "ancient forest", "primeval", "elderwood", "deep wood", "withered wood", "canopy"), "🌳"),
    (("wood", "forest", "thicket", "grove", "timber", "copse", "taiga", "trees", "sylvan", "greenvale", "briarwood"), "🌲"),
    (("farmland", "plain", "field", "valley", "pasture", "meadow", "prairie", "rural", "amberfield", "sunreach", "harvest-vale"), "🌾"),
    (("city center", "downtown", "uptown", "commercial", "shopping", "megacorp", "plaza", "promenade", "metropolis"), "🏙️"),
    (("residential", "neighborhood", "slum", "ward", "district", "suburb", "scrap-town", "settlement"), "🏘️"),
    (("fallout vault", "shelter", "fallout", "bunker", "irradiated", "radiation"), "☢️"),
    (("mountain park", "recreation", "nature reserve", "botanical"), "🌲"),
    (("abandoned", "haunted", "manor", "ruin", "colliery"), "🏚️"),
)

GUILD_CAPITAL_ZONE_KEYWORDS = (
    "capital", "imperial", "solaria", "highspire", "lunaria", "aethelgard", "metropolis", "grand city",
)
GUILD_OUTPOST_ZONE_KEYWORDS = (
    "forest", "woods", "mountain", "mountains", "peak", "frontier", "vale",
    "swamp", "marsh", "desert", "tundra", "crag", "ruins", "wilds",
)

SCHOOL_DISUSED_RE = re.compile(r"\b(abandoned|derelict|haunted|decaying|dilapidated|ruin|ruins)\b")
SCHOOL_SECLUDED_CLUB_KEYWORDS = (
    "storage room", "music room", "behind gym", "sheds", "club room", "secret hangout", "hideout",
)
SCHOOL_ADMIN_KEYWORDS = (
    "student council", "council office", "staff room", "teachers' staff",
    "faculty", "principal", "guidance", "infirmary", "nurse",
)
SCHOOL_SOCIAL_HANGOUT_RE = re.compile(
    r"\b(café|cafe|coffee|bakery|restaurant|diner|boba|ramen|canteen|cafeteria|snack shack)\b"
)
SCHOOL_TEA_LOUNGE_KEYWORDS = ("tea lounge", "tea house", "tea room", "tea shop", "coffee & tea")
SCHOOL_ENTERTAINMENT_RE = re.compile(r"\b(arcade|karaoke|bowling|cinema|theater|theatre)\b")
SCHOOL_GAME_LOUNGE_KEYWORDS = ("game center", "game lounge", "game bar")
SCHOOL_RETAIL_RE = re.compile(
    r"\b(convenience|store|shop|market|boutique|bookstore|stationery|mall|shopping|promenade|strip)\b"
)
SCHOOL_CLASSROOM_STUDY_KEYWORDS = (
    "classroom", "homeroom", "library", "lab", "laboratory", "science lab",
    "chemistry", "study", "lecture", "auditorium", "stage",
)
SCHOOL_SPORTS_KEYWORDS = (
    "gymnasium", "gym", "swimming pool", "pool", "athletic field", "field", "track",
    "running track", "bleachers", "court", "basketball", "dojo", "tennis", "soccer",
)
SCHOOL_RESIDENCE_KEYWORDS = ("house", "bedroom", "residence", "apartment", "dorm", "living quarters")
SCHOOL_CIRCULATION_KEYWORDS = (
    "hallway", "hallways", "corridor", "foyer", "shoe lockers", "lockers",
    "stair", "stairs", "entrance", "lobby", "courtyard", "skywalk", "rooftop",
)
SCHOOL_OUTDOOR_KEYWORDS = (
    "park", "beach", "pier", "coastline", "lake", "mountain", "lookout",
    "campsite", "cabin", "summit", "trail", "reserve", "nature", "garden", "cherry tree",
)

ANOM_RIFT_KEYWORDS = ("rift", "anomaly", "anomalies", "containment", "quarantine", "breach", "incursion", "distortion")
ANOM_AGENCY_FACILITY_KEYWORDS = (
    "agency", "headquarters", "operations hq", "tower hq", "spire hq",
    "precinct", "command", "briefing", "armory", "syndicate", "warden", "enclave", "dispatch",
)
ANOM_MEDICAL_SANCTUARY_KEYWORDS = (
    "hospital", "medical", "clinic", "triage", "trauma", "ward",
    "pharmacy", "dispensary", "temple", "shrine", "sanctuary", "chapel",
)
ANOM_CAMPUS_RESEARCH_KEYWORDS = (
    "university", "campus", "lecture", "research", "lab", "laboratory",
    "archive", "library", "institute", "observatory",
)
ANOM_TRANSIT_KEYWORDS = (
    "station", "subway", "platform", "turnstile", "terminal", "airport",
    "harbor", "dock", "pier", "bridge", "overpass", "underpass", "highway", "tunnel",
)
ANOM_COMMERCIAL_LEISURE_KEYWORDS = (
    "cafe", "café", "diner", "restaurant", "ramen", "izakaya", "bar", "nightclub",
    "arcade", "mall", "shop", "store", "boutique", "market", "bazaar", "roastery",
    "bakery", "theme park", "amusement", "midway", "karaoke", "hotel",
)
ANOM_RESIDENTIAL_KEYWORDS = (
    "residence", "apartment", "house", "penthouse", "safehouse", "dorm", "quarters", "home",
)
ANOM_CIVIC_PARKS_KEYWORDS = (
    "park", "garden", "plaza", "square", "promenade", "courtyard", "beach", "boardwalk", "lookout", "forest", "woods",
)

MONSTER_LAIR_RE = re.compile(
    r"\b(lair|lairs|den|dens|nest|nests|nesting|chop-shop|smuggler|hideout|hideouts|coven|mutant|spider|bone tent|war-den)\b"
)
RUINS_ABANDONED_RE = re.compile(
    r"\b(ruin|ruins|ruined|abandoned|derelict|haunted|catacomb|catacombs|ossuary|tomb|tombs|crypt|crypts|colliery|graveyard|scrap-titan|sunken|desecrated|overgrown|collapsed|withered|corrupted|hollowed|dusty|dilapidated)\b"
)
BATTLEGROUND_RE = re.compile(r"\b(warfield|battlefield|barrow|mound|mounds|cairn|cairns|hanging tree)\b")
ARCANE_ANOMALY_RE = re.compile(r"\b(rift|rifts|anomaly|anomalies|distortion|caldera|crater|craters|quantum core)\b")
NATURAL_GROTTO_RE = re.compile(r"\b(spring|springs|geode|thermal|cavern|caverns)\b")
GENERAL_FACILITY_KEYWORDS = (
    "mill", "quarry", "mine", "foundry", "refinery", "furnace", "lab", "laboratory",
    "workshop", "drydock", "facility", "gymnasium", "gym", "swimming pool", "pool",
    "boiler", "engine room", "airlock", "hangar", "terminal", "cargo",
    "power plant", "purification", "solar", "bio-dome", "clinic", "ripperdoc",
)
CAMPSITE_RE = re.compile(r"\b(campsite|campsites|bivouac|encampment|camp|camps|tent|tents)\b")
SOLITARY_DWELLING_RE = re.compile(r"\b(hut|huts|cabin|cabins|bothy|shack|shacks|hermitage|nurse)\b")
SACRED_SITE_RE = re.compile(
    r"\b(shrine|shrines|altar|altars|moonwell|monolith|temple|temples|chapel|cathedral|nave|sanctum|leyline|summoning chamber)\b"
)
GENERAL_HAVEN_KEYWORDS = (
    "village", "town", "hamlet", "settlement", "outpost", "sanctuary", "haven",
    "guild", "market", "bazaar", "plaza", "tavern", "inn", "canteen", "saloon", "lodge",
    "café", "cafe", "arcade", "karaoke", "homeroom", "classroom", "library",
    "residence", "apartment", "living quarters", "dormitory", "penthouse",
    "convenience", "student council", "council office", "staff room", "teachers' staff",
    "office", "faculty", "lounge", "hab", "enclave", "promenade",
)
GENERAL_STRONGHOLD_KEYWORDS = (
    "fortress", "fort", "stronghold", "bastion", "keep", "watchtower", "watchpost",
    "citadel", "palisade", "barricade", "garrison", "precinct", "black site",
    "command bridge", "overseer", "armory", "gladiator",
)
GENERAL_TRANSIT_KEYWORDS = (
    "bridge", "gate", "tollgate", "crossing", "ferry", "pier", "boardwalk",
    "hallway", "hallways", "corridor", "foyer", "lockers", "stairs", "skywalk",
    "turnstile", "skybridge", "dock", "docks", "waypoint", "portal", "checkpoint", "lighthouse",
)
GENERAL_LANDMARK_KEYWORDS = (
    "pass", "overlook", "summit", "peak", "canyon", "gorge", "valley", "archway",
    "lake", "beach", "shoreline", "field", "courtyard", "garden", "park", "clearing",
    "meadow", "bluff", "ridge", "rooftop",
)

DYNAMIC_MINOR_CLUB_ROOM_KEYWORDS = (
    "science & robotics lab",
    "traditional martial arts dojo",
    "art & design studio",
    "newspaper & media room",
    "music wing rehearsal hall",
    "home economics & culinary kitchen",
    "rooftop astronomy dome",
    "library annex reading room",
    "indoor aquatics center",
)

SCHOOL_ROOM_BOARD_KEYWORDS = (
    "campus directive & petition board", "petition board", "directive & petition board",
    "backstage casting & production callboard", "production callboard", "callboard",
    "tournament roster & challenge board", "challenge board", "tournament roster",
    "whispered favors & secret ledger", "secret ledger", "velvet request",
    "notice board", "bulletin board", "bounty board",
    "school gate", "main gate", "front gate", "entrance foyer", "main foyer",
    "central courtyard", "main courtyard",
    "old storage room 3-b", "esports & gaming clubroom",
    "behind gym storage sheds", "abandoned wing boiler-room den",
    *DYNAMIC_MINOR_CLUB_ROOM_KEYWORDS,
)
ANOMALOUS_BOARD_KEYWORDS = (
    "agency hq", "headquarters", "operations hq", "tower hq", "spire hq",
    "command center", "briefing", "dispatch", "precinct", "bounty board",
    "notice board", "bulletin", "mission board", "contract terminal",
    "hidden sanctum", "shadow exchange", "acolyte cloister", "chant hall",
    "brokerage floor",
)
BOUNTY_BOARD_KEYWORDS = (
    "guild", "board", "bulletin", "notice", "bounty", "kiosk", "terminal", "precinct",
    "outpost", "cantina", "lodge", "tavern", "inn", "saloon", "headquarters", "station",
    "student council", "entrance", "lockers", "lobby", "courtyard", "foyer", "library",
    "archive", "hallway", "town square", "dispatch", "aerodrome", "hangar", "depot",
    "village", "settlement", "market", "bazaar", "plaza", "sanctuary", "haven",
)

SCHOOL_CLUB_MERCHANT_KEYWORDS = (
    "club room", "gang", "hideout", "hangout", "clubhouse",
    "quartermaster", "requisition & supply", "supply counter",
    "prop quartermaster", "training quartermaster", "apothecary counter",
    "old storage room 3-b", "esports & gaming clubroom",
    "behind gym storage sheds", "abandoned wing boiler-room den",
    *DYNAMIC_MINOR_CLUB_ROOM_KEYWORDS,
)
ANOM_SCHOOL_CLUB_MERCHANT_KEYWORDS = (
    "club room", "gang", "hideout", "hangout", "clubhouse",
    "council requisition", "requisition & supply", "supply counter",
    "prop quartermaster", "training quartermaster",
    "old storage room 3-b", "esports & gaming clubroom",
    "behind gym storage sheds", "abandoned wing boiler-room den",
    *DYNAMIC_MINOR_CLUB_ROOM_KEYWORDS,
)
BAZAAR_HUB_KEYWORDS = (
    "capital", "grand bazaar", "bazaar", "central market", "market district", "promenade",
    "trade quarter", "commercial district", "metropolis", "citadel plaza", "harbor market",
    "starport concourse", "neon arcade",
)
MULTI_WING_COMPLEX_MARKERS = (
    "tower hq", "field office hq", "office hq", "operations hq", "operations spire hq",
    "headquarters", "agency hq", "hidden sanctum", "shadow exchange",
    "theme park", "amusement", "grand temple",
    "eastern temple", "hospital", "medical center", "botanical",
)


def _compile_word_boundary_union(terms: tuple[str, ...]) -> re.Pattern[str]:
    ordered = sorted(terms, key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(re.escape(k) for k in ordered) + r")\b")


_EXPLICIT_ROOM_SHOP_TERMS = (
    "shop", "store", "market", "bazaar", "emporium", "armory", "ordnance",
    "black-bag ballistics", "tailor", "loom", "vestment", "cognitohazard lab",
    "requisition", "quartermaster", "outfitter", "tailoring", "tactical rigging",
    "fitted armor", "cleansing bay", "psychic detox", "neural recovery",
    "field infirmary", "dispensary", "apothecary", "apotheca", "pharmacy", "canteen",
    "refectory", "commissary", "cafeteria", "espresso", "pour-over", "roastery", "kitchenette",
    "cafe", "café", "taproom", "bar", "tavern", "bakery", "diner",
    "ramen", "izakaya", "tea house", "boutique", "konbini", "convenience",
    "kiosk", "vending", "co-op", "bookstore", "bookshop", "supply counter",
    "velvet boutique", "clubroom", "pawn", "black market", "auction house",
)
_NON_SHOP_ROOM_TERMS = (
    "lobby", "foyer", "corridor", "hallway", "stairwell", "bedroom", "loft",
    "dorm", "dormitory", "dormitories", "quarters", "bathroom", "restroom",
    "locker room", "classroom", "homeroom", "dispatch", "forensics",
    "calibration", "firing range", "training", "containment", "quarantine",
    "vault", "sub-cellar", "cell", "interrogation", "archive", "server",
    "morgue", "icu", "helipad", "garage", "parking", "rooftop", "platform",
    "turnstile", "ward", "triage", "trauma", "operating", "altar", "prayer",
)
_NON_SHOP_ANOM_ROOMS = (
    "classroom", "lecture", "library", "study", "office", "hallway", "corridor",
    "foyer", "lobby", "courtyard", "quad", "roof", "rooftop", "parking",
    "platform", "turnstile", "gate", "ward", "triage", "trauma", "operating",
    "morgue", "icu", "sanctuary", "altar", "shrine", "prayer", "pagoda",
    "coaster", "ferris", "haunted house", "carousel", "dock", "pier", "beach",
    "trail", "forest", "lookout", "bedroom", "living room", "kitchen",
    "briefing", "command", "interrogation", "containment", "cell", "training",
    "firing range", "helipad", "garage", "archive", "server",
)
_EXPLICIT_SHOP_NOUNS = (
    "shop", "store", "market", "bazaar", "emporium", "café", "cafe", "pharmacy",
    "armory", "ordnance", "black-bag ballistics", "tailor", "loom", "vestment", "cognitohazard lab",
    "requisition", "quartermaster", "outfitter", "tailoring",
    "tactical rigging", "fitted armor", "cleansing bay", "psychic detox",
    "neural recovery", "field infirmary", "dispensary", "apotheca", "convenience", "konbini",
    "boutique", "bakery", "stall", "canteen", "refectory", "commissary", "diner", "roastery", "pour-over",
    "kitchenette", "izakaya", "ramen", "espresso", "tea house", "bookstore",
    "duty-free", "midway", "omikuji", "talisman stand", "pawn", "black market",
    "auction house", "boiler-room locker", "custodian's boiler", "campus co-op", "co-op",
    "fox-fire apothecary", "spirit-fire curio", "myōbu spirit-fire", "myobu spirit-fire", "spirit curio",
    "pusaka", "artisan hall", "ranger station", "park ranger field station", "ranger field station",
    "trailhead information counter", "trailhead outpost", "trail permit", "tea street",
)
_SHOP_KEYWORDS = (
    "shop", "store", "market", "bazaar", "emporium", "café", "cafe", "pharmacy",
    "armory", "blacksmith", "weaponsmith", "quartermaster", "convenience", "boutique",
    "bakery", "stall", "merchant", "trader", "noodle bar", "canteen", "saloon", "tavern", "taproom",
    "inn", "trading post", "general store", "guild shop", "alchemist", "herbalist", "forge",
    "outfitter", "tailoring", "tactical rigging", "fitted armor", "cleansing bay", "psychic detox",
    "neural recovery", "field infirmary", "dispensary", "clinic", "roastery", "pour-over", "kitchenette", "izakaya", "ramen",
    "antiquities", "licensed wards", "pawn", "black market", "afterdark", "red-lantern",
    "konbini", "auction house", "espresso", "velvet mirage", "crimson masquerade", "fish market",
    "omikuji", "talisman", "carnival midway", "gift emporium", "duty-free", "night market",
    "apothecary", "black bazaar", "tea house", "bookstore", "trauma center", "emergency trauma", "ambulance triage",
    "regional tower hq", "operations spire hq", "tower hq", "field office hq", "office hq", "operations hq",
    "requisition shop", "requisition depot",
)
_HQ_SHOP_WING_KEYWORDS = (
    "armory", "ordnance", "requisition", "outfitter", "tailoring",
    "tactical rigging", "fitted armor", "cleansing bay", "psychic detox",
    "neural recovery", "field infirmary", "dispensary", "clinic", "medical",
    "canteen", "espresso", "pour-over", "kitchenette", "cafe", "café", "shop", "store",
)

_EXPLICIT_ROOM_SHOP_RE = _compile_word_boundary_union(_EXPLICIT_ROOM_SHOP_TERMS)
_NON_SHOP_ROOM_RE = _compile_word_boundary_union(_NON_SHOP_ROOM_TERMS)
_NON_SHOP_ANOM_ROOM_RE = _compile_word_boundary_union(_NON_SHOP_ANOM_ROOMS)
_EXPLICIT_SHOP_NOUNS_RE = _compile_word_boundary_union(_EXPLICIT_SHOP_NOUNS)
_SHOP_KEYWORDS_RE = _compile_word_boundary_union(_SHOP_KEYWORDS)
_HQ_SHOP_WING_RE = _compile_word_boundary_union(_HQ_SHOP_WING_KEYWORDS)
_HQ_TOKEN_RE = re.compile(r"\bhq\b")

SCHOOL_QUARTERMASTER_OR_MINOR_SHOPS = (
    "council requisition & supply counter", "requisition & supply", "supply counter",
    "costume wardrobe & prop quartermaster", "prop quartermaster",
    "varsity gear & training quartermaster", "training quartermaster",
    "silk & curio apothecary counter", "apothecary counter",
    "velvet boutique",
    "old storage room 3-b", "esports & gaming clubroom",
    "behind gym storage sheds", "abandoned wing boiler-room den",
    *DYNAMIC_MINOR_CLUB_ROOM_KEYWORDS,
)
NON_SHOP_SCHOOL_PLACES = (
    "classroom", "homeroom", "library", "office", "council",
    "lockers", "gym", "gymnasium", "rooftop", "lounge", "staff room",
    "infirmary", "dorm", "desk", "corridor", "foyer", "stairs", "alcove",
    "lobby", "vault", "sub-cellar", "containment", "quarantine",
)
SCHOOL_HQ_EXEMPT_SHOP_WINGS = (
    "armory", "ordnance", "requisition", "outfitter", "tailoring", "apothecary", "cleansing bay",
)
SCHOOL_SHOP_KEYWORDS = (
    "cafeteria", "canteen", "café", "cafe", "convenience", "store", "bakery",
    "kiosk", "vending", "co-op", "food court", "shopping", "bakeshop",
    "sweet shop", "restaurant", "diner", "conbini", "stall", "market", "boutique", "gift",
)
HQ_PARENT_CHAIN_KEYWORDS = (
    "tower hq", "field office hq", "office hq", "operations hq", "operations spire hq", "headquarters", "agency hq",
)

EXCLUDED_FACTION_HQ_PARENT_WINGS = (
    "cultural & student clubroom wing",
    "general student clubroom wing",
    "cultural arts & student union",
    "abandoned old campus building",
    "abandoned old campus wing",
    "abandoned old campus wing & clock tower",
)
FACTION_HQ_KEYWORDS = (
    "faction hq", "headquarters", "command center", "guild master",
    "executive council chamber", "main auditorium stage",
    "main gymnasium & varsity court", "main velvet salon",
    "old storage room 3-b", "esports & gaming clubroom",
    "behind gym storage sheds", "abandoned wing boiler-room den",
    *DYNAMIC_MINOR_CLUB_ROOM_KEYWORDS,
)
FACTION_HQ_SCHOOL_FACILITY_KEYWORDS = (
    "student council office", "council office",
    "campus auditorium & drama theater",
    "varsity athletic directorate & gymnasium",
    "velvet basement salon",
)

# ── Access Gate & Sanctuary / Authority / Breach / Privacy Catalogs ───────
_SANCTUARY_PREFERRED_KEYWORDS = (
    "inn", "tavern", "guild", "cafe", "coffee", "diner", "teahouse",
    "commons", "agency_hq", "lobby", "sanctuary", "shelter", "bazaar",
    "market", "promenade", "plaza", "hub",
)
_SANCTUARY_EXCLUDED_KEYWORDS = (
    "homeroom", "classroom", "rooftop", "infirmary", "faculty",
    "principal", "council", "locker", "pool", "dungeon", "prison",
    "morgue", "quarantine", "vault", "sewer", "crypt",
)
MULTI_WING_UNLOCK_PARENTS = (
    "loc_agency_hq", "loc_private_hq_1", "loc_private_hq_2",
    "loc_general_hospital", "loc_theme_park", "loc_eastern_temple", "loc_botanical_zoo",
    "loc_cult_sanctum_hq", "loc_clandestine_syndicate_hq",
    "fac_agency_residence", "fac_temple_residence", "fac_cult_residence", "fac_syndicate_residence",
    "loc_hidden_kitsune_village", "loc_hidden_bunian_village",
)
NPC_AUTHORITY_FACULTY_ROLES = (
    "teacher", "faculty", "staff", "nurse", "counselor", "principal", "guard", "security",
)
NPC_AUTHORITY_COUNCIL_ROLES = (
    "student council", "council", "president", "treasurer", "vice president",
)
NPC_AUTHORITY_COUNCIL_TARGETS = ("council", "homeroom", "hallway", "commons", "library")
NPC_AUTHORITY_VELVET_CLUBS = (
    "velvet", "secret society", "after-hours", "salon", "midnight", "crimson", "hedon",
)

ANOM_PUBLIC_HQ_OPEN_KEYWORDS = (
    "loc_hq_main_lobby", "loc_hq_tactical_armory", "loc_hq_field_outfitter",
    "loc_hq_medical_bay", "loc_hq_cleansing_bay", "loc_hq_canteen_cafe",
    "loc_hq_executive_dispatch", "entrance", "lobby", "reception", "bounty",
)
ANOM_PUBLIC_HQ_RESTRICTED_KEYWORDS = (
    "loc_hq_containment_sector", "loc_hq_research_division", "loc_hq_parapsych_lab",
    "loc_hq_training_range", "loc_hq_training_arena", "loc_hq_agent_dormitories",
)
ANOM_PRIV1_OPEN_KEYWORDS = (
    "sub_priv1_entrance", "sub_priv1_dispatch", "entrance", "lobby", "atrium",
    "atrium concierge", "global contracts", "contracts & telemetry",
    "contract board", "contract & telemetry", "contract & tactical dispatch",
)
ANOM_PRIV2_OPEN_KEYWORDS = (
    "sub_priv2_entrance", "sub_priv2_dispatch", "entrance", "foyer", "reception",
    "brick-front vestibule", "security reception", "partner case room",
    "lobby", "corkboard", "dispatch bullpen", "contract board", "contract & tactical dispatch",
)
ANOM_MONASTIC_RESTRICTED_KEYWORDS = (
    "loc_et_five_story_pagoda", "loc_et_reliquary_pagoda", "loc_et_exorcist_dojo",
)
ANOM_HQ_REASON_LABELS = {
    "public_agency": "Restricted Bureau Inner Sector (Public Agency Clearance Required)",
    "private_agency_1": "Restricted High-Security Tower Floor & Vault (Conglomerate Clearance Required)",
    "private_agency_2": "Restricted Partner Suite & Vaulted Armory (Agency Partner Credentials Required)",
    "monastic_order": "Restricted Monastic Inner Sanctum (Order Initiate Clearance Required)",
    "cult_faction": "Ward-Sealed Occult Sanctum (Hostile Cult Restricted Area)",
    "clandestine_faction": "Biometric Clandestine Vault (Unauthorized Entry Prohibited)",
}

BREACH_ACTION_KEYWORDS = (
    "sneak", "pick", "climb", "scale", "fence", "lockpick", "force", "break in", "bypass",
    "talk your way", "convince", "excuse", "nurse", "ring the intercom", "buzz", "apologize",
    "audition", "charm", "cellar", "grate", "contract permit", "freelance permit", "public agency", "flash permit",
)
PERMIT_ACTION_KEYWORDS = ("contract permit", "freelance permit", "flash permit")
TRUANCY_PASS_KEYWORDS = (
    "hall pass", "nurse pass", "sick pass", "early dismissal", "staff pass", "gate pass", "master key", "council badge",
)
TRUANCY_STAFF_COMPANION_ROLES = ("teacher", "faculty", "staff", "nurse", "counselor", "principal")
LOVE_HOTEL_APPT_KEYWORDS = ("love_hotel", "love hotel", "mirrored luxury", "rooftop jacuzzi")
INVENTORY_UNLOCK_KEY_RE = re.compile(
    r"\b(master key|skeleton key|staff pass|council badge|keycard|passcard|access card|clearance badge|door key|gate key|vault key|sanctum key|room key|office key|key)\b"
)
INTERCOM_RING_ONLY_KEYWORDS = ("ring the intercom", "buzz", "ring the bell", "intercom")
INTERCOM_BREACH_EXCLUSION_KEYWORDS = (
    "sneak", "pick", "lockpick", "climb", "scale", "force", "break in", "bypass",
)
COVERT_SNEAK_ATTEMPT_KEYWORDS = ("sneak", "infiltrate", "slip", "creep", "climb", "scale")
PATROL_AUTHORITY_ROLES = (
    "teacher", "staff", "guidance", "counselor", "principal", "vice principal",
    "prefect", "hall monitor", "discipline", "security", "guard", "officer",
)
PATROL_AUTHORITY_CLUBS = ("student council", "disciplinary")
PATROL_OFFICER_POOL = (
    "Officer Takahashi", "Officer Miller", "Officer Sato", "Officer Vance", "Officer Henderson",
)

SECLUDED_PROP_KEYWORDS = (
    "aisle", "alcove", "corner", "behind", "booth", "closet", "balcony",
    "stairwell", "under", "terrace", "shed", "secluded", "private", "trellis",
)
SECLUDED_LOCATION_KEYWORDS = (
    "balcony", "booth", "alcove", "shed", "closet", "terrace", "secluded", "stairwell", "trellis",
)
SECRET_CONTEXT_ACTION_KEYWORDS = (
    "confess", "kiss", "whisper", "private", "alone", "secret", "hide", "intimate",
)
SECLUDED_SIBLING_NAME_KEYWORDS = (
    "balcony", "terrace", "booth", "alcove", "shed", "nook", "private", "corner",
)

CIVIC_POLICE_ROLE_TOKENS = frozenset({
    "police", "patrol", "officer", "detective", "sergeant", "sheriff", "koban", "constable",
})
ACADEMIC_FACULTY_TOKENS = frozenset({
    "teacher", "faculty", "staff", "nurse", "librarian", "principal", "counselor",
    "custodian", "janitor", "professor", "instructor",
})
ACADEMIC_STAGE_LOCATION_KEYWORDS = (
    "school", "academy", "classroom", "homeroom", "stacks", "library", "infirmary", "staff room",
)

__all__ = [
    "ACADEMIC_FACULTY_TOKENS",
    "ACADEMIC_STAGE_LOCATION_KEYWORDS",
    "ANOMALOUS_BOARD_KEYWORDS",
    "ANOM_AGENCY_FACILITY_KEYWORDS",
    "ANOM_CAMPUS_RESEARCH_KEYWORDS",
    "ANOM_CIVIC_PARKS_KEYWORDS",
    "ANOM_COMMERCIAL_LEISURE_KEYWORDS",
    "ANOM_HQ_REASON_LABELS",
    "ANOM_MEDICAL_SANCTUARY_KEYWORDS",
    "ANOM_MONASTIC_RESTRICTED_KEYWORDS",
    "ANOM_PRIV1_OPEN_KEYWORDS",
    "ANOM_PRIV2_OPEN_KEYWORDS",
    "ANOM_PUBLIC_HQ_OPEN_KEYWORDS",
    "ANOM_PUBLIC_HQ_RESTRICTED_KEYWORDS",
    "ANOM_RESIDENTIAL_KEYWORDS",
    "ANOM_RIFT_KEYWORDS",
    "ANOM_SCHOOL_CLUB_MERCHANT_KEYWORDS",
    "ANOM_TRANSIT_KEYWORDS",
    "ARCANE_ANOMALY_RE",
    "BATTLEGROUND_RE",
    "BAZAAR_HUB_KEYWORDS",
    "BOUNTY_BOARD_KEYWORDS",
    "BREACH_ACTION_KEYWORDS",
    "CAMPSITE_RE",
    "CAMPUS_FACILITY_KEYWORDS",
    "CIVIC_POLICE_ROLE_TOKENS",
    "COMMERCIAL_PLACE_KEYWORDS",
    "COVERT_SNEAK_ATTEMPT_KEYWORDS",
    "DYNAMIC_MINOR_CLUB_ROOM_KEYWORDS",
    "ENCLOSED_ROOM_KEYWORDS",
    "EXCLUDED_FACTION_HQ_PARENT_WINGS",
    "FACTION_HQ_KEYWORDS",
    "FACTION_HQ_SCHOOL_FACILITY_KEYWORDS",
    "GENERAL_FACILITY_KEYWORDS",
    "GENERAL_HAVEN_KEYWORDS",
    "GENERAL_LANDMARK_KEYWORDS",
    "GENERAL_STRONGHOLD_KEYWORDS",
    "GENERAL_TRANSIT_KEYWORDS",
    "GUILD_CAPITAL_ZONE_KEYWORDS",
    "GUILD_OUTPOST_ZONE_KEYWORDS",
    "HQ_PARENT_CHAIN_KEYWORDS",
    "HUB_LOCATION_KEYWORDS",
    "INCONGRUOUS_EXTERIOR_SUB_KEYWORDS",
    "INTERCOM_BREACH_EXCLUSION_KEYWORDS",
    "INTERCOM_RING_ONLY_KEYWORDS",
    "INVENTORY_UNLOCK_KEY_RE",
    "LOCATION_SCENARIOS",
    "LOVE_HOTEL_APPT_KEYWORDS",
    "MONSTER_LAIR_RE",
    "MULTI_WING_COMPLEX_MARKERS",
    "MULTI_WING_UNLOCK_PARENTS",
    "NATURAL_GROTTO_RE",
    "NON_SHOP_SCHOOL_PLACES",
    "NPC_AUTHORITY_COUNCIL_ROLES",
    "NPC_AUTHORITY_COUNCIL_TARGETS",
    "NPC_AUTHORITY_FACULTY_ROLES",
    "NPC_AUTHORITY_VELVET_CLUBS",
    "PATROL_AUTHORITY_CLUBS",
    "PATROL_AUTHORITY_ROLES",
    "PATROL_OFFICER_POOL",
    "PERMIT_ACTION_KEYWORDS",
    "RESIDENTIAL_PLACE_KEYWORDS",
    "RUINS_ABANDONED_RE",
    "SACRED_SITE_RE",
    "SCHOOL_ADMIN_KEYWORDS",
    "SCHOOL_CIRCULATION_KEYWORDS",
    "SCHOOL_CLASSROOM_STUDY_KEYWORDS",
    "SCHOOL_CLUB_MERCHANT_KEYWORDS",
    "SCHOOL_DISUSED_RE",
    "SCHOOL_ENTERTAINMENT_RE",
    "SCHOOL_GAME_LOUNGE_KEYWORDS",
    "SCHOOL_HQ_EXEMPT_SHOP_WINGS",
    "SCHOOL_OUTDOOR_KEYWORDS",
    "SCHOOL_QUARTERMASTER_OR_MINOR_SHOPS",
    "SCHOOL_RESIDENCE_KEYWORDS",
    "SCHOOL_RETAIL_RE",
    "SCHOOL_ROOM_BOARD_KEYWORDS",
    "SCHOOL_SECLUDED_CLUB_KEYWORDS",
    "SCHOOL_SHOP_KEYWORDS",
    "SCHOOL_SOCIAL_HANGOUT_RE",
    "SCHOOL_SPORTS_KEYWORDS",
    "SCHOOL_TEA_LOUNGE_KEYWORDS",
    "SECLUDED_LOCATION_KEYWORDS",
    "SECLUDED_PROP_KEYWORDS",
    "SECLUDED_SIBLING_NAME_KEYWORDS",
    "SECRET_CONTEXT_ACTION_KEYWORDS",
    "SOLITARY_DWELLING_RE",
    "TAG_TO_LOCATION_SEED_KEY",
    "TRUANCY_PASS_KEYWORDS",
    "TRUANCY_STAFF_COMPANION_ROLES",
    "ZONE_EMOJI_KEYWORD_RULES",
    "_EXPLICIT_ROOM_SHOP_RE",
    "_EXPLICIT_ROOM_SHOP_TERMS",
    "_EXPLICIT_SHOP_NOUNS",
    "_EXPLICIT_SHOP_NOUNS_RE",
    "_HQ_SHOP_WING_KEYWORDS",
    "_HQ_SHOP_WING_RE",
    "_HQ_TOKEN_RE",
    "_NON_SHOP_ANOM_ROOMS",
    "_NON_SHOP_ANOM_ROOM_RE",
    "_NON_SHOP_ROOM_RE",
    "_NON_SHOP_ROOM_TERMS",
    "_SANCTUARY_EXCLUDED_KEYWORDS",
    "_SANCTUARY_PREFERRED_KEYWORDS",
    "_SEED_PATH",
    "_SHOP_KEYWORDS",
    "_SHOP_KEYWORDS_RE",
    "_compile_word_boundary_union",
]
