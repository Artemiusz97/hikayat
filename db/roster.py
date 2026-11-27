from __future__ import annotations

"""
Normalized SQLite Persistence for Closed-World NPC Roster (`world_roster` table).

Provides unified storage, turn-indexed snapshots, schedule/residence/staff-status
tracking, promotion to `contacts`, and atomic turn rollback parity. Legacy roster
adaptation is delegated to `db.roster_adapters`.
"""

import json
import sqlite3
import time
from typing import Any, Callable, Mapping, Sequence

import db
from .core import UnitOfWork, _conn_ctx, _opt_int, ensure_table_group_once
from .roster_adapters import (
    ALLOWED_ROSTER_ORIGINS,
    ALLOWED_ROSTER_TIERS,
    ALLOWED_SHIFT_PROFILES,
    ALLOWED_STAFF_STATUSES,
    adapt_legacy_rosters,
    clamp_affinity,
    collect_existing_roster_and_contact_keys,
    merge_dict_safely,
    mirror_anchors_into_basic_info,
    parse_json_dict,
    parse_json_list,
    pick_non_empty,
    slugify_npc_id,
)

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


def _ensure_world_roster_table(conn: sqlite3.Connection) -> None:
    """Self-healing DDL guard for isolated unit tests that bypass full migrations."""
    def _create_if_missing(c: sqlite3.Connection) -> None:
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='world_roster' LIMIT 1").fetchone():
            return
        for sql in WORLD_ROSTER_V54_DDL:
            c.execute(sql)

    ensure_table_group_once(conn, "world_roster_v54", _create_if_missing)


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
                bk_s, loc_s = str(bk or "").strip(), str(loc or "").strip()
                if bk_s and loc_s:
                    target[bk_s] = loc_s
    return out


