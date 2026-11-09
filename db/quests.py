from __future__ import annotations

import db
import asyncio
import json
import time
from contextlib import contextmanager
from typing import Any, Optional
import re
import sqlite3
from config import DB_PATH
import character_data as cd
from .core import *
from .core import _delete_session_records, _to_str, _is_suspicious_entity_text, _safe_int_db, _sanitize_npcs_list
from .dossiers import _enrich_dossier_dict, get_quest_dossier

_TRANSIENT_SUB_OBJ_KEYS = {
    "waypoints",
    "active_waypoint",
    "stage_label",
    "stage_index",
    "total_stages",
    "completed_stages",
    "stages",
}


def is_quest_main_objectives_complete(sub_objectives: list | None) -> bool:
    """Evaluates whether a quest's mandatory Main Objective(s) are satisfied.
    - On compiled `1 Main + 1-3 Optionals` quests: True if Main (`is_optional=False`) is completed/bypassed
      OR if an `alternative` Optional (`role == 'alternative'`) is completed. Skipped/failed Optionals never block.
    - On legacy 3-checkbox quests (no `is_optional` flags): True when all sub-objectives are `completed`.
    """
    valid = [so for so in (sub_objectives or []) if isinstance(so, dict)]
    if not valid:
        return False
    if any(
        bool(so.get("is_optional"))
        and str(so.get("role") or "").strip().lower() == "alternative"
        and (bool(so.get("completed")) or str(so.get("status") or "").strip().lower() == "completed")
        for so in valid
    ):
        return True
    main_sos = [so for so in valid if not bool(so.get("is_optional"))]
    if not main_sos:
        return False
    return all(
        bool(so.get("completed"))
        or str(so.get("status") or "").strip().lower() in ("completed", "bypassed")
        for so in main_sos
    )


def compute_quest_main_progress_ratio(sub_objectives: list | None) -> float:
    """Computes 0.0..1.0 Main Objective progress without penalizing skipped Optionals."""
    valid = [so for so in (sub_objectives or []) if isinstance(so, dict)]
    if not valid:
        return 0.0
    if is_quest_main_objectives_complete(valid):
        return 1.0
    main_sos = [so for so in valid if not bool(so.get("is_optional"))]
    if not main_sos:
        return 0.0
    if len(main_sos) == 1:
        m0 = main_sos[0]
        tot = int(m0.get("total_stages") or 0)
        done = int(m0.get("completed_stages") or 0)
        if tot > 0:
            return max(0.0, min(1.0, done / float(tot)))
    done_cnt = sum(
        1
        for so in main_sos
        if bool(so.get("completed")) or str(so.get("status") or "").strip().lower() in ("completed", "bypassed")
    )
    return max(0.0, min(1.0, done_cnt / float(len(main_sos))))

def _normalize_loc_arrow(loc: str) -> str:
    if not loc:
        return ""
    return re.sub(r"\s*->\s*", " ➔ ", str(loc).strip())

def _clean_sub_objectives_for_storage(sub_objectives: list | str | None) -> str:
    if isinstance(sub_objectives, list):
        cleaned = []
        for so in sub_objectives:
            if isinstance(so, dict):
                cleaned.append({k: v for k, v in so.items() if k not in _TRANSIENT_SUB_OBJ_KEYS})
            else:
                cleaned.append(so)
        return json.dumps(cleaned)
    return sub_objectives or "[]"

def _serialize_quest_anomaly_blueprint_col(
    anomaly_blueprint: dict | str | None,
    quest_notes: str | None,
) -> str | None:
    if isinstance(anomaly_blueprint, dict):
        return json.dumps(anomaly_blueprint, separators=(",", ":"), ensure_ascii=True) if anomaly_blueprint else "{}"
    if isinstance(anomaly_blueprint, str) and anomaly_blueprint.strip():
        return anomaly_blueprint.strip()
    if quest_notes and ("anomaly_bp:" in str(quest_notes) or "anomaly_blueprint:" in str(quest_notes)):
        try:
            from mechanics.world.anomaly_engine import parse_blueprint_from_notes
            parsed = parse_blueprint_from_notes(str(quest_notes))
            if isinstance(parsed, dict) and parsed:
                return json.dumps(parsed, separators=(",", ":"), ensure_ascii=True)
        except Exception:
            pass
    return None


def upsert_quest(session_id: int, quest_id: str, quest_type: str, title: str,
                 objective: str, progress: str = "", current_clues: str = "",
                 status: str = "Active", reward_xp: int = 100, reward_gold: int = 25,
                 reward_stat_points: int = 0, reward_item: str = "",
                 is_story_quest: int = 0, clues_required: int = 3,
                 quest_notes: str = None, sub_objectives: list | str = None,
                 blueprint_id: str = None, client_npc: str = None,
                 client_location: str = None, required_item: str = None,
                 required_item_count: int = None, strikes: int = None,
                 max_strikes: int = None, deadline_day: int = None,
                 deadline_minute: int = None, resolution_approach: str = None,
                 engine: str = None, dossier_stage: str = None,
                 anomaly_blueprint: dict | str | None = None) -> dict:
    now = time.time()
    is_story_flag = int(
        bool(int(is_story_quest or 0) == 1 or str(quest_type or "").strip().lower() in ("story quest", "main quest"))
    )
    if is_story_flag:
        is_story_quest = 1
        deadline_day = None
        deadline_minute = None
    sub_obj_str = _clean_sub_objectives_for_storage(sub_objectives)
    bp_col_str = _serialize_quest_anomaly_blueprint_col(anomaly_blueprint, quest_notes)
    if blueprint_id is None:
        try:
            from mechanics.narrative.blueprints import get_blueprint_for_archetype
            blueprint_id = get_blueprint_for_archetype(quest_type, objective)
        except Exception:
            blueprint_id = ""

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id, reward_claimed FROM quests WHERE session_id=? AND quest_id=?",
            (session_id, quest_id)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE quests SET
                   quest_type=?, title=?, objective=?, progress=?, current_clues=?,
                   status=?, reward_xp=?, reward_gold=?, reward_stat_points=?, reward_item=?,
                   is_story_quest=?, clues_required=?,
                   quest_notes=COALESCE(?, quest_notes),
                   sub_objectives_json=CASE WHEN ? != '[]' THEN ? ELSE sub_objectives_json END,
                   blueprint_id=COALESCE(?, blueprint_id),
                   client_npc=COALESCE(?, client_npc),
                   client_location=COALESCE(?, client_location),
                   required_item=COALESCE(?, required_item),
                   required_item_count=COALESCE(?, required_item_count),
                   strikes=COALESCE(?, strikes),
                   max_strikes=COALESCE(?, max_strikes),
                   deadline_day=CASE WHEN ? = 1 THEN NULL ELSE COALESCE(?, deadline_day) END,
                   deadline_minute=CASE WHEN ? = 1 THEN NULL ELSE COALESCE(?, deadline_minute) END,
                   resolution_approach=COALESCE(?, resolution_approach),
                   engine=COALESCE(?, engine),
                   dossier_stage=COALESCE(?, dossier_stage),
                   anomaly_blueprint_json=COALESCE(?, anomaly_blueprint_json),
                   updated_at=?
                   WHERE id=?""",
                (quest_type or "Main Quest", title, objective, progress or "", current_clues or "",
                 status or "Active", reward_xp, reward_gold, reward_stat_points, reward_item or "",
                 is_story_quest, clues_required,
                 quest_notes, sub_obj_str, sub_obj_str,
                 blueprint_id, client_npc, client_location, required_item, required_item_count,
                 strikes, max_strikes,
                 is_story_flag, deadline_day,
                 is_story_flag, deadline_minute,
                 resolution_approach,
                 engine, dossier_stage, bp_col_str,
                 now, existing["id"])
            )
        else:
            conn.execute(
                """INSERT INTO quests
                   (session_id, quest_id, quest_type, title, objective, progress, current_clues,
                    status, reward_xp, reward_gold, reward_stat_points, reward_item,
                    is_story_quest, clues_required, reward_claimed, quest_notes,
                    sub_objectives_json, blueprint_id, client_npc, client_location,
                    required_item, required_item_count, strikes, max_strikes,
                    deadline_day, deadline_minute, resolution_approach, engine, dossier_stage,
                    anomaly_blueprint_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (session_id, quest_id, quest_type or "Main Quest", title, objective, progress or "",
                 current_clues or "", status or "Active", reward_xp, reward_gold, reward_stat_points,
                 reward_item or "", is_story_quest, clues_required, quest_notes or "",
                 sub_obj_str, blueprint_id or "", client_npc or "", client_location or "",
                 required_item or "", int(required_item_count if required_item_count is not None else 1),
                 int(strikes or 0), int(max_strikes if max_strikes is not None else 2),
                 deadline_day, deadline_minute, resolution_approach or "",
                 engine or "", dossier_stage or "legacy",
                 bp_col_str or "{}", now, now)
            )

    return get_quest_by_id(session_id, quest_id)

def _hydrate_quest_waypoint_for_enrichment(
    session_id: int,
    wr: Any,
    session: Optional[dict] = None,
    session_time: Optional[tuple] = None,
    contacts_cache: Optional[dict] = None,
) -> dict:
    w_dict = dict(wr)
    try:
        appr_raw = w_dict.get("approaches_json") or "[]"
        w_dict["approaches"] = json.loads(appr_raw) if isinstance(appr_raw, str) else (appr_raw or [])
    except Exception:
        w_dict["approaches"] = []
    if w_dict.get("target_location"):
        w_dict["target_location"] = _normalize_loc_arrow(w_dict["target_location"])
    w_dict["static_target_location"] = w_dict.get("target_location", "")
    if w_dict.get("follow_npc_schedule") and w_dict.get("target_npc"):
        try:
            from mechanics.world.waypoints.matching import resolve_effective_waypoint_location
            eff_loc = resolve_effective_waypoint_location(
                session_id,
                w_dict,
                session=session,
                session_time=session_time,
                contacts_cache=contacts_cache,
            )
            if eff_loc:
                norm_eff = _normalize_loc_arrow(eff_loc)
                w_dict["live_scheduled_location"] = norm_eff
                w_dict["effective_location"] = norm_eff
                w_dict["target_location"] = norm_eff
        except Exception:
            pass
    if not w_dict.get("effective_location"):
        w_dict["effective_location"] = w_dict.get("target_location", "")
    return w_dict

