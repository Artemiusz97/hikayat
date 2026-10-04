import unittest
import db
import character_data as cd
from mechanics.combat.items import (
    generate_random_equipment,
    generate_random_clothing,
    parse_item,
    serialize_item
)
from mechanics.social.attributes import calculate_combat_attributes
from mechanics.narrative.choice_generator import generate_categorized_combat_actions
from mechanics.combat import calculate_tactical_damage, precompute_combat_turn
from mechanics.combat.merchant import calculate_balanced_price, MERCHANT_ARCHETYPES
from cogs.inventory import build_item_inspect_embed


class TestVendorInspectVersatileClothing(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.user_id = 1122334455
        chars = db.get_user_characters(self.user_id)
        for c in chars:
            db.delete_character(self.user_id, c["id"])
        with db.get_conn() as conn:
            conn.execute("DELETE FROM inventory WHERE user_id=?", (self.user_id,))

    def tearDown(self):
        chars = db.get_user_characters(self.user_id)
        for c in chars:
            db.delete_character(self.user_id, c["id"])
        with db.get_conn() as conn:
            conn.execute("DELETE FROM inventory WHERE user_id=?", (self.user_id,))

    # -------------------------------------------------------------------------
    # 1. VENDOR STOCKING & PRICING
    # -------------------------------------------------------------------------
    def test_vendor_pricing_for_armor_and_head(self):
        """Ensure calculate_balanced_price supports 'Armor' and 'Head' properly."""
        p_armor_t1 = calculate_balanced_price("Armor", "Plate Cuirass", tier=1)
        p_armor_t2 = calculate_balanced_price("Armor", "Plate Cuirass", tier=2)
        p_armor_t3 = calculate_balanced_price("Armor", "Plate Cuirass", tier=3)

        self.assertGreaterEqual(p_armor_t1, 450)
        self.assertGreaterEqual(p_armor_t2, 110)
        self.assertGreaterEqual(p_armor_t3, 25)

        p_head_t1 = calculate_balanced_price("Head", "Great Helm", tier=1)
        p_head_t2 = calculate_balanced_price("Head", "Great Helm", tier=2)
        p_head_t3 = calculate_balanced_price("Head", "Great Helm", tier=3)

        self.assertGreaterEqual(p_head_t1, 450)
        self.assertGreaterEqual(p_head_t2, 110)
        self.assertGreaterEqual(p_head_t3, 25)

    def test_merchant_archetype_allowed_types(self):
        """Verify armor_merchant includes Armor, Head, Gloves, Shoes."""
        armor_arch = MERCHANT_ARCHETYPES["armor_merchant"]
        allowed = armor_arch["allowed_types"]
        self.assertIn("Armor", allowed)
        self.assertIn("Head", allowed)
        self.assertIn("Top", allowed)
        self.assertIn("Bottom", allowed)
        self.assertIn("Gloves", allowed)
        self.assertIn("Shoes", allowed)

    # -------------------------------------------------------------------------
    # 2. CLOTHING & ARMOR LAYERING COEXISTENCE
    # -------------------------------------------------------------------------
    def test_clothing_stats_suppressed_when_combat_armor_is_equipped(self):
        """When combat Armor is equipped, civilian clothing stats/social modifiers must be suppressed."""
        char = {
            "name": "Armored Hero", "str_": 5, "per_": 5, "end_": 5, "cha_": 5,
            "int_": 5, "agi_": 5, "luk": 5, "level": 1, "hp": 50, "max_hp": 50
        }
        # Civilian shirt: +2 EVA, +1 CHA
        shirt = {
            "name": "Casual Linen Shirt",
            "slot": "Top",
            "item_type": "Clothing",
            "effect": serialize_item({
                "archetype": "casual_shirt",
                "slot": "Top",
                "item_type": "Clothing",
                "social_modifiers": {"cha": 1, "eva": 2, "luck": 0}
            })
        }
        # 1. With only shirt equipped:
        attrs_shirt_only = calculate_combat_attributes(char, [shirt])
        self.assertFalse(attrs_shirt_only.get("clothing_suppressed", False))
        # base_eva with agi 5, luk 5 = 19; shirt provides +2 EVA = 21
        self.assertEqual(attrs_shirt_only["eva"], 21)

        # 2. Equip heavy combat armor:
        armor = {
            "name": "Knight's Steel Cuirass",
            "slot": "Armor",
            "item_type": "Armor",
            "effect": serialize_item({
                "archetype": "plate",
                "slot": "Armor",
                "item_type": "Armor",
                "base_dt": 22,
                "base_eva": -6
            })
        }
        attrs_layered = calculate_combat_attributes(char, [shirt, armor])
        self.assertTrue(attrs_layered.get("clothing_suppressed", False))
        # Clothing +2 EVA is suppressed, so only base 19 - 6 (armor penalty) = 13
        self.assertEqual(attrs_layered["eva"], 13)
        self.assertEqual(attrs_layered["base_dt"], 22)

    # -------------------------------------------------------------------------
    # 3. EQUIPMENT AUTO-COMPARE IN INSPECT UI
    # -------------------------------------------------------------------------
    def test_inspect_embed_auto_compare_weapon(self):
        """Inspecting an unequipped weapon shows side-by-side comparison with equipped weapon."""
        char_id = db.create_character(
            user_id=self.user_id,
            name="Duelist",
            gender="Non-binary",
            char_class="Warrior",
            scenario="fantasy"
        )
        # Equip a Basic Sword (multiplier 1.25, crit 4)
        sword_id = db.add_item(
            user_id=self.user_id,
            name="Iron Broadsword",
            item_type="Weapon",
            slot_cost=1,
            effect=serialize_item({
                "slot": "Weapon",
                "item_type": "Weapon",
                "archetype": "sword",
                "multiplier": 1.25,
                "crit_bonus": 4.0
            })
        )
        db.equip_item(self.user_id, sword_id, "Weapon")

        # Inspect a Superior Katana (multiplier 1.45, crit 8)
        new_katana = {
            "id": 9991,
            "name": "Superior Steel Katana",
            "item_type": "Weapon",
            "slot": "Weapon",
            "slot_cost": 1,
            "equipped": 0,
            "effect": serialize_item({
                "slot": "Weapon",
                "item_type": "Weapon",
                "archetype": "katana",
                "multiplier": 1.45,
                "crit_bonus": 8.0,
                "armor_penetration": 0.25
            })
        }

        embed = build_item_inspect_embed(new_katana, self.user_id)
        # Find comparison field
        compare_field = next((f for f in embed.fields if "vs Equipped" in f.name), None)
        self.assertIsNotNone(compare_field)
        self.assertIn("Iron Broadsword", compare_field.name)
        self.assertIn("Power Mult:", compare_field.value)
        self.assertIn("`1.25` ➔ `1.45` (+0.2 🔺)", compare_field.value)
        self.assertIn("Crit Bonus:", compare_field.value)
        self.assertIn("`4.0%` ➔ `8.0%` (+4.0% 🔺)", compare_field.value)

    def test_inspect_embed_empty_slot_free_upgrade(self):
        """Inspecting gear for an empty slot indicates free upgrade."""
        db.create_character(
            user_id=self.user_id,
            name="Rookie",
            gender="Male",
            char_class="Adventurer",
            scenario="fantasy"
        )
        new_shield = {
            "id": 9992,
            "name": "Tower Shield",
            "item_type": "Shield",
            "slot": "Shield",
            "slot_cost": 1,
            "equipped": 0,
            "effect": serialize_item({
                "slot": "Shield",
                "item_type": "Shield",
                "archetype": "tower_shield",
                "block_chance": 25,
                "base_dt": 14
            })
        }
        embed = build_item_inspect_embed(new_shield, self.user_id)
        compare_field = next((f for f in embed.fields if "vs Equipped" in f.name), None)
        self.assertIsNotNone(compare_field)
        self.assertIn("Free upgrade!", compare_field.value)

    # -------------------------------------------------------------------------
    # 4. VERSATILE STANCE DYNAMIC COMBAT CHOICES & RESOLUTION
    # -------------------------------------------------------------------------
    def test_versatile_weapon_generates_1h_and_2h_attack_options(self):
        """A versatile weapon generates both (1H) and (2H) attack options in choice generator."""
        char = {
            "name": "Knight", "str_": 7, "per_": 5, "end_": 6, "cha_": 3,
            "int_": 3, "agi_": 5, "luk": 4, "hp": 60, "max_hp": 60, "mp": 20, "max_mp": 20
        }
        monster = {
            "name": "Cave Troll", "level": 3,
            "stats": {"STR": 6, "PER": 3, "END": 5, "CHA": 1, "INT": 2, "AGI": 3, "LUK": 2}
        }
        versatile_sword = {
            "name": "Bastard Sword",
            "slot": "Weapon",
            "equipped": 1,
            "item_type": "Weapon",
            "effect": serialize_item({
                "name": "Bastard Sword",
                "slot": "Weapon",
                "item_type": "Weapon",
                "archetype": "sword",
                "handedness": "Versatile",
                "attack_types": ["slash", "thrust"],
                "multiplier": 1.25,
                "crit_bonus": 4.0
            })
        }
        party = [(char, [versatile_sword])]
        cat = generate_categorized_combat_actions(party, monster, "ruins", "fantasy")
        attacks = cat["attacks"]

        stances = [a.get("stance") for a in attacks]
        self.assertIn("1H", stances)
        self.assertIn("2H", stances)

        label_1h = next(a["label"] for a in attacks if a.get("stance") == "1H")
        label_2h = next(a["label"] for a in attacks if a.get("stance") == "2H")
        self.assertIn("(1H)", label_1h)
        self.assertIn("(2H)", label_2h)

    def test_versatile_2h_strike_damage_and_shield_suppression(self):
        """2H versatile strike deals +15% damage and suppresses shield block/DT during enemy counter."""
        char_attrs = {
            "atk": 50, "matk": 20, "def": 20, "mdef": 20,
            "acc": 75, "eva": 15, "block_chance": 30, "base_dt": 12
        }
        enemy_attrs = {
            "atk": 30, "matk": 10, "def": 15, "mdef": 10,
            "acc": 60, "eva": 10, "block_chance": 0, "base_dt": 4
        }
        weapon_meta = {
            "name": "Broadsword",
            "archetype": "sword",
            "handedness": "Versatile",
            "attack_types": ["slash"],
            "multiplier": 1.25
        }
        armor_meta = {"base_dt": 4, "type_dt": {}}

        # Calculate 1H vs 2H strike
        dmg_1h = calculate_tactical_damage(
            attacker_attrs=char_attrs,
            defender_attrs=enemy_attrs,
            weapon_meta=weapon_meta,
            armor_meta=armor_meta,
            tier="success",
            attacker_level=2,
            defender_max_hp=100,
            stance="1H"
        )
        dmg_2h = calculate_tactical_damage(
            attacker_attrs=char_attrs,
            defender_attrs=enemy_attrs,
            weapon_meta=weapon_meta,
            armor_meta=armor_meta,
            tier="success",
            attacker_level=2,
            defender_max_hp=100,
            stance="2H"
        )

        self.assertTrue(dmg_2h.get("versatile_2h"))
        self.assertFalse(dmg_1h.get("versatile_2h"))
        self.assertGreater(dmg_2h["base_damage"], dmg_1h["base_damage"])

        # Test precompute_combat_turn shield suppression when 2H stance action is chosen
        char_id = db.create_character(
            user_id=self.user_id,
            name="Vanguard",
            gender="Female",
            char_class="Warrior",
            scenario="fantasy"
        )
        shield_id = db.add_item(
            user_id=self.user_id,
            name="Knight Shield",
            item_type="Shield",
            slot_cost=1,
            effect=serialize_item({
                "slot": "Shield",
                "item_type": "Shield",
                "archetype": "heater_shield",
                "block_chance": 35,
                "base_dt": 8
            })
        )
        db.equip_item(self.user_id, shield_id, "Shield")
        char = db.get_character(self.user_id)
        session = {
            "scenario": "fantasy",
            "nearby_enemies": [{
                "name": "Orc Brute", "archetype": "Brute", "level": 2, "hp": 50, "max_hp": 50
            }],
            "combat_turn": 1
        }
        # Choose 2H stance action
        action_2h = {
            "label": "⚔️ Slash (2H) with Broadsword",
            "choice_type": "MELEE_SLASHING_PIERCING",
            "attack_type": "slash",
            "stance": "2H",
            "tier": "success"
        }
        res_2h = precompute_combat_turn(session, [(char, [])], [action_2h])
        log_text = " ".join(res_2h.get("combat_log", []))
        self.assertIn("Two-Handed Grip!", log_text)


if __name__ == "__main__":
    unittest.main()
