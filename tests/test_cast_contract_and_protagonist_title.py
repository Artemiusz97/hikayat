"""
Regression tests for the stage-plan cast contract (A/B), protagonist-title exclusivity (C),
and quest-only-hostility zone tags (Anomalous Incursions has no Safe Hub / Frontier tags).
"""
from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

import pytest

from game_engine.npcs.descriptor_presence import (
    detect_unregistered_onscreen_actors,
    has_descriptor_physical_presence,
    protagonist_role_tokens,
)

pytestmark = pytest.mark.unit

PLAYER = {"name": "Artemiusz", "gender": "male", "char_class": "Bureau Forensic Investigator"}
PARTY = [[PLAYER]]
ROLE_TOKS = protagonist_role_tokens(PARTY)

TURN_PROSE = (
    "The creature lets out a distorted screech. The investigator scrambles toward you on all fours, "
    "his eyes wide with terror as he points toward the darkened kiosk behind you."
)


# ---------------------------------------------------------------------------
# C: protagonist role tokens
# ---------------------------------------------------------------------------

def test_protagonist_role_tokens_extracted():
    assert {"investigator", "forensic", "bureau"} <= ROLE_TOKS


def test_protagonist_title_never_confirms_npc_descriptor():
    npc = {"name": "Elias Voss", "gender": "male", "role": "Investigator"}
    narr = "The investigator stumbles out from behind the pillar, clutching a scanner."
    assert has_descriptor_physical_presence(npc, narr)
    assert not has_descriptor_physical_presence(npc, narr, exclude_tokens=ROLE_TOKS)


def test_pronoun_linker_ignores_player_role_words_for_npc_match():
    from game_engine.pronoun_resolver import tag_narrative_pronouns
    narr = "An investigator kneels by the pillar. He studies the cracks."
    tagged = tag_narrative_pronouns(
        narr,
        party=[{"name": "Artemiusz", "gender": "male", "char_class": "Bureau Forensic Investigator"}],
        npcs_present=[{"name": "Elias Voss", "gender": "male", "descriptor": "investigator"}],
    )
    assert 'char="Elias Voss"' not in tagged
    assert 'char="Artemiusz"' not in tagged


# ---------------------------------------------------------------------------
# B: deterministic detection
# ---------------------------------------------------------------------------

def test_detects_unlisted_actor_even_with_protagonist_title_when_you_is_addressed():
    v = detect_unregistered_onscreen_actors(TURN_PROSE, present_npcs=[], exclude_tokens=ROLE_TOKS)
    assert [x["noun"] for x in v] == ["investigator"]


def test_protagonist_title_without_second_person_is_not_flagged():
    narr = "The investigator crouches over the fragments, gloved fingers trembling."
    assert detect_unregistered_onscreen_actors(narr, present_npcs=[], exclude_tokens=ROLE_TOKS) == []


@pytest.mark.parametrize(
    "narr",
    [
        '"A man in a coat was asking about you," she says.',
        "You recall the man who questioned you last week.",
        "On the screen, a man gestures wildly at the camera.",
        "The man left an hour ago.",
        "You consider calling an investigator about the fragments.",
        "If a woman walked in now, you would run.",
    ],
)
def test_detection_ignores_mentions_memories_screens_and_departures(narr):
    assert detect_unregistered_onscreen_actors(narr, present_npcs=[]) == []


def test_unlisted_speaker_attributed_outside_quotes_is_flagged():
    narr = '"A man in a coat was asking about you," the vendor says.'
    v = detect_unregistered_onscreen_actors(narr, present_npcs=[])
    assert [x["noun"] for x in v] == ["vendor"]


def test_definite_mention_is_anaphoric_to_present_npc():
    narr = "The man scrambles to his feet and wipes the blood from his forehead."
    present = [{"name": "Elias Voss", "gender": "male"}]
    assert detect_unregistered_onscreen_actors(narr, present_npcs=present) == []


def test_indefinite_new_person_flagged_despite_present_npc():
    narr = "A woman in a red scarf sprints past the turnstiles."
    present = [{"name": "Elias Voss", "gender": "male"}]
    v = detect_unregistered_onscreen_actors(narr, present_npcs=present)
    assert v and v[0]["gender"] == "female"


def test_arrive_event_covers_mention():
    narr = "A woman in a red scarf sprints past the turnstiles."
    events = [{"type": "arrive", "npc": "Mira Sol", "gender": "female", "descriptor": "woman in a red scarf"}]
    assert detect_unregistered_onscreen_actors(narr, present_npcs=[], cast_events=events) == []


# ---------------------------------------------------------------------------
# B: bounded repair call
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_repair_registers_flagged_actor_as_confirmed_arrive():
    from game_engine.npcs.cast_contract import repair_cast_contract_violations
    result = {"outcome_narrative": TURN_PROSE, "next_narrative": "", "cast_events": []}
    fake = AsyncMock(return_value={"arrivals": [
        {"name": "Elias Voss", "gender": "male", "descriptor": "trembling man in a torn coat", "role": "Field Agent", "mention": "The investigator"},
        {"name": "Extra Person", "gender": "female"},  # beyond flagged count -> dropped
    ]})
    with patch("llm_client.call_llm_json", fake):
        added = await repair_cast_contract_violations(result, present_npcs=[], party=PARTY, session={})
    assert [e["npc"] for e in added] == ["Elias Voss"]
    assert added[0]["_contract_confirmed"] is True
    assert result["cast_events"][-1]["npc"] == "Elias Voss"
    assert fake.await_count == 1


