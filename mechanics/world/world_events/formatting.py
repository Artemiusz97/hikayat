from __future__ import annotations

import re
from typing import Any

import db
import llm_client

_STAT_LEAK_RE = re.compile(
    r"(\bDC\s*\d+\b|\b\d+\s*HP\b|\b\d+\s*MP\b|\b\d+%\b|\[ITEM_JSON\]|\[GEAR_JSON\]|\[SPELLBOOK_JSON\])",
    re.IGNORECASE,
)


def _sanitize_prose(text: str) -> str:
    if not text:
        return ""
    cleaned = _STAT_LEAK_RE.sub("", str(text))
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def resolve_session_time_and_turn(
    session_id: int,
    current_day: int | None = None,
    current_minute: int | None = None,
    turn_number: int | None = None,
    session: dict[str, Any] | None = None,
) -> tuple[int, int, int]:
    """Resolves (day, minute, turn_number) cleanly from parameters or session fallback."""
    if current_day is None or current_minute is None:
        c_day, c_min, _ = db.get_session_time(session_id)
        current_day = c_day if current_day is None else current_day
        current_minute = c_min if current_minute is None else current_minute
    if turn_number is None:
        sess = session if session is not None else (db.get_session(session_id) or {})
        turn_number = db.infer_session_turn(sess)
    return int(current_day), int(current_minute), int(turn_number)


def resolve_event_description(ev: dict[str, Any], allow_nsfw: bool = True) -> str:
    """Returns SFW fallback description if NSFW is disallowed, otherwise normal description."""
    if int(bool(ev.get("is_nsfw", 0))) and not allow_nsfw:
        fallback = str(ev.get("sfw_fallback_description") or "").strip()
        if fallback:
            return fallback
    return str(ev.get("description") or "")


def _resolve_event_description(ev: dict[str, Any], allow_nsfw: bool) -> str:
    return _sanitize_prose(resolve_event_description(ev, allow_nsfw=allow_nsfw))


def extract_minor_events(
    events_or_snapshot: Any,
    statuses: tuple[str, ...] = ("active", "resolved_aftermath"),
) -> list[dict[str, Any]]:
    """Extracts minor events from an events snapshot dict or raw event list."""
    if not events_or_snapshot:
        return []
    if isinstance(events_or_snapshot, dict):
        raw = events_or_snapshot.get("active_minor_events")
        if raw is None:
            raw = [
                e for e in (events_or_snapshot.get("all_events") or [])
                if isinstance(e, dict) and e.get("entity_type") == "minor_event"
            ]
        items = [e for e in (raw or []) if isinstance(e, dict)]
    elif isinstance(events_or_snapshot, list):
        items = [
            e for e in events_or_snapshot
            if isinstance(e, dict) and e.get("entity_type") == "minor_event"
        ]
    else:
        return []
    if statuses:
        return [e for e in items if e.get("status") in statuses]
    return items


def _extract_list(events_or_snapshot: Any, key: str, entity_type: str) -> list[dict[str, Any]]:
    if not events_or_snapshot:
        return []
    if isinstance(events_or_snapshot, dict):
        items = events_or_snapshot.get(key) or []
        return [e for e in items if isinstance(e, dict)]
    if isinstance(events_or_snapshot, list):
        return [e for e in events_or_snapshot if isinstance(e, dict) and e.get("entity_type", entity_type) == entity_type]
    return []


