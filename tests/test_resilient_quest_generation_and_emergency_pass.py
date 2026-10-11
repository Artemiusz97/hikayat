import unittest
from unittest.mock import patch, AsyncMock, MagicMock
import asyncio
import db
import game_engine

class TestResilientQuestGenerationAndEmergencyPass(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.session_id = db.create_session(
            host_user_id=88881,
            mode="solo",
            capacity=1,
            verbosity="vivid",
            dialogue_mode="individual",
            image_gen_enabled=False,
            scenario="fantasy"
        )
        self.session = db.get_session(self.session_id)

    def tearDown(self):
        pass

    async def test_generate_story_quest_pass1_success(self):
        """Verify Pass 1 succeeds when LLM responds normally."""
        mock_response = {
            "title": "The Whispering Glade",
            "archetype": "Mystery",
            "objective": "Investigate the arcane disturbances stirring in the glade.",
            "sub_quests": [
                {"id": 1, "archetype": "Investigation", "text": "Inspect the glowing monolith"},
                {"id": 2, "archetype": "Infiltration", "text": "Slip past the boundary wards"},
                {"id": 3, "archetype": "Diplomacy", "text": "Consult the grove warden"}
            ]
        }
        with patch("game_engine.call_llm_json", new=AsyncMock(return_value=mock_response)) as mock_llm:
            res = await game_engine.generate_story_quest(self.session_id, self.session, chapter_num=1)
            self.assertEqual(res["title"], "The Whispering Glade")
            self.assertEqual(len(res["sub_objectives"]), 3)
            self.assertEqual(mock_llm.call_count, 1)

    async def test_generate_story_quest_pass2_emergency_pass_triggered_on_pass1_failure(self):
        """Verify Emergency Pass 2 is triggered when Pass 1 raises an exception or times out."""
        emergency_response = {
            "title": "Emergency Quest: The Breach",
            "archetype": "Emergency",
            "objective": "Contain the sudden regional rift before it expands.",
            "sub_quests": [
                {"id": 1, "archetype": "Investigation", "text": "Analyze the energy fluctuations"},
                {"id": 2, "archetype": "Infiltration", "text": "Enter the quarantined perimeter"},
                {"id": 3, "archetype": "Diplomacy", "text": "Coordinate with defense sentinels"}
            ]
        }

        # First call fails (Pass 1), second call succeeds (Emergency Pass 2)
        mock_llm = AsyncMock(side_effect=[RuntimeError("Pass 1 API Timeout"), emergency_response])
        with patch("game_engine.call_llm_json", new=mock_llm):
            res = await game_engine.generate_story_quest(self.session_id, self.session, chapter_num=1)
            self.assertEqual(res["title"], "Emergency Quest: The Breach")
            self.assertEqual(len(res["sub_objectives"]), 3)
            self.assertEqual(mock_llm.call_count, 2)
            # Verify Pass 2 was called with temperature=0.7 and use_utility=False
            call2_kwargs = mock_llm.call_args_list[1].kwargs
            self.assertEqual(call2_kwargs.get("temperature"), 0.7)
            self.assertFalse(call2_kwargs.get("use_utility"))

    async def test_generate_story_quest_pass3_deterministic_fallback_when_all_llm_passes_fail(self):
        """Verify Pass 3 produces a rich contextual quest with 3 sub-quests and waypoints when all LLM calls fail."""
        mock_llm = AsyncMock(side_effect=RuntimeError("Network unreachable"))
        with patch("game_engine.call_llm_json", new=mock_llm):
            res = await game_engine.generate_story_quest(
                self.session_id,
                self.session,
                chapter_num=1,
                starting_hook_context={"archetype": "delve_threshold", "archetype_title": "Delve Threshold"}
            )
            self.assertIsNotNone(res)
            self.assertIn("Delve Threshold", res["title"])
            self.assertEqual(len(res["sub_objectives"]), 3)
            self.assertEqual(len(res["sub_waypoints"]), 3)
            for so in res["sub_objectives"]:
                self.assertTrue(len(so["text"]) > 10)
                self.assertIn(so["id"], res["sub_waypoints"])
                self.assertEqual(len(res["sub_waypoints"][so["id"]]), 3)

    def test_ensure_story_quest_exists_self_heals_blank_generic_quest(self):
        """Verify ensure_story_quest_exists self-heals any quest with 0 sub-objectives or generic placeholder title."""
        # Insert a broken generic placeholder quest with 0 sub-objectives
        db.upsert_quest(
            session_id=self.session_id,
            quest_id="SQ-BROKEN-01",
            quest_type="Story Quest",
            title="Story Quest #1: A New Adventure Begins",
            objective="Explore the area and uncover what dangers or mysteries await.",
            progress="Quest #1",
            current_clues="",
            status="Active",
            reward_xp=250,
            reward_gold=60,
            is_story_quest=1,
            clues_required=3,
            sub_objectives=[]
        )

        healed = game_engine.ensure_story_quest_exists(self.session)
        self.assertIsNotNone(healed)
        self.assertNotEqual(healed["title"], "Story Quest #1: A New Adventure Begins")
        self.assertGreaterEqual(len(healed.get("sub_objectives", [])), 3)

        # Check DB also has the healed quest
        in_db = db.get_active_story_quest(self.session_id)
        self.assertIsNotNone(in_db)
        self.assertEqual(len(in_db["sub_objectives"]), 3)

    def test_get_active_story_quest_prioritizes_non_empty_over_blank(self):
        """Verify db.get_active_story_quest prioritizes a quest that has sub-objectives over an empty placeholder."""
        # Insert a quest with objectives
        db.upsert_quest(
            session_id=self.session_id,
            quest_id="SQ-REAL-01",
            quest_type="Main Quest",
            title="The Real Mystery",
            objective="Solve the case.",
            status="Active",
            is_story_quest=1,
            sub_objectives=[{"id": 1, "text": "Follow lead"}]
        )
        # Insert an empty placeholder with a newer timestamp
        db.upsert_quest(
            session_id=self.session_id,
            quest_id="SQ-EMPTY-02",
            quest_type="Story Quest",
            title="Story Quest #1: A New Adventure Begins",
            objective="Explore the area.",
            status="Active",
            is_story_quest=1,
            sub_objectives=[]
        )

        selected = db.get_active_story_quest(self.session_id)
        self.assertEqual(selected["quest_id"], "SQ-REAL-01")
        self.assertEqual(selected["title"], "The Real Mystery")

if __name__ == "__main__":
    unittest.main()
