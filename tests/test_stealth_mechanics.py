"""
Unit Tests for Stealth & Infiltration Mechanics.
"""
import pytest
import db
import db.core


@pytest.fixture(autouse=True)
def _isolate_stealth_test_db(tmp_path, monkeypatch):
    """Ensure no test in test_stealth_mechanics ever mutates live hikayat.db (AGENTS.md §3)."""
    test_db = str(tmp_path / "test_stealth_isolated.db")
    monkeypatch.setattr(db, "DB_PATH", test_db)
    monkeypatch.setattr(db.core, "DB_PATH", test_db)
    db.init_db()
    yield
from mechanics.stealth.alert_tracker import (
    ALERT_UNAWARE,
    ALERT_SUSPICIOUS,
    ALERT_SEARCHING,
    ALERT_DETECTED,
    get_alert_stage,
    accumulate_detection,
    apply_natural_decay,
    apply_distraction,
    get_alert_badge_data
)
from mechanics.stealth.formulas import (
    calculate_armor_noise,
    calculate_companion_noise_penalty,
    calculate_lighting_modifier,
    calculate_opposed_stealth_odds,
    resolve_opposed_stealth_check
)
from mechanics.stealth.core import (
    init_stealth_state,
    get_session_stealth_state,
    toggle_stealth_stance,
    break_stealth,
    apply_stealth_distraction,
    resolve_stealth_action,
    format_stealth_truth_directive
)


def test_alert_stage_thresholds():
    assert get_alert_stage(0) == ALERT_UNAWARE
    assert get_alert_stage(25) == ALERT_UNAWARE
    assert get_alert_stage(26) == ALERT_SUSPICIOUS
    assert get_alert_stage(60) == ALERT_SUSPICIOUS
    assert get_alert_stage(61) == ALERT_SEARCHING
    assert get_alert_stage(99) == ALERT_SEARCHING
    assert get_alert_stage(100) == ALERT_DETECTED


def test_detection_accumulation_and_decay():
    # Success adds 0
    m1, s1 = accumulate_detection(10, "success")
    assert m1 == 10
    assert s1 == ALERT_UNAWARE

    # Failure adds 25+
    m2, s2 = accumulate_detection(10, "fail")
    assert m2 >= 35
    assert s2 == ALERT_SUSPICIOUS

    # Critical failure adds 45+
    m3, s3 = accumulate_detection(20, "crit_fail")
    assert m3 >= 65
    assert s3 == ALERT_SEARCHING

    # Natural decay drops meter
    decayed, stage = apply_natural_decay(50, quiet_turns=2)
    assert decayed == 30
    assert stage == ALERT_SUSPICIOUS

    # Distraction drops meter by 30
    distracted, d_stage = apply_distraction(50, reduction=30)
    assert distracted == 20
    assert d_stage == ALERT_UNAWARE


def test_armor_noise_and_gear_bonus():
    heavy_gear = [
        {"name": "Plate Cuirass", "slot": "Armor", "tags": {"weight": ["heavy", "plate"]}},
        {"name": "Iron Boots", "slot": "Shoes", "tags": {"weight": ["heavy"]}}
    ]
    noise_pen, stealth_bon = calculate_armor_noise(heavy_gear)
    assert noise_pen >= 25
    assert stealth_bon == 0

    shadow_gear = [
        {"name": "Shadow Silk Gambeson", "slot": "Armor", "tags": {"features": ["stealth", "silent_step"]}},
        {"name": "Muffled Stalker Boots", "slot": "Shoes", "tags": {"features": ["silent_step"]}}
    ]
    s_noise, s_bonus = calculate_armor_noise(shadow_gear)
    assert s_noise == 0
    assert s_bonus >= 15


def test_lighting_modifier():
    # Midnight (0 or 1440 min)
    dark_mod = calculate_lighting_modifier(0)
    assert dark_mod == 20

    # Noon (720 min)
    noon_mod = calculate_lighting_modifier(720)
    assert noon_mod == -15


def test_companion_noise_penalty():
    solo_party = [{"name": "Rogue", "stats": {"AGI": 8}}]
    assert calculate_companion_noise_penalty(solo_party) == 0

    clunky_party = [
        {"name": "Rogue", "stats": {"AGI": 8}},
        {"name": "Sir Galahad", "class": "Paladin", "description": "A heavy tank knight", "stats": {"AGI": 2}}
    ]
    assert calculate_companion_noise_penalty(clunky_party) >= 10


def test_opposed_stealth_odds():
    high_stealth_actor = {"AGI": 10, "LUK": 6}
    low_per_sentry = 2
    odds = calculate_opposed_stealth_odds(
        actor_stats=high_stealth_actor,
        target_per=low_per_sentry,
        current_minute=0  # Midnight
    )
    assert odds["success_chance"] >= 80

    clumsy_actor = {"AGI": 2, "LUK": 2}
    eagle_eyed_sentry = 8
    low_odds = calculate_opposed_stealth_odds(
        actor_stats=clumsy_actor,
        target_per=eagle_eyed_sentry,
        current_minute=720  # Noon
    )
    assert low_odds["success_chance"] <= 25


def test_invisibility_sensory_separation():
    # Invisible actor with heavy armor
    heavy_gear = [{"name": "Tarnished Plate", "slot": "Armor", "tags": ["heavy"]}]
    odds_vis = calculate_opposed_stealth_odds(
        actor_stats={"AGI": 6, "LUK": 3},
        target_per=4,
        equipped_items=heavy_gear,
        is_invisible=True
    )
    # Optical concealment is high
    assert odds_vis["optical_concealment"] >= 40
    # But armor noise is still deducted
    assert odds_vis["armor_noise"] >= 25


def test_session_stealth_lifecycle():
    session = {"id": 1, "scenario": "fantasy"}
    st = get_session_stealth_state(session)
    assert st["is_hidden"] is False

    toggle_stealth_stance(session, True)
    assert session["stealth_state"]["is_hidden"] is True

    apply_stealth_distraction(session, 20)
    assert session["stealth_state"]["last_alert_cause"] == "distraction_deployed"

    break_stealth(session, reason="shouted_alarm")
    assert session["stealth_state"]["is_hidden"] is False
    assert session["stealth_state"]["last_alert_cause"] == "shouted_alarm"


