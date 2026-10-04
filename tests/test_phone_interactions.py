"""
Unit tests for Hikayat Messenger App Interactions & Tiered Skill Checks.
"""
import unittest
import db
import scenario_data
from mechanics import phone


class TestPhoneInteractions(unittest.TestCase):
    def setUp(self):
        self.session_id = 998822
        self.user_id = 887722

        # Clean up existing test data
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (self.session_id,))

        db.create_character(
            user_id=self.user_id,
            name="Aoi",
            gender="female",
            stats={"STR": 5, "AGI": 5, "END": 5, "INT": 8, "PER": 6, "CHA": 9, "LUK": 4}
        )
        self.char = db.get_character(self.user_id)

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE user_id = ?", (self.user_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.session_id,))
            conn.execute("DELETE FROM phone_appointments WHERE session_id = ?", (self.session_id,))

    def test_tiered_dc_meetup_scaling(self):
        """Verify meetup DC scales properly from hostile (-100) to lover (100)."""
        # Platonic
        self.assertEqual(phone.get_dm_requirement(-10, "meetup", track="platonic"), 15)
        self.assertEqual(phone.get_dm_requirement(0, "meetup", track="platonic"), 10)
        self.assertEqual(phone.get_dm_requirement(10, "meetup", track="platonic"), 10)
        self.assertEqual(phone.get_dm_requirement(20, "meetup", track="platonic"), 7)
        self.assertEqual(phone.get_dm_requirement(50, "meetup", track="platonic"), 5)
        self.assertEqual(phone.get_dm_requirement(70, "meetup", track="platonic"), 3)
        self.assertEqual(phone.get_dm_requirement(90, "meetup", track="platonic"), 2)

        # Romantic track bonus
        self.assertEqual(phone.get_dm_requirement(20, "meetup", track="romantic"), 6)
        self.assertEqual(phone.get_dm_requirement(50, "meetup", track="romantic"), 4)
        self.assertEqual(phone.get_dm_requirement(70, "meetup", track="romantic"), 3)
        self.assertEqual(phone.get_dm_requirement(90, "meetup", track="romantic"), 2)

    def test_tiered_dc_all_intents(self):
        """Verify DC calculations for chat, intel_rumor, flirt, photo, and nsfw_photo."""
        # Chat
        self.assertEqual(phone.get_dm_requirement(5, "chat"), 6)
        self.assertEqual(phone.get_dm_requirement(20, "chat"), 5)
        self.assertEqual(phone.get_dm_requirement(50, "chat"), 4)
        self.assertEqual(phone.get_dm_requirement(80, "chat"), 3)

        # Intel & Rumors
        self.assertEqual(phone.get_dm_requirement(5, "intel_rumor"), 8)
        self.assertEqual(phone.get_dm_requirement(20, "intel_rumor"), 6)
        self.assertEqual(phone.get_dm_requirement(50, "intel_rumor"), 4)
        self.assertEqual(phone.get_dm_requirement(80, "intel_rumor"), 3)

        # Casual Photo
        self.assertEqual(phone.get_dm_requirement(5, "photo"), 8)
        self.assertEqual(phone.get_dm_requirement(20, "photo"), 6)
        self.assertEqual(phone.get_dm_requirement(50, "photo"), 4)
        self.assertEqual(phone.get_dm_requirement(80, "photo"), 3)

        # Intimate Photo (NSFW)
        self.assertEqual(phone.get_dm_requirement(-5, "nsfw_photo", track="romantic"), 18)
        self.assertEqual(phone.get_dm_requirement(5, "nsfw_photo", track="platonic"), 14)
        self.assertEqual(phone.get_dm_requirement(20, "nsfw_photo", track="platonic"), 11)
        self.assertEqual(phone.get_dm_requirement(50, "nsfw_photo", track="platonic"), 8)
        self.assertEqual(phone.get_dm_requirement(50, "nsfw_photo", track="romantic"), 5)
        self.assertEqual(phone.get_dm_requirement(70, "nsfw_photo", track="romantic"), 3)
        self.assertEqual(phone.get_dm_requirement(90, "nsfw_photo", track="romantic"), 2)

    def test_dm_chat_view_button_composition_platonic_vs_romantic(self):
        """Verify dynamic buttons on DMChatView."""
        sess_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        platonic_contact = {
            "npc_id": "zihan_moon",
            "name": "Zihan Moon",
            "relationship_score": 25,
            "track": "platonic"
        }
        romantic_contact = {
            "npc_id": "zihan_moon",
            "name": "Zihan Moon",
            "relationship_score": 65,
            "track": "romantic"
        }

        # Platonic view
        view_platonic = phone.DMChatView(None, sess_id, self.user_id, platonic_contact, [platonic_contact])
        labels = [item.label for item in view_platonic.children if hasattr(item, "label")]
        self.assertIn("Have a Chat", labels)
        self.assertIn("Ask to Meet Up", labels)
        self.assertNotIn("Ask Out for a Date", labels)
        self.assertIn("Intel & Rumors", labels)
        self.assertIn("Exchange Photos", labels)

        # Romantic view
        view_romantic = phone.DMChatView(None, sess_id, self.user_id, romantic_contact, [romantic_contact])
        labels_rom = [item.label for item in view_romantic.children if hasattr(item, "label")]
        self.assertIn("Ask Out for a Date", labels_rom)
        self.assertNotIn("Ask to Meet Up", labels_rom)

    def test_dm_chat_view_nsfw_scenario_button(self):
        """Verify Swap Intimate Photos button renders conditionally for NSFW scenarios."""
        sess_sfw = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        contact = {"npc_id": "denise", "name": "Denise", "relationship_score": 50, "track": "romantic"}

        view_sfw = phone.DMChatView(None, sess_sfw, self.user_id, contact, [contact])
        labels_sfw = [item.label for item in view_sfw.children if hasattr(item, "label")]
        self.assertNotIn("Swap Intimate Photos", labels_sfw)

        # Check if an NSFW scenario has the button
        scenarios = scenario_data.load_scenarios()
        nsfw_scenarios = [k for k in scenarios if scenario_data.is_nsfw_scenario(k)]
        if nsfw_scenarios:
            sess_nsfw = db.create_session(
                self.user_id, "solo", 1, "vivid", "individual", False, scenario=nsfw_scenarios[0]
            )
            view_nsfw = phone.DMChatView(None, sess_nsfw, self.user_id, contact, [contact])
            labels_nsfw = [item.label for item in view_nsfw.children if hasattr(item, "label")]
            self.assertIn("Swap Intimate Photos", labels_nsfw)

    def test_database_affinity_update_resilience(self):
        """Verify update_contact_score safely updates contacts regardless of character_id or casing."""
        sess_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )

        db.upsert_contact(
            session_id=sess_id,
            character_id=0,
            npc_id="Zihan Moon",
            name="Zihan Moon",
            basic_info={"role": "Companion"},
            delta_score=10,
            track="platonic"
        )

        # Update with character_id set and normalized npc_id
        db.update_contact_score(sess_id, "zihan_moon", 45, character_id=self.char["id"])
        c = db.get_contact(sess_id, "zihan_moon", character_id=self.char["id"])
        self.assertIsNotNone(c)
        self.assertEqual(c["relationship_score"], 45)

        # Update with negative score clamping
        db.update_contact_score(sess_id, "Zihan Moon", -150, character_id=self.char["id"])
        c2 = db.get_contact(sess_id, "zihan_moon", character_id=self.char["id"])
        self.assertEqual(c2["relationship_score"], -100)

    def test_contacts_app_on_phone_main_view(self):
        """Verify Contacts App button appears on PhoneMainView with scenario branding."""
        sess_hs = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        view_hs = phone.PhoneMainView(None, sess_hs, self.user_id)
        labels_hs = [item.label for item in view_hs.children if hasattr(item, "label")]
        self.assertIn("Student Directory", labels_hs)
        self.assertIn("Line Messenger", labels_hs)

        # Cyberpunk branding
        sess_cyber = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="cyberpunk"
        )
        view_cyber = phone.PhoneMainView(None, sess_cyber, self.user_id)
        labels_cyber = [item.label for item in view_cyber.children if hasattr(item, "label")]
        self.assertIn("Net Directory", labels_cyber)

        # Home embed has contacts field
        embed = phone.build_phone_home_embed(sess_hs, self.user_id)
        field_names = [f.name for f in embed.fields]
        self.assertTrue(any("Student Directory" in name for name in field_names))

    def test_contact_view_phone_integration_vs_slash_command(self):
        """Verify ContactView includes Phone Home and Text buttons when opened from phone, but not via /contacts."""
        from cogs.contacts import ContactView
        sess_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        contacts = [{"npc_id": "denise", "name": "Denise", "relationship_score": 30, "track": "platonic"}]

        # From phone (active_contact=None)
        view_phone = ContactView(contacts, "high_school_drama", self.user_id, session_id=sess_id, from_phone=True)
        labels_phone = [item.label for item in view_phone.children if hasattr(item, "label")]
        self.assertIn("Phone Home", labels_phone)

        # From phone with active contact selected
        view_phone_active = ContactView(
            contacts, "high_school_drama", self.user_id,
            active_contact=contacts[0], session_id=sess_id, from_phone=True
        )
        labels_phone_active = [item.label for item in view_phone_active.children if hasattr(item, "label")]
        self.assertIn("Text Denise", labels_phone_active)
        self.assertIn("Contact List", labels_phone_active)
        self.assertIn("Phone Home", labels_phone_active)

        # Standard slash command (/contacts): from_phone=False
        view_slash = ContactView(contacts, "high_school_drama", self.user_id, active_contact=contacts[0])
        labels_slash = [item.label for item in view_slash.children if hasattr(item, "label")]
        self.assertNotIn("Phone Home", labels_slash)
        self.assertNotIn("Text Denise", labels_slash)

    def test_rendezvous_strictly_isolated_to_meetup_intent(self):
        """Verify rendezvous location is never displayed for non-meetup intents even if passed."""
        contact = {"npc_id": "denise", "name": "Denise", "relationship_score": 50, "track": "romantic"}

        # Simulating reply for nsfw_photo that erroneously includes a location
        nsfw_reply = {
            "reply_text": "[Attached Intimate Photo: ...] Looking good!",
            "affinity_delta": 3,
            "rendezvous_location": "old garden terrace",
            "intent": "nsfw_photo",
            "new_score": 53,
            "check_result": {
                "stat": "CHA",
                "chance": 100,
                "tier": "success",
                "tier_label": "Success",
                "succeeded": True
            }
        }
        embed = phone._build_dm_chat_embed(self.session_id, contact, last_reply=nsfw_reply)
        field_text = "\n".join(f.value for f in embed.fields)
        self.assertNotIn("Rendezvous", field_text)
        self.assertNotIn("Date:", field_text)
        self.assertNotIn("old garden terrace", field_text)

        # But for meetup intent, it MUST display
        meetup_reply = dict(nsfw_reply)
        meetup_reply["intent"] = "meetup"
        embed_meet = phone._build_dm_chat_embed(self.session_id, contact, last_reply=meetup_reply)
        field_text_meet = "\n".join(f.value for f in embed_meet.fields)
        self.assertIn("old garden terrace", field_text_meet)


if __name__ == "__main__":
    unittest.main()
