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
import random
import re
from typing import Dict, Any, List, Optional, Tuple

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
    r = str(race).strip().lower().replace("-", "_")
    if ":" in r:
        return r.split(":")[-1]
    for sp in (
        "fennec_fox", "fennec", "cheetah", "tiger", "lion", "mouse", "rat",
        "rabbit", "bunny", "cat", "wolf", "fox", "bear", "bird", "reptile"
    ):
        if sp in r:
            return sp
    from mechanics.social.races import resolve_animal_family_species
    fam_sp = resolve_animal_family_species(r)
    if fam_sp:
        return fam_sp
    return ""


def extract_surname_and_firstname(name: str) -> Tuple[str, str]:
    """Splits full name into (first_name, surname).
    e.g. 'Sofia Anderson' -> ('Sofia', 'Anderson')
    'Aldric' -> ('Aldric', '')
    """
    if not name or not isinstance(name, str):
        return ("Unknown", "")
    parts = str(name).strip().split()
    if len(parts) >= 2:
        first = parts[0]
        last = " ".join(parts[1:])
        return (first, last)
    return (parts[0] if parts else "Unknown", "")


def get_deterministic_firstname(scenario: str, gender: str, hash_val: int) -> str:
    """Deterministically rolls a gendered first name using hash_val and scenario data."""
    data = namegen._get_scenario_data(scenario, "person")
    if not isinstance(data, dict):
        data = {}
    g = str(gender or "").lower().strip()
    is_female = ("female" in g or "woman" in g or "girl" in g or "feminine" in g or "she" in g)
    is_male = ("male" in g or "man" in g or "boy" in g or "masculine" in g or "he" in g) and not is_female

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
    family_surname = child_surname or get_deterministic_surname(scenario, hash_val)
    maiden_surname = get_deterministic_surname(scenario, hash_val * 7 + 13)
    if maiden_surname.lower() == family_surname.lower():
        maiden_surname = get_deterministic_surname(scenario, hash_val * 11 + 29)

    father_first = get_deterministic_firstname(scenario, "male", hash_val * 3 + 5)
    mother_first = get_deterministic_firstname(scenario, "female", hash_val * 5 + 11)

    father_name = f"{father_first} {family_surname}".strip()
    mother_name = f"{mother_first} {family_surname} (née {maiden_surname})".strip()

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

    family_surname = father.get("surname") or mother.get("surname") or get_deterministic_surname(scenario, hash_val)
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

        sib_first = get_deterministic_firstname(scenario, gender, sib_hash)
        if sib_first.lower() == father.get("first_name", "").lower() or sib_first.lower() == mother.get("first_name", "").lower():
            sib_first = get_deterministic_firstname(scenario, gender, sib_hash * 3 + 17)
        sib_name = f"{sib_first} {family_surname}".strip()
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
    is_player_partner = is_romantic_track or has_relationship_mem

    is_player_interest = (
        is_player_partner
        or contact.get("relationship_score", 0) >= 30
        or app_data.get("intimate_revealed")
        or app_data.get("had_first_time_with_player")
    )
    desc_str = (str(contact.get("description", "")) + " " + str((contact.get("basic_info") or {}).get("description", ""))).lower()
    is_explicitly_single = "single" in desc_str or "unmarried" in desc_str or "unattached" in desc_str

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
        # 2. Current Partner roll (15% chance, suppressed if player interest or explicitly single)
        has_current_partner = (((abs(hash_val) * 29 + 11) % 100) < 15) and not is_player_interest and not is_explicitly_single
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

    # 3. Secret Affair roll (3% chance)
    has_secret_affair = ((abs(hash_val) * 31 + 23) % 100) < 3
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

    # 4. Ex-Partners roll (15% chance, or guaranteed if past intimate history exists)
    has_ex = ((abs(hash_val) * 37 + 19) % 100) < 15 or bool(past_partner_name)
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


# ==============================================================================
# CANONICAL SHARED HOUSEHOLD LINEAGE ENGINE
# ==============================================================================

