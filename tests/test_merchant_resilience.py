import unittest
import json
import db
from mechanics.combat.merchant import apply_merchant_encounter_result


class TestMerchantResilience(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.session_id = 99882
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("""
                INSERT INTO sessions (id, channel_id, host_user_id, status, mode, capacity, scenario, current_location, turn_order)
                VALUES (?, 100, 1, 'active', 'solo', 1, 'fantasy', 'Kingdom of Eldoria ➔ Rivertown ➔ Market Square', ?)
            """, (self.session_id, json.dumps([1])))

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))

    def test_apply_merchant_with_list_input(self):
        """Verify that when LLM returns an empty list or list of dicts, no AttributeError is raised."""
        # 1. Empty list
        res = apply_merchant_encounter_result(self.session_id, [])
        self.assertFalse(res["available"])

        # 2. List containing a merchant dict
        res = apply_merchant_encounter_result(self.session_id, [{"present": True, "name": "Barkeep Bob", "description": "Local seller"}])
        self.assertTrue(res["available"])
        self.assertEqual(res["flavor_name"], "Barkeep Bob")

    def test_apply_merchant_with_dict_and_none(self):
        """Verify dict and None inputs."""
        res = apply_merchant_encounter_result(self.session_id, None)
        self.assertFalse(res["available"])

        res = apply_merchant_encounter_result(self.session_id, {"present": True, "name": "Alchemist Sarah", "description": "Potions seller"})
        self.assertTrue(res["available"])
        self.assertEqual(res["flavor_name"], "Alchemist Sarah")

    def test_school_scenario_suppresses_merchant(self):
        """Verify high school scenario suppresses roadside wandering merchants."""
        with db.get_conn() as conn:
            conn.execute("UPDATE sessions SET scenario = 'high_school_drama' WHERE id = ?", (self.session_id,))

        res = apply_merchant_encounter_result(self.session_id, {"present": True, "name": "Shady Guy", "description": "Peddler"})
        self.assertFalse(res["available"])

    async def test_generate_merchant_shop_spellbook_json_serialization(self):
        """Verify generate_merchant_shop serializes spellbooks with json without NameError."""
        from unittest.mock import patch, AsyncMock
        from mechanics.combat.merchant import generate_merchant_shop

        party = [({"name": "Jack", "id": 1, "user_id": 1}, [])]
        session = {"id": self.session_id, "scenario": "steampunk", "current_location": "Engine Room"}

        mock_llm_res = {
            "intro_narrative": "Welcome to the Ledger.",
            "stock": [
                {"name": "Brass Cog", "item_type": "Item", "description": "A shiny gear", "price": 10, "quantity": 2}
            ],
            "rumors": []
        }

        with patch("mechanics.combat.merchant.call_llm_json", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_llm_res
            shop = await generate_merchant_shop(
                party, "Aetheric Dispatch", "Catalog", session,
                is_phone_shop=True, merchant_type="general_merchant"
            )
            self.assertIn("stock", shop)
            # Find injected spellbook if combat enabled
            spellbooks = [i for i in shop["stock"] if i.get("item_type") == "Spellbook"]
            for sp in spellbooks:
                self.assertTrue(sp["effect"].startswith("[SPELLBOOK_JSON]"))
                parsed = json.loads(sp["effect"].replace("[SPELLBOOK_JSON]", ""))
                self.assertEqual(parsed["item_type"], "Spellbook")

    async def test_all_item_types_in_merchant_stock_and_view(self):
        """Verify weapons, armor, potions, foods, novelties, gifts, and duplicate items are listed properly."""
        from unittest.mock import patch, AsyncMock, MagicMock
        from mechanics.combat.merchant import generate_merchant_shop, BuySelectView

        party = [({"name": "Jack", "id": 1, "user_id": 1}, [])]
        session = {"id": self.session_id, "scenario": "fantasy", "current_location": "Bazaar"}

        mock_llm_res = {
            "intro_narrative": "Finest wares in the realm!",
            "stock": [
                {"name": "Steel Longsword", "item_type": "Weapon", "description": "Sharp forged blade", "price": 150, "quantity": 1},
                {"name": "Iron Plate Armor", "item_type": "Armor", "description": "Heavy protective cuirass", "price": 200, "quantity": 1},
                {"name": "Tower Shield", "item_type": "Shield", "description": "Large wooden barrier", "price": 90, "quantity": 1},
                {"name": "Leather Boots", "item_type": "Shoes", "description": "Sturdy traveling boots", "price": 40, "quantity": 2},
                {"name": "Silk Gloves", "item_type": "Gloves", "description": "Fine embroidered gloves", "price": 35, "quantity": 1},
                {"name": "Silver Amulet", "item_type": "Gift", "description": "A shiny keepsake gift", "price": 75, "quantity": 1},
                {"name": "Music Box", "item_type": "Novelty", "description": "Plays a gentle melody", "price": 50, "quantity": 1},
                {"name": "Ration Pack", "item_type": "Food", "description": "Hardtack and dried beef", "price": 10, "quantity": 3},
                {"name": "Ration Pack", "item_type": "Food", "description": "Another identical ration", "price": 10, "quantity": 2},
            ],
            "rumors": ["Rumor 1", "Rumor 2", "Rumor 3"]
        }

        with patch("mechanics.combat.merchant.call_llm_json", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_llm_res
            shop = await generate_merchant_shop(
                party, "Bazaar Merchant", "Wares", session,
                is_phone_shop=False, merchant_type="general_merchant"
            )

            stock = shop["stock"]
            self.assertGreaterEqual(len(stock), 9)

            # 1. Verify equipment enrichment
            weapons = [i for i in stock if i["item_type"] == "Weapon"]
            self.assertTrue(len(weapons) >= 1)
            self.assertTrue(weapons[0]["effect"].startswith("[ITEM_JSON]"))

            armors = [i for i in stock if i["item_type"] == "Armor"]
            self.assertTrue(len(armors) >= 1)
            self.assertTrue(armors[0]["effect"].startswith("[ITEM_JSON]"))

            # 2. Verify BuySelectView handles duplicate item names safely without duplicate select values
            mock_cog = MagicMock()
            view = BuySelectView(mock_cog, self.session_id, stock, discount_pct=10)
            select_component = view.children[0]
            values = [opt.value for opt in select_component.options]
            # Ensure all values are unique for Discord UI
            self.assertEqual(len(values), len(set(values)))
            # Ensure none exceed Discord limit
            for opt in select_component.options:
                self.assertLessEqual(len(opt.value), 100)
                self.assertLessEqual(len(opt.label), 100)
                if opt.description:
                    self.assertLessEqual(len(opt.description), 100)

    def test_merchant_catalogue_daily_restock_logic(self):
        """Verify should_restock_merchant detects new day, 24h passage, or missing catalogue."""
        from mechanics.combat.merchant import should_restock_merchant

        # 1. Missing or empty stock
        self.assertTrue(should_restock_merchant(None, 1, 600))
        self.assertTrue(should_restock_merchant({}, 1, 600))
        self.assertTrue(should_restock_merchant({"stock": []}, 1, 600))

        # 2. Same day, 2 hours later (min 600 -> min 720) -> NO restock
        cat = {"restock_day": 1, "restock_minute": 600, "stock": [{"name": "Item A", "quantity": 1}]}
        self.assertFalse(should_restock_merchant(cat, 1, 720))

        # 3. Same day, late evening (min 600 -> min 1300) -> NO restock
        self.assertFalse(should_restock_merchant(cat, 1, 1300))

        # 4. Next day (day 1 -> day 2, min 100) -> YES restock
        self.assertTrue(should_restock_merchant(cat, 2, 100))

        # 5. Exactly 1440 minutes later (day 2, min 600) -> YES restock
        self.assertTrue(should_restock_merchant(cat, 2, 600))

        # 6. Clock rollback protection (day 2 -> day 1) -> YES restock
        cat_day2 = {"restock_day": 2, "restock_minute": 600, "stock": [{"name": "Item A", "quantity": 1}]}
        self.assertTrue(should_restock_merchant(cat_day2, 1, 600))

    def test_merchant_catalogue_preserves_stock_and_decrements_on_buy(self):
        """Verify stock persistence across visits on the same day and stock decrements."""
        from mechanics.combat.merchant import (
            get_or_create_merchant_catalogue,
            update_merchant_catalogue,
        )

        merchant = {}
        store_key = "phone_shop"
        initial_shop = {
            "intro_narrative": "Welcome to the catalog.",
            "stock": [
                {"name": "Health Potion", "item_type": "Consumable", "price": 25, "quantity": 3},
                {"name": "Iron Sword", "item_type": "Weapon", "price": 100, "quantity": 1},
            ],
            "rumors": ["Rumor A"],
        }

        # Visit 1: Initial creation at Day 1, 10:00 AM (min 600)
        cat_entry, needs_restock = get_or_create_merchant_catalogue(merchant, store_key, 1, 600)
        self.assertTrue(needs_restock)
        cat_entry = update_merchant_catalogue(merchant, store_key, initial_shop, 1, 600)
        self.assertEqual(len(cat_entry["stock"]), 2)

        # Visit 2: Later same day, 02:00 PM (min 840) -> Stock re-used
        cat_entry2, needs_restock2 = get_or_create_merchant_catalogue(merchant, store_key, 1, 840)
        self.assertFalse(needs_restock2)
        self.assertEqual(cat_entry2["stock"][0]["quantity"], 3)

        # Player buys 1 Health Potion
        cat_entry2["stock"][0]["quantity"] -= 1
        self.assertEqual(cat_entry2["stock"][0]["quantity"], 2)

        # Visit 3: Even later same day (min 1100) -> Stock still decremented to 2
        cat_entry3, needs_restock3 = get_or_create_merchant_catalogue(merchant, store_key, 1, 1100)
        self.assertFalse(needs_restock3)
        self.assertEqual(cat_entry3["stock"][0]["quantity"], 2)

        # Visit 4: Next morning (Day 2, min 450) -> Needs restock!
        cat_entry4, needs_restock4 = get_or_create_merchant_catalogue(merchant, store_key, 2, 450)
        self.assertTrue(needs_restock4)

    def test_apply_sleep_rest_clears_merchant_catalogues(self):
        """Verify sleeping overnight clears cached merchant stock so morning has fresh wares."""
        from mechanics.system.time_engine import apply_sleep_rest

        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id = 1")
        db.create_character(user_id=1, name="Hero", gold=500)

        merchant = {
            "active": True,
            "catalogues": {
                "phone_shop": {
                    "stock": [{"name": "Old Staff", "quantity": 1}],
                    "restock_day": 1,
                    "restock_minute": 600,
                }
            },
            "stock": [{"name": "Old Staff", "quantity": 1}],
        }
        db.save_merchant_state(self.session_id, merchant)

        # Ensure starting session time
        db.update_session_time(self.session_id, current_day=1, current_minute=1300, consecutive_days_awake=0)

        # Sleep overnight
        result = apply_sleep_rest(self.session_id, [1])
        self.assertEqual(result["new_day"], 2)
        self.assertEqual(result["new_minute"], 450)

        # Verify merchant catalogues were cleared in DB
        sess = db.get_session(self.session_id)
        self.assertEqual(sess["merchant"].get("catalogues"), {})
        self.assertEqual(sess["merchant"].get("stock"), [])

    async def test_enter_merchant_shop_prevents_reroll_same_day(self):
        """Verify entering shop multiple times on the same day does not call LLM shop generator again."""
        from unittest.mock import patch, AsyncMock, MagicMock
        from cogs.adventure import AdventureCog

        bot = MagicMock()
        cog = AdventureCog(bot)

        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id = 1")
        db.create_character(user_id=1, name="Hero", gold=500)
        db.update_session_time(self.session_id, current_day=1, current_minute=600, consecutive_days_awake=0)

        shop_payload = {
            "intro_narrative": "Welcome traveler!",
            "stock": [
                {"name": "Bronze Sword", "item_type": "Weapon", "description": "Basic blade", "price": 50, "quantity": 1}
            ],
            "rumors": ["Gossip"],
        }

        mock_interaction = MagicMock()
        mock_interaction.response.is_done.return_value = True
        mock_interaction.edit_original_response = AsyncMock()

        with patch("game_engine.generate_merchant_shop", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = shop_payload

            # 1st entry: calls generator
            await cog.enter_merchant_shop(mock_interaction, self.session_id, initiator_id=1, is_phone_shop=False)
            self.assertEqual(mock_gen.call_count, 1)

            # 2nd entry same day: cached, generator NOT called again!
            db.update_session_time(self.session_id, current_day=1, current_minute=900, consecutive_days_awake=0)
            await cog.enter_merchant_shop(mock_interaction, self.session_id, initiator_id=1, is_phone_shop=False)
            self.assertEqual(mock_gen.call_count, 1)

            # 3rd entry next day: restocked, generator called again!
            db.update_session_time(self.session_id, current_day=2, current_minute=480, consecutive_days_awake=0)
            await cog.enter_merchant_shop(mock_interaction, self.session_id, initiator_id=1, is_phone_shop=False)
            self.assertEqual(mock_gen.call_count, 2)

    async def test_faction_quartermaster_daily_cache(self):
        """Verify faction quartermaster stock caches daily and does not reroll on same day."""
        from unittest.mock import patch, AsyncMock, MagicMock
        from cogs.adventure import AdventureCog

        bot = MagicMock()
        cog = AdventureCog(bot)

        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id = 1")
        db.create_character(user_id=1, name="Hero", gold=500)
        db.update_session_time(self.session_id, current_day=1, current_minute=600, consecutive_days_awake=0)

        faction = {"id": "guild_thieves", "name": "Shadow Guild", "reputation_score": 100, "category": "guild"}
        qm_shop_payload = {
            "intro_narrative": "Welcome shadow brother.",
            "stock": [
                {"name": "Lockpick Set", "item_type": "Item", "description": "Thieves tools", "price": 15, "quantity": 2}
            ],
            "faction_discount_pct": 10,
        }

        mock_interaction = MagicMock()
        mock_interaction.response.is_done.return_value = True
        mock_interaction.followup.send = AsyncMock()

        with patch("mechanics.combat.merchant.generate_faction_quartermaster_shop", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = qm_shop_payload

            # 1st entry: calls generator
            await cog.faction_quartermaster(mock_interaction, self.session_id, user_id=1, faction=faction)
            self.assertEqual(mock_gen.call_count, 1)

            # 2nd entry same day: cached, generator NOT called!
            db.update_session_time(self.session_id, current_day=1, current_minute=800, consecutive_days_awake=0)
            await cog.faction_quartermaster(mock_interaction, self.session_id, user_id=1, faction=faction)
            self.assertEqual(mock_gen.call_count, 1)

            # 3rd entry next day: restocked, generator called again!
            db.update_session_time(self.session_id, current_day=2, current_minute=500, consecutive_days_awake=0)
            await cog.faction_quartermaster(mock_interaction, self.session_id, user_id=1, faction=faction)
            self.assertEqual(mock_gen.call_count, 2)

    async def test_buy_item_decrements_and_displays_sold_out(self):
        """Verify purchasing items decrements quantity in catalogue and displays sold out message when exhausted."""
        from unittest.mock import MagicMock, AsyncMock
        from cogs.adventure import AdventureCog
        from mechanics.combat.merchant import update_merchant_catalogue

        bot = MagicMock()
        cog = AdventureCog(bot)

        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id = 1")
            conn.execute("DELETE FROM inventory WHERE user_id = 1")
        db.create_character(user_id=1, name="Hero", gold=500)
        db.update_session_time(self.session_id, current_day=1, current_minute=600, consecutive_days_awake=0)

        session = db.get_session(self.session_id)
        merchant = session["merchant"]
        store_key = "local:general_merchant:Barkeep Bob"
        shop_data = {
            "intro_narrative": "Finest ales and daggers.",
            "stock": [
                {"name": "Iron Dagger", "item_type": "Weapon", "description": "Sharp", "price": 10, "quantity": 1}
            ],
            "rumors": []
        }
        cat = update_merchant_catalogue(merchant, store_key, shop_data, 1, 600)
        merchant.update({
            "active": True,
            "active_store_key": store_key,
            "stock": cat["stock"],
            "discount_pct": 0,
        })
        db.save_merchant_state(self.session_id, merchant)

        # Buy the only dagger
        mock_interaction = MagicMock()
        mock_interaction.response.edit_message = AsyncMock()
        await cog.buy_item(mock_interaction, self.session_id, user_id=1, item_name="Iron Dagger")
        mock_interaction.response.edit_message.assert_awaited_once()

        # Check that merchant catalogue in DB has quantity 0
        sess_after = db.get_session(self.session_id)
        cat_after = sess_after["merchant"]["catalogues"][store_key]
        self.assertEqual(cat_after["stock"][0]["quantity"], 0)

        # Open buy menu when sold out
        mock_buy_interaction = MagicMock()
        mock_buy_interaction.response.send_message = AsyncMock()
        await cog.open_buy_menu(mock_buy_interaction, self.session_id)
        mock_buy_interaction.response.send_message.assert_awaited_once()
        msg = mock_buy_interaction.response.send_message.call_args[0][0]
        self.assertIn("sold out for today", msg)
        self.assertIn("Day 2", msg)

    def test_merchant_encounter_dummy_placeholder_validation(self):
        """Verify TurnOutcome and MerchantEncounter gracefully handle dummy placeholder dicts from LLMs."""
        from models.llm_schemas import TurnOutcome
        from models.trackers import MerchantEncounter

        # 1. DeepSeek dummy filler dictionary without 'present'
        dummy_dict = {"_this_field_is_intentionally_left_blank_______okay_done": "OK"}
        m = MerchantEncounter.model_validate(dummy_dict)
        self.assertFalse(m.present)

        # 2. TurnOutcome with dummy merchant dict coerces to None
        outcome = TurnOutcome.model_validate({
            "scene_title": "Test Scene",
            "merchant_encounter": dummy_dict
        })
        self.assertIsNone(outcome.merchant_encounter)

        # 3. TurnOutcome with valid merchant dict validates properly
        valid_dict = {"present": True, "name": "Barkeep Bob", "description": "Local seller"}
        outcome_valid = TurnOutcome.model_validate({
            "scene_title": "Test Scene",
            "merchant_encounter": valid_dict
        })
        self.assertIsNotNone(outcome_valid.merchant_encounter)
        self.assertTrue(outcome_valid.merchant_encounter.present)
        self.assertEqual(outcome_valid.merchant_encounter.name, "Barkeep Bob")


if __name__ == "__main__":
    unittest.main()


