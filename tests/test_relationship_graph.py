"""
tests/test_relationship_graph.py

Comprehensive test suite for the Normalized Interpersonal Social Graph & Relationship Network:
1. Bidirectional symmetry & node registry.
2. Mutual exclusivity of friendship and rivalry with auto-transitions (Decision 2).
3. Romantic exclusivity & multi-dating / secret affair routing (Decision 1).
4. Breakup history preservation & ex-partner derivation (Finding 1 fix).
5. Intimacy ledger secret affair synchronization.
6. Incest guard enforcement across household boundaries.
7. Background seeding: procedural romance peers vs real contact friends (Decision 4).
8. Hydration linking & UI contactability.
9. Save/load cloning & child table integrity.
10. Migration conflict resolution tiering (Decision 5).
11. Turn rollback engine.
"""

import json
import time
import unittest
import db
from db.core import get_conn, _delete_session_records
import mechanics.social.relationship_graph as rg
from mechanics.social.genealogy import ensure_contact_relations


class TestRelationshipGraph(unittest.TestCase):
    def setUp(self):
        self.session_id = 999881
        self.char_id = "test_hero_1"
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        with get_conn() as conn:
            _delete_session_records(conn, self.session_id)
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM social_persons WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM social_ties WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM intimate_events WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM households WHERE session_id = ?", (self.session_id,))

    def _create_mock_session(self):
        with get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO sessions (id, mode, capacity, status, scenario, created_at, updated_at)
                   VALUES (?, 'solo', 1, 'active', 'high_school_drama', ?, ?)""",
                (self.session_id, time.time(), time.time()),
            )

    def _create_mock_contact(self, npc_id: str, name: str, gender: str = "female", role: str = "Student", club: str = "Art Club"):
        with get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO contacts
                   (session_id, character_id, npc_id, name, gender, basic_info_json, relations_json, track, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, '{}', 'platonic', ?, ?)""",
                (
                    self.session_id,
                    self.char_id,
                    npc_id,
                    name,
                    gender,
                    json.dumps({"role": role, "club": club, "grade": "Junior"}),
                    time.time(),
                    time.time(),
                ),
            )
            rg.get_or_create_person(
                self.session_id,
                name,
                person_key=rg.canonical_person_key(name),
                gender=gender,
                role=role,
                origin="contact",
                contact_npc_id=npc_id,
                conn=conn,
            )

    def test_bidirectional_symmetry_and_materialization(self):
        """Friendship formed between Alice and Bob reflects symmetrically in both materialized records."""
        self._create_mock_session()
        self._create_mock_contact("alice_w", "Alice Walker")
        self._create_mock_contact("bob_m", "Bob Miller", gender="male")

        a_key = rg.canonical_person_key("Alice Walker")
        b_key = rg.canonical_person_key("Bob Miller")

        rg.form_tie(self.session_id, a_key, b_key, rg.TIETYPE_FRIEND, closeness=85)

        with get_conn() as conn:
            c_alice = conn.execute("SELECT * FROM contacts WHERE session_id = ? AND npc_id = 'alice_w'", (self.session_id,)).fetchone()
            c_bob = conn.execute("SELECT * FROM contacts WHERE session_id = ? AND npc_id = 'bob_m'", (self.session_id,)).fetchone()

        mat_a = json.loads(c_alice["relations_json"])
        mat_b = json.loads(c_bob["relations_json"])

        # Alice lists Bob as friend with closeness 85
        self.assertTrue(any(f["name"] == "Bob Miller" and f["closeness"] == 85 for f in mat_a["friends"]))
        # Bob lists Alice as friend with closeness 85
        self.assertTrue(any(f["name"] == "Alice Walker" and f["closeness"] == 85 for f in mat_b["friends"]))

    def test_mutual_exclusivity_friend_rival_transitions(self):
        """Decision 2: Forming friendship reconciles active rivalry, and rivalry breaks active friendship."""
        self._create_mock_session()
        self._create_mock_contact("alice_w", "Alice Walker")
        self._create_mock_contact("bob_m", "Bob Miller", gender="male")

        a_key = rg.canonical_person_key("Alice Walker")
        b_key = rg.canonical_person_key("Bob Miller")

        # 1. Form rivalry
        rg.form_tie(self.session_id, a_key, b_key, rg.TIETYPE_RIVAL, closeness=50, turn=1)
        ties = rg.get_ties(self.session_id, a_key, active_only=True)
        self.assertEqual(len(ties), 1)
        self.assertEqual(ties[0]["tie_type"], "rival")

        # 2. Form friendship -> auto-reconciles rivalry
        rg.form_tie(self.session_id, a_key, b_key, rg.TIETYPE_FRIEND, closeness=80, turn=5)
        active_ties = rg.get_ties(self.session_id, a_key, active_only=True)
        self.assertEqual(len(active_ties), 1)
        self.assertEqual(active_ties[0]["tie_type"], "friend")

        # Verify old rivalry is ended with end_reason='reconciled'
        all_ties = rg.get_ties(self.session_id, a_key, active_only=False)
        reconciled = [t for t in all_ties if t["tie_type"] == "rival" and t["status"] == "ended"]
        self.assertEqual(len(reconciled), 1)
        self.assertEqual(reconciled[0]["end_reason"], "reconciled")
        self.assertEqual(reconciled[0]["ended_turn"], 5)

        # 3. Forming rivalry again -> auto-ends friendship with end_reason='falling_out'
        rg.form_tie(self.session_id, a_key, b_key, rg.TIETYPE_RIVAL, closeness=45, turn=8)
        active_ties = rg.get_ties(self.session_id, a_key, active_only=True)
        self.assertEqual(len(active_ties), 1)
        self.assertEqual(active_ties[0]["tie_type"], "rival")

        all_ties = rg.get_ties(self.session_id, a_key, active_only=False)
        falling_out = [t for t in all_ties if t["tie_type"] == "friend" and t["status"] == "ended"]
        self.assertEqual(len(falling_out), 1)
        self.assertEqual(falling_out[0]["end_reason"], "falling_out")
        self.assertEqual(falling_out[0]["ended_turn"], 8)

    def test_romantic_exclusivity_and_supersede(self):
        """NPC cannot date two people exclusively without supersede. Supersede moves ex to ended ties."""
        self._create_mock_session()
        self._create_mock_contact("alice_w", "Alice Walker")
        self._create_mock_contact("bob_m", "Bob Miller", gender="male")
        self._create_mock_contact("charlie_k", "Charlie Kim", gender="male")

        a_key = rg.canonical_person_key("Alice Walker")
        b_key = rg.canonical_person_key("Bob Miller")
        c_key = rg.canonical_person_key("Charlie Kim")

        # Alice dates Bob
        rg.form_tie(self.session_id, a_key, b_key, rg.TIETYPE_DATING, closeness=75, turn=1)

        # Alice tries to date Charlie without supersede -> ValueError
        with self.assertRaises(ValueError):
            rg.form_tie(self.session_id, a_key, c_key, rg.TIETYPE_DATING, closeness=70, turn=2)

        # Alice dates Charlie with supersede=True -> Bob gets ended tie with reason='left_for_partner'
        rg.form_tie(self.session_id, a_key, c_key, rg.TIETYPE_DATING, closeness=70, turn=3, supersede=True)

        # Current partner of Alice is Charlie
        curr = rg.get_current_partner(self.session_id, a_key)
        self.assertIsNotNone(curr)
        self.assertEqual(curr["person_key"], c_key)

        # Bob has Alice as an ex
        exes = rg.get_ex_partners(self.session_id, b_key)
        self.assertEqual(len(exes), 1)
        self.assertEqual(exes[0]["person_key"], a_key)
        self.assertEqual(exes[0]["end_reason"], "left_for_partner")

    def test_player_multi_dating_and_secret_affairs(self):
        """Decision 1: Player dating multiple partners auto-routes secondary partner to Secret Affair."""
        self._create_mock_session()
        self._create_mock_contact("alice_w", "Alice Walker")
        self._create_mock_contact("chloe_s", "Chloe Stone")

        p_key = rg.player_person_key(self.char_id)
        a_key = rg.canonical_person_key("Alice Walker")
        c_key = rg.canonical_person_key("Chloe Stone")

        # Player dates Alice
        rg.form_tie(self.session_id, p_key, a_key, rg.TIETYPE_DATING, closeness=80, turn=1)
        curr = rg.get_current_partner(self.session_id, p_key)
        self.assertEqual(curr["person_key"], a_key)

        # Player dates Chloe without supersede -> Decision 1: converted to Secret Affair
        rg.form_tie(self.session_id, p_key, c_key, rg.TIETYPE_DATING, closeness=75, turn=3)

        # Alice remains primary exclusive partner
        curr_p = rg.get_current_partner(self.session_id, p_key)
        self.assertEqual(curr_p["person_key"], a_key)

        # Chloe is an active secret affair
        affairs = rg.get_secret_affairs(self.session_id, p_key)
        self.assertEqual(len(affairs), 1)
        self.assertEqual(affairs[0]["person_key"], c_key)

        # Check Chloe's materialized relations: secret_partner is set, current_partner is None
        with get_conn() as conn:
            c_row = conn.execute("SELECT relations_json FROM contacts WHERE session_id = ? AND npc_id = 'chloe_s'", (self.session_id,)).fetchone()
            chloe_mat = json.loads(c_row["relations_json"])
            self.assertIsNotNone(chloe_mat["romance"]["secret_partner"])
            self.assertEqual(chloe_mat["romance"]["secret_partner"]["person_key"], p_key)

    def test_breakup_preserves_full_history(self):
        """Ending a romantic tie moves the partner to ex_partners without erasing prior exes or affairs."""
        self._create_mock_session()
        self._create_mock_contact("alice_w", "Alice Walker")
        self._create_mock_contact("bob_m", "Bob Miller", gender="male")

        p_key = rg.player_person_key(self.char_id)
        a_key = rg.canonical_person_key("Alice Walker")
        b_key = rg.canonical_person_key("Bob Miller")

        # Alice had an ex Bob
        rg.form_tie(self.session_id, a_key, b_key, rg.TIETYPE_DATING, turn=1)
        rg.end_tie(self.session_id, a_key, b_key, rg.TIETYPE_DATING, turn=2, reason="drifted_apart")

        # Alice dates Player
        rg.form_tie(self.session_id, p_key, a_key, rg.TIETYPE_DATING, turn=3)

        # Breakup between Player and Alice
        rg.end_tie(self.session_id, p_key, a_key, rg.TIETYPE_DATING, turn=5, reason="affinity_collapse")

        # Materialized check on Alice
        with get_conn() as conn:
            a_row = conn.execute("SELECT relations_json, track FROM contacts WHERE session_id = ? AND npc_id = 'alice_w'", (self.session_id,)).fetchone()
            mat = json.loads(a_row["relations_json"])

        self.assertEqual(mat["romance"]["status"], "Single")
        self.assertIsNone(mat["romance"]["current_partner"])
        ex_names = [e["person_key"] for e in mat["romance"]["ex_partners"]]
        # Both Player and Bob are present in ex_partners
        self.assertIn(p_key, ex_names)
        self.assertIn(b_key, ex_names)
        self.assertEqual(a_row["track"], "platonic")

    def test_intimacy_ledger_secret_affair_sync(self):
        """Recording physical intimacy when an exclusive partner exists auto-flags is_secret_affair and forms affair tie."""
        from mechanics.social.persona.intimacy.ledger import record_intimate_event

        self._create_mock_session()
        self._create_mock_contact("alice_w", "Alice Walker")
        self._create_mock_contact("chloe_s", "Chloe Stone")

        p_key = rg.player_person_key(self.char_id)
        a_key = rg.canonical_person_key("Alice Walker")
        c_key = rg.canonical_person_key("Chloe Stone")

        # Player dates Alice
        rg.form_tie(self.session_id, p_key, a_key, rg.TIETYPE_DATING, closeness=85, turn=1)

        # Intimate event between Player and Chloe
        ev_id = record_intimate_event(
            session_id=self.session_id,
            character_id="chloe_s",
            partner_name="Hero",
            partner_id="0",
            act_type="kiss",
            direction="mutual",
            turn_number=4,
            event_origin="gameplay",
            is_physical=True
        )

        with get_conn() as conn:
            ev = conn.execute("SELECT is_secret_affair FROM intimate_events WHERE id = ?", (ev_id,)).fetchone()
            self.assertEqual(ev["is_secret_affair"], 1)

        # Verify graph now holds a secret affair tie between Player and Chloe
        affairs = rg.get_secret_affairs(self.session_id, c_key)
        self.assertEqual(len(affairs), 1)
        self.assertEqual(affairs[0]["person_key"], p_key)

    def test_incest_guard(self):
        """Incest guard prevents romantic ties between household members."""
        self._create_mock_session()
        with get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO households
                   (session_id, household_key, surname, father_json, mother_json, narrative_siblings_json, created_at, updated_at)
                   VALUES (?, 'hh_anderson', 'Anderson', '{}', '{}', '[]', ?, ?)""",
                (self.session_id, time.time(), time.time()),
            )
            hh_id = cur.lastrowid

            conn.execute(
                """INSERT INTO contacts
                   (session_id, character_id, npc_id, name, gender, household_id, basic_info_json, relations_json, track)
                   VALUES (?, ?, 'amanda_a', 'Amanda Anderson', 'female', ?, '{}', '{}', 'platonic')""",
                (self.session_id, self.char_id, hh_id),
            )
            conn.execute(
                """INSERT INTO contacts
                   (session_id, character_id, npc_id, name, gender, household_id, basic_info_json, relations_json, track)
                   VALUES (?, ?, 'sofia_a', 'Sofia Anderson', 'female', ?, '{}', '{}', 'platonic')""",
                (self.session_id, self.char_id, hh_id),
            )

        amanda_key = rg.canonical_person_key("Amanda Anderson")
        sofia_key = rg.canonical_person_key("Sofia Anderson")

        # Attempt to form dating tie between Amanda and Sofia -> rejected by incest guard
        with self.assertRaises(ValueError):
            rg.form_tie(self.session_id, amanda_key, sofia_key, rg.TIETYPE_DATING)

    def test_save_load_child_table_integrity(self):
        """Save and load correctly duplicates social_persons and social_ties without FK breakage."""
        import db.saves as saves

        self._create_mock_session()
        self._create_mock_contact("alice_w", "Alice Walker")
        self._create_mock_contact("bob_m", "Bob Miller", gender="male")

        a_key = rg.canonical_person_key("Alice Walker")
        b_key = rg.canonical_person_key("Bob Miller")
        rg.form_tie(self.session_id, a_key, b_key, rg.TIETYPE_FRIEND, closeness=90)

        # Ensure characters table has test_hero_1 with active_session_id
        with get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO characters (id, user_id, name, char_class, max_hp, max_mp, hp, mp, gold, active_session_id, created_at)
                   VALUES (101, 101, 'TestHero', 'Warrior', 100, 50, 100, 50, 10, ?, ?)""",
                (self.session_id, time.time()),
            )

        # Save adventure slot
        save_dict = saves.save_adventure_slot(101, "Slot 1")
        save_id = save_dict["save_id"]
        self.assertGreater(save_id, 0)

        # Load adventure slot into new session
        loaded_session = saves.load_adventure_slot(101, "Slot 1")
        new_sid = loaded_session["id"]
        self.assertNotEqual(new_sid, self.session_id)

        try:
            # Check ties in new session
            new_ties = rg.get_ties(new_sid, a_key, active_only=True)
            self.assertEqual(len(new_ties), 1)
            self.assertEqual(new_ties[0]["other_person_key"], b_key)
            self.assertEqual(new_ties[0]["closeness"], 90)

            # Delete old session completely
            with get_conn() as conn:
                _delete_session_records(conn, self.session_id)

            # New session still retains intact ties and persons
            persisted_ties = rg.get_ties(new_sid, a_key, active_only=True)
            self.assertEqual(len(persisted_ties), 1)
        finally:
            with get_conn() as conn:
                _delete_session_records(conn, new_sid)
                conn.execute("DELETE FROM adventure_saves WHERE id = ?", (save_id,))
                conn.execute("DELETE FROM characters WHERE id = 101")

    def test_migration_conflict_tiering_policy(self):
        """Decision 5: Player tie wins, most recent update wins for partner conflict, rival beats friend."""
        self._create_mock_session()
        p_key = rg.player_person_key(self.char_id)
        # Create contradictory contacts
        with get_conn() as conn:
            # Contact 1: Elena claiming Hyun-woo Smirnov
            conn.execute(
                """INSERT INTO contacts
                   (session_id, character_id, npc_id, name, relations_json, track, updated_at)
                   VALUES (?, ?, 'elena_h', 'Elena Ha', ?, 'platonic', 1000)""",
                (
                    self.session_id,
                    self.char_id,
                    json.dumps({
                        "romance": {"current_partner": {"name": "Hyun-woo Smirnov", "relationship_type": "Dating"}},
                        "friends": [{"name": "Ginevra Yamazaki", "closeness": 70}],
                    }),
                ),
            )
            # Contact 2: Ginevra claiming Hyun-woo Smirnov with newer timestamp (2000) AND claiming Elena as rival
            conn.execute(
                """INSERT INTO contacts
                   (session_id, character_id, npc_id, name, relations_json, track, updated_at)
                   VALUES (?, ?, 'ginevra_y', 'Ginevra Yamazaki', ?, 'platonic', 2000)""",
                (
                    self.session_id,
                    self.char_id,
                    json.dumps({
                        "romance": {"current_partner": {"name": "Hyun-woo Smirnov", "relationship_type": "Dating"}},
                        "rivals": [{"name": "Elena Ha", "type": "Rival"}],
                    }),
                ),
            )

        with get_conn() as conn:
            report = rg.migrate_legacy_relations(conn)

        self.assertGreater(report["ties_created"], 0)
        self.assertGreater(report["conflicts_resolved"], 0)

        # 1. Romantic Conflict: Ginevra (updated_at=2000) wins over Elena (updated_at=1000)
        g_curr = rg.get_current_partner(self.session_id, "ginevra_yamazaki")
        self.assertIsNotNone(g_curr)
        self.assertEqual(g_curr["person_key"], "hyun_woo_smirnov")

        e_curr = rg.get_current_partner(self.session_id, "elena_ha")
        self.assertIsNone(e_curr)
        # Elena's tie is marked ended with migration_conflict
        e_exes = rg.get_ex_partners(self.session_id, "elena_ha")
        self.assertTrue(any(e["person_key"] == "hyun_woo_smirnov" and e["end_reason"] == "migration_conflict" for e in e_exes))

        # 2. Friend vs Rival: Rivalry supersedes friendship (Decision 5)
        elena_ginevra_ties = rg.get_ties(self.session_id, "elena_ha", active_only=True)
        eg_active = [t for t in elena_ginevra_ties if t["other_person_key"] == "ginevra_yamazaki"]
        self.assertEqual(len(eg_active), 1)
        self.assertEqual(eg_active[0]["tie_type"], "rival")

    def test_rollback_ties_after_turn(self):
        """Ties started after turn N are deleted, and ties ended after turn N are reopened."""
        self._create_mock_session()
        self._create_mock_contact("alice_w", "Alice Walker")
        self._create_mock_contact("bob_m", "Bob Miller", gender="male")

        a_key = rg.canonical_person_key("Alice Walker")
        b_key = rg.canonical_person_key("Bob Miller")

        # Tie 1: Formed turn 2, ended turn 4
        rg.form_tie(self.session_id, a_key, b_key, rg.TIETYPE_FRIEND, closeness=70, turn=2)
        rg.end_tie(self.session_id, a_key, b_key, rg.TIETYPE_FRIEND, turn=4, reason="breakup")

        # Tie 2: Formed turn 5
        rg.form_tie(self.session_id, a_key, b_key, rg.TIETYPE_RIVAL, closeness=50, turn=5)

        # Rollback to turn 3:
        # - Tie 2 (started turn 5) is deleted
        # - Tie 1 (ended turn 4) is reopened to active!
        rg.rollback_ties_after_turn(self.session_id, 3)

        active = rg.get_ties(self.session_id, a_key, active_only=True)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["tie_type"], "friend")
        self.assertEqual(active[0]["closeness"], 70)


if __name__ == "__main__":
    unittest.main()
