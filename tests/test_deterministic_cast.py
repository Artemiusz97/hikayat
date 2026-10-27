from __future__ import annotations
import asyncio
import pytest
from unittest.mock import AsyncMock, patch

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
    c = Choice(label="Thank Minato Saito, excuse yourself, and look around", stat="NONE", requirement=0, intent="area_scout", ends_dialogue=True)
    assert c.ends_dialogue is True
    assert c.intent == "area_scout"

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

    plan = plan_pre_turn(session, party, actions)
    assert plan.has_exited_convo is True
    assert plan.dialogue_partners == []
    assert "Minato Saito" in plan.bystander_npcs
    assert any(n["name"] == "Minato Saito" for n in plan.present_npcs)

    c_state = get_cast_state(session)
    assert c_state["disengaged_at_turn"].get("minato saito") == 5

    raw_cast_events = []
    final_plan, rejections = apply_cast_events(plan, raw_cast_events, session, party)

    assert final_plan.dialogue_partners == []
    assert "Minato Saito" in final_plan.bystander_npcs
    assert rejections == []


def test_reengage_cooldown_and_player_override():
    """An engage cast_event within 2 turns of disengagement is rejected, but a player dialogue_init overrides cooldown."""
    session = {
        "id": 9999,
        "current_location": "Classroom 2-A",
        "current_turn_index": 6,
        "current_npcs": [{"name": "Minato Saito", "stage_role": "room_bystander"}],
        "dialogue_partner": None,
        "dialogue_partners": [],
        "extra_json": {"cast_state": {"disengaged_at_turn": {"minato saito": 5}, "idle_turns": {}}},
    }
    party = [[{"name": "Hero", "user_id": 1}]]
    actions = [{"label": "Examine the teacher's desk", "intent": "investigate_clue", "ends_dialogue": False}]

    plan = plan_pre_turn(session, party, actions)
    assert plan.dialogue_partners == []

    cast_events = [{"type": "engage", "npc": "Minato Saito", "reason": "Minato comments on the desk"}]
    final_plan, rejections = apply_cast_events(plan, cast_events, session, party)

    assert len(rejections) == 1
    assert "cooldown active" in rejections[0]["reason"].lower()
    assert final_plan.dialogue_partners == []

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
    actions = [{"label": "Browse books on ancient alchemy", "intent": "area_scout", "ends_dialogue": False}]

    plan = plan_pre_turn(session, party, actions)
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
    actions = [{"label": "Walk over to the library", "intent": "movement", "ends_dialogue": False}]

    plan = plan_pre_turn(session, party, actions, new_loc="Library")
    assert plan.dialogue_partners == []


def test_arrive_gate_known_contact_vs_open_world_stranger_and_private_room(tmp_path, monkeypatch):
    """D4: Known off-schedule contacts are blocked unless appointed; open-world caps new arrivals at 1 and blocks private rooms."""
    import db
    import db.core

    isolated_db = str(tmp_path / "test_d4_arrive.db")
    monkeypatch.setattr(db, "DB_PATH", isolated_db)
    monkeypatch.setattr(db.core, "DB_PATH", isolated_db)
    db.init_db()

    sess_id = db.create_session(701, "solo", 1, "vivid", "balanced", False, scenario="fantasy")
    db.update_session(sess_id, current_location="Frontier Town ➔ Tavern ➔ Common Hall", current_npcs=[])
    db.upsert_contact(sess_id, "lord_malakar", "Lord Malakar", basic_info={"location": "Obsidian Citadel"})

    session = db.get_session(sess_id)
    party = [[{"name": "Hero", "user_id": 701}]]
    plan = plan_pre_turn(session, party, [{"label": "Order a mug of ale", "intent": "general_action"}])

    cast_events = [
        {"type": "arrive", "npc": "a friendly barista", "reason": "staffing counter"},
        {"type": "arrive", "npc": "Lord Malakar", "reason": "teleports randomly"},
        {"type": "arrive", "npc": "Garrick Stone", "reason": "wandering mercenary"},
        {"type": "arrive", "npc": "Lyra Whisper", "reason": "second unscheduled stranger"},
    ]
    final_plan, rejections = apply_cast_events(plan, cast_events, session, party)
    present_names = [n["name"] for n in final_plan.present_npcs]

    # Ambient extra + max 1 open-world stranger approved; known remote Lord Malakar & 2nd stranger rejected
    assert "a friendly barista" in present_names
    assert "Garrick Stone" in present_names
    assert "Lord Malakar" not in present_names
    assert "Lyra Whisper" not in present_names
    assert len(rejections) == 2

    # Private room blocks even open-world unscheduled strangers
    db.save_world_node(sess_id, "room_inn_bed", None, "Private Inn Bedroom", node_type="ROOM", privacy_level="private")
    session["current_node_id"] = "room_inn_bed"
    session["current_location"] = "Frontier Town ➔ Tavern ➔ Private Inn Bedroom"
    priv_plan = plan_pre_turn(session, party, [{"label": "Rest quietly"}])
    priv_final, priv_rej = apply_cast_events(
        priv_plan, [{"type": "arrive", "npc": "Stranger Bob", "reason": "walks in"}], session, party
    )
    assert len(priv_rej) == 1
    assert not any(n["name"] == "Stranger Bob" for n in priv_final.present_npcs)


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


