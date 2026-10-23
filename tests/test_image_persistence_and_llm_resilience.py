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


@pytest.mark.asyncio
async def test_session_image_polling_endpoint(mock_session):
    from fastapi.testclient import TestClient
    import server

    session_id, user_id = mock_session
    client = TestClient(server.app)

    # Initial state: no image
    res = client.get(f"/api/adventure/session-image/{session_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"] == session_id
    assert data["scene_image_url"] is None

    # Update session with image url
    db.update_session(session_id, scene_image_url="http://localhost:8000/images/test_scene.png")
    res = client.get(f"/api/adventure/session-image/{session_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["scene_image_url"] == "http://localhost:8000/images/test_scene.png"


@pytest.mark.asyncio
async def test_connection_manager_broadcast_type_resilience():
    from api.deps import manager

    # Fake websocket object
    class DummyWS:
        def __init__(self):
            self.sent = []

        async def send_json(self, msg):
            self.sent.append(msg)

    ws = DummyWS()
    # Connect with int
    manager.active_connections[12345] = [{"ws": ws, "user_id": 99}]

    # Broadcast with string session id
    await manager.broadcast("12345", {"type": "SCENE_IMAGE", "url": "http://test.png"})
    assert len(ws.sent) == 1
    assert ws.sent[0]["url"] == "http://test.png"

    # Broadcast with int session id
    await manager.broadcast(12345, {"type": "SCENE_IMAGE", "url": "http://test2.png"})
    assert len(ws.sent) == 2
    assert ws.sent[1]["url"] == "http://test2.png"

    # Cleanup
    del manager.active_connections[12345]

