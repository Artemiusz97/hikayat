import unittest
import db
from game_engine.keywords import sanitize_npc_pronoun_consistency
from game_engine.context import _describe_tracked_entity, _scene_context_text
from mechanics.social.persona.core import format_persona_summary
from game_engine.prompts import SYSTEM_PROMPT
from llm_client import GM_SHARED_RULES


class TestNPCGenderAndPronounConsistency(unittest.TestCase):
    def test_system_prompt_rules_mandate_pronoun_immutability(self):
        """Verify SYSTEM_PROMPT and GM_SHARED_RULES contain explicit pronoun and gender immutability rules."""
        self.assertIn("MANDATORY GENDER & PRONOUN CANON", SYSTEM_PROMPT)
        self.assertIn("CHARACTER IDENTITY, GENDER & PRONOUN IMMUTABILITY", GM_SHARED_RULES)

    def test_format_persona_summary_includes_gender(self):
        """Verify format_persona_summary includes explicit gender and pronouns."""
        app = {"eye_color": "amethyst", "hair_color": "warm brown"}
        summary_m = format_persona_summary(app, gender="male")
        self.assertIn("Gender: Male (he/him)", summary_m)

        summary_f = format_persona_summary(app, gender="female")
        self.assertIn("Gender: Female (she/her)", summary_f)

    def test_describe_tracked_entity_includes_gender(self):
        """Verify _describe_tracked_entity includes gender and pronouns."""
        e_male = {"name": "Ye-jun Halloway", "gender": "male", "level": 1}
        desc_m = _describe_tracked_entity(e_male)
        self.assertIn("Ye-jun Halloway (Male, he/him, Lvl 1)", desc_m)

        e_female = {"name": "Natalia Vance", "gender": "female", "level": 2}
        desc_f = _describe_tracked_entity(e_female)
        self.assertIn("Natalia Vance (Female, she/her, Lvl 2)", desc_f)

    def test_sanitize_npc_pronoun_consistency_male_npc(self):
        """Verify feminine pronouns for a male NPC are corrected in generated narrative."""
        raw_text = (
            'Inside, Ye-jun Halloway sat behind a large oak desk, a cat-beastfolk with sleek grey fur and sharp amber eyes. '
            'She looked up from a stack of files, her tail flicking in mild irritation at the interruption. '
            '"You\'re early," she said, her voice cool and measured. '
            '"Most people don\'t find this office until they\'re looking for permission slips or detention forms. What do you want?"'
        )
        session = {"id": 1, "current_npcs": [{"name": "Ye-jun Halloway", "gender": "male"}]}
        party = [[{"name": "Artem", "gender": "male"}]]

        cleaned = sanitize_npc_pronoun_consistency(raw_text, session=session, party=party)

        self.assertIn("He looked up from a stack of files", cleaned)
        self.assertIn("his tail flicking in mild irritation", cleaned)
        self.assertIn('"You\'re early," he said', cleaned)
        self.assertIn("his voice cool and measured", cleaned)
        # Verify text inside quotes was preserved
        self.assertIn('"You\'re early,"', cleaned)
        self.assertIn('"Most people don\'t find this office until they\'re looking for permission slips or detention forms. What do you want?"', cleaned)

    def test_sanitize_npc_pronoun_consistency_female_npc(self):
        """Verify masculine pronouns for a female NPC are corrected in generated narrative."""
        raw_text = (
            'Natalia stood beside the podium. He adjusted his glasses, then turned to speak. '
            '"Please take your seats," he said quietly.'
        )
        session = {"id": 1, "current_npcs": [{"name": "Natalia", "gender": "female"}]}
        party = [[{"name": "Hero", "gender": "female"}]]

        cleaned = sanitize_npc_pronoun_consistency(raw_text, session=session, party=party)

        self.assertIn("She adjusted her glasses", cleaned)
        self.assertIn('"Please take your seats," she said quietly', cleaned)

    def test_sanitize_npc_pronoun_preserves_dialogue_interior(self):
        """Verify third-person pronouns inside quoted dialogue are not altered."""
        raw_text = 'Ye-jun sighed. "She told me she would arrive before third period," he said.'
        session = {"id": 1, "current_npcs": [{"name": "Ye-jun", "gender": "male"}]}
        party = [[{"name": "Artem", "gender": "male"}]]

        cleaned = sanitize_npc_pronoun_consistency(raw_text, session=session, party=party)
        self.assertIn('"She told me she would arrive before third period," he said.', cleaned)


if __name__ == "__main__":
    unittest.main()
