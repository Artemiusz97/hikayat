"""
mechanics/world/presence_doorbell.py — Tier 4 Resident Doorbell Etiquette
========================================================================
Evaluates whether a resident answers the door at an unlocked concrete residence
based on schedule presence, shift-derived sleep windows, affinity/crisis overrides,
verified household cohabitation, and active spare-key grants — with zero N+1 DB reads
when called with preloaded context from `resolve_node_presence`.
"""
from __future__ import annotations

from typing import Any, Mapping

import db
from mechanics.world.anchor_schedule import (
    SHIFT_PROFILES,
    _effective_shift_windows,
    _normalize_shift_profile,
    resolve_anchor_schedule_nodes,
)
from mechanics.world.locations.residence_fog import (
    SHARED_ABSTRACT_RESIDENCE_NODE,
    _UNSET as _FOG_UNSET,
    can_materialize_npc_residence,
)
from mechanics.world.locations.residences import (
    get_player_owned_or_starter_property_for_node,
    is_npc_active_spare_key_holder,
)
from mechanics.world.npc_schedule import get_npc_scheduled_node_id
from mechanics.world.presence_graph import (
    extract_affinity,
    is_deceased_or_arrested,
    merge_npc_records,
    parse_dict,
    parse_int,
    residence_matches_node,
    slugify_key,
)
from mechanics.world.schedule_blocks import get_time_block_key
from mechanics.world.world_schedule import (
    get_scenario_sleep_minute,
    get_scenario_wake_minute,
)

_MIN_SLEEP_DOORBELL_AFFINITY = 40


def resolve_sleep_windows(
    npc: Mapping[str, Any],
    scen_key: str,
) -> list[tuple[int, int]]:
    """
    Returns `[(start_min, end_min), ...]` daily sleep intervals for an NPC based on
    `shift_profile` (`SHIFT_PROFILES`) and scenario wake/sleep defaults.
    """
    basic = parse_dict(npc.get("basic_info"))
    raw_shift = str(npc.get("shift_profile") or basic.get("shift_profile") or "").strip().lower()
    has_route = bool(npc.get("roaming_route") or basic.get("roaming_route"))
    if raw_shift or has_route:
        norm_shift = _normalize_shift_profile(raw_shift, has_route=has_route)
        if norm_shift in ("night", "evening", "rotating", "pedestrian", "street_vendor"):
            profile = SHIFT_PROFILES.get(norm_shift)
            if profile:
                _, _, windows = _effective_shift_windows(norm_shift, profile, npc)
                if windows:
                    return [(int(s), int(e)) for s, e in windows]

    sleep_start = int(get_scenario_sleep_minute(scen_key) or 1320)
    wake_end = int(get_scenario_wake_minute(scen_key) or 420)
    return [(sleep_start, 1440), (0, wake_end)]


def _in_sleep_windows(minute: int, windows: list[tuple[int, int]]) -> bool:
    m = int(minute) % 1440
    return any(s <= m < e for s, e in windows)


def is_verified_household_cohabitant(
    session_id: int,
    merged_npc: Mapping[str, Any],
    contact_row: Mapping[str, Any] | None,
    household_cache: dict[int, dict[str, Any] | None],
    player_household_id: int | None,
    player_last_name: str,
) -> bool:
    """Checks verified cohabitant / player-household status without trusting bare SQL `household_role`."""
    basic = parse_dict(merged_npc.get("basic_info"))
    c_basic = parse_dict(contact_row.get("basic_info")) if isinstance(contact_row, Mapping) else {}
    for src in (merged_npc, basic, contact_row or {}, c_basic):
        if isinstance(src, Mapping) and (src.get("cohabiting") is True or src.get("cohabiting_family") is True):
            return True
    for rec in (contact_row, merged_npc):
        if not isinstance(rec, Mapping):
            continue
        rels = rec.get("relations")
        if isinstance(rels, Mapping) and rels.get("cohabiting_family") is True:
            return True

    hh_id_val = parse_int((contact_row or {}).get("household_id")) or parse_int(merged_npc.get("household_id"))
    if not hh_id_val or not session_id:
        return False
    if player_household_id and hh_id_val == player_household_id:
        return True

    if hh_id_val not in household_cache:
        try:
            household_cache[hh_id_val] = db.get_household_by_id(hh_id_val)
        except Exception:
            household_cache[hh_id_val] = None
    hh = household_cache.get(hh_id_val)
    if not isinstance(hh, Mapping):
        return False
    hh_key = str(hh.get("household_key") or "").strip().lower()
    if hh_key.startswith("player"):
        return True
    hh_surname = str(hh.get("surname") or "").strip().lower()
    return bool(hh_surname and player_last_name and hh_surname == player_last_name)


