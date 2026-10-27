"""
mechanics/world/npc_schedule.py — Deterministic NPC Daily & Weekend Schedules
=============================================================================
Derives and manages time-of-day and day-of-week (Weekday vs. Weekend) stations
and transitions for NPCs across all genres, with specialized support for High School:

High School NPC Schedule:
  - Wake-Up Time: 07:00 AM (420) | Sleep Time: 10:00 PM (1320)
  - Weekdays (Monday–Friday):
    * 07:00–08:00 (420..479, 'commute'): Students prepare and head to school
      (School Main Gates, Entrance Foyer & Shoe Lockers, Central Courtyard, Homeroom).
    * 08:00–15:00 (480..899, 'morning' / 'lunch' / 'class_afternoon'): Class periods
      and midday lunch break (12:00–13:00). Students attend class and roam around the
      school area; teachers lecture or work in the Staff Room.
    * 15:00–20:00 (900..1199, 'extracurricular'): Extracurricular period. Students do
      club activities (e.g. Auditorium Stage for Theater/Drama Club, Music Room, Fine
      Arts Studio, Student Council Office, Old Storage Room 3-B for Occult Club) and
      jocks/athletes train at sports facilities (Main Gymnasium, Athletic Track &
      Stadium Field, Swimming Pool, Martial Arts Dojo).
    * 20:00–07:00 (1200..1439 & 0..419, 'night'): All students and teachers return home.
  - Weekends (Saturday–Sunday):
    * 07:00–20:00 (420..1199): Students roam freely around the world (Commercial
      District cafes/arcades/stores, Neighborhood Park, Seaside, Mountain Park), while
      some students/athletes hang around the school's unlocked sports facilities or
      club HQs for weekend training and club meetings.
    * 20:00–07:00 (1200..1439 & 0..419): All students and teachers return home.
"""
from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
import hashlib
import re

from .world_schedule import is_weekend, is_high_school_setting

# Standard 5-block daily time blocks (minutes from midnight 0..1439)
SCHEDULE_TIME_BLOCKS = [
    (360, 719, "morning", "Morning"),
    (720, 779, "lunch", "Lunch"),
    (780, 1019, "afternoon", "Afternoon"),
    (1020, 1199, "evening", "Evening"),
]
# Night covers 1200..1439 and 0..359

# Boundary minutes where schedule transitions occur
BLOCK_BOUNDARIES = [
    (420, "commute"),         # 07:00 Morning Wake & Commute
    (480, "morning"),         # 08:00 Class Start / Morning Opening
    (720, "lunch"),           # 12:00 Lunch Break
    (780, "afternoon"),       # 13:00 Afternoon Classes / Weekend Afternoon
    (900, "extracurricular"), # 15:00 After-School Extracurriculars (Weekdays)
    (1020, "evening"),        # 17:00 Evening Shift
    (1200, "night"),          # 20:00 After-Hours / Return Home
]


def get_time_block_key(minute: int) -> str:
    """Returns the canonical 5-block identifier: 'morning', 'lunch', 'afternoon', 'evening', or 'night'."""
    safe_min = int(minute or 0) % 1440
    for start, end, key, _ in SCHEDULE_TIME_BLOCKS:
        if start <= safe_min <= end:
            return key
    return "night"


def get_detailed_npc_time_phase(
    minute: int,
    current_day: int = 1,
    scen_key: str = "high_school_drama"
) -> str:
    """
    Returns the granular High School schedule phase key for an NPC at (minute, current_day):
      - 'night': 20:00–06:59 (1200..1439 and 0..419)
      - 'commute': 07:00–07:59 (420..479)
      - 'morning': 08:00–11:59 (480..719)
      - 'lunch': 12:00–12:59 (720..779)
      - 'class_afternoon': 13:00–14:59 (780..899) on weekdays, or 'afternoon' on weekends
      - 'extracurricular': 15:00–19:59 (900..1199) on weekdays, or 'afternoon'/'evening' on weekends
    """
    safe_min = int(minute or 0) % 1440
    if not is_high_school_setting(scen_key):
        return get_time_block_key(safe_min)

    if safe_min >= 1200 or safe_min < 420:
        return "night"
    if 420 <= safe_min < 480:
        return "commute"
    if 480 <= safe_min < 720:
        return "morning"
    if 720 <= safe_min < 780:
        return "lunch"
    if is_weekend(current_day):
        if 780 <= safe_min < 1020:
            return "afternoon"
        return "evening"
    else:
        if 780 <= safe_min < 900:
            return "class_afternoon"
        return "extracurricular"


def is_schedule_transition_imminent(
    current_minute: int,
    window_minutes: int = 15,
    current_day: int = 1,
    scen_key: str = "high_school_drama"
) -> Tuple[bool, str, str, int]:
    """
    Checks if current_minute is within window_minutes prior to a schedule block boundary.
    Returns: (is_imminent, current_block, next_block, minutes_remaining).
    """
    safe_min = int(current_minute or 0) % 1440
    cur_block = get_time_block_key(safe_min)
    weekend = is_weekend(current_day)
    is_hs = is_high_school_setting(scen_key)

    if is_hs and weekend:
        active_boundaries = [
            (420, "morning"),
            (720, "lunch"),
            (780, "afternoon"),
            (1020, "evening"),
            (1200, "night"),
        ]
    elif is_hs and not weekend:
        active_boundaries = [
            (420, "commute"),
            (480, "morning"),
            (720, "lunch"),
            (780, "afternoon"),
            (900, "extracurricular"),
            (1020, "evening"),
            (1200, "night"),
        ]
    else:
        active_boundaries = [
            (360, "morning"),
            (720, "lunch"),
            (780, "afternoon"),
            (1020, "evening"),
            (1200, "night"),
        ]

    for boundary_min, next_block in active_boundaries:
        diff = (boundary_min - safe_min) % 1440
        if 0 < diff <= window_minutes:
            return True, cur_block, next_block, diff

    return False, cur_block, "", 0


def detect_schedule_boundary_crossed(
    old_day: int,
    old_minute: int,
    new_day: int,
    new_minute: int,
    scen_key: str = "high_school_drama",
) -> Dict[str, Any]:
    """
    Deterministically detects if advancing the clock from (old_day, old_minute)
    to (new_day, new_minute) crossed a schedule phase or time-block boundary.

    Returns:
      {
        "crossed": bool,
        "old_phase": str,
        "new_phase": str,
        "old_block": str,
        "new_block": str,
        "day_changed": bool,
        "transition_label": str,
      }
    """
    old_d = int(old_day or 1)
    new_d = int(new_day or old_d)
    old_m = int(old_minute or 480) % 1440
    new_m = int(new_minute or old_m) % 1440

    old_phase = get_detailed_npc_time_phase(old_m, current_day=old_d, scen_key=scen_key)
    new_phase = get_detailed_npc_time_phase(new_m, current_day=new_d, scen_key=scen_key)
    old_block = get_time_block_key(old_m)
    new_block = get_time_block_key(new_m)
    day_changed = (new_d != old_d)
    crossed = bool(day_changed or (old_phase != new_phase) or (old_block != new_block))

    phase_labels = {
        "commute": "Morning Commute & Arrival (07:00)",
        "morning": "Morning Period (08:00)",
        "lunch": "Midday Lunch Break (12:00)",
        "class_afternoon": "Afternoon Classes (13:00)",
        "extracurricular": "After-School Extracurriculars & Clubs (15:00)",
        "afternoon": "Afternoon Shift",
        "evening": "Evening Hours",
        "night": "Night & After-Hours (20:00+)",
    }
    transition_label = phase_labels.get(new_phase, new_phase.replace("_", " ").title()) if crossed else ""

    return {
        "crossed": crossed,
        "old_phase": old_phase,
        "new_phase": new_phase,
        "old_block": old_block,
        "new_block": new_block,
        "day_changed": day_changed,
        "transition_label": transition_label,
    }


def _is_anomalous_incursions_setting(scen_key: str) -> bool:
    """Returns True if `scen_key` is an Anomalous Incursions / Urban Fantasy scenario."""
    low = str(scen_key or "").strip().lower()
    if any(k in low for k in ("anomalous", "urban_anomalies", "urban_fantasy", "scp")):
        return True
    try:
        import scenario_data
        return bool(scenario_data.is_anomalous_incursions_scenario(scen_key))
    except Exception:
        return False


_ROTATING_TEACHER_CLASSROOMS: List[Tuple[str, str]] = [
    ("loc_homeroom", "Main Academy Campus ➔ Main Campus Building ➔ Homeroom Classroom"),
    ("loc_freshman_class", "Main Academy Campus ➔ Main Campus Building ➔ Freshman Classroom 1-A"),
    ("loc_sophomore_class", "Main Academy Campus ➔ Main Campus Building ➔ Sophomore Classroom 2-A"),
    ("loc_junior_class", "Main Academy Campus ➔ Main Campus Building ➔ Junior Classroom 3-B"),
    ("loc_senior_class", "Main Academy Campus ➔ Main Campus Building ➔ Senior Classroom 4-A"),
]


