"""
mechanics/world/presence_resolver.py — Unified 6-Tier Pre-Turn Presence Resolver
================================================================================
Deterministic closed-world NPC presence evaluation before narrative generation.
Resolves who is physically present at a location across 6 strict precedence tiers:

  Tier 1 (party): Party members, companions, temporary escorts, and `staff_status == "in_party"`.
  Tier 2 (commitment): Confirmed active commitments / phone appointments within bounded window.
  Tier 3 (quest_pin): Active quest/bounty waypoints and story objectives pinned at this node.
  Tier 4 (doorbell_answered / doorbell_events): Resident doorbell etiquette at unlocked residences.
  Tier 5 (schedule): Active anchor-node schedules (`world_roster`) + legacy/materialized legacy pools.
  Tier 6 (crowd_flavor): Atmospheric unnamed venue flavor when no NPC is present (zero DB writes).
"""
from __future__ import annotations

from typing import Any, Mapping

import db
from mechanics.world.anchor_schedule import resolve_anchor_schedule_nodes
from mechanics.world.locations.residence_fog import (
    SHARED_ABSTRACT_RESIDENCE_NODE,
    can_materialize_npc_residence,
)
from mechanics.world.npc_schedule import get_npc_scheduled_node_id
from mechanics.world.presence_doorbell import check_doorbell_etiquette
from mechanics.world.presence_graph import (
    format_node_display_label,
    is_deceased_or_arrested,
    is_node_descendant_in_memory,
    is_private_home_or_wilderness,
    location_targets_node,
    npc_aliases,
    parse_dict,
    residence_matches_node,
    resolve_node_id_in_memory,
    schedule_matches_node,
    slugify_key,
)
from mechanics.world.presence_preload import (
    _PresenceContext,
    _preload_presence_context,
    preload_presence_context,
)
from mechanics.world.venue_seeder import format_venue_crowd_flavor
from mechanics.world.waypoints.matching import (
    get_waypoint_npc_schedule_info,
    is_hostile_or_lair_waypoint,
)
from mechanics.world.world_schedule import is_weekend

_CRISIS_KEYWORDS: tuple[str, ...] = (
    "crisis", "ambush", "emergency", "under siege", "attack", "assault", "rescue",
)
_ARRIVED_GRACE_MINUTES = 120


def _compute_commitment_abs_window(row: Mapping[str, Any]) -> tuple[int, int, int]:
    s_day = max(1, int(row.get("scheduled_day") or 1))
    s_min = max(0, int(row.get("start_minute") if row.get("start_minute") is not None else 0))
    raw_end = int(row.get("end_minute") if row.get("end_minute") is not None else 1439)
    if raw_end >= 1440:
        extra_days, e_min = divmod(raw_end, 1440)
        e_day = s_day + extra_days
    else:
        e_min = max(0, raw_end)
        if row.get("end_day") is not None:
            e_day = max(s_day, int(row["end_day"]))
        elif e_min < s_min:
            e_day = s_day + 1
        else:
            e_day = s_day
    return (s_day - 1) * 1440 + s_min, (e_day - 1) * 1440 + e_min, e_day


def _resolve_tier1_party(ctx: _PresenceContext, party_names: set[str] | None) -> None:
    tier1_entries: list[dict[str, Any]] = []
    raw_party_lists = [
        list(party_names or ()),
        list(ctx.session_dict.get("party_npcs") or ()),
        list(ctx.session_dict.get("temporary_companions") or ()),
        list(ctx.session_dict.get("party") or ()),
    ]
    for grp in raw_party_lists:
        for item in grp:
            obj = item[0] if isinstance(item, (tuple, list)) and item else item
            if isinstance(obj, Mapping):
                tier1_entries.append(dict(obj))
            elif isinstance(obj, str) and obj.strip():
                tier1_entries.append({"name": obj.strip()})
    for r in ctx.roster_rows:
        if str(r.get("staff_status") or "").strip().lower() == "in_party":
            tier1_entries.append(dict(r))
    for entry in tier1_entries:
        ctx.stage(entry, 1, "party")


