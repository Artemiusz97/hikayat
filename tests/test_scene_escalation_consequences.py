import unittest
import db
import game_engine
from game_engine import build_scene_escalation_and_consequence_directives, apply_quest_update


class TestSceneEscalationDirectives(unittest.TestCase):
    def test_ticking_clock_detects_prolonged_lingering(self):
        """When history shows 2+ recent turns under active tension, escalation directive is injected."""
        session = {
            "id": 99001,
            "current_location": "Royal Capital of Highspire ➔ Royal Summoning Chamber ➔ Outer Sentry Gallery",
            "history": [
                "[Success] Alicia: Decode the relay's destination -> Sentry patrols outside hammer on the barricaded doors.",
                "[Success] Alicia: Interrogate the command pattern -> Royal defenders redouble their assault on the door.",
            ]
        }
        party = []
        actions = [{"label": "Examine runes", "check": None}]
        story_quest = None

        directives = build_scene_escalation_and_consequence_directives(session, party, actions, story_quest)
        self.assertIn("MANDATORY SCENE ESCALATION & TICKING CLOCK DIRECTIVE", directives)
        self.assertIn("The ticking clock has EXPIRED", directives)

    def test_calm_scene_does_not_trigger_escalation(self):
        """When history is peaceful conversation, no ticking clock escalation is injected."""
        session = {
            "id": 99002,
            "current_location": "School Library ➔ Study Tables",
            "history": [
                "[Success] Artemiusz: Ask Kana about homework -> She smiles and hands over her notes.",
                "[Success] Artemiusz: Thank Kana -> She blushes and looks away.",
            ]
        }
        party = []
        actions = [{"label": "Read textbook", "check": None}]
        story_quest = None

        directives = build_scene_escalation_and_consequence_directives(session, party, actions, story_quest)
        self.assertNotIn("MANDATORY SCENE ESCALATION & TICKING CLOCK DIRECTIVE", directives)

    def test_investigation_saturation_blocks_infinite_clues(self):
        """When 3+ clues already exist, investigation saturation directive is injected."""
        session = {
            "id": 99003,
            "current_location": "Summoning Chamber",
            "history": []
        }
        party = []
        actions = [{"label": "Appraise circle", "check": None}]
        story_quest = {
            "quest_id": "SQ-TEST01",
            "title": "Investigate Chamber",
            "current_clues": "• Clue 1: Distorted sigil\n• Clue 2: Black relay\n• Clue 3: Sentry protocol\n• Clue 4: Loophole",
            "sub_objectives": [
                {"id": 1, "archetype": "Arcane Forensics", "text": "Analyze the circle", "completed": False}
            ]
        }

        directives = build_scene_escalation_and_consequence_directives(session, party, actions, story_quest)
        self.assertIn("INVESTIGATION SATURATED - NO MORE CLUES", directives)
        self.assertIn("Do NOT output further investigation notes", directives)

    def test_sub_objective_contextual_guidance_triggered_when_matching(self):
        """When location matches an uncompleted sub-objective, specific guidance is injected."""
        session = {
            "id": 99004,
            "current_location": "Royal Summoning Chamber ➔ Outer Sentry Gallery",
            "history": []
        }
        party = []
        actions = [{"label": "Escape through the service passage", "check": None}]
        story_quest = {
            "quest_id": "SQ-TEST02",
            "title": "Escape the Chamber",
            "current_clues": "• Clue 1\n• Clue 2\n• Clue 3",
            "sub_objectives": [
                {"id": 1, "archetype": "Royal Infiltration", "text": "Identify sigil in Summoning Chamber and escape", "completed": False},
                {"id": 2, "archetype": "Recruitment", "text": "Get license at Adventurers Guild", "completed": False},
            ]
        }

        directives = build_scene_escalation_and_consequence_directives(session, party, actions, story_quest)
        self.assertIn("SUB-QUEST PROGRESSION GUIDANCE (Sub-Objective #1)", directives)
        self.assertIn("completed_sub_quest_ids: [1]", directives)


class TestSubObjectiveProgressUpdates(unittest.TestCase):
    def setUp(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id=?", (99010,))
            conn.execute("DELETE FROM sessions WHERE turn_order LIKE ?", ("%99010%",))

    def test_progress_string_auto_calculated_as_cleared(self):
        """apply_quest_update automatically updates progress to 'X/Y Cleared' for story quests."""
        uid = 99010
        char = db.create_character(uid, "EscTester", "Mage", "fantasy")
        sess_id = db.create_session(uid, "solo", 1, "vivid", "individual", False, scenario="fantasy")

        db.upsert_quest(
            session_id=sess_id,
            quest_id="SQ-TEST99",
            quest_type="Story Quest",
            title="The Grand Escape",
            objective="Analyze and escape.",
            progress="0/3 Cleared",
            current_clues="• Clue 1\n• Clue 2\n• Clue 3",
            status="Active",
            reward_xp=250,
            reward_gold=50,
            reward_stat_points=0,
            reward_item="",
            is_story_quest=1,
            clues_required=3,
            quest_notes="",
            sub_objectives=[
                {"id": 1, "archetype": "Forensics", "text": "Analyze the circle", "completed": False},
                {"id": 2, "archetype": "Infiltration", "text": "Get license", "completed": False},
                {"id": 3, "archetype": "Diplomacy", "text": "Meet guildmaster", "completed": False},
            ]
        )

        quest_update = {
            "quest_id": "SQ-TEST99",
            "completed_sub_quest_ids": [1],
            "status": "Active"
        }
        apply_quest_update(sess_id, quest_update, party_user_ids=[uid])

        saved = db.get_quest_by_id(sess_id, "SQ-TEST99")
        self.assertIsNotNone(saved)
        self.assertEqual(saved["progress"], "1/3 Cleared")
        sub_objs = saved.get("sub_objectives", [])
        self.assertTrue(sub_objs[0]["completed"])
        self.assertFalse(sub_objs[1]["completed"])
        self.assertFalse(sub_objs[2]["completed"])


if __name__ == "__main__":
    unittest.main()
