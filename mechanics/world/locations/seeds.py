from __future__ import annotations
from .constants import *
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import db


_SEED_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "locations_seed.json"
_LOCATION_SEEDS_CACHE: Dict[str, Any] = {}

LOCATION_SCENARIOS = {"high_school_drama", "nsfw_high_school_drama", "nsfw_furry_high_school_drama", "furry_high_school_drama"}

def _load_seeds() -> Dict[str, Any]:
    global _LOCATION_SEEDS_CACHE
    if not _LOCATION_SEEDS_CACHE and _SEED_PATH.exists():
        try:
            with open(_SEED_PATH, "r", encoding="utf-8") as f:
                _LOCATION_SEEDS_CACHE = json.load(f)
        except Exception:
            _LOCATION_SEEDS_CACHE = {}
    return _LOCATION_SEEDS_CACHE

def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", str(text or "").lower()).strip()
    return re.sub(r"[-\s]+", "_", cleaned) or "loc"

TAG_TO_LOCATION_SEED_KEY = {
    "space": "sci_fi",
    "sci_fi": "sci_fi",
    "dark_fantasy": "dark_fantasy",
    "isekai": "isekai_fantasy",
    "isekai_fantasy": "isekai_fantasy",
    "high_school": "high_school_drama",
    "high_school_drama": "high_school_drama",
    "slice_of_life": "slice_of_life",
    "post_apocalypse": "nuclear_post_apocalypse",
    "nuclear_post_apocalypse": "nuclear_post_apocalypse",
    "cyberpunk": "cyberpunk",
    "steampunk": "steampunk",
    "fantasy": "fantasy",
    "urban_fantasy": "anomalous_incursions",
    "anomalous_incursions": "anomalous_incursions",
}

def _filter_seed_zones_for_nsfw(zones: list[dict], allow_nsfw: bool) -> list[dict]:
    """Filters out `nsfw_only: True` primary facilities and sub-locations when `allow_nsfw` is False."""
    if allow_nsfw or not zones:
        return [dict(z) for z in zones] if zones else []
    filtered_zones: list[dict] = []
    for z in zones:
        if z.get("nsfw_only"):
            continue
        z_copy = dict(z)
        new_primaries: list[dict] = []
        for p in z.get("primary_locations") or []:
            if p.get("nsfw_only"):
                continue
            p_copy = dict(p)
            p_copy["sub_locations"] = [
                dict(s) for s in (p.get("sub_locations") or [])
                if not s.get("nsfw_only")
            ]
            new_primaries.append(p_copy)
        z_copy["primary_locations"] = new_primaries
        filtered_zones.append(z_copy)
    return filtered_zones


def get_scenario_seed_data(scenario_key: str) -> dict:
    """Helper to get seed data for scenario or combine zones across all active tags for multi-genre custom scenarios."""
    data = _load_seeds()
    allow_nsfw = False
    try:
        import scenario_data
        allow_nsfw = bool(scenario_data.is_nsfw_scenario(scenario_key or ""))
    except Exception:
        allow_nsfw = "nsfw" in str(scenario_key or "").lower()

    if not scenario_key:
        raw = data.get("fantasy") or data.get("high_school_drama") or {}
        return {"zones": _filter_seed_zones_for_nsfw(raw.get("zones") or [], allow_nsfw)}
    scen_data = data.get(scenario_key) or data.get(TAG_TO_LOCATION_SEED_KEY.get(scenario_key, ""))
    if not scen_data:
        try:
            from scenario_data import get_scenario
            scen = get_scenario(scenario_key)
            base = scen.get("base_scenario")
            if base and base in data:
                scen_data = data.get(base)
            elif base and TAG_TO_LOCATION_SEED_KEY.get(base) in data:
                scen_data = data.get(TAG_TO_LOCATION_SEED_KEY[base])
            if not scen_data:
                tags = scen.get("tags") or []
                combined_zones = []
                for tag in tags:
                    k = tag if tag in data else TAG_TO_LOCATION_SEED_KEY.get(tag, "")
                    if k in data and "zones" in data[k]:
                        combined_zones.extend(data[k]["zones"])
                if combined_zones:
                    scen_data = {"zones": combined_zones}
        except Exception:
            pass
    if not scen_data:
        scen_data = data.get("fantasy") or data.get("high_school_drama") or {}
    out = dict(scen_data)
    if "zones" in out:
        out["zones"] = _filter_seed_zones_for_nsfw(out.get("zones") or [], allow_nsfw)
    return out


def get_seed_node_metadata(node_id_or_name: str, scenario_key: str = "high_school_drama") -> Dict[str, Any]:
    """
    Returns static metadata flags (`is_discreet`, `is_private_intimate`, `gender_restriction`,
    `grade_exclusive`, `suite_fee`, `nsfw_only`) for a facility or sub-location from `locations_seed.json`.
    """
    target = str(node_id_or_name or "").strip().lower()
    if not target:
        return {}
    if "➔" in target:
        parts = [p.strip() for p in target.split("➔") if p.strip()]
        leaf_target = parts[-1] if parts else target
    else:
        leaf_target = target

    data = _load_seeds()
    base_key = "high_school_drama" if is_school_scenario(scenario_key) else (
        scenario_key if scenario_key in data else TAG_TO_LOCATION_SEED_KEY.get(scenario_key, "high_school_drama")
    )
    zones = (data.get(base_key) or {}).get("zones") or []
    for z in zones:
        for p in z.get("primary_locations") or []:
            p_id = str(p.get("id") or "").lower()
            p_name = str(p.get("name") or "").lower()
            if leaf_target in (p_id, p_name):
                return {
                    "id": p.get("id", ""),
                    "name": p.get("name", ""),
                    "zone_id": z.get("id", ""),
                    "is_discreet": bool(p.get("is_discreet")),
                    "is_private_intimate": bool(p.get("is_private_intimate")),
                    "gender_restriction": str(p.get("gender_restriction") or "").lower(),
                    "grade_exclusive": str(p.get("grade_exclusive") or ""),
                    "suite_fee": int(p.get("suite_fee") or 0),
                    "nsfw_only": bool(p.get("nsfw_only")),
                }
            for s in p.get("sub_locations") or []:
                s_id = str(s.get("id") or "").lower()
                s_name = str(s.get("name") or "").lower()
                if leaf_target in (s_id, s_name) or target in (s_id, s_name):
                    return {
                        "id": s.get("id", ""),
                        "name": s.get("name", ""),
                        "parent_id": p.get("id", ""),
                        "parent_name": p.get("name", ""),
                        "zone_id": z.get("id", ""),
                        "is_discreet": bool(s.get("is_discreet")),
                        "is_private_intimate": bool(s.get("is_private_intimate") or p.get("is_private_intimate")),
                        "gender_restriction": str(s.get("gender_restriction") or p.get("gender_restriction") or "").lower(),
                        "grade_exclusive": str(s.get("grade_exclusive") or ""),
                        "suite_fee": int(s.get("suite_fee") or 0),
                        "nsfw_only": bool(s.get("nsfw_only") or p.get("nsfw_only")),
                    }
    return {}


def get_discreet_locations_for_scenario(scenario_key: str = "high_school_drama", session_id: int = 0) -> List[Dict[str, Any]]:
    """Returns all seeded `is_discreet: True` rooms (with session-resolved 3-tier paths if `session_id` is given)."""
    scen_data = get_scenario_seed_data(scenario_key)
    results: List[Dict[str, Any]] = []
    node_path_by_id: Dict[str, str] = {}
    if session_id:
        try:
            for r in db.get_session_locations(session_id) or []:
                lid = str(r.get("location_id") or "")
                if lid:
                    node_path_by_id[lid] = f"{r.get('zone_name', '')} ➔ {r.get('primary_name', '')} ➔ {r.get('sub_name', '')}"
        except Exception:
            pass
    for z in scen_data.get("zones") or []:
        z_id = z.get("id", "")
        z_name = z.get("name", "")
        for p in z.get("primary_locations") or []:
            p_id = p.get("id", "")
            p_name = p.get("name", "")
            for s in p.get("sub_locations") or []:
                if s.get("is_discreet"):
                    s_id = s.get("id", "")
                    s_name = s.get("name", "")
                    full_path = node_path_by_id.get(s_id) or f"{z_name} ➔ {p_name} ➔ {s_name}"
                    results.append({
                        "node_id": s_id,
                        "name": s_name,
                        "facility_id": p_id,
                        "facility_name": p_name,
                        "zone_id": z_id,
                        "zone_name": z_name,
                        "path": full_path,
                    })
    return results

def is_school_scenario(scenario_key: str) -> bool:
    """Checks if scenario is an academic/school setting."""
    scen = str(scenario_key or "").lower().strip()
    if any(k in scen for k in ("high_school", "school", "furry_high_school", "academy")):
        return True
    try:
        from scenario_data import has_tag
        return bool(
            has_tag(scen, "high_school")
            or has_tag(scen, "high_school_drama")
        )
    except Exception:
        return False

