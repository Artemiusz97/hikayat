from __future__ import annotations

import db
from fastapi import (
    APIRouter,
    Request,
)
from db import adb
from mechanics.system.concurrency import distributed_session_lock
from ..security import verify_session_participant

router = APIRouter()


def _inspect_location_seeding(
    session_id: int,
    scen_key: str,
    current_loc: str,
    char_name: str,
    *,
    check_missing_wp_table: bool = False,
) -> tuple[dict, list[dict], str, str, list[str], bool]:
    """Read-only collection of unseeded waypoint, commitment, and current-location targets."""
    from mechanics.system.commitments_engine import get_active_commitments
    from mechanics.world.locations import sanitize_location_target
    from mechanics.world.locations.realms import get_node_realm_id_in_memory

    needs_wp_seed = False
    if check_missing_wp_table:
        with db.get_conn() as conn:
            missing_wp_row = conn.execute(
                """SELECT 1 FROM quests q
                   WHERE q.session_id = ?
                     AND LOWER(COALESCE(q.status, '')) IN ('active', 'in progress')
                     AND NOT EXISTS (
                         SELECT 1 FROM quest_waypoints qw
                         WHERE qw.session_id = q.session_id AND qw.quest_id = q.quest_id
                     )
                   LIMIT 1""",
                (session_id,),
            ).fetchone()
            needs_wp_seed = bool(missing_wp_row)

    existing_loc_strs: set[str] = set()
    for _lr in (db.get_session_locations(session_id) or []):
        if not isinstance(_lr, dict):
            continue
        _rz = str(_lr.get("zone_name") or "").strip()
        _rp = str(_lr.get("primary_name") or "").strip()
        _rs = str(_lr.get("sub_name") or "").strip()
        if _rz and _rp:
            existing_loc_strs.add(f"{_rz} ➔ {_rp}".lower())
            if _rs:
                existing_loc_strs.add(f"{_rz} ➔ {_rp} ➔ {_rs}".lower())
    processed_loc_keys: set[str] = set()
    pending_seed_targets: list[str] = []

    def _is_already_seeded_raw(loc_candidate: str) -> bool:
        norm_cmp = str(loc_candidate or "").replace("->", "➔").strip().lower()
        return bool(norm_cmp) and (norm_cmp in processed_loc_keys or norm_cmp in existing_loc_strs)

    def _queue_loc_seed(loc_candidate: str) -> None:
        norm = str(loc_candidate or "").strip()
        if not norm:
            return
        norm_cmp = norm.replace("->", "➔").strip().lower()
        if norm_cmp in processed_loc_keys or norm_cmp in existing_loc_strs:
            return
        processed_loc_keys.add(norm_cmp)
        pending_seed_targets.append(norm)

    pre_sess = db.get_session(session_id) or {}
    pre_curr_nid = str(pre_sess.get("current_node_id") or "").strip()
    pre_nodes = db.get_session_world_nodes(session_id) or []
    pre_nodes_by_id = {str(n.get("node_id") or ""): n for n in pre_nodes if isinstance(n, dict) and n.get("node_id")}
    pre_node_ids = set(pre_nodes_by_id.keys())
    pre_curr_realm_id = get_node_realm_id_in_memory(pre_curr_nid, pre_nodes_by_id) if pre_curr_nid else ""

    resolved_loc_cache: dict[tuple[str, bool], str] = {}

    def _cached_resolve_nid(loc_str: str, *, prefer_facility: bool = True) -> str:
        key = (str(loc_str or "").strip(), bool(prefer_facility))
        if not key[0] or not pre_nodes:
            return ""
        if key not in resolved_loc_cache:
            resolved_loc_cache[key] = str(
                db.resolve_node_id_from_location(
                    session_id,
                    key[0],
                    prefer_facility=prefer_facility,
                    preferred_realm_id=pre_curr_realm_id or None,
                )
                or ""
            )
        return resolved_loc_cache[key]

    def _target_exists_in_graph(target_nid: str, target_loc: str) -> bool:
        if target_nid and str(target_nid) in pre_node_ids:
            return True
        if target_loc and pre_nodes and _cached_resolve_nid(target_loc, prefer_facility=True):
            return True
        return False

    def _is_off_realm_target(target_nid: str, target_loc: str) -> bool:
        if not pre_curr_realm_id:
            return False
        cand_nid = str(target_nid or "").strip() or (
            _cached_resolve_nid(target_loc, prefer_facility=False)
            if target_loc and pre_nodes
            else ""
        )
        if cand_nid and cand_nid in pre_nodes_by_id:
            t_realm = get_node_realm_id_in_memory(cand_nid, pre_nodes_by_id)
            if t_realm and t_realm != pre_curr_realm_id:
                return True
        return False

    for wp in (db.get_all_session_active_waypoints(session_id) or []):
        target_loc = (wp.get("target_location") or "").strip()
        target_nid = str(wp.get("target_node_id") or "").strip()
        if not target_loc or _is_already_seeded_raw(target_loc) or _is_off_realm_target(target_nid, target_loc) or _target_exists_in_graph(target_nid, target_loc):
            continue
        clean_target = sanitize_location_target(target_loc, session_id=session_id, scen_key=scen_key, char_name=char_name)
        _queue_loc_seed(clean_target)

    for appt in (get_active_commitments(session_id, commitment_type="rendezvous", limit=25) or []):
        appt_loc = (appt.get("target_location") or appt.get("rendezvous_location") or "").strip()
        appt_nid = str(appt.get("target_node_id") or "").strip()
        if not appt_loc or _is_already_seeded_raw(appt_loc) or _is_off_realm_target(appt_nid, appt_loc) or _target_exists_in_graph(appt_nid, appt_loc):
            continue
        clean_appt_loc = sanitize_location_target(appt_loc, session_id=session_id, scen_key=scen_key, char_name=char_name)
        _queue_loc_seed(clean_appt_loc)

    if current_loc and not _target_exists_in_graph("", current_loc):
        _queue_loc_seed(current_loc)

    return pre_sess, pre_nodes, pre_curr_nid, pre_curr_realm_id, pending_seed_targets, needs_wp_seed


