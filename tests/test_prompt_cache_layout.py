import pytest
import hashlib
import json
import subprocess
import os
import sys
from unittest.mock import AsyncMock, patch, MagicMock

import game_engine.prompt_layout as prompt_layout
from game_engine.turn.core import resolve_turn
from llm_client import _build_messages, _extract_cached_tokens, _STREAM_USAGE_UNSUPPORTED

def test_static_core_stability():
    mode = "narrative"
    kind = "turn"
    
    # Run the same logic in different subprocesses with different hash seeds
    code = f"""
import sys
sys.path.append(r'{os.getcwd()}')
from game_engine.prompt_layout import build_static_core
import hashlib
print(hashlib.md5(build_static_core("narrative", "turn").encode()).hexdigest())
"""
    
    env = os.environ.copy()
    
    env["PYTHONHASHSEED"] = "1"
    res1 = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    
    env["PYTHONHASHSEED"] = "2"
    res2 = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    
    assert res1.stdout.strip() == res2.stdout.strip(), "Static core must be byte-identical across processes!"

def test_shared_prefix():
    narrative_core = prompt_layout.build_static_core("narrative", "turn")
    combat_core = prompt_layout.build_static_core("combat", "turn")
    
    from llm_client import GM_SHARED_RULES
    assert narrative_core.startswith(GM_SHARED_RULES)
    assert combat_core.startswith(GM_SHARED_RULES)

def test_session_independence():
    session1 = {"id": "1", "scenario": "fantasy", "style": "normal"}
    session2 = {"id": "2", "scenario": "cyberpunk", "style": "normal"}
    
    core1 = prompt_layout.build_static_core("narrative", "turn")
    core2 = prompt_layout.build_static_core("narrative", "turn")
    assert core1 == core2
    
    zone1_1 = prompt_layout.build_session_zone(session1)
    zone1_2 = prompt_layout.build_session_zone(session2)
    assert zone1_1 != zone1_2

@pytest.mark.asyncio
async def test_resolve_turn_system_prompt():
    session = {"id": "1", "scenario": "fantasy", "style": "normal", "history": []}
    char = {"id": "1", "name": "Hero", "user_id": 1}
    inventory = []
    actions = []
    
    with patch("game_engine.call_llm_json_stream", new_callable=AsyncMock) as mock_llm, \
         patch("game_engine.call_llm_json", new_callable=AsyncMock) as mock_llm_json, \
         patch("llm_client.get_embedding", new_callable=AsyncMock) as mock_emb:
        mock_llm.return_value = {"narrative": "Test"}
        mock_llm_json.return_value = {}
        mock_emb.return_value = [0.0] * 1536
        
        await resolve_turn(session, [(char, inventory)], actions)
        
        args = mock_llm_json.call_args
        assert args is not None
        system_prompt = args[0][0]
        user_prompt = args[0][1]
        
        assert isinstance(system_prompt, str)
        assert "KNOWN WORLD:" in system_prompt
        assert "CHARACTER SHEET(S):" in system_prompt
        assert "OUTPUT SCHEMA" in system_prompt
        
        assert "ACTIONS:" in user_prompt

def test_extract_cached_tokens():
    usage = type("Usage", (), {"prompt_tokens_details": {"cached_tokens": 50}})()
    assert _extract_cached_tokens(usage) == 50
    
    usage2 = type("Usage", (), {"prompt_cache_hit_tokens": 60})()
    assert _extract_cached_tokens(usage2) == 60
    
    assert _extract_cached_tokens(None) is None

def test_build_messages():
    messages = _build_messages([{"role": "system", "content": "Part 1"}, {"role": "system", "content": "Part 2"}], "User")
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "Part 1\n\nPart 2" in messages[0]["content"]





