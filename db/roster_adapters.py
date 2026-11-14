from __future__ import annotations

"""
Internal normalization helpers and read-only legacy roster adapters for `world_roster`.

Bridges unhydrated entries from `sessions.extra_json` (`anomalous_agent_roster`,
`folklore_villager_roster`) and `school_directory` without duplicating entries
already materialized in `world_roster` or `contacts`.
"""

import json
import re
import sqlite3
from typing import Any

ALLOWED_ROSTER_ORIGINS: frozenset[str] = frozenset(
    {
        "venue_seed",
        "role_slot_fill",
        "roaming_merchant",
        "quest_seed",
        "replacement_hire",
        "legacy_adapter",
    }
)
ALLOWED_ROSTER_TIERS: frozenset[str] = frozenset({"seeded", "acquaintance", "promoted"})
ALLOWED_SHIFT_PROFILES: frozenset[str] = frozenset(
    {"day", "evening", "night", "student", "rotating", "roaming_merchant"}
)
ALLOWED_STAFF_STATUSES: frozenset[str] = frozenset({"active", "dead", "arrested", "in_party"})

_STUDENT_GRADE_TOKENS = frozenset({"freshman", "sophomore", "junior", "senior", "student"})


def slugify_npc_id(raw: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(raw or "").strip().lower()).strip("_")


def clamp_affinity(val: Any) -> int:
    try:
        num = int(val)
    except (TypeError, ValueError):
        num = 0
    return max(-100, min(300, num))


def parse_json_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return {}


