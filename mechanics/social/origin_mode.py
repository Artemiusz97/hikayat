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


def resolve_authoritative_origin_session(
    session_or_id: Mapping[str, Any] | int | None,
    session_id: int = 0,
    scen_key: str = "",
) -> dict[str, Any]:
    """Resolve session dict for origin checks, falling back to `db.get_session()` when `origin_mode` is absent."""
    if isinstance(session_or_id, Mapping) and "origin_mode" in session_or_id:
        merged = dict(session_or_id)
        if scen_key and not merged.get("scenario"):
            merged["scenario"] = scen_key
        return merged
    sid = int(session_id or (session_or_id.get("id") if isinstance(session_or_id, Mapping) else 0) or 0)
    db_sess = _as_session(sid) if sid else {}
    merged = {**db_sess, **dict(session_or_id)} if isinstance(session_or_id, Mapping) else dict(db_sess)
    if scen_key and not merged.get("scenario"):
        merged["scenario"] = scen_key
    return merged


def is_adult_ahs_operative_fail_closed(
    session_or_id: Mapping[str, Any] | int | None,
    session_id: int = 0,
    scen_key: str = "",
) -> bool:
    """Return True ONLY when an authoritative Anomalous High session explicitly records `adult` origin."""
    sess = resolve_authoritative_origin_session(session_or_id, session_id=session_id, scen_key=scen_key)
    if not scenario_data.is_anomalous_high_school_scenario(str(sess.get("scenario") or "")):
        return False
    raw_mode = str(sess.get("origin_mode") or "").strip().lower()
    if not raw_mode:
        return False
    return normalize_origin_mode(raw_mode) == ORIGIN_ADULT


def resolve_player_age_profile(
    session: Mapping[str, Any] | int | None,
    char: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive the canonical player age bracket, origin mode, and UI badge from session + character.

    Rules:
    - Anomalous High: respects `session["origin_mode"]` (`"student"` vs `"adult"`), with legacy
      save fallback to `char["appearance"]["origin_mode"]` and `joined_faction_id == "student_freelancer"`
      before defaulting to `"adult"`.
    - Pure high school scenarios (`is_school_scenario`): always `"teen"` / `"student"`.
    - All other scenarios: always `"adult"` (never student).
    """
    sess = _as_session(session)
    char_dict = dict(char) if isinstance(char, Mapping) else {}
    scen_key = str(sess.get("scenario") or "")

    if scenario_data.is_anomalous_high_school_scenario(scen_key):
        raw_mode = str(sess.get("origin_mode") or "").strip().lower()
        app = char_dict.get("appearance")
        app_dict = app if isinstance(app, Mapping) else {}
        if not raw_mode:
            app_mode = str(app_dict.get("origin_mode") or "").strip().lower()
            if app_mode:
                raw_mode = app_mode
            elif (
                str(char_dict.get("joined_faction_id") or "").strip().lower() == STUDENT_FACTION_KEY
                or str(sess.get("joined_faction") or "").strip().lower() == STUDENT_FACTION_KEY
            ):
                raw_mode = ORIGIN_STUDENT
            else:
                raw_mode = ORIGIN_ADULT
        mode = normalize_origin_mode(raw_mode)
        if mode == ORIGIN_STUDENT:
            raw_grade = sess.get("student_grade") or app_dict.get("student_grade")
            grade = normalize_student_grade(raw_grade)
            return {
                "age_bracket": "teen",
                "age_tag": "Teen",
                "origin_mode": ORIGIN_STUDENT,
                "is_student": True,
                "is_adult_field_agent": False,
                "student_grade": grade,
                "badge_label": "Teen • Student",
            }
        return {
            "age_bracket": "adult",
            "age_tag": "Adult",
            "origin_mode": ORIGIN_ADULT,
            "is_student": False,
            "is_adult_field_agent": True,
            "student_grade": None,
            "badge_label": "Adult • Field Agent",
        }

    if scenario_data.is_school_scenario(scen_key):
        app = char_dict.get("appearance")
        app_dict = app if isinstance(app, Mapping) else {}
        raw_grade = str(sess.get("student_grade") or app_dict.get("student_grade") or "").strip()
        grade = normalize_student_grade(raw_grade) if raw_grade else None
        return {
            "age_bracket": "teen",
            "age_tag": "Teen",
            "origin_mode": ORIGIN_STUDENT,
            "is_student": True,
            "is_adult_field_agent": False,
            "student_grade": grade,
            "badge_label": "Teen • Student",
        }

    return {
        "age_bracket": "adult",
        "age_tag": "Adult",
        "origin_mode": ORIGIN_ADULT,
        "is_student": False,
        "is_adult_field_agent": False,
        "student_grade": None,
        "badge_label": "Adult",
    }


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
