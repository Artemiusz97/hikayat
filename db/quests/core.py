"""Core quest CRUD, waypoint schedule hydration, and structured objective enrichment."""
from __future__ import annotations

import json
import re
import time
from typing import Any, Optional

from ..core import _safe_int_db, get_conn
from ..dossiers import _enrich_dossier_dict, get_quest_dossier

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
    """Evaluates whether a quest's mandatory Main Objective(s) are satisfied."""
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
        if bool(so.get("completed"))
        or str(so.get("status") or "").strip().lower() in ("completed", "bypassed")
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
        return (
            json.dumps(anomaly_blueprint, separators=(",", ":"), ensure_ascii=True)
            if anomaly_blueprint
            else "{}"
        )
    if isinstance(anomaly_blueprint, str) and anomaly_blueprint.strip():
        return anomaly_blueprint.strip()
    if quest_notes and (
        "anomaly_bp:" in str(quest_notes) or "anomaly_blueprint:" in str(quest_notes)
    ):
        try:
            from mechanics.world.anomaly_engine import parse_blueprint_from_notes

            parsed = parse_blueprint_from_notes(str(quest_notes))
            if isinstance(parsed, dict) and parsed:
                return json.dumps(parsed, separators=(",", ":"), ensure_ascii=True)
        except Exception:
            pass
    return None


def upsert_quest(
    session_id: int,
    quest_id: str,
    quest_type: str,
    title: str,
    objective: str,
    progress: str = "",
    current_clues: str = "",
    status: str = "Active",
    reward_xp: int = 100,
    reward_gold: int = 25,
    reward_stat_points: int = 0,
    reward_item: str = "",
    is_story_quest: int = 0,
    clues_required: int = 3,
    quest_notes: str = None,
    sub_objectives: list | str = None,
    blueprint_id: str = None,
    client_npc: str = None,
    client_location: str = None,
    required_item: str = None,
    required_item_count: int = None,
    strikes: int = None,
    max_strikes: int = None,
    deadline_day: int = None,
    deadline_minute: int = None,
    resolution_approach: str = None,
    engine: str = None,
    dossier_stage: str = None,
    anomaly_blueprint: dict | str | None = None,
) -> dict:
    now = time.time()
    is_story_flag = int(
        bool(
            int(is_story_quest or 0) == 1
            or str(quest_type or "").strip().lower() in ("story quest", "main quest")
        )
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
            (session_id, quest_id),
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
                (
                    quest_type or "Main Quest",
                    title,
                    objective,
                    progress or "",
                    current_clues or "",
                    status or "Active",
                    reward_xp,
                    reward_gold,
                    reward_stat_points,
                    reward_item or "",
                    is_story_quest,
                    clues_required,
                    quest_notes,
                    sub_obj_str,
                    sub_obj_str,
                    blueprint_id,
                    client_npc,
                    client_location,
                    required_item,
                    required_item_count,
                    strikes,
                    max_strikes,
                    is_story_flag,
                    deadline_day,
                    is_story_flag,
                    deadline_minute,
                    resolution_approach,
                    engine,
                    dossier_stage,
                    bp_col_str,
                    now,
                    existing["id"],
                ),
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
                (
                    session_id,
                    quest_id,
                    quest_type or "Main Quest",
                    title,
                    objective,
                    progress or "",
                    current_clues or "",
                    status or "Active",
                    reward_xp,
                    reward_gold,
                    reward_stat_points,
                    reward_item or "",
                    is_story_quest,
                    clues_required,
                    quest_notes or "",
                    sub_obj_str,
                    blueprint_id or "",
                    client_npc or "",
                    client_location or "",
                    required_item or "",
                    int(required_item_count if required_item_count is not None else 1),
                    int(strikes or 0),
                    int(max_strikes if max_strikes is not None else 2),
                    deadline_day,
                    deadline_minute,
                    resolution_approach or "",
                    engine or "",
                    dossier_stage or "legacy",
                    bp_col_str or "{}",
                    now,
                    now,
                ),
            )

    return get_quest_by_id(session_id, quest_id)


