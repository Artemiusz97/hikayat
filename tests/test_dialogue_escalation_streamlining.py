"""
Tests for Issue #4: Duplicate Dialogue Stall & Escalation Directives Streamlining.
"""
import pytest
from game_engine.npcs import (
    count_dialogue_stall_turns,
    format_dialogue_stall_directive,
    compute_scene_beat_linger_turns,
    format_organic_npc_initiative_directive,
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

    def test_compute_scene_beat_linger_turns(self):
        # Consecutive turns in same location with same partners without location/combat change
        history = [
            {"current_location": "Library", "dialogue_partners": ["Mia"], "action_label": "Ask about notes"},
            {"current_location": "Library", "dialogue_partners": ["Mia"], "action_label": "Read quietly"},
            {"current_location": "Library", "dialogue_partners": ["Mia"], "action_label": "Offer tea"},
        ]
        session = {"current_location": "Library", "dialogue_partners": ["Mia"]}
        linger = compute_scene_beat_linger_turns(history, session=session)
        assert linger == 3

        # Location shift interrupts linger
        history_shifted = [
            {"current_location": "Courtyard", "dialogue_partners": ["Mia"]},
            {"current_location": "Library", "dialogue_partners": ["Mia"]},
            {"current_location": "Library", "dialogue_partners": ["Mia"]},
        ]
        linger_shifted = compute_scene_beat_linger_turns(history_shifted, session=session)
        assert linger_shifted == 2

    def test_format_organic_npc_initiative_directive_stages(self):
        npc = {
            "name": "Justin",
            "micro_blocking": {"active_prop": "a sealed love note"},
            "immediate_agenda": "deliver his love letter discretely",
        }
        # Stage 0: linger < 2 -> empty
        d0 = format_organic_npc_initiative_directive(1, npc, dialogue_type="social")
        assert d0 == ""

        # Stage 1: linger == 2 -> Beat pivot grounded in prop/agenda
        d1 = format_organic_npc_initiative_directive(2, npc, dialogue_type="social")
        assert "Stage 1 — Natural Beat Pivot" in d1
        assert "sealed love note" in d1

        # Stage 2: linger >= 3 -> Physical & Schedule progression
        d2 = format_organic_npc_initiative_directive(3, npc, dialogue_type="social")
        assert "SOCIAL HANGOUT PROGRESSION" in d2
        assert "sealed love note" in d2

    def test_compute_scene_beat_linger_turns_production_schema(self):
        # 1. Opening scene entry is not a dialogue turn
        # 2. Production "label" is read properly
        # 3. Active quest_updates do NOT prematurely reset linger counter, but completed ones DO
        history = [
            {"type": "scene", "current_location": "Library", "narrative": "Beginning"},
            {"current_location": "Library", "label": "Review the study guides", "witnessed_by": ["Mia"], "quest_updates": [{"quest_id": "q1", "status": "Active"}]},
            {"current_location": "Library", "label": "Share a pastry with Mia", "witnessed_by": ["Mia"], "quest_updates": [{"quest_id": "q1", "status": "Active"}]},
        ]
        session = {"current_location": "Library"}
        linger = compute_scene_beat_linger_turns(history, session=session, active_partners=["Mia"])
        assert linger == 2, f"Expected 2 turns with Mia, got {linger}"

        # Completed quest update resets linger
        history_completed = history + [
            {"current_location": "Library", "label": "Submit final report", "witnessed_by": ["Mia"], "quest_updates": [{"quest_id": "q1", "status": "Completed"}]},
            {"current_location": "Library", "label": "Exhale with relief", "witnessed_by": ["Mia"], "quest_updates": []},
        ]
        linger_after_comp = compute_scene_beat_linger_turns(history_completed, session=session, active_partners=["Mia"])
        assert linger_after_comp == 1, f"Expected 1 turn after quest milestone, got {linger_after_comp}"

        # Partner mismatch resets linger
        history_different_partner = history + [
            {"current_location": "Library", "label": "Talk with Justin", "witnessed_by": ["Justin"], "quest_updates": []},
        ]
        linger_diff = compute_scene_beat_linger_turns(history_different_partner, session=session, active_partners=["Mia"])
        assert linger_diff == 0, f"Expected 0 turns for Mia when last turn was with Justin, got {linger_diff}"

    def test_format_organic_npc_initiative_directive_schedule_hint(self):
        npc = {
            "name": "Sarah",
            "role": "Student",
            "club": "swimming",
            "micro_blocking": {"active_prop": "towel"},
        }
        # In afternoon (minute 900), swimming club member's schedule is Indoor Swimming Pool
        directive = format_organic_npc_initiative_directive(
            linger_turns=3,
            npc=npc,
            current_location="School Library ➔ Study Tables",
            current_minute=900,
            scen_key="high_school",
            dialogue_type="social",
        )
        assert "SOCIAL HANGOUT PROGRESSION" in directive
        assert "Swimming Pool" in directive
        assert "invites walking toward" in directive

