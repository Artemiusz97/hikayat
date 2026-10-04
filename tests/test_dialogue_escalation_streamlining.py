"""
Tests for Issue #4: Duplicate Dialogue Stall & Escalation Directives Streamlining.
"""
import pytest
from game_engine.npcs import (
    count_dialogue_stall_turns,
    format_dialogue_stall_directive,
    build_scene_escalation_and_consequence_directives
)

class TestDialogueEscalationStreamlining:

    def test_count_dialogue_stall_turns(self):
        history = [
            {"action_label": "Propose a new strategy"},
            {"action_label": "Move to the door"},
            {"action_label": "Analyze the clues"},
            {"action_label": "Attack the guard"},
            {"action_label": "Suggest we retreat"},
            {"action_label": "Summarize the evidence"},
            {"action_label": "Walk through the timeline"},
        ]
        # Should catch: Propose, Analyze, Suggest, Summarize, Walk through -> 5
        count = count_dialogue_stall_turns(history)
        assert count == 5, f"Expected 5 stall verbs, got {count}"

    def test_format_bounty_stall_directive(self):
        # 1-turn stall
        note1 = format_dialogue_stall_directive(1, "bounty", "Justin", "Secret Note")
        assert note1 == ""
        
        # 2-turn stall
        note2 = format_dialogue_stall_directive(2, "bounty", "Justin", "Secret Note")
        assert "BOUNTY DEPTH" in note2
        assert "Secret Note" in note2
        
        # 3-turn stall
        note3 = format_dialogue_stall_directive(3, "bounty", "Justin", "Secret Note")
        assert "BOUNTY STALL WARNING" in note3
        assert "urge the player to accept and act" in note3

    def test_format_quest_stall_directive(self):
        # 2-turn stall
        note2 = format_dialogue_stall_directive(2, "quest", "Elara")
        assert "DEPTH WARNING" in note2
        assert "CONCRETE COMMITMENT" in note2
        
        # 3-turn stall
        note3 = format_dialogue_stall_directive(3, "quest", "Elara")
        assert "QUEST INVESTIGATION LOOP DETECTED" in note3
        assert "MUST reach a concrete turning point" in note3
        assert "BANNED THIS TURN" in note3

    def test_format_social_stall_directive(self):
        # 2-turn stall
        note2 = format_dialogue_stall_directive(2, "social", "Mitsuki")
        assert "SOCIAL HANGOUT MOMENTUM" in note2
        assert "authentic reactions" in note2
        
        # 3-turn stall
        note3 = format_dialogue_stall_directive(3, "social", "Mitsuki")
        assert "SOCIAL HANGOUT PROGRESSION" in note3
        assert "STRICTLY FORBIDDEN: Do NOT turn this into a challenge" in note3

    def test_build_scene_escalation_dialogue_gate(self):
        # Test that in_dialogue_mode=True suppresses the stall logic in directive_note
        session = {
            "history": [
                {"action_label": "Propose plan"} for _ in range(4)
            ],
            "dialogue_partners": ["Justin"]
        }
        party = []
        actions = []
        
        # Without in_dialogue_mode, we expect a social hangout directive to appear (or quest)
        # Because we mocked dialogue_partners and stall_count=4
        directives_default = build_scene_escalation_and_consequence_directives(session, party, actions)
        assert "SOCIAL DIALOGUE MOMENTUM" in directives_default or "SOCIAL HANGOUT" in directives_default or "QUEST" in directives_default
        
        # With in_dialogue_mode=True, it should be entirely suppressed
        directives_gated = build_scene_escalation_and_consequence_directives(session, party, actions, in_dialogue_mode=True)
        assert directives_gated == "", "Expected empty directives when in_dialogue_mode=True suppresses stall injection"
