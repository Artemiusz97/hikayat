"""
Shared canonical daily time-block constants and minute-to-phase helpers
used across both legacy schedules (`npc_schedule.py`) and anchor schedules (`anchor_schedule.py`).
"""
from __future__ import annotations

from typing import List, Tuple

from .world_schedule import is_high_school_setting, is_weekend

# Standard 5-block daily time blocks (minutes from midnight 0..1439)
SCHEDULE_TIME_BLOCKS: List[Tuple[int, int, str, str]] = [
    (360, 719, "morning", "Morning"),
    (720, 779, "lunch", "Lunch"),
    (780, 1019, "afternoon", "Afternoon"),
    (1020, 1199, "evening", "Evening"),
]
# Night covers 1200..1439 and 0..359

# Boundary minutes where schedule transitions occur
BLOCK_BOUNDARIES: List[Tuple[int, str]] = [
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
    scen_key: str = "high_school_drama",
) -> str:
    """
    Returns the granular High School schedule phase key for an NPC at (minute, current_day):
      - 'night': 20:00-06:59 (1200..1439 and 0..419)
      - 'commute': 07:00-07:59 (420..479)
      - 'morning': 08:00-11:59 (480..719)
      - 'lunch': 12:00-12:59 (720..779)
      - 'class_afternoon': 13:00-14:59 (780..899) on weekdays, or 'afternoon' on weekends
      - 'extracurricular': 15:00-19:59 (900..1199) on weekdays, or 'afternoon'/'evening' on weekends
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
    if 780 <= safe_min < 900:
        return "class_afternoon"
    return "extracurricular"
