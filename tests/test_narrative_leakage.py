"""
tests/test_narrative_leakage.py — Unit tests for the Narrative Leakage Guard
=============================================================================
Tests cover:
  - Gold gain / gold loss detection from narrative prose
  - Non-combat damage detection (fail / crit_fail only)
  - Item grant detection with blocklist filtering
  - Combat passthrough (guard must not touch combat outcomes)
  - Zero-leakage passthrough (no prose, or prose with no transactions)
  - Character_outcomes entry creation when LLM omitted it entirely
  - Safety caps (MAX_GOLD_LEAKAGE_PATCH, damage sanity bounds)
"""
import sys
import os
import unittest
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Stub for CheckResult so we can fake check tiers without full skill_check import
# ---------------------------------------------------------------------------
@dataclass
class _FakeCheck:
    tier: str
    succeeded: bool = True


def _make_party(name: str = "Aria", hp: int = 50, gold: int = 100) -> list:
    char = {"name": name, "user_id": 1, "hp": hp, "max_hp": 100, "gold": gold}
    return [(char, {})]


def _make_action(tier: str = "success") -> dict:
    return {"label": "Do something", "check": _FakeCheck(tier=tier)}


# ---------------------------------------------------------------------------
# Patch game_engine.get_active_enemies to always return [] (non-combat default)
# ---------------------------------------------------------------------------
import game_engine as _ge_module  # noqa: E402  (needed for patch target)


class TestLeakageGuardGold(unittest.TestCase):
    """Gold gain and loss leakage detection."""

    def _run(self, outcome: dict, actions=None, party=None):
        from game_engine.state import reconcile_narrative_leakage
        party = party or _make_party()
        actions = actions or [_make_action("success")]
        with patch.object(_ge_module, "get_active_enemies", return_value=[]):
            return reconcile_narrative_leakage(outcome, party, actions)

    def test_gold_gain_patched(self):
        outcome = {
            "outcome_narrative": "The merchant rewards you with 50 gold for your troubles.",
            "character_outcomes": [],
        }
        result = self._run(outcome)
        co = result["character_outcomes"][0]
        self.assertEqual(co["gold_change"], 50)

    def test_gold_gain_variant_phrases(self):
        for phrase in [
            "You earned 200 gold.",
            "The chest contained 75 coins.",
            "You received 10 credits.",
            "She awarded you 30 gold for your service.",
        ]:
            outcome = {"outcome_narrative": phrase, "character_outcomes": []}
            result = self._run(outcome)
            co = result["character_outcomes"][0]
            self.assertGreater(co["gold_change"], 0, f"Should detect gold gain in: {phrase!r}")

    def test_gold_loss_patched(self):
        outcome = {
            "outcome_narrative": "You paid 20 gold to the innkeeper.",
            "character_outcomes": [],
        }
        result = self._run(outcome)
        co = result["character_outcomes"][0]
        self.assertEqual(co["gold_change"], -20)

    def test_gold_not_patched_when_already_set(self):
        """If character_outcomes already has a gold_change, the guard must not overwrite it."""
        outcome = {
            "outcome_narrative": "You received 100 gold.",
            "character_outcomes": [{"name": "Aria", "gold_change": 30, "hp_change": 0, "items_gained": []}],
        }
        result = self._run(outcome)
        co = result["character_outcomes"][0]
        self.assertEqual(co["gold_change"], 30, "Pre-set gold_change must not be overwritten")

    def test_gold_safety_cap(self):
        """Gold patch is capped at MAX_GOLD_LEAKAGE_PATCH."""
        outcome = {
            "outcome_narrative": "You found 99999 gold in the treasury.",
            "character_outcomes": [],
        }
        result = self._run(outcome)
        co = result["character_outcomes"][0]
        self.assertLessEqual(co["gold_change"], 5000, "Gold patch must be capped at MAX_GOLD_LEAKAGE_PATCH")

    def test_no_false_positive_on_year_numbers(self):
        """Prose like 'in 1050 BCE' must not be detected as gold."""
        outcome = {
            "outcome_narrative": "This artifact dates back to the year 1050.",
            "character_outcomes": [],
        }
        result = self._run(outcome)
        co = result["character_outcomes"][0]
        self.assertEqual(co["gold_change"], 0, "Year numbers must not trigger gold detection")


class TestLeakageGuardDamage(unittest.TestCase):
    """Non-combat damage leakage detection."""

    def _run(self, outcome, tier="fail", party=None):
        from game_engine.state import reconcile_narrative_leakage
        party = party or _make_party()
        actions = [_make_action(tier)]
        with patch.object(_ge_module, "get_active_enemies", return_value=[]):
            return reconcile_narrative_leakage(outcome, party, actions)

    def test_damage_patched_on_fail(self):
        outcome = {
            "outcome_narrative": "The trap triggers, dealing 15 damage to Aria.",
            "character_outcomes": [],
        }
        result = self._run(outcome, tier="fail")
        co = result["character_outcomes"][0]
        self.assertEqual(co["hp_change"], -15)

    def test_damage_patched_on_crit_fail(self):
        outcome = {
            "outcome_narrative": "Aria suffers 30 points of damage from the collapsing floor.",
            "character_outcomes": [],
        }
        result = self._run(outcome, tier="crit_fail")
        co = result["character_outcomes"][0]
        self.assertEqual(co["hp_change"], -30)

    def test_damage_not_patched_on_success(self):
        """On a successful action, damage prose must NOT be patched (could be enemy HP description)."""
        outcome = {
            "outcome_narrative": "Your blade deals 25 damage to the goblin.",
            "character_outcomes": [],
        }
        result = self._run(outcome, tier="success")
        co = result["character_outcomes"][0]
        self.assertEqual(co.get("hp_change", 0), 0, "Damage must not be patched on success tier")

    def test_damage_not_patched_when_already_set(self):
        outcome = {
            "outcome_narrative": "Aria takes 20 damage.",
            "character_outcomes": [{"name": "Aria", "hp_change": -5, "gold_change": 0, "items_gained": []}],
        }
        result = self._run(outcome, tier="fail")
        co = result["character_outcomes"][0]
        self.assertEqual(co["hp_change"], -5, "Pre-set hp_change must not be overwritten")

    def test_damage_sanity_bounds(self):
        """Values over 200 must be ignored (likely NPC stats or false positive)."""
        outcome = {
            "outcome_narrative": "The ancient dragon takes 999 damage from the spell.",
            "character_outcomes": [],
        }
        result = self._run(outcome, tier="fail")
        co = result["character_outcomes"][0]
        self.assertEqual(co.get("hp_change", 0), 0, "Damage > 200 must be filtered by sanity bounds")


