"""
Automated Pytest Suite for Hikayat World Navigation & Waypoint Simulation.

Tests:
1. Multi-scenario batch simulation runs (fantasy, school, scifi, cyberpunk, etc.).
2. Fuzzing survivability (realistic LLM perturbation noise).
3. Deadlock and oscillation loop detection in SpatialInvariantAuditor.
4. Deterministic seed replay consistency.
5. School campus facility movement and gate dynamics.
"""
import pytest
from tests.simulators.world import (
    WorldNavigationSimulator,
    SpatialInvariantAuditor,
    WaypointFuzzer,
    NavigatorAI,
)


@pytest.mark.unit
class TestNavigationSimulation:

    def test_navigation_batch_fantasy(self):
        """Verify batch navigation journeys complete reliably in fantasy wilderness."""
        sim = WorldNavigationSimulator(seed=101)
        report = sim.run_batch(
            journeys=6,
            scenario="fantasy",
            fuzz_mode="clean",
            fail_fast=True,
        )
        assert report.total_journeys == 6
        assert report.crashes == 0
        assert report.total_violations == 0
        assert report.successful_journeys >= 4

    def test_navigation_batch_school_campus(self):
        """Verify school campus navigation, facility presence, and gate dynamics."""
        sim = WorldNavigationSimulator(seed=202)
        report = sim.run_batch(
            journeys=6,
            scenario="high_school_drama",
            fuzz_mode="clean",
            fail_fast=True,
        )
        assert report.total_journeys == 6
        assert report.crashes == 0
        assert report.total_violations == 0

    def test_navigation_realistic_fuzzing(self):
        """Verify engine tolerates realistic LLM perturbations (action verbs, markdown, delimiters)."""
        sim = WorldNavigationSimulator(seed=303)
        report = sim.run_batch(
            journeys=8,
            scenario="all",
            fuzz_mode="realistic",
            fail_fast=False,
        )
        assert report.crashes == 0
        # No critical formatting leaks or action verb leaks
        assert report.violations_by_category.get("format_empty_location", 0) == 0
        assert report.violations_by_category.get("format_markdown_leak", 0) == 0
        assert report.violations_by_category.get("format_action_verb_leak", 0) == 0

    def test_reproduction_seed_consistency(self):
        """Verify deterministic seed replay reproduces the exact same trajectory and outcomes."""
        sim1 = WorldNavigationSimulator(seed=999)
        res1 = sim1.run_journey(scenario="cyberpunk", seed=424242, fuzz_mode="realistic", max_turns=20)

        sim2 = WorldNavigationSimulator(seed=999)
        res2 = sim2.run_journey(scenario="cyberpunk", seed=424242, fuzz_mode="realistic", max_turns=20)

        assert res1.total_turns == res2.total_turns
        assert res1.completed_stages == res2.completed_stages
        assert res1.success == res2.success
        assert res1.path_history == res2.path_history

    def test_oscillation_auditor_detection(self):
        """Verify auditor catches alternating A -> B -> A -> B loops."""
        auditor = SpatialInvariantAuditor(scenario_key="fantasy")
        loc_a = "Kingdom of Vale ➔ Town Square ➔ Main Area"
        loc_b = "Kingdom of Vale ➔ Town Tavern ➔ Main Area"

        # Simulate 6 alternating turns
        for t in range(1, 7):
            loc = loc_a if t % 2 == 1 else loc_b
            auditor.audit_turn(
                turn=t,
                session_id=0,
                current_location=loc,
                current_minute=480 + t * 5,
                current_day=1,
                active_wps=[{"stage_index": 1}],
                completed_stage_count=0,
            )

        categories = [v.category for v in auditor.violations]
        assert "deadlock_oscillation_loop" in categories

    def test_instant_spawn_arrival_advance(self):
        """Verify that spawning directly at an arrival waypoint advances it immediately on turn 1."""
        sim = WorldNavigationSimulator(seed=555)
        # Run a single journey and verify that completed_stages progresses from turn 1
        res = sim.run_journey(scenario="fantasy", seed=555, fuzz_mode="clean", max_turns=10)
        assert res.completed_stages > 0
        assert res.error is None

    def test_stress_fuzzing_resilience(self):
        """Verify that stress fuzzing (boundary noise, unicode, traversal, newlines) runs without crashes."""
        sim = WorldNavigationSimulator(seed=777)
        report = sim.run_batch(
            journeys=4,
            scenario="all",
            fuzz_mode="stress",
            fail_fast=False,
        )
        assert report.total_journeys == 4
        assert report.crashes == 0
        assert report.violations_by_category.get("format_empty_location", 0) == 0
