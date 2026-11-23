"""Campaign goals, chapters, quest waypoints, split-brain healing, and dossier projection sync."""
from __future__ import annotations

import json
import re
import sqlite3
import time
from typing import Any, Optional

import db
from ..core import UnitOfWork, _safe_int_db, get_conn
from ..dossiers import (
    append_dossier_state_event,
    get_effective_session_turn,
    get_quest_dossier,
)
from .core import (
    _clean_sub_objectives_for_storage,
    _normalize_loc_arrow,
    _preload_waypoint_schedule_ctx,
)


def update_session_campaign_goals(session_id: int, goals: list):
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET campaign_end_goals_json=?, updated_at=? WHERE id=?",
            (json.dumps(goals), time.time(), session_id),
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
            (chapter, time.time(), session_id),
        )


def get_session_chapter(session_id: int) -> int:
    session = db.get_session(session_id)
    if not session:
        return 1
    return session.get("current_chapter", 1) or 1


def save_quest_waypoints(
    session_id: int, quest_id: str, waypoints: list, sub_obj_id: int | None = None
):
    """Bulk upsert waypoints for a quest or sub-objective."""
    if not waypoints:
        return
    now = time.time()
    node_id_cache: dict[str, str] = {}
    with UnitOfWork() as conn:
        if sub_obj_id is None:
            conn.execute(
                "DELETE FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL",
                (session_id, quest_id),
            )
        else:
            conn.execute(
                "DELETE FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id=?",
                (session_id, quest_id, sub_obj_id),
            )
        rows_to_insert: list[tuple[Any, ...]] = []
        for i, wp in enumerate(waypoints):
            if not isinstance(wp, dict):
                continue
            stage_idx = int(wp.get("stage_index", i + 1))
            status = (
                wp.get("status")
                if wp.get("status") in ("active", "locked", "completed", "failed")
                else ("active" if stage_idx == 1 else "locked")
            )
            target_loc = str(wp.get("target_location", ""))[:200]
            target_node = str(wp.get("target_node_id", "") or "").strip()
            if not target_node and target_loc:
                if target_loc in node_id_cache:
                    target_node = node_id_cache[target_loc]
                else:
                    try:
                        target_node = (
                            db.resolve_node_id_from_location(session_id, target_loc) or ""
                        )
                    except Exception:
                        target_node = ""
                    node_id_cache[target_loc] = target_node
            follow_sched = int(
                bool(wp.get("follow_npc_schedule", 1 if wp.get("target_npc") else 0))
            )
            req_item = str(wp.get("required_item", "") or "")[:100]
            phases_val = wp.get("valid_time_phases") or wp.get("valid_time_phases_json") or []
            phases_str = (
                json.dumps(phases_val) if isinstance(phases_val, list) else str(phases_val or "[]")
            )
            appr_val = wp.get("approaches") or wp.get("approaches_json") or []
            appr_str = (
                json.dumps(appr_val) if isinstance(appr_val, list) else str(appr_val or "[]")
            )
            rows_to_insert.append(
                (
                    session_id,
                    quest_id,
                    sub_obj_id,
                    stage_idx,
                    str(wp.get("stage_label", ""))[:200],
                    target_loc,
                    target_node,
                    str(wp.get("target_npc", "") or "")[:100],
                    str(wp.get("completion_trigger", "arrival")),
                    int(wp.get("resource_target", 0)),
                    0,
                    status,
                    follow_sched,
                    req_item,
                    phases_str,
                    appr_str,
                    now,
                    now,
                )
            )
        if rows_to_insert:
            conn.executemany(
                """INSERT OR REPLACE INTO quest_waypoints
                   (session_id, quest_id, sub_obj_id, stage_index, stage_label,
                    target_location, target_node_id, target_npc, completion_trigger,
                    resource_target, resource_collected, status,
                    follow_npc_schedule, required_item, valid_time_phases_json, approaches_json,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows_to_insert,
            )


def _hydrate_waypoint_row(row) -> dict | None:
    if not row:
        return None
    d = dict(row)
    try:
        vp_raw = d.get("valid_time_phases_json") or "[]"
        d["valid_time_phases"] = (
            json.loads(vp_raw) if isinstance(vp_raw, str) else (vp_raw or [])
        )
    except Exception:
        d["valid_time_phases"] = []
    try:
        ap_raw = d.get("approaches_json") or "[]"
        d["approaches"] = json.loads(ap_raw) if isinstance(ap_raw, str) else (ap_raw or [])
    except Exception:
        d["approaches"] = []
    return d


def get_active_waypoint(
    session_id: int, quest_id: str, sub_obj_id: int | None = None
) -> dict | None:
    """Returns the first 'active' waypoint for this quest/sub-objective, or None."""
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
                (session_id, quest_id),
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND status='active'
                   ORDER BY stage_index ASC LIMIT 1""",
                (session_id, quest_id, eff_sub_id),
            ).fetchone()
        return _hydrate_waypoint_row(row)


