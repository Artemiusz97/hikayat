"""
Core Stealth & Infiltration Lifecycle Manager.

Manages persistent session stealth states, executes covert turn actions,
handles stance toggling, breaks cover on loud events, and produces
anti-hallucination truth directives for narration.
"""
from typing import Dict, Any, Optional, List, Tuple
import copy

from mechanics.stealth.alert_tracker import (
    ALERT_UNAWARE,
    ALERT_SUSPICIOUS,
    ALERT_SEARCHING,
    ALERT_DETECTED,
    get_alert_stage,
    accumulate_detection,
    apply_natural_decay,
    apply_distraction,
    get_alert_badge_data
)
from mechanics.stealth.formulas import (
    calculate_opposed_stealth_odds,
    resolve_opposed_stealth_check,
    calculate_action_noise
)


def init_stealth_state(is_hidden: bool = True) -> Dict[str, Any]:
    """Creates a new canonical stealth_state dictionary."""
    return {
        "is_hidden": bool(is_hidden),
        "alert_level": ALERT_UNAWARE,
        "detection_meter": 0,
        "noise_level": 0,
        "last_alert_cause": None,
        "unpatrolled_turns": 0,
        "combat_vanished": False
    }


def get_session_stealth_state(session: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Retrieve or initialize the persistent stealth_state from a session."""
    if not isinstance(session, dict):
        return init_stealth_state(False)

    st = session.get("stealth_state")
    if not isinstance(st, dict):
        st = init_stealth_state(False)
        session["stealth_state"] = st
    return st


def set_session_stealth_state(session: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    """Update and persist the session's stealth_state."""
    if isinstance(session, dict):
        session["stealth_state"] = dict(state)
    return state


def toggle_stealth_stance(session: Dict[str, Any], active: bool) -> Dict[str, Any]:
    """
    Toggles the persistent covert stance ON or OFF.
    """
    st = get_session_stealth_state(session)
    st["is_hidden"] = bool(active)
    if not active:
        st["combat_vanished"] = False
        st["unpatrolled_turns"] = 0
    return set_session_stealth_state(session, st)


def break_stealth(session: Dict[str, Any], reason: str = "detected") -> Dict[str, Any]:
    """
    Breaks cover immediately (e.g. from 100% detection, loud gunshot, or shouting).
    """
    st = get_session_stealth_state(session)
    st["is_hidden"] = False
    st["combat_vanished"] = False
    st["last_alert_cause"] = str(reason)
    return set_session_stealth_state(session, st)


def apply_stealth_decay_turn(session: Dict[str, Any]) -> Dict[str, Any]:
    """
    Applies natural passive decay over a quiet turn.
    """
    st = get_session_stealth_state(session)
    if not st.get("is_hidden"):
        return st

    turns = st.get("unpatrolled_turns", 0) + 1
    st["unpatrolled_turns"] = turns

    new_meter, new_stage = apply_natural_decay(st.get("detection_meter", 0), quiet_turns=1)
    st["detection_meter"] = new_meter
    st["alert_level"] = new_stage
    return set_session_stealth_state(session, st)


def apply_stealth_distraction(session: Dict[str, Any], reduction: int = 30) -> Dict[str, Any]:
    """
    Applies an active distraction (e.g. throwing a stone) to shed detection.
    """
    st = get_session_stealth_state(session)
    new_meter, new_stage = apply_distraction(st.get("detection_meter", 0), reduction=reduction)
    st["detection_meter"] = new_meter
    st["alert_level"] = new_stage
    st["last_alert_cause"] = "distraction_deployed"
    return set_session_stealth_state(session, st)


def resolve_stealth_action(
    session: Dict[str, Any],
    actor_char: Dict[str, Any],
    action_data: Dict[str, Any],
    target_entity: Optional[Dict[str, Any]] = None,
    party: Optional[List[Any]] = None,
    equipped_items: Optional[List[Dict[str, Any]]] = None,
    current_minute: Optional[int] = None,
    environment: str = "",
    check_mode: str = "off"
) -> Dict[str, Any]:
    """
    Executes a covert action within a session, deterministically computing
    opposed check odds, resolving rolls, adjusting detection meter,
    and evaluating escalation.
    """
    st = get_session_stealth_state(session)
    actor_stats = actor_char.get("stats") or actor_char

    # Determine sentry perception
    target_per = 3
    if isinstance(target_entity, dict):
        t_stats = target_entity.get("stats") or target_entity
        target_per = int(t_stats.get("PER", t_stats.get("per", 3)) or 3)
    elif isinstance(session, dict):
        # Look for nearby enemies in session
        enemies = session.get("nearby_enemies") or session.get("monsters") or []
        if enemies and isinstance(enemies[0], dict):
            e_stats = enemies[0].get("stats") or enemies[0]
            target_per = int(e_stats.get("PER", e_stats.get("per", 3)) or 3)

    action_label = str(action_data.get("label") or action_data.get("custom_action_text") or "")
    action_noise = calculate_action_noise(action_data.get("action_type", ""), action_label)

    # Check for active invisibility buff
    status_effects = actor_char.get("status_effects") or []
    is_invisible = any("invisib" in str(eff).lower() or "optical_camo" in str(eff).lower() for eff in status_effects)

    current_stage = st.get("alert_level", ALERT_UNAWARE)
    luck = int(actor_stats.get("LUK", actor_stats.get("luk", 3)) or 3)

    check_res, odds = resolve_opposed_stealth_check(
        actor_stats=actor_stats,
        target_per=target_per,
        equipped_items=equipped_items,
        current_minute=current_minute,
        party=party,
        alert_stage=current_stage,
        is_invisible=is_invisible,
        environment=environment,
        action_noise=action_noise,
        luck=luck,
        check_mode=check_mode
    )

    # Accumulate detection
    new_meter, new_stage = accumulate_detection(
        current_meter=st.get("detection_meter", 0),
        check_tier=check_res.tier,
        margin=abs(odds["diff"]) if not check_res.succeeded else 0.0,
        action_noise=action_noise
    )

    st["detection_meter"] = new_meter
    st["alert_level"] = new_stage
    st["noise_level"] = action_noise

    trigger_combat = False
    trigger_confrontation = False

    # Check for 100% detection escalation
    if new_stage == ALERT_DETECTED or new_meter >= 100:
        st["is_hidden"] = False
        st["combat_vanished"] = False
        st["last_alert_cause"] = "detected_at_100_percent"

        from scenario_data import is_non_combat_scenario
        scen = session.get("scenario", "fantasy")
        if is_non_combat_scenario(scen) or scen in ("highschool", "slice_of_life"):
            trigger_confrontation = True
        else:
            trigger_combat = True

    set_session_stealth_state(session, st)

    badge = get_alert_badge_data(new_meter, is_hidden=st["is_hidden"])

    return {
        "check": check_res,
        "odds": odds,
        "stealth_state": dict(st),
        "alert_badge": badge,
        "trigger_combat": trigger_combat,
        "trigger_confrontation": trigger_confrontation,
        "directive": format_stealth_truth_directive(session, st)
    }


def format_stealth_truth_directive(session: Dict[str, Any], state: Optional[Dict[str, Any]] = None) -> str:
    """
    Synthesizes an immutable prompt directive enforcing covert rules for narration.
    """
    st = state or get_session_stealth_state(session)
    is_hidden = st.get("is_hidden", False)
    stage = st.get("alert_level", ALERT_UNAWARE).upper()
    meter = st.get("detection_meter", 0)

    if not is_hidden:
        if st.get("last_alert_cause"):
            return (
                f"\n[MANDATORY STEALTH DIRECTIVE]: Player cover has been BROKEN ({st['last_alert_cause']}). "
                f"Sentries or bystanders have spotted the party. Narrate immediate open confrontation, reaction, or inquiry.\n"
            )
        return ""

    if stage == "UNAWARE":
        stage_desc = "Sentries maintain relaxed, routine duties and have no suspicion."
    elif stage == "SUSPICIOUS":
        stage_desc = "A nearby guard heard a subtle sound or saw a shifting shadow and is pausing to inspect the area."
    elif stage == "SEARCHING":
        stage_desc = "Guards are actively searching with lanterns, weapons drawn, or sweeping scanners. Stealth is under intense pressure."
    else:
        stage_desc = "Guards are fully alerted and searching aggressively."

    return (
        f"\n[MANDATORY STEALTH & CONCEALMENT DIRECTIVE]:\n"
        f"- Covert Stance: ACTIVE (is_hidden = True).\n"
        f"- Detection Meter: {meter}/100 | Alert Stage: {stage}.\n"
        f"- Sentry Awareness: {stage_desc}\n"
        f"- TRUTH RULE: The player is remaining quiet and utilizing shadow/cover. "
        f"Do NOT narrate casual open conversation, walking in plain sight, or friendly daytime banter with sentries.\n"
    )
