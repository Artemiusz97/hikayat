import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
import game_engine
import mechanics.world.waypoints as waypoints
from cogs.adventure import AdventureCog


class TestMultiStageAndMultiLocationWaypoints(unittest.TestCase):

    def setUp(self):
        self.test_session_id = 99887766
        db.init_db()
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.test_session_id,))
            conn.execute("INSERT INTO sessions (id, mode, capacity, scenario, current_location) VALUES (?, 'solo', 1, 'fantasy', 'School -> Rooftop')", (self.test_session_id,))
            conn.commit()

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.test_session_id,))
            conn.commit()

    def test_all_archetypes_have_at_least_3_stages(self):
        """Verify that every archetype in ARCHETYPE_WAYPOINT_TEMPLATES has at least 3 progressive stages."""
        for arch, stages in waypoints.ARCHETYPE_WAYPOINT_TEMPLATES.items():
            self.assertGreaterEqual(
                len(stages), 3,
                f"Archetype '{arch}' template has fewer than 3 stages: {stages}"
            )
            # Stage 1 should be arrival
            self.assertEqual(stages[0]["stage_index"], 1)
            self.assertEqual(stages[0]["completion_trigger"], "arrival")
            # Stages 2 and 3 should be skill_check
            self.assertEqual(stages[1]["stage_index"], 2)
            self.assertEqual(stages[1]["completion_trigger"], "skill_check")
            self.assertEqual(stages[2]["stage_index"], 3)
            self.assertEqual(stages[2]["completion_trigger"], "skill_check")

    def test_ensure_multi_stage_waypoints_expands_to_3_stages(self):
        """Verify ensure_multi_stage_waypoints expands 1 or 2 stage inputs to 3 progressive stages."""
        # 1. Empty input
        empty_res = waypoints.ensure_multi_stage_waypoints([], default_loc="Academy -> Library", archetype="investigation")
        self.assertEqual(len(empty_res), 3)

        # 2. 1-stage input
        one_stage = [{"stage_index": 1, "stage_label": "Recover the weathered note", "target_location": "School -> Rooftop", "completion_trigger": "skill_check"}]
        expanded_one = waypoints.ensure_multi_stage_waypoints(one_stage, default_loc="School -> Rooftop", archetype="investigation")
        self.assertEqual(len(expanded_one), 3)
        self.assertEqual(expanded_one[0]["completion_trigger"], "arrival")
        self.assertEqual(expanded_one[1]["completion_trigger"], "skill_check")
        self.assertEqual(expanded_one[2]["stage_label"], "Recover the weathered note")

        # 3. 2-stage input
        two_stages = [
            {"stage_index": 1, "stage_label": "Travel to Rooftop", "target_location": "School -> Rooftop", "completion_trigger": "arrival"},
            {"stage_index": 2, "stage_label": "Recover the weathered note", "target_location": "School -> Rooftop", "completion_trigger": "skill_check"}
        ]
        expanded_two = waypoints.ensure_multi_stage_waypoints(two_stages, default_loc="School -> Rooftop", archetype="investigation")
        self.assertEqual(len(expanded_two), 3)
        self.assertEqual(expanded_two[0]["stage_index"], 1)
        self.assertEqual(expanded_two[1]["stage_index"], 2)
        self.assertEqual(expanded_two[2]["stage_index"], 3)
        self.assertEqual(expanded_two[2]["stage_label"], "Recover the weathered note")

    def test_multi_location_waypoint_routing(self):
        """Verify fallback waypoints distribute distinct locations across stages 1, 2, and 3."""
        loc1 = "Academy -> Library"
        loc2 = "Forbidden Forest -> Old Ruin"
        loc3 = "Royal Capital -> Council Chamber"

        wps = waypoints.get_archetype_fallback_waypoints(
            "investigation",
            target_location=loc1,
            intermediate_location=loc2,
            final_location=loc3
        )
        self.assertEqual(len(wps), 3)
        self.assertEqual(wps[0]["target_location"], loc1)
        self.assertEqual(wps[1]["target_location"], loc2)
        self.assertEqual(wps[2]["target_location"], loc3)

    def test_multi_location_advancement_updates_active_target(self):
        """Verify advancing a multi-location waypoint stage updates active waypoint target location."""
        loc1 = "Academy -> Library"
        loc2 = "Forbidden Forest -> Old Ruin"
        loc3 = "Royal Capital -> Council Chamber"

        stages = [
            {"stage_index": 1, "stage_label": "Scout Library", "target_location": loc1, "completion_trigger": "arrival"},
            {"stage_index": 2, "stage_label": "Investigate Ruin", "target_location": loc2, "completion_trigger": "skill_check"},
            {"stage_index": 3, "stage_label": "Deliver Proof", "target_location": loc3, "completion_trigger": "skill_check"},
        ]

        db.save_quest_waypoints(self.test_session_id, "test_q1", stages, sub_obj_id=1)

        # Stage 1 active initially at loc1
        active_wp1 = db.get_active_waypoint(self.test_session_id, "test_q1", sub_obj_id=1)
        self.assertEqual(active_wp1["stage_index"], 1)
        self.assertEqual(active_wp1["target_location"], loc1)

        # Advance stage 1 on arrival at loc1
        notice1 = waypoints.try_advance_on_arrival(self.test_session_id, "test_q1", 1, current_location=loc1)
        self.assertIsNotNone(notice1)
        self.assertEqual(notice1["stage_completed"], 1)

        # Stage 2 now active at loc2
        active_wp2 = db.get_active_waypoint(self.test_session_id, "test_q1", sub_obj_id=1)
        self.assertEqual(active_wp2["stage_index"], 2)
        self.assertEqual(active_wp2["target_location"], loc2)

    def test_clean_choices_prunes_completed_in_situ_actions(self):
        """Verify _clean_choices prunes actions that attempt to repeat already-completed sub-objectives."""
        sub_objs = [
            {"id": 1, "text": "Recover the weathered note left in the crevice", "archetype": "Investigation", "completed": True},
            {"id": 2, "text": "Decode the encrypted message at the comms station", "archetype": "Tech Extraction", "completed": False},
        ]

        with db.get_conn() as conn:
            conn.execute(
                """INSERT INTO quests (session_id, quest_id, title, objective, status, is_story_quest, sub_objectives_json)
                   VALUES (?, 'sq_1', 'Whispers of the Roof', 'Investigate', 'Active', 1, ?)""",
                (self.test_session_id, json.dumps(sub_objs))
            )
            conn.commit()

        raw_choices = [
            {"label": "Reach into the crevice and recover the weathered note", "stat": "AGI", "requirement": 5, "sub_obj_id": 1},
            {"label": "Examine the concrete wall and look around the maintenance alcove", "stat": "NONE", "requirement": 0},
            {"label": "Head toward the Comms Station to decipher remaining frequencies", "stat": "NONE", "requirement": 0}
        ]

        cleaned = AdventureCog._clean_choices(
            raw_choices,
            scenario="high_school_drama",
            location="Maplewood Academy -> School Rooftop -> East Maintenance Alcove",
            session_id=self.test_session_id
        )

        labels = [c["label"] for c in cleaned]
        # Should prune the completed note recovery action
        self.assertFalse(any("weathered note" in l for l in labels))
        # Should retain observation and onward movement
        self.assertTrue(any("maintenance alcove" in l for l in labels))
        self.assertTrue(any("Comms Station" in l for l in labels))

    def test_sub_objective_cannot_complete_while_waypoints_pending(self):
        """Verify apply_quest_update Guardrail 3 blocks premature completion while waypoints are active."""
        sub_objs = [
            {"id": 1, "text": "Recover the weathered note", "archetype": "Investigation", "completed": False},
            {"id": 2, "text": "Decode the frequency", "archetype": "Investigation", "completed": False}
        ]
        with db.get_conn() as conn:
            conn.execute(
                """INSERT INTO quests (session_id, quest_id, title, objective, status, is_story_quest, sub_objectives_json)
                   VALUES (?, 'sq_test_1', 'Investigate Mystery', 'Find proof', 'Active', 1, ?)""",
                (self.test_session_id, json.dumps(sub_objs))
            )
            conn.commit()

        # Save 3-stage waypoints for sub_obj 1 (Stage 1 active)
        stages = [
            {"stage_index": 1, "stage_label": "Travel to Roof", "target_location": "School -> Roof", "completion_trigger": "arrival"},
            {"stage_index": 2, "stage_label": "Search Alcove", "target_location": "School -> Roof", "completion_trigger": "skill_check"},
            {"stage_index": 3, "stage_label": "Recover Note", "target_location": "School -> Roof", "completion_trigger": "skill_check"},
        ]
        db.save_quest_waypoints(self.test_session_id, "sq_test_1", stages, sub_obj_id=1)

        # Simulate LLM attempting to prematurely mark sub-objective 1 as completed on Turn 2
        quest_update = {
            "quest_id": "sq_test_1",
            "title": "Investigate Mystery",
            "quest_type": "Story Quest",
            "completed_sub_quest_ids": [1]
        }
        res = game_engine.apply_quest_update(self.test_session_id, quest_update)
        
        # Check database: sub_objective 1 must remain incomplete
        updated_quest = db.get_quest_by_id(self.test_session_id, "sq_test_1")
        so1 = next(so for so in updated_quest["sub_objectives"] if so["id"] == 1)

        # Guardrail 3 must prevent completion because stages 1-3 are not finished
        self.assertFalse(so1["completed"])
        self.assertIsNone(res)

    def test_multi_turn_resource_progress_requirement(self):
        """Verify resource_target: 3 requires multiple increments across turns before stage completion."""
        stages = [
            {"stage_index": 1, "stage_label": "Travel to Site", "target_location": "Forest -> Cave", "completion_trigger": "arrival"},
            {"stage_index": 2, "stage_label": "Collect 3 Clues", "target_location": "Forest -> Cave", "completion_trigger": "skill_check", "resource_target": 3},
            {"stage_index": 3, "stage_label": "Decipher Final Clue", "target_location": "Forest -> Cave", "completion_trigger": "skill_check"},
        ]
        db.save_quest_waypoints(self.test_session_id, "sq_res_test", stages, sub_obj_id=1)

        # Advance stage 1
        waypoints.try_advance_on_arrival(self.test_session_id, "sq_res_test", 1, current_location="Forest -> Cave")

        # Turn 2: Success on check (gain 1/3)
        res1 = waypoints.try_complete_on_skill_check(
            self.test_session_id, "sq_res_test", 1,
            check_success=True,
            action_text="Collect 3 Clues",
            check_result_tier="success",
            current_location="Forest -> Cave"
        )
        self.assertEqual(res1["trigger"], "resource_progress")
        self.assertEqual(res1["resource_collected"], 1)
        self.assertFalse(res1["all_stages_complete"])

        # Stage 2 still active
        active_wp = db.get_active_waypoint(self.test_session_id, "sq_res_test", 1)
        self.assertEqual(active_wp["stage_index"], 2)

        # Turn 3: Success on check (gain 2/3)
        res2 = waypoints.try_complete_on_skill_check(
            self.test_session_id, "sq_res_test", 1,
            check_success=True,
            action_text="Collect 3 Clues",
            check_result_tier="success",
            current_location="Forest -> Cave"
        )
        self.assertEqual(res2["resource_collected"], 2)
        self.assertFalse(res2["all_stages_complete"])

        # Turn 4: Success on check (gain 3/3 -> Stage 2 completed!)
        res3 = waypoints.try_complete_on_skill_check(
            self.test_session_id, "sq_res_test", 1,
            check_success=True,
            action_text="Collect 3 Clues",
            check_result_tier="success",
            current_location="Forest -> Cave"
        )
        self.assertEqual(res3["stage_completed"], 2)
        self.assertFalse(res3["all_stages_complete"])

        # Now Stage 3 is active
        active_wp3 = db.get_active_waypoint(self.test_session_id, "sq_res_test", 1)
        self.assertEqual(active_wp3["stage_index"], 3)


if __name__ == "__main__":
    unittest.main()
