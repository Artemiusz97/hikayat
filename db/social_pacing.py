from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Iterable

from .core import get_conn

SOCIAL_V50_DDL_STATEMENTS: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS npc_social_composure (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id              INTEGER NOT NULL,
        npc_id                  TEXT NOT NULL,
        current_composure       INTEGER NOT NULL DEFAULT 100,
        max_composure           INTEGER NOT NULL DEFAULT 100,
        composure_state         TEXT NOT NULL DEFAULT 'composed',
        mood                    TEXT NOT NULL DEFAULT 'Engaged',
        mood_dc_mod             INTEGER NOT NULL DEFAULT 0,
        last_schedule_block     TEXT NOT NULL DEFAULT '',
        last_interaction_day    INTEGER NOT NULL DEFAULT 1,
        last_interaction_minute INTEGER NOT NULL DEFAULT 0,
        lockout_until_day       INTEGER NOT NULL DEFAULT 0,
        lockout_until_minute    INTEGER NOT NULL DEFAULT 0,
        clear_the_air_required  INTEGER NOT NULL DEFAULT 0,
        clear_the_air_reason    TEXT NOT NULL DEFAULT '',
        turn_updated            INTEGER NOT NULL DEFAULT 0,
        updated_at              REAL NOT NULL,
        UNIQUE(session_id, npc_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_npc_social_composure_sess ON npc_social_composure(session_id, npc_id)",
    """CREATE TABLE IF NOT EXISTS character_social_daily (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id              INTEGER NOT NULL,
        character_id            INTEGER NOT NULL DEFAULT 0,
        npc_id                  TEXT NOT NULL,
        current_day             INTEGER NOT NULL DEFAULT 1,
        daily_affinity_earned   INTEGER NOT NULL DEFAULT 0,
        is_on_date              INTEGER NOT NULL DEFAULT 0,
        gift_given_today        INTEGER NOT NULL DEFAULT 0,
        confession_given_today  INTEGER NOT NULL DEFAULT 0,
        turn_updated            INTEGER NOT NULL DEFAULT 0,
        updated_at              REAL NOT NULL,
        UNIQUE(session_id, character_id, npc_id, current_day)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_char_social_daily_lookup ON character_social_daily(session_id, character_id, current_day)",
    """CREATE TABLE IF NOT EXISTS social_topic_states (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id              INTEGER NOT NULL,
        character_id            INTEGER NOT NULL DEFAULT 0,
        npc_id                  TEXT NOT NULL,
        topic_id                TEXT NOT NULL,
        category                TEXT NOT NULL DEFAULT '',
        depth_tier              INTEGER NOT NULL DEFAULT 1,
        last_outcome            TEXT NOT NULL DEFAULT '',
        last_discussed_day      INTEGER NOT NULL DEFAULT 0,
        cooldown_until_day      INTEGER NOT NULL DEFAULT 0,
        cooldown_until_minute   INTEGER NOT NULL DEFAULT 0,
        last_venue_leaf         TEXT NOT NULL DEFAULT '',
        turn_updated            INTEGER NOT NULL DEFAULT 0,
        updated_at              REAL NOT NULL,
        UNIQUE(session_id, character_id, npc_id, topic_id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_social_topic_states_lookup ON social_topic_states(session_id, character_id, npc_id)",
    """CREATE TABLE IF NOT EXISTS contact_dossier_discoveries (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id              INTEGER NOT NULL,
        character_id            INTEGER NOT NULL DEFAULT 0,
        npc_id                  TEXT NOT NULL,
        fact_category           TEXT NOT NULL,
        fact_key                TEXT NOT NULL,
        fact_value              TEXT NOT NULL DEFAULT '',
        discovered_turn         INTEGER NOT NULL DEFAULT 0,
        discovery_source        TEXT NOT NULL DEFAULT 'dialogue',
        created_at              REAL NOT NULL,
        UNIQUE(session_id, character_id, npc_id, fact_category, fact_key)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_contact_discoveries_lookup ON contact_dossier_discoveries(session_id, character_id, npc_id)",
    "CREATE INDEX IF NOT EXISTS idx_contact_discoveries_turn ON contact_dossier_discoveries(session_id, discovered_turn)",
    """CREATE TABLE IF NOT EXISTS social_turn_snapshots (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id              INTEGER NOT NULL,
        turn_number             INTEGER NOT NULL,
        composure_json          TEXT NOT NULL DEFAULT '[]',
        daily_json              TEXT NOT NULL DEFAULT '[]',
        topic_states_json       TEXT NOT NULL DEFAULT '[]',
        updated_at              REAL NOT NULL,
        UNIQUE(session_id, turn_number)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_social_turn_snap_sess_turn ON social_turn_snapshots(session_id, turn_number)",
)

_KIN_TIE_TYPES = frozenset(
    {
        "sibling",
        "brother",
        "sister",
        "parent",
        "father",
        "mother",
        "child",
        "son",
        "daughter",
        "spouse",
        "husband",
        "wife",
        "cousin",
        "guardian",
        "kin",
        "family",
    }
)
_ROMANTIC_TIE_TYPES = frozenset({"dating", "lover", "partner", "spouse", "husband", "wife", "fiance", "girlfriend", "boyfriend"})


def canon_social_npc_id(npc_id: str) -> str:
    raw = str(npc_id or "").strip()
    if not raw:
        return ""
    try:
        from mechanics.social.relationship_graph import canonical_person_key

        return canonical_person_key(raw)
    except Exception:
        return raw.lower().replace("-", "_").replace(" ", "_")


def _ensure_social_v50_tables(conn: sqlite3.Connection) -> None:
    for sql in SOCIAL_V50_DDL_STATEMENTS:
        conn.execute(sql)


def get_npc_social_composure(
    session_id: int,
    npc_id: str,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    if not session_id or not npc_id:
        return None
    nid = canon_social_npc_id(npc_id)

    def _run(c: sqlite3.Connection) -> dict[str, Any] | None:
        row = c.execute(
            "SELECT * FROM npc_social_composure WHERE session_id = ? AND npc_id = ?",
            (int(session_id), nid),
        ).fetchone()
        return dict(row) if row else None

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def get_npc_social_composure_batch(
    session_id: int,
    npc_ids: Iterable[str] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, dict[str, Any]]:
    if not session_id:
        return {}
    norm_ids = [canon_social_npc_id(x) for x in (npc_ids or []) if str(x or "").strip()]

    def _run(c: sqlite3.Connection) -> dict[str, dict[str, Any]]:
        if norm_ids:
            qmarks = ",".join("?" * len(norm_ids))
            rows = c.execute(
                f"SELECT * FROM npc_social_composure WHERE session_id = ? AND npc_id IN ({qmarks})",
                [int(session_id), *norm_ids],
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM npc_social_composure WHERE session_id = ?",
                (int(session_id),),
            ).fetchall()
        return {str(r["npc_id"]): dict(r) for r in rows}

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def upsert_npc_social_composure(
    session_id: int,
    npc_id: str,
    *,
    current_composure: int | None = None,
    max_composure: int | None = None,
    composure_state: str | None = None,
    mood: str | None = None,
    mood_dc_mod: int | None = None,
    last_schedule_block: str | None = None,
    last_interaction_day: int | None = None,
    last_interaction_minute: int | None = None,
    lockout_until_day: int | None = None,
    lockout_until_minute: int | None = None,
    clear_the_air_required: int | bool | None = None,
    clear_the_air_reason: str | None = None,
    turn_updated: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    sid = int(session_id)
    nid = canon_social_npc_id(npc_id)
    now = time.time()

    def _run(c: sqlite3.Connection) -> dict[str, Any]:
        existing = get_npc_social_composure(sid, nid, conn=c) or {}
        eff_max = int(max_composure if max_composure is not None else existing.get("max_composure", 100))
        eff_max = max(20, eff_max)
        eff_cur = int(current_composure if current_composure is not None else existing.get("current_composure", eff_max))
        eff_cur = max(0, min(eff_max, eff_cur))
        eff_state = str(composure_state if composure_state is not None else existing.get("composure_state", "composed"))
        eff_mood = str(mood if mood is not None else existing.get("mood", "Engaged"))
        eff_dc_mod = int(mood_dc_mod if mood_dc_mod is not None else existing.get("mood_dc_mod", 0))
        eff_block = str(last_schedule_block if last_schedule_block is not None else existing.get("last_schedule_block", ""))
        eff_day = int(last_interaction_day if last_interaction_day is not None else existing.get("last_interaction_day", 1))
        eff_min = int(last_interaction_minute if last_interaction_minute is not None else existing.get("last_interaction_minute", 0))
        eff_lock_day = int(lockout_until_day if lockout_until_day is not None else existing.get("lockout_until_day", 0))
        eff_lock_min = int(lockout_until_minute if lockout_until_minute is not None else existing.get("lockout_until_minute", 0))
        eff_cta = int(bool(clear_the_air_required)) if clear_the_air_required is not None else int(existing.get("clear_the_air_required", 0))
        eff_cta_reason = str(clear_the_air_reason if clear_the_air_reason is not None else existing.get("clear_the_air_reason", ""))
        eff_turn = int(turn_updated if turn_updated is not None else existing.get("turn_updated", 0))

        c.execute(
            """INSERT INTO npc_social_composure (
                   session_id, npc_id, current_composure, max_composure, composure_state,
                   mood, mood_dc_mod, last_schedule_block, last_interaction_day, last_interaction_minute,
                   lockout_until_day, lockout_until_minute, clear_the_air_required, clear_the_air_reason,
                   turn_updated, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id, npc_id) DO UPDATE SET
                   current_composure = excluded.current_composure,
                   max_composure = excluded.max_composure,
                   composure_state = excluded.composure_state,
                   mood = excluded.mood,
                   mood_dc_mod = excluded.mood_dc_mod,
                   last_schedule_block = excluded.last_schedule_block,
                   last_interaction_day = excluded.last_interaction_day,
                   last_interaction_minute = excluded.last_interaction_minute,
                   lockout_until_day = excluded.lockout_until_day,
                   lockout_until_minute = excluded.lockout_until_minute,
                   clear_the_air_required = excluded.clear_the_air_required,
                   clear_the_air_reason = excluded.clear_the_air_reason,
                   turn_updated = excluded.turn_updated,
                   updated_at = excluded.updated_at""",
            (
                sid,
                nid,
                eff_cur,
                eff_max,
                eff_state,
                eff_mood,
                eff_dc_mod,
                eff_block,
                eff_day,
                eff_min,
                eff_lock_day,
                eff_lock_min,
                eff_cta,
                eff_cta_reason,
                eff_turn,
                now,
            ),
        )
        return get_npc_social_composure(sid, nid, conn=c) or {}

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def set_clear_the_air_gate(
    session_id: int,
    npc_id: str,
    reason: str = "flaked_commitment",
    turn_updated: int = 0,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    existing = get_npc_social_composure(session_id, npc_id, conn=conn) or {}
    cur_mod = int(existing.get("mood_dc_mod", 0))
    return upsert_npc_social_composure(
        session_id,
        npc_id,
        mood="Upset",
        mood_dc_mod=max(cur_mod, 2),
        clear_the_air_required=1,
        clear_the_air_reason=str(reason or "flaked_commitment"),
        turn_updated=turn_updated if turn_updated else existing.get("turn_updated", 0),
        conn=conn,
    )


def clear_clear_the_air_gate(
    session_id: int,
    npc_id: str,
    *,
    mood: str = "Guarded",
    mood_dc_mod: int = 0,
    turn_updated: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    return upsert_npc_social_composure(
        session_id,
        npc_id,
        mood=mood,
        mood_dc_mod=mood_dc_mod,
        clear_the_air_required=0,
        clear_the_air_reason="",
        turn_updated=turn_updated,
        conn=conn,
    )


def get_character_social_daily(
    session_id: int,
    character_id: int,
    npc_id: str,
    current_day: int = 1,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    if not session_id or not npc_id:
        return None
    nid = canon_social_npc_id(npc_id)

    def _run(c: sqlite3.Connection) -> dict[str, Any] | None:
        row = c.execute(
            """SELECT * FROM character_social_daily
               WHERE session_id = ? AND character_id = ? AND npc_id = ? AND current_day = ?""",
            (int(session_id), int(character_id or 0), nid, int(current_day or 1)),
        ).fetchone()
        return dict(row) if row else None

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def get_character_social_daily_batch(
    session_id: int,
    character_id: int,
    current_day: int = 1,
    npc_ids: Iterable[str] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, dict[str, Any]]:
    if not session_id:
        return {}
    norm_ids = [canon_social_npc_id(x) for x in (npc_ids or []) if str(x or "").strip()]

    def _run(c: sqlite3.Connection) -> dict[str, dict[str, Any]]:
        if norm_ids:
            qmarks = ",".join("?" * len(norm_ids))
            rows = c.execute(
                f"""SELECT * FROM character_social_daily
                    WHERE session_id = ? AND character_id = ? AND current_day = ? AND npc_id IN ({qmarks})""",
                [int(session_id), int(character_id or 0), int(current_day or 1), *norm_ids],
            ).fetchall()
        else:
            rows = c.execute(
                """SELECT * FROM character_social_daily
                   WHERE session_id = ? AND character_id = ? AND current_day = ?""",
                (int(session_id), int(character_id or 0), int(current_day or 1)),
            ).fetchall()
        return {str(r["npc_id"]): dict(r) for r in rows}

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def upsert_character_social_daily(
    session_id: int,
    character_id: int,
    npc_id: str,
    current_day: int = 1,
    *,
    daily_affinity_earned: int | None = None,
    is_on_date: int | bool | None = None,
    gift_given_today: int | bool | None = None,
    confession_given_today: int | bool | None = None,
    turn_updated: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    sid = int(session_id)
    cid = int(character_id or 0)
    nid = canon_social_npc_id(npc_id)
    day = int(current_day or 1)
    now = time.time()

    def _run(c: sqlite3.Connection) -> dict[str, Any]:
        existing = get_character_social_daily(sid, cid, nid, current_day=day, conn=c) or {}
        eff_earned = int(daily_affinity_earned if daily_affinity_earned is not None else existing.get("daily_affinity_earned", 0))
        eff_date = int(bool(is_on_date)) if is_on_date is not None else int(existing.get("is_on_date", 0))
        eff_gift = int(bool(gift_given_today)) if gift_given_today is not None else int(existing.get("gift_given_today", 0))
        eff_conf = int(bool(confession_given_today)) if confession_given_today is not None else int(existing.get("confession_given_today", 0))
        eff_turn = int(turn_updated if turn_updated is not None else existing.get("turn_updated", 0))

        c.execute(
            """INSERT INTO character_social_daily (
                   session_id, character_id, npc_id, current_day,
                   daily_affinity_earned, is_on_date, gift_given_today, confession_given_today,
                   turn_updated, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id, character_id, npc_id, current_day) DO UPDATE SET
                   daily_affinity_earned = excluded.daily_affinity_earned,
                   is_on_date = excluded.is_on_date,
                   gift_given_today = excluded.gift_given_today,
                   confession_given_today = excluded.confession_given_today,
                   turn_updated = excluded.turn_updated,
                   updated_at = excluded.updated_at""",
            (sid, cid, nid, day, eff_earned, eff_date, eff_gift, eff_conf, eff_turn, now),
        )
        return get_character_social_daily(sid, cid, nid, current_day=day, conn=c) or {}

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def get_social_topic_states(
    session_id: int,
    character_id: int,
    npc_id: str,
    conn: sqlite3.Connection | None = None,
) -> dict[str, dict[str, Any]]:
    if not session_id or not npc_id:
        return {}
    nid = canon_social_npc_id(npc_id)

    def _run(c: sqlite3.Connection) -> dict[str, dict[str, Any]]:
        rows = c.execute(
            """SELECT * FROM social_topic_states
               WHERE session_id = ? AND character_id = ? AND npc_id = ?""",
            (int(session_id), int(character_id or 0), nid),
        ).fetchall()
        return {str(r["topic_id"]): dict(r) for r in rows}

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def get_social_topic_states_batch(
    session_id: int,
    character_id: int,
    npc_ids: Iterable[str] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    if not session_id:
        return {}
    norm_ids = [canon_social_npc_id(x) for x in (npc_ids or []) if str(x or "").strip()]

    def _run(c: sqlite3.Connection) -> dict[str, dict[str, dict[str, Any]]]:
        if norm_ids:
            qmarks = ",".join("?" * len(norm_ids))
            rows = c.execute(
                f"""SELECT * FROM social_topic_states
                    WHERE session_id = ? AND character_id = ? AND npc_id IN ({qmarks})""",
                [int(session_id), int(character_id or 0), *norm_ids],
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM social_topic_states WHERE session_id = ? AND character_id = ?",
                (int(session_id), int(character_id or 0)),
            ).fetchall()
        out: dict[str, dict[str, dict[str, Any]]] = {}
        for r in rows:
            d = dict(r)
            out.setdefault(str(d["npc_id"]), {})[str(d["topic_id"])] = d
        return out

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def upsert_social_topic_state(
    session_id: int,
    character_id: int,
    npc_id: str,
    topic_id: str,
    *,
    category: str | None = None,
    depth_tier: int | None = None,
    last_outcome: str | None = None,
    last_discussed_day: int | None = None,
    cooldown_until_day: int | None = None,
    cooldown_until_minute: int | None = None,
    last_venue_leaf: str | None = None,
    turn_updated: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    sid = int(session_id)
    cid = int(character_id or 0)
    nid = canon_social_npc_id(npc_id)
    tid = str(topic_id or "").strip()
    now = time.time()

    def _run(c: sqlite3.Connection) -> dict[str, Any]:
        row = c.execute(
            """SELECT * FROM social_topic_states
               WHERE session_id = ? AND character_id = ? AND npc_id = ? AND topic_id = ?""",
            (sid, cid, nid, tid),
        ).fetchone()
        existing = dict(row) if row else {}
        eff_cat = str(category if category is not None else existing.get("category", ""))
        eff_depth = max(1, min(3, int(depth_tier if depth_tier is not None else existing.get("depth_tier", 1))))
        eff_out = str(last_outcome if last_outcome is not None else existing.get("last_outcome", ""))
        eff_disc_day = int(last_discussed_day if last_discussed_day is not None else existing.get("last_discussed_day", 0))
        eff_cd_day = int(cooldown_until_day if cooldown_until_day is not None else existing.get("cooldown_until_day", 0))
        eff_cd_min = int(cooldown_until_minute if cooldown_until_minute is not None else existing.get("cooldown_until_minute", 0))
        eff_venue = str(last_venue_leaf if last_venue_leaf is not None else existing.get("last_venue_leaf", ""))
        eff_turn = int(turn_updated if turn_updated is not None else existing.get("turn_updated", 0))

        c.execute(
            """INSERT INTO social_topic_states (
                   session_id, character_id, npc_id, topic_id, category, depth_tier,
                   last_outcome, last_discussed_day, cooldown_until_day, cooldown_until_minute,
                   last_venue_leaf, turn_updated, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id, character_id, npc_id, topic_id) DO UPDATE SET
                   category = excluded.category,
                   depth_tier = excluded.depth_tier,
                   last_outcome = excluded.last_outcome,
                   last_discussed_day = excluded.last_discussed_day,
                   cooldown_until_day = excluded.cooldown_until_day,
                   cooldown_until_minute = excluded.cooldown_until_minute,
                   last_venue_leaf = excluded.last_venue_leaf,
                   turn_updated = excluded.turn_updated,
                   updated_at = excluded.updated_at""",
            (sid, cid, nid, tid, eff_cat, eff_depth, eff_out, eff_disc_day, eff_cd_day, eff_cd_min, eff_venue, eff_turn, now),
        )
        updated = c.execute(
            """SELECT * FROM social_topic_states
               WHERE session_id = ? AND character_id = ? AND npc_id = ? AND topic_id = ?""",
            (sid, cid, nid, tid),
        ).fetchone()
        return dict(updated) if updated else {}

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def record_contact_dossier_discoveries(
    session_id: int,
    npc_id: str,
    discoveries: Iterable[dict[str, Any]],
    *,
    character_ids: Iterable[int] | None = None,
    discovered_turn: int = 0,
    primary_character_id: int | None = None,
    discovery_source: str = "dialogue",
    conn: sqlite3.Connection | None = None,
) -> int:
    if not session_id or not npc_id:
        return 0
    sid = int(session_id)
    nid = canon_social_npc_id(npc_id)
    disc_list = [d for d in (discoveries or []) if isinstance(d, dict)]
    if not disc_list:
        return 0
    now = time.time()

    def _run(c: sqlite3.Connection) -> int:
        cids: list[int] = []
        for raw_cid in (character_ids or []):
            try:
                ic = int(raw_cid)
                if ic not in cids:
                    cids.append(ic)
            except (TypeError, ValueError):
                pass
        if not cids:
            if primary_character_id is not None:
                cids.append(int(primary_character_id))
            else:
                sr = c.execute("SELECT character_id FROM sessions WHERE id = ?", (sid,)).fetchone()
                cids.append(int(sr["character_id"] or 0) if sr else 0)

        prim_cid = int(primary_character_id) if primary_character_id is not None else cids[0]
        inserted = 0
        for cid in cids:
            eff_source = (
                "earshot_coop"
                if (discovery_source == "dialogue" and len(cids) > 1 and cid != prim_cid)
                else str(discovery_source or "dialogue")
            )
            for item in disc_list:
                f_cat = str(item.get("fact_category") or "").strip().lower()
                f_val = str(item.get("fact_value") or "").strip()
                f_key = str(item.get("fact_key") or "").strip().lower()
                if not f_cat or (not f_key and not f_val):
                    continue
                if not f_key:
                    f_key = f"{f_cat}:{f_val.lower()}"
                cur = c.execute(
                    """INSERT OR IGNORE INTO contact_dossier_discoveries (
                           session_id, character_id, npc_id, fact_category, fact_key,
                           fact_value, discovered_turn, discovery_source, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (sid, cid, nid, f_cat, f_key, f_val, int(discovered_turn or 0), eff_source, now),
                )
                inserted += int(cur.rowcount or 0)
        return inserted

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def get_contact_dossier_discoveries(
    session_id: int,
    character_id: int,
    npc_id: str,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    if not session_id or not npc_id:
        return []
    nid = canon_social_npc_id(npc_id)

    def _run(c: sqlite3.Connection) -> list[dict[str, Any]]:
        rows = c.execute(
            """SELECT * FROM contact_dossier_discoveries
               WHERE session_id = ? AND character_id IN (?, 0) AND npc_id = ?
               ORDER BY discovered_turn ASC, id ASC""",
            (int(session_id), int(character_id or 0), nid),
        ).fetchall()
        return [dict(r) for r in rows]

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def get_contact_dossier_discoveries_batch(
    session_id: int,
    character_id: int,
    npc_ids: Iterable[str] | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if not session_id:
        return {}
    norm_ids = [canon_social_npc_id(x) for x in (npc_ids or []) if str(x or "").strip()]

    def _run(c: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
        if norm_ids:
            qmarks = ",".join("?" * len(norm_ids))
            rows = c.execute(
                f"""SELECT * FROM contact_dossier_discoveries
                    WHERE session_id = ? AND character_id IN (?, 0) AND npc_id IN ({qmarks})
                    ORDER BY discovered_turn ASC, id ASC""",
                [int(session_id), int(character_id or 0), *norm_ids],
            ).fetchall()
        else:
            rows = c.execute(
                """SELECT * FROM contact_dossier_discoveries
                   WHERE session_id = ? AND character_id IN (?, 0)
                   ORDER BY discovered_turn ASC, id ASC""",
                (int(session_id), int(character_id or 0)),
            ).fetchall()
        out: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            d = dict(r)
            out.setdefault(str(d["npc_id"]), []).append(d)
        return out

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def backfill_exempt_and_legacy_contact_discoveries(
    conn: sqlite3.Connection,
    session_id: int | None = None,
    is_legacy_migration: bool = False,
) -> int:
    """Idempotently seeds contact_dossier_discoveries for kin, starting companions, romantic partners, and pre-v50 saves."""
    _ensure_social_v50_tables(conn)
    if session_id is not None:
        sess_rows = conn.execute(
            "SELECT id, character_id, party_npcs_json FROM sessions WHERE id = ?",
            (int(session_id),),
        ).fetchall()
    else:
        sess_rows = conn.execute("SELECT id, character_id, party_npcs_json FROM sessions").fetchall()

    total_inserted = 0
    for s_row in sess_rows:
        sid = int(s_row["id"])
        host_cid = int(s_row["character_id"] or 0)
        party_keys: set[str] = set()
        try:
            raw_party = json.loads(s_row["party_npcs_json"] or "[]")
            for p_entry in (raw_party if isinstance(raw_party, list) else []):
                p_name = p_entry.get("name") or p_entry.get("npc_id") if isinstance(p_entry, dict) else p_entry
                if p_name:
                    party_keys.add(canon_social_npc_id(str(p_name)))
        except Exception:
            pass

        tie_rows = conn.execute(
            "SELECT person_a_key, person_b_key, tie_type FROM social_ties WHERE session_id = ? AND status = 'active'",
            (sid,),
        ).fetchall()
        kin_keys: set[str] = set()
        rom_keys: set[str] = set()
        for tr in tie_rows:
            a_k = str(tr["person_a_key"] or "").strip()
            b_k = str(tr["person_b_key"] or "").strip()
            t_type = str(tr["tie_type"] or "").strip().lower()
            other_k = b_k if a_k == "player" else (a_k if b_k == "player" else "")
            if not other_k:
                continue
            canon_other = canon_social_npc_id(other_k)
            if t_type in _KIN_TIE_TYPES:
                kin_keys.add(canon_other)
            if t_type in _ROMANTIC_TIE_TYPES:
                rom_keys.add(canon_other)

        c_rows = conn.execute("SELECT * FROM contacts WHERE session_id = ?", (sid,)).fetchall()
        for cr in c_rows:
            cd = dict(cr)
            cid = int(cd.get("character_id") or host_cid or 0)
            nid = canon_social_npc_id(cd.get("npc_id") or cd.get("name") or "")
            if not nid:
                continue
            try:
                b_info = json.loads(cd.get("basic_info_json") or "{}")
                if not isinstance(b_info, dict):
                    b_info = {}
            except Exception:
                b_info = {}
            try:
                traits = json.loads(cd.get("unlocked_traits_json") or "[]")
                if not isinstance(traits, list):
                    traits = []
            except Exception:
                traits = []
            try:
                prefs = json.loads(cd.get("preferences_json") or "{}")
            except Exception:
                prefs = {}

            likes: list[str] = []
            dislikes: list[str] = []
            if isinstance(prefs, dict):
                likes = [str(x).strip() for x in (prefs.get("likes") or []) if str(x).strip()]
                dislikes = [str(x).strip() for x in (prefs.get("dislikes") or []) if str(x).strip()]
            elif isinstance(prefs, list) and prefs:
                try:
                    import mechanics.social.persona as _persona
                    dislike_kws = getattr(_persona, "DISLIKE_KEYWORDS", ("dislike", "dislikes", "hate", "hates", "avoid", "avoids"))
                    for raw_p in prefs:
                        sp = str(raw_p or "").strip().lstrip("-*•· ").rstrip(".")
                        if not sp:
                            continue
                        if any(kw in sp.lower() for kw in dislike_kws):
                            fmt = _persona.format_preference_phrase(sp, is_dislike=True)
                            if fmt and fmt.lower() not in (d.lower() for d in dislikes):
                                dislikes.append(fmt)
                        else:
                            fmt = _persona.format_preference_phrase(sp, is_dislike=False)
                            if fmt and fmt.lower() not in (l.lower() for l in likes):
                                likes.append(fmt)
                except Exception:
                    for raw_p in prefs:
                        sp = str(raw_p or "").strip()
                        if not sp:
                            continue
                        if sp.lower().startswith("dislike"):
                            dislikes.append(sp.split(":", 1)[-1].strip() if ":" in sp else sp)
                        else:
                            likes.append(sp.split(":", 1)[-1].strip() if ":" in sp else sp)

            rel_role = str(b_info.get("relationship_to_player") or "").strip().lower()
            is_kin = (
                nid in kin_keys
                or bool(b_info.get("is_player_kin") or b_info.get("is_household_member"))
                or any(tok in rel_role for tok in ("sister", "brother", "mother", "father", "sibling", "parent", "cousin", "spouse", "wife", "husband"))
            )
            is_companion = nid in party_keys or bool(b_info.get("is_starting_companion"))
            is_romance = (
                nid in rom_keys
                or (str(cd.get("track") or "").lower() == "romantic" and int(cd.get("relationship_score") or 0) >= 200)
            )

            exempt_source = ""
            if is_romance:
                exempt_source = "romance"
            elif is_kin:
                exempt_source = "kin"
            elif is_companion:
                exempt_source = "companion"

            if exempt_source or is_legacy_migration:
                src = exempt_source or "legacy_save"
                items_to_record: list[dict[str, str]] = []
                for t_val in traits:
                    tv = str(t_val or "").strip()
                    if tv:
                        items_to_record.append({"fact_category": "trait", "fact_key": f"trait:{tv.lower()}", "fact_value": tv})
                for l_val in likes:
                    items_to_record.append({"fact_category": "like", "fact_key": f"like:{l_val.lower()}", "fact_value": l_val})
                for d_val in dislikes:
                    items_to_record.append({"fact_category": "dislike", "fact_key": f"dislike:{d_val.lower()}", "fact_value": d_val})
                if exempt_source:
                    items_to_record.append({"fact_category": "schedule", "fact_key": "schedule:all", "fact_value": "known"})
                    items_to_record.append({"fact_category": "trait", "fact_key": "trait:*", "fact_value": "*"})
                    items_to_record.append({"fact_category": "like", "fact_key": "like:*", "fact_value": "*"})
                    items_to_record.append({"fact_category": "dislike", "fact_key": "dislike:*", "fact_value": "*"})
                if exempt_source == "romance":
                    items_to_record.append({"fact_category": "intimate", "fact_key": "intimate:*", "fact_value": "*"})
                if items_to_record:
                    total_inserted += record_contact_dossier_discoveries(
                        sid,
                        nid,
                        items_to_record,
                        character_ids=[cid],
                        discovered_turn=0,
                        discovery_source=src,
                        conn=conn,
                    )
    return total_inserted


def snapshot_session_social_state_for_turn(
    session_id: int,
    turn_number: int,
    conn: sqlite3.Connection | None = None,
) -> None:
    if not session_id:
        return
    sid = int(session_id)
    t_num = int(turn_number)
    now = time.time()

    def _run(c: sqlite3.Connection) -> None:
        _ensure_social_v50_tables(c)
        comp_rows = [
            {k: v for k, v in dict(r).items() if k != "id"}
            for r in c.execute("SELECT * FROM npc_social_composure WHERE session_id = ?", (sid,)).fetchall()
        ]
        daily_rows = [
            {k: v for k, v in dict(r).items() if k != "id"}
            for r in c.execute("SELECT * FROM character_social_daily WHERE session_id = ?", (sid,)).fetchall()
        ]
        topic_rows = [
            {k: v for k, v in dict(r).items() if k != "id"}
            for r in c.execute("SELECT * FROM social_topic_states WHERE session_id = ?", (sid,)).fetchall()
        ]
        c.execute(
            """INSERT INTO social_turn_snapshots (
                   session_id, turn_number, composure_json, daily_json, topic_states_json, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id, turn_number) DO UPDATE SET
                   composure_json = excluded.composure_json,
                   daily_json = excluded.daily_json,
                   topic_states_json = excluded.topic_states_json,
                   updated_at = excluded.updated_at""",
            (
                sid,
                t_num,
                json.dumps(comp_rows, default=str),
                json.dumps(daily_rows, default=str),
                json.dumps(topic_rows, default=str),
                now,
            ),
        )

    if conn is not None:
        _run(conn)
    else:
        with get_conn() as c:
            _run(c)


def rollback_social_pacing_state_after_turn(
    session_id: int,
    turn_number: int,
    conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    if not session_id:
        return {"discoveries_deleted": 0, "composure_restored": 0, "daily_restored": 0, "topics_restored": 0}
    sid = int(session_id)
    t_num = int(turn_number)

    def _run(c: sqlite3.Connection) -> dict[str, int]:
        _ensure_social_v50_tables(c)
        disc_cur = c.execute(
            "DELETE FROM contact_dossier_discoveries WHERE session_id = ? AND discovered_turn > ?",
            (sid, t_num),
        )
        disc_deleted = int(disc_cur.rowcount or 0)

        snap_row = c.execute(
            """SELECT turn_number, composure_json, daily_json, topic_states_json
               FROM social_turn_snapshots
               WHERE session_id = ? AND turn_number <= ?
               ORDER BY turn_number DESC
               LIMIT 1""",
            (sid, t_num),
        ).fetchone()
        pruned_cur = c.execute(
            "DELETE FROM social_turn_snapshots WHERE session_id = ? AND turn_number > ?",
            (sid, t_num),
        )
        pruned_future = int(pruned_cur.rowcount or 0)

        if snap_row is None:
            if pruned_future > 0 or t_num <= 0:
                c.execute("DELETE FROM npc_social_composure WHERE session_id = ? AND turn_updated > ?", (sid, t_num))
                c.execute("DELETE FROM character_social_daily WHERE session_id = ? AND turn_updated > ?", (sid, t_num))
                c.execute("DELETE FROM social_topic_states WHERE session_id = ? AND turn_updated > ?", (sid, t_num))
            return {
                "discoveries_deleted": disc_deleted,
                "composure_restored": 0,
                "daily_restored": 0,
                "topics_restored": 0,
            }

        def _restore_table(table_name: str, raw_json: str) -> int:
            try:
                items = json.loads(raw_json or "[]")
            except Exception:
                items = []
            valid_cols = {
                r["name"] if isinstance(r, sqlite3.Row) else r[1]
                for r in c.execute(f"PRAGMA table_info({table_name})").fetchall()
            }
            c.execute(f"DELETE FROM {table_name} WHERE session_id = ?", (sid,))
            count = 0
            for item in (items if isinstance(items, list) else []):
                if not isinstance(item, dict):
                    continue
                row_dict = {
                    k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
                    for k, v in item.items()
                    if k in valid_cols and k not in ("id", "session_id")
                }
                if not row_dict:
                    continue
                row_dict["session_id"] = sid
                cols_sql = ",".join(row_dict.keys())
                qmarks = ",".join("?" * len(row_dict))
                c.execute(f"INSERT INTO {table_name} ({cols_sql}) VALUES ({qmarks})", list(row_dict.values()))
                count += 1
            return count

        comp_cnt = _restore_table("npc_social_composure", snap_row["composure_json"])
        daily_cnt = _restore_table("character_social_daily", snap_row["daily_json"])
        topic_cnt = _restore_table("social_topic_states", snap_row["topic_states_json"])
        return {
            "discoveries_deleted": disc_deleted,
            "composure_restored": comp_cnt,
            "daily_restored": daily_cnt,
            "topics_restored": topic_cnt,
        }

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)



def get_player_fow_exemption_sets(session_id: int) -> dict[str, set[str]]:
    """Returns canonical NPC keys exempt from Fog-of-War via party membership, kinship, or active romance."""
    party_npc_keys: set[str] = set()
    kin_npc_keys: set[str] = set()
    romantic_npc_keys: set[str] = set()
    if not session_id:
        return {
            "party_npc_keys": party_npc_keys,
            "kin_npc_keys": kin_npc_keys,
            "romantic_npc_keys": romantic_npc_keys,
        }
    sid = int(session_id)
    import mechanics.social.relationship_graph as rg

    with get_conn() as conn:
        try:
            s_row = conn.execute("SELECT party_npcs_json FROM sessions WHERE id = ?", (sid,)).fetchone()
            if s_row and s_row["party_npcs_json"]:
                for p in json.loads(s_row["party_npcs_json"]):
                    pn = p.get("name") if isinstance(p, dict) else p
                    if pn:
                        ck = canon_social_npc_id(str(pn))
                        if ck:
                            party_npc_keys.add(ck)
        except Exception:
            pass
        try:
            t_rows = conn.execute(
                """SELECT person_a_key, person_b_key, tie_type FROM social_ties
                   WHERE session_id = ? AND status = 'active'
                     AND (person_a_key = 'player' OR person_b_key = 'player')""",
                (sid,),
            ).fetchall()
            for tr in t_rows:
                other_raw = tr["person_b_key"] if tr["person_a_key"] == "player" else tr["person_a_key"]
                resolved_nid = rg.resolve_npc_id_for_person(sid, other_raw, conn=conn)
                other_key = canon_social_npc_id(resolved_nid or other_raw)
                if not other_key:
                    continue
                tt = str(tr["tie_type"] or "").lower()
                if tt in rg.ROMANTIC_TYPES:
                    romantic_npc_keys.add(other_key)
                elif tt in _KIN_TIE_TYPES:
                    kin_npc_keys.add(other_key)
        except Exception:
            pass
    return {
        "party_npc_keys": party_npc_keys,
        "kin_npc_keys": kin_npc_keys,
        "romantic_npc_keys": romantic_npc_keys,
    }
