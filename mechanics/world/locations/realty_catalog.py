from __future__ import annotations

"""
Static catalog and deterministic perk math for Faction Starter Quarters and
Purchasable Properties in Anomalous Incursions & Anomalous High School.
"""

from typing import Any, Mapping

TIER_BASE_SLOTS: dict[int, int] = {
    0: 0,
    1: 5,
    2: 10,
    3: 18,
}

MAX_PROPERTY_SLOT_BONUS: int = 25
EXTRA_DEED_SLOT_BONUS: int = 2
SPARE_KEY_MIN_AFFINITY: int = 70


STARTER_QUARTERS_MAP: dict[str, dict[str, Any]] = {
    "public_agency": {
        "property_id": "starter_public_agency",
        "faction_key": "public_agency",
        "zone_id": "zone_city_center",
        "zone_name": "City Center",
        "facility_node_id": "fac_agency_residence",
        "entrance_node_id": "sub_agency_res_lobby",
        "bedroom_node_id": "sub_agency_res_unit",
        "name": "Public Agency Residential Hall",
        "room_name": "Assigned Agent Private Quarters",
        "all_room_ids": (
            "sub_agency_res_lobby",
            "sub_agency_res_lounge",
            "sub_agency_res_unit",
        ),
        "description": "Humble private billet assigned to active Civil Containment special agents and support staff.",
    },
    "private_agency_1": {
        "property_id": "starter_downtown_walkup",
        "faction_key": "private_agency_1",
        "zone_id": "zone_downtown",
        "zone_name": "Downtown",
        "facility_node_id": "fac_downtown_walkup",
        "entrance_node_id": "sub_walkup_stairwell",
        "bedroom_node_id": "sub_walkup_studio",
        "name": "Modest Rented Walk-Up Apartment",
        "room_name": "Rented Studio Unit",
        "all_room_ids": (
            "sub_walkup_stairwell",
            "sub_walkup_studio",
        ),
        "description": "Compact third-floor brick walk-up studio above a quiet Downtown side street.",
    },
    "private_agency_2": {
        "property_id": "starter_downtown_walkup",
        "faction_key": "private_agency_2",
        "zone_id": "zone_downtown",
        "zone_name": "Downtown",
        "facility_node_id": "fac_downtown_walkup",
        "entrance_node_id": "sub_walkup_stairwell",
        "bedroom_node_id": "sub_walkup_studio",
        "name": "Modest Rented Walk-Up Apartment",
        "room_name": "Rented Studio Unit",
        "all_room_ids": (
            "sub_walkup_stairwell",
            "sub_walkup_studio",
        ),
        "description": "Compact third-floor brick walk-up studio above a quiet Downtown side street.",
    },
    "freelancer": {
        "property_id": "starter_downtown_walkup",
        "faction_key": "freelancer",
        "zone_id": "zone_downtown",
        "zone_name": "Downtown",
        "facility_node_id": "fac_downtown_walkup",
        "entrance_node_id": "sub_walkup_stairwell",
        "bedroom_node_id": "sub_walkup_studio",
        "name": "Modest Rented Walk-Up Apartment",
        "room_name": "Rented Studio Unit",
        "all_room_ids": (
            "sub_walkup_stairwell",
            "sub_walkup_studio",
        ),
        "description": "Compact third-floor brick walk-up studio leased month-to-month in Downtown.",
    },
    "monastic_order": {
        "property_id": "starter_temple_residence",
        "faction_key": "monastic_order",
        "zone_id": "zone_eastern_sanctuary",
        "zone_name": "Sacred Mountain Sanctuary & Onsen Quarter",
        "facility_node_id": "fac_temple_residence",
        "entrance_node_id": "sub_temple_res_courtyard",
        "bedroom_node_id": "sub_temple_res_cell",
        "name": "Outer Cloister Initiate Quarters",
        "room_name": "Private Initiate Cell",
        "all_room_ids": (
            "sub_temple_res_courtyard",
            "sub_temple_res_veranda",
            "sub_temple_res_cell",
        ),
        "description": "Serene timber-framed cloister cell within the consecrated mountain temple grounds.",
    },
    "student_freelancer": {
        "property_id": "starter_parents_house",
        "faction_key": "student_freelancer",
        "zone_id": "zone_suburbs",
        "zone_name": "Suburban Residential District",
        "facility_node_id": "loc_player_house",
        "entrance_node_id": "sub_player_front_porch",
        "bedroom_node_id": "sub_player_bedroom",
        "name": "Parents' Family House",
        "room_name": "Personal Bedroom & Wardrobe",
        "all_room_ids": (
            "sub_player_front_porch",
            "sub_player_living_room",
            "sub_player_bedroom",
        ),
        "description": "Your second-floor bedroom inside your parents' suburban two-story family home.",
    },
}


