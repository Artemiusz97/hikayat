from __future__ import annotations
"""
mechanics/social/roster_tags.py — Two-Tier Demographics, Roster Taxonomy & Dialogue Registers
=============================================================================================
Provides pure, deterministic functions to classify NPC demographics (teen vs adult),
academic standings, contact eligibility, visual badges, and localized dialogue register
directives for the narrative LLM.
"""
import re
from typing import Any, Dict, List, Literal, Optional, Tuple
from models.llm_schemas import CharacterBadges, AgeGroup

AGE_GROUP_TEEN: AgeGroup = "teen"
AGE_GROUP_ADULT: AgeGroup = "adult"

_STUDENT_GRADES = {
    "freshman": "Freshman",
    "sophomore": "Sophomore",
    "junior": "Junior",
    "senior": "Senior",
}

_FACULTY_KEYWORDS = (
    "teacher", "faculty", "professor", "principal", "vice principal", "vice-principal",
    "dean", "counselor", "guidance counselor", "nurse", "school nurse", "librarian",
    "coach", "athletic director", "headmaster", "headmistress", "instructor", "tutor", "sensei"
)

_STAFF_KEYWORDS = (
    "security", "security guard", "guard", "patrol", "gatekeeper", "campus guard",
    "school guard", "custodian", "janitor", "groundskeeper", "caretaker", "lunch lady",
    "cafeteria staff", "cafeteria worker", "cook", "chef", "dorm warden", "dorm mother"
)

_ADULT_FAMILY_KEYWORDS = (
    "parent", "mother", "father", "mom", "dad", "stepmother", "stepfather",
    "guardian", "uncle", "aunt", "grandmother", "grandfather"
)

_ADULT_SERVICE_KEYWORDS = (
    "clerk", "cashier", "store clerk", "shopkeeper", "storekeeper", "barista",
    "waiter", "waitress", "bartender", "barkeep", "vendor", "peddler",
    "driver", "bus driver", "transit worker", "police", "police officer",
    "cop", "detective", "sheriff", "landlord", "landlady", "manager",
    "florist", "pharmacist", "doctor", "baker", "butcher", "mechanic",
    "merchant", "tailor", "librarian", "owner", "roaster", "proprietor",
    "electrician", "contractor", "tradesperson", "artisan", "barber",
    "stylist", "innkeeper", "carpenter", "plumber", "accountant", "lawyer",
    "lifeguard", "rescuer", "courier"
)

# False-positive student exceptions (words that contain adult tokens but are student roles)
_STUDENT_ROLE_EXCEPTIONS = (
    "student council", "class rep", "class representative", "student teacher",
    "peer tutor", "club president", "club vice president", "club leader",
    "team captain", "club captain", "prefect", "delinquent", "cheerleader", "valedictorian",
    "transfer student", "exchange student", "cyclist", "student"
)


def is_school_scenario(scen_key: str = "") -> bool:
    """Checks whether the scenario key belongs to high school or academy settings."""
    try:
        import scenario_data
        return scenario_data.has_school_campus_mechanics(scen_key)
    except Exception:
        scen_low = str(scen_key or "").strip().lower()
        return any(k in scen_low for k in ("school", "academy", "high_school"))