def _enrich_quest_dict(
    row: Any,
    preloaded_wps: Optional[list[Any]] = None,
    preloaded_dossier: Optional[dict] = None,
    dossier_preloaded: bool = False,
) -> dict | None:
    if not row:
        return None
    d = dict(row)
    d["strikes"] = int(d.get("strikes") or 0)
    d["max_strikes"] = int(d.get("max_strikes") or 2)
    d["resolution_approach"] = str(d.get("resolution_approach") or "")
    d["engine"] = str(d.get("engine") or "")
    d["dossier_stage"] = str(d.get("dossier_stage") or "legacy")
    try:
        from mechanics.world.anomaly_engine import parse_blueprint_from_notes
        d["anomaly_blueprint"] = parse_blueprint_from_notes(d)
    except Exception:
        d["anomaly_blueprint"] = None
    if d.get("sub_objectives_json"):
        try:
            raw_sos = json.loads(d["sub_objectives_json"])
            d["sub_objectives"] = [dict(so) if isinstance(so, dict) else so for so in (raw_sos or [])]
        except Exception:
            d["sub_objectives"] = []
    else:
        d["sub_objectives"] = []

    session_id = d.get("session_id")
    quest_id = d.get("quest_id")
    all_wps: list[dict] = []
    if session_id and quest_id:
        if preloaded_wps is not None:
            all_wps = [_hydrate_quest_waypoint_for_enrichment(session_id, wr) for wr in preloaded_wps]
        else:
            try:
                with get_conn() as conn:
                    wp_rows = conn.execute(
                        """SELECT * FROM quest_waypoints
                           WHERE session_id=? AND quest_id=?
                           ORDER BY COALESCE(sub_obj_id, 0) ASC, stage_index ASC""",
                        (session_id, quest_id)
                    ).fetchall()
                    all_wps = [_hydrate_quest_waypoint_for_enrichment(session_id, wr) for wr in wp_rows]
            except Exception:
                all_wps = []

        if dossier_preloaded:
            d["dossier"] = preloaded_dossier
        else:
            try:
                d["dossier"] = get_quest_dossier(int(session_id), str(quest_id))
            except Exception:
                d["dossier"] = None
    else:
        d["dossier"] = preloaded_dossier if dossier_preloaded else None

    d["has_structured_objectives"] = False
    d["main_objective"] = None
    d["optional_objectives"] = []

    if d["sub_objectives"]:
        is_structured = any(
            isinstance(so, dict) and ("is_optional" in so or _safe_int_db(so.get("id"), -1) == 0)
            for so in d["sub_objectives"]
        )
        d["has_structured_objectives"] = is_structured

        for idx, so in enumerate(d["sub_objectives"]):
            if not isinstance(so, dict):
                continue
            so_id = so.get("id", idx + 1)
            so_wps = [
                w for w in all_wps
                if w.get("sub_obj_id") is not None and _safe_int_db(w.get("sub_obj_id"), -1) == _safe_int_db(so_id, -2)
            ]
            if so_wps:
                is_disc = bool(so.get("is_discovered", True))
                so_stat = str(so.get("status") or ("completed" if so.get("completed") else "active")).lower()
                active_wp = next((w for w in so_wps if w.get("status") == "active"), None)
                if not active_wp and not so.get("completed") and is_disc and so_stat not in ("failed", "bypassed", "locked_out"):
                    active_wp = next((w for w in so_wps if w.get("status") == "locked"), so_wps[0])
                elif not active_wp and so.get("completed"):
                    active_wp = so_wps[-1]
                so["waypoints"] = so_wps
                so["active_waypoint"] = active_wp if (is_disc and so_stat not in ("failed", "bypassed", "locked_out")) else None
                so["target_location"] = (active_wp.get("target_location") or "") if active_wp else _normalize_loc_arrow(so.get("target_location") or "")
                so["target_npc"] = (active_wp.get("target_npc") or "") if active_wp else (so.get("target_npc") or "")
                so["stage_label"] = (active_wp.get("stage_label") or "") if active_wp else ""
                so["stage_index"] = int(active_wp.get("stage_index", 1) or 1) if active_wp else 1
                so["total_stages"] = len(so_wps)
                so["completed_stages"] = sum(1 for w in so_wps if w.get("status") in ("completed", "bypassed"))
                so["stages"] = [
                    {
                        "stage_index": int(w.get("stage_index", i + 1) or (i + 1)),
                        "stage_label": w.get("stage_label", ""),
                        "text": w.get("stage_label", ""),
                        "target_location": w.get("target_location", ""),
                        "target_npc": w.get("target_npc", ""),
                        "completion_trigger": w.get("completion_trigger", "arrival"),
                        "status": w.get("status", "locked"),
                        "completed": w.get("status") in ("completed", "bypassed"),
                    }
                    for i, w in enumerate(so_wps)
                ]
            elif so.get("target_location"):
                so["target_location"] = _normalize_loc_arrow(so["target_location"])

        all_so_done = is_quest_main_objectives_complete(d["sub_objectives"])
        if all_so_done and d.get("status") == "Active":
            d["climax_ready"] = True

        if is_structured:
            d["main_objective"] = next(
                (so for so in d["sub_objectives"] if isinstance(so, dict) and not bool(so.get("is_optional"))),
                None,
            )
            d["optional_objectives"] = [
                so
                for so in d["sub_objectives"]
                if isinstance(so, dict) and bool(so.get("is_optional")) and bool(so.get("is_discovered", True))
            ]
            if d["main_objective"] and d["main_objective"].get("stages"):
                d["stages"] = d["main_objective"]["stages"]

        eligible_sos = [
            so
            for so in d["sub_objectives"]
            if isinstance(so, dict)
            and not bool(so.get("completed"))
            and bool(so.get("is_discovered", True))
            and str(so.get("status") or "active").lower() not in ("completed", "failed", "bypassed", "locked_out")
            and so.get("active_waypoint")
        ]
        # Prioritize Main Objective (`is_optional=False` / `id=0`) in HUD compass
        eligible_sos.sort(key=lambda s: (1 if bool(s.get("is_optional")) else 0, _safe_int_db(s.get("id"), 99)))
        active_so_wps = [so["active_waypoint"] for so in eligible_sos]
        if all_wps:
            d["waypoints"] = [
                w
                for w in all_wps
                if not any(
                    isinstance(s, dict)
                    and _safe_int_db(s.get("id"), -99) == _safe_int_db(w.get("sub_obj_id"), -98)
                    and not bool(s.get("is_discovered", True))
                    for s in d["sub_objectives"]
                )
            ]
            d["active_waypoints"] = active_so_wps
            if active_so_wps:
                d["active_waypoint"] = active_so_wps[0]
                if not d.get("target_location"):
                    d["target_location"] = active_so_wps[0].get("target_location", "")
                if not d.get("target_npc"):
                    d["target_npc"] = active_so_wps[0].get("target_npc", "")
                if not d.get("stage_label"):
                    d["stage_label"] = active_so_wps[0].get("stage_label", "")
    elif all_wps:
        quest_wps = [w for w in all_wps if w.get("sub_obj_id") is None] or all_wps
        d["waypoints"] = quest_wps
        active_wp = next((w for w in quest_wps if w.get("status") == "active"), None)
        if not active_wp and d.get("status") != "Completed":
            active_wp = next((w for w in quest_wps if w.get("status") == "locked"), quest_wps[0])
        elif not active_wp and quest_wps:
            active_wp = quest_wps[-1]
        d["active_waypoint"] = active_wp
        d["active_waypoints"] = [active_wp] if active_wp and active_wp.get("status") == "active" else []
        if active_wp:
            d["target_location"] = active_wp.get("target_location") or _normalize_loc_arrow(d.get("target_location") or "")
            d["target_npc"] = active_wp.get("target_npc") or ""
            d["stage_label"] = active_wp.get("stage_label") or ""
        d["stages"] = [
            {
                "stage_index": int(w.get("stage_index", i + 1) or (i + 1)),
                "stage_label": w.get("stage_label", ""),
                "text": w.get("stage_label", ""),
                "target_location": w.get("target_location", ""),
                "target_npc": w.get("target_npc", ""),
                "completion_trigger": w.get("completion_trigger", "arrival"),
                "resource_target": int(w.get("resource_target", 0) or 0),
                "resource_collected": int(w.get("resource_collected", 0) or 0),
                "status": w.get("status", "locked"),
                "completed": w.get("status") == "completed",
            }
            for i, w in enumerate(quest_wps)
        ]

    return d

