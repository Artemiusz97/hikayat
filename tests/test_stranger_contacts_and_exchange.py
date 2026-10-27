from __future__ import annotations

import asyncio
import pytest
from fastapi import HTTPException

import db
import db.core
from mechanics.social.relationships import (
    calculate_contact_exchange_dc,
    is_contact_blocked,
    is_unlocked_contact,
)
from mechanics.social.agent_roster import prune_unmet_preseeded_special_agents
from mechanics.narrative.intent import (
    IntentCategory,
    classify_action_intent,
    is_contact_exchange_action,
)
from db.social import (
    decrement_contact_request_cooldowns,
    get_contact_request_cooldown,
    set_contact_request_cooldown,
)
from api.codex_phone import (
    get_contacts,
    get_lorebook,
    get_phone_state,
    send_npc_message,
)
from api.deps import PhoneMessageRequest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_stranger_contacts.db")
    monkeypatch.setattr(db, "DB_PATH", test_db)
    monkeypatch.setattr(db.core, "DB_PATH", test_db)
    db.init_db()
    return test_db


@pytest.mark.unit
def test_is_unlocked_contact_qualification():
    # Strangers and Acquaintances without explicit unlock provenance are NOT unlocked contacts
    stranger = {"name": "Kazuya Halloway", "relationship_score": 0}
    assert is_unlocked_contact(stranger) is False

    acquaintance = {"name": "Seo-ah Vance", "relationship_score": 50}
    assert is_unlocked_contact(acquaintance) is False

    # < 100 affinity Party Companions do NOT auto-unlock personal Contacts
    assert is_unlocked_contact(stranger, party_names={"kazuya halloway"}) is False

    # Friends with relationship_score >= 100 ARE unlocked contacts
    friend = {"name": "Seo-ah Vance", "relationship_score": 100}
    assert is_unlocked_contact(friend) is True

    best_friend = {"name": "Li Vance", "relationship_score": 180}
    assert is_unlocked_contact(best_friend) is True

    # 3 explicit provenance flags unlock contacts at any affinity score (including < 100 dips)
    exchanged = {
        "name": "Seo-ah Vance",
        "relationship_score": 15,
        "basic_info": {"exchanged_contact": True},
    }
    assert is_unlocked_contact(exchanged) is True

    peerpulse = {
        "name": "Seo-ah Vance",
        "relationship_score": 10,
        "basic_info": {"added_via_peerpulse": True},
    }
    assert is_unlocked_contact(peerpulse) is True

    dipped_friend = {
        "name": "Li Vance",
        "relationship_score": 95,
        "basic_info": {"unlocked_via_friendship": True},
    }
    assert is_unlocked_contact(dipped_friend) is True


@pytest.mark.unit
def test_calculate_contact_exchange_dc():
    # Cold Stranger (0..24) base DC is 16; Warm Stranger (25..49) is 15; Acquaintance is 10 / 9
    neutral_npc = {"name": "Student A", "relationship_score": 0, "traits": [], "appearance": {}}
    assert calculate_contact_exchange_dc(neutral_npc, "high_school_drama") == 16

    warm_stranger = {"name": "Student B", "relationship_score": 35, "traits": [], "appearance": {}}
    assert calculate_contact_exchange_dc(warm_stranger, "high_school_drama") == 15

    early_acq = {"name": "Student C", "relationship_score": 60, "traits": [], "appearance": {}}
    assert calculate_contact_exchange_dc(early_acq, "high_school_drama") == 10

    close_acq = {"name": "Student D", "relationship_score": 85, "traits": [], "appearance": {}}
    assert calculate_contact_exchange_dc(close_acq, "high_school_drama") == 9

    # Shameless / Flirty reduces DC
    open_npc = {
        "name": "Seo-ah Vance",
        "relationship_score": 0,
        "unlocked_traits": ["flirty", "confident"],
        "appearance": {"erotic_openness": "shameless"},
    }
    dc_open = calculate_contact_exchange_dc(open_npc, "high_school_drama")
    assert 11 <= dc_open < 16

    # Shy / Guarded / Tsundere increases DC
    guarded_npc = {
        "name": "Tsundere Peer",
        "relationship_score": 0,
        "unlocked_traits": ["shy", "guarded", "tsundere"],
        "appearance": {"erotic_openness": "guarded"},
    }
    dc_guarded = calculate_contact_exchange_dc(guarded_npc, "high_school_drama")
    assert 16 < dc_guarded <= 20