def test_resolve_stealth_action_and_escalation():
    session = {"id": 1, "scenario": "fantasy"}
    actor = {"name": "Infiltrator", "stats": {"AGI": 8, "LUK": 4}}
    action = {"label": "Slip past the door", "action_type": "creep"}

    # Always success mode
    res = resolve_stealth_action(
        session=session,
        actor_char=actor,
        action_data=action,
        check_mode="always_success"
    )
    assert res["check"].succeeded is True
    assert res["stealth_state"]["detection_meter"] == 0
    assert res["trigger_combat"] is False

    # Force 100% detection escalation
    session["stealth_state"]["detection_meter"] = 90
    res_fail = resolve_stealth_action(
        session=session,
        actor_char=actor,
        action_data=action,
        check_mode="always_crit_fail"
    )
    assert res_fail["stealth_state"]["detection_meter"] == 100
    assert res_fail["stealth_state"]["alert_level"] == ALERT_DETECTED
    assert res_fail["stealth_state"]["is_hidden"] is False
    assert res_fail["trigger_combat"] is True


def test_badge_and_truth_directive():
    badge = get_alert_badge_data(45, is_hidden=True)
    assert badge["stage"] == ALERT_SUSPICIOUS
    assert "SUSPICIOUS" in badge["label"]

    revealed_badge = get_alert_badge_data(45, is_hidden=False)
    assert revealed_badge["stage"] == "revealed"

    session = {
        "stealth_state": {
            "is_hidden": True,
            "alert_level": ALERT_SUSPICIOUS,
            "detection_meter": 45
        }
    }
    directive = format_stealth_truth_directive(session)
    assert "[MANDATORY STEALTH & CONCEALMENT DIRECTIVE]" in directive
    assert "SUSPICIOUS" in directive
    assert "45/100" not in directive
    assert "NEVER mention" in directive


import pytest
import asyncio
import db
from services.turn_service import TurnService
from game_engine.turn.prompts import _build_player_actions_text


@pytest.mark.asyncio
async def test_prepare_and_roll_action_stealth_flow():
    # Setup test character and session in DB
    user_id = 888123
    db.create_character(
        user_id=user_id,
        name="ShadowScout",
        char_class="Rogue",
        stats={"STR": 4, "PER": 5, "END": 4, "CHA": 4, "INT": 5, "AGI": 8, "LUK": 5},
        gold=100
    )
    session_id = db.create_session(host_user_id=user_id, mode="solo", capacity=1, verbosity="normal", dialogue_mode="balanced", image_gen_enabled=False)

    # 1. Execute stealth movement
    raw_pick = {
        "custom_action_text": "I sneak past the patrolling sentry into the courtyard.",
        "is_stealth": True,
        "stance": "stealth"
    }
    action = await TurnService.prepare_and_roll_action(
        session_id=session_id,
        user_id=user_id,
        raw_pick=raw_pick
    )
    assert action["is_stealth"] is True
    assert action["stance"] == "stealth"
    assert action.get("stealth_outcome") is not None
    assert action.get("check") is not None

    sess = db.get_session(session_id)
    assert sess.get("stealth_state") is not None
    assert sess["stealth_state"]["is_hidden"] is True

    # 2. Deploy distraction
    distract_pick = {
        "custom_action_text": "I throw a small stone to create a noise distraction and divert attention.",
        "intent": "stealth_covert",
        "is_stealth": True
    }
    action2 = await TurnService.prepare_and_roll_action(
        session_id=session_id,
        user_id=user_id,
        raw_pick=distract_pick
    )
    assert action2["is_stealth"] is True

    # 3. Prompt directive generation
    directive_text = _build_player_actions_text([action], session=sess)
    assert "[MANDATORY STEALTH & CONCEALMENT DIRECTIVE]" in directive_text



from mechanics.combat.formulas import calculate_tactical_damage
from mechanics.narrative.choice_generator import generate_categorized_combat_actions
from mechanics.combat.core import precompute_combat_turn


def test_tactical_damage_ambush_and_backstab():
    attacker_attrs = {"atk": 40, "combat_turn": 1, "is_ambush": True}
    defender_attrs = {"def": 10, "base_dt": 4, "block_chance": 100}
    res = calculate_tactical_damage(
        attacker_attrs=attacker_attrs,
        defender_attrs=defender_attrs,
        weapon_meta={"name": "Dagger", "multiplier": 1.0},
        armor_meta={"name": "Leather", "base_dt": 4},
        tier="success",
        stance="stealth"
    )
    assert res["ambush_strike"] is True or res.get("flanking_backstab") is True
    assert res["blocked"] is False
    assert res["ap_ratio"] >= 0.50
    assert res["damage"] > 0


def test_choice_generator_vanish_and_backstab():
    # Regular character
    char = {"name": "Rogue", "stats": {"AGI": 8, "LUK": 5, "STR": 4, "PER": 5, "END": 4, "INT": 4, "CHA": 4}}
    monster = {"name": "Orc", "stats": {"PER": 3, "AGI": 3, "STR": 6}}
    choices = generate_categorized_combat_actions([(char, [])], monster)

    # Vanish tactic should be present
    vanish_tactic = next((t for t in choices["tactics"] if t["choice_type"] == "STEALTH_VANISH"), None)
    assert vanish_tactic is not None
    assert "Vanish into Shadows" in vanish_tactic["label"]

    # When character is vanished, Flanking Backstab should be the top attack
    char_vanished = {
        "name": "Rogue",
        "stats": {"AGI": 8, "LUK": 5, "STR": 4, "PER": 5, "END": 4, "INT": 4, "CHA": 4},
        "status_effects": ["Hidden in Shadows [1 turn]"]
    }
    choices_vanished = generate_categorized_combat_actions([(char_vanished, [])], monster)
    top_attack = choices_vanished["attacks"][0]
    assert "Flanking Backstab" in top_attack["label"]
    assert top_attack["stance"] == "stealth"


