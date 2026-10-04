"""
Procedural name generator with scenario-specific name pools.

The LLM is instructed (see game_engine.SYSTEM_PROMPT) to emit indexed
placeholder tokens -- `{{PERSON_1}}`, `{{PERSON_2}}`, `{{PLACE_1}}`, etc --
the *first* time it introduces a brand-new character or location, instead of
inventing a name itself.

`resolve_tokens_deep()` finds every distinct token in a full LLM JSON
response, rolls exactly one name per distinct token matching the session's
scenario, and substitutes it everywhere that token appears.
"""
import json
import random
import re
from pathlib import Path
from mechanics.world.locations.seeds import is_school_scenario

_DATA_PATH = Path(__file__).parent / "data" / "namegen_data.json"

with open(_DATA_PATH, encoding="utf-8") as f:
    _DATA = json.load(f)

# Precompile comprehensive sets of male and female names from all scenarios
_ALL_MALE_NAMES = set()
_ALL_FEMALE_NAMES = set()

for s_val in _DATA.values():
    if isinstance(s_val, dict) and "person" in s_val:
        p_dict = s_val["person"]
        if isinstance(p_dict, dict):
            for n in p_dict.get("male", []):
                _ALL_MALE_NAMES.add(str(n).lower().strip())
            for n in p_dict.get("female", []):
                _ALL_FEMALE_NAMES.add(str(n).lower().strip())

_ALL_ROLE_NAMES = set()
for s_val in _DATA.values():
    if isinstance(s_val, dict) and "roles" in s_val:
        for r in s_val.get("roles", []):
            if isinstance(r, str):
                _ALL_ROLE_NAMES.add(r.lower().strip())

_GENERIC_ROLE_PATTERNS = [
    r"^(student council|class|club|team|guild|order|gang|committee|department|faculty)\s+(president|vice president|treasurer|secretary|leader|captain|head|officer|member|lead|rep|representative|enforcer|brawler|scout|advisor|coordinator|director)$",
    r"^(headmaster|principal|vice principal|teacher|professor|instructor|tutor|librarian|counselor|advisor|dean|sensei|dorm warden|curator)$",
    r"^(guildmaster|shopkeeper|innkeeper|bartender|tavernkeeper|blacksmith|armorer|merchant|alchemist|apothecary|quartermaster|vendor|peddler|trader)$",
    r"^(guard|town guard|city guard|guard captain|captain of the guard|sentinel|watchman|paladin commander|soldier|knight|grunt|patrol|enforcer)$",
    r"^(president|vice president|chairman|chairwoman|director|ceo|executive|manager|boss|chief|commander|warlord|gang boss|secretary|treasurer|rep|representative)$",
    r"^(class rep|class representative|hall monitor|discipline officer|prefect|student council member)$",
    r"^(drunken|noisy|rowdy|weary|curious|hooded|elderly|young|local|fellow|ambient|suspicious|shady)?\s*(patron|bystander|customer|citizen|civilian|traveler|onlooker|wanderer|adventurer|villager|townsperson|student|bouncer|barkeep|waiter|waitress|maid|servant|minstrel|bard|drifter|dockworker|sailor|laborer|commoner|peasant)$",
]
_GENERIC_ROLE_RE = [re.compile(p, re.IGNORECASE) for p in _GENERIC_ROLE_PATTERNS]


def is_generic_role_name(name: str) -> bool:
    """Checks if a string is a generic job title / role rather than a personal character name."""
    if not name:
        return False
    clean = str(name).strip().lower()
    # Strip leading articles and bracketed tags like [NPC] or (Neutral)
    clean = re.sub(r"^(the|a|an)\s+", "", clean).strip()
    clean = re.sub(r"[\(\[\{].*?[\)\]\}]", "", clean).strip()
    if not clean:
        return False
    if clean in _ALL_ROLE_NAMES:
        return True
    for rx in _GENERIC_ROLE_RE:
        if rx.match(clean):
            return True
    return False


def is_valid_entity_name(name: str) -> bool:
    """Checks if a string is a valid personal character/NPC or faction name,
    strictly rejecting LLM meta-commentary, reasoning leakages, leaked JSON fragments,
    and corrupted prompt markers."""
    if not name or not isinstance(name, str):
        return False
    clean = name.strip()
    # Length boundaries (names shouldn't be single chars or long run-on sentences)
    if len(clean) < 2 or len(clean) > 50:
        return False
    # Reject strings containing JSON / code / formatting syntax
    if any(c in clean for c in "{}[]\\*`<>|"):
        return False
    if clean.count('"') > 0 or clean.count("'") > 2:
        return False
    if "\n" in clean or "\r" in clean:
        return False
    # Reject known LLM meta-talk keywords and reasoning markers
    low = clean.lower()
    meta_keywords = (
        "wait -", "correcting", "providing full", "json", "requested output",
        "scene:", "scene_text", "outcome_narrative", "next_narrative",
        "turn summary", "action breakdown", "error:", "attributeerror",
        "undefined", "null", "none", "token", "person_", "role_", "placeholder",
        "actually providing", "consistency with"
    )
    if any(kw in low for kw in meta_keywords):
        return False
    return True


def split_name_and_role(raw_text: str, scenario: str = "fantasy", gender: str = "") -> tuple[str, str]:
    """Splits a combined name string like 'Skye Anderson (Student Council President)'
    or 'Student Council President' into (proper_name, role_title)."""
    if not raw_text:
        return generate_person_name(scenario, gender=gender), ""
    text = str(raw_text).strip()
    
    # Pattern: Name (Role) or Name [Role]
    paren_match = re.match(r"^([^\(\[\{]+)[\(\[\{]([^\)\]\}]+)[\)\]\}]$", text)
    if paren_match:
        part1 = paren_match.group(1).strip()
        part2 = paren_match.group(2).strip()
        if is_generic_role_name(part2):
            return part1, part2
        if is_generic_role_name(part1):
            return part2, part1
        return part1, part2
        
    # Pattern: Role - Name or Name - Role
    if " — " in text or " - " in text:
        delimiter = " — " if " — " in text else " - "
        parts = text.split(delimiter, 1)
        part1 = parts[0].strip()
        part2 = parts[1].strip()
        if is_generic_role_name(part1):
            return part2, part1
        if is_generic_role_name(part2):
            return part1, part2

    if is_generic_role_name(text):
        return generate_person_name(scenario, gender=gender), text

    return text, ""


def sanitize_person_name(name: str, scenario: str = "fantasy", gender: str = "") -> str:
    """If name is a generic role title, generate an authentic personal name. Otherwise return name."""
    clean_name, _ = split_name_and_role(name, scenario=scenario, gender=gender)
    return clean_name


_TOKEN_RE = re.compile(r"\{{1,2}(PERSON|PLACE|ROLE|SCHOOL|CLASSROOM|PARK)(?:_\w+)?\}{1,2}", re.IGNORECASE)


def is_known_male_name(name: str) -> bool:
    """Checks if a given name or first name matches any known male name in namegen data."""
    if not name:
        return False
    clean = str(name).strip().lower()
    first = clean.split()[0] if clean else ""
    return first in _ALL_MALE_NAMES or clean in _ALL_MALE_NAMES


def is_known_female_name(name: str) -> bool:
    """Checks if a given name or first name matches any known female name in namegen data."""
    if not name:
        return False
    clean = str(name).strip().lower()
    first = clean.split()[0] if clean else ""
    return first in _ALL_FEMALE_NAMES or clean in _ALL_FEMALE_NAMES


def get_all_gendered_names() -> tuple[set, set]:
    """Returns all precompiled male and female names from namegen data."""
    return set(_ALL_MALE_NAMES), set(_ALL_FEMALE_NAMES)


TAG_TO_NAMEGEN_KEY = {
    "space": "sci_fi",
    "sci_fi": "sci_fi",
    "grimdark": "dark_fantasy",
    "dark_fantasy": "dark_fantasy",
    "isekai": "isekai_fantasy",
    "isekai_fantasy": "isekai_fantasy",
    "high_school": "high_school_drama",
    "high_school_drama": "high_school_drama",
    "post_apocalypse": "nuclear_post_apocalypse",
    "nuclear_post_apocalypse": "nuclear_post_apocalypse",
    "cyberpunk": "cyberpunk",
    "steampunk": "steampunk",
    "fantasy": "fantasy",
}


