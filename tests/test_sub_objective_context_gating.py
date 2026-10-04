import unittest
import db
import game_engine
from game_engine import build_scene_escalation_and_consequence_directives


class TestSubObjectiveContextGating(unittest.TestCase):
    def test_out_of_location_sub_objective_receives_transition_guidance_not_completion(self):
        """When player is in Sentry Gallery, Sub-Objective 2 (Adventurers Guild) receives transition guidance, NOT completion directive."""
        session = {
            "id": 99020,
            "current_location": "Royal Capital of Highspire ➔ Royal Summoning Chamber ➔ Outer Sentry Gallery",
            "history": []
        }
        party = []
        actions = [{"label": "Thrust route token toward wall", "check": None}]
        story_quest = {
            "quest_id": "SQ-TEST03",
            "title": "The Appraisal That Cracked the Crown",
            "current_clues": "\n".join(f"• Clue {i}" for i in range(1, 18)),  # 17 clues!
            "sub_objectives": [
                {"id": 1, "archetype": "Forensics", "text": "Summoning chamber forensics", "completed": True},
                {"id": 2, "archetype": "Tactical Recruitment", "text": "Win license at Adventurers Guild Hall against mimic", "completed": False},
                {"id": 3, "archetype": "Merchant Interception", "text": "Track courier in Cobblestone Market Plaza", "completed": False},
            ]
        }

        directives = build_scene_escalation_and_consequence_directives(session, party, actions, story_quest)
        # Should NOT tell LLM to complete Sub-Objective 2 or 3
        self.assertNotIn("SUB-QUEST PROGRESSION GUIDANCE (Sub-Objective #2)", directives)
        self.assertNotIn("SUB-QUEST PROGRESSION GUIDANCE (Sub-Objective #3)", directives)
        self.assertNotIn("completed_sub_quest_ids: [2]", directives)
        self.assertNotIn("completed_sub_quest_ids: [3]", directives)

        # Should give Transition Guidance telling LLM to direct choices toward the Guild or Market
        self.assertIn("SUB-QUEST TRANSITION GUIDANCE", directives)
        self.assertIn("STRICTLY PROHIBITED: Do NOT mark unvisited sub-quests as completed", directives)

    def test_in_location_sub_objective_receives_progression_guidance(self):
        """When player arrives at Guild Hall, Sub-Objective 2 receives progression guidance."""
        session = {
            "id": 99021,
            "current_location": "Royal Capital of Highspire ➔ Adventurers Guild Hall ➔ Quest Board",
            "history": []
        }
        party = []
        actions = [{"label": "Expose the mimic disguised as a quest-board contract", "check": None}]
        story_quest = {
            "quest_id": "SQ-TEST03",
            "title": "The Appraisal That Cracked the Crown",
            "current_clues": "• Clue 1\n• Clue 2\n• Clue 3",
            "sub_objectives": [
                {"id": 1, "archetype": "Forensics", "text": "Summoning chamber forensics", "completed": True},
                {"id": 2, "archetype": "Tactical Recruitment", "text": "Win license at Adventurers Guild Hall against mimic", "completed": False},
                {"id": 3, "archetype": "Merchant Interception", "text": "Track courier in Cobblestone Market Plaza", "completed": False},
            ]
        }

        directives = build_scene_escalation_and_consequence_directives(session, party, actions, story_quest)
        self.assertIn("SUB-QUEST PROGRESSION GUIDANCE (Sub-Objective #2)", directives)
        self.assertIn("completed_sub_quest_ids: [2]", directives)


if __name__ == "__main__":
    unittest.main()