def get_canonical_family_unit(
    session_id: int,
    surname: str,
    known_contact: dict,
    scenario: str = "fantasy"
) -> Dict[str, Any]:
    """
    Generates and returns the canonical Family / Household unit shared by all siblings.
    Ensures Father, Mother, maiden names, careers, races, and sibling roster are 100% identical.
    """
    clean_surname = (surname or "").strip()
    if not clean_surname:
        first, last = extract_surname_and_firstname(known_contact.get("name", ""))
        if last:
            clean_surname = last
        else:
            name_seed = int(hashlib.md5(f"{session_id}_{first}".encode("utf-8")).hexdigest(), 16)
            clean_surname = get_deterministic_surname(scenario, name_seed)

    # Canonical household seed based on session and family surname
    household_seed = f"{session_id}_household_{clean_surname.lower()}_v3".encode("utf-8")
    household_hash = int(hashlib.md5(household_seed).hexdigest(), 16)

    # Resolve child race robustly: try contact race, then basic_info, then lorebook, then narrative extraction
    child_race = known_contact.get("race") or (known_contact.get("basic_info") or {}).get("race") or ""
    if not child_race:
        # Try lorebook
        try:
            import db
            c_name_raw = known_contact.get("name", "")
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
        # Try narrative extraction from description
        from mechanics.social.races import extract_race_from_text
        desc_text = (known_contact.get("basic_info") or {}).get("description", "") or ""
        if desc_text:
            child_race = extract_race_from_text(desc_text, scen_key=scenario, name=known_contact.get("name", "")) or ""
    if not child_race:
        child_race = "human"
    child_appearance = known_contact.get("appearance") or {}

    father, mother = reverse_generate_parents(
        child_race=child_race,
        child_appearance=child_appearance,
        child_surname=clean_surname,
        scenario=scenario,
        hash_val=household_hash
    )

    # Gather all known children/siblings in the session for this household
    children_dict: Dict[str, Dict[str, Any]] = {}
    grade_order = {"Faculty": 5, "Senior": 4, "Junior": 3, "Sophomore": 2, "Freshman": 1}

    # 1. Add current known contact
    c_full = known_contact.get("name", "Unknown")
    c_first, _ = extract_surname_and_firstname(c_full)
    c_grade = (known_contact.get("basic_info") or {}).get("grade", "Junior")
    c_gender = known_contact.get("gender") or "female"
    c_role = (known_contact.get("basic_info") or {}).get("role", "Student")

    children_dict[c_first.lower()] = {
        "name": c_full,
        "first_name": c_first,
        "surname": clean_surname,
        "grade": c_grade,
        "grade_val": grade_order.get(c_grade, 2),
        "gender": c_gender,
        "role": c_role,
        "race": child_race,
        "status": "Alive",
        "features": f"{child_appearance.get('eyes', 'Amber')} eyes, {child_appearance.get('hair', 'Golden-Blonde')} hair"
    }

    # 2. Check explicitly linked sibling in basic_info
    sib_linked = (known_contact.get("basic_info") or {}).get("sibling_name")
    if sib_linked:
        s_first, _ = extract_surname_and_firstname(sib_linked)
        s_gender, s_grade = _get_raw_contact_gender_and_grade(session_id, sib_linked)
        if not s_gender:
            s_gender, s_grade = _get_raw_contact_gender_and_grade(session_id, s_first)
        if not s_gender:
            s_gender = "female" if any(f in s_first.lower() for f in ["sofia", "sophia", "maya", "elena", "chloe", "hana", "seraphina", "alina", "anna", "ann", "amanda", "yea-ji", "zihan"]) else "male"
        
        if not s_grade:
            s_grade = "Senior" if s_first.lower() in ("amanda", "ann") else ("Freshman" if s_first.lower() in ("maya",) else "Junior")

        s_role = "Drama Club Lead" if "amanda" in s_first.lower() else ("Library Assistant" if "ann" in s_first.lower() else ("Student" if "maya" in s_first.lower() else "Student"))
        s_full = f"{s_first} {clean_surname}"
        children_dict[s_first.lower()] = {
            "name": s_full,
            "first_name": s_first,
            "surname": clean_surname,
            "grade": s_grade,
            "grade_val": grade_order.get(s_grade, 3),
            "gender": s_gender,
            "role": s_role,
            "race": child_race,
            "status": "Alive",
            "features": f"{child_appearance.get('eyes', 'Amber')} eyes, {child_appearance.get('hair', 'Golden-Blonde')} hair"
        }

    # 3. Check session contacts that EXPLICITLY reference this contact as their sibling
    # Surnames alone NEVER constitute a biological sibling relationship.
    is_anderson = clean_surname.lower() == "anderson" and any(k in (c_first.lower(), (sib_linked or "").lower()) for k in ("sofia", "maya", "amanda"))

    if not is_anderson:
        try:
            import db
            if session_id:
                contacts = db.get_contacts(session_id, resolve_relations=False, ensure_scene=False)
                for other_c in (contacts or []):
                    o_name = other_c.get("name", "")
                    o_first, o_last = extract_surname_and_firstname(o_name)
                    if o_first.lower() in children_dict:
                        continue
                    # Sibling relationship requires:
                    # a) Shared surname
                    # b) Explicit sibling cross-reference (basic_info.sibling_name matches known contact or family member)
                    # c) Biological genetic compatibility with the parents
                    if o_last.lower() == clean_surname.lower():
                        o_b = other_c.get("basic_info") or {}
                        other_sib = o_b.get("sibling_name", "")
                        target_names = {c_full.lower(), c_first.lower()}
                        for ch in children_dict.values():
                            target_names.add(ch["name"].lower())
                            target_names.add(ch["first_name"].lower())

                        if other_sib.lower() in target_names:
                            other_race = other_c.get("race") or o_b.get("race") or child_race
                            if not is_race_compatible_with_parents(other_race, father["race"], mother["race"]):
                                continue

                            from mechanics.social.persona import infer_contact_gender
                            o_gr = o_b.get("grade", "Junior")
                            o_gen = other_c.get("gender") or infer_contact_gender(other_c) or "female"
                            o_rl = o_b.get("role", "Student")
                            children_dict[o_first.lower()] = {
                                "name": o_name,
                                "first_name": o_first,
                                "surname": clean_surname,
                                "grade": o_gr,
                                "grade_val": grade_order.get(o_gr, 2),
                                "gender": o_gen,
                                "role": o_rl,
                                "race": other_race,
                                "status": "Alive",
                                "features": f"{child_appearance.get('eyes', 'Amber')} eyes, {child_appearance.get('hair', 'Golden-Blonde')} hair"
                            }
        except Exception:
            pass

    # 4. Canonical Anderson Sisters: Amanda (Senior), Sofia (Junior), Maya (Freshman)
    # The Anderson household is strictly and exclusively the three fox sisters.
    if is_anderson:
        father["race"] = "beastfolk:fox"
        mother["race"] = "beastfolk:fox"
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
                    "features": f"{child_appearance.get('eyes', 'Amber')} eyes, {child_appearance.get('hair', 'Golden-Blonde')} hair"
                }
            else:
                children_dict[a_key]["gender"] = "female"
                children_dict[a_key]["race"] = "beastfolk:fox"

    # 5. Generate procedural siblings using diminishing rates if household has fewer than 5 children
    # Sibling count ladder: 75% for 1st, 50% for 2nd, 25% for 3rd, 5% for 4th (capped at 4 siblings max)
    # Skip extra procedural generation for established canonical households like Anderson
    existing_sib_count = max(0, len(children_dict) - 1)
    if not is_anderson and existing_sib_count < 4:
        proc_sibs = generate_siblings(
            father, mother, child_appearance,
            scenario=scenario, hash_val=household_hash,
            contact_grade=c_grade,
            existing_sibling_count=existing_sib_count
        )
        for ps in proc_sibs:
            p_first = ps.get("first_name", "")
            f_first = father.get("first_name", "")
            m_first = mother.get("first_name", "")
            if p_first.lower() not in children_dict and p_first.lower() != f_first.lower() and p_first.lower() != m_first.lower():
                is_older = "older" in ps.get("relation", "").lower()
                p_grade = ps.get("grade") or ("Senior" if is_older else "Freshman")
                p_contactable = ps.get("is_contactable") or (p_grade in ("Freshman", "Sophomore", "Junior", "Senior"))
                children_dict[p_first.lower()] = {
                    "name": ps.get("name", f"{p_first} {clean_surname}"),
                    "first_name": p_first,
                    "surname": clean_surname,
                    "grade": p_grade,
                    "grade_val": grade_order.get(p_grade, 3 if is_older else 1),
                    "gender": ps.get("gender", "female"),
                    "role": ps.get("occupation", "Student"),
                    "club": ps.get("club", ""),
                    "race": ps.get("race", child_race),
                    "status": ps.get("status", "Alive"),
                    "is_contactable": p_contactable,
                    "features": ps.get("features", f"{child_appearance.get('eyes', 'Amber')} eyes")
                }

    return {
        "surname": clean_surname,
        "father": father,
        "mother": mother,
        "children": list(children_dict.values())
    }