def parse_json_list(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return []


def is_empty_val(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str):
        return val.strip().lower() in ("", "none", "unknown", "null", "n/a")
    if isinstance(val, (list, dict, tuple, set)):
        return len(val) == 0
    return False


def merge_dict_safely(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for src in (existing, incoming):
        if not isinstance(src, dict):
            continue
        for k, v in src.items():
            if not is_empty_val(v):
                merged[k] = v.strip() if isinstance(v, str) else v
    return merged


def pick_non_empty(*values: Any, default: str = "") -> str:
    for v in values:
        if isinstance(v, str):
            s = v.strip()
            if s:
                return s
    return default


def mirror_anchors_into_basic_info(
    basic_info: dict[str, Any],
    workplace_node_id: str,
    home_node_id: str,
    hangout_node_id: str,
    shift_profile: str,
    residence_unlocked: bool,
) -> dict[str, Any]:
    out = dict(basic_info)
    out["workplace_node_id"] = workplace_node_id
    out["home_node_id"] = home_node_id
    out["hangout_node_id"] = hangout_node_id
    out["shift_profile"] = shift_profile
    out["residence_unlocked"] = bool(residence_unlocked)
    return out


def collect_existing_roster_and_contact_keys(
    conn: sqlite3.Connection,
    session_id: int,
) -> tuple[set[str], set[str]]:
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    sid = int(session_id)

    for tbl in ("world_roster", "contacts"):
        try:
            rows = conn.execute(f"SELECT npc_id, name FROM {tbl} WHERE session_id = ?", (sid,)).fetchall()
        except sqlite3.OperationalError:
            continue
        for r in rows:
            nid = str(r["npc_id"] or "").strip().lower()
            nm = str(r["name"] or "").strip().lower()
            if nid:
                seen_ids.add(nid)
            if nm:
                seen_names.add(nm)

    return seen_ids, seen_names


def _register_legacy_candidate(
    raw_npc_id: Any,
    raw_name: Any,
    seen_ids: set[str],
    seen_names: set[str],
) -> tuple[str, str] | None:
    name = str(raw_name or "").strip()
    npc_id = slugify_npc_id(raw_npc_id or name)
    if not npc_id or not name:
        return None
    name_low = name.lower()
    if npc_id in seen_ids or name_low in seen_names:
        return None
    seen_ids.add(npc_id)
    seen_names.add(name_low)
    return npc_id, name


def _build_legacy_adapted_entry(
    session_id: int,
    *,
    npc_id: str,
    name: str,
    gender: Any = "",
    race: Any = "human",
    role: Any = "",
    affinity_score: Any = 0,
    workplace_node_id: str = "",
    home_node_id: str = "",
    hangout_node_id: str = "",
    shift_profile: str = "day",
    basic_info: dict[str, Any] | None = None,
    appearance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    b_info = mirror_anchors_into_basic_info(
        merge_dict_safely({}, basic_info or {}),
        workplace_node_id=workplace_node_id,
        home_node_id=home_node_id,
        hangout_node_id=hangout_node_id,
        shift_profile=shift_profile,
        residence_unlocked=False,
    )
    return {
        "id": None,
        "session_id": int(session_id),
        "npc_id": npc_id,
        "name": name,
        "gender": str(gender or "").strip().lower(),
        "race": str(race or "human").strip() or "human",
        "role": str(role or "").strip(),
        "origin": "legacy_adapter",
        "tier_status": "seeded",
        "affinity_score": clamp_affinity(affinity_score),
        "met_in_person": False,
        "first_met_turn": None,
        "workplace_node_id": workplace_node_id,
        "home_node_id": home_node_id,
        "hangout_node_id": hangout_node_id,
        "roaming_route": [],
        "shift_profile": shift_profile,
        "staff_status": "active",
        "staff_status_day": 0,
        "is_unique_proprietor": False,
        "residence_unlocked": False,
        "residence_unlock_reason": "",
        "discovered_slots": {},
        "basic_info": b_info,
        "appearance": parse_json_dict(appearance),
        "traits": [],
        "turn_snapshots": {},
        "turn_created": 0,
        "turn_updated": 0,
        "created_at": 0.0,
        "updated_at": 0.0,
    }


def _adapt_agent_entry(sid: int, entry: dict[str, Any], seen_ids: set[str], seen_names: set[str]) -> dict[str, Any] | None:
    if int(entry.get("is_hydrated") or 0) == 1:
        return None
    reg = _register_legacy_candidate(entry.get("npc_id"), entry.get("name"), seen_ids, seen_names)
    if reg is None:
        return None
    npc_id, name = reg
    shift = "student" if entry.get("is_student_agent") else "day"
    if str(entry.get("shift_profile") or "") in ALLOWED_SHIFT_PROFILES:
        shift = str(entry["shift_profile"])
    role = entry.get("role") or entry.get("agent_class") or ""
    return _build_legacy_adapted_entry(
        sid,
        npc_id=npc_id,
        name=name,
        gender=entry.get("gender"),
        race=entry.get("race") or "human",
        role=role,
        affinity_score=entry.get("initial_affinity") or 0,
        workplace_node_id=pick_non_empty(
            entry.get("workplace_node_id"), entry.get("primary_node_id"), entry.get("primary_facility")
        ),
        home_node_id=pick_non_empty(entry.get("home_node_id"), entry.get("residence_node_id")),
        hangout_node_id=pick_non_empty(
            entry.get("hangout_node_id"), entry.get("secondary_node_id"), entry.get("secondary_facility")
        ),
        shift_profile=shift,
        basic_info={
            "role": role,
            "grade": entry.get("grade") or "",
            "club": entry.get("club") or "",
            "clique": entry.get("clique") or "",
            "faction_id": entry.get("faction_id") or "",
            "faction": entry.get("faction_name") or "",
            "rank_title": entry.get("rank_title") or "",
            "agent_class": entry.get("agent_class") or "",
            "agent_tier": entry.get("agent_tier"),
            "primary_facility": entry.get("primary_facility") or "",
            "secondary_facility": entry.get("secondary_facility") or "",
            "social_role_type": entry.get("social_role_type") or "",
            "age_group": entry.get("age_group") or "",
            "is_special_agent": bool(entry.get("is_special_agent", True)),
            "is_student_agent": bool(entry.get("is_student_agent", False)),
            "anomalous_npc_tag": entry.get("anomalous_npc_tag") or "",
            "description": entry.get("personality_summary") or "",
        },
        appearance=entry.get("appearance"),
    )


def _adapt_folklore_entry(sid: int, entry: dict[str, Any], seen_ids: set[str], seen_names: set[str]) -> dict[str, Any] | None:
    if entry.get("hydrated"):
        return None
    reg = _register_legacy_candidate(entry.get("npc_id"), entry.get("name"), seen_ids, seen_names)
    if reg is None:
        return None
    npc_id, name = reg
    home = pick_non_empty(entry.get("home_node_id"), entry.get("home_node"))
    return _build_legacy_adapted_entry(
        sid,
        npc_id=npc_id,
        name=name,
        gender=entry.get("gender"),
        race=entry.get("race") or "human",
        role=entry.get("role"),
        affinity_score=entry.get("initial_affinity") or 0,
        workplace_node_id=pick_non_empty(entry.get("workplace_node_id"), home),
        home_node_id=home,
        hangout_node_id=pick_non_empty(entry.get("hangout_node_id"), entry.get("village_id")),
        shift_profile="day",
        basic_info={
            "role": entry.get("role") or "",
            "rank_title": entry.get("rank_title") or "",
            "folklore_village": entry.get("folklore_village") or "",
            "village_id": entry.get("village_id") or "",
            "is_folklore_villager": True,
            "is_sovereign": bool(entry.get("is_sovereign", False)),
            "is_royal_heir": bool(entry.get("is_royal_heir", False)),
            "merchant_type": entry.get("merchant_type") or "",
            "description": entry.get("personality_summary") or "",
        },
        appearance=entry.get("appearance"),
    )


def _adapt_school_row(sid: int, sr: sqlite3.Row, seen_ids: set[str], seen_names: set[str]) -> dict[str, Any] | None:
    reg = _register_legacy_candidate(sr["npc_id"], sr["name"], seen_ids, seen_names)
    if reg is None:
        return None
    npc_id, name = reg
    grade_val = str(sr["grade"] or "").strip()
    shift = "student" if grade_val.lower() in _STUDENT_GRADE_TOKENS else "day"
    workplace = str(sr["primary_facility"] or "").strip()
    hangout = str(sr["secondary_facility"] or "").strip()
    return _build_legacy_adapted_entry(
        sid,
        npc_id=npc_id,
        name=name,
        gender=sr["gender"],
        race=sr["race"] or "human",
        role=sr["role"],
        affinity_score=0,
        workplace_node_id=workplace,
        home_node_id="",
        hangout_node_id=hangout,
        shift_profile=shift,
        basic_info={
            "role": sr["role"] or "",
            "grade": grade_val,
            "club": sr["club"] or "",
            "clique": sr["clique"] or "",
            "primary_facility": workplace,
            "secondary_facility": hangout,
            "sibling_name": sr["sibling_name"] or "",
            "description": sr["personality_summary"] or "",
        },
    )


def adapt_legacy_rosters(
    conn: sqlite3.Connection,
    session_id: int,
    seen_ids: set[str],
    seen_names: set[str],
) -> list[dict[str, Any]]:
    """Adapts unhydrated legacy NPC rosters in priority order without persisting or duplicating."""
    sid = int(session_id)
    adapted: list[dict[str, Any]] = []

    extra_obj: dict[str, Any] = {}
    try:
        s_row = conn.execute("SELECT extra_json FROM sessions WHERE id = ?", (sid,)).fetchone()
        if s_row and s_row["extra_json"]:
            extra_obj = parse_json_dict(s_row["extra_json"])
    except sqlite3.OperationalError:
        extra_obj = {}

    for key, builder in (
        ("anomalous_agent_roster", _adapt_agent_entry),
        ("folklore_villager_roster", _adapt_folklore_entry),
    ):
        roster_list = extra_obj.get(key)
        if not isinstance(roster_list, list):
            continue
        for entry in roster_list:
            if not isinstance(entry, dict):
                continue
            item = builder(sid, entry, seen_ids, seen_names)
            if item is not None:
                adapted.append(item)

    try:
        sd_rows = conn.execute(
            """SELECT * FROM school_directory
               WHERE session_id = ? AND COALESCE(is_hydrated, 0) = 0
               ORDER BY id ASC""",
            (sid,),
        ).fetchall()
    except sqlite3.OperationalError:
        sd_rows = []

    for sr in sd_rows:
        item = _adapt_school_row(sid, sr, seen_ids, seen_names)
        if item is not None:
            adapted.append(item)

    return adapted