def test_combat_core_vanish_and_surprise_round():
    session = {
        "id": 9991,
        "combat_turn": 1,
        "is_ambush": True,
        "scenario": "fantasy"
    }
    player = {
        "user_id": 9991,
        "name": "Ghost",
        "hp": 100,
        "max_hp": 100,
        "stats": {"AGI": 10, "LUK": 6, "STR": 5, "PER": 5, "END": 5, "INT": 5, "CHA": 5}
    }
    companion = {
        "user_id": 9992,
        "name": "ShieldKnight",
        "hp": 100,
        "max_hp": 100,
        "stats": {"STR": 8, "END": 8, "AGI": 2}
    }
    party = [(player, []), (companion, [])]
    enemies = [{"name": "Goblin Sentry", "hp": 50, "max_hp": 50, "stats": {"PER": 2, "STR": 3}}]
    session["nearby_enemies"] = enemies

    # 1. Turn 1 Ambush: Enemies should be Surprised and stunned!
    actions = [{"choice_type": "MELEE_SLASHING_PIERCING", "label": "Attack", "stat": "AGI"}]
    turn1_res = precompute_combat_turn(session, party, actions)
    assert any("Surprise Round" in log for log in turn1_res["combat_log"])
    assert any("Surprised" in log for log in turn1_res["combat_log"])

    # 2. Turn 2: Vanish into Shadows
    session["combat_turn"] = 2
    session["is_ambush"] = False
    vanish_action = [{"choice_type": "STEALTH_VANISH", "label": "Vanish into Shadows", "stat": "AGI", "tier": "success"}]
    turn2_res = precompute_combat_turn(session, party, vanish_action)
    assert any("vanished from enemy sight" in log for log in turn2_res["combat_log"])
    assert session.get("stealth_state", {}).get("combat_vanished") is True

    # 3. Enemy attacks: Because player is vanished, enemy must target the companion!
    target_names = [a["target_name"] for a in turn2_res.get("enemy_attacks", []) if a.get("target_name")]
    if target_names:
        assert all(t != "Ghost" for t in target_names)


@pytest.mark.asyncio
async def test_discord_choice_view_stealth_button(monkeypatch):
    import db
    from cogs.adventure.views.choices import ChoiceView
    from unittest.mock import AsyncMock, MagicMock

    user_id = 12345
    session_id = 8888
    session_data = {
        "id": session_id,
        "status": "active",
        "turn_user_id": user_id,
        "turn_order": [user_id],
        "scenario": "fantasy",
        "stealth_state": {
            "is_hidden": False,
            "detection_meter": 0,
            "alert_level": "unaware"
        }
    }
    char_data = {
        "id": 1,
        "user_id": user_id,
        "name": "Shadow",
        "agi_": 8
    }

    monkeypatch.setattr(db, "get_session", lambda sid: dict(session_data) if sid == session_id else None)
    monkeypatch.setattr(db, "get_character", lambda uid: dict(char_data) if uid == user_id else None)
    monkeypatch.setattr(db, "get_settings", lambda uid: {})
    def fake_update_session(sid, **kwargs):
        session_data.update(kwargs)
    monkeypatch.setattr(db, "update_session", fake_update_session)

    mock_cog = MagicMock()
    choices = [{"label": "Sneak ahead", "stat": "AGI", "requirement": 5}]
    view = ChoiceView(mock_cog, session_id, user_id, choices, char_data)

    assert hasattr(view, "stealth_btn")
    assert view.stealth_btn.label == "Stealth"
    assert str(view.stealth_btn.emoji) == "🥷"

    # Simulate interaction clicking the button
    mock_interaction = MagicMock()
    mock_interaction.user.id = user_id
    mock_interaction.response.is_done.return_value = False
    mock_interaction.response.edit_message = AsyncMock()
    mock_interaction.followup.send = AsyncMock()

    await view._stealth_callback(mock_interaction)

    assert session_data["stealth_state"]["is_hidden"] is True
    assert view.stealth_btn.label == "Sneaking (0%)"
    mock_interaction.response.edit_message.assert_awaited_once_with(view=view)
    mock_interaction.followup.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_discord_sync_choice_view_stealth_button(monkeypatch):
    import db
    from cogs.adventure.views.choices import SyncChoiceView
    from unittest.mock import AsyncMock, MagicMock

    user_id = 12345
    session_id = 8889
    session_data = {
        "id": session_id,
        "status": "active",
        "turn_order": [user_id],
        "scenario": "fantasy",
        "pending_picks": {},
        "stealth_state": {
            "is_hidden": False,
            "detection_meter": 20,
            "alert_level": "unaware"
        }
    }
    char_data = {"id": 1, "user_id": user_id, "name": "Shadow"}

    monkeypatch.setattr(db, "get_session", lambda sid: dict(session_data) if sid == session_id else None)
    monkeypatch.setattr(db, "get_character", lambda uid: dict(char_data) if uid == user_id else None)
    monkeypatch.setattr(db, "get_settings", lambda uid: {})
    def fake_update_session(sid, **kwargs):
        session_data.update(kwargs)
    monkeypatch.setattr(db, "update_session", fake_update_session)

    mock_cog = MagicMock()
    choices = [{"label": "Sneak ahead", "stat": "AGI", "requirement": 5}]
    view = SyncChoiceView(mock_cog, session_id, [user_id], choices, party=[(char_data, [])])

    assert hasattr(view, "stealth_btn")
    assert view.stealth_btn.label == "Stealth"

    mock_interaction = MagicMock()
    mock_interaction.user.id = user_id
    mock_interaction.response.is_done.return_value = False
    mock_interaction.response.edit_message = AsyncMock()
    mock_interaction.followup.send = AsyncMock()

    await view._stealth_callback(mock_interaction)

    assert session_data["stealth_state"]["is_hidden"] is True
    assert view.stealth_btn.label == "Sneaking (20%)"


