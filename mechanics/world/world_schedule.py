"""
mechanics/world/world_schedule.py — World & Facility Operating Schedule Framework
=================================================================================
Manages time-of-day and day-of-week world schedules across all genres and scenarios,
with deep support for High School scenarios:

1. High School World Schedule:
   - Weekdays (Monday–Friday):
     * 07:00–08:00 (420..479): School area unrestricted (arrival & morning prep).
     * 08:00–15:00 (480..899): Class period (with 12:00–13:00 lunch break). All school
       facilities unlocked; students are FORBIDDEN from leaving school areas.
     * 15:00–20:00 (900..1199): Extracurricular period. Students can roam campus or leave.
       Sports facilities and club HQs are active; unused/hazardous rooms (Empty Classroom,
       School Rooftop, Chemical Storage Closet, and Staff Room after 17:00) are locked.
     * 20:00–07:00 (1200..1439, 0..419): Entire school area is restricted & locked.
       All students and teachers return home. Entering or staying on campus is TRESPASSING.
   - Special Condition — Abandoned School Building (`zone_abandoned_school`):
     * Always remains accessible 24/7 (nobody bothers to lock the doors or patrol it).
   - Weekends (Saturday–Sunday):
     * School is closed. Main Academic Wing and Cafeteria are locked.
     * Limited campus access (07:00–20:00): Sports facilities (`zone_school_athletics`),
       Club HQs (`zone_school_arts`), Courtyard, Main Gates, and Abandoned School are open
       for sports training and club meetings.
     * After 20:00 (20:00–07:00): All school access is restricted / trespassing (except
       the Abandoned School Building).
   - Other Areas (Commercial District, Parks, Residential, Seaside, etc.):
     * District/outdoor areas remain open 24/7.
     * Commercial venues (cafes, stores, restaurants, arcades, karaoke) operate
       08:00–22:00 (480..1320) every day, while the 24-Hour Convenience Store
       (`loc_convenience_store`) remains open 24/7.

2. Extensible Genre Framework:
   - Provides structured world schedule profiles for `high_school`, `slice_of_life`,
     `cyberpunk`, `sci_fi`, `steampunk`, `dark_fantasy`, `nuclear_post_apocalypse`,
     `isekai`, and `fantasy`, plus automatic fallback for any future genre/scenario.
"""
from __future__ import annotations
from typing import Dict, Any, Optional, Tuple


# Canonical scenario schedule profiles for all current and future genres
SCENARIO_WORLD_SCHEDULES: Dict[str, Dict[str, Any]] = {
    "high_school": {
        "genre_family": "high_school",
        "wake_minute": 420,          # 07:00 AM
        "sleep_minute": 1320,        # 10:00 PM (22:00)
        "sleep_end_minute": 420,     # 07:00 AM
        "commercial_open_min": 480,  # 08:00 AM
        "commercial_close_min": 1320,# 10:00 PM (22:00)
        "school_open_min": 420,      # 07:00 AM
        "class_start_min": 480,      # 08:00 AM
        "lunch_start_min": 720,      # 12:00 PM
        "lunch_end_min": 780,        # 01:00 PM (13:00)
        "class_end_min": 900,        # 03:00 PM (15:00)
        "extracurricular_end_min": 1200, # 08:00 PM (20:00)
    },
    "slice_of_life": {
        "genre_family": "slice_of_life",
        "wake_minute": 450,          # 07:30 AM
        "sleep_minute": 1320,        # 10:00 PM
        "sleep_end_minute": 360,     # 06:00 AM
        "commercial_open_min": 480,  # 08:00 AM
        "commercial_close_min": 1320,# 10:00 PM
    },
    "cyberpunk": {
        "genre_family": "cyberpunk",
        "wake_minute": 450,
        "sleep_minute": 1320,
        "sleep_end_minute": 360,
        "commercial_open_min": 0,    # 24/7 neon megacity markets & bars
        "commercial_close_min": 1440,
    },
    "sci_fi": {
        "genre_family": "sci_fi",
        "wake_minute": 450,
        "sleep_minute": 1320,
        "sleep_end_minute": 360,
        "commercial_open_min": 360,  # Station Alpha/Beta cycles
        "commercial_close_min": 1380,
    },
    "steampunk": {
        "genre_family": "steampunk",
        "wake_minute": 450,
        "sleep_minute": 1320,
        "sleep_end_minute": 360,
        "commercial_open_min": 480,
        "commercial_close_min": 1320,
    },
    "dark_fantasy": {
        "genre_family": "dark_fantasy",
        "wake_minute": 450,
        "sleep_minute": 1320,
        "sleep_end_minute": 360,
        "commercial_open_min": 480,
        "commercial_close_min": 1200, # Dusk curfew locking town gates
    },
    "nuclear_post_apocalypse": {
        "genre_family": "post_apocalypse",
        "wake_minute": 450,
        "sleep_minute": 1320,
        "sleep_end_minute": 360,
        "commercial_open_min": 420,
        "commercial_close_min": 1200, # Daylight trading before nocturnal radiation/raiders
    },
    "isekai": {
        "genre_family": "isekai",
        "wake_minute": 450,
        "sleep_minute": 1320,
        "sleep_end_minute": 360,
        "commercial_open_min": 480,
        "commercial_close_min": 1320,
    },
    "fantasy": {
        "genre_family": "fantasy",
        "wake_minute": 450,
        "sleep_minute": 1320,
        "sleep_end_minute": 360,
        "commercial_open_min": 480,
        "commercial_close_min": 1320,
    },
}


