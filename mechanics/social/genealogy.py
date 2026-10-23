from __future__ import annotations
"""
Modular Genealogy & Social Relations Engine for Hikayat.

Implements:
- Reverse-genealogy & genetic phenotype inheritance (working backward from child).
- Interracial genetics:
  * Human + Beastfolk: 1/3 Human, 1/3 Half-Beast, 1/3 Beastfolk with strict species locking.
  * Other Interracial crosses: 50/50 split between parent races.
- Strict surname and phenotypic color/features inheritance across immediate family.
- Decoupled relationship status (current partner, secret affairs, exes) independent of virginity.
- Friends & Rivals social graph.
- Strict 3-tier progressive information disclosure.
"""
import hashlib
import json
import logging
import random
import re
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

import namegen
from mechanics.social.races import (
    format_race_display,
    normalize_race,
    BEASTFOLK_ALIASES,
    HALF_BEAST_ALIASES
)


def resolve_player_character_name(contact: dict, session_id: int = 0) -> str:
    """Attempts to find the player character's name associated with this contact."""
    # 1. Try from intimate memories (e.g. "Maya accepted Artemiusz's request...")
    mems = contact.get("intimate_memories") or []
    if isinstance(mems, str):
        try:
            mems = json.loads(mems)
        except Exception:
            mems = [mems]

    for m in mems:
        m_str = str(m)
        match = re.search(r"(?:with|on|for|from|to|accepted)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)'s?\s+(?:request|bedroom|intimacy|kiss|night|first taste)", m_str)
        if match:
            cand = match.group(1).strip()
            if cand.lower() not in ("her", "his", "their", "the", "a", "an"):
                return cand

    # 2. Try from database character lookup
    char_id = contact.get("character_id", 0)
    sess_id = session_id or contact.get("session_id", 0)
    try:
        import db
        if char_id:
            char = db.get_character_by_id(char_id)
            if char and char.get("name"):
                return char["name"]
        if sess_id:
            with db.get_conn() as conn:
                row = conn.execute(
                    """SELECT c.name FROM characters c
                       JOIN session_members sm ON c.user_id = sm.user_id
                       WHERE sm.session_id = ? AND c.is_active = 1 LIMIT 1""",
                    (sess_id,)
                ).fetchone()
                if row and row["name"]:
                    return row["name"]

                row_alt = conn.execute(
                    "SELECT name FROM characters WHERE active_session_id=? AND is_active=1 LIMIT 1",
                    (sess_id,)
                ).fetchone()
                if row_alt and row_alt["name"]:
                    return row_alt["name"]
    except Exception:
        pass

    return "Player"


def extract_species_from_race(race: str) -> str:
    """Extracts the base animal species (e.g. 'fox', 'cat', 'wolf', 'rabbit')
    from beastfolk or half-beast race strings. Returns '' if not beastfolk/hybrid."""
    if not race:
        return ""
    r = str(race).strip().lower().replace("-", " ").replace("_", " ")
    if ":" in r:
        return r.split(":")[-1].strip().replace(" ", "_")
    from game_engine.matching import find_keyword_match
    species_list = [
        "fennec_fox", "fennec fox", "fennec", "cheetah", "tiger", "lion", "mouse", "rat",
        "rabbit", "bunny", "cat", "wolf", "fox", "bear", "bird", "reptile"
    ]
    res = find_keyword_match(r, species_list)
    if res.matched:
        matched = res.matched_term.lower().replace(" ", "_")
        if matched in ("fennec_fox", "fennec"):
            return "fennec"
        if matched in ("rabbit", "bunny"):
            return "rabbit"
        if matched in ("mouse", "rat"):
            return "mouse"
        return matched
    from mechanics.social.races import resolve_animal_family_species
    fam_sp = resolve_animal_family_species(r)
    if fam_sp:
        return fam_sp
    return ""


def extract_surname_and_firstname(name: str) -> Tuple[str, str]:
    """Splits full name into (first_name, surname) respecting East Asian surname-first,
    Malay patronymics, and gender-inflected surnames.
    e.g. 'Sofia Anderson' -> ('Sofia', 'Anderson')
    'Zhang Wei' -> ('Wei', 'Zhang')
    'Danial bin Ismail' -> ('Danial', 'Ismail')
    'Zuzanna Kowalska' -> ('Zuzanna', 'Kowalski')
    'Aldric' -> ('Aldric', '')
    """
    if not name or not isinstance(name, str) or not name.strip():
        return ("Unknown", "")
    first, last = namegen.extract_first_and_last_name(name)
    if last:
        last = namegen.normalize_base_surname(last)
    return (first or "Unknown", last)


def get_deterministic_firstname(scenario: str, gender: str, hash_val: int, culture: str = "") -> str:
    """Deterministically rolls a gendered first name using hash_val, scenario data, and optional family culture."""
    data = namegen._get_scenario_data(scenario, "person")
    if not isinstance(data, dict):
        data = {}
    g = str(gender or "").lower().strip()
    is_female = ("female" in g or "woman" in g or "girl" in g or "feminine" in g or "she" in g)
    is_male = ("male" in g or "man" in g or "boy" in g or "masculine" in g or "he" in g) and not is_female

    # If a specific family culture is known and intra-cultural roll succeeds (75%), pull from that culture's pool
    c_key = str(culture or "").lower().strip()
    if c_key and c_key != "english" and ((abs(hash_val) * 19 + 7) % 100) < 75:
        cultures_dict = data.get("cultures") if isinstance(data.get("cultures"), dict) else None
        if not cultures_dict:
            default_person = namegen._DATA.get("default", {}).get("person", {})
            if isinstance(default_person, dict) and isinstance(default_person.get("cultures"), dict):
                cultures_dict = default_person["cultures"]
        if cultures_dict and c_key in cultures_dict:
            c_pool_dict = cultures_dict[c_key]
            c_male = c_pool_dict.get("male") or []
            c_female = c_pool_dict.get("female") or []
            c_pool = c_female if is_female else (c_male if is_male else (c_male + c_female))
            if c_pool:
                idx = (abs(hash_val) * 31 + 17) % len(c_pool)
                return c_pool[idx]

    male_pool = data.get("male") or [
        "Marcus", "Julian", "Leon", "Adrian", "Lucas", "Darius", "Ethan", "Cyrus",
        "Alexander", "Cedric", "Damian", "Soren", "Felix", "Tristan", "Victor", "Gabriel"
    ]
    female_pool = data.get("female") or [
        "Elena", "Seraphina", "Cassandra", "Valerie", "Vivian", "Chloe", "Camilla", "Iris",
        "Morgan", "Hana", "Maya", "Lyra", "Giselle", "Natalia", "Astrid", "Evelyn"
    ]

    pool = female_pool if is_female else (male_pool if is_male else (male_pool + female_pool))
    idx = (abs(hash_val) * 31 + 17) % len(pool)
    return pool[idx]


def get_deterministic_surname(scenario: str, hash_val: int) -> str:
    """Deterministically rolls a scenario-appropriate surname."""
    data = namegen._get_scenario_data(scenario, "person")
    if not isinstance(data, dict):
        data = {}
    last_pool = data.get("last") or [
        "Anderson", "Vance", "Reed", "Drake", "Cross", "Sterling", "Thorne", "Cole",
        "Black", "Wright", "Finch", "Blackwood", "Mercer", "Ashwood", "Volkov", "Ward", "Hayes"
    ]
    idx = (abs(hash_val) * 43 + 19) % len(last_pool)
    return last_pool[idx]


def get_parent_role(scenario: str, gender: str, hash_val: int) -> str:
    """Generates adult/parent occupations matching scenario flavor."""
    from scenario_data import has_tag
    if has_tag(scenario, "high_school"):
        roles = [
            "Athletic Director / Coach", "University Professor", "Architect",
            "Hospital Physician", "Research Scientist", "Small Business Owner",
            "Corporate Executive", "Veterinarian", "Published Author",
            "Civil Engineer", "Boutique Owner", "Senior Accountant"
        ]
    elif has_tag(scenario, "sci_fi") or has_tag(scenario, "space") or has_tag(scenario, "cyberpunk"):
        roles = [
            "Starship Systems Engineer", "Bio-Tech Researcher", "Orbital Station Officer",
            "Cybernetics Specialist", "Freight Fleet Captain", "Planetary Cartographer",
            "Quantum Grid Architect", "Corporate Senior Analyst"
        ]
    elif has_tag(scenario, "post_apocalypse"):
        roles = [
            "Settlement Elder", "Scrap Workshop Master", "Caravan Guard Captain",
            "Hydro-Farm Specialist", "Wasteland Herbalist", "Bunker Mechanic"
        ]
    else:  # Fantasy / Default
        roles = [
            "High Guild Merchant", "Master Blacksmith", "Herbalist Apothecary",
            "Town Guard Veteran", "Court Scholar", "Caravan Master",
            "Archmage Academy Archivist", "Estate Landholder"
        ]
    return roles[(abs(hash_val) * 23 + 11) % len(roles)]