def _resolve_tier2_rendezvous(ctx: _PresenceContext) -> None:
    if ctx.sid <= 0 or (not ctx.eff_node_id and not ctx.eff_loc):
        return
    abs_now = (ctx.safe_day - 1) * 1440 + ctx.safe_min
    for rc in ctx.active_commitments:
        if not isinstance(rc, Mapping):
            continue
        cands: list[tuple[str, str]] = []
        cand_aliases: set[str] = set()
        for p in (rc.get("participants") or []):
            if not isinstance(p, Mapping):
                continue
            pk = str(p.get("person_key") or p.get("npc_id") or "").strip()
            p_name = str(p.get("name") or p.get("npc_name") or "").strip()
            if pk.lower() == "player" or pk.lower().startswith("player:") or p_name.lower() in ctx.player_names:
                continue
            disp = p_name or pk.replace("_", " ").title()
            if disp:
                nid_val = pk or slugify_key(disp)
                cands.append((nid_val, disp))
                cand_aliases.update({disp.lower(), slugify_key(disp), pk.lower()})
        if not cands:
            tgt_e = str(rc.get("target_entity") or "").strip()
            src_e = str(rc.get("source_entity") or "").strip()
            cand_e = tgt_e if (tgt_e and tgt_e.lower() != "player") else src_e
            if cand_e and cand_e.lower() not in ctx.player_names:
                disp = cand_e.replace("_", " ").title() if "_" in cand_e else cand_e
                cands.append((cand_e.lower(), disp))
                cand_aliases.update({disp.lower(), slugify_key(disp), cand_e.lower()})
        if not cands:
            continue

        status_val = str(rc.get("status") or "pending").strip().lower()
        a_start, a_end, max_day = _compute_commitment_abs_window(rc)
        if status_val in ("arrived", "in_progress"):
            in_grace = (a_start - 15) <= abs_now <= (a_end + _ARRIVED_GRACE_MINUTES)
            same_day_active_dp = ctx.safe_day <= max_day and bool(cand_aliases & ctx.active_dialogue_partners)
            if not (in_grace or same_day_active_dp):
                continue
        else:
            if not ((a_start - 15) <= abs_now <= a_end):
                continue

        r_nid = str(rc.get("target_node_id") or "").strip()
        r_loc = str(rc.get("target_location") or "").strip()
        if not location_targets_node(r_nid, r_loc, ctx.eff_node_id, ctx.eff_loc, ctx.nodes_by_id, ctx.loc_cache):
            continue

        for npc_id_val, disp_name in cands:
            ctx.tier2_aliases.update({disp_name.lower(), slugify_key(disp_name), npc_id_val.lower()})
            ctx.stage({"npc_id": npc_id_val, "name": disp_name}, 2, "commitment")


def _collect_tier3_candidate_waypoints(ctx: _PresenceContext) -> list[dict[str, Any]]:
    candidate_wps: list[dict[str, Any]] = [dict(wp) for wp in ctx.active_wps if isinstance(wp, Mapping)]
    active_wp_keys = {
        (str(wp.get("quest_id") or ""), wp.get("sub_obj_id"))
        for wp in candidate_wps
        if wp.get("quest_id")
    }
    if not isinstance(ctx.story_quest, Mapping):
        return candidate_wps

    sq_qid = str(ctx.story_quest.get("quest_id") or "")
    sq_loc = str(
        ctx.story_quest.get("target_location")
        or ctx.story_quest.get("location")
        or ctx.story_quest.get("client_location")
        or ""
    ).strip()
    sq_node = str(ctx.story_quest.get("target_node_id") or "").strip()
    sub_objs = ctx.story_quest.get("sub_objectives") or []
    has_active_sub = False
    for idx, so in enumerate(sub_objs):
        if isinstance(so, Mapping) and not so.get("completed"):
            has_active_sub = True
            so_id = so.get("id", idx + 1)
            if sq_qid and (sq_qid, so_id) in active_wp_keys:
                continue
            if so.get("target_npc"):
                so_wp = dict(so)
                active_nested = so.get("active_waypoint")
                if isinstance(active_nested, Mapping):
                    for inherit_k in (
                        "follow_npc_schedule",
                        "target_node_id",
                        "bounty_pattern",
                        "completion_trigger",
                        "valid_time_phases",
                        "is_crisis",
                    ):
                        if inherit_k not in so_wp and active_nested.get(inherit_k) not in (None, ""):
                            so_wp[inherit_k] = active_nested[inherit_k]
                if not str(so_wp.get("target_location") or "").strip() and sq_loc:
                    so_wp["target_location"] = sq_loc
                if not str(so_wp.get("location") or "").strip() and sq_loc:
                    so_wp["location"] = sq_loc
                if not str(so_wp.get("target_node_id") or "").strip() and sq_node:
                    so_wp["target_node_id"] = sq_node
                if not str(so_wp.get("stage_label") or "").strip():
                    so_wp["stage_label"] = str(so.get("text") or so.get("stage_label") or "")
                candidate_wps.append(so_wp)
    if not has_active_sub and ctx.story_quest.get("target_npc"):
        if not (sq_qid and (sq_qid, None) in active_wp_keys):
            sq_wp = dict(ctx.story_quest)
            if not str(sq_wp.get("stage_label") or "").strip():
                sq_wp["stage_label"] = str(ctx.story_quest.get("title") or ctx.story_quest.get("objective") or "")
            candidate_wps.append(sq_wp)
    return candidate_wps


