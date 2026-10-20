import pytest
from unittest.mock import AsyncMock, patch
import db
from services.turn_service import TurnService
import game_engine
# Unit tests for image persistence and LLM resilience

@pytest.fixture
def mock_session():
    user_id = 99201
    session_id = db.create_session(
        host_user_id=user_id,
        mode="solo",
        capacity=1,
        verbosity="normal",
        dialogue_mode="balanced",
        image_gen_enabled=True,
        scenario="fantasy"
    )
    db.add_session_member(session_id, user_id)
    db.set_session_active(session_id, [user_id])
    db.create_character(user_id, "Artem", "Scholar")
    return session_id, user_id

@pytest.mark.asyncio
async def test_scene_image_url_persistence(mock_session):
    session_id, user_id = mock_session

    # Verify session has scene_image_url column
    db.update_session(session_id, scene_image_url="https://example.com/test_scene.webp")
    sess = db.get_session(session_id)
    assert sess["scene_image_url"] == "https://example.com/test_scene.webp"

@pytest.mark.asyncio
async def test_resolve_turn_graceful_fallback_on_llm_outage(mock_session):
    session_id, user_id = mock_session
    sess = db.get_session(session_id)
    char = db.get_character(user_id)
    party = [(dict(char), [])]
    action = {
        "user_id": user_id,
        "label": "'Trust me, I can handle it without causing a scene.'",
        "stat": "CHA",
        "requirement": 5,
        "mp_spent": 0,
        "char": dict(char)
    }

    # Simulate upstream LLM complete outage / timeout
    with patch("game_engine.call_llm_json_stream", new_callable=AsyncMock) as mock_stream, \
         patch("game_engine.call_llm_json", new_callable=AsyncMock) as mock_batch:
        mock_stream.side_effect = RuntimeError("All LLM candidate models in fallback chain failed. Last error: Connection timed out.")
        mock_batch.side_effect = RuntimeError("All LLM candidate models in fallback chain failed. Last error: Connection timed out.")

        # resolve_turn should NOT crash; it should activate deterministic fallback
        outcome = await game_engine.resolve_turn(sess, party, [action])
        assert outcome is not None
        assert outcome.get("_is_fallback_narrative") is True
        assert outcome.get("is_fallback") is True
        assert "outcome_narrative" in outcome and len(outcome["outcome_narrative"]) > 0
        assert "next_narrative" in outcome and len(outcome["next_narrative"]) > 0
        assert len(outcome.get("choices", [])) > 0
