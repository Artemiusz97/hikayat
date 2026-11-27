from __future__ import annotations
"""Mobile vessel docking, FTL jump plotting, and autopilot recall operations."""

from typing import Any

import db

from .hierarchy import (
    _load_nodes_map,
    check_realm_comms_available,
    get_node_realm_id_in_memory,
    get_realm_rules,
    parse_node_state_json,
)

MAX_DOCK_HISTORY = 25


def _rewire_vessel_dock(
    c: Any,
    session_id: int,
    vessel_realm_id: str,
    target_realm_id: str,
    target_dock_node_id: str,
    turn_number: int,
) -> dict[str, Any]:
    """Updates mobile vessel shuttle_route edges and records dock_history for multi-jump rollback."""
    v_row = db.get_world_node_tx(session_id, vessel_realm_id, conn=c)
    if not v_row:
        raise ValueError(f"Vessel realm '{vessel_realm_id}' not found.")
    td_row = db.get_world_node_tx(session_id, target_dock_node_id, conn=c)
    if not td_row:
        raise ValueError(f"Target dock node '{target_dock_node_id}' not found in world_nodes.")
    v_state = parse_node_state_json(v_row)
    airlock_id = str(v_state.get("airlock_node_id") or "").strip()
    prev_realm_id = str(v_state.get("docked_realm_id") or "").strip()
    prev_dock_id = str(v_state.get("docked_node_id") or "").strip()

    if airlock_id:
        db.delete_world_edges_by_node_type(session_id, "shuttle_route", airlock_id, conn=c)
        for src, dst in ((airlock_id, target_dock_node_id), (target_dock_node_id, airlock_id)):
            db.upsert_world_edge_tx(
                session_id,
                src,
                dst,
                travel_minutes=5,
                edge_type="shuttle_route",
                is_bidirectional=1,
                is_locked=0,
                update_on_conflict=True,
                conn=c,
            )
        a_row = db.get_world_node_tx(session_id, airlock_id, conn=c)
        if a_row:
            a_st = parse_node_state_json(a_row)
            t_realm_row = db.get_world_node_tx(session_id, target_realm_id, conn=c)
            t_realm_name = str(t_realm_row["name"]) if t_realm_row else target_realm_id
            a_portals = dict(a_st.get("portals") or {})
            if prev_dock_id and prev_dock_id != target_dock_node_id:
                a_portals.pop(prev_dock_id, None)
            a_portals[target_dock_node_id] = {
                "target_realm_id": target_realm_id,
                "label": f"🚀 Disembark to {t_realm_name}",
                "icon": "🚀",
                "is_hidden_portal": False,
            }
            a_st["portals"] = a_portals
            db.update_world_node_state_json(session_id, airlock_id, a_st, conn=c)

        if prev_dock_id and prev_dock_id != target_dock_node_id:
            pd_row = db.get_world_node_tx(session_id, prev_dock_id, conn=c)
            if pd_row:
                pd_st = parse_node_state_json(pd_row)
                pd_portals = dict(pd_st.get("portals") or {})
                if airlock_id in pd_portals:
                    pd_portals.pop(airlock_id, None)
                    pd_st["portals"] = pd_portals
                    db.update_world_node_state_json(session_id, prev_dock_id, pd_st, conn=c)

        td_st = parse_node_state_json(td_row)
        td_portals = dict(td_st.get("portals") or {})
        td_portals[airlock_id] = {
            "target_realm_id": vessel_realm_id,
            "label": f"🚀 Board {v_row['name']}",
            "icon": "🚀",
            "is_hidden_portal": False,
        }
        td_st["portals"] = td_portals
        db.update_world_node_state_json(session_id, target_dock_node_id, td_st, conn=c)

    if int(turn_number or 0) > 0 and prev_realm_id and prev_dock_id and (
        prev_realm_id != target_realm_id or prev_dock_id != target_dock_node_id
    ):
        hist = [dict(h) for h in (v_state.get("dock_history") or []) if isinstance(h, dict)]
        hist.append({
            "turn": int(turn_number),
            "prev_realm_id": prev_realm_id,
            "prev_node_id": prev_dock_id,
            "new_realm_id": target_realm_id,
            "new_node_id": target_dock_node_id,
        })
        v_state["dock_history"] = hist[-MAX_DOCK_HISTORY:]

    v_state["docked_realm_id_prev"] = prev_realm_id
    v_state["docked_node_id_prev"] = prev_dock_id
    v_state["docked_realm_id"] = target_realm_id
    v_state["docked_node_id"] = target_dock_node_id
    v_state["docked_turn"] = int(turn_number or 0)
    db.update_world_node_state_json(session_id, vessel_realm_id, v_state, conn=c)
    return {
        "vessel_realm_id": vessel_realm_id,
        "vessel_name": str(v_row["name"]),
        "docked_realm_id": target_realm_id,
        "docked_node_id": target_dock_node_id,
        "airlock_node_id": airlock_id,
    }