def derive_age_group(
    grade: str = "",
    role: str = "",
    social_role_type: str = "",
    scen_key: str = "high_school",
    is_family: bool = False,
) -> AgeGroup:
    """
    Deterministically derives whether an NPC belongs to 'teen' or 'adult' demographic.
    In High School scenarios, defaults to 'teen' for campus students and 'adult' for faculty/staff/town.
    In non-school scenarios (Fantasy, Sci-Fi), defaults to 'adult'.
    """
    srt_clean = str(social_role_type or "").lower().strip()
    if srt_clean in ("faculty_staff", "adult_service", "family_relative", "parent", "special_agent", "folklore_villager"):
        g_probe = str(grade or "").lower().strip()
        if srt_clean == "special_agent" and any(k in g_probe for k in _STUDENT_GRADES):
            return AGE_GROUP_TEEN
        return AGE_GROUP_ADULT
    if srt_clean in ("student_peer", "peer", "contemporary", "classmate"):
        return AGE_GROUP_TEEN

    g_clean = str(grade or "").lower().strip()
    if g_clean in ("faculty", "staff", "citizen", "adult", "operative") or g_clean.startswith("tier "):
        return AGE_GROUP_ADULT
    for k in _STUDENT_GRADES:
        if k in g_clean or f"grade {9 + list(_STUDENT_GRADES.keys()).index(k)}" in g_clean:
            return AGE_GROUP_TEEN
    if g_clean in ("youth peer", "student"):
        return AGE_GROUP_TEEN

    r_clean = str(role or "").lower().strip()

    # If role explicitly matches student exceptions, it is a teen
    if any(k in r_clean for k in _STUDENT_ROLE_EXCEPTIONS):
        return AGE_GROUP_TEEN

    # Check adult role categories with word boundaries
    all_adult = _FACULTY_KEYWORDS + _STAFF_KEYWORDS + _ADULT_FAMILY_KEYWORDS + _ADULT_SERVICE_KEYWORDS
    for kw in all_adult:
        if re.search(rf"\b{re.escape(kw)}\b", r_clean):
            return AGE_GROUP_ADULT

    if is_school_scenario(scen_key):
        return AGE_GROUP_TEEN
    return AGE_GROUP_ADULT


def normalize_standing(role: str = "", grade: str = "", scen_key: str = "high_school") -> str:
    """
    Deterministically resolves the mutually exclusive academic / institutional standing.
    Returns: 'Freshman' | 'Sophomore' | 'Junior' | 'Senior' | 'Faculty' | 'Staff' | 'Citizen' | 'Youth Peer' | ''
    """
    g_low = str(grade or "").strip().lower()
    for k, v in _STUDENT_GRADES.items():
        if k in g_low or f"grade {9 + list(_STUDENT_GRADES.keys()).index(k)}" in g_low:
            return v
    if "youth peer" in g_low:
        return "Youth Peer"
    if g_low.startswith("tier ") or g_low == "operative":
        return str(grade).strip() or "Operative"

    if not is_school_scenario(scen_key):
        return ""

    r_low = str(role or "").strip().lower()

    # Guard against town roles like "staff writer"
    if any(re.search(rf"\b{re.escape(w)}\b", r_low) for w in _STAFF_KEYWORDS) and "writer" not in r_low and "reporter" not in r_low:
        return "Staff"
    if any(re.search(rf"\b{re.escape(w)}\b", r_low) for w in _FACULTY_KEYWORDS):
        return "Faculty"
    if any(k in r_low for k in ("student", "classmate", "peer", "delinquent", "cyclist", "otaku", "slacker", "cheerleader")):
        return "Sophomore" if "high_school" in scen_key else "Student"

    if "faculty" in g_low:
        return "Faculty"
    if "staff" in g_low:
        return "Staff"
    if "citizen" in g_low:
        return "Citizen"

    return "Citizen"


def normalize_social_role_type(
    role: str = "",
    grade: str = "",
    social_role_type: str = "",
    scen_key: str = "high_school",
    is_family: bool = False,
) -> str:
    """Normalizes the relational engine social_role_type."""
    if social_role_type and str(social_role_type).strip():
        return str(social_role_type).strip().lower()
    if is_family:
        return "family_relative"

    age_grp = derive_age_group(grade=grade, role=role, scen_key=scen_key)
    if age_grp == AGE_GROUP_TEEN:
        return "student_peer"

    standing = normalize_standing(role=role, grade=grade, scen_key=scen_key)
    if standing in ("Faculty", "Staff"):
        return "faculty_staff"
    return "adult_service"


