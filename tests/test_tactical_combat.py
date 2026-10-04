import unittest
import db
import character_data as cd
from mechanics.social.attributes import calculate_combat_attributes
from mechanics.combat.equipment import generate_random_equipment, build_equipment_effect_str
from mechanics.combat.enemies import get_enemy_armor_profile, get_enemy_weapon_profile
from mechanics.combat import (
    calculate_tactical_damage,
    get_attack_type_multiplier,
    get_elemental_multiplier,
    precompute_combat_turn
)

class TestTacticalCombat(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.user_id = 887766554
        chars = db.get_user_characters(self.user_id)
        for c in chars:
            db.delete_character(self.user_id, c["id"])

    def tearDown(self):
        chars = db.get_user_characters(self.user_id)
        for c in chars:
            db.delete_character(self.user_id, c["id"])

    def test_affinity_multipliers(self):
        plate_armor = {"armor_type": "plate"}
        chain_armor = {"armor_type": "chainmail"}
        robe_armor = {"armor_type": "magic_robe"}

        # 1. Blunt vs Plate gets 1.20x bonus
        blunt_mult = get_attack_type_multiplier(["blunt"], plate_armor)
        self.assertAlmostEqual(blunt_mult, 1.20, places=2)

        # 2. Slash vs Plate gets 0.70x reduction
        slash_plate_mult = get_attack_type_multiplier(["slash"], plate_armor)
        self.assertAlmostEqual(slash_plate_mult, 0.70, places=2)

        # 3. Thrust vs Chainmail gets 1.30x piercing bonus
        thrust_chain_mult = get_attack_type_multiplier(["thrust"], chain_armor)
        self.assertAlmostEqual(thrust_chain_mult, 1.30, places=2)

        # 4. Lightning vs Plate gets 1.40x conduction bonus
        lightning_mult = get_elemental_multiplier({"lightning": 1.0}, plate_armor)
        self.assertAlmostEqual(lightning_mult, 1.40, places=2)

        # 5. Magic/Fire vs Magic Robes gets 0.60x warding resistance
        fire_robe_mult = get_elemental_multiplier({"fire": 1.0}, robe_armor)
        self.assertAlmostEqual(fire_robe_mult, 0.60, places=2)

    def test_calculate_tactical_damage_blunt_vs_slash(self):
        attacker_attrs = {"atk": 70, "matk": 22}
        defender_attrs = {"def": 40, "mdef": 20, "block_chance": 0}

        hammer_weapon = {"attack_types": ["blunt"], "damage_types": {"physical": 1.0}}
        sword_weapon = {"attack_types": ["slash"], "damage_types": {"physical": 1.0}}
        plate_armor = {"armor_type": "plate"}

        dmg_hammer = calculate_tactical_damage(
            attacker_attrs=attacker_attrs,
            defender_attrs=defender_attrs,
            weapon_meta=hammer_weapon,
            armor_meta=plate_armor,
            tier="success"
        )

        dmg_sword = calculate_tactical_damage(
            attacker_attrs=attacker_attrs,
            defender_attrs=defender_attrs,
            weapon_meta=sword_weapon,
            armor_meta=plate_armor,
            tier="success"
        )

        # Hammer crushing plate must deal significantly more damage than sword slashing plate
        self.assertGreater(dmg_hammer["damage"], dmg_sword["damage"])
        self.assertAlmostEqual(dmg_hammer["matchup_mult"], 1.20, places=2)
        self.assertAlmostEqual(dmg_sword["matchup_mult"], 0.70, places=2)

    def test_shield_blocking_absorption(self):
        attacker_attrs = {"atk": 80, "matk": 22}
        defender_attrs = {"def": 30, "mdef": 20, "block_chance": 100} # 100% block for test
        weapon = {"attack_types": ["slash"], "damage_types": {"physical": 1.0}}
        armor = {"armor_type": "leather"}

        res = calculate_tactical_damage(
            attacker_attrs=attacker_attrs,
            defender_attrs=defender_attrs,
            weapon_meta=weapon,
            armor_meta=armor,
            tier="success"
        )
        self.assertTrue(res["blocked"])
        self.assertGreater(res["damage"], 0)

    def test_enemy_profiles(self):
        guardian_armor = get_enemy_armor_profile("Guardian")
        self.assertEqual(guardian_armor["armor_type"], "heavy")
        self.assertGreater(guardian_armor["block_chance"], 0)

        caster_armor = get_enemy_armor_profile("Caster")
        self.assertEqual(caster_armor["armor_type"], "magic_robe")
        self.assertGreater(caster_armor["mdef_bonus"], 15)

    def test_full_precompute_combat_turn(self):
        base_stats = {"STR": 6, "PER": 2, "END": 5, "CHA": 1, "INT": 1, "AGI": 3, "LUK": 2}
        char = db.create_character(
            user_id=self.user_id,
            name="TacticalHero",
            char_class="Warrior",
            class_description="Combat Tester",
            stats=base_stats
        )

        # Equip gear for user
        sword = generate_random_equipment("fantasy", "Weapon", tier=2)
        sword["name"] = "Fine Steel Sword"
        sword["metadata"]["name"] = "Fine Steel Sword"
        sword["metadata"]["archetype"] = "sword"
        sword["metadata"]["attack_types"] = ["slash"]
        sword["metadata"]["damage_types"] = {"physical": 1.0}
        sword["metadata"]["handedness"] = "1H"
        sword["effect"] = build_equipment_effect_str(sword["metadata"])

        shield = generate_random_equipment("fantasy", "Shield", tier=2)
        shield["name"] = "Tower Shield"
        shield["metadata"]["name"] = "Tower Shield"
        shield["metadata"]["archetype"] = "tower_shield"
        shield["metadata"]["block_chance"] = 40
        shield["effect"] = build_equipment_effect_str(shield["metadata"])

        id_sw = db.add_item(self.user_id, sword["name"], "Weapon", sword["effect"], force=True)
        id_sh = db.add_item(self.user_id, shield["name"], "Shield", shield["effect"], force=True)
        db.equip_item(self.user_id, id_sw, "Weapon")
        db.equip_item(self.user_id, id_sh, "Shield")

        session = {
            "id": 9999,
            "scenario": "fantasy",
            "nearby_enemies": [
                {"name": "Orc Marauder", "archetype": "Brute", "level": 2, "hp": 80, "max_hp": 80}
            ],
            "current_npcs": []
        }

        # Mock action
        actions = [{"stat": "STR", "tier": "success", "label": "Slash with blade"}]
        char_dict = dict(char)
        char_dict["user_id"] = self.user_id
        party = [(char_dict, None)]

        precompute = precompute_combat_turn(session, party, actions)
        self.assertIn("combat_log", precompute)
        self.assertIn("dead_enemies", precompute)
        self.assertGreater(len(precompute["combat_log"]), 0)

    def test_enemy_damage_scaling_and_safety_cap(self):
        """Verify that enemy attacks against an 80 HP player deal balanced ~15-22 damage and never 1-shot the player."""
        enemy_atk_attrs = {"atk": 150, "matk": 20, "acc": 80}
        player_attrs = {"def": 25, "mdef": 20, "eva": 15, "block_chance": 0}
        enemy_weapon = {"attack_types": ["blunt"], "damage_types": {"physical": 1.0}}
        player_armor = {"armor_type": "magic_robe"}

        # 1. Normal hit
        res_normal = calculate_tactical_damage(
            attacker_attrs=enemy_atk_attrs,
            defender_attrs=player_attrs,
            weapon_meta=enemy_weapon,
            armor_meta=player_armor,
            tier="success",
            attacker_level=16,
            defender_max_hp=80,
            is_enemy_attacker=True
        )
        self.assertGreaterEqual(res_normal["damage"], 10)
        self.assertLessEqual(res_normal["damage"], 22, "Normal enemy hit must not exceed 22% of player max HP (18-20 dmg)")

        # 2. Critical hit
        res_crit = calculate_tactical_damage(
            attacker_attrs=enemy_atk_attrs,
            defender_attrs=player_attrs,
            weapon_meta=enemy_weapon,
            armor_meta=player_armor,
            tier="crit_success",
            attacker_level=16,
            defender_max_hp=80,
            is_enemy_attacker=True
        )
        self.assertGreaterEqual(res_crit["damage"], 18)
        self.assertLessEqual(res_crit["damage"], 28, "Critical enemy hit must never exceed 30% of player max HP (24-28 dmg)")

    def test_failed_int_check_deals_zero_damage_and_does_not_defeat_enemy(self):
        """Verify that a failed INT check (e.g. 85% chance missed) deals 0 damage, does not kill the enemy, and preserves living enemy directive."""
        sentinel = {
            "name": "Steam Sentinel Alpha",
            "hp": 100,
            "max_hp": 100,
            "level": 3,
            "archetype": "Brute",
            "stats": {"STR": 7, "AGI": 4, "END": 6, "INT": 3, "PER": 5, "CHA": 2, "LUK": 3}
        }
        session = {
            "scenario": "steampunk",
            "combat_turn": 1,
            "nearby_enemies": [sentinel],
            "current_npcs": []
        }
        player_char = {
            "name": "Hero",
            "hp": 100,
            "max_hp": 100,
            "level": 3,
            "str_": 5,
            "agi_": 5,
            "int_": 8,
            "per_": 5,
            "end_": 5,
            "cha_": 5,
            "luk": 5,
            "user_id": self.user_id
        }
        party = [(player_char, None)]
        from skill_check import CheckResult
        failed_check = CheckResult(chance=85, roll=92.0, tier="fail", tier_label="Missed", succeeded=False, requirement=5)
        actions = [{
            "char": player_char,
            "label": "Overload Steam Manifold",
            "stat": "INT",
            "tier": "fail",
            "check": failed_check,
            "mp_spent": 0
        }]

        precomputed = precompute_combat_turn(session, party, actions)

        # 1. Sentinel must NOT be defeated
        self.assertNotIn("Steam Sentinel Alpha", precomputed.get("dead_enemies", []))
        # 2. Sentinel HP must not have taken damage from player
        self.assertGreaterEqual(sentinel["hp"], 80)
        # 3. Combat log must record that the action missed / failed
        log_text = " ".join(precomputed.get("combat_log", []))
        self.assertTrue("missed" in log_text.lower() or "failed" in log_text.lower())
        # 4. Directive must state living enemy is still alive and fighting
        self.assertIn("STILL ALIVE and fighting", precomputed["directive"])
        self.assertNotIn("Victory: All hostiles are DEFEATED", precomputed["directive"])

    def test_failed_physical_check_deals_zero_damage(self):
        """Verify that a failed physical attack deals 0 damage and does not defeat an enemy at 1 HP."""
        wounded_goblin = {
            "name": "Wounded Goblin",
            "hp": 1,
            "max_hp": 30,
            "level": 1,
            "archetype": "Skirmisher",
            "stats": {"STR": 3, "AGI": 4, "END": 3, "INT": 2, "PER": 3, "CHA": 2, "LUK": 2}
        }
        session = {
            "scenario": "fantasy",
            "combat_turn": 1,
            "nearby_enemies": [wounded_goblin],
            "current_npcs": []
        }
        player_char = {
            "name": "Hero",
            "hp": 100,
            "max_hp": 100,
            "level": 1,
            "user_id": self.user_id
        }
        party = [(player_char, None)]
        actions = [{
            "char": player_char,
            "label": "Slash with Rusty Blade",
            "stat": "STR",
            "tier": "fail",
            "choice_type": "MELEE_SLASHING_PIERCING",
            "mp_spent": 0
        }]

        precomputed = precompute_combat_turn(session, party, actions)
        self.assertNotIn("Wounded Goblin", precomputed.get("dead_enemies", []))
        self.assertEqual(wounded_goblin["hp"], 1)
        log_text = " ".join(precomputed.get("combat_log", []))
        self.assertIn("Attack failed / deflected.", log_text)

    def test_environmental_trap_success_and_failure(self):
        """Verify environmental traps deal damage and stagger on success, and do nothing on failure."""
        troll = {
            "name": "Cave Troll",
            "hp": 200,
            "max_hp": 200,
            "level": 2,
            "archetype": "Brute",
            "stats": {"STR": 6, "AGI": 3, "END": 5, "INT": 1, "PER": 3, "CHA": 1, "LUK": 2}
        }
        session = {
            "scenario": "fantasy",
            "combat_turn": 1,
            "nearby_enemies": [troll],
            "current_npcs": []
        }
        player_char = {
            "name": "Hero",
            "hp": 100,
            "max_hp": 100,
            "level": 2,
            "int_": 8,
            "user_id": self.user_id
        }
        party = [(player_char, None)]

        # Failure test
        fail_actions = [{
            "char": player_char,
            "label": "Trigger Stalactite Collapse",
            "stat": "INT",
            "tier": "fail",
            "choice_type": "ENVIRONMENTAL_TRAP",
            "mp_spent": 0
        }]
        res_fail = precompute_combat_turn(session, party, fail_actions)
        self.assertEqual(troll["hp"], 200)
        self.assertIn("failed to trigger", " ".join(res_fail.get("combat_log", [])))

        # Success test
        troll["hp"] = 200
        troll["status_effects"] = []
        session["nearby_enemies"] = [troll]
        success_actions = [{
            "char": player_char,
            "label": "Trigger Stalactite Collapse",
            "stat": "INT",
            "tier": "success",
            "choice_type": "ENVIRONMENTAL_TRAP",
            "mp_spent": 0
        }]
        res_succ = precompute_combat_turn(session, party, success_actions)
        self.assertLess(session["nearby_enemies"][0]["hp"], 200)
        self.assertTrue(any("Staggered" in str(s) for s in session["nearby_enemies"][0].get("status_effects", [])))
        self.assertIn("Staggered them", " ".join(res_succ.get("combat_log", [])))