def _preload_waypoint_schedule_ctx(session_id: int) -> dict[str, Any]:
    """Preloads session, schedule, roster, world graph, events, commitments, and primary property once per call."""
    from ..properties import get_primary_property
    from ..roster import get_world_roster
    from ..sessions import get_session, get_session_time
    from ..social import get_contacts
    from ..world import get_session_world_nodes
    from ..world_events import get_world_events

    sched_sess = get_session(session_id)
    sched_time = get_session_time(session_id)
    contacts_list = get_contacts(session_id) or []
    contacts_cache: dict[str, dict] = {}
    for c in contacts_list:
        if not isinstance(c, dict):
            continue
        c_name = str(c.get("name") or "").strip().lower()
        c_nid = str(c.get("npc_id") or "").strip().lower()
        if c_name:
            contacts_cache[c_name] = c
            contacts_cache[re.sub(r"[^a-z0-9]+", "_", c_name).strip("_")] = c
        if c_nid:
            contacts_cache.setdefault(c_nid, c)
    roster_by_key: dict[str, dict] = {}
    for r in get_world_roster(session_id, include_legacy_rosters=False) or []:
        if not isinstance(r, dict):
            continue
        r_name = str(r.get("name") or "").strip().lower()
        r_nid = str(r.get("npc_id") or "").strip().lower()
        if r_name:
            roster_by_key[r_name] = r
            roster_by_key[re.sub(r"[^a-z0-9]+", "_", r_name).strip("_")] = r
        if r_nid:
            roster_by_key.setdefault(r_nid, r)
    nodes_by_id = {
        str(n.get("node_id") or ""): n
        for n in (get_session_world_nodes(session_id) or [])
        if isinstance(n, dict) and n.get("node_id")
    }
    active_events = get_world_events(session_id, entity_type="macro_event") or []
    from mechanics.system.commitments_engine import get_active_commitments

    active_commitments = (
        get_active_commitments(session_id, commitment_type="rendezvous", limit=50) or []
    )
    primary_property = get_primary_property(session_id)
    person_ties: list[Any] | None = None
    try:
        with get_conn() as c_ties:
            t_rows = c_ties.execute(
                """SELECT * FROM social_ties
                   WHERE session_id = ? AND status = 'active'
                     AND (LOWER(person_a_key) = 'player' OR LOWER(person_b_key) = 'player'
                          OR LOWER(person_a_key) LIKE 'player:%' OR LOWER(person_b_key) LIKE 'player:%')
                   ORDER BY updated_at DESC""",
                (session_id,),
            ).fetchall()
        person_ties = [dict(tr) for tr in t_rows]
    except Exception:
        person_ties = None
    return {
        "session": sched_sess,
        "session_time": sched_time,
        "contacts": contacts_list,
        "contacts_cache": contacts_cache,
        "roster_by_key": roster_by_key,
        "nodes_by_id": nodes_by_id,
        "active_events": active_events,
        "active_commitments": active_commitments,
        "primary_property": primary_property,
        "primary_property_loaded": True,
        "person_ties": person_ties,
    }


