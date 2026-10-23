import pytest
from unittest.mock import MagicMock, patch

from game_engine.npcs.cast_planner import (
    plan_pre_turn,
    render_stage_plan,
    apply_cast_events,
    get_cast_state,
    save_cast_state,
    CastPlan,
)
from mechanics.narrative.intent import (
    is_dialogue_exit_action,
    get_resolved_intent,
)
from models.llm_schemas import Choice, CastEvent, DeterministicTurnNarration


def test_choice_and_resolved_intent_ends_dialogue():
    """Verify that Choice and ActionClassification support ends_dialogue and is_dialogue_exit_action recognizes it."""
    # Choice with ends_dialogue = True
    c = Choice(label="Thank Minato Saito, excuse yourself, and look around", stat="NONE", requirement=0, intent="area_scout", ends_dialogue=True)
    assert c.ends_dialogue is True
    assert c.intent == "area_scout"

    # Action dict with ends_dialogue
    action = {
        "label": "Thank Minato Saito, excuse yourself, and look around the room",
        "intent": "area_scout",
        "ends_dialogue": True,
        "target_npc": "Minato Saito",
    }
    assert is_dialogue_exit_action(action) is True

    r_intent = get_resolved_intent(action)
    assert r_intent["ends_dialogue"] is True
    assert r_intent["intent"] == "area_scout"


def test_minato_case_departure_and_bystander():
    """The Minato case: area_scout + ends_dialogue -> dialogue_partners is empty, Minato is a room bystander, prose quotes change nothing."""
    session = {
        "id": 9999,
        "current_location": "Classroom 2-A",
        "current_turn_index": 5,
        "current_npcs": [{"name": "Minato Saito", "stage_role": "active_partner"}],
        "dialogue_partner": "Minato Saito",
        "dialogue_partners": ["Minato Saito"],
        "extra_json": {},
    }
    party = [[{"name": "Hero", "user_id": 1}]]
    actions = [{
        "label": "Thank Minato Saito, excuse yourself, and look around the room",
        "intent": "area_scout",
        "ends_dialogue": True,
        "target_npc": "Minato Saito",
    }]

    # Pre-turn planning
    plan = plan_pre_turn(session, party, actions)
    assert plan.has_exited_convo is True
    assert plan.dialogue_partners == []
    assert "Minato Saito" in plan.bystander_npcs
    assert any(n["name"] == "Minato Saito" for n in plan.present_npcs)

    # Cooldown should be recorded
    c_state = get_cast_state(session)
    assert c_state["disengaged_at_turn"].get("minato saito") == 5

    # Post-narration: Narrator outputs prose where Minato talks ('Catch you later!'), but NO cast_events
    raw_cast_events = []
    final_plan, rejections = apply_cast_events(plan, raw_cast_events, session, party)

    # Dialogue partner MUST remain empty! Minato must NOT resurrect into [TALKING]!
    assert final_plan.dialogue_partners == []
    assert "Minato Saito" in final_plan.bystander_npcs
    assert rejections == []


def test_reengage_cooldown_and_player_override():
    """An engage cast_event within 2 turns of disengagement is rejected, but a player dialogue_init overrides cooldown."""
    session = {
        "id": 9999,
        "current_location": "Classroom 2-A",
        "current_turn_index": 6,  # 1 turn after turn 5
        "current_npcs": [{"name": "Minato Saito", "stage_role": "room_bystander"}],
        "dialogue_partner": None,
        "dialogue_partners": [],
        "extra_json": {"cast_state": {"disengaged_at_turn": {"minato saito": 5}, "idle_turns": {}}},
    }
    party = [[{"name": "Hero", "user_id": 1}]]
    # Ambient player action: player investigates desk (NOT targeting Minato)
    actions = [{"label": "Examine the teacher's desk", "intent": "investigate_clue", "ends_dialogue": False}]

    plan = plan_pre_turn(session, party, actions)
    assert plan.dialogue_partners == []

    # Narrator attempts to suggest Minato walking up to talk (engage)
    cast_events = [{"type": "engage", "npc": "Minato Saito", "reason": "Minato comments on the desk"}]
    final_plan, rejections = apply_cast_events(plan, cast_events, session, party)

    # MUST be rejected due to 2-turn cooldown!
    assert len(rejections) == 1
    assert "cooldown active" in rejections[0]["reason"].lower()
    assert final_plan.dialogue_partners == []

    # Now test player directly choosing to talk to Minato at turn 6: Player action OVERRIDES cooldown!
    actions_talk = [{"label": "Ask Minato about the test", "intent": "dialogue_init", "target_npc": "Minato Saito", "ends_dialogue": False}]
    plan_override = plan_pre_turn(session, party, actions_talk)
    assert plan_override.dialogue_partners == ["Minato Saito"]


