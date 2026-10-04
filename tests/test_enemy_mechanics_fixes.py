import unittest
from mechanics.combat.formulas import calculate_tactical_damage, matches_damage_type
from mechanics.combat.spells.kits import calculate_spell_damage
from mechanics.combat.enemies import generate_scenario_enemy, infer_taxonomy_from_archetype
from mechanics.combat.core import precompute_combat_turn


class TestEnemyMechanicsFixes(unittest.TestCase):
    def test_spell_weakness_resistance_immunity(self):
        """Test 1: Spells respect weaknesses, resistances, and immunities."""
        spell_fire = {"name": "Fireball", "damage_type": "fire", "power_mult": 1.0}
        
        # Base damage vs neutral
        neutral_defender = {"mdef": 10, "weaknesses": [], "resistances": [], "immunities": []}
        base_dmg = calculate_spell_damage(30, spell_fire, 1.0, defender_attrs=neutral_defender)
        
        # Fire weakness
        weak_defender = {"mdef": 10, "weaknesses": ["fire"], "resistances": [], "immunities": []}
        weak_dmg = calculate_spell_damage(30, spell_fire, 1.0, defender_attrs=weak_defender)
        self.assertGreater(weak_dmg, base_dmg)
        
        # Fire resistance
        res_defender = {"mdef": 10, "weaknesses": [], "resistances": ["fire"], "immunities": []}
        res_dmg = calculate_spell_damage(30, spell_fire, 1.0, defender_attrs=res_defender)
        self.assertLess(res_dmg, base_dmg)
        
        # Fire immunity
        imm_defender = {"mdef": 10, "weaknesses": [], "resistances": [], "immunities": ["fire"]}
        imm_dmg = calculate_spell_damage(30, spell_fire, 1.0, defender_attrs=imm_defender)
        self.assertEqual(imm_dmg, 0)

    def test_damage_type_alias_normalization(self):
        """Test 2: Aliases match correctly (slash == slashing, cold == ice, lightning == shock)."""
        # Alias matching helper
        self.assertTrue(matches_damage_type(["slashing"], "slash"))
        self.assertTrue(matches_damage_type(["slash"], "slashing"))
        self.assertTrue(matches_damage_type(["cold"], "ice"))
        self.assertTrue(matches_damage_type(["ice"], "cold"))
        self.assertTrue(matches_damage_type(["lightning"], "shock"))
        self.assertTrue(matches_damage_type(["shock"], "lightning"))
        self.assertTrue(matches_damage_type(["piercing"], "thrust"))

        # Physical attack with slash vs slashing weakness
        attacker = {"atk": 50, "matk": 20}
        defender = {"def": 10, "mdef": 10, "weaknesses": ["slashing"]}
        weapon = {"attack_types": ["slash"], "damage_types": {"physical": 1.0}, "attack_profiles": {"slash": {"damage_type": "physical", "multiplier": 1.0}}}
        armor = {"base_dt": 0, "type_dt": {}}

        res = calculate_tactical_damage(attacker, defender, weapon, armor, attack_type="slash")
        self.assertEqual(res["matchup_mult"], 1.5)

    def test_turn_1_intent_seeding(self):
        """Test 3: Intent is generated on spawn for Tier 3+ enemies."""
        # Tier 1 (Minion) -> None
        e_minion = generate_scenario_enemy("fantasy", "dungeon", 1, exact_tier=1)
        self.assertIsNone(e_minion.get("intent"))

        # Tier 2 (Standard) -> None
        e_standard = generate_scenario_enemy("fantasy", "dungeon", 1, exact_tier=2)
        self.assertIsNone(e_standard.get("intent"))

        # Tier 3 (Elite) -> active string
        e_elite = generate_scenario_enemy("fantasy", "dungeon", 1, exact_tier=3)
        self.assertIsNotNone(e_elite.get("intent"))
        self.assertIsInstance(e_elite["intent"], str)
        self.assertGreater(len(e_elite["intent"]), 0)

        # Tier 5 (Boss) -> active string
        e_boss = generate_scenario_enemy("fantasy", "dungeon", 1, exact_tier=5)
        self.assertIsNotNone(e_boss.get("intent"))
        self.assertIsInstance(e_boss["intent"], str)

    def test_dynamic_archetype_taxonomy_fallback(self):
        """Test 4: Custom enemies without exact templates get intelligent fallbacks."""
        # Custom robot mech
        e_mech = generate_scenario_enemy("scifi", "hangar", 1, custom_name="Unit ZX-99", custom_archetype="Heavy Mech")
        self.assertIn("construct", e_mech["category"])
        self.assertIn("robot", e_mech["category"])
        self.assertEqual(e_mech["essence"], "technological")

        # Custom mutant abomination
        e_mutant = generate_scenario_enemy("wasteland", "crater", 1, custom_name="Glowfiend", custom_archetype="Rad-Mutant")
        self.assertIn("mutant", e_mutant["category"])
        self.assertEqual(e_mutant["essence"], "irradiated")

    def test_boss_phase_2_lethal_intercept(self):
        """Test 5: Tier 5 Boss survives lethal blow that skips 50% HP threshold."""
        session = {
            "id": "boss_test_session",
            "scenario": "fantasy",
            "nearby_enemies": [
                {
                    "name": "Overlord Malakor",
                    "tier_rank": 5,
                    "archetype": "Brute",
                    "hp": 60,
                    "max_hp": 100,
                    "phase_2_triggered": False,
                    "stats": {"STR": 8, "END": 8, "AGI": 4, "INT": 2, "PER": 4, "CHA": 2, "LUK": 3}
                }
            ],
            "history": []
        }
        player_char = {
            "user_id": 9999,
            "name": "Champion",
            "level": 10,
            "hp": 100,
            "max_hp": 100,
            "stats": {"STR": 10, "AGI": 8, "END": 8, "INT": 5, "PER": 5, "CHA": 5, "LUK": 5}
        }
        # Player executes massive hit that would deal 80+ damage (overkilling from 60 to 0)
        action = {
            "user_id": 9999,
            "choice_type": "MELEE_ATTACK",
            "label": "Mega Strike",
            "tier": "crit_success",
            "target_entity": "Overlord Malakor"
        }

        turn_res = precompute_combat_turn(session, [player_char], [action])

        # Boss must NOT be dead!
        boss = session["nearby_enemies"][0]
        self.assertTrue(boss.get("phase_2_triggered"))
        self.assertGreater(boss["hp"], 0)
        # Should have received Enraged status
        status_effects = boss.get("status_effects", [])
        self.assertTrue(any("Enraged" in s for s in status_effects), f"Expected Enraged in {status_effects}")


if __name__ == "__main__":
    unittest.main()
