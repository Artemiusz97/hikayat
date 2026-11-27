from __future__ import annotations
"""In-memory and SQLite hierarchy, realm rule, portal discovery, and distance helpers."""

from collections import defaultdict
import heapq
import json
from typing import Any, Iterable, Mapping, Optional

import db

from .constants import DEFAULT_REALM_RULES, PORTAL_EDGE_TYPES


def parse_node_state_json(node: Mapping[str, Any] | None) -> dict[str, Any]:
    """Safely decodes world_nodes.state_json into a dictionary."""
    if not isinstance(node, Mapping):
        return {}
    raw = node.get("state_json")
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return dict(parsed) if isinstance(parsed, Mapping) else {}
        except Exception:
            return {}
    return {}


def get_realm_rules(realm_node: Mapping[str, Any] | None) -> dict[str, Any]:
    """Returns normalized realm rules merged with DEFAULT_REALM_RULES."""
    rules = dict(DEFAULT_REALM_RULES)
    if not isinstance(realm_node, Mapping):
        return rules
    parsed = parse_node_state_json(realm_node)
    for k, v in parsed.items():
        if v is not None:
            rules[k] = v
    if "is_hidden" in realm_node and realm_node.get("is_hidden") is not None:
        rules["is_hidden"] = bool(realm_node.get("is_hidden"))
    if rules.get("is_hidden") and "discovered" not in parsed:
        rules["discovered"] = False
    try:
        rules["time_scale"] = float(rules.get("time_scale", 1.0))
    except (TypeError, ValueError):
        rules["time_scale"] = 1.0
    return rules


