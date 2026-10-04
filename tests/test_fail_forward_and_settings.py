import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import time
import discord

import character_data
import db
import game_engine
from cogs.adventure import _choice_button_label, ChoiceDropdown
from skill_check import CheckResult


class TestFailForwardAndSettings(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user_id = int(time.time() * 1000) % 1000000000 + 100000
        db.init_db()
        with db.get_conn() as conn:
            conn.execute("DELETE FROM user_settings WHERE user_id=?", (self.user_id,))

    def test_xp_rewards_fail_forward(self):
        """Verify that fail and crit_fail award meaningful XP under Fail-Forward."""
        self.assertEqual(character_data.XP_REWARDS["crit_success"], 25)
        self.assertEqual(character_data.XP_REWARDS["success"], 18)
        self.assertEqual(character_data.XP_REWARDS["fail"], 10)
        self.assertEqual(character_data.XP_REWARDS["crit_fail"], 15)

    def test_db_settings_show_percentages(self):
        """Verify show_percentages defaults to 1 and can be toggled to 0."""
        s = db.get_settings(self.user_id)
        self.assertEqual(s.get("show_percentages"), 1)

        db.update_settings(self.user_id, show_percentages=0)
        s2 = db.get_settings(self.user_id)
        self.assertEqual(s2.get("show_percentages"), 0)

        db.update_settings(self.user_id, show_percentages=1)
        s3 = db.get_settings(self.user_id)
        self.assertEqual(s3.get("show_percentages"), 1)

    def test_db_settings_with_active_session(self):
        """Verify update_settings / save_user_settings works when user has an active session."""
        db.create_character(self.user_id, "TestChar", "Warrior", "fantasy")
        sess_id = db.create_session(self.user_id, "solo", 1, "vivid", "balanced", False)
        
        # Should not raise sqlite3.OperationalError: no such column: show_percentages
        db.save_user_settings(self.user_id, image_gen_enabled=1, show_percentages=0)
        s = db.get_user_settings(self.user_id)
        sess = db.get_session(sess_id)
        self.assertEqual(s.get("image_gen_enabled"), 1)
        self.assertEqual(s.get("show_percentages"), 0)
        self.assertEqual(sess.get("image_gen_enabled"), 1)
        self.assertEqual(sess.get("show_percentages"), 0)

    def test_choice_button_label_percentages_toggle(self):
        """Verify _choice_button_label includes or strips percentage correctly."""
        choice_standard = {"label": "Search the archives for clues", "stat": "INT", "requirement": 5}
        choice_combat = {"label": "⚔️ STR 75% Strike with Broadsword against Goblin", "stat": "STR", "requirement": 4}

        # Standard choice: with prefix
        lbl_on = _choice_button_label(0, choice_standard, "100% ", show_percentages=True)
        self.assertTrue(lbl_on.startswith("100% "))
        self.assertIn("Search the archives", lbl_on)

        # Standard choice: without prefix
        lbl_off = _choice_button_label(0, choice_standard, "100% ", show_percentages=False)
        self.assertFalse(lbl_off.startswith("100% "))
        self.assertTrue(lbl_off.startswith("Search the archives"))

        # Combat pre-formatted choice: on
        c_on = _choice_button_label(0, choice_combat, "", show_percentages=True)
        self.assertIn("75%", c_on)

        # Combat pre-formatted choice: off
        c_off = _choice_button_label(0, choice_combat, "", show_percentages=False)
        self.assertNotIn("75%", c_off)
        self.assertIn("Strike with Broadsword", c_off)

    def test_choice_dropdown_percentages_toggle(self):
        """Verify ChoiceDropdown options have percentage when enabled and omit when disabled."""
        choices = [
            {"label": "Examine the glowing sigil on the wall", "stat": "INT", "requirement": 6},
            {"label": "⚔️ STR 60% Power slash against the automaton", "stat": "STR", "requirement": 5},
        ]
        actor_char = {
            "user_id": self.user_id, "name": "Aria", "char_class": "Mage",
            "int_": 6, "str_": 5, "agi": 5, "per_": 5, "end_": 5, "cha": 5, "luk": 3
        }

        # 1. Percentages ON
        db.update_settings(self.user_id, show_percentages=1)
        dropdown_on = ChoiceDropdown(cog=MagicMock(), session_id=0, choices=choices, actor_char=actor_char)
        opts_on = dropdown_on.options
        self.assertIn("%", opts_on[0].label)
        self.assertIn("%", opts_on[1].label)

        # 2. Percentages OFF
        db.update_settings(self.user_id, show_percentages=0)
        dropdown_off = ChoiceDropdown(cog=MagicMock(), session_id=0, choices=choices, actor_char=actor_char)
        opts_off = dropdown_off.options
        self.assertNotIn("%", opts_off[0].label)
        self.assertNotIn("%", opts_off[1].label)
        self.assertIn("Examine the glowing sigil", opts_off[0].label)
        self.assertIn("Power slash against the automaton", opts_off[1].label)

    @patch("game_engine.call_llm_json", new_callable=AsyncMock)
    async def test_resolve_turn_fail_forward_directives(self, mock_llm):
        """Verify that game_engine.resolve_turn passes Fail-Forward directives for failure tiers."""
        mock_llm.return_value = {
            "scene_title": "Aftermath",
            "outcome_narrative": "A dramatic complication arose.",
            "next_narrative": "Tension mounts as footsteps approach.",
            "next_choices": [{"label": "Flee", "stat": "AGI", "requirement": 5}]
        }

        session = {
            "id": 12345, "scenario": "fantasy", "history": [], "current_location": "Dungeon",
            "nearby_monsters": [], "current_npcs": [], "status": "active"
        }
        char_obj = {
            "user_id": self.user_id, "name": "Aria", "char_class": "Rogue", "race": "Human",
            "level": 1, "hp": 50, "max_hp": 50, "mp": 20, "max_mp": 20, "gold": 50,
            "str_": 5, "agi": 7, "per_": 6, "end_": 5, "int_": 5, "cha": 4, "luk": 3
        }
        party = [(char_obj, [])]

        actions = [
            {
                "char": char_obj,
                "label": "Pick the heavy iron lock",
                "mp_spent": 0,
                "check": CheckResult(chance=40, roll=60.0, tier="fail", tier_label="Failure", succeeded=False)
            }
        ]

        with patch("db.get_session_campaign_goals", return_value=[]), \
             patch("db.get_active_story_quest", return_value=None), \
             patch("db.get_session_quests", return_value=[]), \
             patch("db.get_session_chapter", return_value=1), \
             patch("game_engine.reconcile_movement_location", return_value="Dungeon"):
            res = await game_engine.resolve_turn(session, party, actions)

        # Inspect the user prompt sent to LLM
        call_args = mock_llm.call_args
        self.assertIsNotNone(call_args)
        user_prompt = call_args[0][1]
        self.assertIn("FAIL FORWARD", user_prompt)
        self.assertIn("Suffer a complication, escalation, or success-at-a-cost", user_prompt)


if __name__ == "__main__":
    unittest.main()
