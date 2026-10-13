import unittest
import db
import game_engine


class TestNpcDispositionDiversity(unittest.TestCase):
    def setUp(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id IN (99050, 99051)")
            conn.execute("DELETE FROM sessions WHERE turn_order LIKE '%99050%' OR turn_order LIKE '%99051%'")

    def test_friendly_npc_auto_added_to_contacts(self):
        """When a new entity is emitted, it is added to the World Codex (lorebook), while contacts require Friend tier (affinity >= 100) or party recruitment."""
        uid = 99050
        char = db.create_character(uid, "DispTester", "Mage", "fantasy")
        sess_id = db.create_session(uid, "solo", 1, "vivid", "individual", False, scenario="fantasy")
        session = db.get_session(sess_id)
        party = [(char, db.get_inventory(uid))]

        outcome = {
            "scene_title": "Tavern Entrance",
            "narrative": "A warm tavern.",
            "location": "Solaria ➔ The Boar's Tusk Tavern ➔ Hearth",
            "new_entities": [
                {
                    "type": "person",
                    "name": "Elowen Greenbrier",
                    "race": "elf",
                    "gender": "female",
                    "appearance": {"eye_color": "green", "hair_color": "silver"},
                    "description": "A warm, helpful guide",
                    "disposition": "friendly",
                    "traits": ["Helpful", "Cheerful"]
                }
            ],
            "npcs_present": [{"name": "Elowen Greenbrier"}],
            "next_choices": []
        }

        game_engine.apply_outcome(sess_id, party, outcome)

        # Verify added to lorebook (World Codex)
        lore = next((p for p in db.get_lorebook(sess_id).get("person", []) if p["name"] == "Elowen Greenbrier"), None)
        self.assertIsNotNone(lore)

        # Contacts are strictly gated behind Friend tier (>= 100) or party recruitment
        contact = db.get_contact(sess_id, "Elowen Greenbrier", char["id"])
        self.assertIsNone(contact)

        # Once reaching Friend tier (affinity >= 100), NPC enters contacts
        db.upsert_contact(sess_id, "Elowen Greenbrier", "Elowen Greenbrier", character_id=char["id"], delta_score=100)
        c_friend = db.get_contact(sess_id, "Elowen Greenbrier", char["id"])
        self.assertIsNotNone(c_friend)
        self.assertEqual(c_friend["name"], "Elowen Greenbrier")

    def test_relationship_update_promotes_neutral_npc_to_friendly(self):
        """Neutral NPCs preserve non-hostile stance and only graduate to contacts upon reaching Friend tier (>= 100)."""
        uid = 99051
        char = db.create_character(uid, "DispTester2", "Mage", "fantasy")
        sess_id = db.create_session(uid, "solo", 1, "vivid", "individual", False, scenario="fantasy")
        party = [(char, db.get_inventory(uid))]

        # Turn 1: Meet neutral NPC
        outcome_1 = {
            "scene_title": "Tavern Bar",
            "narrative": "A quiet bar.",
            "location": "Solaria ➔ The Boar's Tusk Tavern ➔ Bar Counter",
            "new_entities": [
                {
                    "type": "person",
                    "name": "Boran Stout",
                    "race": "dwarf",
                    "gender": "male",
                    "appearance": {"eye_color": "brown", "hair_color": "black"},
                    "description": "A stoic tavern keeper",
                    "disposition": "neutral",
                    "traits": ["Stoic"]
                }
            ],
            "npcs_present": [{"name": "Boran Stout"}],
            "next_choices": []
        }
        game_engine.apply_outcome(sess_id, party, outcome_1)

        lore_1 = next((p for p in db.get_lorebook(sess_id).get("person", []) if p["name"] == "Boran Stout"), None)
        self.assertIsNotNone(lore_1)
        self.assertEqual(lore_1["disposition"], "neutral")

        # Turn 2: Player has positive conversation (+5 relationship score, still Stranger tier)
        outcome_2 = {
            "scene_title": "Sharing Ale",
            "narrative": "Boran smiles and shares an old recipe.",
            "location": "Solaria ➔ The Boar's Tusk Tavern ➔ Bar Counter",
            "npcs_present": [{"name": "Boran Stout"}],
            "relationship_updates": [
                {
                    "npc_name": "Boran Stout",
                    "delta_score": 5,
                    "new_traits": ["Generous"]
                }
            ],
            "next_choices": []
        }
        game_engine.apply_outcome(sess_id, party, outcome_2)

        # Disposition remains neutral (non-hostile)
        lore_2 = next((p for p in db.get_lorebook(sess_id).get("person", []) if p["name"] == "Boran Stout"), None)
        self.assertIsNotNone(lore_2)
        self.assertEqual(lore_2["disposition"], "neutral")

        # Turn 3: Reach Friend tier (>= 100), promoting to contacts
        db.upsert_contact(sess_id, "Boran Stout", "Boran Stout", character_id=char["id"], delta_score=100)
        contact = db.get_contact(sess_id, "Boran Stout", char["id"])
        self.assertIsNotNone(contact)
        self.assertGreaterEqual(contact["relationship_score"], 100)


if __name__ == "__main__":
    unittest.main()
