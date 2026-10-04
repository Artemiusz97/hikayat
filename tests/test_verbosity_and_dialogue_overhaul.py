"""
Tests for the verbosity scaling, style supremacy, and two-way dialogue overhaul.
Verifies:
  - VERBOSITY_INSTRUCTIONS contains paragraph quotas and STRICTLY FORBIDDEN constraints for all 5 modes
  - DIALOGUE_INSTRUCTIONS contains two-way mandate and STRICTLY FORBIDDEN constraints for all key modes
  - OUTCOME_SCHEMA and SCENE_SCHEMA no longer contain hardcoded vivid/immersive paragraph references
  - SYSTEM_PROMPT contains the STYLE & DIALOGUE SUPREMACY clause
  - _style_block() outputs the STRICT SUPREMACY header and footer
  - get_narrative_requirements() returns verbosity-correct content and DIALOGUE RULE for all combinations
"""
import pytest
from game_engine.core import (
    VERBOSITY_INSTRUCTIONS,
    DIALOGUE_INSTRUCTIONS,
    OUTCOME_SCHEMA,
    SCENE_SCHEMA,
    SYSTEM_PROMPT,
)
from game_engine.context import _style_block
from game_engine.turn import get_narrative_requirements


# ---------------------------------------------------------------------------
# 1. VERBOSITY_INSTRUCTIONS
# ---------------------------------------------------------------------------
class TestVerbosityInstructions:
    def test_all_modes_present(self):
        assert "concise" in VERBOSITY_INSTRUCTIONS
        assert "direct" in VERBOSITY_INSTRUCTIONS
        assert "normal" in VERBOSITY_INSTRUCTIONS
        assert "vivid" in VERBOSITY_INSTRUCTIONS
        assert "shakespearean" in VERBOSITY_INSTRUCTIONS

    def test_concise_has_1_paragraph_quota(self):
        text = VERBOSITY_INSTRUCTIONS["concise"]
        assert "1 punchy" in text or "exactly 1" in text.lower()
        assert "STRICTLY FORBIDDEN" in text

    def test_direct_has_correct_quota(self):
        text = VERBOSITY_INSTRUCTIONS["direct"]
        assert "1-2" in text or "2" in text
        assert "STRICTLY FORBIDDEN" in text

    def test_normal_has_contemporary_vocabulary_rule(self):
        text = VERBOSITY_INSTRUCTIONS["normal"]
        assert "contemporary" in text.lower() or "modern" in text.lower()
        assert "STRICTLY FORBIDDEN" in text
        assert "vivid" not in text.lower()

    def test_vivid_forbids_flat_prose(self):
        text = VERBOSITY_INSTRUCTIONS["vivid"]
        assert "STRICTLY FORBIDDEN" in text
        assert "flat" in text.lower() or "dry" in text.lower() or "rushed" in text.lower()

    def test_shakespearean_requires_archaic_and_forbids_modern(self):
        text = VERBOSITY_INSTRUCTIONS["shakespearean"]
        assert "archaic" in text.lower() or "elizabethan" in text.lower()
        assert "STRICTLY FORBIDDEN" in text
        assert "modern slang" in text.lower() or "colloquial" in text.lower()

    def test_no_hardcoded_vivid_in_concise_or_direct(self):
        for mode in ("concise", "direct"):
            text = VERBOSITY_INSTRUCTIONS[mode]
            assert "vivid, atmospheric" not in text.lower()


