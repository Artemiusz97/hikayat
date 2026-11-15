"""
Anchor-node schedule system for closed-world NPCs, rotating roamers,
staff shift/rest-day cadence, and residential fog-of-war abstraction.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple

import db
from .locations.residence_fog import (
    SHARED_ABSTRACT_RESIDENCE_NODE,
    can_materialize_npc_residence,
)
from .schedule_blocks import get_detailed_npc_time_phase, get_time_block_key
from .world_schedule import is_weekend


SHIFT_PROFILES: Dict[str, Dict[str, Any]] = {
    "day": {
        "work_windows": [(480, 1080)],       # 08:00 - 18:00
        "hangout_windows": [(1080, 1260)],   # 18:00 - 21:00
        "sleep_windows": [(1260, 1440), (0, 480)],
        "supports_rest_day": True,
        "weekday_only": False,
    },
    "evening": {
        "work_windows": [(840, 1380)],       # 14:00 - 23:00
        "hangout_windows": [(540, 840)],     # 09:00 - 14:00
        "sleep_windows": [(1380, 1440), (0, 540)],
        "supports_rest_day": True,
        "weekday_only": False,
    },
    "night": {
        "work_windows": [(1200, 1440), (0, 300)],  # 20:00 - 05:00
        "hangout_windows": [(840, 1200)],          # 14:00 - 20:00
        "sleep_windows": [(300, 840)],             # 05:00 - 14:00
        "supports_rest_day": True,
        "weekday_only": False,
    },
    "student": {
        "work_windows": [(480, 930)],        # 08:00 - 15:30 weekdays
        "hangout_windows": [(930, 1260)],    # 15:30 - 21:00 (all day weekends)
        "sleep_windows": [(1260, 1440), (0, 480)],
        "supports_rest_day": False,
        "weekday_only": True,
    },
    "rotating": {
        "work_windows": [(420, 660), (960, 1200)],     # 07:00-11:00 & 16:00-20:00
        "hangout_windows": [(660, 960), (1200, 1320)], # 11:00-16:00 & 20:00-22:00
        "sleep_windows": [(1320, 1440), (0, 420)],
        "supports_rest_day": True,
        "weekday_only": False,
    },
    "roaming_merchant": {
        "work_windows": [(480, 1200)],       # 08:00 - 20:00 along rotating route
        "hangout_windows": [(1200, 1260)],   # 20:00 - 21:00
        "sleep_windows": [(1260, 1440), (0, 480)],
        "supports_rest_day": False,
        "weekday_only": False,
    },
}

_SHIFT_ALIASES: Dict[str, str] = {"roaming": "roaming_merchant"}

_ANCHOR_ORIGINS: FrozenSet[str] = frozenset({
    "venue_seed",
    "role_slot_fill",
    "roaming_merchant",
    "replacement_hire",
    "quest_seed",
})

_BLOCK_ORDER: Tuple[str, ...] = (
    "morning",
    "lunch",
    "afternoon",
    "evening",
    "night",
    "commute",
    "class_afternoon",
    "extracurricular",
)

_STATIC_BLOCK_ROLES: Dict[str, Dict[str, str]] = {
    "day": {
        "commute": "home",
        "morning": "work",
        "lunch": "work",
        "class_afternoon": "work",
        "afternoon": "work",
        "extracurricular": "work",
        "evening": "hangout",
        "night": "home",
    },
    "evening": {
        "commute": "home",
        "morning": "hangout",
        "lunch": "hangout",
        "class_afternoon": "work",
        "afternoon": "work",
        "extracurricular": "work",
        "evening": "work",
        "night": "home",
    },
    "night": {
        "commute": "home",
        "morning": "home",
        "lunch": "home",
        "class_afternoon": "home",
        "afternoon": "hangout",
        "extracurricular": "hangout",
        "evening": "work",
        "night": "work",
    },
    "student": {
        "commute": "work",
        "morning": "work",
        "lunch": "work",
        "class_afternoon": "work",
        "afternoon": "hangout",
        "extracurricular": "hangout",
        "evening": "hangout",
        "night": "home",
    },
    "rotating": {
        "commute": "work",
        "morning": "work",
        "lunch": "hangout",
        "class_afternoon": "hangout",
        "afternoon": "hangout",
        "extracurricular": "work",
        "evening": "work",
        "night": "home",
    },
    "roaming_merchant": {
        "commute": "work",
        "morning": "work",
        "lunch": "work",
        "class_afternoon": "work",
        "afternoon": "work",
        "extracurricular": "work",
        "evening": "work",
        "night": "home",
    },
}


def _in_windows(minute: int, windows: List[Tuple[int, int]]) -> bool:
    m = int(minute) % 1440
    return any(start <= m < end for start, end in windows)


def _normalize_shift_profile(raw_profile: Any, has_route: bool = False) -> str:
    cleaned = str(raw_profile or "").strip().lower()
    if cleaned in _SHIFT_ALIASES:
        cleaned = _SHIFT_ALIASES[cleaned]
    if cleaned in SHIFT_PROFILES:
        return cleaned
    if has_route:
        return "roaming_merchant"
    return "day"


def _parse_roaming_route(raw_route: Any) -> List[str]:
    if isinstance(raw_route, str):
        stripped = raw_route.strip()
        if not stripped:
            return []
        if stripped.startswith("["):
            try:
                raw_route = json.loads(stripped)
            except Exception:
                raw_route = [part.strip() for part in stripped.split(",")]
        else:
            raw_route = [part.strip() for part in stripped.split(",")]
    if isinstance(raw_route, (list, tuple)):
        return [str(stop).strip() for stop in raw_route if str(stop or "").strip()]
    return []


def _extract_lookup_key(npc: Mapping[str, Any]) -> str:
    basic = npc.get("basic_info") if isinstance(npc.get("basic_info"), Mapping) else {}
    return str(npc.get("npc_key") or npc.get("npc_id") or npc.get("name") or basic.get("name") or "").strip()


def _canonical_seed_key(npc: Mapping[str, Any]) -> str:
    """Produces a deterministic hash key consistent across DB rows and raw NPC dicts."""
    basic = npc.get("basic_info") if isinstance(npc.get("basic_info"), Mapping) else {}
    raw_name = str(npc.get("name") or basic.get("name") or "").strip().lower()
    if raw_name:
        slug = re.sub(r"[^a-z0-9]+", "_", raw_name).strip("_")
        if slug:
            return slug
    return _extract_lookup_key(npc).lower() or "npc"


def _deterministic_seed_int(seed_key: str) -> int:
    digest = hashlib.md5(seed_key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _merge_roster_context(
    npc: Mapping[str, Any],
    session_id: Optional[int],
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """
    Merges caller NPC dict with world_roster DB truth (excluding legacy adapters
    in DB lookup per Ruling 6) so persisted locks, staff statuses, and home nodes stay fresh.
    """
    eff: Dict[str, Any] = dict(npc) if isinstance(npc, Mapping) else {}
    in_basic = eff.get("basic_info") if isinstance(eff.get("basic_info"), Mapping) else {}
    eff_basic: Dict[str, Any] = dict(in_basic)

    db_row: Optional[Dict[str, Any]] = None
    lookup_key = _extract_lookup_key(eff)
    if session_id and lookup_key and not eff.get("_roster_premerged"):
        try:
            db_row = db.get_world_roster_npc(int(session_id), lookup_key, include_legacy_rosters=False)
        except Exception:
            db_row = None

    if isinstance(db_row, dict):
        db_basic = db_row.get("basic_info") if isinstance(db_row.get("basic_info"), Mapping) else {}
        merged_basic = dict(db_basic)
        merged_basic.update(eff_basic)
        eff_basic = merged_basic

        for field in (
            "npc_key", "name", "origin", "shift_profile",
            "workplace_node_id", "hangout_node_id", "roaming_route", "is_unique_proprietor",
        ):
            cur_val = eff.get(field)
            if cur_val is None or cur_val == "" or cur_val == []:
                if field in db_row and db_row[field] not in (None, ""):
                    eff[field] = db_row[field]

        # DB row is strictly authoritative over stale caller dicts (prevents stale dict rollback bypass)
        db_status = str(db_row.get("staff_status") or "active").strip().lower() or "active"
        eff["staff_status"] = db_status
        eff_basic["staff_status"] = db_status
        if "affinity_score" in db_row:
            eff["affinity_score"] = db_row.get("affinity_score")
            eff_basic["affinity_score"] = db_row.get("affinity_score")
        if "tier_status" in db_row:
            eff["tier_status"] = db_row.get("tier_status")
        unlocked_db = bool(db_row.get("residence_unlocked"))
        db_home = str(db_row.get("home_node_id") or "").strip()
        eff["residence_unlocked"] = unlocked_db
        eff_basic["residence_unlocked"] = unlocked_db
        eff["home_node_id"] = db_home
        if db_home:
            eff_basic["home_node_id"] = db_home
        else:
            eff_basic.pop("home_node_id", None)
        for stale_key in ("is_romantic", "romantic_partner", "relationship_tier"):
            if stale_key in db_basic:
                eff_basic[stale_key] = db_basic[stale_key]
                eff[stale_key] = db_basic[stale_key]
            else:
                eff_basic.pop(stale_key, None)
                eff.pop(stale_key, None)

    eff["basic_info"] = eff_basic
    return eff, db_row


def _is_inactive_staff(eff: Mapping[str, Any]) -> bool:
    basic = eff.get("basic_info") if isinstance(eff.get("basic_info"), Mapping) else {}
    status = str(eff.get("staff_status") or basic.get("staff_status") or "active").strip().lower()
    if status and status != "active":
        return True
    if bool(eff.get("is_deceased") or basic.get("is_deceased")):
        return True
    if eff.get("alive") is False or basic.get("alive") is False:
        return True
    return False


def _is_24h_station(eff: Mapping[str, Any]) -> bool:
    basic = eff.get("basic_info") if isinstance(eff.get("basic_info"), Mapping) else {}
    return bool(eff.get("is_24h_station") or basic.get("is_24h_station"))


def _is_anchor_npc(eff: Mapping[str, Any], db_row: Optional[Dict[str, Any]]) -> bool:
    basic = eff.get("basic_info") if isinstance(eff.get("basic_info"), Mapping) else {}
    origin = str(eff.get("origin") or basic.get("origin") or "").strip().lower()
    route = _parse_roaming_route(eff.get("roaming_route") or basic.get("roaming_route"))
    use_anchor = bool(eff.get("use_anchor_schedule") or basic.get("use_anchor_schedule"))

    # Ruling 6: isolate legacy_adapter rows unless explicitly opted into anchor schedules or given a route
    if origin == "legacy_adapter" and not use_anchor and not route:
        return False

    if db_row is not None:
        return True
    if origin in _ANCHOR_ORIGINS:
        return True
    if use_anchor or route:
        return True
    return bool(eff.get("workplace_node_id") or eff.get("hangout_node_id") or _is_24h_station(eff))


def _resolve_active_work_node(eff: Mapping[str, Any], current_day: int, seed_key: str) -> str:
    basic = eff.get("basic_info") if isinstance(eff.get("basic_info"), Mapping) else {}
    route = _parse_roaming_route(eff.get("roaming_route") or basic.get("roaming_route"))
    if route:
        day_offset = max(0, int(current_day or 1) - 1)
        idx = (_deterministic_seed_int(seed_key) + day_offset) % len(route)
        return route[idx]
    return str(eff.get("workplace_node_id") or basic.get("workplace_node_id") or "").strip()


def _is_rest_or_off_day(eff: Mapping[str, Any], profile: Mapping[str, Any], current_day: int, seed_key: str) -> bool:
    if _is_24h_station(eff):
        return False
    if bool(profile.get("weekday_only")) and is_weekend(current_day):
        return True
    if bool(profile.get("supports_rest_day")) and not bool(eff.get("is_unique_proprietor")):
        rest_seed = _deterministic_seed_int(seed_key)
        return ((rest_seed + max(1, int(current_day or 1))) % 7) == 0
    return False


def _resolve_home_node(
    eff: Mapping[str, Any],
    session_id: Optional[int],
    scen_key: str,
    seed_key: str,
) -> str:
    basic = eff.get("basic_info") if isinstance(eff.get("basic_info"), Mapping) else {}
    raw_home = str(eff.get("home_node_id") or basic.get("home_node_id") or "").strip()
    if not can_materialize_npc_residence(session_id, eff):
        return SHARED_ABSTRACT_RESIDENCE_NODE
    if raw_home and raw_home != SHARED_ABSTRACT_RESIDENCE_NODE:
        return raw_home
    if session_id:
        try:
            from .locations.residences import is_adult_special_agent_contact, resolve_agent_residence_blueprint

            if is_adult_special_agent_contact(eff) or bool(eff.get("is_special_agent") or eff.get("is_student_agent")):
                bp = resolve_agent_residence_blueprint(int(session_id), eff, scen_key=scen_key)
                bed_nid = str(bp.get("bedroom_node_id") or "").strip()
                if bed_nid:
                    return bed_nid
            nodes = {n["node_id"]: n for n in db.get_session_world_nodes(int(session_id))}
            for cand in (f"sub_npc_res_{seed_key}", f"fac_npc_res_{seed_key}"):
                if cand in nodes:
                    return cand
        except Exception:
            pass
    return SHARED_ABSTRACT_RESIDENCE_NODE


def resolve_anchor_schedule_nodes(
    npc: Mapping[str, Any],
    current_day: int = 1,
    scen_key: str = "fantasy",
    session_id: Optional[int] = None,
    current_minute: Optional[int] = None,
) -> Optional[Dict[str, str]]:
    """
    Resolves canonical 8-block anchor-node schedule (morning, lunch, afternoon, evening,
    night, commute, class_afternoon, extracurricular) for world-roster NPCs, returning
    None for legacy High School / Folklore / Anomalous NPCs.
    """
    if not isinstance(npc, Mapping):
        return None

    eff, db_row = _merge_roster_context(npc, session_id)
    if not _is_anchor_npc(eff, db_row):
        return None

    basic = eff.get("basic_info") if isinstance(eff.get("basic_info"), Mapping) else {}
    seed_key = _canonical_seed_key(eff)
    route = _parse_roaming_route(eff.get("roaming_route") or basic.get("roaming_route"))
    shift_key = _normalize_shift_profile(eff.get("shift_profile") or basic.get("shift_profile"), has_route=bool(route))
    profile = SHIFT_PROFILES[shift_key]

    work_node = _resolve_active_work_node(eff, current_day, seed_key)
    hangout_node = str(eff.get("hangout_node_id") or basic.get("hangout_node_id") or "").strip()
    home_node = _resolve_home_node(eff, session_id, scen_key, seed_key)

    # Inactive staff take precedence over 24h station duty
    if _is_inactive_staff(eff):
        return {block: home_node for block in _BLOCK_ORDER}

    if _is_24h_station(eff) and work_node:
        return {block: work_node for block in _BLOCK_ORDER}

    off_day = _is_rest_or_off_day(eff, profile, current_day, seed_key)
    fallback_hangout = hangout_node or (work_node if shift_key == "roaming_merchant" else home_node)

    roles = dict(_STATIC_BLOCK_ROLES[shift_key])
    if off_day:
        for blk, r in list(roles.items()):
            if r == "work":
                roles[blk] = "hangout"

    if current_minute is not None:
        safe_min = int(current_minute) % 1440
        phase_key = get_detailed_npc_time_phase(safe_min, current_day=int(current_day or 1), scen_key=scen_key)
        canon_key = get_time_block_key(safe_min)
        if not off_day and _in_windows(safe_min, profile["work_windows"]):
            role_now = "work"
        elif _in_windows(safe_min, profile["hangout_windows"]) or (
            off_day and not _in_windows(safe_min, profile["sleep_windows"])
        ):
            role_now = "hangout"
        else:
            role_now = "home"
        roles[phase_key] = role_now
        roles[canon_key] = role_now

    schedule: Dict[str, str] = {}
    for block in _BLOCK_ORDER:
        role_b = roles[block]
        if role_b == "work":
            schedule[block] = work_node or fallback_hangout or home_node
        elif role_b == "hangout":
            schedule[block] = fallback_hangout or home_node
        else:
            schedule[block] = home_node
    return schedule


def is_npc_on_active_shift(
    npc: Mapping[str, Any],
    current_minute: int = 600,
    current_day: int = 1,
    scen_key: str = "fantasy",
    session_id: Optional[int] = None,
) -> Tuple[bool, str]:
    """
    Checks whether an anchor-scheduled NPC is currently working on shift at `current_minute`.
    Returns (True, active_work_node_id) or (False, "").
    """
    _ = scen_key
    if not isinstance(npc, Mapping):
        return False, ""

    eff, db_row = _merge_roster_context(npc, session_id)
    if not _is_anchor_npc(eff, db_row):
        return False, ""
    if _is_inactive_staff(eff):
        return False, ""

    basic = eff.get("basic_info") if isinstance(eff.get("basic_info"), Mapping) else {}
    seed_key = _canonical_seed_key(eff)
    route = _parse_roaming_route(eff.get("roaming_route") or basic.get("roaming_route"))
    shift_key = _normalize_shift_profile(eff.get("shift_profile") or basic.get("shift_profile"), has_route=bool(route))
    profile = SHIFT_PROFILES[shift_key]
    work_node = _resolve_active_work_node(eff, current_day, seed_key)
    if not work_node:
        return False, ""

    if _is_24h_station(eff):
        return True, work_node

    if _is_rest_or_off_day(eff, profile, current_day, seed_key):
        return False, ""

    if _in_windows(int(current_minute), profile["work_windows"]):
        return True, work_node

    return False, ""
