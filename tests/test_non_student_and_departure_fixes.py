from __future__ import annotations
import os
import tempfile
import unittest
import db
import db.core
from game_engine.npcs.cast_planner import plan_pre_turn, apply_cast_events
from mechanics.social.relationships import is_contact_eligible


class TestNonStudentAndDepartureFixes(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._isolated_db = os.path.join(self._tmp_dir.name, "test_non_student.db")
        self._orig_db_path = db.DB_PATH
        self._orig_core_db_path = db.core.DB_PATH
        db.DB_PATH = self._isolated_db
        db.core.DB_PATH = self._isolated_db
        db.init_db()
        self.user_id = 99881122
        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )

    def tearDown(self):
        if hasattr(db, "close_all_connections"):
            db.close_all_connections()
        db.DB_PATH = self._orig_db_path
        db.core.DB_PATH = self._orig_core_db_path
        self._tmp_dir.cleanup()

    def test_non_student_faculty_not_contact_eligible(self):
        """Verify teachers, faculty, staff, and adults are not contact-eligible in high school."""
        self.assertFalse(is_contact_eligible(
            name="Dr. Raymond Satou",
            role="Chemistry Teacher",
            description="Strict fennec teacher",
            scenario="high_school_drama",
            session_id=self.session_id,
        ))
        self.assertFalse(is_contact_eligible(
            name="Coach Tanaka",
            role="Head Coach",
            description="Athletic director",
            scenario="high_school_drama",
            session_id=self.session_id,
        ))
        self.assertTrue(is_contact_eligible(
            name="Mio Kobayashi",
            role="Student",
            description="Quiet classmate",
            scenario="high_school_drama",
            session_id=self.session_id,
        ))

    def test_upsert_contact_rejects_faculty_and_stores_in_lorebook(self):
        """Verify upsert_contact returns empty for faculty and does not persist them to contacts table."""
        res = db.upsert_contact(
            session_id=self.session_id,
            npc_id="dr_raymond_satou",
            name="Dr. Raymond Satou",
            basic_info={"role": "Chemistry Teacher", "description": "Chemistry teacher"},
        )
        self.assertEqual(res, {})
        contacts = db.get_contacts(self.session_id)
        self.assertEqual(len(contacts), 0)

        db.upsert_lorebook_entity(
            session_id=self.session_id,
            entity_type="person",
            name="Dr. Raymond Satou",
            description="Chemistry teacher",
            mannerisms="Adjusts wire-rimmed glasses frequently",
            race="Fennec Fox Half-Beast",
            appearance={"coat_color": "Golden-cream fur", "eye_color": "Amber"},
            gender="male",
        )
        lore = db.get_lorebook_entity(self.session_id, "Dr. Raymond Satou")
        self.assertIsNotNone(lore)
        self.assertEqual(lore.get("mannerisms"), "Adjusts wire-rimmed glasses frequently")
        self.assertEqual(lore.get("race"), "Fennec Fox Half-Beast")

    def test_structured_faculty_depart_cast_event(self):
        """Structured depart cast_event removes Dr. Raymond Satou while keeping Mio Kobayashi."""
        session = {
            "id": self.session_id,
            "current_location": "Chemistry Lab",
            "current_turn_index": 3,
            "current_npcs": [
                {"name": "Dr. Raymond Satou", "race": "Fennec Fox Half-Beast", "role": "Chemistry Teacher"},
                {"name": "Mio Kobayashi", "race": "Human", "role": "Student"},
            ],
            "dialogue_partner": None,
            "dialogue_partners": [],
            "extra_json": {},
        }
        party = [[{"name": "Hero", "user_id": self.user_id}]]
        plan = plan_pre_turn(session, party, [{"label": "Clean up lab equipment"}])
        final_plan, rejections = apply_cast_events(
            plan,
            [{"type": "depart", "npc": "Dr. Raymond Satou", "reason": "Strides out toward faculty prep room"}],
            session,
            party,
        )
        self.assertEqual(rejections, [])
        self.assertIn("Dr. Raymond Satou", final_plan.departing_npcs)
        present_names = [n["name"] for n in final_plan.present_npcs]
        self.assertNotIn("Dr. Raymond Satou", present_names)
        self.assertIn("Mio Kobayashi", present_names)


if __name__ == "__main__":
    unittest.main()