def get_rotating_classroom_for_teacher(
    role: str,
    current_day: int = 1,
    phase: str = "morning",
) -> str:
    """
    Deterministically rotates the 5 classroom subject teachers 1-to-1 across the 5 grade
    classrooms (`loc_homeroom`, `loc_freshman_class`, `loc_sophomore_class`,
    `loc_junior_class`, `loc_senior_class`) during active weekday lectures (`morning` &
    `class_afternoon`). Returns `""` for specialist/non-rotating faculty & staff.
    """
    r_low = str(role or "").strip().lower()
    teacher_idx = -1
    if "mathematics" in r_low or "math " in f"{r_low} ":
        teacher_idx = 0
    elif "history" in r_low or "civics" in r_low:
        teacher_idx = 1
    elif "english" in r_low or "literature" in r_low:
        teacher_idx = 2
    elif "foreign language" in r_low:
        teacher_idx = 3
    elif "biology" in r_low or "ecology" in r_low:
        teacher_idx = 4

    if teacher_idx < 0:
        return ""
    safe_day = max(1, int(current_day or 1))
    aft_shift = 1 if str(phase or "").lower() == "class_afternoon" else 0
    cls_idx = (teacher_idx + safe_day + aft_shift) % len(_ROTATING_TEACHER_CLASSROOMS)
    return _ROTATING_TEACHER_CLASSROOMS[cls_idx][0]


def _resolve_student_classroom_node_and_path(
    npc: Dict[str, Any],
    primary_fac: str = "",
) -> Tuple[str, str]:
    """Resolves the exclusive grade classroom `(node_id, fallback_path)` for a High School student."""
    basic = npc.get("basic_info") if isinstance(npc.get("basic_info"), dict) else {}
    grade_low = str(npc.get("grade") or basic.get("grade") or "").strip().lower()
    clique_low = str(npc.get("clique") or basic.get("clique") or "").strip().lower()
    pf_low = str(primary_fac or "").lower()

    if grade_low == "freshman" or "freshman classroom" in pf_low:
        return "loc_freshman_class", "Main Academy Campus ➔ Main Campus Building ➔ Freshman Classroom 1-A"
    if grade_low == "sophomore" or "sophomore classroom" in pf_low:
        return "loc_sophomore_class", "Main Academy Campus ➔ Main Campus Building ➔ Sophomore Classroom 2-A"
    if grade_low == "senior" or "senior classroom" in pf_low:
        return "loc_senior_class", "Main Academy Campus ➔ Main Campus Building ➔ Senior Classroom 4-A"
    if "junior classroom 3-b" in pf_low or (
        grade_low == "junior" and clique_low in ("upperclassmen", "hedonists") and "homeroom" not in pf_low
    ):
        return "loc_junior_class", "Main Academy Campus ➔ Main Campus Building ➔ Junior Classroom 3-B"
    hr_path = primary_fac if "homeroom" in pf_low else "Main Academy Campus ➔ Main Campus Building ➔ Homeroom Classroom"
    return "loc_homeroom", hr_path


def _resolve_school_faculty_class_station(
    role: str,
    primary_fac: str = "",
    current_day: int = 1,
    phase: str = "morning",
) -> Tuple[str, str]:
    """Resolves (node_id, fallback_path) for High School faculty & campus staff during weekday class periods."""
    rot_cls = get_rotating_classroom_for_teacher(role, current_day=current_day, phase=phase)
    if rot_cls:
        for c_nid, c_path in _ROTATING_TEACHER_CLASSROOMS:
            if c_nid == rot_cls:
                return c_nid, c_path

    comb = f"{role} {primary_fac}".lower()
    if "nurse" in comb or ("infirmary" in comb and "boarded" not in comb):
        return "loc_school_infirmary", "Main Academy Campus ➔ Main Campus Building ➔ School Infirmary"
    if "librarian" in comb or "library" in comb:
        return "loc_library", "Main Academy Campus ➔ Main Campus Building ➔ School Library"
    if any(k in comb for k in ("cafeteria", "chef", "cook", "lunch")):
        return "loc_cafeteria", "Main Academy Campus ➔ Student Commons & Central Plaza ➔ Campus Dining Hall & Cafeteria"
    if any(k in comb for k in ("custodian", "groundskeeper", "janitor")):
        return "loc_greenhouse", "Main Academy Campus ➔ Student Commons & Central Plaza ➔ Botanical Glasshouse"
    if any(k in comb for k in ("science", "chem", "robotics", "physics", "lab")):
        return "loc_science_lab", "Main Academy Campus ➔ Main Campus Building ➔ Chemistry & Science Lab"
    if any(k in comb for k in ("coach", "pe ", "p.e.", "physical")):
        return "loc_gymnasium", "Main Academy Campus ➔ School Grounds & Athletics ➔ Main Gymnasium"
    if "music" in comb:
        return "loc_old_east_music_room", "Main Academy Campus ➔ Cultural Arts & Student Union ➔ Old East Wing Music Room"
    if "art" in comb and "martial" not in comb:
        return "loc_fine_arts_studio", "Main Academy Campus ➔ Cultural Arts & Student Union ➔ Fine Arts Studio"
    if "homeroom" in comb:
        return "loc_homeroom", "Main Academy Campus ➔ Main Campus Building ➔ Homeroom Classroom"
    return "loc_staff_room", "Main Academy Campus ➔ Main Campus Building ➔ Teachers' Staff Room"


def _resolve_school_extracurricular_node(
    role: str,
    club: str,
    trait_names: List[str],
    seed_val: int,
    primary_fac: str = "",
    clique: str = "",
) -> Tuple[str, str]:
    """
    Resolves (node_id, fallback_tiered_path) for a High School NPC's club or sport
    during the 15:00–20:00 Extracurricular Period (and weekend club/sport sessions).
    """
    sport_probe = f"{club} {role} {primary_fac}".lower()
    if clique.lower() == "hedonists" or "velvet basement salon" in sport_probe or role.startswith("salon "):
        return "loc_nsfw_faction_hq", "Main Academy Campus ➔ Abandoned Old Campus Building ➔ Velvet Basement Salon"
    if "nurse" in role or ("infirmary" in sport_probe and "boarded" not in sport_probe):
        return "loc_school_infirmary", "Main Academy Campus ➔ Main Campus Building ➔ School Infirmary"
    if "swim" in sport_probe or "swimming pool" in sport_probe:
        return "loc_pool", "Main Academy Campus ➔ School Grounds & Athletics ➔ Swimming Pool Facility"
    if any(c in sport_probe for c in ("kendo", "martial", "judo", "karate", "aikido", "fencing", "dojo")):
        return "loc_martial_arts_dojo", "Main Academy Campus ➔ School Grounds & Athletics ➔ Martial Arts Dojo"
    if any(c in sport_probe for c in ("track", "soccer", "football", "baseball", "tennis", "running", "sprinter", "athletic field", "sports_field")):
        return "loc_sports_field", "Main Academy Campus ➔ School Grounds & Athletics ➔ Athletic Field"
    if any(c in club for c in ("gym", "basketball", "volleyball", "athletics", "sports", "badminton", "cheer")):
        return "loc_gymnasium", "Main Academy Campus ➔ School Grounds & Athletics ➔ Main Gymnasium"
    if any(c in club for c in ("drama", "theater", "theatre", "acting", "stage")):
        return "loc_auditorium_stage", "Main Academy Campus ➔ Cultural Arts & Student Union ➔ School Auditorium Stage"
    if any(c in club for c in ("art", "drawing", "sculpture", "painting", "manga", "photography")):
        return "loc_fine_arts_studio", "Main Academy Campus ➔ Cultural Arts & Student Union ➔ Fine Arts Studio"
    if any(c in club for c in ("music", "band", "orchestra", "choir", "jazz", "guitar", "piano")):
        return "loc_old_east_music_room", "Main Academy Campus ➔ Cultural Arts & Student Union ➔ Old East Wing Music Room"
    if any(c in club for c in ("science", "chem", "biology", "astronomy", "robotics", "physics")):
        return "loc_science_lab", "Main Academy Campus ➔ Main Campus Building ➔ Chemistry & Science Lab"
    if any(c in club for c in ("council", "president", "treasurer", "vice president", "secretary")):
        return "loc_student_council", "Main Academy Campus ➔ Cultural Arts & Student Union ➔ Student Council Office"
    if any(c in club for c in ("library", "book", "literature", "literary", "poetry", "reading")):
        return "loc_library", "Main Academy Campus ➔ Main Campus Building ➔ School Library"
    if any(c in club for c in ("broadcast", "newspaper", "media", "journalism", "radio", "press")):
        return "loc_broadcasting_room", "Main Academy Campus ➔ Cultural Arts & Student Union ➔ Campus Media & Broadcasting Room"
    if any(c in club for c in ("garden", "botany", "plant", "floral", "horticulture")):
        return "loc_greenhouse", "Main Academy Campus ➔ Student Commons & Central Plaza ➔ Botanical Glasshouse"
    if any(c in club for c in ("occult", "paranormal", "tarot", "mystery", "supernatural")):
        return "loc_old_storage_3b", "Main Academy Campus ➔ Abandoned Old Campus Building ➔ Old Storage Room 3-B"

    # Trait / Role fallbacks when no explicit club string is set
    if any(w in role for w in ("custodian", "groundskeeper", "janitor")):
        return "loc_greenhouse", "Main Academy Campus ➔ Student Commons & Central Plaza ➔ Botanical Glasshouse"
    if any(w in role for w in ("chef", "cafeteria", "cook")):
        return "loc_cafeteria", "Main Academy Campus ➔ Student Commons & Central Plaza ➔ Campus Dining Hall & Cafeteria"
    if any(w in role for w in ("teacher", "staff", "principal", "counselor", "dean")):
        return "loc_staff_room", "Main Academy Campus ➔ Main Campus Building ➔ Teachers' Staff Room"
    if "librarian" in role:
        return "loc_library", "Main Academy Campus ➔ Main Campus Building ➔ School Library"
    if any(t in trait_names for t in ("delinquent", "brawler", "rebel", "truant")) or "delinquent" in role:
        return "loc_behind_gym_sheds", "Main Academy Campus ➔ School Grounds & Athletics ➔ Behind Gym Storage Sheds"
    if any(t in trait_names for t in ("jock", "athletic", "sporty", "runner", "swimmer")) or any(w in role for w in ("jock", "athlete", "captain")):
        sport_opts = [
            ("loc_gymnasium", "Main Academy Campus ➔ School Grounds & Athletics ➔ Main Gymnasium"),
            ("loc_sports_field", "Main Academy Campus ➔ School Grounds & Athletics ➔ Athletic Field"),
        ]
        return sport_opts[seed_val % len(sport_opts)]

    default_opts = [
        ("loc_library", "Main Academy Campus ➔ Main Campus Building ➔ School Library"),
        ("loc_courtyard", "Main Academy Campus ➔ Student Commons & Central Plaza ➔ Central Courtyard"),
        ("loc_vending_pavilion", "Main Academy Campus ➔ Student Commons & Central Plaza ➔ Vending Machine Pavilion"),
        ("loc_clubroom_corridor", "Main Academy Campus ➔ Cultural Arts & Student Union ➔ Student Clubroom Corridor"),
    ]
    return default_opts[seed_val % len(default_opts)]