def _build_locations_payload(session_id: int, scen_key: str, current_loc: str, char_name: str) -> dict:
    from mechanics.world.locations import (
        build_access_eval_context,
        build_location_occupancy_index,
        format_travel_eta_tag,
        get_node_effective_access_info,
        get_zone_summary_tree,
        parse_tiered_location,
        process_llm_location_update,
    )
    from mechanics.world.waypoints import ensure_quest_waypoints_exist

    pre_sess: dict | None = None
    pre_nodes: list[dict] | None = None
    seeded_any = False
    if session_id and not db.is_in_readonly_uow():
        try:
            ensure_quest_waypoints_exist(session_id)
        except Exception:
            pass

        pre_sess, pre_nodes, pre_curr_nid, pre_curr_realm_id, pending_seed_targets, _ = _inspect_location_seeding(
            session_id, scen_key, current_loc, char_name, check_missing_wp_table=False
        )

        if pending_seed_targets:
            with db.UnitOfWork():
                cur_sess_uow = db.get_session(session_id) or {}
                cur_nid_uow = str(cur_sess_uow.get("current_node_id") or "").strip()
                realm_alive = (
                    (not pre_curr_realm_id)
                    or (db.get_world_node(session_id, pre_curr_realm_id) is not None)
                )
                if cur_nid_uow == pre_curr_nid and realm_alive:
                    seeded_any = True
                    for _seed_loc in pending_seed_targets:
                        process_llm_location_update(
                            session_id,
                            _seed_loc,
                            scen_key,
                            char_name=char_name,
                            preferred_realm_id=pre_curr_realm_id,
                        )

    from mechanics.world.locations.realms import (
        _format_tiered_location_in_memory,
        build_session_realm_summary,
        find_nearest_access_point_for_realm,
        get_node_realm_id_in_memory,
        get_realm_rules,
    )
    session = pre_sess if (not seeded_any and pre_sess is not None) else db.get_session(session_id)
    curr_node_id = session.get("current_node_id") if session else None
    all_nodes = (
        pre_nodes
        if (not seeded_any and pre_nodes is not None)
        else (db.get_session_world_nodes(session_id) if session_id else [])
    )
    nodes_by_id = {str(n["node_id"]): n for n in all_nodes if isinstance(n, dict) and n.get("node_id")}
    all_edges = db.get_session_world_edges(session_id) if session_id else []

    resolved_loc_nid = (
        db.resolve_node_id_from_location(session_id, current_loc, prefer_facility=False)
        if (session_id and current_loc and not curr_node_id)
        else None
    )
    eff_curr_node_id = curr_node_id or resolved_loc_nid
    realm_summary = build_session_realm_summary(
        session_id, eff_curr_node_id, nodes=all_nodes, edges=all_edges
    )
    curr_realm_info = realm_summary.get("current_realm")
    curr_realm_id = str((curr_realm_info or {}).get("realm_id") or "").strip()

    zones_summary = get_zone_summary_tree(
        session_id,
        scen_key,
        current_loc=current_loc,
        char_name=char_name,
        ensure_waypoints=False,
        realm_id=curr_realm_id or None,
    )
    curr_z, curr_p, curr_sub = (
        parse_tiered_location(current_loc, scen_key, session_id=session_id, char_name=char_name)
        if current_loc else ("", "", "")
    )
    fac_zone_id_by_name_lower: dict[str, str] = {}
    for _wn in all_nodes:
        if not isinstance(_wn, dict):
            continue
        _wn_id = _wn.get("node_id")
        if curr_realm_id and _wn_id and get_node_realm_id_in_memory(str(_wn_id), nodes_by_id) != curr_realm_id:
            continue
        if _wn_id and _wn.get("node_type") in ("FACILITY", "ZONE"):
            _wn_nl = str(_wn.get("name") or "").strip().lower()
            if _wn_nl:
                fac_zone_id_by_name_lower.setdefault(_wn_nl, str(_wn_id))
    curr_node = (
        nodes_by_id.get(str(eff_curr_node_id))
        or (db.get_world_node(session_id, eff_curr_node_id) if (session_id and eff_curr_node_id) else None)
    )

    def _is_transit_hub_in_mem(nid: str | None) -> bool:
        if not nid:
            return False
        node_obj = nodes_by_id.get(str(nid))
        if not node_obj:
            return False
        if node_obj.get("is_transit_hub"):
            return True
        p_id = node_obj.get("parent_id")
        if p_id and str(p_id) in nodes_by_id:
            return bool(nodes_by_id[str(p_id)].get("is_transit_hub"))
        return False

    outgoing_edges = db.get_outgoing_edges(session_id, eff_curr_node_id) if (session_id and eff_curr_node_id) else []
    adjacent_node_ids = {e["to_node_id"] for e in outgoing_edges}
    adjacent_parent_ids = {
        str(nodes_by_id[str(nid)]["parent_id"])
        for nid in adjacent_node_ids
        if str(nid) in nodes_by_id and nodes_by_id[str(nid)].get("parent_id")
    }
    player_at_transit_hub = _is_transit_hub_in_mem(eff_curr_node_id) if (session_id and eff_curr_node_id) else False

    fallback_eval_ctx: dict | None = None
    fallback_occ_by_node: dict[str, dict] | None = None
    curr_day: int | None = None
    curr_min: int | None = None

    player_restrained = False
    if session_id:
        try:
            from mechanics.social.physical_state import find_player_actor_key, is_actor_restrained
            phys_map = db.get_session_physical_state(session_id)
            if phys_map and isinstance(phys_map.get("actors"), dict):
                pk_m = find_player_actor_key(phys_map["actors"], session_id=session_id)
                if pk_m and is_actor_restrained(phys_map["actors"].get(pk_m) or {}):
                    player_restrained = True
        except Exception:
            pass

    from mechanics.world.waypoints.core import _classify_waypoint_marker
    seen_dest_keys: set[tuple[str, str]] = set()
    enriched_zones = []
    active_quest_destinations = []
    for z in zones_summary:
        z_copy = dict(z)
        z_name = z_copy.get("zone_name", "")
        is_same_zone = bool(curr_z and curr_z.lower() == z_name.lower())
        primaries = []
        for p in z_copy.get("primary_locations", []):
            p_copy = dict(p)
            p_copy["is_current_place"] = bool(
                is_same_zone and curr_p and curr_p.lower() == (p_copy.get("name") or "").lower()
            )

            p_node_id = p_copy.get("node_id") or ""
            if not p_node_id:
                p_nm_raw = str(p_copy.get("name") or "")
                if p_nm_raw and not any(sep in p_nm_raw for sep in ("->", "➔", ">", "/")):
                    p_node_id = fac_zone_id_by_name_lower.get(p_nm_raw.strip().lower(), "")
                if not p_node_id:
                    p_node_id = db.resolve_node_id_from_location(
                        session_id,
                        f"{z_name} ➔ {p_nm_raw}",
                        prefer_facility=True,
                        preferred_realm_id=curr_realm_id,
                    )
            node = nodes_by_id.get(p_node_id) if p_node_id else None
            is_transit_hub = bool(node and node.get("is_transit_hub"))
            can_transit_travel = _is_transit_hub_in_mem(p_node_id) if p_node_id else False
            is_adjacent = bool(
                p_node_id and (
                    p_node_id in adjacent_node_ids or
                    p_node_id in adjacent_parent_ids
                )
            )
            can_travel = bool(
                p_copy["is_current_place"]
                or (not player_restrained and (bool(p_node_id) or is_adjacent or (player_at_transit_hub and can_transit_travel) or not all_nodes))
            )

            if p_copy["is_current_place"]:
                p_copy["travel_tag"] = "Here"
                p_copy["travel_minutes"] = 0
            else:
                eta_tag = p_copy.get("travel_tag")
                if not eta_tag or eta_tag in ("Travel", "Instant Local", "Inter-Zone Travel"):
                    t_mins = int(p_copy.get("travel_minutes") or (4 if is_same_zone else 15))
                    eta_tag = format_travel_eta_tag(t_mins, is_same_zone=is_same_zone, scen_key=scen_key, is_here=False)
                if player_at_transit_hub and can_transit_travel and not is_same_zone and "transit" not in eta_tag.lower():
                    p_copy["travel_tag"] = f"Transit • {eta_tag}"
                else:
                    p_copy["travel_tag"] = eta_tag

            has_precomputed_access = (
                isinstance(p_copy.get("access_badge"), str)
                and "access_tier" in p_copy
                and bool(p_node_id)
                and str(p_copy.get("node_id") or "") == str(p_node_id)
            )
            if has_precomputed_access:
                access_info = {
                    "access_tier": p_copy.get("access_tier", "open"),
                    "status_badge": p_copy.get("access_badge", "Open"),
                    "curfew_active": p_copy.get("is_curfew_active", False),
                    "schedule_locked": p_copy.get("schedule_locked", False),
                    "is_trespassing": p_copy.get("is_trespassing", False),
                    "is_unlocked": p_copy.get("is_unlocked", False),
                    "scene_residue": p_copy.get("scene_residue") or "",
                }
            elif p_node_id:
                if curr_day is None or curr_min is None:
                    curr_day, curr_min, _ = db.get_session_time(session_id)
                if fallback_eval_ctx is None:
                    fallback_eval_ctx = build_access_eval_context(
                        session_id,
                        scen_key=scen_key,
                        session=session if isinstance(session, dict) else None,
                        all_nodes=all_nodes,
                    )
                access_info = get_node_effective_access_info(
                    session_id,
                    p_node_id,
                    current_day=curr_day,
                    current_minute=curr_min,
                    scen_key=scen_key,
                    session=session if isinstance(session, dict) else None,
                    quest_gate_snapshot=fallback_eval_ctx.get("quest_gate_snapshot"),
                    eval_ctx=fallback_eval_ctx,
                )
            else:
                access_info = {}

            has_precomputed_occ = (
                isinstance(p_copy.get("known_npcs_here"), list)
                and "unmet_activity_count" in p_copy
                and bool(p_node_id)
                and str(p_copy.get("node_id") or "") == str(p_node_id)
            )
            if has_precomputed_occ:
                known_npcs_here = p_copy["known_npcs_here"]
                unmet_activity_count = p_copy["unmet_activity_count"]
            elif p_node_id:
                if fallback_occ_by_node is None:
                    if curr_day is None or curr_min is None:
                        curr_day, curr_min, _ = db.get_session_time(session_id)
                    fallback_occ_by_node = build_location_occupancy_index(
                        session_id,
                        scen_key=scen_key,
                        curr_day=curr_day,
                        curr_min=curr_min,
                        node_by_id=nodes_by_id,
                        rendezvous_commitments=None,
                    )
                occ_data = fallback_occ_by_node.get(p_node_id, {"known_npcs": [], "unmet_count": 0})
                known_npcs_here = occ_data["known_npcs"][:3]
                unmet_activity_count = occ_data["unmet_count"]
            else:
                known_npcs_here = []
                unmet_activity_count = 0

            p_copy["node_id"] = p_node_id or ""
            p_copy["is_transit_hub"] = is_transit_hub
            p_copy["is_adjacent"] = is_adjacent
            p_copy["can_travel"] = can_travel
            p_copy["access_tier"] = access_info.get("access_tier", "open")
            p_copy["access_badge"] = access_info.get("status_badge", "Open")
            p_copy["is_curfew_active"] = access_info.get("curfew_active", False)
            p_copy["schedule_locked"] = access_info.get("schedule_locked", False)
            p_copy["is_trespassing"] = access_info.get("is_trespassing", False)
            p_copy["is_unlocked"] = access_info.get("is_unlocked", False)
            p_copy["scene_residue"] = access_info.get("scene_residue") or p_copy.get("scene_residue") or ""
            p_copy["known_npcs_here"] = known_npcs_here
            p_copy["unmet_activity_count"] = unmet_activity_count
            if p_copy.get("is_unpurchased_realty") or str(p_copy.get("access_badge") or "").startswith("For Sale"):
                p_copy["is_unpurchased_realty"] = True
                p_copy["sub_locations"] = []
                p_copy["sub_location_details"] = []
                p_copy["direct_quest_markers"] = list(p_copy.get("quest_markers") or [])
                p_copy["direct_quest_tag"] = p_copy.get("quest_tag", "")
                p_copy["sub_quest_count"] = 0
                p_copy["sub_quest_tags"] = []

            primaries.append(p_copy)

            for sub in (p_copy.get("sub_location_details") or []):
                sub_name = sub.get("name", "")
                sub_val = sub.get("value") or f"{z_name} ➔ {p_copy.get('name', '')} ➔ {sub_name}"
                for qm in (sub.get("quest_markers") or []):
                    m_kind, m_tag = _classify_waypoint_marker(qm)
                    dest_key = (sub_val, qm)
                    if dest_key in seen_dest_keys:
                        continue
                    seen_dest_keys.add(dest_key)
                    active_quest_destinations.append({
                        "zone_name": z_name,
                        "place_name": p_copy.get("name", ""),
                        "sub_name": sub_name,
                        "value": sub_val,
                        "marker": qm,
                        "quest_tag": m_tag or sub.get("quest_tag") or p_copy.get("quest_tag", ""),
                        "quest_kind": m_kind or sub.get("quest_kind") or "",
                        "is_current_place": bool(sub.get("is_current_room")),
                        "is_current_room": bool(sub.get("is_current_room")),
                        "is_transit_hub": bool(sub.get("is_transit_hub") or is_transit_hub),
                        "can_travel": can_travel,
                        "travel_tag": sub.get("travel_tag") or p_copy.get("travel_tag", ""),
                        "travel_minutes": sub.get("travel_minutes", p_copy.get("travel_minutes", 0)),
                    })

            direct_qms = (
                p_copy["direct_quest_markers"]
                if "direct_quest_markers" in p_copy
                else (p_copy.get("quest_markers") or [])
            )
            place_val = p_copy.get("value") or f"{z_name} ➔ {p_copy.get('name', '')}"
            for qm in direct_qms:
                m_kind, m_tag = _classify_waypoint_marker(qm)
                dest_key = (place_val, qm)
                if dest_key in seen_dest_keys:
                    continue
                seen_dest_keys.add(dest_key)
                active_quest_destinations.append({
                    "zone_name": z_name,
                    "place_name": p_copy.get("name", ""),
                    "sub_name": "",
                    "value": place_val,
                    "marker": qm,
                    "quest_tag": m_tag or p_copy.get("direct_quest_tag") or p_copy.get("quest_tag", ""),
                    "quest_kind": m_kind or "",
                    "is_current_place": p_copy["is_current_place"],
                    "is_current_room": False,
                    "is_transit_hub": is_transit_hub,
                    "can_travel": can_travel,
                    "travel_tag": p_copy.get("travel_tag", ""),
                    "travel_minutes": p_copy.get("travel_minutes", 0),
                })
        primaries.sort(
            key=lambda item: (
                0 if item.get("is_current_place") else 1,
                0 if (item.get("quest_markers") or item.get("quest_tag")) else 1,
                (item.get("name") or "").lower(),
            )
        )
        z_copy["primary_locations"] = primaries
        enriched_zones.append(z_copy)

    enriched_zones.sort(
        key=lambda item: (
            0 if item.get("is_current") else 1,
            0 if (item.get("quest_count", 0) > 0 or any("Quest" in t or "Climax" in t or "Bounty" in t or "Meetup" in t for t in (item.get("active_tags") or []))) else 1,
            (item.get("zone_name") or "").lower(),
        )
    )

    realm_gateways = list(realm_summary.get("realm_gateways") or [])
    off_realm_quest_destinations: list[dict] = []
    if curr_realm_id and session_id:
        try:
            raw_wps = db.get_all_session_active_waypoints(session_id) or []
        except Exception:
            raw_wps = []
        off_by_ap: dict[tuple[str, str], dict] = {}
        ap_counts: dict[tuple[str, str], int] = {}
        ap_unique_counts: dict[str, int] = {}
        nearest_ap_cache: dict[str, dict | None] = {}
        for wp in raw_wps:
            wp_nid = str(wp.get("target_node_id") or "").strip()
            wp_loc = str(wp.get("target_location") or "").strip()
            if not wp_nid and wp_loc:
                wp_nid = str(db.resolve_node_id_from_location(session_id, wp_loc, prefer_facility=False) or "")
            if not wp_nid or wp_nid not in nodes_by_id:
                continue
            wp_realm_id = get_node_realm_id_in_memory(wp_nid, nodes_by_id)
            if not wp_realm_id or wp_realm_id == curr_realm_id:
                continue
            wp_r_node = nodes_by_id.get(wp_realm_id)
            wp_r_rules = get_realm_rules(wp_r_node)
            if wp_r_rules.get("is_hidden"):
                continue
            ap_match = next(
                (gw for gw in realm_gateways if gw.get("target_realm_id") == wp_realm_id),
                None,
            )
            if not ap_match and eff_curr_node_id:
                if wp_realm_id not in nearest_ap_cache:
                    nearest_ap_cache[wp_realm_id] = find_nearest_access_point_for_realm(
                        session_id, str(eff_curr_node_id), wp_realm_id
                    )
                near_ap = nearest_ap_cache[wp_realm_id]
                if near_ap:
                    ap_nid_n = str(near_ap.get("access_point_node_id") or near_ap.get("node_id") or "")
                    ap_match = {
                        "access_point_node_id": ap_nid_n,
                        "access_point_name": str(near_ap.get("access_point_name") or ap_nid_n),
                        "access_point_location": _format_tiered_location_in_memory(ap_nid_n, nodes_by_id) if ap_nid_n else "",
                        "target_realm_id": wp_realm_id,
                        "target_realm_name": str((wp_r_node or {}).get("name") or wp_realm_id),
                        "icon": str(near_ap.get("icon") or "🌀"),
                    }
            ap_nid_raw = str((ap_match or {}).get("access_point_node_id") or "")
            ap_nid_key = ap_nid_raw or f"unknown:{wp_realm_id}"
            pair_key = (ap_nid_key, wp_realm_id)
            if ap_nid_raw:
                ap_counts[(ap_nid_raw, wp_realm_id)] = ap_counts.get((ap_nid_raw, wp_realm_id), 0) + 1
                ap_unique_counts[ap_nid_raw] = ap_unique_counts.get(ap_nid_raw, 0) + 1
            group = off_by_ap.setdefault(
                pair_key,
                {
                    "access_point_node_id": ap_nid_raw,
                    "access_point_name": (ap_match or {}).get("access_point_name") or "Access Point",
                    "access_point_location": (ap_match or {}).get("access_point_location") or "",
                    "target_realm_id": wp_realm_id,
                    "target_realm_name": str((wp_r_node or {}).get("name") or wp_realm_id),
                    "icon": (ap_match or {}).get("icon") or "🌀",
                    "objective_count": 0,
                    "markers": [],
                },
            )
            group["objective_count"] += 1
            lbl = str(wp.get("stage_label") or wp.get("quest_title") or "Off-realm objective")
            if lbl not in group["markers"]:
                group["markers"].append(lbl)
        for gw in realm_gateways:
            ap_id = str(gw.get("access_point_node_id") or "")
            t_rid = str(gw.get("target_realm_id") or "")
            if gw.get("action_kind") == "recall_starship":
                gw["off_realm_objective_count"] = 0
            elif ap_id and t_rid and (ap_id, t_rid) in ap_counts:
                gw["off_realm_objective_count"] = ap_counts[(ap_id, t_rid)]
        off_realm_quest_destinations = list(off_by_ap.values())

        # Attach gateway metadata directly onto matching Access Point facilities/rooms in current realm
        gw_by_node: dict[str, list[dict]] = {}
        for gw in realm_gateways:
            ap_id = str(gw.get("access_point_node_id") or "")
            if ap_id:
                gw_by_node.setdefault(ap_id, []).append(gw)
        for z_it in enriched_zones:
            for p_it in (z_it.get("primary_locations") or []):
                p_nid_g = str(p_it.get("node_id") or "")
                p_gws = list(gw_by_node.get(p_nid_g, []))
                node_obj_cnt = ap_unique_counts.get(p_nid_g, 0)
                for s_it in (p_it.get("sub_location_details") or []):
                    s_nid_g = str(s_it.get("node_id") or "")
                    if s_nid_g in gw_by_node:
                        s_it["gateways"] = gw_by_node[s_nid_g]
                        p_gws.extend(gw_by_node[s_nid_g])
                        node_obj_cnt += ap_unique_counts.get(s_nid_g, 0)
                if p_gws:
                    p_it["gateways"] = p_gws
                    p_it["off_realm_objective_count"] = node_obj_cnt

    return {
        "session_id": session_id,
        "scenario": scen_key,
        "current_location": current_loc,
        "current_node_id": curr_node_id or "",
        "current_node": curr_node,
        "player_at_transit_hub": player_at_transit_hub,
        "outgoing_edges": outgoing_edges,
        "current_zone": curr_z,
        "current_primary": curr_p,
        "current_sub": curr_sub,
        "can_travel": not player_restrained,
        "travel_blocked_reason": "You are currently restrained and cannot fast travel." if player_restrained else "",
        "zones": enriched_zones,
        "active_quest_destinations": active_quest_destinations,
        "current_realm": curr_realm_info,
        "show_realm_badge": bool(realm_summary.get("show_realm_badge")),
        "visible_realm_count": int(realm_summary.get("visible_realm_count") or 0),
        "realm_gateways": realm_gateways,
        "off_realm_quest_destinations": off_realm_quest_destinations,
    }


