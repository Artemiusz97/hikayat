from __future__ import annotations

"""
Normalized SQLite Persistence for Epistemic Asymmetry Matrix (`epistemic_facts` & `epistemic_knowledge`).

Implements:
- Natural-key `(session_id, fact_key)` join between facts and per-holder knowledge rows
  so multi-witness containment (`containment_state`) and conflicting per-holder alibis
  (`alibi_claim`, `alibi_witness_key`) never clobber each other (`D-1`, `D-2`).
- Bounded 10-turn `_turn_snapshots` inside `metadata_json` on both tables for lossless
  rollback of in-place mutations (`D-3`).
- Proof-artifact confidence transitions (`clue:<id>`, `inv:<id>`, `photo:<inv_id>`,
  `dm:<npc>:<turn>`) via `downgrade_or_upgrade_proof_ref` (`B10`).
- Strict server-side Fog-of-War summary (`build_player_fog_of_war_summary`, `B7`) that
  never serializes `player_aware == 0` gossip hops.
"""

from contextlib import nullcontext
import json
import sqlite3
import time
from typing import Any, Literal, Mapping, Sequence

from .core import UnitOfWork, get_conn

MAX_TURN_SNAPSHOTS = 10

ALLOWED_FACT_CATEGORIES: frozenset[str] = frozenset(
    {"affair", "crime", "faction_breach", "npc_secret", "identity", "alibi_lie", "anomaly", "secret"}
)
ALLOWED_FACT_STATUSES: frozenset[str] = frozenset({"active", "resolved", "decayed", "exposed_public"})
ALLOWED_CONFIDENCES: frozenset[str] = frozenset({"rumor", "firsthand", "hard_proof"})
ALLOWED_CONTAINMENT_STATES: frozenset[str] = frozenset(
    {"spotted_window", "hushed", "wiped", "incapacitated", "co_conspirator", "active", "decayed"}
)

