"""
Unit tests for smartphone daily limits, anti-bypass badgering penalties,
meetup relocation, shared photo/spicy pools, and gender-specific intimacy dynamics.
"""
import unittest
from unittest.mock import AsyncMock, patch
import db
from mechanics.system.phone.messaging import (
    generate_contact_dm_reply,
    generate_player_chat_message,
    get_dm_requirement,
)


class TestPhoneDailyLimitsAndInteractions(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.session_id = 919299
        self.user_id = 819299

        # Clean database
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_messages WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_daily_interactions WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.session_id,))

        db.create_character(
            user_id=self.user_id,
            name="Hiro",
            gender="male",
            stats={"STR": 5, "AGI": 5, "END": 5, "INT": 8, "PER": 6, "CHA": 8, "LUK": 4}
        )
        self.char = db.get_character(self.user_id)

        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        db.update_settings(self.user_id, debug_check_mode="always_success")

        db.save_session_location(
            session_id=self.session_id,
            location_id="academy_library",
            zone_name="Westlake High",
            primary_name="Library",
            sub_name="Reading Room",
            atmosphere="Quiet study tables."
        )
        db.save_session_location(
            session_id=self.session_id,
            location_id="academy_courtyard",
            zone_name="Westlake High",
            primary_name="Courtyard",
            sub_name="Fountain",
            atmosphere="Sunlit benches."
        )
        db.save_session_location(
            session_id=self.session_id,
            location_id="academy_cafe",
            zone_name="Westlake High",
            primary_name="Student Cafe",
            sub_name="Corner Booth",
            atmosphere="Cozy cafe."
        )

        self.contact = {
            "npc_id": "chiyo_sakura",
            "name": "Chiyo Sakura",
            "relationship_score": 25,
            "track": "romantic",
            "basic_info": {
                "role": "Art Club Classmate",
                "traits": ["Creative", "Shy"],
                "gender": "female"
            },
            "appearance": {
                "erotic_openness": "moderate",
                "bra": "White lace bra",
                "underwear": "Matching white panties",
                "intimate_demeanor": "blushing and sweet",
                "intimate_dynamic": "switch"
            }
        }

    @patch("mechanics.system.phone.messaging.mechanics.system.phone.call_llm_json", new_callable=AsyncMock)
    async def test_flirt_daily_limits_and_escalating_badgering_penalties(self, mock_llm):
        mock_llm.return_value = {
            "reply_text": "Aww, you're sweet! That made me blush a little 😊",
            "affinity_delta": 2
        }

        # 1. Attempt 1: Success
        res1 = await generate_contact_dm_reply(
            {"id": self.session_id, "scenario": "high_school_drama"},
            self.contact,
            self.char,
            "You looked really cute today Chiyo! 😉",
            intent="flirt"
        )
        self.assertEqual(res1["daily_limits"]["flirt"]["used"], 1)
        self.assertFalse(res1["daily_limits"]["flirt"]["locked"])
        self.assertEqual(res1["affinity_delta"], 2)

        # 2. Attempt 2: Success
        res2 = await generate_contact_dm_reply(
            {"id": self.session_id, "scenario": "high_school_drama"},
            self.contact,
            self.char,
            "I couldn't stop thinking about your smile earlier 💕",
            intent="flirt"
        )
        self.assertEqual(res2["daily_limits"]["flirt"]["used"], 2)
        self.assertFalse(res2["daily_limits"]["flirt"]["locked"])

        # 3. Attempt 3: Success (max attempts reached)
        res3 = await generate_contact_dm_reply(
            {"id": self.session_id, "scenario": "high_school_drama"},
            self.contact,
            self.char,
            "Honestly, you're my favorite person to talk to ❤️",
            intent="flirt"
        )
        self.assertEqual(res3["daily_limits"]["flirt"]["used"], 3)
        self.assertTrue(res3["daily_limits"]["flirt"]["locked"])

        # 4. Attempt 4 (1st Over-limit attempt): Soft refusal, 0 penalty
        mock_llm.return_value = {
            "reply_text": "Haha you're sweet, but that's enough charm for today! Let's talk about something else 😊"
        }
        res4 = await generate_contact_dm_reply(
            {"id": self.session_id, "scenario": "high_school_drama"},
            self.contact,
            self.char,
            "Come on, just one more compliment! 😉",
            intent="flirt"
        )
        self.assertEqual(res4["daily_limits"]["flirt"]["used"], 3)
        self.assertEqual(res4["daily_limits"]["flirt"]["over_limit_count"], 1)
        self.assertEqual(res4["affinity_delta"], 0)
        self.assertFalse(res4["check_result"]["succeeded"])

        # 5. Attempt 5 (2nd Over-limit attempt): Badgering penalty (-2)
        res5 = await generate_contact_dm_reply(
            {"id": self.session_id, "scenario": "high_school_drama"},
            self.contact,
            self.char,
            "You know you love it when I flirt with you! 💕",
            intent="flirt"
        )
        self.assertEqual(res5["daily_limits"]["flirt"]["over_limit_count"], 2)
        self.assertEqual(res5["affinity_delta"], -2)

        # 6. Attempt 6 (3rd Over-limit attempt): Severe badgering penalty (-4)
        res6 = await generate_contact_dm_reply(
            {"id": self.session_id, "scenario": "high_school_drama"},
            self.contact,
            self.char,
            "Don't be shy Chiyo, tell me I'm handsome! 😉",
            intent="flirt"
        )
        self.assertEqual(res6["daily_limits"]["flirt"]["over_limit_count"], 3)
        self.assertEqual(res6["affinity_delta"], -4)

        # 7. Attempt 7 (4th Over-limit attempt): Harassment penalty (-6)
        res7 = await generate_contact_dm_reply(
            {"id": self.session_id, "scenario": "high_school_drama"},
            self.contact,
            self.char,
            "Keep flirting non stop!",
            intent="flirt"
        )
        self.assertEqual(res7["daily_limits"]["flirt"]["over_limit_count"], 4)
        self.assertEqual(res7["affinity_delta"], -6)

    @patch("mechanics.system.phone.messaging.mechanics.system.phone.call_llm_json", new_callable=AsyncMock)
    async def test_daily_reset_on_clock_advancement(self, mock_llm):
        mock_llm.return_value = {"reply_text": "Sure!", "affinity_delta": 2}

        # Use up Day 1 flirt attempts
        for _ in range(3):
            await generate_contact_dm_reply(
                {"id": self.session_id, "scenario": "high_school_drama"},
                self.contact,
                self.char,
                "Flirt line",
                intent="flirt"
            )

        day1_limits = db.get_phone_daily_limits(self.session_id, self.contact["npc_id"], 1)
        self.assertTrue(day1_limits["flirt"]["locked"])
        self.assertEqual(day1_limits["flirt"]["used"], 3)

        # Advance calendar clock to Day 2
        db.update_session_time(self.session_id, current_day=2, current_minute=540)

        day2_limits = db.get_phone_daily_limits(self.session_id, self.contact["npc_id"], 2)
        self.assertFalse(day2_limits["flirt"]["locked"])
        self.assertEqual(day2_limits["flirt"]["used"], 0)
        self.assertEqual(day2_limits["flirt"]["over_limit_count"], 0)

    @patch("mechanics.system.phone.messaging.mechanics.system.phone.call_llm_json", new_callable=AsyncMock)
    async def test_meetup_proposal_and_relocation_limits(self, mock_llm):
        # 1. Initial meetup proposal
        mock_llm.return_value = {
            "reply_text": "I'd love to meet up! Let's go to the Library.",
            "affinity_delta": 2,
            "rendezvous_location": "Library"
        }
        res_prop = await generate_contact_dm_reply(
            {"id": self.session_id, "scenario": "high_school_drama"},
            self.contact,
            self.char,
            "Would you like to meet up today? 📍",
            intent="meetup"
        )
        self.assertEqual(res_prop["daily_limits"]["meetup"]["status"], "accepted")
        self.assertEqual(res_prop["daily_limits"]["meetup"]["relocations_left"], 2)
        self.assertIn("Library", res_prop["rendezvous_location"])

        # 2. Relocation 1: change spot to Courtyard
        mock_llm.return_value = {
            "reply_text": "Sure, the Courtyard sounds much nicer! See you by the fountain.",
            "affinity_delta": 2,
            "rendezvous_location": "Courtyard"
        }
        res_reloc1 = await generate_contact_dm_reply(
            {"id": self.session_id, "scenario": "high_school_drama"},
            self.contact,
            self.char,
            "Can we change the location to somewhere more private, like the Courtyard? 📍",
            intent="meetup"
        )
        self.assertEqual(res_reloc1["daily_limits"]["meetup"]["relocations_left"], 1)
        self.assertEqual(res_reloc1["daily_limits"]["meetup"]["relocations_used"], 1)
        self.assertIn("Courtyard", res_reloc1["rendezvous_location"])

        # 3. Relocation 2: change spot to Student Cafe
        mock_llm.return_value = {
            "reply_text": "Okay, let's meet at the Student Cafe instead!",
            "affinity_delta": 2,
            "rendezvous_location": "Student Cafe"
        }
        res_reloc2 = await generate_contact_dm_reply(
            {"id": self.session_id, "scenario": "high_school_drama"},
            self.contact,
            self.char,
            "Actually, let's meet at another place, the Student Cafe instead? 📍",
            intent="meetup"
        )
        self.assertEqual(res_reloc2["daily_limits"]["meetup"]["relocations_left"], 0)
        self.assertEqual(res_reloc2["daily_limits"]["meetup"]["relocations_used"], 2)
        self.assertTrue(res_reloc2["daily_limits"]["meetup"]["locked"])
        self.assertIn("Student Cafe", res_reloc2["rendezvous_location"])

        # 4. Relocation 3: Attempting beyond the 2 relocations limit -> locked / over limit
        mock_llm.return_value = {
            "reply_text": "I already agreed to change spots twice! Let's just stick with the Student Cafe."
        }
        res_reloc3 = await generate_contact_dm_reply(
            {"id": self.session_id, "scenario": "high_school_drama"},
            self.contact,
            self.char,
            "Wait, can we change spot one more time?",
            intent="meetup"
        )
        self.assertFalse(res_reloc3["check_result"]["succeeded"])
        self.assertEqual(res_reloc3["daily_limits"]["meetup"]["over_limit_count"], 1)

    @patch("mechanics.system.phone.messaging.mechanics.system.phone.call_llm_json", new_callable=AsyncMock)
    async def test_photo_shared_pool_ask_and_send(self, mock_llm):
        # 1. Ask Photo -> Contact sends photo with item drop
        mock_llm.return_value = {
            "reply_text": "Here you go! [Attached Photo: Sitting at art desk with sketchbook]",
            "affinity_delta": 2
        }
        res1 = await generate_contact_dm_reply(
            {"id": self.session_id, "scenario": "high_school_drama"},
            self.contact,
            self.char,
            "Send me a quick photo! 😊",
            intent="photo_ask"
        )
        self.assertEqual(res1["daily_limits"]["photo"]["used"], 1)
        self.assertIsNotNone(res1["digital_item_id"])

        # 2. Send Photo -> Player sends casual photo, contact reacts
        mock_llm.return_value = {
            "reply_text": "Haha love that view! You look like you're having fun ✨",
            "affinity_delta": 1
        }
        res2 = await generate_contact_dm_reply(
            {"id": self.session_id, "scenario": "high_school_drama"},
            self.contact,
            self.char,
            "Here's what I'm up to right now! [Player Photo: Sunlit courtyard]",
            intent="photo_send"
        )
        self.assertEqual(res2["daily_limits"]["photo"]["used"], 2)

        # 3. Ask Photo again -> 3rd combined attempt (reaches limit)
        mock_llm.return_value = {
            "reply_text": "Snapped one outside! [Attached Photo: Walking under sakura trees]",
            "affinity_delta": 2
        }
        res3 = await generate_contact_dm_reply(
            {"id": self.session_id, "scenario": "high_school_drama"},
            self.contact,
            self.char,
            "Can you send another selfie? 😊",
            intent="photo_ask"
        )
        self.assertEqual(res3["daily_limits"]["photo"]["used"], 3)
        self.assertTrue(res3["daily_limits"]["photo"]["locked"])

        # 4. 4th photo attempt (over limit)
        mock_llm.return_value = {
            "reply_text": "That's enough photos for today! Putting my phone away 📸"
        }
        res4 = await generate_contact_dm_reply(
            {"id": self.session_id, "scenario": "high_school_drama"},
            self.contact,
            self.char,
            "One more photo please!",
            intent="photo_ask"
        )
        self.assertFalse(res4["check_result"]["succeeded"])
        self.assertEqual(res4["daily_limits"]["photo"]["over_limit_count"], 1)

    @patch("mechanics.system.phone.messaging.mechanics.system.phone.call_llm_json", new_callable=AsyncMock)
    async def test_spicy_gender_dynamics_penalties(self, mock_llm):
        # Force skill check failure to test failure penalties
        db.update_settings(self.user_id, debug_check_mode="always_fail")

        # CASE A: Male player sends unsolicited spicy photo to modest female contact -> Severe penalty (-4 to -6)
        mock_llm.return_value = {
            "reply_text": "Why on earth would you send that to me?! Delete that right now!",
            "affinity_delta": -4
        }
        res_male_fail = await generate_contact_dm_reply(
            {"id": self.session_id, "scenario": "high_school_drama"},
            self.contact,
            self.char,  # Male char
            "Thinking of you... [Intimate Photo: Bare chest and low towel]",
            intent="spicy_send"
        )
        self.assertLessEqual(res_male_fail["affinity_delta"], -4)

        # CASE B: Female player sends unsolicited spicy photo to male contact -> Minor to no penalty (0 to -1)
        female_char = dict(self.char)
        female_char["gender"] = "female"

        male_contact = {
            "npc_id": "ren_takahashi",
            "name": "Ren Takahashi",
            "relationship_score": 30,
            "track": "romantic",
            "basic_info": {"role": "Track Captain", "traits": ["Athletic"], "gender": "male"},
            "appearance": {"erotic_openness": "moderate"}
        }

        mock_llm.return_value = {
            "reply_text": "Whoa... I really wasn't expecting that right now 😳",
            "affinity_delta": 0
        }
        res_fem_fail = await generate_contact_dm_reply(
            {"id": self.session_id, "scenario": "high_school_drama"},
            male_contact,
            female_char,
            "Thinking of you... [Intimate Photo: Lace bra tease]",
            intent="spicy_send"
        )
        self.assertGreaterEqual(res_fem_fail["affinity_delta"], -1)

    @patch("mechanics.system.phone.messaging.mechanics.system.phone.call_llm_json", new_callable=AsyncMock)
    async def test_custom_message_anti_bypass_and_false_positive_prevention(self, mock_llm):
        db.update_settings(self.user_id, debug_check_mode="always_success")

        # 1. Max out spicy limit (3/3)
        mock_llm.return_value = {
            "reply_text": "Here's something spicy for you... [Attached Intimate Photo: Silk chemise]",
            "affinity_delta": 3
        }
        for _ in range(3):
            await generate_contact_dm_reply(
                {"id": self.session_id, "scenario": "high_school_drama"},
                self.contact,
                self.char,
                "Can you send me a spicy photo? 😉",
                intent="spicy_ask"
            )

        limits = db.get_phone_daily_limits(self.session_id, self.contact["npc_id"], 1)
        self.assertTrue(limits["spicy"]["locked"])

        # 2. Player attempts to bypass limit using a custom text message asking for nudes
        mock_llm.return_value = {
            "reply_text": "I told you no more spicy pictures today. Let's talk about something else."
        }
        res_bypass = await generate_contact_dm_reply(
            {"id": self.session_id, "scenario": "high_school_drama"},
            self.contact,
            self.char,
            "hey Chiyo send me your nudes right now please",
            intent="custom"
        )
        # Should be classified into spicy, recognized as over limit, and rejected!
        self.assertFalse(res_bypass["check_result"]["succeeded"])
        self.assertEqual(res_bypass["daily_limits"]["spicy"]["over_limit_count"], 1)

        # 3. Disambiguation check: Normal innocent chat mentioning "picture" or "meet" should NOT be blocked
        mock_llm.return_value = {
            "reply_text": "Oh the art library exhibit? That was really amazing!",
            "affinity_delta": 1
        }
        res_innocent = await generate_contact_dm_reply(
            {"id": self.session_id, "scenario": "high_school_drama"},
            self.contact,
            self.char,
            "I saw that beautiful painting picture in the academy library earlier!",
            intent="custom"
        )
        # Treated as normal chat, succeeds!
        self.assertTrue(res_innocent["check_result"]["succeeded"])
        self.assertEqual(res_innocent["intent"], "custom")


if __name__ == "__main__":
    unittest.main()
