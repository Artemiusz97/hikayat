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


def _resolve_school_extracurricular_node(
    role: str,
    club: str,
    trait_names: List[str],
    seed_val: int
) -> Tuple[str, str]:
    """
    Resolves (node_id, fallback_tiered_path) for a High School NPC's club or sport
    during the 15:00–20:00 Extracurricular Period (and weekend club/sport sessions).
    """
    if "swim" in club:
        return "loc_pool", "School Grounds & Athletics ➔ Swimming Pool Facility"
    if any(c in club for c in ("kendo", "martial", "judo", "karate", "aikido", "fencing")):
        return "loc_martial_arts_dojo", "School Grounds & Athletics ➔ Martial Arts Dojo"
    if any(c in club for c in ("track", "soccer", "football", "baseball", "tennis", "running", "field")):
        return "loc_sports_field", "School Grounds & Athletics ➔ Athletic Track & Stadium Field"
    if any(c in club for c in ("gym", "basketball", "volleyball", "athletics", "sports", "badminton", "cheer")):
        return "loc_gymnasium", "School Grounds & Athletics ➔ Main Gymnasium"
    if any(c in club for c in ("drama", "theater", "theatre", "acting", "stage")):
        return "loc_auditorium_stage", "Cultural Arts & Student Union ➔ School Auditorium Stage"
    if any(c in club for c in ("art", "drawing", "sculpture", "painting", "manga", "photography")):
        return "loc_fine_arts_studio", "Cultural Arts & Student Union ➔ Fine Arts Studio"
    if any(c in club for c in ("music", "band", "orchestra", "choir", "jazz", "guitar", "piano")):
        return "loc_old_east_music_room", "Cultural Arts & Student Union ➔ Old East Wing Music Room"
    if any(c in club for c in ("science", "chem", "biology", "astronomy", "robotics", "physics")):
        return "loc_science_lab", "Main Academy Campus ➔ Chemistry & Science Lab"
    if any(c in club for c in ("council", "president", "treasurer", "vice president", "secretary")):
        return "loc_student_council", "Cultural Arts & Student Union ➔ Student Council Office"
    if any(c in club for c in ("library", "book", "lit", "poetry", "reading")):
        return "loc_library", "Main Academy Campus ➔ School Library"
    if any(c in club for c in ("broadcast", "newspaper", "media", "journalism", "radio", "press")):
        return "loc_broadcasting_room", "Cultural Arts & Student Union ➔ Campus Media & Broadcasting Room"
    if any(c in club for c in ("garden", "botany", "plant", "floral", "horticulture")):
        return "loc_greenhouse", "Student Commons & Central Plaza ➔ Botanical Glasshouse"
    if any(c in club for c in ("occult", "paranormal", "tarot", "mystery", "supernatural")):
        return "loc_old_storage_3b", "Abandoned Old Campus Building ➔ Old Storage Room 3-B"

    # Trait / Role fallbacks when no explicit club string is set
    if any(w in role for w in ("teacher", "staff", "principal", "counselor", "nurse")):
        return "loc_staff_room", "Main Academy Campus ➔ Teachers' Staff Room"
    if "librarian" in role:
        return "loc_library", "Main Academy Campus ➔ School Library"
    if any(t in trait_names for t in ("delinquent", "brawler", "rebel", "truant")) or "delinquent" in role:
        return "loc_behind_gym_sheds", "School Grounds & Athletics ➔ Behind Gym Storage Sheds"
    if any(t in trait_names for t in ("jock", "athletic", "sporty", "runner", "swimmer")) or any(w in role for w in ("jock", "athlete", "captain")):
        sport_opts = [
            ("loc_gymnasium", "School Grounds & Athletics ➔ Main Gymnasium"),
            ("loc_sports_field", "School Grounds & Athletics ➔ Athletic Track & Stadium Field"),
        ]
        return sport_opts[seed_val % len(sport_opts)]

    default_opts = [
        ("loc_library", "Main Academy Campus ➔ School Library ➔ Study Tables"),
        ("loc_courtyard", "Student Commons & Central Plaza ➔ Central Courtyard"),
        ("loc_vending_pavilion", "Student Commons & Central Plaza ➔ Vending Machine Pavilion"),
        ("loc_clubroom_corridor", "Cultural Arts & Student Union ➔ Student Clubroom Corridor"),
    ]
    return default_opts[seed_val % len(default_opts)]


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
    current_day: int = 1
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

    if is_school:
        club_node, _ = _resolve_school_extracurricular_node(role, club, trait_names, seed_val)
        is_faculty = any(w in role for w in ("teacher", "staff", "principal", "counselor", "nurse", "librarian"))

        if not weekend:
            # WEEKDAY SCHEDULE (Monday - Friday)
            # 0. Commute / Morning Prep (07:00 - 07:59)
            if is_faculty:
                schedule_nodes["commute"] = "loc_library" if "librarian" in role else "loc_staff_room"
            else:
                commute_opts = ["loc_school_gate", "loc_entrance_foyer", "loc_courtyard", "loc_homeroom"]
                schedule_nodes["commute"] = commute_opts[seed_val % len(commute_opts)]

            # 1. Morning Class Period (08:00 - 11:59)
            if "librarian" in role:
                schedule_nodes["morning"] = "loc_library"
            elif is_faculty:
                schedule_nodes["morning"] = "loc_staff_room"
            else:
                schedule_nodes["morning"] = "loc_homeroom"

            # 2. Lunch Break (12:00 - 12:59)
            if is_faculty:
                schedule_nodes["lunch"] = "loc_library" if "librarian" in role else "loc_staff_room"
            elif any(t in trait_names for t in ("introverted", "shy", "bookworm", "studious")):
                schedule_nodes["lunch"] = "loc_library"
            elif any(t in trait_names for t in ("athletic", "energetic", "outgoing")):
                schedule_nodes["lunch"] = "loc_courtyard"
            else:
                schedule_nodes["lunch"] = "loc_cafeteria"

            # 3. Afternoon Class Period (13:00 - 14:59): Students attend class & roam school area
            if "librarian" in role:
                schedule_nodes["class_afternoon"] = "loc_library"
            elif is_faculty:
                schedule_nodes["class_afternoon"] = "loc_staff_room"
            else:
                class_aft_opts = ["loc_homeroom", "loc_science_lab", "loc_library", "loc_courtyard"]
                schedule_nodes["class_afternoon"] = class_aft_opts[(seed_val >> 1) % len(class_aft_opts)]

            # 4. Extracurricular Period (15:00 - 19:59): Clubs & Sports Training
            schedule_nodes["extracurricular"] = club_node
            schedule_nodes["afternoon"] = club_node
            schedule_nodes["evening"] = club_node

            # 5. Night (20:00 - 06:59): Everyone returns home
            schedule_nodes["night"] = f"loc_{name_slug}_house"

        else:
            # WEEKEND SCHEDULE (Saturday - Sunday)
            # Students roam freely around the world, though some club/sport students train at school
            roam_morning = ["loc_cafe", "loc_local_park", "loc_coastal_pier", "loc_mountain_lake"]
            roam_lunch = ["loc_cafe", "loc_seaside_cafe", "loc_arcade", "loc_local_park"]
            roam_afternoon = [
                "loc_arcade", "loc_karaoke", "loc_local_park",
                "loc_sandy_beach", "loc_coastal_pier", "loc_summit_lookout", "loc_cafe"
            ]
            roam_evening = ["loc_karaoke", "loc_arcade", "loc_cafe", "loc_local_park", "loc_convenience_store"]

            has_club_sport = _has_active_club_or_sport(role, club, trait_names) and not is_faculty
            # Dedicated club/sport students spend part of the weekend training/meeting at school
            trains_on_weekend = has_club_sport and ((seed_val + current_day) % 2 == 0)

            schedule_nodes["commute"] = f"loc_{name_slug}_house" if (seed_val % 2 == 0) else roam_morning[seed_val % len(roam_morning)]
            schedule_nodes["morning"] = club_node if trains_on_weekend else roam_morning[seed_val % len(roam_morning)]
            schedule_nodes["lunch"] = roam_lunch[(seed_val >> 1) % len(roam_lunch)]
            schedule_nodes["class_afternoon"] = club_node if trains_on_weekend else roam_afternoon[(seed_val >> 2) % len(roam_afternoon)]
            schedule_nodes["extracurricular"] = club_node if trains_on_weekend else roam_afternoon[(seed_val >> 2) % len(roam_afternoon)]
            schedule_nodes["afternoon"] = schedule_nodes["extracurricular"]
            schedule_nodes["evening"] = roam_evening[(seed_val >> 3) % len(roam_evening)]
            schedule_nodes["night"] = f"loc_{name_slug}_house"

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
    node_sched = get_npc_schedule_node_ids(npc, scen_key=scen_key, current_day=current_day)
    return node_sched.get(block_key, node_sched.get(get_time_block_key(current_minute), node_sched.get("morning", "loc_homeroom")))