def _get_scenario_data(scenario: str, category: str):
    scen = str(scenario or "fantasy").lower().strip()
    direct_key = TAG_TO_NAMEGEN_KEY.get(scen, scen)
    if direct_key in _DATA and category in _DATA[direct_key]:
        return _DATA[direct_key][category]

    try:
        from scenario_data import get_scenario
        scen_info = get_scenario(scen)
        base = scen_info.get("base_scenario")
        if base:
            base_key = TAG_TO_NAMEGEN_KEY.get(base, base)
            if base_key in _DATA and category in _DATA[base_key]:
                return _DATA[base_key][category]
        tags = scen_info.get("tags") or []
        matching = []
        for tag in tags:
            tag_key = TAG_TO_NAMEGEN_KEY.get(tag, tag)
            if tag_key in _DATA and category in _DATA[tag_key]:
                matching.append(tag_key)
        if matching:
            chosen = random.choice(matching)
            return _DATA[chosen][category]
    except Exception:
        pass

    if "fantasy" in _DATA and category in _DATA["fantasy"]:
        return _DATA["fantasy"][category]
    if "default" in _DATA and category in _DATA["default"]:
        return _DATA["default"][category]
    for s_key, s_val in _DATA.items():
        if isinstance(s_val, dict) and category in s_val:
            return s_val[category]
    return {} if category != "roles" else []


def generate_person_name(scenario: str = "fantasy", gender: str = "") -> str:
    d = _get_scenario_data(scenario, "person")
    male_pool = d.get("male") or []
    female_pool = d.get("female") or []

    g = str(gender or "").lower().strip()
    is_female = ("female" in g or "woman" in g or "girl" in g or "feminine" in g or "she" in g)
    is_male = ("male" in g or "man" in g or "boy" in g or "masculine" in g or "he" in g) and not is_female

    if is_female:
        pool = female_pool or ["Celestia"]
    elif is_male:
        pool = male_pool or ["Aldric"]
    else:
        if male_pool and female_pool:
            pool = random.choice([male_pool, female_pool])
        else:
            pool = male_pool or female_pool or ["Aldric"]

    first = random.choice(pool)
    surname_chance = d.get("surname_chance", 0.5)
    last_list = d.get("last") or []
    if last_list and random.random() < surname_chance:
        return f"{first} {random.choice(last_list)}"
    return first


def generate_role(scenario: str = "fantasy", hash_val: int = None) -> str:
    """Generates a scenario-specific role/occupation/title from namegen_data.json."""
    roles = _get_scenario_data(scenario, "roles")
    if not isinstance(roles, list) or not roles:
        roles = _get_scenario_data("default", "roles")
    if not isinstance(roles, list) or not roles:
        roles = [
            "Former Classmate", "Academy Senior", "Town Guard", "Travelling Merchant",
            "Childhood Friend", "Fellow Adventurer", "Apprentice Specialist"
        ]

    if hash_val is not None:
        return roles[(hash_val * 17 + 13) % len(roles)]
    return random.choice(roles)


def generate_neutral_npc(scenario: str = "fantasy", gender: str = "") -> dict:
    """Generates a nameless/neutral NPC package with name and role."""
    name = generate_person_name(scenario=scenario, gender=gender)
    role = generate_role(scenario=scenario)
    return {
        "name": name,
        "role": role,
        "gender": gender or "neutral"
    }


SCHOOL_NAME_PREFIXES = [
    # Anime / Japanese-inspired
    "Sakuragaoka", "Kiyosumi", "Hanamizuki", "Shiranui", "Fujimi", "Hakurei", "Kamome",
    "Aobajohsai", "Kurogane", "Mizuho", "Tachibana", "Shinonome", "Kasumigaoka", "Suimei",
    "Tsukimori", "Kirisaki", "Hoshizora", "Asahi", "Suzuran", "Seiryo", "Hanazono", "Ouka",
    # Western / Classical / Prestige
    "Oakhaven", "St. Jude", "Maplewood", "Crestview", "Willow Creek", "Rosewood", "Silverthorne",
    "Sunnyvale", "Northwood", "Everglade", "Ashford", "Briarcliff", "St. Michael", "Brookridge",
    "Westlake", "St. Valeria", "Oakridge", "Riverdale", "Sunnyside", "Pinewood", "Greenwood",
    "Highridge", "Kingsley", "Riverwood", "St. Claire", "Fairview", "Meadowbrook", "Ravenwood"
]

SCHOOL_NAME_SUFFIXES = [
    "Academy",
    "High School",
    "Preparatory Academy",
    "Senior High",
    "Private Academy",
    "Institute"
]


def generate_school_name(scenario: str = "high_school_drama", hash_val: int = None) -> str:
    """Generates a dynamic scenario-appropriate school/academy name."""
    scen = str(scenario or "high_school_drama").lower().strip()

    if "fantasy" in scen or "isekai" in scen:
        fantasy_prefixes = ["Royal Magic", "Silverleaf Arcane", "Grand Spire", "Aethelgard", "St. Celestia", "Solaria", "Astral", "Highspire", "Valerius"]
        fantasy_suffixes = ["Academy", "Scholomance", "Arcane Institute", "College of Magic", "Academy of Sorcery"]
        if hash_val is not None:
            p = fantasy_prefixes[(hash_val * 19 + 7) % len(fantasy_prefixes)]
            s = fantasy_suffixes[(hash_val * 31 + 13) % len(fantasy_suffixes)]
            return f"{p} {s}"
        return f"{random.choice(fantasy_prefixes)} {random.choice(fantasy_suffixes)}"

    if "cyberpunk" in scen or "sci_fi" in scen or "space" in scen:
        scifi_prefixes = ["Neo-Kyoto", "Aegis Orbital", "Apex Cybernetics", "Nova Horizon", "Nexus Technical", "Helios Advanced", "Vanguard"]
        scifi_suffixes = ["Institute", "Collegiate", "Academy", "Technical High", "Polytechnic"]
        if hash_val is not None:
            p = scifi_prefixes[(hash_val * 19 + 7) % len(scifi_prefixes)]
            s = scifi_suffixes[(hash_val * 31 + 13) % len(scifi_suffixes)]
            return f"{p} {s}"
        return f"{random.choice(scifi_prefixes)} {random.choice(scifi_suffixes)}"

    # Default High School Drama / Furry High School / Modern
    if hash_val is not None:
        p = SCHOOL_NAME_PREFIXES[(hash_val * 23 + 11) % len(SCHOOL_NAME_PREFIXES)]
        s = SCHOOL_NAME_SUFFIXES[(hash_val * 37 + 17) % len(SCHOOL_NAME_SUFFIXES)]
        return f"{p} {s}"
    return f"{random.choice(SCHOOL_NAME_PREFIXES)} {random.choice(SCHOOL_NAME_SUFFIXES)}"


CLASSROOM_NAMES = [
    "Class 2-B (Homeroom)",
    "Class 2-A (Homeroom)",
    "Class 2-C (Homeroom)",
    "Classroom 2-B (Homeroom)",
    "Classroom 2-A (Homeroom)",
    "Class 3-A (Homeroom)",
    "Class 3-B (Homeroom)",
    "Class 1-A (Homeroom)",
    "Class 1-B (Homeroom)",
    "Room 204 (Homeroom)",
    "Room 201 (Homeroom)",
    "Room 302 (Homeroom)",
    "Class 2-1 (Homeroom)",
    "Class 2-2 (Homeroom)",
    "Class 2-D (Homeroom)",
]


def generate_classroom_name(scenario: str = "high_school_drama", hash_val: int = None) -> str:
    """Generates a dynamic scenario-appropriate classroom/homeroom name."""
    scen = str(scenario or "high_school_drama").lower().strip()

    if "fantasy" in scen or "isekai" in scen:
        fantasy_classes = [
            "Novice Mage Lecture Hall (Homeroom)",
            "Arcane Theory Room 3 (Homeroom)",
            "Class 1-A Arcane Studies (Homeroom)",
            "Spire Lecture Hall B (Homeroom)",
            "Elementalist Class 2-A (Homeroom)",
            "Enchanters' Study Hall (Homeroom)"
        ]
        if hash_val is not None:
            return fantasy_classes[(hash_val * 17 + 5) % len(fantasy_classes)]
        return random.choice(fantasy_classes)

    if "cyberpunk" in scen or "sci_fi" in scen or "space" in scen:
        scifi_classes = [
            "Sector 4 Tech Lab (Homeroom)",
            "Sim-Deck Classroom 2B (Homeroom)",
            "Cyber-Theory Room 201 (Homeroom)",
            "Tactical Analytics Lab (Homeroom)",
            "Neural Interface Room 3A (Homeroom)"
        ]
        if hash_val is not None:
            return scifi_classes[(hash_val * 17 + 5) % len(scifi_classes)]
        return random.choice(scifi_classes)

    # High School Drama / Modern
    if hash_val is not None:
        return CLASSROOM_NAMES[(hash_val * 29 + 13) % len(CLASSROOM_NAMES)]
    return random.choice(CLASSROOM_NAMES)


PARK_NAME_PREFIXES = [
    # Japanese / Anime inspired
    "Sakuragaoka", "Komorebi", "Hanamizuki", "Mizuho", "Shiranui", "Tachibana", "Kasumigaoka",
    "Shinonome", "Asahi", "Suzuran", "Hanazono", "Hoshizora", "Fujimi", "Tsukimori",
    # Western / Classical / Picturesque
    "Greenwood", "Maple Grove", "Willow Creek", "Riverside", "Sunnyside", "Oakridge",
    "Peace Memorial", "Springwater", "Meadowbrook", "Central City", "Fairview", "Briarwood",
    "Silver Lake", "Crestview", "Pinewood", "Briarcliff", "Rosewood", "Brookside"
]

