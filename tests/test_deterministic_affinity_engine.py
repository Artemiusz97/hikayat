from __future__ import annotations

import unittest
from skill_check import CheckResult
from mechanics.social.affinity_engine import calculate_social_affinity_delta


class TestDeterministicSocialAffinityEngine(unittest.TestCase):
    """Comprehensive test suite for the Deterministic Social Affinity Engine.
    Verifies that every player action in dialogue/social interactions receives
    accurate mathematical base deltas and 5-dimensional modifier scaling.
    """

    def setUp(self):
        # Mia Yamada's canonical profile (from Turn 12)
        self.mia_contact = {
            "name": "Mia Yamada",
            "relationship_score": 15,
            "track": "platonic",
            "unlocked_traits": ["Playful", "Sensitive"],
            "preferences": [
                "Likes Direct Candor & Unfiltered Honesty",
                "Dislikes Invasive Prying & Boundary Pushing",
                "Likes Aged Earl Grey Tea",
                "Dislikes Cheap Instant Coffee"
            ],
            "appearance": {
                "intimate_demeanor": "Hesitant & Flustered",
                "intimate_dynamic": "Surrenders Control",
                "sensitive_spots": "Nape of neck, collarbone",
                "turn_ons": "Gentle guidance, whispers, hair stroking",
                "turn_offs": "Prying into past intimacy, crude vulgarity, aggressive rushing",
                "act_likes": "Gentle kissing, holding hands, slow undressing",
                "act_dislikes": "Rough handling, public exposure",
                "erotic_openness": "Modest"
            }
        }

    # -------------------------------------------------------------------------
    # 1. BASELINE TESTS (SUCCESS / FAILURE / CRIT / AMBIENT)
    # -------------------------------------------------------------------------
    def test_base_delta_regular_success(self):
        """Standard check success against Stranger (< 50) with no matching traits/prefs yields base +8."""
        action = {
            "label": "Ask about the student council report format",
            "stat": "INT",
            "check": CheckResult(chance=70, roll=50.0, tier="success", tier_label="Success", succeeded=True, requirement=5)
        }
        delta, reasons, breakdown = calculate_social_affinity_delta(action, "Generic Student", {})
        self.assertEqual(delta, 8)
        self.assertEqual(breakdown["base_delta"], 8)
        self.assertIn("Check Success (+8)", reasons)

    def test_base_delta_critical_success(self):
        """Critical check success against Stranger (< 50) yields base +12."""
        action = {
            "label": "Deliver an impeccably structured proposal",
            "stat": "CHA",
            "check": CheckResult(chance=95, roll=98.0, tier="crit_success", tier_label="Critical Success", succeeded=True, requirement=8)
        }
        delta, reasons, breakdown = calculate_social_affinity_delta(action, "Generic Student", {})
        self.assertEqual(delta, 12)
        self.assertEqual(breakdown["base_delta"], 12)
        self.assertIn("Critical Success (+12)", reasons)

    def test_base_delta_regular_failure(self):
        """Standard check failure with no matching traits/prefs yields base -2."""
        action = {
            "label": "Attempt to explain the scheduling conflict",
            "stat": "CHA",
            "check": CheckResult(chance=50, roll=65.0, tier="fail", tier_label="Failure", succeeded=False, requirement=6)
        }
        delta, reasons, breakdown = calculate_social_affinity_delta(action, "Generic Student", {})
        self.assertEqual(delta, -2)
        self.assertEqual(breakdown["base_delta"], -2)
        self.assertIn("Check Failure (-2)", reasons)

    def test_base_delta_critical_failure(self):
        """Critical check failure yields base -4."""
        action = {
            "label": "Stumble over words and drop the paperwork",
            "stat": "CHA",
            "check": CheckResult(chance=30, roll=5.0, tier="crit_fail", tier_label="Critical Failure", succeeded=False, requirement=6)
        }
        delta, reasons, breakdown = calculate_social_affinity_delta(action, "Generic Student", {})
        self.assertEqual(delta, -4)
        self.assertEqual(breakdown["base_delta"], -4)
        self.assertIn("Critical Failure (-4)", reasons)

    def test_tapered_base_deltas_acquaintance_friend_meetup_and_clamp(self):
        """Acquaintance (+4/+6), Friend+ (+3/+5), Private Meetup (+2), and [-10, 18] clamp."""
        ok_chk = CheckResult(chance=75, roll=30.0, tier="success", tier_label="Success", succeeded=True, requirement=6)
        crit_chk = CheckResult(chance=90, roll=99.0, tier="crit_success", tier_label="Critical Success", succeeded=True, requirement=6)

        # Acquaintance (50..99)
        d_acq, r_acq, _ = calculate_social_affinity_delta(
            {"label": "Discuss club logistics", "stat": "INT", "check": ok_chk},
            "Student",
            {"relationship_score": 65},
        )
        self.assertEqual(d_acq, 4)
        self.assertIn("Check Success (+4)", r_acq)

        d_acq_crit, r_acq_crit, _ = calculate_social_affinity_delta(
            {"label": "Discuss club logistics", "stat": "INT", "check": crit_chk},
            "Student",
            {"relationship_score": 65},
        )
        self.assertEqual(d_acq_crit, 6)
        self.assertIn("Critical Success (+6)", r_acq_crit)

        # Friend+ (>= 100) + Private Meetup (+2)
        d_fr, r_fr, _ = calculate_social_affinity_delta(
            {"label": "Share stories over coffee", "stat": "CHA", "check": ok_chk, "is_private_meetup": True},
            "Student",
            {"relationship_score": 120},
        )
        self.assertEqual(d_fr, 5)
        self.assertIn("Check Success (+3)", r_fr)
        self.assertIn("Private Meetup / Date chemistry (+2)", r_fr)

        # Single-turn upper clamp at +18 (Stranger Crit +12 + Meetup +2 + Vintage Favorite Gift +5 + Playful +1 = +20 -> 18)
        d_cap, _, b_cap = calculate_social_affinity_delta(
            {
                "label": "Playfully tease and present Vintage Aged Earl Grey Tea",
                "action_category": "gift_offer",
                "item_name": "Vintage Aged Earl Grey Tea",
                "stat": "CHA",
                "check": crit_chk,
                "is_private_meetup": True,
            },
            "Mia Yamada",
            self.mia_contact,
        )
        self.assertEqual(d_cap, 18)
        self.assertEqual(b_cap["capped_delta"], 18)

    def test_neutral_ambient_dialogue_choice_yields_zero(self):
        """Neutral ambient dialogue choices (stat: NONE, no check) must yield exactly 0 delta."""
        action = {
            "label": "Ask about the history of the upright piano in the alcove",
            "stat": "NONE",
            "check": None
        }
        delta, reasons, breakdown = calculate_social_affinity_delta(action, "Mia Yamada", self.mia_contact)
        self.assertEqual(delta, 0)
        self.assertEqual(breakdown["base_delta"], 0)
        self.assertIn("Neutral dialogue choice (0)", reasons)

    def test_warm_ambient_dialogue_choice_yields_plus_one(self):
        """Polite or warm ambient remarks yield +1 delta."""
        action = {
            "label": "Smile warmly and thank her for sharing the room",
            "stat": "NONE",
            "check": None
        }
        delta, reasons, breakdown = calculate_social_affinity_delta(action, "Mia Yamada", self.mia_contact)
        self.assertGreaterEqual(delta, 1)
        self.assertEqual(breakdown["base_delta"], 1)
        self.assertIn("Warm / polite conversation (+1)", reasons)

    def test_hostile_ambient_dialogue_choice_yields_penalty(self):
        """Hostile or abrasive remarks yield negative delta."""
        action = {
            "label": "Scoff rudely and glare at her ledger",
            "stat": "NONE",
            "check": None
        }
        delta, reasons, breakdown = calculate_social_affinity_delta(action, "Mia Yamada", self.mia_contact)
        self.assertLessEqual(delta, -2)
        self.assertEqual(breakdown["base_delta"], -2)
        self.assertIn("Hostile / abrasive tone (-2)", reasons)

    # -------------------------------------------------------------------------
    # 2. PHYSICAL GIFT SCALING TESTS
    # -------------------------------------------------------------------------
    def test_gift_scaling_common_favorite(self):
        """Standard/common favorite gift yields +3 additive bonus."""
        action = {
            "label": "Offer her a cup of Earl Grey Tea",
            "action_category": "gift_offer",
            "item_name": "Earl Grey Tea",
            "stat": "CHA",
            "check": CheckResult(chance=90, roll=50.0, tier="success", tier_label="Success", succeeded=True, requirement=4)
        }
        delta, reasons, breakdown = calculate_social_affinity_delta(action, "Mia Yamada", self.mia_contact)
        self.assertGreaterEqual(delta, 4)
        self.assertIn("Loves gift: Earl Grey Tea (+3)", reasons)

    def test_gift_scaling_vintage_rare_favorite(self):
        """Vintage/rare favorite gift scales up to +5 additive bonus."""
        action = {
            "label": "Present a canister of Vintage Aged Earl Grey Tea",
            "action_category": "gift_offer",
            "item_name": "Vintage Aged Earl Grey Tea",
            "stat": "CHA",
            "check": CheckResult(chance=90, roll=50.0, tier="success", tier_label="Success", succeeded=True, requirement=4)
        }
        delta, reasons, breakdown = calculate_social_affinity_delta(action, "Mia Yamada", self.mia_contact)
        self.assertGreaterEqual(delta, 6)
        self.assertIn("Loves gift: Vintage Aged Earl Grey Tea (+5)", reasons)

    def test_gift_scaling_disliked_gift(self):
        """Disliked gift yields negative penalty (-3 to -5) even on check success."""
        action = {
            "label": "Offer her a cup of Instant Coffee",
            "action_category": "gift_offer",
            "item_name": "Instant Coffee",
            "stat": "CHA",
            "check": CheckResult(chance=90, roll=50.0, tier="success", tier_label="Success", succeeded=True, requirement=4)
        }
        delta, reasons, breakdown = calculate_social_affinity_delta(action, "Mia Yamada", self.mia_contact)
        self.assertLessEqual(delta, 0)
        self.assertIn("Dislikes gift: Instant Coffee (-3)", reasons)

    # -------------------------------------------------------------------------
    # 3. FIVE-DIMENSION MODIFIER TESTS
    # -------------------------------------------------------------------------
    def test_traits_alignment_playful_and_diligent(self):
        """Action aligning with character traits grants additive trait bonus."""
        contact_diligent = {
            "name": "Yea-ji Kang",
            "unlocked_traits": ["Diligent"],
            "preferences": []
        }
        action = {
            "label": "Study student council budget notes with careful focus",
            "stat": "INT",
            "check": CheckResult(chance=80, roll=40.0, tier="success", tier_label="Success", succeeded=True, requirement=5)
        }
        delta, reasons, breakdown = calculate_social_affinity_delta(action, "Yea-ji Kang", contact_diligent)
        self.assertGreaterEqual(delta, 2)
        self.assertIn("Diligent appreciates studious focus (+1)", reasons)

    def test_demeanor_and_dynamic_alignment(self):
        """Receptive / Surrenders Control dynamic gains affinity when partner takes charge confidently."""
        action = {
            "label": "Confident and gentle, guide her hand across the keyboard",
            "stat": "CHA",
            "check": CheckResult(chance=80, roll=30.0, tier="success", tier_label="Success", succeeded=True, requirement=6)
        }
        delta, reasons, breakdown = calculate_social_affinity_delta(action, "Mia Yamada", self.mia_contact)
        self.assertGreaterEqual(delta, 2)
        self.assertIn("Matches dynamic: appreciates partner taking charge (+1)", reasons)

    def test_turn_on_triggered_on_success(self):
        """Touching or triggering a known turn-on on success grants +2 bonus."""
        action = {
            "label": "Whisper softly close to her ear and gently stroke her hair",
            "action_category": "affection_touch",
            "stat": "CHA",
            "check": CheckResult(chance=80, roll=35.0, tier="success", tier_label="Success", succeeded=True, requirement=6)
        }
        delta, reasons, breakdown = calculate_social_affinity_delta(action, "Mia Yamada", self.mia_contact)
        self.assertGreaterEqual(delta, 3)
        self.assertIn("Turn-on triggered: Whispers (+2)", reasons)

    def test_turn_off_triggered_on_success_caps_affinity_at_zero(self):
        """Even if check succeeded, hitting an explicit turn-off prevents positive gain (capped at 0)."""
        action = {
            "label": "Flirt using crude vulgarity and coarse language",
            "stat": "CHA",
            "check": CheckResult(chance=80, roll=40.0, tier="success", tier_label="Success", succeeded=True, requirement=6)
        }
        delta, reasons, breakdown = calculate_social_affinity_delta(action, "Mia Yamada", self.mia_contact)
        self.assertLessEqual(delta, 0)
        self.assertTrue(any("Turn-off triggered" in r for r in reasons))

    # -------------------------------------------------------------------------
    # 4. BOUNDING & BYSTANDER CONSTRAINTS
    # -------------------------------------------------------------------------
    def test_check_failure_hard_ceiling_at_zero(self):
        """A failed check can NEVER award positive affinity delta, even with trait resonance."""
        action = {
            "label": "Try to playfully tease her but stumble clumsily",
            "stat": "CHA",
            "check": CheckResult(chance=50, roll=70.0, tier="fail", tier_label="Failure", succeeded=False, requirement=6)
        }
        delta, reasons, breakdown = calculate_social_affinity_delta(action, "Mia Yamada", self.mia_contact)
        self.assertLessEqual(delta, -1, "Failed check must result in an affinity penalty")

    def test_bystander_protection_never_loses_affinity(self):
        """Bystanders not targeted or involved in the action receive 0 affinity change."""
        action = {
            "label": "Playfully challenge Mia Yamada about past experiences",
            "stat": "CHA",
            "check": CheckResult(chance=50, roll=70.0, tier="fail", tier_label="Failure", succeeded=False, requirement=6)
        }
        delta, reasons, breakdown = calculate_social_affinity_delta(
            action, "Yuki Kuroda", {}, is_target_npc=False
        )
        self.assertEqual(delta, 0)
        self.assertIn("Bystander (no interaction)", reasons)

    # -------------------------------------------------------------------------
    # 5. TURN 12 EXACT SCENARIO (MIA YAMADA REGRESSION TEST)
    # -------------------------------------------------------------------------
    def test_turn_12_mia_yamada_failed_prying_challenge(self):
        """In Turn 12, player rolled a failed CHA check on 'Playfully challenge her about past experiences'."""
        action = {
            "label": "Playfully challenge her about past experiences",
            "action_category": "dialogue",
            "stat": "CHA",
            "target_npc": "Mia Yamada",
            "check": CheckResult(chance=83, roll=85.0, tier="fail", tier_label="Failure", succeeded=False, requirement=6)
        }
        delta, reasons, breakdown = calculate_social_affinity_delta(
            action, "Mia Yamada", self.mia_contact, is_target_npc=True
        )

        self.assertLessEqual(delta, -3, f"Expected significant negative affinity penalty, got {delta}")
        self.assertIn("Check Failure (-2)", reasons)
        self.assertTrue(any("Invasive Prying" in r for r in reasons), f"Preferences dislike should be triggered: {reasons}")
        self.assertTrue(any("Turn-off triggered" in r for r in reasons), f"Turn-off should be triggered: {reasons}")
        self.assertLessEqual(breakdown["capped_delta"], -3)


if __name__ == "__main__":
    unittest.main()