_ANOMALOUS_HANGOUT_LEAF_MAP: List[Tuple[str, str]] = [
    ("shattered fountain atrium", "sub_plaza_fountain"),
    ("open-kitchen broth", "sub_ramen_counter_hall"),
    ("warded iron cage", "sub_uni_forbidden_cage"),
    ("lower subway platform", "sub_transit_platform"),
    ("corrugated iron loading bay", "sub_foundry_loading"),
    ("sub-basement morgue", "loc_hosp_morgue"),
    ("window eat-in counter nook", "sub_subkonbini_nook"),
    ("rhythm & fighting cabinet", "sub_cabinet_aisles"),
    ("end-of-pier fishing", "sub_pier_observation"),
    ("duck pond", "sub_park_pond"),
    ("shaded vending machine pavilion", "sub_vending_alcove"),
    ("outdoor running track", "sub_athletic_track"),
    ("80th-floor infinity pool", "sub_sky_infinity_bar"),
    ("panoramic tarmac-view champagne bar", "sub_ap_runway_bar"),
    ("candlelit amphitheater", "sub_auction_amphitheater"),
    ("glass skywalk dining terrace", "sub_plaza_terrace"),
    ("streetwear & designer apparel", "sub_fashion_boutique"),
    ("smoke-hazy billiards lounge", "sub_billiards_lounge"),
    ("brandy & cigar parlour", "sub_elysium_cigar_room"),
    ("gantry crane operator cab", "sub_pier_gantry"),
    ("appraisal desk & leyline map", "sub_curio_appraisal"),
    ("chain-link ring & betting", "sub_fight_cage"),
    ("main cocktail lounge & quartet", "sub_jazz_lounge"),
    ("neon atrium food court", "sub_food_court"),
    ("misty ravine suspension footbridge", "sub_cedar_bridge"),
    ("brass ticket rotunda", "sub_uc_brass_rotunda"),
    ("school rooftop", "loc_school_rooftop"),
    ("stained-glass nave", "sub_cathedral_nave"),
    ("numbers station chamber", "sub_bunker_radio_room"),
    ("still-water ossuary rotunda", "sub_uc_black_font"),
    ("rare book mezzanine", "sub_roastery_mezzanine"),
    ("infinite hall of mirrors", "loc_tp_mirror_labyrinth"),
    ("abandoned fallout control room", "sub_bunker_command"),
    ("under-pier catwalk", "sub_smuggler_pier"),
    ("sub-basement contraband relic stalls", "sub_black_market_bazaar"),
    ("anomaly doppler array", "sub_ap_weather_array"),
    ("rusted freight boxcars", "sub_rail_boxcars"),
    ("velvet hookah & drink parlor", "sub_red_lantern_parlor"),
    ("main worship hall", "loc_et_main_sanctuary"),
    ("five-story pagoda", "loc_et_five_story_pagoda"),
    ("zen rock garden", "loc_et_zen_tea_garden"),
    ("onsen bathhouse", "loc_et_onsen_bathhouse"),
    ("grand torii gate", "loc_et_torii_approach"),
]


def _resolve_anomalous_npc_profile(npc: Dict[str, Any], seed_val: int) -> Dict[str, Any]:
    """
    Deterministically extracts `(faction_id, primary_node_id, secondary_node_id, agent_tier, primary_fac, secondary_fac)`
    for Special Agents, `school_directory` rows, or general urban NPCs in `anomalous_incursions`.
    """
    basic = npc.get("basic_info") if isinstance(npc.get("basic_info"), dict) else {}
    fac_id = str(
        npc.get("faction_id")
        or npc.get("faction_archetype_key")
        or basic.get("faction_id")
        or ""
    ).strip().lower()

    role = str(npc.get("role") or basic.get("role") or npc.get("occupation") or "").lower()
    club = str(npc.get("club") or basic.get("faction") or "").lower()
    grade = str(npc.get("grade") or "").lower()
    prim_fac = str(npc.get("primary_facility") or basic.get("primary_facility") or basic.get("location") or "").strip()
    sec_fac = str(npc.get("secondary_facility") or basic.get("secondary_facility") or "").strip()
    prim_low = prim_fac.lower()
    sec_low = sec_fac.lower()
    probe = f"{fac_id} {role} {club} {prim_low}"

    if not fac_id:
        if any(k in probe for k in ("hidden sanctum", "hierophant", "cantor of frequencies", "abyssal conduit", "cryptic archivist", "veiled acolyte", "rift-watcher", "cult_faction")):
            fac_id = "cult_faction"
        elif any(k in probe for k in ("shadow exchange", "shadow broker", "wetwork", "black-market quartermaster", "signal interceptor", "relic runner", "covert fixer", "clandestine_faction")):
            fac_id = "clandestine_faction"
        elif any(k in probe for k in ("grand abbot", "barrier wards", "shikigami", "sacred blade", "shrine purification", "wandering ascetic", "novice shrine", "bell-ringer", "eastern grand temple", "monastic")):
            fac_id = "monastic_order"
        elif "operations hq" in prim_low or "operations spire" in prim_low or any(k in role for k in ("managing partner", "field operations commander", "senior occult appraiser", "close-quarters eliminator", "licensed bounty operative", "associate field contractor")):
            fac_id = "private_agency_2"
        elif "tower hq" in prim_low or any(k in role for k in ("chief executive & tactical", "hazard termination commander", "relic acquisition specialist", "ballistic resonance sniper", "contract combat specialist", "junior contract hunter")):
            fac_id = "private_agency_1"
        elif any(k in probe for k in ("bureau", "containment", "probationary", "mitigation", "public_agency", "forensic", "psychic resonance", "spatial recon", "heavy suppression")):
            fac_id = "public_agency"

    tier = int(npc.get("agent_tier") or basic.get("agent_tier") or 0)
    if not tier:
        m_tier = re.search(r"tier\s*(\d+)", grade)
        tier = int(m_tier.group(1)) if m_tier else 2

    p_nid = str(npc.get("primary_node_id") or basic.get("primary_node_id") or "").strip()
    if not p_nid and prim_low:
        if fac_id == "public_agency":
            for kw, nid in (
                ("executive & tactical dispatch", "loc_hq_executive_dispatch"),
                ("psychometric training", "loc_hq_training_range"),
                ("medical & psychic cleansing", "loc_hq_medical_bay"),
                ("occult forensics & entity research", "loc_hq_research_division"),
                ("tactical armory", "loc_hq_tactical_armory"),
                ("subterranean containment", "loc_hq_containment_sector"),
                ("field outfitter", "loc_hq_field_outfitter"),
                ("canteen & espresso", "loc_hq_canteen_cafe"),
                ("operative dormitories", "loc_hq_agent_dormitories"),
                ("main lobby", "loc_hq_main_lobby"),
            ):
                if kw in prim_low:
                    p_nid = nid
                    break
        elif fac_id in ("private_agency_1", "private_agency_2"):
            pfx = "sub_priv1_" if fac_id == "private_agency_1" else "sub_priv2_"
            for kw, sfx in (
                ("dispatch", "dispatch"),
                ("training", "training"),
                ("r&d", "research"),
                ("appraisal division", "research"),
                ("armory", "armory"),
                ("outfitter", "outfitter"),
                ("detox", "medbay"),
                ("canteen", "canteen"),
                ("espresso", "canteen"),
                ("quarters", "quarters"),
                ("vault", "vault"),
                ("lobby", "entrance"),
                ("entrance", "entrance"),
            ):
                if kw in prim_low:
                    p_nid = f"{pfx}{sfx}"
                    break
        elif fac_id == "monastic_order":
            for kw, nid in (
                ("five-story pagoda", "loc_et_five_story_pagoda"),
                ("zen rock garden", "loc_et_zen_tea_garden"),
                ("onsen bathhouse", "loc_et_onsen_bathhouse"),
                ("torii gate", "loc_et_torii_approach"),
                ("main worship hall", "loc_et_main_sanctuary"),
            ):
                if kw in prim_low:
                    p_nid = nid
                    break
        elif fac_id == "cult_faction":
            for kw, nid in (
                ("inner sanctum", "sub_cult_sanctum"),
                ("fracture altar", "sub_cult_altar"),
                ("holding cells", "sub_cult_cells"),
                ("apocrypha reliquary", "sub_cult_reliquary"),
                ("cloister", "sub_cult_cloister"),
                ("threshold entrance", "sub_cult_entrance"),
            ):
                if kw in prim_low:
                    p_nid = nid
                    break
        elif fac_id == "clandestine_faction":
            for kw, nid in (
                ("black-ledger vault", "sub_synd_vault"),
                ("auction pens", "sub_synd_pens"),
                ("brokerage floor", "sub_synd_floor"),
                ("cognitohazard lab", "sub_synd_lab"),
                ("security guardroom", "sub_synd_guardroom"),
                ("vault door entrance", "sub_synd_entrance"),
            ):
                if kw in prim_low:
                    p_nid = nid
                    break

    s_nid = str(npc.get("secondary_node_id") or basic.get("secondary_node_id") or "").strip()
    if not s_nid and sec_low:
        for kw, nid in _ANOMALOUS_HANGOUT_LEAF_MAP:
            if kw in sec_low:
                s_nid = nid
                break

    urban_day_fallbacks = [
        ("sub_plaza_fountain", "City Center ➔ Sunken Plaza Galleria ➔ Shattered Fountain Atrium"),
        ("sub_roastery_mezzanine", "Uptown District ➔ Uptown Roastery & Rare Bookshop ➔ Leather-Armchair Rare Book Mezzanine"),
        ("sub_food_court", "Downtown ➔ Neon Shopping Arcade & Mall ➔ Neon Atrium Food Court"),
        ("sub_park_pond", "Suburban Residential District ➔ Neighborhood Park ➔ Duck Pond & Wooden Footbridge"),
    ]
    urban_eve_fallbacks = [
        ("sub_ramen_counter_hall", "Downtown ➔ Late-Night Ramen & Izakaya Alley ➔ Open-Kitchen Broth & Counter Hall"),
        ("sub_jazz_lounge", "Downtown ➔ Basement Jazz & Cocktail Bar ➔ Main Cocktail Lounge & Quartet Stage"),
        ("sub_cabinet_aisles", "Downtown ➔ 24-Hour Arcade & Billiards Hall ➔ Rhythm & Fighting Cabinet Aisles"),
        ("sub_subkonbini_nook", "Suburban Residential District ➔ 24-Hour Corner Convenience Store ➔ Window Eat-In Counter Nook"),
    ]
    fb_day_nid, fb_day_path = urban_day_fallbacks[seed_val % len(urban_day_fallbacks)]
    fb_eve_nid, fb_eve_path = urban_eve_fallbacks[seed_val % len(urban_eve_fallbacks)]

    return {
        "faction_id": fac_id,
        "agent_tier": tier,
        "primary_node_id": p_nid or fb_day_nid,
        "secondary_node_id": s_nid or fb_eve_nid,
        "primary_path": prim_fac or fb_day_path,
        "secondary_path": sec_fac or fb_eve_path,
    }