def test_party_vitals_text_stealth_display(monkeypatch):
    import db
    from cogs.adventure.embeds import _party_vitals_text

    user_id = 555
    char_data = {
        "id": 1,
        "user_id": user_id,
        "name": "Kage",
        "level": 3,
        "hp": 90,
        "max_hp": 100,
        "mp": 40,
        "max_mp": 50,
        "status_effects": ["Blessed"]
    }
    monkeypatch.setattr(db, "get_character", lambda uid: dict(char_data) if uid == user_id else None)
    monkeypatch.setattr(db, "current_turn_user_id", lambda s: user_id)

    # 1. Hidden stealth state
    session_stealth = {
        "turn_order": [user_id],
        "scenario": "fantasy",
        "stealth_state": {
            "is_hidden": True,
            "detection_meter": 42
        }
    }
    vitals_text = _party_vitals_text(session_stealth)
    assert "🥷 Sneaking (42%)" in vitals_text
    assert "Blessed" in vitals_text

    # 2. Combat vanished state
    session_vanished = {
        "turn_order": [user_id],
        "scenario": "fantasy",
        "stealth_state": {
            "is_hidden": True,
            "combat_vanished": True,
            "detection_meter": 10
        }
    }
    vitals_text_vanished = _party_vitals_text(session_vanished)
    assert "💨 Vanished" in vitals_text_vanished


@pytest.mark.asyncio
async def test_distraction_and_auto_break_via_turn_service(monkeypatch):
    import db
    from services.turn_service import TurnService

    session_id = 7711
    user_id = 3322
    session_data = {
        "id": session_id,
        "status": "active",
        "turn_user_id": user_id,
        "scenario": "fantasy",
        "history": [],
        "current_npcs": [],
        "nearby_enemies": [],
        "stealth_state": {
            "is_hidden": True,
            "detection_meter": 60,
            "alert_level": "searching"
        }
    }

    import game_engine
    from unittest.mock import AsyncMock
    monkeypatch.setattr(game_engine, "call_llm_json", AsyncMock(return_value={
        "stat": "AGI",
        "requirement": 5,
        "intent": "stealth_covert"
    }))
    char_data = {
        "id": 1,
        "user_id": user_id,
        "name": "Ghost",
        "stats": {"AGI": 7, "LUK": 5, "STR": 4, "PER": 5, "END": 4, "INT": 4, "CHA": 4}
    }

    monkeypatch.setattr(db, "get_session", lambda sid: dict(session_data) if sid == session_id else None)
    monkeypatch.setattr(db, "get_character", lambda uid: dict(char_data) if uid == user_id else None)
    monkeypatch.setattr(db, "get_settings", lambda uid: {})
    def fake_update_session(sid, **kwargs):
        session_data.update(kwargs)
    monkeypatch.setattr(db, "update_session", fake_update_session)

    # 1. Distraction throw reduces detection meter by 30%
    distract_pick = {
        "custom_action_text": "I throw a small stone to divert attention and create a noise distraction.",
        "intent": "stealth_covert"
    }
    action1 = await TurnService.prepare_and_roll_action(
        session_id=session_id,
        user_id=user_id,
        raw_pick=distract_pick,
        session=session_data,
        char=char_data
    )
    assert session_data["stealth_state"]["detection_meter"] <= 30
    assert session_data["stealth_state"]["alert_level"] == "suspicious"

    # 2. Speaking openly (dialogue_init) cleanly breaks stealth stance
    talk_pick = {
        "custom_action_text": "I step forward and introduce myself openly to the merchant.",
        "intent": "dialogue_init"
    }
    action2 = await TurnService.prepare_and_roll_action(
        session_id=session_id,
        user_id=user_id,
        raw_pick=talk_pick,
        session=session_data,
        char=char_data
    )
    assert action2["is_stealth"] is False
    assert session_data["stealth_state"]["is_hidden"] is False


def test_social_scenario_confrontation_escalation():
    from mechanics.stealth.core import resolve_stealth_action

    # High school scenario at 95% detection
    session = {
        "id": 101,
        "scenario": "high_school_drama",
        "stealth_state": {
            "is_hidden": True,
            "detection_meter": 95,
            "alert_level": "searching"
        }
    }
    char = {
        "name": "Student",
        "stats": {"AGI": 2, "LUK": 1, "STR": 2, "PER": 2, "END": 2, "INT": 2, "CHA": 2}
    }
    # Sentry teacher with high PER
    sentry = {"name": "Teacher Sentry", "stats": {"PER": 8}}

    # Force failure to trigger 100% detection
    res = resolve_stealth_action(
        session=session,
        actor_char=char,
        action_data={"label": "Sneak into faculty lounge", "action_type": "creep"},
        target_entity=sentry,
        check_mode="always_fail"
    )

    assert session["stealth_state"]["detection_meter"] == 100
    assert session["stealth_state"]["is_hidden"] is False
    # Non-combat social scenario must trigger apprehension / confrontation, NOT lethal combat!
    assert res["trigger_confrontation"] is True
    assert res["trigger_combat"] is False


@pytest.mark.asyncio
async def test_api_toggle_stealth_endpoint(monkeypatch):
    import db
    from api.deps import ToggleStealthRequest
    from api.adventure import toggle_adventure_stealth

    session_id = 4455
    user_id = 9988
    session_data = {
        "id": session_id,
        "status": "active",
        "turn_user_id": user_id,
        "scenario": "fantasy",
        "stealth_state": {
            "is_hidden": False,
            "detection_meter": 0,
            "alert_level": "unaware"
        }
    }

    monkeypatch.setattr(db, "get_session", lambda sid: dict(session_data) if sid == session_id else None)
    def fake_update_session(sid, **kwargs):
        session_data.update(kwargs)
    monkeypatch.setattr(db, "update_session", fake_update_session)

    # 1. Turn ON explicitly
    req1 = ToggleStealthRequest(session_id=session_id, user_id=user_id, active=True)
    res1 = await toggle_adventure_stealth(req1)
    assert res1["success"] is True
    assert res1["stealth_state"]["is_hidden"] is True
    assert session_data["stealth_state"]["is_hidden"] is True

    # 2. Toggle flip (active=None)
    req2 = ToggleStealthRequest(session_id=session_id, user_id=user_id, active=None)
    res2 = await toggle_adventure_stealth(req2)
    assert res2["success"] is True
    assert res2["stealth_state"]["is_hidden"] is False
    assert session_data["stealth_state"]["is_hidden"] is False


