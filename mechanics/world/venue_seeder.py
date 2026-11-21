"""
Lazy Seed-Deterministic Venue Seeder, Roaming Merchants & Staff-Bound Shop Availability.

Pure closed-world authority backed by SQLite `world_nodes`, `world_roster`, and `world_events`.
Enforces Ruling 5 (canonical enums in `db/roster_adapters.py`) and Ruling 6 (`include_legacy_rosters=False`).
"""
from __future__ import annotations

import hashlib
import random
import re
import sqlite3
from typing import Any, Mapping

import db
import namegen
import scenario_data
from db.roster_adapters import slugify_npc_id
from mechanics.world.anchor_schedule import is_npc_on_active_shift
from mechanics.social.relationships import safe_get_contacts
from mechanics.world.locations import (
    get_available_merchant_types_for_location,
    is_school_scenario,
    location_has_merchant_shop,
)
from mechanics.world.locations.residence_fog import SHARED_ABSTRACT_RESIDENCE_NODE
from mechanics.world.schedule_blocks import get_time_block_key
from mechanics.world.venue_templates import (
    FESTIVAL_EVENT_SUBTYPES,
    PRIVATE_RESIDENCE_KEYWORDS,
    ROAMER_EXCLUDE_KEYWORDS,
    ROAMER_HUB_KEYWORDS,
    get_crowd_flavor_text,
    is_civic_or_multi_wing_hub_node,
    is_kiosk_location,
    is_node_staffable,
    parse_node_state,
    resolve_slot_fill_role_spec,
    select_venue_template,
)


_SHIFT_REPRESENTATIVE_MINUTE: dict[str, int] = {
    "day": 600,
    "evening": 960,
    "night": 1320,
    "student": 600,
    "rotating": 600,
    "roaming_merchant": 600,
}


def _availability_result(
    *,
    available: bool,
    reason: str,
    reason_message: str,
    staff_npc: dict[str, Any] | None = None,
    facility_node_id: str = "",
) -> dict[str, Any]:
    return {
        "available": bool(available),
        "reason": str(reason),
        "reason_message": str(reason_message),
        "staff_npc": dict(staff_npc) if isinstance(staff_npc, dict) else None,
        "facility_node_id": str(facility_node_id or ""),
    }


def _derive_seed_int(seed_material: str) -> int:
    return int(hashlib.sha256(seed_material.encode("utf-8")).hexdigest()[:16], 16)


def _get_session_seed(session: Mapping[str, Any] | None, session_id: int) -> str:
    sess = session if isinstance(session, Mapping) else (db.get_session(session_id) if session_id > 0 else None)
    return str((sess or {}).get("world_seed") or (sess or {}).get("rng_seed") or session_id)


def _collect_taken_names_and_ids(session_id: int) -> tuple[set[str], set[str]]:
    taken_names: set[str] = set()
    taken_ids: set[str] = set()
    if int(session_id or 0) <= 0:
        return taken_names, taken_ids
    for row in safe_get_contacts(session_id, ensure_scene=False, resolve_relations=False) + (db.get_world_roster(session_id, include_legacy_rosters=False) or []):
        rname = str(row.get("name") or "").strip().lower()
        rid = str(row.get("npc_id") or "").strip().lower()
        if rname:
            taken_names.add(rname)
        if rid:
            taken_ids.add(rid)
    return taken_names, taken_ids


def _generate_unique_seeded_profile(
    *,
    seed_base: str,
    scen_key: str,
    taken_names: set[str],
    taken_ids: set[str],
    shift_profile: str,
    is_24h: bool,
    is_unique: bool,
    facility_node_id: str,
    roaming_route: list[str] | None = None,
    check_open_day: int | None = None,
) -> tuple[str, str, str]:
    chosen_id, chosen_name, chosen_gender = "", "", "female"
    fallback_candidate: tuple[str, str, str] | None = None
    for attempt in range(32):
        material = seed_base if attempt == 0 else f"{seed_base}:salt:{attempt}"
        profile = namegen.generate_npc_profile(scenario=scen_key, rng=random.Random(_derive_seed_int(material))) or {}
        name = str(profile.get("name") or f"Merchant {attempt + 1}").strip()
        gender = str(profile.get("gender") or "female").strip()
        if name.lower() in taken_names:
            continue

        base_slug = slugify_npc_id(name) or f"npc_{attempt + 1}"
        cand_id = base_slug
        if cand_id.lower() in taken_ids:
            cand_id = next((f"{base_slug}_{i}" for i in range(2, 40) if f"{base_slug}_{i}".lower() not in taken_ids), f"{base_slug}_{attempt}")
        if fallback_candidate is None:
            fallback_candidate = (cand_id, name, gender)

        # Avoid deterministic weekly rest day landing right on Day 1 or on a replacement hire's onboarding day.
        # _canonical_seed_key hashes "name" first, so stepping to a new deterministic name on collision is required.
        if check_open_day is not None and not is_24h and shift_profile not in ("student", "roaming_merchant"):
            rep_min = _SHIFT_REPRESENTATIVE_MINUTE.get(shift_profile, 600)
            probe_npc = {
                "npc_id": cand_id, "name": name, "origin": "venue_seed", "shift_profile": shift_profile,
                "staff_status": "active", "workplace_node_id": facility_node_id,
                "roaming_route": list(roaming_route or []), "is_unique_proprietor": is_unique,
                "basic_info": {"name": name, "is_24h_station": is_24h},
            }
            on_shift, _ = is_npc_on_active_shift(probe_npc, rep_min, current_day=check_open_day, scen_key=scen_key, session_id=None)
            if not on_shift:
                continue

        chosen_id, chosen_name, chosen_gender = cand_id, name, gender
        break

    if not chosen_id:
        for fb_idx in range(32):
            fallback_seed = _derive_seed_int(f"{seed_base}:fallback:{fb_idx}")
            fb_name = f"Merchant {fallback_seed % 9000 + 1000}"
            fb_id = slugify_npc_id(fb_name)
            if fb_name.lower() in taken_names or fb_id.lower() in taken_ids:
                continue
            if check_open_day is not None and not is_24h and shift_profile not in ("student", "roaming_merchant"):
                rep_min = _SHIFT_REPRESENTATIVE_MINUTE.get(shift_profile, 600)
                probe_fb = {
                    "npc_id": fb_id, "name": fb_name, "origin": "venue_seed", "shift_profile": shift_profile,
                    "staff_status": "active", "workplace_node_id": facility_node_id,
                    "roaming_route": list(roaming_route or []), "is_unique_proprietor": is_unique,
                    "basic_info": {"name": fb_name, "is_24h_station": is_24h},
                }
                if not is_npc_on_active_shift(probe_fb, rep_min, current_day=check_open_day, scen_key=scen_key, session_id=None)[0]:
                    continue
            chosen_id, chosen_name = fb_id, fb_name
            break
        if not chosen_id and fallback_candidate is not None:
            chosen_id, chosen_name, chosen_gender = fallback_candidate
        elif not chosen_id:
            fallback_seed = _derive_seed_int(f"{seed_base}:fallback")
            chosen_id = f"seeded_npc_{fallback_seed % 1000000}"
            chosen_name = f"Merchant {fallback_seed % 900 + 100}"

    taken_names.add(chosen_name.lower())
    taken_ids.add(chosen_id.lower())
    return chosen_id, chosen_name, chosen_gender


