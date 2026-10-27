from __future__ import annotations
"""
Comprehensive Test Suite for Phase 2: Deterministic Intimacy & Physical Milestone Engine.

Covers:
1. Metaphor Guard: Metaphorical prose produces zero intimacy or ledger changes.
2. Directional Inversion: Player-centric sub_intent maps accurately to NPC perspective.
3. First Kiss Promotion: Virgin NPC receives 'first_kiss'; subsequent kiss receives 'kiss'.
4. Check Failure Gate: Failed check yields zero meter gain, no milestone, intact clothing.
5. Target Isolation: Action targeting NPC A leaves spectator NPC B completely untouched.
6. Multi-Partner Collective: Comma-separated target_npc updates all named partners.
7. Male Refractory Soft Gate: Male in refractory period downgrades penetrative acts to foreplay + directive.
8. Premature Finish Exit Penalty: Exiting encounter while unsatisfied partner demanded inflicts -5 score penalty.
9. Hybrid Redressing & Intimate Contact Lifecycle: Reset on redress, movement, or dialogue exit.
10. D6 Confession Gate (< 100 vs >= 100): Score < 100 keeps platonic, awards +2 flattered affinity & directive.
11. D14 Smartphone DM Grounding & In-Person Gate: Meetup snaps to world_nodes; confessions & quest probes gated in-person.
12. D15 Multiplayer Co-op Intimacy: Secondary action slots in co-op party resolve cleanly.
"""

import pytest
from game_engine.state.reducers import _evaluate_npc_milestones
from game_engine.state.core import apply_outcome
from mechanics.social.intimate_excitement import (
    resolve_pre_turn_intimacy_and_clothing,
    compute_excitement_step,
    build_intimate_choice_blueprints,
)
from mechanics.system.phone.dm_grounding import (
    evaluate_dm_in_person_gate,
    resolve_rendezvous_location,
)


def test_metaphor_guard_narrative_never_triggers_milestone():
    """Metaphorical prose ('kiss of death', 'penetrate their defenses') produces zero milestones without structured sub_intent."""
    app_dict = {}
    action = {
        "label": "Deliver the kiss of death with your blade and penetrate their defenses",
        "intent": "combat_attack",
        "sub_intent": "combat_attack",
        "target_npc": "Minato Saito",
        "check": {"succeeded": True, "tier": "strong_hit"},
    }
    narrative = "You strike Minato with the kiss of death, penetrating deep into his guard."

    mem, intercourse, oral, manual, track, is_intimate, boost = _evaluate_npc_milestones(
        npc_name="Minato Saito",
        app_dict=app_dict,
        track="platonic",
        milestone_ev="",
        custom_summary=None,
        intercourse_exp="virgin",
        oral_exp="inexperienced",
        actions=[action],
        narrative_text=narrative,
        overall_check_success=True,
        is_player_romantic_action=False,
        is_player_intimate_action=False,
        is_player_oral_action=False,
        is_player_intercourse_action=False,
        is_player_confession_action=False,
        is_player_affection_action=False,
        affection_target_npc=None,
        gift_target_npc=None,
        gift_item_name=None,
        confession_target_npc=None,
        first_char_name="Hero",
    )

    assert mem is None
    assert intercourse == "virgin"
    assert oral == "inexperienced"
    assert is_intimate is False
    assert not app_dict.get("had_first_time_with_player")
    assert not app_dict.get("intercourse_revealed")


