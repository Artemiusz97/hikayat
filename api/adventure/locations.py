from __future__ import annotations

import db
from fastapi import (
    APIRouter,
    Request,
)
from db import adb
from ..security import verify_session_participant

router = APIRouter()


def _build_locations_payload(session_id: int, scen_key: str, current_loc: str, char_name: str) -> dict:
    from mechanics.world.locations import (
        build_access_eval_context,
        build_location_occupancy_index,
        format_travel_eta_tag,
        get_node_effective_access_info,
        get_zone_summary_tree,
        parse_tiered_location,
        process_llm_location_update,
        sanitize_location_target,
    )
    from mechanics.world.waypoints import ensure_quest_waypoints_exist

    appts_cache: list[dict] | None = None
    if session_id and not db.is_in_readonly_uow():
        try:
            ensure_quest_waypoints_exist(session_id)
        except Exception:
            pass

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

        active_wps = db.get_all_session_active_waypoints(session_id)
        for wp in active_wps:
            target_loc = (wp.get("target_location") or "").strip()
            if not target_loc or _is_already_seeded_raw(target_loc):
                continue
            clean_target = sanitize_location_target(target_loc, session_id=session_id, scen_key=scen_key, char_name=char_name)
            _queue_loc_seed(clean_target)

        # Seed any active rendezvous commitment destinations
        from mechanics.system.commitments_engine import get_active_commitments
        appts_cache = get_active_commitments(session_id, commitment_type="rendezvous", limit=25) or []
        for appt in appts_cache:
            appt_loc = (appt.get("target_location") or appt.get("rendezvous_location") or "").strip()
            if not appt_loc or _is_already_seeded_raw(appt_loc):
                continue
            clean_appt_loc = sanitize_location_target(appt_loc, session_id=session_id, scen_key=scen_key, char_name=char_name)
            _queue_loc_seed(clean_appt_loc)

        if current_loc:
            _queue_loc_seed(current_loc)

        if pending_seed_targets:
            with db.UnitOfWork():
                for _seed_loc in pending_seed_targets:
                    process_llm_location_update(session_id, _seed_loc, scen_key, char_name=char_name)

    zones_summary = get_zone_summary_tree(
        session_id,
        scen_key,
        current_loc=current_loc,
        char_name=char_name,
        ensure_waypoints=False,
    )
    curr_z, curr_p, curr_sub = (
        parse_tiered_location(current_loc, scen_key, session_id=session_id, char_name=char_name)
        if current_loc else ("", "", "")
    )

    session = db.get_session(session_id)
    curr_node_id = session.get("current_node_id") if session else None
    resolved_loc_nid = db.resolve_node_id_from_location(session_id, current_loc, prefer_facility=False) if (session_id and current_loc) else None
    eff_curr_node_id = resolved_loc_nid or curr_node_id
    all_nodes = db.get_session_world_nodes(session_id) if session_id else []
    nodes_by_id = {str(n["node_id"]): n for n in all_nodes if isinstance(n, dict) and n.get("node_id")}
    fac_zone_id_by_name_lower: dict[str, str] = {}
    for _wn in all_nodes:
        if not isinstance(_wn, dict):
            continue
        _wn_id = _wn.get("node_id")
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
                    p_node_id = db.resolve_node_id_from_location(session_id, f"{z_name} ➔ {p_nm_raw}", prefer_facility=True)
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
                        rendezvous_commitments=appts_cache,
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
    }


@router.get("/api/locations/{session_id}")
async def get_world_map_locations(session_id: int, user_id: int | None = None, request: Request = None):
    """Returns the 3-tiered discovered World Map hierarchy (Zones -> Primary Locations -> Sub-Areas) with travel tags and quest badges."""
    user_id = user_id if isinstance(user_id, (int, str)) and not isinstance(user_id, bool) else None
    valid_uid = int(user_id) if isinstance(user_id, int) or (isinstance(user_id, str) and user_id.isdigit()) else None
    session, eff_uid = await verify_session_participant(request, session_id, valid_uid)

    scen_key = session.get("scenario", "fantasy")
    current_loc = session.get("current_location") or ""
    lookup_uid = valid_uid or eff_uid or session.get("host_user_id")
    char_row = await adb(db.get_character, lookup_uid) if lookup_uid else None
    char_name = char_row.get("name", "") if char_row else ""

    payload = await adb(_build_locations_payload, session_id, scen_key, current_loc, char_name)
    return payload
