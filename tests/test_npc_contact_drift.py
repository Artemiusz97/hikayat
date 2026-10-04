import unittest
import db
from mechanics.social.factions import ensure_session_factions_seeded
import game_engine


class TestFactionLeaderLorebook(unittest.TestCase):
    """Fix C: faction leaders are seeded into lorebook on faction discovery."""

    def setUp(self):
        for uid in (91001, 91002):
            with db.get_conn() as conn:
                conn.execute("DELETE FROM characters WHERE user_id=?", (uid,))
                conn.execute("DELETE FROM sessions WHERE turn_order LIKE ?", (f"%{uid}%",))

    def test_faction_leaders_seeded_into_lorebook(self):
        uid = 91001
        db.create_character(uid, "LoreTest", "Student", "high_school_drama")
        sess_id = db.create_session(uid, "solo", 1, "vivid", "individual", False, scenario="high_school_drama")
        factions = ensure_session_factions_seeded(sess_id, "high_school_drama")
        self.assertGreater(len(factions), 0)
        expected_names = set()
        for f in factions:
            for member in (f.get("leadership_roster") or []):
                if not member.get("is_vacant") and member.get("name"):
                    expected_names.add(member["name"].lower().strip())
        with db.get_conn() as conn:
            rows = conn.execute("SELECT name FROM lorebook WHERE session_id=?", (sess_id,)).fetchall()
        lorebook_names = {r[0].lower().strip() for r in rows}
        for name in expected_names:
            self.assertIn(name, lorebook_names, f"Faction leader not seeded: {name}")

    def test_faction_leader_lorebook_has_description(self):
        uid = 91002
        db.create_character(uid, "TitleTest", "Student", "high_school_drama")
        sess_id = db.create_session(uid, "solo", 1, "vivid", "individual", False, scenario="high_school_drama")
        ensure_session_factions_seeded(sess_id, "high_school_drama")
        with db.get_conn() as conn:
            rows = conn.execute("SELECT name, description FROM lorebook WHERE session_id=?", (sess_id,)).fetchall()
        for r in rows:
            self.assertTrue(r[1], f"Empty description for {r[0]}")


class TestPartialRoleNameSanitizer(unittest.TestCase):
    """Fix B: _sanitize_outcome_person_names catches partial-role aliases."""

    def _seed_council(self, sess_id):
        db.upsert_faction(
            session_id=sess_id, name="Student Council", delta_score=0,
            category="council", hq_location_id="", notes="", hierarchy_template="council",
            leadership_roster=[
                {"rank": 4, "title": "Student Council President", "name": "Denise Yamada",
                 "is_player": False, "is_vacant": False},
                {"rank": 3, "title": "Student Council Vice President", "name": "Tommaso Laurent",
                 "is_player": False, "is_vacant": False},
            ]
        )

    def setUp(self):
        for uid in (91010, 91011, 91012):
            with db.get_conn() as conn:
                conn.execute("DELETE FROM characters WHERE user_id=?", (uid,))
                conn.execute("DELETE FROM sessions WHERE turn_order LIKE ?", (f"%{uid}%",))

    def test_exact_role_title_resolved(self):
        uid = 91010
        db.create_character(uid, "RoleTest", "Student", "high_school_drama")
        sess_id = db.create_session(uid, "solo", 1, "vivid", "individual", False, scenario="high_school_drama")
        self._seed_council(sess_id)
        outcome = {
            "new_entities": [{"type": "person", "name": "Student Council President", "description": "Desk."}],
            "npcs_present": [], "relationship_updates": [], "character_outcomes": [],
        }
        game_engine._sanitize_outcome_person_names(outcome, sess_id, "high_school_drama")
        self.assertEqual(outcome["new_entities"][0]["name"], "Denise Yamada")

    def test_partial_role_alias_resolved(self):
        uid = 91011
        db.create_character(uid, "PartialTest", "Student", "high_school_drama")
        sess_id = db.create_session(uid, "solo", 1, "vivid", "individual", False, scenario="high_school_drama")
        self._seed_council(sess_id)
        outcome = {
            "new_entities": [{"type": "person", "name": "President Sarah", "description": "Commanding."}],
            "npcs_present": [{"name": "President Sarah"}],
            "relationship_updates": [{"npc_name": "President Sarah", "delta_score": 1}],
            "character_outcomes": [],
        }
        game_engine._sanitize_outcome_person_names(outcome, sess_id, "high_school_drama")
        self.assertEqual(outcome["new_entities"][0]["name"], "Denise Yamada")
        self.assertEqual(outcome["npcs_present"][0]["name"], "Denise Yamada")
        self.assertEqual(outcome["relationship_updates"][0]["npc_name"], "Denise Yamada")

    def test_normal_name_not_altered(self):
        uid = 91012
        db.create_character(uid, "NormalTest", "Student", "high_school_drama")
        sess_id = db.create_session(uid, "solo", 1, "vivid", "individual", False, scenario="high_school_drama")
        self._seed_council(sess_id)
        outcome = {
            "new_entities": [{"type": "person", "name": "Luna", "description": "Info broker."}],
            "npcs_present": [{"name": "Luna"}],
            "relationship_updates": [{"npc_name": "Luna", "delta_score": 2}],
            "character_outcomes": [],
        }
        game_engine._sanitize_outcome_person_names(outcome, sess_id, "high_school_drama")
        self.assertEqual(outcome["new_entities"][0]["name"], "Luna")
        self.assertEqual(outcome["npcs_present"][0]["name"], "Luna")