REALTY_CATALOG: dict[str, dict[str, Any]] = {
    # ── Tier 1: Modest Safehouses (400–600g, +5 base slots) ─────────────────
    "prop_tenement_flat": {
        "property_id": "prop_tenement_flat",
        "name": "Lower Wards Tenement Flat",
        "tier": 1,
        "price": 400,
        "zone_id": "zone_low_cost_wards",
        "zone_name": "The Lower Wards & Tenements",
        "facility_node_id": "fac_tenement_flat",
        "entrance_node_id": "sub_tenement_landing",
        "bedroom_node_id": "sub_tenement_studio",
        "all_room_ids": ("sub_tenement_landing", "sub_tenement_studio"),
        "base_slots": 5,
        "cha_invite_dc_mod": 0,
        "rest_multiplier": 1.0,
        "hangout_affinity_bonus": 0,
        "theme_blurb": "Reinforced iron-door studio tucked behind neon laundry lines in the Lower Wards.",
        "luxury_sensory": "reinforced deadbolt clicks, warm radiator pipes, rain tapping corrugated awnings outside",
    },
    "prop_container_loft": {
        "property_id": "prop_container_loft",
        "name": "Harbor Container Loft",
        "tier": 1,
        "price": 500,
        "zone_id": "zone_city_docks",
        "zone_name": "City Docks & Harbor",
        "facility_node_id": "fac_container_loft",
        "entrance_node_id": "sub_container_catwalk",
        "bedroom_node_id": "sub_container_bunk",
        "all_room_ids": ("sub_container_catwalk", "sub_container_bunk"),
        "base_slots": 5,
        "cha_invite_dc_mod": 0,
        "rest_multiplier": 1.0,
        "hangout_affinity_bonus": 0,
        "theme_blurb": "Converted steel cargo container loft overlooking the foggy harbor cranes.",
        "luxury_sensory": "riveted marine steel walls, warm Edison bulbs, distant foghorns across salt-misted water",
    },
    "prop_vault_safehouse": {
        "property_id": "prop_vault_safehouse",
        "name": "Subterranean Vault Safehouse",
        "tier": 1,
        "price": 600,
        "zone_id": "zone_undercity",
        "zone_name": "Subterranean Under-City & Catacombs",
        "facility_node_id": "fac_vault_safehouse",
        "entrance_node_id": "sub_vault_airlock",
        "bedroom_node_id": "sub_vault_bunker",
        "all_room_ids": ("sub_vault_airlock", "sub_vault_bunker"),
        "base_slots": 5,
        "cha_invite_dc_mod": 0,
        "rest_multiplier": 1.0,
        "hangout_affinity_bonus": 0,
        "theme_blurb": "Decommissioned civil-defense utility vault retrofitted into an off-grid bunker.",
        "luxury_sensory": "sealed steel bulkhead door, quiet geothermal air vents, amber Faraday cage lamps",
    },
    # ── Tier 2: Refined Residences (1,300–2,000g, +10 slots, -1 CHA DC, 1.25x rest) ─
    "prop_shophouse_loft": {
        "property_id": "prop_shophouse_loft",
        "name": "Lantern-Alley Shophouse Loft",
        "tier": 2,
        "price": 1300,
        "zone_id": "zone_chinatown",
        "zone_name": "Old Eastern Quarter & Night Market",
        "facility_node_id": "fac_shophouse_loft",
        "entrance_node_id": "sub_shophouse_vestibule",
        "bedroom_node_id": "sub_shophouse_bedroom",
        "all_room_ids": (
            "sub_shophouse_vestibule",
            "sub_shophouse_tea_parlor",
            "sub_shophouse_bedroom",
        ),
        "base_slots": 10,
        "cha_invite_dc_mod": -1,
        "rest_multiplier": 1.25,
        "hangout_affinity_bonus": 0,
        "theme_blurb": "Timber-and-lattice upper loft perched above glowing silk lanterns in the Old Quarter.",
        "luxury_sensory": "carved rosewood screens, faint jasmine tea steam, warm crimson lantern glow on lacquered floors",
    },
    "prop_suburban_house": {
        "property_id": "prop_suburban_house",
        "name": "Tree-Lined Suburban House",
        "student_name": "Maple-Lane Detached Townhouse",
        "tier": 2,
        "price": 1500,
        "zone_id": "zone_suburbs",
        "zone_name": "Suburban Residential District",
        "facility_node_id": "loc_player_house",
        "entrance_node_id": "sub_player_front_porch",
        "bedroom_node_id": "sub_player_bedroom",
        "all_room_ids": (
            "sub_player_front_porch",
            "sub_player_living_room",
            "sub_player_bedroom",
        ),
        "student_facility_node_id": "fac_suburbs_townhouse",
        "student_entrance_node_id": "sub_townhouse_porch",
        "student_bedroom_node_id": "sub_townhouse_bedroom",
        "student_all_room_ids": (
            "sub_townhouse_porch",
            "sub_townhouse_lounge",
            "sub_townhouse_bedroom",
        ),
        "base_slots": 10,
        "cha_invite_dc_mod": -1,
        "rest_multiplier": 1.25,
        "hangout_affinity_bonus": 0,
        "theme_blurb": "Two-story detached home with a quiet garden porch along a peaceful maple street.",
        "luxury_sensory": "polished oak floorboards, sunlit bay windows, rustling maple leaves beyond a private garden fence",
    },
    "prop_highrise_condo": {
        "property_id": "prop_highrise_condo",
        "name": "Uptown Glass High-Rise Condo",
        "tier": 2,
        "price": 1800,
        "zone_id": "zone_uptown",
        "zone_name": "Uptown District",
        "facility_node_id": "fac_highrise_condo",
        "entrance_node_id": "sub_condo_foyer",
        "bedroom_node_id": "sub_condo_master_suite",
        "all_room_ids": (
            "sub_condo_foyer",
            "sub_condo_skyline_salon",
            "sub_condo_master_suite",
        ),
        "base_slots": 10,
        "cha_invite_dc_mod": -1,
        "rest_multiplier": 1.25,
        "hangout_affinity_bonus": 0,
        "theme_blurb": "Sleek corner condominium thirty floors above Uptown's museum boulevards.",
        "luxury_sensory": "floor-to-ceiling skyline glass, brushed travertine counters, whisper-quiet climate control",
    },
    "prop_ocean_bungalow": {
        "property_id": "prop_ocean_bungalow",
        "name": "Seaside Cliff Bungalow",
        "tier": 2,
        "price": 2000,
        "zone_id": "zone_seaside_beach",
        "zone_name": "Seaside & Coastal Beach",
        "facility_node_id": "fac_ocean_bungalow",
        "entrance_node_id": "sub_bungalow_deck",
        "bedroom_node_id": "sub_bungalow_bedroom",
        "all_room_ids": (
            "sub_bungalow_deck",
            "sub_bungalow_sunroom",
            "sub_bungalow_bedroom",
        ),
        "base_slots": 10,
        "cha_invite_dc_mod": -1,
        "rest_multiplier": 1.25,
        "hangout_affinity_bonus": 0,
        "theme_blurb": "Cedar-shingled coastal bungalow with a private salt-breeze sundeck above the surf.",
        "luxury_sensory": "bleached cedar decking, linen curtains billowing in sea air, rhythmic hush of breaking waves",
    },
    # ── Tier 3: Prestige Estates (3,800–5,000g, +18 slots, -2 CHA DC, 1.5x rest, +1 hangout) ─
    "prop_onsen_villa": {
        "property_id": "prop_onsen_villa",
        "name": "Cypress Mountain Onsen Villa",
        "tier": 3,
        "price": 3800,
        "zone_id": "zone_eastern_sanctuary",
        "zone_name": "Sacred Mountain Sanctuary & Onsen Quarter",
        "facility_node_id": "fac_onsen_villa",
        "entrance_node_id": "sub_villa_gatehouse",
        "bedroom_node_id": "sub_villa_tatami_suite",
        "all_room_ids": (
            "sub_villa_gatehouse",
            "sub_villa_hearth_hall",
            "sub_villa_hotspring_bath",
            "sub_villa_tatami_suite",
        ),
        "base_slots": 18,
        "cha_invite_dc_mod": -2,
        "rest_multiplier": 1.5,
        "hangout_affinity_bonus": 1,
        "theme_blurb": "Secluded hinoki-wood mountain retreat complete with a private steaming mineral bath.",
        "luxury_sensory": "fragrant hinoki cypress beams, rising mineral hot-spring mist, bamboo water-clacker in a moss garden",
    },
    "prop_sovereign_mansion": {
        "property_id": "prop_sovereign_mansion",
        "name": "Sovereign Hills Sky-Mansion",
        "tier": 3,
        "price": 5000,
        "zone_id": "zone_ultra_rich",
        "zone_name": "Sovereign Hills & Sky-Estates",
        "facility_node_id": "fac_sovereign_mansion",
        "entrance_node_id": "sub_mansion_portico",
        "bedroom_node_id": "sub_mansion_penthouse_suite",
        "all_room_ids": (
            "sub_mansion_portico",
            "sub_mansion_grand_salon",
            "sub_mansion_infinity_terrace",
            "sub_mansion_penthouse_suite",
        ),
        "base_slots": 18,
        "cha_invite_dc_mod": -2,
        "rest_multiplier": 1.5,
        "hangout_affinity_bonus": 1,
        "theme_blurb": "Architectural glass-and-marble cliffside estate crowning Sovereign Hills.",
        "luxury_sensory": "veined Calacatta marble atrium, heated infinity-pool terrace, panoramic glittering city horizon",
    },
}


