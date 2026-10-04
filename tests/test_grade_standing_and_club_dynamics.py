import unittest
import json
import db
from cogs.contacts import build_contact_detail_embed


class TestGradeStandingAndClubDynamics(unittest.TestCase):
    def setUp(self):
        self.session_id = db.create_session(
            host_user_id=2001,
            mode="solo",
            capacity=1,
            verbosity="normal",
            dialogue_mode="adaptive",
            image_gen_enabled=False,
            scenario="high_school_drama"
        )
        self.fantasy_session_id = db.create_session(
            host_user_id=2002,
            mode="solo",
            capacity=1,
            verbosity="normal",
            dialogue_mode="adaptive",
            image_gen_enabled=False,
            scenario="fantasy"
        )

    def tearDown(self):
        db.delete_session(self.session_id)
        db.delete_session(self.fantasy_session_id)

    def test_newly_generated_students_have_random_grades_and_stability(self):
        """Verify newly generated students get randomly decided grades that do not change arbitrarily."""
        student_names = [
            "Aria Sato", "Kaelen Voss", "Riko Takahashi", "Junpei Mori",
            "Mina Zhao", "Tobias Finch", "Hana Lin", "Daiki Shimizu"
        ]

        assigned_grades = []
        for name in student_names:
            c = db.upsert_contact(
                session_id=self.session_id,
                npc_id=name.lower().replace(" ", "_"),
                name=name,
                basic_info={"description": f"{name} is a student chatting with classmates."},
                delta_score=1
            )
            b = c.get("basic_info", {})
            grade = b.get("grade")
            self.assertIn(grade, ("Freshman", "Sophomore", "Junior", "Senior"))
            assigned_grades.append(grade)

            # Read back immediately to verify stability
            c_read = db.get_contact(self.session_id, name)
            self.assertEqual(c_read["basic_info"].get("grade"), grade)

            # Update score / basic_info without grade to verify it NEVER mutates arbitrarily
            c_updated = db.upsert_contact(
                session_id=self.session_id,
                npc_id=name.lower().replace(" ", "_"),
                name=name,
                basic_info={"description": f"{name} continues studying."},
                delta_score=2
            )
            self.assertEqual(c_updated["basic_info"].get("grade"), grade)

        # Ensure grades are distributed and not all identical
        unique_grades = set(assigned_grades)
        self.assertGreater(len(unique_grades), 1, f"Grades should be varied, but got: {assigned_grades}")

    def test_pregenerated_characters_preserve_exact_grade_and_club(self):
        """Verify pregenerated directory characters retain their exact assigned grade without being overwritten."""
        with db.get_conn() as conn:
            conn.execute(
                """INSERT INTO school_directory (session_id, npc_id, name, role, grade, club, clique, primary_facility, personality_summary, is_hydrated, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1000)""",
                (self.session_id, "natalie_sato", "Natalie Sato", "Drama Club Performer", "Sophomore", "Fine Arts Guild", "Artists", "Auditorium", "Creative artist.",)
            )

        c = db.upsert_contact(
            session_id=self.session_id,
            npc_id="natalie_sato",
            name="Natalie Sato",
            basic_info={"description": "Natalie Sato watches from the stage."},
            delta_score=1
        )
        self.assertEqual(c["basic_info"].get("grade"), "Sophomore")
        self.assertEqual(c["basic_info"].get("club"), "Fine Arts Guild")
        self.assertEqual(c["basic_info"].get("role"), "Drama Club Performer")

    def test_high_school_embed_displays_grade_and_rank_combined(self):
        """Verify High School Drama embed displays '• **Grade / Standing**: [Grade], [Rank]'."""
        # 1. Member
        contact_member = {
            "name": "Aria Sato",
            "relationship_score": 10,
            "basic_info": {
                "grade": "Freshman",
                "club": "Science & Robotics Club",
                "role": "Club Member"
            },
            "appearance": {}
        }
        embed = build_contact_detail_embed(contact_member, "high_school_drama")
        basic_field = next(f for f in embed.fields if f.name == "Basic Details").value
        self.assertIn("• **Grade / Standing**: Freshman, Club Member", basic_field)
        self.assertIn("• **Role**: Club Member", basic_field)
        self.assertIn("• **Faction Affiliation**: Science & Robotics Club", basic_field)

        # 2. Officer / Vice President
        contact_officer = {
            "name": "Yea-ji",
            "relationship_score": 15,
            "basic_info": {
                "grade": "Junior",
                "club": "Drama Club",
                "role": "Club Vice President",
                "club_role": "Vice President"
            },
            "appearance": {}
        }
        embed_officer = build_contact_detail_embed(contact_officer, "high_school_drama")
        basic_officer = next(f for f in embed_officer.fields if f.name == "Basic Details").value
        self.assertIn("• **Grade / Standing**: Junior, Club Vice President", basic_officer)

    def test_other_genres_standing_matches_faction_hierarchy(self):
        """Verify non-school genres display standing that matches faction hierarchy."""
        # Guild Leader in Fantasy
        contact_guildmaster = {
            "name": "Valeria Thorne",
            "relationship_score": 25,
            "basic_info": {
                "faction": "Ironfang Mercenary Guild",
                "role": "Guildmaster"
            },
            "appearance": {}
        }
        embed = build_contact_detail_embed(contact_guildmaster, "fantasy")
        basic_val = next(f for f in embed.fields if f.name == "Basic Details").value
        self.assertIn("• **Grade / Standing**: Guildmaster", basic_val)
        self.assertIn("• **Role**: Guildmaster", basic_val)
        self.assertIn("• **Faction Affiliation**: Ironfang Mercenary Guild", basic_val)

        # Knight Commander in Order
        contact_paladin = {
            "name": "Sir Galahad",
            "relationship_score": 30,
            "basic_info": {
                "faction": "Silver Dawn Order",
                "standing": "Knight Commander"
            },
            "appearance": {}
        }
        embed_paladin = build_contact_detail_embed(contact_paladin, "fantasy")
        basic_paladin = next(f for f in embed_paladin.fields if f.name == "Basic Details").value
        self.assertIn("• **Grade / Standing**: Knight Commander", basic_paladin)

    def test_high_school_student_club_rate(self):
        """Verify ~75% of newly generated students are assigned to a club."""
        names = [f"Student_{i}" for i in range(40)]
        in_club = 0
        for name in names:
            c = db.upsert_contact(
                session_id=self.session_id,
                npc_id=name.lower(),
                name=name,
                basic_info={"description": "A high school classmate in uniform."},
                delta_score=1
            )
            club = c.get("basic_info", {}).get("club") or c.get("basic_info", {}).get("faction")
            if club and str(club).strip().lower() not in ("none", "unaffiliated", "unknown", ""):
                in_club += 1

        ratio = in_club / len(names)
        # Expected ~75%, allow reasonable statistical tolerance for 40 samples (between 60% and 90%)
        self.assertGreaterEqual(ratio, 0.60, f"Expected ~75% club rate, but got {ratio:.2%}")
        self.assertLessEqual(ratio, 0.90, f"Expected ~75% club rate, but got {ratio:.2%}")


if __name__ == "__main__":
    unittest.main()
