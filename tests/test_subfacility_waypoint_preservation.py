"""
Unit tests for Sub-Facility Waypoint Preservation, Multi-Occupant Facility Roster,
and Lorebook Gender Parity.
"""
import unittest
import json
import db
from mechanics.world.locations.movement import reconcile_movement_location
from db.world import upsert_lorebook_entity, get_lorebook, get_lorebook_entity


class TestSubFacilityWaypointPreservation(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.session_id = 999222
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (self.session_id,))
            conn.execute("DELETE FROM lorebook WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM school_directory WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM quests WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM session_locations WHERE session_id=?", (self.session_id,))

            conn.execute(
                """INSERT INTO sessions (id, mode, capacity, current_location, scenario)
                   VALUES (?, 'solo', 1, 'Cultural Arts & Student Union ➔ Central Courtyard ➔ Courtyard Fountain', 'nsfw_furry_high_school_drama')""",
                (self.session_id,)
            )

            # Seed physical locations
            conn.execute(
                """INSERT INTO session_locations (session_id, location_id, zone_name, primary_name, sub_name)
                   VALUES (?, 'loc-1', 'Cultural Arts & Student Union', 'Student Council Office', 'President''s Desk')""",
                (self.session_id,)
            )
            conn.execute(
                """INSERT INTO session_locations (session_id, location_id, zone_name, primary_name, sub_name)
                   VALUES (?, 'loc-2', 'Cultural Arts & Student Union', 'Student Council Office', 'Meeting Table')""",
                (self.session_id,)
            )
            conn.execute(
                """INSERT INTO session_locations (session_id, location_id, zone_name, primary_name, sub_name)
                   VALUES (?, 'loc-3', 'Cultural Arts & Student Union', 'Student Council Office', 'Archives & Filing Cabinets')""",
                (self.session_id,)
            )

            # Seed school directory residents
            conn.execute(
                """INSERT INTO school_directory (session_id, npc_id, name, role, grade, club, clique, primary_facility, gender, race, created_at)
                   VALUES (?, 'natalia_vance', 'Natalia Vance', 'Student Council President', 'Senior', 'Student Council', 'Upperclassmen',
                           'Cultural Arts & Student Union ➔ Student Council Office ➔ President''s Desk', 'female', 'beastfolk:cat', 1000.0)""",
                (self.session_id,)
            )
            conn.execute(
                """INSERT INTO school_directory (session_id, npc_id, name, role, grade, club, clique, primary_facility, gender, race, created_at)
                   VALUES (?, 'ye-jun_halloway', 'Ye-jun Halloway', 'Student Council Junior Aide', 'Sophomore', 'Student Council', 'Underclassmen',
                           'Cultural Arts & Student Union ➔ Student Council Office ➔ Meeting Table', 'male', 'half_beast:cat', 1000.0)""",
                (self.session_id,)
            )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (self.session_id,))
            conn.execute("DELETE FROM lorebook WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM school_directory WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM quests WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM session_locations WHERE session_id=?", (self.session_id,))

    def test_lorebook_gender_column_parity(self):
        """Verify upsert_lorebook_entity stores and retrieves gender accurately."""
        upsert_lorebook_entity(
            self.session_id, "person", "Ye-jun Halloway",
            description="Council Aide", gender="male", race="half_beast:cat"
        )
        entity = get_lorebook_entity(self.session_id, "Ye-jun Halloway")
        self.assertIsNotNone(entity)
        self.assertEqual(entity.get("gender"), "male")

        # Update entity without gender and verify previous gender is preserved
        upsert_lorebook_entity(
            self.session_id, "person", "Ye-jun Halloway",
            description="Diligent Council Aide"
        )
        updated = get_lorebook_entity(self.session_id, "Ye-jun Halloway")
        self.assertEqual(updated.get("gender"), "male")
        self.assertEqual(updated.get("description"), "Diligent Council Aide")

    def test_reconcile_movement_locks_subfacility_to_target_character(self):
        """Verify that traveling to find Ye-jun locks to Meeting Table even if LLM drifts to President's Desk."""
        action = "Travel to the Student Council Office to locate Ye-jun Halloway"
        # LLM returns drifted location: President's Desk
        llm_drifted_loc = "Cultural Arts & Student Union ➔ Student Council Office ➔ President's Desk"
        current_loc = "Cultural Arts & Student Union ➔ Central Courtyard ➔ Courtyard Fountain"

        reconciled = reconcile_movement_location(
            self.session_id,
            current_loc,
            llm_drifted_loc,
            action_text=action,
            scen_key="nsfw_furry_high_school_drama"
        )

        # Must be locked to Ye-jun's designated station: Meeting Table
        self.assertIn("Meeting Table", reconciled)
        self.assertNotIn("President's Desk", reconciled)

    def test_reconcile_movement_locks_subfacility_to_active_quest_waypoint(self):
        """Verify that active quest sub-objective locks the sub-facility."""
        sub_objs = [
            {
                "id": 1,
                "text": "Befriend Ye-jun Halloway",
                "completed": False,
                "target_location": "Cultural Arts & Student Union ➔ Student Council Office ➔ Meeting Table",
                "target_npc": "Ye-jun Halloway"
            }
        ]
        with db.get_conn() as conn:
            conn.execute(
                """INSERT INTO quests (session_id, quest_id, title, objective, sub_objectives_json, status)
                   VALUES (?, 'Q1', 'Main Quest', 'Solve mystery', ?, 'Active')""",
                (self.session_id, json.dumps(sub_objs))
            )

        action = "Head into the Student Council Office"
        llm_drifted_loc = "Cultural Arts & Student Union ➔ Student Council Office ➔ President's Desk"
        current_loc = "Cultural Arts & Student Union ➔ Central Courtyard ➔ Courtyard Fountain"

        reconciled = reconcile_movement_location(
            self.session_id,
            current_loc,
            llm_drifted_loc,
            action_text=action,
            scen_key="nsfw_furry_high_school_drama"
        )

        self.assertIn("Meeting Table", reconciled)
        self.assertNotIn("President's Desk", reconciled)

    def test_reconcile_movement_allows_unconstrained_travel_when_no_npc_target(self):
        """Verify that normal general travel without NPC target respects legitimate sub-areas."""
        action = "Walk into the Student Council Office to see the President"
        llm_loc = "Cultural Arts & Student Union ➔ Student Council Office ➔ President's Desk"
        current_loc = "Cultural Arts & Student Union ➔ Central Courtyard ➔ Courtyard Fountain"

        reconciled = reconcile_movement_location(
            self.session_id,
            current_loc,
            llm_loc,
            action_text=action,
            scen_key="nsfw_furry_high_school_drama"
        )

        self.assertIn("President's Desk", reconciled)


if __name__ == "__main__":
    unittest.main()
