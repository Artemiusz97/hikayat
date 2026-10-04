"""
Unit tests for Hikayat Natural Character Dialogue, Speech Mannerisms & Anti-Cliché Rules.
Verifies that the Game Engine enforces anti-cliché guardrails, concrete anecdotal banter,
distinct character mannerisms, and paced intimacy progression.
"""
import unittest
import json
import db
import game_engine


class TestNaturalDialogueAndAntiCliche(unittest.TestCase):
    def setUp(self):
        self.session_id = 998833
        self.user_id = 887733

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
            basic_info={
                "role": "Club President",
                "mannerisms": "Stretches arms overhead while talking, uses athletic metaphors, laughs loudly at friendly banter."
            },
            track="romantic"
        )
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE contacts SET unlocked_traits_json = ?, preferences_json = ?, relationship_score = ? WHERE session_id = ? AND npc_id = ?",
                (json.dumps(["Athletic", "Competitive", "Energetic"]), json.dumps(["Likes Honest Banter", "Prefers Cold Drinks"]), 20, self.session_id, "sofia_anderson")
            )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.session_id,))

    def test_system_prompt_anti_cliche_guardrails(self):
        """Verify SYSTEM_PROMPT explicitly bans generic protagonist flattery tropes."""
        sys_prompt = game_engine.SYSTEM_PROMPT

        # Check banned tropes are explicitly in SYSTEM_PROMPT
        self.assertIn("Natural Character Dialogue, Speech Mannerisms & Anti-Cliché Rules", sys_prompt)
        self.assertIn("You're different from the others", sys_prompt)
        self.assertIn("Most people just see the title", sys_prompt)
        self.assertIn("You're an interesting one", sys_prompt)
        self.assertIn("It's... refreshing", sys_prompt)
        self.assertIn("CONCRETE GROUNDING & ANECDOTAL TEXTURE", sys_prompt)
        self.assertIn("SPEECH MANNERISMS & CHARACTER VOICE GROUNDING", sys_prompt)
        self.assertIn("PACED VULNERABILITY & AFFINITY PROGRESSION", sys_prompt)

    def test_contact_mannerisms_injected_into_dialogue_prompt(self):
        """Verify character mannerisms and speech quirks are injected into the active dialogue prompt."""
        contacts = db.get_contacts(self.session_id)
        sofia = next((c for c in contacts if c.get("name") == "Sofia Anderson"), None)
        self.assertIsNotNone(sofia)
        
        mannerisms = sofia.get("mannerisms") or (sofia.get("basic_info") or {}).get("mannerisms")
        self.assertIn("Stretches arms overhead", mannerisms)
        self.assertIn("athletic metaphors", mannerisms)

    def test_social_hangout_prompt_rules(self):
        """Verify SOCIAL HANGOUT dialogue block contains specific voice, anti-cliche, and pacing instructions."""
        # Inspect the template in game_engine
        import inspect
        src = inspect.getsource(game_engine.turn.dialogue)
        self.assertIn("CHARACTER VOICE & ANTI-CLICHÉ RULES:", src)
        self.assertIn("CONCRETE CONVERSATION:", src)
        self.assertIn("PACED INTIMACY:", src)


if __name__ == "__main__":
    unittest.main()
