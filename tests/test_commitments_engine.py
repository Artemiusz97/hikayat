"""
tests/test_commitments_engine.py — Comprehensive Test Suite for Unified Commitments & Rendezvous Engine
=======================================================================================================
Verifies all 15 locked invariants and edge cases from the /grill-me architecture:
  1. Minimal binary split ('rendezvous' vs 'promise')
  2. Multi-NPC group rendezvous spawning
  3. NPC living schedule overrides (15-min lead-up)
  4. Tiered flaking penalties (-25 date, -15 casual) & hurt memory
  5. Apology mitigation recovery (50% penalty recovery)
  6. Confidential & romantic 1-on-1 party companion isolation
  7. Permissive double-booking conflict detection
  8. Walking out / abrupt departure mid-meeting abandonment penalty (-10)
  9. Time jumps & sleep automatic flaking
 10. Clean voiding of disrupted commitments without penalties
 11. Early arrival contextual [Wait] choice generation
 12. Secret affair exposure risk in phone gossip
 13. Two-way synchronization with legacy phone_appointments
 14. Save/load cloning child table persistence
"""
import json
import unittest
import db
import game_engine
from mechanics.system.commitments_engine import (
    create_rendezvous,
    create_promise,
    advance_rendezvous_to_arrived,
    fulfill_commitment,
    flake_commitment,
    abandon_rendezvous,
    cancel_commitment,
    void_commitment,
    apply_apology_recovery,
    get_commitment,
    get_active_commitments,
    inject_npc_schedule_overrides,
    check_double_booking,
    audit_and_expire_commitments
)


