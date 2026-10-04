import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cogs.adventure import (
    AdventureCog,
    ChoiceDropdown,
    _strip_leading_emojis,
    _get_choice_emoji,
    _choice_button_label
)


class TestChoiceEmojiDeduplication(unittest.TestCase):

    def test_strip_leading_emojis(self):
        """Test stripping leading emojis, symbols, and bracketed prefixes."""
        self.assertEqual(_strip_leading_emojis("🧭 Scout the archway perimeter"), "Scout the archway perimeter")
        self.assertEqual(_strip_leading_emojis("🔮 Decipher the glowing inscriptions"), "Decipher the glowing inscriptions")
        self.assertEqual(_strip_leading_emojis("🎒 Prepare expedition equipment"), "Prepare expedition equipment")
        self.assertEqual(_strip_leading_emojis("🚪 Enter the awakening first chamber"), "Enter the awakening first chamber")
        self.assertEqual(_strip_leading_emojis("💬 Speak with Mara Vey"), "Speak with Mara Vey")
        self.assertEqual(_strip_leading_emojis("📜 [INT] Read the contract board"), "Read the contract board")
        self.assertEqual(_strip_leading_emojis("👁️ 🧭 Scout the archway perimeter"), "Scout the archway perimeter")
        self.assertEqual(_strip_leading_emojis("Normal choice text without emojis"), "Normal choice text without emojis")

    def test_clean_choices_strips_leading_emojis(self):
        """Test that AdventureCog._clean_choices removes leading emojis from all choices."""
        raw_choices = [
            {"label": "🧭 Scout the archway perimeter", "stat": "PER", "requirement": 6},
            {"label": "🔮 Decipher the glowing inscriptions", "stat": "INT", "requirement": 6, "mp_cost": 2},
            {"label": "🎒 Prepare expedition equipment", "stat": "NONE", "requirement": 0},
            {"label": "🚪 Enter the awakening first chamber", "stat": "END", "requirement": 5}
        ]

        cleaned = AdventureCog._clean_choices(raw_choices)
        self.assertEqual(cleaned[0]["label"], "Scout the archway perimeter")
        self.assertEqual(cleaned[1]["label"], "Decipher the glowing inscriptions")
        self.assertEqual(cleaned[2]["label"], "Prepare expedition equipment")
        self.assertEqual(cleaned[3]["label"], "Enter the awakening first chamber")

    def test_choice_dropdown_options_have_single_emoji(self):
        """Test that ChoiceDropdown generates select options with clean labels and distinct option emojis."""
        choices = [
            {"label": "🧭 Scout the archway perimeter", "stat": "PER", "requirement": 6},
            {"label": "🔮 Decipher the glowing inscriptions", "stat": "INT", "requirement": 6, "mp_cost": 2},
            {"label": "🎒 Prepare expedition equipment", "stat": "NONE", "requirement": 0},
            {"label": "🚪 Enter the awakening first chamber", "stat": "END", "requirement": 5}
        ]

        dropdown = ChoiceDropdown(
            cog=None,
            session_id=12345,
            turn_user_id=999,
            choices=choices,
            actor_char={"user_id": 999, "name": "Alice", "per_": 7, "int_": 8, "end_": 6}
        )

        options = dropdown.options
        self.assertEqual(len(options), 4)

        # Option 1: PER check
        self.assertEqual(str(options[0].emoji), "👁️")
        self.assertNotIn("🧭", options[0].label)
        self.assertIn("Scout the archway perimeter", options[0].label)

        # Option 2: INT check with MP cost in description
        self.assertEqual(str(options[1].emoji), "🧠")
        self.assertNotIn("🔮", options[1].label)
        self.assertIn("Decipher the glowing", options[1].label)
        self.assertIn("2 MP", options[1].description)

        # Option 3: Free Action
        self.assertEqual(str(options[2].emoji), "🎒")
        self.assertNotIn("🎒", options[2].label)
        self.assertIn("Prepare expedition equipment", options[2].label)

        # Option 4: END check
        self.assertEqual(str(options[3].emoji), "🛡️")
        self.assertNotIn("🚪", options[3].label)
        self.assertIn("Enter the awakening first", options[3].label)

    def test_choice_button_label_strips_emojis(self):
        """Test that button label formatter strips leading emojis."""
        choice = {"label": "🧭 Scout the archway perimeter"}
        lbl = _choice_button_label(1, choice, prefix="100% ", show_percentages=False)
        self.assertNotIn("🧭", lbl)
        self.assertEqual(lbl, "Scout the archway perimeter")


if __name__ == "__main__":
    unittest.main()
