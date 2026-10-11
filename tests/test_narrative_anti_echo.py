import pytest
import re
from game_engine.keywords import sanitize_narrative_context_echo


@pytest.mark.unit
def test_sanitize_narrative_context_echo_no_echo():
    """Verify that completely new, non-overlapping narrative text is preserved untouched."""
    text = "You draw your blade and deflect the incoming strike with a swift, ringing parry."
    prev_session = {
        "history": [
            {
                "outcome_narrative": "You walked through the quiet forest.",
                "next_narrative": "The trees swayed gently in the autumn wind.",
            }
        ],
        "narrative": "The trees swayed gently in the autumn wind.",
    }
    result = sanitize_narrative_context_echo(text, prev_session, action_label="Parry strike", character_name="Artemiusz")
    assert result == text


@pytest.mark.unit
def test_sanitize_narrative_context_echo_strips_echo_paragraph():
    """Verify that an echoed recap paragraph is stripped while a subsequent new paragraph is kept."""
    prev_turn_outcome = (
        'You give Yuki a quick, easy smile and nod. "Deal. I\'ll bring back whatever\'s inside that locker—training '
        'logs, name lists, scratched initials, the works." You tap your kendo sword resting against the desk edge. '
        '"If it\'s empty, I\'ll tell you so you don\'t waste time on a ghost."'
    )
    prev_turn_next = (
        'Yuki\'s fox ears give a small, appreciative twitch. "Good. The archives have a whole drawer of old athletic '
        'records—coaches\' logs, team rosters from the \'80s and \'90s. Ten minutes, then we split up at the stairwell. '
        'You take the locker, I take the archives." She closes her notebook with a soft click and stands.'
    )

    prev_session = {
        "history": [
            {
                "outcome_narrative": prev_turn_outcome,
                "next_narrative": prev_turn_next,
            }
        ],
        "narrative": prev_turn_next,
    }

    echo_paragraph = (
        'You give Yuki a quick, easy smile and nod. "Deal. I\'ll bring back whatever\'s inside that locker—training '
        'logs, name lists, scratched initials, the works." You tap your kendo sword resting against the desk edge. '
        '"If it\'s empty, I\'ll tell you so you don\'t waste time on a ghost." Yuki\'s fox ears give a small, appreciative twitch. '
        '"Good. The archives have a whole drawer of old athletic records—coaches\' logs, team rosters from the \'80s and \'90s. '
        'Ten minutes, then we split up at the stairwell. You take the locker, I take the archives."'
    )
    new_paragraph = "With the plan settled, you offer a respectful bow of thanks and turn toward the classroom door, stepping out into the bright morning corridor."

    combined_input = f"{echo_paragraph}\n\n{new_paragraph}"

    result = sanitize_narrative_context_echo(
        combined_input,
        prev_session,
        action_label="Thank Yuki and excuse yourself to head to the stairwell",
        character_name="Artemiusz"
    )

    # The echo paragraph must be stripped; only the new paragraph must remain
    assert result == new_paragraph
    assert "Deal. I'll bring back whatever's inside that locker" not in result
    assert "The archives have a whole drawer" not in result


@pytest.mark.unit
def test_sanitize_narrative_context_echo_full_echo_replacement():
    """Verify that when the ENTIRE narrative is an echo, it cleanly falls back without repeating past dialogue."""
    prev_turn_outcome = (
        'You give Yuki a quick, easy smile and nod. "Deal. I\'ll bring back whatever\'s inside that locker—training '
        'logs, name lists, scratched initials, the works." You tap your kendo sword resting against the desk edge.'
    )
    prev_turn_next = (
        'Yuki\'s fox ears give a small, appreciative twitch. "Good. The archives have a whole drawer of old athletic '
        'records. Ten minutes, then we split up at the stairwell. You take the locker, I take the archives."'
    )

    prev_session = {
        "history": [
            {
                "outcome_narrative": prev_turn_outcome,
                "next_narrative": prev_turn_next,
            }
        ],
        "narrative": prev_turn_next,
    }

    full_echo = (
        'You give Yuki a quick, easy smile and nod. "Deal. I\'ll bring back whatever\'s inside that locker—training '
        'logs, name lists, scratched initials, the works." You tap your kendo sword resting against the desk edge. '
        'Yuki\'s fox ears give a small, appreciative twitch. "Good. The archives have a whole drawer of old athletic records. '
        'Ten minutes, then we split up at the stairwell. You take the locker, I take the archives."'
    )

    result = sanitize_narrative_context_echo(
        full_echo,
        prev_session,
        action_label="Thank Yuki and excuse yourself to head to the stairwell",
        character_name="Artemiusz"
    )

    assert "Deal. I'll bring back whatever's inside that locker" not in result
    assert "The archives have a whole drawer" not in result
    assert "Ten minutes, then we split up" not in result
    assert len(result) > 10


