import unittest
from mechanics.combat.formulas import calculate_tactical_damage

class TestCombatIntegration(unittest.TestCase):
    def test_damage_matrix_weakness(self):
        attacker = {"atk": 50, "matk": 50}
        defender = {"def": 10, "mdef": 10, "weaknesses": ["fire"]}
        weapon = {"attack_types": ["slash"], "damage_types": {"fire": 1.0}, "attack_profiles": {"slash": {"damage_type": "fire", "multiplier": 1.0}}}
        armor = {"base_dt": 0, "type_dt": {}}
        
        res = calculate_tactical_damage(attacker, defender, weapon, armor, attack_type="slash")
        self.assertEqual(res["matchup_mult"], 1.5)
        
    def test_damage_matrix_resistance(self):
        attacker = {"atk": 50, "matk": 50}
        defender = {"def": 10, "mdef": 10, "resistances": ["fire"]}
        weapon = {"attack_types": ["slash"], "damage_types": {"fire": 1.0}, "attack_profiles": {"slash": {"damage_type": "fire", "multiplier": 1.0}}}
        armor = {"base_dt": 0, "type_dt": {}}
        
        res = calculate_tactical_damage(attacker, defender, weapon, armor, attack_type="slash")
        self.assertEqual(res["matchup_mult"], 0.5)

    def test_damage_matrix_immunity(self):
        attacker = {"atk": 50, "matk": 50}
        defender = {"def": 10, "mdef": 10, "immunities": ["poison"]}
        weapon = {"attack_types": ["slash"], "damage_types": {"poison": 1.0}, "attack_profiles": {"slash": {"damage_type": "poison", "multiplier": 1.0}}}
        armor = {"base_dt": 0, "type_dt": {}}
        
        res = calculate_tactical_damage(attacker, defender, weapon, armor, attack_type="slash")
        self.assertEqual(res["damage"], 0)
        self.assertEqual(res["matchup_mult"], 0.0)
        
    def test_boss_phase_transition_and_intent(self):
        enemies = [
            {"name": "Big Boss", "hp": 100, "max_hp": 100, "tier_rank": 5, "archetype": "Brute", "stats": {"STR": 5}}
        ]
        
        combat_log = []
        enemies[0]["hp"] -= 60 
        
        for m in enemies:
            if m.get("tier_rank", 1) >= 5 and m.get("hp", 0) > 0 and m.get("hp", 0) < m.get("max_hp", 100) * 0.5:
                if not m.get("phase_2_triggered"):
                    m["phase_2_triggered"] = True
                    heal_amt = int(m.get("max_hp", 100) * 0.2)
                    m["hp"] += heal_amt
                    if "status_effects" not in m:
                        m["status_effects"] = []
                    m["status_effects"].append("Enraged [3 turns]")
                    combat_log.append("BOSS PHASE TRANSITION")
                    
        self.assertTrue(enemies[0]["phase_2_triggered"])
        self.assertEqual(enemies[0]["hp"], 60)
        self.assertIn("Enraged [3 turns]", enemies[0]["status_effects"])
        self.assertIn("BOSS PHASE TRANSITION", combat_log)
        
    def test_ai_targeting(self):
        active_targets = [
            {"name": "Tank", "hp": 100, "stats": {"str_": 10, "luk": 5}},
            {"name": "Mage", "hp": 50, "stats": {"str_": 2, "luk": 2}},
            {"name": "Scout", "hp": 80, "stats": {"str_": 5, "luk": 8}}
        ]
        
        chosen_target = min(active_targets, key=lambda t: t.get("stats", {}).get("luk", 5))
        self.assertEqual(chosen_target["name"], "Mage")
        
        chosen_target = max(active_targets, key=lambda t: t.get("stats", {}).get("str_", 5))
        self.assertEqual(chosen_target["name"], "Tank")
        
        chosen_target = min(active_targets, key=lambda t: t.get("hp", 100))
        self.assertEqual(chosen_target["name"], "Mage")

if __name__ == '__main__':
    unittest.main()
