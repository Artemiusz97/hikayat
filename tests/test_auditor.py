import unittest
import pytest
from game_engine.auditor import AuditorEngine, _extract_state_facts, _state_preserved
from models.llm_schemas import TurnOutcome, CharacterOutcome

class TestAuditorEngine(unittest.TestCase):
    def test_extract_state_facts(self):
        outcome = {
            "character_outcomes": [
                {
                    "name": "Kaelen",
                    "items_gained": ["Obsidian Blade", "Health Potion"],
                    "items_lost": ["Broken Dagger"],
                    "hp_change": -15,
                    "gold_change": 50
                }
            ],
            "quest_updates": [
                {"title": "The Whispering Cavern"}
            ],
            "deceased_characters": ["Cave Troll"]
        }
        facts = _extract_state_facts(outcome)
        self.assertIn("obsidian blade", facts)
        self.assertIn("health potion", facts)
        self.assertIn("broken dagger", facts)
        self.assertIn("15", facts)
        self.assertIn("50", facts)
        self.assertIn("the whispering cavern", facts)
        self.assertIn("cave troll", facts)

    def test_state_preserved_veto_dropped_item(self):
        outcome = {
            "character_outcomes": [
                {
                    "name": "Kaelen",
                    "items_gained": ["Obsidian Blade"],
                    "hp_change": 0,
                    "gold_change": 0
                }
            ]
        }
        orig = "You reach into the rubble and retrieve the Obsidian Blade, feeling its dark hum."
        # Rewritten prose drops the item completely
        rewritten = "You reach into the rubble, your breath catching in your throat as dust settles."
        
        # Must VETO (returns False)
        self.assertFalse(_state_preserved(orig, rewritten, outcome))

    def test_state_preserved_keeps_fact(self):
        outcome = {
            "character_outcomes": [
                {
                    "name": "Kaelen",
                    "items_gained": ["Obsidian Blade"],
                    "hp_change": 0,
                    "gold_change": 0
                }
            ]
        }
        orig = "You reach into the rubble and retrieve the Obsidian Blade, feeling its dark hum as if someone watched."
        # Rewritten removes gesture gloss but keeps the blade
        rewritten = "You reach into the rubble and retrieve the Obsidian Blade."
        
        # Must ALLOW (returns True)
        self.assertTrue(_state_preserved(orig, rewritten, outcome))

    def test_state_preserved_allows_item_not_in_orig(self):
        outcome = {
            "character_outcomes": [
                {
                    "name": "Kaelen",
                    "items_gained": ["Obsidian Blade"],
                    "hp_change": 0,
                    "gold_change": 0
                }
            ]
        }
        # Original text didn't mention the item by exact name
        orig = "You search the chamber thoroughly and find a weapon wrapped in cloth."
        rewritten = "You search the chamber thoroughly, finding a concealed weapon."
        
        # Item was never in orig, so it shouldn't trigger veto
        self.assertTrue(_state_preserved(orig, rewritten, outcome))


    def test_state_preserved_word_boundary_no_false_positive(self):
        outcome = {
            "character_outcomes": [
                {
                    "name": "Kaelen",
                    "items_gained": ["Cat"],
                    "hp_change": 5,
                    "gold_change": 0
                }
            ]
        }
        # Original text has "location" (contains "cat" as substring) and "50" (contains "5" as substring)
        # but neither the standalone item "Cat" nor standalone number "5"
        orig = "You arrive at the location and spot 50 gold pieces on the pedestal."
        rewritten = "You arrive at the destination and spot 50 gold pieces on the pedestal."
        
        # Should NOT veto because "cat" and "5" were only substrings, not standalone words
        self.assertTrue(_state_preserved(orig, rewritten, outcome))

    def test_state_preserved_veto_dropped_enemy(self):
        outcome = {
            "nearby_enemies": [{"name": "Shadow Drake"}]
        }
        orig = "The darkness shifts, and a Shadow Drake roars in fury!"
        rewritten = "The darkness shifts quietly around you."
        
        # Dropped newly emerged enemy mentioned in draft -> VETO
        self.assertFalse(_state_preserved(orig, rewritten, outcome))


@pytest.mark.asyncio
async def test_auditor_empty_prose_bypasses():
    draft = TurnOutcome(outcome_narrative="", next_narrative="")
    new_out, new_next, report = await AuditorEngine.audit_turn([], "prompt", draft)
    assert report["verdict"] == "clean"
    assert new_out == ""
    assert new_next == ""


