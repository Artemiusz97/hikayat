"""
Regression tests for unnamed on-screen actors:
- Pronoun linker must never attribute an unnamed man's pronouns to the player.
- Pronoun sanitizer must never singularize object plurals ("the numbers... they are" -> "he is").
- Descriptor-based presence confirmation must rescue DECLARED entities introduced by
  description, while never confirming people who are only mentioned, remembered,
  shown on screens, quoted in dialogue, or departed.
"""
from __future__ import annotations

from typing import Any, Dict

import pytest

from game_engine.npcs.descriptor_presence import (
    find_unnamed_person_mentions,
    has_descriptor_physical_presence,
)
from game_engine.pronoun_resolver import strip_pronoun_tags, tag_narrative_pronouns
from game_engine.keywords import sanitize_npc_pronoun_consistency

pytestmark = pytest.mark.unit

PLAYER = {"name": "Artemiusz", "gender": "male", "role": "Tech Prodigy"}

SCENE_P1 = (
    "The screeching from the pylon intensifies, vibrating in your very teeth. A few yards away, "
    "a man in a disheveled investigator's coat bolts upright from behind a structural pillar, his eyes "
    "wide with panic. He fumbles with a handheld scanner that is emitting a frantic, high-pitched alarm."
)
SCENE_P2_RAW = (
    "Beyond him, near the darkened metro entrance, you see something wrong with the station's clock. "
    "The digital numbers are not merely flickering; they are spinning backward at an impossible speed, "
    "blurring into a white smear of light."
)

INVESTIGATOR: Dict[str, Any] = {
    "name": "Elias Voss",
    "gender": "male",
    "role": "Investigator",
    "descriptor": "man in a disheveled investigator's coat",
}


# ---------------------------------------------------------------------------
# Fix 3: pronoun linker
# ---------------------------------------------------------------------------

def test_unnamed_man_pronouns_never_link_to_player():
    narrative = SCENE_P1 + "\n\n" + SCENE_P2_RAW
    tagged = tag_narrative_pronouns(narrative, party=[PLAYER], npcs_present=[])
    assert 'char="Artemiusz"' not in tagged
    assert strip_pronoun_tags(tagged) == narrative


def test_unnamed_man_pronouns_link_to_declared_descriptor_npc():
    narrative = SCENE_P1 + "\n\n" + SCENE_P2_RAW
    tagged = tag_narrative_pronouns(narrative, party=[PLAYER], npcs_present=[INVESTIGATOR])
    assert 'char="Artemiusz"' not in tagged
    assert '<ref char="Elias Voss" role="Investigator">his</ref> eyes' in tagged
    assert '<ref char="Elias Voss" role="Investigator">He</ref> fumbles' in tagged
    assert strip_pronoun_tags(tagged) == narrative


def test_definite_noun_stays_anaphoric_to_named_npc():
    narrative = "Lucas Nakamura opens the door. The boy hesitates, and he glances at you."
    tagged = tag_narrative_pronouns(
        narrative,
        party=[PLAYER],
        npcs_present=[{"name": "Lucas Nakamura", "gender": "male", "role": "Student"}],
    )
    assert '<ref char="Lucas Nakamura" role="Student">he</ref>' in tagged


def test_third_person_player_narration_still_links_player():
    narrative = "Kenji stood quietly. He nodded to Ayane."
    tagged = tag_narrative_pronouns(
        narrative,
        party=[{"name": "Kenji", "gender": "male"}],
        npcs_present=[{"name": "Ayane Vance", "gender": "female"}],
    )
    assert '<ref char="Kenji"' in tagged


def test_unnamed_mention_detection_skips_quotes_and_pronoun_spans():
    sent = '"A man came by yesterday," she says, as a woman in a red scarf waves.'
    mentions = find_unnamed_person_mentions(sent)
    texts = [m[4].lower() for m in mentions]
    assert not any("a man" == t for t in texts)
    assert any(t.endswith("woman") for t in texts)


# ---------------------------------------------------------------------------
# Fix 4: sanitizer must not singularize object plurals
# ---------------------------------------------------------------------------

def test_sanitizer_preserves_object_plural_they_in_player_only_scene():
    narrative = SCENE_P1 + "\n\n" + SCENE_P2_RAW
    cleaned = sanitize_npc_pronoun_consistency(narrative, session={}, party=[[PLAYER]])
    assert "they are spinning backward" in cleaned
    assert "he is spinning" not in cleaned


