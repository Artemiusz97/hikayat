import unittest
import db
import mechanics.world.locations as locs
import mechanics.world.waypoints as waypoints
import game_engine
from cogs.adventure import _build_quest_log_embed


class TestStoryQuestClimaxMarkers(unittest.TestCase):
    def setUp(self):
        self.user_id = 998877665
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id=?", (self.user_id,))

        self.char_data = db.create_character(self.user_id, "Ren", "Student", "high_school_drama")
        self.session_id = db.create_session(self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama")
        
        db.save_session_scene(
            self.session_id,
            scene_title="Investigation Turn",
            narrative="Ren reviews the clues.",
            choices=[],
            history=["Turn 1", "Turn 2"],
            location="Main Academy Campus ➔ Student Council Office ➔ President's Desk",
            nearby_enemies=[]
        )

        self.quest_id = "SQ-NEON-01"
        self.sub_objs = [
            {
                "id": 1,
                "archetype": "Environmental Recovery",
                "text": "Retrieve discarded notes",
                "completed": True
            },
            {
                "id": 2,
                "archetype": "Social Intelligence",
                "text": "Gather gossip from students",
                "completed": True
            },
            {
                "id": 3,
                "archetype": "Political Maneuvering",
                "text": "Submit a sanitized report",
                "completed": True
            }
        ]
        db.upsert_quest(
            session_id=self.session_id,
            quest_id=self.quest_id,
            quest_type="Story Quest",
            title="The Neon Smoke Aftermath",
            objective="Navigate the chaos of the chemical leak to secure evidence and identify those responsible for the sabotage.",
            progress="3/3 Cleared",
            current_clues="• Note found\n• Culprit identified",
            status="Active",
            reward_xp=250,
            reward_gold=60,
            is_story_quest=1,
            sub_objectives=self.sub_objs
        )
        
        # Save a completed waypoint representing where the last stage completed
        waypoints.db.save_quest_waypoints(
            session_id=self.session_id,
            quest_id=self.quest_id,
            waypoints=[{
                "stage_index": 1,
                "stage_label": "Submit report to President",
                "target_location": "Main Academy Campus ➔ Student Council Office",
                "completion_trigger": "skill_check"
            }],
            sub_obj_id=3
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id=?", (self.user_id,))
            conn.execute("DELETE FROM sessions WHERE id=?", (self.session_id,))
            conn.execute("DELETE FROM quests WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id=?", (self.session_id,))

    def test_get_story_quest_climax_location(self):
        """When 3/3 sub-objectives are completed, helper returns quest and climax location."""
        sq, climax_loc = waypoints.get_story_quest_climax_location(self.session_id)
        self.assertIsNotNone(sq)
        self.assertEqual(sq["quest_id"], self.quest_id)
        self.assertIn("Student Council Office", climax_loc)

    def test_location_waypoint_markers_and_zone_tree_contain_climax_tag(self):
        """World map waypoint markers and zone tree highlight ⚡ Story Climax."""
        markers = waypoints.get_location_waypoint_markers(self.session_id)
        # Verify ⚡ Story Climax tag exists in markers
        climax_found = False
        for loc_key, tag_list in markers.items():
            if any("⚡ [Story Climax]" in t for t in tag_list):
                climax_found = True
                break
        self.assertTrue(climax_found, f"Markers did not contain ⚡ [Story Climax]: {markers}")

        # Check zone tree
        summary = locs.get_zone_summary_tree(self.session_id, "high_school_drama")
        climax_zone = next((z for z in summary if "⚡ Story Climax" in z["active_tags"]), None)
        self.assertTrue(len(climax_zone["zone_name"]) > 0)
        self.assertIn("⚡ Story Climax", climax_zone["active_tags"])

    def test_generate_quest_action_choices_synthesizes_climax_action(self):
        """When player is at climax location, dedicated ⚡ [Story Climax] action is synthesized."""
        cur_loc = "Main Academy Campus ➔ Student Council Office ➔ President's Desk"
        char = db.get_character(self.user_id)
        choices = waypoints.generate_quest_action_choices(self.session_id, cur_loc, scen_key="high_school_drama", char=char)
        
        self.assertTrue(len(choices) > 0)
        climax_choice = next((c for c in choices if c.get("is_climax_action")), None)
        self.assertIsNotNone(climax_choice)
        self.assertIn("⚡ [Story Climax]", climax_choice["label"])
        self.assertIn("The Neon Smoke Aftermath", climax_choice["label"])

    def test_apply_outcome_completes_climax_quest_without_name_error(self):
        """apply_outcome and apply_quest_update complete climax quest cleanly without NameError."""
        char = db.get_character(self.user_id)
        party = [(char, 0)]
        outcome = {
            "scene_title": "Victory in the Council",
            "outcome_narrative": "You present the plan and the council agrees.",
            "next_narrative": "Peace returns to the academy.",
            "location": "Main Academy Campus ➔ Student Council Office ➔ President's Desk",
            "quest_updates": [
                {
                    "quest_id": self.quest_id,
                    "title": "The Neon Smoke Aftermath",
                    "status": "Active",
                    "completed_sub_quest_ids": []
                }
            ],
            "next_choices": [
                {"label": "Celebrate the resolution", "stat": "CHA", "requirement": 5}
            ]
        }
        action = {
            "char": char,
            "label": "⚡ [Story Climax] Present your leadership plan",
            "stat": "CHA",
            "requirement": 6,
            "mp_spent": 0,
            "is_climax_action": True,
            "is_quest_action": True,
            "quest_id": self.quest_id,
            "contract_type": "climax",
            "check": type("CheckResult", (), {"succeeded": True, "tier": "Success"})()
        }

        # Should execute without raising NameError
        items_gained = game_engine.apply_outcome(self.session_id, party, outcome, {self.user_id: 0}, actions=[action])
        self.assertIsNotNone(items_gained)

        # Check that quest marked Completed
        sq = db.get_quest_by_id(self.session_id, self.quest_id)
        self.assertEqual(sq["status"], "Completed")


if __name__ == "__main__":
    unittest.main()
