import os
import sys
import asyncio
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
import game_engine
from cogs.adventure import AdventureCog
from mechanics.world.mobility import has_narrative_continuity_bridge, is_dialogue_partner

from game_engine.choices_cleaner import clean_choices_impl, is_exempt_free_action, infer_choice_stat_and_dc


class TestDialogueRetentionAndBystanderIsolation(unittest.TestCase):

    def setUp(self):
        self.test_session_id = 887755
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.test_session_id,))
            conn.commit()

    def tearDown(self):
        with db.get_conn() as conn:
            conn.execute("DELETE FROM session_locations WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM contacts WHERE session_id = ?", (self.test_session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (self.test_session_id,))
            conn.commit()

    @patch("game_engine.call_llm_json")
    def test_dialogue_partner_retained_on_intra_venue_movement_with_pronouns(self, mock_llm):
        """Issue 1: Dialogue partner (Mia) is retained when moving to a sub-location and narrative uses pronouns."""
        mock_llm.return_value = {
            "title": "A Quieter Spot in the Alcove",
            "outcome_narrative": "Alice asks Mia to step over to the East Alcove.",
            "next_narrative": "\"Let's sit over here,\" she smiled, settling onto the bench away from the noise.",
            "location": "Westlake Academy ➔ Main Gymnasium ➔ East Alcove",
            "npcs_present": [{"name": "Mia Yamada", "role": "Track Athlete"}],
            "next_choices": [
                {"label": "Ask about her training routine", "stat": "CHA", "requirement": 6},
                {"label": "Thank Mia and excuse yourself", "stat": "NONE", "requirement": 0}
            ]
        }

        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Westlake Academy ➔ Main Gymnasium ➔ Main Area",
            "current_npcs": [
                {"name": "Mia Yamada", "role": "Track Athlete"},
                {"name": "Coach Kai Nakamura", "role": "Athletic Coach"}
            ],
            "dialogue_partner": "Mia Yamada",
            "dialogue_partners": ["Mia Yamada"],
            "history": []
        }
        party = [({"id": 1, "user_id": 12345, "name": "Alice", "class": "Journalist", "str_": 5, "agi_": 5, "int_": 10}, [])]
        actions = [{
            "char": {"name": "Alice"},
            "label": "Suggest moving over to the East Alcove with Mia to chat in private",
            "stat": "CHA",
            "check": type("Check", (), {"tier": "success", "chance": 80})(),
            "mp_spent": 0
        }]

        res = asyncio.run(game_engine.resolve_turn(session, party, actions))

        # Mia must be retained as the active dialogue partner!
        self.assertEqual(res.get("dialogue_partner"), "Mia Yamada")
        self.assertEqual(res.get("dialogue_partners"), ["Mia Yamada"])

        # Cleaner should NOT inject a redundant 'Speak with Mia Yamada' choice!
        choices = AdventureCog._clean_choices(
            res.get("next_choices", []),
            dialogue_partner=res.get("dialogue_partner"),
            current_npcs=res.get("npcs_present", [])
        )
        self.assertFalse(any("speak with mia" in c["label"].lower() or "talk to mia" in c["label"].lower() for c in choices))

    def test_bystander_coach_isolated_from_speaking_npcs(self):
        """Issue 2: Ambient coach running drills does not match speaking_npcs or hijack dialogue."""
        narrative = (
            "Across the gym, coach whistles pierced the air and the coach barked orders at the freshmen team.\n"
            "Mia Yamada leaned against the wall and smiled softly at Alice."
        )
        npcs_present = [
            {"name": "Mia Yamada", "role": "Track Athlete"},
            {"name": "Coach Kai Nakamura", "role": "Athletic Coach"}
        ]

        _, _, _, speakers, _ = game_engine.extract_scene_fields({"dialogue_partners": ["Mia Yamada"], "outcome_narrative": narrative, "npcs_present": npcs_present})

        # Coach Kai must NOT be in speaking NPCs (title word 'coach' must not trigger a match for Kai)
        self.assertNotIn("Coach Kai Nakamura", speakers)

    def test_sub_location_transition_leaves_coach_behind(self):
        """Issue 3: When moving from Main Area to East Alcove, Coach Kai stays behind in Main Area."""
        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Westlake Academy ➔ Main Gymnasium ➔ Main Area",
            "current_npcs": [
                {"name": "Mia Yamada", "role": "Track Athlete"},
                {"name": "Coach Kai Nakamura", "role": "Athletic Coach"}
            ],
            "dialogue_partner": "Mia Yamada",
            "dialogue_partners": ["Mia Yamada"],
            "party": [({"name": "Alice"}, [])]
        }
        actions = [{
            "label": "Ask Mia to follow you to the East Alcove",
            "stat": "CHA"
        }]

        raw_result = {
            "outcome_narrative": "Alice and Mia walk over to the East Alcove.",
            "next_narrative": "The East Alcove is secluded and peaceful. Mia takes a seat on the bench.",
            "npcs_present": []
        }

        final_npcs = game_engine.process_scene_npcs(
            raw_result,
            session,
            new_loc="Westlake Academy ➔ Main Gymnasium ➔ East Alcove",
            old_loc="Westlake Academy ➔ Main Gymnasium ➔ Main Area",
            actions=actions
        )

        final_names = [game_engine._get_npc_name(n) for n in final_npcs]

        # Mia Yamada came along
        self.assertIn("Mia Yamada", final_names)
        # Coach Kai Nakamura stayed behind in the Main Area!
        self.assertNotIn("Coach Kai Nakamura", final_names)

    def test_bystander_continuity_bridge_denied_on_sub_location_switch(self):
        """Issue 3: Continuity bridge is False for uninvited bystanders when switching sub-locations."""
        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Westlake Academy ➔ Main Gymnasium ➔ Main Area",
            "current_npcs": [
                {"name": "Mia Yamada", "role": "Track Athlete"},
                {"name": "Coach Kai Nakamura", "role": "Athletic Coach"}
            ],
            "dialogue_partner": "Mia Yamada",
            "dialogue_partners": ["Mia Yamada"],
        }
        actions = [{
            "label": "Head over to the East Alcove with Mia",
            "stat": "NONE"
        }]

        # Coach Kai Nakamura has NO bridge to the East Alcove
        has_bridge = has_narrative_continuity_bridge(
            "Coach Kai Nakamura",
            session=session,
            actions=actions,
            new_loc="Westlake Academy ➔ Main Gymnasium ➔ East Alcove"
        )
        self.assertFalse(has_bridge)

        # Mia Yamada DOES have a bridge because she is an active partner and mentioned with accompanied travel
        mia_bridge = has_narrative_continuity_bridge(
            "Mia Yamada",
            session=session,
            actions=actions,
            new_loc="Westlake Academy ➔ Main Gymnasium ➔ East Alcove"
        )
        self.assertTrue(mia_bridge)

    def test_skill_check_invariants_in_dialogue_mode(self):
        """Issue 4: In dialogue mode, every action requires a skill check (DC 5-8) EXCEPT the dedicated exit."""
        raw_choices = [
            {"label": "Ask Mia about her previous tournament", "stat": "NONE", "requirement": 0},
            {"label": "Playfully tease her about her competitive streak", "stat": "NONE", "requirement": 0},
            {"label": "⭐ [Story Quest] Inquire about the missing gym trophy", "stat": "NONE", "requirement": 0, "is_quest_action": True},
            {"label": "Thank Mia and excuse yourself to step away", "stat": "NONE", "requirement": 0},
        ]

        cleaned = clean_choices_impl(
            None,
            raw_choices,
            scenario="high_school_drama",
            location="Westlake Academy ➔ Main Gymnasium ➔ East Alcove",
            dialogue_partner="Mia Yamada"
        )

        exit_choices = [c for c in cleaned if c["stat"] == "NONE" and c["requirement"] == 0]
        skill_choices = [c for c in cleaned if c["stat"] != "NONE" and c["requirement"] > 0]

        # Exactly 1 free choice (the exit)
        self.assertEqual(len(exit_choices), 1)
        self.assertIn("Thank Mia", exit_choices[0]["label"])

        # All other 3 choices MUST have skill checks!
        self.assertEqual(len(skill_choices), 3)

        # Story quest choice in dialogue has a skill check
        sq_choice = next(c for c in cleaned if "missing gym trophy" in c["label"])
        self.assertNotEqual(sq_choice["stat"], "NONE")
        self.assertGreaterEqual(sq_choice["requirement"], 5)
        self.assertLessEqual(sq_choice["requirement"], 8)
        self.assertTrue(sq_choice.get("is_quest_action"))

    def test_skill_check_invariants_in_free_exploration(self):
        """Issue 4: In free exploration, quest actions require skill checks, while the 9 routine actions are free."""
        raw_choices = [
            {"label": "Speak with Coach Kai Nakamura", "stat": "CHA", "requirement": 6},
            {"label": "Head to the Westlake Library", "stat": "AGI", "requirement": 5},
            {"label": "Look around the gymnasium and observe students", "stat": "PER", "requirement": 6},
            {"label": "Read the athletic tournament notice board", "stat": "INT", "requirement": 6},
            {"label": "Search the sports equipment locker", "stat": "STR", "requirement": 7},
            {"label": "🎯 [Bounty] Interrogate the locker room suspect", "stat": "NONE", "requirement": 0, "is_quest_action": True},
        ]

        cleaned = clean_choices_impl(
            None,
            raw_choices,
            scenario="high_school_drama",
            location="Westlake Academy ➔ Main Gymnasium ➔ Main Area",
            dialogue_partner=None,
            current_npcs=[{"name": "Coach Kai Nakamura"}]
        )

        bounty_choice = next(c for c in cleaned if "interrogate the locker room" in c["label"].lower())
        # Quest choice in exploration MUST have a skill check
        self.assertNotEqual(bounty_choice["stat"], "NONE")
        self.assertGreaterEqual(bounty_choice["requirement"], 5)

        # Routine free actions MUST be normalized to stat=NONE and requirement=0
        speak_choice = next(c for c in cleaned if "speak with coach kai" in c["label"].lower())
        self.assertEqual(speak_choice["stat"], "NONE")
        self.assertEqual(speak_choice["requirement"], 0)

        travel_choice = next(c for c in cleaned if "head to the westlake library" in c["label"].lower())
        self.assertEqual(travel_choice["stat"], "NONE")
        self.assertEqual(travel_choice["requirement"], 0)

        scout_choice = next(c for c in cleaned if "observe students" in c["label"].lower())
        self.assertEqual(scout_choice["stat"], "NONE")
        self.assertEqual(scout_choice["requirement"], 0)

        board_choice = next(c for c in cleaned if "notice board" in c["label"].lower())
        self.assertEqual(board_choice["stat"], "NONE")
        self.assertEqual(board_choice["requirement"], 0)

        prop_choice = next(c for c in cleaned if "equipment locker" in c["label"].lower())
        self.assertEqual(prop_choice["stat"], "NONE")
        self.assertEqual(prop_choice["requirement"], 0)

    @patch("game_engine.call_llm_json")
    def test_legitimate_quest_npc_chimes_in_active_dialogue(self, mock_llm):
        """Relevant quest NPC or interjector chimes into an active conversation with Mia."""
        mock_llm.return_value = {
            "title": "A Sudden Interruption",
            "outcome_narrative": "Alice continues talking with Mia about the team.",
            "next_narrative": "Sofia Anderson rushes over breathlessly. \"Alice, Mia, you need to see this!\" she gasps.",
            "location": "Westlake Academy ➔ Main Gymnasium ➔ Main Area",
            "npcs_present": [
                {"name": "Mia Yamada", "role": "Track Athlete"},
                {"name": "Sofia Anderson", "role": "Student Journalist"}
            ],
            "cast_events": [{"type": "engage", "npc": "Sofia Anderson", "reason": "Urgent news"}],
            "next_choices": [
                {"label": "Ask Sofia what she found", "stat": "CHA", "requirement": 6},
                {"label": "Reassure Mia and keep focused", "stat": "CHA", "requirement": 6},
                {"label": "Excuse yourself from both of them", "stat": "NONE", "requirement": 0}
            ]
        }

        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Westlake Academy ➔ Main Gymnasium ➔ Main Area",
            "current_npcs": [
                {"name": "Mia Yamada", "role": "Track Athlete"},
                {"name": "Sofia Anderson", "role": "Student Journalist"}
            ],
            "dialogue_partner": "Mia Yamada",
            "dialogue_partners": ["Mia Yamada"],
            "history": []
        }
        party = [({"id": 1, "user_id": 12345, "name": "Alice", "class": "Journalist", "str_": 5, "agi_": 5, "int_": 10}, [])]
        actions = [{
            "char": {"name": "Alice"},
            "label": "Ask Mia about her training routine",
            "stat": "CHA",
            "check": type("Check", (), {"tier": "success", "chance": 80})(),
            "mp_spent": 0
        }]

        res = asyncio.run(game_engine.resolve_turn(session, party, actions))

        # Both Mia and Sofia must be in dialogue_partners!
        self.assertIn("Mia Yamada", res.get("dialogue_partners", []))
        self.assertIn("Sofia Anderson", res.get("dialogue_partners", []))

    @patch("game_engine.call_llm_json")
    def test_ambient_bystander_barking_at_third_parties_blocked_from_active_dialogue(self, mock_llm):
        """Ambient coach shouting at freshmen across the gym does NOT chime into Mia's conversation."""
        mock_llm.return_value = {
            "title": "Gym Practice",
            "outcome_narrative": "Alice asks Mia about the track meet.",
            "next_narrative": "Across the gym, Coach Kai Nakamura barked orders at the freshmen team.\nMia nods thoughtfully at Alice.",
            "location": "Westlake Academy ➔ Main Gymnasium ➔ Main Area",
            "npcs_present": [
                {"name": "Mia Yamada", "role": "Track Athlete"},
                {"name": "Coach Kai Nakamura", "role": "Athletic Coach"}
            ],
            "entity_audit": {"speaking_characters": ["Coach Kai Nakamura"]},
            "next_choices": [
                {"label": "Ask Mia more questions", "stat": "CHA", "requirement": 6},
                {"label": "Leave the gym", "stat": "NONE", "requirement": 0}
            ]
        }

        session = {
            "id": self.test_session_id,
            "scenario": "high_school_drama",
            "current_location": "Westlake Academy ➔ Main Gymnasium ➔ Main Area",
            "current_npcs": [
                {"name": "Mia Yamada", "role": "Track Athlete"},
                {"name": "Coach Kai Nakamura", "role": "Athletic Coach"}
            ],
            "dialogue_partner": "Mia Yamada",
            "dialogue_partners": ["Mia Yamada"],
            "history": []
        }
        party = [({"id": 1, "user_id": 12345, "name": "Alice", "class": "Journalist", "str_": 5, "agi_": 5, "int_": 10}, [])]
        actions = [{
            "char": {"name": "Alice"},
            "label": "Ask Mia about the upcoming track meet",
            "stat": "CHA",
            "check": type("Check", (), {"tier": "success", "chance": 80})(),
            "mp_spent": 0
        }]

        res = asyncio.run(game_engine.resolve_turn(session, party, actions))

        # Only Mia is retained; Coach Kai must NOT hijack dialogue!
        self.assertEqual(res.get("dialogue_partners"), ["Mia Yamada"])
        self.assertEqual(res.get("dialogue_partner"), "Mia Yamada")

    def test_can_chime_in_to_dialogue_direct_rules(self):
        """Unit test of can_chime_in_to_dialogue rules."""
        # Rule 1: No prior conversation -> True
        self.assertTrue(game_engine.can_chime_in_to_dialogue("Sofia Anderson", retained_partners=[]))

        # Rule 2: Explicitly named in player action -> True
        actions = [{"label": "Ask Sofia Anderson about the clue"}]
        self.assertTrue(game_engine.can_chime_in_to_dialogue(
            "Sofia Anderson",
            retained_partners=["Mia Yamada"],
            actions=actions
        ))

        # Rule 3: Ambient shout at third parties -> False
        nar_ambient = "Across the gym, Coach Kai Nakamura barked orders at the freshmen team."
        self.assertFalse(game_engine.can_chime_in_to_dialogue(
            "Coach Kai Nakamura",
            retained_partners=["Mia Yamada"],
            narrative=nar_ambient
        ))

        # Rule 4: Direct conversational addressing with player/partner -> True
        nar_chime = "Sofia Anderson steps forward. 'Alice and Mia, wait until you hear this!'"
        self.assertTrue(game_engine.can_chime_in_to_dialogue(
            "Sofia Anderson",
            retained_partners=["Mia Yamada"],
            narrative=nar_chime,
            party=[({"name": "Alice"}, [])]
        ))

        # Rule 5: Active Party Companion -> True
        self.assertTrue(game_engine.can_chime_in_to_dialogue(
            "Leo Thorne",
            retained_partners=["Mia Yamada"],
            session={"party_npcs": [{"name": "Leo Thorne"}]}
        ))

        # Rule 6: Conversational interjection verb (e.g. Amélie in council meeting) -> True
        nar_council = "Amélie Yamashita nods in agreement with Yea-ji. 'Precisely, we must maintain stability.'"
        self.assertTrue(game_engine.can_chime_in_to_dialogue(
            "Amélie Yamashita",
            retained_partners=["Yea-ji Kang"],
            narrative=nar_council
        ))


if __name__ == "__main__":
    unittest.main()
