"""
Unit tests for the Campus Directory & School Roster System in Hikayat.

Verifies:
1. Roster generation produces 48 characters with proper grade breakdown (12 Faculty, 12 Homeroom, 14 Upperclassmen, 12 Underclassmen).
2. Sibling pairing correctly establishes matching surnames and mutual sibling links.
3. Just-in-time facility queries return exact matching staff/students for specific facilities.
4. Off-campus locations return 0 directory characters to protect context window tokens.
5. Scene presence automatically hydrates directory characters into full contacts.
"""
import unittest
from unittest.mock import patch, MagicMock
import json
import os
import sys

import db
import game_engine
from mechanics import school_roster, mobility


class TestSchoolRosterGenerationAndFacilityPresence(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.user_id = 99887755
        self.test_session_id = db.create_session(self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama")
        from mechanics import locations
        locations.process_llm_location_update(self.test_session_id, "Westlake Academy ➔ Academic Wing ➔ Classroom 3-B", scenario_key="high_school_drama")

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (self.test_session_id,))
            conn.execute("DELETE FROM session_locations WHERE session_id=?", (self.test_session_id,))
            conn.execute("DELETE FROM school_directory WHERE session_id=?", (self.test_session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id=?", (self.test_session_id,))
            conn.execute("DELETE FROM characters WHERE user_id=?", (self.user_id,))
            conn.commit()

    def test_roster_generation_and_composition(self):
        """Verify generation produces 50 characters with balanced grades and sibling links."""
        roster = school_roster.generate_campus_directory(self.test_session_id, scen_key="high_school_drama")
        self.assertEqual(len(roster), 50)

        # Faculty count
        faculty = [c for c in roster if c["grade"] == "Faculty"]
        self.assertEqual(len(faculty), 12)
        fac_roles = {f["role"] for f in faculty}
        self.assertIn("Chemistry Teacher", fac_roles)
        self.assertIn("Mathematics Teacher", fac_roles)
        self.assertIn("Head Varsity Athletics Coach", fac_roles)
        self.assertIn("School Nurse", fac_roles)
        self.assertIn("Head Librarian", fac_roles)

        # Homeroom count
        from mechanics.world.locations import get_session_classroom_name
        c_name = get_session_classroom_name(self.test_session_id, "high_school_drama")
        homeroom = [c for c in roster if c["grade"] == "Junior" and (f"➔ {c_name} ➔" in c["primary_facility"] or "Homeroom" in c["primary_facility"])]
        self.assertEqual(len(homeroom), 12)

        # Upperclassmen & Underclassmen
        seniors = [c for c in roster if c["grade"] == "Senior"]
        juniors = [c for c in roster if c["grade"] == "Junior"]
        sophomores = [c for c in roster if c["grade"] == "Sophomore"]
        freshmen = [c for c in roster if c["grade"] == "Freshman"]

        self.assertGreaterEqual(len(seniors), 7)
        self.assertGreaterEqual(len(juniors), 12)
        self.assertGreaterEqual(len(sophomores), 6)
        self.assertGreaterEqual(len(freshmen), 6)

        # Sibling links
        siblings = [c for c in roster if c.get("sibling_name")]
        self.assertGreaterEqual(len(siblings), 6)  # At least 3 pairs (6 students)
        for sib in siblings:
            sib_partner = next((c for c in roster if c["name"] == sib["sibling_name"]), None)
            self.assertIsNotNone(sib_partner)
            self.assertEqual(sib_partner["sibling_name"], sib["name"])
            import namegen
            sib_sur = namegen.normalize_base_surname(namegen.extract_first_and_last_name(sib["name"])[1])
            partner_sur = namegen.normalize_base_surname(namegen.extract_first_and_last_name(sib_partner["name"])[1])
            self.assertEqual(sib_sur.lower(), partner_sur.lower())

    def test_seed_and_retrieve_from_database(self):
        """Verify ensure_school_directory_exists saves and retrieves the roster in SQLite."""
        session = {"id": self.test_session_id, "scenario": "high_school_drama"}
        roster = school_roster.ensure_school_directory_exists(session)
        self.assertEqual(len(roster), 50)

        db_roster = db.get_school_roster(self.test_session_id)
        self.assertEqual(len(db_roster), 50)

    def test_just_in_time_facility_query(self):
        """Verify querying by facility returns only the relevant resident characters."""
        session = {"id": self.test_session_id, "scenario": "high_school_drama"}
        school_roster.ensure_school_directory_exists(session)

        # Chemistry Lab
        chem_chars = school_roster.get_facility_ambient_characters(self.test_session_id, "Westlake Academy ➔ Science Wing ➔ Chemistry Lab")
        self.assertGreaterEqual(len(chem_chars), 1)
        self.assertTrue(any("Chemistry" in c["role"] for c in chem_chars))

        # Homeroom Classroom 3-B
        from mechanics.world.locations import get_session_classroom_name
        c_name = get_session_classroom_name(self.test_session_id, "high_school_drama")
        homeroom_chars = school_roster.get_facility_ambient_characters(self.test_session_id, "Westlake Academy ➔ Academic Wing ➔ Classroom 3-B", limit=3)
        self.assertEqual(len(homeroom_chars), 3)
        for hc in homeroom_chars:
            self.assertTrue(c_name in hc["primary_facility"] or "Homeroom" in hc["primary_facility"])

        # Gym & Fieldhouse
        gym_chars = school_roster.get_facility_ambient_characters(self.test_session_id, "School Grounds & Athletics ➔ Gym & Fieldhouse ➔ Main Court Area")
        self.assertGreaterEqual(len(gym_chars), 1)
        self.assertTrue(any("Athletics" in c["club"] or "Coach" in c["role"] for c in gym_chars))

        # Off-campus location (e.g. coffee shop or diner)
        off_campus = school_roster.get_facility_ambient_characters(self.test_session_id, "Downtown ➔ Velvet Mug Coffee Shop ➔ Corner Booth")
        self.assertEqual(len(off_campus), 0)

    def test_known_world_text_injection(self):
        """Verify _known_world_text includes ambient facility characters for campus rooms."""
        session = {"id": self.test_session_id, "scenario": "high_school_drama"}
        school_roster.ensure_school_directory_exists(session)

        text = game_engine._known_world_text(
            session_id=self.test_session_id,
            current_location="Westlake Academy ➔ Science Wing ➔ Chemistry Lab",
            current_npcs=[]
        )
        self.assertIn("Campus Directory & Ambient Residents", text)
        self.assertIn("Chemistry Teacher", text)

    def test_scene_presence_hydrates_directory_character(self):
        """Verify that when a directory student appears in a scene, they are automatically hydrated into contacts and lorebook."""
        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Westlake Academy ➔ Academic Wing ➔ Classroom 3-B",
            "current_npcs": []
        }
        school_roster.ensure_school_directory_exists(session)
        db_roster = db.get_school_roster(self.test_session_id)
        student_peer = next(c for c in db_roster if c["grade"] != "Faculty")

        result = {
            "outcome_narrative": f"Artemiusz walks into homeroom where {student_peer['name']} is chatting.",
            "next_narrative": f"{student_peer['name']} turns and greets you.",
            "npcs_present": [{"name": student_peer["name"], "role": student_peer["role"]}]
        }
        new_loc = "Westlake Academy ➔ Academic Wing ➔ Classroom 3-B"
        old_loc = "Westlake Academy ➔ Main Hallways ➔ 2nd Floor Corridor"

        final_npcs = game_engine.process_scene_npcs(result, session, new_loc, old_loc, actions=[])
        npc_names = [n["name"] if isinstance(n, dict) else n for n in final_npcs]
        self.assertIn(student_peer["name"], npc_names)

        # Verify contacts table now has the hydrated contact
        contact = db.get_contact(self.test_session_id, student_peer["npc_id"])
        self.assertIsNotNone(contact)
        self.assertEqual(contact["name"], student_peer["name"])
        self.assertEqual(contact["basic_info"]["role"], student_peer["role"])

        # Verify lorebook entry
        lore_entry = next((p for p in db.get_lorebook(self.test_session_id).get("person", []) if p["name"] == student_peer["name"]), None)
        self.assertIsNotNone(lore_entry)

    def test_dynamic_personality_across_sessions(self):
        """Verify that different sessions produce different 4-layer psychological attributes for identical roles."""
        roster_a = school_roster.generate_campus_directory(session_id=101, scen_key="high_school_drama")
        roster_b = school_roster.generate_campus_directory(session_id=202, scen_key="high_school_drama")

        # Check that summaries include 4-layer attributes
        vp_a = next(c for c in roster_a if "Vice-President" in c["role"])
        vp_b = next(c for c in roster_b if "Vice-President" in c["role"])

        self.assertIn("Drive:", vp_a["personality_summary"])
        self.assertIn("Flaw:", vp_a["personality_summary"])
        self.assertIn("Mannerism:", vp_a["personality_summary"])

        # Compare across sessions - should differ in drive, flaw, or mannerism
        self.assertNotEqual(vp_a["personality_summary"], vp_b["personality_summary"])

        # Check faculty contradiction
        chem_a = next(c for c in roster_a if "Chemistry" in c["role"])
        chem_b = next(c for c in roster_b if "Chemistry" in c["role"])
        self.assertIn("Contradiction:", chem_a["personality_summary"])
        self.assertNotEqual(chem_a["personality_summary"], chem_b["personality_summary"])

    def test_deterministic_race_generation_and_sibling_parity(self):
        """Verify that directory generation assigns persistent races and guarantees sibling parity."""
        # Test in furry high school drama
        roster_furry = school_roster.generate_campus_directory(session_id=self.test_session_id, scen_key="nsfw_furry_high_school_drama")
        self.assertEqual(len(roster_furry), 50)

        # Every character must have an assigned race
        for c in roster_furry:
            self.assertTrue(bool(c.get("race")), f"Character {c['name']} has empty race")

        # Sibling pairs must have matching races
        siblings = [c for c in roster_furry if c.get("sibling_name")]
        self.assertGreaterEqual(len(siblings), 6)
        for sib in siblings:
            partner = next((c for c in roster_furry if c["name"] == sib["sibling_name"]), None)
            self.assertIsNotNone(partner)
            self.assertEqual(sib["race"], partner["race"], f"Sibling race mismatch between {sib['name']} and {partner['name']}")

        # Determinism check across identical seeds
        roster_furry_2 = school_roster.generate_campus_directory(session_id=self.test_session_id, scen_key="nsfw_furry_high_school_drama")
        for c1, c2 in zip(roster_furry, roster_furry_2):
            self.assertEqual(c1["name"], c2["name"])
            self.assertEqual(c1["race"], c2["race"])

        # Test in regular high school drama (all human)
        roster_human = school_roster.generate_campus_directory(session_id=self.test_session_id, scen_key="high_school_drama")
        for c in roster_human:
            self.assertEqual(c["race"], "human")




class TestSchoolRosterModernization(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.session_id = 99881122

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (self.session_id,))
            conn.execute("DELETE FROM school_directory WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM lorebook WHERE session_id=?", (self.session_id,))
            conn.commit()

    def test_dynamic_cultural_surnames_and_lineages(self):
        """Verify directories across different seeds sample diverse cultural family lineages."""
        roster_a = school_roster.generate_campus_directory(session_id=111, scen_key="high_school_drama")
        roster_b = school_roster.generate_campus_directory(session_id=999, scen_key="high_school_drama")

        sibs_a = {c["sibling_name"] for c in roster_a if c.get("sibling_name")}
        sibs_b = {c["sibling_name"] for c in roster_b if c.get("sibling_name")}
        self.assertGreaterEqual(len(sibs_a), 6)
        self.assertGreaterEqual(len(sibs_b), 6)

        import namegen
        # Diverse session seeds should produce different sibling surname pools
        surnames_a = {namegen.normalize_base_surname(namegen.extract_first_and_last_name(n)[1]) for n in sibs_a}
        surnames_b = {namegen.normalize_base_surname(namegen.extract_first_and_last_name(n)[1]) for n in sibs_b}
        self.assertNotEqual(surnames_a, surnames_b)

    def test_sibling_kinship_labels_and_pronoun_fidelity(self):
        """Verify sibling peer generation formats correct pronouns and computes kinship kinematics."""
        contact_ref = {
            "name": "Maya Kowalska",
            "gender": "female",
            "basic_info": {"grade": "Junior"},
            "relations": {
                "family": [
                    {"name": "Jakub Kowalski", "gender": "male", "relation": "older brother", "grade": "Senior"}
                ]
            }
        }
        # Generate male sibling peer
        peer = school_roster.generate_sibling_student_peer(
            session_id=self.session_id,
            sibling_name="Jakub Kowalski",
            known_contact=contact_ref,
            scen_key="high_school_drama",
            grade_override="Senior",
            gender="male",
            relation_type="older brother"
        )
        self.assertEqual(peer["gender"], "male")
        # Ensure pronouns in summary and mannerisms are masculine
        summary_and_manners = f"{peer['personality_summary']} {peer['mannerisms']}"
        self.assertNotIn("her heels", summary_and_manners)
        self.assertNotIn("her knuckles", summary_and_manners)
        self.assertNotIn("her own", summary_and_manners)

        # Test Kinship resolution helper directly
        self.assertEqual(school_roster._resolve_sibling_relation("Senior", "male", "Freshman"), "Older brother")
        self.assertEqual(school_roster._resolve_sibling_relation("Freshman", "female", "Senior"), "Younger sister")
        self.assertEqual(school_roster._resolve_sibling_relation("Junior", "male", "Junior"), "Twin brother")

    def test_faculty_hydration_and_formal_titles(self):
        """Verify that faculty members hydrate into contacts with platonic mentor track and formal titles."""
        roster = school_roster.generate_campus_directory(session_id=self.session_id, scen_key="high_school_drama")
        fac_member = next(c for c in roster if c["grade"] == "Faculty")
        self.assertTrue(bool(fac_member.get("formal_title")))

        success = school_roster.hydrate_school_character(self.session_id, fac_member)
        self.assertTrue(success)

        contact = db.get_contact(self.session_id, fac_member["npc_id"])
        self.assertIsNotNone(contact)
        self.assertEqual(contact["track"], "platonic")
        self.assertTrue(contact["basic_info"]["is_faculty"])
        self.assertIn("Faculty /", contact["basic_info"]["role"])
        self.assertEqual(contact["basic_info"]["disposition"], "faculty_mentor")
        self.assertEqual(contact["basic_info"]["formal_title"], fac_member["formal_title"])

    def test_dynamic_peer_species_and_schema_parity(self):
        """Verify generate_dynamic_student_peer sets normalized race and structured mannerisms."""
        peer = school_roster.generate_dynamic_student_peer(
            session_id=self.session_id,
            scen_key="nsfw_furry_high_school_drama",
            seed=42
        )
        self.assertTrue(bool(peer.get("race")))
        self.assertNotEqual(peer["race"], "human")
        self.assertTrue(bool(peer.get("mannerisms")))
        self.assertTrue(bool(peer.get("speech_style")))
        self.assertEqual(peer["is_hydrated"], 0)


if __name__ == "__main__":
    unittest.main()