EPISTEMIC_V55_DDL: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS epistemic_facts (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id              INTEGER NOT NULL,
    fact_key                TEXT NOT NULL,
    category                TEXT NOT NULL DEFAULT 'secret',
    culprit_actor_key       TEXT NOT NULL DEFAULT 'player',
    subject_actor_key       TEXT NOT NULL DEFAULT '',
    location_node_id        TEXT NOT NULL DEFAULT '',
    summary                 TEXT NOT NULL DEFAULT '',
    severity                INTEGER NOT NULL DEFAULT 1,
    proof_artifact_ref      TEXT NOT NULL DEFAULT '',
    heat_score              INTEGER NOT NULL DEFAULT 50,
    decay_day_last_ticked   INTEGER NOT NULL DEFAULT 0,
    status                  TEXT NOT NULL DEFAULT 'active',
    metadata_json           TEXT NOT NULL DEFAULT '{}',
    turn_created            INTEGER NOT NULL DEFAULT 0,
    turn_updated            INTEGER NOT NULL DEFAULT 0,
    created_at              REAL NOT NULL,
    updated_at              REAL NOT NULL,
    UNIQUE(session_id, fact_key)
)""",
    "CREATE INDEX IF NOT EXISTS idx_ep_facts_session_status ON epistemic_facts(session_id, status)",
    """CREATE TABLE IF NOT EXISTS epistemic_knowledge (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id              INTEGER NOT NULL,
    fact_key                TEXT NOT NULL,
    holder_actor_key        TEXT NOT NULL,
    confidence              TEXT NOT NULL DEFAULT 'rumor',
    containment_state       TEXT NOT NULL DEFAULT 'active',
    source_actor_key        TEXT NOT NULL DEFAULT '',
    acquisition_channel     TEXT NOT NULL DEFAULT 'witness',
    hop_count               INTEGER NOT NULL DEFAULT 0,
    player_aware            INTEGER NOT NULL DEFAULT 0,
    alibi_claim             TEXT NOT NULL DEFAULT '',
    alibi_witness_key       TEXT NOT NULL DEFAULT '',
    is_alibi_busted         INTEGER NOT NULL DEFAULT 0,
    metadata_json           TEXT NOT NULL DEFAULT '{}',
    turn_acquired           INTEGER NOT NULL DEFAULT 0,
    turn_updated            INTEGER NOT NULL DEFAULT 0,
    created_at              REAL NOT NULL,
    updated_at              REAL NOT NULL,
    UNIQUE(session_id, fact_key, holder_actor_key)
)""",
    "CREATE INDEX IF NOT EXISTS idx_ep_know_session_holder ON epistemic_knowledge(session_id, holder_actor_key)",
    "CREATE INDEX IF NOT EXISTS idx_ep_know_session_fact ON epistemic_knowledge(session_id, fact_key)",
)


def _conn_ctx(conn: sqlite3.Connection | None):
    return nullcontext(conn) if conn is not None else get_conn()


def _ensure_epistemic_tables(conn: sqlite3.Connection) -> None:
    """Self-healing DDL guard for isolated unit tests that bypass full migrations."""
    def _check(c: sqlite3.Connection) -> None:
        has_facts = c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='epistemic_facts' LIMIT 1"
        ).fetchone()
        has_know = c.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='epistemic_knowledge' LIMIT 1"
        ).fetchone()
        if has_facts and has_know:
            return
        for sql in EPISTEMIC_V55_DDL:
            c.execute(sql)

    from .core import ensure_table_group_once
    ensure_table_group_once(conn, "epistemic_v55", _check)


def _opt_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


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


def _clamp_int(val: Any, low: int, high: int, default: int) -> int:
    try:
        n = int(val)
    except (TypeError, ValueError):
        n = default
    return max(low, min(high, n))


def _hydrate_fact_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    d = dict(row)
    d["session_id"] = int(d.get("session_id") or 0)
    d["severity"] = _clamp_int(d.get("severity"), 1, 3, 1)
    d["heat_score"] = _clamp_int(d.get("heat_score"), 0, 100, 50)
    for k in ("decay_day_last_ticked", "turn_created", "turn_updated"):
        d[k] = int(d.get(k) or 0)
    d["metadata"] = _parse_json_dict(d.get("metadata_json"))
    return d


def _hydrate_knowledge_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    d = dict(row)
    d["session_id"] = int(d.get("session_id") or 0)
    for k in ("hop_count", "player_aware", "is_alibi_busted", "turn_acquired", "turn_updated"):
        d[k] = int(d.get(k) or 0)
    d["metadata"] = _parse_json_dict(d.get("metadata_json"))
    return d


def _capture_turn_snapshot(
    meta: dict[str, Any],
    snap_fields: dict[str, Any],
    turn_number: int,
) -> dict[str, Any]:
    out_meta = dict(meta) if isinstance(meta, dict) else {}
    snaps = out_meta.get("_turn_snapshots")
    snaps_dict = dict(snaps) if isinstance(snaps, dict) else {}
    t_key = str(int(turn_number))
    if t_key not in snaps_dict:
        extra_meta = {k: v for k, v in out_meta.items() if k != "_turn_snapshots"}
        entry = dict(snap_fields)
        entry["extra_metadata"] = json.loads(json.dumps(extra_meta))
        snaps_dict[t_key] = entry
    if len(snaps_dict) > MAX_TURN_SNAPSHOTS:
        sortable = [(-1 if _opt_int(k) is None else int(k), str(k)) for k in snaps_dict]
        sortable.sort(key=lambda item: item[0])
        for _, drop_k in sortable[: len(snaps_dict) - MAX_TURN_SNAPSHOTS]:
            snaps_dict.pop(drop_k, None)
    out_meta["_turn_snapshots"] = snaps_dict
    return out_meta


def _fact_snapshot_payload(cur: dict[str, Any]) -> dict[str, Any]:
    return {
        "category": str(cur.get("category") or "secret"),
        "culprit_actor_key": str(cur.get("culprit_actor_key") or "player"),
        "subject_actor_key": str(cur.get("subject_actor_key") or ""),
        "location_node_id": str(cur.get("location_node_id") or ""),
        "summary": str(cur.get("summary") or ""),
        "severity": _clamp_int(cur.get("severity"), 1, 3, 1),
        "proof_artifact_ref": str(cur.get("proof_artifact_ref") or ""),
        "heat_score": _clamp_int(cur.get("heat_score"), 0, 100, 50),
        "decay_day_last_ticked": int(cur.get("decay_day_last_ticked") or 0),
        "status": str(cur.get("status") or "active"),
        "turn_updated": int(cur.get("turn_updated") or 0),
    }


def _knowledge_snapshot_payload(cur: dict[str, Any]) -> dict[str, Any]:
    return {
        "confidence": str(cur.get("confidence") or "rumor"),
        "containment_state": str(cur.get("containment_state") or "active"),
        "source_actor_key": str(cur.get("source_actor_key") or ""),
        "acquisition_channel": str(cur.get("acquisition_channel") or "witness"),
        "hop_count": int(cur.get("hop_count") or 0),
        "player_aware": int(bool(cur.get("player_aware"))),
        "alibi_claim": str(cur.get("alibi_claim") or ""),
        "alibi_witness_key": str(cur.get("alibi_witness_key") or ""),
        "is_alibi_busted": int(bool(cur.get("is_alibi_busted"))),
        "turn_updated": int(cur.get("turn_updated") or 0),
    }


def _merge_metadata(existing_meta: dict[str, Any], patch: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(existing_meta or {})
    if isinstance(patch, dict):
        for k, v in patch.items():
            if k != "_turn_snapshots":
                merged[k] = v
    return merged


def upsert_epistemic_fact(
    session_id: int,
    fact_key: str,
    *,
    category: str | None = None,
    culprit_actor_key: str | None = None,
    subject_actor_key: str | None = None,
    location_node_id: str | None = None,
    summary: str | None = None,
    severity: int | None = None,
    proof_artifact_ref: str | None = None,
    heat_score: int | None = None,
    decay_day_last_ticked: int | None = None,
    status: str | None = None,
    turn: int = 0,
    metadata: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Inserts or updates an epistemic fact row, snapshotting pre-mutation state for turn rollback."""
    sid = int(session_id or 0)
    fkey = str(fact_key or "").strip()
    if not sid or not fkey:
        return {}
    t_num, now = int(turn), time.time()

    def _run(c: sqlite3.Connection) -> dict[str, Any]:
        _ensure_epistemic_tables(c)
        row = c.execute(
            "SELECT * FROM epistemic_facts WHERE session_id = ? AND fact_key = ? LIMIT 1",
            (sid, fkey),
        ).fetchone()
        if row is not None:
            cur = _hydrate_fact_row(row)
            meta = _capture_turn_snapshot(cur.get("metadata") or {}, _fact_snapshot_payload(cur), t_num)
            meta = _merge_metadata(meta, metadata)
            cat_val = str(category if category is not None else cur["category"]).strip() or "secret"
            if cat_val not in ALLOWED_FACT_CATEGORIES:
                cat_val = cur["category"] if cur["category"] in ALLOWED_FACT_CATEGORIES else "secret"
            st_val = str(status if status is not None else cur["status"]).strip() or "active"
            if st_val not in ALLOWED_FACT_STATUSES:
                st_val = cur["status"] if cur["status"] in ALLOWED_FACT_STATUSES else "active"
            new_cols = {
                "category": cat_val,
                "culprit_actor_key": str(culprit_actor_key if culprit_actor_key is not None else cur["culprit_actor_key"]).strip() or "player",
                "subject_actor_key": str(subject_actor_key if subject_actor_key is not None else cur["subject_actor_key"]).strip(),
                "location_node_id": str(location_node_id if location_node_id is not None else cur["location_node_id"]).strip(),
                "summary": str(summary if summary is not None else cur["summary"]).strip(),
                "severity": _clamp_int(severity if severity is not None else cur["severity"], 1, 3, 1),
                "proof_artifact_ref": str(proof_artifact_ref if proof_artifact_ref is not None else cur["proof_artifact_ref"]).strip(),
                "heat_score": _clamp_int(heat_score if heat_score is not None else cur["heat_score"], 0, 100, 50),
                "decay_day_last_ticked": int(decay_day_last_ticked if decay_day_last_ticked is not None else cur["decay_day_last_ticked"]),
                "status": st_val,
                "metadata_json": json.dumps(meta),
                "turn_updated": t_num,
                "updated_at": now,
            }
            set_sql = ", ".join(f"{k} = ?" for k in new_cols)
            c.execute(f"UPDATE epistemic_facts SET {set_sql} WHERE id = ?", (*new_cols.values(), cur["id"]))
            out_row = c.execute("SELECT * FROM epistemic_facts WHERE id = ?", (cur["id"],)).fetchone()
            return _hydrate_fact_row(out_row) if out_row is not None else {}

        cat_val = str(category or "secret").strip()
        if cat_val not in ALLOWED_FACT_CATEGORIES:
            cat_val = "secret"
        st_val = str(status or "active").strip()
        if st_val not in ALLOWED_FACT_STATUSES:
            st_val = "active"
        meta = _merge_metadata({}, metadata)
        cur_ins = c.execute(
            """INSERT INTO epistemic_facts (
                session_id, fact_key, category, culprit_actor_key, subject_actor_key,
                location_node_id, summary, severity, proof_artifact_ref, heat_score,
                decay_day_last_ticked, status, metadata_json, turn_created, turn_updated,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sid, fkey, cat_val,
                str(culprit_actor_key or "player").strip() or "player",
                str(subject_actor_key or "").strip(),
                str(location_node_id or "").strip(),
                str(summary or "").strip(),
                _clamp_int(severity, 1, 3, 1),
                str(proof_artifact_ref or "").strip(),
                _clamp_int(heat_score, 0, 100, 50),
                int(decay_day_last_ticked or 0),
                st_val,
                json.dumps(meta),
                t_num,
                t_num,
                now,
                now,
            ),
        )
        out_row = c.execute("SELECT * FROM epistemic_facts WHERE id = ?", (cur_ins.lastrowid,)).fetchone()
        return _hydrate_fact_row(out_row) if out_row is not None else {}

    with _conn_ctx(conn) as c:
        return _run(c)


def upsert_epistemic_knowledge(
    session_id: int,
    fact_key: str,
    holder_actor_key: str,
    *,
    confidence: str | None = None,
    containment_state: str | None = None,
    source_actor_key: str | None = None,
    acquisition_channel: str | None = None,
    hop_count: int | None = None,
    player_aware: int | None = None,
    alibi_claim: str | None = None,
    alibi_witness_key: str | None = None,
    is_alibi_busted: int | None = None,
    metadata: dict[str, Any] | None = None,
    turn: int = 0,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Inserts or updates a per-holder epistemic knowledge row with turn-snapshot capture."""
    sid = int(session_id or 0)
    fkey = str(fact_key or "").strip()
    hkey = str(holder_actor_key or "").strip().lower()
    if not sid or not fkey or not hkey:
        return {}
    t_num, now = int(turn), time.time()

    def _run(c: sqlite3.Connection) -> dict[str, Any]:
        _ensure_epistemic_tables(c)
        row = c.execute(
            """SELECT * FROM epistemic_knowledge
               WHERE session_id = ? AND fact_key = ? AND holder_actor_key = ? LIMIT 1""",
            (sid, fkey, hkey),
        ).fetchone()
        if row is not None:
            cur = _hydrate_knowledge_row(row)
            meta = _capture_turn_snapshot(cur.get("metadata") or {}, _knowledge_snapshot_payload(cur), t_num)
            meta = _merge_metadata(meta, metadata)
            conf_val = str(confidence if confidence is not None else cur["confidence"]).strip()
            if conf_val not in ALLOWED_CONFIDENCES:
                conf_val = cur["confidence"] if cur["confidence"] in ALLOWED_CONFIDENCES else "rumor"
            cont_val = str(containment_state if containment_state is not None else cur["containment_state"]).strip()
            if cont_val not in ALLOWED_CONTAINMENT_STATES:
                cont_val = cur["containment_state"] if cur["containment_state"] in ALLOWED_CONTAINMENT_STATES else "active"
            new_cols = {
                "confidence": conf_val,
                "containment_state": cont_val,
                "source_actor_key": str(source_actor_key if source_actor_key is not None else cur["source_actor_key"]).strip(),
                "acquisition_channel": str(acquisition_channel if acquisition_channel is not None else cur["acquisition_channel"]).strip() or "witness",
                "hop_count": max(0, int(hop_count if hop_count is not None else cur["hop_count"])),
                "player_aware": int(bool(player_aware if player_aware is not None else cur["player_aware"])),
                "alibi_claim": str(alibi_claim if alibi_claim is not None else cur["alibi_claim"]).strip(),
                "alibi_witness_key": str(alibi_witness_key if alibi_witness_key is not None else cur["alibi_witness_key"]).strip().lower(),
                "is_alibi_busted": int(bool(is_alibi_busted if is_alibi_busted is not None else cur["is_alibi_busted"])),
                "metadata_json": json.dumps(meta),
                "turn_updated": t_num,
                "updated_at": now,
            }
            set_sql = ", ".join(f"{k} = ?" for k in new_cols)
            c.execute(f"UPDATE epistemic_knowledge SET {set_sql} WHERE id = ?", (*new_cols.values(), cur["id"]))
            out_row = c.execute("SELECT * FROM epistemic_knowledge WHERE id = ?", (cur["id"],)).fetchone()
            return _hydrate_knowledge_row(out_row) if out_row is not None else {}

        conf_val = str(confidence or "rumor").strip()
        if conf_val not in ALLOWED_CONFIDENCES:
            conf_val = "rumor"
        cont_val = str(containment_state or "active").strip()
        if cont_val not in ALLOWED_CONTAINMENT_STATES:
            cont_val = "active"
        meta = _merge_metadata({}, metadata)
        cur_ins = c.execute(
            """INSERT INTO epistemic_knowledge (
                session_id, fact_key, holder_actor_key, confidence, containment_state,
                source_actor_key, acquisition_channel, hop_count, player_aware,
                alibi_claim, alibi_witness_key, is_alibi_busted, metadata_json,
                turn_acquired, turn_updated, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sid, fkey, hkey, conf_val, cont_val,
                str(source_actor_key or "").strip(),
                str(acquisition_channel or "witness").strip() or "witness",
                max(0, int(hop_count or 0)),
                int(bool(player_aware)),
                str(alibi_claim or "").strip(),
                str(alibi_witness_key or "").strip().lower(),
                int(bool(is_alibi_busted)),
                json.dumps(meta),
                t_num,
                t_num,
                now,
                now,
            ),
        )
        out_row = c.execute("SELECT * FROM epistemic_knowledge WHERE id = ?", (cur_ins.lastrowid,)).fetchone()
        return _hydrate_knowledge_row(out_row) if out_row is not None else {}

    with _conn_ctx(conn) as c:
        return _run(c)


def get_epistemic_fact(
    session_id: int,
    fact_key: str,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    sid = int(session_id or 0)
    fkey = str(fact_key or "").strip()
    if not sid or not fkey:
        return None
    with _conn_ctx(conn) as c:
        _ensure_epistemic_tables(c)
        row = c.execute(
            "SELECT * FROM epistemic_facts WHERE session_id = ? AND fact_key = ? LIMIT 1",
            (sid, fkey),
        ).fetchone()
        return _hydrate_fact_row(row) if row is not None else None


def get_epistemic_knowledge_rows(
    session_id: int,
    *,
    fact_key: str = "",
    holder_actor_key: str = "",
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    sid = int(session_id or 0)
    if not sid:
        return []
    clauses, params = ["session_id = ?"], [sid]
    if fact_key:
        clauses.append("fact_key = ?")
        params.append(str(fact_key).strip())
    if holder_actor_key:
        clauses.append("holder_actor_key = ?")
        params.append(str(holder_actor_key).strip().lower())
    with _conn_ctx(conn) as c:
        _ensure_epistemic_tables(c)
        rows = c.execute(
            f"SELECT * FROM epistemic_knowledge WHERE {' AND '.join(clauses)} ORDER BY id ASC",
            params,
        ).fetchall()
        return [_hydrate_knowledge_row(r) for r in rows]


def preload_epistemic_matrix(
    session_id: int,
    actor_keys: Sequence[str] | None = None,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Batch-loads all epistemic facts and holder knowledge for a session in <= 2 indexed queries."""
    sid = int(session_id or 0)
    empty = {"facts_by_key": {}, "knowledge_rows": [], "by_holder": {}, "by_fact": {}}
    if not sid:
        return empty
    actor_filter = {str(a).strip().lower() for a in actor_keys if str(a or "").strip()} if actor_keys is not None else None

    def _run(c: sqlite3.Connection) -> dict[str, Any]:
        _ensure_epistemic_tables(c)
        fact_rows = c.execute(
            "SELECT * FROM epistemic_facts WHERE session_id = ? ORDER BY id ASC",
            (sid,),
        ).fetchall()
        know_rows = c.execute(
            "SELECT * FROM epistemic_knowledge WHERE session_id = ? ORDER BY id ASC",
            (sid,),
        ).fetchall()
        facts_by_key = {str(r["fact_key"]): _hydrate_fact_row(r) for r in fact_rows}
        knowledge_rows: list[dict[str, Any]] = []
        by_holder: dict[str, list[dict[str, Any]]] = {}
        by_fact: dict[str, dict[str, dict[str, Any]]] = {}
        for kr in know_rows:
            k = _hydrate_knowledge_row(kr)
            knowledge_rows.append(k)
            hk = str(k["holder_actor_key"])
            fk = str(k["fact_key"])
            if actor_filter is None or hk in actor_filter or hk == "player":
                by_holder.setdefault(hk, []).append(k)
            by_fact.setdefault(fk, {})[hk] = k
        return {
            "facts_by_key": facts_by_key,
            "knowledge_rows": knowledge_rows,
            "by_holder": by_holder,
            "by_fact": by_fact,
        }

    with _conn_ctx(conn) as c:
        return _run(c)


def downgrade_or_upgrade_proof_ref(
    session_id: int,
    proof_artifact_ref: str,
    *,
    action: Literal["present", "destroy_or_steal"],
    target_holder_key: str = "",
    turn: int = 0,
    conn: sqlite3.Connection | None = None,
) -> list[str]:
    """Transitions epistemic confidence when proof (`clue:`, `inv:`, `photo:`, `dm:`) is presented or destroyed/stolen (`B10`)."""
    sid = int(session_id or 0)
    pref = str(proof_artifact_ref or "").strip()
    hkey = str(target_holder_key or "").strip().lower()
    t_num, now = int(turn), time.time()
    if not sid or not pref:
        return []

    def _run(c: sqlite3.Connection) -> list[str]:
        _ensure_epistemic_tables(c)
        fact_rows = c.execute(
            "SELECT * FROM epistemic_facts WHERE session_id = ? AND proof_artifact_ref = ? ORDER BY id ASC",
            (sid, pref),
        ).fetchall()
        affected: list[str] = []
        for fr in fact_rows:
            cur_f = _hydrate_fact_row(fr)
            fkey = cur_f["fact_key"]
            affected.append(fkey)
            if action == "present":
                if hkey:
                    upsert_epistemic_knowledge(
                        sid, fkey, hkey,
                        confidence="hard_proof",
                        acquisition_channel="proof_shown",
                        player_aware=1,
                        turn=t_num,
                        conn=c,
                    )
                else:
                    holders = c.execute(
                        "SELECT holder_actor_key FROM epistemic_knowledge WHERE session_id = ? AND fact_key = ?",
                        (sid, fkey),
                    ).fetchall()
                    for hr in holders:
                        upsert_epistemic_knowledge(
                            sid, fkey, hr["holder_actor_key"],
                            confidence="hard_proof",
                            acquisition_channel="proof_shown",
                            turn=t_num,
                            conn=c,
                        )
            elif action == "destroy_or_steal":
                clauses = ["session_id = ?", "fact_key = ?", "confidence = 'hard_proof'"]
                params: list[Any] = [sid, fkey]
                if hkey:
                    clauses.append("holder_actor_key = ?")
                    params.append(hkey)
                holders = c.execute(
                    f"SELECT holder_actor_key FROM epistemic_knowledge WHERE {' AND '.join(clauses)}",
                    params,
                ).fetchall()
                for hr in holders:
                    upsert_epistemic_knowledge(
                        sid, fkey, hr["holder_actor_key"],
                        confidence="firsthand",
                        turn=t_num,
                        conn=c,
                    )
                rem_hard = int(
                    c.execute(
                        "SELECT COUNT(*) FROM epistemic_knowledge WHERE session_id = ? AND fact_key = ? AND confidence = 'hard_proof'",
                        (sid, fkey),
                    ).fetchone()[0]
                    or 0
                )
                if not hkey or rem_hard == 0:
                    meta = _capture_turn_snapshot(cur_f.get("metadata") or {}, _fact_snapshot_payload(cur_f), t_num)
                    c.execute(
                        """UPDATE epistemic_facts
                           SET proof_artifact_ref = '', metadata_json = ?, turn_updated = ?, updated_at = ?
                           WHERE id = ?""",
                        (json.dumps(meta), t_num, now, cur_f["id"]),
                    )
        return affected

    with _conn_ctx(conn) as c:
        return _run(c)


def _extract_future_snapshot(meta: dict[str, Any], t_num: int) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    snaps = meta.get("_turn_snapshots")
    if not isinstance(snaps, dict) or not snaps:
        return None, meta
    future: list[tuple[int, str]] = []
    for k in snaps:
        ki = _opt_int(k)
        if ki is not None and ki > t_num:
            future.append((ki, str(k)))
    if not future:
        return None, meta
    future.sort(key=lambda item: item[0])
    earliest_snap = snaps.get(future[0][1])
    new_snaps = dict(snaps)
    for _, fk in future:
        new_snaps.pop(fk, None)
    if isinstance(earliest_snap, dict):
        restored_meta = dict(earliest_snap.get("extra_metadata") or {})
        if new_snaps:
            restored_meta["_turn_snapshots"] = new_snaps
        return earliest_snap, restored_meta
    clean_meta = dict(meta)
    if new_snaps:
        clean_meta["_turn_snapshots"] = new_snaps
    else:
        clean_meta.pop("_turn_snapshots", None)
    return None, clean_meta


def rollback_epistemic_state_after_turn(
    session_id: int,
    t_num: int,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    """Rolls back newly created and in-place mutated epistemic facts/knowledge strictly after `t_num` (`D-3`)."""
    sid, target_turn, now = int(session_id or 0), int(t_num), time.time()
    if not sid:
        return {"facts_deleted": 0, "facts_restored": 0, "knowledge_deleted": 0, "knowledge_restored": 0}

    def _run(c: sqlite3.Connection) -> dict[str, int]:
        _ensure_epistemic_tables(c)
        k_del = int(
            c.execute("DELETE FROM epistemic_knowledge WHERE session_id = ? AND turn_acquired > ?", (sid, target_turn)).rowcount or 0
        )
        f_del = int(
            c.execute("DELETE FROM epistemic_facts WHERE session_id = ? AND turn_created > ?", (sid, target_turn)).rowcount or 0
        )
        f_rest, k_rest = 0, 0

        for fr in c.execute("SELECT * FROM epistemic_facts WHERE session_id = ?", (sid,)).fetchall():
            cur = _hydrate_fact_row(fr)
            snap, rest_meta = _extract_future_snapshot(cur.get("metadata") or {}, target_turn)
            if snap is None and rest_meta == (cur.get("metadata") or {}):
                continue
            if snap is not None:
                c.execute(
                    """UPDATE epistemic_facts
                       SET category = ?, culprit_actor_key = ?, subject_actor_key = ?,
                           location_node_id = ?, summary = ?, severity = ?, proof_artifact_ref = ?,
                           heat_score = ?, decay_day_last_ticked = ?, status = ?,
                           metadata_json = ?, turn_updated = ?, updated_at = ?
                       WHERE id = ?""",
                    (
                        str(snap.get("category") or cur["category"]),
                        str(snap.get("culprit_actor_key") or cur["culprit_actor_key"]),
                        str(snap.get("subject_actor_key", cur["subject_actor_key"]) or ""),
                        str(snap.get("location_node_id", cur["location_node_id"]) or ""),
                        str(snap.get("summary", cur["summary"]) or ""),
                        _clamp_int(snap.get("severity", cur["severity"]), 1, 3, 1),
                        str(snap.get("proof_artifact_ref", cur["proof_artifact_ref"]) or ""),
                        _clamp_int(snap.get("heat_score", cur["heat_score"]), 0, 100, 50),
                        int(snap.get("decay_day_last_ticked", cur["decay_day_last_ticked"]) or 0),
                        str(snap.get("status") or cur["status"]),
                        json.dumps(rest_meta),
                        min(int(snap.get("turn_updated", target_turn) or 0), target_turn),
                        now,
                        cur["id"],
                    ),
                )
                f_rest += 1
            else:
                c.execute(
                    "UPDATE epistemic_facts SET metadata_json = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(rest_meta), now, cur["id"]),
                )

        for kr in c.execute("SELECT * FROM epistemic_knowledge WHERE session_id = ?", (sid,)).fetchall():
            cur = _hydrate_knowledge_row(kr)
            snap, rest_meta = _extract_future_snapshot(cur.get("metadata") or {}, target_turn)
            if snap is None and rest_meta == (cur.get("metadata") or {}):
                continue
            if snap is not None:
                c.execute(
                    """UPDATE epistemic_knowledge
                       SET confidence = ?, containment_state = ?, source_actor_key = ?,
                           acquisition_channel = ?, hop_count = ?, player_aware = ?,
                           alibi_claim = ?, alibi_witness_key = ?, is_alibi_busted = ?,
                           metadata_json = ?, turn_updated = ?, updated_at = ?
                       WHERE id = ?""",
                    (
                        str(snap.get("confidence") or cur["confidence"]),
                        str(snap.get("containment_state") or cur["containment_state"]),
                        str(snap.get("source_actor_key", cur["source_actor_key"]) or ""),
                        str(snap.get("acquisition_channel") or cur["acquisition_channel"]),
                        int(snap.get("hop_count", cur["hop_count"]) or 0),
                        int(bool(snap.get("player_aware", cur["player_aware"]))),
                        str(snap.get("alibi_claim", cur["alibi_claim"]) or ""),
                        str(snap.get("alibi_witness_key", cur["alibi_witness_key"]) or ""),
                        int(bool(snap.get("is_alibi_busted", cur["is_alibi_busted"]))),
                        json.dumps(rest_meta),
                        min(int(snap.get("turn_updated", target_turn) or 0), target_turn),
                        now,
                        cur["id"],
                    ),
                )
                k_rest += 1
            else:
                c.execute(
                    "UPDATE epistemic_knowledge SET metadata_json = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(rest_meta), now, cur["id"]),
                )

        return {
            "facts_deleted": f_del,
            "facts_restored": f_rest,
            "knowledge_deleted": k_del,
            "knowledge_restored": k_rest,
        }

    with _conn_ctx(conn) as c:
        return _run(c)


def _compute_leak_risk(known_witnesses: list[dict[str, Any]], exposed_public: bool) -> str:
    if exposed_public:
        return "critical"
    if not known_witnesses:
        return "none"
    max_score = 0
    total_score = 0
    conf_bonus = {"rumor": 0, "firsthand": 10, "hard_proof": 20}
    for w in known_witnesses:
        st = str(w.get("containment_state") or "active")
        if st in ("wiped", "incapacitated", "decayed"):
            continue
        sev = _clamp_int(w.get("severity"), 1, 3, 1)
        heat = _clamp_int(w.get("heat_score"), 0, 100, 50)
        cb = conf_bonus.get(str(w.get("confidence") or "rumor"), 0)
        if st == "co_conspirator":
            score = 5
        elif st == "hushed":
            score = 8 + (heat // 10)
        elif st == "spotted_window":
            score = 28 + sev * 12 + (cb // 2)
        else:
            score = 25 + sev * 15 + cb + (heat // 5)
        max_score = max(max_score, score)
        total_score += score
    eff = max(max_score, min(100, total_score // 2 if len(known_witnesses) > 1 else max_score))
    if eff <= 0:
        return "low" if any(str(w.get("containment_state") or "") == "co_conspirator" for w in known_witnesses) else "none"
    if eff < 25:
        return "low"
    if eff < 50:
        return "moderate"
    if eff < 75:
        return "high"
    return "critical"


def build_player_fog_of_war_summary(
    session_id: int,
    matrix: Mapping[str, Any] | None = None,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """Builds strict player-visible Fog-of-War HUD data (`B7`), omitting all `player_aware == 0` hops."""
    if matrix is None:
        matrix = preload_epistemic_matrix(session_id, conn=conn)
    facts_by_key = dict(matrix.get("facts_by_key") or {})
    know_rows = list(matrix.get("knowledge_rows") or [])

    spotted_witnesses: list[dict[str, Any]] = []
    known_witnesses: list[dict[str, Any]] = []
    active_alibis: list[dict[str, Any]] = []
    held_npc_secrets: list[dict[str, Any]] = []
    exposed_public = False

    for kr in know_rows:
        fk = str(kr.get("fact_key") or "")
        fact = facts_by_key.get(fk)
        if not fact:
            continue
        fact_status = str(fact.get("status") or "active")
        if fact_status in ("decayed", "resolved"):
            continue
        culprit = str(fact.get("culprit_actor_key") or "player").lower()
        fact_cat = str(fact.get("category") or "").lower()
        is_player_deed = culprit in ("player", "unknown", "") and fact_cat != "npc_secret"
        holder = str(kr.get("holder_actor_key") or "").lower()
        p_aware = int(bool(kr.get("player_aware")))
        cont_state = str(kr.get("containment_state") or "active")

        if holder == "player" and not is_player_deed:
            held_npc_secrets.append(
                {
                    "fact_key": fk,
                    "category": str(fact.get("category") or "npc_secret"),
                    "subject_actor_key": str(fact.get("subject_actor_key") or culprit),
                    "culprit_actor_key": culprit,
                    "summary": str(fact.get("summary") or ""),
                    "confidence": str(kr.get("confidence") or "rumor"),
                    "severity": int(fact.get("severity") or 1),
                    "proof_artifact_ref": str(fact.get("proof_artifact_ref") or ""),
                    "status": fact_status,
                }
            )
            continue

        # Strict Fog-of-War gate: never serialize hidden `player_aware == 0` hops or NPCs
        if p_aware != 1 or holder == "player":
            continue

        if fact_status == "exposed_public" and is_player_deed:
            exposed_public = True

        if kr.get("alibi_claim"):
            active_alibis.append(
                {
                    "fact_key": fk,
                    "holder_actor_key": holder,
                    "alibi_claim": str(kr.get("alibi_claim") or ""),
                    "alibi_witness_key": str(kr.get("alibi_witness_key") or ""),
                    "is_busted": bool(kr.get("is_alibi_busted")),
                }
            )

        if is_player_deed and cont_state not in ("wiped", "decayed"):
            entry = {
                "fact_key": fk,
                "category": str(fact.get("category") or "secret"),
                "culprit_actor_key": culprit or "player",
                "holder_actor_key": holder,
                "confidence": str(kr.get("confidence") or "rumor"),
                "containment_state": cont_state,
                "acquisition_channel": str(kr.get("acquisition_channel") or "witness"),
                "severity": int(fact.get("severity") or 1),
                "heat_score": int(fact.get("heat_score") or 50),
                "summary": str(fact.get("summary") or ""),
                "proof_artifact_ref": str(fact.get("proof_artifact_ref") or ""),
            }
            known_witnesses.append(entry)
            if cont_state == "spotted_window":
                spotted_witnesses.append(entry)

    leak_risk = _compute_leak_risk(known_witnesses, exposed_public=exposed_public)
    return {
        "leak_risk": leak_risk,
        "spotted_witnesses": spotted_witnesses,
        "known_witnesses": known_witnesses,
        "active_alibis": active_alibis,
        "held_npc_secrets": held_npc_secrets,
        "counts": {
            "spotted": len(spotted_witnesses),
            "witnesses": len(known_witnesses),
            "alibis": len(active_alibis),
            "secrets": len(held_npc_secrets),
        },
    }
