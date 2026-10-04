"""
Unit tests for scene contact auto-registration and deterministic relationship fallback.
"""
import json
import unittest
import db
import game_engine
from game_engine import is_dialogue_partner, apply_outcome


class TestRelationshipAndContactFallback(unittest.TestCase):
    def setUp(self):
        self.session_id = 99881
        self.user_id = 88771
        self.char_id = 77661

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
                {"name": "Zihan Moon", "role": "Companion"},
                {"name": "Sofia Anderson", "role": "Club President"},
                {"name": "Yea-ji Kang", "role": "Student Council President"},
                {"name": "Amélie Yamashita", "role": "Student Council Vice President"},
                {"name": "Sophia", "role": "Council Secretary"},
                {"name": "Harold Wójcik", "role": "Council Representative"}
            ]

            conn.execute(
                """INSERT INTO sessions (id, mode, capacity, status, scenario, current_location, current_npcs_json, turn_order, created_at, updated_at)
                   VALUES (?, 'solo', 1, 'active', 'high_school_drama', 'Westlake Academy ➔ Student Council Office ➔ Main Office Area', ?, ?, 0, 0)""",
                (self.session_id, json.dumps(current_npcs), json.dumps([self.user_id]))
            )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE id=? OR user_id=?", (self.char_id, self.user_id))
            conn.execute("DELETE FROM contacts WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM lorebook WHERE session_id=?", (self.session_id,))

    def test_ensure_scene_npcs_in_contacts(self):
        contacts = db.get_contacts(self.session_id, character_id=self.char_id)
        contact_names = {c["name"] for c in contacts}
        self.assertIn("Yea-ji Kang", contact_names)
        self.assertIn("Amélie Yamashita", contact_names)
        self.assertIn("Sofia Anderson", contact_names)
        self.assertIn("Sophia", contact_names)
        self.assertIn("Harold Wójcik", contact_names)

    def test_social_check_fallback_for_yea_ji_kang(self):
        char = db.get_character(self.user_id)
        party = [(char, None)]

        actions = [{
            "char": char,
            "label": "Suggest cultivating a loyal proxy to Yea-ji Kang",
            "stat": "CHA",
            "check": {"is_success": True, "tier": "success"}
        }]
        outcome = {
            "outcome_narrative": "Yea-ji Kang listens with intensifying focus...",
            "next_narrative": "The office remains quiet...",
            "relationship_updates": [],
            "npcs_present": [
                {"name": "Yea-ji Kang", "role": "Student Council President"},
                {"name": "Amélie Yamashita", "role": "Student Council Vice President"}
            ],
            "dialogue_partners": ["Yea-ji Kang"]
        }

        apply_outcome(self.session_id, party, outcome, mp_already_spent=False, actions=actions)

        self.assertTrue(len(outcome.get("relationship_updates", [])) >= 1)
        rel_entry = next((r for r in outcome["relationship_updates"] if r.get("npc_name") == "Yea-ji Kang"), None)
        self.assertIsNotNone(rel_entry)
        self.assertEqual(rel_entry["delta_score"], 3)

        c = db.get_contact(self.session_id, "Yea-ji Kang", character_id=self.char_id)
        self.assertIsNotNone(c)
        self.assertEqual(c["relationship_score"], 3)

    def test_social_check_fallback_for_amelie_diacritics(self):
        char = db.get_character(self.user_id)
        party = [(char, None)]

        actions = [{
            "char": char,
            "label": "Present critique with clinical precision to Amélie Yamashita",
            "stat": "CHA",
            "check": {"is_success": True, "tier": "success"}
        }]
        outcome = {
            "outcome_narrative": "Amélie listens with focused analytical intensity...",
            "next_narrative": "She acknowledges the validity of the risk...",
            "relationship_updates": [],
            "npcs_present": [
                {"name": "Yea-ji Kang", "role": "Student Council President"},
                {"name": "Amélie Yamashita", "role": "Student Council Vice President"}
            ],
            "dialogue_partners": ["Amélie Yamashita"]
        }

        apply_outcome(self.session_id, party, outcome, mp_already_spent=False, actions=actions)

        rel_entry = next((r for r in outcome["relationship_updates"] if is_dialogue_partner(r.get("npc_name"), ["Amélie Yamashita"])), None)
        self.assertIsNotNone(rel_entry)
        self.assertEqual(rel_entry["delta_score"], 3)

        c = db.get_contact(self.session_id, "Amélie Yamashita", character_id=self.char_id)
        self.assertIsNotNone(c)
        self.assertEqual(c["relationship_score"], 3)

    def test_explicit_llm_update_not_overwritten(self):
        char = db.get_character(self.user_id)
        party = [(char, None)]

        actions = [{
            "char": char,
            "label": "Debate strategy with Yea-ji Kang",
            "stat": "CHA",
            "check": {"is_success": True, "tier": "success"}
        }]
        outcome = {
            "outcome_narrative": "...",
            "relationship_updates": [
                {"npc_name": "Yea-ji Kang", "delta_score": 6, "new_traits": ["Ambitious"]}
            ],
            "dialogue_partners": ["Yea-ji Kang"]
        }

        apply_outcome(self.session_id, party, outcome, mp_already_spent=False, actions=actions)

        self.assertEqual(len(outcome["relationship_updates"]), 1)
        self.assertEqual(outcome["relationship_updates"][0]["delta_score"], 6)

        c = db.get_contact(self.session_id, "Yea-ji Kang", character_id=self.char_id)
        self.assertEqual(c["relationship_score"], 6)
        self.assertIn("Ambitious", c["unlocked_traits"])

    def test_fantasy_generic_patron_safeguard(self):
        # Create a fantasy tavern session with named NPCs + generic ambient crowd
        fantasy_sess_id = 99882
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (fantasy_sess_id,))
            conn.execute("DELETE FROM contacts WHERE session_id=?", (fantasy_sess_id,))
            tavern_npcs = [
                {"name": "Mara Vey", "role": "Mercenary Leader"},
                {"name": "Eldrin", "role": "Archivist"},
                {"name": "Drunken Patron", "role": "Patron"},
                {"name": "Town Guard", "role": "Guard"},
                {"name": "Bystander", "role": "Commoner"}
            ]
            conn.execute(
                """INSERT INTO sessions (id, mode, capacity, status, scenario, current_location, current_npcs_json, turn_order, created_at, updated_at)
                   VALUES (?, 'solo', 1, 'active', 'fantasy', 'Oakhaven ➔ Boar Tusk Tavern ➔ Common Room', ?, ?, 0, 0)""",
                (fantasy_sess_id, json.dumps(tavern_npcs), json.dumps([self.user_id]))
            )

        # 1. Inspect contacts without speaking to anyone:
        # Named NPCs (Mara Vey, Eldrin) SHOULD be in contacts.
        # Generic ambient crowd (Drunken Patron, Town Guard, Bystander) MUST NOT be in contacts.
        contacts = db.get_contacts(fantasy_sess_id, character_id=self.char_id)
        contact_names = {c["name"] for c in contacts}
        self.assertIn("Mara Vey", contact_names)
        self.assertIn("Eldrin", contact_names)
        self.assertNotIn("Drunken Patron", contact_names)
        self.assertNotIn("Town Guard", contact_names)
        self.assertNotIn("Bystander", contact_names)

        # Clean up
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (fantasy_sess_id,))
            conn.execute("DELETE FROM contacts WHERE session_id=?", (fantasy_sess_id,))


if __name__ == "__main__":
    unittest.main()