ALL_STATIC_RESIDENTIAL_FACILITY_IDS: frozenset[str] = frozenset(
    {
        "fac_agency_residence",
        "fac_downtown_walkup",
        "fac_temple_residence",
        "loc_player_house",
        "fac_suburbs_townhouse",
        "fac_tenement_flat",
        "fac_container_loft",
        "fac_vault_safehouse",
        "fac_shophouse_loft",
        "fac_highrise_condo",
        "fac_ocean_bungalow",
        "fac_onsen_villa",
        "fac_sovereign_mansion",
    }
)


def is_anomalous_realty_scenario(scenario_key: str) -> bool:
    """Returns True for Anomalous Incursions, Anomalous High School, and their variants."""
    s = str(scenario_key or "").strip().lower()
    if not s:
        return False
    if any(k in s for k in ("anomalous_incursions", "anomalous_high_school", "urban_anomalies")):
        return True
    try:
        import scenario_data
        return bool(
            scenario_data.is_anomalous_incursions_scenario(s)
            or scenario_data.is_anomalous_high_school_scenario(s)
        )
    except Exception:
        return False


def _session_is_student(session_or_id: Mapping[str, Any] | int | None) -> bool:
    if session_or_id is None:
        return False
    try:
        from mechanics.social.origin_mode import is_student_operative
        return bool(is_student_operative(session_or_id))
    except Exception:
        return False


