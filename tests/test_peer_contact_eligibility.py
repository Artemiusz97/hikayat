"""
Unit tests for Peer Contact Eligibility & High School / Non-Combat Disposition Decoupling.
Verifies that:
1. Fellow students and contemporaries (classmates, council leaders, club members, delinquents)
   are eligible for Contacts registration and Affinity progression.
2. Adults, faculty (teachers, principals), parents, and service workers (clerks, janitors)
   are strictly excluded from Contacts registration and Affinity progression.
3. Social checks performed on teachers/clerks/parents never add affinity or contact rows.
4. Fantasy scenarios remain unaffected.
"""
import json
import unittest
import db
import game_engine
from game_engine import apply_outcome
import mechanics.social.relationships as relationships


class TestPeerContactEligibility(unittest.TestCase):
    def setUp(self):
        self.session_id = 99883
        self.user_id = 88773
        self.char_id = 77663

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

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE id=? OR user_id=?", (self.char_id, self.user_id))
            conn.execute("DELETE FROM contacts WHERE session_id=?", (self.session_id,))
            conn.execute("DELETE FROM lorebook WHERE session_id=?", (self.session_id,))

    def test_classifier_peer_vs_non_peer(self):
        # Peers
        self.assertTrue(relationships.is_contact_eligible("Yea-ji Kang", role="Student Council President", scenario="high_school_drama"))
        self.assertTrue(relationships.is_contact_eligible("Amélie Yamashita", role="Student Council Vice President", scenario="high_school_drama"))
        self.assertTrue(relationships.is_contact_eligible("Sofia Anderson", role="Club President", scenario="high_school_drama"))
        self.assertTrue(relationships.is_contact_eligible("Zihan Moon", role="Classmate", scenario="high_school_drama"))
        self.assertTrue(relationships.is_contact_eligible("Marcus", role="Delinquent", scenario="high_school_drama"))
        self.assertTrue(relationships.is_contact_eligible("Ken", role="Transfer Student", scenario="high_school_drama"))
        self.assertTrue(relationships.is_contact_eligible("Sophia", role="Council Secretary", scenario="high_school_drama"))

        # Novel / Quirky Student Archetypes (Defaults to True)
        self.assertTrue(relationships.is_contact_eligible("Kaito", role="Goth Otaku", scenario="high_school_drama"))
        self.assertTrue(relationships.is_contact_eligible("Rin", role="Chess Prodigy", scenario="high_school_drama"))
        self.assertTrue(relationships.is_contact_eligible("Hikari", role="Campus Streamer", scenario="high_school_drama"))
        self.assertTrue(relationships.is_contact_eligible("Daiki", role="Track Star", scenario="high_school_drama"))
        self.assertTrue(relationships.is_contact_eligible("Serena", role="School Idol", scenario="high_school_drama"))
        self.assertTrue(relationships.is_contact_eligible("Yuki", role="Quiet Bookworm", description="Second-year student who frequents the library", scenario="high_school_drama"))

        # Non-peers: Faculty & Staff
        self.assertFalse(relationships.is_contact_eligible("Mr. Harrison", role="Biology Teacher", scenario="high_school_drama"))
        self.assertFalse(relationships.is_contact_eligible("Principal Vance", role="School Principal", scenario="high_school_drama"))
        self.assertFalse(relationships.is_contact_eligible("Nurse Davis", role="School Nurse", scenario="high_school_drama"))
        self.assertFalse(relationships.is_contact_eligible("Coach Miller", role="Track Coach", scenario="high_school_drama"))
        self.assertFalse(relationships.is_contact_eligible("Joe", role="Janitor", scenario="high_school_drama"))

        # Novel Adult / Authority / Service Non-Peers
        self.assertFalse(relationships.is_contact_eligible("Dr. Vance", role="Visiting Inspector", scenario="high_school_drama"))
        self.assertFalse(relationships.is_contact_eligible("Mr. Hayes", role="School Board Trustee", scenario="high_school_drama"))
        self.assertFalse(relationships.is_contact_eligible("Gladys", role="Cafeteria Lunch Lady", scenario="high_school_drama"))
        self.assertFalse(relationships.is_contact_eligible("Mrs. Gable", role="Boarding House Landlady", scenario="high_school_drama"))
        self.assertFalse(relationships.is_contact_eligible("Marcus", role="Night Caretaker", scenario="high_school_drama"))

        # Non-peers: Parents & Service Workers
        self.assertFalse(relationships.is_contact_eligible("Elena", role="Mother", scenario="high_school_drama"))
        self.assertFalse(relationships.is_contact_eligible("Robert", role="Father", scenario="high_school_drama"))
        self.assertFalse(relationships.is_contact_eligible("Dave", role="Convenience Store Clerk", scenario="high_school_drama"))
        self.assertFalse(relationships.is_contact_eligible("Officer Jones", role="Police Officer", scenario="high_school_drama"))

    def test_ensure_scene_npcs_filters_non_peers(self):
        scene_npcs = [
            {"name": "Yea-ji Kang", "role": "Student Council President"},
            {"name": "Zihan Moon", "role": "Classmate"},
            {"name": "Mr. Harrison", "role": "Biology Teacher"},
            {"name": "Principal Vance", "role": "Principal"},
            {"name": "Dave", "role": "Store Clerk"},
        ]

        with db.get_conn() as conn:
            conn.execute(
                """INSERT INTO sessions (id, mode, capacity, status, scenario, current_location, current_npcs_json, turn_order, created_at, updated_at)
                   VALUES (?, 'solo', 1, 'active', 'high_school_drama', 'Westlake Academy ➔ Main Hall', ?, ?, 0, 0)""",
                (self.session_id, json.dumps(scene_npcs), json.dumps([self.user_id]))
            )

        contacts = db.get_contacts(self.session_id, character_id=self.char_id)
        contact_names = {c["name"] for c in contacts}

        # Students MUST be in contacts
        self.assertIn("Yea-ji Kang", contact_names)
        self.assertIn("Zihan Moon", contact_names)

        # Non-peers MUST NOT be in contacts
        self.assertNotIn("Mr. Harrison", contact_names)
        self.assertNotIn("Principal Vance", contact_names)
        self.assertNotIn("Dave", contact_names)

    def test_social_check_on_teacher_never_adds_affinity_or_contact(self):
        scene_npcs = [
            {"name": "Mr. Harrison", "role": "Biology Teacher"},
            {"name": "Yea-ji Kang", "role": "Student Council President"}
        ]

        with db.get_conn() as conn:
            conn.execute(
                """INSERT INTO sessions (id, mode, capacity, status, scenario, current_location, current_npcs_json, turn_order, created_at, updated_at)
                   VALUES (?, 'solo', 1, 'active', 'high_school_drama', 'Westlake Academy ➔ Biology Lab', ?, ?, 0, 0)""",
                (self.session_id, json.dumps(scene_npcs), json.dumps([self.user_id]))
            )

        char = db.get_character(self.user_id)
        party = [(char, None)]

        # Action targeting the teacher
        actions = [{
            "char": char,
            "label": "Persuade Mr. Harrison to grant an extension on the project",
            "stat": "CHA",
            "check": {"is_success": True, "tier": "success"}
        }]

        outcome = {
            "outcome_narrative": "Mr. Harrison adjusts his glasses and sighs...",
            "next_narrative": "He writes a revised deadline on the chalkboard.",
            "relationship_updates": [
                {"npc_name": "Mr. Harrison", "delta_score": 5}  # LLM mistakenly emitted teacher update
            ],
            "npcs_present": scene_npcs,
            "dialogue_partners": ["Mr. Harrison"]
        }

        apply_outcome(self.session_id, party, outcome, mp_already_spent=False, actions=actions)

        # 1. outcome["relationship_updates"] must have stripped Mr. Harrison
        self.assertEqual(len(outcome.get("relationship_updates", [])), 0)

        # 2. Database contacts must NOT contain Mr. Harrison
        contacts = db.get_contacts(self.session_id, character_id=self.char_id)
        contact_names = {c["name"] for c in contacts}
        self.assertNotIn("Mr. Harrison", contact_names)
        self.assertIn("Yea-ji Kang", contact_names)

    def test_fantasy_characters_not_blocked(self):
        fantasy_npcs = [
            {"name": "Mara Vey", "role": "Mercenary Leader"},
            {"name": "Eldrin", "role": "Archivist"},
            {"name": "Garrick", "role": "Innkeeper"}
        ]
        with db.get_conn() as conn:
            conn.execute(
                """INSERT INTO sessions (id, mode, capacity, status, scenario, current_location, current_npcs_json, turn_order, created_at, updated_at)
                   VALUES (?, 'solo', 1, 'active', 'fantasy', 'Oakhaven ➔ Inn', ?, ?, 0, 0)""",
                (self.session_id, json.dumps(fantasy_npcs), json.dumps([self.user_id]))
            )

        contacts = db.get_contacts(self.session_id, character_id=self.char_id)
        contact_names = {c["name"] for c in contacts}
        self.assertIn("Mara Vey", contact_names)
        self.assertIn("Eldrin", contact_names)


if __name__ == "__main__":
    unittest.main()
