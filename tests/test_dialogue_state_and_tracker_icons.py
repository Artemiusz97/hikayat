import os
import sys
import unittest
from unittest.mock import patch, AsyncMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
import game_engine
from cogs.adventure import AdventureCog, _format_tracker_entity, _is_dialogue_partner


class TestDialogueStateAndTrackerIcons(unittest.TestCase):

    def test_is_dialogue_partner_token_matching(self):
        """Verify token matching for multi-word NPC names and dialogue partners."""
        self.assertTrue(_is_dialogue_partner("Elder Maerwyn Rootspeaker", ["Maerwyn"]))
        self.assertTrue(_is_dialogue_partner("Elder Maerwyn Rootspeaker", ["Elder Maerwyn Rootspeaker"]))
        self.assertTrue(_is_dialogue_partner("Elder Maerwyn Rootspeaker", ["Rootspeaker"]))
        self.assertTrue(_is_dialogue_partner("Maerwyn", ["Elder Maerwyn Rootspeaker"]))
        self.assertFalse(_is_dialogue_partner("Valerius Ironclad", ["Maerwyn"]))

    def test_format_tracker_entity_shows_speech_bubble_icon(self):
        """Verify that an active dialogue partner gets the 💬 icon prepended."""
        entity = {"name": "Elder Maerwyn Rootspeaker", "role": "Druid Elder"}
        
        # When in dialogue
        formatted_conv = _format_tracker_entity(entity, dialogue_partners=["Elder Maerwyn Rootspeaker"])
        self.assertIn("💬 **Elder Maerwyn Rootspeaker**", formatted_conv)

        # When not in dialogue
        formatted_idle = _format_tracker_entity(entity, dialogue_partners=[])
        self.assertNotIn("💬", formatted_idle)
        self.assertIn("**Elder Maerwyn Rootspeaker**", formatted_idle)

    def test_clean_choices_does_not_inject_duplicate_speak_option(self):
        """Verify that _clean_choices does not inject 'Speak with Elder Maerwyn Rootspeaker' when dialogue choices already exist."""
        raw_choices = [
            {"label": "Describe the blue fire and Seventh Sigil in precise detail", "stat": "INT", "requirement": 6},
            {"label": "Appeal to Maerwyn's duty by explaining how corruption threatens the roots", "stat": "CHA", "requirement": 5},
            {"label": "Study Maerwyn's expression for signs of concealed knowledge", "stat": "PER", "requirement": 6},
            {"label": "Thank Elder Maerwyn, say goodbye, and step back from the bough-court", "stat": "NONE", "requirement": 0}
        ]
        current_npcs = [{"name": "Elder Maerwyn Rootspeaker", "role": "Druid Elder"}]

        cleaned = AdventureCog._clean_choices(
            raw_choices,
            scenario="fantasy",
            location="Forest of Sunlit Vale ➔ Sunken Moonwell ➔ Rootbound Ascent",
            current_npcs=current_npcs,
            dialogue_partner="Elder Maerwyn Rootspeaker"
        )

        labels = [c["label"] for c in cleaned]
        
        # Must NOT inject generic 'Speak with Elder Maerwyn Rootspeaker'
        self.assertNotIn("Speak with Elder Maerwyn Rootspeaker", labels)
        self.assertEqual(len([l for l in labels if "Maerwyn" in l or "Seventh Sigil" in l]), 4)


if __name__ == "__main__":
    unittest.main()