def is_weekend(current_day: int) -> bool:
    """
    Returns True if current_day falls on Saturday (Day 6, 13, ...) or Sunday (Day 7, 14, ...).
    Day 1 = Monday.
    """
    day_idx = max(0, int(current_day or 1) - 1) % 7
    return day_idx in (5, 6)


def get_day_type(current_day: int) -> str:
    """Returns 'weekend' for Saturday/Sunday, or 'weekday' for Monday–Friday."""
    return "weekend" if is_weekend(current_day) else "weekday"


def is_high_school_setting(scen_key: str) -> bool:
    """Checks if the scenario key or its genre tags belong to the High School genre."""
    s = str(scen_key or "").lower().strip()
    if any(k in s for k in ("high_school", "school", "academy")):
        return True
    try:
        from scenario_data import has_tag
        return bool(has_tag(s, "high_school") or has_tag(s, "high_school_drama"))
    except Exception:
        return False


def resolve_genre_schedule_key(scen_key: str = "fantasy") -> str:
    """Resolves any scenario key or custom tag combination to a canonical schedule profile key."""
    s = str(scen_key or "").lower().strip()
    if is_high_school_setting(s):
        return "high_school"
    if "slice_of_life" in s:
        return "slice_of_life"
    if "cyberpunk" in s or "cyber" in s:
        return "cyberpunk"
    if any(k in s for k in ("sci_fi", "scifi", "space")):
        return "sci_fi"
    if "steampunk" in s:
        return "steampunk"
    if "dark_fantasy" in s or "grimdark" in s:
        return "dark_fantasy"
    if "apocalypse" in s or "fallout" in s:
        return "nuclear_post_apocalypse"
    if "isekai" in s:
        return "isekai"
    return "fantasy"


def get_scenario_schedule_profile(scen_key: str = "fantasy") -> Dict[str, Any]:
    """Returns the world schedule configuration dictionary for a scenario."""
    key = resolve_genre_schedule_key(scen_key)
    return dict(SCENARIO_WORLD_SCHEDULES.get(key, SCENARIO_WORLD_SCHEDULES["fantasy"]))


def get_scenario_wake_minute(scen_key: str = "fantasy") -> int:
    """
    Returns the canonical morning wake-up minute for the scenario:
    - High School: 420 (07:00 AM) so player & NPCs can prepare for school.
    - Default / Other genres: 450 (07:30 AM).
    """
    profile = get_scenario_schedule_profile(scen_key)
    return int(profile.get("wake_minute", 450))


def get_scenario_sleep_minute(scen_key: str = "fantasy") -> int:
    """Returns the canonical bedtime start minute (default 1320 / 22:00 / 10:00 PM)."""
    profile = get_scenario_schedule_profile(scen_key)
    return int(profile.get("sleep_minute", 1320))