def _undock_vessel_cleanly(
    c: Any,
    session_id: int,
    vessel_realm_id: str,
    kept_hist: list[dict[str, Any]],
) -> None:
    """Clears dangling vessel shuttle routes & portal metadata when no valid previous dock exists."""
    v_row = db.get_world_node_tx(session_id, vessel_realm_id, conn=c)
    if not v_row:
        return
    vst = parse_node_state_json(v_row)
    airlock_id = str(vst.get("airlock_node_id") or "").strip()
    old_dock_id = str(vst.get("docked_node_id") or "").strip()
    if airlock_id:
        db.delete_world_edges_by_node_type(session_id, "shuttle_route", airlock_id, conn=c)
        a_row = db.get_world_node_tx(session_id, airlock_id, conn=c)
        if a_row:
            a_st = parse_node_state_json(a_row)
            a_portals = dict(a_st.get("portals") or {})
            if old_dock_id and old_dock_id in a_portals:
                a_portals.pop(old_dock_id, None)
                a_st["portals"] = a_portals
                db.update_world_node_state_json(session_id, airlock_id, a_st, conn=c)
        if old_dock_id:
            od_row = db.get_world_node_tx(session_id, old_dock_id, conn=c)
            if od_row:
                od_st = parse_node_state_json(od_row)
                od_portals = dict(od_st.get("portals") or {})
                if airlock_id in od_portals:
                    od_portals.pop(airlock_id, None)
                    od_st["portals"] = od_portals
                    db.update_world_node_state_json(session_id, old_dock_id, od_st, conn=c)

    vst["dock_history"] = kept_hist
    if kept_hist:
        last_kept = kept_hist[-1]
        vst["docked_turn"] = int(last_kept.get("turn") or 0)
        vst["docked_realm_id_prev"] = str(last_kept.get("prev_realm_id") or "")
        vst["docked_node_id_prev"] = str(last_kept.get("prev_node_id") or "")
    else:
        vst["docked_turn"] = 0
        vst["docked_realm_id_prev"] = ""
        vst["docked_node_id_prev"] = ""
    vst["docked_realm_id"] = ""
    vst["docked_node_id"] = ""
    db.update_world_node_state_json(session_id, vessel_realm_id, vst, conn=c)


def _load_nodes_map_with_conn(session_id: int, conn: Any = None) -> dict[str, dict[str, Any]]:
    if conn is not None:
        rows = db.get_session_world_nodes_tx(session_id, conn=conn) or []
        return {str(r["node_id"]): dict(r) for r in rows if r.get("node_id")}
    return _load_nodes_map(session_id)


