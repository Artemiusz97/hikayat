import unittest
import sqlite3
import json
from unittest.mock import patch

import db
from models.llm_schemas import TurnOutcome
from models.trackers import TrackerEntity, NewEntity, RelationshipUpdate
from game_engine.npcs import process_scene_npcs
from cogs.contacts import build_contact_detail_embed


class TestContactMetadataPersistence(unittest.TestCase):
    def setUp(self):
        self.session_id = db.create_session(
            host_user_id=1001,
            mode="solo",
            capacity=1,
            verbosity="normal",
            dialogue_mode="adaptive",
            image_gen_enabled=False,
            scenario="high_school_drama"
        )

    def tearDown(self):
        db.delete_session(self.session_id)

    def test_pydantic_turn_outcome_preserves_npc_and_new_entity_metadata(self):
        """Verify TurnOutcome validation does not strip role, faction, club, grade, or description."""
        raw_payload = {
            "scene_title": "The Student Lounge",
            "outcome_narrative": "You approach the desk.",
            "next_narrative": "Denise Yamada, the Student Council President, looks up from her documents.",
            "npcs_present": [
                {
                    "name": "Denise Yamada",
                    "role": "Student Council President",
                    "faction": "Student Council",
                    "club": "Student Council",
                    "club_role": "President",
                    "grade": "Senior",
                    "description": "The composed and diligent president of the Student Council.",
                    "disposition": "friendly",
                    "traits": ["Diligent", "Composed"],
                    "preferences": ["Likes Matcha Tea", "Dislikes Tardiness"]
                }
            ],
            "new_entities": [
                {
                    "type": "person",
                    "name": "Denise Yamada",
                    "role": "Student Council President",
                    "faction": "Student Council",
                    "club": "Student Council",
                    "club_role": "President",
                    "grade": "Senior",
                    "description": "The composed and diligent president of the Student Council.",
                    "disposition": "friendly",
                    "traits": ["Diligent", "Composed"],
                    "preferences": ["Likes Matcha Tea", "Dislikes Tardiness"]
                }
            ]
        }
        validated = TurnOutcome.model_validate(raw_payload).model_dump()
        npc = validated["npcs_present"][0]
        self.assertEqual(npc["name"], "Denise Yamada")
        self.assertEqual(npc["role"], "Student Council President")
        self.assertEqual(npc["faction"], "Student Council")
        self.assertEqual(npc["club"], "Student Council")
        self.assertEqual(npc["club_role"], "President")
        self.assertEqual(npc["grade"], "Senior")
        self.assertEqual(npc["description"], "The composed and diligent president of the Student Council.")

        ent = validated["new_entities"][0]
        self.assertEqual(ent["role"], "Student Council President")
        self.assertEqual(ent["faction"], "Student Council")
        self.assertEqual(ent["club"], "Student Council")
        self.assertEqual(ent["club_role"], "President")
        self.assertEqual(ent["grade"], "Senior")

    def test_empty_basic_info_never_overwrites_existing_contact_metadata(self):
        """Verify ensure_scene_npcs_in_contacts or empty basic_info dicts never wipe out saved role/description."""
        db.upsert_contact(
            session_id=self.session_id,
            npc_id="denise_yamada",
            name="Denise Yamada",
            basic_info={
                "role": "Student Council President",
                "faction": "Student Council",
                "club": "Student Council",
                "club_role": "President",
                "grade": "Senior",
                "description": "Focused Student Council President who keeps strict order."
            },
            delta_score=3
        )

        # Simulate subsequent turn where scene NPC has empty role and description
        db.upsert_contact(
            session_id=self.session_id,
            npc_id="denise_yamada",
            name="Denise Yamada",
            basic_info={"role": "", "description": ""},
            delta_score=2
        )

        contact = db.get_contact(self.session_id, "Denise Yamada")
        self.assertIsNotNone(contact)
        binfo = contact["basic_info"]
        self.assertEqual(binfo.get("role"), "Student Council President")
        self.assertEqual(binfo.get("faction"), "Student Council")
        self.assertEqual(binfo.get("club"), "Student Council")
        self.assertEqual(binfo.get("club_role"), "President")
        self.assertEqual(binfo.get("grade"), "Senior")
        self.assertIn("Focused Student Council President", binfo.get("description", ""))

    def test_narrative_role_and_affiliation_extraction_on_blank_npc(self):
        """Verify an NPC introduced in narrative as 'Denise Yamada, the Student Council President' gets full metadata."""
        narr = (
            "Near the center of the room, Denise Yamada, the Student Council President, is reviewing a stack of documents. "
            "She is a focused presence, her posture perfectly straight as she ignores the noise around her."
        )
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE sessions SET narrative=?, current_npcs_json=? WHERE id=?",
                (narr, json.dumps([{"name": "Denise Yamada", "role": ""}]), self.session_id)
            )

        db.ensure_scene_npcs_in_contacts(self.session_id)
        contact = db.get_contact(self.session_id, "Denise Yamada")
        self.assertIsNotNone(contact)
        binfo = contact["basic_info"]
        self.assertEqual(binfo.get("role"), "Student Council President")
        self.assertEqual(binfo.get("faction"), "Student Council")
        self.assertEqual(binfo.get("club"), "Student Council")
        self.assertEqual(binfo.get("club_role"), "President")
        self.assertEqual(binfo.get("grade"), "Senior")
        self.assertIn("Denise Yamada, the Student Council President", binfo.get("description", ""))

        embed = build_contact_detail_embed(contact, "high_school_drama")
        basic_field = next(f for f in embed.fields if f.name == "Basic Details")
        self.assertIn("• **Grade / Standing**: Senior", basic_field.value)
        self.assertIn("• **Role**: Student Council President", basic_field.value)
        self.assertIn("• **Faction Affiliation**: Student Council (President)", basic_field.value)

    def test_process_scene_npcs_merges_entity_audit_and_new_entities_metadata(self):
        """Verify process_scene_npcs does not drop new_entities metadata when entity_audit lists the same NPC first."""
        session = {
            "id": self.session_id,
            "scenario": "high_school_drama",
            "current_location": "St. Michael Academy ➔ Student Lounge ➔ Main Area",
            "current_npcs": []
        }
        result = {
            "location": "St. Michael Academy ➔ Student Lounge ➔ Main Area",
            "outcome_narrative": "You enter the student lounge.",
            "next_narrative": "Denise Yamada, the Student Council President, greets you.",
            "entity_audit": {
                "present_named_characters": ["Denise Yamada"],
                "speaking_characters": ["Denise Yamada"],
                "departed_characters": []
            },
            "npcs_present": [{"name": "Denise Yamada"}],
            "new_entities": [
                {
                    "type": "person",
                    "name": "Denise Yamada",
                    "role": "Student Council President",
                    "faction": "Student Council",
                    "club": "Student Council",
                    "club_role": "President",
                    "grade": "Senior",
                    "description": "The diligent Student Council President."
                }
            ]
        }
        loc = "St. Michael Academy ➔ Student Lounge ➔ Main Area"
        present = process_scene_npcs(result, session, loc, loc, actions=[])
        self.assertEqual(len(present), 1)
        self.assertEqual(present[0]["name"], "Denise Yamada")
        self.assertEqual(present[0].get("role"), "Student Council President")
        self.assertEqual(present[0].get("faction"), "Student Council")
        self.assertEqual(present[0].get("club_role"), "President")
        self.assertEqual(present[0].get("grade"), "Senior")
        self.assertEqual(present[0].get("description"), "The diligent Student Council President.")


if __name__ == "__main__":
    unittest.main()