def test_idle_turn_timeout():
    """3 consecutive non-involving turns causes an active partner to time out and return to bystander."""
    session = {
        "id": 9999,
        "current_location": "Library",
        "current_turn_index": 10,
        "current_npcs": [{"name": "Sofia Vance", "stage_role": "active_partner"}],
        "dialogue_partner": "Sofia Vance",
        "dialogue_partners": ["Sofia Vance"],
        "extra_json": {"cast_state": {"disengaged_at_turn": {}, "idle_turns": {"sofia vance": 2}}},
    }
    party = [[{"name": "Hero", "user_id": 1}]]
    # Player performs action not involving Sofia
    actions = [{"label": "Browse books on ancient alchemy", "intent": "area_scout", "ends_dialogue": False}]

    plan = plan_pre_turn(session, party, actions)
    # Reached 3 idle turns -> Sofia should time out!
    assert plan.dialogue_partners == []
    assert "Sofia Vance" in plan.bystander_npcs
    c_state = get_cast_state(session)
    assert c_state["disengaged_at_turn"].get("sofia vance") == 10


def test_movement_drops_unaccompanied_partners():
    """Moving to a different location drops active dialogue partners who are not in the party and not invited."""
    session = {
        "id": 9999,
        "current_location": "Courtyard",
        "current_turn_index": 12,
        "current_npcs": [{"name": "Sofia Vance"}],
        "dialogue_partner": "Sofia Vance",
        "dialogue_partners": ["Sofia Vance"],
        "extra_json": {},
    }
    party = [[{"name": "Hero", "user_id": 1}]]
    # Solo travel action to Library
    actions = [{"label": "Walk over to the library", "intent": "movement", "ends_dialogue": False}]

    plan = plan_pre_turn(session, party, actions, new_loc="Library")
    assert plan.dialogue_partners == []


def test_arrive_event_validation():
    """Arrive events for ambient role extras are accepted; un-scheduled known NPCs are rejected."""
    session = {
        "id": 9999,
        "current_location": "Academy Cafe",
        "current_turn_index": 15,
        "current_npcs": [],
        "dialogue_partner": None,
        "dialogue_partners": [],
        "extra_json": {},
    }
    party = [[{"name": "Hero", "user_id": 1}]]
    actions = [{"label": "Order a tea", "intent": "general_action", "ends_dialogue": False}]
    plan = plan_pre_turn(session, party, actions)

    cast_events = [
        {"type": "arrive", "npc": "a friendly barista", "reason": "staffing the counter"},
        {"type": "arrive", "npc": "Lord Malakar", "reason": "spawns randomly"},
    ]

    final_plan, rejections = apply_cast_events(plan, cast_events, session, party)

    # 'a friendly barista' matches ambient extra keyword -> approved
    assert any(n["name"] == "a friendly barista" for n in final_plan.present_npcs)

    # 'Lord Malakar' is unscheduled -> rejected
    assert any(r["npc"] == "Lord Malakar" for r in rejections)
    assert not any(n["name"] == "Lord Malakar" for n in final_plan.present_npcs)


