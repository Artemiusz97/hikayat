import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
import game_engine
import mechanics.world.locations as locs
import mechanics.world.waypoints as waypoints
from cogs.adventure import AdventureCog


class TestCompletedSubObjectiveMarkersAndChoiceFiltering(unittest.TestCase):

    def setUp(self):
        self.test_session_id = 88776655
        db.init_db()
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.test_session_id,))
            conn.commit()

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.test_session_id,))
            conn.commit()

    def test_completed_sub_objective_markers_disappear(self):
        """Verify that completing sub-objectives removes ⭐ markers from the map for cleared locations."""
        sub_objs = [
            {"id": 1, "text": "Enter the overgrown Sunken Moonwell and trace the blue fire", "archetype": "Arcane Infiltration", "completed": True},
            {"id": 2, "text": "Return to the Adventurers Guild with evidence", "archetype": "Guild Intelligence", "completed": False},
            {"id": 3, "text": "Seek the First Grove's druids", "archetype": "Druidic Diplomacy", "completed": True},
        ]

        with db.get_conn() as conn:
            conn.execute(
                """INSERT INTO quests (session_id, quest_id, title, objective, status, is_story_quest, sub_objectives_json)
                   VALUES (?, 'story_ch1', 'The Blue Fire', 'Investigate', 'Active', 1, ?)""",
                (self.test_session_id, json.dumps(sub_objs))
            )
            conn.commit()

        # Seed waypoints for all 3 sub-objectives
        db.save_quest_waypoints(
            self.test_session_id, "story_ch1",
            [{"stage_index": 1, "stage_label": "Enter Moonwell", "target_location": "Forest of Sunlit Vale ➔ Sunken Moonwell", "completion_trigger": "arrival"}],
            sub_obj_id=1
        )
        db.save_quest_waypoints(
            self.test_session_id, "story_ch1",
            [{"stage_index": 1, "stage_label": "Report to Guild", "target_location": "Royal Capital of Lunaria ➔ Adventurers' Guild Hall", "completion_trigger": "arrival"}],
            sub_obj_id=2
        )
        db.save_quest_waypoints(
            self.test_session_id, "story_ch1",
            [{"stage_index": 1, "stage_label": "Consult Druids", "target_location": "Great Canopy of The First Grove ➔ Druidic Tree Sanctuary", "completion_trigger": "arrival"}],
            sub_obj_id=3
        )

        # Seed session locations
        locs.process_llm_location_update(self.test_session_id, "Forest of Sunlit Vale ➔ Sunken Moonwell ➔ Inner Sanctum", "fantasy")
        locs.process_llm_location_update(self.test_session_id, "Royal Capital of Lunaria ➔ Adventurers' Guild Hall ➔ Counter", "fantasy")
        locs.process_llm_location_update(self.test_session_id, "Great Canopy of The First Grove ➔ Druidic Tree Sanctuary ➔ Moonwell", "fantasy")

        # 1. Verify get_all_session_active_waypoints filters out sub-objs 1 and 3
        active_wps = db.get_all_session_active_waypoints(self.test_session_id)
        active_sub_ids = [wp.get("sub_obj_id") for wp in active_wps]
        self.assertIn(2, active_sub_ids)
        self.assertNotIn(1, active_sub_ids)
        self.assertNotIn(3, active_sub_ids)

        # 2. Verify get_location_waypoint_markers only contains the active guild hall
        markers = waypoints.get_location_waypoint_markers(self.test_session_id)
        self.assertIn("Royal Capital of Lunaria ➔ Adventurers' Guild Hall", markers)
        self.assertNotIn("Forest of Sunlit Vale ➔ Sunken Moonwell", markers)
        self.assertNotIn("Great Canopy of The First Grove ➔ Druidic Tree Sanctuary", markers)

        # 3. Verify get_zone_summary_tree does not give ⭐ to cleared zones / places
        summary = locs.get_zone_summary_tree(self.test_session_id, "fantasy")
        forest_zone = next(z for z in summary if "Forest" in z["zone_name"] or "Sunlit" in z["zone_name"])
        grove_zone = next(z for z in summary if "Grove" in z["zone_name"] or "Canopy" in z["zone_name"])
        capital_zone = next(z for z in summary if "Capital" in z["zone_name"] or "Lunaria" in z["zone_name"])

        self.assertNotIn("⭐ Story Quest", forest_zone["active_tags"])
        self.assertNotIn("⭐ Story Quest", grove_zone["active_tags"])
        self.assertIn("⭐ Story Quest", capital_zone["active_tags"])

        sanctuary = next(p for p in grove_zone["primary_locations"] if "Sanctuary" in p["name"])
        self.assertNotIn("⭐", sanctuary["badges"])

        guild_hall = next(p for p in capital_zone["primary_locations"] if "Guild" in p["name"])
        self.assertIn("⭐", guild_hall["badges"])

    def test_clean_choices_prunes_travel_to_completed_sites(self):
        """Verify _clean_choices drops travel/guidance options targeting completed sub-objective locations."""
        sub_objs = [
            {"id": 1, "text": "Enter the overgrown Sunken Moonwell and trace the source of the blue fire", "archetype": "Arcane Infiltration", "completed": True},
            {"id": 2, "text": "Return to the Adventurers Guild with evidence", "archetype": "Guild Intelligence", "completed": False},
            {"id": 3, "text": "Seek the First Grove's druids", "archetype": "Druidic Diplomacy", "completed": True},
        ]

        with db.get_conn() as conn:
            conn.execute(
                """INSERT INTO quests (session_id, quest_id, title, objective, status, is_story_quest, sub_objectives_json)
                   VALUES (?, 'story_ch1', 'The Blue Fire', 'Investigate', 'Active', 1, ?)""",
                (self.test_session_id, json.dumps(sub_objs))
            )
            conn.commit()

        raw_choices = [
            {"label": "Compare sealed expedition logs against maps and merchant reports", "stat": "INT", "requirement": 6},
            {"label": "Speak with Nynaeve Valiant about concealed guild records", "stat": "CHA", "requirement": 5},
            {"label": "Ask Elder Maerwyn Rootspeaker whether the luminous root-path can guide Alice toward the First Grove sanctuary", "stat": "CHA", "requirement": 5},
            {"label": "Travel onward through the forest toward the Sunken Moonwell and its vine-choked archway", "stat": "NONE", "requirement": 0},
            {"label": "Rest beneath the pavilion awning, steady the Resonance Shard, and review the next routes", "stat": "NONE", "requirement": 0}
        ]

        cleaned = AdventureCog._clean_choices(
            raw_choices,
            scenario="fantasy",
            location="Royal Capital of Lunaria ➔ Outer Pavilion ➔ Bough Bench",
            session_id=self.test_session_id
        )

        labels = [c["label"] for c in cleaned]

        # Should prune travel to Sunken Moonwell (Sub #1 is complete)
        self.assertFalse(any("Sunken Moonwell" in l for l in labels))

        # Should prune guidance toward First Grove (Sub #3 is complete)
        self.assertFalse(any("First Grove" in l for l in labels))

        # Active choices and rest must be retained
        self.assertTrue(any("expedition logs" in l for l in labels))
        self.assertTrue(any("Nynaeve Valiant" in l for l in labels))
        self.assertTrue(any("pavilion awning" in l for l in labels))

    def test_update_quest_sub_objectives_syncs_waypoints(self):
        """Verify that game_engine.apply_quest_update sets quest_waypoints to 'completed'."""
        sub_objs = [
            {"id": 1, "text": "Sunken Moonwell", "archetype": "Arcane Infiltration", "completed": False},
            {"id": 2, "text": "Adventurers Guild", "archetype": "Guild Intelligence", "completed": False},
        ]
        db.upsert_quest(
            session_id=self.test_session_id,
            quest_id="story_ch1",
            quest_type="Story Quest",
            title="The Blue Fire",
            objective="Investigate",
            progress="0/2",
            current_clues="",
            status="Active",
            reward_xp=100,
            reward_gold=50,
            reward_stat_points=0,
            reward_item="",
            is_story_quest=True,
            sub_objectives=sub_objs
        )
        db.save_quest_waypoints(
            self.test_session_id, "story_ch1",
            [{"stage_index": 1, "stage_label": "Enter Moonwell", "target_location": "Forest of Sunlit Vale ➔ Sunken Moonwell", "completion_trigger": "arrival"}],
            sub_obj_id=1
        )
        db.save_quest_waypoints(
            self.test_session_id, "story_ch1",
            [{"stage_index": 1, "stage_label": "Report to Guild", "target_location": "Royal Capital of Lunaria ➔ Adventurers' Guild Hall", "completion_trigger": "arrival"}],
            sub_obj_id=2
        )

        # Mark Sub-Objective 1 complete via quest update
        game_engine.apply_quest_update(
            self.test_session_id,
            {
                "quest_id": "story_ch1",
                "title": "The Blue Fire",
                "is_story_quest": True,
                "completed_sub_quest_ids": [1],
                "sub_objectives": [
                    {"id": 1, "text": "Sunken Moonwell", "archetype": "Arcane Infiltration", "completed": True},
                    {"id": 2, "text": "Adventurers Guild", "archetype": "Guild Intelligence", "completed": False},
                ]
            }
        )

        with db.get_conn() as conn:
            row_so1 = conn.execute("SELECT status FROM quest_waypoints WHERE session_id=? AND quest_id='story_ch1' AND sub_obj_id=1", (self.test_session_id,)).fetchone()
            row_so2 = conn.execute("SELECT status FROM quest_waypoints WHERE session_id=? AND quest_id='story_ch1' AND sub_obj_id=2", (self.test_session_id,)).fetchone()

        self.assertEqual(row_so1["status"], "completed")
        self.assertEqual(row_so2["status"], "active")

    def test_escalation_directives_forbid_completed_sites(self):
        """Verify that build_scene_escalation_and_consequence_directives includes the completed objectives prohibition."""
        sub_objs = [
            {"id": 1, "text": "Sunken Moonwell", "archetype": "Arcane Infiltration", "completed": True},
            {"id": 2, "text": "Adventurers Guild", "archetype": "Guild Intelligence", "completed": False},
        ]
        story_quest = {
            "title": "The Blue Fire",
            "is_story_quest": True,
            "sub_objectives": sub_objs,
            "current_clues": ""
        }
        session = {"current_location": "Royal Capital of Lunaria ➔ Adventurers' Guild Hall", "history": []}
        directives = game_engine.build_scene_escalation_and_consequence_directives(session, [], [], story_quest=story_quest)

        self.assertIn("🚫 [COMPLETED OBJECTIVES & CLEARED SITES - STRICTLY FORBIDDEN IN CHOICES]", directives)
        self.assertIn("NEVER generate travel choices", directives)


if __name__ == "__main__":
    unittest.main()