class TestFactionLeaderContactGate(unittest.TestCase):
    """Fix A: Faction leaders get a contact row even at neutral disposition."""

    def setUp(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id=?", (91020,))
            conn.execute("DELETE FROM sessions WHERE turn_order LIKE ?", ("%91020%",))

    def test_faction_leader_contact_at_neutral(self):
        uid = 91020
        char = db.create_character(uid, "GateTest", "Student", "high_school_drama")
        char_id = char["id"]
        sess_id = db.create_session(uid, "solo", 1, "vivid", "individual", False, scenario="high_school_drama")
        ensure_session_factions_seeded(sess_id, "high_school_drama")
        factions = db.get_factions(sess_id)
        denise = None
        for f in factions:
            for r in (f.get("leadership_roster") or []):
                if r.get("title") == "Student Council President":
                    denise = r["name"]
        self.assertIsNotNone(denise)
        self.assertIsNone(db.get_contact(sess_id, denise, character_id=char_id))
        is_faction_leader = False
        for _f in factions:
            for _r in (_f.get("leadership_roster") or []):
                if _r.get("name") and _r["name"].lower().strip() == denise.lower().strip():
                    is_faction_leader = True
                    break
            if is_faction_leader:
                break
        self.assertTrue(is_faction_leader)
        db.upsert_contact(session_id=sess_id, character_id=char_id, npc_id=denise,
                          name=denise, basic_info={"description": "Council President."},
                          delta_score=0, new_traits=[], new_preferences=[],
                          race="human", gender="female", appearance={})
        saved = db.get_contact(sess_id, denise, character_id=char_id)
        self.assertIsNotNone(saved)
        self.assertEqual(saved["name"], denise)


class TestTieredNPCTrackerPersistence(unittest.TestCase):
    """Fix D: NPC tracker uses tiered location logic."""

    def test_tier3_subarea_same_primary(self):
        from mechanics.world.locations import get_zone_location_name, get_primary_location_name
        old = "Oakhaven Academy \u2794 Student Council Room \u2794 Main Office"
        new = "Oakhaven Academy \u2794 Student Council Room \u2794 Doorway"
        self.assertEqual(get_zone_location_name(old), get_zone_location_name(new))
        self.assertEqual(get_primary_location_name(old), get_primary_location_name(new))

    def test_tier2_room_change_keeps_engaged(self):
        from mechanics.world.locations import get_zone_location_name, get_primary_location_name
        old = "Oakhaven Academy \u2794 Student Council Room \u2794 Main Office"
        new = "Oakhaven Academy \u2794 Hallway \u2794 Corridor"
        self.assertEqual(get_zone_location_name(old), get_zone_location_name(new))
        self.assertNotEqual(get_primary_location_name(old), get_primary_location_name(new))
        current_npcs = [
            {"name": "Denise Yamada", "level": 5},
            {"name": "Bystander", "level": 2},
            {"name": "Companion", "hp": 80, "max_hp": 80},
        ]
        active = {"denise yamada"}
        retained = [n for n in current_npcs if isinstance(n, dict) and
                    (n.get("hp") is not None or n.get("name", "").lower().strip() in active)]
        names = [n["name"] for n in retained]
        self.assertIn("Denise Yamada", names)
        self.assertIn("Companion", names)
        self.assertNotIn("Bystander", names)

    def test_tier1_zone_clears_non_companions(self):
        from mechanics.world.locations import get_zone_location_name
        old = "Oakhaven Academy \u2794 Student Council Room \u2794 Main Office"
        new = "Residential Area \u2794 Artemiusz House \u2794 Living Room"
        self.assertNotEqual(get_zone_location_name(old), get_zone_location_name(new))
        current_npcs = [{"name": "Denise Yamada", "level": 5}, {"name": "Companion", "hp": 80, "max_hp": 80}]
        retained = [n for n in current_npcs if isinstance(n, dict) and n.get("hp") is not None]
        names = [n["name"] for n in retained]
        self.assertNotIn("Denise Yamada", names)
        self.assertIn("Companion", names)


class TestFactionContactRosterSync(unittest.TestCase):
    """Verify that faction leadership rosters stay synchronized with established contacts."""

    def setUp(self):
        self.uid = 92001
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id=?", (self.uid,))
            conn.execute("DELETE FROM sessions WHERE turn_order LIKE ?", (f"%{self.uid}%",))

    def test_sync_faction_rosters_with_contacts(self):
        from mechanics.social.factions import sync_faction_rosters_with_contacts, ensure_session_factions_seeded
        db.create_character(self.uid, "SyncTester", "Student", "high_school_drama")
        sess_id = db.create_session(self.uid, "solo", 1, "vivid", "individual", False, scenario="high_school_drama")
        
        # Seed factions (starts with procedural names)
        ensure_session_factions_seeded(sess_id, "high_school_drama")

        # Now establish actual story contacts with roles
        db.upsert_contact(sess_id, "yea_ji", "Yea-ji Kang", basic_info={"role": "Student Council President", "club": "Student Council"})
        db.upsert_contact(sess_id, "amelie", "Amélie Yamashita", basic_info={"role": "Student Council Vice President", "club": "Student Council"})
        db.upsert_contact(sess_id, "sophia", "Sophia", basic_info={"role": "Council Secretary", "club": "Student Council"})

        # Sync factions
        updated_factions = sync_faction_rosters_with_contacts(sess_id)
        council = next(f for f in updated_factions if "Council" in f["name"])
        roster_map = {r["title"]: r["name"] for r in council["leadership_roster"]}

        self.assertEqual(roster_map["Student Council President"], "Yea-ji Kang")
        self.assertEqual(roster_map["Student Council Vice President"], "Amélie Yamashita")
        self.assertEqual(roster_map["Council Secretary"], "Sophia")


if __name__ == "__main__":
    unittest.main()