def get_quest_waypoints(
    session_id: int, quest_id: str, sub_obj_id: int | None = None
) -> list[dict]:
    """Returns all waypoints for this quest/sub-objective ordered by stage_index ASC."""
    with get_conn() as conn:
        if sub_obj_id is None:
            rows = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL
                   ORDER BY stage_index ASC""",
                (session_id, quest_id),
            ).fetchall()
            if not rows:
                rows = conn.execute(
                    """SELECT * FROM quest_waypoints
                       WHERE session_id=? AND quest_id=? AND sub_obj_id=0
                       ORDER BY stage_index ASC""",
                    (session_id, quest_id),
                ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id=?
                   ORDER BY stage_index ASC""",
                (session_id, quest_id, sub_obj_id),
            ).fetchall()
        return [_hydrate_waypoint_row(r) for r in rows if r]


def advance_waypoint(
    session_id: int, quest_id: str, stage_index: int, sub_obj_id: int | None = None
) -> dict | None:
    """Marks the given stage as 'completed', unlocks the next 'locked' stage to 'active'."""
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

        is_legacy_stage0 = eff_sub_id is None and int(stage_index) == 0
        if eff_sub_id in (None, 0) and not is_legacy_stage0:
            dos = get_quest_dossier(session_id, quest_id, conn=conn)
            climax_dos = dict((dos or {}).get("climax_spec") or {})
            main_stages_dos = [
                dict(s) for s in (climax_dos.get("main_stages") or []) if isinstance(s, dict)
            ]
            if (
                dos
                and str(dos.get("status_stage") or "pitch") != "pitch"
                and (main_stages_dos or climax_dos.get("has_structured_model"))
            ):
                prev_climax_dos = json.loads(json.dumps(climax_dos))
                if main_stages_dos:
                    tot_dos = len(main_stages_dos)
                    gate_kind_dos = str(
                        climax_dos.get("gate_type") or climax_dos.get("gate_mode") or "open"
                    ).lower()
                    for idx_d, st_d in enumerate(main_stages_dos):
                        s_i = int(st_d.get("stage_index") or (idx_d + 1))
                        cur_stat_d = str(st_d.get("status") or "").lower()
                        if s_i <= int(stage_index):
                            if cur_stat_d not in ("completed", "bypassed") and not st_d.get(
                                "completed"
                            ):
                                st_d["status"] = "completed"
                                st_d["completed"] = True
                                if not st_d.get("is_climax_stage") and s_i < tot_dos:
                                    st_d["_clock_decrement_pending"] = True
                        main_stages_dos[idx_d] = st_d
                    if (
                        int(stage_index) >= tot_dos - 1
                        and tot_dos >= 2
                        and gate_kind_dos == "secret"
                    ):
                        climax_dos["is_unlocked"] = True
                        climax_dos["secret_lair_locked"] = False
                    for idx_d, st_d in enumerate(main_stages_dos):
                        s_i = int(st_d.get("stage_index") or (idx_d + 1))
                        if s_i == int(stage_index) + 1:
                            is_clx_d = bool(st_d.get("is_climax_stage") or s_i == tot_dos)
                            if (
                                not is_clx_d
                                or gate_kind_dos != "secret"
                                or bool(climax_dos.get("is_unlocked"))
                            ):
                                st_d["status"] = "active"
                                st_d["completed"] = False
                            main_stages_dos[idx_d] = st_d
                    if int(stage_index) >= tot_dos:
                        climax_dos["completed"] = True
                    climax_dos["main_stages"] = main_stages_dos
                    conn.execute(
                        "UPDATE quest_dossiers SET climax_spec_json=?, updated_at=? WHERE session_id=? AND quest_id=?",
                        (json.dumps(climax_dos), now, session_id, quest_id),
                    )
                    dos["climax_spec"] = climax_dos
                    try:
                        eff_turn_wp = int(get_effective_session_turn(session_id, conn=conn) or 0)
                        append_dossier_state_event(
                            session_id,
                            quest_id,
                            eff_turn_wp,
                            "climax_spec",
                            prev_climax_dos,
                            climax_dos,
                            conn=conn,
                        )
                    except Exception:
                        pass
                sync_quest_projection_from_dossier(session_id, quest_id, dossier=dos, conn=conn)
                tot_row = conn.execute(
                    "SELECT COUNT(*) as c FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id=0",
                    (session_id, quest_id),
                ).fetchone()
                don_row = conn.execute(
                    "SELECT COUNT(*) as c FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id=0 AND status IN ('completed', 'bypassed')",
                    (session_id, quest_id),
                ).fetchone()
                tot = tot_row["c"] if tot_row else 0
                don = don_row["c"] if don_row else 0
                if tot > 0:
                    conn.execute(
                        "UPDATE quests SET progress=?, updated_at=? WHERE session_id=? AND quest_id=?",
                        (f"{don}/{tot} Main Objective Stages", now, session_id, quest_id),
                    )
                next_row = conn.execute(
                    """SELECT * FROM quest_waypoints
                       WHERE session_id=? AND quest_id=? AND sub_obj_id=0 AND stage_index > ? AND status='active'
                       ORDER BY stage_index ASC LIMIT 1""",
                    (session_id, quest_id, stage_index),
                ).fetchone()
                return _hydrate_waypoint_row(next_row) if next_row else None

        if eff_sub_id is None:
            conn.execute(
                "UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND stage_index=?",
                (now, session_id, quest_id, stage_index),
            )
            next_row = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND status='locked'
                   ORDER BY stage_index ASC LIMIT 1""",
                (session_id, quest_id),
            ).fetchone()
            if next_row:
                conn.execute(
                    "UPDATE quest_waypoints SET status='active', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND stage_index=?",
                    (now, session_id, quest_id, next_row["stage_index"]),
                )
            tot_row = conn.execute(
                "SELECT COUNT(*) as c FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL",
                (session_id, quest_id),
            ).fetchone()
            don_row = conn.execute(
                "SELECT COUNT(*) as c FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND status='completed'",
                (session_id, quest_id),
            ).fetchone()
            tot = tot_row["c"] if tot_row else 0
            don = don_row["c"] if don_row else 0
            if tot > 0:
                conn.execute(
                    "UPDATE quests SET progress=?, updated_at=? WHERE session_id=? AND quest_id=?",
                    (f"{don}/{tot} Milestones", now, session_id, quest_id),
                )
            if next_row is None:
                dos_leg = get_quest_dossier(session_id, quest_id, conn=conn)
                if dos_leg and str(dos_leg.get("status_stage") or "pitch") != "pitch":
                    prev_climax_leg = json.loads(json.dumps(dos_leg.get("climax_spec") or {}))
                    climax_leg = json.loads(json.dumps(prev_climax_leg))
                    climax_leg["completed"] = True
                    ms_leg = [
                        dict(s)
                        for s in (climax_leg.get("main_stages") or [])
                        if isinstance(s, dict)
                    ]
                    for idx_l, st_l in enumerate(ms_leg):
                        st_l["status"] = "completed"
                        st_l["completed"] = True
                        ms_leg[idx_l] = st_l
                    if ms_leg:
                        climax_leg["main_stages"] = ms_leg
                    conn.execute(
                        "UPDATE quest_dossiers SET climax_spec_json=?, updated_at=? WHERE session_id=? AND quest_id=?",
                        (json.dumps(climax_leg), now, session_id, quest_id),
                    )
                    try:
                        eff_turn_leg = int(get_effective_session_turn(session_id, conn=conn) or 0)
                        append_dossier_state_event(
                            session_id,
                            quest_id,
                            eff_turn_leg,
                            "climax_spec",
                            prev_climax_leg,
                            climax_leg,
                            conn=conn,
                        )
                    except Exception:
                        pass
        else:
            conn.execute(
                "UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND stage_index=?",
                (now, session_id, quest_id, eff_sub_id, stage_index),
            )
            next_row = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND status='locked'
                   ORDER BY stage_index ASC LIMIT 1""",
                (session_id, quest_id, eff_sub_id),
            ).fetchone()
            if next_row:
                conn.execute(
                    "UPDATE quest_waypoints SET status='active', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND stage_index=?",
                    (now, session_id, quest_id, eff_sub_id, next_row["stage_index"]),
                )
            tot_row = conn.execute(
                "SELECT COUNT(*) as c FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id=?",
                (session_id, quest_id, eff_sub_id),
            ).fetchone()
            don_row = conn.execute(
                "SELECT COUNT(*) as c FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND status='completed'",
                (session_id, quest_id, eff_sub_id),
            ).fetchone()
            tot = tot_row["c"] if tot_row else 0
            don = don_row["c"] if don_row else 0
            if tot > 0:
                prefix_lbl = "Main Objective" if eff_sub_id == 0 else f"Optional #{eff_sub_id}"
                conn.execute(
                    "UPDATE quests SET progress=?, updated_at=? WHERE session_id=? AND quest_id=?",
                    (f"{don}/{tot} {prefix_lbl} Stages", now, session_id, quest_id),
                )
        return dict(next_row) if next_row else None


