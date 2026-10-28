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

logger = logging.getLogger(__name__)


def format_node_hierarchy(session_id: int, node_id: str) -> str:
    """
    Deterministically formats a node_id into a canonical 3-tier location string:
    'Zone ➔ Facility ➔ Room'.
    """
    if not session_id or not node_id:
        return ""
    node = db.get_world_node(session_id, node_id)
    if not node:
        return str(node_id)
    ntype = node.get("node_type", "ROOM")
    ancestors = db.get_node_ancestors(session_id, node_id)
    from .hierarchy import resolve_default_sublocation

    if ntype == "ROOM":
        fac_node = ancestors[0] if ancestors else None
        zone_node = ancestors[1] if len(ancestors) > 1 else (fac_node if fac_node and fac_node.get("node_type") == "ZONE" else None)
        z_name = zone_node.get("name") if zone_node else "Main Academy Campus"
        f_name = fac_node.get("name") if fac_node else "Main Facility"
        r_name = node.get("name") or ""
        if not r_name or r_name.strip().lower() == "main area":
            r_name = resolve_default_sublocation(f_name, z_name, session_id=session_id)
        return f"{z_name} ➔ {f_name} ➔ {r_name}"
    elif ntype == "FACILITY":
        zone_node = ancestors[0] if ancestors else None
        z_name = zone_node.get("name") if zone_node else "Main Academy Campus"
        f_name = node.get("name") or "Main Facility"
        r_name = resolve_default_sublocation(f_name, z_name, session_id=session_id)
        return f"{z_name} ➔ {f_name} ➔ {r_name}"
    elif ntype == "ZONE":
        z_name = node.get("name") or "Main Academy Campus"
        all_nodes = db.get_session_world_nodes(session_id)
        fac = next((n for n in all_nodes if n.get("node_type") == "FACILITY" and n.get("parent_id") == node_id), None)
        f_name = fac["name"] if fac else z_name
        r_name = resolve_default_sublocation(f_name, z_name, session_id=session_id)
        return f"{z_name} ➔ {f_name} ➔ {r_name}"
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
    persist_db: bool = True,
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
            "focal_point": None,
            "traversed_nodes": [curr_nid] if curr_nid else [],
            "travel_minutes": 0,
            "gated": False,
            "barrier_node_id": None,
            "stage_directives": [],
            "waiting_outside_companions": [],
            "traveling_companions": traveling_companions or [],
            "unlocked_edges": [],
            "unlocked_nodes": [],
            "consumed_key_items": [],
        }

    effective_node_id = route_node_ids[0]
    traversed_nodes = [effective_node_id]
    accumulated_minutes = 0
    gated = False
    barrier_node_id = None
    halt_focal_point: Optional[str] = None
    stage_directives: List[str] = []
    unlocked_edges: List[Tuple[str, str]] = []
    unlocked_nodes: List[str] = []
    consumed_key_items: List[dict] = []
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

    # Evaluate action check tier if player attempted breach across any party action
    action_check_tier = None
    for act_cand in (actions or []):
        if isinstance(act_cand, dict) and act_cand.get("check"):
            chk = act_cand["check"]
            cand_tier = str(chk.get("tier", "success") if isinstance(chk, dict) else getattr(chk, "tier", "success")).lower()
            action_check_tier = cand_tier
            if cand_tier in ("critical_success", "crit_success", "success", "partial_success"):
                break

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
                unlocked_nodes.append(v)
                unlocked_edges.append((u, v))
                if persist_db:
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
                        consumed_key_items.append({
                            "user_id": c_obj["user_id"],
                            "item_id": it.get("id"),
                            "name": it.get("name", ""),
                        })
                        if persist_db:
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
                is_skill_success = bool(action_check_tier) and action_check_tier in ("critical_success", "crit_success", "success", "partial_success")
                if skill_req and is_skill_success:
                    unlocked_edges.append((u, v))
                    if persist_db:
                        with db.get_conn() as conn:
                            conn.execute(
                                "UPDATE world_edges SET is_locked = 0 WHERE session_id = ? AND ((from_node_id = ? AND to_node_id = ?) OR (from_node_id = ? AND to_node_id = ? AND is_bidirectional = 1))",
                                (session_id, u, v, v, u)
                            )
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
            from mechanics.stealth import any_actor_hidden, get_session_stealth_state
            st_state = get_session_stealth_state(session)
            if any_actor_hidden(session) and (v_state.get("has_sentries") or v_state.get("hostile_patrol") or v_state.get("alert_level") in ("suspicious", "searching")):
                alert_stage = st_state.get("alert_level", "unaware")
                if alert_stage in ("suspicious", "searching", "detected"):
                    accumulated_minutes += travel_cost
                    effective_node_id = v
                    traversed_nodes.append(v)
                    v_node = db.get_world_node(session_id, v)
                    v_name = (v_node.get("name") if v_node else v) or v
                    stage_directives.append(
                        f"[STAGE DIRECTION — STEALTH CHECKPOINT HALT]: Covert movement halted at {v_name}. "
                        f"Sentries are alert ({alert_stage.upper()} {st_state.get('detection_meter', 0)}%) — pausing for player tactical command "
                        f"(do NOT print raw percentages or stage names in narrative prose)."
                    )
                    break

        # Successfully traversed hop
        accumulated_minutes += travel_cost
        effective_node_id = v
        traversed_nodes.append(v)

    if gated and barrier_node_id:
        b_node = db.get_world_node(session_id, barrier_node_id)
        v_name = (b_node.get("name") if b_node else barrier_node_id) or barrier_node_id
        if last_gate_res and last_gate_res.get("halt_location_override"):
            effective_location = last_gate_res["halt_location_override"]
            override_nid = str(last_gate_res.get("node_id") or "").strip()
            if override_nid and db.get_world_node(session_id, override_nid):
                effective_node_id = override_nid
            halt_focal_point = last_gate_res.get("focal_point") or f"Outside the Locked Entrance ({v_name})"
        else:
            u_node = db.get_world_node(session_id, effective_node_id)
            u_loc = format_node_hierarchy(session_id, effective_node_id)
            gate_reason = str((last_gate_res or {}).get("reason_code") or "")
            if gate_reason in ("locked_edge", "transit_fare") or (u_node and u_node.get("node_type") == "ROOM"):
                effective_location = u_loc
                halt_focal_point = (last_gate_res or {}).get("focal_point") or f"Outside the Locked Entrance ({v_name})"
            else:
                sep = "➔" if "➔" in u_loc else "->"
                parts = [p.strip() for p in u_loc.split(sep) if p.strip()]
                if len(parts) >= 2:
                    effective_location = f"{parts[0]} ➔ {parts[1]} ➔ Outside the Locked Entrance ({v_name})"
                else:
                    effective_location = f"{u_loc} ➔ Outside the Locked Entrance ({v_name})"
                halt_focal_point = (last_gate_res or {}).get("focal_point") or f"Outside the Locked Entrance ({v_name})"
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
        "focal_point": halt_focal_point,
        "traversed_nodes": traversed_nodes,
        "travel_minutes": accumulated_minutes,
        "gated": gated,
        "barrier_node_id": barrier_node_id,
        "access_gate": last_gate_res if (gated and last_gate_res) else {"gated": False},
        "stage_directives": stage_directives,
        "waiting_outside_companions": waiting_outside,
        "traveling_companions": traveling_companions or [],
        "unlocked_edges": unlocked_edges,
        "unlocked_nodes": unlocked_nodes,
        "consumed_key_items": consumed_key_items,
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


