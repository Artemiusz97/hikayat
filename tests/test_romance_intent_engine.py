import unittest
import db
from mechanics.social.relationships import (
    is_romantic_confession_intent,
    can_trigger_romantic_confession,
    get_relationship_tier,
)


class TestRomanceIntentEngine(unittest.TestCase):
    def setUp(self):
        self.user_id = 992288
        self.char_name = "Artemiusz"
        self.npc_name = "Maya Anderson"
        self.scenario = "high_school_drama"

        db.init_db()
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
        self.char_info = db.create_character(
            user_id=self.user_id,
            name=self.char_name,
            gender="male",
            scenario=self.scenario
        )
        self.char_dict = db.get_character(self.user_id)
        self.char_id = self.char_dict["id"]
        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False,
            scenario=self.scenario
        )
        with db.get_conn() as conn:
            conn.execute("UPDATE sessions SET dialogue_partner = ? WHERE id = ?", (self.npc_name, self.session_id))

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))

    def test_layer1_and_layer2_intent_classifier(self):
        """Verify Layer 1 structural regex patterns and Layer 2 negative disambiguation filters."""
        # Layer 1 Positive Matches
        positives = [
            "Ask her if she would like to pursue a relationship with you",
            "Artemiusz asks Maya if she would like to pursue a romantic relationship with him",
            "Confess your feelings and ask her to be your girlfriend",
            "Tell her you want to take things to the next level",
            "Ask if she wants to start dating officially",
            "Ask her to be more than friends",
            "Confess your love to her under the cherry blossoms",
            "Admit your romantic feelings for her",
            "Ask if she wants to become romantically involved",
            "Give this a chance and date each other",
        ]
        for phrase in positives:
            self.assertTrue(is_romantic_confession_intent(phrase), f"Failed to recognize positive confession: '{phrase}'")

        # Layer 2 Negative Disambiguation / False-Positive Guards
        negatives = [
            "Maintain a strictly professional and working relationship with the client",
            "Ask about her relationship with the student council president",
            "We have a strong platonic relationship as study buddies",
            "I don't want to pursue a relationship right now",
            "Refuse to date or enter a relationship with him",
            "Investigate rumors about their relationship",
            "Discuss their strained business relationship",
            "Ask the teacher about the homework assignment",
        ]
        for phrase in negatives:
            self.assertFalse(is_romantic_confession_intent(phrase), f"False positive triggered on non-romantic phrase: '{phrase}'")

    def test_confession_prerequisites(self):
        """Verify the 6 prerequisite gates of can_trigger_romantic_confession."""
        # 1. Low Affinity (< 70) -> Should NOT trigger
        db.upsert_contact(self.session_id, "maya_anderson", self.npc_name, delta_score=50, track="platonic")
        self.assertFalse(can_trigger_romantic_confession(self.session_id, self.char_id, self.npc_name, self.scenario))

        # 2. High Affinity (>= 70, platonic) -> SHOULD trigger
        db.upsert_contact(self.session_id, "maya_anderson", self.npc_name, delta_score=30, track="platonic") # score = 80
        self.assertTrue(can_trigger_romantic_confession(self.session_id, self.char_id, self.npc_name, self.scenario))

        # 3. Already on Romantic track -> Should NOT trigger (already dating)
        db.upsert_contact(self.session_id, "maya_anderson", self.npc_name, track="romantic")
        self.assertFalse(can_trigger_romantic_confession(self.session_id, self.char_id, self.npc_name, self.scenario))

        # 4. Ineligible NPC (Teacher / Adult) -> Should NOT trigger
        db.upsert_contact(self.session_id, "mr_harrison", "Mr. Harrison", delta_score=80, track="platonic")
        self.assertFalse(can_trigger_romantic_confession(self.session_id, self.char_id, "Mr. Harrison", self.scenario))

        # 5. Cooldown Active -> Should NOT trigger
        db.upsert_contact(self.session_id, "maya_anderson", self.npc_name, track="platonic")
        db.set_confession_cooldown(self.session_id, self.npc_name, turns=3)
        self.assertFalse(can_trigger_romantic_confession(self.session_id, self.char_id, self.npc_name, self.scenario))

    def test_dedicated_choice_auto_injection(self):
        """Verify that _clean_choices auto-injects the dedicated romance milestone action."""
        from cogs.adventure import AdventureCog
        db.upsert_contact(self.session_id, "maya_anderson", self.npc_name, delta_score=85, track="platonic")

        raw_choices = [
            {"label": "Discuss today's chemistry assignment", "stat": "INT", "requirement": 6, "mp_cost": 0},
            {"label": "Share a pastry and chat about the festival", "stat": "CHA", "requirement": 5, "mp_cost": 0},
            {"label": f"Thank {self.npc_name}, excuse yourself, and look around the room", "stat": "NONE", "requirement": 0, "mp_cost": 0},
        ]

        cleaned = AdventureCog._clean_choices(
            raw_choices,
            scenario=self.scenario,
            char=self.char_dict,
            dialogue_partner=self.npc_name,
            session_id=self.session_id
        )

        # Assert dedicated confession choice is present with intent and target_npc
        conf_choice = next((c for c in cleaned if c.get("intent") == "romantic_confession"), None)
        self.assertIsNotNone(conf_choice, "Dedicated confession choice was not auto-injected!")
        self.assertEqual(conf_choice.get("target_npc"), self.npc_name)
        self.assertIn("Confess your feelings", conf_choice.get("label", ""))

    def test_mechanical_track_transition_on_successful_action(self):
        """Verify that selecting the confession choice with check success transitions track to romantic."""
        db.upsert_contact(self.session_id, "maya_anderson", self.npc_name, delta_score=95, track="platonic")

        selected_action = [{
            "label": f"Confess your feelings and ask {self.npc_name} to pursue a romantic relationship",
            "stat": "CHA",
            "requirement": 8,
            "mp_cost": 0,
            "intent": "romantic_confession",
            "target_npc": self.npc_name,
            "check": {"succeeded": True, "roll": 15, "total": 19, "requirement": 8, "tier": "success"}
        }]

        mock_llm_result = {
            "scene_title": "A Heartfelt Confession",
            "outcome_narrative": "Maya's breath catches as Artemiusz confesses his feelings. Her face flushes crimson and her golden ears twitch with pure joy.",
            "next_narrative": "She takes his hands in hers, nodding eagerly. 'I want that more than anything, Artemiusz.'",
            "location": "Sakura Hill Residential Town ➔ Anderson Residence ➔ Foyer",
            "relationship_updates": [{"npc_name": self.npc_name, "delta_score": 5}],
            "next_choices": [
                {"label": "Hold her close and share a tender embrace", "stat": "CHA", "requirement": 6, "mp_cost": 0}
            ]
        }

        # Resolve turn through engine pipeline
        from game_engine import apply_outcome
        apply_outcome(
            self.session_id,
            [(self.char_dict, [])],
            mock_llm_result,
            actions=selected_action
        )

        # Verify SQLite contact was mechanically switched to romantic
        contact = db.get_contact(self.session_id, self.npc_name, self.char_id)
        self.assertEqual(contact.get("track"), "romantic")
        self.assertEqual(contact.get("relationship_score"), 100)

        # Verify tier is Lover / Partner
        tier = get_relationship_tier(contact["relationship_score"], contact["track"], self.scenario)
        self.assertEqual(tier["name"], "Lover / Partner")

    def test_failed_confession_sets_cooldown(self):
        """Verify that a failed confession check keeps track platonic and sets a 3-turn cooldown."""
        db.upsert_contact(self.session_id, "maya_anderson", self.npc_name, delta_score=85, track="platonic")

        selected_action = [{
            "label": f"Confess your feelings and ask {self.npc_name} to pursue a romantic relationship",
            "stat": "CHA",
            "requirement": 8,
            "mp_cost": 0,
            "intent": "romantic_confession",
            "target_npc": self.npc_name,
            "check": {"succeeded": False, "roll": 2, "total": 4, "requirement": 8, "tier": "failure"}
        }]

        mock_llm_result = {
            "scene_title": "An Awkward Hesitation",
            "outcome_narrative": "Maya blushes nervously, caught off guard. 'Artemiusz, you're a great friend, but I need some time to process this.'",
            "next_narrative": "An awkward silence falls over the foyer.",
            "location": "Sakura Hill Residential Town ➔ Anderson Residence ➔ Foyer",
            "relationship_updates": [{"npc_name": self.npc_name, "delta_score": -1}],
            "next_choices": [
                {"label": "Apologize and change the subject", "stat": "CHA", "requirement": 5, "mp_cost": 0}
            ]
        }

        from game_engine import apply_outcome
        apply_outcome(
            self.session_id,
            [(self.char_dict, [])],
            mock_llm_result,
            actions=selected_action
        )

        # Verify contact remained platonic
        contact = db.get_contact(self.session_id, self.npc_name, self.char_id)
        self.assertEqual(contact.get("track"), "platonic")

        # Verify 3-turn cooldown is active in database
        self.assertEqual(db.get_confession_cooldown(self.session_id, self.npc_name), 3)


if __name__ == "__main__":
    unittest.main()
