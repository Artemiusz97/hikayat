import unittest
import db
from mechanics.combat.spells import (
    get_spell,
    get_all_spells,
    get_starter_spells,
    calculate_spell_damage,
    format_spell_choice_label
)
from mechanics.combat.equipment import generate_spellbook_item, parse_equipment_metadata
from mechanics.combat.items import apply_item_to_target
from mechanics.combat import calculate_tactical_damage, precompute_combat_turn, tick_status_timers

class TestMagicSystem(unittest.TestCase):
    def setUp(self):
        db.init_db()

    def test_spell_matrix_completeness(self):
        spells = get_all_spells()
        self.assertGreaterEqual(len(spells), 30)

        # Check pure magic, fire, shock, ice, earth, wind, poison, holy, dark, physical
        elements = ["magical", "fire", "shock", "ice", "water", "earth", "wind", "poison", "holy", "dark", "physical"]
        for elem in elements:
            elem_spells = [s for s in spells.values() if s.get("damage_type") == elem and s.get("discipline") == "attack"]
            self.assertGreaterEqual(len(elem_spells), 1, f"Missing attack spells for element {elem}")

        # Check 3 tiers
        for tier in (1, 2, 3):
            tier_spells = [s for s in spells.values() if s.get("tier") == tier]
            self.assertGreaterEqual(len(tier_spells), 5, f"Missing spells for tier {tier}")

        # Check disciplines
        disciplines = set(s.get("discipline") for s in spells.values())
        self.assertEqual(disciplines, {"attack", "support", "curse", "summon"})

    def test_starter_spell_package(self):
        # Default fantasy starter kit for INT 4 (5 starter cantrips)
        fantasy_kit = get_starter_spells("fantasy", "Mage", int_stat=4)
        self.assertEqual(len(fantasy_kit), 5)
        
        spells = [get_spell(sid) for sid in fantasy_kit]
        attacks = [s for s in spells if s["discipline"] == "attack"]
        supports = [s for s in spells if s["discipline"] == "support"]
        curses = [s for s in spells if s["discipline"] == "curse"]

        self.assertEqual(len(attacks), 3)
        self.assertEqual(len(supports), 1)
        self.assertEqual(len(curses), 1)

    def test_spell_damage_and_mdef(self):
        firebolt = get_spell("firebolt_t3_st")
        matk = 50
        mdef = 20

        # New unified FNV legacy fallback (no defender_attrs):
        # raw = MATK * power_mult * affinity_mult = 50 * 1.2 * 1.0 = 60
        # net = raw = 60
        dmg = calculate_spell_damage(matk, firebolt, affinity_multiplier=1.0, defender_attrs={})
        self.assertEqual(dmg, 60)

        # Weakness affinity (1.25x applied to raw):
        # raw = 50 * 1.2 * 1.25 = 75.0
        # net = raw = 75
        weak_dmg = calculate_spell_damage(matk, firebolt, affinity_multiplier=1.25, defender_attrs={})
        self.assertEqual(weak_dmg, 75)

    def test_spellbook_learning_and_consumption(self):
        import random
        test_uid = random.randint(900_000_000, 999_999_999)
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id=?", (test_uid,))
            conn.execute("DELETE FROM inventory WHERE user_id=?", (test_uid,))
        db.create_character(user_id=test_uid, name="Wizard", char_class="Mage", stats=None)
        
        # Initially empty learned spells
        self.assertEqual(db.get_learned_spells(test_uid), [])

        # Create a Spellbook item in inventory
        book = generate_spellbook_item("pyroblast_t2_st")
        item_id = db.add_item(test_uid, book["name"], item_type=book["item_type"], effect=book["effect"], slot_cost=1)
        inv_item = next(i for i in db.get_inventory(test_uid) if i["id"] == item_id)

        # Use Spellbook
        ok, msg = apply_item_to_target(test_uid, inv_item, target_type="self", target_name="Wizard")
        self.assertTrue(ok)
        self.assertIn("Spell Learned", msg)
        self.assertTrue(db.has_learned_spell(test_uid, "pyroblast_t2_st"))

        # Spellbook should now be consumed
        inv_after = db.get_inventory(test_uid)
        self.assertNotIn(item_id, [i["id"] for i in inv_after])

        # Attempting to re-learn fails gracefully
        item_id2 = db.add_item(test_uid, book["name"], item_type=book["item_type"], effect=book["effect"], slot_cost=1)
        inv_item2 = next(i for i in db.get_inventory(test_uid) if i["id"] == item_id2)
        ok2, msg2 = apply_item_to_target(test_uid, inv_item2, target_type="self", target_name="Wizard")
        self.assertFalse(ok2)
        self.assertIn("already mastered", msg2)

    def test_status_effect_timers_and_dot(self):
        monster = {
            "name": "Goblin",
            "hp": 50,
            "status_effects": ["Burned [2 turns]", "Poisoned [1 turn]"]
        }

        # Tick 1: Takes Burn (8) + Poison (10) = 18 DoT
        tick_status_timers(monster)
        self.assertEqual(monster["hp"], 32)
        self.assertIn("Burned [1 turn]", monster["status_effects"])
        # Poisoned [1 turn] decrements to 0 and expires!
        self.assertNotIn("Poisoned", str(monster["status_effects"]))

        # Tick 2: Takes Burn (8) = 24 HP remaining
        tick_status_timers(monster)
        self.assertEqual(monster["hp"], 24)
        # Burn expires!
        self.assertEqual(monster["status_effects"], [])

    def test_aoe_combat_resolution(self):
        acting_char = {
            "user_id": 999888111,
            "name": "Archmage",
            "hp": 100,
            "max_hp": 100,
            "mp": 50,
            "max_mp": 50,
            "int_": 10,
            "per_": 8
        }
        enemies = [
            {"name": "Orc Grunt 1", "hp": 40, "max_hp": 40, "stats": {"END": 4}},
            {"name": "Orc Grunt 2", "hp": 40, "max_hp": 40, "stats": {"END": 4}},
            {"name": "Orc Shaman", "hp": 50, "max_hp": 50, "stats": {"END": 4}}
        ]
        action = {
            "label": "🔥 Flame Wave (AOE)",
            "spell_id": "flame_wave_t3_aoe",
            "choice_type": "MAGIC_SPELL",
            "targets": "all_enemies",
            "mp_cost": 10
        }

        session = {
            "id": 1,
            "scenario": "fantasy",
            "nearby_enemies": enemies
        }
        result = precompute_combat_turn(
            session=session,
            party=[(acting_char, None)],
            actions=[action]
        )

        # All enemies in session should take damage
        for enemy in session["nearby_enemies"]:
            self.assertLess(enemy["hp"], enemy["max_hp"])
        # Player MP should be deducted by 10
        self.assertEqual(acting_char["mp"], 40)

    def test_spell_mp_spending_lifecycle(self):
        """Verify that casting a 10 MP spell when having 37 MP leaves exactly 27 MP."""
        user_id = 888777
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id = ?", (user_id,))
        db.create_character(user_id, "Alice", char_class="Mage", stats={"STR": 5, "PER": 5, "END": 5, "CHA": 5, "INT": 8, "AGI": 5, "LUK": 5})
        # Set Alice's MP to 37
        with db.get_conn() as conn:
            conn.execute("UPDATE characters SET hp=80, max_hp=80, mp=37, max_mp=39 WHERE user_id=?", (user_id,))

        char = db.get_character(user_id)
        self.assertEqual(char["mp"], 37)

        # 1. Player picks Flame Wave (10 MP): Upfront deduction
        mp_cost = 10
        db.apply_hp_mp_delta(user_id, hp_delta=0, mp_delta=-mp_cost)
        char_after_pick = db.get_character(user_id)
        self.assertEqual(char_after_pick["mp"], 27)

        # 2. Combat resolution
        action = {
            "char": char_after_pick,
            "label": "🔥 Flame Wave (AOE)",
            "spell_id": "flame_wave_t3_aoe",
            "choice_type": "MAGIC_SPELL",
            "targets": "all_enemies",
            "mp_cost": 10,
            "mp_spent": 10
        }
        session = {
            "id": 9991,
            "scenario": "fantasy",
            "nearby_enemies": [{"name": "Dark Elf Assassin", "hp": 50, "max_hp": 50, "stats": {"END": 5}}]
        }
        precomputed = precompute_combat_turn(session, [(char_after_pick, None)], [action])
        from mechanics.combat import reconcile_combat_results
        reconciled = reconcile_combat_results(session, {"character_outcomes": []}, precomputed, party=[(char_after_pick, None)])

        # Verify outcome reports 10 MP spent
        alice_outcome = next(co for co in reconciled["character_outcomes"] if co["name"] == "Alice")
        self.assertEqual(alice_outcome["mp_change"], -10)

        # 3. Apply outcome
        import game_engine
        game_engine.apply_outcome(session["id"], [(char_after_pick, None)], reconciled, mp_already_spent={user_id: 10}, actions=[action])

        # Verify final MP is EXACTLY 27
        final_char = db.get_character(user_id)
        self.assertEqual(final_char["mp"], 27)
