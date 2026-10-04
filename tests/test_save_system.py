"""
Unit tests for the Campaign / Slot Saving System in Hikayat.
Verifies save slot creation, validation, overwrite protection, child-table restoration,
character state restoration, save deletion, and character-deletion cascading cleanup.
"""
import time
import pytest
import db
from mechanics.system.save_system import validate_slot_name


@pytest.fixture(autouse=True)
def setup_db():
    db.init_db()


def test_validate_slot_name():
    # Valid names
    assert validate_slot_name("Chapter 1") == "Chapter 1"
    assert validate_slot_name("Before-Boss_Gate") == "Before-Boss_Gate"
    assert validate_slot_name("  Slot A  ") == "Slot A"

    # Invalid names
    with pytest.raises(ValueError, match="empty"):
        validate_slot_name("")

    with pytest.raises(ValueError, match="exceed 32"):
        validate_slot_name("A" * 33)

    with pytest.raises(ValueError, match="invalid characters"):
        validate_slot_name("Slot<Bad>?")


def test_save_requires_active_character_and_session():
    fake_uid = 999990001
    with pytest.raises(ValueError, match="active character"):
        db.save_adventure_slot(fake_uid, "TestSlot")

    # Create character but no active session
    char = db.create_character(fake_uid, "HeroWithoutSession", "Warrior", "A sturdy warrior")
    with pytest.raises(ValueError, match="active adventure"):
        db.save_adventure_slot(fake_uid, "TestSlot")

    db.delete_character(fake_uid)


def test_save_and_load_adventure_slot():
    uid = 999990002
    db.delete_character(uid)
    char = db.create_character(uid, "SaveTester", "Mage", "Arcane scholar")
    char_id = char["id"]

    # Start a test session
    session_id = db.create_session(
        host_user_id=uid, mode="turn", capacity=1, verbosity="normal",
        dialogue_mode="balanced", image_gen_enabled=False, scenario="fantasy"
    )
    db.save_session_scene(
        session_id,
        scene_title="The Sunken Crypt",
        narrative="You stand before the obsidian gate as ancient glyphs glow.",
        choices=[{"text": "Touch the runes", "stat": "int"}],
        history=[],
        location="Obsidian Gate"
    )

    # Seed child records
    db.upsert_lorebook_entity(session_id, "place", "Obsidian Gate", "A monolithic seal of black glass.")
    db.upsert_quest(session_id, "crypt_quest", "Main", "Break the Seal", "Open the obsidian gate.")
    db.add_session_clue(session_id, "ancient_symbol", "A spiral glyph carved in glass.")
    db.upsert_contact(session_id, "thorne", "Archivist Thorne", character_id=char_id)

    # Add custom inventory item & modify vitals
    db.add_item(uid, "Glass Resonance Key", "Key Item", "Vibrates near obsidian.", slot_cost=0)
    db.apply_hp_mp_delta(uid, hp_delta=-10, mp_delta=-5)

    # Save to slot
    res = db.save_adventure_slot(uid, "Pre-Gate Checkpoint")
    assert res["status"] == "saved"
    assert res["slot_name"] == "Pre-Gate Checkpoint"
    assert res["current_location"] == "Obsidian Gate"

    # Verify listing
    saves = db.list_adventure_saves(uid)
    assert len(saves) == 1
    assert saves[0]["slot_name"] == "Pre-Gate Checkpoint"
    assert saves[0]["scene_title"] == "The Sunken Crypt"

    # Modify the active state (simulate advancing the game)
    db.apply_hp_mp_delta(uid, hp_delta=-20, mp_delta=-10)
    db.save_session_scene(
        session_id,
        scene_title="Deep Caverns",
        narrative="You fell down a pit trap into total darkness.",
        choices=[],
        history=[],
        location="Dark Pit"
    )

    # Load the checkpoint
    restored_session = db.load_adventure_slot(uid, "Pre-Gate Checkpoint")
    assert restored_session is not None
    assert restored_session["status"] == "active"
    assert restored_session["scene_title"] == "The Sunken Crypt"
    assert restored_session["current_location"] == "Obsidian Gate"

    # Verify child tables were restored
    restored_id = restored_session["id"]
    lore_entry = db.get_lorebook_entity(restored_id, "Obsidian Gate")
    assert lore_entry is not None
    assert lore_entry["name"] == "Obsidian Gate"

    quests = db.get_session_quests(restored_id)
    assert any(q["quest_id"] == "crypt_quest" for q in quests)

    clues = db.get_session_clues(restored_id)
    assert any(c["title"] == "ancient_symbol" for c in clues)

    contacts = db.get_contacts(restored_id, character_id=char_id)
    assert any(c["name"] == "Archivist Thorne" for c in contacts)

    # Verify inventory and vitals restored
    restored_inv = db.get_inventory(uid)
    assert any(item["name"] == "Glass Resonance Key" for item in restored_inv)

    restored_char = db.get_character(uid)
    assert restored_char["active_session_id"] == restored_id
    assert restored_char["hp"] == char["hp"] - 10
    assert restored_char["mp"] == char["mp"] - 5

    # Cleanup
    db.delete_adventure_save(uid, "Pre-Gate Checkpoint")
    db.delete_character(uid)


