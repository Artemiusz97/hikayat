"""
tests/test_stealth_simulation.py
Automated Pytest Suite for Hikayat Stealth & Infiltration Simulation.

Tests:
1. Ghost profile covert infiltration batch run.
2. Heavy profile noise drag & combat transition verification.
3. Specialist distraction meter shed verification.
4. Deterministic seed replay consistency.
5. Invariant auditor detection of meter overflow/underflow.
6. Invariant auditor detection of formula math leaks in truth directives.
"""
import pytest
from tests.simulators.stealth import (
    StealthSimulator,
    StealthInvariantAuditor,
    StealthViolation,
    StealthActorAI
)
from mechanics.stealth.alert_tracker import ALERT_UNAWARE, ALERT_SUSPICIOUS, ALERT_SEARCHING, ALERT_DETECTED


@pytest.mark.unit
class TestStealthSimulation:

    def test_stealth_batch_ghost_profile(self):
        """Verify ghost profile maintains stealth across multi-scenario operations with zero violations."""
        sim = StealthSimulator(seed=101)
        report = sim.run_batch(
            count=10,
            scenario="cyberpunk",
            profile="ghost",
            party_range=(1, 1),
            fail_fast=True
        )
        assert report.total_missions == 10
        assert report.crashes == 0
        assert len(report.violations_by_category) == 0
        # Ghost profile should have low detection rate
        assert report.detected_count <= 2

    def test_stealth_heavy_profile_noise_and_combat_escalation(self):
        """Verify heavy profile (noisy plate armor) tests combat handoff when cover is blown."""
        sim = StealthSimulator(seed=202)
        report = sim.run_batch(
            count=10,
            scenario="fantasy",
            profile="heavy",
            party_range=(1, 3),
            fail_fast=True
        )
        assert report.total_missions == 10
        assert report.crashes == 0
        assert len(report.violations_by_category) == 0
        # Heavy noise will cause multiple combat handoffs
        assert report.combat_escalations >= 1

    def test_stealth_specialist_distraction_deployment(self):
        """Verify distraction specialist actively reduces alert meter and avoids crashes."""
        sim = StealthSimulator(seed=303)
        report = sim.run_batch(
            count=8,
            scenario="scifi",
            profile="specialist",
            party_range=(1, 2),
            fail_fast=True
        )
        assert report.total_missions == 8
        assert report.crashes == 0
        assert len(report.violations_by_category) == 0

    def test_reproduction_seed_consistency(self):
        """Verify identical seeds reproduce exact turn counts, final meters, and outcomes."""
        sim1 = StealthSimulator(seed=999)
        res1 = sim1.run_mission(mission_id=1, scenario="cyberpunk", profile="ghost", seed=424242)

        sim2 = StealthSimulator(seed=999)
        res2 = sim2.run_mission(mission_id=1, scenario="cyberpunk", profile="ghost", seed=424242)

        assert res1.total_turns == res2.total_turns
        assert res1.final_meter == res2.final_meter
        assert res1.final_stage == res2.final_stage
        assert res1.detected == res2.detected
        assert res1.trace_log == res2.trace_log

    def test_auditor_catches_illegal_meter_bounds(self):
        """Verify auditor catches meter overflow (>100) or underflow (<0)."""
        auditor = StealthInvariantAuditor(scenario="cyberpunk")
        session = {"id": 1, "scenario": "cyberpunk"}

        # Meter > 100
        corrupt_state = {"detection_meter": 115, "alert_level": "detected", "is_hidden": False}
        violations = auditor.audit_turn(
            turn=1,
            session=session,
            stealth_state=corrupt_state,
            action={"label": "Sneak"},
            resolution={"trigger_combat": True}
        )
        assert any(v.category == "meter_overflow" for v in violations)

        # Meter < 0
        corrupt_state2 = {"detection_meter": -5, "alert_level": "unaware", "is_hidden": True}
        violations2 = auditor.audit_turn(
            turn=2,
            session=session,
            stealth_state=corrupt_state2,
            action={"label": "Wait"},
            resolution={"trigger_combat": False}
        )
        assert any(v.category == "meter_underflow" for v in violations2)

    def test_auditor_catches_directive_math_leak(self):
        """Verify auditor flags leaked formula tokens or dice notation in directives."""
        auditor = StealthInvariantAuditor(scenario="fantasy")
        session = {"id": 1, "scenario": "fantasy"}
        clean_state = {"detection_meter": 40, "alert_level": "suspicious", "is_hidden": True}

        leaked_resolution = {
            "directive": "Sentry is suspicious. Roll 1d20 against opposed_dc = 15.",
            "trigger_combat": False
        }
        violations = auditor.audit_turn(
            turn=1,
            session=session,
            stealth_state=clean_state,
            action={"label": "Sneak"},
            resolution=leaked_resolution
        )
        assert any(v.category == "directive_math_leak" for v in violations)
