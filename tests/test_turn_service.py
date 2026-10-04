"""
Unit & Integration Tests for TurnService (services/turn_service.py).

Tests:
1. Solo Action Resolution: Base XP, LLM Bonus XP, Inventory Rewards, History Updates.
2. Synchronized Multiplayer: Partial locks (waiting_for_party), full party resolution, lock reset.
3. Dynamic History Limit: Limit expands to 12 when dialogue partners are present.
4. Error handling: Non-existent session IDs.
"""
import pytest
from unittest.mock import patch, AsyncMock
import db
from services.turn_service import TurnService, TurnResponse
from skill_check import CheckResult


@pytest.fixture
def setup_solo_session():
    """Sets up a clean solo adventure session in SQLite."""
    user_id = 88001
    char = db.create_character(
        user_id=user_id,
        name="SoloHero",
        char_class="Warrior",
        stats={"STR": 5, "PER": 2, "END": 3, "CHA": 1, "INT": 1, "AGI": 2, "LUK": 1}
    )
    session_id = db.create_session(
        host_user_id=user_id,
        mode="solo",
        capacity=1,
        verbosity="normal",
        dialogue_mode="balanced",
        image_gen_enabled=False,
        scenario="fantasy"
    )
    db.add_session_member(session_id, user_id)
    db.set_session_active(session_id, [user_id])
    return session_id, user_id


@pytest.fixture
def setup_party_session():
    """Sets up a clean 2-player synchronized adventure session in SQLite."""
    u1, u2 = 88002, 88003
    db.create_character(user_id=u1, name="PlayerOne", char_class="Mage", stats={"STR": 1, "PER": 2, "END": 2, "CHA": 2, "INT": 5, "AGI": 2, "LUK": 1})
    db.create_character(user_id=u2, name="PlayerTwo", char_class="Rogue", stats={"STR": 2, "PER": 4, "END": 2, "CHA": 1, "INT": 1, "AGI": 4, "LUK": 1})

    session_id = db.create_session(
        host_user_id=u1,
        mode="sync",
        capacity=2,
        verbosity="normal",
        dialogue_mode="balanced",
        image_gen_enabled=False,
        scenario="fantasy"
    )
    db.add_session_member(session_id, u1)
    db.add_session_member(session_id, u2)
    db.set_session_active(session_id, [u1, u2])
    return session_id, u1, u2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resolve_action_solo_success(setup_solo_session):
    session_id, user_id = setup_solo_session

    check = CheckResult(chance=80, roll=70.0, tier="success", tier_label="Success", succeeded=True, requirement=8)
    action = {
        "user_id": user_id,
        "character_name": "SoloHero",
        "label": "Charge the goblin guard",
        "check": check,
        "tier": "success",
        "mp_spent": 0
    }

    mock_outcome = {
        "scene_title": "Goblin Outpost",
        "outcome_narrative": "You overwhelm the goblin with brute force!",
        "next_narrative": "The path forward into the caves lies open.",
        "choices": [{"label": "Enter cavern", "stat": "PER", "requirement": 5}],
        "character_outcomes": [
            {"name": "SoloHero", "xp_change": 15, "items_gained": ["Iron Key"]}
        ]
    }

    with patch("game_engine.resolve_turn", new_callable=AsyncMock) as mock_resolve, \
         patch("game_engine.apply_outcome", return_value={user_id: ["Iron Key"]}), \
         patch("game_engine.apply_quest_update"):

        mock_resolve.return_value = mock_outcome

        resp = await TurnService.resolve_action(session_id, user_id, action, mode="solo")

        assert isinstance(resp, TurnResponse)
        assert resp.success is True
        # Base XP for 'success' is 18 + bonus 15 = 33 XP
        assert resp.xp_gained == 33
        assert user_id in resp.items_gained_by_user
        assert resp.items_gained_by_user[user_id] == ["Iron Key"]

        # Verify history was pushed
        fresh = db.get_session(session_id)
        assert len(fresh["history"]) > 0
        assert fresh['history'][-1].get('character_name') == 'SoloHero'
        assert fresh['history'][-1].get('label') == 'Charge the goblin guard'


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resolve_action_sync_multiplayer_flow(setup_party_session):
    session_id, u1, u2 = setup_party_session

    action1 = {
        "user_id": u1,
        "character_name": "PlayerOne",
        "label": "Cast Magic Missile",
        "tier": "success",
        "mp_spent": 5
    }
    action2 = {
        "user_id": u2,
        "character_name": "PlayerTwo",
        "label": "Sneak behind enemy lines",
        "tier": "success",
        "mp_spent": 0
    }

    mock_outcome = {
        "scene_title": "Dungeon Ambush",
        "outcome_narrative": "The combined assault breaks the enemy ranks!",
        "next_narrative": "Victory is yours.",
        "choices": [],
        "character_outcomes": []
    }

    # Player 1 submits first: must raise 'waiting_for_party'
    with pytest.raises(ValueError, match="waiting_for_party"):
        await TurnService.resolve_action(session_id, u1, action1, mode="sync")

    # Verify pending picks has player 1's action saved
    sess = db.get_session(session_id)
    assert str(u1) in sess["pending_picks"]
    assert sess["pending_picks"][str(u1)]["label"] == "Cast Magic Missile"

    # Player 2 submits: both players are locked in -> resolves!
    with patch("game_engine.resolve_turn", new_callable=AsyncMock) as mock_resolve, \
         patch("game_engine.apply_outcome", return_value={u1: [], u2: []}), \
         patch("game_engine.apply_quest_update"):

        mock_resolve.return_value = mock_outcome

        resp = await TurnService.resolve_action(session_id, u2, action2, mode="sync")
        assert resp.success is True

        # Verify pending picks was cleared to empty
        fresh = db.get_session(session_id)
        assert fresh["pending_picks"] == {}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_resolve_action_invalid_session():
    with pytest.raises(ValueError, match="Session 9999999 not found"):
        await TurnService.resolve_action(9999999, 1234, {"label": "Look"})