def test_stealth_presence_shield_blocks_engage():
    """D16: Active stealth (is_stealth=True + succeeded check) sets stealth_active and blocks NPC engage events."""
    session = {
        "id": 9981,
        "current_location": "Guard Barracks",
        "current_turn_index": 8,
        "current_npcs": [{"name": "Captain Varn", "stage_role": "room_bystander"}],
        "dialogue_partner": None,
        "dialogue_partners": [],
        "extra_json": {},
    }
    party = [[{"name": "Shadow", "user_id": 1}]]
    actions = [{
        "label": "Slip behind the weapon racks in silence",
        "intent": "stealth_covert",
        "is_stealth": True,
        "check": {"succeeded": True, "tier": "success"},
    }]
    plan = plan_pre_turn(session, party, actions, persist_db=False)
    assert plan.stealth_active is True
    assert "[STAGE PLAN — STEALTH ACTIVE]" in render_stage_plan(plan)

    final_plan, rejections = apply_cast_events(
        plan,
        [{"type": "engage", "npc": "Captain Varn", "reason": "Greets player casually"}],
        session,
        party,
        persist_db=False,
    )
    assert len(rejections) == 1
    assert "stealth" in rejections[0]["reason"].lower()
    assert final_plan.dialogue_partners == []


def test_clean_choices_strips_unstamped_structural_ids_preserves_stamped(tmp_path, monkeypatch):
    """D5: Un-stamped LLM choices strip structural IDs (quest_id, target_node_id); _server_stamped choices keep them."""
    import db
    import db.core
    from game_engine.choices_cleaner import clean_choices_impl

    isolated_db = str(tmp_path / "test_d5_stamp.db")
    monkeypatch.setattr(db, "DB_PATH", isolated_db)
    monkeypatch.setattr(db.core, "DB_PATH", isolated_db)
    db.init_db()
    sess_id = db.create_session(799, "solo", 1, "vivid", "balanced", False, scenario="fantasy")
    db.upsert_quest(
        session_id=sess_id,
        quest_id="SQ-REAL",
        quest_type="Story Quest",
        title="Archive Chest",
        objective="Unlock the archive chest",
        status="Active",
        is_story_quest=1,
    )
    db.save_quest_waypoints(
        session_id=sess_id,
        quest_id="SQ-REAL",
        waypoints=[{"stage_index": 1, "stage_label": "Unlock the archive chest", "target_location": "Archive Hall", "completion_trigger": "skill_check"}],
    )

    raw_choices = [
        {
            "label": "Inspect the rusty barrel",
            "stat": "PER",
            "requirement": 5,
            "quest_id": "SQ-REAL",
            "target_node_id": "hallucinated_node",
            "triggers_loot_roll": True,
            "is_quest_action": True,
        },
        {
            "label": "⭐ [Story Quest] Unlock the archive chest",
            "stat": "AGI",
            "requirement": 6,
            "quest_id": "SQ-REAL",
            "target_node_id": "room_archive",
            "triggers_loot_roll": True,
            "is_quest_action": True,
            "_server_stamped": True,
        },
    ]
    cleaned = clean_choices_impl(None, raw_choices, scenario="fantasy", location="Archive Hall", session_id=sess_id)
    unstamped = next(c for c in cleaned if "rusty barrel" in c["label"])
    stamped = next(c for c in cleaned if "archive chest" in c["label"])

    assert not unstamped.get("quest_id")
    assert not unstamped.get("target_node_id")
    assert not unstamped.get("is_quest_action")

    assert stamped.get("quest_id") == "SQ-REAL"
    assert stamped.get("target_node_id") == "room_archive"
    assert stamped.get("triggers_loot_roll") is True
    assert stamped.get("is_quest_action") is True