def _locations_seed_needed(session_id: int, scen_key: str, current_loc: str, char_name: str = "") -> bool:
    """Read-only check whether GET /api/locations needs to acquire the session lock to seed missing nodes/waypoints."""
    if not session_id:
        return False
    with db.ReadUnitOfWork():
        _, _, _, _, pending_seeds, needs_wp = _inspect_location_seeding(
            session_id,
            scen_key,
            current_loc,
            char_name,
            check_missing_wp_table=True,
        )
        return bool(needs_wp or pending_seeds)


def _build_locations_payload_readonly(session_id: int, scen_key: str, current_loc: str, char_name: str) -> dict:
    with db.ReadUnitOfWork():
        return _build_locations_payload(session_id, scen_key, current_loc, char_name)


@router.get("/api/locations/{session_id}")
async def get_world_map_locations(session_id: int, user_id: int | None = None, request: Request = None):
    """Returns the 3-tiered discovered World Map hierarchy (Zones -> Primary Locations -> Sub-Areas) with travel tags and quest badges."""
    user_id = user_id if isinstance(user_id, (int, str)) and not isinstance(user_id, bool) else None
    valid_uid = int(user_id) if isinstance(user_id, int) or (isinstance(user_id, str) and user_id.isdigit()) else None
    session, eff_uid = await verify_session_participant(request, session_id, valid_uid)

    scen_key = session.get("scenario", "fantasy")
    current_loc = session.get("current_location") or ""
    lookup_uid = valid_uid or eff_uid or session.get("host_user_id")
    char_row = (
        (
            await adb(db.get_character, lookup_uid, session_id=session_id)
            or await adb(db.get_character, lookup_uid)
        )
        if lookup_uid
        else None
    )
    char_name = char_row.get("name", "") if char_row else ""

    if await adb(_locations_seed_needed, session_id, scen_key, current_loc, char_name):
        async with distributed_session_lock(session_id):
            payload = await adb(_build_locations_payload, session_id, scen_key, current_loc, char_name)
    else:
        payload = await adb(_build_locations_payload_readonly, session_id, scen_key, current_loc, char_name)
    return payload