def is_abandoned_school_node(
    node: Optional[Dict[str, Any]] = None,
    parent_node: Optional[Dict[str, Any]] = None,
    location_str: str = ""
) -> bool:
    """
    Returns True if the node or location belongs to the Abandoned Old Campus Building zone
    (`zone_abandoned_school` and its child facilities/rooms).
    Per world schedule rules, nobody bothers to lock the doors or check this area,
    so it remains unrestricted and accessible 24/7.
    """
    parts = [str(location_str or "")]
    for n in (node, parent_node):
        if isinstance(n, dict):
            parts.append(str(n.get("node_id") or ""))
            parts.append(str(n.get("parent_id") or ""))
            parts.append(str(n.get("name") or ""))
    combined = " ".join(parts).lower()
    abandoned_markers = (
        "zone_abandoned_school",
        "abandoned old campus",
        "old showa campus",
        "derelict old campus",
        "decaying clock tower",
        "forgotten clock tower",
        "clock tower",
        "heritage wing",
        "showa campus",
        "loc_clock_tower",
        "loc_old_storage_3b",
        "old storage room 3-b",
        "storage room 3-b",
        "loc_derelict_gym",
        "derelict old gymnasium",
        "loc_old_infirmary",
        "boarded old infirmary",
        "loc_ruined_hallway",
        "overgrown hallway",
        "dark_equipment_room",
        "sub_dark_equipment_room",
    )
    return any(m in combined for m in abandoned_markers)


def is_campus_node_or_location(
    node: Optional[Dict[str, Any]] = None,
    parent_node: Optional[Dict[str, Any]] = None,
    location_str: str = "",
    session_id: int = 0,
    scen_key: str = "high_school_drama"
) -> bool:
    """
    Determines whether a node or tiered location string is part of the school campus.
    """
    if isinstance(node, dict) and str(node.get("category") or "").lower() == "academic":
        return True
    if isinstance(parent_node, dict) and str(parent_node.get("category") or "").lower() == "academic":
        return True

    parts = [str(location_str or "")]
    for n in (node, parent_node):
        if isinstance(n, dict):
            parts.append(str(n.get("node_id") or ""))
            parts.append(str(n.get("parent_id") or ""))
            parts.append(str(n.get("name") or ""))
    combined = " ".join(parts).lower()

    # Explicitly exclude residential & commercial off-campus markers
    if any(off in combined for off in (
        "zone_commercial", "zone_residential", "zone_seaside_bay", "zone_mountain_park",
        "loc_player_house", "sub_player_bedroom", "loc_cafe", "loc_arcade",
        "loc_convenience_store", "loc_bookstore", "loc_fashion_boutique",
        "loc_karaoke_box", "loc_ramen_shop", "loc_local_park"
    )):
        return False

    campus_markers = (
        "zone_school_main", "zone_school_commons", "zone_school_athletics",
        "zone_school_arts", "zone_abandoned_school",
        "academy", "school", "athletics", "commons", "annex", "academic wing",
        "science wing", "chemistry lab", "chemistry & science lab",
        "homeroom", "classroom", "staff room", "school library", "science lab",
        "school rooftop", "school main gates", "entrance foyer", "shoe lockers",
        "central courtyard", "campus dining hall", "vending machine pavilion",
        "botanical glasshouse", "main gymnasium", "athletic track", "swimming pool",
        "martial arts dojo", "behind gym", "student council", "auditorium",
        "music room", "fine arts studio", "broadcasting room", "clubroom",
        "abandoned old campus", "old storage room 3-b", "clock tower",
        "loc_homeroom", "loc_empty_class", "loc_staff_room", "loc_library",
        "loc_science_lab", "loc_rooftop", "loc_school_gate", "loc_entrance_foyer",
        "loc_courtyard", "loc_cafeteria", "loc_vending_pavilion", "loc_greenhouse",
        "loc_gymnasium", "loc_sports_field", "loc_pool", "loc_martial_arts_dojo",
        "loc_behind_gym_sheds", "loc_student_council", "loc_auditorium_stage",
        "loc_old_east_music_room", "loc_fine_arts_studio", "loc_broadcasting_room",
        "loc_clubroom_corridor",
    )
    if any(m in combined for m in campus_markers):
        return True

    if session_id and is_high_school_setting(scen_key):
        try:
            from mechanics.world.locations.seeds import (
                get_session_school_name,
                get_session_athletics_complex_name,
                get_session_student_commons_name,
                get_session_cultural_arts_name,
                get_session_abandoned_campus_name,
            )
            campus_zones = [
                get_session_school_name(session_id, scen_key),
                get_session_athletics_complex_name(session_id, scen_key),
                get_session_student_commons_name(session_id, scen_key),
                get_session_cultural_arts_name(session_id, scen_key),
                get_session_abandoned_campus_name(session_id, scen_key),
            ]
            for cz in campus_zones:
                if cz and cz.lower() in combined:
                    return True
        except Exception:
            pass

    return False


