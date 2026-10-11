import unittest
from mechanics.combat.items.tags import DAMAGE_TYPES
from mechanics.combat.items.armors import ARMOR_ARCHETYPES
from mechanics.combat.items.shields import SHIELD_ARCHETYPES
from mechanics.combat.equipment.tables import RANDOM_AFFIX_POOL, THEME_VOCABULARY
from mechanics.combat.equipment.core import generate_random_equipment, format_equipment_card
from mechanics.combat.spells.kits import get_starter_spells, calculate_spell_damage
from mechanics.combat.spells.registry import get_spell
from mechanics.combat.spells.procedural import (
    generate_procedural_spell, DND_DAMAGE_TYPES, DND_SCHOOLS,
    SUMMON_TEMPLATES, SCENARIO_SPELL_AFFIXES
)
from mechanics.combat.enemies import (
    get_enemy_armor_profile, derive_taxonomy_weaknesses, AFFIX_REGISTRY
)
from mechanics.combat.formulas import (
    TYPE_AFFINITIES, DAMAGE_TYPE_ALIASES, matches_damage_type,
    calculate_tactical_damage
)

class TestElementalFeatureParity(unittest.TestCase):

    def test_damage_types_parity(self):
        """All classical elements (Earth, Water, Wind) are registered in core DAMAGE_TYPES."""
        for elem in ("earth", "water", "wind"):
            self.assertIn(elem, DAMAGE_TYPES)
            self.assertIn(elem, TYPE_AFFINITIES)
            self.assertIn(elem, DAMAGE_TYPE_ALIASES)

    def test_armor_and_shields_dt_parity(self):
        """Every armor archetype and energy shield has explicit type_dt entries for Earth, Water, and Wind."""
        for arch_name, arch_data in ARMOR_ARCHETYPES.items():
            type_dt = arch_data.get("type_dt", {})
            for elem in ("earth", "water", "wind"):
                self.assertIn(elem, type_dt, f"Armor {arch_name} missing {elem} DT")
        
        energy_shield_dt = SHIELD_ARCHETYPES["energy_shield"]["type_dt"]
        for elem in ("earth", "water", "wind"):
            self.assertIn(elem, energy_shield_dt, f"Energy shield missing {elem} DT")
            self.assertEqual(energy_shield_dt[elem], 12)

    def test_equipment_affixes_and_formatting_parity(self):
        """Earth, Water, and Wind have parity in conversion, resistance pools, and tooltip formatting."""
        for elem in ("earth", "water", "wind"):
            convert_key = f"{elem}_convert"
            res_key = f"{elem}_res"
            self.assertIn(convert_key, RANDOM_AFFIX_POOL)
            self.assertIn(res_key, RANDOM_AFFIX_POOL)
            self.assertIn(elem, THEME_VOCABULARY)

        # Check tooltip effect string formatting
        sample_meta = {
            "name": "Primal Stone Cuirass",
            "tier": 2,
            "stat_modifiers": {
                "earth_res": 20,
                "water_res": 15,
                "wind_res": 18,
                "earth_convert": 0.30
            }
        }
        card_str = format_equipment_card(sample_meta)
        self.assertIn("Earth Res +20%", card_str)
        self.assertIn("Water Res +15%", card_str)
        self.assertIn("Wind Res +18%", card_str)
        self.assertIn("Earth Conversion +30%", card_str)

    def test_spell_kits_and_calculation_parity(self):
        """Starter spell kits exist for Geomancer, Hydromancer, and Aeromancer and calculate damage."""
        starter_geomancer = get_starter_spells(scenario="fantasy", char_class="Geomancer", int_stat=7)
        starter_hydromancer = get_starter_spells(scenario="fantasy", char_class="Hydromancer", int_stat=7)
        starter_aeromancer = get_starter_spells(scenario="fantasy", char_class="Aeromancer", int_stat=7)

        self.assertGreater(len(starter_geomancer), 0)
        self.assertGreater(len(starter_hydromancer), 0)
        self.assertGreater(len(starter_aeromancer), 0)

        # Test calculate_spell_damage with Earth spell vs enemy with Earth DT
        earth_spell_id = starter_geomancer[0]
        earth_spell = get_spell(earth_spell_id)
        self.assertIsNotNone(earth_spell)
        self.assertEqual(earth_spell["damage_type"], "earth")

        caster_matk = 25
        defender_attrs = {
            "innate_magic_dr": 0.10,
            "innate_magic_dt": 2,
            "gear_dr": {"earth": 0.15}
        }
        armor_type_dt = {"earth": 8}
        dmg = calculate_spell_damage(
            caster_matk=caster_matk,
            spell=earth_spell,
            affinity_multiplier=1.0,
            defender_attrs=defender_attrs,
            armor_type_dt=armor_type_dt
        )
        self.assertGreater(dmg, 0)

    def test_procedural_spell_generation_parity(self):
        """Procedural generator supports Earth, Water, and Wind across genres."""
        for elem in ("earth", "water", "wind"):
            self.assertIn(elem, DND_DAMAGE_TYPES)
            self.assertIn(elem, DND_SCHOOLS["Evocation"]["default_damage_types"])
            self.assertIn(elem, DND_SCHOOLS["Conjuration"]["default_damage_types"])
            
            # Genre affix parity
            for genre in ("steampunk", "cyberpunk", "dark_fantasy"):
                genre_affixes = SCENARIO_SPELL_AFFIXES[genre]["elem_adjectives"]
                self.assertIn(elem, genre_affixes, f"Genre {genre} missing {elem} adjectives")
                self.assertGreater(len(genre_affixes[elem]), 0)

            # Generate spells
            spell = generate_procedural_spell(tier=2, element=elem, scenario="fantasy")
            self.assertEqual(spell["damage_type"], elem)
            self.assertIn("name", spell)

        # Elemental summons
        self.assertIn("earth_elemental", SUMMON_TEMPLATES)
        self.assertIn("water_elemental", SUMMON_TEMPLATES)
        self.assertIn("wind_elemental", SUMMON_TEMPLATES)
        self.assertEqual(SUMMON_TEMPLATES["earth_elemental"]["damage_type"], "earth")
        self.assertEqual(SUMMON_TEMPLATES["water_elemental"]["damage_type"], "water")
        self.assertEqual(SUMMON_TEMPLATES["wind_elemental"]["damage_type"], "wind")

    def test_enemy_armor_profiles_and_affixes_parity(self):
        """Enemies have defined DT against Earth, Water, and Wind and responsive taxonomy."""
        for arch in ("Guardian", "Brute", "Caster", "Security Drone", "Skirmisher"):
            profile = get_enemy_armor_profile(arch)
            type_dt = profile["type_dt"]
            for elem in ("earth", "water", "wind"):
                self.assertIn(elem, type_dt, f"Enemy {arch} missing {elem} DT")
        
        # Casters have high magic/elemental DT parity
        caster_profile = get_enemy_armor_profile("Caster")
        self.assertEqual(caster_profile["type_dt"]["earth"], 12)
        self.assertEqual(caster_profile["type_dt"]["water"], 12)
        self.assertEqual(caster_profile["type_dt"]["wind"], 12)

        # Taxonomy: constructs are weak to water
        res, weak, imm = derive_taxonomy_weaknesses(["construct"], "corporeal", "arcane")
        self.assertIn("water", weak)
        self.assertIn("wind", res)

        # Taxonomy: plants resist water and earth
        res_plant, weak_plant, _ = derive_taxonomy_weaknesses(["plant"], "corporeal", "primal")
        self.assertIn("water", res_plant)
        self.assertIn("earth", res_plant)

        # Affixes: Grounded, Hydro-Shielded, Tempest-Wreathed
        self.assertIn("Grounded", AFFIX_REGISTRY)
        self.assertIn("earth", AFFIX_REGISTRY["Grounded"]["grants_resistances"])
        self.assertIn("water", AFFIX_REGISTRY["Grounded"]["grants_weaknesses"])

        self.assertIn("Hydro-Shielded", AFFIX_REGISTRY)
        self.assertIn("water", AFFIX_REGISTRY["Hydro-Shielded"]["grants_resistances"])

        self.assertIn("Tempest-Wreathed", AFFIX_REGISTRY)
        self.assertIn("wind", AFFIX_REGISTRY["Tempest-Wreathed"]["grants_resistances"])
        self.assertIn("earth", AFFIX_REGISTRY["Tempest-Wreathed"]["grants_weaknesses"])

    def test_tactical_damage_elemental_conversion(self):
        """Weapons with elemental conversion deal split physical + elemental damage with DT resolution."""
        attacker_attrs = {"atk": 30, "matk": 20, "tags": []}
        defender_attrs = {"def": 15, "mdef": 15, "tags": [], "gear_dr": {"earth": 0.20}}
        armor_meta = {"armor_type": "medium", "base_dt": 4, "type_dt": {"earth": 6, "physical": 8}}
        weapon_meta = {
            "archetype": "sword",
            "attack_types": ["slash"],
            "multiplier": 1.0,
            "stat_modifiers": {"earth_convert": 0.40}
        }
        res = calculate_tactical_damage(
            attacker_attrs=attacker_attrs,
            defender_attrs=defender_attrs,
            weapon_meta=weapon_meta,
            armor_meta=armor_meta,
            tier="success"
        )
        self.assertGreater(res["damage"], 0)
        self.assertTrue(res["hit"])

if __name__ == "__main__":
    unittest.main()
