import unittest
from mechanics.combat.enemies import (
    SCENARIO_ENEMY_TEMPLATES, 
    generate_scenario_enemy, 
    generate_balanced_encounter,
    derive_taxonomy_weaknesses,
    roll_enemy_affixes
)

class TestEnemyExpansion(unittest.TestCase):
    
    def test_taxonomy_weaknesses(self):
        # Construct (e.g. Arcane Golem)
        res, weak, imm = derive_taxonomy_weaknesses(["construct"], "corporeal", "arcane")
        self.assertIn("poison", imm)
        self.assertIn("bleed", imm)
        self.assertIn("shock", weak)
        self.assertIn("acid", weak)
        
        # Incorporeal Undead
        res, weak, imm = derive_taxonomy_weaknesses(["undead"], "incorporeal", "occult")
        self.assertIn("physical", res)
        self.assertIn("holy", weak)
        self.assertIn("poison", imm)
        
    def test_affix_generation_and_conflict_prevention(self):
        # Tier 4 (Miniboss) Construct should roll 2 affixes, but NOT Vampiric (forbidden for construct)
        affixes = roll_enemy_affixes(tier_rank=4, categories=["construct"], form="corporeal", essence="technological", base_weaknesses=["shock", "acid"])
        self.assertEqual(len(affixes), 2)
        self.assertNotIn("Vampiric", affixes)
        
        # Incorporeal creature should be eligible for Phasing, but not Corrosive (mutant/beast only)
        affixes = roll_enemy_affixes(tier_rank=3, categories=["aberration"], form="incorporeal", essence="occult", base_weaknesses=["holy"])
        self.assertIn("Phasing", affixes)
        self.assertNotIn("Corrosive", affixes)
        
    def test_generate_scenario_enemy_template_matching(self):
        enemy = generate_scenario_enemy("fantasy", "area", 1, custom_name="Arcane Golem")
        self.assertEqual(enemy["category"], ["construct"])
        self.assertEqual(enemy["form"], "corporeal")
        self.assertEqual(enemy["essence"], "arcane")
        self.assertIn("poison", enemy["immunities"])
        
    def test_tier_scaling(self):
        minion = generate_scenario_enemy("fantasy", "area", 1, custom_name="Goblin Skirmisher", exact_tier=1)
        elite = generate_scenario_enemy("fantasy", "area", 1, custom_name="Goblin Skirmisher", exact_tier=3)
        boss = generate_scenario_enemy("fantasy", "area", 1, custom_name="Goblin Skirmisher", exact_tier=5)
        
        self.assertEqual(minion["tier"], "minion")
        self.assertEqual(elite["tier"], "elite")
        self.assertEqual(boss["tier"], "boss")
        
        self.assertLess(minion["max_hp"], elite["max_hp"])
        self.assertLess(elite["max_hp"], boss["max_hp"])
        
    def test_balanced_encounter_generation(self):
        party = [{"level": 1, "str_": 2, "per_": 2, "end_": 2, "cha": 1, "int_": 2, "agi": 2, "luk": 1}] * 2
        enemies, xp_mult = generate_balanced_encounter(party, "steampunk", "area", 1)
        
        self.assertGreaterEqual(len(enemies), 1)
        for m in enemies:
            self.assertIn("category", m)
            self.assertIn("form", m)
            self.assertIn("essence", m)
            self.assertIn("tier", m)

if __name__ == '__main__':
    unittest.main()
