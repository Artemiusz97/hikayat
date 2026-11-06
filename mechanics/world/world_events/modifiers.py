from __future__ import annotations

import hashlib
import json
from typing import Any

from .constants import (
    AROUSAL_MULTIPLIER_MAX,
    AROUSAL_MULTIPLIER_MIN,
    DC_MODIFIER_MAX,
    DC_MODIFIER_MIN,
    DEFENSIVE_CHA_DC_PENALTY,
    IMPLICATED_NPC_FACTION_REP_DELTA,
    PRICE_MULTIPLIER_MAX,
    PRICE_MULTIPLIER_MIN,
)


def _parse_dict(val: Any) -> dict[str, Any]:
    if isinstance(val, dict):
        return val
    if isinstance(val, str) and val.strip():
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _extract_event_modifiers(ev: dict[str, Any]) -> dict[str, Any]:
    if ev.get("entity_type") == "minor_event":
        return {}
    mods = dict(_parse_dict(ev.get("modifiers") or ev.get("modifiers_json")))
    if "dc_modifiers_json" in ev and "dc_modifiers" not in mods:
        mods["dc_modifiers"] = _parse_dict(ev.get("dc_modifiers_json"))
    if "merchant_modifiers_json" in ev:
        m_mod = _parse_dict(ev.get("merchant_modifiers_json"))
        if "price_multiplier" in m_mod and "price_multiplier" not in mods:
            mods["price_multiplier"] = m_mod["price_multiplier"]
    if "social_modifiers_json" in ev:
        s_mod = _parse_dict(ev.get("social_modifiers_json"))
        if "arousal_multiplier" in s_mod and "arousal_multiplier" not in mods:
            mods["arousal_multiplier"] = s_mod["arousal_multiplier"]
    return mods


def _extract_macro_events(events_or_snapshot: Any) -> list[dict[str, Any]]:
    if not events_or_snapshot:
        return []
    if isinstance(events_or_snapshot, dict):
        items = events_or_snapshot.get("active_macro_events") or []
        return [
            e for e in items
            if isinstance(e, dict) and e.get("entity_type", "macro_event") != "minor_event"
        ]
    if isinstance(events_or_snapshot, list):
        return [
            e for e in events_or_snapshot
            if isinstance(e, dict) and e.get("entity_type", "macro_event") == "macro_event"
        ]
    return []


def _extract_rumors(events_or_snapshot: Any) -> list[dict[str, Any]]:
    if not events_or_snapshot:
        return []
    if isinstance(events_or_snapshot, dict):
        items = events_or_snapshot.get("active_rumors") or []
        return [e for e in items if isinstance(e, dict)]
    if isinstance(events_or_snapshot, list):
        return [
            e for e in events_or_snapshot
            if isinstance(e, dict) and e.get("entity_type") == "rumor"
        ]
    return []


def _node_matches(ev: dict[str, Any], target_node_id: str) -> bool:
    ev_node = str(ev.get("location_node_id") or "").strip().lower()
    if not ev_node or not target_node_id:
        return True
    tgt = str(target_node_id).strip().lower()
    return ev_node == tgt or ev_node in tgt or tgt in ev_node


def compute_event_dc_modifier(
    events_or_snapshot: Any,
    stat: str,
    location_node_id: str = "",
    node_id: str = "",
    is_stealth: bool = False,
    domain: str = "",
    **kwargs: Any,
) -> int:
    """Computes cumulative DC modifier from active macro events, strictly clamped to [-4, +4]."""
    stat_key = str(stat or "").upper().strip()
    if not stat_key or stat_key in ("NONE", "FREE", "ITEM"):
        return 0
    loc = location_node_id or node_id
    total = 0
    for ev in _extract_macro_events(events_or_snapshot):
        if ev.get("status") != "active":
            continue
        if not _node_matches(ev, loc):
            continue
        mods = _extract_event_modifiers(ev)
        dc_map = _parse_dict(mods.get("dc_modifiers"))
        if stat_key in dc_map:
            try:
                total += int(dc_map[stat_key])
            except (TypeError, ValueError):
                pass
        if (is_stealth or str(domain).lower() == "stealth") and stat_key == "AGI":
            try:
                total += int(mods.get("stealth_modifier") or 0)
            except (TypeError, ValueError):
                pass
    return max(DC_MODIFIER_MIN, min(DC_MODIFIER_MAX, total))


