import unittest
import json
import db
import game_engine


class TestProseEntitySync(unittest.TestCase):
    def setUp(self):
        self.session_id = 99899
        self.user_id = 99899
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM factions WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))

        db.create_character(self.user_id, "Artemiusz", char_class="Student", stats={"STR": 5, "PER": 7, "END": 5, "CHA": 8, "INT": 9, "AGI": 6, "LUK": 5})

        # Create session at Student Council Office
        with db.get_conn() as conn:
            conn.execute("""
                INSERT INTO sessions (id, channel_id, host_user_id, status, mode, capacity, scenario, current_location, turn_order, current_npcs_json)
                VALUES (?, 100, ?, 'active', 'solo', 1, 'high_school_drama', 'Westlake Academy ➔ Student Council Office ➔ Main Office Area', ?, ?)
            """, (self.session_id, self.user_id, json.dumps([self.user_id]), json.dumps([{"name": "Zihan Moon", "hp": 100, "max_hp": 100}])))

        # Create Velvet Rose Pact faction with leadership roster in DB
        roster = [
            {"rank": 4, "title": "Club President", "name": "Sofia Anderson", "is_player": False},
            {"rank": 3, "title": "Vice President", "name": "Manon Sokolov", "is_player": False},
            {"rank": 2, "title": "Club Secretary", "name": "So-hee Mendoza", "is_player": False},
            {"rank": 1, "title": "Club Treasurer", "name": "Mila Kuznetsov", "is_player": False}
        ]
        db.upsert_faction(
            session_id=self.session_id,
            name="Velvet Rose Pact",
            delta_score=0,
            hierarchy_template="club",
            leadership_roster=roster,
            hq_location_id="Student Council Office"
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM factions WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))

    def test_prose_scanner_recovers_omitted_faction_members(self):
        """Verify that when prose mentions Mila, So-hee, and Manon but JSON only has Sofia, all 4 are recovered."""
        session = db.get_session(self.session_id)
        loc = "Westlake Academy ➔ Student Council Office ➔ Main Office Area"

        # Simulated LLM output where JSON npcs_present dropped Mila, So-hee, and Manon
        raw_llm_result = {
            "scene_title": "The Seat of Authority",
            "outcome_narrative": "Artemiusz steps forward and presents the incident report to the council.",
            "next_narrative": "Behind the massive mahogany desk sits Sofia Anderson. Beside her, the other council members—Mila, So-hee, and Manon—watch with varying degrees of curiosity.",
            "npcs_present": [{"name": "Sofia Anderson"}]
        }

        final_npcs = game_engine.process_scene_npcs(raw_llm_result, session, loc, loc)
        npc_names = [n.get("name") if isinstance(n, dict) else n for n in final_npcs]

        # All 4 council members and traveling companion Zihan Moon must be present
        self.assertIn("Zihan Moon", npc_names)
        self.assertIn("Sofia Anderson", npc_names)
        self.assertIn("Manon Sokolov", npc_names)
        self.assertIn("So-hee Mendoza", npc_names)
        self.assertIn("Mila Kuznetsov", npc_names)

    def test_entity_audit_parsing(self):
        """Verify that characters listed in entity_audit are automatically parsed and included."""
        session = db.get_session(self.session_id)
        loc = "Westlake Academy ➔ Student Council Office ➔ Main Office Area"

        raw_llm_result = {
            "scene_title": "Meeting",
            "entity_audit": {
                "present_named_characters": ["Sofia Anderson", "Yea-ji Kang"],
                "speaking_characters": ["Sofia Anderson"]
            },
            "outcome_narrative": "Discussions begin.",
            "next_narrative": "The council reviews the papers.",
            "npcs_present": []
        }

        final_npcs = game_engine.process_scene_npcs(raw_llm_result, session, loc, loc)
        npc_names = [n.get("name") if isinstance(n, dict) else n for n in final_npcs]

        self.assertIn("Sofia Anderson", npc_names)
        self.assertIn("Yea-ji Kang", npc_names)

    def test_remote_contacts_in_other_zones_not_added_from_prose(self):
        """Verify that mentioning someone far away in another zone does NOT summon them into the room."""
        session = db.get_session(self.session_id)
        loc = "Westlake Academy ➔ Student Council Office ➔ Main Office Area"

        # Create a contact in a different zone (e.g. Downtown)
        db.upsert_contact(
            self.session_id, character_id=0, npc_id="downtown_detective",
            name="Detective Vance", basic_info={"location": "Downtown District ➔ Police Station"}
        )

        raw_llm_result = {
            "scene_title": "Memories",
            "outcome_narrative": "Artemiusz recalled what Detective Vance told him earlier in the downtown district.",
            "next_narrative": "Sofia waits for your answer.",
            "npcs_present": [{"name": "Sofia Anderson"}]
        }

        final_npcs = game_engine.process_scene_npcs(raw_llm_result, session, loc, loc)
        npc_names = [n.get("name") if isinstance(n, dict) else n for n in final_npcs]

        self.assertIn("Sofia Anderson", npc_names)
        self.assertNotIn("Detective Vance", npc_names)

    def test_player_character_excluded_from_npcs_present(self):
        """Verify that the player character (Artemiusz) is NEVER placed into npcs_present even if in entity_audit."""
        session = db.get_session(self.session_id)
        loc = "Westlake Academy ➔ Student Council Office ➔ Main Office Area"

        raw_llm_result = {
            "scene_title": "Assembly",
            "entity_audit": {
                "present_named_characters": ["Artemiusz", "Sofia Anderson", "Zihan Moon"],
                "speaking_characters": ["Sofia Anderson"]
            },
            "outcome_narrative": "Artemiusz speaks.",
            "next_narrative": "Sofia answers Artemiusz.",
            "npcs_present": [{"name": "Artemiusz"}, {"name": "Sofia Anderson"}]
        }

        final_npcs = game_engine.process_scene_npcs(raw_llm_result, session, loc, loc)
        npc_names = [n.get("name") if isinstance(n, dict) else n for n in final_npcs]

        # Player character Artemiusz MUST NOT be in npcs_present
        self.assertNotIn("Artemiusz", npc_names)
        self.assertIn("Sofia Anderson", npc_names)


if __name__ == "__main__":
    unittest.main()