PARK_NAME_SUFFIXES = [
    "Park",
    "Riverside Park",
    "Memorial Park",
    "Community Park",
    "Gardens",
    "Greenway",
    "Public Park"
]


def generate_park_name(scenario: str = "high_school_drama", hash_val: int = None) -> str:
    """Generates a dynamic, scenario-appropriate park or garden name."""
    scen = str(scenario or "high_school_drama").lower().strip()

    if "fantasy" in scen or "isekai" in scen:
        fantasy_prefixes = ["Moonlight", "Elderwood", "Starlight", "Silverleaf", "Sunlit Meadow", "Crystal Spring", "Grand Botanical", "Celestia", "Sylvan"]
        fantasy_suffixes = ["Gardens", "Grove Commons", "Sanctuary Park", "Botanical Grounds", "Memorial Plaza", "Public Park"]
        if hash_val is not None:
            p = fantasy_prefixes[(hash_val * 23 + 7) % len(fantasy_prefixes)]
            s = fantasy_suffixes[(hash_val * 37 + 13) % len(fantasy_suffixes)]
            return f"{p} {s}"
        return f"{random.choice(fantasy_prefixes)} {random.choice(fantasy_suffixes)}"

    if "cyberpunk" in scen:
        cp_names = [
            "Sector 4 Sky Garden", "Neon Hologram Plaza Park", "Cyber-Arboretum",
            "Nexus Bio-Dome Park", "Monolith Promenade Park", "Vanguard Bio-Sphere Park",
            "Neo-Kyoto Sky Park", "Apex Central Park"
        ]
        if hash_val is not None:
            return cp_names[(hash_val * 19 + 11) % len(cp_names)]
        return random.choice(cp_names)

    if "sci_fi" in scen or "space" in scen:
        scifi_names = [
            "Station Hydroponic Arboretum", "Orbital Bio-Sphere Park", "Promenade Commons",
            "Centrifuge Botanical Park", "Colony Dome Park", "Orion Plaza Gardens"
        ]
        if hash_val is not None:
            return scifi_names[(hash_val * 19 + 11) % len(scifi_names)]
        return random.choice(scifi_names)

    if "post_apocalypse" in scen or "apocalypse" in scen:
        apoc_names = [
            "Overgrown Crater Grove", "Rust-Valley Oasis", "Wasteland Botanical Ruins",
            "Survivor's Memorial Park", "Sunken Valley Greenery"
        ]
        if hash_val is not None:
            return apoc_names[(hash_val * 19 + 11) % len(apoc_names)]
        return random.choice(apoc_names)

    if "dark_fantasy" in scen or "grimdark" in scen:
        df_names = [
            "Weeping Willow Grove", "Blackwood Memorial Grounds", "Forgotten Abbey Gardens",
            "Gallows Hill Commons", "Mourning Cloak Park"
        ]
        if hash_val is not None:
            return df_names[(hash_val * 19 + 11) % len(df_names)]
        return random.choice(df_names)

    # High School Drama / Slice of life / Modern
    if hash_val is not None:
        p = PARK_NAME_PREFIXES[(hash_val * 23 + 7) % len(PARK_NAME_PREFIXES)]
        s = PARK_NAME_SUFFIXES[(hash_val * 37 + 13) % len(PARK_NAME_SUFFIXES)]
        return f"{p} {s}"
    return f"{random.choice(PARK_NAME_PREFIXES)} {random.choice(PARK_NAME_SUFFIXES)}"


SCHOOL_ATHLETICS_NAMES = [
    "School Grounds & Athletics",
    "Varsity Athletics Complex & Stadium",
    "Campus Athletic Pavilion & Fieldhouse",
    "Sports Grounds & Stadium Complex",
    "Varsity Training Grounds & Pavilion",
    "Olympic Athletic Complex",
]

SCHOOL_COMMONS_NAMES = [
    "Student Commons & Central Plaza",
    "Central Courtyard & Dining Plaza",
    "Campus Promenade & Student Commons",
    "Sunlit Commons & Central Plaza",
    "Student Plaza & Dining Pavilion",
]

SCHOOL_ARTS_WING_NAMES = [
    "Cultural Arts & Student Union",
    "Creative Arts & Student Union Wing",
    "Student Activities Center & Arts Wing",
    "Cultural Union & Performing Arts Annex",
    "Fine Arts & Student Union Hall",
]

SCHOOL_ABANDONED_WING_NAMES = [
    "Abandoned Old Campus Building",
    "Decaying Clock Tower & Heritage Wing",
    "Old Showa Campus Annex",
    "Forgotten Clock Tower Wing",
    "Derelict Old Campus Wing",
]


def generate_school_athletics_name(scenario: str = "high_school_drama", hash_val: int = None) -> str:
    """Generates a dynamic scenario-appropriate school athletics zone name."""
    if hash_val is not None:
        return SCHOOL_ATHLETICS_NAMES[(hash_val * 23 + 5) % len(SCHOOL_ATHLETICS_NAMES)]
    return random.choice(SCHOOL_ATHLETICS_NAMES)


def generate_school_commons_name(scenario: str = "high_school_drama", hash_val: int = None) -> str:
    """Generates a dynamic scenario-appropriate student commons & central plaza zone name."""
    if hash_val is not None:
        return SCHOOL_COMMONS_NAMES[(hash_val * 17 + 7) % len(SCHOOL_COMMONS_NAMES)]
    return random.choice(SCHOOL_COMMONS_NAMES)


def generate_school_arts_wing_name(scenario: str = "high_school_drama", hash_val: int = None) -> str:
    """Generates a dynamic scenario-appropriate cultural arts & student union zone name."""
    if hash_val is not None:
        return SCHOOL_ARTS_WING_NAMES[(hash_val * 19 + 11) % len(SCHOOL_ARTS_WING_NAMES)]
    return random.choice(SCHOOL_ARTS_WING_NAMES)


def generate_school_abandoned_wing_name(scenario: str = "high_school_drama", hash_val: int = None) -> str:
    """Generates a dynamic scenario-appropriate abandoned old campus zone name."""
    if hash_val is not None:
        return SCHOOL_ABANDONED_WING_NAMES[(hash_val * 29 + 13) % len(SCHOOL_ABANDONED_WING_NAMES)]
    return random.choice(SCHOOL_ABANDONED_WING_NAMES)



def generate_player_residence_name(char_name: str = "", scenario: str = "high_school_drama", hash_val: int = None) -> str:
    """Generates a dynamic, scenario-tailored residence name for the player."""
    clean = str(char_name or "").strip()
    scen = str(scenario or "high_school_drama").lower().strip()

    if clean:
        # Strip trailing possessive or words if already formatted
        if clean.lower().endswith(" residence") or clean.lower().endswith(" house") or clean.lower().endswith(" apartment"):
            return clean
        if clean.endswith("'s") or clean.endswith("’s"):
            clean = clean[:-2].strip()

        parts = clean.split()
        if len(parts) >= 2:
            surname = parts[-1]
            first_name = parts[0]
            if "cyberpunk" in scen:
                return f"{surname} Residence" if hash_val and hash_val % 2 == 0 else f"{first_name}'s Apartment"
            if "sci_fi" in scen or "space" in scen:
                return f"{first_name}'s Living Quarters"
            if "fantasy" in scen or "isekai" in scen:
                return f"{surname} Residence" if hash_val and hash_val % 2 == 0 else f"{first_name}'s Cottage"
            # High School / Modern: alternate between "[Surname] Residence" and "[First]'s House"
            if hash_val is not None:
                return f"{surname} Residence" if (hash_val % 2 == 0) else f"{first_name}'s House"
            return f"{surname} Residence"
        else:
            if "cyberpunk" in scen:
                return f"{clean}'s Apartment"
            if "sci_fi" in scen or "space" in scen:
                return f"{clean}'s Living Quarters"
            if "fantasy" in scen or "isekai" in scen:
                return f"{clean}'s Cottage"
            return f"{clean}'s House"

    if "cyberpunk" in scen:
        return "Megabuilding Apartment"
    if "sci_fi" in scen or "space" in scen:
        return "Crew Living Quarters"
    if "fantasy" in scen or "isekai" in scen:
        return "Your Cottage"
    return "Player's House"


