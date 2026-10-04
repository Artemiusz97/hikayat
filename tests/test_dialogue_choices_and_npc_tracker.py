import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
import game_engine
from cogs.adventure import AdventureCog


class TestDialogueChoicesAndNPCTracker(unittest.TestCase):

    def setUp(self):
        self.test_session_id = 887766
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.test_session_id,))
            conn.commit()

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.test_session_id,))
            conn.commit()

    def test_clean_choices_in_dialogue_mode_filters_wandering_and_guarantees_exit(self):
        """Verify _clean_choices removes unrelated room wanderings and guarantees a free exit choice."""
        raw_choices = [
            {"label": "Question Maelin about the ledger", "stat": "CHA", "requirement": 5},
            {"label": "Study the contract runes with Maelin", "stat": "INT", "requirement": 6},
            {"label": "Search public quest boards on the wall", "stat": "LUK", "requirement": 5},
            {"label": "Inspect the undercroft basement access", "stat": "PER", "requirement": 7},
            {"label": "Leave the guild and explore the city", "stat": "AGI", "requirement": 5},
        ]

        cleaned = AdventureCog._clean_choices(raw_choices, dialogue_partner="Maelin Voss")
        labels = [c["label"] for c in cleaned]

        # In-dialogue choices are preserved
        self.assertTrue(any("Question Maelin" in l for l in labels))
        self.assertTrue(any("Study the contract" in l for l in labels))

        # Room wandering choices are filtered out
        self.assertFalse(any("Search public quest boards" in l for l in labels))
        self.assertFalse(any("Inspect the undercroft" in l for l in labels))
        self.assertFalse(any("Leave the guild" in l for l in labels))

        # Guaranteed exit choice was appended
        exit_choices = [c for c in cleaned if c["stat"] == "NONE" and c["requirement"] == 0]
        self.assertEqual(len(exit_choices), 1)
        self.assertIn("Thank Maelin", exit_choices[0]["label"])

    def test_clean_choices_in_dialogue_mode_preserves_existing_exit(self):
        """Verify that if the LLM already provided an exit choice, it is kept and not duplicated."""
        raw_choices = [
            {"label": "Question Maelin about the ledger", "stat": "CHA", "requirement": 5},
            {"label": "Thank Maelin, excuse yourself, and survey the room", "stat": "NONE", "requirement": 0},
        ]

        cleaned = AdventureCog._clean_choices(raw_choices, dialogue_partner="Maelin Voss")
        self.assertEqual(len(cleaned), 2)
        exit_choices = [c for c in cleaned if c["stat"] == "NONE"]
        self.assertEqual(len(exit_choices), 1)

    @patch("game_engine.call_llm_json")
    def test_zone_transition_preserves_newly_generated_npcs(self, mock_llm):
        """Verify that moving to a new zone retains new NPCs introduced at the destination."""
        import asyncio
        import mechanics.world.locations as locs

        locs.process_llm_location_update(self.test_session_id, "Emerald Thicket ➔ Sunken Moonwell ➔ Ruined Archway", scenario_key="fantasy")
        locs.process_llm_location_update(self.test_session_id, "Royal Capital of Highspire ➔ Adventurers' Guild Hall ➔ Registrar's Desk", scenario_key="fantasy")

        # LLM returns new location and new NPC Maelin Voss
        mock_llm.return_value = {
            "title": "The Guildbound Arrival",
            "outcome_narrative": "Alice arrives in the bustling capital.",
            "next_narrative": "Behind the registrar's desk, Maelin Voss looks up.",
            "location": "Royal Capital of Highspire ➔ Adventurers' Guild Hall ➔ Registrar's Desk",
            "npcs_present": [{"name": "Maelin Voss", "description": "Guild registrar"}],
            "next_choices": [
                {"label": "Talk to Maelin Voss", "stat": "CHA", "requirement": 5},
                {"label": "Search notice board", "stat": "PER", "requirement": 5}
            ]
        }

        session = {
            "id": self.test_session_id,
            "scenario": "fantasy",
            "current_location": "Emerald Thicket ➔ Sunken Moonwell ➔ Ruined Archway",
            "current_npcs": [{"name": "Moonwell Warden's Echo", "description": "Ancient spirit"}],
            "history": []
        }
        party = [({"id": 1, "user_id": 12345, "name": "Alice", "class": "Mage", "str_": 5, "agi_": 5, "int_": 10}, [])]
        actions = [{
            "char": {"name": "Alice"},
            "label": "Travel toward Highspire's Adventurers' Guild Hall",
            "stat": "NONE",
            "check": type("Check", (), {"tier": "success", "chance": 100})(),
            "mp_spent": 0
        }]

        res = asyncio.run(game_engine.resolve_turn(session, party, actions))
        
        # Verify Maelin Voss is preserved in npcs_present
        npc_names = [n["name"] if isinstance(n, dict) else n for n in res.get("npcs_present", [])]
        self.assertIn("Maelin Voss", npc_names)
        # Verify old spirit from previous zone is not carried over
        self.assertNotIn("Moonwell Warden's Echo", npc_names)

    @patch("game_engine.call_llm_json")
    def test_dialogue_partner_state_transition(self, mock_llm):
        """Verify dialogue_partner activates on talking to an NPC and clears on exit."""
        import asyncio

        mock_llm.return_value = {
            "title": "Speaking with Maelin",
            "outcome_narrative": "Alice speaks with Maelin.",
            "next_narrative": "Maelin leans closer and whispers.",
            "location": "Royal Capital of Highspire ➔ Adventurers' Guild Hall ➔ Registrar's Desk",
            "npcs_present": [{"name": "Maelin Voss", "description": "Guild registrar"}],
            "next_choices": [
                {"label": "Question Maelin further", "stat": "INT", "requirement": 6},
                {"label": "Thank Maelin and step away", "stat": "NONE", "requirement": 0}
            ]
        }

        session = {
            "id": self.test_session_id,
            "scenario": "fantasy",
            "current_location": "Royal Capital of Highspire ➔ Adventurers' Guild Hall ➔ Registrar's Desk",
            "current_npcs": [{"name": "Maelin Voss", "description": "Guild registrar"}],
            "dialogue_partner": None,
            "history": []
        }
        party = [({"id": 1, "user_id": 12345, "name": "Alice", "class": "Mage", "str_": 5, "agi_": 5, "int_": 10}, [])]

        # Action 1: Start dialogue with Maelin Voss
        actions_start = [{
            "char": {"name": "Alice"},
            "label": "Talk to Maelin Voss at the desk",
            "stat": "CHA",
            "check": type("Check", (), {"tier": "success", "chance": 80})(),
            "mp_spent": 0
        }]
        res1 = asyncio.run(game_engine.resolve_turn(session, party, actions_start))
        self.assertEqual(res1.get("dialogue_partner"), "Maelin Voss")

        # Action 2: Choose exit
        session["dialogue_partner"] = "Maelin Voss"
        actions_exit = [{
            "char": {"name": "Alice"},
            "label": "Thank Maelin, excuse yourself, and look around the room",
            "stat": "NONE",
            "check": type("Check", (), {"tier": "success", "chance": 100})(),
            "mp_spent": 0
        }]
        res2 = asyncio.run(game_engine.resolve_turn(session, party, actions_exit))
        self.assertIsNone(res2.get("dialogue_partner"))

    @patch("game_engine.call_llm_json")
    def test_dialogue_partner_cleared_on_travel_to_empty_room(self, mock_llm):
        """Verify dialogue_partner is cleared when traveling to a location where no NPCs are present."""
        import asyncio

        mock_llm.return_value = {
            "title": "The Silent Rooftop",
            "outcome_narrative": "Alice steps onto the silent roof alcove.",
            "next_narrative": "The wind howls across the empty concrete.",
            "location": "Maplewood Academy ➔ School Rooftop ➔ East Maintenance Alcove",
            "npcs_present": [],
            "next_choices": [
                {"label": "Search for the hidden ledge", "stat": "PER", "requirement": 5},
                {"label": "Analyze the atmospheric shimmer", "stat": "INT", "requirement": 6}
            ]
        }

        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Maplewood Academy ➔ School Library ➔ Restricted Archives",
            "current_npcs": [{"name": "Tim Wilson", "role": "Club Treasurer"}],
            "dialogue_partner": "Tim Wilson",
            "dialogue_partners": ["Tim Wilson"],
            "history": []
        }
        party = [({"id": 1, "user_id": 12345, "name": "Alice", "class": "Journalist", "str_": 5, "agi_": 5, "int_": 10}, [])]

        actions = [{
            "char": {"name": "Alice"},
            "label": "Travel to the school rooftop to find the ledge",
            "stat": "NONE",
            "check": type("Check", (), {"tier": "success", "chance": 100})(),
            "mp_spent": 0
        }]
        res = asyncio.run(game_engine.resolve_turn(session, party, actions))
        self.assertIsNone(res.get("dialogue_partner"))
        self.assertEqual(res.get("dialogue_partners"), [])
        self.assertEqual(res.get("npcs_present"), [])

    def test_classify_scene_npcs_does_not_carry_dialogue_partner_to_new_primary_location(self):
        """Verify that classify_scene_npcs leaves behind old dialogue partners when moving between primary locations."""
        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Maplewood Academy ➔ School Rooftop ➔ East Maintenance Alcove",
            "current_npcs": [{"name": "Tim Wilson", "role": "Club Treasurer"}],
            "dialogue_partner": "Tim Wilson",
            "dialogue_partners": ["Tim Wilson"],
        }
        traveling, left_behind = game_engine.classify_scene_npcs(
            session, actions=[], old_primary="School Rooftop", dest_primary="Student Council Office"
        )
        traveling_names = [n.get("name") for n in traveling]
        left_behind_names = [n.get("name") for n in left_behind]
        self.assertNotIn("Tim Wilson", traveling_names)
        self.assertIn("Tim Wilson", left_behind_names)

    def test_prose_scanner_requires_matching_known_zone(self):
        """Verify that local contact scanner does not inject contacts whose location is empty or in another zone."""
        sess_id = db.create_session(999123, "solo", 1, "vivid", "individual", False, scenario="high_school_drama")
        try:
            # Contact 1: Tim Wilson has no location set
            db.upsert_contact(sess_id, 0, "tim_wilson", "Tim Wilson", basic_info={"role": "Treasurer", "location": ""})
            # Contact 2: Sofia has a location in Residential Neighborhood
            db.upsert_contact(sess_id, 0, "sofia", "Sofia Anderson", basic_info={"role": "Student", "location": "Residential Neighborhood ➔ Park"})

            raw_result = {
                "outcome_narrative": "Alice recalls Tim Wilson and Sofia Anderson while studying.",
                "next_narrative": "The room is quiet.",
                "npcs_present": []
            }
            session = db.get_session(sess_id)
            npcs = game_engine.process_scene_npcs(raw_result, session, "Westlake Academy ➔ Classroom 2-B ➔ Desk", "Westlake Academy ➔ Hallway")
            npc_names = [n.get("name") for n in npcs]
            # Neither should be injected into Classroom 2-B
            self.assertNotIn("Tim Wilson", npc_names)
            self.assertNotIn("Sofia Anderson", npc_names)
        finally:
            with db.get_conn() as conn:
                conn.execute("DELETE FROM contacts WHERE session_id = ?", (sess_id,))
                conn.execute("DELETE FROM sessions WHERE id = ?", (sess_id,))

    def test_clean_choices_deduplicates_multiple_speak_options_for_same_npc(self):
        """Verify that _clean_choices collapses duplicate Speak with options targeting the same NPC."""
        raw_choices = [
            {"label": "Speak with Tim Wilson (Club Treasurer)", "stat": "NONE", "requirement": 0},
            {"label": "Speak with Tim Wilson", "stat": "NONE", "requirement": 0},
            {"label": "Talk to Tim Wilson", "stat": "NONE", "requirement": 0},
            {"label": "Converse with Tim Wilson", "stat": "NONE", "requirement": 0},
            {"label": "Search the room for hidden items", "stat": "PER", "requirement": 5},
        ]
        cleaned = AdventureCog._clean_choices(raw_choices, current_npcs=[{"name": "Tim Wilson", "role": "Club Treasurer"}])
        speak_choices = [c for c in cleaned if "tim wilson" in c["label"].lower()]
        self.assertEqual(len(speak_choices), 1)


if __name__ == "__main__":
    unittest.main()