def get_session_school_name(session_id: int = 0, scenario_key: str = "high_school_drama") -> str:
    """Retrieves or deterministically generates the unique dynamic school name for a session."""
    if session_id:
        existing = db.get_session_locations(session_id)
        for r in existing:
            z = r.get("zone_name") or ""
            if z and "{session_school}" not in z and z not in ("Main Academy Campus", "Main Academy Building") and z not in (
                "Commercial District", "Downtown", "City Center", "Residential District", "Residential Neighborhood",
                "School Grounds & Athletics", "Local Park & Waterfront", "World Region",
                "Starting Zone", "Main Area", "Seaside & Coastal Bay", "Recreational Mountain Park", "Recreational Park"
            ):
                p_name = r.get("primary_name") or ""
                s_name = r.get("sub_name") or ""
                if (
                    p_name in (
                        "Main Campus Building", "Homeroom Classroom", "Empty Classroom", "School Hallways", "2F Hallway",
                        "Teachers' Staff Room", "School Library", "Chemistry & Science Lab",
                        "School Rooftop", "Gymnasium", "Main Gymnasium", "School Main Gates"
                    )
                    or s_name in (
                        "Homeroom Classroom", "Empty Classroom", "School Hallways", "2F Hallway",
                        "Teachers' Staff Room", "School Library", "Chemistry & Science Lab",
                        "School Rooftop", "Gymnasium", "Main Gymnasium", "School Main Gates"
                    )
                    or "Homeroom" in s_name
                ):
                    return z

    from namegen import generate_school_name
    h_val = int(session_id) if session_id else None
    return generate_school_name(scenario=scenario_key, hash_val=h_val)

def get_session_classroom_name(session_id: int = 0, scenario_key: str = "high_school_drama") -> str:
    """Retrieves or deterministically generates the unique dynamic classroom name for a session."""
    if session_id:
        existing = db.get_session_locations(session_id)
        for r in existing:
            for val in (r.get("sub_name") or "", r.get("primary_name") or ""):
                if val and val != "Homeroom Classroom" and "Homeroom" in val and "Desk" not in val:
                    return val

    from namegen import generate_classroom_name
    h_val = int(session_id) if session_id else None
    return generate_classroom_name(scenario=scenario_key, hash_val=h_val)

def get_session_park_name(session_id: int = 0, scenario_key: str = "high_school_drama") -> str:
    """Retrieves or deterministically generates the unique dynamic park name for a session."""
    if session_id:
        existing = db.get_session_locations(session_id)
        for r in existing:
            p = r.get("primary_name") or ""
            if p and p not in ("Neighborhood Park", "Local Park", "loc_local_park") and ("Park" in p or "Gardens" in p or "Grove" in p or "Commons" in p):
                return p

    from namegen import generate_park_name
    h_val = int(session_id) if session_id else None
    return generate_park_name(scenario=scenario_key, hash_val=h_val)

def get_session_cafe_name(session_id: int = 0, scenario_key: str = "high_school_drama") -> str:
    """Retrieves or deterministically generates the unique dynamic café name for a session."""
    if session_id:
        existing = db.get_session_locations(session_id)
        for r in existing:
            p = r.get("primary_name") or ""
            if p and p not in ("Local Café", "Sunny Days Café", "loc_cafe") and ("Café" in p or "Cafe" in p or "Bakery" in p or "Tea" in p):
                return p

    from namegen import generate_cafe_name
    h_val = int(session_id) if session_id else None
    return generate_cafe_name(scenario=scenario_key, hash_val=h_val)

def get_session_arcade_name(session_id: int = 0, scenario_key: str = "high_school_drama") -> str:
    """Retrieves or deterministically generates the unique dynamic arcade center name for a session."""
    if session_id:
        existing = db.get_session_locations(session_id)
        for r in existing:
            p = r.get("primary_name") or ""
            if p and p not in ("Game Arcade", "Pixel Paradise Arcade", "loc_arcade") and ("Arcade" in p or "Game Center" in p or "Lounge" in p):
                return p

    from namegen import generate_arcade_name
    h_val = int(session_id) if session_id else None
    return generate_arcade_name(scenario=scenario_key, hash_val=h_val)

def get_session_ripperdoc_name(session_id: int = 0, scenario_key: str = "cyberpunk") -> str:
    """Retrieves or deterministically generates the unique dynamic ripperdoc clinic name for a session."""
    if session_id:
        existing = db.get_session_locations(session_id)
        for r in existing:
            p = r.get("primary_name") or ""
            if p and p not in ("Ripperdoc Clinic", "loc_ripperdoc_clinic") and ("Ripperdoc" in p or "Clinic" in p or "Augmentation" in p or "Surgery" in p):
                return p

    from namegen import generate_ripperdoc_name
    h_val = int(session_id) if session_id else None
    return generate_ripperdoc_name(scenario=scenario_key, hash_val=h_val)

def get_session_kingdom_name(session_id: int = 0, scenario_key: str = "fantasy") -> str:
    """Generates a dynamic kingdom name."""
    from namegen import generate_kingdom_name
    h_val = int(session_id) if session_id else None
    return generate_kingdom_name(scenario=scenario_key, hash_val=h_val)

def get_session_forest_name(session_id: int = 0, scenario_key: str = "fantasy") -> str:
    """Generates a dynamic regular forest / woods name."""
    from namegen import generate_forest_name
    h_val = int(session_id) if session_id else None
    return generate_forest_name(scenario=scenario_key, hash_val=h_val)

def get_session_ancient_forest_name(session_id: int = 0, scenario_key: str = "fantasy") -> str:
    """Generates a dynamic primeval ancient forest name."""
    from namegen import generate_ancient_forest_name
    h_val = int(session_id) if session_id else None
    return generate_ancient_forest_name(scenario=scenario_key, hash_val=h_val)

def get_session_plains_name(session_id: int = 0, scenario_key: str = "fantasy") -> str:
    """Generates a dynamic farmlands / plains biome name."""
    from namegen import generate_plains_name
    h_val = int(session_id) if session_id else None
    return generate_plains_name(scenario=scenario_key, hash_val=h_val)

def get_session_harbor_name(session_id: int = 0, scenario_key: str = "fantasy") -> str:
    """Generates a dynamic coastal harbor town name."""
    from namegen import generate_harbor_name
    h_val = int(session_id) if session_id else None
    return generate_harbor_name(scenario=scenario_key, hash_val=h_val)

def get_session_tundra_name(session_id: int = 0, scenario_key: str = "fantasy") -> str:
    """Generates a dynamic frozen snow / tundra biome name."""
    from namegen import generate_tundra_name
    h_val = int(session_id) if session_id else None
    return generate_tundra_name(scenario=scenario_key, hash_val=h_val)

def get_session_volcano_name(session_id: int = 0, scenario_key: str = "fantasy") -> str:
    """Generates a dynamic volcanic ashlands biome name."""
    from namegen import generate_volcano_name
    h_val = int(session_id) if session_id else None
    return generate_volcano_name(scenario=scenario_key, hash_val=h_val)

def get_session_shadowlands_name(session_id: int = 0, scenario_key: str = "fantasy") -> str:
    """Generates a dynamic cursed shadowlands biome name."""
    from namegen import generate_shadowlands_name
    h_val = int(session_id) if session_id else None
    return generate_shadowlands_name(scenario=scenario_key, hash_val=h_val)

def get_session_caves_name(session_id: int = 0, scenario_key: str = "fantasy") -> str:
    """Generates a dynamic deep cave network biome name."""
    from namegen import generate_caves_name
    h_val = int(session_id) if session_id else None
    return generate_caves_name(scenario=scenario_key, hash_val=h_val)

def get_session_chasm_name(session_id: int = 0, scenario_key: str = "fantasy") -> str:
    """Generates a dynamic underworld chasm biome name."""
    from namegen import generate_chasm_name
    h_val = int(session_id) if session_id else None
    return generate_chasm_name(scenario=scenario_key, hash_val=h_val)

def get_session_dungeon_name(session_id: int = 0, scenario_key: str = "fantasy") -> str:
    """Generates a dynamic ancient dungeon complex biome name."""
    from namegen import generate_dungeon_name
    h_val = int(session_id) if session_id else None
    return generate_dungeon_name(scenario=scenario_key, hash_val=h_val)

def get_session_mountain_name(session_id: int = 0, scenario_key: str = "fantasy") -> str:
    """Generates a dynamic mountain range name."""
    from namegen import generate_mountain_name
    h_val = int(session_id) if session_id else None
    return generate_mountain_name(scenario=scenario_key, hash_val=h_val)

def get_session_desert_name(session_id: int = 0, scenario_key: str = "fantasy") -> str:
    """Generates a dynamic desert biome name."""
    from namegen import generate_desert_name
    h_val = int(session_id) if session_id else None
    return generate_desert_name(scenario=scenario_key, hash_val=h_val)

def get_session_swamp_name(session_id: int = 0, scenario_key: str = "fantasy") -> str:
    """Generates a dynamic swamp biome name."""
    from namegen import generate_swamp_name
    h_val = int(session_id) if session_id else None
    return generate_swamp_name(scenario=scenario_key, hash_val=h_val)


def get_session_agency_name(session_id: int = 0, scenario_key: str = "urban_anomalies") -> str:
    """Generates a dynamic agency organization name."""
    from namegen import generate_agency_name
    h_val = int(session_id) if session_id else None
    return generate_agency_name(scenario=scenario_key, hash_val=h_val)