def compute_rumor_defensive_dc(
    events_or_snapshot: Any,
    target: Any = None,
    contact_id: int | None = None,
    npc_id: str | None = None,
    npc_name: str | None = None,
    **kwargs: Any,
) -> int:
    """Returns +2 CHA DC ([Defensive]) if the target NPC is implicated in an active unresolved rumor."""
    candidates: set[str] = set()
    if isinstance(target, (list, tuple, set)):
        for item in target:
            if item:
                candidates.add(str(item).strip().lower())
    elif target:
        candidates.add(str(target).strip().lower())
    for extra in (npc_id, npc_name):
        if extra:
            candidates.add(str(extra).strip().lower())

    for rm in _extract_rumors(events_or_snapshot):
        if rm.get("status") != "active":
            continue
        imp_cid = rm.get("implicated_contact_id")
        if contact_id is not None and imp_cid is not None:
            try:
                if int(contact_id) == int(imp_cid):
                    return DEFENSIVE_CHA_DC_PENALTY
            except (TypeError, ValueError):
                pass
        if candidates:
            meta = _parse_dict(rm.get("metadata") or rm.get("metadata_json"))
            imp_names = {
                str(meta.get("implicated_npc_name") or "").strip().lower(),
                str(meta.get("implicated_npc_id") or "").strip().lower(),
            } - {""}
            if candidates & imp_names:
                return DEFENSIVE_CHA_DC_PENALTY
    return 0


def compute_virtual_faction_rep_delta(
    events_or_snapshot: Any,
    faction_id: str,
    **kwargs: Any,
) -> int:
    """Computes temporary virtual faction reputation pressure (-10 while an unresolved rumor/crisis implicates the faction)."""
    fac = str(faction_id or "").strip().lower()
    if not fac:
        return 0
    delta = 0
    for rm in _extract_rumors(events_or_snapshot):
        if rm.get("status") == "active" and str(rm.get("faction_id") or "").strip().lower() == fac:
            delta += IMPLICATED_NPC_FACTION_REP_DELTA
            break
    if delta == 0:
        for ev in _extract_macro_events(events_or_snapshot):
            if ev.get("status") == "active" and ev.get("event_subtype") == "crisis":
                if str(ev.get("faction_id") or "").strip().lower() == fac:
                    delta += IMPLICATED_NPC_FACTION_REP_DELTA
                    break
    return max(-20, min(20, delta))


def compute_merchant_event_multiplier(
    events_or_snapshot: Any,
    location_node_id: str = "",
    node_id: str = "",
    **kwargs: Any,
) -> float:
    """Computes active macro event price multiplier, strictly clamped to [0.5, 2.0]."""
    loc = location_node_id or node_id
    mult = 1.0
    for ev in _extract_macro_events(events_or_snapshot):
        if ev.get("status") != "active":
            continue
        if not _node_matches(ev, loc):
            continue
        mods = _extract_event_modifiers(ev)
        try:
            ev_m = float(mods.get("price_multiplier") or 1.0)
            if ev_m > 0:
                mult *= ev_m
        except (TypeError, ValueError):
            continue
    return round(max(PRICE_MULTIPLIER_MIN, min(PRICE_MULTIPLIER_MAX, mult)), 3)


def compute_arousal_event_multiplier(
    events_or_snapshot: Any,
    location_node_id: str = "",
    node_id: str = "",
    **kwargs: Any,
) -> float:
    """Computes active world event/rumor arousal & boldness multiplier, strictly clamped to [0.5, 2.0]."""
    loc = location_node_id or node_id
    mult = 1.0
    for ev in _extract_macro_events(events_or_snapshot) + _extract_rumors(events_or_snapshot):
        if ev.get("status") != "active":
            continue
        if ev.get("entity_type") == "rumor" and not ev.get("is_discovered", True):
            continue
        if not _node_matches(ev, loc):
            continue
        mods = _extract_event_modifiers(ev)
        try:
            ev_m = float(mods.get("arousal_multiplier") or 1.0)
            if ev_m > 0:
                mult *= ev_m
        except (TypeError, ValueError):
            continue
    return round(max(AROUSAL_MULTIPLIER_MIN, min(AROUSAL_MULTIPLIER_MAX, mult)), 3)


def is_node_locked_by_event(
    events_or_snapshot: Any,
    node_id: str,
    **kwargs: Any,
) -> dict[str, Any] | None:
    """Checks if a spatial facility/node is currently soft-locked by an active crisis/quarantine event."""
    tgt = str(node_id or "").strip().lower()
    if not tgt:
        return None
    for ev in _extract_macro_events(events_or_snapshot):
        if ev.get("status") != "active":
            continue
        mods = _extract_event_modifiers(ev)
        locked_nodes = [str(n).strip().lower() for n in (mods.get("lockdown_nodes") or []) if n]
        ev_node = str(ev.get("location_node_id") or "").strip().lower()
        is_direct_lock = bool(mods.get("is_locked")) and bool(ev_node) and (ev_node == tgt or tgt in ev_node)
        if tgt in locked_nodes or is_direct_lock:
            return {
                "is_locked": True,
                "event_key": str(ev.get("event_key") or ""),
                "title": str(ev.get("title") or "Event Lockdown"),
                "reason": str(ev.get("description") or ev.get("title") or "Quarantined by active world event"),
            }
    return None