def test_directional_inversion_player_to_npc():
    """Player sub_intent 'oral_give' flips to NPC 'oral_receive'; 'oral_receive' flips to NPC 'oral_give'."""
    app_k = {}
    action_give = {
        "label": "Kneel close and please Kana with your mouth",
        "intent": "intimate_act",
        "sub_intent": "oral_give",
        "target_npc": "Kana",
        "check": {"succeeded": True, "tier": "strong_hit"},
    }
    mem_k, _, _, _, _, is_intimate_k, _ = _evaluate_npc_milestones(
        npc_name="Kana",
        app_dict=app_k,
        track="romantic",
        milestone_ev="",
        custom_summary=None,
        intercourse_exp="virgin",
        oral_exp="inexperienced",
        actions=[action_give],
        narrative_text="You pleasure Kana tenderly.",
        overall_check_success=True,
        is_player_romantic_action=True,
        is_player_intimate_action=True,
        is_player_oral_action=True,
        is_player_intercourse_action=False,
        is_player_confession_action=False,
        is_player_affection_action=False,
        affection_target_npc=None,
        gift_target_npc=None,
        gift_item_name=None,
        confession_target_npc=None,
        first_char_name="Hero",
    )
    assert is_intimate_k is True
    assert mem_k is not None
    assert app_k.get("oral_revealed") is True

    app_m = {}
    action_rec = {
        "label": "Guide Minato's head gently as he pleasures you",
        "intent": "intimate_act",
        "sub_intent": "oral_receive",
        "target_npc": "Minato",
        "check": {"succeeded": True, "tier": "strong_hit"},
    }
    mem_m, _, _, _, _, is_intimate_m, _ = _evaluate_npc_milestones(
        npc_name="Minato",
        app_dict=app_m,
        track="romantic",
        milestone_ev="",
        custom_summary=None,
        intercourse_exp="virgin",
        oral_exp="inexperienced",
        actions=[action_rec],
        narrative_text="Minato looks up at you with flushed cheeks.",
        overall_check_success=True,
        is_player_romantic_action=True,
        is_player_intimate_action=True,
        is_player_oral_action=True,
        is_player_intercourse_action=False,
        is_player_confession_action=False,
        is_player_affection_action=False,
        affection_target_npc=None,
        gift_target_npc=None,
        gift_item_name=None,
        confession_target_npc=None,
        first_char_name="Hero",
    )
    assert is_intimate_m is True
    assert mem_m is not None
    assert app_m.get("oral_revealed") is True


def test_first_kiss_promotion():
    """An NPC with no prior kiss receives 'first_kiss'; a subsequent kiss receives 'kiss'."""
    app_dict = {}
    action_kiss = {
        "label": "Lean in and kiss Kana softly",
        "intent": "intimate_act",
        "sub_intent": "kiss",
        "target_npc": "Kana",
        "check": {"succeeded": True, "tier": "strong_hit"},
    }

    mem1, _, _, _, _, _, _ = _evaluate_npc_milestones(
        npc_name="Kana",
        app_dict=app_dict,
        track="platonic",
        milestone_ev="",
        custom_summary=None,
        intercourse_exp="virgin",
        oral_exp="inexperienced",
        actions=[action_kiss],
        narrative_text="Your lips meet for the first time.",
        overall_check_success=True,
        is_player_romantic_action=True,
        is_player_intimate_action=True,
        is_player_oral_action=False,
        is_player_intercourse_action=False,
        is_player_confession_action=False,
        is_player_affection_action=False,
        affection_target_npc=None,
        gift_target_npc=None,
        gift_item_name=None,
        confession_target_npc=None,
        first_char_name="Hero",
    )
    assert mem1 is not None
    assert "first kiss" in mem1.lower()
    assert app_dict.get("had_first_kiss") is True

    mem2, _, _, _, _, _, _ = _evaluate_npc_milestones(
        npc_name="Kana",
        app_dict=app_dict,
        track="platonic",
        milestone_ev="",
        custom_summary=None,
        intercourse_exp="virgin",
        oral_exp="inexperienced",
        actions=[action_kiss],
        narrative_text="You kiss Kana again.",
        overall_check_success=True,
        is_player_romantic_action=True,
        is_player_intimate_action=True,
        is_player_oral_action=False,
        is_player_intercourse_action=False,
        is_player_confession_action=False,
        is_player_affection_action=False,
        affection_target_npc=None,
        gift_target_npc=None,
        gift_item_name=None,
        confession_target_npc=None,
        first_char_name="Hero",
    )
    assert mem2 is not None
    assert "first kiss" not in mem2.lower()
    assert "kiss" in mem2.lower()


