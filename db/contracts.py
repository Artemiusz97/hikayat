from __future__ import annotations
"""
Normalized SQLite Persistence for Entity Contracts, Grudge Nemeses, Snapshots & Compendium (Layer 3).

Tables (Migration v52):
- `session_entity_contracts`: Active/severed/spurned player & Special Agent pacts per session.
- `session_contract_grudges`: Violently severed Stage 2 Grudge Nemesis & Soul Scar tracking.
- `session_contract_turn_snapshots`: Turn-indexed contract & grudge snapshots for rollback & retry idempotency.
- `user_patron_compendium`: Account-wide Patron mastery & Folklore Encyclopedia badge tracking.
"""

import json
import logging
import sqlite3
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

import db
from .core import UnitOfWork, get_conn

log = logging.getLogger(__name__)

ENTITY_CONTRACTS_V52_DDL: Tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS session_entity_contracts (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id          INTEGER NOT NULL,
        character_id        INTEGER DEFAULT NULL,
        contract_key        TEXT NOT NULL,
        patron_id           TEXT NOT NULL,
        source_pool         TEXT NOT NULL DEFAULT 'bespoke',
        codex_id            TEXT NOT NULL DEFAULT '',
        entity_name         TEXT NOT NULL,
        element             TEXT NOT NULL DEFAULT 'aether',
        synergy_stat        TEXT NOT NULL DEFAULT 'INT',
        holder_type         TEXT NOT NULL DEFAULT 'player',
        holder_id           TEXT NOT NULL,
        status              TEXT NOT NULL DEFAULT 'active',
        tier                INTEGER NOT NULL DEFAULT 1,
        resonance_xp        INTEGER NOT NULL DEFAULT 0,
        appraisal_state     TEXT NOT NULL DEFAULT 'neutral',
        breach_stage        INTEGER NOT NULL DEFAULT 0,
        unpaid_blood_debt   INTEGER NOT NULL DEFAULT 0,
        bound_gear_item_id  INTEGER DEFAULT NULL,
        bound_gear_slot     TEXT NOT NULL DEFAULT '',
        taboo_id            TEXT NOT NULL DEFAULT '',
        tithe_schedule_json TEXT NOT NULL DEFAULT '{}',
        stat_locks_json     TEXT NOT NULL DEFAULT '{}',
        metadata_json       TEXT NOT NULL DEFAULT '{}',
        turn_signed         INTEGER NOT NULL DEFAULT 1,
        turn_updated        INTEGER NOT NULL DEFAULT 1,
        created_at          REAL NOT NULL,
        updated_at          REAL NOT NULL,
        UNIQUE(session_id, contract_key)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_entity_contracts_sess_holder ON session_entity_contracts(session_id, holder_type, holder_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_entity_contracts_sess_patron ON session_entity_contracts(session_id, patron_id, tier, status)",
    "CREATE INDEX IF NOT EXISTS idx_entity_contracts_char ON session_entity_contracts(character_id, status)",
    """CREATE TABLE IF NOT EXISTS session_contract_grudges (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id          INTEGER NOT NULL,
        character_id        INTEGER DEFAULT NULL,
        grudge_key          TEXT NOT NULL,
        patron_id           TEXT NOT NULL,
        entity_name         TEXT NOT NULL,
        holder_id           TEXT NOT NULL,
        status              TEXT NOT NULL DEFAULT 'active',
        soul_scar_active    INTEGER NOT NULL DEFAULT 1,
        nemesis_spawned     INTEGER NOT NULL DEFAULT 0,
        metadata_json       TEXT NOT NULL DEFAULT '{}',
        severance_turn      INTEGER NOT NULL DEFAULT 1,
        resolved_turn       INTEGER DEFAULT NULL,
        created_at          REAL NOT NULL,
        updated_at          REAL NOT NULL,
        UNIQUE(session_id, grudge_key)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_contract_grudges_sess_holder ON session_contract_grudges(session_id, holder_id, status)",
    """CREATE TABLE IF NOT EXISTS session_contract_turn_snapshots (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id          INTEGER NOT NULL,
        turn_number         INTEGER NOT NULL,
        contracts_json      TEXT NOT NULL DEFAULT '[]',
        grudges_json        TEXT NOT NULL DEFAULT '[]',
        created_at          REAL NOT NULL,
        UNIQUE(session_id, turn_number)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_contract_snaps_sess_turn ON session_contract_turn_snapshots(session_id, turn_number)",
    """CREATE TABLE IF NOT EXISTS user_patron_compendium (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id                 INTEGER NOT NULL,
        patron_id               TEXT NOT NULL,
        source_pool             TEXT NOT NULL DEFAULT 'bespoke',
        codex_id                TEXT NOT NULL DEFAULT '',
        entity_name             TEXT NOT NULL DEFAULT '',
        max_tier_reached        INTEGER NOT NULL DEFAULT 1,
        times_signed            INTEGER NOT NULL DEFAULT 1,
        times_invoked           INTEGER NOT NULL DEFAULT 0,
        times_severed           INTEGER NOT NULL DEFAULT 0,
        is_currently_contracted INTEGER NOT NULL DEFAULT 1,
        metadata_json           TEXT NOT NULL DEFAULT '{}',
        first_discovered_at     REAL NOT NULL,
        updated_at              REAL NOT NULL,
        UNIQUE(user_id, patron_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_user_patron_comp_uid ON user_patron_compendium(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_user_patron_comp_codex ON user_patron_compendium(user_id, codex_id)",
    "ALTER TABLE inventory ADD COLUMN is_pact_locked INTEGER DEFAULT 0",
    "ALTER TABLE inventory ADD COLUMN linked_contract_key TEXT DEFAULT ''",
)


def _ensure_contracts_v52_tables(conn: sqlite3.Connection) -> None:
    """Self-healing DDL guard for isolated unit tests that bypass full migrations."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='session_entity_contracts' LIMIT 1"
    ).fetchone()
    if row is not None:
        return
    for sql in ENTITY_CONTRACTS_V52_DDL:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise


def build_contract_key(session_id: int, holder_id: str | int, patron_id: str) -> str:
    return f"pact_{int(session_id)}_{str(holder_id).strip()}_{str(patron_id).strip()}"


def build_grudge_key(session_id: int, holder_id: str | int, patron_id: str) -> str:
    return f"grudge_{int(session_id)}_{str(holder_id).strip()}_{str(patron_id).strip()}"


def _hydrate_contract_row(row: sqlite3.Row | Dict[str, Any]) -> Dict[str, Any]:
    d = dict(row)
    for j_col, out_col in (
        ("tithe_schedule_json", "tithe_schedule"),
        ("stat_locks_json", "stat_locks"),
        ("metadata_json", "metadata"),
    ):
        raw = d.get(j_col)
        if isinstance(raw, str):
            try:
                d[out_col] = json.loads(raw) if raw.strip() else {}
            except Exception:
                d[out_col] = {}
        elif isinstance(raw, dict):
            d[out_col] = dict(raw)
        else:
            d[out_col] = {}
    return d


def get_player_active_pacts(
    session_id: int,
    user_id: int | str,
    *,
    character_id: Optional[int] = None,
    include_inactive: bool = False,
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    """Returns active Entity Contracts for a specific player (`holder_id=str(user_id)`) in `session_id`."""
    if not session_id or user_id is None:
        return []
    sid = int(session_id)
    hid = str(user_id).strip()

    def _run(c: sqlite3.Connection) -> List[Dict[str, Any]]:
        _ensure_contracts_v52_tables(c)
        if include_inactive:
            if character_id is not None:
                rows = c.execute(
                    """SELECT * FROM session_entity_contracts
                       WHERE session_id = ? AND holder_type = 'player'
                         AND (holder_id = ? OR character_id = ?)
                       ORDER BY id ASC""",
                    (sid, hid, int(character_id)),
                ).fetchall()
            else:
                rows = c.execute(
                    """SELECT * FROM session_entity_contracts
                       WHERE session_id = ? AND holder_type = 'player' AND holder_id = ?
                       ORDER BY id ASC""",
                    (sid, hid),
                ).fetchall()
        else:
            if character_id is not None:
                rows = c.execute(
                    """SELECT * FROM session_entity_contracts
                       WHERE session_id = ? AND holder_type = 'player' AND status = 'active'
                         AND (holder_id = ? OR character_id = ?)
                       ORDER BY id ASC""",
                    (sid, hid, int(character_id)),
                ).fetchall()
            else:
                rows = c.execute(
                    """SELECT * FROM session_entity_contracts
                       WHERE session_id = ? AND holder_type = 'player' AND holder_id = ? AND status = 'active'
                       ORDER BY id ASC""",
                    (sid, hid),
                ).fetchall()
        return [_hydrate_contract_row(r) for r in rows]

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def get_session_pacts_batch(
    session_id: int,
    *,
    holder_type: Optional[str] = None,
    active_only: bool = True,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Batch-loads contracts in a single query, keyed by `holder_id` (`str(user_id)` or `npc_id`)."""
    if not session_id:
        return {}
    sid = int(session_id)

    def _run(c: sqlite3.Connection) -> Dict[str, List[Dict[str, Any]]]:
        _ensure_contracts_v52_tables(c)
        clauses = ["session_id = ?"]
        params: List[Any] = [sid]
        if holder_type:
            clauses.append("holder_type = ?")
            params.append(str(holder_type))
        if active_only:
            clauses.append("status = 'active'")
        where_sql = " AND ".join(clauses)
        rows = c.execute(
            f"SELECT * FROM session_entity_contracts WHERE {where_sql} ORDER BY id ASC",
            params,
        ).fetchall()
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            hd = _hydrate_contract_row(r)
            grouped.setdefault(str(hd["holder_id"]), []).append(hd)
        return grouped

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def get_exclusive_tier3_holder(
    session_id: int,
    patron_id: str,
    *,
    exclude_holder_id: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[Dict[str, Any]]:
    """Checks if a Patron is currently locked in an Exclusive Tier III pact by another holder in `session_id`."""
    if not session_id or not patron_id:
        return None
    sid = int(session_id)
    pid = str(patron_id).strip()

    def _run(c: sqlite3.Connection) -> Optional[Dict[str, Any]]:
        _ensure_contracts_v52_tables(c)
        if exclude_holder_id:
            row = c.execute(
                """SELECT * FROM session_entity_contracts
                   WHERE session_id = ? AND patron_id = ? AND tier >= 3
                     AND status = 'active' AND holder_id != ?
                   LIMIT 1""",
                (sid, pid, str(exclude_holder_id)),
            ).fetchone()
        else:
            row = c.execute(
                """SELECT * FROM session_entity_contracts
                   WHERE session_id = ? AND patron_id = ? AND tier >= 3 AND status = 'active'
                   LIMIT 1""",
                (sid, pid),
            ).fetchone()
        return _hydrate_contract_row(row) if row else None

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def is_patron_spurned_for_holder(
    session_id: int,
    holder_id: str | int,
    patron_id: str,
    *,
    conn: Optional[sqlite3.Connection] = None,
) -> bool:
    """Returns True if `holder_id` violently breached (`status = 'spurned'`) `patron_id` in this session."""
    if not session_id or not patron_id:
        return False
    sid = int(session_id)
    hid = str(holder_id).strip()
    pid = str(patron_id).strip()

    def _run(c: sqlite3.Connection) -> bool:
        _ensure_contracts_v52_tables(c)
        row = c.execute(
            """SELECT 1 FROM session_entity_contracts
               WHERE session_id = ? AND holder_id = ? AND patron_id = ? AND status = 'spurned'
               LIMIT 1""",
            (sid, hid, pid),
        ).fetchone()
        return row is not None

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def upsert_user_patron_compendium(
    user_id: int,
    patron: Dict[str, Any],
    *,
    tier: int = 1,
    signed_delta: int = 0,
    invoked_delta: int = 0,
    severed_delta: int = 0,
    is_currently_contracted: Optional[bool] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """Updates the account-wide Patron Compendium & Folklore `Contracted` badge table."""
    if not user_id or not isinstance(patron, dict) or not patron.get("patron_id"):
        return
    uid = int(user_id)
    pid = str(patron["patron_id"]).strip()
    now = time.time()

    def _run(c: sqlite3.Connection) -> None:
        _ensure_contracts_v52_tables(c)
        existing = c.execute(
            "SELECT * FROM user_patron_compendium WHERE user_id = ? AND patron_id = ?",
            (uid, pid),
        ).fetchone()
        if existing:
            ex = dict(existing)
            new_max_tier = max(int(ex.get("max_tier_reached") or 1), int(tier or 1))
            new_signed = max(0, int(ex.get("times_signed") or 0) + int(signed_delta))
            new_invoked = max(0, int(ex.get("times_invoked") or 0) + int(invoked_delta))
            new_severed = max(0, int(ex.get("times_severed") or 0) + int(severed_delta))
            cur_flag = int(bool(is_currently_contracted)) if is_currently_contracted is not None else int(ex.get("is_currently_contracted") or 0)
            c.execute(
                """UPDATE user_patron_compendium
                   SET max_tier_reached = ?, times_signed = ?, times_invoked = ?,
                       times_severed = ?, is_currently_contracted = ?, updated_at = ?
                   WHERE id = ?""",
                (new_max_tier, new_signed, new_invoked, new_severed, cur_flag, now, ex["id"]),
            )
        else:
            cur_flag = int(bool(is_currently_contracted)) if is_currently_contracted is not None else 1
            c.execute(
                """INSERT INTO user_patron_compendium (
                       user_id, patron_id, source_pool, codex_id, entity_name,
                       max_tier_reached, times_signed, times_invoked, times_severed,
                       is_currently_contracted, metadata_json, first_discovered_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)""",
                (
                    uid,
                    pid,
                    str(patron.get("source_pool") or "bespoke"),
                    str(patron.get("codex_id") or ""),
                    str(patron.get("name") or patron.get("display_name") or pid),
                    max(1, int(tier or 1)),
                    max(1, int(signed_delta or 1)),
                    max(0, int(invoked_delta)),
                    max(0, int(severed_delta)),
                    cur_flag,
                    now,
                    now,
                ),
            )

    if conn is not None:
        _run(conn)
    else:
        with get_conn() as c:
            _run(c)


def get_user_patron_compendium(
    user_id: int,
    *,
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    """Returns all Patron Compendium entries discovered/contracted across saves by `user_id`."""
    if not user_id:
        return []
    uid = int(user_id)

    def _run(c: sqlite3.Connection) -> List[Dict[str, Any]]:
        _ensure_contracts_v52_tables(c)
        rows = c.execute(
            "SELECT * FROM user_patron_compendium WHERE user_id = ? ORDER BY first_discovered_at ASC, id ASC",
            (uid,),
        ).fetchall()
        return [dict(r) for r in rows]

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def get_users_contracted_codex_map(
    user_ids: Iterable[int],
    *,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Dict[str, Any]]:
    """Batch-loads `codex_id -> compendium summary` for `build_encyclopedia_payload` (`Contracted` badge)."""
    uids = list(dict.fromkeys(int(u) for u in (user_ids or []) if u))
    if not uids:
        return {}

    def _run(c: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
        _ensure_contracts_v52_tables(c)
        qmarks = ",".join("?" * len(uids))
        rows = c.execute(
            f"""SELECT codex_id, patron_id, MAX(max_tier_reached) AS max_tier,
                       SUM(times_signed) AS total_signed, SUM(times_invoked) AS total_invoked,
                       MAX(is_currently_contracted) AS active_flag
                FROM user_patron_compendium
                WHERE user_id IN ({qmarks}) AND codex_id != ''
                GROUP BY codex_id""",
            uids,
        ).fetchall()
        out: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            cid = str(r["codex_id"] or "")
            if cid:
                out[cid] = {
                    "codex_id": cid,
                    "patron_id": str(r["patron_id"] or ""),
                    "contracted_ever": True,
                    "max_pact_tier": int(r["max_tier"] or 1),
                    "times_signed": int(r["total_signed"] or 1),
                    "times_invoked": int(r["total_invoked"] or 0),
                    "is_currently_contracted": bool(r["active_flag"]),
                }
        return out

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def _bind_or_update_symbiotic_gear_in_conn(
    conn: sqlite3.Connection,
    user_id: int,
    char: Dict[str, Any],
    patron: Dict[str, Any],
    tier: int,
    contract_key: str,
) -> Tuple[Optional[int], str]:
    """Equips or scales `[Pact-Bound]` symbiotic gear inside an active transaction, enforcing 2H/Shield locks."""
    from mechanics.combat.equipment import is_two_handed
    from mechanics.pacts.appraisal import build_pact_bound_gear_spec

    spec = build_pact_bound_gear_spec(char, patron, tier, contract_key)
    if not spec:
        return None, ""

    char_id = int(char["id"])
    target_slot = str(spec["slot"])
    existing_bound = conn.execute(
        "SELECT * FROM inventory WHERE character_id = ? AND linked_contract_key = ? LIMIT 1",
        (char_id, contract_key),
    ).fetchone()
    if existing_bound:
        conn.execute(
            "UPDATE inventory SET name = ?, effect = ?, equipped = 1, slot = ?, is_pact_locked = 1 WHERE id = ?",
            (spec["name"], spec["effect"], target_slot, existing_bound["id"]),
        )
        return int(existing_bound["id"]), target_slot

    # Check if ANOTHER contract already locked this slot
    conflict = conn.execute(
        """SELECT name, linked_contract_key FROM inventory
           WHERE (character_id = ? OR (character_id IS NULL AND user_id = ?))
             AND slot = ? AND equipped = 1 AND is_pact_locked = 1 AND linked_contract_key != ?""",
        (char_id, user_id, target_slot, contract_key),
    ).fetchone()
    if conflict:
        raise ValueError(
            f"Cannot bind {spec['name']}: your '{target_slot}' slot is already fused with {conflict['name']}."
        )

    # Check 2H Weapon vs Shield cross-slot lock
    if target_slot == "Weapon" and is_two_handed(spec):
        shield_row = conn.execute(
            """SELECT id, name, is_pact_locked FROM inventory
               WHERE (character_id = ? OR (character_id IS NULL AND user_id = ?))
                 AND slot = 'Shield' AND equipped = 1""",
            (char_id, user_id),
        ).fetchone()
        if shield_row:
            if bool(shield_row["is_pact_locked"]):
                raise ValueError(
                    f"Cannot bind two-handed {spec['name']} while off-hand is pact-locked with {shield_row['name']}."
                )
            conn.execute("UPDATE inventory SET equipped = 0, slot = NULL WHERE id = ?", (shield_row["id"],))

    # Unequip normal gear in target_slot
    conn.execute(
        """UPDATE inventory SET equipped = 0, slot = NULL
           WHERE (character_id = ? OR (character_id IS NULL AND user_id = ?))
             AND slot = ? AND equipped = 1 AND is_pact_locked = 0""",
        (char_id, user_id, target_slot),
    )

    cur = conn.execute(
        """INSERT INTO inventory (
               user_id, character_id, name, item_type, equipped, effect,
               slot_cost, slot, is_quest_locked, linked_quest_id, is_pact_locked, linked_contract_key
           ) VALUES (?, ?, ?, ?, 1, ?, 0, ?, 0, '', 1, ?)""",
        (user_id, char_id, spec["name"], spec["item_type"], spec["effect"], target_slot, contract_key),
    )
    return int(cur.lastrowid), target_slot


def _remove_symbiotic_gear_in_conn(
    conn: sqlite3.Connection,
    contract_key: str,
    bound_gear_item_id: Optional[int] = None,
) -> Optional[str]:
    """Removes `[Pact-Bound]` gear linked to `contract_key` on severance or rollback."""
    removed_slot: Optional[str] = None
    if contract_key:
        row = conn.execute(
            "SELECT id, slot FROM inventory WHERE linked_contract_key = ? LIMIT 1",
            (contract_key,),
        ).fetchone()
        if row:
            removed_slot = row["slot"]
            conn.execute("DELETE FROM inventory WHERE id = ?", (row["id"],))
    if bound_gear_item_id and removed_slot is None:
        row2 = conn.execute(
            "SELECT id, slot FROM inventory WHERE id = ? AND is_pact_locked = 1",
            (int(bound_gear_item_id),),
        ).fetchone()
        if row2:
            removed_slot = row2["slot"]
            conn.execute("DELETE FROM inventory WHERE id = ?", (row2["id"],))
    return removed_slot


def sign_entity_contract(
    session_id: int,
    user_id: int,
    patron: Dict[str, Any],
    *,
    tier: int = 1,
    turn_number: int = 1,
    current_day: int = 1,
    is_deaths_door: bool = False,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Atomically validates slots, base-stat minimums, Tier III exclusivity, and signs a player Entity Contract."""
    from mechanics.pacts.appraisal import (
        can_afford_stat_locks,
        compute_tier_locks_for_patron,
        evaluate_patron_appraisal,
        get_pact_slot_capacity,
    )
    from mechanics.pacts.catalog import ensure_pact_spells_registered

    ensure_pact_spells_registered()
    sid = int(session_id)
    uid = int(user_id)
    hid = str(uid)
    pid = str(patron.get("patron_id") or "").strip()
    if not pid:
        raise ValueError("Invalid Patron definition.")

    with UnitOfWork() as conn:
        _ensure_contracts_v52_tables(conn)
        # Load raw DB character row so base stats & max_hp are exact
        char_row = conn.execute(
            """SELECT * FROM characters
               WHERE user_id = ? AND (active_session_id = ? OR is_active = 1)
               ORDER BY CASE WHEN active_session_id = ? THEN 0 ELSE 1 END ASC, id DESC
               LIMIT 1""",
            (uid, sid, sid),
        ).fetchone()
        if not char_row:
            raise ValueError("No active character found for user.")
        raw_char = dict(char_row)
        char_id = int(raw_char["id"])

        if is_patron_spurned_for_holder(sid, hid, pid, conn=conn):
            raise ValueError(f"{patron.get('name', 'This entity')} has permanently Spurned you after a violent breach.")

        active_pacts = get_player_active_pacts(sid, uid, character_id=char_id, conn=conn)
        if any(p["patron_id"] == pid for p in active_pacts):
            raise ValueError(f"You already hold an active contract with {patron.get('name', pid)}.")

        slot_cap = get_pact_slot_capacity(raw_char)
        if len(active_pacts) >= slot_cap:
            raise ValueError(
                f"Pact Slot capacity reached ({len(active_pacts)}/{slot_cap}). Sever an existing contract first."
            )

        appraisal = evaluate_patron_appraisal(raw_char, patron, is_deaths_door=is_deaths_door)
        req_tier = max(1, min(3, int(tier or 1)))
        if req_tier > int(appraisal["upfront_tier_cap"]):
            raise ValueError(
                f"Upfront Tier {req_tier} requires 'Favored' appraisal (current: {appraisal['state'].title()})."
            )
        if req_tier > int(appraisal["max_unlocked_tier"]):
            raise ValueError(f"{patron.get('name', 'Patron')} disdains you and refuses Tier III Exclusive binding.")

        if req_tier >= 3:
            ex_holder = get_exclusive_tier3_holder(sid, pid, exclude_holder_id=hid, conn=conn)
            if ex_holder:
                holder_label = (ex_holder.get("metadata") or {}).get("holder_name") or ex_holder["holder_id"]
                raise ValueError(
                    f"{patron.get('name', 'Patron')}'s Exclusive Core (Tier III) is already bound to {holder_label}."
                )

        stat_locks, hp_lock_pct = compute_tier_locks_for_patron(patron, req_tier, appraisal["state"])
        ok_stats, stat_err = can_afford_stat_locks(raw_char, stat_locks, active_pacts)
        if not ok_stats:
            raise ValueError(stat_err)

        ckey = build_contract_key(sid, hid, pid)
        gear_item_id, gear_slot = _bind_or_update_symbiotic_gear_in_conn(
            conn, uid, raw_char, patron, req_tier, ckey
        )

        costs = patron.get("costs") or {}
        tithe_cfg = costs.get("tithe")
        tithe_schedule: Dict[str, Any] = {}
        if isinstance(tithe_cfg, dict) and tithe_cfg.get("interval_days"):
            interval = max(1, int(tithe_cfg["interval_days"]))
            tithe_schedule = {
                "interval_days": interval,
                "next_due_day": int(current_day) + interval,
                "last_fed_day": int(current_day),
                "label": str(tithe_cfg.get("label") or "Patron Offering"),
                "credit_fallback": int(tithe_cfg.get("credit_fallback") or 50),
                "item_keywords": list(tithe_cfg.get("item_keywords") or []),
            }

        meta_dict: Dict[str, Any] = {
            "max_hp_lock_pct": hp_lock_pct,
            "regulated": bool(patron.get("regulated", True)),
            "daily_charges_used": 0,
            "last_charge_reset_day": int(current_day),
            "zero_minute_used_day": 0,
            "appraisal_quote": appraisal["quote"],
            "holder_name": str(raw_char.get("name") or "Player"),
        }
        if extra_metadata:
            meta_dict.update(extra_metadata)

        now = time.time()
        conn.execute(
            """INSERT INTO session_entity_contracts (
                   session_id, character_id, contract_key, patron_id, source_pool, codex_id,
                   entity_name, element, synergy_stat, holder_type, holder_id, status,
                   tier, resonance_xp, appraisal_state, breach_stage, unpaid_blood_debt,
                   bound_gear_item_id, bound_gear_slot, taboo_id, tithe_schedule_json,
                   stat_locks_json, metadata_json, turn_signed, turn_updated, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'player', ?, 'active', ?, 0, ?, 0, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id, contract_key) DO UPDATE SET
                   character_id = excluded.character_id,
                   status = 'active',
                   tier = excluded.tier,
                   appraisal_state = excluded.appraisal_state,
                   breach_stage = 0,
                   unpaid_blood_debt = 0,
                   bound_gear_item_id = excluded.bound_gear_item_id,
                   bound_gear_slot = excluded.bound_gear_slot,
                   tithe_schedule_json = excluded.tithe_schedule_json,
                   stat_locks_json = excluded.stat_locks_json,
                   metadata_json = excluded.metadata_json,
                   turn_signed = excluded.turn_signed,
                   turn_updated = excluded.turn_updated,
                   updated_at = excluded.updated_at""",
            (
                sid,
                char_id,
                ckey,
                pid,
                str(patron.get("source_pool") or "bespoke"),
                str(patron.get("codex_id") or ""),
                str(patron.get("name") or patron.get("display_name") or pid),
                str(patron.get("element") or "aether"),
                str(patron.get("synergy_stat") or "INT"),
                hid,
                req_tier,
                appraisal["state"],
                gear_item_id,
                gear_slot,
                str(costs.get("taboo_id") or ""),
                json.dumps(tithe_schedule),
                json.dumps(stat_locks),
                json.dumps(meta_dict),
                int(turn_number),
                int(turn_number),
                now,
                now,
            ),
        )

        # Clamp stored characters.hp if derived max_hp dropped below current hp
        eff_char = db.get_character(uid, session_id=sid)
        if eff_char and int(raw_char.get("hp") or 0) > int(eff_char.get("max_hp") or 100):
            conn.execute(
                "UPDATE characters SET hp = ? WHERE id = ?",
                (int(eff_char["max_hp"]), char_id),
            )

        upsert_user_patron_compendium(
            uid, patron, tier=req_tier, signed_delta=1, is_currently_contracted=True, conn=conn
        )
        created_row = conn.execute(
            "SELECT * FROM session_entity_contracts WHERE session_id = ? AND contract_key = ?",
            (sid, ckey),
        ).fetchone()
        result = _hydrate_contract_row(created_row)

    if gear_slot:
        try:
            from .inventory import _sync_post_equipment_mutation
            _sync_post_equipment_mutation(uid, changed_slot=gear_slot, raise_on_error=False)
        except Exception:
            pass
    return result


def seed_npc_entity_contract(
    session_id: int,
    npc_id: str,
    npc_name: str,
    patron: Dict[str, Any],
    *,
    tier: int = 1,
    turn_number: int = 0,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[Dict[str, Any]]:
    """Registers a pre-contracted Special Agent's pact in `session_entity_contracts` (respecting Tier III uniqueness)."""
    if not session_id or not npc_id or not isinstance(patron, dict):
        return None
    sid = int(session_id)
    hid = str(npc_id).strip()
    pid = str(patron.get("patron_id") or "").strip()
    eff_tier = max(1, min(3, int(tier or 1)))

    def _run(c: sqlite3.Connection) -> Optional[Dict[str, Any]]:
        _ensure_contracts_v52_tables(c)
        if eff_tier >= 3 and get_exclusive_tier3_holder(sid, pid, exclude_holder_id=hid, conn=c):
            return None
        ckey = build_contract_key(sid, hid, pid)
        now = time.time()
        meta = {
            "holder_name": str(npc_name or hid),
            "regulated": bool(patron.get("regulated", True)),
            "daily_charges_used": 0,
        }
        c.execute(
            """INSERT OR IGNORE INTO session_entity_contracts (
                   session_id, character_id, contract_key, patron_id, source_pool, codex_id,
                   entity_name, element, synergy_stat, holder_type, holder_id, status,
                   tier, resonance_xp, appraisal_state, breach_stage, unpaid_blood_debt,
                   bound_gear_item_id, bound_gear_slot, taboo_id, tithe_schedule_json,
                   stat_locks_json, metadata_json, turn_signed, turn_updated, created_at, updated_at
               ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, 'npc', ?, 'active', ?, 0, 'favored', 0, 0, NULL, '', ?, '{}', '{}', ?, ?, ?, ?, ?)""",
            (
                sid,
                ckey,
                pid,
                str(patron.get("source_pool") or "bespoke"),
                str(patron.get("codex_id") or ""),
                str(patron.get("name") or pid),
                str(patron.get("element") or "aether"),
                str(patron.get("synergy_stat") or "INT"),
                hid,
                eff_tier,
                str((patron.get("costs") or {}).get("taboo_id") or ""),
                json.dumps(meta),
                int(turn_number),
                int(turn_number),
                now,
                now,
            ),
        )
        row = c.execute(
            "SELECT * FROM session_entity_contracts WHERE session_id = ? AND contract_key = ?",
            (sid, ckey),
        ).fetchone()
        return _hydrate_contract_row(row) if row else None

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def upgrade_entity_contract_tier(
    session_id: int,
    user_id: int,
    patron_id: str,
    patron: Dict[str, Any],
    *,
    target_tier: Optional[int] = None,
    turn_number: int = 1,
) -> Dict[str, Any]:
    """Upgrades an active Pact to Tier II or Tier III (checking Resonance XP, Appraisal cap, stat locks & exclusivity)."""
    from mechanics.pacts.appraisal import (
        RESONANCE_XP_THRESHOLDS,
        can_afford_stat_locks,
        compute_tier_locks_for_patron,
    )

    sid = int(session_id)
    uid = int(user_id)
    hid = str(uid)
    pid = str(patron_id).strip()

    with UnitOfWork() as conn:
        _ensure_contracts_v52_tables(conn)
        active = get_player_active_pacts(sid, uid, conn=conn)
        current = next((p for p in active if p["patron_id"] == pid), None)
        if not current:
            raise ValueError("No active contract found for that Patron.")
        if int(current.get("breach_stage") or 0) >= 1:
            raise ValueError("Cannot deepen a contract while the Patron is Displeased (Stage 1 Breach).")

        cur_tier = int(current.get("tier") or 1)
        next_tier = int(target_tier) if target_tier is not None else (cur_tier + 1)
        if next_tier <= cur_tier or next_tier > 3:
            raise ValueError("Contract is already at maximum available Tier.")

        app_state = str(current.get("appraisal_state") or "neutral").lower()
        if app_state == "disdained" and next_tier >= 3:
            raise ValueError(f"{current['entity_name']} disdains you and refuses Exclusive Tier III binding.")

        req_xp = RESONANCE_XP_THRESHOLDS.get(next_tier, 99)
        if app_state != "favored" and int(current.get("resonance_xp") or 0) < req_xp:
            raise ValueError(
                f"Insufficient Pact Resonance ({current.get('resonance_xp', 0)}/{req_xp}) for Tier {next_tier}."
            )

        if next_tier >= 3:
            ex_holder = get_exclusive_tier3_holder(sid, pid, exclude_holder_id=hid, conn=conn)
            if ex_holder:
                holder_label = (ex_holder.get("metadata") or {}).get("holder_name") or ex_holder["holder_id"]
                raise ValueError(f"{current['entity_name']} Tier III Exclusive Core is currently held by {holder_label}.")

        char_row = conn.execute(
            "SELECT * FROM characters WHERE id = ? LIMIT 1",
            (current.get("character_id"),),
        ).fetchone() or conn.execute(
            "SELECT * FROM characters WHERE user_id = ? ORDER BY is_active DESC, id DESC LIMIT 1",
            (uid,),
        ).fetchone()
        raw_char = dict(char_row)

        stat_locks, hp_lock_pct = compute_tier_locks_for_patron(patron, next_tier, app_state)
        ok_stats, stat_err = can_afford_stat_locks(
            raw_char, stat_locks, active, replacing_contract_key=current["contract_key"]
        )
        if not ok_stats:
            raise ValueError(stat_err)

        gear_item_id, gear_slot = _bind_or_update_symbiotic_gear_in_conn(
            conn, uid, raw_char, patron, next_tier, current["contract_key"]
        )
        meta = dict(current.get("metadata") or {})
        meta["max_hp_lock_pct"] = hp_lock_pct
        now = time.time()
        conn.execute(
            """UPDATE session_entity_contracts
               SET tier = ?, stat_locks_json = ?, metadata_json = ?,
                   bound_gear_item_id = COALESCE(?, bound_gear_item_id),
                   bound_gear_slot = CASE WHEN ? != '' THEN ? ELSE bound_gear_slot END,
                   turn_updated = ?, updated_at = ?
               WHERE id = ?""",
            (
                next_tier,
                json.dumps(stat_locks),
                json.dumps(meta),
                gear_item_id,
                gear_slot,
                gear_slot,
                int(turn_number),
                now,
                current["id"],
            ),
        )
        upsert_user_patron_compendium(uid, patron, tier=next_tier, is_currently_contracted=True, conn=conn)
        updated_row = conn.execute(
            "SELECT * FROM session_entity_contracts WHERE id = ?", (current["id"],)
        ).fetchone()
        res = _hydrate_contract_row(updated_row)

    if gear_slot:
        try:
            from .inventory import _sync_post_equipment_mutation
            _sync_post_equipment_mutation(uid, changed_slot=gear_slot, raise_on_error=False)
        except Exception:
            pass
    return res


def record_pact_resonance_and_charges(
    session_id: int,
    contract_key: str,
    *,
    user_id: Optional[int] = None,
    patron: Optional[Dict[str, Any]] = None,
    xp_delta: int = 1,
    charge_delta: int = 0,
    current_day: Optional[int] = None,
    clear_breach: bool = False,
    advance_tithe: bool = False,
    turn_number: int = 1,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[Dict[str, Any]]:
    """Updates `resonance_xp`, daily cast charges, tithe due date, or clears Stage 1 `Displeased`."""
    sid = int(session_id)
    now = time.time()

    def _run(c: sqlite3.Connection) -> Optional[Dict[str, Any]]:
        _ensure_contracts_v52_tables(c)
        row = c.execute(
            "SELECT * FROM session_entity_contracts WHERE session_id = ? AND contract_key = ?",
            (sid, contract_key),
        ).fetchone()
        if not row:
            return None
        cur = _hydrate_contract_row(row)
        new_xp = max(0, int(cur.get("resonance_xp") or 0) + int(xp_delta))
        meta = dict(cur.get("metadata") or {})
        if current_day is not None and int(meta.get("last_charge_reset_day") or 0) != int(current_day):
            meta["daily_charges_used"] = 0
            meta["last_charge_reset_day"] = int(current_day)
        if charge_delta:
            meta["daily_charges_used"] = max(0, int(meta.get("daily_charges_used") or 0) + int(charge_delta))

        tithe = dict(cur.get("tithe_schedule") or {})
        if advance_tithe and tithe.get("interval_days") and current_day is not None:
            tithe["last_fed_day"] = int(current_day)
            tithe["next_due_day"] = int(current_day) + int(tithe["interval_days"])

        new_breach = 0 if clear_breach else int(cur.get("breach_stage") or 0)
        new_debt = 0 if clear_breach else int(cur.get("unpaid_blood_debt") or 0)

        c.execute(
            """UPDATE session_entity_contracts
               SET resonance_xp = ?, breach_stage = ?, unpaid_blood_debt = ?,
                   tithe_schedule_json = ?, metadata_json = ?, turn_updated = ?, updated_at = ?
               WHERE id = ?""",
            (
                new_xp,
                new_breach,
                new_debt,
                json.dumps(tithe),
                json.dumps(meta),
                int(turn_number),
                now,
                cur["id"],
            ),
        )
        if user_id and patron and charge_delta > 0:
            upsert_user_patron_compendium(int(user_id), patron, tier=int(cur.get("tier") or 1), invoked_delta=1, conn=c)
        refreshed = c.execute("SELECT * FROM session_entity_contracts WHERE id = ?", (cur["id"],)).fetchone()
        return _hydrate_contract_row(refreshed) if refreshed else None

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def mark_pact_zero_minute_step_used(
    session_id: int,
    contract_key: str,
    current_day: int,
    *,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """Marks the 1/day 0-minute threshold transit step as used for `current_day`."""
    if not session_id or not contract_key:
        return
    sid = int(session_id)
    now = time.time()

    def _run(c: sqlite3.Connection) -> None:
        _ensure_contracts_v52_tables(c)
        row = c.execute(
            "SELECT id, metadata_json FROM session_entity_contracts WHERE session_id = ? AND contract_key = ?",
            (sid, str(contract_key)),
        ).fetchone()
        if not row:
            return
        try:
            meta = json.loads(row["metadata_json"] or "{}")
            if not isinstance(meta, dict):
                meta = {}
        except Exception:
            meta = {}
        meta["zero_minute_used_day"] = int(current_day or 1)
        c.execute(
            "UPDATE session_entity_contracts SET metadata_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(meta), now, row["id"]),
        )

    if conn is not None:
        _run(conn)
    else:
        with get_conn() as c:
            _run(c)


def apply_contract_breach_strike(
    session_id: int,
    contract_key: str,
    *,
    reason: str = "unpaid_blood_debt",
    blood_debt_amount: int = 0,
    turn_number: int = 1,
    spawn_grudge_if_stage2: bool = True,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    """Escalates a contract from Stage 0 -> Stage 1 (`Displeased`) or Stage 1 -> Stage 2 (`Violent Severance`)."""
    sid = int(session_id)
    now = time.time()

    def _run(c: sqlite3.Connection) -> Dict[str, Any]:
        _ensure_contracts_v52_tables(c)
        row = c.execute(
            "SELECT * FROM session_entity_contracts WHERE session_id = ? AND contract_key = ?",
            (sid, contract_key),
        ).fetchone()
        if not row:
            return {"escalated_to": 0}
        cur = _hydrate_contract_row(row)
        prev_stage = int(cur.get("breach_stage") or 0)
        meta = dict(cur.get("metadata") or {})
        meta["last_breach_reason"] = str(reason)
        meta["last_breach_turn"] = int(turn_number)

        if prev_stage == 0:
            new_debt = int(cur.get("unpaid_blood_debt") or 0) + max(1, int(blood_debt_amount or 1))
            c.execute(
                """UPDATE session_entity_contracts
                   SET breach_stage = 1, unpaid_blood_debt = ?, metadata_json = ?, turn_updated = ?, updated_at = ?
                   WHERE id = ?""",
                (new_debt, json.dumps(meta), int(turn_number), now, cur["id"]),
            )
            return {
                "escalated_to": 1,
                "contract_key": contract_key,
                "patron_id": cur["patron_id"],
                "entity_name": cur["entity_name"],
                "holder_id": cur["holder_id"],
                "reason": reason,
            }

        # Stage 1 -> Stage 2: Violent Severance!
        removed_slot = _remove_symbiotic_gear_in_conn(c, contract_key, cur.get("bound_gear_item_id"))
        c.execute(
            """UPDATE session_entity_contracts
               SET status = 'spurned', breach_stage = 2, bound_gear_item_id = NULL,
                   bound_gear_slot = '', metadata_json = ?, turn_updated = ?, updated_at = ?
               WHERE id = ?""",
            (json.dumps(meta), int(turn_number), now, cur["id"]),
        )

        is_unregulated = not bool(meta.get("regulated", True))
        grudge_key = build_grudge_key(sid, cur["holder_id"], cur["patron_id"])
        nemesis_flag = 1 if (spawn_grudge_if_stage2 and is_unregulated) else 0
        c.execute(
            """INSERT INTO session_contract_grudges (
                   session_id, character_id, grudge_key, patron_id, entity_name, holder_id,
                   status, soul_scar_active, nemesis_spawned, metadata_json,
                   severance_turn, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, 'active', 1, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id, grudge_key) DO UPDATE SET
                   status = 'active',
                   soul_scar_active = 1,
                   nemesis_spawned = excluded.nemesis_spawned,
                   severance_turn = excluded.severance_turn,
                   updated_at = excluded.updated_at""",
            (
                sid,
                cur.get("character_id"),
                grudge_key,
                cur["patron_id"],
                cur["entity_name"],
                cur["holder_id"],
                nemesis_flag,
                json.dumps({"reason": reason, "element": cur.get("element", "aether"), "tier": cur.get("tier", 1)}),
                int(turn_number),
                now,
                now,
            ),
        )
        if cur.get("holder_type") == "player" and str(cur.get("holder_id", "")).isdigit():
            c.execute(
                """UPDATE user_patron_compendium
                   SET is_currently_contracted = 0, times_severed = times_severed + 1, updated_at = ?
                   WHERE user_id = ? AND patron_id = ?""",
                (now, int(cur["holder_id"]), cur["patron_id"]),
            )
        return {
            "escalated_to": 2,
            "contract_key": contract_key,
            "grudge_key": grudge_key,
            "patron_id": cur["patron_id"],
            "entity_name": cur["entity_name"],
            "holder_id": cur["holder_id"],
            "soul_scar_applied": True,
            "grudge_nemesis_spawned": bool(nemesis_flag),
            "removed_gear_slot": removed_slot,
            "reason": reason,
        }

    if conn is not None:
        return _run(conn)
    with UnitOfWork() as c:
        return _run(c)


def sever_entity_contract(
    session_id: int,
    user_id: int,
    patron_id: str,
    *,
    turn_number: int = 1,
    mark_spurned: bool = False,
) -> Dict[str, Any]:
    """Cleanly terminates an active player contract (after Medical/Temple scrub or Exorcism victory)."""
    sid = int(session_id)
    uid = int(user_id)
    hid = str(uid)
    pid = str(patron_id).strip()
    now = time.time()
    removed_slot: Optional[str] = None

    with UnitOfWork() as conn:
        _ensure_contracts_v52_tables(conn)
        row = conn.execute(
            """SELECT * FROM session_entity_contracts
               WHERE session_id = ? AND holder_type = 'player' AND holder_id = ?
                 AND patron_id = ? AND status = 'active'
               LIMIT 1""",
            (sid, hid, pid),
        ).fetchone()
        if not row:
            raise ValueError("No active contract found for that Patron.")
        cur = _hydrate_contract_row(row)
        removed_slot = _remove_symbiotic_gear_in_conn(conn, cur["contract_key"], cur.get("bound_gear_item_id"))
        new_status = "spurned" if mark_spurned else "severed"
        conn.execute(
            """UPDATE session_entity_contracts
               SET status = ?, bound_gear_item_id = NULL, bound_gear_slot = '',
                   turn_updated = ?, updated_at = ?
               WHERE id = ?""",
            (new_status, int(turn_number), now, cur["id"]),
        )
        conn.execute(
            """UPDATE user_patron_compendium
               SET is_currently_contracted = 0, times_severed = times_severed + 1, updated_at = ?
               WHERE user_id = ? AND patron_id = ?""",
            (now, uid, pid),
        )

    if removed_slot:
        try:
            from .inventory import _sync_post_equipment_mutation
            _sync_post_equipment_mutation(uid, changed_slot=removed_slot, raise_on_error=False)
        except Exception:
            pass
    return {"status": new_status, "patron_id": pid, "entity_name": cur["entity_name"], "removed_gear_slot": removed_slot}


def liberate_npc_exclusive_pacts(
    session_id: int,
    npc_identifier: str,
    *,
    turn_number: int = 1,
    conn: Optional[sqlite3.Connection] = None,
) -> List[str]:
    """Frees any Exclusive Tier III Patrons held by a defeated/exorcised hostile VIP Special Agent."""
    if not session_id or not npc_identifier:
        return []
    sid = int(session_id)
    needle = str(npc_identifier).strip().lower()
    now = time.time()

    def _run(c: sqlite3.Connection) -> List[str]:
        _ensure_contracts_v52_tables(c)
        rows = c.execute(
            "SELECT * FROM session_entity_contracts WHERE session_id = ? AND holder_type = 'npc' AND status = 'active'",
            (sid,),
        ).fetchall()
        freed: List[str] = []
        for r in rows:
            hd = _hydrate_contract_row(r)
            h_name = str((hd.get("metadata") or {}).get("holder_name") or "").strip().lower()
            if str(hd["holder_id"]).strip().lower() == needle or (h_name and h_name == needle):
                c.execute(
                    "UPDATE session_entity_contracts SET status = 'severed', turn_updated = ?, updated_at = ? WHERE id = ?",
                    (int(turn_number), now, hd["id"]),
                )
                freed.append(str(hd["patron_id"]))
        return freed

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def get_session_active_grudges(
    session_id: int,
    holder_id: Optional[str | int] = None,
    *,
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    if not session_id:
        return []
    sid = int(session_id)

    def _run(c: sqlite3.Connection) -> List[Dict[str, Any]]:
        _ensure_contracts_v52_tables(c)
        if holder_id is not None:
            rows = c.execute(
                "SELECT * FROM session_contract_grudges WHERE session_id = ? AND holder_id = ? AND status = 'active'",
                (sid, str(holder_id).strip()),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM session_contract_grudges WHERE session_id = ? AND status = 'active'",
                (sid,),
            ).fetchall()
        return [dict(r) for r in rows]

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def save_contract_turn_snapshot(
    session_id: int,
    turn_number: int,
    *,
    overwrite: bool = False,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """Captures `session_entity_contracts` and `session_contract_grudges` at `turn_number`."""
    if not session_id:
        return
    sid = int(session_id)
    t_num = int(turn_number)
    now = time.time()

    def _run(c: sqlite3.Connection) -> None:
        _ensure_contracts_v52_tables(c)
        contracts = [
            {k: v for k, v in dict(r).items() if k != "id"}
            for r in c.execute("SELECT * FROM session_entity_contracts WHERE session_id = ? ORDER BY id ASC", (sid,)).fetchall()
        ]
        grudges = [
            {k: v for k, v in dict(r).items() if k != "id"}
            for r in c.execute("SELECT * FROM session_contract_grudges WHERE session_id = ? ORDER BY id ASC", (sid,)).fetchall()
        ]
        if overwrite:
            c.execute(
                """INSERT INTO session_contract_turn_snapshots (
                       session_id, turn_number, contracts_json, grudges_json, created_at
                   ) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(session_id, turn_number) DO UPDATE SET
                       contracts_json = excluded.contracts_json,
                       grudges_json = excluded.grudges_json,
                       created_at = excluded.created_at""",
                (sid, t_num, json.dumps(contracts, default=str), json.dumps(grudges, default=str), now),
            )
        else:
            c.execute(
                """INSERT OR IGNORE INTO session_contract_turn_snapshots (
                       session_id, turn_number, contracts_json, grudges_json, created_at
                   ) VALUES (?, ?, ?, ?, ?)""",
                (sid, t_num, json.dumps(contracts, default=str), json.dumps(grudges, default=str), now),
            )

    if conn is not None:
        _run(conn)
    else:
        with get_conn() as c:
            _run(c)


def rollback_entity_contracts_after_turn(
    session_id: int,
    turn_number: int,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, int]:
    """Restores contracts, grudges, and `[Pact-Bound]` gear to `turn_number` inside atomic session rollback."""
    if not session_id:
        return {"contracts_restored": 0, "grudges_restored": 0, "pact_gear_pruned": 0}
    sid = int(session_id)
    t_num = int(turn_number)

    def _run(c: sqlite3.Connection) -> Dict[str, int]:
        _ensure_contracts_v52_tables(c)
        snap_row = c.execute(
            """SELECT turn_number, contracts_json, grudges_json
               FROM session_contract_turn_snapshots
               WHERE session_id = ? AND turn_number <= ?
               ORDER BY turn_number DESC
               LIMIT 1""",
            (sid, t_num),
        ).fetchone()
        c.execute(
            "DELETE FROM session_contract_turn_snapshots WHERE session_id = ? AND turn_number > ?",
            (sid, t_num),
        )

        contracts_restored = 0
        grudges_restored = 0

        if snap_row is not None:
            def _restore(tbl: str, raw_json: str) -> int:
                try:
                    items = json.loads(raw_json or "[]")
                except Exception:
                    items = []
                valid_cols = {
                    r["name"] if isinstance(r, sqlite3.Row) else r[1]
                    for r in c.execute(f"PRAGMA table_info({tbl})").fetchall()
                }
                c.execute(f"DELETE FROM {tbl} WHERE session_id = ?", (sid,))
                cnt = 0
                for item in (items if isinstance(items, list) else []):
                    if not isinstance(item, dict):
                        continue
                    rd = {
                        k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
                        for k, v in item.items()
                        if k in valid_cols and k not in ("id", "session_id")
                    }
                    if not rd:
                        continue
                    rd["session_id"] = sid
                    cols_sql = ",".join(rd.keys())
                    qmarks = ",".join("?" * len(rd))
                    c.execute(f"INSERT INTO {tbl} ({cols_sql}) VALUES ({qmarks})", list(rd.values()))
                    cnt += 1
                return cnt

            contracts_restored = _restore("session_entity_contracts", snap_row["contracts_json"])
            grudges_restored = _restore("session_contract_grudges", snap_row["grudges_json"])
        else:
            c.execute(
                "DELETE FROM session_entity_contracts WHERE session_id = ? AND turn_signed > ?",
                (sid, t_num),
            )
            c.execute(
                "DELETE FROM session_contract_grudges WHERE session_id = ? AND severance_turn > ?",
                (sid, t_num),
            )

        # Prune any [Pact-Bound] gear in this session whose contract is no longer active
        gear_cur = c.execute(
            """DELETE FROM inventory
               WHERE is_pact_locked = 1
                 AND linked_contract_key != ''
                 AND linked_contract_key NOT IN (
                     SELECT contract_key FROM session_entity_contracts
                     WHERE session_id = ? AND status = 'active'
                 )
                 AND (
                     character_id IN (
                         SELECT id FROM characters
                         WHERE active_session_id = ?
                            OR user_id IN (SELECT user_id FROM session_members WHERE session_id = ?)
                     )
                     OR user_id IN (SELECT user_id FROM session_members WHERE session_id = ?)
                 )""",
            (sid, sid, sid, sid),
        )
        pruned_gear = int(gear_cur.rowcount or 0)

        # Re-create & re-link [Pact-Bound] gear if an active contract lost its item (e.g., violent severance rolled back!)
        from mechanics.pacts.catalog import get_patron_by_id
        active_player_rows = c.execute(
            "SELECT * FROM session_entity_contracts WHERE session_id = ? AND holder_type = 'player' AND status = 'active'",
            (sid,),
        ).fetchall()
        for pr in active_player_rows:
            phd = _hydrate_contract_row(pr)
            if not str(phd.get("holder_id") or "").isdigit():
                continue
            uid = int(phd["holder_id"])
            patron = get_patron_by_id(phd["patron_id"])
            if not patron or not patron.get("bound_gear"):
                continue
            c_row = c.execute("SELECT * FROM characters WHERE id = ? LIMIT 1", (phd.get("character_id"),)).fetchone()
            if not c_row:
                continue
            try:
                g_id, g_slot = _bind_or_update_symbiotic_gear_in_conn(
                    c, uid, dict(c_row), patron, int(phd.get("tier") or 1), phd["contract_key"]
                )
                if g_id:
                    c.execute(
                        "UPDATE session_entity_contracts SET bound_gear_item_id = ?, bound_gear_slot = ? WHERE id = ?",
                        (g_id, g_slot, phd["id"]),
                    )
            except Exception:
                pass

        return {
            "contracts_restored": contracts_restored,
            "grudges_restored": grudges_restored,
            "pact_gear_pruned": pruned_gear,
        }

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)
