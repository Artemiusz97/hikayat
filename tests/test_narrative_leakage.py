"""
tests/test_narrative_leakage.py — Unit tests for Deterministic Pre-Turn Vitals & Resources Engine
================================================================================================
Replaces retired post-hoc narrative leakage regex scraper with deterministic pre-turn checks:
  - Gold spending deduction on successful check (ActionCommand.gold_spent)
  - Procedural loot roll when ActionCommand.triggers_loot_roll is set on success
  - Bounded hazard HP damage on failed STR/AGI/END physical checks in combat-capable scenarios
  - Complete suppression of hazard HP damage in non-combat/social scenarios
  - Combat turns bypass (combat is handled by precompute_combat_turn)
"""
import unittest
from skill_check import CheckResult
from game_engine.state.core import resolve_pre_turn_vitals_and_resources


class TestPreTurnVitalsAndResources(unittest.TestCase):
    def setUp(self):
        self.char = {
            "name": "Aria",
            "user_id": 1,
            "hp": 80,
            "max_hp": 100,
            "gold": 150,
            "level": 2
        }
        self.party = [self.char]
        self.session_fantasy = {"id": 1, "scenario": "fantasy", "nearby_enemies": []}
        self.session_school = {"id": 2, "scenario": "high_school", "nearby_enemies": []}

    def test_gold_spending_deducted_on_success(self):
        """ActionCommand.gold_spent is deducted deterministically when check succeeds."""
        action = {
            "char": self.char,
            "label": "Pay 50 gold to bribe the guard",
            "gold_spent": 50,
            "check": CheckResult(chance=80, roll=20, tier="success", tier_label="Success", succeeded=True, requirement=8)
        }
        res = resolve_pre_turn_vitals_and_resources(self.session_fantasy, self.party, [action])
        outcomes = res["character_outcomes"]
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["gold_change"], -50)
        self.assertTrue(any("spent 50 Gold" in d for d in res["stage_directives"]))

    def test_gold_spending_not_deducted_on_failure(self):
        """Gold is not deducted if the transaction check failed."""
        action = {
            "char": self.char,
            "label": "Attempt to purchase the contraband",
            "gold_spent": 40,
            "check": CheckResult(chance=40, roll=85, tier="fail", tier_label="Failure", succeeded=False, requirement=12)
        }
        res = resolve_pre_turn_vitals_and_resources(self.session_fantasy, self.party, [action])
        self.assertEqual(len(res["character_outcomes"]), 0)

    def test_procedural_loot_roll_on_success(self):
        """ActionCommand.triggers_loot_roll deterministically rolls consumable loot on success outside combat."""
        action = {
            "char": self.char,
            "label": "Rummage through the abandoned supply crates",
            "triggers_loot_roll": True,
            "stat": "PER",
            "check": CheckResult(chance=85, roll=15, tier="success", tier_label="Success", succeeded=True, requirement=7)
        }
        res = resolve_pre_turn_vitals_and_resources(self.session_fantasy, self.party, [action])
        outcomes = res["character_outcomes"]
        self.assertEqual(len(outcomes), 1)
        self.assertTrue(len(outcomes[0]["items_gained"]) > 0)
        self.assertTrue(len(res["loot_items_rolled"]) > 0)
        self.assertTrue(any("STAGE DIRECTION — LOOT DISCOVERED" in d for d in res["stage_directives"]))

    def test_physical_hazard_damage_on_failed_str_in_fantasy(self):
        """Failed physical STR checks in fantasy scenario apply bounded hazard damage (5% on fail, 10% on crit_fail)."""
        # Regular failure -> 5% of 100 max_hp = -5 HP
        action_fail = {
            "char": self.char,
            "label": "Try to force open the rusted iron portcullis",
            "stat": "STR",
            "check": CheckResult(chance=50, roll=70, tier="fail", tier_label="Failure", succeeded=False, requirement=10)
        }
        res_fail = resolve_pre_turn_vitals_and_resources(self.session_fantasy, self.party, [action_fail])
        self.assertEqual(res_fail["character_outcomes"][0]["hp_change"], -5)

        # Critical failure -> 10% of 100 max_hp = -10 HP
        action_crit_fail = {
            "char": self.char,
            "label": "Leap across the crumbling chasm",
            "stat": "AGI",
            "check": CheckResult(chance=30, roll=98, tier="crit_fail", tier_label="Critical Failure", succeeded=False, requirement=14)
        }
        res_crit = resolve_pre_turn_vitals_and_resources(self.session_fantasy, self.party, [action_crit_fail])
        self.assertEqual(res_crit["character_outcomes"][0]["hp_change"], -10)

    def test_hazard_damage_suppressed_in_non_combat_scenario(self):
        """Non-combat scenarios (e.g. high_school) must never deduct HP on failed checks."""
        action = {
            "char": self.char,
            "label": "Sprint down the stairs before class starts",
            "stat": "AGI",
            "check": CheckResult(chance=40, roll=80, tier="fail", tier_label="Failure", succeeded=False, requirement=10)
        }
        res = resolve_pre_turn_vitals_and_resources(self.session_school, self.party, [action])
        self.assertEqual(len(res["character_outcomes"]), 0)

    def test_hazard_damage_suppressed_on_social_and_cha_actions(self):
        """Social/conversational actions (CHA stat or dialogue intent) must never inflict physical hazard damage."""
        action = {
            "char": self.char,
            "label": "Attempt an intense standoff debate",
            "stat": "CHA",
            "intent": "dialogue",
            "check": CheckResult(chance=40, roll=80, tier="fail", tier_label="Failure", succeeded=False, requirement=10)
        }
        res = resolve_pre_turn_vitals_and_resources(self.session_fantasy, self.party, [action])
        self.assertEqual(len(res["character_outcomes"]), 0)

    def test_combat_turns_bypassed(self):
        """Active combat turns are bypassed by resolve_pre_turn_vitals_and_resources."""
        session_combat = {
            "id": 3,
            "scenario": "fantasy",
            "nearby_enemies": [{"name": "Goblin", "hp": 20}]
        }
        action = {
            "char": self.char,
            "label": "Swing axe",
            "gold_spent": 10,
            "check": CheckResult(chance=80, roll=10, tier="success", tier_label="Success", succeeded=True, requirement=8)
        }
        res = resolve_pre_turn_vitals_and_resources(session_combat, self.party, [action])
        self.assertEqual(len(res["character_outcomes"]), 0)


if __name__ == "__main__":
    unittest.main()