# ---------------------------------------------------------------------------
# 2. DIALOGUE_INSTRUCTIONS
# ---------------------------------------------------------------------------
class TestDialogueInstructions:
    def test_all_modes_present(self):
        for mode in ("off", "minimal", "balanced", "adaptive", "rich"):
            assert mode in DIALOGUE_INSTRUCTIONS

    def test_balanced_mandates_both_characters_speaking(self):
        text = DIALOGUE_INSTRUCTIONS["balanced"]
        assert "BOTH" in text or "both" in text
        assert "STRICTLY FORBIDDEN" in text
        assert "one-sided" in text.lower() or "only the NPC" in text.lower() or "only" in text.lower()

    def test_adaptive_mandates_two_way_in_social_context(self):
        text = DIALOGUE_INSTRUCTIONS["adaptive"]
        assert "BOTH" in text or "both" in text
        assert "STRICTLY FORBIDDEN" in text
        assert "social" in text.lower() or "investigation" in text.lower()

    def test_rich_mandates_minimum_exchanges(self):
        text = DIALOGUE_INSTRUCTIONS["rich"]
        assert "3-5" in text or "3" in text
        assert "STRICTLY FORBIDDEN" in text

    def test_minimal_forbids_extended_exchanges(self):
        text = DIALOGUE_INSTRUCTIONS["minimal"]
        assert "STRICTLY FORBIDDEN" in text
        assert "extended" in text.lower() or "multi-line" in text.lower()

    def test_off_forbids_all_spoken_dialogue(self):
        text = DIALOGUE_INSTRUCTIONS["off"]
        assert "STRICTLY FORBIDDEN" in text
        assert "quotation marks" in text.lower() or "spoken dialogue" in text.lower()


# ---------------------------------------------------------------------------
# 3. OUTCOME_SCHEMA and SCENE_SCHEMA
# ---------------------------------------------------------------------------
class TestSchemaHardcodedTextRemoval:
    def test_outcome_schema_no_hardcoded_vivid_paragraphs(self):
        assert "1-2 vivid, action-focused paragraphs" not in OUTCOME_SCHEMA
        assert "2-3 detailed, immersive paragraphs" not in OUTCOME_SCHEMA

    def test_outcome_schema_references_style_directive(self):
        assert "STYLE DIRECTIVE" in OUTCOME_SCHEMA or "ACTIVE STYLE" in OUTCOME_SCHEMA

    def test_scene_schema_no_hardcoded_vivid_paragraphs(self):
        assert "2-3 vivid paragraphs" not in SCENE_SCHEMA

    def test_scene_schema_references_style_directive(self):
        assert "STYLE DIRECTIVE" in SCENE_SCHEMA or "ACTIVE STYLE" in SCENE_SCHEMA


# ---------------------------------------------------------------------------
# 4. SYSTEM_PROMPT supremacy clause
# ---------------------------------------------------------------------------
class TestSystemPromptSupremacy:
    def test_supremacy_clause_present(self):
        import llm_client
        assert "STYLE & DIALOGUE SUPREMACY" in llm_client.GM_SHARED_RULES or "STYLE \u0026 DIALOGUE SUPREMACY" in llm_client.GM_SHARED_RULES

    def test_supremacy_clause_mentions_overrides(self):
        import llm_client
        assert "OVERRIDES" in llm_client.GM_SHARED_RULES or "overrides" in llm_client.GM_SHARED_RULES

    def test_narrative_balance_defers_to_style(self):
        import llm_client
        assert "active STYLE directive" in llm_client.GM_SHARED_RULES or "STYLE directive" in llm_client.GM_SHARED_RULES

    def test_no_longer_hardcodes_vivid_immersive_paragraphs(self):
        import llm_client
        assert "1-2 vivid, action-focused paragraphs narrating action" not in llm_client.GM_SHARED_RULES
        assert "2-3 immersive, detailed paragraphs establishing scene" not in llm_client.GM_SHARED_RULES

    def test_narrative_immersion_not_unconditional(self):
        assert "Write vivid, atmospheric prose rich with sensory details (lighting, sounds, scents, ambient mood)." not in SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# 5. _style_block() header/footer framing