@pytest.mark.unit
def test_contact_request_cooldown_db_lifecycle():
    user_id = 99881
    sess_id = db.create_session(
        user_id,
        "solo",
        1,
        "normal",
        "direct",
        False,
        scenario="high_school_drama",
    )

    assert get_contact_request_cooldown(sess_id, "Seo-ah Vance") == 0

    set_contact_request_cooldown(sess_id, "Seo-ah Vance", hours=24, until_next_day=True)
    mins = get_contact_request_cooldown(sess_id, "Seo-ah Vance")
    assert 0 < mins <= 24 * 60

    with db.get_conn() as conn:
        conn.execute("UPDATE sessions SET current_day=2, current_minute=500 WHERE id=?", (sess_id,))

    decrement_contact_request_cooldowns(sess_id)
    assert get_contact_request_cooldown(sess_id, "Seo-ah Vance") == 0


@pytest.mark.unit
def test_contact_exchange_intent_classification():
    text1 = "📱 Ask for Seo-ah's Phone Number / Contact Info [CHA DC 14]"
    assert is_contact_exchange_action(text1) is True
    assert classify_action_intent(text1).category == IntentCategory.PHONE_CONTACT_EXCHANGE

    text2 = "Can I have your number or add you on Line?"
    assert is_contact_exchange_action(text2) is True
    assert classify_action_intent(text2).category == IntentCategory.PHONE_CONTACT_EXCHANGE

    text3 = "Exchange phone contacts with Kazuya"
    assert is_contact_exchange_action(text3) is True
    assert classify_action_intent(text3).category == IntentCategory.PHONE_CONTACT_EXCHANGE

    assert is_contact_exchange_action("Ask about the student council Gala budget") is False
    assert is_contact_exchange_action("Attack the shadow monster") is False


@pytest.mark.api
def test_api_filtering_strangers_vs_lore():
    user_id = 99882
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
        0,
        "seo_ah_vance",
        "Seo-ah Vance",
        delta_score=2,
        race="beastfolk:fennec",
        gender="female",
        basic_info={
            "role": "Student Council President",
            "grade": "Senior",
            "club": "Student Council",
            "mannerisms": "Fiddles with keychain",
            "description": "Articulate senior student council leader",
            "met_in_person": True,
        },
        appearance={
            "eye_color": "golden-ochre",
            "hair_color": "warm sand-gold",
            "physique": "Full-Figured & Voluptuous",
        },
    )

    db.upsert_contact(
        sess_id,
        0,
        "li_vance",
        "Li Vance",
        delta_score=105,
        race="beastfolk:fennec",
        gender="female",
        basic_info={
            "role": "Close Classmate",
            "grade": "Senior",
            "description": "Lifelong friendly peer",
        },
    )

    # 1. Contacts API: Only Li Vance is unlocked, Seo-ah (stranger) is excluded
    contacts_res = asyncio.run(get_contacts(sess_id, user_id=None))
    c_names = [c["name"] for c in contacts_res["contacts"]]
    assert "Li Vance" in c_names
    assert "Seo-ah Vance" not in c_names

    # 2. Phone API: Only Li Vance is present in Messenger contacts
    phone_res = asyncio.run(get_phone_state(sess_id, user_id=None))
    p_names = [c["name"] for c in phone_res["contacts"]]
    assert "Li Vance" in p_names
    assert "Seo-ah Vance" not in p_names

    # 3. Lorebook API: Seo-ah Vance is present in Known Characters with is_contact == False
    lore_res = asyncio.run(get_lorebook(sess_id))
    seo_lore = next((e for e in lore_res["entities"] if e["name"] == "Seo-ah Vance"), None)
    li_lore = next((e for e in lore_res["entities"] if e["name"] == "Li Vance"), None)
    assert seo_lore is not None
    assert seo_lore["role"] == "Student Council President"
    assert seo_lore["relationship_score"] == 2
    assert seo_lore["is_contact"] is False
    assert li_lore is not None
    assert li_lore["is_contact"] is True