def _resolve_tier3_waypoints(ctx: _PresenceContext) -> None:
    for wp in _collect_tier3_candidate_waypoints(ctx):
        t_npc = str(wp.get("target_npc") or "").strip()
        if not t_npc:
            continue
        r_row, c_row = ctx.find_linked(t_npc)
        wp_aliases = npc_aliases(r_row) | npc_aliases(c_row) | {t_npc.lower(), slugify_key(t_npc)}
        if wp_aliases & ctx.casualty_keys:
            continue

        wp_loc = str(wp.get("target_location") or wp.get("location") or "").strip()
        wp_node = str(wp.get("target_node_id") or "").strip()
        is_hostile = is_hostile_or_lair_waypoint(wp)
        wp_blob = f"{wp.get('stage_label', '')} {wp.get('title', '')} {wp.get('objective', '')} {wp.get('notes', '')}".lower()
        is_crisis = bool(wp.get("is_crisis")) or any(k in wp_blob for k in _CRISIS_KEYWORDS)
        follow_sched = bool(wp.get("follow_npc_schedule"))

        if is_hostile or is_crisis or not follow_sched:
            if not location_targets_node(wp_node, wp_loc, ctx.eff_node_id, ctx.eff_loc, ctx.nodes_by_id, ctx.loc_cache):
                continue
            if is_crisis:
                ctx.tier3_crisis_aliases.update(wp_aliases)
            ctx.stage({"name": t_npc, "npc_id": (c_row or r_row or {}).get("npc_id") or slugify_key(t_npc)}, 3, "quest_pin")
            continue

        sched_info = get_waypoint_npc_schedule_info(
            ctx.sid,
            wp,
            current_minute=ctx.safe_min,
            session=ctx.session_dict,
            session_time=(ctx.safe_day, ctx.safe_min, ctx.eff_turn),
            contacts_by_name=ctx.contacts_by_name,
            roster_by_key=ctx.roster_by_key,
            nodes_by_id=ctx.nodes_by_id,
            active_events=ctx.active_events,
            primary_property=ctx.prim_prop,
            primary_property_loaded=ctx.prim_prop_loaded,
            contacts=ctx.contacts,
            person_ties=ctx.person_ties,
            active_commitments=ctx.active_commitments,
            legacy_entries_by_key=ctx.legacy_enrichment_by_key,
        )
        eff_sched_loc = str(sched_info.get("effective_location") or "").strip()
        eff_sched_nid = str(sched_info.get("effective_node_id") or "").strip()
        if eff_sched_loc and eff_sched_loc != wp_loc:
            wp_loc = eff_sched_loc
            if eff_sched_nid:
                wp_node = eff_sched_nid
            elif ctx.nodes_by_id:
                wp_node = (
                    resolve_node_id_in_memory(wp_loc, ctx.nodes_by_id, prefer_facility=False, cache=ctx.loc_cache)
                    or resolve_node_id_in_memory(wp_loc, ctx.nodes_by_id, prefer_facility=True, cache=ctx.loc_cache)
                    or wp_node
                )
        elif eff_sched_nid:
            wp_node = eff_sched_nid

        if not location_targets_node(wp_node, wp_loc, ctx.eff_node_id, ctx.eff_loc, ctx.nodes_by_id, ctx.loc_cache):
            continue
        if not sched_info.get("is_off_duty"):
            ctx.stage({"name": t_npc, "npc_id": (c_row or r_row or {}).get("npc_id") or slugify_key(t_npc)}, 3, "quest_pin")


