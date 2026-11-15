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
from mechanics.social.activity_tags import resolve_actor_activity_bundle
from mechanics.world.anchor_schedule import resolve_anchor_schedule_nodes
from mechanics.world.locations.residence_fog import (
    SHARED_ABSTRACT_RESIDENCE_NODE,
    can_materialize_npc_residence,
)
from mechanics.world.locations.residences import is_npc_active_spare_key_holder
from mechanics.world.npc_autonomy import resolve_autonomy_node_override
from mechanics.world.npc_schedule import get_npc_scheduled_node_id
from mechanics.world.presence_doorbell import (
    check_doorbell_etiquette,
    is_verified_household_cohabitant,
)
from mechanics.world.presence_graph import (
    format_node_display_label,
    is_deceased_or_arrested,
    is_node_descendant_in_memory,
    is_private_home_or_wilderness,
    is_private_residence_node,
    location_targets_node,
    merge_npc_records,
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
MAX_TIER5_BYSTANDERS = 5
_PAIR_TIE_TYPES: frozenset[str] = frozenset({"dating", "engaged", "married", "affair", "best_friend", "friend"})


def _minutes_to_next_bell(safe_min: int, block_key: str) -> int:
    m = int(safe_min or 0) % 1440
    ends = {"morning": 720, "lunch": 780, "afternoon": 1020, "evening": 1200}
    b = str(block_key or "afternoon").lower()
    if b in ends:
        return max(0, ends[b] - m)
    return (360 - m) if m < 360 else (1440 - m + 360)


def _extract_max_party_per(session_dict: Mapping[str, Any], present_list: list[dict[str, Any]]) -> int:
    best = 10
    for key in ("player_stats", "stats"):
        s_map = session_dict.get(key)
        if isinstance(s_map, Mapping):
            raw = s_map.get("per") if s_map.get("per") is not None else s_map.get("PER")
            if raw is None:
                raw = s_map.get("perception")
            if raw is not None:
                try:
                    best = max(best, int(raw))
                except (TypeError, ValueError):
                    pass
    for npc in present_list:
        if npc.get("presence_tier") == 1 or npc.get("in_party"):
            st = npc.get("stats") if isinstance(npc.get("stats"), Mapping) else {}
            raw = npc.get("per") or st.get("per") or st.get("PER") or st.get("perception")
            if raw is not None:
                try:
                    best = max(best, int(raw))
                except (TypeError, ValueError):
                    pass
    return best


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

        remaining_to_end = a_end - abs_now
        elapsed_since_start = abs_now - a_start
        rv_state = (
            "checking_time"
            if (remaining_to_end <= 30 or (rc.get("start_minute") is not None and elapsed_since_start >= 30))
            else "waiting"
        )
        for npc_id_val, disp_name in cands:
            ctx.tier2_aliases.update({disp_name.lower(), slugify_key(disp_name), npc_id_val.lower()})
            ctx.stage(
                {"npc_id": npc_id_val, "name": disp_name},
                2,
                "commitment",
                extra={"rendezvous_state": rv_state},
            )


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
        target_priv = str((ctx.target_node or {}).get("privacy_level") or "").strip().lower()
        loc_label_low = f"{ctx.eff_loc or ''} {(ctx.target_node or {}).get('name') or ''}".lower()
        is_private_room = bool(
            ctx.prop_at_node is not None
            or target_priv in ("private", "restricted", "discreet")
            or is_private_residence_node(ctx.target_node, ctx.eff_node_id)
            or (
                target_priv != "public"
                and any(k in loc_label_low for k in ("bedroom", "dorm room", "private suite", "private quarters"))
            )
        )
        if is_private_room:
            is_own_unlocked_res = False
            if r_row is not None or c_row is not None:
                merged_npc = merge_npc_records(r_row, c_row)
                npc_home = str(
                    merged_npc.get("home_node_id")
                    or parse_dict(merged_npc.get("basic_info")).get("home_node_id")
                    or ""
                ).strip()
                if npc_home and ctx.eff_node_id and residence_matches_node(npc_home, ctx.eff_node_id, ctx.nodes_by_id):
                    is_own_unlocked_res = can_materialize_npc_residence(
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
            if not is_own_unlocked_res:
                continue
        if r_row is None and c_row is None and not (420 <= (int(ctx.safe_min) % 1440) < 1320):
            continue
        if not sched_info.get("is_off_duty"):
            ctx.stage({"name": t_npc, "npc_id": (c_row or r_row or {}).get("npc_id") or slugify_key(t_npc)}, 3, "quest_pin")


def _resolve_tier4_doorbell(ctx: _PresenceContext) -> None:
    if not ctx.eff_node_id or ctx.eff_node_id == SHARED_ABSTRACT_RESIDENCE_NODE:
        return
    override_pin_aliases = ctx.tier2_aliases | ctx.tier3_crisis_aliases
    is_player_res = bool(
        ctx.prop_at_node is not None
        or (ctx.player_home_node_id and residence_matches_node(ctx.player_home_node_id, ctx.eff_node_id, ctx.nodes_by_id))
    )

    for r_row, c_row, merged_npc, aliases in ctx.unified_records:
        if aliases & ctx.casualty_keys:
            continue
        npc_home = str(merged_npc.get("home_node_id") or parse_dict(merged_npc.get("basic_info")).get("home_node_id") or "").strip()
        if is_player_res and not residence_matches_node(npc_home, ctx.eff_node_id, ctx.nodes_by_id):
            if any(ak in ctx.staged_by_key for ak in aliases) or (aliases & ctx.active_dialogue_partners):
                continue
            ov_drop = resolve_autonomy_node_override(
                merged_npc,
                session_id=ctx.sid,
                day=ctx.safe_day,
                block=ctx.block_key,
                scen_key=ctx.scen_key,
                active_ties_by_person=ctx.active_ties_by_person,
                roster_by_key=ctx.roster_by_key,
                active_events=ctx.active_events,
                has_active_rendezvous_or_quest=bool(aliases & override_pin_aliases),
                player_home_node_id=ctx.player_home_node_id or ctx.eff_node_id,
            )
            a_map_d, _ = ctx.get_anchor_eval(merged_npc, force_anchor=True)
            sched_d = str((a_map_d or {}).get(ctx.block_key) or "").strip()
            wants_dropby = bool(
                (isinstance(ov_drop, Mapping) and (ov_drop.get("is_dropby") or residence_matches_node(str(ov_drop.get("node_id") or ""), ctx.eff_node_id, ctx.nodes_by_id)))
                or (not ov_drop and sched_d and residence_matches_node(sched_d, ctx.eff_node_id, ctx.nodes_by_id))
            )
            if not wants_dropby:
                continue
            has_key = bool(
                (ctx.combined_spare_keys and ctx.sid > 0 and is_npc_active_spare_key_holder(ctx.sid, merged_npc, ctx.combined_spare_keys, contacts=ctx.contacts, person_ties=ctx.person_ties))
                or is_verified_household_cohabitant(ctx.sid, merged_npc, c_row, ctx.household_cache, ctx.player_hh_id, ctx.player_last_name)
            )
            npc_disp = str(merged_npc.get("name") or "").strip()
            if has_key:
                ctx.doorbell_events.append({
                    "applicable": True,
                    "npc_name": npc_disp,
                    "doorbell_status": "spare_key_entry",
                    "entry_mode": "spare_key_entry",
                    "allowed": True,
                    "should_block_sleep": False,
                    "override_reason": "spare_key",
                    "home_node_id": ctx.eff_node_id,
                })
                ctx.stage(
                    merged_npc,
                    4,
                    "doorbell_answered",
                    extra={"doorbell_status": "spare_key_entry", "entry_mode": "spare_key_entry"},
                )
            else:
                ctx.doorbell_events.append({
                    "applicable": True,
                    "npc_name": npc_disp,
                    "doorbell_status": "npc_ringing_player_door",
                    "entry_mode": "doorbell_ringing",
                    "allowed": False,
                    "should_block_sleep": False,
                    "reason": "player_doorbell_ringing",
                    "home_node_id": ctx.eff_node_id,
                })
                ctx.stage(
                    merged_npc,
                    4,
                    "doorbell_ringing",
                    extra={
                        "doorbell_status": "npc_ringing_player_door",
                        "entry_mode": "threshold_doorbell",
                        "at_threshold": True,
                        "stage_role": "threshold_visitor",
                    },
                )
            continue
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
    protected_aliases = ctx.tier2_aliases | ctx.tier3_crisis_aliases
    candidates: list[dict[str, Any]] = []

    # Track 5A: Closed-world non-legacy `world_roster`
    for r_row, c_row, merged_npc, aliases in ctx.unified_records:
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

        # F4: Evaluate ephemeral current-day D1/D3/D14 autonomy override cleanly without mutating anchor schedule
        ov = resolve_autonomy_node_override(
            merged_npc,
            session_id=ctx.sid,
            day=ctx.safe_day,
            block=ctx.block_key,
            scen_key=ctx.scen_key,
            active_ties_by_person=ctx.active_ties_by_person,
            roster_by_key=ctx.roster_by_key,
            active_events=ctx.active_events,
            has_active_rendezvous_or_quest=bool(aliases & protected_aliases),
            player_home_node_id=ctx.player_home_node_id,
        )
        # D10: Do not allow autonomy friend-visiting to crowd an active Tier 2 rendezvous NPC.
        if isinstance(ov, Mapping):
            vis_low = str(ov.get("visiting_npc") or "").strip().lower()
            if vis_low and vis_low in ctx.tier2_aliases:
                ov = None
        eff_work_match = bool(
            not ov
            and on_shift
            and schedule_matches_node(
                work_nid,
                ctx.eff_node_id,
                ctx.eff_loc,
                ctx.nodes_by_id,
                prop_at_node=ctx.prop_at_node,
                resident_home_ids=ctx.resident_home_ids,
            )
        )
        eff_sched_nid = str(ov["node_id"]) if isinstance(ov, Mapping) and ov.get("node_id") else sched_nid
        sched_match = schedule_matches_node(
            eff_sched_nid,
            ctx.eff_node_id,
            ctx.eff_loc,
            ctx.nodes_by_id,
            prop_at_node=ctx.prop_at_node,
            resident_home_ids=ctx.resident_home_ids,
        )
        if not (eff_work_match or sched_match):
            continue

        aff_val = int((c_row or {}).get("relationship_score") or (c_row or {}).get("affinity") or merged_npc.get("affinity") or 0)
        is_dropby = bool(isinstance(ov, Mapping) and ov.get("is_dropby"))
        extra_meta: dict[str, Any] = {}
        if isinstance(ov, Mapping):
            extra_meta["autonomy_reason"] = str(ov.get("reason") or "")
            if ov.get("visit_label"):
                extra_meta["autonomy_visit_label"] = str(ov["visit_label"])
            if is_dropby:
                extra_meta["is_autonomy_dropby"] = True
        candidates.append({
            "npc": merged_npc,
            "r_row": r_row,
            "priority": (0 if is_dropby else 1, -aff_val),
            "extra": extra_meta,
            "aliases": aliases,
            "key": str(r_row.get("person_key") or r_row.get("npc_id") or merged_npc.get("name") or "").strip().lower(),
        })

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

        candidates.append({
            "npc": leg_npc,
            "r_row": linked_r_row,
            "priority": (2, 0),
            "extra": {},
            "aliases": aliases,
            "key": str((linked_r_row or {}).get("person_key") or leg_npc.get("npc_id") or leg_npc.get("name") or "").strip().lower(),
        })

    # F2: Group active tie pairs atomically before admitting up to MAX_TIER5_BYSTANDERS = 5
    candidates.sort(key=lambda c: c["priority"])
    by_alias: dict[str, int] = {}
    for idx, c in enumerate(candidates):
        for ak in c["aliases"] | {c["key"]}:
            if ak:
                by_alias[ak] = idx

    paired_idx: set[int] = set()
    units: list[list[int]] = []
    for i, c in enumerate(candidates):
        if i in paired_idx:
            continue
        partner_j: int | None = None
        for ak in (c["aliases"] | {c["key"]}):
            for t in ctx.active_ties_by_person.get(ak, ()):
                ttype = str(t.get("tie_type") or "").strip().lower()
                if ttype not in _PAIR_TIE_TYPES:
                    continue
                pa = str(t.get("person_a_key") or "").strip().lower()
                pb = str(t.get("person_b_key") or "").strip().lower()
                other_k = pb if pa == ak else pa
                if not other_k or other_k in ctx.tier2_aliases:
                    continue
                j = by_alias.get(other_k)
                if j is not None and j != i and j not in paired_idx:
                    partner_j = j
                    break
            if partner_j is not None:
                break

        if partner_j is not None:
            paired_idx.update((i, partner_j))
            name_i = str(c["npc"].get("name") or "")
            name_j = str(candidates[partner_j]["npc"].get("name") or "")
            if name_j:
                c["extra"]["paired_with"] = name_j
            if name_i:
                candidates[partner_j]["extra"]["paired_with"] = name_i
            units.append([i, partner_j])
        else:
            paired_idx.add(i)
            units.append([i])

    admitted = 0
    overflow = 0
    for unit in units:
        if admitted + len(unit) > MAX_TIER5_BYSTANDERS:
            overflow += len(unit)
            continue
        for idx in unit:
            c = candidates[idx]
            staged = ctx.stage(c["npc"], 5, "schedule", extra=c["extra"])
            if staged is not None:
                admitted += 1
                if c["r_row"] is not None:
                    _record_discovery_if_needed(ctx, c["r_row"], day_kind, display_loc)
    ctx.tier5_overflow_count += overflow


def _resolve_tier6_crowd(ctx: _PresenceContext, present_list: list[dict[str, Any]]) -> str:
    if not ctx.eff_node_id and not ctx.eff_loc:
        return ""
    if is_private_home_or_wilderness(ctx.target_node, ctx.eff_node_id, ctx.eff_loc, ctx.prop_at_node):
        return ""
    if present_list and int(getattr(ctx, "tier5_overflow_count", 0) or 0) <= 0:
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
    lang_code = str(ctx.session_dict.get("language") or "en").strip().lower()
    max_per = _extract_max_party_per(ctx.session_dict, present_list)
    mins_left = _minutes_to_next_bell(ctx.safe_min, ctx.block_key)
    in_combat = bool(ctx.session_dict.get("in_combat"))
    in_erotic = bool(ctx.session_dict.get("in_erotic_scene"))
    node_type_val = str((ctx.target_node or {}).get("node_type") or "")
    joined_partner_low = str(ctx.session_dict.get("joined_activity_npc") or "").strip().lower()
    joined_partners_set: set[str] = {joined_partner_low} if joined_partner_low else set()
    for jp in (ctx.session_dict.get("joined_activity_partners") or ()):
        jp_s = str(jp or "").strip().lower()
        if jp_s:
            joined_partners_set.add(jp_s)

    for npc_entry in present_list:
        n_low = str(npc_entry.get("name") or "").strip().lower()
        nid_low = str(npc_entry.get("npc_id") or "").strip().lower()
        is_dp = bool(
            n_low in ctx.active_dialogue_partners
            or nid_low in ctx.active_dialogue_partners
        )
        rv_state = str(
            npc_entry.get("rendezvous_state")
            or (
                "waiting"
                if (int(npc_entry.get("presence_tier") or 5) == 2 or npc_entry.get("doorbell_status") == "npc_ringing_player_door")
                else ""
            )
        ).strip().lower()
        bundle = resolve_actor_activity_bundle(
            npc_entry,
            location=ctx.eff_loc or str((ctx.target_node or {}).get("name") or ""),
            node_type=node_type_val,
            scen_key=ctx.scen_key,
            time_block=ctx.block_key,
            stage_role=str(npc_entry.get("stage_role") or "room_bystander"),
            is_dialogue_partner=is_dp,
            is_joined_activity=bool((n_low and n_low in joined_partners_set) or (nid_low and nid_low in joined_partners_set)),
            is_combat=in_combat,
            is_erotic=in_erotic,
            paired_with=str(npc_entry.get("paired_with") or ""),
            rendezvous_state=rv_state,
            minutes_to_bell=mins_left,
            max_party_per=max_per,
            lang=lang_code,
            session_id=ctx.sid,
            day=ctx.safe_day,
        )
        npc_entry.update(bundle)

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
        "epistemic_matrix": dict(ctx.epistemic_matrix),
    }


__all__ = [
    "MAX_TIER5_BYSTANDERS",
    "resolve_node_presence",
    "check_doorbell_etiquette",
    "is_node_descendant_in_memory",
    "resolve_node_id_in_memory",
    "preload_presence_context",
    "_preload_presence_context",
    "_PresenceContext",
]