def resolve_starter_quarters_spec(
    faction_key: str | Mapping[str, Any] | None = "",
    session_or_id: Mapping[str, Any] | int | None = None,
) -> dict[str, Any]:
    """Resolves the active starter quarters specification for a player faction."""
    if isinstance(faction_key, Mapping):
        if session_or_id is None:
            session_or_id = faction_key
        fk = ""
    else:
        fk = str(faction_key or "").strip().lower()
    if not fk and session_or_id is not None:
        sess_map: Mapping[str, Any] | None = None
        if isinstance(session_or_id, Mapping):
            sess_map = session_or_id
        elif isinstance(session_or_id, int) and session_or_id > 0:
            try:
                import db
                sess_map = db.get_session(int(session_or_id)) or {}
            except Exception:
                sess_map = None
        if isinstance(sess_map, Mapping):
            fac_st = sess_map.get("anomalous_faction_state")
            fk = str(
                (fac_st.get("faction_archetype_key") if isinstance(fac_st, Mapping) else "")
                or sess_map.get("anomalous_starting_faction")
                or ""
            ).strip().lower()
    if not fk:
        fk = "student_freelancer" if _session_is_student(session_or_id) else "public_agency"
    if fk == "student_freelancer":
        return dict(STARTER_QUARTERS_MAP["student_freelancer"])
    if fk in STARTER_QUARTERS_MAP:
        return dict(STARTER_QUARTERS_MAP[fk])
    # Fallback: Covert/unaffiliated operatives rent the Downtown walk-up
    spec = dict(STARTER_QUARTERS_MAP["freelancer"])
    spec["faction_key"] = fk
    return spec


