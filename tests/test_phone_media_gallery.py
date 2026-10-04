"""
Unit tests for Hikayat Smartphone Media Gallery App, Narrative Photo/Video Auto-Capture,
and Undergarment/Demeanor Media Grounding Synchronization.
"""
import unittest
import json
import time

import db
from mechanics.narrative.intent import classify_action_intent, IntentCategory, IntentContext
from mechanics.system.phone import (
    PHONE_BRANDING,
    get_phone_branding,
    build_phone_home_embed,
    build_media_gallery_embed,
    _build_media_item_detail_embed
)
from mechanics.combat.items import create_digital_media_item, is_digital_item, parse_digital_item_metadata
import game_engine


class TestPhoneMediaGallery(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Setup clean test session and character
        self.user_id = 88811
        chars = db.get_user_characters(self.user_id)
        for c in chars:
            db.delete_character(self.user_id, c["id"])
        inv = db.get_inventory(self.user_id)
        for item in inv:
            db.remove_item(item["id"])

        self.session_id = db.create_session(
            host_user_id=self.user_id,
            mode="solo",
            capacity=1,
            verbosity="normal",
            dialogue_mode="balanced",
            image_gen_enabled=False,
            scenario="high_school_drama"
        )
        db.create_character(
            user_id=self.user_id,
            name="Alex",
            gender="male"
        )

    def tearDown(self):
        chars = db.get_user_characters(self.user_id)
        for c in chars:
            db.delete_character(self.user_id, c["id"])
        inv = db.get_inventory(self.user_id)
        for item in inv:
            db.remove_item(item["id"])

    def test_intent_engine_media_capture_classification(self):
        """Verify Intent Engine accurately classifies photos, selfies, videos, and respects negative guards."""
        ctx = IntentContext(dialogue_partner="Maya Anderson", current_zone="Library", scenario="high_school_drama")

        # 1. Selfies
        intent1 = classify_action_intent("Take a selfie with Maya in the library", context=ctx)
        self.assertEqual(intent1.category, IntentCategory.MEDIA_CAPTURE)
        self.assertEqual(intent1.sub_target, "selfie")
        self.assertEqual(intent1.metadata.get("media_type"), "photo")
        self.assertIn("Maya", intent1.target_entity)

        # 2. Photos of objects/scenes
        intent2 = classify_action_intent("Snap a picture of the strange occult circle on the blackboard", context=ctx)
        self.assertEqual(intent2.category, IntentCategory.MEDIA_CAPTURE)
        self.assertEqual(intent2.sub_target, "photo")
        self.assertEqual(intent2.metadata.get("media_type"), "photo")

        # 3. Video Recordings
        intent3 = classify_action_intent("Record a short video clip of the argument in the courtyard", context=ctx)
        self.assertEqual(intent3.category, IntentCategory.MEDIA_CAPTURE)
        self.assertEqual(intent3.sub_target, "video")
        self.assertEqual(intent3.metadata.get("media_type"), "video")

        # 4. Spicy / NSFW Media
        intent4 = classify_action_intent("Snap a spicy intimate selfie together", context=ctx)
        self.assertEqual(intent4.category, IntentCategory.MEDIA_CAPTURE)
        self.assertTrue(intent4.metadata.get("is_nsfw"))
        self.assertEqual(intent4.metadata.get("media_type"), "nsfw_photo")

        # 5. Device Aiming Gestures
        intent5 = classify_action_intent("Point my phone at the stage to record the performance", context=ctx)
        self.assertEqual(intent5.category, IntentCategory.MEDIA_CAPTURE)

        # 6. Disambiguation Guards (Negatives: must NOT be media capture)
        intent6 = classify_action_intent("Look at the picture hanging on the hallway wall", context=ctx)
        self.assertNotEqual(intent6.category, IntentCategory.MEDIA_CAPTURE)

        intent7 = classify_action_intent("Picture this scenario in your mind", context=ctx)
        self.assertNotEqual(intent7.category, IntentCategory.MEDIA_CAPTURE)

        intent8 = classify_action_intent("Shoot an arrow at the target dummy", context=ctx)
        self.assertNotEqual(intent8.category, IntentCategory.MEDIA_CAPTURE)

    def test_phone_branding_gallery_app(self):
        """Verify all scenario branding tables contain gallery app name and emoji."""
        scenarios = ["high_school_drama", "cyberpunk", "sci_fi", "steampunk", "general_modern"]
        for scen in scenarios:
            branding = get_phone_branding(scen)
            self.assertIn("gallery_app_name", branding, f"Missing gallery_app_name for {scen}")
            self.assertIn("gallery_emoji", branding, f"Missing gallery_emoji for {scen}")
            self.assertTrue(len(branding["gallery_app_name"]) > 0)
            self.assertTrue(len(branding["gallery_emoji"]) > 0)

    def test_phone_home_embed_gallery_counter(self):
        """Verify phone home embed renders accurate photo & video counts."""
        # Add 1 photo and 1 video
        create_digital_media_item(
            user_id=self.user_id,
            contact_name="Maya Anderson",
            media_type="photo",
            caption="Maya smiling brightly by the library window.",
            subject="Library"
        )
        create_digital_media_item(
            user_id=self.user_id,
            contact_name="Sofia Anderson",
            media_type="video",
            caption="Sofia demonstrating an acrobatic flip.",
            subject="Gym"
        )

        embed = build_phone_home_embed(self.session_id, self.user_id)
        field_names = [f.name for f in embed.fields]
        self.assertTrue(any("Photo Vault" in name for name in field_names))
        vault_field = next(f for f in embed.fields if "Photo Vault" in f.name)
        self.assertIn("2", vault_field.value)
        self.assertIn("1 photos", vault_field.value)
        self.assertIn("1 videos", vault_field.value)

    def test_media_gallery_embed_filtering_and_pagination(self):
        """Verify gallery embed supports contact filters, category filters, and detail rendering."""
        # Create 3 distinct items
        item_id1 = create_digital_media_item(
            user_id=self.user_id,
            contact_name="Maya Anderson",
            media_type="photo",
            caption="Casual selfie with Maya after study session.",
            subject="Study Room"
        )
        item_id2 = create_digital_media_item(
            user_id=self.user_id,
            contact_name="Sofia Anderson",
            media_type="nsfw_photo",
            caption="Sofia posing playfully in her black lace bra.",
            subject="Bedroom"
        )
        item_id3 = create_digital_media_item(
            user_id=self.user_id,
            contact_name="Maya Anderson",
            media_type="video",
            caption="Video clip of the drama club rehearsal.",
            subject="Auditorium"
        )

        # 1. Unfiltered Gallery
        embed_all = build_media_gallery_embed(self.session_id, self.user_id, filter_contact=None, filter_type=None, page=0)
        self.assertIn("`3` items saved", embed_all.description)
        self.assertEqual(len(embed_all.fields), 3)

        # 2. Filter by Contact (Maya)
        embed_maya = build_media_gallery_embed(self.session_id, self.user_id, filter_contact="Maya Anderson", filter_type=None, page=0)
        self.assertIn("`2` items saved", embed_maya.description)
        self.assertEqual(len(embed_maya.fields), 2)

        # 3. Filter by Category (Intimate)
        embed_intimate = build_media_gallery_embed(self.session_id, self.user_id, filter_contact=None, filter_type="intimate", page=0)
        self.assertIn("`1` items saved", embed_intimate.description)
        self.assertIn("Sofia Anderson", embed_intimate.fields[0].value)

        # 4. Detailed Media Card View
        inv = db.get_inventory(self.user_id)
        item = next(it for it in inv if it["id"] == item_id2)
        detail_embed = _build_media_item_detail_embed(item)
        self.assertIn("Sofia posing playfully", detail_embed.fields[-1].value)
        self.assertIn("Sofia Anderson", detail_embed.fields[1].value)
        self.assertIn("🔞 Intimate Photo", detail_embed.fields[2].value)

    def test_story_turn_auto_capture_digital_media(self):
        """Verify that successful media capture actions during a story turn auto-create 0-slot digital items."""
        char = db.get_character(self.user_id)
        party = [(char, None)]

        action = {
            "user_id": self.user_id,
            "label": "Take a selfie with Maya in the library",
            "mp_spent": 0,
            "check": type("Check", (), {"succeeded": True, "tier": 3, "tier_label": "Success"})()
        }

        outcome = {
            "outcome_narrative": "You hold up your phone with Maya smiling beside you in the warm library light.",
            "character_outcomes": [{"name": "Alex", "hp_change": 0, "mp_change": 0}],
            "location": "High School Library"
        }

        # Apply outcome
        gained = game_engine.apply_outcome(
            self.session_id,
            party,
            outcome,
            mp_already_spent={self.user_id: 0},
            actions=[action]
        )

        # Check inventory for digital media item
        inv = db.get_inventory(self.user_id)
        digital_items = [it for it in inv if is_digital_item(it)]
        self.assertTrue(len(digital_items) >= 1)
        media_item = digital_items[0]
        meta = parse_digital_item_metadata(media_item)
        self.assertEqual(meta.get("media_type"), "photo")
        self.assertIn("Maya", meta.get("contact_name"))
        self.assertEqual(media_item.get("slot_cost"), 0)

    async def test_dm_undergarment_and_demeanor_prompt_injection(self):
        """Verify DM reply generation explicitly injects canonical undergarments and demeanor into the prompt."""
        from unittest.mock import patch, AsyncMock
        from mechanics.system.phone import generate_contact_dm_reply

        session = db.get_session(self.session_id)
        char = db.get_character(self.user_id)
        contact = {
            "name": "Maya Anderson",
            "relationship_score": 60,
            "track": "romantic",
            "basic_info": {"role": "Student Council President", "traits": ["Ambitious", "Teasing"]},
            "appearance": {
                "undergarments": {
                    "bra": "sheer crimson lace balcony bra",
                    "underwear": "matching crimson lace cheekies"
                },
                "intimate_demeanor": "Secretly Dominant & Seductive",
                "intimate_dynamic": "Switch / Sensual"
            }
        }

        captured_prompts = []
        async def mock_call(sys_prompt, user_prompt, **kwargs):
            captured_prompts.append((sys_prompt, user_prompt))
            return {
                "reply_text": "Here you go... hope you like it! [Attached Intimate Photo: Maya posing on satin sheets wearing her sheer crimson lace balcony bra and matching cheekies.]",
                "affinity_delta": 3
            }

        with patch("mechanics.system.phone.call_llm_json", side_effect=mock_call):
            res = await generate_contact_dm_reply(
                session=session,
                contact=contact,
                player_char=char,
                user_message="Send me a spicy selfie in bed",
                intent="nsfw_photo"
            )

        self.assertTrue(len(captured_prompts) > 0)
        sys_p, _ = captured_prompts[0]
        self.assertIn("sheer crimson lace balcony bra", sys_p)
        self.assertIn("matching crimson lace cheekies", sys_p)
        self.assertIn("Secretly Dominant & Seductive", sys_p)
        self.assertIn("Switch / Sensual", sys_p)
        self.assertIn("CANONICAL UNDERGARMENTS", sys_p)


if __name__ == "__main__":
    unittest.main()
