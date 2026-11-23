"""Account-wide Folklore Encyclopedia progression and recognition queries."""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Optional, Sequence

from ..core import get_conn
from .profiles import _deserialize_json_field, _effective_session_turn

_FOLKLORE_STAGE_RANK = {
    "undiscovered": 0,
    "sighted": 1,
    "verified": 2,
    "contained": 3,
}


def get_user_folklore_codex(
    user_id: int,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, dict[str, Any]]:
    """Returns account-wide Folklore Encyclopedia unlock rows keyed by `codex_id`."""
    if not user_id or int(user_id) <= 0:
        return {}

    def _run(c: sqlite3.Connection) -> dict[str, dict[str, Any]]:
        rows = c.execute(
            "SELECT * FROM user_folklore_codex WHERE user_id = ?",
            (int(user_id),),
        ).fetchall()
        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            cid = str(r["codex_id"] or "").strip()
            if cid:
                out[cid] = dict(r)
        return out

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def get_users_folklore_codex_batch(
    user_ids: Sequence[int],
    conn: Optional[sqlite3.Connection] = None,
) -> dict[int, dict[str, dict[str, Any]]]:
    """Returns account-wide Folklore Encyclopedia unlock rows for multiple users in a single `WHERE user_id IN (...)` query."""
    uniq_uids: list[int] = []
    seen_u: set[int] = set()
    for u in (user_ids or ()):
        try:
            uid_val = int(u)
        except (TypeError, ValueError):
            continue
        if uid_val > 0 and uid_val not in seen_u:
            seen_u.add(uid_val)
            uniq_uids.append(uid_val)
    if not uniq_uids:
        return {}

    def _run(c: sqlite3.Connection) -> dict[int, dict[str, dict[str, Any]]]:
        out: dict[int, dict[str, dict[str, Any]]] = {uid: {} for uid in uniq_uids}
        placeholders = ",".join("?" for _ in uniq_uids)
        rows = c.execute(
            f"SELECT * FROM user_folklore_codex WHERE user_id IN ({placeholders})",
            tuple(uniq_uids),
        ).fetchall()
        for r in rows:
            uid_r = int(r["user_id"] or 0)
            cid = str(r["codex_id"] or "").strip()
            if uid_r in out and cid:
                out[uid_r][cid] = dict(r)
        return out

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def record_folklore_codex_progress(
    user_ids: int | list[int] | tuple[int, ...],
    codex_id: str,
    stage: str = "sighted",
    session_id: Optional[int] = None,
    turn_number: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    """
    Monotonically advances account-wide Folklore Encyclopedia progress (`sighted` -> `verified` -> `contained`)
    for one or more `user_ids`. Persists permanently across playthroughs and rollbacks, while recording
    first-sighting session/turn provenance so rewound future sightings in the same session do not leak `-1` clue bonuses.
    """
    cid = str(codex_id or "").strip()
    norm_stage = str(stage or "sighted").strip().lower()
    if norm_stage not in ("sighted", "verified", "contained"):
        norm_stage = "sighted"
    if isinstance(user_ids, int):
        uid_list = [user_ids] if user_ids > 0 else []
    else:
        uid_list = [int(u) for u in (user_ids or []) if u and int(u) > 0]
    if not cid or not uid_list:
        return {"updated": False, "codex_id": cid, "stage": norm_stage}

    now = time.time()
    target_rank = _FOLKLORE_STAGE_RANK[norm_stage]

    def _resolve_uid_session_turn(c: sqlite3.Connection, uid: int) -> tuple[Optional[int], int]:
        sid_val = int(session_id) if session_id else None
        if not sid_val:
            ch_row = c.execute(
                "SELECT active_session_id FROM characters WHERE user_id = ? AND is_active = 1 LIMIT 1",
                (uid,),
            ).fetchone()
            if ch_row and ch_row["active_session_id"]:
                sid_val = int(ch_row["active_session_id"])
        if turn_number is not None:
            return sid_val, int(turn_number)
        if sid_val:
            s_row = c.execute(
                "SELECT turn_count, last_turn_snapshot_json FROM sessions WHERE id = ?",
                (sid_val,),
            ).fetchone()
            if s_row:
                return sid_val, _effective_session_turn(s_row)
        return sid_val, 0

    def _stamp_session_sighting_meta(
        c: sqlite3.Connection,
        sid_val: Optional[int],
        uid: int,
        first_t: int,
        verified_t: Optional[int],
    ) -> None:
        if not sid_val:
            return
        s_row = c.execute("SELECT extra_json FROM sessions WHERE id = ?", (sid_val,)).fetchone()
        if not s_row:
            return
        extra = _deserialize_json_field(s_row["extra_json"], {})
        if not isinstance(extra, dict):
            extra = {}
        fs_map = dict(extra.get("_codex_first_sightings") or {})
        key = f"{uid}:{cid}"
        prev = dict(fs_map.get(key) or {})
        entry: dict[str, Any] = {
            "first_turn": int(prev["first_turn"]) if prev.get("first_turn") is not None else int(first_t),
        }
        if prev.get("verified_turn") is not None:
            entry["verified_turn"] = int(prev["verified_turn"])
        elif verified_t is not None:
            entry["verified_turn"] = int(verified_t)
        fs_map[key] = entry
        extra["_codex_first_sightings"] = fs_map
        c.execute(
            "UPDATE sessions SET extra_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(extra), now, sid_val),
        )

    def _run(c: sqlite3.Connection) -> dict[str, Any]:
        col_names = {r["name"] for r in c.execute("PRAGMA table_info(user_folklore_codex)").fetchall()}
        has_prov_cols = "first_session_id" in col_names and "first_turn" in col_names
        final_stage = norm_stage
        for uid in dict.fromkeys(uid_list):
            existing = c.execute(
                "SELECT * FROM user_folklore_codex WHERE user_id = ? AND codex_id = ?",
                (uid, cid),
            ).fetchone()
            sid_eff, t_eff = _resolve_uid_session_turn(c, uid)
            if not existing:
                t_sight = 1
                t_cont = 1 if norm_stage == "contained" else 0
                if has_prov_cols:
                    c.execute(
                        """INSERT INTO user_folklore_codex (
                            user_id, codex_id, unlock_stage, times_sighted, times_contained,
                            first_discovered_at, updated_at, first_session_id, first_turn
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (uid, cid, norm_stage, t_sight, t_cont, now, now, sid_eff, t_eff),
                    )
                else:
                    c.execute(
                        """INSERT INTO user_folklore_codex (
                            user_id, codex_id, unlock_stage, times_sighted, times_contained,
                            first_discovered_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (uid, cid, norm_stage, t_sight, t_cont, now, now),
                    )
                _stamp_session_sighting_meta(
                    c,
                    sid_eff,
                    uid,
                    first_t=t_eff,
                    verified_t=t_eff if target_rank >= 2 else None,
                )
            else:
                cur_stage = str(existing["unlock_stage"] or "sighted").strip().lower()
                cur_rank = _FOLKLORE_STAGE_RANK.get(cur_stage, 1)
                eff_stage = norm_stage if target_rank > cur_rank else cur_stage
                final_stage = eff_stage
                t_sight = int(existing["times_sighted"] or 1) + (1 if norm_stage == "sighted" else 0)
                t_cont = int(existing["times_contained"] or 0) + (1 if norm_stage == "contained" else 0)
                c.execute(
                    """UPDATE user_folklore_codex
                       SET unlock_stage = ?, times_sighted = ?, times_contained = ?, updated_at = ?
                       WHERE user_id = ? AND codex_id = ?""",
                    (eff_stage, t_sight, t_cont, now, uid, cid),
                )
                if t_sight <= 1 and cur_rank < 2 and target_rank >= 2:
                    _stamp_session_sighting_meta(
                        c,
                        sid_eff,
                        uid,
                        first_t=int(existing["first_turn"]) if (has_prov_cols and existing["first_turn"] is not None) else t_eff,
                        verified_t=t_eff,
                    )
        return {"updated": True, "codex_id": cid, "stage": final_stage}

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def user_has_folklore_recognition(
    user_ids: int | list[int] | tuple[int, ...],
    codex_id: str,
    session_id: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> bool:
    """
    Returns True if any user in `user_ids` has already reached `verified` or `contained`
    for `codex_id` in their account-wide Folklore Encyclopedia (granting -1 Stage 1 clue recognition),
    excluding single-sighting unlocks whose first discovery occurred on a later rewound turn of the same session.
    """
    cid = str(codex_id or "").strip()
    if isinstance(user_ids, int):
        uid_list = [user_ids] if user_ids > 0 else []
    else:
        uid_list = [int(u) for u in (user_ids or []) if u and int(u) > 0]
    if not cid or not uid_list:
        return False

    def _run(c: sqlite3.Connection) -> bool:
        uniq_uids = list(dict.fromkeys(uid_list))
        placeholders = ",".join("?" for _ in uniq_uids)
        rows = c.execute(
            f"SELECT * FROM user_folklore_codex WHERE user_id IN ({placeholders}) AND codex_id = ?",
            (*uniq_uids, cid),
        ).fetchall()
        for r in rows:
            uid = int(r["user_id"] or 0)
            st = str(r["unlock_stage"] or "").strip().lower()
            if _FOLKLORE_STAGE_RANK.get(st, 0) < 2:
                continue
            t_sight = int(r["times_sighted"] or 0)
            if t_sight > 1:
                return True

            # Single-sighting check: gate bonus if first sighted/verified on a later rewound turn of this session
            check_sid = int(session_id) if session_id else None
            if not check_sid:
                ch_row = c.execute(
                    "SELECT active_session_id FROM characters WHERE user_id = ? AND is_active = 1 LIMIT 1",
                    (uid,),
                ).fetchone()
                if ch_row and ch_row["active_session_id"]:
                    check_sid = int(ch_row["active_session_id"])

            if check_sid:
                s_row = c.execute(
                    "SELECT turn_count, last_turn_snapshot_json, extra_json FROM sessions WHERE id = ?",
                    (check_sid,),
                ).fetchone()
                if s_row:
                    cur_t = _effective_session_turn(s_row)
                    s_extra = _deserialize_json_field(s_row["extra_json"], {})
                    origin_sids: set[int] = {int(check_sid)}
                    if isinstance(s_extra, dict):
                        for _osid in (s_extra.get("_origin_session_ids") or []):
                            try:
                                origin_sids.add(int(_osid))
                            except (TypeError, ValueError):
                                pass
                    r_keys = set(r.keys())
                    if "first_session_id" in r_keys and "first_turn" in r_keys:
                        f_sid = r["first_session_id"]
                        f_turn = r["first_turn"]
                        if f_sid is not None and int(f_sid) in origin_sids and f_turn is not None and int(f_turn) > cur_t:
                            continue
                    if isinstance(s_extra, dict):
                        fs_meta = (s_extra.get("_codex_first_sightings") or {}).get(f"{uid}:{cid}")
                        if isinstance(fs_meta, dict):
                            if fs_meta.get("first_turn") is not None and int(fs_meta["first_turn"]) > cur_t:
                                continue
                            if fs_meta.get("verified_turn") is not None and int(fs_meta["verified_turn"]) > cur_t:
                                continue
                        rw_turns = s_extra.get("_rewound_codex_first_turns") or {}
                        if cid in rw_turns and int(rw_turns[cid] or 0) > cur_t:
                            continue
                        rel_fl_rows = []
                        try:
                            rel_fl_rows = c.execute(
                                "SELECT stage FROM session_anomaly_records WHERE session_id = ? AND record_type = 'field_log' AND codex_id = ?",
                                (check_sid, cid),
                            ).fetchall()
                        except sqlite3.OperationalError:
                            rel_fl_rows = []
                        if rel_fl_rows:
                            max_fl_rank = max(
                                (_FOLKLORE_STAGE_RANK.get(str(rr["stage"] or "sighted").strip().lower(), 0) for rr in rel_fl_rows),
                                default=0,
                            )
                            if max_fl_rank < 2 and (
                                ("first_session_id" in r_keys and r["first_session_id"] is not None and int(r["first_session_id"]) in origin_sids)
                                or isinstance(fs_meta, dict)
                            ):
                                continue
                            return True
                        matching_leg_fl = [
                            fl_it for fl_it in (s_extra.get("anomaly_field_log") or [])
                            if isinstance(fl_it, dict) and str(fl_it.get("codex_id") or "") == cid
                        ]
                        if matching_leg_fl:
                            max_leg_rank = max(
                                (_FOLKLORE_STAGE_RANK.get(str(fl_it.get("stage") or "sighted").strip().lower(), 0) for fl_it in matching_leg_fl),
                                default=0,
                            )
                            if max_leg_rank < 2 and (
                                ("first_session_id" in r_keys and r["first_session_id"] is not None and int(r["first_session_id"]) in origin_sids)
                                or isinstance(fs_meta, dict)
                            ):
                                continue
                        return True
            return True
        return False

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)
