from __future__ import annotations
"""
mechanics/world/locations/pathfinding.py
Deterministic Graph Pathfinding & Spatial Movement Engine (Phase 4).

Implements:
- Multi-edge shortest path graph routing (BFS/Dijkstra) across SQLite world_edges
- Access gating, key checks, lockpicking, curfew stealth verification & threshold halting (Q3, A1)
- Fog of War: hidden node exclusion until discovered (A6)
- Combat flee & eviction displacement with one-way edge fallback (A7, A12)
- Companion privacy filtering & auto-reunion (A2, A9)
- Freeform text fuzzy graph destination resolution (A10)
- Intermediate node ambush interruption (A11)
- Transit hub fare gating (A13)
"""

import heapq
import json
import logging
import re
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set, Tuple

import db
from config import DETERMINISTIC_MOVEMENT

logger = logging.getLogger(__name__)


def format_node_hierarchy(session_id: int, node_id: str) -> str:
    """
    Deterministically formats a node_id into a canonical 3-tier location string:
    'Zone ➔ Facility ➔ Room' or 'Zone ➔ Facility ➔ Main Area'.
    """
    if not session_id or not node_id:
        return ""
    node = db.get_world_node(session_id, node_id)
    if not node:
        return str(node_id)
    ntype = node.get("node_type", "ROOM")
    ancestors = db.get_node_ancestors(session_id, node_id)

    if ntype == "ROOM":
        fac_node = ancestors[0] if ancestors else None
        zone_node = ancestors[1] if len(ancestors) > 1 else (fac_node if fac_node and fac_node.get("node_type") == "ZONE" else None)
        z_name = zone_node.get("name") if zone_node else "Main Academy Campus"
        f_name = fac_node.get("name") if fac_node else "Main Facility"
        r_name = node.get("name") or "Main Area"
        return f"{z_name} ➔ {f_name} ➔ {r_name}"
    elif ntype == "FACILITY":
        zone_node = ancestors[0] if ancestors else None
        z_name = zone_node.get("name") if zone_node else "Main Academy Campus"
        f_name = node.get("name") or "Main Facility"
        return f"{z_name} ➔ {f_name} ➔ Main Area"
    elif ntype == "ZONE":
        z_name = node.get("name") or "Main Academy Campus"
        return f"{z_name} ➔ Main Area ➔ Main Area"
    return node.get("name") or str(node_id)


def get_edge_between(session_id: int, from_node_id: str, to_node_id: str) -> dict:
    """
    Retrieves the edge definition between two adjacent nodes in world_edges.
    Falls back to implicit parent-child transitions (1 minute, unlocked).
    """
    if not session_id or not from_node_id or not to_node_id:
        return {"from_node_id": from_node_id, "to_node_id": to_node_id, "travel_minutes": 2, "is_locked": 0, "edge_type": "hallway", "is_bidirectional": 1}

    with db.get_conn() as conn:
        # Check direct edge
        row = conn.execute(
            "SELECT * FROM world_edges WHERE session_id = ? AND from_node_id = ? AND to_node_id = ?",
            (session_id, from_node_id, to_node_id)
        ).fetchone()
        if row:
            return dict(row)

        # Check bidirectional edge
        row = conn.execute(
            "SELECT * FROM world_edges WHERE session_id = ? AND from_node_id = ? AND to_node_id = ? AND is_bidirectional = 1",
            (session_id, to_node_id, from_node_id)
        ).fetchone()
        if row:
            return dict(row)

    # Check parent-child hierarchy
    from_node = db.get_world_node(session_id, from_node_id)
    to_node = db.get_world_node(session_id, to_node_id)
    if from_node and to_node:
        if from_node.get("parent_id") == to_node_id or to_node.get("parent_id") == from_node_id:
            return {
                "from_node_id": from_node_id,
                "to_node_id": to_node_id,
                "travel_minutes": 1,
                "is_locked": 0,
                "edge_type": "internal",
                "is_bidirectional": 1,
            }

    return {
        "from_node_id": from_node_id,
        "to_node_id": to_node_id,
        "travel_minutes": 2,
        "is_locked": 0,
        "edge_type": "hallway",
        "is_bidirectional": 1,
    }


