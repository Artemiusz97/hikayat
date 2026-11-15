"""
mechanics/world/presence_resolver.py — Unified 6-Tier Pre-Turn Presence Resolver
=================================================================================
Deterministic closed-world NPC presence evaluation before narrative generation.
Resolves who is physically present at a location across 6 strict precedence tiers:

  Tier 1 (party): Party members, companions, temporary escorts, and `staff_status == "in_party"`.
  Tier 2 (commitment): Confirmed active commitments / phone appointments within time window.
  Tier 3 (quest_pin): Active quest/bounty waypoints and story objectives pinned at this node.
  Tier 4 (doorbell_answered / doorbell_events): Resident doorbell etiquette at unlocked residences.
  Tier 5 (schedule): Active anchor-node schedules (closed-world `world_roster`) + legacy schedule pools.
  Tier 6 (crowd_flavor): Atmospheric unnamed venue flavor when no NPC is present (zero DB writes).
"""
from __future__ import annotations

import json
import re
from typing import Any, Mapping

import db
from db.world import _LEGACY_NODE_ID_ALIASES
import scenario_data
from mechanics.system.commitments_engine import get_active_rendezvous_at_node
from mechanics.world.anchor_schedule import (
    is_npc_on_active_shift,
    resolve_anchor_schedule_nodes,
)
from mechanics.world.locations.residence_fog import (
    SHARED_ABSTRACT_RESIDENCE_NODE,
    can_materialize_npc_residence,
)
from mechanics.world.locations.residences import (
    get_player_owned_or_starter_property_for_node,
    is_npc_active_spare_key_holder,
)
from mechanics.world.npc_schedule import (
    get_npc_scheduled_node_id,
    is_high_school_setting,
)
from mechanics.world.schedule_blocks import get_time_block_key
from mechanics.world.venue_seeder import (
    ensure_roaming_merchants_seeded,
    ensure_venue_staff_seeded,
    format_venue_crowd_flavor,
)
from mechanics.world.venue_templates import (
    HOSPITALITY_OUTPOST_OVERRIDE_KEYWORDS,
    PRIVATE_RESIDENCE_KEYWORDS,
    STAFFED_VENUE_OVERRIDE_KEYWORDS,
    WILDERNESS_DUNGEON_KEYWORDS,
    is_node_staffable,
    parse_node_state,
)
from mechanics.world.waypoints.matching import (
    check_location_matches_waypoint,
    get_waypoint_npc_schedule_info,
    is_hostile_or_lair_waypoint,
)
from mechanics.world.world_schedule import is_weekend


_CRISIS_KEYWORDS: tuple[str, ...] = (
    "crisis", "ambush", "emergency", "under siege", "attack", "assault", "rescue",
)
_SLEEP_WINDOW_START_MIN = 1320  # 22:00
_SLEEP_WINDOW_END_MIN = 420     # 07:00
_MIN_SLEEP_DOORBELL_AFFINITY = 40
_PLAYER_SELF_TOKENS: frozenset[str] = frozenset({"player", "you", "mc", "protagonist"})


def _slugify(raw: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(raw or "").strip().lower()).strip("_")


def _parse_int(raw: Any) -> int | None:
    if raw is None or raw == "" or isinstance(raw, bool):
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def _parse_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except (ValueError, TypeError):
            pass
    return {}


def _is_deceased_or_arrested(rec: Mapping[str, Any] | None) -> bool:
    if not isinstance(rec, Mapping):
        return False
    basic = _parse_dict(rec.get("basic_info"))
    status = str(rec.get("staff_status") or basic.get("staff_status") or "").strip().lower()
    if status in ("dead", "arrested", "deceased"):
        return True
    if bool(rec.get("is_deceased") or basic.get("is_deceased") or basic.get("deceased")):
        return True
    if rec.get("alive") is False or basic.get("alive") is False:
        return True
    return str(basic.get("status") or "").strip().lower() in ("dead", "deceased", "arrested")


def _extract_affinity(roster_row: Mapping[str, Any] | None, contact_row: Mapping[str, Any] | None) -> int:
    scores: list[int] = []
    for src in (roster_row, contact_row):
        if not isinstance(src, Mapping):
            continue
        basic = _parse_dict(src.get("basic_info"))
        for cand in (
            src.get("affinity_score"),
            src.get("interaction_score"),
            src.get("relationship_score"),
            basic.get("affinity_score"),
            basic.get("interaction_score"),
            basic.get("relationship_score"),
        ):
            parsed = _parse_int(cand)
            if parsed is not None:
                scores.append(parsed)
    return max(scores) if scores else 0


def _npc_aliases(rec: Mapping[str, Any] | None) -> set[str]:
    if not isinstance(rec, Mapping):
        return set()
    basic = _parse_dict(rec.get("basic_info"))
    raw_vals = (
        rec.get("npc_id"),
        rec.get("npc_key"),
        rec.get("name"),
        basic.get("npc_id"),
        basic.get("name"),
    )
    aliases: set[str] = set()
    for val in raw_vals:
        s = str(val or "").strip().lower()
        if s:
            aliases.add(s)
            slug = _slugify(s)
            if slug:
                aliases.add(slug)
    return aliases