def test_covert_movement_threshold_halting(monkeypatch):
    import db
    from mechanics.world.locations.pathfinding import evaluate_spatial_route

    session_id = 9912
    session = {
        "id": session_id,
        "current_node_id": "n_start",
        "stealth_state": {
            "is_hidden": True,
            "alert_level": "searching",
            "detection_meter": 75
        }
    }

    nodes = {
        "n_start": {"id": "n_start", "name": "Dark Alley"},
        "n_mid": {"id": "n_mid", "name": "Courtyard Gate"},
        "n_end": {"id": "n_end", "name": "Inner Sanctum"}
    }
    node_states = {
        "n_start": {},
        "n_mid": {"has_sentries": True},
        "n_end": {}
    }

    monkeypatch.setattr(db, "get_world_node", lambda sid, nid: nodes.get(nid))
    monkeypatch.setattr(db, "get_world_node_state", lambda sid, nid: node_states.get(nid, {}))
    monkeypatch.setattr("mechanics.world.locations.pathfinding.get_edge_between", lambda sid, u, v: {"travel_minutes": 3, "is_locked": False})
    monkeypatch.setattr(db, "get_conn", lambda: None)
    monkeypatch.setattr("mechanics.world.locations.pathfinding.format_node_hierarchy", lambda sid, nid: nodes[nid]["name"])

    route = ["n_start", "n_mid", "n_end"]
    res = evaluate_spatial_route(session_id, route, session)

    assert res["effective_node_id"] == "n_mid"
    assert res["traversed_nodes"] == ["n_start", "n_mid"]
    assert any("STEALTH CHECKPOINT HALT" in d for d in res["stage_directives"])
    assert any("SEARCHING 75%" in d for d in res["stage_directives"])


def test_covert_intent_classification_patterns():
    from mechanics.narrative.intent import classify_action_intent, IntentCategory

    # 1. Distraction
    res1 = classify_action_intent("I throw a small stone to distract the guards.")
    assert res1.category == IntentCategory.STEALTH_COVERT
    assert res1.sub_target == "distraction"

    # 2. Infiltration / Sneak
    res2 = classify_action_intent("I sneak through the shadows past the watchtower.")
    assert res2.category == IntentCategory.STEALTH_COVERT
    assert res2.sub_target == "sneak"

    # 3. Lockpicking with complex descriptor
    res3 = classify_action_intent("I pick the heavy iron lock on the chest.")
    assert res3.category == IntentCategory.STEALTH_COVERT
    assert res3.sub_target == "lockpick"

    # 4. Pickpocketing
    res4 = classify_action_intent("I pickpocket the sleeping sentry.")
    assert res4.category == IntentCategory.STEALTH_COVERT
    assert res4.sub_target == "pickpocket"


def test_backstab_and_ambush_break_stealth_on_miss_and_hit(monkeypatch):
    import db
    from mechanics.combat.core import precompute_combat_turn

    monkeypatch.setattr(db, "get_equipment", lambda uid: {})
    monkeypatch.setattr(db, "remove_item_by_name", lambda uid, name: True)

    session = {
        "id": 9931,
        "scenario": "fantasy",
        "combat_turn": 1,
        "nearby_enemies": [{"name": "Guard", "hp": 50, "max_hp": 50, "stats": {"STR": 4, "END": 4, "PER": 4}}],
        "stealth_state": {
            "is_hidden": True,
            "combat_vanished": True,
            "detection_meter": 20
        }
    }
    party = [({
        "user_id": 1001,
        "name": "Assassin",
        "hp": 40,
        "max_hp": 40,
        "luk": 5,
        "status_effects": ["Hidden in Shadows [1 turn]"],
        "stats": {"STR": 5, "AGI": 8, "PER": 5, "END": 5, "LUK": 5}
    }, [])]

    # Action that fails / misses
    action_miss = {
        "choice_type": "MELEE_SLASHING_PIERCING",
        "label": "🗡️ Flanking Backstab",
        "stance": "stealth",
        "attack_type": "pierce",
        "tier": "fail"
    }

    res = precompute_combat_turn(session, party, [action_miss])
    # Hidden in Shadows must be stripped and combat_vanished cleared even on failure
    assert not any("Hidden in Shadows" in str(s) for s in party[0][0].get("status_effects", []))
    assert session["stealth_state"]["combat_vanished"] is False


def test_choice_deck_reflects_session_combat_vanished():
    from mechanics.narrative.choice_generator import generate_categorized_combat_actions

    char = {
        "user_id": 1002,
        "name": "Rogue",
        "char_class": "Rogue",
        "hp": 30,
        "max_hp": 30,
        "mp": 20,
        "luk": 5,
        "agi_": 8,
        "str_": 5
    }
    monster = {"name": "Orc Sentry", "hp": 40, "max_hp": 40, "stats": {"PER": 3, "AGI": 3}}
    session = {
        "id": 9932,
        "stealth_state": {
            "is_hidden": True,
            "combat_vanished": True,
            "detection_meter": 10
        }
    }

    deck = generate_categorized_combat_actions([(char, [])], monster, "dungeon", "fantasy", session=session)
    attacks = deck.get("attacks", [])
    tactics = deck.get("tactics", [])

    # Backstab must be present in attacks
    assert any("Flanking Backstab" in a["label"] for a in attacks)
    # Redundant Vanish into Shadows must NOT be in tactics when already vanished
    assert not any("Vanish into Shadows" in t["label"] for t in tactics)


