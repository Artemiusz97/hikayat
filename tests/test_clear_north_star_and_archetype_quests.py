import os
import sys
import unittest
from unittest.mock import patch, AsyncMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
import game_engine
from cogs.adventure import AdventureCog


class TestClearNorthStarAndArchetypeQuests(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.test_session_id = 998822
        with db.get_conn() as conn:
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.test_session_id,))
            conn.commit()

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.test_session_id,))
            conn.commit()

    def test_clean_choices_preserves_north_star_choice_1_at_top(self):
        """Verify that Choice #1 (Quest / Travel / Delve action) remains at index 0 when active NPCs are present."""
        raw_choices = [
            {"label": "Set out toward the Silverwood Moonwell", "stat": "NONE", "requirement": 0},
            {"label": "Inspect the glowing contract board", "stat": "NONE", "requirement": 0},
            {"label": "Sit, drink, and review gear", "stat": "NONE", "requirement": 0}
        ]
        current_npcs = [
            {"name": "Mara Vey", "role": "Expedition Partner"},
            {"name": "Elderly Archivist", "role": "Scholar"}
        ]

        cleaned = AdventureCog._clean_choices(
            raw_choices,
            scenario="fantasy",
            location="Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table",
            current_npcs=current_npcs
        )

        # Choice 1 MUST be the North Star travel action
        self.assertEqual(cleaned[0]["label"], "Set out toward the Silverwood Moonwell")

        # Missing NPC choices must be placed directly after Choice 1
        labels = [c["label"] for c in cleaned]
        self.assertIn("Speak with Mara Vey (Expedition Partner)", labels)
        self.assertIn("Speak with Elderly Archivist (Scholar)", labels)

    def test_clean_choices_preserves_delve_threshold_choice_1(self):
        """Verify that a dungeon delving action stays at index 0 even when companions are present."""
        raw_choices = [
            {"label": "Step through the glowing archway into the awakening chamber", "stat": "END", "requirement": 5},
            {"label": "Decipher the ancient runes on the threshold", "stat": "INT", "requirement": 6},
            {"label": "Check map and mark the trail leading back toward Solaria", "stat": "NONE", "requirement": 0}
        ]
        current_npcs = [
            {"name": "Valerius Ironclad", "role": "Guardian"}
        ]

        cleaned = AdventureCog._clean_choices(
            raw_choices,
            scenario="fantasy",
            location="Solaria ➔ Silverwood Forest ➔ Moonwell Archway",
            current_npcs=current_npcs
        )

        self.assertEqual(cleaned[0]["label"], "Step through the glowing archway into the awakening chamber")
        labels = [c["label"] for c in cleaned]
        self.assertIn("Speak with Valerius Ironclad (Guardian)", labels)
        self.assertIn("Check map and mark the trail leading back toward Solaria", labels)

    @patch("game_engine.call_llm_json", new_callable=AsyncMock)
    async def test_generate_story_quest_injects_starting_hook_context(self, mock_llm):
        """Verify that Chapter 1 Story Quest prompt receives and integrates the starting hook context."""
        mock_llm.return_value = {
            "title": "Story Quest #1: The Awakening of the Moonwell",
            "archetype": "Investigation",
            "objective": "Investigate the ancient runic disturbance at the Silverwood Moonwell and stop the arcane resonance.",
            "sub_quests": [
                {
                    "id": 1,
                    "archetype": "Delve",
                    "text": "Breach the awakening inner chamber of the Moonwell",
                    "waypoints": [
                        {"stage_index": 1, "target_location": "Solaria -> Silverwood Forest", "stage_label": "Reach the archway", "completion_trigger": "arrival"},
                        {"stage_index": 2, "target_location": "Solaria -> Silverwood Forest", "stage_label": "Unseal the doorway", "completion_trigger": "skill_check"}
                    ]
                },
                {
                    "id": 2,
                    "archetype": "Investigation",
                    "text": "Consult Guildmaster Elira Voss at the Adventurers' Guild",
                    "waypoints": [
                        {"stage_index": 1, "target_location": "Solaria -> Adventurers' Guild Hall", "stage_label": "Report to the Guild", "completion_trigger": "arrival"}
                    ]
                },
                {
                    "id": 3,
                    "archetype": "Diplomacy",
                    "text": "Secure runic stabilizers at the Arcane Sanctum",
                    "waypoints": [
                        {"stage_index": 1, "target_location": "Solaria -> Arcane Sanctum", "stage_label": "Request stabilizers", "completion_trigger": "arrival"}
                    ]
                }
            ]
        }

        session = {
            "id": self.test_session_id,
            "scenario": "fantasy",
            "current_location": "Solaria ➔ Silverwood Forest ➔ Moonwell Archway"
        }

        hook_ctx = {
            "archetype": "delve_threshold",
            "archetype_title": "Delve Threshold",
            "hook_text": "Begin outside the ancient Silverwood Moonwell as runes begin to glow.",
            "suggested_location": "Solaria ➔ Silverwood Forest ➔ Moonwell Archway",
            "opening_narrative": "The oldest trees of the Silverwood lean over the broken basin...",
            "scene_title": "The Moonwell Awakens"
        }

        res = await game_engine.generate_story_quest(
            self.test_session_id,
            session,
            chapter_num=1,
            starting_hook_context=hook_ctx
        )

        self.assertEqual(res["title"], "Story Quest #1: The Awakening of the Moonwell")
        self.assertEqual(len(res["sub_objectives"]), 3)

        # Check user prompt passed to LLM
        call_args = mock_llm.call_args[0]
        user_prompt = call_args[1]

        self.assertIn("OPENING INCITING INCIDENT [Delve Threshold]", user_prompt)
        self.assertIn("The Moonwell Awakens", user_prompt)
        self.assertIn("DIRECTIVE FOR CHAPTER 1 QUEST", user_prompt)


if __name__ == "__main__":
    unittest.main()