def get_session_agency_hq_name(session_id: int = 0, scenario_key: str = "urban_anomalies") -> str:
    """Generates a dynamic agency headquarters facility name."""
    from namegen import generate_agency_hq_name
    h_val = int(session_id) if session_id else None
    return generate_agency_hq_name(scenario=scenario_key, hash_val=h_val)


def is_urban_anomalous_scenario(scenario_key: str = "") -> bool:
    """Checks if the scenario uses the Anomalous Incursions / Urban Fantasy procedural city topology."""
    s = str(scenario_key or "").lower().strip()
    if any(k in s for k in ("anomalous", "incursion", "urban_anomalies", "urban_fantasy", "scp", "control")):
        return True
    try:
        from scenario_data import has_tag
        return bool(has_tag(s, "urban_fantasy") or has_tag(s, "anomalous_incursions"))
    except Exception:
        return False


def get_session_urban_zone_name(session_id: int, z_id: str, raw_zone_name: str, scenario_key: str = "anomalous_incursions") -> str:
    """Deterministically generates a procedural Tier-1 Zone name for a session."""
    from namegen import generate_urban_zone_name
    h_val = int(session_id) if session_id else 1
    return generate_urban_zone_name(z_id=z_id, raw_zone_name=raw_zone_name, hash_val=h_val, scenario=scenario_key)


def get_session_urban_facility_name(
    session_id: int,
    z_id: str,
    p_id: str,
    raw_primary_name: str,
    scenario_key: str = "anomalous_incursions",
    char_name: str = "",
) -> str:
    """Deterministically generates a procedural Tier-2 Primary Facility name for a session."""
    from namegen import generate_urban_facility_name
    h_val = int(session_id) if session_id else 1
    return generate_urban_facility_name(
        z_id=z_id,
        p_id=p_id,
        raw_primary_name=raw_primary_name,
        hash_val=h_val,
        char_name=char_name,
        scenario=scenario_key,
    )


def inject_anomalous_faction_hq_facilities(zones: list[dict], session_id: int = 0, scenario_key: str = "anomalous_incursions") -> list[dict]:
    """
    When seeding an Anomalous Incursions session, deterministically injects the
    Tier-2 HQ facilities (and Tier-3 sub-locations) for Private Agency #1, Private Agency #2,
    the Occult Cult, and the Clandestine Syndicate into their assigned city zones.
    """
    try:
        from scenario_data import is_anomalous_incursions_scenario
        if not is_anomalous_incursions_scenario(scenario_key):
            return zones
    except Exception:
        return zones

    from namegen import (
        format_org_acronym,
        generate_private_agency_name,
        generate_occult_cult_name,
        generate_clandestine_syndicate_name,
    )
    import copy

    h_val = int(session_id) if session_id else 1
    priv_1_name = generate_private_agency_name(scenario_key, hash_val=h_val, agency_index=1)
    priv_2_name = generate_private_agency_name(scenario_key, hash_val=h_val, agency_index=2)
    if priv_2_name == priv_1_name:
        priv_2_name = generate_private_agency_name(scenario_key, hash_val=h_val + 99, agency_index=3)
    cult_name = generate_occult_cult_name(scenario_key, hash_val=h_val)
    synd_name = generate_clandestine_syndicate_name(scenario_key, hash_val=h_val)

    priv_1_acronym = format_org_acronym(priv_1_name)
    priv_1_hq = f"{priv_1_acronym} Tower HQ" if priv_1_acronym else f"{priv_1_name} HQ"
    priv_2_acronym = format_org_acronym(priv_2_name)
    priv_2_hq = f"{priv_2_acronym} Operations HQ" if priv_2_acronym else f"{priv_2_name} HQ"

    urban_core_zones = ["zone_city_center", "zone_downtown", "zone_uptown"]
    p1_zone = urban_core_zones[h_val % 3]
    p2_zone = urban_core_zones[(h_val + 1) % 3]
    cult_zone = "zone_woods_reserve" if (h_val % 2 == 0) else "zone_undercity"
    synd_zone = "zone_undercity" if cult_zone == "zone_woods_reserve" else "zone_industrial"

    injected_by_zone = {
        p1_zone: {
            "id": "loc_private_hq_1",
            "name": priv_1_hq,
            "is_anomalous": False,
            "sub_locations": [
                {
                    "id": "sub_priv1_entrance",
                    "name": "Corporate Security Lobby & Entrance",
                    "is_entrance": 1,
                    "props": ["Biometric Turnstiles", "Reception Concierge Desk", "Executive Directory Display", "Leather Waiting Lounge"],
                },
                {
                    "id": "sub_priv1_dispatch",
                    "name": "Executive Contract & Tactical Dispatch Wing",
                    "props": ["Holographic Contract Board", "Client Briefing Table", "Encrypted Dispatch Terminal", "Priority Threat Ticker"],
                },
                {
                    "id": "sub_priv1_armory",
                    "name": "Syndicate Tactical Armory & Requisition Depot",
                    "access_tier": "restricted",
                    "props": ["Quartermaster Counter", "Anomalous Ordnance Racks", "Ammunition Lockers", "Weapon Calibration Bench"],
                },
                {
                    "id": "sub_priv1_outfitter",
                    "name": "Bespoke Ballistic Outfitter & Tailoring Atelier",
                    "access_tier": "restricted",
                    "props": ["Ballistic Mannequin Row", "Kevlar Tailoring Counter", "Warded Trenchcoat Racks", "Fitting Mirror Booth"],
                },
                {
                    "id": "sub_priv1_medbay",
                    "name": "Corporate Trauma & Psychic Detox Clinic",
                    "access_tier": "restricted",
                    "props": ["Trauma Stabilization Pod", "Psychic Cleansing Chair", "Stim-Pack Dispensary Counter", "Bio-Scan Console"],
                },
                {
                    "id": "sub_priv1_canteen",
                    "name": "Skyline Executive Espresso Bar & Canteen",
                    "access_tier": "restricted",
                    "props": ["Marble Espresso Counter", "Panoramic Window Booths", "Chef's Hot-Plate Station", "Executive Wine & Tea Rack"],
                },
                {
                    "id": "sub_priv1_research",
                    "name": "Proprietary Relic R&D & Appraisal Division",
                    "access_tier": "restricted",
                    "props": ["Lead-Glass Analysis Hood", "Resonance Spectrometer", "Catalogued Relic Vault", "Lead Researcher's Terminal"],
                },
                {
                    "id": "sub_priv1_training",
                    "name": "VR Tactical & Resonance Calibration Range",
                    "access_tier": "restricted",
                    "props": ["Live-Fire Ballistic Lanes", "Holographic Breach Simulator", "Resonance Output Meter", "Weapon Maintenance Rack"],
                },
                {
                    "id": "sub_priv1_quarters",
                    "name": "Operative Penthouse Suites & Rest Quarters",
                    "access_tier": "restricted",
                    "props": ["Memory-Foam Suite Bed", "Plush Leather Sofa", "Private Locker & Wardrobe", "Cityscape Balcony Window"],
                },
                {
                    "id": "sub_priv1_vault",
                    "name": "Sub-Basement Corporate Containment & Quarantine Vault",
                    "access_tier": "restricted",
                    "props": ["Reinforced Blast Airlock", "Suppression Stasis Cells", "Black-Box Relic Lockers", "Security Overwatch Console"],
                },
            ],
        },
        p2_zone: {
            "id": "loc_private_hq_2",
            "name": priv_2_hq,
            "is_anomalous": False,
            "sub_locations": [
                {
                    "id": "sub_priv2_entrance",
                    "name": "Executive Security Lobby & Entrance",
                    "is_entrance": 1,
                    "props": ["Biometric Turnstiles", "Executive Reception Desk", "Operations Status Wall", "Visitor Screening Lounge"],
                },
                {
                    "id": "sub_priv2_dispatch",
                    "name": "Executive Contract & Tactical Dispatch Wing",
                    "props": ["Holographic Contract Board", "Tactical Briefing Holotable", "Encrypted Dispatch Terminal", "Municipal Bid Monitor"],
                },
                {
                    "id": "sub_priv2_armory",
                    "name": "Syndicate Tactical Armory & Requisition Depot",
                    "access_tier": "restricted",
                    "props": ["Quartermaster Counter", "Heavy Anomalous Weapon Racks", "Ordnance Lockers", "Ballistic Test Bench"],
                },
                {
                    "id": "sub_priv2_outfitter",
                    "name": "Bespoke Ballistic Outfitter & Tailoring Atelier",
                    "access_tier": "restricted",
                    "props": ["Tactical Suit Display", "Armored Tailoring Bench", "Field Rigging Lockers", "Fitting Mirror Alcove"],
                },
                {
                    "id": "sub_priv2_medbay",
                    "name": "Corporate Trauma & Psychic Detox Clinic",
                    "access_tier": "restricted",
                    "props": ["Surgical Recovery Bed", "Neural Cleansing Pod", "Combat Pharmacy Counter", "Vital Telemetry Array"],
                },
                {
                    "id": "sub_priv2_canteen",
                    "name": "Skyline Executive Espresso Bar & Canteen",
                    "access_tier": "restricted",
                    "props": ["Brushed-Steel Espresso Bar", "Skyline Dining Tables", "High-Protein Ration Counter", "Private Lounge Booth"],
                },
                {
                    "id": "sub_priv2_research",
                    "name": "Proprietary Relic R&D & Appraisal Division",
                    "access_tier": "restricted",
                    "props": ["Containment Glovebox", "Aetheric Frequency Scanner", "Secured Specimen Drawers", "Appraisal Ledger Terminal"],
                },
                {
                    "id": "sub_priv2_training",
                    "name": "VR Tactical & Resonance Calibration Range",
                    "access_tier": "restricted",
                    "props": ["Modular Kill-House Floor", "Firing Range Dividers", "Psychic Dampening Pylons", "Combat Telemetry Desk"],
                },
                {
                    "id": "sub_priv2_quarters",
                    "name": "Operative Penthouse Suites & Rest Quarters",
                    "access_tier": "restricted",
                    "props": ["Memory-Foam Suite Bed", "Plush Leather Sofa", "Armored Gear Locker", "Nightstand Intercom"],
                },
                {
                    "id": "sub_priv2_vault",
                    "name": "Sub-Basement Corporate Containment & Quarantine Vault",
                    "access_tier": "restricted",
                    "props": ["Hydraulic Vault Door", "High-Threat Stasis Pods", "Classified Evidence Safe", "Containment Control Desk"],
                },
            ],
        },
        cult_zone: {
            "id": "loc_cult_sanctum_hq",
            "name": f"{cult_name} Hidden Sanctum",
            "is_anomalous": True,
            "access_tier": "restricted",
            "sub_locations": [
                {
                    "id": "sub_cult_entrance",
                    "name": "Ward-Sealed Threshold Entrance",
                    "is_entrance": 1,
                    "props": ["Blood-Warded Iron Door", "Occult Braziers", "Lookout Spy-Slit", "Carved Warning Stele"],
                },
                {
                    "id": "sub_cult_cloister",
                    "name": "Acolyte Cloister & Chant Hall",
                    "access_tier": "restricted",
                    "props": ["Robed Pew Benches", "Incense Thurible Stands", "Whispering Fresco Wall", "Ritual Vestment Rack"],
                },
                {
                    "id": "sub_cult_altar",
                    "name": "Resonant Fracture Altar",
                    "access_tier": "restricted",
                    "props": ["Obsidian Fracture Altar", "Shimmering Reality Tear", "Ceremonial Dagger Pedestal", "Candelabra Ring"],
                },
                {
                    "id": "sub_cult_cells",
                    "name": "Sacrificial Entity Holding Cells",
                    "access_tier": "restricted",
                    "props": ["Rusted Rune-Barred Cages", "Warding Salt Lines", "Shackle Wall", "Warden's Key Hook"],
                },
                {
                    "id": "sub_cult_reliquary",
                    "name": "Forbidden Apocrypha Reliquary",
                    "access_tier": "restricted",
                    "props": ["Chained Grimoire Lecterns", "Cursed Relic Display Cases", "Wax-Sealed Scroll Racks", "Cipher Translation Desk"],
                },
                {
                    "id": "sub_cult_sanctum",
                    "name": "Abyssal Conduit Inner Sanctum",
                    "access_tier": "restricted",
                    "props": ["Hierophant's Dais", "Pulsing Rift Monolith", "Ritual Conduit Pylons", "Sealed Offering Chest"],
                },
            ],
        },
        synd_zone: {
            "id": "loc_clandestine_syndicate_hq",
            "name": f"{synd_name} Shadow Exchange HQ",
            "is_anomalous": True,
            "access_tier": "restricted",
            "sub_locations": [
                {
                    "id": "sub_synd_entrance",
                    "name": "Biometric Vault Door Entrance",
                    "is_entrance": 1,
                    "props": ["Retinal Scan Airlock", "Armored Blast Shutter", "Concealed Turret Mount", "Decoy Freight Elevator"],
                },
                {
                    "id": "sub_synd_guardroom",
                    "name": "Mercenary Security Guardroom",
                    "access_tier": "restricted",
                    "props": ["CCTV Monitor Wall", "Riot Gear Racks", "Security Armory Locker", "Duty Roster Desk"],
                },
                {
                    "id": "sub_synd_floor",
                    "name": "Black-Budget Brokerage Floor",
                    "access_tier": "restricted",
                    "props": ["Encrypted Bidding Terminals", "Private VIP Negotiation Booths", "Escrow Vault Chute", "Ticker Display Ring"],
                },
                {
                    "id": "sub_synd_pens",
                    "name": "Contraband Entity Auction Pens",
                    "access_tier": "restricted",
                    "props": ["Shock-Shielded Containment Pens", "Reinforced Viewing Glass", "Sedative Injector Console", "Cargo Winch"],
                },
                {
                    "id": "sub_synd_lab",
                    "name": "Weaponized Cognitohazard Lab",
                    "access_tier": "restricted",
                    "props": ["Memetic Isolation Chamber", "Centrifuge & Vial Racks", "Hazmat Airlock", "Research Server Array"],
                },
                {
                    "id": "sub_synd_vault",
                    "name": "Directorate Black-Ledger Vault",
                    "access_tier": "restricted",
                    "props": ["Time-Locked Titanium Safe", "Cold-Storage Crypto Drives", "Bearer-Bond Cabinets", "Executive Shredder Console"],
                },
            ],
        },
    }

    out_zones = []
    for z in zones:
        z_copy = copy.deepcopy(z)
        z_id = z_copy.get("id", "")
        if z_id in injected_by_zone:
            fac = injected_by_zone[z_id]
            existing_ids = {p.get("id") for p in (z_copy.get("primary_locations") or [])}
            if fac["id"] not in existing_ids:
                z_copy.setdefault("primary_locations", []).append(fac)
        out_zones.append(z_copy)
    return out_zones