def generate_npc_residence_name(npc_name: str, scenario: str = "high_school_drama", hash_val: int = None) -> str:
    """Generates an authentic NPC residence name (e.g. 'Kana's House' or 'Watanabe Residence')."""
    clean = str(npc_name or "").strip()
    scen = str(scenario or "high_school_drama").lower().strip()
    if not clean:
        return "Friend's House"

    if clean.lower().endswith(" residence") or clean.lower().endswith(" house") or clean.lower().endswith(" apartment") or clean.lower().endswith(" manor") or clean.lower().endswith(" cottage"):
        return clean
    if clean.endswith("'s") or clean.endswith("’s"):
        clean = clean[:-2].strip()

    parts = clean.split()
    if len(parts) >= 2:
        surname = parts[-1]
        first_name = parts[0]
        if "fantasy" in scen or "isekai" in scen:
            return f"{surname} Manor" if hash_val and hash_val % 2 == 0 else f"{first_name}'s Cottage"
        if "cyberpunk" in scen:
            return f"{surname} Residence" if hash_val and hash_val % 2 == 0 else f"{first_name}'s Apartment"
        if hash_val is not None:
            return f"{surname} Residence" if (hash_val % 2 == 0) else f"{first_name}'s House"
        return f"{surname} Residence"
    else:
        if "fantasy" in scen or "isekai" in scen:
            return f"{clean}'s Cottage"
        if "cyberpunk" in scen:
            return f"{clean}'s Apartment"
        return f"{clean}'s House"


def generate_kingdom_name(scenario: str = "fantasy", hash_val: int = None) -> str:
    """Generates a majestic fantasy kingdom / realm name."""
    prefixes = [
        "Aeloria", "Valerius", "Elyria", "Astrid", "Aldoria", "Highspire", "Solaria",
        "Vaeloria", "Drakensberg", "Eldoria", "Lunaria", "Aethelgard", "Gondoril", "Kaelen"
    ]
    if hash_val is not None:
        return prefixes[(hash_val * 31 + 7) % len(prefixes)]
    return random.choice(prefixes)


def generate_forest_name(scenario: str = "fantasy", hash_val: int = None) -> str:
    """Generates an evocative regular forest / woods name with varied naming structures."""
    adjectives = [
        "Whispering", "Greenvale", "Emerald", "Pinecrest", "Sylvan", "Silverwood",
        "Sunlit", "Twilight", "Riverwood", "Briarwood", "Oakridge", "Timberveil", "Mosswood"
    ]
    nouns = ["Silverleaf", "Greenwood", "Twilight Whispers", "The Sylvan Glade", "Pinecrest", "Emerald Mist", "Sunlit Vale"]
    suffixes = ["Woods", "Forest", "Thicket", "Grove", "Wilds", "Timberlands", "Copse"]
    
    if hash_val is not None:
        pattern_mode = (hash_val * 7 + 3) % 3
        a = adjectives[(hash_val * 17 + 11) % len(adjectives)]
        s = suffixes[(hash_val * 29 + 5) % len(suffixes)]
        n = nouns[(hash_val * 13 + 7) % len(nouns)]
        clean_a = a[4:] if a.startswith("The ") else a
        if pattern_mode == 0:
            return f"{a} {s}"
        elif pattern_mode == 1:
            return f"Forest of {n}"
        else:
            return f"The {clean_a} {s}"
    
    pattern_mode = random.choice([0, 1, 2])
    if pattern_mode == 0:
        return f"{random.choice(adjectives)} {random.choice(suffixes)}"
    elif pattern_mode == 1:
        return f"Forest of {random.choice(nouns)}"
    a = random.choice(adjectives)
    clean_a = a[4:] if a.startswith("The ") else a
    return f"The {clean_a} {random.choice(suffixes)}"


def generate_ancient_forest_name(scenario: str = "fantasy", hash_val: int = None) -> str:
    """Generates a deep, mythic primeval ancient forest name with varied structures."""
    adjectives = [
        "Elderwood", "Primeval", "Ancient", "Forgotten", "Timeless", "Mistveil",
        "Ironwood", "Ethereal", "Starfall", "Primordial", "Gloomwood", "Arcane"
    ]
    lore_places = ["Eldoria", "Mistveil", "Starfall", "The Moonwell", "Primordial Roots", "The First Grove", "Ironwood Giants"]
    suffixes = ["Deep Woods", "Ancient Forest", "Old-Growth Wilds", "Primeval Grove", "Great Canopy", "Sanctuary Woods"]
    
    if hash_val is not None:
        pattern_mode = (hash_val * 11 + 5) % 3
        a = adjectives[(hash_val * 23 + 17) % len(adjectives)]
        s = suffixes[(hash_val * 41 + 13) % len(suffixes)]
        l = lore_places[(hash_val * 19 + 7) % len(lore_places)]
        clean_a = a[4:] if a.startswith("The ") else a
        if pattern_mode == 0:
            return f"{a} {s}"
        elif pattern_mode == 1:
            return f"Great Canopy of {l}"
        else:
            return f"The {clean_a} {s}"
            
    pattern_mode = random.choice([0, 1, 2])
    if pattern_mode == 0:
        return f"{random.choice(adjectives)} {random.choice(suffixes)}"
    elif pattern_mode == 1:
        return f"Great Canopy of {random.choice(lore_places)}"
    a = random.choice(adjectives)
    clean_a = a[4:] if a.startswith("The ") else a
    return f"The {clean_a} {random.choice(suffixes)}"


def generate_mountain_name(scenario: str = "fantasy", hash_val: int = None) -> str:
    """Generates a majestic mountain range name with varied structures."""
    prefixes = [
        "Frostpeak", "Dragonspine", "Thunderhead", "Ironhorn", "Stormwatch",
        "Cloudspire", "Skyreach", "Bloodcrag", "Shadowpeak", "Mistfall"
    ]
    suffixes = ["Mountains", "Range", "Peaks", "Crags", "Heights", "Ridge"]
    lore_peaks = ["Dragon's Spine", "Stormwatch", "The Cloudspire", "Thunderhead", "Mistfall", "The Skyreach", "Ironhorn"]
    
    if hash_val is not None:
        pattern_mode = (hash_val * 13 + 7) % 3
        p = prefixes[(hash_val * 23 + 13) % len(prefixes)]
        s = suffixes[(hash_val * 19 + 7) % len(suffixes)]
        lp = lore_peaks[(hash_val * 31 + 11) % len(lore_peaks)]
        clean_p = p[4:] if p.startswith("The ") else p
        if pattern_mode == 0:
            return f"{p} {s}"
        elif pattern_mode == 1:
            return f"Mountains of {lp}"
        else:
            return f"The {clean_p} {s}"
            
    pattern_mode = random.choice([0, 1, 2])
    if pattern_mode == 0:
        return f"{random.choice(prefixes)} {random.choice(suffixes)}"
    elif pattern_mode == 1:
        return f"Mountains of {random.choice(lore_peaks)}"
    p = random.choice(prefixes)
    clean_p = p[4:] if p.startswith("The ") else p
    return f"The {clean_p} {random.choice(suffixes)}"


def generate_desert_name(scenario: str = "fantasy", hash_val: int = None) -> str:
    """Generates a desert / arid biome name with varied structures."""
    prefixes = [
        "Sunscorched", "Golden", "Shifting", "Crimson", "Glass", "Ashen", "Mirage", "Endless", "Sunfire"
    ]
    suffixes = ["Sands", "Wastes", "Expanse", "Dunes", "Desert", "Dune Sea"]
    lore_deserts = ["Shifting Sands", "The Golden Mirage", "Sunscorched Glass", "The Ashen Dunes", "Crimson Mirage", "The Endless Sun"]
    
    if hash_val is not None:
        pattern_mode = (hash_val * 17 + 3) % 3
        p = prefixes[(hash_val * 37 + 19) % len(prefixes)]
        s = suffixes[(hash_val * 13 + 3) % len(suffixes)]
        ld = lore_deserts[(hash_val * 29 + 17) % len(lore_deserts)]
        clean_p = p[4:] if p.startswith("The ") else p
        if pattern_mode == 0:
            return f"{p} {s}"
        elif pattern_mode == 1:
            return f"Desert of {ld}"
        else:
            return f"The {clean_p} {s}"
            
    pattern_mode = random.choice([0, 1, 2])
    if pattern_mode == 0:
        return f"{random.choice(prefixes)} {random.choice(suffixes)}"
    elif pattern_mode == 1:
        return f"Desert of {random.choice(lore_deserts)}"
    p = random.choice(prefixes)
    clean_p = p[4:] if p.startswith("The ") else p
    return f"The {clean_p} {random.choice(suffixes)}"


def generate_swamp_name(scenario: str = "fantasy", hash_val: int = None) -> str:
    """Generates a swamp / marsh biome name with varied structures."""
    prefixes = [
        "Plague-Blighted", "Black Mire", "Witch-Mist", "Murkwater", "Sunken",
        "Rotwood", "Serpent's Tongue", "Gloom-Bog", "Vapor", "Venom-Root"
    ]
    suffixes = ["Marshes", "Swamp", "Fens", "Mire", "Bogs"]
    lore_swamps = ["Murkwater", "The Serpent's Coil", "The Witch's Hollow", "Sunken Rotwood", "The Black Mire", "Gloom-Bog"]
    
    if hash_val is not None:
        pattern_mode = (hash_val * 19 + 11) % 3
        p = prefixes[(hash_val * 29 + 17) % len(prefixes)]
        s = suffixes[(hash_val * 31 + 11) % len(suffixes)]
        ls = lore_swamps[(hash_val * 23 + 5) % len(lore_swamps)]
        clean_p = p[4:] if p.startswith("The ") else p
        if pattern_mode == 0:
            return f"{p} {s}"
        elif pattern_mode == 1:
            return f"Marshes of {ls}"
        else:
            return f"The {clean_p} {s}"
            
    pattern_mode = random.choice([0, 1, 2])
    if pattern_mode == 0:
        return f"{random.choice(prefixes)} {random.choice(suffixes)}"
    elif pattern_mode == 1:
        return f"Marshes of {random.choice(lore_swamps)}"
    p = random.choice(prefixes)
    clean_p = p[4:] if p.startswith("The ") else p
    return f"The {clean_p} {random.choice(suffixes)}"