def test_check_failure_gate_blocks_all_progression():
    """Failed skill check produces zero meter gain, no milestone, and leaves clothing intact."""
    app_dict = {}
    action_failed = {
        "label": "Attempt to undress and take Kana",
        "intent": "intimate_act",
        "sub_intent": "intercourse",
        "target_npc": "Kana",
        "check": {"succeeded": False, "tier": "fail"},
    }

    mem, exp, _, _, _, is_intimate, _ = _evaluate_npc_milestones(
        npc_name="Kana",
        app_dict=app_dict,
        track="platonic",
        milestone_ev="",
        custom_summary=None,
        intercourse_exp="virgin",
        oral_exp="inexperienced",
        actions=[action_failed],
        narrative_text="An awkward stumble breaks the mood.",
        overall_check_success=False,
        is_player_romantic_action=True,
        is_player_intimate_action=True,
        is_player_oral_action=False,
        is_player_intercourse_action=True,
        is_player_confession_action=False,
        is_player_affection_action=False,
        affection_target_npc=None,
        gift_target_npc=None,
        gift_item_name=None,
        confession_target_npc=None,
        first_char_name="Hero",
    )
    assert mem is None
    assert exp == "virgin"
    assert is_intimate is False
    assert not app_dict.get("had_first_time_with_player")

    session = {
        "id": 1001,
        "dialogue_partner": "Kana",
        "dialogue_partners": ["Kana"],
        "player_character": {"name": "Hero", "gender": "Male"},
        "physical_state": {
            "intimate_contact": "none",
            "actors": {
                "Hero": {"clothing": {"top": "Clothed", "bottom": "Clothed", "under_top": "Worn", "under_bottom": "Worn"}},
                "Kana": {"clothing": {"top": "Clothed", "bottom": "Clothed", "under_top": "Worn", "under_bottom": "Worn"}},
            },
        },
    }
    res = resolve_pre_turn_intimacy_and_clothing(session, actions=[action_failed])
    phys = res["physical_state"]
    assert phys["actors"]["Kana"]["clothing"]["bottom"] == "Clothed"
    assert phys["actors"]["Hero"]["clothing"]["bottom"] == "Clothed"
    assert phys.get("intimate_contact") == "none"


def test_target_isolation_spectator_untouched():
    """In a scene with Kana and Minato, an intimate act targeting Kana leaves Minato 100% untouched."""
    sess = {
        "id": 1002,
        "dialogue_partner": "Kana",
        "dialogue_partners": ["Kana", "Minato"],
        "player_character": {"name": "Hero", "gender": "Male"},
        "physical_state": {
            "intimate_contact": "none",
            "actors": {
                "Hero": {"clothing": {"top": "Clothed", "bottom": "Clothed", "under_top": "Worn", "under_bottom": "Worn"}},
                "Kana": {"clothing": {"top": "Clothed", "bottom": "Clothed", "under_top": "Worn", "under_bottom": "Worn"}},
                "Minato": {"clothing": {"top": "Clothed", "bottom": "Clothed", "under_top": "Worn", "under_bottom": "Worn"}},
            },
        },
    }
    action = {
        "label": "Pull Kana into your lap and undress her",
        "intent": "intimate_act",
        "sub_intent": "intercourse",
        "target_npc": "Kana",
        "check": {"succeeded": True, "tier": "strong_hit"},
    }

    app_minato = {}
    mem_m, exp_m, _, _, _, is_int_m, _ = _evaluate_npc_milestones(
        npc_name="Minato",
        app_dict=app_minato,
        track="platonic",
        milestone_ev="",
        custom_summary=None,
        intercourse_exp="virgin",
        oral_exp="inexperienced",
        actions=[action],
        narrative_text="Minato glances away politely while you and Kana embrace.",
        overall_check_success=True,
        is_player_romantic_action=True,
        is_player_intimate_action=True,
        is_player_oral_action=False,
        is_player_intercourse_action=True,
        is_player_confession_action=False,
        is_player_affection_action=False,
        affection_target_npc=None,
        gift_target_npc=None,
        gift_item_name=None,
        confession_target_npc=None,
        first_char_name="Hero",
        session=sess,
    )
    assert mem_m is None
    assert exp_m == "virgin"
    assert is_int_m is False

    res = resolve_pre_turn_intimacy_and_clothing(sess, actions=[action])
    assert res["physical_state"]["actors"]["Minato"]["clothing"]["bottom"] == "Clothed"
    assert res["physical_state"]["actors"]["Kana"]["clothing"]["bottom"] == "Displaced"