def test_save_overwrite_and_deletion():
    uid = 999990003
    char = db.create_character(uid, "SlotMaster", "Rogue", "Swift shadow")
    session_id = db.create_session(
        host_user_id=uid, mode="turn", capacity=1, verbosity="normal",
        dialogue_mode="balanced", image_gen_enabled=False, scenario="fantasy"
    )
    db.save_session_scene(session_id, "Scene A", "First text", [], [], location="Camp")

    # Initial save
    res1 = db.save_adventure_slot(uid, "SlotOne")
    assert res1["status"] == "saved"

    # Attempt save again without overwrite
    res2 = db.save_adventure_slot(uid, "SlotOne", overwrite=False)
    assert res2["status"] == "exists"

    # Overwrite
    db.save_session_scene(session_id, "Scene B", "Second text", [], [], location="Castle")
    res3 = db.save_adventure_slot(uid, "SlotOne", overwrite=True)
    assert res3["status"] == "saved"
    assert res3["current_location"] == "Castle"

    meta = db.get_adventure_save_metadata(uid, "SlotOne")
    assert meta["current_location"] == "Castle"

    # Delete save
    deleted = db.delete_adventure_save(uid, "SlotOne")
    assert deleted is True
    assert len(db.list_adventure_saves(uid)) == 0

    # Cleanup
    db.delete_character(uid)


def test_cascade_delete_character_cleans_saves():
    uid = 999990004
    char = db.create_character(uid, "DoomedHero", "Paladin", "Holy knight")
    char_id = char["id"]
    session_id = db.create_session(
        host_user_id=uid, mode="turn", capacity=1, verbosity="normal",
        dialogue_mode="balanced", image_gen_enabled=False, scenario="fantasy"
    )

    db.save_adventure_slot(uid, "Checkpoint 1")
    db.save_adventure_slot(uid, "Checkpoint 2")
    assert len(db.list_adventure_saves(uid)) == 2

    # Delete character
    db.delete_character(uid)

    with db.get_conn() as conn:
        remaining_saves = conn.execute("SELECT * FROM adventure_saves WHERE character_id = ?", (char_id,)).fetchall()
        assert len(remaining_saves) == 0


def test_max_save_slots_limit():
    uid = 999990005
    db.delete_character(uid)
    char = db.create_character(uid, "LimitTester", "Ranger", "Keen archer")
    session_id = db.create_session(
        host_user_id=uid, mode="turn", capacity=1, verbosity="normal",
        dialogue_mode="balanced", image_gen_enabled=False, scenario="fantasy"
    )

    for i in range(1, 11):
        db.save_adventure_slot(uid, f"Slot {i}")

    saves = db.list_adventure_saves(uid)
    assert len(saves) == 10

    # 11th save should fail
    with pytest.raises(ValueError, match="Maximum save slots reached"):
        db.save_adventure_slot(uid, "Slot 11")

    db.delete_character(uid)


@pytest.mark.asyncio
async def test_async_adb_save_load():
    uid = 999990006
    db.delete_character(uid)
    char = await db.adb(db.create_character, uid, "AsyncHero", "Cleric", "Healer")
    session_id = await db.adb(
        db.create_session,
        host_user_id=uid, mode="turn", capacity=1, verbosity="normal",
        dialogue_mode="balanced", image_gen_enabled=False, scenario="fantasy"
    )

    save_res = await db.adb(db.save_adventure_slot, uid, "AsyncCheckpoint")
    assert save_res["status"] == "saved"

    loaded = await db.adb(db.load_adventure_slot, uid, "AsyncCheckpoint")
    assert loaded["id"] != session_id
    assert loaded["status"] == "active"

    db.delete_character(uid)