def _dedupe_str_list(existing: list[Any], incoming: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in list(existing or []) + list(incoming or []):
        s = str(item or "").strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out


def _hydrate_roster_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    d = dict(row)
    d["session_id"] = int(d.get("session_id") or 0)
    d["affinity_score"] = clamp_affinity(d.get("affinity_score") or 0)
    for bkey in ("met_in_person", "is_unique_proprietor", "residence_unlocked"):
        d[bkey] = bool(d.get(bkey))
    for ikey in ("staff_status_day", "turn_created", "turn_updated"):
        d[ikey] = int(d.get(ikey) or 0)
    if d.get("first_met_turn") is not None:
        d["first_met_turn"] = int(d["first_met_turn"])
    d["roaming_route"] = parse_json_list(d.get("roaming_route_json"))
    d["discovered_slots"] = parse_json_dict(d.get("discovered_slots_json"))
    d["basic_info"] = parse_json_dict(d.get("basic_info_json"))
    d["appearance"] = parse_json_dict(d.get("appearance_json"))
    d["traits"] = parse_json_list(d.get("traits_json"))
    d["turn_snapshots"] = parse_json_dict(d.get("turn_snapshots_json"))
    return d


def _capture_turn_snapshot(snapshots: dict[str, Any], row: dict[str, Any], turn_number: int) -> dict[str, Any]:
    out = dict(snapshots) if isinstance(snapshots, dict) else {}
    t_key = str(int(turn_number))
    if t_key not in out:
        out[t_key] = {
            "origin": str(row.get("origin") or "venue_seed"),
            "tier_status": str(row.get("tier_status") or "seeded"),
            "affinity_score": clamp_affinity(row.get("affinity_score") or 0),
            "met_in_person": int(bool(row.get("met_in_person"))),
            "first_met_turn": row.get("first_met_turn"),
            "staff_status": str(row.get("staff_status") or "active"),
            "staff_status_day": int(row.get("staff_status_day") or 0),
            "residence_unlocked": int(bool(row.get("residence_unlocked"))),
            "residence_unlock_reason": str(row.get("residence_unlock_reason") or ""),
            "home_node_id": str(row.get("home_node_id") or ""),
            "workplace_node_id": str(row.get("workplace_node_id") or ""),
            "hangout_node_id": str(row.get("hangout_node_id") or ""),
            "discovered_slots": json.loads(json.dumps(row.get("discovered_slots") or {})),
            "basic_info": json.loads(json.dumps(row.get("basic_info") or {})),
        }
    if len(out) > MAX_TURN_SNAPSHOTS:
        sortable = [(-1 if _opt_int(k) is None else int(k), str(k)) for k in out]
        sortable.sort(key=lambda item: item[0])
        for _, drop_key in sortable[: len(out) - MAX_TURN_SNAPSHOTS]:
            out.pop(drop_key, None)
    return out


def _matches_npc_key(npc_id: str, name: str, raw_needle: str, slug_needle: str) -> bool:
    nid, nm = str(npc_id or "").strip().lower(), str(name or "").strip()
    if raw_needle and (nid == raw_needle or nm.lower() == raw_needle):
        return True
    return bool(slug_needle and (nid == slug_needle or slugify_npc_id(nm) == slug_needle))


def _find_roster_row(conn: sqlite3.Connection, session_id: int, npc_key_or_name: str) -> sqlite3.Row | None:
    raw_needle = str(npc_key_or_name or "").strip().lower()
    slug_needle = slugify_npc_id(npc_key_or_name)
    if not raw_needle and not slug_needle:
        return None
    row = conn.execute(
        """SELECT * FROM world_roster WHERE session_id = ?
             AND (LOWER(npc_id) = ? OR LOWER(npc_id) = ? OR LOWER(name) = ?)
           ORDER BY id ASC LIMIT 1""",
        (int(session_id), raw_needle, slug_needle, raw_needle),
    ).fetchone()
    if row is not None or not slug_needle:
        return row
    for candidate in conn.execute("SELECT * FROM world_roster WHERE session_id = ? ORDER BY id ASC", (int(session_id),)).fetchall():
        if slugify_npc_id(candidate["name"]) == slug_needle:
            return candidate
    return None


def _materialize_or_find_roster_row(conn: sqlite3.Connection, session_id: int, npc_key_or_name: str) -> sqlite3.Row | None:
    row = _find_roster_row(conn, session_id, npc_key_or_name)
    if row is not None:
        return row
    raw_needle, slug_needle = str(npc_key_or_name or "").strip().lower(), slugify_npc_id(npc_key_or_name)
    if not raw_needle and not slug_needle:
        return None
    seen_ids, seen_names = collect_existing_roster_and_contact_keys(conn, session_id)
    for entry in adapt_legacy_rosters(conn, session_id, seen_ids, seen_names):
        if _matches_npc_key(entry["npc_id"], entry["name"], raw_needle, slug_needle):
            upsert_world_roster_npc(session_id, entry, turn_number=0, conn=conn)
            return _find_roster_row(conn, session_id, entry["npc_id"])
    return None


def _load_and_snapshot(
    conn: sqlite3.Connection,
    sid: int,
    npc_key_or_name: str,
    t_num: int,
    *,
    materialize: bool = True,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    _ensure_world_roster_table(conn)
    row = _materialize_or_find_roster_row(conn, sid, npc_key_or_name) if materialize else _find_roster_row(conn, sid, npc_key_or_name)
    if row is None:
        return None
    cur = _hydrate_roster_row(row)
    return cur, _capture_turn_snapshot(cur.get("turn_snapshots") or {}, cur, t_num)


def _update_matching_contacts_basic_info(
    conn: sqlite3.Connection,
    session_id: int,
    npc_id: str,
    name: str,
    mutator: Callable[[dict[str, Any]], None],
    now: float,
) -> None:
    rows = conn.execute(
        "SELECT id, basic_info_json FROM contacts WHERE session_id = ? AND (LOWER(npc_id) = ? OR LOWER(name) = ?)",
        (session_id, npc_id.lower(), name.lower()),
    ).fetchall()
    for cr in rows:
        c_info = parse_json_dict(cr["basic_info_json"])
        mutator(c_info)
        conn.execute("UPDATE contacts SET basic_info_json = ?, updated_at = ? WHERE id = ?", (json.dumps(c_info), now, cr["id"]))


def _pick_allowed(raw: Any, existing_val: Any, allowed: frozenset[str], default: str) -> str:
    candidate = str(raw or existing_val or default).strip()
    if candidate in allowed:
        return candidate
    fallback = str(existing_val or default).strip()
    return fallback if fallback in allowed else default


def _set_school_hydrated(conn: sqlite3.Connection, sid: int, npc_id_low: str, name_low: str, flag: int) -> None:
    try:
        conn.execute(
            "UPDATE school_directory SET is_hydrated = ? WHERE session_id = ? AND (LOWER(npc_id) = ? OR LOWER(name) = ?)",
            (flag, sid, npc_id_low, name_low),
        )
    except sqlite3.OperationalError:
        pass


def _json_field(data: dict[str, Any], key: str, json_key: str, parser: Callable[[Any], Any]) -> Any:
    return parser(data.get(key) if key in data else data.get(json_key))


def _first_present(sources: tuple[dict[str, Any], ...], key: str) -> Any:
    for src in sources:
        if key in src:
            return src[key]
    return None


def _update_roster_columns(conn: sqlite3.Connection, row_id: int, cols: dict[str, Any]) -> sqlite3.Row | None:
    set_sql = ", ".join(f"{col} = ?" for col in cols)
    conn.execute(f"UPDATE world_roster SET {set_sql} WHERE id = ?", (*cols.values(), row_id))
    return conn.execute("SELECT * FROM world_roster WHERE id = ?", (row_id,)).fetchone()


def _build_roster_upsert_columns(npc_data: dict[str, Any], existing: dict[str, Any], final_name: str, t_num: int) -> dict[str, Any]:
    in_basic = _json_field(npc_data, "basic_info", "basic_info_json", parse_json_dict)
    in_app = _json_field(npc_data, "appearance", "appearance_json", parse_json_dict)
    in_slots = _json_field(npc_data, "discovered_slots", "discovered_slots_json", parse_json_dict)
    in_traits = _json_field(npc_data, "traits", "traits_json", parse_json_list)
    in_route = _json_field(npc_data, "roaming_route", "roaming_route_json", parse_json_list) if ("roaming_route" in npc_data or "roaming_route_json" in npc_data) else None

    role = pick_non_empty(npc_data.get("role"), in_basic.get("role"), existing.get("role"))
    raw_aff = npc_data.get("affinity_score")
    affinity_score = clamp_affinity(raw_aff if raw_aff is not None else (existing.get("affinity_score") if existing else npc_data.get("initial_affinity") or 0))
    met_in_person = int(bool(_first_present((npc_data, existing), "met_in_person")))
    explicit_fmt = _opt_int(npc_data.get("first_met_turn"))
    first_met_turn = explicit_fmt if explicit_fmt is not None else (existing.get("first_met_turn") if existing.get("first_met_turn") is not None else (t_num if met_in_person else None))

    workplace, home, hangout = (
        pick_non_empty(npc_data.get(k), in_basic.get(k), existing.get(k))
        for k in ("workplace_node_id", "home_node_id", "hangout_node_id")
    )
    shift_profile = _pick_allowed(
        pick_non_empty(npc_data.get("shift_profile"), in_basic.get("shift_profile")),
        existing.get("shift_profile"), ALLOWED_SHIFT_PROFILES, "day",
    )
    res_unlocked = int(bool(_first_present((npc_data, in_basic, existing), "residence_unlocked")))
    roaming_route = [str(x).strip() for x in in_route if str(x or "").strip()] if in_route is not None and (in_route or not existing) else list(existing.get("roaming_route") or [])
    merged_basic = merge_dict_safely(existing.get("basic_info") or {}, in_basic)
    if role:
        merged_basic.setdefault("role", role)
    merged_basic = mirror_anchors_into_basic_info(merged_basic, workplace, home, hangout, shift_profile, bool(res_unlocked))
    staff_day = _opt_int(npc_data.get("staff_status_day"))
    return {
        "name": final_name,
        "gender": pick_non_empty(npc_data.get("gender"), in_basic.get("gender"), existing.get("gender")),
        "race": pick_non_empty(npc_data.get("race"), in_basic.get("race"), existing.get("race"), default="human"),
        "role": role,
        "origin": _pick_allowed(npc_data.get("origin"), existing.get("origin"), ALLOWED_ROSTER_ORIGINS, "venue_seed"),
        "tier_status": _pick_allowed(npc_data.get("tier_status"), existing.get("tier_status"), ALLOWED_ROSTER_TIERS, "seeded"),
        "affinity_score": affinity_score, "met_in_person": met_in_person, "first_met_turn": first_met_turn,
        "workplace_node_id": workplace, "home_node_id": home, "hangout_node_id": hangout,
        "roaming_route_json": json.dumps(roaming_route), "shift_profile": shift_profile,
        "staff_status": _pick_allowed(str(npc_data.get("staff_status") or "").strip().lower(), existing.get("staff_status"), ALLOWED_STAFF_STATUSES, "active"),
        "staff_status_day": staff_day if staff_day is not None else int(existing.get("staff_status_day") or 0),
        "is_unique_proprietor": int(bool(_first_present((npc_data, existing), "is_unique_proprietor"))),
        "residence_unlocked": res_unlocked,
        "residence_unlock_reason": pick_non_empty(npc_data.get("residence_unlock_reason"), existing.get("residence_unlock_reason")),
        "discovered_slots_json": json.dumps(_merge_discovered_slots(existing.get("discovered_slots") or {}, in_slots)),
        "basic_info_json": json.dumps(merged_basic),
        "appearance_json": json.dumps(merge_dict_safely(existing.get("appearance") or {}, in_app)),
        "traits_json": json.dumps(_dedupe_str_list(existing.get("traits") or [], in_traits)),
    }


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
    raw_name, raw_npc_id = str(npc_data.get("name") or "").strip(), str(npc_data.get("npc_id") or "").strip()
    default_npc_id = slugify_npc_id(raw_npc_id or raw_name)
    if not default_npc_id:
        return {}
    now, t_num = time.time(), int(turn_number)

    def _run(c: sqlite3.Connection) -> dict[str, Any]:
        _ensure_world_roster_table(c)
        resolved_npc_id = default_npc_id
        existing_row: sqlite3.Row | None = None
        if not raw_npc_id and raw_name:
            existing_row = _find_roster_row(c, sid, raw_name)
            if existing_row is not None:
                resolved_npc_id = str(existing_row["npc_id"])
        if existing_row is None:
            existing_row = c.execute(
                "SELECT * FROM world_roster WHERE session_id = ? AND npc_id = ? LIMIT 1", (sid, resolved_npc_id)
            ).fetchone()

        existing = _hydrate_roster_row(existing_row) if existing_row is not None else {}
        final_name = raw_name or str(existing.get("name") or raw_npc_id or "").strip()
        if not final_name:
            return {}

        cols = _build_roster_upsert_columns(npc_data, existing, final_name, t_num)
        if existing_row is not None:
            row_out = _update_roster_columns(
                c, int(existing_row["id"]),
                {**cols, "turn_snapshots_json": json.dumps(existing.get("turn_snapshots") or {}), "turn_updated": t_num, "updated_at": now},
            )
        else:
            snaps = parse_json_dict(npc_data.get("turn_snapshots") or npc_data.get("turn_snapshots_json"))
            insert_cols = {"session_id": sid, "npc_id": resolved_npc_id, **cols, "turn_snapshots_json": json.dumps(snaps), "turn_created": t_num, "turn_updated": t_num, "created_at": now, "updated_at": now}
            cur = c.execute(
                f"INSERT INTO world_roster ({', '.join(insert_cols.keys())}) VALUES ({', '.join('?' for _ in insert_cols)})",
                tuple(insert_cols.values()),
            )
            row_out = c.execute("SELECT * FROM world_roster WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _hydrate_roster_row(row_out) if row_out is not None else {}

    with _conn_ctx(conn) as c:
        return _run(c)


def bulk_upsert_world_roster(
    session_id: int,
    npcs: list[dict[str, Any]],
    turn_number: int = 0,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Inserts many `world_roster` NPCs in a single transaction, skipping already-present IDs/names."""
    if not session_id or not npcs:
        return []
    sid = int(session_id)
    now, t_num = time.time(), int(turn_number)

    def _run(c: sqlite3.Connection) -> list[dict[str, Any]]:
        _ensure_world_roster_table(c)
        existing_rows = c.execute(
            "SELECT npc_id, name FROM world_roster WHERE session_id = ?",
            (sid,),
        ).fetchall()
        seen_ids: set[str] = {str(r["npc_id"] or "").strip().lower() for r in existing_rows}
        seen_names: set[str] = {str(r["name"] or "").strip().lower() for r in existing_rows}

        batch_rows: list[tuple[Any, ...]] = []
        col_names: tuple[str, ...] | None = None
        inserted_ids: list[str] = []

        for npc_data in npcs:
            if not isinstance(npc_data, dict):
                continue
            raw_name = str(npc_data.get("name") or "").strip()
            raw_npc_id = str(npc_data.get("npc_id") or "").strip()
            resolved_npc_id = slugify_npc_id(raw_npc_id or raw_name)
            final_name = raw_name or raw_npc_id
            if not resolved_npc_id or not final_name:
                continue
            if resolved_npc_id.lower() in seen_ids or final_name.lower() in seen_names:
                continue
            seen_ids.add(resolved_npc_id.lower())
            seen_names.add(final_name.lower())

            cols = _build_roster_upsert_columns(npc_data, {}, final_name, t_num)
            snaps = parse_json_dict(npc_data.get("turn_snapshots") or npc_data.get("turn_snapshots_json"))
            insert_cols = {
                "session_id": sid,
                "npc_id": resolved_npc_id,
                **cols,
                "turn_snapshots_json": json.dumps(snaps),
                "turn_created": t_num,
                "turn_updated": t_num,
                "created_at": now,
                "updated_at": now,
            }
            if col_names is None:
                col_names = tuple(insert_cols.keys())
            batch_rows.append(tuple(insert_cols[k] for k in col_names))
            inserted_ids.append(resolved_npc_id)

        if not batch_rows or col_names is None:
            return []

        placeholders = ", ".join("?" for _ in col_names)
        c.executemany(
            f"INSERT OR IGNORE INTO world_roster ({', '.join(col_names)}) VALUES ({placeholders})",
            batch_rows,
        )
        out: list[dict[str, Any]] = []
        for idx in range(0, len(inserted_ids), 200):
            chunk = inserted_ids[idx : idx + 200]
            q_marks = ", ".join("?" for _ in chunk)
            rows = c.execute(
                f"SELECT * FROM world_roster WHERE session_id = ? AND npc_id IN ({q_marks}) ORDER BY id ASC",
                (sid, *chunk),
            ).fetchall()
            out.extend(_hydrate_roster_row(r) for r in rows)
        return out

    with _conn_ctx(conn) as c:
        return _run(c)


def hydrate_world_roster_visuals(
    session_id: int,
    updates: list[dict[str, Any]],
    conn: sqlite3.Connection | None = None,
) -> int:
    """Persists Stage 1 on-scene visual/trait/basic_info hydration onto `world_roster` rows."""
    if not session_id or not updates:
        return 0
    sid = int(session_id)
    now = time.time()

    def _run(c: sqlite3.Connection) -> int:
        _ensure_world_roster_table(c)
        all_rows = c.execute(
            "SELECT * FROM world_roster WHERE session_id = ? ORDER BY id ASC",
            (sid,),
        ).fetchall()
        if not all_rows:
            return 0
        by_nid: dict[str, sqlite3.Row] = {}
        by_name: dict[str, sqlite3.Row] = {}
        by_slug: dict[str, sqlite3.Row] = {}
        for r in all_rows:
            nid_low = str(r["npc_id"] or "").strip().lower()
            nm_raw = str(r["name"] or "").strip()
            nm_low = nm_raw.lower()
            nm_slug = slugify_npc_id(nm_raw)
            if nid_low and nid_low not in by_nid:
                by_nid[nid_low] = r
            if nm_low and nm_low not in by_name:
                by_name[nm_low] = r
            if nm_slug and nm_slug not in by_slug:
                by_slug[nm_slug] = r

        updated = 0
        for item in updates:
            if not isinstance(item, dict):
                continue
            key = str(item.get("npc_id") or item.get("name") or "").strip()
            if not key:
                continue
            raw_needle = key.lower()
            slug_needle = slugify_npc_id(key)
            row = by_nid.get(raw_needle) or (by_nid.get(slug_needle) if slug_needle else None) or by_name.get(raw_needle) or (by_slug.get(slug_needle) if slug_needle else None)
            if row is None:
                continue
            existing = _hydrate_roster_row(row)
            in_app = item.get("appearance") if isinstance(item.get("appearance"), dict) else {}
            in_traits = item.get("traits") if isinstance(item.get("traits"), list) else []
            in_basic = item.get("basic_info_updates") if isinstance(item.get("basic_info_updates"), dict) else {}

            merged_app = merge_dict_safely(existing.get("appearance") or {}, in_app)
            merged_traits = _dedupe_str_list(existing.get("traits") or [], in_traits)
            merged_basic = merge_dict_safely(existing.get("basic_info") or {}, in_basic)
            merged_basic["visual_hydrated"] = True

            c.execute(
                """UPDATE world_roster
                   SET appearance_json = ?, traits_json = ?, basic_info_json = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    json.dumps(merged_app),
                    json.dumps(merged_traits),
                    json.dumps(merged_basic),
                    now,
                    int(row["id"]),
                ),
            )
            updated += 1
        return updated

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
        clauses, params = ["session_id = ?"], [sid]
        if tier_status is not None:
            clauses.append("tier_status = ?")
            params.append(str(tier_status))
        if workplace_node_id is not None:
            clauses.append("workplace_node_id = ?")
            params.append(str(workplace_node_id))

        rows = c.execute(f"SELECT * FROM world_roster WHERE {' AND '.join(clauses)} ORDER BY id ASC", params).fetchall()
        results = [_hydrate_roster_row(r) for r in rows]
        if include_legacy_rosters:
            seen_ids, seen_names = collect_existing_roster_and_contact_keys(c, sid)
            for adapted in adapt_legacy_rosters(c, sid, seen_ids, seen_names):
                if (tier_status is None or adapted["tier_status"] == str(tier_status)) and (
                    workplace_node_id is None or adapted["workplace_node_id"] == str(workplace_node_id)
                ):
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
    raw_needle, slug_needle = str(npc_key_or_name).strip().lower(), slugify_npc_id(npc_key_or_name)

    def _run(c: sqlite3.Connection) -> dict[str, Any] | None:
        _ensure_world_roster_table(c)
        row = _find_roster_row(c, sid, npc_key_or_name)
        if row is not None:
            return _hydrate_roster_row(row)
        if include_legacy_rosters:
            seen_ids, seen_names = collect_existing_roster_and_contact_keys(c, sid)
            for adapted in adapt_legacy_rosters(c, sid, seen_ids, seen_names):
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
    sid, t_num, now = int(session_id), int(turn_number), time.time()

    def _run(c: sqlite3.Connection) -> dict[str, Any] | None:
        loaded = _load_and_snapshot(c, sid, npc_key_or_name, t_num, materialize=True)
        if loaded is None:
            return None
        cur, snaps = loaded
        new_tier = str(cur.get("tier_status") or "seeded")
        new_met = int(bool(cur.get("met_in_person")))
        new_first_met = cur.get("first_met_turn")
        if met_in_person:
            new_met = 1
            if new_first_met is None:
                new_first_met = t_num
            if new_tier == "seeded":
                new_tier = "acquaintance"

        slots = _merge_discovered_slots(cur.get("discovered_slots") or {}, {})
        if isinstance(discovered_slot, (tuple, list)) and len(discovered_slot) == 3:
            dk, bk, loc = str(discovered_slot[0] or "").strip().lower(), str(discovered_slot[1] or "").strip(), str(discovered_slot[2] or "").strip()
            if dk in ("weekday", "weekend") and bk and loc:
                slots.setdefault(dk, {})[bk] = loc

        updated = _update_roster_columns(
            c, int(cur["id"]),
            {
                "tier_status": new_tier, "affinity_score": clamp_affinity(int(cur.get("affinity_score") or 0) + int(delta_score or 0)),
                "met_in_person": new_met, "first_met_turn": new_first_met, "discovered_slots_json": json.dumps(slots),
                "turn_snapshots_json": json.dumps(snaps), "turn_updated": t_num, "updated_at": now,
            },
        )
        return _hydrate_roster_row(updated) if updated is not None else None

    with _conn_ctx(conn) as c:
        return _run(c)


def record_discovered_schedule_slot(
    session_id: int, npc_key_or_name: str, day_kind: str, block_key: str, location_label: str,
    turn_number: int = 1, conn: sqlite3.Connection | None = None,
) -> bool:
    """Records an observed/inquired schedule slot into `world_roster` and mirrors to `contacts.basic_info_json`."""
    dk, bk, loc = str(day_kind or "").strip().lower(), str(block_key or "").strip(), str(location_label or "").strip()
    if not session_id or dk not in ("weekday", "weekend") or not bk or not loc:
        return False
    sid, t_num, now = int(session_id), int(turn_number), time.time()

    def _run(c: sqlite3.Connection) -> bool:
        loaded = _load_and_snapshot(c, sid, npc_key_or_name, t_num, materialize=True)
        if loaded is None:
            return False
        cur, snaps = loaded
        slots = _merge_discovered_slots(cur.get("discovered_slots") or {}, {dk: {bk: loc}})
        _update_roster_columns(c, int(cur["id"]), {"discovered_slots_json": json.dumps(slots), "turn_snapshots_json": json.dumps(snaps), "turn_updated": t_num, "updated_at": now})

        def _apply_slot(c_info: dict[str, Any]) -> None:
            prev = c_info.get("discovered_slots")
            c_info["discovered_slots"] = _merge_discovered_slots(prev if isinstance(prev, dict) else {}, {dk: {bk: loc}})

        _update_matching_contacts_basic_info(c, sid, cur["npc_id"], cur["name"], _apply_slot, now)
        return True

    with _conn_ctx(conn) as c:
        return _run(c)


def set_world_roster_residence_unlocked(
    session_id: int, npc_key_or_name: str, reason: str, home_node_id: str = "",
    turn_number: int = 1, conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Marks an NPC's residence unlocked in `world_roster` (with snapshot) and mirrors onto `contacts`."""
    if not session_id or not str(npc_key_or_name or "").strip():
        return None
    sid, t_num, now = int(session_id), int(turn_number), time.time()
    clean_home, clean_reason = str(home_node_id or "").strip(), str(reason or "").strip()

    def _run(c: sqlite3.Connection) -> dict[str, Any] | None:
        loaded = _load_and_snapshot(c, sid, npc_key_or_name, t_num, materialize=True)
        if loaded is None:
            return None
        cur, snaps = loaded
        final_home = clean_home or str(cur.get("home_node_id") or "")
        b_info = dict(cur.get("basic_info") or {})
        b_info["residence_unlocked"] = True
        if final_home:
            b_info["home_node_id"] = final_home
        updated = _update_roster_columns(
            c, int(cur["id"]),
            {"residence_unlocked": 1, "residence_unlock_reason": clean_reason, "home_node_id": final_home, "basic_info_json": json.dumps(b_info), "turn_snapshots_json": json.dumps(snaps), "turn_updated": t_num, "updated_at": now},
        )

        def _apply_unlock(c_info: dict[str, Any]) -> None:
            c_info["residence_unlocked"] = True
            if final_home:
                c_info["home_node_id"] = final_home

        _update_matching_contacts_basic_info(c, sid, cur["npc_id"], cur["name"], _apply_unlock, now)
        return _hydrate_roster_row(updated) if updated is not None else None

    with _conn_ctx(conn) as c:
        return _run(c)


def mark_world_roster_staff_status(
    session_id: int, npc_key_or_name: str, staff_status: str, day_changed: int,
    turn_number: int = 1, conn: sqlite3.Connection | None = None,
) -> bool:
    """Updates an NPC's `staff_status` in `world_roster` with turn-snapshot capture."""
    st = str(staff_status or "").strip().lower()
    if st not in ALLOWED_STAFF_STATUSES:
        raise ValueError(f"Invalid staff_status {staff_status!r}; expected one of {sorted(ALLOWED_STAFF_STATUSES)}")
    if not session_id or not str(npc_key_or_name or "").strip():
        return False
    sid, t_num, now = int(session_id), int(turn_number), time.time()

    def _run(c: sqlite3.Connection) -> bool:
        loaded = _load_and_snapshot(c, sid, npc_key_or_name, t_num, materialize=False)
        if loaded is None:
            return False
        cur, snaps = loaded
        _update_roster_columns(c, int(cur["id"]), {"staff_status": st, "staff_status_day": int(day_changed), "turn_snapshots_json": json.dumps(snaps), "turn_updated": t_num, "updated_at": now})
        return True

    with _conn_ctx(conn) as c:
        return _run(c)


def clear_roster_npc_merchant_archetypes(
    session_id: int,
    npc_id: str,
    new_role: str | None = None,
    new_occupation: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> bool:
    """Clear stale `merchant_archetypes` on a `world_roster` NPC row without clobbering identity or contacts."""
    raw_nid = str(npc_id or "").strip()
    if not session_id or not raw_nid:
        return False
    sid, now = int(session_id), time.time()

    def _run(c: sqlite3.Connection) -> bool:
        _ensure_world_roster_table(c)
        row = c.execute(
            "SELECT * FROM world_roster WHERE session_id = ? AND (npc_id = ? OR lower(npc_id) = ?) LIMIT 1",
            (sid, raw_nid, raw_nid.lower()),
        ).fetchone()
        if row is None:
            return False
        basic_info = parse_json_dict(row["basic_info_json"])
        basic_info["merchant_archetypes"] = []
        role_val = str(row["role"] or "")
        if new_role is not None and str(new_role).strip():
            role_val = str(new_role).strip()
            basic_info["role"] = role_val
        if new_occupation is not None and str(new_occupation).strip():
            basic_info["occupation"] = str(new_occupation).strip()
        _update_roster_columns(
            c,
            int(row["id"]),
            {"role": role_val, "basic_info_json": json.dumps(basic_info), "updated_at": now},
        )
        return True

    with _conn_ctx(conn) as c:
        return _run(c)


_ALLOWED_HEAL_ROSTER_COLS: frozenset[str] = frozenset({
    "role",
    "workplace_node_id",
    "home_node_id",
    "hangout_node_id",
    "shift_profile",
    "staff_status",
})


def heal_world_roster_npc_employment(
    session_id: int,
    npc_id: str,
    *,
    updates: Mapping[str, Any] | None = None,
    basic_info_updates: Mapping[str, Any] | None = None,
    remove_basic_keys: Sequence[str] = (),
    conn: sqlite3.Connection | None = None,
) -> bool:
    """Safely updates employment/demographic fields on a `world_roster` NPC row and linked contacts."""
    raw_nid = str(npc_id or "").strip()
    if not session_id or not raw_nid:
        return False
    sid, now = int(session_id), time.time()

    def _run(c: sqlite3.Connection) -> bool:
        _ensure_world_roster_table(c)
        row = _find_roster_row(c, sid, raw_nid)
        if row is None:
            return False
        basic_info = parse_json_dict(row["basic_info_json"])
        for rk in (remove_basic_keys or ()):
            basic_info.pop(str(rk), None)
        if isinstance(basic_info_updates, Mapping):
            for bk, bv in basic_info_updates.items():
                basic_info[str(bk)] = bv

        col_updates: dict[str, Any] = {
            "basic_info_json": json.dumps(basic_info),
            "updated_at": now,
        }
        if isinstance(updates, Mapping):
            for ck, cv in updates.items():
                if ck in _ALLOWED_HEAL_ROSTER_COLS:
                    col_updates[ck] = str(cv or "").strip()

        _update_roster_columns(c, int(row["id"]), col_updates)

        def _sync_contact(c_info: dict[str, Any]) -> None:
            for rk in (remove_basic_keys or ()):
                c_info.pop(str(rk), None)
            if isinstance(basic_info_updates, Mapping):
                for bk, bv in basic_info_updates.items():
                    c_info[str(bk)] = bv

        _update_matching_contacts_basic_info(
            c,
            sid,
            str(row["npc_id"] or raw_nid),
            str(row["name"] or ""),
            _sync_contact,
            now,
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
    *,
    scenario: str | None = None,
) -> dict[str, Any] | None:
    """Promotes a `world_roster` (or legacy adapter) NPC into `contacts` while snapshotting pre-promotion state."""
    if not session_id or not str(npc_key_or_name or "").strip():
        return None
    sid, cid, t_num, now = int(session_id), int(character_id or 0), int(turn_number), time.time()

    with UnitOfWork() as conn:
        loaded = _load_and_snapshot(conn, sid, npc_key_or_name, t_num, materialize=True)
        if loaded is None:
            return None
        cur, snaps = loaded
        target_score = clamp_affinity(cur.get("affinity_score") or 0)

        char_filter = "AND (character_id = ? OR character_id = 0) " if cid else ""
        params: list[Any] = [sid, cid] if cid else [sid]
        params.extend([cur["npc_id"].lower(), cur["name"].lower()])
        existing_contact = conn.execute(
            f"SELECT relationship_score, basic_info_json FROM contacts WHERE session_id = ? {char_filter}AND (LOWER(npc_id) = ? OR LOWER(name) = ?) ORDER BY id ASC LIMIT 1",
            params,
        ).fetchone()

        existing_c_info = parse_json_dict(existing_contact["basic_info_json"]) if existing_contact is not None else {}
        delta_score = target_score - int(existing_contact["relationship_score"] or 0) if existing_contact is not None else target_score

        prev_turn = _opt_int(existing_c_info.get("promoted_from_roster_turn"))
        if prev_turn is not None:
            promoted_turn = min(prev_turn, t_num)
        elif cur.get("tier_status") == "promoted":
            fallback_turn = cur.get("first_met_turn") if cur.get("first_met_turn") is not None else cur.get("turn_updated")
            promoted_turn = min(int(fallback_turn), t_num) if fallback_turn is not None else t_num
        else:
            promoted_turn = t_num

        prev_reason = str(existing_c_info.get("promotion_reason") or "").strip()
        b_info = mirror_anchors_into_basic_info(
            dict(cur.get("basic_info") or {}),
            cur.get("workplace_node_id") or "", cur.get("home_node_id") or "", cur.get("hangout_node_id") or "",
            cur.get("shift_profile") or "day", bool(cur.get("residence_unlocked")),
        )
        if cur.get("role"):
            b_info["role"] = cur["role"]
        b_info.update({
            "roaming_route": list(cur.get("roaming_route") or []),
            "discovered_slots": dict(cur.get("discovered_slots") or {}),
            "met_in_person": True,
            "has_contact_info": bool(has_contact_info) or bool(existing_c_info.get("has_contact_info")),
            "promoted_from_roster_turn": promoted_turn,
            "promotion_reason": prev_reason if prev_reason else str(reason or ""),
        })

        contact_res = db.upsert_contact(
            session_id=sid, npc_id=cur["npc_id"], name=cur["name"], character_id=cid,
            basic_info=b_info, delta_score=delta_score, new_traits=list(cur.get("traits") or []),
            race=str(cur.get("race") or ""), gender=str(cur.get("gender") or ""),
            appearance=dict(cur.get("appearance") or {}) or None, narrative_text=narrative_text or "",
            scenario=scenario,
        )
        if not contact_res:
            return None

        first_met = cur.get("first_met_turn") if cur.get("first_met_turn") is not None else t_num
        _update_roster_columns(
            conn, int(cur["id"]),
            {"tier_status": "promoted", "met_in_person": 1, "first_met_turn": first_met, "turn_snapshots_json": json.dumps(snaps), "turn_updated": t_num, "updated_at": now},
        )
        _set_school_hydrated(conn, sid, cur["npc_id"].lower(), cur["name"].lower(), 1)
        return contact_res


def _resync_promoted_contact_row(conn: sqlite3.Connection, cr: sqlite3.Row, c_info: dict[str, Any], sync: dict[str, Any], now: float) -> None:
    dirty = c_info.get("discovered_slots") != sync["discovered_slots"]
    if dirty:
        c_info["discovered_slots"] = dict(sync["discovered_slots"])
    if bool(c_info.get("residence_unlocked")) != sync["residence_unlocked"] or (not sync["residence_unlocked"] and "residence_unlocked" in c_info):
        dirty = True
        if sync["residence_unlocked"]:
            c_info["residence_unlocked"] = True
        else:
            c_info.pop("residence_unlocked", None)
    for anchor_k in ("home_node_id", "workplace_node_id", "hangout_node_id"):
        if anchor_k not in sync:
            continue
        anchor_val = sync[anchor_k]
        if anchor_val and c_info.get(anchor_k) != anchor_val:
            c_info[anchor_k] = anchor_val
            dirty = True
        elif not anchor_val and anchor_k in c_info:
            c_info.pop(anchor_k, None)
            dirty = True
    if isinstance(sync.get("basic_info"), dict):
        sync_bi = sync["basic_info"]
        for opt_k in ("autonomy_override", "pending_hangout_ping"):
            if opt_k in sync_bi:
                if c_info.get(opt_k) != sync_bi[opt_k]:
                    c_info[opt_k] = json.loads(json.dumps(sync_bi[opt_k]))
                    dirty = True
            elif opt_k in c_info:
                c_info.pop(opt_k, None)
                dirty = True
    if dirty:
        conn.execute("UPDATE contacts SET basic_info_json = ?, updated_at = ? WHERE id = ?", (json.dumps(c_info), now, cr["id"]))


def _restore_snapshot_row(conn: sqlite3.Connection, cur: dict[str, Any], snap: dict[str, Any], snaps: dict[str, Any], t_num: int, now: float) -> dict[str, Any]:
    rest_res_unlocked = int(bool(snap.get("residence_unlocked", cur["residence_unlocked"])))
    rest_home = str(snap.get("home_node_id", cur["home_node_id"]) or "")
    rest_workplace = str(snap.get("workplace_node_id", cur.get("workplace_node_id") or "") or "")
    rest_hangout = str(snap.get("hangout_node_id", cur.get("hangout_node_id") or "") or "")
    rest_slots = _merge_discovered_slots({}, snap.get("discovered_slots") if isinstance(snap.get("discovered_slots"), dict) else {})
    rest_basic = dict(snap["basic_info"]) if isinstance(snap.get("basic_info"), dict) else dict(cur.get("basic_info") or {})
    _update_roster_columns(
        conn, int(cur["id"]),
        {
            "origin": _pick_allowed(snap.get("origin"), cur.get("origin"), ALLOWED_ROSTER_ORIGINS, "venue_seed"),
            "tier_status": str(snap.get("tier_status") or cur["tier_status"]),
            "affinity_score": clamp_affinity(snap.get("affinity_score", cur["affinity_score"])),
            "met_in_person": int(bool(snap.get("met_in_person", cur["met_in_person"]))),
            "first_met_turn": snap.get("first_met_turn", cur.get("first_met_turn")),
            "staff_status": str(snap.get("staff_status") or cur["staff_status"]),
            "staff_status_day": int(snap.get("staff_status_day", cur["staff_status_day"])),
            "residence_unlocked": rest_res_unlocked,
            "home_node_id": rest_home,
            "workplace_node_id": rest_workplace,
            "hangout_node_id": rest_hangout,
            "residence_unlock_reason": str(snap.get("residence_unlock_reason", cur["residence_unlock_reason"]) or ""),
            "discovered_slots_json": json.dumps(rest_slots), "basic_info_json": json.dumps(rest_basic),
            "turn_snapshots_json": json.dumps(snaps), "turn_updated": min(int(cur.get("turn_updated") or 0), t_num), "updated_at": now,
        },
    )
    return {
        "discovered_slots": rest_slots,
        "residence_unlocked": bool(rest_res_unlocked),
        "home_node_id": rest_home,
        "workplace_node_id": rest_workplace,
        "hangout_node_id": rest_hangout,
        "basic_info": rest_basic,
    }


def apply_world_roster_autonomy_mutations(
    session_id: int,
    mutations: list[dict[str, Any]],
    *,
    turn_number: int,
    conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    """Applies boundary-tick NPC schedule overrides, anchor shifts, pings, or replacement hires atomically with turn snapshots (`D8`, `D10`, `F3`)."""
    if not session_id or not mutations:
        return {"updated": 0, "created": 0}
    sid, t_num, now = int(session_id), int(turn_number), time.time()

    def _run(c: sqlite3.Connection) -> dict[str, int]:
        _ensure_world_roster_table(c)
        updated, created = 0, 0
        for mut in mutations:
            if not isinstance(mut, dict):
                continue
            rep = mut.get("replacement_npc")
            if isinstance(rep, dict) and (rep.get("name") or rep.get("npc_id")):
                rep_payload = dict(rep)
                rep_payload.setdefault("origin", "replacement_hire")
                res = upsert_world_roster_npc(sid, rep_payload, turn_number=t_num, conn=c)
                if res:
                    created += 1
                continue
            target_key = str(mut.get("npc_id") or mut.get("npc_key") or mut.get("name") or "").strip()
            if not target_key:
                continue
            loaded = _load_and_snapshot(c, sid, target_key, t_num, materialize=True)
            if loaded is None:
                continue
            cur, snaps = loaded
            new_workplace = str(mut["workplace_node_id"]).strip() if "workplace_node_id" in mut else str(cur.get("workplace_node_id") or "")
            new_home = str(mut["home_node_id"]).strip() if "home_node_id" in mut else str(cur.get("home_node_id") or "")
            new_hangout = str(mut["hangout_node_id"]).strip() if "hangout_node_id" in mut else str(cur.get("hangout_node_id") or "")
            new_staff = _pick_allowed(str(mut.get("staff_status") or "").strip().lower(), cur.get("staff_status"), ALLOWED_STAFF_STATUSES, "active")
            new_staff_day = _opt_int(mut.get("staff_status_day"))
            staff_day_val = new_staff_day if new_staff_day is not None else int(cur.get("staff_status_day") or 0)

            b_info = dict(cur.get("basic_info") or {})
            if "autonomy_override" in mut:
                ov = mut["autonomy_override"]
                if isinstance(ov, dict) and ov:
                    b_info["autonomy_override"] = dict(ov)
                else:
                    b_info.pop("autonomy_override", None)
            if mut.get("clear_autonomy_override"):
                b_info.pop("autonomy_override", None)
            if "pending_hangout_ping" in mut:
                ping = mut["pending_hangout_ping"]
                if isinstance(ping, dict) and ping:
                    b_info["pending_hangout_ping"] = dict(ping)
                else:
                    b_info.pop("pending_hangout_ping", None)
            if mut.get("clear_pending_hangout_ping"):
                b_info.pop("pending_hangout_ping", None)
            if isinstance(mut.get("basic_info_updates"), dict):
                b_info = merge_dict_safely(b_info, mut["basic_info_updates"])
                for uk, uv in mut["basic_info_updates"].items():
                    if uv in ("", None):
                        b_info.pop(uk, None)
            b_info = mirror_anchors_into_basic_info(
                b_info, new_workplace, new_home, new_hangout,
                str(cur.get("shift_profile") or "day"), bool(cur.get("residence_unlocked")),
            )

            cols_update: dict[str, Any] = {
                "workplace_node_id": new_workplace,
                "home_node_id": new_home,
                "hangout_node_id": new_hangout,
                "staff_status": new_staff,
                "staff_status_day": staff_day_val,
                "basic_info_json": json.dumps(b_info),
                "turn_snapshots_json": json.dumps(snaps),
                "turn_updated": t_num,
                "updated_at": now,
            }
            if mut.get("origin"):
                cols_update["origin"] = _pick_allowed(mut.get("origin"), cur.get("origin"), ALLOWED_ROSTER_ORIGINS, "venue_seed")
            _update_roster_columns(c, int(cur["id"]), cols_update)
            updated += 1

            def _sync_contact(c_info: dict[str, Any]) -> None:
                c_info["workplace_node_id"] = new_workplace
                c_info["home_node_id"] = new_home
                c_info["hangout_node_id"] = new_hangout
                if "autonomy_override" in b_info:
                    c_info["autonomy_override"] = json.loads(json.dumps(b_info["autonomy_override"]))
                else:
                    c_info.pop("autonomy_override", None)
                if "pending_hangout_ping" in b_info:
                    c_info["pending_hangout_ping"] = json.loads(json.dumps(b_info["pending_hangout_ping"]))
                else:
                    c_info.pop("pending_hangout_ping", None)

            _update_matching_contacts_basic_info(c, sid, cur["npc_id"], cur["name"], _sync_contact, now)
        return {"updated": updated, "created": created}

    with _conn_ctx(conn) as c:
        return _run(c)


def rollback_world_roster_after_turn(
    session_id: int, turn_number: int, conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    """Rolls back `world_roster` mutations, future-created rows, and promoted `contacts` strictly after `turn_number`."""
    if not session_id:
        return {"roster_deleted": 0, "roster_restored": 0, "promoted_contacts_reverted": 0}
    sid, t_num, now = int(session_id), int(turn_number), time.time()

    def _run(c: sqlite3.Connection) -> dict[str, int]:
        _ensure_world_roster_table(c)
        roster_deleted = int(c.execute("DELETE FROM world_roster WHERE session_id = ? AND turn_created > ?", (sid, t_num)).rowcount or 0)
        roster_restored, promoted_contacts_reverted = 0, 0
        restored_sync_by_key: dict[str, dict[str, Any]] = {}

        for r in c.execute("SELECT * FROM world_roster WHERE session_id = ?", (sid,)).fetchall():
            cur = _hydrate_roster_row(r)
            snaps = dict(cur.get("turn_snapshots") or {})
            future_turns = sorted(((ki, str(k)) for k in snaps for ki in (_opt_int(k),) if ki is not None and ki > t_num), key=lambda x: x[0])
            if not future_turns:
                continue
            snap = snaps.get(future_turns[0][1])
            for _, fk in future_turns:
                snaps.pop(fk, None)
            if isinstance(snap, dict):
                sync_payload = _restore_snapshot_row(c, cur, snap, snaps, t_num, now)
                roster_restored += 1
                restored_sync_by_key[cur["npc_id"].lower()] = restored_sync_by_key[cur["name"].lower()] = sync_payload
            else:
                _update_roster_columns(c, int(cur["id"]), {"turn_snapshots_json": json.dumps(snaps), "updated_at": now})

        try:
            c_rows = c.execute("SELECT id, npc_id, name, basic_info_json FROM contacts WHERE session_id = ?", (sid,)).fetchall()
        except sqlite3.OperationalError:
            c_rows = []
        for cr in c_rows:
            c_info = parse_json_dict(cr["basic_info_json"])
            prom_turn = _opt_int(c_info.get("promoted_from_roster_turn"))
            c_npc_low, c_name_low = str(cr["npc_id"] or "").strip().lower(), str(cr["name"] or "").strip().lower()
            if prom_turn is not None and prom_turn > t_num:
                c.execute("DELETE FROM contacts WHERE id = ?", (cr["id"],))
                promoted_contacts_reverted += 1
                _set_school_hydrated(c, sid, c_npc_low, c_name_low, 0)
                continue
            sync = restored_sync_by_key.get(c_npc_low) or restored_sync_by_key.get(c_name_low)
            if sync is not None:
                _resync_promoted_contact_row(c, cr, c_info, sync, now)

        return {"roster_deleted": roster_deleted, "roster_restored": roster_restored, "promoted_contacts_reverted": promoted_contacts_reverted}

    with _conn_ctx(conn) as c:
        return _run(c)


def batch_commit_opening_npcs(
    session_id: int,
    char_id: int,
    npcs_arg: list[Any],
    *,
    location: str = "",
    scenario_key: str = "fantasy",
    enemy_names: set[str] | None = None,
    open_party_names: set[str] | None = None,
    narrative: str = "",
    conn: sqlite3.Connection | None = None,
) -> int:
    """Atomically persists Turn-0 opening scene NPCs to world_roster, lorebook, and contacts."""
    if not session_id or not npcs_arg:
        return 0
    from .sessions import get_session_party_npcs
    from .social import get_contact
    from .world import upsert_lorebook_entity
    from mechanics.social.relationships import (
        is_contact_eligible,
        should_promote_roster_npc_to_contact,
    )

    sid = int(session_id)
    cid = int(char_id or 0)
    enemy_set = {str(e).strip().lower() for e in (enemy_names or set()) if e}
    party_set = {str(p).strip().lower() for p in (open_party_names or set()) if p}

    def _run(c: sqlite3.Connection) -> int:
        preloaded_sess = db.get_session(sid)
        party_npc_rows = get_session_party_npcs(sid) or []
        for p in party_npc_rows:
            if isinstance(p, dict) and p.get("name"):
                party_set.add(str(p["name"]).strip().lower())

        committed = 0
        for npc in npcs_arg:
            if isinstance(npc, dict):
                raw_n = npc.get("name") or npc.get("npc_name") or npc.get("character")
                n_name = str(raw_n).strip() if raw_n is not None else ""
            else:
                n_name = str(npc or "").strip()
            if not n_name or n_name.lower() in enemy_set:
                continue

            b_info = dict(npc.get("basic_info") or {}) if isinstance(npc, dict) else {}
            if isinstance(npc, dict):
                if "role" in npc and not b_info.get("role"):
                    b_info["role"] = npc.get("role", "")
                if "description" in npc and not b_info.get("description"):
                    b_info["description"] = npc.get("description", "")
            if not b_info.get("location"):
                b_info["location"] = location
            b_info["met_in_person"] = True

            existing_wr = get_world_roster_npc(sid, n_name, include_legacy_rosters=False, conn=c)
            roster_payload = {
                "name": n_name,
                "role": b_info.get("role", "") or (npc.get("role", "") if isinstance(npc, dict) else ""),
                "gender": npc.get("gender", "") if isinstance(npc, dict) else "",
                "race": npc.get("race", "") if isinstance(npc, dict) else "",
                "traits": (npc.get("traits") or []) if isinstance(npc, dict) else [],
                "appearance": (npc.get("appearance") or {}) if isinstance(npc, dict) else {},
                "origin": (existing_wr.get("origin") if existing_wr else None) or (npc.get("origin") if isinstance(npc, dict) and npc.get("origin") else "venue_seed"),
                "tier_status": (existing_wr.get("tier_status") if existing_wr else "acquaintance"),
                "met_in_person": True,
                "basic_info": b_info,
            }
            upsert_world_roster_npc(sid, roster_payload, turn_number=0, conn=c)

            m_val = npc.get("mannerisms", "") if isinstance(npc, dict) else ""
            if not m_val and isinstance(b_info, dict):
                m_val = b_info.get("mannerisms", "")
            upsert_lorebook_entity(
                session_id=sid,
                entity_type="person",
                name=n_name,
                description=b_info.get("description", "") or (npc.get("description", "") if isinstance(npc, dict) else ""),
                traits=npc.get("traits") if isinstance(npc, dict) else [],
                mannerisms=m_val,
                race=npc.get("race", "") if isinstance(npc, dict) else "",
                appearance=npc.get("appearance", {}) if isinstance(npc, dict) else {},
                gender=npc.get("gender", "") if isinstance(npc, dict) else "",
            )

            existing_c = get_contact(sid, n_name, cid)
            hh_role = str(
                (existing_c.get("household_role") if existing_c else "")
                or (npc.get("household_role") if isinstance(npc, dict) else "")
                or ""
            ).strip().lower()
            is_family = bool(
                hh_role in ("father", "mother", "parent", "brother", "sister", "sibling", "twin", "spouse", "husband", "wife")
                or b_info.get("is_adult_family")
                or b_info.get("cohabiting_family") is True
                or (existing_c and ((existing_c.get("basic_info") or {}).get("is_adult_family") or (existing_c.get("basic_info") or {}).get("cohabiting_family") is True))
                or (existing_wr and str(existing_wr.get("origin") or "").lower() == "household")
            )
            in_party = n_name.lower() in party_set
            eligible = is_family or in_party or is_contact_eligible(
                name=npc if isinstance(npc, dict) else n_name,
                role=b_info.get("role", ""),
                description=b_info.get("description", ""),
                scenario=scenario_key,
                session_id=sid,
                preloaded_session=preloaded_sess,
                skip_session_lookup=preloaded_sess is None,
            )
            if eligible:
                qualifies, promo_reason = should_promote_roster_npc_to_contact(
                    npc if isinstance(npc, dict) else {"name": n_name, "basic_info": b_info},
                    affinity=int((existing_c or {}).get("relationship_score") or (existing_wr or {}).get("affinity_score") or 0),
                    in_party=in_party,
                    is_family=is_family,
                    has_quest_link=bool(b_info.get("has_quest_link")),
                    scenario=scenario_key,
                    session_id=sid,
                )
                if qualifies:
                    promote_world_roster_to_contact(
                        sid,
                        cid,
                        n_name,
                        promo_reason or "opening_scene",
                        has_contact_info=bool(is_family or in_party or b_info.get("exchanged_contact") or b_info.get("added_via_peerpulse")),
                        turn_number=0,
                        narrative_text=narrative,
                        scenario=scenario_key,
                    )
            committed += 1
        return committed

    if conn is not None:
        from .core.connection import _resolve_db_path, _uow_conn_var, _uow_db_path_var, is_in_readonly_uow

        if is_in_readonly_uow():
            raise RuntimeError("Cannot call batch_commit_opening_npcs inside ReadUnitOfWork")
        if _uow_conn_var.get() is not conn:
            c_tok = _uow_conn_var.set(conn)
            p_tok = _uow_db_path_var.set(_resolve_db_path())
            try:
                return _run(conn)
            finally:
                _uow_db_path_var.reset(p_tok)
                _uow_conn_var.reset(c_tok)
        return _run(conn)
    with UnitOfWork() as uow_conn:
        return _run(uow_conn)
