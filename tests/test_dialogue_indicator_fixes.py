from __future__ import annotations
import unittest
import character_data as cd
import game_engine
from game_engine.npcs.cast_planner import plan_pre_turn, apply_cast_events


class TestDialogueIndicatorAndPresenceFixes(unittest.TestCase):
    def test_prose_vocal_verbs_never_hijack_dialogue_without_cast_event(self):
        """Prose vocal verbs ('rumbles', single quotes) never promote bystanders without structured cast_events."""
        session = {
            "id": 9101,
            "current_location": "Cabin",
            "current_turn_index": 3,
            "current_npcs": [{"name": "Diana Yamada"}, {"name": "Henry Sterling"}],
            "dialogue_partner": None,
            "dialogue_partners": [],
            "extra_json": {},
        }
        party = [[{"name": "Artem", "user_id": 1}]]
        plan = plan_pre_turn(session, party, [{"label": "Check tactical console", "intent": "area_scout"}])

        # Without cast_events, prose speech alone never promotes Diana
        final_plan_no_ev, _ = apply_cast_events(plan, [], session, party)
        self.assertEqual(final_plan_no_ev.dialogue_partners, [])

        # Structured engage event promotes Diana cleanly
        final_plan_ev, rejections = apply_cast_events(
            plan, [{"type": "engage", "npc": "Diana Yamada", "reason": "Addresses Artem"}], session, party
        )
        self.assertEqual(rejections, [])
        self.assertIn("Diana Yamada", final_plan_ev.dialogue_partners)
        self.assertNotIn("Henry Sterling", final_plan_ev.dialogue_partners)

    def test_attendance_tags_filtered_from_status_effects(self):
        """Verify Present, Absent, Nearby are stripped from RPG condition status effects."""
        raw = ["Present", "Bleeding", "Absent", "Stunned", "nearby", ""]
        sanitized = cd.sanitize_status_effects(raw)
        self.assertEqual(sanitized, ["Bleeding", "Stunned"])

    def test_extract_scene_fields_strictly_uses_structured_dialogue_partners(self):
        """Verify extract_scene_fields strictly uses structured dialogue_partners and never scrapes prose."""
        outcome = {
            "dialogue_partners": [],
            "outcome_narrative": "Henry Sterling simply steps into your line. 'Whoa—whoa—whoa,' he says.",
            "next_narrative": "The hallway falls quiet.",
            "npcs_present": [{"name": "Henry Sterling"}],
            "choices": ["Listen to Henry", "Push past him"],
        }
        _, _, _, det_partner, _ = game_engine.extract_scene_fields(outcome)
        self.assertEqual(det_partner, [])

        outcome_active = dict(outcome, dialogue_partners=["Henry Sterling"])
        _, _, _, active_partner, _ = game_engine.extract_scene_fields(outcome_active)
        self.assertEqual(active_partner, ["Henry Sterling"])

    def test_possessive_apostrophe_never_triggers_false_speaker_match(self):
        """Verify possessive apostrophes (e.g. lobby's) and lowercase adjectives ('long') never attribute speech to 'Long Hall'."""
        outcome = {
            "dialogue_partners": [],
            "outcome_narrative": (
                "The violet stabilization field casts long, flickering shadows against the lobby's reception rotunda. "
                "Artemiusz stands alone in the center of the atrium."
            ),
            "next_narrative": "Silence hums across the rotunda.",
            "npcs_present": [{"name": "Long Hall"}],
            "choices": ["Inspect rotunda"],
        }
        _, _, _, partner_arg, _ = game_engine.extract_scene_fields(outcome)
        self.assertEqual(partner_arg, [])


if __name__ == "__main__":
    unittest.main()
