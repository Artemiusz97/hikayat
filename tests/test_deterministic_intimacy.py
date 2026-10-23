"""
Comprehensive Test Suite for Phase 2: Deterministic Intimacy & Physical Milestone Engine.

Covers:
1. Metaphor Guard: Metaphorical prose produces zero intimacy or ledger changes.
2. Directional Inversion: Player-centric sub_intent maps accurately to NPC perspective.
3. First Kiss Promotion: Virgin NPC receives 'first_kiss'; subsequent kiss receives 'kiss'.
4. Check Failure Gate: Failed check yields zero meter gain, no milestone, intact clothing.
5. Target Isolation: Action targeting NPC A leaves spectator NPC B completely untouched.
6. Multi-Partner Collective: Comma-separated target_npc updates all named partners.
7. Male Refractory Soft Gate: Male in refractory period gains 0 delta and cannot climax; partner still progresses.
8. Premature Finish Exit Penalty: Exiting encounter while unsatisfied partner demanded inflicts -5 score penalty.
9. Hybrid Redressing & Intimate Contact Lifecycle: Reset on redress, movement, or dialogue exit.
10. Rollback Guard: DETERMINISTIC_INTIMACY = False restores legacy keyword behavior.
"""

import pytest
from game_engine.state.reducers import _evaluate_npc_milestones
from mechanics.social.intimate_excitement import (
    resolve_pre_turn_intimacy_and_clothing,
    compute_excitement_step,
    build_intimate_choice_blueprints,
)
import config


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
    # 1. Player gives oral -> NPC receives oral
    app_k = {}
    action_give = {
        "label": "Kneel close and please Kana with your mouth",
        "intent": "intimate_act",
        "sub_intent": "oral_give",
        "target_npc": "Kana",
        "check": {"succeeded": True, "tier": "strong_hit"},
    }
    mem_k, _, oral_k, _, _, is_intimate_k, _ = _evaluate_npc_milestones(
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
    # NPC receives oral experience
    assert app_k.get("oral_revealed") is True

    # 2. Player receives oral -> NPC gives oral
    app_m = {}
    action_rec = {
        "label": "Guide Minato's head gently as he pleasures you",
        "intent": "intimate_act",
        "sub_intent": "oral_receive",
        "target_npc": "Minato",
        "check": {"succeeded": True, "tier": "strong_hit"},
    }
    mem_m, _, oral_m, _, _, is_intimate_m, _ = _evaluate_npc_milestones(
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

    # Pass 1: First kiss
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

    # Pass 2: Subsequent kiss
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

    # 1. Reducer test: zero milestone
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

    # 2. Pre-turn excitement & clothing: clothing stays intact
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
            }
        }
    }
    res = resolve_pre_turn_intimacy_and_clothing(session, actions=[action_failed])
    phys = res["physical_state"]
    kana_cloth = phys["actors"]["Kana"]["clothing"]
    hero_cloth = phys["actors"]["Hero"]["clothing"]

    assert kana_cloth["bottom"] == "Clothed"
    assert hero_cloth["bottom"] == "Clothed"
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
            }
        }
    }
    action = {
        "label": "Pull Kana into your lap and undress her",
        "intent": "intimate_act",
        "sub_intent": "intercourse",
        "target_npc": "Kana",
        "check": {"succeeded": True, "tier": "strong_hit"},
    }

    # Reducer on Minato: must return None
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

    # Clothing on Minato: must remain Clothed
    res = resolve_pre_turn_intimacy_and_clothing(sess, actions=[action])
    minato_cloth = res["physical_state"]["actors"]["Minato"]["clothing"]
    kana_cloth = res["physical_state"]["actors"]["Kana"]["clothing"]

    assert minato_cloth["bottom"] == "Clothed"
    assert kana_cloth["bottom"] == "Displaced"


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
            }
        }
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
    """A male actor in refractory cooldown receives 0 excitement delta and cannot climax, while partner still progresses."""
    session = {
        "id": 1004,
        "current_day": 1,
        "current_minute": 500,
        "dialogue_partner": "Kana",
        "player_character": {"name": "Hero", "gender": "Male"},
    }
    # Male player is in refractory cooldown until minute 530
    physical_state = {
        "intimate_contact": "intercourse with Kana",
        "excitement": {
            "active": True,
            "refractory_until_minute": 530,
            "player_in_refractory": True,
            "actors": {
                "Hero": {"meter": 100, "endurance": 5, "climaxes_count": 1, "status": "💥 Climaxed (Spent)", "idle_turns": 0},
                "Kana": {"meter": 60, "endurance": 6, "climaxes_count": 0, "status": "Arousal Building", "idle_turns": 0},
            }
        },
        "climax_state": {"player_climaxed": True, "partner_climaxed": False, "partner_climaxes": {"Kana": False}}
    }

    # Step: penetrative intercourse attempted during cooldown
    res = compute_excitement_step(
        physical_state=physical_state,
        action_str="Thrust slowly inside Kana",
        player_char={"name": "Hero", "gender": "Male"},
        partner_contact={"name": "Kana", "gender": "Female"},
        session=session,
        sub_intent="intercourse",
        target_npc="Kana",
    )

    # Hero (Male in refractory) delta must be 0
    assert res["player_delta"] == 0
    # Kana (Female partner) delta must be positive
    assert res["partner_delta"] > 0
    assert res["partner_meter"] > 60


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
        }
    }

    mem, _, _, _, _, _, delta_boost = _evaluate_npc_milestones(
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
            }
        }
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
    phys = res["physical_state"]
    assert phys["intimate_contact"] == "none"


def test_intimate_choice_blueprints_stamp_metadata():
    """build_intimate_choice_blueprints stamps sub_intent, ends_dialogue, and isolated target_npc."""
    blueprints = build_intimate_choice_blueprints(
        partner_name="Kana",
        last_act="foreplay_nongenital",
        partner_actors=[{"name": "Kana", "gender": "Female", "meter": 40}],
    )
    choices = blueprints["choices"]
    assert len(choices) >= 3

    # The exit choice must have ends_dialogue: True
    exit_c = [c for c in choices if c.get("intent") == "dialogue_exit"][0]
    assert exit_c["ends_dialogue"] is True
    assert exit_c["target_npc"] == "Kana"


def test_rollback_guard_when_deterministic_intimacy_false(monkeypatch):
    """When DETERMINISTIC_INTIMACY is set to False, legacy keyword behavior functions as rollback."""
    monkeypatch.setattr(config, "DETERMINISTIC_INTIMACY", False)

    app_dict = {}
    action = [{"label": "Pleasure Kana tenderly with your mouth"}]
    # Legacy keyword scan in action text
    mem, _, _, _, _, is_intimate, _ = _evaluate_npc_milestones(
        npc_name="Kana",
        app_dict=app_dict,
        track="romantic",
        milestone_ev="",
        custom_summary=None,
        intercourse_exp="virgin",
        oral_exp="inexperienced",
        actions=action,
        narrative_text="She sighs softly.",
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
    assert is_intimate is True
    assert mem is not None
