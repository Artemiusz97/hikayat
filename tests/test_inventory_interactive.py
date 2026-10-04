import unittest
import db
import character_data as cd
from mechanics.combat.items import parse_item_effect, apply_item_to_target
from cogs.inventory import build_inventory_embed
from skill_check import CheckResult


class TestInteractiveInventory(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.user_id = 9988776655
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id=?", (self.user_id,))
            conn.execute("DELETE FROM inventory WHERE user_id=?", (self.user_id,))
            conn.execute("DELETE FROM sessions WHERE host_user_id=?", (self.user_id,))

        # Create test character
        self.char = db.create_character(
            user_id=self.user_id,
            name="Aria Lightbringer",
            gender="Female",
            char_class="Cleric",
            scenario="fantasy"
        )

    def test_build_inventory_embed(self):
        """Test building rich inventory embed with gear and carried items."""
        db.add_item(self.user_id, "Steel Sword", "Weapon", "A sharp blade", 1)
        sword = next(i for i in db.get_inventory(self.user_id) if i["name"] == "Steel Sword")
        db.equip_item(self.user_id, sword["id"], "Weapon")

        db.add_item(self.user_id, "Healing Potion", "Consumable", "Restores 35 HP", 1)

        embed = build_inventory_embed(self.user_id, feedback_notice="✨ Test notice")
        self.assertIn("Inventory", embed.title)
        self.assertIn("Test notice", embed.description)
        field_names = [f.name for f in embed.fields]
        self.assertTrue(any("Equipped" in fn for fn in field_names))
        self.assertTrue(any("Carried" in fn for fn in field_names))


if __name__ == "__main__":
    unittest.main()
