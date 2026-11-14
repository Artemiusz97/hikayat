from __future__ import annotations

"""
Normalized SQLite Persistence for Closed-World NPC Roster (`world_roster` table).

Provides unified storage, legacy adapter bridging (`school_directory`,
`anomalous_agent_roster`, `folklore_villager_roster`), turn-indexed snapshots,
schedule/residence/staff-status tracking, promotion to `contacts`, and atomic
turn rollback parity.
"""

from contextlib import nullcontext
import json
import re
import sqlite3
import time
from typing import Any

import db
from .core import UnitOfWork, get_conn

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
MAX_TURN_SNAPSHOTS = 10

WORLD_ROSTER_V54_DDL: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS world_roster (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id              INTEGER NOT NULL,
    npc_id                  TEXT NOT NULL,
    name                    TEXT NOT NULL,
    gender                  TEXT NOT NULL DEFAULT '',
    race                    TEXT NOT NULL DEFAULT 'human',
    role                    TEXT NOT NULL DEFAULT '',
    origin                  TEXT NOT NULL DEFAULT 'venue_seed',
    tier_status             TEXT NOT NULL DEFAULT 'seeded',
    affinity_score          INTEGER NOT NULL DEFAULT 0,
    met_in_person           INTEGER NOT NULL DEFAULT 0,
    first_met_turn          INTEGER DEFAULT NULL,
    workplace_node_id       TEXT NOT NULL DEFAULT '',
    home_node_id            TEXT NOT NULL DEFAULT '',
    hangout_node_id         TEXT NOT NULL DEFAULT '',
    roaming_route_json      TEXT NOT NULL DEFAULT '[]',
    shift_profile           TEXT NOT NULL DEFAULT 'day',
    staff_status            TEXT NOT NULL DEFAULT 'active',
    staff_status_day        INTEGER NOT NULL DEFAULT 0,
    is_unique_proprietor    INTEGER NOT NULL DEFAULT 0,
    residence_unlocked      INTEGER NOT NULL DEFAULT 0,
    residence_unlock_reason TEXT NOT NULL DEFAULT '',
    discovered_slots_json   TEXT NOT NULL DEFAULT '{}',
    basic_info_json         TEXT NOT NULL DEFAULT '{}',
    appearance_json         TEXT NOT NULL DEFAULT '{}',
    traits_json             TEXT NOT NULL DEFAULT '[]',
    turn_snapshots_json     TEXT NOT NULL DEFAULT '{}',
    turn_created            INTEGER NOT NULL DEFAULT 0,
    turn_updated            INTEGER NOT NULL DEFAULT 0,
    created_at              REAL NOT NULL,
    updated_at              REAL NOT NULL,
    UNIQUE(session_id, npc_id)
)""",
    "CREATE INDEX IF NOT EXISTS idx_world_roster_sess_tier ON world_roster(session_id, tier_status)",
    "CREATE INDEX IF NOT EXISTS idx_world_roster_workplace ON world_roster(session_id, workplace_node_id, staff_status)",
)


def _conn_ctx(conn: sqlite3.Connection | None):
    return nullcontext(conn) if conn is not None else get_conn()


def _ensure_world_roster_table(conn: sqlite3.Connection) -> None:
    """Self-healing DDL guard for isolated unit tests that bypass full migrations."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='world_roster' LIMIT 1"
    ).fetchone()
    if row is not None:
        return
    for sql in WORLD_ROSTER_V54_DDL:
        conn.execute(sql)


def _slugify_npc_id(raw: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(raw or "").strip().lower()).strip("_")


def _clamp_affinity(val: Any) -> int:
    try:
        num = int(val)
    except (TypeError, ValueError):
        num = 0
    return max(-100, min(300, num))


def _parse_json_dict(raw: Any) -> dict[str, Any]:
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


def _parse_json_list(raw: Any) -> list[Any]:
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


def _is_empty_val(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str):
        return val.strip().lower() in ("", "none", "unknown", "null", "n/a")
    if isinstance(val, (list, dict, tuple, set)):
        return len(val) == 0
    return False


