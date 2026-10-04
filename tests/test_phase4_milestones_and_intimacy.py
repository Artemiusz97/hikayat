import unittest
from game_engine.state import _evaluate_npc_milestones


class TestPhase4MilestonesAndIntimacy(unittest.TestCase):
    """Verifies Phase 4 Intimacy Milestone & Experience Tracking Streamlining."""

    def setUp(self):
        self.first_char = "Cid"
        self.npc_name = "Elena"

    def test_tier1_structured_intercourse_milestone(self):
        """Verify structured intercourse milestone properly updates status, memories, and reveal flags."""
        app_dict = {}
        (
            new_mem,
            intercourse,
            oral,
            manual,
            track,
            is_intimate,
            boost,
        ) = _evaluate_npc_milestones(
            npc_name=self.npc_name,
            app_dict=app_dict,
            track="romantic",
            milestone_ev="intercourse",
            custom_summary="An unforgettable night in the high tower.",
            intercourse_exp="virgin",
            oral_exp="inexperienced",
            actions=[],
            narrative_text="",
            overall_check_success=True,
            is_player_romantic_action=True,
            is_player_intimate_action=True,
            is_player_oral_action=False,
            is_player_intercourse_action=True,
            is_player_confession_action=False,
            is_player_affection_action=False,
            affection_target_npc=None,
            gift_target_npc=None,
            gift_item_name=None,
            confession_target_npc=None,
            first_char_name=self.first_char,
        )
        self.assertTrue(is_intimate)
        self.assertEqual(intercourse, "non_virgin")
        self.assertIn("night", new_mem.lower())
        # Check that reveal flags are set
        self.assertTrue(app_dict.get("intercourse_revealed"))
        self.assertTrue(app_dict.get("oral_revealed"))
        self.assertTrue(app_dict.get("intimate_revealed"))
        self.assertTrue(app_dict.get("turn_ons_revealed"))
        self.assertTrue(app_dict.get("fetishes_revealed"))
        self.assertTrue(app_dict.get("act_preferences_revealed"))

    def test_tier1_structured_oral_experience_transitions(self):
        """Verify structured oral milestone transitions oral experience from inexperienced to experienced."""
        app_dict = {}
        (
            new_mem,
            intercourse,
            oral,
            manual,
            track,
            is_intimate,
            boost,
        ) = _evaluate_npc_milestones(
            npc_name=self.npc_name,
            app_dict=app_dict,
            track="romantic",
            milestone_ev="oral_give",
            custom_summary=None,
            intercourse_exp="virgin",
            oral_exp="inexperienced",
            actions=[],
            narrative_text="",
            overall_check_success=True,
            is_player_romantic_action=True,
            is_player_intimate_action=True,
            is_player_oral_action=True,
            is_player_intercourse_action=False,
            is_player_confession_action=False,
            is_player_affection_action=False,
            affection_target_npc=None,
            gift_target_npc=None,
            gift_item_name=None,
            confession_target_npc=None,
            first_char_name=self.first_char,
        )
        self.assertTrue(is_intimate)
        self.assertIn("oral", oral.lower())
        self.assertTrue(app_dict.get("oral_revealed"))
        self.assertTrue(app_dict.get("intimate_revealed"))
        # Fetishes should NOT be revealed on pure oral
        self.assertFalse(app_dict.get("fetishes_revealed", False))

    def test_tier2_safety_net_narrative_intercourse(self):
        """Verify Tier 2 safety net catches implicit intercourse in narrative when milestone_ev is empty."""
        app_dict = {}
        narrative = "They made love passionately under the starlight until dawn."
        (
            new_mem,
            intercourse,
            oral,
            manual,
            track,
            is_intimate,
            boost,
        ) = _evaluate_npc_milestones(
            npc_name=self.npc_name,
            app_dict=app_dict,
            track="romantic",
            milestone_ev="",
            custom_summary=None,
            intercourse_exp="virgin",
            oral_exp="inexperienced",
            actions=[{"label": "Spend the night together with Elena"}],
            narrative_text=narrative,
            overall_check_success=True,
            is_player_romantic_action=True,
            is_player_intimate_action=True,
            is_player_oral_action=False,
            is_player_intercourse_action=True,
            is_player_confession_action=False,
            is_player_affection_action=False,
            affection_target_npc=None,
            gift_target_npc=None,
            gift_item_name=None,
            confession_target_npc=None,
            first_char_name=self.first_char,
            single_update=True,
        )
        self.assertTrue(is_intimate)
        self.assertEqual(intercourse, "non_virgin")
        self.assertTrue(app_dict.get("intercourse_revealed"))
        self.assertTrue(app_dict.get("intimate_revealed"))

    def test_precomputed_combined_check_text_matches_default(self):
        """Verify passing precomputed combined_check_text yields identical results to internal fallback."""
        actions = [{"label": "Kiss Elena gently under the mistletoe"}]
        narrative = "Elena leaned in, closing her eyes as their lips met."
        precomputed = (" ".join(a["label"] for a in actions) + " " + narrative).lower()

        app_dict1 = {}
        res1 = _evaluate_npc_milestones(
            npc_name=self.npc_name,
            app_dict=app_dict1,
            track="romantic",
            milestone_ev="",
            custom_summary=None,
            intercourse_exp="virgin",
            oral_exp="inexperienced",
            actions=actions,
            narrative_text=narrative,
            overall_check_success=True,
            is_player_romantic_action=True,
            is_player_intimate_action=False,
            is_player_oral_action=False,
            is_player_intercourse_action=False,
            is_player_confession_action=False,
            is_player_affection_action=False,
            affection_target_npc=None,
            gift_target_npc=None,
            gift_item_name=None,
            confession_target_npc=None,
            first_char_name=self.first_char,
            single_update=True,
            combined_check_text=None,
        )

        app_dict2 = {}
        res2 = _evaluate_npc_milestones(
            npc_name=self.npc_name,
            app_dict=app_dict2,
            track="romantic",
            milestone_ev="",
            custom_summary=None,
            intercourse_exp="virgin",
            oral_exp="inexperienced",
            actions=actions,
            narrative_text=narrative,
            overall_check_success=True,
            is_player_romantic_action=True,
            is_player_intimate_action=False,
            is_player_oral_action=False,
            is_player_intercourse_action=False,
            is_player_confession_action=False,
            is_player_affection_action=False,
            affection_target_npc=None,
            gift_target_npc=None,
            gift_item_name=None,
            confession_target_npc=None,
            first_char_name=self.first_char,
            single_update=True,
            combined_check_text=precomputed,
        )

        self.assertEqual(res1, res2)
        self.assertEqual(app_dict1, app_dict2)


if __name__ == "__main__":
    unittest.main()