def _hydrate_quest_waypoint_for_enrichment(
    session_id: int,
    wr: Any,
    session: Optional[dict] = None,
    session_time: Optional[tuple] = None,
    contacts_cache: Optional[dict] = None,
    resolve_schedule: bool = True,
    preloaded_sched_ctx: Optional[dict] = None,
) -> dict:
    w_dict = dict(wr)
    try:
        appr_raw = w_dict.get("approaches_json") or "[]"
        w_dict["approaches"] = (
            json.loads(appr_raw) if isinstance(appr_raw, str) else (appr_raw or [])
        )
    except Exception:
        w_dict["approaches"] = []
    if w_dict.get("target_location"):
        w_dict["target_location"] = _normalize_loc_arrow(w_dict["target_location"])
    w_dict["static_target_location"] = w_dict.get("target_location", "")
    if resolve_schedule and w_dict.get("follow_npc_schedule") and w_dict.get("target_npc"):
        try:
            from mechanics.world.waypoints.matching import resolve_effective_waypoint_location

            ctx_map = preloaded_sched_ctx if isinstance(preloaded_sched_ctx, dict) else {}
            eff_loc = resolve_effective_waypoint_location(
                session_id,
                w_dict,
                session=ctx_map.get("session", session),
                session_time=ctx_map.get("session_time", session_time),
                contacts_cache=ctx_map.get("contacts_cache", contacts_cache),
                roster_by_key=ctx_map.get("roster_by_key"),
                nodes_by_id=ctx_map.get("nodes_by_id"),
                active_events=ctx_map.get("active_events"),
                primary_property=ctx_map.get("primary_property"),
                primary_property_loaded=bool(ctx_map.get("primary_property_loaded", False)),
                contacts=ctx_map.get("contacts"),
                person_ties=ctx_map.get("person_ties"),
                active_commitments=ctx_map.get("active_commitments"),
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
    resolve_schedule: bool = True,
    preloaded_sched_ctx: Optional[dict] = None,
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
            d["sub_objectives"] = [
                dict(so) if isinstance(so, dict) else so for so in (raw_sos or [])
            ]
        except Exception:
            d["sub_objectives"] = []
    else:
        d["sub_objectives"] = []

    session_id = d.get("session_id")
    quest_id = d.get("quest_id")
    all_wps: list[dict] = []
    if session_id and quest_id:
        wp_rows = preloaded_wps
        if wp_rows is None:
            try:
                with get_conn() as conn:
                    wp_rows = conn.execute(
                        """SELECT * FROM quest_waypoints
                           WHERE session_id=? AND quest_id=?
                           ORDER BY COALESCE(sub_obj_id, 0) ASC, stage_index ASC""",
                        (session_id, quest_id),
                    ).fetchall()
            except Exception:
                wp_rows = []
        raw_wp_dicts = [dict(wr) for wr in (wp_rows or [])]
        sched_ctx_local = preloaded_sched_ctx if isinstance(preloaded_sched_ctx, dict) else None
        if (
            sched_ctx_local is None
            and resolve_schedule
            and any(w.get("follow_npc_schedule") and w.get("target_npc") for w in raw_wp_dicts)
        ):
            try:
                sched_ctx_local = _preload_waypoint_schedule_ctx(int(session_id))
            except Exception:
                sched_ctx_local = None
        all_wps = [
            _hydrate_quest_waypoint_for_enrichment(
                session_id,
                wr,
                resolve_schedule=resolve_schedule,
                preloaded_sched_ctx=sched_ctx_local,
            )
            for wr in raw_wp_dicts
        ]

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
                w
                for w in all_wps
                if w.get("sub_obj_id") is not None
                and _safe_int_db(w.get("sub_obj_id"), -1) == _safe_int_db(so_id, -2)
            ]
            if so_wps:
                is_disc = bool(so.get("is_discovered", True))
                so_stat = str(
                    so.get("status") or ("completed" if so.get("completed") else "active")
                ).lower()
                active_wp = next((w for w in so_wps if w.get("status") == "active"), None)
                if (
                    not active_wp
                    and not so.get("completed")
                    and is_disc
                    and so_stat not in ("failed", "bypassed", "locked_out")
                ):
                    active_wp = next((w for w in so_wps if w.get("status") == "locked"), so_wps[0])
                elif not active_wp and so.get("completed"):
                    active_wp = so_wps[-1]
                so["waypoints"] = so_wps
                so["active_waypoint"] = (
                    active_wp
                    if (is_disc and so_stat not in ("failed", "bypassed", "locked_out"))
                    else None
                )
                so["target_location"] = (
                    (active_wp.get("target_location") or "")
                    if active_wp
                    else _normalize_loc_arrow(so.get("target_location") or "")
                )
                so["target_npc"] = (
                    (active_wp.get("target_npc") or "") if active_wp else (so.get("target_npc") or "")
                )
                so["stage_label"] = (active_wp.get("stage_label") or "") if active_wp else ""
                so["stage_index"] = int(active_wp.get("stage_index", 1) or 1) if active_wp else 1
                so["total_stages"] = len(so_wps)
                so["completed_stages"] = sum(
                    1 for w in so_wps if w.get("status") in ("completed", "bypassed")
                )
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
                (
                    so
                    for so in d["sub_objectives"]
                    if isinstance(so, dict) and not bool(so.get("is_optional"))
                ),
                None,
            )
            d["optional_objectives"] = [
                so
                for so in d["sub_objectives"]
                if isinstance(so, dict)
                and bool(so.get("is_optional"))
                and bool(so.get("is_discovered", True))
            ]
            if d["main_objective"] and d["main_objective"].get("stages"):
                d["stages"] = d["main_objective"]["stages"]

        eligible_sos = [
            so
            for so in d["sub_objectives"]
            if isinstance(so, dict)
            and not bool(so.get("completed"))
            and bool(so.get("is_discovered", True))
            and str(so.get("status") or "active").lower()
            not in ("completed", "failed", "bypassed", "locked_out")
            and so.get("active_waypoint")
        ]
        eligible_sos.sort(
            key=lambda s: (1 if bool(s.get("is_optional")) else 0, _safe_int_db(s.get("id"), 99))
        )
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
        d["active_waypoints"] = (
            [active_wp] if active_wp and active_wp.get("status") == "active" else []
        )
        if active_wp:
            d["target_location"] = active_wp.get("target_location") or _normalize_loc_arrow(
                d.get("target_location") or ""
            )
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


