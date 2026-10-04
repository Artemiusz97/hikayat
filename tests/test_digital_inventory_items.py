import unittest
import os
import db
import character_data as cd
from mechanics.combat.items import (
    create_digital_media_item,
    is_digital_item,
    parse_digital_item_metadata,
    apply_item_to_target,
    parse_item_effect
)
from cogs.inventory import build_inventory_embed, build_item_inspect_embed


class TestDigitalInventoryItems(unittest.TestCase):
    def setUp(self):
        # Setup clean test character
        self.user_id = 987654321
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id=?", (self.user_id,))
            conn.execute("DELETE FROM inventory WHERE user_id=?", (self.user_id,))
        stats = {s: 5 for s in cd.STATS}
        self.char = db.create_character(self.user_id, "Rei", "Mage", stats=stats, gender="Female", scenario="cyberpunk")
        self.char_id = self.char["id"]

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id=?", (self.user_id,))
            conn.execute("DELETE FROM inventory WHERE user_id=?", (self.user_id,))

    def test_create_digital_media_item(self):
        item_id = create_digital_media_item(
            user_id=self.user_id,
            contact_name="Sofia Anderson",
            media_type="photo",
            caption="A sunny afternoon selfie enjoying iced coffee at the cafe terrace."
        )
        self.assertIsNotNone(item_id)
        
        inv = db.get_inventory(self.user_id)
        self.assertEqual(len(inv), 1)
        item = inv[0]
        
        self.assertTrue(item["name"].startswith("📸 Photo: Sofia Anderson"))
        self.assertEqual(item["item_type"], "Misc")
        self.assertEqual(item["slot_cost"], 0)
        self.assertTrue(is_digital_item(item))
        
        meta = parse_digital_item_metadata(item)
        self.assertIsNotNone(meta)
        self.assertEqual(meta["contact_name"], "Sofia Anderson")
        self.assertIn("misc", meta["tags"])
        self.assertIn("digital", meta["tags"])
        self.assertEqual(meta["caption"], "A sunny afternoon selfie enjoying iced coffee at the cafe terrace.")

    def test_intimate_photo_and_video_naming_and_icons(self):
        photo_id = create_digital_media_item(
            user_id=self.user_id,
            contact_name="Elena",
            media_type="nsfw_photo",
            caption="A sultry bedroom mirror selfie in sheer lace lingerie."
        )
        video_id = create_digital_media_item(
            user_id=self.user_id,
            contact_name="Denise",
            media_type="video",
            caption="A high-energy backstage dance routine rehearsal video."
        )
        nsfw_video_id = create_digital_media_item(
            user_id=self.user_id,
            contact_name="Elena",
            media_type="nsfw_video",
            caption="A private, sultry night-time dance recording in silk robes."
        )

        inv = {i["id"]: i for i in db.get_inventory(self.user_id)}
        
        self.assertIn("🔞 Intimate Photo: Elena", inv[photo_id]["name"])
        self.assertIn("📹 Video: Denise", inv[video_id]["name"])
        self.assertIn("🔞 Intimate Video: Elena", inv[nsfw_video_id]["name"])

        self.assertEqual(cd.get_item_icon(inv[photo_id]["name"]), "🔞")
        self.assertEqual(cd.get_item_icon(inv[video_id]["name"]), "📹")
        self.assertEqual(cd.get_item_icon(inv[nsfw_video_id]["name"]), "🔞")

    def test_zero_inventory_space_usage(self):
        # Initial slots should be 0
        self.assertEqual(db.used_slots(self.user_id), 0)

        # Add 5 digital items
        for i in range(5):
            create_digital_media_item(
                user_id=self.user_id,
                contact_name=f"Contact_{i}",
                media_type="photo",
                caption=f"Photo #{i}"
            )

        # Used slots MUST still be 0
        self.assertEqual(db.used_slots(self.user_id), 0)
        self.assertEqual(len(db.get_inventory(self.user_id)), 5)

        # Add a physical sword (slot_cost = 1)
        db.add_item(self.user_id, "Iron Sword", "Weapon", slot_cost=1)
        self.assertEqual(db.used_slots(self.user_id), 1)

    def test_digital_item_not_consumed_on_use(self):
        item_id = create_digital_media_item(
            user_id=self.user_id,
            contact_name="Sofia Anderson",
            media_type="photo",
            caption="Smiling warmly by the fountain."
        )
        inv_before = db.get_inventory(self.user_id)
        self.assertEqual(len(inv_before), 1)

        item = inv_before[0]
        success, msg = apply_item_to_target(self.user_id, item, target_type="self", target_name="Yourself")

        self.assertTrue(success)
        self.assertIn("Viewing 📸 Photo from Sofia Anderson", msg)
        self.assertIn("Smiling warmly by the fountain.", msg)
        self.assertIn("remains in your inventory", msg)

        # Item MUST NOT be consumed/removed from database
        inv_after = db.get_inventory(self.user_id)
        self.assertEqual(len(inv_after), 1)
        self.assertEqual(inv_after[0]["id"], item_id)

    def test_digital_item_drop_and_delete(self):
        create_digital_media_item(
            user_id=self.user_id,
            contact_name="Sofia Anderson",
            media_type="photo",
            caption="To be deleted"
        )
        inv = db.get_inventory(self.user_id)
        self.assertEqual(len(inv), 1)

        # Drop by name
        removed = db.remove_item_by_name(self.user_id, inv[0]["name"])
        self.assertTrue(removed)

        # Item is now gone
        inv_after = db.get_inventory(self.user_id)
        self.assertEqual(len(inv_after), 0)

    def test_inspect_embed_rendering(self):
        item_id = create_digital_media_item(
            user_id=self.user_id,
            contact_name="Sofia Anderson",
            media_type="nsfw_photo",
            caption="A sultry bedroom mirror selfie in delicate lace lingerie."
        )
        item = db.get_inventory(self.user_id)[0]
        embed = build_item_inspect_embed(item, self.user_id)

        # Verify fields
        field_dict = {f.name: f.value for f in embed.fields}
        self.assertIn("Category / Type", field_dict)
        self.assertIn("Misc", field_dict["Category / Type"])
        self.assertIn("Tags", field_dict)
        self.assertIn("#misc", field_dict["Tags"])
        self.assertIn("#digital", field_dict["Tags"])
        self.assertIn("Sender / Subject", field_dict)
        self.assertEqual(field_dict["Sender / Subject"], "**Sofia Anderson**")
        self.assertIn("🖼️ Visual Description / Transcript", field_dict)
        self.assertIn("A sultry bedroom mirror selfie in delicate lace lingerie.", field_dict["🖼️ Visual Description / Transcript"])

    def test_detect_custom_message_intent(self):
        from mechanics.system.phone import detect_custom_message_intent
        self.assertEqual(detect_custom_message_intent("send nudes"), "nsfw_photo")
        self.assertEqual(detect_custom_message_intent("can you send a spicy selfie?"), "nsfw_photo")
        self.assertEqual(detect_custom_message_intent("send a video clip of your rehearsal"), "video")
        self.assertEqual(detect_custom_message_intent("send an intimate video just for me"), "nsfw_video")
        self.assertEqual(detect_custom_message_intent("send a quick picture from town"), "photo")
        self.assertEqual(detect_custom_message_intent("want to meet up for coffee later?"), "meetup")
        self.assertEqual(detect_custom_message_intent("heard any interesting rumors?"), "intel_rumor")
        self.assertEqual(detect_custom_message_intent("hello how are you doing today"), "custom")

    async def _async_test_dm_custom_message_safeguard(self):
        from mechanics.system.phone import generate_contact_dm_reply
        from unittest.mock import patch

        # Session and contact setup
        session_id = db.create_session(self.user_id, "solo", 1, "vivid", "individual", False, scenario="cyberpunk")
        contact = {
            "name": "Zihan Moon",
            "npc_id": "zihan_moon",
            "relationship_score": 75,
            "track": "romantic",
            "basic_info": {"role": "Hacker", "gender": "female"}
        }

        # Mock LLM returning text that omits bracket tag (exactly what happened in user's screenshot)
        mock_llm_response = {
            "reply_text": "Here... hope this is what you wanted! 🙈 I'm a bit nervous, but I wanted to show you more... ❤️✨",
            "affinity_delta": 2
        }

        with patch("mechanics.system.phone.call_llm_json", return_value=mock_llm_response):
            result = await generate_contact_dm_reply(
                session={"id": session_id, "scenario": "cyberpunk", "current_location": "Night City"},
                contact=contact,
                player_char=self.char,
                user_message="send nudes",
                intent="custom"
            )

        # 1. Intent should have been auto-classified as nsfw_photo
        self.assertEqual(result["intent"], "nsfw_photo")
        
        # 2. Bracketed attachment MUST have been added to reply_text
        self.assertIn("[Attached Intimate Photo:", result["reply_text"])
        
        # 3. Item MUST have been created in player's inventory
        self.assertIsNotNone(result["digital_item_id"])
        self.assertEqual(result["media_type_created"], "nsfw_photo")

        inv = db.get_inventory(self.user_id)
        self.assertEqual(len(inv), 1)
        self.assertTrue(inv[0]["name"].startswith("🔞 Intimate Photo: Zihan Moon"))
        self.assertEqual(inv[0]["slot_cost"], 0)

    def test_custom_message_dm_safeguard(self):
        import asyncio
        asyncio.run(self._async_test_dm_custom_message_safeguard())


if __name__ == "__main__":
    unittest.main()