def is_anomalous_high_school_contact_eligible(
    player_age_group: str,
    npc_age_group: str,
    npc_is_special_agent: bool,
    is_household_family: bool = False,
    npc_is_folklore_villager: bool = False,
) -> bool:
    """
    2x2 Contact Eligibility Matrix for `anomalous_high_school` and its variants:
    - Adult Special Agent PC (`player_age_group == "adult"`):
      Can have unrestricted contact with Adult characters (Special Agent or Civilian)
      and Teen/Student Special Agents ONLY. Cannot add Civilian Teen/Students.
    - Teen/Student Special Agent PC (`player_age_group == "teen"`):
      Can have unrestricted contact with Teen/Student characters (Special Agent or Civilian),
      Adult Special Agents, and Household Family members ONLY. Cannot add non-family Adult Civilians.
    - Folklore Enclave Villagers (Orang Bunian & Kitsune): Exempt as ageless folklore allies/romanceables.
    """
    if npc_is_folklore_villager:
        return True
    p_age = str(player_age_group or AGE_GROUP_TEEN).strip().lower()
    n_age = str(npc_age_group or AGE_GROUP_ADULT).strip().lower()
    if is_household_family and p_age == AGE_GROUP_TEEN:
        return True
    if p_age == AGE_GROUP_ADULT:
        return (n_age == AGE_GROUP_ADULT) or bool(npc_is_special_agent)
    # Default: teen/student special agent player character
    return (n_age == AGE_GROUP_TEEN) or bool(npc_is_special_agent)


def is_contact_eligible_demographic(
    age_group: str = "",
    social_role_type: str = "",
    scen_key: str = "high_school",
    is_family: bool = False,
    player_age_group: str = "",
    npc_is_special_agent: bool = False,
    npc_is_folklore_villager: bool = False,
) -> bool:
    """
    True if the NPC demographic is eligible for personal contacts directory and affinity meters.
    In High School scenarios:
    - Teens (students/peers) ARE eligible.
    - Adults (faculty/staff/townspeople) ARE NOT eligible (story-only in lorebook).
    - Exception: Household parents / adult family members ARE eligible for family curfew/allowance SMS.
    In Anomalous High School scenarios:
    - Uses the 2x2 `is_anomalous_high_school_contact_eligible` matrix based on `player_age_group`
      ("adult" vs "teen") and `npc_is_special_agent` (plus `npc_is_folklore_villager`).
    In non-school scenarios: Adults and all canonical characters are eligible.
    """
    if npc_is_folklore_villager or str(social_role_type).strip().lower() == "folklore_villager":
        return True
    if not is_school_scenario(scen_key):
        return True

    fam_flag = bool(is_family or str(social_role_type).lower() in ("family_relative", "parent"))
    clean_age = str(age_group or "").strip().lower()
    clean_srt = str(social_role_type or "").strip().lower()
    if not clean_age:
        if clean_srt in ("faculty_staff", "adult_service", "special_agent"):
            clean_age = AGE_GROUP_ADULT
        else:
            clean_age = AGE_GROUP_TEEN

    if "anomalous_high_school" in str(scen_key or "").strip().lower():
        return is_anomalous_high_school_contact_eligible(
            player_age_group=player_age_group or AGE_GROUP_TEEN,
            npc_age_group=clean_age,
            npc_is_special_agent=bool(npc_is_special_agent or clean_srt == "special_agent"),
            is_household_family=fam_flag,
        )

    if fam_flag:
        return True

    if clean_age == AGE_GROUP_ADULT:
        return False
    if clean_age == AGE_GROUP_TEEN:
        return True

    if clean_srt in ("faculty_staff", "adult_service"):
        return False
    return True


def npc_is_folklore_villager(entity: Any) -> bool:
    """Returns True if `entity` (contact/NPC dict) is an Orang Bunian or Kitsune folklore villager."""
    if not isinstance(entity, dict):
        return False
    if entity.get("is_folklore_villager"):
        return True
    basic = entity.get("basic_info") if isinstance(entity.get("basic_info"), dict) else {}
    if basic.get("is_folklore_villager") or basic.get("folklore_village"):
        return True
    srt = str(entity.get("social_role_type") or basic.get("social_role_type") or "").strip().lower()
    if srt == "folklore_villager":
        return True
    race_low = str(entity.get("race") or basic.get("race") or "").strip().lower()
    return race_low in ("orang_bunian", "kitsune:humanoid", "kitsune:myobu_fox", "kitsune")