def get_minimal_story_quest(
    session_id: int,
    quest_id: Optional[str] = None,
    *,
    conn: Any = None,
) -> Optional[dict]:
    """Lightweight quest header lookup matching active story quest criteria without N+1 joins."""

    def _query(c: Any) -> Optional[dict]:
        if quest_id:
            row = c.execute(
                "SELECT quest_id, title, status, is_story_quest, engine, quest_type FROM quests WHERE session_id=? AND quest_id=? LIMIT 1",
                (session_id, quest_id),
            ).fetchone()
        else:
            row = c.execute(
                """SELECT quest_id, title, status, is_story_quest, engine, quest_type
                   FROM quests
                   WHERE session_id=? AND LOWER(status)='active'
                     AND (is_story_quest=1 OR LOWER(quest_type) IN ('story quest', 'main quest'))
                   ORDER BY (CASE WHEN sub_objectives_json IS NOT NULL AND sub_objectives_json != '[]' AND sub_objectives_json != '' THEN 1 ELSE 0 END) DESC, updated_at DESC
                   LIMIT 1""",
                (session_id,),
            ).fetchone()
        return dict(row) if row else None

    if conn is not None:
        return _query(conn)
    with get_conn() as c:
        return _query(c)


def get_quest_waypoint_target_location(
    session_id: int,
    quest_id: str,
    *,
    mode: str = "climax_null_sub",
    conn: Any = None,
) -> Optional[str]:
    """Looks up target_location from quest_waypoints cleanly in the DB persistence layer."""

    def _query(c: Any) -> Optional[str]:
        if mode == "highest_sub":
            row = c.execute(
                """SELECT target_location FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND target_location IS NOT NULL AND target_location != ''
                   ORDER BY CASE WHEN sub_obj_id = 0 THEN 0 ELSE 1 END ASC, sub_obj_id DESC, stage_index DESC LIMIT 1""",
                (session_id, quest_id),
            ).fetchone()
        else:
            row = c.execute(
                """SELECT target_location FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND status IN ('active', 'locked') LIMIT 1""",
                (session_id, quest_id),
            ).fetchone()
        return str(row["target_location"]) if (row and row["target_location"]) else None

    if conn is not None:
        return _query(conn)
    with get_conn() as c:
        return _query(c)


