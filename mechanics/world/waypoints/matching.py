from __future__ import annotations
"""
Location matching, arrival triggers, and skill check completion logic.
"""
import json
import re
from typing import Optional, Any

import db
import scenario_data
from .templates import parse_zone_primary


def check_location_matches_waypoint(
    current_location: str,
    target_location: str,
    session_id: int = 0,
    current_node_id: str = None,
    target_node_id: str = None
) -> bool:
    """Returns True if current_location matches the waypoint target.
    If session_id is provided, checks strict spatial graph containment (is_descendant_of) first.
    Matches on Zone + Primary only. Empty target always matches.
    Robust to multi-tier inversion (e.g. Student Council Office inside Administration Wing).
    """
    if not target_location or not target_location.strip():
        return True

    if session_id:
        try:
            curr_nid = current_node_id or (db.resolve_node_id_from_location(session_id, current_location) if current_location else None)
            tgt_nid = target_node_id or (db.resolve_node_id_from_location(session_id, target_location) if target_location else None)
            if curr_nid and tgt_nid:
                return db.is_descendant_of(session_id, curr_nid, tgt_nid) or db.is_descendant_of(session_id, tgt_nid, curr_nid)
        except Exception:
            pass

    curr_zone, curr_primary = parse_zone_primary(current_location)
    tgt_zone, tgt_primary = parse_zone_primary(target_location)

    # 1. Full/Sub-string containment check:
    # If the player's primary location is contained anywhere in target_location (e.g. "Student Council Office" in
    # "Westlake Academy -> Administration Wing -> Student Council Office") and zones are compatible, it's a match!
    curr_prim_norm = curr_primary.strip().lower()
    tgt_loc_norm = target_location.strip().lower()
    if curr_prim_norm and len(curr_prim_norm) >= 4 and curr_prim_norm in tgt_loc_norm:
        if not tgt_zone or not curr_zone or tgt_zone in curr_zone or curr_zone in tgt_zone:
            return True

    # Reverse: If target's primary is contained in current_location
    if tgt_primary and len(tgt_primary) >= 4 and tgt_primary in current_location.lower():
        if not tgt_zone or not curr_zone or tgt_zone in curr_zone or curr_zone in tgt_zone:
            return True
    
    # If the target is just a zone (e.g., "Forest"), and we're inside that zone (e.g., "Forest -> Deep Woods")
    if not tgt_zone and curr_zone:
        tgt_words = set(re.findall(r"\b\w{3,}\b", tgt_primary))
        curr_z_words = set(re.findall(r"\b\w{3,}\b", curr_zone))
        if tgt_words and tgt_words.issubset(curr_z_words):
            return True
            
    if tgt_primary and curr_primary:
        tgt_words = set(re.findall(r"\b\w{3,}\b", tgt_primary))
        curr_words = set(re.findall(r"\b\w{3,}\b", curr_primary))
        if tgt_words and tgt_words.issubset(curr_words):
            return True
        if curr_words and curr_words.issubset(tgt_words):
            return True
    if tgt_zone and curr_zone:
        tgt_z_words = set(re.findall(r"\b\w{3,}\b", tgt_zone))
        curr_z_words = set(re.findall(r"\b\w{3,}\b", curr_zone))
        if tgt_z_words and tgt_z_words.issubset(curr_z_words):
            if tgt_primary and curr_primary and (tgt_primary in curr_primary or curr_primary in tgt_primary):
                return True
    return False


def is_hostile_or_lair_waypoint(wp: dict) -> bool:
    """Returns True if the waypoint represents a hostile boss/outlaw/monster hideout stage."""
    bp = str(wp.get("blueprint_id") or "").upper()
    lbl = str(wp.get("stage_label") or "").lower()
    trig = str(wp.get("completion_trigger") or "").strip().lower()
    is_climax = bool(wp.get("is_climax_stage") or wp.get("is_climax"))
    target_npc = str(wp.get("target_npc") or "").strip().lower()
    client_npc = str(wp.get("client_npc") or "").strip().lower()
    if client_npc and target_npc == client_npc:
        return False
    if trig == "key_clue" and not is_climax:
        return False
    if any(w in lbl for w in ("turn in", "deliver", "report to", "return to", "hand over")):
        return False
    if bp in ("NEUTRALIZATION", "EXPLORATION_HAZARD", "SITE_DEFENSE_RITUAL"):
        return True
    if any(w in lbl for w in ("confront", "eliminate", "slay", "assassinate", "capture", "defeat", "outlaw", "poacher", "smuggler", "bandit", "hideout", "lair")):
        return True
    return False


def _minutes_until_next_shift_open(shift_profile: str, safe_min: int, fallback_wake: int) -> int:
    from mechanics.world.anchor_schedule import SHIFT_PROFILES, _normalize_shift_profile
    norm = _normalize_shift_profile(shift_profile, has_route=False)
    windows = SHIFT_PROFILES.get(norm, {}).get("work_windows") or []
    waits = [((int(start) - safe_min) % 1440) or 1440 for start, _ in windows]
    if waits:
        return min(waits)
    wait_mins = (fallback_wake - safe_min) % 1440
    return wait_mins if wait_mins > 0 else 60


def _lookup_in_memory_special_agent(
    session: Optional[dict],
    target_npc: str,
    slug_npc: str,
    legacy_entries_by_key: Optional[dict[str, dict]],
) -> Optional[dict]:
    tgt_low = target_npc.lower()
    if isinstance(legacy_entries_by_key, dict):
        hit = legacy_entries_by_key.get(tgt_low) or legacy_entries_by_key.get(slug_npc)
        if isinstance(hit, dict):
            return hit
    if not isinstance(session, dict):
        return None
    agents = session.get("anomalous_agent_roster")
    if not isinstance(agents, list) and isinstance(session.get("extra"), dict):
        agents = session["extra"].get("anomalous_agent_roster")
    if not isinstance(agents, list) and isinstance(session.get("extra_json"), str) and session["extra_json"].strip():
        try:
            parsed_extra = json.loads(session["extra_json"])
            if isinstance(parsed_extra, dict):
                agents = parsed_extra.get("anomalous_agent_roster")
        except Exception:
            agents = None
    if not isinstance(agents, list):
        return None
    for ag in agents:
        if not isinstance(ag, dict):
            continue
        ag_nm = str(ag.get("name") or "").strip().lower()
        ag_id = str(ag.get("npc_id") or "").strip().lower()
        if ag_nm == tgt_low or (slug_npc and ag_id == slug_npc):
            return ag
    return None


def _resolve_sanctuary_node_in_memory(nodes_by_id: dict) -> str:
    from mechanics.world.locations.access_gate import (
        _SANCTUARY_EXCLUDED_KEYWORDS,
        _SANCTUARY_PREFERRED_KEYWORDS,
    )
    from mechanics.world.venue_templates import parse_node_state

    nodes = [n for n in nodes_by_id.values() if isinstance(n, dict)]
    if not nodes:
        return "loc_hub_sanctuary"
    facilities = [n for n in nodes if str(n.get("node_type") or "").upper() == "FACILITY"] or list(nodes)
    for fac in facilities:
        nid = str(fac.get("node_id") or "")
        if nid and parse_node_state(fac).get("safe_sanctuary_exempt"):
            return nid
    for fac in facilities:
        nid = str(fac.get("node_id") or "")
        tier = str(fac.get("access_tier") or "open").lower()
        blob = f"{nid} {fac.get('name') or ''}".lower()
        if tier == "open" and not any(ex in blob for ex in _SANCTUARY_EXCLUDED_KEYWORDS) and any(pk in blob for pk in _SANCTUARY_PREFERRED_KEYWORDS):
            return nid
    for fac in facilities:
        nid = str(fac.get("node_id") or "")
        tier = str(fac.get("access_tier") or "open").lower()
        blob = f"{nid} {fac.get('name') or ''}".lower()
        if tier == "open" and not any(ex in blob for ex in _SANCTUARY_EXCLUDED_KEYWORDS):
            return nid
    return "loc_hub_sanctuary"