def test_post_combat_cleanup_resets_combat_vanished(monkeypatch):
    import db
    from mechanics.combat.core import precompute_combat_turn

    monkeypatch.setattr(db, "get_equipment", lambda uid: {})

    session = {
        "id": 9933,
        "scenario": "fantasy",
        "combat_turn": 1,
        "nearby_enemies": [{"name": "Guard", "hp": 10, "max_hp": 10, "stats": {"STR": 3, "END": 3, "PER": 3}}],
        "stealth_state": {
            "is_hidden": True,
            "combat_vanished": True,
            "detection_meter": 0
        }
    }
    party = [({
        "user_id": 1003,
        "name": "Ninja",
        "hp": 30,
        "max_hp": 30,
        "luk": 5,
        "status_effects": ["Hidden in Shadows [1 turn]"],
        "stats": {"STR": 8, "AGI": 8, "PER": 5, "END": 5, "LUK": 5}
    }, [])]

    # Fatal attack that defeats the last enemy
    action_kill = {
        "choice_type": "MELEE_SLASHING_PIERCING",
        "label": "Fatal Strike",
        "tier": "crit_success"
    }

    precompute_combat_turn(session, party, [action_kill])
    assert session["stealth_state"]["combat_vanished"] is False


# ==============================================================================
# Step 4 Comprehensive Architectural & Omnichannel Regression Suite
# ==============================================================================


def test_unequipped_backpack_armor_and_gear_json_tags():
    from mechanics.stealth.formulas import calculate_armor_noise

    backpack_and_equipped = [
        # Heavy armor sitting UNEQUIPPED in backpack must contribute 0 noise!
        {
            "name": "Looted Full Plate",
            "slot": "Armor",
            "equipped": 0,
            "effect": '[GEAR_JSON]{"slot":"Armor","weight_class":"heavy","tags":["heavy","plate"]}',
        },
        # Equipped silent leather with [GEAR_JSON] metadata grants stealth bonus
        {
            "name": "Shadow-Stitched Jerkin",
            "slot": "Armor",
            "equipped": 1,
            "effect": '[GEAR_JSON]{"slot":"Armor","weight_class":"light","tags":["stealth","silent_step"]}',
        },
    ]
    noise_pen, stealth_bon = calculate_armor_noise(backpack_and_equipped)
    assert noise_pen == 0
    assert stealth_bon >= 10

    # Equipping that plate immediately triggers heavy noise penalty
    backpack_and_equipped[0]["equipped"] = 1
    backpack_and_equipped[1]["equipped"] = 0
    eq_noise, _ = calculate_armor_noise(backpack_and_equipped)
    assert eq_noise >= 25


def test_sqlite_agi_column_scales_opposed_stealth_odds():
    # Live SQLite character rows use 'agi_' and 'luk' rather than nested 'stats'
    agile_row = {"user_id": 11, "name": "Shade", "agi_": 10, "luk": 7}
    clumsy_row = {"user_id": 12, "name": "Clump", "agi_": 1, "luk": 1}

    odds_high = calculate_opposed_stealth_odds(actor_stats=agile_row, target_per=4, current_minute=720)
    odds_low = calculate_opposed_stealth_odds(actor_stats=clumsy_row, target_per=4, current_minute=720)
    assert odds_high["success_chance"] >= odds_low["success_chance"] + 35


def test_cast_planner_graduated_alert_preserves_cover_below_100():
    from game_engine.npcs.cast_planner import plan_pre_turn
    from skill_check import CheckResult

    failed_chk = CheckResult(chance=55, roll=88.0, tier="fail", tier_label="Failure", succeeded=False, requirement=6)
    sentry_npc = {"name": "Watchman Voss", "role": "Guard", "location": "Vault Hallway"}

    # At 35% (SUSPICIOUS) and 70% (SEARCHING), a failed stealth roll must NOT break cover!
    for meter, stage in ((35, ALERT_SUSPICIOUS), (70, ALERT_SEARCHING)):
        session = {
            "id": 9101,
            "scenario": "fantasy",
            "current_location": "Keep ➔ Vault Hallway",
            "current_npcs": [dict(sentry_npc)],
            "stealth_state": {
                "is_hidden": True,
                "detection_meter": meter,
                "alert_level": stage,
                "actors": {"501": {"is_hidden": True, "combat_vanished": False}},
            },
        }
        plan = plan_pre_turn(
            session=session,
            party=[({"user_id": 501, "name": "Lyra"}, [])],
            actions=[{"user_id": 501, "label": "Creep past Watchman Voss", "is_stealth": True, "stance": "stealth", "check": failed_chk}],
            is_combat=False,
            persist_db=False,
        )
        assert plan.stealth_active is True
        assert session["stealth_state"]["is_hidden"] is True
        assert "Watchman Voss" not in plan.dialogue_partners
        assert "Watchman Voss" in plan.bystander_npcs

    # At 100% (DETECTED), cover breaks and stealth_active drops to False
    session_detected = {
        "id": 9102,
        "scenario": "fantasy",
        "current_location": "Keep ➔ Vault Hallway",
        "current_npcs": [dict(sentry_npc)],
        "stealth_state": {
            "is_hidden": False,
            "detection_meter": 100,
            "alert_level": ALERT_DETECTED,
            "actors": {"501": {"is_hidden": False, "combat_vanished": False}},
        },
    }
    plan_det = plan_pre_turn(
        session=session_detected,
        party=[({"user_id": 501, "name": "Lyra"}, [])],
        actions=[{"user_id": 501, "label": "Creep past Watchman Voss", "is_stealth": True, "stance": "stealth", "check": failed_chk}],
        is_combat=False,
        persist_db=False,
    )
    assert plan_det.stealth_active is False


