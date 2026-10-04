import unittest
from unittest.mock import patch, AsyncMock
import db
import game_engine

class MockCheck:
    succeeded = True
    is_success = True
    tier = "success"
    chance = 90

class TestIntimateLLMInjection(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        db.init_db()
        self.session_id = 88776655
        self.user_id = 99887711

        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))

        db.create_character(user_id=self.user_id, name="Protagonist", gender="male")
        self.char = db.get_character(self.user_id)
        self.session_id = db.create_session(self.user_id, "solo", 1, "vivid", "individual", False, scenario="nsfw_high_school_drama")

        self.contact_npc = {
            "session_id": self.session_id,
            "character_id": self.char["id"],
            "npc_id": "maya_anderson",
            "name": "Maya Anderson",
            "relationship_score": 10,
            "track": "romantic",
            "race": "Fox-Beastfolk",
            "gender": "female",
            "traits": ["Ambitious"],
            "preferences": ["Logistics"],
            "mannerisms": "Twitches ears",
            "appearance": {
                "breast_size": "plump",
                "predetermined_intercourse_experience": "virgin",
                "intimate_demeanor": "Secretly Teasing",
                "intimate_dynamic": "Switch / Sensual",
                "sensitive_spots": "Base of tail, ear tips",
                "turn_ons": "Whispered praise, ear nibbling",
                "fetishes": "Sensory deprivation"
            }
        }
        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="maya_anderson",
            name="Maya Anderson",
            track="romantic",
            appearance=self.contact_npc["appearance"]
        )

        db.save_session_scene(
            session_id=self.session_id,
            scene_title="Classroom",
            narrative="Maya Anderson is organizing club paperwork.",
            choices=[],
            history=["Turn 1"],
            location="Westlake Academy ➔ Student Council",
            current_npcs=[{"name": "Maya Anderson", "role": "Council Member"}],
            dialogue_partner="Maya Anderson"
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))

    async def test_llm_prompt_injects_undiscovered_intimate_info_at_level_1(self):
        """Verify that at low affinity, intimate details are still injected to shape behavior."""
        session = db.get_session(self.session_id)
        actions = [{
            "char": self.char,
            "label": "Chat with Maya Anderson about council records",
            "stat": "CHA",
            "check": MockCheck(),
            "mp_spent": 0
        }]

        with patch("game_engine.call_llm_json", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "outcome_narrative": "You chat with Maya.",
                "next_narrative": "Maya smiles politely.",
                "next_choices": [{"label": "Continue conversation", "stat": "CHA", "requirement": 5}]
            }
            await game_engine.resolve_turn(session, [(self.char, [])], actions)

            self.assertTrue(mock_call.called)
            user_prompt = mock_call.call_args_list[0][0][1]

            # Demeanor and dynamic are present
            self.assertIn("Intimate Demeanor: Secretly Teasing", user_prompt)
            self.assertIn("Intimate Dynamic: Switch / Sensual", user_prompt)

            # Undiscovered sensitive spots and turn-ons ARE now leaked to the LLM so it can shape behavior!
            self.assertIn("Sensitive Spots: Base of tail, ear tips", user_prompt)
            self.assertIn("Turn-Ons: Whispered praise, ear nibbling", user_prompt)
            self.assertIn("Kinks: Sensory deprivation", user_prompt)

    async def test_llm_prompt_injects_specific_revealed_flag_at_level_1(self):
        """Verify that if a specific flag is revealed (e.g. sensitive_spots_revealed), it gets injected even at level 1."""
        app_with_flag = dict(self.contact_npc["appearance"])
        app_with_flag["sensitive_spots_revealed"] = True
        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="maya_anderson",
            name="Maya Anderson",
            appearance=app_with_flag
        )

        session = db.get_session(self.session_id)
        actions = [{
            "char": self.char,
            "label": "Chat with Maya Anderson",
            "stat": "CHA",
            "check": MockCheck(),
            "mp_spent": 0
        }]

        with patch("game_engine.call_llm_json", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = {
                "outcome_narrative": "Success",
                "next_narrative": "Next",
                "next_choices": []
            }
            await game_engine.resolve_turn(session, [(self.char, [])], actions)

            self.assertTrue(mock_call.called)
            user_prompt = mock_call.call_args_list[0][0][1]


            # Sensitive spots was revealed -> injected!
            self.assertIn("Sensitive Spots: Base of tail, ear tips", user_prompt)
            # Turn-ons is now also injected unconditionally to shape personality
            self.assertIn("Turn-Ons: Whispered praise, ear nibbling", user_prompt)

if __name__ == "__main__":
    unittest.main()