def test_sanitizer_preserves_object_plural_they_with_unmentioned_npc():
    para = "The digital numbers are not merely flickering; they are spinning backward."
    session = {"current_npcs": [{"name": "Dr. Kento Satou", "gender": "male"}]}
    cleaned = sanitize_npc_pronoun_consistency(para, session=session, party=[[PLAYER]])
    assert "they are spinning backward" in cleaned


def test_sanitizer_named_singular_they_still_corrected():
    raw = "Satou sighs. Their tail flicks behind them as they reach across the table."
    session = {"current_npcs": [{"name": "Dr. Kento Satou", "gender": "male"}]}
    cleaned = sanitize_npc_pronoun_consistency(raw, session=session, party=[[PLAYER]])
    assert "His tail flicks" in cleaned


# ---------------------------------------------------------------------------
# Fix 2: descriptor presence confirmation (positive)
# ---------------------------------------------------------------------------

def test_descriptor_confirms_declared_actor_physically_acting():
    assert has_descriptor_physical_presence(INVESTIGATOR, SCENE_P1)


def test_descriptor_confirms_renamed_generic_alias():
    ent = {"name": "Elias Voss", "gender": "male", "description": "Investigator — panicked anomaly tracker"}
    narr = "An investigator stumbles out from behind the pillar, clutching a scanner."
    assert has_descriptor_physical_presence(ent, narr)


# ---------------------------------------------------------------------------
# Fix 2: descriptor presence confirmation (must NOT confirm)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "narrative",
    [
        # Only mentioned in NPC dialogue
        '"There was a man in an investigator\'s coat asking about you," she says, leaning closer.',
        # Remembered
        "You recall the disheveled investigator who questioned you last week.",
        # Shown on a screen
        "On the screen, a man in a disheveled investigator's coat gestures wildly.",
        # Departed
        "The disheveled investigator left an hour ago.",
        # Object of the player's thought/action, not acting
        "You consider calling an investigator about the disheveled coat you found.",
        # Hypothetical
        "If a man in an investigator's coat walked in now, you would run.",
    ],
)
def test_descriptor_never_confirms_mentions_memories_screens_or_departures(narrative):
    assert not has_descriptor_physical_presence(INVESTIGATOR, narrative)


def test_descriptor_rejects_gender_contradiction():
    narr = "A woman in a disheveled investigator's coat bolts upright from behind a pillar."
    assert not has_descriptor_physical_presence(INVESTIGATOR, narr)


def test_descriptor_requires_specific_tokens_not_generic_man():
    ent = {"name": "Elias Voss", "gender": "male", "descriptor": "a man"}
    assert not has_descriptor_physical_presence(ent, "A man bolts upright from behind a pillar.")


def test_undeclared_entity_cannot_be_confirmed():
    assert not has_descriptor_physical_presence({}, SCENE_P1)
    assert not has_descriptor_physical_presence(None, SCENE_P1)


# ---------------------------------------------------------------------------
# Fix 2 integration: phantom guard in process_scene_npcs
# ---------------------------------------------------------------------------

@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    import db
    test_db = str(tmp_path / "test_unnamed_actor.db")
    monkeypatch.setattr(db, "DB_PATH", test_db)
    monkeypatch.setattr(db.core, "DB_PATH", test_db)
    db.init_db()
    return db


def _run_scene(isolated_db, result: dict) -> list:
    from game_engine.npcs.reconciliation import process_scene_npcs
    loc = "Neo City ➔ Central Metro ➔ Platform 3"
    session = {"id": None, "scenario": "modern", "current_npcs": []}
    return process_scene_npcs(result, session, loc, loc, actions=[], party=[[PLAYER]])


def test_phantom_guard_keeps_declared_descriptor_actor(isolated_db):
    result = {
        "narrative": SCENE_P1,
        "new_entities": [dict(INVESTIGATOR, type="person", disposition="neutral")],
        "npcs_present": [{"name": "Elias Voss"}],
    }
    names = [n.get("name") if isinstance(n, dict) else n for n in _run_scene(isolated_db, result)]
    assert "Elias Voss" in names


def test_phantom_guard_drops_declared_actor_only_mentioned_in_dialogue(isolated_db):
    result = {
        "narrative": '"A man in an investigator\'s coat was here earlier," the vendor mutters, wiping the counter.',
        "new_entities": [dict(INVESTIGATOR, type="person", disposition="neutral")],
        "npcs_present": [{"name": "Elias Voss"}],
    }
    names = [n.get("name") if isinstance(n, dict) else n for n in _run_scene(isolated_db, result)]
    assert "Elias Voss" not in names
