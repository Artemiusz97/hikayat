from __future__ import annotations
"""Deterministic Phase2Choice builders for portal crossings and mobile vessels."""

from typing import Any

import db

from .hierarchy import (
    _load_nodes_map,
    get_node_realm_id_in_memory,
    get_portal_edges_in_memory,
    get_realm_rules,
    is_at_access_point_in_memory,
)


def get_portal_choices_at_node(session_id: int, curr_node_id: str) -> list[dict[str, Any]]:
    """
    Builds deterministic Phase2Choice dictionaries when standing at a Realm Access Point,
    a mobile vessel Bridge, or a Spaceport dock capable of recalling a mobile vessel.
    """
    if not session_id or not curr_node_id:
        return []
    nodes_by_id = _load_nodes_map(session_id)
    if curr_node_id not in nodes_by_id:
        return []
    curr_realm_id = get_node_realm_id_in_memory(curr_node_id, nodes_by_id)
    if not curr_realm_id:
        return []
    curr_realm_node = nodes_by_id.get(curr_realm_id)
    curr_rules = get_realm_rules(curr_realm_node)
    edges = db.get_session_world_edges(session_id) or []

    choices: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()

    # 1. Direct outgoing portal edges from curr_node_id (or its parent FACILITY if standing in an AP facility)
    portals = get_portal_edges_in_memory(nodes_by_id, edges, from_realm_id=curr_realm_id, include_hidden=False)
    for p in portals:
        if not is_at_access_point_in_memory(curr_node_id, p["from_node_id"], nodes_by_id):
            continue
        dst_nid = p["to_node_id"]
        dst_realm = p["target_realm_id"]
        key = ("portal_cross", dst_nid, dst_realm)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        icon = p["icon"]
        r_name = p["target_realm_name"]
        label = p["label"] or f"{icon} Cross into {r_name}"
        if p["is_locked"]:
            label = f"{label} [Locked]"
        choices.append({
            "label": label,
            "stat": str(p.get("skill_check_type") or "NONE").upper() if p["is_locked"] and p.get("skill_check_type") else "NONE",
            "requirement": int(p.get("skill_check_dc") or 0) if p["is_locked"] and p.get("skill_check_type") else 0,
            "mp_cost": 0,
            "intent": "movement",
            "sub_intent": "portal_cross",
            "target_node_id": dst_nid,
            "target_realm_id": dst_realm,
            "portal_edge_type": p["edge_type"],
            "is_phase2_choice": True,
            "_priority_slot": True,
        })

    # 2. Mobile vessel Bridge -> FTL Jump choices to unlocked/discovered dockable realms
    if curr_rules.get("is_mobile_vessel") and str(curr_rules.get("bridge_node_id") or "") == curr_node_id:
        docked_rid = str(curr_rules.get("docked_realm_id") or "")
        for r_nid, r_node in nodes_by_id.items():
            if str(r_node.get("node_type") or "").upper() != "REALM":
                continue
            if r_nid in (curr_realm_id, docked_rid):
                continue
            r_rules = get_realm_rules(r_node)
            if r_rules.get("is_hidden"):
                continue
            dock_nid = str(r_rules.get("dock_node_id") or "")
            if not dock_nid or dock_nid not in nodes_by_id:
                continue
            key = ("starship_jump", dock_nid, r_nid)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            r_name = str(r_node.get("name") or r_nid)
            choices.append({
                "label": f"🚀 Plot FTL Jump to {r_name}",
                "stat": "NONE",
                "requirement": 0,
                "mp_cost": 0,
                "intent": "movement",
                "sub_intent": "starship_jump",
                "target_node_id": dock_nid,
                "target_realm_id": r_nid,
                "vessel_realm_id": curr_realm_id,
                "portal_edge_type": "ftl_jump",
                "is_phase2_choice": True,
                "_priority_slot": True,
            })

    # 3. Spaceport / Dock -> Autopilot Recall Starship when vessel is docked elsewhere (disabled if comms_isolated)
    if not curr_rules.get("comms_isolated") and curr_rules.get("dock_node_id") and is_at_access_point_in_memory(
        curr_node_id, str(curr_rules["dock_node_id"]), nodes_by_id
    ):
        for v_nid, v_node in nodes_by_id.items():
            if str(v_node.get("node_type") or "").upper() != "REALM" or v_nid == curr_realm_id:
                continue
            v_rules = get_realm_rules(v_node)
            if not v_rules.get("is_mobile_vessel"):
                continue
            if str(v_rules.get("docked_realm_id") or "") == curr_realm_id:
                continue
            key = ("recall_starship", str(curr_rules["dock_node_id"]), v_nid)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            v_name = str(v_node.get("name") or v_nid)
            choices.append({
                "label": f"🚀 Recall {v_name} to Dock",
                "stat": "NONE",
                "requirement": 0,
                "mp_cost": 0,
                "intent": "movement",
                "sub_intent": "recall_starship",
                "target_node_id": str(curr_rules["dock_node_id"]),
                "target_realm_id": curr_realm_id,
                "vessel_realm_id": v_nid,
                "portal_edge_type": "shuttle_route",
                "is_phase2_choice": True,
                "_priority_slot": True,
            })

    # 4. Domain portal extensions (e.g., Folklore Spirit Realm)
    from ..folklore_spirit_realm import get_folklore_portal_choices
    extra = get_folklore_portal_choices(session_id, curr_node_id, curr_realm_id, nodes_by_id, seen_keys) or []
    if extra:
        choices.extend(extra)

    return choices