class TestLeakageGuardItems(unittest.TestCase):
    """Item grant leakage detection."""

    def _run(self, outcome, party=None):
        from game_engine.state import reconcile_narrative_leakage
        party = party or _make_party()
        actions = [_make_action("success")]
        with patch.object(_ge_module, "get_active_enemies", return_value=[]):
            return reconcile_narrative_leakage(outcome, party, actions)

    def test_item_grant_detected(self):
        outcome = {
            "outcome_narrative": "The guard hands you a Silver Key.",
            "character_outcomes": [],
        }
        result = self._run(outcome)
        co = result["character_outcomes"][0]
        self.assertIn("Silver Key", co.get("items_gained", []))

    def test_item_not_duplicated_if_already_listed(self):
        outcome = {
            "outcome_narrative": "You received a Healing Potion.",
            "character_outcomes": [{"name": "Aria", "hp_change": 0, "gold_change": 0,
                                    "items_gained": ["Healing Potion"]}],
        }
        result = self._run(outcome)
        co = result["character_outcomes"][0]
        self.assertEqual(co["items_gained"].count("Healing Potion"), 1, "Duplicate item must not be added")

    def test_blocklist_words_not_added(self):
        """Common prose words in the blocklist must never be mistaken for items."""
        for word in ["moment", "chance", "breath", "step"]:
            outcome = {
                "outcome_narrative": f"She gives you a {word} to think.",
                "character_outcomes": [],
            }
            result = self._run(outcome)
            co = result["character_outcomes"][0]
            items = [i.lower() for i in co.get("items_gained", [])]
            self.assertNotIn(word.lower(), items, f"Blocklist word '{word}' must not become an item")


class TestLeakageGuardCombatPassthrough(unittest.TestCase):
    """During combat, the guard must be a no-op."""

    def test_combat_outcome_untouched(self):
        from game_engine.state import reconcile_narrative_leakage
        party = _make_party()
        actions = [_make_action("fail")]
        outcome = {
            "outcome_narrative": "You received 100 gold and took 50 damage.",
            "_combat_log": [{"msg": "combat"}],
            "character_outcomes": [],
        }
        # get_active_enemies must return something to trigger combat guard
        with patch.object(_ge_module, "get_active_enemies", return_value=[{"name": "Goblin"}]):
            result = reconcile_narrative_leakage(outcome, party, actions)

        co_list = result.get("character_outcomes", [])
        # Either empty or unchanged — the guard must not have created or patched any entry
        for co in co_list:
            self.assertEqual(co.get("gold_change", 0), 0, "Combat gold must not be patched by leakage guard")
            self.assertEqual(co.get("hp_change", 0), 0, "Combat damage must not be patched by leakage guard")


class TestLeakageGuardPassthrough(unittest.TestCase):
    """Edge cases: empty narrative, no party, etc."""

    def test_empty_narrative_is_noop(self):
        from game_engine.state import reconcile_narrative_leakage
        party = _make_party()
        outcome = {"character_outcomes": []}
        with patch.object(_ge_module, "get_active_enemies", return_value=[]):
            result = reconcile_narrative_leakage(outcome, party, [])
        # Should return outcome unchanged
        self.assertEqual(result.get("character_outcomes"), [])

    def test_empty_party_is_noop(self):
        from game_engine.state import reconcile_narrative_leakage
        outcome = {
            "outcome_narrative": "You received 50 gold.",
            "character_outcomes": [],
        }
        with patch.object(_ge_module, "get_active_enemies", return_value=[]):
            result = reconcile_narrative_leakage(outcome, [], [])
        # No party → can't determine acting character → no patch
        self.assertEqual(result["character_outcomes"], [])

    def test_new_co_entry_created_when_missing(self):
        """Guard must create a character_outcome entry when LLM omitted it entirely."""
        from game_engine.state import reconcile_narrative_leakage
        party = _make_party("Torvin")
        outcome = {
            "outcome_narrative": "Torvin received 40 gold from the bounty board.",
            "character_outcomes": [],  # LLM provided no entry at all
        }
        with patch.object(_ge_module, "get_active_enemies", return_value=[]):
            result = reconcile_narrative_leakage(outcome, party, [_make_action("success")])
        co_list = result.get("character_outcomes", [])
        self.assertTrue(len(co_list) > 0, "Guard must create a character_outcome entry if absent")
        co = co_list[0]
        self.assertEqual(co["gold_change"], 40)


if __name__ == "__main__":
    unittest.main()
