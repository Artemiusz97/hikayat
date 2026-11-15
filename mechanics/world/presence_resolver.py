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

from dataclasses import dataclass, field
from typing import Any, Mapping

import db
import scenario_data
from mechanics.system.commitments_engine import get_active_commitments
from mechanics.world.anchor_schedule import (
    is_npc_on_active_shift,
    resolve_anchor_schedule_nodes,
)
from mechanics.world.locations.residence_fog import (
    SHARED_ABSTRACT_RESIDENCE_NODE,
    can_materialize_npc_residence,
)
from mechanics.world.locations.residences import get_player_owned_or_starter_property_for_node
from mechanics.world.npc_schedule import (
    get_npc_scheduled_node_id,
    is_high_school_setting,
)
from mechanics.world.presence_doorbell import check_doorbell_etiquette
from mechanics.world.presence_graph import (
    adapt_legacy_entry_for_presence,
    format_node_display_label,
    is_deceased_or_arrested,
    is_node_descendant_in_memory,
    is_private_home_or_wilderness,
    location_targets_node,
    merge_npc_records,
    npc_aliases,
    parse_dict,
    parse_int,
    residence_matches_node,
    resolve_node_id_in_memory,
    schedule_matches_node,
    slugify_key,
)
from mechanics.world.schedule_blocks import get_time_block_key
from mechanics.world.venue_seeder import (
    ensure_roaming_merchants_seeded,
    ensure_venue_staff_seeded,
    format_venue_crowd_flavor,
)
from mechanics.world.venue_templates import is_node_staffable, parse_node_state
from mechanics.world.waypoints.matching import (
    get_waypoint_npc_schedule_info,
    is_hostile_or_lair_waypoint,
)
from mechanics.world.world_schedule import is_weekend

_CRISIS_KEYWORDS: tuple[str, ...] = (
    "crisis", "ambush", "emergency", "under siege", "attack", "assault", "rescue",
)
_PLAYER_SELF_TOKENS: frozenset[str] = frozenset({"player", "you", "mc", "protagonist"})
_ARRIVED_GRACE_MINUTES = 120


def _extract_player_identity(session_dict: Mapping[str, Any]) -> tuple[set[str], int | None, str, set[str]]:
    player_names = set(_PLAYER_SELF_TOKENS)
    player_last_name = ""
    player_hh_id = parse_int(session_dict.get("household_id"))
    char_name = str(session_dict.get("character_name") or "").strip()
    if char_name:
        player_names.add(char_name.lower())
        player_last_name = char_name.split()[-1].lower()
    char_id = parse_int(session_dict.get("character_id"))
    if char_id:
        try:
            p_char = db.get_character_by_id(char_id)
            if isinstance(p_char, Mapping):
                cn = str(p_char.get("name") or "").strip()
                if cn:
                    player_names.add(cn.lower())
                    player_last_name = cn.split()[-1].lower()
                if not player_hh_id:
                    player_hh_id = parse_int(p_char.get("household_id"))
        except Exception:
            pass

    active_dp: set[str] = set()
    dp_single = str(session_dict.get("dialogue_partner") or "").strip().lower()
    if dp_single:
        active_dp.add(dp_single)
        active_dp.add(slugify_key(dp_single))
    for p in (session_dict.get("dialogue_partners") or []):
        p_s = str(p or "").strip().lower()
        if p_s:
            active_dp.add(p_s)
            active_dp.add(slugify_key(p_s))
    active_dp.discard("")
    return player_names, player_hh_id, player_last_name, active_dp


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