def is_node_hidden(node: Optional[dict]) -> bool:
    """Returns True if a node is marked as hidden/secret either directly or via state_json (A6)."""
    if not node:
        return False
    if node.get("is_hidden") == 1:
        return True
    s_json = node.get("state_json")
    if s_json:
        try:
            parsed = json.loads(s_json) if isinstance(s_json, str) else s_json
            return bool(parsed.get("is_hidden"))
        except Exception:
            pass
    return False


def find_spatial_path(
    session_id: int,
    from_node_id: str,
    to_node_id: str,
    include_hidden: bool = False,
    discovered_nodes: Optional[Set[str]] = None,
) -> List[str]:
    """
    Finds the shortest path of node IDs from from_node_id to to_node_id
    using Dijkstra's algorithm across world_edges plus implicit parent-child transitions.
    Excludes hidden nodes (is_hidden == 1) unless discovered (A6).
    Returns an ordered list of node IDs: [from_node_id, ..., to_node_id].
    """
    if not session_id or not from_node_id or not to_node_id:
        return []
    if from_node_id == to_node_id:
        return [from_node_id]

    discovered = set(discovered_nodes or [])
    # Also check session discovered POIs / unlocked nodes
    with db.get_conn() as conn:
        disc_rows = conn.execute(
            "SELECT node_id FROM world_nodes WHERE session_id = ? AND (is_dynamic = 1 OR state_json LIKE '%discovered%')",
            (session_id,)
        ).fetchall()
        for dr in disc_rows:
            discovered.add(dr["node_id"])

    edges = db.get_session_world_edges(session_id)
    nodes = db.get_session_world_nodes(session_id)
    node_map = {n["node_id"]: n for n in nodes}

    to_node_obj = node_map.get(to_node_id)
    if is_node_hidden(to_node_obj) and not include_hidden:
        if to_node_id not in discovered:
            # Cannot pathfind to undiscovered secret node (A6)
            return []

    adj = defaultdict(list)
    for e in edges:
        u = e.get("from_node_id")
        v = e.get("to_node_id")
        w = max(1, int(e.get("travel_minutes") or 2))
        if not u or not v:
            continue

        v_node = node_map.get(v)
        v_hidden = bool(is_node_hidden(v_node) and v not in discovered and not include_hidden)
        if not v_hidden:
            adj[u].append((v, w))

        if e.get("is_bidirectional", 1):
            u_node = node_map.get(u)
            u_hidden = bool(is_node_hidden(u_node) and u not in discovered and not include_hidden)
            if not u_hidden:
                adj[v].append((u, w))

    # Add implicit parent-child transitions ONLY between FACILITY and ROOM for nodes that have no explicit edges defined
    explicit_nodes = {e.get("from_node_id") for e in edges} | {e.get("to_node_id") for e in edges}
    for n in nodes:
        pid = n.get("parent_id")
        nid = n.get("node_id")
        p_node = node_map.get(pid)
        if p_node and p_node.get("node_type") == "FACILITY" and n.get("node_type") == "ROOM":
            if nid not in explicit_nodes or pid not in explicit_nodes:
                n_hidden = bool(is_node_hidden(n) and nid not in discovered and not include_hidden)
                if not n_hidden:
                    adj[pid].append((nid, 1))
                    adj[nid].append((pid, 1))

    dist = {from_node_id: 0}
    parent: Dict[str, Optional[str]] = {from_node_id: None}
    pq = [(0, from_node_id)]

    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, float("inf")):
            continue
        if u == to_node_id:
            break
        for v, w in adj.get(u, []):
            if d + w < dist.get(v, float("inf")):
                dist[v] = d + w
                parent[v] = u
                heapq.heappush(pq, (d + w, v))

    if to_node_id not in parent:
        return []

    path = []
    curr: Optional[str] = to_node_id
    while curr is not None:
        path.append(curr)
        curr = parent.get(curr)
    path.reverse()
    return path


