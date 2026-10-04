import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
import game_engine
import mechanics.world.locations as locs
import mechanics.world.mobility as mobility


class TestSmartCampusMobilityAndArrivalTracking(unittest.TestCase):

    def setUp(self):
        self.test_session_id = 991122
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

    @patch("game_engine.call_llm_json")
    def test_immediate_npc_tracking_on_arrival_at_meetup(self, mock_llm):
        """Verify that traveling across campus to meet Sofia Anderson immediately tracks her in npcs_present & dialogue_partner."""
        import asyncio

        # Initial location: Faculty Wing (Westlake Academy)
        # Sofia's recorded home in contacts: School Rooftop (Westlake Academy)
        import json
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO contacts (session_id, character_id, npc_id, name, relationship_score, basic_info_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (self.test_session_id, 0, "sofia_anderson", "Sofia Anderson", 10,
                 json.dumps({"location": "Westlake Academy ➔ School Rooftop ➔ Rooftop Benches", "role": "Club President"}), 1000)
            )
            conn.commit()

        locs.process_llm_location_update(self.test_session_id, "Westlake Academy ➔ Faculty Wing ➔ Staff Room", scenario_key="high_school_drama")
        locs.process_llm_location_update(self.test_session_id, "School Grounds & Athletics ➔ Gym & Fieldhouse ➔ Main Court Area", scenario_key="high_school_drama")

        mock_llm.return_value = {
            "title": "The Echoes of the Arena",
            "outcome_narrative": "Artemiusz departs the administrative wing and arrives at the gym where Sofia Anderson is waiting.",
            "next_narrative": "\"You're actually on time,\" Sofia says with an energetic smirk.",
            "location": "School Grounds & Athletics ➔ Gym & Fieldhouse ➔ Main Court Area",
            "npcs_present": [
                {"name": "Sofia Anderson", "role": "Club President"}
            ],
            "next_choices": [
                {"label": "Inquire about resistant club heads", "stat": "INT", "requirement": 5}
            ]
        }

        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Westlake Academy ➔ Faculty Wing ➔ Staff Room",
            "current_npcs": [{"name": "Professor Halloway", "role": "Teacher"}],
            "dialogue_partners": ["Professor Halloway"],
            "history": []
        }
        party = [({"id": 1, "user_id": 12345, "name": "Artemiusz", "class": "Student", "str_": 5, "agi_": 5, "int_": 10}, [])]
        actions = [{
            "char": {"name": "Artemiusz"},
            "label": "Travel to the Gym & Fieldhouse to meet Sofia Anderson",
            "stat": "CHA",
            "check": type("Check", (), {"tier": "success", "chance": 85})(),
            "mp_spent": 0
        }]

        res = asyncio.run(game_engine.resolve_turn(session, party, actions))

        npc_names = [n["name"] if isinstance(n, dict) else n for n in res.get("npcs_present", [])]
        # Sofia Anderson must be immediately tracked upon arrival
        self.assertIn("Sofia Anderson", npc_names)
        # Professor Halloway must have stayed behind
        self.assertNotIn("Professor Halloway", npc_names)
        # Sofia must be the active dialogue partner
        self.assertEqual(res.get("dialogue_partner"), "Sofia Anderson")

    def test_contact_location_synchronization_on_arrival(self):
        """Verify that arriving at a new location automatically updates the contact's canonical location in database."""
        import json
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO contacts (session_id, character_id, npc_id, name, relationship_score, basic_info_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (self.test_session_id, 0, "sofia_anderson", "Sofia Anderson", 10,
                 json.dumps({"location": "Westlake Academy ➔ School Rooftop ➔ Rooftop Benches", "role": "Club President"}), 1000)
            )
            conn.commit()

        final_npcs = [{"name": "Sofia Anderson", "role": "Club President"}]
        new_loc = "School Grounds & Athletics ➔ Gym & Fieldhouse ➔ Main Court Area"

        mobility.sync_contact_locations(final_npcs, new_loc, self.test_session_id)

        contact = db.get_contact(self.test_session_id, "sofia_anderson")
        self.assertIsNotNone(contact)
        self.assertEqual(contact["basic_info"]["location"], new_loc)

    def test_quest_waypoint_rendezvous_deterministic_presence(self):
        """Verify that an active Story Quest waypoint guarantees NPC presence on arrival even if LLM omitted them."""
        import json
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO contacts (session_id, character_id, npc_id, name, relationship_score, basic_info_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (self.test_session_id, 0, "sofia_anderson", "Sofia Anderson", 10,
                 json.dumps({"location": "Westlake Academy ➔ School Rooftop ➔ Rooftop Benches", "role": "Club President"}), 1000)
            )
            # Active story quest & waypoint directing meeting with Sofia
            conn.execute(
                """INSERT INTO quests (session_id, quest_id, title, objective, status, is_story_quest, sub_objectives_json)
                   VALUES (?, 'story_ch1', 'Athletic Club Inquiries', 'Convene emergency meeting with Sofia Anderson', 'Active', 1, '[]')""",
                (self.test_session_id,)
            )
            conn.execute(
                """INSERT INTO quest_waypoints (session_id, quest_id, stage_index, stage_label, target_location, target_npc, completion_trigger, status)
                   VALUES (?, 'story_ch1', 1, 'Convene emergency meeting with Sofia Anderson', 'School Grounds & Athletics ➔ Gym & Fieldhouse ➔ Main Court Area', 'Sofia Anderson', 'arrival', 'active')""",
                (self.test_session_id,)
            )
            conn.commit()

        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Westlake Academy ➔ Faculty Wing ➔ Staff Room",
            "current_npcs": [],
            "dialogue_partners": []
        }
        # LLM output returns empty npcs_present
        result = {
            "outcome_narrative": "Artemiusz arrives at the gym.",
            "next_narrative": "The court echoes quietly.",
            "npcs_present": []
        }
        new_loc = "School Grounds & Athletics ➔ Gym & Fieldhouse ➔ Main Court Area"
        old_loc = "Westlake Academy ➔ Faculty Wing ➔ Staff Room"

        npcs = game_engine.process_scene_npcs(result, session, new_loc, old_loc, actions=[])
        npc_names = [n["name"] if isinstance(n, dict) else n for n in npcs]
        self.assertIn("Sofia Anderson", npc_names)

    @patch("game_engine.call_llm_json")
    def test_passive_mention_of_remote_npc_remains_pruned(self, mock_llm):
        """Verify that an ancient spirit bound to a distant dungeon (passive mention) is still pruned from a city guild hall."""
        import asyncio
        import json

        locs.process_llm_location_update(self.test_session_id, "Emerald Thicket ➔ Sunken Moonwell ➔ Ruined Archway", scenario_key="fantasy")
        locs.process_llm_location_update(self.test_session_id, "Royal Capital of Highspire ➔ Adventurers' Guild Hall ➔ Alice's Desk", scenario_key="fantasy")

        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO contacts (session_id, character_id, npc_id, name, relationship_score, basic_info_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (self.test_session_id, 0, "moonwell_wardens_echo", "Moonwell Warden's Echo", 10,
                 json.dumps({"location": "Emerald Thicket ➔ Sunken Moonwell ➔ Ruined Archway", "role": "Ancient Spirit"}), 1000)
            )
            conn.commit()

        # Passive rumor mention of the Moonwell Warden in Highspire
        mock_llm.return_value = {
            "title": "Guild Hall Inquiries",
            "outcome_narrative": "Alice asks Maelin about the distant Moonwell.",
            "next_narrative": "Maelin shakes her head. \"The warden has been asleep for centuries.\"",
            "location": "Royal Capital of Highspire ➔ Adventurers' Guild Hall ➔ Alice's Desk",
            "npcs_present": [
                {"name": "Maelin Voss", "role": "Guild Registrar"},
                {"name": "Moonwell Warden's Echo", "role": "Ancient Spirit"}
            ],
            "next_choices": [
                {"label": "Inquire about bounties", "stat": "INT", "requirement": 5}
            ]
        }

        session = {
            "id": self.test_session_id,
            "scenario": "fantasy",
            "current_location": "Royal Capital of Highspire ➔ Adventurers' Guild Hall ➔ Alice's Desk",
            "current_npcs": [{"name": "Maelin Voss", "role": "Guild Registrar"}],
            "dialogue_partners": ["Maelin Voss"],
            "history": []
        }
        party = [({"id": 1, "user_id": 12345, "name": "Alice", "class": "Mage", "str_": 5, "agi_": 5, "int_": 10}, [])]
        actions = [{
            "char": {"name": "Alice"},
            "label": "Ask Maelin about the bounty rewards",
            "stat": "CHA",
            "check": type("Check", (), {"tier": "success", "chance": 85})(),
            "mp_spent": 0
        }]

        res = asyncio.run(game_engine.resolve_turn(session, party, actions))

        npc_names = [n["name"] if isinstance(n, dict) else n for n in res.get("npcs_present", [])]
        self.assertIn("Maelin Voss", npc_names)
        self.assertNotIn("Moonwell Warden's Echo", npc_names)

    @patch("game_engine.call_llm_json")
    def test_campus_co_located_active_presence_speaking(self, mock_llm):
        """Verify that a mobile campus peer speaking in dialogue at connected campus facilities is tracked."""
        import asyncio
        import json

        locs.process_llm_location_update(self.test_session_id, "Westlake Academy ➔ Main Hallways ➔ 2nd Floor Corridor", scenario_key="high_school_drama")
        locs.process_llm_location_update(self.test_session_id, "School Grounds & Athletics ➔ Central Courtyard ➔ Fountain Benches", scenario_key="high_school_drama")

        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO contacts (session_id, character_id, npc_id, name, relationship_score, basic_info_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (self.test_session_id, 0, "sofia_anderson", "Sofia Anderson", 10,
                 json.dumps({"location": "Westlake Academy ➔ School Rooftop ➔ Rooftop Benches", "role": "Club President"}), 1000)
            )
            conn.commit()

        # General exploration: player didn't specifically target Sofia, but Sofia is at courtyard speaking directly
        mock_llm.return_value = {
            "title": "Courtyard Encounter",
            "outcome_narrative": "Artemiusz steps out into the crisp air of the central courtyard.",
            "next_narrative": "\"Hey Artemiusz!\" Sofia calls out from near the fountain with a bright grin.",
            "location": "School Grounds & Athletics ➔ Central Courtyard ➔ Fountain Benches",
            "npcs_present": [
                {"name": "Sofia Anderson", "role": "Club President"}
            ],
            "entity_audit": {
                "speaking_characters": ["Sofia Anderson"],
                "present_named_characters": ["Sofia Anderson"]
            },
            "next_choices": [
                {"label": "Greet Sofia", "stat": "CHA", "requirement": 5}
            ]
        }

        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Westlake Academy ➔ Main Hallways ➔ 2nd Floor Corridor",
            "current_npcs": [],
            "dialogue_partners": [],
            "history": []
        }
        party = [({"id": 1, "user_id": 12345, "name": "Artemiusz", "class": "Student", "str_": 5, "agi_": 5, "int_": 10}, [])]
        actions = [{
            "char": {"name": "Artemiusz"},
            "label": "Head outside to get some fresh air at the central courtyard",
            "stat": "AGI",
            "check": type("Check", (), {"tier": "success", "chance": 85})(),
            "mp_spent": 0
        }]

        res = asyncio.run(game_engine.resolve_turn(session, party, actions))

        npc_names = [n["name"] if isinstance(n, dict) else n for n in res.get("npcs_present", [])]
        self.assertIn("Sofia Anderson", npc_names)
        self.assertEqual(res.get("dialogue_partner"), "Sofia Anderson")

    @patch("game_engine.call_llm_json")
    def test_go_alone_and_excuse_still_leaves_patron_behind(self, mock_llm):
        """Verify that explicitly excusing oneself or choosing to travel alone leaves the NPC behind without clinginess."""
        import asyncio
        import json

        locs.process_llm_location_update(self.test_session_id, "Westlake Academy ➔ School Rooftop ➔ Rooftop Benches", scenario_key="high_school_drama")
        locs.process_llm_location_update(self.test_session_id, "Westlake Academy ➔ Academic Wing ➔ Classroom 3-B", scenario_key="high_school_drama")

        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO contacts (session_id, character_id, npc_id, name, relationship_score, basic_info_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (self.test_session_id, 0, "sofia_anderson", "Sofia Anderson", 50,
                 json.dumps({"location": "Westlake Academy ➔ School Rooftop ➔ Rooftop Benches", "role": "Club President"}), 1000)
            )
            conn.commit()

        mock_llm.return_value = {
            "title": "Homeroom Arrival",
            "outcome_narrative": "Artemiusz excuses himself from the rooftop and arrives in Classroom 3-B alone.",
            "next_narrative": "Students are chatting at their desks as the warning bell rings.",
            "location": "Westlake Academy ➔ Academic Wing ➔ Classroom 3-B",
            "npcs_present": [
                {"name": "Piotr Xu", "role": "Science Club President"}
            ],
            "next_choices": [
                {"label": "Take your seat", "stat": "INT", "requirement": 5}
            ]
        }

        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Westlake Academy ➔ School Rooftop ➔ Rooftop Benches",
            "current_npcs": [{"name": "Sofia Anderson", "role": "Club President"}],
            "dialogue_partners": ["Sofia Anderson"],
            "history": []
        }
        party = [({"id": 1, "user_id": 12345, "name": "Artemiusz", "class": "Student", "str_": 5, "agi_": 5, "int_": 10}, [])]
        actions = [{
            "char": {"name": "Artemiusz"},
            "label": "Excuse yourself and head to homeroom class alone",
            "stat": "CHA",
            "check": type("Check", (), {"tier": "success", "chance": 85})(),
            "mp_spent": 0
        }]

        res = asyncio.run(game_engine.resolve_turn(session, party, actions))

        npc_names = [n["name"] if isinstance(n, dict) else n for n in res.get("npcs_present", [])]
        self.assertIn("Piotr Xu", npc_names)
        self.assertNotIn("Sofia Anderson", npc_names)

    def test_phone_appointment_rendezvous_arrival_tracking(self):
        """Verify that arriving at a scheduled phone appointment rendezvous guarantees NPC presence."""
        import json
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO contacts (session_id, character_id, npc_id, name, relationship_score, basic_info_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (self.test_session_id, 0, "sofia_anderson", "Sofia Anderson", 10,
                 json.dumps({"location": "Westlake Academy ➔ School Rooftop ➔ Rooftop Benches", "role": "Club President"}), 1000)
            )
            conn.commit()

        # Pending phone appointment at the Gym
        db.save_phone_appointment(
            session_id=self.test_session_id,
            npc_id="sofia_anderson",
            npc_name="Sofia Anderson",
            rendezvous_location="School Grounds & Athletics ➔ Gym & Fieldhouse ➔ Main Court Area"
        )

        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Westlake Academy ➔ Faculty Wing ➔ Staff Room",
            "current_npcs": [],
            "dialogue_partners": []
        }
        result = {
            "outcome_narrative": "Artemiusz arrives at the gym per the phone text appointment.",
            "next_narrative": "The gym lights hum above.",
            "npcs_present": []
        }
        new_loc = "School Grounds & Athletics ➔ Gym & Fieldhouse ➔ Main Court Area"
        old_loc = "Westlake Academy ➔ Faculty Wing ➔ Staff Room"

        npcs = game_engine.process_scene_npcs(result, session, new_loc, old_loc, actions=[])
        npc_names = [n["name"] if isinstance(n, dict) else n for n in npcs]
        self.assertIn("Sofia Anderson", npc_names)


if __name__ == "__main__":
    unittest.main()