def is_merchant_character(entity: Dict[str, Any]) -> bool:
    """Centralized check for merchant characters to eliminate frontend regex sniffing."""
    if not isinstance(entity, dict):
        return False
    if entity.get("is_merchant"):
        return True
    basic = entity.get("basic_info") if isinstance(entity.get("basic_info"), dict) else {}
    if basic.get("is_merchant"):
        return True
    r = str(entity.get("role") or basic.get("role") or basic.get("occupation") or "").lower()
    return bool(re.search(r"\b(merchant|shopkeeper|vendor|apothecary|peddler|trader|storekeeper|clerk)\b", r))


def is_student_character(
    entity: Dict[str, Any] | str,
    role: str = "",
    grade: str = "",
    scen_key: str = "high_school",
) -> bool:
    """Returns True if the character is an enrolled high school student peer."""
    if isinstance(entity, str):
        g = grade or entity
        r = role
    elif isinstance(entity, dict):
        basic = entity.get("basic_info") if isinstance(entity.get("basic_info"), dict) else {}
        r = str(entity.get("role") or basic.get("role") or basic.get("occupation") or role).strip()
        g = str(entity.get("grade") or basic.get("grade") or grade).strip()
    else:
        return False
    standing = normalize_standing(role=r, grade=g, scen_key=scen_key)
    return standing in _STUDENT_GRADES.values()


def resolve_character_badges(
    entity: Dict[str, Any],
    scen_key: str = "high_school",
    party_names: Optional[set[str]] = None,
    is_contact: bool = False,
    is_blocked: bool = False,
) -> CharacterBadges:
    """Full deterministic projection from entity attributes to typed CharacterBadges."""
    basic = entity.get("basic_info") if isinstance(entity.get("basic_info"), dict) else {}
    raw_role = str(entity.get("role") or basic.get("role") or basic.get("occupation") or "").strip()
    raw_grade = str(entity.get("grade") or basic.get("grade") or "").strip()
    raw_club = str(entity.get("club") or basic.get("club") or "").strip()
    raw_clique = str(entity.get("clique") or basic.get("clique") or "").strip()
    raw_srt = str(entity.get("social_role_type") or basic.get("social_role_type") or "").strip()
    name = str(entity.get("name") or "").strip()
    is_fam = bool(entity.get("is_adult_family") or basic.get("is_adult_family") or entity.get("household_role") in ("father", "mother", "guardian"))

    age_grp = derive_age_group(grade=raw_grade, role=raw_role, social_role_type=raw_srt, scen_key=scen_key, is_family=is_fam)
    standing = normalize_standing(raw_role, raw_grade, scen_key=scen_key)

    is_stu = standing in _STUDENT_GRADES.values()
    is_fac = standing == "Faculty"
    is_stf = standing == "Staff"
    is_ctz = standing == "Citizen"
    is_merch = is_merchant_character(entity)
    is_spec = bool(basic.get("is_special_agent") or entity.get("is_special_agent") or basic.get("anomalous_npc_tag") == "special_agent")
    in_pty = bool(party_names and name.lower() in party_names)

    # Only enrolled school students belong to school clubs; regular adults, citizens, and staff never have clubs.
    club = raw_club if (is_stu and raw_club.lower() not in ("", "none", "unaffiliated", "general")) else ""
    clique = raw_clique if raw_clique.lower() not in ("", "none", "unaffiliated") else ""

    # Visual badge pills in strict precedence order
    badge_list: List[str] = []
    if standing:
        badge_list.append(standing)
    if club:
        badge_list.append(f"Club: {club}")
    if is_merch:
        badge_list.append("Merchant")
    if is_spec:
        badge_list.append("Special Agent")
    if in_pty:
        badge_list.append("In Party")
    if is_blocked:
        badge_list.append("Blocked")

    return CharacterBadges(
        standing=standing,
        primary_role=raw_role or standing,
        club=club,
        clique=clique,
        badges=badge_list,
        age_group=age_grp,
        is_student=is_stu,
        is_faculty=is_fac,
        is_staff=is_stf,
        is_citizen=is_ctz,
        is_merchant=is_merch,
        is_special_agent=is_spec,
        is_contact=is_contact,
        is_in_party=in_pty,
        is_blocked=is_blocked,
    )


