import pytest
import db
import asyncio
from mechanics.social.relationships import (
    is_unlocked_contact,
    calculate_contact_exchange_dc,
)
from mechanics.narrative.intent import (
    classify_action_intent,
    is_contact_exchange_action,
    IntentCategory,
)
from db.social import (
    get_contact_request_cooldown,
    set_contact_request_cooldown,
    decrement_contact_request_cooldowns,
)
from api.codex_phone import get_contacts, get_phone_state, get_lorebook


def test_is_unlocked_contact_qualification():
    # Strangers with low affinity are NOT unlocked contacts
    stranger = {"name": "Kazuya Halloway", "relationship_score": 0}
    assert is_unlocked_contact(stranger) is False

    acquaintance = {"name": "Seo-ah Vance", "relationship_score": 50}
    assert is_unlocked_contact(acquaintance) is False

    # Friends with relationship_score >= 100 ARE unlocked contacts
    friend = {"name": "Seo-ah Vance", "relationship_score": 100}
    assert is_unlocked_contact(friend) is True

    best_friend = {"name": "Li Vance", "relationship_score": 180}
    assert is_unlocked_contact(best_friend) is True

    # Party companions ARE unlocked contacts regardless of affinity
    assert is_unlocked_contact(stranger, party_names={"kazuya halloway"}) is True

    # Contact explicitly added via successful contact exchange check
    explicit_c = {
        "name": "Seo-ah Vance",
        "relationship_score": 10,
        "basic_info": {"contact_added": True},
    }
    assert is_unlocked_contact(explicit_c) is True

    explicit_c2 = {
        "name": "Seo-ah Vance",
        "relationship_score": 10,
        "contact_added": True,
    }
    assert is_unlocked_contact(explicit_c2) is True


def test_calculate_contact_exchange_dc():
    # Base DC is 16
    neutral_npc = {"name": "Student A", "traits": [], "appearance": {}}
    assert calculate_contact_exchange_dc(neutral_npc, "high_school_drama") == 16

    # Shameless / Flirty reduces DC
    open_npc = {
        "name": "Seo-ah Vance",
        "unlocked_traits": ["flirty", "confident"],
        "appearance": {"erotic_openness": "shameless"},
    }
    dc_open = calculate_contact_exchange_dc(open_npc, "high_school_drama")
    assert dc_open < 16
    assert dc_open >= 11

    # Shy / Guarded / Tsundere increases DC
    guarded_npc = {
        "name": "Tsundere Peer",
        "unlocked_traits": ["shy", "guarded", "tsundere"],
        "appearance": {"erotic_openness": "guarded"},
    }
    dc_guarded = calculate_contact_exchange_dc(guarded_npc, "high_school_drama")
    assert dc_guarded > 16
    assert dc_guarded <= 20


def test_contact_request_cooldown_db_lifecycle():
    # Create test session
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

    # Initial cooldown is 0
    assert get_contact_request_cooldown(sess_id, "Seo-ah Vance") == 0

    # Set cooldown (24h / until next day)
    set_contact_request_cooldown(sess_id, "Seo-ah Vance", hours=24)
    mins = get_contact_request_cooldown(sess_id, "Seo-ah Vance")
    assert mins > 0
    assert mins <= 24 * 60

    # Simulate next day arriving in session
    with db.get_conn() as conn:
        conn.execute("UPDATE sessions SET current_day=2, current_minute=500 WHERE id=?", (sess_id,))

    # Cooldown expires because next day arrived
    decrement_contact_request_cooldowns(sess_id)
    assert get_contact_request_cooldown(sess_id, "Seo-ah Vance") == 0


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

    # Regular dialogue or combat actions
    assert is_contact_exchange_action("Ask about the student council Gala budget") is False
    assert is_contact_exchange_action("Attack the shadow monster") is False


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

    # Add a stranger contact
    db.upsert_contact(
        sess_id,
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
        },
        appearance={
            "eye_color": "golden-ochre",
            "hair_color": "warm sand-gold",
            "physique": "Full-Figured & Voluptuous",
        },
    )

    # Add a friend contact
    db.upsert_contact(
        sess_id,
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

    # 2. Phone API: Only Li Vance is present in Line Messenger
    phone_res = asyncio.run(get_phone_state(sess_id, user_id=None))
    p_names = [c["name"] for c in phone_res["contacts"]]
    assert "Li Vance" in p_names
    assert "Seo-ah Vance" not in p_names

    # 3. Lorebook API: Seo-ah Vance is present with full basic profile fields
    lore_res = asyncio.run(get_lorebook(sess_id))
    seo_lore = next((e for e in lore_res["entities"] if e["name"] == "Seo-ah Vance"), None)
    assert seo_lore is not None
    assert seo_lore["role"] == "Student Council President"
    assert seo_lore["grade"] == "Senior"
    assert seo_lore["club"] == "Student Council"
    assert seo_lore["mannerisms"] == "Fiddles with keychain"
    assert seo_lore["description"] == "Articulate senior student council leader"
    assert seo_lore["appearance"]["eye_color"] == "golden-ochre"
    assert seo_lore["relationship_score"] == 2
