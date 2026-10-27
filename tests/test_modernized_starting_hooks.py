import unittest
from unittest.mock import patch, AsyncMock
import db
import scenario_data
import game_engine
from mechanics.narrative.image_prompt_composer import compose_turn_image_prompt


class TestModernizedStartingHooks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.session_id = 98765432
        self.user_id = 12345678
        with db.get_conn() as conn:
            conn.execute("DELETE FROM inventory WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM actor_physical_states WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE id = 99999")
            conn.execute(
                "INSERT OR REPLACE INTO characters (id, user_id, name, char_class, str_, per_, end_, cha, int_, agi, luk) "
                "VALUES (99999, ?, 'Kaelen', 'Warrior', 5, 5, 5, 5, 5, 5, 5)",
                (self.user_id,)
            )
            conn.commit()

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM inventory WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM actor_physical_states WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE id = 99999")
            conn.commit()

    def test_all_primary_setting_genres_have_modernized_fields(self):
        """Verify that every starting hook across all 8 primary genres has the complete modernized schema."""
        genres = scenario_data.load_genres(reload=True)
        required_fields = (
            "archetype", "starting_minute", "hook", "suggested_location",
            "directive", "focal_point", "scheduled_roles",
            "initial_physical_state", "starting_prop", "visual_cues"
        )
        
        for genre_key in scenario_data.PRIMARY_SETTING_TAGS:
            genre_data = genres.get(genre_key, {})
            hooks = genre_data.get("starting_hooks", [])
            self.assertGreaterEqual(len(hooks), 6 if genre_key != "high_school" and genre_key != "fantasy" else 9 if genre_key == "high_school" else 15,
                                    f"Genre '{genre_key}' does not meet expected hook count.")
            for idx, h in enumerate(hooks):
                for field in required_fields:
                    self.assertIn(field, h, f"Hook {idx} in genre '{genre_key}' missing required field '{field}'.")
                
                self.assertIsInstance(h["starting_minute"], int)
                self.assertTrue(0 <= h["starting_minute"] < 1440)
                self.assertIsInstance(h["focal_point"], str)
                self.assertTrue(len(h["focal_point"]) > 0)
                self.assertIsInstance(h["scheduled_roles"], list)
                self.assertGreaterEqual(len(h["scheduled_roles"]), 1)
                self.assertIsInstance(h["initial_physical_state"], dict)
                self.assertIn("posture", h["initial_physical_state"])
                self.assertIn("composure", h["initial_physical_state"])
                self.assertIsInstance(h["starting_prop"], dict)
                self.assertIn("name", h["starting_prop"])
                self.assertIsInstance(h["visual_cues"], str)
                self.assertTrue(len(h["visual_cues"]) > 0)

    def test_dark_fantasy_scenario_override_has_modernized_fields(self):
        """Verify that dark_fantasy scenario override in scenarios.json has all 6 modernized hooks."""
        scenarios = scenario_data.load_scenarios(reload=True)
        df_hooks = scenarios["dark_fantasy"].get("starting_hooks", [])
        self.assertEqual(len(df_hooks), 6)
        for h in df_hooks:
            self.assertIn("starting_minute", h)
            self.assertIn("focal_point", h)
            self.assertIn("scheduled_roles", h)
            self.assertIn("initial_physical_state", h)
            self.assertIn("starting_prop", h)
            self.assertIn("visual_cues", h)

    def test_get_dynamic_starting_hook_resolves_all_modernized_attributes(self):
        """Verify get_dynamic_starting_hook returns populated modernized fields for any scenario."""
        for scen_key in ("fantasy", "cyberpunk", "sci_fi", "steampunk", "dark_fantasy", "high_school_drama"):
            hook_info = scenario_data.get_dynamic_starting_hook(scen_key, session_id=self.session_id, char_name="Kaelen")
            self.assertIn("archetype", hook_info)
            self.assertIn("starting_minute", hook_info)
            self.assertIsNotNone(hook_info["starting_minute"])
            self.assertIn("focal_point", hook_info)
            self.assertTrue(len(hook_info["focal_point"]) > 0)
            self.assertIn("scheduled_roles", hook_info)
            self.assertGreaterEqual(len(hook_info["scheduled_roles"]), 1)
            self.assertIn("initial_physical_state", hook_info)
            self.assertIn("starting_prop", hook_info)
            self.assertIsNotNone(hook_info["starting_prop"])
            self.assertIn("visual_cues", hook_info)
            self.assertTrue(len(hook_info["visual_cues"]) > 0)

    @patch("game_engine.call_llm_json", new_callable=AsyncMock)
    async def test_generate_opening_scene_wires_clock_focal_point_npcs_and_prop(self, mock_llm):
        """Verify generate_opening_scene updates session focal point, stages NPCs, gives prop, and sets visual cues."""
        mock_llm.return_value = {
            "scene_title": "The Awakening",
            "narrative": "You open your eyes as the morning light spills over the counter.",
            "choices": [{"id": 1, "text": "Inspect the surrounding area", "stat": "PER"}],
            "location": "Imperial Capital ➔ Central Market ➔ Grand Fountain",
            "focal_point": "Beside the stone fountain rim",
            "story_quest": {
                "quest_id": "SQ-01",
                "title": "A New Beginning",
                "objective": "Investigate the local rumors",
                "narrative_hook": "A mysterious rumor spreads."
            }
        }
        
        session = {
            "id": self.session_id,
            "scenario": "cyberpunk",
            "current_location": "",
            "current_day": 1,
            "current_minute": 480,
            "history": [],
            "current_npcs": []
        }
        with db.get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (id, mode, capacity, current_day, current_minute, current_location, current_npcs_json) "
                "VALUES (?, 'solo', 1, 1, 480, '', '[]')",
                (self.session_id,)
            )
            conn.commit()

        char = {"id": 99999, "user_id": self.user_id, "name": "Kaelen", "gender": "male"}
        party = [(char, [])]

        res = await game_engine.turn.generation.generate_opening_scene(session, party)
        self.assertIsNotNone(res)

        # 1. Clock updated
        _, updated_min, _ = db.get_session_time(self.session_id)
        self.assertNotEqual(updated_min, 480) # Cyberpunk starts at 1230, 720, 1425, 1095, 180, or 90

        # 2. Focal point persisted on session
        sess_db = db.get_session(self.session_id)
        self.assertTrue(len(sess_db.get("focal_point", "")) > 0)

        # 3. Scheduled NPCs staged in current_npcs
        curr_npcs = sess_db.get("current_npcs") or []
        self.assertGreaterEqual(len(curr_npcs), 1)

        # 4. Starting prop added to player inventory
        items = db.get_inventory(self.user_id)
        self.assertGreaterEqual(len(items), 1)
        prop_item = items[0]
        self.assertTrue(len(prop_item["name"]) > 0)

        # 5. Visual cues injected into compose_turn_image_prompt
        composed = compose_turn_image_prompt(session, outcome=res)
        self.assertTrue(len(composed.prompt) > 0)
        self.assertTrue(any(word in composed.prompt.lower() for word in ("neon", "cyber", "rain", "lounge", "terminal", "vault", "booth", "alley")))


if __name__ == "__main__":
    unittest.main()