def _is_town_citizen_or_youth_peer(npc: Dict[str, Any]) -> bool:
    """Returns True if `npc` is a High School Town Citizen or Out-of-School Youth Peer."""
    if not isinstance(npc, dict):
        return False
    basic = npc.get("basic_info") if isinstance(npc.get("basic_info"), dict) else {}
    grade = str(npc.get("grade") or basic.get("grade") or "").strip().lower()
    if grade in ("citizen", "youth peer"):
        return True
    summary = str(npc.get("personality_summary") or basic.get("description") or "")
    if "[TownArchetype:" in summary:
        return True
    srt = str(npc.get("social_role_type") or basic.get("social_role_type") or "").strip().lower()
    if srt == "adult_service" and grade != "faculty":
        return True
    return False


_HS_NODE_FALLBACK_PATHS: Dict[str, str] = {
    "loc_cafe": "Downtown ➔ Local Café",
    "loc_convenience_store": "Downtown ➔ Convenience Store",
    "loc_arcade": "Downtown ➔ Game Arcade",
    "loc_karaoke": "Downtown ➔ Karaoke Lounge",
    "loc_city_square": "Downtown ➔ City Square",
    "loc_transit_plaza": "Downtown ➔ City Square",
    "loc_restaurant": "Downtown ➔ Downtown Diner & Family Restaurant",
    "loc_clothing_store": "Downtown ➔ Casual Streetwear & Apparel Shop",
    "loc_brand_clothing_store": "Downtown ➔ Luxury Designer Boutique",
    "loc_accessories_store": "Downtown ➔ Accessories & Bijoux Emporium",
    "loc_gift_store": "Downtown ➔ Curio & Gift Shop",
    "loc_night_market": "Downtown ➔ Lantern Night Market & Bazaar",
    "loc_nightclub": "Downtown ➔ Neon Pulse Nightclub",
    "loc_adult_store": "Downtown ➔ Velvet Curtain Adult Boutique",
    "loc_love_hotel": "Downtown ➔ Mirage Boutique Love Hotel",
    "loc_local_park": "Residential Neighborhood ➔ Neighborhood Park",
    "loc_sandy_beach": "Seaside & Coastal Bay ➔ Sandy Beach & Coastline",
    "loc_coastal_pier": "Seaside & Coastal Bay ➔ Boardwalk Pier & Lighthouse",
    "loc_seaside_cafe": "Seaside & Coastal Bay ➔ Seaside Beach Shack",
    "loc_campsite": "Recreational Park ➔ Woodland Campsite & Cabin Grounds",
    "loc_park_lake": "Recreational Park ➔ Park Lake & Boathouse",
    "loc_mountain_lake": "Recreational Park ➔ Park Lake & Boathouse",
    "loc_hilltop_lookout": "Recreational Park ➔ Hilltop Scenic Lookout",
    "loc_summit_lookout": "Recreational Park ➔ Hilltop Scenic Lookout",
    "loc_sakura_grove": "Recreational Park ➔ Sakura Blossom Grove",
    "loc_park_shrine": "Recreational Park ➔ Wayside Shrine & Cedar Path",
    "loc_picnic_pavilions": "Recreational Park ➔ Picnic Pavilions & Open Lawn",
    "loc_school_gate": "Main Academy Campus ➔ Main Campus Building ➔ Entrance Foyer & Shoe Lockers",
    "loc_entrance_foyer": "Main Academy Campus ➔ Main Campus Building ➔ Entrance Foyer & Shoe Lockers",
    "loc_school_hallway": "Main Academy Campus ➔ Main Campus Building ➔ School Hallways",
    "loc_homeroom": "Main Academy Campus ➔ Main Campus Building ➔ Homeroom Classroom",
    "loc_freshman_class": "Main Academy Campus ➔ Main Campus Building ➔ Freshman Classroom 1-A",
    "loc_sophomore_class": "Main Academy Campus ➔ Main Campus Building ➔ Sophomore Classroom 2-A",
    "loc_junior_class": "Main Academy Campus ➔ Main Campus Building ➔ Junior Classroom 3-B",
    "loc_senior_class": "Main Academy Campus ➔ Main Campus Building ➔ Senior Classroom 4-A",
    "loc_empty_class": "Main Academy Campus ➔ Main Campus Building ➔ Empty Classroom",
    "loc_school_infirmary": "Main Academy Campus ➔ Main Campus Building ➔ School Infirmary",
    "loc_male_restroom": "Main Academy Campus ➔ Main Campus Building ➔ Boys' Restroom",
    "loc_female_restroom": "Main Academy Campus ➔ Main Campus Building ➔ Girls' Restroom",
    "loc_library": "Main Academy Campus ➔ Main Campus Building ➔ School Library",
    "loc_science_lab": "Main Academy Campus ➔ Main Campus Building ➔ Chemistry & Science Lab",
    "loc_staff_room": "Main Academy Campus ➔ Main Campus Building ➔ Teachers' Staff Room",
    "loc_school_rooftop": "Main Academy Campus ➔ Main Campus Building ➔ School Rooftop",
    "loc_gymnasium": "Main Academy Campus ➔ School Grounds & Athletics ➔ Main Gymnasium",
    "loc_sports_field": "Main Academy Campus ➔ School Grounds & Athletics ➔ Athletic Field",
    "loc_pool": "Main Academy Campus ➔ School Grounds & Athletics ➔ Swimming Pool Facility",
    "loc_martial_arts_dojo": "Main Academy Campus ➔ School Grounds & Athletics ➔ Martial Arts Dojo",
    "loc_male_shower_room": "Main Academy Campus ➔ School Grounds & Athletics ➔ Men's Locker & Shower Room",
    "loc_female_shower_room": "Main Academy Campus ➔ School Grounds & Athletics ➔ Women's Locker & Shower Room",
    "loc_behind_gym_sheds": "Main Academy Campus ➔ School Grounds & Athletics ➔ Behind Gym Storage Sheds",
    "loc_courtyard": "Main Academy Campus ➔ Student Commons & Central Plaza ➔ Central Courtyard",
    "loc_cafeteria": "Main Academy Campus ➔ Student Commons & Central Plaza ➔ Campus Dining Hall & Cafeteria",
    "loc_vending_pavilion": "Main Academy Campus ➔ Student Commons & Central Plaza ➔ Vending Machine Pavilion",
    "loc_greenhouse": "Main Academy Campus ➔ Student Commons & Central Plaza ➔ Botanical Glasshouse",
    "loc_student_council": "Main Academy Campus ➔ Cultural Arts & Student Union ➔ Student Council Office",
    "loc_auditorium_stage": "Main Academy Campus ➔ Cultural Arts & Student Union ➔ School Auditorium Stage",
    "loc_fine_arts_studio": "Main Academy Campus ➔ Cultural Arts & Student Union ➔ Fine Arts Studio",
    "loc_old_east_music_room": "Main Academy Campus ➔ Cultural Arts & Student Union ➔ Old East Wing Music Room",
    "loc_broadcasting_room": "Main Academy Campus ➔ Cultural Arts & Student Union ➔ Campus Media & Broadcasting Room",
    "loc_clubroom_corridor": "Main Academy Campus ➔ Cultural Arts & Student Union ➔ Student Clubroom Corridor",
    "loc_old_storage_3b": "Main Academy Campus ➔ Abandoned Old Campus Building ➔ Old Storage Room 3-B",
    "loc_nsfw_faction_hq": "Main Academy Campus ➔ Abandoned Old Campus Building ➔ Velvet Basement Salon",
}