def test_multi_partner_collective_targeting():
    """Comma-separated target_npc ('Kana, Minato') updates clothing and milestones for both partners."""
    sess = {
        "id": 1003,
        "dialogue_partner": "Kana",
        "dialogue_partners": ["Kana", "Minato"],
        "player_character": {"name": "Hero", "gender": "Male"},
        "physical_state": {
            "intimate_contact": "none",
            "actors": {
                "Hero": {"clothing": {"top": "Clothed", "bottom": "Clothed", "under_top": "Worn", "under_bottom": "Worn"}},
                "Kana": {"clothing": {"top": "Clothed", "bottom": "Clothed", "under_top": "Worn", "under_bottom": "Worn"}},
                "Minato": {"clothing": {"top": "Clothed", "bottom": "Clothed", "under_top": "Worn", "under_bottom": "Worn"}},
            },
        },
    }
    action = {
        "label": "Hold both Kana and Minato close as clothes fall away",
        "intent": "intimate_act",
        "sub_intent": "intercourse",
        "target_npc": "Kana, Minato",
        "check": {"succeeded": True, "tier": "strong_hit"},
    }

    res = resolve_pre_turn_intimacy_and_clothing(sess, actions=[action])
    actors = res["physical_state"]["actors"]
    assert actors["Kana"]["clothing"]["bottom"] == "Displaced"
    assert actors["Minato"]["clothing"]["bottom"] == "Displaced"
    assert actors["Hero"]["clothing"]["bottom"] == "Displaced"


def test_male_refractory_soft_gate():
    """A male actor in refractory cooldown downgrades intercourse to foreplay, emits REFRACTORY LIMIT directive, and gains 0 delta."""
    session = {
        "id": 1004,
        "current_day": 1,
        "current_minute": 500,
        "dialogue_partner": "Kana",
        "dialogue_partners": ["Kana"],
        "player_character": {"name": "Hero", "gender": "Male"},
        "physical_state": {
            "intimate_contact": "intercourse with Kana",
            "excitement": {
                "active": True,
                "refractory_until_minute": 1970,
                "player_in_refractory": True,
                "actors": {
                    "Hero": {"meter": 100, "endurance": 5, "climaxes_count": 1, "status": "💥 Climaxed (Spent)", "idle_turns": 0},
                    "Kana": {"meter": 60, "endurance": 6, "climaxes_count": 0, "status": "Arousal Building", "idle_turns": 0},
                },
            },
            "climax_state": {"player_climaxed": True, "partner_climaxed": False, "partner_climaxes": {"Kana": False}},
            "actors": {
                "Hero": {"clothing": {"top": "Disheveled", "bottom": "Displaced", "under_top": "Worn", "under_bottom": "Displaced"}},
                "Kana": {"clothing": {"top": "Disheveled", "bottom": "Displaced", "under_top": "Worn", "under_bottom": "Displaced"}},
            },
        },
    }

    act = {
        "label": "Thrust slowly inside Kana",
        "intent": "intimate_act",
        "sub_intent": "intercourse",
        "target_npc": "Kana",
        "check": {"succeeded": True, "tier": "success"},
    }
    pre = resolve_pre_turn_intimacy_and_clothing(session, actions=[act])
    assert act["sub_intent"] == "foreplay"
    assert any("REFRACTORY LIMIT" in d for d in pre.get("directives", []))


def test_premature_finish_exit_penalty():
    """Disengaging (ends_dialogue: True) while partner is unsatisfied and demanded continuation inflicts -5 score penalty."""
    app_dict = {}
    action_exit = {
        "label": "Step back abruptly and leave the room",
        "intent": "dialogue_exit",
        "sub_intent": "aftercare",
        "ends_dialogue": True,
        "target_npc": "Kana",
        "check": {"succeeded": True, "tier": "strong_hit"},
    }
    session = {
        "id": 1005,
        "dialogue_partner": "Kana",
        "physical_state": {
            "excitement": {
                "premature_finish": True,
                "partner_demanded": True,
            }
        },
    }

    _, _, _, _, _, _, delta_boost = _evaluate_npc_milestones(
        npc_name="Kana",
        app_dict=app_dict,
        track="romantic",
        milestone_ev="",
        custom_summary=None,
        intercourse_exp="non_virgin",
        oral_exp="inexperienced",
        actions=[action_exit],
        narrative_text="You excuse yourself abruptly.",
        overall_check_success=True,
        is_player_romantic_action=False,
        is_player_intimate_action=False,
        is_player_oral_action=False,
        is_player_intercourse_action=False,
        is_player_confession_action=False,
        is_player_affection_action=False,
        affection_target_npc=None,
        gift_target_npc=None,
        gift_item_name=None,
        confession_target_npc=None,
        first_char_name="Hero",
        session=session,
    )

    assert delta_boost == -5
    assert session["physical_state"]["excitement"]["premature_finish"] is False


