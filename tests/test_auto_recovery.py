import pytest
import asyncio
from unittest.mock import AsyncMock, patch

import db
from services.turn_service import TurnService, TurnResponse
import game_engine

@pytest.fixture
def mock_session():
    user_id = 99102
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
    
    db.create_character(user_id, "TestChar", "Warrior")
    return session_id, user_id

@pytest.mark.asyncio
async def test_auto_recovery_triggered_on_fallback(mock_session):
    session_id, user_id = mock_session
    
    mock_base_outcome = {
        "_is_fallback_narrative": True,
        "outcome_narrative": "Hero acts with deliberate intent: acts.",
        "next_narrative": "The atmosphere settles around the area as the immediate action resolves."
    }
    
    # Mock game_engine.resolve_turn to return a fallback narrative
    with patch("game_engine.resolve_turn", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = mock_base_outcome
        
        # Mock TurnService.retry_narration to simulate a successful recovery
        mock_recovered_response = TurnResponse(
            success=True,
            session={"history": []},
            outcome={
                "outcome_narrative": "Hero gracefully swings their sword.",
                "next_narrative": "The goblin recoils in fear.",
                "fallback_reason": None
            },
            action={"char": {"name": "Hero"}, "stat": "STR"},
            items_gained_by_user={},
            xp_gained=0,
            levels_gained=[],
            new_char={}
        )
        with patch.object(TurnService, "retry_narration", new=AsyncMock(return_value=mock_recovered_response)) as mock_retry:
            action = {"label": "Attack", "stat": "STR", "type": "custom", "check": {"chance": 100, "tier_label": "Success", "tier": "success"}}
            response = await TurnService.resolve_action(session_id, user_id, action, mode="solo")
            
            mock_retry.assert_called_once()
            assert response.outcome["outcome_narrative"] == "Hero gracefully swings their sword."
            assert response.outcome["next_narrative"] == "The goblin recoils in fear."

@pytest.mark.asyncio
async def test_auto_recovery_fails_and_sets_fallback_reason(mock_session):
    session_id, user_id = mock_session
    
    mock_base_outcome = {
        "_is_fallback_narrative": True,
        "outcome_narrative": "Hero acts with deliberate intent: acts.",
        "next_narrative": "The atmosphere settles around the area as the immediate action resolves."
    }
    
    with patch("game_engine.resolve_turn", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = mock_base_outcome
        
        # Mock TurnService.retry_narration to simulate a failure
        with patch.object(TurnService, "retry_narration", new=AsyncMock(side_effect=Exception("LLM offline"))) as mock_retry:
            action = {"label": "Attack", "stat": "STR", "type": "custom", "check": {"chance": 100, "tier_label": "Success", "tier": "success"}}
            response = await TurnService.resolve_action(session_id, user_id, action, mode="solo")
            
            mock_retry.assert_called_once()
            # Falls back to base response
            assert response.outcome["outcome_narrative"] == "Hero acts with deliberate intent: acts."
            assert response.outcome["fallback_reason"] == "empty_prose"
            
            # Verify snapshot was updated with fallback reason
            snapshot = db.get_turn_snapshot(session_id)
            assert snapshot["fallback_reason"] == "empty_prose"

@pytest.mark.asyncio
async def test_retry_narration_missing_snapshot(mock_session):
    session_id, user_id = mock_session
    
    # Try to retry without a snapshot
    with pytest.raises(ValueError, match="No completed snapshot available to retry"):
        await TurnService.retry_narration(session_id, user_id)
        
@pytest.mark.asyncio
async def test_retry_narration_pending_snapshot(mock_session):
    session_id, user_id = mock_session
    
    # Add a pending snapshot (representing a turn that is currently generating)
    db.set_turn_snapshot(session_id, {"status": "pending"})
    
    # Try to retry with a pending snapshot
    with pytest.raises(ValueError, match="No completed snapshot available to retry"):
        await TurnService.retry_narration(session_id, user_id)
