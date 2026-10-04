"""
Unit and integration tests for PeerPulse Social Media Hub Mechanics:
1. Scenario Branding & Localization across genres
2. Social State & Turn-Based Rumor Charges (3 charges, 5-turn cooldown reset)
3. Difficult Rumor Scouting Check (DC 14, Quest log integration, red herring fallbacks)
4. Social Profile Lookup (Peers vs Faculty restrictions, Handles, Bios)
5. Mutual Friends, Sibling Ties, and Dynamic Social Modifiers
6. Friend Request Resolution (Hydration on accept, 5-turn cooldown on reject)
7. Suggested Peer Discovery & Dynamic Student Generation
"""
import unittest
from unittest.mock import patch, MagicMock
import db
from mechanics import phone, school_roster, relationships


class TestPeerPulseSocialApp(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        db.init_db()
        self.user_id = 112233
        self.char_id = 445566
        self.test_session_id = db.create_session(
            self.user_id, "solo", 1, "vivid", "individual", False, scenario="high_school_drama"
        )
        self.session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Westlake Academy ➔ Academic Wing ➔ Classroom 3-B",
            "current_npcs": [],
            "history": ["Turn 1", "Turn 2"]
        }

        # Create character with CHA=12, PER=14, INT=13
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE id=? OR user_id=?", (self.char_id, self.user_id))
            conn.execute(
                """INSERT INTO characters (id, user_id, name, char_class, gender, scenario,
                                          str_, per_, end_, cha, int_, agi, luk, hp, max_hp, mp, max_mp, level, xp, gold, status_effects, created_at)
                   VALUES (?, ?, 'Ren', 'Student', 'male', 'high_school_drama',
                           10, 14, 10, 12, 13, 10, 10, 100, 100, 50, 50, 1, 0, 100, '[]', 0)""",
                (self.char_id, self.user_id)
            )

        self.roster = school_roster.ensure_school_directory_exists(self.session)

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (self.test_session_id,))
            conn.execute("DELETE FROM characters WHERE id=? OR user_id=?", (self.char_id, self.user_id))
            conn.execute("DELETE FROM school_directory WHERE session_id=?", (self.test_session_id,))
            conn.execute("DELETE FROM phone_gossip_feed WHERE session_id=?", (self.test_session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id=?", (self.test_session_id,))
            conn.execute("DELETE FROM quests WHERE session_id=?", (self.test_session_id,))
            conn.commit()

    def test_scenario_branding_localization(self):
        """Verify scenario branding maps to PeerPulse and other genre-appropriate names."""
        hs_brand = phone.get_phone_branding("high_school_drama")
        self.assertEqual(hs_brand["feed_app_name"], "PeerPulse")
        self.assertEqual(hs_brand["feed_emoji"], "📶")

        cyber_brand = phone.get_phone_branding("cyberpunk")
        self.assertEqual(cyber_brand["feed_app_name"], "NetWire")
        self.assertEqual(cyber_brand["feed_emoji"], "🌐")

        scifi_brand = phone.get_phone_branding("sci_fi")
        self.assertEqual(scifi_brand["feed_app_name"], "GalactiNet")
        self.assertEqual(scifi_brand["feed_emoji"], "📡")

        steam_brand = phone.get_phone_branding("steampunk")
        self.assertEqual(steam_brand["feed_app_name"], "The Aether Club")
        self.assertEqual(steam_brand["feed_emoji"], "⚙️")

        mod_brand = phone.get_phone_branding("general_modern")
        self.assertEqual(mod_brand["feed_app_name"], "EchoFeed")
        self.assertEqual(mod_brand["feed_emoji"], "📱")

    def test_social_state_turn_based_charge_reset(self):
        """Verify rumor charges initialize to 3 and reset after 5 game turns."""
        summary = phone.get_social_state_summary(self.test_session_id, self.session)
        self.assertEqual(summary["charges"], 3)

        # Manually consume charges
        state = summary["state"]
        state["rumor_charges"] = 0
        state["rumor_last_turn"] = 2
        db.update_phone_social_state(self.test_session_id, state)

        # Still at turn 2 -> 0 charges
        summary_empty = phone.get_social_state_summary(self.test_session_id, self.session)
        self.assertEqual(summary_empty["charges"], 0)

        # Advance session history to turn 7 (5 turns later)
        session_adv = dict(self.session)
        session_adv["history"] = [f"Turn {i}" for i in range(1, 8)]

        summary_reset = phone.get_social_state_summary(self.test_session_id, session_adv)
        self.assertEqual(summary_reset["charges"], 3)

    @patch("mechanics.system.phone.call_llm_json")
    async def test_scour_feed_for_rumors_success_and_fail(self, mock_llm):
        """Verify difficult rumor scouting check, charge consumption, and quest logging."""
        mock_llm.return_value = {
            "clue": "Council President Yea-ji left a locked folder in the 3rd floor archives.",
            "source": "Student Forum Leak"
        }

        # Seed active quest
        db.upsert_quest(
            session_id=self.test_session_id,
            quest_id="sq_1",
            quest_type="Story Quest",
            title="Westlake Mysteries",
            objective="Uncover what happened in the archives.",
            is_story_quest=1
        )

        with patch("skill_check.resolve_check") as mock_check:
            # Test Success
            mock_check.return_value = MagicMock(succeeded=True, chance=55, tier="success", tier_label="Success")
            res = await phone.scour_feed_for_rumor(self.session, self.user_id)

            self.assertTrue(res["success"])
            self.assertEqual(res["charges_left"], 2)
            self.assertIn("Yea-ji", res["clue"])

            # Verify clue was logged to active story quest
            sq = db.get_active_story_quest(self.test_session_id)
            self.assertIn("Yea-ji left a locked folder", sq["current_clues"])

            # Test Failure (Noise / Red Herring)
            mock_check.return_value = MagicMock(succeeded=False, chance=55, tier="fail", tier_label="Fail")
            res_fail = await phone.scour_feed_for_rumor(self.session, self.user_id)
            self.assertFalse(res_fail["success"])
            self.assertEqual(res_fail["charges_left"], 1)
            self.assertTrue(len(res_fail.get("red_herring", "")) > 10)

    def test_social_profile_lookup_and_faculty_restriction(self):
        """Verify lookup_social_profile finds peers with handles and marks faculty as restricted."""
        # Find a student and a faculty in roster
        student = next(c for c in self.roster if c["grade"] != "Faculty")
        faculty = next(c for c in self.roster if c["grade"] == "Faculty")

        # Student lookup
        s_prof = phone.lookup_social_profile(self.test_session_id, self.user_id, student["name"])
        self.assertIsNotNone(s_prof)
        self.assertEqual(s_prof["name"], student["name"])
        self.assertTrue(s_prof["handle"].startswith("@"))
        self.assertTrue(s_prof["is_eligible"])
        self.assertFalse(s_prof["is_faculty"])

        # Faculty lookup
        f_prof = phone.lookup_social_profile(self.test_session_id, self.user_id, faculty["name"])
        self.assertIsNotNone(f_prof)
        self.assertEqual(f_prof["name"], faculty["name"])
        self.assertFalse(f_prof["is_eligible"])
        self.assertTrue(f_prof["is_faculty"])

        # Friend request on faculty should be strictly restricted
        req_res = phone.resolve_social_friend_request(self.session, self.user_id, f_prof)
        self.assertFalse(req_res["accepted"])
        self.assertEqual(req_res["error"], "restricted")

    def test_friend_request_modifiers_and_sibling_bonus(self):
        """Verify +4 bonus for sibling in contacts, club bonus, and cooldown on rejection."""
        # Find a student with a sibling
        sib_student = next(c for c in self.roster if c.get("sibling_name"))
        sibling_name = sib_student["sibling_name"]

        # Case 1: Total stranger (sibling NOT in contacts, no shared club)
        stranger_prof = phone.lookup_social_profile(self.test_session_id, self.user_id, sib_student["name"])
        self.assertFalse(stranger_prof["is_sibling_friend"])
        self.assertEqual(len(stranger_prof["mutual_friends"]), 0)

        # Case 2: Add their sibling to contacts!
        db.upsert_contact(
            session_id=self.test_session_id,
            character_id=self.char_id,
            npc_id=sibling_name.lower().replace(" ", "_"),
            name=sibling_name,
            delta_score=20,
            basic_info={"role": "Student", "grade": "Senior"}
        )

        friend_prof = phone.lookup_social_profile(self.test_session_id, self.user_id, sib_student["name"])
        self.assertTrue(friend_prof["is_sibling_friend"])
        self.assertIn(sibling_name, friend_prof["mutual_friends"])

        # Check resolution with mock roll (fail)
        with patch("skill_check.resolve_check") as mock_check:
            mock_check.return_value = MagicMock(succeeded=False, chance=70, tier="fail", tier_label="Fail")
            fail_res = phone.resolve_social_friend_request(self.session, self.user_id, friend_prof)
            self.assertFalse(fail_res["accepted"])
            self.assertIn("+4 (Friend of Sibling", fail_res["mod_reasons"][0])
            self.assertEqual(fail_res["turns_cooldown"], 5)

            # Check that immediate subsequent request is on cooldown
            blocked_res = phone.resolve_social_friend_request(self.session, self.user_id, friend_prof)
            self.assertTrue(blocked_res["on_cooldown"])

            # Check successful request hydrates into contacts
            mock_check.return_value = MagicMock(succeeded=True, chance=85, tier="success", tier_label="Success")
            # Clear cooldown
            state = db.get_phone_social_state(self.test_session_id)
            state["friend_request_cooldowns"] = {}
            db.update_phone_social_state(self.test_session_id, state)
            friend_prof["cooldown_turns_left"] = 0

            succ_res = phone.resolve_social_friend_request(self.session, self.user_id, friend_prof)
            self.assertTrue(succ_res["accepted"])

            # Verify saved in contacts table
            saved_contact = db.get_contact(self.test_session_id, friend_prof["npc_id"], character_id=self.char_id)
            self.assertIsNotNone(saved_contact)
            self.assertEqual(saved_contact["name"], sib_student["name"])

    def test_suggested_peer_discovery_and_dynamic_generation(self):
        """Verify discover_suggested_peer finds uncontacted students and dynamically generates fresh ones."""
        peer_prof = phone.discover_suggested_peer(self.test_session_id, self.user_id)
        self.assertIsNotNone(peer_prof)
        self.assertTrue(peer_prof["is_eligible"])
        self.assertNotEqual(peer_prof["grade"], "Faculty")

    def test_search_lorebook_entity_and_get_lorebook_entity(self):
        """Verify db.get_lorebook_entity retrieves records and lookup_social_profile finds them without error."""
        # Upsert a lorebook entity
        db.upsert_lorebook_entity(
            session_id=self.test_session_id,
            entity_type="person",
            name="Mystery Student X",
            description="A transfer student seen hanging around the rooftop."
        )

        # Direct db function check
        lore = db.get_lorebook_entity(self.test_session_id, "Mystery Student X")
        self.assertIsNotNone(lore)
        self.assertEqual(lore["name"], "Mystery Student X")

        # Social profile lookup check
        prof = phone.lookup_social_profile(self.test_session_id, self.user_id, "Mystery Student X")
        self.assertIsNotNone(prof)
        self.assertEqual(prof["name"], "Mystery Student X")
        self.assertTrue(prof["handle"].startswith("@"))

    def test_search_contact_sibling_web(self):
        """Verify searching for a sibling of a contact finds the sibling even if not in directory originally."""
        # Upsert a contact with a named sibling
        db.upsert_contact(
            session_id=self.test_session_id,
            character_id=self.char_id,
            npc_id="charlotte_cross",
            name="Charlotte Cross",
            basic_info={"grade": "Senior", "role": "Fencing Captain", "sibling_name": "Lysander Cross"}
        )

        # Search for "Lysander Cross"
        p_full = phone.lookup_social_profile(self.test_session_id, self.user_id, "Lysander Cross")
        self.assertIsNotNone(p_full)
        self.assertEqual(p_full["name"], "Lysander Cross")
        self.assertEqual(p_full["sibling_name"], "Charlotte Cross")
        self.assertTrue(p_full["is_sibling_friend"])
        self.assertIn("Charlotte Cross", p_full["mutual_friends"])

        # Search by first name "Lysander"
        p_first = phone.lookup_social_profile(self.test_session_id, self.user_id, "Lysander")
        self.assertIsNotNone(p_first)
        self.assertEqual(p_first["name"], "Lysander Cross")


if __name__ == "__main__":
    unittest.main()