def get_active_story_quest(session_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM quests
               WHERE session_id=? AND (is_story_quest=1 OR LOWER(quest_type) IN ('story quest', 'main quest'))
               AND LOWER(status)='active'
               ORDER BY (CASE WHEN sub_objectives_json IS NOT NULL AND sub_objectives_json != '[]' AND sub_objectives_json != '' THEN 1 ELSE 0 END) DESC, updated_at DESC""",
            (session_id,)
        ).fetchone()
    return _enrich_quest_dict(row)

def get_session_quests(session_id: int, status: str = None) -> list[dict]:
    wps_by_qid: dict[str, list[Any]] = {}
    dossiers_by_qid: dict[str, dict] = {}
    with get_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM quests WHERE session_id=? AND LOWER(status)=LOWER(?) ORDER BY updated_at DESC",
                (session_id, status)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM quests WHERE session_id=? ORDER BY updated_at DESC",
                (session_id,)
            ).fetchall()
        if rows:
            try:
                wp_rows = conn.execute(
                    """SELECT * FROM quest_waypoints
                       WHERE session_id=?
                       ORDER BY quest_id ASC, COALESCE(sub_obj_id, 0) ASC, stage_index ASC""",
                    (session_id,)
                ).fetchall()
                for wr in wp_rows:
                    qid_key = str(wr["quest_id"] or "")
                    wps_by_qid.setdefault(qid_key, []).append(wr)
            except Exception:
                wps_by_qid = {}
            try:
                d_rows = conn.execute(
                    "SELECT * FROM quest_dossiers WHERE session_id=?",
                    (session_id,)
                ).fetchall()
                for dr in d_rows:
                    ed = _enrich_dossier_dict(dr)
                    if ed and ed.get("quest_id"):
                        dossiers_by_qid[str(ed["quest_id"])] = ed
            except Exception:
                dossiers_by_qid = {}
    out: list[dict] = []
    for r in rows:
        if not r:
            continue
        qid = str(r["quest_id"] or "")
        enriched = _enrich_quest_dict(
            r,
            preloaded_wps=wps_by_qid.get(qid, []),
            preloaded_dossier=dossiers_by_qid.get(qid),
            dossier_preloaded=True,
        )
        if enriched:
            out.append(enriched)
    return out

get_quests = get_session_quests

def get_quest_by_id(session_id: int, quest_id: str) -> dict | None:

    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM quests WHERE session_id=? AND quest_id=?",
            (session_id, quest_id)
        ).fetchone()
    return _enrich_quest_dict(row)

def update_session_campaign_goals(session_id: int, goals: list):
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET campaign_end_goals_json=?, updated_at=? WHERE id=?",
            (json.dumps(goals), time.time(), session_id)
        )

def get_session_campaign_goals(session_id: int) -> list:
    session = db.get_session(session_id)
    if not session or not session.get("campaign_end_goals_json"):
        return []
    try:
        val = json.loads(session["campaign_end_goals_json"])
        return val if isinstance(val, list) else []
    except Exception:
        return []

def set_session_chapter(session_id: int, chapter: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET current_chapter=?, updated_at=? WHERE id=?",
            (chapter, time.time(), session_id)
        )

update_session_chapter = set_session_chapter

def get_session_chapter(session_id: int) -> int:
    session = db.get_session(session_id)
    if not session:
        return 1
    return session.get("current_chapter", 1) or 1

def update_quest_status(session_id: int, quest_id: str, status: str):
    now = time.time()
    with get_conn() as conn:
        if status == "Active":
            row = conn.execute(
                "SELECT deadline_day, is_story_quest FROM quests WHERE session_id=? AND quest_id=?",
                (session_id, quest_id)
            ).fetchone()
            if row and row["deadline_day"] is not None and not row["is_story_quest"]:
                s_row = conn.execute("SELECT current_day FROM sessions WHERE id=?", (session_id,)).fetchone()
                curr_day = int(s_row["current_day"] or 1) if s_row else 1
                min_deadline = curr_day + 5
                if int(row["deadline_day"]) < min_deadline:
                    conn.execute(
                        "UPDATE quests SET deadline_day=? WHERE session_id=? AND quest_id=?",
                        (min_deadline, session_id, quest_id)
                    )
        conn.execute(
            "UPDATE quests SET status=?, updated_at=? WHERE session_id=? AND quest_id=?",
            (status, now, session_id, quest_id)
        )

def append_quest_note_flag_in_db(session_id: int, quest_id: str, flag_key: str, flag_val: str = "1") -> str:
    """Appends or updates a flag in the quest's quest_notes field in SQLite (and syncs `anomaly_blueprint_json` on reveal)."""
    from mechanics.narrative.blueprints import append_quest_note_flag
    now = time.time()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT quest_notes, anomaly_blueprint_json FROM quests WHERE session_id=? AND quest_id=?",
            (session_id, quest_id),
        ).fetchone()
        cur_notes = row["quest_notes"] if row else ""
        new_notes = append_quest_note_flag(cur_notes, flag_key, flag_val)
        bp_json_upd = None
        if row and flag_key == "dossier_revealed":
            raw_bp_j = row["anomaly_blueprint_json"] or ""
            if raw_bp_j.strip() not in ("", "{}"):
                try:
                    bp_d = json.loads(raw_bp_j)
                    if isinstance(bp_d, dict) and bp_d:
                        rev_bool = str(flag_val).strip().lower() in ("1", "true", "yes")
                        bp_d["dossier_revealed"] = rev_bool
                        if rev_bool and isinstance(bp_d.get("disguise_state"), dict):
                            bp_d["disguise_state"]["is_disguised"] = False
                        bp_json_upd = json.dumps(bp_d, separators=(",", ":"), ensure_ascii=True)
                except Exception:
                    bp_json_upd = None
        if bp_json_upd is not None:
            conn.execute(
                "UPDATE quests SET quest_notes=?, anomaly_blueprint_json=?, updated_at=? WHERE session_id=? AND quest_id=?",
                (new_notes, bp_json_upd, now, session_id, quest_id),
            )
        else:
            conn.execute(
                "UPDATE quests SET quest_notes=?, updated_at=? WHERE session_id=? AND quest_id=?",
                (new_notes, now, session_id, quest_id),
            )
        return new_notes


def update_quest_anomaly_blueprint(
    session_id: int,
    quest_id: str,
    blueprint: dict,
    quest_notes: str | None = None,
) -> bool:
    """Persists an updated `AnomalyBlueprint` into `quests.anomaly_blueprint_json` (and optional `quest_notes`)."""
    if not session_id or not quest_id or not isinstance(blueprint, dict):
        return False
    now = time.time()
    bp_json_str = json.dumps(blueprint, separators=(",", ":"), ensure_ascii=True)
    with get_conn() as conn:
        if quest_notes is not None:
            cur = conn.execute(
                "UPDATE quests SET anomaly_blueprint_json=?, quest_notes=?, updated_at=? WHERE session_id=? AND quest_id=?",
                (bp_json_str, quest_notes, now, session_id, quest_id),
            )
        else:
            cur = conn.execute(
                "UPDATE quests SET anomaly_blueprint_json=?, updated_at=? WHERE session_id=? AND quest_id=?",
                (bp_json_str, now, session_id, quest_id),
            )
        return cur.rowcount > 0