def get_node_ancestors_in_memory(
    node_id: str,
    nodes_by_id: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Walks parent_id pointers upward in memory with cycle protection."""
    nid = str(node_id or "").strip()
    if not nid or not isinstance(nodes_by_id, Mapping):
        return []
    curr = nodes_by_id.get(nid)
    if not curr:
        return []
    ancestors: list[dict[str, Any]] = []
    visited: set[str] = {nid}
    while curr and curr.get("parent_id"):
        pid = str(curr["parent_id"])
        if pid in visited:
            break
        visited.add(pid)
        p_node = nodes_by_id.get(pid)
        if not p_node:
            break
        ancestors.append(dict(p_node))
        curr = p_node
    return ancestors


def get_node_hierarchy_roles_in_memory(
    node_id: str,
    nodes_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Optional[dict[str, Any]]]:
    """
    Role-based hierarchy resolver supporting variable-depth graphs:
      - REALM -> ZONE -> FACILITY -> ROOM
      - REALM -> FACILITY -> ROOM
      - REALM -> ROOM
      - Legacy ZONE -> FACILITY -> ROOM (no REALM)
    Returns {"realm": ..., "zone": ..., "facility": ..., "room": ...}.
    """
    roles: dict[str, Optional[dict[str, Any]]] = {
        "realm": None,
        "zone": None,
        "facility": None,
        "room": None,
    }
    nid = str(node_id or "").strip()
    if not nid or not isinstance(nodes_by_id, Mapping):
        return roles
    target = nodes_by_id.get(nid)
    if not target:
        return roles
    chain = [dict(target)] + get_node_ancestors_in_memory(nid, nodes_by_id)
    for item in chain:
        ntype = str(item.get("node_type") or "").strip().upper()
        if ntype == "ROOM" and roles["room"] is None:
            roles["room"] = item
        elif ntype == "FACILITY" and roles["facility"] is None:
            roles["facility"] = item
        elif ntype == "ZONE" and roles["zone"] is None:
            roles["zone"] = item
        elif ntype == "REALM" and roles["realm"] is None:
            roles["realm"] = item
    return roles


def format_tiered_location_in_memory(
    node_id: str,
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    fallback_zone: str = "World Region",
) -> str:
    """Formats a node_id into canonical 'Zone ➔ Facility ➔ Room' strictly in memory."""
    nid = str(node_id or "").strip()
    if not nid or not isinstance(nodes_by_id, Mapping):
        return ""
    target = nodes_by_id.get(nid)
    if not target:
        return ""

    roles = get_node_hierarchy_roles_in_memory(nid, nodes_by_id)
    realm_node = roles.get("realm")
    zone_node = roles.get("zone")
    fac_node = roles.get("facility")
    n_type = str(target.get("node_type") or "ROOM").upper()

    if n_type == "REALM":
        for child_type in ("ZONE", "FACILITY", "ROOM"):
            child = next(
                (
                    n for n in nodes_by_id.values()
                    if str(n.get("node_type") or "").upper() == child_type
                    and str(n.get("parent_id") or "") == nid
                ),
                None,
            )
            if child:
                return format_tiered_location_in_memory(
                    str(child["node_id"]),
                    nodes_by_id,
                    fallback_zone=fallback_zone,
                )
        r_name = str(target.get("name") or fallback_zone)
        return f"{r_name} ➔ {r_name} ➔ Central Area"

    if n_type == "ZONE":
        z_name = str(target.get("name") or fallback_zone)
        fac = next(
            (
                n for n in nodes_by_id.values()
                if str(n.get("node_type") or "").upper() == "FACILITY"
                and str(n.get("parent_id") or "") == nid
            ),
            None,
        )
        p_name = str(fac.get("name") or z_name) if fac else z_name
        parent_for_room = str(fac["node_id"]) if fac else nid
        child_room = next(
            (
                n for n in nodes_by_id.values()
                if str(n.get("node_type") or "").upper() == "ROOM"
                and str(n.get("parent_id") or "") == parent_for_room
                and str(n.get("name") or "").strip().lower() != "main area"
            ),
            None,
        )
        s_name = str(child_room["name"]) if child_room else "Main Area"
        return f"{z_name} ➔ {p_name} ➔ {s_name}"

    if n_type == "FACILITY":
        z_name = str(
            (zone_node or {}).get("name")
            or (realm_node or {}).get("name")
            or fallback_zone
        )
        p_name = str(target.get("name") or nid)
        child_room = next(
            (
                n for n in nodes_by_id.values()
                if str(n.get("node_type") or "").upper() == "ROOM"
                and str(n.get("parent_id") or "") == nid
                and str(n.get("name") or "").strip().lower() != "main area"
            ),
            None,
        )
        s_name = str(child_room["name"]) if child_room else "Main Area"
        return f"{z_name} ➔ {p_name} ➔ {s_name}"

    z_name = str(
        (zone_node or {}).get("name")
        or (realm_node or {}).get("name")
        or (fac_node or {}).get("name")
        or fallback_zone
    )
    p_name = str(
        (fac_node or {}).get("name")
        or (realm_node or {}).get("name")
        or target.get("name")
        or nid
    )
    s_name = str(target.get("name") or "Main Area").strip() or "Main Area"
    return f"{z_name} ➔ {p_name} ➔ {s_name}"


_format_tiered_location_in_memory = format_tiered_location_in_memory


def get_node_realm_in_memory(
    node_id: str,
    nodes_by_id: Mapping[str, Mapping[str, Any]],
) -> Optional[dict[str, Any]]:
    """Returns the owning REALM node dict for node_id (or None if unrooted)."""
    roles = get_node_hierarchy_roles_in_memory(node_id, nodes_by_id)
    return roles.get("realm")


def get_node_realm_id_in_memory(
    node_id: str,
    nodes_by_id: Mapping[str, Mapping[str, Any]],
) -> str:
    """Returns the owning REALM node_id for node_id (or '' if none)."""
    realm = get_node_realm_in_memory(node_id, nodes_by_id)
    return str(realm.get("node_id") or "") if isinstance(realm, Mapping) else ""


def is_node_or_realm_hidden_in_memory(
    node_id: str,
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    discovered_nodes: Optional[set[str]] = None,
) -> bool:
    """Returns True if node_id or ANY ancestor (FACILITY/ZONE/REALM) is hidden and undiscovered."""
    nid = str(node_id or "").strip()
    if not nid or nid not in nodes_by_id:
        return False
    disc = discovered_nodes or set()
    node = nodes_by_id[nid]
    chain = [node] + get_node_ancestors_in_memory(nid, nodes_by_id)
    for item in chain:
        item_id = str(item.get("node_id") or "")
        st = parse_node_state_json(item)
        item_hidden = bool(item.get("is_hidden") == 1 or st.get("is_hidden"))
        if not item_hidden:
            continue
        if st.get("discovered") is True and not st.get("is_hidden"):
            continue
        if item_id in disc and not st.get("is_hidden"):
            continue
        return True
    return False


def is_at_access_point_in_memory(
    curr_node_id: str,
    ap_node_id: str,
    nodes_by_id: Mapping[str, Mapping[str, Any]],
) -> bool:
    """Returns True when curr_node_id is physically standing at ap_node_id (or inside ap_node_id if FACILITY)."""
    c_nid = str(curr_node_id or "").strip()
    a_nid = str(ap_node_id or "").strip()
    if not c_nid or not a_nid:
        return False
    if c_nid == a_nid:
        return True
    c_node = nodes_by_id.get(c_nid)
    a_node = nodes_by_id.get(a_nid)
    if c_node and a_node and str(a_node.get("node_type") or "").upper() == "FACILITY":
        if str(c_node.get("parent_id") or "") == a_nid:
            return True
    return False


def get_primary_realm_in_memory(
    nodes_by_id: Mapping[str, Mapping[str, Any]],
) -> Optional[dict[str, Any]]:
    """Returns the primary REALM node dict, or first REALM node if none flagged."""
    first_realm: Optional[dict[str, Any]] = None
    for n in nodes_by_id.values():
        if str(n.get("node_type") or "").upper() != "REALM":
            continue
        if first_realm is None:
            first_realm = dict(n)
        rules = get_realm_rules(n)
        if rules.get("is_primary_realm"):
            return dict(n)
    return first_realm


def get_portal_edges_in_memory(
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    edges: Iterable[Mapping[str, Any]],
    *,
    from_realm_id: str = "",
    include_hidden: bool = False,
) -> list[dict[str, Any]]:
    """
    Collects cross-realm portal edges (both directions for bidirectional edges)
    with portal metadata, honoring fog-of-war visibility unless include_hidden=True.
    """
    results: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for e in (edges or ()):
        etype = str(e.get("edge_type") or "").strip()
        if etype not in PORTAL_EDGE_TYPES:
            continue
        u = str(e.get("from_node_id") or "").strip()
        v = str(e.get("to_node_id") or "").strip()
        if not u or not v:
            continue
        pairs: list[tuple[str, str]] = [(u, v)]
        if int(e.get("is_bidirectional", 1) or 0) != 0:
            pairs.append((v, u))
        for src, dst in pairs:
            if (src, dst) in seen_pairs:
                continue
            src_realm = get_node_realm_id_in_memory(src, nodes_by_id)
            dst_realm = get_node_realm_id_in_memory(dst, nodes_by_id)
            if not src_realm or not dst_realm or src_realm == dst_realm:
                continue
            if from_realm_id and src_realm != from_realm_id:
                continue
            src_node = nodes_by_id.get(src) or {}
            dst_node = nodes_by_id.get(dst) or {}
            dst_realm_node = nodes_by_id.get(dst_realm) or {}
            dst_rules = get_realm_rules(dst_realm_node)
            src_state = parse_node_state_json(src_node)
            portal_meta_map = src_state.get("portals") if isinstance(src_state.get("portals"), Mapping) else {}
            p_meta = portal_meta_map.get(dst) if isinstance(portal_meta_map.get(dst), Mapping) else {}
            is_hidden_portal = bool(p_meta.get("is_hidden_portal"))
            visible_when_target_hidden = bool(p_meta.get("visible_when_target_hidden", not is_hidden_portal))
            target_realm_hidden = bool(dst_rules.get("is_hidden"))
            spirit_side_locked = bool(
                p_meta.get("spirit_side_unlock_only")
                and int(e.get("is_locked") or 0) == 1
                and src_realm != "realm_veiled_spirit_world"
            )
            if not include_hidden:
                if is_hidden_portal or spirit_side_locked:
                    continue
                if target_realm_hidden and not visible_when_target_hidden:
                    continue
                if is_node_or_realm_hidden_in_memory(src, nodes_by_id):
                    continue
            seen_pairs.add((src, dst))
            icon = str(
                p_meta.get("icon")
                or dst_rules.get("portal_icon")
                or ("🚀" if etype in ("ftl_jump", "shuttle_route") else "🌀")
            )
            results.append({
                "from_node_id": src,
                "from_node_name": str(src_node.get("name") or src),
                "from_realm_id": src_realm,
                "to_node_id": dst,
                "to_node_name": str(dst_node.get("name") or dst),
                "target_realm_id": dst_realm,
                "target_realm_name": str(dst_realm_node.get("name") or dst_realm),
                "target_realm_hidden": target_realm_hidden,
                "edge_type": etype,
                "travel_minutes": max(1, int(e.get("travel_minutes") or 5)),
                "is_locked": bool(int(e.get("is_locked") or 0)),
                "lock_key_item": str(e.get("lock_key_item") or ""),
                "skill_check_type": str(e.get("skill_check_type") or ""),
                "skill_check_dc": int(e.get("skill_check_dc") or 0),
                "label": str(p_meta.get("label") or ""),
                "icon": icon,
                "is_hidden_portal": is_hidden_portal,
                "require_explicit_portal_unlock": bool(p_meta.get("require_explicit_portal_unlock")),
                "veil_village_key": str(p_meta.get("veil_village_key") or ""),
                "spirit_side_unlock_only": bool(p_meta.get("spirit_side_unlock_only")),
            })
    return results


def _load_nodes_map(session_id: int) -> dict[str, dict[str, Any]]:
    if not session_id:
        return {}
    rows = db.get_session_world_nodes(session_id) or []
    return {str(r["node_id"]): dict(r) for r in rows if isinstance(r, Mapping) and r.get("node_id")}


def get_node_realm(session_id: int, node_id: str) -> Optional[dict[str, Any]]:
    """Returns the owning REALM node dict for a node_id in SQLite."""
    if not session_id or not node_id:
        return None
    nodes_by_id = _load_nodes_map(session_id)
    return get_node_realm_in_memory(node_id, nodes_by_id)


def get_node_realm_id(session_id: int, node_id: str) -> str:
    """Returns the owning REALM node_id for a node_id in SQLite (or '')."""
    realm = get_node_realm(session_id, node_id)
    return str(realm.get("node_id") or "") if isinstance(realm, Mapping) else ""


def get_session_realms(session_id: int, *, include_hidden: bool = True) -> list[dict[str, Any]]:
    """Returns all REALM nodes in a session with merged rules."""
    if not session_id:
        return []
    nodes = db.get_session_world_nodes(session_id) or []
    realms: list[dict[str, Any]] = []
    for n in nodes:
        if str(n.get("node_type") or "").upper() != "REALM":
            continue
        rules = get_realm_rules(n)
        if not include_hidden and rules.get("is_hidden"):
            continue
        entry = dict(n)
        entry["rules"] = rules
        realms.append(entry)
    return realms


def get_realm_rules_for_node(session_id: int, node_id: str) -> dict[str, Any]:
    """Returns the owning realm's rules dict for node_id (defaults when unrooted)."""
    realm = get_node_realm(session_id, node_id) if (session_id and node_id) else None
    return get_realm_rules(realm)


def get_realm_time_scale(session_id: int, node_id: Optional[str] = None) -> float:
    """Returns the active realm's time_scale multiplier (defaults to 1.0)."""
    if not session_id:
        return 1.0
    nid = str(node_id or "").strip()
    if not nid:
        sess = db.get_session(session_id)
        nid = str((sess or {}).get("current_node_id") or "").strip()
    if not nid:
        return 1.0
    rules = get_realm_rules_for_node(session_id, nid)
    try:
        return float(rules.get("time_scale", 1.0))
    except (TypeError, ValueError):
        return 1.0


def check_realm_comms_available(session_id: int, node_id: Optional[str] = None) -> dict[str, Any]:
    """Checks whether live external communications (Phone DMs, Feed, Realty, Recall) work in the current realm."""
    if not session_id:
        return {
            "available": True,
            "comms_isolated": False,
            "supports_spirit_relay": False,
            "spirit_relay_active": False,
            "realm_id": "",
            "realm_name": "",
            "reason": "",
        }
    nid = str(node_id or "").strip()
    if not nid:
        sess = db.get_session(session_id)
        nid = str((sess or {}).get("current_node_id") or "").strip()
        if not nid and sess and sess.get("current_location"):
            nid = str(db.resolve_node_id_from_location(session_id, sess["current_location"]) or "")
    realm = get_node_realm(session_id, nid) if nid else None
    if not realm:
        return {
            "available": True,
            "comms_isolated": False,
            "supports_spirit_relay": False,
            "spirit_relay_active": False,
            "realm_id": "",
            "realm_name": "",
            "reason": "",
        }
    rules = get_realm_rules(realm)
    isolated = bool(rules.get("comms_isolated"))
    supports_spirit_relay = bool(str(rules.get("realm_kind") or "").strip().lower() == "spirit_world")
    r_name = str(realm.get("name") or realm.get("node_id") or "Unknown Realm")
    reason = (
        f"No Signal — Isolated Realm: Live communications are unavailable while inside {r_name}."
        if isolated
        else ""
    )
    return {
        "available": not isolated,
        "comms_isolated": isolated,
        "supports_spirit_relay": supports_spirit_relay,
        "spirit_relay_active": bool(isolated and supports_spirit_relay),
        "realm_id": str(realm.get("node_id") or ""),
        "realm_name": r_name,
        "reason": reason,
    }


def _compute_intra_realm_distances(
    from_node_id: str,
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    edges: Iterable[Mapping[str, Any]],
    realm_id: str,
) -> dict[str, int]:
    """Dijkstra from from_node_id staying strictly inside realm_id."""
    adj: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for e in (edges or ()):
        u = str(e.get("from_node_id") or "")
        v = str(e.get("to_node_id") or "")
        if not u or not v:
            continue
        if get_node_realm_id_in_memory(u, nodes_by_id) != realm_id:
            continue
        if get_node_realm_id_in_memory(v, nodes_by_id) != realm_id:
            continue
        w = max(1, int(e.get("travel_minutes") or 2))
        adj[u].append((v, w))
        if int(e.get("is_bidirectional", 1) or 0) != 0:
            adj[v].append((u, w))
    for nid, n in nodes_by_id.items():
        pid = str(n.get("parent_id") or "")
        if pid and str(n.get("node_type") or "").upper() == "ROOM":
            p_node = nodes_by_id.get(pid)
            if p_node and str(p_node.get("node_type") or "").upper() == "FACILITY":
                if get_node_realm_id_in_memory(nid, nodes_by_id) == realm_id:
                    adj[pid].append((nid, 1))
                    adj[nid].append((pid, 1))
    dist: dict[str, int] = {from_node_id: 0}
    pq: list[tuple[int, str]] = [(0, from_node_id)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, 10**9):
            continue
        for v, w in adj.get(u, ()):
            nd = d + w
            if nd < dist.get(v, 10**9):
                dist[v] = nd
                heapq.heappush(pq, (nd, v))
    return dist


def find_nearest_access_point_for_realm(
    session_id: int,
    from_node_id: str,
    target_realm_id: str,
    *,
    include_hidden: bool = False,
) -> Optional[dict[str, Any]]:
    """
    Finds the nearest Access Point node in from_node_id's current realm
    that connects to target_realm_id (direct portal edge, or mobile vessel dock/bridge).
    """
    if not session_id or not from_node_id or not target_realm_id:
        return None
    nodes_by_id = _load_nodes_map(session_id)
    if from_node_id not in nodes_by_id:
        return None
    curr_realm_id = get_node_realm_id_in_memory(from_node_id, nodes_by_id)
    if not curr_realm_id or curr_realm_id == target_realm_id:
        return None
    edges = db.get_session_world_edges(session_id) or []
    portals = get_portal_edges_in_memory(
        nodes_by_id,
        edges,
        from_realm_id=curr_realm_id,
        include_hidden=include_hidden,
    )
    candidates = [p for p in portals if p["target_realm_id"] == target_realm_id]
    if not candidates:
        curr_realm_node = nodes_by_id.get(curr_realm_id)
        curr_rules = get_realm_rules(curr_realm_node)
        target_rules = get_realm_rules(nodes_by_id.get(target_realm_id))
        if curr_rules.get("is_mobile_vessel") and curr_rules.get("bridge_node_id") and not target_rules.get("is_hidden"):
            bridge_nid = str(curr_rules["bridge_node_id"])
            if bridge_nid in nodes_by_id:
                candidates.append({
                    "from_node_id": bridge_nid,
                    "from_node_name": str(nodes_by_id[bridge_nid].get("name") or bridge_nid),
                    "to_node_id": target_rules.get("dock_node_id") or "",
                    "target_realm_id": target_realm_id,
                    "target_realm_name": str((nodes_by_id.get(target_realm_id) or {}).get("name") or target_realm_id),
                    "edge_type": "ftl_jump",
                    "icon": "🚀",
                    "is_bridge_jump": True,
                })
        if not candidates and target_rules.get("is_mobile_vessel") and curr_rules.get("dock_node_id"):
            dock_nid = str(curr_rules["dock_node_id"])
            if dock_nid in nodes_by_id:
                candidates.append({
                    "from_node_id": dock_nid,
                    "from_node_name": str(nodes_by_id[dock_nid].get("name") or dock_nid),
                    "to_node_id": str(target_rules.get("airlock_node_id") or ""),
                    "target_realm_id": target_realm_id,
                    "target_realm_name": str((nodes_by_id.get(target_realm_id) or {}).get("name") or target_realm_id),
                    "edge_type": "shuttle_route",
                    "icon": "🚀",
                    "is_recall_dock": True,
                })
    if not candidates:
        return None
    dist = _compute_intra_realm_distances(from_node_id, nodes_by_id, edges, curr_realm_id)
    candidates.sort(key=lambda c: dist.get(c["from_node_id"], 10**9))
    best = dict(candidates[0])
    best["node_id"] = best["from_node_id"]
    best["access_point_node_id"] = best["from_node_id"]
    best["access_point_name"] = best.get("from_node_name") or best["from_node_id"]
    best["travel_minutes_to_ap"] = dist.get(best["from_node_id"], 5)
    return best
