from __future__ import annotations
"""Lightweight HUD & Atlas realm summary builder (zero N+1 SQL scans)."""

from typing import Any, Mapping, Optional

import db

from .hierarchy import (
    format_tiered_location_in_memory,
    get_node_realm_in_memory,
    get_portal_edges_in_memory,
    get_primary_realm_in_memory,
    get_realm_rules,
    is_at_access_point_in_memory,
)


def build_session_realm_summary(
    session_id: int,
    current_node_id: Optional[str] = None,
    *,
    nodes: Optional[list[dict[str, Any]]] = None,
    edges: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Builds lightweight HUD & Atlas realm summary for a session."""
    if not session_id:
        return {
            "current_realm": None,
            "show_realm_badge": False,
            "visible_realm_count": 0,
            "realm_gateways": [],
        }
    all_nodes = nodes if nodes is not None else (db.get_session_world_nodes(session_id) or [])
    nodes_by_id = {str(n["node_id"]): dict(n) for n in all_nodes if isinstance(n, Mapping) and n.get("node_id")}
    nid = str(current_node_id or "").strip()
    curr_realm = get_node_realm_in_memory(nid, nodes_by_id) if nid else None
    if curr_realm is None:
        curr_realm = get_primary_realm_in_memory(nodes_by_id)

    realm_nodes = [dict(n) for n in all_nodes if str(n.get("node_type") or "").upper() == "REALM"]
    visible_realms = [r for r in realm_nodes if not get_realm_rules(r).get("is_hidden")]
    curr_rules = get_realm_rules(curr_realm)
    is_primary = bool(curr_rules.get("is_primary_realm", True)) if curr_realm else True
    show_badge = bool(curr_realm) and (len(visible_realms) >= 2 or not is_primary)

    curr_realm_id = str(curr_realm.get("node_id") or "") if curr_realm else ""
    curr_realm_payload = None
    if curr_realm:
        icon_val = str(curr_rules.get("portal_icon") or ("🚀" if curr_rules.get("is_mobile_vessel") else "🌐"))
        docked_rid = str(curr_rules.get("docked_realm_id") or "")
        docked_r_node = nodes_by_id.get(docked_rid) if docked_rid else None
        docked_r_name = str(docked_r_node.get("name") or docked_rid) if (docked_rid and docked_r_node) else docked_rid
        curr_realm_payload = {
            "realm_id": curr_realm_id,
            "name": str(curr_realm.get("name") or curr_realm_id),
            "realm_kind": str(curr_rules.get("realm_kind") or "world"),
            "is_primary_realm": is_primary,
            "comms_isolated": bool(curr_rules.get("comms_isolated")),
            "time_scale": float(curr_rules.get("time_scale", 1.0)),
            "has_local_safe_hub": bool(curr_rules.get("has_local_safe_hub", True)),
            "exit_mode": str(curr_rules.get("exit_mode") or "open"),
            "is_ephemeral": bool(curr_rules.get("is_ephemeral")),
            "is_mobile_vessel": bool(curr_rules.get("is_mobile_vessel")),
            "docked_realm_id": docked_rid,
            "docked_realm_name": docked_r_name,
            "docked_node_id": str(curr_rules.get("docked_node_id") or ""),
            "pacified": bool(curr_rules.get("pacified")),
            "icon": icon_val,
            "portal_icon": icon_val,
        }

    all_edges = edges if edges is not None else (db.get_session_world_edges(session_id) or [])
    raw_portals = (
        get_portal_edges_in_memory(nodes_by_id, all_edges, from_realm_id=curr_realm_id, include_hidden=False)
        if curr_realm_id
        else []
    )
    gateways: list[dict[str, Any]] = []
    for p in raw_portals:
        ap_nid = p["from_node_id"]
        can_cross_now = is_at_access_point_in_memory(nid, ap_nid, nodes_by_id)
        if curr_rules.get("exit_mode") == "lockdown_until_cleared" and not curr_rules.get("pacified"):
            can_cross_now = False
        ap_loc = format_tiered_location_in_memory(ap_nid, nodes_by_id)
        gateways.append({
            "access_point_node_id": ap_nid,
            "access_point_name": p["from_node_name"],
            "access_point_location": ap_loc,
            "target_node_id": p["to_node_id"],
            "target_node_name": p["to_node_name"],
            "target_realm_id": p["target_realm_id"],
            "target_realm_name": p["target_realm_name"],
            "edge_type": p["edge_type"],
            "icon": p["icon"],
            "label": p["label"] or f"Cross into {p['target_realm_name']}",
            "is_locked": p["is_locked"],
            "can_cross_now": can_cross_now,
            "action_kind": "portal_cross",
            "off_realm_objective_count": 0,
        })

    if curr_realm_id and curr_rules.get("is_mobile_vessel") and curr_rules.get("bridge_node_id"):
        bridge_nid = str(curr_rules["bridge_node_id"])
        bridge_loc = format_tiered_location_in_memory(bridge_nid, nodes_by_id)
        docked_rid = str(curr_rules.get("docked_realm_id") or "")
        at_bridge = is_at_access_point_in_memory(nid, bridge_nid, nodes_by_id)
        for r_node in visible_realms:
            r_id = str(r_node["node_id"])
            if r_id in (curr_realm_id, docked_rid):
                continue
            r_rules = get_realm_rules(r_node)
            dock_nid = str(r_rules.get("dock_node_id") or "")
            if not dock_nid or dock_nid not in nodes_by_id:
                continue
            gateways.append({
                "access_point_node_id": bridge_nid,
                "access_point_name": str((nodes_by_id.get(bridge_nid) or {}).get("name") or "Ship Bridge"),
                "access_point_location": bridge_loc,
                "target_node_id": dock_nid,
                "target_node_name": str((nodes_by_id.get(dock_nid) or {}).get("name") or dock_nid),
                "target_realm_id": r_id,
                "target_realm_name": str(r_node.get("name") or r_id),
                "vessel_realm_id": curr_realm_id,
                "edge_type": "ftl_jump",
                "icon": "🚀",
                "label": f"Jump to {r_node.get('name') or r_id}",
                "is_locked": False,
                "can_cross_now": at_bridge,
                "action_kind": "starship_jump",
                "off_realm_objective_count": 0,
            })

    if curr_realm_id and curr_rules.get("dock_node_id") and not curr_rules.get("comms_isolated"):
        dock_nid = str(curr_rules["dock_node_id"])
        dock_loc = format_tiered_location_in_memory(dock_nid, nodes_by_id)
        at_dock = is_at_access_point_in_memory(nid, dock_nid, nodes_by_id)
        for r_node in visible_realms:
            v_id = str(r_node["node_id"])
            if v_id == curr_realm_id:
                continue
            v_rules = get_realm_rules(r_node)
            if not v_rules.get("is_mobile_vessel"):
                continue
            if str(v_rules.get("docked_realm_id") or "") == curr_realm_id:
                continue
            gateways.append({
                "access_point_node_id": dock_nid,
                "access_point_name": str((nodes_by_id.get(dock_nid) or {}).get("name") or "Docking Pad"),
                "access_point_location": dock_loc,
                "target_node_id": dock_nid,
                "target_node_name": str(r_node.get("name") or v_id),
                "target_realm_id": curr_realm_id,
                "target_realm_name": str(r_node.get("name") or v_id),
                "vessel_realm_id": v_id,
                "edge_type": "shuttle_route",
                "icon": "🚀",
                "label": f"Recall {r_node.get('name') or v_id}",
                "is_locked": False,
                "can_cross_now": at_dock,
                "action_kind": "recall_starship",
                "off_realm_objective_count": 0,
            })

    return {
        "current_realm": curr_realm_payload,
        "show_realm_badge": show_badge,
        "visible_realm_count": len(visible_realms),
        "realm_gateways": gateways,
    }
