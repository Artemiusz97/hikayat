import unittest
import json
import db
from mechanics.combat.spells import (
    get_spell,
    register_spell,
    load_all_procedural_spells,
    generate_procedural_spell,
    SPELL_REGISTRY
)
from mechanics.narrative.choice_generator import generate_categorized_combat_actions
from mechanics.combat import calculate_tactical_damage, precompute_combat_turn
from mechanics.combat.equipment import enrich_equipment_item, is_two_handed
from mechanics.combat.items import parse_item
from cogs.character import build_character_sheet_embed


class TestSpellsDualWieldMerchantEnrich(unittest.TestCase):
    def setUp(self):
        db.init_db()

    def tearDown(self):
        to_del = [sid for sid in SPELL_REGISTRY if sid.startswith("proc_")]
        for sid in to_del:
            del SPELL_REGISTRY[sid]

    def test_procedural_spell_persistence_and_lazy_hydration(self):
        """Verify procedural spells persist to SQLite and lazy-hydrate on get_spell()."""
        # Generate a procedural spell
        proc_spell = generate_procedural_spell(tier=2, scenario="fantasy")
        spell_id = proc_spell["id"]
        self.assertTrue(spell_id.startswith("proc_"))

        # Register it (which auto-saves to db)
        register_spell(proc_spell)
        self.assertIn(spell_id, SPELL_REGISTRY)

        # Verify it was persisted to SQLite
        saved = db.get_procedural_spell(spell_id)
        self.assertIsNotNone(saved)
        self.assertEqual(saved["name"], proc_spell["name"])

        # Evict from in-memory registry to simulate bot restart
        del SPELL_REGISTRY[spell_id]
        self.assertNotIn(spell_id, SPELL_REGISTRY)

        # Lazy hydration via get_spell()
        hydrated = get_spell(spell_id)
        self.assertIsNotNone(hydrated)
        self.assertEqual(hydrated["name"], proc_spell["name"])
        self.assertEqual(hydrated["tier"], proc_spell["tier"])
        self.assertIn(spell_id, SPELL_REGISTRY)

        # Test bulk loading all procedural spells
        del SPELL_REGISTRY[spell_id]
        load_all_procedural_spells()
        self.assertIn(spell_id, SPELL_REGISTRY)

    def test_dual_wield_combat_action_choices(self):
        """Verify dual-wielding generates Dual Flurry, Off-Hand Strike, and Lead Strike choices."""
        char = {
            "id": 9991,
            "user_id": 9991,
            "name": "Duelist",
            "level": 5,
            "hp": 100,
            "max_hp": 100,
            "mp": 50,
            "max_mp": 50,
            "str_": 14,
            "agi": 16,
            "int_": 10,
            "per_": 12,
            "cha": 10,
            "luk": 10,
            "status_effects": []
        }
        # Two 1-handed weapons equipped
        main_weapon = {
            "name": "Steel Rapier",
            "item_type": "Weapon",
            "slot": "Weapon",
            "multiplier": 1.15,
            "handedness": "1H",
            "attack_types": ["thrust", "slash"],
            "damage_types": {"physical": 1.0},
            "tags": {"handedness": "1H"}
        }
        offhand_weapon = {
            "name": "Shadow Dagger",
            "item_type": "Weapon",
            "slot": "Shield",
            "multiplier": 0.85,
            "handedness": "1H",
            "attack_types": ["thrust"],
            "damage_types": {"physical": 1.0},
            "tags": {"handedness": "1H"}
        }
        inventory = [
            dict(main_weapon, equipped=True),
            dict(offhand_weapon, equipped=True)
        ]
        party = [(char, inventory)]
        monster = {"name": "Goblin Raider", "stats": {"HP": 50, "DEF": 5, "EVA": 5}}
        res = generate_categorized_combat_actions(party, monster)
        choices = res["attacks"]

        labels = [c["label"] for c in choices]
        stances = [c.get("stance") for c in choices]

        # Verify dual-wield options generated
        self.assertTrue(any("Dual Flurry" in lbl for lbl in labels), f"Missing Dual Flurry in {labels}")
        self.assertTrue(any("Off-Hand Strike" in lbl for lbl in labels), f"Missing Off-Hand Strike in {labels}")
        self.assertTrue(any("Lead Strike" in lbl for lbl in labels), f"Missing Lead Strike in {labels}")
        self.assertIn("dual_wield", stances)

    def test_dual_wield_combat_flurry_resolution(self):
        """Verify dual-wield flurry applies +15% damage bonus and logs tag in combat."""
        attacker_attrs = {"atk": 30, "matk": 10, "combat_turn": 1}
        defender_attrs = {"def": 10, "mdef": 10}

        # Single 1H attack
        res_normal = calculate_tactical_damage(
            attacker_attrs=attacker_attrs,
            defender_attrs=defender_attrs,
            weapon_meta={"multiplier": 1.0, "attack_types": ["slash"]},
            armor_meta={"base_dt": 2},
            tier="success",
            attacker_level=5,
            stance="1H"
        )
        # Dual flurry attack
        res_dual = calculate_tactical_damage(
            attacker_attrs=attacker_attrs,
            defender_attrs=defender_attrs,
            weapon_meta={"multiplier": 1.0, "attack_types": ["slash"]},
            armor_meta={"base_dt": 2},
            tier="success",
            attacker_level=5,
            stance="dual_wield"
        )
        self.assertTrue(res_dual["dual_wield"])
        self.assertGreater(res_dual["base_damage"], res_normal["base_damage"])
        self.assertAlmostEqual(res_dual["base_damage"] / res_normal["base_damage"], 1.15, delta=0.02)

        # Precompute combat turn check
        session = {
            "id": 99999,
            "nearby_enemies": [{"name": "Orc Grunt", "hp": 100, "max_hp": 100, "level": 3, "stats": {"DEF": 5}}]
        }
        party = [({"id": 101, "user_id": 101, "name": "Swordsman", "level": 3, "equipment": {}}, {})]
        actions = [{
            "user_id": 101,
            "type": "attack",
            "target": "Orc Grunt",
            "stance": "dual_wield",
            "dual_wield": True,
            "tier": "success"
        }]
        result = precompute_combat_turn(session, party, actions)
        log = "\n".join(result.get("combat_log", []))
        self.assertIn("Dual-Wield Flurry! +15% damage", log)
    def test_two_handed_shield_unavailable_in_character_profile(self):
        """Verify character sheet displays *(unavailable)* for Shield slot when 2H weapon equipped."""
        char = {
            "id": 8881,
            "user_id": 8881,
            "name": "Knight Berserker",
            "class_name": "Warrior",
            "level": 1,
            "xp": 0,
            "hp": 100,
            "max_hp": 100,
            "mp": 30,
            "max_mp": 30,
            "gold": 50,
            "str_": 16,
            "per_": 10,
            "end_": 14,
            "cha": 10,
            "int_": 8,
            "agi": 10,
            "luk": 10,
            "pending_stat_points": 0,
            "scenario": "fantasy"
        }

        # Case 1: 2H Greatsword equipped, no Shield
        equipment_2h = {
            "Weapon": {"name": "Iron Greatsword", "item_type": "Weapon", "handedness": "2H"},
            "Shield": None
        }
        self.assertTrue(is_two_handed(equipment_2h["Weapon"]))
        embed_2h = build_character_sheet_embed(char, equipment=equipment_2h)
        # Find Equipment field
        equip_field = next(f for f in embed_2h.fields if f.name == "Equipment")
        self.assertIn("🛡️ **Shield:** *(unavailable)*", equip_field.value)
        self.assertNotIn("*(empty)*", [line for line in equip_field.value.split("\n") if "Shield:" in line][0])

        # Case 2: 1H Shortsword equipped, no Shield
        equipment_1h = {
            "Weapon": {"name": "Iron Shortsword", "item_type": "Weapon", "handedness": "1H"},
            "Shield": None
        }
        self.assertFalse(is_two_handed(equipment_1h["Weapon"]))
        embed_1h = build_character_sheet_embed(char, equipment=equipment_1h)
        equip_field_1h = next(f for f in embed_1h.fields if f.name == "Equipment")
        self.assertIn("🛡️ **Shield:** *(empty)*", equip_field_1h.value)