def get_session_cyber_city_name(session_id: int = 0, scenario_key: str = "cyberpunk") -> str:
    """Generates a dynamic cyberpunk city name."""
    from namegen import generate_cyber_city_name
    h_val = int(session_id) if session_id else None
    return generate_cyber_city_name(scenario=scenario_key, hash_val=h_val)

def get_session_planet_name(session_id: int = 0, biome_type: str = "") -> str:
    """Generates a dynamic planet name."""
    from namegen import generate_planet_name
    h_val = int(session_id) if session_id else None
    return generate_planet_name(biome_type=biome_type, hash_val=h_val)

def get_session_station_name(session_id: int = 0) -> str:
    """Generates a dynamic space station name."""
    from namegen import generate_space_station_name
    h_val = int(session_id) if session_id else None
    return generate_space_station_name(hash_val=h_val)

def get_session_seaside_name(session_id: int = 0, scenario_key: str = "high_school_drama") -> str:
    """Generates a dynamic seaside / coastal bay name."""
    from namegen import generate_seaside_name
    h_val = int(session_id) if session_id else None
    return generate_seaside_name(scenario=scenario_key, hash_val=h_val)

def get_session_recreation_park_name(session_id: int = 0, scenario_key: str = "high_school_drama") -> str:
    """Generates a dynamic recreational park name."""
    from namegen import generate_recreation_park_name
    h_val = int(session_id) if session_id else None
    return generate_recreation_park_name(scenario=scenario_key, hash_val=h_val)

def get_session_commercial_district_name(session_id: int = 0, scenario_key: str = "high_school_drama") -> str:
    """Retrieves or dynamically generates the unique downtown / commercial district name for a session."""
    if session_id:
        existing = db.get_session_locations(session_id)
        for r in existing:
            z = r.get("zone_name") or ""
            if z and z not in ("Commercial District", "Downtown", "City Center"):
                if any(sk in z for sk in ("School", "Academy", "Campus", "Commons", "Athletics", "Arts", "Abandoned", "Recreational", "Residential", "Seaside", "Coastal")):
                    continue
                if any(k in z for k in ("Downtown", "Commercial", "Shopping", "Promenade", "Arcade", "Avenue", "Strip", "Market", "Square")):
                    return z

    from namegen import generate_commercial_district_name
    h_val = int(session_id) if session_id else None
    return generate_commercial_district_name(scenario=scenario_key, hash_val=h_val)

def get_session_residential_neighborhood_name(session_id: int = 0, scenario_key: str = "high_school_drama") -> str:
    """Retrieves or dynamically generates the unique residential neighborhood name for a session."""
    if session_id:
        existing = db.get_session_locations(session_id)
        for r in existing:
            z = r.get("zone_name") or ""
            if z and z != "Residential Neighborhood" and "Recreational" not in z and any(k in z for k in ("Residential", "Suburban", "Quarter", "Heights", "Miyamae", "Sakura Hill", "Midori-cho")):
                return z

    from namegen import generate_residential_neighborhood_name
    h_val = int(session_id) if session_id else None
    return generate_residential_neighborhood_name(scenario=scenario_key, hash_val=h_val)

