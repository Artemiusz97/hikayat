from __future__ import annotations
"""
Time & Day/Night Engine for Hikayat.

Provides:
- 24-hour clock simulation (00:00 - 23:59) stored in minutes from midnight (0..1439).
- Weekday tracking (Monday - Sunday).
- Time-of-day phases (Dawn, Morning, Afternoon, Dusk, Night, Midnight) with emoji.
- Setting-aware travel and action time calculations (Modern vs Wilderness/Fantasy).
- Progressive multi-stage fatigue tracking for staying awake past dawn (05:00 AM).
- Bedtime & Sleep resolution (advances to 07:30 AM, restores HP/MP, clears fatigue, rolls Day +1).
- LLM prompt context formatting for narrative atmosphere and lighting.
"""
import json
import logging
from typing import Dict, Any, List, Optional, Tuple

import db

log = logging.getLogger("hikayat.time_engine")

DAYS_OF_WEEK = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

# Time of day phases mapped by minute from midnight (0..1439)
# Format: (start_minute, end_minute, phase_name, emoji, lighting_desc)
TIME_PHASES = [
    (300, 479, "Early Morning", "🌅", "Crisp dawn light, pale morning sky, cool morning air"),
    (480, 719, "Morning", "☀️", "Bright daylight, active morning bustle"),
    (720, 1019, "Afternoon", "☀️", "Warm sun, midday to late afternoon light"),
    (1020, 1199, "Evening", "🌇", "Golden hour dusk, long shadows, twilight glow"),
    (1200, 1439, "Night", "🌙", "Dark night sky, artificial lighting, moonlit atmosphere"),
    (0, 299, "Midnight", "🌌", "Dead of night, dim shadows, late-night stillness"),
]


def is_modern_setting(scen_key: str) -> bool:
    """Checks if scenario has modern/fast transit."""
    if not scen_key:
        return False
    s = str(scen_key).lower()
    return any(m in s for m in ["high_school", "school", "cyber", "scifi", "sci_fi", "modern"])


def format_clock(minute: int) -> str:
    """Formats minutes from midnight into 24-hour HH:MM format."""
    safe_min = int(minute or 0) % 1440
    hour = safe_min // 60
    rem_min = safe_min % 60
    return f"{hour:02d}:{rem_min:02d}"


def get_time_of_day_phase(minute: int) -> Tuple[str, str, str]:
    """Returns (phase_name, emoji, lighting_description) for the given minute."""
    safe_min = int(minute or 0) % 1440
    for start, end, name, emoji, lighting in TIME_PHASES:
        if start <= safe_min <= end:
            return name, emoji, lighting
    return "Day", "☀️", "Ambient light"


def get_day_of_week(current_day: int) -> str:
    """Returns standard weekday name for current_day (Day 1 = Monday)."""
    day_idx = max(0, int(current_day or 1) - 1) % len(DAYS_OF_WEEK)
    return DAYS_OF_WEEK[day_idx]


def format_time_header(current_day: int, current_minute: int) -> str:
    """Formats the time display for the adventure dashboard.
    Example: 📅 Monday | 🕒 08:30 (Morning ☀️)
    """
    day_name = get_day_of_week(current_day)
    clock_str = format_clock(current_minute)
    phase_name, emoji, _ = get_time_of_day_phase(current_minute)
    return f"📅 {day_name} | 🕒 {clock_str} ({phase_name} {emoji})"


def is_sleep_time(current_minute: int) -> bool:
    """Returns True if it is bedtime (>= 22:00 / 10:00 PM or < 06:00 / 06:00 AM)."""
    safe_min = int(current_minute or 0) % 1440
    return safe_min >= 1320 or safe_min < 360


def is_sleep_action(action_label: str) -> bool:
    """Checks if an action string represents sleeping / turning in for the night."""
    if not action_label:
        return False
    lbl = str(action_label).lower().strip()
    keywords = [
        "sleep until morning", "sleep through the night", "call it a night",
        "go to sleep", "head to sleep", "sleep in your bed", "sleep in bed",
        "turn in for the night", "rest until morning", "sleep until tomorrow",
        "[rest] sleep", "sleep until 7", "sleep until 07", "sleep until 8"
    ]
    return any(kw in lbl for kw in keywords)


