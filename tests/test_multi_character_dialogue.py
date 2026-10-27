from __future__ import annotations
import os
import sys
import unittest
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import game_engine
from game_engine.npcs.cast_planner import plan_pre_turn, apply_cast_events
from cogs.adventure import AdventureCog, _format_tracker_entity, _is_dialogue_partner


class TestMultiCharacterDialogue(unittest.TestCase):

    def test_structured_council_multi_partner_engage_isolates_bystanders(self):
        """Structured cast_events engage promotes Yea-ji Kang and Amélie Yamashita while keeping bystanders isolated."""
        npcs_present = [
            {"name": "Sofia Anderson", "role": "Club President"},
            {"name": "Yea-ji Kang", "role": "Student Council President"},
            {"name": "Amélie Yamashita", "role": "Student Council Vice President"},
            {"name": "Sophia", "role": "Council Secretary"},
            {"name": "Harold Wójcik", "role": "Council Representative"},
        ]
        session = {
            "id": 9201,
            "current_location": "Student Council Office",
            "current_turn_index": 3,
            "current_npcs": npcs_present,
            "dialogue_partner": "Yea-ji Kang",
            "dialogue_partners": ["Yea-ji Kang"],
            "extra_json": {},
        }
        party = [[{"name": "Artemiusz", "user_id": 1}]]
        plan = plan_pre_turn(session, party, [{"label": "Discuss council stability with Yea-ji Kang", "target_npc": "Yea-ji Kang"}])
        final_plan, rejections = apply_cast_events(
            plan,
            [{"type": "engage", "npc": "Amélie Yamashita", "reason": "Nods in agreement and chimes in"}],
            session,
            party,
        )
        self.assertEqual(rejections, [])
        self.assertEqual(final_plan.dialogue_partners, ["Yea-ji Kang", "Amélie Yamashita"])
        self.assertNotIn("Sofia Anderson", final_plan.dialogue_partners)
        self.assertNotIn("Sophia", final_plan.dialogue_partners)
        self.assertNotIn("Harold Wójcik", final_plan.dialogue_partners)

    def test_extract_scene_fields_single_speaker_with_mentioned_npcs_in_quotes(self):
        """Quoted mentions of other NPCs in narrative never promote them into dialogue_partners."""
        outcome = {
            "dialogue_partners": ["Yea-ji Kang"],
            "outcome_narrative": 'Yea-ji Kang says, "We must question Sofia Anderson and check the archives." Sophia stands quietly near the door.',
            "npcs_present": [
                {"name": "Sofia Anderson", "role": "Club President"},
                {"name": "Yea-ji Kang", "role": "Student Council President"},
                {"name": "Sophia", "role": "Council Secretary"},
            ],
        }
        _, _, _, speakers, _ = game_engine.extract_scene_fields(outcome)
        self.assertEqual(speakers, ["Yea-ji Kang"])

    def test_is_dialogue_partner_unicode_and_formats(self):
        """Verify diacritic-insensitive and format-agnostic matching for dialogue partners."""
        partners = ["Yea-ji Kang", "Amélie Yamashita"]

        # Exact match
        self.assertTrue(_is_dialogue_partner("Yea-ji Kang", partners))
        self.assertTrue(_is_dialogue_partner("Amélie Yamashita", partners))

        # Diacritic-normalized match
        self.assertTrue(_is_dialogue_partner("Amelie Yamashita", partners))
        self.assertTrue(game_engine.is_dialogue_partner("Amélie Yamashita", ["Amelie Yamashita"]))

        # Partial token match with title
        self.assertTrue(_is_dialogue_partner("Vice President Amélie Yamashita", partners))
        self.assertTrue(_is_dialogue_partner("President Yea-ji Kang", partners))

        # Non-partners
        self.assertFalse(_is_dialogue_partner("Sofia Anderson", partners))
        self.assertFalse(_is_dialogue_partner("Sophia", partners))

        # JSON string input
        json_partners = json.dumps(partners)
        self.assertTrue(_is_dialogue_partner("Yea-ji Kang", json_partners))
        self.assertTrue(_is_dialogue_partner("Amélie Yamashita", json_partners))

    def test_format_tracker_entity_renders_speech_bubble_for_all_partners(self):
        """Verify that every active dialogue partner gets the 💬 icon prepended in the Character tracker."""
        dialogue_partners = ["Yea-ji Kang", "Amélie Yamashita"]

        yea_ji = {"name": "Yea-ji Kang", "role": "Student Council President"}
        amelie = {"name": "Amélie Yamashita", "role": "Student Council Vice President"}
        sofia = {"name": "Sofia Anderson", "role": "Club President"}

        formatted_yeaji = _format_tracker_entity(yea_ji, dialogue_partners=dialogue_partners)
        formatted_amelie = _format_tracker_entity(amelie, dialogue_partners=dialogue_partners)
        formatted_sofia = _format_tracker_entity(sofia, dialogue_partners=dialogue_partners)

        self.assertIn("💬 **Yea-ji Kang** (Student Council President)", formatted_yeaji)
        self.assertIn("💬 **Amélie Yamashita** (Student Council Vice President)", formatted_amelie)
        self.assertNotIn("💬", formatted_sofia)
        self.assertIn("**Sofia Anderson** (Club President)", formatted_sofia)

    def test_clean_choices_multi_character_exit_choice(self):
        """Verify that _clean_choices generates a natural combined exit choice for 2 or 3+ partners."""
        raw_choices = [
            {"label": "Agree with Yea-ji Kang's emphasis on public perception and student stability", "stat": "CHA", "requirement": 6},
            {"label": "Support Amélie Yamashita's proposal for selective accountability without wider scars", "stat": "INT", "requirement": 6},
            {"label": "Propose a unified council compromise balancing both perspectives", "stat": "CHA", "requirement": 7},
        ]
        current_npcs = [
            {"name": "Yea-ji Kang", "role": "Student Council President"},
            {"name": "Amélie Yamashita", "role": "Student Council Vice President"},
        ]

        # 2 partners
        cleaned_2 = AdventureCog._clean_choices(
            raw_choices,
            scenario="modern",
            location="Westlake Academy ➔ Student Council Office",
            current_npcs=current_npcs,
            dialogue_partner=["Yea-ji Kang", "Amélie Yamashita"],
        )
        labels_2 = [c["label"] for c in cleaned_2]
        self.assertIn("Thank Yea-ji Kang and Amélie Yamashita, excuse yourself, and look around the room", labels_2)

        # 3+ partners
        cleaned_3 = AdventureCog._clean_choices(
            raw_choices,
            scenario="modern",
            location="Westlake Academy ➔ Student Council Office",
            current_npcs=current_npcs,
            dialogue_partner=["Sofia Anderson", "Yea-ji Kang", "Amélie Yamashita"],
        )
        labels_3 = [c["label"] for c in cleaned_3]
        self.assertIn("Thank everyone, excuse yourself, and look around the room", labels_3)

    def test_chime_in_with_five_friendly_npcs_in_scene(self):
        """Verify that with 5 friendly NPCs present in a council meeting, multiple members can chime in."""
        from game_engine.npcs import can_chime_in_to_dialogue

        five_npcs = [
            {"name": "Yea-ji Kang", "role": "Student Council President"},
            {"name": "Amélie Yamashita", "role": "Student Council Vice President"},
            {"name": "Sophia", "role": "Council Secretary"},
            {"name": "Harold Wójcik", "role": "Council Treasurer"},
            {"name": "Denise Richards", "role": "Council Representative"},
        ]

        narrative = (
            "Yea-ji Kang reviews the financial agenda with Artemiusz.\n"
            "Amélie Yamashita interjects, noting the political implications across the factions.\n"
            "Harold Wójcik explains that the reserve fund cannot cover the shortfall.\n"
            "Denise Richards says, \"We have to ensure the student clubs don't suffer the consequences.\"\n"
            "Sophia sits attentively taking notes."
        )

        retained = ["Yea-ji Kang"]
        party = [({"name": "Artemiusz"}, [])]

        self.assertTrue(can_chime_in_to_dialogue("Yea-ji Kang", retained_partners=retained, narrative=narrative, npcs_present=five_npcs, party=party))
        self.assertTrue(can_chime_in_to_dialogue("Amélie Yamashita", retained_partners=retained, narrative=narrative, npcs_present=five_npcs, party=party))
        self.assertTrue(can_chime_in_to_dialogue("Harold Wójcik", retained_partners=retained, narrative=narrative, npcs_present=five_npcs, party=party))
        self.assertTrue(can_chime_in_to_dialogue("Denise Richards", retained_partners=retained, narrative=narrative, npcs_present=five_npcs, party=party))
        self.assertFalse(can_chime_in_to_dialogue("Sophia", retained_partners=retained, narrative=narrative, npcs_present=five_npcs, party=party))

        coach_narrative = narrative + "\nOutside the office, Coach Kai Nakamura barked orders at the freshmen."
        self.assertFalse(can_chime_in_to_dialogue("Coach Kai Nakamura", retained_partners=retained, narrative=coach_narrative, npcs_present=five_npcs + [{"name": "Coach Kai Nakamura"}], party=party))


if __name__ == "__main__":
    unittest.main()