def is_npc_nocturnal_or_night_shift(
    npc: Dict[str, Any],
    scen_key: str = "fantasy",
    current_day: int = 1,
) -> bool:
    """
    Returns True if the NPC operates on an active nocturnal / night-watch shift
    (preventing waypoints from falsely marking them 'Off-Duty: Sleeping' after 20:00).
    """
    if not isinstance(npc, dict):
        return False
    if is_high_school_setting(scen_key):
        basic = npc.get("basic_info") if isinstance(npc.get("basic_info"), dict) else {}
        if npc.get("is_nocturnal_shift") or basic.get("is_nocturnal_shift"):
            return True
        if _is_town_citizen_or_youth_peer(npc):
            from mechanics.social.town_roster import infer_town_schedule_archetype
            return infer_town_schedule_archetype(npc) in (
                "konbini_night", "police_night_patrol", "campus_night_guard",
                "lighthouse_caretaker", "commuter_salaryman",
                "night_merchant_nightclub", "day_night_merchant_adult_store",
            )
        return False
    if not _is_anomalous_incursions_setting(scen_key):
        return False
    name = str(npc.get("name") or "NPC").strip()
    basic = npc.get("basic_info") if isinstance(npc.get("basic_info"), dict) else {}
    role = str(npc.get("role") or basic.get("role") or npc.get("occupation") or "").lower()
    club = str(npc.get("club") or basic.get("club") or "").lower()
    seed_val = int(hashlib.md5(f"{name}_{role}_{club}".encode("utf-8")).hexdigest(), 16)
    prof = _resolve_anomalous_npc_profile(npc, seed_val)
    fac_id = prof["faction_id"]
    p_nid = prof["primary_node_id"]
    s_nid = prof["secondary_node_id"]

    if fac_id in ("cult_faction", "clandestine_faction"):
        return True
    if s_nid == "sub_uc_brass_rotunda" or "wandering ascetic" in role:
        return True
    if p_nid in ("loc_hq_main_lobby", "loc_hq_containment_sector", "sub_priv1_entrance", "sub_priv2_entrance", "loc_et_torii_approach"):
        return True
    if fac_id in ("public_agency", "private_agency_1", "private_agency_2", "monastic_order") and ((seed_val + int(current_day or 1)) % 3 == 0):
        return True
    return False


def _has_active_club_or_sport(role: str, club: str, trait_names: List[str]) -> bool:
    """Returns True if the NPC belongs to a school club or athletics team."""
    if club and club not in ("none", "unaffiliated", "go-home", "go home club", "faculty"):
        return True
    if any(t in trait_names for t in ("jock", "athletic", "sporty", "dedicated", "disciplined")):
        return True
    if any(w in role for w in ("jock", "athlete", "president", "council", "captain")):
        return True
    return False