def get_dialogue_register(speaker_age_group: str, listener_age_group: str) -> str:
    """Determines conversational register: 'formal', 'casual', 'instructive', or 'neutral'."""
    s_age = str(speaker_age_group or "").strip().lower()
    l_age = str(listener_age_group or "").strip().lower()

    if s_age == AGE_GROUP_TEEN and l_age == AGE_GROUP_ADULT:
        return "formal"
    if s_age == AGE_GROUP_TEEN and l_age == AGE_GROUP_TEEN:
        return "casual"
    if s_age == AGE_GROUP_ADULT and l_age == AGE_GROUP_TEEN:
        return "instructive"
    return "neutral"


_LOCALIZED_HONORIFICS = {
    "en": "formal titles (Mr., Ms., Mrs., Sir, Coach, Dr., Sensei)",
    "ms": "panggilan hormat (Cikgu, Encik, Puan, Tuan)",
    "pl": "zwrotów grzecznościowych (Pan, Pani, Panie Profesorze)",
    "zh": "尊称（老师、先生、女士、教练）",
    "de": "Höflichkeitsformen und Titel (Herr, Frau, Herr/Frau Professor)",
}


def format_dialogue_register_directive(
    speaker_name: str,
    listener_name: str,
    register: str,
    listener_role: str = "",
    language: str = "en",
    speaker_traits: Optional[List[Any]] = None,
) -> str:
    """Generates a localized LLM prompt directive enforcing conversational tone and honorifics."""
    lang_key = str(language or "en").lower().split("-")[0]
    hon_hint = _LOCALIZED_HONORIFICS.get(lang_key, _LOCALIZED_HONORIFICS["en"])

    if register == "formal":
        title_hint = f" ({listener_role})" if listener_role else ""
        delinquent_clause = ""
        if speaker_traits:
            t_names = {str(t.get("name") if isinstance(t, dict) else t).lower() for t in speaker_traits if t}
            if t_names & {"rebel", "delinquent", "insolent", "defiant", "hot-headed"}:
                delinquent_clause = (
                    f" (Note: {speaker_name} has rebellious traits and may speak with insolence or grudging curtness, "
                    f"which {listener_name} will sternly reprimand as an authority figure.)"
                )

        return (
            f"DIALOGUE REGISTER DIRECTIVE (Formal / Respectful):\n"
            f"- {speaker_name} is a student speaking with an adult authority figure: {listener_name}{title_hint}.\n"
            f"- MUST use respectful honorifics ({hon_hint}) and polite, deferential syntax.{delinquent_clause}\n"
            f"- STRICTLY FORBIDDEN: Do NOT use casual teenage slang, irreverent banter, or intimate teasing toward {listener_name}."
        )

    if register == "casual":
        return (
            f"DIALOGUE REGISTER DIRECTIVE (Casual / Peer):\n"
            f"- {speaker_name} and {listener_name} are peer students.\n"
            f"- Use contemporary youth dialogue, informal contractions, authentic peer banter, and first names."
        )

    if register == "instructive":
        return (
            f"DIALOGUE REGISTER DIRECTIVE (Authoritative Mentor):\n"
            f"- {speaker_name} is an adult addressing student {listener_name} with professional guidance, mentorship, or pastoral authority."
        )

    return ""
