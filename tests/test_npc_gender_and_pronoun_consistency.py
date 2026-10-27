import unittest
import re
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

    def test_sanitize_player_pronoun_consistency_male_protagonist(self):
        """Verify misgendered pronouns for a male player character are corrected."""
        raw_text = 'Artem stepped forward to investigate the chest. She reached out her hand cautiously, her heart pounding.'
        actions = [{"char": {"name": "Artem", "gender": "male"}}]
        session = {"id": 1, "lead_character_name": "Artem", "lead_character_gender": "male"}

        cleaned = sanitize_npc_pronoun_consistency(raw_text, session=session, actions=actions)
        self.assertIn("He reached out his hand cautiously", cleaned)
        self.assertIn("his heart pounding", cleaned)

    def test_character_sheet_text_includes_pronoun_mandate_and_biology(self):
        """Verify _character_sheet_text outputs gender mandate, canonical biology, and anatomy."""
        from game_engine.context import _character_sheet_text

        # Male Human
        char_male = {
            "name": "Jack",
            "gender": "Male",
            "race": "human",
            "char_class": "Warrior",
            "level": 1,
            "appearance": {"penis_size": "Formidable", "asset_texture": "Veined & Firm"},
        }
        sheet_m = _character_sheet_text(char_male, [])
        self.assertIn("Gender: Male", sheet_m)
        self.assertIn("Pronouns: he/him/his | MANDATORY: The protagonist is strictly MALE", sheet_m)
        self.assertIn("CANONICAL BIOLOGY: 100% Human (Humanoid)", sheet_m)
        self.assertIn("STRICTLY FORBIDDEN: This character has NO animal ears", sheet_m)
        self.assertIn("Anatomy: Phallus: Formidable (Veined & Firm)", sheet_m)
        self.assertNotIn("Breasts", sheet_m)

        # Female Human
        char_female = {
            "name": "Sarah",
            "gender": "Female",
            "race": "human",
            "char_class": "Mage",
            "level": 1,
            "appearance": {"breast_size": "Voluptuous", "asset_texture": "Pillowy Soft & Yielding"},
        }
        sheet_f = _character_sheet_text(char_female, [])
        self.assertIn("Gender: Female", sheet_f)
        self.assertIn("Pronouns: she/her/hers | MANDATORY: The protagonist is strictly FEMALE", sheet_f)
        self.assertIn("CANONICAL BIOLOGY: 100% Human (Humanoid)", sheet_f)
        self.assertIn("Anatomy: Breasts: Voluptuous (Pillowy Soft & Yielding)", sheet_f)
        self.assertNotIn("Phallus", sheet_f)

    def test_sanitize_player_physical_biology_strips_phantom_animal_traits_on_human(self):
        """Verify phantom animal features on a human player are deterministically cleaned while preserving NPC traits."""
        from game_engine.keywords import sanitize_player_physical_biology

        human_party = [[{"name": "Jack", "race": "human", "gender": "male"}]]
        raw_narrative = (
            "Your fox ears twitch at the sudden clang in the corridor. "
            "Your tail wags happily as you greet the shopkeeper. "
            "A low purr rumbles in your throat while you examine the tome. "
            "Beside you, Kana's fox ears twitch and her tail wags with excitement."
        )

        cleaned = sanitize_player_physical_biology(raw_narrative, party=human_party)

        # Player's phantom traits should be replaced
        self.assertNotIn("Your fox ears twitch", cleaned)
        self.assertNotIn("Your tail wags", cleaned)
        self.assertNotIn("purr rumbles in your throat", cleaned)
        self.assertIn("Your brow furrows at the sudden clang", cleaned)
        self.assertIn("You smile warmly as you greet", cleaned)
        self.assertIn("chuckle rumbles in your throat", cleaned)

        # Beastfolk NPC (Kana) traits MUST be preserved!
        self.assertIn("Kana's fox ears twitch", cleaned)
        self.assertIn("her tail wags with excitement", cleaned)

    def test_sanitize_npc_pronoun_consistency_singular_they_for_honorific_male_npc(self):
        """Verify singular they/them/their for a male NPC with honorific title is corrected to he/him/his."""
        raw_text = (
            "Their paw snaps out to catch your wrist before you can swipe a finger through the silver residue. "
            "Satou sighs, releasing you after a beat. "
            "Their tail flicks in tight irritated arcs behind them as they reach across the table. "
            "A magnifying lens is retrieved from their lab coat pocket."
        )
        session = {"id": 999999, "current_npcs": [{"name": "Dr. Kento Satou", "gender": "male"}]}
        party = [[{"name": "Artem", "gender": "male"}]]

        cleaned = sanitize_npc_pronoun_consistency(raw_text, session=session, party=party)

        self.assertIn("His paw snaps out", cleaned)
        self.assertIn("His tail flicks", cleaned)
        self.assertIn("behind him", cleaned)
        self.assertIn("retrieved from his lab coat pocket", cleaned)

    def test_sanitize_npc_pronoun_consistency_lorebook_contact_recovery(self):
        """Verify NPC pronouns are corrected even when npcs_present is empty, recovering gender from lorebook."""
        import db
        test_sess_id = 88887777
        with db.get_conn() as conn:
            conn.execute("DELETE FROM lorebook WHERE session_id=?", (test_sess_id,))
            conn.execute(
                "INSERT INTO lorebook (session_id, entity_type, name, gender) VALUES (?, 'person', ?, ?)",
                (test_sess_id, "Dr. Kento Satou", "male"),
            )

        raw_text = (
            "Satou sighs, leaning against the lab counter. "
            "Their tail flicks in tight irritated arcs behind them as they reach across the table. "
            "A magnifying lens is retrieved from their lab coat pocket."
        )
        session = {"id": test_sess_id, "current_npcs": []}
        party = [[{"name": "Artem", "gender": "male"}]]

        try:
            cleaned = sanitize_npc_pronoun_consistency(raw_text, session=session, party=party)
            self.assertIn("His tail flicks", cleaned)
            self.assertIn("behind him", cleaned)
            self.assertIn("retrieved from his lab coat pocket", cleaned)
        finally:
            with db.get_conn() as conn:
                conn.execute("DELETE FROM lorebook WHERE session_id=?", (test_sess_id,))

    def test_possessive_preposition_not_mutilated_to_him_phone(self):
        """Verify preposition + possessive 'her phone' converts to 'his phone', never 'him phone'."""
        from game_engine.keywords import _replace_pronouns_to_masculine
        sample = "She glances briefly at her phone and touches her notes."
        out = _replace_pronouns_to_masculine(sample)
        self.assertIn("at his phone", out)
        self.assertNotIn("him phone", out)

    def test_dialogue_quote_vocative_does_not_mutate_female_speaker_to_masculine(self):
        """Verify female NPC speaking to male protagonist in quotes is preserved as female."""
        raw_text = (
            'Ayane Vance offers a soft smile, her topaz eyes crinkling. '
            'She meets your gaze with sincerity, aligning her brass pen.\n\n'
            '"Thank you, Artemiusz. It\'s a bit of a mess today," she says, her voice carrying a diligent cadence. '
            'She glances briefly at her phone, checking for messages from Lucas Nakamura before looking back at you.'
        )
        session = {
            "id": 1,
            "dialogue_partner": "Ayane Vance",
            "current_npcs": [
                {"name": "Ayane Vance", "gender": "female"},
                {"name": "Lucas Nakamura", "gender": "male"},
            ],
        }
        party = [[{"name": "Artemiusz", "gender": "male"}]]

        cleaned = sanitize_npc_pronoun_consistency(raw_text, session=session, party=party)
        self.assertIn('"Thank you, Artemiusz. It\'s a bit of a mess today," she says, her voice', cleaned)
        self.assertIn("She glances briefly at her phone", cleaned)
        self.assertFalse(re.search(r'\bhe says\b', cleaned))
        self.assertNotIn("him phone", cleaned)


    def test_multi_character_scene_does_not_mutate_male_lead_pronouns(self):
        """Verify that in multi-character scenes with female NPCs, male protagonist pronouns are not blindly converted to feminine."""
        raw_text = (
            "Static hums quietly through the receiver, pressing against his ears as he stands alone in his search. "
            "A few yards away, Astrid Larsen shifts her weight, her gaze lingering on him with a mix of curiosity and guardedness, "
            "while Luciana Bjornsson remains leaning against the lockers."
        )
        session = {
            "id": 1,
            "lead_character_name": "Hero",
            "lead_character_gender": "male",
            "current_npcs": [
                {"name": "Astrid Larsen", "gender": "female"},
                {"name": "Luciana Bjornsson", "gender": "female"},
            ],
        }
        party = [[{"name": "Hero", "gender": "male"}]]

        cleaned = sanitize_npc_pronoun_consistency(raw_text, session=session, party=party)
        # Male lead pronouns must NOT be corrupted to "her ears as she stands alone in his search" or "lingering on her"
        self.assertIn("pressing against his ears as he stands alone in his search", cleaned)
        self.assertIn("her gaze lingering on him", cleaned)
        self.assertNotIn("pressing against her ears as she stands alone in his search", cleaned)
        self.assertNotIn("lingering on her with a mix", cleaned)

    def test_tag_narrative_pronouns_left_to_right_discourse_attribution(self):
        """Verify pronoun_resolver tags pronouns in left-to-right order rather than attributing prior pronouns to later characters."""
        from game_engine.pronoun_resolver import tag_narrative_pronouns

        session = {
            "lead_character_name": "Hero",
            "lead_character_gender": "male",
            "current_npcs": [
                {"name": "Astrid Larsen", "gender": "female", "role": "student"},
                {"name": "Luciana Bjornsson", "gender": "female", "role": "student"},
            ],
        }
        party = [[{"name": "Hero", "gender": "male", "char_class": "Hero"}]]
        sentence = (
            "A few yards away, Astrid Larsen shifts her weight, her gaze lingering on him with curiosity, "
            "while Luciana Bjornsson folds her arms quietly."
        )
        tagged = tag_narrative_pronouns(sentence, session=session, party=party)

        # Astrid's pronouns must refer to Astrid Larsen
        self.assertIn('<ref char="Astrid Larsen" role="student">her</ref> weight', tagged)
        self.assertIn('<ref char="Astrid Larsen" role="student">her</ref> gaze', tagged)
        # Him refers to Hero
        self.assertIn('<ref char="Hero"', tagged)
        self.assertIn('>him</ref>', tagged)
        # Luciana's pronoun must refer to Luciana Bjornsson
        self.assertIn('<ref char="Luciana Bjornsson" role="student">her</ref> arms', tagged)


if __name__ == "__main__":
    unittest.main()



