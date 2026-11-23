"""
mechanics/world/locations/access_gate.py
========================================
Core access control, curfew enforcement, threshold barriers, private residence intercoms,
and rolling room memory (scene residue) for Hikayat's Relational Spatial Graph.
"""
from __future__ import annotations
import hashlib
import json
import logging
import random
import re
from typing import Any, Mapping

import db
import scenario_data

log = logging.getLogger("hikayat.world.access_gate")


class Phase2Choice(str):
    """A choice string subclass that also provides dictionary-like properties for choices_cleaner."""
    label: str
    stat: str
    requirement: int
    mp_cost: int

    def __new__(cls, label: str, stat: str = "NONE", requirement: int = 0, mp_cost: int = 0, **kwargs):
        val = super().__new__(cls, str(label).strip())
        val.label = str(label).strip()
        val.stat = stat
        val.requirement = requirement
        val.mp_cost = mp_cost
        val.is_phase2_choice = True
        val._extra_kwargs = dict(kwargs)
        for k, v in kwargs.items():
            setattr(val, k, v)
        return val

    def get(self, key, default=None):
        if key in ("label", "text", "action"): return self.label
        if key == "stat": return getattr(self, "stat", default)
        if key == "requirement": return getattr(self, "requirement", default)
        if key == "mp_cost": return getattr(self, "mp_cost", default)
        if key == "is_phase2_choice": return True
        return getattr(self, key, default)

    def __getitem__(self, key):
        if key in ("label", "text", "action"): return self.label
        if hasattr(self, key): return getattr(self, key)
        return super().__getitem__(key)

    def to_dict(self) -> dict:
        d = {
            "label": self.label,
            "stat": self.stat,
            "requirement": self.requirement,
            "mp_cost": self.mp_cost,
            "is_phase2_choice": True,
        }
        for k, v in (getattr(self, "_extra_kwargs", None) or {}).items():
            d[k] = v
        return d


def is_curfew_active(
    curfew_start_min: int | None,
    curfew_end_min: int | None,
    current_minute: int
) -> bool:
    """
    Returns True if curfew hours are currently active.
    Handles overnight wrap-around (e.g. 1320..360, where 22:00 -> 06:00 crosses midnight).
    """
    if curfew_start_min is None or curfew_end_min is None:
        return False
    safe_min = int(current_minute or 0) % 1440
    start = int(curfew_start_min) % 1440
    end = int(curfew_end_min) % 1440

    if start == end:
        return False
    if start > end:
        # Overnight window, e.g. 22:00 (1320) to 06:00 (360)
        return safe_min >= start or safe_min < end
    else:
        # Same-day window, e.g. 12:00 (720) to 14:00 (840)
        return start <= safe_min < end


def format_minute_to_hhmm(minute: int | None) -> str:
    """Formats an absolute or modulo minute into HH:MM string."""
    if minute is None:
        return "00:00"
    m = int(minute) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


_SANCTUARY_PREFERRED_KEYWORDS = (
    "inn", "tavern", "guild", "cafe", "coffee", "diner", "teahouse",
    "commons", "agency_hq", "lobby", "sanctuary", "shelter", "bazaar",
    "market", "promenade", "plaza", "hub",
)
_SANCTUARY_EXCLUDED_KEYWORDS = (
    "homeroom", "classroom", "rooftop", "infirmary", "faculty",
    "principal", "council", "locker", "pool", "dungeon", "prison",
    "morgue", "quarantine", "vault", "sewer", "crypt",
)


def _parse_node_state_json(node: Mapping[str, Any] | None) -> dict[str, Any]:
    """Parse `world_nodes.state_json` safely into a dict without DB round-trips."""
    from mechanics.world.anomalous_sites.catalog import parse_node_state
    return parse_node_state(node)


def get_designated_hub_sanctuary_node_id(
    session_id: int,
    *,
    all_nodes: list[dict[str, Any]] | None = None,
    state_by_id: Mapping[str, dict[str, Any]] | None = None,
) -> str:
    """
    Designates and persists 1 core Hub Sanctuary facility per session (`safe_sanctuary_exempt = True`)
    that can NEVER be locked down by WorldScars or Chapter 8–9 martial law.
    """
    if not session_id:
        return ""
    if all_nodes is not None:
        nodes = list(all_nodes)
    else:
        try:
            nodes = db.get_session_world_nodes(session_id) or []
        except Exception:
            nodes = []
    if not nodes:
        return "loc_hub_sanctuary"

    facilities = [n for n in nodes if str(n.get("node_type") or "").upper() == "FACILITY"]
    if not facilities:
        facilities = list(nodes)

    for fac in facilities:
        nid = str(fac.get("node_id") or "")
        if not nid:
            continue
        try:
            if state_by_id is not None and nid in state_by_id:
                st = state_by_id.get(nid) or {}
            elif all_nodes is not None:
                st = _parse_node_state_json(fac)
            else:
                st = db.get_world_node_state(session_id, nid) or {}
            if st.get("safe_sanctuary_exempt"):
                return nid
        except Exception:
            pass

    chosen_nid = ""
    for fac in facilities:
        nid = str(fac.get("node_id") or "")
        tier = str(fac.get("access_tier") or "open").lower()
        blob = f"{nid} {fac.get('name') or ''}".lower()
        if tier != "open":
            continue
        if any(ex in blob for ex in _SANCTUARY_EXCLUDED_KEYWORDS):
            continue
        if any(pk in blob for pk in _SANCTUARY_PREFERRED_KEYWORDS):
            chosen_nid = nid
            break

    if not chosen_nid:
        for fac in facilities:
            nid = str(fac.get("node_id") or "")
            tier = str(fac.get("access_tier") or "open").lower()
            blob = f"{nid} {fac.get('name') or ''}".lower()
            if tier == "open" and not any(ex in blob for ex in _SANCTUARY_EXCLUDED_KEYWORDS):
                chosen_nid = nid
                break

    if not chosen_nid:
        for nd in nodes:
            nid = str(nd.get("node_id") or "")
            tier = str(nd.get("access_tier") or "open").lower()
            blob = f"{nid} {nd.get('name') or ''}".lower()
            if (
                nid
                and tier == "open"
                and not any(ex in blob for ex in _SANCTUARY_EXCLUDED_KEYWORDS)
                and any(pk in blob for pk in _SANCTUARY_PREFERRED_KEYWORDS)
            ):
                chosen_nid = nid
                break

    if chosen_nid:
        if not db.is_in_readonly_uow():
            try:
                db.update_world_node_state(session_id, chosen_nid, {"safe_sanctuary_exempt": True})
            except Exception:
                pass
        if isinstance(state_by_id, dict):
            state_by_id.setdefault(chosen_nid, {})["safe_sanctuary_exempt"] = True
    return chosen_nid


def is_safe_sanctuary_node(
    session_id: int,
    node_id: str,
    *,
    node_by_id: Mapping[str, dict[str, Any]] | None = None,
    state_by_id: Mapping[str, dict[str, Any]] | None = None,
    sanctuary_id: str | None = None,
) -> bool:
    """Returns True if `node_id` (or its parent facility) is the session's Safe Hub Sanctuary."""
    if not session_id or not node_id:
        return False
    if sanctuary_id is None:
        sanctuary_id = get_designated_hub_sanctuary_node_id(
            session_id,
            all_nodes=list(node_by_id.values()) if node_by_id is not None else None,
            state_by_id=state_by_id,
        )
    target = str(node_id).strip()
    if sanctuary_id and target.lower() == sanctuary_id.lower():
        return True
    try:
        node = node_by_id.get(target) if node_by_id is not None else db.get_world_node(session_id, target)
        if node:
            if state_by_id is not None and target in state_by_id:
                st = state_by_id.get(target) or {}
            elif node_by_id is not None:
                st = _parse_node_state_json(node)
            else:
                st = db.get_world_node_state(session_id, target) or {}
            if st.get("safe_sanctuary_exempt"):
                return True
            parent_id = str(node.get("parent_id") or "")
            if parent_id:
                if sanctuary_id and parent_id.lower() == sanctuary_id.lower():
                    return True
                if state_by_id is not None and parent_id in state_by_id:
                    pst = state_by_id.get(parent_id) or {}
                elif node_by_id is not None:
                    pst = _parse_node_state_json(node_by_id.get(parent_id))
                else:
                    pst = db.get_world_node_state(session_id, parent_id) or {}
                if pst.get("safe_sanctuary_exempt"):
                    return True
    except Exception:
        pass
    return False


def _quest_loc_matches_node(loc_str: Any, node: dict | None, fac_node: dict | None = None) -> bool:
    raw = str(loc_str or "").strip().lower()
    if not raw or not isinstance(node, dict):
        return False
    leaf = raw.split("➔")[-1].split("->")[-1].strip()
    nid = str(node.get("node_id") or "").strip().lower()
    nname = str(node.get("name") or "").strip().lower()
    candidates = {x for x in (nid, nname) if x}
    if isinstance(fac_node, dict):
        fnid = str(fac_node.get("node_id") or "").strip().lower()
        fname = str(fac_node.get("name") or "").strip().lower()
        if fnid:
            candidates.add(fnid)
        if fname and leaf == fname:
            candidates.add(fname)
    return raw in candidates or (bool(leaf) and leaf in candidates)


def build_active_quest_gate_snapshot(session_id: int) -> dict[str, Any]:
    """Preloads active quests, dossiers, and active waypoints ONCE per map/payload sweep."""
    if not session_id:
        return {"quests": [], "dossiers_by_qid": {}, "active_wps": []}
    try:
        quests = db.get_session_quests(session_id, status="Active") or []
        dossiers_by_qid = {
            str(d.get("quest_id") or ""): d
            for d in (db.get_session_quest_dossiers(session_id) or [])
            if isinstance(d, dict) and d.get("quest_id")
        }
        active_wps = db.get_all_session_active_waypoints(session_id) or []
        return {
            "quests": quests,
            "dossiers_by_qid": dossiers_by_qid,
            "active_wps": active_wps,
        }
    except Exception:
        return {"quests": [], "dossiers_by_qid": {}, "active_wps": []}