def get_session_athletics_complex_name(session_id: int = 0, scenario_key: str = "high_school_drama") -> str:
    """Retrieves or dynamically generates the athletics complex building/wing name for a session."""
    if session_id:
        existing = db.get_session_locations(session_id)
        for r in existing:
            for val in (r.get("primary_name") or "", r.get("zone_name") or ""):
                if val and any(k in val.lower() for k in ("athletics", "grounds", "sports complex", "stadium")):
                    return val

    from namegen import generate_school_athletics_name
    h_val = int(session_id) if session_id else None
    return generate_school_athletics_name(scenario=scenario_key, hash_val=h_val)

def get_session_student_commons_name(session_id: int = 0, scenario_key: str = "high_school_drama") -> str:
    """Retrieves or dynamically generates the student commons & central plaza building/wing name for a session."""
    if session_id:
        existing = db.get_session_locations(session_id)
        for r in existing:
            for val in (r.get("primary_name") or "", r.get("zone_name") or ""):
                if val and any(k in val.lower() for k in ("commons", "central plaza", "courtyard & dining", "promenade & commons")):
                    return val

    from namegen import generate_school_commons_name
    h_val = int(session_id) if session_id else None
    return generate_school_commons_name(scenario=scenario_key, hash_val=h_val)

def get_session_cultural_arts_name(session_id: int = 0, scenario_key: str = "high_school_drama") -> str:
    """Retrieves or dynamically generates the cultural arts & student union building/wing name for a session."""
    if session_id:
        existing = db.get_session_locations(session_id)
        for r in existing:
            for val in (r.get("primary_name") or "", r.get("zone_name") or ""):
                if val and any(k in val.lower() for k in ("cultural arts", "student union", "creative arts", "activities center", "arts & union")):
                    return val

    from namegen import generate_school_arts_wing_name
    h_val = int(session_id) if session_id else None
    return generate_school_arts_wing_name(scenario=scenario_key, hash_val=h_val)

def get_session_abandoned_campus_name(session_id: int = 0, scenario_key: str = "high_school_drama") -> str:
    """Retrieves or dynamically generates the abandoned old campus building/wing name for a session."""
    if session_id:
        existing = db.get_session_locations(session_id)
        for r in existing:
            for val in (r.get("primary_name") or "", r.get("zone_name") or ""):
                if val and any(k in val.lower() for k in ("abandoned old campus", "decaying clock tower", "old showa campus", "derelict old campus")):
                    return val

    from namegen import generate_school_abandoned_wing_name
    h_val = int(session_id) if session_id else None
    return generate_school_abandoned_wing_name(scenario=scenario_key, hash_val=h_val)

def get_session_airship_name(session_id: int = 0, scenario_key: str = "steampunk") -> str:
    """Generates a dynamic steampunk airship name."""
    from namegen import generate_airship_name
    h_val = int(session_id) if session_id else None
    return generate_airship_name(scenario=scenario_key, hash_val=h_val)

def get_session_player_house_name(session_id: int = 0, char_name: str = "", scenario_key: str = "high_school_drama") -> str:
    """Retrieves or dynamically generates the player residence name based on character's name."""
    clean_name = str(char_name or "").strip()
    if not clean_name and session_id:
        try:
            members = db.get_session_members(session_id)
            if members:
                char = db.get_character(members[0])
                if char and char.get("name"):
                    clean_name = char["name"].strip()
            if not clean_name:
                sess = db.get_session(session_id)
                if sess and sess.get("host_user_id"):
                    char = db.get_character(sess["host_user_id"])
                    if char and char.get("name"):
                        clean_name = char["name"].strip()
        except Exception:
            pass

    if session_id:
        existing = db.get_session_locations(session_id)
        for r in existing:
            p = r.get("primary_name") or ""
            if p and p not in ("Player's House", "Player House", "loc_player_house") and (
                "Residence" in p or "House" in p or "Apartment" in p or "Cottage" in p or "Living Quarters" in p
            ) and "Friend" not in p and "Aoi" not in p:
                if clean_name and (clean_name.split()[0].lower() in p.lower() or clean_name.split()[-1].lower() in p.lower()):
                    return p

    from namegen import generate_player_residence_name
    h_val = int(session_id) if session_id else None
    return generate_player_residence_name(char_name=clean_name, scenario=scenario_key, hash_val=h_val)

def get_session_zone_by_tag(session_id: int = 0, tag: str = "residential", scenario_key: str = "high_school_drama") -> str:
    """
    Returns the canonical zone name matching a semantic tag (e.g. 'residential', 'commercial', 'campus').
    """
    tag_clean = str(tag or "").lower().strip()
    if tag_clean == "residential":
        return get_session_residential_neighborhood_name(session_id, scenario_key)
    elif tag_clean == "commercial":
        return get_session_commercial_district_name(session_id, scenario_key)
    elif tag_clean in ("campus", "school"):
        return get_session_school_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""
    return ""

def resolve_npc_residence(session_id: int, npc_name: str, scenario_key: str = "high_school_drama") -> tuple[str, str]:
    """
    Resolves the canonical household residence for an NPC.
    - Surnamed NPCs generate '[Surname] Residence' (e.g. 'Anderson Residence').
    - Family members (siblings/shared surname) automatically reuse the same existing household.
    - Strictly anchored to the session's Residential Neighborhood zone.
    Returns (zone_name, primary_residence_name).
    """
    clean_name = str(npc_name or "").strip()
    res_zone = get_session_residential_neighborhood_name(session_id, scenario_key)

    if not clean_name:
        return (res_zone, "Friend's House")

    parts = clean_name.split()
    first_name = parts[0] if parts else clean_name
    surname = parts[-1] if len(parts) >= 2 else ""

    # If only first name was provided, attempt to resolve full name and surname from contacts / directory
    if len(parts) == 1 and session_id:
        try:
            contacts = db.get_contacts(session_id)
            for c in contacts:
                c_name = c.get("name", "")
                if c_name.lower().startswith(clean_name.lower()) and len(c_name.split()) >= 2:
                    clean_name = c_name
                    parts = clean_name.split()
                    first_name = parts[0]
                    surname = parts[-1]
                    break
        except Exception:
            pass

    # Check if NPC has known siblings or family relations from contacts / school directory
    sibling_names = []
    if session_id:
        try:
            contacts = db.get_contacts(session_id)
            for c in contacts:
                c_name = c.get("name", "")
                b_info = c.get("basic_info") or {}
                if isinstance(b_info, str):
                    try:
                        b_info = json.loads(b_info)
                    except Exception:
                        b_info = {}
                # If this is the target NPC, check their sibling_name
                c_low_parts = c_name.lower().split()
                if c_name.lower() == clean_name.lower() or (c_low_parts and first_name.lower() == c_low_parts[0] and len(first_name) >= 3):
                    sib = b_info.get("sibling_name")
                    if sib:
                        sibling_names.append(sib)
                # If another contact shares the same surname (and surname >= 3 chars)
                elif surname and len(surname) >= 3 and c_name.lower().endswith(surname.lower()):
                    sibling_names.append(c_name)
        except Exception:
            pass

    # Search existing session_locations for an already registered family household
    if session_id:
        existing = db.get_session_locations(session_id)
        # 1. Match by exact surname residence (e.g. "Anderson Residence")
        if surname and len(surname) >= 3:
            surname_match = next((
                r.get("primary_name") for r in existing
                if surname.lower() in (r.get("primary_name") or "").lower() and any(k in (r.get("primary_name") or "").lower() for k in ("residence", "house", "apartment", "manor", "cottage"))
            ), None)
            if surname_match:
                return (res_zone, surname_match)

        # 2. Match by sibling's name (e.g. if "Sofia's House" or "Maya's House" exists)
        for sib in sibling_names:
            sib_parts = sib.split()
            sib_first = sib_parts[0] if sib_parts else sib
            sib_match = next((
                r.get("primary_name") for r in existing
                if sib_first.lower() in (r.get("primary_name") or "").lower() and any(k in (r.get("primary_name") or "").lower() for k in ("residence", "house", "apartment", "manor", "cottage"))
            ), None)
            if sib_match:
                return (res_zone, sib_match)

        # 3. Match by target NPC's first name
        first_match = next((
            r.get("primary_name") for r in existing
            if first_name.lower() in (r.get("primary_name") or "").lower() and any(k in (r.get("primary_name") or "").lower() for k in ("residence", "house", "apartment", "manor", "cottage"))
        ), None)
        if first_match:
            return (res_zone, first_match)

    # If not already registered, generate standard name (preferring surname e.g. "Anderson Residence")
    canonical_residence = get_npc_residence_name(clean_name, scenario_key=scenario_key)

    # Save the new household (with full 4-room interior layout) to session_locations & world_nodes
    if session_id and res_zone:
        bedroom_label = f"{first_name}'s Bedroom" if first_name else "Bedroom"
        residence_rooms = ["Front Porch", "Living Room", "Kitchen", bedroom_label]
        try:
            existing_nodes = db.get_session_world_nodes(session_id)
            if existing_nodes:
                z_node_id = next(
                    (
                        n["node_id"]
                        for n in existing_nodes
                        if n["node_type"] == "ZONE"
                        and (n["name"].lower() == res_zone.lower() or n["node_id"] in ("zone_residential", "zone_suburbs", "zone_sol_residential"))
                    ),
                    None,
                )
                fac_exists = any(
                    n["node_type"] == "FACILITY" and n["name"].lower() == canonical_residence.lower()
                    for n in existing_nodes
                )
                if z_node_id and not fac_exists:
                    house_node_id = f"loc_{_slugify(clean_name)}_house"
                    db.save_world_node(
                        session_id=session_id,
                        node_id=house_node_id,
                        parent_id=z_node_id,
                        name=canonical_residence,
                        node_type="FACILITY",
                        category="residential",
                        privacy_level="private",
                        is_enclosed=1,
                        is_transit_hub=0,
                        access_tier="private",
                        is_dynamic=1,
                    )
                    sibling_facs = [
                        n["node_id"]
                        for n in existing_nodes
                        if n["node_type"] == "FACILITY" and n.get("parent_id") == z_node_id and n["node_id"] != house_node_id
                    ]
                    for sf_id in sibling_facs[:3]:
                        db.save_world_edge(session_id, house_node_id, sf_id, travel_minutes=5, edge_type="pathway", is_bidirectional=1)
        except Exception:
            pass

        for idx, sub_room in enumerate(residence_rooms):
            loc_id = f"sub_{_slugify(canonical_residence)}_{_slugify(sub_room)}"
            db.save_session_location(
                session_id=session_id,
                location_id=loc_id,
                zone_name=res_zone,
                primary_name=canonical_residence,
                sub_name=sub_room,
                is_dynamic=1,
            )

    return (res_zone, canonical_residence)

