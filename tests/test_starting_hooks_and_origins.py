import os
import sys
import unittest
from unittest.mock import MagicMock, patch, AsyncMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
import scenario_data
import mechanics.world.locations as locs
import game_engine


class TestStartingHooksAndOrigins(unittest.TestCase):

    def setUp(self):
        self.test_session_id = 998811
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.test_session_id,))
            conn.commit()

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.test_session_id,))
            conn.commit()

    def test_all_setting_tags_have_three_structured_starting_archetypes(self):
        """Verify that every primary setting tag in data/tags.json contains structured hooks covering all 3 archetypes."""
        tags_data = scenario_data.load_tags(reload=True)
        required_archetypes = {"hub_launchpad", "in_media_res", "delve_threshold"}

        for tag_key in scenario_data.PRIMARY_SETTING_TAGS:
            tag_info = tags_data.get(tag_key, {})
            hooks = tag_info.get("starting_hooks", [])
            self.assertGreaterEqual(len(hooks), 3, f"Primary setting tag '{tag_key}' should have at least 3 starting hooks.")
            
            found_archetypes = set()
            for h in hooks:
                self.assertIsInstance(h, dict, f"Hook in tag '{tag_key}' should be a structured dict.")
                self.assertIn("archetype", h, f"Hook in tag '{tag_key}' missing 'archetype'.")
                self.assertIn("hook", h, f"Hook in tag '{tag_key}' missing 'hook'.")
                self.assertIn("suggested_location", h, f"Hook in tag '{tag_key}' missing 'suggested_location'.")
                self.assertIn("directive", h, f"Hook in tag '{tag_key}' missing 'directive'.")
                found_archetypes.add(h["archetype"])

            for req in required_archetypes:
                self.assertIn(req, found_archetypes, f"Primary setting tag '{tag_key}' missing required archetype '{req}'.")

    def test_procedural_location_token_resolution(self):
        """Verify that resolve_session_location_tokens converts procedural tokens into unique session-seeded names."""
        template_fantasy = "{session_kingdom} ➔ The Boar's Tusk Tavern ➔ Hearthside Table"
        resolved_fantasy_1 = locs.resolve_session_location_tokens(
            session_id=101, template=template_fantasy, scenario_key="fantasy"
        )
        resolved_fantasy_2 = locs.resolve_session_location_tokens(
            session_id=202, template=template_fantasy, scenario_key="fantasy"
        )

        self.assertNotIn("{session_kingdom}", resolved_fantasy_1)
        self.assertNotIn("{session_kingdom}", resolved_fantasy_2)
        self.assertIn("The Boar's Tusk Tavern", resolved_fantasy_1)
        self.assertIn("The Boar's Tusk Tavern", resolved_fantasy_2)

        # High school template
        template_school = "{session_school} ➔ Central Courtyard ➔ Sakura Fountain"
        resolved_school = locs.resolve_session_location_tokens(
            session_id=303, template=template_school, scenario_key="high_school_drama"
        )
        self.assertNotIn("{session_school}", resolved_school)
        self.assertIn("Central Courtyard", resolved_school)

        # Cyberpunk template
        template_cyber = "{session_cyber_city} ➔ The Wiretap Lounge ➔ VIP Synth Booth"
        resolved_cyber = locs.resolve_session_location_tokens(
            session_id=404, template=template_cyber, scenario_key="cyberpunk"
        )
        self.assertNotIn("{session_cyber_city}", resolved_cyber)
        self.assertIn("The Wiretap Lounge", resolved_cyber)

    def test_get_dynamic_starting_hook_across_all_scenarios(self):
        """Verify get_dynamic_starting_hook works for all standard scenarios and returns valid dicts."""
        scenarios = scenario_data.load_scenarios(reload=True)
        
        for scen_key, scen_data in scenarios.items():
            hook_info = scenario_data.get_dynamic_starting_hook(
                scenario=scen_data, session_id=self.test_session_id, char_name="Hero"
            )
            self.assertIn("archetype", hook_info)
            self.assertIn(hook_info["archetype"], ("hub_launchpad", "in_media_res", "delve_threshold"))
            self.assertTrue(hook_info["hook_text"].startswith("Begin"))
            self.assertIn("directive", hook_info)
            self.assertTrue(len(hook_info["directive"]) > 10)
            
            # Suggested location should be resolved (no leftover curly bracket tokens)
            suggested_loc = hook_info.get("suggested_location", "")
            self.assertNotIn("{session_", suggested_loc)

    @patch("game_engine.call_llm_json")
    def test_generate_opening_scene_incorporates_archetype_directive(self, mock_llm):
        """Verify generate_opening_scene injects archetype directives into prompts and reconciles locations."""
        import asyncio
        mock_llm.return_value = {
            "title": "A New Journey",
            "narrative": "You step into the lively hall and look around.",
            "location": "Aethelgard ➔ The Boar's Tusk Tavern ➔ Hearthside Table",
            "npcs_present": ["Elian Voss"],
            "next_choices": [
                {"label": "Talk to Elian", "stat": "CHA", "requirement": 5},
                {"label": "Inspect notice board", "stat": "PER", "requirement": 5},
                {"label": "Sit and rest", "stat": "NONE", "requirement": 0}
            ],
            "story_quest": {
                "quest_id": "sq_ch1",
                "title": "The First Contract",
                "objective": "Investigate the mysterious disappearance"
            }
        }

        session = {
            "id": self.test_session_id,
            "scenario": "fantasy",
            "history": []
        }
        party = [({"id": 1, "user_id": 12345, "name": "Alice", "class": "Mage", "str_": 5, "agi_": 5, "int_": 10}, [])]

        res = asyncio.run(game_engine.generate_opening_scene(session, party))
        self.assertIsInstance(res, dict)
        self.assertEqual(res["title"], "A New Journey")
        self.assertIn("Aethelgard", res["location"])

        # Inspect LLM prompt call arguments from the opening scene generation call
        first_call = mock_llm.call_args_list[0]
        sys_prompt_arg, user_prompt_arg = first_call[0][0], first_call[0][1]
        self.assertIn("OPENING INCITING INCIDENT", user_prompt_arg)
        self.assertIn("ARCHETYPE DIRECTIVE", user_prompt_arg)
        self.assertIn("OPENING CHOICE DIRECTIVE", user_prompt_arg)


if __name__ == "__main__":
    unittest.main()
