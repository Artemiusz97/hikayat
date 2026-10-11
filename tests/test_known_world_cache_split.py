"""KNOWN WORLD volatility split: canon (Z1b, cached) vs scene (Z2) vs quest board (Z3)."""
import time
from unittest.mock import AsyncMock, patch

import pytest

import db
import game_engine
import game_engine.prompt_layout as prompt_layout
from mechanics.social.factions import format_llm_faction_context, format_llm_faction_standings


def _fresh_session_id() -> int:
    return int(time.time() * 1000) % 1_000_000_000 + 4_200_000


def _seed_world(sid: int) -> None:
    db.upsert_lorebook_entity(sid, "place", "Whispering Docks", description="Fog-bound harbour")
    db.upsert_lorebook_entity(sid, "place", "Amber Keep", description="Old royal fortress")
    db.upsert_lorebook_entity(sid, "faction", "Iron Guild", disposition="friendly")
    db.upsert_lorebook_entity(sid, "person", "Mira Vale", description="Dockmaster", race="human")


def test_world_canon_independent_of_db_update_order():
    sid = _fresh_session_id()
    _seed_world(sid)
    before = game_engine._world_canon_text(sid)

    # Touching a row bumps updated_at (the DB query orders by it); canon must not move.
    time.sleep(0.01)
    db.upsert_lorebook_entity(sid, "place", "Amber Keep", description="Old royal fortress")
    after = game_engine._world_canon_text(sid)

    assert before == after
    assert before.index("Amber Keep") < before.index("Whispering Docks")  # alphabetical
    assert "Iron Guild" in before


def test_world_canon_excludes_scene_volatile_data():
    sid = _fresh_session_id()
    _seed_world(sid)
    session = {"id": sid, "scenario": "fantasy"}
    zone_1b = prompt_layout.build_world_canon_zone(session)

    assert zone_1b.startswith(prompt_layout.WORLD_CANON_HEADER)
    assert "NPCs currently present" not in zone_1b
    assert "Current location" not in zone_1b
    assert "Known people" not in zone_1b


def test_scene_context_carries_volatile_data():
    sid = _fresh_session_id()
    _seed_world(sid)
    npcs = [{"name": "Mira Vale", "hp": 12, "max_hp": 20}]
    scene = game_engine._scene_context_text(sid, "Whispering Docks", current_npcs=npcs)

    assert "Whispering Docks" in scene
    assert "Mira Vale" in scene
    assert "HP 12/20" in scene
    assert "Nearby known places" in scene


def test_known_world_wrapper_keeps_full_content():
    sid = _fresh_session_id()
    _seed_world(sid)
    text = game_engine._known_world_text(sid, "Whispering Docks", current_npcs=[{"name": "Mira Vale"}])
    for needle in ("Amber Keep", "Whispering Docks", "Iron Guild", "Mira Vale", "NPC CANON RULE"):
        assert needle in text


def test_canon_cap_is_mode_independent_and_bounded():
    long = "; ".join(f"Place {i:03d} (a very long description of somewhere)" for i in range(200))
    capped = prompt_layout._cap(long, prompt_layout.WORLD_CANON_MAX_CHARS)
    assert len(capped) <= prompt_layout.WORLD_CANON_MAX_CHARS + 2
    assert capped == prompt_layout._cap(long, prompt_layout.WORLD_CANON_MAX_CHARS)


def test_faction_roster_has_no_standing_and_standings_have_score():
    factions = [{
        "faction_id": "f1", "name": "Iron Guild", "reputation_score": 35,
        "leadership_roster": [{"rank": 4, "name": "Bram Holt", "title": "Guildmaster"}],
        "rival_faction_ids": [],
    }]
    roster = format_llm_faction_context(factions, include_standing=False)
    assert roster == "FACTIONS: Iron Guild [Leader:Bram Holt]"
    assert "+35" not in roster

    standings = format_llm_faction_standings(factions)
    assert standings.startswith("FACTION STANDINGS: Iron Guild [")
    assert "+35" in standings

    # Default behaviour unchanged for existing callers
    assert "+35" in format_llm_faction_context(factions)


@pytest.mark.asyncio
async def test_resolve_turn_zone_order_and_quest_board_not_truncated():
    sid = _fresh_session_id()
    _seed_world(sid)
    session = {"id": sid, "scenario": "fantasy", "style": "normal", "history": []}
    char = {"id": "1", "name": "Hero", "user_id": 1}

    huge_scene = "Current location: Docks\n" + ("filler sentence. " * 2000)
    with patch("game_engine.call_llm_json", new_callable=AsyncMock) as mock_llm_json, \
         patch("game_engine.call_llm_json_stream", new_callable=AsyncMock), \
         patch("game_engine._scene_context_text", return_value=huge_scene), \
         patch("game_engine._quest_board_parts", return_value=("WAYPOINT-MARKER-XYZ", "CASEBOARD-MARKER-XYZ")):
        mock_llm_json.return_value = {}
        await game_engine.resolve_turn(session, [(char, [])], [])

    system_prompt, user_prompt = mock_llm_json.call_args[0][0], mock_llm_json.call_args[0][1]

    canon_i = system_prompt.index(prompt_layout.WORLD_CANON_HEADER)
    sheet_i = system_prompt.index("CHARACTER SHEET(S):")
    scene_i = system_prompt.index(prompt_layout.SCENE_CONTEXT_HEADER)
    assert system_prompt.index("OUTPUT SCHEMA") < canon_i < sheet_i < scene_i

    # Previously appended to the tail of KNOWN WORLD and cut by the "lore" trim.
    assert "WAYPOINT-MARKER-XYZ" in user_prompt
    assert "CASEBOARD-MARKER-XYZ" in user_prompt
    assert "WAYPOINT-MARKER-XYZ" not in system_prompt