def resolve_safe_open_eviction_destination(
    session_id: int,
    current_node_id: Optional[str] = None,
    current_day: int = 1,
    current_minute: int = 480,
    scen_key: str = "high_school_drama",
    current_location: str = "",
    previous_node_id: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Deterministically resolves the nearest currently-open, non-curfewed public node
    when a player is evicted from a restricted, private, or curfew-locked area.
    - Daytime campus trespass (07:00–20:00) evicts to the nearest open school hallway/foyer/courtyard.
    - Night campus curfew (20:00–07:00) evicts outside to the School Main Gates exterior / public street
      rather than leaving the player inside a curfewed hallway.
    """
    if not session_id:
        return ("", "")

    start_nid = str(current_node_id or "").strip()
    if not start_nid and current_location:
        try:
            start_nid = db.resolve_node_id_from_location(session_id, current_location) or ""
        except Exception:
            start_nid = ""

    safe_min = int(current_minute or 480) % 1440
    from mechanics.world.world_schedule import (
        is_abandoned_school_node,
        is_campus_node_or_location,
        is_high_school_setting,
    )
    from .access_gate import get_node_effective_access_info

    start_node = db.get_world_node(session_id, start_nid) if start_nid else None
    start_parent = (
        db.get_world_node(session_id, start_node["parent_id"])
        if (start_node and start_node.get("parent_id"))
        else None
    )

    # 1. High School Night Curfew (20:00–07:00): Campus buildings are all under curfew lockdown,
    # so security escorts the player outside to the School Main Gates exterior or public street.
    if is_high_school_setting(scen_key) and (safe_min >= 1200 or safe_min < 420):
        on_campus = is_campus_node_or_location(
            start_node, start_parent, location_str=current_location, session_id=session_id, scen_key=scen_key
        )
        if on_campus and not is_abandoned_school_node(start_node, start_parent, location_str=current_location):
            from .seeds import get_session_school_name
            school_zone = get_session_school_name(session_id, scen_key) or "Main Academy Campus"
            if start_nid != "loc_school_gate" and db.get_world_node(session_id, "loc_school_gate"):
                return ("loc_school_gate", f"{school_zone} ➔ School Main Gates ➔ Outside the Locked Entrance")
            for street_nid in ("loc_city_square", "loc_local_park", "loc_convenience_store"):
                if db.get_world_node(session_id, street_nid):
                    return (street_nid, format_node_hierarchy(session_id, street_nid))
            return ("loc_school_gate", f"{school_zone} ➔ School Main Gates ➔ Outside the Locked Entrance")

    def _is_safe_open_public(nid: str) -> bool:
        if not nid or nid == start_nid:
            return False
        n_obj = db.get_world_node(session_id, nid)
        if not n_obj or n_obj.get("is_hidden"):
            return False
        if str(n_obj.get("node_type") or "").upper() == "ZONE":
            return False
        if str(n_obj.get("privacy_level") or "public").lower() == "private":
            return False
        info = get_node_effective_access_info(
            session_id, nid, current_day=current_day, current_minute=current_minute, scen_key=scen_key
        )
        return bool(
            info.get("access_tier") == "open"
            and not info.get("curfew_active")
            and not info.get("is_trespassing")
            and not info.get("schedule_locked")
        )

    def _is_hallway_or_lobby(nid: str) -> bool:
        n_obj = db.get_world_node(session_id, nid) or {}
        nm = f"{nid} {n_obj.get('name', '')}".lower()
        return any(
            k in nm
            for k in ("foyer", "hallway", "corridor", "lobby", "entrance", "courtyard", "commons", "gate", "plaza", "square", "street")
        )

    # 2. Check previous_node_id if it is currently safe and open
    if previous_node_id and _is_safe_open_public(previous_node_id):
        return (previous_node_id, format_node_hierarchy(session_id, previous_node_id))

    all_nodes = db.get_session_world_nodes(session_id) or []

    # 3. Check sibling open hallway/foyer/entrance/courtyard rooms under the same parent facility
    if start_node and start_node.get("parent_id"):
        pid = start_node["parent_id"]
        siblings = [n["node_id"] for n in all_nodes if n.get("parent_id") == pid and n.get("node_id") != start_nid]
        for sib_id in siblings:
            if _is_hallway_or_lobby(sib_id) and _is_safe_open_public(sib_id):
                return (sib_id, format_node_hierarchy(session_id, sib_id))
        for sib_id in siblings:
            if _is_safe_open_public(sib_id):
                return (sib_id, format_node_hierarchy(session_id, sib_id))
        if _is_safe_open_public(pid):
            return (pid, format_node_hierarchy(session_id, pid))

    # 4. Walk outward via BFS over world_edges and parent/child relationships
    if start_nid:
        adj: Dict[str, List[str]] = {}
        try:
            with db.get_conn() as conn:
                edges = conn.execute(
                    "SELECT from_node_id, to_node_id, is_bidirectional FROM world_edges WHERE session_id=?",
                    (session_id,),
                ).fetchall()
            for r in edges:
                u, v = r["from_node_id"], r["to_node_id"]
                adj.setdefault(u, []).append(v)
                if r["is_bidirectional"] != 0:
                    adj.setdefault(v, []).append(u)
        except Exception:
            pass
        for n in all_nodes:
            nid = n.get("node_id")
            pid = n.get("parent_id")
            if nid and pid:
                adj.setdefault(nid, []).append(pid)
                adj.setdefault(pid, []).append(nid)

        visited = {start_nid}
        frontier = [start_nid]
        for _ in range(6):
            if not frontier:
                break
            next_frontier: List[str] = []
            for curr in frontier:
                for nb in adj.get(curr, []):
                    if nb not in visited:
                        visited.add(nb)
                        next_frontier.append(nb)
            for cand in next_frontier:
                if _is_hallway_or_lobby(cand) and _is_safe_open_public(cand):
                    return (cand, format_node_hierarchy(session_id, cand))
            for cand in next_frontier:
                if _is_safe_open_public(cand):
                    return (cand, format_node_hierarchy(session_id, cand))
            frontier = next_frontier

    # 5. Deterministic canonical public fallbacks
    for fallback_nid in (
        "loc_entrance_foyer",
        "loc_courtyard",
        "loc_school_gate",
        "loc_hq_main_lobby",
        "loc_city_square",
        "loc_local_park",
        "loc_convenience_store",
    ):
        if _is_safe_open_public(fallback_nid):
            return (fallback_nid, format_node_hierarchy(session_id, fallback_nid))

    for n in all_nodes:
        nid = n.get("node_id") or ""
        if _is_safe_open_public(nid):
            return (nid, format_node_hierarchy(session_id, nid))

    if start_nid:
        return (start_nid, format_node_hierarchy(session_id, start_nid))
    return ("", current_location)


def match_freeform_spatial_destination(
    session_id: int,
    current_node_id: str,
    action_text: str,
    intent: Optional[str] = None,
) -> Optional[str]:
    """
    Fuzzy matches freeform player movement text against reachable nodes in SQLite world_nodes (A10).
    Strictly requires movement intent (either structured intent or movement phrasing) and whole-word
    boundaries so local actions like 'Look at the library book' never teleport the party.
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

    norm_intent = str(intent or "").strip().lower()
    if norm_intent and norm_intent not in (
        "movement", "travel", "fast_travel", "move", "general_action",
        "social_invite", "accompanied_travel", "dialogue_init", "investigate_clue",
    ):
        return None
    from mechanics.world.locations.movement import is_movement_action
    if not is_movement_action(action_text):
        return None

    nodes = db.get_session_world_nodes(session_id)
    if not nodes:
        return None

    node_map = {n["node_id"]: n for n in nodes}

    def _get_root_zone_id(nid: str) -> str:
        curr = nid
        seen: Set[str] = set()
        while curr and curr in node_map and curr not in seen:
            seen.add(curr)
            pid = node_map[curr].get("parent_id")
            if not pid:
                return curr
            curr = pid
        return curr

    curr_root_zone = _get_root_zone_id(current_node_id) if current_node_id else ""

    best_match: Optional[str] = None
    longest_match_len = 0
    best_path_len = 999

    _generic_loc_words = {
        "the", "and", "for", "main", "area", "room", "hall", "hallway", "hallways",
        "building", "first", "second", "third", "floor", "north", "south", "east",
        "west", "central", "upper", "lower", "outer", "inner", "wing", "district",
        "street", "avenue", "school", "academy", "campus", "grounds",
        "corridor", "spot", "path", "bench", "benches", "desk", "desks",
        "running", "outdoor", "indoor", "quiet",
        "student", "service", "security",
        "store", "center", "centre", "place", "site", "front", "back",
        "side", "zone", "academic", "athletic", "commercial", "residential",
        "founder", "founders", "founder's", "varsity", "crown",
        "study", "case", "old", "new", "high", "private", "public",
    }
    token_to_nids: Dict[str, List[str]] = {}
    local_token_to_nids: Dict[str, List[str]] = {}
    for _n in nodes:
        _nid = _n["node_id"]
        _nm = str(_n.get("name") or "").strip().lower()
        _same_zone = bool(curr_root_zone and _get_root_zone_id(_nid) == curr_root_zone)
        for _w in set(re.findall(r"[a-z0-9']+", _nm)):
            if len(_w) >= 5 and _w not in _generic_loc_words:
                token_to_nids.setdefault(_w, []).append(_nid)
                if _same_zone:
                    local_token_to_nids.setdefault(_w, []).append(_nid)

    _stop_words = {"the", "and", "for", "of", "in", "at", "to", "a", "an", "main", "area", "room", "hall", "building", "first", "second", "third", "floor"}

    for n in nodes:
        nid = n["node_id"]
        if nid == current_node_id:
            continue
        n_name = str(n.get("name") or "").strip().lower()
        if not n_name or len(n_name) < 3:
            continue

        same_root_zone = bool(curr_root_zone and _get_root_zone_id(nid) == curr_root_zone)

        # Enforce whole-word boundaries so substrings inside other words never false-trigger
        matched_len = 0
        is_exact_full_name = False
        if re.search(r"(?<!\w)" + re.escape(n_name) + r"(?!\w)", clean):
            matched_len = len(n_name)
            is_exact_full_name = True
        else:
            name_words = [w for w in re.findall(r"[a-z0-9']+", n_name) if w not in _stop_words]
            if len(name_words) == 1 and len(name_words[0]) >= 5:
                stem = name_words[0]
                if re.search(r"(?<!\w)" + re.escape(stem) + r"(?!\w)", clean):
                    matched_len = len(stem)
            if matched_len == 0:
                # Multi-word phrase match from node name (e.g. 'running track', 'basketball court', 'library stacks')
                tokens_in_clean = [
                    w for w in name_words
                    if len(w) >= 4 and re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", clean)
                ]
                if len(tokens_in_clean) >= 2 and any(w not in _generic_loc_words or w in ("track", "court", "stacks", "gate", "foyer") for w in tokens_in_clean):
                    matched_len = sum(len(w) for w in tokens_in_clean)
            if matched_len == 0:
                # Single distinctive facility noun match (e.g. 'cafeteria', 'library', 'gymnasium', 'rooftop', 'homeroom')
                for w in name_words:
                    if len(w) >= 5 and w not in _generic_loc_words:
                        is_unique_locally = same_root_zone and 1 <= len(local_token_to_nids.get(w, [])) <= 2
                        is_unique_globally = len(token_to_nids.get(w, [])) == 1
                        if (is_unique_locally or is_unique_globally) and re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", clean):
                            matched_len = max(matched_len, len(w))

        if matched_len > 0 and (matched_len > longest_match_len or (matched_len == longest_match_len and best_match is not None)):
            path = find_spatial_path(session_id, current_node_id, nid)
            if not path:
                continue
            # Partial/token matches must stay within a reasonable multi-hop path
            if not is_exact_full_name:
                if not same_root_zone and len(path) > 8:
                    continue
                if len(path) > 10:
                    continue
            elif len(path) > 16:
                continue
            if matched_len > longest_match_len or len(path) < best_path_len:
                best_match = nid
                longest_match_len = matched_len
                best_path_len = len(path)

    return best_match


def get_adjacent_reachable_exits(session_id: int, current_node_id: str, limit: int = 6) -> List[str]:
    """Returns human-readable names of valid adjacent/reachable world_nodes from current_node_id."""
    if not session_id or not current_node_id:
        return []
    nodes = db.get_session_world_nodes(session_id)
    node_map = {n["node_id"]: n for n in nodes}
    edges = db.get_session_world_edges(session_id)
    cand_ids: List[str] = []
    seen: Set[str] = {current_node_id}

    for e in edges:
        u = e.get("from_node_id")
        v = e.get("to_node_id")
        if u == current_node_id and v and v not in seen:
            seen.add(v)
            cand_ids.append(v)
        elif v == current_node_id and e.get("is_bidirectional", 1) and u and u not in seen:
            seen.add(u)
            cand_ids.append(u)

    curr_node = node_map.get(current_node_id)
    if curr_node:
        pid = curr_node.get("parent_id")
        if pid and pid not in seen:
            seen.add(pid)
            cand_ids.append(pid)
        for n in nodes:
            nid = n["node_id"]
            if nid not in seen and (n.get("parent_id") == current_node_id or (pid and n.get("parent_id") == pid)):
                seen.add(nid)
                cand_ids.append(nid)

    names: List[str] = []
    for nid in cand_ids:
        n_obj = node_map.get(nid)
        if not n_obj or is_node_hidden(n_obj):
            continue
        nm = str(n_obj.get("name") or "").strip()
        if nm and nm not in names:
            names.append(nm)
        if len(names) >= limit:
            break
    return names


def resolve_unmatched_movement_destination(
    session_id: int,
    current_node_id: str,
    target_location_str: str = "",
    action_text: str = "",
    scen_key: str = "fantasy",
) -> dict[str, Any]:
    """
    Resolves freeform movement to a destination not yet matched in world_nodes (D10):
    - Campus / Slice-of-Life: blocks unseeded destinations (0m elapsed, stays at current_node_id,
      returns [STAGE DIRECTION — INVALID EXIT] with valid exits).
    - Open-World scenarios: deterministically spawns & stitches a 3-minute bidirectional child
      ROOM/FACILITY node in world_nodes + world_edges so Dijkstra routes into it cleanly.
    """
    raw_dest = str(target_location_str or "").strip()
    if not raw_dest and action_text:
        m = re.search(
            r"\b(?:travel|head|walk|go|move|journey|enter|visit|venture)\s+(?:over\s+|straight\s+|back\s+|out\s+)?(?:to|into|toward|towards)\s+(?:the\s+|a\s+|an\s+)?([a-zA-Z0-9' \-]{3,45})",
            str(action_text).strip(),
            re.IGNORECASE,
        )
        if m:
            raw_dest = re.split(r"\b(?:to\s+(?:ask|talk|speak|find|search|look|buy|check|meet|rest)|and\s+|where\s+|for\s+)\b", m.group(1), maxsplit=1, flags=re.IGNORECASE)[0].strip(" .,!?;:")

    if not raw_dest or raw_dest.lower() in ("here", "outside", "inside", "around", "away", "back"):
        return {"spawned_node_id": None, "blocked": False, "directive": ""}

    if "➔" in raw_dest or "->" in raw_dest:
        sep = "➔" if "➔" in raw_dest else "->"
        parts = [p.strip() for p in raw_dest.split(sep) if p.strip()]
        leaf_name = parts[-1] if parts else raw_dest
    else:
        leaf_name = raw_dest.strip()

    if len(leaf_name) < 3:
        return {"spawned_node_id": None, "blocked": False, "directive": ""}

    # Before blocking or spawning, check if raw_dest or leaf_name resolves to an existing node in world_nodes
    if session_id:
        resolved_existing = db.resolve_node_id_from_location(session_id, raw_dest) or db.resolve_node_id_from_location(session_id, leaf_name)
        if resolved_existing:
            return {"spawned_node_id": resolved_existing, "blocked": False, "directive": ""}

    import scenario_data
    from mechanics.world.mobility import is_campus_scenario
    is_closed_campus = bool(is_campus_scenario(scen_key) or scenario_data.is_non_combat_scenario(scen_key))

    if is_closed_campus:
        valid_exits = get_adjacent_reachable_exits(session_id, current_node_id)
        exits_str = ", ".join(valid_exits) if valid_exits else "seeded campus facilities"
        curr_node = db.get_world_node(session_id, current_node_id) if (session_id and current_node_id) else None
        curr_nm = (curr_node.get("name") if curr_node else "current area") or "current area"
        return {
            "spawned_node_id": None,
            "blocked": True,
            "directive": (
                f"[STAGE DIRECTION — INVALID EXIT]: '{leaf_name}' is not a valid reachable destination from {curr_nm}. "
                f"Do NOT change location (0 minutes elapsed). Valid reachable exits: {exits_str}."
            ),
        }

    if not session_id or not current_node_id:
        return {"spawned_node_id": None, "blocked": False, "directive": ""}

    curr_node = db.get_world_node(session_id, current_node_id)
    if not curr_node:
        return {"spawned_node_id": None, "blocked": False, "directive": ""}

    display_name = leaf_name if leaf_name[0].isupper() else leaf_name.title()
    slug = re.sub(r"[^a-z0-9]+", "_", display_name.lower()).strip("_")[:36]
    if not slug:
        return {"spawned_node_id": None, "blocked": False, "directive": ""}
    new_node_id = f"dyn_{slug}"

    existing = db.get_world_node(session_id, new_node_id)
    if existing:
        return {"spawned_node_id": new_node_id, "blocked": False, "directive": ""}

    curr_type = str(curr_node.get("node_type") or "FACILITY").upper()
    if curr_type == "ZONE":
        parent_id = current_node_id
        new_type = "FACILITY"
    elif curr_type == "FACILITY":
        parent_id = current_node_id
        new_type = "ROOM"
    else:
        parent_id = curr_node.get("parent_id") or current_node_id
        new_type = "ROOM"

    db.save_world_node(
        session_id=session_id,
        node_id=new_node_id,
        parent_id=parent_id,
        name=display_name,
        node_type=new_type,
        category=str(curr_node.get("category") or "exploration"),
        privacy_level="public",
        is_enclosed=1,
        access_tier="open",
        is_dynamic=1,
    )
    db.save_world_edge(
        session_id=session_id,
        from_node_id=current_node_id,
        to_node_id=new_node_id,
        travel_minutes=3,
        edge_type="pathway",
        is_bidirectional=1,
    )
    return {
        "spawned_node_id": new_node_id,
        "blocked": False,
        "directive": f"[STAGE DIRECTION — EXPLORATION DISCOVERY]: Discovered and entered '{display_name}' (3m travel).",
    }
