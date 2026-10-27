from __future__ import annotations

import asyncio
from typing import Any, Dict, List
from unittest.mock import AsyncMock
import pytest

import db
import game_engine
import skill_check
from game_engine.npcs.cast_planner import apply_cast_events, plan_pre_turn
from game_engine.npcs.stage_manager import compute_pre_turn_stage
from game_engine.turn.dialogue import _compute_dialogue_intent
from mechanics.social.conversation_choices import (
    evaluate_conversation_departure_turn,
    get_npc_departure_states,
    pin_dialogue_exit_last,
    relocate_departed_schedule_npcs,
    save_npc_departure_states,
)
from services.turn_service import TurnService


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_conversation_architecture.db")
    monkeypatch.setattr(db, "DB_PATH", test_db)
    monkeypatch.setattr(db.core, "DB_PATH", test_db)
    db.init_db()
    return test_db


def _seed_test_session(
    scenario: str = "anomalous_incursions",
    location: str = "Sector 4 ➔ Containment Outpost ➔ Lobby",
    minute: int = 540,
) -> tuple[int, Dict[str, Any], Dict[str, Any]]:
    uid = 7001
    char = dict(
        db.create_character(
            user_id=uid,
            name="Rizal",
            char_class="Operative",
            stats={"STR": 6, "AGI": 6, "INT": 7, "END": 6, "CHA": 7, "PER": 6, "LUK": 5},
            scenario=scenario,
        )
    )
    sess_id = db.create_session(
        host_user_id=uid,
        mode="solo",
        capacity=1,
        verbosity="normal",
        dialogue_mode="normal",
        image_gen_enabled=False,
        channel_id=99001,
        scenario=scenario,
        character_id=char["id"],
    )
    db.update_session(sess_id, current_location=location)
    db.update_session_time(sess_id, 1, minute, 0)
    session = dict(db.get_session(sess_id))
    session["current_location"] = location
    session["current_day"] = 1
    session["current_minute"] = minute
    return sess_id, session, char


@pytest.mark.unit
def test_stranger_turn1_conversation_choice_bands_and_blocks(isolated_db):
    sess_id, session, char = _seed_test_session()
    party = [(char, [])]

    # Seed an active bounty/quest in DB
    db.upsert_quest(
        sess_id,
        quest_id="BNT-401",
        quest_type="side_bounty",
        title="Rift Surge at Sublevel B",
        objective="Track the anomalous resonance spike near Sector 4.",
        status="Active",
        client_location="Sector 4 ➔ Sublevel B",
    )

    # Stranger NPC (0 affinity)
    npc_obj = {"name": "Putri Wijaya", "role": "Field Analyst", "stage_role": "active_partner"}
    db.upsert_contact(
        session_id=sess_id,
        character_id=char["id"],
        npc_id="putri_wijaya",
        name="Putri Wijaya",
        basic_info={"role": "Field Analyst", "location": session["current_location"], "met_in_person": True},
        delta_score=0,
    )
    session["current_npcs"] = [npc_obj]
    session["dialogue_partner"] = "Putri Wijaya"
    session["dialogue_partners"] = ["Putri Wijaya"]

    # LLM hallucinates premature Stranger actions + random Walk With + unprompted Convince Stay + omits Leave Convo
    bad_llm_choices = [
        {"label": "Walk with Putri Wijaya to Duck Pond & Wooden Footbridge", "stat": "NONE", "requirement": 0},
        {"label": "[CHA] Convince Putri Wijaya to stay here a little longer", "stat": "CHA", "requirement": 11},
        {"label": "Compliment Putri Wijaya on her striking eyes", "stat": "CHA", "requirement": 6},
        {"label": "Offer a witty observation and playfully tease Putri Wijaya", "stat": "CHA", "requirement": 6},
        {"label": "Ask Putri Wijaya about anomalous Rift Surge readings near Sector 4", "stat": "INT", "requirement": 6},
    ]

    choices = game_engine.build_hybrid_turn_choices(
        bad_llm_choices,
        session=session,
        party=party,
        result={"npcs_present": [npc_obj], "dialogue_partners": ["Putri Wijaya"], "location": session["current_location"]},
    )

    labels = [c["label"] for c in choices]
    labels_low = " | ".join(labels).lower()

    # Forbidden Stranger options must be completely absent
    assert "walk with" not in labels_low
    assert "convince" not in labels_low or "stay" not in labels_low
    assert "compliment" not in labels_low
    assert "witty observation" not in labels_low
    assert "tease" not in labels_low

    # Pinned final slot MUST be exact standardized Leave conversation
    assert choices[-1]["label"] == "Leave conversation with Putri Wijaya"
    assert choices[-1]["stat"] == "NONE"
    assert choices[-1]["requirement"] == 0
    assert choices[-1]["intent"] == "dialogue_exit"
    assert choices[-1]["ends_dialogue"] is True

    # Band 1 + Band 2: Every non-exit dialogue choice (including questions, queries, compliments, jokes, teases, flirts) is skill-check gated!
    body = choices[:-1]
    assert 3 <= len(body) <= 7
    for c in body:
        assert c["stat"] in ("INT", "PER", "CHA")
        assert int(c["requirement"]) >= 5


