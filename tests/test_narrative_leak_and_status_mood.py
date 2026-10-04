import unittest
import db
import game_engine
from cogs.adventure.embeds import _format_tracker_entity


class TestNarrativeLeakAndStatusMood(unittest.TestCase):
    def test_sanitize_meta_objective_leaks_in_narration_and_dialogue(self):
        """Verify that leaked engine quest tracking labels are replaced with in-universe narrative phrasing."""
        # 1. Exact user screenshot dialogue
        raw_text_1 = (
            'Artem glances at Yea-ji, then back at the rabbit girl. "This is exactly what we needed," '
            'he says. Yea-ji closes her notebook and offers a small smile. "Thank you for speaking up. '
            'You\'ve given us a strong lead on Sub-Objective #2." She then turns to Artem.'
        )
        cleaned_1 = game_engine.sanitize_meta_objective_leaks(raw_text_1)
        self.assertNotIn("Sub-Objective #2", cleaned_1)
        self.assertNotIn("Sub-Objective", cleaned_1)
        self.assertIn("strong lead on the investigation", cleaned_1)

        # 2. Alternative phrasing
        raw_text_2 = "We need to focus on Sub-Objective #1 before evening."
        cleaned_2 = game_engine.sanitize_meta_objective_leaks(raw_text_2)
        self.assertNotIn("Sub-Objective #1", cleaned_2)
        self.assertIn("focus on the objective", cleaned_2)

        raw_text_3 = "Sub-Objective #3 has been achieved."
        cleaned_3 = game_engine.sanitize_meta_objective_leaks(raw_text_3)
        self.assertNotIn("Sub-Objective #3", cleaned_3)
        self.assertIn("The investigation has been achieved", cleaned_3)

        raw_text_4 = "That gives us a vital clue for Sub-Quest #2."
        cleaned_4 = game_engine.sanitize_meta_objective_leaks(raw_text_4)
        self.assertNotIn("Sub-Quest #2", cleaned_4)
        self.assertIn("clue for the investigation", cleaned_4)

    def test_status_mood_and_neutral_default_for_noncombat_characters(self):
        """Verify that non-combat characters (like Aria Sato) receive Status: Neutral when unperturbed,
        and dynamically display emotional moods (e.g. Flustered, Angry, Scared, Aroused)."""
        # 1. Healthy/unperturbed NPC with empty status_effects (Aria Sato case)
        aria = {
            "name": "Aria Sato",
            "role": "",
            "level": None,
            "hp": None,
            "status_effects": []
        }
        aria_formatted = _format_tracker_entity(aria, show_vitals=False)
        self.assertIn("**Aria Sato**", aria_formatted)
        self.assertIn("Status: Neutral", aria_formatted)

        # 2. NPC with dynamic emotional mood in status_effects
        aria_flustered = {
            "name": "Aria Sato",
            "role": "",
            "level": None,
            "hp": None,
            "status_effects": ["Flustered"]
        }
        flustered_formatted = _format_tracker_entity(aria_flustered, show_vitals=False)
        self.assertIn("**Aria Sato**", flustered_formatted)
        self.assertIn("Status: Flustered", flustered_formatted)

        # 3. NPC with mood specified in mood field
        aria_angry = {
            "name": "Aria Sato",
            "role": "Student",
            "level": None,
            "hp": None,
            "mood": "Angry",
            "status_effects": []
        }
        angry_formatted = _format_tracker_entity(aria_angry, show_vitals=False)
        self.assertIn("**Aria Sato**", angry_formatted)
        self.assertIn("(Student)", angry_formatted)
        self.assertIn("Status: Angry", angry_formatted)

        # 4. NPC with both tactical status and emotional mood
        combat_npc = {
            "name": "Valerius",
            "role": "Warrior",
            "level": 5,
            "hp": 80,
            "max_hp": 100,
            "mp": 20,
            "max_mp": 20,
            "mood": "Enraged",
            "status_effects": ["Bleeding"]
        }
        combat_formatted = _format_tracker_entity(combat_npc, show_vitals=True)
        self.assertIn("Lvl 5", combat_formatted)
        self.assertIn("**Valerius**", combat_formatted)
        self.assertIn("❤️ 80/100", combat_formatted)
        self.assertIn("Status: Bleeding, Enraged", combat_formatted)


if __name__ == "__main__":
    unittest.main()