@dataclass
class _PresenceContext:
    sid: int
    session_dict: dict[str, Any]
    scen_key: str
    safe_day: int
    safe_min: int
    eff_turn: int
    block_key: str
    eff_node_id: str
    eff_loc: str
    record_discovery: bool
    nodes_by_id: dict[str, dict[str, Any]]
    loc_cache: dict[tuple[str, bool], str]
    target_node: dict[str, Any] | None
    prop_at_node: dict[str, Any] | None
    prim_prop: dict[str, Any] | None
    combined_spare_keys: dict[str, Any]
    person_ties: list[Mapping[str, Any]] | None
    contacts: list[dict[str, Any]]
    roster_rows: list[dict[str, Any]]
    contacts_by_key: dict[str, dict[str, Any]]
    contacts_by_name: dict[str, dict[str, Any]]
    roster_by_key: dict[str, dict[str, Any]]
    closed_world_roster_keys: set[str]
    casualty_keys: set[str]
    resident_home_ids: set[str]
    active_wps: list[dict[str, Any]]
    story_quest: dict[str, Any] | None
    story_wps_for_legacy: list[dict[str, Any]]
    active_events: list[dict[str, Any]]
    legacy_enrichment_by_key: dict[str, dict[str, Any]]
    raw_legacy_entries: list[dict[str, Any]]
    player_names: set[str]
    player_hh_id: int | None
    player_last_name: str
    active_dialogue_partners: set[str]
    household_cache: dict[int, dict[str, Any] | None] = field(default_factory=dict)
    anchor_cache: dict[str, tuple[dict[str, str] | None, tuple[bool, str]]] = field(default_factory=dict)
    staged_by_key: dict[str, dict[str, Any]] = field(default_factory=dict)
    staged_order: list[str] = field(default_factory=list)
    blocked_sleeping_keys: set[str] = field(default_factory=set)
    tier2_aliases: set[str] = field(default_factory=set)
    tier3_crisis_aliases: set[str] = field(default_factory=set)
    doorbell_events: list[dict[str, Any]] = field(default_factory=list)
    unified_records: list[tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any], set[str]]] = field(
        default_factory=list
    )

    def find_linked(self, name_or_id: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        raw_s = str(name_or_id or "").strip().lower()
        slug_s = slugify_key(raw_s)
        r_row = self.roster_by_key.get(raw_s) or self.roster_by_key.get(slug_s)
        c_row = self.contacts_by_key.get(raw_s) or self.contacts_by_key.get(slug_s)
        if r_row and not c_row:
            for ak in npc_aliases(r_row):
                if ak in self.contacts_by_key:
                    c_row = self.contacts_by_key[ak]
                    break
        if c_row and not r_row:
            for ak in npc_aliases(c_row):
                if ak in self.roster_by_key:
                    r_row = self.roster_by_key[ak]
                    break
        return r_row, c_row

    def stage(
        self,
        raw_rec: Mapping[str, Any],
        tier: int,
        reason: str,
        extra: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        raw_name = str(raw_rec.get("name") or raw_rec.get("npc_name") or raw_rec.get("npc_id") or "").strip()
        if not raw_name or raw_name.lower() in self.player_names:
            return None
        r_row, c_row = self.find_linked(raw_rec.get("npc_id") or raw_name)
        merged = merge_npc_records(raw_rec, merge_npc_records(r_row, c_row))
        aliases = npc_aliases(merged) | {raw_name.lower(), slugify_key(raw_name)}
        aliases.discard("")
        if (aliases & self.casualty_keys) or any(ak in self.staged_by_key for ak in aliases):
            return None
        merged["name"] = str(merged.get("name") or raw_name).strip()
        merged["npc_id"] = str(merged.get("npc_id") or merged.get("npc_key") or slugify_key(merged["name"])).strip()
        merged["presence_tier"] = tier
        merged["presence_reason"] = reason
        if isinstance(extra, Mapping):
            merged.update(extra)
        canonical_key = slugify_key(merged["name"]) or merged["npc_id"].lower()
        self.staged_order.append(canonical_key)
        for ak in aliases | {canonical_key}:
            self.staged_by_key[ak] = merged
        return merged

    def get_anchor_eval(
        self,
        eff_rec: Mapping[str, Any],
        *,
        force_anchor: bool = False,
        residence_unlocked_override: bool | None = None,
    ) -> tuple[dict[str, str] | None, tuple[bool, str]]:
        c_key = slugify_key(eff_rec.get("npc_id") or eff_rec.get("npc_key") or eff_rec.get("name")) or str(id(eff_rec))
        cache_key = f"{c_key}:{int(bool(residence_unlocked_override))}"
        if cache_key in self.anchor_cache:
            return self.anchor_cache[cache_key]
        probe = dict(eff_rec)
        probe["_roster_premerged"] = True
        probe["_db_hydrated"] = True
        if residence_unlocked_override is True:
            probe["residence_unlocked"] = True
        if force_anchor and str(probe.get("origin") or "").strip().lower() != "legacy_adapter":
            probe["use_anchor_schedule"] = True
        a_map = resolve_anchor_schedule_nodes(
            probe,
            current_day=self.safe_day,
            scen_key=self.scen_key,
            session_id=None,
            current_minute=self.safe_min,
        )
        shift_tup = is_npc_on_active_shift(
            probe, self.safe_min, current_day=self.safe_day, scen_key=self.scen_key, session_id=None
        )
        self.anchor_cache[cache_key] = (a_map, shift_tup)
        return a_map, shift_tup


def _load_raw_legacy_entries(
    sid: int,
    eff_scen: str,
    session_dict: Mapping[str, Any],
    nodes_by_id: Mapping[str, dict[str, Any]],
    loc_cache: dict[tuple[str, bool], str],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    entries: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    extra_raw = parse_dict(session_dict.get("extra_json"))
    if not extra_raw and isinstance(session_dict.get("extra"), Mapping):
        extra_raw = dict(session_dict["extra"])

    def _push(adapted: dict[str, Any] | None) -> None:
        if adapted is None:
            return
        entries.append(adapted)
        for ak in npc_aliases(adapted):
            by_key.setdefault(ak, adapted)

    if sid > 0 and is_high_school_setting(eff_scen):
        for sr in (db.get_school_roster(sid) or []):
            if isinstance(sr, Mapping):
                _push(adapt_legacy_entry_for_presence(sid, sr, "school", nodes_by_id, loc_cache))

    if sid > 0 and scenario_data.is_anomalous_incursions_scenario(eff_scen):
        agents = extra_raw.get("anomalous_agent_roster") or session_dict.get("anomalous_agent_roster")
        if not isinstance(agents, list):
            agents = db.get_anomalous_agent_roster(sid) or []
        for ar in agents:
            if isinstance(ar, Mapping):
                _push(adapt_legacy_entry_for_presence(sid, ar, "agent", nodes_by_id, loc_cache))

    folklore_list = extra_raw.get("folklore_villager_roster") or session_dict.get("folklore_villager_roster") or []
    for fv in folklore_list:
        if isinstance(fv, Mapping):
            _push(adapt_legacy_entry_for_presence(sid, fv, "folklore", nodes_by_id, loc_cache))

    return entries, by_key


def _enrich_with_legacy_meta(
    merged_npc: dict[str, Any],
    enrichment_by_key: Mapping[str, dict[str, Any]],
    aliases: set[str],
    r_row: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Merges raw legacy metadata (e.g. folklore `schedule`, HS `grade`) while keeping persisted `r_row` authoritative."""
    match_raw: dict[str, Any] | None = None
    for ak in aliases:
        if ak in enrichment_by_key:
            match_raw = enrichment_by_key[ak]
            break
    if match_raw is None:
        return merged_npc

    enriched = merge_npc_records(merged_npc, match_raw)
    for k in ("grade", "club", "clique", "primary_facility", "secondary_facility", "schedule"):
        if not enriched.get(k) and match_raw.get(k):
            enriched[k] = match_raw[k]
    if isinstance(r_row, Mapping):
        for persisted_k in ("staff_status", "home_node_id", "residence_unlocked", "discovered_slots", "affinity_score", "npc_key", "npc_id"):
            if persisted_k in r_row and r_row[persisted_k] not in (None, ""):
                enriched[persisted_k] = r_row[persisted_k]
        if "residence_unlocked" in r_row:
            enriched["residence_unlocked"] = bool(r_row["residence_unlocked"])
        if "home_node_id" in r_row:
            enriched["home_node_id"] = str(r_row.get("home_node_id") or "").strip()
    enriched["_roster_premerged"] = True
    enriched["_db_hydrated"] = True
    return enriched


def _preload_presence_context(
    session_id: int,
    node_id: str,
    location_str: str,
    current_day: int | None,
    current_minute: int | None,
    scen_key: str,
    session: dict[str, Any] | None,
    turn_number: int,
    record_discovery: bool,
) -> _PresenceContext:
    sid = int(session_id or 0)
    session_dict = dict(session) if isinstance(session, Mapping) else (dict(db.get_session(sid) or {}) if sid > 0 else {})
    eff_scen = str(scen_key or session_dict.get("scenario") or "fantasy").strip() or "fantasy"

    if current_day is None or current_minute is None:
        db_day, db_min, db_turn = db.get_session_time(sid) if sid > 0 else (1, 600, 1)
        safe_day = max(1, int(current_day if current_day is not None else db_day or 1))
        safe_min = int(current_minute if current_minute is not None else db_min or 0) % 1440
        eff_turn = int(turn_number or db_turn or 1)
    else:
        safe_day = max(1, int(current_day or 1))
        safe_min = int(current_minute or 0) % 1440
        eff_turn = int(turn_number or 1)

    block_key = get_time_block_key(safe_min)
    eff_loc = str(location_str or "").strip()
    eff_node_id = str(node_id or "").strip()

    world_nodes = (db.get_session_world_nodes(sid) or []) if sid > 0 else []
    nodes_by_id: dict[str, dict[str, Any]] = {
        str(n["node_id"]): n for n in world_nodes if isinstance(n, dict) and n.get("node_id")
    }
    loc_cache: dict[tuple[str, bool], str] = {}
    if not eff_node_id and eff_loc and nodes_by_id:
        eff_node_id = resolve_node_id_in_memory(eff_loc, nodes_by_id, prefer_facility=True, cache=loc_cache)

    target_node = nodes_by_id.get(eff_node_id)
    if (
        sid > 0
        and eff_node_id
        and eff_node_id != SHARED_ABSTRACT_RESIDENCE_NODE
        and isinstance(target_node, dict)
        and str(target_node.get("node_type") or "").upper() == "FACILITY"
        and is_node_staffable(target_node, scen_key=eff_scen)
    ):
        ensure_venue_staff_seeded(sid, eff_node_id, scen_key=eff_scen, current_day=safe_day, turn_number=eff_turn)
        ensure_roaming_merchants_seeded(sid, scen_key=eff_scen, turn_number=eff_turn)

    contacts = (db.get_contacts(sid, ensure_scene=False) or []) if sid > 0 else []
    roster_rows = (db.get_world_roster(sid, include_legacy_rosters=False) or []) if sid > 0 else []

    contacts_by_key: dict[str, dict[str, Any]] = {}
    contacts_by_name: dict[str, dict[str, Any]] = {}
    casualty_keys: set[str] = set()
    resident_home_ids: set[str] = set()

    for c in contacts:
        if not isinstance(c, dict):
            continue
        c_name = str(c.get("name") or "").strip().lower()
        if c_name:
            contacts_by_name[c_name] = c
        c_aliases = npc_aliases(c)
        for ak in c_aliases:
            contacts_by_key[ak] = c
        if is_deceased_or_arrested(c):
            casualty_keys.update(c_aliases)
        c_home = str(c.get("home_node_id") or parse_dict(c.get("basic_info")).get("home_node_id") or "").strip()
        if c_home and c_home != SHARED_ABSTRACT_RESIDENCE_NODE:
            resident_home_ids.add(c_home)

    roster_by_key: dict[str, dict[str, Any]] = {}
    closed_world_roster_keys: set[str] = set()
    for r in roster_rows:
        if not isinstance(r, dict):
            continue
        r_aliases = npc_aliases(r)
        origin_val = str(r.get("origin") or "").strip().lower()
        for ak in r_aliases:
            roster_by_key[ak] = r
            if origin_val != "legacy_adapter":
                closed_world_roster_keys.add(ak)
        if is_deceased_or_arrested(r):
            casualty_keys.update(r_aliases)
        r_home = str(r.get("home_node_id") or parse_dict(r.get("basic_info")).get("home_node_id") or "").strip()
        if r_home and r_home != SHARED_ABSTRACT_RESIDENCE_NODE:
            resident_home_ids.add(r_home)

    prop_at_node = get_player_owned_or_starter_property_for_node(sid, eff_node_id, session=session_dict) if (sid > 0 and eff_node_id) else None
    prim_prop = db.get_primary_property(sid) if (sid > 0 and eff_node_id and eff_node_id != SHARED_ABSTRACT_RESIDENCE_NODE) else None
    combined_spare_keys: dict[str, Any] = {}
    for prop in (prim_prop, prop_at_node):
        if isinstance(prop, Mapping) and isinstance(prop.get("spare_keys"), Mapping):
            combined_spare_keys.update(prop["spare_keys"])
    node_state_map = parse_node_state(target_node) if isinstance(target_node, dict) else {}
    if isinstance(node_state_map.get("spare_keys"), Mapping):
        combined_spare_keys.update(node_state_map["spare_keys"])

    person_ties: list[Mapping[str, Any]] | None = None
    if sid > 0:
        try:
            import mechanics.social.relationship_graph as rg
            person_ties = rg.get_person_ties(sid, "player") if hasattr(rg, "get_person_ties") else []
        except Exception:
            person_ties = []

    active_wps = (db.get_all_session_active_waypoints(sid) or []) if sid > 0 else []
    story_quest = db.get_active_story_quest(sid) if sid > 0 else None
    story_wps_for_legacy = [wp for wp in active_wps if wp.get("target_node_id")] if active_wps else []
    active_events = (db.get_world_events(sid, entity_type="macro_event") or []) if sid > 0 else []

    raw_legacy_entries, legacy_enrichment_by_key = _load_raw_legacy_entries(
        sid, eff_scen, session_dict, nodes_by_id, loc_cache
    )
    for leg in raw_legacy_entries:
        if is_deceased_or_arrested(leg):
            casualty_keys.update(npc_aliases(leg))

    player_names, player_hh_id, player_last_name, active_dp = _extract_player_identity(session_dict)

    ctx = _PresenceContext(
        sid=sid,
        session_dict=session_dict,
        scen_key=eff_scen,
        safe_day=safe_day,
        safe_min=safe_min,
        eff_turn=eff_turn,
        block_key=block_key,
        eff_node_id=eff_node_id,
        eff_loc=eff_loc,
        record_discovery=record_discovery,
        nodes_by_id=nodes_by_id,
        loc_cache=loc_cache,
        target_node=target_node,
        prop_at_node=prop_at_node,
        prim_prop=prim_prop,
        combined_spare_keys=combined_spare_keys,
        person_ties=person_ties,
        contacts=contacts,
        roster_rows=roster_rows,
        contacts_by_key=contacts_by_key,
        contacts_by_name=contacts_by_name,
        roster_by_key=roster_by_key,
        closed_world_roster_keys=closed_world_roster_keys,
        casualty_keys=casualty_keys,
        resident_home_ids=resident_home_ids,
        active_wps=active_wps,
        story_quest=story_quest,
        story_wps_for_legacy=story_wps_for_legacy,
        active_events=active_events,
        legacy_enrichment_by_key=legacy_enrichment_by_key,
        raw_legacy_entries=raw_legacy_entries,
        player_names=player_names,
        player_hh_id=player_hh_id,
        player_last_name=player_last_name,
        active_dialogue_partners=active_dp,
    )

    seen_unified: set[str] = set()
    for r in roster_rows:
        if not isinstance(r, dict):
            continue
        r_aliases = npc_aliases(r)
        if not r_aliases or (r_aliases & seen_unified):
            continue
        seen_unified.update(r_aliases)
        _, linked_c = ctx.find_linked(r.get("npc_id") or r.get("name"))
        if linked_c:
            seen_unified.update(npc_aliases(linked_c))
        merged = merge_npc_records(r, linked_c)
        if str(r.get("origin") or "").strip().lower() == "legacy_adapter":
            merged = _enrich_with_legacy_meta(merged, legacy_enrichment_by_key, r_aliases, r)
        ctx.unified_records.append((r, linked_c, merged, r_aliases))

    for c in contacts:
        if not isinstance(c, dict):
            continue
        c_aliases = npc_aliases(c)
        if not c_aliases or (c_aliases & seen_unified):
            continue
        seen_unified.update(c_aliases)
        merged = merge_npc_records(c, None)
        merged = _enrich_with_legacy_meta(merged, legacy_enrichment_by_key, c_aliases, None)
        ctx.unified_records.append((None, c, merged, c_aliases))

    return ctx


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
    active_rows = get_active_commitments(ctx.sid, commitment_type="rendezvous", limit=50) or []
    for rc in active_rows:
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


def _resolve_tier3_waypoints(ctx: _PresenceContext) -> None:
    candidate_wps: list[dict[str, Any]] = [dict(wp) for wp in ctx.active_wps if isinstance(wp, Mapping)]
    if isinstance(ctx.story_quest, Mapping):
        sq_loc = str(ctx.story_quest.get("target_location") or ctx.story_quest.get("location") or ctx.story_quest.get("client_location") or "").strip()
        sq_node = str(ctx.story_quest.get("target_node_id") or "").strip()
        sub_objs = ctx.story_quest.get("sub_objectives") or []
        has_active_sub = False
        for so in sub_objs:
            if isinstance(so, Mapping) and not so.get("completed"):
                has_active_sub = True
                if so.get("target_npc"):
                    so_wp = dict(so)
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
            sq_wp = dict(ctx.story_quest)
            if not str(sq_wp.get("stage_label") or "").strip():
                sq_wp["stage_label"] = str(ctx.story_quest.get("title") or ctx.story_quest.get("objective") or "")
            candidate_wps.append(sq_wp)

    for wp in candidate_wps:
        t_npc = str(wp.get("target_npc") or "").strip()
        if not t_npc:
            continue
        wp_loc = str(wp.get("target_location") or wp.get("location") or "").strip()
        wp_node = str(wp.get("target_node_id") or "").strip()
        if not location_targets_node(wp_node, wp_loc, ctx.eff_node_id, ctx.eff_loc, ctx.nodes_by_id, ctx.loc_cache):
            continue
        r_row, c_row = ctx.find_linked(t_npc)
        wp_aliases = npc_aliases(r_row) | npc_aliases(c_row) | {t_npc.lower(), slugify_key(t_npc)}
        if wp_aliases & ctx.casualty_keys:
            continue

        is_hostile = is_hostile_or_lair_waypoint(wp)
        wp_blob = f"{wp.get('stage_label', '')} {wp.get('title', '')} {wp.get('objective', '')} {wp.get('notes', '')}".lower()
        is_crisis = bool(wp.get("is_crisis")) or any(k in wp_blob for k in _CRISIS_KEYWORDS)
        follow_sched = bool(wp.get("follow_npc_schedule"))
        if is_hostile or is_crisis or not follow_sched:
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
        )
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
            primary_property_loaded=True,
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

    # Custom graph fallback when unhydrated legacy facilities point to custom world_nodes IDs
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

        # Private residence entry must pass Tier 4 doorbell etiquette, never bare legacy fallback
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
) -> dict[str, Any]:
    """
    Authoritative 6-tier pre-turn presence resolver for a target world node/location.
    Never honors unconfirmed 'travel to meet <NPC>' verbs; strictly respects Ruling 5 & Ruling 6.
    """
    _ = actions
    ctx = _preload_presence_context(
        session_id=session_id,
        node_id=node_id,
        location_str=location_str,
        current_day=current_day,
        current_minute=current_minute,
        scen_key=scen_key,
        session=session,
        turn_number=turn_number,
        record_discovery=record_discovery,
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
    }


__all__ = [
    "resolve_node_presence",
    "check_doorbell_etiquette",
    "is_node_descendant_in_memory",
    "resolve_node_id_in_memory",
]
