import unittest
import os
import sqlite3
import tempfile
import db
import game_engine
from mechanics.combat.items import can_equip_item_in_scenario
from cogs.character import build_character_sheet_embed
from mechanics.combat import precompute_combat_turn
from character_data import sanitize_status_effects


class TestCombatConsumablesAndGearLockout(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.user_id = 8888001
        db.delete_character(self.user_id)
        db.create_character(
            user_id=self.user_id,
            name="TestHero",
            gender="Male",
            race="human",
            char_class="Warrior",
            stats={"STR": 10, "PER": 10, "END": 10, "CHA": 10, "INT": 10, "AGI": 10, "LUK": 10},
            scenario="fantasy"
        )

    def tearDown(self):
        db.delete_character(self.user_id)

    # -------------------------------------------------------------------------
    # 1. Non-Combat Scenario Gear Lockout
    # -------------------------------------------------------------------------
    def test_non_combat_gear_lockout(self):
        # Items
        plate_armor = {"name": "Iron Plate Armor", "item_type": "Armor", "effect": "[ITEM_JSON]{\"archetype\": \"plate\", \"base_dt\": 22}"}
        tower_shield = {"name": "Tower Shield", "item_type": "Shield", "effect": "[ITEM_JSON]{\"archetype\": \"tower_shield\", \"base_dt\": 14}"}
        greathelm = {"name": "Full Greathelm", "item_type": "Headwear", "effect": "[ITEM_JSON]{\"archetype\": \"full_greathelm\", \"base_dt\": 6}"}
        cap = {"name": "Baseball Cap", "item_type": "Headwear", "effect": "[ITEM_JSON]{\"archetype\": \"cap\", \"base_dt\": 0}"}
        heavy_gauntlets = {"name": "Steel Gauntlets", "item_type": "Gloves", "effect": "[ITEM_JSON]{\"archetype\": \"heavy_gauntlets\", \"base_dt\": 6, \"armor_type\": \"heavy\"}"}
        formal_gloves = {"name": "Silk Gloves", "item_type": "Gloves", "effect": "[ITEM_JSON]{\"archetype\": \"formal_gloves\", \"base_dt\": 0}"}
        combat_boots = {"name": "Combat Boots", "item_type": "Shoes", "effect": "[ITEM_JSON]{\"archetype\": \"combat_boots\", \"base_dt\": 3}"}
        sneakers = {"name": "Light Sneakers", "item_type": "Shoes", "effect": "[ITEM_JSON]{\"archetype\": \"light_sneakers\", \"base_dt\": 0}"}
        shirt = {"name": "Linen Shirt", "item_type": "Clothing", "effect": "[ITEM_JSON]{\"archetype\": \"casual_shirt\", \"base_dt\": 0}"}

        # Under non-combat scenario: high_school
        allowed, msg = can_equip_item_in_scenario(plate_armor, "Armor", "high_school")
        self.assertFalse(allowed)
        self.assertIn("Combat armor", msg)

        allowed, msg = can_equip_item_in_scenario(tower_shield, "Shield", "high_school")
        self.assertFalse(allowed)

        allowed, msg = can_equip_item_in_scenario(greathelm, "Head", "high_school")
        self.assertFalse(allowed)
        self.assertIn("Combat helmets", msg)

        allowed, msg = can_equip_item_in_scenario(cap, "Head", "high_school")
        self.assertTrue(allowed)

        allowed, msg = can_equip_item_in_scenario(heavy_gauntlets, "Gloves", "high_school")
        self.assertFalse(allowed)
        self.assertIn("Heavy combat gauntlets", msg)

        allowed, msg = can_equip_item_in_scenario(formal_gloves, "Gloves", "high_school")
        self.assertTrue(allowed)

        allowed, msg = can_equip_item_in_scenario(combat_boots, "Shoes", "high_school")
        self.assertFalse(allowed)
        self.assertIn("Combat boots", msg)

        allowed, msg = can_equip_item_in_scenario(sneakers, "Shoes", "high_school")
        self.assertTrue(allowed)

        allowed, msg = can_equip_item_in_scenario(shirt, "Top", "high_school")
        self.assertTrue(allowed)

        # Under combat scenario: fantasy (all should be allowed)
        self.assertTrue(can_equip_item_in_scenario(plate_armor, "Armor", "fantasy")[0])
        self.assertTrue(can_equip_item_in_scenario(tower_shield, "Shield", "fantasy")[0])
        self.assertTrue(can_equip_item_in_scenario(greathelm, "Head", "fantasy")[0])
        self.assertTrue(can_equip_item_in_scenario(heavy_gauntlets, "Gloves", "fantasy")[0])
        self.assertTrue(can_equip_item_in_scenario(combat_boots, "Shoes", "fantasy")[0])

    # -------------------------------------------------------------------------
    # 2. Dormant Civilian Clothing Display in Character Profile
    # -------------------------------------------------------------------------
    def test_dormant_civilian_clothing_profile_display(self):
        char = db.get_character(self.user_id)
        
        # Scenario A: Top & Bottom equipped, NO combat armor
        equipment_no_armor = {
            "Top": {"name": "Linen Shirt", "item_type": "Clothing", "effect": ""},
            "Bottom": {"name": "Slacks", "item_type": "Clothing", "effect": ""},
            "Weapon": {"name": "Shortsword", "item_type": "Weapon", "effect": ""}
        }
        embed_no_armor = build_character_sheet_embed(char, equipment_no_armor)
        equip_field = next(f for f in embed_no_armor.fields if f.name == "Equipment")
        self.assertIn("Linen Shirt", equip_field.value)
        self.assertNotIn("*(dormant)*", equip_field.value)

        # Scenario B: Combat Armor equipped + Top & Bottom
        equipment_with_armor = {
            "Armor": {"name": "Steel Cuirass", "item_type": "Armor", "effect": ""},
            "Top": {"name": "Linen Shirt", "item_type": "Clothing", "effect": ""},
            "Bottom": {"name": "Slacks", "item_type": "Clothing", "effect": ""},
            "Weapon": {"name": "Shortsword", "item_type": "Weapon", "effect": ""}
        }
        embed_with_armor = build_character_sheet_embed(char, equipment_with_armor)
        equip_field_armor = next(f for f in embed_with_armor.fields if f.name == "Equipment")
        self.assertIn("Linen Shirt *(dormant)*", equip_field_armor.value)
        self.assertIn("Slacks *(dormant)*", equip_field_armor.value)
        self.assertIn("Steel Cuirass", equip_field_armor.value)
        self.assertNotIn("Steel Cuirass *(dormant)*", equip_field_armor.value)

    # -------------------------------------------------------------------------
    # 3. Consumable Inventory Deduction in Battle Engine
    # -------------------------------------------------------------------------
    def test_consumable_deduction_in_combat(self):
        # Give player 2 healing potions
        db.add_item(self.user_id, "Lesser Healing Potion", "Consumable", "Restores 20 HP")
        db.add_item(self.user_id, "Lesser Healing Potion", "Consumable", "Restores 20 HP")
        
        inv_before = db.get_inventory(self.user_id)
        potions_before = [i for i in inv_before if i["name"] == "Lesser Healing Potion"]
        self.assertEqual(len(potions_before), 2)

        # Prepare combat session & party
        session = {
            "id": 101,
            "scenario": "fantasy",
            "combat_turn": 1,
            "current_npcs": [],
            "nearby_enemies": [{"name": "Goblin", "hp": 30, "max_hp": 30, "stats": {}}]
        }
        char = db.get_character(self.user_id)
        party = [(char, inv_before)]
        
        # Execute item action
        action = {
            "stat": "ITEM",
            "choice_type": "ITEM_ACTION",
            "label": "Use Lesser Healing Potion on Yourself",
            "item_name": "Lesser Healing Potion"
        }
        
        res = precompute_combat_turn(session, party, [action])
        self.assertTrue(action.get("item_consumed"))

        # Check that 1 potion was deducted
        inv_after = db.get_inventory(self.user_id)
        potions_after = [i for i in inv_after if i["name"] == "Lesser Healing Potion"]
        self.assertEqual(len(potions_after), 1)

        # Calling again with item_consumed=True should not double deduct
        precompute_combat_turn(session, party, [action])
        inv_after_second = db.get_inventory(self.user_id)
        potions_after_second = [i for i in inv_after_second if i["name"] == "Lesser Healing Potion"]
        self.assertEqual(len(potions_after_second), 1)

    # -------------------------------------------------------------------------
    # 4. Out-of-Combat Exploration Timer Decay for Combat Buffs
    # -------------------------------------------------------------------------
    def test_out_of_combat_buff_clearing(self):
        # Create session and setup character with combat buff
        sess_id = db.create_session(
            host_user_id=self.user_id,
            mode="solo",
            capacity=1,
            verbosity="standard",
            dialogue_mode="group",
            image_gen_enabled=False,
            scenario="fantasy"
        )
        char = db.get_character(self.user_id)
        
        # Outcome outside of combat (is_combat = False)
        outcome = {
            "character_outcomes": [
                {
                    "name": char["name"],
                    "hp_change": 0,
                    "mp_change": 0,
                    "gold_change": 0,
                    "status_effects": [
                        "Bleeding",
                        "Iron Skin [+8 DT] [3 turns]",
                        "Combat Booster [+25% ATK] [2 turns]"
                    ]
                }
            ]
        }
        
        party = [(char, [])]
        game_engine.apply_outcome(sess_id, party, outcome)
        
        # The combat turn buffs should be cleared, leaving only standard condition "Bleeding"
        char_after = db.get_character(self.user_id)
        status_after = char_after.get("status_effects", "")
        self.assertIn("Bleeding", status_after)
        self.assertNotIn("Iron Skin [+8 DT] [3 turns]", status_after)
        self.assertNotIn("Combat Booster [+25% ATK] [2 turns]", status_after)


if __name__ == "__main__":
    unittest.main()