def _apply_in_memory_commitment_override(
    active_commitments: list,
    npc_dict: dict,
    target_npc: str,
    current_day: int,
    current_minute: int,
    nodes_by_id: dict,
) -> tuple[str, str]:
    from mechanics.world.presence_graph import format_node_display_label, slugify_key

    tokens: set[str] = set()
    for raw in (npc_dict.get("npc_id"), npc_dict.get("npc_key"), npc_dict.get("name"), target_npc):
        s = str(raw or "").strip().lower()
        if s:
            tokens.add(s)
            sl = slugify_key(s)
            if sl:
                tokens.add(sl)
    if not tokens:
        return "", ""

    abs_now = (max(1, int(current_day)) - 1) * 1440 + max(0, int(current_minute))
    for row in active_commitments:
        if not isinstance(row, dict):
            continue
        stat = str(row.get("status") or "active").strip().lower()
        if stat in ("cancelled", "canceled", "completed", "missed", "expired", "failed"):
            continue
        row_keys: set[str] = set()
        for rk_field in ("npc_id", "target_entity", "source_entity"):
            r_val = str(row.get(rk_field) or "").strip().lower()
            if r_val and r_val != "player":
                row_keys.add(r_val)
                row_keys.add(slugify_key(r_val))
        p_raw = row.get("participants")
        if p_raw is None and isinstance(row.get("participants_json"), str):
            try:
                p_raw = json.loads(row["participants_json"])
            except Exception:
                p_raw = []
        if isinstance(p_raw, list):
            for p in p_raw:
                if isinstance(p, dict):
                    for pk in (p.get("person_key"), p.get("npc_id"), p.get("name"), p.get("npc_name")):
                        ps = str(pk or "").strip().lower()
                        if ps and ps != "player" and not ps.startswith("player:"):
                            row_keys.add(ps)
                            row_keys.add(slugify_key(ps))
                else:
                    ps = str(p or "").strip().lower()
                    if ps and ps != "player" and not ps.startswith("player:"):
                        row_keys.add(ps)
                        row_keys.add(slugify_key(ps))
        row_keys.discard("")
        if not (row_keys & tokens):
            continue

        s_day = max(1, int(row.get("scheduled_day") or 1))
        s_min = max(0, int(row.get("start_minute") if row.get("start_minute") is not None else 0))
        raw_end = int(row.get("end_minute") if row.get("end_minute") is not None else 1439)
        if raw_end >= 1440:
            extra_d, e_min = divmod(raw_end, 1440)
            e_day = s_day + extra_d
        else:
            e_min = max(0, raw_end)
            if row.get("end_day") is not None:
                e_day = max(s_day, int(row["end_day"]))
            elif e_min < s_min:
                e_day = s_day + 1
            else:
                e_day = s_day
        abs_start = (s_day - 1) * 1440 + s_min
        abs_end = (e_day - 1) * 1440 + e_min
        if max(0, abs_start - 15) <= abs_now <= abs_end:
            ov_nid = str(row.get("target_node_id") or "").strip()
            ov_loc = str(row.get("target_location") or "").strip()
            if ov_nid and ov_nid in nodes_by_id:
                return format_node_display_label(ov_nid, ov_loc, nodes_by_id), ov_nid
            if ov_loc:
                return ov_loc, ov_nid
    return "", ""


def _resolve_waypoint_scheduled_location_in_memory(
    session_id: int,
    npc_dict: dict,
    target_npc: str,
    curr_day: int,
    safe_min: int,
    scen_key: str,
    session: Optional[dict],
    nodes_by_id: dict,
    *,
    active_events: Optional[list[dict]] = None,
    primary_property: Optional[dict] = None,
    primary_property_loaded: bool = False,
    contacts: Optional[list[dict]] = None,
    person_ties: Optional[list[Any]] = None,
    active_commitments: Optional[list[dict]] = None,
    skip_uncached_db: bool = False,
) -> tuple[str, str]:
    from mechanics.social.races import is_myobu_fox_race
    from mechanics.social.roster_tags import npc_is_folklore_villager
    from mechanics.world.locations.realty_catalog import is_anomalous_realty_scenario
    from mechanics.world.locations.residence_fog import SHARED_ABSTRACT_RESIDENCE_NODE
    from mechanics.world.locations.residences import resolve_spare_key_evening_visit_node
    from mechanics.world.npc_schedule import (
        get_detailed_npc_time_phase,
        get_npc_schedule,
        get_npc_schedule_node_ids,
    )
    from mechanics.world.presence_graph import format_node_display_label, resolve_node_id_in_memory
    from mechanics.world.schedule_blocks import get_time_block_key

    if active_commitments is not None:
        ov_loc, ov_nid = _apply_in_memory_commitment_override(
            active_commitments, npc_dict, target_npc, curr_day, safe_min, nodes_by_id
        )
        if ov_loc:
            return ov_loc, ov_nid
    elif session_id and not skip_uncached_db:
        try:
            from mechanics.system.commitments_engine import inject_npc_schedule_overrides
            npc_id_key = str(npc_dict.get("npc_id") or npc_dict.get("name") or "").strip().lower().replace(" ", "_")
            override = inject_npc_schedule_overrides(session_id, npc_id_key, curr_day, safe_min)
            if override and override.get("location"):
                return str(override["location"]).strip(), str(override.get("node_id") or "").strip()
        except Exception:
            pass

    scen_low = str(scen_key or "").lower()
    node_sched = dict(
        get_npc_schedule_node_ids(
            npc_dict,
            scen_key=scen_key,
            current_day=curr_day,
            current_minute=safe_min,
            session_id=None,
        )
        or {}
    )

    skip_spare = npc_is_folklore_villager(npc_dict) and is_myobu_fox_race(str(npc_dict.get("race") or ""))
    if session_id and is_anomalous_realty_scenario(scen_low) and not skip_spare and (primary_property_loaded or not skip_uncached_db):
        sk_eve = resolve_spare_key_evening_visit_node(
            int(session_id),
            npc_dict,
            curr_day,
            "evening",
            primary_property=primary_property,
            primary_property_loaded=primary_property_loaded,
            contacts=contacts,
            person_ties=person_ties,
            session=session,
        )
        if sk_eve:
            node_sched["evening"] = sk_eve
            if "extracurricular" in node_sched:
                node_sched["extracurricular"] = sk_eve
        sk_aft = resolve_spare_key_evening_visit_node(
            int(session_id),
            npc_dict,
            curr_day,
            "afternoon",
            primary_property=primary_property,
            primary_property_loaded=primary_property_loaded,
            contacts=contacts,
            person_ties=person_ties,
            session=session,
        )
        if sk_aft:
            node_sched["afternoon"] = sk_aft

    detail_block = get_detailed_npc_time_phase(safe_min, current_day=curr_day, scen_key=scen_key)
    base_block = get_time_block_key(safe_min)
    block_key = detail_block if detail_block in node_sched else (base_block if base_block in node_sched else "morning")
    sched_nid = str(node_sched.get(block_key) or node_sched.get("morning") or "").strip()

    ev_list = active_events
    if ev_list is None and session_id and not skip_uncached_db:
        try:
            ev_list = db.get_world_events(session_id, entity_type="macro_event") or []
        except Exception:
            ev_list = []

    if ev_list and sched_nid != SHARED_ABSTRACT_RESIDENCE_NODE:
        crisis_events = [
            ev for ev in ev_list
            if isinstance(ev, dict)
            and ev.get("status") == "active"
            and (
                (ev.get("modifiers") or {}).get("is_locked")
                or (ev.get("modifiers") or {}).get("lockdown_nodes")
                or (ev.get("modifiers") or {}).get("martial_law_lockdown")
                or (ev.get("metadata") or {}).get("scar_tier") == "peak"
            )
        ]
        basic = npc_dict.get("basic_info") if isinstance(npc_dict.get("basic_info"), dict) else {}
        role = str(npc_dict.get("role") or basic.get("role") or npc_dict.get("occupation") or "").lower()
        if crisis_events and not any(w in role for w in ("inquisitor", "enforcer", "warden", "sentinel", "occupier")):
            try:
                from mechanics.world.world_events.modifiers import is_node_locked_by_event
                sanctuary_nid = _resolve_sanctuary_node_in_memory(nodes_by_id)
                sanc_target_nid = sanctuary_nid
                open_rooms = [
                    n["node_id"]
                    for n in nodes_by_id.values()
                    if isinstance(n, dict)
                    and str(n.get("parent_id") or "") == sanctuary_nid
                    and str(n.get("access_tier") or "open").lower() == "open"
                ]
                if open_rooms:
                    sanc_target_nid = open_rooms[0]
                loc_obj = nodes_by_id.get(sched_nid)
                fac_nid = (
                    str(loc_obj.get("parent_id") or "")
                    if (isinstance(loc_obj, dict) and str(loc_obj.get("node_type") or "").upper() == "ROOM")
                    else sched_nid
                )
                if not (sanctuary_nid and (sched_nid == sanctuary_nid or fac_nid == sanctuary_nid)):
                    cur_ch = int((session or {}).get("current_chapter") or 1)
                    martial_curfew = cur_ch in (8, 9) and any(
                        bool((ev.get("modifiers") or {}).get("martial_law_lockdown")) for ev in crisis_events
                    )
                    locked_hit = bool(
                        (sched_nid and is_node_locked_by_event(crisis_events, sched_nid, safe_sanctuary_node_id=sanctuary_nid))
                        or (fac_nid and is_node_locked_by_event(crisis_events, fac_nid, safe_sanctuary_node_id=sanctuary_nid))
                    )
                    sched_disp_low = format_node_display_label(sched_nid, "", nodes_by_id).lower()
                    scar_hit = any(
                        (ev.get("metadata") or {}).get("scar_tier") == "peak"
                        and any(
                            len(seg.strip()) >= 4 and seg.strip().lower() in sched_disp_low
                            for seg in str(ev.get("location_name") or "").split("➔")[-1:]
                        )
                        for ev in crisis_events
                    )
                    curfew_hit = bool(martial_curfew and block_key in ("evening", "night"))
                    if locked_hit or scar_hit or curfew_hit:
                        home_nid = str(npc_dict.get("home_node_id") or basic.get("home_node_id") or "").strip()
                        if block_key == "night" and home_nid and home_nid != SHARED_ABSTRACT_RESIDENCE_NODE and home_nid != sched_nid:
                            sched_nid = home_nid
                        elif sanc_target_nid:
                            sched_nid = sanc_target_nid
            except Exception:
                pass

    if sched_nid == SHARED_ABSTRACT_RESIDENCE_NODE:
        return "Residential District (Unknown Address)", sched_nid
    if sched_nid and sched_nid in nodes_by_id:
        return format_node_display_label(sched_nid, "", nodes_by_id), sched_nid

    text_sched = get_npc_schedule(
        npc_dict, scen_key=scen_key, session_id=None, current_day=curr_day, current_minute=safe_min
    )
    fallback_loc = str(
        text_sched.get(detail_block, text_sched.get(base_block, text_sched.get("morning", "")))
    ).strip()
    resolved_nid = (
        resolve_node_id_in_memory(fallback_loc, nodes_by_id, prefer_facility=False)
        if (fallback_loc and nodes_by_id)
        else ""
    )
    return fallback_loc, (resolved_nid or sched_nid)