@pytest.mark.unit
def test_affinity_tier_scaling_negative_acquaintance_friend_and_meetup(isolated_db):
    sess_id, session, char = _seed_test_session(
        scenario="slice_of_life",
        location="Harbor District ➔ Pier Cafe ➔ Patio Table",
    )
    party = [(char, [])]
    db.save_session_location(sess_id, "loc_boardwalk", "Harbor District", "Pier Cafe", "Boardwalk Overlook")
    npc_obj = {"name": "Nadia Kusuma", "role": "Illustrator", "stage_role": "active_partner"}
    session["current_npcs"] = [npc_obj]
    session["dialogue_partners"] = ["Nadia Kusuma"]

    raw_social_mix = [
        {"label": "Offer Nadia Kusuma a polite compliment on her sketchbook work", "stat": "CHA", "requirement": 6},
        {"label": "Playfully tease Nadia Kusuma and flirt with her", "stat": "CHA", "requirement": 7},
        {"label": "Walk with Nadia Kusuma to Distant Industrial Smelter", "stat": "NONE", "requirement": 0},
        {"label": "Walk with Nadia Kusuma to Boardwalk Overlook", "stat": "NONE", "requirement": 0},
        {"label": "Ask Nadia Kusuma about local gallery rumors in the district", "stat": "INT", "requirement": 6},
    ]

    # 1. Negative (-40): blocks compliment, tease/flirt, and walk-with
    db.upsert_contact(sess_id, char["id"], "nadia_kusuma", "Nadia Kusuma", basic_info={"role": "Illustrator"}, delta_score=-40)
    neg_choices = game_engine.build_hybrid_turn_choices(raw_social_mix, session=session, party=party, result={"dialogue_partners": ["Nadia Kusuma"], "npcs_present": [npc_obj]})
    neg_low = " | ".join(c["label"].lower() for c in neg_choices)
    assert "compliment" not in neg_low
    assert "walk with" not in neg_low
    assert "flirt" not in neg_low

    # 2. Acquaintance (+65, net +25 -> +40 more = +65): allows polite compliment (skill-check gated), still blocks heavy flirt & Walk With
    db.upsert_contact(sess_id, char["id"], "nadia_kusuma", "Nadia Kusuma", delta_score=105)  # -40 + 105 = 65
    acq_choices = game_engine.build_hybrid_turn_choices(raw_social_mix, session=session, party=party, result={"dialogue_partners": ["Nadia Kusuma"], "npcs_present": [npc_obj]})
    acq_map = {c["label"]: c for c in acq_choices}
    assert "Offer Nadia Kusuma a polite compliment on her sketchbook work" in acq_map
    assert acq_map["Offer Nadia Kusuma a polite compliment on her sketchbook work"]["stat"] == "CHA"
    assert acq_map["Offer Nadia Kusuma a polite compliment on her sketchbook work"]["requirement"] >= 5
    assert not any("walk with" in k.lower() for k in acq_map)
    assert not any("flirt with" in k.lower() for k in acq_map)

    # 3. Friend+ (+120): unlocks contextual Walk With (Boardwalk Overlook in same zone) while STILL blocking random off-site Smelter!
    db.upsert_contact(sess_id, char["id"], "nadia_kusuma", "Nadia Kusuma", delta_score=55)  # 65 + 55 = 120
    fr_choices = game_engine.build_hybrid_turn_choices(raw_social_mix, session=session, party=party, result={"dialogue_partners": ["Nadia Kusuma"], "npcs_present": [npc_obj]})
    fr_labels = [c["label"] for c in fr_choices]
    assert any("Walk with Nadia Kusuma to Boardwalk Overlook" in lbl for lbl in fr_labels)
    assert not any("Industrial Smelter" in lbl for lbl in fr_labels)