def get_npc_schedule_node_ids(
    npc: Dict[str, Any],
    scen_key: str = "fantasy",
    current_day: int = 1,
    current_minute: Optional[int] = None,
    session_id: Optional[int] = None,
) -> Dict[str, str]:
    """
    Deterministically computes a schedule dictionary mapping time blocks
    ('morning', 'lunch', 'afternoon', 'evening', 'night', plus High School granular keys
    'commute', 'class_afternoon', 'extracurricular') to canonical graph node_ids.
    """
    if not isinstance(npc, dict):
        return {}

    name = str(npc.get("name") or "NPC").strip()
    basic = npc.get("basic_info") or {}
    role = str(npc.get("role") or basic.get("role") or npc.get("occupation") or "").lower()
    club = str(npc.get("club") or basic.get("club") or "").lower()
    traits = npc.get("unlocked_traits") or npc.get("traits") or basic.get("traits") or []
    trait_names = [str(t.get("name") if isinstance(t, dict) else t).lower() for t in traits if t]

    seed_val = int(hashlib.md5(f"{name}_{role}_{club}".encode("utf-8")).hexdigest(), 16)
    scen_key_low = str(scen_key or "").lower()
    is_school = is_high_school_setting(scen_key_low)
    weekend = is_weekend(current_day)
    name_slug = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')

    schedule_nodes: Dict[str, str] = {}

    primary_fac = str(npc.get("primary_facility") or basic.get("primary_facility") or basic.get("location") or "").strip()
    if is_school:
        if _is_town_citizen_or_youth_peer(npc):
            from mechanics.social.town_roster import get_town_citizen_schedule_nodes
            return get_town_citizen_schedule_nodes(
                npc, current_day=current_day, seed_val=seed_val, current_minute=current_minute
            )

        clique_low = str(npc.get("clique") or basic.get("clique") or "").strip().lower()
        gender_low = str(npc.get("gender") or basic.get("gender") or "").strip().lower()
        safe_min = (int(current_minute) % 1440) if current_minute is not None else None
        club_node, _ = _resolve_school_extracurricular_node(
            role, club, trait_names, seed_val, primary_fac=primary_fac, clique=clique_low
        )
        grade_low = str(npc.get("grade") or basic.get("grade") or "").strip().lower()
        is_faculty = grade_low == "faculty" or any(
            w in role for w in ("teacher", "staff", "principal", "counselor", "nurse", "librarian", "coach", "custodian", "chef", "dean")
        )
        fac_morning_node, _ = _resolve_school_faculty_class_station(role, primary_fac, current_day=current_day, phase="morning")
        fac_aft_node, _ = _resolve_school_faculty_class_station(role, primary_fac, current_day=current_day, phase="class_afternoon")
        student_cls_node, _ = _resolve_student_classroom_node_and_path(npc, primary_fac=primary_fac)
        house_nid = f"loc_{name_slug}_house"

        is_athlete = (not is_faculty) and any(
            c in f"{role} {club} {clique_low}"
            for c in ("swim", "track", "basketball", "martial", "athletic", "sprinter", "runner", "tennis", "athletes")
        )
        shower_nid = "loc_male_shower_room" if gender_low == "male" else "loc_female_shower_room"
        is_nsfw_member = (not is_faculty) and (
            clique_low == "hedonists"
            or npc.get("faction_category") == "nsfw_club"
            or basic.get("faction_category") == "nsfw_club"
            or role.startswith("salon ")
            or "velvet basement salon" in primary_fac.lower()
        )
        is_nsfw_guest = False
        if not is_faculty and not is_nsfw_member and session_id:
            try:
                import scenario_data
                if scenario_data.is_nsfw_scenario(scen_key_low):
                    from mechanics.social.school_roster import get_nsfw_faction_invited_guest_names
                    is_nsfw_guest = name.lower() in get_nsfw_faction_invited_guest_names(
                        int(session_id), current_day, scen_key=scen_key_low
                    )
            except Exception:
                is_nsfw_guest = False

        if not weekend:
            # WEEKDAY SCHEDULE (Monday - Friday)
            # 0. Commute / Morning Prep (07:00 - 07:59)
            if is_faculty:
                if "librarian" in role:
                    schedule_nodes["commute"] = "loc_library"
                elif "chef" in role or "cafeteria" in role:
                    schedule_nodes["commute"] = "loc_cafeteria"
                elif "custodian" in role or "groundskeeper" in role:
                    schedule_nodes["commute"] = "loc_courtyard"
                else:
                    schedule_nodes["commute"] = "loc_staff_room"
            elif is_athlete and safe_min is not None and 435 <= safe_min < 470 and ("swim" in f"{role} {club}" or seed_val % 2 == 0):
                schedule_nodes["commute"] = shower_nid
            else:
                commute_opts = ["loc_school_gate", "loc_entrance_foyer", "loc_courtyard", student_cls_node]
                schedule_nodes["commute"] = commute_opts[seed_val % len(commute_opts)]

            # 1. Morning Class Period (08:00 - 11:59): Exclusive grade classrooms + rotating teachers
            if is_faculty:
                schedule_nodes["morning"] = fac_morning_node
            else:
                schedule_nodes["morning"] = student_cls_node

            # 2. Lunch Break (12:00 - 12:59)
            if is_faculty:
                if "nurse" in role:
                    schedule_nodes["lunch"] = "loc_school_infirmary"
                elif "librarian" in role:
                    schedule_nodes["lunch"] = "loc_library"
                elif "chef" in role or "cafeteria" in role:
                    schedule_nodes["lunch"] = "loc_cafeteria"
                else:
                    schedule_nodes["lunch"] = "loc_staff_room"
            elif any(t in trait_names for t in ("introverted", "shy", "bookworm", "studious")):
                schedule_nodes["lunch"] = "loc_library"
            elif any(t in trait_names for t in ("athletic", "energetic", "outgoing")):
                schedule_nodes["lunch"] = "loc_courtyard"
            else:
                schedule_nodes["lunch"] = "loc_cafeteria"

            # 3. Afternoon Class Period (13:00 - 14:59): Exclusive grade classrooms + rotating teachers
            if is_faculty:
                schedule_nodes["class_afternoon"] = fac_aft_node
            else:
                schedule_nodes["class_afternoon"] = student_cls_node

            # 4. Extracurricular Period (15:00 - 19:59): Clubs, Sports, Showers, Nurse 17:00 lock, NSFW Salon 16:00-20:00
            if "nurse" in role:
                nurse_after_five = bool(safe_min is not None and safe_min >= 1020)
                schedule_nodes["extracurricular"] = house_nid if nurse_after_five else "loc_school_infirmary"
                schedule_nodes["afternoon"] = "loc_school_infirmary"
                schedule_nodes["evening"] = house_nid
            elif is_nsfw_member or is_nsfw_guest:
                in_weekday_salon = (safe_min is None) or (960 <= safe_min < 1200)
                pre_salon = "loc_clubroom_corridor" if is_nsfw_member else club_node
                schedule_nodes["extracurricular"] = "loc_nsfw_faction_hq" if in_weekday_salon else pre_salon
                schedule_nodes["afternoon"] = pre_salon if (safe_min is not None and safe_min < 960) else "loc_nsfw_faction_hq"
                schedule_nodes["evening"] = "loc_nsfw_faction_hq"
            elif is_athlete and safe_min is not None and (
                1110 <= safe_min < 1170 or (((seed_val + current_day) % 3 == 0) and 990 <= safe_min < 1035)
            ):
                schedule_nodes["extracurricular"] = shower_nid
                schedule_nodes["afternoon"] = shower_nid
                schedule_nodes["evening"] = shower_nid
            else:
                schedule_nodes["extracurricular"] = club_node
                schedule_nodes["afternoon"] = club_node
                schedule_nodes["evening"] = club_node

            # 5. Night (20:00 - 06:59): Everyone returns home
            schedule_nodes["night"] = house_nid

        else:
            # WEEKEND SCHEDULE (Saturday - Sunday)
            roam_morning = ["loc_cafe", "loc_local_park", "loc_coastal_pier", "loc_park_lake", "loc_sakura_grove", "loc_city_square"]
            roam_lunch = ["loc_cafe", "loc_restaurant", "loc_seaside_cafe", "loc_arcade", "loc_picnic_pavilions"]
            roam_afternoon = [
                "loc_arcade", "loc_karaoke", "loc_clothing_store", "loc_gift_store",
                "loc_sandy_beach", "loc_coastal_pier", "loc_hilltop_lookout", "loc_sakura_grove", "loc_cafe"
            ]
            roam_evening = ["loc_night_market", "loc_karaoke", "loc_arcade", "loc_restaurant", "loc_city_square", "loc_convenience_store"]

            has_club_sport = _has_active_club_or_sport(role, club, trait_names) and not is_faculty
            trains_on_weekend = has_club_sport and ((seed_val + current_day) % 2 == 0) and not is_nsfw_member

            schedule_nodes["commute"] = house_nid if (seed_val % 2 == 0) else roam_morning[seed_val % len(roam_morning)]
            if is_athlete and trains_on_weekend and safe_min is not None and 660 <= safe_min < 710:
                schedule_nodes["morning"] = shower_nid
            else:
                schedule_nodes["morning"] = club_node if trains_on_weekend else roam_morning[seed_val % len(roam_morning)]
            schedule_nodes["lunch"] = roam_lunch[(seed_val >> 1) % len(roam_lunch)]

            if is_nsfw_member or is_nsfw_guest:
                # Weekend Velvet Basement Salon gathering: 15:00–21:00 (900..1259)
                in_wknd_aft = (safe_min is None) or (safe_min >= 900)
                in_wknd_night = bool(safe_min is not None and 1200 <= safe_min < 1260)
                pre_wknd = roam_afternoon[(seed_val >> 2) % len(roam_afternoon)]
                schedule_nodes["class_afternoon"] = "loc_nsfw_faction_hq" if in_wknd_aft else pre_wknd
                schedule_nodes["extracurricular"] = schedule_nodes["class_afternoon"]
                schedule_nodes["afternoon"] = schedule_nodes["class_afternoon"]
                schedule_nodes["evening"] = "loc_nsfw_faction_hq"
                schedule_nodes["night"] = "loc_nsfw_faction_hq" if in_wknd_night else house_nid
            else:
                schedule_nodes["class_afternoon"] = club_node if trains_on_weekend else roam_afternoon[(seed_val >> 2) % len(roam_afternoon)]
                schedule_nodes["extracurricular"] = schedule_nodes["class_afternoon"]
                schedule_nodes["afternoon"] = schedule_nodes["extracurricular"]
                schedule_nodes["evening"] = roam_evening[(seed_val >> 3) % len(roam_evening)]
                schedule_nodes["night"] = house_nid

        # 6. Student Part-Time Shifts (Mon/Wed/Fri or Tue/Thu 17:00–21:30 + 1 Weekend Day 12:00–17:00)
        if not is_faculty:
            from mechanics.social.town_roster import get_student_part_time_spec, is_student_on_part_time_shift
            if current_minute is not None:
                active_pt = is_student_on_part_time_shift(npc, current_day, current_minute, session_id=session_id or 0)
                if active_pt:
                    pt_nid = active_pt["venue_node_id"]
                    for k_phase in ("lunch", "class_afternoon", "extracurricular", "afternoon", "evening", "night"):
                        schedule_nodes[k_phase] = pt_nid
            else:
                pt_spec = get_student_part_time_spec(npc)
                if pt_spec:
                    day_mod = max(1, int(current_day or 1)) % 7
                    if weekend and day_mod in pt_spec["weekend_mods"]:
                        schedule_nodes["lunch"] = pt_spec["venue_node_id"]
                        schedule_nodes["class_afternoon"] = pt_spec["venue_node_id"]
                        schedule_nodes["extracurricular"] = pt_spec["venue_node_id"]
                        schedule_nodes["afternoon"] = pt_spec["venue_node_id"]
                    elif not weekend and day_mod in pt_spec["weekday_mods"]:
                        schedule_nodes["evening"] = pt_spec["venue_node_id"]

    elif _is_anomalous_incursions_setting(scen_key_low):
        prof = _resolve_anomalous_npc_profile(npc, seed_val)
        fac_id = prof["faction_id"]
        tier = prof["agent_tier"]
        p_nid = prof["primary_node_id"]
        s_nid = prof["secondary_node_id"]
        night_watch = is_npc_nocturnal_or_night_shift(npc, scen_key=scen_key_low, current_day=current_day)
        is_tp_hangout = s_nid.startswith("loc_tp_")

        if fac_id in ("cult_faction", "clandestine_faction"):
            # Nocturnal Covert Operatives: civilian cover by day, active sanctum / rift / black-market ops by night!
            day_cover = "sub_roastery_mezzanine" if is_tp_hangout else s_nid
            schedule_nodes["morning"] = day_cover if ((seed_val + current_day) % 2 == 0) else p_nid
            schedule_nodes["lunch"] = day_cover
            schedule_nodes["afternoon"] = day_cover
            schedule_nodes["evening"] = p_nid
            # During 22:00+ Night Shift, Veiled Acolyte Whisperer converges on Theme Park Hall of Mirrors Anomaly!
            schedule_nodes["night"] = s_nid if (is_tp_hangout or s_nid in ("sub_black_market_bazaar", "sub_red_lantern_parlor", "sub_smuggler_pier")) else p_nid
        elif fac_id == "monastic_order":
            is_student_acolyte = (s_nid == "loc_school_rooftop")
            is_subway_monk = (s_nid == "sub_uc_brass_rotunda")
            if not weekend:
                schedule_nodes["morning"] = s_nid if is_student_acolyte else p_nid
                schedule_nodes["lunch"] = s_nid if is_student_acolyte else "loc_et_zen_tea_garden"
                schedule_nodes["afternoon"] = p_nid
                schedule_nodes["evening"] = s_nid if is_subway_monk else (p_nid if is_student_acolyte else s_nid)
                schedule_nodes["night"] = s_nid if is_subway_monk else (p_nid if night_watch else "loc_et_onsen_bathhouse")
            else:
                on_temple_duty = ((seed_val + current_day) % 2 == 0) or tier >= 4
                schedule_nodes["morning"] = p_nid if on_temple_duty else s_nid
                schedule_nodes["lunch"] = "loc_et_zen_tea_garden" if on_temple_duty else s_nid
                schedule_nodes["afternoon"] = p_nid if on_temple_duty else s_nid
                schedule_nodes["evening"] = s_nid
                schedule_nodes["night"] = s_nid if is_subway_monk else (p_nid if night_watch else "loc_et_onsen_bathhouse")
        elif fac_id in ("public_agency", "private_agency_1", "private_agency_2"):
            canteen_nid = (
                "loc_hq_canteen_cafe" if fac_id == "public_agency"
                else ("sub_priv1_canteen" if fac_id == "private_agency_1" else "sub_priv2_canteen")
            )
            quarters_nid = (
                "loc_hq_agent_dormitories" if fac_id == "public_agency"
                else ("sub_priv1_quarters" if fac_id == "private_agency_1" else "sub_priv2_quarters")
            )
            eve_hangout = canteen_nid if s_nid in ("sub_vending_alcove", "sub_athletic_track", "loc_school_rooftop") else s_nid
            if not weekend:
                schedule_nodes["morning"] = p_nid
                schedule_nodes["lunch"] = canteen_nid if (seed_val % 2 == 0) else s_nid
                # Tier 1-2 field operatives alternate afternoon HQ duty with metropolitan field patrol
                field_patrol = (tier <= 2 and ((seed_val + current_day) % 2 == 0))
                schedule_nodes["afternoon"] = s_nid if field_patrol else p_nid
                schedule_nodes["evening"] = eve_hangout
                if night_watch:
                    schedule_nodes["night"] = p_nid
                elif s_nid in ("sub_ramen_counter_hall", "sub_cabinet_aisles", "sub_subkonbini_nook", "sub_billiards_lounge", "sub_jazz_lounge") and ((seed_val + current_day) % 2 == 1):
                    schedule_nodes["night"] = s_nid
                else:
                    schedule_nodes["night"] = quarters_nid if tier <= 2 else f"loc_{name_slug}_apartment"
            else:
                weekend_duty = ((seed_val + current_day) % 2 == 0)
                schedule_nodes["morning"] = p_nid if weekend_duty else s_nid
                schedule_nodes["lunch"] = s_nid
                schedule_nodes["afternoon"] = p_nid if weekend_duty else s_nid
                schedule_nodes["evening"] = eve_hangout
                schedule_nodes["night"] = p_nid if night_watch else (quarters_nid if tier <= 2 else f"loc_{name_slug}_apartment")
        else:
            # General Urban / Civilian / Freelance Contacts in Anomalous Incursions
            schedule_nodes["morning"] = p_nid
            schedule_nodes["lunch"] = "sub_food_court" if (seed_val % 2 == 0) else s_nid
            schedule_nodes["afternoon"] = s_nid if weekend else p_nid
            schedule_nodes["evening"] = s_nid
            schedule_nodes["night"] = f"loc_{name_slug}_apartment"

    elif any(k in scen_key_low for k in ("cyberpunk", "sci_fi", "space")):
        if "cyberpunk" in scen_key_low:
            schedule_nodes["morning"] = "loc_corp_tower" if any(w in role for w in ("corpo", "executive", "agent")) else "loc_noodle_bar"
            schedule_nodes["lunch"] = "loc_downtown_plaza"
            if any(w in role for w in ("doctor", "ripper", "medic")):
                schedule_nodes["afternoon"] = "loc_ripperdoc_clinic"
            elif any(w in role for w in ("nomad", "smuggler")):
                schedule_nodes["afternoon"] = "loc_cargo_dock"
            else:
                schedule_nodes["afternoon"] = "loc_neon_alley"
            schedule_nodes["evening"] = "loc_nightclub"
            schedule_nodes["night"] = "loc_luxury_penthouse" if any(w in role for w in ("corpo", "executive")) else f"loc_{name_slug}_capsule"
        else:
            schedule_nodes["morning"] = "loc_bridge" if any(w in role for w in ("captain", "officer", "commander")) else "loc_station_promenade"
            schedule_nodes["lunch"] = "loc_station_promenade"
            if any(w in role for w in ("engineer", "mechanic", "tech")):
                schedule_nodes["afternoon"] = "loc_engineering"
            elif any(w in role for w in ("scientist", "researcher")):
                schedule_nodes["afternoon"] = "loc_research_base"
            else:
                schedule_nodes["afternoon"] = "loc_ship_dock"
            schedule_nodes["evening"] = "loc_station_promenade"
            schedule_nodes["night"] = f"loc_{name_slug}_quarters"

    elif "slice_of_life" in scen_key_low:
        schedule_nodes["morning"] = "loc_sol_roastery"
        schedule_nodes["lunch"] = "loc_sol_ramen_counter"
        if any(w in role for w in ("artist", "designer", "writer", "developer")):
            schedule_nodes["afternoon"] = "loc_sol_cowork_loft"
        elif any(w in role for w in ("athlete", "boxer", "gym")):
            schedule_nodes["afternoon"] = "loc_sol_boxing_gym"
        else:
            schedule_nodes["afternoon"] = "loc_sol_bookstore"
        schedule_nodes["evening"] = "loc_sol_jazz_bar"
        schedule_nodes["night"] = f"loc_{name_slug}_studio"

    elif "steampunk" in scen_key_low:
        schedule_nodes["morning"] = "loc_alchemist_guild"
        schedule_nodes["lunch"] = "loc_gentlemans_club"
        if any(w in role for w in ("mechanist", "inventor", "tinkerer")):
            schedule_nodes["afternoon"] = "loc_mechanist_vaults"
        elif any(w in role for w in ("boiler", "foundry", "furnace")):
            schedule_nodes["afternoon"] = "loc_furnace_complex"
        else:
            schedule_nodes["afternoon"] = "loc_observation_deck"
        schedule_nodes["evening"] = "loc_gentlemans_club"
        schedule_nodes["night"] = f"loc_{name_slug}_cabin"

    elif "dark_fantasy" in scen_key_low:
        schedule_nodes["morning"] = "loc_town_square"
        schedule_nodes["lunch"] = "loc_grim_tavern"
        if any(w in role for w in ("witch", "coven", "occult")):
            schedule_nodes["afternoon"] = "loc_witch_coven"
        elif any(w in role for w in ("guard", "torturer", "knight")):
            schedule_nodes["afternoon"] = "loc_dungeon_keep"
        else:
            schedule_nodes["afternoon"] = "loc_bone_chapel"
        schedule_nodes["evening"] = "loc_grim_tavern"
        schedule_nodes["night"] = f"loc_{name_slug}_cell"

    elif "nuclear_post_apocalypse" in scen_key_low:
        schedule_nodes["morning"] = "loc_scavenger_bazaar"
        schedule_nodes["lunch"] = "loc_saloon"
        if any(w in role for w in ("overseer", "commander")):
            schedule_nodes["afternoon"] = "loc_overseer_office"
        elif any(w in role for w in ("gladiator", "brawler")):
            schedule_nodes["afternoon"] = "loc_gladiator_pit"
        else:
            schedule_nodes["afternoon"] = "loc_subway_terminal"
        schedule_nodes["evening"] = "loc_saloon"
        schedule_nodes["night"] = f"loc_{name_slug}_shelter"

    elif "isekai" in scen_key_low:
        schedule_nodes["morning"] = "loc_summoning_chamber"
        schedule_nodes["lunch"] = "loc_market_district_isekai"
        schedule_nodes["afternoon"] = "loc_elven_sanctuary_isekai"
        schedule_nodes["evening"] = "loc_guild_hall_isekai"
        schedule_nodes["night"] = f"loc_{name_slug}_inn"

    else:
        # Default / Fantasy
        schedule_nodes["morning"] = "loc_guild_hall"
        schedule_nodes["lunch"] = "loc_market_district"
        if any(w in role for w in ("guard", "knight", "soldier", "paladin")):
            schedule_nodes["afternoon"] = "loc_imperial_palace"
        elif any(w in role for w in ("hunter", "tracker")):
            schedule_nodes["afternoon"] = "loc_hunters_trail"
        else:
            schedule_nodes["afternoon"] = "loc_guild_hall"
        schedule_nodes["evening"] = "loc_sailor_tavern"
        schedule_nodes["night"] = f"loc_{name_slug}_quarters"

    return schedule_nodes


