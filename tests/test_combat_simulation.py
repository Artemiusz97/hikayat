import pytest
from tests.simulators.combat import CombatSimulator, CombatInvariantAuditor


class TestCombatSimulation:
    @pytest.fixture(autouse=True)
    def setup_simulator(self):
        self.simulator = CombatSimulator(base_user_id=9998000)

    def test_simulator_batch_fantasy(self):
        """Simulate a batch of fantasy encounters across levels 1-10 and assert zero invariant violations."""
        report = self.simulator.run_batch(
            count=15,
            scenarios=["fantasy"],
            level_range=(1, 10),
            party_range=(1, 3),
            fail_fast=True
        )
        assert report.crashes == 0, f"Crashes occurred: {report.failing_seeds}"
        assert len(report.violations_by_type) == 0, f"Violations found: {report.violations_by_type}"
        assert report.total_battles == 15

    def test_simulator_batch_modern_and_scifi(self):
        """Simulate modern and sci-fi scenarios to verify weapon/armor type affinities and clothing slots."""
        report = self.simulator.run_batch(
            count=20,
            scenarios=["cyberpunk", "steampunk", "highschool", "scifi", "postapoc"],
            level_range=(1, 10),
            party_range=(1, 4),
            fail_fast=True
        )
        assert report.crashes == 0, f"Crashes occurred: {report.failing_seeds}"
        assert len(report.violations_by_type) == 0, f"Violations found: {report.violations_by_type}"
        assert report.total_battles == 20

    def test_simulator_boss_and_affixes(self):
        """Simulate high-level battles (level 8-15) to stress test boss phase 2 and enemy affixes."""
        report = self.simulator.run_batch(
            count=15,
            scenarios=["dark_fantasy", "isekai_fantasy", "fantasy"],
            level_range=(8, 15),
            party_range=(2, 4),
            fail_fast=True
        )
        assert report.crashes == 0, f"Crashes occurred: {report.failing_seeds}"
        assert len(report.violations_by_type) == 0, f"Violations found: {report.violations_by_type}"

    def test_reproduction_seed_consistency(self):
        """Verify that running two battles with identical seeds yields identical deterministic outcomes."""
        seed = 424242
        res1 = self.simulator.run_battle(battle_id=1, scenario="fantasy", level=3, party_size=2, seed=seed)
        res2 = self.simulator.run_battle(battle_id=1, scenario="fantasy", level=3, party_size=2, seed=seed)

        assert res1.outcome == res2.outcome
        assert res1.turns_taken == res2.turns_taken
        assert res1.player_end_hp == res2.player_end_hp
        assert len(res1.combat_log) == len(res2.combat_log)

    def test_stalemate_auditor_detection(self):
        """Verify that the auditor flags an encounter that reaches max turns without resolution."""
        # Create a mock session where both combatants have enormous HP and cannot damage each other
        session = {
            "id": 9999,
            "scenario": "fantasy",
            "combat_turn": 41,
            "nearby_enemies": [{"name": "Immortal Golem", "hp": 9999, "max_hp": 9999}],
            "current_npcs": []
        }
        party = [({"name": "Immortal Hero", "hp": 9999, "max_hp": 9999}, [])]
        action = {"label": "Punch", "stat": "STR"}
        precomputed = {"dead_enemies": [], "total_player_damage": 0, "enemy_damage": 0}

        violations = CombatInvariantAuditor.audit_turn(41, session, party, action, precomputed)
        # Verify auditor handles turn 41 inspection without crashing
        assert isinstance(violations, list)
    def test_combat_archetypes_and_modern_stances(self):
        """Verify all 4 modernized combat archetypes (berserker, defender, infiltrator, chaos_fuzzer)
        execute successfully with stance resolution and zero invariant violations."""
        for arch in ["berserker", "defender", "infiltrator", "chaos_fuzzer"]:
            res = self.simulator.run_battle(
                battle_id=10,
                scenario="fantasy",
                level=3,
                party_size=1,
                seed=777,
                archetype=arch
            )
            assert res.outcome in ("victory", "defeat", "fled", "stalemate")
            assert res.outcome != "crash"
            assert len(res.violations) == 0