def calculate_action_time_cost(
    action: dict | str,
    scen_key: str = "fantasy",
    old_loc: str = "",
    new_loc: str = "",
    is_dialogue: bool = False,
    is_combat: bool = False
) -> int:
    raw_lbl = action.get("label") if isinstance(action, dict) else action
    lbl = str(raw_lbl or "").lower().strip()
    
    # 1. Free / Ambient Actions (Observation, Redressing, Dropping burden)
    if isinstance(action, dict) and str(action.get("stat", "")).upper() == "FREE":
        return 0

    # 1.5 Sleep Action handled separately by apply_sleep_rest
    if is_sleep_action(lbl):
        return 0

    # 2. Combat Encounter turn
    if is_combat or any(kw in lbl for kw in ["attack", "strike", "cast ", "shoot", "defend", "brace", "dodge"]):
        return 5

    # 3. Location Travel & Movement
    try:
        if old_loc and new_loc and old_loc != new_loc:
            from mechanics.world.mobility import calculate_route_travel_time
            return calculate_route_travel_time(old_loc, new_loc, scen_key=scen_key)
    except Exception:
        pass

    # Check by action keywords if explicit travel was requested in action label
    travel_verbs = ["travel to", "travel toward", "head to", "head toward", "walk to", "journey to", "depart toward", "go to", "move to", "commute to"]
    if any(tv in lbl for tv in travel_verbs):
        is_modern = is_modern_setting(scen_key)
        if any(kw in lbl for kw in ["district", "downtown", "suburb", "city", "zone", "station", "valley", "mountains", "forest"]):
            return 25 if is_modern else 120
        return 5 if is_modern else 15

    # 4. Dialogue / Social Turn
    if is_dialogue or any(kw in lbl for kw in ["talk", "speak", "discuss", "chat", "ask", "inquire", "whisper", "comfort", "tease", "flirt", "confess"]):
        return 2

    # 5. Investigation / Search / Examination
    if any(kw in lbl for kw in ["search", "investigate", "inspect", "examine", "study", "read", "scavenge", "loot", "look around", "survey"]):
        return 10

    # 6. Default Exploration Action
    return 5


def advance_time(
    session_id: int,
    delta_minutes: int,
    party_uids: Optional[List[int]] = None
) -> Dict[str, Any]:
    """
    Advances session time by delta_minutes.
    Handles minute overflow, day incrementation, and character days_adventured tracking.
    Returns summary dict of state changes.
    """
    if delta_minutes <= 0:
        sess = db.get_session(session_id) or {}
        return {
            "session_id": session_id,
            "old_day": sess.get("current_day", 1),
            "new_day": sess.get("current_day", 1),
            "old_minute": sess.get("current_minute", 480),
            "new_minute": sess.get("current_minute", 480),
            "days_elapsed": 0,
            "minutes_elapsed": 0,
            "day_rolled_over": False,
            "fatigue_applied": []
        }

    curr_day, curr_min, consecutive_awake = db.get_session_time(session_id)
    total_minutes = curr_min + delta_minutes
    
    days_elapsed = total_minutes // 1440
    new_minute = total_minutes % 1440
    new_day = curr_day + days_elapsed
    day_rolled = days_elapsed > 0

    # Update database
    db.update_session_time(
        session_id=session_id,
        current_day=new_day,
        current_minute=new_minute,
        consecutive_days_awake=consecutive_awake + days_elapsed
    )

    # If day rolled over, increment days_adventured for all party members
    if day_rolled and party_uids:
        for uid in party_uids:
            try:
                db.increment_days_adventured(uid, delta=days_elapsed)
            except Exception as e:
                log.warning("Failed to increment days_adventured for user %s: %s", uid, e)

    # Check for fatigue escalation if crossing dawn (05:00 AM / minute 300) without sleeping
    fatigue_notices = []
    if (curr_min < 300 and new_minute >= 300) or days_elapsed > 0:
        fatigue_notices = check_and_apply_fatigue(session_id, party_uids or [])

    return {
        "session_id": session_id,
        "old_day": curr_day,
        "new_day": new_day,
        "old_minute": curr_min,
        "new_minute": new_minute,
        "days_elapsed": days_elapsed,
        "minutes_elapsed": delta_minutes,
        "day_rolled_over": day_rolled,
        "fatigue_applied": fatigue_notices
    }


