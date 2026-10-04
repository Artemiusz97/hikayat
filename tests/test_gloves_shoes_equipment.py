import unittest
from mechanics.combat.items import (
    generate_random_equipment,
    format_equipment_card,
    parse_item,
    GLOVE_ARCHETYPES,
    SHOE_ARCHETYPES,
    ARMOR_ARCHETYPES,
    SHIELD_ARCHETYPES,
    ACCESSORY_ARCHETYPES,
    NON_COMBAT_SHIELD_ARCHETYPES,
    NON_COMBAT_ACCESSORY_ARCHETYPES,
    NON_COMBAT_GLOVE_ARCHETYPES,
    NON_COMBAT_SHOE_ARCHETYPES
)
from mechanics.social.attributes import calculate_combat_attributes

class TestGlovesShoesAndEquipment(unittest.TestCase):
    def test_all_glove_archetypes_generation(self):
        """Verify all 8 glove archetypes generate valid [ITEM_JSON] items with proper slots and stats."""
        expected_archetypes = [
            "cloth_wraps", "fingerless_gloves", "leather_gloves", "precision_gloves",
            "heavy_gauntlets", "insulated_gloves", "arcane_gloves", "formal_gloves"
        ]
        self.assertEqual(len(GLOVE_ARCHETYPES), 8)
        for arch in expected_archetypes:
            self.assertIn(arch, GLOVE_ARCHETYPES)
            item = generate_random_equipment(scenario="fantasy", slot="Gloves", tier=3)
            # Force generate each archetype
            from mechanics.combat.items.gloves import generate_random_equipment as _gen_g
            arch_item = _gen_g(scenario="fantasy", slot="Gloves", tier=3, archetype=arch)
            self.assertEqual(arch_item["item_type"], "Gloves")
            self.assertEqual(arch_item["slot"], "Gloves")
            meta = parse_item(arch_item)
            self.assertEqual(meta["archetype"], arch)
            self.assertIn("tags", meta)
            self.assertIn("stat_modifiers", meta)
            self.assertFalse(arch_item["name"].startswith("Tier 3"))

    def test_all_shoe_archetypes_generation(self):
        """Verify all 8 shoe archetypes generate valid [ITEM_JSON] items with proper slots and stats."""
        expected_archetypes = [
            "light_sneakers", "sandals", "combat_boots", "heavy_greaves",
            "stealth_boots", "riding_boots", "hazard_boots", "formal_shoes"
        ]
        self.assertEqual(len(SHOE_ARCHETYPES), 8)
        for arch in expected_archetypes:
            self.assertIn(arch, SHOE_ARCHETYPES)
            from mechanics.combat.items.shoes import generate_random_equipment as _gen_s
            arch_item = _gen_s(scenario="fantasy", slot="Shoes", tier=3, archetype=arch)
            self.assertEqual(arch_item["item_type"], "Shoes")
            self.assertEqual(arch_item["slot"], "Shoes")
            meta = parse_item(arch_item)
            self.assertEqual(meta["archetype"], arch)
            self.assertIn("tags", meta)
            self.assertIn("stat_modifiers", meta)
            self.assertFalse(arch_item["name"].startswith("Tier 3"))

    def test_glove_and_shoe_tier_scaling(self):
        """Verify tier scaling increases DT and stat modifiers appropriately."""
        from mechanics.combat.items.gloves import generate_random_equipment as _gen_g
        from mechanics.combat.items.shoes import generate_random_equipment as _gen_s
        
        t3_glove = parse_item(_gen_g(scenario="fantasy", slot="Gloves", tier=3, archetype="heavy_gauntlets"))
        t1_glove = parse_item(_gen_g(scenario="fantasy", slot="Gloves", tier=1, archetype="heavy_gauntlets"))
        self.assertGreaterEqual(t1_glove["base_dt"], t3_glove["base_dt"])
        
        t3_shoe = parse_item(_gen_s(scenario="fantasy", slot="Shoes", tier=3, archetype="heavy_greaves"))
        t1_shoe = parse_item(_gen_s(scenario="fantasy", slot="Shoes", tier=1, archetype="heavy_greaves"))
        self.assertGreaterEqual(t1_shoe["base_dt"], t3_shoe["base_dt"])

    def test_genre_affixes_across_all_genres(self):
        """Verify armors, shields, accessories, gloves, and shoes have rich genre names (no 'Tier X Archetype')."""
        genres = ["fantasy", "steampunk", "cyberpunk", "nuclear_post_apocalypse", "sci_fi", "dark_fantasy", "high_school"]
        slots = ["Armor", "Shield", "Accessory 1", "Gloves", "Shoes"]
        
        for genre in genres:
            for slot in slots:
                item = generate_random_equipment(scenario=genre, slot=slot, tier=2)
                name = item["name"]
                # Must not be raw placeholder
                self.assertFalse(name.startswith("Tier 2"), f"Item {name} in {genre}/{slot} used raw placeholder!")
                self.assertTrue(len(name.split()) >= 2, f"Item {name} has fewer than 2 words!")

    def test_non_combat_scenario_safety(self):
        """Verify slice of life / high school settings generate non-combat items."""
        # Shields in non-combat settings should roll satchels, backpacks, etc.
        shield = generate_random_equipment(scenario="high_school_drama", slot="Shield", tier=3)
        s_meta = parse_item(shield)
        self.assertIn(s_meta["archetype"], NON_COMBAT_SHIELD_ARCHETYPES)
        self.assertEqual(s_meta["block_chance"], 0)
        
        # Accessories in non-combat settings
        acc = generate_random_equipment(scenario="high_school_drama", slot="Accessory 1", tier=3)
        a_meta = parse_item(acc)
        self.assertIn(a_meta["archetype"], NON_COMBAT_ACCESSORY_ARCHETYPES)
        
        # Armor requested in non-combat settings should route to clothing (Top) rather than combat plate
        armor = generate_random_equipment(scenario="high_school_drama", slot="Armor", tier=3)
        self.assertEqual(armor["item_type"], "Clothing")
        self.assertEqual(armor["slot"], "Top")

    def test_slot_routing_in_generate_random_equipment(self):
        """Verify slot parameter cleanly routes to proper generator."""
        g = generate_random_equipment(scenario="fantasy", slot="Gloves")
        self.assertEqual(g["slot"], "Gloves")
        self.assertEqual(g["item_type"], "Gloves")
        
        s = generate_random_equipment(scenario="fantasy", slot="Shoes")
        self.assertEqual(s["slot"], "Shoes")
        self.assertEqual(s["item_type"], "Shoes")

    def test_equipment_card_formatting(self):
        """Verify card formatting handles gloves, shoes, armor, and shields cleanly."""
        g = generate_random_equipment(scenario="cyberpunk", slot="Gloves", tier=2)
        g_card = format_equipment_card(parse_item(g))
        self.assertIn("Handwear", g_card)
        
        s = generate_random_equipment(scenario="steampunk", slot="Shoes", tier=2)
        s_card = format_equipment_card(parse_item(s))
        self.assertIn("Footwear", s_card)

    def test_offhand_weapon_def_leak_protection(self):
        """Verify an off-hand weapon in the Shield slot does not leak DEF into player base DT."""
        character = {
            "name": "Duelist",
            "level": 10,
            "special": {"strength": 10, "perception": 10, "endurance": 10, "charisma": 10, "intelligence": 10, "agility": 10, "luck": 10}
        }
        
        # Off-hand weapon with def=10 in stat_modifiers
        offhand_weapon = {
            "name": "Defensive Parrying Dagger",
            "item_type": "Weapon",
            "slot": "Shield",
            "archetype": "dagger",
            "multiplier": 0.85,
            "stat_modifiers": {"def": 10, "acc": 2}
        }
        
        attrs = calculate_combat_attributes(character, equipped_items=[offhand_weapon])
        # Weapons should never contribute to base DT
        self.assertEqual(attrs.get("base_dt", 0), 0)

    def test_gloves_and_shoes_dt_and_stat_aggregation(self):
        """Verify gloves and shoes contribute base DT and stat modifiers to character combat attributes."""
        character = {
            "name": "Iron Sentinel",
            "level": 5,
            "special": {"strength": 10, "perception": 10, "endurance": 10, "charisma": 10, "intelligence": 10, "agility": 10, "luck": 10}
        }
        
        glove = {
            "name": "Steel Gauntlets",
            "item_type": "Gloves",
            "slot": "Gloves",
            "archetype": "heavy_gauntlets",
            "base_dt": 6,
            "type_dt": {"physical": 8},
            "stat_modifiers": {"base_dt": 6, "acc": -1, "eva": -2}
        }
        shoe = {
            "name": "Steel Sabatons",
            "item_type": "Shoes",
            "slot": "Shoes",
            "archetype": "heavy_greaves",
            "base_dt": 7,
            "type_dt": {"physical": 10},
            "stat_modifiers": {"base_dt": 7, "eva": -3}
        }
        
        attrs = calculate_combat_attributes(character, equipped_items=[glove, shoe])
        self.assertEqual(attrs.get("base_dt"), 13)
        self.assertEqual(attrs.get("type_dt", {}).get("physical"), 18)

if __name__ == "__main__":
    unittest.main()