def reverse_generate_parents(
    child_race: str,
    child_appearance: dict,
    child_surname: str = "",
    scenario: str = "fantasy",
    hash_val: int = 0
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Works backward from the child character to generate Father and Mother:
    - 15% chance of interracial parents (85% same race).
    - If child is beastfolk/half-beast:
      * Same-race: both parents beastfolk.
      * Interracial: one parent is Human, one parent is Beastfolk (or Half-Beast).
      * Species (e.g. 'fox') is 100% locked across all beastfolk/half-beast parents.
    - Surnames: Father takes child_surname. Mother takes child_surname with optional maiden name.
    - Phenotype: Parents' eye, hair, fur/coat colors match and complement child's appearance.
    """
    c_race = normalize_race(child_race, scenario)
    species = extract_species_from_race(c_race)
    is_beast = c_race.startswith("beastfolk")
    is_half_beast = c_race.startswith("half_beast") or c_race.startswith("hybrid")

    # 15% chance of interracial parent pairing
    is_interracial = ((abs(hash_val) * 13 + 7) % 100) < 15

    father_race = c_race
    mother_race = c_race

    if is_beast or is_half_beast:
        base_species = species or "fox"
        if is_half_beast:
            # Half-beasts naturally have one human and one beastfolk parent (or two half-beasts)
            if (abs(hash_val) % 100) < 75:
                # 75% Human + Beastfolk pairing
                if (abs(hash_val) % 2) == 0:
                    father_race = "human"
                    mother_race = f"beastfolk:{base_species}"
                else:
                    father_race = f"beastfolk:{base_species}"
                    mother_race = "human"
            else:
                father_race = f"half_beast:{base_species}"
                mother_race = f"half_beast:{base_species}"
        elif is_interracial:
            # Beastfolk child with interracial parents (Human + Beastfolk)
            if (abs(hash_val) % 2) == 0:
                father_race = "human"
                mother_race = f"beastfolk:{base_species}"
            else:
                father_race = f"beastfolk:{base_species}"
                mother_race = "human"
        else:
            father_race = f"beastfolk:{base_species}"
            mother_race = f"beastfolk:{base_species}"
    elif is_interracial:
        # Fantasy / Sci-Fi interracial (e.g. Elf + Human)
        scenario_other_races = ["human"] if c_race != "human" else ["elf", "dwarf", "beastfolk:cat", "beastfolk:fox"]
        other_r = scenario_other_races[(abs(hash_val) * 7) % len(scenario_other_races)]
        if (abs(hash_val) % 2) == 0:
            father_race = c_race
            mother_race = normalize_race(other_r, scenario)
        else:
            father_race = normalize_race(other_r, scenario)
            mother_race = c_race

    # Surnames
    family_surname = namegen.normalize_base_surname(child_surname) if child_surname else get_deterministic_surname(scenario, hash_val)
    s_culture = namegen.infer_surname_culture(family_surname)
    maiden_surname = get_deterministic_surname(scenario, hash_val * 7 + 13)
    if maiden_surname.lower() == family_surname.lower():
        maiden_surname = get_deterministic_surname(scenario, hash_val * 11 + 29)

    father_first = get_deterministic_firstname(scenario, "male", hash_val * 3 + 5, culture=s_culture)
    mother_first = get_deterministic_firstname(scenario, "female", hash_val * 5 + 11, culture=s_culture)

    father_name = namegen.format_cultural_full_name(
        father_first, family_surname, gender="male", surname_culture=s_culture,
        deterministic_seed=f"father_{family_surname}_{hash_val}"
    ).strip()
    mother_married_name = namegen.format_cultural_full_name(
        mother_first, family_surname, gender="female", surname_culture=s_culture,
        deterministic_seed=f"mother_{family_surname}_{hash_val}"
    ).strip()
    maiden_inflected = namegen.format_cultural_full_name(
        "X", maiden_surname, first_culture="english", gender="female", use_patronymic=False
    ).split()[-1] if maiden_surname else maiden_surname
    mother_name = f"{mother_married_name} (née {maiden_inflected})".strip()

    father_role = get_parent_role(scenario, "male", hash_val * 2 + 1)
    mother_role = get_parent_role(scenario, "female", hash_val * 2 + 3)

    # Status: In High School / Academy / Modern scenarios, parents are Alive unless explicitly orphaned in backstory
    from scenario_data import has_tag
    if has_tag(scenario, "high_school") or has_tag(scenario, "high_school_drama") or has_tag(scenario, "modern") or has_tag(scenario, "academy"):
        father_alive = True
        mother_alive = True
    else:
        father_alive = ((abs(hash_val) * 17) % 100) >= 5
        mother_alive = ((abs(hash_val) * 19) % 100) >= 5

    father_status = "Alive" if father_alive else "Deceased"
    mother_status = "Alive" if mother_alive else "Deceased"

    # Color palettes & traits consistency
    child_eyes = child_appearance.get("eyes") or "Amber"
    child_hair = child_appearance.get("hair") or "Golden-Blonde"
    child_fur = child_appearance.get("fur") or child_appearance.get("coat") or "Golden-Blonde Fur"

    father = {
        "relation": "Father",
        "name": father_name,
        "first_name": father_first,
        "surname": family_surname,
        "race": father_race,
        "gender": "male",
        "status": father_status,
        "occupation": father_role,
        "features": f"{child_eyes} eyes, {child_hair} hair" + (f", {child_fur}" if father_race.startswith("beastfolk") else "")
    }

    mother = {
        "relation": "Mother",
        "name": mother_name,
        "first_name": mother_first,
        "surname": family_surname,
        "maiden_name": maiden_surname,
        "race": mother_race,
        "gender": "female",
        "status": mother_status,
        "occupation": mother_role,
        "features": f"{child_eyes} eyes, {child_hair} hair" + (f", {child_fur}" if mother_race.startswith("beastfolk") else "")
    }

    return (father, mother)


def roll_sibling_race(
    parent1_race: str,
    parent2_race: str,
    base_species: str,
    hash_val: int
) -> str:
    """
    Rolls a sibling's race according to the established parental cross:
    - If one parent is Human and one is Beastfolk (or cross involving half-beast):
      * 1/3 chance: Human
      * 1/3 chance: Half-Beast (<species>)
      * 1/3 chance: Beastfolk (<species>)
      * 100% Species Consistent (Fox never produces Cat).
    - If other interracial pairing (e.g. Elf + Human):
      * 50% chance Parent 1's race, 50% chance Parent 2's race.
    - If both parents share race: Sibling inherits that race.
    """
    p1 = parent1_race.lower().strip()
    p2 = parent2_race.lower().strip()

    is_p1_human = (p1 == "human")
    is_p2_human = (p2 == "human")
    is_p1_beast = p1.startswith("beastfolk") or p1.startswith("half_beast") or p1.startswith("hybrid")
    is_p2_beast = p2.startswith("beastfolk") or p2.startswith("half_beast") or p2.startswith("hybrid")

    # Special Beastfolk + Human cross
    if (is_p1_human and is_p2_beast) or (is_p2_human and is_p1_beast) or (p1.startswith("half_beast") and p2.startswith("half_beast")):
        sp = base_species or extract_species_from_race(p1) or extract_species_from_race(p2) or "fox"
        roll = abs(hash_val) % 3
        if roll == 0:
            return "human"
        elif roll == 1:
            return f"half_beast:{sp}"
        else:
            return f"beastfolk:{sp}"

    # General interracial cross (50/50 split)
    if p1 != p2:
        return p1 if (abs(hash_val) % 2 == 0) else p2

    return p1


def is_race_compatible_with_parents(child_race: str, father_race: str, mother_race: str) -> bool:
    """
    Validates biological inheritance rules:
    - If child has an animal species (beastfolk or half-beast), species MUST come from either father or mother.
    - If both parents are the exact same beastfolk species (e.g. fox + fox), child CANNOT be a different species (e.g. rabbit).
    - If parents are pure human, child cannot be beastfolk.
    - If neither parent is beastfolk, child cannot be beastfolk.
    """
    if not child_race or not father_race or not mother_race:
        return True

    c_norm = normalize_race(child_race)
    f_norm = normalize_race(father_race)
    m_norm = normalize_race(mother_race)

    c_species = extract_species_from_race(c_norm)
    f_species = extract_species_from_race(f_norm)
    m_species = extract_species_from_race(m_norm)

    # 1. If child has an animal species:
    if c_species:
        allowed_species = set(filter(None, [f_species, m_species]))
        if allowed_species and c_species not in allowed_species:
            return False
        if not allowed_species:
            # Parents have no beastfolk species at all
            return False

    # 2. If parents are both the exact same beastfolk species:
    if f_species and m_species and f_species == m_species:
        if c_species != f_species:
            return False

    # 3. If both parents are human:
    if f_norm == "human" and m_norm == "human":
        if c_norm != "human":
            return False

    # 4. If neither parent is beastfolk and child is beastfolk:
    if not f_species and not m_species and c_species:
        return False

    return True


def generate_siblings(
    father: Dict[str, Any],
    mother: Dict[str, Any],
    child_appearance: dict,
    scenario: str = "fantasy",
    hash_val: int = 0,
    contact_grade: str = "Junior",
    existing_sibling_count: int = 0
) -> List[Dict[str, Any]]:
    """
    Generates siblings using a diminishing probability ladder:
    - 75% for 1st sibling
    - 50% for 2nd sibling
    - 25% for 3rd sibling
    - 5% for 4th sibling (capped at 4 total siblings).
    - 50/50 roll for Older vs. Younger sibling.
    - Context-aware school grade scaling for High School / Academy scenarios.
    """
    diminishing_rates = [75, 50, 25, 5]
    siblings_to_generate = 0

    # Roll sequentially from existing_sibling_count up to 4 siblings max
    for idx in range(existing_sibling_count, 4):
        rate = diminishing_rates[idx]
        roll = (abs(hash_val * 43 + (idx + 1) * 79) % 100)
        if roll < rate:
            siblings_to_generate += 1
        else:
            break

    if siblings_to_generate == 0:
        return []

    family_surname = namegen.normalize_base_surname(
        father.get("surname") or mother.get("surname") or get_deterministic_surname(scenario, hash_val)
    )
    s_culture = namegen.infer_surname_culture(family_surname)
    base_species = extract_species_from_race(father.get("race", "")) or extract_species_from_race(mother.get("race", "")) or "fox"

    child_eyes = child_appearance.get("eyes") or "Amber"
    child_hair = child_appearance.get("hair") or "Golden-Blonde"
    child_fur = child_appearance.get("fur") or child_appearance.get("coat") or "Golden-Blonde Fur"

    from scenario_data import has_tag
    is_school = (
        has_tag(scenario, "high_school") or
        has_tag(scenario, "high_school_drama") or
        has_tag(scenario, "academy") or
        "school" in str(scenario).lower() or
        "high_school" in str(scenario).lower()
    )

    grade_map = {"Freshman": 1, "Sophomore": 2, "Junior": 3, "Senior": 4}
    base_grade_val = grade_map.get(contact_grade, 3)

    HIGH_SCHOOL_STUDENT_ROLES = [
        ("Student Council Aide", "Student Council"),
        ("Art Club Member", "Fine Arts Guild"),
        ("Track Sprinter", "Athletic Directorate"),
        ("Robotics Apprentice", "Science & Robotics Club"),
        ("Drama Club Performer", "Fine Arts Guild"),
        ("Library Assistant", "Academic Directorate"),
        ("Campus Photojournalist", "Journalism & Media"),
        ("Esports Team Member", "Esports & Gaming Club"),
        ("Swim Team Member", "Athletic Directorate"),
        ("Student", "General Academy")
    ]

    siblings = []
    for i in range(siblings_to_generate):
        sib_idx = existing_sibling_count + i + 1
        sib_hash = hash_val * 37 + sib_idx * 73
        is_female = ((abs(sib_hash) % 2) == 0)
        gender = "female" if is_female else "male"

        # 50/50 roll for Older vs. Younger sibling
        is_older = ((abs(sib_hash * 13 + 7) % 100) < 50)
        relation_title = f"{'Older' if is_older else 'Younger'} {'Sister' if is_female else 'Brother'}"

        sib_first = get_deterministic_firstname(scenario, gender, sib_hash, culture=s_culture)
        if sib_first.lower() == father.get("first_name", "").lower() or sib_first.lower() == mother.get("first_name", "").lower():
            sib_first = get_deterministic_firstname(scenario, gender, sib_hash * 3 + 17, culture=s_culture)
        sib_name = namegen.format_cultural_full_name(
            sib_first, family_surname, gender=gender, surname_culture=s_culture,
            deterministic_seed=f"sib_{sib_first}_{family_surname}_{sib_hash}"
        ).strip()
        sib_race = roll_sibling_race(father.get("race", "human"), mother.get("race", "human"), base_species, sib_hash)

        # Status: 100% Alive in School/Modern, 95% Alive in other scenarios
        if is_school:
            sib_status = "Alive"
        else:
            sib_status = "Alive" if ((abs(sib_hash) % 100) >= 5) else "Deceased"

        # School grade & contactability resolution
        sib_grade = ""
        is_contactable = False
        if is_school:
            age_roll = abs(sib_hash * 19 + 11) % 100
            if base_grade_val == 3:  # Junior
                if is_older:
                    sib_grade = "Senior" if age_roll < 70 else "College Alumnus"
                else:
                    sib_grade = "Sophomore" if age_roll < 50 else "Freshman"
            elif base_grade_val == 2:  # Sophomore
                if is_older:
                    sib_grade = "Junior" if age_roll < 50 else "Senior"
                else:
                    sib_grade = "Freshman" if age_roll < 75 else "Middle Schooler"
            elif base_grade_val == 1:  # Freshman
                if is_older:
                    if age_roll < 34:
                        sib_grade = "Sophomore"
                    elif age_roll < 67:
                        sib_grade = "Junior"
                    else:
                        sib_grade = "Senior"
                else:
                    sib_grade = "Middle Schooler"
            elif base_grade_val == 4:  # Senior
                if is_older:
                    sib_grade = "College Alumnus"
                else:
                    if age_roll < 34:
                        sib_grade = "Junior"
                    elif age_roll < 67:
                        sib_grade = "Sophomore"
                    else:
                        sib_grade = "Freshman"
            else:
                sib_grade = "Senior" if is_older else "Freshman"

            if sib_grade in ("Freshman", "Sophomore", "Junior", "Senior"):
                is_contactable = True
                role_idx = (sib_hash * 7) % len(HIGH_SCHOOL_STUDENT_ROLES)
                sib_role, sib_club = HIGH_SCHOOL_STUDENT_ROLES[role_idx]
            elif sib_grade == "Middle Schooler":
                sib_role = "Middle School Student"
                sib_club = ""
            else:
                sib_role = "University Student" if is_female else "College Student"
                sib_club = ""
        else:
            sib_role = namegen.generate_role(scenario, hash_val=sib_hash)
            sib_club = ""

        features_str = f"{child_eyes} eyes, {child_hair} hair"
        if sib_race.startswith("beastfolk") or sib_race.startswith("half_beast"):
            features_str += f", {child_fur}"

        sib_dict = {
            "relation": relation_title,
            "name": sib_name,
            "first_name": sib_first,
            "surname": family_surname,
            "race": sib_race,
            "gender": gender,
            "status": sib_status,
            "occupation": sib_role,
            "features": features_str
        }
        if sib_grade:
            sib_dict["grade"] = sib_grade
        if is_contactable:
            sib_dict["is_contactable"] = True
            if sib_club:
                sib_dict["club"] = sib_club

        siblings.append(sib_dict)

    return siblings


def generate_relationship_status(
    contact: dict,
    scenario: str = "fantasy",
    hash_val: int = 0
) -> Dict[str, Any]:
    """
    Rolls relationship standing independently from virginity:
    - 15% chance of Current Partner.
    - 3% chance of Secret Affair / Secret Lover.
    - 15% chance of Ex-Partner(s).
    - Synchronizes with named lovers from intimate_memories / past_intimate_history if present.
    """
    name = contact.get("name", "Unknown NPC")
    contact_gender = contact.get("gender") or "female"
    is_char_male = any(kw in str(contact_gender).lower() for kw in ("male", "man", "boy", "he")) and not any(kw in str(contact_gender).lower() for kw in ("female", "woman"))
    partner_gender = "female" if is_char_male else "male"

    # 1. Check if contact has established past intimate partner in intimate_memories
    memories = list(contact.get("intimate_memories", []))
    past_partner_name = ""
    past_partner_role = "Former Classmate"
    for m in memories:
        if "with '" in str(m) or "from '" in str(m):
            import re
            m_match = re.search(r"['\"]([^'\"]+)['\"]\s*\(([^)]+)\)", str(m))
            if m_match:
                past_partner_name = m_match.group(1).strip()
                past_partner_role = m_match.group(2).strip()
                break

    # If not in memories, check predetermined past intimate history
    app_data = contact.get("appearance", {})
    p_intercourse = app_data.get("predetermined_intercourse") or app_data.get("intercourse_experience")
    p_oral = app_data.get("oral_experience") or "inexperienced"
    p_manual = app_data.get("manual_experience") or "inexperienced"
    if not past_partner_name and (p_intercourse and p_intercourse != "virgin" or p_oral != "inexperienced" or p_manual != "inexperienced") and not app_data.get("had_first_time_with_player"):
        from mechanics.social.persona import generate_past_intimate_history
        seed_str = (name + "_past_history").encode("utf-8")
        h_val = int(hashlib.md5(seed_str).hexdigest(), 16)
        past_data = generate_past_intimate_history(intercourse=p_intercourse, oral=p_oral, manual=p_manual, hash_val=h_val, gender=contact_gender, scenario=scenario)
        if past_data:
            past_partner_name = past_data.get("partner_name", "")
            past_partner_role = past_data.get("partner_role", "Former Classmate")

    # Check if contact is an active romantic interest of the player or established as single
    is_romantic_track = str(contact.get("track") or "").strip().lower() == "romantic"
    mems = contact.get("intimate_memories") or []
    if isinstance(mems, str):
        try:
            mems = json.loads(mems)
        except Exception:
            mems = [mems]
    has_relationship_mem = any(any(rc in str(m).lower() for rc in ("relationship", "dating", "lover", "girlfriend", "boyfriend", "accepted")) for m in mems)
    is_player_partner = is_romantic_track

    is_player_interest = (
        is_player_partner
        or contact.get("relationship_score", 0) >= 30
        or app_data.get("intimate_revealed")
        or app_data.get("had_first_time_with_player")
    )
    desc_str = (str(contact.get("description", "")) + " " + str((contact.get("basic_info") or {}).get("description", ""))).lower()
    is_explicitly_single = "single" in desc_str or "unmarried" in desc_str or "unattached" in desc_str

    # Openness-scaled romantic and intimate history rates
    open_str = str(
        app_data.get("erotic_openness")
        or app_data.get("openness")
        or contact.get("openness")
        or (contact.get("basic_info") or {}).get("openness")
        or "moderate"
    ).lower()
    if "prude" in open_str or "modest" in open_str or "chaste" in open_str:
        curr_partner_rate = 8
        ex_partner_rate = 10
        affair_rate = 1
    elif "shameless" in open_str or "lewd" in open_str:
        curr_partner_rate = 35
        ex_partner_rate = 40
        affair_rate = 6
    elif "bold" in open_str or "uninhibited" in open_str:
        curr_partner_rate = 25
        ex_partner_rate = 30
        affair_rate = 4
    else:  # moderate
        curr_partner_rate = 15
        ex_partner_rate = 20
        affair_rate = 2

    if is_player_partner:
        player_name = resolve_player_character_name(contact, session_id=contact.get("session_id", 0))
        score = contact.get("relationship_score", 0)
        role_label = "Lover / Soulmate" if score >= 80 else ("Romantic Partner / Dating" if score >= 40 else "Romantic Partner")
        current_partner = {
            "name": player_name,
            "role": role_label,
            "relationship_type": "Dating / Romantic Partner"
        }
        status = "In a Relationship"
    else:
        # 2. Current Partner roll (openness-scaled chance, suppressed if player interest or explicitly single)
        has_current_partner = (((abs(hash_val) * 29 + 11) % 100) < curr_partner_rate) and not is_player_interest and not is_explicitly_single
        current_partner = None
        if has_current_partner:
            c_partner_first = get_deterministic_firstname(scenario, partner_gender, hash_val * 41 + 13)
            c_partner_last = get_deterministic_surname(scenario, hash_val * 43 + 17)
            c_partner_role = namegen.generate_role(scenario, hash_val=hash_val * 47 + 19)
            current_partner = {
                "name": f"{c_partner_first} {c_partner_last}",
                "role": c_partner_role,
                "relationship_type": "Dating / Partner"
            }
        status = "In a Relationship" if current_partner else "Single"

    # 3. Secret Affair roll (openness-scaled chance)
    has_secret_affair = ((abs(hash_val) * 31 + 23) % 100) < affair_rate
    secret_partner = None
    if has_secret_affair:
        s_partner_first = get_deterministic_firstname(scenario, partner_gender, hash_val * 53 + 7)
        s_partner_last = get_deterministic_surname(scenario, hash_val * 59 + 11)
        s_partner_role = namegen.generate_role(scenario, hash_val=hash_val * 61 + 13)
        secret_partner = {
            "name": f"{s_partner_first} {s_partner_last}",
            "role": s_partner_role,
            "relationship_type": "Secret Affair / Lover"
        }

    # 4. Ex-Partners roll (openness-scaled chance, or guaranteed if past intimate history exists)
    has_ex = ((abs(hash_val) * 37 + 19) % 100) < ex_partner_rate or bool(past_partner_name)
    ex_partners = []
    if past_partner_name:
        ex_partners.append({
            "name": past_partner_name,
            "role": past_partner_role,
            "notes": "Past Romantic / Intimate Partner"
        })
    elif has_ex:
        ex_first = get_deterministic_firstname(scenario, partner_gender, hash_val * 67 + 31)
        ex_last = get_deterministic_surname(scenario, hash_val * 71 + 37)
        ex_role = namegen.generate_role(scenario, hash_val=hash_val * 73 + 41)
        ex_partners.append({
            "name": f"{ex_first} {ex_last}",
            "role": ex_role,
            "notes": "Former High School Romance"
        })

    return {
        "status": status,
        "current_partner": current_partner,
        "secret_partner": secret_partner,
        "ex_partners": ex_partners
    }


def generate_friends_and_rivals(
    contact: dict,
    scenario: str = "fantasy",
    hash_val: int = 0
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Generates 1-2 close friends and 1 rival for the character."""
    name = contact.get("name", "Unknown NPC")
    contact_gender = contact.get("gender") or "female"

    # Friends (1 to 2)
    friend_count = 1 if ((abs(hash_val) % 100) < 65) else 2
    friends = []
    for i in range(friend_count):
        f_hash = hash_val * 83 + (i + 1) * 97
        f_gender = "female" if ((abs(f_hash) % 2) == 0) else "male"
        f_first = get_deterministic_firstname(scenario, f_gender, f_hash)
        f_last = get_deterministic_surname(scenario, f_hash * 3 + 7)
        f_role = namegen.generate_role(scenario, hash_val=f_hash)
        friends.append({
            "name": f"{f_first} {f_last}",
            "role": f_role,
            "closeness": "Close Friend / Confidant" if i == 0 else "Good Friend"
        })

    # Rival (1)
    r_hash = hash_val * 101 + 53
    r_gender = contact_gender
    r_first = get_deterministic_firstname(scenario, r_gender, r_hash)
    r_last = get_deterministic_surname(scenario, r_hash * 5 + 17)
    r_role = namegen.generate_role(scenario, hash_val=r_hash)
    rivals = [{
        "name": f"{r_first} {r_last}",
        "role": r_role,
        "type": "Fierce Rival / Competitor"
    }]

    return (friends, rivals)


def _get_raw_contact_gender_and_grade(session_id: int, name_query: str) -> tuple[str, str]:
    """Safely looks up gender and grade without triggering get_contact post-processing recursion."""
    if not session_id or not name_query:
        return ("", "")
    try:
        import db
        with db.get_conn() as conn:
            q_clean = name_query.strip().lower()
            row = conn.execute(
                """SELECT gender, basic_info_json FROM contacts
                   WHERE session_id=? AND (lower(npc_id)=? OR lower(name)=? OR lower(name) LIKE ?)
                   LIMIT 1""",
                (session_id, q_clean, q_clean, f"{q_clean}%")
            ).fetchone()
            if row:
                g = str(row["gender"] or "").strip()
                gr = ""
                try:
                    b = json.loads(row["basic_info_json"] or "{}")
                    gr = b.get("grade", "")
                except Exception:
                    pass
                return (g, gr)
    except Exception:
        pass
    return ("", "")


def _register_named_sibling(
    session_id: int,
    clean_surname: str,
    sib_name: str,
    children_dict: dict,
    child_race: str,
    child_appearance: dict,
    grade_order: dict
) -> bool:
    """Helper to register an explicitly named sibling into the children roster deterministically."""
    if not sib_name:
        return False
    s_first, _ = extract_surname_and_firstname(sib_name)
    if not s_first or s_first.lower() in children_dict:
        return False

    s_gender, s_grade = _get_raw_contact_gender_and_grade(session_id, sib_name)
    if not s_gender:
        s_gender, s_grade = _get_raw_contact_gender_and_grade(session_id, s_first)
    if not s_gender:
        if namegen.is_known_female_name(s_first):
            s_gender = "female"
        elif namegen.is_known_male_name(s_first):
            s_gender = "male"
        else:
            s_gender = "female" if any(f in s_first.lower() for f in ["sofia", "sophia", "maya", "elena", "chloe", "hana", "seraphina", "alina", "anna", "ann", "amanda", "yea-ji", "zihan", "mia", "ayane", "su-bin"]) else "male"

    if not s_grade:
        s_grade = "Senior" if s_first.lower() in ("amanda", "ann", "andrew") else ("Freshman" if s_first.lower() in ("maya", "su-bin") else "Junior")

    s_role = "Drama Club Lead" if "amanda" in s_first.lower() else ("Library Assistant" if "ann" in s_first.lower() else ("Student" if "maya" in s_first.lower() else "Student"))
    s_full = namegen.format_cultural_full_name(
        s_first, clean_surname, gender=s_gender,
        deterministic_seed=f"sib_linked_{s_first}_{clean_surname}"
    ).strip()

    children_dict[s_first.lower()] = {
        "name": s_full,
        "first_name": s_first,
        "surname": clean_surname,
        "grade": s_grade,
        "grade_val": grade_order.get(s_grade, 2),
        "gender": s_gender,
        "role": s_role,
        "race": child_race,
        "status": "Alive",
        "sibling_name": sib_name,
        "features": f"{child_appearance.get('eyes', 'Amber')} eyes, {child_appearance.get('hair', 'Golden-Blonde')} hair"
    }
    return True


# ==============================================================================
# CANONICAL SHARED HOUSEHOLD LINEAGE ENGINE (ARCHITECTURE 1)
# ==============================================================================

def _resolve_child_race(contact: dict, session_id: int, scenario: str) -> str:
    child_race = contact.get("race") or (contact.get("basic_info") or {}).get("race") or ""
    if not child_race:
        try:
            import db
            c_name_raw = contact.get("name", "")
            if session_id and c_name_raw:
                with db.get_conn() as conn:
                    lb_row = conn.execute(
                        "SELECT race FROM lorebook WHERE session_id=? AND lower(name)=? AND entity_type='person' LIMIT 1",
                        (session_id, c_name_raw.lower())
                    ).fetchone()
                if lb_row and lb_row["race"] and str(lb_row["race"]).strip().lower() not in ("", "unknown"):
                    child_race = lb_row["race"].strip()
        except Exception:
            pass
    if not child_race:
        from mechanics.social.races import extract_race_from_text
        desc_text = (contact.get("basic_info") or {}).get("description", "") or ""
        if desc_text:
            child_race = extract_race_from_text(desc_text, scen_key=scenario, name=contact.get("name", "")) or ""
    if not child_race:
        child_race = "human"
    return child_race


def _determine_shared_residence_location(surname: str, scenario: str) -> str:
    from scenario_data import has_tag
    is_school = (
        has_tag(scenario, "high_school") or
        has_tag(scenario, "high_school_drama") or
        has_tag(scenario, "academy") or
        "school" in str(scenario).lower() or
        "high_school" in str(scenario).lower() or
        "modern" in str(scenario).lower()
    )
    if is_school:
        return f"Suburban Residential District -> {surname} Residence"
    elif "scifi" in str(scenario).lower() or "cyberpunk" in str(scenario).lower():
        return f"Sector 4 Habitation Complex -> {surname} Pod"
    else:
        return f"Upper Ward -> {surname} Estate"


def _apply_non_traditional_family_status(father: dict, mother: dict, contact: dict):
    desc = ((contact.get("basic_info") or {}).get("description") or "").lower()
    traits = " ".join((contact.get("unlocked_traits") or []) + (contact.get("basic_info", {}).get("traits") or [])).lower()
    text = f"{desc} {traits}"

    if any(w in text for w in ("orphan", "lost both parents", "abandoned by parents")):
        father["status"] = "Deceased"
        mother["status"] = "Deceased"
    else:
        if any(w in text for w in ("late father", "deceased father", "father passed", "lost her father", "lost his father", "single mother", "raised by her mother", "raised by his mother")):
            father["status"] = "Deceased"
        elif any(w in text for w in ("estranged father", "absent father", "abandoned by father", "disowned by father")):
            father["status"] = "Estranged"

        if any(w in text for w in ("late mother", "deceased mother", "mother passed", "lost her mother", "lost his mother", "single father", "raised by her father", "raised by his father")):
            mother["status"] = "Deceased"
        elif any(w in text for w in ("estranged mother", "absent mother", "abandoned by mother", "disowned by mother")):
            mother["status"] = "Estranged"


def _link_contact_to_household(session_id: int, contact: dict, household_id: int):
    contact["household_id"] = household_id
    c_id = contact.get("id")
    c_nid = contact.get("npc_id") or contact.get("name")
    if session_id and (c_id or c_nid):
        try:
            import db
            db.assign_contact_household(session_id, c_id or c_nid, household_id)
        except Exception:
            pass


def _generate_narrative_siblings(
    father: dict,
    mother: dict,
    child_appearance: dict,
    clean_surname: str,
    known_contact: dict,
    session_contacts: list,
    scenario: str,
    household_hash: int,
    is_anderson: bool,
    is_vance: bool
) -> list[dict]:
    if is_anderson:
        return []

    narrative_siblings = []

    # Vance household canon: Mia Vance (Older Sister / Off-Campus College Student)
    if is_vance:
        narrative_siblings.append({
            "name": "Mia Vance",
            "first_name": "Mia",
            "surname": "Vance",
            "relation": "Older Sister",
            "role": "Student",
            "grade": "Junior",
            "race": father.get("race", "half_beast:fennec"),
            "gender": "female",
            "status": "Alive",
            "is_contactable": True,
            "features": f"{child_appearance.get('eyes', 'Amber')} eyes, {child_appearance.get('hair', 'Golden-Blonde')} hair"
        })
        return narrative_siblings

    # Procedural generation:
    existing_contacts_names = {c.get("name", "").lower() for c in session_contacts}
    existing_contacts_names.add(known_contact.get("name", "").lower())

    sib_linked = (known_contact.get("basic_info") or {}).get("sibling_name")
    if sib_linked and sib_linked.lower() not in existing_contacts_names:
        s_first, s_last = extract_surname_and_firstname(sib_linked)
        if not s_last:
            s_last = clean_surname
        from namegen import is_known_female_name, is_known_male_name
        s_gen = "female" if is_known_female_name(s_first) else ("male" if is_known_male_name(s_first) else "female")
        narrative_siblings.append({
            "name": f"{s_first} {s_last}",
            "first_name": s_first,
            "surname": s_last,
            "relation": "Sister" if s_gen == "female" else "Brother",
            "role": "Student",
            "grade": "Sophomore",
            "race": father.get("race", "human"),
            "gender": s_gen,
            "status": "Alive",
            "is_contactable": True,
            "features": f"{child_appearance.get('eyes', 'Amber')} eyes"
        })

    if len(narrative_siblings) < 1:
        c_grade = (known_contact.get("basic_info") or {}).get("grade", "Junior")
        proc_sibs = generate_siblings(
            father, mother, child_appearance,
            scenario=scenario, hash_val=household_hash,
            contact_grade=c_grade,
            existing_sibling_count=len(narrative_siblings)
        )
        for ps in proc_sibs:
            p_first = ps.get("first_name", "")
            f_first = father.get("first_name", "")
            m_first = mother.get("first_name", "")
            p_full = ps.get("name", f"{p_first} {clean_surname}")
            if p_full.lower() not in existing_contacts_names and p_first.lower() != f_first.lower() and p_first.lower() != m_first.lower():
                is_older = "older" in ps.get("relation", "").lower()
                p_grade = ps.get("grade") or ("Senior" if is_older else "Freshman")
                narrative_siblings.append({
                    "name": p_full,
                    "first_name": p_first,
                    "surname": clean_surname,
                    "relation": ps.get("relation", "Sister" if ps.get("gender") == "female" else "Brother"),
                    "grade": p_grade,
                    "gender": ps.get("gender", "female"),
                    "role": ps.get("occupation", "Student"),
                    "club": ps.get("club", ""),
                    "race": ps.get("race", father.get("race", "human")),
                    "status": ps.get("status", "Alive"),
                    "is_contactable": ps.get("is_contactable", False),
                    "features": ps.get("features", f"{child_appearance.get('eyes', 'Amber')} eyes")
                })
                break
    return narrative_siblings


def _hydrate_household_entity(hh: dict, contact: dict, scenario: str) -> dict:
    import db
    household = dict(hh)
    if isinstance(household.get("father"), str):
        try:
            household["father"] = json.loads(household["father"])
        except Exception:
            household["father"] = {}
    if isinstance(household.get("mother"), str):
        try:
            household["mother"] = json.loads(household["mother"])
        except Exception:
            household["mother"] = {}
    if isinstance(household.get("narrative_siblings"), str):
        try:
            household["narrative_siblings"] = json.loads(household["narrative_siblings"])
        except Exception:
            household["narrative_siblings"] = []

    clean_surname = household.get("surname", "")
    is_anderson = clean_surname.lower() == "anderson"

    grade_order = {"Faculty": 5, "Senior": 4, "Junior": 3, "Sophomore": 2, "Freshman": 1}
    children_dict = {}

    f_info = household.get("father") or {}
    m_info = household.get("mother") or {}
    f_name = f_info.get("name", "")
    m_name_val = m_info.get("name", "")
    f_first, _ = extract_surname_and_firstname(f_name) if f_name else ("", "")
    m_first, _ = extract_surname_and_firstname(m_name_val) if m_name_val else ("", "")

    # Query active contact members from SQLite
    if household.get("id"):
        members = db.get_household_members(household["id"])
        for m in members:
            m_name = m.get("name", "")
            m_first_c, _ = extract_surname_and_firstname(m_name)

            # Check if this member is the father or mother; if so, link and do not add to children
            is_parent = False
            if f_name and (m_name.lower() == f_name.lower() or (m_first_c and f_first and m_first_c.lower() == f_first.lower())):
                household["father"]["id"] = m.get("id")
                household["father"]["npc_id"] = m.get("npc_id")
                household["father"]["is_contactable"] = True
                is_parent = True
            elif m_name_val and (m_name.lower() == m_name_val.lower() or (m_first_c and m_first and m_first_c.lower() == m_first.lower())):
                household["mother"]["id"] = m.get("id")
                household["mother"]["npc_id"] = m.get("npc_id")
                household["mother"]["is_contactable"] = True
                is_parent = True

            if is_parent:
                continue

            m_b = m.get("basic_info") or {}
            m_gr = m_b.get("grade", "Junior")
            m_gen = m.get("gender") or "female"
            m_rl = m_b.get("role", "Student")
            m_race = m.get("race") or household.get("father", {}).get("race")
            m_app = m.get("appearance") or {}
            children_dict[m_first_c.lower()] = {
                "id": m.get("id"),
                "npc_id": m.get("npc_id"),
                "name": m_name,
                "first_name": m_first_c,
                "surname": clean_surname,
                "grade": m_gr,
                "grade_val": grade_order.get(m_gr, 2),
                "gender": m_gen,
                "role": m_rl,
                "club": m_b.get("club", ""),
                "race": m_race,
                "status": "Alive",
                "is_contactable": True,
                "features": m_app.get("features", f"{m_app.get('eyes', 'Amber')} eyes, {m_app.get('hair', 'Golden-Blonde')} hair")
            }

    # Add narrative siblings
    for ns in household.get("narrative_siblings", []):
        ns_first = ns.get("first_name") or ns.get("name", "").split()[0]
        if ns_first.lower() not in children_dict:
            ns_gr = ns.get("grade", "Junior")
            children_dict[ns_first.lower()] = {
                "name": ns.get("name"),
                "first_name": ns_first,
                "surname": clean_surname,
                "grade": ns_gr,
                "grade_val": grade_order.get(ns_gr, 2),
                "gender": ns.get("gender", "female"),
                "role": ns.get("role") or ns.get("occupation", "Student"),
                "club": ns.get("club", ""),
                "race": ns.get("race") or household.get("father", {}).get("race"),
                "status": ns.get("status", "Alive"),
                "is_contactable": ns.get("is_contactable", False),
                "features": ns.get("features", "")
            }

    # Also ensure calling contact itself is included (unless it is father or mother)
    c_name = contact.get("name", "")
    c_first, _ = extract_surname_and_firstname(c_name)
    is_calling_parent = False
    if f_name and (c_name.lower() == f_name.lower() or (c_first and f_first and c_first.lower() == f_first.lower())):
        is_calling_parent = True
        household["father"]["id"] = contact.get("id")
        household["father"]["npc_id"] = contact.get("npc_id")
        household["father"]["is_contactable"] = True
    elif m_name_val and (c_name.lower() == m_name_val.lower() or (c_first and m_first and c_first.lower() == m_first.lower())):
        is_calling_parent = True
        household["mother"]["id"] = contact.get("id")
        household["mother"]["npc_id"] = contact.get("npc_id")
        household["mother"]["is_contactable"] = True

    if not is_calling_parent and c_first and c_first.lower() not in children_dict:
        c_b = contact.get("basic_info") or {}
        c_gr = c_b.get("grade", "Junior")
        children_dict[c_first.lower()] = {
            "id": contact.get("id"),
            "npc_id": contact.get("npc_id"),
            "name": c_name,
            "first_name": c_first,
            "surname": clean_surname,
            "grade": c_gr,
            "grade_val": grade_order.get(c_gr, 2),
            "gender": contact.get("gender") or "female",
            "role": c_b.get("role", "Student"),
            "club": c_b.get("club", ""),
            "race": contact.get("race") or household.get("father", {}).get("race"),
            "status": "Alive",
            "is_contactable": True,
            "features": (contact.get("appearance") or {}).get("features", "")
        }

    if is_anderson:
        household["father"]["race"] = "beastfolk:fox"
        household["mother"]["race"] = "beastfolk:fox"
        anderson_roster = {
            "amanda": ("Amanda Anderson", "Senior", 4, "Drama Club Lead"),
            "sofia": ("Sofia Anderson", "Junior", 3, "Robotics & Tech Apprentice"),
            "maya": ("Maya Anderson", "Freshman", 1, "Student Council Junior Aide")
        }
        # Strictly purge any non-canonical children from the Anderson household
        children_dict = {k: v for k, v in children_dict.items() if k in anderson_roster}
        for a_key, (a_name, a_grade, a_gval, a_role) in anderson_roster.items():
            if a_key not in children_dict:
                children_dict[a_key] = {
                    "name": a_name,
                    "first_name": a_name.split()[0],
                    "surname": clean_surname,
                    "grade": a_grade,
                    "grade_val": a_gval,
                    "gender": "female",
                    "role": a_role,
                    "race": "beastfolk:fox",
                    "status": "Alive",
                    "is_contactable": True,
                    "features": "Amber eyes, Golden-Blonde hair"
                }
            else:
                children_dict[a_key]["gender"] = "female"
                children_dict[a_key]["race"] = "beastfolk:fox"

    household["children"] = list(children_dict.values())
    return household


def get_or_create_household(
    session_id: int,
    surname: str,
    contact: dict,
    scenario: str = "fantasy"
) -> Dict[str, Any]:
    """
    Retrieves or creates the normalized household entity in SQLite for a character.
    Guarantees 100% symmetric family trees and single source of truth across all siblings.
    """
    clean_surname = namegen.normalize_base_surname((surname or "").strip())
    if not clean_surname:
        first, last = extract_surname_and_firstname(contact.get("name", ""))
        if last:
            clean_surname = last
        else:
            name_seed = int(hashlib.md5(f"{session_id}_{first}".encode("utf-8")).hexdigest(), 16)
            clean_surname = get_deterministic_surname(scenario, name_seed)

    # 1. If session_id is 0 / offline, generate in-memory household
    if not session_id:
        household_seed = f"0_household_{clean_surname.lower()}_v3".encode("utf-8")
        household_hash = int(hashlib.md5(household_seed).hexdigest(), 16)
        child_race = _resolve_child_race(contact, session_id, scenario)
        child_appearance = contact.get("appearance") or {}
        father, mother = reverse_generate_parents(
            child_race=child_race,
            child_appearance=child_appearance,
            child_surname=clean_surname,
            scenario=scenario,
            hash_val=household_hash
        )
        hh = {
            "id": 0,
            "session_id": 0,
            "household_key": f"{clean_surname.lower()}_offline",
            "surname": clean_surname,
            "father": father,
            "mother": mother,
            "narrative_siblings": [],
            "residence_location": _determine_shared_residence_location(clean_surname, scenario)
        }
        return _hydrate_household_entity(hh, contact, scenario)

    import db

    # 2. Check if contact already has household_id assigned
    c_hid = contact.get("household_id")
    if c_hid:
        hh = db.get_household_by_id(c_hid)
        if hh:
            return _hydrate_household_entity(hh, contact, scenario)

    c_first, _ = extract_surname_and_firstname(contact.get("name", ""))
    sib_linked = (contact.get("basic_info") or {}).get("sibling_name")
    is_anderson = clean_surname.lower() == "anderson" and any(k in (c_first.lower(), (sib_linked or "").lower()) for k in ("sofia", "maya", "amanda"))
    is_vance = clean_surname.lower() == "vance" and any(k in (c_first.lower(), (sib_linked or "").lower()) for k in ("su-bin", "subin", "ayane", "andrew", "mia"))

    canonical_key = None
    if is_anderson:
        canonical_key = f"anderson_household_{session_id}"
    elif is_vance:
        canonical_key = f"vance_household_{session_id}"

    if canonical_key:
        hh = db.get_household_by_key(session_id, canonical_key)
        if hh:
            _link_contact_to_household(session_id, contact, hh["id"])
            return _hydrate_household_entity(hh, contact, scenario)

    # 3. Check existing contacts in the session for matching household
    session_contacts = db.get_contacts(session_id, resolve_relations=False, ensure_scene=False) or []
    target_names = {contact.get("name", "").lower(), c_first.lower()}
    if sib_linked:
        target_names.add(sib_linked.lower())
        s_first, _ = extract_surname_and_firstname(sib_linked)
        if s_first:
            target_names.add(s_first.lower())

    for other_c in session_contacts:
        if other_c.get("id") == contact.get("id") and contact.get("id"):
            continue
        o_name = other_c.get("name", "")
        o_first, o_last = extract_surname_and_firstname(o_name)
        if o_last.lower() == clean_surname.lower() and other_c.get("household_id"):
            o_b = other_c.get("basic_info") or {}
            other_sib = o_b.get("sibling_name", "")
            other_fam = [
                str(f.get("name") or "").lower()
                for f in (other_c.get("relations") or {}).get("family", [])
                if isinstance(f, dict) and any(k in str(f.get("relation", "")).lower() for k in ("sister", "brother", "sibling", "twin"))
            ]
            is_linked = False
            if other_sib and any(tn in other_sib.lower() for tn in target_names):
                is_linked = True
            elif any(o_first.lower() in tn or o_name.lower() in tn for tn in target_names):
                is_linked = True
            elif any(any(tn in fn for tn in target_names) for fn in other_fam):
                is_linked = True
            elif is_anderson and o_first.lower() in ("sofia", "maya", "amanda") and c_first.lower() in ("sofia", "maya", "amanda"):
                is_linked = True
            elif is_vance and o_first.lower() in ("su-bin", "subin", "ayane", "andrew", "mia") and c_first.lower() in ("su-bin", "subin", "ayane", "andrew", "mia"):
                is_linked = True

            if is_linked:
                hh = db.get_household_by_id(other_c["household_id"])
                if hh:
                    _link_contact_to_household(session_id, contact, hh["id"])
                    return _hydrate_household_entity(hh, contact, scenario)

    # 4. Create new household record in SQLite
    if not canonical_key:
        c_unique = contact.get("id") or contact.get("npc_id") or abs(hash(contact.get("name", "")))
        canonical_key = f"{clean_surname.lower()}_{session_id}_{c_unique}"

    hh = db.get_household_by_key(session_id, canonical_key)
    if hh:
        _link_contact_to_household(session_id, contact, hh["id"])
        return _hydrate_household_entity(hh, contact, scenario)

    child_race = _resolve_child_race(contact, session_id, scenario)
    child_appearance = contact.get("appearance") or {}
    household_seed = f"{session_id}_household_{clean_surname.lower()}_v3".encode("utf-8")
    household_hash = int(hashlib.md5(household_seed).hexdigest(), 16)

    father, mother = reverse_generate_parents(
        child_race=child_race,
        child_appearance=child_appearance,
        child_surname=clean_surname,
        scenario=scenario,
        hash_val=household_hash
    )

    _apply_non_traditional_family_status(father, mother, contact)
    residence_location = _determine_shared_residence_location(clean_surname, scenario)
    narrative_siblings = _generate_narrative_siblings(
        father=father,
        mother=mother,
        child_appearance=child_appearance,
        clean_surname=clean_surname,
        known_contact=contact,
        session_contacts=session_contacts,
        scenario=scenario,
        household_hash=household_hash,
        is_anderson=is_anderson,
        is_vance=is_vance
    )

    hh_id = db.create_household(
        session_id=session_id,
        household_key=canonical_key,
        surname=clean_surname,
        father=father,
        mother=mother,
        narrative_siblings=narrative_siblings,
        residence_location=residence_location
    )

    _link_contact_to_household(session_id, contact, hh_id)

    # Link any unlinked sibling contacts in the session to this newly created household
    for other_c in session_contacts:
        if other_c.get("id") == contact.get("id") and contact.get("id"):
            continue
        o_name = other_c.get("name", "")
        o_first, o_last = extract_surname_and_firstname(o_name)
        if o_last.lower() == clean_surname.lower() and not other_c.get("household_id"):
            o_b = other_c.get("basic_info") or {}
            other_sib = o_b.get("sibling_name", "")
            is_sibling_match = False
            if other_sib and any(tn in other_sib.lower() for tn in target_names):
                is_sibling_match = True
            elif any(o_first.lower() in tn or o_name.lower() in tn for tn in target_names):
                is_sibling_match = True
            elif is_anderson and o_first.lower() in ("sofia", "maya", "amanda") and c_first.lower() in ("sofia", "maya", "amanda"):
                is_sibling_match = True
            elif is_vance and o_first.lower() in ("su-bin", "subin", "ayane", "andrew", "mia") and c_first.lower() in ("su-bin", "subin", "ayane", "andrew", "mia"):
                is_sibling_match = True

            if is_sibling_match:
                _link_contact_to_household(session_id, other_c, hh_id)

    hh = db.get_household_by_id(hh_id)
    return _hydrate_household_entity(hh, contact, scenario)


def get_canonical_family_unit(
    session_id: int,
    surname: str,
    known_contact: dict,
    scenario: str = "fantasy"
) -> Dict[str, Any]:
    """Compatibility alias for get_or_create_household."""
    return get_or_create_household(session_id, surname, contact=known_contact, scenario=scenario)


def build_family_tree_for_member(
    household: Dict[str, Any],
    member_name: str,
    scenario: str = "fantasy"
) -> List[Dict[str, Any]]:
    """
    Constructs the family tree from the perspective of a specific member in the household.
    - If viewed from a child's perspective: Father and Mother are listed with relation='Father'/'Mother',
      and siblings are listed with accurate relative labels ('Older Sister', 'Brother', etc.).
    - If viewed from a parent's perspective: The spouse is listed with relation='Husband'/'Wife',
      and children are listed with relation='Son'/'Daughter'.
    Active contact members include their contact id, npc_id, and is_contactable=True for UI navigation.
    """
    father = dict(household["father"])
    mother = dict(household["mother"])
    children = household.get("children", [])

    grade_order = {"Faculty": 5, "Senior": 4, "Junior": 3, "Sophomore": 2, "Freshman": 1}

    f_name = father.get("name", "")
    m_name_val = mother.get("name", "")
    f_first, _ = extract_surname_and_firstname(f_name) if f_name else ("", "")
    m_first, _ = extract_surname_and_firstname(m_name_val) if m_name_val else ("", "")

    m_target_first, _ = extract_surname_and_firstname(member_name)
    is_father = bool(f_name and (member_name.lower() == f_name.lower() or (m_target_first and f_first and m_target_first.lower() == f_first.lower())))
    is_mother = bool(m_name_val and (member_name.lower() == m_name_val.lower() or (m_target_first and m_first and m_target_first.lower() == m_first.lower())))

    if is_father or is_mother:
        # Build children list from parent's perspective
        descendants = []
        for c in children:
            g_val = str(c.get("gender", "")).strip().lower()
            f_name_c = str(c.get("first_name", "")).strip()
            from namegen import is_known_male_name, is_known_female_name
            is_female = any(kw in g_val for kw in ("female", "woman", "girl", "lady", "she", "her"))
            if not is_female and g_val:
                is_male = any(kw in g_val for kw in ("male", "man", "boy", "lord", "he", "him", "his")) and not any(kw in g_val for kw in ("female", "woman"))
                is_female = not is_male
            elif not g_val:
                is_female = not is_known_male_name(f_name_c) if is_known_male_name(f_name_c) else is_known_female_name(f_name_c)

            rel = "Daughter" if is_female else "Son"
            child_entry = {
                "relation": rel,
                "name": c.get("name"),
                "first_name": c.get("first_name"),
                "surname": household.get("surname"),
                "race": c.get("race") or "",
                "gender": "female" if is_female else "male",
                "status": c.get("status", "Alive"),
                "occupation": c.get("role", "Student"),
                "features": c.get("features", "")
            }
            if c.get("id"):
                child_entry["id"] = c["id"]
            if c.get("npc_id"):
                child_entry["npc_id"] = c["npc_id"]
            if c.get("grade"):
                child_entry["grade"] = c["grade"]
            if c.get("is_contactable"):
                child_entry["is_contactable"] = True
            if c.get("club"):
                child_entry["club"] = c["club"]
            descendants.append(child_entry)

        # Sort descendants: oldest to youngest
        descendants.sort(key=lambda d: -grade_order.get(d.get("grade", "Junior"), 2))
        spouse = dict(mother if is_father else father)
        spouse["relation"] = "Wife" if is_father else "Husband"
        return [spouse] + descendants

    # Perspective of a child: Father, Mother, and Siblings
    target_child = next((c for c in children if c["first_name"].lower() == m_target_first.lower()), None)
    my_grade_val = target_child.get("grade_val", 2) if target_child else 2

    siblings = []
    for c in children:
        if c["first_name"].lower() == m_target_first.lower():
            continue  # Do not list oneself as a sibling

        g_val = str(c.get("gender", "")).strip().lower()
        f_name_c = str(c.get("first_name", "")).strip()

        from namegen import is_known_male_name, is_known_female_name
        is_female = any(kw in g_val for kw in ("female", "woman", "girl", "lady", "she", "her"))
        if not is_female and g_val:
            is_male = any(kw in g_val for kw in ("male", "man", "boy", "lord", "he", "him", "his")) and not any(kw in g_val for kw in ("female", "woman"))
            is_female = not is_male
        elif not g_val:
            if is_known_male_name(f_name_c):
                is_female = False
            elif is_known_female_name(f_name_c):
                is_female = True
            else:
                is_female = True

        other_grade_val = c.get("grade_val", 2)

        if other_grade_val > my_grade_val:
            rel = "Older Sister" if is_female else "Older Brother"
        elif other_grade_val < my_grade_val:
            rel = "Sister" if is_female else "Brother"
        else:
            rel = "Sister" if is_female else "Brother"

        c_role = c.get("role", "Student")
        sib_entry = {
            "relation": rel,
            "name": c.get("name"),
            "first_name": c.get("first_name"),
            "surname": household.get("surname"),
            "race": c.get("race") or "",
            "gender": "female" if is_female else "male",
            "status": c.get("status", "Alive"),
            "occupation": c_role,
            "features": c.get("features", "")
        }
        if c.get("id"):
            sib_entry["id"] = c["id"]
        if c.get("npc_id"):
            sib_entry["npc_id"] = c["npc_id"]
        if c.get("grade"):
            sib_entry["grade"] = c["grade"]
        if c.get("is_contactable"):
            sib_entry["is_contactable"] = True
        if c.get("club"):
            sib_entry["club"] = c["club"]
        siblings.append(sib_entry)

    # Sort siblings: Older first, then younger
    siblings.sort(key=lambda s: 0 if "older" in s["relation"].lower() else 1)

    return [father, mother] + siblings


def build_family_tree_from_household(
    household: Dict[str, Any],
    contact_name: str,
    scenario: str = "fantasy"
) -> List[Dict[str, Any]]:
    """Constructs the perspective family tree from a normalized household entity."""
    return build_family_tree_for_member(household, contact_name, scenario=scenario)


def hydrate_parent_to_contact(session_id: int, household_id: int, parent_role: str = "father") -> dict:
    """
    Promotes a lightweight parent JSON from the household entity into an active contact
    in the contacts table when met or interacted with in the narrative.
    """
    if not session_id or not household_id:
        return {}
    import db
    hh = db.get_household_by_id(household_id)
    if not hh:
        return {}
    role_key = "mother" if any(w in parent_role.lower() for w in ("mother", "mom", "matriarch")) else "father"
    parent = hh.get(role_key) or {}
    if not parent or not parent.get("name"):
        return {}
    p_name = parent["name"]
    p_first, _ = extract_surname_and_firstname(p_name)
    p_gender = parent.get("gender", "female" if role_key == "mother" else "male")
    p_race = parent.get("race", "human")
    p_role = parent.get("occupation", "Parent")
    p_desc = f"{p_role} of the {hh.get('surname', '')} family."

    basic_info = {
        "role": p_role,
        "description": p_desc,
        "status_effects": [],
        "traits": [p_role, f"{hh.get('surname', '')} Household"],
    }
    appearance = {
        "features": parent.get("features", "")
    }
    npc_id = p_name.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("née", "nee").replace("'", "")
    contact = db.upsert_contact(
        session_id=session_id,
        npc_id=npc_id,
        name=p_name,
        basic_info=basic_info,
        race=p_race,
        gender=p_gender,
        appearance=appearance
    )
    if contact and contact.get("id"):
        db.assign_contact_household(session_id, contact["id"], household_id)
        contact["household_id"] = household_id
    return contact


# ==============================================================================
# DYNAMIC SOCIAL GRAPH MUTATION HELPERS (FRIENDS, RIVALS, ROMANCE)
# ==============================================================================

def add_friend_relation(contact_dict: dict, friend_name: str, role: str = "Student", closeness: str = "Good Friend", session_id: int = 0) -> dict:
    """Dynamically adds or upgrades a friend in the contact's relations record."""
    if session_id:
        try:
            import mechanics.social.relationship_graph as rg
            a_key = rg.canonical_person_key(contact_dict.get("name", ""))
            b_key = rg.canonical_person_key(friend_name)
            closeness_val = 80 if any(k in str(closeness).lower() for k in ("close", "best")) else 65
            rg.get_or_create_person(session_id, friend_name, person_key=b_key, role=role)
            rg.form_tie(session_id, a_key, b_key, rg.TIETYPE_FRIEND, closeness=closeness_val)
            mat = rg.materialize_relations(session_id, contact_dict)
            if mat:
                contact_dict["relations"] = mat
                return mat
        except Exception:
            pass

    relations = contact_dict.get("relations") or {}
    friends = relations.setdefault("friends", [])
    for f in friends:
        if f.get("name", "").lower() == friend_name.lower():
            f["closeness"] = closeness
            f["role"] = role or f.get("role", "Friend")
            return relations
    friends.append({
        "name": friend_name,
        "role": role or "Friend",
        "closeness": closeness
    })
    return relations


def add_rival_relation(contact_dict: dict, rival_name: str, role: str = "Student", rival_type: str = "Class Rival", session_id: int = 0) -> dict:
    """Dynamically adds or upgrades a rival/enemy in the contact's relations record."""
    if session_id:
        try:
            import mechanics.social.relationship_graph as rg
            a_key = rg.canonical_person_key(contact_dict.get("name", ""))
            b_key = rg.canonical_person_key(rival_name)
            rg.get_or_create_person(session_id, rival_name, person_key=b_key, role=role)
            rg.form_tie(session_id, a_key, b_key, rg.TIETYPE_RIVAL, closeness=50)
            mat = rg.materialize_relations(session_id, contact_dict)
            if mat:
                contact_dict["relations"] = mat
                return mat
        except Exception:
            pass

    relations = contact_dict.get("relations") or {}
    rivals = relations.setdefault("rivals", [])
    for r in rivals:
        if r.get("name", "").lower() == rival_name.lower():
            r["type"] = rival_type
            r["role"] = role or r.get("role", "Rival")
            return relations
    rivals.append({
        "name": rival_name,
        "role": role or "Rival",
        "type": rival_type
    })
    return relations


def remove_relation(contact_dict: dict, target_name: str, session_id: int = 0) -> dict:
    """Removes a character from both friends and rivals."""
    if session_id:
        try:
            import mechanics.social.relationship_graph as rg
            a_key = rg.canonical_person_key(contact_dict.get("name", ""))
            b_key = rg.canonical_person_key(target_name)
            rg.end_tie(session_id, a_key, b_key, reason="removed")
            mat = rg.materialize_relations(session_id, contact_dict)
            if mat:
                contact_dict["relations"] = mat
                return mat
        except Exception:
            pass

    relations = contact_dict.get("relations") or {}
    t_clean = target_name.strip().lower()
    relations["friends"] = [f for f in relations.get("friends", []) if f.get("name", "").lower() != t_clean]
    relations["rivals"] = [r for r in relations.get("rivals", []) if r.get("name", "").lower() != t_clean]
    return relations


def set_romantic_partner(contact_dict: dict, partner_name: str, role: str = "Lover / Soulmate", status: str = "In a Relationship", session_id: int = 0) -> dict:
    """Dynamically sets an active romantic partner."""
    if session_id:
        try:
            import mechanics.social.relationship_graph as rg
            a_key = rg.canonical_person_key(contact_dict.get("name", ""))
            b_key = rg.canonical_person_key(partner_name)
            tie_type = rg.TIETYPE_DATING
            if "married" in status.lower():
                tie_type = rg.TIETYPE_MARRIED
            elif "engaged" in status.lower():
                tie_type = rg.TIETYPE_ENGAGED
            rg.get_or_create_person(session_id, partner_name, person_key=b_key, role=role)
            rg.form_tie(session_id, a_key, b_key, tie_type, closeness=75, supersede=True)
            mat = rg.materialize_relations(session_id, contact_dict)
            if mat:
                contact_dict["relations"] = mat
                return mat
        except Exception:
            pass

    relations = contact_dict.get("relations") or {}
    relations["romance"] = {
        "status": status,
        "current_partner": {
            "name": partner_name,
            "role": role,
            "relationship_type": "Dating / Romantic Partner"
        },
        "secret_partner": relations.get("romance", {}).get("secret_partner"),
        "ex_partners": relations.get("romance", {}).get("ex_partners", [])
    }
    return relations


def break_up_romantic_partner(contact_dict: dict, session_id: int = 0) -> dict:
    """Breaks up with current partner, moving them to ex-partners."""
    if session_id:
        try:
            import mechanics.social.relationship_graph as rg
            a_key = rg.canonical_person_key(contact_dict.get("name", ""))
            curr = rg.get_current_partner(session_id, a_key)
            if curr:
                rg.end_tie(session_id, a_key, curr["person_key"], curr["tie_type"], reason="breakup")
            mat = rg.materialize_relations(session_id, contact_dict)
            if mat:
                contact_dict["relations"] = mat
                return mat
        except Exception:
            pass

    relations = contact_dict.get("relations") or {}
    rom = relations.get("romance", {})
    curr = rom.get("current_partner")
    exes = rom.get("ex_partners", [])
    if curr and curr.get("name"):
        exes.append({
            "name": curr["name"],
            "role": curr.get("role", "Ex-Partner"),
            "notes": "Recent Breakup"
        })
    rom["status"] = "Single"
    rom["current_partner"] = None
    rom["ex_partners"] = exes
    relations["romance"] = rom
    return relations


def ensure_contact_relations(
    contact: dict,
    session_id: int = 0,
    scenario: str = "fantasy"
) -> Dict[str, Any]:
    """
    Ensures that a contact has complete, deterministic, and synchronized relations data.
    - Synchronizes nuclear family (Parents, maiden names, careers, siblings) across household.
    - Dynamically reflects romantic standing based on contact track.
    - Dynamically keeps social circle (friends & rivals) updated.
    """
    name = contact.get("name", "Unknown NPC")
    first_name, surname = extract_surname_and_firstname(name)

    # Protect Player Character from procedural family invention (Decision 8)
    player_name = resolve_player_character_name(contact, session_id=session_id or contact.get("session_id", 0))
    if contact.get("is_player") or (name and player_name and name.strip().lower() == player_name.strip().lower() and not contact.get("household_id")):
        existing = contact.get("relations")
        if not isinstance(existing, dict):
            existing = {}
        return existing

    # 1. Resolve canonical family household unit
    household = get_or_create_household(session_id, surname, contact=contact, scenario=scenario)
    family_tree = build_family_tree_from_household(household, name, scenario=scenario)

    seed_str = f"{session_id}_{name}_relations_v2".encode("utf-8")
    hash_val = int(hashlib.md5(seed_str).hexdigest(), 16)

    existing = contact.get("relations")
    if not isinstance(existing, dict):
        existing = {}

    # Update/synchronize family tree and shared residence
    existing["family"] = family_tree
    if household.get("residence_location"):
        existing["residence_location"] = household["residence_location"]
    if household.get("id"):
        existing["household_id"] = household["id"]

    # Register contactable student siblings in school_roster for high school scenarios
    from scenario_data import has_tag
    is_school = (
        has_tag(scenario, "high_school") or
        has_tag(scenario, "high_school_drama") or
        has_tag(scenario, "academy") or
        "school" in str(scenario).lower() or
        "high_school" in str(scenario).lower()
    )
    if is_school and session_id:
        try:
            import db
            from mechanics.social.school_roster import generate_sibling_student_peer
            roster = db.get_school_roster(session_id) or []
            existing_names = {str(r.get("name", "")).lower() for r in roster}
            new_recs = []
            for fam in family_tree:
                r_type = str(fam.get("relation", "")).lower()
                is_sib = any(k in r_type for k in ("sister", "brother", "sibling", "twin"))
                fam_name = str(fam.get("name", "")).strip()
                fam_grade = str(fam.get("grade", ""))
                if is_sib and fam_name and fam_name.lower() not in existing_names:
                    if fam_grade in ("Freshman", "Sophomore", "Junior", "Senior") or fam.get("is_contactable"):
                        rec = generate_sibling_student_peer(
                            session_id=session_id,
                            sibling_name=fam_name,
                            known_contact=contact,
                            scen_key=scenario,
                            grade_override=fam_grade,
                            role_override=fam.get("occupation", ""),
                            club_override=fam.get("club", ""),
                            gender=fam.get("gender", ""),
                            relation_type=r_type
                        )
                        new_recs.append(rec)
                        existing_names.add(fam_name.lower())
            if new_recs:
                db.save_school_roster(session_id, new_recs)
        except Exception:
            pass

    # Normalized Relationship Graph Integration (Phase 2 & 3)
    is_romantic_track = str(contact.get("track") or "").strip().lower() == "romantic"
    if session_id:
        try:
            import mechanics.social.relationship_graph as rg
            c_key = rg.canonical_person_key(name)
            p_npc = contact.get("npc_id")

            # Link or create contact person node
            rg.get_or_create_person(
                session_id, name, person_key=c_key,
                gender=contact.get("gender") or "", origin="contact", contact_npc_id=p_npc
            )

            # Check if graph ties are already seeded
            ties = rg.get_ties(session_id, c_key, active_only=False)
            if not ties:
                rg.seed_contact_social_graph(contact, session_id=session_id, scenario=scenario, hash_val=hash_val)

            # Romance track synchronization in graph
            if is_romantic_track:
                char_id = contact.get("character_id") or "default"
                player_key = rg.player_person_key(char_id)
                curr_partner = rg.get_current_partner(session_id, c_key)
                if not curr_partner or curr_partner.get("person_key") != player_key:
                    rg.form_tie(session_id, player_key, c_key, rg.TIETYPE_DATING, closeness=80, supersede=True)
            else:
                curr_partner = rg.get_current_partner(session_id, c_key)
                if curr_partner and curr_partner.get("person_key", "").startswith("player:"):
                    rg.end_tie(session_id, curr_partner["person_key"], c_key, rg.TIETYPE_DATING, reason="track_transition")

                # If contact has an established NON-PLAYER background partner in relations dict, preserve it into graph
                if isinstance(existing.get("romance"), dict):
                    bg_p = existing["romance"].get("current_partner")
                    if bg_p and isinstance(bg_p, dict) and bg_p.get("name"):
                        bg_name = bg_p["name"].strip()
                        if bg_name.lower() not in ("player", "you") and not bg_name.lower().startswith("player:"):
                            bg_key = rg.canonical_person_key(bg_name)
                            rg.get_or_create_person(session_id, bg_name, person_key=bg_key, role=bg_p.get("role", "Partner"))
                            if not curr_partner or curr_partner.get("person_key") != bg_key:
                                rg.form_tie(session_id, c_key, bg_key, rg.TIETYPE_DATING, closeness=70, supersede=True)

            mat = rg.materialize_relations(session_id, contact)
            if mat:
                existing["romance"] = mat.get("romance", {})
                existing["friends"] = mat.get("friends", [])
                existing["rivals"] = mat.get("rivals", [])
                if mat.get("residence_location"):
                    existing["residence_location"] = mat["residence_location"]
                if mat.get("household_id"):
                    existing["household_id"] = mat["household_id"]
                return existing
        except Exception as e:
            logger.warning(f"Failed to synchronize relationship graph for {name}: {e}")

    # Fallback path for offline / unpersisted calls (e.g. unit tests without session_id)
    # 2. Romance track synchronization
    is_romantic_track = str(contact.get("track") or "").strip().lower() == "romantic"
    mems = contact.get("intimate_memories") or []
    if isinstance(mems, str):
        try:
            mems = json.loads(mems)
        except Exception:
            mems = [mems]

    has_relationship_mem = any(any(rc in str(m).lower() for rc in ("relationship", "dating", "lover", "girlfriend", "boyfriend", "accepted")) for m in mems)

    if not existing.get("romance"):
        existing["romance"] = generate_relationship_status(contact, scenario=scenario, hash_val=hash_val)

    if is_romantic_track:
        score = contact.get("relationship_score", 0)
        role_label = "Lover / Soulmate" if score >= 80 else ("Romantic Partner / Dating" if score >= 40 else "Romantic Partner")

        # Preserve any existing non-player partner in ex_partners so canon history is retained
        curr_p = existing["romance"].get("current_partner")
        if curr_p and isinstance(curr_p, dict) and curr_p.get("name") and curr_p.get("name") != player_name:
            if "ex_partners" not in existing["romance"] or not isinstance(existing["romance"]["ex_partners"], list):
                existing["romance"]["ex_partners"] = []
            if not any(e.get("name") == curr_p.get("name") for e in existing["romance"]["ex_partners"] if isinstance(e, dict)):
                existing["romance"]["ex_partners"].append(curr_p)

        existing["romance"]["status"] = "In a Relationship"
        existing["romance"]["current_partner"] = {
            "name": player_name,
            "role": role_label,
            "relationship_type": "Dating / Romantic Partner"
        }
    else:
        # Platonic track: if current partner was player, reset partner to None
        c_part = existing["romance"].get("current_partner")
        if c_part and (c_part.get("name") == "Player" or c_part.get("name") == resolve_player_character_name(contact, session_id=session_id)):
            existing["romance"]["current_partner"] = None
            existing["romance"]["status"] = "Single"

    # 3. Friends & Rivals
    if not existing.get("friends") or not existing.get("rivals"):
        f_list, r_list = generate_friends_and_rivals(contact, scenario=scenario, hash_val=hash_val)
        if not existing.get("friends"):
            existing["friends"] = f_list
        if not existing.get("rivals"):
            existing["rivals"] = r_list

    # 4. Register contactable student siblings in school_roster for high school scenarios
    from scenario_data import has_tag
    is_school = (
        has_tag(scenario, "high_school") or
        has_tag(scenario, "high_school_drama") or
        has_tag(scenario, "academy") or
        "school" in str(scenario).lower() or
        "high_school" in str(scenario).lower()
    )
    if is_school and session_id:
        try:
            import db
            from mechanics.social.school_roster import generate_sibling_student_peer
            roster = db.get_school_roster(session_id) or []
            existing_names = {str(r.get("name", "")).lower() for r in roster}
            new_recs = []
            for fam in family_tree:
                r_type = str(fam.get("relation", "")).lower()
                is_sib = any(k in r_type for k in ("sister", "brother", "sibling", "twin"))
                fam_name = str(fam.get("name", "")).strip()
                fam_grade = str(fam.get("grade", ""))
                if is_sib and fam_name and fam_name.lower() not in existing_names:
                    if fam_grade in ("Freshman", "Sophomore", "Junior", "Senior") or fam.get("is_contactable"):
                        rec = generate_sibling_student_peer(
                            session_id=session_id,
                            sibling_name=fam_name,
                            known_contact=contact,
                            scen_key=scenario,
                            grade_override=fam_grade,
                            role_override=fam.get("occupation", ""),
                            club_override=fam.get("club", ""),
                            gender=fam.get("gender", ""),
                            relation_type=r_type
                        )
                        new_recs.append(rec)
                        existing_names.add(fam_name.lower())
            if new_recs:
                db.save_school_roster(session_id, new_recs)
        except Exception:
            pass

    # 5. Persist relations to DB and synchronize across all sibling contacts in the same household
    if session_id:
        try:
            import db
            c_id = contact.get("id")
            if c_id:
                with db.get_conn() as conn:
                    conn.execute("UPDATE contacts SET relations_json = ? WHERE id = ?", (json.dumps(existing), c_id))

            for sibling in household.get("children", []):
                s_name = sibling.get("name", "")
                if s_name.lower() == name.lower():
                    continue
                s_first = sibling.get("first_name", "")
                sib_contact = db.get_contact(session_id, s_first.lower()) or db.get_contact(session_id, s_name.lower().replace(" ", "_"))
                if sib_contact and sib_contact.get("id") and sib_contact.get("id") != c_id:
                    sib_tree = build_family_tree_from_household(household, s_name, scenario=scenario)
                    s_rel = sib_contact.get("relations")
                    if not isinstance(s_rel, dict):
                        s_rel = {}
                    s_rel["family"] = sib_tree
                    if household.get("residence_location"):
                        s_rel["residence_location"] = household["residence_location"]
                    if household.get("id"):
                        s_rel["household_id"] = household["id"]
                    with db.get_conn() as conn:
                        conn.execute("UPDATE contacts SET relations_json = ? WHERE id = ?", (json.dumps(s_rel), sib_contact["id"]))
        except Exception:
            pass

    return existing


def format_relations_for_disclosure(
    relations: dict,
    info_level: int = 1,
    debug_reveal: bool = False
) -> Dict[str, Any]:
    """
    Applies strict 3-tier progressive information disclosure to relations:
    - Level 1: Surface hints (Public marital/dating status, general friends/rivals hints).
      Family is completely locked.
    - Level 2: Friends and open rivals detailed. Family & secret affairs remain locked.
    - Level 3: Full unredacted family tree, parents, siblings, exes, and secret affairs.
    """
    if debug_reveal:
        info_level = 3

    output = {}

    # 1. Family Tree (Level 3 Required)
    if info_level >= 3:
        raw_members = relations.get("family", [])
        norm_members = []
        for m in raw_members:
            if isinstance(m, dict):
                m_copy = dict(m)
                if not m_copy.get("name"):
                    first = m_copy.get("first_name", "").strip()
                    last = m_copy.get("surname", "").strip()
                    m_copy["name"] = f"{first} {last}".strip() or "Unknown"
                norm_members.append(m_copy)
            else:
                norm_members.append(m)
        output["family"] = {
            "revealed": True,
            "members": norm_members
        }
    else:
        output["family"] = {
            "revealed": False,
            "locked_message": "🔒 Family Tree & Lineage is guarded. (Requires Information Disclosure Level 3/3 or Confidant standing)"
        }

    # 2. Romantic Standing
    romance = relations.get("romance", {})
    current_partner = romance.get("current_partner")
    secret_partner = romance.get("secret_partner")
    ex_partners = romance.get("ex_partners", [])

    if info_level >= 3:
        output["romance"] = {
            "revealed": True,
            "status": romance.get("status", "Single"),
            "current_partner": current_partner,
            "secret_partner": secret_partner,
            "ex_partners": ex_partners
        }
    elif info_level >= 2:
        output["romance"] = {
            "revealed": True,
            "status": romance.get("status", "Single"),
            "current_partner": current_partner,
            "secret_partner": {"locked": True, "message": "🔒 Secret Affairs & Lovers (Requires Level 3)"} if secret_partner else None,
            "ex_partners": [{"locked": True, "message": f"🔒 {len(ex_partners)} Past Relationship(s) Recorded (Requires Level 3)"}] if ex_partners else []
        }
    else:
        # Level 1
        output["romance"] = {
            "revealed": False,
            "status": romance.get("status", "Single") if not secret_partner else "Unknown",
            "current_partner": {"name": "Known Partner", "role": "Public Knowledge"} if current_partner else None,
            "secret_partner": None,
            "ex_partners": []
        }

    # 3. Friends & Social Circle (Level 2 Required)
    friends = relations.get("friends", [])
    if info_level >= 2:
        output["friends"] = {
            "revealed": True,
            "members": friends
        }
    else:
        output["friends"] = {
            "revealed": False,
            "members": [{"name": f.get("name", "Classmate"), "role": f.get("role", "Acquaintance"), "closeness": "Known Associate"} for f in friends] if friends else []
        }

    # 4. Rivals & Grudges (Level 2 Required)
    rivals = relations.get("rivals", [])
    if info_level >= 2:
        output["rivals"] = {
            "revealed": True,
            "members": rivals
        }
    else:
        output["rivals"] = {
            "revealed": False,
            "members": [{"name": r.get("name", "Competitor"), "role": "Known Rival", "type": "Rumored Tension"} for r in rivals] if rivals else []
        }

    return output


def _retrieve_contextual_memories(
    query_text: str,
    memories: list,
    max_recent: int = 3,
    max_recalled: int = 2
) -> list[str]:
    """Dynamically substitutes older memories into the prompt budget when referenced by the player.
    Guarantees total returned memories <= (max_recent + max_recalled), preserving 0% net token increase.
    """
    if not memories:
        return []
    if len(memories) <= max_recent:
        return [str(m) for m in memories]

    recent_slice = memories[-max_recent:]
    recent_set = set(str(m) for m in recent_slice)
    older_mems = [m for m in memories if str(m) not in recent_set]

    if not older_mems or not query_text:
        return [str(m) for m in memories[-5:]]

    q_lower = query_text.lower()

    # Check if query contains recall / query indicators or distinctive event cues
    recall_cues = (
        "remember", "recall", "back when", "that time", "our first", "first time",
        "when we", "did you forget", "we once", "that night", "that day", "used to",
        "do you still", "don't you remember", "you remember"
    )
    is_recall_query = any(rc in q_lower for rc in recall_cues)

    # Extract significant search tokens (length >= 3, excluding common stop words)
    stopwords = {
        "the", "and", "that", "this", "with", "for", "have", "had", "was",
        "were", "what", "when", "where", "which", "who", "whom", "will", "would",
        "you", "your", "our", "are", "about", "from", "then", "them", "they",
        "she", "her", "his", "him", "just", "like", "some", "more", "also", "into"
    }
    raw_tokens = re.findall(r'[a-zA-Z]{3,}', q_lower)
    search_tokens = [t for t in raw_tokens if t not in stopwords]

    if not search_tokens and not is_recall_query:
        return [str(m) for m in memories[-5:]]

    min_score = 1 if is_recall_query else 2
    scored_candidates = []
    for m in older_mems:
        m_str = str(m)
        m_lower = m_str.lower()
        score = 0
        for token in search_tokens:
            if token in m_lower:
                score += 1
                if len(token) >= 5:
                    score += 1

        # Boost multi-word phrase matches from query
        for phrase in ("first kiss", "first time", "last night", "in the library", "in the bedroom", "stargazing", "courtyard"):
            if phrase in q_lower and phrase in m_lower:
                score += 3

        if score >= min_score:
            scored_candidates.append((score, m_str))

    if not scored_candidates:
        return [str(m) for m in memories[-5:]]

    # Sort by highest match score, breaking ties by order (more recent first)
    scored_candidates.sort(key=lambda x: x[0], reverse=True)
    recalled_mems = [f"[RECALLED PAST MOMENT]: {cand[1]}" for cand in scored_candidates[:max_recalled]]

    # Combine recalled + recent (max 2 recalled + 3 recent = max 5 items total)
    return recalled_mems + [str(m) for m in recent_slice]


def build_topic_aware_npc_context(
    contact: dict,
    actions: list = None,
    session_history: list = None,
    scenario: str = "fantasy"
) -> str:
    """
    Constructs an ultra-dense, token-efficient canon grounding block for an active dialogue partner.
    Dynamically gates personal background dossiers based on the player's action and conversation topic:
    - Family & Lineage (Parents, Siblings, exact composition)
    - Romantic History & Past Exes
    - Social Circle (Friends & Rivals)
    - Established Shared Milestones with the Player (Intimate Memories, Confessions, First Kiss, etc.)
    - Intimate Preferences (Sensitive spots, turn-ons, demeanor) during romantic/intimate scenes.
    """
    if not contact or not isinstance(contact, dict):
        return ""

    name = contact.get("name", "NPC")
    relations = contact.get("relations") or {}
    appr = contact.get("appearance") or {}

    # Extract action text and recent history for topic detection
    act_pieces = []
    if actions:
        if isinstance(actions, str):
            act_pieces.append(actions)
        elif isinstance(actions, (list, tuple)):
            for a in actions:
                if isinstance(a, dict):
                    act_pieces.append(str(a.get("label", "")) + " " + str(a.get("text", "")))
                else:
                    act_pieces.append(str(a))
        else:
            act_pieces.append(str(actions))
    if session_history and isinstance(session_history, list):
        for h in session_history[-2:]:
            if isinstance(h, dict):
                act_pieces.append(str(h.get("action_label", "")) + " " + str(h.get("action", "")))
            else:
                act_pieces.append(str(h))

    act_lower = " ".join(act_pieces).lower()

    sections = []

    # 1. Family & Lineage Topic
    family_kws = (
        "family", "parents", "parent", "father", "mother", "dad", "mom",
        "brother", "brothers", "sister", "sisters", "sibling", "siblings",
        "childhood", "upbringing", "home life", "grow up", "grew up",
        "lineage", "relative", "relatives", "household", "family brand"
    )
    if any(kw in act_lower for kw in family_kws):
        family = relations.get("family", [])
        if family:
            f_list = [m for m in family if "father" in m.get("relation", "").lower()]
            m_list = [m for m in family if "mother" in m.get("relation", "").lower()]
            sibs = [m for m in family if any(w in m.get("relation", "").lower() for w in ("sister", "brother", "sibling"))]

            f_str = f"{f_list[0].get('name')} ({f_list[0].get('occupation', 'Parent')})" if f_list else "Unknown"
            m_str = f"{m_list[0].get('name')} ({m_list[0].get('occupation', 'Parent')})" if m_list else "Unknown"

            sib_strs = []
            num_brothers = 0
            num_sisters = 0
            for s in sibs:
                rel = s.get("relation", "Sibling")
                s_name = s.get("name", s.get("first_name", "Sibling"))
                s_occ = s.get("occupation", "Student")
                if "brother" in rel.lower():
                    num_brothers += 1
                elif "sister" in rel.lower():
                    num_sisters += 1
                sib_strs.append(f"{s_name} [{rel} - {s_occ}]")

            sibs_formatted = ", ".join(sib_strs) if sib_strs else "None (Only child)"
            sections.append(
                f"  [CANON FAMILY & LINEAGE GROUNDING - {name}]:\n"
                f"  * Parents: Father: {f_str} | Mother: {m_str}\n"
                f"  * Siblings: {sibs_formatted} -> (COMPOSITION: EXACTLY {num_sisters} sister(s), {num_brothers} brother(s))\n"
                f"  * DIRECTIVE: Strictly adhere to this family structure. DO NOT invent non-existent siblings (e.g. {num_brothers} brothers) or alter parents."
            )

    # 2. Romantic History & Past Exes Topic
    romance_kws = (
        "ex", "exes", "dated", "dating", "past relationship", "past relationships",
        "past partner", "prior partner", "ex-boyfriend", "ex-girlfriend",
        "first kiss", "virginity", "who have you dated",
        "single", "taken", "boyfriend", "girlfriend", "partner", "current partner",
        "in a relationship", "relationship", "love life", "dating anyone",
        "seeing anyone", "crush", "significant other", "married", "spouse",
        "experience", "experienced", "suitor", "suitors", "handling guys", "handling girls",
        "turn on", "turn off", "turn-on", "turn-off", "desires", "kinks"
    )
    if any(kw in act_lower for kw in romance_kws):
        romance = relations.get("romance", {})
        if romance:
            status = romance.get("status", "Single")
            curr_p = romance.get("current_partner")
            curr_str = ""
            if curr_p and isinstance(curr_p, dict) and curr_p.get("name"):
                p_role = curr_p.get("role", "Partner")
                p_type = curr_p.get("relationship_type", "Dating")
                curr_str = f" | Current Partner: {curr_p.get('name')} ({p_role} - {p_type})"

            exes = romance.get("ex_partners", [])
            ex_strs = [f"{e.get('name')} ({e.get('role', 'Ex-Partner')})" for e in exes if isinstance(e, dict) and e.get("name")]
            ex_formatted = ", ".join(ex_strs) if ex_strs else "None (No prior relationships recorded)"
            ic_state = str(appr.get("intercourse_experience") or appr.get("predetermined_intercourse") or "virgin").strip().lower()
            sections.append(
                f"  [CANON ROMANCE & DATING HISTORY - {name}]:\n"
                f"  * Current Status: {status}{curr_str} | Past Ex-Partner(s): {ex_formatted} | Intercourse Experience: {ic_state}\n"
                f"  * DIRECTIVE: When asked about dating status, partners, relationship history, suitors, or sexual experience, strictly reference these canon records. If Intercourse Experience is 'virgin' and Past Ex-Partner(s) is 'None', {name} has NEVER had sexual partners, suitors, or bedroom experiences and MUST NEVER claim to have had them!"
            )

    # 3. Friends & Rivals Topic
    social_kws = (
        "friend", "friends", "best friend", "close friend", "inner circle",
        "rival", "rivals", "adversary", "competitor", "social circle", "class rep"
    )
    if any(kw in act_lower for kw in social_kws):
        friends = relations.get("friends", [])
        rivals = relations.get("rivals", [])
        fr_strs = [f"{f.get('name')} ({f.get('role', 'Friend')})" for f in friends if isinstance(f, dict) and f.get("name")]
        rv_strs = [f"{r.get('name')} ({r.get('role', 'Rival')})" for r in rivals if isinstance(r, dict) and r.get("name")]
        fr_formatted = ", ".join(fr_strs) if fr_strs else "None"
        rv_formatted = ", ".join(rv_strs) if rv_strs else "None"
        sections.append(
            f"  [CANON SOCIAL CIRCLE & RIVALS - {name}]:\n"
            f"  * Friends: {fr_formatted} | Rivals: {rv_formatted}\n"
            f"  * DIRECTIVE: Reference these specific friends and rivals when discussing peer relationships."
        )

    # 4. Established Shared Milestones & Recent Interactions with the Player
    from mechanics.social.persona import is_romantic_milestone_str
    mems = contact.get("intimate_memories") or (contact.get("appearance") or {}).get("intimate_memories") or []
    romantic_mems = [m for m in mems if not str(m).startswith("Past History:") and is_romantic_milestone_str(str(m))]

    recent_interactions = contact.get("recent_memories") or contact.get("rel_history") or (contact.get("appearance") or {}).get("recent_memories") or []
    if not recent_interactions:
        recent_interactions = [m for m in mems if not str(m).startswith("Past History:") and not is_romantic_milestone_str(str(m))]

    milestone_kws = (
        "remember when", "remember that", "last night", "our night", "our kiss",
        "our date", "first time we", "we kissed", "we slept", "intimate",
        "confession", "promise", "past memory", "memories with you", "between us"
    )
    is_intimate_action = any(
        ikw in act_lower for ikw in (
            "kiss", "hold", "touch", "caress", "bed", "bedroom", "sheets",
            "naked", "undress", "strip", "breast", "thigh", "whisper",
            "embrace", "cuddle", "lie down", "lay down", "intercourse", "oral", "anal"
        )
    )

    # 4A. General Shared Interactions (Capped strictly at latest 5 or 3 recent + up to 2 recalled)
    if recent_interactions:
        selected_recent = _retrieve_contextual_memories(act_lower, recent_interactions, max_recent=3, max_recalled=2)
        sections.append(
            f"  [RECENT SHARED INTERACTIONS & MEMORIES - {name}]:\n"
            f"  * Recent History: {'; '.join(selected_recent)}\n"
            f"  * DIRECTIVE: Maintain continuous, coherent recall of these shared interactions with the player."
        )

    # 4B. Romantic & Intimate Milestones (Injected when romantic context is active or during intimate scenes, max 5)
    if romantic_mems and (any(kw in act_lower for kw in milestone_kws) or is_intimate_action or contact.get("track") == "romantic"):
        selected_romantic = _retrieve_contextual_memories(act_lower, romantic_mems, max_recent=3, max_recalled=2)
        sections.append(
            f"  [ESTABLISHED SHARED MEMORIES WITH PLAYER - {name}]:\n"
            f"  * Romantic Milestones: {'; '.join(selected_romantic)}\n"
            f"  * DIRECTIVE: Maintain continuous, coherent recall of these established shared moments with the player."
        )

    # 5. Intimate Preferences & Sensitive Spots (Injected during intimate/romantic dialogue)
    sensitive_spots = appr.get("sensitive_spots")
    turn_ons = appr.get("turn_ons")
    is_intimacy_active = any(
        ikw in act_lower for ikw in (
            "kiss", "touch", "caress", "bed", "bedroom", "sheets", "naked",
            "undress", "strip", "breast", "thigh", "intimate", "oral", "intercourse", "anal"
        )
    )
    turns_revealed = (
        appr.get("turn_ons_revealed") or appr.get("sensitive_spots_revealed")
        or appr.get("intimate_revealed") or appr.get("all_revealed")
    )
    if is_intimacy_active and turns_revealed and (sensitive_spots or turn_ons):
        from mechanics.social.persona import clean_attribute_list_string
        spots_str = clean_attribute_list_string(sensitive_spots) or "None"
        ons_str = clean_attribute_list_string(turn_ons) or "None"
        sections.append(
            f"  [INTIMATE PREFERENCES & SENSITIVE SPOTS - {name}]:\n"
            f"  * Sensitive Spots: {spots_str} | Turn-Ons: {ons_str}"
        )

    return "\n".join(sections)

