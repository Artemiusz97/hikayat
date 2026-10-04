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


if __name__ == "__main__":
    unittest.main()
