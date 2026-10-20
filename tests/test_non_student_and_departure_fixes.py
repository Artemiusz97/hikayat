import unittest
import db
import game_engine
from mechanics.social.relationships import is_contact_eligible


class TestNonStudentAndDepartureFixes(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.user_id = 99881122
        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (self.session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM lorebook WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM school_directory WHERE session_id=?", (self.session_id,))
            conn.commit()

    def test_non_student_faculty_not_contact_eligible(self):
        """Verify teachers, faculty, staff, and adults are not contact-eligible in high school."""
        self.assertFalse(is_contact_eligible(
            name="Dr. Raymond Satou",
            role="Chemistry Teacher",
            description="Strict fennec teacher",
            scenario="high_school_drama",
            session_id=self.session_id
        ))
        self.assertFalse(is_contact_eligible(
            name="Coach Tanaka",
            role="Head Coach",
            description="Athletic director",
            scenario="high_school_drama",
            session_id=self.session_id
        ))
        # Fellow students ARE eligible
        self.assertTrue(is_contact_eligible(
            name="Mio Kobayashi",
            role="Student",
            description="Quiet classmate",
            scenario="high_school_drama",
            session_id=self.session_id
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

        # Store basic info in lorebook
        db.upsert_lorebook_entity(
            session_id=self.session_id,
            entity_type="person",
            name="Dr. Raymond Satou",
            description="Chemistry teacher",
            mannerisms="Adjusts wire-rimmed glasses frequently",
            race="Fennec Fox Half-Beast",
            appearance={"coat_color": "Golden-cream fur", "eye_color": "Amber"},
            gender="male"
        )
        lore = db.get_lorebook_entity(self.session_id, "Dr. Raymond Satou")
        self.assertIsNotNone(lore)
        self.assertEqual(lore.get("mannerisms"), "Adjusts wire-rimmed glasses frequently")
        self.assertEqual(lore.get("race"), "Fennec Fox Half-Beast")

    def test_epithet_departure_extraction_fennec_half_beast(self):
        """Verify extract_departed_npcs_from_narrative captures departures using epithets and movement verbs."""
        cand_npcs = [
            {"name": "Dr. Raymond Satou", "race": "Fennec Fox Half-Beast", "role": "Chemistry Teacher"},
            {"name": "Mio Kobayashi", "race": "Human", "role": "Student"}
        ]
        prose = (
            "With that, the fennec half-beast pivots sharply on their heel and strides out "
            "toward faculty prep room, bushy cream tail disappearing around corridor corner."
        )
        departed = game_engine.extract_departed_npcs_from_narrative(prose, cand_npcs)
        self.assertIn("Dr. Raymond Satou", departed)
        self.assertNotIn("Mio Kobayashi", departed)

    def test_epithet_departure_extraction_title_and_stride(self):
        """Verify extract_departed_npcs_from_narrative captures title with directional strides."""
        cand_npcs = [
            {"name": "Dr. Raymond Satou", "race": "Fennec Fox Half-Beast", "role": "Chemistry Teacher"},
        ]
        prose = "Dr. Satou strides out toward the faculty room."
        departed = game_engine.extract_departed_npcs_from_narrative(prose, cand_npcs)
        self.assertIn("Dr. Raymond Satou", departed)