def test_combat_vanished_persists_across_apply_outcome():
    import game_engine
    from mechanics.stealth import is_actor_combat_vanished

    uid = 6101
    db.create_character(
        user_id=uid,
        name="Vesper",
        char_class="Rogue",
        stats={"STR": 5, "PER": 6, "END": 5, "CHA": 4, "INT": 5, "AGI": 9, "LUK": 6},
        gold=50,
    )
    sid = db.create_session(
        host_user_id=uid, mode="solo", capacity=1, verbosity="normal", dialogue_mode="balanced", image_gen_enabled=False
    )
    enemy = {"name": "Crypt Stalker", "hp": 45, "max_hp": 45, "stats": {"STR": 5, "PER": 3, "END": 4, "AGI": 4}}
    db.update_session(sid, nearby_enemies=[enemy], current_location="Catacombs ➔ Bone Nave")

    session = db.get_session(sid)
    char = db.get_character(uid)
    party = [(char, [])]
    vanish_action = [{
        "user_id": uid,
        "character_name": "Vesper",
        "choice_type": "STEALTH_VANISH",
        "label": "💨 Vanish into Shadows",
        "stat": "AGI",
        "tier": "success",
    }]
    combat_res = precompute_combat_turn(session, party, vanish_action)
    assert is_actor_combat_vanished(session, uid) is True

    outcome = {
        "outcome_narrative": "Vesper melts into the pillared gloom.",
        "next_narrative": "The Crypt Stalker snarls, scanning the empty dark.",
        "nearby_enemies": combat_res["surviving_monsters"],
        "stealth_state": session["stealth_state"],
        "choices": [],
    }
    game_engine.apply_outcome(
        session_id=sid,
        party=party,
        outcome=outcome,
        actions=vanish_action,
    )

    reloaded = db.get_session(sid)
    assert is_actor_combat_vanished(reloaded, uid) is True


def test_context_aware_100_percent_escalation_combat_vs_confrontation():
    from mechanics.stealth.escalation import reduce_stealth_turn_outcome

    # 1. Restricted dungeon/vault in fantasy -> immediate sentry combat spawn (is_ambush=False)
    dungeon_sess = {
        "id": 0,
        "scenario": "fantasy",
        "current_location": "Obsidian Citadel ➔ Restricted Treasury Vault",
        "nearby_enemies": [],
        "current_npcs": [],
        "stealth_state": {"is_hidden": True, "detection_meter": 100, "alert_level": "detected"},
    }
    dungeon_out = {"next_narrative": "Torchlight flares across the flagstones.", "choices": []}
    reduce_stealth_turn_outcome(
        session_id=0,
        session=dungeon_sess,
        party=[({"user_id": 1, "name": "Garrett", "level": 4}, [])],
        outcome=dungeon_out,
        actions=[{"stealth_outcome": {"trigger_combat": True, "trigger_confrontation": False}}],
        scen_key="fantasy",
        is_combat=False,
    )
    assert len(dungeon_out["nearby_enemies"]) >= 1
    assert dungeon_out["is_ambush"] is False
    assert "Cover Blown!" in dungeon_out["next_narrative"]

    # 2. Civilian town tavern in fantasy -> authority confrontation + 4 deterministic choices (no combat)
    tavern_sess = {
        "id": 0,
        "scenario": "fantasy",
        "current_location": "Oakhaven ➔ Town Market Tavern ➔ Back Counter",
        "nearby_enemies": [],
        "current_npcs": [{"name": "Barkeep Marta", "role": "Innkeeper"}],
        "stealth_state": {"is_hidden": True, "detection_meter": 100, "alert_level": "detected"},
    }
    tavern_out = {"next_narrative": "A floorboard groans behind the counter.", "choices": []}
    tid_flag_combat, tid_flag_conf = False, True
    reduce_stealth_turn_outcome(
        session_id=0,
        session=tavern_sess,
        party=[({"user_id": 1, "name": "Garrett", "level": 4}, [])],
        outcome=tavern_out,
        actions=[{"stealth_outcome": {"trigger_combat": tid_flag_combat, "trigger_confrontation": tid_flag_conf}}],
        scen_key="fantasy",
        is_combat=False,
    )
    assert not tavern_out.get("nearby_enemies")
    assert tavern_out["dialogue_partner"] == "Barkeep Marta"
    assert len(tavern_out["choices"]) == 4
    assert any(c.get("gold_cost") == 15 for c in tavern_out["choices"])


def test_spatial_suspicion_halving_reset_and_quiet_decay():
    from mechanics.stealth.core import apply_stealth_spatial_transition, apply_stealth_decay_turn

    session = {
        "id": 0,
        "scenario": "cyberpunk",
        "stealth_state": {
            "is_hidden": True,
            "detection_meter": 70,
            "alert_level": "searching",
            "free_distraction_used": True,
            "actors": {"1": {"is_hidden": True, "combat_vanished": False}},
        },
    }

    # Same facility room hop halves meter (70 -> 35) and resets per-room free distraction
    apply_stealth_spatial_transition(
        session,
        prev_location="Arasaka Tower ➔ Sublevel Lab ➔ Server Room A",
        new_location="Arasaka Tower ➔ Sublevel Lab ➔ Server Room B",
    )
    assert session["stealth_state"]["detection_meter"] == 35
    assert session["stealth_state"]["alert_level"] == "suspicious"
    assert session["stealth_state"]["free_distraction_used"] is False

    # Waiting motionless decays by -15% (35 -> 20)
    apply_stealth_decay_turn(session, is_waiting_still=True)
    assert session["stealth_state"]["detection_meter"] == 20
    assert session["stealth_state"]["alert_level"] == "unaware"

    # Standard quiet turn decays by -10% (20 -> 10)
    apply_stealth_decay_turn(session, is_waiting_still=False)
    assert session["stealth_state"]["detection_meter"] == 10

    # Exiting facility resets suspicion to 0%
    apply_stealth_spatial_transition(
        session,
        prev_location="Arasaka Tower ➔ Sublevel Lab ➔ Server Room B",
        new_location="Night Market ➔ Noodle Stall ➔ Counter",
    )
    assert session["stealth_state"]["detection_meter"] == 0