def test_retry_narration_freezes_cast_state(tmp_path, monkeypatch):
    """D13: TurnService.retry_narration updates prose/choices while keeping npcs_present, dialogue_partners, and cast_state frozen."""
    import db
    import db.core
    from services.turn_service import TurnService

    isolated_db = str(tmp_path / "test_d13_retry.db")
    monkeypatch.setattr(db, "DB_PATH", isolated_db)
    monkeypatch.setattr(db.core, "DB_PATH", isolated_db)
    db.init_db()

    uid = 702
    db.create_character(uid, "Ren", "Student", stats={"STR": 5, "PER": 5, "END": 5, "CHA": 6, "INT": 6, "AGI": 5, "LUK": 5})
    sess_id = db.create_session(uid, "solo", 1, "vivid", "balanced", False, scenario="high_school_drama")
    frozen_npcs = [{"name": "Minato Saito", "stage_role": "room_bystander"}]
    frozen_cast = {"disengaged_at_turn": {"minato saito": 3}, "idle_turns": {}}
    db.update_session(
        sess_id,
        current_location="Classroom 2-A",
        current_npcs=frozen_npcs,
        dialogue_partner=None,
        extra={"cast_state": frozen_cast, "dialogue_partners": []},
    )
    db.set_turn_snapshot(sess_id, {
        "status": "completed",
        "retry_attempts": 0,
        "applied": {
            "location": "Classroom 2-A",
            "npcs_present": frozen_npcs,
            "dialogue_partners": [],
            "dialogue_partner": None,
            "cast_state": frozen_cast,
        },
    })

    fake_retry_llm = {
        "scene_title": "Retried Quiet Classroom",
        "outcome_narrative": "Freshly rewritten prose.",
        "next_narrative": "Minato glances out the window.",
        "next_choices": [{"label": "Read textbook", "stat": "NONE", "requirement": 0}],
        "cast_events": [{"type": "engage", "npc": "Minato Saito", "reason": "Should be ignored on retry"}],
        "npcs_present": [{"name": "Hallucinated Ghost"}],
        "dialogue_partners": ["Minato Saito"],
    }
    with patch("game_engine.turn.narration.run_narration_pass", new=AsyncMock(return_value=fake_retry_llm)):
        resp = asyncio.run(TurnService.retry_narration(sess_id, uid))

    assert resp.outcome.get("scene_title") == "Retried Quiet Classroom"
    assert resp.outcome.get("npcs_present") == frozen_npcs
    assert resp.outcome.get("dialogue_partners") == []
    reloaded = db.get_session(sess_id)
    assert reloaded.get("cast_state") == frozen_cast


def test_deterministic_turn_narration_cast_events_schema():
    """Verify DeterministicTurnNarration model parses and validates cast_events and drops invalid types."""
    data = {
        "scene_title": "Quiet Study",
        "outcome_narrative": "You step away from the table.",
        "next_narrative": "The room falls quiet.",
        "next_choices": [
            {"label": "Leave the room", "intent": "movement", "ends_dialogue": True}
        ],
        "cast_events": [
            {"type": "depart", "npc": "Minato Saito", "reason": "Excuses himself"},
            {"type": "invalid_teleport", "npc": "Ghost", "reason": "Invalid event filtered"},
        ],
    }
    model = DeterministicTurnNarration(**data)
    assert len(model.cast_events) == 1
    assert model.cast_events[0].type == "depart"
    assert model.cast_events[0].npc == "Minato Saito"
    assert model.next_choices[0].ends_dialogue is True