def get_waypoint_npc_schedule_info(
    session_id: int,
    wp: dict,
    current_minute: Optional[int] = None,
    session: Optional[dict] = None,
    session_time: Optional[tuple] = None,
    contacts_by_name: Optional[dict] = None,
    roster_by_key: Optional[dict] = None,
    nodes_by_id: Optional[dict] = None,
    active_events: Optional[list[dict]] = None,
    primary_property: Optional[dict] = None,
    primary_property_loaded: bool = False,
    contacts: Optional[list[dict]] = None,
    person_ties: Optional[list[Any]] = None,
    active_commitments: Optional[list[dict]] = None,
    legacy_entries_by_key: Optional[dict[str, dict]] = None,
) -> dict:
    """
    Resolves live NPC schedule routing and Nighttime Off-Duty Guard for a waypoint.
    Returns:
      {
        "effective_location": str,
        "static_location": str,
        "is_off_duty": bool,
        "schedule_phase": str,
        "wait_until_morning_minutes": int,
        "wake_clock": str,
      }
    """
    from mechanics.system.time_engine import format_clock
    static_loc = wp.get("static_target_location") or wp.get("target_location", "")
    default_res = {
        "effective_location": static_loc,
        "static_location": static_loc,
        "scheduled_location": static_loc,
        "is_off_duty": False,
        "schedule_phase": "",
        "status_label": "On-Duty",
        "wait_until_morning_minutes": 0,
        "wake_clock": "07:30",
        "wake_minute": 420,
    }
    if not wp.get("follow_npc_schedule") or not wp.get("target_npc") or not session_id:
        return default_res
    if is_hostile_or_lair_waypoint(wp):
        return default_res

    target_npc = str(wp.get("target_npc") or "").strip()
    try:
        if session_time is not None:
            curr_day, db_curr_min, _ = session_time
        else:
            curr_day, db_curr_min, _ = db.get_session_time(session_id)
        curr_min = current_minute if current_minute is not None else db_curr_min
        if session is None:
            session = db.get_session(session_id) or {}
        scen_key = str(session.get("scenario") or "fantasy")
        from mechanics.world.world_schedule import get_scenario_wake_minute
        from mechanics.world.npc_schedule import get_npc_scheduled_location, get_detailed_npc_time_phase
        from mechanics.world.anchor_schedule import is_npc_on_active_shift, resolve_anchor_schedule_nodes
        from mechanics.world.schedule_blocks import get_time_block_key
        wake_min = int(get_scenario_wake_minute(scen_key) or 420)
        safe_min = int(curr_min or 0) % 1440
        phase_key = get_detailed_npc_time_phase(safe_min, current_day=curr_day, scen_key=scen_key)

        slug_npc = re.sub(r"[^a-z0-9]+", "_", target_npc.lower()).strip("_")
        if roster_by_key is not None:
            roster_npc = roster_by_key.get(target_npc.lower()) or roster_by_key.get(slug_npc)
        else:
            roster_npc = db.get_world_roster_npc(session_id, target_npc, include_legacy_rosters=False)

        if contacts_by_name is not None:
            contact = contacts_by_name.get(target_npc.lower()) or contacts_by_name.get(slug_npc)
            if not contact and contacts:
                target_keys = {k for k in (target_npc.lower(), slug_npc) if k}
                for c_item in contacts:
                    if not isinstance(c_item, dict):
                        continue
                    c_id_l = str(c_item.get("npc_id") or "").strip().lower()
                    c_nm_l = str(c_item.get("name") or "").strip().lower()
                    c_sl = re.sub(r"[^a-z0-9]+", "_", c_nm_l).strip("_")
                    if target_keys & {k for k in (c_id_l, c_nm_l, c_sl) if k}:
                        contact = c_item
                        break
        else:
            contact = db.get_contact(session_id, target_npc)

        legacy_npc = _lookup_in_memory_special_agent(session, target_npc, slug_npc, legacy_entries_by_key)
        is_preloaded_lookup = (
            contacts_by_name is not None
            or roster_by_key is not None
            or legacy_entries_by_key is not None
        )
        if (
            not contact
            and not roster_npc
            and not legacy_npc
            and not is_preloaded_lookup
            and scenario_data.is_anomalous_incursions_scenario(scen_key)
        ):
            try:
                from mechanics.social.agent_roster import find_special_agent_by_name
                contact = find_special_agent_by_name(session_id, target_npc, scen_key=scen_key)
            except Exception:
                contact = None

        npc_record: Optional[dict] = None
        if contact or roster_npc or legacy_npc:
            npc_record = dict(contact or {})
            if isinstance(legacy_npc, dict):
                l_basic = legacy_npc.get("basic_info") if isinstance(legacy_npc.get("basic_info"), dict) else {}
                c_basic = npc_record.get("basic_info") if isinstance(npc_record.get("basic_info"), dict) else {}
                merged_basic = dict(l_basic)
                merged_basic.update(c_basic)
                npc_record["basic_info"] = merged_basic
                for l_key, l_val in legacy_npc.items():
                    if l_key == "basic_info":
                        continue
                    if not npc_record.get(l_key) and l_val not in (None, "", []):
                        npc_record[l_key] = l_val
            if isinstance(roster_npc, dict):
                r_basic = roster_npc.get("basic_info") if isinstance(roster_npc.get("basic_info"), dict) else {}
                c_basic = npc_record.get("basic_info") if isinstance(npc_record.get("basic_info"), dict) else {}
                merged_basic = dict(c_basic)
                merged_basic.update(r_basic)
                npc_record["basic_info"] = merged_basic
                for r_key in (
                    "npc_key", "npc_id", "name", "origin", "shift_profile",
                    "workplace_node_id", "hangout_node_id", "home_node_id",
                    "roaming_route", "is_unique_proprietor", "residence_unlocked",
                    "staff_status", "affinity_score", "is_24h_station",
                ):
                    r_val = roster_npc.get(r_key)
                    if r_val not in (None, "", []):
                        npc_record[r_key] = r_val
            npc_record["_roster_premerged"] = True
            npc_record["_db_hydrated"] = True

        score_cands = []
        for rec_s, key_s in (
            (contact, "relationship_score"),
            (contact, "interaction_score"),
            (roster_npc, "affinity_score"),
        ):
            if isinstance(rec_s, dict) and rec_s.get(key_s) not in (None, ""):
                try:
                    score_cands.append(int(rec_s[key_s]))
                except (TypeError, ValueError):
                    pass
        affinity = max(score_cands) if score_cands else 0

        if npc_record:
            rec_basic = npc_record.get("basic_info") if isinstance(npc_record.get("basic_info"), dict) else {}
            rec_status = str(npc_record.get("staff_status") or rec_basic.get("staff_status") or "active").strip().lower()
            if rec_status in ("dead", "arrested", "deceased") or npc_record.get("is_deceased") or npc_record.get("alive") is False:
                return {
                    "effective_location": static_loc,
                    "static_location": static_loc,
                    "scheduled_location": static_loc,
                    "is_off_duty": True,
                    "schedule_phase": phase_key,
                    "status_label": "Unavailable",
                    "wait_until_morning_minutes": 0,
                    "wake_clock": format_clock(wake_min),
                    "wake_minute": wake_min,
                }

        # Check if waypoint explicitly expects Night/Midnight
        v_phases = [str(p).lower() for p in (wp.get("valid_time_phases") or [])]
        night_allowed = any(p in ("night", "midnight") for p in v_phases)
        if not night_allowed and npc_record:
            from mechanics.world.schedules import is_npc_nocturnal_or_night_shift
            night_allowed = is_npc_nocturnal_or_night_shift(
                npc_record, scen_key=scen_key, current_day=curr_day, session_id=None
            )

        rec_basic = (npc_record.get("basic_info") if isinstance(npc_record.get("basic_info"), dict) else {}) if npc_record else {}
        origin_low = str((npc_record or {}).get("origin") or rec_basic.get("origin") or "").strip().lower()
        shift_prof = str((npc_record or {}).get("shift_profile") or rec_basic.get("shift_profile") or "").strip().lower()
        is_closed_world_worker = bool(npc_record) and (
            origin_low in ("venue_seed", "replacement_hire", "roaming_merchant", "role_slot_fill")
            or (roster_npc is not None and origin_low != "legacy_adapter" and bool(shift_prof))
        )

        # Shift-aware evaluation BEFORE generic >= 20:00 sleeping guard so active evening/night workers stay On-Duty
        if is_closed_world_worker and npc_record is not None:
            on_shift, _ = is_npc_on_active_shift(
                npc_record, safe_min, current_day=curr_day, scen_key=scen_key, session_id=None
            )
            if not on_shift and affinity < 40:
                anchor_nodes = resolve_anchor_schedule_nodes(
                    npc_record,
                    current_day=curr_day,
                    scen_key=scen_key,
                    session_id=None,
                    current_minute=safe_min,
                )
                sched_nid_now = str((anchor_nodes or {}).get(get_time_block_key(safe_min)) or "").strip()
                wp_node_id = str(wp.get("target_node_id") or "").strip()
                if not wp_node_id and static_loc:
                    if nodes_by_id is not None:
                        from mechanics.world.presence_graph import resolve_node_id_in_memory
                        wp_node_id = resolve_node_id_in_memory(static_loc, nodes_by_id, prefer_facility=True)
                    else:
                        wp_node_id = str(db.resolve_node_id_from_location(session_id, static_loc, prefer_facility=True) or "").strip()
                work_nid = str(npc_record.get("workplace_node_id") or "").strip()
                at_pinned_venue = bool(wp_node_id and sched_nid_now and sched_nid_now == wp_node_id)

                from mechanics.world.presence_doorbell import resolve_sleep_windows
                sleep_wins = resolve_sleep_windows(npc_record, scen_key)
                in_shift_sleep = any(s <= safe_min < e for s, e in sleep_wins)
                if shift_prof in ("day", "student", "roaming_merchant", "") and not night_allowed:
                    in_shift_sleep = in_shift_sleep or (safe_min >= 1200 or safe_min < wake_min)

                if in_shift_sleep and not at_pinned_venue and not (night_allowed and shift_prof != "night"):
                    wait_mins = (
                        ((wake_min - safe_min) % 1440) or 60
                        if shift_prof in ("day", "student", "roaming_merchant", "")
                        else _minutes_until_next_shift_open(shift_prof or "day", safe_min, wake_min)
                    )
                    return {
                        "effective_location": static_loc,
                        "static_location": static_loc,
                        "scheduled_location": static_loc,
                        "is_off_duty": True,
                        "schedule_phase": phase_key,
                        "status_label": "Off-Duty: Sleeping",
                        "wait_until_morning_minutes": wait_mins,
                        "wake_clock": format_clock(wake_min),
                        "wake_minute": wake_min,
                    }

                if not (shift_prof != "night" and night_allowed) and (
                    (wp_node_id and not at_pinned_venue) or (not wp_node_id and work_nid and sched_nid_now != work_nid)
                ):
                    wait_mins = _minutes_until_next_shift_open(shift_prof or "day", safe_min, wake_min)
                    return {
                        "effective_location": static_loc,
                        "static_location": static_loc,
                        "scheduled_location": static_loc,
                        "is_off_duty": True,
                        "schedule_phase": phase_key,
                        "status_label": "Off-Duty: Closed",
                        "wait_until_morning_minutes": wait_mins,
                        "wake_clock": format_clock(wake_min),
                        "wake_minute": wake_min,
                    }
        else:
            is_night = (safe_min >= 1200 or safe_min < wake_min)
            if is_night and not night_allowed and affinity < 40:
                wait_mins = (wake_min - safe_min) % 1440
                if wait_mins == 0:
                    wait_mins = 60
                return {
                    "effective_location": static_loc,
                    "static_location": static_loc,
                    "scheduled_location": static_loc,
                    "is_off_duty": True,
                    "schedule_phase": "night",
                    "status_label": "Off-Duty: Sleeping",
                    "wait_until_morning_minutes": wait_mins,
                    "wake_clock": format_clock(wake_min),
                    "wake_minute": wake_min,
                }

        # Only override static_loc with dynamic schedule if contact/roster/legacy exists
        if npc_record:
            npc_dict = dict(npc_record)
            if not npc_dict.get("name"):
                npc_dict["name"] = target_npc
            eff_sched_nid = ""
            if nodes_by_id is not None:
                sched_loc, eff_sched_nid = _resolve_waypoint_scheduled_location_in_memory(
                    session_id,
                    npc_dict,
                    target_npc,
                    curr_day,
                    safe_min,
                    scen_key,
                    session,
                    nodes_by_id,
                    active_events=active_events,
                    primary_property=primary_property,
                    primary_property_loaded=primary_property_loaded,
                    contacts=contacts,
                    person_ties=person_ties,
                    active_commitments=active_commitments,
                    skip_uncached_db=is_preloaded_lookup,
                )
            else:
                sched_loc = get_npc_scheduled_location(
                    npc_dict,
                    current_minute=safe_min,
                    scen_key=scen_key,
                    session_id=session_id,
                    current_day=curr_day,
                )
            if sched_loc and str(sched_loc).strip():
                res_out = {
                    "effective_location": str(sched_loc).strip(),
                    "static_location": static_loc,
                    "scheduled_location": str(sched_loc).strip(),
                    "is_off_duty": False,
                    "schedule_phase": phase_key,
                    "status_label": "On-Duty",
                    "wait_until_morning_minutes": 0,
                    "wake_clock": format_clock(wake_min),
                    "wake_minute": wake_min,
                }
                if eff_sched_nid:
                    res_out["effective_node_id"] = eff_sched_nid
                return res_out
    except Exception:
        pass

    return default_res


