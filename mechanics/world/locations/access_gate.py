"""
mechanics/world/locations/access_gate.py
========================================
Core access control, curfew enforcement, threshold barriers, private residence intercoms,
and rolling room memory (scene residue) for Hikayat's Relational Spatial Graph.
"""
from __future__ import annotations
import json
import logging
import re
from typing import Dict, Any, List, Optional, Tuple

import db

log = logging.getLogger("hikayat.world.access_gate")


class Phase2Choice(str):
    """A choice string subclass that also provides dictionary-like properties for choices_cleaner."""
    def __new__(cls, label: str, stat: str = "NONE", requirement: int = 0, mp_cost: int = 0, **kwargs):
        val = super().__new__(cls, str(label).strip())
        val.label = str(label).strip()
        val.stat = stat
        val.requirement = requirement
        val.mp_cost = mp_cost
        val.is_phase2_choice = True
        for k, v in kwargs.items():
            setattr(val, k, v)
        return val

    def get(self, key, default=None):
        if key in ("label", "text", "action"): return self.label
        if key == "stat": return getattr(self, "stat", default)
        if key == "requirement": return getattr(self, "requirement", default)
        if key == "mp_cost": return getattr(self, "mp_cost", default)
        if key == "is_phase2_choice": return True
        return getattr(self, key, default)

    def __getitem__(self, key):
        if key in ("label", "text", "action"): return self.label
        if hasattr(self, key): return getattr(self, key)
        return super().__getitem__(key)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "stat": self.stat,
            "requirement": self.requirement,
            "mp_cost": self.mp_cost,
            "is_phase2_choice": True
        }


def is_curfew_active(
    curfew_start_min: int | None,
    curfew_end_min: int | None,
    current_minute: int
) -> bool:
    """
    Returns True if curfew hours are currently active.
    Handles overnight wrap-around (e.g. 1320..360, where 22:00 -> 06:00 crosses midnight).
    """
    if curfew_start_min is None or curfew_end_min is None:
        return False
    safe_min = int(current_minute or 0) % 1440
    start = int(curfew_start_min) % 1440
    end = int(curfew_end_min) % 1440

    if start == end:
        return False
    if start > end:
        # Overnight window, e.g. 22:00 (1320) to 06:00 (360)
        return safe_min >= start or safe_min < end
    else:
        # Same-day window, e.g. 12:00 (720) to 14:00 (840)
        return start <= safe_min < end


def format_minute_to_hhmm(minute: int | None) -> str:
    """Formats an absolute or modulo minute into HH:MM string."""
    if minute is None:
        return "00:00"
    m = int(minute) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def get_node_effective_access_info(
    session_id: int,
    node_id: str,
    current_day: int = 1,
    current_minute: int = 480,
    scen_key: str = ""
) -> dict[str, Any]:
    """
    Computes effective access status, curfew status, dynamic world-schedule locks,
    unlock persistence, and scene residue for a node, taking into account parent facility inheritance.
    """
    if not session_id or not node_id:
        return {
            "access_tier": "open",
            "is_unlocked": True,
            "curfew_active": False,
            "curfew_label": "",
            "status_badge": "Open",
            "scene_residue": "",
            "scene_residue_log": [],
            "schedule_locked": False,
            "is_trespassing": False,
        }

    node = db.get_world_node(session_id, node_id)
    if not node:
        return {
            "access_tier": "open",
            "is_unlocked": True,
            "curfew_active": False,
            "curfew_label": "",
            "status_badge": "Open",
            "scene_residue": "",
            "scene_residue_log": [],
            "schedule_locked": False,
            "is_trespassing": False,
        }

    if not scen_key:
        try:
            sess_row = db.get_session(session_id)
            scen_key = (sess_row or {}).get("scenario") or "high_school_drama"
        except Exception:
            scen_key = "high_school_drama"

    fac_node = None
    if node.get("parent_id") and node.get("node_type") == "ROOM":
        fac_node = db.get_world_node(session_id, node["parent_id"])

    # Effective access tier
    tier = str(node.get("access_tier") or "open").lower()
    if fac_node and tier == "open":
        fac_tier = str(fac_node.get("access_tier") or "open").lower()
        if fac_tier in ("restricted", "private"):
            tier = fac_tier

    # State JSON check for unlocks and residue
    state = db.get_world_node_state(session_id, node_id)
    fac_state = db.get_world_node_state(session_id, fac_node["node_id"]) if fac_node else {}

    is_unlocked = bool(
        state.get("unlocked_permanent")
        or (state.get("unlocked_until_day") or 0) >= current_day
        or fac_state.get("unlocked_permanent")
        or (fac_state.get("unlocked_until_day") or 0) >= current_day
    )

    # Curfew evaluation (static + dynamic world schedule)
    c_start = node.get("curfew_start_min")
    c_end = node.get("curfew_end_min")
    if c_start is None and fac_node:
        c_start = fac_node.get("curfew_start_min")
        c_end = fac_node.get("curfew_end_min")

    curfew_active = is_curfew_active(c_start, c_end, current_minute)
    curfew_label = f"{format_minute_to_hhmm(c_start)}–{format_minute_to_hhmm(c_end)}" if (c_start is not None and c_end is not None) else ""

    from mechanics.world.world_schedule import evaluate_world_schedule_node_access
    sched_access = evaluate_world_schedule_node_access(
        node, fac_node, scen_key=scen_key, current_day=current_day, current_minute=current_minute
    )

    schedule_locked = bool(sched_access.get("schedule_locked"))
    is_trespassing = bool(sched_access.get("is_trespassing"))
    sched_reason_code = str(sched_access.get("reason_code") or "")
    sched_reason_label = str(sched_access.get("reason_label") or "")

    if sched_access.get("force_open"):
        tier = "open"
        curfew_active = False
        curfew_label = ""
        schedule_locked = False
        is_trespassing = False
    elif schedule_locked:
        if is_trespassing or sched_reason_code in ("curfew", "commercial_closed", "weekend_closed"):
            curfew_active = True
            if sched_access.get("curfew_label"):
                curfew_label = sched_access["curfew_label"]
        else:
            if tier == "open":
                tier = "restricted"
            if sched_access.get("curfew_label") and not curfew_label:
                curfew_label = sched_access["curfew_label"]

    # Anomalous Incursions Tiered HQ Access Gate evaluation
    anom_hq = evaluate_anomalous_hq_access(session_id, node, fac_node, scen_key=scen_key)
    if anom_hq.get("force_open"):
        tier = "open"
        is_unlocked = True
    elif anom_hq.get("force_restricted"):
        tier = "restricted"
        if not sched_reason_label and anom_hq.get("reason_label"):
            sched_reason_label = anom_hq["reason_label"]
            sched_reason_code = "faction_hq_restricted"

    # Status Badge
    if is_unlocked and (tier in ("restricted", "private") or schedule_locked):
        status_badge = "Unlocked"
    elif sched_access.get("badge_override") and sched_reason_code == "theme_park_anomalous_shift":
        status_badge = sched_access["badge_override"]
    elif schedule_locked and sched_access.get("badge_override") and sched_reason_code in ("commercial_closed", "weekend_closed", "restricted"):
        status_badge = sched_access["badge_override"]
    elif curfew_active:
        status_badge = f"Curfew ({curfew_label})" if curfew_label else "Curfew"
    elif tier == "restricted":
        status_badge = "Restricted"
    elif tier == "private":
        status_badge = "Private"
    else:
        status_badge = "Open"

    residue = state.get("scene_residue") or fac_state.get("scene_residue") or ""
    residue_log = state.get("scene_residue_log") or fac_state.get("scene_residue_log") or []

    return {
        "access_tier": tier,
        "is_unlocked": is_unlocked,
        "curfew_active": curfew_active,
        "curfew_label": curfew_label,
        "status_badge": status_badge,
        "scene_residue": residue,
        "scene_residue_log": residue_log,
        "schedule_locked": schedule_locked,
        "is_trespassing": is_trespassing,
        "schedule_reason_code": sched_reason_code,
        "schedule_reason_label": sched_reason_label,
    }


