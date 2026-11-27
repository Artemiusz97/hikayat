"""
mechanics/world/presence_graph.py — In-Memory Node Graph & Legacy Roster Adapter
===============================================================================
Cohesive graph traversal, residence/facility geometry, name-matching normalization,
and zero-write legacy roster adaptation for the 6-tier presence resolver.
"""
from __future__ import annotations

import json
import re
from typing import Any, Mapping

from db.world import _LEGACY_NODE_ID_ALIASES
from mechanics.world.locations.residence_fog import SHARED_ABSTRACT_RESIDENCE_NODE
from mechanics.world.venue_templates import (
    HOSPITALITY_OUTPOST_OVERRIDE_KEYWORDS,
    PRIVATE_RESIDENCE_KEYWORDS,
    STAFFED_VENUE_OVERRIDE_KEYWORDS,
    WILDERNESS_DUNGEON_KEYWORDS,
    parse_node_state,
)
from mechanics.world.waypoints.matching import check_location_matches_waypoint

_STUDENT_GRADE_TOKENS: frozenset[str] = frozenset(
    {"freshman", "sophomore", "junior", "senior", "student", "peer"}
)
_PUBLIC_NODE_CATEGORIES: frozenset[str] = frozenset(
    {"commercial", "campus", "academic", "civic", "social", "market", "wilderness"}
)


def slugify_key(raw: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(raw or "").strip().lower()).strip("_")


def parse_int(raw: Any) -> int | None:
    if raw is None or raw == "" or isinstance(raw, bool):
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def parse_dict(raw: Any) -> dict[str, Any]:
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


def is_deceased_or_arrested(rec: Mapping[str, Any] | None) -> bool:
    if not isinstance(rec, Mapping):
        return False
    basic = parse_dict(rec.get("basic_info"))
    status = str(rec.get("staff_status") or basic.get("staff_status") or "").strip().lower()
    if status in ("dead", "arrested", "deceased"):
        return True
    if bool(rec.get("is_deceased") or basic.get("is_deceased") or basic.get("deceased")):
        return True
    if rec.get("alive") is False or basic.get("alive") is False:
        return True
    return str(basic.get("status") or "").strip().lower() in ("dead", "deceased", "arrested")


def extract_affinity(
    roster_row: Mapping[str, Any] | None,
    contact_row: Mapping[str, Any] | None,
) -> int:
    scores: list[int] = []
    for src in (roster_row, contact_row):
        if not isinstance(src, Mapping):
            continue
        basic = parse_dict(src.get("basic_info"))
        for cand in (
            src.get("affinity_score"),
            src.get("interaction_score"),
            src.get("relationship_score"),
            basic.get("affinity_score"),
            basic.get("interaction_score"),
            basic.get("relationship_score"),
        ):
            parsed = parse_int(cand)
            if parsed is not None:
                scores.append(parsed)
    return max(scores) if scores else 0


def npc_aliases(rec: Mapping[str, Any] | None) -> set[str]:
    if not isinstance(rec, Mapping):
        return set()
    basic = parse_dict(rec.get("basic_info"))
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
            slug = slugify_key(s)
            if slug:
                aliases.add(slug)
    return aliases