@pytest.mark.unit
def test_pinned_leave_conversation_survives_injections_and_ends_all_talking(isolated_db):
    sess_id, session, char = _seed_test_session()
    party = [(char, [])]
    npcs = [
        {"name": "Putri Wijaya", "role": "Field Analyst", "stage_role": "active_partner", "attention_ring": "ring_1_partner"},
        {"name": "Raka Pratama", "role": "Vanguard", "stage_role": "active_partner", "attention_ring": "ring_1_partner"},
    ]
    session["current_npcs"] = npcs
    session["dialogue_partners"] = ["Putri Wijaya", "Raka Pratama"]
    session["dialogue_partner"] = "Putri Wijaya"
    db.add_temporary_companion(sess_id, {"name": "Putri Wijaya", "role": "Field Analyst"})

    # Flood with 10 choices; multi-NPC pinned choice must be "Leave conversation" at the very end
    flooded = [{"label": f"Inspect anomaly log #{i}", "stat": "INT", "requirement": 6} for i in range(10)]
    pinned = pin_dialogue_exit_last(flooded, ["Putri Wijaya", "Raka Pratama"], max_total=8)
    assert len(pinned) == 8
    assert pinned[-1]["label"] == "Leave conversation"
    assert pinned[-1]["ends_dialogue"] is True

    # Execute Leave conversation action: must clear ALL partners, block LLM engage cast_event, and demote stage_role without banishing NPCs from room
    leave_action = dict(pinned[-1])
    new_partners, has_exited = _compute_dialogue_intent(session, [leave_action])
    assert has_exited is True
    assert new_partners == []
    assert db.get_temporary_companions(sess_id) == []

    plan = plan_pre_turn(session, party, [leave_action], persist_db=False)
    assert plan.has_exited_convo is True
    assert plan.dialogue_partners == []
    assert len(plan.present_npcs) == 2

    final_plan, rejections = apply_cast_events(
        plan,
        [{"type": "engage", "npc": "Putri Wijaya", "reason": "Tries to keep talking"}],
        session=session,
        party=party,
        persist_db=False,
    )
    assert final_plan.dialogue_partners == []
    assert len(rejections) == 1
    assert rejections[0]["type"] == "engage"
    for n in final_plan.present_npcs:
        assert n.get("stage_role") == "room_bystander"
        assert n.get("attention_ring") == "ring_3_bystander"


@pytest.mark.integration
def test_urgent_schedule_departure_full_state_machine_and_relocation(isolated_db, monkeypatch):
    sess_id, session, char = _seed_test_session(
        scenario="anomalous_incursions",
        location="Sector 4 ➔ Containment Outpost ➔ Lobby",
        minute=540,  # 09:00 AM (far from 12:00 PM boundary)
    )
    party = [(char, [])]
    npc_obj = {"name": "Putri Wijaya", "role": "Field Analyst", "stage_role": "active_partner"}
    db.upsert_contact(
        sess_id,
        char["id"],
        "putri_wijaya",
        "Putri Wijaya",
        basic_info={"role": "Field Analyst", "location": session["current_location"], "met_in_person": True},
        delta_score=0,
    )
    session["current_npcs"] = [npc_obj]
    session["dialogue_partners"] = ["Putri Wijaya"]
    session["dialogue_partner"] = "Putri Wijaya"

    # Force scheduled location elsewhere so we can test Turn 1-3 protection vs boundary trigger
    dest_loc = "Sector 1 ➔ Central Command ➔ Operations Floor"
    db.save_session_location(sess_id, "loc_ops_floor", "Sector 1", "Central Command", "Operations Floor")
    monkeypatch.setattr(
        "mechanics.world.schedules.get_npc_scheduled_location",
        lambda *args, **kwargs: dest_loc,
    )
    monkeypatch.setattr(
        "mechanics.world.schedules.get_npc_scheduled_node_id",
        lambda *args, **kwargs: "",
    )

    # 1. Turn 1 (only opening scene in history, no boundary crossed): MUST NOT trigger hurry!
    session["history"] = [{"type": "scene", "narrative": "Opening scene"}]
    eval_t1 = evaluate_conversation_departure_turn(
        session, [{"label": "Ask Putri Wijaya about recent anomalies", "stat": "INT", "requirement": 6}], ["Putri Wijaya"], False, party=party
    )
    assert get_npc_departure_states(session) == {}
    assert eval_t1["departing_for_schedule"] == []

    # 2. Clock crosses into 15-min pre-lunch window after 1+ real turn -> triggers Stage 1 Warning!
    session["history"].append({
        "type": "turn",
        "action_label": "Ask Putri Wijaya about recent anomalies",
        "location": session["current_location"],
        "dialogue_partners": ["Putri Wijaya"],
    })
    session["_prev_turn_day"] = 1
    session["_prev_turn_minute"] = 700
    session["current_minute"] = 710  # 10 mins before 720 lunch boundary

    eval_s1 = evaluate_conversation_departure_turn(
        session, [{"label": "Ask Putri Wijaya about Sector 4 logs", "stat": "INT", "requirement": 6}], ["Putri Wijaya"], False, party=party
    )
    st_map = get_npc_departure_states(session)
    assert st_map["putri wijaya"]["stage"] == "stage_1_warning"
    assert "Operations Floor" in eval_s1["directive_note"]

    # Stage 1 choices: Slot 0 is [CHA] Convince to stay (Stranger DC 12), and normal choices get hurry-gated (+3 DC / FREE -> CHA DC 9)
    s1_choices = game_engine.build_hybrid_turn_choices(
        [{"label": "Ask Putri Wijaya for containment intel", "stat": "INT", "requirement": 6}],
        session=session,
        party=party,
        result={"dialogue_partners": ["Putri Wijaya"], "npcs_present": [npc_obj], "location": session["current_location"]},
    )
    assert s1_choices[0]["label"] == "Convince Putri Wijaya to stay a little longer"
    assert s1_choices[0]["stat"] == "CHA"
    assert s1_choices[0]["requirement"] == 12
    assert s1_choices[-1]["label"] == "Leave conversation with Putri Wijaya"
    for mid_c in s1_choices[1:-1]:
        assert mid_c["stat"] in ("INT", "PER", "CHA")
        assert int(mid_c["requirement"]) >= 9

    # 3. Succeeding a gated non-convince choice in Stage 1 -> answers normally & transitions to Stage 2 Ultimatum
    ok_check = skill_check.CheckResult(chance=80, roll=25.0, tier="success", tier_label="Success", succeeded=True, requirement=9)
    eval_s2 = evaluate_conversation_departure_turn(
        session,
        [{"label": s1_choices[1]["label"], "stat": s1_choices[1]["stat"], "requirement": s1_choices[1]["requirement"], "check": ok_check, "success": True}],
        ["Putri Wijaya"],
        False,
        party=party,
    )
    assert get_npc_departure_states(session)["putri wijaya"]["stage"] == "stage_2_ultimatum"
    assert "STAGE 2 ULTIMATUM" in eval_s2["directive_note"]

    # Stage 2 choices: Strictly ONLY 2 options (Convince to stay | Leave conversation with Putri Wijaya)
    s2_choices = game_engine.build_hybrid_turn_choices(
        [{"label": "Ask another question", "stat": "INT", "requirement": 6}],
        session=session,
        party=party,
        result={"dialogue_partners": ["Putri Wijaya"], "npcs_present": [npc_obj], "location": session["current_location"]},
    )
    assert len(s2_choices) == 2
    assert s2_choices[0]["label"] == "Convince Putri Wijaya to stay a little longer"
    assert s2_choices[1]["label"] == "Leave conversation with Putri Wijaya"

    # 4. Submitting ANY Custom Action in Stage 2 auto-fails in TurnService.prepare_and_roll_action and causes immediate departure + relocation!
    monkeypatch.setattr(
        game_engine,
        "classify_custom_action",
        AsyncMock(return_value={"stat": "CHA", "requirement": 5, "intent": "dialogue_init", "target_npc": "Putri Wijaya"}),
    )
    rolled_custom = asyncio.run(
        TurnService.prepare_and_roll_action(
            sess_id,
            char["user_id"],
            {"custom_action_text": "Wait, tell me one more thing about the anomaly!"},
            session=session,
            char=char,
        )
    )
    assert rolled_custom["success"] is False
    assert rolled_custom["rate"] == 0
    assert rolled_custom["_stage2_custom_auto_fail"] is True

    eval_dep = evaluate_conversation_departure_turn(session, [rolled_custom], ["Putri Wijaya"], False, party=party)
    assert eval_dep["active_partners"] == []
    assert len(eval_dep["departing_for_schedule"]) == 1
    assert eval_dep["departing_for_schedule"][0]["target_location"] == dest_loc

    turn_res = {"npcs_present": [npc_obj], "dialogue_partners": ["Putri Wijaya"], "dialogue_partner": "Putri Wijaya"}
    relocate_departed_schedule_npcs(session, turn_res, eval_dep["departing_for_schedule"])
    assert turn_res["npcs_present"] == []
    assert turn_res["dialogue_partners"] == []
    assert "Putri Wijaya" in turn_res["npc_departures"]

    updated_contact = db.get_contact(sess_id, "putri_wijaya", char["id"])
    assert updated_contact["basic_info"]["location"] == dest_loc

    # 5. Traveling to Operations Floor finds Putri Wijaya physically waiting there!
    stage_arrival = compute_pre_turn_stage(
        session,
        [{"label": f"Travel to {dest_loc}", "intent": "movement", "target_location": dest_loc}],
        party=party,
    )
    arrived_names = [n.get("name") for n in (stage_arrival.get("stage_npcs") or []) if isinstance(n, dict)]
    assert "Putri Wijaya" in arrived_names