def get_npc_schedule(
    npc: Dict[str, Any],
    scen_key: str = "fantasy",
    session_id: Optional[int] = None,
    current_day: int = 1
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

    node_sched = get_npc_schedule_node_ids(npc, scen_key=scen_key, current_day=current_day)
    schedule: Dict[str, str] = {}

    if is_school:
        _, club_path = _resolve_school_extracurricular_node(role, club, trait_names, seed_val)
        is_faculty = any(w in role for w in ("teacher", "staff", "principal", "counselor", "nurse", "librarian"))
        base_primary = primary_fac or "Main Academy Campus ➔ Homeroom Classroom"

        if not weekend:
            # WEEKDAY (Monday - Friday)
            commute_paths = [
                "Main Academy Campus ➔ School Main Gates",
                "Main Academy Campus ➔ Entrance Foyer & Shoe Lockers",
                "Student Commons & Central Plaza ➔ Central Courtyard",
                base_primary,
            ]
            schedule["commute"] = (
                "Main Academy Campus ➔ Teachers' Staff Room"
                if is_faculty
                else commute_paths[seed_val % len(commute_paths)]
            )
            schedule["morning"] = (
                "Main Academy Campus ➔ School Library"
                if "librarian" in role
                else ("Main Academy Campus ➔ Teachers' Staff Room" if is_faculty else base_primary)
            )

            if is_faculty:
                schedule["lunch"] = "Main Academy Campus ➔ Teachers' Staff Room"
            elif any(t in trait_names for t in ("introverted", "shy", "bookworm", "studious")):
                schedule["lunch"] = "Main Academy Campus ➔ School Library ➔ Study Tables"
            elif any(t in trait_names for t in ("athletic", "energetic", "outgoing")):
                schedule["lunch"] = "Student Commons & Central Plaza ➔ Central Courtyard ➔ Courtyard Fountain"
            else:
                schedule["lunch"] = "Student Commons & Central Plaza ➔ Campus Dining Hall & Cafeteria"

            class_aft_paths = [
                base_primary,
                "Main Academy Campus ➔ Chemistry & Science Lab",
                "Main Academy Campus ➔ School Library",
                "Student Commons & Central Plaza ➔ Central Courtyard",
            ]
            schedule["class_afternoon"] = (
                "Main Academy Campus ➔ Teachers' Staff Room"
                if is_faculty
                else class_aft_paths[(seed_val >> 1) % len(class_aft_paths)]
            )
            schedule["extracurricular"] = club_path
            schedule["afternoon"] = club_path
            schedule["evening"] = club_path
            schedule["night"] = home_loc or "Residential Neighborhood ➔ Residential Area"
        else:
            # WEEKEND (Saturday - Sunday)
            roam_morning_paths = [
                "Commercial District ➔ Local Café",
                "Residential Neighborhood ➔ Neighborhood Park",
                "Seaside & Coastal Bay ➔ Boardwalk Pier & Lighthouse",
                "Recreational Mountain Park ➔ Mountain Lake Pier",
            ]
            roam_lunch_paths = [
                "Commercial District ➔ Local Café",
                "Seaside & Coastal Bay ➔ Seaside Beach Shack",
                "Commercial District ➔ Game Arcade",
                "Residential Neighborhood ➔ Neighborhood Park",
            ]
            roam_afternoon_paths = [
                "Commercial District ➔ Game Arcade",
                "Commercial District ➔ Karaoke Lounge",
                "Residential Neighborhood ➔ Neighborhood Park",
                "Seaside & Coastal Bay ➔ Sandy Beach & Coastline",
                "Seaside & Coastal Bay ➔ Boardwalk Pier & Lighthouse",
                "Recreational Mountain Park ➔ Mountain Summit Lookout",
                "Commercial District ➔ Local Café",
            ]
            roam_evening_paths = [
                "Commercial District ➔ Karaoke Lounge",
                "Commercial District ➔ Game Arcade",
                "Commercial District ➔ Local Café",
                "Residential Neighborhood ➔ Neighborhood Park",
                "Commercial District ➔ Convenience Store",
            ]
            has_club_sport = _has_active_club_or_sport(role, club, trait_names) and not is_faculty
            trains_on_weekend = has_club_sport and ((seed_val + current_day) % 2 == 0)

            schedule["commute"] = home_loc or roam_morning_paths[seed_val % len(roam_morning_paths)]
            schedule["morning"] = club_path if trains_on_weekend else roam_morning_paths[seed_val % len(roam_morning_paths)]
            schedule["lunch"] = roam_lunch_paths[(seed_val >> 1) % len(roam_lunch_paths)]
            schedule["class_afternoon"] = club_path if trains_on_weekend else roam_afternoon_paths[(seed_val >> 2) % len(roam_afternoon_paths)]
            schedule["extracurricular"] = schedule["class_afternoon"]
            schedule["afternoon"] = schedule["extracurricular"]
            schedule["evening"] = roam_evening_paths[(seed_val >> 3) % len(roam_evening_paths)]
            schedule["night"] = home_loc or "Residential Neighborhood ➔ Residential Area"

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
    sched = get_npc_schedule(npc, scen_key=scen_key, session_id=session_id, current_day=current_day)
    return sched.get(block_key, sched.get(get_time_block_key(current_minute), sched.get("morning", "")))
