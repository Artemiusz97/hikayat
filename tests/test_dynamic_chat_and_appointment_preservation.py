"""
Unit tests for dynamic player chat generation and appointment preservation during DMs.
"""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import db
from mechanics import phone


class TestDynamicChatAndAppointmentPreservation(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.session_id = 918255
        self.user_id = 818255

        # Clean database
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_messages WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.session_id,))

        db.create_character(
            user_id=self.user_id,
            name="Aoi",
            gender="female",
            stats={"STR": 5, "AGI": 5, "END": 5, "INT": 8, "PER": 6, "CHA": 9, "LUK": 4}
        )
        self.char = db.get_character(self.user_id)

        self.session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        db.update_settings(self.user_id, debug_check_mode="always_success")

        db.save_session_location(
            session_id=self.session_id,
            location_id="westlake_library",
            zone_name="Westlake Academy",
            primary_name="School Library",
            sub_name="Study Tables",
            atmosphere="Quiet rows of books and tables."
        )
        db.save_session_location(
            session_id=self.session_id,
            location_id="westlake_rooftop",
            zone_name="Westlake Academy",
            primary_name="School Rooftop",
            sub_name="Rooftop Benches",
            atmosphere="Breezy rooftop area."
        )

        self.contact = {
            "npc_id": "maya_anderson",
            "name": "Maya Anderson",
            "relationship_score": 8,
            "track": "platonic",
            "basic_info": {
                "role": "Student Council Junior Aide",
                "grade": "Junior",
                "sibling_name": "Sofia Anderson"
            }
        }
        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char["id"],
            npc_id=self.contact["npc_id"],
            name=self.contact["name"],
            basic_info=self.contact["basic_info"],
            track=self.contact["track"]
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_messages WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.session_id,))

    def test_custom_message_intent_classification(self):
        """Conversational questions with 'hang out' must NOT be classified as meetup intent."""
        # The user's exact phrase:
        self.assertEqual(
            phone.detect_custom_message_intent("do you think she'll be mad if i hang out with you?"),
            "custom"
        )
        self.assertEqual(
            phone.detect_custom_message_intent("i had fun when we hung out"),
            "custom"
        )
        self.assertEqual(
            phone.detect_custom_message_intent("i was just drinking coffee with Sofia"),
            "custom"
        )
        # Actual invitations must still be detected as meetup:
        self.assertEqual(
            phone.detect_custom_message_intent("want to meet up for coffee later?"),
            "meetup"
        )
        self.assertEqual(
            phone.detect_custom_message_intent("are you free right now? want to meet up?"),
            "meetup"
        )
        self.assertEqual(
            phone.detect_custom_message_intent("let's hang out after school"),
            "meetup"
        )

    async def test_appointment_preservation_on_custom_message(self):
        """A custom reply must NOT overwrite an already scheduled appointment or generate a new rendezvous."""
        # 1. Existing confirmed appointment at School Library
        library_loc = "Westlake Academy ➔ School Library ➔ Study Tables"
        db.save_phone_appointment(self.session_id, "maya_anderson", "Maya Anderson", library_loc)

        session = db.get_session(self.session_id)
        custom_text = "do you think she'll be mad if i hang out with you?"

        fake_llm_reply = {
            "reply_text": "Haha, she's not the type to be mad! See you at the library soon! ✨",
            "affinity_delta": 2
        }

        with patch("mechanics.system.phone.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = fake_llm_reply

            result = await phone.generate_contact_dm_reply(
                session, self.contact, self.char, custom_text, intent="custom"
            )

        # Intent must remain custom, and rendezvous_location must be empty (not overwritten!)
        self.assertEqual(result["intent"], "custom")
        self.assertEqual(result["rendezvous_location"], "")

        # Verify the database appointment is still School Library
        appts = db.get_phone_appointments(self.session_id, status="pending")
        self.assertEqual(len(appts), 1)
        self.assertEqual(appts[0]["rendezvous_location"], library_loc)

    async def test_appointment_preservation_when_asking_to_meet_again(self):
        """If player asks to meet when an appointment already exists, it preserves the existing location."""
        library_loc = "Westlake Academy ➔ School Library ➔ Study Tables"
        db.save_phone_appointment(self.session_id, "maya_anderson", "Maya Anderson", library_loc)

        session = db.get_session(self.session_id)
        meet_text = "Are you free right now? Want to meet up somewhere quiet to talk? 📍"

        fake_llm_reply = {
            "reply_text": "We already agreed to meet at the library! See you in a bit! 😊",
            "affinity_delta": 1,
            "rendezvous_location": "Westlake Academy ➔ School Library ➔ Study Tables"
        }

        with patch("mechanics.system.phone.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = fake_llm_reply

            result = await phone.generate_contact_dm_reply(
                session, self.contact, self.char, meet_text, intent="meetup"
            )

        self.assertEqual(result["rendezvous_location"], library_loc)
        appts = db.get_phone_appointments(self.session_id, status="pending")
        self.assertEqual(len(appts), 1)
        self.assertEqual(appts[0]["rendezvous_location"], library_loc)

    async def test_dynamic_player_chat_generation(self):
        """generate_player_chat_message produces natural conversation replies based on history."""
        session = db.get_session(self.session_id)

        # First call with no prior history
        with patch("mechanics.system.phone.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"message": "Hey Maya! Busy with student council today? 📚"}

            msg1 = await phone.generate_player_chat_message(session, self.contact, self.char)
            self.assertEqual(msg1, "Hey Maya! Busy with student council today? 📚")

        # Save previous exchange into history
        db.save_phone_message(self.session_id, "maya_anderson", sender="player", message=msg1, intent="chat")
        db.save_phone_message(
            self.session_id, "maya_anderson", sender="npc",
            message="Just finished a mountain of paperwork! How's your day treating you?",
            intent="chat"
        )

        # Second call with history
        with patch("mechanics.system.phone.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"message": "Glad you finished! My day's been pretty relaxed so far 😊"}

            msg2 = await phone.generate_player_chat_message(session, self.contact, self.char)
            self.assertEqual(msg2, "Glad you finished! My day's been pretty relaxed so far 😊")

            # Check that user_prompt provided recent conversation history to the LLM
            user_prompt = mock_llm.call_args[0][1]
            self.assertIn("mountain of paperwork", user_prompt)

    async def test_generate_player_chat_strips_accidental_greeting_in_ongoing_conversation(self):
        """If the LLM accidentally generates a greeting prefix in an ongoing conversation, it is stripped."""
        session = db.get_session(self.session_id)
        db.save_phone_message(self.session_id, "maya_anderson", sender="player", message="Hey Maya!", intent="chat")
        db.save_phone_message(self.session_id, "maya_anderson", sender="npc", message="Hey! What's up?", intent="chat")

        with patch("mechanics.system.phone.call_llm_json", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = {"message": "Hey Maya! Just wrapping up some reading at the library 😊"}
            msg = await phone.generate_player_chat_message(session, self.contact, self.char)
            # The greeting prefix 'Hey Maya! ' should be stripped in an active chat
            self.assertEqual(msg, "Just wrapping up some reading at the library 😊")

    async def test_generate_player_chat_contextual_fallbacks_no_greetings(self):
        """When LLM fails or is unavailable, fallbacks directly advance the chat without repeating greetings."""
        session = db.get_session(self.session_id)

        # 1. NPC asked a question: 'How about you?'
        db.save_phone_message(self.session_id, "maya_anderson", sender="npc", message="Just finished prep! How about you? ✨", intent="chat")
        with patch("mechanics.system.phone.call_llm_json", side_effect=Exception("LLM Timeout")):
            msg = await phone.generate_player_chat_message(session, self.contact, self.char)
            self.assertFalse(msg.lower().startswith("hey"))
            self.assertFalse(msg.lower().startswith("hi"))
            self.assertTrue(any(w in msg.lower() for w in ["myself", "end", "good", "doing well", "not too bad"]))

        # 2. NPC confirmed meetup: 'meet at the office'
        db.save_phone_message(self.session_id, "maya_anderson", sender="npc", message="Why don't we meet at the office? See you soon! ✨", intent="meetup")
        with patch("mechanics.system.phone.call_llm_json", side_effect=Exception("LLM Timeout")):
            msg = await phone.generate_player_chat_message(session, self.contact, self.char)
            self.assertFalse(msg.lower().startswith("hey"))
            self.assertTrue(any(w in msg.lower() for w in ["plan", "see you", "way", "shortly"]))

        # 3. NPC teased/flirted
        db.save_phone_message(self.session_id, "maya_anderson", sender="npc", message="You're making it hard to focus on these reports! 😉", intent="flirt")
        with patch("mechanics.system.phone.call_llm_json", side_effect=Exception("LLM Timeout")):
            msg = await phone.generate_player_chat_message(session, self.contact, self.char)
            self.assertFalse(msg.lower().startswith("hey"))
            self.assertTrue(any(w in msg.lower() for w in ["distract", "truth", "comes to you", "guilty"]))


if __name__ == "__main__":
    unittest.main()