def get_npc_residence_name(npc_name: str, scenario_key: str = "high_school_drama") -> str:
    """Retrieves a formatted dynamic residence name for an NPC."""
    from namegen import generate_npc_residence_name
    return generate_npc_residence_name(npc_name=npc_name, scenario=scenario_key)

def get_session_player_desk_name(session_id: int = 0, char_name: str = "") -> str:
    """Retrieves or dynamically generates the player desk name based on character's name."""
    clean_name = str(char_name or "").strip()
    if not clean_name and session_id:
        try:
            members = db.get_session_members(session_id)
            if members:
                char = db.get_character(members[0])
                if char and char.get("name"):
                    clean_name = char["name"].strip()
            if not clean_name:
                sess = db.get_session(session_id)
                if sess and sess.get("host_user_id"):
                    char = db.get_character(sess["host_user_id"])
                    if char and char.get("name"):
                        clean_name = char["name"].strip()
        except Exception:
            pass

    if clean_name:
        if clean_name.lower().endswith(" desk"):
            return clean_name
        if clean_name.endswith("'s") or clean_name.endswith("’s"):
            return f"{clean_name} Desk"
        return f"{clean_name}'s Desk"
    return "Player's Desk"

def provision_faction_hq_tier2_location(session_id: int, faction_name: str, scen_key: str = "high_school_drama", hq_name: str = "") -> str:
    """
    Provisions a distinct, sensible Tier 2 Primary Location (and rich Tier 3 Sub-Areas)
    in SQLite for a newly discovered or created faction HQ.
    Returns the clean Tier 2 Primary Location name.
    """
    import db
    from scenario_data import has_tag
    from mechanics.social.factions import infer_default_hq_location
    
    primary_hq = (hq_name or "").strip() or infer_default_hq_location(faction_name, scen_key)
    hq_low = primary_hq.lower()
    
    # 1. Determine Tier 1 Zone (prefer an already-seeded real zone in the session so no synthetic 'World Region' is added)
    seeded_zones = []
    if session_id:
        try:
            seeded_zones = list(dict.fromkeys(
                r["zone_name"]
                for r in (db.get_session_locations(session_id) or [])
                if r.get("zone_name") and r["zone_name"] != "World Region"
            ))
        except Exception:
            seeded_zones = []

    if is_school_scenario(scen_key):
        target_zone = get_session_school_name(session_id, scen_key) or (seeded_zones[0] if seeded_zones else "Westlake Academy")
    elif seeded_zones:
        hub_match = next(
            (z for z in seeded_zones if any(k in z.lower() for k in ("city center", "capital", "downtown", "settlement", "station", "clocktower", "scavenger", "arcade"))),
            seeded_zones[0],
        )
        target_zone = hub_match
    elif has_tag(scen_key, "cyberpunk"):
        target_zone = "Night District"
    elif has_tag(scen_key, "fantasy") or has_tag(scen_key, "dark_fantasy"):
        target_zone = "Capital Citadel"
    elif has_tag(scen_key, "space") or has_tag(scen_key, "sci_fi"):
        target_zone = "Orbital Station Sector"
    elif has_tag(scen_key, "steampunk"):
        target_zone = "Clocktower City Center"
    elif has_tag(scen_key, "post_apocalypse") or "apocalypse" in str(scen_key).lower():
        target_zone = "Scavenger Market Settlement"
    else:
        target_zone = "Central District"

    # 2. Determine rich, sensible Tier 3 Rooms / Sub-Areas (each beginning with an entrance threshold)
    if any(k in hq_low for k in ("esport", "gaming", "game")):
        sub_list = ["Clubroom Entrance & Check-In", "Competitive PC Arena", "Strategy & Console Lounge"]
    elif any(k in hq_low for k in ("science", "robotics", "laboratory")) or re.search(r'\blabs?\b', hq_low):
        sub_list = ["Lab Entrance & Safety Station", "Robotics Assembly Bay", "Chemical Synthesis Chamber"]
    elif re.search(r'\b(art|arts|manga|anime|design)\b', hq_low):
        sub_list = ["Studio Entrance & Gallery Hall", "Drafting & Illustration Studio", "Supply & Print Archive Room"]
    elif any(k in hq_low for k in ("journalism", "newspaper", "media", "press")):
        sub_list = ["Newsroom Entrance & Copy Hall", "Editorial & Layout Office", "Soundproof Recording Booth"]
    elif any(k in hq_low for k in ("kendo", "martial", "dojo", "budo", "boxing")):
        sub_list = ["Dojo Sliding Doors Entrance", "Central Sparring Hall", "Armory & Meditation Alcove"]
    elif any(k in hq_low for k in ("music", "band", "orchestra", "rehearsal")):
        sub_list = ["Music Hall Sound-Lock Entrance", "Ensemble Rehearsal Room", "Soundproof Recording Booth"]
    elif any(k in hq_low for k in ("cooking", "culinary", "kitchen")):
        sub_list = ["Kitchen Pantry Entrance", "Main Culinary Prep Floor", "Tasting & Dining Room"]
    elif any(k in hq_low for k in ("astronomy", "dome", "stargazing")):
        sub_list = ["Observatory Stairwell Entrance", "Telescope Dome Rotunda", "Star Chart Archive Study"]
    elif any(k in hq_low for k in ("library", "literature", "reading", "book")):
        sub_list = ["Library Entrance Turnstiles", "Archive Book Stacks", "Quiet Reading Lounge"]
    elif any(k in hq_low for k in ("council", "stuco")):
        sub_list = ["Council Office Entrance Foyer", "Executive Conference Room", "Council Archive Vault"]
    elif any(k in hq_low for k in ("drama", "theater", "auditorium")):
        sub_list = ["Auditorium Double Doors Entrance", "Main Theater Stage", "Backstage Dressing Rooms"]
    elif any(k in hq_low for k in ("occult", "mystery", "storage")):
        sub_list = ["Warded Doorway Entrance", "Ritual Study Chamber", "Relic & Archive Vault"]
    elif any(k in hq_low for k in ("shed", "gym", "delinquent", "gang", "hideout")):
        sub_list = ["Alleyway Hideout Entrance", "Back-Lot Hangout Lounge", "Stash & Lookout Alcove"]
    elif any(k in hq_low for k in ("corp", "tower", "plaza")):
        sub_list = ["Security Lobby Entrance", "Executive Boardroom", "Skyline Operations Suite"]
    elif any(k in hq_low for k in ("subnet", "netrunner", "hacker")):
        sub_list = ["Airlocked Safehouse Entrance", "Deep Net Dive Bay", "Encrypted Server Vault"]
    elif any(k in hq_low for k in ("alchem", "apothecary", "potion", "distill", "brewing")):
        sub_list = ["Apothecary Front Entrance", "Distillation Laboratory", "Classified Reagent Vault"]
    elif any(k in hq_low for k in ("academy", "institute", "university", "research", "scholars", "conservatory")):
        sub_list = ["Institute Atrium Entrance", "Grand Lecture Amphitheater", "Faculty Research Vault"]
    elif any(k in hq_low for k in ("fleet", "navy", "aeronaut", "dirigible", "airship", "starship", "bridge", "gantry")):
        sub_list = ["Boarding Gangway Entrance", "Command Bridge & Helm", "Officers' Briefing Wardroom"]
    elif any(k in hq_low for k in ("union", "foundry", "boiler", "smelter", "labor hall", "machinist")):
        sub_list = ["Foundry Gatehouse Entrance", "Piston Forge Floor", "Union Steward's Office"]
    elif any(k in hq_low for k in ("merchant", "exchange", "bourse", "caravan", "trading post", "bank")):
        sub_list = ["Exchange Portico Entrance", "Ledger & Counting Hall", "Secured Bullion Vault"]
    elif any(k in hq_low for k in ("inquisit", "witch hunter", "purifier", "sanctum")):
        sub_list = ["Sanctum Gatehouse Entrance", "Sanctified Interrogation Hall", "Relic & Purging Armory"]
    elif any(k in hq_low for k in ("cult", "coven", "catacomb", "altar", "necroman", "eldritch")):
        sub_list = ["Ward-Sealed Threshold Entrance", "Chanting Catacomb Hall", "Forbidden Reliquary Vault"]
    elif any(k in hq_low for k in ("scavenger", "salvage", "scrapper", "scrapyard", "scrap", "prospector")):
        sub_list = ["Scrapyard Gate Checkpoint", "Salvage Sifting Bay", "Smelting & Trade Hall"]
    elif any(k in hq_low for k in ("guild", "hall", "order", "citadel")):
        sub_list = ["Guildhall Great Doors Entrance", "Main Mission & Banquet Hall", "Quartermaster Armory"]
    else:
        sub_list = [f"{primary_hq} Entrance", f"{primary_hq} Main Chamber", f"{primary_hq} Inner Office"]

    # 3. Save Tier 2 and Tier 3 entries into SQLite
    for sub in sub_list:
        loc_id = f"loc_{_slugify(target_zone)}_{_slugify(primary_hq)}_{_slugify(sub)}"
        db.save_session_location(
            session_id=session_id,
            location_id=loc_id,
            zone_name=target_zone,
            primary_name=primary_hq,
            sub_name=sub,
            atmosphere=f"The dedicated headquarters of {faction_name}.",
            is_dynamic=0
        )

    return primary_hq


