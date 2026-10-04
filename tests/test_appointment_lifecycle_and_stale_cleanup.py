"""
Unit tests for phone appointment lifecycle and stale arrived appointment completion.
"""
import unittest
import db
import game_engine


class TestAppointmentLifecycleAndStaleCleanup(unittest.TestCase):
    def setUp(self):
        self.session_id = 993322
        self.user_id = 883322

        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (self.session_id,))

        db.create_character(self.user_id, "Protagonist", "male")
        self.char = db.get_character(self.user_id)
        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )

        db.upsert_contact(
            self.session_id, character_id=self.char["id"], npc_id="sofia_anderson",
            name="Sofia Anderson", basic_info={"location": "Westlake Academy"}
        )
        db.upsert_contact(
            self.session_id, character_id=self.char["id"], npc_id="maya_anderson",
            name="Maya Anderson", basic_info={"location": "Westlake Academy"}
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (self.session_id,))

    def test_stale_arrived_appointment_does_not_inject_into_new_meetup(self):
        """A past 'arrived' appointment with Sofia must NOT inject Sofia into a new rooftop scene with Maya."""
        rooftop = "Westlake Academy ➔ School Rooftop ➔ Rooftop Benches"

        # 1. Past Sofia appointment already arrived turns ago
        db.save_phone_appointment(self.session_id, "sofia_anderson", "Sofia Anderson", rooftop)
        db.update_phone_appointment_status(self.session_id, "sofia_anderson", "arrived")

        # 2. Fresh pending appointment with Maya
        db.save_phone_appointment(self.session_id, "maya_anderson", "Maya Anderson", rooftop)

        session = db.get_session(self.session_id)
        # Player is coming from their house (old_loc)
        old_loc = "Sakura Hill Residential Town ➔ Artemiusz's House ➔ Your Bedroom"
        new_loc = rooftop

        result = {
            "npcs_present": [{"name": "Maya Anderson"}],
            "outcome_narrative": "You step onto the rooftop and see Maya waiting.",
            "next_narrative": "Maya smiles warmly."
        }

        final_npcs = game_engine.process_scene_npcs(result, session, new_loc, old_loc)
        names = [n["name"] for n in final_npcs]

        # Maya must be present
        self.assertIn("Maya Anderson", names)
        # Sofia must NOT be present!
        self.assertNotIn("Sofia Anderson", names)

    def test_moving_away_from_rendezvous_completes_arrived_appointment(self):
        """When player moves away from the rendezvous location, the arrived appointment is marked completed."""
        rooftop = "Westlake Academy ➔ School Rooftop ➔ Rooftop Benches"
        classroom = "Westlake Academy ➔ Classroom 2-B ➔ Desks"

        db.save_phone_appointment(self.session_id, "maya_anderson", "Maya Anderson", rooftop)
        db.update_phone_appointment_status(self.session_id, "maya_anderson", "arrived")

        session = db.get_session(self.session_id)
        result = {
            "npcs_present": [],
            "outcome_narrative": "You leave the rooftop and head downstairs to class.",
            "next_narrative": "The classroom is full of students."
        }

        game_engine.process_scene_npcs(result, session, new_loc=classroom, old_loc=rooftop)

        # Maya's appointment should now be completed
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT status FROM phone_appointments WHERE session_id = ? AND npc_id = ?",
                (self.session_id, "maya_anderson")
            ).fetchone()
            self.assertEqual(row["status"], "completed")

    def test_departing_npc_completes_appointment(self):
        """When an NPC departs in the narrative, their appointment is marked completed."""
        house = "Sakura Hill Residential Town ➔ House ➔ Living Room"

        db.save_phone_appointment(self.session_id, "sofia_anderson", "Sofia Anderson", house)
        db.update_phone_appointment_status(self.session_id, "sofia_anderson", "arrived")

        session = db.get_session(self.session_id)
        result = {
            "npcs_present": [],
            "outcome_narrative": "Artemiusz watches Sofia depart, the soft click of the front door signaling her exit.",
            "next_narrative": "You relax in the quiet room."
        }

        game_engine.process_scene_npcs(result, session, new_loc=house, old_loc=house)

        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT status FROM phone_appointments WHERE session_id = ? AND npc_id = ?",
                (self.session_id, "sofia_anderson")
            ).fetchone()
            self.assertEqual(row["status"], "completed")

    def test_conversational_action_does_not_summon_absent_npc(self):
        """Clicking 'Speak with Sofia Anderson' when Sofia is not in the room must NOT spawn Sofia into the scene."""
        rooftop = "Westlake Academy ➔ School Rooftop ➔ Rooftop Benches"
        session = db.get_session(self.session_id)

        result = {
            "npcs_present": [{"name": "Maya Anderson"}],
            "outcome_narrative": "Maya leans back against the railing and teases you playfully.",
            "next_narrative": "The rooftop is quiet as Maya waits for your response."
        }

        # Action is local conversational, staying on rooftop (new_loc == old_loc)
        actions = [{"label": "Speak with Sofia Anderson"}]
        final_npcs = game_engine.process_scene_npcs(result, session, new_loc=rooftop, old_loc=rooftop, actions=actions)
        names = [n["name"] for n in final_npcs]

        self.assertIn("Maya Anderson", names)
        self.assertNotIn("Sofia Anderson", names)


if __name__ == "__main__":
    unittest.main()