def resolve_effective_waypoint_location(
    session_id: int,
    wp: dict,
    session: Optional[dict] = None,
    session_time: Optional[tuple] = None,
    contacts_cache: Optional[dict] = None,
) -> str:
    """Returns the effective live target location for a waypoint, resolving NPC schedule if tagged."""
    info = get_waypoint_npc_schedule_info(
        session_id,
        wp,
        session=session,
        session_time=session_time,
        contacts_by_name=contacts_cache,
    )
    eff = info["effective_location"]
    if eff and "{" in eff and session_id:
        try:
            from mechanics.world.locations.hierarchy import resolve_session_location_tokens
            sess = session or db.get_session(session_id)
            scen_key = sess.get("scenario", "fantasy") if sess else "fantasy"
            eff = resolve_session_location_tokens(session_id, eff, scen_key)
        except Exception:
            pass
    return eff


def resolve_waypoint_target_npc(session_id: int, wp: dict) -> str:
    """
    Returns the target NPC for a waypoint, resolving or inferring from stage_label/session if empty.
    Checks:
    1. Explicit wp.get('target_npc')
    2. Active dialogue partner name mentioned in stage_label
    3. Room present NPCs mentioned in stage_label
    4. Known contacts mentioned in stage_label
    """
    t_npc = str((wp or {}).get("target_npc") or "").strip()
    if t_npc:
        return t_npc

    stage_label = str((wp or {}).get("stage_label") or "")
    if not stage_label or not session_id:
        return ""

    try:
        session = db.get_session(session_id)
        if not session:
            return ""

        stage_low = stage_label.lower()

        from mechanics.world.mobility import get_session_dialogue_partners
        dps = get_session_dialogue_partners(session) or []
        for dp in dps:
            dp_clean = str(dp).strip()
            if dp_clean and len(dp_clean) >= 3 and dp_clean.lower() in stage_low:
                return dp_clean

        curr_npcs = session.get("current_npcs")
        if curr_npcs:
            if isinstance(curr_npcs, str):
                import json
                try:
                    curr_npcs = json.loads(curr_npcs)
                except Exception:
                    curr_npcs = [curr_npcs]
            if isinstance(curr_npcs, list):
                for npc in curr_npcs:
                    npc_name = (npc.get("name") if isinstance(npc, dict) else str(npc)).strip()
                    if npc_name and len(npc_name) >= 3 and npc_name.lower() in stage_low:
                        return npc_name

        contacts = db.get_contacts(session_id, resolve_relations=False, ensure_scene=False) or []
        for c in contacts:
            c_name = str(c.get("name") or "").strip()
            if c_name and len(c_name) >= 3 and c_name.lower() in stage_low:
                return c_name
    except Exception:
        pass

    return ""


