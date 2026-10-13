"""
Unit tests for the Relationship Meter & Contact List mechanics.
"""
import os
import sys
import unittest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
from mechanics.social.relationships import (
    clamp_score,
    get_relationship_tier,
    get_relationship_modifier,
    get_unlocked_info_level,
    format_progress_bar,
    format_llm_relationship_context,
    MIN_RELATIONSHIP,
    MAX_RELATIONSHIP,
    is_martial_npc
)


class TestRelationshipsMechanic(unittest.TestCase):

    def test_score_clamping(self):
        self.assertEqual(clamp_score(50), 50)
        self.assertEqual(clamp_score(350), MAX_RELATIONSHIP)
        self.assertEqual(clamp_score(-200), MIN_RELATIONSHIP)
        self.assertEqual(clamp_score(0), 0)

    def test_tier_resolution_platonic(self):
        tier_stranger = get_relationship_tier(5, track="platonic", scenario="high_school_drama")
        self.assertEqual(tier_stranger["name"], "Stranger")

        tier_hallway = get_relationship_tier(75, track="platonic", scenario="high_school_drama")
        self.assertEqual(tier_hallway["name"], "Hallway Buddy")

        tier_friend = get_relationship_tier(120, track="platonic", scenario="high_school_drama")
        self.assertEqual(tier_friend["name"], "Lunch Friend")

        tier_bestie = get_relationship_tier(170, track="platonic", scenario="high_school_drama")
        self.assertEqual(tier_bestie["name"], "Best Friend")

        tier_inner = get_relationship_tier(220, track="platonic", scenario="high_school_drama")
        self.assertEqual(tier_inner["name"], "Inner Circle")

        tier_sworn = get_relationship_tier(270, track="platonic", scenario="high_school_drama")
        self.assertEqual(tier_sworn["name"], "Sworn Bestie")

    def test_tier_resolution_romantic(self):
        tier_crush = get_relationship_tier(120, track="romantic", scenario="high_school_drama")
        self.assertEqual(tier_crush["name"], "Big Crush")

        tier_partner = get_relationship_tier(170, track="romantic", scenario="high_school_drama")
        self.assertEqual(tier_partner["name"], "Dating / Partner")

        tier_exclusive = get_relationship_tier(220, track="romantic", scenario="high_school_drama")
        self.assertEqual(tier_exclusive["name"], "Exclusive Romance")

        tier_soulmate = get_relationship_tier(270, track="romantic", scenario="high_school_drama")
        self.assertEqual(tier_soulmate["name"], "High School Sweethearts / Soulmate")

    def test_tier_resolution_negative(self):
        tier_unfriendly = get_relationship_tier(-5, track="platonic", scenario="high_school_drama")
        self.assertEqual(tier_unfriendly["name"], "Annoyance")

        tier_rival = get_relationship_tier(-25, track="platonic", scenario="high_school_drama")
        self.assertEqual(tier_rival["name"], "Class Rival")

        tier_enemy = get_relationship_tier(-95, track="platonic", scenario="high_school_drama")
        self.assertEqual(tier_enemy["name"], "Arch-Enemy")

    def test_skill_check_modifiers(self):
        self.assertEqual(get_relationship_modifier(45), 4)
        self.assertEqual(get_relationship_modifier(85), 8)
        self.assertEqual(get_relationship_modifier(150), 10)
        self.assertEqual(get_relationship_modifier(0), 0)
        self.assertEqual(get_relationship_modifier(-35), -4)
        self.assertEqual(get_relationship_modifier(-75), -8)

    def test_unlocked_info_level(self):
        self.assertEqual(get_unlocked_info_level(5), 1)
        self.assertEqual(get_unlocked_info_level(80), 1)
        self.assertEqual(get_unlocked_info_level(120), 2)
        self.assertEqual(get_unlocked_info_level(220), 3)

    def test_progress_bar_format(self):
        bar = format_progress_bar(200, width=10)
        self.assertIn("███████", bar)
        self.assertIn("+200", bar)

    def test_database_contacts_crud(self):
        db.init_db()
        import time
        test_session_id = int(time.time() * 1000)
        test_char_id = 88888


        # Create contact
        c1 = db.upsert_contact(
            session_id=test_session_id,
            character_id=test_char_id,
            npc_id="alex_vance",
            name="Alex Vance",
            basic_info={"role": "Class President", "age": 17},
            delta_score=25,
            track="romantic",
            new_traits=["Ambitious", "Coffee Addict"]
        )
        self.assertEqual(c1["relationship_score"], 25)
        self.assertEqual(c1["track"], "romantic")

        # Update contact (add +30 relationship delta and new trait)
        c1_updated = db.upsert_contact(
            session_id=test_session_id,
            character_id=test_char_id,
            npc_id="alex_vance",
            name="Alex Vance",
            delta_score=30,
            new_traits=["Secretly failing Math"]
        )
        self.assertEqual(c1_updated["relationship_score"], 55)
        self.assertIn("Secretly Failing Math", c1_updated["unlocked_traits"])
        self.assertIn("Coffee Addict", c1_updated["unlocked_traits"])

        # Fetch contacts list
        contacts = db.get_contacts(test_session_id, test_char_id)
        self.assertTrue(any(c["npc_id"] == "alex_vance" for c in contacts))

        # Format LLM context
        llm_context = format_llm_relationship_context(contacts, scenario="high_school_drama")
        self.assertIn("Alex Vance", llm_context)
        self.assertIn("+55", llm_context)

    def test_reconcile_action_affinity_delta_deterministic_guards(self):
        from mechanics.social.relationships import reconcile_action_affinity_delta

        # 1. Hallucinated -7 on successful check is rejected and bounded to positive (+2 default)
        action_success = {"label": "[Charisma 12] Tease Yea-ji", "check": {"tier": "success", "roll": 14, "dc": 12}}
        delta_recovered = reconcile_action_affinity_delta(
            raw_delta=-7,
            action=action_success,
            is_target=True,
            overall_check_success=True,
            is_hostile=False
        )
        self.assertEqual(delta_recovered, 2)

        # 2. Critical success allows +3 to +6 (default +4 if raw is negative/corrupted)
        action_crit = {"label": "[Charisma 15] Charm Yea-ji", "check": {"tier": "crit_success", "roll": 20, "dc": 15}}
        delta_crit = reconcile_action_affinity_delta(
            raw_delta=-7,
            action=action_crit,
            is_target=True,
            overall_check_success=True,
            is_hostile=False
        )
        self.assertEqual(delta_crit, 4)

        # 3. Bystander protection: uninvolved characters (like Zihan) never receive negative affinity
        delta_bystander = reconcile_action_affinity_delta(
            raw_delta=-7,
            action=action_success,
            is_target=False,
            overall_check_success=True,
            is_hostile=False
        )
        self.assertEqual(delta_bystander, 0)

        # 4. Hostile action overrides positive raw delta to negative
        delta_hostile = reconcile_action_affinity_delta(
            raw_delta=5,
            action={"label": "Insult and mock the student"},
            is_target=True,
            overall_check_success=True,
            is_hostile=True
        )
        self.assertLess(delta_hostile, 0)

        # 5. Failed conversational check bounds to mild penalty (not -7 catastrophe, clamped to [-5, 0])
        action_fail = {"label": "[Charisma 12] Tease Yea-ji", "check": {"tier": "fail", "roll": 8, "dc": 12}}
        delta_fail = reconcile_action_affinity_delta(
            raw_delta=-7,
            action=action_fail,
            is_target=True,
            overall_check_success=False,
            is_hostile=False
        )
        self.assertGreaterEqual(delta_fail, -5)
        self.assertLessEqual(delta_fail, 0)

    def test_is_martial_npc(self):
        # Fantasy martial roles
        self.assertTrue(is_martial_npc({"name": "Alex", "role": "Town Guard", "description": "Standing watch."}, scenario="fantasy"))
        self.assertTrue(is_martial_npc({"name": "Bob", "role": "Knight", "description": "Wandering knight with claymore."}, scenario="fantasy"))
        self.assertTrue(is_martial_npc({"name": "Kael", "role": "Mage", "description": "Battle wizard."}, scenario="fantasy"))
        
        # Fantasy civilian roles
        self.assertFalse(is_martial_npc({"name": "Donald", "role": "Blacksmith", "description": "Hammering horseshoes."}, scenario="fantasy"))
        self.assertFalse(is_martial_npc({"name": "Toby", "role": "Innkeeper", "description": "Cleaning mugs."}, scenario="fantasy"))
        self.assertFalse(is_martial_npc({"name": "Jack", "role": "Villager", "description": "Farming wheat."}, scenario="fantasy"))
        self.assertFalse(is_martial_npc({"name": "Rowan", "role": "Merchant", "description": "Selling fruits."}, scenario="fantasy"))

        # Veteran exception
        self.assertTrue(is_martial_npc({"name": "Jack", "role": "Farmer", "description": "Retired veteran of the Vanguard."}, scenario="fantasy"))

        # Non-combat genres (e.g. High School) are always non-martial
        self.assertFalse(is_martial_npc({"name": "Alex", "role": "Town Guard", "description": "Campus security."}, scenario="high_school_drama"))

    def test_get_recruitment_cost(self):
        from mechanics.social.relationships import get_recruitment_cost
        # Friend tier (>= 100): 0 gold
        self.assertEqual(get_recruitment_cost(100, level=1), 0)
        self.assertEqual(get_recruitment_cost(250, level=5), 0)
        
        # Stranger (0): Full base cost = 200 + level * 50 = 250 at lvl 1
        self.assertEqual(get_recruitment_cost(0, level=1), 250)
        # Stranger (< 0): Full base cost
        self.assertEqual(get_recruitment_cost(-30, level=1), 250)

        # Acquaintance (50): 50% discount = 125 at lvl 1
        self.assertEqual(get_recruitment_cost(50, level=1), 125)


if __name__ == "__main__":
    unittest.main()