def _merge_npc_records(
    primary: Mapping[str, Any] | None,
    secondary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    base_basic: dict[str, Any] = {}
    for src in (secondary, primary):
        if not isinstance(src, Mapping):
            continue
        src_basic = _parse_dict(src.get("basic_info"))
        for k, v in src_basic.items():
            if v not in (None, ""):
                base_basic[k] = v
        for k, v in src.items():
            if k == "basic_info":
                continue
            if v not in (None, "") or k not in merged:
                merged[k] = v
    merged["basic_info"] = base_basic
    if not merged.get("name") and base_basic.get("name"):
        merged["name"] = base_basic["name"]
    if not merged.get("npc_id") and merged.get("npc_key"):
        merged["npc_id"] = merged["npc_key"]
    return merged


def _in_mem_ancestors(node_id: str, nodes_by_id: Mapping[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    curr = nodes_by_id.get(node_id)
    visited: set[str] = {node_id}
    while isinstance(curr, dict) and curr.get("parent_id"):
        pid = str(curr["parent_id"])
        if pid in visited:
            break
        visited.add(pid)
        parent = nodes_by_id.get(pid)
        if not parent:
            break
        out.append(parent)
        curr = parent
    return out


def is_node_descendant_in_memory(
    node_id: str,
    ancestor_id: str,
    nodes_by_id: Mapping[str, dict[str, Any]],
) -> bool:
    if not node_id or not ancestor_id:
        return False
    if node_id == ancestor_id:
        return True
    if _LEGACY_NODE_ID_ALIASES.get(node_id.lower()) == ancestor_id or node_id == _LEGACY_NODE_ID_ALIASES.get(ancestor_id.lower()):
        return True
    anc_target = _LEGACY_NODE_ID_ALIASES.get(ancestor_id.lower(), ancestor_id)
    return any(a.get("node_id") in (ancestor_id, anc_target) for a in _in_mem_ancestors(node_id, nodes_by_id))


def resolve_node_id_in_memory(
    location_str: str,
    nodes_by_id: Mapping[str, dict[str, Any]],
    prefer_facility: bool = True,
    cache: dict[tuple[str, bool], str] | None = None,
) -> str:
    loc_clean = str(location_str or "").strip()
    if not loc_clean or not nodes_by_id:
        return ""
    c_key = (loc_clean, prefer_facility)
    if cache is not None and c_key in cache:
        return cache[c_key]

    resolved = ""
    if loc_clean in nodes_by_id:
        resolved = loc_clean
    if not resolved:
        alias = _LEGACY_NODE_ID_ALIASES.get(loc_clean.lower())
        if alias and alias in nodes_by_id:
            resolved = alias
    if not resolved:
        low_clean = loc_clean.lower()
        for nid in nodes_by_id:
            if nid.lower() == low_clean:
                resolved = nid
                break

    if not resolved:
        parts = [p.strip() for p in re.split(r"\s*(?:➔|->|>|/)\s*", loc_clean) if p.strip()]
        leaf_name = parts[-1].lower() if parts else ""
        prim_name = parts[1].lower() if len(parts) >= 2 else (parts[0].lower() if parts else "")
        nodes = list(nodes_by_id.values())

        prim_node: dict[str, Any] | None = None
        if prim_name:
            for n in nodes:
                if n.get("node_type") in ("FACILITY", "ZONE") and str(n.get("name") or "").lower() == prim_name:
                    prim_node = n
                    break
            if prim_node is None:
                for n in nodes:
                    n_low = str(n.get("name") or "").lower()
                    if n.get("node_type") in ("FACILITY", "ZONE") and (prim_name in n_low or n_low in prim_name):
                        prim_node = n
                        break
        if prim_node is not None:
            if prefer_facility:
                resolved = str(prim_node["node_id"])
            elif leaf_name and leaf_name != prim_name:
                child = next(
                    (
                        rn for rn in nodes
                        if rn.get("parent_id") == prim_node["node_id"]
                        and str(rn.get("name") or "").lower() == leaf_name
                    ),
                    None,
                )
                if child is None and leaf_name not in ("main area", "area", "main"):
                    child = next(
                        (
                            rn for rn in nodes
                            if rn.get("parent_id") == prim_node["node_id"]
                            and (leaf_name in str(rn.get("name") or "").lower() or str(rn.get("name") or "").lower() in leaf_name)
                        ),
                        None,
                    )
                resolved = str((child or prim_node)["node_id"])
            else:
                resolved = str(prim_node["node_id"])

        if not resolved and leaf_name and leaf_name not in ("main area", "area", "main"):
            type_order = ("FACILITY", "ZONE", "ROOM") if prefer_facility else ("ROOM", "FACILITY", "ZONE")
            for n_type in type_order:
                for n in nodes:
                    if n.get("node_type") == n_type and str(n.get("name") or "").lower() == leaf_name:
                        resolved = str(n["node_id"])
                        break
                if resolved:
                    break

        if not resolved and leaf_name and len(leaf_name) >= 4 and leaf_name not in ("main area", "area", "main"):
            for n in nodes:
                n_low = str(n.get("name") or "").lower()
                if leaf_name in n_low or n_low in leaf_name:
                    resolved = str(n["node_id"])
                    break

    if cache is not None:
        cache[c_key] = resolved
    return resolved


def _location_targets_node(
    target_node_id: str,
    target_loc: str,
    eff_node_id: str,
    eff_loc: str,
    nodes_by_id: Mapping[str, dict[str, Any]],
    loc_cache: dict[tuple[str, bool], str],
) -> bool:
    t_nid = str(target_node_id or "").strip()
    if not t_nid and target_loc and nodes_by_id:
        t_nid = resolve_node_id_in_memory(target_loc, nodes_by_id, prefer_facility=False, cache=loc_cache)

    if eff_node_id and t_nid:
        if eff_node_id == t_nid:
            return True
        if is_node_descendant_in_memory(eff_node_id, t_nid, nodes_by_id):
            return True
        target_type = str((nodes_by_id.get(eff_node_id) or {}).get("node_type") or "").upper()
        if target_type != "ZONE" and is_node_descendant_in_memory(t_nid, eff_node_id, nodes_by_id):
            return True
        return False

    if eff_loc and target_loc:
        return bool(
            check_location_matches_waypoint(eff_loc, target_loc)
            or check_location_matches_waypoint(target_loc, eff_loc)
        )
    return not t_nid and not target_loc


def _residence_matches_node(
    home_node_id: str,
    target_node_id: str,
    nodes_by_id: Mapping[str, dict[str, Any]],
) -> bool:
    home_nid = str(home_node_id or "").strip()
    tgt_nid = str(target_node_id or "").strip()
    if not home_nid or not tgt_nid or home_nid == SHARED_ABSTRACT_RESIDENCE_NODE or tgt_nid == SHARED_ABSTRACT_RESIDENCE_NODE:
        return False
    if home_nid == tgt_nid:
        return True
    tgt_node = nodes_by_id.get(tgt_nid)
    home_node = nodes_by_id.get(home_nid)
    if isinstance(tgt_node, Mapping) and str(tgt_node.get("node_type") or "").upper() == "FACILITY":
        if isinstance(home_node, Mapping) and home_node.get("parent_id") == tgt_nid:
            return True
    if isinstance(tgt_node, Mapping) and tgt_node.get("parent_id") == home_nid:
        if isinstance(home_node, Mapping) and str(home_node.get("node_type") or "").upper() == "FACILITY":
            return True
    return False


def _format_node_display_label(
    node_id: str,
    location_str: str,
    nodes_by_id: Mapping[str, dict[str, Any]],
) -> str:
    node = nodes_by_id.get(node_id)
    if isinstance(node, Mapping):
        chain: list[str] = []
        ancs = _in_mem_ancestors(node_id, nodes_by_id)
        for anc in reversed(ancs):
            nm = str(anc.get("name") or "").strip()
            if nm:
                chain.append(nm)
        self_name = str(node.get("name") or "").strip()
        if self_name:
            chain.append(self_name)
        if chain:
            return " ➔ ".join(chain)
    return str(location_str or node_id or "").strip()


def _is_private_home_or_wilderness(
    target_node: Mapping[str, Any] | None,
    eff_node_id: str,
    eff_loc: str,
    prop_at_node: Mapping[str, Any] | None,
) -> bool:
    if prop_at_node is not None:
        return True
    node_state = parse_node_state(dict(target_node)) if isinstance(target_node, Mapping) else {}
    if bool(node_state.get("is_player_residence") or node_state.get("owner_npc_id") or node_state.get("owner_npc_name")):
        return True
    if eff_node_id.startswith(("fac_npc_res_", "sub_npc_res_")):
        return True
    if str((target_node or {}).get("privacy_level") or "").strip().lower() == "private":
        return True

    combined = f"{(target_node or {}).get('name') or ''} {eff_loc}".lower()
    cat = str((target_node or {}).get("category") or "").strip().lower()
    has_hosp_or_staff = any(k in combined for k in HOSPITALITY_OUTPOST_OVERRIDE_KEYWORDS) or any(
        k in combined for k in STAFFED_VENUE_OVERRIDE_KEYWORDS
    )
    if any(kw in combined for kw in PRIVATE_RESIDENCE_KEYWORDS) and not has_hosp_or_staff:
        return True
    if (cat == "wilderness" or any(kw in combined for kw in WILDERNESS_DUNGEON_KEYWORDS)) and not has_hosp_or_staff:
        return True
    return False


def _is_verified_household_cohabitant(
    session_id: int,
    merged_npc: Mapping[str, Any],
    contact_row: Mapping[str, Any] | None,
    household_cache: dict[int, dict[str, Any] | None],
    player_household_id: int | None,
    player_last_name: str,
) -> bool:
    """Checks verified cohabitant / player-household status without trusting bare SQL `household_role`."""
    basic = _parse_dict(merged_npc.get("basic_info"))
    c_basic = _parse_dict(contact_row.get("basic_info")) if isinstance(contact_row, Mapping) else {}
    for src in (merged_npc, basic, contact_row or {}, c_basic):
        if isinstance(src, Mapping) and (src.get("cohabiting") is True or src.get("cohabiting_family") is True):
            return True
    for rec in (contact_row, merged_npc):
        if not isinstance(rec, Mapping):
            continue
        rels = rec.get("relations")
        if isinstance(rels, Mapping) and rels.get("cohabiting_family") is True:
            return True

    hh_id_val = _parse_int((contact_row or {}).get("household_id")) or _parse_int(merged_npc.get("household_id"))
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


def _compute_appt_abs_window(appt: Mapping[str, Any]) -> tuple[int, int]:
    s_day = max(1, int(appt.get("scheduled_day") or 1))
    s_min = max(0, int(appt.get("start_minute") if appt.get("start_minute") is not None else 0))
    raw_end = int(appt.get("end_minute") if appt.get("end_minute") is not None else 1439)
    if raw_end >= 1440:
        extra_days, e_min = divmod(raw_end, 1440)
        e_day = s_day + extra_days
    else:
        e_min = max(0, raw_end)
        if appt.get("end_day") is not None:
            e_day = max(s_day, int(appt["end_day"]))
        elif e_min < s_min:
            e_day = s_day + 1
        else:
            e_day = s_day
    return (s_day - 1) * 1440 + s_min, (e_day - 1) * 1440 + e_min


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
    contact_row: Mapping[str, Any] | None = None,
    spare_keys: Mapping[str, Any] | None = None,
    scheduled_node_id: str | None = None,
    household_cache: dict[int, dict[str, Any] | None] | None = None,
    player_household_id: int | None = None,
    player_last_name: str = "",
) -> dict[str, Any]:
    """
    Evaluate Tier 4 doorbell etiquette when approaching an NPC's unlocked concrete residence.
    Never runs on `zone_residential_abstract` (`SHARED_ABSTRACT_RESIDENCE_NODE`) or empty `node_id`.
    """
    tgt_nid = str(node_id or "").strip()
    npc_name = str(npc.get("name") or _parse_dict(npc.get("basic_info")).get("name") or "").strip()
    npc_id = str(npc.get("npc_id") or npc.get("npc_key") or _slugify(npc_name)).strip()

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
        return _result(applicable=False, doorbell_status="not_applicable", allowed=False, reason="abstract_or_empty_node")

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
        local_nodes = {str(n["node_id"]): n for n in (raw_nodes or []) if isinstance(n, dict) and n.get("node_id")}

    eff_contact = contact_row
    if eff_contact is None and sid > 0 and (npc_id or npc_name):
        try:
            eff_contact = db.get_contact(sid, npc_name or npc_id)
        except Exception:
            eff_contact = None

    eff_npc: Mapping[str, Any] = npc
    if nodes_by_id is None and sid > 0 and (npc_id or npc_name) and not str(npc.get("home_node_id") or "").strip():
        try:
            roster_row = db.get_world_roster_npc(sid, npc_id or npc_name, include_legacy_rosters=False)
            if isinstance(roster_row, Mapping):
                eff_npc = {**roster_row, **dict(npc)}
        except Exception:
            pass

    merged = _merge_npc_records(eff_npc, eff_contact)
    if _is_deceased_or_arrested(merged):
        return _result(applicable=False, doorbell_status="unavailable", allowed=False, reason="casualty")

    basic = _parse_dict(merged.get("basic_info"))
    home_nid = str(merged.get("home_node_id") or basic.get("home_node_id") or "").strip()
    if not _residence_matches_node(home_nid, tgt_nid, local_nodes):
        return _result(applicable=False, doorbell_status="not_applicable", allowed=False, reason="not_resident", home_node_id=home_nid)

    if not can_materialize_npc_residence(sid if sid > 0 else None, merged):
        return _result(applicable=False, doorbell_status="not_applicable", allowed=False, reason="residence_fogged", home_node_id=home_nid)

    eff_sched_nid = scheduled_node_id
    if eff_sched_nid is None:
        probe = dict(merged)
        probe["use_anchor_schedule"] = True
        anchor_map = resolve_anchor_schedule_nodes(probe, current_day=safe_day, scen_key=eff_scen, session_id=None, current_minute=safe_min)
        if anchor_map is not None:
            eff_sched_nid = str(anchor_map.get(get_time_block_key(safe_min)) or "").strip()
        else:
            eff_sched_nid = str(get_npc_scheduled_node_id(probe, current_minute=safe_min, scen_key=eff_scen, current_day=safe_day, session_id=sid or None) or "").strip()

    is_home_now = bool(eff_sched_nid and _residence_matches_node(eff_sched_nid, tgt_nid, local_nodes))
    if not is_home_now:
        return _result(applicable=True, doorbell_status="not_home", allowed=False, reason="scheduled_elsewhere", home_node_id=home_nid)

    in_sleep_window = safe_min >= _SLEEP_WINDOW_START_MIN or safe_min < _SLEEP_WINDOW_END_MIN
    if not in_sleep_window:
        return _result(applicable=True, doorbell_status="answered", allowed=True, reason="waking_hours_at_home", home_node_id=home_nid)

    if has_active_override_pin:
        return _result(applicable=True, doorbell_status="answered", allowed=True, reason="sleep_override", home_node_id=home_nid, override_reason="commitment_or_crisis")

    if _extract_affinity(merged, eff_contact) >= _MIN_SLEEP_DOORBELL_AFFINITY:
        return _result(applicable=True, doorbell_status="answered", allowed=True, reason="sleep_override", home_node_id=home_nid, override_reason="affinity")

    local_hh_cache = household_cache if household_cache is not None else {}
    p_last = player_last_name
    if not p_last and sid > 0:
        char_id = _parse_int(eff_session.get("character_id"))
        if char_id:
            p_char = db.get_character_by_id(char_id)
            p_parts = str((p_char or {}).get("name") or "").strip().split()
            p_last = p_parts[-1].lower() if p_parts else ""
    if _is_verified_household_cohabitant(sid, merged, eff_contact, local_hh_cache, player_household_id, p_last):
        return _result(applicable=True, doorbell_status="answered", allowed=True, reason="sleep_override", home_node_id=home_nid, override_reason="cohabitant")

    eff_spare_keys = spare_keys
    if eff_spare_keys is None and sid > 0:
        combined: dict[str, Any] = {}
        prop_node = get_player_owned_or_starter_property_for_node(sid, tgt_nid, session=eff_session)
        if isinstance(prop_node, Mapping) and isinstance(prop_node.get("spare_keys"), Mapping):
            combined.update(prop_node["spare_keys"])
        prim_prop = db.get_primary_property(sid)
        if isinstance(prim_prop, Mapping) and isinstance(prim_prop.get("spare_keys"), Mapping):
            combined.update(prim_prop["spare_keys"])
        eff_spare_keys = combined

    if eff_spare_keys and sid > 0 and is_npc_active_spare_key_holder(sid, merged, eff_spare_keys):
        return _result(applicable=True, doorbell_status="answered", allowed=True, reason="sleep_override", home_node_id=home_nid, override_reason="spare_key")

    return _result(applicable=True, doorbell_status="refused_asleep", allowed=False, should_block_sleep=True, reason="sleeping_no_override", home_node_id=home_nid)


def _extract_player_names(session_dict: Mapping[str, Any]) -> tuple[set[str], int | None, str]:
    player_names = set(_PLAYER_SELF_TOKENS)
    player_last_name = ""
    player_hh_id = _parse_int(session_dict.get("household_id"))
    char_name = str(session_dict.get("character_name") or "").strip()
    if char_name:
        player_names.add(char_name.lower())
        player_last_name = char_name.split()[-1].lower()
    char_id = _parse_int(session_dict.get("character_id"))
    if char_id:
        try:
            p_char = db.get_character_by_id(char_id)
            if isinstance(p_char, Mapping):
                cn = str(p_char.get("name") or "").strip()
                if cn:
                    player_names.add(cn.lower())
                    player_last_name = cn.split()[-1].lower()
                if not player_hh_id:
                    player_hh_id = _parse_int(p_char.get("household_id"))
        except Exception:
            pass
    return player_names, player_hh_id, player_last_name


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
    if not eff_node_id and eff_loc and sid > 0:
        eff_node_id = str(db.resolve_node_id_from_location(sid, eff_loc, prefer_facility=True) or "").strip()

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
    for c in contacts:
        if not isinstance(c, dict):
            continue
        c_name = str(c.get("name") or "").strip().lower()
        if c_name:
            contacts_by_name[c_name] = c
        for ak in _npc_aliases(c):
            contacts_by_key[ak] = c

    roster_by_key: dict[str, dict[str, Any]] = {}
    casualty_keys: set[str] = set()
    for r in roster_rows:
        if not isinstance(r, dict):
            continue
        aliases = _npc_aliases(r)
        for ak in aliases:
            roster_by_key[ak] = r
        if _is_deceased_or_arrested(r):
            casualty_keys.update(aliases)
    for c in contacts:
        if _is_deceased_or_arrested(c):
            casualty_keys.update(_npc_aliases(c))

    staged_by_key: dict[str, dict[str, Any]] = {}
    staged_order: list[str] = []
    blocked_sleeping_keys: set[str] = set()
    player_names, player_hh_id, player_last_name = _extract_player_names(session_dict)

    def _find_linked(name_or_id: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        raw_s = str(name_or_id or "").strip().lower()
        slug_s = _slugify(raw_s)
        r_row = roster_by_key.get(raw_s) or roster_by_key.get(slug_s)
        c_row = contacts_by_key.get(raw_s) or contacts_by_key.get(slug_s)
        if r_row and not c_row:
            for ak in _npc_aliases(r_row):
                if ak in contacts_by_key:
                    c_row = contacts_by_key[ak]
                    break
        if c_row and not r_row:
            for ak in _npc_aliases(c_row):
                if ak in roster_by_key:
                    r_row = roster_by_key[ak]
                    break
        return r_row, c_row

    def _is_already_staged(aliases: set[str]) -> bool:
        return any(ak in staged_by_key for ak in aliases)

    def _is_blocked_casualty(aliases: set[str]) -> bool:
        return bool(aliases & casualty_keys)

    def _stage(raw_rec: Mapping[str, Any], tier: int, reason: str, extra: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
        raw_name = str(raw_rec.get("name") or raw_rec.get("npc_name") or raw_rec.get("npc_id") or "").strip()
        if not raw_name or raw_name.lower() in player_names:
            return None
        r_row, c_row = _find_linked(raw_rec.get("npc_id") or raw_name)
        merged = _merge_npc_records(raw_rec, _merge_npc_records(r_row, c_row))
        aliases = _npc_aliases(merged) | {raw_name.lower(), _slugify(raw_name)}
        aliases.discard("")
        if _is_blocked_casualty(aliases) or _is_already_staged(aliases):
            return None
        merged["name"] = str(merged.get("name") or raw_name).strip()
        merged["npc_id"] = str(merged.get("npc_id") or merged.get("npc_key") or _slugify(merged["name"])).strip()
        merged["presence_tier"] = tier
        merged["presence_reason"] = reason
        if isinstance(extra, Mapping):
            merged.update(extra)
        canonical_key = _slugify(merged["name"]) or merged["npc_id"].lower()
        staged_order.append(canonical_key)
        for ak in aliases | {canonical_key}:
            staged_by_key[ak] = merged
        return merged

    # ------------------------------------------------------------------
    # Tier 1: Party / Escort / Active `in_party` Roster Members
    # ------------------------------------------------------------------
    tier1_entries: list[dict[str, Any]] = []
    raw_party_lists = [
        list(party_names or ()),
        list(session_dict.get("party_npcs") or ()),
        list(session_dict.get("temporary_companions") or ()),
        list(session_dict.get("party") or ()),
    ]
    for grp in raw_party_lists:
        for item in grp:
            obj = item[0] if isinstance(item, (tuple, list)) and item else item
            if isinstance(obj, Mapping):
                tier1_entries.append(dict(obj))
            elif isinstance(obj, str) and obj.strip():
                tier1_entries.append({"name": obj.strip()})
    for r in roster_rows:
        if str(r.get("staff_status") or "").strip().lower() == "in_party":
            tier1_entries.append(dict(r))
    for entry in tier1_entries:
        _stage(entry, 1, "party")

    # ------------------------------------------------------------------
    # Tier 2: Confirmed Active Commitments / Rendezvous Appointments
    # ------------------------------------------------------------------
    abs_now = (safe_day - 1) * 1440 + safe_min
    tier2_aliases: set[str] = set()
    if sid > 0 and (eff_node_id or eff_loc):
        rendez_hits = get_active_rendezvous_at_node(
            sid, eff_node_id or eff_loc, current_day=safe_day, current_minute=safe_min, enforce_window=True
        ) or []
        for rc in rendez_hits:
            staged_any = False
            for p in (rc.get("participants") or []):
                if not isinstance(p, Mapping):
                    continue
                pk = str(p.get("person_key") or p.get("npc_id") or "").strip()
                p_name = str(p.get("name") or p.get("npc_name") or "").strip()
                if pk.lower() == "player" or pk.lower().startswith("player:") or p_name.lower() in player_names:
                    continue
                cand_name = p_name or pk.replace("_", " ").title()
                if cand_name:
                    tier2_aliases.update({cand_name.lower(), _slugify(cand_name), pk.lower()})
                    _stage({"npc_id": pk or _slugify(cand_name), "name": cand_name}, 2, "commitment")
                    staged_any = True
            if not staged_any:
                tgt_e = str(rc.get("target_entity") or "").strip()
                src_e = str(rc.get("source_entity") or "").strip()
                cand_e = tgt_e if (tgt_e and tgt_e.lower() != "player") else src_e
                if cand_e and cand_e.lower() not in player_names:
                    disp = cand_e.replace("_", " ").title() if "_" in cand_e else cand_e
                    tier2_aliases.update({disp.lower(), _slugify(disp), cand_e.lower()})
                    _stage({"npc_id": cand_e.lower(), "name": disp}, 2, "commitment")

        pending_appts = db.get_phone_appointments(sid, status="pending") or []
        arrived_appts = db.get_phone_appointments(sid, status="arrived") or []
        for appt in pending_appts + arrived_appts:
            if not isinstance(appt, Mapping):
                continue
            status_val = str(appt.get("status") or "").strip().lower()
            if status_val != "arrived":
                a_start, a_end = _compute_appt_abs_window(appt)
                if not ((a_start - 15) <= abs_now <= a_end):
                    continue
            a_nid = str(appt.get("target_node_id") or "").strip()
            a_loc = str(appt.get("rendezvous_location") or "").strip()
            if not _location_targets_node(a_nid, a_loc, eff_node_id, eff_loc, nodes_by_id, loc_cache):
                continue
            a_name = str(appt.get("npc_name") or "").strip()
            a_id = str(appt.get("npc_id") or "").strip()
            if a_name or a_id:
                disp = a_name or a_id.replace("_", " ").title()
                tier2_aliases.update({disp.lower(), _slugify(disp), a_id.lower()})
                _stage({"npc_id": a_id or _slugify(disp), "name": disp}, 2, "commitment")

    # ------------------------------------------------------------------
    # Tier 3: Active Quest / Bounty / Story Waypoint Pins
    # ------------------------------------------------------------------
    tier3_crisis_aliases: set[str] = set()
    active_wps = (db.get_all_session_active_waypoints(sid) or []) if sid > 0 else []
    story_quest = db.get_active_story_quest(sid) if sid > 0 else None
    candidate_wps: list[dict[str, Any]] = [dict(wp) for wp in active_wps if isinstance(wp, Mapping)]
    if isinstance(story_quest, Mapping):
        sq_loc = str(story_quest.get("target_location") or story_quest.get("location") or "").strip()
        sq_node = str(story_quest.get("target_node_id") or "").strip()
        sub_objs = story_quest.get("sub_objectives") or []
        has_active_sub = False
        for so in sub_objs:
            if isinstance(so, Mapping) and not so.get("completed"):
                has_active_sub = True
                if so.get("target_npc"):
                    so_wp = dict(so)
                    so_wp.setdefault("target_location", sq_loc)
                    so_wp.setdefault("target_node_id", sq_node)
                    so_wp.setdefault("stage_label", so.get("text") or so.get("stage_label") or "")
                    candidate_wps.append(so_wp)
        if not has_active_sub and story_quest.get("target_npc"):
            sq_wp = dict(story_quest)
            sq_wp.setdefault("stage_label", story_quest.get("title") or story_quest.get("objective") or "")
            candidate_wps.append(sq_wp)

    for wp in candidate_wps:
        t_npc = str(wp.get("target_npc") or "").strip()
        if not t_npc:
            continue
        wp_loc = str(wp.get("target_location") or wp.get("location") or "").strip()
        wp_node = str(wp.get("target_node_id") or "").strip()
        if not _location_targets_node(wp_node, wp_loc, eff_node_id, eff_loc, nodes_by_id, loc_cache):
            continue
        r_row, c_row = _find_linked(t_npc)
        wp_aliases = _npc_aliases(r_row) | _npc_aliases(c_row) | {t_npc.lower(), _slugify(t_npc)}
        if _is_blocked_casualty(wp_aliases):
            continue

        is_hostile = is_hostile_or_lair_waypoint(wp)
        wp_blob = f"{wp.get('stage_label', '')} {wp.get('title', '')} {wp.get('objective', '')} {wp.get('notes', '')}".lower()
        is_crisis = bool(wp.get("is_crisis")) or any(k in wp_blob for k in _CRISIS_KEYWORDS)
        follow_sched = bool(wp.get("follow_npc_schedule"))
        if is_hostile or is_crisis or not follow_sched:
            if is_crisis:
                tier3_crisis_aliases.update(wp_aliases)
            _stage({"name": t_npc, "npc_id": (c_row or r_row or {}).get("npc_id") or _slugify(t_npc)}, 3, "quest_pin")
            continue

        sched_info = get_waypoint_npc_schedule_info(
            sid,
            wp,
            current_minute=safe_min,
            session=session_dict,
            session_time=(safe_day, safe_min, eff_turn),
            contacts_by_name=contacts_by_name,
        )
        if not sched_info.get("is_off_duty"):
            _stage({"name": t_npc, "npc_id": (c_row or r_row or {}).get("npc_id") or _slugify(t_npc)}, 3, "quest_pin")

    # ------------------------------------------------------------------
    # Precompute Tier 4 & Tier 5 Unified Roster/Contact State
    # ------------------------------------------------------------------
    prop_at_node = get_player_owned_or_starter_property_for_node(sid, eff_node_id, session=session_dict) if (sid > 0 and eff_node_id) else None
    prim_prop = db.get_primary_property(sid) if (sid > 0 and eff_node_id and eff_node_id != SHARED_ABSTRACT_RESIDENCE_NODE) else None
    combined_spare_keys: dict[str, Any] = {}
    for prop in (prim_prop, prop_at_node):
        if isinstance(prop, Mapping) and isinstance(prop.get("spare_keys"), Mapping):
            combined_spare_keys.update(prop["spare_keys"])
    node_state_map = parse_node_state(target_node) if isinstance(target_node, dict) else {}
    if isinstance(node_state_map.get("spare_keys"), Mapping):
        combined_spare_keys.update(node_state_map["spare_keys"])

    household_cache: dict[int, dict[str, Any] | None] = {}
    anchor_cache: dict[str, tuple[dict[str, str] | None, tuple[bool, str]]] = {}

    def _get_anchor_eval(eff_rec: Mapping[str, Any], *, force_anchor: bool = False) -> tuple[dict[str, str] | None, tuple[bool, str]]:
        c_key = _slugify(eff_rec.get("npc_id") or eff_rec.get("npc_key") or eff_rec.get("name")) or str(id(eff_rec))
        if c_key in anchor_cache:
            return anchor_cache[c_key]
        probe = dict(eff_rec)
        if force_anchor and str(probe.get("origin") or "").strip().lower() != "legacy_adapter":
            probe["use_anchor_schedule"] = True
        a_map = resolve_anchor_schedule_nodes(probe, current_day=safe_day, scen_key=eff_scen, session_id=None, current_minute=safe_min)
        shift_tup = is_npc_on_active_shift(probe, safe_min, current_day=safe_day, scen_key=eff_scen, session_id=None)
        anchor_cache[c_key] = (a_map, shift_tup)
        return a_map, shift_tup

    # Deduplicated person records across non-legacy world_roster + contacts
    unified_records: list[tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any], set[str]]] = []
    seen_unified_keys: set[str] = set()
    for r in roster_rows:
        if not isinstance(r, dict):
            continue
        aliases = _npc_aliases(r)
        if not aliases or (aliases & seen_unified_keys):
            continue
        seen_unified_keys.update(aliases)
        _, linked_c = _find_linked(r.get("npc_id") or r.get("name"))
        if linked_c:
            seen_unified_keys.update(_npc_aliases(linked_c))
        unified_records.append((r, linked_c, _merge_npc_records(r, linked_c), aliases))

    for c in contacts:
        if not isinstance(c, dict):
            continue
        aliases = _npc_aliases(c)
        if not aliases or (aliases & seen_unified_keys):
            continue
        seen_unified_keys.update(aliases)
        unified_records.append((None, c, _merge_npc_records(c, None), aliases))

    # ------------------------------------------------------------------
    # Tier 4: Resident Doorbell Etiquette (never on zone_residential_abstract)
    # ------------------------------------------------------------------
    doorbell_events: list[dict[str, Any]] = []
    story_wps_for_legacy = [wp for wp in active_wps if wp.get("target_node_id")] if active_wps else []
    active_events_cache = (db.get_world_events(sid, entity_type="macro_event") or []) if sid > 0 else []

    if eff_node_id and eff_node_id != SHARED_ABSTRACT_RESIDENCE_NODE:
        override_pin_aliases = tier2_aliases | tier3_crisis_aliases
        for r_row, c_row, merged_npc, aliases in unified_records:
            if _is_blocked_casualty(aliases):
                continue
            npc_home = str(merged_npc.get("home_node_id") or _parse_dict(merged_npc.get("basic_info")).get("home_node_id") or "").strip()
            if not _residence_matches_node(npc_home, eff_node_id, nodes_by_id):
                continue

            if r_row is not None and str(r_row.get("origin") or "").lower() != "legacy_adapter":
                a_map, _ = _get_anchor_eval(merged_npc, force_anchor=True)
                sched_nid = str((a_map or {}).get(block_key) or "").strip()
            else:
                sched_nid = str(
                    get_npc_scheduled_node_id(
                        merged_npc,
                        current_minute=safe_min,
                        scen_key=eff_scen,
                        current_day=safe_day,
                        session_id=sid or None,
                        story_waypoints=story_wps_for_legacy,
                        active_events=active_events_cache,
                    ) or ""
                ).strip()

            dbell = check_doorbell_etiquette(
                sid,
                merged_npc,
                eff_node_id,
                current_day=safe_day,
                current_minute=safe_min,
                scen_key=eff_scen,
                session=session_dict,
                has_active_override_pin=bool(aliases & override_pin_aliases),
                nodes_by_id=nodes_by_id,
                contact_row=c_row,
                spare_keys=combined_spare_keys,
                scheduled_node_id=sched_nid,
                household_cache=household_cache,
                player_household_id=player_hh_id,
                player_last_name=player_last_name,
            )
            if not dbell["applicable"]:
                continue
            doorbell_events.append(dbell)
            if dbell["should_block_sleep"]:
                blocked_sleeping_keys.update(aliases)
            elif dbell["allowed"]:
                _stage(merged_npc, 4, "doorbell_answered", extra={"doorbell_status": dbell["doorbell_status"]})

    # ------------------------------------------------------------------
    # Tier 5: Active Anchor Schedules (`world_roster`) + Legacy Pools
    # ------------------------------------------------------------------
    display_loc = _format_node_display_label(eff_node_id, eff_loc, nodes_by_id)
    day_kind = "weekend" if is_weekend(safe_day) else "weekday"

    for r_row, c_row, merged_npc, aliases in unified_records:
        if r_row is None:
            continue
        origin_val = str(r_row.get("origin") or "").strip().lower()
        status_val = str(r_row.get("staff_status") or "active").strip().lower()
        if origin_val == "legacy_adapter" or status_val != "active":
            continue
        if _is_blocked_casualty(aliases) or (aliases & blocked_sleeping_keys) or _is_already_staged(aliases):
            continue

        a_map, (on_shift, work_nid) = _get_anchor_eval(merged_npc, force_anchor=True)
        sched_nid = str((a_map or {}).get(block_key) or "").strip()
        work_match = bool(eff_node_id and on_shift and work_nid == eff_node_id)
        sched_match = bool(
            eff_node_id
            and eff_node_id != SHARED_ABSTRACT_RESIDENCE_NODE
            and sched_nid == eff_node_id
        )
        if not (work_match or sched_match):
            continue

        staged = _stage(merged_npc, 5, "schedule")
        if staged is not None and record_discovery and sid > 0 and eff_node_id and eff_node_id != SHARED_ABSTRACT_RESIDENCE_NODE and display_loc:
            existing_slots = (r_row.get("discovered_slots") or {}).get(day_kind, {})
            if existing_slots.get(block_key) != display_loc:
                npc_key = str(r_row.get("npc_key") or r_row.get("npc_id") or r_row.get("name") or "").strip()
                if npc_key:
                    db.record_discovered_schedule_slot(
                        sid, npc_key, day_kind, block_key, display_loc, turn_number=eff_turn
                    )

    # Track 5B: Legacy schedule pools (Ruling 6 — never via include_legacy_rosters=True)
    legacy_pool: list[dict[str, Any]] = []
    for _, c_row, merged_npc, aliases in unified_records:
        if any(ak in roster_by_key for ak in aliases):
            continue
        legacy_pool.append(merged_npc)

    if sid > 0:
        if is_high_school_setting(eff_scen):
            for sr in (db.get_school_roster(sid) or []):
                if isinstance(sr, dict):
                    legacy_pool.append(sr)
        if scenario_data.is_anomalous_incursions_scenario(eff_scen):
            for ar in (db.get_anomalous_agent_roster(sid) or []):
                if isinstance(ar, dict):
                    legacy_pool.append(ar)
        extra_raw = _parse_dict(session_dict.get("extra_json"))
        for fv in (extra_raw.get("folklore_villager_roster") or session_dict.get("folklore_villager_roster") or []):
            if isinstance(fv, dict):
                legacy_pool.append(fv)

    for leg_npc in legacy_pool:
        aliases = _npc_aliases(leg_npc)
        if not aliases or _is_deceased_or_arrested(leg_npc):
            continue
        if _is_blocked_casualty(aliases) or (aliases & blocked_sleeping_keys) or _is_already_staged(aliases):
            continue
        if any(ak in roster_by_key for ak in aliases):
            continue
        if not eff_node_id or eff_node_id == SHARED_ABSTRACT_RESIDENCE_NODE:
            continue

        sched_nid = str(
            get_npc_scheduled_node_id(
                leg_npc,
                current_minute=safe_min,
                scen_key=eff_scen,
                current_day=safe_day,
                session_id=sid or None,
                story_waypoints=story_wps_for_legacy,
                active_events=active_events_cache,
            ) or ""
        ).strip()
        if not sched_nid or sched_nid != eff_node_id or sched_nid == SHARED_ABSTRACT_RESIDENCE_NODE:
            continue
        # Only allow private residence entry via Tier 4 doorbell etiquette, never bare legacy fallback
        sched_node = nodes_by_id.get(sched_nid)
        if _is_private_home_or_wilderness(sched_node, sched_nid, "", prop_at_node):
            continue
        _stage(leg_npc, 5, "schedule")

    # ------------------------------------------------------------------
    # Tier 6: Unnamed Crowd Flavor Fallback (ZERO DB writes)
    # ------------------------------------------------------------------
    present_list = [staged_by_key[k] for k in staged_order]
    crowd_flavor = ""
    if not present_list and (eff_node_id or eff_loc):
        if not _is_private_home_or_wilderness(target_node, eff_node_id, eff_loc, prop_at_node):
            crowd_flavor = format_venue_crowd_flavor(eff_node_id, eff_loc, eff_scen, safe_min)

    return {
        "node_id": eff_node_id,
        "location": eff_loc,
        "present_npcs": present_list,
        "allowed_names": [n["name"] for n in present_list],
        "doorbell_events": doorbell_events,
        "crowd_flavor": crowd_flavor,
        "time_block": block_key,
    }
