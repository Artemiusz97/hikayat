import unittest
import uuid
import character_data as cd
from scenario_data import is_non_combat_scenario
from mechanics.combat.items import generate_starter_equipment_loadout
from mechanics.combat.items.clothing import generate_random_clothing
import db


class TestHighSchoolAndNonCombatLoadout(unittest.TestCase):
    def test_non_combat_scenario_weapon_slot_empty(self):
        # 1. Starting weapons list is empty for non-combat scenarios
        self.assertEqual(cd.get_starting_weapons("high_school_drama"), [])
        self.assertEqual(cd.get_starting_weapons("nsfw_high_school_drama"), [])
        self.assertEqual(cd.get_starting_weapons("furry_high_school_drama"), [])
        self.assertEqual(cd.get_starting_weapons("custom_combinator_slice_of_life_non_combat"), [])

        # 2. Starter gear template has Weapon/Shield/Armor as None
        gear = cd.get_starter_gear_by_class("high_school_drama", "Delinquent")
        self.assertIsNone(gear.get("Weapon"))
        self.assertIsNone(gear.get("Shield"))
        self.assertIsNone(gear.get("Armor"))

        # 3. Procedural starter equipment loadout omits Weapon, Shield, Armor
        loadout = generate_starter_equipment_loadout("high_school_drama", char_class="Honor Student", weapon_name="")
        self.assertNotIn("Weapon", loadout)
        self.assertNotIn("Shield", loadout)
        self.assertNotIn("Armor", loadout)

        # 4. db.apply_adventure_loadout does not equip any weapon in non-combat
        test_uid = 777700000 + (uuid.uuid4().int % 100000)
        db.create_character(test_uid, "StudentTest", "Male", "Human")
        db.apply_adventure_loadout(
            user_id=test_uid,
            scenario="high_school_drama",
            char_class="Honor Student",
            weapon_name="",
            gear_map=loadout
        )
        equipped = db.get_equipment(test_uid)
        self.assertIsNone(equipped.get("Weapon"))
        self.assertIsNone(equipped.get("Shield"))
        self.assertIsNone(equipped.get("Armor"))

    def test_high_school_classes_are_faction_role_agnostic(self):
        templates = cd.get_class_templates("high_school_drama")
        self.assertEqual(len(templates), 14)

        expected_classes = [
            "Delinquent", "Varsity Athlete", "Honor Student", "Aspiring Actor",
            "School Journalist", "Occult Enthusiast", "Tech Prodigy", "Artistic Soul",
            "Campus Trendsetter", "Band Musician", "Home Ec Specialist", "Quiet Bookworm",
            "Class Organizer", "Rooftop Daydreamer"
        ]
        self.assertEqual(list(templates.keys()), expected_classes)

        for c_name in templates:
            # Must not be locked to faction leadership/office (e.g. Student Council President)
            self.assertNotIn("Student Council President", c_name)
            self.assertNotIn("President", c_name)
            self.assertNotIn("Captain", c_name)
            self.assertNotIn("Leader", c_name)

    def test_starting_equipment_school_related(self):
        templates = cd.get_class_templates("high_school_drama")
        school_keywords = ["uniform", "blazer", "cardigan", "sweater", "vest", "blouse", "polo", "gakuran", "smock", "jacket", "school", "pullover"]
        
        for c_name, c_info in templates.items():
            starter_gear = c_info.get("starter_gear", {})
            top_name = starter_gear["Top"][0].lower()
            self.assertTrue(
                any(kw in top_name for kw in school_keywords),
                f"Class {c_name} top '{top_name}' should be school-related"
            )

    def test_starting_equipment_gender_and_race_aware(self):
        # 1. Gender awareness: male gets slacks/trousers/chinos, female gets skirts
        for c_name in ["Honor Student", "School Journalist", "Campus Trendsetter", "Class Organizer"]:
            male_gear = cd.get_starter_gear_by_class("high_school_drama", c_name, gender="Male", race="Human")
            female_gear = cd.get_starter_gear_by_class("high_school_drama", c_name, gender="Female", race="Human")

            self.assertNotIn("skirt", male_gear["Bottom"][0].lower())
            male_bot = male_gear["Bottom"][0].lower()
            self.assertTrue("trousers" in male_bot or "slacks" in male_bot or "pants" in male_bot or "chinos" in male_bot)
            self.assertTrue("skirt" in female_gear["Bottom"][0].lower())

        # 2. Race awareness: Beastfolk / Anthro / tailed races get Tail-Slotted bottom
        beast_gear = cd.get_starter_gear_by_class("high_school_drama", "Varsity Athlete", gender="Female", race="Beastfolk / Anthro")
        self.assertTrue(beast_gear["Bottom"][0].startswith("Tail-Slotted "))

        hybrid_gear = cd.get_starter_gear_by_class("high_school_drama", "Quiet Bookworm", gender="Male", race="Half-Beast / Hybrid")
        self.assertTrue(hybrid_gear["Bottom"][0].startswith("Tail-Slotted "))

        # 3. Tailless races (Human, Elf, Dwarf, Android) do not have Tail-Slotted prefix
        for tailless in ["Human", "Elf", "Dwarf", "Dark Elf", "Android / Synth", "Cyborg"]:
            gear = cd.get_starter_gear_by_class("high_school_drama", "Varsity Athlete", gender="Female", race=tailless)
            self.assertFalse(gear["Bottom"][0].startswith("Tail-Slotted "))

    def test_procedural_random_clothing_school_awareness(self):
        top_names = []
        for _ in range(20):
            top = generate_random_clothing("high_school_drama", "Top")
            top_names.append(top["name"].lower())

        # School-appropriate clothing terms should appear frequently
        school_terms = ["uniform", "blazer", "cardigan", "sweater", "vest", "blouse", "shirt", "polo", "jacket"]
        matches = [t for t in top_names if any(st in t for st in school_terms)]
        self.assertTrue(len(matches) >= 15, f"Expected mostly school garments, got {matches}")


if __name__ == "__main__":
    unittest.main()
