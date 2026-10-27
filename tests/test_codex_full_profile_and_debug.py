from __future__ import annotations
import asyncio
import json
import os
import pytest
from api.codex_phone import get_lorebook, get_contacts, get_phone_state, _enrich_factions_list
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


def test_anomalous_incursions_known_characters_excludes_unmet_agents_and_heals_legacy_saves(tmp_path, monkeypatch):
    """Ensure Known Characters / Contacts / Phone / Discord Codex never list unmet Special Agents and heal legacy saves."""
    iso_db = str(tmp_path / "test_anom_known_chars.db")
    monkeypatch.setattr(db, "DB_PATH", iso_db)
    monkeypatch.setattr(db.core, "DB_PATH", iso_db)
    db.init_db()

    from cogs.contacts import build_world_codex_embed
    from mechanics.social.agent_roster import ensure_anomalous_agent_roster
    from mechanics.world.anomalous_events import bootstrap_anomalous_session

    user_id = 9988501
    char = db.create_character(
        user_id=user_id,
        name="Agent Zero",
        gender="Male",
        race="Human",
        char_class="Anomaly Investigator",
        scenario="anomalous_incursions",
    )
    sess_id = db.create_session(
        user_id,
        "solo",
        1,
        "normal",
        "direct",
        False,
        scenario="anomalous_incursions",
        character_id=char["id"],
    )

    bootstrap_anomalous_session(sess_id, "anomalous_incursions", user_id, "public_agency", "Agent Zero")
    _enrich_factions_list(sess_id, user_id=user_id)
    roster = ensure_anomalous_agent_roster(sess_id, "anomalous_incursions")
    assert len(roster) == 44

    # 1. Zero unmet Special Agents in Contacts, Known Characters (Lorebook), Phone, and Discord World Codex
    contacts_res = asyncio.run(get_contacts(sess_id, user_id=user_id))
    assert contacts_res["contacts"] == []

    lore_res = asyncio.run(get_lorebook(sess_id, user_id=user_id))
    person_entities = [e for e in lore_res["entities"] if e.get("entity_type") == "person"]
    assert person_entities == []

    phone_res = asyncio.run(get_phone_state(sess_id, user_id=user_id))
    non_dispatch_phone_contacts = [c for c in phone_res["contacts"] if not c.get("is_dispatch_channel")]
    assert non_dispatch_phone_contacts == []

    _, _, discord_persons = build_world_codex_embed(sess_id, "anomalous_incursions", "Agent Zero", page=0)
    assert discord_persons == []

    # 2. Simulate a legacy save that previously pre-seeded an unmet colleague with is_special_agent + contact_added
    unmet_colleague = next(a for a in roster if a["faction_id"] == "public_agency")
    db.upsert_contact(
        session_id=sess_id,
        character_id=0,
        npc_id=unmet_colleague["npc_id"],
        name=unmet_colleague["name"],
        delta_score=0,
        basic_info={
            "role": unmet_colleague["role"],
            "faction_id": "public_agency",
            "is_special_agent": True,
            "contact_added": True,
        },
    )

    healed_contacts = asyncio.run(get_contacts(sess_id, user_id=user_id))
    assert healed_contacts["contacts"] == []
    healed_lore = asyncio.run(get_lorebook(sess_id, user_id=user_id))
    assert [e for e in healed_lore["entities"] if e.get("entity_type") == "person"] == []
    assert db.get_contact(sess_id, unmet_colleague["name"]) is None

    # 3. Once an agent is physically met in a scene, they DO appear and persist even after moving rooms at score 0
    met_agent = roster[0]
    db.save_session_scene(
        sess_id,
        "Briefing Room",
        f"{met_agent['name']} nods across the briefing table.",
        [],
        [],
        location="City Center ➔ Agency HQ ➔ Briefing Room",
        current_npcs=[{"name": met_agent["name"], "role": met_agent["role"]}],
    )
    # Player moves to empty hallway on Turn 1 without changing affinity
    db.save_session_scene(
        sess_id,
        "Hallway",
        "You step out into the quiet corridor.",
        [],
        [{"turn": 1, "action": "Step into hallway"}],
        location="City Center ➔ Agency HQ ➔ Main Lobby",
        current_npcs=[],
    )

    after_meet_lore = asyncio.run(get_lorebook(sess_id, user_id=user_id))
    met_people = [e["name"] for e in after_meet_lore["entities"] if e.get("entity_type") == "person"]
    assert met_people == [met_agent["name"]]


def test_offscreen_sibling_ripple_hidden_until_met_and_debug_reveal_button_removed(tmp_path, monkeypatch):
    """Ensure off-screen sibling ripples stay hidden until met, and CodexPanel has no inline Debug Reveal button."""
    iso_db = str(tmp_path / "test_sibling_ripple_hidden.db")
    monkeypatch.setattr(db, "DB_PATH", iso_db)
    monkeypatch.setattr(db.core, "DB_PATH", iso_db)
    db.init_db()

    user_id = 9988502
    sess_id = db.create_session(user_id, "solo", 1, "normal", "direct", False, scenario="high_school_drama")

    db.upsert_contact(
        session_id=sess_id,
        character_id=0,
        npc_id="unmet_sibling",
        name="Unmet Sibling",
        delta_score=-2,
        basic_info={"offscreen_ripple_only": True},
        new_general_memory="Player was hostile towards my sibling.",
    )

    lore_before = asyncio.run(get_lorebook(sess_id, user_id=user_id))
    assert "Unmet Sibling" not in [e["name"] for e in lore_before["entities"] if e.get("entity_type") == "person"]

    # Now meet the sibling in-scene -> revealed with the -2 protective friction preserved
    db.save_session_scene(
        sess_id,
        "Courtyard",
        "Unmet Sibling glares from across the bench.",
        [],
        [{"turn": 1}],
        location="Academy ➔ Courtyard",
        current_npcs=[{"name": "Unmet Sibling", "role": "Student"}],
    )
    lore_after = asyncio.run(get_lorebook(sess_id, user_id=user_id))
    sib_entry = next((e for e in lore_after["entities"] if e.get("name") == "Unmet Sibling"), None)
    assert sib_entry is not None
    assert sib_entry["relationship_score"] == -2

    # Verify per-card Debug Reveal toggle button was removed from CodexPanel.jsx while Developer Sandbox support remains
    codex_jsx_path = os.path.join(os.path.dirname(__file__), "..", "web", "src", "components", "Sidebar", "CodexPanel.jsx")
    with open(codex_jsx_path, "r", encoding="utf-8") as f:
        codex_jsx = f.read()
    assert "toggleDebugReveal" not in codex_jsx
    assert "debugToggleOverrides" not in codex_jsx
    assert "codex.debug_reveal'" not in codex_jsx
    assert 'codex.debug_reveal"' not in codex_jsx
    assert "rawNpc.debug_revealed" in codex_jsx
