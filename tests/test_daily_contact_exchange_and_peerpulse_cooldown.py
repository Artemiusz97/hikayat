import pytest
import unittest
from unittest.mock import patch, MagicMock
import db
import game_engine
from game_engine.choices_cleaner import build_hybrid_turn_choices
from mechanics.system.phone import social_graph as phone
from skill_check import CheckResult


class TestDailyContactExchangeAndPeerPulseCooldown(unittest.TestCase):
    def setUp(self):
        self.user_id = 99770
        self.session_id = db.create_session(
            self.user_id,
            "solo",
            1,
            "normal",
            "direct",
            False,
            scenario="high_school_drama",
        )
        self.char_id = 88770
        with db.get_conn() as conn:
            conn.execute("DELETE FROM characters WHERE id=? OR user_id=?", (self.char_id, self.user_id))
            conn.execute(
                """INSERT INTO characters (id, user_id, name, char_class, gender, scenario,
                                          str_, per_, end_, cha, int_, agi, luk, hp, max_hp, mp, max_mp, level, xp, gold, status_effects, created_at)
                   VALUES (?, ?, 'Artem', 'Student', 'male', 'high_school_drama',
                           10, 14, 10, 12, 13, 10, 10, 100, 100, 50, 50, 1, 0, 100, '[]', 0)""",
                (self.char_id, self.user_id)
            )
        self.char = db.get_character(self.user_id)
        self.party = [(self.char, [])]
        self.session = db.get_session(self.session_id)
        # Ensure session starts on Day 1
        with db.get_conn() as conn:
            conn.execute("UPDATE sessions SET current_day=1, current_minute=500 WHERE id=?", (self.session_id,))
        self.session["current_day"] = 1
        self.session["current_minute"] = 500

        # Add Alicja Yamamoto to lorebook as eligible student peer
        db.upsert_lorebook_entity(
            self.session_id,
            "person",
            "Alicja Yamamoto",
            description="Classmate with silver hair."
        )

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM sessions WHERE id=?", (self.session_id,))
            conn.execute("DELETE FROM characters WHERE id=? OR user_id=?", (self.char_id, self.user_id))
            conn.execute("DELETE FROM contacts WHERE session_id=?", (self.session_id,))
            conn.commit()

    def test_dialogue_contact_exchange_suppressed_after_failed_check_until_next_day(self):
        """Verify that attempting contact exchange and failing does not show the option on the following turn or rest of the day, but re-enables on the next day."""
        partner = "Alicja Yamamoto"

        # Turn 1: Player in active dialogue with Alicja Yamamoto
        # Before any attempt, the priority button SHOULD be present
        choices_turn1 = build_hybrid_turn_choices(
            raw_choices=["Ask about homework", "Talk about music"],
            session=self.session,
            party=self.party,
            result={"dialogue_partners": [partner], "location": "Classroom"},
            actions=[],
        )
        has_contact_btn_t1 = any(
            isinstance(c, dict) and "Ask for Alicja Yamamoto's Phone Number" in c.get("label", "")
            for c in choices_turn1
        )
        self.assertTrue(has_contact_btn_t1, "Priority contact request button should appear for eligible stranger.")

        # Turn 1 Action: Player attempts to ask for Alicja's contact info and FAILS
        failed_contact_action = {
            "label": "📱 Ask for Alicja Yamamoto's Phone Number / Contact Info",
            "intent": "phone_contact_exchange",
            "target_npc": partner,
            "char": self.char,
            "check": CheckResult(
                roll=2.0,
                chance=40,
                tier="fail",
                tier_label="Failure",
                succeeded=False,
                requirement=14
            )
        }

        # Resolve choices for Turn 2 (choices generated at the end of Turn 1)
        raw_llm_choices_with_contact = [
            "📱 Ask for Alicja Yamamoto's Phone Number / Contact Info",
            "Ask about homework",
            "Leave the classroom"
        ]
        choices_turn2 = build_hybrid_turn_choices(
            raw_choices=raw_llm_choices_with_contact,
            session=self.session,
            party=self.party,
            result={"dialogue_partners": [partner], "location": "Classroom"},
            actions=[failed_contact_action],
        )

        # On following turn, contact exchange option MUST NOT appear (both priority slot and cleaned LLM choices)
        has_contact_btn_t2 = any(
            isinstance(c, dict) and any(kw in c.get("label", "").lower() for kw in ("phone number", "contact info", "line id"))
            for c in choices_turn2
        )
        self.assertFalse(
            has_contact_btn_t2,
            "Contact exchange option must not appear on following turn immediately after failed attempt!"
        )

        # Verify DB cooldown is recorded
        cd_mins = db.get_contact_request_cooldown(self.session_id, partner)
        self.assertGreater(cd_mins, 0, "Cooldown should be active in DB.")

        # Turn 3 (still Day 1): Player talks about something else
        normal_action = {"label": "Ask about homework", "char": self.char}
        choices_turn3 = build_hybrid_turn_choices(
            raw_choices=["Ask about homework", "📱 Ask for Alicja's Phone Number", "Say goodbye"],
            session=self.session,
            party=self.party,
            result={"dialogue_partners": [partner], "location": "Classroom"},
            actions=[normal_action],
        )
        has_contact_btn_t3 = any(
            isinstance(c, dict) and any(kw in c.get("label", "").lower() for kw in ("phone number", "contact info", "line id"))
            for c in choices_turn3
        )
        self.assertFalse(has_contact_btn_t3, "Contact exchange option must not appear during the rest of Day 1.")

        # Advance to Day 2
        with db.get_conn() as conn:
            conn.execute("UPDATE sessions SET current_day=2, current_minute=480 WHERE id=?", (self.session_id,))
        self.session["current_day"] = 2
        self.session["current_minute"] = 480

        # On Day 2, cooldown is expired
        cd_day2 = db.get_contact_request_cooldown(self.session_id, partner)
        self.assertEqual(cd_day2, 0, "Cooldown should expire once the next day arrives.")

        # On Day 2, dialogue with Alicja should offer contact exchange again
        choices_day2 = build_hybrid_turn_choices(
            raw_choices=["Ask about homework", "Say goodbye"],
            session=self.session,
            party=self.party,
            result={"dialogue_partners": [partner], "location": "Classroom"},
            actions=[normal_action],
        )
        has_contact_btn_d2 = any(
            isinstance(c, dict) and "Ask for Alicja Yamamoto's Phone Number" in c.get("label", "")
            for c in choices_day2
        )
        self.assertTrue(has_contact_btn_d2, "Contact exchange option should reappear once the following day arrives.")

    def test_peerpulse_add_friend_cooldown_only_once_per_day(self):
        """Verify PeerPulse Add Friend enforces once per day per character on failed check."""
        partner = "Alicja Yamamoto"
        npc_id = "alicja_yamamoto"

        # Lookup profile on Day 1
        prof = phone.lookup_social_profile(self.session_id, self.user_id, partner)
        self.assertIsNotNone(prof)
        self.assertFalse(prof["on_cooldown"])
        self.assertFalse(prof["is_already_contact"])

        # Send friend request with mock failed check on Day 1
        with patch("skill_check.resolve_check") as mock_check:
            mock_check.return_value = MagicMock(succeeded=False, chance=40, tier="fail", tier_label="Fail")
            res1 = phone.resolve_social_friend_request(self.session, self.user_id, prof)

            self.assertFalse(res1["accepted"])
            self.assertEqual(res1["cooldown_until_day"], 2)
            self.assertIn("tomorrow", res1["message"].lower())

            # Attempting again on Day 1 is blocked
            blocked = phone.resolve_social_friend_request(self.session, self.user_id, prof)
            self.assertFalse(blocked["accepted"])
            self.assertTrue(blocked["on_cooldown"])
            self.assertIn("tomorrow", blocked["message"].lower())

            # Profile lookup on Day 1 reflects cooldown
            prof_day1 = phone.lookup_social_profile(self.session_id, self.user_id, partner)
            self.assertTrue(prof_day1["on_cooldown"])

            # Advance to Day 2
            with db.get_conn() as conn:
                conn.execute("UPDATE sessions SET current_day=2, current_minute=500 WHERE id=?", (self.session_id,))
            self.session["current_day"] = 2
            self.session["current_minute"] = 500

            # Profile lookup on Day 2 shows cooldown is cleared
            prof_day2 = phone.lookup_social_profile(self.session_id, self.user_id, partner)
            self.assertFalse(prof_day2["on_cooldown"])

            # Friend request on Day 2 succeeds with successful check
            mock_check.return_value = MagicMock(succeeded=True, chance=85, tier="success", tier_label="Success")
            succ = phone.resolve_social_friend_request(self.session, self.user_id, prof_day2)
            self.assertTrue(succ["accepted"])

            # Now that she's a contact, subsequent requests report already friend
            again = phone.resolve_social_friend_request(self.session, self.user_id, prof_day2)
            self.assertTrue(again.get("already_friend"))

    def test_dialogue_contact_exchange_success_unlocks_and_never_reappears(self):
        """Verify that successfully exchanging contacts unlocks the NPC and the priority button never reappears."""
        from game_engine.state.social import _reduce_social_and_milestones
        partner = "Alicja Yamamoto"

        # Successful contact exchange action
        success_action = {
            "label": "📱 Ask for Alicja Yamamoto's Phone Number / Contact Info",
            "intent": "phone_contact_exchange",
            "target_npc": partner,
            "char": self.char,
            "check": CheckResult(
                roll=85.0,
                chance=80,
                tier="success",
                tier_label="Success",
                succeeded=True,
                requirement=14
            )
        }

        # Turn choices generated on the same turn as the success
        choices_next = build_hybrid_turn_choices(
            raw_choices=["Ask about homework", "📱 Ask for Alicja's Phone Number", "Say goodbye"],
            session=self.session,
            party=self.party,
            result={"dialogue_partners": [partner], "location": "Classroom"},
            actions=[success_action],
        )
        has_contact_btn = any(
            isinstance(c, dict) and any(kw in c.get("label", "").lower() for kw in ("phone number", "contact info", "line id"))
            for c in choices_next
        )
        self.assertFalse(has_contact_btn, "Contact exchange button must not appear immediately after success.")

        # Apply social outcome
        _reduce_social_and_milestones(
            self.session_id,
            self.session,
            self.party,
            {},
            [success_action],
            "high_school_drama",
            {},
            self.char_id,
            "Artem"
        )

        # Contact is now unlocked in DB
        contact = db.get_contact(self.session_id, partner, self.char_id)
        self.assertIsNotNone(contact)
        self.assertTrue(contact.get("basic_info", {}).get("contact_added"))

        # Subsequent turns (even without actions) do not offer contact request
        choices_subsequent = build_hybrid_turn_choices(
            raw_choices=["Ask about homework", "Say goodbye"],
            session=self.session,
            party=self.party,
            result={"dialogue_partners": [partner], "location": "Classroom"},
            actions=[],
        )
        has_contact_btn_sub = any(
            isinstance(c, dict) and any(kw in c.get("label", "").lower() for kw in ("phone number", "contact info", "line id"))
            for c in choices_subsequent
        )
        self.assertFalse(has_contact_btn_sub, "Contact exchange button must never reappear once unlocked.")

    def test_dialogue_contact_exchange_name_mismatch_first_and_full_name(self):
        """Verify cooldown matches whether partner is referred to as 'Alicja' or 'Alicja Yamamoto'."""
        partner = "Alicja Yamamoto"

        # Action used short name 'Alicja'
        failed_action = {
            "label": "📱 Ask for Alicja's Phone Number / Contact Info",
            "intent": "phone_contact_exchange",
            "target_npc": "Alicja",
            "char": self.char,
            "check": CheckResult(
                roll=2.0,
                chance=40,
                tier="fail",
                tier_label="Failure",
                succeeded=False,
                requirement=14
            )
        }

        # Full name in new_partners
        choices = build_hybrid_turn_choices(
            raw_choices=["Ask about homework"],
            session=self.session,
            party=self.party,
            result={"dialogue_partners": [partner], "location": "Classroom"},
            actions=[failed_action],
        )

        has_contact_btn = any(
            isinstance(c, dict) and any(kw in c.get("label", "").lower() for kw in ("phone number", "contact info", "line id"))
            for c in choices
        )
        self.assertFalse(has_contact_btn, "Cooldown must match across first name and full name.")

        # Check DB cooldown via full name and short name
        self.assertGreater(db.get_contact_request_cooldown(self.session_id, "Alicja Yamamoto"), 0)
        self.assertGreater(db.get_contact_request_cooldown(self.session_id, "Alicja"), 0)
