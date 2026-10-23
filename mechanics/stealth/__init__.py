"""
Hikayat Stealth Mechanics Package.
"""
from mechanics.stealth.alert_tracker import (
    ALERT_UNAWARE,
    ALERT_SUSPICIOUS,
    ALERT_SEARCHING,
    ALERT_DETECTED,
    STAGE_THRESHOLDS,
    get_alert_stage,
    accumulate_detection,
    apply_natural_decay,
    apply_distraction,
    get_alert_badge_data,
)
from mechanics.stealth.formulas import (
    calculate_armor_noise,
    calculate_companion_noise_penalty,
    calculate_lighting_modifier,
    calculate_action_noise,
    calculate_opposed_stealth_odds,
    resolve_opposed_stealth_check,
)
from mechanics.stealth.core import (
    init_stealth_state,
    get_session_stealth_state,
    set_session_stealth_state,
    toggle_stealth_stance,
    break_stealth,
    apply_stealth_decay_turn,
    apply_stealth_distraction,
    resolve_stealth_action,
    format_stealth_truth_directive,
)

__all__ = [
    "ALERT_UNAWARE",
    "ALERT_SUSPICIOUS",
    "ALERT_SEARCHING",
    "ALERT_DETECTED",
    "STAGE_THRESHOLDS",
    "get_alert_stage",
    "accumulate_detection",
    "apply_natural_decay",
    "apply_distraction",
    "get_alert_badge_data",
    "calculate_armor_noise",
    "calculate_companion_noise_penalty",
    "calculate_lighting_modifier",
    "calculate_action_noise",
    "calculate_opposed_stealth_odds",
    "resolve_opposed_stealth_check",
    "init_stealth_state",
    "get_session_stealth_state",
    "set_session_stealth_state",
    "toggle_stealth_stance",
    "break_stealth",
    "apply_stealth_decay_turn",
    "apply_stealth_distraction",
    "resolve_stealth_action",
    "format_stealth_truth_directive",
]