def test_depart_event_for_party_member_rejected():
    """A depart cast_event for a formal party member is rejected."""
    session = {
        "id": 9999,
        "current_location": "Dungeon Entrance",
        "current_turn_index": 20,
        "current_npcs": [{"name": "Aria"}],
        "dialogue_partner": None,
        "dialogue_partners": [],
        "extra_json": {},
    }
    party = [
        [{"name": "Hero", "user_id": 1}],
        [{"name": "Aria", "user_id": 2}],
    ]
    actions = [{"label": "Check weapons", "intent": "general_action", "ends_dialogue": False}]
    plan = plan_pre_turn(session, party, actions)

    cast_events = [{"type": "depart", "npc": "Aria", "reason": "wanders off"}]
    final_plan, rejections = apply_cast_events(plan, cast_events, session, party)

    assert len(rejections) == 1
    assert "party member" in rejections[0]["reason"].lower()
    assert any(n["name"] == "Aria" for n in final_plan.present_npcs)


def test_deterministic_turn_narration_cast_events_schema():
    """Verify DeterministicTurnNarration model parses and validates cast_events."""
    data = {
        "scene_title": "Quiet Study",
        "outcome_narrative": "You step away from the table.",
        "next_narrative": "The room falls quiet.",
        "next_choices": [
            {"label": "Leave the room", "intent": "movement", "ends_dialogue": True}
        ],
        "cast_events": [
            {"type": "depart", "npc": "Minato Saito", "reason": "Excuses himself"}
        ]
    }
    model = DeterministicTurnNarration(**data)
    assert len(model.cast_events) == 1
    assert model.cast_events[0].type == "depart"
    assert model.cast_events[0].npc == "Minato Saito"
    assert model.next_choices[0].ends_dialogue is True


def test_dismisses_npc_flag_and_persistence(tmp_path, monkeypatch):
    """Verify dismisses_npc structured flag dismisses NPC without keyword matching, and cast_state persists."""
    import db
    from models.llm_schemas import Choice
    c = Choice(label="Nod quietly to Kana", target_npc="Kana", dismisses_npc=True)
    assert c.dismisses_npc is True

    session = {
        "id": 8888,
        "current_location": "Tea Shop",
        "history": [{"narrative": "Turn 1"}, {"narrative": "Turn 2"}],
        "current_npcs": [{"name": "Kana"}, {"name": "Old Man"}],
        "dialogue_partner": "Kana",
        "dialogue_partners": ["Kana"],
        "extra_json": {},
    }
    party = [[{"name": "Hero", "user_id": 1}]]
    # Notice: label contains ZERO departure keywords ("leave", "go home", etc.)
    action = {
        "label": "Nod quietly to Kana",
        "target_npc": "Kana",
        "dismisses_npc": True,
        "ends_dialogue": True,
    }

    # Mock db.update_session to capture extra dict
    captured_db_updates = {}
    def mock_update_session(sess_id, **kwargs):
        captured_db_updates.setdefault(sess_id, {}).update(kwargs)

    monkeypatch.setattr(db, "update_session", mock_update_session)

    plan = plan_pre_turn(session, party, [action])
    assert "Kana" in plan.departing_npcs
    assert not any(n["name"] == "Kana" for n in plan.present_npcs)
    assert plan.dialogue_partners == []
    assert any(n["name"] == "Old Man" for n in plan.present_npcs)

    # Verify db.update_session was invoked with cast_state extra
    assert 8888 in captured_db_updates
    assert "extra" in captured_db_updates[8888]
    assert "cast_state" in captured_db_updates[8888]["extra"]
    saved_cast = captured_db_updates[8888]["extra"]["cast_state"]
    assert "disengaged_at_turn" in saved_cast
    assert saved_cast["disengaged_at_turn"].get("kana") == 2  # len(history) == 2

    # Verify reload hydration via get_cast_state
    hydrated_session = {
        "id": 8888,
        "cast_state": saved_cast,
    }
    loaded_state = get_cast_state(hydrated_session)
    assert loaded_state["disengaged_at_turn"].get("kana") == 2
