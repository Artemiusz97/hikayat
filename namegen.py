from __future__ import annotations
from typing import Any, Optional
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
_ALL_LAST_NAMES = set()
_ALL_EAST_ASIAN_SURNAMES = set()
_ALL_EAST_ASIAN_GIVEN_NAMES = set()
_NON_EA_GIVEN_NAMES = set()
_SURNAME_TO_CULTURE: dict[str, str] = {}
_FIRST_NAME_TO_CULTURE: dict[str, str] = {}

_EAST_ASIAN_CULTURE_KEYS = ("chinese", "japanese", "korean", "vietnamese")

for s_val in _DATA.values():
    if isinstance(s_val, dict) and "person" in s_val:
        p_dict = s_val["person"]
        if isinstance(p_dict, dict):
            if "cultures" in p_dict and isinstance(p_dict["cultures"], dict):
                for cult_key, cult_data in p_dict["cultures"].items():
                    if isinstance(cult_data, dict):
                        is_ea = cult_key in _EAST_ASIAN_CULTURE_KEYS
                        for n in cult_data.get("male", []):
                            n_low = str(n).lower().strip()
                            _ALL_MALE_NAMES.add(n_low)
                            _FIRST_NAME_TO_CULTURE.setdefault(n_low, cult_key)
                            if is_ea:
                                _ALL_EAST_ASIAN_GIVEN_NAMES.add(n_low)
                            else:
                                _NON_EA_GIVEN_NAMES.add(n_low)
                        for n in cult_data.get("female", []):
                            n_low = str(n).lower().strip()
                            _ALL_FEMALE_NAMES.add(n_low)
                            _FIRST_NAME_TO_CULTURE.setdefault(n_low, cult_key)
                            if is_ea:
                                _ALL_EAST_ASIAN_GIVEN_NAMES.add(n_low)
                            else:
                                _NON_EA_GIVEN_NAMES.add(n_low)
                        for n in cult_data.get("last", []):
                            n_low = str(n).lower().strip()
                            _ALL_LAST_NAMES.add(n_low)
                            _SURNAME_TO_CULTURE.setdefault(n_low, cult_key)
                            if is_ea:
                                _ALL_EAST_ASIAN_SURNAMES.add(n_low)
            for n in p_dict.get("male", []):
                _ALL_MALE_NAMES.add(str(n).lower().strip())
            for n in p_dict.get("female", []):
                _ALL_FEMALE_NAMES.add(str(n).lower().strip())
            for n in p_dict.get("last", []):
                _ALL_LAST_NAMES.add(str(n).lower().strip())

if "high_school_drama" in _DATA and "person" in _DATA["high_school_drama"]:
    hs_p = _DATA["high_school_drama"]["person"]
    for n in hs_p.get("last", []):
        n_low = str(n).lower().strip()
        if n_low == "smith":
            break
        _ALL_EAST_ASIAN_SURNAMES.add(n_low)
        _SURNAME_TO_CULTURE.setdefault(n_low, "japanese")
    for n in hs_p.get("male", []):
        n_low = str(n).lower().strip()
        if n_low in ("alex", "liam", "james"):
            break
        _ALL_EAST_ASIAN_GIVEN_NAMES.add(n_low)
        _FIRST_NAME_TO_CULTURE.setdefault(n_low, "japanese")
    for n in hs_p.get("female", []):
        n_low = str(n).lower().strip()
        if n_low in ("maya", "chloe", "emma", "mary"):
            break
        _ALL_EAST_ASIAN_GIVEN_NAMES.add(n_low)
        _FIRST_NAME_TO_CULTURE.setdefault(n_low, "japanese")

_SURNAME_TO_CULTURE.setdefault("sterling", "english")
_SURNAME_TO_CULTURE.setdefault("yamada", "japanese")
_SURNAME_TO_CULTURE.setdefault("vance", "english")
_SURNAME_TO_CULTURE.setdefault("halloway", "english")
_SURNAME_TO_CULTURE.setdefault("kowalski", "polish")

_ALL_ROLE_NAMES = set()
for s_val in _DATA.values():
    if isinstance(s_val, dict) and "roles" in s_val:
        for r in s_val.get("roles", []):
            if isinstance(r, str):
                _ALL_ROLE_NAMES.add(r.lower().strip())

_GENERIC_ROLE_PATTERNS = [
    r"^(student council|class|club|team|guild|order|gang|committee|department|faculty)\s+(president|vice president|treasurer|secretary|leader|captain|head|officer|member|lead|rep|representative|enforcer|brawler|scout|advisor|coordinator|director)(?:s|es)?$",
    r"^(headmaster|principal|vice principal|teacher|professor|instructor|tutor|librarian|counselor|advisor|dean|sensei|dorm warden|curator)(?:s|es)?$",
    r"^(guildmaster|shopkeeper|innkeeper|bartender|tavernkeeper|blacksmith|armorer|merchant|alchemist|apothecary|quartermaster|vendor|peddler|trader)(?:s|es)?$",
    r"^(guard|town guard|city guard|guard captain|captain of the guard|sentinel|watchman|watchmen|paladin commander|soldier|knight|grunt|patrol|enforcer)(?:s|es)?$",
    r"^(president|vice president|chairman|chairwoman|director|ceo|executive|manager|boss|chief|commander|warlord|gang boss|secretary|treasurer|rep|representative)(?:s|es)?$",
    r"^(class rep|class representative|hall monitor|discipline officer|prefect|student council member)(?:s|es)?$",
    r"^(drunken|noisy|rowdy|weary|curious|hooded|elderly|young|local|fellow|nearby|ambient|suspicious|shady|nervous|quiet|another)?\s*(patron|bystander|customer|citizen|civilian|traveler|onlooker|wanderer|adventurer|villager|townsperson|townspeople|townsfolk|student|classmate|bouncer|barkeep|waiter|waitress|maid|servant|minstrel|bard|drifter|dockworker|sailor|laborer|commoner|peasant)(?:s|es)?$",
    r"^(townsfolk|townspeople|watchmen|patrols|guards|soldiers|merchants|students|classmates|patrons|bystanders|customers|citizens|civilians|travelers|onlookers|wanderers|adventurers|villagers|clerks|locals|regulars|pedestrians|passersby)$",
    # Role word followed by descriptive participial or prepositional phrase:
    # e.g. "classmate seated nearby", "student sitting at desk", "patron standing by the counter"
    r"^(?:drunken|noisy|rowdy|weary|curious|hooded|elderly|young|local|fellow|nearby|ambient|suspicious|shady|nervous|quiet|another)?\s*(patron|bystander|customer|citizen|civilian|traveler|onlooker|wanderer|adventurer|villager|townsperson|townspeople|townsfolk|student|classmate|bouncer|barkeep|waiter|waitress|maid|servant|minstrel|bard|drifter|dockworker|sailor|laborer|commoner|peasant|guard|soldier|merchant|clerk|pedestrian|passerby)\s+(?:seated|sitting|standing|waiting|walking|passing|nearby|behind|at|in|across|by|on|listening|chatting|whispering|watching|looking|working)\b.*$",
    # Generic role with class/room/section identifier, e.g. "Classmate 2-B", "Student from Class 1-A"
    r"^(?:classmate|student|patron|guard|merchant)\s+(?:(?:from|in|of|seated in|at)\s+)?(?:(?:class|room|section|desk|table)\s+[\d\w\-_]+|\d+[\w\-_]*)$",
]
_GENERIC_ROLE_RE = [re.compile(p, re.IGNORECASE) for p in _GENERIC_ROLE_PATTERNS]

# Tokenized role / entity patterns like Classmate_2B, Student_1A, NPC_1, Person_2, Role_1, etc.
_TOKENIZED_ROLE_RE = re.compile(
    r"^(?:[a-z]+_\d+[a-z0-9_]*|(?:classmate|student|patron|npc|character|person|role|guard|bystander|merchant|villager)[\s_]+(?:[0-9]+[a-z0-9_\-]*|[a-z0-9_\-]+_[0-9]+[a-z0-9_\-]*))$",
    re.IGNORECASE
)

_COLLECTIVE_ENTITY_PATTERNS = [
    r"^(?:the\s+|a\s+|an\s+)?(?:cluster|group|crowd|throng|gathering|pack|horde|mob|circle|bunch|party|roomful|flock|herd|swarm)\s+(?:of\s+)?(?:[a-z0-9_\-]+\s*)*$",
    r"^(?:the\s+)?(?:students|classmates|patrons|customers|bystanders|citizens|civilians|townsfolk|townspeople|guards|soldiers|watchmen|crowd|audience|onlookers|passersby|pedestrians|locals|regulars|clerks|villagers|adventurers|wanderers|travelers|staff|faculty|merchants|shoppers|barkeeps|waiters|waitresses|guests|members|patrols|bandits|thugs|cultists|people|everyone|all of them|both of them)$",
]
_COLLECTIVE_ENTITY_RE = [re.compile(p, re.IGNORECASE) for p in _COLLECTIVE_ENTITY_PATTERNS]


def is_collective_entity_name(name: str) -> bool:
    """Checks if a string represents an ambient collective group, crowd, or plural entity rather than an individual person."""
    if not name:
        return False
    clean = str(name).strip().lower()
    clean = re.sub(r"^(the|a|an)\s+", "", clean).strip()
    clean = re.sub(r"[\(\[\{].*?[\)\]\}]", "", clean).strip()
    if not clean:
        return False
    for rx in _COLLECTIVE_ENTITY_RE:
        if rx.match(clean):
            return True
    return False