# ---------------------------------------------------------------------------
class TestStyleBlockFormatting:
    def _make_session(self, verbosity="vivid", dialogue_mode="balanced", choices_style="dropdown"):
        return {"verbosity": verbosity, "dialogue_mode": dialogue_mode, "choices_style": choices_style}

    def test_supremacy_header_present(self):
        block = _style_block(self._make_session())
        assert "STRICT SUPREMACY" in block or "OVERRIDES ALL OTHER INSTRUCTIONS" in block

    def test_supremacy_footer_present(self):
        block = _style_block(self._make_session())
        assert "END STYLE" in block or "MUST COMPLY" in block

    def test_style_label_present(self):
        block = _style_block(self._make_session())
        assert "STYLE:" in block

    def test_dialogue_label_present(self):
        block = _style_block(self._make_session())
        assert "DIALOGUE:" in block

    def test_concise_verbosity_reflected(self):
        block = _style_block(self._make_session(verbosity="concise"))
        assert "STRICTLY FORBIDDEN" in block

    def test_balanced_dialogue_reflected(self):
        block = _style_block(self._make_session(dialogue_mode="balanced"))
        assert "BOTH" in block or "both" in block

    def test_unknown_verbosity_falls_back_to_vivid(self):
        block = _style_block(self._make_session(verbosity="nonexistent"))
        vivid_text = VERBOSITY_INSTRUCTIONS["vivid"][:30]
        assert vivid_text in block

    def test_unknown_dialogue_mode_falls_back_to_balanced(self):
        block = _style_block(self._make_session(dialogue_mode="nonexistent"))
        balanced_text = DIALOGUE_INSTRUCTIONS["balanced"][:30]
        assert balanced_text in block


# ---------------------------------------------------------------------------
# 6. get_narrative_requirements()
# ---------------------------------------------------------------------------
class TestGetNarrativeRequirements:
    def test_concise_outcome_1_paragraph(self):
        text = get_narrative_requirements("concise", "balanced")
        assert "Exactly 1" in text or "1 punchy" in text.lower()

    def test_concise_next_1_paragraph(self):
        text = get_narrative_requirements("concise", "balanced")
        assert "Exactly 1 compact" in text or "1 compact" in text.lower()

    def test_direct_outcome_1_2_paragraphs(self):
        text = get_narrative_requirements("direct", "balanced")
        assert "1-2 tight" in text.lower() or "1-2" in text

    def test_direct_next_exactly_2_paragraphs(self):
        text = get_narrative_requirements("direct", "off")
        assert "Exactly 2" in text or "exactly 2" in text.lower()

    def test_normal_outcome_1_2_paragraphs(self):
        text = get_narrative_requirements("normal", "balanced")
        assert "1-2" in text

    def test_vivid_outcome_rich_paragraphs(self):
        text = get_narrative_requirements("vivid", "rich")
        assert "1-2 rich" in text.lower() or "rich" in text.lower()

    def test_shakespearean_output_contains_elizabethan(self):
        text = get_narrative_requirements("shakespearean", "off")
        assert "elizabethan" in text.lower() or "Elizabethan" in text

    def test_dialogue_rule_off_forbids_quotes(self):
        text = get_narrative_requirements("vivid", "off")
        assert "DIALOGUE RULE" in text
        assert "quotation marks" in text.lower() or "spoken dialogue" in text.lower()

    def test_dialogue_rule_balanced_mandates_both(self):
        text = get_narrative_requirements("vivid", "balanced")
        assert "DIALOGUE RULE" in text
        assert "BOTH" in text or "both" in text

    def test_dialogue_rule_rich_mandates_exchanges(self):
        text = get_narrative_requirements("normal", "rich")
        assert "DIALOGUE RULE" in text
        assert "3-5" in text or "exchanges" in text.lower()

    def test_strictly_forbidden_in_all_verbosity_modes(self):
        for mode in ("concise", "direct", "normal", "vivid", "shakespearean"):
            text = get_narrative_requirements(mode, "balanced")
            assert "STRICTLY FORBIDDEN" in text, f"STRICTLY FORBIDDEN missing for verbosity={mode}"

    def test_unknown_verbosity_falls_back_to_vivid(self):
        text = get_narrative_requirements("nonexistent", "balanced")
        assert "rich" in text.lower() or "atmospheric" in text.lower()

    def test_unknown_dialogue_falls_back_to_balanced(self):
        text = get_narrative_requirements("vivid", "nonexistent")
        assert "BOTH" in text or "both" in text