_ESSENTIAL_STAFF_ROLES = (
    "faculty", "teacher", "principal", "dean", "headmaster", "headmistress",
    "nurse", "doctor", "physician", "counselor",
    "staff", "merchant", "shopkeeper", "vendor", "clerk", "cashier", "innkeeper", "barkeep",
    "guard", "janitor", "custodian", "librarian", "coach", "officer", "police",
)


def _is_essential_staff_role(npc: Any) -> bool:
    if not isinstance(npc, dict):
        return False
    if npc.get("is_essential_staff") or npc.get("is_merchant") or npc.get("is_faculty") or npc.get("is_staff"):
        return True
    basic = npc.get("basic_info") if isinstance(npc.get("basic_info"), dict) else {}
    grade_str = f"{npc.get('grade') or ''} {basic.get('grade') or ''}".lower()
    if any(g in grade_str for g in ("freshman", "sophomore", "junior", "senior", "student", "peer")):
        return False
    role = f"{npc.get('role') or ''} {npc.get('occupation') or ''} {grade_str}".lower()
    role += f" {basic.get('role') or ''} {basic.get('occupation') or ''}".lower()
    if "basketball" in role and "guard" in role:
        role = role.replace("guard", "")
    return any(kw in role for kw in _ESSENTIAL_STAFF_ROLES)


def _is_npc_implicated_in_event(npc: Any, ev: dict[str, Any]) -> bool:
    if not isinstance(npc, dict) or not isinstance(ev, dict):
        return False
    npc_name = str(npc.get("name") or "").strip().lower()
    npc_id = str(npc.get("npc_id") or "").strip().lower()
    npc_pk = npc.get("id") if npc.get("id") is not None else npc.get("contact_id")
    ev_imp_cid = ev.get("implicated_contact_id")
    if ev_imp_cid is not None and npc_pk is not None:
        try:
            if int(ev_imp_cid) == int(npc_pk):
                return True
        except (TypeError, ValueError):
            pass
    mods = _extract_event_modifiers(ev)
    meta = _parse_dict(ev.get("metadata") if ev.get("metadata") is not None else ev.get("metadata_json"))
    for container in (ev, mods, meta):
        for key in ("actor_key", "implicated_npc_name"):
            cand = str(container.get(key) or "").strip().lower()
            if cand and cand in (npc_name, npc_id):
                return True
        for list_key in ("target_npcs", "implicated_actors", "implicated_npcs"):
            raw_list = container.get(list_key)
            if isinstance(raw_list, (list, tuple)):
                for item in raw_list:
                    cand = str(item).strip().lower()
                    if cand and cand in (npc_name, npc_id):
                        return True
    return False


def resolve_npc_stationing_with_events(
    events_or_snapshot: Any,
    npc: Any,
    scheduled_node_id: str = "",
    date_node_id: str = "",
    story_node_id: str = "",
    base_node_id: str = "",
    **kwargs: Any,
) -> str:
    """Enforces stationing priority: Story Quest > Active Date > Event Crowd > Normal Schedule > Base."""
    if story_node_id:
        return str(story_node_id)
    if date_node_id:
        return str(date_node_id)
    for ev in _extract_macro_events(events_or_snapshot):
        if ev.get("status") != "active":
            continue
        ev_node = str(ev.get("location_node_id") or "").strip()
        if not ev_node:
            continue
        mods = _extract_event_modifiers(ev)
        if ev.get("event_subtype") == "festival" or str(mods.get("crowd_density") or "").lower() == "high":
            if not isinstance(npc, dict):
                return ev_node
            implicated = _is_npc_implicated_in_event(npc, ev)
            if implicated:
                return ev_node
            if _is_essential_staff_role(npc):
                continue
            pull_pct = int(mods.get("crowd_pull_pct") if mods.get("crowd_pull_pct") is not None else 60)
            if pull_pct >= 100:
                return ev_node
            if pull_pct <= 0:
                continue
            npc_ident = str(npc.get("npc_id") or npc.get("name") or "") if isinstance(npc, dict) else str(npc or "")
            seed_str = f"{ev.get('event_key') or ev_node}:{npc_ident}".lower()
            hash_bucket = int(hashlib.sha256(seed_str.encode("utf-8")).hexdigest()[:8], 16) % 100
            if hash_bucket < pull_pct:
                return ev_node
    if scheduled_node_id:
        return str(scheduled_node_id)
    return str(base_node_id or "")
