import unittest
import json
import db
from mechanics.world.waypoints.matching import resolve_waypoint_target_npc, is_waypoint_npc_present_in_scene
from mechanics.world.waypoints.core import build_waypoint_prompt_block
from mechanics.world.waypoints.choices import tag_and_enrich_quest_choices


class TestWaypointNPCInference(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.session_id = 99988877
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (self.session_id,))
            conn.execute("DELETE FROM quests WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id=?", (self.session_id,))

            conn.execute(
                """INSERT INTO sessions (id, mode, capacity, current_location, dialogue_partner, scenario)
                   VALUES (?, 'solo', 1, 'Shiranui Senior High ➔ Empty Classroom ➔ Back Corner', '["Nicholas Ito"]', 'high_school')""",
                (self.session_id,)
            )

            conn.execute(
                """INSERT INTO contacts (session_id, character_id, npc_id, name, basic_info_json)
                   VALUES (?, 0, 'nicholas_ito', 'Nicholas Ito', '{"role": "Journalist"}')""",
                (self.session_id,)
            )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (self.session_id,))
            conn.execute("DELETE FROM quests WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id=?", (self.session_id,))

    def test_infer_target_npc_from_stage_label_when_empty(self):
        wp = {
            "session_id": self.session_id,
            "quest_id": "SQ-TEST",
            "stage_label": "Secure Exclusive Interview with Nicholas Ito",
            "target_location": "Student Commons & Central Plaza -> Central Courtyard",
            "target_npc": ""
        }
        resolved = resolve_waypoint_target_npc(self.session_id, wp)
        self.assertEqual(resolved, "Nicholas Ito")
        self.assertTrue(is_waypoint_npc_present_in_scene(self.session_id, resolved))

    def test_build_waypoint_prompt_block_recognizes_present_npc_target(self):
        with db.get_conn() as conn:
            conn.execute(
                """INSERT INTO quests (session_id, quest_id, title, objective, sub_objectives_json, status, is_story_quest)
                   VALUES (?, 'SQ-TEST', 'The Headline Mystery', 'Find the culprit', '[]', 'Active', 1)""",
                (self.session_id,)
            )
            conn.execute(
                """INSERT INTO quest_waypoints (session_id, quest_id, sub_obj_id, stage_index, stage_label, target_location, target_npc, status, completion_trigger)
                   VALUES (?, 'SQ-TEST', 1, 3, 'Secure Exclusive Interview with Nicholas Ito', 'Student Commons & Central Plaza -> Central Courtyard', '', 'active', 'skill_check')""",
                (self.session_id,)
            )

        prompt_block = build_waypoint_prompt_block(self.session_id, "Shiranui Senior High ➔ Empty Classroom ➔ Back Corner")
        self.assertIn("(AT TARGET)", prompt_block)
        self.assertIn("ACTIVE LOCAL QUEST OBJECTIVE AT CURRENT LOCATION", prompt_block)
        self.assertNotIn("(NOT at target)", prompt_block)

    def test_tag_and_enrich_quest_choices_injects_dialogue_choice_even_if_allow_fallback_false(self):
        with db.get_conn() as conn:
            conn.execute(
                """INSERT INTO quests (session_id, quest_id, title, objective, sub_objectives_json, status, is_story_quest)
                   VALUES (?, 'SQ-TEST', 'The Headline Mystery', 'Find the culprit', '[]', 'Active', 1)""",
                (self.session_id,)
            )
            conn.execute(
                """INSERT INTO quest_waypoints (session_id, quest_id, sub_obj_id, stage_index, stage_label, target_location, target_npc, status, completion_trigger)
                   VALUES (?, 'SQ-TEST', 1, 3, 'Secure Exclusive Interview with Nicholas Ito', 'Student Commons & Central Plaza -> Central Courtyard', '', 'active', 'skill_check')""",
                (self.session_id,)
            )

        raw_choices = [
            {"label": "Ask about his favorite dessert", "stat": "CHA", "requirement": 5},
            {"label": "Leave the classroom", "stat": "NONE", "requirement": 0}
        ]

        enriched = tag_and_enrich_quest_choices(
            choices=raw_choices,
            session_id=self.session_id,
            current_location="Shiranui Senior High ➔ Empty Classroom ➔ Back Corner",
            scen_key="high_school",
            dialogue_partner=["Nicholas Ito"],
            allow_fallback=False
        )

        has_quest_choice = any(c.get("is_quest_action") for c in enriched)
        self.assertTrue(has_quest_choice)
        quest_choice = next(c for c in enriched if c.get("is_quest_action"))
        self.assertIn("Nicholas Ito", quest_choice["label"])
        self.assertIn("Secure Exclusive Interview", quest_choice["label"])


if __name__ == "__main__":
    unittest.main()
