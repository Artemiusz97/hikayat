import unittest
import db
import game_engine


class TestSubObjectiveGuardrails(unittest.TestCase):
    def setUp(self):
        self.user_id = 999888777
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id=?", (self.user_id,))

        self.char_data = db.create_character(self.user_id, "Alice", "Mage", "fantasy")
        self.session_id = db.create_session(self.user_id, "solo", 1, "vivid", "individual", False, scenario="fantasy")
        db.save_session_scene(
            self.session_id,
            scene_title="Opening Scene",
            narrative="Alice arrives at the archway.",
            choices=[],
            history=[],
            location="Mosswood Thicket ➔ Sunken Moonwell ➔ Ruined Archway",
            nearby_enemies=[]
        )

        # Upsert a story quest with a multi-step delve sub-objective
        self.quest_id = "SQ-MOONWELL-01"
        self.sub_objs = [
            {
                "id": 1,
                "archetype": "Arcane Delve and Seal-Breaking",
                "text": "Enter the Sunken Moonwell through the glowing archway, survive the ruin's awakened defenses, and recover the first Moon-Sigil fragment from the chamber beneath the roots.",
                "completed": False
            },
            {
                "id": 2,
                "archetype": "Lore Research",
                "text": "Study the arcane glyphs to decipher the origin of the anomaly.",
                "completed": False
            }
        ]
        db.upsert_quest(
            session_id=self.session_id,
            quest_id=self.quest_id,
            quest_type="Story Quest",
            title="The Moonwell Awakens",
            objective="Investigate the Sunken Moonwell and retrieve the ancient relics.",
            progress="0/2 Cleared",
            current_clues="",
            status="Active",
            reward_xp=250,
            reward_gold=60,
            is_story_quest=1,
            sub_objectives=self.sub_objs
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id=?", (self.user_id,))
            conn.execute("DELETE FROM sessions WHERE id=?", (self.session_id,))

    def test_sub_objective_not_completed_on_turn_1_delve_inspection(self):
        """Turn 1 opening inspection check with spawning hostiles must NOT complete delve/recovery sub-quest."""
        party = [(db.get_character(self.user_id), db.get_inventory(self.user_id))]

        outcome = {
            "narrative": "Alice deciphers the runes, but an ambush springs!",
            "nearby_enemies": [{"name": "Dark Elf Assassin", "hp": 30, "max_hp": 30}],
            "quest_updates": [
                {
                    "quest_id": self.quest_id,
                    "title": "The Moonwell Awakens",
                    "completed_sub_quest_ids": [1],  # LLM erroneously claims sub-quest 1 is done
                }
            ],
            "character_outcomes": [{"name": "Alice", "hp_change": 0, "mp_change": -2}]
        }

        # Apply outcome
        game_engine.apply_outcome(self.session_id, party, outcome)

        # Verify sub-objective 1 is STILL not completed
        quest = db.get_quest_by_id(self.session_id, self.quest_id)
        sub_objs = quest["sub_objectives"]
        so1 = next(so for so in sub_objs if so["id"] == 1)
        self.assertFalse(so1["completed"])
        self.assertNotIn("_completed_sub_quests", outcome)

    def test_sub_objective_not_completed_while_active_hostiles_remain(self):
        """Mid-adventure action while enemies remain in combat must NOT complete combat/delve sub-quest."""
        db.save_session_scene(
            self.session_id,
            scene_title="Combat Round 2",
            narrative="The golem attacks!",
            choices=[],
            history=["Turn 1 narrative", "Turn 2 narrative"],
            location="Mosswood Thicket ➔ Sunken Moonwell ➔ Ruined Archway",
            nearby_enemies=[{"name": "Arcane Golem", "hp": 50, "max_hp": 50}]
        )

        party = [(db.get_character(self.user_id), db.get_inventory(self.user_id))]
        outcome = {
            "narrative": "Alice dodges the golem's fist!",
            "nearby_enemies": [{"name": "Arcane Golem", "hp": 50, "max_hp": 50}],
            "_combat_resolved": False,
            "quest_updates": [
                {
                    "quest_id": self.quest_id,
                    "title": "The Moonwell Awakens",
                    "completed_sub_quest_ids": [1],
                }
            ],
            "character_outcomes": [{"name": "Alice", "hp_change": 0, "mp_change": 0}]
        }

        game_engine.apply_outcome(self.session_id, party, outcome)

        quest = db.get_quest_by_id(self.session_id, self.quest_id)
        so1 = next(so for so in quest["sub_objectives"] if so["id"] == 1)
        self.assertFalse(so1["completed"])

    def test_sub_objective_completed_when_combat_resolved_and_objective_secured(self):
        """When combat is resolved and objective is secured (Turn > 1), sub-quest correctly completes."""
        db.save_session_scene(
            self.session_id,
            scene_title="Delve Complete",
            narrative="Pedestal reached.",
            choices=[],
            history=["Turn 1 narrative", "Turn 2 narrative", "Turn 3 combat defeated"],
            location="Mosswood Thicket ➔ Sunken Moonwell ➔ Ruined Archway",
            nearby_enemies=[]
        )

        party = [(db.get_character(self.user_id), db.get_inventory(self.user_id))]
        outcome = {
            "narrative": "Alice retrieves the Moon-Sigil fragment from the glowing pedestal!",
            "nearby_enemies": [],
            "_combat_resolved": True,
            "quest_updates": [
                {
                    "quest_id": self.quest_id,
                    "title": "The Moonwell Awakens",
                    "completed_sub_quest_ids": [1],
                }
            ],
            "character_outcomes": [{"name": "Alice", "hp_change": 0, "mp_change": 0}]
        }

        game_engine.apply_outcome(self.session_id, party, outcome)

        quest = db.get_quest_by_id(self.session_id, self.quest_id)
        so1 = next(so for so in quest["sub_objectives"] if so["id"] == 1)
        self.assertTrue(so1["completed"])
        self.assertIn("_completed_sub_quests", outcome)


if __name__ == "__main__":
    unittest.main()
