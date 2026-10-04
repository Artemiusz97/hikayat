import unittest
from mechanics.social.attributes import calculate_combat_attributes, format_combat_attributes_text
import character_data as cd

class TestCombatAttributes(unittest.TestCase):
    def test_baseline_human_attributes(self):
        # Baseline human (all SPECIAL stats = 1)
        char = {
            "str_": 1, "per_": 1, "end_": 1,
            "cha": 1, "int_": 1, "agi": 1, "luk": 1
        }
        attrs = calculate_combat_attributes(char)

        # Expected:
        # ATK:  10 + 10(1) + 2(1) = 22
        # DEF:  10 + 8(1) + 4(1)  = 22
        # MATK: 10 + 10(1) + 2(1) = 22
        # MDEF: 10 + 8(1) + 4(1)  = 22
        # ACC:  60 + 4(1) + 2(1)  = 66%
        # MACC: 60 + 4(1) + 2(1)  = 66%
        # EVA:  5 + 4(1) + 2(1)   = 11%
        self.assertEqual(attrs["atk"], 22)
        self.assertEqual(attrs.get("base_dt", 0) + attrs.get("innate_phys_dt", 0), 0) # END 1 -> 0 DT
        self.assertEqual(attrs["matk"], 22)
        self.assertEqual(attrs.get("innate_magic_dt", 0), 0) # INT 1 -> 0 DT
        self.assertEqual(attrs["acc"], 66)
        self.assertEqual(attrs["macc"], 66)
        self.assertEqual(attrs["eva"], 11)

    def test_maxed_stats_attributes(self):
        # Maxed out character (all SPECIAL stats = 10)
        char = {
            "str_": 10, "per_": 10, "end_": 10,
            "cha": 10, "int_": 10, "agi": 10, "luk": 10
        }
        attrs = calculate_combat_attributes(char)

        # Expected:
        # ATK:  10 + 10(10) + 2(10) = 130
        # DEF:  10 + 8(10) + 4(10)  = 130
        # MATK: 10 + 10(10) + 2(10) = 130
        # MDEF: 10 + 8(10) + 4(10)  = 130
        # ACC:  60 + 4(10) + 2(10)  = 120%
        # MACC: 60 + 4(10) + 2(10)  = 120%
        # EVA:  5 + 4(10) + 2(10)   = 65%
        self.assertEqual(attrs["atk"], 130)
        self.assertEqual(attrs.get("base_dt", 0) + attrs.get("innate_phys_dt", 0), 3) # END 10 -> 3 DT
        self.assertEqual(attrs["matk"], 130)
        self.assertEqual(attrs.get("innate_magic_dt", 0), 3) # INT 10 -> 3 DT
        self.assertEqual(attrs["acc"], 120)
        self.assertEqual(attrs["macc"], 120)
        self.assertEqual(attrs["eva"], 65)

    def test_specialized_warrior_build(self):
        # Warrior with STR 5, END 4, AGI 2, PER 1, INT 1, CHA 1, LUK 1
        char = {
            "str_": 5, "per_": 1, "end_": 4,
            "cha": 1, "int_": 1, "agi": 2, "luk": 1
        }
        attrs = calculate_combat_attributes(char)
        # ATK: 10 + 50 + 4 = 64
        # DEF: 10 + 40 + 16 = 66
        # MATK: 10 + 10 + 2 = 22
        # MDEF: 10 + 8 + 16 = 34
        # ACC: 60 + 4 + 4 = 68%
        # MACC: 60 + 4 + 4 = 68%
        # EVA: 5 + 8 + 2 = 15%
        self.assertEqual(attrs["atk"], 64)
        self.assertEqual(attrs.get("base_dt", 0) + attrs.get("innate_phys_dt", 0), 1) # END 4 -> 1 DT
        self.assertEqual(attrs["matk"], 22)
        self.assertEqual(attrs.get("innate_magic_dt", 0), 0) # INT 1 -> 0 DT
        self.assertEqual(attrs["acc"], 68)
        self.assertEqual(attrs["macc"], 68)
        self.assertEqual(attrs["eva"], 15)

    def test_specialized_mage_build(self):
        # Mage with INT 6, PER 3, END 2, STR 1, AGI 1, CHA 1, LUK 1
        char = {
            "str_": 1, "per_": 3, "end_": 2,
            "cha": 1, "int_": 6, "agi": 1, "luk": 1
        }
        attrs = calculate_combat_attributes(char)
        # ATK: 10 + 10 + 2 = 22
        # DEF: 10 + 8 + 8 = 26
        # MATK: 10 + 60 + 6 = 76
        # MDEF: 10 + 48 + 8 = 66
        # ACC: 60 + 12 + 2 = 74%
        # MACC: 60 + 12 + 2 = 74%
        # EVA: 5 + 4 + 2 = 11%
        self.assertEqual(attrs["atk"], 22)
        self.assertEqual(attrs.get("base_dt", 0) + attrs.get("innate_phys_dt", 0), 0) # END 2 -> 0 DT
        self.assertEqual(attrs["matk"], 76)
        self.assertEqual(attrs.get("innate_magic_dt", 0), 2) # INT 6 -> 2 DT
        self.assertEqual(attrs["acc"], 74)
        self.assertEqual(attrs["macc"], 74)
        self.assertEqual(attrs["eva"], 11)

    def test_stat_dict_aliases_in_character_data(self):
        char = {"STR": 3, "PER": 2, "END": 2, "CHA": 1, "INT": 1, "AGI": 2, "LUK": 1}
        attrs = cd.calculate_combat_attributes(char)
        self.assertEqual(attrs["atk"], 10 + 30 + 4) # 44
        direct = cd.derive_combat_attributes(str_=3, per_=2, end_=2, cha=1, int_=1, agi=2, luk=1)
        self.assertEqual(direct["atk"], 44)

    def test_formatting_output(self):
        char = {
            "str_": 1, "per_": 1, "end_": 1,
            "cha": 1, "int_": 1, "agi": 1, "luk": 1
        }
        attrs = calculate_combat_attributes(char)
        text = format_combat_attributes_text(attrs)
        self.assertIn("**ATK:** 22", text)
        self.assertIn("**DT:** 0", text)
        self.assertIn("**MATK:** 22", text)
        self.assertIn("**M-DT:** 0", text)
        self.assertIn("**ACC:** 66%", text)
        self.assertIn("**MACC:** 66%", text)
        self.assertIn("**EVA:** 11%", text)

    def test_equipment_flat_and_multiplier_aggregation(self):
        char = {
            "str_": 2, "per_": 1, "end_": 2,
            "cha": 1, "int_": 1, "agi": 1, "luk": 1
        }
        # Base:
        # ATK = 10 + 20 + 2 = 32
        # DEF = 10 + 16 + 8 = 34

        # Equip a Tier 2 weapon (+25 flat ATK, +8% mult ATK, +4 ACC)
        weapon = {
            "name": "Runic Blade",
            "metadata": {
                "stat_modifiers": {"atk": 25, "atk_pct": 0.08, "acc": 4}
            }
        }
        # Equip a Tier 3 armor (+18 flat DEF, -2 EVA)
        armor = {
            "name": "Chainmail Hauberk",
            "metadata": {
                "stat_modifiers": {"eva": -2}
            }
        }

        attrs = calculate_combat_attributes(char, [weapon, armor])
        # Expected ATK = round((32 + 25) * 1.08) = round(57 * 1.08) = round(61.56) = 62
        # Expected DEF = 34 + 18 = 52
        # Expected ACC = 66 + 4 = 70%
        # Expected EVA = 11 - 2 = 9%
        self.assertEqual(attrs["atk"], 62)
        self.assertEqual(attrs["acc"], 70)
        self.assertEqual(attrs["eva"], 9)

    def test_shield_block_chance_and_formatting(self):
        char = {
            "str_": 1, "per_": 1, "end_": 1,
            "cha": 1, "int_": 1, "agi": 1, "luk": 1
        }
        shield = {
            "name": "Steel Heater Shield",
            "metadata": {
                "block_chance": 25,
                "base_dt": 16
            }
        }
        attrs = calculate_combat_attributes(char, [shield])
        self.assertEqual(attrs["block_chance"], 25)
        self.assertEqual(attrs.get("base_dt", 0), 16) # shield provides 16 base_dt

        text = format_combat_attributes_text(attrs)
        self.assertIn("**BLOCK:** 25%", text)
