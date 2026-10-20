import asyncio
import json
import os
import pytest
from api.codex_phone import get_lorebook, get_contacts
import db


def test_locale_parity_for_dossier_and_debug_keys():
    """Ensure all 5 locale JSON files contain the new dossier and debug reveal keys."""
    locales_dir = os.path.join(os.path.dirname(__file__), "..", "web", "src", "locales")
    expected_keys = [
        "view_full_profile",
        "view_summary",
        "debug_reveal",
        "debug_revealed_badge",
        "disclosure_level",
    ]
    languages = ["en", "de", "zh", "ms", "pl"]
    
    for lang in languages:
        path = os.path.join(locales_dir, f"{lang}.json")
        assert os.path.exists(path), f"Locale file {lang}.json missing"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        codex_section = data.get("codex", {})
        for key in expected_keys:
            assert key in codex_section, f"Key 'codex.{key}' missing from {lang}.json"
            assert isinstance(codex_section[key], str) and len(codex_section[key]) > 0


def test_stranger_character_enrichment_and_debug_profile():
    """Verify that get_lorebook enriches stranger characters with progressive disclosure and debug_profile."""
    user_id = 99883
    sess_id = db.create_session(
        user_id,
        "solo",
        1,
        "normal",
        "direct",
        False,
        scenario="high_school_drama",
    )
    
    # Add a stranger person entity to contacts with low affinity (so it's a stranger)
    db.upsert_contact(
        sess_id,
        "seo_ah_vance",
        "Seo-ah Vance",
        delta_score=10,
        race="beastfolk:fennec",
        gender="female",
        basic_info={
            "role": "Student Council Treasurer",
            "grade": "Senior",
            "club": "Student Council",
            "mannerisms": "Fiddles with keychain",
            "description": "Articulate senior student council leader",
            "traits": ["Cautious", "Meticulous", "Bookworm"],
            "likes": ["Budgeting", "Earl Grey Tea", "Quiet Libraries"],
            "dislikes": ["Wasted Funds", "Loud Chewing"],
        },
        appearance={
            "eye_color": "golden-ochre",
            "hair_color": "warm sand-gold",
            "physique": "Full-Figured & Voluptuous",
            "breast_size": "Full C-Cup",
        },
    )
    
    lore_data = asyncio.run(get_lorebook(sess_id, user_id=user_id))
    assert "entities" in lore_data
    
    entities = lore_data["entities"]
    seo_ah = next((e for e in entities if e.get("name") == "Seo-ah Vance"), None)
    assert seo_ah is not None, "Seo-ah Vance should be found in lorebook entities"
    
    # Check progressive disclosure: at low affinity/info_level=1, intimate is gated, traits gated
    assert seo_ah.get("info_level", 0) <= 1
    
    # Check that debug_profile is attached with complete unmasked data
    assert "debug_profile" in seo_ah
    dbg = seo_ah["debug_profile"]
    assert dbg["info_level"] == 3
    assert dbg["debug_revealed"] is True
    assert "unlocked_traits" in dbg
    assert len(dbg["unlocked_traits"]) > 0
    assert "preferences" in dbg
    assert "dislikes" in dbg
    assert "intimate_sections" in dbg
    assert "appearance" in dbg


def test_contacts_debug_profile_attached():
    """Verify that get_contacts also attaches debug_profile to contacts."""
    user_id = 99884
    sess_id = db.create_session(
        user_id,
        "solo",
        1,
        "normal",
        "direct",
        False,
        scenario="high_school_drama",
    )
    
    db.upsert_contact(
        sess_id,
        "li_vance",
        "Li Vance",
        delta_score=110,
        race="beastfolk:fennec",
        gender="female",
        basic_info={
            "role": "Close Classmate",
            "grade": "Senior",
            "description": "Lifelong friendly peer",
        },
    )
    
    contacts_data = asyncio.run(get_contacts(sess_id, user_id=user_id))
    contacts = contacts_data.get("contacts", [])
    li_v = next((c for c in contacts if c.get("name") == "Li Vance"), None)
    assert li_v is not None, "Li Vance should be present in contacts"
    
    assert "debug_profile" in li_v
    dbg = li_v["debug_profile"]
    assert dbg["info_level"] == 3
    assert "intimate_sections" in dbg
    assert "appearance" in dbg
