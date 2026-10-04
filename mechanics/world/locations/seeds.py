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
    "grimdark": "dark_fantasy",
    "dark_fantasy": "dark_fantasy",
    "isekai": "isekai_fantasy",
    "isekai_fantasy": "isekai_fantasy",
    "high_school": "high_school_drama",
    "high_school_drama": "high_school_drama",
    "post_apocalypse": "nuclear_post_apocalypse",
    "nuclear_post_apocalypse": "nuclear_post_apocalypse",
    "cyberpunk": "cyberpunk",
    "steampunk": "steampunk",
    "fantasy": "fantasy",
}

def get_scenario_seed_data(scenario_key: str) -> dict:
    """Helper to get seed data for scenario or combine zones across all active tags for multi-genre custom scenarios."""
    data = _load_seeds()
    if not scenario_key:
        return data.get("fantasy") or data.get("high_school_drama") or {}
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
    return scen_data

def is_school_scenario(scenario_key: str) -> bool:
    """Checks if scenario is an academic/school or modern slice-of-life setting."""
    scen = str(scenario_key or "").lower().strip()
    if any(k in scen for k in ("high_school", "school", "furry_high_school", "academy", "slice_of_life")):
        return True
    try:
        from scenario_data import has_tag
        return bool(
            has_tag(scen, "high_school")
            or has_tag(scen, "high_school_drama")
            or has_tag(scen, "slice_of_life")
        )
    except Exception:
        return False