def get_world_schedule_state(
    scen_key: str = "fantasy",
    current_day: int = 1,
    current_minute: int = 480
) -> Dict[str, Any]:
    """
    Computes the active World Schedule state for any scenario, day, and minute.
    """
    safe_min = int(current_minute or 0) % 1440
    weekend = is_weekend(current_day)
    day_type = "weekend" if weekend else "weekday"
    profile = get_scenario_schedule_profile(scen_key)
    genre_family = profile["genre_family"]

    comm_open = int(profile.get("commercial_open_min", 480))
    comm_close = int(profile.get("commercial_close_min", 1320))
    commercial_venues_open = (comm_open <= safe_min < comm_close) if comm_open < comm_close else True

    if genre_family == "high_school":
        if not weekend:
            # MONDAY - FRIDAY
            if 420 <= safe_min < 480:
                period_key = "school_arrival_prep"
                period_label = "Morning Arrival & School Prep (07:00–08:00)"
                school_open = True
                school_status = "open_unrestricted"
                can_leave_campus = True
                is_trespassing = False
                narrative_directive = (
                    "School gates and facilities are open and unrestricted (07:00–08:00 AM). "
                    "Students and teachers are commuting to campus, changing shoes at the lockers, "
                    "and gathering in homerooms before the 08:00 AM first bell."
                )
            elif 480 <= safe_min < 900:
                is_lunch = (720 <= safe_min < 780)
                period_key = "class_hours_lunch" if is_lunch else "class_hours"
                period_label = (
                    "School Lunch Break (12:00–13:00 | Class Hours Lockdown 08:00–15:00)"
                    if is_lunch
                    else "Active Class Hours (08:00–15:00 | Leaving Campus Forbidden)"
                )
                school_open = True
                school_status = "in_session_lockdown"
                can_leave_campus = False
                is_trespassing = False
                if is_lunch:
                    narrative_directive = (
                        "School is in session for the midday Lunch Break (12:00–13:00). "
                        "Students stream out of classrooms to eat in the Cafeteria, Central Courtyard, "
                        "and Library. All school facilities are unlocked, but students remain forbidden "
                        "from leaving school grounds until 15:00 (3:00 PM)."
                    )
                else:
                    narrative_directive = (
                        "School is actively in session (08:00–15:00). All school facilities are unlocked. "
                        "Narrate students attending lectures, taking notes in classrooms, or moving between "
                        "periods when bells ring. Students are strictly FORBIDDEN from leaving the school "
                        "areas until 15:00 (3:00 PM)."
                    )
            elif 900 <= safe_min < 1200:
                period_key = "extracurricular_period"
                period_label = "After-School Extracurricular Period (15:00–20:00)"
                school_open = True
                school_status = "extracurricular_open"
                can_leave_campus = True
                is_trespassing = False
                narrative_directive = (
                    "It is the After-School Extracurricular Period (15:00–20:00). Students may freely "
                    "roam the school areas or leave campus. Club members gather in clubrooms (e.g., "
                    "Auditorium/Theater, Music Room, Fine Arts Studio, Student Council) and athletes train "
                    "at sports facilities, while unused rooms (Empty Classroom, School Rooftop, Chemical "
                    "Storage Closet, and Staff Room after 17:00) are locked."
                )
            else:
                # 20:00 - 07:00
                period_key = "after_hours_restricted"
                period_label = "After-Hours Campus Lockdown & Trespassing (20:00–07:00)"
                school_open = False
                school_status = "restricted_trespassing"
                can_leave_campus = True
                is_trespassing = True
                narrative_directive = (
                    "The entire school campus is CLOSED and RESTRICTED (20:00–07:00). All students and "
                    "teachers have returned home, and all school facilities are locked. Staying at or "
                    "entering the school during these hours is considered TRESPASSING (except the "
                    "Abandoned Old Campus Building, which remains unlocked and unpatrolled 24/7)."
                )
        else:
            # SATURDAY - SUNDAY (WEEKEND)
            if 420 <= safe_min < 1200:
                period_key = "weekend_daytime"
                period_label = "Weekend Limited Campus Access (07:00–20:00)"
                school_open = False
                school_status = "weekend_limited"
                can_leave_campus = True
                is_trespassing = False
                narrative_directive = (
                    "School is closed for the weekend (Saturday/Sunday). Almost all academic facilities "
                    "(Main Academic Wing and Cafeteria) are locked, but limited access to school areas "
                    "is permitted until 20:00: Sports Facilities and Club HQs are open for weekend "
                    "sports training and club meetings, while most students roam the town freely."
                )
            else:
                # 20:00 - 07:00 Weekend Night
                period_key = "after_hours_restricted"
                period_label = "Weekend Night Campus Lockdown & Trespassing (20:00–07:00)"
                school_open = False
                school_status = "restricted_trespassing"
                can_leave_campus = True
                is_trespassing = True
                narrative_directive = (
                    "It is after 20:00 (8:00 PM) on the weekend. All access to the school campus is "
                    "restricted and locked until 07:00 AM; being on campus is considered TRESPASSING "
                    "(except the Abandoned Old Campus Building, which remains unlocked 24/7)."
                )

        comm_status_note = (
            "Commercial shops, cafés, restaurants, and arcades are OPEN (08:00–22:00 daily)."
            if commercial_venues_open
            else "Commercial shops, cafés, restaurants, and arcades are CLOSED (open 08:00–22:00 daily; only outdoor streets/parks and the 24-Hour Convenience Store remain open)."
        )

        return {
            "genre_family": genre_family,
            "is_weekend": weekend,
            "day_type": day_type,
            "period_key": period_key,
            "period_label": period_label,
            "school_open": school_open,
            "school_status": school_status,
            "can_leave_campus": can_leave_campus,
            "is_trespassing_on_campus": is_trespassing,
            "commercial_venues_open": commercial_venues_open,
            "commercial_status_note": comm_status_note,
            "wake_minute": profile["wake_minute"],
            "sleep_minute": profile["sleep_minute"],
            "narrative_directive": f"{narrative_directive} {comm_status_note}",
        }

    # Non-school genres (Slice of Life, Cyberpunk, Sci-Fi, Steampunk, Fantasy, Isekai, Post-Apoc)
    if 420 <= safe_min < 1200:
        period_key = "weekend_daytime" if weekend else "daytime_operations"
        period_label = "Weekend Daytime Activity" if weekend else "Standard Daytime Operations"
        narrative_directive = (
            f"Daytime operations are active ({'Weekend' if weekend else 'Weekday'}). "
            f"{'Commercial venues and guild halls are open.' if commercial_venues_open else 'Early morning preparation before commercial venues open at 08:00.'}"
        )
    else:
        period_key = "night_operations"
        period_label = "Nighttime / After-Hours (20:00–07:00)"
        narrative_directive = (
            "Nighttime hours are in effect. "
            + ("24/7 neon nightlife and street markets remain active." if genre_family == "cyberpunk" else "Standard daytime shops are shuttered for the night (08:00–22:00 daily), while taverns, inns, and outdoor districts remain accessible.")
        )

    return {
        "genre_family": genre_family,
        "is_weekend": weekend,
        "day_type": day_type,
        "period_key": period_key,
        "period_label": period_label,
        "school_open": False,
        "school_status": "n/a",
        "can_leave_campus": True,
        "is_trespassing_on_campus": False,
        "commercial_venues_open": commercial_venues_open,
        "commercial_status_note": "Commercial venues open (08:00–22:00)." if commercial_venues_open else "Commercial venues closed (22:00–08:00).",
        "wake_minute": profile["wake_minute"],
        "sleep_minute": profile["sleep_minute"],
        "narrative_directive": narrative_directive,
    }