@pytest.mark.api
def test_legacy_special_agent_pruning_and_provenance_healing():
    user_id = 99883
    char = db.create_character(user_id=user_id, name="Rizal", char_class="Operative", scenario="anomalous_incursions")
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

    # 1. Unmet 0-affinity pre-seeded Special Agent with auto-generated "Past History: ..." lore
    import json
    db.upsert_contact(
        sess_id,
        char["id"],
        "unmet_agent",
        "Bima Saputra",
        delta_score=0,
        basic_info={"role": "Senior Operative", "is_special_agent": True, "contact_added": True},
    )
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE contacts SET intimate_memories_json=? WHERE session_id=? AND npc_id=?",
            (json.dumps(["Past History: Graduated from S.O.A.I. Field Academy."]), sess_id, "unmet_agent"),
        )

    # 2. Met < 100 Special Agent with stale pre-seeded contact_added=True and NO explicit provenance
    db.upsert_contact(
        sess_id,
        char["id"],
        "met_agent",
        "Putri Wijaya",
        delta_score=40,
        basic_info={
            "role": "Junior Operative",
            "is_special_agent": True,
            "met_in_person": True,
            "contact_added": True,
        },
    )

    pruned_count = prune_unmet_preseeded_special_agents(sess_id)
    assert pruned_count >= 1
    assert db.get_contact(sess_id, "unmet_agent", char["id"]) is None

    healed_putri = db.get_contact(sess_id, "met_agent", char["id"])
    assert healed_putri is not None
    assert not healed_putri["basic_info"].get("contact_added")

    # Putri appears in Known Characters (Lorebook) but NOT in personal Contacts or Phone DMs
    contacts_res = asyncio.run(get_contacts(sess_id, user_id=user_id))
    assert [c["name"] for c in contacts_res["contacts"]] == []

    lore_res = asyncio.run(get_lorebook(sess_id))
    lore_names = [e["name"] for e in lore_res["entities"] if e.get("entity_type") == "person"]
    assert "Putri Wijaya" in lore_names
    assert "Bima Saputra" not in lore_names


@pytest.mark.api
def test_contact_persistence_hostile_blocking_and_dispatch_separation():
    user_id = 99884
    char = db.create_character(user_id=user_id, name="Rizal", char_class="Operative", scenario="anomalous_incursions")
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

    # Reach Friend (100) -> stamps unlocked_via_friendship=True
    db.upsert_contact(
        sess_id,
        char["id"],
        "nadia_kusuma",
        "Nadia Kusuma",
        delta_score=100,
        basic_info={"role": "Field Medic", "met_in_person": True},
    )
    # Dip to 95 -> remains unlocked Contact!
    db.upsert_contact(sess_id, char["id"], "nadia_kusuma", "Nadia Kusuma", delta_score=-5)
    c_95 = db.get_contact(sess_id, "nadia_kusuma", char["id"])
    assert c_95["relationship_score"] == 95
    assert c_95["basic_info"].get("unlocked_via_friendship") is True
    assert is_unlocked_contact(c_95) is True
    assert is_contact_blocked(c_95) is False

    # Seed an automated dispatch broadcast message
    db.save_phone_message(
        sess_id,
        "metropolitan_anomaly_watch",
        "Metropolitan Anomaly Watch",
        "npc",
        "⚠️ Rift surge detected in Sector 4.",
    )
    phone_res = asyncio.run(get_phone_state(sess_id, user_id=user_id))
    assert "Nadia Kusuma" in [c["name"] for c in phone_res["contacts"]]
    assert all(not c.get("is_dispatch_channel") for c in phone_res["contacts"])
    dispatch_ids = [d["npc_id"] for d in phone_res["dispatch_channels"]]
    assert "metropolitan_anomaly_watch" in dispatch_ids

    # Replying to a read-only dispatch channel is rejected with HTTP 400
    with pytest.raises(HTTPException) as exc_disp:
        asyncio.run(
            send_npc_message(
                sess_id,
                "metropolitan_anomaly_watch",
                PhoneMessageRequest(user_id=user_id, message="Copy that", intent="chat"),
            )
        )
    assert exc_disp.value.status_code == 400

    # Drop Nadia to Hostile (-55 <= -50) -> still in Contacts with is_blocked_contact=True, and DMs blocked!
    db.upsert_contact(sess_id, char["id"], "nadia_kusuma", "Nadia Kusuma", delta_score=-150)
    contacts_hostile = asyncio.run(get_contacts(sess_id, user_id=user_id))["contacts"]
    nadia_entry = next(c for c in contacts_hostile if c["name"] == "Nadia Kusuma")
    assert nadia_entry["relationship_score"] == -55
    assert nadia_entry["is_blocked_contact"] is True

    with pytest.raises(HTTPException) as exc_blk:
        asyncio.run(
            send_npc_message(
                sess_id,
                "nadia_kusuma",
                PhoneMessageRequest(user_id=user_id, message="Hey Nadia", intent="chat"),
            )
        )
    assert exc_blk.value.status_code == 400
    assert "blocked" in str(exc_blk.value.detail).lower()
