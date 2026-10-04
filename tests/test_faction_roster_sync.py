import unittest
import db
from mechanics import factions, school_roster


class TestFactionRosterSync(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.user_id = 994411
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id=?", (self.user_id,))
            conn.execute("DELETE FROM sessions WHERE turn_order LIKE ?", (f"%{self.user_id}%",))
            conn.commit()
        self.char = db.create_character(self.user_id, "RosterTester", "Student", "high_school_drama")
        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id=?", (self.user_id,))
            conn.execute("DELETE FROM sessions WHERE id=?", (self.session_id,))
            conn.execute("DELETE FROM school_directory WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM factions WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM lorebook WHERE session_id=?", (self.session_id,))
            conn.commit()

    def test_student_council_seeded_with_president_and_vp_from_directory(self):
        """Newly seeded school sessions have a Student Council President at Rank 4 and VP at Rank 3."""
        directory = school_roster.ensure_school_directory_exists({"id": self.session_id, "scenario": "high_school_drama"})
        dir_by_name = {c["name"]: c for c in directory}

        seeded = factions.ensure_starter_factions(self.session_id, "high_school_drama")
        council = next(f for f in seeded if f["name"] == "Student Council")
        roster_by_rank = {r["rank"]: r for r in council["leadership_roster"]}

        pres_name = roster_by_rank[4]["name"]
        vp_name = roster_by_rank[3]["name"]
        self.assertIn(pres_name, dir_by_name)
        self.assertIn(vp_name, dir_by_name)
        self.assertEqual(dir_by_name[pres_name]["role"], "Student Council President")
        self.assertEqual(dir_by_name[vp_name]["role"], "Student Council Vice-President")

    def test_drama_club_excludes_faculty_and_martial_arts(self):
        """Drama Club roster never includes Faculty teachers or Varsity Martial Arts Leads."""
        directory = school_roster.ensure_school_directory_exists({"id": self.session_id, "scenario": "high_school_drama"})
        dir_by_name = {c["name"]: c for c in directory}

        seeded = factions.ensure_starter_factions(self.session_id, "high_school_drama")
        drama = next(f for f in seeded if f["name"] == "Drama Club")

        for r_entry in drama["leadership_roster"]:
            m_name = r_entry["name"]
            if m_name in dir_by_name:
                dir_char = dir_by_name[m_name]
                self.assertNotEqual(dir_char["grade"], "Faculty", f"Faculty member {m_name} assigned to Drama Club")
                self.assertNotEqual(dir_char["club"], "Athletic Directorate", f"Athlete {m_name} assigned to Drama Club")
                self.assertNotIn("martial art", dir_char["role"].lower())

        # Rank 4 President should be Drama Senior Director
        rank4_name = next(r["name"] for r in drama["leadership_roster"] if r["rank"] == 4)
        self.assertEqual(dir_by_name[rank4_name]["role"], "Drama Senior Director")

    def test_contact_president_cascades_displaced_vp_and_preserves_lorebook(self):
        """
        When Denise Yamada is introduced as Student Council President in contacts:
        - Rank 4 becomes Denise Yamada
        - The previous Rank 4 holder cascades to Rank 3 (if not already a contact)
        - Denise Yamada's rich narrative description and friendly disposition in lorebook are preserved
        - Denise Yamada is synced into school_directory
        - Repeated calls to sync_faction_rosters_with_contacts are idempotent
        """
        seeded = factions.ensure_starter_factions(self.session_id, "high_school_drama")
        council_before = next(f for f in seeded if f["name"] == "Student Council")
        orig_rank4_name = next(r["name"] for r in council_before["leadership_roster"] if r["rank"] == 4)
        orig_rank3_name = next(r["name"] for r in council_before["leadership_roster"] if r["rank"] == 3)

        rich_desc = (
            "Near the center of the room, Denise Yamada, the Student Council President, "
            "is reviewing a stack of documents with composed authority."
        )
        db.upsert_lorebook_entity(
            session_id=self.session_id,
            entity_type="person",
            name="Denise Yamada",
            description=rich_desc,
            disposition="friendly",
            faction="Student Council",
        )
        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="Denise Yamada",
            name="Denise Yamada",
            basic_info={
                "role": "Student Council President",
                "club": "Student Council",
                "club_role": "President",
                "grade": "Senior",
                "description": rich_desc,
            },
            delta_score=5,
        )

        synced = factions.sync_faction_rosters_with_contacts(self.session_id)
        council_after = next(f for f in synced if f["name"] == "Student Council")
        after_by_rank = {r["rank"]: r["name"] for r in council_after["leadership_roster"]}

        self.assertEqual(after_by_rank[4], "Denise Yamada")
        self.assertEqual(after_by_rank[3], orig_rank4_name)
        self.assertEqual(after_by_rank[2], orig_rank3_name)

        # Verify idempotency on second call
        synced_again = factions.sync_faction_rosters_with_contacts(self.session_id)
        council_again = next(f for f in synced_again if f["name"] == "Student Council")
        again_by_rank = {r["rank"]: r["name"] for r in council_again["leadership_roster"]}
        self.assertEqual(again_by_rank, after_by_rank)

        # Verify Denise's rich lorebook description and friendly disposition were not overwritten
        lb = db.get_lorebook(self.session_id)
        denise_lb = next(p for p in lb["person"] if p["name"] == "Denise Yamada")
        self.assertEqual(denise_lb["description"], rich_desc)
        self.assertEqual(denise_lb["disposition"], "friendly")

        # Verify displaced officer's generic lorebook description updated to Vice President
        displaced_lb = next(p for p in lb["person"] if p["name"] == orig_rank4_name)
        self.assertEqual(displaced_lb["description"], "Student Council Vice President of Student Council.")

        # Verify Denise is now in school_directory
        dir_after = db.get_school_roster(self.session_id)
        denise_dir = next((c for c in dir_after if c["name"] == "Denise Yamada"), None)
        self.assertIsNotNone(denise_dir)
        self.assertEqual(denise_dir["role"], "Student Council President")
        self.assertEqual(denise_dir["club"], "Student Council")

    def test_llm_faction_context_includes_all_starters_and_officers(self):
        """format_llm_faction_context includes all 5 NSFW high school factions, Leader, and Officers."""
        seeded = factions.ensure_starter_factions(self.session_id, "nsfw_high_school_drama")
        ctx_str = factions.format_llm_faction_context(seeded)
        for fac in seeded:
            self.assertIn(fac["name"], ctx_str)
        self.assertIn("|Leader:", ctx_str)
        self.assertIn("|Officers:", ctx_str)


if __name__ == "__main__":
    unittest.main()