def build_family_tree_for_member(
    household: Dict[str, Any],
    member_name: str,
    scenario: str = "fantasy"
) -> List[Dict[str, Any]]:
    """
    Constructs the family tree from the perspective of a specific child in the household.
    Father and Mother are identical across all siblings; siblings are listed with accurate relative labels.
    """
    father = dict(household["father"])
    mother = dict(household["mother"])
    children = household.get("children", [])

    m_first, _ = extract_surname_and_firstname(member_name)
    target_child = next((c for c in children if c["first_name"].lower() == m_first.lower()), None)
    my_grade_val = target_child.get("grade_val", 2) if target_child else 2

    siblings = []
    for c in children:
        if c["first_name"].lower() == m_first.lower():
            continue  # Do not list oneself as a sibling

        g_val = str(c.get("gender", "")).strip().lower()
        f_name = str(c.get("first_name", "")).strip()

        from namegen import is_known_male_name, is_known_female_name
        if "female" in g_val or "woman" in g_val or "girl" in g_val:
            is_female = True
        elif "male" in g_val or "man" in g_val or "boy" in g_val:
            is_female = False
        elif is_known_male_name(f_name):
            is_female = False
        elif is_known_female_name(f_name):
            is_female = True
        else:
            is_female = True if "female" in g_val else False

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
            "gender": c.get("gender", "female"),
            "status": c.get("status", "Alive"),
            "occupation": c_role,
            "features": c.get("features", "")
        }
        if c.get("grade"):
            sib_entry["grade"] = c["grade"]
        if c.get("is_contactable") or (c.get("grade") in ("Freshman", "Sophomore", "Junior", "Senior")):
            sib_entry["is_contactable"] = True
        if c.get("club"):
            sib_entry["club"] = c["club"]
        siblings.append(sib_entry)

    # Sort siblings: Older first, then younger
    siblings.sort(key=lambda s: 0 if "older" in s["relation"].lower() else 1)

    return [father, mother] + siblings