@pytest.mark.integration
@pytest.mark.asyncio
async def test_history_dynamic_limit_dialogue_expansion(setup_solo_session):
    session_id, user_id = setup_solo_session
    action = {"user_id": user_id, "character_name": "SoloHero", "label": "Talk", "tier": "action"}

    # Case A: with dialogue partners present -> limit expands to 12
    outcome_with_partner = {
        "scene_title": "Conversation",
        "outcome_narrative": "Chatting with the merchant.",
        "dialogue_partners": ["Merchant Bob"],
        "choices": []
    }
    with patch("game_engine.resolve_turn", new_callable=AsyncMock) as mock_resolve, \
         patch("game_engine.apply_outcome", return_value={}), \
         patch("game_engine.apply_quest_update"), \
         patch("game_engine.push_history", wraps=lambda h, e, limit: h + [f"limit_{limit}"]) as mock_push:

        mock_resolve.return_value = outcome_with_partner
        await TurnService.resolve_action(session_id, user_id, action, mode="solo")
        mock_push.assert_called_with(mock_push.call_args[0][0], mock_push.call_args[0][1], limit=12)

    # Case B: no dialogue partners -> limit stays at 4
    outcome_no_partner = {
        "scene_title": "Exploration",
        "outcome_narrative": "Walking through empty corridors.",
        "choices": []
    }
    with patch("game_engine.resolve_turn", new_callable=AsyncMock) as mock_resolve, \
         patch("game_engine.apply_outcome", return_value={}), \
         patch("game_engine.apply_quest_update"), \
         patch("game_engine.push_history", wraps=lambda h, e, limit: h + [f"limit_{limit}"]) as mock_push:

        mock_resolve.return_value = outcome_no_partner
        await TurnService.resolve_action(session_id, user_id, action, mode="solo")
        mock_push.assert_called_with(mock_push.call_args[0][0], mock_push.call_args[0][1], limit=4)