def check_doorbell_etiquette(
    session_id: int,
    npc: Mapping[str, Any],
    node_id: str,
    current_day: int | None = None,
    current_minute: int | None = None,
    *,
    scen_key: str = "",
    session: Mapping[str, Any] | None = None,
    has_active_override_pin: bool = False,
    nodes_by_id: Mapping[str, dict[str, Any]] | None = None,
    roster_row: Mapping[str, Any] | None = None,
    roster_loaded: bool = False,
    contact_row: Mapping[str, Any] | None = None,
    contacts: list[dict[str, Any]] | None = None,
    contacts_loaded: bool = False,
    person_ties: list[Mapping[str, Any]] | None = None,
    primary_property: Mapping[str, Any] | None = None,
    primary_property_loaded: bool = False,
    spare_keys: Mapping[str, Any] | None = None,
    scheduled_node_id: str | None = None,
    household_cache: dict[int, dict[str, Any] | None] | None = None,
    player_household_id: int | None = None,
    player_last_name: str = "",
    player_last_name_loaded: bool = False,
    autonomy_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Evaluate Tier 4 doorbell etiquette when approaching an NPC's unlocked concrete residence.
    Never runs on `zone_residential_abstract` (`SHARED_ABSTRACT_RESIDENCE_NODE`) or empty `node_id`.
    """
    tgt_nid = str(node_id or "").strip()
    npc_name = str(npc.get("name") or parse_dict(npc.get("basic_info")).get("name") or "").strip()
    npc_id = str(npc.get("npc_id") or npc.get("npc_key") or slugify_key(npc_name)).strip()

    def _result(
        *,
        applicable: bool,
        doorbell_status: str,
        allowed: bool,
        should_block_sleep: bool = False,
        reason: str = "",
        home_node_id: str = "",
        override_reason: str = "",
    ) -> dict[str, Any]:
        return {
            "applicable": applicable,
            "doorbell_status": doorbell_status,
            "status": doorbell_status,
            "allowed": allowed,
            "should_block_sleep": should_block_sleep,
            "npc_id": npc_id,
            "name": npc_name,
            "node_id": tgt_nid,
            "home_node_id": home_node_id,
            "reason": reason,
            "override_reason": override_reason,
        }

    if not tgt_nid or tgt_nid == SHARED_ABSTRACT_RESIDENCE_NODE:
        return _result(
            applicable=False,
            doorbell_status="not_applicable",
            allowed=False,
            reason="abstract_or_empty_node",
        )

    sid = int(session_id or 0)
    eff_session = session if isinstance(session, Mapping) else (db.get_session(sid) or {} if sid > 0 else {})
    eff_scen = str(scen_key or eff_session.get("scenario") or "fantasy").strip() or "fantasy"
    if current_day is None or current_minute is None:
        db_day, db_min, _ = db.get_session_time(sid) if sid > 0 else (1, 600, 1)
        safe_day = max(1, int(current_day if current_day is not None else db_day or 1))
        safe_min = int(current_minute if current_minute is not None else db_min or 0) % 1440
    else:
        safe_day = max(1, int(current_day or 1))
        safe_min = int(current_minute or 0) % 1440

    local_nodes = nodes_by_id
    if local_nodes is None:
        raw_nodes = db.get_session_world_nodes(sid) if sid > 0 else []
        local_nodes = {
            str(n["node_id"]): n
            for n in (raw_nodes or [])
            if isinstance(n, dict) and n.get("node_id")
        }

    eff_contact = contact_row
    if eff_contact is None and not contacts_loaded and sid > 0 and (npc_id or npc_name):
        try:
            eff_contact = db.get_contact(sid, npc_name or npc_id)
        except Exception:
            eff_contact = None

    eff_roster = roster_row
    if eff_roster is None and not roster_loaded and sid > 0 and (npc_id or npc_name):
        if not str(npc.get("home_node_id") or "").strip():
            try:
                got_roster = db.get_world_roster_npc(sid, npc_id or npc_name, include_legacy_rosters=False)
                if isinstance(got_roster, Mapping):
                    eff_roster = got_roster
            except Exception:
                eff_roster = None

    eff_npc: Mapping[str, Any] = {**eff_roster, **dict(npc)} if isinstance(eff_roster, Mapping) else npc
    merged = merge_npc_records(eff_npc, eff_contact)
    if is_deceased_or_arrested(merged):
        return _result(applicable=False, doorbell_status="unavailable", allowed=False, reason="casualty")

    basic = parse_dict(merged.get("basic_info"))
    home_nid = str(merged.get("home_node_id") or basic.get("home_node_id") or "").strip()
    if not residence_matches_node(home_nid, tgt_nid, local_nodes):
        return _result(
            applicable=False,
            doorbell_status="not_applicable",
            allowed=False,
            reason="not_resident",
            home_node_id=home_nid,
        )

    eff_prim_prop = primary_property
    if not primary_property_loaded and sid > 0:
        try:
            eff_prim_prop = db.get_primary_property(sid)
        except Exception:
            eff_prim_prop = None

    fog_roster = eff_roster if (eff_roster is not None or roster_loaded) else _FOG_UNSET
    fog_contact = eff_contact if (eff_contact is not None or contacts_loaded) else _FOG_UNSET
    fog_prop = eff_prim_prop if (eff_prim_prop is not None or primary_property_loaded) else _FOG_UNSET

    local_hh_cache = household_cache if household_cache is not None else {}
    p_last = player_last_name
    if not p_last and not player_last_name_loaded and sid > 0:
        char_id = parse_int(eff_session.get("character_id"))
        if char_id:
            try:
                p_char = db.get_character_by_id(char_id)
                p_parts = str((p_char or {}).get("name") or "").strip().split()
                p_last = p_parts[-1].lower() if p_parts else ""
            except Exception:
                p_last = ""

    if not can_materialize_npc_residence(
        sid if sid > 0 else None,
        merged,
        roster_row=fog_roster,
        contact_row=fog_contact,
        primary_property=fog_prop,
        contacts=contacts,
        person_ties=person_ties,
        household_cache=local_hh_cache,
        player_last_name=p_last,
    ):
        return _result(
            applicable=False,
            doorbell_status="not_applicable",
            allowed=False,
            reason="residence_fogged",
            home_node_id=home_nid,
        )

    eff_sched_nid = scheduled_node_id
    if eff_sched_nid is None:
        probe = dict(merged)
        probe["residence_unlocked"] = True
        probe["use_anchor_schedule"] = True
        probe["_roster_premerged"] = True
        probe["_db_hydrated"] = True
        anchor_map = resolve_anchor_schedule_nodes(
            probe,
            current_day=safe_day,
            scen_key=eff_scen,
            session_id=None,
            current_minute=safe_min,
        )
        if anchor_map is not None:
            eff_sched_nid = str(anchor_map.get(get_time_block_key(safe_min)) or "").strip()
        else:
            sched_sid = None if (roster_loaded and contacts_loaded) else (sid or None)
            eff_sched_nid = str(
                get_npc_scheduled_node_id(
                    probe,
                    current_minute=safe_min,
                    scen_key=eff_scen,
                    current_day=safe_day,
                    session_id=sched_sid,
                )
                or ""
            ).strip()

    if isinstance(autonomy_override, Mapping) and autonomy_override.get("node_id"):
        ov_nid = str(autonomy_override["node_id"]).strip()
        if residence_matches_node(ov_nid, tgt_nid, local_nodes) and autonomy_override.get("is_dropby"):
            return _result(
                applicable=True,
                doorbell_status="visitor_dropby",
                allowed=True,
                reason=str(autonomy_override.get("visit_label") or "Dropping by"),
                home_node_id=home_nid,
                override_reason="dropby",
            )
        if not residence_matches_node(ov_nid, tgt_nid, local_nodes):
            return _result(
                applicable=True,
                doorbell_status="not_home",
                allowed=False,
                reason=str(autonomy_override.get("visit_label") or autonomy_override.get("reason") or "scheduled_elsewhere"),
                home_node_id=home_nid,
                override_reason=str(autonomy_override.get("reason") or ""),
            )

    is_home_now = bool(eff_sched_nid and residence_matches_node(eff_sched_nid, tgt_nid, local_nodes))
    if not is_home_now:
        not_home_reason = "scheduled_elsewhere"
        if isinstance(autonomy_override, Mapping) and (autonomy_override.get("visit_label") or autonomy_override.get("reason")):
            not_home_reason = str(autonomy_override.get("visit_label") or autonomy_override.get("reason"))
        return _result(
            applicable=True,
            doorbell_status="not_home",
            allowed=False,
            reason=not_home_reason,
            home_node_id=home_nid,
        )

    sleep_windows = resolve_sleep_windows(merged, eff_scen)
    if not _in_sleep_windows(safe_min, sleep_windows):
        return _result(
            applicable=True,
            doorbell_status="answered",
            allowed=True,
            reason="waking_hours_at_home",
            home_node_id=home_nid,
        )

    if has_active_override_pin:
        return _result(
            applicable=True,
            doorbell_status="answered",
            allowed=True,
            reason="sleep_override",
            home_node_id=home_nid,
            override_reason="commitment_or_crisis",
        )

    if extract_affinity(merged, eff_contact) >= _MIN_SLEEP_DOORBELL_AFFINITY:
        return _result(
            applicable=True,
            doorbell_status="answered",
            allowed=True,
            reason="sleep_override",
            home_node_id=home_nid,
            override_reason="affinity",
        )

    if is_verified_household_cohabitant(sid, merged, eff_contact, local_hh_cache, player_household_id, p_last):
        return _result(
            applicable=True,
            doorbell_status="answered",
            allowed=True,
            reason="sleep_override",
            home_node_id=home_nid,
            override_reason="cohabitant",
        )

    eff_spare_keys = spare_keys
    if eff_spare_keys is None and sid > 0:
        combined: dict[str, Any] = {}
        prop_node = get_player_owned_or_starter_property_for_node(sid, tgt_nid, session=eff_session)
        if isinstance(prop_node, Mapping) and isinstance(prop_node.get("spare_keys"), Mapping):
            combined.update(prop_node["spare_keys"])
        if isinstance(eff_prim_prop, Mapping) and isinstance(eff_prim_prop.get("spare_keys"), Mapping):
            combined.update(eff_prim_prop["spare_keys"])
        eff_spare_keys = combined

    if eff_spare_keys and sid > 0 and is_npc_active_spare_key_holder(
        sid, merged, eff_spare_keys, contacts=contacts, person_ties=person_ties
    ):
        return _result(
            applicable=True,
            doorbell_status="answered",
            allowed=True,
            reason="sleep_override",
            home_node_id=home_nid,
            override_reason="spare_key",
        )

    return _result(
        applicable=True,
        doorbell_status="refused_asleep",
        allowed=False,
        should_block_sleep=True,
        reason="sleeping_no_override",
        home_node_id=home_nid,
    )
