"""
Stage-Plan Cast Contract Enforcement (post-narration).

The narrator receives an authoritative STAGE PLAN listing who is present, but may still
depict an unlisted person acting on-screen (often someone carried over from RECENT HISTORY).
This module detects such contract violations and attempts ONE bounded repair:

1. ``detect_unregistered_onscreen_actors`` (deterministic, detect-only) flags unnamed people
   physically acting/speaking in narration who are not in the cast and were not announced.
2. A single utility-model call asks for registration details (personal name, gender,
   descriptor) for ONLY the flagged people.
3. The resulting ``arrive`` events are appended to ``result["cast_events"]`` and still pass
   through ``apply_cast_events`` (schedules, private rooms, 1-arrival open-world cap).

Nothing is ever spawned from prose alone: if the repair call fails or returns nothing,
the violation is only logged and recorded on ``result["_cast_contract_violations"]``.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from game_engine.npcs.descriptor_presence import (
    detect_unregistered_onscreen_actors,
    protagonist_role_tokens,
)

log = logging.getLogger("hikayat.game_engine.npcs.cast_contract")

_REPAIR_SYSTEM_PROMPT = (
    "You are the cast registrar for an interactive fiction engine. The narrator depicted people "
    "acting on-screen without registering them. For EACH flagged person, return registration details. "
    "Rules: give every person a culturally fitting personal name (never a role title like 'Investigator'); "
    "never register the protagonist (addressed as 'you'); skip anyone who is only remembered, quoted, "
    "shown on a screen, or not physically present. Respond with ONLY JSON: "
    '{"arrivals": [{"name": "Personal Name", "gender": "male|female", "descriptor": "short physical '
    'descriptor from the prose", "role": "role or occupation", "mention": "exact flagged mention"}]}'
)


def _player_names(party: Any) -> set:
    names = set()
    for p in (party or []):
        p_obj = p[0] if isinstance(p, (list, tuple)) and p else p
        if isinstance(p_obj, dict) and p_obj.get("name"):
            names.add(str(p_obj["name"]).strip().lower())
    return names


def find_cast_contract_violations(
    result: Dict[str, Any],
    present_npcs: Optional[List[Any]],
    party: Any = None,
    session: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Deterministic, detect-only check over the turn's narration."""
    if not isinstance(result, dict):
        return []
    narrative = f"{result.get('outcome_narrative') or ''}\n\n{result.get('next_narrative') or ''}".strip()
    if not narrative:
        return []
    return detect_unregistered_onscreen_actors(
        narrative,
        present_npcs=present_npcs,
        cast_events=result.get("cast_events") or [],
        exclude_tokens=protagonist_role_tokens(party, session),
    )


async def repair_cast_contract_violations(
    result: Dict[str, Any],
    present_npcs: Optional[List[Any]],
    party: Any = None,
    session: Optional[Dict[str, Any]] = None,
    scenario_label: str = "",
) -> List[Dict[str, Any]]:
    """
    Detects stage-plan violations and, if any, makes one utility-model call to register them as
    ``arrive`` cast events (marked ``_contract_confirmed``). Returns the events appended.
    """
    violations = find_cast_contract_violations(result, present_npcs, party=party, session=session)
    if not violations:
        return []

    result["_cast_contract_violations"] = violations
    log.warning("[CastContract] Unregistered on-screen actors detected: %s", [v["mention"] for v in violations])

    narrative = f"{result.get('outcome_narrative') or ''}\n\n{result.get('next_narrative') or ''}".strip()
    user_prompt = (
        f"SCENARIO: {scenario_label or 'unknown'}\n\n"
        f"NARRATION:\n{narrative[:4000]}\n\n"
        f"FLAGGED PEOPLE (register only these):\n{json.dumps(violations, ensure_ascii=False)}"
    )

    try:
        from llm_client import call_llm_json
        raw = await call_llm_json(
            _REPAIR_SYSTEM_PROMPT,
            user_prompt,
            temperature=0.3,
            max_tokens=600,
            retries=0,
            use_utility=True,
            timeout=25,
        )
    except Exception as e:
        log.warning("[CastContract] Repair call failed; violation logged only: %s", e)
        return []

    arrivals = raw.get("arrivals") if isinstance(raw, dict) else None
    if not isinstance(arrivals, list):
        return []

    player_names = _player_names(party)
    present_lows = {
        str((n.get("name") if isinstance(n, dict) else n) or "").strip().lower()
        for n in (present_npcs or [])
    }
    flagged_genders = {v.get("gender") or "" for v in violations}

    added: List[Dict[str, Any]] = []
    for arr in arrivals[: len(violations)]:
        if not isinstance(arr, dict):
            continue
        name = str(arr.get("name") or "").strip()
        if not name or name.lower() in player_names or name.lower() in present_lows:
            continue
        gender = str(arr.get("gender") or "").strip().lower()
        if gender not in ("male", "female"):
            gender = ""
        # Must correspond to a flagged person (gender-compatible with at least one violation)
        if gender and flagged_genders and not ({gender, ""} & flagged_genders):
            continue
        ev = {
            "type": "arrive",
            "npc": name,
            "reason": f"Cast contract repair: '{arr.get('mention') or violations[0]['mention']}' acted on-screen",
            "gender": gender or None,
            "descriptor": str(arr.get("descriptor") or "").strip() or None,
            "role": str(arr.get("role") or "").strip() or None,
            "_contract_confirmed": True,
        }
        added.append(ev)

    if added:
        existing = list(result.get("cast_events") or [])
        result["cast_events"] = existing + added
        log.info("[CastContract] Registered via repair: %s", [e["npc"] for e in added])
    return added
