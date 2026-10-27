from __future__ import annotations
"""
tests/simulators/stealth/auditor.py
Zero-tolerance invariant auditor for Hikayat's Stealth & Infiltration mechanics.

Audits:
- Strict meter bounds: [0..100]
- Stage threshold correspondence (UNAWARE, SUSPICIOUS, SEARCHING, DETECTED)
- Natural decay monotonicity and non-negativity
- 100% alert cover-break and combat trigger parity
- Truth directive cleanliness (no raw math, DC values, or formula leaks)
- Noise penalty calculations and companion drag integrity
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from mechanics.stealth.alert_tracker import (
    ALERT_UNAWARE,
    ALERT_SUSPICIOUS,
    ALERT_SEARCHING,
    ALERT_DETECTED,
    get_alert_stage
)


@dataclass
class StealthViolation:
    """Telemetry for an invariant violation detected during stealth simulation."""
    turn: int
    category: str
    message: str
    context: Dict[str, Any] = field(default_factory=dict)


class StealthInvariantAuditor:
    """Audits turn-by-turn state transitions and invariants in stealth operations."""

    def __init__(self, scenario: str = "fantasy"):
        self.scenario = scenario
        self.violations: List[StealthViolation] = []
        self.previous_meter: Optional[int] = None
        self.previous_stage: Optional[str] = None
        self.previous_unpatrolled_turns: int = 0

    def audit_turn(
        self,
        turn: int,
        session: Dict[str, Any],
        stealth_state: Dict[str, Any],
        action: Dict[str, Any],
        resolution: Dict[str, Any],
        quiet_turn: bool = False
    ) -> List[StealthViolation]:
        """Audits all stealth state invariants for a single turn."""
        turn_violations: List[StealthViolation] = []

        meter = stealth_state.get("detection_meter")
        stage = stealth_state.get("alert_level")
        is_hidden = stealth_state.get("is_hidden")
        unpatrolled_turns = stealth_state.get("unpatrolled_turns", 0)

        # 1. Meter Numeric & Bound Invariants [0, 100]
        if meter is None or not isinstance(meter, (int, float)):
            turn_violations.append(StealthViolation(
                turn=turn,
                category="meter_type_invalid",
                message=f"Detection meter is non-numeric or None: {meter}",
                context={"stealth_state": stealth_state}
            ))
        else:
            if meter < 0:
                turn_violations.append(StealthViolation(
                    turn=turn,
                    category="meter_underflow",
                    message=f"Detection meter dropped below zero: {meter}",
                    context={"meter": meter}
                ))
            if meter > 100:
                turn_violations.append(StealthViolation(
                    turn=turn,
                    category="meter_overflow",
                    message=f"Detection meter exceeded 100: {meter}",
                    context={"meter": meter}
                ))

        # 2. Stage-to-Meter Mapping Correspondence
        if isinstance(meter, (int, float)):
            expected_stage = get_alert_stage(meter)
            if stage != expected_stage:
                turn_violations.append(StealthViolation(
                    turn=turn,
                    category="stage_meter_mismatch",
                    message=f"Alert stage '{stage}' does not correspond to meter {meter} (expected '{expected_stage}')",
                    context={"meter": meter, "actual_stage": stage, "expected_stage": expected_stage}
                ))

        # 3. 100% Detection Cover-Break Invariant
        if meter is not None and meter >= 100:
            if is_hidden:
                turn_violations.append(StealthViolation(
                    turn=turn,
                    category="detected_still_hidden",
                    message="Detection meter is 100% (DETECTED) but is_hidden remains True",
                    context={"meter": meter, "is_hidden": is_hidden}
                ))
            # Verify trigger_combat or trigger_confrontation is flagged
            if not resolution.get("trigger_combat") and not resolution.get("trigger_confrontation"):
                turn_violations.append(StealthViolation(
                    turn=turn,
                    category="detected_no_escalation",
                    message="Detection meter reached 100% but neither combat nor confrontation was triggered",
                    context={"resolution": resolution}
                ))

        # 4. Natural Decay Monotonicity
        if quiet_turn and self.previous_meter is not None and meter is not None:
            if self.previous_meter > 0 and meter > self.previous_meter:
                turn_violations.append(StealthViolation(
                    turn=turn,
                    category="decay_inversion",
                    message=f"Quiet turn resulted in meter increase: {self.previous_meter} -> {meter}",
                    context={"previous": self.previous_meter, "current": meter}
                ))

        # 5. Graduated Alert Invariant (< 100% failed roll must NOT break stealth stance)
        chk = resolution.get("check")
        chk_failed = bool(chk is not None and not getattr(chk, "succeeded", True))
        if chk_failed and isinstance(meter, (int, float)) and meter < 100:
            if not is_hidden:
                turn_violations.append(StealthViolation(
                    turn=turn,
                    category="premature_cover_break",
                    message=f"Failed stealth check at {meter}% (< 100%) prematurely broke stealth cover",
                    context={"meter": meter, "stage": stage}
                ))
            cast_plan = resolution.get("cast_plan")
            if isinstance(cast_plan, dict) and not cast_plan.get("stealth_active", True):
                turn_violations.append(StealthViolation(
                    turn=turn,
                    category="cast_planner_premature_reveal",
                    message=f"CastPlanner dropped stealth_active at {meter}% (< 100%)",
                    context={"meter": meter, "cast_plan": cast_plan}
                ))

        # 6. Truth Directive Cleanliness (Anti-Hallucination & Zero Stat Leakage)
        directive = resolution.get("directive", "")
        if directive:
            leak_patterns = [
                r"\b1d20\b",
                r"\bopposed_dc\b",
                r"\baction_noise\s*=",
                r"\bmargin\s*=",
                r"\bcalculate_opposed_stealth_odds\b",
                r"\b\d+\s*/\s*100\b",
                r"\b\d+%\b",
            ]
            for pat in leak_patterns:
                if re.search(pat, directive, re.IGNORECASE):
                    turn_violations.append(StealthViolation(
                        turn=turn,
                        category="directive_math_leak",
                        message=f"Stealth truth directive leaked raw math/numbers: pattern '{pat}' matched",
                        context={"directive": directive}
                    ))

        # 7. Companion Noise Drag & Backpack Unequipped Immunity Invariants
        odds = resolution.get("odds", {})
        if isinstance(odds, dict) and odds:
            comp_pen = odds.get("companion_noise_penalty", 0)
            if comp_pen < 0:
                turn_violations.append(StealthViolation(
                    turn=turn,
                    category="negative_companion_penalty",
                    message=f"Companion noise penalty is negative: {comp_pen}",
                    context={"odds": odds}
                ))
            if resolution.get("expect_zero_armor_noise") and odds.get("armor_noise", 0) > 0:
                turn_violations.append(StealthViolation(
                    turn=turn,
                    category="unequipped_backpack_armor_leak",
                    message=f"Unequipped backpack armor leaked armor_noise={odds.get('armor_noise')}",
                    context={"odds": odds}
                ))

        # 8. Serialization Safety Invariant (CheckResult JSON safety)
        if resolution.get("serialization_error"):
            turn_violations.append(StealthViolation(
                turn=turn,
                category="action_json_serialization_failure",
                message=f"_serializable_action failed json.dumps: {resolution['serialization_error']}",
                context={}
            ))

        self.previous_meter = meter
        self.previous_stage = stage
        self.previous_unpatrolled_turns = unpatrolled_turns
        self.violations.extend(turn_violations)
        return turn_violations
