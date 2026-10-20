import unittest
import json
import sqlite3
import db
from mechanics.social.persona import (
    is_romantic_milestone_str,
    generate_past_intimate_history,
)
from mechanics.social.genealogy import build_topic_aware_npc_context

class TestMemorySeparationAndMultiAct(unittest.TestCase):
    def setUp(self):
        db.init_db()

    def test_is_romantic_milestone_str(self):
        # Romantic milestones -> True
        self.assertTrue(is_romantic_milestone_str("Shared a passionate first kiss with Artemiusz"))
        self.assertTrue(is_romantic_milestone_str("Confessed feelings and agreed to date Artemiusz"))
        self.assertTrue(is_romantic_milestone_str("Shared intimate night with Artemiusz"))
        self.assertTrue(is_romantic_milestone_str("Provided oral intimacy to Artemiusz"))
        self.assertTrue(is_romantic_milestone_str("Received oral intimacy from Artemiusz"))
        self.assertTrue(is_romantic_milestone_str("Shared a tender, affectionate moment with Artemiusz"))
        self.assertTrue(is_romantic_milestone_str("[Romance] Shared a quiet walk at sunset"))
        self.assertTrue(is_romantic_milestone_str("Romantic milestone shared with Artemiusz"))

        # General non-romantic interactions -> False
        self.assertFalse(is_romantic_milestone_str("Inspected the dormitory room with Harry"))
        self.assertFalse(is_romantic_milestone_str("Agreed to an alliance against the rival faction"))
        self.assertFalse(is_romantic_milestone_str("Discussed strategy for the upcoming tournament"))
        self.assertFalse(is_romantic_milestone_str("Traded 50 gold for a library key"))
        self.assertFalse(is_romantic_milestone_str("Studied together for the midterm exams"))

    def test_multi_act_past_intimate_history(self):
        # Dual-experienced character (both intercourse and oral)
        res = generate_past_intimate_history(
            intercourse="non_virgin",
            oral="has_done_oral",
            hash_val=105,
            gender="female",
            scenario="high_school_drama",
            openness="moderate"
        )
        self.assertIsNotNone(res)
        entry = res["entry"]
        self.assertIn("Past History:", entry)
        self.assertIn("intercourse", entry.lower())
        self.assertIn("oral", entry.lower())

    def test_multi_act_affair_past_history(self):
        # Shameless character with affair probability
        res = generate_past_intimate_history(
            intercourse="non_virgin",
            oral="has_done_oral",
            hash_val=999,
            gender="female",
            scenario="high_school_drama",
            openness="shameless",
            has_existing_partner=True
        )
        self.assertIsNotNone(res)
        entries = res["entries"]
        # Should have multiple partners and at least one affair mentioning specific acts
        affair_entries = [e for e in entries if "Secret affair" in e]
        if affair_entries:
            self.assertTrue(any("intercourse" in e or "oral" in e for e in affair_entries))

    def test_contact_memory_separation_and_auto_migration(self):
        sess_id = 999123
        char_id = 101
        with db.get_conn() as conn:
            db.core._delete_session_records(conn, sess_id)

        # 1. Upsert contact with non-romantic memory
        c1 = db.upsert_contact(
            session_id=sess_id,
            character_id=char_id,
            npc_id="Aoi Todo",
            name="Aoi Todo",
            new_general_memory="Discussed jujutsu tournament tactics"
        )
        self.assertIn("Discussed jujutsu tournament tactics", c1.get("recent_memories", []))
        self.assertNotIn("Discussed jujutsu tournament tactics", c1.get("intimate_memories", []))

        # 2. Upsert contact with romantic memory
        c2 = db.upsert_contact(
            session_id=sess_id,
            character_id=char_id,
            npc_id="Aoi Todo",
            name="Aoi Todo",
            new_memory="Shared a passionate first kiss under the cherry blossoms"
        )
        self.assertIn("Shared a passionate first kiss under the cherry blossoms", c2.get("intimate_memories", []))
        self.assertIn("Discussed jujutsu tournament tactics", c2.get("recent_memories", []))

        # 3. Verify get_contacts returns clean partitioning
        contacts = db.get_contacts(sess_id, char_id)
        found = next((c for c in contacts if c["name"] == "Aoi Todo"), None)
        self.assertIsNotNone(found)
        self.assertEqual(len(found.get("shared_romantic_milestones", [])), 1)
        self.assertEqual(found["shared_romantic_milestones"][0], "Shared a passionate first kiss under the cherry blossoms")
        self.assertIn("Discussed jujutsu tournament tactics", found.get("recent_memories", []))

    def test_prompt_injection_budget_cap(self):
        # Contact with 10 general memories and 10 romantic memories
        contact = {
            "name": "Kiyomi",
            "track": "romantic",
            "intimate_memories": [f"Romantic memory {i} with kiss" for i in range(10)],
            "recent_memories": [f"General interaction {i}" for i in range(10)]
        }
        prompt = build_topic_aware_npc_context(contact)
        # Verify prompt exists and recent memories are capped at 5
        self.assertIn("[RECENT SHARED INTERACTIONS & MEMORIES - Kiyomi]", prompt)
        self.assertIn("General interaction 9", prompt)
        self.assertNotIn("General interaction 0", prompt)
        # Romantic milestones also capped at 5
        self.assertIn("[ESTABLISHED SHARED MEMORIES WITH PLAYER - Kiyomi]", prompt)
        self.assertIn("Romantic memory 9 with kiss", prompt)
        self.assertNotIn("Romantic memory 0 with kiss", prompt)

if __name__ == "__main__":
    unittest.main()
