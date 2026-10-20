import unittest
import db
from skill_check import CheckResult
from mechanics.combat import precompute_combat_turn


class TestCombatTacticalDepth(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.user_id = 998877665
        chars = db.get_user_characters(self.user_id)
        for c in chars:
            db.delete_character(self.user_id, c["id"])

        base_stats = {"STR": 16, "AGI": 14, "END": 14, "CHA": 12, "INT": 10, "PER": 12, "LUK": 10}
        self.char = db.create_character(
            user_id=self.user_id,
            name="Gideon",
            char_class="Warrior",
            class_description="Combat Tester",
            stats=base_stats
        )
        self.party = [self.char]

    def tearDown(self):
        chars = db.get_user_characters(self.user_id)
        for c in chars:
            db.delete_character(self.user_id, c["id"])

    def test_combat_parley_standard_enemy_low_hp_surrender(self):
        """Standard enemies at or below 50% HP yield/surrender on parley success and grant rewards."""
        session = {
            "id": 101,
            "scenario": "fantasy",
            "nearby_enemies": [
                {"name": "Goblin Raider", "hp": 30, "max_hp": 80, "tier_rank": 2, "atk": 15, "def": 5}
            ],
            "current_npcs": []
        }
        action = {
            "char": self.char,
            "label": "Demand that the goblin drop its blade and surrender",
            "combat_tactical_archetype": "combat_parley",
            "target": "Goblin Raider",
            "check": CheckResult(chance=80, roll=20, tier="success", tier_label="Success", succeeded=True, requirement=8)
        }
        res = precompute_combat_turn(session, self.party, [action])
        self.assertIn("Goblin Raider", res["surrendered_enemies"])
        self.assertIn("Goblin Raider", res["fled_enemies"])
        self.assertTrue(res["xp_gain"] > 0, "Surrendered enemies must award XP")
        self.assertTrue(res["gold_gain"] > 0, "Surrendered enemies must award Gold")

    def test_combat_parley_boss_inflicts_demoralized_without_defeat(self):
        """Bosses or high-HP enemies resist instant surrender but receive Demoralized and Staggered."""
        boss = {"name": "Dragon Warlord", "hp": 400, "max_hp": 500, "tier_rank": 5, "atk": 45, "def": 25}
        session = {
            "id": 102,
            "scenario": "fantasy",
            "nearby_enemies": [boss],
            "current_npcs": []
        }
        action = {
            "char": self.char,
            "label": "Call out the Dragon Warlord's dishonorable tactics to shake his resolve",
            "combat_tactical_archetype": "combat_parley",
            "target": "Dragon Warlord",
            "check": CheckResult(chance=75, roll=30, tier="success", tier_label="Success", succeeded=True, requirement=10)
        }
        res = precompute_combat_turn(session, self.party, [action])
        self.assertNotIn("Dragon Warlord", res["surrendered_enemies"])
        self.assertTrue(len(session["nearby_enemies"]) > 0)
        surviving_boss = session["nearby_enemies"][0]
        self.assertTrue(surviving_boss["hp"] > 0)
        effects = surviving_boss.get("status_effects", [])
        self.assertTrue(any("Hesitating / Demoralized" in eff for eff in effects))
        self.assertTrue(any("Staggered" in eff for eff in effects))

    def test_called_shot_piercing_and_targeted_ailments(self):
        """Called shots pierce 40% DT and inflict part-specific debuffs based on label keywords."""
        # 1. Aim for eyes/head -> Blinded
        enemy1 = {"name": "Orc Berserker", "hp": 500, "max_hp": 500, "tier_rank": 3, "atk": 30, "def": 15, "base_dt": 8}
        session = {"id": 103, "scenario": "fantasy", "nearby_enemies": [enemy1], "current_npcs": []}
        action1 = {
            "char": self.char,
            "label": "Shoot an arrow right into the berserker's eye slit",
            "combat_tactical_archetype": "called_shot",
            "target": "Orc Berserker",
            "check": CheckResult(chance=80, roll=15, tier="success", tier_label="Success", succeeded=True, requirement=9)
        }
        precompute_combat_turn(session, self.party, [action1])
        effects1 = session["nearby_enemies"][0].get("status_effects", [])
        self.assertTrue(any("Blinded" in eff for eff in effects1))

        # 2. Aim for hand/weapon -> Disarmed
        enemy2 = {"name": "Orc Captain", "hp": 500, "max_hp": 500, "tier_rank": 3, "atk": 30, "def": 15, "base_dt": 8}
        session2 = {"id": 104, "scenario": "fantasy", "nearby_enemies": [enemy2], "current_npcs": []}
        action2 = {
            "char": self.char,
            "label": "Slash across the captain's weapon wrist to force a disarm",
            "combat_tactical_archetype": "called_shot",
            "target": "Orc Captain",
            "check": CheckResult(chance=80, roll=15, tier="success", tier_label="Success", succeeded=True, requirement=9)
        }
        precompute_combat_turn(session2, self.party, [action2])
        effects2 = session2["nearby_enemies"][0].get("status_effects", [])
        self.assertTrue(any("Disarmed" in eff for eff in effects2))

        # 3. Aim for leg/kneecap -> Crippled + Staggered
        enemy3 = {"name": "Orc Brute", "hp": 500, "max_hp": 500, "tier_rank": 3, "atk": 30, "def": 15, "base_dt": 8}
        session3 = {"id": 105, "scenario": "fantasy", "nearby_enemies": [enemy3], "current_npcs": []}
        action3 = {
            "char": self.char,
            "label": "Kick hard into his kneecap to cripple his movement",
            "combat_tactical_archetype": "called_shot",
            "target": "Orc Brute",
            "check": CheckResult(chance=80, roll=15, tier="success", tier_label="Success", succeeded=True, requirement=9)
        }
        precompute_combat_turn(session3, self.party, [action3])
        effects3 = session3["nearby_enemies"][0].get("status_effects", [])
        self.assertTrue(any("Crippled" in eff for eff in effects3))
        self.assertTrue(any("Staggered" in eff for eff in effects3))

    def test_reposition_clears_grapple_and_primes_flanking(self):
        """Reposition clears restraints, raises dodge chance, and primes Flanking Advantage."""
        enemy = {"name": "Cave Troll", "hp": 500, "max_hp": 500, "tier_rank": 3, "atk": 35, "def": 10}
        session = {
            "id": 106,
            "scenario": "fantasy",
            "nearby_enemies": [enemy],
            "current_npcs": [],
            "physical_state": {
                "actors": {
                    "Gideon": {"tether": "grappled_by_troll"}
                }
            }
        }
        action = {
            "char": self.char,
            "label": "Slip out of the troll's grip and roll behind the pillar",
            "combat_tactical_archetype": "reposition",
            "target": "Cave Troll",
            "check": CheckResult(chance=85, roll=10, tier="success", tier_label="Success", succeeded=True, requirement=8)
        }
        res = precompute_combat_turn(session, self.party, [action])
        # Verify tether cleared
        self.assertEqual(session["physical_state"]["actors"]["Gideon"]["tether"], "none")
        char_effects = self.char.get("status_effects", [])
        self.assertTrue(any("Evasive Maneuver" in eff for eff in char_effects))
        self.assertTrue(any("Flanking Advantage" in eff for eff in char_effects))

    def test_tactical_debuff_inflicts_vulnerable_and_staggered(self):
        """Tactical debuffs inflict Vulnerable and Staggered."""
        enemy = {"name": "Shadow Stalker", "hp": 500, "max_hp": 500, "tier_rank": 3, "atk": 28, "def": 8}
        session = {"id": 107, "scenario": "fantasy", "nearby_enemies": [enemy], "current_npcs": []}
        action = {
            "char": self.char,
            "label": "Throw sand into the stalker's eyes and feint left",
            "combat_tactical_archetype": "tactical_debuff",
            "target": "Shadow Stalker",
            "check": CheckResult(chance=80, roll=12, tier="success", tier_label="Success", succeeded=True, requirement=8)
        }
        precompute_combat_turn(session, self.party, [action])
        effects = session["nearby_enemies"][0].get("status_effects", [])
        self.assertTrue(any("Vulnerable" in eff for eff in effects))
        self.assertTrue(any("Staggered" in eff for eff in effects))

    def test_environmental_hazard_applies_damage_and_stagger(self):
        """Environmental hazards deal heavy damage and Stagger the target enemy."""
        enemy = {"name": "Bandit Leader", "hp": 500, "max_hp": 500, "tier_rank": 3, "atk": 25, "def": 8}
        session = {"id": 108, "scenario": "fantasy", "nearby_enemies": [enemy], "current_npcs": []}
        action = {
            "char": self.char,
            "label": "Cut the rope holding the chandelier above the bandit leader",
            "combat_tactical_archetype": "environmental_hazard",
            "target": "Bandit Leader",
            "check": CheckResult(chance=85, roll=10, tier="success", tier_label="Success", succeeded=True, requirement=7)
        }
        res = precompute_combat_turn(session, self.party, [action])
        surviving_bandit = session["nearby_enemies"][0]
        self.assertTrue(surviving_bandit["hp"] < 500)
        effects = surviving_bandit.get("status_effects", [])
        self.assertTrue(any("Staggered" in eff for eff in effects))
