from __future__ import annotations
"""
Stealth & Infiltration Alert Tracker.

Manages the 0-100 Detection Meter, discrete alert stages, accumulation on
failed checks, natural decay over unpatrolled turns, spatial transition resets,
and distraction reductions.
"""
from typing import Dict, Any, Tuple

# Alert Stages
ALERT_UNAWARE = "unaware"         # 0 - 25%: Sentries maintain routine patrol
ALERT_SUSPICIOUS = "suspicious"   # 26 - 60%: Guard halts, inspects noise/shadow
ALERT_SEARCHING = "searching"     # 61 - 99%: Active search with torches/scanners; DC +4
ALERT_DETECTED = "detected"       # 100%: Cover blown, alarm raised, combat/detention

STAGE_THRESHOLDS = (
    (ALERT_UNAWARE, 0, 25),
    (ALERT_SUSPICIOUS, 26, 60),
    (ALERT_SEARCHING, 61, 99),
    (ALERT_DETECTED, 100, 100),
)


def get_alert_stage(meter: int) -> str:
    """Return the canonical alert stage for a given detection meter value [0, 100]."""
    safe_val = max(0, min(100, int(meter or 0)))
    if safe_val >= 100:
        return ALERT_DETECTED
    if safe_val >= 61:
        return ALERT_SEARCHING
    if safe_val >= 26:
        return ALERT_SUSPICIOUS
    return ALERT_UNAWARE


def accumulate_detection(
    current_meter: int,
    check_tier: str,
    margin: float = 0.0,
    action_noise: int = 0
) -> Tuple[int, str]:
    """
    Deterministically update the detection meter after an opposed stealth roll.
    Returns (new_meter, new_stage).
    
    - crit_success: -5% (slips past cleanly, shakes off minor suspicion)
    - success: +0% (clean execution)
    - fail: +20% to +30% based on margin
    - crit_fail: +45% (stumble, loud noise, flash of visibility)
    - action_noise: adds extra immediate detection (e.g. unsuppressed weapons)
    """
    meter = max(0, min(100, int(current_meter or 0)))
    tier = str(check_tier or "").lower()

    delta = 0
    if tier == "crit_success":
        delta = -5
    elif tier == "success":
        delta = 0
    elif tier in ("fail", "failure"):
        delta = 25 + int(max(0, min(10, margin)))
    elif tier in ("crit_fail", "critical_failure"):
        delta = 45 + int(max(0, min(15, margin)))
    else:
        delta = 10

    # Add acoustic sound footprint from loud action
    delta += max(0, int(action_noise or 0))

    new_meter = max(0, min(100, meter + delta))
    return new_meter, get_alert_stage(new_meter)


def apply_natural_decay(current_meter: int, quiet_turns: int = 1, per_turn_decay: int = 10) -> Tuple[int, str]:
    """
    Passively reduce detection when the player stays still in cover
    or moves quietly through unpatrolled waypoints.
    Reduces detection by per_turn_decay (default 10%, or 15% when waiting still) per quiet turn.
    """
    meter = max(0, min(100, int(current_meter or 0)))
    turns = max(1, int(quiet_turns or 1))
    step = max(1, int(per_turn_decay or 10))
    decay_amount = step * turns
    new_meter = max(0, meter - decay_amount)
    return new_meter, get_alert_stage(new_meter)


def apply_spatial_transition_decay(current_meter: int, same_facility: bool = False) -> Tuple[int, str]:
    """
    Adjusts detection meter across spatial movement:
    - Leaving a facility/zone resets local sentry suspicion to 0%.
    - Moving to an adjacent room inside the same facility carries over half the meter.
    """
    meter = max(0, min(100, int(current_meter or 0)))
    if not same_facility:
        return 0, ALERT_UNAWARE
    halved = meter // 2
    return halved, get_alert_stage(halved)


def apply_distraction(current_meter: int, reduction: int = 30) -> Tuple[int, str]:
    """
    Actively reduce detection meter by creating a diversion (e.g. Throwing a stone).
    Lures sentries away and drops suspicion by reduction amount (default 30%).
    """
    meter = max(0, min(100, int(current_meter or 0)))
    red = max(1, int(reduction or 30))
    new_meter = max(0, meter - red)
    return new_meter, get_alert_stage(new_meter)


def get_alert_badge_data(meter: int, is_hidden: bool = True) -> Dict[str, Any]:
    """
    Telemetry payload for frontend UI badges (React Web UI & Discord Embeds).
    """
    stage = get_alert_stage(meter)
    safe_meter = max(0, min(100, int(meter or 0)))
    
    if not is_hidden:
        return {
            "stage": "revealed",
            "label": "REVEALED",
            "meter": safe_meter,
            "color": "#ef4444",       # Red
            "is_alerted": True,
            "badge_text": "REVEALED"
        }

    badge_map = {
        ALERT_UNAWARE: {
            "label": "HIDDEN",
            "color": "#8b5cf6",       # Violet
            "badge_text": f"HIDDEN {safe_meter}%" if safe_meter > 0 else "HIDDEN",
            "is_alerted": False
        },
        ALERT_SUSPICIOUS: {
            "label": "SUSPICIOUS",
            "color": "#eab308",       # Yellow
            "badge_text": f"SUSPICIOUS {safe_meter}%",
            "is_alerted": True
        },
        ALERT_SEARCHING: {
            "label": "SEARCHING",
            "color": "#f97316",       # Orange
            "badge_text": f"SEARCHING {safe_meter}%",
            "is_alerted": True
        },
        ALERT_DETECTED: {
            "label": "DETECTED",
            "color": "#dc2626",       # Bright Red
            "badge_text": "DETECTED 100%",
            "is_alerted": True
        }
    }
    info = badge_map.get(stage, badge_map[ALERT_UNAWARE])
    return {
        "stage": stage,
        "label": info["label"],
        "meter": safe_meter,
        "color": info["color"],
        "is_alerted": info["is_alerted"],
        "badge_text": info["badge_text"]
    }