def test_distraction_anti_spam_free_then_contested():
    from mechanics.stealth.core import resolve_distraction_action

    session = {
        "id": 0,
        "scenario": "fantasy",
        "stealth_state": {
            "is_hidden": True,
            "detection_meter": 65,
            "alert_level": "searching",
            "free_distraction_used": False,
            "actors": {"77": {"is_hidden": True, "combat_vanished": False}},
        },
    }
    actor = {"user_id": 77, "name": "Trickster", "agi_": 7, "luk": 6}

    # 1st distraction in cycle: guaranteed roll-free -30% (65 -> 35)
    r1 = resolve_distraction_action(session, actor_char=actor, user_id=77)
    assert r1["was_free_distraction"] is True
    assert r1["check"].chance == 100 and r1["check"].requirement == 0 and r1["check"].succeeded is True
    assert session["stealth_state"]["detection_meter"] == 35
    assert session["stealth_state"]["free_distraction_used"] is True

    # 2nd distraction in same cycle: contested roll — failure backfires (+15% -> 50)
    r2_fail = resolve_distraction_action(session, actor_char=actor, user_id=77, check_mode="always_fail")
    assert r2_fail["was_free_distraction"] is False
    assert r2_fail["check"] is not None and r2_fail["check"].succeeded is False
    assert session["stealth_state"]["detection_meter"] == 50

    # Contested success sheds -25% (50 -> 25)
    r3_pass = resolve_distraction_action(session, actor_char=actor, user_id=77, check_mode="always_success")
    assert r3_pass["check"].succeeded is True
    assert session["stealth_state"]["detection_meter"] == 25


def test_one_turn_alert_transient_consumption_prevents_prompt_poisoning():
    from mechanics.stealth.core import consume_stealth_turn_transients

    session = {"id": 1, "scenario": "fantasy"}
    toggle_stealth_stance(session, True, user_id=10)
    break_stealth(session, reason="unsuppressed_offensive_magic", user_id=10, break_all=True)

    # On the turn stealth breaks, directive instructs LLM to narrate cover blowing once
    d_turn1 = format_stealth_truth_directive(session)
    assert "COVER WAS JUST BROKEN" in d_turn1

    # After Phase 4 consumes transients, subsequent normal turns emit empty directive
    consume_stealth_turn_transients(session)
    d_turn2 = format_stealth_truth_directive(session)
    assert d_turn2 == ""


def test_recursive_serializable_action_handles_nested_stealth_check():
    import json
    from api.deps import _serializable_action

    session = {"id": 1, "scenario": "fantasy"}
    actor = {"user_id": 42, "name": "Shade", "agi_": 8, "luk": 5}
    so = resolve_stealth_action(
        session=session,
        actor_char=actor,
        action_data={"label": "Sneak through archway", "action_type": "sneak"},
        check_mode="always_success",
        user_id=42,
    )
    raw_action = {
        "user_id": 42,
        "label": "Sneak through archway",
        "is_stealth": True,
        "check": so["check"],
        "stealth_outcome": so,
    }
    safe_payload = _serializable_action(raw_action)
    encoded = json.dumps(safe_payload)
    decoded = json.loads(encoded)
    assert decoded["stealth_outcome"]["check"]["succeeded"] is True


def test_coop_per_player_stealth_isolation_and_projection(monkeypatch):
    from mechanics.stealth import (
        is_actor_hidden,
        project_stealth_state_for_user,
        set_actor_combat_vanished,
        is_actor_combat_vanished,
    )
    from cogs.adventure.embeds import _party_vitals_text

    session = {
        "id": 500,
        "mode": "turn",
        "turn_order": [101, 202],
        "scenario": "fantasy",
        "stealth_state": init_stealth_state(),
    }
    toggle_stealth_stance(session, True, user_id=101)
    toggle_stealth_stance(session, False, user_id=202)
    session["stealth_state"]["detection_meter"] = 30

    assert is_actor_hidden(session, 101) is True
    assert is_actor_hidden(session, 202) is False

    proj_101 = project_stealth_state_for_user(session, 101)
    proj_202 = project_stealth_state_for_user(session, 202)
    assert proj_101["is_hidden"] is True
    assert proj_202["is_hidden"] is False
    assert proj_101["detection_meter"] == 30 and proj_202["detection_meter"] == 30

    chars = {
        101: {"user_id": 101, "name": "ShadowRogue", "level": 3, "hp": 80, "max_hp": 80, "mp": 30, "max_mp": 30, "status_effects": []},
        202: {"user_id": 202, "name": "LoudPaladin", "level": 3, "hp": 120, "max_hp": 120, "mp": 20, "max_mp": 20, "status_effects": []},
    }
    monkeypatch.setattr(db, "get_character", lambda uid: chars.get(uid))
    monkeypatch.setattr(db, "current_turn_user_id", lambda s: 101)

    vitals = _party_vitals_text(session)
    lines = vitals.splitlines()
    rogue_line = next(l for l in lines if "ShadowRogue" in l)
    paladin_line = next(l for l in lines if "LoudPaladin" in l)
    assert "🥷 Sneaking (30%)" in rogue_line
    assert "Sneaking" not in paladin_line

    set_actor_combat_vanished(session, True, user_id=101)
    assert is_actor_combat_vanished(session, 101) is True
    assert is_actor_combat_vanished(session, 202) is False


def test_enrich_choices_with_odds_uses_opposed_stealth_math():
    from api.deps import enrich_choices_with_odds

    uid = 7101
    db.create_character(
        user_id=uid,
        name="Whisper",
        char_class="Rogue",
        stats={"STR": 3, "PER": 6, "END": 4, "CHA": 4, "INT": 5, "AGI": 9, "LUK": 6},
        gold=50,
    )
    sid = db.create_session(
        host_user_id=uid, mode="solo", capacity=1, verbosity="normal", dialogue_mode="balanced", image_gen_enabled=False
    )
    session = db.get_session(sid)
    toggle_stealth_stance(session, True, user_id=uid)
    session["current_npcs"] = [{"name": "Eagle Watchman", "role": "Guard", "stats": {"PER": 7}}]

    choices = [{"label": "Shadow Step — Slip quietly past the watchman", "stat": "AGI", "requirement": 6, "intent": "stealth_covert", "is_stealth": True}]
    enriched_light = enrich_choices_with_odds(choices, uid, session=session)

    # Now equip heavy plate armor in SQLite inventory and verify displayed stealth odds drop
    item_id = db.add_item(
        uid,
        "Towering Full Plate",
        item_type="Armor",
        effect='[GEAR_JSON]{"slot":"Armor","weight_class":"heavy","tags":["heavy","plate"]}',
    )
    db.equip_item(uid, item_id, "Armor")
    enriched_heavy = enrich_choices_with_odds(choices, uid, session=session)

    assert enriched_heavy[0]["success_pct"] < enriched_light[0]["success_pct"]
