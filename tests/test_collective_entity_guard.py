import unittest
import db
import game_engine
import namegen
from mechanics.narrative.intent import classify_action_intent, IntentCategory
from mechanics.social.relationships import is_contact_eligible
from db.social import _extract_role_and_affiliation_from_text


class TestCollectiveEntityGuard(unittest.TestCase):
    def setUp(self):
        self.session_id = db.create_session(
            host_user_id=1,
            mode="solo",
            capacity=1,
            verbosity="vivid",
            dialogue_mode="individual",
            image_gen_enabled=False,
            scenario="high_school_drama"
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM lorebook WHERE session_id = ?", (self.session_id,))

    def test_collective_entity_recognition(self):
        """Verify collective group nouns and plurals are recognized as collective entities."""
        self.assertTrue(namegen.is_collective_entity_name("students"))
        self.assertTrue(namegen.is_collective_entity_name("patrons"))
        self.assertTrue(namegen.is_collective_entity_name("bystanders"))
        self.assertTrue(namegen.is_collective_entity_name("crowd"))
        self.assertTrue(namegen.is_collective_entity_name("cluster of students"))
        self.assertTrue(namegen.is_collective_entity_name("group of students"))
        self.assertTrue(namegen.is_collective_entity_name("guards"))
        self.assertTrue(namegen.is_collective_entity_name("the students"))

        self.assertFalse(namegen.is_collective_entity_name("student"))
        self.assertFalse(namegen.is_collective_entity_name("Maya Vance"))
        self.assertFalse(namegen.is_collective_entity_name("Artemiusz"))

    def test_intent_classification_does_not_extract_collective_target_npc(self):
        """Action 'Step into main café and greet students' must NOT extract 'students' as an individual target NPC."""
        action = "Step into main café and greet students"
        parsed = classify_action_intent(action)
        self.assertEqual(parsed.category, IntentCategory.DIALOGUE_INIT)
        self.assertNotEqual(parsed.target_entity, "students")
        self.assertEqual(parsed.target_entity or "", "")

    def test_compute_dialogue_intent_ignores_collective_entities(self):
        """_compute_dialogue_intent must NOT set a collective noun as a dialogue partner."""
        from game_engine.turn.dialogue import _compute_dialogue_intent
        session = db.get_session(self.session_id)
        actions = [{"label": "Step into main café and greet students"}]
        new_partners, has_exited = _compute_dialogue_intent(session, actions)
        self.assertNotIn("students", new_partners)
        self.assertNotIn("cluster of students", new_partners)

    def test_contact_eligibility_rejects_collective_entities(self):
        """Collective entities must never be eligible as phone/directory contacts."""
        self.assertFalse(is_contact_eligible("students", scenario="high_school_drama"))
        self.assertFalse(is_contact_eligible("cluster of students", scenario="high_school_drama"))
        self.assertFalse(is_contact_eligible("patrons", scenario="high_school_drama"))
        self.assertFalse(is_contact_eligible("crowd", scenario="fantasy"))

        self.assertTrue(is_contact_eligible("Maya Vance", role="Student", scenario="high_school_drama"))

    def test_upsert_contact_rejects_collective_entities(self):
        """db.upsert_contact must reject collective entities and return empty dict."""
        res = db.upsert_contact(
            session_id=self.session_id,
            npc_id="students",
            name="students",
            character_id=1,
            delta_score=1
        )
        self.assertEqual(res, {})
        contact = db.get_contact(self.session_id, "students")
        self.assertIsNone(contact)

    def test_process_scene_npcs_filters_collective_entities(self):
        """process_scene_npcs must filter collective entities from npcs_present."""
        session = db.get_session(self.session_id)
        result = {
            "npcs_present": [
                {"name": "students"},
                {"name": "Mila Vance"}
            ],
            "outcome_narrative": "Artemiusz greets the students. Mila Vance smiles and waves back.",
            "next_narrative": "Mila Vance leans forward with a warm smile."
        }
        loc = "Manga & Brew Café ➔ Window Seat Table"
        final_npcs = game_engine.process_scene_npcs(result, session, new_loc=loc, old_loc=loc)
        names = [n["name"] for n in final_npcs]
        self.assertIn("Mila Vance", names)
        self.assertNotIn("students", names)

    def test_description_extraction_does_not_steal_player_action(self):
        """_extract_role_and_affiliation_from_text must not assign the player's perception sentence to an NPC."""
        narrative = (
            "Artemiusz steps past the café's glass doors. He adjusts his newsboy cap and scans the room, "
            "spotting a cluster of students near the window seats, their laughter cutting through the smell of roasted beans. "
            "Mila Vance is a cheerful high school senior sitting near the window."
        )
        extracted = _extract_role_and_affiliation_from_text(
            name="students",
            char_text="",
            scene_narrative=narrative,
            scenario="high_school_drama"
        )
        # It must not steal Artemiusz adjusting his newsboy cap
        desc = extracted.get("description", "")
        self.assertNotIn("newsboy cap", desc)
        self.assertNotIn("He adjusts", desc)


if __name__ == "__main__":
    unittest.main()
