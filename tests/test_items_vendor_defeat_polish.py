import unittest
import os
import tempfile
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import discord

import db
import game_engine
from cogs.adventure import AdventureCog
from cogs.inventory import EquipSlotSelectDropdown, build_item_inspect_embed
from mechanics.combat.items.consumables import apply_item_to_target
from mechanics.combat import reconcile_combat_results
from character_data import sanitize_status_effects


class TestItemsVendorDefeatPolish(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        db.init_db()
        self.user_id = 9999001
        db.delete_character(self.user_id)
        db.create_character(
            user_id=self.user_id,
            name="Valeros",
            gender="Male",
            race="human",
            char_class="Warrior",
            stats={"STR": 16, "PER": 10, "END": 14, "CHA": 10, "INT": 8, "AGI": 12, "LUK": 10},
            scenario="fantasy"
        )

    def tearDown(self):
        db.delete_character(self.user_id)

    # -------------------------------------------------------------------------
    # 1. Selling Equipped and Key Items to Merchants
    # -------------------------------------------------------------------------
    async def test_merchant_selling_equipped_and_key_items_guard(self):
        w_id = db.add_item(self.user_id, "Iron Longsword", "Weapon", "[ITEM_JSON]{\"archetype\": \"sword\"}")
        db.equip_item(self.user_id, w_id, "Weapon")

        key_id = db.add_item(self.user_id, "Ancient Crypt Key", "Quest Item", "[ITEM_JSON]{\"is_key_item\": true}")
        loot_id = db.add_item(self.user_id, "Silver Goblet", "Treasure", "A gleaming cup")

        inv = db.get_inventory(self.user_id)
        self.assertEqual(len(inv), 3)

        bot = MagicMock()
        cog = AdventureCog(bot)
        session_id = 123

        # Test A: Attempt to sell equipped item directly -> rejected
        interaction_equip = MagicMock(spec=discord.Interaction)
        interaction_equip.response.send_message = AsyncMock()
        await cog.sell_item(interaction_equip, session_id, self.user_id, w_id, "Iron Longsword", 50)
        interaction_equip.response.send_message.assert_awaited_once()
        msg_equip = interaction_equip.response.send_message.call_args[0][0]
        self.assertIn("cannot sell an item while it is equipped", msg_equip)

        # Test B: Attempt to sell key item directly -> rejected
        interaction_key = MagicMock(spec=discord.Interaction)
        interaction_key.response.send_message = AsyncMock()
        await cog.sell_item(interaction_key, session_id, self.user_id, key_id, "Ancient Crypt Key", 100)
        interaction_key.response.send_message.assert_awaited_once()
        msg_key = interaction_key.response.send_message.call_args[0][0]
        self.assertIn("Key narrative items cannot be sold", msg_key)

        # Test C: Sell regular carried item -> succeeds and increases gold
        char_before = db.get_character(self.user_id)
        gold_before = char_before["gold"]
        interaction_ok = MagicMock(spec=discord.Interaction)
        interaction_ok.response.edit_message = AsyncMock()
        interaction_ok.response.send_message = AsyncMock()
        await cog.sell_item(interaction_ok, session_id, self.user_id, loot_id, "Silver Goblet", 35)
        interaction_ok.response.edit_message.assert_awaited_once()

        inv_after = db.get_inventory(self.user_id)
        self.assertEqual(len(inv_after), 2)
        self.assertIsNone(next((i for i in inv_after if i["id"] == loot_id), None))
        char_after = db.get_character(self.user_id)
        self.assertEqual(char_after["gold"], gold_before + 35)

    # -------------------------------------------------------------------------
    # 2. Spellbook Compatibility Warnings & Item Inspect Card
    # -------------------------------------------------------------------------
    async def test_spellbook_study_mp_warning_and_inspect_embed(self):
        # Set max_mp to 15 (less than 26 MP cost of astral_beam_t1_st)
        with db.get_conn() as conn:
            conn.execute("UPDATE characters SET max_mp = 15, mp = 15 WHERE user_id = ?", (self.user_id,))

        char = db.get_character(self.user_id)
        self.assertEqual(char["max_mp"], 15)

        spellbook_effect = "[SPELLBOOK_JSON]{\"spell_id\": \"astral_beam_t1_st\"}"
        sb_id = db.add_item(self.user_id, "Tome of Astral Beam", "Spellbook", spellbook_effect)

        sb_item = next(i for i in db.get_inventory(self.user_id) if i["id"] == sb_id)

        # Inspect embed verification
        embed = build_item_inspect_embed(sb_item, user_id=self.user_id)
        self.assertIsNotNone(embed)
        compat_field = next((f for f in embed.fields if "Arcane Compatibility" in f.name), None)
        self.assertIsNotNone(compat_field)
        self.assertIn("Insufficient MP Capacity", compat_field.value)

        # Study the spellbook
        success, message = apply_item_to_target(self.user_id, sb_item, "self", "Valeros")
        self.assertTrue(success)
        self.assertIn("Spell Learned!", message)
        self.assertIn("⚠️ *Note: This spell requires **26 MP**", message)
        self.assertTrue(db.has_learned_spell(self.user_id, "astral_beam_t1_st"))

    # -------------------------------------------------------------------------
    # 3. Dual-Wielding Equip UX Guidance
    # -------------------------------------------------------------------------
    def test_dual_wielding_dropdown_ux(self):
        item_1h = {
            "name": "Steel Dagger",
            "item_type": "Weapon",
            "effect": "[ITEM_JSON]{\"archetype\": \"dagger\", \"handedness\": \"1H\"}"
        }
        dropdown = EquipSlotSelectDropdown(
            user_id=self.user_id,
            item=item_1h
        )
        shield_opt = next((opt for opt in dropdown.options if opt.value == "Shield"), None)
        self.assertIsNotNone(shield_opt)
        self.assertEqual(shield_opt.description, "🗡️ Equip as Off-Hand Weapon (Dual-Wielding)")
        self.assertEqual(str(shield_opt.emoji), "🗡️")

    # -------------------------------------------------------------------------
    # 4. Defeat / Revive Ailment Purge
    # -------------------------------------------------------------------------
    def test_defeat_revival_and_combat_ailment_purge(self):
        char = db.get_character(self.user_id)
        db.set_status_effects(self.user_id, [
            "Bleeding",
            "Poisoned",
            "Torn Clothes",
            "Scorched Armor",
            "Iron Skin [+8 DT] [2 turns]"
        ])

        sess_id = db.create_session(
            host_user_id=self.user_id,
            mode="solo",
            capacity=1,
            verbosity="standard",
            dialogue_mode="group",
            image_gen_enabled=False,
            scenario="fantasy"
        )
        party = [(char, [])]
        outcome = {
            "character_outcomes": [
                {
                    "name": char["name"],
                    "hp_change": 10,
                    "mp_change": 0,
                    "gold_change": 0,
                    "status_effects": ["Exhausted / Recovering"]
                }
            ]
        }
        game_engine.apply_outcome(sess_id, party, outcome)

        char_after = db.get_character(self.user_id)
        status_after = char_after.get("status_effects", "")
        self.assertIn("Exhausted / Recovering", status_after)
        self.assertNotIn("Bleeding", status_after)
        self.assertNotIn("Poisoned", status_after)
        self.assertNotIn("Torn Clothes", status_after)
        self.assertNotIn("Scorched Armor", status_after)
        self.assertNotIn("Iron Skin", status_after)

    def test_reconcile_combat_results_party_wipeout_recovery(self):
        char = db.get_character(self.user_id)
        session = {
            "id": 999,
            "nearby_enemies": [{"name": "Dragon", "hp": 500, "max_hp": 500}],
            "nearby_enemies": [{"name": "Dragon", "hp": 500, "max_hp": 500}]
        }
        party = [(char, [])]
        precomputed = {
            "combat_log": ["The dragon breathes catastrophic fire!"],
            "player_damage_by_name": {char["name"]: 2500}, # Exceeds max HP to guarantee down
            "player_damage_taken": 2500,
            "acting_char_name": char["name"],
            "dead_enemies": [],
            "xp_gain": 0,
            "gold_gain": 0
        }
        llm_outcome = {
            "narrative": "The dragon incinerates everything.",
            "character_outcomes": [
                {"name": char["name"], "hp_change": -2500, "mp_change": 0, "gold_change": 0}
            ]
        }

        reconcile_combat_results(session, llm_outcome, precomputed, party)

        # Verify hostiles cleared
        self.assertEqual(session.get("nearby_enemies"), [])
        self.assertEqual(session.get("nearby_enemies"), [])
        self.assertEqual(llm_outcome.get("nearby_enemies"), [])

        # Verify character revived at half HP with Exhausted / Recovering
        co = next(c for c in llm_outcome["character_outcomes"] if c["name"] == char["name"])
        self.assertEqual(co["status_effects"], ["Exhausted / Recovering"])
        expected_hp = max(1, char["max_hp"] // 2)
        self.assertEqual(char["hp"] + co["hp_change"], expected_hp)


if __name__ == "__main__":
    unittest.main()

