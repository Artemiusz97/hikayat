import unittest
import db
import character_data as cd
from mechanics.social.attributes import calculate_combat_attributes
from mechanics.combat.equipment import generate_random_equipment, build_equipment_effect_str
from mechanics.narrative.choice_generator import generate_categorized_combat_actions

class TestCombatUI(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        db.init_db()
        self.user_id = 998877665
        chars = db.get_user_characters(self.user_id)
        for c in chars:
            db.delete_character(self.user_id, c["id"])
        with db.get_conn() as conn:
            conn.execute("DELETE FROM user_settings WHERE user_id=?", (self.user_id,))

    def tearDown(self):
        chars = db.get_user_characters(self.user_id)
        for c in chars:
            db.delete_character(self.user_id, c["id"])
        with db.get_conn() as conn:
            conn.execute("DELETE FROM user_settings WHERE user_id=?", (self.user_id,))

    def test_settings_combat_ui_style(self):
        settings = db.get_settings(self.user_id)
        self.assertEqual(settings.get("combat_ui_style"), "battle_deck")

        # Update to multi_dropdown
        db.update_settings(self.user_id, combat_ui_style="multi_dropdown")
        updated = db.get_settings(self.user_id)
        self.assertEqual(updated.get("combat_ui_style"), "multi_dropdown")

    def test_unarmed_combat_actions(self):
        char = {
            "name": "Brawler", "str_": 6, "per_": 4, "end_": 5, "cha_": 3,
            "int_": 3, "agi_": 5, "luk": 4, "hp": 50, "max_hp": 50, "mp": 20, "max_mp": 20
        }
        monster = {
            "name": "Goblin Skirmisher", "level": 2,
            "stats": {"STR": 3, "PER": 3, "END": 3, "CHA": 2, "INT": 2, "AGI": 4, "LUK": 2}
        }
        party = [(char, [])]

        cat = generate_categorized_combat_actions(party, monster, "cave", "fantasy")
        self.assertEqual(cat["weapon_name"], "Fists")
        self.assertGreater(len(cat["attacks"]), 0)
        self.assertIn("Unarmed", cat["attacks"][0]["label"])
        self.assertGreater(len(cat["magic"]), 0)
        self.assertGreater(len(cat["tactics"]), 0)
        self.assertIsNotNone(cat["flee"])
        self.assertIn("Disengage", cat["flee"]["label"])

    def test_sword_equipped_combat_actions(self):
        char = {
            "name": "Swordsman", "str_": 7, "per_": 5, "end_": 6, "cha_": 3,
            "int_": 4, "agi_": 6, "luk": 3, "hp": 60, "max_hp": 60, "mp": 25, "max_mp": 25
        }
        sword = {
            "name": "Silver Longsword", "slot": "Weapon", "equipped": 1,
            "item_type": "Weapon",
            "effect": '[GEAR_JSON]{"name": "Silver Longsword", "archetype": "longsword", "attack_types": ["slash", "thrust"], "handedness": "1H", "tier": 2, "flat_bonuses": {"atk": 15}}'
        }
        party = [(char, [sword])]
        monster = {
            "name": "Armored Knight", "level": 3,
            "stats": {"STR": 5, "PER": 4, "END": 6, "CHA": 3, "INT": 3, "AGI": 3, "LUK": 3}
        }

        cat = generate_categorized_combat_actions(party, monster, "castle", "fantasy")
        self.assertEqual(cat["weapon_name"], "Silver Longsword")
        
        # Verify Slash and Thrust attack choices are generated
        labels = [a["label"] for a in cat["attacks"]]
        self.assertTrue(any("Slash" in l for l in labels))
        self.assertTrue(any("Thrust" in l for l in labels))

        # Verify magic spells require MP
        for spell in cat["magic"]:
            self.assertGreater(spell["mp_cost"], 0)



    async def test_resolve_pick_spell_and_attack_actions(self):
        from cogs.adventure import AdventureCog
        char = db.create_character(
            self.user_id, "Alice", "Mage", "human",
            stats={"STR": 3, "PER": 5, "END": 4, "CHA": 4, "INT": 8, "AGI": 4, "LUK": 4}
        )
        session_id = db.create_session(
            self.user_id, "single", 1, "standard", "dynamic", False, scenario="fantasy"
        )
        session = db.get_session(session_id)

        # Mock bot for AdventureCog
        from unittest.mock import MagicMock
        cog = AdventureCog(MagicMock())

        # Test spell pick (Flame Wave)
        pick_spell = {
            "direct_choice": {
                "label": "Flame Wave (69% • 10 MP • AOE)",
                "action_category": "magic",
                "spell_name": "Flame Wave",
                "mp_cost": 10,
                "hit_chance": 69,
                "stat": "INT"
            }
        }
        resolved = await cog._resolve_pick(session, self.user_id, pick_spell)
        self.assertEqual(resolved["mp_spent"], 10)
        self.assertIn("Flame Wave", resolved["label"])
        self.assertIsNotNone(resolved["check"])
        self.assertIsInstance(resolved["check"].roll, float)