@pytest.mark.unit
def test_sanitize_narrative_context_echo_edge_cases():
    """Verify robustness across empty, None, and trivial input values."""
    assert sanitize_narrative_context_echo("", {}) == ""
    assert sanitize_narrative_context_echo(None, {}) is None
    assert sanitize_narrative_context_echo("Hello world.", None) == "Hello world."
    assert sanitize_narrative_context_echo("Hello world.", {}) == "Hello world."
    assert sanitize_narrative_context_echo("Hello world.", {"history": []}) == "Hello world."


@pytest.mark.unit
def test_asymmetric_recency_compaction():
    """Verify that older turns (N-2+) are compacted without dialogue quotes while the latest turn (N-1) preserves full prose."""
    from game_engine.context import _history_text
    history = [
        {
            "character_name": "Artemiusz",
            "label": "Negotiate locker deal with Yuki",
            "tier_label": "Success",
            "outcome_narrative": 'You lean across the desk and hand over the key. "Here is the key," you say quietly. "Make sure no one sees it." Yuki accepts it with a slight grin.',
            "next_narrative": 'The classroom begins to fill with students as the morning bell rings. "See you after fifth period," Yuki whispers.',
        },
        {
            "character_name": "Artemiusz",
            "label": "Thank Yuki and excuse yourself",
            "tier_label": "Action",
            "outcome_narrative": "You give Yuki a brief, polite nod of farewell and slide your bag over your shoulder.",
            "next_narrative": "Stepping out into the hallway, the bright sunlight floods through the high courtyard windows as you head toward the lockers.",
        }
    ]
    formatted = _history_text(history)
    # Turn N-1 (latest turn in history) must retain full verbatim prose
    assert "You give Yuki a brief, polite nod of farewell" in formatted
    assert "Stepping out into the hallway, the bright sunlight floods" in formatted

    # Turn N-2 (older turn) must NOT retain verbatim quoted dialogue
    assert '"Here is the key,"' not in formatted
    assert '"See you after fifth period,"' not in formatted
    assert "Negotiate locker deal with Yuki" in formatted


@pytest.mark.unit
def test_embed_free_action_styling():
    """Verify that free narrative/dialogue choices are styled with free tier and narrative progression title."""
    from cogs.adventure.embeds import build_outcome_embeds, _RESULT_COLORS, _RESULT_TITLES
    import discord

    assert "free" in _RESULT_COLORS
    assert _RESULT_TITLES.get("free") == "📖 STORY PROGRESSION"
    assert _RESULT_COLORS.get("free") == discord.Color.from_rgb(88, 101, 242)

    outcome = {
        "outcome_narrative": "You thank Yuki politely and step into the sunlit hall.",
        "next_narrative": "The corridor is quiet as students gather by the library.",
    }
    embeds = build_outcome_embeds(
        outcome=outcome,
        check_field_name="💬 Action",
        check_field_value="*Thank Yuki and excuse yourself*",
        loot_text="",
        result_display="detailed",
        primary_tier="free"
    )
    assert len(embeds) >= 1
    story_embed = embeds[0]
    assert story_embed.title == "📖 STORY PROGRESSION"
    assert story_embed.color.value == discord.Color.from_rgb(88, 101, 242).value
    assert any(f.name == "💬 Action" and f.value == "*Thank Yuki and excuse yourself*" for f in story_embed.fields)


