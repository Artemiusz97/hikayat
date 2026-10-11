"""
Unit tests for Hikayat Smartphone / Cyberdeck Meetup Appointments & Rendezvous Engine.
Verifies that NPCs who agree to a meetup via DM reliably appear at the rendezvous location,
that Tier 3 sub-location variations match correctly, and that appointment lifecycles transition properly.
"""
import unittest
import os
import db
import game_engine
from mechanics import waypoints, locations, phone


class TestPhoneMeetupAndRendezvous(unittest.TestCase):
    def setUp(self):
        # Create unique test session and character
        self.session_id = 998811
        self.user_id = 887711
        
        # Clean up any leftover test data
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.session_id,))

        db.create_character(
            user_id=self.user_id,
            name="Artemiusz",
            gender="male",
            stats={"STR": 10, "AGI": 10, "END": 10, "INT": 12, "PER": 10, "CHA": 15, "LUK": 5}
        )
        self.char = db.get_character(self.user_id)

        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        db.save_session_scene(
            self.session_id,
            scene_title="Afternoon Classroom",
            narrative="Artemiusz is checking his phone at his desk.",
            choices=[],
            history=["Turn 1"],
            location="Westlake Academy ➔ Classroom 2-B ➔ Teacher's Desk",
            nearby_enemies=[]
        )

        # Seed known locations
        db.save_session_location(
            session_id=self.session_id,
            location_id="westlake_classroom_2b",
            zone_name="Westlake Academy",
            primary_name="Classroom 2-B",
            sub_name="Teacher's Desk",
            atmosphere="Quiet afternoon classroom."
        )
        db.save_session_location(
            session_id=self.session_id,
            location_id="westlake_school_rooftop",
            zone_name="Westlake Academy",
            primary_name="School Rooftop",
            sub_name="Rooftop Benches",
            atmosphere="Breezy rooftop overlook."
        )

        # Add contact
        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="denise_yamada",
            name="Denise Yamada",
            basic_info={"role": "Student Council President", "location": "Westlake Academy ➔ Student Council Office"},
            track="platonic"
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.session_id,))

    def test_location_matches_waypoint_tier2_flexibility(self):
        """Verify that check_location_matches_waypoint matches across different Tier 3 sub-locations."""
        appt_target = "Westlake Academy ➔ School Rooftop ➔ Rooftop Benches"
        player_loc_1 = "Westlake Academy ➔ School Rooftop ➔ Observation Point"
        player_loc_2 = "Westlake Academy -> School Rooftop -> Main Area"
        player_loc_diff = "Westlake Academy ➔ Classroom 2-B ➔ Desk"

        self.assertTrue(waypoints.check_location_matches_waypoint(player_loc_1, appt_target))
        self.assertTrue(waypoints.check_location_matches_waypoint(player_loc_2, appt_target))
        self.assertFalse(waypoints.check_location_matches_waypoint(player_loc_diff, appt_target))

    def test_build_waypoint_prompt_block_with_destination(self):
        """Verify build_waypoint_prompt_block includes meetup when traveling to destination."""
        db.save_phone_appointment(
            session_id=self.session_id,
            npc_id="denise_yamada",
            npc_name="Denise Yamada",
            rendezvous_location="Westlake Academy ➔ School Rooftop ➔ Rooftop Benches"
        )

        # At origin location without destination: should be empty
        block_origin = waypoints.build_waypoint_prompt_block(
            self.session_id,
            current_location="Westlake Academy ➔ Classroom 2-B ➔ Desk"
        )
        self.assertNotIn("Denise Yamada", block_origin)

        # At origin location WITH destination passed: should include appointment directive
        block_with_dest = waypoints.build_waypoint_prompt_block(
            self.session_id,
            current_location="Westlake Academy ➔ Classroom 2-B ➔ Desk",
            destination_location="Westlake Academy ➔ School Rooftop"
        )
        self.assertIn("Denise Yamada", block_with_dest)
        self.assertIn("MEETUP APPOINTMENT", block_with_dest)

        # Verify prompt generation did NOT mutate appointment status
        appts = db.get_phone_appointments(self.session_id, status="pending")
        self.assertEqual(len(appts), 1)
        self.assertEqual(appts[0]["npc_id"], "denise_yamada")

    def test_process_scene_npcs_injects_appointment_npc(self):
        """Verify process_scene_npcs automatically ensures the meetup NPC is present at rendezvous."""
        db.save_phone_appointment(
            session_id=self.session_id,
            npc_id="denise_yamada",
            npc_name="Denise Yamada",
            rendezvous_location="Westlake Academy ➔ School Rooftop ➔ Rooftop Benches"
        )

        session = db.get_session(self.session_id)
        llm_result = {
            "npcs_present": [],  # LLM omitted all NPCs
            "entity_audit": {"present_named_characters": [], "speaking_characters": []}
        }
        old_loc = "Westlake Academy ➔ Classroom 2-B ➔ Desk"
        new_loc = "Westlake Academy ➔ School Rooftop ➔ Observation Point"

        scene_npcs = game_engine.process_scene_npcs(llm_result, session, new_loc, old_loc)
        npc_names = [n["name"] for n in scene_npcs if isinstance(n, dict)]

        self.assertIn("Denise Yamada", npc_names)

    def test_tag_and_enrich_quest_choices_adds_meetup_choice(self):
        """Verify tag_and_enrich_quest_choices injects a meetup interaction choice at rendezvous."""
        db.save_phone_appointment(
            session_id=self.session_id,
            npc_id="denise_yamada",
            npc_name="Denise Yamada",
            rendezvous_location="Westlake Academy ➔ School Rooftop ➔ Rooftop Benches"
        )

        raw_choices = [
            {"label": "Look out over the campus railing", "stat": "PER", "requirement": 5},
            {"label": "Search for any hidden items", "stat": "INT", "requirement": 6}
        ]
        enriched = waypoints.tag_and_enrich_quest_choices(
            raw_choices,
            session_id=self.session_id,
            current_location="Westlake Academy ➔ School Rooftop ➔ Observation Point",
            scen_key="high_school_drama",
            char=self.char
        )

        labels = [c.get("label", "") for c in enriched]
        self.assertTrue(any("Denise Yamada" in l and "Meetup" in l for l in labels))

    def test_apply_outcome_advances_appointment_to_arrived(self):
        """Verify apply_outcome marks the appointment as arrived once at destination."""
        db.save_phone_appointment(
            session_id=self.session_id,
            npc_id="denise_yamada",
            npc_name="Denise Yamada",
            rendezvous_location="Westlake Academy ➔ School Rooftop ➔ Rooftop Benches"
        )

        outcome = {
            "location": "Westlake Academy ➔ School Rooftop ➔ Observation Point",
            "npcs_present": [{"name": "Denise Yamada"}]
        }
        party = [(self.char, [])]
        action = {"label": "I travel to Westlake Academy ➔ School Rooftop.", "mp_spent": 0, "check": None}

        game_engine.apply_outcome(self.session_id, party, outcome, actions=[action])

        # Verify pending is empty and arrived has the appointment
        pending = db.get_phone_appointments(self.session_id, status="pending")
        arrived = db.get_phone_appointments(self.session_id, status="arrived")
        self.assertEqual(len(pending), 0)
        self.assertEqual(len(arrived), 1)
        self.assertEqual(arrived[0]["npc_id"], "denise_yamada")

    def test_in_dialogue_prevents_greeting_choice_injection(self):
        """Verify tag_and_enrich_quest_choices does NOT inject greeting choices when already in dialogue."""
        db.save_phone_appointment(
            session_id=self.session_id,
            npc_id="denise_yamada",
            npc_name="Denise Yamada",
            rendezvous_location="Westlake Academy ➔ School Rooftop ➔ Rooftop Benches"
        )
        # Put session into active dialogue mode with Denise
        db.save_session_scene(
            self.session_id,
            scene_title="Talking with Denise",
            narrative="Denise is discussing council reorganization.",
            choices=[],
            history=["Turn 1"],
            location="Westlake Academy ➔ School Rooftop ➔ Rooftop Benches",
            current_npcs=[{"name": "Denise Yamada"}],
            dialogue_partner="Denise Yamada"
        )

        raw_choices = [
            {"label": "Discuss a strategic plan for reorganizing the student body", "stat": "INT", "requirement": 6},
            {"label": "Propose a coordinated effort to secure the corridors", "stat": "CHA", "requirement": 7}
        ]
        enriched = waypoints.tag_and_enrich_quest_choices(
            raw_choices,
            session_id=self.session_id,
            current_location="Westlake Academy ➔ School Rooftop ➔ Rooftop Benches",
            scen_key="high_school_drama",
            char=self.char
        )

        labels = [c.get("label", "") for c in enriched]
        # Must NOT inject 'Greet and talk with Denise Yamada'
        self.assertFalse(any("Greet and talk" in l for l in labels))

    def test_clean_choices_filters_out_greeting_when_in_dialogue(self):
        """Verify _clean_choices strictly filters out any greeting choices targeting the active dialogue partner."""
        from cogs.adventure import AdventureCog
        incoming_choices = [
            {"label": "Greet and talk with Denise Yamada", "stat": "NONE", "requirement": 0},
            {"label": "Discuss a strategic plan for reorganizing the student body", "stat": "INT", "requirement": 6},
            {"label": "Propose a coordinated effort to secure the corridors", "stat": "CHA", "requirement": 7},
            {"label": "Thank Denise and excuse yourself to survey the rooftop", "stat": "NONE", "requirement": 0}
        ]
        cleaned = AdventureCog._clean_choices(
            incoming_choices,
            scenario="high_school_drama",
            location="Westlake Academy ➔ School Rooftop ➔ Rooftop Benches",
            char=self.char,
            dialogue_partner="Denise Yamada",
            current_npcs=[{"name": "Denise Yamada"}],
            session_id=self.session_id
        )

        labels = [c.get("label", "") for c in cleaned]
        # Greet and talk must be filtered out
        self.assertFalse(any("Greet and talk with Denise Yamada" in l for l in labels))
        self.assertTrue(any("Discuss a strategic plan" in l for l in labels))
        self.assertTrue(any("Thank Denise" in l for l in labels))

    def test_meetup_reschedule_updates_appointment_and_marker(self):
        """Verifies that rescheduling a meetup via phone DM updates the appointment and map marker."""
        import asyncio
        from unittest.mock import patch, AsyncMock
        from skill_check import CheckResult
        from mechanics.system.phone.messaging import (
            is_meetup_reschedule_request,
            is_meetup_confirmation_message,
            generate_contact_dm_reply
        )

        # 1. Test reschedule & confirmation intent classification
        self.assertTrue(is_meetup_reschedule_request("Can we meet somewhere more private?"))
        self.assertTrue(is_meetup_reschedule_request("Let's meet at the music room instead."))
        self.assertTrue(is_meetup_reschedule_request("Could we go somewhere quiet?"))
        self.assertTrue(is_meetup_reschedule_request("How about the Old East Wing Music Room?"))
        self.assertTrue(is_meetup_confirmation_message("Sounds nice"))
        self.assertTrue(is_meetup_confirmation_message("Deal"))
        self.assertTrue(is_meetup_confirmation_message("See you there"))

        # 2. Set up initial appointment at School Main Gates
        initial_loc = "Sakuragaoka Academy ➔ School Main Gates ➔ Entrance Steps"
        new_loc_primary = "Old East Wing Music Room"
        new_loc_full = "Cultural Union & Performing Arts Annex ➔ Old East Wing Music Room ➔ Upright Piano Alcove"

        db.save_session_location(
            session_id=self.session_id,
            location_id="sakuragaoka_main_gates",
            zone_name="Sakuragaoka Academy",
            primary_name="School Main Gates",
            sub_name="Entrance Steps",
            atmosphere="School entrance."
        )
        db.save_session_location(
            session_id=self.session_id,
            location_id="old_east_wing_music_room",
            zone_name="Cultural Union & Performing Arts Annex",
            primary_name="Old East Wing Music Room",
            sub_name="Upright Piano Alcove",
            atmosphere="An empty, quiet music room."
        )

        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="mia_yamada",
            name="Mia Yamada",
            basic_info={"role": "Student"}
        )
        contact = db.get_contact(self.session_id, "mia_yamada", self.char["id"])

        # Save initial appointment
        db.save_phone_appointment(self.session_id, "mia_yamada", "Mia Yamada", initial_loc)
        appts = db.get_phone_appointments(self.session_id, status="pending")
        self.assertEqual(len(appts), 1)
        self.assertEqual(appts[0]["rendezvous_location"], initial_loc)

        # Initial markers check
        markers_before = waypoints.get_location_waypoint_markers(self.session_id)
        self.assertTrue(any("💌" in tag for tag in markers_before.get("School Main Gates", [])))
        self.assertFalse(any("💌" in tag for tag in markers_before.get("Old East Wing Music Room", [])))

        # 3. Simulate Player sending "Can we meet somewhere more private?"
        mock_check = CheckResult(
            chance=85,
            roll=20.0,
            tier="success",
            tier_label="Success",
            succeeded=True,
            requirement=5
        )
        mock_llm_reply = {
            "reply_text": "Sure, let's meet at the Old East Wing Music Room.",
            "affinity_delta": 2,
            "rendezvous_location": new_loc_primary
        }

        sess = db.get_session(self.session_id)
        with patch("mechanics.system.phone.call_llm_json", new=AsyncMock(return_value=mock_llm_reply)), \
             patch("llm_client.call_llm_json", new=AsyncMock(return_value=mock_llm_reply)), \
             patch("mechanics.system.phone.messaging.resolve_check", return_value=mock_check):
            result = asyncio.run(generate_contact_dm_reply(
                session=sess,
                contact=contact,
                player_char=self.char,
                user_message="Can we meet somewhere more private?",
                intent="custom"
            ))

        # 4. Verify appointment in DB was updated to the new music room
        appts_after = db.get_phone_appointments(self.session_id, status="pending")
        self.assertEqual(len(appts_after), 1)
        self.assertIn("Old East Wing Music Room", appts_after[0]["rendezvous_location"])
        self.assertEqual(
            appts_after[0]["rendezvous_location"],
            "Cultural Union & Performing Arts Annex ➔ Old East Wing Music Room ➔ Upright Piano Alcove"
        )

        # 5. Verify waypoint markers update to the new location and no longer point to School Main Gates
        markers_after = waypoints.get_location_waypoint_markers(self.session_id)
        self.assertFalse(any("💌" in tag for tag in markers_after.get("School Main Gates", [])))
        self.assertTrue(any("💌" in tag for tag in markers_after.get("Old East Wing Music Room", [])))

    def test_private_phone_meetup_prevents_uninvited_bystanders_from_traveling(self):
        """Verify that ambient classmates from homeroom stay behind when traveling to a private phone rendezvous."""
        music_room = "Cultural Union & Performing Arts Annex ➔ Old East Wing Music Room ➔ Upright Piano Alcove"
        hallway = "Sakuragaoka Academy ➔ School Hallways ➔ Main Area"

        # Save active appointment with Mia Yamada in the music room
        db.save_phone_appointment(self.session_id, "mia_yamada", "Mia Yamada", music_room)

        session = {
            "id": self.session_id,
            "scenario": "high_school_drama",
            "current_location": hallway,
            "current_npcs": [
                {"name": "Yuki Kuroda", "role": "Student"},
                {"name": "Leon Schneider", "role": "Club Member"}
            ],
            "dialogue_partners": ["Yuki Kuroda"],
            "history": ["Player talked briefly with Yuki in the hallway."]
        }

        # Player travels to music room
        actions = [{"label": f"I travel to {music_room}"}]
        llm_result = {
            "location": music_room,
            "npcs_present": [
                {"name": "Mia Yamada", "role": "Student"},
                {"name": "Yuki Kuroda"},
                {"name": "Leon Schneider"}
            ]
        }

        processed = game_engine.process_scene_npcs(
            llm_result,
            session,
            new_loc=music_room,
            old_loc=hallway,
            actions=actions
        )
        names = [n["name"] for n in processed]

        # Mia Yamada must be present for the rendezvous
        self.assertIn("Mia Yamada", names)
        # Yuki and Leon from the hallway must NOT travel to the private meetup
        self.assertNotIn("Yuki Kuroda", names)
        self.assertNotIn("Leon Schneider", names)

    def test_first_name_and_full_name_deduplication_in_reconciliation(self):
        """Verify that single-word first names (e.g. Yuki, Leon) are deduplicated into full canonical names."""
        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="yuki_kuroda",
            name="Yuki Kuroda",
            basic_info={"role": "Student"},
            track="platonic"
        )
        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id="leon_schneider",
            name="Leon Schneider",
            basic_info={"role": "Club Member"},
            track="platonic"
        )

        session = {
            "id": self.session_id,
            "scenario": "high_school_drama",
            "current_location": "Cultural Union & Performing Arts Annex ➔ Old East Wing Music Room ➔ Upright Piano Alcove",
            "current_npcs": [{"name": "Mia Yamada", "role": "Student"}],
            "history": []
        }

        # Incoming entities contain both short names from entity audit and full names from contact scan
        llm_result = {
            "location": "Cultural Union & Performing Arts Annex ➔ Old East Wing Music Room ➔ Upright Piano Alcove",
            "npcs_present": [
                {"name": "Mia Yamada", "role": "Student"},
                {"name": "Yuki", "role": ""},
                {"name": "Leon", "role": ""},
                {"name": "Yuki Kuroda", "role": "Student"},
                {"name": "Leon Schneider", "role": "Club Member"}
            ]
        }

        processed = game_engine.process_scene_npcs(
            llm_result,
            session,
            new_loc=session["current_location"],
            old_loc=session["current_location"]
        )
        names = [n["name"] for n in processed]

        # Must contain only canonical full names, no duplicates
        self.assertIn("Mia Yamada", names)
        self.assertIn("Yuki Kuroda", names)
        self.assertIn("Leon Schneider", names)
        self.assertNotIn("Yuki", names)
        self.assertNotIn("Leon", names)
        self.assertEqual(len(names), 3)

    def test_relationship_updates_does_not_trigger_meetup_history(self):
        """Verify that 'updates' substring containing 'date' does not falsely trigger narrative continuity bridge."""
        from mechanics.world.mobility import has_narrative_continuity_bridge

        session = {
            "id": self.session_id,
            "scenario": "high_school_drama",
            "current_location": "Sakuragaoka Academy ➔ School Hallways ➔ Main Area",
            "history": [
                {
                    "relationship_updates": [{"npc_name": "Yuki Kuroda", "delta_score": 3}],
                    "witnessed_by": ["Artemiusz", "Yuki Kuroda"],
                    "narrative": "Artemiusz walks through the school hallway."
                }
            ]
        }
        has_bridge = has_narrative_continuity_bridge(
            "Yuki Kuroda",
            session=session,
            actions=[{"label": "Travel to Music Room"}],
            new_loc="Cultural Union & Performing Arts Annex ➔ Old East Wing Music Room ➔ Upright Piano Alcove"
        )
        self.assertFalse(has_bridge)


if __name__ == "__main__":
    unittest.main()
