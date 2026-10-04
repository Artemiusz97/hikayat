import unittest
from game_engine.state import is_check_success
from mechanics.system.memory.digest import should_trigger_digest
from mechanics.system.memory.budget import _classify_scene, SceneMode
from cogs.adventure.embeds import _get_choice_skill_emoji


class TestPhase5Hardening(unittest.TestCase):
    """Verifies Phase 5A (Sweeping Phase 1 & 2 Traps) and Phase 5B (Stat Checks & Intimacy Alignment)."""

    # --- Sub-Phase 5A Tests ---

    def test_digest_not_triggered_by_polite_thank_dialogue(self):
        """Verify should_trigger_digest does NOT fire on polite 'thank' dialogue choices."""
        session = {
            "history": ["t1", "t2", "t3"],
            "dialogue_partners": ["Elena"],
        }
        polite_actions = [{"label": "Thank Elena for the tea and ask about her studies"}]
        self.assertFalse(
            should_trigger_digest(session, polite_actions, {}),
            "Polite 'thank' dialogue should not prematurely trigger arc memory compression",
        )

        exit_actions = [{"label": "Say goodbye to Elena and leave the room"}]
        self.assertTrue(
            should_trigger_digest(session, exit_actions, {}),
            "Genuine conversational exit should trigger arc memory compression",
        )

    def test_digest_ignores_empty_json_dialogue_partners(self):
        """Verify '[]' in dialogue_partners is treated as empty and does not trigger exit digest."""
        session = {
            "history": ["t1", "t2", "t3"],
            "dialogue_partners": "[]",
            "dialogue_partner": "",
        }
        exit_actions = [{"label": "Say goodbye and step back"}]
        self.assertFalse(
            should_trigger_digest(session, exit_actions, {}),
            "Empty JSON array '[]' in dialogue_partners should evaluate to no active partner",
        )

    def test_embed_skill_emoji_for_polite_thank_is_not_door(self):
        """Verify Discord choice emoji for polite 'thank' conversation is 💬, not 🚪."""
        polite_choice = {
            "label": "Thank Elena for her guidance and ask about the ruins",
            "stat": "NONE",
            "requirement": 0,
        }
        self.assertEqual(_get_choice_skill_emoji(polite_choice), "💬")

        exit_choice = {
            "label": "Say goodbye to Elena and walk away",
            "stat": "NONE",
            "requirement": 0,
        }
        self.assertEqual(_get_choice_skill_emoji(exit_choice), "🚪")

    def test_budget_scene_mode_ignores_empty_json_dialogue_partners(self):
        """Verify _classify_scene returns EXPLORATION when dialogue_partners is '[]'."""
        session = {
            "scenario": "high_school",
            "dialogue_partners": "[]",
            "dialogue_partner": "",
        }
        mode = _classify_scene(session, None, [{"label": "Walk down the hallway"}])
        self.assertEqual(mode, SceneMode.EXPLORATION)

    # --- Sub-Phase 5B Tests ---

    def test_is_check_success_handles_all_formats_and_casings(self):
        """Verify canonical is_check_success handles None, objects, dicts, and mixed-case tiers."""
        # 1. None handling
        self.assertTrue(is_check_success(None, default_if_none=True))
        self.assertFalse(is_check_success(None, default_if_none=False))

        # 2. Object with succeeded / is_success attributes
        chk_obj_ok = type("Check", (), {"succeeded": True, "tier": "FAILURE"})()
        self.assertTrue(is_check_success(chk_obj_ok))

        chk_obj_fail = type("Check", (), {"is_success": False, "tier": "SUCCESS"})()
        self.assertFalse(is_check_success(chk_obj_fail))

        # 3. Object with only tier (uppercase and lowercase)
        for t in ("SUCCESS", "CRITICAL_SUCCESS", "PARTIAL_SUCCESS", "success", "crit_success", "partial_success"):
            obj = type("Check", (), {"tier": t})()
            self.assertTrue(is_check_success(obj), f"Expected True for tier={t}")

        for t in ("FAILURE", "FAIL", "CRITICAL_FAILURE", "CRIT_FAIL", "failure", "fail", "crit_fail"):
            obj = type("Check", (), {"tier": t})()
            self.assertFalse(is_check_success(obj), f"Expected False for tier={t}")

        # 4. Dictionary formats
        self.assertTrue(is_check_success({"tier": "SUCCESS"}))
        self.assertTrue(is_check_success({"tier": "crit_success"}))
        self.assertFalse(is_check_success({"tier": "FAILURE"}))
        self.assertFalse(is_check_success({"tier": "crit_fail"}))
        self.assertFalse(is_check_success({"is_success": False, "tier": "SUCCESS"}))
        self.assertTrue(is_check_success({"succeeded": True, "tier": "FAILURE"}))

    def test_budget_scene_mode_detects_central_intent_intimate_act(self):
        """Verify _classify_scene detects intimate acts via central intent engine."""
        session = {
            "scenario": "high_school",
            "dialogue_partners": ["Elena"],
        }
        # Action using vocabulary in central intent engine (e.g. 'fellatio' / 'blowjob')
        intimate_actions = [{"label": "Perform fellatio on him passionately"}]
        mode = _classify_scene(session, None, intimate_actions)
        self.assertEqual(mode, SceneMode.NSFW_INTIMATE)


if __name__ == "__main__":
    unittest.main()
