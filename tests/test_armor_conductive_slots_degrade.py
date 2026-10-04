import unittest
import sqlite3
from unittest.mock import MagicMock, patch

from mechanics.social.attributes import calculate_combat_attributes
from mechanics.combat import (
    calculate_tactical_damage,
    try_inflict_status,
    precompute_combat_turn,
    tick_status_timers
)
from mechanics.combat.items.armors import generate_random_equipment as gen_armor, ARMOR_ARCHETYPES
from mechanics.combat.items.headwear import generate_random_equipment as gen_headwear, HEADWEAR_ARCHETYPES
from mechanics.combat.items.clothing import generate_random_clothing
from mechanics.combat.items.weapons import generate_random_equipment as gen_weapon
from mechanics.combat.items.shields import generate_random_equipment as gen_shield
from mechanics.combat.equipment import parse_equipment_metadata
import db


class TestArmorConductiveSlotsDegrade(unittest.TestCase):
    def setUp(self):
        self.user_id = 88888
        self.tearDown()
        self.char_data = {
            "id": self.user_id,
            "user_id": self.user_id,
            "name": "ArmoredHero",
            "char_class": "Warrior",
            "class_description": "Fighter",
            "stats": {"STR": 10, "AGI": 5, "END": 10, "INT": 5, "PER": 5, "CHA": 5, "LUK": 5},
            "gold": 100,
            "pending_stat_points": 0,
            "gender": "Non-binary",
            "scenario": "fantasy",
            "race": "Human",
            "race_description": "Standard Human",
            "level": 5,
            "hp": 100,
            "max_hp": 100,
            "mp": 50,
            "max_mp": 50,
            "str_": 10,
            "agi": 5,
            "int_": 5,
            "per_": 5,
            "end_": 10,
            "cha": 5,
            "luk": 5,
            "status_effects": []
        }

        # Setup test DB character
        with db.get_conn() as conn:
            conn.execute("DELETE FROM inventory WHERE user_id=?", (self.user_id,))
            conn.execute("DELETE FROM characters WHERE user_id=?", (self.user_id,))
        
        db.create_character(
            user_id=self.user_id,
            name=self.char_data["name"],
            char_class=self.char_data["char_class"],
            class_description=self.char_data["class_description"],
            stats=self.char_data["stats"],
            gold=self.char_data["gold"],
            pending_stat_points=self.char_data["pending_stat_points"],
            gender=self.char_data["gender"],
            scenario=self.char_data["scenario"],
            race=self.char_data["race"],
            race_description=self.char_data["race_description"]
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM inventory WHERE user_id=?", (self.user_id,))
            conn.execute("DELETE FROM characters WHERE user_id=?", (self.user_id,))

    # ──────────────────────────────────────────────────────────────────────────
    # 1. 🛡️ Slot-Mismatched Equipping Enforcement
    # ──────────────────────────────────────────────────────────────────────────
    def test_combat_armor_cannot_equip_in_clothing_slots(self):
        plate = gen_armor("fantasy", slot="Armor", archetype="plate")
        item_id = db.add_item(self.user_id, plate["name"], plate["item_type"], plate["effect"], plate["slot_cost"])

        # Attempting to equip combat armor into civilian clothing slots (Top/Bottom) must raise ValueError
        with self.assertRaises(ValueError) as ctx_top:
            db.equip_item(self.user_id, item_id, "Top")
        self.assertIn("Combat body armor can only be equipped in the dedicated 'Armor' slot", str(ctx_top.exception))

        with self.assertRaises(ValueError) as ctx_bot:
            db.equip_item(self.user_id, item_id, "Bottom")
        self.assertIn("Combat body armor can only be equipped in the dedicated 'Armor' slot", str(ctx_bot.exception))

        # Successfully equips into dedicated Armor slot
        db.equip_item(self.user_id, item_id, "Armor")
        current_equip = db.get_equipment(self.user_id)
        self.assertIsNotNone(current_equip.get("Armor"))
        self.assertEqual(current_equip["Armor"]["id"], item_id)

    def test_civilian_clothing_cannot_equip_in_combat_armor_slot(self):
        shirt = generate_random_clothing("fantasy", slot="Top")
        shirt_id = db.add_item(self.user_id, shirt["name"], shirt["item_type"], shirt["effect"], shirt["slot_cost"])

        # Attempting to equip civilian clothing into combat Armor slot must raise ValueError
        with self.assertRaises(ValueError) as ctx:
            db.equip_item(self.user_id, shirt_id, "Armor")
        self.assertIn("Civilian clothing can only be equipped in 'Top' or 'Bottom' slots", str(ctx.exception))

        # Successfully equips in Top
        db.equip_item(self.user_id, shirt_id, "Top")
        current_equip = db.get_equipment(self.user_id)
        self.assertIsNotNone(current_equip.get("Top"))
        self.assertEqual(current_equip["Top"]["id"], shirt_id)

    def test_headwear_and_shield_slot_restrictions(self):
        helm = gen_headwear("fantasy", archetype="full_greathelm")
        helm_id = db.add_item(self.user_id, helm["name"], helm["item_type"], helm["effect"], helm["slot_cost"])

        with self.assertRaises(ValueError) as ctx_h:
            db.equip_item(self.user_id, helm_id, "Armor")
        self.assertIn("Headwear and helmets can only be equipped in the 'Head' slot", str(ctx_h.exception))

        shield = gen_shield("fantasy", archetype="heater_shield")
        shield_id = db.add_item(self.user_id, shield["name"], shield["item_type"], shield["effect"], shield["slot_cost"])

        with self.assertRaises(ValueError) as ctx_s:
            db.equip_item(self.user_id, shield_id, "Top")
        self.assertIn("Shields can only be equipped in the 'Shield' slot", str(ctx_s.exception))

    def test_inventory_dropdown_filters_valid_slots_by_type(self):
        from cogs.inventory import EquipSlotSelectDropdown

        plate = gen_armor("fantasy", archetype="plate")
        dropdown_armor = EquipSlotSelectDropdown(self.user_id, plate)
        slots_armor = [opt.value for opt in dropdown_armor.options]
        self.assertEqual(slots_armor, ["Armor"])

        clothing = generate_random_clothing("fantasy", slot="Top")
        dropdown_clothing = EquipSlotSelectDropdown(self.user_id, clothing)
        slots_clothing = [opt.value for opt in dropdown_clothing.options]
        self.assertEqual(slots_clothing, ["Top", "Bottom"])

        helm = gen_headwear("fantasy", archetype="full_greathelm")
        dropdown_helm = EquipSlotSelectDropdown(self.user_id, helm)
        slots_helm = [opt.value for opt in dropdown_helm.options]
        self.assertEqual(slots_helm, ["Head"])

    # ──────────────────────────────────────────────────────────────────────────
    # 2. ⚡ Elemental Insulation & Shock Vulnerability on Metal Armors
    # ──────────────────────────────────────────────────────────────────────────
    def test_conductive_metal_armors_have_negative_shock_res(self):
        for arch in ("chainmail", "lamellar", "plate"):
            data = ARMOR_ARCHETYPES[arch]
            self.assertIn("shock_res", data.get("stat_modifiers", {}))
            self.assertEqual(data["stat_modifiers"]["shock_res"], -15)

            genned = gen_armor("fantasy", archetype=arch)
            meta = parse_equipment_metadata(genned)
            self.assertEqual(meta["stat_modifiers"].get("shock_res"), -15)

    def test_shock_vulnerability_yields_negative_dr_and_amplifies_damage(self):
        plate = gen_armor("fantasy", archetype="plate")
        attrs = calculate_combat_attributes(self.char_data, [plate])

        # Plate wearer must have -15% shock resistance / negative DR
        self.assertEqual(attrs["shock_res"], -15)
        self.assertAlmostEqual(attrs["gear_dr"]["shock"], -0.15)

        # Attacker dealing shock damage
        attacker_attrs = {"atk": 20, "matk": 40, "acc": 80, "eva": 10}
        shock_spell_weapon = {
            "multiplier": 1.0,
            "attack_types": ["channeling"],
            "damage_types": {"shock": 1.0}
        }
        plate_meta = parse_equipment_metadata(plate)
        res_shock = calculate_tactical_damage(
            attacker_attrs=attacker_attrs,
            defender_attrs=attrs,
            weapon_meta=shock_spell_weapon,
            armor_meta=plate_meta,
            tier="success",
            attacker_level=5,
            defender_max_hp=100
        )

        # Compare with insulated magic robe
        robe = gen_armor("fantasy", archetype="magic_robe")
        robe_attrs = calculate_combat_attributes(self.char_data, [robe])
        robe_meta = parse_equipment_metadata(robe)
        res_robe = calculate_tactical_damage(
            attacker_attrs=attacker_attrs,
            defender_attrs=robe_attrs,
            weapon_meta=shock_spell_weapon,
            armor_meta=robe_meta,
            tier="success",
            attacker_level=5,
            defender_max_hp=100
        )

        # Conductive plate must take strictly more shock damage than insulated robe
        self.assertGreater(res_shock["damage"], res_robe["damage"])

    # ──────────────────────────────────────────────────────────────────────────
    # 3. 🪖 Headwear vs. Full-Face Helmets (Sensory Blind Spot / PER Penalty)
    # ──────────────────────────────────────────────────────────────────────────
    def test_full_face_helmet_per_penalty_strictly_capped_at_minus_one(self):
        # Baseline attributes without helmet
        base_attrs = calculate_combat_attributes(self.char_data, [])
        self.assertEqual(base_attrs["per"], 5)
        base_acc = base_attrs["acc"]

        # Tier 3 full greathelm
        helm_t3 = gen_headwear("fantasy", tier=3, archetype="full_greathelm")
        meta_t3 = parse_equipment_metadata(helm_t3)
        self.assertEqual(meta_t3["stat_modifiers"].get("per"), -1)

        # Tier 1 full greathelm (even with 1.45x tier multiplier)
        helm_t1 = gen_headwear("fantasy", tier=1, archetype="full_greathelm")
        meta_t1 = parse_equipment_metadata(helm_t1)
        # Strictly capped at -1 (never -2 or worse)
        self.assertEqual(meta_t1["stat_modifiers"].get("per"), -1)

        # Equipped attributes reflect exactly -1 PER and -4 base accuracy
        equipped_attrs = calculate_combat_attributes(self.char_data, [helm_t3])
        self.assertEqual(equipped_attrs["per"], 4)
        # PER drops by 1 -> accuracy drops by 4 (base_acc = 60 + per*4 + agi*2)
        self.assertEqual(equipped_attrs["base_acc"], base_acc - 4)

    # ──────────────────────────────────────────────────────────────────────────
    # 4. 🩹 Cosmetic Garment Durability / Degradation Under Direct Combat
    # ──────────────────────────────────────────────────────────────────────────
    def test_unarmored_combat_inflicts_temporary_torn_clothes_debuff(self):
        session = {
            "nearby_enemies": [{
                "name": "Goblin Berserker",
                "archetype": "Brute",
                "level": 3,
                "hp": 40,
                "max_hp": 40,
                "stats": {"STR": 8, "AGI": 5, "END": 6, "INT": 3, "PER": 5, "CHA": 3, "LUK": 4}
            }],
            "current_npcs": []
        }
        unarmored_player = dict(self.char_data)
        unarmored_player["status_effects"] = []

        actions = [{
            "user_id": self.user_id,
            "char": unarmored_player,
            "stat": "STR",
            "tier": "fail",
            "choice_type": "MELEE_SLASHING_PIERCING"
        }]

        # Run combat turn where enemy strikes unarmored player with heavy damage
        turn_result = precompute_combat_turn(session, [unarmored_player], actions)

        # Verify status effect was inflicted
        status_list = unarmored_player.get("status_effects", [])
        has_torn_status = any("Torn / Scorched Clothes [-1 CHA]" in s for s in status_list)
        self.assertTrue(has_torn_status, f"Expected torn clothes status in {status_list}")

        # Verify log contains narrative notice
        log_text = " ".join(turn_result["combat_log"])
        self.assertIn("civilian clothes were torn and scorched", log_text)

        # Verify attributes reflect -1 CHA
        attrs_degraded = calculate_combat_attributes(unarmored_player, [])
        self.assertEqual(attrs_degraded["cha"], 4)  # Base 5 - 1 = 4

    def test_armored_combat_prevents_garment_degradation(self):
        # When wearing combat armor, civilian clothes are shielded
        plate = gen_armor("fantasy", archetype="plate")
        plate_id = db.add_item(self.user_id, plate["name"], plate["item_type"], plate["effect"], plate["slot_cost"])
        db.equip_item(self.user_id, plate_id, "Armor")

        session = {
            "nearby_enemies": [{
                "name": "Goblin Berserker",
                "archetype": "Brute",
                "level": 3,
                "hp": 40,
                "max_hp": 40,
                "stats": {"STR": 8, "AGI": 5, "END": 6, "INT": 3, "PER": 5, "CHA": 3, "LUK": 4}
            }],
            "current_npcs": []
        }
        armored_player = dict(self.char_data)
        armored_player["status_effects"] = []

        actions = [{
            "user_id": self.user_id,
            "char": armored_player,
            "stat": "STR",
            "tier": "fail",
            "choice_type": "MELEE_SLASHING_PIERCING"
        }]

        precompute_combat_turn(session, [armored_player], actions)
        status_list = armored_player.get("status_effects", [])
        has_torn_status = any("Torn / Scorched Clothes" in s for s in status_list)
        self.assertFalse(has_torn_status, "Armored player should not suffer torn civilian clothes debuff")

    def test_torn_clothes_status_strictly_temporary_decay(self):
        # Test natural 2-turn countdown and expiration via tick_status_timers
        entity = {"status_effects": ["Torn / Scorched Clothes [-1 CHA] [2 turns]"], "hp": 50}

        # Turn 1
        tick_status_timers(entity)
        self.assertEqual(entity["status_effects"], ["Torn / Scorched Clothes [-1 CHA] [1 turn]"])

        # Turn 2
        tick_status_timers(entity)
        self.assertEqual(entity["status_effects"], [])  # Completely expired


if __name__ == "__main__":
    unittest.main()
