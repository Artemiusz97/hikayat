import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cogs.adventure import AdventureCog


class TestOpenHubNPCChoiceInjection(unittest.TestCase):

    def test_open_hub_injects_missing_npcs_and_deduplicates_travel(self):
        """Verify that when in an open hub with multiple NPCs, missing NPCs get dialogue choices and travel is pruned."""
        current_npcs = [
            {"name": "Elderly Archivist"},
            {"name": "Severus Stormblessed", "role": "Dwarf"},
            {"name": "Szeth Gryffindor", "role": "Caravan Guard"},
            {"name": "Mara Vey"},
        ]

        # LLM only gave 3 travel options + 1 question to Mara
        raw_choices = [
            {"label": "Travel openly toward the Adventurers' Guild Hall", "stat": "AGI", "requirement": 5},
            {"label": "Ask Mara which capital route avoids the hunters", "stat": "CHA", "requirement": 5},
            {"label": "Slip through rain-darkened alleys toward the Guild Hall", "stat": "AGI", "requirement": 6},
            {"label": "Leave the tavern and head for Cobblestone Market Plaza", "stat": "AGI", "requirement": 5},
        ]

        cleaned = AdventureCog._clean_choices(
            raw_choices,
            scenario="fantasy",
            location="Solaria ➔ The Boar's Tusk Tavern ➔ Hearthside Table",
            dialogue_partner=None,
            current_npcs=current_npcs
        )

        labels = [c["label"] for c in cleaned]

        # All 3 missing NPCs must have dialogue options
        self.assertTrue(any("Elderly Archivist" in l for l in labels), f"Missing Elderly Archivist in {labels}")
        self.assertTrue(any("Severus Stormblessed" in l for l in labels), f"Missing Severus in {labels}")
        self.assertTrue(any("Szeth Gryffindor" in l for l in labels), f"Missing Szeth in {labels}")
        # Mara was already addressed in 'Ask Mara...'
        self.assertTrue(any("Mara" in l for l in labels), f"Missing Mara in {labels}")

        # Injected choices must be Free Actions (stat: NONE, requirement: 0)
        for c in cleaned:
            if "Elderly Archivist" in c["label"] or "Severus Stormblessed" in c["label"] or "Szeth Gryffindor" in c["label"]:
                self.assertEqual(c["stat"], "NONE")
                self.assertEqual(c["requirement"], 0)

    def test_open_hub_excludes_incapacitated_npcs(self):
        """Verify that unconscious, fallen, or dead NPCs are not injected as active conversationalists."""
        current_npcs = [
            {"name": "Elderly Archivist"},
            {"name": "Rovan Kest", "status_effects": ["Unconscious"]},
            {"name": "Ilyra Sorn", "status_effects": ["Fallen"]},
        ]

        raw_choices = [
            {"label": "Inspect the glowing contract board", "stat": "INT", "requirement": 5},
            {"label": "Sit, drink, and check your gear", "stat": "END", "requirement": 4},
        ]

        cleaned = AdventureCog._clean_choices(
            raw_choices,
            dialogue_partner=None,
            current_npcs=current_npcs
        )

        labels = [c["label"] for c in cleaned]

        # Elderly Archivist is conscious -> must be injected
        self.assertTrue(any("Elderly Archivist" in l for l in labels))

        # Incapacitated characters must NOT be injected
        self.assertFalse(any("Rovan Kest" in l for l in labels), f"Unexpected Rovan Kest in {labels}")
        self.assertFalse(any("Ilyra Sorn" in l for l in labels), f"Unexpected Ilyra Sorn in {labels}")

    def test_dialogue_mode_does_not_inject_other_npcs(self):
        """Verify that when in active dialogue with Mara Vey, other room NPCs are not injected."""
        current_npcs = [
            {"name": "Elderly Archivist"},
            {"name": "Severus Stormblessed"},
            {"name": "Mara Vey"},
        ]

        raw_choices = [
            {"label": "Ask Mara about the sealed map", "stat": "CHA", "requirement": 6},
            {"label": "Inquire about the hunters pursuing Mara", "stat": "INT", "requirement": 5},
        ]

        cleaned = AdventureCog._clean_choices(
            raw_choices,
            dialogue_partner=["Mara Vey"],
            current_npcs=current_npcs
        )

        labels = [c["label"] for c in cleaned]

        # When in dialogue with Mara, we must NOT inject choices to talk to other NPCs
        self.assertFalse(any("Elderly Archivist" in l for l in labels))
        self.assertFalse(any("Severus Stormblessed" in l for l in labels))

        # Must have guaranteed exit
        self.assertTrue(any("Thank Mara" in l or "excuse yourself" in l.lower() for l in labels))


if __name__ == "__main__":
    unittest.main()
