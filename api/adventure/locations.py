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
        process_llm_location_update,
        get_zone_summary_tree,
        sanitize_location_target,
        parse_tiered_location,
    )
    from mechanics.world.waypoints import ensure_quest_waypoints_exist
    try:
        ensure_quest_waypoints_exist(session_id)
    except Exception:
        pass

    active_wps = db.get_all_session_active_waypoints(session_id)
    for wp in active_wps:
        target_loc = (wp.get("target_location") or "").strip()
        if target_loc:
            clean_target = sanitize_location_target(target_loc, session_id=session_id, scen_key=scen_key, char_name=char_name)
            process_llm_location_update(session_id, clean_target, scen_key, char_name=char_name)

    # Seed any active rendezvous commitment destinations
    from mechanics.system.commitments_engine import get_active_commitments
    appts = get_active_commitments(session_id, commitment_type="rendezvous", limit=25) if session_id else []
    for appt in appts:
        appt_loc = (appt.get("target_location") or appt.get("rendezvous_location") or "").strip()
        if appt_loc:
            clean_appt_loc = sanitize_location_target(appt_loc, session_id=session_id, scen_key=scen_key, char_name=char_name)
            process_llm_location_update(session_id, clean_appt_loc, scen_key, char_name=char_name)

    if current_loc:
        process_llm_location_update(session_id, current_loc, scen_key, char_name=char_name)

    zones_summary = get_zone_summary_tree(session_id, scen_key, current_loc=current_loc, char_name=char_name)
    curr_z, curr_p, curr_sub = (
        parse_tiered_location(current_loc, scen_key, session_id=session_id, char_name=char_name)
        if current_loc else ("", "", "")
    )

    session = db.get_session(session_id)
    curr_node_id = session.get("current_node_id") if session else None
    resolved_loc_nid = db.resolve_node_id_from_location(session_id, current_loc, prefer_facility=False) if (session_id and current_loc) else None
    eff_curr_node_id = resolved_loc_nid or curr_node_id
    curr_node = db.get_world_node(session_id, eff_curr_node_id) if (session_id and eff_curr_node_id) else None
    all_nodes = db.get_session_world_nodes(session_id) if session_id else []
    nodes_by_id = {str(n["node_id"]): n for n in all_nodes if isinstance(n, dict) and n.get("node_id")}

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
    player_at_transit_hub = _is_transit_hub_in_mem(eff_curr_node_id) if (session_id and eff_curr_node_id) else False

    from mechanics.world.schedules import get_npc_scheduled_node_id
    from mechanics.world.anchor_schedule import is_npc_on_active_shift, resolve_anchor_schedule_nodes
    from mechanics.world.locations.access_gate import (
        build_active_quest_gate_snapshot,
        get_node_effective_access_info,
    )
    from mechanics.world.locations.residence_fog import SHARED_ABSTRACT_RESIDENCE_NODE
    from mechanics.world.schedule_blocks import get_detailed_npc_time_phase, get_time_block_key
    q_gate_snap = build_active_quest_gate_snapshot(session_id) if session_id else None

    curr_day, curr_min, _ = db.get_session_time(session_id)
    contacts = db.get_contacts(session_id) or []
    world_roster_rows = (
        db.get_world_roster(session_id, include_legacy_rosters=False) or []
        if (session_id and hasattr(db, "get_world_roster"))
        else []
    )
    world_roster_by_low = {
        str(w.get("name") or "").strip().lower(): w
        for w in world_roster_rows
        if isinstance(w, dict) and w.get("name")
    }
    roster = db.get_school_roster(session_id) if hasattr(db, "get_school_roster") else []

    occupancy_by_node: dict[str, dict] = {}
    def _get_occ_entry(nid: str):
        if nid not in occupancy_by_node:
            occupancy_by_node[nid] = {"known_npcs": [], "unmet_count": 0}
        return occupancy_by_node[nid]

    for appt in appts:
        tgt = appt.get("target_node_id")
        a_loc = appt.get("target_location") or appt.get("rendezvous_location") or ""
        if not tgt and a_loc:
            tgt = db.resolve_node_id_from_location(session_id, a_loc, prefer_facility=True)
        if tgt:
            tgt_node = nodes_by_id.get(tgt)
            fac_id = tgt_node.get("parent_id") if (tgt_node and tgt_node.get("node_type") == "ROOM") else tgt
            if fac_id:
                occ = _get_occ_entry(fac_id)
                a_nm = appt.get("npc_name") or ""
                if not a_nm and appt.get("participants"):
                    for pt in appt["participants"]:
                        if pt.get("role") != "organizer" and pt.get("person_key") != "player":
                            a_nm = pt.get("name") or pt.get("person_key") or ""
                            break
                if not a_nm and appt.get("target_entity") and appt.get("target_entity") not in ("player", "group"):
                    a_nm = str(appt["target_entity"]).replace("_", " ").title()
                if a_nm and not any(kn["name"].lower() == a_nm.lower() for kn in occ["known_npcs"]):
                    occ["known_npcs"].append({"name": a_nm, "status": "Rendezvous"})

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

    contact_names_lower = set()
    for c in contacts:
        c_nm = (c.get("name") or "").strip()
        if not c_nm:
            continue
        contact_names_lower.add(c_nm.lower())
        c_probe = c
        c_wr = world_roster_by_low.get(c_nm.lower())
        if isinstance(c_wr, dict):
            c_bi = c.get("basic_info") if isinstance(c.get("basic_info"), dict) else {}
            w_bi = c_wr.get("basic_info") if isinstance(c_wr.get("basic_info"), dict) else {}
            c_probe = {
                **c_wr,
                **c,
                "basic_info": {**w_bi, **c_bi},
                "_roster_premerged": True,
                "_db_hydrated": True,
            }
        sched_nid = get_npc_scheduled_node_id(c_probe, current_minute=curr_min, scen_key=scen_key, current_day=curr_day)
        if sched_nid:
            s_node = nodes_by_id.get(sched_nid)
            fac_id = s_node.get("parent_id") if (s_node and s_node.get("node_type") == "ROOM") else sched_nid
            if fac_id:
                occ = _get_occ_entry(fac_id)
                if not any(kn["name"].lower() == c_nm.lower() for kn in occ["known_npcs"]):
                    occ["known_npcs"].append({"name": c_nm, "status": "Routine"})

    seen_roster_names_lower: set[str] = set()
    curr_phase_occ = get_detailed_npc_time_phase(curr_min, current_day=curr_day, scen_key=scen_key)
    curr_blk_occ = get_time_block_key(curr_min)
    for wr in world_roster_rows:
        wr_nm = str(wr.get("name") or "").strip()
        if not wr_nm or wr_nm.lower() in contact_names_lower:
            continue
        if str(wr.get("origin") or "").strip().lower() == "legacy_adapter":
            continue
        if str(wr.get("staff_status") or "active").strip().lower() != "active":
            continue
        wr_pre = {**wr, "_roster_premerged": True}
        a_map = resolve_anchor_schedule_nodes(
            wr_pre, current_day=curr_day, scen_key=scen_key, session_id=None, current_minute=curr_min
        )
        on_sh, work_nid = is_npc_on_active_shift(
            wr_pre, curr_min, current_day=curr_day, scen_key=scen_key, session_id=None
        )
        sched_nid = (
            (work_nid if (on_sh and work_nid) else "")
            or str((a_map or {}).get(curr_phase_occ) or (a_map or {}).get(curr_blk_occ) or "").strip()
        )
        if not sched_nid or sched_nid in (SHARED_ABSTRACT_RESIDENCE_NODE, "loc_rival_academy_away"):
            continue
        s_node = nodes_by_id.get(sched_nid)
        fac_id = s_node.get("parent_id") if (s_node and s_node.get("node_type") == "ROOM") else sched_nid
        if fac_id:
            occ = _get_occ_entry(fac_id)
            if wr.get("met_in_person") or int(wr.get("affinity_score") or 0) != 0:
                if not any(kn["name"].lower() == wr_nm.lower() for kn in occ["known_npcs"]):
                    occ["known_npcs"].append({"name": wr_nm, "status": "Routine"})
            else:
                occ["unmet_count"] += 1
            seen_roster_names_lower.add(wr_nm.lower())

    for r in roster:
        r_nm = (r.get("name") or "").strip()
        if not r_nm or r_nm.lower() in contact_names_lower or r_nm.lower() in seen_roster_names_lower:
            continue
        sched_nid = get_npc_scheduled_node_id(r, current_minute=curr_min, scen_key=scen_key, current_day=curr_day)
        if sched_nid:
            s_node = nodes_by_id.get(sched_nid)
            fac_id = s_node.get("parent_id") if (s_node and s_node.get("node_type") == "ROOM") else sched_nid
            if fac_id:
                occ = _get_occ_entry(fac_id)
                occ["unmet_count"] += 1

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

            p_node_id = db.resolve_node_id_from_location(session_id, f"{z_name} ➔ {p_copy.get('name', '')}", prefer_facility=True)
            node = nodes_by_id.get(p_node_id) if p_node_id else None
            is_transit_hub = bool(node and node.get("is_transit_hub"))
            can_transit_travel = _is_transit_hub_in_mem(p_node_id) if p_node_id else False
            is_adjacent = bool(
                p_node_id and (
                    p_node_id in adjacent_node_ids or
                    any(n.get("parent_id") == p_node_id and n["node_id"] in adjacent_node_ids for n in all_nodes)
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
                    from mechanics.world.locations.formatting import format_travel_eta_tag
                    t_mins = int(p_copy.get("travel_minutes") or (4 if is_same_zone else 15))
                    eta_tag = format_travel_eta_tag(t_mins, is_same_zone=is_same_zone, scen_key=scen_key, is_here=False)
                if player_at_transit_hub and can_transit_travel and not is_same_zone and "transit" not in eta_tag.lower():
                    p_copy["travel_tag"] = f"Transit • {eta_tag}"
                else:
                    p_copy["travel_tag"] = eta_tag

            access_info = (
                get_node_effective_access_info(
                    session_id,
                    p_node_id,
                    current_day=curr_day,
                    current_minute=curr_min,
                    scen_key=scen_key,
                    quest_gate_snapshot=q_gate_snap,
                )
                if p_node_id
                else {}
            )
            occ_data = occupancy_by_node.get(p_node_id, {"known_npcs": [], "unmet_count": 0}) if p_node_id else {"known_npcs": [], "unmet_count": 0}

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
            p_copy["known_npcs_here"] = occ_data["known_npcs"][:3]
            p_copy["unmet_activity_count"] = occ_data["unmet_count"]
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