def evaluate_spatial_route(
    session_id: int,
    route_node_ids: List[str],
    session: dict,
    party: list = None,
    actions: list = None,
    traveling_companions: list = None,
) -> dict[str, Any]:
    """
    Evaluates a planned multi-node route:
    - Verifies locks, keys, and skill check DC on each edge (Q3, A3)
    - Checks curfew and access gates (A4)
    - Halts immediately at the pre-barrier node on failure (A1)
    - Detects mid-route ambush interruptions (A11)
    - Checks transit hub fare gating (A13)
    - Applies companion privacy gating and auto-reunion (A2, A9)
    """
    if not route_node_ids:
        curr_nid = session.get("current_node_id") or ""
        curr_loc = session.get("current_location") or ""
        return {
            "success": True,
            "effective_node_id": curr_nid,
            "effective_location": curr_loc,
            "traversed_nodes": [curr_nid] if curr_nid else [],
            "travel_minutes": 0,
            "gated": False,
            "barrier_node_id": None,
            "stage_directives": [],
            "waiting_outside_companions": [],
            "traveling_companions": traveling_companions or [],
            "unlocked_edges": [],
        }

    effective_node_id = route_node_ids[0]
    traversed_nodes = [effective_node_id]
    accumulated_minutes = 0
    gated = False
    barrier_node_id = None
    stage_directives: List[str] = []
    unlocked_edges: List[Tuple[str, str]] = []
    last_gate_res: Optional[dict] = None

    # Gather party inventory
    inventory_items: List[str] = []
    inv_objs: List[Any] = []
    for member in (party or []):
        c_obj = member[0] if isinstance(member, (tuple, list)) else member
        inv_list = []
        if isinstance(member, (tuple, list)) and len(member) > 1 and isinstance(member[1], list):
            inv_list = member[1]
        elif isinstance(c_obj, dict) and c_obj.get("inventory"):
            inv_list = c_obj["inventory"]
        elif isinstance(c_obj, dict) and c_obj.get("user_id"):
            inv_list = db.get_inventory(c_obj["user_id"]) or []

        for it in (inv_list or []):
            it_name = str(it.get("name") if isinstance(it, dict) else it).strip().lower()
            inventory_items.append(it_name)
            inv_objs.append((c_obj, it, inv_list))

    # Evaluate action check tier if player attempted breach
    action_check_tier = "success"
    if actions and isinstance(actions[0], dict) and actions[0].get("check"):
        chk = actions[0]["check"]
        if isinstance(chk, dict):
            action_check_tier = str(chk.get("tier", "success")).lower()
        else:
            action_check_tier = str(getattr(chk, "tier", "success")).lower()

    # Step through each hop
    for i in range(len(route_node_ids) - 1):
        u = route_node_ids[i]
        v = route_node_ids[i + 1]
        edge = get_edge_between(session_id, u, v)
        travel_cost = max(1, int(edge.get("travel_minutes") or 2))

        # 1. Edge Lock Check (A3)
        if edge.get("is_locked"):
            key_req = str(edge.get("lock_key_item") or "").strip().lower()
            has_key = False
            matching_it_obj = None

            if key_req:
                for c_obj, it, inv_list in inv_objs:
                    it_nm = str(it.get("name") if isinstance(it, dict) else it).strip().lower()
                    if key_req in it_nm or it_nm in key_req:
                        has_key = True
                        matching_it_obj = (c_obj, it, inv_list)
                        break

            # Check if unlocked by key
            if has_key and matching_it_obj:
                c_obj, it, inv_list = matching_it_obj
                # Permanent unlock for session
                try:
                    from mechanics.world.locations.access_gate import record_node_unlock
                    record_node_unlock(session_id, v)
                except Exception:
                    pass
                with db.get_conn() as conn:
                    conn.execute(
                        "UPDATE world_edges SET is_locked = 0 WHERE session_id = ? AND ((from_node_id = ? AND to_node_id = ?) OR (from_node_id = ? AND to_node_id = ? AND is_bidirectional = 1))",
                        (session_id, u, v, v, u)
                    )
                unlocked_edges.append((u, v))

                # Standard keys remain in inventory; single-use keys are consumed (A3)
                is_single_use = (
                    isinstance(it, dict)
                    and (
                        it.get("is_single_use")
                        or it.get("consumable")
                        or str(it.get("item_type", "")).lower() in ("consumable", "single_use")
                    )
                )
                if is_single_use:
                    try:
                        inv_list.remove(it)
                    except Exception:
                        pass
                    if isinstance(c_obj, dict) and c_obj.get("user_id"):
                        try:
                            if it.get("id"):
                                db.remove_item(c_obj["user_id"], it["id"])
                            else:
                                db.remove_item_by_name(c_obj["user_id"], it.get("name", ""))
                        except Exception:
                            pass
            else:
                # Check skill check lockpick/force (A4)
                skill_req = str(edge.get("skill_check_type") or "").strip().upper()
                is_skill_success = action_check_tier in ("critical_success", "crit_success", "success", "partial_success")
                if skill_req and is_skill_success:
                    with db.get_conn() as conn:
                        conn.execute(
                            "UPDATE world_edges SET is_locked = 0 WHERE session_id = ? AND ((from_node_id = ? AND to_node_id = ?) OR (from_node_id = ? AND to_node_id = ? AND is_bidirectional = 1))",
                            (session_id, u, v, v, u)
                        )
                    unlocked_edges.append((u, v))
                else:
                    # Halt at preceding accessible node u (Q3, A1)
                    gated = True
                    barrier_node_id = v
                    last_gate_res = {"gated": True, "node_id": v, "reason_code": "locked_edge"}
                    v_node = db.get_world_node(session_id, v)
                    v_name = (v_node.get("name") if v_node else v) or v
                    stage_directives.append(
                        f"[STAGE DIRECTION — ACCESS BLOCKED]: The pathway to {v_name} is locked. "
                        f"Requires key '{edge.get('lock_key_item') or 'Key'}' or lockpicking check."
                    )
                    break

        # 2. Transit Hub Fare Gating (A13)
        if edge.get("edge_type") == "transit_hub" or edge.get("is_transit_hub") == 1:
            fare_key = str(edge.get("lock_key_item") or "").strip().lower()
            if fare_key and not any(fare_key in item for item in inventory_items):
                gated = True
                barrier_node_id = v
                last_gate_res = {"gated": True, "node_id": v, "reason_code": "transit_fare"}
                v_node = db.get_world_node(session_id, v)
                v_name = (v_node.get("name") if v_node else v) or v
                stage_directives.append(
                    f"[STAGE DIRECTION — ACCESS BLOCKED]: Transit requires {edge.get('lock_key_item')} to travel to {v_name}."
                )
                break

        # 3. Node Access Gate / Curfew Verification (A4)
        from mechanics.world.locations.access_gate import evaluate_node_access_gate
        gate_res = evaluate_node_access_gate(
            session_id, v, session,
            actions=actions, party=party, companions=traveling_companions
        )
        if gate_res.get("gated"):
            gated = True
            barrier_node_id = v
            last_gate_res = gate_res
            v_node = db.get_world_node(session_id, v)
            v_name = (v_node.get("name") if v_node else v) or v
            reason = gate_res.get("reason") or "Access restricted"
            stage_directives.append(
                f"[STAGE DIRECTION — ACCESS BLOCKED]: Access to {v_name} halted. Reason: {reason}."
            )
            break

        # 4. Mid-Route Ambush / Encounter Interruption (A11)
        if v != route_node_ids[-1]:
            # Intermediate node check
            v_state = db.get_world_node_state(session_id, v)
            if v_state.get("active_ambush") or v_state.get("hostile_patrol"):
                accumulated_minutes += travel_cost
                effective_node_id = v
                traversed_nodes.append(v)
                v_node = db.get_world_node(session_id, v)
                v_name = (v_node.get("name") if v_node else v) or v
                stage_directives.append(
                    f"[STAGE DIRECTION — AMBUSH INTERRUPTION]: Journey interrupted at {v_name}! Hostile forces block the route."
                )
                break

            # Covert threshold halting (Blueprint 9B)
            st_state = session.get("stealth_state") or {}
            if st_state.get("is_hidden") and (v_state.get("has_sentries") or v_state.get("hostile_patrol") or v_state.get("alert_level") in ("suspicious", "searching")):
                alert_stage = st_state.get("alert_level", "unaware")
                if alert_stage in ("suspicious", "searching", "detected"):
                    accumulated_minutes += travel_cost
                    effective_node_id = v
                    traversed_nodes.append(v)
                    v_node = db.get_world_node(session_id, v)
                    v_name = (v_node.get("name") if v_node else v) or v
                    stage_directives.append(
                        f"[STAGE DIRECTION — STEALTH CHECKPOINT HALT]: Covert movement halted at {v_name}. Sentries are alert ({alert_stage.upper()} {st_state.get('detection_meter', 0)}%) — pausing for player tactical command."
                    )
                    break

        # Successfully traversed hop
        accumulated_minutes += travel_cost
        effective_node_id = v
        traversed_nodes.append(v)

    if gated and barrier_node_id:
        if last_gate_res and last_gate_res.get("halt_location_override"):
            effective_location = last_gate_res["halt_location_override"]
        else:
            barrier_loc = format_node_hierarchy(session_id, barrier_node_id)
            sep = "➔" if "➔" in barrier_loc else "->"
            parts = [p.strip() for p in barrier_loc.split(sep) if p.strip()]
            if len(parts) >= 2:
                effective_location = f"{parts[0]} ➔ {parts[1]} ➔ Outside the Locked Entrance"
            else:
                effective_location = f"{barrier_loc} ➔ Outside the Locked Entrance"
    else:
        effective_location = format_node_hierarchy(session_id, effective_node_id)

    # 5. Companion Privacy Filter (A2, A9)
    dest_node = db.get_world_node(session_id, effective_node_id)
    privacy_lvl = str((dest_node.get("privacy_level") if dest_node else "public") or "public").lower()

    active_companions = list(traveling_companions or [])
    waiting_outside: List[dict] = []
    following_inside: List[dict] = []

    if privacy_lvl == "private":
        # Check romantic/intimate context
        intimacy_state = session.get("intimacy_state") or {}
        dialogue_partners = {str(dp).strip().lower() for dp in (session.get("dialogue_partners") or [])}

        for comp in active_companions:
            c_name = str(comp.get("name") or "").strip()
            c_low = c_name.lower()
            is_intimate = (
                c_low in intimacy_state
                or comp.get("affinity", 0) >= 80
                or c_low in dialogue_partners
                or bool(comp.get("is_romantic") or comp.get("active_rendezvous"))
            )
            if is_intimate:
                following_inside.append(comp)
            else:
                waiting_outside.append(comp)

        if waiting_outside:
            names = ", ".join(c.get("name", "Companion") for c in waiting_outside)
            room_name = (dest_node.get("name") if dest_node else "Private Room") or "Private Room"
            stage_directives.append(
                f"[STAGE DIRECTION — PRIVACY GATE]: {names} wait outside in the hallway while the player enters {room_name}."
            )
            session["waiting_outside_companions"] = waiting_outside
            traveling_companions = following_inside
    else:
        # Returning to public or semi-private space: Auto-rejoin waiting companions (A9)
        previously_waiting = session.get("waiting_outside_companions") or []
        if previously_waiting:
            active_companions.extend(previously_waiting)
            traveling_companions = active_companions
            session["waiting_outside_companions"] = []
            names = ", ".join(c.get("name", "Companion") for c in previously_waiting)
            stage_directives.append(
                f"[STAGE DIRECTION — COMPANION REUNION]: {names} re-join the party upon exiting into public space."
            )

    return {
        "success": not gated,
        "effective_node_id": effective_node_id,
        "effective_location": effective_location,
        "traversed_nodes": traversed_nodes,
        "travel_minutes": accumulated_minutes,
        "gated": gated,
        "barrier_node_id": barrier_node_id,
        "access_gate": last_gate_res if (gated and last_gate_res) else {"gated": False},
        "stage_directives": stage_directives,
        "waiting_outside_companions": waiting_outside,
        "traveling_companions": traveling_companions or [],
        "unlocked_edges": unlocked_edges,
    }