def claim_quest_reward(session_id: int, quest_id: str, party_user_ids: list[int]) -> dict:
    quest = get_quest_by_id(session_id, quest_id)
    if not quest or quest.get("reward_claimed"):
        return {"already_claimed": True}

    try:
        from game_engine.quests import consume_quest_delivery_item_if_needed
        consume_quest_delivery_item_if_needed(session_id, quest, party_user_ids)
    except Exception:
        pass

    rxp = quest.get("reward_xp", 100)
    rgold = quest.get("reward_gold", 25)
    ritem = quest.get("reward_item") or ""
    notes = str(quest.get("quest_notes") or "")
    is_story_q = bool(quest.get("is_story_quest") or quest.get("quest_type") in ("Story Quest", "Main Quest"))

    # Anomalous Incursions: Faction Reward Confiscation, 5-Tier Promotion Meter & Vault Log
    anom_promotion_result = None
    anom_reward_note = ""
    scen_key = "fantasy"
    try:
        import scenario_data
        sess_row = db.get_session(session_id) or {}
        scen_key = str(sess_row.get("scenario") or "fantasy")
        if scenario_data.is_anomalous_incursions_scenario(scen_key):
            from mechanics.social.factions import get_anomalous_faction_state, update_agent_promotion_reputation
            from mechanics.narrative.bounty import parse_anomalous_quest_board_source
            lead_uid = party_user_ids[0] if party_user_ids else sess_row.get("host_user_id")
            fac_st = get_anomalous_faction_state(session_id, user_id=lead_uid)
            player_arch = str(fac_st.get("faction_archetype_key") or "public_agency")
            board_src = parse_anomalous_quest_board_source(quest, session_id=session_id)
            is_mandatory = ("mandatory_daily:1" in notes) or str(quest_id or "").upper().startswith("MAND-")

            # 1. Reward & Loot Confiscation Rules
            if player_arch == "public_agency" and (board_src == "public_agency" or is_story_q or is_mandatory):
                rgold = 0
                ritem = ""
                anom_reward_note = "Taxpayer Mandate: 0G / 0 Loot (salaried Public Agency duty)."
            elif player_arch == "monastic_order" and (board_src == "monastic_order" or is_mandatory):
                rgold = 0
                anom_reward_note = "Sacred Shrine Duty: 0G bounty fee (recovered relics/spoils retained)."

            # 2. 5-Tier Agent Promotion Meter Progression
            if player_arch != "freelancer":
                earns_promo_rep = (
                    is_mandatory
                    or (board_src == player_arch)
                    or is_story_q
                )
                if earns_promo_rep:
                    rep_delta = 15 if (is_mandatory or is_story_q) else 10
                    anom_promotion_result = update_agent_promotion_reputation(
                        session_id=session_id,
                        delta_rep=rep_delta,
                        reason=f"Completed '{quest.get('title', 'Mission')}'",
                        is_mandatory_completion=is_mandatory,
                        user_id=lead_uid,
                    )

            # 3. Record Non-Hostile Entity / Altered Relic Containment to Vault Log (unless failed-forward via dire_cost)
            q_type_low = str(quest.get("quest_type") or "").lower()
            res_app_low = str(quest.get("resolution_approach") or "").lower()
            if res_app_low != "dire_cost" and any(k in q_type_low for k in ("non-hostile", "non_hostile", "altered item", "cursed relic", "relic_retrieval")):
                from mechanics.world.anomalous_events import record_contained_anomaly_to_vault_log, extract_non_hostile_entity_name
                is_nh_type = "non-hostile" in q_type_low or "non_hostile" in q_type_low
                ent_disp = (
                    extract_non_hostile_entity_name(quest)
                    if is_nh_type
                    else str(quest.get("required_item") or quest.get("title") or "Anomalous Specimen")
                )
                record_contained_anomaly_to_vault_log(
                    session_id=session_id,
                    entity_name=ent_disp,
                    category_tag="cursed_relic" if ("relic" in q_type_low or "item" in q_type_low) else "spatial_warp",
                    subtype="non_hostile_entity" if is_nh_type else "environmental_phenomenon",
                    location=str(quest.get("client_location") or sess_row.get("current_location") or "Metropolitan Grid"),
                    containment_note=f"Secured and logged upon completion of '{quest.get('title', 'Containment Operation')}'.",
                    resolution_method="Bounty Containment Protocol",
                    user_id=lead_uid,
                    quest_id=str(quest_id or ""),
                )
    except Exception:
        pass

    levels_gained_by_user = {}
    for uid in party_user_ids:
        lvl_ups = db.add_xp(uid, rxp)
        if lvl_ups:
            levels_gained_by_user[uid] = lvl_ups

        db.apply_hp_mp_delta(uid, 0, 0, rgold)

        if ritem:
            import scenario_data as _sd_q
            if _sd_q.is_anomalous_incursions_scenario(scen_key):
                try:
                    from mechanics.combat.items.consumables.generators import generate_procedural_potion
                    r_lower = str(ritem).lower()
                    eff_tags = ["mana_restore"] if any(w in r_lower for w in ("stabilizer", "incense", "ampoule", "focus", "spirit")) else ["healing"]
                    pot = generate_procedural_potion(tier=2, effect_tags=eff_tags, genre="anomalous_incursions")
                    db.add_item(uid, ritem, pot.get("item_type", "Potion"), pot.get("effect", "Restores HP"), 1)
                except Exception:
                    db.add_item(uid, ritem, "Potion", "Restores 35 HP", 1)
            else:
                db.add_item(uid, ritem, "Quest", "Quest Reward", 1)

    # Client Affinity Boost: +8 for personal commissions, +5 for standard quests
    client_affinity_gain = 0
    client_npc = quest.get("client_npc") or ""
    notes = str(quest.get("quest_notes") or "")
    if client_npc:
        client_affinity_gain = 8 if (quest_id.startswith("COMM-") or "commission:1" in notes) else 5
        try:
            db.update_relationship_score(session_id, client_npc, delta_score=client_affinity_gain)
        except Exception:
            pass

    # Sponsoring Faction Rep Gain & Rival Faction Reputation Ripple (-5)
    faction_rep_gained = 0
    rival_rep_deltas = {}
    if "faction:" in notes or "rival_faction:" in notes:
        try:
            parts = [p.strip() for p in re.split(r'[|\n]+', notes) if p.strip()]
            faction_id = ""
            riv_ids = []
            for p in parts:
                if p.startswith("faction:"):
                    faction_id = p.split(":", 1)[1].strip()
                elif p.startswith("rep_reward:"):
                    faction_rep_gained = int(p.split(":", 1)[1].strip())
                elif p.startswith("rival_faction:"):
                    r_val = p.split(":", 1)[1].strip()
                    if r_val and r_val not in riv_ids:
                        riv_ids.append(r_val)
            if faction_id:
                if faction_rep_gained <= 0:
                    faction_rep_gained = 10
                db.upsert_faction(session_id, faction_id, delta_score=faction_rep_gained, notes="Faction bounty completed")
                try:
                    s_fac = db.get_faction(session_id, faction_id)
                    if s_fac and s_fac.get("rival_faction_ids"):
                        for r in s_fac["rival_faction_ids"]:
                            if r and str(r).strip() not in riv_ids:
                                riv_ids.append(str(r).strip())
                except Exception:
                    pass

            for rid in riv_ids:
                if rid and rid != faction_id:
                    try:
                        db.upsert_faction(session_id, rid, delta_score=-5, notes=f"Rival operation '{quest.get('title')}' completed")
                        rival_rep_deltas[rid] = -5
                    except Exception:
                        pass
        except Exception:
            pass


    with get_conn() as conn:
        conn.execute(
            "UPDATE quests SET reward_claimed=1, status='Completed', updated_at=? WHERE session_id=? AND quest_id=?",
            (time.time(), session_id, quest_id)
        )

    return {
        "claimed": True,
        "title": quest["title"],
        "quest_type": quest["quest_type"],
        "is_story_quest": bool(quest.get("is_story_quest") or quest.get("quest_type") in ("Story Quest", "Main Quest")),
        "xp": rxp,
        "gold": rgold,
        "item": ritem,
        "levels_gained": levels_gained_by_user,
        "_item_granted_in_db": bool(ritem),
        "client_affinity_gained": client_affinity_gain,
        "faction_rep_gained": faction_rep_gained,
        "rival_rep_deltas": rival_rep_deltas,
        "anomalous_promotion": anom_promotion_result,
        "anomalous_reward_note": anom_reward_note,
    }