def record_node_unlock(
    session_id: int,
    node_id: str,
    unlock_type: str = "day",
    current_day: int = 1,
    reason: str = ""
) -> bool:
    """
    Persists an unlock event onto the node and its parent facility state_json.
    unlock_type: 'permanent' (persists session-long) or 'day' (resets next day).
    """
    if not session_id or not node_id:
        return False
    node = db.get_world_node(session_id, node_id)
    if not node:
        return False

    updates: dict[str, Any] = {"last_unlock_reason": reason}
    if unlock_type == "permanent":
        updates["unlocked_permanent"] = True
    else:
        updates["unlocked_until_day"] = current_day

    db.update_world_node_state(session_id, node_id, updates)
    parent_id = str(node.get("parent_id") or "")
    multi_wing_parents = (
        "loc_agency_hq", "loc_private_hq_1", "loc_private_hq_2",
        "loc_general_hospital", "loc_theme_park", "loc_eastern_temple", "loc_botanical_zoo",
        "loc_cult_sanctum_hq", "loc_clandestine_syndicate_hq",
    )
    if parent_id and node.get("node_type") == "ROOM" and not parent_id.startswith("bld_school_") and parent_id not in multi_wing_parents:
        db.update_world_node_state(session_id, parent_id, updates)
    return True


def has_npc_authority_for_node(npc: dict, node: dict, parent_node: dict | None = None) -> bool:
    """
    Determines if an NPC has authorized credentials/role for entering a restricted or curfew node.
    """
    if not isinstance(npc, dict) or not isinstance(node, dict):
        return False

    name = str(npc.get("name") or "").lower()
    role = str(npc.get("role") or (npc.get("basic_info") or {}).get("role") or "").lower()
    club = str(npc.get("club") or (npc.get("basic_info") or {}).get("club") or "").lower()

    n_id = str(node.get("node_id") or "").lower()
    n_name = str(node.get("name") or "").lower()
    p_id = str((parent_node or {}).get("node_id") or "").lower()
    p_name = str((parent_node or {}).get("name") or "").lower()
    full_target = f"{n_id} {n_name} {p_id} {p_name}"

    # Faculty & Staff have universal academic authority
    if any(k in role for k in ("teacher", "faculty", "staff", "nurse", "counselor", "principal", "guard", "security")):
        return True

    # Student Council authority
    if any(k in club or k in role for k in ("student council", "council", "president", "treasurer", "vice president")):
        if any(k in full_target for k in ("council", "homeroom", "hallway", "commons", "library")):
            return True

    # Club authority for matching facility
    if "swim" in club and "pool" in full_target:
        return True
    if any(k in club for k in ("kendo", "martial", "judo", "karate")) and "dojo" in full_target:
        return True
    if any(k in club for k in ("gym", "basketball", "volleyball", "athletics", "sports")) and ("gym" in full_target or "sports_field" in full_target or "track" in full_target):
        return True
    if any(k in club for k in ("drama", "theater", "theatre", "acting")) and "auditorium" in full_target:
        return True
    if any(k in club for k in ("art", "drawing", "sculpture")) and "fine_arts" in full_target:
        return True
    if any(k in club for k in ("music", "band", "orchestra")) and ("music" in full_target or "piano" in full_target):
        return True
    if any(k in club for k in ("science", "chem", "biology")) and "science_lab" in full_target:
        return True
    if any(k in club for k in ("broadcast", "newspaper", "media")) and "broadcasting" in full_target:
        return True
    if any(k in club for k in ("garden", "botany")) and "greenhouse" in full_target:
        return True
    if any(k in club for k in ("occult", "paranormal", "tarot")) and "old_storage" in full_target:
        return True
    if any(k in club for k in ("velvet", "secret society", "after-hours", "salon", "midnight", "crimson", "hedon")) and ("nsfw_faction_hq" in full_target or "velvet basement" in full_target):
        return True
    if str(npc.get("faction_category") or (npc.get("basic_info") or {}).get("faction_category") or "").lower() == "nsfw_club" and ("nsfw_faction_hq" in full_target or "velvet basement" in full_target):
        return True

    # Private residence ownership (resident's home)
    if "house" in full_target or "residence" in full_target or "bedroom" in full_target:
        if name and (name in full_target or any(part in full_target for part in name.split() if len(part) >= 3)):
            return True

    # Anomalous Incursions Faction HQ authority
    f_arch = str(npc.get("faction_archetype_key") or (npc.get("basic_info") or {}).get("faction_archetype_key") or "").lower()
    if f_arch:
        if f_arch == "public_agency" and ("loc_hq_" in full_target or "zone_agency_hq" in full_target or "loc_agency_hq" in full_target):
            return True
        if f_arch == "private_agency_1" and ("loc_private_hq_1" in full_target or "sub_priv1_" in full_target):
            return True
        if f_arch == "private_agency_2" and ("loc_private_hq_2" in full_target or "sub_priv2_" in full_target):
            return True
        if f_arch == "monastic_order" and ("loc_et_" in full_target or "zone_eastern_temple" in full_target):
            return True
        if f_arch == "cult_faction" and ("loc_cult_" in full_target or "sub_cult_" in full_target):
            return True
        if f_arch == "clandestine_faction" and ("loc_clandestine_" in full_target or "sub_synd_" in full_target):
            return True

    return False