def generate_plains_name(scenario: str = "fantasy", hash_val: int = None) -> str:
    """Generates an idyllic farmlands / plains biome name with varied structures."""
    prefixes = [
        "Amberfield", "Golden Valley", "Sunreach", "Greenmeadow", "Harvest-Vale",
        "Windward", "Briar-Plain", "Highland Vale", "Riverbend", "Oatgrass", "Sweetmeadow"
    ]
    suffixes = ["Farmlands & Plains", "Pastures & Fields", "Agrarian Valley", "Wheatfields & Plains", "Country Plains"]
    lore_valleys = ["Sunreach", "Amberfield", "The Golden Vale", "Harvest-Vale", "Greenmeadow", "Riverbend", "The High Plains"]
    
    if hash_val is not None:
        pattern_mode = (hash_val * 23 + 13) % 4
        p = prefixes[(hash_val * 19 + 7) % len(prefixes)]
        s = suffixes[(hash_val * 23 + 13) % len(suffixes)]
        lv = lore_valleys[(hash_val * 31 + 17) % len(lore_valleys)]
        clean_p = p[4:] if p.startswith("The ") else p
        if pattern_mode == 0:
            return f"{p} {s}"
        elif pattern_mode == 1:
            return f"Plains of {lv}"
        elif pattern_mode == 2:
            return f"Fields of {lv}"
        else:
            return f"The {clean_p} {s}"
            
    pattern_mode = random.choice([0, 1, 2, 3])
    if pattern_mode == 0:
        return f"{random.choice(prefixes)} {random.choice(suffixes)}"
    elif pattern_mode == 1:
        return f"Plains of {random.choice(lore_valleys)}"
    elif pattern_mode == 2:
        return f"Fields of {random.choice(lore_valleys)}"
    p = random.choice(prefixes)
    clean_p = p[4:] if p.startswith("The ") else p
    return f"The {clean_p} {random.choice(suffixes)}"


def generate_harbor_name(scenario: str = "fantasy", hash_val: int = None) -> str:
    """Generates a bustling coastal harbor / port town name with varied structures."""
    prefixes = [
        "Port Silverwind", "Blackanchor", "Tidehaven", "Seagull Cove", "Saltbreeze",
        "Mermaid's Quay", "Stormbay", "Azure Coast", "Pelican Pier", "Dredgeport", "Coralreach"
    ]
    suffixes = ["Harbor Town", "Trading Port", "Seaport & Docks", "Maritime Bay", "Coastal Haven"]
    lore_ports = ["Silverwind", "Blackanchor", "Tidehaven", "The Azure Coast", "Mermaid's Quay", "Stormbay"]
    
    if hash_val is not None:
        pattern_mode = (hash_val * 29 + 17) % 3
        p = prefixes[(hash_val * 31 + 17) % len(prefixes)]
        s = suffixes[(hash_val * 17 + 5) % len(suffixes)]
        lp = lore_ports[(hash_val * 19 + 11) % len(lore_ports)]
        clean_p = p[4:] if p.startswith("The ") else p
        if pattern_mode == 0:
            return f"{p} {s}"
        elif pattern_mode == 1:
            return f"Port of {lp}"
        else:
            return f"The {clean_p} {s}"
            
    pattern_mode = random.choice([0, 1, 2])
    if pattern_mode == 0:
        return f"{random.choice(prefixes)} {random.choice(suffixes)}"
    elif pattern_mode == 1:
        return f"Port of {random.choice(lore_ports)}"
    p = random.choice(prefixes)
    clean_p = p[4:] if p.startswith("The ") else p
    return f"The {clean_p} {random.choice(suffixes)}"


def generate_tundra_name(scenario: str = "fantasy", hash_val: int = None) -> str:
    """Generates a freezing snow / glacial tundra biome name with varied structures."""
    prefixes = [
        "Frostfell", "Glacial Drift", "Everwinter", "Blizzard-Reach", "Rimewind",
        "Icepeak", "Frostbite", "Aurora-Glow", "Shiverstone", "Winterveil"
    ]
    suffixes = ["Tundra & Snow", "Glacial Expanse", "Frozen Wastes", "Ice Plains", "Permafrost Wilderness"]
    lore_tundras = ["Frostfell", "Everwinter", "The Rimewind", "The Glacial Drift", "Winterveil", "The Shiverstone"]
    
    if hash_val is not None:
        pattern_mode = (hash_val * 31 + 19) % 3
        p = prefixes[(hash_val * 37 + 11) % len(prefixes)]
        s = suffixes[(hash_val * 29 + 19) % len(suffixes)]
        lt = lore_tundras[(hash_val * 23 + 7) % len(lore_tundras)]
        clean_p = p[4:] if p.startswith("The ") else p
        if pattern_mode == 0:
            return f"{p} {s}"
        elif pattern_mode == 1:
            return f"Wastes of {lt}"
        else:
            return f"The {clean_p} {s}"
            
    pattern_mode = random.choice([0, 1, 2])
    if pattern_mode == 0:
        return f"{random.choice(prefixes)} {random.choice(suffixes)}"
    elif pattern_mode == 1:
        return f"Wastes of {random.choice(lore_tundras)}"
    p = random.choice(prefixes)
    clean_p = p[4:] if p.startswith("The ") else p
    return f"The {clean_p} {random.choice(suffixes)}"


def generate_volcano_name(scenario: str = "fantasy", hash_val: int = None) -> str:
    """Generates a volcanic / molten ashlands biome name with varied structures."""
    prefixes = [
        "Cinder-Reach", "Ashen Waste", "Infernal Caldera", "Brimstone", "Black-Fire",
        "Magma-Vein", "Obsidian-Crag", "Hellfire", "Charcoal", "Pyre-Peak"
    ]
    suffixes = ["Ashlands & Caldera", "Volcanic Wastes", "Lava Fields", "Magma Ashlands", "Molten Craters"]
    lore_volcanoes = ["Infernal Flames", "Brimstone", "The Black Pyre", "Obsidian-Crag", "Cinder-Reach", "The Molten Core"]
    
    if hash_val is not None:
        pattern_mode = (hash_val * 37 + 23) % 3
        p = prefixes[(hash_val * 41 + 23) % len(prefixes)]
        s = suffixes[(hash_val * 13 + 7) % len(suffixes)]
        lv = lore_volcanoes[(hash_val * 17 + 13) % len(lore_volcanoes)]
        clean_p = p[4:] if p.startswith("The ") else p
        if pattern_mode == 0:
            return f"{p} {s}"
        elif pattern_mode == 1:
            return f"Caldera of {lv}"
        else:
            return f"The {clean_p} {s}"
            
    pattern_mode = random.choice([0, 1, 2])
    if pattern_mode == 0:
        return f"{random.choice(prefixes)} {random.choice(suffixes)}"
    elif pattern_mode == 1:
        return f"Caldera of {random.choice(lore_volcanoes)}"
    p = random.choice(prefixes)
    clean_p = p[4:] if p.startswith("The ") else p
    return f"The {clean_p} {random.choice(suffixes)}"


def generate_shadowlands_name(scenario: str = "fantasy", hash_val: int = None) -> str:
    """Generates a cursed / necrotic shadowlands biome name with varied structures."""
    prefixes = [
        "Shadowveil", "Necrotic Blight", "Dreadfall", "Mourning-Reach", "Gloomspire",
        "Barrow-Downs", "Soul-Grave", "Blighted Moors", "Corrupted Waste", "Nightfall"
    ]
    suffixes = ["Shadowlands & Ruins", "Blighted Waste", "Necropolis Grounds", "Cursed Moors", "Shadow Fens"]
    lore_shadows = ["Dreadfall", "Necrotic Blight", "Shadowveil", "The Barrow-Downs", "Soul-Grave", "Mourning-Reach"]
    
    if hash_val is not None:
        pattern_mode = (hash_val * 41 + 29) % 3
        p = prefixes[(hash_val * 29 + 13) % len(prefixes)]
        s = suffixes[(hash_val * 31 + 7) % len(suffixes)]
        ls = lore_shadows[(hash_val * 19 + 5) % len(lore_shadows)]
        clean_p = p[4:] if p.startswith("The ") else p
        if pattern_mode == 0:
            return f"{p} {s}"
        elif pattern_mode == 1:
            return f"Shadowlands of {ls}"
        else:
            return f"The {clean_p} {s}"
            
    pattern_mode = random.choice([0, 1, 2])
    if pattern_mode == 0:
        return f"{random.choice(prefixes)} {random.choice(suffixes)}"
    elif pattern_mode == 1:
        return f"Shadowlands of {random.choice(lore_shadows)}"
    p = random.choice(prefixes)
    clean_p = p[4:] if p.startswith("The ") else p
    return f"The {clean_p} {random.choice(suffixes)}"


