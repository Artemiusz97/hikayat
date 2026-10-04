"""
Tests for School Roster Deep Integration:
1. Campus Chirper Gossip Feed
2. School Clubs as Active Factions
3. Sibling Web in Relations & Family Tree Codex
4. Direct Messaging & Meetup Sibling/Grade Awareness
"""
import unittest
from unittest.mock import patch, MagicMock
import db
from mechanics import phone, factions, genealogy, school_roster


class TestSchoolSocialSystemsIntegration(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        db.init_db()
        self.user_id = 998877
        self.test_session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        self.session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Westlake Academy ➔ Academic Wing ➔ Classroom 3-B",
            "current_npcs": []
        }
        self.roster = school_roster.ensure_school_directory_exists(self.session)

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (self.test_session_id,))
            conn.execute("DELETE FROM school_directory WHERE session_id=?", (self.test_session_id,))
            conn.execute("DELETE FROM factions WHERE session_id=?", (self.test_session_id,))
            conn.execute("DELETE FROM phone_gossip_feed WHERE session_id=?", (self.test_session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id=?", (self.test_session_id,))
            conn.commit()

    @patch("mechanics.system.phone.call_llm_json")
    async def test_gossip_feed_injects_campus_directory_residents(self, mock_llm):
        """Verify generate_gossip_feed_posts injects campus residents and clubs into system prompt."""
        mock_llm.return_value = {
            "posts": [
                {
                    "author_name": "Campus Watch",
                    "author_handle": "@westlake_eye",
                    "content": "Heard Dr. Thorne caught someone near the Chemistry Lab after curfew.",
                    "tag": "#CampusDrama",
                    "clue_hook": "",
                    "time_ago": "5m ago"
                }
            ]
        }

        posts = await phone.generate_gossip_feed_posts(self.session, force_refresh=True)
        self.assertEqual(len(posts), 1)

        call_args = mock_llm.call_args
        system_prompt = call_args[0][0] if len(call_args[0]) > 0 else call_args[1].get("system_prompt", "")
        self.assertIn("CAMPUS RESIDENTS & STUDENT DIRECTORY CONTEXT", system_prompt)
        self.assertIn("[Senior]", system_prompt)
        self.assertIn("[Faculty]", system_prompt)

    def test_faction_starter_seeding_matches_school_directory_clubs(self):
        """Verify school starter factions have their leadership roster populated from the school directory."""
        seeded_factions = factions.ensure_starter_factions(self.test_session_id, "high_school_drama")
        self.assertTrue(len(seeded_factions) >= 2)

        council_fac = next((f for f in seeded_factions if "council" in f["name"].lower()), None)
        self.assertIsNotNone(council_fac)
        council_roster = council_fac.get("leadership_roster", [])
        self.assertTrue(len(council_roster) >= 2)

        # Confirm roster names originate from the school directory students in the Student Council
        council_students = [c["name"] for c in self.roster if c.get("club") == "Student Council" or "council" in c.get("role", "").lower()]
        roster_names = [m["name"] for m in council_roster]
        overlap = set(council_students).intersection(set(roster_names))
        self.assertTrue(len(overlap) > 0, f"Expected overlap between directory council students {council_students} and faction roster {roster_names}")

    def test_genealogy_sibling_tree_includes_directory_sibling(self):
        """Verify ensure_contact_relations adds the known sibling into the family tree."""
        # Find a character in the roster with a sibling
        sib_char = next((c for c in self.roster if c.get("sibling_name")), None)
        self.assertIsNotNone(sib_char, "Expected at least one character with a sibling in roster")

        contact = {
            "name": sib_char["name"],
            "race": "human",
            "basic_info": {
                "role": sib_char["role"],
                "grade": sib_char["grade"],
                "sibling_name": sib_char["sibling_name"]
            },
            "appearance": {"eyes": "Amber", "hair": "Brown"}
        }

        relations = genealogy.ensure_contact_relations(contact, session_id=self.test_session_id, scenario="high_school_drama")
        family = relations.get("family", [])
        family_first_names = [m.get("first_name") for m in family]
        sib_first = sib_char["sibling_name"].split()[0]
        self.assertIn(sib_first, family_first_names, f"Expected sibling {sib_first} in family tree {family}")

    @patch("mechanics.system.phone.call_llm_json")
    async def test_phone_dm_reply_injects_sibling_and_grade_dynamics(self, mock_llm):
        """Verify generate_contact_dm_reply injects grade and sibling dynamics into the LLM prompt."""
        mock_llm.return_value = {
            "reply_text": "Hey! Yeah, I have some free time between council prep.",
            "affinity_delta": 2
        }

        player_char = {"name": "Artemiusz", "user_id": self.user_id, "cha": 7, "luk": 4}
        contact = {
            "npc_id": "kaito_anderson",
            "name": "Kaito Anderson",
            "relationship_score": 15,
            "track": "platonic",
            "basic_info": {
                "grade": "Senior",
                "role": "Student Council VP",
                "sibling_name": "Maya Anderson"
            }
        }

        # Seed sibling contact with high affinity to test sibling relationship note
        db.upsert_contact(
            session_id=self.test_session_id,
            character_id=0,
            npc_id="maya_anderson",
            name="Maya Anderson",
            delta_score=35,
            track="romantic",
            basic_info={"grade": "Freshman", "role": "Robotics Apprentice"}
        )

        res = await phone.generate_contact_dm_reply(
            session=self.session,
            contact=contact,
            player_char=player_char,
            user_message="Hey Kaito, are you free this afternoon?",
            intent="chat"
        )
        self.assertIn("reply_text", res)

        call_args = mock_llm.call_args
        system_prompt = call_args[0][0] if len(call_args[0]) > 0 else call_args[1].get("system_prompt", "")
        self.assertIn("FAMILY & GRADE DYNAMICS", system_prompt)
        self.assertIn("Senior (Upperclassman)", system_prompt)
        self.assertIn("Maya Anderson", system_prompt)
        self.assertIn("SIBLING RELATIONSHIP NOTE", system_prompt)


if __name__ == "__main__":
    unittest.main()