@pytest.mark.asyncio
async def test_conversational_departure_directive_injection():
    """Verify that [CONVERSATIONAL DEPARTURE & SCENE TRANSITION DIRECTIVE] is injected into the user prompt when has_exited_convo=True."""
    from unittest.mock import patch, AsyncMock
    import game_engine

    session = {
        "id": 999112,
        "scenario": "nsfw_high_school_drama",
        "current_location": "Westlake Academy ➔ 1st Floor ➔ West Corridor",
        "history": [],
        "dialogue_partners": ["Yuki Tanaka"],
        "current_npcs": [{"name": "Yuki Tanaka", "role": "Student"}],
        "turn_order": [12345]
    }
    party = [({"id": 12345, "name": "Artemiusz", "user_id": 12345}, [])]

    class MockCheck:
        succeeded = True
        is_success = True
        tier = "success"
        chance = 100
        tier_label = "Action"

    actions = [{
        "char": party[0][0],
        "label": "Thank Yuki and excuse yourself",
        "stat": "NONE",
        "check": MockCheck(),
        "mp_spent": 0
    }]

    mock_llm_response = {
        "outcome_narrative": "You give a polite nod of thanks and step back toward the hallway.",
        "next_narrative": "The corridor ahead is brightly lit by the morning sun.",
        "next_choices": [{"label": "Head to class", "stat": "NONE", "requirement": 0}]
    }

    with patch("game_engine.call_llm_json", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_llm_response
        result = await game_engine.resolve_turn(session, party, actions)

        assert mock_call.called
        # Locate the primary TurnOutcome narrative call
        from models.llm_schemas import TurnOutcome
        narrative_call = next(
            c for c in mock_call.call_args_list if c[1].get("response_model") == TurnOutcome
        )
        narrative_prompt = narrative_call[0][1]
        assert "[CONVERSATIONAL DEPARTURE & SCENE TRANSITION DIRECTIVE]" in narrative_prompt
        assert "DO NOT reopen the conversation" in narrative_prompt
        assert "The corridor ahead is brightly lit" in result["next_narrative"]


@pytest.mark.asyncio
async def test_same_turn_outcome_echo_in_next_narrative_sanitized():
    """Verify that if LLM repeats outcome_narrative inside next_narrative in the same turn, the echo is stripped."""
    from unittest.mock import patch, AsyncMock
    import game_engine

    session = {
        "id": 999113,
        "scenario": "fantasy",
        "current_location": "Grand Library ➔ Reading Room",
        "history": [],
        "dialogue_partners": [],
        "current_npcs": [],
        "turn_order": [12345]
    }
    party = [({"id": 12345, "name": "Artemiusz", "user_id": 12345}, [])]

    class MockCheck:
        succeeded = True
        is_success = True
        tier = "success"
        chance = 100
        tier_label = "Action"

    actions = [{
        "char": party[0][0],
        "label": "Inspect ancient tome",
        "stat": "INT",
        "check": MockCheck(),
        "mp_spent": 0
    }]

    outcome_text = "You carefully turn the yellowed parchment pages of the ancient tome, uncovering a hidden crest."
    echo_para = "You carefully turn the yellowed parchment pages of the ancient tome, uncovering a hidden crest."
    new_scene_para = "Dust motes dance in the amber light from the stained glass window as the room settles into silence."

    mock_llm_response = {
        "outcome_narrative": outcome_text,
        "next_narrative": f"{echo_para}\n\n{new_scene_para}",
        "next_choices": [{"label": "Read crest", "stat": "INT", "requirement": 5}]
    }

    with patch("game_engine.call_llm_json", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = mock_llm_response
        result = await game_engine.resolve_turn(session, party, actions)

        assert result["outcome_narrative"] == outcome_text
        # The duplicated paragraph in next_narrative must be cleanly removed
        assert result["next_narrative"] == new_scene_para
        assert "You carefully turn the yellowed parchment pages" not in result["next_narrative"]


@pytest.mark.unit
def test_embed_item_action_styling():
    """Verify that ITEM actions are styled cleanly as backpack item actions rather than dice checks."""
    from cogs.adventure.embeds import build_outcome_embeds, _get_choice_skill_emoji

    item_action = {"stat": "ITEM", "label": "Use Minor Healing Potion"}
    emoji = _get_choice_skill_emoji(item_action)
    assert emoji == "🎒"

    embeds = build_outcome_embeds(
        outcome={"outcome_narrative": "You drink the glowing red elixir and feel refreshed.", "next_narrative": "Your vitality is restored."},
        check_field_name="🎒 Action",
        check_field_value="*Use Minor Healing Potion*",
        loot_text="",
        result_display="detailed",
        primary_tier="free"
    )
    assert len(embeds) >= 1
    story_embed = embeds[0]
    assert story_embed.title == "📖 STORY PROGRESSION"
    assert any(f.name == "🎒 Action" and f.value == "*Use Minor Healing Potion*" for f in story_embed.fields)


@pytest.mark.unit
def test_history_text_none_safety():
    """Verify that None, empty dicts, or falsy items in history are safely filtered without producing '- None'."""
    from game_engine.context import _history_text

    corrupted_history = [
        None,
        {},
        "",
        {"character_name": "Artemiusz", "label": "Examine desk", "outcome_narrative": "You look at the desk."},
        None,
    ]
    res = _history_text(corrupted_history)
    assert "None" not in res
    assert "- " in res
    assert "Examine desk" in res
