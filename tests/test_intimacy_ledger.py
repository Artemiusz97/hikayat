import unittest
import time
import json
import sqlite3
import db
from mechanics.social.persona.intimacy.ledger import (
    enforce_biological_invariants,
    compute_intimate_tracks_from_ledger,
    record_intimate_event,
    get_intimate_events,
    recompute_and_cache_character_intimacy,
    delete_intimate_events_after_turn,
    record_intimate_turn_encounter,
    parse_past_history_entry_to_events,
)

class TestIntimacyLedger(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.session_id = int(time.time() * 1000) + 777

    def tearDown(self):
        with db.get_conn() as conn:
            db.core._delete_session_records(conn, self.session_id)

    # -------------------------------------------------------------------------
    # 1. Biological Invariants
    # -------------------------------------------------------------------------
    def test_biological_invariants_female_anal(self):
        """Female characters can strictly ONLY receive anal intimacy. Any 'give' or 'mutual' is coerced to 'receive'."""
        # Female giving anal -> coerced to receive
        self.assertEqual(
            enforce_biological_invariants(gender="female", act_type="anal", direction="give"),
            "receive"
        )
        # Female mutual anal -> coerced to receive
        self.assertEqual(
            enforce_biological_invariants(gender="female", act_type="anal", direction="mutual"),
            "receive"
        )
        # Female receiving anal -> stays receive
        self.assertEqual(
            enforce_biological_invariants(gender="female", act_type="anal", direction="receive"),
            "receive"
        )

    def test_biological_invariants_male_anal(self):
        """Male characters with female partners can ONLY give anal. With male partners, they can give, receive, or be mutual."""
        # Male with female partner
        self.assertEqual(
            enforce_biological_invariants(gender="male", act_type="anal", direction="give", partner_gender="female"),
            "give"
        )
        self.assertEqual(
            enforce_biological_invariants(gender="male", act_type="anal", direction="receive", partner_gender="female"),
            "give"
        )
        self.assertEqual(
            enforce_biological_invariants(gender="male", act_type="anal", direction="mutual", partner_gender="female"),
            "give"
        )

        # Male with male partner
        self.assertEqual(
            enforce_biological_invariants(gender="male", act_type="anal", direction="give", partner_gender="male"),
            "give"
        )
        self.assertEqual(
            enforce_biological_invariants(gender="male", act_type="anal", direction="receive", partner_gender="male"),
            "receive"
        )
        self.assertEqual(
            enforce_biological_invariants(gender="male", act_type="anal", direction="mutual", partner_gender="male"),
            "mutual"
        )

    def test_biological_invariants_non_anal_preserved(self):
        """Non-anal acts (oral, manual, intercourse, kiss) preserve their direction."""
        for act in ("oral", "manual", "intercourse", "kiss"):
            for direction in ("give", "receive", "mutual"):
                self.assertEqual(
                    enforce_biological_invariants(gender="female", act_type=act, direction=direction),
                    direction
                )
                self.assertEqual(
                    enforce_biological_invariants(gender="male", act_type=act, direction=direction),
                    direction
                )

    # -------------------------------------------------------------------------
    # 2. Track Derivation from Ledger Events
    # -------------------------------------------------------------------------
    def test_compute_intimate_tracks_empty_ledger(self):
        """Empty ledger produces baseline virgin and inexperienced states across all tracks."""
        tracks = compute_intimate_tracks_from_ledger([])
        self.assertEqual(tracks["intercourse"], "virgin")
        self.assertEqual(tracks["oral"], "inexperienced")
        self.assertEqual(tracks["manual"], "inexperienced")
        self.assertEqual(tracks["anal"], "inexperienced")

    def test_compute_intimate_tracks_directional_progression(self):
        """Directional progression accurately reflects give, receive, and combined done_and_received."""
        events = [
            {"act_type": "oral", "direction": "give", "is_physical": True},
        ]
        self.assertEqual(compute_intimate_tracks_from_ledger(events)["oral"], "has_done_oral")

        events.append({"act_type": "oral", "direction": "receive", "is_physical": True})
        self.assertEqual(compute_intimate_tracks_from_ledger(events)["oral"], "has_done_and_received_oral")

        events_manual = [
            {"act_type": "manual", "direction": "mutual", "is_physical": True}
        ]
        self.assertEqual(compute_intimate_tracks_from_ledger(events_manual)["manual"], "has_done_and_received_manual")

    def test_compute_intimate_tracks_ignores_non_physical_milestones(self):
        """Non-physical milestones (confession, date, media) do not advance physical experience tracks."""
        events = [
            {"act_type": "confession", "direction": "mutual", "is_physical": False},
            {"act_type": "date", "direction": "mutual", "is_physical": False},
        ]
        tracks = compute_intimate_tracks_from_ledger(events)
        self.assertEqual(tracks["intercourse"], "virgin")
        self.assertEqual(tracks["oral"], "inexperienced")
        self.assertEqual(tracks["manual"], "inexperienced")
        self.assertEqual(tracks["anal"], "inexperienced")

    # -------------------------------------------------------------------------
    # 3. Reciprocal Symmetry in Record Event
    # -------------------------------------------------------------------------
    def test_reciprocal_event_creation(self):
        """Recording an event between two active characters creates a reciprocal inverted entry."""
        ev_id = record_intimate_event(
            session_id=self.session_id,
            character_id="alice",
            partner_name="Bob",
            act_type="oral",
            direction="give",
            partner_id="bob",
            turn_number=1,
            event_origin="gameplay",
            character_gender="female",
            partner_gender="male"
        )
        self.assertGreater(ev_id, 0)

        alice_evs = get_intimate_events(self.session_id, "alice")
        self.assertEqual(len(alice_evs), 1)
        self.assertEqual(alice_evs[0]["act_type"], "oral")
        self.assertEqual(alice_evs[0]["direction"], "give")

        bob_evs = get_intimate_events(self.session_id, "bob")
        self.assertEqual(len(bob_evs), 1)
        self.assertEqual(bob_evs[0]["act_type"], "oral")
        self.assertEqual(bob_evs[0]["direction"], "receive")

    # -------------------------------------------------------------------------
    # 4. Live Turn Encounters & Cache Synchronization
    # -------------------------------------------------------------------------
    def test_record_intimate_turn_encounter_updates_profile_and_tracks(self):
        """Live turn encounter updates intimate_events and re-caches tracks in contacts table."""
        # Create contact
        db.upsert_contact(
            session_id=self.session_id,
            character_id=1,
            npc_id="chloe_adams",
            name="Chloe Adams",
            gender="female",
            appearance={"intercourse_experience": "virgin"}
        )

        mem, tracks = record_intimate_turn_encounter(
            session_id=self.session_id,
            character_id="chloe_adams",
            partner_id="player",
            partner_name="Artemiusz",
            milestone_event="intercourse",
            turn_number=3,
            character_gender="female"
        )
        self.assertEqual(tracks["intercourse"], "non_virgin")
        self.assertIn("Artemiusz", mem)

        contact = db.get_contact(self.session_id, "chloe_adams", 1)
        self.assertEqual(contact["intercourse_experience"], "non_virgin")
        self.assertEqual(contact["intimate_profile"]["tracks"]["intercourse"], "non_virgin")
        self.assertTrue(contact["intimate_profile"]["disclosure_flags"]["intercourse_revealed"])
        self.assertTrue(contact["intimate_profile"]["disclosure_flags"]["intimate_revealed"])

    # -------------------------------------------------------------------------
    # 5. Save Rollback / Pruning
    # -------------------------------------------------------------------------
    def test_delete_intimate_events_after_turn_rollbacks_tracks(self):
        """Pruning events after a checkpoint turn correctly rewinds intimate tracks."""
        db.upsert_contact(
            session_id=self.session_id,
            character_id=1,
            npc_id="elena_rostova",
            name="Elena Rostova",
            gender="female"
        )

        # Turn 1: Oral encounter
        record_intimate_turn_encounter(
            session_id=self.session_id,
            character_id="elena_rostova",
            milestone_event="oral_give",
            turn_number=1,
            character_gender="female"
        )

        # Turn 2: Intercourse encounter
        record_intimate_turn_encounter(
            session_id=self.session_id,
            character_id="elena_rostova",
            milestone_event="intercourse",
            turn_number=2,
            character_gender="female"
        )

        # Check turn 2 state
        c_turn2 = db.get_contact(self.session_id, "elena_rostova", 1)
        self.assertEqual(c_turn2["intercourse_experience"], "non_virgin")
        self.assertEqual(c_turn2["oral_experience"], "has_done_oral")

        # Rollback back to turn 1
        deleted = delete_intimate_events_after_turn(self.session_id, 1)
        self.assertGreater(deleted, 0)

        # Contact tracks must be restored to turn 1 state
        c_rewound = db.get_contact(self.session_id, "elena_rostova", 1)
        self.assertEqual(c_rewound["intercourse_experience"], "virgin")
        self.assertEqual(c_rewound["oral_experience"], "has_done_oral")

    # -------------------------------------------------------------------------
    # 6. Zero Desynchronization Guarantee (Su-bin Vance Parity)
    # -------------------------------------------------------------------------
    def test_subin_vance_zero_desynchronization_parity(self):
        """Verifies that Su-bin's past history strings and derived badges are 100% in sync with zero discrepancies."""
        db.upsert_contact(
            session_id=self.session_id,
            character_id=1,
            npc_id="su-bin_vance",
            name="Su-bin Vance",
            gender="female",
            new_memory="Past History: Engaged in mutual manual foreplay & received anal 7 times with 'Bartosz Kuznetsov' (Swim Team Member)"
        )
        db.upsert_contact(
            session_id=self.session_id,
            character_id=1,
            npc_id="su-bin_vance",
            name="Su-bin Vance",
            gender="female",
            new_memory="Past History: Engaged in mutual manual foreplay & received anal 8 times with 'Tomas Lopez' (Student Council President)"
        )

        contact = db.get_contact(self.session_id, "su-bin_vance", 1)

        # Derived tracks
        self.assertEqual(contact["intercourse_experience"], "virgin")
        self.assertEqual(contact["oral_experience"], "inexperienced")
        self.assertEqual(contact["manual_experience"], "has_done_and_received_manual")
        self.assertEqual(contact["anal_experience"], "has_received_anal")

        # Ledger events
        events = contact["past_intimate_events"]
        self.assertEqual(len(events), 4)  # 2 manual + 2 anal
        for ev in events:
            if ev["act_type"] == "anal":
                self.assertEqual(ev["direction"], "receive")
            elif ev["act_type"] == "manual":
                self.assertEqual(ev["direction"], "mutual")

        # Backward-compatible memories
        past_entries = contact["past_intimate_entries"]
        self.assertEqual(len(past_entries), 2)
        self.assertTrue(any("Bartosz Kuznetsov" in p for p in past_entries))
        self.assertTrue(any("Tomas Lopez" in p for p in past_entries))

    def test_reciprocal_partner_name_resolution(self):
        """Verifies that when recording an intimate event between two tracked NPCs,
        the reciprocal row generated for the partner has partner_name resolved to the human-readable
        name of the character, rather than the raw character_id or slug string."""
        # Create Alice and Bob as contacts in session
        c_alice = db.upsert_contact(
            session_id=self.session_id,
            character_id=1,
            npc_id="alice_hart",
            name="Alice Hart",
            gender="female"
        )
        c_bob = db.upsert_contact(
            session_id=self.session_id,
            character_id=1,
            npc_id="bob_miller",
            name="Bob Miller",
            gender="male"
        )

        # Record intimate event for Alice with Bob
        ev_id = record_intimate_event(
            session_id=self.session_id,
            character_id=str(c_alice["id"]),
            partner_name="Bob Miller",
            act_type="kiss",
            direction="mutual",
            partner_id=str(c_bob["id"]),
            turn_number=1,
            event_origin="gameplay",
            is_physical=True,
            character_gender="female",
            partner_gender="male"
        )
        self.assertGreater(ev_id, 0)

        # Check Bob's reciprocal event row
        bob_events = get_intimate_events(self.session_id, str(c_bob["id"]))
        self.assertEqual(len(bob_events), 1)
        bob_ev = bob_events[0]
        self.assertEqual(bob_ev["character_id"], c_bob["npc_id"])
        self.assertEqual(bob_ev["partner_id"], c_alice["npc_id"])
        # partner_name must be the human-readable "Alice Hart", NOT the numeric ID or slug!
        self.assertEqual(bob_ev["partner_name"], "Alice Hart")

if __name__ == "__main__":
    unittest.main()