ENTRANCE_KEYWORDS = (
    "entrance", "door", "foyer", "gate", "archway", "porch", "turnstile",
    "vestibule", "threshold", "portal", "entryway", "airlock", "hatch", "checkpoint"
)


def is_entrance_sublocation(name: str) -> bool:
    """Checks if a sublocation name represents a dedicated entrance/threshold."""
    low = str(name or "").lower()
    return any(k in low for k in ENTRANCE_KEYWORDS)


def get_facility_entrance_name(fac_name: str) -> str:
    """Deterministically derives a specific, relevant entrance sublocation name for a facility."""
    low = str(fac_name or "").lower().strip()
    if "homeroom" in low or "class" in low:
        return "Classroom Sliding Door Entrance" if "homeroom" in low else "Classroom Doorway Entrance"
    if "lab" in low or "chemistry" in low or "science" in low:
        return "Lab Entrance & Safety Station"
    if "library" in low or "archives" in low:
        return "Library Entrance Turnstiles"
    if "staff" in low or "faculty" in low:
        return "Staff Room Entrance Doorway"
    if "gym" in low:
        return "Gymnasium Double Doors Entrance"
    if "dojo" in low:
        return "Dojo Sliding Doors Entrance"
    if "pool" in low:
        return "Pool Facility Entrance & Footbath"
    if "roof" in low:
        return "Rooftop Heavy Access Door"
    if "dining" in low or "cafeteria" in low or "canteen" in low:
        return "Dining Hall Double Doors Entrance"
    if "auditorium" in low or "theater" in low or "stage" in low:
        return "Auditorium Double Doors Entrance"
    if "music" in low:
        return "Music Room Entrance Door"
    if "studio" in low or "arts" in low:
        return f"{fac_name} Entrance Doorway"
    if "broadcast" in low or "media" in low:
        return "Studio Sound-Lock Entrance"
    if "corridor" in low or "clubroom" in low:
        return "Club Corridor Entrance"
    if "office" in low or "council" in low:
        return "Council Office Entrance Doorway"
    if "courtyard" in low or "plaza" in low:
        return "Courtyard Archway Entrance"
    if "park" in low or "garden" in low:
        return "Park Entrance Arch"
    if "glasshouse" in low or "greenhouse" in low:
        return "Glasshouse Double Doors Entrance"
    if "pavilion" in low:
        return "Pavilion Entrance Walkway"
    if "café" in low or "cafe" in low:
        return "Café Front Glass Door"
    if "arcade" in low:
        return "Arcade Neon Entrance"
    if "karaoke" in low:
        return "Lounge Reception Entrance"
    if "convenience" in low or "store" in low or "shop" in low:
        return "Shop Front Entrance Door"
    if "house" in low or "residence" in low or "home" in low:
        return "Front Door & Genkan Entrance"
    if "tavern" in low or "inn" in low or "pub" in low:
        return "Tavern Heavy Oak Door"
    if "temple" in low or "shrine" in low or "chapel" in low or "church" in low or "sanctuary" in low:
        return "Sanctuary Grand Archway"
    if "dungeon" in low or "crypt" in low or "ruin" in low or "vault" in low:
        return "Stone Chamber Threshold"
    if "cave" in low or "cavern" in low or "mine" in low:
        return "Cavern Mouth Entrance"
    if "castle" in low or "keep" in low or "fort" in low or "palace" in low:
        return "Castle Great Gate"
    if "pier" in low or "dock" in low or "harbor" in low:
        return "Pier Entrance Ramp"
    if "beach" in low or "coast" in low:
        return "Beach Access Boardwalk"
    if "camp" in low or "cabin" in low:
        return "Campground Trailhead Entrance"
    if "shed" in low:
        return "Alleyway Storage Entrance"
    if "tower" in low or "clock" in low:
        return "Arched Tower Doorway"
    return f"{fac_name} Entrance"


def get_contextual_interior_name(fac_name: str) -> str:
    """Deterministically derives a descriptive, non-generic room/area name to replace 'Main Area'."""
    low = str(fac_name or "").lower().strip()
    if "homeroom" in low or "class" in low:
        return "Student Desks Cluster"
    if "lab" in low or "chemistry" in low or "science" in low:
        return "Lab Workbenches"
    if "library" in low or "archives" in low:
        return "Study Tables"
    if "staff" in low or "faculty" in low:
        return "Faculty Desks"
    if "gym" in low or "dojo" in low:
        return "Basketball Court" if "gym" in low else "Central Tatami Mat"
    if "pool" in low:
        return "Poolside Deck"
    if "roof" in low:
        return "Rooftop Benches"
    if "dining" in low or "cafeteria" in low or "canteen" in low:
        return "Central Dining Tables"
    if "auditorium" in low or "theater" in low or "stage" in low:
        return "Auditorium Stage"
    if "music" in low:
        return "Upright Piano Alcove"
    if "studio" in low or "arts" in low:
        return "Easel & Drafting Desks"
    if "broadcast" in low or "media" in low:
        return "Newspaper Layout Desk"
    if "corridor" in low or "clubroom" in low:
        return "Shared Club Noticeboard"
    if "office" in low or "council" in low:
        return "Meeting Table"
    if "courtyard" in low or "plaza" in low:
        return "Central Courtyard Plaza"
    if "park" in low or "garden" in low:
        return "Park Grounds"
    if "glasshouse" in low or "greenhouse" in low:
        return "Interior Greenery Path"
    if "pavilion" in low:
        return "Vending Machines Area"
    if "café" in low or "cafe" in low:
        return "Main Seating Lounge"
    if "arcade" in low:
        return "Fighting Game Cabinets"
    if "karaoke" in low:
        return "Private Karaoke Room"
    if "convenience" in low or "store" in low or "shop" in low:
        return "Cash Register & Aisles"
    if "house" in low or "residence" in low or "home" in low:
        return "Living Room"
    if "tavern" in low or "inn" in low or "pub" in low:
        return "Common Room & Hearth"
    if "temple" in low or "shrine" in low or "chapel" in low:
        return "Main Sanctuary"
    if "dungeon" in low or "crypt" in low or "vault" in low:
        return "Central Chamber"
    if "cave" in low or "cavern" in low:
        return "Central Cavern"
    if "castle" in low or "keep" in low:
        return "Great Hall"
    if "pier" in low or "dock" in low:
        return "Pier Railing Lookout"
    if "beach" in low or "coast" in low:
        return "Beach Towel Spot"
    return f"{fac_name} Central Area"


def get_facility_contextual_sublocations(primary_name: str, existing_subs: list[dict] = None) -> list[dict]:
    """
    Ensures a facility has an Entrance sublocation (index 0) and contextual, non-generic room names.
    Replaces any 'Main Area' sublocations with facility-appropriate names.
    """
    subs = list(existing_subs or [])
    new_subs = []
    has_entrance = False

    for s in subs:
        s_dict = dict(s)
        s_name = s_dict.get("name", "").strip()
        # Rename generic "Main Area"
        if s_name.lower() in ("main area", "area", "main"):
            s_dict["name"] = get_contextual_interior_name(primary_name)
            s_dict["id"] = f"sub_{_slugify(primary_name)}_{_slugify(s_dict['name'])}"
        if s_dict.get("is_entrance") or is_entrance_sublocation(s_dict["name"]):
            has_entrance = True
        new_subs.append(s_dict)

    if not has_entrance:
        ent_name = get_facility_entrance_name(primary_name)
        ent_sub = {
            "id": f"sub_{_slugify(primary_name)}_entrance",
            "name": ent_name,
            "is_entrance": 1
        }
        new_subs.insert(0, ent_sub)

    if len(new_subs) == 1 and (new_subs[0].get("is_entrance") or is_entrance_sublocation(new_subs[0]["name"])):
        int_name = get_contextual_interior_name(primary_name)
        int_sub = {
            "id": f"sub_{_slugify(primary_name)}_{_slugify(int_name)}",
            "name": int_name
        }
        new_subs.append(int_sub)

    return new_subs