def apply_sleep_rest(
    session_id: int,
    party_uids: List[int],
    wake_minute: int = 450
) -> Dict[str, Any]:
    """
    Executes a full night's sleep.
    - Advances clock to wake_minute (default 07:30 AM / 450 mins).
    - Advances current_day += 1.
    - Increments character days_adventured += 1.
    - Restores character HP to max_hp, MP to max_mp.
    - Clears all fatigue status effects ('Fatigued', 'Exhausted', 'Delirious').
    - Resets consecutive_days_awake to 0.
    """
    curr_day, curr_min, _ = db.get_session_time(session_id)
    
    # If sleeping before midnight (e.g. 22:00), sleep until next morning -> Day + 1
    # If sleeping in early morning after midnight (e.g. 02:00), wake at 07:30 same morning
    new_day = curr_day + 1 if curr_min >= 720 else curr_day
    new_minute = wake_minute  # 07:30 AM

    db.update_session_time(
        session_id=session_id,
        current_day=new_day,
        current_minute=new_minute,
        consecutive_days_awake=0
    )

    # Restock all merchant catalogues upon sleeping / morning wake-up
    try:
        session = db.get_session(session_id)
        if session and "merchant" in session:
            merchant = session["merchant"]
            if isinstance(merchant, dict):
                merchant["catalogues"] = {}
                merchant["stock"] = []
                db.save_merchant_state(session_id, merchant)
    except Exception as e:
        log.error("Failed to clear merchant catalogues on sleep for session %s: %s", session_id, e)

    fatigue_effects_cleared = []
    for uid in party_uids:
        try:
            char = db.get_character(uid)
            if not char:
                continue
            
            # 1. Restore HP/MP to full
            max_hp = char.get("max_hp", 100)
            max_mp = char.get("max_mp", 50)
            db.update_character_fields(uid, hp=max_hp, mp=max_mp)

            # 2. Increment days adventured
            db.increment_days_adventured(uid, delta=1)

            # 3. Clear fatigue status effects
            raw_status = char.get("status_effects") or "[]"
            status_list = []
            if isinstance(raw_status, str):
                try:
                    status_list = json.loads(raw_status)
                except Exception:
                    status_list = [raw_status]
            elif isinstance(raw_status, list):
                status_list = list(raw_status)

            fatigue_names = {"fatigued", "exhausted", "delirious", "sleep deprived"}
            filtered_status = []
            for s in status_list:
                s_str = (s.get("name", "") if isinstance(s, dict) else str(s)).strip()
                if s_str.lower() in fatigue_names:
                    fatigue_effects_cleared.append(s_str)
                else:
                    filtered_status.append(s_str)

            if len(filtered_status) != len(status_list):
                db.set_status_effects(uid, filtered_status)

        except Exception as e:
            log.error("Failed to apply sleep rest to user %s: %s", uid, e, exc_info=True)

    return {
        "session_id": session_id,
        "new_day": new_day,
        "new_minute": new_minute,
        "clock_display": format_clock(new_minute),
        "day_name": get_day_of_week(new_day),
        "fatigue_cleared": fatigue_effects_cleared,
        "hp_restored": True,
        "mp_restored": True
    }


def check_and_apply_fatigue(session_id: int, party_uids: List[int]) -> List[str]:
    """
    Checks if party members pulled an all-nighter past 05:00 AM and applies progressive fatigue.
    - Stage 1 (1 night missed): Fatigued (-1 PER, -1 AGI)
    - Stage 2 (2 nights missed): Exhausted (-2 PER, -2 AGI, -2 INT)
    - Stage 3 (3+ nights missed): Delirious (-3 all stats)
    """
    _, curr_min, consecutive_awake = db.get_session_time(session_id)
    if curr_min < 300 and consecutive_awake == 0:
        return []

    applied_notices = []
    
    stage = 1
    if consecutive_awake >= 2:
        stage = 3
    elif consecutive_awake == 1:
        stage = 2

    stage_tags = {
        1: "Fatigued",
        2: "Exhausted",
        3: "Delirious"
    }
    chosen_tag = stage_tags.get(stage, "Fatigued")

    for uid in party_uids:
        try:
            char = db.get_character(uid)
            if not char:
                continue
            
            raw_status = char.get("status_effects") or "[]"
            status_list = []
            if isinstance(raw_status, str):
                try:
                    status_list = json.loads(raw_status)
                except Exception:
                    status_list = [raw_status]
            elif isinstance(raw_status, list):
                status_list = list(raw_status)

            # Remove lower tier fatigue effects if upgrading
            fatigue_names = {"fatigued", "exhausted", "delirious", "sleep deprived"}
            filtered_status = [
                (s.get("name", "") if isinstance(s, dict) else str(s)).strip()
                for s in status_list
                if (s.get("name", "") if isinstance(s, dict) else str(s)).strip().lower() not in fatigue_names
            ]
            
            filtered_status.append(chosen_tag)
            db.set_status_effects(uid, filtered_status)
            applied_notices.append(f"{char['name']} is now **{chosen_tag}**")
        except Exception as e:
            log.warning("Failed to apply fatigue to user %s: %s", uid, e)

    return applied_notices


def format_llm_time_context(
    current_day: int,
    current_minute: int,
    scen_key: str = "fantasy"
) -> str:
    """
    Formats the time block for injection into the game engine's user_prompt.
    Provides clear context so the narrator renders accurate ambient lighting,
    crowd levels, shadows, and atmosphere.
    """
    day_name = get_day_of_week(current_day)
    clock_str = format_clock(current_minute)
    phase_name, emoji, lighting = get_time_of_day_phase(current_minute)
    
    context_lines = [
        f"IN-GAME TIME & ENVIRONMENT:",
        f"- Current Time: {day_name} (Day {current_day}), {clock_str} [{phase_name} {emoji}]",
        f"- Atmosphere & Lighting: {lighting}.",
    ]
    
    if is_sleep_time(current_minute):
        context_lines.append(
            f"- Late-Night Flavor: It is late evening / nighttime ({clock_str}). Most shops and facilities are closed, hallways/streets are quiet, and characters feel natural weariness if active."
        )
    else:
        context_lines.append(
            f"- Day Progression: Daytime activities, ambient NPCs, and normal operations are active."
        )

    return "\n".join(context_lines) + "\n"
