import unittest
import json
import db
from mechanics.world.locations.movement import (
    is_movement_action,
    extract_movement_destination,
    reconcile_movement_location,
)
from mechanics.world.locations.seeding import ensure_session_locations_seeded
import game_engine.npcs.presence as pres
import game_engine.turn.dialogue as dlg
from game_engine.choices_cleaner import clean_choices_impl
from mechanics.narrative.intent import classify_action_intent, IntentCategory
from mechanics.system.time_engine import advance_time, apply_sleep_rest

HIGH_SCHOOL_SCENARIO = "high_school_drama"

class TestInPersonRendezvousAndHangouts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session_id = 99882244
        cls.char_id = 88772244
        cls.char_name = "Artem"
        with db.get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO characters 
                (id, user_id, name, char_class, gender, scenario, race, hp, max_hp, mp, max_mp, level) 
                VALUES (?, ?, ?, 'Student', 'male', ?, 'human', 100, 100, 50, 50, 1)""",
                (cls.char_id, 99992244, cls.char_name, HIGH_SCHOOL_SCENARIO)
            )
            conn.execute(
                """INSERT OR REPLACE INTO sessions 
                (id, mode, capacity, scenario, current_location, current_day, current_minute, turn_order, dialogue_partner, temporary_companions_json) 
                VALUES (?, 'solo', 1, ?, 'Campus Promenade & Student Commons ➔ Central Courtyard ➔ Old Cherry Tree', 1, 480, '[]', '["Seo-ah Vance", "Kazuya Halloway"]', '[]')""",
                (cls.session_id, HIGH_SCHOOL_SCENARIO)
            )
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (cls.session_id,))
            conn.execute("DELETE FROM phone_messages WHERE session_id = ?", (cls.session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (cls.session_id,))
            conn.execute("DELETE FROM commitments_ledger WHERE session_id = ?", (cls.session_id,))
            conn.commit()
        ensure_session_locations_seeded(cls.session_id, HIGH_SCHOOL_SCENARIO, char_name=cls.char_name)

    @classmethod
    def tearDownClass(cls):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (cls.session_id,))
            conn.execute("DELETE FROM phone_messages WHERE session_id = ?", (cls.session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (cls.session_id,))
            conn.execute("DELETE FROM commitments_ledger WHERE session_id = ?", (cls.session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (cls.session_id,))
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (cls.session_id,))
            conn.execute("DELETE FROM characters WHERE id = ?", (cls.char_id,))
            conn.commit()

    def setUp(self):
        # Reset session state before each test
        with db.get_conn() as conn:
            conn.execute(
                """UPDATE sessions 
                SET current_location = 'Campus Promenade & Student Commons ➔ Central Courtyard ➔ Old Cherry Tree',
                    current_day = 1,
                    current_minute = 480,
                    dialogue_partner = '["Seo-ah Vance", "Kazuya Halloway"]',
                    temporary_companions_json = '[]'
                WHERE id = ?""",
                (self.session_id,)
            )
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_messages WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM commitments_ledger WHERE session_id = ?", (self.session_id,))
            conn.commit()

    def test_rendezvous_proposal_classification_and_appointment_creation(self):
        """Turn 1: Rendezvous proposal is classified as SOCIAL_INVITE with is_rendezvous=True, not immediate movement."""
        action_text = "Propose moving to the Botanical Glasshouse to talk about the circle's budget leaks in private."
        
        # 1. Action is not physical travel
        self.assertFalse(is_movement_action(action_text))
        
        # 2. Intent classification
        intent = classify_action_intent(action_text)
        self.assertEqual(intent.category, IntentCategory.SOCIAL_INVITE)
        self.assertTrue(intent.metadata.get("is_rendezvous"))
        self.assertTrue(intent.metadata.get("is_confidential"))
        self.assertIn("budget leaks", intent.metadata.get("topic", ""))

        # 3. Processing dialogue intent creates appointment in DB and departs NPC
        sess = db.get_session(self.session_id)
        actions = [{"label": action_text}]
        new_partners, has_exited = dlg._compute_dialogue_intent(sess, actions)

        self.assertTrue(has_exited)
        self.assertNotIn("Seo-ah Vance", new_partners)
        self.assertIn("Kazuya Halloway", new_partners)

        # 4. Check appointment saved in DB
        appts = db.get_active_rendezvous_appointments(self.session_id)
        self.assertEqual(len(appts), 1)
        appt = appts[0]
        self.assertEqual(appt["npc_name"], "Seo-ah Vance")
        self.assertIn("Botanical Glasshouse", appt["rendezvous_location"])
        self.assertEqual(appt["status"], "pending")
        self.assertEqual(appt["created_minute"], 480)
        self.assertEqual(appt["expiry_minute"], 525)

    def test_confidential_topic_embargo_in_public_and_lifted_at_venue(self):
        """Choices leaking confidential topic are embargoed away from venue, permitted once at venue."""
        db.save_rendezvous_appointment(
            session_id=self.session_id,
            npc_id="Seo-ah Vance",
            npc_name="Seo-ah Vance",
            rendezvous_location="Campus Promenade & Student Commons ➔ Botanical Glasshouse",
            topic="the circle's budget leaks",
            is_confidential=True,
            created_minute=480,
            expiry_minute=525
        )

        raw_choices = [
            {"label": "Ask Kazuya about the circle's budget leaks", "stat": "wit", "requirement": 10},
            {"label": "Talk about the upcoming cultural festival", "stat": "charm", "requirement": 5},
            {"label": "Head to the Botanical Glasshouse", "stat": "athletics", "requirement": 0}
        ]

        # 1. At Central Courtyard (public): leaked topic choice is embargoed
        cleaned_courtyard = clean_choices_impl(
            None,
            choices=raw_choices,
            session_id=self.session_id,
            location="Campus Promenade & Student Commons ➔ Central Courtyard ➔ Old Cherry Tree"
        )
        labels_courtyard = [c["label"] for c in cleaned_courtyard]
        self.assertFalse(any("budget leaks" in l for l in labels_courtyard))
        self.assertTrue(any("cultural festival" in l for l in labels_courtyard))
        # Also travel choice gets meetup annotation
        self.assertTrue(any("(Meetup: Seo-ah Vance)" in l for l in labels_courtyard))

        # 2. At Botanical Glasshouse (rendezvous venue): topic choice is permitted
        cleaned_venue = clean_choices_impl(
            None,
            choices=raw_choices,
            session_id=self.session_id,
            location="Campus Promenade & Student Commons ➔ Botanical Glasshouse"
        )
        labels_venue = [c["label"] for c in cleaned_venue]
        self.assertTrue(any("budget leaks" in l for l in labels_venue))

    def test_turn_2_manual_travel_and_arrival_convergence(self):
        """Turn 2: Player chooses travel action, arrives at venue, completes appointment, and resumes dialogue."""
        db.save_rendezvous_appointment(
            session_id=self.session_id,
            npc_id="Seo-ah Vance",
            npc_name="Seo-ah Vance",
            rendezvous_location="Campus Promenade & Student Commons ➔ Botanical Glasshouse",
            topic="the circle's budget leaks",
            is_confidential=True,
            created_minute=480,
            expiry_minute=525
        )

        travel_action = "[Travel to Botanical Glasshouse] (Meetup: Seo-ah Vance)"
        self.assertTrue(is_movement_action(travel_action))

        # Reconcile movement updates location to Botanical Glasshouse
        curr_loc = "Campus Promenade & Student Commons ➔ Central Courtyard ➔ Old Cherry Tree"
        new_loc = reconcile_movement_location(
            self.session_id,
            curr_loc,
            "",
            action_text=travel_action,
            scen_key=HIGH_SCHOOL_SCENARIO
        )
        self.assertIn("Botanical Glasshouse", new_loc)

        # In turn/core.py arrival logic: active rendezvous matching new_loc completes
        active = db.get_active_rendezvous_appointments(self.session_id)
        self.assertEqual(len(active), 1)
        db.update_phone_appointment_status(self.session_id, "Seo-ah Vance", "completed")

        # Appointment status is completed
        completed_appts = db.get_phone_appointments(self.session_id, status="completed")
        self.assertEqual(len(completed_appts), 1)
        self.assertEqual(completed_appts[0]["npc_name"], "Seo-ah Vance")

    def test_rendezvous_30_min_sms_reminder_and_45_min_standup_penalty(self):
        """At +30 min an SMS reminder is sent; at +45 min appointment expires with stand-up penalty."""
        db.save_rendezvous_appointment(
            session_id=self.session_id,
            npc_id="Seo-ah Vance",
            npc_name="Seo-ah Vance",
            rendezvous_location="Campus Promenade & Student Commons ➔ Botanical Glasshouse",
            topic="the circle's budget leaks",
            is_confidential=True,
            created_minute=480,
            expiry_minute=525
        )

        # Initial score is 50
        db.upsert_contact(session_id=self.session_id, npc_id="Seo-ah Vance", name="Seo-ah Vance", delta_score=50)

        # 1. Advance time by 30 minutes (minute 510): 30-min reminder fires
        advance_time(self.session_id, 30)
        messages = db.get_phone_messages(self.session_id, contact_npc_id="Seo-ah Vance")
        self.assertTrue(len(messages) >= 1)
        self.assertIn("Botanical Glasshouse", messages[-1]["message"])

        # Appointment reminder_sent should now be 1
        appts = db.get_active_rendezvous_appointments(self.session_id)
        self.assertEqual(len(appts), 1)
        self.assertEqual(appts[0]["reminder_sent"], 1)

        # 2. Advance time by another 20 minutes (minute 530, past 525 expiry): Stand-up penalty fires
        advance_time(self.session_id, 20)
        appts_after = db.get_active_rendezvous_appointments(self.session_id)
        self.assertEqual(len(appts_after), 0)

        stood_up = db.get_phone_appointments(self.session_id, status="stood_up")
        self.assertEqual(len(stood_up), 1)

        # Score should have decreased (tiered flaking penalty -25 for confidential date, legacy -5)
        contact = db.get_contact(self.session_id, "Seo-ah Vance")
        self.assertIn(contact["relationship_score"], (25, 45))

        # Check refusal/cancellation text was sent
        all_messages = db.get_phone_messages(self.session_id, contact_npc_id="Seo-ah Vance")
        self.assertTrue(len(all_messages) >= 2)
        last_msg = all_messages[-1]["message"].lower()
        self.assertTrue("couldn't wait any longer" in last_msg or "never showed up" in last_msg)

    def test_temporary_companions_hangout_follow_and_dismissal(self):
        """Companions follow player across locations, capped at 3, and dismissed on parting ways."""
        # 1. Invite Seo-ah to walk together
        sess = db.get_session(self.session_id)
        actions = [{"label": "Invite Seo-ah Vance to walk together around campus"}]
        new_partners, has_exited = dlg._compute_dialogue_intent(sess, actions)
        self.assertFalse(has_exited)
        self.assertIn("Seo-ah Vance", new_partners)

        # Seo-ah is in temporary_companions
        comps = db.get_temporary_companions(self.session_id)
        self.assertEqual(len(comps), 1)
        self.assertEqual(comps[0]["name"], "Seo-ah Vance")

        # 2. Add second and third companions, cap at 3
        db.add_temporary_companion(self.session_id, "Kazuya Halloway", "studying")
        db.add_temporary_companion(self.session_id, "Maya Lin", "chatting")
        db.add_temporary_companion(self.session_id, "Excess Character", "extra")
        comps_3 = db.get_temporary_companions(self.session_id)
        self.assertEqual(len(comps_3), 3)
        self.assertNotIn("Excess Character", [c["name"] for c in comps_3])

        # 3. During spatial transition, temporary companions are included in traveling companions
        sess_with_comps = db.get_session(self.session_id)
        sess_with_comps["current_npcs"] = [
            {"name": "Seo-ah Vance", "role": "President"},
            {"name": "Kazuya Halloway", "role": "Vice President"},
            {"name": "Maya Lin", "role": "Member"},
            {"name": "Bystander Student", "role": "Student"}
        ]
        traveling, left_behind = pres.classify_scene_npcs(
            sess_with_comps,
            actions=[{"label": "Travel to the Campus Dining Hall"}],
            old_primary="Central Courtyard",
            dest_primary="Campus Dining Hall",
            new_loc="Campus Dining Hall & Cafeteria ➔ Main Area"
        )
        traveling_names = [n["name"] for n in traveling]
        left_behind_names = [n["name"] for n in left_behind]

        self.assertIn("Seo-ah Vance", traveling_names)
        self.assertIn("Kazuya Halloway", traveling_names)
        self.assertIn("Maya Lin", traveling_names)
        self.assertIn("Bystander Student", left_behind_names)

        # 4. Part ways dismisses companions
        part_actions = [{"label": "Say goodbye and part ways with everyone"}]
        dlg._compute_dialogue_intent(sess_with_comps, part_actions)
        comps_after = db.get_temporary_companions(self.session_id)
        self.assertEqual(len(comps_after), 0)

    def test_dialogue_exit_excuse_yourself_clears_temporary_companions(self):
        """Verifies that excusing oneself (e.g. from conversation) clears temporary companions."""
        db.add_temporary_companion(self.session_id, "Henry Sterling", "accompany")
        db.add_temporary_companion(self.session_id, "Alicja Yamamoto", "accompany")
        self.assertEqual(len(db.get_temporary_companions(self.session_id)), 2)

        sess = db.get_session(self.session_id)
        actions = [{"label": "Thank Alicja Yamamoto and Artem Suzuki, excuse yourself, and look around the room"}]
        new_partners, has_exited = dlg._compute_dialogue_intent(sess, actions)

        self.assertTrue(has_exited)
        self.assertEqual(new_partners, [])
        comps_after = db.get_temporary_companions(self.session_id)
        self.assertEqual(len(comps_after), 0, "Temporary companions must be cleared when player excuses themselves")

    def test_solo_travel_without_active_dialogue_leaves_temporary_companions_behind(self):
        """When player has already exited conversation and moves alone, companions stay behind."""
        db.add_temporary_companion(self.session_id, "Henry Sterling", "accompany")
        db.add_temporary_companion(self.session_id, "Alicja Yamamoto", "accompany")

        sess = db.get_session(self.session_id)
        sess["dialogue_partner"] = None
        sess["dialogue_partners"] = []
        sess["current_npcs"] = [
            {"name": "Henry Sterling", "role": "Student"},
            {"name": "Alicja Yamamoto", "role": "Student"},
            {"name": "Mr. Joo-won Takahashi", "role": "Teacher"}
        ]
        traveling, left_behind = pres.classify_scene_npcs(
            sess,
            actions=[{"label": "I travel to Shiranui Senior High ➔ Empty Classroom."}],
            old_primary="Homeroom 204",
            dest_primary="Empty Classroom",
            new_loc="Shiranui Senior High ➔ Empty Classroom ➔ Back Corner"
        )
        traveling_names = [n["name"] for n in traveling]
        left_behind_names = [n["name"] for n in left_behind]

        self.assertNotIn("Henry Sterling", traveling_names)
        self.assertNotIn("Alicja Yamamoto", traveling_names)
        self.assertIn("Henry Sterling", left_behind_names)
        self.assertIn("Alicja Yamamoto", left_behind_names)

    def test_unaccompanied_venue_departure_clears_temporary_companions(self):
        """Moving to another venue unaccompanied clears temporary companions."""
        db.add_temporary_companion(self.session_id, "Henry Sterling", "accompany")
        self.assertEqual(len(db.get_temporary_companions(self.session_id)), 1)

        sess = db.get_session(self.session_id)
        sess["current_location"] = "Shiranui Senior High ➔ Homeroom 204"
        actions = [{"label": "I travel to Shiranui Senior High ➔ Empty Classroom."}]
        dlg._compute_dialogue_intent(sess, actions)

        comps_after = db.get_temporary_companions(self.session_id)
        self.assertEqual(len(comps_after), 0, "Unaccompanied departure must clear temporary companions")

    def test_sleep_rest_clears_temporary_companions(self):
        """Sleeping / resting resets temporary companions."""
        db.add_temporary_companion(self.session_id, "Seo-ah Vance", "walking_together")
        self.assertEqual(len(db.get_temporary_companions(self.session_id)), 1)

        apply_sleep_rest(self.session_id, [self.char_id])
        self.assertEqual(len(db.get_temporary_companions(self.session_id)), 0)

    def test_failed_skill_check_dialogue_intent_does_not_book_rendezvous(self):
        """When an action has success=False, rendezvous is not booked and partner is not evicted."""
        sess = db.get_session(self.session_id)
        failed_action = [{
            "label": "Suggest we meet in private at the Botanical Glasshouse to talk",
            "stat": "CHA",
            "success": False
        }]
        new_partners, has_exited = dlg._compute_dialogue_intent(sess, failed_action)
        self.assertFalse(has_exited, "NPC should NOT leave the scene on a failed invitation check")
        self.assertIn("Seo-ah Vance", new_partners, "Active partner should remain to decline in prose")
        
        # Verify no appointment was booked
        appts = db.get_phone_appointments(self.session_id, status="pending")
        self.assertEqual(len(appts), 0, "No appointment should be scheduled when check fails")

    def test_multiday_appointment_clock_and_expiration(self):
        """Verifies appointments created on Day 2 use absolute minutes and expire correctly."""
        # Day 2, 10:00 AM = (2 - 1) * 1440 + 600 = 2040 absolute minutes
        created_abs = 2040
        db.save_rendezvous_appointment(
            session_id=self.session_id,
            npc_id="seo_ah_vance",
            npc_name="Seo-ah Vance",
            rendezvous_location="Campus Promenade & Student Commons ➔ Botanical Glasshouse",
            topic="Secret discussion",
            created_minute=created_abs,
            expiry_minute=created_abs + 45
        )
        
        # Check reminders: at 2060 (20 mins later) -> not due
        reminders_early = db.get_due_reminder_appointments(self.session_id, 2060)
        self.assertEqual(len(reminders_early), 0)
        
        # At 2075 (35 mins later) -> due
        reminders_due = db.get_due_reminder_appointments(self.session_id, 2075)
        self.assertEqual(len(reminders_due), 1)
        self.assertEqual(reminders_due[0]["npc_id"], "seo_ah_vance")
        
        # At 2086 (46 mins later) -> expired / stood up
        expired = db.expire_overdue_appointments(self.session_id, 2086)
        self.assertEqual(len(expired), 1)
        self.assertEqual(expired[0]["status"], "stood_up")


if __name__ == "__main__":
    unittest.main()