@pytest.mark.unit
def test_convince_stay_5_turn_extension_and_once_per_block_cap(isolated_db):
    sess_id, session, char = _seed_test_session(minute=715)
    party = [(char, [])]
    npc_obj = {"name": "Putri Wijaya", "role": "Field Analyst", "stage_role": "active_partner"}
    session["current_npcs"] = [npc_obj]
    session["dialogue_partners"] = ["Putri Wijaya"]
    dest_loc = "Sector 1 ➔ Central Command ➔ Operations Floor"

    save_npc_departure_states(
        session,
        {
            "putri wijaya": {
                "stage": "stage_1_warning",
                "target_location": dest_loc,
                "target_node_id": "",
                "triggered_block": "lunch",
                "turns_remaining": 0,
                "extended_block": "",
            }
        },
    )

    # Succeeding Convince to Stay grants 5 bonus turns
    ok_check = skill_check.CheckResult(chance=75, roll=12.0, tier="success", tier_label="Success", succeeded=True, requirement=12)
    conv_act = {
        "label": "Convince Putri Wijaya to stay a little longer",
        "stat": "CHA",
        "requirement": 12,
        "_convince_stay": True,
        "departure_action": "convince_stay",
        "target_npc": "Putri Wijaya",
        "check": ok_check,
        "success": True,
    }
    res_ext = evaluate_conversation_departure_turn(session, [conv_act], ["Putri Wijaya"], False, party=party)
    st = get_npc_departure_states(session)["putri wijaya"]
    assert st["stage"] == "extended_stay"
    assert st["turns_remaining"] == 5
    assert res_ext["departing_for_schedule"] == []

    # Bonus turns 1..4 count down cleanly without hurry-gating or offering Convince to Stay again
    for expected_rem in (4, 3, 2, 1):
        ev = evaluate_conversation_departure_turn(
            session, [{"label": "Ask Putri Wijaya about anomaly readings", "check": ok_check, "success": True}], ["Putri Wijaya"], False, party=party
        )
        assert ev["departing_for_schedule"] == []
        assert get_npc_departure_states(session)["putri wijaya"]["turns_remaining"] == expected_rem
        c_turn = game_engine.build_hybrid_turn_choices(
            [{"label": "Ask Putri Wijaya about anomaly readings", "stat": "INT", "requirement": 6}],
            session=session,
            party=party,
            result={"dialogue_partners": ["Putri Wijaya"], "npcs_present": [npc_obj], "location": session["current_location"]},
        )
        assert not any("convince" in c["label"].lower() and "stay" in c["label"].lower() for c in c_turn)

    # 5th bonus turn -> responds warmly and physically departs (capped once per time-block)
    ev_final = evaluate_conversation_departure_turn(
        session, [{"label": "Share one last thought", "check": ok_check, "success": True}], ["Putri Wijaya"], False, party=party
    )
    assert len(ev_final["departing_for_schedule"]) == 1
    assert ev_final["active_partners"] == []
    assert "STAY EXTENSION COMPLETE" in ev_final["directive_note"]


