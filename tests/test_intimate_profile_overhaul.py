import unittest
from mechanics.social.persona import (
    generate_dynamic_turn_ons,
    generate_dynamic_fetish,
    generate_dynamic_act_preferences,
    generate_dynamic_intimate_experience,
    generate_past_intimate_history,
    calculate_intimate_action_dc_modifier,
    format_turn_ons_prompt_directive,
    format_fetish_prompt_directive,
    format_act_preferences_prompt_directive,
    normalize_appearance,
    merge_appearance_safely,
    merge_intercourse_states,
    merge_oral_states,
    merge_manual_states,
    ACT_PREFERENCE_REGISTRY,
    INTERCOURSE_STATES,
    ORAL_INTIMACY_STATES,
    MANUAL_INTIMACY_STATES
)
from cogs.contacts import build_intimate_profile_embed

class TestIntimateProfileOverhaul(unittest.TestCase):
    def test_dynamic_turn_ons_generation(self):
        """Verify that every character receives 1-2 Physical and 1-2 Action turn-ons with appropriate species tags."""
        # Human
        t_human = generate_dynamic_turn_ons(12345, race="human")
        self.assertIn("(Physical)", t_human)
        self.assertIn("(Action)", t_human)
        
        # Winged race (Angel)
        t_angel = generate_dynamic_turn_ons(54321, race="angel")
        self.assertIn("(Physical)", t_angel)
        self.assertIn("(Action)", t_angel)
        
        # Beastfolk (Fox)
        t_fox = generate_dynamic_turn_ons(99999, race="fox-beastfolk")
        self.assertIn("(Physical)", t_fox)
        self.assertIn("(Action)", t_fox)

    def test_dynamic_fetish_25_percent_rate_and_single_cap(self):
        """Verify that fetish generation rolls ~25% single fetish and ~75% None (Vanilla)."""
        vanilla_count = 0
        fetish_count = 0
        total = 500
        
        for i in range(total):
            f = generate_dynamic_fetish(i * 101 + 7, openness="moderate")
            if f == "None (Vanilla)":
                vanilla_count += 1
            else:
                fetish_count += 1
                # Must be a single fetish (no comma-separated list)
                self.assertNotIn(",", f, f"Fetish '{f}' must be a single kink, not a comma-separated list")

        vanilla_ratio = vanilla_count / total
        fetish_ratio = fetish_count / total
        self.assertAlmostEqual(fetish_ratio, 0.25, delta=0.08, msg="Fetish rate must be approximately 25%")
        self.assertAlmostEqual(vanilla_ratio, 0.75, delta=0.08, msg="Vanilla rate must be approximately 75%")

    def test_fetish_prompt_directive(self):
        """Verify that characters with a fetish generate a high-priority prompt directive to fulfill it first."""
        f_dir = format_fetish_prompt_directive("Maya", "Blindfolds", "Proactive / Dominant")
        self.assertIn("FETISH PRIORITY DIRECTIVE", f_dir)
        self.assertIn("Blindfolds", f_dir)
        self.assertIn("Maya", f_dir)
        
        # Vanilla character produces empty directive
        v_dir = format_fetish_prompt_directive("Maya", "None (Vanilla)", "Proactive / Dominant")
        self.assertEqual(v_dir, "")

    def test_symmetrical_act_preferences(self):
        """Verify that act preferences generate 1-3 disjoint Likes and 1-3 Dislikes from the 17-item registry."""
        self.assertGreaterEqual(len(ACT_PREFERENCE_REGISTRY), 17)
        for i in range(100):
            likes, dislikes = generate_dynamic_act_preferences(i * 31 + 13, openness="moderate")
            l_set = {x.strip().lower() for x in likes.split(",") if x.strip()}
            d_set = {x.strip().lower() for x in dislikes.split(",") if x.strip()}
            
            self.assertGreaterEqual(len(l_set), 1)
            self.assertLessEqual(len(l_set), 3)
            self.assertGreaterEqual(len(d_set), 1)
            self.assertLessEqual(len(d_set), 3)
            
            # Must be mutually exclusive (no overlap)
            self.assertTrue(l_set.isdisjoint(d_set), f"Likes {l_set} and Dislikes {d_set} must not overlap")

    def test_dc_modifier_calculation(self):
        """Verify dynamic DC modifier calculations for turn-ons, liked acts, disliked acts, and openness."""
        app_dict = {
            "turn_ons": "Inner thighs (Physical), Whispered praise (Action)",
            "act_likes": "Slow sensual rhythm",
            "act_dislikes": "Rough handling",
            "erotic_openness": "moderate"
        }
        # Turn-on hit (-2 bonus)
        dc_bonus = calculate_intimate_action_dc_modifier(
            label="Gently caress and stroke her inner thighs",
            app_dict=app_dict
        )
        self.assertLess(dc_bonus, 0, "Targeting a turn-on must reduce DC")

        # Disliked act (+3 penalty)
        dc_penalty = calculate_intimate_action_dc_modifier(
            label="Use rough handling and aggressively hold her down",
            app_dict=app_dict
        )
        self.assertGreater(dc_penalty, 0, "Triggering a disliked act must increase DC")

    def test_decoupled_3_track_experience_generation(self):
        """Verify that all 3 tracks are generated independently with openness modifiers."""
        # Test states validity
        for op in ["prude", "moderate", "bold", "shameless"]:
            for i in range(50):
                exp = generate_dynamic_intimate_experience(i * 73 + 19, openness=op)
                self.assertIn(exp["intercourse"], INTERCOURSE_STATES)
                self.assertIn(exp["oral"], ORAL_INTIMACY_STATES)
                self.assertIn(exp["manual"], MANUAL_INTIMACY_STATES)

    def test_4_tier_past_partner_scaling_and_affairs(self):
        """Verify 4-tier scaling: Prude/Moderate (1-2), Bold (1-4), Shameless (2-5 + secret affairs)."""
        # Prude with experience
        prude_hist = generate_past_intimate_history(intercourse="non_virgin", hash_val=42, gender="female", openness="prude")
        self.assertIsNotNone(prude_hist)
        self.assertLessEqual(prude_hist["partner_count"], 2)

        # Bold with experience
        bold_hist = generate_past_intimate_history(intercourse="non_virgin", hash_val=42, gender="female", openness="bold")
        self.assertIsNotNone(bold_hist)
        self.assertLessEqual(bold_hist["partner_count"], 4)

        # Shameless with experience & affair chance
        shameless_hist = generate_past_intimate_history(intercourse="non_virgin", hash_val=42, gender="female", openness="shameless", has_existing_partner=True)
        self.assertIsNotNone(shameless_hist)
        self.assertGreaterEqual(shameless_hist["partner_count"], 2)

    def test_one_way_experience_ratchets(self):
        """Verify that intercourse, oral, and manual tracks never regress."""
        # Intercourse
        self.assertEqual(merge_intercourse_states("virgin", "non_virgin"), "non_virgin")
        self.assertEqual(merge_intercourse_states("non_virgin", "virgin"), "non_virgin")
        
        # Oral
        self.assertEqual(merge_oral_states("inexperienced", "has_done_oral"), "has_done_oral")
        self.assertEqual(merge_oral_states("has_done_oral", "has_received_oral"), "has_done_and_received_oral")
        self.assertEqual(merge_oral_states("has_done_and_received_oral", "has_done_oral"), "has_done_and_received_oral")
        self.assertEqual(merge_oral_states("has_done_oral", "inexperienced"), "has_done_oral")

        # Manual
        self.assertEqual(merge_manual_states("inexperienced", "has_done_manual"), "has_done_manual")
        self.assertEqual(merge_manual_states("has_done_manual", "has_received_manual"), "has_done_and_received_manual")
        self.assertEqual(merge_manual_states("has_done_and_received_manual", "inexperienced"), "has_done_and_received_manual")

    def test_build_intimate_profile_embed_5_fields(self):
        """Verify build_intimate_profile_embed formats the 5 clear fields properly."""
        contact = {
            "name": "Evelyn Ross",
            "relationship_score": 85,
            "appearance": {
                "breast_size": "Voluptuous D-Cup",
                "intercourse_experience": "virgin",
                "oral_experience": "has_done_oral",
                "manual_experience": "has_received_manual",
                "intimate_demeanor": "Secretly Teasing",
                "intimate_dynamic": "Switch / Sensual",
                "erotic_openness": "shameless",
                "turn_ons": "Inner thighs (Physical), Whispered praise (Action)",
                "fetishes": "Sensory deprivation",
                "act_likes": "Slow sensual rhythm, Giving oral intimacy",
                "act_dislikes": "Rough handling",
                "intimate_revealed": True
            }
        }
        embed = build_intimate_profile_embed(contact, scenario_key="nsfw_high_school_drama")
        field_names = [f.name for f in embed.fields]
        
        self.assertIn("🔞 Anatomy & Experience", field_names)
        self.assertIn("🎭 Demeanor & Dynamic", field_names)
        self.assertIn("🔥 Turn-Ons & Desires", field_names)
        self.assertIn("❤️ Act & Position Preferences", field_names)
        self.assertNotIn("💡 Active Intimate Synergy & Modifiers", field_names)

if __name__ == "__main__":
    unittest.main()
