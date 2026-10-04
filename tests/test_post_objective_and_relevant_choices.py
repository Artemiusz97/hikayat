import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
import game_engine
import llm_client
import mechanics.world.waypoints as waypoints


class TestPostObjectiveAndRelevantChoices(unittest.TestCase):

    def setUp(self):
        self.test_session_id = 776655
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

    def test_system_prompt_contains_post_objective_and_substance_rules(self):
        """Verify GM_SHARED_RULES contains the Post-Objective Resolution and Relevance-Only rules."""
        self.assertIn("POST-OBJECTIVE RESOLUTION & TRANSITION RULE", llm_client.GM_SHARED_RULES)
        self.assertIn("RELEVANCE & SUBSTANCE-ONLY CHOICES", llm_client.GM_SHARED_RULES)
        self.assertNotIn("cover at least 3 DIFFERENT stats", llm_client.GM_SHARED_RULES)

    def test_base_system_prompt_template_contains_post_objective_and_substance_rules(self):
        """Verify BASE_SYSTEM_PROMPT_TEMPLATE in llm_client.py contains the rules."""
        self.assertIn("POST-OBJECTIVE RESOLUTION & TRANSITION RULE", llm_client.BASE_SYSTEM_PROMPT_TEMPLATE)
        self.assertIn("RELEVANCE & SUBSTANCE-ONLY CHOICES", llm_client.BASE_SYSTEM_PROMPT_TEMPLATE)

    def test_waypoint_prompt_block_post_objective_directive(self):
        """Verify build_waypoint_prompt_block includes post-objective transition when active waypoints are elsewhere."""
        with db.get_conn() as conn:
            conn.execute(
                """INSERT INTO quests (session_id, quest_id, title, objective, status, is_story_quest)
                   VALUES (?, 'story_ch1', 'The Highspire Investigation', 'Track down the ledger', 'Active', 1)""",
                (self.test_session_id,)
            )
            conn.commit()

        waypoints.db.save_quest_waypoints(
            session_id=self.test_session_id,
            quest_id="story_ch1",
            waypoints=[{
                "stage_index": 1,
                "stage_label": "Examine the guild archive records",
                "target_location": "Highspire ➔ Adventurers' Guild Hall",
                "target_npc": "Archivist",
                "completion_trigger": "arrival"
            }],
            sub_obj_id=1
        )

        # Player is at the completed Moonwell site
        wp_block = waypoints.build_waypoint_prompt_block(
            self.test_session_id,
            current_location="Emerald Thicket ➔ Sunken Moonwell ➔ Ruined Archway"
        )
        self.assertIn("POST-OBJECTIVE / TRAVEL TRANSITION", wp_block)
        self.assertIn("do NOT generate redundant micro-checks on the solved obstacle", wp_block)
        self.assertIn("Highspire ➔ Adventurers' Guild Hall", wp_block)


if __name__ == "__main__":
    unittest.main()
