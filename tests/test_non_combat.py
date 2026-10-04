import unittest
import scenario_data
from mechanics.social.attributes import calculate_combat_attributes
from mechanics.combat.equipment import generate_random_equipment, format_equipment_card, parse_equipment_metadata

class TestNonCombatScenarios(unittest.TestCase):
    def test_non_combat_tag_detection(self):
        # High School scenarios have non_combat tag
        self.assertTrue(scenario_data.is_non_combat_scenario("high_school_drama"))
        self.assertTrue(scenario_data.is_non_combat_scenario("nsfw_high_school_drama"))
        self.assertTrue(scenario_data.is_non_combat_scenario("furry_high_school_drama"))
        self.assertTrue(scenario_data.is_non_combat_scenario("nsfw_furry_high_school_drama"))
        self.assertFalse(scenario_data.is_combat_enabled("high_school_drama"))

        # Fantasy and Sci-Fi are combat enabled
        self.assertFalse(scenario_data.is_non_combat_scenario("fantasy"))
        self.assertTrue(scenario_data.is_combat_enabled("fantasy"))
        self.assertTrue(scenario_data.is_combat_enabled("sci_fi"))

    def test_custom_non_combat_tag_resolution(self):
        # Combinations with non-combat tag
        custom_key = scenario_data.resolve_scenario_or_custom_key(["fantasy", "non-combat"])
        self.assertTrue(scenario_data.is_non_combat_scenario(custom_key))
        self.assertFalse(scenario_data.is_combat_enabled(custom_key))

    def test_cosmetic_equipment_generation(self):
        # High School Drama item generation
        item = generate_random_equipment(scenario="high_school_drama", slot="Weapon")
        meta = item["metadata"]
        
        self.assertTrue(meta.get("is_cosmetic"))
        self.assertEqual(meta.get("stat_modifiers"), {})
        self.assertIn("Non-Combat", meta.get("tags", []))

        # Inspect card formatting
        card = format_equipment_card(meta)
        self.assertIn("Cosmetic & Narrative Flair", card)
        self.assertNotIn("⚔️ ATK +", card)

    def test_combat_attributes_disabled_in_non_combat(self):
        char = {
            "name": "Student", "scenario": "high_school_drama",
            "str_": 8, "per_": 7, "end_": 6, "cha": 9,
            "int_": 8, "agi": 6, "luk": 5
        }
        item = generate_random_equipment(scenario="high_school_drama", slot="Weapon")
        
        attrs = calculate_combat_attributes(char, [item], scenario="high_school_drama")
        self.assertTrue(attrs.get("is_non_combat"))
        self.assertEqual(attrs.get("atk"), 0)
        self.assertEqual(attrs.get("innate_phys_dt"), 0)
        self.assertEqual(attrs.get("matk"), 0)
        self.assertEqual(attrs.get("innate_magic_dt"), 0)