@pytest.mark.unit
def test_private_meetup_exit_rule_and_multi_npc_partial_departure(isolated_db, monkeypatch):
    # Part A: Private Meetup at neutral cafe -> hurry never triggers; player Leave Conversation makes NPC depart too
    sess_id, session, char = _seed_test_session(
        scenario="slice_of_life",
        location="Downtown ➔ Starlight Cafe ➔ Corner Booth",
        minute=715,
    )
    party = [(char, [])]
    dest_loc = "Downtown ➔ Design Studio ➔ Desk"
    monkeypatch.setattr("mechanics.world.schedules.get_npc_scheduled_location", lambda *a, **kw: dest_loc)
    monkeypatch.setattr("mechanics.world.schedules.get_npc_scheduled_node_id", lambda *a, **kw: "")

    db.save_phone_appointment(
        sess_id,
        npc_id="putri_wijaya",
        npc_name="Putri Wijaya",
        rendezvous_location="Downtown ➔ Starlight Cafe ➔ Corner Booth",
        topic="Coffee meetup",
        created_minute=700,
    )
    db.update_phone_appointment_status(sess_id, "putri_wijaya", "arrived")
    session["dialogue_partners"] = ["Putri Wijaya"]
    session["dialogue_partner"] = "Putri Wijaya"
    session["history"] = [
        {"type": "turn", "action_label": f"Chat turn {i}", "location": session["current_location"], "dialogue_partners": ["Putri Wijaya"]}
        for i in range(6)
    ]

    # Even after 6 linger turns near clock shift, Private Meetup suppresses hurry!
    ev_meetup = evaluate_conversation_departure_turn(
        session, [{"label": "Chat with Putri Wijaya"}], ["Putri Wijaya"], False, party=party
    )
    assert get_npc_departure_states(session) == {}
    assert ev_meetup["departing_for_schedule"] == []

    # Player clicks Leave Conversation at neutral cafe -> NPC says goodbye, mentions needing to go too, and departs!
    ev_exit_cafe = evaluate_conversation_departure_turn(
        session, [{"label": "Leave conversation with Putri Wijaya", "intent": "dialogue_exit", "ends_dialogue": True}], [], True, party=party
    )
    assert len(ev_exit_cafe["departing_for_schedule"]) == 1
    assert "PRIVATE MEETUP CONCLUSION & DEPARTURE" in ev_exit_cafe["directive_note"]

    # Part B: Private Meetup at NPC's own apartment -> NPC says warm goodbye and stays in their own home!
    home_loc = "Residential Ward ➔ Putri Wijaya's Apartment ➔ Living Room"
    session["current_location"] = home_loc
    session["dialogue_partners"] = ["Putri Wijaya"]
    db.save_phone_appointment(
        sess_id,
        npc_id="putri_wijaya",
        npc_name="Putri Wijaya",
        rendezvous_location=home_loc,
        topic="Evening hangout",
        created_minute=1100,
    )
    db.update_phone_appointment_status(sess_id, "putri_wijaya", "arrived")
    ev_exit_home = evaluate_conversation_departure_turn(
        session, [{"label": "Leave conversation with Putri Wijaya", "intent": "dialogue_exit", "ends_dialogue": True}], [], True, party=party
    )
    assert ev_exit_home["departing_for_schedule"] == []
    assert "PRIVATE MEETUP GOODBYE" in ev_exit_home["directive_note"]

    # Part C: Multi-NPC Stage 2 ("Let Putri Wijaya head out") keeps Raka Pratama in active dialogue!
    session["current_location"] = "Downtown ➔ Plaza"
    session["dialogue_partners"] = ["Putri Wijaya", "Raka Pratama"]
    npcs_multi = [
        {"name": "Putri Wijaya", "stage_role": "active_partner"},
        {"name": "Raka Pratama", "stage_role": "active_partner"},
    ]
    save_npc_departure_states(
        session,
        {"putri wijaya": {"stage": "stage_2_ultimatum", "target_location": dest_loc, "target_node_id": "", "triggered_block": "lunch", "turns_remaining": 0, "extended_block": ""}},
    )
    multi_s2 = game_engine.build_hybrid_turn_choices(
        [],
        session=session,
        party=party,
        result={"dialogue_partners": ["Putri Wijaya", "Raka Pratama"], "npcs_present": npcs_multi, "location": "Downtown ➔ Plaza"},
    )
    assert len(multi_s2) == 2
    assert multi_s2[0]["label"] == "Convince Putri Wijaya to stay a little longer"
    assert multi_s2[1]["label"] == "Let Putri Wijaya head out"

    let_go_act = dict(multi_s2[1])
    rem_partners, exited_all = _compute_dialogue_intent(session, [let_go_act])
    assert exited_all is False
    assert rem_partners == ["Putri Wijaya", "Raka Pratama"]

    ev_multi_dep = evaluate_conversation_departure_turn(session, [let_go_act], rem_partners, exited_all, party=party)
    assert ev_multi_dep["active_partners"] == ["Raka Pratama"]
    assert [d["name"] for d in ev_multi_dep["departing_for_schedule"]] == ["Putri Wijaya"]


