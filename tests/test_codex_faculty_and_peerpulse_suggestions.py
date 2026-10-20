import pytest
from mechanics.system.phone.social_graph import (
    lookup_social_profile,
    get_suggested_peers,
    resolve_social_friend_request,
)


def test_faculty_profile_flagging(monkeypatch):
    """Faculty members must be flagged with is_faculty=True and cannot be direct contacts."""
    session_id = 99888304
    user_id = 837619168597639250

    mock_session = {
        "id": session_id,
        "scenario": "nsfw_furry_high_school_drama",
        "current_location": "Science Lab",
    }
    mock_character = {
        "id": 1,
        "user_id": user_id,
        "name": "Kieran",
    }
    mock_roster = [
        {
            "name": "Dr. Kento Satou",
            "npc_id": "dr_kento_satou",
            "role": "Chemistry Teacher",
            "grade": "Faculty",
            "personality": "Analytical and eccentric",
            "club": "None",
            "facility": "Science Lab",
            "is_hydrated": 1,
        },
        {
            "name": "Henry Sterling",
            "npc_id": "henry_sterling",
            "role": "Transfer Student",
            "grade": "Class 2-B",
            "personality": "Quiet and observant",
            "club": "None",
            "facility": "Classroom 2-B",
            "is_hydrated": 1,
        },
    ]

    monkeypatch.setattr("db.get_session", lambda sid: mock_session)
    monkeypatch.setattr("db.get_character", lambda uid: mock_character)
    monkeypatch.setattr("db.get_school_roster", lambda sid: mock_roster)
    monkeypatch.setattr("db.get_contacts", lambda sid, character_id=0: [])

    # 1. Test Dr. Kento Satou (Faculty)
    faculty_profile = lookup_social_profile(session_id, user_id, "Dr. Kento Satou")
    assert faculty_profile is not None
    assert faculty_profile["is_faculty"] is True
    assert faculty_profile["grade"] == "Faculty"
    assert faculty_profile["is_eligible"] is False

    # 2. Test Henry Sterling (Classmate / Peer)
    peer_profile = lookup_social_profile(session_id, user_id, "Henry Sterling")
    assert peer_profile is not None
    assert peer_profile["is_faculty"] is False
    assert peer_profile["is_already_contact"] is False
    assert peer_profile["grade"] == "Class 2-B"
    assert peer_profile["is_eligible"] is True


def test_get_suggested_peers_excludes_faculty(monkeypatch):
    """Suggested peers list must strictly exclude faculty and prioritize classmates."""
    session_id = 99888304
    user_id = 837619168597639250

    mock_session = {
        "id": session_id,
        "scenario": "nsfw_furry_high_school_drama",
        "current_npcs": [{"name": "Henry Sterling"}],
        "history": [
            {
                "turn": 0,
                "narration": "In the lab with Dr. Satou.",
                "witnessed_by": ["Dr. Kento Satou"],
                "dialogue_partner": "Dr. Kento Satou",
            },
            {
                "turn": 1,
                "narration": "In classroom with Diana.",
                "witnessed_by": ["Diana Yamada"],
            }
        ],
    }
    mock_character = {
        "id": 1,
        "user_id": user_id,
        "name": "Kieran",
    }
    mock_roster = [
        {
            "name": "Dr. Kento Satou",
            "npc_id": "dr_kento_satou",
            "role": "Chemistry Teacher",
            "grade": "Faculty",
            "personality": "Analytical and eccentric",
            "club": "None",
            "facility": "Science Lab",
        },
        {
            "name": "Nurse Patricia Vole",
            "npc_id": "nurse_patricia_vole",
            "role": "School Nurse",
            "grade": "Faculty",
            "personality": "Gentle",
            "club": "None",
            "facility": "Infirmary",
        },
        {
            "name": "Henry Sterling",
            "npc_id": "henry_sterling",
            "role": "Transfer Student",
            "grade": "Class 2-B",
            "personality": "Quiet",
            "club": "None",
            "facility": "Classroom 2-B",
        },
        {
            "name": "Diana Yamada",
            "npc_id": "diana_yamada",
            "role": "Class Representative",
            "grade": "Class 2-B",
            "personality": "Strict",
            "club": "Student Council",
            "facility": "Classroom 2-B",
        },
        {
            "name": "Raphaël Ito",
            "npc_id": "raphael_ito",
            "role": "Art Prodigy",
            "grade": "Class 2-B",
            "personality": "Dramatic",
            "club": "Art Club",
            "facility": "Art Room",
        },
    ]

    monkeypatch.setattr("db.get_session", lambda sid: mock_session)
    monkeypatch.setattr("db.get_character", lambda uid: mock_character)
    monkeypatch.setattr("db.get_school_roster", lambda sid: mock_roster)
    monkeypatch.setattr("db.get_contacts", lambda sid, character_id=0: [])

    suggestions = get_suggested_peers(session_id, user_id, limit=10)

    suggested_names = [s["name"] for s in suggestions]
    # Faculty strictly excluded
    assert "Dr. Kento Satou" not in suggested_names
    assert "Nurse Patricia Vole" not in suggested_names
    for s in suggestions:
        assert s["is_faculty"] is False
        assert s["grade"] != "Faculty"

    # Known classmates prioritized
    assert "Henry Sterling" in suggested_names
    assert "Diana Yamada" in suggested_names
    assert "Raphaël Ito" in suggested_names


