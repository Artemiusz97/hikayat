import unittest
import json
from pathlib import Path
import character_data as cd
from scenario_data import load_scenarios


class TestClassTemplates(unittest.TestCase):
    def setUp(self):
        self.data_dir = Path(__file__).resolve().parent.parent / "data"
        self.class_templates = json.loads((self.data_dir / "class_templates.json").read_text(encoding="utf-8"))
        self.starting_weapons = json.loads((self.data_dir / "starting_weapons.json").read_text(encoding="utf-8"))

    def test_scenario_counts_and_structure(self):
        expected_scenarios = [
            "fantasy", "sci_fi", "cyberpunk", "steampunk",
            "dark_fantasy", "isekai_fantasy", "high_school_drama", "nuclear_post_apocalypse"
        ]
        self.assertEqual(list(self.class_templates.keys()), expected_scenarios)
        self.assertEqual(list(self.starting_weapons.keys()), expected_scenarios)

        for scen, classes in self.class_templates.items():
            self.assertEqual(len(classes), 6, f"Scenario '{scen}' should have exactly 6 classes")
            for c_name, c_data in classes.items():
                self.assertIn("description", c_data, f"Class {c_name} missing description")
                self.assertTrue(len(c_data["description"]) > 0)
                self.assertIn("starting_items", c_data, f"Class {c_name} missing starting_items")
                self.assertIsInstance(c_data["starting_items"], list)
                self.assertTrue(len(c_data["starting_items"]) >= 1)

                self.assertIn("starter_gear", c_data, f"Class {c_name} missing starter_gear")
                gear = c_data["starter_gear"]
                for slot in ("Head", "Top", "Bottom", "Gloves", "Shoes", "Shield"):
                    self.assertIn(slot, gear, f"Class {c_name} missing gear slot {slot}")

    def test_high_school_drama_no_student_council_president(self):
        hs_classes = self.class_templates["high_school_drama"]
        self.assertNotIn("Student Council President", hs_classes)
        self.assertNotIn("Drama Club Star", hs_classes)
        self.assertNotIn("Occult Club Enthusiast", hs_classes)
        self.assertIn("Varsity Athlete", hs_classes)
        self.assertIn("Aspiring Actor", hs_classes)
        self.assertIn("School Journalist", hs_classes)
        self.assertIn("Occult Enthusiast", hs_classes)

    def test_starting_weapons_count(self):
        for scen, weapons in self.starting_weapons.items():
            self.assertEqual(len(weapons), 6, f"Scenario '{scen}' should have 6 starting weapons")

    def test_character_data_helpers(self):
        all_classes = cd.get_all_class_templates()
        self.assertEqual(len(all_classes), 48)

        for scen, classes in self.class_templates.items():
            scen_classes = cd.get_class_templates(scen)
            self.assertEqual(len(scen_classes), 6)
            for c_name in classes:
                gear_map = cd.get_starter_gear_by_class(scen, c_name)
                self.assertIsInstance(gear_map, dict)
                self.assertIn("Top", gear_map)
                self.assertIn("Bottom", gear_map)

                items = cd.get_starting_items(scen, c_name)
                self.assertIsInstance(items, list)
                self.assertTrue(len(items) >= 1)

            weapons = cd.get_starting_weapons(scen)
            self.assertEqual(len(weapons), 6)


    def test_equipment_gender_and_race_separation(self):
        # 1. School Journalist: Male gets Smart Slacks, Female gets Pencil Skirt
        male_journo = cd.get_starter_gear_by_class("high_school_drama", "School Journalist", gender="Male", race="Human")
        female_journo = cd.get_starter_gear_by_class("high_school_drama", "School Journalist", gender="Female", race="Human")
        self.assertEqual(male_journo["Bottom"][0], "Smart Slacks")
        self.assertEqual(female_journo["Bottom"][0], "Pencil Skirt")
        self.assertNotIn("/", male_journo["Bottom"][0])
        self.assertNotIn("skirt", male_journo["Bottom"][0].lower())

        # 2. Occult Enthusiast: Male gets Dark Trousers, Female gets Pleated Plaid Skirt
        male_occult = cd.get_starter_gear_by_class("high_school_drama", "Occult Enthusiast", gender="Male", race="Human")
        female_occult = cd.get_starter_gear_by_class("high_school_drama", "Occult Enthusiast", gender="Female", race="Human")
        self.assertEqual(male_occult["Bottom"][0], "Dark Trousers")
        self.assertEqual(female_occult["Bottom"][0], "Pleated Plaid Skirt")
        self.assertNotIn("/", male_occult["Bottom"][0])
        self.assertNotIn("skirt", male_occult["Bottom"][0].lower())

        # 3. Archmage & Hex Weaver: Male gets trousers
        male_archmage = cd.get_starter_gear_by_class("fantasy", "Archmage", gender="Male", race="Human")
        female_archmage = cd.get_starter_gear_by_class("fantasy", "Archmage", gender="Female", race="Human")
        self.assertEqual(male_archmage["Bottom"][0], "Enchanted Robe Trousers")
        self.assertEqual(female_archmage["Bottom"][0], "Enchanted Robe Skirt")

        # 4. Humanoid tailless race strips tail-slotted prefix
        tail_gear = cd.get_starter_gear_by_class("high_school_drama", "Varsity Athlete", gender="Male", race="Human")
        for slot, entry in tail_gear.items():
            if entry:
                self.assertNotIn("tail-slotted", entry[0].lower())


    def test_apply_adventure_loadout_all_template_classes(self):
        import db
        import uuid
        test_uid = 888800000 + (uuid.uuid4().int % 100000)
        db.create_character(test_uid, "Tester", "Male", "Human")

        scenarios_to_test = list(self.class_templates.keys()) + ["nsfw_isekai_fantasy"]
        for scen in scenarios_to_test:
            classes = cd.get_class_templates(scen)
            for c_name in classes:
                gear_map = cd.get_starter_gear_by_class(scen, c_name, gender="Male", race="Human")
                starting_items = cd.get_starting_items(scen, c_name)
                # Should apply without raising ValueError (e.g. Combat body armor in non-Armor slots)
                db.apply_adventure_loadout(
                    user_id=test_uid,
                    scenario=scen,
                    char_class=c_name,
                    gear_map=gear_map,
                    starting_items=starting_items
                )


if __name__ == "__main__":
    unittest.main()