@pytest.mark.unit
def test_llm_dict_list_coercion_and_hub_dialogue_tension_suppression(isolated_db, monkeypatch):
    from models.llm_schemas import DeterministicCombatNarration, DeterministicTurnNarration
    from game_engine.npcs.dialogue_tracking import evaluate_and_tick_scene_tension_timer

    # 1. Extra list fields returned as a single dict by the LLM must coerce cleanly to lists
    raw_llm = {
        "scene_title": "Briefing",
        "outcome_narrative": "Putri shakes her head.",
        "next_narrative": "She glances back at her console.",
        "relationship_updates": {"npc_name": "Putri Wijaya", "delta_score": -1},
        "character_outcomes": {"name": "Rizal", "hp_change": 0, "status_effects": "Focused"},
        "quest_updates": {"quest_id": "SQ-1", "status": "Active"},
    }
    parsed_turn = DeterministicTurnNarration.model_validate(raw_llm).model_dump(exclude_unset=False)
    assert isinstance(parsed_turn["relationship_updates"], list)
    assert isinstance(parsed_turn["character_outcomes"], list)
    assert isinstance(parsed_turn["quest_updates"], list)

    parsed_combat = DeterministicCombatNarration.model_validate(raw_llm).model_dump(exclude_unset=False)
    assert isinstance(parsed_combat["relationship_updates"], list)
    assert isinstance(parsed_combat["character_outcomes"], list)
    assert isinstance(parsed_combat["quest_updates"], list)

    # 2. Safe Hub / active dialogue must NOT tick tension timer or spawn hostile enemies when talking about breaches/patrols
    sess_id, session, _ = _seed_test_session(
        scenario="anomalous_incursions",
        location="S.O.A.I. HQ ➔ Main Area",
    )
    session["dialogue_partners"] = ["Putri Wijaya"]
    session["dialogue_partner"] = "Putri Wijaya"
    session["history"] = [
        {"type": "turn", "narrative": "Putri mentions the anomalous breach and the patrol schedule."},
        {"type": "turn", "narrative": "The alarm logs from the breach are still under review by the patrol."},
    ]
    res = evaluate_and_tick_scene_tension_timer(session, actions=[{"label": "Ask Putri about the breach"}])
    assert res["expired"] is False
    assert res["spawned_hostile_enemy"] is None
    assert session.get("scene_tension_timer") == 0



