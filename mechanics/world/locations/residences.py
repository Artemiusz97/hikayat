from __future__ import annotations

"""
Lazy-materialized NPC Special Agent residences, residential safe-zone predicates,
unpurchased realty detection, and Spare Key visit helpers.
"""

import hashlib
import json
import re
from typing import Any, Mapping

import db

from .realty_catalog import (
    ALL_STATIC_RESIDENTIAL_FACILITY_IDS,
    SPARE_KEY_MIN_AFFINITY,
    STARTER_QUARTERS_MAP,
    compute_property_slot_bonus,
    find_realty_by_node_id,
    is_anomalous_realty_scenario,
    iter_session_realty_catalog,
    resolve_realty_entry,
    resolve_starter_quarters_spec,
)


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", str(text or "").lower()).strip()
    return re.sub(r"[-\s]+", "_", cleaned) or "npc"


def _as_session(session_id: int, session: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(session, Mapping) and session:
        return dict(session)
    if session_id:
        try:
            return db.get_session(int(session_id)) or {}
        except Exception:
            return {}
    return {}


def is_adult_special_agent_contact(contact: Mapping[str, Any] | None) -> bool:
    """
    Returns True if `contact` represents one of the 44 Adult Special Agents
    (and NOT a teen Student Special Agent or civilian).
    """
    if not isinstance(contact, Mapping):
        return False
    b_info = contact.get("basic_info")
    if isinstance(b_info, str):
        try:
            b_info = json.loads(b_info)
        except Exception:
            b_info = {}
    if not isinstance(b_info, Mapping):
        raw_json = contact.get("basic_info_json")
        if isinstance(raw_json, str) and raw_json.strip():
            try:
                b_info = json.loads(raw_json)
            except Exception:
                b_info = {}
    b = b_info if isinstance(b_info, Mapping) else {}

    is_special = bool(
        contact.get("is_special_agent")
        or b.get("is_special_agent")
        or contact.get("anomalous_npc_tag") == "special_agent"
        or b.get("anomalous_npc_tag") == "special_agent"
        or contact.get("social_role_type") == "special_agent"
        or b.get("social_role_type") == "special_agent"
    )
    if not is_special:
        return False

    age_grp = str(contact.get("age_group") or b.get("age_group") or "").strip().lower()
    is_student = bool(
        contact.get("is_student_agent")
        or b.get("is_student_agent")
        or contact.get("is_student_operative")
        or b.get("is_student_operative")
        or age_grp == "teen"
        or str(contact.get("social_role_type") or b.get("social_role_type") or "").strip().lower() == "student_peer"
    )
    return not is_student


def get_player_owned_or_starter_property_for_node(
    session_id: int,
    node_id: str,
    session: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    If `node_id` belongs to the player's active starter quarters, a Student Operative's
    Parents' House, or a permanently purchased deed, returns the enriched property dict.
    """
    target = str(node_id or "").strip()
    if not session_id or not target:
        return None
    sess = _as_session(session_id, session)
    scen_key = str(sess.get("scenario") or "")
    if not is_anomalous_realty_scenario(scen_key):
        if target in ("loc_player_house", "sub_player_front_porch", "sub_player_living_room", "sub_player_bedroom"):
            return {"property_id": "legacy_player_house", "facility_node_id": "loc_player_house", "tier": 0, "is_starter": 1}
        return None

    parent_id = ""
    try:
        w_node = db.get_world_node(int(session_id), target)
        if w_node:
            parent_id = str(w_node.get("parent_id") or "")
    except Exception:
        parent_id = ""

    props = db.get_player_properties(int(session_id))
    for p in props:
        fac_id = str(p.get("facility_node_id") or "")
        if target == fac_id or (parent_id and parent_id == fac_id):
            enriched = dict(p)
            if not enriched.get("is_starter"):
                cat = resolve_realty_entry(str(p.get("property_id") or ""), session_or_id=sess)
                if cat:
                    enriched["catalog_entry"] = cat
            return enriched
        if not p.get("is_starter"):
            cat = resolve_realty_entry(str(p.get("property_id") or ""), session_or_id=sess)
            if cat and target in cat.get("all_room_ids", ()):
                enriched = dict(p)
                enriched["catalog_entry"] = cat
                return enriched
        else:
            for st_spec in STARTER_QUARTERS_MAP.values():
                if st_spec["facility_node_id"] == fac_id and target in st_spec.get("all_room_ids", ()):
                    return dict(p)

    # Fallback when starter quarters row hasn't been persisted yet on an in-flight bootstrap
    if not props:
        f_state = sess.get("anomalous_faction_state") if isinstance(sess.get("anomalous_faction_state"), Mapping) else {}
        fk = str(
            (f_state or {}).get("faction_archetype_key")
            or sess.get("anomalous_starting_faction")
            or ("student_freelancer" if str(sess.get("origin_mode") or "").lower() == "student" else "public_agency")
        )
        st_spec = resolve_starter_quarters_spec(fk, session_or_id=sess)
        if target == st_spec["facility_node_id"] or parent_id == st_spec["facility_node_id"] or target in st_spec.get("all_room_ids", ()):
            return {
                "property_id": st_spec["property_id"],
                "facility_node_id": st_spec["facility_node_id"],
                "zone_id": st_spec["zone_id"],
                "tier": 0,
                "is_starter": 1,
                "is_primary": 1,
                "spare_keys": {},
            }

    # Student Operatives always retain access to Parents' House in Suburbs
    try:
        from mechanics.social.origin_mode import is_student_operative
        if is_student_operative(sess) and (
            target == "loc_player_house"
            or parent_id == "loc_player_house"
            or target in ("sub_player_front_porch", "sub_player_living_room", "sub_player_bedroom")
        ):
            return {
                "property_id": "starter_parents_house",
                "facility_node_id": "loc_player_house",
                "zone_id": "zone_suburbs",
                "tier": 0,
                "is_starter": 1,
                "is_primary": 0,
                "spare_keys": {},
            }
    except Exception:
        pass

    return None


def is_residential_safe_zone(
    session_id: int,
    node_id: str = "",
    location_str: str = "",
    session: Mapping[str, Any] | None = None,
) -> bool:
    """
    Returns True if the node/location is an owned or active starter safe residence for the player
    (immune to trespassing stealth triggers and eligible for safe rest).
    """
    nid = str(node_id or "").strip()
    if session_id and not nid and location_str:
        try:
            nid = db.resolve_node_id_from_location(int(session_id), location_str) or ""
        except Exception:
            nid = ""
    if session_id and nid:
        if get_player_owned_or_starter_property_for_node(int(session_id), nid, session=session) is not None:
            return True
    sess = _as_session(session_id, session)
    scen_key = str(sess.get("scenario") or "")
    if not is_anomalous_realty_scenario(scen_key):
        loc_low = str(location_str or "").lower()
        if nid.lower() in ("loc_player_house", "sub_player_bedroom") or "player's house" in loc_low or "player's bedroom" in loc_low:
            return True
    return False


def is_excluded_from_random_incursions(
    session_id: int,
    node_id: str = "",
    parent_id: str = "",
    location_str: str = "",
) -> bool:
    """
    Excludes all static starter/realty residential facilities and dynamic NPC residences
    from random daily Anomaly Breaches and routine Bounties.
    """
    nid = str(node_id or "").strip()
    loc_clean = str(location_str or "").strip()
    if session_id and not nid and loc_clean:
        try:
            nid = db.resolve_node_id_from_location(int(session_id), loc_clean, prefer_facility=True) or ""
        except Exception:
            nid = ""

    for candidate in (nid, str(parent_id or "").strip()):
        if not candidate:
            continue
        if candidate in ALL_STATIC_RESIDENTIAL_FACILITY_IDS or candidate in ("loc_hidden_kitsune_village", "loc_hidden_bunian_village"):
            return True
        low = candidate.lower()
        if low.startswith(("fac_npc_res_", "sub_npc_ent_", "sub_npc_bed_", "sub_agency_unit_", "sub_temple_cell_", "sub_kitsune_", "sub_bunian_")):
            return True
        if low.endswith("_house") or low.endswith("_apartment"):
            return True

    if loc_clean:
        parts = [p.strip() for p in loc_clean.replace("->", "➔").split("➔") if p.strip()]
        prim_low = (parts[1] if len(parts) >= 2 else parts[0]).lower() if parts else ""
        if prim_low:
            static_names = {
                str(v.get("name") or "").strip().lower()
                for v in list(STARTER_QUARTERS_MAP.values()) + list(iter_session_realty_catalog(session_id or None))
                if v.get("name")
            }
            static_names.update(
                {
                    "special agents' residential tower",
                    "walk-up apartment building",
                    "outer cloister initiate quarters",
                    "parents' house",
                    "player's house",
                    "detached suburban house",
                    "suburban corner townhouse",
                }
            )
            try:
                # Anomalous seed zones live in data/locations_seed.json (the old `seeds_anomalous`
                # module no longer exists, so this lookup previously failed silently every call).
                from .seeds import get_scenario_seed_data
                for _anom_scen in ("anomalous_incursions", "anomalous_high_school", "urban_anomalies"):
                    for z in (get_scenario_seed_data(_anom_scen) or {}).get("zones", []):
                        for fac in z.get("primary_locations", []):
                            if isinstance(fac, dict) and fac.get("id") in ALL_STATIC_RESIDENTIAL_FACILITY_IDS and fac.get("name"):
                                static_names.add(str(fac["name"]).strip().lower())
            except Exception:
                pass
            if prim_low in static_names:
                return True

    if session_id and (nid or loc_clean) and is_residential_safe_zone(int(session_id), node_id=nid, location_str=loc_clean):
        return True
    return False


def is_unpurchased_realty_node(
    session_id: int,
    node_id: str,
    session: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    If `node_id` is part of an unpurchased realty property in an Anomalous scenario,
    returns its resolved `REALTY_CATALOG` dict; otherwise returns `None`.
    """
    if not session_id or not node_id:
        return None
    sess = _as_session(session_id, session)
    if not is_anomalous_realty_scenario(str(sess.get("scenario") or "")):
        return None

    entry = find_realty_by_node_id(node_id, session_or_id=sess)
    if not entry:
        return None

    props = db.get_player_properties(int(session_id))
    for p in props:
        if not p.get("is_starter") and (
            p.get("property_id") == entry["property_id"]
            or p.get("facility_node_id") == entry["facility_node_id"]
        ):
            return None
    return entry


_TIER_PRIVATE_RESIDENCE_THEMES: dict[int, list[tuple[str, str, str, str]]] = {
    1: [
        ("zone_low_cost_wards", "The Lower Wards & Tenements", "{first}'s Tenement Safehouse", "Reinforced Studio Flat"),
        ("zone_chinatown", "Old Eastern Quarter & Night Market", "{first}'s Lantern-Alley Flat", "Timber Upper Studio"),
        ("zone_downtown", "Downtown", "{first}'s Walk-Up Apartment", "Third-Floor Studio Unit"),
        ("zone_city_docks", "City Docks & Harbor", "{first}'s Harbor Container Loft", "Converted Cargo Loft"),
    ],
    2: [
        ("zone_chinatown", "Old Eastern Quarter & Night Market", "{first}'s Shophouse Loft", "Lacquered Loft Bedroom"),
        ("zone_downtown", "Downtown", "{first}'s Brickstone Apartment", "Corner Loft Bedroom"),
        ("zone_city_docks", "City Docks & Harbor", "{first}'s Pierfront Flat", "Harbor-View Bedroom"),
        ("zone_low_cost_wards", "The Lower Wards & Tenements", "{first}'s Ironworks Loft", "Private Living Quarters"),
    ],
    3: [
        ("zone_uptown", "Uptown District", "{first}'s Uptown High-Rise Condo", "Skyline Master Suite"),
        ("zone_suburbs", "Suburban Residential District", "{first}'s Detached Townhouse", "Upstairs Master Bedroom"),
        ("zone_seaside_beach", "Seaside & Coastal Beach", "{first}'s Coastal Cliff Bungalow", "Surf-View Bedroom"),
    ],
    4: [
        ("zone_ultra_rich", "Sovereign Hills & Sky-Estates", "{first}'s Sovereign Hills Penthouse", "Penthouse Master Suite"),
        ("zone_eastern_sanctuary", "Sacred Mountain Sanctuary & Onsen Quarter", "{first}'s Mountain Cypress Villa", "Tatami Master Suite"),
    ],
    5: [
        ("zone_ultra_rich", "Sovereign Hills & Sky-Estates", "{first}'s Sovereign Sky-Estate", "Executive Penthouse Wing"),
    ],
}


def resolve_agent_residence_blueprint(
    session_id: int,
    npc_dict: Mapping[str, Any],
    scen_key: str = "",
) -> dict[str, Any]:
    """
    Deterministically computes the residence blueprint for any of the 60 Special Agents
    WITHOUT mutating the database on Turn 1:
    - 16 Teen Student Agents -> Parents' Family House in `zone_suburbs` (`cohabiting_family=True`).
    - 12 Adult `public_agency` Agents -> Solo billet unit inside `fac_agency_residence` (`zone_city_center`).
    - 8 Adult `monastic_order` Agents -> Solo cell/suite inside `fac_temple_residence` (`zone_woods_reserve`).
    - 24 Adult `private_agency_1/2`, `cult_faction`, `clandestine_faction` Agents -> Solo district-themed
      apartment/condo/penthouse scaled by `agent_tier` (1..5).
    """
    b_raw = npc_dict.get("basic_info")
    if isinstance(b_raw, str):
        try:
            b_raw = json.loads(b_raw)
        except Exception:
            b_raw = {}
    b = b_raw if isinstance(b_raw, Mapping) else {}

    full_name = str(npc_dict.get("name") or b.get("name") or "Special Agent").strip()
    parts = [p for p in full_name.split() if p]
    first_name = parts[0] if parts else "Agent"
    surname = parts[-1] if len(parts) >= 2 else first_name
    npc_id = str(npc_dict.get("npc_id") or b.get("npc_id") or _slugify(full_name)).strip()
    slug_npc = _slugify(npc_id or full_name)
    slug_surname = _slugify(surname)

    fac_id = str(
        npc_dict.get("faction_archetype_key")
        or npc_dict.get("faction_id")
        or b.get("faction_archetype_key")
        or b.get("faction_id")
        or "freelancer"
    ).strip().lower()
    tier = max(1, min(5, int(npc_dict.get("agent_tier") or b.get("agent_tier") or npc_dict.get("promotion_tier") or 1)))

    age_grp = str(npc_dict.get("age_group") or b.get("age_group") or "").strip().lower()
    is_teen_student = bool(
        npc_dict.get("is_student_agent")
        or b.get("is_student_agent")
        or npc_dict.get("is_student_operative")
        or b.get("is_student_operative")
        or age_grp == "teen"
    )

    h_bytes = hashlib.md5(f"{int(session_id or 1)}_{slug_npc}_{fac_id}".encode("utf-8")).hexdigest()
    h_int = int(h_bytes[:12], 16)

    if is_teen_student:
        fac_name = f"{surname} Family Residence"
        fac_nid = f"loc_{slug_surname}_house"
        ent_nid = f"sub_{slug_surname}_porch"
        living_nid = f"sub_{slug_surname}_living_room"
        bed_nid = f"sub_{slug_npc}_bedroom"
        bed_name = f"{first_name}'s Bedroom"
        return {
            "npc_id": npc_id,
            "npc_name": full_name,
            "zone_id": "zone_suburbs",
            "zone_name": "Suburban Residential District",
            "facility_node_id": fac_nid,
            "facility_name": fac_name,
            "entrance_node_id": ent_nid,
            "entrance_name": "Front Porch & Family Entryway",
            "extra_rooms": [(living_nid, "Family Living Room & Kitchen")],
            "bedroom_node_id": bed_nid,
            "bedroom_name": bed_name,
            "reuse_existing_facility": False,
            "cohabiting_family": True,
            "residence_display": f"Suburban Residential District ➔ {fac_name} ➔ {bed_name}",
        }

    if fac_id == "public_agency":
        unit_num = 101 + (h_int % 390)
        room_title = (
            f"{first_name}'s Senior Officer Quarters (Suite {unit_num})"
            if tier >= 4
            else f"{first_name}'s Private Billet (Unit {unit_num})"
        )
        bed_nid = f"sub_agency_unit_{slug_npc}"
        return {
            "npc_id": npc_id,
            "npc_name": full_name,
            "zone_id": "zone_city_center",
            "zone_name": "City Center",
            "facility_node_id": "fac_agency_residence",
            "facility_name": "Public Agency Residential Hall",
            "entrance_node_id": "sub_agency_res_lobby",
            "entrance_name": "Residential Security Lobby & Mailboxes",
            "extra_rooms": [],
            "bedroom_node_id": bed_nid,
            "bedroom_name": room_title,
            "reuse_existing_facility": True,
            "cohabiting_family": False,
            "residence_display": f"City Center ➔ Public Agency Residential Hall ➔ {room_title}",
        }

    if fac_id == "monastic_order":
        cell_label = (
            f"{first_name}'s Senior Abbot Cloister Suite"
            if tier >= 4
            else f"{first_name}'s Private Cloister Cell"
        )
        bed_nid = f"sub_temple_cell_{slug_npc}"
        return {
            "npc_id": npc_id,
            "npc_name": full_name,
            "zone_id": "zone_eastern_sanctuary",
            "zone_name": "Sacred Mountain Sanctuary & Onsen Quarter",
            "facility_node_id": "fac_temple_residence",
            "facility_name": "Outer Cloister Initiate Quarters",
            "entrance_node_id": "sub_temple_res_courtyard",
            "entrance_name": "Cloister Stepping-Stone Courtyard",
            "extra_rooms": [],
            "bedroom_node_id": bed_nid,
            "bedroom_name": cell_label,
            "reuse_existing_facility": True,
            "cohabiting_family": False,
            "residence_display": f"Sacred Mountain Sanctuary & Onsen Quarter ➔ Outer Cloister Initiate Quarters ➔ {cell_label}",
        }

    # Private Agencies, Cult, Clandestine, or Adult Freelancer: tier-scaled solo apartment/condo/penthouse
    pool = _TIER_PRIVATE_RESIDENCE_THEMES.get(tier, _TIER_PRIVATE_RESIDENCE_THEMES[2])
    z_id, z_name, fac_tmpl, bed_name = pool[h_int % len(pool)]
    fac_name = fac_tmpl.format(first=first_name, surname=surname)
    fac_nid = f"fac_npc_res_{slug_npc}"
    ent_nid = f"sub_npc_ent_{slug_npc}"
    bed_nid = f"sub_npc_bed_{slug_npc}"
    extra_rooms: list[tuple[str, str]] = []
    if tier >= 3:
        extra_rooms.append((f"sub_npc_lounge_{slug_npc}", "Private Lounge & Kitchenette"))

    return {
        "npc_id": npc_id,
        "npc_name": full_name,
        "zone_id": z_id,
        "zone_name": z_name,
        "facility_node_id": fac_nid,
        "facility_name": fac_name,
        "entrance_node_id": ent_nid,
        "entrance_name": "Private Entry Vestibule & Intercom",
        "extra_rooms": extra_rooms,
        "bedroom_node_id": bed_nid,
        "bedroom_name": bed_name,
        "reuse_existing_facility": False,
        "cohabiting_family": False,
        "residence_display": f"{z_name} ➔ {fac_name} ➔ {bed_name}",
    }


def ensure_npc_residence_materialized(
    session_id: int,
    npc_dict: Mapping[str, Any],
    scen_key: str = "",
) -> tuple[str, str]:
    """
    Lazily materializes an NPC Special Agent's private residence into `world_nodes`
    (uppercase `"FACILITY"` + `"ROOM"` with `is_entrance=1`), `world_edges` (bidirectional),
    and `session_locations` (`is_dynamic=1`) inside a single atomic `UnitOfWork`.
    Returns `(bedroom_node_id, tiered_location_display)`.
    """
    bp = resolve_agent_residence_blueprint(session_id, npc_dict, scen_key=scen_key)
    if not session_id:
        return bp["bedroom_node_id"], bp["residence_display"]

    existing_nodes = db.get_session_world_nodes(int(session_id)) or []
    node_map = {n["node_id"]: n for n in existing_nodes}
    z_id = bp["zone_id"]
    z_node = node_map.get(z_id)
    z_display = str(z_node["name"]) if z_node else bp["zone_name"]
    fac_id = bp["facility_node_id"]
    bed_id = bp["bedroom_node_id"]
    if bed_id in node_map and fac_id in node_map:
        fac_disp = str(node_map[fac_id]["name"])
        return bed_id, f"{z_display} ➔ {fac_disp} ➔ {bp['bedroom_name']}"

    with db.UnitOfWork():
        return _materialize_npc_residence_tx(int(session_id), bp, existing_nodes, node_map)


def _materialize_npc_residence_tx(
    session_id: int,
    bp: dict[str, Any],
    existing_nodes: list[dict[str, Any]],
    node_map: dict[str, dict[str, Any]],
) -> tuple[str, str]:
    z_id = bp["zone_id"]
    z_node = node_map.get(z_id)
    z_display = str(z_node["name"]) if z_node else bp["zone_name"]

    fac_id = bp["facility_node_id"]
    fac_name = bp["facility_name"]
    ent_id = bp["entrance_node_id"]
    bed_id = bp["bedroom_node_id"]

    if bp["reuse_existing_facility"] and fac_id in node_map:
        fac_name = str(node_map[fac_id]["name"])
        if bed_id not in node_map:
            db.save_world_node(
                session_id=int(session_id),
                node_id=bed_id,
                parent_id=fac_id,
                name=bp["bedroom_name"],
                node_type="ROOM",
                category="residential",
                privacy_level="private",
                is_enclosed=1,
                is_transit_hub=0,
                access_tier="private",
                is_dynamic=1,
                state_json={
                    "privacy_level": "private",
                    "is_private_intimate": True,
                    "owner_npc_id": bp["npc_id"],
                    "owner_npc_name": bp["npc_name"],
                },
            )
            if ent_id in node_map:
                db.save_world_edge(
                    int(session_id),
                    ent_id,
                    bed_id,
                    travel_minutes=1,
                    edge_type="door",
                    is_bidirectional=1,
                )
            else:
                db.save_world_edge(
                    int(session_id),
                    fac_id,
                    bed_id,
                    travel_minutes=1,
                    edge_type="door",
                    is_bidirectional=1,
                )
        db.save_session_location(
            session_id=int(session_id),
            location_id=bed_id,
            zone_name=z_display,
            primary_name=fac_name,
            sub_name=bp["bedroom_name"],
            is_dynamic=1,
        )
        return bed_id, f"{z_display} ➔ {fac_name} ➔ {bp['bedroom_name']}"

    # Standalone dynamic residential facility + entrance room + interior rooms
    if fac_id not in node_map:
        db.save_world_node(
            session_id=int(session_id),
            node_id=fac_id,
            parent_id=z_id if z_node else None,
            name=fac_name,
            node_type="FACILITY",
            category="residential",
            privacy_level="private",
            is_enclosed=1,
            is_transit_hub=0,
            access_tier="private",
            is_dynamic=1,
            state_json={
                "privacy_level": "private",
                "owner_npc_id": bp["npc_id"],
                "owner_npc_name": bp["npc_name"],
            },
        )
        sibling_facs = [
            n["node_id"]
            for n in existing_nodes
            if n.get("node_type") == "FACILITY" and n.get("parent_id") == z_id and n["node_id"] != fac_id
        ]
        for sf_id in sibling_facs[:2]:
            db.save_world_edge(
                int(session_id),
                fac_id,
                sf_id,
                travel_minutes=5,
                edge_type="pathway",
                is_bidirectional=1,
            )

    if ent_id not in node_map:
        db.save_world_node(
            session_id=int(session_id),
            node_id=ent_id,
            parent_id=fac_id,
            name=bp["entrance_name"],
            node_type="ROOM",
            category="residential",
            privacy_level="public",
            is_enclosed=1,
            is_transit_hub=0,
            access_tier="private",
            is_dynamic=1,
            state_json={
                "is_entrance": 1,
                "owner_npc_id": bp["npc_id"],
                "owner_npc_name": bp["npc_name"],
            },
        )
        db.save_world_edge(
            int(session_id),
            fac_id,
            ent_id,
            travel_minutes=1,
            edge_type="door",
            is_bidirectional=1,
        )
        sibling_entrances = [
            n["node_id"]
            for n in existing_nodes
            if n.get("node_type") == "ROOM"
            and n.get("parent_id") in {
                sf["node_id"]
                for sf in existing_nodes
                if sf.get("node_type") == "FACILITY" and sf.get("parent_id") == z_id and sf["node_id"] != fac_id
            }
            and (
                (isinstance(n.get("state_json"), str) and '"is_entrance": 1' in str(n.get("state_json")))
                or "entrance" in str(n.get("name") or "").lower()
                or "lobby" in str(n.get("name") or "").lower()
                or "porch" in str(n.get("name") or "").lower()
            )
        ]
        for se_id in sibling_entrances[:2]:
            db.save_world_edge(
                int(session_id),
                ent_id,
                se_id,
                travel_minutes=4,
                edge_type="pathway",
                is_bidirectional=1,
            )

    db.save_session_location(
        session_id=int(session_id),
        location_id=ent_id,
        zone_name=z_display,
        primary_name=fac_name,
        sub_name=bp["entrance_name"],
        is_dynamic=1,
    )

    for ex_id, ex_name in bp.get("extra_rooms", []):
        if ex_id not in node_map:
            db.save_world_node(
                session_id=int(session_id),
                node_id=ex_id,
                parent_id=fac_id,
                name=ex_name,
                node_type="ROOM",
                category="residential",
                privacy_level="private",
                is_enclosed=1,
                is_transit_hub=0,
                access_tier="private",
                is_dynamic=1,
                state_json={"privacy_level": "private", "owner_npc_id": bp["npc_id"]},
            )
            db.save_world_edge(
                int(session_id),
                ent_id,
                ex_id,
                travel_minutes=1,
                edge_type="door",
                is_bidirectional=1,
            )
        db.save_session_location(
            session_id=int(session_id),
            location_id=ex_id,
            zone_name=z_display,
            primary_name=fac_name,
            sub_name=ex_name,
            is_dynamic=1,
        )

    if bed_id not in node_map:
        db.save_world_node(
            session_id=int(session_id),
            node_id=bed_id,
            parent_id=fac_id,
            name=bp["bedroom_name"],
            node_type="ROOM",
            category="residential",
            privacy_level="private",
            is_enclosed=1,
            is_transit_hub=0,
            access_tier="private",
            is_dynamic=1,
            state_json={
                "privacy_level": "private",
                "is_private_intimate": True,
                "owner_npc_id": bp["npc_id"],
                "owner_npc_name": bp["npc_name"],
            },
        )
        db.save_world_edge(
            int(session_id),
            ent_id,
            bed_id,
            travel_minutes=1,
            edge_type="door",
            is_bidirectional=1,
        )
        for ex_id, _ in bp.get("extra_rooms", []):
            db.save_world_edge(
                int(session_id),
                ex_id,
                bed_id,
                travel_minutes=1,
                edge_type="door",
                is_bidirectional=1,
            )

    db.save_session_location(
        session_id=int(session_id),
        location_id=bed_id,
        zone_name=z_display,
        primary_name=fac_name,
        sub_name=bp["bedroom_name"],
        is_dynamic=1,
    )
    return bed_id, f"{z_display} ➔ {fac_name} ➔ {bp['bedroom_name']}"


def is_npc_active_spare_key_holder(
    session_id: int,
    npc_ref: str | Mapping[str, Any],
    spare_keys: Mapping[str, Any] | None,
) -> bool:
    """
    Returns True if `npc_ref` holds a Spare Key in `spare_keys`, is NOT deceased,
    and remains non-hostile and eligible (Affinity >= SPARE_KEY_MIN_AFFINITY or active romantic tie/status).
    """
    if not session_id or not spare_keys:
        return False

    if isinstance(npc_ref, Mapping):
        b_raw = npc_ref.get("basic_info")
        if isinstance(b_raw, str):
            try:
                b_raw = json.loads(b_raw)
            except Exception:
                b_raw = {}
        b = b_raw if isinstance(b_raw, Mapping) else {}
        if (
            npc_ref.get("is_deceased")
            or b.get("is_deceased")
            or b.get("deceased")
            or str(b.get("status") or "").strip().lower() == "deceased"
        ):
            return False
        npc_id = str(npc_ref.get("npc_id") or b.get("npc_id") or "").strip().lower()
        npc_name = str(npc_ref.get("name") or b.get("name") or "").strip().lower()
    else:
        raw_str = str(npc_ref or "").strip().lower()
        npc_id = raw_str
        npc_name = raw_str

    slug_name = _slugify(npc_name) if npc_name else ""
    cand_ids = {x for x in (npc_id, npc_name, slug_name) if x}
    if not cand_ids:
        return False

    key_lows = {str(k).strip().lower() for k in spare_keys.keys() if str(k).strip()}
    matched_c: dict[str, Any] | None = None
    try:
        contacts = db.get_contacts(int(session_id)) or []
    except Exception:
        contacts = []
    for c in contacts:
        cid_l = str(c.get("npc_id") or "").strip().lower()
        cnm_l = str(c.get("name") or "").strip().lower()
        cslug = _slugify(cnm_l) if cnm_l else ""
        c_aliases = {x for x in (cid_l, cnm_l, cslug) if x}
        if c_aliases & cand_ids:
            matched_c = dict(c)
            cand_ids.update(c_aliases)
            break

    if not (key_lows & cand_ids):
        return False

    if matched_c is not None:
        cb_raw = matched_c.get("basic_info")
        if isinstance(cb_raw, str):
            try:
                cb_raw = json.loads(cb_raw)
            except Exception:
                cb_raw = {}
        cb = cb_raw if isinstance(cb_raw, Mapping) else {}
        if (
            matched_c.get("is_deceased")
            or cb.get("is_deceased")
            or cb.get("deceased")
            or str(cb.get("status") or "").strip().lower() == "deceased"
        ):
            return False
        if str(matched_c.get("race") or cb.get("race") or "").strip().lower() == "kitsune:myobu_fox":
            return False
        score = int(matched_c.get("relationship_score") or 0)
        if score < 0:
            return False
        track = str(matched_c.get("track") or "").strip().lower()
        r_stat = str(cb.get("romantic_status") or cb.get("relationship_status") or "").strip().lower()
        is_rom = track in ("romantic", "lover", "partner", "spouse", "married", "dating", "fiance", "fiancee") or r_stat in (
            "dating", "romantic", "lover", "partner", "engaged", "married", "spouse", "boyfriend", "girlfriend"
        )
        if not is_rom:
            try:
                import mechanics.social.relationship_graph as rg
                ties = rg.get_person_ties(int(session_id), "player") if hasattr(rg, "get_person_ties") else []
                for t in (ties or []):
                    t_type = str(t.get("tie_type") or "").strip().lower()
                    if t.get("status") == "active" and t_type in ("romantic", "dating", "partner", "lover", "engaged", "married", "spouse"):
                        other_nm = str(t.get("other_display_name") or t.get("person_b_key") or t.get("person_a_key") or "").strip().lower()
                        if other_nm and other_nm in cand_ids:
                            is_rom = True
                            break
            except Exception:
                pass
        if score < SPARE_KEY_MIN_AFFINITY and not is_rom:
            return False

    return True


def resolve_spare_key_evening_visit_node(
    session_id: int,
    npc_dict: Mapping[str, Any],
    current_day: int,
    slot_key: str,
) -> str | None:
    """
    If the player's Primary Home is a permanently purchased deed (`is_starter == 0`)
    and `npc_dict` holds a Spare Key on that deed, returns the Primary Home's entrance/lounge/bedroom
    node for 25% of deterministic `evening` / Sunday `afternoon` slots.
    """
    if not session_id or slot_key not in ("evening", "afternoon"):
        return None
    if slot_key == "afternoon" and (max(1, int(current_day or 1)) % 7) != 0:
        return None
    try:
        prim = db.get_primary_property(int(session_id))
    except Exception:
        prim = None
    if not prim or prim.get("is_starter"):
        return None
    spare_keys = prim.get("spare_keys") or {}
    if not is_npc_active_spare_key_holder(int(session_id), npc_dict, spare_keys):
        return None

    b_raw = npc_dict.get("basic_info")
    if isinstance(b_raw, str):
        try:
            b_raw = json.loads(b_raw)
        except Exception:
            b_raw = {}
    b = b_raw if isinstance(b_raw, Mapping) else {}
    npc_id = str(npc_dict.get("npc_id") or b.get("npc_id") or "").strip().lower()
    npc_name = str(npc_dict.get("name") or b.get("name") or "").strip().lower()
    slug_name = _slugify(npc_name)

    roll_seed = hashlib.md5(
        f"spare_key_visit_{session_id}_{npc_id or slug_name}_{current_day}_{slot_key}".encode("utf-8")
    ).hexdigest()
    if (int(roll_seed[:8], 16) % 4) != 0:
        return None

    cat = resolve_realty_entry(str(prim.get("property_id") or ""), session_or_id=session_id)
    if cat:
        rooms = list(cat.get("all_room_ids") or ())
        if len(rooms) >= 2:
            # Prefer parlor/lounge/living room over raw doorstep when visiting with a spare key
            return rooms[1]
        return str(cat.get("bedroom_node_id") or prim.get("facility_node_id") or "")
    return str(prim.get("facility_node_id") or "")


def build_realty_payload(
    session_id: int,
    user_id: int | None = None,
) -> dict[str, Any]:
    """
    Omnichannel domain payload builder for Smartphone Realty (FastAPI + Discord).
    Returns owned residences, starter quarters, 9-deed market catalog, inventory slot
    bonuses, and contacts eligible for Spare Keys (affinity >= 70 or romantic partners).
    """
    import character_data as cd

    sess = _as_session(int(session_id)) if session_id else {}
    scen_key = str(sess.get("scenario") or "fantasy")
    enabled = is_anomalous_realty_scenario(scen_key)

    eff_uid = int(user_id or sess.get("host_user_id") or 0)
    char = None
    if eff_uid:
        try:
            char = db.get_character(eff_uid)
        except Exception:
            char = None
    if not char and session_id:
        try:
            party_chars = db.get_session_characters(int(session_id))
            if party_chars:
                char = dict(party_chars[0])
                eff_uid = int(char.get("user_id") or eff_uid or 0)
        except Exception:
            char = None

    char_dict = dict(char) if char else {"str_": 1, "gold": 0}
    gold = int(char_dict.get("gold") or 0)
    base_slots = cd.inventory_capacity(int(char_dict.get("str_", 1) or 1), bonus_slots=0)
    max_slots = (
        db.get_character_inventory_capacity(eff_uid, char=char_dict, session_id=int(session_id))
        if (eff_uid and session_id)
        else base_slots
    )

    if not enabled or not session_id:
        return {
            "enabled": False,
            "session_id": int(session_id or 0),
            "scenario": scen_key,
            "gold": gold,
            "base_inventory_slots": base_slots,
            "max_inventory_slots": max_slots,
            "property_slot_bonus": 0,
            "starter_quarters": None,
            "owned_properties": [],
            "catalog": [],
            "eligible_spare_key_contacts": [],
        }

    # Ensure starter quarters row is seeded if missing on an active anomalous session
    raw_props = db.get_player_properties(int(session_id))
    if not any(p.get("is_starter") for p in raw_props):
        try:
            db.grant_or_relocate_starter_quarters(int(session_id))
            raw_props = db.get_player_properties(int(session_id))
        except Exception:
            pass

    contacts = db.get_contacts(int(session_id)) or []
    contacts_by_key: dict[str, dict[str, Any]] = {}
    eligible_contacts: list[dict[str, Any]] = []

    romantic_person_names: set[str] = set()
    try:
        import mechanics.social.relationship_graph as rg
        ties = rg.get_person_ties(int(session_id), "player") if hasattr(rg, "get_person_ties") else []
        for t in (ties or []):
            t_type = str(t.get("tie_type") or "").strip().lower()
            if t.get("status") == "active" and t_type in ("romantic", "dating", "partner", "lover", "engaged", "married", "spouse"):
                other_nm = str(t.get("other_display_name") or t.get("person_b_key") or t.get("person_a_key") or "").strip().lower()
                if other_nm:
                    romantic_person_names.add(other_nm)
    except Exception:
        pass

    for c in contacts:
        c_dict = dict(c)
        c_name = str(c_dict.get("name") or "").strip()
        if not c_name:
            continue
        b_info = c_dict.get("basic_info")
        if isinstance(b_info, str):
            try:
                b_info = json.loads(b_info)
            except Exception:
                b_info = {}
        if not isinstance(b_info, Mapping):
            b_info = {}
        if str(c_dict.get("race") or b_info.get("race") or "").strip().lower() == "kitsune:myobu_fox":
            continue
        if b_info.get("is_deceased") or c_dict.get("is_deceased") or b_info.get("is_dispatch_channel"):
            continue

        c_id = str(c_dict.get("npc_id") or b_info.get("npc_id") or _slugify(c_name)).strip()
        contacts_by_key[c_id.lower()] = c_dict
        contacts_by_key[c_name.lower()] = c_dict
        contacts_by_key[_slugify(c_name)] = c_dict

        rel_score = int(c_dict.get("relationship_score") or 0)
        track = str(c_dict.get("track") or "").strip().lower()
        r_stat = str(b_info.get("romantic_status") or b_info.get("relationship_status") or "").strip().lower()
        is_rom = (
            track in ("romantic", "lover", "partner", "spouse", "married", "dating", "fiance", "fiancee")
            or r_stat in ("dating", "romantic", "lover", "partner", "engaged", "married", "spouse", "boyfriend", "girlfriend")
            or c_name.lower() in romantic_person_names
            or c_id.lower() in romantic_person_names
        )
        if rel_score >= SPARE_KEY_MIN_AFFINITY or is_rom:
            eligible_contacts.append({
                "npc_id": c_id,
                "name": c_name,
                "relationship_score": rel_score,
                "is_romantic": is_rom,
            })

    eligible_contacts.sort(key=lambda x: (-1 if x["is_romantic"] else 0, -x["relationship_score"], x["name"].lower()))

    def _hydrate_key_holders(spare_map: Mapping[str, Any]) -> list[dict[str, Any]]:
        holders: list[dict[str, Any]] = []
        for raw_k, granted_turn in (spare_map or {}).items():
            k_str = str(raw_k or "").strip()
            if not k_str:
                continue
            matched_c = (
                contacts_by_key.get(k_str.lower())
                or contacts_by_key.get(_slugify(k_str))
            )
            holders.append({
                "npc_id": k_str,
                "name": str(matched_c.get("name") if matched_c else k_str.replace("_", " ").title()),
                "relationship_score": int(matched_c.get("relationship_score") or 0) if matched_c else 0,
                "granted_turn": int(granted_turn or 0),
            })
        return holders

    starter_spec = resolve_starter_quarters_spec(sess)
    starter_payload: dict[str, Any] | None = None
    owned_list: list[dict[str, Any]] = []
    owned_by_prop_id: dict[str, dict[str, Any]] = {}
    owned_tiers: list[int] = []

    for row in raw_props:
        pid = str(row.get("property_id") or "")
        if row.get("is_starter"):
            spec = next(
                (v for v in STARTER_QUARTERS_MAP.values() if v["property_id"] == pid),
                starter_spec,
            ) or {}
            starter_payload = {
                **row,
                "name": str(spec.get("name") or "Assigned Starter Quarters"),
                "room_name": str(spec.get("room_name") or "Private Room"),
                "zone_name": str(spec.get("zone_name") or ""),
                "bedroom_node_id": str(spec.get("bedroom_node_id") or row.get("facility_node_id") or ""),
                "description": str(spec.get("description") or ""),
                "base_slots": 0,
                "cha_invite_dc_mod": 0,
                "rest_multiplier": 1.0,
                "hangout_affinity_bonus": 0,
                "can_grant_spare_key": False,
                "spare_key_holders": [],
            }
        else:
            cat = resolve_realty_entry(pid, session_or_id=sess) or {}
            t_val = int(row.get("tier") or cat.get("tier") or 1)
            owned_tiers.append(t_val)
            holders = _hydrate_key_holders(row.get("spare_keys") or {})
            enriched_deed = {
                **row,
                "name": str(cat.get("name") or pid),
                "zone_name": str(cat.get("zone_name") or ""),
                "bedroom_node_id": str(cat.get("bedroom_node_id") or row.get("facility_node_id") or ""),
                "description": str(cat.get("theme_blurb") or ""),
                "base_slots": int(cat.get("base_slots") or 0),
                "cha_invite_dc_mod": int(cat.get("cha_invite_dc_mod") or 0),
                "rest_multiplier": float(cat.get("rest_multiplier") or 1.0),
                "hangout_affinity_bonus": int(cat.get("hangout_affinity_bonus") or 0),
                "can_grant_spare_key": True,
                "spare_key_holders": holders,
            }
            owned_list.append(enriched_deed)
            owned_by_prop_id[pid] = enriched_deed

    slot_bonus = compute_property_slot_bonus(owned_tiers)

    catalog_list: list[dict[str, Any]] = []
    for entry in iter_session_realty_catalog(sess):
        pid = entry["property_id"]
        owned_row = owned_by_prop_id.get(pid)
        catalog_list.append({
            "property_id": pid,
            "name": entry["name"],
            "tier": int(entry["tier"]),
            "price": int(entry["price"]),
            "zone_id": entry["zone_id"],
            "zone_name": entry.get("zone_name", ""),
            "facility_node_id": entry["facility_node_id"],
            "entrance_node_id": entry["entrance_node_id"],
            "bedroom_node_id": entry["bedroom_node_id"],
            "base_slots": int(entry.get("base_slots") or 0),
            "cha_invite_dc_mod": int(entry.get("cha_invite_dc_mod") or 0),
            "rest_multiplier": float(entry.get("rest_multiplier") or 1.0),
            "hangout_affinity_bonus": int(entry.get("hangout_affinity_bonus") or 0),
            "description": entry.get("theme_blurb", ""),
            "is_owned": bool(owned_row),
            "is_primary": bool(owned_row and owned_row.get("is_primary")),
            "can_afford": bool(gold >= int(entry["price"])),
            "spare_key_holders": owned_row.get("spare_key_holders", []) if owned_row else [],
        })

    return {
        "enabled": True,
        "session_id": int(session_id),
        "scenario": scen_key,
        "gold": gold,
        "base_inventory_slots": base_slots,
        "max_inventory_slots": max_slots,
        "property_slot_bonus": slot_bonus,
        "starter_quarters": starter_payload,
        "owned_properties": owned_list,
        "catalog": catalog_list,
        "eligible_spare_key_contacts": eligible_contacts,
    }
