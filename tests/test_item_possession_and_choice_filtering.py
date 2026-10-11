import pytest
import db
from game_engine.choices_cleaner import clean_choices_impl
from game_engine.prompts import SYSTEM_PROMPT
from game_engine.prompt_layout import TURN_OUTPUT_RULES
from mechanics.social.physical_state import build_physical_prompt_block


def test_unowned_food_offering_is_filtered_when_inventory_empty():
    """Verify that action choices offering unowned food (e.g. onigiri) are filtered when player inventory is empty."""
    raw_choices = [
        {"label": "Offer Yuki half your onigiri to share while you both review notes", "stat": "CHA", "requirement": 6},
        {"label": "Ask Yuki what she thinks might be inside that hidden locker", "stat": "INT", "requirement": 5},
        {"label": "Notice Yuki's watch and ask if she has time before first period starts", "stat": "PER", "requirement": 5},
        {"label": "Thank Yuki, excuse yourself, and look around the room", "stat": "NONE", "requirement": 0},
    ]
    char_empty = {"inventory": []}
    cleaned = clean_choices_impl(
        None,
        raw_choices,
        scenario="high_school_drama",
        location="Class 2-B",
        char=char_empty,
        dialogue_partner="Yuki Kuroda",
    )
    labels = [c["label"] for c in cleaned]
    assert not any("onigiri" in l.lower() for l in labels), f"Unowned onigiri choice should have been filtered: {labels}"
    assert any("hidden locker" in l.lower() for l in labels)
    assert any("excuse yourself" in l.lower() for l in labels)


def test_owned_item_offering_is_preserved():
    """Verify that choices offering items the player actually carries in inventory are preserved."""
    char_with_items = {
        "inventory": [
            {"name": "Wooden Kendo Sword"},
            {"name": "Scientific Calculator"},
            {"name": "Folded Yellowed Note (First Clue)"},
        ]
    }
    raw_choices = [
        {"label": "Hand Yuki your wooden sword for inspection", "stat": "CHA", "requirement": 6},
        {"label": "Offer your scientific calculator to help with the equations", "stat": "INT", "requirement": 5},
        {"label": "Offer Yuki half your onigiri to share while you both review notes", "stat": "CHA", "requirement": 6},
        {"label": "Excuse yourself and look around the room", "stat": "NONE", "requirement": 0},
    ]
    cleaned = clean_choices_impl(
        None,
        raw_choices,
        scenario="high_school_drama",
        location="Class 2-B",
        char=char_with_items,
        dialogue_partner="Yuki Kuroda",
    )
    labels = [c["label"] for c in cleaned]
    assert any("wooden sword" in l.lower() for l in labels), "Owned wooden sword offering should be kept"
    assert any("scientific calculator" in l.lower() for l in labels), "Owned calculator offering should be kept"
    assert not any("onigiri" in l.lower() for l in labels), "Unowned onigiri offering must be filtered"


def test_exempt_abstract_gestures_are_preserved():
    """Verify that abstract gestures (hand, smile, notes, perspective) are never mistakenly pruned as unowned items."""
    char_empty = {"inventory": []}
    raw_choices = [
        {"label": "Offer your hand to help Yuki up", "stat": "AGI", "requirement": 6},
        {"label": "Offer a warm smile to Yuki to ease the tension", "stat": "CHA", "requirement": 5},
        {"label": "Share your study notes with Yuki", "stat": "INT", "requirement": 5},
        {"label": "Share your perspective on the mystery with Yuki", "stat": "INT", "requirement": 6},
        {"label": "Excuse yourself and look around the room", "stat": "NONE", "requirement": 0},
    ]
    cleaned = clean_choices_impl(
        None,
        raw_choices,
        scenario="high_school_drama",
        location="Class 2-B",
        char=char_empty,
        dialogue_partner="Yuki Kuroda",
    )
    labels = [c["label"] for c in cleaned]
    assert any("offer your hand" in l.lower() for l in labels)
    assert any("warm smile" in l.lower() for l in labels)
    assert any("study notes" in l.lower() for l in labels)
    assert any("perspective" in l.lower() for l in labels)


def test_db_session_inventory_filters_unowned_food_and_gear():
    """Verify that DB session lookup filters unowned onigiri/sandwich while preserving owned/exempt choices."""
    uid = 998877
    db.create_character(uid, "Artemiusz", "STR")
    db.add_item(uid, "Wooden Kendo Sword", "Weapon")
    db.add_item(uid, "Scientific Calculator", "Accessory")
    sess_id = db.create_session(uid, "solo", 1, "normal", "balanced", False, scenario="high_school_drama")

    raw_choices = [
        {"label": "Offer Yuki half your onigiri to share while you both review notes", "stat": "CHA", "requirement": 6},
        {"label": "Share some of your sandwich with Leon", "stat": "CHA", "requirement": 6},
        {"label": "Hand Yuki your wooden sword for inspection", "stat": "CHA", "requirement": 6},
        {"label": "Excuse yourself and look around the room", "stat": "NONE", "requirement": 0},
    ]
    cleaned = clean_choices_impl(
        None,
        raw_choices,
        scenario="high_school_drama",
        location="Class 2-B",
        session_id=sess_id,
        dialogue_partner="Yuki Kuroda",
    )
    labels = [c["label"] for c in cleaned]
    assert not any("onigiri" in l.lower() for l in labels), "Character has no onigiri; choice must be filtered"
    assert not any("sandwich" in l.lower() for l in labels), "Character has no sandwich; choice must be filtered"
    assert any("wooden sword" in l.lower() for l in labels), "Character has a wooden sword; choice must be kept"


def test_system_prompt_possession_boundaries_instruction():
    """Verify that SYSTEM_PROMPT contains the Item & Prop Possession Boundaries directive."""
    assert "Item & Prop Possession Boundaries" in SYSTEM_PROMPT
    assert "NO UNGROUNDED TRANSFERS" in SYSTEM_PROMPT
    assert "GROUNDED ACTION CHOICES (`next_choices`)" in SYSTEM_PROMPT
    assert "NEVER offer an item the player does not possess" in SYSTEM_PROMPT


def test_turn_output_rules_item_possession_grounding():
    """Verify that TURN_OUTPUT_RULES enforces item possession grounding for next_choices."""
    assert "ITEM POSSESSION GROUNDING" in TURN_OUTPUT_RULES
    assert "NEVER generate choices offering, giving, or sharing an item" in TURN_OUTPUT_RULES


def test_physical_state_continuity_directive_ownership():
    """Verify that build_physical_prompt_block injects ownership continuity instructions."""
    block = build_physical_prompt_block({"id": 1, "scenario": "high_school_drama"}, party=[])
    assert "Items, food, or props held by or associated with NPCs belong strictly to that NPC" in block
    assert "In `next_choices`, NEVER generate choices offering or sharing items the player does not carry" in block