def generate_caves_name(scenario: str = "fantasy", hash_val: int = None) -> str:
    """Generates a subterranean crystal cave network biome name with varied structures."""
    prefixes = [
        "Glow-Crystal", "Subterranean Echo", "Abyssal Stone", "Dark-Grotto", "Stalactite-Hollow",
        "Blind-Chasm", "Glimmer-Depths", "Riven-Rock", "Shadow-Cavern", "Luminescent"
    ]
    suffixes = ["Cave Network", "Crystal Caverns", "Subterranean Tunnels", "Deep Grottos", "Stone Depths"]
    lore_caves = ["Glow-Crystal", "The Glimmer-Depths", "Riven-Rock", "The Abyssal Depths", "Stalactite-Hollow", "The Blind Caverns"]
    
    if hash_val is not None:
        pattern_mode = (hash_val * 43 + 31) % 3
        p = prefixes[(hash_val * 23 + 19) % len(prefixes)]
        s = suffixes[(hash_val * 37 + 11) % len(suffixes)]
        lc = lore_caves[(hash_val * 29 + 13) % len(lore_caves)]
        clean_p = p[4:] if p.startswith("The ") else p
        if pattern_mode == 0:
            return f"{p} {s}"
        elif pattern_mode == 1:
            return f"Caverns of {lc}"
        else:
            return f"The {clean_p} {s}"
            
    pattern_mode = random.choice([0, 1, 2])
    if pattern_mode == 0:
        return f"{random.choice(prefixes)} {random.choice(suffixes)}"
    elif pattern_mode == 1:
        return f"Caverns of {random.choice(lore_caves)}"
    p = random.choice(prefixes)
    clean_p = p[4:] if p.startswith("The ") else p
    return f"The {clean_p} {random.choice(suffixes)}"


def generate_chasm_name(scenario: str = "fantasy", hash_val: int = None) -> str:
    """Generates a deep underworld abyss / chasm biome name with varied structures."""
    prefixes = [
        "Abyssal Rift", "The Great Void", "Black-Fissure", "Bioluminescent Trench",
        "Deep-Hollow", "Nether-Chasm", "Obsidian Trench", "Eldritch Fault", "Null-Chasm"
    ]
    suffixes = ["Underworld Chasm", "Abyssal Rift", "Subterranean Abyss", "Nether Trench", "Deep Fissure"]
    lore_chasms = ["The Great Void", "The Nether-Chasm", "The Obsidian Trench", "The Eldritch Rift", "The Black Fissure"]
    
    if hash_val is not None:
        pattern_mode = (hash_val * 47 + 37) % 3
        p = prefixes[(hash_val * 19 + 29) % len(prefixes)]
        s = suffixes[(hash_val * 41 + 17) % len(suffixes)]
        lch = lore_chasms[(hash_val * 31 + 7) % len(lore_chasms)]
        clean_p = p[4:] if p.startswith("The ") else p
        if pattern_mode == 0:
            return f"{p} {s}"
        elif pattern_mode == 1:
            return f"Chasm of {lch}"
        else:
            return f"The {clean_p} {s}"
            
    pattern_mode = random.choice([0, 1, 2])
    if pattern_mode == 0:
        return f"{random.choice(prefixes)} {random.choice(suffixes)}"
    elif pattern_mode == 1:
        return f"Chasm of {random.choice(lore_chasms)}"
    p = random.choice(prefixes)
    clean_p = p[4:] if p.startswith("The ") else p
    return f"The {clean_p} {random.choice(suffixes)}"


def generate_dungeon_name(scenario: str = "fantasy", hash_val: int = None) -> str:
    """Generates an ancient multi-level dungeon labyrinth biome name with varied structures."""
    prefixes = [
        "Forgotten Crypt", "Iron-Labyrinth", "Dread-Catacombs", "Sunken Vaults",
        "Titan's Tomb", "Runed-Gauntlet", "Cursed Labyrinth", "Obsidian Gauntlet", "Ancient Citadel"
    ]
    suffixes = ["Dungeon Complex", "Stone Labyrinth", "Ancient Catacombs", "Underground Vaults", "Trap Chambers"]
    lore_dungeons = ["The Forgotten Crypt", "The Titan's Tomb", "The Iron-Labyrinth", "The Sunken Vaults", "The Obsidian Gauntlet"]
    
    if hash_val is not None:
        pattern_mode = (hash_val * 53 + 41) % 3
        p = prefixes[(hash_val * 31 + 23) % len(prefixes)]
        s = suffixes[(hash_val * 29 + 5) % len(suffixes)]
        ld = lore_dungeons[(hash_val * 17 + 19) % len(lore_dungeons)]
        clean_p = p[4:] if p.startswith("The ") else p
        if pattern_mode == 0:
            return f"{p} {s}"
        elif pattern_mode == 1:
            return f"Labyrinth of {ld}"
        else:
            return f"The {clean_p} {s}"
            
    pattern_mode = random.choice([0, 1, 2])
    if pattern_mode == 0:
        return f"{random.choice(prefixes)} {random.choice(suffixes)}"
    elif pattern_mode == 1:
        return f"Labyrinth of {random.choice(lore_dungeons)}"
    p = random.choice(prefixes)
    clean_p = p[4:] if p.startswith("The ") else p
    return f"The {clean_p} {random.choice(suffixes)}"


def generate_cyber_city_name(scenario: str = "cyberpunk", hash_val: int = None) -> str:
    """Generates a high-tech cyberpunk city name."""
    prefixes = [
        "Neo-Veridia", "Night City", "New Kyoto", "Aegis Prime", "Apex Megacity",
        "Nova Kowloon", "Cyber-Vanguard", "Delta-9 Sprawl", "Chrono-Metropolis"
    ]
    if hash_val is not None:
        return prefixes[(hash_val * 41 + 13) % len(prefixes)]
    return random.choice(prefixes)


def generate_planet_name(biome_type: str = "", hash_val: int = None) -> str:
    """Generates an evocative sci-fi planet name."""
    roots = [
        "Zephyrus", "Aethelgard", "Vanguard", "Orion", "Xyron", "Chronos", "Aegis", "Solaria",
        "Tartarus", "Hyperion", "Glaciem", "Ignis", "Verdantia", "Nautilus", "Kryos", "Vesper"
    ]
    designations = ["Prime", "Secundus", "Major", "Minor", "IX", "IV", "VII", "Alpha", "Omega"]
    if hash_val is not None:
        b_offset = sum(ord(c) for c in biome_type) if biome_type else 0
        r = roots[(hash_val * 37 + b_offset * 13 + 11) % len(roots)]
        d = designations[(hash_val * 19 + b_offset * 7 + 7) % len(designations)]
        return f"Planet {r} {d}"
    return f"Planet {random.choice(roots)} {random.choice(designations)}"


def generate_space_station_name(hash_val: int = None) -> str:
    """Generates a sci-fi space station name."""
    prefixes = ["Orion Nebula", "Aegis Orbital", "Vanguard Gateway", "Nova Horizon", "Apex Centrifuge", "Chronos Citadel", "Starlight Nexus"]
    suffixes = ["Station Alpha", "Outpost 9", "Spire One", "Gateway", "Array Beta", "Command Hub"]
    if hash_val is not None:
        p = prefixes[(hash_val * 23 + 17) % len(prefixes)]
        s = suffixes[(hash_val * 31 + 5) % len(suffixes)]
        return f"{p} {s}"
    return f"{random.choice(prefixes)} {random.choice(suffixes)}"


def generate_airship_name(scenario: str = "steampunk", hash_val: int = None) -> str:
    """Generates a magnificent steampunk airship / zeppelin name."""
    prefixes = [
        "HMS Leviathan", "The Brass Sovereign", "The Zephyr Queen", "Gargantuan Ironclad",
        "The Celestial Kraken", "The Aether Dreadnought", "The Clockwork Titan", "The Storm Swallow"
    ]
    if hash_val is not None:
        return prefixes[(hash_val * 29 + 13) % len(prefixes)]
    return random.choice(prefixes)


def generate_seaside_name(scenario: str = "high_school_drama", hash_val: int = None) -> str:
    """Generates a scenic seaside / bay name."""
    prefixes = ["Minami", "Seaside", "Sunrise", "Shiranui", "Oceanview", "Coral", "Azure", "Kamome", "Shiokaze"]
    suffixes = ["Bay & Coastline", "Beach & Waterfront", "Coastal Pier & Bay", "Harbor Bay"]
    if hash_val is not None:
        p = prefixes[(hash_val * 17 + 7) % len(prefixes)]
        s = suffixes[(hash_val * 23 + 11) % len(suffixes)]
        return f"{p} {s}"
    return f"{random.choice(prefixes)} {random.choice(suffixes)}"


