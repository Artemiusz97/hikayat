import unittest
import os
import db
import character_data as cd

class TestCharacterLimit(unittest.TestCase):
    def setUp(self):
        # Setup in-memory or temp db for isolated testing
        db.init_db()
        self.user_id = 999999123

    def tearDown(self):
        # Clean up test user's data
        chars = db.get_user_characters(self.user_id)
        for c in chars:
            db.delete_character(self.user_id, c["id"])

    def test_character_creation_limit_six(self):
        base_stats = {"STR": 1, "PER": 1, "END": 1, "CHA": 1, "INT": 1, "AGI": 1, "LUK": 1}
        created = []
        for i in range(1, 7):
            char = db.create_character(
                user_id=self.user_id,
                name=f"Hero_{i}",
                char_class="Mercenary",
                class_description="Test hero",
                stats=base_stats,
                gold=10
            )
            self.assertIsNotNone(char)
            created.append(char)

        # Confirm 6 characters in database
        all_chars = db.get_user_characters(self.user_id)
        self.assertEqual(len(all_chars), 6)

        # 7th creation must raise ValueError
        with self.assertRaises(ValueError) as ctx:
            db.create_character(
                user_id=self.user_id,
                name="Hero_7",
                char_class="Mercenary",
                class_description="Overflow hero",
                stats=base_stats
            )
        self.assertIn("maximum 6 characters", str(ctx.exception))

    def test_equipment_and_inventory_per_character_isolation(self):
        base_stats = {"STR": 1, "PER": 1, "END": 1, "CHA": 1, "INT": 1, "AGI": 1, "LUK": 1}
        char1 = db.create_character(self.user_id, "Char_One", "Mercenary", "", base_stats)
        item1_id = db.add_item(self.user_id, "Iron Sword", "Weapon")
        db.equip_item(self.user_id, item1_id, "Weapon")

        equip1 = db.get_equipment(self.user_id)
        self.assertIsNotNone(equip1["Weapon"])
        self.assertEqual(equip1["Weapon"]["name"], "Iron Sword")

        # Create second character (which activates Char_Two)
        char2 = db.create_character(self.user_id, "Char_Two", "Arcanist", "", base_stats)
        item2_id = db.add_item(self.user_id, "Magic Staff", "Weapon")
        db.equip_item(self.user_id, item2_id, "Weapon")

        equip2 = db.get_equipment(self.user_id)
        self.assertIsNotNone(equip2["Weapon"])
        self.assertEqual(equip2["Weapon"]["name"], "Magic Staff")

        # Switch back to Char_One
        db.switch_character(self.user_id, char1["id"])
        equip1_again = db.get_equipment(self.user_id)
        self.assertIsNotNone(equip1_again["Weapon"])
        self.assertEqual(equip1_again["Weapon"]["name"], "Iron Sword")

if __name__ == "__main__":
    unittest.main()
