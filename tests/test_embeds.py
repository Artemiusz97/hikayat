"""
Unit tests for adventure embed builders, outcome embed parsing, and waypoint headers.
"""
import unittest
import db
from cogs.adventure import build_outcome_embeds


class TestOutcomeEmbeds(unittest.TestCase):

    def setUp(self):
        db.init_db()
        self.session_id = 777111
        # Seed a test quest
        db.upsert_quest(
            session_id=self.session_id,
            quest_id="Q-TEST-01",
            quest_type="Story Quest",
            title="Investigate the Ruins",
            objective="Search the altar",
            is_story_quest=1,
            status="Active"
        )

    def test_build_outcome_embeds_with_waypoints(self):
        outcome = {
            "outcome_narrative": "You search the dusty archives and uncover the ancient waypoint map.",
            "next_narrative": "A sudden breeze rustles the torn scrolls.",
            "_waypoint_notices": [
                {
                    "trigger": "skill_check",
                    "stage_completed": 1,
                    "stage_label": "Discover Secret Compartment",
                    "quest_id": "Q-TEST-01",
                    "all_stages_complete": False,
                    "next_waypoint": {"stage_label": "Decode the runes"}
                }
            ]
        }

        embeds = build_outcome_embeds(
            outcome=outcome,
            check_field_name="🎯 Check",
            check_field_value="**PER check** (85% chance) → **SUCCESS**",
            loot_text="",
            result_display="detailed",
            session_id=self.session_id,
            primary_tier="success"
        )

        self.assertGreaterEqual(len(embeds), 2)
        # Check story embed
        self.assertIn("dusty archives", embeds[0].description)
        # Check breakdown embed contains waypoint info
        field_names = [f.name for f in embeds[1].fields]
        self.assertTrue(any("Waypoint" in name for name in field_names))

    def test_format_tracker_entity_string_attributes(self):
        from cogs.adventure import _format_tracker_entity, _tracker_group_text
        
        # Test entity with string numbers
        e1 = {
            "name": "Skye Anderson",
            "role": "Council President",
            "level": "5",
            "hp": "20",
            "max_hp": "20",
            "mp": "15",
            "max_mp": "15",
            "status_effects": ["Charmed", "Alert"]
        }
        text1 = _format_tracker_entity(e1)
        self.assertIn("Skye Anderson", text1)
        self.assertIn("20/20", text1)
        self.assertIn("15/15", text1)

        # Test entity with invalid/non-numeric strings and None
        e2 = {
            "name": "Guard",
            "role": "Sentry",
            "level": None,
            "hp": "N/A",
            "mp": "unknown",
            "status_effects": []
        }
        text2 = _format_tracker_entity(e2)
        self.assertIn("Guard", text2)

        # Test non-combat scenario vitals suppression and -1 HP suppression
        e3 = {
            "name": "Yea-ji",
            "role": "None",
            "level": 1,
            "hp": -1,
            "max_hp": -1,
            "status_effects": ["Neutral"]
        }
        text3_noncombat = _format_tracker_entity(e3, show_vitals=False)
        self.assertNotIn("❤️", text3_noncombat)
        self.assertNotIn("-1", text3_noncombat)
        self.assertNotIn("Lvl", text3_noncombat)
        self.assertNotIn("(None)", text3_noncombat)
        self.assertIn("Yea-ji", text3_noncombat)
        self.assertIn("Status: Neutral", text3_noncombat)

        # Even with show_vitals=True, negative sentinel HP should be suppressed
        text3_combat = _format_tracker_entity(e3, show_vitals=True)
        self.assertNotIn("❤️", text3_combat)
        self.assertNotIn("-1", text3_combat)
        self.assertNotIn("(None)", text3_combat)
        
        # Test tracker group rendering
        group_text = _tracker_group_text([e1, e2, e3], show_vitals=False)
        self.assertIn("Skye Anderson", group_text)
        self.assertNotIn("20/20", group_text)
        self.assertIn("Guard", group_text)
        self.assertIn("Yea-ji", group_text)

    def test_known_world_text_with_dict_status_and_traits(self):
        import game_engine
        
        # Test _describe_tracked_entity with dict status effects
        entity = {
            "name": "Corrupted Wolf",
            "level": 3,
            "hp": 30,
            "max_hp": 30,
            "mp": 10,
            "max_mp": 10,
            "status_effects": [{"name": "Enraged", "duration": 2}, "Bleeding"]
        }
        desc = game_engine._describe_tracked_entity(entity)
        self.assertIn("Corrupted Wolf", desc)
        self.assertIn("Enraged", desc)
        self.assertIn("Bleeding", desc)

        # Test _known_world_text with NPCs having dict traits
        db.upsert_lorebook_entity(
            session_id=self.session_id,
            entity_type="person",
            name="Aoi Takahashi",
            description="Student librarian",
            traits=[{"name": "Studious"}, "Observant"]
        )
        world_text = game_engine._known_world_text(
            self.session_id,
            current_location="Library",
            current_npcs=[{"name": "Aoi Takahashi", "status_effects": [{"name": "Calm"}]}]
        )
        self.assertIn("Aoi Takahashi", world_text)

    def test_scene_embed_field_length_limits(self):
        from cogs.adventure import scene_embed
        
        # Build 40 NPCs with verbose statuses to deliberately exceed 1024 characters
        npcs = [
            {
                "name": f"Student Council Representative {i}",
                "role": "Discipline Officer",
                "level": i,
                "hp": 20 + i,
                "max_hp": 20 + i,
                "mp": 10,
                "max_mp": 10,
                "status_effects": ["Vigilant", "Hyper-Alert", "Exam Stress"]
            }
            for i in range(1, 41)
        ]
        
        session = {
            "id": self.session_id,
            "scenario": "high_school_drama",
            "current_location": "Main Hallway",
            "current_npcs": npcs,
            "nearby_monsters": [],
            "turn_order": [99999],
            "current_turn_index": 0,
            "mode": "solo",
            "choices_style": "dropdown"
        }
        
        actor_char = {
            "user_id": 99999,
            "name": "Artemiusz",
            "level": 5,
            "hp": 25,
            "max_hp": 25,
            "mp": 15,
            "max_mp": 15,
            "str_": 5, "agi": 5, "end_": 5, "int_": 5, "per_": 5, "cha": 5, "luk": 5
        }
        try:
            db.delete_character(99999)
        except Exception:
            pass
        db.create_character(99999, "Artemiusz")
        
        choices = [{"label": "Head to class", "stat": "PER", "requirement": 5, "mp_cost": 0}]
        
        embeds = scene_embed(
            session=session,
            actor_char=actor_char,
            scene_title="A Busy Morning in the Hallway",
            narrative="Students bustle past as the bell rings.",
            choices=choices
        )
        
        self.assertEqual(len(embeds), 2)
        story_embed, dash_embed = embeds
        
        # Verify Discord limit constraints: each field name <= 256, each field value <= 1024
        for field in dash_embed.fields:
            self.assertLessEqual(len(field.name), 256, f"Field name exceeded 256 chars: {field.name}")
            self.assertLessEqual(len(field.value), 1024, f"Field value exceeded 1024 chars: {field.value}")
        
        # Verify that NPC tracker field gracefully truncated with '... and X more'
        npc_field = next(f for f in dash_embed.fields if "Character" in f.name)
        self.assertIn("... and", npc_field.value)

    def test_style_block_all_options(self):
        import game_engine
        
        for verbosity in ["vivid", "normal", "direct", "concise", "shakespearean", "unknown_style"]:
            for dialogue in ["off", "minimal", "balanced", "adaptive", "rich", "default", "unknown_mode"]:
                for choices in ["dropdown", "embed", "buttons", "unknown_choice"]:
                    session = {
                        "verbosity": verbosity,
                        "dialogue_mode": dialogue,
                        "choices_style": choices
                    }
                    style_text = game_engine._style_block(session)
                    self.assertIn("STYLE:", style_text)
                    self.assertIn("DIALOGUE:", style_text)
                    self.assertIn("CHOICE DESCRIPTIONS:", style_text)


if __name__ == "__main__":
    unittest.main()
