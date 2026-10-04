import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
from cogs.adventure import AdventureCog


class TestConversationLockingAndChoiceFiltering(unittest.TestCase):

    def test_conversation_lock_filters_other_npcs_travel_and_resting(self):
        """Verify that when in dialogue with Seraphine Quill, options to talk to Gate Guards, travel, or rest are filtered out."""
        raw_choices = [
            {"label": "Present the violet core and command rune, then negotiate a sanctioned ruin-mapping contract", "stat": "CHA", "requirement": 8},
            {"label": "Speak with Guildmaster Seraphine Quill about the faction motives hidden inside each contract", "stat": "INT", "requirement": 7},
            {"label": "Question the regrouped gate guards about surviving witnesses and the construct's final command", "stat": "PER", "requirement": 6},
            {"label": "Travel toward the Primordial Sanctuary Woods and seek Elder Rowan-of-the-First-Bough", "stat": "AGI", "requirement": 5},
            {"label": "Rest beside the muster chamber's ward brazier and review the contracts before departing", "stat": "NONE", "requirement": 0},
        ]
        current_npcs = [
            {"name": "Gate Guards", "status_effects": ["Scattered"]},
            {"name": "Seraphine Quill", "role": "Guildmaster"},
            {"name": "Gate-Captain Maelis Vorn", "role": "Captain"},
        ]

        cleaned = AdventureCog._clean_choices(
            raw_choices,
            dialogue_partner=["Seraphine Quill"],
            current_npcs=current_npcs
        )
        labels = [c["label"] for c in cleaned]

        # In-conversation choices with Seraphine are preserved
        self.assertTrue(any("Present the violet core" in l for l in labels))
        self.assertTrue(any("Inquire about the faction motives" in l or "faction motives" in l for l in labels))

        # Other NPCs, travel, and resting are filtered out!
        self.assertFalse(any("gate guards" in l.lower() for l in labels))
        self.assertFalse(any("primordial sanctuary" in l.lower() for l in labels))
        self.assertFalse(any("rest beside" in l.lower() for l in labels))

        # Exactly 1 clean conversational exit choice exists
        exit_choices = [c for c in cleaned if c["stat"] == "NONE" and c["requirement"] == 0]
        self.assertEqual(len(exit_choices), 1)
        self.assertIn("Thank Seraphine Quill", exit_choices[0]["label"])

    def test_conversation_lock_generates_fallbacks_if_all_choices_were_unrelated(self):
        """Verify that if LLM generated only travel and room search choices, dialogue fallbacks are created."""
        raw_choices = [
            {"label": "Travel toward the mountain pass", "stat": "AGI", "requirement": 5},
            {"label": "Search the guild notice board", "stat": "LUK", "requirement": 6},
            {"label": "Rest beside the fire", "stat": "NONE", "requirement": 0},
        ]
        current_npcs = [{"name": "Archivist Nerys Pell"}]

        cleaned = AdventureCog._clean_choices(
            raw_choices,
            dialogue_partner=["Archivist Nerys Pell"],
            current_npcs=current_npcs
        )
        labels = [c["label"] for c in cleaned]

        # No travel or rest choices
        self.assertFalse(any("mountain pass" in l.lower() for l in labels))
        self.assertFalse(any("notice board" in l.lower() for l in labels))
        self.assertFalse(any("rest beside" in l.lower() for l in labels))

        # In-dialogue fallbacks with Nerys Pell were injected
        self.assertTrue(any("Archivist Nerys Pell" in l or "Nerys" in l for l in labels))
        self.assertTrue(any("Thank Archivist Nerys Pell" in l for l in labels))

    def test_open_hub_mode_allows_talking_to_all_npcs_travel_and_resting(self):
        """Verify that outside of dialogue (dialogue_partner=None), all NPCs, travel, and resting choices are available."""
        raw_choices = [
            {"label": "Speak with Guildmaster Seraphine Quill", "stat": "NONE", "requirement": 0},
            {"label": "Question the regrouped gate guards", "stat": "NONE", "requirement": 0},
            {"label": "Travel toward the Primordial Sanctuary", "stat": "NONE", "requirement": 0},
            {"label": "Rest beside the muster chamber brazier", "stat": "NONE", "requirement": 0},
        ]
        current_npcs = [
            {"name": "Gate Guards"},
            {"name": "Seraphine Quill"},
        ]

        cleaned = AdventureCog._clean_choices(
            raw_choices,
            dialogue_partner=None,
            current_npcs=current_npcs
        )
        labels = [c["label"] for c in cleaned]

        self.assertTrue(any("Seraphine" in l for l in labels))
        self.assertTrue(any("gate guards" in l.lower() for l in labels))
        self.assertTrue(any("Primordial Sanctuary" in l for l in labels))
        self.assertTrue(any("Rest beside" in l for l in labels))


if __name__ == "__main__":
    unittest.main()