_BEDROOM_DISPLAY_NAMES: dict[str, str] = {
    "sub_tenement_bedroom": "Reinforced Sleeping Alcove",
    "sub_container_loft_bed": "Mezzanine Bunk & Gear Rack",
    "sub_vault_bunkroom": "Sealed Bunk Chamber",
    "sub_shophouse_bedroom": "Lacquered Timber Bedroom",
    "sub_player_bedroom": "Master Bedroom & Wardrobe",
    "sub_townhouse_bedroom": "Upstairs Master Bedroom",
    "sub_condo_master_suite": "Skyline Master Suite",
    "sub_bungalow_bedroom": "Oceanfront Bedroom",
    "sub_villa_tatami_suite": "Hinoki Tatami Master Suite",
    "sub_mansion_penthouse_suite": "Sovereign Penthouse Suite",
}


def resolve_realty_entry(
    property_id: str,
    session_or_id: Mapping[str, Any] | int | None = None,
) -> dict[str, Any] | None:
    """Returns a session-resolved copy of a purchasable property entry (handling Adult vs Student Suburbs split)."""
    raw = REALTY_CATALOG.get(str(property_id or "").strip())
    if not raw:
        return None
    entry = dict(raw)
    if entry["property_id"] == "prop_suburban_house" and _session_is_student(session_or_id):
        entry["name"] = entry.get("student_name", entry["name"])
        entry["facility_node_id"] = entry["student_facility_node_id"]
        entry["entrance_node_id"] = entry["student_entrance_node_id"]
        entry["bedroom_node_id"] = entry["student_bedroom_node_id"]
        entry["all_room_ids"] = entry["student_all_room_ids"]
    entry.setdefault(
        "bedroom_name",
        _BEDROOM_DISPLAY_NAMES.get(str(entry.get("bedroom_node_id") or ""), "Private Bedroom"),
    )
    entry.setdefault("description", str(entry.get("theme_blurb") or ""))
    return entry


def iter_session_realty_catalog(
    session_or_id: Mapping[str, Any] | int | None = None,
) -> list[dict[str, Any]]:
    """Returns all 9 purchasable properties resolved for the session's origin mode."""
    out: list[dict[str, Any]] = []
    for pid in REALTY_CATALOG:
        resolved = resolve_realty_entry(pid, session_or_id=session_or_id)
        if resolved:
            out.append(resolved)
    return out


def find_realty_by_node_id(
    node_id: str,
    session_or_id: Mapping[str, Any] | int | None = None,
) -> dict[str, Any] | None:
    """Finds the purchasable property entry matching a facility or sub-room node_id for this session."""
    target = str(node_id or "").strip()
    if not target:
        return None
    for entry in iter_session_realty_catalog(session_or_id=session_or_id):
        if target == entry["facility_node_id"] or target in entry.get("all_room_ids", ()):
            return entry
    return None


def compute_property_slot_bonus(owned_tiers: list[int] | tuple[int, ...]) -> int:
    """
    Computes flat inventory slot bonus from permanently purchased deeds (`is_starter == 0`).
    Formula: min(25, best_tier_slots + 2 * max(0, num_owned - 1)).
    Starter quarters (tier 0 / empty list) grant +0.
    """
    valid_tiers = [int(t) for t in (owned_tiers or []) if int(t) in (1, 2, 3)]
    if not valid_tiers:
        return 0
    best_slots = max(TIER_BASE_SLOTS.get(t, 0) for t in valid_tiers)
    extra = EXTRA_DEED_SLOT_BONUS * max(0, len(valid_tiers) - 1)
    return min(MAX_PROPERTY_SLOT_BONUS, best_slots + extra)