def get_session_school_name(session_id: int = 0, scenario_key: str = "high_school_drama") -> str:
    """Retrieves or deterministically generates the unique dynamic school name for a session."""
    if session_id:
        existing = db.get_session_locations(session_id)
        for r in existing:
            z = r.get("zone_name") or ""
            if z and z not in ("Main Academy Campus", "Main Academy Building") and z not in (
                "Commercial District", "Residential District", "Residential Neighborhood",
                "School Grounds & Athletics", "Local Park & Waterfront", "World Region",
                "Starting Zone", "Main Area", "Seaside & Coastal Bay", "Recreational Mountain Park"
            ):
                if r.get("primary_name") in (
                    "Homeroom Classroom", "Empty Classroom", "School Hallways", "2F Hallway",
                    "Teachers' Staff Room", "School Library", "Chemistry & Science Lab",
                    "School Rooftop", "Gymnasium", "Main Gymnasium"
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
            p = r.get("primary_name") or ""
            if p and p != "Homeroom Classroom" and "Homeroom" in p:
                return p

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
    """Retrieves or dynamically generates the unique commercial district name for a session."""
    if session_id:
        existing = db.get_session_locations(session_id)
        for r in existing:
            z = r.get("zone_name") or ""
            if z and z != "Commercial District":
                if any(sk in z for sk in ("School", "Academy", "Campus", "Commons", "Athletics", "Arts", "Abandoned")):
                    continue
                if any(k in z for k in ("Commercial", "Shopping", "Promenade", "Arcade", "Avenue", "Strip", "Market")):
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
            if z and z != "Residential Neighborhood" and any(k in z for k in ("Residential", "Suburban", "Quarter", "Heights", "Miyamae", "Sakura Hill", "Midori-cho")):
                return z

    from namegen import generate_residential_neighborhood_name
    h_val = int(session_id) if session_id else None
    return generate_residential_neighborhood_name(scenario=scenario_key, hash_val=h_val)

def get_session_athletics_complex_name(session_id: int = 0, scenario_key: str = "high_school_drama") -> str:
    """Retrieves or dynamically generates the athletics complex zone name for a session."""
    if session_id:
        existing = db.get_session_locations(session_id)
        for r in existing:
            z = r.get("zone_name") or ""
            if z and any(k in z.lower() for k in ("athletics", "grounds", "sports complex", "stadium")):
                return z

    from namegen import generate_school_athletics_name
    h_val = int(session_id) if session_id else None
    return generate_school_athletics_name(scenario=scenario_key, hash_val=h_val)

def get_session_student_commons_name(session_id: int = 0, scenario_key: str = "high_school_drama") -> str:
    """Retrieves or dynamically generates the student commons & central plaza zone name for a session."""
    if session_id:
        existing = db.get_session_locations(session_id)
        for r in existing:
            z = r.get("zone_name") or ""
            if z and any(k in z.lower() for k in ("commons", "central plaza", "courtyard & dining", "promenade & commons")):
                return z

    from namegen import generate_school_commons_name
    h_val = int(session_id) if session_id else None
    return generate_school_commons_name(scenario=scenario_key, hash_val=h_val)

def get_session_cultural_arts_name(session_id: int = 0, scenario_key: str = "high_school_drama") -> str:
    """Retrieves or dynamically generates the cultural arts & student union zone name for a session."""
    if session_id:
        existing = db.get_session_locations(session_id)
        for r in existing:
            z = r.get("zone_name") or ""
            if z and any(k in z.lower() for k in ("cultural arts", "student union", "creative arts", "activities center", "arts & union")):
                return z

    from namegen import generate_school_arts_wing_name
    h_val = int(session_id) if session_id else None
    return generate_school_arts_wing_name(scenario=scenario_key, hash_val=h_val)

def get_session_abandoned_campus_name(session_id: int = 0, scenario_key: str = "high_school_drama") -> str:
    """Retrieves or dynamically generates the abandoned old campus zone name for a session."""
    if session_id:
        existing = db.get_session_locations(session_id)
        for r in existing:
            z = r.get("zone_name") or ""
            if z and any(k in z.lower() for k in ("abandoned old campus", "decaying clock tower", "old showa campus", "derelict old campus")):
                return z

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

    # Save the new household to session_locations
    if session_id and res_zone:
        loc_id = f"loc_{_slugify(res_zone)}_{_slugify(canonical_residence)}_front_porch"
        db.save_session_location(
            session_id=session_id,
            location_id=loc_id,
            zone_name=res_zone,
            primary_name=canonical_residence,
            sub_name="Front Porch",
            is_dynamic=1
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
    
    # 1. Determine Tier 1 Zone
    if is_school_scenario(scen_key):
        school_name = get_session_school_name(session_id, scen_key) or "Westlake Academy"
        athletics_name = get_session_athletics_complex_name(session_id, scen_key)
        commons_name = get_session_student_commons_name(session_id, scen_key)
        arts_name = get_session_cultural_arts_name(session_id, scen_key)
        abandoned_name = get_session_abandoned_campus_name(session_id, scen_key)

        if any(k in hq_low for k in ("gym", "field", "shed", "track", "outdoor", "court", "sheds", "brawler", "delinquent", "sports", "martial", "tatami")):
            target_zone = athletics_name
        elif any(k in hq_low for k in ("commons", "cafeteria", "canteen", "vending", "greenhouse", "courtyard", "garden")):
            target_zone = commons_name
        elif any(k in hq_low for k in ("council", "stuco", "drama", "auditorium", "music", "piano", "art", "media", "broadcast", "club", "esport", "gaming")):
            target_zone = arts_name
        elif any(k in hq_low for k in ("occult", "mystery", "abandoned", "clock tower", "derelict", "storage room 3")):
            target_zone = abandoned_name
        else:
            target_zone = school_name
    elif has_tag(scen_key, "cyberpunk"):
        target_zone = "Night District"
    elif has_tag(scen_key, "fantasy") or has_tag(scen_key, "dark_fantasy"):
        target_zone = "Capital Citadel"
    elif has_tag(scen_key, "space") or has_tag(scen_key, "sci_fi"):
        target_zone = "Orbital Station Sector"
    else:
        target_zone = "World Region"

    # 2. Determine rich, sensible Tier 3 Sub-Areas
    if any(k in hq_low for k in ("esport", "gaming", "game")):
        sub_list = ["PC Battle Stations", "Strategy Meeting Area", "Console Lounge & Trophy Shelf"]
    elif any(k in hq_low for k in ("science", "robotics", "laboratory")) or re.search(r'\blabs?\b', hq_low):
        sub_list = ["Robotics Workbench", "Chemical Synthesis Station", "Central Testing Array"]
    elif re.search(r'\b(art|arts|manga|anime|design)\b', hq_low):
        sub_list = ["Easel & Drafting Desks", "Digital Tablets & Lightboxes", "Gallery Display Wall"]
    elif any(k in hq_low for k in ("journalism", "newspaper", "media", "press")):
        sub_list = ["Chief Editor's Desk", "Layout & Printing Workstations", "Interview Recording Booth"]
    elif any(k in hq_low for k in ("kendo", "martial", "dojo", "budo", "boxing")):
        sub_list = ["Central Tatami Mat", "Wooden Weapon Rack", "Meditation & Trophy Altar"]
    elif any(k in hq_low for k in ("music", "band", "orchestra", "rehearsal")):
        sub_list = ["Soundproof Recording Booth", "Instrument Storage & Racks", "Ensemble Rehearsal Stage"]
    elif any(k in hq_low for k in ("cooking", "culinary", "kitchen")):
        sub_list = ["Commercial Cooking Range", "Prep & Cutting Islands", "Dining & Tasting Counter"]
    elif any(k in hq_low for k in ("astronomy", "dome", "stargazing")):
        sub_list = ["Main Telescope Platform", "Star Chart Plotting Desk", "Observation Dome Hatch"]
    elif any(k in hq_low for k in ("library", "literature", "reading", "book")):
        sub_list = ["Archive Book Stacks", "Quiet Reading Alcoves", "Senior Librarian's Desk"]
    elif any(k in hq_low for k in ("council", "stuco")):
        sub_list = ["President's Desk", "Council Meeting Table", "Archive Files & Safe"]
    elif any(k in hq_low for k in ("drama", "theater", "auditorium")):
        sub_list = ["Auditorium Main Stage", "Backstage Dressing Rooms", "Prop & Costume Storage"]
    elif any(k in hq_low for k in ("occult", "mystery", "storage")):
        sub_list = ["Ritual Circle & Altar", "Cursed Artifact Shelves", "Divination Corner"]
    elif any(k in hq_low for k in ("shed", "gym", "delinquent", "gang", "hideout")):
        sub_list = ["Hideout Benches & Couch", "Lookout Point", "Graffiti Wall & Stash"]
    elif any(k in hq_low for k in ("corp", "tower", "plaza")):
        sub_list = ["Executive Boardroom", "Data Vault Terminal", "Skyline View Lounge"]
    elif any(k in hq_low for k in ("subnet", "netrunner", "hacker")):
        sub_list = ["Deep Net Access Pods", "Encrypted Server Racks", "Operative Safehouse"]
    elif any(k in hq_low for k in ("alchem", "apothecary", "potion", "distill", "brewing")):
        sub_list = ["Brewing & Distillation Station", "Reagent Vault & Ingredient Shelves", "Classified Alchemical Archive"]
    elif any(k in hq_low for k in ("academy", "institute", "university", "research", "scholars", "conservatory")):
        sub_list = ["Grand Lecture Amphitheater", "Faculty Archive & Research Vault", "Experimental Study Chamber"]
    elif any(k in hq_low for k in ("fleet", "navy", "aeronaut", "dirigible", "airship", "starship", "bridge", "gantry")):
        sub_list = ["Bridge & Navigation Helm", "Flight Deck & Launch Catapult", "Officer's Mess & Briefing Room"]
    elif any(k in hq_low for k in ("union", "foundry", "boiler", "smelter", "labor hall", "machinist")):
        sub_list = ["Piston Foundry & Forge Floor", "Union Steward's Office", "Boiler Pressure Testing Array"]
    elif any(k in hq_low for k in ("merchant", "exchange", "bourse", "caravan", "trading post", "bank")):
        sub_list = ["Bourse & Ledger Counting Room", "Vault & Secured Lockboxes", "Caravan Staging Yard"]
    elif any(k in hq_low for k in ("inquisit", "witch hunter", "purifier", "sanctum")):
        sub_list = ["Sanctified Interrogation Chamber", "Relic & Purging Armory", "Lord Inquisitor's Private Quarters"]
    elif any(k in hq_low for k in ("cult", "coven", "catacomb", "altar", "necroman", "eldritch")):
        sub_list = ["Sacrificial Obsidian Altar", "Forbidden Reliquary & Tome Shelves", "Chanting Catacomb Vault"]
    elif any(k in hq_low for k in ("scavenger", "salvage", "scrapper", "scrapyard", "scrap", "prospector")):
        sub_list = ["Salvage Sifting Bay", "Scrap Smelting Crucible", "Prospector's Trade Outpost"]
    elif any(k in hq_low for k in ("guild", "hall", "order", "citadel")):
        sub_list = ["Guildmaster's Dais", "Bounty & Mission Board", "Armory & Supply Depot"]
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