def evaluate_world_schedule_node_access(
    node: Dict[str, Any],
    parent_node: Optional[Dict[str, Any]] = None,
    scen_key: str = "high_school_drama",
    current_day: int = 1,
    current_minute: int = 480
) -> Dict[str, Any]:
    """
    Evaluates dynamic world-schedule facility locks for a node at (current_day, current_minute).
    Returns:
      - schedule_locked (bool)
      - is_trespassing (bool)
      - force_open (bool)
      - badge_override (str)
      - curfew_label (str)
      - reason_code (str)
      - reason_label (str)
    """
    if not isinstance(node, dict):
        return {"schedule_locked": False, "is_trespassing": False, "force_open": False}

    safe_min = int(current_minute or 0) % 1440
    weekend = is_weekend(current_day)
    n_id = str(node.get("node_id") or "").lower()
    n_name = str(node.get("name") or "").lower()
    n_type = str(node.get("node_type") or "").upper()
    n_cat = str(node.get("category") or "").lower()
    p_id = str((parent_node or {}).get("node_id") or node.get("parent_id") or "").lower()
    p_name = str((parent_node or {}).get("name") or "").lower()
    combined = f"{n_id} {n_name} {p_id} {p_name}"

    # 1. Special Rule: Abandoned School Building (`zone_abandoned_school`) is ALWAYS accessible 24/7
    if is_abandoned_school_node(node, parent_node):
        return {
            "schedule_locked": False,
            "is_trespassing": False,
            "force_open": True,
            "badge_override": "Open",
            "curfew_label": "",
            "reason_code": "",
            "reason_label": "",
        }

    # 2. District / Zone nodes remain open 24/7 (unless it's a school zone after 20:00)
    if n_type == "ZONE" and n_cat != "academic":
        return {"schedule_locked": False, "is_trespassing": False, "force_open": False}

    # 3. Commercial Venues: Cafes, stores, restaurants, arcades, karaoke open 08:00–22:00 every day
    if n_cat == "commercial":
        # 24-Hour Convenience Store and outdoor streets/plazas stay open 24/7
        is_24h_or_outdoor = any(k in combined for k in (
            "convenience_store", "convenience store", "24-hour", "24h",
            "street", "plaza", "avenue", "promenade", "alley", "district"
        )) and not any(v in combined for v in ("cafe", "café", "arcade", "bookstore", "boutique", "karaoke", "ramen", "restaurant"))
        if is_24h_or_outdoor:
            return {"schedule_locked": False, "is_trespassing": False, "force_open": True, "badge_override": "Open (24/7)"}

        # Standard commercial operating hours: 08:00 (480) to 22:00 (1320) every day
        profile = get_scenario_schedule_profile(scen_key)
        c_open = int(profile.get("commercial_open_min", 480))
        c_close = int(profile.get("commercial_close_min", 1320))
        if c_open < c_close and (safe_min < c_open or safe_min >= c_close):
            return {
                "schedule_locked": True,
                "is_trespassing": False,
                "force_open": False,
                "badge_override": "Closed (22:00–08:00)",
                "curfew_label": "22:00–08:00",
                "reason_code": "commercial_closed",
                "reason_label": "Commercial Venue Closed (Open 08:00–22:00 Daily)",
            }
        return {"schedule_locked": False, "is_trespassing": False, "force_open": False}

    # 4. High School Academic / Campus Facilities
    if n_cat == "academic" and is_high_school_setting(scen_key):
        # 4a. After-Hours Campus Lockdown & Trespassing: 20:00 (1200) to 07:00 (420) every day
        if safe_min >= 1200 or safe_min < 420:
            return {
                "schedule_locked": True,
                "is_trespassing": True,
                "force_open": False,
                "badge_override": "Curfew / Trespassing (20:00–07:00)",
                "curfew_label": "20:00–07:00",
                "reason_code": "curfew",
                "reason_label": "After-Hours Campus Lockdown & Trespassing (20:00–07:00)",
            }

        # 4b. Weekend Daytime (07:00–20:00 on Saturday & Sunday)
        if weekend:
            # Open on weekends: Sports Facilities, Club HQs / Cultural Arts, Courtyard, Main Gates
            weekend_open_markers = (
                "zone_school_athletics", "zone_school_arts",
                "loc_gymnasium", "main gymnasium", "basketball", "bleachers", "locker",
                "loc_sports_field", "athletic track", "stadium field", "running track", "dugout",
                "loc_pool", "swimming pool", "diving", "poolside",
                "loc_martial_arts_dojo", "martial arts dojo", "tatami", "shinai",
                "loc_behind_gym_sheds", "behind gym",
                "loc_student_council", "student council",
                "loc_auditorium_stage", "auditorium", "backstage",
                "loc_old_east_music_room", "music room", "piano",
                "loc_fine_arts_studio", "fine arts", "easel", "pottery",
                "loc_broadcasting_room", "broadcasting", "media",
                "loc_clubroom_corridor", "clubroom",
                "loc_school_gate", "school main gates", "front gate", "bike racks", "notice board",
                "loc_courtyard", "central courtyard", "fountain", "cherry tree",
                "loc_vending_pavilion", "vending machine",
                "loc_greenhouse", "botanical glasshouse", "greenhouse",
            )
            # Restricted sub-rooms inside club wing still keep their own lock (e.g. Council Archives & Safe)
            if any(r in combined for r in ("council_archives", "archive files & safe", "soundproof_closet")):
                return {"schedule_locked": False, "is_trespassing": False, "force_open": False}

            if any(m in combined for m in weekend_open_markers):
                return {"schedule_locked": False, "is_trespassing": False, "force_open": False}

            # All other school facilities (Main Academic Wing: Homeroom, Empty Classroom, Library,
            # Science Lab, Staff Room, Rooftop, Entrance Foyer, Hallways, and Cafeteria) are locked on weekends
            return {
                "schedule_locked": True,
                "is_trespassing": False,
                "force_open": False,
                "badge_override": "Locked (Weekend)",
                "curfew_label": "Weekend Closure",
                "reason_code": "weekend_closed",
                "reason_label": "School Closed for Weekend (Only Sports Facilities & Club HQs Open)",
            }

        # 4c. Weekday Extracurricular Period (15:00–20:00 on Monday–Friday)
        if 900 <= safe_min < 1200:
            # Unused/hazardous rooms locked during extracurriculars:
            # Empty Classroom, School Rooftop, Chemical Storage Closet, and Staff Room after 17:00 (1020)
            is_empty_class = any(k in combined for k in ("loc_empty_class", "empty classroom", "unused desks", "supply closet"))
            is_rooftop = any(k in combined for k in ("loc_rooftop", "school rooftop"))
            is_chem_closet = any(k in combined for k in ("chemical_closet", "chemical storage"))
            is_staff_room = any(k in combined for k in ("loc_staff_room", "staff room", "teachers' staff"))
            is_staff_late = is_staff_room and safe_min >= 1020

            if is_empty_class or is_rooftop or is_chem_closet or is_staff_late:
                return {
                    "schedule_locked": True,
                    "is_trespassing": False,
                    "force_open": False,
                    "badge_override": "Locked (After-School)",
                    "curfew_label": "15:00–07:00",
                    "reason_code": "restricted",
                    "reason_label": "Locked During Extracurricular Hours (15:00–20:00)",
                }

        # 4d. Weekday Open School Hours (07:00–15:00 on Monday–Friday):
        # General academic facilities and campus wings are unlocked, except inner security/restricted
        # rooms (Chemical Closet, Council Archives, Soundproof Closet, Staff Room, and locked School Rooftop).
        if 420 <= safe_min < 900:
            is_inner_restricted = any(k in combined for k in (
                "chemical_closet", "chemical storage",
                "council_archives", "archive files",
                "soundproof_closet",
                "loc_staff_room", "staff room", "teachers' staff", "teacher's desk", "print room",
                "loc_rooftop", "school rooftop",
            ))
            if not is_inner_restricted:
                return {
                    "schedule_locked": False,
                    "is_trespassing": False,
                    "force_open": True,
                    "badge_override": "Open",
                }

    return {"schedule_locked": False, "is_trespassing": False, "force_open": False}
