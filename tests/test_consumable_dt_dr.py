import unittest
from mechanics.combat.items.consumables import (
    POTION_SCALING,
    FOOD_SCALING,
    generate_procedural_potion,
    generate_procedural_food,
    parse_item_effect,
    parse_consumable_metadata
)
from mechanics.social.attributes import calculate_combat_attributes
from mechanics.combat import calculate_tactical_damage


class TestConsumableDtDrIntegration(unittest.TestCase):

    def test_potion_and_food_scaling_tables(self):
        self.assertEqual(POTION_SCALING['defense_buff'][3], 4)
        self.assertEqual(POTION_SCALING['resistance_buff'][3], 0.10)
        self.assertEqual(POTION_SCALING['attack_buff'][3], 0.15)
        self.assertEqual(POTION_SCALING['defense_buff'][1], 14)
        self.assertEqual(POTION_SCALING['resistance_buff'][1], 0.35)
        self.assertEqual(POTION_SCALING['attack_buff'][1], 0.40)

        self.assertEqual(FOOD_SCALING['defense_buff'][3], 2)
        self.assertEqual(FOOD_SCALING['resistance_buff'][3], 0.05)
        self.assertEqual(FOOD_SCALING['attack_buff'][3], 0.08)
        self.assertEqual(FOOD_SCALING['defense_buff'][1], 8)
        self.assertEqual(FOOD_SCALING['resistance_buff'][1], 0.18)
        self.assertEqual(FOOD_SCALING['attack_buff'][1], 0.25)

    def test_generate_procedural_potion_buffs_and_desc(self):
        potion = generate_procedural_potion(
            tier=2,
            effect_tags=['defense_buff', 'attack_buff'],
            genre='fantasy'
        )
        meta = parse_consumable_metadata(potion)
        self.assertIsNotNone(meta)
        buffs = meta.get('buffs', {})
        self.assertEqual(buffs.get('dt'), 8)
        self.assertEqual(buffs.get('atk_pct'), 0.25)
        self.assertIn('+8 DT', potion['description'])
        self.assertIn('+25% ATK', potion['description'])

    def test_generate_procedural_food_buffs_and_desc(self):
        food = generate_procedural_food(
            tier=2,
            taste_tags=['savory', 'comfort'],
            effect_tags=['defense_buff', 'attack_buff'],
            genre='fantasy'
        )
        meta = parse_consumable_metadata(food)
        self.assertIsNotNone(meta)
        buffs = meta.get('buffs', {})
        self.assertEqual(buffs.get('dt'), 4)
        self.assertEqual(buffs.get('atk_pct'), 0.15)
        self.assertIn('+4 DT', food['description'])
        self.assertIn('+15% ATK', food['description'])

    def test_calculate_combat_attributes_with_active_buffs(self):
        char = {
            'STR': 10, 'AGI': 10, 'INT': 10, 'PER': 10, 'END': 10, 'CHA': 10, 'LUK': 10,
            'level': 1,
            'status_effects': [
                'Iron Skin [+8 DT] [3 turns]',
                'Aegis Warding [+20% DR] [3 turns]',
                'Combat Booster [+25% ATK] [3 turns]'
            ]
        }
        attrs = calculate_combat_attributes(char, [])
        self.assertEqual(attrs['base_dt'], 8)
        self.assertAlmostEqual(attrs['gear_dr'].get('physical', 0.0), 0.20)
        base_power = 10 + (10 * 10) + (10 * 2)
        expected_atk = int(round(base_power * 1.0 * 1.25))
        self.assertEqual(attrs['atk'], expected_atk)

    def test_tactical_damage_mitigation_from_potion_buff(self):
        defender_no_buff = {
            'STR': 10, 'AGI': 10, 'INT': 10, 'PER': 10, 'END': 10, 'CHA': 10, 'LUK': 10,
            'level': 1,
            'status_effects': []
        }
        attrs_no_buff = calculate_combat_attributes(defender_no_buff, [])

        defender_with_buff = {
            'STR': 10, 'AGI': 10, 'INT': 10, 'PER': 10, 'END': 10, 'CHA': 10, 'LUK': 10,
            'level': 1,
            'status_effects': [
                'Iron Skin [+14 DT] [3 turns]',
                'Aegis Warding [+35% DR] [3 turns]'
            ]
        }
        attrs_with_buff = calculate_combat_attributes(defender_with_buff, [])

        enemy_atk_attrs = {'atk': 45, 'matk': 20, 'acc': 80}
        enemy_weapon = {
            'attack_types': ['slash'],
            'damage_types': {'physical': 1.0},
            'multiplier': 1.0
        }

        res_no_buff = calculate_tactical_damage(
            attacker_attrs=enemy_atk_attrs,
            defender_attrs=attrs_no_buff,
            weapon_meta=enemy_weapon,
            armor_meta={'armor_type': 'medium', 'base_dt': 0},
            tier='success',
            attacker_level=5,
            defender_max_hp=100,
            is_enemy_attacker=True
        )

        res_with_buff = calculate_tactical_damage(
            attacker_attrs=enemy_atk_attrs,
            defender_attrs=attrs_with_buff,
            weapon_meta=enemy_weapon,
            armor_meta={'armor_type': 'medium', 'base_dt': attrs_with_buff['base_dt']},
            tier='success',
            attacker_level=5,
            defender_max_hp=100,
            is_enemy_attacker=True
        )

        self.assertLess(res_with_buff['damage'], res_no_buff['damage'])


if __name__ == '__main__':
    unittest.main()