def _resolve_tier4_doorbell(ctx: _PresenceContext) -> None:
    if not ctx.eff_node_id or ctx.eff_node_id == SHARED_ABSTRACT_RESIDENCE_NODE:
        return
    override_pin_aliases = ctx.tier2_aliases | ctx.tier3_crisis_aliases

    for r_row, c_row, merged_npc, aliases in ctx.unified_records:
        if aliases & ctx.casualty_keys:
            continue
        npc_home = str(merged_npc.get("home_node_id") or parse_dict(merged_npc.get("basic_info")).get("home_node_id") or "").strip()
        if not residence_matches_node(npc_home, ctx.eff_node_id, ctx.nodes_by_id):
            continue

        is_unlocked = can_materialize_npc_residence(
            ctx.sid if ctx.sid > 0 else None,
            merged_npc,
            roster_row=r_row,
            contact_row=c_row,
            primary_property=ctx.prim_prop,
            contacts=ctx.contacts,
            person_ties=ctx.person_ties,
            household_cache=ctx.household_cache,
            player_last_name=ctx.player_last_name,
        )
        if not is_unlocked:
            if is_private_home_or_wilderness(ctx.target_node, ctx.eff_node_id, ctx.eff_loc, ctx.prop_at_node):
                ctx.blocked_sleeping_keys.update(aliases)
            continue

        if r_row is not None and str(r_row.get("origin") or "").lower() != "legacy_adapter":
            a_map, _ = ctx.get_anchor_eval(merged_npc, force_anchor=True, residence_unlocked_override=True)
            sched_nid = str((a_map or {}).get(ctx.block_key) or "").strip()
        else:
            probe = dict(merged_npc)
            probe["residence_unlocked"] = True
            probe["_roster_premerged"] = True
            probe["_db_hydrated"] = True
            sched_nid = str(
                get_npc_scheduled_node_id(
                    probe,
                    current_minute=ctx.safe_min,
                    scen_key=ctx.scen_key,
                    current_day=ctx.safe_day,
                    session_id=None,
                    story_waypoints=ctx.story_wps_for_legacy,
                    active_events=ctx.active_events,
                )
                or ""
            ).strip()

        dbell = check_doorbell_etiquette(
            ctx.sid,
            merged_npc,
            ctx.eff_node_id,
            current_day=ctx.safe_day,
            current_minute=ctx.safe_min,
            scen_key=ctx.scen_key,
            session=ctx.session_dict,
            has_active_override_pin=bool(aliases & override_pin_aliases),
            nodes_by_id=ctx.nodes_by_id,
            roster_row=r_row,
            roster_loaded=True,
            contact_row=c_row,
            contacts=ctx.contacts,
            contacts_loaded=True,
            person_ties=ctx.person_ties,
            primary_property=ctx.prim_prop,
            primary_property_loaded=ctx.prim_prop_loaded,
            spare_keys=ctx.combined_spare_keys,
            scheduled_node_id=sched_nid,
            household_cache=ctx.household_cache,
            player_household_id=ctx.player_hh_id,
            player_last_name=ctx.player_last_name,
            player_last_name_loaded=True,
        )
        if not dbell["applicable"]:
            continue
        ctx.doorbell_events.append(dbell)
        if dbell["should_block_sleep"]:
            ctx.blocked_sleeping_keys.update(aliases)
        elif dbell["allowed"]:
            ctx.stage(merged_npc, 4, "doorbell_answered", extra={"doorbell_status": dbell["doorbell_status"]})


def _record_discovery_if_needed(
    ctx: _PresenceContext,
    r_row: Mapping[str, Any] | None,
    day_kind: str,
    display_loc: str,
) -> None:
    if (
        r_row is None
        or not ctx.record_discovery
        or ctx.sid <= 0
        or not ctx.eff_node_id
        or ctx.eff_node_id == SHARED_ABSTRACT_RESIDENCE_NODE
        or not display_loc
    ):
        return
    existing_slots = (r_row.get("discovered_slots") or {}).get(day_kind, {})
    if existing_slots.get(ctx.block_key) != display_loc:
        npc_key = str(r_row.get("npc_key") or r_row.get("npc_id") or r_row.get("name") or "").strip()
        if npc_key:
            db.record_discovered_schedule_slot(
                ctx.sid, npc_key, day_kind, ctx.block_key, display_loc, turn_number=ctx.eff_turn
            )