def evaluate_anomalous_hq_access(
    session_id: int,
    node: dict,
    fac_node: dict | None = None,
    scen_key: str = "",
) -> dict[str, Any]:
    """
    Evaluates Tiered HQ Access Gates for Anomalous Incursions:
    - Public Lobbies, Contract Boards & Public Agency Shops are open to all friendly operatives & Freelancers.
    - Inner Sanctums, Containment Vaults, Operative Lounges & Private Armories require membership in that faction
      (or an active Story/Bounty quest waypoint or companion escort).
    - Cult & Clandestine HQs are restricted unless unlocked by a Story/Bounty waypoint or breach check.
    """
    try:
        from scenario_data import is_anomalous_incursions_scenario
        if not is_anomalous_incursions_scenario(scen_key):
            return {}
    except Exception:
        return {}

    n_id = str(node.get("node_id") or "").lower()
    n_name = str(node.get("name") or "").lower()
    p_id = str((fac_node or {}).get("node_id") or "").lower()
    p_name = str((fac_node or {}).get("name") or "").lower()
    combined = f"{n_id} {p_id} {n_name} {p_name}"

    required_arch = ""
    is_open_lobby_or_shop = False

    # 1. Public Agency HQ (`loc_agency_hq` / `zone_agency_hq` / `loc_hq_*`)
    if "loc_hq_" in combined or n_id in ("zone_agency_hq", "loc_agency_hq") or p_id in ("zone_agency_hq", "loc_agency_hq"):
        if n_id == "loc_agency_hq":
            is_open_lobby_or_shop = True
        elif any(k in combined for k in (
            "loc_hq_main_lobby", "loc_hq_tactical_armory", "loc_hq_field_outfitter",
            "loc_hq_medical_bay", "loc_hq_cleansing_bay", "loc_hq_canteen_cafe",
            "loc_hq_executive_dispatch", "entrance", "lobby", "reception", "bounty"
        )) and "loc_hq_containment_sector" not in combined and "loc_hq_research_division" not in combined:
            is_open_lobby_or_shop = True
        elif any(k in combined for k in (
            "loc_hq_containment_sector", "loc_hq_research_division", "loc_hq_parapsych_lab",
            "loc_hq_training_range", "loc_hq_training_arena", "loc_hq_agent_dormitories",
        )):
            required_arch = "public_agency"

    # 2. Private Agency #1 HQ (`loc_private_hq_1` / `sub_priv1_*`)
    elif "loc_private_hq_1" in combined or "sub_priv1_" in combined:
        if n_id == "loc_private_hq_1" or any(k in combined for k in ("sub_priv1_entrance", "sub_priv1_dispatch", "entrance", "lobby", "contract board", "contract & tactical dispatch")):
            is_open_lobby_or_shop = True
        else:
            required_arch = "private_agency_1"

    # 3. Private Agency #2 HQ (`loc_private_hq_2` / `sub_priv2_*`)
    elif "loc_private_hq_2" in combined or "sub_priv2_" in combined:
        if n_id == "loc_private_hq_2" or any(k in combined for k in ("sub_priv2_entrance", "sub_priv2_dispatch", "entrance", "lobby", "contract board", "contract & tactical dispatch")):
            is_open_lobby_or_shop = True
        else:
            required_arch = "private_agency_2"

    # 4. Monastic Shrine Order HQ (`loc_eastern_temple` / `loc_et_*`)
    elif "loc_et_" in combined or n_id in ("loc_eastern_temple", "zone_eastern_temple"):
        if any(k in combined for k in ("loc_et_five_story_pagoda", "loc_et_reliquary_pagoda", "loc_et_exorcist_dojo")) and "entrance" not in n_name:
            required_arch = "monastic_order"
        else:
            is_open_lobby_or_shop = True

    # 5. Cult & Clandestine HQs (`loc_cult_sanctum_hq`, `loc_clandestine_syndicate_hq`)
    elif "loc_cult_sanctum_hq" in combined or "sub_cult_" in combined:
        required_arch = "cult_faction"
    elif "loc_clandestine_syndicate_hq" in combined or "sub_synd_" in combined:
        required_arch = "clandestine_faction"

    if is_open_lobby_or_shop and not required_arch:
        return {"force_open": True}
    if not required_arch:
        return {}

    from mechanics.social.factions import get_anomalous_faction_state
    f_state = get_anomalous_faction_state(session_id)
    player_arch = str(f_state.get("faction_archetype_key") or "").lower()
    if player_arch == required_arch:
        return {"force_open": True, "unlocked_by_faction": required_arch}

    # Check if an active Story Quest or Accepted Bounty targets this location
    try:
        quests = db.get_session_quests(session_id) or []
        for q in quests:
            if str(q.get("status") or "").lower() in ("active", "accepted", "in_progress"):
                cand_locs = [
                    str(q.get("target_location") or "").lower(),
                    str(q.get("waypoint") or "").lower(),
                    str(q.get("location") or "").lower(),
                ]
                for wp_item in (q.get("waypoints") or []):
                    if isinstance(wp_item, dict):
                        cand_locs.append(str(wp_item.get("location") or wp_item.get("name") or "").lower())
                    elif wp_item:
                        cand_locs.append(str(wp_item).lower())
                for wp in cand_locs:
                    if wp and (wp in combined or (n_name and len(n_name) >= 5 and n_name in wp) or (p_name and len(p_name) >= 5 and p_name in wp)):
                        return {
                            "force_open": True,
                            "unlocked_by_quest": bool(q.get("is_story_quest")),
                            "unlocked_by_bounty": not bool(q.get("is_story_quest")),
                        }
    except Exception:
        pass

    label_map = {
        "public_agency": "Restricted Bureau Inner Sector (Public Agency Clearance Required)",
        "private_agency_1": "Restricted Syndicate Vault & Armory (Agency #1 Operative Clearance Required)",
        "private_agency_2": "Restricted Rival Syndicate Vault & Armory (Agency #2 Operative Clearance Required)",
        "monastic_order": "Restricted Monastic Inner Sanctum (Order Initiate Clearance Required)",
        "cult_faction": "Ward-Sealed Occult Sanctum (Hostile Cult Restricted Area)",
        "clandestine_faction": "Biometric Clandestine Vault (Unauthorized Entry Prohibited)",
    }
    return {
        "force_restricted": True,
        "required_faction_archetype": required_arch,
        "reason_label": label_map.get(required_arch, "Restricted Faction Sector"),
    }