def _merge_dict_safely(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for src in (existing, incoming):
        if not isinstance(src, dict):
            continue
        for k, v in src.items():
            if not _is_empty_val(v):
                merged[k] = v.strip() if isinstance(v, str) else v
    return merged


def _merge_discovered_slots(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for src in (existing, incoming):
        if not isinstance(src, dict):
            continue
        for day_kind, blocks in src.items():
            dk = str(day_kind or "").strip().lower()
            if not dk or not isinstance(blocks, dict):
                continue
            target = out.setdefault(dk, {})
            for bk, loc in blocks.items():
                bk_s = str(bk or "").strip()
                loc_s = str(loc or "").strip()
                if bk_s and loc_s:
                    target[bk_s] = loc_s
    return out


def _dedupe_str_list(existing: list[Any], incoming: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in list(existing or []) + list(incoming or []):
        s = str(item or "").strip()
        if not s:
            continue
        low = s.lower()
        if low not in seen:
            seen.add(low)
            out.append(s)
    return out


def _pick_non_empty(*values: Any, default: str = "") -> str:
    for v in values:
        if isinstance(v, str):
            s = v.strip()
            if s:
                return s
    return default


def _mirror_anchors_into_basic_info(
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


def _hydrate_roster_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    d = dict(row)
    d["session_id"] = int(d.get("session_id") or 0)
    d["affinity_score"] = _clamp_affinity(d.get("affinity_score") or 0)
    d["met_in_person"] = bool(d.get("met_in_person"))
    d["is_unique_proprietor"] = bool(d.get("is_unique_proprietor"))
    d["residence_unlocked"] = bool(d.get("residence_unlocked"))
    d["staff_status_day"] = int(d.get("staff_status_day") or 0)
    d["turn_created"] = int(d.get("turn_created") or 0)
    d["turn_updated"] = int(d.get("turn_updated") or 0)
    if d.get("first_met_turn") is not None:
        d["first_met_turn"] = int(d["first_met_turn"])

    d["roaming_route"] = _parse_json_list(d.get("roaming_route_json"))
    d["discovered_slots"] = _parse_json_dict(d.get("discovered_slots_json"))
    d["basic_info"] = _parse_json_dict(d.get("basic_info_json"))
    d["appearance"] = _parse_json_dict(d.get("appearance_json"))
    d["traits"] = _parse_json_list(d.get("traits_json"))
    d["turn_snapshots"] = _parse_json_dict(d.get("turn_snapshots_json"))
    return d


def _capture_turn_snapshot(
    snapshots: dict[str, Any],
    row: dict[str, Any],
    turn_number: int,
) -> dict[str, Any]:
    out = dict(snapshots) if isinstance(snapshots, dict) else {}
    t_key = str(int(turn_number))
    if t_key not in out:
        out[t_key] = {
            "tier_status": str(row.get("tier_status") or "seeded"),
            "affinity_score": _clamp_affinity(row.get("affinity_score") or 0),
            "met_in_person": int(bool(row.get("met_in_person"))),
            "first_met_turn": row.get("first_met_turn"),
            "staff_status": str(row.get("staff_status") or "active"),
            "staff_status_day": int(row.get("staff_status_day") or 0),
            "residence_unlocked": int(bool(row.get("residence_unlocked"))),
            "residence_unlock_reason": str(row.get("residence_unlock_reason") or ""),
            "home_node_id": str(row.get("home_node_id") or ""),
            "discovered_slots": json.loads(json.dumps(row.get("discovered_slots") or {})),
            "basic_info": json.loads(json.dumps(row.get("basic_info") or {})),
        }
    if len(out) > MAX_TURN_SNAPSHOTS:
        sortable: list[tuple[int, str]] = []
        for k in out:
            try:
                sortable.append((int(k), str(k)))
            except (TypeError, ValueError):
                sortable.append((-1, str(k)))
        sortable.sort(key=lambda item: item[0])
        for _, drop_key in sortable[: len(out) - MAX_TURN_SNAPSHOTS]:
            out.pop(drop_key, None)
    return out


def _matches_npc_key(npc_id: str, name: str, raw_needle: str, slug_needle: str) -> bool:
    nid = str(npc_id or "").strip().lower()
    nm = str(name or "").strip()
    nm_lower = nm.lower()
    if raw_needle and (nid == raw_needle or nm_lower == raw_needle):
        return True
    if slug_needle and (nid == slug_needle or _slugify_npc_id(nm) == slug_needle):
        return True
    return False


def _find_roster_row(conn: sqlite3.Connection, session_id: int, npc_key_or_name: str) -> sqlite3.Row | None:
    raw_needle = str(npc_key_or_name or "").strip().lower()
    slug_needle = _slugify_npc_id(npc_key_or_name)
    if not raw_needle and not slug_needle:
        return None
    row = conn.execute(
        """SELECT * FROM world_roster
           WHERE session_id = ?
             AND (LOWER(npc_id) = ? OR LOWER(npc_id) = ? OR LOWER(name) = ?)
           ORDER BY id ASC LIMIT 1""",
        (int(session_id), raw_needle, slug_needle, raw_needle),
    ).fetchone()
    if row is not None or not slug_needle:
        return row
    for candidate in conn.execute(
        "SELECT * FROM world_roster WHERE session_id = ? ORDER BY id ASC",
        (int(session_id),),
    ).fetchall():
        if _slugify_npc_id(candidate["name"]) == slug_needle:
            return candidate
    return None


def _collect_existing_roster_and_contact_keys(
    conn: sqlite3.Connection,
    session_id: int,
) -> tuple[set[str], set[str]]:
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    sid = int(session_id)

    for r in conn.execute("SELECT npc_id, name FROM world_roster WHERE session_id = ?", (sid,)).fetchall():
        nid = str(r["npc_id"] or "").strip().lower()
        nm = str(r["name"] or "").strip().lower()
        if nid:
            seen_ids.add(nid)
        if nm:
            seen_names.add(nm)

    try:
        for r in conn.execute("SELECT npc_id, name FROM contacts WHERE session_id = ?", (sid,)).fetchall():
            nid = str(r["npc_id"] or "").strip().lower()
            nm = str(r["name"] or "").strip().lower()
            if nid:
                seen_ids.add(nid)
            if nm:
                seen_names.add(nm)
    except sqlite3.OperationalError:
        pass

    return seen_ids, seen_names


def _build_legacy_adapted_entry(
    session_id: int,
    *,
    npc_id: str,
    name: str,
    gender: str = "",
    race: str = "human",
    role: str = "",
    affinity_score: int = 0,
    workplace_node_id: str = "",
    home_node_id: str = "",
    hangout_node_id: str = "",
    shift_profile: str = "day",
    basic_info: dict[str, Any] | None = None,
    appearance: dict[str, Any] | None = None,
    traits: list[str] | None = None,
) -> dict[str, Any]:
    b_info = _mirror_anchors_into_basic_info(
        dict(basic_info or {}),
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
        "gender": gender,
        "race": race or "human",
        "role": role,
        "origin": "legacy_adapter",
        "tier_status": "seeded",
        "affinity_score": _clamp_affinity(affinity_score),
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
        "appearance": dict(appearance or {}),
        "traits": list(traits or []),
        "turn_snapshots": {},
        "turn_created": 0,
        "turn_updated": 0,
        "created_at": 0.0,
        "updated_at": 0.0,
    }


def _adapt_legacy_rosters(
    conn: sqlite3.Connection,
    session_id: int,
    seen_ids: set[str],
    seen_names: set[str],
) -> list[dict[str, Any]]:
    sid = int(session_id)
    adapted: list[dict[str, Any]] = []

    extra_obj: dict[str, Any] = {}
    try:
        s_row = conn.execute("SELECT extra_json FROM sessions WHERE id = ?", (sid,)).fetchone()
        if s_row and s_row["extra_json"]:
            extra_obj = _parse_json_dict(s_row["extra_json"])
    except sqlite3.OperationalError:
        extra_obj = {}

    agent_roster = extra_obj.get("anomalous_agent_roster")
    if isinstance(agent_roster, list):
        for entry in agent_roster:
            if not isinstance(entry, dict):
                continue
            if int(entry.get("is_hydrated") or 0) == 1:
                continue
            name = str(entry.get("name") or "").strip()
            npc_id = _slugify_npc_id(entry.get("npc_id") or name)
            if not npc_id or not name:
                continue
            if npc_id in seen_ids or name.lower() in seen_names:
                continue
            seen_ids.add(npc_id)
            seen_names.add(name.lower())
            workplace = _pick_non_empty(
                entry.get("workplace_node_id"),
                entry.get("primary_node_id"),
                entry.get("primary_facility"),
            )
            home = _pick_non_empty(entry.get("home_node_id"), entry.get("residence_node_id"))
            hangout = _pick_non_empty(
                entry.get("hangout_node_id"),
                entry.get("secondary_node_id"),
                entry.get("secondary_facility"),
            )
            shift = "student" if entry.get("is_student_agent") else "day"
            if str(entry.get("shift_profile") or "") in ALLOWED_SHIFT_PROFILES:
                shift = str(entry["shift_profile"])
            b_info = _merge_dict_safely(
                {},
                {
                    "role": entry.get("role") or entry.get("agent_class") or "",
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
            )
            adapted.append(
                _build_legacy_adapted_entry(
                    sid,
                    npc_id=npc_id,
                    name=name,
                    gender=str(entry.get("gender") or "").strip().lower(),
                    race=str(entry.get("race") or "human").strip() or "human",
                    role=str(entry.get("role") or entry.get("agent_class") or "").strip(),
                    affinity_score=int(entry.get("initial_affinity") or 0),
                    workplace_node_id=workplace,
                    home_node_id=home,
                    hangout_node_id=hangout,
                    shift_profile=shift,
                    basic_info=b_info,
                    appearance=_parse_json_dict(entry.get("appearance")),
                    traits=[],
                )
            )

    folklore_roster = extra_obj.get("folklore_villager_roster")
    if isinstance(folklore_roster, list):
        for entry in folklore_roster:
            if not isinstance(entry, dict) or entry.get("hydrated"):
                continue
            name = str(entry.get("name") or "").strip()
            npc_id = _slugify_npc_id(entry.get("npc_id") or name)
            if not npc_id or not name:
                continue
            if npc_id in seen_ids or name.lower() in seen_names:
                continue
            seen_ids.add(npc_id)
            seen_names.add(name.lower())
            home = _pick_non_empty(entry.get("home_node_id"), entry.get("home_node"))
            workplace = _pick_non_empty(entry.get("workplace_node_id"), home)
            hangout = _pick_non_empty(entry.get("hangout_node_id"), entry.get("village_id"))
            b_info = _merge_dict_safely(
                {},
                {
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
            )
            adapted.append(
                _build_legacy_adapted_entry(
                    sid,
                    npc_id=npc_id,
                    name=name,
                    gender=str(entry.get("gender") or "").strip().lower(),
                    race=str(entry.get("race") or "human").strip() or "human",
                    role=str(entry.get("role") or "").strip(),
                    affinity_score=int(entry.get("initial_affinity") or 0),
                    workplace_node_id=workplace,
                    home_node_id=home,
                    hangout_node_id=hangout,
                    shift_profile="day",
                    basic_info=b_info,
                    appearance=_parse_json_dict(entry.get("appearance")),
                    traits=[],
                )
            )

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
        name = str(sr["name"] or "").strip()
        npc_id = _slugify_npc_id(sr["npc_id"] or name)
        if not npc_id or not name:
            continue
        if npc_id in seen_ids or name.lower() in seen_names:
            continue
        seen_ids.add(npc_id)
        seen_names.add(name.lower())
        grade_val = str(sr["grade"] or "").strip()
        shift = (
            "student"
            if grade_val.lower() in ("freshman", "sophomore", "junior", "senior", "student")
            else "day"
        )
        workplace = str(sr["primary_facility"] or "").strip()
        hangout = str(sr["secondary_facility"] or "").strip()
        b_info = _merge_dict_safely(
            {},
            {
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
        adapted.append(
            _build_legacy_adapted_entry(
                sid,
                npc_id=npc_id,
                name=name,
                gender=str(sr["gender"] or "").strip().lower(),
                race=str(sr["race"] or "human").strip() or "human",
                role=str(sr["role"] or "").strip(),
                affinity_score=0,
                workplace_node_id=workplace,
                home_node_id="",
                hangout_node_id=hangout,
                shift_profile=shift,
                basic_info=b_info,
                appearance={},
                traits=[],
            )
        )

    return adapted


def _materialize_or_find_roster_row(
    conn: sqlite3.Connection,
    session_id: int,
    npc_key_or_name: str,
) -> sqlite3.Row | None:
    row = _find_roster_row(conn, session_id, npc_key_or_name)
    if row is not None:
        return row
    raw_needle = str(npc_key_or_name or "").strip().lower()
    slug_needle = _slugify_npc_id(npc_key_or_name)
    if not raw_needle and not slug_needle:
        return None
    seen_ids, seen_names = _collect_existing_roster_and_contact_keys(conn, session_id)
    for entry in _adapt_legacy_rosters(conn, session_id, seen_ids, seen_names):
        if _matches_npc_key(entry["npc_id"], entry["name"], raw_needle, slug_needle):
            upsert_world_roster_npc(session_id, entry, turn_number=0, conn=conn)
            return _find_roster_row(conn, session_id, entry["npc_id"])
    return None


def upsert_world_roster_npc(
    session_id: int,
    npc_data: dict[str, Any],
    turn_number: int = 0,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Inserts or non-destructively updates a `world_roster` NPC row."""
    if not session_id or not isinstance(npc_data, dict):
        return {}
    sid = int(session_id)
    raw_name = str(npc_data.get("name") or "").strip()
    raw_npc_id = str(npc_data.get("npc_id") or "").strip()
    npc_id = _slugify_npc_id(raw_npc_id or raw_name)
    if not npc_id:
        return {}

    now = time.time()
    t_num = int(turn_number)

    def _run(c: sqlite3.Connection) -> dict[str, Any]:
        _ensure_world_roster_table(c)
        existing_row = c.execute(
            "SELECT * FROM world_roster WHERE session_id = ? AND npc_id = ? LIMIT 1",
            (sid, npc_id),
        ).fetchone()
        existing = _hydrate_roster_row(existing_row) if existing_row is not None else {}

        final_name = raw_name or str(existing.get("name") or raw_npc_id or "").strip()
        if not final_name:
            return {}

        in_basic = _parse_json_dict(
            npc_data.get("basic_info") if "basic_info" in npc_data else npc_data.get("basic_info_json")
        )
        in_app = _parse_json_dict(
            npc_data.get("appearance") if "appearance" in npc_data else npc_data.get("appearance_json")
        )
        in_slots = _parse_json_dict(
            npc_data.get("discovered_slots") if "discovered_slots" in npc_data else npc_data.get("discovered_slots_json")
        )
        if "roaming_route" in npc_data:
            in_route = _parse_json_list(npc_data.get("roaming_route"))
        elif "roaming_route_json" in npc_data:
            in_route = _parse_json_list(npc_data.get("roaming_route_json"))
        else:
            in_route = None
        in_traits = _parse_json_list(
            npc_data.get("traits") if "traits" in npc_data else npc_data.get("traits_json")
        )

        gender = _pick_non_empty(npc_data.get("gender"), in_basic.get("gender"), existing.get("gender"))
        race = _pick_non_empty(npc_data.get("race"), in_basic.get("race"), existing.get("race"), default="human")
        role = _pick_non_empty(npc_data.get("role"), in_basic.get("role"), existing.get("role"))

        raw_origin = str(npc_data.get("origin") or existing.get("origin") or "venue_seed").strip()
        origin = raw_origin if raw_origin in ALLOWED_ROSTER_ORIGINS else str(existing.get("origin") or "venue_seed")

        raw_tier = str(npc_data.get("tier_status") or existing.get("tier_status") or "seeded").strip()
        tier_status = raw_tier if raw_tier in ALLOWED_ROSTER_TIERS else str(existing.get("tier_status") or "seeded")

        if "affinity_score" in npc_data and npc_data.get("affinity_score") is not None:
            affinity_score = _clamp_affinity(npc_data["affinity_score"])
        elif existing:
            affinity_score = _clamp_affinity(existing.get("affinity_score") or 0)
        else:
            affinity_score = _clamp_affinity(npc_data.get("initial_affinity") or 0)

        met_in_person = (
            int(bool(npc_data["met_in_person"]))
            if "met_in_person" in npc_data
            else int(bool(existing.get("met_in_person")))
        )
        if "first_met_turn" in npc_data and npc_data.get("first_met_turn") is not None:
            first_met_turn: int | None = int(npc_data["first_met_turn"])
        elif existing.get("first_met_turn") is not None:
            first_met_turn = int(existing["first_met_turn"])
        else:
            first_met_turn = t_num if met_in_person else None

        workplace_node_id = _pick_non_empty(
            npc_data.get("workplace_node_id"), in_basic.get("workplace_node_id"), existing.get("workplace_node_id")
        )
        home_node_id = _pick_non_empty(
            npc_data.get("home_node_id"), in_basic.get("home_node_id"), existing.get("home_node_id")
        )
        hangout_node_id = _pick_non_empty(
            npc_data.get("hangout_node_id"), in_basic.get("hangout_node_id"), existing.get("hangout_node_id")
        )

        raw_shift = _pick_non_empty(
            npc_data.get("shift_profile"), in_basic.get("shift_profile"), existing.get("shift_profile"), default="day"
        )
        shift_profile = raw_shift if raw_shift in ALLOWED_SHIFT_PROFILES else str(existing.get("shift_profile") or "day")

        raw_staff = str(npc_data.get("staff_status") or existing.get("staff_status") or "active").strip().lower()
        staff_status = raw_staff if raw_staff in ALLOWED_STAFF_STATUSES else str(existing.get("staff_status") or "active")

        staff_status_day = (
            int(npc_data["staff_status_day"])
            if "staff_status_day" in npc_data and npc_data.get("staff_status_day") is not None
            else int(existing.get("staff_status_day") or 0)
        )
        is_unique_proprietor = (
            int(bool(npc_data["is_unique_proprietor"]))
            if "is_unique_proprietor" in npc_data
            else int(bool(existing.get("is_unique_proprietor")))
        )
        if "residence_unlocked" in npc_data:
            residence_unlocked = int(bool(npc_data["residence_unlocked"]))
        elif "residence_unlocked" in in_basic:
            residence_unlocked = int(bool(in_basic["residence_unlocked"]))
        else:
            residence_unlocked = int(bool(existing.get("residence_unlocked")))

        residence_unlock_reason = _pick_non_empty(
            npc_data.get("residence_unlock_reason"), existing.get("residence_unlock_reason")
        )

        roaming_route = (
            [str(x).strip() for x in in_route if str(x or "").strip()]
            if in_route is not None and (in_route or not existing)
            else list(existing.get("roaming_route") or [])
        )
        discovered_slots = _merge_discovered_slots(existing.get("discovered_slots") or {}, in_slots)
        merged_basic = _merge_dict_safely(existing.get("basic_info") or {}, in_basic)
        if role:
            merged_basic.setdefault("role", role)
        merged_basic = _mirror_anchors_into_basic_info(
            merged_basic,
            workplace_node_id=workplace_node_id,
            home_node_id=home_node_id,
            hangout_node_id=hangout_node_id,
            shift_profile=shift_profile,
            residence_unlocked=bool(residence_unlocked),
        )
        merged_app = _merge_dict_safely(existing.get("appearance") or {}, in_app)
        merged_traits = _dedupe_str_list(existing.get("traits") or [], in_traits)

        if existing_row is not None:
            snaps = existing.get("turn_snapshots") or {}
            c.execute(
                """UPDATE world_roster
                   SET name = ?, gender = ?, race = ?, role = ?, origin = ?, tier_status = ?,
                       affinity_score = ?, met_in_person = ?, first_met_turn = ?,
                       workplace_node_id = ?, home_node_id = ?, hangout_node_id = ?,
                       roaming_route_json = ?, shift_profile = ?, staff_status = ?, staff_status_day = ?,
                       is_unique_proprietor = ?, residence_unlocked = ?, residence_unlock_reason = ?,
                       discovered_slots_json = ?, basic_info_json = ?, appearance_json = ?,
                       traits_json = ?, turn_snapshots_json = ?, turn_updated = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    final_name,
                    gender,
                    race,
                    role,
                    origin,
                    tier_status,
                    affinity_score,
                    met_in_person,
                    first_met_turn,
                    workplace_node_id,
                    home_node_id,
                    hangout_node_id,
                    json.dumps(roaming_route),
                    shift_profile,
                    staff_status,
                    staff_status_day,
                    is_unique_proprietor,
                    residence_unlocked,
                    residence_unlock_reason,
                    json.dumps(discovered_slots),
                    json.dumps(merged_basic),
                    json.dumps(merged_app),
                    json.dumps(merged_traits),
                    json.dumps(snaps),
                    t_num,
                    now,
                    existing_row["id"],
                ),
            )
            row_out = c.execute("SELECT * FROM world_roster WHERE id = ?", (existing_row["id"],)).fetchone()
        else:
            snaps = _parse_json_dict(npc_data.get("turn_snapshots") or npc_data.get("turn_snapshots_json"))
            cur = c.execute(
                """INSERT INTO world_roster (
                       session_id, npc_id, name, gender, race, role, origin, tier_status,
                       affinity_score, met_in_person, first_met_turn,
                       workplace_node_id, home_node_id, hangout_node_id,
                       roaming_route_json, shift_profile, staff_status, staff_status_day,
                       is_unique_proprietor, residence_unlocked, residence_unlock_reason,
                       discovered_slots_json, basic_info_json, appearance_json,
                       traits_json, turn_snapshots_json, turn_created, turn_updated,
                       created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sid,
                    npc_id,
                    final_name,
                    gender,
                    race,
                    role,
                    origin,
                    tier_status,
                    affinity_score,
                    met_in_person,
                    first_met_turn,
                    workplace_node_id,
                    home_node_id,
                    hangout_node_id,
                    json.dumps(roaming_route),
                    shift_profile,
                    staff_status,
                    staff_status_day,
                    is_unique_proprietor,
                    residence_unlocked,
                    residence_unlock_reason,
                    json.dumps(discovered_slots),
                    json.dumps(merged_basic),
                    json.dumps(merged_app),
                    json.dumps(merged_traits),
                    json.dumps(snaps),
                    t_num,
                    t_num,
                    now,
                    now,
                ),
            )
            row_out = c.execute("SELECT * FROM world_roster WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _hydrate_roster_row(row_out) if row_out is not None else {}

    with _conn_ctx(conn) as c:
        return _run(c)


def get_world_roster(
    session_id: int,
    tier_status: str | None = None,
    workplace_node_id: str | None = None,
    include_legacy_rosters: bool = True,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Returns `world_roster` entries for a session, optionally filtering and adapting unhydrated legacy rosters."""
    if not session_id:
        return []
    sid = int(session_id)

    def _run(c: sqlite3.Connection) -> list[dict[str, Any]]:
        _ensure_world_roster_table(c)
        clauses = ["session_id = ?"]
        params: list[Any] = [sid]
        if tier_status is not None:
            clauses.append("tier_status = ?")
            params.append(str(tier_status))
        if workplace_node_id is not None:
            clauses.append("workplace_node_id = ?")
            params.append(str(workplace_node_id))

        where_sql = " AND ".join(clauses)
        rows = c.execute(f"SELECT * FROM world_roster WHERE {where_sql} ORDER BY id ASC", params).fetchall()
        results = [_hydrate_roster_row(r) for r in rows]

        if include_legacy_rosters:
            seen_ids, seen_names = _collect_existing_roster_and_contact_keys(c, sid)
            for adapted in _adapt_legacy_rosters(c, sid, seen_ids, seen_names):
                if tier_status is not None and adapted["tier_status"] != str(tier_status):
                    continue
                if workplace_node_id is not None and adapted["workplace_node_id"] != str(workplace_node_id):
                    continue
                results.append(adapted)
        return results

    with _conn_ctx(conn) as c:
        return _run(c)


def get_world_roster_npc(
    session_id: int,
    npc_key_or_name: str,
    include_legacy_rosters: bool = True,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Looks up one NPC in `world_roster` by `npc_id`, slug, or case-insensitive name, with optional legacy fallback."""
    if not session_id or not str(npc_key_or_name or "").strip():
        return None
    sid = int(session_id)
    raw_needle = str(npc_key_or_name).strip().lower()
    slug_needle = _slugify_npc_id(npc_key_or_name)

    def _run(c: sqlite3.Connection) -> dict[str, Any] | None:
        _ensure_world_roster_table(c)
        row = _find_roster_row(c, sid, npc_key_or_name)
        if row is not None:
            return _hydrate_roster_row(row)
        if include_legacy_rosters:
            seen_ids, seen_names = _collect_existing_roster_and_contact_keys(c, sid)
            for adapted in _adapt_legacy_rosters(c, sid, seen_ids, seen_names):
                if _matches_npc_key(adapted["npc_id"], adapted["name"], raw_needle, slug_needle):
                    return adapted
        return None

    with _conn_ctx(conn) as c:
        return _run(c)


def record_world_roster_interaction(
    session_id: int,
    npc_key_or_name: str,
    delta_score: int = 0,
    discovered_slot: tuple[str, str, str] | None = None,
    met_in_person: bool = True,
    turn_number: int = 1,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Snapshots pre-turn state, updates affinity/tier/met_in_person/discovered_slot, and returns hydrated dict."""
    if not session_id or not str(npc_key_or_name or "").strip():
        return None
    sid = int(session_id)
    t_num = int(turn_number)
    now = time.time()

    def _run(c: sqlite3.Connection) -> dict[str, Any] | None:
        _ensure_world_roster_table(c)
        row = _materialize_or_find_roster_row(c, sid, npc_key_or_name)
        if row is None:
            return None

        cur = _hydrate_roster_row(row)
        snaps = _capture_turn_snapshot(cur.get("turn_snapshots") or {}, cur, t_num)

        new_tier = str(cur.get("tier_status") or "seeded")
        new_met = int(bool(cur.get("met_in_person")))
        new_first_met = cur.get("first_met_turn")
        if met_in_person:
            new_met = 1
            if new_first_met is None:
                new_first_met = t_num
            if new_tier == "seeded":
                new_tier = "acquaintance"

        new_affinity = _clamp_affinity(int(cur.get("affinity_score") or 0) + int(delta_score or 0))
        slots = _merge_discovered_slots(cur.get("discovered_slots") or {}, {})
        if isinstance(discovered_slot, (tuple, list)) and len(discovered_slot) == 3:
            dk = str(discovered_slot[0] or "").strip().lower()
            bk = str(discovered_slot[1] or "").strip()
            loc = str(discovered_slot[2] or "").strip()
            if dk in ("weekday", "weekend") and bk and loc:
                slots.setdefault(dk, {})[bk] = loc

        c.execute(
            """UPDATE world_roster
               SET tier_status = ?, affinity_score = ?, met_in_person = ?, first_met_turn = ?,
                   discovered_slots_json = ?, turn_snapshots_json = ?, turn_updated = ?, updated_at = ?
               WHERE id = ?""",
            (
                new_tier,
                new_affinity,
                new_met,
                new_first_met,
                json.dumps(slots),
                json.dumps(snaps),
                t_num,
                now,
                cur["id"],
            ),
        )
        updated = c.execute("SELECT * FROM world_roster WHERE id = ?", (cur["id"],)).fetchone()
        return _hydrate_roster_row(updated) if updated is not None else None

    with _conn_ctx(conn) as c:
        return _run(c)


def record_discovered_schedule_slot(
    session_id: int,
    npc_key_or_name: str,
    day_kind: str,
    block_key: str,
    location_label: str,
    turn_number: int = 1,
    conn: sqlite3.Connection | None = None,
) -> bool:
    """Records an observed/inquired schedule slot into `world_roster` and mirrors to `contacts.basic_info_json`."""
    dk = str(day_kind or "").strip().lower()
    bk = str(block_key or "").strip()
    loc = str(location_label or "").strip()
    if not session_id or dk not in ("weekday", "weekend") or not bk or not loc:
        return False

    sid = int(session_id)
    t_num = int(turn_number)
    now = time.time()

    def _run(c: sqlite3.Connection) -> bool:
        _ensure_world_roster_table(c)
        row = _materialize_or_find_roster_row(c, sid, npc_key_or_name)
        if row is None:
            return False

        cur = _hydrate_roster_row(row)
        snaps = _capture_turn_snapshot(cur.get("turn_snapshots") or {}, cur, t_num)
        slots = _merge_discovered_slots(cur.get("discovered_slots") or {}, {dk: {bk: loc}})

        c.execute(
            """UPDATE world_roster
               SET discovered_slots_json = ?, turn_snapshots_json = ?, turn_updated = ?, updated_at = ?
               WHERE id = ?""",
            (json.dumps(slots), json.dumps(snaps), t_num, now, cur["id"]),
        )

        contact_rows = c.execute(
            """SELECT id, basic_info_json FROM contacts
               WHERE session_id = ? AND (LOWER(npc_id) = ? OR LOWER(name) = ?)""",
            (sid, cur["npc_id"].lower(), cur["name"].lower()),
        ).fetchall()
        for cr in contact_rows:
            c_info = _parse_json_dict(cr["basic_info_json"])
            c_info["discovered_slots"] = _merge_discovered_slots(
                c_info.get("discovered_slots") if isinstance(c_info.get("discovered_slots"), dict) else {},
                {dk: {bk: loc}},
            )
            c.execute(
                "UPDATE contacts SET basic_info_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(c_info), now, cr["id"]),
            )
        return True

    with _conn_ctx(conn) as c:
        return _run(c)


def set_world_roster_residence_unlocked(
    session_id: int,
    npc_key_or_name: str,
    reason: str,
    home_node_id: str = "",
    turn_number: int = 1,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Marks an NPC's residence unlocked in `world_roster` (with snapshot) and mirrors onto `contacts`."""
    if not session_id or not str(npc_key_or_name or "").strip():
        return None
    sid = int(session_id)
    t_num = int(turn_number)
    now = time.time()
    clean_home = str(home_node_id or "").strip()
    clean_reason = str(reason or "").strip()

    def _run(c: sqlite3.Connection) -> dict[str, Any] | None:
        _ensure_world_roster_table(c)
        row = _materialize_or_find_roster_row(c, sid, npc_key_or_name)
        if row is None:
            return None

        cur = _hydrate_roster_row(row)
        snaps = _capture_turn_snapshot(cur.get("turn_snapshots") or {}, cur, t_num)
        final_home = clean_home or str(cur.get("home_node_id") or "")
        b_info = dict(cur.get("basic_info") or {})
        b_info["residence_unlocked"] = True
        if final_home:
            b_info["home_node_id"] = final_home

        c.execute(
            """UPDATE world_roster
               SET residence_unlocked = 1, residence_unlock_reason = ?, home_node_id = ?,
                   basic_info_json = ?, turn_snapshots_json = ?, turn_updated = ?, updated_at = ?
               WHERE id = ?""",
            (clean_reason, final_home, json.dumps(b_info), json.dumps(snaps), t_num, now, cur["id"]),
        )

        contact_rows = c.execute(
            """SELECT id, basic_info_json FROM contacts
               WHERE session_id = ? AND (LOWER(npc_id) = ? OR LOWER(name) = ?)""",
            (sid, cur["npc_id"].lower(), cur["name"].lower()),
        ).fetchall()
        for cr in contact_rows:
            c_info = _parse_json_dict(cr["basic_info_json"])
            c_info["residence_unlocked"] = True
            if final_home:
                c_info["home_node_id"] = final_home
            c.execute(
                "UPDATE contacts SET basic_info_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(c_info), now, cr["id"]),
            )

        updated = c.execute("SELECT * FROM world_roster WHERE id = ?", (cur["id"],)).fetchone()
        return _hydrate_roster_row(updated) if updated is not None else None

    with _conn_ctx(conn) as c:
        return _run(c)


def mark_world_roster_staff_status(
    session_id: int,
    npc_key_or_name: str,
    staff_status: str,
    day_changed: int,
    turn_number: int = 1,
    conn: sqlite3.Connection | None = None,
) -> bool:
    """Updates an NPC's `staff_status` in `world_roster` with turn-snapshot capture."""
    st = str(staff_status or "").strip().lower()
    if st not in ALLOWED_STAFF_STATUSES:
        raise ValueError(f"Invalid staff_status {staff_status!r}; expected one of {sorted(ALLOWED_STAFF_STATUSES)}")
    if not session_id or not str(npc_key_or_name or "").strip():
        return False

    sid = int(session_id)
    t_num = int(turn_number)
    now = time.time()

    def _run(c: sqlite3.Connection) -> bool:
        _ensure_world_roster_table(c)
        row = _find_roster_row(c, sid, npc_key_or_name)
        if row is None:
            return False

        cur = _hydrate_roster_row(row)
        snaps = _capture_turn_snapshot(cur.get("turn_snapshots") or {}, cur, t_num)
        c.execute(
            """UPDATE world_roster
               SET staff_status = ?, staff_status_day = ?, turn_snapshots_json = ?,
                   turn_updated = ?, updated_at = ?
               WHERE id = ?""",
            (st, int(day_changed), json.dumps(snaps), t_num, now, cur["id"]),
        )
        return True

    with _conn_ctx(conn) as c:
        return _run(c)


def promote_world_roster_to_contact(
    session_id: int,
    character_id: int,
    npc_key_or_name: str,
    reason: str,
    has_contact_info: bool = False,
    turn_number: int = 1,
    narrative_text: str = "",
) -> dict[str, Any] | None:
    """Promotes a `world_roster` (or legacy adapter) NPC into `contacts` while snapshotting pre-promotion state."""
    if not session_id or not str(npc_key_or_name or "").strip():
        return None
    sid = int(session_id)
    cid = int(character_id or 0)
    t_num = int(turn_number)
    now = time.time()

    with UnitOfWork() as conn:
        _ensure_world_roster_table(conn)
        row = _materialize_or_find_roster_row(conn, sid, npc_key_or_name)
        if row is None:
            return None

        cur = _hydrate_roster_row(row)
        snaps = _capture_turn_snapshot(cur.get("turn_snapshots") or {}, cur, t_num)

        target_score = _clamp_affinity(cur.get("affinity_score") or 0)
        if cid:
            existing_contact = conn.execute(
                """SELECT relationship_score FROM contacts
                   WHERE session_id = ? AND (character_id = ? OR character_id = 0)
                     AND (LOWER(npc_id) = ? OR LOWER(name) = ?)
                   ORDER BY id ASC LIMIT 1""",
                (sid, cid, cur["npc_id"].lower(), cur["name"].lower()),
            ).fetchone()
        else:
            existing_contact = conn.execute(
                """SELECT relationship_score FROM contacts
                   WHERE session_id = ? AND (LOWER(npc_id) = ? OR LOWER(name) = ?)
                   ORDER BY id ASC LIMIT 1""",
                (sid, cur["npc_id"].lower(), cur["name"].lower()),
            ).fetchone()

        if existing_contact is not None:
            delta_score = target_score - int(existing_contact["relationship_score"] or 0)
        else:
            delta_score = target_score

        b_info = dict(cur.get("basic_info") or {})
        if cur.get("role"):
            b_info["role"] = cur["role"]
        b_info["workplace_node_id"] = cur.get("workplace_node_id") or ""
        b_info["home_node_id"] = cur.get("home_node_id") or ""
        b_info["hangout_node_id"] = cur.get("hangout_node_id") or ""
        b_info["roaming_route"] = list(cur.get("roaming_route") or [])
        b_info["shift_profile"] = cur.get("shift_profile") or "day"
        b_info["discovered_slots"] = dict(cur.get("discovered_slots") or {})
        b_info["residence_unlocked"] = bool(cur.get("residence_unlocked"))
        b_info["met_in_person"] = True
        b_info["has_contact_info"] = bool(has_contact_info)
        b_info["promoted_from_roster_turn"] = t_num
        b_info["promotion_reason"] = str(reason or "")

        contact_res = db.upsert_contact(
            session_id=sid,
            npc_id=cur["npc_id"],
            name=cur["name"],
            character_id=cid,
            basic_info=b_info,
            delta_score=delta_score,
            new_traits=list(cur.get("traits") or []),
            race=str(cur.get("race") or ""),
            gender=str(cur.get("gender") or ""),
            appearance=dict(cur.get("appearance") or {}) or None,
            narrative_text=narrative_text or "",
        )
        if not contact_res:
            return None

        first_met = cur.get("first_met_turn") if cur.get("first_met_turn") is not None else t_num
        conn.execute(
            """UPDATE world_roster
               SET tier_status = 'promoted', met_in_person = 1, first_met_turn = ?,
                   turn_snapshots_json = ?, turn_updated = ?, updated_at = ?
               WHERE id = ?""",
            (first_met, json.dumps(snaps), t_num, now, cur["id"]),
        )
        try:
            conn.execute(
                """UPDATE school_directory SET is_hydrated = 1
                   WHERE session_id = ? AND (LOWER(npc_id) = ? OR LOWER(name) = ?)""",
                (sid, cur["npc_id"].lower(), cur["name"].lower()),
            )
        except sqlite3.OperationalError:
            pass

        return contact_res


def rollback_world_roster_after_turn(
    session_id: int,
    turn_number: int,
    conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    """Rolls back `world_roster` mutations, future-created rows, and promoted `contacts` strictly after `turn_number`."""
    if not session_id:
        return {"roster_deleted": 0, "roster_restored": 0, "promoted_contacts_reverted": 0}
    sid = int(session_id)
    t_num = int(turn_number)
    now = time.time()

    def _run(c: sqlite3.Connection) -> dict[str, int]:
        _ensure_world_roster_table(c)
        del_cur = c.execute(
            "DELETE FROM world_roster WHERE session_id = ? AND turn_created > ?",
            (sid, t_num),
        )
        roster_deleted = int(del_cur.rowcount or 0)
        roster_restored = 0
        promoted_contacts_reverted = 0

        restored_sync_by_key: dict[str, dict[str, Any]] = {}
        rows = c.execute("SELECT * FROM world_roster WHERE session_id = ?", (sid,)).fetchall()
        for r in rows:
            cur = _hydrate_roster_row(r)
            snaps = dict(cur.get("turn_snapshots") or {})
            future_turns: list[tuple[int, str]] = []
            for k in snaps:
                try:
                    ki = int(k)
                except (TypeError, ValueError):
                    continue
                if ki > t_num:
                    future_turns.append((ki, str(k)))

            if not future_turns:
                continue

            future_turns.sort(key=lambda item: item[0])
            earliest_key = future_turns[0][1]
            snap = snaps.get(earliest_key)
            for _, fk in future_turns:
                snaps.pop(fk, None)

            if isinstance(snap, dict):
                rest_tier = str(snap.get("tier_status") or cur["tier_status"])
                rest_aff = _clamp_affinity(snap.get("affinity_score", cur["affinity_score"]))
                rest_met = int(bool(snap.get("met_in_person", cur["met_in_person"])))
                rest_first_met = snap.get("first_met_turn", cur.get("first_met_turn"))
                rest_staff = str(snap.get("staff_status") or cur["staff_status"])
                rest_staff_day = int(snap.get("staff_status_day", cur["staff_status_day"]))
                rest_res_unlocked = int(bool(snap.get("residence_unlocked", cur["residence_unlocked"])))
                rest_res_reason = str(snap.get("residence_unlock_reason", cur["residence_unlock_reason"]) or "")
                rest_home = str(snap.get("home_node_id", cur["home_node_id"]) or "")
                rest_slots = _merge_discovered_slots(
                    {}, snap.get("discovered_slots") if isinstance(snap.get("discovered_slots"), dict) else {}
                )
                rest_basic = (
                    dict(snap["basic_info"])
                    if isinstance(snap.get("basic_info"), dict)
                    else dict(cur.get("basic_info") or {})
                )
                c.execute(
                    """UPDATE world_roster
                       SET tier_status = ?, affinity_score = ?, met_in_person = ?, first_met_turn = ?,
                           staff_status = ?, staff_status_day = ?, residence_unlocked = ?,
                           residence_unlock_reason = ?, home_node_id = ?, discovered_slots_json = ?,
                           basic_info_json = ?, turn_snapshots_json = ?, turn_updated = ?, updated_at = ?
                       WHERE id = ?""",
                    (
                        rest_tier,
                        rest_aff,
                        rest_met,
                        rest_first_met,
                        rest_staff,
                        rest_staff_day,
                        rest_res_unlocked,
                        rest_res_reason,
                        rest_home,
                        json.dumps(rest_slots),
                        json.dumps(rest_basic),
                        json.dumps(snaps),
                        min(int(cur.get("turn_updated") or 0), t_num),
                        now,
                        cur["id"],
                    ),
                )
                roster_restored += 1
                sync_payload = {
                    "discovered_slots": rest_slots,
                    "residence_unlocked": bool(rest_res_unlocked),
                    "home_node_id": rest_home,
                }
                restored_sync_by_key[cur["npc_id"].lower()] = sync_payload
                restored_sync_by_key[cur["name"].lower()] = sync_payload
            else:
                c.execute(
                    "UPDATE world_roster SET turn_snapshots_json = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(snaps), now, cur["id"]),
                )

        try:
            c_rows = c.execute(
                "SELECT id, npc_id, name, basic_info_json FROM contacts WHERE session_id = ?",
                (sid,),
            ).fetchall()
        except sqlite3.OperationalError:
            c_rows = []

        for cr in c_rows:
            c_info = _parse_json_dict(cr["basic_info_json"])
            prom_turn_raw = c_info.get("promoted_from_roster_turn")
            prom_turn: int | None = None
            if prom_turn_raw is not None:
                try:
                    prom_turn = int(prom_turn_raw)
                except (TypeError, ValueError):
                    prom_turn = None

            c_npc_low = str(cr["npc_id"] or "").strip().lower()
            c_name_low = str(cr["name"] or "").strip().lower()
            if prom_turn is not None and prom_turn > t_num:
                c.execute("DELETE FROM contacts WHERE id = ?", (cr["id"],))
                promoted_contacts_reverted += 1
                try:
                    c.execute(
                        """UPDATE school_directory SET is_hydrated = 0
                           WHERE session_id = ? AND (LOWER(npc_id) = ? OR LOWER(name) = ?)""",
                        (sid, c_npc_low, c_name_low),
                    )
                except sqlite3.OperationalError:
                    pass
                continue

            sync = restored_sync_by_key.get(c_npc_low) or restored_sync_by_key.get(c_name_low)
            if sync is not None:
                dirty = False
                if c_info.get("discovered_slots") != sync["discovered_slots"]:
                    c_info["discovered_slots"] = dict(sync["discovered_slots"])
                    dirty = True
                if not sync["residence_unlocked"] and "residence_unlocked" in c_info:
                    c_info.pop("residence_unlocked", None)
                    dirty = True
                elif sync["residence_unlocked"] and not c_info.get("residence_unlocked"):
                    c_info["residence_unlocked"] = True
                    dirty = True
                if sync["home_node_id"]:
                    if c_info.get("home_node_id") != sync["home_node_id"]:
                        c_info["home_node_id"] = sync["home_node_id"]
                        dirty = True
                elif "home_node_id" in c_info:
                    c_info.pop("home_node_id", None)
                    dirty = True
                if dirty:
                    c.execute(
                        "UPDATE contacts SET basic_info_json = ?, updated_at = ? WHERE id = ?",
                        (json.dumps(c_info), now, cr["id"]),
                    )

        return {
            "roster_deleted": roster_deleted,
            "roster_restored": roster_restored,
            "promoted_contacts_reverted": promoted_contacts_reverted,
        }

    with _conn_ctx(conn) as c:
        return _run(c)
