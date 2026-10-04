import unittest
import db
import game_engine
from cogs.adventure import scene_embed, sync_scene_embed


class TestEnemyCharacterSeparation(unittest.TestCase):
    def setUp(self):
        db.init_db()
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id IN (99890, 99891)")
            conn.execute("DELETE FROM sessions WHERE turn_order LIKE '%99890%' OR turn_order LIKE '%99891%'")

    def test_hostile_entities_excluded_from_current_npcs(self):
        """Hostile entities in new_entities must be sent to nearby_enemies and excluded from npcs_present."""
        session = {
            "id": 99890,
            "scenario": "fantasy",
            "current_location": "Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table",
            "current_npcs": [{"name": "Mara Vey"}],
            "nearby_enemies": [],
            "nearby_monsters": [],
            "history": []
        }

        raw_llm_result = {
            "scene_title": "Assassins Strike",
            "narrative": "Rovan Kest and Ilyra Sorn draw their blades!",
            "location": "Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table",
            "new_entities": [
                {"name": "Mara Vey", "type": "person", "disposition": "friendly", "description": "Scout ally"},
                {"name": "Rovan Kest", "type": "person", "disposition": "hostile", "description": "Bounty Hunter"},
                {"name": "Ilyra Sorn", "type": "person", "disposition": "hostile", "description": "Rogue Assassin"}
            ],
            "nearby_enemies": [
                {"name": "Rovan Kest", "hp": 96, "max_hp": 96, "mp": 18, "max_mp": 18},
                {"name": "Ilyra Sorn", "hp": 78, "max_hp": 78, "mp": 24, "max_mp": 24}
            ],
            "next_choices": [
                {"label": "Cast a barrier", "stat": "INT", "requirement": 5}
            ]
        }

        loc = raw_llm_result["location"]
        npcs_present = game_engine.process_scene_npcs(raw_llm_result, session, loc, loc)
        npc_names = [n.get("name") if isinstance(n, dict) else n for n in npcs_present]

        # Mara Vey should be present in npcs_present
        self.assertIn("Mara Vey", npc_names)
        # Hostile enemies Rovan Kest and Ilyra Sorn MUST NOT be in npcs_present
        self.assertNotIn("Rovan Kest", npc_names)
        self.assertNotIn("Ilyra Sorn", npc_names)

    def test_dashboard_embed_filters_duplicate_enemies_from_characters(self):
        """Even if legacy current_npcs contains an enemy, the dashboard embed filters it from Characters field."""
        uid = 99891
        char = db.create_character(uid, "Bob", "Warrior", "fantasy")
        sess_id = db.create_session(uid, "solo", 1, "vivid", "individual", False, scenario="fantasy")

        mock_session = {
            "id": sess_id,
            "scenario": "fantasy",
            "current_location": "Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table",
            "current_npcs": [
                {"name": "Mara Vey"},
                {"name": "Rovan Kest"}, # Legacy overlap
                {"name": "Ilyra Sorn"}  # Legacy overlap
            ],
            "nearby_enemies": [
                {"name": "Rovan Kest", "level": 12, "hp": 96, "max_hp": 96, "mp": 18, "max_mp": 18, "status_effects": []},
                {"name": "Ilyra Sorn", "level": 11, "hp": 78, "max_hp": 78, "mp": 24, "max_mp": 24, "status_effects": []}
            ],
            "turn_order": [uid],
            "current_turn_index": 0,
            "mode": "solo",
            "choices_style": "dropdown"
        }

        embeds = scene_embed(mock_session, char, "Combat Scene", "Fighting enemies", [])
        dash_embed = embeds[1]

        char_field = next((f for f in dash_embed.fields if "Character" in f.name), None)
        enemy_field = next((f for f in dash_embed.fields if "Enemy" in f.name or "Enemies" in f.name), None)

        self.assertIsNotNone(char_field)
        self.assertIsNotNone(enemy_field)

        # Characters field should only have Mara Vey
        self.assertIn("Mara Vey", char_field.value)
        self.assertNotIn("Rovan Kest", char_field.value)
        self.assertNotIn("Ilyra Sorn", char_field.value)

        # Enemies field should have both enemies
        self.assertIn("Rovan Kest", enemy_field.value)
        self.assertIn("Ilyra Sorn", enemy_field.value)


if __name__ == "__main__":
    unittest.main()
