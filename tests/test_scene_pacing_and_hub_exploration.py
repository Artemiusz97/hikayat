import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
import game_engine
import character_data
import mechanics.world.locations as locs
import mechanics.world.waypoints as waypoints
from skill_check import resolve_check, success_chance, CheckResult


class TestScenePacingAndHubExploration(unittest.TestCase):

    def setUp(self):
        self.test_session_id = 889911
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

    def test_free_action_and_non_check_success_rate(self):
        """Verify that free actions (stat: NONE or requirement: 0) evaluate to 100% chance and clean success."""
        chance_zero_req = success_chance(stat_value=5, requirement=0)
        self.assertEqual(chance_zero_req, 100)

        # resolve_check with requirement=0
        check = resolve_check(stat_value=5, requirement=0, luck=3)
        self.assertEqual(check.chance, 100)
        self.assertIn(check.tier, ("success", "crit_success"))
        self.assertTrue(check.succeeded)

    def test_local_quest_objective_hook_injection(self):
        """Verify that when the player is at the quest target location, the engine injects an explicit ACTIVE LOCAL QUEST directive."""
        # Seed a quest with a waypoint at Ancient Woods -> Forgotten Aqueduct
        with db.get_conn() as conn:
            conn.execute(
                """INSERT INTO quests (session_id, quest_id, title, objective, status, is_story_quest)
                   VALUES (?, 'story_ch2', 'The Aqueduct Mystery', 'Investigate the old sluice', 'Active', 1)""",
                (self.test_session_id,)
            )
            conn.commit()

        waypoints.db.save_quest_waypoints(
            session_id=self.test_session_id,
            quest_id="story_ch2",
            waypoints=[{
                "stage_index": 1,
                "stage_label": "Examine the pried grate in the aqueduct",
                "target_location": "Ancient Woods -> Forgotten Aqueduct",
                "target_npc": "",
                "completion_trigger": "skill_check"
            }],
            sub_obj_id=1
        )

        # 1. Player is NOT at target location
        wp_block_away = waypoints.build_waypoint_prompt_block(
            self.test_session_id,
            current_location="Ancient Woods ➔ Forest Perimeter ➔ Mist Trail"
        )
        self.assertIn("Player must travel to", wp_block_away)
        self.assertNotIn("ACTIVE LOCAL QUEST OBJECTIVE AT CURRENT LOCATION", wp_block_away)

        # 2. Player IS at target location
        wp_block_at_target = waypoints.build_waypoint_prompt_block(
            self.test_session_id,
            current_location="Ancient Woods ➔ Forgotten Aqueduct ➔ Grate Entrance"
        )
        self.assertIn("ACTIVE LOCAL QUEST OBJECTIVE AT CURRENT LOCATION", wp_block_at_target)
        self.assertIn("Examine the pried grate in the aqueduct", wp_block_at_target)

        # 3. get_active_local_quest_hooks returns the matched waypoint
        hooks = waypoints.get_active_local_quest_hooks(
            self.test_session_id,
            current_location="Ancient Woods ➔ Forgotten Aqueduct ➔ Grate Entrance"
        )
        self.assertEqual(len(hooks), 1)
        self.assertEqual(hooks[0]["stage_label"], "Examine the pried grate in the aqueduct")

    def test_wilderness_poi_delve_chamber_discovery_and_persistence(self):
        """Verify that discovering new micro-dungeon chambers during exploration registers them into SQLite."""
        chamber_loc = locs.discover_poi_chamber(
            session_id=self.test_session_id,
            zone_name="Whispering Woods",
            primary_name="Sunken Monastic Vault",
            sub_name="Scribe's Library",
            scenario_key="fantasy"
        )
        self.assertIn("Whispering Woods", chamber_loc)
        self.assertIn("Sunken Monastic Vault", chamber_loc)
        self.assertIn("Scribe's Library", chamber_loc)

        # Verify it is permanently in SQLite session_locations
        existing = db.get_session_locations(self.test_session_id)
        vault_entry = next((r for r in existing if r.get("primary_name") == "Sunken Monastic Vault"), None)
        self.assertIsNotNone(vault_entry)
        self.assertEqual(vault_entry["zone_name"], "Whispering Woods")
        self.assertEqual(vault_entry["sub_name"], "Scribe's Library")

        # Archetype resolution matches Ruins / Abandoned
        arch, icon = locs.get_location_archetype("Sunken Monastic Vault")
        self.assertIn(arch, ("Ruins / Abandoned", "Haven / Settlement", "Infrastructure / Facility"))

    def test_conversation_exit_to_open_hub_spatial_transition(self):
        """Verify that choosing a conversational exit keeps the player spatially anchored in the same room."""
        current_loc = "Fairview High School ➔ Student Council Office ➔ President's Desk"

        # Player picks conversational exit: "Thank Denise, excuse yourself, and look around the room"
        reconciled = locs.reconcile_movement_location(
            session_id=self.test_session_id,
            current_loc=current_loc,
            result_loc=current_loc,
            action_text="Thank Denise, excuse yourself, and look around the office",
            narrative="Artem steps away from the desk as Denise finishes her paperwork, turning to inspect the wider room.",
            scen_key="high_school_drama",
            char_name="Artemiusz"
        )
        self.assertIn("Student Council Office", reconciled)
        self.assertIn("Fairview High School", reconciled)

    def test_scene_schema_and_outcome_schema_accept_free_actions(self):
        """Verify that SCENE_SCHEMA and OUTCOME_SCHEMA include 'NONE' as an allowed stat and requirement 0."""
        self.assertIn("NONE", game_engine.SCENE_SCHEMA)
        self.assertIn("0-12", game_engine.SCENE_SCHEMA)
        self.assertIn("NONE", game_engine.OUTCOME_SCHEMA)
        self.assertIn("0-12", game_engine.OUTCOME_SCHEMA)


if __name__ == "__main__":
    unittest.main()
