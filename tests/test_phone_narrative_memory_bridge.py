import unittest
import time
import json
from unittest.mock import patch, AsyncMock
import db
from game_engine.turn.dialogue import _build_dialogue_prompt_block
from game_engine.turn_context import TurnContext
from mechanics.system.phone.messaging import generate_contact_dm_reply
from mechanics.social.persona.intimacy.formatting import format_milestone_memory

class TestPhoneNarrativeMemoryBridge(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.user_id = 99887766
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
        self.char = db.create_character(self.user_id, "Protagonist", "Adventurer")
        self.char_id = self.char["id"]
        self.session_id = db.create_session(
            host_user_id=self.user_id,
            mode="Solo",
            capacity=1,
            verbosity="normal",
            dialogue_mode="full",
            image_gen_enabled=False,
            scenario="high_school"
        )
        
        # Create test contact
        self.npc_id = "mia_yamada"
        self.contact_name = "Mia Yamada"
        self.contact = db.upsert_contact(
            session_id=self.session_id,
            npc_id=self.npc_id,
            name=self.contact_name,
            character_id=self.char_id,
            delta_score=45,
            track="platonic",
            basic_info={"role": "Class Clown & Slacker", "grade": "Junior", "description": "Playful student"},
            appearance={"erotic_openness": "moderate"}
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM phone_messages WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM inventory WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE id = ?", (self.char_id,))

    def test_dm_media_exchange_records_caption_aware_milestone(self):
        """Verify that sending/receiving media over DM records caption-specific milestone in contact memories."""
        video_caption = "A short video clip of Mia Yamada in relaxed silk loungewear, posing playfully in warm ambient lighting and blowing a gentle kiss to the camera"
        mock_llm_reply = {
            "reply_text": f"Here you go! [Attached Intimate Video: {video_caption}]",
            "affinity_delta": 4
        }

        session = db.get_session(self.session_id)
        char = self.char
        contact = db.get_contact(self.session_id, self.npc_id)

        with patch("mechanics.system.phone.call_llm_json", new_callable=AsyncMock) as mock_call, \
             patch("mechanics.system.phone.messaging.resolve_check") as mock_chk:
            from skill_check import CheckResult
            mock_chk.return_value = CheckResult(chance=1.0, roll=0.1, tier="success", tier_label="Success", succeeded=True)
            mock_call.return_value = mock_llm_reply

            import asyncio
            result = asyncio.run(generate_contact_dm_reply(
                session=session,
                contact=contact,
                player_char=char,
                user_message="Send me that clip from earlier!",
                intent="nsfw_video"
            ))

        self.assertIn("reply_text", result)
        self.assertTrue(result["check_result"]["succeeded"])

        # Check contact memories
        updated_c = db.get_contact(self.session_id, self.npc_id)
        intimate_mems = updated_c.get("intimate_memories", [])
        self.assertTrue(
            any("Exchanged intimate video via DM: Mia Yamada" in str(m) and "relaxed silk loungewear" in str(m) for m in intimate_mems),
            f"Expected caption-aware intimate video memory in {intimate_mems}"
        )

        # Check inventory collectible
        inv = db.get_inventory(self.user_id)
        self.assertTrue(any("Intimate Video: Mia Yamada" in item["name"] for item in inv))

    def test_dm_meetup_records_rendezvous_milestone(self):
        """Verify that agreeing on a meetup over DM records a milestone in contact memories."""
        mock_llm_reply = {
            "reply_text": "Deal, let's slip into the empty music room instead! 🎹",
            "affinity_delta": 3,
            "rendezvous_location": "Music Room"
        }

        session = db.get_session(self.session_id)
        char = self.char
        contact = db.get_contact(self.session_id, self.npc_id)

        with patch("mechanics.system.phone.call_llm_json", new_callable=AsyncMock) as mock_call, \
             patch("mechanics.system.phone.messaging.resolve_check") as mock_chk:
            from skill_check import CheckResult
            mock_chk.return_value = CheckResult(chance=1.0, roll=0.1, tier="success", tier_label="Success", succeeded=True)
            mock_call.return_value = mock_llm_reply

            import asyncio
            result = asyncio.run(generate_contact_dm_reply(
                session=session,
                contact=contact,
                player_char=char,
                user_message="Can we meet somewhere more private?",
                intent="meetup"
            ))

        updated_c = db.get_contact(self.session_id, self.npc_id)
        recent_mems = updated_c.get("recent_memories", [])
        self.assertTrue(
            any("Agreed via DM to meet for" in str(m) and "Music Room" in str(m) for m in recent_mems),
            f"Expected rendezvous milestone in {recent_mems}"
        )

    def test_in_person_dialogue_prompt_injects_fresh_phone_texts(self):
        """Verify that fresh phone texts and media callback hints are injected into in-person dialogue prompt."""
        # Insert phone messages
        db.save_phone_message(self.session_id, self.npc_id, sender="npc", message="[Attached Intimate Video: Mia posing playfully in silk loungewear]", intent="nsfw_video")
        db.save_phone_message(self.session_id, self.npc_id, sender="player", message="Can we meet at the music room?", intent="meetup")
        db.save_phone_message(self.session_id, self.npc_id, sender="npc", message="Deal! See you there! 🎹", intent="meetup")

        session = db.get_session(self.session_id)
        char = db.get_character(self.char_id)
        ctx = TurnContext(self.session_id, session, char)

        prompt_block = _build_dialogue_prompt_block(
            session=session,
            ctx=ctx,
            new_partners=[self.contact_name],
            party=[char],
            actions=[{"label": "Greet Mia with a smile", "check": {"succeeded": True}}]
        )

        self.assertIn("RECENT MOBILE TEXTS & EXCHANGES WITH Mia Yamada", prompt_block)
        self.assertIn("Can we meet at the music room?", prompt_block)
        self.assertIn("EXCHANGED MEDIA CALLBACK (PROACTIVE)", prompt_block)
        self.assertIn("AGREED MEETUP CONTINUITY", prompt_block)

    def test_freshness_lifecycle_stamping(self):
        """Verify that update_contact_in_person_timestamp marks texts as acknowledged so they aren't repeated every turn."""
        t_msg = time.time() - 10
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO phone_messages (session_id, contact_npc_id, sender, message, intent, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (self.session_id, self.npc_id, "npc", "Hey see you soon!", "chat", t_msg)
            )

        session = db.get_session(self.session_id)
        char = db.get_character(self.char_id)
        ctx = TurnContext(self.session_id, session, char)

        # Before meeting in person: should show fresh texts
        prompt1 = _build_dialogue_prompt_block(
            session=session,
            ctx=ctx,
            new_partners=[self.contact_name],
            party=[char],
            actions=[]
        )
        self.assertIn("RECENT MOBILE TEXTS & EXCHANGES WITH Mia Yamada", prompt1)

        # Meet in person: update timestamp
        db.update_contact_in_person_timestamp(self.session_id, self.contact_name)

        # Refresh context cache
        ctx2 = TurnContext(self.session_id, session, char)
        prompt2 = _build_dialogue_prompt_block(
            session=session,
            ctx=ctx2,
            new_partners=[self.contact_name],
            party=[char],
            actions=[]
        )
        self.assertNotIn("RECENT MOBILE TEXTS & EXCHANGES WITH Mia Yamada", prompt2)

    def test_bidirectional_dm_prompt_injects_in_person_memories(self):
        """Verify that recent in-person memories are injected into the phone DM prompt so NPCs recall what happened face-to-face."""
        db.upsert_contact(
            session_id=self.session_id,
            character_id=self.char_id,
            npc_id=self.npc_id,
            name=self.contact_name,
            new_memory="Shared a passionate first kiss in the empty music room after class"
        )

        session = db.get_session(self.session_id)
        char = self.char
        contact = db.get_contact(self.session_id, self.npc_id)

        with patch("mechanics.system.phone.call_llm_json", new_callable=AsyncMock) as mock_call, \
             patch("mechanics.system.phone.messaging.resolve_check") as mock_chk:
            from skill_check import CheckResult
            mock_chk.return_value = CheckResult(chance=1.0, roll=0.1, tier="success", tier_label="Success", succeeded=True)
            mock_call.return_value = {"reply_text": "Hey!", "affinity_delta": 1}

            import asyncio
            asyncio.run(generate_contact_dm_reply(
                session=session,
                contact=contact,
                player_char=char,
                user_message="Hey Mia!",
                intent="chat"
            ))

            call_args = mock_call.call_args[0]
            system_prompt = call_args[0]
            self.assertIn("RECENT IN-PERSON SHARED EXPERIENCES & MEMORIES", system_prompt)
            self.assertIn("kiss in the empty music room", system_prompt)

if __name__ == "__main__":
    unittest.main()
