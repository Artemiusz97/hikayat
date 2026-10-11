"""
Test suite for Phone UI Overhaul backend logic:
- Rumor scour inserting lead and noise posts into gossip_feed
- Phone merchant delivery stock expansion (>= 8-12 items)
- Procedural fallback generation ensuring bounties/requests are never empty
"""

import unittest
from unittest.mock import patch, MagicMock
import db
import game_engine
from mechanics.system.phone.gossip_feed import scour_feed_for_rumor
from api.inventory_merchant import get_merchant_shop


class TestPhoneUIOverhaul(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.user_id = 887733
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM inventory WHERE user_id = ?", (self.user_id,))

        self.session_id = db.create_session(
            host_user_id=self.user_id,
            mode="solo",
            capacity=1,
            verbosity="standard",
            dialogue_mode="narrative",
            image_gen_enabled=False,
            scenario="highschool_rebels"
        )
        db.update_session(self.session_id, current_location="School Courtyard", current_day=1, current_minute=480)

        db.create_character(
            user_id=self.user_id,
            name="Tester",
            gender="female",
            stats={"STR": 5, "AGI": 5, "END": 5, "INT": 8, "PER": 6, "CHA": 9, "LUK": 4}
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM quests WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM inventory WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM phone_gossip_feed WHERE session_id = ?", (self.session_id,))

    async def test_scour_feed_inserts_verified_lead_post_into_gossip_feed(self):
        """When scour succeeds, a #VerifiedLead post must be prepended to gossip_feed."""
        session = db.get_session(self.session_id)
        mock_check_res = MagicMock()
        mock_check_res.succeeded = True
        mock_check_res.chance = 80
        mock_check_res.tier = "strong_hit"
        mock_check_res.tier_label = "Strong Hit"

        with patch("skill_check.resolve_check", return_value=mock_check_res), \
             patch("mechanics.system.phone.call_llm_json", return_value={"clue": "Faculty Lounge Keycode 9921", "source": "Class Rep"}):
            res = await scour_feed_for_rumor(session, self.user_id)

        self.assertTrue(res.get("success"))
        self.assertIn("Faculty Lounge Keycode", res.get("clue", ""))
        self.assertIn("gossip_feed", res)
        feed = res["gossip_feed"]
        self.assertGreaterEqual(len(feed), 1)
        top_post = feed[0]
        self.assertTrue(top_post.get("is_lead"))
        self.assertEqual(top_post.get("tag"), "#VerifiedLead")

        # Verify persisted to DB
        persisted_feed = db.get_gossip_feed(self.session_id, limit=10)
        self.assertGreaterEqual(len(persisted_feed), 1)
        self.assertEqual(persisted_feed[0].get("tag"), "#VerifiedLead")
        self.assertTrue(persisted_feed[0].get("clue_hook"))

    async def test_scour_feed_inserts_noise_post_when_check_fails(self):
        """When scour check fails, a random chatter post is prepended to feed."""
        session = db.get_session(self.session_id)
        mock_check_res = MagicMock()
        mock_check_res.succeeded = False
        mock_check_res.chance = 20
        mock_check_res.tier = "miss"
        mock_check_res.tier_label = "Miss"

        with patch("skill_check.resolve_check", return_value=mock_check_res):
            res = await scour_feed_for_rumor(session, self.user_id)

        self.assertFalse(res.get("success"))
        self.assertIsNone(res.get("clue"))
        feed = res.get("gossip_feed", [])
        self.assertGreaterEqual(len(feed), 1)
        top_post = feed[0]
        self.assertEqual(top_post.get("tag"), "#CampusChat")

    async def test_phone_shop_has_at_least_8_items_with_delivery_stock(self):
        """Phone shop delivery inventory must have 8-12 diverse items."""
        payload = await get_merchant_shop(self.session_id, self.user_id, is_phone_shop=True)
        inventory = payload.get("inventory", [])

        self.assertGreaterEqual(len(inventory), 8)
        names = [item["name"] for item in inventory]
        self.assertTrue(any("Energy Drink" in n or "Bento" in n or "Power Bank" in n for n in names))

    async def test_procedural_fallback_bounties_generated_when_empty(self):
        """Procedural fallback generation guarantees bounties are not empty for phone."""
        session = db.get_session(self.session_id)
        # Force LLM to return empty so fallback triggers
        with patch("mechanics.narrative.bounty.call_llm_json", return_value={"bounties": []}):
            bounties = await game_engine.generate_bounty_board(session, force_refresh=True)

        self.assertGreaterEqual(len(bounties), 3)
        for b in bounties:
            self.assertEqual(b.get("status"), "Available")
            self.assertTrue(b.get("title"))
            self.assertTrue(b.get("quest_type"))
            self.assertGreater(b.get("reward_gold"), 0)