def _resolve_legacy_scheduled_node(ctx: _PresenceContext, leg_npc: Mapping[str, Any]) -> str:
    probe = dict(leg_npc)
    probe["_db_hydrated"] = True
    probe["_roster_premerged"] = True
    sched_nid = str(
        get_npc_scheduled_node_id(
            probe,
            current_minute=ctx.safe_min,
            scen_key=ctx.scen_key,
            current_day=ctx.safe_day,
            session_id=None,
            story_waypoints=ctx.story_wps_for_legacy,
            active_events=ctx.active_events,
        )
        or ""
    ).strip()

    if sched_nid and sched_nid in ctx.nodes_by_id:
        return sched_nid
    if sched_nid and ctx.nodes_by_id:
        aliased = resolve_node_id_in_memory(sched_nid, ctx.nodes_by_id, prefer_facility=False, cache=ctx.loc_cache)
        if aliased:
            return aliased

    work_nid = str(probe.get("workplace_node_id") or "").strip()
    hang_nid = str(probe.get("hangout_node_id") or "").strip()
    home_nid = str(probe.get("home_node_id") or "").strip()
    if any(n and n in ctx.nodes_by_id for n in (work_nid, hang_nid, home_nid)):
        probe["use_anchor_schedule"] = True
        a_map = resolve_anchor_schedule_nodes(
            probe,
            current_day=ctx.safe_day,
            scen_key=ctx.scen_key,
            session_id=None,
            current_minute=ctx.safe_min,
        )
        fallback_nid = str((a_map or {}).get(ctx.block_key) or "").strip()
        if fallback_nid:
            return fallback_nid
    return sched_nid


def _resolve_tier5_schedules(ctx: _PresenceContext) -> None:
    if not ctx.eff_node_id or ctx.eff_node_id == SHARED_ABSTRACT_RESIDENCE_NODE:
        return
    display_loc = format_node_display_label(ctx.eff_node_id, ctx.eff_loc, ctx.nodes_by_id)
    day_kind = "weekend" if is_weekend(ctx.safe_day) else "weekday"

    # Track 5A: Closed-world non-legacy `world_roster`
    for r_row, _, merged_npc, aliases in ctx.unified_records:
        if r_row is None:
            continue
        origin_val = str(r_row.get("origin") or "").strip().lower()
        status_val = str(r_row.get("staff_status") or "active").strip().lower()
        if origin_val == "legacy_adapter" or status_val != "active":
            continue
        if (aliases & ctx.casualty_keys) or (aliases & ctx.blocked_sleeping_keys) or any(ak in ctx.staged_by_key for ak in aliases):
            continue

        a_map, (on_shift, work_nid) = ctx.get_anchor_eval(merged_npc, force_anchor=True)
        sched_nid = str((a_map or {}).get(ctx.block_key) or "").strip()
        work_match = bool(
            on_shift
            and schedule_matches_node(
                work_nid,
                ctx.eff_node_id,
                ctx.eff_loc,
                ctx.nodes_by_id,
                prop_at_node=ctx.prop_at_node,
                resident_home_ids=ctx.resident_home_ids,
            )
        )
        sched_match = schedule_matches_node(
            sched_nid,
            ctx.eff_node_id,
            ctx.eff_loc,
            ctx.nodes_by_id,
            prop_at_node=ctx.prop_at_node,
            resident_home_ids=ctx.resident_home_ids,
        )
        if not (work_match or sched_match):
            continue

        staged = ctx.stage(merged_npc, 5, "schedule")
        if staged is not None:
            _record_discovery_if_needed(ctx, r_row, day_kind, display_loc)

    # Track 5B: Materialized `legacy_adapter` rows + unlinked contacts + raw legacy pools (Ruling 6)
    legacy_candidates: list[tuple[dict[str, Any], dict[str, Any] | None, set[str]]] = []
    seen_legacy_keys: set[str] = set()

    for r_row, _, merged_npc, aliases in ctx.unified_records:
        if r_row is not None:
            origin_val = str(r_row.get("origin") or "").strip().lower()
            if origin_val != "legacy_adapter":
                continue
            status_val = str(r_row.get("staff_status") or "active").strip().lower()
            seen_legacy_keys.update(aliases)
            if status_val != "active":
                continue
            legacy_candidates.append((merged_npc, r_row, aliases))
        else:
            if aliases & ctx.closed_world_roster_keys:
                continue
            seen_legacy_keys.update(aliases)
            legacy_candidates.append((merged_npc, None, aliases))

    for leg_entry in ctx.raw_legacy_entries:
        aliases = npc_aliases(leg_entry)
        if not aliases or (aliases & seen_legacy_keys) or (aliases & ctx.closed_world_roster_keys):
            continue
        seen_legacy_keys.update(aliases)
        legacy_candidates.append((leg_entry, None, aliases))

    for leg_npc, linked_r_row, aliases in legacy_candidates:
        if is_deceased_or_arrested(leg_npc):
            continue
        if (aliases & ctx.casualty_keys) or (aliases & ctx.blocked_sleeping_keys) or any(ak in ctx.staged_by_key for ak in aliases):
            continue

        sched_nid = _resolve_legacy_scheduled_node(ctx, leg_npc)
        if not schedule_matches_node(
            sched_nid,
            ctx.eff_node_id,
            ctx.eff_loc,
            ctx.nodes_by_id,
            prop_at_node=ctx.prop_at_node,
            resident_home_ids=ctx.resident_home_ids,
        ):
            continue

        sched_node = ctx.nodes_by_id.get(sched_nid)
        eff_node_obj = ctx.nodes_by_id.get(ctx.eff_node_id)
        if is_private_home_or_wilderness(sched_node, sched_nid, "", ctx.prop_at_node) or is_private_home_or_wilderness(
            eff_node_obj, ctx.eff_node_id, ctx.eff_loc, ctx.prop_at_node
        ):
            continue

        staged = ctx.stage(leg_npc, 5, "schedule")
        if staged is not None and linked_r_row is not None:
            _record_discovery_if_needed(ctx, linked_r_row, day_kind, display_loc)


