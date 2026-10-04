import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
import game_engine
from cogs.adventure import AdventureCog, _format_tracker_entity, _tracker_group_text
import mechanics.world.locations as locs


class TestMultiNPCDialogueAndPresenceValidation(unittest.TestCase):

    def setUp(self):
        self.test_session_id = 998877
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.test_session_id,))
            conn.commit()

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.test_session_id,))
            conn.commit()

    def test_dashboard_tracker_conversation_marker(self):
        """Verify _format_tracker_entity and _tracker_group_text render 💬 next to active conversants."""
        npcs = [
            {"name": "Maelin Voss", "role": "Guild Registrar"},
            {"name": "Aide Marcus", "role": "Clerk"},
        ]

        # 1-on-1 dialogue with Maelin Voss
        text = _tracker_group_text(npcs, dialogue_partners=["Maelin Voss"])
        self.assertIn("💬 **Maelin Voss** (Guild Registrar)", text)
        self.assertIn("**Aide Marcus** (Clerk)", text)
        self.assertNotIn("💬 **Aide Marcus**", text)

        # Multi-NPC dialogue with both Maelin and Marcus
        text_multi = _tracker_group_text(npcs, dialogue_partners=["Maelin Voss", "Aide Marcus"])
        self.assertIn("💬 **Maelin Voss** (Guild Registrar)", text_multi)
        self.assertIn("💬 **Aide Marcus** (Clerk)", text_multi)

        # No dialogue active (open room exploration)
        text_none = _tracker_group_text(npcs, dialogue_partners=[])
        self.assertNotIn("🗣️", text_none)

    @patch("game_engine.call_llm_json")
    def test_anti_teleportation_prunes_remote_zone_npcs(self, mock_llm):
        """Verify that an NPC bound to Emerald Thicket is pruned when the party is in Highspire."""
        import asyncio

        locs.process_llm_location_update(self.test_session_id, "Emerald Thicket ➔ Sunken Moonwell ➔ Ruined Archway", scenario_key="fantasy")
        locs.process_llm_location_update(self.test_session_id, "Royal Capital of Highspire ➔ Adventurers' Guild Hall ➔ Alice's Desk", scenario_key="fantasy")

        # Record Moonwell Warden's Echo in contacts with home location in Emerald Thicket
        import json
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO contacts (session_id, character_id, npc_id, name, relationship_score, basic_info_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (self.test_session_id, 0, "moonwell_wardens_echo", "Moonwell Warden's Echo", 10,
                 json.dumps({"location": "Emerald Thicket ➔ Sunken Moonwell ➔ Ruined Archway"}), 1000)
            )
            conn.commit()

        # LLM hallucinates Moonwell Warden's Echo into npcs_present while in Highspire
        mock_llm.return_value = {
            "title": "Guild Hall Inquiries",
            "outcome_narrative": "Alice speaks to the registrar about the distant Moonwell.",
            "next_narrative": "Maelin stamps the parchment.",
            "location": "Royal Capital of Highspire ➔ Adventurers' Guild Hall ➔ Alice's Desk",
            "npcs_present": [
                {"name": "Maelin Voss", "description": "Guild registrar"},
                {"name": "Moonwell Warden's Echo", "description": "Ancient spirit back at the thicket"}
            ],
            "next_choices": [
                {"label": "Ask Maelin about the bounty", "stat": "CHA", "requirement": 5}
            ]
        }

        session = {
            "id": self.test_session_id,
            "scenario": "fantasy",
            "current_location": "Royal Capital of Highspire ➔ Adventurers' Guild Hall ➔ Alice's Desk",
            "current_npcs": [{"name": "Maelin Voss", "description": "Guild registrar"}],
            "dialogue_partners": ["Maelin Voss"],
            "history": []
        }
        party = [({"id": 1, "user_id": 12345, "name": "Alice", "class": "Mage", "str_": 5, "agi_": 5, "int_": 10}, [])]
        actions = [{
            "char": {"name": "Alice"},
            "label": "Ask Maelin about the bounty reward",
            "stat": "CHA",
            "check": type("Check", (), {"tier": "success", "chance": 85})(),
            "mp_spent": 0
        }]

        res = asyncio.run(game_engine.resolve_turn(session, party, actions))

        npc_names = [n["name"] if isinstance(n, dict) else n for n in res.get("npcs_present", [])]
        # Maelin Voss must be present in Highspire
        self.assertIn("Maelin Voss", npc_names)
        # Moonwell Warden's Echo must be stripped by the anti-teleportation validation
        self.assertNotIn("Moonwell Warden's Echo", npc_names)

    @patch("game_engine.call_llm_json")
    def test_multi_npc_dialogue_state_tracking(self, mock_llm):
        """Verify dialogue_partners tracks multiple NPCs simultaneously and clears on exit."""
        import asyncio

        mock_llm.return_value = {
            "title": "Addressing the Council",
            "outcome_narrative": "Alice speaks to both Sarah and Marcus.",
            "next_narrative": "Sarah and Marcus exchange glances.",
            "location": "Main Academy Building ➔ Student Council Office ➔ Conference Table",
            "npcs_present": [
                {"name": "Sarah Chen", "description": "Council President"},
                {"name": "Marcus Vance", "description": "Vice President"}
            ],
            "next_choices": [
                {"label": "Present evidence to Sarah Chen and Marcus Vance", "stat": "INT", "requirement": 6},
                {"label": "Thank everyone and step away", "stat": "NONE", "requirement": 0}
            ]
        }

        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Main Academy Building ➔ Student Council Office ➔ Conference Table",
            "current_npcs": [
                {"name": "Sarah Chen", "description": "Council President"},
                {"name": "Marcus Vance", "description": "Vice President"}
            ],
            "dialogue_partners": [],
            "history": []
        }
        party = [({"id": 1, "user_id": 12345, "name": "Alice", "class": "Detective", "str_": 5, "agi_": 5, "int_": 10}, [])]

        # Action: Address both Sarah Chen and Marcus Vance
        actions_multi = [{
            "char": {"name": "Alice"},
            "label": "Talk to both Sarah Chen and Marcus Vance regarding the budget",
            "stat": "CHA",
            "check": type("Check", (), {"tier": "success", "chance": 90})(),
            "mp_spent": 0
        }]

        res = asyncio.run(game_engine.resolve_turn(session, party, actions_multi))
        partners = res.get("dialogue_partners", [])
        self.assertIn("Sarah Chen", partners)
        self.assertIn("Marcus Vance", partners)

        # Next turn: Choose exit
        session["dialogue_partners"] = ["Sarah Chen", "Marcus Vance"]
        actions_exit = [{
            "char": {"name": "Alice"},
            "label": "Thank everyone, excuse yourself, and step away to look around",
            "stat": "NONE",
            "check": type("Check", (), {"tier": "success", "chance": 100})(),
            "mp_spent": 0
        }]
        res_exit = asyncio.run(game_engine.resolve_turn(session, party, actions_exit))
        self.assertEqual(res_exit.get("dialogue_partners"), [])
        self.assertIsNone(res_exit.get("dialogue_partner"))

    @patch("game_engine.call_llm_json")
    def test_left_behind_npc_pruned_from_choices_on_location_transition(self, mock_llm):
        """Verify that when the party travels to a new primary location, left-behind NPCs are pruned from next_choices."""
        import asyncio

        # LLM returns a hallucinated choice to speak with Sofia Anderson after traveling to the Science Lab
        mock_llm.return_value = {
            "title": "The Sterile Silence",
            "outcome_narrative": "Artemiusz descends from the rooftop and arrives at the Chemistry & Science Lab.",
            "next_narrative": "The laboratory is quiet and evacuated.",
            "location": "Westlake Academy ➔ Chemistry & Science Lab ➔ Main Laboratory Floor",
            "npcs_present": [],
            "next_choices": [
                {"label": "Greet and talk with Sofia Anderson", "stat": "NONE", "requirement": 0},
                {"label": "Inspect the chemical spill zones for residue", "stat": "PER", "requirement": 5},
                {"label": "Review the abandoned lab notes on the desks", "stat": "INT", "requirement": 5},
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
        party = [({"id": 1, "user_id": 12345, "name": "Artemiusz", "class": "Detective", "str_": 5, "agi_": 5, "int_": 10}, [])]
        actions = [{
            "char": {"name": "Artemiusz"},
            "label": "Travel to Westlake Academy ➔ Chemistry & Science Lab",
            "stat": "AGI",
            "check": type("Check", (), {"tier": "success", "chance": 100})(),
            "mp_spent": 0
        }]

        res = asyncio.run(game_engine.resolve_turn(session, party, actions))

        choice_labels = [c.get("label", "") for c in res.get("next_choices", [])]
        # Sofia Anderson must NOT be in next_choices
        self.assertFalse(any("Sofia Anderson" in l for l in choice_labels))
        self.assertTrue(any("Inspect the chemical spill" in l for l in choice_labels))

    def test_clean_choices_prunes_absent_known_npc_dialogue(self):
        """Verify _clean_choices prunes greeting/dialogue options targeting absent known contacts."""
        import json
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO contacts (session_id, character_id, npc_id, name, relationship_score, basic_info_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (self.test_session_id, 0, "sofia_anderson", "Sofia Anderson", 10,
                 json.dumps({"location": "Westlake Academy ➔ School Rooftop ➔ Rooftop Benches"}), 1000)
            )
            conn.commit()

        incoming_choices = [
            {"label": "Greet and talk with Sofia Anderson", "stat": "NONE", "requirement": 0},
            {"label": "Inspect the chemical spill zones for residue", "stat": "PER", "requirement": 5},
            {"label": "Review the abandoned lab notes on the desks", "stat": "INT", "requirement": 5},
            {"label": "Proceed toward the Teachers' Staff Room", "stat": "NONE", "requirement": 0}
        ]

        cleaned = AdventureCog._clean_choices(
            incoming_choices,
            scenario="high_school_drama",
            location="Westlake Academy ➔ Chemistry & Science Lab ➔ Main Laboratory Floor",
            char={"name": "Artemiusz"},
            dialogue_partner=None,
            current_npcs=[],
            session_id=self.test_session_id
        )

        labels = [c.get("label", "") for c in cleaned]
        self.assertFalse(any("Sofia Anderson" in l for l in labels))
        self.assertTrue(any("Inspect the chemical spill" in l for l in labels))
        self.assertTrue(any("Proceed toward" in l for l in labels))


if __name__ == "__main__":
    unittest.main()

