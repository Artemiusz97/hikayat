import unittest
from mechanics.combat.items import (
    generate_random_equipment,
    format_equipment_card,
    parse_item,
    HEADWEAR_ARCHETYPES,
    NON_COMBAT_HEADWEAR_ARCHETYPES
)
from mechanics.social.attributes import calculate_combat_attributes
import character_data as cd

class TestHeadwearEquipment(unittest.TestCase):
    def test_head_slot_in_constants(self):
        """Verify Head slot is registered in EQUIPMENT_SLOTS and DEFAULT_EQUIP_SLOT_FOR_ITEM_TYPE."""
        self.assertIn("Head", cd.EQUIPMENT_SLOTS)
        self.assertIn("Head", cd.EQUIPMENT_SLOT_EMOJI)
        self.assertEqual(cd.DEFAULT_EQUIP_SLOT_FOR_ITEM_TYPE.get("Head"), "Head")
        self.assertEqual(cd.DEFAULT_EQUIP_SLOT_FOR_ITEM_TYPE.get("Helmet"), "Head")
        self.assertEqual(cd.DEFAULT_EQUIP_SLOT_FOR_ITEM_TYPE.get("Headwear"), "Head")
        # Ensure ordering constraint remains valid
        self.assertLess(cd.EQUIPMENT_SLOTS.index("Armor"), cd.EQUIPMENT_SLOTS.index("Top"))

    def test_all_headwear_archetypes_generation(self):
        """Verify all 8 headwear archetypes generate valid [ITEM_JSON] items with proper slots and stats."""
        expected_archetypes = [
            "cloth_hood", "cap", "open_helm", "full_greathelm",
            "tech_visor", "gas_mask", "circlet", "formal_hat"
        ]
        self.assertEqual(len(HEADWEAR_ARCHETYPES), 8)
        for arch in expected_archetypes:
            self.assertIn(arch, HEADWEAR_ARCHETYPES)
            from mechanics.combat.items.headwear import generate_random_equipment as _gen_h
            arch_item = _gen_h(scenario="fantasy", slot="Head", tier=3, archetype=arch)
            self.assertEqual(arch_item["item_type"], "Headwear")
            self.assertEqual(arch_item["slot"], "Head")
            meta = parse_item(arch_item)
            self.assertEqual(meta["archetype"], arch)
            self.assertIn("tags", meta)
            self.assertIn("stat_modifiers", meta)
            self.assertFalse(arch_item["name"].startswith("Tier 3"))

    def test_headwear_tier_scaling(self):
        """Verify tier scaling increases DT and stat modifiers appropriately."""
        from mechanics.combat.items.headwear import generate_random_equipment as _gen_h
        
        t3_helm = parse_item(_gen_h(scenario="fantasy", slot="Head", tier=3, archetype="full_greathelm"))
        t1_helm = parse_item(_gen_h(scenario="fantasy", slot="Head", tier=1, archetype="full_greathelm"))
        self.assertGreaterEqual(t1_helm["base_dt"], t3_helm["base_dt"])
        
        t3_visor = parse_item(_gen_h(scenario="cyberpunk", slot="Head", tier=3, archetype="tech_visor"))
        t1_visor = parse_item(_gen_h(scenario="cyberpunk", slot="Head", tier=1, archetype="tech_visor"))
        self.assertGreaterEqual(t1_visor["stat_modifiers"].get("acc", 0), t3_visor["stat_modifiers"].get("acc", 0))

    def test_genre_affixes_across_all_genres(self):
        """Verify headwear has rich procedural names across all 7 scenarios."""
        genres = ["fantasy", "steampunk", "cyberpunk", "nuclear_post_apocalypse", "sci_fi", "dark_fantasy", "high_school"]
        
        for genre in genres:
            item = generate_random_equipment(scenario=genre, slot="Head", tier=2)
            name = item["name"]
            self.assertFalse(name.startswith("Tier 2"), f"Headwear {name} in {genre} used raw placeholder!")
            self.assertTrue(len(name.split()) >= 2, f"Headwear {name} has fewer than 2 words!")

    def test_non_combat_scenario_safety(self):
        """Verify slice of life / high school settings generate safe civilian headwear."""
        for _ in range(20):
            item = generate_random_equipment(scenario="high_school_drama", slot="Head", tier=3)
            meta = parse_item(item)
            self.assertIn(meta["archetype"], NON_COMBAT_HEADWEAR_ARCHETYPES)
            self.assertNotEqual(meta["archetype"], "full_greathelm")

    def test_slot_routing_in_generate_random_equipment(self):
        """Verify slot parameter cleanly routes to headwear generator."""
        h = generate_random_equipment(scenario="fantasy", slot="Head")
        self.assertEqual(h["slot"], "Head")
        self.assertEqual(h["item_type"], "Headwear")

    def test_equipment_card_formatting(self):
        """Verify card formatting handles headwear cleanly."""
        h = generate_random_equipment(scenario="cyberpunk", slot="Head", tier=2)
        card = format_equipment_card(parse_item(h))
        self.assertIn("Headwear", card)
        self.assertIn("Protection & Utility", card)

    def test_headwear_combat_attributes_aggregation(self):
        """Verify headwear contributes base DT, type DT, and stat modifiers to character combat attributes."""
        character = {
            "name": "Knight Commander",
            "level": 5,
            "special": {"strength": 10, "perception": 10, "endurance": 10, "charisma": 10, "intelligence": 10, "agility": 10, "luck": 10}
        }
        
        helm = {
            "name": "Crusader's Steel Greathelm",
            "item_type": "Headwear",
            "slot": "Head",
            "archetype": "full_greathelm",
            "base_dt": 7,
            "type_dt": {"physical": 10, "ballistic": 8},
            "stat_modifiers": {"base_dt": 7, "eva": -2, "per": -1}
        }
        
        attrs = calculate_combat_attributes(character, equipped_items=[helm])
        self.assertEqual(attrs.get("base_dt"), 7)
        self.assertEqual(attrs.get("type_dt", {}).get("physical"), 10)
        self.assertEqual(attrs.get("type_dt", {}).get("ballistic"), 8)

if __name__ == "__main__":
    unittest.main()