def _resolve_tier6_crowd(ctx: _PresenceContext, present_list: list[dict[str, Any]]) -> str:
    if present_list or (not ctx.eff_node_id and not ctx.eff_loc):
        return ""
    if is_private_home_or_wilderness(ctx.target_node, ctx.eff_node_id, ctx.eff_loc, ctx.prop_at_node):
        return ""
    return format_venue_crowd_flavor(ctx.eff_node_id, ctx.eff_loc, ctx.scen_key, ctx.safe_min)


def resolve_node_presence(
    session_id: int,
    node_id: str,
    location_str: str = "",
    current_day: int | None = None,
    current_minute: int | None = None,
    scen_key: str = "",
    party_names: set[str] | None = None,
    actions: list[Any] | None = None,
    session: dict[str, Any] | None = None,
    turn_number: int = 1,
    record_discovery: bool = True,
    persist_db: bool = True,
) -> dict[str, Any]:
    """
    Authoritative 6-tier pre-turn presence resolver for a target world node/location.
    Never honors unconfirmed 'travel to meet <NPC>' verbs; strictly respects Ruling 5 & Ruling 6.
    """
    _ = actions
    ctx = preload_presence_context(
        session_id=session_id,
        node_id=node_id,
        location_str=location_str,
        current_day=current_day,
        current_minute=current_minute,
        scen_key=scen_key,
        session=session,
        turn_number=turn_number,
        record_discovery=bool(record_discovery and persist_db),
        persist_db=persist_db,
    )
    _resolve_tier1_party(ctx, party_names)
    _resolve_tier2_rendezvous(ctx)
    _resolve_tier3_waypoints(ctx)
    _resolve_tier4_doorbell(ctx)
    _resolve_tier5_schedules(ctx)

    present_list = [ctx.staged_by_key[k] for k in ctx.staged_order]
    crowd_flavor = _resolve_tier6_crowd(ctx, present_list)
    return {
        "node_id": ctx.eff_node_id,
        "location": ctx.eff_loc,
        "present_npcs": present_list,
        "allowed_names": [n["name"] for n in present_list],
        "doorbell_events": ctx.doorbell_events,
        "crowd_flavor": crowd_flavor,
        "time_block": ctx.block_key,
        "staged_roster_ops": dict(ctx.staged_roster_ops),
    }


__all__ = [
    "resolve_node_presence",
    "check_doorbell_etiquette",
    "is_node_descendant_in_memory",
    "resolve_node_id_in_memory",
    "preload_presence_context",
    "_preload_presence_context",
    "_PresenceContext",
]
