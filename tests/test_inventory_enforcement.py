import unittest
import db
import character_data as cd
import game_engine

class TestInventoryEnforcement(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.user_id = 999988771
        chars = db.get_user_characters(self.user_id)
        for c in chars:
            db.delete_character(self.user_id, c["id"])

    def tearDown(self):
        chars = db.get_user_characters(self.user_id)
        for c in chars:
            db.delete_character(self.user_id, c["id"])

    def test_inventory_capacity_formula(self):
        # Base capacity 30, +3 per STR point
        self.assertEqual(cd.inventory_capacity(1), 33)
        self.assertEqual(cd.inventory_capacity(4), 42)
        self.assertEqual(cd.inventory_capacity(10), 60)

    def test_hard_enforcement_add_item(self):
        base_stats = {"STR": 1, "PER": 1, "END": 1, "CHA": 1, "INT": 1, "AGI": 1, "LUK": 1}
        char = db.create_character(
            user_id=self.user_id,
            name="BagTester",
            char_class="Warrior",
            class_description="Test bag limits",
            stats=base_stats
        )
        self.assertIsNotNone(char)
        cap = cd.inventory_capacity(char["str_"])  # 33 slots

        # Fill up to capacity
        for i in range(cap):
            item_id = db.add_item(self.user_id, f"Item_{i}", "Consumable", "Test item", slot_cost=1)
            self.assertIsNotNone(item_id, f"Failed adding item {i} within capacity")

        self.assertEqual(db.used_slots(self.user_id), cap)
        self.assertFalse(db.can_add_item(self.user_id, 1))

        # Adding 34th item should return None (rejected)
        overflow_id = db.add_item(self.user_id, "Overflow_Item", "Consumable", "Should fail", slot_cost=1)
        self.assertIsNone(overflow_id)
        self.assertEqual(db.used_slots(self.user_id), cap)

        # Force adding works if explicitly requested
        forced_id = db.add_item(self.user_id, "Forced_Item", "Consumable", "Forced", slot_cost=1, force=True)
        self.assertIsNotNone(forced_id)
        self.assertEqual(db.used_slots(self.user_id), cap + 1)

    def test_adventure_loot_rejection_on_full_inventory(self):
        base_stats = {"STR": 1, "PER": 1, "END": 1, "CHA": 1, "INT": 1, "AGI": 1, "LUK": 1}
        char = db.create_character(
            user_id=self.user_id,
            name="LootTester",
            char_class="Warrior",
            class_description="Test loot overflow",
            stats=base_stats
        )
        cap = cd.inventory_capacity(char["str_"])
        for i in range(cap):
            db.add_item(self.user_id, f"Item_{i}", "Consumable")

        # Mock outcome with gained items
        party = [(db.get_character(self.user_id), db.get_inventory(self.user_id))]
        outcome = {
            "character_outcomes": [
                {
                    "name": "LootTester",
                    "hp_change": 0,
                    "mp_change": 0,
                    "gold_change": 10,
                    "items_gained": ["Legendary Relic"]
                }
            ]
        }
        items_gained = game_engine.apply_outcome(session_id=0, party=party, outcome=outcome)
        user_gained = items_gained.get(self.user_id, [])
        self.assertEqual(len(user_gained), 1)
        self.assertIn("Lost: Inventory Full!", user_gained[0])
