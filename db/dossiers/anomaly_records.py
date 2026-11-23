"""Session-scoped anomaly records, Field Log lifecycle, cooldowns, and turn rollback."""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Optional

from ..core import get_conn
from .folklore import _FOLKLORE_STAGE_RANK
from .profiles import _deserialize_json_field, _effective_session_turn

SESSION_ANOMALY_KEY_TO_RECORD_TYPE: dict[str, str] = {
    "anomaly_field_log": "field_log",
    "anomalous_vault_requisitions": "vault_requisition",
    "anomalous_vault_log": "vault_log",
    "contained_anomalies_log": "contained_log",
}
_RECORD_TYPE_TO_SESSION_ANOMALY_KEY: dict[str, str] = {
    v: k for k, v in SESSION_ANOMALY_KEY_TO_RECORD_TYPE.items()
}


def _extract_anomaly_record_columns(record_type: str, item: dict[str, Any]) -> tuple[str, str, str, int, int, str]:
    """Derives `(entity_key, codex_id, stage, first_turn, turn_updated, payload_json)` for a `session_anomaly_records` row."""
    if record_type == "field_log":
        entity_key = str(item.get("blueprint_id") or item.get("codex_id") or item.get("name") or "").strip()
    else:
        entity_key = str(
            item.get("blueprint_id")
            or item.get("requisition_id")
            or item.get("item_id")
            or item.get("codex_id")
            or item.get("name")
            or ""
        ).strip()
    codex_id = str(item.get("codex_id") or "").strip()
    default_stage = "contained" if record_type == "contained_log" else "sighted"
    stage = str(item.get("stage") or item.get("status") or default_stage).strip().lower() or default_stage
    first_turn = 0
    for tk in ("first_turn", "turn_captured", "turn"):
        if item.get(tk) is not None:
            try:
                first_turn = int(item[tk])
                break
            except (TypeError, ValueError):
                continue
    turn_updated = first_turn
    if item.get("turn_updated") is not None:
        try:
            turn_updated = int(item["turn_updated"])
        except (TypeError, ValueError):
            turn_updated = first_turn
    payload_json = json.dumps(item, default=str)
    return entity_key, codex_id, stage, first_turn, turn_updated, payload_json