GENERIC_WAYPOINT_NPC_STOPWORDS = {
    "officer", "dispatch", "agency", "guard", "clerk", "receptionist",
    "staff", "patrol", "investigator", "detective", "worker", "soldier",
    "bureau", "directorate", "operative", "agent", "captain", "lieutenant",
    "sergeant", "commander", "specialist", "technician", "doctor", "researcher",
    "member", "patron", "civilian", "person", "contact", "handler",
    "central", "initiative", "division", "security", "defense", "control",
}


def can_waypoint_match_via_npc_presence(target_npc: str, stage_key: str = "", current_location: str = "", waypoint: Optional[dict] = None) -> bool:
    """
    Returns True ONLY if the waypoint stage is explicitly an NPC dialogue / interaction stage
    (e.g. talk_to, report_to, turn_in, rendezvous) AND not an arrival/investigation/combat stage.
    Site investigation or combat stages (e.g. investigate, slay, scout, explore, recover)
    CANNOT be satisfied merely because an NPC with a matching title/stopword is nearby.
    """
    st_low = str(stage_key or (waypoint.get("stage_key") if waypoint else "") or "").lower()
    st_lbl_low = str((waypoint.get("stage_label") if waypoint else "") or "").lower()
    comp_trig = str((waypoint.get("completion_trigger") if waypoint else "") or "").lower()
    dialogue_verbs = (
        "talk", "report", "turn_in", "speak", "deliver", "rendezvous", "return to",
        "interrogate", "question", "convince", "persuade", "negotiate", "interview",
        "consult", "confront", "discuss", "brief", "debrief", "meet with", "present",
    )
    has_dialogue_verb = any(k in st_low or k in st_lbl_low for k in dialogue_verbs)

    if waypoint:
        if waypoint.get("is_climax_stage") or str(waypoint.get("contract_type", "")).lower() == "climax":
            return False
        if (
            waypoint.get("target_location")
            and waypoint.get("follow_npc_schedule") == 0
            and comp_trig != "key_clue"
            and not has_dialogue_verb
        ):
            return False
    if comp_trig != "key_clue" and any(k in st_low for k in ("investigate", "explore", "slay", "combat", "scout", "breach", "clear", "neutralize", "gather_clues", "arrive", "travel", "reach")):
        return False
    if comp_trig == "arrival" and not has_dialogue_verb:
        return False
    if comp_trig in ("action_choice", "combat_victory", "skill_check", "inspect_prop", "resource_progress", "defeat_target") and not has_dialogue_verb:
        return False
    return True