def evaluate_node_access_gate(
    session_id: int,
    target_node_id: str,
    session: dict,
    actions: list = None,
    party: list = None,
    companions: list = None
) -> dict[str, Any]:
    """
    Evaluates whether player travel to target_node_id is halted by a lock, curfew,
    world schedule restriction, weekday school-hours truancy lockdown, or private residence intercom barrier.
    """
    if not session_id or not target_node_id:
        return {"gated": False}

    node = db.get_world_node(session_id, target_node_id)
    if not node:
        return {"gated": False}

    db_day, db_min, _ = db.get_session_time(session_id)
    curr_day = int(session.get("current_day") if (isinstance(session, dict) and session.get("current_day") is not None) else db_day)
    curr_min = int(session.get("current_minute") if (isinstance(session, dict) and session.get("current_minute") is not None) else db_min)
    safe_min = curr_min % 1440
    scen_key = (session.get("scenario") if isinstance(session, dict) else "") or "high_school_drama"

    from mechanics.world.schedules import get_time_block_key
    from mechanics.world.world_schedule import (
        is_abandoned_school_node,
        is_campus_node_or_location,
        is_high_school_setting,
        is_weekend,
    )
    time_block = (session.get("time_slot") if isinstance(session, dict) else None) or get_time_block_key(curr_min)

    fac_node = db.get_world_node(session_id, node["parent_id"]) if (node.get("parent_id") and node.get("node_type") == "ROOM") else None
    display_name = node.get("name") or target_node_id
    fac_name = fac_node.get("name") if fac_node else display_name
    low_id = target_node_id.lower()

    # 0. Special Condition: Abandoned School Building (`zone_abandoned_school`) is ALWAYS accessible 24/7
    if is_abandoned_school_node(node, fac_node, location_str=display_name):
        return {"gated": False, "abandoned_school_unrestricted": True}

    # Inventory & Accompanying Companion extraction (used by both Truancy Gate and Facility Gate)
    inventory_items = []
    for member in (party or []):
        c_obj = member[0] if isinstance(member, (tuple, list)) else member
        if isinstance(c_obj, dict):
            for it in (c_obj.get("inventory") or []):
                it_name = str(it.get("name") if isinstance(it, dict) else it).lower()
                inventory_items.append(it_name)
    inv_str = " ".join(inventory_items)

    active_companions = list(companions or [])
    if isinstance(session, dict):
        if session.get("temporary_companions"):
            active_companions.extend(session["temporary_companions"])
        if session.get("dialogue_partners"):
            for dp in session["dialogue_partners"]:
                if dp and not any(dp.lower() == (c.get("name") or "").lower() for c in active_companions if isinstance(c, dict)):
                    active_companions.append({"name": dp})

    current_action_label = " ".join(str(a.get("label", "") if isinstance(a, dict) else a) for a in (actions or [])).lower()
    has_check = bool(actions and isinstance(actions[0], dict) and (actions[0].get("check") or str(actions[0].get("stat", "NONE")).upper() != "NONE"))
    is_breach_action = has_check or any(w in current_action_label for w in (
        "sneak", "pick", "climb", "scale", "fence", "lockpick", "force", "break in", "bypass",
        "talk your way", "convince", "excuse", "nurse", "ring the intercom", "buzz", "apologize",
        "audition", "charm", "cellar", "grate"
    ))

    action_check_tier = "success"
    if actions and isinstance(actions[0], dict) and actions[0].get("check"):
        chk = actions[0]["check"]
        if isinstance(chk, dict):
            action_check_tier = str(chk.get("tier", "success")).lower()
        else:
            action_check_tier = str(getattr(chk, "tier", "success")).lower()

    # 0b. High School Weekday Class Hours (08:00–15:00 Mon–Fri): Outbound Truancy Lockdown & Late Arrival
    late_arrival_directive = ""
    if is_high_school_setting(scen_key) and not is_weekend(curr_day) and (480 <= safe_min < 900):
        raw_curr_loc = (session.get("current_location") if isinstance(session, dict) else "") or ""
        curr_node_id = (session.get("current_node_id") if isinstance(session, dict) else "") or ""
        curr_node_obj = db.get_world_node(session_id, curr_node_id) if curr_node_id else None
        curr_parent_obj = (
            db.get_world_node(session_id, curr_node_obj["parent_id"])
            if (curr_node_obj and curr_node_obj.get("parent_id"))
            else None
        )
        player_on_campus = is_campus_node_or_location(
            curr_node_obj, curr_parent_obj, location_str=raw_curr_loc, session_id=session_id, scen_key=scen_key
        )
        target_on_campus = is_campus_node_or_location(
            node, fac_node, location_str=display_name, session_id=session_id, scen_key=scen_key
        )

        # If player is already halted at loc_school_gate on Turn 2 and chooses "Return to campus grounds"
        if low_id == "loc_school_gate" and "return to campus" in current_action_label:
            db.update_world_node_state(session_id, "loc_school_gate", {"pending_truancy_target_node_id": "", "pending_truancy_target_name": ""})
            return {"gated": False, "returned_to_campus": True}

        # If player is halted at loc_school_gate on Turn 2 and attempts an outbound truancy breach
        gate_state = db.get_world_node_state(session_id, "loc_school_gate")
        if low_id == "loc_school_gate" and is_breach_action and gate_state.get("pending_truancy_target_node_id"):
            pending_id = gate_state["pending_truancy_target_node_id"]
            pending_node = db.get_world_node(session_id, pending_id)
            if pending_node:
                node = pending_node
                target_node_id = pending_id
                low_id = pending_id.lower()
                fac_node = db.get_world_node(session_id, node["parent_id"]) if (node.get("parent_id") and node.get("node_type") == "ROOM") else None
                display_name = node.get("name") or target_node_id
                fac_name = fac_node.get("name") if fac_node else display_name
                target_on_campus = False

        # Preserve direct NPC private residence intercom tests while enforcing truancy on all other off-campus destinations
        is_npc_private_home = (
            str(node.get("access_tier") or "").lower() == "private"
            and ("house" in low_id or "residence" in low_id)
            and low_id not in ("loc_player_house", "sub_player_bedroom")
            and "player's house" not in display_name.lower()
        )

        if player_on_campus and not target_on_campus and not is_npc_private_home:
            has_truancy_pass = (
                (gate_state.get("truancy_unlocked_day") or 0) >= curr_day
                or (isinstance(session, dict) and int(session.get("infirmary_pass_day") or 0) >= curr_day)
                or any(k in inv_str for k in ("hall pass", "nurse pass", "sick pass", "early dismissal", "staff pass", "gate pass", "master key", "council badge"))
                or any(
                    isinstance(comp, dict)
                    and any(r in str(comp.get("role") or (comp.get("basic_info") or {}).get("role") or "").lower() for r in ("teacher", "faculty", "staff", "nurse", "counselor", "principal"))
                    for comp in active_companions
                )
            )
            if not has_truancy_pass:
                from mechanics.world.locations.seeds import get_session_school_name
                school_zone = get_session_school_name(session_id, scen_key) or "Main Academy Campus"
                halt_loc = f"{school_zone} ➔ School Main Gates ➔ Outside the Locked Entrance"

                if is_breach_action:
                    is_success_tier = action_check_tier in ("critical_success", "crit_success", "success", "partial_success")
                    if is_success_tier:
                        db.update_world_node_state(
                            session_id,
                            "loc_school_gate",
                            {"truancy_unlocked_day": curr_day, "pending_truancy_target_node_id": "", "pending_truancy_target_name": ""}
                        )
                        return {
                            "gated": False,
                            "unlocked_by": "truancy_bypass",
                            "resolved_target_node_id": target_node_id,
                            "resolved_target_name": display_name,
                        }
                    else:
                        return {
                            "gated": True,
                            "node_id": "loc_school_gate",
                            "facility_node_id": "loc_school_gate",
                            "node_name": "School Main Gates",
                            "halt_location_override": halt_loc,
                            "reason_code": "school_hours_lockdown",
                            "reason_label": "Caught Attempting Truancy (08:00–15:00)",
                            "focal_point": "At the School Main Gates (Intercepted by Campus Gatekeeper)",
                            "patrol_confrontation": True,
                            "patrol_npc": {
                                "name": "Officer Takahashi",
                                "role": "Campus Gatekeeper",
                                "stage_role": "active_partner",
                                "attention_ring": "ring_1_primary",
                                "status_effects": ["Alerted"],
                            },
                            "prompt_directive": (
                                f"[SYSTEM: TRUANCY ATTEMPT INTERCEPTED (08:00–15:00)]\n"
                                f"The player attempted to sneak off campus toward {display_name} during active school hours, "
                                f"but was intercepted at the School Main Gates by the Campus Gatekeeper!"
                            ),
                            "barrier_choices": [
                                Phase2Choice(f"[CHA] Apologize and make up an excuse about forgetting a textbook", stat="CHA", requirement=10),
                                Phase2Choice("Return to campus grounds", stat="NONE", requirement=0),
                            ],
                        }

                db.update_world_node_state(
                    session_id,
                    "loc_school_gate",
                    {"pending_truancy_target_node_id": target_node_id, "pending_truancy_target_name": display_name}
                )
                return {
                    "gated": True,
                    "node_id": "loc_school_gate",
                    "facility_node_id": "loc_school_gate",
                    "node_name": "School Main Gates",
                    "halt_location_override": halt_loc,
                    "reason_code": "school_hours_lockdown",
                    "reason_label": "School Hours Lockdown (08:00–15:00 — Leaving Campus Forbidden)",
                    "focal_point": "At the Locked School Main Gates (Class Hours Lockdown 08:00–15:00)",
                    "prompt_directive": (
                        f"[SYSTEM: SCHOOL HOURS LOCKDOWN (08:00–15:00) — LEAVING CAMPUS FORBIDDEN]\n"
                        f"The player attempted to leave the school areas for {display_name} during active class hours (08:00 AM–3:00 PM Monday–Friday).\n"
                        f"- School rules strictly forbid students from leaving the school areas between 08:00 and 15:00.\n"
                        f"- Place the scene at '{halt_loc}' where the closed iron gates and campus gatekeeper block students from leaving.\n"
                        f"- The player must pass an [AGI] check to climb the side perimeter fence/sneak out, pass a [CHA] check to bluff past the gatekeeper with an excuse, or return to campus."
                    ),
                    "barrier_choices": [
                        Phase2Choice(f"[AGI] Sneak out by climbing the side perimeter fence toward {display_name}", stat="AGI", requirement=12),
                        Phase2Choice(f"[CHA] Convince the gatekeeper with a nurse's pass or family emergency excuse to leave for {display_name}", stat="CHA", requirement=11),
                        Phase2Choice("Return to campus grounds", stat="NONE", requirement=0),
                    ],
                }
        elif (not player_on_campus) and target_on_campus and safe_min > 480:
            late_arrival_directive = (
                f"[SYSTEM: LATE ARRIVAL TO SCHOOL ({format_minute_to_hhmm(safe_min)})]\n"
                f"The player is arriving on campus after the 08:00 AM first bell during active class hours. "
                f"Acknowledge the tardiness in the narration (quiet corridors, classes already underway, or slipping through the gate late)."
            )

    # 1. Player's own home is always accessible to the player (once off-campus)
    if low_id in ("loc_player_house", "sub_player_bedroom") or "player's house" in display_name.lower():
        return {"gated": False}

    # 1b. Love Hotel Automated Suite Rental (`$40` Mirrored Suite / `$80` Rooftop Jacuzzi Suite + Partner Waiver)
    node_state_raw = db.get_world_node_state(session_id, target_node_id)
    if low_id in ("sub_love_hotel_mirrored", "sub_love_hotel_jacuzzi") or node_state_raw.get("suite_fee"):
        suite_fee = int(node_state_raw.get("suite_fee") or (80 if "jacuzzi" in low_id else 40))
        suite_bonus = 3 if "jacuzzi" in low_id else 1
        if (
            (node_state_raw.get("suite_paid_day") or 0) >= curr_day
            or (node_state_raw.get("unlocked_until_day") or 0) >= curr_day
            or node_state_raw.get("unlocked_permanent")
        ):
            if isinstance(session, dict):
                session["active_love_hotel_suite_bonus"] = suite_bonus
            return {"gated": False, "love_hotel_suite_bonus": suite_bonus}

        # Check Partner-Invited Waiver ($0)
        partner_waived = bool(
            isinstance(session, dict)
            and (
                session.get("partner_treating_love_hotel")
                or int(session.get("love_hotel_waived_day") or 0) >= curr_day
            )
        )
        if not partner_waived:
            appts_lh = (db.get_phone_appointments(session_id, status="pending") or []) + (db.get_phone_appointments(session_id, status="arrived") or [])
            for appt in appts_lh:
                appt_t = str(appt.get("target_node_id") or "").lower()
                appt_l = str(appt.get("rendezvous_location") or "").lower()
                if any(k in f"{appt_t} {appt_l}" for k in ("love_hotel", "love hotel", "mirrored luxury", "rooftop jacuzzi")):
                    partner_waived = True
                    break

        if partner_waived:
            db.update_world_node_state(
                session_id,
                target_node_id,
                {"suite_paid_day": curr_day, "unlocked_until_day": curr_day, "last_unlock_reason": "partner_treated_suite"},
            )
            if isinstance(session, dict):
                session["active_love_hotel_suite_bonus"] = suite_bonus
            return {
                "gated": False,
                "unlocked_by": "partner_treated_suite",
                "suite_fee_paid": 0,
                "love_hotel_suite_bonus": suite_bonus,
                "prompt_directive": (
                    f"[STAGE DIRECTION — SUITE TREATED BY PARTNER]: Your partner already handled the automated kiosk fee "
                    f"for {display_name} ($0 charged to you; suite unlocked for the day/night)."
                ),
            }

        # Check player gold & deduct automated suite fee
        char_obj = None
        for member in (party or []):
            cand = member[0] if isinstance(member, (tuple, list)) else member
            if isinstance(cand, dict) and (cand.get("user_id") or cand.get("gold") is not None):
                char_obj = cand
                break
        user_id = int((char_obj or {}).get("user_id") or (session.get("host_id") if isinstance(session, dict) else 0) or 0)
        db_char = db.get_character(user_id) if user_id else None
        avail_gold = int(
            (char_obj.get("gold") if (char_obj and char_obj.get("gold") is not None) else (db_char or {}).get("gold")) or 0
        )

        if avail_gold >= suite_fee:
            if user_id and db_char:
                db.apply_hp_mp_delta(user_id, gold_delta=-suite_fee)
            if isinstance(char_obj, dict):
                char_obj["gold"] = max(0, avail_gold - suite_fee)
            db.update_world_node_state(
                session_id,
                target_node_id,
                {"suite_paid_day": curr_day, "unlocked_until_day": curr_day, "last_unlock_reason": "suite_fee_paid"},
            )
            if isinstance(session, dict):
                session["active_love_hotel_suite_bonus"] = suite_bonus
            return {
                "gated": False,
                "unlocked_by": "love_hotel_suite_payment",
                "suite_fee_paid": suite_fee,
                "love_hotel_suite_bonus": suite_bonus,
                "prompt_directive": (
                    f"[STAGE DIRECTION — AUTOMATED SUITE UNLOCKED]: The discreet touchscreen kiosk dispenses a magnetic keycard "
                    f"for {display_name} (${suite_fee} paid; unlocked for the rest of the day/night)."
                ),
            }
        else:
            lobby_choices = []
            if low_id == "sub_love_hotel_jacuzzi" and avail_gold >= 40:
                lobby_choices.append(Phase2Choice("Rent the Mirrored Luxury Suite ($40) instead", stat="NONE", requirement=0))
            lobby_choices.append(Phase2Choice("Step back into the Automated Touchscreen Check-In Lobby", stat="NONE", requirement=0))
            return {
                "gated": True,
                "node_id": "sub_love_hotel_lobby",
                "facility_node_id": "loc_love_hotel",
                "node_name": display_name,
                "reason_code": "insufficient_funds",
                "reason_label": f"Automated Suite Kiosk Requires ${suite_fee} (You have ${avail_gold})",
                "focal_point": "At the Automated Touchscreen Check-In Kiosk",
                "prompt_directive": (
                    f"[SYSTEM: LOVE HOTEL AUTOMATED SUITE KIOSK — INSUFFICIENT FUNDS]\n"
                    f"The glowing touchscreen panel in the clerkless lobby displays a ${suite_fee} rate for {display_name}, "
                    f"but the player currently only carries ${avail_gold}. Halt at the Automated Touchscreen Check-In Lobby."
                ),
                "barrier_choices": lobby_choices,
            }

    # 1c. NSFW Secret Society HQ (`loc_nsfw_faction_hq` / `Velvet Basement Salon`) Speakeasy Gate
    if low_id == "loc_nsfw_faction_hq" or "velvet basement" in display_name.lower():
        if isinstance(session, dict) and (
            session.get("nsfw_faction_member")
            or int(session.get("nsfw_faction_invited_day") or 0) >= curr_day
        ):
            record_node_unlock(session_id, target_node_id, unlock_type="day", current_day=curr_day, reason="nsfw_faction_invite")
            return {"gated": False, "unlocked_by": "nsfw_faction_invite"}
        try:
            for fac in (db.get_factions(session_id) or []):
                f_cat = str(fac.get("category") or "").lower()
                f_hq = str(fac.get("hq_location_id") or "").lower()
                if f_cat == "nsfw_club" or "velvet basement" in f_hq or "loc_nsfw_faction_hq" in f_hq:
                    f_rep = int(fac.get("reputation_score") or fac.get("reputation") or 0)
                    p_rank = int(fac.get("player_rank") or 0)
                    f_rank = str(fac.get("player_title") or fac.get("member_rank") or "").strip().lower()
                    if bool(fac.get("is_member")) or p_rank > 0 or f_rank not in ("", "none", "outsider", "non-member") or f_rep >= 25:
                        record_node_unlock(session_id, target_node_id, unlock_type="day", current_day=curr_day, reason="nsfw_faction_standing")
                        return {"gated": False, "unlocked_by": "nsfw_faction_standing"}
        except Exception:
            pass

    # 2. Check access info & existing unlocks
    access_info = get_node_effective_access_info(
        session_id, target_node_id, current_day=curr_day, current_minute=curr_min, scen_key=scen_key
    )
    if access_info["is_unlocked"]:
        res = {"gated": False}
        if late_arrival_directive:
            res["late_arrival_warning"] = True
            res["prompt_directive"] = late_arrival_directive
        return res

    tier = access_info["access_tier"]
    curfew_active = access_info["curfew_active"]
    schedule_locked = access_info.get("schedule_locked", False)
    is_trespassing = access_info.get("is_trespassing", False)

    # If it's an open node and neither curfew nor schedule lock is active, access is clear!
    if tier == "open" and not curfew_active and not schedule_locked:
        res = {"gated": False}
        if late_arrival_directive:
            res["late_arrival_warning"] = True
            res["prompt_directive"] = late_arrival_directive
        return res

    # Special Rule: Theme Park 22:00–08:00 Anomalous Shift allows nocturnal field investigation past warped turnstiles
    if access_info.get("schedule_reason_code") == "theme_park_anomalous_shift":
        return {
            "gated": False,
            "is_trespassing": True,
            "anomalous_shift_active": True,
            "prompt_directive": (
                "[STAGE DIRECTION — THEME PARK ANOMALOUS SHIFT (22:00–08:00)]: "
                "The Theme Park & Amusement Resort is closed to civilian crowds after 10:00 PM, "
                "but active spatial distortion leaves the shuttered turnstiles warped open. "
                "Depict an eerie nocturnal carnival atmosphere: reversed calliope music, flickering neon midway lights, "
                "zero mundane tourists, and active anomalous phenomena."
            ),
        }

    # 3. Check Inventory for Key / Pass / Badge (strict word-boundary match so "Keychain"/"Whiskey" never unlock vaults)
    if re.search(
        r"\b(master key|skeleton key|staff pass|council badge|keycard|passcard|access card|clearance badge|door key|gate key|vault key|sanctum key|room key|office key|key)\b",
        inv_str,
    ):
        record_node_unlock(session_id, target_node_id, unlock_type="permanent", current_day=curr_day, reason="key")
        return {"gated": False, "unlocked_by": "key"}

    # 4. Check Accompanying Companion Authority
    for comp in active_companions:
        if isinstance(comp, dict) and has_npc_authority_for_node(comp, node, fac_node):
            record_node_unlock(session_id, target_node_id, unlock_type="day", current_day=curr_day, reason="companion_authority")
            return {"gated": False, "unlocked_by": "companion_authority", "authorized_npc": comp.get("name")}

    # 5. Check Illicit / Scheduled Rendezvous (Edge Case 2)
    appts = (db.get_phone_appointments(session_id, status="pending") or []) + (db.get_phone_appointments(session_id, status="arrived") or [])
    for appt in appts:
        appt_target = appt.get("target_node_id") or ""
        appt_loc = appt.get("rendezvous_location") or ""
        is_match = False
        if appt_target:
            is_match = db.is_descendant_of(session_id, target_node_id, appt_target) or db.is_descendant_of(session_id, appt_target, target_node_id)
        elif appt_loc:
            from mechanics.world.waypoints import check_location_matches_waypoint
            is_match = check_location_matches_waypoint(display_name, appt_loc) or check_location_matches_waypoint(appt_loc, display_name)

        if is_match:
            record_node_unlock(session_id, target_node_id, unlock_type="day", current_day=curr_day, reason="illicit_rendezvous")
            return {
                "gated": False,
                "unlocked_by": "illicit_rendezvous",
                "illicit_rendezvous_npc": appt.get("npc_name", "your partner")
            }

    # 6. Check Private Residence Intercom Gate (Edge Case 5)
    if tier == "private" and ("house" in low_id or "residence" in low_id):
        contacts = db.get_contacts(session_id) or []
        disp_low = display_name.lower()
        resident_contact = None
        for c in contacts:
            if not isinstance(c, dict) or not c.get("name"):
                continue
            c_name = c["name"].strip()
            c_low = c_name.lower()
            tokens = [t for t in re.split(r"[\s_]+", c_low) if len(t) >= 3]
            if c_low in disp_low or any(t in disp_low for t in tokens):
                resident_contact = c
                break

        if resident_contact:
            score = int(resident_contact.get("relationship_score", 0) or 0)
            track = str(resident_contact.get("track", "")).lower()
            is_high_bond = (score >= 40) or (track == "romantic")
            if is_high_bond and safe_min < 1320:
                record_node_unlock(session_id, target_node_id, unlock_type="day", current_day=curr_day, reason="resident_welcome")
                return {"gated": False, "unlocked_by": "resident_welcome", "resident_name": resident_contact.get("name")}

    # 7. Check Current Action Check Result (Breach / Persuasion Attempt & Escalating Complication)
    state = db.get_world_node_state(session_id, target_node_id)
    failed_block_tag = f"{curr_day}_{time_block}"
    is_lock_jammed = state.get("failed_block") == failed_block_tag

    if is_breach_action:
        is_success_tier = action_check_tier in ("critical_success", "crit_success", "success", "partial_success")
        is_crit_fail_tier = action_check_tier in ("critical_failure", "crit_fail")
        if is_success_tier:
            record_node_unlock(session_id, target_node_id, unlock_type="day", current_day=curr_day, reason="skill_check")
            return {"gated": False, "unlocked_by": "skill_check"}
        else:
            # Action Failed: escalate complication
            db.update_world_node_state(session_id, target_node_id, {"failed_block": failed_block_tag})
            patrol_confrontation = is_crit_fail_tier or curfew_active or is_trespassing
            patrol_npc = None
            if patrol_confrontation:
                if isinstance(session, dict):
                    try:
                        from mechanics.stealth import break_stealth
                        break_stealth(session, reason="caught_at_restricted_gate", break_all=True)
                    except Exception:
                        pass
                # Try pulling an existing authority figure from contacts / school roster (User Decision #1)
                roster = db.get_school_roster(session_id) or []
                contacts = db.get_contacts(session_id) or []
                authority_cands = []
                if not (curfew_active or is_trespassing):
                    for c in (contacts + roster):
                        if not isinstance(c, dict):
                            continue
                        r_txt = str(c.get("role") or (c.get("basic_info") or {}).get("role") or "").lower()
                        c_txt = str(c.get("club") or (c.get("basic_info") or {}).get("club") or "").lower()
                        if any(k in r_txt for k in ("teacher", "staff", "guidance", "counselor", "principal", "vice principal", "prefect", "hall monitor", "discipline")) or any(k in c_txt for k in ("student council", "disciplinary")):
                            authority_cands.append(c)
                if authority_cands:
                    chosen = authority_cands[0]
                    c_role = chosen.get("role") or "Campus Authority"
                    patrol_npc = {
                        "name": chosen.get("name"),
                        "role": f"{c_role} (Hall Monitor)" if "hall monitor" not in c_role.lower() else c_role,
                        "stage_role": "active_partner",
                        "attention_ring": "ring_1_primary",
                        "status_effects": ["Alerted"]
                    }
                else:
                    import hashlib
                    officer_pool = ["Officer Takahashi", "Officer Miller", "Officer Sato", "Officer Vance", "Officer Henderson"]
                    s_idx = int(hashlib.md5(f"patrol_{session_id}_{target_node_id}_{curr_day}".encode()).hexdigest(), 16) % len(officer_pool)
                    chosen_officer = officer_pool[s_idx]
                    patrol_npc = {
                        "name": chosen_officer,
                        "role": "Night Security Officer" if (curfew_active or is_trespassing) else "Campus Hall Monitor",
                        "stage_role": "active_partner",
                        "attention_ring": "ring_1_primary",
                        "status_effects": ["Alerted"]
                    }
            return {
                "gated": True,
                "node_id": target_node_id,
                "node_name": display_name,
                "reason_code": "breach_failed",
                "reason_label": "Lock Jammed / Caught Trespassing" if is_trespassing else "Lock Jammed / Caught Sneaking",
                "focal_point": f"Outside the Locked Entrance ({display_name})",
                "patrol_confrontation": patrol_confrontation,
                "patrol_npc": patrol_npc,
                "prompt_directive": (
                    f"[SYSTEM: BREACH FAILED - PATROL CONFRONTATION]\n"
                    f"The attempt to enter {display_name} failed! "
                    + (f"A patrolling authority figure ({patrol_npc['name']}) has spotted the player and demands an explanation." if patrol_npc else "The door mechanism jammed shut, preventing further forced entry for now.")
                ),
                "barrier_choices": [
                    Phase2Choice(f"[CHA] Make up a believable excuse to defuse suspicion", stat="CHA", requirement=11),
                    Phase2Choice(f"[AGI] Slip away into the corridor shadows before you are detained", stat="AGI", requirement=12),
                    Phase2Choice(f"Step away from {display_name}", stat="NONE", requirement=0)
                ] if patrol_confrontation else [
                    Phase2Choice(f"[CHA] Seek out someone with a key or permission for {display_name}", stat="CHA", requirement=10),
                    Phase2Choice(f"Turn back from {display_name}", stat="NONE", requirement=0)
                ]
            }

    # 8. Unresolved Barrier: Halt at Threshold
    sched_reason_code = access_info.get("schedule_reason_code") or ""
    sched_reason_label = access_info.get("schedule_reason_label") or ""

    if sched_reason_code in ("commercial_closed", "weekend_closed"):
        reason_code = sched_reason_code
        reason_label = sched_reason_label
    elif curfew_active or is_trespassing:
        reason_code = "curfew"
        reason_label = sched_reason_label or f"Curfew in Effect ({access_info['curfew_label']})"
    elif tier == "private":
        reason_code = "private_intercom"
        reason_label = "Private Residence Gate"
    elif low_id == "loc_nsfw_faction_hq" or "velvet basement" in display_name.lower():
        reason_code = "speakeasy_restricted"
        reason_label = "Secret Society Speakeasy Door (Membership, Invite, or Audition Required)"
    else:
        reason_code = "restricted"
        reason_label = sched_reason_label or "Restricted Access"

    barrier_choices = []
    if low_id == "loc_nsfw_faction_hq" or "velvet basement" in display_name.lower():
        if not is_lock_jammed:
            barrier_choices.append(Phase2Choice(f"[AGI] Slip quietly through the cellar service grate into {display_name}", stat="AGI", requirement=12))
        barrier_choices.append(Phase2Choice(f"[CHA] Audition or charm the doorkeeper to gain entry to {display_name}", stat="CHA", requirement=12))
        barrier_choices.append(Phase2Choice(f"Step away from {display_name}", stat="NONE", requirement=0))
    else:
        if not is_lock_jammed:
            barrier_choices.append(Phase2Choice(f"[AGI] Sneak in or pick the lock to enter {display_name}", stat="AGI", requirement=12))
        if tier == "private":
            barrier_choices.append(Phase2Choice(f"[CHA] Ring the intercom and ask to be let into {display_name}", stat="CHA", requirement=10))
        else:
            barrier_choices.append(Phase2Choice(f"[CHA] Talk your way past authority or seek permission for {display_name}", stat="CHA", requirement=11))
        barrier_choices.append(Phase2Choice(f"Turn back from {display_name}", stat="NONE", requirement=0))

    trespass_note = (
        "\n- TRESPASSING WARNING: It is between 20:00 and 07:00. All students and teachers have gone home, "
        "the entire school area is restricted, and entering or staying on campus is considered TRESPASSING."
        if is_trespassing
        else ""
    )

    prompt_directive = (
        f"[SYSTEM: LOCKED / RESTRICTED THRESHOLD BARRIER]\n"
        f"The player has arrived at the threshold of {display_name}, but cannot enter because: {reason_label}.\n"
        f"- Location and micro-positioning: Place characters at 'Outside the Locked Entrance / Threshold of {display_name}'.\n"
        f"- Narration: Describe the locked doors, darkened interior, or warning signage. Characters MUST halt here until granted entry or bypassing the lock."
        f"{trespass_note}"
    )

    return {
        "gated": True,
        "node_id": target_node_id,
        "facility_node_id": fac_node.get("node_id") if fac_node else target_node_id,
        "node_name": display_name,
        "reason_code": reason_code,
        "reason_label": reason_label,
        "is_trespassing": is_trespassing,
        "focal_point": f"Outside the Locked Entrance ({reason_label})",
        "prompt_directive": prompt_directive,
        "barrier_choices": barrier_choices
    }


