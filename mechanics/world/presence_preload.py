"""
mechanics/world/presence_preload.py — Single-Pass Context Preloader for Presence Resolution
===========================================================================================
Loads session nodes, contacts, closed-world roster, legacy/special-agent rosters,
active commitments, active quest waypoints, and spare keys in O(1) queries per turn
so Tiers 1–6 execute with zero N+1 SQLite round-trips.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import db
import scenario_data
from mechanics.social.relationships import safe_get_contacts
from mechanics.system.commitments_engine import get_active_commitments
from mechanics.world.anchor_schedule import (
    is_npc_on_active_shift,
    resolve_anchor_schedule_nodes,
)
from mechanics.world.locations import location_has_merchant_shop
from mechanics.world.locations.residence_fog import SHARED_ABSTRACT_RESIDENCE_NODE
from mechanics.world.locations.residences import get_player_owned_or_starter_property_for_node
from mechanics.world.npc_schedule import is_high_school_setting
from mechanics.world.presence_graph import (
    adapt_legacy_entry_for_presence,
    is_deceased_or_arrested,
    merge_npc_records,
    npc_aliases,
    parse_dict,
    parse_int,
    resolve_node_id_in_memory,
    slugify_key,
)
from mechanics.world.schedule_blocks import get_time_block_key
from mechanics.world.venue_seeder import (
    ensure_roaming_merchants_seeded,
    ensure_venue_staff_seeded,
    heal_stale_civic_hq_staff,
)
from mechanics.world.venue_templates import (
    is_civic_or_multi_wing_hub_node,
    is_node_staffable,
    parse_node_state,
)

_PLAYER_SELF_TOKENS: frozenset[str] = frozenset({"player", "you", "mc", "protagonist"})


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
    prim_prop_loaded: bool
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
    active_commitments: list[dict[str, Any]]
    story_quest: dict[str, Any] | None
    story_wps_for_legacy: list[dict[str, Any]]
    active_events: list[dict[str, Any]]
    legacy_enrichment_by_key: dict[str, dict[str, Any]]
    raw_legacy_entries: list[dict[str, Any]]
    player_names: set[str]
    player_hh_id: int | None
    player_last_name: str
    active_dialogue_partners: set[str]
    all_social_ties: list[dict[str, Any]] = field(default_factory=list)
    active_ties_by_person: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    epistemic_matrix: dict[str, Any] = field(default_factory=dict)
    player_home_node_id: str = ""
    tier5_overflow_count: int = 0
    household_cache: dict[int, dict[str, Any] | None] = field(default_factory=dict)
    anchor_cache: dict[str, tuple[dict[str, str] | None, tuple[bool, str]]] = field(default_factory=dict)
    staged_by_key: dict[str, dict[str, Any]] = field(default_factory=dict)
    staged_order: list[str] = field(default_factory=list)
    blocked_sleeping_keys: set[str] = field(default_factory=set)
    tier2_aliases: set[str] = field(default_factory=set)
    tier3_crisis_aliases: set[str] = field(default_factory=set)
    doorbell_events: list[dict[str, Any]] = field(default_factory=list)
    staged_roster_ops: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
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
    *,
    session_was_provided: bool = False,
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
        if not isinstance(agents, list) and isinstance(session_dict.get("extra"), Mapping):
            agents = session_dict["extra"].get("anomalous_agent_roster")
        has_extra_loaded = (
            not session_was_provided
            or "extra" in session_dict
            or "extra_json" in session_dict
            or "anomalous_agent_roster" in session_dict
        )
        if not isinstance(agents, list):
            agents = [] if has_extra_loaded else (db.get_anomalous_agent_roster(sid) or [])
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


def preload_presence_context(
    session_id: int,
    node_id: str,
    location_str: str,
    current_day: int | None,
    current_minute: int | None,
    scen_key: str,
    session: dict[str, Any] | None,
    turn_number: int,
    record_discovery: bool,
    persist_db: bool = True,
) -> _PresenceContext:
    """Single-pass preloader fetching all session state before Tiers 1–6 evaluate."""
    sid = int(session_id or 0)
    session_was_provided = isinstance(session, Mapping)
    session_dict = dict(session) if session_was_provided else (dict(db.get_session(sid) or {}) if sid > 0 else {})
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
        eff_node_id = resolve_node_id_in_memory(eff_loc, nodes_by_id, prefer_facility=False, cache=loc_cache)
        if not eff_node_id:
            eff_node_id = resolve_node_id_in_memory(eff_loc, nodes_by_id, prefer_facility=True, cache=loc_cache)

    eff_record_discovery = bool(record_discovery and persist_db)
    staged_roster_ops: dict[str, list[dict[str, Any]]] = {}
    target_node = nodes_by_id.get(eff_node_id)
    is_staffable_facility = bool(
        sid > 0
        and eff_node_id
        and eff_node_id != SHARED_ABSTRACT_RESIDENCE_NODE
        and isinstance(target_node, dict)
        and str(target_node.get("node_type") or "").upper() == "FACILITY"
        and is_node_staffable(target_node, scen_key=eff_scen)
    )
    seed_node_id = ""
    if is_staffable_facility:
        seed_node_id = eff_node_id
    elif sid > 0 and eff_node_id and isinstance(target_node, dict) and str(target_node.get("node_type") or "").upper() == "ROOM":
        chain: list[str] = []
        cur_walk: dict[str, Any] | None = target_node
        seen_walk: set[str] = set()
        while isinstance(cur_walk, dict):
            w_nid = str(cur_walk.get("node_id") or "")
            if w_nid in seen_walk:
                break
            seen_walk.add(w_nid)
            if cur_walk.get("name"):
                chain.append(str(cur_walk["name"]).strip())
            w_pid = str(cur_walk.get("parent_id") or "").strip()
            cur_walk = nodes_by_id.get(w_pid) if w_pid else None
        chain.reverse()
        probe_loc = (
            " ➔ ".join(chain) if len(chain) >= 3
            else (f"Zone ➔ {chain[0]} ➔ {chain[1]}" if len(chain) == 2 else (eff_loc or str(target_node.get("name") or "")))
        )
        t_meta = parse_node_state(target_node)
        is_priv_room = bool(t_meta.get("is_player_residence")) or str(target_node.get("privacy_level") or "").strip().lower() == "private"
        room_is_shop = False if t_meta.get("is_player_residence") else bool(
            t_meta.get("has_merchant_shop")
            or t_meta.get("has_shop")
            or (not is_priv_room and (t_meta.get("is_minor_club_hq") or (probe_loc and location_has_merchant_shop(probe_loc, scen_key=eff_scen))))
        )
        parent_id = str(target_node.get("parent_id") or "").strip()
        parent_node = nodes_by_id.get(parent_id) if parent_id else None
        parent_is_hub = bool(parent_node and is_civic_or_multi_wing_hub_node(parent_node, scen_key=eff_scen))
        if room_is_shop:
            if (
                parent_node
                and str(parent_node.get("node_type") or "").upper() == "FACILITY"
                and not parent_is_hub
                and is_node_staffable(parent_node, scen_key=eff_scen)
                and (
                    str(parent_node.get("category") or "").strip().lower() == "commercial"
                    or location_has_merchant_shop(str(parent_node.get("name") or ""), scen_key=eff_scen)
                )
            ):
                seed_node_id = parent_id
            elif is_node_staffable(target_node, scen_key=eff_scen):
                seed_node_id = eff_node_id
        elif (
            not is_priv_room
            and parent_node
            and str(parent_node.get("node_type") or "").upper() == "FACILITY"
            and not parent_is_hub
            and is_node_staffable(parent_node, scen_key=eff_scen)
        ):
            seed_node_id = parent_id

    if persist_db:
        if seed_node_id:
            ensure_venue_staff_seeded(sid, seed_node_id, scen_key=eff_scen, current_day=safe_day, turn_number=eff_turn)
        if is_staffable_facility:
            ensure_roaming_merchants_seeded(sid, scen_key=eff_scen, turn_number=eff_turn)
        contacts = safe_get_contacts(sid, ensure_scene=False) if sid > 0 else []
        roster_rows = (db.get_world_roster(sid, include_legacy_rosters=False) or []) if sid > 0 else []
        if sid > 0 and heal_stale_civic_hq_staff(sid, scen_key=eff_scen, roster=roster_rows, nodes_by_id=nodes_by_id, contacts=contacts):
            roster_rows = db.get_world_roster(sid, include_legacy_rosters=False) or []
    elif sid > 0:
        # Read-only pre-turn stage preview: seed inside a rolled-back SAVEPOINT and defer
        # persistent world_roster inserts until UnitOfWork commit in apply_outcome.
        contacts = []
        roster_rows = []
        with db.UnitOfWork() as uow_conn:
            sp_name = "sp_presence_preload"
            uow_conn.execute(f"SAVEPOINT {sp_name}")
            try:
                pre_keys = (
                    {
                        str(r.get("npc_id") or "").strip().lower()
                        for r in (db.get_world_roster(sid, include_legacy_rosters=False) or [])
                        if isinstance(r, dict) and r.get("npc_id")
                    }
                    if (seed_node_id or is_staffable_facility)
                    else set()
                )
                if seed_node_id:
                    ensure_venue_staff_seeded(sid, seed_node_id, scen_key=eff_scen, current_day=safe_day, turn_number=eff_turn)
                if is_staffable_facility:
                    ensure_roaming_merchants_seeded(sid, scen_key=eff_scen, turn_number=eff_turn)
                contacts = safe_get_contacts(sid, ensure_scene=False)
                roster_rows = db.get_world_roster(sid, include_legacy_rosters=False) or []
                if seed_node_id or is_staffable_facility:
                    new_rows = [
                        r for r in roster_rows
                        if isinstance(r, dict)
                        and str(r.get("npc_id") or "").strip().lower() not in pre_keys
                    ]
                    if seed_node_id and any(str(r.get("origin") or "").lower() == "venue_seed" for r in new_rows):
                        staged_roster_ops.setdefault("venue_seeds", []).append({
                            "facility_node_id": seed_node_id,
                            "scen_key": eff_scen,
                            "current_day": safe_day,
                            "turn_number": eff_turn,
                        })
                    if any(str(r.get("origin") or "").lower() in ("roaming_merchant", "merchant") for r in new_rows):
                        staged_roster_ops.setdefault("roaming_merchants", []).append({
                            "scen_key": eff_scen,
                            "turn_number": eff_turn,
                        })
            finally:
                try:
                    uow_conn.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
                    uow_conn.execute(f"RELEASE SAVEPOINT {sp_name}")
                except Exception:
                    pass
    else:
        contacts = []
        roster_rows = []

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

    prop_at_node = (
        get_player_owned_or_starter_property_for_node(
            sid,
            eff_node_id,
            session=session_dict,
            world_node=target_node,
            world_node_loaded=True,
        )
        if (sid > 0 and eff_node_id)
        else None
    )
    prim_prop_loaded = sid <= 0 or eff_node_id != SHARED_ABSTRACT_RESIDENCE_NODE
    prim_prop = db.get_primary_property(sid) if (sid > 0 and prim_prop_loaded) else None
    combined_spare_keys: dict[str, Any] = {}
    for prop in (prim_prop, prop_at_node):
        if isinstance(prop, Mapping) and isinstance(prop.get("spare_keys"), Mapping):
            combined_spare_keys.update(prop["spare_keys"])
    node_state_map = parse_node_state(target_node) if isinstance(target_node, dict) else {}
    if isinstance(node_state_map.get("spare_keys"), Mapping):
        combined_spare_keys.update(node_state_map["spare_keys"])

    person_ties: list[Mapping[str, Any]] | None = None
    all_social_ties: list[dict[str, Any]] = []
    active_ties_by_person: dict[str, list[dict[str, Any]]] = {}
    epistemic_matrix: dict[str, Any] = {}
    if sid > 0:
        try:
            with db.get_conn() as c_ties:
                t_rows = c_ties.execute(
                    "SELECT * FROM social_ties WHERE session_id = ? AND status = 'active' ORDER BY updated_at DESC",
                    (sid,),
                ).fetchall()
            all_social_ties = [dict(tr) for tr in t_rows]
            player_tie_list: list[Mapping[str, Any]] = []
            for t_dict in all_social_ties:
                pa = str(t_dict.get("person_a_key") or "").strip().lower()
                pb = str(t_dict.get("person_b_key") or "").strip().lower()
                if pa:
                    active_ties_by_person.setdefault(pa, []).append(t_dict)
                if pb and pb != pa:
                    active_ties_by_person.setdefault(pb, []).append(t_dict)
                if pa == "player" or pb == "player" or pa.startswith("player:") or pb.startswith("player:"):
                    player_tie_list.append(t_dict)
            person_ties = player_tie_list
        except Exception:
            person_ties = []
        try:
            epistemic_matrix = db.preload_epistemic_matrix(sid) or {}
        except Exception:
            epistemic_matrix = {}

    player_home_node_id = str(
        (prim_prop or {}).get("node_id")
        or session_dict.get("player_home_node_id")
        or ""
    ).strip()

    active_wps = (db.get_all_session_active_waypoints(sid, resolve_schedule=False) or []) if sid > 0 else []
    active_commitments = (get_active_commitments(sid, commitment_type="rendezvous", limit=50) or []) if sid > 0 else []
    story_quest = db.get_active_story_quest(sid, resolve_schedule=False) if sid > 0 else None
    story_wps_for_legacy = [wp for wp in active_wps if wp.get("target_node_id")] if active_wps else []
    active_events = (db.get_world_events(sid, entity_type="macro_event") or []) if sid > 0 else []

    raw_legacy_entries, legacy_enrichment_by_key = _load_raw_legacy_entries(
        sid,
        eff_scen,
        session_dict,
        nodes_by_id,
        loc_cache,
        session_was_provided=session_was_provided,
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
        record_discovery=eff_record_discovery,
        nodes_by_id=nodes_by_id,
        loc_cache=loc_cache,
        target_node=target_node,
        prop_at_node=prop_at_node,
        prim_prop=prim_prop,
        prim_prop_loaded=prim_prop_loaded,
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
        active_commitments=active_commitments,
        story_quest=story_quest,
        story_wps_for_legacy=story_wps_for_legacy,
        active_events=active_events,
        legacy_enrichment_by_key=legacy_enrichment_by_key,
        raw_legacy_entries=raw_legacy_entries,
        player_names=player_names,
        player_hh_id=player_hh_id,
        player_last_name=player_last_name,
        active_dialogue_partners=active_dp,
        all_social_ties=all_social_ties,
        active_ties_by_person=active_ties_by_person,
        epistemic_matrix=epistemic_matrix,
        player_home_node_id=player_home_node_id,
        staged_roster_ops=staged_roster_ops,
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


_preload_presence_context = preload_presence_context


__all__ = [
    "_PresenceContext",
    "_enrich_with_legacy_meta",
    "_extract_player_identity",
    "_load_raw_legacy_entries",
    "_preload_presence_context",
    "preload_presence_context",
]