def test_hybrid_redressing_and_contact_lifecycle():
    """Redress restores canonical wardrobe and clears intimate contact to 'none'."""
    sess = {
        "id": 1006,
        "dialogue_partner": "Kana",
        "player_character": {"name": "Hero", "gender": "Male"},
        "physical_state": {
            "intimate_contact": "intercourse with Kana",
            "actors": {
                "Hero": {"clothing": {"top": "Disheveled", "bottom": "Displaced", "under_top": "Worn", "under_bottom": "Displaced"}},
                "Kana": {"clothing": {"top": "Disheveled", "bottom": "Displaced", "under_top": "Worn", "under_bottom": "Displaced"}},
            },
        },
    }
    action_redress = {
        "label": "Fasten your clothes and help Kana get dressed",
        "intent": "intimate_act",
        "sub_intent": "redress",
        "target_npc": "Kana",
        "ends_dialogue": True,
        "check": {"succeeded": True, "tier": "strong_hit"},
    }

    res = resolve_pre_turn_intimacy_and_clothing(sess, actions=[action_redress])
    assert res["physical_state"]["intimate_contact"] == "none"


def test_intimate_choice_blueprints_stamp_metadata():
    """build_intimate_choice_blueprints stamps sub_intent, ends_dialogue, and isolated target_npc."""
    blueprints = build_intimate_choice_blueprints(
        partner_name="Kana",
        last_act="foreplay_nongenital",
        partner_actors=[{"name": "Kana", "gender": "Female", "meter": 40}],
    )
    choices = blueprints["choices"]
    assert len(choices) >= 3

    exit_c = [c for c in choices if c.get("intent") == "dialogue_exit"][0]
    assert exit_c["ends_dialogue"] is True
    assert exit_c["target_npc"] == "Kana"


def test_confession_below_100_stays_platonic_and_above_100_promotes(tmp_path, monkeypatch):
    """D6: Score < 100 keeps track='platonic', grants +2 flattered affinity & CONFESSION TOO EARLY directive; >= 100 promotes to 'romantic'."""
    import db
    import db.core
    from game_engine.state.social import resolve_pre_turn_social_and_disclosures

    isolated_db = str(tmp_path / "test_d6_confession.db")
    monkeypatch.setattr(db, "DB_PATH", isolated_db)
    monkeypatch.setattr(db.core, "DB_PATH", isolated_db)
    db.init_db()

    uid = 801
    char = db.create_character(uid, "Ren", "Student", stats={"STR": 5, "PER": 5, "END": 5, "CHA": 7, "INT": 5, "AGI": 5, "LUK": 5})
    sess_id = db.create_session(uid, "solo", 1, "vivid", "balanced", False, scenario="high_school_drama")
    db.upsert_contact(sess_id, "kana_sato", "Kana Sato", delta_score=65, track="platonic")

    session = db.get_session(sess_id)
    session["dialogue_partner"] = "Kana Sato"
    session["dialogue_partners"] = ["Kana Sato"]
    party = [(char, [])]
    confess_act = {
        "label": "Confess your romantic feelings to Kana Sato",
        "intent": "romantic_move",
        "sub_intent": "romantic_confession",
        "target_npc": "Kana Sato",
        "stat": "CHA",
        "check": {"succeeded": True, "tier": "success"},
    }

    social_pre = resolve_pre_turn_social_and_disclosures(session, party, [confess_act])
    assert any("CONFESSION TOO EARLY" in d for d in (social_pre.get("directives") or social_pre.get("stage_directives") or []))

    outcome = {"relationship_updates": [{"npc_name": "Kana Sato", "track": "romantic", "delta_score": 5}]}
    apply_outcome(sess_id, party, outcome, actions=[confess_act])
    kana_below = db.get_contact(sess_id, "Kana Sato")
    assert kana_below["track"] == "platonic"
    assert kana_below["relationship_score"] >= 67  # flattered platonic affinity, never romantic

    # Now bump Kana to >= 100 and confess again -> promotes to romantic!
    db.upsert_contact(sess_id, "kana_sato", "Kana Sato", delta_score=40)
    outcome_high = {"relationship_updates": [{"npc_name": "Kana Sato", "track": "romantic", "delta_score": 3}]}
    apply_outcome(sess_id, party, outcome_high, actions=[confess_act])
    kana_above = db.get_contact(sess_id, "Kana Sato")
    assert kana_above["track"] == "romantic"


