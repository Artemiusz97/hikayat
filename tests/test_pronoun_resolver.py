import pytest
from game_engine.pronoun_resolver import (
    strip_pronoun_tags,
    format_pronouns_for_prompt,
    build_actor_registry,
    tag_narrative_pronouns,
    annotate_turn_pronouns,
)


def test_strip_pronoun_tags():
    raw = "Ayane smiled. She said hello to him."
    tagged = '<ref char="Ayane Vance" role="Class Representative">She</ref> said hello to <ref char="Kenji">him</ref>.'
    assert strip_pronoun_tags(tagged) == "She said hello to him."
    assert strip_pronoun_tags("") == ""
    assert strip_pronoun_tags(None) == ""
    assert format_pronouns_for_prompt(tagged) == "She said hello to him."


def test_build_actor_registry():
    party = [{"name": "Kenji", "gender": "male", "class": "Warrior"}]
    npcs = [
        {"name": "Ayane Vance", "gender": "female", "role": "Class Representative"},
        {"name": "Prof. Rowan", "gender": "male", "role": "Instructor"},
    ]
    actors, default_f, default_m = build_actor_registry(
        party=party,
        npcs_present=npcs,
        dialogue_partner="Ayane Vance",
    )

    actor_names = [a["name"] for a in actors]
    assert "Kenji" in actor_names
    assert "Ayane Vance" in actor_names
    assert "Prof. Rowan" in actor_names

    assert default_f is not None
    assert default_f["name"] == "Ayane Vance"
    assert default_m is not None
    # Dialogue partner priority or player priority for male
    assert default_m["name"] == "Kenji"


def test_tag_narrative_pronouns_single_female():
    narrative = "Ayane Vance stepped forward. She looked down at her notes and adjusted her collar."
    tagged = tag_narrative_pronouns(
        narrative,
        party=[{"name": "Kenji", "gender": "male"}],
        npcs_present=[{"name": "Ayane Vance", "gender": "female", "role": "Class Representative"}],
        dialogue_partner="Ayane Vance",
    )

    assert '<ref char="Ayane Vance"' in tagged
    assert strip_pronoun_tags(tagged) == narrative


def test_tag_narrative_pronouns_multi_gender():
    narrative = "Kenji stood quietly. He nodded to Ayane. She returned his greeting with a warm smile."
    tagged = tag_narrative_pronouns(
        narrative,
        party=[{"name": "Kenji", "gender": "male"}],
        npcs_present=[{"name": "Ayane Vance", "gender": "female", "role": "Class Rep"}],
        dialogue_partner="Ayane Vance",
    )

    # He and his -> Kenji
    assert '<ref char="Kenji"' in tagged
    assert '>He</ref>' in tagged
    assert '>his</ref>' in tagged
    # She -> Ayane Vance
    assert '<ref char="Ayane Vance" role="Class Rep">She</ref>' in tagged
    assert strip_pronoun_tags(tagged) == narrative


def test_tag_narrative_pronouns_subject_switch():
    narrative = "Ayane checked her desk. She seemed nervous. Meanwhile, Elena walked inside. She took her seat quietly."
    tagged = tag_narrative_pronouns(
        narrative,
        party=[{"name": "Kenji", "gender": "male"}],
        npcs_present=[
            {"name": "Ayane Vance", "gender": "female", "role": "Student"},
            {"name": "Elena Cross", "gender": "female", "role": "Student"},
        ],
    )

    # First part mentions Ayane, so pronoun resolves to Ayane
    assert '<ref char="Ayane Vance"' in tagged
    # Second part mentions Elena, so sentence resolves to Elena
    assert '<ref char="Elena Cross"' in tagged
    assert strip_pronoun_tags(tagged) == narrative


def test_annotate_turn_pronouns():
    turn_result = {
        "outcome_narrative": "She handed over the assignment.",
        "next_narrative": "Ayane waited patiently. She glanced at the clock.",
        "narrative": "She smiled warmly.",
        "npcs_present": [{"name": "Ayane Vance", "gender": "female", "role": "Rep"}],
        "dialogue_partner": "Ayane Vance",
    }

    annotated = annotate_turn_pronouns(turn_result, session=None, party=[{"name": "Hero", "gender": "male"}])

    for key in ("outcome_narrative", "next_narrative", "narrative"):
        assert '<ref char="Ayane Vance"' in annotated[key]
        assert "She" in annotated[key]


def test_dialogue_vocative_quote_does_not_hijack_attribution():
    """Verify vocative addressee inside quotation marks ('Thank you, Artemiusz') does not set the speech tag speaker."""
    narrative = (
        'Ayane Vance offers a soft smile. '
        '"Thank you, Artemiusz. It\'s a bit of a mess today," she says, her voice carrying a calm cadence. '
        'She glances briefly at her phone, checking for messages from Lucas Nakamura before looking back at you.'
    )
    party = [{"name": "Artemiusz", "gender": "male", "role": "Tech Prodigy", "is_player": True}]
    npcs = [
        {"name": "Ayane Vance", "gender": "female", "role": "Theater Set Painter"},
        {"name": "Lucas Nakamura", "gender": "male", "role": "Student"},
        {"name": "Kevin Nakamura", "gender": "male", "role": "Delinquent"},
    ]

    tagged = tag_narrative_pronouns(
        narrative,
        party=party,
        npcs_present=npcs,
        dialogue_partner="Ayane Vance",
    )

    # Ayane Vance is the speaker, NOT Artemiusz
    assert '<ref char="Ayane Vance" role="Theater Set Painter">she</ref> says' in tagged
    assert '<ref char="Ayane Vance" role="Theater Set Painter">her</ref> voice' in tagged
    # Artemiusz must NOT be tagged as saying "Thank you, Artemiusz"
    assert '<ref char="Artemiusz"' not in tagged
    # Lucas Nakamura must not collide with Kevin Nakamura
    assert '<ref char="Kevin Nakamura"' not in tagged
    assert strip_pronoun_tags(tagged) == narrative


def test_shared_surname_token_disambiguation():
    """Verify shared surnames like 'Nakamura' or 'Vance' do not match the wrong person."""
    narrative = "Lucas Nakamura opened the door. He asked for Ayane."
    party = [{"name": "Hero", "gender": "male"}]
    npcs = [
        {"name": "Kevin Nakamura", "gender": "male", "role": "Delinquent"},
        {"name": "Lucas Nakamura", "gender": "male", "role": "Student"},
    ]

    tagged = tag_narrative_pronouns(
        narrative,
        party=party,
        npcs_present=npcs,
    )

    # He refers to Lucas Nakamura, NOT Kevin Nakamura
    assert '<ref char="Lucas Nakamura"' in tagged
    assert '<ref char="Kevin Nakamura"' not in tagged
    assert strip_pronoun_tags(tagged) == narrative


def test_second_person_pov_prevents_player_self_attribution():
    """Verify 3rd-person pronouns in a clause addressing the player as 'you' do not resolve to the player."""
    narrative = 'He stepped closer before looking back at you with a curious smile.'
    party = [{"name": "Artemiusz", "gender": "male", "role": "Tech Prodigy"}]
    npcs = [{"name": "Andrew Vance", "gender": "male", "role": "Artist"}]

    tagged = tag_narrative_pronouns(
        narrative,
        party=party,
        npcs_present=npcs,
    )

    # The person looking back at 'you' must be Andrew Vance, not the player himself
    assert '<ref char="Andrew Vance"' in tagged
    assert '<ref char="Artemiusz"' not in tagged
    assert strip_pronoun_tags(tagged) == narrative