def get_npc_scheduled_node_id(
    npc: Dict[str, Any],
    current_minute: int = 480,
    scen_key: str = "fantasy",
    time_slot: str = "",
    current_day: int = 1,
    session_id: Optional[int] = None
) -> str:
    """Returns the canonical node_id where the NPC is scheduled at (current_minute, current_day) or time_slot."""
    if session_id:
        try:
            from mechanics.system.commitments_engine import inject_npc_schedule_overrides
            npc_id = str(npc.get("npc_id") or npc.get("name") or "").strip().lower().replace(" ", "_")
            override = inject_npc_schedule_overrides(session_id, npc_id, current_day, current_minute)
            if override and override.get("node_id"):
                return override["node_id"]
        except Exception:
            pass

    valid_blocks = (
        "morning", "lunch", "afternoon", "evening", "night",
        "commute", "class_afternoon", "extracurricular"
    )
    ts_low = str(time_slot or "").lower().strip()
    if ts_low in valid_blocks:
        block_key = ts_low
    else:
        block_key = get_detailed_npc_time_phase(current_minute, current_day=current_day, scen_key=scen_key)
    node_sched = get_npc_schedule_node_ids(
        npc, scen_key=scen_key, current_day=current_day, current_minute=current_minute, session_id=session_id
    )
    return node_sched.get(block_key, node_sched.get(get_time_block_key(current_minute), node_sched.get("morning", "loc_homeroom")))