def is_generic_role_name(name: str) -> bool:
    """Checks if a string is a generic job title / role or descriptive role phrase rather than a personal character name."""
    if not name:
        return False
    raw_str = str(name).strip()
    if not raw_str:
        return False
    clean = raw_str.lower()
    # Check tokenized role patterns before stripping
    if _TOKENIZED_ROLE_RE.match(raw_str) or _TOKENIZED_ROLE_RE.match(clean):
        return True
    # Strip leading articles and bracketed tags like [NPC] or (Neutral)
    clean = re.sub(r"^(the|a|an)\s+", "", clean).strip()
    clean = re.sub(r"[\(\[\{].*?[\)\]\}]", "", clean).strip()
    if not clean:
        return False
    if is_collective_entity_name(clean):
        return True
    if clean in _ALL_ROLE_NAMES:
        return True
    if _TOKENIZED_ROLE_RE.match(clean):
        return True
    for rx in _GENERIC_ROLE_RE:
        if rx.match(clean):
            return True
    # Catch any descriptive phrase starting with indefinite article "a/an" followed by known role words
    if re.match(r"^(?:a|an)\s+(?:fellow|another|nearby|curious|nervous|quiet)?\s*(?:classmate|student|patron|bystander|customer|guard|merchant|citizen|civilian)\b", raw_str, re.IGNORECASE):
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
    # Reject tokenized names like Classmate_2B, Student_1A, NPC_1, Person_2
    if _TOKENIZED_ROLE_RE.match(clean):
        return False
    # Reject names starting with lowercase indefinite articles (e.g. "a classmate seated nearby", "an onlooker")
    if re.match(r"^(?:a|an)\s+", clean, re.IGNORECASE):
        return False
    # Reject known LLM meta-talk keywords and reasoning markers
    low = clean.lower()
    meta_keywords = (
        "wait -", "correcting", "providing full", "json", "requested output",
        "scene:", "scene_text", "outcome_narrative", "next_narrative",
        "turn summary", "action breakdown", "error:", "attributeerror",
        "undefined", "null", "none", "token", "person_", "role_", "placeholder",
        "actually providing", "consistency with", "classmate_", "student_", "npc_"
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

    if is_generic_role_name(text) or not is_valid_entity_name(text):
        return generate_person_name(scenario, gender=gender), text

    return text, ""


def sanitize_person_name(name: str, scenario: str = "fantasy", gender: str = "") -> str:
    """If name is a generic role title, generate an authentic personal name. Otherwise return name."""
    clean_name, _ = split_name_and_role(name, scenario=scenario, gender=gender)
    return clean_name


_TOKEN_RE = re.compile(r"\{{1,2}(PERSON|PLACE|ROLE|SCHOOL|CLASSROOM|PARK)(?:_\w+)?\}{1,2}", re.IGNORECASE)


def is_known_male_name(name: str) -> bool:
    """Checks if a given name or any token matches any known male name in namegen data."""
    if not name:
        return False
    clean = str(name).strip().lower()
    tokens = clean.split()
    return clean in _ALL_MALE_NAMES or any(t in _ALL_MALE_NAMES for t in tokens)


def is_known_female_name(name: str) -> bool:
    """Checks if a given name or any token matches any known female name in namegen data."""
    if not name:
        return False
    clean = str(name).strip().lower()
    tokens = clean.split()
    return clean in _ALL_FEMALE_NAMES or any(t in _ALL_FEMALE_NAMES for t in tokens)


NAME_PARTICLES_AND_HONORIFICS = {
    "bin", "binti", "ibn", "bint", "van", "von", "der", "den", "het", "ten", "ter",
    "del", "della", "degli", "das", "dos", "de", "la", "le", "el", "al", "the",
    "mr", "ms", "mrs", "miss", "mx", "dr", "prof", "professor", "madame", "madam", "sir",
    "dame", "lord", "lady", "captain", "officer", "constable", "detective", "inspector",
    "agent", "director", "commander", "ranger", "chef", "coach", "nurse", "principal",
    "headmaster", "headmistress", "dean", "sensei", "senpai", "elder", "druid", "scholar",
    "guardian", "warden", "father", "sister", "brother",
}

_HONORIFIC_PREFIXES = {
    "mr", "ms", "mrs", "miss", "mx", "dr", "prof", "professor", "madame", "madam",
    "sir", "dame", "lord", "lady", "captain", "officer", "constable", "detective",
    "inspector", "agent", "director", "commander", "ranger", "chef", "coach", "nurse",
    "principal", "headmaster", "headmistress", "dean", "sensei", "senpai", "elder",
    "guardian", "warden", "father", "sister", "brother",
}

_INDONESIAN_NON_PATRONYMIC_SURNAMES: frozenset[str] = frozenset({
    "saputra", "wijaya", "hidayat", "pratama", "kusuma", "santoso", "setiawan", "nasution",
})


def normalize_base_surname(surname: str) -> str:
    """Normalizes gender-inflected or patronymic-prefixed surnames back to their base canonical form
    (e.g. 'Kowalska' -> 'Kowalski', 'Semenova' -> 'Semenov', 'Magnusdottir' -> 'Magnusson', 'bin Ismail' -> 'Ismail')."""
    if not surname:
        return ""
    s = str(surname).strip()
    if not s:
        return ""
    parts = s.split()
    if len(parts) >= 2 and parts[0].lower() in ("bin", "binti"):
        s = " ".join(parts[1:]).strip()
    s_low = s.lower()
    if s_low in _ALL_LAST_NAMES:
        return s
    if s_low.endswith("ska") and len(s) > 4:
        if (s[:-3] + "skyi").lower() in _ALL_LAST_NAMES:
            return s[:-3] + "skyi"
        return s[:-3] + "ski"
    if s_low.endswith("cka") and len(s) > 4:
        return s[:-3] + "cki"
    if s_low.endswith("dzka") and len(s) > 5:
        return s[:-4] + "dzki"
    if s_low.endswith("skaya") and len(s) > 6:
        return s[:-5] + "sky"
    if s_low.endswith(("ova", "eva", "ina")) and len(s) > 4:
        if s[:-1].lower() in _ALL_LAST_NAMES or s_low.endswith(("ova", "eva")):
            return s[:-1]
    if s_low.endswith(("idou", "iadou")) and len(s) > 5:
        return s[:-2] + "is"
    if s_low.endswith("aki") and len(s) > 4 and (
        (s + "s").lower() in _ALL_LAST_NAMES
        or s_low.endswith(("daki", "laki", "naki", "maki", "raki", "taki", "kaki", "haki"))
    ):
        return s + "s"
    if s_low.endswith("ou") and len(s) > 4:
        if (s[:-2] + "os").lower() in _ALL_LAST_NAMES or s_low.endswith("poulou"):
            return s[:-2] + "os"
    if s_low.endswith("sdottir") and len(s) > 8:
        return s[:-7] + "sson"
    if s_low.endswith("dottir") and len(s) > 7:
        return s[:-6] + "son"
    return s


def infer_surname_culture(surname: str) -> str:
    """Infers the cultural pool for a surname (after normalizing inflections)."""
    if not surname:
        return ""
    s_raw = str(surname).lower().strip()
    if s_raw in _SURNAME_TO_CULTURE:
        return _SURNAME_TO_CULTURE[s_raw]
    base = normalize_base_surname(surname).lower().strip()
    if base in _SURNAME_TO_CULTURE:
        return _SURNAME_TO_CULTURE[base]
    if base in ("halloway", "sterling", "vance"):
        return "english"
    if base in _ALL_EAST_ASIAN_SURNAMES:
        return "japanese"
    s_low = str(surname).lower().strip()
    if s_low.endswith(("sdottir", "dottir", "sson")):
        return "icelandic"
    if s_low.endswith(("ski", "ska", "cki", "cka", "dzki", "dzka")):
        return "polish"
    if s_low.endswith(("skyi", "enko", "chuk")):
        return "ukrainian"
    if s_low.endswith(("ov", "ova", "ev", "eva", "skaya")):
        return "russian"
    if s_low.endswith(("opoulos", "opoulou", "akis", "idis", "idou", "iadis", "iadou")):
        return "greek"
    return ""


def infer_first_name_culture(first_name: str) -> str:
    """Infers the cultural pool for a given name."""
    if not first_name:
        return ""
    f_low = str(first_name).lower().strip()
    if f_low in _FIRST_NAME_TO_CULTURE:
        return _FIRST_NAME_TO_CULTURE[f_low]
    if f_low in _ALL_EAST_ASIAN_GIVEN_NAMES:
        return "japanese"
    return ""


def extract_first_and_last_name(full_name: str) -> tuple[str, str]:
    """Extracts (first_name, surname) respecting East Asian surname-first, patronymic, and compound surname conventions."""
    cleaned_full = re.sub(r"\s*\((?:née|nee)\s+[^)]*\)", "", str(full_name or ""), flags=re.IGNORECASE).strip()
    parts = cleaned_full.split()
    if not parts:
        return "", ""
    while len(parts) >= 2 and parts[0].lower().rstrip(".") in _HONORIFIC_PREFIXES:
        parts = parts[1:]
    if len(parts) == 1:
        p0_low = parts[0].lower()
        if (
            (p0_low in _ALL_LAST_NAMES or p0_low in _ALL_EAST_ASIAN_SURNAMES)
            and p0_low not in _ALL_MALE_NAMES
            and p0_low not in _ALL_FEMALE_NAMES
        ):
            return "", parts[0]
        if p0_low in _ALL_LAST_NAMES and p0_low not in (_ALL_MALE_NAMES | _ALL_FEMALE_NAMES):
            return "", parts[0]
        return parts[0], ""

    # Handle patronymic bin / binti: "Danial bin Ismail" -> first="Danial", last="Ismail"
    if len(parts) >= 3 and parts[1].lower() in ("bin", "binti"):
        return parts[0], " ".join(parts[2:])

    # Handle East Asian surname first: "Zhang Wei", "Tanaka Ren", "Kim Min-jun", "Zhang Chen"
    if len(parts) == 2 and parts[0].lower() in _ALL_EAST_ASIAN_SURNAMES:
        p0_low = parts[0].lower()
        p1_low = parts[1].lower()
        p1_base = normalize_base_surname(parts[1]).lower()
        is_p1_non_ea_surname = (
            (p1_low in _ALL_LAST_NAMES or p1_base in _ALL_LAST_NAMES)
            and p1_low not in _ALL_EAST_ASIAN_SURNAMES
            and p1_base not in _ALL_EAST_ASIAN_SURNAMES
        )
        if not is_p1_non_ea_surname:
            if p1_low in _ALL_EAST_ASIAN_GIVEN_NAMES and (
                p1_low not in _ALL_LAST_NAMES or p0_low not in _NON_EA_GIVEN_NAMES
            ):
                return parts[1], parts[0]

    # Standard Western / Compound surname: first="Elena", last="Vance Anderson" or "Smith"
    return parts[0], " ".join(parts[1:])


def infer_name_culture(full_name: str) -> str:
    """Infers the primary cultural pool from a full character name (handling East Asian order,
    honorifics, compound surnames, patronymics, and feminine surname inflections)."""
    if not full_name:
        return ""
    first, last = extract_first_and_last_name(full_name)
    if last:
        s_cult = infer_surname_culture(last)
        if s_cult:
            return s_cult
    if first:
        f_cult = infer_first_name_culture(first)
        if f_cult:
            return f_cult
    return ""


def get_given_name(full_name: str) -> str:
    """Returns the character's personal given name, stripping honorifics, patronymics, and (née ...),
    and respecting East Asian surname-first ordering."""
    if not full_name or not isinstance(full_name, str):
        return ""
    first, _ = extract_first_and_last_name(full_name)
    if first:
        return first
    cleaned = re.sub(r"\s*\((?:née|nee)\s+[^)]*\)", "", full_name, flags=re.IGNORECASE).strip()
    parts = cleaned.split()
    while len(parts) >= 2 and parts[0].lower().rstrip(".") in _HONORIFIC_PREFIXES:
        parts = parts[1:]
    return parts[0] if parts else ""


def format_formal_title(prefix: str, full_name: str) -> str:
    """Formats a culturally respectful formal title (e.g. 'Ms. Watanabe', 'Chef Watanabe',
    'Ms. Kowalska', 'Ms. Siti' for Malay patronymics, 'Ms. Birgitta' for Icelandic patronymics)."""
    p_clean = str(prefix or "").strip()
    n_clean = str(full_name or "").strip()
    if not p_clean:
        return n_clean
    if not n_clean:
        return p_clean
    first, last = extract_first_and_last_name(n_clean)
    padded_low = f" {n_clean.lower()} "
    is_malay_patronymic = (" bin " in padded_low) or (" binti " in padded_low)
    is_icelandic_patronymic = bool(last and infer_surname_culture(last) == "icelandic")
    if is_malay_patronymic or is_icelandic_patronymic:
        return f"{p_clean} {first or last}".strip()
    if last:
        return f"{p_clean} {last}".strip()
    return f"{p_clean} {first or n_clean}".strip()


def get_display_short_name(full_name: str, max_len: int = 15) -> str:
    """Returns a UI-safe compact display name that NEVER truncates to a bare honorific like 'Ms.' or 'Chef'."""
    n_clean = re.sub(r"\s*\((?:née|nee)\s+[^)]*\)", "", str(full_name or ""), flags=re.IGNORECASE).strip()
    if not n_clean:
        return "NPC"
    if len(n_clean) <= max_len:
        return n_clean
    parts = n_clean.split()
    if len(parts) >= 2 and parts[0].lower().rstrip(".") in _HONORIFIC_PREFIXES:
        formal = format_formal_title(parts[0], n_clean)
        if len(formal) <= max_len:
            return formal
    given = get_given_name(n_clean)
    if given and len(given) <= max_len:
        return given
    return (given or n_clean)[:max_len].strip()


_COMMON_ENGLISH_SHORT_STOPWORDS: frozenset[str] = frozenset({
    "in", "on", "at", "to", "an", "as", "by", "do", "go", "he", "hi", "if",
    "is", "it", "me", "my", "no", "of", "oh", "ok", "or", "so", "up", "us", "we",
    "and", "are", "but", "can", "did", "for", "get", "got", "had", "has", "her",
    "him", "his", "how", "its", "let", "man", "may", "new", "not", "now", "off",
    "old", "one", "our", "out", "own", "put", "ran", "run", "saw", "say", "see",
    "she", "sit", "son", "the", "too", "two", "use", "was", "way", "who", "why",
    "win", "won", "yes", "yet", "you",
})


def get_unique_person_tokens(full_name: str, peer_names: Any = None, min_len: int = 3) -> set[str]:
    """Returns lowercase name/phrase identifiers for `full_name` that safely distinguish them:
    - Never emits standalone honorifics ('ms.', 'dr.', 'coach', 'chef') or particles ('bin', 'van', 'de').
    - Includes given name (including 2-3 letter East Asian given names like 'ren', 'mei', 'wei', 'yui' unless common English stopword),
      surname, base full name (without honorific/née), and titled formal address ('ms. watanabe').
    - Automatically drops any shared token (e.g. shared family surname 'tanaka') that also belongs to another person in `peer_names`.
    """
    if not full_name or not isinstance(full_name, str):
        return set()

    def _raw_tokens_for(nm: str) -> set[str]:
        cleaned = re.sub(r"\s*\((?:née|nee)\s+[^)]*\)", "", str(nm or ""), flags=re.IGNORECASE).strip()
        if not cleaned:
            return set()
        out: set[str] = {cleaned.lower()}
        parts = cleaned.split()
        lead_prefix = ""
        if len(parts) >= 2 and parts[0].lower().rstrip(".") in _HONORIFIC_PREFIXES:
            lead_prefix = parts[0]
            without_hon = " ".join(parts[1:]).strip()
            if without_hon:
                out.add(without_hon.lower())
        first, last = extract_first_and_last_name(cleaned)
        if first:
            f_low = first.strip(".,'\"()[]{}").lower()
            eff_min = 2 if f_low in _ALL_EAST_ASIAN_GIVEN_NAMES else min_len
            if len(f_low) >= eff_min and f_low not in NAME_PARTICLES_AND_HONORIFICS and f_low not in _COMMON_ENGLISH_SHORT_STOPWORDS:
                out.add(f_low)
        if last:
            l_low = last.strip(".,'\"()[]{}").lower()
            if len(l_low) >= min_len and l_low not in NAME_PARTICLES_AND_HONORIFICS and l_low not in _COMMON_ENGLISH_SHORT_STOPWORDS:
                out.add(l_low)
            for lp in l_low.split():
                lp_c = lp.strip(".,'\"()[]{}")
                if len(lp_c) >= max(min_len, 3) and lp_c not in NAME_PARTICLES_AND_HONORIFICS and lp_c not in _COMMON_ENGLISH_SHORT_STOPWORDS:
                    out.add(lp_c)
        if lead_prefix:
            ft = format_formal_title(lead_prefix, cleaned).lower()
            if ft:
                out.add(ft)
                out.add(ft.replace(".", ""))
        return out

    my_clean = re.sub(r"\s*\((?:née|nee)\s+[^)]*\)", "", full_name, flags=re.IGNORECASE).strip().lower()
    my_tokens = _raw_tokens_for(full_name)
    if not peer_names:
        return my_tokens

    peer_shared: set[str] = set()
    for p in peer_names:
        p_str = p.get("name", "") if isinstance(p, dict) else str(p or "")
        p_clean = re.sub(r"\s*\((?:née|nee)\s+[^)]*\)", "", p_str, flags=re.IGNORECASE).strip().lower()
        if not p_clean or p_clean == my_clean:
            continue
        peer_shared |= _raw_tokens_for(p_str)

    # Always preserve the exact full name; drop ambiguous partial tokens shared with peers
    disambiguated = {t for t in my_tokens if t == my_clean or t not in peer_shared}
    disambiguated.add(full_name.strip().lower())
    return disambiguated


def get_substantive_name_tokens(full_name: str) -> list[str]:
    """Returns ordered substantive name tokens with the true given name first, excluding particles and honorifics."""
    if not full_name or not isinstance(full_name, str):
        return []
    first, last = extract_first_and_last_name(full_name)
    candidates = []
    if first:
        candidates.append(first)
    if last:
        for lp in last.split():
            candidates.append(lp)
    for raw_p in full_name.strip().split():
        candidates.append(raw_p)

    result = []
    seen = set()
    for tok in candidates:
        clean_t = tok.strip(".,'\"()[]{}")
        low_t = clean_t.lower()
        if len(clean_t) >= 2 and low_t not in NAME_PARTICLES_AND_HONORIFICS and low_t not in seen:
            seen.add(low_t)
            result.append(clean_t)
    return result


def get_all_gendered_names() -> tuple[set, set]:
    """Returns all precompiled male and female names from namegen data."""
    return set(_ALL_MALE_NAMES), set(_ALL_FEMALE_NAMES)


TAG_TO_NAMEGEN_KEY = {
    "modern": "default",
    "general_modern": "default",
    "anomalous_incursions": "default",
    "urban_fantasy": "default",
    "urban_anomalies": "default",
    "space": "sci_fi",
    "sci_fi": "sci_fi",
    "dark_fantasy": "dark_fantasy",
    "isekai": "isekai_fantasy",
    "isekai_fantasy": "isekai_fantasy",
    "high_school": "high_school_drama",
    "high_school_drama": "high_school_drama",
    "slice_of_life": "default",
    "post_apocalypse": "nuclear_post_apocalypse",
    "nuclear_post_apocalypse": "nuclear_post_apocalypse",
    "cyberpunk": "cyberpunk",
    "steampunk": "steampunk",
    "fantasy": "fantasy",
}


def get_scenario_cultures(scenario: str = "default") -> list[str]:
    """Returns the list of culture names available for a scenario, or empty list if none."""
    d = _get_scenario_data(scenario, "person")
    if isinstance(d, dict) and "cultures" in d and isinstance(d["cultures"], dict):
        return list(d["cultures"].keys())
    return []


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


CULTURE_ALIASES = {
    "russian/ukrainian": ["russian", "ukrainian"],
    "ukrainian/russian": ["russian", "ukrainian"],
    "east_slavic": ["russian", "ukrainian"],
    "scandinavian": ["swedish", "norwegian", "danish"],
    "scandinavia": ["swedish", "norwegian", "danish"],
    "nordic": ["swedish", "norwegian", "danish"],
    "malay/indo": ["malay"],
    "malay_indo": ["malay"],
    "indonesian": ["malay"],
    "indo": ["malay"],
    "portuguese/brazil": ["portuguese"],
    "brazilian": ["portuguese"],
    "brazil": ["portuguese"],
    "dutch & flemish": ["dutch"],
    "dutch/flemish": ["dutch"],
    "flemish": ["dutch"],
    "persian/iranian": ["persian"],
    "iranian": ["persian"],
    "scot": ["scottish"],
}


def format_cultural_full_name(
    first_name: str,
    surname: str,
    first_culture: str = "",
    surname_culture: str = "",
    gender: str = "",
    deterministic_seed: str | None = None,
    use_patronymic: bool | None = None,
    rng: Any = None,
) -> str:
    """Formats a cultural name according to ethnic naming rules, gender inflections,
    patronymics, and native East Asian surname-first ordering."""
    if not surname:
        return first_name
    if not first_name:
        return surname

    s_clean = normalize_base_surname(surname.strip())
    f_clean = first_name.strip()

    g = str(gender or "").lower().strip()
    is_female = any(w in g for w in ("female", "woman", "girl", "feminine", "she"))
    is_male = any(w in g for w in ("male", "man", "boy", "masculine", "he")) and not is_female
    if not is_female and not is_male:
        f_low = f_clean.lower()
        if f_low in _ALL_FEMALE_NAMES and f_low not in _ALL_MALE_NAMES:
            is_female = True

    s_cult = str(surname_culture or "").lower().strip() or infer_surname_culture(s_clean)
    f_cult = str(first_culture or "").lower().strip() or infer_first_name_culture(f_clean)

    # 1. Gendered surname inflections (grammatical gender follows the surname's culture)
    if is_female:
        if s_cult == "polish":
            if s_clean.endswith("ski"):
                s_clean = s_clean[:-3] + "ska"
            elif s_clean.endswith("cki"):
                s_clean = s_clean[:-3] + "cka"
            elif s_clean.endswith("dzki"):
                s_clean = s_clean[:-4] + "dzka"
        elif s_cult in ("russian", "slavic"):
            if s_clean.endswith(("ov", "ev", "in")):
                s_clean = s_clean + "a"
            elif s_clean.endswith("sky"):
                s_clean = s_clean[:-3] + "skaya"
        elif s_cult == "ukrainian":
            if s_clean.endswith("skyi"):
                s_clean = s_clean[:-4] + "ska"
        elif s_cult == "greek":
            if s_clean.endswith(("idis", "iadis")):
                s_clean = s_clean[:-2] + "ou"
            elif s_clean.endswith("akis"):
                s_clean = s_clean[:-1]
            elif s_clean.endswith("os"):
                s_clean = s_clean[:-2] + "ou"
        elif s_cult == "icelandic":
            if s_clean.endswith("sson"):
                s_clean = s_clean[:-4] + "sdottir"
            elif s_clean.endswith("son"):
                s_clean = s_clean[:-3] + "dottir"

    # 2. Malay & Indonesian patronymics (bin / binti)
    if s_cult == "malay":
        if use_patronymic is not None:
            include_patronymic = bool(use_patronymic)
        elif s_clean.lower() in _INDONESIAN_NON_PATRONYMIC_SURNAMES:
            include_patronymic = False
        elif deterministic_seed is not None:
            import hashlib
            h_val = int(hashlib.md5(str(deterministic_seed).encode("utf-8")).hexdigest(), 16)
            include_patronymic = (h_val % 2) == 0
        elif rng is not None:
            include_patronymic = (rng.random() < 0.5)
        else:
            include_patronymic = random.random() < 0.5
        if include_patronymic:
            particle = "binti" if is_female else "bin"
            return f"{f_clean} {particle} {s_clean}"
        return f"{f_clean} {s_clean}"

    # 3. East Asian & Vietnamese order
    east_asian_cultures = {"chinese", "japanese", "korean", "vietnamese"}
    if s_cult in east_asian_cultures:
        # Pure East Asian (both given name and surname are East Asian): Surname first
        if f_cult in east_asian_cultures:
            return f"{s_clean} {f_clean}"
        # Hybrid (e.g. English first + Chinese last): Western given name first
        return f"{f_clean} {s_clean}"

    # 4. Standard Western order (Given name first)
    return f"{f_clean} {s_clean}"


_HOMONYM_MODIFIER_TOKENS: frozenset[str] = frozenset({
    "long", "short", "tall", "high", "low", "deep", "wide", "broad", "narrow",
    "great", "grand", "big", "little", "small", "new", "old", "young",
    "north", "south", "east", "west", "upper", "lower", "inner", "outer",
    "front", "back", "central", "main", "mid", "middle", "far", "near",
    "dark", "bright", "light", "clear", "dim", "pale", "black", "white",
    "red", "green", "blue", "gray", "grey", "golden", "gold", "silver", "iron",
    "stone", "rock", "wood", "wooden", "glass", "brass", "copper", "bronze",
    "cold", "warm", "hot", "cool", "dry", "wet", "still", "silent", "quiet",
    "hidden", "lost", "open", "closed", "free", "safe", "cross", "royal",
})

_HOMONYM_PLACE_OBJECT_TOKENS: frozenset[str] = frozenset({
    "hall", "halls", "room", "rooms", "chamber", "chambers", "wing", "wings",
    "gate", "gates", "door", "doors", "wall", "walls", "tower", "towers",
    "bridge", "bridges", "court", "courts", "yard", "yards", "square",
    "street", "lane", "road", "way", "path", "alley", "walk", "cross", "crossing",
    "park", "garden", "gardens", "grove", "wood", "woods", "forest",
    "hill", "hills", "ridge", "peak", "cliff", "stone", "rock",
    "brook", "creek", "river", "lake", "pond", "well", "spring", "springs",
    "field", "fields", "meadow", "moor", "marsh", "dale", "glen", "vale",
    "bay", "cove", "port", "harbor", "haven", "point", "arch", "vault",
    "keep", "spire", "ward", "house", "mill", "forge", "bell", "post",
    "bank", "shore", "strand", "corridor", "lobby", "atrium", "plaza",
})


def is_spatial_or_object_homonym_name(name: str) -> bool:
    """Returns True when a two-token person name accidentally forms an English spatial/architectural phrase (e.g. 'Long Hall', 'West Wing', 'North Gate')."""
    if not name or not isinstance(name, str):
        return False
    tokens = [t.strip(".,'\"-").lower() for t in name.strip().split() if t.strip(".,'\"-")]
    if len(tokens) != 2:
        return False
    first_tok, second_tok = tokens[0], tokens[1]
    if first_tok == second_tok:
        return True
    if first_tok in _HOMONYM_MODIFIER_TOKENS and second_tok in _HOMONYM_PLACE_OBJECT_TOKENS:
        return True
    if first_tok in _HOMONYM_PLACE_OBJECT_TOKENS and second_tok in _HOMONYM_PLACE_OBJECT_TOKENS:
        return True
    return False


def generate_person_name(
    scenario: str = "fantasy",
    gender: str = "",
    cross_culture_chance: float | None = None,
    culture_weights: dict[str, float] | None = None,
    culture: str | None = None,
    seed: int | str | None = None,
) -> str:
    rng = random.Random(seed) if seed is not None else random

    d = _get_scenario_data(scenario, "person")
    cultures = d.get("cultures") if isinstance(d, dict) else None
    if not cultures:
        def_p = _get_scenario_data("default", "person")
        if isinstance(def_p, dict) and "cultures" in def_p:
            scen_low = str(scenario or "").lower()
            if any(k in scen_low for k in ("school", "academy", "modern", "slice_of_life", "default", "anomalous", "urban_fantasy", "urban_anomalies")):
                cultures = def_p.get("cultures")
                if not isinstance(d, dict):
                    d = {}
                if "cross_culture_chance" not in d:
                    d["cross_culture_chance"] = def_p.get("cross_culture_chance", 0.25)
                if "culture_weights" not in d:
                    d["culture_weights"] = def_p.get("culture_weights")

    # Culture-segregated name generation (e.g. modern / slice-of-life)
    if cultures and isinstance(cultures, dict):
        culture_keys = list(cultures.keys())
        if culture_keys:
            # 1. Select the base culture (determines surname/heritage)
            if culture:
                c_clean = str(culture).lower().strip()
                if c_clean in cultures:
                    base_culture = c_clean
                elif c_clean in CULTURE_ALIASES:
                    candidates = [c for c in CULTURE_ALIASES[c_clean] if c in cultures]
                    base_culture = rng.choice(candidates) if candidates else rng.choice(culture_keys)
                else:
                    base_culture = rng.choice(culture_keys)
            else:
                active_weights = culture_weights if culture_weights is not None else d.get("culture_weights")
                if active_weights and isinstance(active_weights, dict):
                    default_w = 1.0 if culture_weights is None else 0.0
                    weights = [float(active_weights.get(k, default_w)) for k in culture_keys]
                    if sum(weights) <= 0:
                        weights = [1.0] * len(culture_keys)
                    base_culture = rng.choices(culture_keys, weights=weights, k=1)[0]
                else:
                    base_culture = rng.choice(culture_keys)

            base_pool = cultures.get(base_culture) or {}

            # 2. Determine first name culture (intra-cultural vs cross-cultural)
            eff_cross_chance = (
                cross_culture_chance
                if cross_culture_chance is not None
                else float(d.get("cross_culture_chance", 0.25))
            )

            other_cultures = [c for c in culture_keys if c != base_culture]
            if other_cultures and rng.random() < eff_cross_chance:
                # Cross-cultural given name roll
                active_weights = culture_weights if culture_weights is not None else d.get("culture_weights")
                if active_weights and isinstance(active_weights, dict):
                    default_w = 1.0 if culture_weights is None else 0.0
                    other_weights = [float(active_weights.get(k, default_w)) for k in other_cultures]
                    if sum(other_weights) <= 0:
                        other_weights = [1.0] * len(other_cultures)
                    first_culture = rng.choices(other_cultures, weights=other_weights, k=1)[0]
                else:
                    first_culture = rng.choice(other_cultures)
            else:
                first_culture = base_culture

            first_pool = cultures.get(first_culture) or base_pool

            # 3. Select gender-appropriate first name
            g = str(gender or "").lower().strip()
            is_female = any(w in g for w in ("female", "woman", "girl", "feminine", "she"))
            is_male = any(w in g for w in ("male", "man", "boy", "masculine", "he")) and not is_female

            male_pool = first_pool.get("male") or []
            female_pool = first_pool.get("female") or []

            if is_female:
                pool = female_pool or ["Sarah"]
                resolved_gender = "female"
            elif is_male:
                pool = male_pool or ["Alex"]
                resolved_gender = "male"
            else:
                if male_pool and female_pool:
                    pool = rng.choice([male_pool, female_pool])
                    resolved_gender = "female" if pool is female_pool else "male"
                elif female_pool:
                    pool = female_pool
                    resolved_gender = "female"
                else:
                    pool = male_pool or ["Alex"]
                    resolved_gender = "male"

            first = rng.choice(pool)

            # 4. Determine surname from base_pool
            scen_low = str(scenario or "").lower()
            if any(k in scen_low for k in ("school", "academy", "modern", "cyberpunk", "noir", "anomalous", "urban_fantasy", "urban_anomalies")):
                surname_chance = 1.0
            else:
                surname_chance = float(d.get("surname_chance", 1.0))

            last_list = base_pool.get("last") or []
            if last_list and rng.random() < surname_chance:
                raw_surname = rng.choice(last_list)
                candidate = format_cultural_full_name(
                    first_name=first,
                    surname=raw_surname,
                    first_culture=first_culture,
                    surname_culture=base_culture,
                    gender=resolved_gender,
                    rng=rng,
                    deterministic_seed=str(seed) if seed is not None else None,
                )
                for _ in range(8):
                    if not is_spatial_or_object_homonym_name(candidate):
                        break
                    first = rng.choice(pool)
                    raw_surname = rng.choice(last_list)
                    candidate = format_cultural_full_name(
                        first_name=first,
                        surname=raw_surname,
                        first_culture=first_culture,
                        surname_culture=base_culture,
                        gender=resolved_gender,
                        rng=rng,
                        deterministic_seed=str(seed) if seed is not None else None,
                    )
                return candidate
            return first

    # Standard flat pool fallback (fantasy, dark_fantasy, sci-fi, etc.)
    male_pool = d.get("male") or []
    female_pool = d.get("female") or []

    g = str(gender or "").lower().strip()
    is_female = any(w in g for w in ("female", "woman", "girl", "feminine", "she"))
    is_male = any(w in g for w in ("male", "man", "boy", "masculine", "he")) and not is_female

    if is_female:
        pool = female_pool or ["Celestia"]
    elif is_male:
        pool = male_pool or ["Aldric"]
    else:
        if male_pool and female_pool:
            pool = rng.choice([male_pool, female_pool])
        else:
            pool = male_pool or female_pool or ["Aldric"]

    first = rng.choice(pool)
    scen_low = str(scenario or "").lower()
    if any(k in scen_low for k in ("school", "academy", "modern", "cyberpunk", "noir", "anomalous", "urban_fantasy", "urban_anomalies")):
        surname_chance = 1.0
    else:
        surname_chance = d.get("surname_chance", 0.5)
    last_list = d.get("last") or []
    if last_list and rng.random() < surname_chance:
        candidate = f"{first} {rng.choice(last_list)}"
        for _ in range(8):
            if not is_spatial_or_object_homonym_name(candidate):
                break
            first = rng.choice(pool)
            candidate = f"{first} {rng.choice(last_list)}"
        return candidate
    return first


def generate_person_name_with_surname(
    surname: str,
    scenario: str = "default",
    gender: str = "",
    cross_culture_chance: float | None = None,
    culture_weights: dict[str, float] | None = None,
    seed: int | str | None = None,
    use_patronymic: bool | None = None,
) -> str:
    """Generates a first name matching a predetermined family surname with cultural coordination.
    - Surnames determine baseline family culture (e.g. Yamada -> Japanese, Kowalski -> Polish).
    - 75% intra-cultural given name / 25% cross-cultural given name (customizable via cross_culture_chance).
    - Respects East Asian surname-first ordering, gender inflections (e.g. Kowalska), and patronymics.
    """
    if not surname:
        return generate_person_name(scenario=scenario, gender=gender, seed=seed)

    rng = random.Random(seed) if seed is not None else random

    d = _get_scenario_data(scenario, "person")
    cultures = d.get("cultures") if isinstance(d, dict) else None
    if not cultures:
        def_p = _get_scenario_data("default", "person")
        if isinstance(def_p, dict) and "cultures" in def_p:
            cultures = def_p.get("cultures")
            if not isinstance(d, dict):
                d = {}
            if "culture_weights" not in d:
                d["culture_weights"] = def_p.get("culture_weights")

    if not cultures or not isinstance(cultures, dict):
        raw_first = generate_person_name(scenario=scenario, gender=gender, seed=seed).split()[0]
        return f"{raw_first} {surname}"

    culture_keys = list(cultures.keys())
    base_culture = infer_surname_culture(surname) or "english"
    if base_culture not in cultures:
        base_culture = "english" if "english" in cultures else culture_keys[0]

    base_pool = cultures.get(base_culture) or {}

    eff_cross_chance = (
        cross_culture_chance
        if cross_culture_chance is not None
        else float(d.get("cross_culture_chance", 0.25) if isinstance(d, dict) else 0.25)
    )

    other_cultures = [c for c in culture_keys if c != base_culture]
    if other_cultures and rng.random() < eff_cross_chance:
        active_weights = culture_weights if culture_weights is not None else (d.get("culture_weights") if isinstance(d, dict) else None)
        if active_weights and isinstance(active_weights, dict):
            default_w = 1.0 if culture_weights is None else 0.0
            other_weights = [float(active_weights.get(k, default_w)) for k in other_cultures]
            if sum(other_weights) <= 0:
                other_weights = [1.0] * len(other_cultures)
            first_culture = rng.choices(other_cultures, weights=other_weights, k=1)[0]
        else:
            first_culture = rng.choice(other_cultures)
    else:
        first_culture = base_culture

    first_pool = cultures.get(first_culture) or base_pool

    g = str(gender or "").lower().strip()
    is_female = any(w in g for w in ("female", "woman", "girl", "feminine", "she"))
    is_male = any(w in g for w in ("male", "man", "boy", "masculine", "he")) and not is_female

    male_pool = first_pool.get("male") or []
    female_pool = first_pool.get("female") or []

    if is_female:
        pool = female_pool or ["Sarah"]
        resolved_gender = "female"
    elif is_male:
        pool = male_pool or ["Alex"]
        resolved_gender = "male"
    else:
        if male_pool and female_pool:
            pool = rng.choice([male_pool, female_pool])
            resolved_gender = "female" if pool is female_pool else "male"
        elif female_pool:
            pool = female_pool
            resolved_gender = "female"
        else:
            pool = male_pool or ["Alex"]
            resolved_gender = "male"

    first = rng.choice(pool)
    candidate = format_cultural_full_name(
        first_name=first,
        surname=surname,
        first_culture=first_culture,
        surname_culture=base_culture,
        gender=resolved_gender,
        rng=rng,
        deterministic_seed=str(seed) if seed is not None else None,
        use_patronymic=use_patronymic,
    )
    if is_spatial_or_object_homonym_name(candidate):
        safe_pool = [
            p for p in pool
            if not is_spatial_or_object_homonym_name(
                format_cultural_full_name(
                    first_name=p,
                    surname=surname,
                    first_culture=first_culture,
                    surname_culture=base_culture,
                    gender=resolved_gender,
                    rng=rng,
                    deterministic_seed=str(seed) if seed is not None else None,
                    use_patronymic=use_patronymic,
                )
            )
        ]
        if safe_pool:
            first = rng.choice(safe_pool)
            candidate = format_cultural_full_name(
                first_name=first,
                surname=surname,
                first_culture=first_culture,
                surname_culture=base_culture,
                gender=resolved_gender,
                rng=rng,
                deterministic_seed=str(seed) if seed is not None else None,
                use_patronymic=use_patronymic,
            )
    return candidate


def generate_npc_name(scenario: str = "fantasy", role: str = "", gender: str = "", **kwargs) -> str:
    """Generates an NPC person name (alias to generate_person_name, tolerating role and kwargs)."""
    return generate_person_name(scenario=scenario, gender=gender, **kwargs)


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
            first_name, surname = extract_first_and_last_name(clean)
            if not surname:
                first_name, surname = parts[0], parts[-1]
            surname = normalize_base_surname(surname) or surname
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
        first_name, surname = extract_first_and_last_name(clean)
        if not surname:
            first_name, surname = parts[0], parts[-1]
        surname = normalize_base_surname(surname) or surname
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
    """Generates a recreational woodland / lake park name without mountain references."""
    prefixes = ["Sakura Blossom", "Greenwood", "Pinecrest", "Asahi Grove", "Misty Lake", "Cedar Woodland", "Komorebi"]
    suffixes = ["Recreational Park", "Park & Nature Trails", "Woodland & Campsite Park", "Hilltop Recreational Park"]
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
    """Generates an evocative downtown / city center shopping promenade name."""
    prefixes = [
        "Sakuragaoka", "Ouka", "Minami", "Chuo", "Hanamizuki", "Tsukimi",
        "Komorebi", "Aoba", "Asahi", "Shin-Komiya", "Suzuran", "Midori"
    ]
    suffixes = [
        "Downtown", "Downtown Promenade", "Downtown Core",
        "Downtown Shopping District", "Avenue Downtown", "Downtown & City Square"
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



def format_org_acronym(name: str) -> str:
    """Extracts uppercase initials from an organization name into a punctuated acronym (e.g. 'C.W.C.A.')."""
    words = [w for w in str(name or "").replace("-", " ").split() if w and w.lower() not in ("of", "the", "and", "for", "&")]
    initials = [w[0].upper() for w in words if w[0].isalnum()]
    return ".".join(initials) + ("." if initials else "")


def generate_agency_name(scenario: str = "urban_anomalies", hash_val: int = None) -> str:
    """Generates a procedural paranormal investigation / containment organization name (inspired by SCP, Control, Chainsaw Man)."""
    scopes = [
        "Metropolitan", "Municipal", "Civic", "Central", "Federal",
        "National", "Regional", "State", "City", "Sovereign"
    ]
    domains = [
        "Ward Control", "Breach Defense", "Anomaly Mitigation", "Occult Affairs",
        "Crisis Containment", "Aberration Response", "Threat Suppression",
        "Reality Stabilization", "Special Containment", "Cryptid Oversight"
    ]
    bodies = [
        "Bureau", "Agency", "Directorate", "Commission",
        "Division", "Authority", "Initiative"
    ]
    if hash_val is not None:
        sc = scopes[(hash_val * 31 + 7) % len(scopes)]
        dm = domains[(hash_val * 19 + 13) % len(domains)]
        bd = bodies[(hash_val * 23 + 17) % len(bodies)]
    else:
        import random
        sc = random.choice(scopes)
        dm = random.choice(domains)
        bd = random.choice(bodies)

    return f"{sc} {dm} {bd}"


def generate_agency_hq_name(scenario: str = "urban_anomalies", hash_val: int = None) -> str:
    """Generates the headquarters facility name that reflects the procedural agency name in crisp acronym format."""
    agency = generate_agency_name(scenario, hash_val)
    acronym = format_org_acronym(agency)
    return f"{acronym} HQ" if acronym else f"{agency} HQ"


def generate_exorcist_order_name(scenario: str = "anomalous_incursions", hash_val: int = None) -> str:
    """Generates a procedural Eastern Exorcist Clan / Monastic Shrine Order name."""
    prefixes = [
        "Vermilion Lotus", "Mount Ryujin", "Eightfold Pagoda", "Tenryu-ji",
        "Crimson Talisman", "Byakko Shrine", "Celestial Bell", "Kiyomizu",
        "Amaterasu Seal", "Silent Sutra", "Jade Dragon", "Twilight Torii"
    ]
    suffixes = [
        "Exorcist Order", "Onmyoji Clan", "Monastic Sealing Order",
        "Shrine Wardens", "Spirit-Pacification Conclave", "Ascetic Brotherhood"
    ]
    if hash_val is not None:
        p = prefixes[(hash_val * 29 + 11) % len(prefixes)]
        s = suffixes[(hash_val * 19 + 7) % len(suffixes)]
        return f"The {p} {s}"
    return f"The {random.choice(prefixes)} {random.choice(suffixes)}"


def generate_private_agency_name(scenario: str = "anomalous_incursions", hash_val: int = None, agency_index: int = 1) -> str:
    """Generates a procedural Private Anomaly Hunting Agency / PMC name."""
    prefixes = [
        "Blackwatch", "Aegis", "Cerberus", "Apex", "Hyperion", "Vespera",
        "Kestrel", "Ironveil", "Ouroboros", "Obsidian", "Monolith", "Paladin"
    ]
    domains = [
        "Tactical", "Security", "Defense", "Contractors", "Recovery",
        "Solutions", "Mitigation", "Containment"
    ]
    suffixes = [
        "PMC", "Group", "Corp", "Syndicate", "Consultancy"
    ]
    idx_salt = int(agency_index or 1) * 43
    if hash_val is not None:
        h = int(hash_val) + idx_salt
        p = prefixes[(h * 31 + 5) % len(prefixes)]
        d = domains[(h * 17 + 11) % len(domains)]
        s = suffixes[(h * 23 + 3) % len(suffixes)]
        return f"{p} {d} {s}"
    p = random.choice(prefixes)
    d = random.choice(domains)
    s = random.choice(suffixes)
    return f"{p} {d} {s}"


def generate_occult_cult_name(scenario: str = "anomalous_incursions", hash_val: int = None) -> str:
    """Generates a procedural Occult Anomaly Cult faction name."""
    adjectives = [
        "Hollow", "Pale", "Weeping", "Inverted", "Sunken", "Crimson",
        "Unblinking", "Seventh", "Silent", "Gilded", "Static", "Spiral"
    ]
    nouns = [
        "Aperture", "Broadcast", "Eclipse", "Choir", "Threshold", "Meridian",
        "Witnesses", "Cathedral", "Covenant", "Spiral", "Litany", "Chrysalis"
    ]
    titles = [
        "Children of the", "Order of the", "Congregation of the",
        "Disciples of the", "Church of the", "Heralds of the"
    ]
    if hash_val is not None:
        h = int(hash_val)
        t = titles[(h * 19 + 7) % len(titles)]
        a = adjectives[(h * 29 + 13) % len(adjectives)]
        n = nouns[(h * 37 + 5) % len(nouns)]
        if a == n:
            n = nouns[(h * 37 + 6) % len(nouns)]
        return f"{t} {a} {n}"
    t = random.choice(titles)
    a = random.choice(adjectives)
    n = random.choice([x for x in nouns if x != a] or nouns)
    return f"{t} {a} {n}"


def generate_clandestine_syndicate_name(scenario: str = "anomalous_incursions", hash_val: int = None) -> str:
    """Generates a procedural Clandestine / 'Sus' Syndicate faction name."""
    prefixes = [
        "Sub-Level Zero", "Black-Ribbon", "Cipher-Nine", "Mirror-Shard",
        "Null-Protocol", "Nightshade", "Dead-Drop", "Glass-Key",
        "Phantom-Ledger", "Onyx-Brokerage", "Redacted-Hand", "Grey-Market"
    ]
    bodies = [
        "Directorate", "Consortium", "Exchange", "Syndicate",
        "Cabal", "Network", "Cartel", "Collective"
    ]
    if hash_val is not None:
        h = int(hash_val)
        p = prefixes[(h * 41 + 9) % len(prefixes)]
        b = bodies[(h * 23 + 15) % len(bodies)]
        return f"The {p} {b}"
    return f"The {random.choice(prefixes)} {random.choice(bodies)}"


def generate_anomalous_entity_name(archetype_or_tag: str = "", hash_val: int = None, category_tag: str = "") -> str:
    """
    Generates a procedural anomalous entity name fitting Anomalous Incursions
    (no numeric threat grades).
    """
    descriptors = [
        "Static-Stitched", "Non-Euclidean", "Mirrored", "Porcelain-Faced",
        "Fluorescent", "Hollow-Eyed", "Whispering", "Subway-Born", "Inverted",
        "Vein-Woven", "Clockwork-Spined", "Ash-Draped", "Cathode-Ray",
        "Geometry-Warped", "Rain-Soaked", "Headless-Mannequin", "Signal-Lost"
    ]
    forms = [
        "Mannequin Amalgam", "Commuter Phantom", "Broadcast Doppelganger",
        "Corridor Stalker", "Censor-Hound", "Concrete Weaver", "Echo-Parasite",
        "Warden-Automaton", "Flesh-Choir Vessel", "Threshold Harbinger",
        "Mirror-Wraith", "Turnstile Mimic", "Neon Specter", "Reliquary Fiend"
    ]
    tag_l = str(category_tag or archetype_or_tag or "").lower()
    if "cognitohazard" in tag_l:
        forms = ["Broadcast Doppelganger", "Echo-Parasite", "Signal-Choir Phantasm", "Memetic Stalker"]
    elif "spatial_warp" in tag_l:
        forms = ["Corridor Weaver", "Turnstile Mimic", "Folding-Stairwell Entity", "Tesseract Hound"]
    elif "bio_aberration" in tag_l:
        forms = ["Flesh-Choir Vessel", "Vein-Stitched Amalgam", "Subway Chimera", "Carapace Husker"]
    elif "cursed_relic" in tag_l:
        forms = ["Mannequin Amalgam", "Porcelain Automaton", "Reliquary Idol", "Clockwork Effigy"]
    elif "spectral_echo" in tag_l:
        forms = ["Commuter Phantom", "Mirror-Wraith", "Midnight Platform Apparition", "Weeping Poltergeist"]

    if hash_val is not None:
        h = int(hash_val)
        desc = descriptors[(h * 31 + 11) % len(descriptors)]
        form = forms[(h * 19 + 7) % len(forms)]
        return f"The {desc} {form}"
    return f"The {random.choice(descriptors)} {random.choice(forms)}"


def generate_world_ending_anomaly_profile(hash_val: int = None) -> dict:
    """
    Deterministically rolls a procedural World-Ending Anomaly Antagonist profile
    for the 11-Chapter Anomalous Incursions story campaign.
    """
    profiles = [
        {
            "id": "cataclysm_non_euclidean_convergence",
            "name": "The Non-Euclidean Convergence",
            "title": "Architect of the Inverted Metropolis",
            "classification_tags": ["aberration", "spatial_warp", "cognitohazard"],
            "element": "dark",
            "foreshadow_sign": "impossible 13th-floor corridors and backwards-running transit clocks",
            "cult_goal": "collapse the city's spatial boundaries into an eternal labyrinth",
            "syndicate_goal": "harvest dimensional fold-cores from the collapsing transit grid",
            "harbinger_name": "The Prime Tesseract Apostle",
        },
        {
            "id": "cataclysm_pale_broadcast",
            "name": "The Pale Broadcast Singularity",
            "title": "The Dead-Channel Sovereign",
            "classification_tags": ["incorporeal", "cognitohazard", "spectral_echo"],
            "element": "shock",
            "foreshadow_sign": "unplugged televisions and smartphones whispering on dead frequencies at 03:33",
            "cult_goal": "overwrite human consciousness across the metropolitan broadcast towers",
            "syndicate_goal": "monopolize cognitive-override frequencies as a black-market weapon",
            "harbinger_name": "The Dead-Frequency Conductor",
        },
        {
            "id": "cataclysm_hollow_eclipse",
            "name": "The Hollow Eclipse Sovereign",
            "title": "Devourer of the Penumbral Veil",
            "classification_tags": ["demon", "dark", "cursed_relic"],
            "element": "dark",
            "foreshadow_sign": "second shadows detaching from pedestrians beneath streetlamps",
            "cult_goal": "extinguish the Grand Temple's ancient barrier seals to summon a permanent black sun",
            "syndicate_goal": "smuggle unsealed eclipse relics to high-bidding shadow conglomerates",
            "harbinger_name": "The Penumbral Herald",
        },
        {
            "id": "cataclysm_flesh_signal_choir",
            "name": "The Flesh-Signal Choir",
            "title": "The Resonant Hive-Cathedral",
            "classification_tags": ["aberration", "bio_aberration", "swarm"],
            "element": "poison",
            "foreshadow_sign": "crimson root-like veins pulsing inside the Under-City drainage tunnels",
            "cult_goal": "merge the city's population into a single immortal biological chorus",
            "syndicate_goal": "synthesize illicit regenerative serums from anomalous hive tissue",
            "harbinger_name": "The Crimson Cantor",
        },
        {
            "id": "cataclysm_ouroboros_meridian",
            "name": "The Ouroboros Meridian",
            "title": "Engine of the Fractured Hour",
            "classification_tags": ["construct", "spatial_warp", "cursed_relic"],
            "element": "ice",
            "foreshadow_sign": "localized time-loops freezing entire city blocks in repeating 60-second echoes",
            "cult_goal": "shatter linear time and trap the metropolis in an endless midnight",
            "syndicate_goal": "exploit temporal stasis vaults to execute untraceable heists",
            "harbinger_name": "The Chronos-Broken Warden",
        },
    ]
    if hash_val is not None:
        return dict(profiles[int(hash_val) % len(profiles)])
    return dict(random.choice(profiles))


_URBAN_ZONE_PREFIX_POOLS: dict[str, list[str]] = {
    "zone_city_center": ["Kurokawa", "Veridia", "Aegis-Chuo", "Ouka", "Valenport", "Shin-Asahi", "Caelum", "Sovereign-Core", "Kagutsuchi", "Vanguard-Central", "Hakuho", "Meridian"],
    "zone_downtown": ["Kagero", "Neon-Cross", "Mirage-Ward", "Vespera", "Shinjuku-West", "Starlight", "Pulse-Avenue", "Akatsuki", "Onyx-Square", "Nocturne", "Chuo-South", "Velvet-Mile"],
    "zone_uptown": ["St. Jude's", "Alderwood", "Kensington", "Shirakawa", "Belvedere", "Montclair", "Ravenscroft", "Aethelgard", "Ashford", "Ginkgo-Hill", "Westminster", "Highgate"],
    "zone_ultra_rich": ["Aurelia", "Elysium", "Celestia", "Solaria", "Crown-Crest", "Olympos", "Valhalla", "Gilded-Peak", "Seraphim", "Diamond-Ridge", "Astral-Heights", "Imperial"],
    "zone_low_cost_wards": ["Iron-Gutter", "Cinder-Block", "Kowloon-South", "Rust-Hollow", "Ash-Row", "Rookery-Nine", "Dreg-Side", "Soot-Alley", "Grim-Basin", "Barrow-Ward", "Scrap-Gate", "Bleakwater"],
    "zone_industrial": ["Vulcan", "Kurogane", "Promethean", "Cinder-Forge", "Smokestack-9", "Ironworks", "Brimstone", "Slag-River", "Titan-Foundry", "Anvil-Sector", "Coal-Harbor", "Heavy-Grid"],
    "zone_city_docks": ["Blackanchor", "Tidewater", "Shiokaze", "Iron-Quay", "Foghorn-Bay", "Saltwind", "Kraken-Wharf", "Deepwater", "Breakwater-7", "Leviathan-Port", "Storm-Pier", "Bilgewater"],
    "zone_suburbs": ["Sakura-Hill", "Miyamae", "Komorebi", "Maple-Crest", "Asahigaoka", "Hanamizuki", "Willow-Brook", "Tsukimigaoka", "Birchwood", "Hinata-Vale", "Wakaba", "Clover-Field"],
    "zone_seaside_beach": ["Shiranui", "Minami-Cove", "Azure-Bay", "Kamome", "Coral-Sands", "Suncrest", "Crescent-Shore", "Pearl-Tide", "Sirens-Bay", "Whitecap", "Starfish-Cove", "Lagoon-Point"],
    "zone_woods_reserve": ["Mount Tsukimi", "Pinecrest", "Komorebi-Peak", "Cedar-Ridge", "Misty-Hollow", "Blackwood-Crag", "Mount Asahi", "Silver-Fir", "Whispering-Pines", "Wolf-Crest", "Redwood-Basin", "Ravens-Peak"],
    "zone_theme_park": ["Starlight Wonder", "Dreamland Mirage", "Fantasia Kingdom", "Luna-Carnival", "Arcadia Joy", "Wonder-Galaxy", "Carousel-Bay", "Elysian Funland", "Paradox-Pier", "Miracle-Crown", "Astro-Playland", "Joypolis-Bay"],
    "zone_eastern_temple": ["Mount Ryujin", "Kiyomizu-Lotus", "Tenryu-zan", "Vermilion-Cloud", "Amaterasu-Peak", "Byakko-ji", "Suzaku-Crest", "Seiryu-Ridge", "Kinkaku-Heights", "Eightfold-Lotus", "Fushimi-Inari", "Cloud-Bell"],
    "zone_airport": ["Zephyr-Prime", "Haneda-West", "Pacific-Cross", "Aegis-Skyway", "Narita-Bay", "Horizon-Sky", "Stratos-Hub", "Albatross-Field", "Pegasus-Port", "Meridian-Air", "Vanguard-Aero", "Condor-Bay"],
    "zone_hospital": ["St. Camillus", "Mercy-Cross", "Saiseikai", "Asclepius", "Hakuho-Central", "St. Jude-Memorial", "Seraph-Care", "Providence", "Valen-Medical", "Sanctuary-Cross", "Aegis-General", "Nightingale"],
    "zone_university": ["Teito Imperial", "Miskatonic-East", "Waseda-Caelum", "St. Ignatius", "Aethelgard", "Kurokawa-State", "Veridia-Grand", "Ravenscroft", "Minerva-Heights", "Scholomance", "Ouka-Collegiate", "Solomon-Crown"],
    "zone_chinatown": ["Crimson-Lantern", "Longmen-Cross", "Golden-Dragon", "Kowloon-Gate", "Jade-Lotus", "Vermilion-Arch", "Tai-Ping", "Phoenix-Bazaar", "Qilin-Street", "Nine-Lantern", "Huanglong", "Silk-Pagoda"],
    "zone_undercity": ["Abyssal-Line", "Sector-Zero", "Tartarus-Drain", "Pre-War Hollow", "Nether-Vault", "Gehenna-Depths", "Black-Cistern", "Sub-Level Omega", "Stygian-Line", "Catacomb-Nine", "Deep-Sump", "Under-Crown"],
    "zone_botanical_zoo": ["Eden-Glass", "Verdant-Bay", "Midori-Ark", "Pelagic-Crown", "Sylvan-Dome", "Gaia-Park", "Emerald-Biosphere", "Nautilus-Bay", "Viridian-Ark", "Solaris-Dome", "Flora-Prime", "Leviathan-Reef"],
}


def _dedupe_stuttered_location_words(name: str) -> str:
    """Removes adjacent stuttered words caused by prefix/epithet overlap (e.g. 'Neon-Mirage Neon Shopping Arcade' -> 'Neon-Mirage Shopping Arcade')."""
    if not name:
        return ""
    res = str(name)
    # 1. 'WordA-WordB WordA ...' -> 'WordA-WordB ...'
    res = re.sub(r"\b([A-Za-z]{3,})(-[A-Za-z0-9]+)\s+\1\b", r"\1\2", res, flags=re.IGNORECASE)
    # 2. 'WordA-WordB WordB ...' -> 'WordA-WordB ...'
    res = re.sub(r"\b([A-Za-z0-9]+-([A-Za-z]{3,}))\s+\2\b", r"\1", res, flags=re.IGNORECASE)
    # 3. 'WordA WordA ...' -> 'WordA ...'
    res = re.sub(r"\b([A-Za-z]{3,})\s+\1\b", r"\1", res, flags=re.IGNORECASE)
    return res


def generate_urban_zone_name(z_id: str, raw_zone_name: str, hash_val: int = None, scenario: str = "anomalous_incursions") -> str:
    """
    Generates a deterministic procedural `[Proper Name] [Functional Role]` for any Tier-1 urban zone,
    preserving the base functional zone name so substring/keyword checks remain 100% intact.
    """
    if z_id == "zone_agency_hq" or "{session_agency_hq}" in str(raw_zone_name):
        return generate_agency_hq_name(scenario, hash_val=hash_val)
    if z_id == "zone_school_campus" or "{session_school}" in str(raw_zone_name):
        return generate_school_name(scenario, hash_val=hash_val)

    pool = _URBAN_ZONE_PREFIX_POOLS.get(z_id)
    if not pool:
        pool = _URBAN_ZONE_PREFIX_POOLS["zone_city_center"]

    z_offset = sum(ord(c) * (idx + 1) for idx, c in enumerate(str(z_id or raw_zone_name)))
    if hash_val is not None:
        prefix = pool[(int(hash_val) * 37 + z_offset) % len(pool)]
    else:
        prefix = random.choice(pool)

    base = str(raw_zone_name or "").strip()
    if base.lower().startswith("the "):
        base_clean = base[4:].strip()
        return _dedupe_stuttered_location_words(f"The {prefix} {base_clean}")
    if prefix.lower() in base.lower():
        return _dedupe_stuttered_location_words(base)
    return _dedupe_stuttered_location_words(f"{prefix} {base}")


_URBAN_FACILITY_EPITHET_POOLS: dict[str, list[str]] = {
    "zone_city_center": ["Grand Metro", "Aegis-Square", "Veridia-Core", "Sovereign", "Crown-Plaza", "Centurion", "Apex-Civic", "Meridian", "Ouka-Central", "Obelisk", "Solstice", "Vanguard"],
    "zone_downtown": ["Neon-Mirage", "Starlight", "Velvet-Note", "Cyber-Pulse", "Midnight-Sun", "Kagero-88", "Crimson-Neon", "Electric-Lotus", "Blue-Comet", "Shinjuku-Gold", "Nova-Beat", "Onyx-Dream"],
    "zone_uptown": ["Alderwood", "Belvedere", "St. Cecilia", "Victorian-Rose", "Ginkgo-Crown", "Ravenscroft", "Kensington", "Monarch", "Montclair", "Aethelgard", "Ivory-Arch", "Obsidian-Bell"],
    "zone_ultra_rich": ["Celestia", "Olympos-Gold", "Seraphim", "Valhalla-Crest", "Imperial-Silk", "Solaria-Prime", "Gilded-Swan", "Diamond-Vanguard", "Astral-Crown", "Versailles-Sky", "Platinum-Rose", "Sovereign-Lux"],
    "zone_low_cost_wards": ["Iron-Dog", "Rust-Bucket", "Cinder-9", "Crossbones", "Black-Gutter", "Grim-Corner", "Scrap-Hound", "Broken-Lantern", "Soot-Lung", "Barrow-Pit", "Dead-End", "Copper-Nail"],
    "zone_industrial": ["Hephaestus", "Kurogane-7", "Promethean", "Titan-Forge", "Slag-Works", "Brimstone-Core", "Iron-Anvil", "Molten-Crown", "Smokestack-12", "Goliath", "Cinder-Grid", "Cyclops"],
    "zone_city_docks": ["Kraken-Bay", "Salt-Anchor", "Foghorn-9", "Barnacle-Point", "Leviathan-Quay", "Storm-Tide", "Black-Rudder", "Sirens-Reach", "Deep-Harbor", "Nautilus", "Rusted-Keel", "Maelstrom"],
    "zone_suburbs": ["Sakura-Lane", "Maple-Leaf", "Komorebi", "Sunny-Brook", "Green-Gables", "Clover-Hill", "Bluebird", "Firefly-Way", "Pine-Needle", "Crescent-Moon", "Autumn-Breeze", "Wisteria"],
    "zone_school_campus": ["Sakura-Wing", "Ouka-Hall", "West-Pavilion", "Clockwork-Quad", "East-Annex", "Founder's", "North-Belfry", "Varsity-Crown", "Starlight-Hall", "Silver-Bell", "Ivy-Gate", "Horizon-Wing"],
    "zone_seaside_beach": ["Coral-Reef", "Sun-Splash", "Azure-Wave", "Seagull-Point", "Pelican-Bay", "Tidal-Crown", "Driftwood", "Mermaid-Lagoon", "Golden-Sand", "Albatross", "Riptide", "Conch-Shell"],
    "zone_woods_reserve": ["Whispering-Cedar", "Silver-Wolf", "Misty-Pine", "Black-Bear", "Redwood-Peak", "Owl-Creek", "Stag-Horn", "Mossy-Crag", "Moonlit-Ridge", "Falcon-Roost", "Elder-Spruce", "Raven-Stone"],
    "zone_theme_park": ["Starlight-Spin", "Cosmic-Comet", "Dream-Drop", "Wonder-Wheel", "Neon-Carnival", "Mirage-Coaster", "Galaxy-Splash", "Jester's-Crown", "Phantom-Track", "Calliope-9", "Carousel-Prime", "Sky-Scream"],
    "zone_eastern_temple": ["Ryujin's", "Crimson-Lotus", "Eightfold", "Vermilion-Cloud", "Jade-Bell", "Tenryu", "Amaterasu", "White-Fox", "Golden-Bodhi", "Weeping-Kannon", "Mist-Pagoda", "Silent-Dharma"],
    "zone_airport": ["Skyway-1", "Stratos-9", "Terminal-Omega", "Zephyr-Gate", "Concorde-Bay", "Pegasus-Wing", "Horizon-Deck", "Mach-3", "Jetstream", "Albatross-Hangar", "Valkyrie-Runway", "Icarus-Point"],
    "zone_hospital": ["St. Luke's", "Asclepius-3", "Mercy-Wing", "Nightingale", "Lazarus-Ward", "Hippocrates", "White-Cross", "Seraph-Triage", "Caduceus", "Panacea-Hall", "Sanctuary-7", "Bio-Ward"],
    "zone_university": ["Minerva-Hall", "Euler-Wing", "Miskatonic", "Galileo-Dome", "Paracelsus", "Newton-Quad", "Copernicus", "Hypatia-Stacks", "Solomon-Arch", "Kepler-Spire", "Ptolemy", "Hermes-Lab"],
    "zone_chinatown": ["Golden-Wok", "Red-Dragon", "Jade-Phoenix", "Hundred-Herbs", "Silk-Lantern", "White-Tiger", "Emperor's", "Celestial-Pearl", "Five-Venoms", "Lotus-Tile", "Crimson-Peony", "Vermilion-Moon"],
    "zone_undercity": ["Tartarus-9", "Stygian", "Sub-Zero", "Gorgon-Drain", "Catacomb-7", "Black-Sump", "Nether-Pipe", "Charon's", "Rust-Vault", "Abyssal-Shaft", "Morlock-Row", "Deep-Fissure"],
    "zone_botanical_zoo": ["Eden-Dome", "Amazonia", "Mariana-Trench", "Goliath-Reef", "Orchid-Crown", "Panthera", "Nautilus-9", "Verdant-Canopy", "Chrysalis", "Kraken-Tank", "Biolume", "Rafflesia"],
}


def generate_urban_facility_name(
    z_id: str,
    p_id: str,
    raw_primary_name: str,
    hash_val: int = None,
    char_name: str = "",
    scenario: str = "anomalous_incursions",
) -> str:
    """
    Generates a deterministic per-session procedural name for any Tier-2 Primary Facility in
    Anomalous Incursions while preserving the full functional title for substring/keyword matching.
    """
    base = str(raw_primary_name or "").strip()
    if not base or p_id in ("loc_player_house", "loc_homeroom", "loc_private_hq_1", "loc_private_hq_2", "loc_cult_sanctum_hq", "loc_clandestine_syndicate_hq"):
        return base
    if p_id == "loc_agency_hq" or "{session_agency_hq}" in base:
        if "{session_agency_hq}" in base or base.lower() == "organization headquarters":
            return generate_agency_hq_name(scenario, hash_val=hash_val)
        return base
    if p_id == "loc_theme_park":
        return generate_urban_zone_name("zone_theme_park", base, hash_val=hash_val, scenario=scenario)
    if p_id == "loc_eastern_temple":
        return generate_urban_zone_name("zone_eastern_temple", base, hash_val=hash_val, scenario=scenario)
    if p_id == "loc_general_hospital":
        return generate_urban_zone_name("zone_hospital", base, hash_val=hash_val, scenario=scenario)
    if p_id == "loc_botanical_zoo":
        return generate_urban_zone_name("zone_botanical_zoo", base, hash_val=hash_val, scenario=scenario)

    p_offset = sum(ord(c) * (idx + 3) for idx, c in enumerate(str(p_id or base)))
    h = int(hash_val if hash_val is not None else 1)

    # 1. Organization HQ & Corporate AgencyHQ Wings: Procedural Sector / Wing / Floor / Sub-Level Designation (A5)
    if z_id == "zone_agency_hq" or p_id.startswith("loc_hq_"):
        wing_letters = ["A", "B", "C", "D", "E", "F", "G", "H"]
        w_let = wing_letters[(h * 17 + p_offset) % len(wing_letters)]
        w_num = ((h * 23 + p_offset) % 9) + 1
        if p_id == "loc_hq_main_lobby":
            lobby_prefixes = [f"Concourse {w_let}-1", f"Central Atrium 0{w_num}", f"Gatehouse Sector {w_let}", f"Rotunda Tier {w_num}"]
            desig = lobby_prefixes[(h * 13 + p_offset) % len(lobby_prefixes)]
        elif p_id == "loc_hq_containment_sector":
            sub_num = ((h * 31 + p_offset) % 12) + 4
            vault_prefixes = [f"Sub-Level {sub_num}", f"Deep Vault {w_let}-{sub_num}", f"Quarantine Trench 0{w_num}", f"Abyssal Deck {sub_num}"]
            desig = vault_prefixes[(h * 19 + p_offset) % len(vault_prefixes)]
        else:
            wing_types = [f"Wing {w_let}-{w_num}", f"Sector {w_let}-{w_num}", f"Operations Deck {w_num}", f"Division Bay {w_let}-{w_num}"]
            desig = wing_types[(h * 29 + p_offset) % len(wing_types)]
        if ":" in base:
            return base
        return f"{desig}: {base}"

    if p_id.startswith(("sub_priv1_", "sub_priv2_")):
        if ":" in base:
            return base
        if p_id.endswith("_entrance"):
            desig = "Ground Concourse"
        elif p_id.endswith("_vault"):
            b_lvl = ((h * 19 + p_offset) % 5) + 2
            desig = f"Sub-Level B{b_lvl}"
        else:
            flr = ((h * 11 + p_offset) % 38) + 12
            desig = f"Floor {flr}"
        return f"{desig}: {base}"

    # 2. City & Outskirts Facilities: Prepend thematic proper epithet while keeping base functional name intact
    pool = _URBAN_FACILITY_EPITHET_POOLS.get(z_id) or _URBAN_FACILITY_EPITHET_POOLS["zone_city_center"]
    epithet = pool[(h * 41 + p_offset) % len(pool)].strip()

    if epithet.lower() in base.lower():
        return _dedupe_stuttered_location_words(base)
    if base.lower().startswith("the "):
        return _dedupe_stuttered_location_words(f"The {epithet} {base[4:].strip()}")
    return _dedupe_stuttered_location_words(f"{epithet} {base}")


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


def get_scenario_starter_factions(scenario: str, is_nsfw: bool = False, hash_val: int = None) -> list[dict]:
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
        factions.append({
            "name": "Varsity Athletic Directorate",
            "hierarchy_template": "council",
            "category": "sports",
            "hq_location_id": "Main Gymnasium",
            "notes": "The competitive varsity athletics committee coordinating inter-school tournaments, team training regimens, and sports facility access."
        })
        if is_nsfw or scenario_data.is_nsfw_scenario(scen_key):
            nsfw_name = _unique_name("nsfw", "high_school_drama")
            factions.append({
                "name": nsfw_name,
                "hierarchy_template": "club",
                "category": "nsfw_club",
                "hq_location_id": "Velvet Basement Salon",
                "notes": "An underground campus circle gathering inside the Velvet Basement Salon beneath the Abandoned Old Campus Building for decadent secret rites and intimate trysts."
            })

    # 1.5A Anomalous Incursions (6 Fixed Archetype Factions with Procedural Names)
    elif scenario_data.is_anomalous_incursions_scenario(scen_key):
        agency_name = generate_agency_name(scen_key, hash_val=hash_val)
        priv_1_name = generate_private_agency_name(scen_key, hash_val=hash_val, agency_index=1)
        priv_2_name = generate_private_agency_name(scen_key, hash_val=hash_val, agency_index=2)
        if priv_2_name == priv_1_name:
            priv_2_name = generate_private_agency_name(scen_key, hash_val=(int(hash_val or 7) + 99), agency_index=3)
        exorcist_order = generate_exorcist_order_name(scen_key, hash_val=hash_val)
        cult_name = generate_occult_cult_name(scen_key, hash_val=hash_val)
        syndicate_name = generate_clandestine_syndicate_name(scen_key, hash_val=hash_val)

        # Deterministic zone selection for Private Agency #1 and #2 among City Center, Downtown, Uptown
        urban_core_zones = ["zone_city_center", "zone_downtown", "zone_uptown"]
        h_int = int(hash_val if hash_val is not None else 1)
        p1_zone = urban_core_zones[h_int % 3]
        p2_zone = urban_core_zones[(h_int + 1) % 3]
        cult_zone = "zone_woods_reserve" if (h_int % 2 == 0) else "zone_undercity"
        synd_zone = "zone_undercity" if cult_zone == "zone_woods_reserve" else "zone_industrial"

        priv_1_acr = format_org_acronym(priv_1_name)
        priv_1_hq = f"{priv_1_acr} Tower HQ" if priv_1_acr else f"{priv_1_name} HQ"
        priv_2_acr = format_org_acronym(priv_2_name)
        priv_2_hq = f"{priv_2_acr} Operations HQ" if priv_2_acr else f"{priv_2_name} HQ"

        factions.extend([
            {
                "name": agency_name,
                "archetype_key": "public_agency",
                "hierarchy_template": "corpo",
                "category": "public_agency",
                "joinable": True,
                "diplomatic_stance": "friendly",
                "hq_zone_id": "zone_city_center",
                "hq_node_id": "loc_agency_hq",
                "hq_location_id": "loc_hq_executive_dispatch",
                "notes": "The primary state-sanctioned paranormal investigation and containment organization. Agents receive a daily taxpayer-funded salary and a 50% HQ requisition discount, but must surrender all official bounty payouts and anomaly loot to the Bureau.",
            },
            {
                "name": priv_1_name,
                "archetype_key": "private_agency_1",
                "hierarchy_template": "corpo",
                "category": "private_agency",
                "joinable": True,
                "diplomatic_stance": "friendly",
                "hq_zone_id": p1_zone,
                "hq_node_id": "loc_private_hq_1",
                "hq_location_id": priv_1_hq,
                "notes": "A premier corporate anomaly-hunting agency and licensed containment contractor. Operatives receive no salary, but keep 100% of bounty fees and anomaly loot, and enjoy access to high-tier anomalous gear at their private armory.",
            },
            {
                "name": priv_2_name,
                "archetype_key": "private_agency_2",
                "hierarchy_template": "corpo",
                "category": "private_agency",
                "joinable": True,
                "diplomatic_stance": "friendly",
                "hq_zone_id": p2_zone,
                "hq_node_id": "loc_private_hq_2",
                "hq_location_id": priv_2_hq,
                "notes": "A rival private anomaly-eradication conglomerate competing for high-value corporate and municipal containment contracts. Operatives keep all bounty rewards and salvaged anomalous relics.",
            },
            {
                "name": exorcist_order,
                "archetype_key": "monastic_order",
                "hierarchy_template": "order",
                "category": "monastic_order",
                "joinable": True,
                "diplomatic_stance": "friendly",
                "hq_zone_id": "zone_woods_reserve",
                "hq_node_id": "loc_et_main_sanctuary",
                "hq_location_id": "loc_et_main_sanctuary",
                "notes": "An ancient Eastern monastic exorcist clan and shrine order maintaining sacred seals at the Grand Temple. Initiates receive no salary or order bounty fees, but keep combat spoils and receive 2-3 sacred items completely free each day.",
            },
            {
                "name": cult_name,
                "archetype_key": "cult_faction",
                "hierarchy_template": "order",
                "category": "cult_faction",
                "joinable": False,
                "diplomatic_stance": "distrusted",
                "hq_zone_id": cult_zone,
                "hq_node_id": "loc_cult_sanctum_hq",
                "hq_location_id": f"{cult_name} Hidden Sanctum",
                "notes": "A secretive, distrusted occult congregation that worships reality fractures and seeks to usher in the World-Ending Anomaly. Viewed with deep suspicion or outright hostility by all licensed containment organizations.",
            },
            {
                "name": syndicate_name,
                "archetype_key": "clandestine_faction",
                "hierarchy_template": "syndicate",
                "category": "clandestine_faction",
                "joinable": False,
                "diplomatic_stance": "distrusted",
                "hq_zone_id": synd_zone,
                "hq_node_id": "loc_clandestine_syndicate_hq",
                "hq_location_id": f"{syndicate_name} Shadow Exchange HQ",
                "notes": "A shadowy, distrusted clandestine syndicate trafficking uncatalogued anomalous relics, weaponized cognitohazards, and black-budget research behind the scenes.",
            },
        ])

    # 1.5B Generic Urban Fantasy (Non-Anomalous Incursions)
    elif scenario_data.has_tag(scen_key, "urban_fantasy"):
        agency_name = generate_agency_name(scen_key)
        exorcist_order = generate_exorcist_order_name(scen_key)
        factions.append({
            "name": agency_name,
            "hierarchy_template": "corpo",
            "category": "agency",
            "hq_location_id": "loc_hq_executive_dispatch",
            "notes": "The state-sanctioned paranormal investigation and containment organization responsible for responding to anomalous manifestations."
        })
        factions.append({
            "name": exorcist_order,
            "hierarchy_template": "order",
            "category": "order",
            "hq_location_id": "loc_et_main_sanctuary",
            "notes": "An ancient Eastern monastic exorcist clan and shrine order maintaining sacred seals, protective talismans, and spirit pacification rites at the Grand Temple."
        })
        factions.append({
            "name": "Underground Occult Exchange",
            "hierarchy_template": "syndicate",
            "category": "syndicate",
            "hq_location_id": "loc_occult_curio_shop",
            "notes": "A clandestine black-market network trafficking uncatalogued anomalous relics, forbidden talismans, and unauthorized containment bypasses."
        })
        factions.append({
            "name": "Metropolitan Civil Defense League",
            "hierarchy_template": "guild",
            "category": "guild",
            "hq_location_id": "loc_metro_transit_terminal",
            "notes": "A citywide coalition of licensed anomaly contractors, private wardens, and auxiliary volunteer dispatchers assisting during breaches."
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