def get_room_contextual_props(room_name: str, primary_name: str = "") -> list[str]:
    """
    Deterministically derives 3-4 appropriate interactive room props / focal anchors
    for a Tier 3 room or sub-location when explicit props are not authored in seed data.
    """
    low = f"{room_name or ''} {primary_name or ''}".lower().strip()
    r_clean = str(room_name or primary_name or "Room").strip()

    if "homeroom" in low or "class" in low or "lecture" in low:
        return ["Classroom Sliding Door", "Student Desks", "Teacher's Podium", "Back Window"]
    if "library" in low or "archive" in low or "reading" in low:
        return ["Study Tables", "Book Aisles", "Librarian Counter", "Quiet Reading Alcove"]
    if "lab" in low or "chemistry" in low or "science" in low or "research" in low:
        return ["Lab Workbenches", "Chemical Storage Closet", "Fume Hood Station", "Safety Station"]
    if "staff" in low or "faculty" in low or "counselor" in low:
        return ["Faculty Desks", "Print & Copy Corner", "Filing Cabinets", "Guidance Alcove"]
    if "council" in low or "office" in low or "dispatch" in low or "executive" in low:
        return ["Executive Desk", "Central Meeting Table", "Filing Cabinets & Safe", "Window Ledge"]
    if "roof" in low:
        return ["Rooftop Benches", "Chain-Link Fence Line", "Behind Water Tank", "Heavy Access Door"]
    if "gate" in low or "checkpoint" in low:
        return ["Entrance Path & Archway", "Gate Checkpoint", "Notice Board & Banners", "Front Bicycle Racks"]
    if "foyer" in low or "lobby" in low or "shoe locker" in low:
        return ["Shoe Lockers", "Main Entrance Lobby", "Announcement Board", "Reception Bench"]
    if "hallway" in low or "corridor" in low:
        return ["Behind the Stairwell", "Locker Row", "Noticeboard Wall", "Corridor Window"]
    if "gym" in low or "court" in low:
        return ["Basketball Court", "Upper Concourse Bleachers", "Equipment Storeroom", "Sideline Benches"]
    if "field" in low or "track" in low or "stadium" in low:
        return ["Running Track", "Field Bleachers", "Under the Bleachers", "Soccer Goal Posts"]
    if "pool" in low or "aquatic" in low:
        return ["Poolside Deck", "Starting Blocks", "Swim Club Locker Bench", "Footbath Threshold"]
    if "dojo" in low or "martial" in low or "tatami" in low:
        return ["Central Tatami Mat", "Wooden Weapon Rack", "Meditation Altar", "Sliding Doors"]
    if "shed" in low or "alley" in low:
        return ["Hangout Benches", "Behind Equipment Shed", "Chain-Link Fence Corner", "Stacked Crates"]
    if "dining" in low or "cafeteria" in low or "canteen" in low:
        return ["Central Dining Tables", "Lunch Serving Line", "Corner Window Booth", "Beverage Counter"]
    if "vending" in low or "pavilion" in low:
        return ["Drinks Vending Row", "Hot Snack Machines", "Covered Benches", "Recycling Bins"]
    if "glasshouse" in low or "greenhouse" in low or "botanical" in low:
        return ["Interior Greenery Path", "Potting Workbench", "Secluded Fern Corner", "Glass Canopy Arch"]
    if "courtyard" in low or "plaza" in low or "park" in low or "garden" in low:
        return ["Central Fountain Bench", "Shaded Tree Path", "Stone Seating Ledge", "Walkway Lamp Post"]
    if "auditorium" in low or "stage" in low or "theater" in low:
        return ["Main Stage", "Backstage Curtain Wings", "Velvet Seating Rows", "Lighting Control Booth"]
    if "music" in low or "piano" in low or "band" in low:
        return ["Upright Piano", "Sheet Music Stands", "Soundproof Practice Booth", "Instrument Rack"]
    if "studio" in low or "art" in low:
        return ["Easel & Drafting Desks", "Supply Storage Cabinets", "Still-Life Platform", "Wash Sink"]
    if "broadcast" in low or "media" in low or "newspaper" in low:
        return ["Audio Mixing Console", "Recording Mic Booth", "Layout Worktable", "On-Air Signal Light"]
    if "storage" in low or "closet" in low or "vault" in low or "containment" in low:
        return ["Stacked Storage Shelving", "Locked Supply Cabinet", "Corner Workbench", "Heavy Security Door"]
    if "clock tower" in low or "belfry" in low:
        return ["Spiral Iron Staircase", "Frozen Clockwork Gears", "Belfry Observation Ledge", "Dusty Railing"]
    if "armory" in low or "outfitter" in low or "weapon" in low:
        return ["Quartermaster Counter", "Secured Weapon Racks", "Tactical Gear Lockers", "Ammunition Crate"]
    if "medical" in low or "infirmary" in low or "clinic" in low or "triage" in low:
        return ["Examination Bed", "Privacy Curtain", "Medicine Supply Cabinet", "Diagnostic Monitor"]
    if "dorm" in low or "bedroom" in low or "living" in low or "quarters" in low:
        return ["Study Desk", "Bed & Nightstand", "Window Ledge", "Wardrobe & Bookshelf"]
    if "café" in low or "cafe" in low or "bakery" in low or "tea" in low:
        return ["Window Booth", "Espresso & Pastry Counter", "Corner Table", "Menu Chalkboard"]
    if "arcade" in low or "game" in low:
        return ["Fighting Game Cabinets", "Rhythm Game Stage", "Prize Redemption Counter", "Token Change Machine"]
    if "shop" in low or "store" in low or "market" in low:
        return ["Checkout Counter", "Display Aisles", "Window Display", "Stockroom Door"]
    if "tavern" in low or "inn" in low or "pub" in low or "bar" in low:
        return ["Bar Counter", "Hearthside Tables", "Secluded Corner Booth", "Bounty Notice Board"]
    return [f"{r_clean} Entrance", f"{r_clean} Central Area", "Secluded Corner Alcove"]


def get_node_props(
    session_id: int,
    node_id: str,
    scenario_key: str = "high_school_drama",
    char_name: str = "",
) -> list[str]:
    """
    Returns the list of interactive micro-location props for a given spatial node.
    Checks:
      1. Custom runtime state (`world_nodes.state_json["props"]`)
      2. Authored `"props"` in `data/locations_seed.json` (with session personalization)
      3. Deterministic archetype props via `get_room_contextual_props`
    """
    nid = str(node_id or "").strip()
    node_name = ""
    if isinstance(session_id, str) and not session_id.isdigit():
        nid = session_id.strip()
        node_name = str(node_id or "").strip()
        session_id = 0

    if session_id and nid:
        try:
            st = db.get_world_node_state(session_id, nid)
            if isinstance(st, dict) and isinstance(st.get("props"), list) and st["props"]:
                return [str(p) for p in st["props"] if p]
        except Exception:
            pass

    parent_name = ""
    if session_id and nid:
        try:
            n_row = db.get_world_node(session_id, nid)
            if n_row:
                node_name = n_row.get("name") or ""
                p_id = n_row.get("parent_id") or n_row.get("parent_node_id") or ""
                if p_id:
                    p_row = db.get_world_node(session_id, p_id)
                    if p_row:
                        parent_name = p_row.get("name") or ""
        except Exception:
            pass

    seed_data = get_scenario_seed_data(scenario_key)
    seed_zones = seed_data.get("zones", [])
    if is_urban_anomalous_scenario(scenario_key):
        seed_zones = inject_anomalous_faction_hq_facilities(seed_zones, session_id=session_id, scenario_key=scenario_key)
    desk_name = get_session_player_desk_name(session_id, char_name=char_name) if is_school_scenario(scenario_key) else "Player's Desk"

    for z in seed_zones:
        for p in z.get("primary_locations", []):
            p_id = p.get("id") or ""
            p_name = p.get("name") or ""
            if (nid and p_id == nid) or (node_name and p_name.lower() == node_name.lower()):
                if isinstance(p.get("props"), list) and p["props"]:
                    return [desk_name if pr == "Player's Desk" else str(pr) for pr in p["props"]]
            for s in p.get("sub_locations", []):
                if isinstance(s, dict):
                    s_id = s.get("id") or ""
                    s_name = s.get("name") or ""
                    if (nid and s_id == nid) or (node_name and s_name.lower() == node_name.lower()):
                        if isinstance(s.get("props"), list) and s["props"]:
                            return [desk_name if pr == "Player's Desk" else str(pr) for pr in s["props"]]

    return get_room_contextual_props(node_name or nid, parent_name)



