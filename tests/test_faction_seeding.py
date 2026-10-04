import unittest
import db
import namegen
from mechanics.social.factions import ensure_session_factions_seeded, FACTION_HIERARCHIES


class TestFactionSeeding(unittest.TestCase):
    def setUp(self):
        for uid in (88001, 88002, 88003, 88004, 88005):
            with db.get_conn() as conn:
                conn.execute("DELETE FROM characters WHERE user_id=?", (uid,))
                conn.execute("DELETE FROM sessions WHERE turn_order LIKE ?", (f"%{uid}%",))

    def test_high_school_drama_seeding(self):
        user_id = 88001
        db.create_character(user_id, "SchoolTester", "Student", "high_school_drama")
        sess_id = db.create_session(user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama")

        factions = ensure_session_factions_seeded(sess_id, "high_school_drama")
        self.assertGreaterEqual(len(factions), 4)

        names = [f["name"] for f in factions]
        templates = [f["hierarchy_template"] for f in factions]

        # Fixed institutional factions
        self.assertIn("Student Council", names)
        self.assertIn("Drama Club", names)
        self.assertIn("Occult & Mystery Club", names)

        # Templates
        self.assertIn("council", templates)
        self.assertIn("club", templates)
        self.assertIn("delinquents", templates)

        # Verify rosters
        for fac in factions:
            roster = fac.get("leadership_roster") or []
            self.assertEqual(len(roster), 4)
            for member in roster:
                self.assertTrue(member.get("name"))
                self.assertFalse(namegen.is_generic_role_name(member["name"]))

    def test_nsfw_high_school_drama_seeding(self):
        user_id = 88002
        db.create_character(user_id, "NSFWTester", "Student", "nsfw_high_school_drama")
        sess_id = db.create_session(user_id, "solo", 1, "vivid", "individual", False, scenario="nsfw_high_school_drama")

        factions = ensure_session_factions_seeded(sess_id, "nsfw_high_school_drama")
        # Should have 5 factions (Council, Drama, Occult, Delinquents, NSFW secret circle)
        self.assertGreaterEqual(len(factions), 5)

        names = [f["name"] for f in factions]
        self.assertIn("Student Council", names)
        self.assertIn("Drama Club", names)
        self.assertIn("Occult & Mystery Club", names)

        # Check that one of the clubs is from the NSFW pool
        nsfw_pool = namegen._DATA.get("high_school_drama", {}).get("factions", {}).get("nsfw", [])
        has_nsfw_faction = any(n in nsfw_pool for n in names)
        self.assertTrue(has_nsfw_faction)

    def test_cyberpunk_dynamic_seeding(self):
        user_id = 88003
        db.create_character(user_id, "CyberTester", "Netrunner", "cyberpunk")
        sess_id = db.create_session(user_id, "solo", 1, "vivid", "individual", False, scenario="cyberpunk")

        factions = ensure_session_factions_seeded(sess_id, "cyberpunk")
        self.assertEqual(len(factions), 4)

        templates = [f["hierarchy_template"] for f in factions]
        self.assertEqual(templates.count("corpo"), 2)
        self.assertEqual(templates.count("syndicate"), 1)
        self.assertEqual(templates.count("delinquents"), 1)

        for fac in factions:
            roster = fac.get("leadership_roster") or []
            self.assertEqual(len(roster), 4)
            for member in roster:
                self.assertTrue(member.get("name"))
                self.assertFalse(namegen.is_generic_role_name(member["name"]))

    def test_steampunk_dynamic_seeding(self):
        user_id = 88004
        db.create_character(user_id, "SteamTester", "Engineer", "steampunk")
        sess_id = db.create_session(user_id, "solo", 1, "vivid", "individual", False, scenario="steampunk")

        factions = ensure_session_factions_seeded(sess_id, "steampunk")
        self.assertEqual(len(factions), 3)

        templates = [f["hierarchy_template"] for f in factions]
        self.assertIn("guild", templates)
        self.assertIn("delinquents", templates)
        self.assertIn("syndicate", templates)

    def test_fantasy_seeding(self):
        user_id = 88005
        db.create_character(user_id, "FantasyTester", "Warrior", "fantasy")
        sess_id = db.create_session(user_id, "solo", 1, "vivid", "individual", False, scenario="fantasy")

        factions = ensure_session_factions_seeded(sess_id, "fantasy")
        self.assertEqual(len(factions), 3)

        names = [f["name"] for f in factions]
        self.assertIn("Adventurers Guild", names)

        templates = [f["hierarchy_template"] for f in factions]
        self.assertIn("guild", templates)
        self.assertEqual(templates.count("order"), 2)


if __name__ == "__main__":
    unittest.main()
