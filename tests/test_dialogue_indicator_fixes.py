import unittest
import character_data as cd
import game_engine

class TestDialogueIndicatorAndPresenceFixes(unittest.TestCase):
    def test_vocal_verbs_detected(self):
        """Verify vocal verbs like rumbles, growls, barks, drawls are detected."""
        text = (
            "Diana Yamada doesn't look up from whatever datapad she's flicking through, "
            "though she rumbles low enough that her voice vibrates in the small cabin. "
            "'Don't go getting him all sentimental, Sterling. He's got work to do.'"
        )
        npcs = [{"name": "Diana Yamada"}, {"name": "Henry Sterling"}]
        speakers = game_engine.extract_speaking_npcs_from_narrative(text, npcs)
        self.assertIn("Diana Yamada", speakers)

    def test_single_quote_paragraph_action_beat(self):
        """Verify single quotes in action-beat paragraphs are recognized."""
        text = (
            "Henry Sterling shakes his head with a tired, amused twitch of his lips.\n"
            "'Well, Artem,' he says, leaning back slightly in his chair."
        )
        npcs = [{"name": "Henry Sterling"}]
        speakers = game_engine.extract_speaking_npcs_from_narrative(text, npcs)
        self.assertIn("Henry Sterling", speakers)

    def test_attendance_tags_filtered_from_status_effects(self):
        """Verify Present, Absent, Nearby are stripped from RPG condition status effects."""
        raw = ["Present", "Bleeding", "Absent", "Stunned", "nearby", ""]
        sanitized = cd.sanitize_status_effects(raw)
        self.assertEqual(sanitized, ["Bleeding", "Stunned"])

    def test_extract_scene_fields_evaluates_combined_narrative(self):
        """Verify extract_scene_fields catches speaking NPCs from outcome_narrative when partner_arg was empty."""
        outcome = {
            "dialogue_partners": [],
            "outcome_narrative": "Henry Sterling simply steps into your line. 'Whoa—whoa—whoa,' he says.",
            "next_narrative": "The hallway falls quiet.",
            "npcs_present": [{"name": "Henry Sterling"}],
            "choices": ["Listen to Henry", "Push past him"]
        }
        choices, next_nar, title, partner_arg, npcs_arg = game_engine.extract_scene_fields(outcome)
        self.assertEqual(partner_arg, "Henry Sterling")

if __name__ == "__main__":
    unittest.main()