def execute_starship_jump(
    session_id: int,
    vessel_realm_id: str,
    target_realm_id: str,
    turn_number: int = 1,
    *,
    persist_db: bool = True,
    conn: Any = None,
) -> dict[str, Any]:
    """Plots a mobile vessel FTL jump to target_realm_id and rewires its airlock shuttle_route."""
    nodes_by_id = _load_nodes_map_with_conn(session_id, conn=conn)
    v_node = nodes_by_id.get(vessel_realm_id)
    t_node = nodes_by_id.get(target_realm_id)
    if not v_node or not t_node:
        return {"success": False, "reason": "Target star system or vessel not found."}
    v_rules = get_realm_rules(v_node)
    t_rules = get_realm_rules(t_node)
    if not v_rules.get("is_mobile_vessel"):
        return {"success": False, "reason": "Current realm is not a mobile vessel."}
    if t_rules.get("is_hidden"):
        return {"success": False, "reason": "Target star system has not been charted yet."}
    dock_nid = str(t_rules.get("dock_node_id") or "").strip()
    if not dock_nid or dock_nid not in nodes_by_id:
        return {"success": False, "reason": "Target realm has no valid docking coordinates."}
    if (
        str(v_rules.get("docked_realm_id") or "") == target_realm_id
        and str(v_rules.get("docked_node_id") or "") == dock_nid
    ):
        return {
            "success": True,
            "already_docked": True,
            "vessel_realm_id": vessel_realm_id,
            "vessel_name": str(v_node.get("name") or vessel_realm_id),
            "docked_realm_id": target_realm_id,
            "target_realm_name": str(t_node.get("name") or target_realm_id),
            "docked_node_id": dock_nid,
            "airlock_node_id": str(v_rules.get("airlock_node_id") or ""),
            "travel_minutes": 0,
        }

    if not persist_db:
        return {
            "success": True,
            "vessel_realm_id": vessel_realm_id,
            "vessel_name": str(v_node.get("name") or vessel_realm_id),
            "docked_realm_id": target_realm_id,
            "target_realm_name": str(t_node.get("name") or target_realm_id),
            "docked_node_id": dock_nid,
            "travel_minutes": 45,
        }

    eff_turn = max(1, int(turn_number or 1))
    if conn is not None:
        res = _rewire_vessel_dock(conn, session_id, vessel_realm_id, target_realm_id, dock_nid, eff_turn)
    else:
        with db.UnitOfWork() as uow_conn:
            res = _rewire_vessel_dock(uow_conn, session_id, vessel_realm_id, target_realm_id, dock_nid, eff_turn)
    res.update({
        "success": True,
        "target_realm_name": str(t_node.get("name") or target_realm_id),
        "travel_minutes": 45,
    })
    return res


def execute_recall_starship(
    session_id: int,
    vessel_realm_id: str,
    current_node_id: str,
    turn_number: int = 1,
    *,
    persist_db: bool = True,
    conn: Any = None,
) -> dict[str, Any]:
    """Recalls a mobile vessel via autopilot to the current realm's dock (blocked when comms_isolated)."""
    comms = check_realm_comms_available(session_id, current_node_id)
    if not comms.get("available"):
        return {"success": False, "comms_isolated": True, "reason": comms.get("reason", "No Signal — Isolated Realm.")}
    nodes_by_id = _load_nodes_map_with_conn(session_id, conn=conn)
    curr_realm_id = get_node_realm_id_in_memory(current_node_id, nodes_by_id)
    curr_realm = nodes_by_id.get(curr_realm_id)
    curr_rules = get_realm_rules(curr_realm)
    dock_nid = str(curr_rules.get("dock_node_id") or "").strip()
    if not dock_nid or dock_nid not in nodes_by_id:
        return {"success": False, "reason": "Current location has no orbital/spaceport dock."}
    v_node = nodes_by_id.get(vessel_realm_id)
    if not v_node or not get_realm_rules(v_node).get("is_mobile_vessel"):
        return {"success": False, "reason": "Vessel realm not found."}
    v_rules = get_realm_rules(v_node)
    v_name = str(v_node.get("name") or vessel_realm_id)
    if str(v_rules.get("docked_realm_id") or "") == curr_realm_id:
        return {"success": False, "already_docked": True, "reason": f"{v_name} is already docked here."}

    if not persist_db:
        return {
            "success": True,
            "vessel_realm_id": vessel_realm_id,
            "vessel_name": v_name,
            "docked_realm_id": curr_realm_id,
            "target_realm_name": str((curr_realm or {}).get("name") or curr_realm_id),
            "docked_node_id": dock_nid,
            "travel_minutes": 30,
        }

    eff_turn = max(1, int(turn_number or 1))
    if conn is not None:
        res = _rewire_vessel_dock(conn, session_id, vessel_realm_id, curr_realm_id, dock_nid, eff_turn)
    else:
        with db.UnitOfWork() as uow_conn:
            res = _rewire_vessel_dock(uow_conn, session_id, vessel_realm_id, curr_realm_id, dock_nid, eff_turn)
    res.update({
        "success": True,
        "target_realm_name": str((curr_realm or {}).get("name") or curr_realm_id),
        "travel_minutes": 30,
    })
    return res