def test_dismisses_npc_flag_and_persistence(tmp_path, monkeypatch):
    """Verify dismisses_npc structured flag dismisses NPC without keyword matching, and cast_state persists when persist_db=True."""
    import db
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
    action = {
        "label": "Nod quietly to Kana",
        "target_npc": "Kana",
        "dismisses_npc": True,
        "ends_dialogue": True,
    }

    captured_db_updates = {}
    def mock_update_session(sess_id, **kwargs):
        captured_db_updates.setdefault(sess_id, {}).update(kwargs)

    monkeypatch.setattr(db, "update_session", mock_update_session)

    # Staged mode (persist_db=False) mutates zero DB rows
    plan_staged = plan_pre_turn(dict(session), party, [action], persist_db=False)
    assert "Kana" in plan_staged.departing_npcs
    assert 8888 not in captured_db_updates

    # Direct mode (persist_db=True) persists cast_state
    plan = plan_pre_turn(session, party, [action], persist_db=True)
    assert "Kana" in plan.departing_npcs
    assert not any(n["name"] == "Kana" for n in plan.present_npcs)
    assert plan.dialogue_partners == []
    assert any(n["name"] == "Old Man" for n in plan.present_npcs)
    assert 8888 in captured_db_updates
    saved_cast = captured_db_updates[8888]["extra"]["cast_state"]
    assert saved_cast["disengaged_at_turn"].get("kana") == 2


def test_long_hall_faction_homonym_never_spawns_from_prose(tmp_path, monkeypatch):
    """Regression test: 'Long Hall' in faction leadership_roster must NEVER spawn from 'casts long, flickering shadows' or get marked TALKING from 'lobby's'."""
    import db
    import db.core
    import game_engine

    isolated_db = str(tmp_path / "test_long_hall.db")
    monkeypatch.setattr(db, "DB_PATH", isolated_db)
    monkeypatch.setattr(db.core, "DB_PATH", isolated_db)
    db.init_db()

    sess_id = db.create_session(
        host_user_id=777,
        mode="solo",
        capacity=1,
        verbosity="vivid",
        dialogue_mode="balanced",
        image_gen_enabled=False,
        scenario="urban_anomalies",
    )
    loc = "Downtown Commercial District ➔ Aegis Regional Office ➔ Reception Rotunda"
    db.update_session(sess_id, current_location=loc, current_npcs=[])
    db.upsert_faction(
        session_id=sess_id,
        name="Metropolitan Ward Control Directorate",
        delta_score=0,
        hierarchy_template="agency",
        leadership_roster=[
            {"rank": 4, "title": "Division Executive", "name": "Long Hall", "is_player": False}
        ],
    )

    session = db.get_session(sess_id)
    result = {
        "scene_title": "Stabilization Pulse",
        "outcome_narrative": (
            "The violet stabilization field casts long, flickering shadows against the lobby's reception rotunda."
        ),
        "next_narrative": "Artemiusz stands alone in the center of the atrium.",
        "cast_events": [],
        "actor_poses": {"Long Hall": {"posture": "standing"}},
        "dialogue_partners": [],
        "dialogue_partner": None,
    }

    npcs_det = game_engine.process_scene_npcs(
        result,
        session,
        new_loc=loc,
        old_loc=loc,
        actions=[{"label": "Deploy resonance dampeners around the primary pulse site"}],
        party=[({"name": "Artemiusz"}, [])],
    )
    assert npcs_det == []

    _, _, _, partner_arg, _ = game_engine.extract_scene_fields(
        {**result, "npcs_present": [{"name": "Long Hall"}]},
        session=session,
    )
    assert partner_arg == []
