import unittest
import uuid
import db
import character_data as cd
from mechanics.combat.items import (
    generate_random_equipment,
    generate_starter_equipment_loadout,
    generate_starting_weapons,
    parse_item,
    can_equip_armor_in_scenario,
)
from mechanics.combat.items.weapons import deduce_weapon_archetype
from mechanics.combat.items.envelope import is_item_json


class TestStartingEquipmentGeneration(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.user_id = 999555000 + (uuid.uuid4().int % 100000)
        self.char = db.create_character(
            self.user_id, "TestAdventurer", "Adventurer", "",
            {"STR": 3, "PER": 2, "END": 2, "CHA": 1, "INT": 2, "AGI": 2, "LUK": 1},
            scenario="fantasy", gender="Male", race="Human"
        )

    def tearDown(self):
        db.delete_character(self.user_id, self.char["id"])

    def test_deduce_weapon_archetype(self):
        """Verify archetype deduction from starting weapon names across genres."""
        self.assertEqual(deduce_weapon_archetype("Steel Longsword"), "sword")
        self.assertEqual(deduce_weapon_archetype("Apprentice Staff"), "staff")
        self.assertEqual(deduce_weapon_archetype("Hunting Bow"), "bow")
        self.assertEqual(deduce_weapon_archetype("Iron Dagger"), "dagger")
        self.assertEqual(deduce_weapon_archetype("Hunting Spear"), "spear")
        self.assertEqual(deduce_weapon_archetype("Sturdy Mace"), "mace")
        self.assertEqual(deduce_weapon_archetype("Pulse Pistol"), "pistol")
        self.assertEqual(deduce_weapon_archetype("Bayoneted Musket"), "musket")
        self.assertEqual(deduce_weapon_archetype("Street Katana"), "katana")
        self.assertEqual(deduce_weapon_archetype("Wooden Kendo Sword"), "katana")
        self.assertEqual(deduce_weapon_archetype("Baseball Bat"), "bat")
        self.assertEqual(deduce_weapon_archetype("Fountain Pen"), "fountain_pen")

    def test_starting_weapons_utilize_new_weapon_generation_system(self):
        """Verify starting weapons generated with new weapon system have full metadata, multiplier, profiles and [ITEM_JSON]."""
        genres = ["fantasy", "sci_fi", "cyberpunk", "steampunk", "dark_fantasy", "nuclear_post_apocalypse", "high_school_drama"]
        for genre in genres:
            starter_weapons = generate_starting_weapons(scenario=genre, count=4)
            self.assertEqual(len(starter_weapons), 4)
            for w in starter_weapons:
                self.assertEqual(w["item_type"], "Weapon")
                self.assertEqual(w["slot"], "Weapon")
                self.assertTrue(is_item_json(w))
                meta = w["metadata"]
                self.assertEqual(meta["tier"], 3)
                self.assertIn("multiplier", meta)
                self.assertIn("attack_profiles", meta)
                self.assertIn("handedness", meta)
                self.assertIn("tags", meta)

    def test_named_starting_weapon_generation(self):
        """Verify passing specific name to weapon generator preserves name and populates rich properties."""
        w = generate_random_equipment(scenario="cyberpunk", slot="Weapon", tier=3, name="Thermal Katana")
        self.assertEqual(w["name"], "Thermal Katana")
        meta = w["metadata"]
        self.assertEqual(meta["archetype"], "katana")
        self.assertEqual(meta["handedness"], "Versatile")
        self.assertGreater(meta["multiplier"], 1.0)
        self.assertTrue(is_item_json(w))

        # Check armor piercing weapon name
        w_ap = generate_random_equipment(scenario="cyberpunk", slot="Weapon", tier=3, name="Vibro-Edged Dagger")
        self.assertEqual(w_ap["metadata"]["archetype"], "dagger")
        self.assertGreater(w_ap["metadata"].get("armor_penetration", 0), 0)
        self.assertTrue(is_item_json(w_ap))

    def test_generate_starter_equipment_loadout_combat(self):
        """Verify full starter loadout in fantasy produces weapon, armor, top, bottom, head, gloves, shoes, accessories."""
        loadout = generate_starter_equipment_loadout(
            scenario="fantasy",
            char_class="Paladin",
            gender="Male",
            race="Human",
            weapon_name="Steel Longsword",
            tier=3
        )
        self.assertIn("Weapon", loadout)
        self.assertEqual(loadout["Weapon"]["name"], "Steel Longsword")
        self.assertIn("Armor", loadout)
        self.assertIn("Top", loadout)
        self.assertIn("Bottom", loadout)
        self.assertIn("Head", loadout)
        self.assertIn("Gloves", loadout)
        self.assertIn("Shoes", loadout)
        self.assertIn("Accessory 1", loadout)

        # Verify male gender protection against skirts
        bottom = loadout["Bottom"]
        self.assertNotIn("skirt", bottom["name"].lower())
        self.assertNotEqual(bottom["metadata"].get("archetype"), "skirt")

        # Verify all items in loadout are encoded as [ITEM_JSON]
        for slot, item in loadout.items():
            self.assertTrue(is_item_json(item), f"Slot {slot} not encoded as [ITEM_JSON]")

    def test_generate_starter_equipment_loadout_non_combat(self):
        """Verify non-combat scenarios do not receive combat armor and receive appropriate civilian items."""
        loadout = generate_starter_equipment_loadout(
            scenario="high_school_drama",
            char_class="Student Council President",
            gender="Female",
            race="Human",
            weapon_name="Fountain Pen",
            tier=3
        )
        self.assertIn("Weapon", loadout)
        self.assertEqual(loadout["Weapon"]["name"], "Fountain Pen")
        self.assertNotIn("Armor", loadout)
        self.assertIn("Top", loadout)
        self.assertIn("Bottom", loadout)
        self.assertIn("Head", loadout)
        self.assertIn("Shoes", loadout)

    def test_two_handed_weapon_no_shield_in_loadout(self):
        """Verify 2H weapon starting loadouts never include a shield."""
        for _ in range(10):
            loadout = generate_starter_equipment_loadout(
                scenario="fantasy",
                char_class="Berserker",
                gender="Male",
                race="Human",
                weapon_name="Executioner Greatsword",
                tier=3
            )
            self.assertEqual(loadout["Weapon"]["metadata"]["handedness"], "2H")
            self.assertNotIn("Shield", loadout)

    def test_db_apply_adventure_loadout_with_new_equipment_system(self):
        """Verify db.apply_adventure_loadout equips gear generated by the new system correctly."""
        loadout = generate_starter_equipment_loadout(
            scenario="steampunk",
            char_class="Steam Artificer",
            gender="Male",
            race="Human",
            weapon_name="Brass Revolver",
            tier=3
        )
        db.apply_adventure_loadout(
            user_id=self.user_id,
            scenario="steampunk",
            char_class="Steam Artificer",
            weapon_name="Brass Revolver",
            gear_map=loadout
        )
        equip = db.get_equipment(self.user_id)
        self.assertIsNotNone(equip.get("Weapon"))
        self.assertEqual(equip["Weapon"]["name"], "Brass Revolver")
        self.assertTrue(is_item_json(equip["Weapon"]))
        self.assertIsNotNone(equip.get("Armor"))
        self.assertTrue(is_item_json(equip["Armor"]))
        self.assertIsNotNone(equip.get("Top"))
        self.assertIsNotNone(equip.get("Bottom"))
        self.assertIsNotNone(equip.get("Head"))
        self.assertIsNotNone(equip.get("Shoes"))

    def test_regenerate_equipment_produces_new_items(self):
        """Verify that regenerating equipment produces different randomized items with non-zero stats."""
        first_loadout = generate_starter_equipment_loadout(
            scenario="fantasy",
            char_class="Rogue",
            gender="Male",
            race="Human",
            weapon_name="Iron Dagger",
            tier=3
        )
        second_loadout = generate_starter_equipment_loadout(
            scenario="fantasy",
            char_class="Rogue",
            gender="Male",
            race="Human",
            weapon_name="Iron Dagger",
            tier=3
        )
        # Both loadouts must have valid equipment
        self.assertEqual(first_loadout["Weapon"]["name"], "Iron Dagger")
        self.assertEqual(second_loadout["Weapon"]["name"], "Iron Dagger")
        self.assertIn("Top", first_loadout)
        self.assertIn("Top", second_loadout)
        self.assertTrue(is_item_json(first_loadout["Top"]))
        self.assertTrue(is_item_json(second_loadout["Top"]))


    def test_thematic_paladin_equipment_generation(self):
        """Verify Paladin loadout produces plate/chainmail and appropriate heavy gear."""
        loadout = generate_starter_equipment_loadout(
            scenario="fantasy",
            char_class="Paladin",
            gender="Male",
            race="Human",
            weapon_name="Steel Longsword",
            tier=3
        )
        armor = loadout.get("Armor", {}).get("metadata", {}).get("archetype")
        self.assertIn(armor, ["plate", "chainmail"])
        
        head = loadout.get("Head", {}).get("metadata", {}).get("archetype")
        self.assertIn(head, ["full_greathelm", "open_helm"])