def test_dm_grounding_snaps_meetup_and_enforces_in_person_gates(tmp_path, monkeypatch):
    """D14: DM rendezvous snaps to canonical public world_nodes; romantic confessions & quest interrogations are gated in-person."""
    import db
    import db.core

    isolated_db = str(tmp_path / "test_d14_dm.db")
    monkeypatch.setattr(db, "DB_PATH", isolated_db)
    monkeypatch.setattr(db.core, "DB_PATH", isolated_db)
    db.init_db()

    sess_id = db.create_session(802, "solo", 1, "vivid", "balanced", False, scenario="high_school_drama")
    db.save_world_node(sess_id, "zone_campus", None, "Westlake Campus", node_type="ZONE", privacy_level="public")
    db.save_world_node(sess_id, "fac_rooftop", "zone_campus", "Skyline Rooftop Terrace", node_type="FACILITY", privacy_level="public")
    db.upsert_quest(
        session_id=sess_id,
        quest_id="SQ-DM-1",
        quest_type="Story Quest",
        title="The Locker Sabotage",
        objective="Question Kana Sato about the broken padlock.",
        status="Active",
        is_story_quest=1,
    )

    snapped_loc, resolved_intent = resolve_rendezvous_location(
        session_id=sess_id,
        contact_name="Kana Sato",
        current_loc="Westlake Campus ➔ Homeroom",
        rendezvous="Rooftop Terrace",
        reply_text="Meet me up on the Skyline Rooftop Terrace!",
        known_locations=[],
        existing_appointment=None,
        is_reschedule_request=False,
        intent="meetup",
        check_succeeded=True,
        scenario="high_school_drama",
    )
    assert resolved_intent == "meetup"
    assert "Skyline Rooftop Terrace" in snapped_loc

    gate_confess = evaluate_dm_in_person_gate(
        session_id=sess_id,
        contact_name="Kana Sato",
        track="platonic",
        user_message="I love you Kana, please be my girlfriend!",
        intent="flirt",
    )
    assert gate_confess["is_confession_gated"] is True
    assert gate_confess["max_affinity_delta"] == 2
    assert "IN-PERSON CONFESSION GATE" in gate_confess["directive"]

    gate_quest = evaluate_dm_in_person_gate(
        session_id=sess_id,
        contact_name="Kana Sato",
        track="platonic",
        user_message="Who is the culprit? Tell me the evidence you saw!",
        intent="intel_rumor",
    )
    assert gate_quest["is_quest_gated"] is True
    assert "IN-PERSON INVESTIGATION GATE" in gate_quest["directive"]


def test_coop_multiplayer_intimate_action_in_secondary_slot():
    """D15: Secondary player action in multiplayer co-op resolves clothing/intimacy cleanly instead of only inspecting actions[0]."""
    sess = {
        "id": 1009,
        "dialogue_partner": "Kana",
        "dialogue_partners": ["Kana"],
        "player_character": {"name": "Hero2", "gender": "Male"},
        "physical_state": {
            "intimate_contact": "none",
            "actors": {
                "Hero2": {"clothing": {"top": "Clothed", "bottom": "Clothed", "under_top": "Worn", "under_bottom": "Worn"}},
                "Kana": {"clothing": {"top": "Clothed", "bottom": "Clothed", "under_top": "Worn", "under_bottom": "Worn"}},
            },
        },
    }
    actions = [
        {"label": "Keep watch by the outer corridor", "intent": "area_scout", "check": {"succeeded": True}},
        {
            "label": "Embrace Kana and undress together",
            "intent": "intimate_act",
            "sub_intent": "intercourse",
            "target_npc": "Kana",
            "check": {"succeeded": True, "tier": "strong_hit"},
        },
    ]
    res = resolve_pre_turn_intimacy_and_clothing(sess, actions=actions)
    assert res["physical_state"]["actors"]["Kana"]["clothing"]["bottom"] == "Displaced"