def _loc_leaf_norm(loc_text: str) -> str:
    raw = str(loc_text or "").strip()
    if not raw:
        return ""
    if "➔" in raw:
        raw = raw.split("➔")[-1].strip()
    elif "->" in raw:
        raw = raw.split("->")[-1].strip()
    elif "·" in raw:
        raw = raw.split("·")[0].strip()
    elif " in " in raw.lower():
        raw = raw[: raw.lower().rfind(" in ")].strip()
    if raw.lower().startswith("the "):
        raw = raw[4:].strip()
    return raw.lower()


def unlock_climax_waypoint(
    session_id: int,
    quest_id: str,
    climax_loc: str = "",
    target_npc: str = "",
    conn: Any = None,
) -> int:
    """Promotes a 'locked' climax/Main stage in quest_waypoints to 'active' when climax_spec['is_unlocked'] becomes True."""
    now = time.time()

    def _run(c: Any) -> int:
        rows = c.execute(
            """SELECT id, stage_index, sub_obj_id, target_location
               FROM quest_waypoints
               WHERE session_id=? AND quest_id=? AND (sub_obj_id IS NULL OR sub_obj_id=0) AND status='locked'
               ORDER BY CASE WHEN sub_obj_id IS NULL THEN 0 ELSE 1 END ASC, stage_index DESC""",
            (session_id, quest_id),
        ).fetchall()
        if not rows:
            return 0
        row = None
        if climax_loc:
            c_low = str(climax_loc).strip().lower()
            c_leaf = _loc_leaf_norm(climax_loc)
            for cand in rows:
                t_raw = str(cand["target_location"] or "").strip()
                t_low = t_raw.lower()
                t_leaf = _loc_leaf_norm(t_raw)
                if (t_low and (t_low == c_low or t_low in c_low)) or (
                    c_leaf and t_leaf and c_leaf == t_leaf
                ):
                    row = cand
                    break
        if row is None:
            row = rows[0]
        c.execute(
            "UPDATE quest_waypoints SET status='active', target_npc=CASE WHEN target_npc='' OR target_npc IS NULL THEN ? ELSE target_npc END, updated_at=? WHERE id=?",
            (target_npc or "", now, row["id"]),
        )
        return 1

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def update_waypoint_resource_progress(
    session_id: int, quest_id: str, stage_index: int, delta: int, sub_obj_id: int | None = None
) -> dict:
    """Increment resource_collected for a gathering waypoint."""
    now = time.time()
    with get_conn() as conn:
        if sub_obj_id is None:
            conn.execute(
                "UPDATE quest_waypoints SET resource_collected=MAX(0, resource_collected+?), updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND stage_index=?",
                (delta, now, session_id, quest_id, stage_index),
            )
            row = conn.execute(
                "SELECT resource_collected, resource_target FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND stage_index=?",
                (session_id, quest_id, stage_index),
            ).fetchone()
        else:
            conn.execute(
                "UPDATE quest_waypoints SET resource_collected=MAX(0, resource_collected+?), updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND stage_index=?",
                (delta, now, session_id, quest_id, sub_obj_id, stage_index),
            )
            row = conn.execute(
                "SELECT resource_collected, resource_target FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND stage_index=?",
                (session_id, quest_id, sub_obj_id, stage_index),
            ).fetchone()
        if row:
            collected = row["resource_collected"]
            target = row["resource_target"]
            return {
                "collected": collected,
                "target": target,
                "complete": target > 0 and collected >= target,
            }
        return {"collected": 0, "target": 0, "complete": False}