@pytest.mark.unit
def test_daily_conversation_ledger_non_repeating_and_progressive_taper(isolated_db):
    from mechanics.social.conversation_choices import (
        get_partner_conversation_budget_state,
        record_partner_conversation_turn,
        resolve_partner_conversation_profile,
    )

    sess_id, session, char = _seed_test_session(minute=540)
    party = [(char, [])]
    npc_obj = {"name": "Putri Wijaya", "role": "Junior Operative", "stage_role": "active_partner"}
    db.upsert_contact(
        sess_id,
        char["id"],
        "putri_wijaya",
        "Putri Wijaya",
        basic_info={"role": "Junior Operative", "location": session["current_location"], "met_in_person": True},
        delta_score=0,
    )
    session["current_npcs"] = [npc_obj]
    session["dialogue_partners"] = ["Putri Wijaya"]
    session["dialogue_partner"] = "Putri Wijaya"

    # Turn 1: Ask about work role -> recorded in daily ledger (Stranger budget = 3 -> 2 left)
    asked_q = {"label": "Ask Putri Wijaya about their work as Junior Operative", "stat": "INT", "requirement": 6}
    st1 = record_partner_conversation_turn(
        session, "Putri Wijaya", [asked_q], party=party, current_npcs=[npc_obj], was_already_partner=True
    )
    assert st1["base_budget"] == 3
    assert st1["turns_used"] == 1
    assert st1["remaining_budget"] == 2
    assert "work_role" in st1["asked_topic_signatures"]

    # Turn 2 choices: Even if LLM re-emits the same work-role question, it MUST NOT repeat!
    t2_choices = game_engine.build_hybrid_turn_choices(
        [{"label": "Ask Putri Wijaya about their work as Junior Operative", "stat": "INT", "requirement": 6}],
        session=session,
        party=party,
        result={"dialogue_partners": ["Putri Wijaya"], "npcs_present": [npc_obj], "location": session["current_location"]},
    )
    t2_labels_low = [c["label"].lower() for c in t2_choices]
    assert "ask putri wijaya about their work as junior operative" not in t2_labels_low

    # Exhaust remaining 2 social turns -> budget hits 0
    record_partner_conversation_turn(
        session,
        "Putri Wijaya",
        [{"label": "Ask Putri Wijaya how long they have been stationed here", "stat": "INT", "requirement": 6}],
        party=party,
        current_npcs=[npc_obj],
    )
    st3 = record_partner_conversation_turn(
        session,
        "Putri Wijaya",
        [{"label": "Ask Putri Wijaya about the current mood and pace around here", "stat": "PER", "requirement": 5}],
        party=party,
        current_npcs=[npc_obj],
    )
    assert st3["remaining_budget"] == 0
    assert st3["is_exhausted"] is True

    # Exhausted budget with no active quests tapers cleanly down to Leave conversation!
    exhausted_choices = game_engine.build_hybrid_turn_choices(
        [{"label": "Ask Putri Wijaya another random small-talk question", "stat": "CHA", "requirement": 6}],
        session=session,
        party=party,
        result={"dialogue_partners": ["Putri Wijaya"], "npcs_present": [npc_obj], "location": session["current_location"]},
    )
    assert len(exhausted_choices) == 1
    assert exhausted_choices[0]["label"] == "Leave conversation with Putri Wijaya"

    # Post-budget custom small-talk stamps _post_budget_zero_affinity = True
    post_act = {"label": "Keep making small talk with Putri Wijaya", "stat": "CHA", "requirement": 6}
    record_partner_conversation_turn(session, "Putri Wijaya", [post_act], party=party, current_npcs=[npc_obj])
    assert post_act.get("_post_budget_zero_affinity") is True

    # Advancing to a later time block on the same day grants +2 check-in turns
    session["current_minute"] = 840  # Afternoon block
    prof_later = resolve_partner_conversation_profile(session, "Putri Wijaya", party=party, current_npcs=[npc_obj])
    st_later = get_partner_conversation_budget_state(session, prof_later)
    assert st_later["remaining_budget"] >= 1


@pytest.mark.unit
def test_private_meetup_fresh_budget_rumor_suppression_and_tier_loosening(isolated_db):
    from mechanics.social.conversation_choices import (
        get_partner_conversation_budget_state,
        record_partner_conversation_turn,
        resolve_partner_conversation_profile,
    )

    cafe_loc = "Downtown ➔ Starlight Cafe ➔ Corner Booth"
    sess_id, session, char = _seed_test_session(scenario="slice_of_life", location=cafe_loc, minute=600)
    party = [(char, [])]
    npc_obj = {"name": "Putri Wijaya", "role": "Illustrator", "stage_role": "active_partner"}
    db.upsert_contact(
        sess_id,
        char["id"],
        "putri_wijaya",
        "Putri Wijaya",
        basic_info={"role": "Illustrator", "met_in_person": True, "exchanged_contact": True},
        delta_score=25,  # Stranger tier (25 < 50)
    )
    session["current_npcs"] = [npc_obj]
    session["dialogue_partners"] = ["Putri Wijaya"]

    # Exhaust morning Stranger budget (3 turns) before meetup
    for i in range(3):
        record_partner_conversation_turn(
            session, "Putri Wijaya", [{"label": f"Morning chat topic #{i}", "stat": "CHA", "requirement": 6}], party=party
        )

    # Start scheduled Private Meetup at Starlight Cafe -> fresh 9-turn budget + +1 tier social loosening!
    db.save_phone_appointment(
        sess_id,
        npc_id="putri_wijaya",
        npc_name="Putri Wijaya",
        rendezvous_location=cafe_loc,
        topic="Coffee hangout",
        created_minute=590,
    )
    db.update_phone_appointment_status(sess_id, "putri_wijaya", "arrived")

    prof_meetup = resolve_partner_conversation_profile(session, "Putri Wijaya", party=party, current_npcs=[npc_obj])
    assert prof_meetup["is_private_meetup"] is True
    st_meetup = get_partner_conversation_budget_state(session, prof_meetup)
    assert st_meetup["remaining_budget"] == 9

    meetup_choices = game_engine.build_hybrid_turn_choices(
        [{"label": "Offer Putri Wijaya a polite compliment on her outfit", "stat": "CHA", "requirement": 6}],
        session=session,
        party=party,
        result={"dialogue_partners": ["Putri Wijaya"], "npcs_present": [npc_obj], "location": cafe_loc},
    )
    m_labels = [c["label"] for c in meetup_choices]
    # +1 tier loosening allows Stranger (25) to use Acquaintance polite compliment during a Private Meetup!
    assert "Offer Putri Wijaya a polite compliment on her outfit" in m_labels
    # Generic rumor filler is suppressed during Private Meetups!
    assert not any("notable rumors" in lbl.lower() for lbl in m_labels)