def _build_roster_payload(
    *,
    npc_id: str,
    name: str,
    gender: str,
    role: str,
    occupation: str,
    origin: str,
    workplace_node_id: str,
    shift_profile: str,
    merchant_archetypes: list[str] | tuple[str, ...],
    venue_name: str = "",
    staff_status_day: int = 0,
    is_unique_proprietor: bool = False,
    is_24h_station: bool = False,
    roaming_route: list[str] | None = None,
    extra_basic_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    basic: dict[str, Any] = {
        "role": role,
        "occupation": occupation,
        "age_group": "teen" if shift_profile == "student" else "adult",
        "merchant_archetypes": list(merchant_archetypes or ()),
        "is_24h_station": bool(is_24h_station),
        "is_unique_proprietor": bool(is_unique_proprietor),
        "is_contact_eligible": True,
    }
    if venue_name:
        basic["venue_name"] = venue_name
        basic["work_location_label"] = venue_name
    if extra_basic_info:
        basic.update(extra_basic_info)

    payload: dict[str, Any] = {
        "npc_id": npc_id,
        "name": name,
        "gender": gender,
        "role": role,
        "origin": origin,
        "tier_status": "seeded",
        "workplace_node_id": workplace_node_id,
        "home_node_id": SHARED_ABSTRACT_RESIDENCE_NODE,
        "shift_profile": shift_profile,
        "staff_status": "active",
        "staff_status_day": int(staff_status_day),
        "is_unique_proprietor": bool(is_unique_proprietor),
        "basic_info": basic,
    }
    if roaming_route is not None:
        payload["roaming_route"] = list(roaming_route)
    return payload


def ensure_venue_staff_seeded(
    session_id: int,
    facility_node_id: str,
    scen_key: str = "fantasy",
    current_day: int = 1,
    turn_number: int = 0,
    session: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Lazily and deterministically seed 1–4 named venue staff for a staffable world node.

    Idempotent: returns existing non-legacy `world_roster` rows if already seeded for this node.
    """
    _ = current_day
    sid = int(session_id or 0)
    nid = str(facility_node_id or "").strip()
    if sid <= 0 or not nid:
        return []

    node = db.get_world_node(sid, nid)
    session = dict(session) if isinstance(session, Mapping) else (db.get_session(sid) or {})
    eff_scen = str(scen_key or session.get("scenario") or "fantasy").strip() or "fantasy"
    if not is_node_staffable(node, scen_key=eff_scen):
        return []

    existing_all = db.get_world_roster(sid, workplace_node_id=nid, include_legacy_rosters=False) or []
    existing = [
        r for r in existing_all
        if str(r.get("origin") or "").strip().lower() in ("venue_seed", "replacement_hire", "district_merchant", "civic_staff", "campus_seed")
    ]
    if existing:
        return existing

    session_seed = _get_session_seed(session, sid)
    node_name = str((node or {}).get("name") or nid).strip()
    node_meta = parse_node_state(node)
    _, role_specs = select_venue_template(node_name, category=str((node or {}).get("category") or ""), scen_key=eff_scen, node=node)

    taken_names, taken_ids = _collect_taken_names_and_ids(sid)
    seeded_rows: list[dict[str, Any]] = []
    for slot_idx, spec in enumerate(role_specs[:4]):
        is_unique = bool(spec.get("is_unique_proprietor") or (slot_idx == 0 and node_meta.get("is_unique_proprietor")))
        is_24h = bool(spec.get("is_24h_station"))
        shift_profile = str(spec.get("shift_profile") or "day")
        npc_id, name, gender = _generate_unique_seeded_profile(
            seed_base=f"{session_seed}:{nid}:{slot_idx}",
            scen_key=eff_scen,
            taken_names=taken_names,
            taken_ids=taken_ids,
            shift_profile=shift_profile,
            is_24h=is_24h,
            is_unique=is_unique,
            facility_node_id=nid,
            check_open_day=1 if slot_idx == 0 else None,
        )
        payload = _build_roster_payload(
            npc_id=npc_id, name=name, gender=gender,
            role=spec["role"], occupation=spec["occupation"], origin="venue_seed",
            workplace_node_id=nid, shift_profile=shift_profile,
            merchant_archetypes=spec.get("merchant_archetypes") or (),
            venue_name=node_name, is_unique_proprietor=is_unique, is_24h_station=is_24h,
        )
        row = db.upsert_world_roster_npc(sid, payload, turn_number=int(turn_number or 0))
        if isinstance(row, dict):
            seeded_rows.append(row)
    return seeded_rows


def _select_roamer_candidate_nodes(world_nodes: list[dict[str, Any]]) -> list[str]:
    from mechanics.world.anomalous_sites.catalog import (
        AHS_PROTECTED_SUB_IDS,
        THEME_PARK_EPICENTER_IDS,
        resolve_anomalous_site,
    )

    ranked: list[tuple[int, str]] = []
    for n in world_nodes:
        nid = str(n.get("node_id") or "").strip()
        pid = str(n.get("parent_id") or "").strip()
        name = str(n.get("name") or "").strip().lower()
        cat = str(n.get("category") or "").strip().lower()
        ntype = str(n.get("node_type") or "").strip().upper()
        state_json = parse_node_state(n)
        if not nid or nid == SHARED_ABSTRACT_RESIDENCE_NODE:
            continue
        if ntype == "ROOM" or is_civic_or_multi_wing_hub_node(n):
            continue
        if bool(state_json.get("is_player_residence") or state_json.get("unstaffed")) or any(b in name for b in PRIVATE_RESIDENCE_KEYWORDS):
            continue
        if nid.lower() not in AHS_PROTECTED_SUB_IDS and not state_json.get("is_minor_club_hq"):
            if bool(state_json.get("is_anomalous")) or nid.lower() in THEME_PARK_EPICENTER_IDS:
                continue
            spec = resolve_anomalous_site(node_id=nid, parent_id=pid, location_str=name, curr_node=n, session_nodes=world_nodes)
            if spec is not None and spec.get("site_type") != "theme_park_night":
                continue

        has_hub_kw = any(kw in name for kw in ROAMER_HUB_KEYWORDS)
        has_excl_kw = any(bad in name for bad in ROAMER_EXCLUDE_KEYWORDS)
        if cat == "wilderness" and not any(k in name for k in ("outpost", "crossroads", "caravan", "trading post", "camp")):
            continue
        if cat == "residential" or has_excl_kw:
            continue

        if has_hub_kw and ntype in ("FACILITY", "ZONE"):
            ranked.append((0 if ntype == "FACILITY" else 1, nid))
        elif ntype == "ZONE" and cat == "commercial":
            ranked.append((2, nid))

    ranked.sort(key=lambda item: (item[0], item[1]))
    return list(dict.fromkeys(nid for _, nid in ranked))


def ensure_roaming_merchants_seeded(
    session_id: int,
    scen_key: str = "fantasy",
    turn_number: int = 0,
    session: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Deterministically seed 1–2 `roaming_merchant` NPCs across valid commercial hubs/trade stops.

    Returns `[]` in school scenarios, scenarios without `merchant_encounters`, or graphs lacking trade stops.
    """
    sid = int(session_id or 0)
    if sid <= 0:
        return []

    session = dict(session) if isinstance(session, Mapping) else (db.get_session(sid) or {})
    eff_scen = str(scen_key or session.get("scenario") or "fantasy").strip() or "fantasy"
    roster = db.get_world_roster(sid, include_legacy_rosters=False) or []
    existing_roamers = [r for r in roster if str(r.get("origin") or "").strip().lower() == "roaming_merchant"]
    if existing_roamers:
        return existing_roamers

    if is_school_scenario(eff_scen) or not scenario_data.is_mechanic_enabled(eff_scen, "merchant_encounters"):
        return []

    stops = _select_roamer_candidate_nodes(db.get_session_world_nodes(sid) or [])
    if not stops:
        return []

    roamer_routes = [stops[0:2], stops[2:4]] if len(stops) >= 4 else ([stops[:3]] if len(stops) >= 2 else [[stops[0]]])
    roamer_archetypes = ["general_merchant", "food_merchant", "potion_merchant", "accessories_merchant"]
    if eff_scen.strip().lower() not in ("cyberpunk", "sci_fi", "nuclear_post_apocalypse"):
        roamer_archetypes.append("gift_merchant")

    session_seed = _get_session_seed(session, sid)
    taken_names, taken_ids = _collect_taken_names_and_ids(sid)
    seeded: list[dict[str, Any]] = []

    for idx, route in enumerate(roamer_routes):
        npc_id, name, gender = _generate_unique_seeded_profile(
            seed_base=f"{session_seed}:roamer:{idx}",
            scen_key=eff_scen,
            taken_names=taken_names,
            taken_ids=taken_ids,
            shift_profile="roaming_merchant",
            is_24h=False,
            is_unique=False,
            facility_node_id=route[0],
            roaming_route=route,
        )
        payload = _build_roster_payload(
            npc_id=npc_id, name=name, gender=gender,
            role="Traveling Caravan Merchant", occupation="Traveling Merchant",
            origin="roaming_merchant", workplace_node_id=route[0],
            shift_profile="roaming_merchant", merchant_archetypes=roamer_archetypes,
            roaming_route=route, extra_basic_info={"is_roaming_merchant": True},
        )
        row = db.upsert_world_roster_npc(sid, payload, turn_number=int(turn_number or 0))
        if isinstance(row, dict):
            seeded.append(row)
    return seeded


def _staff_matches_requested_role(staff: dict[str, Any], role_spec: dict[str, Any], requested_role: str) -> bool:
    basic = staff.get("basic_info") if isinstance(staff.get("basic_info"), dict) else {}
    haystack = " ".join([
        str(staff.get("role") or ""), str(basic.get("role") or ""),
        str(basic.get("occupation") or ""), str(basic.get("slot_fill_role_key") or ""),
    ]).strip().lower()
    if not haystack:
        return False
    req_low = str(requested_role or "").strip().lower()
    role_key = str(role_spec.get("role_key") or "").strip().lower()
    return bool(
        (req_low and req_low in haystack)
        or (role_key and role_key in haystack)
        or str(role_spec.get("role") or "").strip().lower() in haystack
        or str(role_spec.get("occupation") or "").strip().lower() in haystack
    )


def slot_fill_custom_action_role(
    session_id: int,
    facility_node_id: str,
    requested_role: str,
    scen_key: str = "fantasy",
    current_day: int = 1,
    current_minute: int = 480,
    turn_number: int = 1,
) -> dict[str, Any] | None:
    """
    Conditionally slot-fill one plausible staffed role on an explicit custom action at a valid facility.

    Enforces venue plausibility, operating-hours gating, existing-staff reuse, and a hard cap of 1
    `origin="role_slot_fill"` per `(session_id, facility_node_id, role_slug)`.
    """
    sid = int(session_id or 0)
    nid = str(facility_node_id or "").strip()
    req = str(requested_role or "").strip()
    if sid <= 0 or not nid or not req:
        return None

    node = db.get_world_node(sid, nid)
    session = db.get_session(sid) or {}
    eff_scen = str(scen_key or session.get("scenario") or "fantasy").strip() or "fantasy"
    if not node or not is_node_staffable(node, scen_key=eff_scen):
        return None

    node_name = str(node.get("name") or "").strip()
    role_spec = resolve_slot_fill_role_spec(req, node_name, category=str(node.get("category") or ""), scen_key=eff_scen, node=node)
    if role_spec is None:
        return None

    eff_day = int(current_day or 1)
    eff_min = int(current_minute if current_minute is not None else 480)
    probe = {
        "origin": "role_slot_fill", "shift_profile": role_spec["shift_profile"],
        "staff_status": "active", "workplace_node_id": nid,
        "basic_info": {"is_24h_station": bool(role_spec["is_24h_station"])},
    }
    if not is_npc_on_active_shift(probe, eff_min, current_day=eff_day, scen_key=eff_scen, session_id=None)[0]:
        return None

    workplace_staff = db.get_world_roster(sid, workplace_node_id=nid, include_legacy_rosters=False) or []
    role_key = str(role_spec["role_key"])
    for existing in workplace_staff:
        ex_basic = existing.get("basic_info") if isinstance(existing.get("basic_info"), dict) else {}
        if str(existing.get("origin") or "").lower() == "role_slot_fill" and str(ex_basic.get("slot_fill_role_key") or "").lower() == role_key:
            if str(existing.get("staff_status") or "active").lower() != "active":
                return None
            on_shift, _ = is_npc_on_active_shift(existing, eff_min, current_day=eff_day, scen_key=eff_scen, session_id=sid)
            return existing if on_shift else None

    for existing in workplace_staff:
        if str(existing.get("staff_status") or "active").lower() == "active" and _staff_matches_requested_role(existing, role_spec, req):
            if is_npc_on_active_shift(existing, eff_min, current_day=eff_day, scen_key=eff_scen, session_id=sid)[0]:
                return existing

    taken_names, taken_ids = _collect_taken_names_and_ids(sid)
    role_slug = slugify_npc_id(role_key) or "staff"
    npc_id, name, gender = _generate_unique_seeded_profile(
        seed_base=f"{_get_session_seed(session, sid)}:{nid}:role:{role_slug}",
        scen_key=eff_scen, taken_names=taken_names, taken_ids=taken_ids,
        shift_profile=role_spec["shift_profile"], is_24h=bool(role_spec["is_24h_station"]),
        is_unique=False, facility_node_id=nid, check_open_day=eff_day,
    )
    payload = _build_roster_payload(
        npc_id=npc_id, name=name, gender=gender,
        role=role_spec["role"], occupation=role_spec["occupation"], origin="role_slot_fill",
        workplace_node_id=nid, shift_profile=role_spec["shift_profile"],
        merchant_archetypes=role_spec.get("merchant_archetypes") or (),
        venue_name=node_name, is_24h_station=bool(role_spec["is_24h_station"]),
        extra_basic_info={"slot_fill_role_key": role_key},
    )
    return db.upsert_world_roster_npc(sid, payload, turn_number=int(turn_number or 0))


def _check_world_event_market_bypass(
    session_id: int,
    resolved_node_id: str,
    node: dict[str, Any] | None,
    location_str: str,
    has_shop_keyword: bool,
    scen_key: str,
) -> dict[str, Any] | None:
    if session_id <= 0:
        return None
    try:
        events = db.get_world_events(session_id, entity_type="macro_event", include_hidden=False, statuses=("active",)) or []
    except (sqlite3.Error, ValueError, TypeError):
        return None

    parent_id = str((node or {}).get("parent_id") or "").strip()
    loc_low = str(location_str or "").strip().lower()
    node_name_low = str((node or {}).get("name") or "").strip().lower()
    valid_node_ids = {x for x in (resolved_node_id, parent_id) if x}

    for ev in events:
        if not isinstance(ev, dict):
            continue
        subtype = str(ev.get("event_subtype") or "").strip().lower()
        mods = ev.get("modifiers") if isinstance(ev.get("modifiers"), dict) else {}
        if subtype not in FESTIVAL_EVENT_SUBTYPES and not (mods.get("open_market") or mods.get("bypass_shop_closure")):
            continue

        ev_node = str(ev.get("location_node_id") or ev.get("target_node_id") or "").strip()
        ev_loc = str(ev.get("location_name") or "").strip().lower()
        matches_here = (
            (ev_node in valid_node_ids) if ev_node
            else ((ev_loc in loc_low or (loc_low and loc_low in ev_loc) or (node_name_low and (ev_loc in node_name_low or node_name_low in ev_loc)))
                  if ev_loc else (has_shop_keyword or is_node_staffable(node, scen_key=scen_key)))
        )
        if matches_here:
            title = str(ev.get("title") or "the local market festival").strip()
            return _availability_result(
                available=True, reason="world_event_bypass", facility_node_id=resolved_node_id,
                reason_message=f"Open-air stalls remain bustling throughout {title}, keeping wares available for trade.",
            )
    return None


def _spawn_replacement_hire(
    *,
    session_id: int,
    facility_node_id: str,
    node: dict[str, Any],
    casualties: list[dict[str, Any]],
    status_day: int,
    scen_key: str,
    session: dict[str, Any] | None,
    turn_number: int,
) -> dict[str, Any] | None:
    existing_all = db.get_world_roster(session_id, workplace_node_id=facility_node_id, include_legacy_rosters=False) or []
    for row in existing_all:
        r_basic = row.get("basic_info") if isinstance(row.get("basic_info"), dict) else {}
        if str(row.get("origin") or "").lower() == "replacement_hire" and str(row.get("staff_status") or "active").lower() == "active" and int(r_basic.get("replacement_for_day") or 0) == int(status_day):
            return row

    primary = casualties[0] if casualties else {}
    p_basic = primary.get("basic_info") if isinstance(primary.get("basic_info"), dict) else {}
    shift_profile = str(primary.get("shift_profile") or "day")
    if shift_profile not in ("day", "evening", "night", "student", "rotating"):
        shift_profile = "day"
    is_24h = bool(p_basic.get("is_24h_station"))
    node_name = str(node.get("name") or facility_node_id).strip()
    reopen_day = int(status_day) + 3

    taken_names, taken_ids = _collect_taken_names_and_ids(session_id)
    npc_id, name, gender = _generate_unique_seeded_profile(
        seed_base=f"{_get_session_seed(session, session_id)}:{facility_node_id}:replacement:{status_day}",
        scen_key=scen_key, taken_names=taken_names, taken_ids=taken_ids,
        shift_profile=shift_profile, is_24h=is_24h, is_unique=False,
        facility_node_id=facility_node_id, check_open_day=reopen_day,
    )
    payload = _build_roster_payload(
        npc_id=npc_id, name=name, gender=gender,
        role=str(primary.get("role") or p_basic.get("role") or "Shopkeeper"),
        occupation=str(p_basic.get("occupation") or "Shopkeeper"),
        origin="replacement_hire", workplace_node_id=facility_node_id,
        shift_profile=shift_profile,
        merchant_archetypes=list(p_basic.get("merchant_archetypes") or ("general_merchant", "food_merchant")),
        venue_name=node_name, staff_status_day=reopen_day, is_24h_station=is_24h,
        extra_basic_info={"replacement_for_day": int(status_day), "replaces_npc_id": str(primary.get("npc_id") or "")},
    )
    return db.upsert_world_roster_npc(session_id, payload, turn_number=int(turn_number or 0))


def heal_stale_civic_hq_staff(
    session_id: int,
    scen_key: str = "fantasy",
    *,
    roster: list[dict[str, Any]] | None = None,
    nodes_by_id: Mapping[str, dict[str, Any]] | None = None,
    contacts: list[dict[str, Any]] | None = None,
) -> int:
    """
    Strip stale `merchant_archetypes` from `origin="venue_seed"` roster rows anchored on
    civic or multi-wing HQ parent `FACILITY` nodes while preserving already-met contacts.
    """
    sid = int(session_id or 0)
    if sid <= 0:
        return 0
    eff_roster = roster if roster is not None else (db.get_world_roster(sid, include_legacy_rosters=False) or [])
    candidates = [
        r for r in eff_roster
        if isinstance(r, Mapping)
        and str(r.get("origin") or "").strip().lower() == "venue_seed"
        and str(r.get("workplace_node_id") or "").strip()
        and bool((r.get("basic_info") or {}).get("merchant_archetypes"))
    ]
    if not candidates:
        return 0

    eff_nodes = nodes_by_id
    if eff_nodes is None:
        eff_nodes = {
            str(n["node_id"]): n
            for n in (db.get_session_world_nodes(sid) or [])
            if isinstance(n, Mapping) and n.get("node_id")
        }

    hub_candidates: list[dict[str, Any]] = []
    for cand in candidates:
        w_nid = str(cand.get("workplace_node_id") or "").strip()
        w_node = eff_nodes.get(w_nid)
        if w_node and is_civic_or_multi_wing_hub_node(w_node, scen_key=scen_key):
            hub_candidates.append(dict(cand))
    if not hub_candidates:
        return 0

    eff_contacts = contacts if contacts is not None else (safe_get_contacts(sid, ensure_scene=False, resolve_relations=False) or [])
    met_keys: set[str] = set()
    for c in eff_contacts:
        if not isinstance(c, Mapping):
            continue
        for key_field in ("npc_id", "person_key", "name"):
            val = str(c.get(key_field) or "").strip().lower()
            if val:
                met_keys.add(val)

    healed = 0
    for row in hub_candidates:
        npc_id = str(row.get("npc_id") or "").strip()
        if not npc_id:
            continue
        npc_name = str(row.get("name") or "").strip().lower()
        is_met = bool(row.get("met_in_person")) or npc_id.lower() in met_keys or (npc_name and npc_name in met_keys)
        role_cur = str(row.get("role") or "").strip()
        if not is_met and role_cur in ("Quartermaster", "Guildmaster"):
            new_role, new_occ = "Duty Officer", "Duty Officer"
        else:
            new_role, new_occ = None, None
        if db.clear_roster_npc_merchant_archetypes(sid, npc_id, new_role=new_role, new_occupation=new_occ):
            healed += 1
    return healed


def _build_room_shop_probe_location(session_id: int, node: Mapping[str, Any], eff_loc: str = "") -> str:
    """Return a >=3-tier location string for strict leaf-room `location_has_merchant_shop` evaluation."""
    node_name = str(node.get("name") or "").strip()
    if eff_loc and ("➔" in eff_loc or "->" in eff_loc):
        parts = [p.strip() for p in re.split(r"➔|->", eff_loc) if p.strip()]
        if parts and (not node_name or parts[-1].lower() == node_name.lower()):
            return f"Zone ➔ {' ➔ '.join(parts)}" if len(parts) == 2 else eff_loc
    nid = str(node.get("node_id") or "").strip()
    if session_id > 0 and nid:
        ancestors = db.get_node_ancestors(session_id, nid) or []
        chain = [str(a.get("name") or "").strip() for a in reversed(ancestors) if a.get("name")]
        if node_name:
            chain.append(node_name)
        if len(chain) >= 3:
            return " ➔ ".join(chain)
        if len(chain) == 2:
            return f"Zone ➔ {chain[0]} ➔ {chain[1]}"
        if chain:
            return f"Zone ➔ Hub ➔ {chain[0]}"
    return f"Zone ➔ Hub ➔ {node_name}" if node_name else eff_loc


def _resolve_shop_context(
    session_id: int,
    location_str: str,
    facility_node_id: str,
    scen_key: str,
    current_day: int | None,
    current_minute: int | None,
    session: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, str, str, int, int, str, dict[str, Any] | None]:
    eff_session: dict[str, Any] | None = (
        dict(session)
        if isinstance(session, Mapping)
        else (db.get_session(session_id) if session_id > 0 else None)
    )
    eff_scen = str(scen_key or (eff_session or {}).get("scenario") or "fantasy").strip() or "fantasy"
    eff_loc = str(location_str or (eff_session or {}).get("current_location") or "").strip()

    if current_day is None or current_minute is None:
        db_day, db_min, _ = db.get_session_time(session_id) if session_id > 0 else (1, 480, 0)
        eff_day = int(db_day if current_day is None else current_day)
        eff_min = int(db_min if current_minute is None else current_minute)
    else:
        eff_day, eff_min = int(current_day), int(current_minute)

    resolved_node_id = str(facility_node_id or "").strip()
    node = db.get_world_node(session_id, resolved_node_id) if (session_id > 0 and resolved_node_id) else None
    if not resolved_node_id and session_id > 0:
        if eff_loc:
            resolved_node_id = str(db.resolve_node_id_from_location(session_id, eff_loc, prefer_facility=False) or "").strip()
        if not resolved_node_id and eff_session and (not location_str or eff_loc == str(eff_session.get("current_location") or "").strip()):
            resolved_node_id = str(eff_session.get("current_node_id") or "").strip()
        if not resolved_node_id and eff_loc:
            resolved_node_id = str(db.resolve_node_id_from_location(session_id, eff_loc, prefer_facility=True) or "").strip()
        if resolved_node_id:
            node = db.get_world_node(session_id, resolved_node_id)

    if resolved_node_id and session_id > 0 and node and str(node.get("node_type") or "").upper() == "ROOM":
        room_meta = parse_node_state(node)
        room_probe_loc = _build_room_shop_probe_location(session_id, node, eff_loc)
        is_priv_room = bool(room_meta.get("is_player_residence")) or str(node.get("privacy_level") or "").strip().lower() == "private"
        explicit_room_flag = bool(room_meta.get("has_merchant_shop") or room_meta.get("has_shop") or room_meta.get("is_minor_club_hq"))
        room_is_shop = False if room_meta.get("is_player_residence") else bool(
            explicit_room_flag
            or (not is_priv_room and bool(room_probe_loc) and location_has_merchant_shop(room_probe_loc, scen_key=eff_scen))
        )
        if room_is_shop and node.get("parent_id"):
            parent = db.get_world_node(session_id, str(node["parent_id"]))
            if (
                parent
                and str(parent.get("node_type") or "").upper() == "FACILITY"
                and not is_civic_or_multi_wing_hub_node(parent, eff_scen)
                and is_node_staffable(parent, eff_scen)
                and (
                    str(parent.get("category") or "").strip().lower() == "commercial"
                    or location_has_merchant_shop(str(parent.get("name") or ""), scen_key=eff_scen)
                )
                and not db.get_world_roster(session_id, workplace_node_id=resolved_node_id, include_legacy_rosters=False)
            ):
                node, resolved_node_id = parent, str(parent["node_id"])

    return eff_session, eff_scen, eff_loc, eff_day, eff_min, resolved_node_id, node


def _find_matching_active_roamer(
    session_id: int,
    resolved_node_id: str,
    eff_loc: str,
    eff_scen: str,
    eff_day: int,
    eff_min: int,
    merchant_type: str,
    node: Mapping[str, Any] | None = None,
    session: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    if isinstance(node, Mapping):
        if str(node.get("node_type") or "").strip().upper() == "ROOM":
            return None
        if is_civic_or_multi_wing_hub_node(node, eff_scen):
            return None
    node_name_low = str((node or {}).get("name") or "").strip().lower()
    eff_loc_low = str(eff_loc or "").strip().lower()
    if any(bad in node_name_low or bad in eff_loc_low for bad in ROAMER_EXCLUDE_KEYWORDS):
        return None

    present_names: set[str] = set()
    for npc in ((session or {}).get("current_npcs") or []):
        if isinstance(npc, Mapping):
            nm = str(npc.get("name") or "").strip().lower()
            if nm:
                present_names.add(nm)
        elif isinstance(npc, str) and npc.strip():
            present_names.add(npc.strip().lower())

    all_roster = db.get_world_roster(session_id, include_legacy_rosters=False) or []
    fallback_hit: dict[str, Any] | None = None
    for roamer in all_roster:
        roam_origin = str(roamer.get("origin") or "").lower()
        roam_shift = str(roamer.get("shift_profile") or "").lower()
        if (roam_origin != "roaming_merchant" and roam_shift != "street_vendor") or str(roamer.get("staff_status") or "active").lower() != "active":
            continue
        on_shift, active_node_id = is_npc_on_active_shift(roamer, eff_min, current_day=eff_day, scen_key=eff_scen, session_id=session_id)
        if not on_shift or not active_node_id:
            continue
        r_basic = roamer.get("basic_info") if isinstance(roamer.get("basic_info"), dict) else {}
        r_archs = set(r_basic.get("merchant_archetypes") or ())
        if merchant_type and r_archs and merchant_type not in r_archs:
            continue
        matched = bool(resolved_node_id and active_node_id == resolved_node_id)
        if not matched and not resolved_node_id and eff_loc:
            r_node = db.get_world_node(session_id, active_node_id)
            r_name = str((r_node or {}).get("name") or "").strip().lower()
            matched = bool(r_name and r_name in eff_loc.lower())
        if matched:
            roam_msg = (
                f"{roamer.get('name') or 'A nocturnal peddler'} slips open a wax-sealed satchel from a shadowy alcove."
                if r_basic.get("nocturnal")
                else (
                    f"{roamer.get('name') or 'A street vendor'} tends a bustling curb stall nearby."
                    if roam_shift == "street_vendor"
                    else f"{roamer.get('name') or 'A traveling merchant'} has set up a caravan display here for today's route."
                )
            )
            hit = _availability_result(
                available=True, reason="roaming_merchant", staff_npc=roamer, facility_node_id=active_node_id or resolved_node_id,
                reason_message=roam_msg,
            )
            r_disp = str(roamer.get("name") or "").strip().lower()
            if present_names and r_disp in present_names:
                return hit
            if fallback_hit is None:
                fallback_hit = hit
    return fallback_hit


def _evaluate_facility_staff(
    *,
    sid: int,
    resolved_node_id: str,
    node: dict[str, Any],
    session: dict[str, Any] | None,
    has_shop_keyword: bool,
    m_type: str,
    eff_scen: str,
    eff_day: int,
    eff_min: int,
    turn_number: int,
) -> tuple[dict[str, Any] | None, bool]:
    """Evaluate venue-seeded staff, casualties, and D+3 replacements; returns (decision_or_None, has_relevant_staff)."""
    ensure_venue_staff_seeded(sid, resolved_node_id, scen_key=eff_scen, current_day=eff_day, turn_number=turn_number, session=session)
    workplace_staff = db.get_world_roster(sid, workplace_node_id=resolved_node_id, include_legacy_rosters=False) or []

    node_meta = parse_node_state(node)
    has_merchant_staff = any(bool((r.get("basic_info") or {}).get("merchant_archetypes")) for r in workplace_staff)
    if not (has_shop_keyword or str(node.get("category") or "").strip().lower() == "commercial" or node_meta.get("has_shop") or has_merchant_staff):
        return _availability_result(available=False, reason="no_merchant", reason_message="No shop counter or merchant stall operates at this venue.", facility_node_id=resolved_node_id), False

    relevant_staff = (
        [r for r in workplace_staff if bool((r.get("basic_info") or {}).get("merchant_archetypes"))]
        if has_merchant_staff
        else list(workplace_staff)
    )
    if m_type:
        matched = [r for r in relevant_staff if m_type in ((r.get("basic_info") or {}).get("merchant_archetypes") or [])]
        if matched:
            relevant_staff = matched

    active_staff = [r for r in relevant_staff if str(r.get("staff_status") or "active").lower() == "active"]
    on_shift_staff = [s for s in active_staff if is_npc_on_active_shift(s, eff_min, current_day=eff_day, scen_key=eff_scen, session_id=sid)[0]]
    if on_shift_staff:
        chosen = next((s for s in on_shift_staff if str(s.get("origin") or "").lower() == "replacement_hire"), on_shift_staff[0])
        reason = "replacement_hired" if str(chosen.get("origin") or "").lower() == "replacement_hire" else "active_staff"
        return _availability_result(available=True, reason=reason, reason_message=f"{chosen.get('name') or 'The shopkeeper'} greets you from behind the counter.", staff_npc=chosen, facility_node_id=resolved_node_id), True

    casualties = [r for r in relevant_staff if str(r.get("staff_status") or "active").lower() != "active"]
    casualty_blocks = bool(casualties) and (
        not active_staff
        or any(is_npc_on_active_shift({**c, "staff_status": "active"}, eff_min, current_day=eff_day, scen_key=eff_scen, session_id=None)[0] for c in casualties)
    )
    if casualties and casualty_blocks:
        is_unique = any(bool(c.get("is_unique_proprietor") or (c.get("basic_info") or {}).get("is_unique_proprietor")) for c in casualties)
        latest_sd = max(int(c["staff_status_day"]) if (c.get("staff_status_day") is not None and int(c.get("staff_status_day") or 0) > 0) else eff_day for c in casualties)
        if is_unique or (eff_day - latest_sd) < 3:
            names = ", ".join(str(c.get("name") or "The proprietor") for c in casualties[:2])
            msg = (
                f"The shutters are drawn tightly and a solemn notice hangs outside — {names}'s establishment is permanently closed."
                if is_unique else f"Heavy wooden shutters bar the counter following {names}'s absence; the stall remains temporarily closed."
            )
            return _availability_result(available=False, reason="casualty_shuttered", reason_message=msg, facility_node_id=resolved_node_id), True

        replacement = _spawn_replacement_hire(
            session_id=sid, facility_node_id=resolved_node_id, node=node, casualties=casualties,
            status_day=latest_sd, scen_key=eff_scen, session=session, turn_number=turn_number,
        )
        if replacement is not None:
            rep_open = is_npc_on_active_shift(replacement, eff_min, current_day=eff_day, scen_key=eff_scen, session_id=sid)[0]
            if rep_open:
                return _availability_result(
                    available=True, reason="replacement_hired", staff_npc=replacement, facility_node_id=resolved_node_id,
                    reason_message=f"{replacement.get('name') or 'A new keeper'} has taken over the counter and gestures toward the open shelves.",
                ), True
            return _availability_result(
                available=False, reason="off_shift", staff_npc=replacement, facility_node_id=resolved_node_id,
                reason_message="The newly hired shopkeeper has closed for the night; the shutters are locked outside operating hours.",
            ), True

    from mechanics.social.town_roster import is_student_on_part_time_shift, remap_town_node_for_scenario

    all_roster_pt = db.get_world_roster(sid, include_legacy_rosters=False) or []
    for pt_cand in all_roster_pt:
        if str(pt_cand.get("origin") or "").strip().lower() != "campus_seed":
            continue
        if str(pt_cand.get("staff_status") or "active").strip().lower() != "active":
            continue
        pt_spec = is_student_on_part_time_shift(pt_cand, eff_day, eff_min, session_id=sid)
        if pt_spec and remap_town_node_for_scenario(str(pt_spec.get("venue_node_id") or ""), eff_scen) == resolved_node_id:
            return _availability_result(
                available=True,
                reason="part_time_staff",
                reason_message=f"{pt_cand.get('name') or 'A student part-timer'} waves from behind the counter.",
                staff_npc=pt_cand,
                facility_node_id=resolved_node_id,
            ), True

    return None, bool(relevant_staff)


_SCHOOL_CLUB_SHOP_NODE_IDS: frozenset[str] = frozenset({
    "loc_stuco_quartermaster",
    "loc_drama_wardrobe",
    "loc_athletics_equipment",
    "loc_nsfw_boutique",
    "loc_old_storage_3b",
    "loc_gaming_clubroom",
    "loc_behind_gym_sheds",
    "loc_delinquent_boiler_den",
})


def _evaluate_school_club_shop(
    *,
    sid: int,
    eff_session: dict[str, Any] | None,
    eff_scen: str,
    eff_loc: str,
    eff_min: int,
    resolved_node_id: str,
    node: dict[str, Any] | None,
    has_shop_keyword: bool,
) -> dict[str, Any] | None:
    """
    Evaluates access, rival turf locks, and campus hours for Major Club
    quartermasters and Minor Club all-in-one HQs without requiring commercial staff.
    """
    if not (is_school_scenario(eff_scen) or scenario_data.has_school_campus_mechanics(eff_scen)):
        return None

    room_nid = ""
    room_node = None
    if sid > 0 and eff_loc:
        room_nid = str(db.resolve_node_id_from_location(sid, eff_loc, prefer_facility=False) or "").strip()
        if room_nid:
            room_node = db.get_world_node(sid, room_nid)
    active_nid = room_nid or resolved_node_id
    active_node = room_node or node
    active_meta = parse_node_state(active_node) if active_node else {}
    loc_low = str(eff_loc or "").lower()
    leaf_low = str((active_node or {}).get("name") or "").strip().lower()
    if not leaf_low and "➔" in loc_low:
        leaf_low = loc_low.split("➔")[-1].strip()

    from mechanics.world.locations.attributes import DYNAMIC_MINOR_CLUB_ROOM_KEYWORDS

    is_club_shop = bool(
        active_nid in _SCHOOL_CLUB_SHOP_NODE_IDS
        or active_nid.startswith("sub_club_")
        or active_meta.get("is_minor_club_hq")
        or (active_meta.get("club_tier") == "major" and active_meta.get("has_merchant_shop"))
        or (
            has_shop_keyword
            and (
                any(
                    k in (leaf_low or loc_low)
                    for k in (
                        "council requisition", "requisition & supply",
                        "costume wardrobe & prop quartermaster", "prop quartermaster",
                        "varsity gear & training quartermaster", "training quartermaster",
                        "silk & curio apothecary", "velvet boutique",
                        "old storage room 3-b", "esports & gaming clubroom",
                        "behind gym storage sheds", "abandoned wing boiler-room den",
                        *DYNAMIC_MINOR_CLUB_ROOM_KEYWORDS,
                    )
                )
                or ("clubroom" in (leaf_low or loc_low) and "clubroom wing" not in (leaf_low or loc_low))
            )
        )
    )
    if not is_club_shop:
        return None

    club_fac = None
    if sid > 0:
        f_name_meta = str(active_meta.get("faction_name") or "").strip()
        if f_name_meta:
            club_fac = db.get_faction(sid, f_name_meta)
        if not club_fac and active_nid:
            club_fac = db.get_faction_by_hq(sid, active_nid)
        if not club_fac and eff_loc:
            club_fac = db.get_faction_by_hq(sid, eff_loc)
        if not club_fac and active_node and active_node.get("parent_id"):
            club_fac = db.get_faction_by_hq(sid, str(active_node["parent_id"]))

    if sid > 0 and club_fac:
        from mechanics.social.factions import check_rival_or_hostile_turf_block
        block_msg = check_rival_or_hostile_turf_block(
            sid,
            club_fac,
            user_id=(eff_session or {}).get("host_user_id"),
            session=eff_session,
        )
        if block_msg:
            return _availability_result(
                available=False,
                reason="rival_turf_barred",
                reason_message=block_msg,
                facility_node_id=active_nid or resolved_node_id,
            )

    fac_cat = str((club_fac or {}).get("category") or "").strip().lower()
    fac_tmpl = str((club_fac or {}).get("hierarchy_template") or "").strip().lower()
    is_unregulated = bool(
        active_nid in ("loc_behind_gym_sheds", "loc_delinquent_boiler_den", "loc_nsfw_boutique")
        or (active_node or {}).get("parent_id") == "loc_nsfw_club_facility"
        or fac_cat in ("delinquents", "nsfw_club")
        or fac_tmpl == "delinquents"
        or any(k in (leaf_low or loc_low) for k in ("behind gym", "boiler-room den", "silk & curio", "velvet basement", "apothecary counter"))
    )
    if is_unregulated:
        return _availability_result(
            available=True,
            reason="club_quartermaster",
            reason_message="The secret stash and barter counter are accessible.",
            facility_node_id=active_nid or resolved_node_id,
        )

    safe_min = int(eff_min if eff_min is not None else 600) % 1440
    if 420 <= safe_min < 1200:
        return _availability_result(
            available=True,
            reason="club_quartermaster",
            reason_message="The club quartermaster counter is open during campus hours.",
            facility_node_id=active_nid or resolved_node_id,
        )
    return _availability_result(
        available=False,
        reason="off_shift",
        reason_message="The club requisition counter is closed outside campus hours (07:00–20:00).",
        facility_node_id=active_nid or resolved_node_id,
    )


def evaluate_shop_staff_availability(
    session_id: int,
    location_str: str = "",
    facility_node_id: str = "",
    merchant_type: str = "",
    is_phone_shop: bool = False,
    scen_key: str = "fantasy",
    current_day: int | None = None,
    current_minute: int | None = None,
    turn_number: int = 0,
    session: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Evaluate closed-world shop availability using staff shift schedules, casualties, roamers,
    automated kiosks, phone delivery, and active festival world events.
    """
    sid = int(session_id or 0)
    if is_phone_shop:
        return _availability_result(available=True, reason="phone_shop", reason_message="Express E-Shop delivery is available around the clock.", facility_node_id=str(facility_node_id or ""))

    eff_session, eff_scen, eff_loc, eff_day, eff_min, resolved_node_id, node = _resolve_shop_context(
        sid, location_str, facility_node_id, scen_key, current_day, current_minute, session=session
    )
    if sid > 0:
        heal_stale_civic_hq_staff(sid, scen_key=eff_scen)
    is_room_node = isinstance(node, Mapping) and str(node.get("node_type") or "").strip().upper() == "ROOM"
    eff_loc_name = str((node or {}).get("name") or eff_loc or "").strip()
    if is_room_node:
        room_probe_loc = _build_room_shop_probe_location(sid, node, eff_loc)
        has_shop_keyword = bool(room_probe_loc and location_has_merchant_shop(room_probe_loc, scen_key=eff_scen))
    else:
        has_shop_keyword = bool(
            (eff_loc_name and location_has_merchant_shop(eff_loc_name, scen_key=eff_scen))
            or (eff_loc and location_has_merchant_shop(eff_loc, scen_key=eff_scen))
        )

    event_bypass = _check_world_event_market_bypass(sid, resolved_node_id, node, eff_loc, has_shop_keyword, eff_scen)
    if event_bypass is not None:
        return event_bypass

    if is_kiosk_location(eff_loc, node=node):
        return _availability_result(available=True, reason="kiosk_bypass", reason_message="An automated self-service kiosk hums softly, ready to dispense stock.", facility_node_id=resolved_node_id)

    club_shop_decision = _evaluate_school_club_shop(
        sid=sid,
        eff_session=eff_session,
        eff_scen=eff_scen,
        eff_loc=eff_loc,
        eff_min=eff_min,
        resolved_node_id=resolved_node_id,
        node=node,
        has_shop_keyword=has_shop_keyword,
    )
    if club_shop_decision is not None:
        return club_shop_decision

    world_nodes = db.get_session_world_nodes(sid) if sid > 0 else []
    if not world_nodes:
        merch_state = (eff_session or {}).get("merchant") if isinstance((eff_session or {}).get("merchant"), dict) else {}
        if has_shop_keyword or merch_state.get("is_faction_quartermaster") or (not eff_loc.strip() and bool(merch_state.get("available"))):
            return _availability_result(available=True, reason="legacy_no_graph", reason_message="A shop counter is open for trade.", facility_node_id=resolved_node_id)
        return _availability_result(available=False, reason="no_merchant", reason_message="No open shopkeeper or traveling merchant is stationed here.", facility_node_id=resolved_node_id)

    if is_room_node:
        room_meta = parse_node_state(node)
        is_priv_room = bool(room_meta.get("is_player_residence")) or str(node.get("privacy_level") or "").strip().lower() == "private"
        room_has_explicit_flag = bool(room_meta.get("has_merchant_shop") or room_meta.get("has_shop"))
        room_is_shop = False if room_meta.get("is_player_residence") else bool(
            room_has_explicit_flag or (not is_priv_room and (has_shop_keyword or room_meta.get("is_minor_club_hq")))
        )
        if not room_is_shop:
            return _availability_result(
                available=False,
                reason="no_merchant",
                reason_message="No open shopkeeper or traveling merchant is stationed here.",
                facility_node_id=resolved_node_id,
            )

    ensure_roaming_merchants_seeded(sid, scen_key=eff_scen, turn_number=turn_number, session=eff_session)
    m_type = str(merchant_type or "").strip()
    has_relevant_staff = False

    if resolved_node_id and node and is_node_staffable(node, scen_key=eff_scen):
        decision, has_relevant_staff = _evaluate_facility_staff(
            sid=sid, resolved_node_id=resolved_node_id, node=node, session=eff_session,
            has_shop_keyword=has_shop_keyword, m_type=m_type, eff_scen=eff_scen,
            eff_day=eff_day, eff_min=eff_min, turn_number=turn_number,
        )
        if decision is not None:
            if decision["reason"] == "no_merchant":
                roamer_hit = _find_matching_active_roamer(sid, resolved_node_id, eff_loc, eff_scen, eff_day, eff_min, m_type, node=node, session=eff_session)
                if roamer_hit is not None:
                    return roamer_hit
            return decision

    roamer_hit = _find_matching_active_roamer(sid, resolved_node_id, eff_loc, eff_scen, eff_day, eff_min, m_type, node=node, session=eff_session)
    if roamer_hit is not None:
        return roamer_hit

    if has_relevant_staff:
        return _availability_result(available=False, reason="off_shift", reason_message="The shutters are down and the counter is quiet — this shop is closed outside operating hours.", facility_node_id=resolved_node_id)

    return _availability_result(available=False, reason="no_merchant", reason_message="No open shopkeeper or traveling merchant is stationed here.", facility_node_id=resolved_node_id)


_CLOSED_SHOP_REASONS: frozenset[str] = frozenset({
    "off_shift",
    "casualty_shuttered",
    "turf_locked",
    "campus_curfew",
})

_OPEN_STAFF_OR_BYPASS_REASONS: frozenset[str] = frozenset({
    "club_quartermaster",
    "roaming_merchant",
    "world_event_bypass",
    "kiosk_bypass",
    "active_staff",
    "part_time_staff",
    "replacement_hired",
})


def resolve_scene_merchant_ui_state(
    session: Mapping[str, Any] | None,
    *,
    session_id: int | None = None,
    in_combat: bool = False,
    preloaded_shop_availability: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Canonical omnichannel resolver for scene-level merchant/shop UI state across
    Web API enrichment, Discord ChoiceView/SyncChoiceView, and closed-shop indicators.
    """
    sess = session if isinstance(session, Mapping) else {}
    sid = int(session_id if session_id is not None else (sess.get("id") or 0))
    current_loc = str(sess.get("current_location") or "").strip()
    scen_key = str(sess.get("scenario") or "fantasy").strip() or "fantasy"
    is_school = is_school_scenario(scen_key)

    if in_combat or not sess:
        return {
            "is_shop_venue": False,
            "available": False,
            "action_label": "Talk to Merchant",
            "shop_closed_visible": False,
            "shop_closed_reason": "",
            "shop_closed_message": "",
            "staff_npc": None,
            "shop_availability": None,
        }

    has_shop_loc = bool(current_loc and location_has_merchant_shop(current_loc, scen_key=scen_key))
    if preloaded_shop_availability is not None:
        shop_avail = dict(preloaded_shop_availability)
    else:
        shop_avail = evaluate_shop_staff_availability(
            sid,
            location_str=current_loc,
            merchant_type="",
            is_phone_shop=False,
            scen_key=scen_key,
            current_day=sess.get("current_day"),
            current_minute=sess.get("current_minute"),
            turn_number=int(sess.get("turn_count") or 0),
            session=sess,
        )

    reason = str(shop_avail.get("reason") or "")
    staff_npc = shop_avail.get("staff_npc") if isinstance(shop_avail.get("staff_npc"), Mapping) else None
    staff_name = str((staff_npc or {}).get("name") or "").strip()

    present_names: set[str] = set()
    for npc in (sess.get("current_npcs") or []):
        if isinstance(npc, Mapping):
            nm = str(npc.get("name") or "").strip().lower()
            if nm:
                present_names.add(nm)
        elif isinstance(npc, str) and npc.strip():
            present_names.add(npc.strip().lower())

    # Roaming merchants in populated outdoor scenes require actual presence in current_npcs.
    if reason == "roaming_merchant" and present_names and (not staff_name or staff_name.lower() not in present_names):
        shop_avail = _availability_result(
            available=False,
            reason="no_merchant",
            reason_message="No open shopkeeper or traveling merchant is stationed here.",
            facility_node_id=str(shop_avail.get("facility_node_id") or ""),
        )
        reason = "no_merchant"
        staff_npc = None
        staff_name = ""

    is_shop_venue = bool(
        has_shop_loc
        or reason in (
            "club_quartermaster",
            "kiosk_bypass",
            "world_event_bypass",
            "active_staff",
            "part_time_staff",
            "replacement_hired",
            *_CLOSED_SHOP_REASONS,
        )
    )

    is_open = bool(shop_avail.get("available"))
    roamer_or_staff_open = is_open and reason in _OPEN_STAFF_OR_BYPASS_REASONS

    show_merchant = False
    merchant_label = "Talk to Merchant"
    shop_closed_visible = False
    shop_closed_reason = ""
    shop_closed_message = ""

    if not is_open:
        show_merchant = False
        if reason in _CLOSED_SHOP_REASONS and is_shop_venue:
            shop_closed_visible = True
            shop_closed_reason = reason
            shop_closed_message = str(shop_avail.get("reason_message") or "")
    elif reason == "club_quartermaster":
        show_merchant = True
        merchant_label = "Visit Club Quartermaster"
    elif has_shop_loc or roamer_or_staff_open:
        show_merchant = True
        tpl_key, _ = select_venue_template(current_loc, scen_key=scen_key)
        loc_stores = get_available_merchant_types_for_location(current_loc, scen_key=scen_key) if current_loc else []
        is_multi_stall = (
            tpl_key in ("bazaar_hub", "bazaar_hub_school")
            or (isinstance(loc_stores, list) and len(loc_stores) > 2)
        )
        can_name_clerk = (
            bool(staff_name)
            and staff_name.lower() in present_names
            and reason not in ("kiosk_bypass", "world_event_bypass")
            and not is_multi_stall
        )
        if can_name_clerk:
            merchant_label = f"Trade with {staff_name}"
        elif is_school:
            merchant_label = "Visit Shop / Café"
        elif has_shop_loc or is_shop_venue:
            merchant_label = "Visit Market / Shop"
        else:
            merchant_label = "Talk to Merchant"

    return {
        "is_shop_venue": is_shop_venue,
        "available": show_merchant,
        "action_label": merchant_label,
        "shop_closed_visible": shop_closed_visible,
        "shop_closed_reason": shop_closed_reason,
        "shop_closed_message": shop_closed_message,
        "staff_npc": dict(staff_npc) if staff_npc is not None else None,
        "shop_availability": shop_avail,
    }


def format_venue_crowd_flavor(
    facility_node_id: str,
    location_str: str,
    scen_key: str,
    current_minute: int,
) -> str:
    """Pure atmospheric crowd flavor formatter (ZERO DB writes, ZERO roster/contact side effects)."""
    loc_label = str(location_str or facility_node_id or "").strip()
    block_key = get_time_block_key(int(current_minute if current_minute is not None else 600))
    return get_crowd_flavor_text(loc_label, scen_key or "fantasy", block_key)