def is_waypoint_npc_present_in_scene(
    session_id: int,
    target_npc: str,
    session: Optional[dict] = None,
) -> bool:
    """Returns True if target_npc is physically present at the player's current scene or active dialogue."""
    if not session_id or not target_npc or not str(target_npc).strip():
        return False

    try:
        session = session if session is not None else db.get_session(session_id)
        if not session:
            return False

        t_clean = str(target_npc).strip().lower()
        # Distinctive tokens only: must have length >= 4 and not be a generic organizational/occupational stopword
        t_distinctive = [w for w in t_clean.split() if len(w) >= 4 and w not in GENERIC_WAYPOINT_NPC_STOPWORDS]

        def _whole_term_in(term: str, haystack: str) -> bool:
            if not term or not haystack:
                return False
            if term.isascii():
                return bool(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", haystack))
            return term in haystack

        def _matches_npc(candidate_name: str) -> bool:
            c_low = candidate_name.strip().lower()
            if not c_low:
                return False
            # 1. Exact match always succeeds
            if t_clean == c_low:
                return True
            # 2. Whole-term containment (guarded against short/generic role words matching longer targets)
            if len(t_clean) >= 3 and _whole_term_in(t_clean, c_low):
                return True
            if len(c_low) >= 3 and c_low not in GENERIC_WAYPOINT_NPC_STOPWORDS:
                c_tokens = [tok for tok in re.findall(r"[^\W_]+", c_low) if len(tok) >= 3]
                if (c_tokens and any(tok not in GENERIC_WAYPOINT_NPC_STOPWORDS for tok in c_tokens)) or not c_low.isascii():
                    if _whole_term_in(c_low, t_clean):
                        return True
            # 3. Distinctive name matching (e.g. 'Astarion' or 'Vance' or 'Kurosawa')
            if t_distinctive and any(_whole_term_in(w, c_low) for w in t_distinctive):
                return True
            return False

        from mechanics.world.mobility import get_session_dialogue_partners
        dps = get_session_dialogue_partners(session) or []
        for dp in dps:
            if _matches_npc(str(dp)):
                return True

        curr_npcs = session.get("current_npcs")
        if curr_npcs:
            if isinstance(curr_npcs, str):
                import json
                try:
                    curr_npcs = json.loads(curr_npcs)
                except Exception:
                    curr_npcs = [curr_npcs]
            if isinstance(curr_npcs, list):
                for npc in curr_npcs:
                    npc_name = (npc.get("name") if isinstance(npc, dict) else str(npc))
                    if _matches_npc(npc_name):
                        return True
    except Exception:
        pass

    return False


# ---------------------------------------------------------------- Waypoint Stage Triggers

def get_matching_clue_sources_for_location(
    session_id: int,
    quest_id: str,
    sub_obj_id: Optional[int],
    current_location: str,
    waypoint: Optional[dict] = None,
    include_bonus: bool = True,
    dossier: Optional[dict] = None,
) -> dict:
    """
    Inspects dossier `main_stages[*].clue_sources` for a `"key_clue"` quest stage and returns
    all open sources matching `current_location` (or active witness NPC presence), plus any
    reachable unclaimed `bonus=True` corroborating sources on completed stages (E2).
    """
    result = {
        "is_clue_stage": False,
        "stage_index": int((waypoint or {}).get("stage_index") or 1),
        "stage": None,
        "open_sources": [],
        "matching_open_sources": [],
        "matching_bonus_sources": [],
    }
    if not session_id or not quest_id or (sub_obj_id not in (None, 0)):
        return result
    dos = dossier if dossier is not None else db.get_quest_dossier(session_id, quest_id)
    if not dos:
        return result
    climax = dos.get("climax_spec") or {}
    main_stages = [s for s in (climax.get("main_stages") or []) if isinstance(s, dict)]
    if not main_stages:
        return result

    target_stage = None
    wp_stage_idx = (waypoint or {}).get("stage_index")
    if wp_stage_idx is not None:
        target_stage = next((s for s in main_stages if int(s.get("stage_index") or 0) == int(wp_stage_idx)), None)
    if target_stage is None:
        target_stage = next((s for s in main_stages if str(s.get("status") or "").lower() == "active"), None)

    def _split_loc_segments(loc_str: str) -> list[str]:
        s = str(loc_str or "").strip()
        for sep in ("\u2794", "->", ">", "|"):
            if sep in s:
                return [p.strip().lower() for p in s.split(sep) if p.strip()]
        return [s.lower()] if s else []

    def _src_location_matches(s_loc: str) -> bool:
        if s_loc and check_location_matches_waypoint(current_location, s_loc, session_id=session_id):
            s_parts = _split_loc_segments(s_loc)
            c_parts = _split_loc_segments(current_location)
            if len(s_parts) >= 2:
                src_leaf = s_parts[-1]
                if src_leaf in ("main area", "area", "") and len(s_parts) >= 2:
                    src_leaf = s_parts[-2]
                if src_leaf in c_parts or (c_parts and c_parts[-1] == src_leaf):
                    return True
            else:
                return True
        return False

    def _match_source_copy(src: dict) -> Optional[dict]:
        if not isinstance(src, dict):
            return None
        s_loc = str(src.get("location") or "").strip()
        if str(src.get("kind") or "").lower() == "witness":
            s_npc = str(src.get("npc_name") or "").strip()
            if (
                s_npc
                and can_waypoint_match_via_npc_presence(s_npc, current_location=current_location, waypoint=waypoint)
                and is_waypoint_npc_present_in_scene(session_id, s_npc)
            ):
                return dict(src)
            if _src_location_matches(s_loc):
                s_copy = dict(src)
                s_copy["off_hours_fallback"] = True
                return s_copy
            return None
        if _src_location_matches(s_loc):
            return dict(src)
        return None

    if target_stage and not target_stage.get("is_climax_stage"):
        raw_sources = [s for s in (target_stage.get("clue_sources") or []) if isinstance(s, dict)]
        trig = str(target_stage.get("completion_trigger") or (waypoint or {}).get("completion_trigger") or "")
        if trig == "key_clue" or raw_sources:
            result["is_clue_stage"] = True
            result["stage_index"] = int(target_stage.get("stage_index") or result["stage_index"])
            result["stage"] = target_stage
            open_srcs = [s for s in raw_sources if str(s.get("status") or "open").lower() == "open"]
            result["open_sources"] = open_srcs
            result["matching_open_sources"] = [
                m for s in open_srcs if (m := _match_source_copy(s)) is not None
            ]

    if include_bonus:
        for st in main_stages:
            st_status = str(st.get("status") or "").lower()
            if not (st.get("completed") or st_status in ("completed", "bypassed")):
                continue
            for src in (st.get("clue_sources") or []):
                if not isinstance(src, dict):
                    continue
                if bool(src.get("bonus")) and str(src.get("status") or "").lower() != "claimed":
                    b_copy = _match_source_copy(src)
                    if b_copy is not None:
                        b_copy["_stage_index"] = int(st.get("stage_index") or 1)
                        b_copy["_stage_label"] = str(st.get("stage_label") or st.get("label") or "")
                        b_copy["_key_clue"] = dict(st.get("key_clue") or {})
                        result["matching_bonus_sources"].append(b_copy)

    return result


def try_advance_on_arrival(session_id: int, quest_id: str, sub_obj_id: Optional[int], current_location: str) -> Optional[dict]:
    """Called every turn. Advances 'arrival' trigger stages when player reaches target,
    reaches the target NPC's live scheduled location, or encounters the NPC in the scene."""
    waypoint = db.get_active_waypoint(session_id, quest_id, sub_obj_id)
    if not waypoint:
        return None
    # E1: Engage chapter Threat Clock if player arrives at Story Stage 1 (even on key_clue triggers)
    if session_id and quest_id and (sub_obj_id in (None, 0)) and int(waypoint.get("stage_index") or 1) == 1:
        t_loc_e1 = resolve_effective_waypoint_location(session_id, waypoint) or waypoint.get("target_location", "")
        at_stage1 = bool(t_loc_e1 and check_location_matches_waypoint(current_location, t_loc_e1, session_id=session_id))
        if not at_stage1 and str(waypoint.get("completion_trigger") or "") == "key_clue":
            ci = get_matching_clue_sources_for_location(session_id, quest_id, sub_obj_id, current_location, waypoint=waypoint, include_bonus=False)
            at_stage1 = bool(ci.get("matching_open_sources"))
        if at_stage1:
            try:
                from mechanics.narrative.threat_clock import mark_chapter_clock_engaged
                mark_chapter_clock_engaged(session_id, quest_id)
            except Exception:
                pass
    if waypoint.get("completion_trigger") != "arrival":
        return None
    # Spatial Graph & Hierarchy Matching
    session = db.get_session(session_id)
    curr_min = session.get("current_minute", 480) if session else 480
    from mechanics.narrative.blueprints import evaluate_waypoint_time_window
    time_eval = evaluate_waypoint_time_window(curr_min, waypoint.get("valid_time_phases"))
    if not time_eval.get("is_valid", True):
        return None

    curr_node = session.get("current_node_id") if session else None
    target_node = waypoint.get("target_node_id")
    target_loc = resolve_effective_waypoint_location(session_id, waypoint)
    static_target_loc = waypoint.get("static_target_location") or waypoint.get("target_location", "")
    target_npc = resolve_waypoint_target_npc(session_id, waypoint) or waypoint.get("target_npc", "")

    if not target_node and target_loc:
        try:
            target_node = db.resolve_node_id_from_location(session_id, target_loc)
        except Exception:
            target_node = None

    matched = False
    if curr_node and target_node:
        matched = (
            curr_node == target_node
            or db.is_descendant_of(session_id, curr_node, target_node)
            or db.is_descendant_of(session_id, target_node, curr_node)
        )
    if not matched and target_loc:
        matched = check_location_matches_waypoint(current_location, target_loc)
    if not matched and static_target_loc:
        matched = check_location_matches_waypoint(current_location, static_target_loc)
    if not matched and target_npc and can_waypoint_match_via_npc_presence(target_npc, waypoint=waypoint) and is_waypoint_npc_present_in_scene(session_id, target_npc):
        matched = True
    elif not matched and not curr_node and not target_loc and not target_npc:
        matched = True

    # Spared deception guaranteed turn-in arrival check
    if not matched:
        quest = db.get_quest_by_id(session_id, quest_id)
        if quest and quest.get("resolution_approach") == "spared_deception":
            c_npc = quest.get("client_npc", "")
            c_loc = quest.get("client_location", "")
            if (c_loc and check_location_matches_waypoint(current_location, c_loc)) or (
                c_npc and is_waypoint_npc_present_in_scene(session_id, c_npc)
            ):
                matched = True

    if not matched:
        # Check if the player traveled directly to the immediately following stage's location,
        # bypassing an 'arrival'-only scouting waypoint.
        all_wps = db.get_quest_waypoints(session_id, quest_id, sub_obj_id) or []
        next_stage = next(
            (w for w in all_wps if w.get("stage_index") == waypoint.get("stage_index", 1) + 1 and w.get("status") == "locked"),
            None
        )
        if not next_stage:
            return None
        next_target_node = next_stage.get("target_node_id")
        next_target_loc = next_stage.get("target_location", "")
        if not next_target_node and next_target_loc:
            try:
                next_target_node = db.resolve_node_id_from_location(session_id, next_target_loc)
            except Exception:
                next_target_node = None
        next_matched = False
        if curr_node and next_target_node:
            next_matched = db.is_descendant_of(session_id, curr_node, next_target_node) or db.is_descendant_of(session_id, next_target_node, curr_node)
        elif next_target_loc:
            next_matched = check_location_matches_waypoint(current_location, next_target_loc)
        if not next_matched:
            return None

    next_wp = db.advance_waypoint(session_id, quest_id, waypoint["stage_index"], sub_obj_id)
    stage_complete = next_wp is None

    notice = {
        "quest_id": quest_id,
        "sub_obj_id": sub_obj_id,
        "stage_completed": waypoint["stage_index"],
        "stage_label": waypoint.get("stage_label", ""),
        "next_waypoint": dict(next_wp) if next_wp else None,
        "all_stages_complete": stage_complete,
        "trigger": "arrival",
    }

    if stage_complete:
        if sub_obj_id is not None:
            db.mark_sub_objective_completed_in_quest(session_id, quest_id, sub_obj_id)
            notice["sub_obj_completed"] = True
        else:
            notice["quest_completed"] = True

    return notice


def _extract_keyword_stems(words: list[str] | set[str]) -> set[str]:
    stems = set()
    for w in words:
        w = w.lower().strip()
        if len(w) < 4:
            continue
        stems.add(w)
        for suf in ("tions", "tion", "ings", "ing", "ments", "ment", "ness", "ities", "ity", "ed", "es", "ic", "al", "ly", "s"):
            if w.endswith(suf) and len(w) - len(suf) >= 4:
                stems.add(w[:-len(suf)])
                break
    return stems


def check_action_matches_waypoint(
    action_text: str, narrative: str, stage_label: str,
    sub_obj_text: str = "", target_npc: str = ""
) -> bool:
    """
    Verifies that the player's action or resulting narrative actually pertains
    to the specific waypoint stage or sub-objective before marking it completed.
    Prevents unrelated skill checks (e.g. asking gossip) from completing unrelated
    objectives (e.g. searching for a dropped notebook in the debris).
    """
    if not action_text and not narrative:
        return True

    act_lower = str(action_text or "").lower()
    narr_lower = str(narrative or "").lower()

    # Movement and travel actions must NOT complete interaction/skill check waypoints
    from mechanics.narrative.intent import is_travel_action, is_conversational_action
    if is_travel_action(action_text):
        return False

    # Conversational / social dialogue actions must NOT complete physical / mechanical / environmental waypoints
    # unless the waypoint explicitly targets that NPC or is a dialogue objective.
    is_conversational_action_flag = is_conversational_action(action_text)

    stage_lower = str(stage_label or "").lower()
    is_dialogue_stage = any(
        dw in stage_lower
        for dw in ("talk", "speak", "ask", "interrogate", "question", "interview", "convince", "persuade", "negotiate", "consult", "inquire", "gossip", "bribe", "confront", "discuss", "chat", "non-hostile", "contain", "pacify", "calm")
    ) or bool(target_npc and str(target_npc).strip())

    if is_conversational_action_flag and not is_dialogue_stage:
        return False

    # 1. Target NPC match
    if target_npc and str(target_npc).strip():
        t_npc_words = [w for w in str(target_npc).lower().split() if len(w) >= 3]
        # Target NPC must be actively mentioned or addressed in the player's action
        if any(w in act_lower for w in t_npc_words):
            return True
        # Or if player action has interaction verbs and NPC is actively interacted with in narrative
        interact_verbs = {"talk", "speak", "ask", "confront", "approach", "deliver", "give", "hand", "tell", "interrogate", "bribe", "persuade", "consult", "meet", "spare"}
        if any(v in act_lower for v in interact_verbs) and any(w in narr_lower for w in t_npc_words):
            return True

    # 2. Substantive keyword extraction from stage label and sub objective
    stop_words = {
        "the", "and", "for", "with", "from", "into", "onto", "among", "using", "about",
        "your", "their", "this", "that", "some", "what", "which", "when", "where",
        "search", "check", "area", "place", "room", "rooms", "zone", "find", "reach", "travel",
        "examine", "inspect", "investigate", "look", "stage", "task", "objective",
        "make", "take", "give", "help", "need", "must", "will", "have",
        "classroom", "classrooms", "office", "offices", "hallway", "hallways", "corridor",
        "corridors", "building", "buildings", "desk", "desks", "return", "returning",
        "arrive", "arrival", "arriving", "student", "students", "homeroom", "school",
        "before", "after", "through", "across", "under", "over", "between", "while", "during",
        "again", "then"
    }

    stage_words = re.findall(r"\b[a-z]{3,}\b", stage_lower)
    stage_keywords = _extract_keyword_stems([w for w in stage_words if w not in stop_words])

    sub_words = re.findall(r"\b[a-z]{4,}\b", str(sub_obj_text or "").lower())
    sub_keywords = _extract_keyword_stems([w for w in sub_words if w not in stop_words])

    # Priority A: Player's action text directly targets stage keywords or sub-objective keywords
    if stage_keywords and any(kw in act_lower for kw in stage_keywords):
        return True
    if sub_keywords and any(kw in act_lower for kw in sub_keywords):
        return True

    # Priority B: Outcome narrative describes completing the stage.
    if stage_keywords:
        if any(kw in narr_lower for kw in stage_keywords):
            return True
        return False

    if sub_keywords:
        if any(kw in narr_lower for kw in sub_keywords):
            return True
        return False

    return True


def does_action_target_waypoint(
    session_id: int, quest_id: str, sub_obj_id: Optional[int],
    current_location: str, action_text: str = "", narrative: str = "", sub_obj_text: str = "",
    is_quest_action: bool = False, action_quest_id: str = "", action_sub_obj_id: Optional[int] = None
) -> Optional[dict]:
    """
    Checks if the player is at the active waypoint's location (or NPC present)
    AND verifies that the action targets this waypoint.
    Returns the active waypoint dict on match, or None.
    """
    waypoint = db.get_active_waypoint(session_id, quest_id, sub_obj_id)
    if not waypoint:
        return None
    is_rumor_inq_act = (
        is_quest_action
        and str(quest_id).startswith(("MNR-", "RMR-"))
        and (str(action_quest_id) == str(quest_id))
    )
    if waypoint.get("completion_trigger") not in ("skill_check", "inspect_prop", "talk_to_npc", "resource_progress", "defeat_target", "action", "key_clue"):
        if not is_rumor_inq_act:
            return None

    # Key-Clue multi-source matching (active open clue_sources + E2 bonus corroborating sources)
    if str(waypoint.get("completion_trigger") or "") == "key_clue" or (sub_obj_id in (None, 0)):
        clue_info = get_matching_clue_sources_for_location(
            session_id,
            quest_id,
            sub_obj_id,
            current_location,
            waypoint=waypoint,
            include_bonus=True,
        )
        if clue_info.get("is_clue_stage") or clue_info.get("matching_bonus_sources"):
            open_hits = clue_info.get("matching_open_sources") or []
            if open_hits:
                act_low = str(action_text or "").lower()
                # Prefer source whose NPC or approach_hint words overlap action_text
                picked = open_hits[0]
                best_score = -1
                for cand in open_hits:
                    sc = 0
                    c_npc = str(cand.get("npc_name") or "").lower().strip()
                    if c_npc and any(tok in act_low for tok in c_npc.split() if len(tok) >= 3):
                        sc += 3
                    hint_words = [w for w in re.findall(r"\b[a-z]{4,}\b", str(cand.get("approach_hint") or "").lower()) if w not in ("from", "with", "into", "this", "that")]
                    sc += sum(1 for w in hint_words if w in act_low)
                    if sc > best_score:
                        best_score = sc
                        picked = cand
                is_action_match = False
                if is_quest_action:
                    if action_quest_id and str(action_quest_id) != str(quest_id):
                        is_action_match = False
                    elif action_sub_obj_id is not None and sub_obj_id is not None and int(action_sub_obj_id) != int(sub_obj_id):
                        is_action_match = False
                    else:
                        is_action_match = True
                else:
                    stage_lbl = str(waypoint.get("stage_label") or "")
                    kc_title = str(((clue_info.get("stage") or {}).get("key_clue") or {}).get("title") or "")
                    combined_hint = f"{stage_lbl} {picked.get('approach_hint', '')} {kc_title}".strip()
                    p_npc = str(picked.get("npc_name") or "") if str(picked.get("kind") or "").lower() == "witness" else ""
                    is_action_match = check_action_matches_waypoint(action_text, narrative, combined_hint, sub_obj_text, p_npc)
                if is_action_match:
                    wp_copy = dict(waypoint)
                    wp_copy["_matched_clue_source_id"] = str(picked.get("source_id") or "")
                    wp_copy["_matched_clue_source"] = dict(picked)
                    wp_copy["_matched_clue_stage_index"] = int(clue_info.get("stage_index") or waypoint.get("stage_index") or 1)
                    wp_copy["_is_bonus_clue"] = False
                    return wp_copy
            # Check E2 bonus corroborating source on a completed stage
            bonus_hits = clue_info.get("matching_bonus_sources") or []
            if bonus_hits:
                b_pick = bonus_hits[0]
                b_npc = str(b_pick.get("npc_name") or "") if str(b_pick.get("kind") or "").lower() == "witness" else ""
                b_kc_title = str((b_pick.get("_key_clue") or {}).get("title") or "")
                b_match = False
                if is_quest_action and (not action_quest_id or str(action_quest_id) == str(quest_id)):
                    if action_sub_obj_id is None or sub_obj_id is None or int(action_sub_obj_id) == int(sub_obj_id):
                        b_match = True
                elif check_action_matches_waypoint(action_text, narrative, f"{b_pick.get('approach_hint', '')} {b_kc_title} bonus corroborate", "", b_npc):
                    b_match = True
                if b_match:
                    wp_copy = dict(waypoint)
                    wp_copy["_matched_clue_source_id"] = str(b_pick.get("source_id") or "")
                    wp_copy["_matched_clue_source"] = dict(b_pick)
                    wp_copy["_matched_clue_stage_index"] = int(b_pick.get("_stage_index") or 1)
                    wp_copy["_is_bonus_clue"] = True
                    return wp_copy
            if str(waypoint.get("completion_trigger") or "") == "key_clue":
                return None
    target_node = waypoint.get("target_node_id")
    target_loc = resolve_effective_waypoint_location(session_id, waypoint)
    static_target_loc = waypoint.get("static_target_location") or waypoint.get("target_location", "")
    target_npc = waypoint.get("target_npc", "")
    session = db.get_session(session_id)
    curr_node = session.get("current_node_id") if session else None

    if not target_node and target_loc:
        try:
            target_node = db.resolve_node_id_from_location(session_id, target_loc)
        except Exception:
            target_node = None

    matched = False
    if curr_node and target_node:
        matched = (
            curr_node == target_node
            or db.is_descendant_of(session_id, curr_node, target_node)
            or db.is_descendant_of(session_id, target_node, curr_node)
        )
    if not matched and target_loc:
        matched = check_location_matches_waypoint(current_location, target_loc)
    if not matched and static_target_loc:
        matched = check_location_matches_waypoint(current_location, static_target_loc)
    if not matched and target_npc and can_waypoint_match_via_npc_presence(target_npc, waypoint=waypoint) and is_waypoint_npc_present_in_scene(session_id, target_npc):
        matched = True
    elif not matched and is_rumor_inq_act:
        matched = True
    elif not matched and not curr_node and not target_loc and not target_npc:
        matched = True

    if not matched:
        return None

    # 1. If this action was an explicit quest-bound action:
    if is_quest_action:
        if action_quest_id and str(action_quest_id) != str(quest_id):
            return None
        if action_sub_obj_id is not None and sub_obj_id is not None and int(action_sub_obj_id) != int(sub_obj_id):
            return None
        return waypoint

    # 2. For un-tagged / custom / LLM actions:
    stage_label = waypoint.get("stage_label", "")
    target_npc = waypoint.get("target_npc", "")
    if check_action_matches_waypoint(action_text, narrative, stage_label, sub_obj_text, target_npc):
        return waypoint

    return None


def try_complete_on_skill_check(
    session_id: int, quest_id: str, sub_obj_id: Optional[int],
    current_location: str, check_success: bool, check_result_tier: str = "success",
    action_text: str = "", narrative: str = "", sub_obj_text: str = "",
    is_quest_action: bool = False, action_quest_id: str = "", action_sub_obj_id: Optional[int] = None
) -> Optional[dict]:
    """Called when a choice resolves. Advances 'skill_check' trigger stages on success at target."""
    waypoint = does_action_target_waypoint(
        session_id=session_id,
        quest_id=quest_id,
        sub_obj_id=sub_obj_id,
        current_location=current_location,
        action_text=action_text,
        narrative=narrative,
        sub_obj_text=sub_obj_text,
        is_quest_action=is_quest_action,
        action_quest_id=action_quest_id,
        action_sub_obj_id=action_sub_obj_id,
    )
    if not waypoint:
        return None
    if not check_success:
        return None

    if waypoint.get("_is_bonus_clue"):
        return {
            "quest_id": quest_id,
            "sub_obj_id": sub_obj_id,
            "stage_completed": None,
            "stage_label": str((waypoint.get("_matched_clue_source") or {}).get("_stage_label") or waypoint.get("stage_label", "")),
            "next_waypoint": db.get_active_waypoint(session_id, quest_id, sub_obj_id),
            "all_stages_complete": False,
            "trigger": "bonus_clue",
            "is_bonus_clue": True,
            "matched_clue_source_id": str(waypoint.get("_matched_clue_source_id") or ""),
            "matched_clue_source": dict(waypoint.get("_matched_clue_source") or {}),
            "matched_clue_stage_index": int(waypoint.get("_matched_clue_stage_index") or 1),
        }

    resource_target = int(waypoint.get("resource_target", 0))

    if resource_target > 0:
        tier_gains = {
            "critical_success": resource_target,
            "success": max(1, resource_target // 2),
            "partial": max(1, resource_target // 4),
            "failure": 0,
        }
        gain = tier_gains.get(check_result_tier, tier_gains["success"])
        progress = db.update_waypoint_resource_progress(session_id, quest_id, waypoint["stage_index"], gain, sub_obj_id)
        if not progress.get("complete"):
            return {
                "quest_id": quest_id,
                "sub_obj_id": sub_obj_id,
                "stage_completed": None,
                "stage_label": waypoint.get("stage_label", ""),
                "next_waypoint": dict(waypoint),
                "all_stages_complete": False,
                "trigger": "resource_progress",
                "resource_collected": progress["collected"],
                "resource_target": progress["target"],
            }

    next_wp = db.advance_waypoint(session_id, quest_id, waypoint["stage_index"], sub_obj_id)
    stage_complete = next_wp is None

    notice = {
        "quest_id": quest_id,
        "sub_obj_id": sub_obj_id,
        "stage_completed": waypoint["stage_index"],
        "stage_label": waypoint.get("stage_label", ""),
        "next_waypoint": dict(next_wp) if next_wp else None,
        "all_stages_complete": stage_complete,
        "trigger": waypoint.get("completion_trigger", "skill_check"),
    }
    if waypoint.get("_matched_clue_source_id"):
        notice["matched_clue_source_id"] = str(waypoint.get("_matched_clue_source_id") or "")
        notice["matched_clue_source"] = dict(waypoint.get("_matched_clue_source") or {})
        notice["matched_clue_stage_index"] = int(waypoint.get("_matched_clue_stage_index") or waypoint["stage_index"])

    if resource_target > 0:
        notice["resource_collected"] = resource_target
        notice["resource_target"] = resource_target

    if stage_complete:
        if sub_obj_id is not None:
            db.mark_sub_objective_completed_in_quest(session_id, quest_id, sub_obj_id)
            notice["sub_obj_completed"] = True
        else:
            notice["quest_completed"] = True

    return notice


def get_story_quest_climax_location(session_id: int, allow_premature: bool = False) -> tuple[Optional[dict], Optional[str]]:
    """
    Returns (story_quest_dict, climax_location_str) if the active story quest has
    completed all sub-objectives and is ready for the Climax Encounter.
    """
    if not session_id:
        return None, None
    story_quest = db.get_active_story_quest(session_id)
    if not story_quest or story_quest.get("status") != "Active":
        return None, None

    sub_objs = story_quest.get("sub_objectives", []) or []
    if not allow_premature:
        if not sub_objs or not db.is_quest_main_objectives_complete(sub_objs):
            return None, None

    # All sub-objectives are done! Resolve the Climax Encounter location
    qid = story_quest.get("quest_id", "")

    # 1. Check if an explicit whole-quest / climax waypoint exists in DB
    climax_wp_loc = db.get_quest_waypoint_target_location(session_id, qid, mode="climax_null_sub")
    if climax_wp_loc:
        return story_quest, climax_wp_loc

    # Check compiled QuestDossier gate rules BEFORE premature gate refusal
    dossier = db.get_quest_dossier(session_id, qid)
    if dossier and isinstance(dossier, dict):
        story_quest["dossier"] = dossier
        cs_dos = dossier.get("climax_spec") or {}
        climax_loc_dos = str(cs_dos.get("location") or "").strip()
        if str(dossier.get("status_stage") or "") == "compiled" and climax_loc_dos:
            gate_mode = str(cs_dos.get("gate_type") or cs_dos.get("gate_mode") or "open").lower()
            is_unlocked = bool(cs_dos.get("is_unlocked"))
            if allow_premature and gate_mode == "secret" and not is_unlocked and not (sub_objs and db.is_quest_main_objectives_complete(sub_objs)):
                return None, None
            if gate_mode == "open" and is_unlocked:
                return story_quest, climax_loc_dos

    # Phase 5 A11: For premature confrontation, only an explicit showdown venue (sub_obj_id IS NULL) or open compiled Climax qualifies
    if allow_premature and not (sub_objs and db.is_quest_main_objectives_complete(sub_objs)):
        return None, None

    # 2. Check if the compiled quest dossier specifies a canonical climax location
    if dossier and isinstance(dossier, dict):
        climax_loc = (dossier.get("climax_spec") or {}).get("location")
        if climax_loc:
            return story_quest, climax_loc

    # 3. Check the target location of the highest sub_obj_id waypoint
    highest_sub_loc = db.get_quest_waypoint_target_location(session_id, qid, mode="highest_sub")
    if highest_sub_loc:
        return story_quest, highest_sub_loc

    # 3. Check session's current location or seeded locations
    session = db.get_session(session_id)
    cur_loc = session.get("current_location", "") if session else ""
    if cur_loc:
        return story_quest, cur_loc

    locs = db.get_session_locations(session_id)
    if locs:
        z = locs[0].get("zone_name", "")
        p = locs[0].get("primary_name", "")
        if z and p:
            return story_quest, f"{z} ➔ {p}"

    return story_quest, "Local Area"


