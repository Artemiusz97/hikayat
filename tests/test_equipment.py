import unittest
import db
import character_data as cd
from mechanics.combat.equipment import (
    generate_random_equipment,
    parse_equipment_metadata,
    build_equipment_effect_str,
    format_equipment_card,
    is_two_handed,
    WEAPON_ARCHETYPES,
    ARMOR_ARCHETYPES,
    SHIELD_ARCHETYPES
)

class TestEquipmentSystem(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.user_id = 998877665
        chars = db.get_user_characters(self.user_id)
        for c in chars:
            db.delete_character(self.user_id, c["id"])

    def tearDown(self):
        chars = db.get_user_characters(self.user_id)
        for c in chars:
            db.delete_character(self.user_id, c["id"])

    def test_procedural_generation_all_scenarios(self):
        scenarios = ["fantasy", "scifi", "cyberpunk", "postapoc"]
        slots = ["Weapon", "Shield", "Top", "Bottom", "Gloves", "Shoes", "Accessory 1"]

        for scen in scenarios:
            for slot in slots:
                item = generate_random_equipment(scenario=scen, slot=slot, tier=2)
                self.assertIsNotNone(item)
                self.assertIn("name", item)
                self.assertIn("effect", item)
                self.assertTrue(item["effect"].startswith("[GEAR_JSON]"))

                meta = parse_equipment_metadata(item)
                self.assertEqual(meta["tier"], 2)
                self.assertEqual(meta["slot"], slot)
                self.assertIn("archetype", meta)
                self.assertIn("stat_modifiers", meta)

    def test_tier_multipliers_and_rarity(self):
        t3_item = generate_random_equipment("fantasy", "Weapon", tier=3)
        t2_item = generate_random_equipment("fantasy", "Weapon", tier=2)
        t1_item = generate_random_equipment("fantasy", "Weapon", tier=1)

        m3 = parse_equipment_metadata(t3_item)
        m2 = parse_equipment_metadata(t2_item)
        m1 = parse_equipment_metadata(t1_item)

        self.assertEqual(m3["tier"], 3)
        self.assertEqual(m2["tier"], 2)
        self.assertEqual(m1["tier"], 1)

        # Higher tiers have percentage bonuses (atk_pct or matk_pct)
        s2 = m2.get("stat_modifiers", {})
        s1 = m1.get("stat_modifiers", {})
        self.assertTrue("atk_pct" in s2 or "matk_pct" in s2 or "def_pct" in s2)
        self.assertTrue("atk_pct" in s1 or "matk_pct" in s1 or "def_pct" in s1)
        self.assertIn("crit", s1)

    def test_weapon_attributes_mass_and_handedness(self):
        # 1H Dagger
        dagger_meta = WEAPON_ARCHETYPES["dagger"]
        self.assertEqual(dagger_meta["handedness"], "1H")
        self.assertEqual(dagger_meta["mass"], "light")
        self.assertIn("thrust", dagger_meta["attack_types"])

        # 2H Greatsword
        gs_meta = WEAPON_ARCHETYPES["greatsword"]
        self.assertEqual(gs_meta["handedness"], "2H")
        self.assertEqual(gs_meta["mass"], "heavy")
        self.assertIn("slash", gs_meta["attack_types"])

        # is_two_handed helper
        self.assertTrue(is_two_handed("Sunfire Greatsword"))
        self.assertTrue(is_two_handed("Heavy Plasma Cannon"))
        self.assertFalse(is_two_handed("Iron Dagger"))

    def test_two_handed_weapon_and_shield_mutual_exclusion(self):
        base_stats = {"STR": 5, "PER": 2, "END": 4, "CHA": 1, "INT": 1, "AGI": 2, "LUK": 1}
        char = db.create_character(
            user_id=self.user_id,
            name="TwoHandTester",
            char_class="Warrior",
            class_description="Testing 2H slots",
            stats=base_stats
        )

        # Generate a 2H weapon, a 1H weapon, and a shield
        t_2h = generate_random_equipment("fantasy", "Weapon", tier=3)
        t_2h["name"] = "Iron Greatsword"
        t_2h["metadata"]["name"] = "Iron Greatsword"
        t_2h["metadata"]["archetype"] = "greatsword"
        t_2h["metadata"]["handedness"] = "2H"
        t_2h["effect"] = build_equipment_effect_str(t_2h["metadata"])

        t_1h = generate_random_equipment("fantasy", "Weapon", tier=3)
        t_1h["name"] = "Iron Shortsword"
        t_1h["metadata"]["name"] = "Iron Shortsword"
        t_1h["metadata"]["archetype"] = "shortsword"
        t_1h["metadata"]["handedness"] = "1H"
        t_1h["effect"] = build_equipment_effect_str(t_1h["metadata"])

        t_shield = generate_random_equipment("fantasy", "Shield", tier=3)
        t_shield["name"] = "Steel Heater Shield"
        t_shield["metadata"]["name"] = "Steel Heater Shield"
        t_shield["metadata"]["archetype"] = "heater_shield"
        t_shield["metadata"]["handedness"] = "1H"
        t_shield["effect"] = build_equipment_effect_str(t_shield["metadata"])

        id_2h = db.add_item(self.user_id, t_2h["name"], "Weapon", t_2h["effect"], force=True)
        id_1h = db.add_item(self.user_id, t_1h["name"], "Weapon", t_1h["effect"], force=True)
        id_shield = db.add_item(self.user_id, t_shield["name"], "Shield", t_shield["effect"], force=True)

        # 1. Equip 1H weapon & Shield
        db.equip_item(self.user_id, id_1h, "Weapon")
        db.equip_item(self.user_id, id_shield, "Shield")

        equip = db.get_equipment(self.user_id)
        self.assertIsNotNone(equip["Weapon"])
        self.assertIsNotNone(equip["Shield"])
        self.assertEqual(equip["Weapon"]["id"], id_1h)
        self.assertEqual(equip["Shield"]["id"], id_shield)

        # 2. Equip 2H weapon -> Shield MUST be automatically unequipped!
        db.equip_item(self.user_id, id_2h, "Weapon")

        equip_after = db.get_equipment(self.user_id)
        self.assertEqual(equip_after["Weapon"]["id"], id_2h)
        self.assertIsNone(equip_after["Shield"], "Shield must be automatically unequipped when wielding a 2H weapon!")

        # 3. Equip Shield while holding 2H weapon -> 2H weapon MUST be automatically unequipped!
        db.equip_item(self.user_id, id_shield, "Shield")
        equip_shield_first = db.get_equipment(self.user_id)
        self.assertEqual(equip_shield_first["Shield"]["id"], id_shield)
        self.assertIsNone(equip_shield_first["Weapon"], "2H weapon must be unequipped when equipping a shield!")

    def test_format_equipment_card(self):
        item = generate_random_equipment("fantasy", "Weapon", tier=1)
        meta = parse_equipment_metadata(item)
        card = format_equipment_card(meta)
        self.assertIn("Legendary", card)
        self.assertIn("**Slot:** Weapon", card)
        self.assertIn("ATK", card)

    def test_build_item_inspect_embed(self):
        from cogs.inventory import build_item_inspect_embed
        # 1. Preset starting staff with text description
        staff_item = {
            "id": 999,
            "name": "Arcane Staff",
            "item_type": "Magical Implement",
            "effect": "Focus crystal staff that amplifies spells.",
            "slot": "Weapon",
            "slot_cost": 1,
            "equipped": 1
        }
        embed = build_item_inspect_embed(staff_item, self.user_id)
        self.assertIn("Staff", embed.description)
        self.assertIn("Attack Modes", embed.description)
        self.assertIn("Focus crystal staff that amplifies spells.", [f.value for f in embed.fields])

        # 2. Preset robe with text description
        robe_item = {
            "id": 1000,
            "name": "Aetherwoven Robe",
            "item_type": "Armor",
            "effect": "A midnight-blue robe threaded with starlight ripples.",
            "slot": "Top",
            "slot_cost": 2,
            "equipped": 1
        }
        embed_robe = build_item_inspect_embed(robe_item, self.user_id)
        self.assertIn("Base DT", embed_robe.description)
        self.assertIn("A midnight-blue robe threaded with starlight ripples.", [f.value for f in embed_robe.fields])
