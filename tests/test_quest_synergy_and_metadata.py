import unittest
import json
import db
import game_engine
from mechanics.world.waypoints import (
    generate_quest_action_choices,
    tag_and_enrich_quest_choices,
    try_complete_on_skill_check,
    try_advance_on_arrival,
    check_action_matches_waypoint,
    ensure_multi_stage_waypoints
)
from mechanics.world.locations import get_location_scout_description


class TestQuestSynergyAndMetadata(unittest.TestCase):
    def setUp(self):
        self.session_id = 99881
        self.user_id = 99881
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.session_id,))

        db.create_character(self.user_id, "Tester", char_class="Detective", stats={"STR": 5, "PER": 7, "END": 5, "CHA": 8, "INT": 9, "AGI": 6, "LUK": 5})
        self.char = db.get_character(self.user_id)

        # Create session at Science Lab
        with db.get_conn() as conn:
            conn.execute("""
                INSERT INTO sessions (id, channel_id, host_user_id, status, mode, capacity, scenario, current_location, turn_order)
                VALUES (?, 100, ?, 'active', 'solo', 1, 'high_school_drama', 'Westlake Academy ➔ Chemistry & Science Lab ➔ Main Workstations', ?)
            """, (self.session_id, self.user_id, json.dumps([self.user_id])))

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.session_id,))

    def test_deterministic_quest_action_injection(self):
        """Verify that being at the target location injects a tagged quest action in Slot 1."""
        qid = "SQ-TEST-001"
        sub_obj_id = 1
        with db.get_conn() as conn:
            conn.execute("""
                INSERT INTO quests (session_id, quest_id, title, objective, status, sub_objectives_json)
                VALUES (?, ?, 'The Mystery Notes', 'Discover secrets', 'Active', ?)
            """, (self.session_id, qid, json.dumps([{"id": sub_obj_id, "text": "Search for the hidden formulas", "completed": False}])))

            conn.execute("""
                INSERT INTO quest_waypoints (session_id, quest_id, sub_obj_id, stage_index, stage_label, target_location, completion_trigger, status)
                VALUES (?, ?, ?, 1, 'Search the workstations for the hidden formula notes', 'Westlake Academy ➔ Chemistry & Science Lab', 'skill_check', 'active')
            """, (self.session_id, qid, sub_obj_id))

        choices = generate_quest_action_choices(
            self.session_id,
            "Westlake Academy ➔ Chemistry & Science Lab ➔ Main Workstations",
            scen_key="high_school_drama",
            char=self.char
        )

        self.assertGreaterEqual(len(choices), 1)
        q_choice = choices[0]
        self.assertTrue(q_choice.get("is_quest_action"))
        self.assertEqual(q_choice.get("quest_id"), qid)
        self.assertEqual(q_choice.get("sub_obj_id"), sub_obj_id)
        self.assertEqual(q_choice.get("stage_index"), 1)
        self.assertEqual(q_choice.get("stat"), "INT")
        self.assertIn("⭐ [Story Quest]", q_choice.get("label"))

    def test_prevent_false_positives_on_unrelated_roleplay_actions(self):
        """Verify that casual dialogue/roleplay actions in the same room DO NOT complete the quest."""
        qid = "SQ-TEST-002"
        sub_obj_id = 1
        with db.get_conn() as conn:
            conn.execute("""
                INSERT INTO quests (session_id, quest_id, title, objective, status, sub_objectives_json)
                VALUES (?, ?, 'Chemistry Incident', 'Investigate the incident', 'Active', ?)
            """, (self.session_id, qid, json.dumps([{"id": sub_obj_id, "text": "Search the debris for discarded notebooks", "completed": False}])))

            conn.execute("""
                INSERT INTO quest_waypoints (session_id, quest_id, sub_obj_id, stage_index, stage_label, target_location, completion_trigger, status)
                VALUES (?, ?, ?, 1, 'Search for the dropped notebook among the debris', 'Westlake Academy ➔ Chemistry & Science Lab', 'skill_check', 'active')
            """, (self.session_id, qid, sub_obj_id))

        # 1. Casual gossip action without quest metadata
        unrelated_action = {
            "char": self.char,
            "label": "Ask Zihan if she suspects any specific students",
            "stat": "INT",
            "mp_spent": 0,
            "is_quest_action": False
        }
        outcome = {
            "character_outcomes": [{"name": "Tester", "hp_change": 0}],
            "outcome_narrative": "Tester asks Zihan about class drama. She blushes and giggles.",
            "next_narrative": "The conversation stays lighthearted."
        }

        # Apply outcome
        game_engine.apply_outcome(self.session_id, [(self.char, [])], outcome, actions=[unrelated_action])

        # Waypoint must NOT be completed!
        active_wp = db.get_active_waypoint(self.session_id, qid, sub_obj_id)
        self.assertIsNotNone(active_wp)
        self.assertEqual(active_wp["status"], "active")

    def test_deterministic_progression_on_tagged_quest_action(self):
        """Verify that executing a tagged quest action advances the waypoint immediately on success."""
        qid = "SQ-TEST-003"
        sub_obj_id = 1
        with db.get_conn() as conn:
            conn.execute("""
                INSERT INTO quests (session_id, quest_id, title, objective, status, sub_objectives_json)
                VALUES (?, ?, 'Chemistry Incident', 'Investigate the incident', 'Active', ?)
            """, (self.session_id, qid, json.dumps([{"id": sub_obj_id, "text": "Search for dropped notes", "completed": False}])))

            conn.execute("""
                INSERT INTO quest_waypoints (session_id, quest_id, sub_obj_id, stage_index, stage_label, target_location, completion_trigger, status)
                VALUES (?, ?, ?, 1, 'Search for the dropped notebook among the debris', 'Westlake Academy ➔ Chemistry & Science Lab', 'skill_check', 'active')
            """, (self.session_id, qid, sub_obj_id))

        # Tagged Quest Action
        quest_action = {
            "char": self.char,
            "label": "⭐ [Story Quest] Search for the dropped notebook among the debris (INT)",
            "stat": "INT",
            "mp_spent": 0,
            "is_quest_action": True,
            "quest_id": qid,
            "sub_obj_id": sub_obj_id,
            "stage_index": 1
        }
        outcome = {
            "character_outcomes": [{"name": "Tester", "hp_change": 0}],
            "outcome_narrative": "Tester carefully retrieves the stained notebook from under the counter.",
            "next_narrative": "The evidence is secured."
        }

        # Apply outcome
        game_engine.apply_outcome(self.session_id, [(self.char, [])], outcome, actions=[quest_action])

        # Waypoint should now be completed!
        active_wp = db.get_active_waypoint(self.session_id, qid, sub_obj_id)
        self.assertIsNone(active_wp)  # No active waypoints remaining for this sub-obj (all done)
        
        # Sub-objective in quest table should be marked completed
        quests = db.get_session_quests(self.session_id)
        q = next(q for q in quests if q["quest_id"] == qid)
        so = next(s for s in q["sub_objectives"] if s["id"] == sub_obj_id)
        self.assertTrue(so["completed"])

    def test_location_scout_description(self):
        """Verify that area scouting produces rich layout details without raw prop dumps."""
        desc = get_location_scout_description(
            self.session_id,
            "Westlake Academy ➔ Chemistry & Science Lab ➔ Main Workstations",
            scen_key="high_school_drama"
        )
        self.assertIn("Scouting Area", desc)
        self.assertIn("Chemistry & Science Lab", desc)
        # Should contain key sections/sub-locations from seed
        self.assertTrue("Lab Workbenches" in desc or "Chemical Storage Closet" in desc or "Key Sections" in desc)
        # Must NOT dump raw dictionary braces or raw database JSON
        self.assertNotIn("{'props'", desc)
        self.assertNotIn('{"props"', desc)

    def test_dynamic_quest_action_tagging(self):
        """Verify that LLM-generated dialogue choices are dynamically tagged and enriched with quest metadata."""
        qid = "SQ-TEST-004"
        sub_obj_id = 3
        with db.get_conn() as conn:
            conn.execute("""
                INSERT INTO quests (session_id, quest_id, title, objective, status, sub_objectives_json)
                VALUES (?, ?, 'The Council Meeting', 'Submit sanitized report', 'Active', ?)
            """, (self.session_id, qid, json.dumps([{"id": sub_obj_id, "text": "Submit a sanitized report to student leadership", "completed": False}])))

            conn.execute("""
                INSERT INTO quest_waypoints (session_id, quest_id, sub_obj_id, stage_index, stage_label, target_location, target_npc, completion_trigger, status)
                VALUES (?, ?, ?, 1, 'Negotiate terms for a sanitized report with council members', 'Westlake Academy ➔ Chemistry & Science Lab', 'Sofia Anderson', 'skill_check', 'active')
            """, (self.session_id, qid, sub_obj_id))

        raw_llm_choices = [
            {"label": "Negotiate terms for a sanitized report to avoid academic penalties", "stat": "CHA", "requirement": 4},
            {"label": "Analyze Sofia's reaction to see if she has a hidden agenda", "stat": "INT", "requirement": 5},
            {"label": "Thank Sofia Anderson and excuse yourself to step away", "stat": "NONE", "requirement": 0}
        ]

        enriched = tag_and_enrich_quest_choices(
            raw_llm_choices,
            self.session_id,
            "Westlake Academy ➔ Chemistry & Science Lab ➔ Main Workstations",
            scen_key="high_school_drama",
            char=self.char
        )

        # First choice should be enriched and tagged with [Story Quest] and metadata
        self.assertEqual(len(enriched), 3)
        q_choice = enriched[0]
        self.assertTrue(q_choice.get("is_quest_action"))
        self.assertEqual(q_choice.get("quest_id"), qid)
        self.assertEqual(q_choice.get("sub_obj_id"), sub_obj_id)
        self.assertIn("⭐ [Story Quest]", q_choice.get("label"))

        # Other choices should remain untouched
        self.assertFalse(enriched[1].get("is_quest_action", False))
        self.assertFalse(enriched[2].get("is_quest_action", False))

    def test_dynamic_tagging_fallback_when_llm_misses_quest(self):
        """Verify that if LLM choices do not contain any quest-related action, a fallback quest action is prepended."""
        qid = "SQ-TEST-005"
        sub_obj_id = 1
        with db.get_conn() as conn:
            conn.execute("""
                INSERT INTO quests (session_id, quest_id, title, objective, status, sub_objectives_json)
                VALUES (?, ?, 'Formula Hunt', 'Find formulas', 'Active', ?)
            """, (self.session_id, qid, json.dumps([{"id": sub_obj_id, "text": "Find formula", "completed": False}])))

            conn.execute("""
                INSERT INTO quest_waypoints (session_id, quest_id, sub_obj_id, stage_index, stage_label, target_location, completion_trigger, status)
                VALUES (?, ?, ?, 1, 'Search workstations for hidden formula notes', 'Westlake Academy ➔ Chemistry & Science Lab', 'skill_check', 'active')
            """, (self.session_id, qid, sub_obj_id))

        # LLM only generated completely unrelated choices
        raw_llm_choices = [
            {"label": "Look out the window at the soccer field", "stat": "PER", "requirement": 2},
            {"label": "Take a short nap at the desk", "stat": "END", "requirement": 2}
        ]

        enriched = tag_and_enrich_quest_choices(
            raw_llm_choices,
            self.session_id,
            "Westlake Academy ➔ Chemistry & Science Lab ➔ Main Workstations",
            scen_key="high_school_drama",
            char=self.char
        )

        # Fallback should be prepended at index 0
        self.assertGreaterEqual(len(enriched), 3)
        self.assertTrue(enriched[0].get("is_quest_action"))
        self.assertEqual(enriched[0].get("quest_id"), qid)
        self.assertIn("⭐ [Story Quest]", enriched[0].get("label"))


if __name__ == "__main__":
    unittest.main()