def merge_npc_records(
    primary: Mapping[str, Any] | None,
    secondary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    base_basic: dict[str, Any] = {}
    for src in (secondary, primary):
        if not isinstance(src, Mapping):
            continue
        src_basic = parse_dict(src.get("basic_info"))
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


def in_mem_ancestors(
    node_id: str,
    nodes_by_id: Mapping[str, dict[str, Any]],
) -> list[dict[str, Any]]:
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
    if (
        _LEGACY_NODE_ID_ALIASES.get(node_id.lower()) == ancestor_id
        or node_id == _LEGACY_NODE_ID_ALIASES.get(ancestor_id.lower())
    ):
        return True
    anc_target = _LEGACY_NODE_ID_ALIASES.get(ancestor_id.lower(), ancestor_id)
    return any(
        a.get("node_id") in (ancestor_id, anc_target)
        for a in in_mem_ancestors(node_id, nodes_by_id)
    )


def resolve_node_id_in_memory(
    location_str: str,
    nodes_by_id: Mapping[str, dict[str, Any]],
    prefer_facility: bool = True,
    cache: dict[tuple[str, bool], str] | None = None,
    preferred_realm_id: str = "",
) -> str:
    loc_clean = str(location_str or "").strip()
    if not loc_clean or not nodes_by_id:
        return ""
    eff_pref_realm = str(preferred_realm_id or "").strip()
    c_key = (f"{eff_pref_realm}::{loc_clean}" if eff_pref_realm else loc_clean, prefer_facility)
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
        all_nodes = list(nodes_by_id.values())
        if eff_pref_realm:
            from mechanics.world.locations.realms import get_node_realm_id_in_memory
            pref_pool = [n for n in all_nodes if get_node_realm_id_in_memory(str(n.get("node_id") or ""), nodes_by_id) == eff_pref_realm]
            other_pool = [n for n in all_nodes if get_node_realm_id_in_memory(str(n.get("node_id") or ""), nodes_by_id) != eff_pref_realm]
            nodes = pref_pool + other_pool
        else:
            nodes = all_nodes

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
                        rn
                        for rn in nodes
                        if rn.get("parent_id") == prim_node["node_id"]
                        and str(rn.get("name") or "").lower() == leaf_name
                    ),
                    None,
                )
                if child is None and leaf_name not in ("main area", "area", "main"):
                    child = next(
                        (
                            rn
                            for rn in nodes
                            if rn.get("parent_id") == prim_node["node_id"]
                            and (
                                leaf_name in str(rn.get("name") or "").lower()
                                or str(rn.get("name") or "").lower() in leaf_name
                            )
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


def location_targets_node(
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


def format_node_display_label(
    node_id: str,
    location_str: str,
    nodes_by_id: Mapping[str, dict[str, Any]],
) -> str:
    node = nodes_by_id.get(node_id)
    if isinstance(node, Mapping):
        chain: list[str] = []
        for anc in reversed(in_mem_ancestors(node_id, nodes_by_id)):
            nm = str(anc.get("name") or "").strip()
            if nm:
                chain.append(nm)
        self_name = str(node.get("name") or "").strip()
        if self_name:
            chain.append(self_name)
        if chain:
            return " ➔ ".join(chain)
    return str(location_str or node_id or "").strip()


def is_private_residence_node(
    node: Mapping[str, Any] | None,
    node_id: str,
) -> bool:
    """True when `node` itself represents a private residence (never commercial/public)."""
    nid = str(node_id or "").strip()
    if not nid or nid == SHARED_ABSTRACT_RESIDENCE_NODE:
        return False
    if nid.startswith(("fac_npc_res_", "sub_npc_res_")):
        return True
    if not isinstance(node, Mapping):
        return False
    priv = str(node.get("privacy_level") or "").strip().lower()
    if priv == "public":
        return False
    node_state = parse_node_state(dict(node))
    if bool(node_state.get("is_player_residence") or node_state.get("owner_npc_id") or node_state.get("owner_npc_name")):
        return True
    if priv == "private":
        return True
    cat = str(node.get("category") or "").strip().lower()
    if cat in _PUBLIC_NODE_CATEGORIES:
        return False
    name_low = str(node.get("name") or "").lower()
    has_hosp_or_staff = any(k in name_low for k in HOSPITALITY_OUTPOST_OVERRIDE_KEYWORDS) or any(
        k in name_low for k in STAFFED_VENUE_OVERRIDE_KEYWORDS
    )
    if has_hosp_or_staff:
        return False
    if cat == "residential":
        return True
    return any(kw in name_low for kw in PRIVATE_RESIDENCE_KEYWORDS)


def residence_matches_node(
    home_node_id: str,
    target_node_id: str,
    nodes_by_id: Mapping[str, dict[str, Any]],
) -> bool:
    """
    Matches `home_node_id` to `target_node_id` for Tier 4 doorbell etiquette.

    Matches when:
    1. Exact match (`home_nid == tgt_nid`).
    2. `tgt_nid` is a non-public sub-room inside the NPC's private `home_nid` facility.
    3. `tgt_nid` is a private residential `FACILITY` owning `home_nid` (NEVER public/commercial e.g. `loc_inn`).
    """
    home_nid = str(home_node_id or "").strip()
    tgt_nid = str(target_node_id or "").strip()
    if (
        not home_nid
        or not tgt_nid
        or home_nid == SHARED_ABSTRACT_RESIDENCE_NODE
        or tgt_nid == SHARED_ABSTRACT_RESIDENCE_NODE
    ):
        return False
    if home_nid == tgt_nid:
        return True

    tgt_node = nodes_by_id.get(tgt_nid)
    home_node = nodes_by_id.get(home_nid)
    tgt_priv = str((tgt_node or {}).get("privacy_level") or "").strip().lower()
    tgt_cat = str((tgt_node or {}).get("category") or "").strip().lower()

    if is_node_descendant_in_memory(tgt_nid, home_nid, nodes_by_id):
        if tgt_priv != "public" and tgt_cat not in ("commercial", "civic", "market"):
            return True
        return False

    if (
        isinstance(tgt_node, Mapping)
        and str(tgt_node.get("node_type") or "").upper() == "FACILITY"
        and isinstance(home_node, Mapping)
        and home_node.get("parent_id") == tgt_nid
    ):
        return is_private_residence_node(tgt_node, tgt_nid)
    return False


def is_private_home_or_wilderness(
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


def schedule_matches_node(
    sched_nid: str,
    eff_node_id: str,
    eff_loc: str,
    nodes_by_id: Mapping[str, dict[str, Any]],
    *,
    prop_at_node: Mapping[str, Any] | None = None,
    resident_home_ids: set[str] | frozenset[str] = frozenset(),
) -> bool:
    """
    Matches scheduled node against queried `eff_node_id`:
    - Exact match always qualifies (Tier 4 guards still block unauthorized residences separately).
    - If NPC is scheduled at a parent `FACILITY` (`loc_inn`), allow reaching them inside
      non-private descendant `ROOM`s (`loc_inn_taproom`) while excluding resident bedrooms/lofts.
    """
    if not sched_nid or not eff_node_id or eff_node_id == SHARED_ABSTRACT_RESIDENCE_NODE:
        return False
    if sched_nid == eff_node_id:
        return True
    sched_node = nodes_by_id.get(sched_nid)
    if not isinstance(sched_node, Mapping) or str(sched_node.get("node_type") or "").upper() != "FACILITY":
        return False
    if not is_node_descendant_in_memory(eff_node_id, sched_nid, nodes_by_id):
        return False
    if eff_node_id in resident_home_ids:
        return False
    eff_node = nodes_by_id.get(eff_node_id)
    if is_private_home_or_wilderness(eff_node, eff_node_id, eff_loc, prop_at_node):
        return False
    return True


def _resolve_field_node_id(
    raw_val: Any,
    nodes_by_id: Mapping[str, dict[str, Any]],
    loc_cache: dict[tuple[str, bool], str],
    *,
    prefer_facility: bool = False,
) -> str:
    text = str(raw_val or "").strip()
    if not text:
        return ""
    if text in nodes_by_id:
        return text
    if nodes_by_id:
        hit = resolve_node_id_in_memory(text, nodes_by_id, prefer_facility=prefer_facility, cache=loc_cache)
        if hit:
            return hit
        if not prefer_facility:
            hit_fac = resolve_node_id_in_memory(text, nodes_by_id, prefer_facility=True, cache=loc_cache)
            if hit_fac:
                return hit_fac
    return text


def adapt_legacy_entry_for_presence(
    session_id: int,
    entry: Mapping[str, Any],
    source_kind: str,
    nodes_by_id: Mapping[str, dict[str, Any]],
    loc_cache: dict[tuple[str, bool], str],
) -> dict[str, Any] | None:
    """
    Normalizes an unhydrated legacy entry (`school`, `agent`, or `folklore`) into a
    schedule-ready dict resolving display names against `nodes_by_id` without DB writes.
    """
    if not isinstance(entry, Mapping):
        return None
    name = str(entry.get("name") or "").strip()
    npc_id = slugify_key(entry.get("npc_id") or name)
    if not name or not npc_id:
        return None

    basic = parse_dict(entry.get("basic_info"))
    role = str(entry.get("role") or entry.get("agent_class") or basic.get("role") or "").strip()

    if source_kind == "school":
        grade_val = str(entry.get("grade") or basic.get("grade") or "").strip()
        grade_low = grade_val.lower()
        shift = "student" if any(tok in grade_low for tok in _STUDENT_GRADE_TOKENS) else "day"
        prim_fac = str(entry.get("primary_facility") or basic.get("primary_facility") or "").strip()
        sec_fac = str(entry.get("secondary_facility") or basic.get("secondary_facility") or "").strip()
        work_nid = _resolve_field_node_id(
            entry.get("workplace_node_id") or prim_fac, nodes_by_id, loc_cache
        )
        hang_nid = _resolve_field_node_id(
            entry.get("hangout_node_id") or sec_fac, nodes_by_id, loc_cache
        )
        home_nid = _resolve_field_node_id(
            entry.get("home_node_id") or entry.get("residence_node_id"), nodes_by_id, loc_cache
        )
        club = str(entry.get("club") or basic.get("club") or "").strip()
        clique = str(entry.get("clique") or basic.get("clique") or "").strip()
        merged_basic = {
            **basic,
            "role": role,
            "grade": grade_val,
            "club": club,
            "clique": clique,
            "primary_facility": prim_fac,
            "secondary_facility": sec_fac,
            "sibling_name": str(entry.get("sibling_name") or basic.get("sibling_name") or ""),
            "workplace_node_id": work_nid,
            "hangout_node_id": hang_nid,
            "home_node_id": home_nid,
            "shift_profile": shift,
        }
        out = dict(entry)
        out.update(
            {
                "session_id": int(session_id),
                "npc_id": npc_id,
                "name": name,
                "role": role,
                "grade": grade_val,
                "club": club,
                "clique": clique,
                "primary_facility": prim_fac,
                "secondary_facility": sec_fac,
                "workplace_node_id": work_nid,
                "hangout_node_id": hang_nid,
                "home_node_id": home_nid,
                "shift_profile": shift,
                "origin": "legacy_adapter",
                "staff_status": str(entry.get("staff_status") or "active").strip().lower(),
                "basic_info": merged_basic,
                "_db_hydrated": True,
                "_roster_premerged": True,
            }
        )
        return out

    if source_kind == "agent":
        shift = "student" if entry.get("is_student_agent") else "day"
        if str(entry.get("shift_profile") or "").strip():
            shift = str(entry["shift_profile"]).strip()
        prim_fac = str(entry.get("primary_facility") or basic.get("primary_facility") or "").strip()
        sec_fac = str(entry.get("secondary_facility") or basic.get("secondary_facility") or "").strip()
        work_nid = _resolve_field_node_id(
            entry.get("workplace_node_id") or entry.get("primary_node_id") or prim_fac,
            nodes_by_id,
            loc_cache,
        )
        hang_nid = _resolve_field_node_id(
            entry.get("hangout_node_id") or entry.get("secondary_node_id") or sec_fac,
            nodes_by_id,
            loc_cache,
        )
        home_nid = _resolve_field_node_id(
            entry.get("home_node_id") or entry.get("residence_node_id") or entry.get("residence_facility_id"),
            nodes_by_id,
            loc_cache,
        )
        merged_basic = {
            **basic,
            "role": role,
            "grade": str(entry.get("grade") or basic.get("grade") or ""),
            "club": str(entry.get("club") or basic.get("club") or ""),
            "clique": str(entry.get("clique") or basic.get("clique") or ""),
            "primary_facility": prim_fac,
            "secondary_facility": sec_fac,
            "is_special_agent": bool(entry.get("is_special_agent", True)),
            "is_student_agent": bool(entry.get("is_student_agent", False)),
            "anomalous_npc_tag": str(entry.get("anomalous_npc_tag") or basic.get("anomalous_npc_tag") or ""),
            "workplace_node_id": work_nid,
            "hangout_node_id": hang_nid,
            "home_node_id": home_nid,
            "shift_profile": shift,
        }
        out = dict(entry)
        out.update(
            {
                "session_id": int(session_id),
                "npc_id": npc_id,
                "name": name,
                "role": role,
                "workplace_node_id": work_nid,
                "hangout_node_id": hang_nid,
                "home_node_id": home_nid,
                "shift_profile": shift,
                "origin": "legacy_adapter",
                "staff_status": str(entry.get("staff_status") or "active").strip().lower(),
                "basic_info": merged_basic,
                "_db_hydrated": True,
                "_roster_premerged": True,
            }
        )
        return out

    # source_kind == "folklore"
    home_raw = str(entry.get("home_node_id") or entry.get("home_node") or basic.get("home_node") or "").strip()
    home_nid = _resolve_field_node_id(home_raw, nodes_by_id, loc_cache)
    work_nid = _resolve_field_node_id(entry.get("workplace_node_id") or home_nid, nodes_by_id, loc_cache)
    hang_nid = _resolve_field_node_id(entry.get("hangout_node_id") or entry.get("village_id"), nodes_by_id, loc_cache)
    sched_dict = entry.get("schedule") if isinstance(entry.get("schedule"), Mapping) else basic.get("schedule")
    merged_basic = {
        **basic,
        "role": role,
        "folklore_village": str(entry.get("folklore_village") or basic.get("folklore_village") or ""),
        "village_id": str(entry.get("village_id") or basic.get("village_id") or ""),
        "is_folklore_villager": True,
        "is_sovereign": bool(entry.get("is_sovereign", basic.get("is_sovereign", False))),
        "is_royal_heir": bool(entry.get("is_royal_heir", basic.get("is_royal_heir", False))),
        "merchant_type": str(entry.get("merchant_type") or basic.get("merchant_type") or ""),
        "home_node": home_raw or home_nid,
        "home_node_id": home_nid,
        "workplace_node_id": work_nid,
        "hangout_node_id": hang_nid,
    }
    if isinstance(sched_dict, Mapping) and sched_dict:
        merged_basic["schedule"] = dict(sched_dict)
    out = dict(entry)
    out.update(
        {
            "session_id": int(session_id),
            "npc_id": npc_id,
            "name": name,
            "role": role,
            "workplace_node_id": work_nid,
            "hangout_node_id": hang_nid,
            "home_node_id": home_nid,
            "shift_profile": str(entry.get("shift_profile") or "day").strip() or "day",
            "origin": "legacy_adapter",
            "staff_status": str(entry.get("staff_status") or "active").strip().lower(),
            "basic_info": merged_basic,
            "_db_hydrated": True,
            "_roster_premerged": True,
        }
    )
    if isinstance(sched_dict, Mapping) and sched_dict:
        out["schedule"] = dict(sched_dict)
    return out
