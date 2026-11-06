from __future__ import annotations

"""
Player origin mode for the Anomalous High hybrid scenario (Adult Special Agent vs.
High School Student Operative).

Single source of truth: the session's `extra_json` keys `origin_mode` and
`student_grade` (merged into `db.get_session()` dicts and persisted through
save slots). Every subsystem must read the origin through these helpers rather
than re-deriving it from class names or factions.
"""

from typing import Any, Mapping

import db
import scenario_data

ORIGIN_ADULT = "adult"
ORIGIN_STUDENT = "student"
ORIGIN_MODES = (ORIGIN_ADULT, ORIGIN_STUDENT)

STUDENT_FACTION_KEY = "student_freelancer"
STUDENT_GRADES = ("Freshman", "Sophomore", "Junior", "Senior")
DEFAULT_STUDENT_GRADE = "Sophomore"

SCHOOL_DAY_START_MINUTE = 8 * 60       # 08:00
SCHOOL_DAY_END_MINUTE = 15 * 60        # 15:00 (exclusive)
AFTER_HOURS_START_MINUTE = 20 * 60     # 20:00
AFTER_HOURS_END_MINUTE = 6 * 60        # 06:00 (exclusive)

STUDENT_DAILY_ALLOWANCE_GOLD = 25


def normalize_origin_mode(value: Any) -> str:
    v = str(value or "").strip().lower()
    if v in ("student", "teen", "high_school_student", "student_operative", STUDENT_FACTION_KEY):
        return ORIGIN_STUDENT
    return ORIGIN_ADULT


def normalize_student_grade(value: Any) -> str:
    v = str(value or "").strip().lower()
    for g in STUDENT_GRADES:
        if v == g.lower() or v.startswith(g.lower()[:4]):
            return g
    return DEFAULT_STUDENT_GRADE


def _as_session(session_or_id: Mapping[str, Any] | int | None) -> dict:
    if isinstance(session_or_id, Mapping):
        return dict(session_or_id)
    if session_or_id:
        try:
            return db.get_session(int(session_or_id)) or {}
        except Exception:
            return {}
    return {}


def get_session_origin_mode(session_or_id: Mapping[str, Any] | int | None) -> str:
    """Returns 'student' or 'adult' for Anomalous High sessions, '' for every other scenario."""
    sess = _as_session(session_or_id)
    if not scenario_data.is_anomalous_high_school_scenario(str(sess.get("scenario") or "")):
        return ""
    return normalize_origin_mode(sess.get("origin_mode"))


def is_student_operative(session_or_id: Mapping[str, Any] | int | None) -> bool:
    return get_session_origin_mode(session_or_id) == ORIGIN_STUDENT


def is_adult_operative(session_or_id: Mapping[str, Any] | int | None) -> bool:
    return get_session_origin_mode(session_or_id) == ORIGIN_ADULT


def get_session_student_grade(session_or_id: Mapping[str, Any] | int | None) -> str:
    """Returns the student PC's grade, or '' when the PC is not a student operative."""
    sess = _as_session(session_or_id)
    if get_session_origin_mode(sess) != ORIGIN_STUDENT:
        return ""
    return normalize_student_grade(sess.get("student_grade"))


def set_session_origin(session_id: int, origin_mode: Any, student_grade: Any = None) -> dict:
    """Persists origin mode (and grade for students) into the session's extra_json."""
    mode = normalize_origin_mode(origin_mode)
    grade = normalize_student_grade(student_grade) if mode == ORIGIN_STUDENT else ""
    db.update_session(int(session_id), extra={"origin_mode": mode, "student_grade": grade})
    return {"origin_mode": mode, "student_grade": grade}


def resolve_starting_faction_for_origin(origin_mode: Any, requested_faction: Any) -> str:
    """Students never start in an agency; adults keep their requested agency (default public_agency)."""
    if normalize_origin_mode(origin_mode) == ORIGIN_STUDENT:
        return STUDENT_FACTION_KEY
    fac = str(requested_faction or "").strip()
    if not fac or fac == STUDENT_FACTION_KEY:
        return "public_agency"
    return fac


def is_weekday(current_day: int) -> bool:
    from mechanics.world.world_schedule import is_weekend
    return not is_weekend(int(current_day or 1))


def is_school_hours(current_day: int, current_minute: int) -> bool:
    """Weekday 08:00-15:00."""
    m = int(current_minute or 0) % 1440
    return is_weekday(current_day) and SCHOOL_DAY_START_MINUTE <= m < SCHOOL_DAY_END_MINUTE


def is_after_hours(current_minute: int) -> bool:
    """20:00-06:00 (school closed for the night), any day."""
    m = int(current_minute or 0) % 1440
    return m >= AFTER_HOURS_START_MINUTE or m < AFTER_HOURS_END_MINUTE


def session_clock(session: Mapping[str, Any] | None) -> tuple[int, int]:
    s = session or {}
    day = int(s.get("current_day") or s.get("in_game_day") or 1)
    minute = int(s.get("current_minute") if s.get("current_minute") is not None else 480)
    return day, minute