def get_all_session_active_waypoints(
    session_id: int,
    *,
    resolve_schedule: bool = True,
    preloaded_sched_ctx: dict[str, Any] | None = None,
) -> list[dict]:
    """Returns all 'active' waypoints across all quests in a session."""
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
            (session_id,),
        ).fetchall()
        row_dicts = [dict(r) for r in rows]
        sched_ctx: dict[str, Any] = {}
        if resolve_schedule and any(
            rd.get("follow_npc_schedule") and rd.get("target_npc") for rd in row_dicts
        ):
            if preloaded_sched_ctx:
                sched_ctx = preloaded_sched_ctx
            else:
                try:
                    sched_ctx = _preload_waypoint_schedule_ctx(session_id)
                    if preloaded_sched_ctx is not None and isinstance(sched_ctx, dict):
                        preloaded_sched_ctx.update(sched_ctx)
                except Exception:
                    sched_ctx = {}
        result = []
        for d in row_dicts:
            try:
                vp_raw = d.get("valid_time_phases_json") or "[]"
                d["valid_time_phases"] = (
                    json.loads(vp_raw) if isinstance(vp_raw, str) else (vp_raw or [])
                )
            except Exception:
                d["valid_time_phases"] = []
            try:
                appr_raw = d.get("approaches_json") or "[]"
                d["approaches"] = (
                    json.loads(appr_raw) if isinstance(appr_raw, str) else (appr_raw or [])
                )
            except Exception:
                d["approaches"] = []
            if d.get("target_location"):
                d["target_location"] = _normalize_loc_arrow(d["target_location"])
            d["static_target_location"] = d.get("target_location", "")
            if resolve_schedule and d.get("follow_npc_schedule") and d.get("target_npc"):
                try:
                    from mechanics.world.waypoints.matching import (
                        resolve_effective_waypoint_location,
                    )

                    eff_loc = resolve_effective_waypoint_location(
                        session_id,
                        d,
                        session=sched_ctx.get("session"),
                        session_time=sched_ctx.get("session_time"),
                        contacts_cache=sched_ctx.get("contacts_cache"),
                        roster_by_key=sched_ctx.get("roster_by_key"),
                        nodes_by_id=sched_ctx.get("nodes_by_id"),
                        active_events=sched_ctx.get("active_events"),
                        primary_property=sched_ctx.get("primary_property"),
                        primary_property_loaded=bool(
                            sched_ctx.get("primary_property_loaded", False)
                        ),
                        contacts=sched_ctx.get("contacts"),
                        person_ties=sched_ctx.get("person_ties"),
                        active_commitments=sched_ctx.get("active_commitments"),
                    )
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
                                or str(s.get("status") or "active").lower()
                                in ("completed", "failed", "bypassed", "locked_out")
                            )
                            for s in sos
                        ):
                            continue
                except Exception:
                    pass
            result.append(d)
        return result


def mark_sub_objective_completed_in_quest(session_id: int, quest_id: str, sub_obj_id: int):
    """Directly marks a quest sub-objective as completed=True in sub_objectives_json."""
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