def record_turn_scene_residue(
    session_id: int,
    node_id: str,
    session: dict,
    result: dict,
    actions: list,
    unlocked_by: str = ""
) -> str | None:
    """
    Evaluates notable moments from this turn and updates a rolling 3-memory log (with priority pinning)
    in state_json for the current room node and its parent facility node.
    """
    if not session_id or not node_id:
        return None

    node = db.get_world_node(session_id, node_id)
    if not node:
        return None

    curr_day, curr_min, _ = db.get_session_time(session_id)
    new_memory_text = ""
    priority = 1

    # 1. Romantic / Intimate Climax (Priority 3)
    from mechanics.social.physical_state import is_erotic_intimate_contact
    _pre_ic = str(((session.get("physical_state") or {}).get("intimate_contact") or "")).lower()
    _upd_ic = str(((result.get("physical_updates") or {}).get("intimate_contact") or "")).lower()
    lead_partner = result.get("dialogue_partner") or (result.get("dialogue_partners") or [None])[0] or "a partner"

    if is_erotic_intimate_contact(_pre_ic) or is_erotic_intimate_contact(_upd_ic):
        new_memory_text = f"Day {curr_day}: Shared an intimate encounter with {lead_partner} here."
        priority = 3
    # 2. Clue Discovery / Quest Progress (Priority 2)
    elif result.get("quest_updates"):
        for qu in result["quest_updates"]:
            if isinstance(qu, dict) and qu.get("current_clues"):
                snip = str(qu["current_clues"]).strip()[:60]
                new_memory_text = f"Day {curr_day}: Discovered clue: {snip}."
                priority = 2
                break
    # 3. Breach / Unlock Event (Priority 2)
    elif unlocked_by in ("skill_check", "key", "illicit_rendezvous"):
        node_name = node.get("name", "the entrance")
        new_memory_text = f"Day {curr_day}: Bypassed security to enter {node_name} ({unlocked_by})."
        priority = 2
    # 4. Hostile Combat Resolution (Priority 2)
    elif result.get("_combat_resolved_notice"):
        new_memory_text = f"Day {curr_day}: Fought off hostile confrontation here."
        priority = 2
    # 5. Memorable NPC Exchange / Bond Shift (Priority 1)
    elif result.get("npc_memories") and isinstance(result["npc_memories"], list) and result["npc_memories"]:
        first_mem = result["npc_memories"][0]
        summary = first_mem.get("summary") or first_mem.get("memory") or ""
        if summary:
            new_memory_text = f"Day {curr_day}: {summary[:70]}."
            priority = 1

    if not new_memory_text:
        return None

    # Load existing state
    state = db.get_world_node_state(session_id, node_id)
    log_list = list(state.get("scene_residue_log") or [])

    # Deduplicate and append
    filtered_log = [m for m in log_list if m.get("text") != new_memory_text]
    filtered_log.append({
        "day": curr_day,
        "minute": curr_min,
        "text": new_memory_text[:140],
        "priority": priority
    })

    # Keep rolling 3 entries
    filtered_log = filtered_log[-3:]

    # Pin highest priority (tie-broken by index, latest wins)
    pinned_entry = max(filtered_log, key=lambda x: (x.get("priority", 1), filtered_log.index(x)))
    pinned_residue = pinned_entry["text"]

    updates = {
        "scene_residue": pinned_residue,
        "scene_residue_log": filtered_log,
        "last_visited_day": curr_day,
        "last_visited_minute": curr_min
    }

    db.update_world_node_state(session_id, node_id, updates)
    if node.get("parent_id") and node.get("node_type") == "ROOM":
        db.update_world_node_state(session_id, node["parent_id"], updates)

    return pinned_residue


