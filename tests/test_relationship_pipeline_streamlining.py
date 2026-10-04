"""
Unit tests for Issue #2: Streamlined Relationship & Intimate Milestone Pipeline.
Verifies single modifier evaluation, variable bleed prevention, polite dialogue fallback,
and deduplicated milestone processing.
"""
import json
import unittest
import db
import game_engine
from game_engine import apply_outcome


class TestRelationshipPipelineStreamlining(unittest.TestCase):
    def setUp(self):
        self.session_id = 99882
        self.user_id = 88772
        self.char_id = 77662

        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE id=? OR user_id=?", (self.char_id, self.user_id))
            conn.execute("DELETE FROM contacts WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM lorebook WHERE session_id=?", (self.session_id,))

            conn.execute(
                """INSERT INTO characters (id, user_id, name, char_class, gender, scenario,
                                          str_, per_, end_, cha, int_, agi, luk, hp, max_hp, mp, max_mp, level, xp, gold, status_effects, created_at)
                   VALUES (?, ?, 'Artemiusz', 'Scholar', 'male', 'high_school_drama',
                           10, 10, 10, 14, 12, 10, 10, 100, 100, 50, 50, 6, 0, 100, '[]', 0)""",
                (self.char_id, self.user_id)
            )

            current_npcs = [
                {"name": "Sofia Anderson", "role": "Club President"},
                {"name": "Yea-ji Kang", "role": "Student Council President"},
                {"name": "Maya Anderson", "role": "Student"}
            ]

            conn.execute(
                """INSERT INTO sessions (id, mode, capacity, status, scenario, current_location, current_npcs_json, turn_order, created_at, updated_at)
                   VALUES (?, 'solo', 1, 'active', 'high_school_drama', 'Westlake Academy ➔ Student Council Office', ?, ?, 0, 0)""",
                (self.session_id, json.dumps(current_npcs), json.dumps([self.user_id]))
            )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE id=? OR user_id=?", (self.char_id, self.user_id))
            conn.execute("DELETE FROM contacts WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM lorebook WHERE session_id=?", (self.session_id,))

    def test_single_modifier_application_on_synthesized_fallback(self):
        """Verify that trait and preference modifiers are applied exactly once,
        not pre-applied in Pass A and re-applied in Pass B (no double-dipping)."""
        char = db.get_character(self.user_id)
        party = [(char, None)]

        # Pre-seed Yea-ji Kang with a known preference: 'Favors Intellectual & Tactical Depth' (+2 for analytical actions)
        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char_id,
            npc_id="Yea-ji Kang",
            name="Yea-ji Kang",
            new_preferences=["Favors Intellectual & Tactical Depth"],
            appearance={"erotic_openness": "modest"}
        )
        c_before = db.get_contact(self.session_id, "Yea-ji Kang", self.char_id)
        self.assertEqual(c_before["relationship_score"], 0)

        # Intellectual action label: "analyze study notes with Yea-ji Kang"
        actions = [{
            "char": char,
            "label": "Analyze study notes and strategic records with Yea-ji Kang",
            "stat": "INT",
            "check": {"is_success": True, "tier": "success"}
        }]
        outcome = {
            "outcome_narrative": "Yea-ji Kang reviews the detailed records with keen interest.",
            "next_narrative": "She nods approvingly.",
            "relationship_updates": [],
            "npcs_present": [{"name": "Yea-ji Kang", "role": "Student Council President"}]
        }

        apply_outcome(self.session_id, party, outcome, mp_already_spent=False, actions=actions)

        # Base for INT success is 3. With 'Favors Intellectual & Tactical Depth' (+2) and 'Warm' trait (+30% gain):
        # Single application: (3 + 2) * 1.3 = 6.5 -> 6.
        # If double-dipped between Pass A and Pass B, it would have been ((3 + 2) * 1.3 + 2) * 1.3 = 10.
        c_after = db.get_contact(self.session_id, "Yea-ji Kang", self.char_id)
        self.assertIsNotNone(c_after)
        self.assertEqual(c_after["relationship_score"], 6)

    def test_polite_thank_action_receives_fallback_affinity(self):
        """Verify that a polite dialogue action containing 'thank' is NOT falsely categorized as an exit action."""
        char = db.get_character(self.user_id)
        party = [(char, None)]

        actions = [{
            "char": char,
            "label": "Thank Yea-ji Kang warmly for her thoughtful guidance",
            "stat": "CHA",
            "check": {"is_success": True, "tier": "success"}
        }]
        outcome = {
            "outcome_narrative": "Yea-ji smiles subtly at the polite gratitude.",
            "next_narrative": "She returns to her paperwork.",
            "relationship_updates": [],
            "npcs_present": [{"name": "Yea-ji Kang", "role": "Student Council President"}]
        }

        apply_outcome(self.session_id, party, outcome, mp_already_spent=False, actions=actions)

        c = db.get_contact(self.session_id, "Yea-ji Kang", self.char_id)
        self.assertIsNotNone(c)
        self.assertGreater(c["relationship_score"], 0)

    def test_genuine_exit_action_is_skipped(self):
        """Verify that genuine exit actions like 'excuse yourself' or 'say goodbye' are skipped."""
        char = db.get_character(self.user_id)
        party = [(char, None)]

        actions = [{
            "char": char,
            "label": "Excuse yourself and leave conversation with Yea-ji Kang",
            "stat": "CHA",
            "check": {"is_success": True, "tier": "success"}
        }]
        outcome = {
            "outcome_narrative": "You step out into the hallway.",
            "next_narrative": "The door clicks shut behind you.",
            "relationship_updates": [],
            "npcs_present": [{"name": "Yea-ji Kang", "role": "Student Council President"}]
        }

        apply_outcome(self.session_id, party, outcome, mp_already_spent=False, actions=actions)

        # No relationship update synthesized
        ru = outcome.get("relationship_updates", [])
        self.assertEqual(len(ru), 0)

    def test_pass_c_narrative_milestone_scanner_without_prior_relationship_updates(self):
        """Verify that Pass C executes cleanly without UnboundLocalError when relationship_updates is empty."""
        char = db.get_character(self.user_id)
        party = [(char, None)]

        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char_id,
            npc_id="Sofia Anderson",
            name="Sofia Anderson",
            appearance={"intercourse_experience": "virgin"}
        )

        actions = [{
            "char": char,
            "label": "Kiss Sofia Anderson passionately under the stars",
            "stat": "CHA",
            "check": {"is_success": True, "tier": "success"}
        }]
        outcome = {
            "outcome_narrative": "Under the pale moonlight, you share a passionate kiss with Sofia Anderson.",
            "next_narrative": "Her eyes linger on yours softly.",
            "relationship_updates": []  # Pass B rel loop does not run
        }

        # This should execute Pass C cleanly and record the kiss milestone memory without error
        apply_outcome(self.session_id, party, outcome, mp_already_spent=False, actions=actions)

        c = db.get_contact(self.session_id, "Sofia Anderson", self.char_id)
        self.assertIsNotNone(c)
        intimate_mems = c.get("intimate_memories") or []
        has_kiss = any("kiss" in m.lower() for m in intimate_mems)
        self.assertTrue(has_kiss)

    def test_pass_c_no_variable_bleed_from_previous_npc(self):
        """Verify that Pass C contacts do not inherit experience or attributes from a different NPC in Pass B."""
        char = db.get_character(self.user_id)
        party = [(char, None)]

        # Pre-seed Maya Anderson as a virgin
        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char_id,
            npc_id="Maya Anderson",
            name="Maya Anderson",
            appearance={"intercourse_experience": "virgin", "oral_experience": "inexperienced"}
        )

        # Pass B runs for Yea-ji Kang with explicit non_virgin intercourse_experience
        # But player's romantic action also addresses Maya Anderson in narrative
        actions = [{
            "char": char,
            "label": "Share a passionate romantic kiss with Maya Anderson",
            "stat": "CHA",
            "check": {"is_success": True, "tier": "success"}
        }]
        outcome = {
            "outcome_narrative": "You share a passionate kiss with Maya Anderson as Yea-ji Kang looks on.",
            "next_narrative": "The atmosphere is electric.",
            "relationship_updates": [{
                "npc_name": "Yea-ji Kang",
                "delta_score": 1,
                "intercourse_experience": "non_virgin",
                "oral_experience": "experienced"
            }]
        }

        apply_outcome(self.session_id, party, outcome, mp_already_spent=False, actions=actions)

        # Maya Anderson must remain a virgin in Pass C (no variable bleed from Yea-ji Kang's loop variables)
        maya = db.get_contact(self.session_id, "Maya Anderson", self.char_id)
        self.assertIsNotNone(maya)
        maya_app = maya.get("appearance", {})
        self.assertEqual(maya_app.get("intercourse_experience"), "virgin")
        self.assertEqual(maya_app.get("oral_experience"), "inexperienced")

    def test_explicit_update_preference_not_modified_twice_in_pass_b(self):
        """Verify that explicit LLM updates do not have preferences applied twice in Pass B."""
        char = db.get_character(self.user_id)
        party = [(char, None)]

        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char_id,
            npc_id="Yea-ji Kang",
            name="Yea-ji Kang",
            new_preferences=["Favors Intellectual & Tactical Depth"],
            appearance={"erotic_openness": "modest"}
        )

        actions = [{
            "char": char,
            "label": "Analyze study notes and strategic records with Yea-ji Kang",
            "stat": "INT",
            "check": {"is_success": True, "tier": "success"}
        }]
        outcome = {
            "outcome_narrative": "Yea-ji Kang analyzes the strategy carefully.",
            "next_narrative": "She nods in agreement.",
            "relationship_updates": [{
                "npc_name": "Yea-ji Kang",
                "delta_score": 2,
                "track": "platonic"
            }]
        }

        apply_outcome(self.session_id, party, outcome, mp_already_spent=False, actions=actions)

        # Base delta = 2. Tactical depth preference adds +2 -> 4. Warm trait (+30%) -> round(4 * 1.3) = 5.
        # If the removed duplicate loop (lines 1500-1514) was still present, it would add another +2 -> 7.
        c = db.get_contact(self.session_id, "Yea-ji Kang", self.char_id)
        self.assertIsNotNone(c)
        self.assertEqual(c["relationship_score"], 5)


if __name__ == "__main__":
    unittest.main()