def generate_recreation_park_name(scenario: str = "high_school_drama", hash_val: int = None) -> str:
    """Generates a recreational forest / mountain park name."""
    prefixes = ["Mount Tsukimi", "Greenwood Forest", "Pinecrest", "Mount Asahi", "Misty Lake", "Cedar Ridge", "Komorebi Mountain"]
    suffixes = ["Recreational Park", "Nature Reserve & Trails", "Forest & Campsite Park", "Mountain Lookout Park"]
    if hash_val is not None:
        p = prefixes[(hash_val * 31 + 17) % len(prefixes)]
        s = suffixes[(hash_val * 19 + 5) % len(suffixes)]
        return f"{p} {s}"
    return f"{random.choice(prefixes)} {random.choice(suffixes)}"


def generate_cafe_name(scenario: str = "high_school_drama", hash_val: int = None) -> str:
    """Generates a charming café name."""
    names = [
        "Sunny Days Café", "Blue Velvet Café", "Café Monolith", "Sweet Romance Bakery & Café",
        "Starlight Coffee & Tea", "Komorebi Tea Lounge", "Manga & Brew Café", "Cat & Clover Café"
    ]
    if hash_val is not None:
        return names[(hash_val * 23 + 19) % len(names)]
    return random.choice(names)


def generate_arcade_name(scenario: str = "high_school_drama", hash_val: int = None) -> str:
    """Generates an energetic arcade center name."""
    names = [
        "Pixel Paradise Arcade", "CyberZone Game Center", "Neon Knights Arcade",
        "Supernova Game Lounge", "Chrono-Quest Arcade", "Retro Rumble Game Bar"
    ]
    if hash_val is not None:
        return names[(hash_val * 29 + 11) % len(names)]
    return random.choice(names)


def generate_ripperdoc_name(scenario: str = "cyberpunk", hash_val: int = None) -> str:
    """Generates a gritty ripperdoc clinic name."""
    names = [
        "Dr. Vance's Ripperdoc Clinic", "Chrome Spine Augmentations", "Neon Needle Clinic",
        "Apex Bio-Hardware Lab", "Dr. Kusanagi's Cyber-Ward", "Overclock Surgery Den"
    ]
    if hash_val is not None:
        return names[(hash_val * 31 + 7) % len(names)]
    return random.choice(names)


def generate_commercial_district_name(scenario: str = "high_school_drama", hash_val: int = None) -> str:
    """Generates an evocative commercial district / shopping promenade name."""
    prefixes = [
        "Sakuragaoka", "Ouka", "Minami", "Chuo", "Hanamizuki", "Tsukimi",
        "Komorebi", "Aoba", "Asahi", "Shin-Komiya", "Suzuran", "Midori"
    ]
    suffixes = [
        "Commercial Strip", "Commercial Promenade", "Commercial District",
        "Commercial Shopping Arcade", "Avenue Commercial Core", "Commercial Promenade & Plaza"
    ]
    if hash_val is not None:
        p = prefixes[(hash_val * 17 + 13) % len(prefixes)]
        s = suffixes[(hash_val * 23 + 7) % len(suffixes)]
        return f"{p} {s}"
    return f"{random.choice(prefixes)} {random.choice(suffixes)}"


def generate_residential_neighborhood_name(scenario: str = "high_school_drama", hash_val: int = None) -> str:
    """Generates a cozy suburban residential neighborhood name."""
    prefixes = [
        "Miyamae", "Sakura Hill", "Midori-cho", "Komorebi Heights", "Asahigaoka",
        "Hanamizuki", "Tsukimigaoka", "Kaede", "Wakaba", "Aobadai", "Hinata"
    ]
    suffixes = [
        "Residential Neighborhood", "Residential Suburban District", "Residential Quarter",
        "Residential Town", "Hillside Residential District"
    ]
    if hash_val is not None:
        p = prefixes[(hash_val * 29 + 11) % len(prefixes)]
        s = suffixes[(hash_val * 19 + 3) % len(suffixes)]
        return f"{p} {s}"
    return f"{random.choice(prefixes)} {random.choice(suffixes)}"


def generate_place_name(scenario: str = "fantasy") -> str:
    d = _get_scenario_data(scenario, "place")
    if not isinstance(d, dict):
        d = {}
    patterns = d.get("patterns") or ["{prefix}{suffix}"]
    pattern = random.choice(patterns)
    return pattern.format(
        prefix=random.choice(d.get("prefixes") or ["Ash"]),
        suffix=random.choice(d.get("suffixes") or ["wood"]),
        adjective=random.choice(d.get("adjectives") or ["Silent"]),
        noun=random.choice(d.get("nouns") or ["Keep"]),
    )


def _collect_tokens(value, found: set):
    if isinstance(value, str):
        for match in _TOKEN_RE.finditer(value):
            found.add(match.group(0))
    elif isinstance(value, list):
        for item in value:
            _collect_tokens(item, found)
    elif isinstance(value, dict):
        for item in value.values():
            _collect_tokens(item, found)


