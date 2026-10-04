import os
import sys
import unittest
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
import game_engine
from cogs.adventure import AdventureCog, _format_tracker_entity, _is_dialogue_partner


class TestMultiCharacterDialogue(unittest.TestCase):

    def test_extract_speaking_npcs_exact_council_scene(self):
        """Verify that extract_speaking_npcs_from_narrative accurately identifies both Yea-ji Kang and Amélie Yamashita."""
        narrative = (
            "The Council's Consensus\n"
            "Yea-ji Kang speaks first, her voice carrying the weight of absolute authority. "
            "\"The evidence is clear, and Sofia's approach is logically sound,\" she states, her eyes narrowing slightly. "
            "\"However, the stability of the student body depends not just on who is punished, but on how that punishment is perceived by the other factions. "
            "We cannot allow this to be seen as a targeted purge or a sign of weakness.\"\n\n"
            "Amélie Yamashita nods in agreement, her expression more nuanced. "
            "\"Precisely. The 'selective accountability' Sofia proposed is a scalpel, but we need to ensure the incision doesn't leave a scar that triggers a wider conflict between the Velvet Rose Pact and the other groups. "
            "We are looking for a resolution that preserves order without fueling further resentment.\"\n\n"
            "They both turn their attention back to Artemiusz, waiting to see if he has an insight that transcends simple evidence—a strategic angle that could ensure the long-term equilibrium of Westlake Academy. "
            "The silence in the office is heavy, punctuated only by the distant hum of students in the hallways."
        )

        npcs_present = [
            {"name": "Sofia Anderson", "role": "Club President"},
            {"name": "Yea-ji Kang", "role": "Student Council President"},
            {"name": "Amélie Yamashita", "role": "Student Council Vice President"},
            {"name": "Sophia", "role": "Council Secretary"},
            {"name": "Harold Wójcik", "role": "Council Representative"}
        ]

        speakers = game_engine.extract_speaking_npcs_from_narrative(narrative, npcs_present)
        self.assertEqual(speakers, ["Yea-ji Kang", "Amélie Yamashita"])
        self.assertNotIn("Sofia Anderson", speakers, "Sofia was only referenced inside quotes, not speaking")
        self.assertNotIn("Sophia", speakers)
        self.assertNotIn("Harold Wójcik", speakers)

    def test_extract_speaking_npcs_single_speaker_with_mentioned_npcs(self):
        """Verify that when only one NPC speaks and mentions another NPC in quotes, only the speaker is returned."""
        narrative = 'Yea-ji Kang says, "We must question Sofia Anderson and check the archives." Sophia stands quietly near the door.'
        npcs_present = [
            {"name": "Sofia Anderson", "role": "Club President"},
            {"name": "Yea-ji Kang", "role": "Student Council President"},
            {"name": "Sophia", "role": "Council Secretary"}
        ]
        speakers = game_engine.extract_speaking_npcs_from_narrative(narrative, npcs_present)
        self.assertEqual(speakers, ["Yea-ji Kang"])

    def test_extract_speaking_npcs_group_discussion(self):
        """Verify that multiple NPCs participating in indirect discussion are all detected."""
        narrative = "Sofia Anderson, Yea-ji Kang, and Amélie Yamashita all agree to coordinate their efforts on the student council."
        npcs_present = [
            {"name": "Sofia Anderson", "role": "Club President"},
            {"name": "Yea-ji Kang", "role": "Student Council President"},
            {"name": "Amélie Yamashita", "role": "Student Council Vice President"},
            {"name": "Harold Wójcik", "role": "Council Representative"}
        ]
        speakers = game_engine.extract_speaking_npcs_from_narrative(narrative, npcs_present)
        self.assertEqual(set(speakers), {"Sofia Anderson", "Yea-ji Kang", "Amélie Yamashita"})
        self.assertNotIn("Harold Wójcik", speakers)

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
            {"label": "Propose a unified council compromise balancing both perspectives", "stat": "CHA", "requirement": 7}
        ]
        current_npcs = [
            {"name": "Yea-ji Kang", "role": "Student Council President"},
            {"name": "Amélie Yamashita", "role": "Student Council Vice President"}
        ]
        
        # 2 partners
        cleaned_2 = AdventureCog._clean_choices(
            raw_choices,
            scenario="modern",
            location="Westlake Academy ➔ Student Council Office",
            current_npcs=current_npcs,
            dialogue_partner=["Yea-ji Kang", "Amélie Yamashita"]
        )
        labels_2 = [c["label"] for c in cleaned_2]
        self.assertIn("Thank Yea-ji Kang and Amélie Yamashita, excuse yourself, and look around the room", labels_2)
        
        # 3+ partners
        cleaned_3 = AdventureCog._clean_choices(
            raw_choices,
            scenario="modern",
            location="Westlake Academy ➔ Student Council Office",
            current_npcs=current_npcs,
            dialogue_partner=["Sofia Anderson", "Yea-ji Kang", "Amélie Yamashita"]
        )
        labels_3 = [c["label"] for c in cleaned_3]
        self.assertIn("Thank everyone, excuse yourself, and look around the room", labels_3)


if __name__ == "__main__":
    unittest.main()