def get_active_story_quest(session_id: int, *, resolve_schedule: bool = True) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM quests
               WHERE session_id=? AND (is_story_quest=1 OR LOWER(quest_type) IN ('story quest', 'main quest'))
               AND LOWER(status)='active'
               ORDER BY (CASE WHEN sub_objectives_json IS NOT NULL AND sub_objectives_json != '[]' AND sub_objectives_json != '' THEN 1 ELSE 0 END) DESC, updated_at DESC""",
            (session_id,),
        ).fetchone()
    return _enrich_quest_dict(row, resolve_schedule=resolve_schedule)


def get_session_quests(
    session_id: int,
    status: str = None,
    *,
    preloaded_sched_ctx: dict[str, Any] | None = None,
) -> list[dict]:
    wps_by_qid: dict[str, list[Any]] = {}
    dossiers_by_qid: dict[str, dict] = {}
    with get_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM quests WHERE session_id=? AND LOWER(status)=LOWER(?) ORDER BY updated_at DESC",
                (session_id, status),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM quests WHERE session_id=? ORDER BY updated_at DESC",
                (session_id,),
            ).fetchall()
        if rows:
            try:
                wp_rows = conn.execute(
                    """SELECT * FROM quest_waypoints
                       WHERE session_id=?
                       ORDER BY quest_id ASC, COALESCE(sub_obj_id, 0) ASC, stage_index ASC""",
                    (session_id,),
                ).fetchall()
                for wr in wp_rows:
                    qid_key = str(wr["quest_id"] or "")
                    wps_by_qid.setdefault(qid_key, []).append(wr)
            except Exception:
                wps_by_qid = {}
            try:
                d_rows = conn.execute(
                    "SELECT * FROM quest_dossiers WHERE session_id=?",
                    (session_id,),
                ).fetchall()
                for dr in d_rows:
                    ed = _enrich_dossier_dict(dr)
                    if ed and ed.get("quest_id"):
                        dossiers_by_qid[str(ed["quest_id"])] = ed
            except Exception:
                dossiers_by_qid = {}
    sched_ctx: dict[str, Any] | None = None
    if rows and any(
        w["follow_npc_schedule"] and w["target_npc"]
        for wp_list in wps_by_qid.values()
        for w in wp_list
    ):
        if preloaded_sched_ctx:
            sched_ctx = preloaded_sched_ctx
        else:
            try:
                sched_ctx = _preload_waypoint_schedule_ctx(session_id)
                if preloaded_sched_ctx is not None and isinstance(sched_ctx, dict):
                    preloaded_sched_ctx.update(sched_ctx)
            except Exception:
                sched_ctx = None
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
            preloaded_sched_ctx=sched_ctx,
        )
        if enriched:
            out.append(enriched)
    return out


get_quests = get_session_quests


def get_quest_by_id(session_id: int, quest_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM quests WHERE session_id=? AND quest_id=?",
            (session_id, quest_id),
        ).fetchone()
    return _enrich_quest_dict(row)


def update_quest_status(session_id: int, quest_id: str, status: str):
    now = time.time()
    with get_conn() as conn:
        if status == "Active":
            row = conn.execute(
                "SELECT deadline_day, is_story_quest FROM quests WHERE session_id=? AND quest_id=?",
                (session_id, quest_id),
            ).fetchone()
            if row and row["deadline_day"] is not None and not row["is_story_quest"]:
                s_row = conn.execute(
                    "SELECT current_day FROM sessions WHERE id=?", (session_id,)
                ).fetchone()
                curr_day = int(s_row["current_day"] or 1) if s_row else 1
                min_deadline = curr_day + 5
                if int(row["deadline_day"]) < min_deadline:
                    conn.execute(
                        "UPDATE quests SET deadline_day=? WHERE session_id=? AND quest_id=?",
                        (min_deadline, session_id, quest_id),
                    )
        conn.execute(
            "UPDATE quests SET status=?, updated_at=? WHERE session_id=? AND quest_id=?",
            (status, now, session_id, quest_id),
        )


def append_quest_note_flag_in_db(
    session_id: int, quest_id: str, flag_key: str, flag_val: str = "1"
) -> str:
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


def get_active_quest_sub_objectives(session_id: int) -> list[list[dict[str, Any]]]:
    """Return parsed sub-objective lists for all Active quests in `session_id`."""
    if not session_id:
        return []
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT sub_objectives_json FROM quests WHERE session_id=? AND status='Active'",
            (int(session_id),),
        ).fetchall()
    parsed: list[list[dict[str, Any]]] = []
    for row in rows:
        try:
            raw = row["sub_objectives_json"] or "[]"
            items = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(items, list):
                parsed.append([so for so in items if isinstance(so, dict)])
        except Exception:
            continue
    return parsed