def _stage_has_genuine_clue_evidence(
    conn: sqlite3.Connection,
    session_id: int,
    quest_id: str,
    st_dict: dict[str, Any],
) -> bool:
    """Returns True if a key_clue stage has genuine claimed clue_sources or recorded session_clues evidence."""
    is_kc_stage = bool(
        str(st_dict.get("completion_trigger") or "").lower() == "key_clue"
        or (
            isinstance(st_dict.get("clue_sources"), list)
            and len(st_dict.get("clue_sources") or []) > 0
        )
    )
    if not is_kc_stage:
        return True
    if any(
        isinstance(s, dict) and str(s.get("status") or "").lower() == "claimed"
        for s in (st_dict.get("clue_sources") or [])
    ):
        return True
    kc_title = str((st_dict.get("key_clue") or {}).get("title") or "").strip()
    if kc_title:
        row = conn.execute(
            "SELECT 1 FROM session_clues WHERE session_id=? AND quest_id=? AND LOWER(title)=LOWER(?) LIMIT 1",
            (session_id, quest_id, kc_title),
        ).fetchone()
        if row is not None:
            return True
    return False


def reconcile_structured_quest_split_brain(
    session_id: int,
    quest_id: str,
    conn: Any = None,
    dossier: dict | None = None,
    preloaded_wps: list[dict[str, Any]] | None = None,
) -> dict | None:
    """Detects quest_dossiers <-> quest_waypoints split-brain on structured quests and heals via projection sync."""
    if not session_id or not quest_id:
        return None

    def _detect_divergence(
        c: sqlite3.Connection,
        cur_dos: dict | None,
        wps_in: list[dict[str, Any]] | None,
    ) -> tuple[dict | None, bool]:
        if not cur_dos or str(cur_dos.get("status_stage") or "pitch") == "pitch":
            return None, False
        climax_spec = cur_dos.get("climax_spec") or {}
        main_stages = [s for s in (climax_spec.get("main_stages") or []) if isinstance(s, dict)]
        if not main_stages:
            return cur_dos, False

        if wps_in is not None:
            wp_rows = list(wps_in)
        else:
            wp_rows = [
                dict(r)
                for r in c.execute(
                    "SELECT sub_obj_id, stage_index, status, completion_trigger FROM quest_waypoints WHERE session_id=? AND quest_id=?",
                    (session_id, quest_id),
                ).fetchall()
            ]

        has_null_sub = any(w.get("sub_obj_id") is None for w in wp_rows)
        wp0_by_idx = {
            int(w.get("stage_index") or 0): str(w.get("status") or "").lower()
            for w in wp_rows
            if w.get("sub_obj_id") == 0
        }
        fam_tier = str(cur_dos.get("family_tier") or "").strip().lower()
        is_world_pulse_arrival = bool(
            not wp0_by_idx
            and (
                fam_tier in ("rumor", "minor", "dispatch")
                or str(quest_id).upper().startswith(("MNR-", "RMR-", "MAND-"))
            )
            and any(
                w.get("sub_obj_id") is None
                and int(w.get("stage_index") if w.get("stage_index") is not None else -1) == 0
                and str(w.get("completion_trigger") or "").strip().lower() == "arrival"
                for w in wp_rows
            )
        )
        if is_world_pulse_arrival:
            return cur_dos, False

        diverged = has_null_sub
        if not wp0_by_idx and not has_null_sub:
            return cur_dos, False

        non_climax = [
            s
            for idx_z, s in enumerate(main_stages)
            if not s.get("is_climax_stage") and idx_z < len(main_stages) - 1
        ]
        all_non_climax_done_dos = bool(non_climax) and all(
            bool(s.get("completed"))
            or str(s.get("status") or "").lower() in ("completed", "bypassed")
            for s in non_climax
        )
        gate_kind = str(
            climax_spec.get("gate_type") or climax_spec.get("gate_mode") or "open"
        ).lower()
        if (
            all_non_climax_done_dos
            and gate_kind == "secret"
            and not bool(climax_spec.get("is_unlocked", False))
        ):
            diverged = True

        if not diverged:
            for idx_z, st in enumerate(main_stages):
                st_idx = int(st.get("stage_index") or (idx_z + 1))
                st_stat = str(st.get("status") or "").lower()
                st_done = bool(st.get("completed") or st_stat in ("completed", "bypassed"))
                wp_stat = wp0_by_idx.get(st_idx)
                if wp_stat is None:
                    diverged = True
                    break
                if st_done and wp_stat not in ("completed", "bypassed"):
                    diverged = True
                    break
                if (
                    not st_done
                    and wp_stat in ("completed", "bypassed")
                    and not _stage_has_genuine_clue_evidence(c, session_id, quest_id, st)
                ):
                    diverged = True
                    break
                if (
                    all_non_climax_done_dos
                    and idx_z == len(main_stages) - 1
                    and bool(climax_spec.get("is_unlocked", True))
                    and wp_stat == "locked"
                ):
                    diverged = True
                    break

        return cur_dos, diverged

    if conn is not None:
        dos_in, diverged = _detect_divergence(
            conn,
            dossier or get_quest_dossier(session_id, quest_id, conn=conn),
            preloaded_wps,
        )
        if not diverged or dos_in is None:
            return None
        sync_quest_projection_from_dossier(session_id, quest_id, dossier=dos_in, conn=conn)
        return get_quest_dossier(session_id, quest_id, conn=conn) or dos_in

    with get_conn() as read_conn:
        _, diverged_read = _detect_divergence(
            read_conn,
            dossier or get_quest_dossier(session_id, quest_id, conn=read_conn),
            preloaded_wps,
        )
        if not diverged_read:
            return None

    with UnitOfWork() as uow_c:
        fresh_dos, diverged_uow = _detect_divergence(
            uow_c,
            get_quest_dossier(session_id, quest_id, conn=uow_c),
            None,
        )
        if not diverged_uow or fresh_dos is None:
            return None
        sync_quest_projection_from_dossier(session_id, quest_id, dossier=fresh_dos, conn=uow_c)
        return get_quest_dossier(session_id, quest_id, conn=uow_c) or fresh_dos


