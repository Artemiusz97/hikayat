import unittest
import sqlite3
from unittest.mock import MagicMock

from mechanics.social.attributes import calculate_combat_attributes
from mechanics.combat import calculate_tactical_damage, try_inflict_status
from mechanics.combat.items.armors import generate_random_equipment as gen_armor, ARMOR_ARCHETYPES
from mechanics.combat.items.shields import generate_random_equipment as gen_shield, SHIELD_ARCHETYPES
from mechanics.combat.items.weapons import generate_random_equipment as gen_weapon, WEAPON_ARCHETYPES, ARMOR_PIERCING_AFFIXES
from mechanics.combat.items.headwear import generate_random_equipment as gen_headwear, HEADWEAR_ARCHETYPES
from mechanics.combat.items.shoes import generate_random_equipment as gen_shoes, SHOE_ARCHETYPES
from mechanics.combat.equipment import parse_equipment_metadata, is_two_handed
import db


class TestArmorApTagsBalance(unittest.TestCase):
    def setUp(self):
        self.char = {
            'id': 9999,
            'user_id': 9999,
            'name': 'BalanceTester',
            'level': 5,
            'hp': 100,
            'max_hp': 100,
            'mp': 50,
            'max_mp': 50,
            'str_': 10,
            'agi': 5,
            'int_': 5,
            'per_': 5,
            'end_': 10,
            'cha': 5,
            'luk': 5,
            'status_effects': []
        }

    def test_heavy_armor_evasion_penalties(self):
        base_attrs = calculate_combat_attributes(self.char, [])
        base_eva = base_attrs['eva']

        plate_armor = gen_armor('fantasy', 'Armor', tier=3, archetype='plate')
        plate_meta = parse_equipment_metadata(plate_armor)
        self.assertEqual(plate_meta.get('base_eva'), -6)
        self.assertEqual(plate_meta.get('stat_modifiers', {}).get('eva'), -6)

        plate_attrs = calculate_combat_attributes(self.char, [plate_armor])
        self.assertEqual(plate_attrs['eva'], base_eva - 6)

        tower_shield = gen_shield('fantasy', tier=3, archetype='tower_shield')
        tower_meta = parse_equipment_metadata(tower_shield)
        self.assertEqual(tower_meta.get('base_eva'), -6)
        self.assertEqual(tower_meta.get('stat_modifiers', {}).get('eva'), -6)

        tank_attrs = calculate_combat_attributes(self.char, [plate_armor, tower_shield])
        self.assertEqual(tank_attrs['eva'], base_eva - 12)

        helm = gen_headwear('fantasy', tier=3, archetype='full_greathelm')
        greaves = gen_shoes('fantasy', tier=3, archetype='heavy_greaves')
        full_tank_attrs = calculate_combat_attributes(self.char, [plate_armor, tower_shield, helm, greaves])
        self.assertEqual(full_tank_attrs['eva'], base_eva - 17)

    def test_light_armor_evasion_bonuses(self):
        base_attrs = calculate_combat_attributes(self.char, [])
        base_eva = base_attrs['eva']

        clothes = gen_armor('fantasy', 'Armor', tier=3, archetype='clothes')
        sneakers = gen_shoes('fantasy', tier=3, archetype='light_sneakers')
        light_attrs = calculate_combat_attributes(self.char, [clothes, sneakers])
        self.assertGreater(light_attrs['eva'], base_eva)

    def test_2h_weapon_slot_filtering_in_dropdown(self):
        from cogs.inventory import EquipSlotSelectDropdown
        two_h_weapon = gen_weapon('fantasy', tier=3)
        two_h_weapon['metadata']['handedness'] = '2H'
        two_h_weapon['metadata']['archetype'] = 'greatsword'
        from mechanics.combat.items.envelope import serialize_item
        two_h_weapon['effect'] = serialize_item(two_h_weapon['metadata'])

        self.assertTrue(is_two_handed(two_h_weapon))

        dropdown = EquipSlotSelectDropdown(self.char['user_id'], two_h_weapon)
        slot_values = [opt.value for opt in dropdown.options]
        self.assertNotIn('Shield', slot_values)
        self.assertIn('Weapon', slot_values)

    def test_1h_weapon_can_equip_in_shield_or_weapon(self):
        from cogs.inventory import EquipSlotSelectDropdown
        dagger = gen_weapon('fantasy', tier=3)
        dagger['metadata']['handedness'] = '1H'
        dagger['metadata']['archetype'] = 'dagger'
        from mechanics.combat.items.envelope import serialize_item
        dagger['effect'] = serialize_item(dagger['metadata'])

        self.assertFalse(is_two_handed(dagger))

        dropdown = EquipSlotSelectDropdown(self.char['user_id'], dagger)
        slot_values = [opt.value for opt in dropdown.options]
        self.assertIn('Shield', slot_values)
        self.assertIn('Weapon', slot_values)

    def test_armor_piercing_affixes_penetration(self):
        defender_attrs = {
            'atk': 20, 'def': 40, 'matk': 10, 'mdef': 20,
            'base_dt': 20, 'type_dt': {'physical': 20}
        }
        armor_meta = {'base_dt': 20, 'type_dt': {'physical': 20}, 'armor_type': 'heavy'}
        attacker_attrs = {'atk': 50, 'matk': 20, 'acc': 80, 'eva': 10}

        standard_weapon = {'multiplier': 1.0, 'attack_types': ['slash'], 'damage_types': {'physical': 1.0}}
        res_standard = calculate_tactical_damage(
            attacker_attrs, defender_attrs, standard_weapon, armor_meta, tier='success'
        )

        ap_weapon = {'multiplier': 1.0, 'attack_types': ['slash'], 'damage_types': {'physical': 1.0}, 'armor_penetration': 0.50}
        res_ap = calculate_tactical_damage(
            attacker_attrs, defender_attrs, ap_weapon, armor_meta, tier='success'
        )
        self.assertGreater(res_ap['damage'], res_standard['damage'])
        self.assertEqual(res_ap['ap_ratio'], 0.50)

    def test_armor_piercing_75_percent_strict_ceiling(self):
        defender_attrs = {
            'atk': 20, 'def': 40, 'matk': 10, 'mdef': 20,
            'base_dt': 20, 'type_dt': {'physical': 20}
        }
        armor_meta = {'base_dt': 20, 'type_dt': {'physical': 20}, 'armor_type': 'heavy'}
        attacker_attrs = {'atk': 50, 'matk': 20, 'acc': 80, 'eva': 10}

        overpowered_weapon = {
            'multiplier': 1.0, 'attack_types': ['slash'], 'damage_types': {'physical': 1.0},
            'armor_penetration': 1.00
        }
        res = calculate_tactical_damage(
            attacker_attrs, defender_attrs, overpowered_weapon, armor_meta, tier='success'
        )
        self.assertEqual(res['ap_ratio'], 0.75)

    def test_temporary_status_degradation(self):
        plate_armor = gen_armor('fantasy', 'Armor', tier=3, archetype='plate')
        base_attrs = calculate_combat_attributes(self.char, [plate_armor])
        baseline_dt = base_attrs['base_dt']
        self.assertGreater(baseline_dt, 15)

        self.char['status_effects'] = ['Armor Cracked [-10 DT] [3 turns]']
        cracked_attrs = calculate_combat_attributes(self.char, [plate_armor])
        self.assertEqual(cracked_attrs['base_dt'], baseline_dt - 10)

        self.char['status_effects'] = ['Acid Corroded [-50% DT] [2 turns]']
        corroded_attrs = calculate_combat_attributes(self.char, [plate_armor])
        expected_dt = int(round(baseline_dt * 0.50))
        self.assertEqual(corroded_attrs['base_dt'], expected_dt)

        self.char['status_effects'] = []
        restored_attrs = calculate_combat_attributes(self.char, [plate_armor])
        self.assertEqual(restored_attrs['base_dt'], baseline_dt)

    def test_hazmat_gear_repels_toxic_hazards(self):
        normal_defender = {'name': 'Civilian', 'status_effects': []}
        normal_attrs = {'tags': []}
        log = []
        applied = try_inflict_status(normal_defender, normal_attrs, 'Poisoned [2 turns]', log)
        self.assertTrue(applied)
        self.assertIn('Poisoned [2 turns]', normal_defender['status_effects'])

        hazmat_defender = {'name': 'Hazmat Trooper', 'status_effects': []}
        hazmat_attrs = {'tags': ['hazmat', 'environmental_isolation']}
        log_hazmat = []
        applied_hazmat = try_inflict_status(hazmat_defender, hazmat_attrs, 'Toxic Cloud [3 turns]', log_hazmat)
        self.assertFalse(applied_hazmat)
        self.assertEqual(len(hazmat_defender['status_effects']), 0)
        self.assertTrue(any('repelled the toxic hazard' in msg for msg in log_hazmat))

        applied_acid = try_inflict_status(hazmat_defender, hazmat_attrs, 'Acid Corroded [-50% DT] [2 turns]', log_hazmat)
        self.assertFalse(applied_acid)
        self.assertEqual(len(hazmat_defender['status_effects']), 0)

    def test_brawler_synergy_boosts_unarmed(self):
        unarmed_weapon = {
            'archetype': 'unarmed', 'multiplier': 1.0, 'attack_types': ['bludgeoning'],
            'damage_types': {'physical': 1.0}
        }
        armor_meta = {'base_dt': 0, 'type_dt': {}, 'armor_type': 'light'}
        defender_attrs = {'atk': 10, 'def': 10, 'matk': 10, 'mdef': 10}

        non_brawler_attrs = {'atk': 40, 'matk': 10, 'tags': []}
        res_non_brawler = calculate_tactical_damage(
            non_brawler_attrs, defender_attrs, unarmed_weapon, armor_meta, tier='success'
        )
        self.assertFalse(res_non_brawler['brawler_synergy'])

        brawler_attrs = {'atk': 40, 'matk': 10, 'tags': ['brawler']}
        res_brawler = calculate_tactical_damage(
            brawler_attrs, defender_attrs, unarmed_weapon, armor_meta, tier='success'
        )
        self.assertTrue(res_brawler['brawler_synergy'])
        self.assertGreater(res_brawler['damage'], res_non_brawler['damage'])

    def test_stealth_ambush_strike_turn_one(self):
        weapon = {'multiplier': 1.0, 'attack_types': ['slash'], 'damage_types': {'physical': 1.0}}
        armor_meta = {'base_dt': 0, 'type_dt': {}, 'armor_type': 'light'}
        defender_attrs = {'atk': 10, 'def': 10, 'matk': 10, 'mdef': 10}

        stealth_turn1_attrs = {'atk': 40, 'matk': 10, 'tags': ['stealth'], 'combat_turn': 1}
        res_ambush = calculate_tactical_damage(
            stealth_turn1_attrs, defender_attrs, weapon, armor_meta, tier='success'
        )
        self.assertTrue(res_ambush['ambush_strike'])

        stealth_turn2_attrs = {'atk': 40, 'matk': 10, 'tags': ['stealth'], 'combat_turn': 2}
        res_turn2 = calculate_tactical_damage(
            stealth_turn2_attrs, defender_attrs, weapon, armor_meta, tier='success'
        )
        self.assertFalse(res_turn2['ambush_strike'])
        self.assertGreater(res_ambush['damage'], res_turn2['damage'])

    def test_tank_stagger_synergy(self):
        weapon = {'multiplier': 1.0, 'attack_types': ['slash'], 'damage_types': {'physical': 1.0}}
        armor_meta = {'base_dt': 50, 'type_dt': {}, 'armor_type': 'heavy'}
        attacker_attrs = {'atk': 20, 'matk': 10}
        tank_defender_attrs = {'atk': 10, 'def': 30, 'matk': 10, 'mdef': 10, 'tags': ['tank']}

        stagger_seen = False
        for _ in range(30):
            res = calculate_tactical_damage(
                attacker_attrs, tank_defender_attrs, weapon, armor_meta, tier='success'
            )
            if res.get('stagger_inflicted'):
                stagger_seen = True
                break
        self.assertTrue(stagger_seen)

if __name__ == '__main__':
    unittest.main()