def resolve_flee_destination(
    session_id: int,
    current_node_id: str,
    previous_node_id: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Deterministically computes the retreat destination when fleeing combat or evicted (A7, A12).
    - If previous_node_id is valid and the reverse edge is bidirectional, retreats to previous_node_id (A7).
    - If previous_node_id is missing or the entry edge was strictly one-way (is_bidirectional == 0),
      cascades to the parent facility entrance or nearest public node (A12).
    Returns (retreat_node_id, retreat_location_str).
    """
    if not session_id or not current_node_id:
        return ("", "")

    # 1. Check reverse edge to previous_node_id (A7)
    if previous_node_id and previous_node_id != current_node_id:
        prev_node = db.get_world_node(session_id, previous_node_id)
        if prev_node:
            edge = get_edge_between(session_id, previous_node_id, current_node_id)
            # If edge was bidirectional, reverse traversal is permitted
            if edge.get("is_bidirectional", 1) != 0:
                loc_str = format_node_hierarchy(session_id, previous_node_id)
                return (previous_node_id, loc_str)

    # 2. One-way entry edge or missing history: Cascade to parent facility entrance (A12)
    curr_node = db.get_world_node(session_id, current_node_id)
    if curr_node:
        parent_id = curr_node.get("parent_id")
        if parent_id:
            # Find sibling entrance room under parent facility
            nodes = db.get_session_world_nodes(session_id)
            for n in nodes:
                if n.get("parent_id") == parent_id and n.get("node_type") == "ROOM":
                    nm = n.get("name", "").lower()
                    if any(ent in nm for ent in ("entrance", "lobby", "foyer", "main hall", "courtyard")):
                        return (n["node_id"], format_node_hierarchy(session_id, n["node_id"]))

            # Fallback to parent node itself
            p_node = db.get_world_node(session_id, parent_id)
            if p_node:
                return (parent_id, format_node_hierarchy(session_id, parent_id))

    return (current_node_id, format_node_hierarchy(session_id, current_node_id))


def match_freeform_spatial_destination(
    session_id: int,
    current_node_id: str,
    action_text: str,
) -> Optional[str]:
    """
    Fuzzy matches freeform player text against reachable nodes in SQLite world_nodes (A10).
    Ignores tactical micro-features (bleachers, desk, altar) per rule A8.
    Returns candidate target_node_id if matched, else None.
    """
    if not session_id or not action_text:
        return None

    clean = str(action_text).strip().lower()

    # Rule A8: Tactical micro-features are NOT node transitions
    micro_patterns = [
        r"\b(?:behind|under|beneath|beside|against|by)\s+(?:the\s+|a\s+)?"
        r"(?:bleachers|desk|curtain|bookshelf|stacks|locker|pillar|tree|bush|table|couch|altar|statue|window|railing)\b",
        r"\b(?:crouch|hide|duck|lean|slip\s+behind|crawl\s+under)\b",
    ]
    for pat in micro_patterns:
        if re.search(pat, clean):
            return None

    nodes = db.get_session_world_nodes(session_id)
    if not nodes:
        return None

    best_match: Optional[str] = None
    longest_match_len = 0

    for n in nodes:
        nid = n["node_id"]
        if nid == current_node_id:
            continue
        n_name = str(n.get("name") or "").strip().lower()
        if not n_name or len(n_name) < 3:
            continue

        # Check exact or substring containment
        if n_name in clean or clean in n_name:
            if len(n_name) > longest_match_len:
                # Ensure a path exists
                path = find_spatial_path(session_id, current_node_id, nid)
                if path:
                    best_match = nid
                    longest_match_len = len(n_name)

    return best_match
