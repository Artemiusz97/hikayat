import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cogs.adventure import AdventureCog, _get_choice_emoji


class TestOpenHubFreeActionsAndSmartEmojis(unittest.TestCase):

    def test_routine_hub_choices_converted_to_free_actions(self):
        """Verify routine dialogue, board inspect, resting, and travel are converted to Free Actions (stat: NONE, req: 0)."""
        raw_choices = [
            {"label": "Speak with Mara Vey", "stat": "CHA", "requirement": 5},
            {"label": "Consult the elderly archivist", "stat": "INT", "requirement": 6},
            {"label": "Inspect the glowing contract board", "stat": "INT", "requirement": 5},
            {"label": "Sit, drink, and check your gear", "stat": "END", "requirement": 4},
            {"label": "Travel through the hunter trails toward the Royal Capital", "stat": "AGI", "requirement": 6},
        ]

        cleaned = AdventureCog._clean_choices(raw_choices)

        for c in cleaned:
            self.assertEqual(c["stat"], "NONE", f"Expected stat NONE for {c['label']}, got {c['stat']}")
            self.assertEqual(c["requirement"], 0, f"Expected requirement 0 for {c['label']}, got {c['requirement']}")
            self.assertEqual(c["mp_cost"], 0, f"Expected mp_cost 0 for {c['label']}, got {c['mp_cost']}")

    def test_risky_skill_checks_preserved(self):
        """Verify that genuine risky/hostile/challenging actions retain their stat requirements."""
        raw_choices = [
            {"label": "Pickpocket the merchant's purse", "stat": "AGI", "requirement": 8},
            {"label": "Intimidate the hostile thug at the door", "stat": "STR", "requirement": 7},
            {"label": "Disarm the trapped lockbox", "stat": "PER", "requirement": 9},
            {"label": "Decipher the forbidden abyssal curse", "stat": "INT", "requirement": 10},
        ]

        cleaned = AdventureCog._clean_choices(raw_choices)

        self.assertEqual(cleaned[0]["stat"], "AGI")
        self.assertEqual(cleaned[0]["requirement"], 8)

        self.assertEqual(cleaned[1]["stat"], "STR")
        self.assertEqual(cleaned[1]["requirement"], 7)

        self.assertEqual(cleaned[2]["stat"], "PER")
        self.assertEqual(cleaned[2]["requirement"], 9)

        self.assertEqual(cleaned[3]["stat"], "INT")
        self.assertEqual(cleaned[3]["requirement"], 10)

    def test_smart_emoji_mapping(self):
        """Verify context-aware emojis for dialogue, contract boards, resting, and travel."""
        # 1. Dialogue -> 💬
        c_dialogue = {"label": "Speak with Mara Vey", "stat": "NONE", "requirement": 0}
        self.assertEqual(_get_choice_emoji(c_dialogue), "💬")

        c_consult = {"label": "Consult the elderly archivist", "stat": "NONE", "requirement": 0}
        self.assertEqual(_get_choice_emoji(c_consult), "💬")

        # 2. Notice / Contract Board -> 📜
        c_board = {"label": "Inspect the glowing contract board", "stat": "NONE", "requirement": 0}
        self.assertEqual(_get_choice_emoji(c_board), "📜")

        # 3. Rest & Downtime -> ☕
        c_rest = {"label": "Sit, drink, and check your gear", "stat": "NONE", "requirement": 0}
        self.assertEqual(_get_choice_emoji(c_rest), "☕")

        # 4. Travel & Movement -> 🚶
        c_travel = {"label": "Travel through the hunter trails toward Highspire", "stat": "NONE", "requirement": 0}
        self.assertEqual(_get_choice_emoji(c_travel), "🚶")

        # 5. True Skill Checks -> Attribute Icons
        c_int = {"label": "Decipher the forbidden abyssal curse", "stat": "INT", "requirement": 10}
        self.assertEqual(_get_choice_emoji(c_int), "🧠")

        c_per = {"label": "Disarm the trapped lockbox", "stat": "PER", "requirement": 9}
        self.assertEqual(_get_choice_emoji(c_per), "👁️")

        c_str = {"label": "Intimidate the hostile thug", "stat": "STR", "requirement": 7}
        self.assertEqual(_get_choice_emoji(c_str), "💪")

        c_agi = {"label": "Pickpocket the merchant", "stat": "AGI", "requirement": 8}
        self.assertEqual(_get_choice_emoji(c_agi), "🏹")


if __name__ == "__main__":
    unittest.main()
