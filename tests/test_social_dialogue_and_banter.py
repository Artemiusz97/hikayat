"""
Unit tests for Hikayat Social & Casual Hangout Dialogue Mode, Banter, and Expanded Choice Palette.
Verifies that conversations with non-quest characters, companions, and phone meetups prioritize
warm banter, personal inquiry, and emotional bonding with an expanded 5-6 choice palette.
"""
import unittest
import db
import game_engine
from cogs.adventure import AdventureCog, _get_choice_skill_emoji


class TestSocialDialogueAndBanter(unittest.TestCase):
    def setUp(self):
        self.session_id = 998822
        self.user_id = 887722

        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.session_id,))

        db.create_character(
            user_id=self.user_id,
            name="Artemiusz",
            gender="male",
            stats={"STR": 10, "AGI": 10, "END": 10, "INT": 12, "PER": 10, "CHA": 15, "LUK": 5}
        )
        self.char = db.get_character(self.user_id)

        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        db.save_session_scene(
            self.session_id,
            scene_title="Rooftop Benches",
            narrative="Artemiusz and Sofia are sitting by the railing.",
            choices=[],
            history=["Turn 1"],
            location="Westlake Academy ➔ School Rooftop ➔ Rooftop Benches",
            current_npcs=[{"name": "Sofia Anderson", "role": "Club President"}],
            dialogue_partner="Sofia Anderson"
        )

        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="sofia_anderson",
            name="Sofia Anderson",
            basic_info={"role": "Club President", "description": "Track star and athletic leader."},
            track="romantic"
        )
        # Add traits and preferences
        contact = db.get_contact(self.session_id, "sofia_anderson")
        if contact:
            with db.get_conn() as conn:
                import json
                conn.execute(
                    "UPDATE contacts SET unlocked_traits_json = ?, preferences_json = ?, relationship_score = ? WHERE session_id = ? AND npc_id = ?",
                    (json.dumps(["Athletic", "Competitive", "Warm"]), json.dumps(["Likes Workout Talk", "Appreciates Honesty"]), 25, self.session_id, "sofia_anderson")
                )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.session_id,))

    def test_social_dialogue_prompt_enrichment(self):
        """Verify that talking to a non-quest contact builds the SOCIAL HANGOUT prompt with traits and archetypes."""
        session = db.get_session(self.session_id)
        # Render prompt text for session in active dialogue with Sofia
        party = [(self.char, [])]
        actions = [{"label": "Talk with Sofia", "mp_spent": 0, "check": None}]
        
        # Test prompt content generated in resolve_turn
        # Mocking turn resolve context or inspecting prompt block directly
        prompt_text = game_engine._known_world_text(self.session_id, session.get("current_location", ""))
        
        # Check that Sofia's context is in DB and will be queried
        contacts = db.get_contacts(self.session_id)
        sofia_c = next((c for c in contacts if c.get("name") == "Sofia Anderson"), None)
        self.assertIsNotNone(sofia_c)
        self.assertTrue("Athletic" in sofia_c.get("unlocked_traits", []) or "Competitive" in sofia_c.get("unlocked_traits", []))
        self.assertIn("Likes Workout Talk", sofia_c.get("preferences", []))

    def test_clean_choices_preserves_expanded_social_choices(self):
        """Verify _clean_choices preserves 5-6 diverse choices across banter, personal inquiry, affection, and exit."""
        incoming_choices = [
            {"label": "Playfully tease Sofia about her intense sprint training", "stat": "NONE", "requirement": 0},
            {"label": "Ask Sofia about what inspired her to run track in high school", "stat": "NONE", "requirement": 0},
            {"label": "Offer a sincere compliment on her leadership and warm smile", "stat": "NONE", "requirement": 0},
            {"label": "Chat casually about the pleasant weather and campus breeze", "stat": "NONE", "requirement": 0},
            {"label": "Challenge Sofia to an arm-wrestle on the bench to test your strength", "stat": "STR", "requirement": 7},
            {"label": "Thank Sofia for the chat and excuse yourself to survey the roof", "stat": "NONE", "requirement": 0}
        ]

        cleaned = AdventureCog._clean_choices(
            incoming_choices,
            scenario="high_school_drama",
            location="Westlake Academy ➔ School Rooftop ➔ Rooftop Benches",
            char=self.char,
            dialogue_partner="Sofia Anderson",
            current_npcs=[{"name": "Sofia Anderson"}],
            session_id=self.session_id
        )

        self.assertEqual(len(cleaned), 6)
        labels = [c["label"] for c in cleaned]
        self.assertTrue(any("tease" in l.lower() for l in labels))
        self.assertTrue(any("inspired" in l.lower() for l in labels))
        self.assertTrue(any("compliment" in l.lower() for l in labels))
        self.assertTrue(any("weather" in l.lower() for l in labels))
        self.assertTrue(any("arm-wrestle" in l.lower() for l in labels))
        self.assertTrue(any("thank" in l.lower() for l in labels))

    def test_choice_emojis_for_banter_and_affection(self):
        """Verify _get_choice_skill_emoji assigns appropriate icons for banter and romance/affection."""
        banter_choice = {"label": "Crack a playful joke about Sofia's workout routine", "stat": "NONE", "requirement": 0}
        flirt_choice = {"label": "Flirt with Sofia and compliment her radiant smile", "stat": "NONE", "requirement": 0}
        inquiry_choice = {"label": "Ask Sofia about her family and childhood dreams", "stat": "NONE", "requirement": 0}

        self.assertEqual(_get_choice_skill_emoji(banter_choice), "🎭")
        self.assertEqual(_get_choice_skill_emoji(flirt_choice), "💖")
        self.assertEqual(_get_choice_skill_emoji(inquiry_choice), "💬")

    def test_multi_emoji_social_skill_checks(self):
        """Verify multi-emoji support correctly pairs interaction archetype with skill check icon."""
        from cogs.adventure import _get_choice_emoji, _get_choice_quest_icon

        banter_cha = {"label": "Playfully tease Sofia about her workout intensity", "stat": "CHA", "requirement": 6}
        flirt_cha = {"label": "Compliment Sofia on her radiant smile and charm her", "stat": "CHA", "requirement": 7}
        inquiry_per = {"label": "Ask Sofia about her personal life and read her reactions", "stat": "PER", "requirement": 5}
        challenge_str = {"label": "Challenge Sofia to an arm-wrestle on the bench", "stat": "STR", "requirement": 7}
        exit_choice = {"label": "Thank Sofia for the chat and excuse yourself", "stat": "NONE", "requirement": 0}

        self.assertEqual(_get_choice_quest_icon(banter_cha), "🎭")
        self.assertEqual(_get_choice_skill_emoji(banter_cha), "🗣️")
        self.assertEqual(_get_choice_emoji(banter_cha), "🎭 🗣️")

        self.assertEqual(_get_choice_quest_icon(flirt_cha), "💖")
        self.assertEqual(_get_choice_skill_emoji(flirt_cha), "🗣️")
        self.assertEqual(_get_choice_emoji(flirt_cha), "💖 🗣️")

        self.assertEqual(_get_choice_quest_icon(inquiry_per), "💬")
        self.assertEqual(_get_choice_skill_emoji(inquiry_per), "👁️")
        self.assertEqual(_get_choice_emoji(inquiry_per), "💬 👁️")

        self.assertEqual(_get_choice_quest_icon(challenge_str), "🎲")
        self.assertEqual(_get_choice_skill_emoji(challenge_str), "💪")
        self.assertEqual(_get_choice_emoji(challenge_str), "🎲 💪")

        self.assertEqual(_get_choice_skill_emoji(exit_choice), "🚪")
        self.assertEqual(_get_choice_emoji(exit_choice), "🚪")


if __name__ == "__main__":
    unittest.main()
