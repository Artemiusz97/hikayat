from __future__ import annotations
"""
End-to-end clean-cutover regression suite for Hikayat's five normalized models:
1. Normalized Household Entity Model
2. Normalized Intimacy Ledger & Act Event Model
3. Normalized Social Graph & Relationship Network
4. Unified Commitments & Rendezvous Engine
5. Normalized Actor Physical State & Garment Layer Model
"""
import json
import os
import unittest
from typing import Any

import config
import db
from db.core import _migrate_clean_cutover_v30
from db.inventory import equip_item
from db.memory import add_commitment
from db.saves import _rewrite_session_key_id, load_adventure_slot, save_adventure_slot
from db.sessions import reset_session_for_opening_retry, rollback_session_normalized_state_after_turn
from game_engine.state.social import _reduce_social_and_milestones, resolve_pre_turn_social_and_disclosures
import mechanics.social.genealogy as genealogy
from mechanics.social.persona.intimacy.ledger import get_intimate_events, record_intimate_event
import mechanics.social.physical_state as ps
import mechanics.social.relationship_graph as rg
from mechanics.system.commitments_engine import cancel_commitment, get_commitment
from mechanics.system.phone.social_graph import evaluate_pre_turn_witness_detection


class TestFiveNormalizedModelsCutover(unittest.TestCase):
    def setUp(self):
        # 1. Snapshot ambient paths prior to redirection
        self._orig_db_path = db.DB_PATH
        self._orig_core_db_path = getattr(db.core, "DB_PATH", db.DB_PATH)
        self._orig_config_db_path = getattr(config, "DB_PATH", db.DB_PATH)
        self._test_db_path: str | None = None
        self._is_temp: bool = False
        self._cleaned_up: bool = False

        # 2. Register cleanup FIRST: guarantees restoration even if isolate_simulation_db raises
        self.addCleanup(self._restore_and_cleanup_db)

        # 3. Strictly isolate to an ephemeral SQLite database on local fast disk
        self._test_db_path, self._is_temp = db.isolate_simulation_db(prefix="hikayat_cutover_test_")

        # 4. Strict regression invariant: prove db.DB_PATH is isolated from repository live DB
        self._assert_db_is_isolated()

        self.user_id = 945001
        self.session_id = 945001
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM adventure_saves WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))

        db.create_character(
            self.user_id,
            "Ren Amamiya",
            "Rogue",
            race="Human",
            gender="male",
            scenario="high_school_drama",
        )
        self.char = db.get_character(self.user_id)
        with db.get_conn() as conn:
            conn.execute(
                """INSERT INTO sessions (id, host_user_id, character_id, status, mode, capacity, scenario, current_location)
                   VALUES (?, ?, ?, 'active', 'single', 1, 'high_school_drama', 'Academy ➔ Main Hallway')""",
                (self.session_id, self.user_id, self.char["id"]),
            )
            conn.execute(
                "UPDATE characters SET active_session_id = ? WHERE id = ?",
                (self.session_id, self.char["id"]),
            )
            from db.core import _delete_session_child_records_only
            _delete_session_child_records_only(conn, self.session_id)

    def tearDown(self):
        """Ensure database handles are closed and isolated state is restored cleanly on teardown."""
        self._restore_and_cleanup_db()
        super().tearDown()

    def _restore_and_cleanup_db(self):
        """Idempotently close all SQLite handles, restore global paths, and unlink temp DB file."""
        if getattr(self, "_cleaned_up", False):
            return
        self._cleaned_up = True

        # Step 1: Drain connection pools to release Windows file locks
        try:
            db.close_all_connections()
        except Exception:
            pass

        # Step 2: Safely close and clear any lingering contextvar connection (prevents [WinError 32])
        try:
            if hasattr(db.core, "_uow_conn_var"):
                active_conn = db.core._uow_conn_var.get()
                if active_conn is not None:
                    try:
                        active_conn.close()
                    except Exception:
                        pass
                db.core._uow_conn_var.set(None)
            if hasattr(db.core, "_uow_db_path_var"):
                db.core._uow_db_path_var.set(None)
        except Exception:
            pass

        # Step 3: Restore global DB path pointers across db, db.core, and config
        try:
            if hasattr(self, "_orig_db_path"):
                db.set_db_path(self._orig_db_path)
        except Exception:
            if hasattr(self, "_orig_db_path"):
                db.DB_PATH = self._orig_db_path
            if hasattr(self, "_orig_core_db_path"):
                db.core.DB_PATH = self._orig_core_db_path
            if hasattr(self, "_orig_config_db_path"):
                config.DB_PATH = self._orig_config_db_path
        finally:
            # Step 4: Safely delete the temporary simulation database file from disk
            test_path = getattr(self, "_test_db_path", None)
            if test_path:
                db.cleanup_simulation_db(
                    test_path,
                    keep=False,
                    is_temp=getattr(self, "_is_temp", True),
                )

    def _assert_db_is_isolated(self):
        """Regression invariant: prove db.DB_PATH and db.core.DB_PATH are strictly isolated from repository live DB."""
        self.assertIsInstance(db.DB_PATH, str, "db.DB_PATH must be a valid path string")
        self.assertIsInstance(db.core.DB_PATH, str, "db.core.DB_PATH must be a valid path string")
        self.assertTrue(len(db.DB_PATH) > 0, "db.DB_PATH must not be empty")

        self.assertEqual(
            db.DB_PATH,
            db.core.DB_PATH,
            f"db.DB_PATH ({db.DB_PATH}) and db.core.DB_PATH ({db.core.DB_PATH}) must be strictly synchronized",
        )
        self.assertEqual(
            db.DB_PATH,
            config.DB_PATH,
            f"db.DB_PATH ({db.DB_PATH}) and config.DB_PATH ({config.DB_PATH}) must be strictly synchronized",
        )

        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        forbidden_live_paths = {
            os.path.normcase(os.path.abspath("hikayat.db")),
            os.path.normcase(os.path.abspath(os.path.join("data", "hikayat.db"))),
            os.path.normcase(os.path.abspath(os.path.join(repo_root, "hikayat.db"))),
            os.path.normcase(os.path.abspath(os.path.join(repo_root, "data", "hikayat.db"))),
        }
        current_norm = os.path.normcase(os.path.abspath(db.DB_PATH))

        self.assertNotIn(
            current_norm,
            forbidden_live_paths,
            f"CRITICAL: db.DB_PATH ({db.DB_PATH}) is pointing to repository live database!",
        )

        for candidate in (
            os.path.join(repo_root, "hikayat.db"),
            os.path.join(repo_root, "data", "hikayat.db"),
            os.path.abspath("hikayat.db"),
        ):
            if os.path.exists(candidate) and os.path.exists(db.DB_PATH):
                try:
                    self.assertFalse(
                        os.path.samefile(db.DB_PATH, candidate),
                        f"Regression violation: db.DB_PATH points to the same file on disk as {candidate}",
                    )
                except (OSError, ValueError):
                    pass

        self.assertTrue(
            os.path.exists(db.DB_PATH),
            f"Isolated temporary database does not exist on disk: {db.DB_PATH}",
        )

    def test_00_database_isolation_contract(self):
        """Regression assertion proving db.DB_PATH and db.core.DB_PATH never point to live hikayat.db."""
        self._assert_db_is_isolated()
        self.assertEqual(db.DB_PATH, self._test_db_path)
        self.assertEqual(db.core.DB_PATH, self._test_db_path)
        self.assertTrue(
            "hikayat_cutover_test_" in os.path.basename(self._test_db_path)
            or "hikayat_sim_" in os.path.basename(self._test_db_path),
            f"Expected temporary database prefix in file name, got: {self._test_db_path}",
        )

    def test_01_migration_30_clean_cutover_player_keys_appointments_and_actors(self):
        """Migration 30 canonicalizes legacy player keys, migrates phone_appointments, backfills household_role, and strips actors JSON."""
        hh_id = db.create_household(
            session_id=self.session_id,
            household_key=f"hh_{self.session_id}_sato_1",
            surname="Sato",
            residence_location="Maple District ➔ Sato House",
            father={"name": "Kenji Sato", "occupation": "Architect"},
            mother={"name": "Yumi Sato (née Tanaka)", "occupation": "Pediatrician"},
        )
        mother_contact = db.upsert_contact(
            session_id=self.session_id,
            npc_id="yumi_sato",
            name="Yumi Sato",
            gender="female",
        )
        with db.get_conn() as conn:
            # Leave household_role blank prior to Migration 30
            conn.execute(
                "UPDATE contacts SET household_id = ?, household_role = '' WHERE id = ?",
                (hh_id, mother_contact["id"]),
            )
            # Legacy player:default / player:77 rows
            conn.execute(
                """INSERT OR REPLACE INTO social_persons (session_id, person_key, display_name, gender, origin, created_at)
                   VALUES (?, 'player:default', 'Ren Amamiya', 'male', 'player', 1.0)""",
                (self.session_id,),
            )
            conn.execute(
                """INSERT OR REPLACE INTO social_persons (session_id, person_key, display_name, gender, origin, created_at)
                   VALUES (?, 'hana_sato', 'Hana Sato', 'female', 'contact', 1.0)""",
                (self.session_id,),
            )
            conn.execute(
                """INSERT INTO social_ties (session_id, person_a_key, person_b_key, tie_type, status, closeness, origin, created_at, updated_at)
                   VALUES (?, 'hana_sato', 'player:default', 'friend', 'active', 55, 'gameplay', 1.0, 1.0)""",
                (self.session_id,),
            )
            conn.execute(
                """INSERT INTO intimate_events (session_id, character_id, partner_id, partner_name, turn_number, event_origin, act_type, direction, is_physical, count, created_at)
                   VALUES (?, 'hana_sato', 'player:77', 'Ren Amamiya', 2, 'gameplay', 'kiss', 'mutual', 1, 1, 1.0)""",
                (self.session_id,),
            )
            # Legacy phone_appointments row
            conn.execute(
                """INSERT INTO phone_appointments (session_id, npc_id, npc_name, rendezvous_location, topic, status, is_confidential, origin, created_minute, expiry_minute, created_at)
                   VALUES (?, 'hana_sato', 'Hana Sato', 'School Rooftop', 'Lunch', 'pending', 1, 'phone', 720, 780, 1.0)""",
                (self.session_id,),
            )
            # Legacy sessions.physical_state_json containing actors + props
            legacy_phys = {
                "actors": {
                    "Ren Amamiya": {
                        "posture": "Leaning against lockers",
                        "holding": "Smartphone",
                        "clothing": {"top": "Academy Blazer", "bottom": "Uniform Slacks"},
                    }
                },
                "props": {"School Bulletin Board": "Pinned with flyers"},
                "intimate_contact": "none",
            }
            conn.execute("DELETE FROM actor_physical_states WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM actor_garments WHERE session_id = ?", (self.session_id,))
            conn.execute(
                "UPDATE sessions SET physical_state_json = ? WHERE id = ?",
                (json.dumps(legacy_phys), self.session_id),
            )

            _migrate_clean_cutover_v30(conn)

            # Verify canonical 'player' key across tables
            legacy_p = conn.execute(
                "SELECT COUNT(*) FROM social_persons WHERE session_id = ? AND person_key LIKE 'player:%'",
                (self.session_id,),
            ).fetchone()[0]
            self.assertEqual(legacy_p, 0)

            tie_row = conn.execute(
                "SELECT person_a_key, person_b_key FROM social_ties WHERE session_id = ? AND tie_type = 'friend'",
                (self.session_id,),
            ).fetchone()
            self.assertIsNotNone(tie_row)
            self.assertIn("player", (tie_row["person_a_key"], tie_row["person_b_key"]))

            ie_row = conn.execute(
                "SELECT partner_id FROM intimate_events WHERE session_id = ? AND character_id = 'hana_sato'",
                (self.session_id,),
            ).fetchone()
            self.assertEqual(ie_row["partner_id"], "player")

            # Verify phone_appointments migrated to commitments_ledger
            appts = db.get_phone_appointments(self.session_id, status="pending")
            self.assertTrue(any(a["rendezvous_location"] == "School Rooftop" for a in appts))

            # Verify household_role backfilled via maiden-name-stripped match
            role_val = conn.execute(
                "SELECT household_role FROM contacts WHERE id = ?",
                (mother_contact["id"],),
            ).fetchone()["household_role"]
            self.assertEqual(role_val, "mother")

            # Verify actors migrated and stripped from sessions.physical_state_json
            raw_sess_meta = json.loads(
                conn.execute("SELECT physical_state_json FROM sessions WHERE id = ?", (self.session_id,)).fetchone()[0]
            )
            self.assertNotIn("actors", raw_sess_meta)
            self.assertEqual(raw_sess_meta["props"]["School Bulletin Board"], "Pinned with flyers")

        ren_phys = ps.get_actor_physical_state(self.session_id, "Ren Amamiya")
        self.assertIsNotNone(ren_phys)
        self.assertEqual(ren_phys["holding"], "Smartphone")
        self.assertEqual(ren_phys["clothing"]["top"], "Academy Blazer")

    def test_02_a1_parent_promotion_adult_role_and_maiden_name_stripping(self):
        """A1: NPC parents promote only when met in-scene, stay Adult non-students, and render spouse/child perspective."""
        hh_id = db.create_household(
            session_id=self.session_id,
            household_key=f"hh_{self.session_id}_sato_2",
            surname="Sato",
            residence_location="Maple District ➔ Sato House",
            father={"name": "Kenji Sato", "gender": "male", "occupation": "Architect"},
            mother={"name": "Yumi Sato (née Tanaka)", "gender": "female", "occupation": "Pediatrician"},
        )
        hana = db.upsert_contact(
            session_id=self.session_id,
            npc_id="hana_sato",
            name="Hana Sato",
            gender="female",
            basic_info={"role": "Student", "grade": "Year 2"},
            household_role="child",
        )
        db.assign_contact_household(self.session_id, hana["id"], hh_id, household_role="child")

        # Parent is NOT a contact before meeting in scene
        self.assertIsNone(db.get_contact(self.session_id, "Yumi Sato"))

        # Promote parent when met in scene (matching despite '(née Tanaka)' suffix in household JSON)
        promoted = genealogy.maybe_promote_scene_parent(self.session_id, "Yumi Sato")
        self.assertIsNotNone(promoted)
        self.assertEqual(promoted["household_role"], "mother")

        loaded = db.get_contact(self.session_id, promoted["npc_id"])
        self.assertEqual(loaded["household_role"], "mother")
        b_info = loaded.get("basic_info") or {}
        self.assertEqual(b_info.get("grade"), "Adult")
        self.assertTrue(b_info.get("is_adult_family"))
        self.assertFalse(b_info.get("club"))

        # Perspective family tree for Yumi Sato must show Husband (Kenji) and Daughter (Hana), NOT herself as Mother
        fam = (loaded.get("relations") or {}).get("family") or []
        rel_labels = {f["name"]: f["relation"] for f in fam}
        self.assertTrue(any("husband" in r.lower() or "spouse" in r.lower() for k, r in rel_labels.items() if "Kenji" in k))
        self.assertTrue(any("daughter" in r.lower() or "child" in r.lower() for k, r in rel_labels.items() if "Hana" in k))
        self.assertFalse(any("Yumi" in f["name"] for f in fam))

    def test_03_a2_secret_affair_colocation_breakup_and_witness_rumor_confrontation(self):
        """A2: Witness #SecretAffair leaks trigger angry DM at 2+ leaks (-25); co-location triggers immediate breakup (-40)."""
        mina = db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="mina_park",
            name="Mina Park",
            gender="female",
            delta_score=65,
            track="romantic",
        )
        sora = db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="sora_kim",
            name="Sora Kim",
            gender="female",
            delta_score=40,
            track="platonic",
        )
        rg.form_tie(self.session_id, "player", "sora_kim", rg.TIETYPE_AFFAIR, closeness=60, supersede=False)
        self.assertIsNotNone(rg.get_current_partner(self.session_id, "player"))

        sess_public = {
            "id": self.session_id,
            "host_user_id": self.user_id,
            "scenario": "high_school_drama",
            "current_location": "Academy ➔ Courtyard",
            "current_npcs": [{"name": "Sora Kim"}, {"name": "Taro Yamada"}],
            "history": [{}],
        }
        kiss_actions = [{"label": "Kiss Sora passionately in the courtyard"}]

        # Leak 1: #SecretAffair rumor posted, suspicion increments to 1 (no confrontation yet)
        w1 = evaluate_pre_turn_witness_detection(
            sess_public, kiss_actions, player_name="Ren Amamiya", target_npc="Sora Kim", location_str="Academy ➔ Courtyard"
        )
        self.assertTrue(w1["witness_spotted"])
        self.assertEqual(w1["event_kind"], "secret_affair")
        self.assertEqual(w1["post"]["tag"], "#SecretAffair")
        self.assertFalse(w1["affair_confrontation_triggered"])

        # Leak 2: Suspicion hits 2 -> angry DM confrontation + -25 affinity penalty on Mina
        w2 = evaluate_pre_turn_witness_detection(
            sess_public, kiss_actions, player_name="Ren Amamiya", target_npc="Sora Kim", location_str="Academy ➔ Courtyard"
        )
        self.assertTrue(w2["affair_confrontation_triggered"])
        mina_after_leaks = db.get_contact(self.session_id, "mina_park", self.char["id"])
        self.assertEqual(mina_after_leaks["relationship_score"], 40)
        dms = db.get_phone_messages(self.session_id, "mina_park")
        self.assertTrue(any("talk" in (m.get("message") or "").lower() for m in dms))

        # Part B: Co-location with primary partner Mina while kissing affair partner Sora -> immediate -40 breakup
        coloc_session = {
            "id": self.session_id,
            "host_user_id": self.user_id,
            "scenario": "high_school_drama",
            "current_location": "Academy ➔ Rooftop",
            "current_npcs": [{"name": "Mina Park"}, {"name": "Sora Kim"}],
            "dialogue_partner": "Sora Kim",
            "history": [{}, {}],
        }
        coloc_outcome = {
            "outcome_narrative": "Mina steps onto the rooftop and freezes as she sees Ren kissing Sora.",
            "npcs_present": [{"name": "Mina Park"}, {"name": "Sora Kim"}],
            "relationship_updates": [{"npc_name": "Sora Kim", "delta_score": 2, "milestone_event": "kiss"}],
        }
        _reduce_social_and_milestones(
            session_id=self.session_id,
            session=coloc_session,
            party=[(self.char, [])],
            outcome=coloc_outcome,
            actions=[{"label": "Kiss Sora Kim tenderly", "target_npc": "Sora Kim"}],
            scen_key="high_school_drama",
            items_gained_by_user={},
            first_char_id=self.char["id"],
            first_char_name="Ren Amamiya",
        )
        mina_broken = db.get_contact(self.session_id, "mina_park", self.char["id"])
        self.assertEqual(mina_broken["relationship_score"], 0)
        self.assertEqual(mina_broken["track"], "platonic")
        self.assertIsNone(rg.get_current_partner(self.session_id, "player"))
        self.assertTrue(any("caught" in n.lower() for n in coloc_outcome.get("system_notices", [])))

    def test_04_a3_hybrid_promise_verification_custom_guard_and_cancel(self):
        """A3: Gold/item debts verify inventory/gold, unverified custom claims do not auto-fulfill, and cancel has 0 penalty."""
        npc = db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="kaede_mori",
            name="Kaede Mori",
            gender="female",
            delta_score=30,
        )
        sess = {
            "id": self.session_id,
            "host_user_id": self.user_id,
            "scenario": "high_school_drama",
            "current_location": "Academy ➔ Library",
            "current_npcs": [{"name": "Kaede Mori"}],
            "dialogue_partners": ["Kaede Mori"],
        }

        # 1. Gold-backed debt: fails at 30g, succeeds at 150g and deducts 100g
        db.update_character_fields(self.user_id, gold=30)
        char_poor = db.get_character(self.user_id)
        cm_gold = add_commitment(
            self.session_id, "player", "Kaede Mori", "debt", "Repay 100g to Kaede Mori",
            turn_number=1, metadata={"gold_amount": 100}
        )
        res_poor = resolve_pre_turn_social_and_disclosures(
            sess, [(char_poor, [])], [{"label": "Repay the 100g debt to Kaede Mori"}]
        )
        self.assertNotIn(cm_gold["id"], res_poor["fulfilled_commitments"])
        self.assertTrue(any("INSUFFICIENT GOLD" in d for d in res_poor["directives"]))

        db.update_character_fields(self.user_id, gold=150)
        char_rich = db.get_character(self.user_id)
        res_rich = resolve_pre_turn_social_and_disclosures(
            sess, [(char_rich, [])], [{"label": "Repay the 100g debt to Kaede Mori"}]
        )
        self.assertIn(cm_gold["id"], res_rich["fulfilled_commitments"])
        self.assertEqual(db.get_character(self.user_id)["gold"], 50)

        # 2. Item-backed promise: fails when missing, succeeds when item is in inventory
        cm_item = add_commitment(
            self.session_id, "player", "Kaede Mori", "promise", "Deliver Rare Herbendium to Kaede Mori",
            turn_number=2, metadata={"item_name": "Rare Herbendium"}
        )
        res_no_item = resolve_pre_turn_social_and_disclosures(
            sess, [(db.get_character(self.user_id), [])], [{"label": "Deliver the Rare Herbendium to Kaede Mori"}]
        )
        self.assertNotIn(cm_item["id"], res_no_item["fulfilled_commitments"])
        self.assertTrue(any("MISSING ITEM" in d for d in res_no_item["directives"]))

        db.add_item(self.user_id, "Rare Herbendium", "Quest", 1)
        res_has_item = resolve_pre_turn_social_and_disclosures(
            sess, [(db.get_character(self.user_id), [])], [{"label": "Deliver the Rare Herbendium to Kaede Mori"}]
        )
        self.assertIn(cm_item["id"], res_has_item["fulfilled_commitments"])

        # 3. Unverified custom action cannot self-fulfill free-form promise pre-turn
        cm_free = add_commitment(
            self.session_id, "player", "Kaede Mori", "promise", "Help Kaede tutor freshmen",
            turn_number=3
        )
        res_custom = resolve_pre_turn_social_and_disclosures(
            sess,
            [(db.get_character(self.user_id), [])],
            [{"label": "Fulfill my promise to Kaede Mori right now", "is_custom": True}],
        )
        self.assertNotIn(cm_free["id"], res_custom["fulfilled_commitments"])
        self.assertTrue(any("ACTIVE COMMITMENT VERIFICATION" in d for d in res_custom["directives"]))

        # 4. Graceful cancellation applies zero penalty
        score_before = db.get_contact(self.session_id, "kaede_mori", self.char["id"])["relationship_score"]
        self.assertTrue(cancel_commitment(self.session_id, cm_free["id"], reason="rescheduled"))
        self.assertEqual(get_commitment(self.session_id, cm_free["id"])["status"], "cancelled")
        score_after = db.get_contact(self.session_id, "kaede_mori", self.char["id"])["relationship_score"]
        self.assertEqual(score_before, score_after)

    def test_05_a4_garment_word_boundaries_anatomical_barriers_and_restraints(self):
        """A4: Word-boundary garment states, chest/genital auto-displacement, and restraint dual-wield/equip rules."""
        # 1. Word-boundary false-positive regression check
        for safe_garment in ("Officer Uniform", "Off-shoulder sweater", "Button-down shirt", "Open cardigan"):
            self.assertEqual(ps.normalize_garment_state(safe_garment), ps.STATE_WORN, safe_garment)

        # 2. Chest & genital anatomical barrier auto-displacement
        full_outfit = {
            ps.SLOT_OUTERWEAR: "Academy Blazer",
            ps.SLOT_TOP: "Button-down shirt",
            ps.SLOT_UNDER_TOP: "Lace Bra",
            ps.SLOT_BOTTOM: "Pleated Skirt",
            ps.SLOT_UNDER_BOTTOM: "Silk Panties",
            ps.SLOT_FOOTWEAR: "Loafers",
        }
        after_chest = ps.enforce_anatomical_barriers_on_act(full_outfit, "kiss and suckle her breasts tenderly")
        self.assertIn("displaced", after_chest[ps.SLOT_OUTERWEAR].lower())
        self.assertIn("displaced", after_chest[ps.SLOT_TOP].lower())
        self.assertIn("displaced", after_chest[ps.SLOT_UNDER_TOP].lower())
        self.assertEqual(after_chest[ps.SLOT_BOTTOM], "Pleated Skirt")

        after_genital = ps.enforce_anatomical_barriers_on_act(full_outfit, "thrust deep inside her")
        self.assertIn("displaced", after_genital[ps.SLOT_BOTTOM].lower())
        self.assertIn("displaced", after_genital[ps.SLOT_UNDER_BOTTOM].lower())

        # 3. Restraint blocks 2H / offhand equip, and 1H equip preserves posture/wet/composure
        ps.upsert_actor_physical_state(
            self.session_id,
            "Ren Amamiya",
            {
                "posture": "Kneeling by fountain",
                "holding": "Coffee Cup",
                "tether_type": "restrained",
                "tether_partner": "steel cuffs",
                "composure": ps.COMPOSURE_FLUSTERED,
                "is_wet": True,
            },
            garments={ps.SLOT_TOP: "Academy Blazer", ps.SLOT_BOTTOM: "Uniform Slacks"},
        )
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO inventory (character_id, user_id, name, item_type, slot_cost, equipped) VALUES (?, ?, 'Greatsword', 'Weapon', 2, 0)",
                (self.char["id"], self.user_id),
            )
            gs_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute(
                "INSERT INTO inventory (character_id, user_id, name, item_type, slot_cost, equipped) VALUES (?, ?, 'Short Dagger', 'Weapon', 1, 0)",
                (self.char["id"], self.user_id),
            )
            dag_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        with self.assertRaises(ValueError):
            equip_item(self.user_id, gs_id, "Weapon")

        # Release restraint and equip 1H dagger -> clears Coffee Cup without wiping posture/wet/composure/garments
        ps.upsert_actor_physical_state(
            self.session_id,
            "Ren Amamiya",
            {"tether_type": "none", "tether_partner": ""},
        )
        equip_item(self.user_id, dag_id, "Weapon")
        ren_after = ps.get_actor_physical_state(self.session_id, "Ren Amamiya")
        self.assertEqual(ren_after["holding"], "Short Dagger")
        self.assertEqual(ren_after["posture"], "Kneeling by fountain")
        self.assertEqual(ren_after["composure"], ps.COMPOSURE_FLUSTERED)
        self.assertEqual(ren_after["is_wet"], 1)
        self.assertEqual(ren_after["clothing"]["top"], "Academy Blazer")

    def test_06_turn0_retry_reset_rollback_and_save_load_id1_anchoring(self):
        """Save/Load session_id=1 key anchoring, multi-table turn rollback, and Turn 0 opening retry reset."""
        # 1. Verify _rewrite_session_key_id does not corrupt trailing digits when old_sid=1
        self.assertEqual(_rewrite_session_key_id("hh_1_vance_101", 1, 99), "hh_99_vance_101")
        self.assertEqual(_rewrite_session_key_id("rv_1_player_hana_1_1100", 1, 42), "rv_42_player_hana_1_1100")

        # 2. Seed Turn 1 and Turn 4 state across social_ties, intimate_events, and commitments_ledger, then rollback > Turn 2
        db.upsert_contact(self.session_id, npc_id="aoi_takahashi", name="Aoi Takahashi", gender="female", character_id=self.char["id"])
        rg.form_tie(self.session_id, "player", "aoi_takahashi", rg.TIETYPE_FRIEND, closeness=45, turn=1, supersede=False)
        rg.form_tie(self.session_id, "player", "aoi_takahashi", rg.TIETYPE_DATING, closeness=80, turn=4, supersede=False)
        record_intimate_event(
            session_id=self.session_id, character_id="aoi_takahashi", partner_name="Ren Amamiya",
            act_type="kiss", direction="mutual", partner_id="player", turn_number=1, event_origin="gameplay"
        )
        record_intimate_event(
            session_id=self.session_id, character_id="aoi_takahashi", partner_name="Ren Amamiya",
            act_type="intercourse", direction="receptive", partner_id="player", turn_number=4, event_origin="gameplay",
            character_gender="female", partner_gender="male"
        )
        add_commitment(self.session_id, "player", "Aoi Takahashi", "promise", "Turn 1 study note promise", turn_number=1)
        add_commitment(self.session_id, "player", "Aoi Takahashi", "promise", "Turn 4 festival promise", turn_number=4)

        rb_res = rollback_session_normalized_state_after_turn(self.session_id, turn_number=2)
        self.assertGreaterEqual(rb_res["ties_rolled_back"], 1)
        self.assertGreaterEqual(rb_res["intimate_events_deleted"], 1)
        self.assertEqual(rb_res["commitments_deleted"], 1)
        self.assertIsNone(rg.get_current_partner(self.session_id, "player"))
        evs_after_rb = get_intimate_events(self.session_id, "aoi_takahashi")
        self.assertEqual([e["act_type"] for e in evs_after_rb], ["kiss"])

        # 3. Save & Load adventure slot clones normalized tables cleanly
        save_res = save_adventure_slot(self.user_id, "CleanCutoverSlot", overwrite=True)
        self.assertEqual(save_res["status"], "saved")
        loaded_sess = load_adventure_slot(self.user_id, "CleanCutoverSlot")
        new_sid = loaded_sess["id"]
        try:
            self.assertNotEqual(new_sid, self.session_id)
            cloned_evs = get_intimate_events(new_sid, "aoi_takahashi")
            self.assertEqual([e["act_type"] for e in cloned_evs], ["kiss"])
            cloned_ties = rg.get_ties(new_sid, "player")
            self.assertTrue(any(t["tie_type"] == rg.TIETYPE_FRIEND for t in cloned_ties))
        finally:
            with db.get_conn() as conn:
                from db.core import _delete_session_child_records_only
                _delete_session_child_records_only(conn, new_sid)
                conn.execute("DELETE FROM sessions WHERE id = ?", (new_sid,))
                conn.execute("UPDATE characters SET active_session_id = ? WHERE id = ?", (self.session_id, self.char["id"]))

        # 4. Turn 0 opening retry reset purges child rows + opening_starting_prop_name without deleting starter gear
        db.add_item(self.user_id, "Starter Backpack", "Misc", 1)
        db.add_item(self.user_id, "Mysterious Brass Key", "Quest", 1)
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE sessions SET extra_json = ? WHERE id = ?",
                (json.dumps({"opening_starting_prop_name": "Mysterious Brass Key"}), self.session_id),
            )
        reset_session_for_opening_retry(self.session_id, user_id=self.user_id)
        self.assertEqual(db.get_contacts(self.session_id), [])
        self.assertEqual(get_intimate_events(self.session_id, "aoi_takahashi"), [])
        inv_names = [i["name"] for i in db.get_inventory(self.user_id)]
        self.assertIn("Starter Backpack", inv_names)
        self.assertNotIn("Mysterious Brass Key", inv_names)


if __name__ == "__main__":
    unittest.main()
