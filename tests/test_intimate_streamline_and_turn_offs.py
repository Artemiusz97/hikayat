import unittest
from mechanics.social.persona.intimacy.constants import (
    TURN_OFF_ITEMS,
    TURN_OFF_TEMPLATES,
    TURN_OFF_DETECTION_REGISTRY,
    DESIRES_AND_KINKS_ITEMS,
    ACT_PREFERENCE_REGISTRY,
)
from mechanics.social.persona.intimacy.generation import (
    generate_dynamic_turn_offs,
    generate_dynamic_desires_and_turn_offs,
    generate_dynamic_act_preferences,
    generate_dynamic_intimate_attributes,
    generate_intimate_synergy_tip,
)
from mechanics.social.persona.intimacy.logic import (
    is_turn_off_triggered,
    calculate_intimate_action_dc_modifier,
)
from mechanics.social.persona.intimacy.formatting import (
    format_desires_and_turn_offs_prompt_directive,
    format_intimate_profile_sections,
)
from mechanics.social.persona.intimacy.appearance import (
    normalize_appearance,
    merge_appearance_safely,
)


class TestIntimateStreamlineAndTurnOffs(unittest.TestCase):

    def test_turn_off_items_and_constants(self):
        """Verify TURN_OFF_ITEMS and registries are populated with sensory/psychological turn-offs."""
        self.assertGreater(len(TURN_OFF_ITEMS), 10)
        self.assertIn("Dead silence & emotional detachment", TURN_OFF_ITEMS)
        self.assertIn("Rushed impatience & entitlement", TURN_OFF_ITEMS)
        self.assertIn("Clumsy / careless rough handling", TURN_OFF_ITEMS)
        self.assertIn("Purely transactional feeling", TURN_OFF_ITEMS)
        detection_ids = [x["id"] for x in TURN_OFF_DETECTION_REGISTRY]
        self.assertIn("dead_silence", detection_ids)
        self.assertIn("crude_degradation", detection_ids)
        self.assertIn("clumsy_rough_handling", detection_ids)

    def test_act_preference_registry_clean_and_deduplicated(self):
        """Verify ACT_PREFERENCE_REGISTRY only contains physical acts/positions/pacing (no mental kinks)."""
        act_ids = [a["id"] for a in ACT_PREFERENCE_REGISTRY]
        self.assertNotIn("mirror_exhibition", act_ids)
        self.assertNotIn("public_thrill", act_ids)
        self.assertNotIn("pinned_down", act_ids)
        self.assertNotIn("dirty_talk", act_ids)
        self.assertIn("missionary", act_ids)
        self.assertIn("giving_oral", act_ids)
        self.assertIn("slow_sensual", act_ids)

    def test_dynamic_generation_counts_and_synergy(self):
        """Verify generator produces 1-2 turn-offs, 1-3 desires, 1-2 likes, 1-2 dislikes."""
        for seed in [1234, 5678, 9999, 42]:
            turn_offs = generate_dynamic_turn_offs(hash_val=seed, dynamic="proactive", openness="moderate", traits=["Proud"])
            to_list = [x.strip() for x in turn_offs.split(",") if x.strip()]
            self.assertIn(len(to_list), (1, 2))

            phys_str, desires_str, turn_offs_str = generate_dynamic_desires_and_turn_offs(
                hash_val=seed,
                race="human",
                dynamic="sensual",
                openness="bold",
                traits=["Playful"]
            )
            self.assertTrue(phys_str)
            self.assertTrue(desires_str)
            self.assertTrue(turn_offs_str)

            acts = generate_dynamic_act_preferences(hash_val=seed, dynamic="submissive", openness="moderate")
            likes_list = [x.strip() for x in acts["act_likes"].split(",") if x.strip()]
            dislikes_list = [x.strip() for x in acts["act_dislikes"].split(",") if x.strip()]
            self.assertIn(len(likes_list), (1, 2))
            self.assertIn(len(dislikes_list), (1, 2))

    def test_is_turn_off_triggered_matching(self):
        """Verify is_turn_off_triggered matches registry tokens and natural language strings."""
        turn_offs_str = "Aggressive rough handling, Dead silence & emotional detachment, Dirty talk & crude vulgarity"

        # Explicit action text matching
        self.assertTrue(is_turn_off_triggered("Force them down with rough aggressive handling", turn_offs_str))
        self.assertTrue(is_turn_off_triggered("Stay in dead silence and cold detachment", turn_offs_str))
        self.assertTrue(is_turn_off_triggered("Whisper crude vulgarity and dirty talk", turn_offs_str))

        # Action that does not match
        self.assertFalse(is_turn_off_triggered("Gently caress their cheek with tender warmth", turn_offs_str))
        self.assertFalse(is_turn_off_triggered("Slow sensual missionary with eye contact", turn_offs_str))

    def test_calculate_intimate_action_dc_modifier_turn_off_penalty(self):
        """Verify DC modifier applies +5 penalty for turn-offs and -2 bonus for desires."""
        appearance = {
            "turn_offs": "Aggressive hair pulling, Dead silence & emotional detachment",
            "desires_and_kinks": "whispered praise, slow undressing",
            "act_likes": "Slow & sensual pacing",
            "act_dislikes": "Fast & passionate urgency",
        }

        # Turn-off triggered: +5 penalty
        mod_turn_off = calculate_intimate_action_dc_modifier("Yank hair aggressively in silence", appearance)
        self.assertGreaterEqual(mod_turn_off, 5)

        # Desired trigger: -2 bonus (or -4 if both desire & liked act match)
        mod_desire = calculate_intimate_action_dc_modifier("Whisper tender praise and take a slow sensual pace", appearance)
        self.assertLessEqual(mod_desire, -2)

        # Disliked act: +3 penalty
        mod_disliked = calculate_intimate_action_dc_modifier("Push with fast urgency and passionate speed", appearance)
        self.assertGreaterEqual(mod_disliked, 3)

    def test_prompt_directive_turn_off_guidance(self):
        """Verify format_desires_and_turn_offs_prompt_directive produces visceral rejection & boundary directives."""
        directive = format_desires_and_turn_offs_prompt_directive(
            partner_name="Seraphina",
            desires_val="whispered praise, ear nibbling",
            turn_offs_val="Sudden biting & harsh pain, Dead silence",
            dynamic_val="sensual"
        )
        self.assertIn("INTIMATE DESIRES & KINKS (Seraphina)", directive)
        self.assertIn("INTIMATE TURN-OFFS & AVERSIONS (Seraphina)", directive)
        self.assertIn("THEY RECOIL WITH DISGUST & REJECTION", directive)
        self.assertIn("On check failure: Seraphina recoils, pulls away, freezes with visible disgust", directive)
        self.assertIn("If the check failed by 5+, intimacy ends immediately", directive)
        self.assertIn("On marginal check success: Seraphina is visibly put off", directive)

    def test_format_intimate_profile_sections_symmetry(self):
        """Verify formatted profile renders Sensitive Spots, Desires & Kinks, and Turn-Offs symmetrically."""
        app = {
            "breast_size": "plump",
            "intercourse_experience": "virgin",
            "oral_experience": "inexperienced",
            "manual_experience": "inexperienced",
            "intimate_demeanor": "teasing",
            "intimate_dynamic": "sensual",
            "erotic_openness": "moderate",
            "sensitive_spots": "Nape of neck, Lower spine",
            "desires_and_kinks": "whispered praise, blindfolds",
            "turn_offs": "Dead silence & emotional detachment, Purely transactional feeling",
            "act_likes": "Slow & sensual pacing",
            "act_dislikes": "Biting & marks",
            "undergarments": {"bra_color": "Silk", "bra_style": "wireless"},
        }
        sections = format_intimate_profile_sections(app, gender="female", info_level=3)

        sens_text = "\n".join(sections["sensitivities"])
        self.assertIn("• **Sensitive Spots**: Nape of neck (Physical)", sens_text)
        self.assertIn("whispered praise (Action)", sens_text)
        self.assertIn("blindfolds (Action)", sens_text)
        self.assertIn("• **Turn-Offs**: Dead silence & emotional detachment, Purely transactional feeling", sens_text)

        spots_text = "\n".join(sections["sensitive_spots"])
        self.assertIn("• **Sensitive Spots**: Nape of neck (Physical)", spots_text)
        self.assertNotIn("Turn-Offs", spots_text)

        desires_text = "\n".join(sections["desires_and_turn_offs"])
        self.assertIn("whispered praise (Action)", desires_text)
        self.assertIn("• **Turn-Offs**: Dead silence & emotional detachment, Purely transactional feeling", desires_text)
        self.assertNotIn("Sensitive Spots", desires_text)

        acts_text = "\n".join(sections["act_preferences"])
        self.assertIn("• **Preferred / Likes**: Slow & sensual pacing", acts_text)
        self.assertIn("• **Aversions / Dislikes**: Biting & marks", acts_text)

    def test_legacy_kinks_in_act_likes_migrated_to_desires(self):
        """Verify legacy kinks (pinned down, mirror exhibition) are migrated out of act_likes into desires_and_kinks."""
        app = {
            "act_likes": "Being pinned down / restrained, Facial climax, Mirror observation & exhibition",
            "act_dislikes": "Face-to-face missionary",
            "turn_ons": "Slow undressing",
        }
        norm = normalize_appearance(app, gender="male", race="human")
        self.assertIn("Facial climax", norm["act_likes"])
        self.assertNotIn("pinned down", norm["act_likes"].lower())
        self.assertNotIn("mirror", norm["act_likes"].lower())
        self.assertIn("pinned down", norm["desires_and_kinks"].lower())
        self.assertIn("mirror", norm["desires_and_kinks"].lower())

    def test_appearance_normalization_and_safe_merge_preserves_turn_offs(self):
        """Verify normalize_appearance and merge_appearance_safely retain turn_offs and desires."""
        base_app = {
            "turn_offs": "Aggressive rough handling",
            "desires_and_kinks": "Gentle caresses",
            "turn_offs_revealed": True,
        }
        norm = normalize_appearance(base_app, gender="female", race="human")
        self.assertIn("turn_offs", norm)
        self.assertTrue(norm.get("turn_offs_revealed"))

        merged_empty = merge_appearance_safely(
            {"turn_offs_revealed": True},
            {"turn_offs": "Aggressive rough handling, Loud public exposure"}
        )
        self.assertIn("Loud public exposure", merged_empty["turn_offs"])
        self.assertTrue(merged_empty.get("turn_offs_revealed"))

        merged_protect = merge_appearance_safely(
            base_app,
            {"turn_offs": "Completely different thing"}
        )
        self.assertEqual(merged_protect["turn_offs"], "Aggressive rough handling")

    def test_synergy_tip_includes_turn_off_warnings(self):
        """Verify synergy tip generates actionable advice on what to pursue and what to strictly avoid."""
        discovered = {
            "turn_ons": "whispered praise",
            "turn_offs": "Dead silence & emotional detachment",
            "act_likes": "Slow & sensual pacing",
            "dynamic": "sensual"
        }
        tip = generate_intimate_synergy_tip("Aria", discovered, info_level=3)
        self.assertEqual(tip["name"], "💡 Active Intimate Synergy & Modifiers")
        self.assertIn("Aria", tip["value"])
        self.assertIn("Turn-Off Warning", tip["value"])
        self.assertIn("Dead silence & emotional detachment", tip["value"])


if __name__ == "__main__":
    unittest.main()
