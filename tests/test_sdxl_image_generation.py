"""
Tests for SDXL/Illustrious Image Prompt Composer & API Pipeline
"""
import pytest
from mechanics.narrative.image_prompt_composer import (
    compose_turn_image_prompt,
    format_species_tags,
    format_npc_appearance_tags,
    format_expression_tags,
    DIMENSION_PORTRAIT,
    DIMENSION_WIDE,
    DEFAULT_NEGATIVE_PROMPT,
)


def test_species_formatting_beastfolk_vs_half_beast():
    # Beastfolk / Furry -> anthro, kemono, <species>
    assert format_species_tags("beastfolk:cat") == "anthro, kemono, cat"
    assert format_species_tags("beastfolk:fox") == "anthro, kemono, fox"
    assert format_species_tags("beastfolk:wolf") == "anthro, kemono, wolf"
    assert format_species_tags("beastfolk", "rabbit") == "anthro, kemono, rabbit"

    # Half Beast / Hybrid -> human, <species> ears, <species> tail
    assert format_species_tags("half_beast:cat") == "human, cat ears, cat tail"
    assert format_species_tags("half_beast:fox") == "human, fox ears, fox tail"
    assert format_species_tags("hybrid:wolf") == "human, wolf ears, wolf tail"
    assert format_species_tags("half_beast", "cat") == "human, cat ears, cat tail"

    # Human & Fantasy races
    assert format_species_tags("human") == "human"
    assert format_species_tags("elf") == "elf, pointy ears"
    assert format_species_tags("dwarf") == "dwarf"


def test_solo_npc_portrait_generation():
    session = {
        "id": 99,
        "scenario": "furry_high_school_drama",
        "current_location": "Class 2-1 (Homeroom)",
        "current_npcs": [
            {
                "name": "Alicja Yamamoto",
                "race": "beastfolk:cat",
                "gender": "female",
                "appearance": {
                    "eye_color": "emerald green",
                    "hair_color": "calico",
                    "hair_style": "short",
                    "distinctive_features": "fluffy calico tail, cat ears",
                    "outfit_style": "school uniform, pleated skirt",
                },
            }
        ],
    }
    outcome = {
        "dialogue_partner": "Alicja Yamamoto",
        "location": "Class 2-1 (Homeroom)",
        "actor_poses": {
            "Alicja Yamamoto": {"posture": "standing", "holding": "clipboard"}
        },
    }
    action = {"label": "inquire about schedule", "check": {"tier": "fail"}}

    res = compose_turn_image_prompt(session, outcome=outcome, action=action)

    assert res.orientation == "portrait"
    assert res.size == DIMENSION_PORTRAIT
    assert "1girl" in res.prompt
    assert "anthro, kemono, cat" in res.prompt
    assert "green eyes" in res.prompt
    assert "short calico hair" in res.prompt
    assert "fluffy calico tail" in res.prompt
    assert "holding clipboard" in res.prompt
    assert "annoyed" in res.prompt  # from check tier fail
    assert "facing viewer" in res.prompt
    assert "classroom" in res.prompt
    assert res.negative_prompt == DEFAULT_NEGATIVE_PROMPT


def test_duo_npcs_wide_generation_with_break():
    session = {
        "id": 100,
        "scenario": "furry_high_school_drama",
        "current_location": "Class 2-1 (Homeroom)",
        "current_npcs": [
            {
                "name": "Alicja Yamamoto",
                "race": "beastfolk:cat",
                "gender": "female",
                "appearance": {
                    "eye_color": "emerald green",
                    "hair_color": "calico",
                },
            },
            {
                "name": "Nicholas Ito",
                "race": "beastfolk:fox",
                "gender": "male",
                "appearance": {
                    "eye_color": "amber",
                    "hair_color": "brown",
                },
            },
        ],
    }
    outcome = {
        "dialogue_partner": "Alicja Yamamoto",
        "npcs_present": [{"name": "Alicja Yamamoto"}, {"name": "Nicholas Ito"}],
        "location": "Class 2-1 (Homeroom)",
        "actor_poses": {
            "Alicja Yamamoto": {"posture": "standing", "holding": "clipboard"},
            "Nicholas Ito": {"posture": "seated", "holding": "notebook"},
        },
    }
    action = {"label": "address them"}

    res = compose_turn_image_prompt(session, outcome=outcome, action=action)

    assert res.orientation == "wide"
    assert res.size == DIMENSION_WIDE
    assert "1boy, 1girl" in res.prompt
    assert "talking to each other" in res.prompt
    assert "BREAK" in res.prompt
    assert "girl on the left" in res.prompt
    assert "anthro, kemono, cat" in res.prompt
    assert "boy on the right" in res.prompt
    assert "anthro, kemono, fox" in res.prompt


def test_empty_scene_scenery_only():
    session = {
        "id": 101,
        "scenario": "high_school_drama",
        "current_location": "Class 2-1 (Homeroom)",
        "current_npcs": [],
    }
    outcome = {
        "location": "Class 2-1 (Homeroom)",
        "npcs_present": [],
    }

    res = compose_turn_image_prompt(session, outcome=outcome)

    assert res.orientation == "wide"
    assert res.size == DIMENSION_WIDE
    assert "scenery, no humans, landscape" in res.prompt
    assert "classroom" in res.prompt
    assert "1girl" not in res.prompt
    assert "1boy" not in res.prompt


def test_combat_enemy_front_and_center():
    session = {
        "id": 102,
        "scenario": "fantasy",
        "current_location": "Desecrated Crypt",
    }
    outcome = {
        "location": "Desecrated Crypt",
        "nearby_enemies": [{"name": "Goblin Raider", "hp": 40}],
    }

    res = compose_turn_image_prompt(session, outcome=outcome)

    assert res.orientation == "wide"
    assert res.size == DIMENSION_WIDE
    assert "1monster, combat scene, battle stance" in res.prompt
    assert "goblin raider" in res.prompt or "goblin" in res.prompt
    assert "glowing eyes" in res.prompt
    assert "dungeon" in res.prompt or "crypt" in res.prompt


def test_expression_mapping():
    assert "joyful smile" in format_expression_tags("crit_success")
    assert "calm" in format_expression_tags("success")
    assert "annoyed" in format_expression_tags("fail")
    assert "flustered" in format_expression_tags("crit_fail")
    assert "aroused" in format_expression_tags(intimate_context=True)


@pytest.mark.asyncio
async def test_reroll_image_endpoint(monkeypatch):
    from unittest.mock import AsyncMock
    import db
    from api.adventure import reroll_adventure_image, RerollImageRequest

    mock_session = {
        "id": 999,
        "image_gen_enabled": 1,
        "scene_title": "Classroom",
        "narrative": "Story text",
        "current_location": "Classroom",
        "scenario": "furry_high_school_drama",
        "history": [{"scene_title": "Classroom", "narrative": "Story text"}]
    }

    monkeypatch.setattr(db, "get_session", lambda sid: mock_session)

    mock_trigger = AsyncMock(return_value="/images/test_scene.webp")
    import api.adventure
    monkeypatch.setattr(api.adventure, "_trigger_scene_image_broadcast", mock_trigger)

    req = RerollImageRequest(session_id=999, user_id=1)
    res = await reroll_adventure_image(req)

    assert res["success"] is True
    assert res["image_url"] == "/images/test_scene.webp"
    mock_trigger.assert_awaited_once()