def get_npc_schedule(
    npc: Dict[str, Any],
    scen_key: str = "fantasy",
    session_id: Optional[int] = None,
    current_day: int = 1,
    current_minute: Optional[int] = None,
) -> Dict[str, str]:
    """
    Deterministically computes a schedule dictionary mapping time blocks to tiered location names.
    Includes standard keys ('morning', 'lunch', 'afternoon', 'evening', 'night') and High School
    phase keys ('commute', 'class_afternoon', 'extracurricular').
    When session_id is provided, resolves canonical node_ids to personalized session place names.
    """
    if not isinstance(npc, dict):
        return {}

    name = str(npc.get("name") or "NPC").strip()
    basic = npc.get("basic_info") or {}
    role = str(npc.get("role") or basic.get("role") or npc.get("occupation") or "").lower()
    club = str(npc.get("club") or basic.get("club") or "").lower()
    primary_fac = str(npc.get("primary_facility") or basic.get("primary_facility") or basic.get("location") or "").strip()
    home_loc = str(npc.get("home_location") or basic.get("home_location") or "").strip()
    traits = npc.get("unlocked_traits") or npc.get("traits") or basic.get("traits") or []
    trait_names = [str(t.get("name") if isinstance(t, dict) else t).lower() for t in traits if t]

    seed_val = int(hashlib.md5(f"{name}_{role}_{club}".encode("utf-8")).hexdigest(), 16)
    is_school = is_high_school_setting(scen_key)
    weekend = is_weekend(current_day)

    node_sched = get_npc_schedule_node_ids(
        npc, scen_key=scen_key, current_day=current_day, current_minute=current_minute, session_id=session_id
    )
    schedule: Dict[str, str] = {}

    if is_school:
        if _is_town_citizen_or_youth_peer(npc):
            sec_fac = str(npc.get("secondary_facility") or basic.get("secondary_facility") or "").strip()
            for blk, nid in node_sched.items():
                if nid == str(npc.get("primary_node_id") or "") and primary_fac:
                    schedule[blk] = primary_fac
                elif nid == str(npc.get("secondary_node_id") or "") and sec_fac:
                    schedule[blk] = sec_fac
                elif nid in _HS_NODE_FALLBACK_PATHS:
                    schedule[blk] = _HS_NODE_FALLBACK_PATHS[nid]
                elif nid == "loc_downtown_office_away":
                    schedule[blk] = "Metropolitan Office District (Away on Workday Commute)"
                elif nid == "loc_rival_academy_away":
                    schedule[blk] = "Neighboring St. Jude's High School (In Class)"
                else:
                    schedule[blk] = home_loc or "Residential Neighborhood ➔ Private Residence"
        else:
            clique_low = str(npc.get("clique") or basic.get("clique") or "").strip().lower()
            _, club_path = _resolve_school_extracurricular_node(
                role, club, trait_names, seed_val, primary_fac=primary_fac, clique=clique_low
            )
            grade_low = str(npc.get("grade") or basic.get("grade") or "").strip().lower()
            is_faculty = grade_low == "faculty" or any(
                w in role for w in ("teacher", "staff", "principal", "counselor", "nurse", "librarian", "coach", "custodian", "chef", "dean")
            )
            _, student_cls_path = _resolve_student_classroom_node_and_path(npc, primary_fac=primary_fac)
            sec_fac = str(npc.get("secondary_facility") or basic.get("secondary_facility") or "").strip()

            for blk, nid in node_sched.items():
                if nid in ("loc_homeroom", "loc_freshman_class", "loc_sophomore_class", "loc_junior_class", "loc_senior_class"):
                    if not is_faculty and nid == "loc_homeroom" and "homeroom" in primary_fac.lower():
                        schedule[blk] = primary_fac
                    else:
                        schedule[blk] = _HS_NODE_FALLBACK_PATHS.get(nid, student_cls_path)
                elif nid in _HS_NODE_FALLBACK_PATHS:
                    fb_p = _HS_NODE_FALLBACK_PATHS[nid]
                    leaf_kw = fb_p.split(" ➔ ")[-1].lower()
                    if primary_fac and leaf_kw in primary_fac.lower():
                        schedule[blk] = primary_fac
                    elif sec_fac and leaf_kw in sec_fac.lower():
                        schedule[blk] = sec_fac
                    elif blk in ("extracurricular", "afternoon", "evening") and nid not in (
                        "loc_male_shower_room", "loc_female_shower_room", "loc_nsfw_faction_hq", "loc_school_infirmary"
                    ) and club_path and leaf_kw in club_path.lower():
                        schedule[blk] = club_path
                    else:
                        schedule[blk] = fb_p
                else:
                    schedule[blk] = home_loc or "Residential Neighborhood ➔ Residential Area"

    elif _is_anomalous_incursions_setting(scen_key):
        prof = _resolve_anomalous_npc_profile(npc, seed_val)
        p_path = prof["primary_path"]
        s_path = prof["secondary_path"]
        fac_id = prof["faction_id"]
        night_watch = is_npc_nocturnal_or_night_shift(npc, scen_key=scen_key, current_day=current_day)
        is_tp_hangout = str(prof["secondary_node_id"]).startswith("loc_tp_")

        if fac_id in ("cult_faction", "clandestine_faction"):
            day_cover_path = (
                "Uptown District ➔ Uptown Roastery & Rare Bookshop ➔ Leather-Armchair Rare Book Mezzanine"
                if is_tp_hangout
                else s_path
            )
            schedule["morning"] = day_cover_path if ((seed_val + current_day) % 2 == 0) else p_path
            schedule["lunch"] = day_cover_path
            schedule["afternoon"] = day_cover_path
            schedule["evening"] = p_path
            schedule["night"] = s_path if is_tp_hangout else p_path
        elif fac_id == "monastic_order":
            is_student_acolyte = (prof["secondary_node_id"] == "loc_school_rooftop")
            is_subway_monk = (prof["secondary_node_id"] == "sub_uc_brass_rotunda")
            schedule["morning"] = s_path if (is_student_acolyte and not weekend) else p_path
            schedule["lunch"] = s_path if (is_student_acolyte and not weekend) else "Woods & Mountain Reserve ➔ Eastern Grand Temple & Sanctuary ➔ Zen Rock Garden & Bamboo Tea House"
            schedule["afternoon"] = p_path if (not weekend or ((seed_val + current_day) % 2 == 0)) else s_path
            schedule["evening"] = p_path if (is_student_acolyte and not weekend) else s_path
            schedule["night"] = s_path if is_subway_monk else (p_path if night_watch else (home_loc or "Woods & Mountain Reserve ➔ Eastern Grand Temple & Sanctuary ➔ Sacred Mountain Hot Springs & Onsen Bathhouse"))
        else:
            on_weekend_duty = ((seed_val + current_day) % 2 == 0)
            field_patrol = (prof["agent_tier"] <= 2 and ((seed_val + current_day) % 2 == 0))
            schedule["morning"] = p_path if (not weekend or on_weekend_duty) else s_path
            schedule["lunch"] = p_path if (not weekend and seed_val % 2 == 0) else s_path
            schedule["afternoon"] = (s_path if field_patrol else p_path) if not weekend else (p_path if on_weekend_duty else s_path)
            schedule["evening"] = s_path
            schedule["night"] = p_path if night_watch else (home_loc or "Suburban Residential District ➔ Private Apartment")

    else:
        base_primary = primary_fac or "Adventurer's Guild ➔ Guild Hall"
        schedule["morning"] = base_primary

        lunch_opts = [
            "Local Tavern ➔ Common Room",
            "Market Square ➔ Open Plaza",
            base_primary,
        ]
        schedule["lunch"] = lunch_opts[seed_val % len(lunch_opts)]

        if any(w in role for w in ("guard", "knight", "soldier", "paladin")):
            schedule["afternoon"] = "Town Barracks ➔ Training Grounds"
        elif any(w in role for w in ("merchant", "shopkeeper", "vendor")):
            schedule["afternoon"] = "Market Square ➔ Trading Stall"
        elif any(w in role for w in ("scholar", "mage", "wizard", "alchemist")):
            schedule["afternoon"] = "Arcane Archives ➔ Study Alcove"
        else:
            afternoon_opts = [
                "Adventurer's Guild ➔ Quest Board",
                "Market Square ➔ Crafting District",
                base_primary,
            ]
            schedule["afternoon"] = afternoon_opts[seed_val % len(afternoon_opts)]

        schedule["evening"] = "Local Tavern ➔ Corner Booth"
        schedule["night"] = home_loc or "Tavern Inn ➔ Guest Quarters"

    # If session_id is provided, overlay resolved world_nodes paths
    if session_id:
        import db as local_db
        session_nodes = local_db.get_session_world_nodes(session_id)
        if session_nodes:
            node_map = {n["node_id"]: n for n in session_nodes}
            resolved_schedule: Dict[str, str] = {}
            for block, nid in node_sched.items():
                if nid in node_map:
                    n_obj = node_map[nid]
                    if n_obj.get("parent_id") and n_obj["parent_id"] in node_map:
                        parent_obj = node_map[n_obj["parent_id"]]
                        if parent_obj.get("parent_id") and parent_obj["parent_id"] in node_map:
                            grand_obj = node_map[parent_obj["parent_id"]]
                            resolved_schedule[block] = f"{grand_obj['name']} ➔ {parent_obj['name']} ➔ {n_obj['name']}"
                            continue
                        else:
                            resolved_schedule[block] = f"{parent_obj['name']} ➔ {n_obj['name']}"
                            continue
                    resolved_schedule[block] = n_obj["name"]
            if resolved_schedule:
                schedule.update(resolved_schedule)

    return schedule


def get_npc_scheduled_location(
    npc: Dict[str, Any],
    current_minute: int = 480,
    scen_key: str = "fantasy",
    time_slot: str = "",
    session_id: Optional[int] = None,
    current_day: int = 1
) -> str:
    """Returns the authoritative scheduled location for the given NPC at (current_minute, current_day) or time_slot."""
    if session_id:
        try:
            from mechanics.system.commitments_engine import inject_npc_schedule_overrides
            npc_id = str(npc.get("npc_id") or npc.get("name") or "").strip().lower().replace(" ", "_")
            override = inject_npc_schedule_overrides(session_id, npc_id, current_day, current_minute)
            if override and override.get("location"):
                return override["location"]
        except Exception:
            pass

    valid_blocks = (
        "morning", "lunch", "afternoon", "evening", "night",
        "commute", "class_afternoon", "extracurricular"
    )
    ts_low = str(time_slot or "").lower().strip()
    if ts_low in valid_blocks:
        block_key = ts_low
    else:
        block_key = get_detailed_npc_time_phase(current_minute, current_day=current_day, scen_key=scen_key)
    sched = get_npc_schedule(
        npc, scen_key=scen_key, session_id=session_id, current_day=current_day, current_minute=current_minute
    )
    return sched.get(block_key, sched.get(get_time_block_key(current_minute), sched.get("morning", "")))
