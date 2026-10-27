from __future__ import annotations
from typing import Any
import asyncio
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import db
import db.core
import game_engine


class TestProseEntitySync(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._isolated_db = os.path.join(self._tmp_dir.name, "test_prose_sync.db")
        self._orig_db_path = db.DB_PATH
        self._orig_core_db_path = db.core.DB_PATH
        db.DB_PATH = self._isolated_db
        db.core.DB_PATH = self._isolated_db
        db.init_db()

        self.session_id = 99899
        self.user_id = 99899

        db.create_character(
            self.user_id,
            "Artemiusz",
            char_class="Student",
            stats={"STR": 5, "PER": 7, "END": 5, "CHA": 8, "INT": 9, "AGI": 6, "LUK": 5},
        )

        with db.get_conn() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, channel_id, host_user_id, status, mode, capacity, scenario, current_location, turn_order, current_npcs_json)
                VALUES (?, 100, ?, 'active', 'solo', 1, 'high_school_drama', 'Westlake Academy ➔ Student Council Office ➔ Main Office Area', ?, ?)
                """,
                (
                    self.session_id,
                    self.user_id,
                    json.dumps([self.user_id]),
                    json.dumps([{"name": "Zihan Moon", "hp": 100, "max_hp": 100}]),
                ),
            )

        roster = [
            {"rank": 4, "title": "Club President", "name": "Sofia Anderson", "is_player": False},
            {"rank": 3, "title": "Vice President", "name": "Manon Sokolov", "is_player": False},
            {"rank": 2, "title": "Club Secretary", "name": "So-hee Mendoza", "is_player": False},
            {"rank": 1, "title": "Club Treasurer", "name": "Mila Kuznetsov", "is_player": False},
        ]
        db.upsert_faction(
            session_id=self.session_id,
            name="Velvet Rose Pact",
            delta_score=0,
            hierarchy_template="club",
            leadership_roster=roster,
            hq_location_id="Student Council Office",
        )

    def tearDown(self):
        if hasattr(db, "close_all_connections"):
            db.close_all_connections()
        db.DB_PATH = self._orig_db_path
        db.core.DB_PATH = self._orig_core_db_path
        self._tmp_dir.cleanup()

    def test_deterministic_cast_stays_strictly_structured_without_prose_scraping(self):
        """Verify process_scene_npcs stays strictly structured and never scrapes un-staged faction members from prose."""
        session = db.get_session(self.session_id)
        loc = "Westlake Academy ➔ Student Council Office ➔ Main Office Area"

        raw_llm_result = {
            "scene_title": "The Seat of Authority",
            "outcome_narrative": "Artemiusz steps forward and presents the incident report to the council.",
            "next_narrative": "Behind the massive mahogany desk sits Sofia Anderson. Beside her, the other council members—Mila, So-hee, and Manon—watch with varying degrees of curiosity.",
            "npcs_present": [{"name": "Sofia Anderson"}],
        }

        det_npcs = game_engine.process_scene_npcs(raw_llm_result, session, loc, loc)
        det_names = [n.get("name") if isinstance(n, dict) else n for n in det_npcs]
        self.assertIn("Zihan Moon", det_names)
        self.assertIn("Sofia Anderson", det_names)
        self.assertNotIn("Manon Sokolov", det_names)
        self.assertNotIn("So-hee Mendoza", det_names)
        self.assertNotIn("Mila Kuznetsov", det_names)

    def test_entity_audit_parsing(self):
        """Verify that characters listed in entity_audit are parsed and included when grounded."""
        session = db.get_session(self.session_id)
        loc = "Westlake Academy ➔ Student Council Office ➔ Main Office Area"

        raw_llm_result = {
            "scene_title": "Meeting",
            "entity_audit": {
                "present_named_characters": ["Sofia Anderson", "Yea-ji Kang"],
            },
            "outcome_narrative": "Discussions begin with Sofia Anderson and Yea-ji Kang.",
            "next_narrative": "The council reviews the papers.",
            "npcs_present": [],
        }

        final_npcs = game_engine.process_scene_npcs(raw_llm_result, session, loc, loc)
        npc_names = [n.get("name") if isinstance(n, dict) else n for n in final_npcs]

        self.assertIn("Sofia Anderson", npc_names)
        self.assertIn("Yea-ji Kang", npc_names)

    def test_remote_contacts_in_other_zones_not_added_from_prose(self):
        """Verify that mentioning someone far away in another zone does NOT summon them into the room."""
        session = db.get_session(self.session_id)
        loc = "Westlake Academy ➔ Student Council Office ➔ Main Office Area"

        db.upsert_contact(
            self.session_id,
            character_id=0,
            npc_id="downtown_detective",
            name="Detective Vance",
            basic_info={"location": "Downtown District ➔ Police Station"},
        )

        raw_llm_result = {
            "scene_title": "Memories",
            "outcome_narrative": "Artemiusz recalled what Detective Vance told him earlier in the downtown district.",
            "next_narrative": "Sofia waits for your answer.",
            "npcs_present": [{"name": "Sofia Anderson"}],
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
            },
            "outcome_narrative": "Artemiusz speaks.",
            "next_narrative": "Sofia answers Artemiusz.",
            "npcs_present": [{"name": "Artemiusz"}, {"name": "Sofia Anderson"}],
        }

        final_npcs = game_engine.process_scene_npcs(raw_llm_result, session, loc, loc)
        npc_names = [n.get("name") if isinstance(n, dict) else n for n in final_npcs]

        self.assertNotIn("Artemiusz", npc_names)
        self.assertIn("Sofia Anderson", npc_names)

    def test_generate_opening_scene_uses_structured_npcs_and_locks_spatial_node(self):
        """Verify Turn 0 OpeningScene uses structured npcs_present only (never prose scraping) and locks current_node_id."""
        from game_engine.turn.generation import generate_opening_scene

        session = db.get_session(self.session_id)
        char = db.get_character(self.user_id)
        party = [(char, [])]

        raw_llm_result = {
            "scene_title": "Petals & Promises",
            "narrative": "Under the tree stands Sofia Anderson, scanning the crowd. Beside her, Manon Sokolov clutches a stack of brochures.",
            "choices": [{"label": "Observe surroundings", "stat": "PER", "requirement": 5}],
            "location": "Westlake Academy ➔ Student Council Office ➔ Main Office Area",
            "npcs_present": [],
        }

        with patch(
            "game_engine.turn.generation.game_engine.call_llm_json",
            new=AsyncMock(return_value=dict(raw_llm_result)),
        ):
            det_scene = asyncio.run(generate_opening_scene(dict(session), party))
            det_names = [n.get("name") if isinstance(n, dict) else n for n in det_scene.get("npcs_present", [])]
            self.assertNotIn("Sofia Anderson", det_names)
            self.assertNotIn("Manon Sokolov", det_names)
            self.assertTrue(bool(det_scene.get("current_node_id") or db.get_session_world_nodes(self.session_id)))


if __name__ == "__main__":
    unittest.main()
