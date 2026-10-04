import unittest
import game_engine
from game_engine.state import get_combined_narrative, _evaluate_npc_milestones
from mechanics.system.memory.budget import _classify_scene, SceneMode
from mechanics.world.locations.seeds import is_school_scenario


class TestPhase6Consolidation(unittest.TestCase):
    """Verifies Phase 6A (dialogue_partner & narrative deduplication) and Phase 6B (Engine helper standardization)."""

    # --- Sub-Phase 6A Tests ---

    def test_get_combined_narrative(self):
        """Verify get_combined_narrative merges all narrative fields cleanly."""
        outcome = {
            "outcome_narrative": "You opened the chest.",
            "next_narrative": "Inside glints an ancient key.",
            "narrative": "The dungeon grows quiet.",
        }
        self.assertEqual(
            get_combined_narrative(outcome),
            "You opened the chest. Inside glints an ancient key. The dungeon grows quiet.",
        )
        self.assertEqual(get_combined_narrative({}), "")
        self.assertEqual(get_combined_narrative(None), "")

    def test_evaluate_npc_milestones_recognizes_modern_dialogue_partners_list(self):
        """Verify _evaluate_npc_milestones detects target NPC when session only sets modern 'dialogue_partners' list."""
        session = {
            "dialogue_partners": ["Elena"],
            "dialogue_partner": "",  # Legacy singular key is empty
        }
        app_dict = {}
        (
            new_mem,
            intercourse,
            oral,
            manual,
            track,
            is_intimate,
            boost,
        ) = _evaluate_npc_milestones(
            npc_name="Elena",
            app_dict=app_dict,
            track="romantic",
            milestone_ev="",
            custom_summary="",
            intercourse_exp="virgin",
            oral_exp="inexperienced",
            actions=[{"label": "I love you"}],
            narrative_text="She blushes deeply, tears of joy in her eyes, and says I love you too.",
            overall_check_success=True,
            is_player_romantic_action=True,
            is_player_intimate_action=False,
            is_player_oral_action=False,
            is_player_intercourse_action=False,
            is_player_confession_action=True,
            is_player_affection_action=False,
            affection_target_npc=None,
            gift_target_npc=None,
            gift_item_name=None,
            confession_target_npc=None,
            first_char_name="Player",
            session=session,
            single_update=False,
        )
        self.assertIsNotNone(new_mem, "Should trigger confession milestone via modern dialogue_partners list")
        self.assertEqual(track, "romantic")

    # --- Sub-Phase 6B Tests ---

    def test_get_active_enemies_filters_dead_and_parses_json(self):
        """Verify get_active_enemies filters hp <= 0, parses JSON strings, and normalizes string entries."""
        # 1. Filters defeated enemies (hp <= 0)
        data_dead = {
            "nearby_enemies": [
                {"name": "Defeated Goblin", "hp": 0},
                {"name": "Overkilled Orc", "hp": -4},
                {"name": "Living Shaman", "hp": 12},
            ]
        }
        active = game_engine.get_active_enemies(data_dead)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["name"], "Living Shaman")

        # 2. Parses JSON strings and empty JSON '[]'
        self.assertEqual(game_engine.get_active_enemies({"nearby_enemies": "[]"}), [])
        json_active = game_engine.get_active_enemies({"nearby_enemies": '[{"name": "Bandit", "hp": 20}]'})
        self.assertEqual(len(json_active), 1)
        self.assertEqual(json_active[0]["name"], "Bandit")

        # 3. Normalizes string entries
        str_active = game_engine.get_active_enemies({"nearby_enemies": ["Dire Wolf"]})
        self.assertEqual(str_active, [{"name": "Dire Wolf"}])

    def test_budget_scene_mode_ignores_defeated_enemies_and_empty_json(self):
        """Verify _classify_scene does not enter COMBAT mode when nearby_enemies are dead (hp=0) or '[]'."""
        session_dead = {
            "scenario": "fantasy",
            "nearby_enemies": [{"name": "Slime", "hp": 0}],
        }
        self.assertEqual(_classify_scene(session_dead, None, []), SceneMode.EXPLORATION)

        session_empty_json = {
            "scenario": "fantasy",
            "nearby_enemies": "[]",
        }
        self.assertEqual(_classify_scene(session_empty_json, None, []), SceneMode.EXPLORATION)

    def test_get_npc_name_supports_fallback_keys(self):
        """Verify _get_npc_name extracts 'name', 'npc_name', or 'character' safely."""
        self.assertEqual(game_engine._get_npc_name({"name": "Elena"}), "Elena")
        self.assertEqual(game_engine._get_npc_name({"npc_name": "Maya"}), "Maya")
        self.assertEqual(game_engine._get_npc_name({"character": "Cid"}), "Cid")
        self.assertEqual(game_engine._get_npc_name("  Kana  "), "Kana")
        self.assertEqual(game_engine._get_npc_name(None), "")

    def test_is_school_scenario_covers_slice_of_life_and_tags(self):
        """Verify is_school_scenario recognizes high_school, slice_of_life, and rejects fantasy."""
        self.assertTrue(is_school_scenario("high_school_drama"))
        self.assertTrue(is_school_scenario("slice_of_life"))
        self.assertTrue(is_school_scenario("academy_romance"))
        self.assertFalse(is_school_scenario("fantasy"))

    def test_extract_scene_fields_normalizes_all_fallback_keys(self):
        """Verify extract_scene_fields handles all LLM key variations and session fallbacks."""
        data = {
            "suggested_actions": [{"label": "Inspect altar"}, "Pray quietly"],
            "story": "  A faint light glows above the shrine.  ",
            "title": "The Forgotten Shrine",
            "dialogue_partners": ["Elena"],
        }
        session = {"current_npcs": [{"name": "Elena"}]}
        choices, narrative, title, partner_arg, npcs_arg = game_engine.extract_scene_fields(data, session=session)
        self.assertEqual(choices, [{"label": "Inspect altar"}, {"label": "Pray quietly"}])
        self.assertEqual(narrative, "A faint light glows above the shrine.")
        self.assertEqual(title, "The Forgotten Shrine")
        self.assertEqual(partner_arg, ["Elena"])
        self.assertEqual(npcs_arg, [{"name": "Elena"}])


if __name__ == "__main__":
    unittest.main()