@pytest.mark.asyncio
async def test_repair_skipped_without_violations_and_never_spawns_on_failure():
    from game_engine.npcs.cast_contract import repair_cast_contract_violations
    fake = AsyncMock(side_effect=RuntimeError("offline"))
    with patch("llm_client.call_llm_json", fake):
        clean = {"outcome_narrative": "The lights flicker over the empty platform.", "next_narrative": ""}
        assert await repair_cast_contract_violations(clean, present_npcs=[], party=PARTY) == []
        assert fake.await_count == 0
        bad = {"outcome_narrative": TURN_PROSE, "next_narrative": "", "cast_events": []}
        assert await repair_cast_contract_violations(bad, present_npcs=[], party=PARTY) == []
        assert bad["cast_events"] == []
        assert bad["_cast_contract_violations"]


# ---------------------------------------------------------------------------
# A: apply_cast_events grounding / enrichment / naming
# ---------------------------------------------------------------------------

def _session() -> Dict[str, Any]:
    return {
        "id": None,
        "scenario": "anomalous_incursions",
        "current_location": "Sovereign-Core City Center ➔ Obelisk Central Transit Terminal ➔ Main Area",
        "current_node_id": "",
        "history": [],
    }


def _apply(events: List[dict], narrative: str | None):
    from game_engine.npcs.cast_planner import CastPlan, apply_cast_events
    plan = CastPlan(present_npcs=[], dialogue_partners=[], bystander_npcs=[], departing_npcs=[])
    return apply_cast_events(plan, events, session=_session(), party=PARTY, persist_db=False, narrative_text=narrative)


def test_arrive_grounded_by_name_is_enriched():
    narr = "Elias Voss stumbles out from behind the pillar, clutching a scanner."
    plan, rej = _apply([{"type": "arrive", "npc": "Elias Voss", "gender": "male", "descriptor": "man in a torn coat"}], narr)
    assert not rej
    npc = plan.present_npcs[0]
    assert npc["name"] == "Elias Voss" and npc["gender"] == "male" and npc["descriptor"] == "man in a torn coat"


def test_ungrounded_new_arrival_rejected():
    narr = "The platform is silent except for the hum of the lights."
    plan, rej = _apply([{"type": "arrive", "npc": "Elias Voss", "gender": "male"}], narr)
    assert not plan.present_npcs and rej and "not physically present" in rej[0]["reason"]


def test_contract_confirmed_arrival_accepted_without_name_in_prose():
    plan, rej = _apply(
        [{"type": "arrive", "npc": "Elias Voss", "gender": "male", "_contract_confirmed": True}],
        TURN_PROSE,
    )
    assert not rej and plan.present_npcs[0]["name"] == "Elias Voss"


def test_generic_role_arrival_gets_personal_name():
    narr = "A field agent in a torn coat staggers through the turnstiles."
    plan, rej = _apply(
        [{"type": "arrive", "npc": "Field Agent", "gender": "male", "_contract_confirmed": True}], narr
    )
    assert not rej
    npc = plan.present_npcs[0]
    assert npc["name"].lower() != "field agent"
    assert npc.get("descriptor") == "Field Agent"


def test_legacy_call_without_narrative_still_approves():
    plan, rej = _apply([{"type": "arrive", "npc": "Elias Voss"}], None)
    assert not rej and plan.present_npcs


def test_stage_plan_includes_cast_continuity_rule():
    from game_engine.npcs.cast_planner import CastPlan, render_stage_plan
    txt = render_stage_plan(CastPlan(present_npcs=[], dialogue_partners=[], bystander_npcs=[], departing_npcs=[]))
    assert "CAST CONTINUITY" in txt and "RECENT HISTORY" in txt


def test_cast_event_schema_accepts_and_coerces_arrival_meta():
    from models.llm_schemas import CastEvent
    ev = CastEvent(type="arrive", npc="Elias Voss", gender="male", descriptor="", role=None)
    assert ev.gender == "male" and ev.descriptor is None and ev.role is None


# ---------------------------------------------------------------------------
# Zone tags: Anomalous Incursions omits Safe Hub / Frontier
# ---------------------------------------------------------------------------

def _zone_tags(monkeypatch, scen_key: str) -> Dict[str, Dict[str, Any]]:
    import db
    import mechanics.world.locations.formatting as fmt
    import mechanics.world.waypoints as wps
    tree = {"Sovereign-Core City Center": {}, "Ashen Wasteland Frontier": {}}
    monkeypatch.setattr(fmt, "ensure_session_locations_seeded", lambda *a, **k: None)
    monkeypatch.setattr(fmt, "get_discovered_location_tree", lambda *a, **k: tree)
    monkeypatch.setattr(wps, "get_location_waypoint_markers", lambda *a, **k: {})
    monkeypatch.setattr(db, "get_session", lambda *a, **k: None)
    monkeypatch.setattr(db, "get_session_locations", lambda *a, **k: [])
    out = fmt.get_zone_summary_tree(0, scen_key=scen_key)
    return {z["zone_name"]: z for z in out}


def test_anomalous_incursions_has_no_safe_hub_or_frontier_tags(monkeypatch):
    zones = _zone_tags(monkeypatch, "anomalous_incursions")
    all_tags = [t for z in zones.values() for t in (z.get("active_tags") or [])]
    assert not any("Safe Hub" in t or "Frontier" in t for t in all_tags), all_tags
    assert not any(z.get("is_hub") for z in zones.values())


def test_fantasy_keeps_safe_hub_and_frontier_tags(monkeypatch):
    zones = _zone_tags(monkeypatch, "fantasy")
    assert any("Safe Hub" in t for t in zones["Sovereign-Core City Center"]["active_tags"])
    assert any("Frontier" in t for t in zones["Ashen Wasteland Frontier"]["active_tags"])