def get_privacy_nudge_choice(
    session_id: int,
    current_node_id: str,
    partner_name: str,
    session: dict,
    actions: list = None
) -> str | None:
    """
    Edge Case 7: When in a public sub-location with an active dialogue partner during
    confidential, secret, or romantic tension, returns a choice to step into an adjacent secluded room or prop.
    """
    if not session_id or not current_node_id or not partner_name:
        return None

    curr_node = db.get_world_node(session_id, current_node_id)
    if not curr_node:
        resolved_id = db.resolve_node_id_from_location(session_id, current_node_id)
        if resolved_id:
            curr_node = db.get_world_node(session_id, resolved_id)
    if not curr_node or curr_node.get("privacy_level") != "public":
        return None

    parent_id = curr_node.get("parent_id")
    if not parent_id:
        return None

    # Check partner bond / context
    contacts = db.get_contacts(session_id) or []
    contact = next((c for c in contacts if (c.get("name") or "").lower() == partner_name.lower()), None)
    is_romantic = False
    if contact:
        score = int(contact.get("relationship_score", 0) or 0)
        track = str(contact.get("track", "")).lower()
        is_romantic = (score >= 30) or (track == "romantic")

    action_text = " ".join(str(a.get("label", "") if isinstance(a, dict) else a) for a in (actions or [])).lower()
    is_secret_context = any(w in action_text for w in ("confess", "kiss", "whisper", "private", "alone", "secret", "hide", "intimate"))

    if not (is_romantic or is_secret_context):
        return None

    # 1. Check for a secluded prop within the current room first
    try:
        from .seeds import get_node_props
        scen_key = (session.get("scenario") if isinstance(session, dict) else "") or "high_school_drama"
        curr_focal = str((session.get("focal_point") if isinstance(session, dict) else "") or "").lower()
        room_props = get_node_props(session_id, curr_node["node_id"], scenario_key=scen_key)
        secluded_prop_keywords = ("aisle", "alcove", "corner", "behind", "booth", "closet", "balcony", "stairwell", "under")
        for pr in room_props:
            pr_low = pr.lower()
            if pr_low != curr_focal and any(k in pr_low for k in secluded_prop_keywords):
                return Phase2Choice(f"Step into {pr} with {partner_name} for privacy", stat="NONE", requirement=0)
    except Exception:
        pass

    # 2. Find adjacent secluded sibling room under the same facility
    all_nodes = db.get_session_world_nodes(session_id)
    siblings = [
        n for n in all_nodes
        if n.get("parent_id") == parent_id
        and n.get("node_id") != curr_node["node_id"]
        and n.get("node_type") == "ROOM"
        and n.get("privacy_level") in ("semi_private", "private")
    ]

    if not siblings:
        return None

    chosen_sub = siblings[0]
    return Phase2Choice(f"Step into {chosen_sub['name']} with {partner_name} for privacy", stat="NONE", requirement=0)