def test_resolve_social_friend_request_unlocks_contact(monkeypatch):
    """When a friend request succeeds on an eligible peer, they must be added to contacts and unlocked."""
    session_id = 99888304
    user_id = 837619168597639250

    mock_session = {
        "id": session_id,
        "scenario": "nsfw_furry_high_school_drama",
    }
    mock_character = {
        "id": 1,
        "user_id": user_id,
        "name": "Kieran",
        "cha": 14,
        "level": 1,
    }
    mock_roster = [
        {
            "name": "Henry Sterling",
            "npc_id": "henry_sterling",
            "role": "Transfer Student",
            "grade": "Class 2-B",
            "personality": "Friendly",
            "club": "None",
            "facility": "Classroom 2-B",
        }
    ]

    saved_upserts = []

    def mock_upsert_contact(session_id, npc_id, name, character_id=0, **kwargs):
        record = {"session_id": session_id, "npc_id": npc_id, "name": name, **kwargs}
        saved_upserts.append(record)
        return record

    monkeypatch.setattr("db.get_session", lambda sid: mock_session)
    monkeypatch.setattr("db.get_character", lambda uid: mock_character)
    monkeypatch.setattr("db.get_school_roster", lambda sid: mock_roster)
    monkeypatch.setattr("db.get_contacts", lambda sid, character_id=0: [])
    monkeypatch.setattr("db.get_contact", lambda sid, nid, character_id=0: {
        "id": 10,
        "session_id": sid,
        "npc_id": nid,
        "name": "Henry Sterling",
        "basic_info": {"role": "Transfer Student", "grade": "Class 2-B"}
    })
    monkeypatch.setattr("db.upsert_contact", mock_upsert_contact)
    monkeypatch.setattr("db.get_session_party_npcs", lambda sid: [])
    monkeypatch.setattr("db.get_phone_social_state", lambda sid: {})

    # Force check to succeed
    class MockCheckRes:
        chance = 80
        tier = "success"
        tier_label = "Success"
        succeeded = True

    monkeypatch.setattr("skill_check.resolve_check", lambda *args, **kwargs: MockCheckRes())

    profile = lookup_social_profile(session_id, user_id, "Henry Sterling")
    result = resolve_social_friend_request(mock_session, user_id, profile)

    assert result["accepted"] is True
    assert result.get("check")["succeeded"] is True
    assert profile["is_already_contact"] is True
    assert len(saved_upserts) > 0
    assert saved_upserts[-1]["name"] == "Henry Sterling"
    assert saved_upserts[-1]["basic_info"]["contact_added"] is True


@pytest.mark.asyncio
async def test_get_lorebook_strictly_discovered_characters_only(monkeypatch):
    """Codex Known Characters must strictly show encountered or unlocked characters, excluding phantom faction leaders."""
    from api.codex_phone import get_lorebook

    session_id = 12345
    mock_session = {
        "id": session_id,
        "scenario": "nsfw_furry_high_school_drama",
        "current_npcs": [{"name": "Henry Sterling"}],
        "history": [
            {
                "turn": 1,
                "witnessed_by": ["Dr. Kento Satou"],
                "dialogue_partner": "Dr. Kento Satou",
            }
        ],
    }
    mock_grouped = {
        "person": [
            {"name": "Dr. Kento Satou", "entity_type": "person", "role": "Teacher"},
            {"name": "Harry Johnson", "entity_type": "person", "role": "Faction Leader", "relationship_score": 0},
            {"name": "Henry Sterling", "entity_type": "person", "role": "Student", "relationship_score": 10},
        ]
    }
    mock_contacts = [
        {"name": "Harry Johnson", "relationship_score": 0},
        {"name": "Henry Sterling", "relationship_score": 10},
        {"name": "Raphaël Ito", "relationship_score": 0},
    ]

    monkeypatch.setattr("db.get_session", lambda sid: mock_session)
    monkeypatch.setattr("db.get_character", lambda uid: {"id": 1, "name": "Artem"})
    monkeypatch.setattr("db.get_settings", lambda uid: {"debug_reveal_all_info": 0})
    monkeypatch.setattr("db.get_lorebook", lambda sid: mock_grouped)
    monkeypatch.setattr("db.get_active_commitments", lambda sid: [])
    monkeypatch.setattr("db.get_contacts", lambda sid: mock_contacts)
    monkeypatch.setattr("db.get_school_roster", lambda sid: [])
    monkeypatch.setattr("db.get_session_party_npcs", lambda sid: [])

    result = await get_lorebook(session_id)
    person_entities = [e for e in result["entities"] if e.get("entity_type") == "person"]
    person_names = {p["name"] for p in person_entities}

    # Dr. Satou (witnessed in turn history) MUST be included
    assert "Dr. Kento Satou" in person_names

    # Henry Sterling (current NPC + score > 0) MUST be included
    assert "Henry Sterling" in person_names

    # Harry Johnson (never met, score 0, faction leader) MUST be strictly excluded
    assert "Harry Johnson" not in person_names

    # Raphaël Ito (in contacts table with score 0 and never met) MUST be strictly excluded
    assert "Raphaël Ito" not in person_names