def _apply_mapping(value, mapping: dict):
    if isinstance(value, str):
        for token, name in mapping.items():
            if token in value:
                value = value.replace(token, name)
        return value
    if isinstance(value, list):
        return [_apply_mapping(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: _apply_mapping(v, mapping) for k, v in value.items()}
    return value


def _extract_gender_from_token(token: str) -> str:
    t = token.upper()
    if "_FEMALE" in t or "_WOMAN" in t or "_GIRL" in t or "_F_" in t or t.endswith("_F}}") or t.endswith("_F}"):
        return "female"
    if "_MALE" in t or "_MAN" in t or "_BOY" in t or "_M_" in t or t.endswith("_M}}") or t.endswith("_M}"):
        return "male"
    return ""


def resolve_tokens_deep(value, scenario: str = "fantasy"):
    """Find every distinct {{PERSON_n}}/{{PLACE_n}}/{{ROLE_n}}/{{SCHOOL_n}}/{{CLASSROOM_n}} (or single-brace {PERSON_n})
    token anywhere in a dict/list/str structure, roll one consistent name per distinct token
    matching the scenario's name pools, and substitute it everywhere. Safe
    to call on a full parsed LLM JSON response."""
    tokens = set()
    _collect_tokens(value, tokens)
    if not tokens:
        return value

    mapping = {}
    for token in tokens:
        t_clean = token.lstrip("{").rstrip("}").upper()
        if t_clean.startswith("PERSON"):
            gender = _extract_gender_from_token(token)
            mapping[token] = generate_person_name(scenario, gender=gender)
        elif t_clean.startswith("ROLE"):
            mapping[token] = generate_role(scenario)
        elif t_clean.startswith("SCHOOL"):
            mapping[token] = generate_school_name(scenario)
        elif t_clean.startswith("CLASSROOM"):
            mapping[token] = generate_classroom_name(scenario)
        elif t_clean.startswith("PARK"):
            mapping[token] = generate_park_name(scenario)
        else:
            mapping[token] = generate_place_name(scenario)
    res = _apply_mapping(value, mapping)
    if isinstance(res, dict):
        for ent in res.get("new_entities", []) or []:
            if isinstance(ent, dict) and str(ent.get("type", "person")).lower() == "person":
                if is_generic_role_name(ent.get("name")):
                    r_title = ent["name"]
                    p_name = generate_person_name(scenario, gender=ent.get("gender", ""))
                    ent["name"] = p_name
                    if r_title.lower() not in str(ent.get("description", "")).lower():
                        ent["description"] = f"{r_title} — {ent.get('description', '')}".strip(" —")
    return res


# ---------------------------------------------------------------- Procedural Faction Generation
def generate_faction_name(scenario: str, category: str = "") -> str:
    """Roll a thematic procedural faction name from namegen_data.json based on scenario and category."""
    import scenario_data
    scen_key = scenario or "fantasy"

    # Map scenario tags
    pool_key = "fantasy"
    if is_school_scenario(scen_key):
        pool_key = "high_school_drama"
    elif scenario_data.has_tag(scen_key, "cyberpunk"):
        pool_key = "cyberpunk"
    elif scenario_data.has_tag(scen_key, "steampunk"):
        pool_key = "steampunk"
    elif scenario_data.has_tag(scen_key, "post_apocalypse") or "apocalypse" in scen_key.lower():
        pool_key = "nuclear_post_apocalypse"
    elif scenario_data.has_tag(scen_key, "space") or scenario_data.has_tag(scen_key, "sci_fi"):
        pool_key = "sci_fi"
    elif scenario_data.has_tag(scen_key, "dark_fantasy") or scenario_data.has_tag(scen_key, "grimdark"):
        pool_key = "dark_fantasy"
    elif scenario_data.has_tag(scen_key, "isekai") or scenario_data.has_tag(scen_key, "isekai_fantasy"):
        pool_key = "isekai_fantasy"
    elif pool_key in _DATA:
        pool_key = scen_key

    fac_pools = _DATA.get(pool_key, {}).get("factions", {})
    if not fac_pools:
        fac_pools = _DATA.get("fantasy", {}).get("factions", {})

    if category and category in fac_pools and fac_pools[category]:
        return random.choice(fac_pools[category])

    # Fallback across all available categories in the pool
    all_names = []
    for cat_list in fac_pools.values():
        if isinstance(cat_list, list):
            all_names.extend(cat_list)

    if all_names:
        return random.choice(all_names)

    return f"The {category.capitalize() or 'Regional'} Syndicate"


def get_scenario_starter_factions(scenario: str, is_nsfw: bool = False) -> list[dict]:
    """
    Returns the list of pre-discovered starter factions for a scenario with
    fixed anchors for institutional factions and dynamic procedural names for gangs,
    secret societies, megacorps, and orders.
    """
    import scenario_data
    scen_key = scenario or "fantasy"
    factions: list[dict] = []
    used_names = set()

    def _unique_name(cat: str, target_scen: str = scen_key) -> str:
        for _ in range(20):
            candidate = generate_faction_name(target_scen, cat)
            if candidate not in used_names:
                used_names.add(candidate)
                return candidate
        return generate_faction_name(target_scen, cat)

    # 1. High School Drama / Slice of Life
    if is_school_scenario(scen_key):
        factions.append({
            "name": "Student Council",
            "hierarchy_template": "council",
            "category": "council",
            "hq_location_id": "Student Council Office",
            "notes": "The executive student governing body overseeing school affairs, budget allocation, campus events, and discipline policies."
        })
        factions.append({
            "name": "Drama Club",
            "hierarchy_template": "club",
            "category": "club",
            "hq_location_id": "School Auditorium Stage",
            "notes": "The theatrical club known for dramatic stage productions, expressive personalities, and lively campus social gossip."
        })
        factions.append({
            "name": "Occult & Mystery Club",
            "hierarchy_template": "club",
            "category": "club",
            "hq_location_id": "Old Storage Room 3-B",
            "notes": "An eccentric student club researching urban legends, campus ghost rumors, and unsolved school mysteries."
        })
        gang_name = _unique_name("delinquents", "high_school_drama")
        factions.append({
            "name": gang_name,
            "hierarchy_template": "delinquents",
            "category": "delinquents",
            "hq_location_id": "Behind Gym Storage Sheds",
            "notes": "A streetwise group of rebellious students and brawlers who operate outside campus rules."
        })
        if is_nsfw or scenario_data.is_nsfw_scenario(scen_key):
            nsfw_name = _unique_name("nsfw", "high_school_drama")
            factions.append({
                "name": nsfw_name,
                "hierarchy_template": "club",
                "category": "club",
                "hq_location_id": "Old East Wing Music Room",
                "notes": "An underground campus circle sharing private romantic rumors, intimate secrets, and after-hours rendezvous."
            })
        else:
            factions.append({
                "name": "Varsity Athletic Directorate",
                "hierarchy_template": "council",
                "category": "sports",
                "hq_location_id": "Main Gymnasium",
                "notes": "The competitive varsity athletics committee coordinating inter-school tournaments, team training regimens, and sports facility access."
            })


    # 2. Cyberpunk
    elif scenario_data.has_tag(scen_key, "cyberpunk"):
        corp1 = _unique_name("corpo", "cyberpunk")
        corp2 = _unique_name("corpo", "cyberpunk")
        syn = _unique_name("syndicate", "cyberpunk")
        gang = _unique_name("delinquents", "cyberpunk")
        factions.extend([
            {
                "name": corp1,
                "hierarchy_template": "corpo",
                "category": "corpo",
                "hq_location_id": "Corporate Plaza Tower",
                "notes": "A multi-trillion credit megacorporation controlling military cyberware, drone surveillance, and urban real estate."
            },
            {
                "name": corp2,
                "hierarchy_template": "corpo",
                "category": "corpo",
                "hq_location_id": "Biotech Research Complex",
                "notes": "A premier neuro-engineering and medical biotechnology conglomerate with immense political influence."
            },
            {
                "name": syn,
                "hierarchy_template": "syndicate",
                "category": "syndicate",
                "hq_location_id": "Subnet Data Haven",
                "notes": "An underground netrunner syndicate fighting corporate data monopolies and surveillance grids."
            },
            {
                "name": gang,
                "hierarchy_template": "delinquents",
                "category": "delinquents",
                "hq_location_id": "Neon Alley Hideout",
                "notes": "A heavily augmented street gang running the lower district black markets and smuggling corridors."
            }
        ])

    # 3. Steampunk
    elif scenario_data.has_tag(scen_key, "steampunk"):
        guild = _unique_name("guild", "steampunk")
        luddite = _unique_name("delinquents", "steampunk")
        union = _unique_name("syndicate", "steampunk")
        factions.extend([
            {
                "name": guild,
                "hierarchy_template": "guild",
                "category": "guild",
                "hq_location_id": "Grand Aether Observatory",
                "notes": "The premier society of steam mechanists, dirigible captains, and clockwork inventors."
            },
            {
                "name": luddite,
                "hierarchy_template": "delinquents",
                "category": "delinquents",
                "hq_location_id": "Abandoned Boiler Cellar",
                "notes": "A radical anti-automation movement protesting mechanization and industrial boiler smog."
            },
            {
                "name": union,
                "hierarchy_template": "syndicate",
                "category": "syndicate",
                "hq_location_id": "Foundry Workers Hall",
                "notes": "An organized labor confederation representing steamfitters, smelters, and locomotive workers."
            }
        ])

    # 4. Post-Apocalypse
    elif scenario_data.has_tag(scen_key, "post_apocalypse") or "apocalypse" in scen_key.lower():
        settle = _unique_name("settlement", "nuclear_post_apocalypse")
        raider = _unique_name("delinquents", "nuclear_post_apocalypse")
        trader = _unique_name("guild", "nuclear_post_apocalypse")
        factions.extend([
            {
                "name": settle,
                "hierarchy_template": "settlement",
                "category": "settlement",
                "hq_location_id": "Fortified Water Well Central",
                "notes": "A fortified survivor bastion organized around clean water, scrap defense, and agriculture."
            },
            {
                "name": raider,
                "hierarchy_template": "delinquents",
                "category": "delinquents",
                "hq_location_id": "Scrapyard Stronghold",
                "notes": "A ruthless motorized warband plundering scrap, fuel, and supplies along the wasteland highways."
            },
            {
                "name": trader,
                "hierarchy_template": "guild",
                "category": "guild",
                "hq_location_id": "Trading Post Crossroads",
                "notes": "A network of roaming traders bartering ammunition, salvaged pre-war tech, and water rations."
            }
        ])

    # 5. Space / Sci-Fi
    elif scenario_data.has_tag(scen_key, "space") or scenario_data.has_tag(scen_key, "sci_fi"):
        fleet = _unique_name("corpo", "sci_fi")
        miners = _unique_name("syndicate", "sci_fi")
        pirates = _unique_name("delinquents", "sci_fi")
        factions.extend([
            {
                "name": fleet,
                "hierarchy_template": "corpo",
                "category": "corpo",
                "hq_location_id": "Orbital Command Station",
                "notes": "The central fleet command managing interstellar jumpgates, orbital defense, and system patrols."
            },
            {
                "name": miners,
                "hierarchy_template": "syndicate",
                "category": "syndicate",
                "hq_location_id": "Asteroid Belt Outpost",
                "notes": "An independent guild of deep space asteroid miners and planetary prospectors."
            },
            {
                "name": pirates,
                "hierarchy_template": "delinquents",
                "category": "delinquents",
                "hq_location_id": "Hidden Nebula Base",
                "notes": "A notorious syndicate of space corsairs and starship raiders targeting unescorted freighters."
            }
        ])

    # 6. Fantasy / Dark Fantasy / Isekai (Default)
    else:
        arcane = _unique_name("order", scen_key if scen_key in _DATA else "fantasy")
        knights = _unique_name("order", scen_key if scen_key in _DATA else "fantasy")
        factions.append({
            "name": "Adventurers Guild",
            "hierarchy_template": "guild",
            "category": "guild",
            "hq_location_id": "Guildmaster's Hall",
            "notes": "The central hub for mercenary contracts, monster bounties, and dungeon exploration."
        })
        factions.append({
            "name": arcane,
            "hierarchy_template": "order",
            "category": "order",
            "hq_location_id": "High Arcane Spire",
            "notes": "An ancient order of mages, scholars, and spellcraft researchers maintaining magical equilibrium."
        })
        factions.append({
            "name": knights,
            "hierarchy_template": "order",
            "category": "order",
            "hq_location_id": "Citadel of the Sunlit Keep",
            "notes": "A righteous chivalric order sworn to protect the realm, defend the weak, and enforce the law."
        })

    return factions