class TestCommitmentsEngine(unittest.TestCase):
    def setUp(self):
        self.session_id = 997701
        self.user_id = 887701

        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM commitments_ledger WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_messages WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_gossip_feed WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM npc_memories WHERE session_id = ?", (self.session_id,))

        db.create_character(self.user_id, "Protagonist", "male")
        self.char = db.get_character(self.user_id)
        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )

        db.upsert_contact(
            self.session_id, character_id=self.char["id"], npc_id="elena_rostova",
            name="Elena Rostova", basic_info={"location": "Westlake Academy"}
        )
        db.upsert_contact(
            self.session_id, character_id=self.char["id"], npc_id="maya_anderson",
            name="Maya Anderson", basic_info={"location": "Westlake Academy"}
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM commitments_ledger WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_messages WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_gossip_feed WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM npc_memories WHERE session_id = ?", (self.session_id,))

    def test_01_binary_split_and_creation(self):
        """Invariant 1: Minimal binary taxonomy strictly categorizes into 'rendezvous' and 'promise'."""
        loc = "Westlake Academy ➔ School Rooftop ➔ Rooftop Benches"
        rend = create_rendezvous(
            session_id=self.session_id,
            organizer="player",
            participants=["elena_rostova"],
            location=loc,
            day=1,
            start_minute=960,
            end_minute=1020,
            title="Afternoon Rooftop Meetup",
            is_confidential=True
        )
        self.assertEqual(rend["commitment_type"], "rendezvous")
        self.assertEqual(rend["target_location"], loc)
        self.assertEqual(rend["start_minute"], 960)
        self.assertEqual(rend["end_minute"], 1020)
        self.assertEqual(rend["status"], "pending")
        self.assertEqual(rend["is_confidential"], 1)

        prom = create_promise(
            session_id=self.session_id,
            promiser="player",
            promisee="maya_anderson",
            description="I promise to return the borrowed history notes before the exam",
            subtype="debt"
        )
        self.assertEqual(prom["commitment_type"], "promise")
        self.assertEqual(prom["target_entity"], "maya_anderson")
        self.assertEqual(prom["metadata"].get("subtype"), "debt")
        self.assertEqual(prom["status"], "active")

    def test_02_multi_party_group_rendezvous_spawning(self):
        """Invariant 9: Multi-NPC group rendezvous stores roster and spawns all attending members."""
        club_room = "Westlake Academy ➔ Drama Club Theater ➔ Backstage Dressing Room"
        group_appt = create_rendezvous(
            session_id=self.session_id,
            organizer="player",
            participants=[
                {"npc_id": "elena_rostova", "name": "Elena Rostova", "role": "lead_actress"},
                {"npc_id": "maya_anderson", "name": "Maya Anderson", "role": "stage_director"}
            ],
            location=club_room,
            day=1,
            start_minute=900,
            end_minute=960,
            title="Drama Club Rehearsal"
        )

        stage_result = game_engine.npcs.stage_manager.compute_pre_turn_stage(
            session={"id": self.session_id, "current_day": 1, "current_minute": 915, "current_location": "Westlake Academy ➔ Entrance Foyer"},
            actions=[{"label": f"Go to {club_room}"}]
        )
        spawned_names = {n["name"] for n in stage_result.get("stage_npcs", [])}
        self.assertIn("Elena Rostova", spawned_names)
        self.assertIn("Maya Anderson", spawned_names)

    def test_03_npc_schedule_override_injection(self):
        """Invariant 8: Routine schedule is overridden 15 minutes before start with appointment phase."""
        loc = "Commercial District ➔ Local Café ➔ Window Booth"
        node_id = "loc_commercial_cafe"
        create_rendezvous(
            session_id=self.session_id,
            organizer="player",
            participants=["elena_rostova"],
            location=loc,
            node_id=node_id,
            day=1,
            start_minute=960,  # 16:00
            end_minute=1020    # 17:00
        )

        # 1. 20 min before (15:40 = 940): Not yet in lead-up
        ov_early = inject_npc_schedule_overrides(self.session_id, "elena_rostova", 1, 940)
        self.assertIsNone(ov_early)

        # 2. 10 min before (15:50 = 950): In transit lead-up
        ov_transit = inject_npc_schedule_overrides(self.session_id, "elena_rostova", 1, 950)
        self.assertIsNotNone(ov_transit)
        self.assertEqual(ov_transit["schedule_phase"], "appointment_transit")
        self.assertEqual(ov_transit["node_id"], node_id)

        # 3. During window (16:15 = 975): Waiting at venue
        ov_waiting = inject_npc_schedule_overrides(self.session_id, "elena_rostova", 1, 975)
        self.assertIsNotNone(ov_waiting)
        self.assertEqual(ov_waiting["schedule_phase"], "appointment_waiting")

        # 4. After window (17:05 = 1025): Expired, routine resumes
        ov_after = inject_npc_schedule_overrides(self.session_id, "elena_rostova", 1, 1025)
        self.assertIsNone(ov_after)

    def test_04_tiered_flaking_penalties_and_hurt_memory(self):
        """Invariant 7: Flaking date incurs -25 affinity and hurt memory; casual incurs -15."""
        db.update_relationship_score(self.session_id, "elena_rostova", delta_score=100)
        db.update_relationship_score(self.session_id, "maya_anderson", delta_score=100)

        # 1. Romantic Date Rendezvous
        date_c = create_rendezvous(
            session_id=self.session_id,
            organizer="player",
            participants=["elena_rostova"],
            location="Sakura Hill ➔ Starlight Observatory",
            day=1,
            start_minute=1100,
            end_minute=1160,
            is_confidential=True,
            metadata={"is_romantic": True}
        )
        res_date = flake_commitment(self.session_id, date_c["id"])
        self.assertEqual(res_date["penalty"], -25)

        with db.get_conn() as conn:
            c_row = conn.execute("SELECT relationship_score FROM contacts WHERE session_id=? AND npc_id='elena_rostova'", (self.session_id,)).fetchone()
            self.assertEqual(c_row["relationship_score"], 75)

            mem_row = conn.execute("SELECT * FROM npc_memories WHERE session_id=? AND lower(npc_name) LIKE '%elena%'", (self.session_id,)).fetchone()
            self.assertIsNotNone(mem_row)
            self.assertEqual(mem_row["emotional_tone"], "hurt")
            self.assertEqual(mem_row["open_thread"], "unresolved_flake")

        # 2. Casual Promise
        prom_c = create_promise(
            session_id=self.session_id,
            promiser="player",
            promisee="maya_anderson",
            description="Fix Maya's bicycle brake cables"
        )
        res_prom = flake_commitment(self.session_id, prom_c["id"])
        self.assertEqual(res_prom["penalty"], -15)

        with db.get_conn() as conn:
            c_row2 = conn.execute("SELECT relationship_score FROM contacts WHERE session_id=? AND npc_id='maya_anderson'", (self.session_id,)).fetchone()
            self.assertEqual(c_row2["relationship_score"], 85)

    def test_05_apology_mitigation_recovery(self):
        """Invariant 7: Apologizing for a missed date recovers 50% of the lost penalty."""
        db.update_relationship_score(self.session_id, "elena_rostova", delta_score=100)
        date_c = create_rendezvous(
            session_id=self.session_id,
            organizer="player",
            participants=["elena_rostova"],
            location="Sakura Hill ➔ Starlight Observatory",
            metadata={"is_romantic": True}
        )
        flake_commitment(self.session_id, date_c["id"])

        # Score was 100 - 25 = 75
        rec = apply_apology_recovery(self.session_id, "elena_rostova", excuse_text="My family had an emergency, I am so sorry!")
        self.assertTrue(rec["recovered"])
        self.assertEqual(rec["recovered_affinity"], 12)  # 25 // 2 = 12

        with db.get_conn() as conn:
            c_row = conn.execute("SELECT relationship_score FROM contacts WHERE session_id=? AND npc_id='elena_rostova'", (self.session_id,)).fetchone()
            self.assertEqual(c_row["relationship_score"], 87)

        # Duplicate apology must NOT grant extra affinity
        rec2 = apply_apology_recovery(self.session_id, "elena_rostova", excuse_text="Please forgive me again!")
        self.assertEqual(rec2, {})

    def test_06_confidential_companion_isolation(self):
        """Invariant 4: Party companions wait outside in antechamber during confidential 1-on-1s."""
        secret_spot = "Westlake Academy ➔ Old Clock Tower ➔ Secret Attic Chamber"
        create_rendezvous(
            session_id=self.session_id,
            organizer="player",
            participants=["elena_rostova"],
            location=secret_spot,
            is_confidential=True
        )

        # Player is inside private secret spot with Maya Anderson as companion
        session_data = {
            "id": self.session_id,
            "scenario": "high_school_drama",
            "current_location": secret_spot,
            "temporary_companions": [{"name": "Maya Anderson", "role": "Companion"}]
        }

        stage_result = game_engine.npcs.stage_manager.compute_pre_turn_stage(
            session=session_data,
            actions=[{"label": "Talk quietly with Elena"}]
        )
        stage_names = {n["name"] for n in stage_result.get("stage_npcs", [])}
        self.assertIn("Elena Rostova", stage_names)
        self.assertNotIn("Maya Anderson", stage_names, "Traveling companion must wait outside private 1-on-1 date")

    def test_07_permissive_double_booking_detection(self):
        """Invariant 3: Permissive double-booking allows overlap but detects conflicts."""
        loc1 = "Westlake Academy ➔ Library ➔ Study Tables"
        create_rendezvous(
            session_id=self.session_id,
            organizer="player",
            participants=["elena_rostova"],
            location=loc1,
            day=2,
            start_minute=840,  # 14:00
            end_minute=900     # 15:00
        )

        # Check overlapping window on same day (14:30 - 15:30)
        conflicts = check_double_booking(self.session_id, day=2, start_minute=870, end_minute=930)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["target_location"], loc1)

        # Different day must have zero conflict
        no_conflict = check_double_booking(self.session_id, day=3, start_minute=870, end_minute=930)
        self.assertEqual(len(no_conflict), 0)

    def test_08_walking_out_mid_meeting_abandonment(self):
        """Invariant 13: Abruptly walking out without saying goodbye incurs -10 penalty and abandonment."""
        loc = "Westlake Academy ➔ Rooftop"
        appt = create_rendezvous(
            session_id=self.session_id,
            organizer="player",
            participants=["elena_rostova"],
            location=loc
        )
        advance_rendezvous_to_arrived(self.session_id, appt["id"])

        res = abandon_rendezvous(self.session_id, appt["id"], reason="walked out mid-meeting")
        self.assertEqual(res["status"], "abandoned")
        self.assertEqual(res["penalty"], -10)

        updated = get_commitment(self.session_id, appt["id"])
        self.assertEqual(updated["status"], "abandoned")
        self.assertTrue(updated["metadata"].get("abandoned"))

    def test_09_time_jump_audit_and_auto_flaking(self):
        """Invariant 11: Long rests / time jumps past appointment end windows auto-flake."""
        appt = create_rendezvous(
            session_id=self.session_id,
            organizer="player",
            participants=["maya_anderson"],
            location="Westlake Academy ➔ Gymnasium",
            day=1,
            start_minute=600,  # 10:00
            end_minute=660     # 11:00
        )

        # Audit at 10:30 (during window) -> not flaked
        f_mid = audit_and_expire_commitments(self.session_id, current_day=1, current_minute=630)
        self.assertEqual(len(f_mid), 0)

        # Long rest jumps to Day 1, 12:00 (720 min) -> flaked!
        f_late = audit_and_expire_commitments(self.session_id, current_day=1, current_minute=720)
        self.assertEqual(len(f_late), 1)
        self.assertEqual(f_late[0]["status"], "flaked")

    def test_10_void_commitment_clean_resolution(self):
        """Invariant 14: Voiding commitment due to disruption incurs zero penalties."""
        c = create_promise(
            session_id=self.session_id,
            promiser="player",
            promisee="elena_rostova",
            description="Deliver encrypted research documents"
        )
        ok = void_commitment(self.session_id, c["id"], reason="elena_arrested")
        self.assertTrue(ok)

        updated = get_commitment(self.session_id, c["id"])
        self.assertEqual(updated["status"], "voided")
        self.assertEqual(updated["metadata"].get("void_reason"), "elena_arrested")

    def test_11_early_arrival_wait_action_choice(self):
        """Invariant 12: Arriving early surfaces contextual [Wait] choice."""
        from mechanics.world.waypoints.choices import tag_and_enrich_quest_choices
        loc = "Westlake Academy ➔ School Rooftop ➔ Rooftop Benches"
        create_rendezvous(
            session_id=self.session_id,
            organizer="player",
            participants=["elena_rostova"],
            location=loc,
            day=1,
            start_minute=960,  # 16:00
            end_minute=1020
        )

        # Player arrives early at 15:00 (900 min)
        with db.get_conn() as conn:
            conn.execute("UPDATE sessions SET current_day=1, current_minute=900 WHERE id=?", (self.session_id,))

        choices = tag_and_enrich_quest_choices(
            choices=[{"label": "Look around the empty rooftop", "stat": "PER", "requirement": 5}],
            session_id=self.session_id,
            current_location=loc,
            dialogue_partner=None
        )
        labels = [c["label"] for c in choices]
        self.assertTrue(any("Wait for Elena Rostova until 4:00 PM" in lbl for lbl in labels))

    def test_12_secret_affair_exposure_risk(self):
        """Invariant 5: Secret affair rendezvous rolls exposure into Phone Gossip feed."""
        affair_c = create_rendezvous(
            session_id=self.session_id,
            organizer="player",
            participants=["elena_rostova"],
            location="Local Motel ➔ Room 204",
            metadata={"is_secret_affair": True, "force_rumor": True}
        )
        advance_rendezvous_to_arrived(self.session_id, affair_c["id"])

        gossip = db.get_gossip_feed(self.session_id)
        self.assertTrue(len(gossip) >= 1)
        self.assertEqual(gossip[0]["tag"], "#SecretAffair")

    def test_13_legacy_phone_appointments_two_way_sync(self):
        """Invariant 13: Legacy phone_appointments functions stay synchronized with commitments_ledger."""
        loc = "Westlake Academy ➔ Music Room"
        db.save_phone_appointment(self.session_id, "maya_anderson", "Maya Anderson", loc)

        # Check commitments_ledger was populated
        ledger_rows = get_active_commitments(self.session_id, entity_name="maya_anderson")
        self.assertTrue(len(ledger_rows) >= 1)
        self.assertEqual(ledger_rows[0]["target_location"], loc)

        # Update via legacy function
        db.update_phone_appointment_status(self.session_id, "maya_anderson", "arrived")
        c = get_commitment(self.session_id, ledger_rows[0]["id"])
        self.assertEqual(c["status"], "arrived")

    def test_14_save_load_cloning_persistence(self):
        """Verifies commitments_ledger rows clone cleanly when session is duplicated."""
        create_rendezvous(
            session_id=self.session_id,
            organizer="player",
            participants=["elena_rostova"],
            location="Westlake Academy ➔ Courtyard",
            title="Courtyard Rendezvous"
        )
        create_promise(
            session_id=self.session_id,
            promiser="player",
            promisee="maya_anderson",
            description="Promise to lend art supplies"
        )

        res = db.save_adventure_slot(self.user_id, "CommitmentCheckpoint")
        self.assertEqual(res["status"], "saved")

        loaded_session = db.load_adventure_slot(self.user_id, "CommitmentCheckpoint")
        cloned_sess_id = loaded_session["id"]
        self.assertIsNotNone(cloned_sess_id)
        self.assertNotEqual(cloned_sess_id, self.session_id)

        cloned_commits = get_active_commitments(cloned_sess_id)
        self.assertEqual(len(cloned_commits), 2)
        texts = [f"{c.get('title', '')} {c.get('description', '')}" for c in cloned_commits]
        self.assertTrue(any("Courtyard Rendezvous" in t for t in texts))
        self.assertTrue(any("art supplies" in t for t in texts))

    def test_15_incest_guard_blocks_romantic_rendezvous(self):
        """Cross-system: Incest Guard blocks romantic/confidential rendezvous between household members."""
        # Create a household where Elena and Maya are in the same household
        with db.get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO households (session_id, household_key, surname) VALUES (?, 'rostova_hh', 'Rostova')",
                (self.session_id,)
            )
            hh_id = cur.lastrowid
            conn.execute("UPDATE contacts SET household_id=? WHERE session_id=?", (hh_id, self.session_id))

        rend = create_rendezvous(
            session_id=self.session_id,
            organizer="elena_rostova",
            participants=["maya_anderson"],
            location="Local Park",
            is_confidential=True,
            metadata={"is_romantic": True}
        )
        self.assertFalse(rend["is_confidential"], "Romantic rendezvous between household members must be stripped of confidential flag")
        self.assertFalse(rend["metadata"].get("is_romantic"), "Romantic flag must be forced False by Incest Guard")
        self.assertTrue(rend["metadata"].get("incest_guarded"))

    def test_16_emergent_secret_affair_detection_from_social_ties(self):
        """Cross-system: Emergent secret affair detection when either party is already in an exclusive relationship in social_ties."""
        import mechanics.social.relationship_graph as rg
        p_key = rg.canonical_person_key("player")
        maya_key = rg.canonical_person_key("maya_anderson")
        elena_key = rg.canonical_person_key("elena_rostova")

        # Player is already dating Maya Anderson
        rg.form_tie(self.session_id, p_key, maya_key, rg.TIETYPE_DATING, closeness=80)

        # Player schedules romantic date with Elena Rostova
        rend = create_rendezvous(
            session_id=self.session_id,
            organizer="player",
            participants=["elena_rostova"],
            location="Bistro ➔ Private Booth",
            is_confidential=True,
            metadata={"is_romantic": True}
        )
        self.assertTrue(rend["metadata"].get("is_secret_affair"), "Must automatically detect secret affair when player is partnered with Maya")
        self.assertEqual(rend["metadata"].get("exposure_risk"), 0.5)

    def test_17_flaking_reduces_closeness_and_triggers_graph_breakup(self):
        """Cross-system: Flaking on a date reduces closeness and triggers breakup if affinity collapses below 0."""
        import mechanics.social.relationship_graph as rg
        p_key = rg.canonical_person_key("player")
        elena_key = rg.canonical_person_key("elena_rostova")

        # Player is dating Elena with low score (+10)
        with db.get_conn() as conn:
            conn.execute("UPDATE contacts SET track='romantic', relationship_score=10 WHERE session_id=? AND npc_id='elena_rostova'", (self.session_id,))
        rg.form_tie(self.session_id, p_key, elena_key, rg.TIETYPE_DATING, closeness=60)

        rend = create_rendezvous(
            session_id=self.session_id,
            organizer="player",
            participants=["elena_rostova"],
            location="Cafe",
            is_confidential=True,
            metadata={"is_romantic": True}
        )

        flake_res = flake_commitment(self.session_id, rend["id"])
        self.assertEqual(flake_res["status"], "flaked")
        self.assertEqual(flake_res["penalty"], -25)

        # Contact track should have collapsed to platonic
        contact = db.get_contact(self.session_id, "elena_rostova")
        self.assertEqual(contact["track"], "platonic")
        self.assertLess(contact["relationship_score"], 0)

        # Dating tie in social_ties must be ended
        partner = rg.get_current_partner(self.session_id, elena_key)
        self.assertIsNone(partner, "Dating tie must be ended upon affinity collapse")

    def test_18_db_add_commitment_unified_schema_delegation(self):
        """Backward-compatibility: db.add_commitment creates unified commitment with commitment_key, title, and participants."""
        from db.memory import add_commitment as mem_add_commitment
        res = mem_add_commitment(
            session_id=self.session_id,
            source_entity="player",
            target_entity="maya_anderson",
            commitment_type="pact",
            description="Blood oath to pass the final exams"
        )
        self.assertIn("commitment_key", res)
        self.assertTrue(res["commitment_key"].startswith("promise_"))
        self.assertEqual(res["commitment_type"], "promise")
        self.assertEqual(res["metadata"].get("subtype"), "pact")
        self.assertIn("Maya", res["title"])


if __name__ == "__main__":
    unittest.main()
