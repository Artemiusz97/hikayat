import unittest
import json
from unittest.mock import patch, AsyncMock
import db
import scenario_data
from mechanics.world.locations import (
    ensure_session_locations_seeded,
    parse_tiered_location,
    reconcile_movement_location,
    get_archetype_starting_location,
    get_session_school_name,
    resolve_session_location_tokens,
)
from mechanics.world.locations.hierarchy import _resolve_reverse_hierarchy
from game_engine.turn.generation import generate_opening_scene
from game_engine.schemas import SCENE_SCHEMA

HIGH_SCHOOL_SCENARIO = "high_school_drama"

class TestAcademicZoneIntegrityAndStartingHooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session_id = 99881122
        cls.char_id = 88771122
        cls.char_name = "Artem"
        with db.get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO characters 
                (id, user_id, name, char_class, gender, scenario, race, hp, max_hp, mp, max_mp, level) 
                VALUES (?, ?, ?, 'Journalist', 'male', ?, 'human', 300, 300, 75, 75, 2)""",
                (cls.char_id, 99991122, cls.char_name, HIGH_SCHOOL_SCENARIO)
            )
            conn.execute(
                """INSERT OR REPLACE INTO sessions 
                (id, mode, capacity, scenario, current_location, current_day, current_minute, turn_order) 
                VALUES (?, 'solo', 1, ?, 'Westlake Academy -> Class 2-2 (Homeroom)', 1, 480, '[]')""",
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

    def test_homeroom_never_hijacked_to_residential_zone(self):
        """Issue 1 Regression Test: 'Homeroom' containing 'home' must NEVER be hijacked to residential neighborhood."""
        school_name = get_session_school_name(self.session_id, HIGH_SCHOOL_SCENARIO)
        
        # Test reconcile_movement_location
        reconciled = reconcile_movement_location(
            self.session_id,
            "",
            "Class 2-2 (Homeroom)",
            action_text="Begin adventure",
            narrative="You sit in the classroom waiting for homeroom to begin.",
            scen_key=HIGH_SCHOOL_SCENARIO,
            char_name=self.char_name
        )
        z, p, s = parse_tiered_location(reconciled, HIGH_SCHOOL_SCENARIO, session_id=self.session_id, char_name=self.char_name)
        self.assertNotIn("Residential", z)
        self.assertIn(school_name, z)
        self.assertEqual(p, "Class 2-2 (Homeroom)")

    def test_campus_facilities_reverse_hierarchy_heals_foreign_zone(self):
        """Issue 1 Regression Test: If an LLM or caller passes a residential zone with a classroom, it auto-heals to campus zone."""
        school_name = get_session_school_name(self.session_id, HIGH_SCHOOL_SCENARIO)
        poisoned_string = "Wakaba Residential Town ➔ Class 2-2 (Homeroom) ➔ Main Area"
        
        z, p, s = parse_tiered_location(poisoned_string, HIGH_SCHOOL_SCENARIO, session_id=self.session_id, char_name=self.char_name)
        self.assertNotIn("Residential", z)
        self.assertEqual(z, school_name)
        self.assertEqual(p, "Class 2-2 (Homeroom)")

    def test_sub_spot_desk_does_not_match_primary_residence(self):
        """Inversion check must not match 'Artem's Desk' with 'Artem's House'."""
        parts = ["Westlake Preparatory Academy", "Class 2-2 (Homeroom)", f"{self.char_name}'s Desk"]
        rev = _resolve_reverse_hierarchy(parts, HIGH_SCHOOL_SCENARIO, session_id=self.session_id, char_name=self.char_name)
        # Should NOT return Artem's House as primary
        if rev:
            z, p, s = rev
            self.assertNotEqual(p, f"{self.char_name}'s House")

    def test_rooftop_hint_resolves_to_school_rooftop_not_campfire(self):
        """Issue 2 Regression Test: Delve threshold rooftop hint must resolve to campus rooftop, not mountain park campfire."""
        school_name = get_session_school_name(self.session_id, HIGH_SCHOOL_SCENARIO)
        resolved_hint = f"{school_name} ➔ School Rooftop ➔ Rooftop Benches"
        
        z, p, s = get_archetype_starting_location(
            session_id=self.session_id,
            scenario_key=HIGH_SCHOOL_SCENARIO,
            archetype="delve_threshold",
            char_name=self.char_name,
            preferred_hint=resolved_hint
        )
        self.assertEqual(z, school_name)
        self.assertEqual(p, "School Rooftop")
        self.assertIn(s, ("Rooftop Benches", "Behind Water Tank", "Rooftop Fence Line"))

    def test_starting_hook_tokens_resolved_before_archetype_location(self):
        """Issue 2 Regression Test: get_dynamic_starting_hook resolves template tokens in suggested_location before matching."""
        hook_info = scenario_data.get_dynamic_starting_hook(
            scenario=HIGH_SCHOOL_SCENARIO,
            session_id=self.session_id,
            char_name=self.char_name
        )
        self.assertNotIn("{session_", hook_info["suggested_location"])

    def test_high_school_delve_hook_free_of_hardcoded_sunset(self):
        """Issue 3 Regression Test: tags.json must not hardcode golden hour/sunset into morning high school delve hooks."""
        tags = scenario_data.load_tags(reload=True)
        hs_hooks = tags["high_school"]["starting_hooks"]
        delve_hooks = [h for h in hs_hooks if h.get("archetype") == "delve_threshold"]
        self.assertTrue(len(delve_hooks) > 0)
        for h in delve_hooks:
            self.assertNotIn("sunset", h["hook"].lower())
            self.assertNotIn("golden hour", h["hook"].lower())

    def test_scene_schema_contains_location_field(self):
        """SCENE_SCHEMA must define the 3-tiered location field."""
        self.assertIn('"location"', SCENE_SCHEMA)

    @patch("game_engine.call_llm_json")
    def test_opening_scene_injects_temporal_mandate(self, mock_llm):
        """Issue 3 Regression Test: generate_opening_scene injects STRICT TEMPORAL CONSISTENCY MANDATE into prompt."""
        import asyncio
        mock_llm.return_value = {
            "scene_title": "Morning Awakening",
            "narrative": "Morning light shines in the classroom.",
            "choices": [],
            "location": "Westlake Academy ➔ Class 2-2 (Homeroom) ➔ Main Area"
        }
        session = {
            "id": self.session_id,
            "scenario": HIGH_SCHOOL_SCENARIO,
            "current_location": "Westlake Academy ➔ Class 2-2 (Homeroom) ➔ Main Area",
            "current_day": 1,
            "current_minute": 480,
            "history": []
        }
        party = [({"id": self.char_id, "name": self.char_name, "user_id": 99991122}, [])]
        asyncio.run(generate_opening_scene(session, party))
        
        self.assertTrue(mock_llm.called)
        user_prompt_arg = mock_llm.call_args_list[0][0][1]
        self.assertIn("STRICT TEMPORAL CONSISTENCY MANDATE", user_prompt_arg)
        self.assertIn("08:00", user_prompt_arg)

    def test_house_never_hijacked_to_school_zone(self):
        """Regression Test: Character house mistakenly paired with school zone heals to residential zone."""
        from mechanics.world.locations import get_session_residential_neighborhood_name
        res_zone = get_session_residential_neighborhood_name(self.session_id, HIGH_SCHOOL_SCENARIO)
        poisoned = f"Asahi Senior High ➔ {self.char_name}'s House ➔ Bedroom"
        z, p, s = parse_tiered_location(poisoned, HIGH_SCHOOL_SCENARIO, session_id=self.session_id, char_name=self.char_name)
        self.assertEqual(z, res_zone)
        self.assertEqual(p, f"{self.char_name}'s House")
        self.assertEqual(s, "Your Bedroom")

    def test_commercial_shop_never_hijacked_to_school_zone(self):
        """Regression Test: Commercial establishment mistakenly paired with school zone heals to commercial zone."""
        from mechanics.world.locations import get_session_commercial_district_name
        comm_zone = get_session_commercial_district_name(self.session_id, HIGH_SCHOOL_SCENARIO)
        poisoned = "Asahi Senior High ➔ Blue Velvet Café ➔ Table 4"
        z, p, s = parse_tiered_location(poisoned, HIGH_SCHOOL_SCENARIO, session_id=self.session_id, char_name=self.char_name)
        self.assertEqual(z, comm_zone)
        self.assertEqual(p, "Blue Velvet Café")
        self.assertEqual(s, "Table 4")

    def test_expanded_campus_facilities_healed_from_residential(self):
        """Regression Test: Medical/administrative campus facilities paired with residential zone heal to school zone."""
        school_name = get_session_school_name(self.session_id, HIGH_SCHOOL_SCENARIO)
        poisoned = "Wakaba Residential Town ➔ Nurse's Office ➔ Recovery Bed"
        z, p, s = parse_tiered_location(poisoned, HIGH_SCHOOL_SCENARIO, session_id=self.session_id, char_name=self.char_name)
        self.assertEqual(z, school_name)
        self.assertEqual(p, "Nurse's Office")
        self.assertEqual(s, "Recovery Bed")
