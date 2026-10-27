import pytest
import db
import game_engine
from game_engine.turn.dialogue import _compute_dialogue_intent


def test_leave_conversation_stops_all_scene_npcs():
    """When the player chooses to leave a conversation, every NPC present must stop talking with the player."""
    user_id = 991122
    sess_id = db.create_session(
        user_id,
        "solo",
        1,
        "normal",
        "direct",
        False,
        scenario="high_school_drama",
    )
    
    # Setup session in active dialogue with multiple NPCs present in the room
    session = db.get_session(sess_id)
    session["current_location"] = "Student Council Room"
    session["dialogue_partner"] = "Amélie Vance"
    session["dialogue_partners"] = ["Amélie Vance", "Leonardo Halloway"]
    session["current_npcs"] = [
        {"name": "Amélie Vance", "role": "President"},
        {"name": "Leonardo Halloway", "role": "Vice President"},
        {"name": "Martyna Kowalska", "role": "Secretary"},
    ]
    db.update_session(
        sess_id,
        dialogue_partner="Amélie Vance",
        current_npcs=session["current_npcs"],
    )

    # Player chooses to leave conversation
    exit_action = {
        "label": "Excuse yourself and leave the conversation",
        "stat": "NONE",
        "requirement": 0,
        "intent": "dialogue_exit",
    }
    actions = [exit_action]

    new_partners, has_exited = _compute_dialogue_intent(session, actions)

    assert has_exited is True, "has_exited_convo must be True when choosing to leave conversation"
    assert new_partners == [], "new_partners must be empty when leaving conversation"


def test_extract_scene_fields_does_not_resurrect_partner_on_convo_exit():
    """When has_exited_convo is True, extract_scene_fields must NEVER resurrect the NPC from farewell dialogue in outcome_narrative."""
    outcome = {
        "dialogue_partners": [],
        "dialogue_partner": None,
        "has_exited_convo": True,
        "npcs_present": [{"name": "Minato Saito", "role": "Drama Club Lead"}],
        "outcome_narrative": "Minato Saito chuckles, tucking his notebook securely under his arm. 'I'll hold you to that! Catch you later!' He gives a quick, energetic wave before pivoting on his heel.",
        "next_narrative": "With the conversation concluded, Artemiusz stands alone for a moment amidst the shifting tide of the morning rush.",
        "choices": ["Check bulletin board"]
    }

    choices, next_nar, title, partner_arg, npcs_arg = game_engine.extract_scene_fields(outcome)
    assert partner_arg is None, f"Expected partner_arg to be None on dialogue exit, got: {partner_arg}"


def test_departed_npc_detected_on_structured_depart_event():
    """Structured depart cast_event removes the NPC from present_npcs and records departed status."""
    from game_engine.npcs.cast_planner import plan_pre_turn, apply_cast_events

    session = {
        "id": 991123,
        "current_location": "Morning Courtyard",
        "current_turn_index": 4,
        "current_npcs": [{"name": "Minato Saito", "role": "Drama Club Lead"}],
        "dialogue_partner": "Minato Saito",
        "dialogue_partners": ["Minato Saito"],
        "extra_json": {},
    }
    party = [[{"name": "Artemiusz", "user_id": 1}]]
    action = [{"label": "Thank Minato Saito, excuse yourself, and look around the room", "ends_dialogue": True}]

    plan = plan_pre_turn(session, party, action)
    final_plan, rejections = apply_cast_events(
        plan,
        [{"type": "depart", "npc": "Minato Saito", "reason": "Waves goodbye and heads to class"}],
        session,
        party,
    )
    assert rejections == []
    assert "Minato Saito" in final_plan.departing_npcs
    assert not any(n.get("name") == "Minato Saito" for n in final_plan.present_npcs)
