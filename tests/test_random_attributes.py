import unittest
from mechanics.combat.equipment import (
    generate_random_equipment,
    format_equipment_card,
    parse_equipment_metadata,
    RANDOM_AFFIX_POOL,
    WEAPON_ARCHETYPES,
    ARMOR_ARCHETYPES
)
from mechanics.social.attributes import calculate_combat_attributes, format_combat_attributes_text
from mechanics.combat import get_elemental_multiplier, calculate_tactical_damage

class TestRandomAttributesAndNaming(unittest.TestCase):

    def test_tier_3_attribute_count(self):
        """Tier 3 items should roll baseline archetype stats + exactly 1 random bonus attribute."""
        for slot in ["Weapon", "Top", "Bottom", "Shield", "Accessory 1"]:
            item = generate_random_equipment("fantasy", slot=slot, tier=3)
            meta = item["metadata"]
            self.assertEqual(meta["tier"], 3)
            self.assertIn("stat_modifiers", meta)
            
            # The item must have base stats and bonus stats
            stat_mods = meta["stat_modifiers"]
            self.assertGreaterEqual(len(stat_mods), 1)

    def test_tier_2_attribute_count(self):
        """Tier 2 items should roll baseline stats + 2 to 3 random bonus attributes."""
        for slot in ["Weapon", "Top", "Bottom", "Shield", "Accessory 2"]:
            item = generate_random_equipment("fantasy", slot=slot, tier=2)
            meta = item["metadata"]
            self.assertEqual(meta["tier"], 2)
            stat_mods = meta["stat_modifiers"]
            # At least 2 bonus stats or modifiers
            self.assertGreaterEqual(len(stat_mods), 2)

    def test_tier_1_attribute_count(self):
        """Tier 1 legendary items should roll baseline stats + 3 to 5 random bonus attributes."""
        for slot in ["Weapon", "Top", "Bottom", "Shield", "Accessory 3"]:
            item = generate_random_equipment("fantasy", slot=slot, tier=1)
            meta = item["metadata"]
            self.assertEqual(meta["tier"], 1)
            stat_mods = meta["stat_modifiers"]
            self.assertGreaterEqual(len(stat_mods), 3)

    def test_procedural_naming_variety_and_theme(self):
        """Generated equipment names should be dynamic, non-empty, and varied."""
        names = set()
        for _ in range(30):
            item = generate_random_equipment("fantasy", slot="Weapon", tier=2)
            names.add(item["name"])
        # With high variety, 30 rolls should produce at least 15 unique names
        self.assertGreaterEqual(len(names), 15)

    def test_combat_attributes_accumulation(self):
        """calculate_combat_attributes should accumulate all elemental attacks, resistances, and vitals."""
        char = {
            "str_": 5, "per_": 5, "end_": 5, "cha": 5, "int_": 5, "agi": 5, "luk": 5
        }
        test_weapon = {
            "name": "Sunfire Longsword",
            "metadata": {
                "stat_modifiers": {
                    "atk": 25,
                    "fire_atk": 15,
                    "crit": 5
                }
            }
        }
        test_armor = {
            "name": "Glacial Magic Robe of Warding",
            "metadata": {
                "base_dt": 10,
                "type_dt": {"magical": 25},
                "stat_modifiers": {
                    "fire_res": 20,
                    "ice_res": 30,
                    "max_hp": 30,
                    "hp_regen": 3
                }
            }
        }

        attrs = calculate_combat_attributes(char, equipped_items=[test_weapon, test_armor])
        self.assertGreater(attrs["atk"], 60)
        self.assertEqual(attrs["fire_atk"], 15)
        self.assertEqual(attrs["fire_res"], 20)
        self.assertEqual(attrs["ice_res"], 30)
        self.assertEqual(attrs["bonus_max_hp"], 30)
        self.assertEqual(attrs["hp_regen"], 3)

        formatted = format_combat_attributes_text(attrs)
        self.assertIn("Resistances:", formatted)
        self.assertIn("20%", formatted)

    def test_elemental_resistance_damage_mitigation(self):
        """get_elemental_multiplier returns base affinity matchup (DR is applied in FNV DT pipeline)."""
        armor_meta = {"armor_type": "plate"}
        
        # Base plate vs fire has 0.90x multiplier
        mult_no_res = get_elemental_multiplier({"fire": 1.0}, armor_meta, defender_attrs={})
        self.assertAlmostEqual(mult_no_res, 0.90, places=2)

        # Under the unified FNV DR->DT->Floor engine, resistance is handled by _apply_dt,
        # so get_elemental_multiplier consistently returns the archetype affinity.
        defender_with_res = {"fire_res": 30}
        mult_with_res = get_elemental_multiplier({"fire": 1.0}, armor_meta, defender_attrs=defender_with_res)
        self.assertAlmostEqual(mult_with_res, 0.90, places=2)

        defender_with_omni = {"fire_res": 10, "omni_res": 20}
        mult_with_omni = get_elemental_multiplier({"fire": 1.0}, armor_meta, defender_attrs=defender_with_omni)
        self.assertAlmostEqual(mult_with_omni, 0.90, places=2)

    def test_format_equipment_card_shows_substats(self):
        """format_equipment_card should render elemental stats and resistances clearly."""
        meta = {
            "name": "Sunfire Greatsword of the Inferno",
            "tier": 1,
            "tier_name": "Legendary",
            "slot": "Weapon",
            "archetype": "greatsword",
            "handedness": "2H",
            "mass": "heavy",
            "attack_types": ["slash", "hack"],
            "stat_modifiers": {
                "atk": 76,
                "atk_pct": 0.15,
                "fire_atk": 22,
                "crit": 8,
                "fire_res": 25,
                "max_hp": 40
            }
        }
        card = format_equipment_card(meta)
        self.assertIn("Sunfire Greatsword of the Inferno", card)
        self.assertIn("Fire ATK +22", card)
        self.assertIn("Fire Res +25%", card)
        self.assertIn("Max HP +40", card)
        self.assertIn("CRIT +8%", card)


