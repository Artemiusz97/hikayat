import unittest
import db
from mechanics.world.locations import (
    ensure_session_locations_seeded,
    reconcile_movement_location,
    extract_movement_destination,
    get_session_school_name,
)
from mechanics.world.locations.hierarchy import get_clean_zone_short_name

HIGH_SCHOOL_SCENARIO = "high_school_drama"

class TestSchoolGateMovement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session_id = 99884411
        cls.char_id = 88774411
        cls.char_name = "Artem"
        with db.get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO characters 
                (id, user_id, name, char_class, gender, scenario, race, hp, max_hp, mp, max_mp, level) 
                VALUES (?, ?, ?, 'Journalist', 'male', ?, 'human', 300, 300, 75, 75, 1)""",
                (cls.char_id, 99994411, cls.char_name, HIGH_SCHOOL_SCENARIO)
            )
            conn.execute(
                """INSERT OR REPLACE INTO sessions 
                (id, mode, capacity, scenario, current_location, current_day, current_minute, turn_order) 
                VALUES (?, 'solo', 1, ?, 'Komorebi Heights Residential Suburban District ➔ Springwater Community Park ➔ Sandbox', 1, 485, '[]')""",
                (cls.session_id, HIGH_SCHOOL_SCENARIO)
            )
            conn.commit()
        ensure_session_locations_seeded(cls.session_id, HIGH_SCHOOL_SCENARIO, char_name=cls.char_name)

    @classmethod
    def tearDownClass(cls):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (cls.session_id,))
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (cls.session_id,))
            conn.execute("DELETE FROM characters WHERE id = ?", (cls.char_id,))
            conn.commit()

    def test_school_main_gates_seeded(self):
        """Verify School Main Gates room and its props are seeded for the session."""
        from mechanics.world.locations.seeds import get_node_props
        locs = db.get_session_locations(self.session_id)
        gate_locs = [l for l in locs if l.get("sub_name") == "School Main Gates"]
        self.assertTrue(len(gate_locs) >= 1, f"Expected School Main Gates room in session_locations, got {len(gate_locs)}")
        self.assertEqual(gate_locs[0].get("primary_name"), "Main Campus Building")
        sub_names = set(get_node_props("loc_school_gate", "School Main Gates", HIGH_SCHOOL_SCENARIO))
        self.assertIn("Entrance Path & Archway", sub_names)
        self.assertIn("Gate Checkpoint", sub_names)
        self.assertIn("Notice Board & Club Banners", sub_names)
        self.assertIn("Front Bicycle Racks", sub_names)

    def test_get_clean_zone_short_name_strips_academic_suffixes(self):
        """Verify get_clean_zone_short_name strips 'High School', 'Academy', etc."""
        self.assertEqual(get_clean_zone_short_name("Aobajohsai High School"), "Aobajohsai")
        self.assertEqual(get_clean_zone_short_name("Westlake Academy"), "Westlake")
        self.assertEqual(get_clean_zone_short_name("Oakhaven Private Academy"), "Oakhaven Private")
        self.assertEqual(get_clean_zone_short_name("St. Jude University"), "St. Jude")

    def test_extract_movement_destination_shorthand_and_generic_school(self):
        """Verify extract_movement_destination resolves shorthand school names and generic 'school'."""
        school_name = get_session_school_name(self.session_id, HIGH_SCHOOL_SCENARIO)
        school_short = get_clean_zone_short_name(school_name)
        
        # Test shorthand: 'The Long Walk to <SchoolShort>'
        dest1 = extract_movement_destination(
            f"The Long Walk to {school_short}",
            self.session_id,
            current_zone="Komorebi Heights Residential Suburban District",
            scen_key=HIGH_SCHOOL_SCENARIO,
            char_name=self.char_name
        )
        self.assertIsNotNone(dest1)
        self.assertEqual(dest1[0], school_name)
        self.assertEqual(dest1[1], "School Main Gates")

        # Test generic: 'Walk to school'
        dest2 = extract_movement_destination(
            "Walk to school",
            self.session_id,
            current_zone="Komorebi Heights Residential Suburban District",
            scen_key=HIGH_SCHOOL_SCENARIO,
            char_name=self.char_name
        )
        self.assertIsNotNone(dest2)
        self.assertEqual(dest2[0], school_name)
        self.assertEqual(dest2[1], "School Main Gates")

    def test_reconcile_movement_user_screenshot_case(self):
        """Regression test for user screenshot: walking from park to school gate updates location correctly."""
        school_name = get_session_school_name(self.session_id, HIGH_SCHOOL_SCENARIO)
        school_short = get_clean_zone_short_name(school_name)
        curr_loc = "Komorebi Heights Residential Suburban District ➔ Springwater Community Park ➔ Sandbox"
        action = f"The Long Walk to {school_short}"
        narrative = (
            f"You round the final corner and see {school_name}'s main gate ahead. "
            "The morning bustle is already underway—students streaming in clusters, some in uniforms, "
            "others in streetwear, chatting and laughing. You can see a noticeable cluster of East District "
            "Delinquents hanging near the gate, their numbers blocking a large chunk of the entrance path. "
            "You stop at the gate, observing how they're positioning themselves."
        )

        # 1. When LLM returns empty location string
        res_empty = reconcile_movement_location(
            self.session_id,
            curr_loc,
            "",
            action_text=action,
            narrative=narrative,
            scen_key=HIGH_SCHOOL_SCENARIO,
            char_name=self.char_name
        )
        self.assertIn(school_name, res_empty)
        self.assertIn("Main Campus Building", res_empty)
        self.assertIn("School Main Gates", res_empty)

        # 2. When LLM echoes previous location string (lazy model)
        res_echo = reconcile_movement_location(
            self.session_id,
            curr_loc,
            curr_loc,
            action_text=action,
            narrative=narrative,
            scen_key=HIGH_SCHOOL_SCENARIO,
            char_name=self.char_name
        )
        self.assertIn(school_name, res_echo)
        self.assertIn("Main Campus Building", res_echo)
        self.assertIn("School Main Gates", res_echo)

    def test_narrative_gate_arrival_fallback_without_destination_in_action(self):
        """Verify narrative proximity scanner catches gate arrival even if action didn't name school."""
        school_name = get_session_school_name(self.session_id, HIGH_SCHOOL_SCENARIO)
        curr_loc = "Komorebi Heights Residential Suburban District ➔ Springwater Community Park ➔ Sandbox"
        action = "Run as fast as you can through the morning streets"
        narrative = (
            f"You sprint through the residential alleys, turning corners until you reach {school_name}. "
            "You stop at the main gate, catching your breath as students stream past the checkpoint."
        )

        res = reconcile_movement_location(
            self.session_id,
            curr_loc,
            "",
            action_text=action,
            narrative=narrative,
            scen_key=HIGH_SCHOOL_SCENARIO,
            char_name=self.char_name
        )
        self.assertIn(school_name, res)
        self.assertIn("School Main Gates", res)
