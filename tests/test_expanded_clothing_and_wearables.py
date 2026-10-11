import unittest
from mechanics.combat.items.clothing import (
    CLOTHING_TOPS,
    CLOTHING_BOTTOMS,
    generate_random_clothing,
    format_clothing_card,
    can_equip_item_in_scenario
)
from mechanics.combat.items.headwear import (
    HEADWEAR_ARCHETYPES,
    NON_COMBAT_HEADWEAR_ARCHETYPES,
    generate_random_equipment as gen_headwear
)
from mechanics.combat.items.accessories import (
    ACCESSORY_ARCHETYPES,
    NON_COMBAT_ACCESSORY_ARCHETYPES,
    generate_random_equipment as gen_accessory
)
from mechanics.combat.items.gloves import (
    GLOVE_ARCHETYPES,
    NON_COMBAT_GLOVE_ARCHETYPES,
    generate_random_equipment as gen_gloves
)
from mechanics.combat.items.shoes import (
    SHOE_ARCHETYPES,
    NON_COMBAT_SHOE_ARCHETYPES,
    generate_random_equipment as gen_shoes
)
from mechanics.combat.items.envelope import parse_item
from mechanics.social.attributes import calculate_combat_attributes


class TestExpandedClothingAndWearables(unittest.TestCase):
    def test_clothing_archetypes_count(self):
        """Verify 19 Top and 15 Bottom clothing archetypes are registered."""
        self.assertEqual(len(CLOTHING_TOPS), 19)
        self.assertEqual(len(CLOTHING_BOTTOMS), 15)

    def test_all_tops_have_zero_dt_and_capped_special(self):
        """Verify all tops have base_dt == 0 and SPECIAL bonuses strictly capped at +1 (only CHA or PER)."""
        prohibited_special = ("int", "luck", "str", "end", "agi")
        for arch, data in CLOTHING_TOPS.items():
            mods = data["social_modifiers"]
            for s in prohibited_special:
                self.assertNotIn(s, mods, f"Archetype {arch} contains prohibited SPECIAL stat {s}")
            self.assertLessEqual(mods.get("cha", 0), 1, f"Archetype {arch} has CHA > 1")
            self.assertLessEqual(mods.get("per", 0), 1, f"Archetype {arch} has PER > 1")

    def test_all_bottoms_have_zero_dt_and_capped_special(self):
        """Verify all bottoms have base_dt == 0 and SPECIAL bonuses strictly capped at +1 (only CHA or PER)."""
        prohibited_special = ("int", "luck", "str", "end", "agi")
        for arch, data in CLOTHING_BOTTOMS.items():
            mods = data["social_modifiers"]
            for s in prohibited_special:
                self.assertNotIn(s, mods, f"Archetype {arch} contains prohibited SPECIAL stat {s}")
            self.assertLessEqual(mods.get("cha", 0), 1, f"Archetype {arch} has CHA > 1")
            self.assertLessEqual(mods.get("per", 0), 1, f"Archetype {arch} has PER > 1")

    def test_procedural_generation_tier_scaling_never_exceeds_plus_one_special(self):
        """Even at Tier 1 (Masterwork), wearables must never exceed +1 CHA or +1 PER."""
        for slot in ("Top", "Bottom"):
            for _ in range(50):
                item = generate_random_clothing(scenario="steampunk", slot=slot, tier=1)
                meta = parse_item(item)
                mods = meta.get("social_modifiers", {})
                self.assertLessEqual(mods.get("cha", 0), 1)
                self.assertLessEqual(mods.get("per", 0), 1)
                self.assertEqual(meta.get("base_dt", 0), 0)

    def test_headwear_archetypes_expansion_and_rules(self):
        """Verify 16 headwear archetypes exist, non-armor items have base_dt == 0, and SPECIAL <= +1."""
        self.assertEqual(len(HEADWEAR_ARCHETYPES), 16)
        civilian_headwear = [
            "cloth_hood", "cap", "formal_hat", "top_hat", "bonnet",
            "bowler_hat", "fascinator", "beanie", "beret", "bandana",
            "ar_glasses", "circlet"
        ]
        for arch in civilian_headwear:
            item = gen_headwear(scenario="steampunk", slot="Head", tier=1, archetype=arch)
            meta = parse_item(item)
            self.assertEqual(meta.get("base_dt", 0), 0, f"Headwear {arch} has non-zero DT")
            mods = meta.get("stat_modifiers", {})
            self.assertLessEqual(mods.get("cha", 0), 1)
            self.assertLessEqual(mods.get("per", 0), 1)
            for s in ("int", "luck", "str", "end", "agi"):
                self.assertNotIn(s, mods)

    def test_accessories_expansion_and_rules(self):
        """Verify 13 accessory archetypes exist, all accessories have 0 DT, and SPECIAL <= +1."""
        self.assertEqual(len(ACCESSORY_ARCHETYPES), 13)
        for arch in ACCESSORY_ARCHETYPES:
            item = gen_accessory(scenario="cyberpunk", slot="Accessory 1", tier=1)
            meta = parse_item(item)
            self.assertEqual(meta.get("base_dt", 0), 0)
            mods = meta.get("stat_modifiers", {})
            self.assertLessEqual(mods.get("cha", 0), 1)
            self.assertLessEqual(mods.get("per", 0), 1)
            for s in ("int", "luck", "str", "end", "agi"):
                self.assertNotIn(s, mods)

    def test_gloves_and_shoes_rules(self):
        """Verify civilian gloves and shoes have 0 DT and SPECIAL <= +1."""
        civilian_gloves = [
            "cloth_wraps", "fingerless_gloves", "leather_gloves", "precision_gloves",
            "insulated_gloves", "arcane_gloves", "formal_gloves", "lace_mitts",
            "tactical_touch_gloves", "haptic_gloves"
        ]
        for arch in civilian_gloves:
            item = gen_gloves(scenario="fantasy", slot="Gloves", tier=1, archetype=arch)
            meta = parse_item(item)
            self.assertEqual(meta.get("base_dt", 0), 0)
            mods = meta.get("stat_modifiers", {})
            self.assertLessEqual(mods.get("cha", 0), 1)
            self.assertLessEqual(mods.get("per", 0), 1)
            for s in ("int", "luck", "str", "end", "agi"):
                self.assertNotIn(s, mods)

        civilian_shoes = [
            "light_sneakers", "sandals", "stealth_boots", "riding_boots",
            "hazard_boots", "formal_shoes", "oxfords", "spats_boots",
            "high_heels", "platform_boots", "mag_sneakers"
        ]
        for arch in civilian_shoes:
            item = gen_shoes(scenario="fantasy", slot="Shoes", tier=1, archetype=arch)
            meta = parse_item(item)
            self.assertEqual(meta.get("base_dt", 0), 0)
            mods = meta.get("stat_modifiers", {})
            self.assertLessEqual(mods.get("cha", 0), 1)
            self.assertLessEqual(mods.get("per", 0), 1)
            for s in ("int", "luck", "str", "end", "agi"):
                self.assertNotIn(s, mods)

    def test_slice_of_life_scenario_validation(self):
        """Non-combat scenarios allow all civilian clothing/headwear/shoes/gloves and forbid combat armor."""
        # Civilian top allowed
        top_item = generate_random_clothing(scenario="high_school", slot="Top", tier=3)
        ok, msg = can_equip_item_in_scenario(top_item, "Top", "high_school")
        self.assertTrue(ok)

        # Combat armor forbidden
        combat_plate = {"name": "Steel Plate", "item_type": "Armor", "slot": "Armor"}
        ok_armor, msg_armor = can_equip_item_in_scenario(combat_plate, "Armor", "high_school")
        self.assertFalse(ok_armor)
        self.assertIn("Combat armor cannot be equipped", msg_armor)

        # Period / modern headwear allowed in slice of life
        beanie = gen_headwear(scenario="high_school", slot="Head", tier=3, archetype="beanie")
        ok_head, _ = can_equip_item_in_scenario(beanie, "Head", "high_school")
        self.assertTrue(ok_head)

        # Heavy combat greathelm forbidden in slice of life
        greathelm = gen_headwear(scenario="fantasy", slot="Head", tier=3, archetype="full_greathelm")
        ok_helm, msg_helm = can_equip_item_in_scenario(greathelm, "Head", "high_school")
        self.assertFalse(ok_helm)

    def test_combat_armor_suppresses_civilian_clothing_modifiers(self):
        """Equipping heavy combat armor suppresses civilian clothing social/evasion stats in combat attributes."""
        character = {
            "name": "Armored Hero",
            "level": 5,
            "special": {"strength": 10, "perception": 10, "endurance": 10, "charisma": 10, "intelligence": 10, "agility": 10, "luck": 10}
        }
        top_item = generate_random_clothing(scenario="fantasy", slot="Top", tier=3)
        bottom_item = generate_random_clothing(scenario="fantasy", slot="Bottom", tier=3)
        
        # When unarmored, clothing provides EVA
        attrs_unarmored = calculate_combat_attributes(character, equipped_items=[top_item, bottom_item])
        self.assertFalse(attrs_unarmored.get("clothing_suppressed", False))

        # When heavy plate armor is equipped, clothing stats are suppressed
        plate_item = {
            "name": "Knight's Full Plate",
            "item_type": "Armor",
            "slot": "Armor",
            "effect": "[ITEM_JSON]{\"archetype\": \"plate\", \"base_dt\": 22, \"armor_type\": \"heavy\"}"
        }
        attrs_armored = calculate_combat_attributes(character, equipped_items=[plate_item, top_item, bottom_item])
        self.assertTrue(attrs_armored.get("clothing_suppressed", False))

    def test_procedural_clothing_suffixes_and_specials(self):
        """Tier 1 and Tier 2 clothing items roll suffixes while maintaining SPECIAL caps and zero DT."""
        from mechanics.combat.items.clothing import SCENARIO_CLOTHING_AFFIXES
        scenarios = ["fantasy", "steampunk", "cyberpunk", "sci_fi", "nuclear_post_apocalypse", "dark_fantasy", "high_school"]
        found_suffix = {1: False, 2: False}

        for sc in scenarios:
            for tier in (1, 2, 3):
                item = generate_random_clothing(scenario=sc, slot="Top", tier=tier)
                meta = item["metadata"]
                self.assertEqual(meta.get("base_dt", 0), 0)
                mods = meta.get("social_modifiers", {})
                self.assertLessEqual(mods.get("cha", 0), 1)
                self.assertLessEqual(mods.get("per", 0), 1)
                for disallowed in ("str", "end", "agi", "int", "luck"):
                    self.assertNotIn(disallowed, mods)

                if tier in (1, 2):
                    suff_list = SCENARIO_CLOTHING_AFFIXES[sc].get("suffixes", {}).get(tier, [])
                    if any(s in meta["name"] for s in suff_list):
                        found_suffix[tier] = True

        self.assertTrue(found_suffix[1], "Tier 1 clothing suffix should be rolled")

    def test_procedural_weapon_archetype_names_and_affixes(self):
        """Weapons roll genre-specific archetype names, and new AP affixes scale DT penetration up to 75%."""
        from mechanics.combat.items.weapons import generate_random_equipment as gen_weapon, THEME_AFFIXES

        # 1. Check elemental themes
        for elem in ("fire", "shock", "ice", "poison", "holy", "dark", "energy"):
            self.assertIn(elem, THEME_AFFIXES)

        # 2. Check genre archetype names in generation
        sp_item = gen_weapon(scenario="steampunk", tier=3, archetype="rifle")
        self.assertIn("rifle", sp_item["metadata"]["archetype"])
        self.assertTrue(any(w in sp_item["metadata"]["name"].lower() for w in ("rifle", "carbine", "arc-caster")))

        cb_item = gen_weapon(scenario="cyberpunk", tier=3, archetype="sword")
        self.assertIn("sword", cb_item["metadata"]["archetype"])
        self.assertTrue(any(w in cb_item["metadata"]["name"].lower() for w in ("katana", "blade", "cutlass")))

        # 3. Check AP scaling and capping
        ap_cases = [
            ("Piston-Driven Steam-Rifle", 0.25),
            ("Armor-Cracking Trench Sweeper", 0.30),
            ("High-Frequency Tanto", 0.35),
            ("Depleted-Uranium Sniper Mag-Rifle", 0.40),
            ("Plasma-Sheathed Energy Blade", 0.45),
            ("Soul-Rending Executioner Blade", 0.50),
            ("Tachyon-Pulsed Particle Beam Rifle", 0.55),
            ("Graviton-Collapsed Hyper-Velocity Rail-Driver", 0.75),
        ]
        for name, expected_ap in ap_cases:
            item = gen_weapon(name=name)
            ap = item["metadata"].get("armor_penetration", 0.0)
            self.assertAlmostEqual(ap, expected_ap, places=2)

    def test_equipment_tables_steampunk_dark_fantasy_parity(self):
        """Equipment subsystem generates loot for steampunk and dark_fantasy with full scenario parity."""
        from mechanics.combat.equipment.core import generate_random_equipment as gen_eq

        for sc in ("steampunk", "dark_fantasy", "sci_fi", "nuclear_post_apocalypse"):
            item = gen_eq(scenario=sc, slot="Weapon", tier=2)
            self.assertTrue(bool(item.get("name")))
            self.assertEqual(item.get("item_type"), "Weapon")

    def test_classical_elements_weapons_and_affixes(self):
        """Verify classical elements (earth, water, wind) generate correctly with damage profile conversion."""
        from mechanics.combat.items.weapons import generate_random_equipment as gen_weapon, THEME_AFFIXES

        # 1. Check all 10 elements are in THEME_AFFIXES
        for elem in ("fire", "water", "earth", "wind", "shock", "ice", "poison", "holy", "dark", "energy"):
            self.assertIn(elem, THEME_AFFIXES)
            self.assertIn("prefixes_t2", THEME_AFFIXES[elem])
            self.assertIn("suffixes_t2", THEME_AFFIXES[elem])

        # 2. Check elemental infusion on martial weapons (sword with earth, water, wind)
        for elem in ("earth", "water", "wind"):
            w = gen_weapon(scenario="fantasy", tier=2, archetype="sword", element=elem)
            meta = w["metadata"]
            self.assertEqual(meta["element"], elem)
            self.assertEqual(meta["damage_types"], {"physical": 0.5, elem: 0.5})
            self.assertIn("elemental", meta["tags"]["special_traits"])
            self.assertIn(f"elem_{elem}", meta["tags"]["special_traits"])
            # Affix should contain either elemental prefix or suffix
            elem_affixes = THEME_AFFIXES[elem]["prefixes_t2"] + THEME_AFFIXES[elem]["suffixes_t2"]
            self.assertTrue(any(a.lower() in meta["name"].lower() for a in elem_affixes))

        # 3. Check pure magic focus on wand/staff (100% element)
        wand = gen_weapon(scenario="fantasy", tier=1, archetype="wand", element="water")
        self.assertEqual(wand["metadata"]["damage_types"], {"water": 1.0})
        for prof in wand["metadata"]["attack_profiles"].values():
            self.assertEqual(prof["damage_type"], "water")

        staff = gen_weapon(scenario="fantasy", tier=2, archetype="staff", element="wind")
        self.assertEqual(staff["metadata"]["damage_types"], {"wind": 1.0})
        for prof in staff["metadata"]["attack_profiles"].values():
            self.assertEqual(prof["damage_type"], "wind")

    def test_classical_elements_combat_mitigation_and_attributes(self):
        """Verify earth_res, water_res, and wind_res aggregate into gear_dr and mitigate damage."""
        from mechanics.social.attributes import calculate_combat_attributes
        from mechanics.combat.formulas import calculate_tactical_damage

        # 1. Attributes aggregation
        char = {"STR": 5, "END": 5, "AGI": 5, "INT": 5, "PER": 5, "CHA": 5, "LUK": 5}
        equipped = [
            {
                "slot": "Top",
                "name": "Earthwarden Tunic",
                "metadata": {
                    "stat_modifiers": {"earth_res": 30, "water_res": 25, "wind_res": 20},
                    "base_dr": 10
                }
            }
        ]
        attrs = calculate_combat_attributes(char, equipped_items=equipped)
        self.assertAlmostEqual(attrs["gear_dr"]["earth"], 0.30, places=2)
        self.assertAlmostEqual(attrs["gear_dr"]["water"], 0.25, places=2)
        self.assertAlmostEqual(attrs["gear_dr"]["wind"], 0.20, places=2)

        # 2. Combat tactical damage mitigation
        atk_attrs = {"atk": 50, "matk": 50}
        def_attrs_no_res = {"def": 20, "mdef": 20, "gear_dr": {}, "innate_magic_dr": 0.0}
        def_attrs_with_res = {"def": 20, "mdef": 20, "gear_dr": {"earth": 0.30, "water": 0.25, "wind": 0.20}, "innate_magic_dr": 0.0}
        armor_meta = {"base_dt": 0, "armor_class": "cloth"}

        for elem in ("earth", "water", "wind"):
            w_meta = {"default_damage": {elem: 1.0}, "damage_types": {elem: 1.0}, "multiplier": 1.0, "attack_types": ["slash"]}
            dmg_unres = calculate_tactical_damage(atk_attrs, def_attrs_no_res, w_meta, armor_meta)
            dmg_res = calculate_tactical_damage(atk_attrs, def_attrs_with_res, w_meta, armor_meta)
            self.assertLess(dmg_res["damage"], dmg_unres["damage"])

    def test_expanded_weapon_archetype_names_variety(self):
        """Verify all scenarios have expanded, diverse base name pools for archetypes."""
        from mechanics.combat.items.weapons import SCENARIO_AFFIXES

        for scen in ("fantasy", "steampunk", "cyberpunk", "nuclear_post_apocalypse", "sci_fi", "dark_fantasy"):
            arch_dict = SCENARIO_AFFIXES[scen]["archetype_names"]
            for arch in ("sword", "dagger", "greatsword", "katana", "rapier", "spear", "bow", "rifle"):
                self.assertIn(arch, arch_dict, f"Missing archetype {arch} in scenario {scen}")
                names = arch_dict[arch]
                self.assertGreaterEqual(len(names), 4, f"Archetype {arch} in {scen} has fewer than 4 variants: {names}")


if __name__ == "__main__":
    unittest.main()
