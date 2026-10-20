import unittest
from unittest.mock import MagicMock
from game_engine.choices_cleaner import clean_choices_impl, sanitize_and_diversify_choices
from mechanics.narrative.choice_generator import get_scenario_dialogue_fallbacks


class TestChoiceReplenishmentAndTransitionDiversity(unittest.TestCase):
    """Test suite verifying substantive choice replenishment, scene transition diversity,
    and genre-aware dialogue fallbacks."""

    def test_escort_departure_replenishes_classroom_choices(self):
        """Simulate Turn 2: Dr. Raymond Satou departs as player arrives in Room 201.
        Choices targeting Raymond are pruned, and the engine replenishes substantive choices
        addressing Yang Ito and present classmates."""
        raw_choices = [
            {"label": "Ask Dr. Raymond Satou about the chemistry experiment", "stat": "INT", "requirement": 6},
            {"label": "Joke with Raymond about his oversized fennec ears", "stat": "CHA", "requirement": 6},
            {"label": "Check your phone messages and campus news feed quietly", "stat": "CHA", "requirement": 6},
            {"label": "Thank Dr. Raymond, excuse yourself, and step away", "stat": "NONE", "requirement": 0},
        ]
        present_npcs = [
            {"name": "Julie Yamada", "role": "Class Clown & Slacker"},
            {"name": "Ji-hoon Sterling", "role": "Council Representative"},
            {"name": "Yang Ito", "role": ""},
            {"name": "Archie Nakamura", "role": "Lieutenant"},
            {"name": "Mio Kobayashi", "role": ""},
        ]
        departed = ["Dr. Raymond Satou"]
        scenario = "nsfw_furry_high_school_drama"
        location = "Northwood Preparatory Academy ➔ Room 201 (Homeroom) ➔ Artem's Desk"
        char = {"name": "Artem", "class": "Student"}

        cleaned = sanitize_and_diversify_choices(
            choices=raw_choices,
            scenario=scenario,
            location=location,
            char=char,
            dialogue_partner="Yang Ito",
            current_npcs=present_npcs,
            departed_npcs=departed,
        )

        # 1. No choices targeting Dr. Raymond Satou or Raymond survived
        for c in cleaned:
            lbl = c.get("label", "").lower()
            self.assertNotIn("dr. raymond", lbl)
            self.assertNotIn("raymond", lbl)

        # 2. Exit choice exists at the end
        exit_choices = [c for c in cleaned if c.get("stat") in ("NONE", "FREE") and c.get("requirement", 0) == 0]
        self.assertGreaterEqual(len(exit_choices), 1)
        self.assertTrue("excuse yourself" in exit_choices[-1]["label"].lower() or "look around" in exit_choices[-1]["label"].lower())

        # 3. Substantive choices count is at least 3
        substantive = [c for c in cleaned if c not in exit_choices]
        self.assertGreaterEqual(len(substantive), 3)

        # 4. Total choices count is at least 4 (substantive + exit)
        self.assertGreaterEqual(len(cleaned), 4)

        # 5. At least one substantive choice addresses Yang Ito or a classroom bystander
        labels_joined = " ".join(c.get("label", "") for c in cleaned)
        self.assertTrue(
            "Yang Ito" in labels_joined or "Julie" in labels_joined or "Ji-hoon" in labels_joined or "desk" in labels_joined.lower(),
            f"Expected classroom interaction in choices, got: {[c.get('label') for c in cleaned]}"
        )

    def test_substantive_count_independent_of_exit_and_free_actions(self):
        """Verifies that having an exit choice and a smartphone contact exchange does NOT block
        replenishment if there are fewer than 3 substantive actions."""
        raw_choices = [
            {"label": "Check your phone messages and campus news feed quietly", "stat": "CHA", "requirement": 6},
            {"label": "📱 Ask for Yang Ito's Phone Number / Contact Info", "stat": "CHA", "requirement": 16},
            {"label": "Thank everyone, excuse yourself, and look around the room", "stat": "NONE", "requirement": 0},
        ]
        present_npcs = [
            {"name": "Yang Ito", "role": ""},
            {"name": "Julie Yamada", "role": "Student"},
        ]
        scenario = "nsfw_furry_high_school_drama"
        location = "Northwood Preparatory Academy ➔ Room 201 (Homeroom)"
        char = {"name": "Artem", "class": "Student"}

        cleaned = sanitize_and_diversify_choices(
            choices=raw_choices,
            scenario=scenario,
            location=location,
            char=char,
            dialogue_partner="Yang Ito",
            current_npcs=present_npcs,
        )

        substantive = [c for c in cleaned if c.get("stat") not in ("NONE", "FREE") or c.get("requirement", 0) > 0]
        self.assertGreaterEqual(
            len(substantive),
            3,
            f"Expected at least 3 substantive choices, got {len(substantive)}: {[c.get('label') for c in cleaned]}"
        )
        self.assertGreaterEqual(len(cleaned), 4)

    def test_genre_aware_dialogue_fallbacks_highschool_vs_fantasy(self):
        """Verifies that dialogue fallbacks reflect the genre rather than generic diplomatic treaties."""
        hs_fallbacks = get_scenario_dialogue_fallbacks(
            partner_name="Yang Ito",
            scenario="high_school",
            present_bystanders=[{"name": "Julie Yamada", "role": "Student"}],
            location="Room 201 (Homeroom) ➔ Desk",
        )
        hs_labels = " ".join(f["label"] for f in hs_fallbacks)
        self.assertNotIn("Negotiate favorable terms", hs_labels)
        self.assertNotIn("mutual cooperation", hs_labels)
        self.assertTrue("Yang Ito" in hs_labels)
        self.assertTrue(any(kw in hs_labels for kw in ("joke", "classes", "homeroom", "mind")))

        fan_fallbacks = get_scenario_dialogue_fallbacks(
            partner_name="Lord Charles",
            scenario="fantasy",
        )
        fan_labels = " ".join(f["label"] for f in fan_fallbacks)
        self.assertTrue("Lord Charles" in fan_labels)
        self.assertTrue(any(kw in fan_labels for kw in ("journey", "lore", "guild", "demeanor")))


if __name__ == "__main__":
    unittest.main()