# ==============================================================================
# DYNAMIC SOCIAL GRAPH MUTATION HELPERS (FRIENDS, RIVALS, ROMANCE)
# ==============================================================================

def add_friend_relation(contact_dict: dict, friend_name: str, role: str = "Student", closeness: str = "Good Friend", session_id: int = 0) -> dict:
    """Dynamically adds or upgrades a friend in the contact's relations record."""
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
    relations = contact_dict.get("relations") or {}
    t_clean = target_name.strip().lower()
    relations["friends"] = [f for f in relations.get("friends", []) if f.get("name", "").lower() != t_clean]
    relations["rivals"] = [r for r in relations.get("rivals", []) if r.get("name", "").lower() != t_clean]
    return relations


def set_romantic_partner(contact_dict: dict, partner_name: str, role: str = "Lover / Soulmate", status: str = "In a Relationship", session_id: int = 0) -> dict:
    """Dynamically sets an active romantic partner."""
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

    # 1. Resolve canonical family household unit
    household = get_canonical_family_unit(session_id, surname, known_contact=contact, scenario=scenario)
    family_tree = build_family_tree_for_member(household, name, scenario=scenario)

    seed_str = f"{session_id}_{name}_relations_v2".encode("utf-8")
    hash_val = int(hashlib.md5(seed_str).hexdigest(), 16)

    existing = contact.get("relations")
    if not isinstance(existing, dict):
        existing = {}

    # Update/synchronize family tree
    existing["family"] = family_tree

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
        player_name = resolve_player_character_name(contact, session_id=session_id or contact.get("session_id", 0))
        score = contact.get("relationship_score", 0)
        role_label = "Lover / Soulmate" if score >= 80 else ("Romantic Partner / Dating" if score >= 40 else "Romantic Partner")
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
                            club_override=fam.get("club", "")
                        )
                        new_recs.append(rec)
                        existing_names.add(fam_name.lower())
            if new_recs:
                db.save_school_roster(session_id, new_recs)
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
        for a in actions:
            if isinstance(a, dict):
                act_pieces.append(str(a.get("label", "")) + " " + str(a.get("text", "")))
            else:
                act_pieces.append(str(a))
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
        "first kiss", "virginity", "who have you dated"
    )
    if any(kw in act_lower for kw in romance_kws):
        romance = relations.get("romance", {})
        if romance:
            status = romance.get("status", "Single")
            exes = romance.get("ex_partners", [])
            ex_strs = [f"{e.get('name')} ({e.get('role', 'Ex-Partner')})" for e in exes if isinstance(e, dict) and e.get("name")]
            ex_formatted = ", ".join(ex_strs) if ex_strs else "None (No prior relationships recorded)"
            sections.append(
                f"  [CANON ROMANCE & DATING HISTORY - {name}]:\n"
                f"  * Current Status: {status} | Past Ex-Partner(s): {ex_formatted}\n"
                f"  * DIRECTIVE: When asked about dating history, strictly reference these canon records."
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

    # 4. Established Shared Milestones with the Player
    mems = contact.get("intimate_memories") or (contact.get("appearance") or {}).get("intimate_memories") or []
    shared_mems = [m for m in mems if not str(m).startswith("Past History:")]
    if shared_mems:
        milestone_kws = (
            "remember when", "remember that", "last night", "our night", "our kiss",
            "our date", "first time we", "we kissed", "we slept", "intimate",
            "confession", "promise", "past memory", "memories with you", "between us"
        )
        is_intimate_action = any(
            ikw in act_lower for ikw in (
                "kiss", "hold", "touch", "caress", "bed", "bedroom", "sheets",
                "naked", "undress", "strip", "breast", "thigh", "whisper",
                "embrace", "cuddle", "lie down", "lay down", "intercourse", "oral"
            )
        )
        if any(kw in act_lower for kw in milestone_kws) or is_intimate_action or len(shared_mems) > 0:
            recent_mems = shared_mems[-8:]  # Cap at 8 most recent to avoid context bloat
            sections.append(
                f"  [ESTABLISHED SHARED MEMORIES WITH PLAYER - {name}]:\n"
                f"  * Shared Milestones: {'; '.join(str(m) for m in recent_mems)}\n"
                f"  * DIRECTIVE: Maintain continuous, coherent recall of these established shared moments with the player."
            )

    # 5. Intimate Preferences & Sensitive Spots (Injected during intimate/romantic dialogue)
    sensitive_spots = appr.get("sensitive_spots")
    turn_ons = appr.get("turn_ons")
    is_intimacy_active = any(
        ikw in act_lower for ikw in (
            "kiss", "touch", "caress", "bed", "bedroom", "sheets", "naked",
            "undress", "strip", "breast", "thigh", "intimate", "oral", "intercourse"
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

