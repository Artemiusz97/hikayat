import unittest
import db
import game_engine
from mechanics.world.locations import (
    is_movement_action,
    extract_movement_destination,
    reconcile_movement_location,
    format_tiered_location_string
)

class TestLocationSwitchingReliability(unittest.TestCase):
    def setUp(self):
        self.user_id = 991122
        self.char_name = "Artemiusz"

        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))

        db.create_character(
            user_id=self.user_id,
            name=self.char_name,
            gender="male",
            stats={"STR": 10, "AGI": 10, "END": 10, "INT": 12, "PER": 10, "CHA": 15, "LUK": 5}
        )
        self.char = db.get_character(self.user_id)

        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="nsfw_high_school_drama"
        )

        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))

        # Seed realistic session locations
        locations_to_seed = [
            ("Westlake Academy", "Teachers' Staff Room", "Central Table Area"),
            ("Westlake Academy", "Teachers' Staff Room", "Homeroom Teacher's Desk"),
            ("Westlake Academy", "School Hallways", "Main Corridor"),
            ("Westlake Academy", "School Hallways", "Locker Row"),
            ("Westlake Academy", "Classroom 2-B (Homeroom)", "Student Desks"),
            ("Sakura Hill Residential Town", "Artemiusz's House", "Living Room"),
            ("Sakura Hill Residential Town", "Artemiusz's House", "Your Bedroom"),
            ("Sakura Hill Residential Town", "Artemiusz's House", "Kitchen"),
            ("Sakura Hill Residential Town", "Artemiusz's House", "Front Porch"),
        ]
        for z, p, s in locations_to_seed:
            loc_id = f"{z}_{p}_{s}".lower().replace(" ", "_").replace("'", "")
            db.save_session_location(self.session_id, loc_id, z, p, s, atmosphere="Quiet room")

        db.upsert_contact(
            self.session_id,
            "sofia_anderson",
            "Sofia Anderson",
            character_id=self.char["id"],
            delta_score=50,
            track="platonic"
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))

    def test_movement_action_detection_and_metaphor_filtering(self):
        """Verify that relational movement options are detected while conversational metaphors are filtered."""
        # True movement actions
        self.assertTrue(is_movement_action("Gently guide her toward the exit... with a confident hand on her back"))
        self.assertTrue(is_movement_action("Thank Sofia and excuse yourself to head... ...home together"))
        self.assertTrue(is_movement_action("Maintain your clinical composure and lead... ...the way out"))
        self.assertTrue(is_movement_action("Artemiusz reaches out and guides Sofia toward the bedroom"))
        self.assertTrue(is_movement_action("Steer Sofia toward the bedroom door"))
        self.assertTrue(is_movement_action("Step into the hallway together"))

        # Conversational / Metaphorical actions (must NOT be treated as movement)
        self.assertFalse(is_movement_action("Gently guide the conversation toward her club activities"))
        self.assertFalse(is_movement_action("Steer the debate away from school politics"))
        self.assertFalse(is_movement_action("Lead the discussion on student council budget"))
        self.assertFalse(is_movement_action("Ask Sofia about her bedroom preferences"))
        self.assertFalse(is_movement_action("Discuss the rumors in the staff room"))

    def test_room_exit_to_hallway_and_npc_lifecycle(self):
        """Verify that leaving the staff room into the hallway updates the location to School Hallways and drops Coach Nakamura."""
        initial_loc = "Westlake Academy ➔ Teachers' Staff Room ➔ Central Table Area"
        db.save_session_scene(
            self.session_id,
            scene_title="Staff Room Meeting",
            narrative="Talking in the staff room.",
            choices=[],
            history=["Turn 1"],
            location=initial_loc,
            current_npcs=[
                {"name": "Sofia Anderson", "role": "Track Ace"},
                {"name": "Coach Larry Nakamura", "role": "Faculty Coach"}
            ]
        )
        sess = db.get_session(self.session_id)

        class MockCheck:
            succeeded = True
            is_success = True
            tier = "success"

        action = [{"label": "🚪 Thank Sofia and excuse yourself to head... ...home together", "check": MockCheck()}]
        raw_result = {
            "scene_title": "The Quiet After the Storm",
            "narrative": "As they step into the hallway, the heavy door of the staff room clicks shut, sealing away the administrative hum of the faculty. The air in the corridor is cooler and smells faintly of floor wax. Sofia walks beside him, her athletic stride matching his pace. 'So,' she says, 'away from the faculty's gaze at last.'",
            "location": "Westlake Academy ➔ Teachers' Staff Room ➔ Hallway Entrance", # LLM lazy output
            "next_choices": [{"label": "Walk down the corridor"}],
            "relationship_updates": [{"npc_name": "Sofia Anderson", "delta_score": 1}]
        }

        # Reconcile location and process NPCs
        new_loc = reconcile_movement_location(
            self.session_id,
            initial_loc,
            raw_result.get("location", ""),
            action_text=action[0]["label"],
            narrative=raw_result["narrative"],
            scen_key="nsfw_high_school_drama",
            char_name=self.char_name
        )
        raw_result["location"] = new_loc
        raw_result["npcs_present"] = game_engine.process_scene_npcs(raw_result, sess, new_loc, initial_loc, actions=action)

        # 1. Verify location was reconciled to School Hallways
        self.assertIn("School Hallways", new_loc)
        self.assertNotIn("Teachers' Staff Room", new_loc)

        # 2. Verify Coach Nakamura was dropped from npcs_present, while Sofia remained
        npcs_present = raw_result["npcs_present"]
        npc_names = [n.get("name") if isinstance(n, dict) else str(n) for n in npcs_present]
        self.assertIn("Sofia Anderson", npc_names)
        self.assertNotIn("Coach Larry Nakamura", npc_names)

    def test_room_to_room_sub_area_transition_inside_house(self):
        """Verify that guiding Sofia from the Living Room to the Bedroom reliably switches the sub-area even if LLM repeats Living Room."""
        initial_loc = "Sakura Hill Residential Town ➔ Artemiusz's House ➔ Living Room"
        db.save_session_scene(
            self.session_id,
            scene_title="Living Room Lounge",
            narrative="Sitting in the living room.",
            choices=[],
            history=["Turn 1"],
            location=initial_loc,
            current_npcs=[{"name": "Sofia Anderson"}]
        )
        sess = db.get_session(self.session_id)

        class MockCheck:
            succeeded = True
            is_success = True
            tier = "success"

        action = [{"label": "[CHA] Reaches out and guides Sofia toward the bedroom", "check": MockCheck()}]
        raw_result = {
            "scene_title": "The Threshold of Intimacy",
            "narrative": "As they enter the room, the soft light of the evening filters through the curtains. Sofia stops beside the bed, her expression an open invitation of confidence and trust. 'You're surprisingly decisive,' she whispers.",
            "location": "Sakura Hill Residential Town ➔ Artemiusz's House ➔ Living Room", # LLM lazy output (repeated old location)
            "next_choices": [{"label": "Step closer to the bed"}],
            "relationship_updates": [{"npc_name": "Sofia Anderson", "delta_score": 2}]
        }

        new_loc = reconcile_movement_location(
            self.session_id,
            initial_loc,
            raw_result.get("location", ""),
            action_text=action[0]["label"],
            narrative=raw_result["narrative"],
            scen_key="nsfw_high_school_drama",
            char_name=self.char_name
        )

        # Verify sub-area accurately switched to Your Bedroom
        self.assertIn("Artemiusz's House", new_loc)
        self.assertIn("Your Bedroom", new_loc)
        self.assertNotIn("Living Room", new_loc)

    def test_dialogue_quote_mentions_do_not_cause_false_positive_transitions(self):
        """Verify that merely mentioning a room or location in spoken dialogue does NOT trigger a transition."""
        initial_loc = "Sakura Hill Residential Town ➔ Artemiusz's House ➔ Living Room"
        db.save_session_scene(
            self.session_id,
            scene_title="Living Room Tea",
            narrative="Tea time.",
            choices=[],
            history=["Turn 1"],
            location=initial_loc,
            current_npcs=[]
        )

        class MockCheck:
            succeeded = True
            is_success = True
            tier = "success"

        action = [{"label": "Ask Sofia about her morning routine", "check": MockCheck()}]
        raw_result = {
            "scene_title": "Tea Time",
            "narrative": "Artemiusz poured tea on the low table in the living room. Sofia smiled and said, 'Thanks! Yesterday I was studying in the Teachers' Staff Room and then relaxed in my bedroom, but your place is much cozier.'",
            "location": "Sakura Hill Residential Town ➔ Artemiusz's House ➔ Living Room",
            "next_choices": [{"label": "Offer her a cookie"}],
            "relationship_updates": [{"npc_name": "Sofia Anderson", "delta_score": 1}]
        }

        new_loc = reconcile_movement_location(
            self.session_id,
            initial_loc,
            raw_result.get("location", ""),
            action_text=action[0]["label"],
            narrative=raw_result["narrative"],
            scen_key="nsfw_high_school_drama",
            char_name=self.char_name
        )

        # Verify location remained firmly at Living Room
        self.assertEqual(new_loc, "Sakura Hill Residential Town ➔ Artemiusz's House ➔ Living Room")

    def test_dynamic_establishment_generation_without_generic_suffix_collision(self):
        """
        Verify that moving to a 'vintage bookstore' dynamically creates and registers the
        Vintage Bookstore establishment rather than colliding with 'Convenience Store' via substring 'store'.
        """
        from mechanics.world.locations import ensure_session_locations_seeded
        ensure_session_locations_seeded(self.session_id, "high_school_drama", char_name=self.char_name)

        initial_loc = "Komorebi Commercial Strip ➔ Café Monolith ➔ Corner Table"
        action = [{"label": "Step out into the cool evening air together toward the vintage bookstore"}]
        raw_result = {
            "scene_title": "The Quiet Rhythm of the Street",
            "narrative": "The neon lights of the commercial strip blur as they head toward the vintage bookstore.",
            "location": "Komorebi Commercial Strip ➔ Vintage Bookstore ➔ Rare Manuscripts Aisle"
        }

        new_loc = reconcile_movement_location(
            self.session_id,
            initial_loc,
            raw_result.get("location", ""),
            action_text=action[0]["label"],
            narrative=raw_result["narrative"],
            scen_key="high_school_drama",
            char_name=self.char_name
        )

        # 1. Must NOT be hijacked to Convenience Store
        self.assertNotIn("Convenience Store", new_loc)
        # 2. Must correctly register Vintage Bookstore
        self.assertIn("Vintage Bookstore", new_loc)
        self.assertIn("Rare Manuscripts Aisle", new_loc)

        # 3. Verify SQLite spatial registry stored Vintage Bookstore with is_dynamic=1
        stored_locs = db.get_session_locations(self.session_id)
        bookstore_entry = next((l for l in stored_locs if l.get("primary_name") == "Vintage Bookstore"), None)
        self.assertIsNotNone(bookstore_entry)
        self.assertEqual(bookstore_entry.get("is_dynamic"), 1)

    def test_npc_family_residence_generation_and_sibling_deduplication(self):
        """
        Verify that visiting Maya Anderson or Sofia Anderson resolves to the same
        surname-based household ('Anderson Residence') in the Residential zone.
        """
        from mechanics.world.locations import resolve_npc_residence, get_session_residential_neighborhood_name
        
        db.upsert_contact(self.session_id, "maya_anderson", "Maya Anderson", basic_info={"sibling_name": "Sofia Anderson"})
        db.upsert_contact(self.session_id, "sofia_anderson", "Sofia Anderson", basic_info={"sibling_name": "Maya Anderson"})

        res_zone = get_session_residential_neighborhood_name(self.session_id, "high_school_drama")
        
        # 1. Resolve for Maya
        z1, p1 = resolve_npc_residence(self.session_id, "Maya Anderson", "high_school_drama")
        self.assertEqual(z1, res_zone)
        self.assertEqual(p1, "Anderson Residence")

        # 2. Resolve for Sofia -> must reuse the same Anderson Residence
        z2, p2 = resolve_npc_residence(self.session_id, "Sofia Anderson", "high_school_drama")
        self.assertEqual(z2, res_zone)
        self.assertEqual(p2, "Anderson Residence")
        self.assertEqual(p1, p2)

        # 3. Single-word resolution with contact lookup
        z3, p3 = resolve_npc_residence(self.session_id, "Maya", "high_school_drama")
        self.assertEqual(p3, "Anderson Residence")

    def test_companion_home_movement_action_routing_to_residential_zone(self):
        """
        Verify that when visiting a companion's home, the movement engine automatically routes
        to the Residential zone and normalizes the residence foyer.
        """
        from mechanics.world.locations import get_session_residential_neighborhood_name
        
        db.upsert_contact(self.session_id, "maya_anderson", "Maya Anderson", basic_info={"sibling_name": "Sofia Anderson"})
        with db.get_conn() as conn:
            conn.execute("UPDATE sessions SET dialogue_partner = 'Maya Anderson' WHERE id = ?", (self.session_id,))

        res_zone = get_session_residential_neighborhood_name(self.session_id, "high_school_drama")

        initial_loc = "Komorebi Commercial Strip ➔ Vintage Bookstore ➔ Rare Manuscripts Section"
        action = [{"label": "Hold her hand and head toward her home together"}]
        raw_result = {
            "scene_title": "The Path to Privacy",
            "narrative": "As they leave the humming neon lights behind, Maya guides him through the winding streets of the residential district.",
            "location": "Komorebi Commercial Strip ➔ Street ➔ Residential Entrance"
        }

        new_loc = reconcile_movement_location(
            self.session_id,
            initial_loc,
            raw_result.get("location", ""),
            action_text=action[0]["label"],
            narrative=raw_result["narrative"],
            scen_key="high_school_drama",
            char_name=self.char_name
        )

        # Must be in the Residential Zone, at Anderson Residence
        self.assertIn(res_zone, new_loc)
        self.assertIn("Anderson Residence", new_loc)

    def test_apply_outcome_handles_nameless_and_none_npcs(self):
        """apply_outcome must not crash when outcome contains nameless or None NPCs."""
        party = [(self.char, [])]
        outcome = {
            "narrative": "You step into the hallway.",
            "location": "Westlake Academy ➔ School Hallways ➔ Main Corridor",
            "npcs_present": [
                None,
                {"name": None, "role": "student"},
                {"type": "person", "description": "A group of students walking by"},
                {"name": "Alice", "role": "student"},
                "Bob"
            ],
            "new_entities": [
                {"type": "person", "description": "A wandering teacher with papers"},
                {"name": None},
                None
            ]
        }
        action = {"label": "Travel to School Hallways", "mp_spent": 0}
        # This must not raise AttributeError: 'NoneType' object has no attribute 'strip'
        items_gained = game_engine.apply_outcome(
            self.session_id, party, outcome, {self.user_id: 0}, actions=[action]
        )
        self.assertIsInstance(items_gained, dict)


if __name__ == "__main__":
    unittest.main()