def sync_quest_projection_from_dossier(
    session_id: int,
    quest_id: str,
    dossier: Optional[dict] = None,
    conn: Optional[sqlite3.Connection] = None,
    is_rollback: bool = False,
) -> list[dict]:
    """Deterministically projects `1 Main Objective + 1-3 Optionals` from `quest_dossiers`."""
    now = time.time()

    def _run(c: sqlite3.Connection) -> list[dict]:
        eff_dossier = dossier or get_quest_dossier(session_id, quest_id, conn=c)
        if not eff_dossier or str(eff_dossier.get("status_stage") or "pitch") == "pitch":
            return []

        climax_spec = dict(eff_dossier.get("climax_spec") or {})
        leads_graph = [
            dict(ld) for ld in (eff_dossier.get("leads_graph") or []) if isinstance(ld, dict)
        ]
        main_stages = [
            dict(st) for st in (climax_spec.get("main_stages") or []) if isinstance(st, dict)
        ]

        if not main_stages and not climax_spec.get("has_structured_model"):
            return []

        q_row = c.execute(
            "SELECT objective, status, progress FROM quests WHERE session_id=? AND quest_id=?",
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

        wp_stage0_arrival = c.execute(
            """SELECT id, status FROM quest_waypoints
               WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND stage_index=0
                 AND LOWER(COALESCE(completion_trigger, ''))='arrival'
               LIMIT 1""",
            (session_id, quest_id),
        ).fetchone()
        has_wp0 = c.execute(
            "SELECT 1 FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id=0 LIMIT 1",
            (session_id, quest_id),
        ).fetchone()
        fam_tier_sync = str(eff_dossier.get("family_tier") or "").strip().lower()
        if (
            wp_stage0_arrival is not None
            and has_wp0 is None
            and (
                fam_tier_sync in ("rumor", "minor", "dispatch")
                or str(quest_id).upper().startswith(("MNR-", "RMR-", "MAND-"))
            )
        ):
            if is_rollback:
                target_wp_stat = "completed" if climax_done else "active"
                if str(wp_stage0_arrival["status"] or "").lower() != target_wp_stat:
                    c.execute(
                        "UPDATE quest_waypoints SET status=?, updated_at=? WHERE id=?",
                        (target_wp_stat, now, wp_stage0_arrival["id"]),
                    )
                    c.execute(
                        "UPDATE quests SET progress=?, updated_at=? WHERE session_id=? AND quest_id=?",
                        (
                            "1/1 Milestones" if climax_done else "0/1 Milestones",
                            now,
                            session_id,
                            quest_id,
                        ),
                    )
            return []

        c.execute(
            "DELETE FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL",
            (session_id, quest_id),
        )

        if not main_stages:
            main_stages = [
                {
                    "stage_index": 1,
                    "stage_label": str(
                        climax_spec.get("label") or q_row["objective"] or "Complete Main Objective"
                    ),
                    "target_location": _normalize_loc_arrow(
                        str(climax_spec.get("target_location") or "")
                    ),
                    "target_npc": str(climax_spec.get("target_npc") or ""),
                    "completion_trigger": str(climax_spec.get("completion_trigger") or "action"),
                    "approaches": list(climax_spec.get("approaches") or []),
                    "status": "completed"
                    if climax_done
                    else ("active" if climax_spec.get("is_unlocked", True) else "locked"),
                }
            ]

        gate_kind = str(
            climax_spec.get("gate_type") or climax_spec.get("gate_mode") or "open"
        ).lower()
        non_climax_dos = [
            st
            for idx_z, st in enumerate(main_stages)
            if not st.get("is_climax_stage") and idx_z < len(main_stages) - 1
        ]
        all_non_climax_done_dos = bool(non_climax_dos) and all(
            bool(st.get("completed"))
            or str(st.get("status") or "").lower() in ("completed", "bypassed")
            for st in non_climax_dos
        )
        if (
            not is_rollback
            and all_non_climax_done_dos
            and gate_kind == "secret"
            and not bool(climax_spec.get("is_unlocked", False))
        ):
            climax_spec["is_unlocked"] = True
            climax_spec["secret_lair_locked"] = False
            c.execute(
                "UPDATE quest_dossiers SET climax_spec_json=?, updated_at=? WHERE session_id=? AND quest_id=?",
                (json.dumps(climax_spec), now, session_id, quest_id),
            )

        secret_gate_unlocked = bool(
            gate_kind == "secret" and climax_spec.get("is_unlocked", False)
        )
        synthetic_npc_names = {
            str(sn.get("name") or "").strip().lower()
            for sn in (climax_spec.get("synthetic_npcs") or [])
            if isinstance(sn, dict) and str(sn.get("name") or "").strip()
        }
        active_assigned = False
        phantom_healed = False
        resolved_main_stages: list[dict] = []
        for idx_zero, st in enumerate(main_stages):
            st_idx = int(st.get("stage_index") or (idx_zero + 1))
            existing_wp = c.execute(
                "SELECT id, status FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id=0 AND stage_index=?",
                (session_id, quest_id, st_idx),
            ).fetchone()
            raw_st_status = str(st.get("status") or "").lower()
            st_done_in_dos = bool(
                st.get("completed") or raw_st_status in ("completed", "bypassed")
            )
            allow_wp_done = True
            if (
                existing_wp
                and not is_rollback
                and not st_done_in_dos
                and existing_wp["status"] in ("completed", "bypassed")
            ):
                allow_wp_done = _stage_has_genuine_clue_evidence(c, session_id, quest_id, st)
                if not allow_wp_done:
                    phantom_healed = True
            wp_is_done = bool(
                existing_wp
                and not is_rollback
                and allow_wp_done
                and existing_wp["status"] in ("completed", "bypassed")
            )
            if climax_done or raw_st_status in ("completed", "bypassed") or wp_is_done:
                eff_st_status = (
                    "completed"
                    if (climax_done or raw_st_status == "completed" or wp_is_done)
                    else "bypassed"
                )
            elif (
                secret_gate_unlocked
                and st_idx == len(main_stages)
                and all(s.get("status") in ("completed", "bypassed") for s in resolved_main_stages)
            ):
                eff_st_status = "active"
                active_assigned = True
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

            st_loc = _normalize_loc_arrow(
                str(st.get("target_location") or climax_spec.get("target_location") or "")
            )
            st_nid = str(st.get("target_node_id") or "").strip()
            if not st_nid and st_loc:
                try:
                    st_nid = str(db.resolve_node_id_from_location(session_id, st_loc) or "")
                except Exception:
                    st_nid = ""
            st_npc = str(
                st.get("target_npc")
                or (climax_spec.get("target_npc") if st_idx == len(main_stages) else "")
                or ""
            )
            st_label = str(
                st.get("stage_label")
                or st.get("label")
                or climax_spec.get("label")
                or f"Stage {st_idx}"
            )
            st_trig = str(st.get("completion_trigger") or "action")
            st_appr = json.dumps(list(st.get("approaches") or climax_spec.get("approaches") or []))
            is_climax_or_lair = bool(
                st_idx == len(main_stages)
                or st.get("is_climax_stage")
                or str(climax_spec.get("location") or "") == st_loc
            )
            is_phys_inspect = bool(
                st_trig == "inspect_prop"
                or any(
                    kw in st_label.lower()
                    for kw in ("inspect physical", "traces", "search site")
                )
            )
            is_synthetic_npc = bool(st_npc and st_npc.strip().lower() in synthetic_npc_names)
            if is_climax_or_lair or is_phys_inspect or is_synthetic_npc:
                follow_sched = 0
            else:
                follow_sched = int(bool(st.get("follow_npc_schedule", bool(st_npc))))

            if existing_wp:
                if wp_is_done:
                    eff_st_status = existing_wp["status"]
                c.execute(
                    """UPDATE quest_waypoints
                       SET stage_label=?, target_location=?, target_node_id=?, target_npc=?, completion_trigger=?,
                           status=?, follow_npc_schedule=?, approaches_json=?, updated_at=?
                       WHERE id=?""",
                    (
                        st_label,
                        st_loc,
                        st_nid,
                        st_npc,
                        st_trig,
                        eff_st_status,
                        follow_sched,
                        st_appr,
                        now,
                        existing_wp["id"],
                    ),
                )
            else:
                c.execute(
                    """INSERT INTO quest_waypoints
                       (session_id, quest_id, sub_obj_id, stage_index, stage_label, target_location,
                        target_node_id, target_npc, completion_trigger, resource_target, resource_collected, status,
                        follow_npc_schedule, valid_time_phases_json, approaches_json, created_at, updated_at)
                       VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, '[]', ?, ?, ?)""",
                    (
                        session_id,
                        quest_id,
                        st_idx,
                        st_label,
                        st_loc,
                        st_nid,
                        st_npc,
                        st_trig,
                        eff_st_status,
                        follow_sched,
                        st_appr,
                        now,
                        now,
                    ),
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

        all_main_stages_done = bool(resolved_main_stages) and all(
            s["status"] in ("completed", "bypassed") for s in resolved_main_stages
        )
        main_done_final = bool(climax_done or all_main_stages_done)
        cur_main_stage = next(
            (s for s in resolved_main_stages if s["status"] not in ("completed", "bypassed")),
            resolved_main_stages[-1],
        )

        projected_sos: list[dict] = [
            {
                "id": 0,
                "text": str(
                    climax_spec.get("main_objective_text")
                    or climax_spec.get("label")
                    or q_row["objective"]
                    or ""
                ),
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

        valid_opt_ids: list[int] = []
        for idx_opt, ld in enumerate(leads_graph, start=1):
            opt_sub_id = int(ld["sub_obj_id"]) if ld.get("sub_obj_id") is not None else idx_opt
            valid_opt_ids.append(opt_sub_id)
            opt_role = str(ld.get("role") or "aid").lower()
            is_disc = bool(ld.get("is_discovered", True))
            ld_status = str(ld.get("status") or "active").lower()
            if ld_status not in ("active", "completed", "failed", "bypassed", "locked_out"):
                ld_status = "active"
            opt_loc = _normalize_loc_arrow(str(ld.get("target_location") or ""))
            opt_nid = str(ld.get("target_node_id") or "").strip()
            if not opt_nid and opt_loc:
                try:
                    opt_nid = str(db.resolve_node_id_from_location(session_id, opt_loc) or "")
                except Exception:
                    opt_nid = ""
            opt_npc = str(ld.get("target_npc") or "")
            opt_label = str(ld.get("label") or f"Optional Lead {idx_opt}")
            opt_appr = json.dumps(list(ld.get("approaches") or []))
            is_phys_opt = bool(
                ld.get("completion_trigger") == "inspect_prop"
                or any(
                    kw in opt_label.lower()
                    for kw in ("inspect physical", "traces", "search site")
                )
            )
            is_synth_opt = bool(opt_npc and opt_npc.strip().lower() in synthetic_npc_names)
            opt_follow = (
                0
                if (is_phys_opt or is_synth_opt)
                else int(bool(ld.get("follow_npc_schedule", bool(opt_npc))))
            )

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
                       SET stage_label=?, target_location=?, target_node_id=?, target_npc=?, completion_trigger=?,
                           status=?, follow_npc_schedule=?, approaches_json=?, updated_at=?
                       WHERE id=?""",
                    (
                        opt_label,
                        opt_loc,
                        opt_nid,
                        opt_npc,
                        str(ld.get("completion_trigger") or "action"),
                        wp_status,
                        opt_follow,
                        opt_appr,
                        now,
                        existing_opt_wp["id"],
                    ),
                )
            else:
                c.execute(
                    """INSERT INTO quest_waypoints
                       (session_id, quest_id, sub_obj_id, stage_index, stage_label, target_location,
                        target_node_id, target_npc, completion_trigger, resource_target, resource_collected, status,
                        follow_npc_schedule, valid_time_phases_json, approaches_json, created_at, updated_at)
                       VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, 0, 0, ?, ?, '[]', ?, ?, ?)""",
                    (
                        session_id,
                        quest_id,
                        opt_sub_id,
                        opt_label,
                        opt_loc,
                        opt_nid,
                        opt_npc,
                        str(ld.get("completion_trigger") or "action"),
                        wp_status,
                        opt_follow,
                        opt_appr,
                        now,
                        now,
                    ),
                )

            projected_sos.append(
                {
                    "id": opt_sub_id,
                    "optional_id": str(
                        ld.get("optional_id") or ld.get("lead_id") or f"opt_{idx_opt}"
                    ),
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

        cur_prog = str(q_row["progress"] or "")
        new_prog = cur_prog
        if resolved_main_stages and (
            phantom_healed or re.match(r"^\d+/\d+\s+Main Objective Stages\b", cur_prog)
        ):
            don_m = sum(
                1 for s in resolved_main_stages if s["status"] in ("completed", "bypassed")
            )
            new_prog = f"{don_m}/{len(resolved_main_stages)} Main Objective Stages"

        c.execute(
            """UPDATE quests
               SET sub_objectives_json=?,
                   progress=?,
                   dossier_stage=CASE WHEN dossier_stage IN ('legacy', 'pitch', '') OR dossier_stage IS NULL THEN 'compiled' ELSE dossier_stage END,
                   updated_at=?
               WHERE session_id=? AND quest_id=?""",
            (_clean_sub_objectives_for_storage(projected_sos), new_prog, now, session_id, quest_id),
        )
        return projected_sos

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)


def get_quest_waypoint_labels(session_id: int, quest_id: str) -> list[dict[str, Any]]:
    """Fetch id, target_location, and stage_label rows for a quest's waypoints."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, target_location, stage_label FROM quest_waypoints WHERE session_id=? AND quest_id=?",
            (int(session_id), str(quest_id)),
        ).fetchall()
    return [dict(r) for r in rows]


def batch_update_quest_waypoint_labels(updates: list[tuple[str, str, int]]) -> int:
    """Batch-update target_location and stage_label for quest_waypoints rows inside one transaction."""
    if not updates:
        return 0
    with UnitOfWork() as conn:
        conn.executemany(
            "UPDATE quest_waypoints SET target_location=?, stage_label=? WHERE id=?",
            [(str(tl), str(sl), int(wid)) for tl, sl, wid in updates],
        )
    return len(updates)
