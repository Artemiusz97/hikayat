import unittest
from unittest.mock import patch, AsyncMock
from dataclasses import dataclass

import game_engine
import character_data
import scenario_data
from game_engine.turn.prompts import _build_player_actions_text, _is_social_or_non_combat_action
from game_engine.state.reducers import _reduce_vitals_and_inventory
from skill_check import CheckResult


class TestSocialFailureAffinityAndVitalsGuard(unittest.IsolatedAsyncioTestCase):
    """Verifies that non-combat and social skill check failures never inflict HP damage,
    and are properly diverted to affinity penalties and social mood effects.
    """

    def setUp(self):
        self.char = {
            "id": 1,
            "user_id": 1001,
            "name": "Artemiusz",
            "hp": 300,
            "max_hp": 300,
            "mp": 50,
            "max_mp": 50,
            "gold": 100,
            "end_": 10,
            "status_effects": [],
        }
        self.party = [(self.char, [])]

    def test_reconcile_character_outcomes_non_combat(self):
        outcome = {"name": "Artemiusz", "hp_change": -12, "temp_hp_change": -12}
        # In non-combat, negative hp_change should be clamped to 0
        reconciled = character_data.reconcile_character_outcomes(self.char, outcome, is_non_combat=True)
        self.assertEqual(reconciled["actual_hp_delta"], 0)
        self.assertEqual(reconciled["new_hp"], 300)

        # In combat, negative hp_change should apply
        reconciled_combat = character_data.reconcile_character_outcomes(self.char, outcome, is_non_combat=False)
        self.assertEqual(reconciled_combat["actual_hp_delta"], -12)
        self.assertEqual(reconciled_combat["new_hp"], 288)

    def test_build_player_actions_text_directives(self):
        failed_check = CheckResult(
            chance=40, roll=60.0, tier="fail", tier_label="Failure", succeeded=False, requirement=6
        )
        action_social = {
            "char": self.char,
            "label": "Playfully challenge her about past experiences",
            "action_category": "dialogue",
            "mp_spent": 0,
            "stat": "CHA",
            "check": failed_check,
        }
        session_drama = {"id": 123, "scenario": "nsfw_high_school_drama"}
        
        # Social action in high school drama must NOT emit hazard math
        text_drama = _build_player_actions_text([action_social], session=session_drama)
        self.assertIn("NON-COMBAT / SOCIAL RULE", text_drama)
        self.assertIn("Do NOT inflict physical HP damage (hp_change MUST be 0)", text_drama)
        self.assertNotIn("[MANDATORY HAZARD MATH]", text_drama)

        # Hazard check in combat scenario DOES emit hazard math
        action_hazard = {
            "char": self.char,
            "label": "Disarm the explosive chest trap",
            "action_category": "action",
            "mp_spent": 0,
            "stat": "AGI",
            "check": failed_check,
        }
        session_fantasy = {"id": 124, "scenario": "fantasy"}
        text_hazard = _build_player_actions_text([action_hazard], session=session_fantasy)
        self.assertIn("[MANDATORY HAZARD MATH]", text_hazard)
        self.assertIn("MUST deal exactly 12 damage!", text_hazard)

    @patch("game_engine.call_llm_json", new_callable=AsyncMock)
    async def test_resolve_turn_suppresses_social_hp_loss_and_applies_affinity(self, mock_llm):
        """When LLM hallucinates -12 HP on a failed social check in dialogue, resolve_turn
        must zero out hp_change and penalize affinity with dialogue partner instead.
        """
        mock_llm.return_value = {
            "scene_title": "Awkward Silence",
            "outcome_narrative": "Your words hang awkwardly in the alcove.",
            "next_narrative": "She shifts her ledger uncomfortably.",
            "character_outcomes": [
                {
                    "name": "Artemiusz",
                    "hp_change": -12,
                    "temp_hp_change": -12,
                    "status_effects": ["Flustered"]
                }
            ],
            "relationship_updates": [
                {
                    "npc_name": "Mia Yamada",
                    "delta_score": 0,
                    "track": "platonic"
                }
            ],
            "next_choices": [{"label": "Change subject", "stat": "CHA", "requirement": 4}]
        }

        session = {
            "id": 999943,
            "scenario": "nsfw_high_school_drama",
            "history": [],
            "current_location": "Music Room ➔ Upright Piano Alcove",
            "dialogue_partner": "Mia Yamada",
            "current_npcs": [{"name": "Mia Yamada"}],
            "status": "active"
        }

        action = {
            "char": self.char,
            "label": "Playfully challenge her about past experiences",
            "action_category": "dialogue",
            "target_npc": "Mia Yamada",
            "mp_spent": 0,
            "stat": "CHA",
            "check": CheckResult(chance=83, roll=85.0, tier="fail", tier_label="Failure", succeeded=False, requirement=6)
        }

        with patch("db.get_session_campaign_goals", return_value=[]), \
             patch("db.get_active_story_quest", return_value=None), \
             patch("db.get_session_quests", return_value=[]), \
             patch("db.get_session_chapter", return_value=1), \
             patch("game_engine.reconcile_movement_location", return_value="Music Room ➔ Upright Piano Alcove"), \
             patch("game_engine.state.core.should_trigger_state_arbiter_pass", return_value=False), \
             patch("game_engine.state.core.should_trigger_social_arbiter_pass", return_value=False):
            outcome = await game_engine.resolve_turn(session, self.party, [action])

        # Verify HP loss was suppressed
        cos = outcome.get("character_outcomes") or []
        self.assertEqual(len(cos), 1)
        art_co = cos[0]
        self.assertEqual(art_co["hp_change"], 0, "HP loss must be suppressed to 0 in non-combat social turn")
        self.assertIn("Flustered", art_co["status_effects"])

        # Verify affinity was penalized instead
        rus = outcome.get("relationship_updates") or []
        self.assertEqual(len(rus), 1)
        mia_ru = rus[0]
        self.assertEqual(mia_ru["npc_name"], "Mia Yamada")
        self.assertEqual(mia_ru["delta_score"], -1, "Affinity must be penalized on failed check when HP was attempted")

    def test_reduce_vitals_non_combat_guard(self):
        """_reduce_vitals_and_inventory must never apply negative HP delta in non-combat scenario."""
        outcome = {
            "character_outcomes": [
                {
                    "name": "Artemiusz",
                    "hp_change": -12,
                    "temp_hp_change": -12,
                    "status_effects": ["Flustered"]
                }
            ]
        }
        session = {"id": 999943, "scenario": "nsfw_high_school_drama"}
        items_gained = {}

        with patch("db.apply_hp_mp_delta") as mock_apply_delta, \
             patch("db.set_status_effects"), \
             patch("db.apply_turn_regen"):
            _reduce_vitals_and_inventory(
                session_id=999943,
                session=session,
                party=self.party,
                outcome=outcome,
                mp_already_spent={},
                scen_key="nsfw_high_school_drama",
                is_combat=False,
                items_gained_by_user=items_gained
            )
            # user_id, hp_delta, mp_delta, gold_delta, temp_hp_delta
            mock_apply_delta.assert_called_once()
            args = mock_apply_delta.call_args[0]
            self.assertEqual(args[0], 1001) # user_id
            self.assertEqual(args[1], 0, "hp_delta passed to DB must be clamped to 0")
            self.assertEqual(args[4], 0, "temp_hp_delta passed to DB must be clamped to 0")


if __name__ == "__main__":
    unittest.main()
