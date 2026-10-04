import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
import game_engine
import mechanics.world.locations as locs
import mechanics.world.mobility as mobility


class TestCrossZoneDateAndMeetupGuardrails(unittest.TestCase):

    def setUp(self):
        self.test_session_id = 998877
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (self.test_session_id,))
            conn.commit()

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (self.test_session_id,))
            conn.commit()

    def test_legitimate_cross_zone_date_tracking(self):
        """Verify that an agreed coffee date across town (Westlake Academy -> Komorebi Commercial Strip) is tracked."""
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO contacts (session_id, character_id, npc_id, name, relationship_score, basic_info_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (self.test_session_id, 0, "maya_anderson", "Maya Anderson", 15,
                 json.dumps({"location": "Westlake Academy", "role": "Student", "club": "Student Council"}), 1000)
            )
            conn.commit()

        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Komorebi Commercial Strip ✖ Café Monolith ✖ Corner Table",
            "current_npcs": [],
            "dialogue_partners": ["Maya Anderson"],
            "dialogue_partner": "Maya Anderson",
            "history": [
                "[Success] Artemiusz: Suggest to her to hangout at a café in the town after school -> Maya agrees with a smile.",
                "[Success] Artemiusz: I travel to Komorebi Commercial Strip ✖ Café Monolith. -> Artemiusz takes a corner table."
            ]
        }

        raw_result = {
            "title": "The Quiet Pulse of Monolith",
            "outcome_narrative": "Artemiusz scans the cafe. Maya arrives and takes a seat across from him.",
            "next_narrative": "Maya shifts her weight, leaning slightly toward Artemiusz with a warm smile. \"You're quite thorough,\" she remarks.",
            "npcs_present": [{"name": "Maya Anderson"}]
        }
        new_loc = "Komorebi Commercial Strip ✖p Café Monolith ✖ Corner Table"
        old_loc = "Komorebi Commercial Strip ✖ Café Monolith ✖p Corner Table"

        final_npcs = game_engine.process_scene_npcs(raw_result, session, new_loc, old_loc, actions=[])
        npc_names = [n["name"] if isinstance(n, dict) else n for n in final_npcs]

        self.assertIn("Maya Anderson", npc_names)

        contact = db.get_contact(self.test_session_id, "maya_anderson")
        self.assertIsNotNone(contact)
        self.assertEqual(contact["basic_info"]["location"], new_loc)

    def test_false_positive_passive_rumor_pruned(self):
        """Verify that an off-zone contact mentioned exclusively inside dialogue quotes is strictly pruned."""
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO contacts (session_id, character_id, npc_id, name, relationship_score, basic_info_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (self.test_session_id, 0, "maya_anderson", "Maya Anderson", 15,
                 json.dumps({"location": "Westlake Academy", "role": "Student"}), 1000)
            )
            conn.commit()

        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Komorebi Commercial Strip ✖ Café Monolith ✖p Counter",
            "current_npcs": [{"name": "Barista Dave", "role": "Barista"}],
            "dialogue_partners": ["Barista Dave"],
            "history": []
        }

        raw_result = {
            "title": "Coffee Counter Gossip",
            "outcome_narrative": "Artemiusz steps up to the counter.",
            "next_narrative": "The barista chuckles. \"Maya Anderson always orders the iced latte whenever she visits this place.\"",
            "npcs_present": [{"name": "Barista Dave"}, {"name": "Maya Anderson"}]
        }
        loc = "Komorebi Commercial Strip ✖p Café Monolith ✖ Counter"

        final_npcs = game_engine.process_scene_npcs(raw_result, session, loc, loc, actions=[])
        npc_names = [n["name"] if isinstance(n, dict) else n for n in final_npcs]

        self.assertIn("Barista Dave", npc_names)
        self.assertNotIn("Maya Anderson", npc_names)

    def test_false_positive_memory_or_thought_pruned(self):
        """Verify that an off-zone contact mentioned only in thoughts/memories is strictly pruned."""
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO contacts (session_id, character_id, npc_id, name, relationship_score, basic_info_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (self.test_session_id, 0, "maya_anderson", "Maya Anderson", 15,
                 json.dumps({"location": "Westlake Academy", "role": "Student"}), 1000)
            )
            conn.commit()

        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Komorebi Commercial Strip ✖ Café Monolith ✖ Corner Table",
            "current_npcs": [],
            "dialogue_partners": [],
            "history": []
        }

        raw_result = {
            "title": "Quiet Contemplation",
            "outcome_narrative": "Artemiusz takes a slow sip of the black coffee.",
            "next_narrative": "The bitter taste fills his senses, reminding him of Maya Anderson and her strict rules regarding focus.",
            "npcs_present": [{"name": "Maya Anderson"}]
        }
        loc = "Komorebi Commercial Strip ✖p Café Monolith ✖ Corner Table"

        final_npcs = game_engine.process_scene_npcs(raw_result, session, loc, loc, actions=[])
        npc_names = [n["name"] if isinstance(n, dict) else n for n in final_npcs]

        self.assertNotIn("Maya Anderson", npc_names)

    def test_false_positive_unprompted_hallucination_pruned(self):
        """Verify that an off-zone NPC with no continuity bridge (no prior dialogue, no appointment) is pruned from random scenes."""
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO contacts (session_id, character_id, npc_id, name, relationship_score, basic_info_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (self.test_session_id, 0, "maya_anderson", "Maya Anderson", 15,
                 json.dumps({"location": "Westlake Academy", "role": "Student"}), 1000)
            )
            conn.commit()

        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Port District ✖ Abandoned Warehouse ✖ Storage Bay",
            "current_location": "Port District ✖ Abandoned Warehouse ✖ Storage Bay",
            "current_npcs": [],
            "dialogue_partners": [],
            "history": [
                "[Success] Artemiusz: Inspect the cargo containers -> The warehouse is dark and silent."
            ]
        }

        raw_result = {
            "title": "Shadows in the Bay",
            "outcome_narrative": "Artemiusz creeps between the rusted containers.",
            "next_narrative": "Suddenly, Maya Anderson steps out from the shadows and smiles.",
            "npcs_present": [{"name": "Maya Anderson"}]
        }
        loc = "Port District ✖ Abandoned Warehouse ✖ Storage Bay"

        final_npcs = game_engine.process_scene_npcs(raw_result, session, loc, loc, actions=[])
        npc_names = [n["name"] if isinstance(n, dict) else n for n in final_npcs]

        self.assertNotIn("Maya Anderson", npc_names)

    def test_stationary_fixture_lockdown(self):
        """Verify that a stationary fixture (e.g. School Nurse or Librarian) is never carried across town."""
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO contacts (session_id, character_id, npc_id, name, relationship_score, basic_info_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (self.test_session_id, 0, "nurse_rebecca", "Nurse Rebecca", 15,
                 json.dumps({"location": "Westlake Academy ✖p Infirmary", "role": "School Nurse"}), 1000)
            )
            conn.commit()

        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Komorebi Commercial Strip ✖ Café Monolith ✖p Corner Table",
            "current_location": "Komorebi Commercial Strip ✖ Café Monolith ✖ Corner Table",
            "current_npcs": [],
            "dialogue_partners": ["Nurse Rebecca"],
            "history": []
        }

        raw_result = {
            "title": "Afternoon Coffee",
            "outcome_narrative": "Artemiusz arrives at the cafe.",
            "next_narrative": "Nurse Rebecca sits down at the table and smiles.",
            "npcs_present": [{"name": "Nurse Rebecca"}]
        }
        loc = "Komorebi Commercial Strip ✖p Café Monolith ✖ Corner Table"

        final_npcs = game_engine.process_scene_npcs(raw_result, session, loc, loc, actions=[])
        npc_names = [n["name"] if isinstance(n, dict) else n for n in final_npcs]

        self.assertNotIn("Nurse Rebecca", npc_names)


if __name__ == '__main__':
    unittest.main()