@pytest.mark.unit
def test_stranger_contact_exchange_injected_and_respects_cooldown(isolated_db):
    from db.social import set_contact_request_cooldown

    sess_id, session, char = _seed_test_session(scenario="anomalous_incursions", minute=540)
    party = [(char, [])]
    npc_obj = {"name": "Putri Wijaya", "role": "Junior Operative", "stage_role": "active_partner"}
    db.upsert_contact(
        sess_id,
        char["id"],
        "putri_wijaya",
        "Putri Wijaya",
        basic_info={"role": "Junior Operative", "met_in_person": True},
        delta_score=10,
    )
    session["current_npcs"] = [npc_obj]
    session["dialogue_partners"] = ["Putri Wijaya"]
    session["dialogue_partner"] = "Putri Wijaya"

    choices = game_engine.build_hybrid_turn_choices(
        [{"label": "Ask Putri Wijaya about containment protocols", "stat": "INT", "requirement": 6}],
        session=session,
        party=party,
        result={"dialogue_partners": ["Putri Wijaya"], "npcs_present": [npc_obj], "location": session["current_location"]},
    )
    contact_btn = next((c for c in choices if c.get("intent") == "phone_contact_exchange"), None)
    assert contact_btn is not None
    assert "Phone Number / Contact Info" in contact_btn["label"]
    assert contact_btn["stat"] == "CHA"
    assert int(contact_btn["requirement"]) == 16

    # Once failed today (cooldown active until next day), button is suppressed
    set_contact_request_cooldown(sess_id, "Putri Wijaya", hours=24, until_next_day=True)
    choices_cd = game_engine.build_hybrid_turn_choices(
        [{"label": "Ask Putri Wijaya about containment protocols", "stat": "INT", "requirement": 6}],
        session=session,
        party=party,
        result={"dialogue_partners": ["Putri Wijaya"], "npcs_present": [npc_obj], "location": session["current_location"]},
    )
    assert not any(c.get("intent") == "phone_contact_exchange" for c in choices_cd)


@pytest.mark.unit
def test_phone_chat_daily_cap_by_affinity_tier(isolated_db, monkeypatch):
    from mechanics.system.phone.messaging import generate_contact_dm_reply

    sess_id, session, char = _seed_test_session(scenario="anomalous_incursions", minute=600)
    async def _fake_phone_llm(*args, **kwargs):
        return {"reply_text": "Hey! All good on my end.", "affinity_delta": 1, "rendezvous_location": ""}

    monkeypatch.setattr("mechanics.system.phone.call_llm_json", _fake_phone_llm)

    # Acquaintance (score=60 < 100) -> max 3 casual chat DMs per day
    db.upsert_contact(
        sess_id,
        char["id"],
        "putri_wijaya",
        "Putri Wijaya",
        basic_info={"role": "Junior Operative", "exchanged_contact": True, "met_in_person": True},
        delta_score=60,
    )
    contact_acq = dict(db.get_contact(sess_id, "putri_wijaya", char["id"]))
    lims_init = db.get_phone_daily_limits(sess_id, "putri_wijaya", 1)
    assert lims_init["chat"]["max"] == 3

    for i in range(3):
        rep = asyncio.run(generate_contact_dm_reply(session, contact_acq, char, f"Hey how is patrol #{i}?", intent="chat"))
        assert rep["check_result"]["tier_label"] != "Over Limit"

    # 4th casual chat DM on same day -> polite busy cap with 0 affinity penalty!
    rep_over = asyncio.run(generate_contact_dm_reply(session, contact_acq, char, "Still around?", intent="chat"))
    assert rep_over["check_result"]["tier_label"] == "Over Limit"
    assert int(rep_over.get("affinity_delta", 0)) == 0
    assert "hands full" in rep_over["reply_text"].lower() or "tomorrow" in rep_over["reply_text"].lower()

    # Upgrade to Friend (score >= 100) -> max 5 casual chat DMs per day!
    db.upsert_contact(sess_id, char["id"], "putri_wijaya", "Putri Wijaya", delta_score=50)  # 60+.. >= 100
    lims_friend = db.get_phone_daily_limits(sess_id, "putri_wijaya", 1)
    assert lims_friend["chat"]["max"] == 5