def _get_active_quest_gate_context(
    session_id: int,
    node: dict | None,
    fac_node: dict | None = None,
    quest_gate_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Inspects active quests & dossiers for earned handover clearance, active quest-room immunity, and rush danger tier."""
    out: dict[str, Any] = {
        "has_earned_clearance": False,
        "is_active_quest_room": False,
        "min_danger_tier": 1,
    }
    if not session_id or not isinstance(node, dict):
        return out
    min_dt: int | None = None
    try:
        snap = quest_gate_snapshot if isinstance(quest_gate_snapshot, dict) else build_active_quest_gate_snapshot(session_id)
        quests = snap.get("quests") or []
        dossiers_by_qid = snap.get("dossiers_by_qid") or {}
        active_wps = snap.get("active_wps") or []
        for q in quests:
            if not isinstance(q, dict) or str(q.get("status") or "").lower() != "active":
                continue
            qid = str(q.get("quest_id") or "")
            dos = dossiers_by_qid.get(qid) or {}
            q_dt = max(1, min(5, int(dos.get("danger_tier") or q.get("danger_tier") or 1)))
            climax = dos.get("climax_spec") or {}
            for cl_loc in (climax.get("earned_clearance_locations") or []):
                if _quest_loc_matches_node(cl_loc, node, fac_node):
                    out["has_earned_clearance"] = True
                    out["is_active_quest_room"] = True
                    min_dt = q_dt if min_dt is None else min(min_dt, q_dt)

            for ms in (climax.get("main_stages") or []):
                if not isinstance(ms, dict):
                    continue
                ms_stat = str(ms.get("status") or "locked").lower()
                if ms.get("completed") or ms_stat in ("completed", "bypassed"):
                    continue
                if ms.get("is_climax_stage"):
                    if climax.get("is_unlocked") and _quest_loc_matches_node(ms.get("target_location") or climax.get("location"), node, fac_node):
                        out["is_active_quest_room"] = True
                        min_dt = q_dt if min_dt is None else min(min_dt, q_dt)
                    continue
                if ms_stat != "active":
                    continue
                if _quest_loc_matches_node(ms.get("target_location"), node, fac_node):
                    out["is_active_quest_room"] = True
                    min_dt = q_dt if min_dt is None else min(min_dt, q_dt)
                for src in (ms.get("clue_sources") or []):
                    if isinstance(src, dict) and str(src.get("status") or "open").lower() == "open":
                        if _quest_loc_matches_node(src.get("location"), node, fac_node):
                            out["is_active_quest_room"] = True
                            min_dt = q_dt if min_dt is None else min(min_dt, q_dt)

        for wp in active_wps:
            if isinstance(wp, dict) and _quest_loc_matches_node(wp.get("target_location") or wp.get("target_node_id"), node, fac_node):
                out["is_active_quest_room"] = True
                wp_dt = max(1, min(5, int((dossiers_by_qid.get(str(wp.get("quest_id") or "")) or {}).get("danger_tier") or 1)))
                min_dt = wp_dt if min_dt is None else min(min_dt, wp_dt)
    except Exception:
        pass
    if min_dt is not None:
        out["min_danger_tier"] = min_dt
    return out


def build_access_eval_context(
    session_id: int,
    *,
    scen_key: str = "",
    session: dict[str, Any] | None = None,
    all_nodes: list[dict[str, Any]] | None = None,
    quest_gate_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Preload session-level spatial, quest, event, faction, and property state once per sweep."""
    sess_row: dict[str, Any] = dict(session) if isinstance(session, dict) else {}
    if not sess_row and session_id:
        try:
            sess_row = db.get_session(session_id) or {}
        except Exception:
            sess_row = {}

    resolved_scen = str(scen_key or sess_row.get("scenario") or "high_school_drama")

    if all_nodes is not None:
        nodes = list(all_nodes)
    elif session_id:
        try:
            nodes = db.get_session_world_nodes(session_id) or []
        except Exception:
            nodes = []
    else:
        nodes = []

    node_by_id: dict[str, dict[str, Any]] = {}
    state_by_id: dict[str, dict[str, Any]] = {}
    for n in nodes:
        if not isinstance(n, dict):
            continue
        nid = str(n.get("node_id") or "")
        if nid:
            node_by_id[nid] = n
            state_by_id[nid] = _parse_node_state_json(n)

    sanctuary_id = (
        get_designated_hub_sanctuary_node_id(
            session_id,
            all_nodes=nodes,
            state_by_id=state_by_id,
        )
        if session_id
        else ""
    )

    macro_events: list[dict[str, Any]] = []
    if session_id:
        try:
            macro_events = db.get_world_events(session_id, entity_type="macro_event") or []
        except Exception:
            macro_events = []

    q_snap = (
        quest_gate_snapshot
        if quest_gate_snapshot is not None
        else build_active_quest_gate_snapshot(session_id)
    )

    faction_state: dict[str, Any] = {}
    session_quests: list[dict[str, Any]] = []
    try:
        from scenario_data import is_anomalous_incursions_scenario
        if session_id and is_anomalous_incursions_scenario(resolved_scen):
            from mechanics.social.factions import get_anomalous_faction_state
            faction_state = get_anomalous_faction_state(session_id) or {}
            session_quests = db.get_session_quests(session_id) or []
    except Exception:
        faction_state = {}
        session_quests = []

    player_properties: list[dict[str, Any]] = []
    if session_id:
        try:
            player_properties = db.get_player_properties(int(session_id)) or []
        except Exception:
            player_properties = []

    return {
        "session_id": session_id,
        "session": sess_row,
        "scen_key": resolved_scen,
        "all_nodes": nodes,
        "node_by_id": node_by_id,
        "state_by_id": state_by_id,
        "sanctuary_id": sanctuary_id,
        "macro_events": macro_events,
        "quest_gate_snapshot": q_snap,
        "faction_state": faction_state,
        "session_quests": session_quests,
        "player_properties": player_properties,
    }


def get_node_effective_access_info(
    session_id: int,
    node_id: str,
    current_day: int = 1,
    current_minute: int = 480,
    scen_key: str = "",
    session: dict | None = None,
    quest_gate_snapshot: dict[str, Any] | None = None,
    eval_ctx: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Computes effective access status, curfew status, dynamic world-schedule locks,
    unlock persistence, and scene residue for a node, taking into account parent facility inheritance.
    """
    if not session_id or not node_id:
        return {
            "access_tier": "open",
            "is_unlocked": True,
            "curfew_active": False,
            "curfew_label": "",
            "status_badge": "Open",
            "scene_residue": "",
            "scene_residue_log": [],
            "schedule_locked": False,
            "is_trespassing": False,
        }

    ctx_nodes_by_id = eval_ctx.get("node_by_id") if isinstance(eval_ctx, Mapping) else None
    ctx_state_by_id = eval_ctx.get("state_by_id") if isinstance(eval_ctx, Mapping) else None
    if session is None and isinstance(eval_ctx, Mapping) and isinstance(eval_ctx.get("session"), dict):
        session = eval_ctx["session"]

    node = ctx_nodes_by_id.get(node_id) if isinstance(ctx_nodes_by_id, Mapping) else db.get_world_node(session_id, node_id)
    if not node:
        return {
            "access_tier": "open",
            "is_unlocked": True,
            "curfew_active": False,
            "curfew_label": "",
            "status_badge": "Open",
            "scene_residue": "",
            "scene_residue_log": [],
            "schedule_locked": False,
            "is_trespassing": False,
        }

    if not scen_key:
        if isinstance(eval_ctx, Mapping) and eval_ctx.get("scen_key"):
            scen_key = str(eval_ctx["scen_key"])
        elif isinstance(session, dict) and session.get("scenario"):
            scen_key = str(session["scenario"])
        else:
            try:
                sess_row = db.get_session(session_id)
                scen_key = (sess_row or {}).get("scenario") or "high_school_drama"
            except Exception:
                scen_key = "high_school_drama"

    fac_node = None
    if node.get("parent_id") and node.get("node_type") == "ROOM":
        fac_node = (
            ctx_nodes_by_id.get(node["parent_id"])
            if isinstance(ctx_nodes_by_id, Mapping)
            else db.get_world_node(session_id, node["parent_id"])
        )

    # Effective access tier
    tier = str(node.get("access_tier") or "open").lower()
    if fac_node and tier == "open":
        fac_tier = str(fac_node.get("access_tier") or "open").lower()
        if fac_tier in ("restricted", "private"):
            tier = fac_tier

    # State JSON check for unlocks and residue
    if isinstance(ctx_state_by_id, Mapping):
        state = ctx_state_by_id.get(node_id) or {}
        fac_state = (ctx_state_by_id.get(fac_node["node_id"]) or {}) if fac_node else {}
    else:
        state = db.get_world_node_state(session_id, node_id)
        fac_state = db.get_world_node_state(session_id, fac_node["node_id"]) if fac_node else {}

    is_unlocked = bool(
        state.get("unlocked_permanent")
        or (state.get("unlocked_until_day") or 0) >= current_day
        or fac_state.get("unlocked_permanent")
        or (fac_state.get("unlocked_until_day") or 0) >= current_day
    )

    # Curfew evaluation (static + dynamic world schedule)
    c_start = node.get("curfew_start_min")
    c_end = node.get("curfew_end_min")
    if c_start is None and fac_node:
        c_start = fac_node.get("curfew_start_min")
        c_end = fac_node.get("curfew_end_min")

    curfew_active = is_curfew_active(c_start, c_end, current_minute)
    curfew_label = f"{format_minute_to_hhmm(c_start)}–{format_minute_to_hhmm(c_end)}" if (c_start is not None and c_end is not None) else ""

    from mechanics.world.world_schedule import evaluate_world_schedule_node_access, is_high_school_setting
    sched_access = evaluate_world_schedule_node_access(
        node,
        fac_node,
        scen_key=scen_key,
        current_day=current_day,
        current_minute=current_minute,
        session_id=session_id,
        session=session,
    )

    schedule_locked = bool(sched_access.get("schedule_locked"))
    is_trespassing = bool(sched_access.get("is_trespassing"))
    sched_reason_code = str(sched_access.get("reason_code") or "")
    sched_reason_label = str(sched_access.get("reason_label") or "")

    # Non-high-school academic zones (e.g., anomalous_incursions University/13th Stairwell) never enforce student curfew
    if curfew_active and str(node.get("category") or "").lower() == "academic" and not is_high_school_setting(scen_key):
        curfew_active = False
        curfew_label = ""

    if sched_access.get("force_open"):
        tier = "open"
        curfew_active = False
        curfew_label = ""
        schedule_locked = False
        is_trespassing = False
    elif sched_access.get("clear_curfew") or sched_reason_code == "after_hours_anomaly_breach":
        curfew_active = False
        curfew_label = ""
        schedule_locked = False
        is_trespassing = False
    elif schedule_locked:
        if is_trespassing or sched_reason_code in ("curfew", "commercial_closed", "weekend_closed"):
            curfew_active = True
            if sched_access.get("curfew_label"):
                curfew_label = sched_access["curfew_label"]
        else:
            if tier == "open":
                tier = "restricted"
            if sched_access.get("curfew_label") and not curfew_label:
                curfew_label = sched_access["curfew_label"]

    # Anomalous Incursions Tiered HQ Access Gate evaluation
    ctx_faction_state = eval_ctx.get("faction_state") if isinstance(eval_ctx, Mapping) else None
    ctx_session_quests = eval_ctx.get("session_quests") if isinstance(eval_ctx, Mapping) else None
    anom_hq = evaluate_anomalous_hq_access(
        session_id,
        node,
        fac_node,
        scen_key=scen_key,
        faction_state=ctx_faction_state,
        quests=ctx_session_quests,
    )
    if anom_hq.get("force_open"):
        tier = "open"
        is_unlocked = True
    elif anom_hq.get("force_restricted"):
        tier = "restricted"
        if not sched_reason_label and anom_hq.get("reason_label"):
            sched_reason_label = anom_hq["reason_label"]
            sched_reason_code = "faction_hq_restricted"

    # Anomalous High School After-Hours Campus Anomaly Breach Unlock (20:00–06:00)
    _may_have_incursions = True
    if isinstance(eval_ctx, Mapping) and isinstance(session, dict) and "daily_incursions" in session and not session.get("daily_incursions"):
        _may_have_incursions = False
    if session_id and _may_have_incursions and not is_unlocked and (schedule_locked or curfew_active) and scenario_data.is_anomalous_high_school_scenario(scen_key):
        try:
            from mechanics.world.anomalous_events import get_active_incursion_at_location
            from mechanics.world.world_schedule import is_campus_node_or_location
            active_inc = get_active_incursion_at_location(
                session_id,
                location_str=str(node.get("name") or ""),
                node_id=node_id,
                current_minute=current_minute,
            )
            if active_inc and is_campus_node_or_location(node, fac_node, session_id=session_id, scen_key=scen_key):
                is_unlocked = True
                curfew_active = False
                schedule_locked = False
                is_trespassing = False
                sched_reason_code = "after_hours_anomaly_breach"
                sched_reason_label = "Resonance Breach Entry / Custodian's Side-Key (Active After-Hours Anomaly)"
        except Exception:
            pass

    # Procedural World Event Facility Lockdown / Quarantine evaluation (Safe Hub Sanctuary is NEVER locked)
    ctx_sanctuary_id = eval_ctx.get("sanctuary_id") if isinstance(eval_ctx, Mapping) else None
    sanctuary_exempt = (
        is_safe_sanctuary_node(
            session_id,
            node_id,
            node_by_id=ctx_nodes_by_id,
            state_by_id=ctx_state_by_id,
            sanctuary_id=ctx_sanctuary_id,
        )
        if session_id
        else False
    )
    has_ctx_events = isinstance(eval_ctx, Mapping) and "macro_events" in eval_ctx
    if session_id and sanctuary_exempt:
        try:
            ev_list = eval_ctx["macro_events"] if has_ctx_events else db.get_world_events(session_id, entity_type="macro_event")
            has_crisis_lock = any(
                ev.get("status") == "active"
                and (
                    (ev.get("modifiers") or {}).get("is_locked")
                    or (ev.get("modifiers") or {}).get("lockdown_nodes")
                    or (ev.get("modifiers") or {}).get("martial_law_lockdown")
                    or (ev.get("metadata") or {}).get("scar_tier") == "peak"
                )
                for ev in (ev_list or [])
                if isinstance(ev, dict)
            )
            if has_crisis_lock:
                tier = "open"
                is_unlocked = True
                curfew_active = False
                curfew_label = ""
                schedule_locked = False
                is_trespassing = False
                sched_reason_code = "safe_hub_sanctuary"
                sched_reason_label = "Safe Hub Sanctuary (Exempt from Crisis Lockdown)"
        except Exception:
            pass
    elif session_id and not is_unlocked:
        try:
            from mechanics.world.world_events.modifiers import is_node_locked_by_event
            sanctuary_nid = (
                ctx_sanctuary_id
                if ctx_sanctuary_id is not None
                else get_designated_hub_sanctuary_node_id(session_id)
            )
            ev_list = eval_ctx["macro_events"] if has_ctx_events else db.get_world_events(session_id, entity_type="macro_event")
            ev_lock = is_node_locked_by_event(ev_list, node_id, safe_sanctuary_node_id=sanctuary_nid) or (
                is_node_locked_by_event(ev_list, str(fac_node.get("node_id") or ""), safe_sanctuary_node_id=sanctuary_nid) if fac_node else None
            )
            if ev_lock and ev_lock.get("is_locked"):
                tier = "restricted"
                schedule_locked = True
                sched_reason_code = "world_event_lockdown"
                sched_reason_label = f"{ev_lock['title']}: {ev_lock['reason']}"
        except Exception:
            pass

    if session_id and not is_unlocked:
        eff_q_snap = quest_gate_snapshot if quest_gate_snapshot is not None else (
            eval_ctx.get("quest_gate_snapshot") if isinstance(eval_ctx, Mapping) else None
        )
        q_gate_acc = _get_active_quest_gate_context(session_id, node, fac_node, quest_gate_snapshot=eff_q_snap)
        if q_gate_acc.get("has_earned_clearance"):
            is_unlocked = True
            curfew_active = False
            curfew_label = ""
            schedule_locked = False
            is_trespassing = False
            sched_reason_code = "quest_handover_clearance"
            sched_reason_label = "Quest Handover Clearance"

    # Status Badge
    owned_badge = ""
    for_sale_badge = ""
    if session_id:
        try:
            from .residences import get_player_owned_or_starter_property_for_node, is_unpurchased_realty_node
            p_props = eval_ctx.get("player_properties") if isinstance(eval_ctx, Mapping) else None
            owned_prop = get_player_owned_or_starter_property_for_node(
                session_id,
                node_id,
                session=session,
                world_node=node,
                world_node_loaded=True,
                player_properties=p_props,
            )
            if owned_prop is not None:
                tier = "open"
                is_unlocked = True
                curfew_active = False
                curfew_label = ""
                schedule_locked = False
                is_trespassing = False
                sched_reason_code = ""
                sched_reason_label = ""
                owned_badge = "Owned Residence" if not owned_prop.get("is_starter") else "Starter Quarters"
            else:
                unbought_realty = is_unpurchased_realty_node(
                    session_id,
                    node_id,
                    session=session,
                    player_properties=p_props,
                )
                if unbought_realty is not None and not is_unlocked:
                    tier = "private"
                    curfew_active = False
                    curfew_label = ""
                    schedule_locked = False
                    is_trespassing = False
                    sched_reason_code = "property_for_sale"
                    sched_reason_label = f"For Sale — {unbought_realty['price']}g"
                    for_sale_badge = f"For Sale — {unbought_realty['price']}g"
        except Exception:
            pass
    if owned_badge:
        status_badge = owned_badge
    elif for_sale_badge:
        status_badge = for_sale_badge
    elif is_unlocked and (tier in ("restricted", "private") or schedule_locked):
        status_badge = "Unlocked"
    elif sched_reason_code == "after_hours_anomaly_breach":
        status_badge = "Anomalous Breach (Unlocked)"
    elif sched_access.get("badge_override") and sched_reason_code == "theme_park_anomalous_shift":
        status_badge = sched_access["badge_override"]
    elif schedule_locked and sched_access.get("badge_override") and sched_reason_code in ("commercial_closed", "weekend_closed", "restricted"):
        status_badge = sched_access["badge_override"]
    elif curfew_active:
        status_badge = f"Curfew ({curfew_label})" if curfew_label else "Curfew"
    elif tier == "restricted":
        status_badge = "Restricted"
    elif tier == "private":
        status_badge = "Private"
    else:
        status_badge = "Open"

    residue = state.get("scene_residue") or fac_state.get("scene_residue") or ""
    residue_log = state.get("scene_residue_log") or fac_state.get("scene_residue_log") or []

    return {
        "access_tier": tier,
        "is_unlocked": is_unlocked,
        "curfew_active": curfew_active,
        "curfew_label": curfew_label,
        "status_badge": status_badge,
        "scene_residue": residue,
        "scene_residue_log": residue_log,
        "schedule_locked": schedule_locked,
        "is_trespassing": is_trespassing,
        "schedule_reason_code": sched_reason_code,
        "schedule_reason_label": sched_reason_label,
        "safe_sanctuary_exempt": bool(sanctuary_exempt),
    }


def record_node_unlock(
    session_id: int,
    node_id: str,
    unlock_type: str = "day",
    current_day: int = 1,
    reason: str = ""
) -> bool:
    """
    Persists an unlock event onto the node and its parent facility state_json.
    unlock_type: 'permanent' (persists session-long) or 'day' (resets next day).
    """
    if not session_id or not node_id:
        return False
    node = db.get_world_node(session_id, node_id)
    if not node:
        return False

    cur_state = db.get_world_node_state(session_id, node_id)
    updates: dict[str, Any] = {"last_unlock_reason": reason}
    if "unlocked_turn" not in cur_state:
        sess_cur = db.get_session(session_id) or {}
        updates["unlocked_turn"] = int(sess_cur.get("turn_count") or 0)
    if unlock_type == "permanent":
        updates["unlocked_permanent"] = True
    else:
        updates["unlocked_until_day"] = current_day

    db.update_world_node_state(session_id, node_id, updates)
    parent_id = str(node.get("parent_id") or "")
    multi_wing_parents = (
        "loc_agency_hq", "loc_private_hq_1", "loc_private_hq_2",
        "loc_general_hospital", "loc_theme_park", "loc_eastern_temple", "loc_botanical_zoo",
        "loc_cult_sanctum_hq", "loc_clandestine_syndicate_hq",
        "fac_agency_residence", "fac_temple_residence", "fac_cult_residence", "fac_syndicate_residence",
        "loc_hidden_kitsune_village", "loc_hidden_bunian_village",
    )
    if parent_id and node.get("node_type") == "ROOM" and not parent_id.startswith("bld_school_") and parent_id not in multi_wing_parents:
        db.update_world_node_state(session_id, parent_id, updates)
    return True


def has_npc_authority_for_node(npc: dict, node: dict, parent_node: dict | None = None) -> bool:
    """
    Determines if an NPC has authorized credentials/role for entering a restricted or curfew node.
    """
    if not isinstance(npc, dict) or not isinstance(node, dict):
        return False

    name = str(npc.get("name") or "").lower()
    role = str(npc.get("role") or (npc.get("basic_info") or {}).get("role") or "").lower()
    club = str(npc.get("club") or (npc.get("basic_info") or {}).get("club") or "").lower()

    n_id = str(node.get("node_id") or "").lower()
    n_name = str(node.get("name") or "").lower()
    p_id = str((parent_node or {}).get("node_id") or "").lower()
    p_name = str((parent_node or {}).get("name") or "").lower()
    full_target = f"{n_id} {n_name} {p_id} {p_name}"

    # Faculty & Staff have universal academic authority
    if any(k in role for k in ("teacher", "faculty", "staff", "nurse", "counselor", "principal", "guard", "security")):
        return True

    # Student Council authority
    if any(k in club or k in role for k in ("student council", "council", "president", "treasurer", "vice president")):
        if any(k in full_target for k in ("council", "homeroom", "hallway", "commons", "library")):
            return True

    # Club authority for matching facility
    if "swim" in club and "pool" in full_target:
        return True
    if any(k in club for k in ("kendo", "martial", "judo", "karate")) and "dojo" in full_target:
        return True
    if any(k in club for k in ("gym", "basketball", "volleyball", "athletics", "sports")) and ("gym" in full_target or "sports_field" in full_target or "track" in full_target):
        return True
    if any(k in club for k in ("drama", "theater", "theatre", "acting")) and "auditorium" in full_target:
        return True
    if any(k in club for k in ("art", "drawing", "sculpture")) and "fine_arts" in full_target:
        return True
    if any(k in club for k in ("music", "band", "orchestra")) and ("music" in full_target or "piano" in full_target):
        return True
    if any(k in club for k in ("science", "chem", "biology")) and "science_lab" in full_target:
        return True
    if any(k in club for k in ("broadcast", "newspaper", "media")) and "broadcasting" in full_target:
        return True
    if any(k in club for k in ("garden", "botany")) and "greenhouse" in full_target:
        return True
    if any(k in club for k in ("occult", "paranormal", "tarot")) and "old_storage" in full_target:
        return True
    if any(k in club for k in ("velvet", "secret society", "after-hours", "salon", "midnight", "crimson", "hedon")) and ("nsfw_faction_hq" in full_target or "velvet basement" in full_target):
        return True
    if str(npc.get("faction_category") or (npc.get("basic_info") or {}).get("faction_category") or "").lower() == "nsfw_club" and ("nsfw_faction_hq" in full_target or "velvet basement" in full_target):
        return True

    # Private residence ownership (resident's home)
    if "house" in full_target or "residence" in full_target or "bedroom" in full_target:
        if name and (name in full_target or any(part in full_target for part in name.split() if len(part) >= 3)):
            return True

    # Anomalous Incursions Faction HQ authority
    f_arch = str(npc.get("faction_archetype_key") or (npc.get("basic_info") or {}).get("faction_archetype_key") or "").lower()
    if f_arch:
        if f_arch == "public_agency" and ("loc_hq_" in full_target or "zone_agency_hq" in full_target or "loc_agency_hq" in full_target):
            return True
        if f_arch == "private_agency_1" and ("loc_private_hq_1" in full_target or "sub_priv1_" in full_target):
            return True
        if f_arch == "private_agency_2" and ("loc_private_hq_2" in full_target or "sub_priv2_" in full_target):
            return True
        if f_arch == "monastic_order" and ("loc_et_" in full_target or "zone_eastern_temple" in full_target):
            return True
        if f_arch == "cult_faction" and (
            "loc_cult_" in full_target or ("sub_cult_" in full_target and "sub_cult_res_" not in full_target)
        ):
            return True
        if f_arch == "clandestine_faction" and (
            "loc_clandestine_" in full_target or ("sub_synd_" in full_target and "sub_synd_res_" not in full_target)
        ):
            return True

    return False


def evaluate_anomalous_hq_access(
    session_id: int,
    node: dict,
    fac_node: dict | None = None,
    scen_key: str = "",
    *,
    faction_state: dict[str, Any] | None = None,
    quests: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Evaluates Tiered HQ Access Gates for Anomalous Incursions:
    - Public Lobbies, Contract Boards & Public Agency Shops are open to all friendly operatives & Freelancers.
    - Inner Sanctums, Containment Vaults, Operative Lounges & Private Armories require membership in that faction
      (or an active Story/Bounty quest waypoint or companion escort).
    - Cult & Clandestine HQs are restricted unless unlocked by a Story/Bounty waypoint or breach check.
    """
    try:
        from scenario_data import is_anomalous_incursions_scenario
        if not is_anomalous_incursions_scenario(scen_key):
            return {}
    except Exception:
        return {}

    n_id = str(node.get("node_id") or "").lower()
    n_name = str(node.get("name") or "").lower()
    p_id = str((fac_node or {}).get("node_id") or "").lower()
    p_name = str((fac_node or {}).get("name") or "").lower()
    combined = f"{n_id} {p_id} {n_name} {p_name}"

    required_arch = ""
    is_open_lobby_or_shop = False
    from mechanics.world.anomalous_sites import is_outlaw_hq_subnode

    # 1. Public Agency HQ (`loc_agency_hq` / `zone_agency_hq` / `loc_hq_*`)
    if "loc_hq_" in combined or n_id in ("zone_agency_hq", "loc_agency_hq") or p_id in ("zone_agency_hq", "loc_agency_hq"):
        if n_id == "loc_agency_hq":
            is_open_lobby_or_shop = True
        elif any(k in combined for k in (
            "loc_hq_main_lobby", "loc_hq_tactical_armory", "loc_hq_field_outfitter",
            "loc_hq_medical_bay", "loc_hq_cleansing_bay", "loc_hq_canteen_cafe",
            "loc_hq_executive_dispatch", "entrance", "lobby", "reception", "bounty"
        )) and "loc_hq_containment_sector" not in combined and "loc_hq_research_division" not in combined:
            is_open_lobby_or_shop = True
        elif any(k in combined for k in (
            "loc_hq_containment_sector", "loc_hq_research_division", "loc_hq_parapsych_lab",
            "loc_hq_training_range", "loc_hq_training_arena", "loc_hq_agent_dormitories",
        )):
            required_arch = "public_agency"

    # 2. Private Agency #1 HQ (`loc_private_hq_1` / `sub_priv1_*`) — Big Corporate Tower
    elif "loc_private_hq_1" in combined or "sub_priv1_" in combined:
        if n_id == "loc_private_hq_1" or any(k in combined for k in (
            "sub_priv1_entrance", "sub_priv1_dispatch", "entrance", "lobby", "atrium",
            "atrium concierge", "global contracts", "contracts & telemetry",
            "contract board", "contract & telemetry", "contract & tactical dispatch",
        )):
            is_open_lobby_or_shop = True
        else:
            required_arch = "private_agency_1"

    # 3. Private Agency #2 HQ (`loc_private_hq_2` / `sub_priv2_*`) — Small Commercial Office
    elif "loc_private_hq_2" in combined or "sub_priv2_" in combined:
        if n_id == "loc_private_hq_2" or any(k in combined for k in (
            "sub_priv2_entrance", "sub_priv2_dispatch", "entrance", "foyer", "reception",
            "brick-front vestibule", "security reception", "partner case room",
            "lobby", "corkboard", "dispatch bullpen", "contract board", "contract & tactical dispatch",
        )):
            is_open_lobby_or_shop = True
        else:
            required_arch = "private_agency_2"

    # 4. Monastic Shrine Order HQ (`loc_eastern_temple` / `loc_et_*`)
    elif "loc_et_" in combined or n_id in ("loc_eastern_temple", "zone_eastern_temple"):
        if any(k in combined for k in ("loc_et_five_story_pagoda", "loc_et_reliquary_pagoda", "loc_et_exorcist_dojo")) and "entrance" not in n_name:
            required_arch = "monastic_order"
        else:
            is_open_lobby_or_shop = True

    # 5. Cult & Clandestine HQs (`loc_cult_sanctum_hq`, `loc_clandestine_syndicate_hq`)
    elif (
        "loc_cult_sanctum_hq" in combined
        or is_outlaw_hq_subnode(n_id) == "cult_faction"
        or ("sub_cult_" in combined and "sub_cult_res_" not in combined)
    ):
        if n_id == "loc_cult_sanctum_hq" or "sub_cult_entrance" in combined or "ward-sealed threshold" in combined:
            is_open_lobby_or_shop = True
        else:
            required_arch = "cult_faction"
    elif (
        "loc_clandestine_syndicate_hq" in combined
        or is_outlaw_hq_subnode(n_id) == "clandestine_faction"
        or ("sub_synd_" in combined and "sub_synd_res_" not in combined)
    ):
        if n_id == "loc_clandestine_syndicate_hq" or "sub_synd_entrance" in combined or "biometric vault door entrance" in combined:
            is_open_lobby_or_shop = True
        else:
            required_arch = "clandestine_faction"

    if is_open_lobby_or_shop and not required_arch:
        return {"force_open": True}
    if not required_arch:
        return {}

    if faction_state is None:
        from mechanics.social.factions import get_anomalous_faction_state
        f_state = get_anomalous_faction_state(session_id)
    else:
        f_state = faction_state
    player_arch = str(f_state.get("faction_archetype_key") or "").lower()
    if player_arch == required_arch:
        return {"force_open": True, "unlocked_by_faction": required_arch}

    # Check if an active Story Quest or Accepted Bounty targets this location
    try:
        quests_list = db.get_session_quests(session_id) or [] if quests is None else quests
        for q in quests_list:
            if str(q.get("status") or "").lower() in ("active", "accepted", "in_progress"):
                cand_locs = [
                    str(q.get("target_location") or "").lower(),
                    str(q.get("waypoint") or "").lower(),
                    str(q.get("location") or "").lower(),
                ]
                for wp_item in (q.get("waypoints") or []):
                    if isinstance(wp_item, dict):
                        cand_locs.append(str(wp_item.get("location") or wp_item.get("name") or "").lower())
                    elif wp_item:
                        cand_locs.append(str(wp_item).lower())
                for wp in cand_locs:
                    if wp and (wp in combined or (n_name and len(n_name) >= 5 and n_name in wp) or (p_name and len(p_name) >= 5 and p_name in wp)):
                        return {
                            "force_open": True,
                            "unlocked_by_quest": bool(q.get("is_story_quest")),
                            "unlocked_by_bounty": not bool(q.get("is_story_quest")),
                        }
    except Exception:
        pass

    label_map = {
        "public_agency": "Restricted Bureau Inner Sector (Public Agency Clearance Required)",
        "private_agency_1": "Restricted High-Security Tower Floor & Vault (Conglomerate Clearance Required)",
        "private_agency_2": "Restricted Partner Suite & Vaulted Armory (Agency Partner Credentials Required)",
        "monastic_order": "Restricted Monastic Inner Sanctum (Order Initiate Clearance Required)",
        "cult_faction": "Ward-Sealed Occult Sanctum (Hostile Cult Restricted Area)",
        "clandestine_faction": "Biometric Clandestine Vault (Unauthorized Entry Prohibited)",
    }
    return {
        "force_restricted": True,
        "required_faction_archetype": required_arch,
        "reason_label": label_map.get(required_arch, "Restricted Faction Sector"),
    }


def _is_npc_private_residence_node(
    node: dict | None,
    fac_node: dict | None,
    low_id: str,
    display_name: str,
) -> bool:
    """Returns True when a private-tier node belongs to an NPC residence rather than player quarters."""
    if not isinstance(node, dict) or str(node.get("access_tier") or "").strip().lower() != "private":
        return False
    if str(node.get("node_type") or "").strip().upper() == "ZONE":
        return False
    if bool(node.get("is_anomalous")) or bool((fac_node or {}).get("is_anomalous")):
        return False
    st_low = str(node.get("state_json") or "").lower()
    fac_st_low = str((fac_node or {}).get("state_json") or "").lower()
    if '"is_anomalous": true' in st_low or '"is_anomalous":true' in st_low:
        return False
    if '"is_anomalous": true' in fac_st_low or '"is_anomalous":true' in fac_st_low:
        return False

    disp_low = str(display_name or "").strip().lower()
    low_id_spaced = str(low_id or "").replace("_", " ").strip().lower()
    if low_id in ("loc_player_house", "sub_player_bedroom") or "player's house" in disp_low:
        return False

    from .graph_seeder import COMPOUND_HOUSE_EXCLUSIONS
    if any(c in disp_low or c in low_id_spaced for c in COMPOUND_HOUSE_EXCLUSIONS):
        return False

    if re.search(r"\b(house|residence|apartment)\b", low_id_spaced) or re.search(r"\b(house|residence|apartment)\b", disp_low):
        return True
    if low_id.startswith(("sub_npc_res_", "fac_npc_res_", "npc_res_")):
        return True
    if str(node.get("category") or "").strip().lower() == "residential":
        return True
    if isinstance(fac_node, dict) and str(fac_node.get("category") or "").strip().lower() == "residential":
        return True
    return False


def _parse_basic_info_dict(row: dict | None) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    raw = row.get("basic_info")
    if isinstance(raw, dict):
        return raw
    raw_json = row.get("basic_info_json")
    if isinstance(raw_json, str) and raw_json.strip():
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def evaluate_node_access_gate(
    session_id: int,
    target_node_id: str,
    session: dict,
    actions: list = None,
    party: list = None,
    companions: list = None,
    persist_db: bool = True,
) -> dict[str, Any]:
    """
    Evaluates whether player travel to target_node_id is halted by a lock, curfew,
    world schedule restriction, weekday school-hours truancy lockdown, or private residence intercom barrier.
    """
    if not session_id or not target_node_id:
        return {"gated": False}

    node = db.get_world_node(session_id, target_node_id)
    if not node:
        return {"gated": False}

    db_day, db_min, _ = db.get_session_time(session_id)
    curr_day = int(session.get("current_day") if (isinstance(session, dict) and session.get("current_day") is not None) else db_day)
    curr_min = int(session.get("current_minute") if (isinstance(session, dict) and session.get("current_minute") is not None) else db_min)
    safe_min = curr_min % 1440
    scen_key = (session.get("scenario") if isinstance(session, dict) else "") or "high_school_drama"

    from mechanics.world.schedules import get_time_block_key
    from mechanics.world.world_schedule import (
        is_abandoned_school_node,
        is_campus_node_or_location,
        is_high_school_setting,
        is_university_node_or_location,
        is_weekend,
    )
    time_block = (session.get("time_slot") if isinstance(session, dict) else None) or get_time_block_key(curr_min)

    fac_node = db.get_world_node(session_id, node["parent_id"]) if (node.get("parent_id") and node.get("node_type") == "ROOM") else None
    display_name = node.get("name") or target_node_id
    fac_name = fac_node.get("name") if fac_node else display_name
    low_id = target_node_id.lower()

    # 0. Special Condition: Abandoned School Building (`zone_abandoned_school`) is ALWAYS accessible 24/7
    if is_abandoned_school_node(node, fac_node, location_str=display_name):
        return {"gated": False, "abandoned_school_unrestricted": True}

    # Inventory & Accompanying Companion extraction (used by both Truancy Gate and Facility Gate)
    inventory_items = []
    for member in (party or []):
        c_obj = member[0] if isinstance(member, (tuple, list)) else member
        if isinstance(c_obj, dict):
            for it in (c_obj.get("inventory") or []):
                it_name = str(it.get("name") if isinstance(it, dict) else it).lower()
                inventory_items.append(it_name)
    inv_str = " ".join(inventory_items)

    active_companions = list(companions or [])
    if isinstance(session, dict):
        if session.get("temporary_companions"):
            active_companions.extend(session["temporary_companions"])
        if session.get("dialogue_partners"):
            for dp in session["dialogue_partners"]:
                if dp and not any(dp.lower() == (c.get("name") or "").lower() for c in active_companions if isinstance(c, dict)):
                    active_companions.append({"name": dp})

    current_action_label = " ".join(str(a.get("label", "") if isinstance(a, dict) else a) for a in (actions or [])).lower()
    has_check = bool(actions and isinstance(actions[0], dict) and (actions[0].get("check") or str(actions[0].get("stat", "NONE")).upper() != "NONE"))
    is_breach_action = has_check or any(w in current_action_label for w in (
        "sneak", "pick", "climb", "scale", "fence", "lockpick", "force", "break in", "bypass",
        "talk your way", "convince", "excuse", "nurse", "ring the intercom", "buzz", "apologize",
        "audition", "charm", "cellar", "grate", "contract permit", "freelance permit", "public agency", "flash permit"
    ))

    action_check_tier = ""
    if actions and isinstance(actions[0], dict) and actions[0].get("check"):
        chk = actions[0]["check"]
        if isinstance(chk, dict):
            action_check_tier = str(chk.get("tier") or "").lower()
        else:
            action_check_tier = str(getattr(chk, "tier", "") or "").lower()

    # A breach only counts as "rolled" when it was a real stat check (AGI/CHA/...), never an
    # auto-success NONE/FREE/ITEM action or a freeform label that merely contains "sneak"/"excuse".
    _first_action = actions[0] if (actions and isinstance(actions[0], dict)) else {}
    _action_stat = str(_first_action.get("stat") or "").upper().strip()
    if not _action_stat:
        _stat_tag = re.match(r"^\s*\[([A-Za-z]{3})\]", str(_first_action.get("label") or ""))
        _action_stat = _stat_tag.group(1).upper() if _stat_tag else ""
    is_rolled_stat_breach = bool(
        _action_stat and _action_stat not in ("NONE", "FREE", "ITEM")
        and action_check_tier in ("critical_success", "crit_success", "success", "partial_success")
    )
    is_permit_action = any(k in current_action_label for k in ("contract permit", "freelance permit", "flash permit"))

    # 0b. High School Weekday Class Hours (08:00–15:00 Mon–Fri): Outbound Truancy Lockdown & Late Arrival
    late_arrival_directive = ""
    if is_high_school_setting(scen_key) and not is_weekend(curr_day) and (480 <= safe_min < 900):
        raw_curr_loc = (session.get("current_location") if isinstance(session, dict) else "") or ""
        curr_node_id = (session.get("current_node_id") if isinstance(session, dict) else "") or ""
        curr_node_obj = db.get_world_node(session_id, curr_node_id) if curr_node_id else None
        curr_parent_obj = (
            db.get_world_node(session_id, curr_node_obj["parent_id"])
            if (curr_node_obj and curr_node_obj.get("parent_id"))
            else None
        )
        player_on_campus = is_campus_node_or_location(
            curr_node_obj, curr_parent_obj, location_str=raw_curr_loc, session_id=session_id, scen_key=scen_key
        )
        target_on_campus = is_campus_node_or_location(
            node, fac_node, location_str=display_name, session_id=session_id, scen_key=scen_key
        )

        # If player is already halted at loc_school_gate on Turn 2 and chooses "Return to campus grounds"
        if low_id == "loc_school_gate" and "return to campus" in current_action_label:
            if persist_db:
                db.update_world_node_state(session_id, "loc_school_gate", {"pending_truancy_target_node_id": "", "pending_truancy_target_name": ""})
            return {"gated": False, "returned_to_campus": True}

        # If player is halted at loc_school_gate on Turn 2 and attempts an outbound truancy breach
        gate_state = db.get_world_node_state(session_id, "loc_school_gate")
        if low_id == "loc_school_gate" and is_breach_action and gate_state.get("pending_truancy_target_node_id"):
            pending_id = gate_state["pending_truancy_target_node_id"]
            pending_node = db.get_world_node(session_id, pending_id)
            if pending_node:
                node = pending_node
                target_node_id = pending_id
                low_id = pending_id.lower()
                fac_node = db.get_world_node(session_id, node["parent_id"]) if (node.get("parent_id") and node.get("node_type") == "ROOM") else None
                display_name = node.get("name") or target_node_id
                fac_name = fac_node.get("name") if fac_node else display_name
                target_on_campus = False

        # Preserve direct NPC private residence intercom tests while enforcing truancy on all other off-campus destinations
        is_npc_private_home = _is_npc_private_residence_node(node, fac_node, low_id, display_name)
        from mechanics.social.origin_mode import is_adult_ahs_operative_fail_closed
        _is_adult_in_ahs = is_adult_ahs_operative_fail_closed(session, session_id=session_id, scen_key=scen_key)

        if player_on_campus and not target_on_campus and not is_npc_private_home:
            has_truancy_pass = (
                _is_adult_in_ahs
                or (gate_state.get("truancy_unlocked_day") or 0) >= curr_day
                or (isinstance(session, dict) and int(session.get("infirmary_pass_day") or 0) >= curr_day)
                or any(k in inv_str for k in ("hall pass", "nurse pass", "sick pass", "early dismissal", "staff pass", "gate pass", "master key", "council badge"))
                or any(
                    isinstance(comp, dict)
                    and any(r in str(comp.get("role") or (comp.get("basic_info") or {}).get("role") or "").lower() for r in ("teacher", "faculty", "staff", "nurse", "counselor", "principal"))
                    for comp in active_companions
                )
            )
            if not has_truancy_pass:
                from mechanics.world.locations.seeds import get_session_school_name
                school_zone = get_session_school_name(session_id, scen_key) or "Main Academy Campus"
                halt_loc = f"{school_zone} ➔ School Main Gates ➔ Outside the Locked Entrance"

                # Public Agency Freelance Contract Permit is only valid for Student Operatives in
                # Anomalous High while an off-campus daytime breach or an active contract exists.
                permit_valid = bool(
                    scenario_data.is_anomalous_high_school_scenario(scen_key)
                    and (
                        any(
                            isinstance(inc, dict)
                            and not inc.get("resolved")
                            and str(inc.get("time_window") or "") != "after_hours"
                            and not is_campus_node_or_location(
                                location_str=str(inc.get("location") or ""),
                                session_id=session_id,
                                scen_key=scen_key,
                            )
                            for inc in ((session.get("daily_incursions") if isinstance(session, dict) else None) or [])
                        )
                        or bool(db.get_session_quests(session_id, status="Active"))
                    )
                )

                if (is_permit_action and permit_valid) or is_rolled_stat_breach:
                    if persist_db:
                        db.update_world_node_state(
                            session_id,
                            "loc_school_gate",
                            {"truancy_unlocked_day": curr_day, "pending_truancy_target_node_id": "", "pending_truancy_target_name": ""}
                        )
                    return {
                        "gated": False,
                        "unlocked_by": "agency_contract_permit" if (is_permit_action and permit_valid) else "truancy_bypass",
                        "resolved_target_node_id": target_node_id,
                        "resolved_target_name": display_name,
                    }
                if is_breach_action and action_check_tier in ("fail", "failure", "crit_fail", "critical_fail", "critical_failure"):
                    return {
                        "gated": True,
                        "node_id": "loc_school_gate",
                        "facility_node_id": "loc_school_gate",
                        "node_name": "School Main Gates",
                        "halt_location_override": halt_loc,
                        "reason_code": "school_hours_lockdown",
                        "reason_label": "Caught Attempting Truancy (08:00–15:00)",
                        "focal_point": "At the School Main Gates (Intercepted by Campus Gatekeeper)",
                        "patrol_confrontation": True,
                        "patrol_npc": {
                            "name": "Officer Takahashi",
                            "role": "Campus Gatekeeper",
                            "stage_role": "active_partner",
                            "attention_ring": "ring_1_primary",
                            "status_effects": ["Alerted"],
                        },
                        "prompt_directive": (
                            f"[SYSTEM: TRUANCY ATTEMPT INTERCEPTED (08:00–15:00)]\n"
                            f"The player attempted to sneak off campus toward {display_name} during active school hours, "
                            f"but was intercepted at the School Main Gates by the Campus Gatekeeper!"
                        ),
                        "barrier_choices": [
                            Phase2Choice(f"[CHA] Apologize and make up an excuse about forgetting a textbook", stat="CHA", requirement=10),
                            Phase2Choice("Return to campus grounds", stat="NONE", requirement=0),
                        ],
                    }

                if persist_db:
                    db.update_world_node_state(
                        session_id,
                        "loc_school_gate",
                        {"pending_truancy_target_node_id": target_node_id, "pending_truancy_target_name": display_name}
                    )
                return {
                    "gated": True,
                    "node_id": "loc_school_gate",
                    "facility_node_id": "loc_school_gate",
                    "node_name": "School Main Gates",
                    "halt_location_override": halt_loc,
                    "reason_code": "school_hours_lockdown",
                    "reason_label": "School Hours Lockdown (08:00–15:00 — Leaving Campus Forbidden)",
                    "focal_point": "At the Locked School Main Gates (Class Hours Lockdown 08:00–15:00)",
                    "prompt_directive": (
                        f"[SYSTEM: SCHOOL HOURS LOCKDOWN (08:00–15:00) — LEAVING CAMPUS FORBIDDEN]\n"
                        f"The player attempted to leave the school areas for {display_name} during active class hours (08:00 AM–3:00 PM Monday–Friday).\n"
                        f"- School rules strictly forbid students from leaving the school areas between 08:00 and 15:00.\n"
                        f"- Place the scene at '{halt_loc}' where the closed iron gates and campus gatekeeper block students from leaving.\n"
                        f"- The player must pass an [AGI] check to climb the side perimeter fence/sneak out, pass a [CHA] check to bluff past the gatekeeper with an excuse, or return to campus."
                    ),
                    "barrier_choices": (
                        [
                            Phase2Choice(
                                f"🪪 Flash Public Agency Freelance Contract Permit to leave for {display_name}",
                                stat="NONE",
                                requirement=0,
                            )
                        ]
                        if permit_valid
                        else []
                    ) + [
                        Phase2Choice(f"[AGI] Sneak out by climbing the side perimeter fence toward {display_name}", stat="AGI", requirement=12),
                        Phase2Choice(f"[CHA] Convince the gatekeeper with a nurse's pass or family emergency excuse to leave for {display_name}", stat="CHA", requirement=11),
                        Phase2Choice("Return to campus grounds", stat="NONE", requirement=0),
                    ],
                }
        elif (
            (not player_on_campus)
            and target_on_campus
            and safe_min > 480
            and not _is_adult_in_ahs
            and not is_university_node_or_location(node, fac_node, location_str=display_name, node_id=target_node_id)
        ):
            late_arrival_directive = (
                f"[SYSTEM: LATE ARRIVAL TO SCHOOL ({format_minute_to_hhmm(safe_min)})]\n"
                f"The player is arriving on campus after the 08:00 AM first bell during active class hours. "
                f"Acknowledge the tardiness in the narration (quiet corridors, classes already underway, or slipping through the gate late)."
            )

    # 1. Player's own home is always accessible to the player (once off-campus)
    from .residences import get_player_owned_or_starter_property_for_node, is_unpurchased_realty_node
    from .realty_catalog import is_anomalous_realty_scenario
    if (get_player_owned_or_starter_property_for_node(session_id, target_node_id, session=session if isinstance(session, dict) else None) is not None) or (not is_anomalous_realty_scenario(scen_key) and (low_id in ("loc_player_house", "sub_player_bedroom") or "player's house" in display_name.lower())):
        return {"gated": False}

    # 1b. Love Hotel Automated Suite Rental (`$40` Mirrored Suite / `$80` Rooftop Jacuzzi Suite + Partner Waiver)
    node_state_raw = db.get_world_node_state(session_id, target_node_id)
    if low_id in ("sub_love_hotel_mirrored", "sub_love_hotel_jacuzzi") or node_state_raw.get("suite_fee"):
        suite_fee = int(node_state_raw.get("suite_fee") or (80 if "jacuzzi" in low_id else 40))
        suite_bonus = 3 if "jacuzzi" in low_id else 1
        if (
            (node_state_raw.get("suite_paid_day") or 0) >= curr_day
            or (node_state_raw.get("unlocked_until_day") or 0) >= curr_day
            or node_state_raw.get("unlocked_permanent")
        ):
            if isinstance(session, dict):
                session["active_love_hotel_suite_bonus"] = suite_bonus
            return {"gated": False, "love_hotel_suite_bonus": suite_bonus}

        # Check Partner-Invited Waiver ($0)
        partner_waived = bool(
            isinstance(session, dict)
            and (
                session.get("partner_treating_love_hotel")
                or int(session.get("love_hotel_waived_day") or 0) >= curr_day
            )
        )
        if not partner_waived:
            appts_lh = (db.get_phone_appointments(session_id, status="pending") or []) + (db.get_phone_appointments(session_id, status="arrived") or [])
            for appt in appts_lh:
                appt_t = str(appt.get("target_node_id") or "").lower()
                appt_l = str(appt.get("rendezvous_location") or "").lower()
                if any(k in f"{appt_t} {appt_l}" for k in ("love_hotel", "love hotel", "mirrored luxury", "rooftop jacuzzi")):
                    partner_waived = True
                    break

        if partner_waived:
            if persist_db:
                db.update_world_node_state(
                    session_id,
                    target_node_id,
                    {"suite_paid_day": curr_day, "unlocked_until_day": curr_day, "last_unlock_reason": "partner_treated_suite"},
                )
            if isinstance(session, dict):
                session["active_love_hotel_suite_bonus"] = suite_bonus
            return {
                "gated": False,
                "unlocked_by": "partner_treated_suite",
                "suite_fee_paid": 0,
                "love_hotel_suite_bonus": suite_bonus,
                "prompt_directive": (
                    f"[STAGE DIRECTION — SUITE TREATED BY PARTNER]: Your partner already handled the automated kiosk fee "
                    f"for {display_name} ($0 charged to you; suite unlocked for the day/night)."
                ),
            }

        # Check player gold & deduct automated suite fee
        char_obj = None
        for member in (party or []):
            cand = member[0] if isinstance(member, (tuple, list)) else member
            if isinstance(cand, dict) and (cand.get("user_id") or cand.get("gold") is not None):
                char_obj = cand
                break
        user_id = int((char_obj or {}).get("user_id") or (session.get("host_id") if isinstance(session, dict) else 0) or 0)
        db_char = db.get_character(user_id) if user_id else None
        avail_gold = int(
            (char_obj.get("gold") if (char_obj and char_obj.get("gold") is not None) else (db_char or {}).get("gold")) or 0
        )

        if avail_gold >= suite_fee:
            if persist_db and user_id and db_char:
                db.apply_hp_mp_delta(user_id, gold_delta=-suite_fee)
            if isinstance(char_obj, dict):
                char_obj["gold"] = max(0, avail_gold - suite_fee)
            if persist_db:
                db.update_world_node_state(
                    session_id,
                    target_node_id,
                    {"suite_paid_day": curr_day, "unlocked_until_day": curr_day, "last_unlock_reason": "suite_fee_paid"},
                )
            if isinstance(session, dict):
                session["active_love_hotel_suite_bonus"] = suite_bonus
            return {
                "gated": False,
                "unlocked_by": "love_hotel_suite_payment",
                "suite_fee_paid": suite_fee,
                "love_hotel_suite_bonus": suite_bonus,
                "prompt_directive": (
                    f"[STAGE DIRECTION — AUTOMATED SUITE UNLOCKED]: The discreet touchscreen kiosk dispenses a magnetic keycard "
                    f"for {display_name} (${suite_fee} paid; unlocked for the rest of the day/night)."
                ),
            }
        else:
            lobby_choices = []
            if low_id == "sub_love_hotel_jacuzzi" and avail_gold >= 40:
                lobby_choices.append(Phase2Choice("Rent the Mirrored Luxury Suite ($40) instead", stat="NONE", requirement=0))
            lobby_choices.append(Phase2Choice("Step back into the Automated Touchscreen Check-In Lobby", stat="NONE", requirement=0))
            return {
                "gated": True,
                "node_id": "sub_love_hotel_lobby",
                "facility_node_id": "loc_love_hotel",
                "node_name": display_name,
                "reason_code": "insufficient_funds",
                "reason_label": f"Automated Suite Kiosk Requires ${suite_fee} (You have ${avail_gold})",
                "focal_point": "At the Automated Touchscreen Check-In Kiosk",
                "prompt_directive": (
                    f"[SYSTEM: LOVE HOTEL AUTOMATED SUITE KIOSK — INSUFFICIENT FUNDS]\n"
                    f"The glowing touchscreen panel in the clerkless lobby displays a ${suite_fee} rate for {display_name}, "
                    f"but the player currently only carries ${avail_gold}. Halt at the Automated Touchscreen Check-In Lobby."
                ),
                "barrier_choices": lobby_choices,
            }

    # 1c. NSFW Secret Society HQ (`loc_nsfw_club_facility` / `loc_nsfw_faction_hq` / `Velvet Basement Salon`) Speakeasy Gate
    is_nsfw_salon_target = (
        low_id == "loc_nsfw_faction_hq"
        or low_id.startswith("loc_nsfw_")
        or (fac_node and fac_node.get("node_id") == "loc_nsfw_club_facility")
        or "velvet basement" in display_name.lower()
    )
    if is_nsfw_salon_target:
        from .seeding import has_player_nsfw_salon_membership_or_standing, reveal_hidden_club_facility
        has_salon_access = has_player_nsfw_salon_membership_or_standing(
            session_id,
            session=session if isinstance(session, dict) else None,
            current_day=curr_day,
            for_atlas_visibility=False,
        )
        if has_salon_access:
            invited_ok = isinstance(session, dict) and (
                session.get("nsfw_faction_member")
                or int(session.get("nsfw_faction_invited_day") or 0) >= curr_day
            )
            unlock_reason = "nsfw_faction_invite" if invited_ok else "nsfw_faction_standing"
            if persist_db:
                record_node_unlock(session_id, target_node_id, unlock_type="day", current_day=curr_day, reason=unlock_reason)
                if fac_node and fac_node.get("node_id") == "loc_nsfw_club_facility":
                    record_node_unlock(session_id, "loc_nsfw_club_facility", unlock_type="day", current_day=curr_day, reason=unlock_reason)
                try:
                    reveal_hidden_club_facility(session_id, "loc_nsfw_club_facility")
                except Exception:
                    pass
            return {"gated": False, "unlocked_by": unlock_reason}

    # 1d. Hidden Folklore Villages Veil Gate & Sanctuary Treaty (must run BEFORE Step 2 open check & Step 3 \bkey\b regex)
    from .folklore_veil import evaluate_folklore_veil_gate
    veil_gate_res = evaluate_folklore_veil_gate(
        session_id=session_id,
        target_node_id=target_node_id,
        node=node,
        fac_node=fac_node,
        session=session if isinstance(session, dict) else None,
        actions=actions,
        party=party,
        active_companions=active_companions,
        current_minute=safe_min,
        persist_db=persist_db,
    )
    if veil_gate_res is not None:
        if not veil_gate_res.get("gated") and late_arrival_directive and not veil_gate_res.get("prompt_directive"):
            veil_gate_res["late_arrival_warning"] = True
            veil_gate_res["prompt_directive"] = late_arrival_directive
        return veil_gate_res

    # 2. Check access info & existing unlocks
    q_gate_snap = build_active_quest_gate_snapshot(session_id)
    access_info = get_node_effective_access_info(
        session_id,
        target_node_id,
        current_day=curr_day,
        current_minute=curr_min,
        scen_key=scen_key,
        session=session if isinstance(session, dict) else None,
        quest_gate_snapshot=q_gate_snap,
    )
    if access_info["is_unlocked"]:
        res = {"gated": False}
        if late_arrival_directive:
            res["late_arrival_warning"] = True
            res["prompt_directive"] = late_arrival_directive
        return res

    tier = access_info["access_tier"]
    curfew_active = access_info["curfew_active"]
    schedule_locked = access_info.get("schedule_locked", False)
    is_trespassing = access_info.get("is_trespassing", False)

    # If it's an open node and neither curfew nor schedule lock is active, access is clear!
    if tier == "open" and not curfew_active and not schedule_locked:
        res = {"gated": False}
        if late_arrival_directive:
            res["late_arrival_warning"] = True
            res["prompt_directive"] = late_arrival_directive
        return res

    # Special Rule: Theme Park 22:00–08:00 Anomalous Shift allows nocturnal field investigation past warped turnstiles
    if access_info.get("schedule_reason_code") == "theme_park_anomalous_shift":
        return {
            "gated": False,
            "is_trespassing": True,
            "anomalous_shift_active": True,
            "prompt_directive": (
                "[STAGE DIRECTION — THEME PARK ANOMALOUS SHIFT (22:00–08:00)]: "
                "The Theme Park & Amusement Resort is closed to civilian crowds after 10:00 PM, "
                "but active spatial distortion leaves the shuttered turnstiles warped open. "
                "Depict an eerie nocturnal carnival atmosphere: reversed calliope music, flickering neon midway lights, "
                "zero mundane tourists, and active anomalous phenomena."
            ),
        }

    # 3. Check Inventory for Key / Pass / Badge (strict word-boundary match so "Keychain"/"Whiskey" never unlock vaults)
    unbought_realty = is_unpurchased_realty_node(session_id, target_node_id, session=session if isinstance(session, dict) else None) if session_id else None
    if (unbought_realty is None) and re.search(
        r"\b(master key|skeleton key|staff pass|council badge|keycard|passcard|access card|clearance badge|door key|gate key|vault key|sanctum key|room key|office key|key)\b",
        inv_str,
    ):
        if persist_db:
            record_node_unlock(session_id, target_node_id, unlock_type="permanent", current_day=curr_day, reason="key")
        return {"gated": False, "unlocked_by": "key"}

    # 4. Check Accompanying Companion Authority
    for comp in ([] if unbought_realty else active_companions):
        if isinstance(comp, dict) and has_npc_authority_for_node(comp, node, fac_node):
            if persist_db:
                record_node_unlock(session_id, target_node_id, unlock_type="day", current_day=curr_day, reason="companion_authority")
            return {"gated": False, "unlocked_by": "companion_authority", "authorized_npc": comp.get("name")}

    # 5. Check Illicit / Scheduled Rendezvous (Edge Case 2)
    appts = (db.get_phone_appointments(session_id, status="pending") or []) + (db.get_phone_appointments(session_id, status="arrived") or [])
    for appt in appts:
        appt_target = appt.get("target_node_id") or ""
        appt_loc = appt.get("rendezvous_location") or ""
        is_match = False
        if appt_target:
            is_match = db.is_descendant_of(session_id, target_node_id, appt_target) or db.is_descendant_of(session_id, appt_target, target_node_id)
        elif appt_loc:
            from mechanics.world.waypoints import check_location_matches_waypoint
            is_match = check_location_matches_waypoint(display_name, appt_loc) or check_location_matches_waypoint(appt_loc, display_name)

        if is_match:
            if persist_db:
                record_node_unlock(session_id, target_node_id, unlock_type="day", current_day=curr_day, reason="illicit_rendezvous")
            return {
                "gated": False,
                "unlocked_by": "illicit_rendezvous",
                "illicit_rendezvous_npc": appt.get("npc_name", "your partner")
            }

    # 6. Check Private Residence Intercom Gate (Edge Case 5) + Living World Doorbell & Spare Keys (Seam 2)
    intercom_reason_code = ""
    intercom_reason_label = ""
    if (unbought_realty is None) and _is_npc_private_residence_node(node, fac_node, low_id, display_name):
        world_roster = db.get_world_roster(session_id, include_legacy_rosters=False) or []
        contacts = db.get_contacts(session_id) or []
        disp_low = display_name.lower()
        target_node_ids = {str(target_node_id or "").strip().lower()}
        if isinstance(fac_node, dict) and fac_node.get("node_id"):
            target_node_ids.add(str(fac_node["node_id"]).strip().lower())

        def _matches_display(name_val: Any) -> bool:
            c_low = str(name_val or "").strip().lower()
            if not c_low:
                return False
            tokens = [t for t in re.split(r"[\s_]+", c_low) if len(t) >= 3]
            return (c_low in disp_low) or any(t in disp_low for t in tokens)

        def _row_aliases(row_obj: dict[str, Any]) -> set[str]:
            return {
                str(row_obj.get(f) or "").strip().lower()
                for f in ("npc_id", "person_key", "npc_key", "name")
                if str(row_obj.get(f) or "").strip()
            }

        roster_row = None
        for r in world_roster:
            if not isinstance(r, dict):
                continue
            r_basic_probe = _parse_basic_info_dict(r)
            r_home = str(r.get("home_node_id") or r_basic_probe.get("home_node_id") or "").strip().lower()
            if r_home and r_home in target_node_ids:
                roster_row = r
                break
        if roster_row is None:
            for r in world_roster:
                if isinstance(r, dict) and _matches_display(r.get("name")):
                    roster_row = r
                    break

        resident_contact = None
        if roster_row is not None:
            r_aliases = _row_aliases(roster_row)
            for c in contacts:
                if isinstance(c, dict) and (_row_aliases(c) & r_aliases):
                    resident_contact = c
                    break
        if resident_contact is None:
            for c in contacts:
                if isinstance(c, dict) and c.get("name") and _matches_display(c.get("name")):
                    resident_contact = c
                    break
        if roster_row is None and resident_contact is not None:
            c_aliases = _row_aliases(resident_contact)
            for r in world_roster:
                if isinstance(r, dict) and (_row_aliases(r) & c_aliases):
                    roster_row = r
                    break

        res_name = str((roster_row or {}).get("name") or (resident_contact or {}).get("name") or "").strip()
        if roster_row is not None or resident_contact is not None:
            r_basic = _parse_basic_info_dict(roster_row)
            c_basic = _parse_basic_info_dict(resident_contact)
            has_spare_key = any(
                bool(src.get("player_has_spare_key") or src.get("spare_key_granted"))
                for src in (roster_row or {}, r_basic, resident_contact or {}, c_basic)
                if isinstance(src, dict)
            )
            is_cohabitant = False
            if not has_spare_key:
                from mechanics.world.presence_doorbell import is_verified_household_cohabitant

                merged_res = {**(resident_contact or {}), **(roster_row or {})}
                is_cohabitant = is_verified_household_cohabitant(
                    session_id,
                    merged_res,
                    resident_contact,
                    {},
                    None,
                    "",
                )
            if has_spare_key or is_cohabitant:
                if persist_db:
                    record_node_unlock(session_id, target_node_id, unlock_type="day", current_day=curr_day, reason="spare_key")
                return {"gated": False, "unlocked_by": "spare_key", "resident_name": res_name}

            from mechanics.world.presence_graph import is_deceased_or_arrested

            merged_res_check = {**(resident_contact or {}), **(roster_row or {})}
            if is_deceased_or_arrested(merged_res_check):
                intercom_reason_code = "private_intercom"
                intercom_reason_label = f"No Answer at Intercom — {res_name or 'Resident'} Unavailable"
            else:
                raw_score = (resident_contact or {}).get("relationship_score")
                if raw_score is None and roster_row is not None:
                    raw_score = roster_row.get("affinity_score")
                score = int(raw_score or 0)
                track = str((resident_contact or {}).get("track") or "").lower()
                is_high_bond = (
                    (score >= 40)
                    or (track == "romantic")
                    or bool(roster_row and (roster_row.get("is_romantic") or r_basic.get("is_romantic")))
                )

                has_anchored_schedule = bool(
                    roster_row
                    and (
                        str(roster_row.get("home_node_id") or r_basic.get("home_node_id") or "").strip()
                        or str(roster_row.get("workplace_node_id") or r_basic.get("workplace_node_id") or "").strip()
                        or isinstance(roster_row.get("autonomy_override"), dict)
                        or isinstance(r_basic.get("autonomy_override"), dict)
                    )
                )
                if has_anchored_schedule and roster_row is not None:
                    from mechanics.world.npc_autonomy import resolve_autonomy_node_override
                    from mechanics.world.presence_doorbell import check_doorbell_etiquette

                    ov = resolve_autonomy_node_override(
                        roster_row,
                        session_id=session_id,
                        day=curr_day,
                        block=get_time_block_key(safe_min),
                        scen_key=scen_key,
                    )
                    dbell = check_doorbell_etiquette(
                        session_id,
                        roster_row,
                        target_node_id,
                        current_day=curr_day,
                        current_minute=safe_min,
                        scen_key=scen_key,
                        session=session if isinstance(session, dict) else None,
                        roster_row=roster_row,
                        roster_loaded=True,
                        contact_row=resident_contact,
                        contacts=contacts,
                        contacts_loaded=True,
                        autonomy_override=ov,
                    )
                    if dbell.get("applicable") and not dbell.get("allowed"):
                        if dbell.get("doorbell_status") == "not_home":
                            intercom_reason_code = "resident_not_home"
                            intercom_reason_label = f"No Answer at Intercom — {res_name or 'Resident'} Is Out"
                        else:
                            intercom_reason_code = "private_intercom"
                            intercom_reason_label = "No Answer at Intercom — Late Night"
                    elif dbell.get("doorbell_status") == "unavailable":
                        intercom_reason_code = "private_intercom"
                        intercom_reason_label = f"No Answer at Intercom — {res_name or 'Resident'} Unavailable"
                    elif is_high_bond and safe_min < 1320:
                        if persist_db:
                            record_node_unlock(session_id, target_node_id, unlock_type="day", current_day=curr_day, reason="resident_welcome")
                        return {"gated": False, "unlocked_by": "resident_welcome", "resident_name": res_name}
                else:
                    if is_high_bond and safe_min < 1320:
                        if persist_db:
                            record_node_unlock(session_id, target_node_id, unlock_type="day", current_day=curr_day, reason="resident_welcome")
                        return {"gated": False, "unlocked_by": "resident_welcome", "resident_name": res_name}

    # 7. Check Current Action Check Result (Breach / Persuasion Attempt & Escalating Complication)
    q_gate_eval = _get_active_quest_gate_context(session_id, node, fac_node, quest_gate_snapshot=q_gate_snap)
    is_active_quest_room = bool(q_gate_eval.get("is_active_quest_room"))
    quest_rush_dc = min(12, 6 + max(1, int(q_gate_eval.get("min_danger_tier") or 1))) if is_active_quest_room else 12
    state = db.get_world_node_state(session_id, target_node_id)
    failed_block_tag = f"{curr_day}_{time_block}"
    is_lock_jammed = False if is_active_quest_room else (state.get("failed_block") == failed_block_tag)

    _is_intercom_ring_only = (
        any(w in current_action_label for w in ("ring the intercom", "buzz", "ring the bell", "intercom"))
        and not any(w in current_action_label for w in ("sneak", "pick", "lockpick", "climb", "scale", "force", "break in", "bypass"))
    )
    if tier == "private" and _is_intercom_ring_only and (
        intercom_reason_code == "resident_not_home" or (not has_check and not action_check_tier)
    ):
        is_breach_action = False

    if is_breach_action:
        is_success_tier = action_check_tier in ("critical_success", "crit_success", "success", "partial_success")
        is_crit_fail_tier = action_check_tier in ("critical_failure", "crit_fail")
        if is_success_tier:
            if persist_db:
                record_node_unlock(session_id, target_node_id, unlock_type="day", current_day=curr_day, reason="skill_check")
                if is_nsfw_salon_target:
                    record_node_unlock(session_id, "loc_nsfw_club_facility", unlock_type="day", current_day=curr_day, reason="skill_check")
                    try:
                        from .seeding import reveal_hidden_club_facility
                        reveal_hidden_club_facility(session_id, "loc_nsfw_club_facility")
                    except Exception:
                        pass
            return {"gated": False, "unlocked_by": "skill_check"}
        else:
            # Action Failed: lock out for this time block and evict to nearest open public node (active quest rooms never jam)
            if persist_db and not is_active_quest_room:
                db.update_world_node_state(session_id, target_node_id, {"failed_block": failed_block_tag})
            from .pathfinding import resolve_safe_open_eviction_destination
            evict_nid, evict_loc = resolve_safe_open_eviction_destination(
                session_id,
                target_node_id,
                current_day=curr_day,
                current_minute=curr_min,
                scen_key=scen_key,
            )
            is_covert_sneak_attempt = any(
                k in current_action_label for k in ("sneak", "infiltrate", "slip", "creep", "climb", "scale")
            )
            patrol_confrontation = bool(is_crit_fail_tier or curfew_active or is_trespassing or is_covert_sneak_attempt)
            if persist_db and isinstance(session, dict):
                try:
                    from mechanics.stealth import break_stealth, get_session_stealth_state, set_session_stealth_state
                    break_stealth(session, reason="caught_at_restricted_gate", break_all=True)
                    st_gate = get_session_stealth_state(session)
                    lockouts = st_gate.setdefault("failed_stealth_lockouts", {})
                    lockouts[f"{target_node_id}:{failed_block_tag}"] = {
                        "node_id": target_node_id,
                        "time_block": failed_block_tag,
                        "day": curr_day,
                    }
                    set_session_stealth_state(session, st_gate)
                except Exception:
                    pass
            patrol_npc = None
            chosen = None
            if patrol_confrontation:
                from mechanics.social.epistemic_propagation import _is_watch_role
                from mechanics.world.presence_graph import is_deceased_or_arrested

                world_roster = db.get_world_roster(session_id, include_legacy_rosters=False) or []
                watch_cands: list[dict[str, Any]] = []
                authority_cands: list[dict[str, Any]] = []

                def _has_patrol_authority(cand: dict[str, Any]) -> bool:
                    cand_basic = _parse_basic_info_dict(cand)
                    r_txt = str(cand.get("role") or cand_basic.get("role") or "").lower()
                    c_txt = str(cand.get("club") or cand_basic.get("club") or "").lower()
                    return (
                        _is_watch_role(cand)
                        or any(k in r_txt for k in ("teacher", "staff", "guidance", "counselor", "principal", "vice principal", "prefect", "hall monitor", "discipline", "security", "guard", "officer"))
                        or any(k in c_txt for k in ("student council", "disciplinary"))
                    )

                for w in world_roster:
                    if not isinstance(w, dict) or not w.get("name"):
                        continue
                    if is_deceased_or_arrested(w) or str(w.get("staff_status") or "active").strip().lower() in ("dead", "deceased", "arrested", "wiped", "removed"):
                        continue
                    if _is_watch_role(w):
                        watch_cands.append(w)
                    elif not (curfew_active or is_trespassing) and _has_patrol_authority(w):
                        authority_cands.append(w)

                if not watch_cands and not authority_cands and not (curfew_active or is_trespassing):
                    roster = db.get_school_roster(session_id) or []
                    contacts = db.get_contacts(session_id) or []
                    for c in (contacts + roster):
                        if not isinstance(c, dict) or not c.get("name"):
                            continue
                        if is_deceased_or_arrested(c):
                            continue
                        if _has_patrol_authority(c):
                            authority_cands.append(c)

                all_real_cands = watch_cands or authority_cands
                if all_real_cands:
                    chosen = all_real_cands[0]
                    c_role = str(chosen.get("role") or "Campus Authority")
                    patrol_npc = {
                        "name": chosen.get("name"),
                        "role": f"{c_role} (Hall Monitor)" if "hall monitor" not in c_role.lower() else c_role,
                        "stage_role": "active_partner",
                        "attention_ring": "ring_1_primary",
                        "status_effects": ["Alerted"],
                    }
                    if persist_db:
                        from mechanics.social.epistemic_engine import detect_scene_witnesses

                        witness_rec = dict(chosen)
                        witness_rec["stage_role"] = "patrol_authority"
                        witness_rec["in_party"] = False
                        sess_dict = session if isinstance(session, dict) else {}
                        turn_num = int(sess_dict.get("turn_count") or len(sess_dict.get("history") or []) + 1)
                        detect_scene_witnesses(
                            int(session_id),
                            sess_dict,
                            present_npcs=[witness_rec],
                            nearby_npcs=[],
                            act_payload={
                                "intent": "stealth_covert",
                                "category": "crime",
                                "is_crime": True,
                                "is_secret_deed": True,
                                "force_spotted": True,
                                "location_node_id": target_node_id,
                                "summary": f"Caught attempting unauthorized breach of {display_name}",
                                "turn": turn_num,
                            },
                            rng=random,
                            turn=turn_num,
                        )
                else:
                    officer_pool = ["Officer Takahashi", "Officer Miller", "Officer Sato", "Officer Vance", "Officer Henderson"]
                    s_idx = int(hashlib.md5(f"patrol_{session_id}_{target_node_id}_{curr_day}".encode()).hexdigest(), 16) % len(officer_pool)
                    chosen_officer = officer_pool[s_idx]
                    patrol_npc = {
                        "name": chosen_officer,
                        "role": "Night Security Officer" if (curfew_active or is_trespassing) else "Campus Hall Monitor",
                        "stage_role": "active_partner",
                        "attention_ring": "ring_1_primary",
                        "status_effects": ["Alerted"],
                    }
            evict_note = f" You are forced back to {evict_loc}." if evict_loc else ""
            return {
                "gated": True,
                "node_id": evict_nid or target_node_id,
                "locked_out_node_id": target_node_id,
                "evicted_to_node_id": evict_nid,
                "evicted_to_location": evict_loc,
                "halt_location_override": evict_loc or None,
                "node_name": display_name,
                "reason_code": "breach_failed",
                "reason_label": "Lock Jammed / Caught Trespassing" if is_trespassing else "Lock Jammed / Caught Sneaking",
                "focal_point": f"Outside the Locked Entrance ({display_name})",
                "patrol_confrontation": patrol_confrontation,
                "patrol_npc": patrol_npc,
                "prompt_directive": (
                    f"[SYSTEM: BREACH FAILED - PATROL CONFRONTATION & EVICTION]\n"
                    f"The attempt to enter {display_name} failed! "
                    + (f"A patrolling authority figure ({patrol_npc['name']}) has spotted the player, demands an explanation, and forces them back to {evict_loc or 'the open hallway'}." if patrol_npc else f"The door mechanism jammed shut, preventing further forced entry during this time block.{evict_note}")
                ),
                "barrier_choices": [
                    Phase2Choice(f"[CHA] Make up a believable excuse to defuse suspicion", stat="CHA", requirement=11),
                    Phase2Choice(f"[AGI] Slip away into the corridor shadows before you are detained", stat="AGI", requirement=12),
                    Phase2Choice(f"Step away from {display_name}", stat="NONE", requirement=0, target_node_id=evict_nid, target_location=evict_loc, intent="movement")
                ] if patrol_confrontation else [
                    Phase2Choice(f"[CHA] Seek out someone with a key or permission for {display_name}", stat="CHA", requirement=10),
                    Phase2Choice(f"Turn back from {display_name}", stat="NONE", requirement=0, target_node_id=evict_nid, target_location=evict_loc, intent="movement")
                ]
            }

    # 8. Unresolved Barrier: Halt at Threshold
    sched_reason_code = access_info.get("schedule_reason_code") or ""
    sched_reason_label = access_info.get("schedule_reason_label") or ""

    if unbought_realty is not None:
        reason_code = "property_for_sale"
        reason_label = f"For Sale — {unbought_realty['price']}g"
    elif sched_reason_code in ("commercial_closed", "weekend_closed"):
        reason_code = sched_reason_code
        reason_label = sched_reason_label
    elif curfew_active or is_trespassing:
        reason_code = "curfew"
        reason_label = sched_reason_label or f"Curfew in Effect ({access_info['curfew_label']})"
    elif tier == "private":
        reason_code = intercom_reason_code or "private_intercom"
        reason_label = intercom_reason_label or "Private Residence Gate"
    elif is_nsfw_salon_target:
        reason_code = "speakeasy_restricted"
        reason_label = "Secret Society Speakeasy Door (Membership, Invite, or Audition Required)"
    else:
        reason_code = "restricted"
        reason_label = sched_reason_label or "Restricted Access"

    from .pathfinding import resolve_safe_open_eviction_destination
    retreat_nid, retreat_loc = resolve_safe_open_eviction_destination(
        session_id,
        target_node_id,
        current_day=curr_day,
        current_minute=curr_min,
        scen_key=scen_key,
    )

    barrier_choices = []
    if unbought_realty is not None:
        barrier_choices.append(Phase2Choice(
            f"[For Sale — {unbought_realty['price']}g] Purchase {unbought_realty['name']} Deed",
            stat="FREE",
            requirement=0,
            intent="property_purchase",
            property_id=unbought_realty["property_id"],
            price=int(unbought_realty["price"]),
            target_node_id=unbought_realty["bedroom_node_id"],
            target_location=f"{unbought_realty['zone_name']} ➔ {unbought_realty['name']} ➔ {unbought_realty['bedroom_name']}",
        ))
        if not is_lock_jammed:
            barrier_choices.append(Phase2Choice(
                f"[AGI] Sneak in or pick the lock to inspect {display_name}",
                stat="AGI",
                requirement=quest_rush_dc,
                target_node_id=target_node_id,
                target_location=display_name,
                intent="movement",
                is_stealth=True,
                stance="stealth",
            ))
        barrier_choices.append(Phase2Choice(
            f"Turn back from {display_name}",
            stat="NONE",
            requirement=0,
            target_node_id=retreat_nid,
            target_location=retreat_loc,
            intent="movement",
        ))
        return {
            "gated": True,
            "node_id": target_node_id,
            "facility_node_id": fac_node.get("node_id") if fac_node else target_node_id,
            "node_name": display_name,
            "reason_code": "property_for_sale",
            "reason_label": f"For Sale — {unbought_realty['price']}g",
            "is_trespassing": False,
            "focal_point": f"Outside {unbought_realty['name']} (For Sale — {unbought_realty['price']}g)",
            "prompt_directive": (
                f"[SYSTEM: PROPERTY FOR SALE — DOORSTEP THRESHOLD]\n"
                f"The player has arrived at the exterior doorstep of {unbought_realty['name']}, an unowned residential property currently listed For Sale (never quote raw gold integers in narrative prose).\n"
                f"- Place characters at the exterior entrance/doorstep of {unbought_realty['name']}.\n"
                f"- Depict the locked residential keypad/door and realty placard ({unbought_realty['description']}). Characters halt here unless purchasing the deed or bypassing the lock."
            ),
            "barrier_choices": barrier_choices,
        }
    if is_nsfw_salon_target:
        if not is_lock_jammed:
            barrier_choices.append(Phase2Choice(
                f"[AGI] Slip quietly through the cellar service grate into {display_name}",
                stat="AGI",
                requirement=quest_rush_dc,
                target_node_id=target_node_id,
                target_location=display_name,
                intent="movement",
                is_stealth=True,
                stance="stealth",
            ))
        barrier_choices.append(Phase2Choice(
            f"[CHA] Audition or charm the doorkeeper to gain entry to {display_name}",
            stat="CHA",
            requirement=quest_rush_dc,
            target_node_id=target_node_id,
            target_location=display_name,
            intent="movement",
        ))
        barrier_choices.append(Phase2Choice(
            f"Step away from {display_name}",
            stat="NONE",
            requirement=0,
            target_node_id=retreat_nid,
            target_location=retreat_loc,
            intent="movement",
        ))
    else:
        has_story_wp = False
        if session_id:
            try:
                with db.get_conn() as conn:
                    wp_row = conn.execute(
                        """SELECT qw.id FROM quest_waypoints qw
                           JOIN quests q ON q.session_id = qw.session_id AND q.quest_id = qw.quest_id
                           WHERE qw.session_id = ? AND qw.status = 'active'
                             AND q.status = 'Active' AND q.is_story_quest = 1
                             AND (LOWER(qw.target_node_id) = ? OR LOWER(qw.target_location) LIKE ?)
                           LIMIT 1""",
                        (session_id, str(target_node_id or "").lower(), f"%{display_name.lower()}%"),
                    ).fetchone()
                    has_story_wp = wp_row is not None
            except Exception:
                has_story_wp = False

        if not is_lock_jammed or has_story_wp or is_active_quest_room or sched_reason_code == "world_event_lockdown":
            infil_label = (
                f"[AGI] Infiltrate past the lockdown perimeter into {display_name}"
                if (sched_reason_code == "world_event_lockdown" or (is_lock_jammed and has_story_wp))
                else f"[AGI] Sneak in or pick the lock to enter {display_name}"
            )
            barrier_choices.append(Phase2Choice(
                infil_label,
                stat="AGI",
                requirement=quest_rush_dc,
                target_node_id=target_node_id,
                target_location=display_name,
                intent="movement",
                is_stealth=True,
                stance="stealth",
            ))
        if tier == "private":
            barrier_choices.append(Phase2Choice(
                f"[CHA] Ring the intercom and ask to be let into {display_name}",
                stat="CHA",
                requirement=min(10, quest_rush_dc),
                target_node_id=target_node_id,
                target_location=display_name,
                intent="movement",
            ))
        else:
            barrier_choices.append(Phase2Choice(
                f"[CHA] Talk your way past authority or seek permission for {display_name}",
                stat="CHA",
                requirement=min(11, quest_rush_dc),
                target_node_id=target_node_id,
                target_location=display_name,
                intent="movement",
            ))
        barrier_choices.append(Phase2Choice(
            f"Turn back from {display_name}",
            stat="NONE",
            requirement=0,
            target_node_id=retreat_nid,
            target_location=retreat_loc,
            intent="movement",
        ))

    trespass_note = (
        "\n- TRESPASSING WARNING: It is between 20:00 and 07:00. All students and teachers have gone home, "
        "the entire school area is restricted, and entering or staying on campus is considered TRESPASSING."
        if is_trespassing
        else ""
    )

    prompt_directive = (
        f"[SYSTEM: LOCKED / RESTRICTED THRESHOLD BARRIER]\n"
        f"The player has arrived at the threshold of {display_name}, but cannot enter because: {reason_label}.\n"
        f"- Location and micro-positioning: Place characters at 'Outside the Locked Entrance / Threshold of {display_name}'.\n"
        f"- Narration: Describe the locked doors, darkened interior, or warning signage. Characters MUST halt here until granted entry or bypassing the lock."
        f"{trespass_note}"
    )

    return {
        "gated": True,
        "node_id": target_node_id,
        "facility_node_id": fac_node.get("node_id") if fac_node else target_node_id,
        "node_name": display_name,
        "reason_code": reason_code,
        "reason_label": reason_label,
        "is_trespassing": is_trespassing,
        "focal_point": f"Outside the Locked Entrance ({reason_label})",
        "prompt_directive": prompt_directive,
        "barrier_choices": barrier_choices
    }


def record_turn_scene_residue(
    session_id: int,
    node_id: str,
    session: dict,
    result: dict,
    actions: list,
    unlocked_by: str = ""
) -> str | None:
    """
    Evaluates notable moments from this turn and updates a rolling 3-memory log (with priority pinning)
    in state_json for the current room node and its parent facility node.
    """
    if not session_id or not node_id:
        return None

    node = db.get_world_node(session_id, node_id)
    if not node:
        return None

    curr_day, curr_min, _ = db.get_session_time(session_id)
    new_memory_text = ""
    priority = 1

    # 1. Romantic / Intimate Climax (Priority 3)
    from mechanics.social.physical_state import is_erotic_intimate_contact
    _pre_ic = str(((session.get("physical_state") or {}).get("intimate_contact") or "")).lower()
    _upd_ic = str(((result.get("physical_updates") or {}).get("intimate_contact") or "")).lower()
    lead_partner = result.get("dialogue_partner") or (result.get("dialogue_partners") or [None])[0] or "a partner"

    if is_erotic_intimate_contact(_pre_ic) or is_erotic_intimate_contact(_upd_ic):
        new_memory_text = f"Day {curr_day}: Shared an intimate encounter with {lead_partner} here."
        priority = 3
    # 2. Clue Discovery / Quest Progress (Priority 2)
    elif result.get("quest_updates"):
        for qu in result["quest_updates"]:
            if isinstance(qu, dict) and qu.get("current_clues"):
                snip = str(qu["current_clues"]).strip()[:60]
                new_memory_text = f"Day {curr_day}: Discovered clue: {snip}."
                priority = 2
                break
        # Persist sparse prop delta if a room prop was searched or focused during clue discovery
        try:
            from mechanics.world.locations.seeds import get_node_props
            room_props = get_node_props(
                session_id, node_id,
                scenario_key=str((session or {}).get("scenario") or "high_school_drama"),
            )
            if room_props:
                focal_str = str(session.get("focal_point") or "").lower()
                act_labels = " ".join(
                    str(a.get("label") or a) if isinstance(a, dict) else str(a)
                    for a in (actions or [])
                ).lower()
                for rp in room_props:
                    rp_low = str(rp).strip().lower()
                    if rp_low and (rp_low in focal_str or rp_low in act_labels):
                        db.update_world_node_prop_delta(session_id, node_id, rp, {"is_searched": True})
        except Exception:
            pass
    # 3. Breach / Unlock Event (Priority 2)
    elif unlocked_by in ("skill_check", "key", "illicit_rendezvous"):
        node_name = node.get("name", "the entrance")
        new_memory_text = f"Day {curr_day}: Bypassed security to enter {node_name} ({unlocked_by})."
        priority = 2
    # 4. Hostile Combat Resolution (Priority 2)
    elif result.get("_combat_resolved_notice"):
        new_memory_text = f"Day {curr_day}: Fought off hostile confrontation here."
        priority = 2
    # 5. Memorable NPC Exchange / Bond Shift (Priority 1)
    elif result.get("npc_memories") and isinstance(result["npc_memories"], list) and result["npc_memories"]:
        first_mem = result["npc_memories"][0]
        summary = first_mem.get("summary") or first_mem.get("memory") or ""
        if summary:
            new_memory_text = f"Day {curr_day}: {summary[:70]}."
            priority = 1

    if not new_memory_text:
        return None

    # Load existing state
    state = db.get_world_node_state(session_id, node_id)
    log_list = list(state.get("scene_residue_log") or [])

    # Deduplicate and append
    is_secret_residue = bool(priority == 3 or unlocked_by in ("skill_check", "illicit_rendezvous"))
    participants: list[str] = ["player"]
    if priority == 3 and lead_partner and str(lead_partner).strip() and str(lead_partner).strip() != "a partner":
        participants.append(str(lead_partner).strip())

    filtered_log = [m for m in log_list if m.get("text") != new_memory_text]
    filtered_log.append({
        "day": curr_day,
        "minute": curr_min,
        "text": new_memory_text[:140],
        "priority": priority,
        "is_secret_residue": is_secret_residue,
        "participants": participants,
        "origin_node_id": str(node_id),
    })

    # Keep rolling 3 entries
    filtered_log = filtered_log[-3:]

    # Pin highest priority (tie-broken by index, latest wins)
    pinned_entry = max(filtered_log, key=lambda x: (x.get("priority", 1), filtered_log.index(x)))
    pinned_residue = pinned_entry["text"]

    updates = {
        "scene_residue": pinned_residue,
        "scene_residue_log": filtered_log,
        "last_visited_day": curr_day,
        "last_visited_minute": curr_min
    }

    db.update_world_node_state(session_id, node_id, updates)
    if node.get("parent_id") and node.get("node_type") == "ROOM":
        db.update_world_node_state(session_id, node["parent_id"], updates)

    return pinned_residue


def get_privacy_nudge_choice(
    session_id: int,
    current_node_id: str,
    partner_name: str,
    session: dict,
    actions: list = None
) -> Phase2Choice | None:
    """
    Edge Case 7: When in a public sub-location with an active dialogue partner during
    confidential, secret, or romantic tension, returns a choice to step into an adjacent secluded room or prop.
    """
    if not session_id or not partner_name:
        return None

    sess_dict = session if isinstance(session, dict) else (getattr(session, '__dict__', {}) if session else {})

    # Seclusion Guard: Stop appearing if already in a secluded prop or private/discreet location
    curr_focal = str(sess_dict.get('focal_point') or '').strip().lower()
    curr_loc_str = str(sess_dict.get('current_location') or '').strip()
    curr_loc_lower = curr_loc_str.lower()
    secluded_keywords = (
        'aisle', 'alcove', 'corner', 'behind', 'booth', 'closet', 'balcony',
        'stairwell', 'under', 'terrace', 'shed', 'secluded', 'private', 'trellis'
    )
    if curr_focal and any(k in curr_focal for k in secluded_keywords):
        return None
    if any(k in curr_loc_lower for k in ('balcony', 'booth', 'alcove', 'shed', 'closet', 'terrace', 'secluded', 'stairwell', 'trellis')):
        return None

    eff_nid = str(current_node_id or sess_dict.get('current_node_id') or '').strip()
    if not eff_nid and curr_loc_str:
        eff_nid = db.resolve_node_id_from_location(session_id, curr_loc_str) or ''

    curr_node = db.get_world_node(session_id, eff_nid) if eff_nid else None
    if not curr_node and eff_nid:
        resolved_id = db.resolve_node_id_from_location(session_id, eff_nid)
        if resolved_id:
            curr_node = db.get_world_node(session_id, resolved_id)

    if not curr_node:
        return None

    try:
        from mechanics.combat.enemy_profiles import is_anomalous_danger_zone
        c_min_nudge = int(sess_dict.get("current_minute") or 720)
        s_key_nudge = str(sess_dict.get("scenario") or "high_school_drama")
        if is_anomalous_danger_zone(
            location_name=curr_loc_str or str(curr_node.get("name") or ""),
            location_id=str(curr_node.get("node_id") or eff_nid or ""),
            current_minute=c_min_nudge,
            session_id=int(session_id),
            scen_key=s_key_nudge,
            turn_count=None,
        ):
            return None
    except Exception:
        pass

    priv_lvl = str(curr_node.get('privacy_level') or 'public').lower()
    if priv_lvl in ('semi_private', 'private', 'restricted') or bool(curr_node.get('is_discreet')) or priv_lvl != 'public':
        return None

    parent_id = curr_node.get('parent_id')
    if not parent_id:
        return None

    # Anti-badgering deflection guard: suppress if partner deflected within last 180 min
    p_key = re.sub(r'[^a-z0-9_]+', '_', partner_name.lower().strip())
    defl = (sess_dict.get('extra') or {}).get(f'privacy_deflected_{p_key}')
    if defl and isinstance(defl, (list, tuple)) and len(defl) == 2:
        d_day, d_min = defl
        c_day = int(sess_dict.get('current_day') or 1)
        c_min = int(sess_dict.get('current_minute') or 480)
        if d_day == c_day and (c_min - d_min) < 180:
            return None

    # Check partner bond / context
    contacts = db.get_contacts(session_id) or []
    contact = next((c for c in contacts if str(c.get('name') or '').strip().lower() == partner_name.strip().lower()), None)
    score = int(contact.get('relationship_score', 0) or 0) if contact else 0
    track = str(contact.get('track', '')).lower() if contact else ''
    is_romantic = (score >= 30) or (track == 'romantic')

    action_text = ' '.join(str(a.get('label', '') if isinstance(a, dict) else a) for a in (actions or [])).lower()
    is_secret_context = any(w in action_text for w in ('confess', 'kiss', 'whisper', 'private', 'alone', 'secret', 'hide', 'intimate'))

    if not (is_romantic or is_secret_context):
        return None

    # Affinity-scaled DC curve (Stranger: DC 12 -> Acquaintance: 10-11 -> Friend: 8-9 -> Romantic/Dating: 5-7)
    score_discount = max(0, min(6, score // 25))
    track_bonus = 2 if track == 'romantic' else (1 if score >= 60 else 0)
    home_dc_mod = 0
    try:
        from .residences import get_player_owned_or_starter_property_for_node
        from .realty_catalog import resolve_realty_entry
        owned_here = get_player_owned_or_starter_property_for_node(session_id, str(parent_id or curr_node['node_id']), session=sess_dict)
        if owned_here and owned_here.get("catalog_entry"):
            home_dc_mod = int(owned_here["catalog_entry"].get("cha_invite_dc_mod") or 0)
        else:
            prim_prop = db.get_primary_property(session_id)
            if prim_prop and not prim_prop.get("is_starter"):
                p_cat = resolve_realty_entry(str(prim_prop.get("property_id") or ""), session_or_id=sess_dict)
                if p_cat:
                    home_dc_mod = int(p_cat.get("cha_invite_dc_mod") or 0)
    except Exception:
        home_dc_mod = 0
    base_dc = max(5, min(14, 12 - score_discount - track_bonus))
    req_dc = max(3, min(14, base_dc + home_dc_mod))

    scen_key = str(sess_dict.get('scenario') or 'high_school_drama')
    from mechanics.world.locations.hierarchy import parse_tiered_location, format_tiered_location_string
    pz, pp, _ = parse_tiered_location(curr_loc_str, scen_key, session_id=session_id)

    # 1. Prefer adjacent secluded sibling room under the same facility for full room transition
    all_nodes = db.get_session_world_nodes(session_id)
    curr_nid = str(curr_node.get('node_id') or '')
    siblings = [
        n for n in all_nodes
        if n.get('parent_id') == parent_id
        and n.get('node_id') != curr_node['node_id']
        and n.get('node_type') == 'ROOM'
        and (n.get('privacy_level') in ('semi_private', 'private', 'restricted') or bool(n.get('is_discreet')))
    ]

    affiliated_siblings = []
    other_siblings = []
    for n in siblings:
        nid = str(n.get('node_id') or '')
        sj_raw = n.get('state_json')
        sj_dict = json.loads(sj_raw) if isinstance(sj_raw, str) and sj_raw.strip().startswith('{') else (sj_raw if isinstance(sj_raw, dict) else {})
        is_child = bool(getattr(sj_dict, 'get', lambda _k: None)('parent_sub_id') == curr_nid)
        if nid.startswith(curr_nid + '_') or is_child:
            affiliated_siblings.append(n)
        else:
            other_siblings.append(n)

    def _sibling_priority(n: dict) -> tuple:
        nid = str(n.get('node_id') or '')
        is_affiliated = nid.startswith(curr_nid + '_')
        name_low = str(n.get('name') or '').lower()
        has_secluded_name = any(k in name_low for k in ('balcony', 'terrace', 'booth', 'alcove', 'shed', 'nook', 'private', 'corner'))
        sj_raw = n.get('state_json')
        sj_dict = json.loads(sj_raw) if isinstance(sj_raw, str) and sj_raw.strip().startswith('{') else (sj_raw if isinstance(sj_raw, dict) else {})
        is_child = bool(getattr(sj_dict, 'get', lambda _k: None)('parent_sub_id') == curr_nid)
        is_discreet = bool(n.get('is_discreet')) or bool(getattr(sj_dict, 'get', lambda _k: None)('is_discreet'))
        return (0 if (is_affiliated or is_child) else 1, 0 if is_discreet else 1, 0 if has_secluded_name else 1)

    def _sibling_priority_stable(n: dict) -> tuple:
        pri = _sibling_priority(n)
        try:
            idx = all_nodes.index(n)
        except Exception:
            idx = 999
        return (pri[0], pri[1], pri[2], idx)

    if affiliated_siblings:
        affiliated_siblings.sort(key=_sibling_priority_stable)
        chosen_sub = affiliated_siblings[0]
        dest_loc = format_tiered_location_string(pz, pp, chosen_sub['name'])
        return Phase2Choice(
            f'Step into {chosen_sub["name"]} with {partner_name} for privacy',
            stat='CHA',
            requirement=req_dc,
            mp_cost=0,
            intent='social_invite',
            sub_intent='privacy_nudge',
            target_npc=partner_name,
            target_node_id=chosen_sub['node_id'],
            target_location=dest_loc,
            _privacy_nudge=True,
            _band=2,
        )

    # 2. Check for a secluded prop within the current room
    try:
        from .seeds import get_node_props
        room_props = get_node_props(session_id, curr_node['node_id'], scenario_key=scen_key)
        for pr in room_props:
            pr_low = pr.lower()
            if pr_low != curr_focal and any(k in pr_low for k in secluded_keywords):
                dest_loc = format_tiered_location_string(pz, curr_node.get('name') or pp, pr)
                return Phase2Choice(
                    f'Step into {pr} with {partner_name} for privacy',
                    stat='CHA',
                    requirement=req_dc,
                    mp_cost=0,
                    intent='social_invite',
                    sub_intent='privacy_nudge',
                    target_npc=partner_name,
                    target_node_id=curr_node['node_id'],
                    target_location=dest_loc,
                    focal_point=pr,
                    _privacy_nudge=True,
                    _band=2,
                )
    except Exception:
        pass

    # 3. Fall back to other secluded sibling rooms under the same facility
    if other_siblings:
        other_siblings.sort(key=_sibling_priority_stable)
        chosen_sub = other_siblings[0]
        dest_loc = format_tiered_location_string(pz, pp, chosen_sub['name'])
        return Phase2Choice(
            f'Step into {chosen_sub["name"]} with {partner_name} for privacy',
            stat='CHA',
            requirement=req_dc,
            mp_cost=0,
            intent='social_invite',
            sub_intent='privacy_nudge',
            target_npc=partner_name,
            target_node_id=chosen_sub['node_id'],
            target_location=dest_loc,
            _privacy_nudge=True,
            _band=2,
        )

    return None


CIVIC_POLICE_ROLE_TOKENS = frozenset({
    "police", "patrol", "officer", "detective", "sergeant", "sheriff", "koban", "constable"
})
ACADEMIC_FACULTY_TOKENS = frozenset({
    "teacher", "faculty", "staff", "nurse", "librarian", "principal", "counselor",
    "custodian", "janitor", "professor", "instructor"
})


def can_npc_stage_at_facility(
    npc_or_role: dict | str,
    location: str,
    session: dict | None = None,
    current_minute: int = 480,
    scen_key: str = ""
) -> bool:
    """Verifies whether an NPC or role is permitted to be staged at a facility at a given time.

    During weekday academic hours (07:30 to 16:30), interior academic rooms (classrooms, libraries,
    homerooms, infirmaries) are restricted to students and school staff, preventing municipal police
    or off-campus civic officials from spawning inside study spaces without an active emergency.
    """
    if not location or not npc_or_role:
        return True
    loc_low = str(location).lower()
    is_academic_loc = any(k in loc_low for k in ("school", "academy", "classroom", "homeroom", "stacks", "library", "infirmary", "staff room"))
    safe_min = int(current_minute or 480) % 1440
    is_school_hours = 450 <= safe_min < 990  # 07:30 to 16:30

    if is_academic_loc and is_school_hours:
        role = (npc_or_role.get("role") or (npc_or_role.get("basic_info") or {}).get("role") or "") if isinstance(npc_or_role, dict) else str(npc_or_role)
        role_low = role.lower()
        standing = str((npc_or_role.get("grade") or (npc_or_role.get("basic_info") or {}).get("grade") or "") if isinstance(npc_or_role, dict) else "").lower()

        # Campus security and school resource officers permitted
        if any(re.search(rf"\b{re.escape(t)}\b", role_low) for t in ("school", "campus", "resource")):
            return True

        # Civic town police officers excluded from interior school facilities during class hours
        if any(re.search(rf"\b{re.escape(t)}\b", role_low) for t in CIVIC_POLICE_ROLE_TOKENS):
            return False

        # Validate student or faculty standing
        if standing in ("faculty", "staff", "freshman", "sophomore", "junior", "senior"):
            return True
        if any(re.search(rf"\b{re.escape(t)}\b", role_low) for t in ACADEMIC_FACULTY_TOKENS) or "student" in role_low or "classmate" in role_low:
            return True
    return True