@pytest.mark.asyncio
async def test_auditor_paragraph_split_multi_paragraph(monkeypatch):
    # Mock game_engine.call_llm_json to return a corrected rewrite
    import game_engine
    
    mock_response = {
        "verdict": "corrected",
        "corrections": [{"rule_violated": "gesture_gloss", "reasoning": "cut gloss"}],
        "final_prose": "Outcome Para 1 cleaned.\n\nOutcome Para 2 cleaned.\n\nNext Para 1 cleaned.\n\nNext Para 2 cleaned.",
        "reasoning_summary": "surgical fix"
    }
    
    async def mock_call(*args, **kwargs):
        return mock_response
        
    monkeypatch.setattr(game_engine, "call_llm_json", mock_call)
    
    draft = TurnOutcome(
        outcome_narrative="Outcome Para 1.\n\nOutcome Para 2.",
        next_narrative="Next Para 1.\n\nNext Para 2."
    )
    
    new_out, new_next, report = await AuditorEngine.audit_turn([], "prompt", draft)
    assert report["verdict"] == "corrected"
    assert report["prose_rewritten"] is True
    # Verify paragraph counts: 2 outcome paragraphs, 2 next paragraphs
    assert new_out == "Outcome Para 1 cleaned.\n\nOutcome Para 2 cleaned."
    assert new_next == "Next Para 1 cleaned.\n\nNext Para 2 cleaned."


@pytest.mark.asyncio
async def test_auditor_llm_failure_fails_open(monkeypatch):
    import game_engine
    
    async def mock_call_error(*args, **kwargs):
        raise TimeoutError("Provider timed out")
        
    monkeypatch.setattr(game_engine, "call_llm_json", mock_call_error)
    
    draft = TurnOutcome(
        outcome_narrative="Initial outcome narrative.",
        next_narrative="Initial next narrative."
    )
    
    new_out, new_next, report = await AuditorEngine.audit_turn([], "prompt", draft)
    # Fails open: returns original draft and clean verdict
    assert report["verdict"] == "clean"
    assert report["error"] == "llm_call_failed"
    assert new_out == "Initial outcome narrative."
    assert new_next == "Initial next narrative."


@pytest.mark.asyncio
async def test_auditor_forwards_is_nsfw_and_timeout(monkeypatch):
    import game_engine
    captured_kwargs = {}
    
    async def mock_call(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return {
            "verdict": "clean",
            "corrections": [],
            "final_prose": "",
            "reasoning_summary": "clean"
        }
        
    monkeypatch.setattr(game_engine, "call_llm_json", mock_call)
    
    draft = TurnOutcome(outcome_narrative="Some draft.", next_narrative="Some next.")
    await AuditorEngine.audit_turn([], "prompt", draft, is_nsfw=True)
    
    assert captured_kwargs.get("is_nsfw") is True
    assert captured_kwargs.get("timeout") == 25.0


@pytest.mark.asyncio
async def test_auditor_rewrites_comparative_flattery_synergy(monkeypatch):
    import game_engine
    
    # Draft with a canned comparative flattery trope
    draft = TurnOutcome(
        outcome_narrative="Sofia leans against the rooftop railing, her eyes scanning you with a spark of genuine curiosity.",
        next_narrative="\"You've got some nerve, you know that? Most guys would be too nervous to even look me in the eye.\" She smirks."
    )
    
    # The Auditor semantically rewrites the dialogue into an organic reaction rather than crude deletion
    mock_auditor_output = {
        "pre_emit_audit": {
            "default_clean": "clean_unless_one_concrete_checkable_violation_never_taste",
            "agency_ceiling": "the_ceiling_is_player_input_plus_established_active_state_police_only_inventions",
            "form_tics": "act_only_on_a_mechanical_or_repeated_effect_seeking_device",
            "comparative_contrast": "rephrase_canned_contrast_into_direct_character_reaction",
            "minimal_change_and_markers": "smallest_edit_that_removes_the_violation_voice_and_length_kept_state_preserved",
            "rewrite_plants_no_vice": "the_prose_i_return_seeds_none_of_the_vices_i_police"
        },
        "verdict": "corrected",
        "corrections": [
            {
                "rule_violated": "comparative_contrast",
                "reasoning": "Rephrased 'most guys would be too nervous' to direct character reaction."
            }
        ],
        "final_prose": "Sofia leans against the rooftop railing, her eyes scanning you with a spark of genuine curiosity.\n\n\"You've got some nerve, you know that? Standing there looking right at me.\" She smirks.",
        "reasoning_summary": "Replaced canned comparative flattery with direct reaction."
    }
    
    async def mock_call(*args, **kwargs):
        return mock_auditor_output
        
    monkeypatch.setattr(game_engine, "call_llm_json", mock_call)
    
    new_out, new_next, report = await AuditorEngine.audit_turn([], "prompt", draft)
    
    assert report["verdict"] == "corrected"
    assert report["prose_rewritten"] is True
    # The canned trope was cleanly rephrased
    assert "Most guys would be too nervous" not in new_next
    assert "Standing there looking right at me" in new_next
    # The regex filter also passes through cleanly without further mutation
    assert game_engine.sanitize_comparative_cliches(new_next) == new_next