def add_session_clue(
    session_id: int,
    title: str,
    lead_text: str,
    category: str = "physical",
    source_location: str = "",
    linked_npc: str = "",
    quest_id: str = "",
    chapter: int = 1,
    is_verified: int = 0,
    deduction_parents: list = None,
    turn_created: int | None = None,
) -> int:
    """Inserts a new structured evidence record into session_clues with deduplication check."""
    if not title or not lead_text:
        return 0
    clean_title = title.strip()[:100]
    clean_lead = lead_text.strip()
    clean_cat = category.strip().lower() if category else "physical"
    if clean_cat not in ("physical", "testimonial", "digital", "document", "deduction"):
        clean_cat = "physical"
    parents_json = json.dumps(deduction_parents) if isinstance(deduction_parents, list) else "[]"
    now = time.time()

    with get_conn() as conn:
        if turn_created is None:
            try:
                s_row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
                turn_created = int(db.infer_session_turn(dict(s_row))) if s_row else 1
            except Exception:
                turn_created = 1

        rows = conn.execute(
            "SELECT * FROM session_clues WHERE session_id=? ORDER BY created_at ASC, id ASC",
            (session_id,)
        ).fetchall()
        t_clean_low = clean_title.lower()
        l_clean_low = clean_lead.lower()
        for r in rows:
            r_title_low = str(r["title"]).lower()
            r_lead_low = str(r["lead_text"]).lower()
            if r_title_low == t_clean_low or r_lead_low == l_clean_low:
                return r["id"]
            if l_clean_low in r_lead_low or r_lead_low in l_clean_low:
                return r["id"]

        cur = conn.execute(
            """INSERT INTO session_clues
               (session_id, quest_id, chapter, title, lead_text, category, source_location, linked_npc, is_verified, deduction_parents_json, turn_created, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, quest_id or "", chapter or 1, clean_title, clean_lead, clean_cat, source_location or "", linked_npc or "", int(is_verified), parents_json, int(turn_created or 1), now, now)
        )
        new_id = cur.lastrowid

        # D12 Smart Tiered 20-Clue Caseboard Cap:
        # Cap active unconsumed leads at 20 by auto-archiving (is_consumed=1) oldest completed-chapter
        # or circumstantial/side-bounty clues first; NEVER evict active Story Quest clues or Breakthroughs.
        try:
            all_rows = conn.execute(
                "SELECT * FROM session_clues WHERE session_id=? ORDER BY created_at ASC, id ASC",
                (session_id,),
            ).fetchall()
            consumed_by_parent: set[int] = set()
            for r in all_rows:
                try:
                    for pid in (json.loads(r["deduction_parents_json"] or "[]") or []):
                        consumed_by_parent.add(int(pid))
                except Exception:
                    pass

            active_unconsumed = []
            for r in all_rows:
                rd = dict(r)
                if rd.get("category") == "deduction":
                    continue
                if bool(rd.get("is_consumed")) or rd["id"] in consumed_by_parent:
                    continue
                active_unconsumed.append(rd)

            if len(active_unconsumed) > 20:
                sq_rows = conn.execute(
                    "SELECT quest_id FROM quests WHERE session_id=? AND status='Active' AND is_story_quest=1",
                    (session_id,),
                ).fetchall()
                active_sq_ids = {str(sr["quest_id"]) for sr in sq_rows if sr["quest_id"]}
                cur_ch_val = int(chapter or 1)
                evictable = [
                    rd for rd in active_unconsumed
                    if rd["id"] != new_id
                    and rd.get("category") != "deduction"
                    and str(rd.get("quest_id") or "") not in active_sq_ids
                ]
                evictable.sort(
                    key=lambda rd: (
                        0 if int(rd.get("chapter") or 1) < cur_ch_val else (1 if not rd.get("quest_id") else 2),
                        float(rd.get("created_at") or 0.0),
                        int(rd["id"]),
                    )
                )
                overflow = len(active_unconsumed) - 20
                for target_rd in evictable[:overflow]:
                    conn.execute(
                        "UPDATE session_clues SET is_consumed=1, updated_at=? WHERE id=?",
                        (now, target_rd["id"]),
                    )
        except sqlite3.OperationalError:
            pass

        return new_id

def get_session_clues(
    session_id: int,
    chapter: int = None,
    linked_npc: str = None,
    category: str = None,
    is_verified: int = None
) -> list[dict]:
    """Retrieves evidence records from session_clues with optional filters."""
    query = "SELECT * FROM session_clues WHERE session_id=?"
    params = [session_id]
    if chapter is not None:
        query += " AND chapter=?"
        params.append(chapter)
    if linked_npc:
        query += " AND (LOWER(linked_npc)=? OR LOWER(linked_npc) LIKE ?)"
        params.extend([linked_npc.strip().lower(), f"%{linked_npc.strip().lower()}%"])
    if category:
        query += " AND category=?"
        params.append(category.strip().lower())
    if is_verified is not None:
        query += " AND is_verified=?"
        params.append(int(is_verified))
    query += " ORDER BY is_verified DESC, id DESC"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        consumed_ids = set()
        for r in rows:
            try:
                parents = json.loads(r["deduction_parents_json"] or "[]")
                consumed_ids.update(parents)
            except Exception:
                pass

        results = []
        for r in rows:
            d = dict(r)
            try:
                d["deduction_parents"] = json.loads(d.get("deduction_parents_json") or "[]")
            except Exception:
                d["deduction_parents"] = []
            d["is_consumed"] = bool(d.get("is_consumed")) or (d["id"] in consumed_ids)
            results.append(d)
        return results

def get_session_clue_by_id(clue_id: int) -> dict | None:
    """Fetches a single evidence record by ID."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM session_clues WHERE id=?", (clue_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["deduction_parents"] = json.loads(d.get("deduction_parents_json") or "[]")
        except Exception:
            d["deduction_parents"] = []
            
        # Check if this clue was consumed by any other deduction
        consumed = False
        all_parents_rows = conn.execute("SELECT deduction_parents_json FROM session_clues WHERE session_id=?", (d["session_id"],)).fetchall()
        for pr in all_parents_rows:
            try:
                p_list = json.loads(pr[0] or "[]")
                if d["id"] in p_list:
                    consumed = True
                    break
            except Exception:
                pass
        d["is_consumed"] = bool(d.get("is_consumed")) or consumed
        return d

def verify_session_clue(clue_id: int) -> bool:
    """Marks an evidence record as verified."""
    with get_conn() as conn:
        cur = conn.execute("UPDATE session_clues SET is_verified=1, updated_at=? WHERE id=?", (time.time(), clue_id))
        return cur.rowcount > 0

def delete_session_clue(clue_id: int) -> bool:
    """Deletes an evidence record by ID."""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM session_clues WHERE id=?", (clue_id,))
        return cur.rowcount > 0

def apply_caseboard_breakthrough_to_quests(
    session_id: int,
    clue_ids: list[int],
    title: str,
    lead_text: str
) -> dict:
    """
    Checks active quests and sub-objectives against a synthesized Caseboard deduction.
    Auto-advances intermediate Stage 1 scouting/investigation to Stage 2 Confrontation,
    and tags the quest with 'caseboard_breakthrough:1' to unlock Breakthrough Leverage.
    """
    matched_qids = []
    advanced_qids = []

    parent_clues = []
    for pid in clue_ids:
        cl = get_session_clue_by_id(pid)
        if cl:
            parent_clues.append(cl)

    parent_qids = {str(c.get("quest_id")).strip() for c in parent_clues if c.get("quest_id")}
    parent_npcs = {str(c.get("linked_npc")).strip().lower() for c in parent_clues if c.get("linked_npc")}

    combined_text = f"{title} {lead_text}".lower()
    text_words = set(re.findall(r'\b[a-z]{4,}\b', combined_text)) - {
        "this", "that", "with", "from", "have", "been", "were", "what", "some", "discovered", "evidence"
    }

    active_quests = get_session_quests(session_id, status="Active") or []
    for q in active_quests:
        qid = q.get("quest_id", "")
        if not qid:
            continue
        all_wps = get_quest_waypoints(session_id, qid, None) or []
        active_wp = get_active_waypoint(session_id, qid, None)

        is_match = False
        if qid in parent_qids:
            is_match = True
        elif parent_npcs and any(str(w.get("target_npc", "")).strip().lower() in parent_npcs for w in all_wps):
            is_match = True
        elif parent_npcs and (str(q.get("client_npc", "")).strip().lower() in parent_npcs or str(q.get("target_npc", "")).strip().lower() in parent_npcs):
            is_match = True
        elif q.get("blueprint_id") in ("INVESTIGATION", "SOCIAL_MANIPULATION") or q.get("is_story_quest"):
            q_text = f"{q.get('title', '')} {q.get('objective', '')}".lower()
            q_words = set(re.findall(r'\b[a-z]{4,}\b', q_text))
            if len(text_words & q_words) >= 1:
                is_match = True

        if is_match:
            matched_qids.append(qid)
            append_quest_note_flag_in_db(session_id, qid, "caseboard_breakthrough", "1")

            # Auto-advance Stage 1 scouting/investigation to Stage 2 Confrontation
            if active_wp and int(active_wp.get("stage_index", 1)) == 1 and len(all_wps) >= 2:
                advance_waypoint(session_id, qid, 1, None)
                advanced_qids.append(qid)

            # Check sub-objectives if story quest
            sub_objs = q.get("sub_objectives") or []
            if isinstance(sub_objs, list) and sub_objs:
                for so in sub_objs:
                    if not isinstance(so, dict) or so.get("completed"):
                        continue
                    so_id = so.get("id")
                    if so_id is None:
                        continue
                    so_wp = get_active_waypoint(session_id, qid, so_id)
                    so_all_wps = get_quest_waypoints(session_id, qid, so_id) or []
                    if so_wp and int(so_wp.get("stage_index", 1)) == 1 and len(so_all_wps) >= 2:
                        advance_waypoint(session_id, qid, 1, so_id)
                        if qid not in advanced_qids:
                            advanced_qids.append(qid)

    return {"matched_quest_ids": matched_qids, "advanced_quest_ids": advanced_qids}

def synthesize_deduction_clue(
    session_id: int,
    clue_ids: list[int],
    title: str,
    lead_text: str,
    chapter: int = 1,
    turn_created: int | None = None,
) -> int:
    """Creates a verified deduction breakthrough linking parent clues and applying quest breakthrough shortcuts."""
    inherited_npc = ""
    inherited_qid = ""
    for pid in clue_ids:
        cl = get_session_clue_by_id(pid)
        if cl:
            if not inherited_npc and cl.get("linked_npc"):
                inherited_npc = str(cl["linked_npc"]).strip()
            if not inherited_qid and cl.get("quest_id"):
                inherited_qid = str(cl["quest_id"]).strip()

    cid = add_session_clue(
        session_id=session_id,
        title=title,
        lead_text=lead_text,
        category="deduction",
        source_location="Mind Palace / Caseboard",
        linked_npc=inherited_npc,
        quest_id=inherited_qid,
        chapter=chapter,
        is_verified=1,
        deduction_parents=clue_ids,
        turn_created=turn_created,
    )
    for parent_id in clue_ids:
        verify_session_clue(parent_id)
        try:
            with get_conn() as conn:
                conn.execute("UPDATE session_clues SET is_consumed=1, updated_at=? WHERE id=?", (time.time(), parent_id))
        except sqlite3.OperationalError:
            pass

    apply_caseboard_breakthrough_to_quests(session_id, clue_ids, title, lead_text)
    return cid

def save_quest_waypoints(session_id: int, quest_id: str, waypoints: list, sub_obj_id: int | None = None):
    """Bulk upsert waypoints for a quest or sub-objective.
    Stage 1 starts as 'active', all others start as 'locked'.
    sub_obj_id=None means the waypoints belong to the whole quest (bounties).
    sub_obj_id=N means they belong to Story Quest sub-objective N.
    """
    if not waypoints:
        return
    now = time.time()
    with get_conn() as conn:
        # Clear existing waypoints for this quest+sub_obj combo first
        if sub_obj_id is None:
            conn.execute(
                "DELETE FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL",
                (session_id, quest_id)
            )
        else:
            conn.execute(
                "DELETE FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id=?",
                (session_id, quest_id, sub_obj_id)
            )
        for i, wp in enumerate(waypoints):
            if not isinstance(wp, dict):
                continue
            stage_idx = int(wp.get("stage_index", i + 1))
            status = wp.get("status") if wp.get("status") in ("active", "locked", "completed", "failed") else ("active" if stage_idx == 1 else "locked")
            target_loc = str(wp.get("target_location", ""))[:200]
            target_node = str(wp.get("target_node_id", "") or "").strip()
            if not target_node and target_loc:
                try:
                    target_node = db.resolve_node_id_from_location(session_id, target_loc) or ""
                except Exception:
                    target_node = ""
            follow_sched = int(bool(wp.get("follow_npc_schedule", 1 if wp.get("target_npc") else 0)))
            req_item = str(wp.get("required_item", "") or "")[:100]
            phases_val = wp.get("valid_time_phases") or wp.get("valid_time_phases_json") or []
            phases_str = json.dumps(phases_val) if isinstance(phases_val, list) else str(phases_val or "[]")
            appr_val = wp.get("approaches") or wp.get("approaches_json") or []
            appr_str = json.dumps(appr_val) if isinstance(appr_val, list) else str(appr_val or "[]")
            conn.execute(
                """INSERT OR REPLACE INTO quest_waypoints
                   (session_id, quest_id, sub_obj_id, stage_index, stage_label,
                    target_location, target_node_id, target_npc, completion_trigger,
                    resource_target, resource_collected, status,
                    follow_npc_schedule, required_item, valid_time_phases_json, approaches_json,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id, quest_id, sub_obj_id, stage_idx,
                    str(wp.get("stage_label", ""))[:200],
                    target_loc,
                    target_node,
                    str(wp.get("target_npc", "") or "")[:100],
                    str(wp.get("completion_trigger", "arrival")),
                    int(wp.get("resource_target", 0)),
                    0,  # resource_collected always starts at 0
                    status,
                    follow_sched,
                    req_item,
                    phases_str,
                    appr_str,
                    now, now
                )
            )

def _hydrate_waypoint_row(row) -> dict | None:
    if not row:
        return None
    d = dict(row)
    try:
        vp_raw = d.get("valid_time_phases_json") or "[]"
        d["valid_time_phases"] = json.loads(vp_raw) if isinstance(vp_raw, str) else (vp_raw or [])
    except Exception:
        d["valid_time_phases"] = []
    try:
        ap_raw = d.get("approaches_json") or "[]"
        d["approaches"] = json.loads(ap_raw) if isinstance(ap_raw, str) else (ap_raw or [])
    except Exception:
        d["approaches"] = []
    return d

def get_active_waypoint(session_id: int, quest_id: str, sub_obj_id: int | None = None) -> dict | None:
    """Returns the first 'active' waypoint for this quest/sub-objective, or None.
    When `sub_obj_id is None` and no legacy `sub_obj_id IS NULL` rows exist, falls back to
    `sub_obj_id = 0` (the Main Objective track of structured `1 Main + 1-3 Optionals` quests).
    """
    with get_conn() as conn:
        if sub_obj_id is None:
            has_legacy = conn.execute(
                "SELECT 1 FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL LIMIT 1",
                (session_id, quest_id),
            ).fetchone()
            eff_sub_id = None if has_legacy else 0
        else:
            eff_sub_id = sub_obj_id

        if eff_sub_id is None:
            row = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND status='active'
                   ORDER BY stage_index ASC LIMIT 1""",
                (session_id, quest_id)
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND status='active'
                   ORDER BY stage_index ASC LIMIT 1""",
                (session_id, quest_id, eff_sub_id)
            ).fetchone()
        return _hydrate_waypoint_row(row)

def get_quest_waypoints(session_id: int, quest_id: str, sub_obj_id: int | None = None) -> list[dict]:
    """Returns all waypoints for this quest/sub-objective ordered by stage_index ASC.
    When `sub_obj_id is None` and no legacy `sub_obj_id IS NULL` rows exist, falls back to
    `sub_obj_id = 0` (the Main Objective track of structured `1 Main + 1-3 Optionals` quests).
    """
    with get_conn() as conn:
        if sub_obj_id is None:
            rows = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL
                   ORDER BY stage_index ASC""",
                (session_id, quest_id)
            ).fetchall()
            if not rows:
                rows = conn.execute(
                    """SELECT * FROM quest_waypoints
                       WHERE session_id=? AND quest_id=? AND sub_obj_id=0
                       ORDER BY stage_index ASC""",
                    (session_id, quest_id)
                ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id=?
                   ORDER BY stage_index ASC""",
                (session_id, quest_id, sub_obj_id)
            ).fetchall()
        return [_hydrate_waypoint_row(r) for r in rows if r]

def advance_waypoint(session_id: int, quest_id: str, stage_index: int, sub_obj_id: int | None = None) -> dict | None:
    """Marks the given stage as 'completed', unlocks the next 'locked' stage to 'active'.
    Returns the newly-unlocked waypoint dict, or None if no more stages remain (quest chain done).
    When `sub_obj_id is None` and no legacy `sub_obj_id IS NULL` rows exist, falls back to
    `sub_obj_id = 0` (the Main Objective track of structured `1 Main + 1-3 Optionals` quests).
    """
    now = time.time()
    with get_conn() as conn:
        if sub_obj_id is None:
            has_legacy = conn.execute(
                "SELECT 1 FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL LIMIT 1",
                (session_id, quest_id),
            ).fetchone()
            eff_sub_id = None if has_legacy else 0
        else:
            eff_sub_id = sub_obj_id

        if eff_sub_id is None:
            conn.execute(
                "UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND stage_index=?",
                (now, session_id, quest_id, stage_index)
            )
            next_row = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND status='locked'
                   ORDER BY stage_index ASC LIMIT 1""",
                (session_id, quest_id)
            ).fetchone()
            if next_row:
                conn.execute(
                    "UPDATE quest_waypoints SET status='active', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND stage_index=?",
                    (now, session_id, quest_id, next_row["stage_index"])
                )
            tot_row = conn.execute(
                "SELECT COUNT(*) as c FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL",
                (session_id, quest_id)
            ).fetchone()
            don_row = conn.execute(
                "SELECT COUNT(*) as c FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND status='completed'",
                (session_id, quest_id)
            ).fetchone()
            tot = tot_row["c"] if tot_row else 0
            don = don_row["c"] if don_row else 0
            if tot > 0:
                conn.execute(
                    "UPDATE quests SET progress=?, updated_at=? WHERE session_id=? AND quest_id=?",
                    (f"{don}/{tot} Milestones", now, session_id, quest_id)
                )
        else:
            conn.execute(
                "UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND stage_index=?",
                (now, session_id, quest_id, eff_sub_id, stage_index)
            )
            next_row = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND status='locked'
                   ORDER BY stage_index ASC LIMIT 1""",
                (session_id, quest_id, eff_sub_id)
            ).fetchone()
            if next_row:
                conn.execute(
                    "UPDATE quest_waypoints SET status='active', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND stage_index=?",
                    (now, session_id, quest_id, eff_sub_id, next_row["stage_index"])
                )
            tot_row = conn.execute(
                "SELECT COUNT(*) as c FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id=?",
                (session_id, quest_id, eff_sub_id)
            ).fetchone()
            don_row = conn.execute(
                "SELECT COUNT(*) as c FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND status='completed'",
                (session_id, quest_id, eff_sub_id)
            ).fetchone()
            tot = tot_row["c"] if tot_row else 0
            don = don_row["c"] if don_row else 0
            if tot > 0:
                prefix_lbl = "Main Objective" if eff_sub_id == 0 else f"Optional #{eff_sub_id}"
                conn.execute(
                    "UPDATE quests SET progress=?, updated_at=? WHERE session_id=? AND quest_id=?",
                    (f"{don}/{tot} {prefix_lbl} Stages", now, session_id, quest_id)
                )
        return dict(next_row) if next_row else None


def unlock_climax_waypoint(
    session_id: int,
    quest_id: str,
    climax_loc: str = "",
    target_npc: str = "",
) -> int:
    """Promotes a 'locked' climax/Main stage in quest_waypoints to 'active' when climax_spec['is_unlocked'] becomes True."""
    now = time.time()
    with get_conn() as conn:
        row = None
        if climax_loc:
            row = conn.execute(
                """SELECT id, stage_index FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND (sub_obj_id IS NULL OR sub_obj_id=0) AND status='locked'
                     AND (target_location=? OR ? LIKE '%' || target_location || '%')
                   ORDER BY COALESCE(sub_obj_id, 0) ASC, stage_index ASC LIMIT 1""",
                (session_id, quest_id, climax_loc, climax_loc),
            ).fetchone()
        if not row:
            row = conn.execute(
                """SELECT id, stage_index FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND (sub_obj_id IS NULL OR sub_obj_id=0) AND status='locked'
                   ORDER BY COALESCE(sub_obj_id, 0) ASC, stage_index ASC LIMIT 1""",
                (session_id, quest_id),
            ).fetchone()
        if row:
            conn.execute(
                "UPDATE quest_waypoints SET status='active', target_npc=CASE WHEN target_npc='' OR target_npc IS NULL THEN ? ELSE target_npc END, updated_at=? WHERE id=?",
                (target_npc or "", now, row["id"]),
            )
            return 1
        return 0


promote_locked_quest_waypoints = unlock_climax_waypoint

def update_waypoint_resource_progress(session_id: int, quest_id: str, stage_index: int, delta: int, sub_obj_id: int | None = None) -> dict:
    """Increment resource_collected for a gathering waypoint.
    Returns {collected, target, complete} after update.
    """
    now = time.time()
    with get_conn() as conn:
        if sub_obj_id is None:
            conn.execute(
                "UPDATE quest_waypoints SET resource_collected=MAX(0, resource_collected+?), updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND stage_index=?",
                (delta, now, session_id, quest_id, stage_index)
            )
            row = conn.execute(
                "SELECT resource_collected, resource_target FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND stage_index=?",
                (session_id, quest_id, stage_index)
            ).fetchone()
        else:
            conn.execute(
                "UPDATE quest_waypoints SET resource_collected=MAX(0, resource_collected+?), updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND stage_index=?",
                (delta, now, session_id, quest_id, sub_obj_id, stage_index)
            )
            row = conn.execute(
                "SELECT resource_collected, resource_target FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND stage_index=?",
                (session_id, quest_id, sub_obj_id, stage_index)
            ).fetchone()
        if row:
            collected = row["resource_collected"]
            target = row["resource_target"]
            return {"collected": collected, "target": target, "complete": target > 0 and collected >= target}
        return {"collected": 0, "target": 0, "complete": False}

def get_all_session_active_waypoints(session_id: int) -> list[dict]:
    """Returns all 'active' waypoints across all quests in a session.
    Used by the location UI to show quest markers on the travel menu.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT qw.*, q.title as quest_title, q.quest_type, q.is_story_quest, q.sub_objectives_json,
                      q.blueprint_id, q.client_npc, q.client_location,
                      q.required_item as quest_required_item, q.required_item_count,
                      q.reward_gold, q.strikes, q.max_strikes, q.resolution_approach, q.quest_notes,
                      q.deadline_day, q.deadline_minute
               FROM quest_waypoints qw
               JOIN quests q ON qw.session_id = q.session_id AND qw.quest_id = q.quest_id
               WHERE qw.session_id=? AND qw.status='active' AND q.status='Active'
               ORDER BY qw.quest_id, qw.sub_obj_id, qw.stage_index""",
            (session_id,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                vp_raw = d.get("valid_time_phases_json") or "[]"
                d["valid_time_phases"] = json.loads(vp_raw) if isinstance(vp_raw, str) else (vp_raw or [])
            except Exception:
                d["valid_time_phases"] = []
            try:
                appr_raw = d.get("approaches_json") or "[]"
                d["approaches"] = json.loads(appr_raw) if isinstance(appr_raw, str) else (appr_raw or [])
            except Exception:
                d["approaches"] = []
            if d.get("target_location"):
                d["target_location"] = _normalize_loc_arrow(d["target_location"])
            d["static_target_location"] = d.get("target_location", "")
            if d.get("follow_npc_schedule") and d.get("target_npc"):
                try:
                    from mechanics.world.waypoints.matching import resolve_effective_waypoint_location
                    eff_loc = resolve_effective_waypoint_location(session_id, d)
                    if eff_loc:
                        d["live_scheduled_location"] = _normalize_loc_arrow(eff_loc)
                        d["target_location"] = _normalize_loc_arrow(eff_loc)
                except Exception:
                    pass
            so_json = d.get("sub_objectives_json")
            sub_id = d.get("sub_obj_id")
            if so_json and sub_id is not None:
                try:
                    sos = json.loads(so_json) if isinstance(so_json, str) else so_json
                    if isinstance(sos, list):
                        if any(
                            isinstance(s, dict)
                            and int(s.get("id", -1)) == int(sub_id)
                            and (
                                bool(s.get("completed"))
                                or not bool(s.get("is_discovered", True))
                                or str(s.get("status") or "active").lower() in ("completed", "failed", "bypassed", "locked_out")
                            )
                            for s in sos
                        ):
                            continue
                except Exception:
                    pass
            result.append(d)
        return result

def mark_sub_objective_completed_in_quest(session_id: int, quest_id: str, sub_obj_id: int):
    """Directly marks a quest sub-objective as completed=True in sub_objectives_json.
    Called by the waypoint engine when all waypoint stages for that sub-obj are done.
    Preserves hidden Optionals and only auto-unlocks `sub_obj_id + 1` on legacy sequential quests.
    """
    now = time.time()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT sub_objectives_json FROM quests WHERE session_id=? AND quest_id=?",
            (session_id, quest_id),
        ).fetchone()
        if not row:
            return
        try:
            sub_objs = json.loads(row["sub_objectives_json"] or "[]")
        except Exception:
            sub_objs = []
        if not isinstance(sub_objs, list):
            return
        is_structured = any(
            isinstance(so, dict) and ("is_optional" in so or _safe_int_db(so.get("id"), -1) == 0)
            for so in sub_objs
        )
        changed = False
        for so in sub_objs:
            if isinstance(so, dict) and int(so.get("id", -1)) == int(sub_obj_id):
                if not so.get("completed") or str(so.get("status") or "") != "completed":
                    so["completed"] = True
                    so["status"] = "completed"
                    changed = True
                break
        if changed:
            conn.execute(
                "UPDATE quests SET sub_objectives_json=?, updated_at=? WHERE session_id=? AND quest_id=?",
                (_clean_sub_objectives_for_storage(sub_objs), now, session_id, quest_id),
            )
            if not is_structured:
                conn.execute(
                    "UPDATE quest_waypoints SET status='active', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND stage_index=1 AND status='locked'",
                    (now, session_id, quest_id, int(sub_obj_id) + 1),
                )


def sync_quest_projection_from_dossier(
    session_id: int,
    quest_id: str,
    dossier: Optional[dict] = None,
    conn: Optional[sqlite3.Connection] = None,
    is_rollback: bool = False,
) -> list[dict]:
    """Deterministically projects `1 Main Objective + 1-3 Optionals` from `quest_dossiers`
    into `quests.sub_objectives_json` and `quest_waypoints` inside a single SQLite transaction.
    Used both at compilation/turn resolution AND during atomic `/rollback`.
    """
    now = time.time()

    def _run(c: sqlite3.Connection) -> list[dict]:
        eff_dossier = dossier or get_quest_dossier(session_id, quest_id, conn=c)
        if not eff_dossier or str(eff_dossier.get("status_stage") or "pitch") == "pitch":
            return []

        climax_spec = dict(eff_dossier.get("climax_spec") or {})
        leads_graph = [dict(ld) for ld in (eff_dossier.get("leads_graph") or []) if isinstance(ld, dict)]
        main_stages = [dict(st) for st in (climax_spec.get("main_stages") or []) if isinstance(st, dict)]

        if not main_stages and not climax_spec.get("has_structured_model"):
            # Pre-overhaul dossier format without `main_stages` — leave untouched
            return []

        q_row = c.execute(
            "SELECT objective, status FROM quests WHERE session_id=? AND quest_id=?",
            (session_id, quest_id),
        ).fetchone()
        if not q_row:
            return []

        alt_completed = any(
            str(ld.get("role") or "").lower() == "alternative"
            and str(ld.get("status") or "").lower() == "completed"
            for ld in leads_graph
        )
        climax_done = bool(
            climax_spec.get("completed")
            or str(climax_spec.get("status") or "").lower() == "completed"
            or alt_completed
            or str(q_row["status"] or "") == "Completed"
        )

        # Remove any stale un-indexed (`sub_obj_id IS NULL`) rows on structured quests
        c.execute(
            "DELETE FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL",
            (session_id, quest_id),
        )

        # 1. Materialize Main Objective stages (`sub_obj_id = 0`)
        if not main_stages:
            main_stages = [
                {
                    "stage_index": 1,
                    "stage_label": str(climax_spec.get("label") or q_row["objective"] or "Complete Main Objective"),
                    "target_location": _normalize_loc_arrow(str(climax_spec.get("target_location") or "")),
                    "target_npc": str(climax_spec.get("target_npc") or ""),
                    "completion_trigger": str(climax_spec.get("completion_trigger") or "action"),
                    "approaches": list(climax_spec.get("approaches") or []),
                    "status": "completed" if climax_done else ("active" if climax_spec.get("is_unlocked", True) else "locked"),
                }
            ]

        gate_kind = str(climax_spec.get("gate_type") or climax_spec.get("gate_mode") or "open").lower()
        secret_gate_unlocked = bool(gate_kind == "secret" and climax_spec.get("is_unlocked", False))
        active_assigned = False
        resolved_main_stages: list[dict] = []
        for idx_zero, st in enumerate(main_stages):
            st_idx = int(st.get("stage_index") or (idx_zero + 1))
            raw_st_status = str(st.get("status") or "").lower()
            if climax_done or raw_st_status in ("completed", "bypassed"):
                eff_st_status = "completed"
            elif secret_gate_unlocked and st_idx == len(main_stages):
                eff_st_status = "active"
            elif not active_assigned:
                active_assigned = True
                is_secret_gate_stage = bool(
                    gate_kind == "secret"
                    and not bool(climax_spec.get("is_unlocked", False))
                    and (st_idx == len(main_stages) or bool(climax_spec.get("secret_lair_locked")))
                )
                eff_st_status = "locked" if is_secret_gate_stage else "active"
            else:
                eff_st_status = "locked"

            st_loc = _normalize_loc_arrow(str(st.get("target_location") or climax_spec.get("target_location") or ""))
            st_npc = str(st.get("target_npc") or (climax_spec.get("target_npc") if st_idx == len(main_stages) else "") or "")
            st_label = str(st.get("stage_label") or st.get("label") or climax_spec.get("label") or f"Stage {st_idx}")
            st_trig = str(st.get("completion_trigger") or "action")
            st_appr = json.dumps(list(st.get("approaches") or climax_spec.get("approaches") or []))
            follow_sched = int(bool(st.get("follow_npc_schedule", bool(st_npc))))

            existing_wp = c.execute(
                "SELECT id, status FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id=0 AND stage_index=?",
                (session_id, quest_id, st_idx),
            ).fetchone()
            if existing_wp:
                if not is_rollback and existing_wp["status"] in ("completed", "bypassed"):
                    eff_st_status = existing_wp["status"]
                c.execute(
                    """UPDATE quest_waypoints
                       SET stage_label=?, target_location=?, target_npc=?, completion_trigger=?,
                           status=?, follow_npc_schedule=?, approaches_json=?, updated_at=?
                       WHERE id=?""",
                    (st_label, st_loc, st_npc, st_trig, eff_st_status, follow_sched, st_appr, now, existing_wp["id"]),
                )
            else:
                c.execute(
                    """INSERT INTO quest_waypoints
                       (session_id, quest_id, sub_obj_id, stage_index, stage_label, target_location,
                        target_npc, completion_trigger, resource_target, resource_collected, status,
                        follow_npc_schedule, valid_time_phases_json, approaches_json, created_at, updated_at)
                       VALUES (?, ?, 0, ?, ?, ?, ?, ?, 0, 0, ?, ?, '[]', ?, ?, ?)""",
                    (session_id, quest_id, st_idx, st_label, st_loc, st_npc, st_trig, eff_st_status, follow_sched, st_appr, now, now),
                )
            resolved_main_stages.append(
                {
                    "stage_index": st_idx,
                    "target_location": st_loc,
                    "target_npc": st_npc,
                    "status": eff_st_status,
                }
            )

        c.execute(
            "DELETE FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id=0 AND stage_index > ?",
            (session_id, quest_id, len(main_stages)),
        )

        all_main_stages_done = bool(resolved_main_stages) and all(s["status"] == "completed" for s in resolved_main_stages)
        main_done_final = bool(climax_done or all_main_stages_done)
        cur_main_stage = next((s for s in resolved_main_stages if s["status"] != "completed"), resolved_main_stages[-1])

        projected_sos: list[dict] = [
            {
                "id": 0,
                "text": str(climax_spec.get("main_objective_text") or climax_spec.get("label") or q_row["objective"] or ""),
                "is_optional": False,
                "is_main": True,
                "role": "main",
                "is_discovered": True,
                "status": "completed" if main_done_final else "active",
                "completed": main_done_final,
                "target_location": cur_main_stage["target_location"],
                "target_npc": cur_main_stage["target_npc"],
            }
        ]

        # 2. Materialize Optional Objectives (`sub_obj_id = 1..3`, 1 stage each)
        valid_opt_ids: list[int] = []
        for idx_opt, ld in enumerate(leads_graph, start=1):
            opt_sub_id = int(ld.get("sub_obj_id") or idx_opt)
            valid_opt_ids.append(opt_sub_id)
            opt_role = str(ld.get("role") or "aid").lower()
            is_disc = bool(ld.get("is_discovered", True))
            ld_status = str(ld.get("status") or "active").lower()
            if ld_status not in ("active", "completed", "failed", "bypassed", "locked_out"):
                ld_status = "active"
            opt_loc = _normalize_loc_arrow(str(ld.get("target_location") or ""))
            opt_npc = str(ld.get("target_npc") or "")
            opt_label = str(ld.get("label") or f"Optional Lead {idx_opt}")
            opt_appr = json.dumps(list(ld.get("approaches") or []))
            opt_follow = int(bool(ld.get("follow_npc_schedule", bool(opt_npc))))

            if ld_status == "completed":
                wp_status = "completed"
            elif not is_disc or ld_status in ("failed", "bypassed", "locked_out"):
                wp_status = "locked"
            else:
                wp_status = "active"

            existing_opt_wp = c.execute(
                "SELECT id FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND stage_index=1",
                (session_id, quest_id, opt_sub_id),
            ).fetchone()
            if existing_opt_wp:
                c.execute(
                    """UPDATE quest_waypoints
                       SET stage_label=?, target_location=?, target_npc=?, completion_trigger=?,
                           status=?, follow_npc_schedule=?, approaches_json=?, updated_at=?
                       WHERE id=?""",
                    (opt_label, opt_loc, opt_npc, str(ld.get("completion_trigger") or "action"), wp_status, opt_follow, opt_appr, now, existing_opt_wp["id"]),
                )
            else:
                c.execute(
                    """INSERT INTO quest_waypoints
                       (session_id, quest_id, sub_obj_id, stage_index, stage_label, target_location,
                        target_npc, completion_trigger, resource_target, resource_collected, status,
                        follow_npc_schedule, valid_time_phases_json, approaches_json, created_at, updated_at)
                       VALUES (?, ?, ?, 1, ?, ?, ?, ?, 0, 0, ?, ?, '[]', ?, ?, ?)""",
                    (session_id, quest_id, opt_sub_id, opt_label, opt_loc, opt_npc, str(ld.get("completion_trigger") or "action"), wp_status, opt_follow, opt_appr, now, now),
                )

            projected_sos.append(
                {
                    "id": opt_sub_id,
                    "optional_id": str(ld.get("optional_id") or ld.get("lead_id") or f"opt_{idx_opt}"),
                    "lead_id": str(ld.get("lead_id") or f"opt_{idx_opt}"),
                    "text": opt_label,
                    "is_optional": True,
                    "is_main": False,
                    "role": opt_role,
                    "badge": str(ld.get("badge") or f"Optional — {opt_role.title()}"),
                    "stakes_hint": str(ld.get("stakes_hint") or ""),
                    "is_discovered": is_disc,
                    "unlock_trigger": str(ld.get("unlock_trigger") or "upfront"),
                    "status": ld_status,
                    "completed": ld_status == "completed",
                    "target_location": opt_loc,
                    "target_npc": opt_npc,
                    "field_bonus": dict(ld.get("field_bonus") or {}),
                    "bonus_claimed": bool(ld.get("bonus_claimed", False)),
                    "rival_faction_slug": str(ld.get("rival_faction_slug") or ""),
                    "opposing_faction_slug": str(ld.get("opposing_faction_slug") or ""),
                    "implicated_ally_npc": str(ld.get("implicated_ally_npc") or ""),
                    "lockout_reason": str(ld.get("lockout_reason") or ""),
                }
            )

        if valid_opt_ids:
            q_marks = ",".join("?" * len(valid_opt_ids))
            c.execute(
                f"DELETE FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id > 0 AND sub_obj_id NOT IN ({q_marks})",
                [session_id, quest_id, *valid_opt_ids],
            )
        else:
            c.execute(
                "DELETE FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id > 0",
                (session_id, quest_id),
            )
        c.execute(
            "DELETE FROM quest_waypoints WHERE session_id=? AND quest_id=? AND (sub_obj_id IS NULL OR (sub_obj_id > 0 AND stage_index > 1))",
            (session_id, quest_id),
        )

        c.execute(
            """UPDATE quests
               SET sub_objectives_json=?,
                   dossier_stage=CASE WHEN dossier_stage IN ('legacy', 'pitch', '') OR dossier_stage IS NULL THEN 'compiled' ELSE dossier_stage END,
                   updated_at=?
               WHERE session_id=? AND quest_id=?""",
            (_clean_sub_objectives_for_storage(projected_sos), now, session_id, quest_id),
        )
        return projected_sos

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


# -----------------------------------------------------------------------------
# Phase 2 Strike Counter, Resolution Approach & Failure CRUD
# -----------------------------------------------------------------------------

def increment_quest_strikes(session_id: int, quest_id: str, delta: int = 1) -> dict:
    """Atomically increments strikes on a quest up to max_strikes (default 2).
    Updates quest.progress with a warning note if not yet failed.
    Returns: {strikes, max_strikes, failed: bool, quest: dict}
    """
    now = time.time()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT strikes, max_strikes, progress, title FROM quests WHERE session_id=? AND quest_id=?",
            (session_id, quest_id)
        ).fetchone()
        if not row:
            return {"strikes": 0, "max_strikes": 2, "failed": False, "quest": None}

        curr_strikes = int(row["strikes"] or 0)
        max_s = int(row["max_strikes"] or 2)
        new_strikes = min(max_s, curr_strikes + max(1, delta))
        failed = new_strikes >= max_s

        prog = str(row["progress"] or "")
        if not failed:
            alert_tag = f"[⚠️ {new_strikes}/{max_s} Strikes: Target Alerted]"
            if "[⚠️" in prog:
                prog = re.sub(r'\[⚠️ \d+/\d+ Strikes: Target Alerted\]', alert_tag, prog)
            else:
                prog = f"{prog} {alert_tag}".strip()

        conn.execute(
            "UPDATE quests SET strikes=?, progress=?, updated_at=? WHERE session_id=? AND quest_id=?",
            (new_strikes, prog, now, session_id, quest_id)
        )

    updated_q = get_quest_by_id(session_id, quest_id)
    return {
        "strikes": new_strikes,
        "max_strikes": max_s,
        "failed": failed,
        "quest": updated_q,
    }


def reset_quest_strikes(session_id: int, quest_id: str) -> None:
    """Resets strikes to 0 for a quest (used on story quest fail-forward)."""
    now = time.time()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT progress FROM quests WHERE session_id=? AND quest_id=?",
            (session_id, quest_id)
        ).fetchone()
        clean_prog = ""
        if row and row["progress"]:
            clean_prog = re.sub(r'\s*\[⚠️ \d+/\d+ Strikes: Target Alerted\]', '', str(row["progress"])).strip()
        conn.execute(
            "UPDATE quests SET strikes=0, progress=?, updated_at=? WHERE session_id=? AND quest_id=?",
            (clean_prog, now, session_id, quest_id)
        )


def set_quest_resolution_approach(session_id: int, quest_id: str, resolution_approach: str) -> dict | None:
    """Updates the resolution_approach on a quest."""
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "UPDATE quests SET resolution_approach=?, updated_at=? WHERE session_id=? AND quest_id=?",
            (str(resolution_approach or ""), now, session_id, quest_id)
        )
    return get_quest_by_id(session_id, quest_id)


def fail_quest_and_waypoints(
    session_id: int,
    quest_id: str,
    resolution_approach: str = "failed_strikes",
    progress_note: str = "Failed",
) -> dict | None:
    """
    Deterministically marks a quest as 'Failed' and sets all non-completed waypoints to 'failed'.
    """
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            """UPDATE quests
               SET status='Failed', resolution_approach=?, progress=?, updated_at=?
               WHERE session_id=? AND quest_id=?""",
            (str(resolution_approach or "failed_strikes"), str(progress_note or "Failed"), now, session_id, quest_id)
        )
        conn.execute(
            """UPDATE quest_waypoints
               SET status='failed', updated_at=?
               WHERE session_id=? AND quest_id=? AND status IN ('active', 'locked')""",
            (now, session_id, quest_id)
        )
    return get_quest_by_id(session_id, quest_id)


def expire_quest_and_waypoints(
    session_id: int,
    quest_id: str,
    progress_note: str = "Failed (Contract Expired — Claimed by Rival)"
) -> dict | None:
    """Marks a timed quest as Failed due to deadline expiration (`expired_deadline`)."""
    return fail_quest_and_waypoints(
        session_id=session_id,
        quest_id=quest_id,
        resolution_approach="expired_deadline",
        progress_note=progress_note,
    )