def get_session_anomaly_records(
    session_id: int,
    record_type: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> list[dict[str, Any]]:
    """Returns deserialized `payload_json` dicts for `session_id` (optionally filtered by `record_type`) ordered by insertion."""
    if not session_id:
        return []

    def _run(c: sqlite3.Connection) -> list[dict[str, Any]]:
        try:
            if record_type:
                rows = c.execute(
                    "SELECT payload_json FROM session_anomaly_records WHERE session_id = ? AND record_type = ? ORDER BY id ASC",
                    (int(session_id), str(record_type)),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT payload_json FROM session_anomaly_records WHERE session_id = ? ORDER BY id ASC",
                    (int(session_id),),
                ).fetchall()
        except sqlite3.OperationalError as e:
            if "no such table" in str(e).lower():
                return []
            raise
        out: list[dict[str, Any]] = []
        for r in rows:
            parsed = _deserialize_json_field(r["payload_json"], None)
            if isinstance(parsed, dict):
                out.append(parsed)
        return out

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def hydrate_session_anomaly_records(
    session_id: int,
    session_dict: dict[str, Any],
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    """Hydrates `anomaly_field_log`, `anomalous_vault_requisitions`, `anomalous_vault_log`, and `contained_anomalies_log` onto `session_dict`."""
    if not session_id or not isinstance(session_dict, dict):
        return session_dict

    def _run(c: sqlite3.Connection) -> dict[str, Any]:
        try:
            rows = c.execute(
                "SELECT record_type, payload_json FROM session_anomaly_records WHERE session_id = ? ORDER BY id ASC",
                (int(session_id),),
            ).fetchall()
        except sqlite3.OperationalError as e:
            if "no such table" in str(e).lower():
                return session_dict
            raise
        by_type: dict[str, list[dict[str, Any]]] = {rt: [] for rt in _RECORD_TYPE_TO_SESSION_ANOMALY_KEY}
        for r in rows:
            rt = str(r["record_type"] or "")
            if rt in by_type:
                parsed = _deserialize_json_field(r["payload_json"], None)
                if isinstance(parsed, dict):
                    by_type[rt].append(parsed)
        for extra_key, rt in SESSION_ANOMALY_KEY_TO_RECORD_TYPE.items():
            if by_type[rt]:
                session_dict[extra_key] = by_type[rt]
            elif extra_key in session_dict and not isinstance(session_dict[extra_key], list):
                session_dict.pop(extra_key, None)
        return session_dict

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def sync_session_anomaly_records_from_extra(
    session_id: int,
    extra_update: dict[str, Any],
    conn: Optional[sqlite3.Connection] = None,
) -> bool:
    """Synchronizes any of the 4 session anomaly keys passed in `extra_update` into `session_anomaly_records`."""
    if not session_id or not isinstance(extra_update, dict):
        return False
    present_keys = [k for k in SESSION_ANOMALY_KEY_TO_RECORD_TYPE if k in extra_update]
    if not present_keys:
        return False

    now = time.time()

    def _run(c: sqlite3.Connection) -> bool:
        try:
            c.execute("SELECT 1 FROM session_anomaly_records LIMIT 1").fetchall()
        except sqlite3.OperationalError as e:
            if "no such table" in str(e).lower():
                return False
            raise

        for extra_key in present_keys:
            rtype = SESSION_ANOMALY_KEY_TO_RECORD_TYPE[extra_key]
            val = extra_update.get(extra_key)
            c.execute(
                "DELETE FROM session_anomaly_records WHERE session_id = ? AND record_type = ?",
                (int(session_id), rtype),
            )
            if not isinstance(val, list) or not val:
                continue
            items_to_insert: list[dict[str, Any]] = [dict(it) for it in val if isinstance(it, dict)]
            if rtype == "field_log":
                deduped_fl: list[dict[str, Any]] = []
                idx_by_key: dict[str, int] = {}
                for it in items_to_insert:
                    ek, *_ = _extract_anomaly_record_columns(rtype, it)
                    if ek and ek in idx_by_key:
                        deduped_fl[idx_by_key[ek]] = it
                    else:
                        if ek:
                            idx_by_key[ek] = len(deduped_fl)
                        deduped_fl.append(it)
                items_to_insert = deduped_fl
            for it in items_to_insert:
                ek, cid, stg, f_turn, t_upd, p_json = _extract_anomaly_record_columns(rtype, it)
                c.execute(
                    """INSERT INTO session_anomaly_records (
                        session_id, record_type, entity_key, codex_id, stage,
                        first_turn, turn_updated, payload_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (int(session_id), rtype, ek, cid, stg, f_turn, t_upd, p_json, now, now),
                )
        return True

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def record_session_anomaly_field_log(
    session_id: int,
    blueprint: dict[str, Any],
    stage: str = "sighted",
    turn_number: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
    *,
    location: str = "",
    resolution_method: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Records or advances a session-scoped Field Log entry in `session_anomaly_records`
    with turn-stamped `stage_history` so mid-session turn rollbacks revert cleanly.
    """
    if not session_id or not isinstance(blueprint, dict):
        return {}
    norm_stage = str(stage or "sighted").strip().lower()
    if norm_stage not in ("sighted", "verified", "contained"):
        norm_stage = "sighted"
    bp_id = str(blueprint.get("blueprint_id") or blueprint.get("codex_id") or blueprint.get("name") or "").strip()
    if not bp_id:
        return {}

    def _run(c: sqlite3.Connection) -> dict[str, Any]:
        row = c.execute(
            "SELECT turn_count, extra_json, last_turn_snapshot_json FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return {}
        now = time.time()
        t_cur = _effective_session_turn(row, turn_number)
        extra = _deserialize_json_field(row["extra_json"], {})
        if not isinstance(extra, dict):
            extra = {}

        # Migrate any unmigrated legacy extra_json anomaly lists on first touch
        legacy_keys_present = [k for k in SESSION_ANOMALY_KEY_TO_RECORD_TYPE if k in extra]
        if legacy_keys_present:
            patch_to_sync: dict[str, Any] = {}
            for k in legacy_keys_present:
                rtype_k = SESSION_ANOMALY_KEY_TO_RECORD_TYPE[k]
                if isinstance(extra.get(k), list) and extra[k]:
                    existing_cnt = c.execute(
                        "SELECT COUNT(*) FROM session_anomaly_records WHERE session_id = ? AND record_type = ?",
                        (int(session_id), rtype_k),
                    ).fetchone()[0]
                    if not existing_cnt:
                        patch_to_sync[k] = extra[k]
                extra.pop(k, None)
            if patch_to_sync:
                sync_session_anomaly_records_from_extra(int(session_id), patch_to_sync, conn=c)
            c.execute(
                "UPDATE sessions SET extra_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(extra, default=str), now, session_id),
            )

        codex_id = str(blueprint.get("codex_id") or "").strip()
        existing_row = c.execute(
            """SELECT id, entity_key, payload_json FROM session_anomaly_records
               WHERE session_id = ? AND record_type = 'field_log'
                 AND (
                     entity_key = ?
                     OR (codex_id != '' AND codex_id = ? AND (? = codex_id OR entity_key = codex_id))
                 )
               ORDER BY CASE WHEN entity_key = ? THEN 0 ELSE 1 END, id DESC
               LIMIT 1""",
            (int(session_id), bp_id, codex_id, bp_id, bp_id),
        ).fetchone()
        is_disguised = bool((blueprint.get("disguise_state") or {}).get("is_disguised")) and norm_stage == "sighted"
        pub_name = (
            str((blueprint.get("disguise_state") or {}).get("disguise_alias") or blueprint.get("name") or "Unknown Anomaly")
            if is_disguised
            else str(blueprint.get("canonical_name") or blueprint.get("name") or blueprint.get("entity_name") or "Unknown Anomaly")
        )

        if existing_row is None:
            entry = {
                "blueprint_id": bp_id,
                "codex_id": codex_id,
                "is_canonical_folklore": bool(blueprint.get("is_canonical_folklore") or codex_id),
                "name": pub_name,
                "true_name": str(blueprint.get("canonical_name") or blueprint.get("name") or pub_name),
                "type": str(blueprint.get("type") or "entity"),
                "form": str(blueprint.get("form") or ""),
                "form_label": str(blueprint.get("form_label") or "Manifestation"),
                "tradition": str(blueprint.get("folklore_tradition") or "Procedural Anomaly"),
                "primary_element": str(blueprint.get("primary_element") or "aether"),
                "sensory_omen": str(blueprint.get("sensory_omen") or ""),
                "taboo_rule": str(blueprint.get("taboo_rule") or ""),
                "containment_protocol": str(blueprint.get("containment_protocol") or ""),
                "weaknesses": list(blueprint.get("weaknesses") or []),
                "resistances": list(blueprint.get("resistances") or []),
                "stage": norm_stage,
                "status": norm_stage,
                "is_disguised": is_disguised,
                "public_name": pub_name,
                "location": str(location or ""),
                "resolution_method": str(resolution_method or ""),
                "first_turn": t_cur,
                "turn_updated": t_cur,
                "stage_history": [
                    {
                        "turn": t_cur,
                        "stage": norm_stage,
                        "name": pub_name,
                        "public_name": pub_name,
                        "is_disguised": is_disguised,
                    }
                ],
            }
            c.execute(
                """INSERT INTO session_anomaly_records (
                    session_id, record_type, entity_key, codex_id, stage,
                    first_turn, turn_updated, payload_json, created_at, updated_at
                ) VALUES (?, 'field_log', ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(session_id),
                    bp_id,
                    codex_id,
                    norm_stage,
                    t_cur,
                    t_cur,
                    json.dumps(entry, default=str),
                    now,
                    now,
                ),
            )
        else:
            entry = dict(_deserialize_json_field(existing_row["payload_json"], {}) or {})
            cur_rank = _FOLKLORE_STAGE_RANK.get(str(entry.get("stage") or "sighted"), 1)
            new_rank = _FOLKLORE_STAGE_RANK.get(norm_stage, 1)
            eff_stage = norm_stage if new_rank >= cur_rank else str(entry.get("stage") or "sighted")
            still_disguised = is_disguised and eff_stage == "sighted"
            if eff_stage in ("verified", "contained") or not still_disguised:
                entry["name"] = str(entry.get("true_name") or pub_name)
            entry["is_disguised"] = still_disguised
            entry["public_name"] = pub_name if still_disguised else entry["name"]
            entry["stage"] = eff_stage
            entry["status"] = eff_stage
            if codex_id and not entry.get("codex_id"):
                entry["codex_id"] = codex_id
            if location:
                entry["location"] = str(location)
            if resolution_method:
                entry["resolution_method"] = str(resolution_method)
            entry["turn_updated"] = t_cur
            hist = list(entry.get("stage_history") or [])
            hist.append(
                {
                    "turn": t_cur,
                    "stage": eff_stage,
                    "name": entry["name"],
                    "public_name": entry["public_name"],
                    "is_disguised": still_disguised,
                }
            )
            entry["stage_history"] = hist[-12:]
            c.execute(
                """UPDATE session_anomaly_records
                   SET codex_id = ?, stage = ?, turn_updated = ?, payload_json = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    str(entry.get("codex_id") or codex_id),
                    eff_stage,
                    t_cur,
                    json.dumps(entry, default=str),
                    now,
                    existing_row["id"],
                ),
            )

        return entry

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def retire_or_cooldown_folklore_in_session(
    session_id: int,
    codex_id: str,
    uniqueness: str = "species",
    current_day: int = 1,
    cooldown_days: int = 4,
    turn_number: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """
    Marks a `singular` Canonical Folklore entry as retired for the remainder of the session,
    or places a `species` entry onto a multi-day spawn cooldown in `sessions.extra_json`.
    """
    cid = str(codex_id or "").strip()
    if not session_id or not cid:
        return

    def _run(c: sqlite3.Connection) -> None:
        row = c.execute(
            "SELECT turn_count, current_day, extra_json, last_turn_snapshot_json FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not row:
            return
        t_cur = _effective_session_turn(row, turn_number)
        eff_day = int(current_day or row["current_day"] or 1)
        extra = _deserialize_json_field(row["extra_json"], {})
        if not isinstance(extra, dict):
            extra = {}

        if str(uniqueness or "species").strip().lower() == "singular":
            retired = list(extra.get("retired_folklore_ids") or [])
            if not any((isinstance(r, dict) and r.get("codex_id") == cid) or r == cid for r in retired):
                retired.append({"codex_id": cid, "turn_set": t_cur})
            extra["retired_folklore_ids"] = retired
        else:
            cooldowns = dict(extra.get("folklore_cooldowns") or {})
            prev_cd = cooldowns.get(cid) if isinstance(cooldowns.get(cid), dict) else {}
            prev_hist = list(prev_cd.get("history") or [])
            if prev_cd and "available_day" in prev_cd and not prev_hist:
                prev_hist.append(
                    {
                        "available_day": int(prev_cd["available_day"]),
                        "turn_set": int(prev_cd.get("turn_set", 0)),
                    }
                )
            new_avail = eff_day + max(1, int(cooldown_days or 4))
            prev_hist.append({"available_day": new_avail, "turn_set": t_cur})
            cooldowns[cid] = {
                "available_day": new_avail,
                "turn_set": t_cur,
                "history": prev_hist[-8:],
            }
            extra["folklore_cooldowns"] = cooldowns

        c.execute(
            "UPDATE sessions SET extra_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(extra), time.time(), session_id),
        )

    if conn is not None:
        _run(conn)
    else:
        with get_conn() as c:
            _run(c)


def rollback_session_anomaly_logs_after_turn(
    session_id: int,
    turn_number: int,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, int]:
    """
    Reverts session-scoped `anomaly_field_log`, `retired_folklore_ids`, and `folklore_cooldowns`
    in `sessions.extra_json` for turns strictly greater than `turn_number`.
    Account-wide `user_folklore_codex` rows remain permanently unlocked.
    """
    t_num = int(turn_number)

    def _run(c: sqlite3.Connection) -> dict[str, int]:
        row = c.execute("SELECT extra_json FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return {"field_log_reverted": 0}
        extra = _deserialize_json_field(row["extra_json"], {}) if row["extra_json"] else {}
        if not isinstance(extra, dict):
            extra = {}

        changed = 0
        extra_changed = False
        now = time.time()

        # 1. Roll back normalized `session_anomaly_records` rows (`first_turn > t_num` delete + `stage_history` rewind)
        try:
            rec_rows = c.execute(
                """SELECT id, record_type, codex_id, stage, first_turn, turn_updated, payload_json
                   FROM session_anomaly_records
                   WHERE session_id = ?
                   ORDER BY id ASC""",
                (int(session_id),),
            ).fetchall()
        except sqlite3.OperationalError as e:
            if "no such table" not in str(e).lower():
                raise
            rec_rows = []

        for rr in rec_rows:
            rec_id = rr["id"]
            rtype = str(rr["record_type"] or "")
            cid_r = str(rr["codex_id"] or "").strip()
            f_turn_r = int(rr["first_turn"] or 0)
            payload = _deserialize_json_field(rr["payload_json"], {})
            if not isinstance(payload, dict):
                payload = {}
            if not f_turn_r:
                for tk in ("first_turn", "turn_captured", "turn"):
                    if payload.get(tk) is not None:
                        try:
                            f_turn_r = int(payload[tk])
                            break
                        except (TypeError, ValueError):
                            continue

            if f_turn_r > t_num:
                eff_cid = cid_r or str(payload.get("codex_id") or "").strip()
                if eff_cid:
                    rw_map = dict(extra.get("_rewound_codex_first_turns") or {})
                    if rtype == "field_log":
                        rw_map[eff_cid] = f_turn_r
                    else:
                        rw_map.setdefault(eff_cid, f_turn_r)
                    extra["_rewound_codex_first_turns"] = rw_map
                    extra_changed = True
                c.execute("DELETE FROM session_anomaly_records WHERE id = ?", (rec_id,))
                changed += 1
                continue

            if rtype == "field_log":
                raw_hist = payload.get("stage_history") or []
                hist = [
                    h for h in raw_hist
                    if isinstance(h, dict) and int(h.get("turn", 0)) <= t_num
                ]
                if hist and (len(hist) != len(raw_hist) or int(rr["turn_updated"] or 0) > t_num):
                    upd = dict(payload)
                    last_h = hist[-1]
                    restored_stage = str(last_h.get("stage", upd.get("stage", "sighted")))
                    restored_name = str(last_h.get("name", upd.get("name", "")))
                    restored_disg = (
                        bool(last_h.get("is_disguised", False))
                        if "is_disguised" in last_h
                        else bool(upd.get("is_disguised") and restored_stage == "sighted")
                    )
                    restored_turn = int(last_h.get("turn", f_turn_r))
                    upd["stage"] = restored_stage
                    upd["status"] = restored_stage
                    upd["name"] = restored_name
                    upd["public_name"] = str(last_h.get("public_name", restored_name))
                    upd["is_disguised"] = restored_disg
                    upd["turn_updated"] = restored_turn
                    upd["stage_history"] = hist
                    c.execute(
                        """UPDATE session_anomaly_records
                           SET stage = ?, turn_updated = ?, payload_json = ?, updated_at = ?
                           WHERE id = ?""",
                        (restored_stage, restored_turn, json.dumps(upd, default=str), now, rec_id),
                    )
                    changed += 1

        # 2. Legacy `extra_json` fallback (plus `retired_folklore_ids`, `folklore_cooldowns`, `daily_incursions`, `anomalous_faction_state`)
        if "anomaly_field_log" in extra and isinstance(extra["anomaly_field_log"], list):
            new_log = []
            for item in extra["anomaly_field_log"]:
                if not isinstance(item, dict):
                    continue
                if int(item.get("first_turn", 0)) > t_num:
                    if item.get("codex_id"):
                        rw_map = dict(extra.get("_rewound_codex_first_turns") or {})
                        rw_map[str(item["codex_id"])] = int(item.get("first_turn", 0))
                        extra["_rewound_codex_first_turns"] = rw_map
                    changed += 1
                    continue
                hist = [h for h in (item.get("stage_history") or []) if isinstance(h, dict) and int(h.get("turn", 0)) <= t_num]
                if hist:
                    upd = dict(item)
                    last_h = hist[-1]
                    restored_stage = last_h.get("stage", upd.get("stage", "sighted"))
                    restored_name = last_h.get("name", upd.get("name", ""))
                    restored_disg = bool(last_h.get("is_disguised", False)) if "is_disguised" in last_h else bool(upd.get("is_disguised") and restored_stage == "sighted")
                    if (
                        upd.get("stage") != restored_stage
                        or upd.get("status") != restored_stage
                        or upd.get("name") != restored_name
                        or bool(upd.get("is_disguised")) != restored_disg
                    ):
                        changed += 1
                    upd["stage"] = restored_stage
                    upd["status"] = restored_stage
                    upd["name"] = restored_name
                    upd["public_name"] = last_h.get("public_name", restored_name)
                    upd["is_disguised"] = restored_disg
                    upd["turn_updated"] = int(last_h.get("turn", upd.get("first_turn", 0)))
                    upd["stage_history"] = hist
                    new_log.append(upd)
                else:
                    new_log.append(item)
            extra["anomaly_field_log"] = new_log

        if "retired_folklore_ids" in extra and isinstance(extra["retired_folklore_ids"], list):
            orig_ret = extra["retired_folklore_ids"]
            surv_ret = [
                r for r in orig_ret
                if not (isinstance(r, dict) and int(r.get("turn_set", 0)) > t_num)
            ]
            if len(surv_ret) != len(orig_ret):
                changed += 1
                extra["retired_folklore_ids"] = surv_ret

        if "folklore_cooldowns" in extra and isinstance(extra["folklore_cooldowns"], dict):
            orig_cd = extra["folklore_cooldowns"]
            surv_cd: dict[str, Any] = {}
            cd_changed = False
            for k, v in orig_cd.items():
                if not isinstance(v, dict):
                    surv_cd[k] = v
                    continue
                cd_hist = [
                    h for h in (v.get("history") or [])
                    if isinstance(h, dict) and int(h.get("turn_set", 0)) <= t_num
                ]
                if v.get("history"):
                    if not cd_hist:
                        cd_changed = True
                        continue
                    last_cd = cd_hist[-1]
                    if int(v.get("turn_set", 0)) != int(last_cd.get("turn_set", 0)) or int(v.get("available_day", 0)) != int(last_cd.get("available_day", 0)):
                        cd_changed = True
                    surv_cd[k] = {
                        "available_day": int(last_cd["available_day"]),
                        "turn_set": int(last_cd["turn_set"]),
                        "history": cd_hist,
                    }
                elif int(v.get("turn_set", 0)) > t_num:
                    cd_changed = True
                else:
                    surv_cd[k] = v
            if cd_changed or len(surv_cd) != len(orig_cd):
                changed += 1
                extra["folklore_cooldowns"] = surv_cd

        def _entry_turn_stamp(v: dict[str, Any]) -> Optional[int]:
            for tk in ("first_turn", "turn_captured", "turn"):
                if v.get(tk) is not None:
                    try:
                        return int(v[tk])
                    except (TypeError, ValueError):
                        continue
            return None

        for v_key in ("contained_anomalies_log", "anomalous_vault_log", "anomalous_vault_requisitions"):
            if v_key in extra and isinstance(extra[v_key], list):
                orig_v = extra[v_key]
                surv_v = []
                for v in orig_v:
                    if isinstance(v, dict):
                        v_turn = _entry_turn_stamp(v)
                        if v_turn is not None and v_turn > t_num:
                            if v.get("codex_id"):
                                rw_map = dict(extra.get("_rewound_codex_first_turns") or {})
                                rw_map.setdefault(str(v["codex_id"]), v_turn)
                                extra["_rewound_codex_first_turns"] = rw_map
                            continue
                    surv_v.append(v)
                if len(surv_v) != len(orig_v):
                    changed += 1
                    extra[v_key] = surv_v

        # Revert daily_incursions / daily_breaches resolved or spawned after t_num
        for inc_key in ("daily_incursions", "daily_breaches"):
            if inc_key in extra and isinstance(extra[inc_key], list):
                orig_len = len(extra[inc_key])
                # Purge dynamic incidents spawned on turns after t_num
                inc_list = [
                    inc for inc in extra[inc_key]
                    if not (isinstance(inc, dict) and inc.get("spawn_turn") and int(inc.get("spawn_turn", 0)) > t_num)
                ]
                if len(inc_list) != orig_len:
                    changed += 1
                for inc in inc_list:
                    if not isinstance(inc, dict):
                        continue
                    if inc.get("resolved") and int(inc.get("resolved_at_turn", 0)) > t_num:
                        inc["resolved"] = False
                        inc["agitated"] = False
                        inc.pop("resolved_at_turn", None)
                        inc.pop("killed_lethally", None)
                        inc.pop("dispersed_unsealed", None)
                        inc.pop("escaped", None)
                        changed += 1
                    if inc.get("dossier_revealed") and int(inc.get("revealed_at_turn", 0)) > t_num:
                        inc["dossier_revealed"] = False
                        inc.pop("revealed_at_turn", None)
                        if inc.get("original_entity_name"):
                            inc["entity_name"] = inc["original_entity_name"]
                            inc.pop("original_entity_name", None)
                        if isinstance(inc.get("anomaly_blueprint"), dict):
                            inc["anomaly_blueprint"]["dossier_revealed"] = False
                        changed += 1
                extra[inc_key] = inc_list

        # Revert anomalous_faction_state promotion rep changes after t_num
        if "anomalous_faction_state" in extra and isinstance(extra["anomalous_faction_state"], dict):
            afs = extra["anomalous_faction_state"]
            rep_hist = afs.get("rep_history")
            if isinstance(rep_hist, list) and rep_hist:
                surviving = [h for h in rep_hist if isinstance(h, dict) and int(h.get("turn", 0)) <= t_num]
                if len(surviving) != len(rep_hist):
                    if surviving:
                        last_h = surviving[-1]
                        afs["promotion_rep"] = int(last_h.get("new_rep", 0) or 0)
                    else:
                        first_h = rep_hist[0]
                        afs["promotion_rep"] = int(first_h.get("old_rep", 0) or 0)
                    afs["rep_history"] = surviving
                    from mechanics.social.factions import get_anomalous_promotion_tier_info
                    t_info = get_anomalous_promotion_tier_info(
                        afs["promotion_rep"],
                        faction_archetype_key=str(afs.get("faction_archetype_key") or ""),
                    )
                    if afs.get("faction_archetype_key") != "freelancer":
                        afs["promotion_tier"] = t_info["tier"]
                        afs["promotion_title"] = t_info["title"]
                    changed += 1

        if changed > 0 or extra_changed:
            c.execute(
                "UPDATE sessions SET extra_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(extra), time.time(), session_id),
            )
            if "anomalous_faction_state" in extra and isinstance(extra["anomalous_faction_state"], dict):
                afs = extra["anomalous_faction_state"]
                c.execute(
                    "UPDATE characters SET faction_rank = ?, faction_title = ? WHERE active_session_id = ?",
                    (int(afs.get("promotion_tier", 0) or 0), str(afs.get("promotion_title") or ""), session_id),
                )
        return {"field_log_reverted": changed}

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)