def format_macro_events_for_z2(
    events_or_snapshot: Any,
    lang: str = "en",
    is_nsfw_enabled: bool | None = None,
) -> str:
    """Formats active Macro World Events for Prompt Zone 2 (Z2), preserving Z1b KV-cache bytes.
    Note: entity_type='minor_event' is strictly excluded from Z2 to prevent KV-cache churn."""
    macros = [
        e for e in _extract_list(events_or_snapshot, "active_macro_events", "macro_event")
        if e.get("entity_type", "macro_event") != "minor_event"
    ]
    if not macros:
        return ""
    allow_nsfw = bool(llm_client.is_nsfw_configured()) if is_nsfw_enabled is None else (bool(is_nsfw_enabled) and bool(llm_client.is_nsfw_configured()))

    lines = ["ACTIVE WORLD EVENTS (Ambient regional context — weave naturally into background atmosphere):"]
    for ev in macros:
        status = str(ev.get("status") or "active")
        if status not in ("active", "resolved_aftermath"):
            continue
        title = _sanitize_prose(str(ev.get("title") or "Regional Event"))
        desc = _resolve_event_description(ev, allow_nsfw=allow_nsfw)
        tag = " [AFTERMATH BUZZ]" if status == "resolved_aftermath" else f" [{str(ev.get('event_subtype') or 'event').upper()}]"
        lines.append(f"- {title}{tag}: {desc}")
    return "\n".join(lines) if len(lines) > 1 else ""


def format_rumors_for_z3(
    events_or_snapshot: Any,
    lang: str = "en",
    is_nsfw_enabled: bool | None = None,
    current_location: str = "",
) -> str:
    """Formats player-discovered Rumors and venue-scoped/claimed Minor Incidents for Prompt Zone 3 (Z3 user prompt)."""
    if isinstance(events_or_snapshot, dict) and "discovered_rumors" in events_or_snapshot:
        rumors = [r for r in (events_or_snapshot.get("discovered_rumors") or []) if isinstance(r, dict)]
    else:
        raw_rumors = _extract_list(events_or_snapshot, "active_rumors", "rumor")
        rumors = [r for r in raw_rumors if bool(r.get("is_discovered"))]

    allow_nsfw = bool(llm_client.is_nsfw_configured()) if is_nsfw_enabled is None else (bool(is_nsfw_enabled) and bool(llm_client.is_nsfw_configured()))

    blocks: list[str] = []
    if rumors:
        lines = ["KNOWN LOCAL RUMORS & GOSSIP (Player-discovered leads):"]
        for rm in rumors:
            status = str(rm.get("status") or "active")
            if status not in ("active", "resolved_aftermath"):
                continue
            title = _sanitize_prose(str(rm.get("title") or "Local Rumor"))
            desc = _resolve_event_description(rm, allow_nsfw=allow_nsfw)
            state_note = " (Resolved Buzz)" if status == "resolved_aftermath" else (" (Actively Investigating)" if rm.get("linked_quest_id") else "")
            lines.append(f"- {title}{state_note}: {desc}")
        if len(lines) > 1:
            blocks.append("\n".join(lines))

    minors = extract_minor_events(events_or_snapshot)

    curr_loc_clean = str(current_location or "").strip().lower()
    curr_loc_leaf = curr_loc_clean.split("➔")[-1].strip()

    minor_lines = ["LOCAL INCIDENTS & CHATTER:"]
    for mev in minors:
        status = str(mev.get("status") or "active")
        if status not in ("active", "resolved_aftermath"):
            continue
        is_linked = bool(mev.get("linked_quest_id"))
        ev_loc = str(mev.get("location_name") or str(mev.get("location_node_id") or "").replace("_", " ")).strip().lower()
        ev_loc_leaf = ev_loc.split("➔")[-1].strip()
        is_venue_match = bool(
            curr_loc_clean
            and ev_loc
            and (
                ev_loc in curr_loc_clean
                or curr_loc_clean in ev_loc
                or (len(ev_loc_leaf) >= 4 and (ev_loc_leaf in curr_loc_leaf or curr_loc_leaf in ev_loc_leaf))
            )
        )
        if is_linked or is_venue_match:
            title = _sanitize_prose(str(mev.get("title") or "Local Incident"))
            desc = _resolve_event_description(mev, allow_nsfw=allow_nsfw)
            state_note = " (Resolved)" if status == "resolved_aftermath" else (" (Actively Investigating)" if is_linked else "")
            minor_lines.append(f"- {title}{state_note}: {desc}")

    if len(minor_lines) > 1:
        blocks.append("\n".join(minor_lines))

    return "\n\n".join(blocks) + "\n\n" if blocks else ""
