"""
Unit tests for the dynamic location, 24-hour clock lighting, active room props,
weather particles, and atmospheric mood overhaul in image_prompt_composer.py.
"""
from __future__ import annotations

import pytest
from mechanics.narrative.image_prompt_composer import (
    compose_turn_image_prompt,
    format_time_lighting_tags,
    format_scenery_archetype_tags,
    format_props_tags,
    format_weather_and_atmosphere_tags,
    format_mood_tags,
)


def test_time_lighting_phases_indoor_and_outdoor():
    # 1. Early Morning (06:00 = 360 min)
    indoor_dawn, p_dawn = format_time_lighting_tags(minute=360, is_indoor=True)
    assert p_dawn == "Early Morning"
    assert "dawn light through window" in indoor_dawn

    outdoor_dawn, _ = format_time_lighting_tags(minute=360, is_indoor=False)
    assert "sunrise" in outdoor_dawn or "dawn" in outdoor_dawn

    # 2. Morning (09:00 = 540 min)
    indoor_morn, p_morn = format_time_lighting_tags(minute=540, is_indoor=True)
    assert p_morn == "Morning"
    assert "sunbeams" in indoor_morn or "morning sunlight" in indoor_morn

    # 3. Afternoon (14:00 = 840 min)
    indoor_aft, p_aft = format_time_lighting_tags(minute=840, is_indoor=True)
    assert p_aft == "Afternoon"
    assert "afternoon sunlight" in indoor_aft

    # 4. Evening / Sunset (18:00 = 1080 min)
    indoor_eve, p_eve = format_time_lighting_tags(minute=1080, is_indoor=True)
    assert p_eve == "Evening"
    assert "sunset" in indoor_eve or "golden hour" in indoor_eve

    outdoor_eve, _ = format_time_lighting_tags(minute=1080, is_indoor=False)
    assert "sunset" in outdoor_eve or "golden hour" in outdoor_eve

    # 5. Night (21:00 = 1260 min)
    indoor_night, p_night = format_time_lighting_tags(minute=1260, is_indoor=True)
    assert p_night == "Night"
    assert "dark outside window" in indoor_night
    assert "lamp" in indoor_night or "interior room lights" in indoor_night

    outdoor_night, _ = format_time_lighting_tags(minute=1260, is_indoor=False)
    assert "starry sky" in outdoor_night or "moonlight" in outdoor_night

    # 6. Midnight (02:00 = 120 min)
    indoor_mid, p_mid = format_time_lighting_tags(minute=120, is_indoor=True)
    assert p_mid == "Midnight"
    assert "pitch black outside window" in indoor_mid

    outdoor_mid, _ = format_time_lighting_tags(minute=120, is_indoor=False)
    assert "pitch black sky" in outdoor_mid or "midnight" in outdoor_mid


def test_scenery_archetype_recognition():
    # Chemistry Lab
    tags, is_in = format_scenery_archetype_tags(location="Science Annex ➔ Advanced Chemistry Lab")
    assert is_in is True
    assert "chemistry laboratory" in tags
    assert "beakers" in tags or "test tubes" in tags

    # Infirmary
    tags, is_in = format_scenery_archetype_tags(location="Main Academy Campus ➔ School Infirmary")
    assert is_in is True
    assert "school infirmary" in tags
    assert "clinic bed" in tags or "white partition curtains" in tags

    # Library
    tags, is_in = format_scenery_archetype_tags(location="Grand Academy Library ➔ Restricted Stacks")
    assert is_in is True
    assert "library" in tags
    assert "bookshelves" in tags

    # Rooftop (Outdoor)
    tags, is_in = format_scenery_archetype_tags(location="Main Campus Building ➔ School Rooftop")
    assert is_in is False
    assert "school rooftop" in tags
    assert "chain-link" in tags or "open sky" in tags

    # Tavern
    tags, is_in = format_scenery_archetype_tags(location="Oakhaven Town ➔ The Prancing Griffin Tavern")
    assert is_in is True
    assert "tavern" in tags
    assert "hearth" in tags or "oak tables" in tags

    # Dungeon
    tags, is_in = format_scenery_archetype_tags(location="Underground Crypt ➔ Dungeon Cell 4")
    assert is_in is True
    assert "dungeon" in tags
    assert "iron-barred" in tags or "stone" in tags


def test_room_props_and_focal_point_formatting():
    # Focal point Player's Desk + authored props
    raw_props = ["Teacher's Podium", "Green Chalkboard", "Window Sill Planters"]
    tags = format_props_tags(props_data=raw_props, focal_point="Player's Desk")

    assert "wooden student desk" in tags
    assert "podium" in tags
    assert "chalkboard" in tags


def test_weather_and_atmosphere_particles():
    # Rain
    res_rain = format_weather_and_atmosphere_tags(
        session={"weather": "rainy"},
        outcome={"narrative": "A downpour lashes against the glass as thunder rumbles."},
        is_indoor=True,
        time_phase="Evening"
    )
    assert "rain" in res_rain
    assert "window" in res_rain or "reflections" in res_rain

    # Snow
    res_snow = format_weather_and_atmosphere_tags(
        session={"season": "winter"},
        outcome={"narrative": "Snowflakes drift softly over the courtyard."},
        is_indoor=False,
        time_phase="Morning"
    )
    assert "snow" in res_snow


def test_mood_and_emotional_atmosphere():
    # Intimate scene
    intimate_mood = format_mood_tags(action={"intent": "intimate_act"}, outcome={}, is_intimate=True)
    assert "intimate atmosphere" in intimate_mood or "romantic mood" in intimate_mood

    # Combat scene
    combat_mood = format_mood_tags(action={"intent": "combat_attack"}, outcome={}, is_combat=True)
    assert "dynamic lighting" in combat_mood or "action scene" in combat_mood

    # Stealth scene
    stealth_mood = format_mood_tags(action={"intent": "stealth_covert"}, outcome={})
    assert "shadows" in stealth_mood or "dim lighting" in stealth_mood


def test_full_turn_prompt_composition_sunset_infirmary():
    session = {
        "id": 888,
        "scenario": "high_school_drama",
        "current_minute": 1050,  # 17:30 Evening / Sunset
        "current_location": "Main Academy Building ➔ School Infirmary",
        "current_npcs": [
            {
                "name": "Alicja Yamamoto",
                "race": "human",
                "gender": "female",
                "appearance": {
                    "eye_color": "emerald green",
                    "hair_color": "silver",
                    "hair_style": "long",
                    "outfit_style": "school uniform",
                },
            }
        ],
        "physical_state": {
            "props": {"Clinic Bed": "Present", "White Partition Curtains": "Present"}
        }
    }
    outcome = {
        "dialogue_partner": "Alicja Yamamoto",
        "current_minute": 1050,
        "location": "Main Academy Building ➔ School Infirmary",
        "focal_point": "Clinic Bed",
    }
    action = {
        "label": "sit next to her on the bed",
        "check": {"tier": "success"}
    }

    res = compose_turn_image_prompt(session, outcome=outcome, action=action)

    assert res.orientation == "portrait"
    assert "1girl" in res.prompt
    assert "silver hair" in res.prompt
    assert "school infirmary" in res.prompt
    assert "sunset" in res.prompt or "golden hour" in res.prompt
    assert "clinic bed" in res.prompt
    assert "shallow depth of field" in res.prompt
