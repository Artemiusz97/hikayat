from __future__ import annotations
from .constants import *
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import db
from .seeds import *
from .seeds import _load_seeds, _slugify, _SEED_PATH

def is_invalid_location_string(name: str) -> bool:

    """

    Returns True if the string is an action, quest objective, or narrative sentence

    rather than a grounded physical location name.

    """

    if not name or not str(name).strip():

        return True

    clean = str(name).strip().lower()



    # 1. Objective / Action verb clauses (e.g. "the library to intercept the Burn Book notes")

    objective_markers = [

        r"\bto (intercept|find|defeat|slay|kill|talk|speak|investigate|search|avoid|collect|gather|deliver|protect|steal|retrieve|discover|confront|rescue|track|scout|meet|acquire|inquire|bypass|eliminate|clear|explore|infiltrate|study|examine|obtain|secure|reach|halt|stop)\b",
        r"\bin order to\b",
        r"\b(slink into|head over to|sneak past|search for|look for|pick up|gain entry to|break into|climb up to)\b",
        r"\b(notes|rumors|evidence|secrets|patrol|participants|culprit|target|plans|orders)\b.*?\b(in|at|near|behind|around)\b"

    ]

    for pat in objective_markers:

        if re.search(pat, clean):

            return True



    # 2. Too many words without delimiters (5+ words is almost always a narrative objective or sentence)
    if "➔" not in clean and "->" not in clean and ">" not in clean and "|" not in clean:
        words = clean.split()
        if len(words) >= 5:
            # Check if this is a known physical establishment or seed location noun (e.g. "Old East Wing Music Room")
            physical_place_nouns = (
                "room", "wing", "hall", "building", "academy", "office", "courtyard",
                "station", "pavilion", "sanctuary", "temple", "shrine", "center",
                "centre", "club", "dorm", "dormitory", "lounge", "plaza", "grounds",
                "garden", "annex", "district", "quarter", "library", "store", "shop",
                "cafe", "cafeteria", "canteen", "lab", "laboratory", "gym", "gymnasium",
                "field", "rooftop", "roof", "auditorium", "theater", "theatre",
                "infirmary", "clinic", "terrace", "balcony", "park", "avenue", "street", "alley"
            )
            if not any(pn in clean for pn in physical_place_nouns) or len(words) >= 8:
                return True

    return False

def get_facility_entrance_sublocation(primary_name: str, session_id: int = 0, scen_key: str = "high_school_drama") -> str:
    """
    Finds or derives the canonical Entrance sublocation for a primary facility.
    Checks session_locations and world_nodes first; falls back to deterministic rule.
    """
    if not primary_name:
        return "Entrance"
    if session_id:
        try:
            nodes = db.get_session_world_nodes(session_id)
            fac_node = next((n for n in nodes if n["node_type"] == "FACILITY" and n["name"].lower() == primary_name.lower()), None)
            if fac_node:
                ent_room = next((rn for rn in nodes if rn["node_type"] == "ROOM" and rn.get("parent_id") == fac_node["node_id"] and is_entrance_sublocation(rn["name"])), None)
                if ent_room:
                    return ent_room["name"]
        except Exception:
            pass
        try:
            existing = db.get_session_locations(session_id)
            for r in existing:
                if r.get("primary_name", "").lower() == primary_name.lower():
                    s_name = r.get("sub_name", "")
                    if is_entrance_sublocation(s_name):
                        return s_name
        except Exception:
            pass
    return get_facility_entrance_name(primary_name)


def sanitize_location_target(raw_target: str, session_id: int = 0, scen_key: str = "fantasy", char_name: str = "") -> str:

    """

    Sanitizes raw waypoint/LLM target strings into clean physical location names.

    E.g. 'the library to intercept the Burn Book notes' -> 'Oakridge Academy ➔ School Library ➔ Library Entrance Turnstiles'

    """

    if not raw_target or not str(raw_target).strip():

        z, p, s = get_default_tiered_location(scen_key, session_id=session_id, char_name=char_name)

        return format_tiered_location_string(z, p, s)

    clean_raw = re.sub(r"[*_`]", "", str(raw_target)).strip()
    clean_raw = re.sub(r"\s*->\s*|\s*-->\s*", " ➔ ", clean_raw)

    # If already a valid, clean location name
    if not is_invalid_location_string(clean_raw):
        return clean_raw

    # Check if a known registered physical place in session matches any part of raw_target
    if session_id:
        existing = db.get_session_locations(session_id)
        raw_lower = clean_raw.lower()
        for r in existing:
            p_name = r.get("primary_name", "")
            if p_name:
                p_lower = p_name.lower()
                # Check direct inclusion of primary name
                if p_lower in raw_lower:
                    z_name = r.get("zone_name") or ""
                    ent_sub = get_facility_entrance_sublocation(p_name, session_id=session_id, scen_key=scen_key)
                    return format_tiered_location_string(z_name, p_name, ent_sub) if z_name else p_name

                # Check root keyword (e.g. "library" in "the library to intercept...")
                p_words = [w for w in p_lower.replace("'", "").replace("&", " ").split() if len(w) >= 4 and w not in ("school", "main", "hall", "room", "area", "house", "grounds", "place")]
                if p_words and any(pw in raw_lower for pw in p_words):
                    z_name = r.get("zone_name") or ""
                    ent_sub = get_facility_entrance_sublocation(p_name, session_id=session_id, scen_key=scen_key)
                    return format_tiered_location_string(z_name, p_name, ent_sub) if z_name else p_name

    # If no existing match, strip trailing objective clause: e.g. "the library to intercept..." -> "Library"
    to_idx = -1
    for marker in (" to ", " in order to ", " and steal ", " and find ", " and search ", " to avoid ", " to intercept ", " to bypass ", " to eliminate "):
        idx = clean_raw.lower().find(marker)
        if idx != -1:
            to_idx = idx
            break

    if to_idx != -1:
        extracted = clean_raw[:to_idx].strip()
        if extracted.lower().startswith("the "):
            extracted = extracted[4:].strip().title()
        if extracted:
            if "➔" in extracted:
                return extracted
            z_default, _, _ = get_default_tiered_location(scen_key, session_id=session_id, char_name=char_name)
            ent_sub = get_facility_entrance_sublocation(extracted.title(), session_id=session_id, scen_key=scen_key)
            return format_tiered_location_string(z_default, extracted.title(), ent_sub)



    # Fallback to default

    z, p, s = get_default_tiered_location(scen_key, session_id=session_id, char_name=char_name)

    return format_tiered_location_string(z, p, s)

def process_llm_location_update(session_id: int, raw_location: str, scenario_key: str = "high_school_drama", char_name: str = "") -> str:

    """

    Parses LLM output location, saves location node to SQLite if new,

    and returns a clean formatted 3-tiered location string.

    """

    if not is_location_engine_enabled(scenario_key):

        return raw_location or ""



    ensure_session_locations_seeded(session_id, scenario_key, char_name=char_name)

    # Clean markdown and delimiters from raw_location
    if raw_location:
        raw_location = re.sub(r"[*_`]", "", str(raw_location)).strip()
        raw_location = re.sub(r"\s*->\s*|\s*-->\s*", " ➔ ", raw_location)

    # Sanitize invalid objective/sentence strings before parsing
    if is_invalid_location_string(raw_location):
        raw_location = sanitize_location_target(raw_location, session_id=session_id, scen_key=scenario_key, char_name=char_name)

    zone, primary, sub = parse_tiered_location(raw_location, scenario_key, session_id=session_id, char_name=char_name)

    # Clean any surviving markdown from components
    zone = re.sub(r"[*_`]", "", str(zone)).strip()
    primary = re.sub(r"[*_`]", "", str(primary)).strip()
    sub = re.sub(r"[*_`]", "", str(sub)).strip()

    # If primary is still detected as invalid objective sentence or poetic drift
    if is_invalid_location_string(primary) or is_poetic_drift_title(primary):
        sanitized_p = sanitize_location_target(primary, session_id=session_id, scen_key=scenario_key, char_name=char_name)
        _, primary, _ = parse_tiered_location(sanitized_p, scenario_key, session_id=session_id, char_name=char_name)

    # If sub is detected as invalid objective sentence or contains action markers
    if is_invalid_location_string(sub):
        for marker in (" to ", " in order to ", " and steal ", " and find ", " and search ", " to avoid ", " to intercept ", " to bypass ", " to eliminate "):
            m_idx = sub.lower().find(marker)
            if m_idx != -1:
                sub = sub[:m_idx].strip()
                break
        if not sub or is_invalid_location_string(sub):
            sub = "Main Area"

    if is_incongruous_container(primary, sub, session_id=session_id, scenario_key=scenario_key):
        zone, primary, sub = auto_heal_incongruous_location(zone, primary, sub, session_id=session_id, scenario_key=scenario_key)



    # STEP 1: Run tier-identity normalization FIRST (before computing loc_id or saving).

    # This ensures any surviving chimera is resolved before it can poison the spatial index.

    from .hierarchy import _build_session_zone_index, _build_session_spatial_index
    zones_index = _build_session_zone_index(session_id, scenario_key)

    primaries, subs_idx = _build_session_spatial_index(session_id, scenario_key)

    p_low = primary.strip().lower()

    s_low = sub.strip().lower()

    if s_low in zones_index or s_low in primaries or p_low in zones_index:

        rev = _resolve_reverse_hierarchy([zone, primary, sub], scenario_key=scenario_key, session_id=session_id, char_name=char_name)

        if rev:

            zone, primary, sub = rev

        else:

            if s_low in zones_index:

                zone, primary, sub = zones_index[s_low][0], zones_index[s_low][1], "Main Area"

            elif s_low in primaries:

                zone, primary, sub = primaries[s_low][0], primaries[s_low][1], "Main Area"

            elif p_low in zones_index:

                zone, primary, sub = zones_index[p_low][0], zones_index[p_low][1], "Main Area"

        # Re-run incongruous check after normalization

        if is_incongruous_container(primary, sub, session_id=session_id, scenario_key=scenario_key):

            zone, primary, sub = auto_heal_incongruous_location(zone, primary, sub, session_id=session_id, scenario_key=scenario_key)



    formatted = format_tiered_location_string(zone, primary, sub)



    # STEP 2: Compute loc_id AFTER normalization so ID matches the clean location.

    loc_id = f"loc_{_slugify(zone)}_{_slugify(primary)}_{_slugify(sub)}"



    # STEP 3: Inherit atmosphere from existing zone locations.

    existing = db.get_session_locations(session_id)

    atmosphere = ""

    for r in existing:

        if r.get("zone_name") == zone and r.get("atmosphere"):

            atmosphere = r.get("atmosphere")

            break



    # STEP 4: Dynamic save gate — only persist if all tier invariants hold.

    # Prevents poisoning the spatial index with chimera or demoted-zone entries.

    p_low_final = primary.strip().lower()

    s_low_final = sub.strip().lower()

    z_low_final = zone.strip().lower()
    is_valid_save = (
        zone and primary and sub
        and not is_invalid_location_string(zone)
        and not is_invalid_location_string(primary)
        and not any(k in z_low_final for k in ("board", "desk", "table", "chair", "bed", "closet", "shelf", "counter"))
        and p_low_final not in zones_index
        and s_low_final not in zones_index
        and s_low_final not in primaries
        and p_low_final not in subs_idx
        and not (is_school_scenario(scenario_key) and p_low_final in primaries and primaries[p_low_final][0].strip().lower() != z_low_final)
        and not is_incongruous_container(primary, sub, session_id=session_id, scenario_key=scenario_key)
    )

    if is_school_scenario(scenario_key):

        from .constants import CAMPUS_FACILITY_KEYWORDS

        res_z = get_session_residential_neighborhood_name(session_id, scenario_key)

        comm_z = get_session_commercial_district_name(session_id, scenario_key)

        school_z = get_session_school_name(session_id, scenario_key)

        z_low_final = zone.strip().lower()

        # Gate 1: Campus facility under residential or commercial zone
        if any(k in p_low_final for k in CAMPUS_FACILITY_KEYWORDS) or p_low_final in ("botanical glasshouse", "interior greenery path"):

            if (res_z and res_z.lower() in z_low_final) or (comm_z and comm_z.lower() in z_low_final) or any(k in z_low_final for k in ("residential", "commercial", "town", "quarter", "neighborhood")):

                is_valid_save = False

        # Gate 2: Residence under school or commercial zone
        is_res = (
            any(re.search(r'\b' + re.escape(k) + r'\b', p_low_final) for k in ("residence", "house", "apartment", "cottage", "manor")) or
            bool(re.search(r"\bhome\b", p_low_final))
        ) and not any(k in p_low_final for k in ("glasshouse", "greenhouse", "conservatory", "arboretum", "pavilion", "commons", "promenade"))
        if is_res:

            if (school_z and school_z.lower() in z_low_final) or (comm_z and comm_z.lower() in z_low_final) or any(k in z_low_final for k in ("academy", "school", "campus", "athletics", "commercial", "arcade", "shopping")):

                is_valid_save = False

        # Gate 3: Commercial shop under school or residential zone
        if any(k in p_low_final for k in ("café", "cafe", "arcade", "diner", "bakery", "restaurant", "bookstore", "game center")):

            if (school_z and school_z.lower() in z_low_final) or (res_z and res_z.lower() in z_low_final) or any(k in z_low_final for k in ("academy", "school", "campus", "athletics", "residential", "town", "quarter", "neighborhood")):

                is_valid_save = False

    if is_valid_save:

        db.save_session_location(

            session_id=session_id,

            location_id=loc_id,

            zone_name=zone,

            primary_name=primary,

            sub_name=sub,

            atmosphere=atmosphere,

            is_dynamic=1

        )



    return formatted

def discover_poi_chamber(session_id: int, zone_name: str, primary_name: str, sub_name: str = "Main Area", scenario_key: str = "fantasy", atmosphere: str = "") -> str:

    """

    Explicitly registers a newly discovered Point of Interest (POI) or delve chamber

    into the session's physical spatial registry in SQLite.

    Returns the formatted 3-tiered location string.

    """

    formatted = format_tiered_location_string(zone_name, primary_name, sub_name)

    return process_llm_location_update(session_id, formatted, scenario_key=scenario_key)

def is_poetic_drift_title(name: str, scene_title: str = "") -> bool:

    """

    Returns True if `name` represents a poetic narrative heading, event title, or abstract phrase

    rather than a grounded physical location/establishment.

    """

    if not name or not str(name).strip():

        return False

    clean = str(name).strip()

    clean_lower = clean.lower()



    # 0. Check for objective sentences

    if is_invalid_location_string(clean):

        return True



    # 1. Check for narrative action clauses & poetic event patterns (takes absolute precedence)

    narrative_event_patterns = [

        r"\b(splits|beyond|leaves|whispers|handoff|revelation|confrontation|rendezvous)\b",

        r"\b(three ways|two ways|crossroads of fate|moment of|dance of|song of)\b",

        r"^the\s+\w+\s+(splits|beyond|unseen|hidden|quiet|lost|broken)\b",

        r"\b(in the dark|under the stars|before the storm|after the rain|into the fire)\b",

        r"\b(road splits|flame beyond|beyond the roots|hidden handoff|counterfeit road)\b"

    ]

    for pat in narrative_event_patterns:

        if re.search(pat, clean_lower):

            return True



    # 2. Concrete physical establishment nouns are real physical places, not poetic drift!

    physical_nouns = (

        "tavern", "inn", "pub", "bar", "café", "cafe", "shop", "store", "market", "bazaar",

        "plaza", "hall", "guild", "keep", "fort", "citadel", "bastion", "tower", "castle",

        "palace", "manor", "house", "residence", "room", "classroom", "lab", "laboratory",

        "library", "archives", "gym", "gymnasium", "pool", "clinic", "infirmary", "hospital",

        "station", "dock", "pier", "bridge", "gate", "pass", "sanctuary", "temple", "shrine",

        "crypt", "ruin", "ruins", "cavern", "cave", "den", "lair", "mill", "camp", "hut",

        "hallway", "corridor", "courtyard", "garden", "park", "road", "street", "alley",

        "wing", "dorm", "dormitory", "office", "desk", "rooftop", "roof", "auditorium",

        "cafeteria", "canteen", "lounge", "quarter", "quarters", "district", "chamber", "vault"

    )

    if any(kw in clean_lower for kw in physical_nouns):

        return False



    # 3. Exact match with scene title without physical noun (narrative beat heading)

    if scene_title and clean_lower == str(scene_title).strip().lower():

        return True



    # 4. High word count (4+ words) without a concrete physical noun

    words = clean.split()

    if len(words) >= 4:

        return True



    return False

def is_incongruous_container(primary_place: str, sub_spot: str, session_id: int = 0, scenario_key: str = "fantasy") -> bool:

    """

    Returns True if sub_spot cannot physically exist inside primary_place.

    Two tiers of checks:

      1. Unconditional tier invariant: sub_spot is a Tier 1 Zone or another Tier 2 Primary -> always invalid.

      2. Enclosed room + exterior sub-spot: e.g. 'Student Council Office -> Terrace Overlook'.

    """

    if not primary_place or not sub_spot:

        return False

    p_low = primary_place.strip().lower()

    s_low = sub_spot.strip().lower()



    if s_low in ("main area", "front porch", "entryway", "foyer"):
        return False

    # Seeded author-defined locations are physically valid by definition
    if session_id:
        try:
            existing = db.get_session_locations(session_id)
            for r in existing:
                if not r.get("is_dynamic"):
                    if r.get("primary_name", "").strip().lower() == p_low and r.get("sub_name", "").strip().lower() == s_low:
                        return False
        except Exception:
            pass

    # UNCONDITIONAL TIER INVARIANT: A sub-spot can NEVER be a Tier 1 Zone or a
    # different Tier 2 Primary Place, regardless of what the container is.
    # This must run before the ENCLOSED_ROOM_KEYWORDS gate so it catches exterior
    # and transitional containers (e.g. School Gates, Residential Walkway) too.
    if session_id:
        from .hierarchy import _build_session_zone_index, _build_session_spatial_index
        zones_index = _build_session_zone_index(session_id, scenario_key)
        primaries, subs_idx = _build_session_spatial_index(session_id, scenario_key)

        if s_low in zones_index:
            return True

        if s_low in primaries and s_low != p_low:
            # If s_low is also an existing sub-location under p_low, it is not incongruous
            if s_low not in subs_idx or subs_idx[s_low][1].strip().lower() != p_low:
                return True

    # Botanical / greenhouse / courtyard / park spaces naturally contain exterior paths and garden features
    if any(k in p_low for k in ("glasshouse", "greenhouse", "conservatory", "arboretum", "patio", "courtyard", "pavilion", "park", "garden", "commons", "promenade")):
        return False

    is_enclosed_room = any(re.search(r'\b' + re.escape(k) + r'\b', p_low) for k in ENCLOSED_ROOM_KEYWORDS)
    if not is_enclosed_room:
        return False

    is_exterior_spot = any(k in s_low for k in INCONGRUOUS_EXTERIOR_SUB_KEYWORDS)
    return is_exterior_spot

def auto_heal_incongruous_location(zone: str, primary: str, sub: str, session_id: int = 0, scenario_key: str = "high_school_drama") -> Tuple[str, str, str]:

    """

    Heals an invalid enclosed room + exterior sub-location combination

    (e.g. 'Student Council Office ➔ Terrace Overlook') by either:

    1. Finding an established semantic match in the current zone or connected zones

       (e.g. 'Campus Promenade & Student Commons ➔ Old Garden Terrace ➔ Observation Point'), OR

    2. Promoting the exterior sub-spot to an independent Tier 2 Primary Place in the zone

       (e.g. 'Creative Arts & Student Union Wing ➔ Arts Wing Terrace ➔ Overlook Railing').

    """

    if not is_incongruous_container(primary, sub, session_id=session_id, scenario_key=scenario_key):

        return (zone, primary, sub)



    s_low = sub.strip().lower()



    # If session_id is available, scan established places in current and connected zones

    if session_id:

        existing = db.get_session_locations(session_id)

        candidate_zones = [zone]

        if is_school_scenario(scenario_key):

            commons_name = get_session_student_commons_name(session_id, scenario_key)

            arts_name = get_session_cultural_arts_name(session_id, scenario_key)

            athletics_name = get_session_athletics_complex_name(session_id, scenario_key)

            campus_name = get_session_school_name(session_id, scenario_key)

            if commons_name and commons_name not in candidate_zones:

                candidate_zones.append(commons_name)

            for cz in (arts_name, athletics_name, campus_name):

                if cz and cz not in candidate_zones:

                    candidate_zones.append(cz)



        # 1. Terrace / Overlook match

        if any(k in s_low for k in ("terrace", "overlook", "balcony", "veranda")):

            for r in existing:

                if r.get("zone_name") in candidate_zones and any(k in (r.get("primary_name") or "").lower() for k in ("terrace", "overlook", "balcony")):

                    target_sub = "Observation Point" if "terrace" in (r.get("primary_name") or "").lower() else "Main Area"

                    return (r.get("zone_name"), r.get("primary_name"), target_sub)



        # 2. Garden / Plants / Flowers match

        if any(k in s_low for k in ("garden", "glasshouse", "greenhouse", "plants", "jasmine")):

            for r in existing:

                if r.get("zone_name") in candidate_zones and any(k in (r.get("primary_name") or "").lower() for k in ("glasshouse", "garden", "courtyard")):

                    target_sub = "Interior Greenery Path" if "glasshouse" in (r.get("primary_name") or "").lower() else "Main Area"

                    return (r.get("zone_name"), r.get("primary_name"), target_sub)



        # 3. Courtyard / Plaza match

        if any(k in s_low for k in ("courtyard", "plaza", "fountain")):

            for r in existing:

                if r.get("zone_name") in candidate_zones and any(k in (r.get("primary_name") or "").lower() for k in ("courtyard", "plaza")):

                    return (r.get("zone_name"), r.get("primary_name"), "Courtyard Fountain" if "fountain" in s_low else "Main Area")



        # 4. Hallway / Corridor match

        if any(k in s_low for k in ("hallway", "corridor", "hall")):

            for r in existing:

                if r.get("zone_name") == zone and any(k in (r.get("primary_name") or "").lower() for k in ("corridor", "hallway", "hall")):

                    return (zone, r.get("primary_name"), "Main Corridor")



    # Fallback: If sub is a known Tier 1 Zone, resolve to that zone's canonical gateway.

    # Never blindly promote a Tier 1 Zone name into Tier 2 of a different zone.

    if session_id:

        from .hierarchy import _build_session_zone_index, _build_session_spatial_index
        zones_index = _build_session_zone_index(session_id, scenario_key)

        primaries_idx, _ = _build_session_spatial_index(session_id, scenario_key)

        if s_low in zones_index:

            # sub is a Tier 1 Zone — resolve to that zone's canonical gateway

            target_zone, gateway_p, gateway_s = zones_index[s_low]

            return (target_zone, gateway_p, gateway_s)

        if s_low in primaries_idx and s_low != primary.strip().lower():

            # sub is a Tier 2 Primary — resolve to its canonical zone

            return (primaries_idx[s_low][0], primaries_idx[s_low][1], "Main Area")



    # Fallback: Promote the sub-spot to an independent Tier 2 Primary Place in the zone

    promoted_p = sub

    if "terrace" in s_low:

        promoted_p = "Arts Wing Terrace" if any(k in zone.lower() for k in ("arts", "union")) else ("Academic Terrace" if any(k in zone.lower() for k in ("academic", "main")) else sub)

    elif "garden" in s_low:

        promoted_p = f"{zone} Gardens" if "wing" in zone.lower() else sub

    return (zone, promoted_p, "Stone Railing" if "terrace" in s_low else "Main Area")

def is_movement_action(action_text: str) -> bool:
    """Detects whether an action represents physical travel or movement."""
    if not action_text or not str(action_text).strip():
        return False

    act_lower = str(action_text).lower().strip()

    # Rendezvous proposals and social invitations (e.g. proposing to meet at another venue,
    # or inviting to hang out / walk together) are dialogue proposals on this turn, NOT immediate physical travel.
    # Player/NPC must agree first (recording appointment or adding temporary companion),
    # and actual physical travel occurs on subsequent turns via explicit travel choices (e.g. '[Travel to...').
    is_explicit_travel_cmd = any(act_lower.startswith(p) for p in (
        "[travel", "[move", "i travel", "i head", "i walk", "i go to", "travel to", "head to", "walk to"
    ))
    if not is_explicit_travel_cmd:
        from mechanics.narrative.intent import RENDEZVOUS_PROPOSAL_RE, SOCIAL_INVITE_RE
        if RENDEZVOUS_PROPOSAL_RE.search(act_lower):
            return False
        if SOCIAL_INVITE_RE.search(act_lower) and any(act_lower.startswith(k) for k in ("ask ", "invite ", "suggest ", "propose ", "want to ", "wanna ")):
            return False

    prefix_movement_pattern = r"^(?:i\s+)?(?:head|walk|travel|go|move|run|rush|sprint|step|leave|exit|return|enter|visit|make\s+(?:my|your|our)\s+way)\s+(?:to|toward|towards|into|out|back|home|straight\s+to|over\s+to) "
    if re.search(prefix_movement_pattern, act_lower):
        return True

    # Intent engine check runs FIRST — before any keyword blacklists.
    # This prevents 'Head toward X to investigate rumors' being blocked by 'rumor'.
    try:
        from mechanics.narrative.intent import classify_action_intent, IntentCategory
        intent = classify_action_intent(action_text)
        if intent.category in (IntentCategory.MOVEMENT, IntentCategory.APPOINTMENT_MEETUP):
            return True
    except Exception:
        pass

    override_movement_phrases = (
        "i travel to", "i head to", "i walk to", "[travel", "[move",
        "head to", "head toward", "head towards", "head straight to", "head over to",
        "walk to", "walk toward", "walk towards", "travel to", "go to",
        "move to", "moving to",
        "step to", "step out to", "step into", "walk into", "head into",
        "lead to", "lead her to", "lead him to", "lead the way to",
        "take her to", "take him to", "bring her to", "bring him to",
        "slip to", "slip into", "slip away to", "go into", "depart to", "depart for",
        "turn back from", "step away from", "turn back", "walk away", "step back",
        "quieter spot", "quiet spot", "secluded spot", "private spot"
    )

    has_movement_directive = (
        any(k in act_lower for k in override_movement_phrases)
        or bool(re.search(r'\b(?:move|moving|travel|traveling|head|heading|walk|walking|go|going|step|stepping|lead|leading|slip|slipping|bring|bringing|take|taking)\b.*?\b(?:to|into|toward|towards|for)\b', act_lower))
        or bool(re.search(r'\b(?:quieter|secluded|quiet|private)\s+spot\b', act_lower))
    )

    # Conversational blacklist only applies when no imperative movement verb/prefix was detected.
    conversational_non_movement = (
        "ask ", "inquire ", "inquired ", "asking ", "talk ", "talking ", "discuss ", "discussing ",
        "tell me about", "rumour", "rumours", "whisper", "speak of", "speak with", "speak to", "speak ",
        "read about", "study ", "studying ", "question ", "questioning ", "interrogate", "investigate rumors"
    )

    if any(cnm in act_lower for cnm in conversational_non_movement) and not has_movement_directive:
        return False

    conversational_nouns = ("conversation", "discussion", "topic", "debate", "subject", "argument", "point of view", "thought", "feelings")

    if any(cn in act_lower for cn in conversational_nouns) and not has_movement_directive:
        return False

    # Intimate and physical interaction actions are not spatial movements unless explicit travel tag/prefix is present
    intimate_actions = (
        "fuck", "fucking", "pound", "pounding", "thrust", "thrusting", "ride", "riding",
        "caress", "caressing", "kiss", "kissing", "undress", "undressing", "strip", "stripping",
        "suck", "sucking", "lick", "licking", "blowjob", "cunnilingus", "oral", "handjob",
        "fingering", "make love", "grind", "grinding", "grope", "groping",
        "taking her", "taking him", "take her", "take him", "from behind", "hands and knees",
        "flip her", "flip him", "turn her", "turn him", "pull out and", "position", "positions"
    )
    if any(re.search(r'\b' + re.escape(ia) + r'\b', act_lower) for ia in intimate_actions) and not any(k in act_lower for k in override_movement_phrases):
        return False

    movement_roots = (

        "travel", "travels", "traveled", "travelling", "traveling",

        "head", "heads", "headed", "heading",

        "walk", "walks", "walked", "walking",

        "journey", "journeys", "journeyed", "journeying",

        "move", "moves", "moved", "moving",

        "enter", "enters", "entered", "entering",

        "visit", "visits", "visited", "visiting",

        "navigate", "navigates", "navigated", "navigating",

        "return", "returns", "returned", "returning",

        "run", "runs", "ran", "running",

        "sneak", "sneaks", "sneaked", "sneaking",

        "explore", "explores", "explored", "exploring",

        "ride", "rides", "rode", "riding",

        "sail", "sails", "sailed", "sailing",

        "infiltrate", "infiltrates", "infiltrated", "infiltrating",

        "sprint", "sprints", "sprinted", "sprinting",

        "rush", "rushes", "rushed", "rushing",

        "reach", "reaches", "reached", "reaching",

        "slip", "slips", "slipped", "slipping",

        "climb", "climbs", "climbed", "climbing",

        "dash", "dashes", "dashed", "dashing",

        "depart", "departs", "departed", "departing",

        "leave", "leaves", "left", "leaving",

        "bring", "brings", "brought", "bringing",

        "carry", "carries", "carried", "carrying",

        "deliver", "delivers", "delivered", "delivering",

        "escort", "escorts", "escorted", "escorting",

        "take", "takes", "took", "taking",

        "seek", "seeks", "sought", "seeking",

        "guide", "guides", "guided", "guiding",

        "steer", "steers", "steered", "steering",

        "lead", "leads", "led", "leading",

        "step", "steps", "stepped", "stepping",

        "usher", "ushers", "ushered", "ushering",

        "follow", "follows", "followed", "following",

        "accompany", "accompanies", "accompanied", "accompanying",

        "exit", "exits", "exited", "exiting"

    )

    direction_terms = (

        "to ", "toward", "towards", "into ", "for ", "through ", "across ", "outside", "out into", "out of", "way out", "the way out",

        "the trail", "the road", "the street", "the alley", "the hall", "the hallway", "the market", "the gate",

        "the exit", "the door", "the bedroom", "the room", "the kitchen", "the porch", "the corridor", "the roof",

        "home", "home together"

    )

    valid_movement_roots = []
    for root in movement_roots:
        if re.search(r'\b' + re.escape(root) + r'\b', act_lower):
            # Reaching for a physical item, body part, or gesture is not spatial movement to a location
            if root.startswith("reach") and re.search(r'\breach(?:es|ed|ing)?\s+(?:under|for|into|between|down|around|behind|out\s+to\s+touch)\b', act_lower):
                continue
            valid_movement_roots.append(root)

    has_root = bool(valid_movement_roots)

    has_dir = any(dir_t in act_lower for dir_t in direction_terms)



    if has_movement_directive or (has_root and (
        has_dir
        or act_lower.startswith("to ")
        or "[travel" in act_lower
        or "[move" in act_lower
        or act_lower.startswith("i travel")
        or act_lower.startswith("i head")
        or act_lower.startswith("i go")
        or act_lower.startswith("i walk")
    )):
        return True



    return False

def extract_movement_destination(action_text: str, session_id: int, current_zone: str = "", scen_key: str = "fantasy", char_name: str = "", allow_proposal: bool = False) -> tuple[str, str] | None:
    """
    Deterministically detects if the player's chosen action intent was to travel/move to a known place.
    Returns (zone_name, primary_name) or None.
    """
    if not is_movement_action(action_text) and not allow_proposal:
        return None

    act_lower = str(action_text).lower()



    existing = db.get_session_locations(session_id)
    if not existing and session_id:
        try:
            from mechanics.world.locations.seeding import ensure_session_locations_seeded
            ensure_session_locations_seeded(session_id, scen_key, char_name=char_name)
            existing = db.get_session_locations(session_id)
        except Exception:
            existing = []

    if not existing:
        return None

    if is_school_scenario(scen_key):
        existing = [
            r for r in existing
            if not any(k in (r.get("zone_name") or "").lower() for k in ("shadowlands", "dreadfall", "necro", "blight", "dungeon", "crypt", "obsidian altar", "ruined keep"))
        ]
        if not existing:
            return None

    # Helper to check if two zone names refer to the same region (e.g. 'Astrid' vs 'Royal Capital of Astrid')
    def is_same_zone(z1: str, z2: str) -> bool:
        if not z1 or not z2:
            return False
        if z1.strip().lower() == z2.strip().lower():
            return True
        sz1 = get_clean_zone_short_name(z1).lower()
        sz2 = get_clean_zone_short_name(z2).lower()
        if sz1 and sz2 and sz1 == sz2:
            return True
        if is_school_scenario(scen_key):
            school_kws = ("school", "academy", "institute", "campus", "high")
            if any(k in z1.lower() for k in school_kws) and any(k in z2.lower() for k in school_kws):
                return True
        return False

    # 0. Direct tiered location matching with explicit delimiters (highest precedence)
    delimiters = ["➔", "->", ">", "|"]
    for d in delimiters:
        if d in action_text:
            raw_target = action_text
            for pfx in ("i travel to ", "travel to ", "i head to ", "head to ", "i walk to ", "walk to ", "i move to ", "move to ", "i visit ", "visit "):
                if act_lower.startswith(pfx):
                    raw_target = action_text[len(pfx):].strip().rstrip(".")
                    break
            pz, pp, _ = parse_tiered_location(raw_target, scenario_key=scen_key, session_id=session_id, char_name=char_name)
            is_known_place = any(
                r.get("primary_name", "").strip().lower() == pp.strip().lower()
                for r in existing
            )
            if pz and pp and pp not in ("Main Area", "") and (is_known_place or not is_poetic_drift_title(pp)):
                return (pz, pp)

    # 0a. Check turn back / step away intent (User Decision #2)
    if any(k in act_lower for k in ("turn back from", "step away from", "turn back", "step back from")):
        target_place = None
        for pfx in ("turn back from ", "step away from ", "step back from "):
            if pfx in act_lower:
                target_place = act_lower.split(pfx, 1)[-1].strip()
                break

        if existing:
            # Look for a public corridor, hallway, courtyard, or plaza in current_zone
            hub_cands = [
                r for r in existing
                if is_same_zone(r.get("zone_name", ""), current_zone) and any(w in (r.get("primary_name") or "").lower() for w in ("hall", "corridor", "courtyard", "plaza", "entrance", "gate", "foyer", "commons"))
                and (not target_place or target_place not in (r.get("primary_name") or "").lower())
            ]
            if hub_cands:
                return (current_zone or hub_cands[0].get("zone_name"), hub_cands[0].get("primary_name"))
            
            zone_cands = [
                r for r in existing
                if is_same_zone(r.get("zone_name", ""), current_zone)
                and (not target_place or target_place not in (r.get("primary_name") or "").lower())
            ]
            if zone_cands:
                return (current_zone or zone_cands[0].get("zone_name"), zone_cands[0].get("primary_name"))
            
            return (current_zone or existing[0].get("zone_name"), existing[0].get("primary_name"))

    # 0a. Check if action matches heading home (player's home or companion's home)

    if any(k in act_lower for k in ("head home", "walk home", "go home", "return home", "travel home", "heading home", "heading back home", "head back home")):

        c_first = char_name.lower().split()[0] if char_name else ""

        home_match = next((

            (r.get("zone_name", ""), r.get("primary_name", ""))

            for r in existing

            if "house" in r.get("primary_name", "").lower() or "home" in r.get("primary_name", "").lower() or (c_first and len(c_first) >= 3 and c_first in r.get("primary_name", "").lower())

        ), None)

        if home_match and home_match[1]:

            return (home_match[0] or current_zone, home_match[1])



    # 0a. Check companion / NPC residence visit intent (e.g. "head toward her home", "hangout at her place", "enter Maya's home", "go to Sofia's house")

    npc_home_triggers = (

        "her home", "his home", "their home", "her house", "his house", "their house",

        "her place", "his place", "their place",

        "to her home", "to his home", "to her house", "to his house", "at her place", "at his place",

        "enter her home", "enter his home", "enter her house", "enter his house"

    )

    is_npc_home_act = any(k in act_lower for k in npc_home_triggers) or bool(re.search(r"\b([a-z]+)'s (house|home|place|residence)\b", act_lower))

    if is_npc_home_act and (is_school_scenario(scen_key)):

        target_npc = ""

        m = re.search(r"\b([a-zA-Z]+)'s (house|home|place|residence)\b", action_text)

        if m:

            cand_first = m.group(1).strip()

            try:

                contacts = db.get_contacts(session_id)

                for c in contacts:

                    if c.get("name", "").lower().startswith(cand_first.lower()):

                        target_npc = c["name"]

                        break

            except Exception:

                pass

            if not target_npc:

                target_npc = cand_first



        if not target_npc and session_id:

            try:

                sess = db.get_session(session_id)

                from mechanics.world.mobility import get_session_dialogue_partners
                dps = get_session_dialogue_partners(sess)
                if dps:
                    target_npc = dps[0]

                if not target_npc:

                    npcs = sess.get("current_npcs") or sess.get("current_npcs_json")

                    if isinstance(npcs, str):

                        npcs = json.loads(npcs or "[]")

                    if isinstance(npcs, list) and npcs:

                        target_npc = npcs[0].get("name", "")

            except Exception:

                pass



        if target_npc:

            return resolve_npc_residence(session_id, target_npc, scenario_key=scen_key)



    # 0b. Check if action matches exiting an interior room to the hallway

    if any(k in act_lower for k in ("the exit", "way out", "leave the room", "exit the room", "into the hallway", "to the hallway", "toward the hallway", "step into the hallway", "step out", "head out")):

        hall_match = next((

            (r.get("zone_name", ""), r.get("primary_name", ""))

            for r in existing

            if any(h in r.get("primary_name", "").lower() for h in ("hallway", "corridor", "hallways"))

            and is_same_zone(r.get("zone_name", ""), current_zone)

        ), None)

        if hall_match and hall_match[1]:

            return (hall_match[0] or current_zone, hall_match[1])






    # 1. Exact full primary_name match in action_text (e.g. "Adventurers' Guild Hall" in "Travel toward the Adventurers' Guild Hall")
    exact_matches = []
    for r in existing:
        p_name = r.get("primary_name", "")
        z_name = r.get("zone_name", "")
        if not p_name:
            continue

        p_lower = p_name.lower()
        clean_p = re.sub(r'\(.*?\)', '', p_lower).strip()
        has_match = False
        if re.search(r'(?<!\w)' + re.escape(p_lower) + r'(?!\w)', act_lower):
            has_match = True
        elif clean_p and len(clean_p) >= 3 and re.search(r'(?<!\w)' + re.escape(clean_p) + r'(?!\w)', act_lower):
            has_match = True

        if has_match:
            exact_matches.append((z_name, p_name, len(p_lower)))

    if exact_matches:
        # Prefer a match within the current zone if available
        same_zone_match = next((m for m in exact_matches if is_same_zone(m[0], current_zone)), None)
        if same_zone_match:
            return (current_zone or same_zone_match[0], same_zone_match[1])

        # Otherwise, travel across zones to the registered zone of the target establishment!
        exact_matches.sort(key=lambda m: m[2], reverse=True)
        return (exact_matches[0][0], exact_matches[0][1])

    # 1b. Zone & Semantic Alias Matching
    from .hierarchy import _build_session_zone_index, _build_session_spatial_index
    zones_index = _build_session_zone_index(session_id, scen_key)

    for z_lower, (z_name, z_gw_p, z_gw_s) in zones_index.items():
        if re.search(r'\b' + re.escape(z_lower) + r'\b', act_lower):
            if not re.search(r'\b(?:out\s+of(?:\s+the)?|leave(?:\s+the)?|exit(?:\s+the)?)\s+' + re.escape(z_lower) + r'\b', act_lower):
                return (z_name, z_gw_p)

    aliases = {
        "student lounge": ("Student Plaza & Dining Pavilion", "Central Courtyard"),
        "student commons": ("Student Plaza & Dining Pavilion", "Central Courtyard"),
        "campus dining": ("Campus Dining Hall & Cafeteria", "Main Area"),
        "cafeteria": ("Campus Dining Hall & Cafeteria", "Main Area"),
    }
    for alias, (alias_z, alias_p) in aliases.items():
        if alias in act_lower:
            return (alias_z, alias_p)



    # 2. Check distinct keywords of registered establishments (e.g. "guild hall", "market plaza", "sunken moonwell", "imperial palace")

    generic_words = (
        "school", "main", "hall", "room", "classroom", "area", "house", "grounds",
        "place", "building", "zone", "corridor", "store", "shop", "market", "bazaar",
        "outlet", "spot", "center", "centre", "office",
        "north", "south", "east", "west", "upper", "lower", "inner", "outer", "old", "new",
        "wing", "front", "back", "side", "central", "middle", "corner",
        "keep", "reach", "hold", "stand", "rest", "take", "step", "bring", "lead", "stop",
        "behind", "beside", "between", "under", "over", "around", "near", "across", "through",
        "along", "against", "toward", "towards"
    )

    keyword_matches = []

    for r in existing:

        p_name = r.get("primary_name", "")

        z_name = r.get("zone_name", "")

        if not p_name:

            continue

        p_lower = p_name.lower()
        clean_p_words = re.sub(r'[()]', ' ', p_lower).replace("'", "").replace("&", " ")
        p_words = [w for w in clean_p_words.split() if (len(w) >= 4 or w.isdigit()) and w not in generic_words]
        matched_words = []
        for pw in p_words:
            if re.search(r'(?<!\w)' + re.escape(pw) + r'(?!\w)', act_lower):
                # Ensure it is not an origin being exited (e.g. "out of the office", "leave the room")
                if re.search(r'\b(?:out\s+of(?:\s+the)?|leave(?:\s+the)?|exit(?:\s+the)?)\s+' + re.escape(pw) + r'(?!\w)', act_lower):
                    continue
                matched_words.append(pw)

        if matched_words:

            match_score = sum(len(pw) for pw in matched_words)

            keyword_matches.append((z_name, p_name, match_score))



    if keyword_matches:

        same_zone_match = next((m for m in keyword_matches if is_same_zone(m[0], current_zone)), None)

        if same_zone_match:

            return (same_zone_match[0] or current_zone, same_zone_match[1])

        keyword_matches.sort(key=lambda m: m[2], reverse=True)

        return (keyword_matches[0][0], keyword_matches[0][1])



    # 3. Direct travel prefix extraction (e.g. "I travel to Empty Classroom." -> "Empty Classroom")

    for pfx in (
        "i travel to ", "travel to ", "i head to ", "head to ", "i walk to ", "walk to ",
        "i move to ", "move to ", "i visit ", "visit ", "sneak into ", "explore ",
        "take the long walk to ", "take the walk to ", "make the walk to ", "the long walk to ", "long walk to ",
        "head toward ", "head towards ", "walk toward ", "walk towards ", "travel toward ", "travel towards "
    ):

        if act_lower.startswith(pfx):

            raw_target = action_text[len(pfx):].strip().rstrip(".")

            if raw_target:

                if is_school_scenario(scen_key) and raw_target.lower() in ("school", "the school", "campus", "the campus", "academy", "the academy", "high school"):

                    s_name = get_session_school_name(session_id, scen_key)

                    if s_name:

                        gw_p = next((r["primary_name"] for r in existing if r.get("zone_name") == s_name and ("gate" in r.get("primary_name", "").lower() or "entrance" in r.get("primary_name", "").lower())), "School Main Gates")

                        return (s_name, gw_p)

                for r in existing:

                    if r.get("primary_name", "").strip().lower() == raw_target.lower():

                        z_name = r.get("zone_name", "")

                        return (z_name or current_zone, r["primary_name"])

                return (current_zone, raw_target)



    return None

def reconcile_movement_location(session_id: int, current_loc: str, result_loc: str,

                                action_text: str = "", narrative: str = "",

                                scen_key: str = "high_school_drama", char_name: str = "",

                                check_tier: str = "success",

                                **kwargs) -> str:

    """

    Reconciles location output with deterministic player movement actions, the session's physical

    spatial registry, and narrative continuity. Completely decoupled from decorative scene/chapter titles.

    """

    if not is_location_engine_enabled(scen_key):

        return result_loc or current_loc or ""



    ensure_session_locations_seeded(session_id, scen_key, char_name=char_name)

    curr_z, curr_p, curr_s = parse_tiered_location(current_loc, scen_key, session_id=session_id, char_name=char_name) if current_loc else ("", "", "")



    raw_res = str(result_loc or "").strip()

    narr_prose = re.sub(r'["“”][^"“”]*?["“”]', '', str(narrative or "")).lower()

    narr_lower = str(narrative or "").lower()

    act_lower = str(action_text or "").lower()
    is_move = is_movement_action(action_text)



    # Step 1: Check if the player explicitly chose a movement action to a registered physical establishment

    action_dest = extract_movement_destination(action_text, session_id, current_zone=curr_z, scen_key=scen_key, char_name=char_name)
    if action_dest and check_tier != "crit_fail":
        dest_z, dest_p = action_dest

        # If the player is already grounded in an established primary venue (curr_p),
        # and the LLM result kept that same venue, do not allow action_dest to pull the player
        if raw_res and curr_p and dest_p.lower() != curr_p.lower():
            p_z, p_p, p_s = parse_tiered_location(raw_res, scen_key, session_id=session_id, char_name=char_name)
            if p_p.lower() == curr_p.lower() and p_s.lower() != (curr_s or "").lower() and dest_p.lower() not in str(action_text).lower():
                action_dest = None

    if action_dest and check_tier != "crit_fail":
        dest_z, dest_p = action_dest
        sub_to_use = get_facility_entrance_sublocation(dest_p, session_id=session_id, scen_key=scen_key)

        # Check if there is an active phone appointment at this destination with a specific sub-location
        locked_target_sub = None
        try:
            pending_appts = db.get_phone_appointments(session_id, status="pending") + db.get_phone_appointments(session_id, status="arrived")
            for appt in pending_appts:
                appt_loc = appt.get("rendezvous_location", "")
                if appt_loc:
                    az, ap, asub = parse_tiered_location(appt_loc, scen_key, session_id=session_id, char_name=char_name)
                    if ap.lower() == dest_p.lower() and asub and asub not in ("Main Area", ""):
                        sub_to_use = asub
                        locked_target_sub = asub
                        break
        except Exception:
            pass

        # Check if there is an active quest waypoint or target character stationed at this primary place
        try:
            with db.get_conn() as _c_conn:
                if not locked_target_sub:
                    q_rows = _c_conn.execute("SELECT sub_objectives_json FROM quests WHERE session_id=? AND status='Active'", (session_id,)).fetchall()
                    for qr in q_rows:
                        sub_objs = json.loads(qr["sub_objectives_json"] or "[]")
                        for so in sub_objs:
                            if not so.get("completed"):
                                t_loc = so.get("target_location", "")
                                t_npc = (so.get("target_npc") or "").strip().lower()
                                if t_loc:
                                    qz, qp, qsub = parse_tiered_location(t_loc, scen_key, session_id=session_id, char_name=char_name)
                                    if qp.lower() == dest_p.lower() and qsub and qsub not in ("Main Area", ""):
                                        sub_to_use = qsub
                                        locked_target_sub = qsub
                                        break
                        if locked_target_sub:
                            break

                if not locked_target_sub:
                    cand_chars = _c_conn.execute(
                        "SELECT name, primary_facility FROM school_directory WHERE session_id=?", (session_id,)
                    ).fetchall()
                    for cc in cand_chars:
                        c_name = (cc["name"] or "").strip().lower()
                        c_fac = cc["primary_facility"] or ""
                        if c_name and (c_name in act_lower or (len(c_name.split()) > 1 and c_name.split()[0] in act_lower)):
                            if c_fac and dest_p.lower() in c_fac.lower():
                                _, _, npc_sub = parse_tiered_location(c_fac, scen_key, session_id=session_id, char_name=char_name)
                                if npc_sub and npc_sub not in ("Main Area", ""):
                                    sub_to_use = npc_sub
                                    locked_target_sub = npc_sub
                                    break
        except Exception:
            pass

        # Scan for sub-area within destination establishment
        existing = db.get_session_locations(session_id)
        known_subs_for_dest = [
            r["sub_name"] for r in existing
            if r.get("primary_name", "").strip().lower() == dest_p.strip().lower() and r.get("sub_name") and r.get("sub_name") not in ("Main Area", "")
        ]
        act_lower = str(action_text).lower()
        if not locked_target_sub:
            dest_p_words = set(re.findall(r"\w+", dest_p.lower()))
            for sub_cand in known_subs_for_dest:
                cand_lower = sub_cand.lower()
                cand_words = [w for w in re.findall(r"\w+", cand_lower) if len(w) >= 4 and w not in ("area", "spot", "your", "main") and w not in dest_p_words]
                if (cand_lower in act_lower or (cand_words and any(cw in act_lower for cw in cand_words))) or (cand_lower in narr_prose or (cand_words and any(cw in narr_prose for cw in cand_words))):
                    sub_to_use = sub_cand
                    break

        for d in ("➔", "->", ">", "|"):
            if d in action_text:
                raw_t = action_text
                for pfx in ("i travel to ", "travel to ", "i head to ", "head to ", "i walk to ", "walk to ", "i move to ", "move to ", "i visit ", "visit "):
                    if act_lower.startswith(pfx):
                        raw_t = action_text[len(pfx):].strip().rstrip(".")
                        break
                _, _, explicit_sub = parse_tiered_location(raw_t, scenario_key=scen_key, session_id=session_id, char_name=char_name)
                if explicit_sub and explicit_sub not in ("Main Area", "") and not is_poetic_drift_title(explicit_sub):
                    sub_to_use = explicit_sub
                    break

        if raw_res:
            parsed_z, parsed_p, parsed_sub = parse_tiered_location(raw_res, scen_key, session_id=session_id, char_name=char_name)
            is_same_dest = bool(parsed_p and parsed_p.lower() == dest_p.lower())
            is_known_sub = bool(known_subs_for_dest and any(parsed_sub.lower() == s.lower() for s in known_subs_for_dest))
            if (is_same_dest or is_known_sub) and parsed_sub and parsed_sub not in ("Main Area", "") and not is_poetic_drift_title(parsed_sub) and not is_incongruous_container(dest_p, parsed_sub, session_id=session_id, scenario_key=scen_key):
                if not (locked_target_sub and parsed_sub.lower() != locked_target_sub.lower()):
                    sub_to_use = parsed_sub

            if parsed_z and not dest_z and not is_poetic_drift_title(parsed_z):

                dest_z = parsed_z



        # Clean up residence sub-location formatting (e.g. "Maya's Home Foyer" -> "Foyer")

        if any(k in dest_p.lower() for k in ("residence", "house", "apartment", "manor", "cottage")):

            for room in ("Foyer", "Living Room", "Front Porch", "Kitchen", "Bedroom", "Dining Room", "Hallway", "Entryway", "Backyard"):

                if room.lower() in sub_to_use.lower():

                    sub_to_use = room

                    break

            else:

                if "entrance" in sub_to_use.lower():

                    sub_to_use = "Foyer"



        if locked_target_sub:
            sub_to_use = locked_target_sub
        elif sub_to_use.lower() in ("main area", "area", "main"):
            sub_to_use = get_facility_entrance_sublocation(dest_p, session_id=session_id, scen_key=scen_key)

        formatted = format_tiered_location_string(dest_z or curr_z, dest_p, sub_to_use)
        return process_llm_location_update(session_id, formatted, scen_key, char_name=char_name)



    # Step 2: If LLM provided a structured 3-tiered location string

    if raw_res:

        res_z, res_p, res_s = parse_tiered_location(raw_res, scen_key, session_id=session_id, char_name=char_name)

        # Reject hallucinated narrative event phrases (e.g. "The Counterfeit Road Splits Three Ways")

        if is_poetic_drift_title(res_p):

            if curr_p and not is_poetic_drift_title(curr_p):

                res_p = curr_p

                if res_s in ("Main Area", "") and curr_s:

                    res_s = curr_s

            else:

                existing = db.get_session_locations(session_id)

                known_in_z = [r["primary_name"] for r in existing if r.get("zone_name", "").strip().lower() == res_z.strip().lower() and r.get("primary_name")]

                if known_in_z:

                    res_p = known_in_z[0]

                else:

                    _, default_p, default_s = get_default_tiered_location(scen_key, session_id=session_id, char_name=char_name)

                    res_p = default_p

                    res_s = default_s



        if is_poetic_drift_title(res_s):

            res_s = curr_s or "Main Area"



        existing = db.get_session_locations(session_id)



        # ENCLOSED ROOM EXIT DEMOTION GUARD:
        # If the player is currently in an interior room (e.g. Teachers' Staff Room, Homeroom, Chemistry Lab)
        # and the narrative (outside dialogue) describes stepping into the hallway, leaving the room, or the door clicking shut:
        # Switch primary place to the zone's hallway/corridor and clear room-specific NPCs.
        has_hallway_exit = False
        action_str = str(action_text or "").lower()
        is_departure_act = any(k in action_str for k in ("exit", "leave", "walk out", "step out", "head out", "slip out", "depart", "goodbye", "farewell", "excuse yourself"))

        # Explicit in-room interactions (dialogue remarks, inquiries, sitting, playing piano, tender touch) anchor the player firmly in the current room
        is_in_room_act = any(k in action_str for k in (
            "ask", "tell", "say", "talk", "whisper", "tease", "kiss", "touch", "caress", "hold",
            "sit", "bench", "piano", "desk", "chair", "table", "inspect", "examine", "look at",
            "suggestive", "play", "listen", "confess", "smile", "laugh"
        ))

        # Check dialogue anchor from session
        in_dialogue_anchor = False
        if session_id:
            try:
                sess_obj = db.get_session(session_id)
                if sess_obj and (sess_obj.get("dialogue_partners") or sess_obj.get("dialogue_partner")):
                    in_dialogue_anchor = True
            except Exception:
                pass

        if curr_p and not any(h in curr_p.lower() for h in ("hallway", "hallways", "corridor")):
            # Only evaluate hallway exit if the action is not an in-room interaction,
            # and either player initiated a departure or is not actively locked in a dialogue conversation
            if not is_in_room_act and (is_departure_act or is_move or not in_dialogue_anchor):
                exit_hallway_cues = (
                    "step into the hallway", "steps into the hallway", "stepped into the hallway", "stepping into the hallway",
                    "step out into the hallway", "steps out into the hallway", "stepped out into the hallway",
                    "door of the staff room clicks shut", "door clicks shut, sealing away", "sealing away the administrative hum",
                    "away from the faculty", "left the staff room", "leaves the staff room",
                    "walked out of the room", "walks out of the room", "walking out of the room",
                    "walked out into the hallway", "walks out into the hallway",
                    "out of the office", "leaves the office", "left the office",
                    "leads the way out", "lead the way out", "led the way out"
                )
                has_hallway_exit = any(cue in narr_prose for cue in exit_hallway_cues) or (
                    (is_move or is_departure_act) and any(k in action_str for k in ("exit", "way out", "the hallway", "step out", "walk out", "head out", "follow"))
                )

                if has_hallway_exit:
                    if res_p.lower() == curr_p.lower() and not any(h in res_p.lower() for h in ("hallway", "corridor", "hallways")):
                        hall_match = next((
                            (r.get("zone_name", ""), r.get("primary_name", ""))
                            for r in existing
                            if any(h in r.get("primary_name", "").lower() for h in ("hallway", "corridor", "hallways"))
                            and (r.get("zone_name", "").strip().lower() == curr_z.strip().lower() or not curr_z)
                        ), None)
                        if hall_match and hall_match[1]:
                            res_p = hall_match[1]
                            res_z = hall_match[0] or curr_z
                            res_s = "Main Corridor"



        # SPATIAL ANCHOR GUARD:

        # If the player is already at an established primary place (curr_p), and did NOT take a movement action:

        # The engine must NOT spontaneously jump primary locations simply because another place was mentioned

        # in dialogue, background sensory atmosphere, or inquiry prose.

        if not has_hallway_exit and not is_move and not action_dest:
            if curr_z and res_z and res_z.lower() != curr_z.lower():
                res_z = curr_z
            if curr_p and res_p and res_p.lower() != curr_p.lower():
                curr_words = [w for w in curr_p.lower().replace("'", "").replace("&", " ").split() if len(w) >= 4 and w not in ("school", "main", "place", "area", "grounds")]
                res_words = [w for w in res_p.lower().replace("'", "").replace("&", " ").split() if len(w) >= 4 and w not in ("school", "main", "place", "area", "grounds")]

                exit_verbs = (
                    "exit", "exits", "exited", "exiting", "leave", "leaves", "leaving", "left", "depart", "departed",
                    "walk out", "walks out", "walked out", "walking out", "step out", "steps out", "stepped out",
                    "slip out", "slips out", "slipped out", "head out", "heads out", "headed out"
                )
                entry_verbs = (
                    "walk into", "walks into", "walked into", "walking into", "step into", "steps into", "stepped into",
                    "arrive at", "arrives at", "arrived at", "enter", "enters", "entered", "entering", "move into",
                    "moves into", "moved into", "moving into", "head into", "heads into", "headed into", "head to", "heads to", "headed to",
                    "slip into", "slips into", "slipped into", "navigate to", "navigates to", "navigated to", "reach", "reaches", "reached"
                )

                has_exit = any(ev in narr_prose for ev in exit_verbs) and (not curr_words or any(cw in narr_prose or cw.rstrip("s") in narr_prose for cw in curr_words))
                has_entry = any(ev in narr_prose for ev in entry_verbs) and (any(rw in narr_prose or rw.rstrip("s") in narr_prose for rw in res_words) or res_p.lower() in narr_prose)

                if not (has_exit and has_entry):
                    # ATOMIC 3-TUPLE ROLLBACK: When no movement detected and no narrative
                    # exit+entry transition confirmed, revert the entire (zone, primary, sub)
                    # tuple to the current grounded position. Never retain a partial res_s
                    # from a foreign venue — that is how chimera sub-locations are born.
                    res_z = curr_z
                    res_p = curr_p
                    res_s = curr_s



        # Sub-step 2b: ONLY if the player took a movement action (is_move is True), but the LLM

        # returned the old/unchanged location (res_p == curr_p), do a narrative proximity scan to catch

        # arrivals described with phrasing like "arrive at the X" or "step into the X".

        if (is_move or action_dest) and res_p.lower() == curr_p.lower() and narr_prose:

            target_zone = curr_z or (existing[0].get("zone_name") if existing else "")

            from mechanics.world.mobility import is_campus_co_located

            if is_school_scenario(scen_key):

                known_candidates = [

                    (r.get("zone_name", ""), r.get("primary_name", ""))

                    for r in existing

                    if is_campus_co_located(curr_z, r.get("zone_name", ""), scen_key) and r.get("primary_name")

                ]

            else:

                known_candidates = [

                    (r.get("zone_name", ""), r.get("primary_name", ""))

                    for r in existing

                    if r.get("zone_name", "").strip().lower() == target_zone.strip().lower() and r.get("primary_name")

                ]



            narr_arrival_verbs = (
                "arrive at", "arrives at", "arrived at", "arrive in", "arrives in", "arrived in",
                "enter", "enters", "entered", "entering",
                "walk into", "walks into", "walked into", "step into", "steps into", "stepped into",
                "slip into", "slips into", "slipped into", "move into", "moves into", "moved into",
                "head into", "heads into", "headed into", "navigate to", "navigated to",
                "reach", "reaches", "reached", "round the final corner and see", "round the corner and see",
                "rounds the corner and sees", "round the corner", "rounds the corner", "stop at", "stops at", "stopped at",
                "stopping at", "stand before", "stands before", "stood before", "near the gate", "at the gate",
                "front of the gate", "main gate ahead", "gates ahead", "at the entrance",
                "path to the", "path to", "leads to the", "lead to the", "stepped into the", "step into the"
            )

            has_narr_arrival = any(ev in narr_prose for ev in narr_arrival_verbs)

            if has_narr_arrival:

                for kz, kp in known_candidates:

                    if kp.lower() == curr_p.lower():

                        continue

                    kp_lower = kp.lower()

                    kp_words = [w for w in kp_lower.replace("'", "").replace("&", " ").split() if len(w) >= 4 and w not in ("school", "main", "place", "area", "grounds")]

                    if kp_lower in narr_prose or (kp_words and all(kw in narr_prose or kw.rstrip("s") in narr_prose for kw in kp_words)):

                        res_p = kp

                        res_z = kz or target_zone

                        break

                if is_school_scenario(scen_key) and res_p.lower() == curr_p.lower():

                    if any(g in narr_prose for g in ("main gate", "school gate", "school's main gate", "front gate", "entrance gate", "school entrance")):

                        gate_cand = next(((kz, kp) for kz, kp in known_candidates if "gate" in kp.lower() or "entrance" in kp.lower()), None)

                        if gate_cand:

                            res_z, res_p = gate_cand

                        else:

                            s_name = get_session_school_name(session_id, scen_key)

                            if s_name:

                                res_z = s_name

                                res_p = "School Main Gates"



        # Sub-step 2c: SUB-AREA (ROOM-TO-ROOM) TRANSITION SCANNER

        # When inside an establishment (res_p), check if the player action or narrative prose describes moving to a specific room

        target_prim = res_p or curr_p

        if target_prim:

            known_subs = [

                r["sub_name"] for r in existing

                if r.get("primary_name", "").strip().lower() == target_prim.strip().lower() and r.get("sub_name") and r.get("sub_name") not in ("Main Area", "")

            ]

            if known_subs:

                act_lower = str(action_text).lower()

                sub_cues = (

                    "into the ", "toward the ", "towards the ", "in the ", "beside the ", "next to the ",

                    "step into ", "steps into ", "stepped into ", "stepping into ",

                    "walk into ", "walks into ", "walked into ", "walking into ",

                    "enter the ", "enters the ", "entered the ", "entering the ",

                    "cross the threshold into ", "crosses the threshold into ", "crossed the threshold into ",

                    "transition from ", "transition to ", "moves to the ", "moved to the ", "move to the ",

                    "head to the ", "heads to the ", "headed to the ", "guide her to the ", "guides her to the ",

                    "steer her to the ", "steers her to the ", "stops beside the ", "stops beside "

                )

                # Prioritize non-current sub-areas and exact action matches

                matched_cand = None

                for sub_cand in sorted(known_subs, key=lambda s: (s.lower() == (curr_s or "").lower(), s)):

                    cand_lower = sub_cand.lower()

                    cand_words = [w for w in cand_lower.split() if len(w) >= 4 and w not in ("area", "spot", "your", "main", "room", "place", "zone")]

                    if "bedroom" in cand_lower and "bed" not in cand_words:

                        cand_words.append("bed")

                    act_sub_match = is_move and (cand_lower in act_lower or (cand_words and any(cw in act_lower for cw in cand_words)))

                    narr_sub_match = any((cue + cw) in narr_prose for cue in sub_cues for cw in cand_words) or (

                        cand_lower in narr_prose and any(sc in narr_prose for sc in ("enter the room", "threshold", "transition", "stops beside the bed", "bedside", "door clicks shut"))

                    )

                    if act_sub_match:

                        matched_cand = sub_cand

                        break

                    if narr_sub_match and not matched_cand:

                        matched_cand = sub_cand



                if matched_cand:

                    res_s = matched_cand



        # RESIDENTIAL ZONE ENFORCEMENT & HOUSEHOLD NORMALIZATION GUARD:

        # In slice-of-life/school scenarios, residences (houses, apartments, manors) and residential street thresholds

        # MUST ALWAYS belong to the canonical Residential Neighborhood zone.

        if is_school_scenario(scen_key):

            from .constants import CAMPUS_FACILITY_KEYWORDS

            res_zone = get_session_residential_neighborhood_name(session_id, scen_key)
            comm_zone = get_session_commercial_district_name(session_id, scen_key)
            school_name = get_session_school_name(session_id, scen_key)

            res_p_clean = (res_p or "").lower().strip()

            res_s_clean = (res_s or "").lower().strip()

            is_campus_fac = any(k in res_p_clean for k in CAMPUS_FACILITY_KEYWORDS)



            if is_campus_fac:

                # CAMPUS FACILITY IMMUNITY & ZONE GUARANTEE:

                # Any school facility MUST NEVER belong to a residential or commercial zone.

                z_clean = (res_z or "").lower().strip()

                if (res_zone and res_zone.lower() in z_clean) or (comm_zone and comm_zone.lower() in z_clean) or any(k in z_clean for k in ("residential", "commercial", "town", "quarter", "neighborhood", "campsite", "forest", "harbor", "bay")):

                    from .hierarchy import _build_session_spatial_index

                    primaries_idx, _ = _build_session_spatial_index(session_id, scen_key)

                    if res_p_clean in primaries_idx:

                        res_z = primaries_idx[res_p_clean][0]

                    elif school_name:

                        res_z = school_name

            else:

                is_residence_place = (

                    any(k in res_p_clean for k in ("residence", "house", "apartment", "cottage", "manor")) or

                    bool(re.search(r"\bhome\b", res_p_clean)) or

                    any(k in res_s_clean for k in ("home foyer", "foyer", "living room", "bedroom", "porch", "kitchen"))

                )

                is_res_street = any(k in res_p_clean for k in ("residential entrance", "residential street", "residential district", "cul-de-sac", "residential walkway"))



                if res_zone and (is_residence_place or is_res_street):

                    res_z = res_zone

                is_commercial_place = (
                    any(k in res_p_clean for k in ("café", "cafe", "arcade", "diner", "bakery", "restaurant", "bookstore", "boba", "boutique", "game center")) or
                    any(k in res_s_clean for k in ("counter", "dining booth", "arcade cabinets", "bookshelves"))
                )

                if comm_zone and is_commercial_place:

                    res_z = comm_zone

                # Normalize street/entrance demotions: e.g. "Residential Entrance ➔ Maya's Home Foyer"

                if is_res_street and (is_residence_place or any(k in narr_prose for k in ("foyer", "entryway", "threshold", "front door", "foyer"))):

                    target_npc = ""

                    if session_id:

                        try:

                            sess = db.get_session(session_id)

                            from mechanics.world.mobility import get_session_dialogue_partners
                            dps = get_session_dialogue_partners(sess)
                            if dps:
                                target_npc = dps[0]

                        except Exception:

                            pass

                    if not target_npc:

                        for word in ("maya", "sofia", "kana", "aoi", "yuki", "elena"):

                            if word in narr_prose or word in (res_s or "").lower() or word in str(action_text).lower():

                                target_npc = word.capitalize()

                                break

                    if target_npc:

                        _, canonical_p = resolve_npc_residence(session_id, target_npc, scen_key)

                        res_p = canonical_p

                        res_s = "Foyer" if any(k in (res_s or "").lower() or k in narr_prose for k in ("foyer", "entryway", "entrance")) else "Living Room"



        final_z = res_z or curr_z

        final_p = res_p or curr_p

        final_s = res_s or curr_s or "Main Area"

        if is_incongruous_container(final_p, final_s, session_id=session_id, scenario_key=scen_key):

            final_z, final_p, final_s = auto_heal_incongruous_location(final_z, final_p, final_s, session_id=session_id, scenario_key=scen_key)

        formatted = format_tiered_location_string(final_z, final_p, final_s)

        return process_llm_location_update(session_id, formatted, scen_key, char_name=char_name)



    # Step 3: If LLM output was empty and the player took a movement action, check narrative for arrival

    if is_move and narr_prose:

        existing = db.get_session_locations(session_id)

        target_zone = curr_z or (existing[0].get("zone_name") if existing else "")

        known_in_z = [r["primary_name"] for r in existing if r.get("zone_name", "").strip().lower() == target_zone.strip().lower() and r.get("primary_name")]



        narr_arrival_verbs = (
            "arrive at", "arrives at", "arrived at", "enter", "enters", "entered", "entering",
            "walk into", "walks into", "walked into", "step into", "steps into", "stepped into",
            "slip into", "slips into", "slipped into", "move into", "moves into", "moved into",
            "head into", "heads into", "headed into", "navigate to", "navigated to",
            "reach", "reaches", "reached", "round the final corner and see", "round the corner and see",
            "rounds the corner and sees", "round the corner", "rounds the corner", "stop at", "stops at", "stopped at",
            "stopping at", "stand before", "stands before", "stood before", "near the gate", "at the gate",
            "front of the gate", "main gate ahead", "gates ahead", "at the entrance"
        )

        has_narr_arrival = any(ev in narr_prose for ev in narr_arrival_verbs)

        if has_narr_arrival:

            if is_school_scenario(scen_key) and any(g in narr_prose for g in ("main gate", "school gate", "school's main gate", "front gate", "entrance gate", "school entrance")):

                s_name = get_session_school_name(session_id, scen_key)

                if s_name:

                    gate_p = next((r["primary_name"] for r in existing if r.get("zone_name") == s_name and ("gate" in r.get("primary_name", "").lower() or "entrance" in r.get("primary_name", "").lower())), "School Main Gates")

                    sub_area = "Entrance Path & Archway" if "path" in narr_prose else ("Gate Checkpoint" if ("checkpoint" in narr_prose or "delinquent" in narr_prose) else "Main Area")

                    formatted = format_tiered_location_string(s_name, gate_p, sub_area)

                    return process_llm_location_update(session_id, formatted, scen_key, char_name=char_name)

            for kp in known_in_z:

                if kp.lower() == curr_p.lower():

                    continue

                kp_lower = kp.lower()

                kp_words = [w for w in kp_lower.replace("'", "").replace("&", " ").split() if len(w) >= 4 and w not in ("school", "main", "place", "area", "grounds")]

                if kp_lower in narr_prose or (kp_words and all(kw in narr_prose or kw.rstrip("s") in narr_prose for kw in kp_words)):

                    formatted = format_tiered_location_string(target_zone, kp, "Main Area")

                    return process_llm_location_update(session_id, formatted, scen_key, char_name=char_name)



    # Step 4: Retain current grounded location

    if current_loc:

        return process_llm_location_update(session_id, current_loc, scen_key, char_name=char_name)



    default_z, default_p, default_s = get_default_tiered_location(scen_key, session_id=session_id, char_name=char_name)

    formatted = format_tiered_location_string(default_z, default_p, default_s)

    return process_llm_location_update(session_id, formatted, scen_key, char_name=char_name)

def is_transit_location(location_str: str) -> bool:

    """Checks if a location string is an active inter-zone transit route."""

    if not location_str:

        return False

    s = str(location_str).strip()

    return any(s.startswith(p) or p in s for p in (

        "🚆 Commute Route:", "🧭 Travel Route:", "🚀 Transit Route:",

        "Commute Route:", "Travel Route:", "Transit Route:", "In Transit:"

    ))

def format_transit_location_string(origin_zone: str, dest_zone: str, scen_key: str = "fantasy") -> str:

    """Returns a formatted transit route location string based on genre."""

    scen = str(scen_key or "").lower()

    orig = str(origin_zone or "Local Area").strip()

    dest = str(dest_zone or "Destination").strip()

    if is_school_scenario(scen):

        return f"🚆 Commute Route: {orig} ➔ {dest}"

    if "cyberpunk" in scen or "sci_fi" in scen or "space" in scen:

        return f"🚀 Transit Route: {orig} ➔ {dest}"

    return f"🧭 Travel Route: {orig} ➔ {dest}"

def is_interzone_travel(current_loc: str, target_loc: str, scen_key: str = "fantasy", session_id: int = 0, char_name: str = "") -> bool:

    """Returns True if traveling from current_loc to target_loc crosses between two distinct Tier 1 Zones."""

    if not current_loc or not target_loc:

        return False

    if is_transit_location(current_loc):

        return False

    curr_z, _, _ = parse_tiered_location(current_loc, scen_key, session_id=session_id, char_name=char_name)

    tgt_z, _, _ = parse_tiered_location(target_loc, scen_key, session_id=session_id, char_name=char_name)

    return curr_z.strip().lower() != tgt_z.strip().lower()


_TACTICAL_FOCAL_POINT_PATTERNS = re.compile(
    r"\b(?:"
    r"(?:behind|under|beneath|beside|underneath|crouched behind|hiding behind|ducking behind|leaning against|by)\s+"
    r"(?:the\s+|a\s+|an\s+)?"
    r"(?P<focal>"
    r"bleachers|desk|teacher'?s\s+desk|counter|curtains?|drapes|bookshelf|bookshelves|stacks|"
    r"lockers?|locker\s+row|pillar|column|tree|bushes|hedges|shrubs|dumpster|crates?|barrels?|"
    r"table|couch|sofa|bed|altar|statue|fountain|vending\s+machines?|stairwell\s+shadow|shadows?|"
    r"window|windowsill|balcony\s+railing|stage\s+wings|partition|screen|booth|alcove\s+bench"
    r")"
    r")\b",
    re.IGNORECASE,
)

_ARCHITECTURAL_SUBROOM_PATTERNS = re.compile(
    r"\b(?:into|enter|entering|sneak\s+into|slip\s+into|step\s+into|head\s+into|go\s+into|open|explore|search\s+inside|unlock)\s+"
    r"(?:the\s+|a\s+|an\s+)?"
    r"(?P<room>"
    r"(?:secret\s+|old\s+|hidden\s+|abandoned\s+|inner\s+|back\s+|private\s+|annex\s+|basement\s+|underground\s+|locked\s+)?"
    r"(?:cellar|basement|boiler\s+room|storage\s+room|annex\s+storage|supply\s+closet|janitor'?s\s+closet|"
    r"equipment\s+shed|back\s+room|back\s+office|inner\s+sanctum|vault|archive\s+room|darkroom|"
    r"dressing\s+room|green\s+room|broadcast\s+booth|server\s+room|attic|loft|wine\s+cellar|"
    r"laboratory\s+annex|prep\s+room|changing\s+stall|private\s+study\s+room|catacombs|crypt)"
    r")\b",
    re.IGNORECASE,
)


def classify_freeform_sublocation(action_text: str) -> Dict[str, Optional[str]]:
    """
    Classifies freeform player spatial exploration into either:
      - kind='focal_point': Tactical cover / furniture micro-position within the current room
      - kind='architectural_room': Separate sub-room / chamber that warrants a child ROOM node in world_nodes
      - kind=None: Not a micro-location or unlisted sub-room phrase
    """
    if not action_text or not str(action_text).strip():
        return {"kind": None, "name": None}

    clean = str(action_text).strip()

    # 1. Check tactical cover / furniture focal points first
    m_focal = _TACTICAL_FOCAL_POINT_PATTERNS.search(clean)
    if m_focal:
        full_phrase = m_focal.group(0).strip()
        full_phrase = re.sub(r"^(?:crouched|hiding|ducking|leaning)\s+", "", full_phrase, flags=re.IGNORECASE).strip()
        formatted_focal = " ".join(w.capitalize() if w.lower() not in ("the", "a", "an", "of", "in", "by") or i == 0 else w.lower() for i, w in enumerate(full_phrase.split()))
        return {"kind": "focal_point", "name": formatted_focal}

    # 2. Check unlisted architectural sub-rooms / chambers
    m_room = _ARCHITECTURAL_SUBROOM_PATTERNS.search(clean)
    if m_room:
        raw_room = m_room.group("room").strip()
        formatted_room = " ".join(w.capitalize() for w in raw_room.split())
        return {"kind": "architectural_room", "name": formatted_room}

    return {"kind": None, "name": None}


def resolve_hybrid_sublocation_or_focal_point(
    session_id: int,
    current_location: str,
    current_node_id: Optional[str],
    action_text: str,
    scen_key: str = "fantasy",
) -> Dict[str, Any]:
    """
    Executes Option C (Hybrid Sub-Location Resolution):
    - If action_text targets tactical cover/furniture ('behind the bleachers', 'under the desk'),
      keeps the current node/location and sets focal_point.
    - If action_text enters an unlisted architectural sub-room ('secret cellar', 'annex storage'),
      spawns a persistent child ROOM node under the current FACILITY in world_nodes and returns
      the updated (new_location, new_node_id).
    """
    info = classify_freeform_sublocation(action_text)
    kind = info.get("kind")
    sub_name = info.get("name")

    if not kind or not sub_name:
        return {"matched": False, "kind": None, "location": current_location, "node_id": current_node_id, "focal_point": None}

    if kind == "focal_point":
        return {
            "matched": True,
            "kind": "focal_point",
            "location": current_location,
            "node_id": current_node_id,
            "focal_point": sub_name,
        }

    # kind == "architectural_room": Spawn or resolve persistent child ROOM node in world_nodes
    pz, pp, _ = parse_tiered_location(current_location, scen_key, session_id=session_id)
    new_loc = format_tiered_location_string(pz, pp, sub_name)
    new_node_id = current_node_id

    if session_id:
        try:
            # Resolve parent FACILITY node
            nodes = db.get_session_world_nodes(session_id)
            node_map = {n["node_id"]: n for n in nodes}
            curr_node = node_map.get(current_node_id) if current_node_id else None
            if not curr_node and current_location:
                resolved_nid = db.resolve_node_id_from_location(session_id, current_location)
                curr_node = node_map.get(resolved_nid) if resolved_nid else None

            fac_id = None
            cat = "academic"
            if curr_node:
                cat = curr_node.get("category") or "academic"
                if curr_node.get("node_type") == "FACILITY":
                    fac_id = curr_node["node_id"]
                elif curr_node.get("node_type") == "ROOM" and curr_node.get("parent_id"):
                    fac_id = curr_node["parent_id"]
                elif curr_node.get("node_type") == "ZONE":
                    fac_id = curr_node["node_id"]

            room_slug = _slugify(f"{pp}_{sub_name}")
            child_node_id = f"sub_dyn_{room_slug}"

            # Check if child node already exists
            existing_child = next(
                (n for n in nodes if n.get("node_type") == "ROOM" and n.get("parent_id") == fac_id and n["name"].lower() == sub_name.lower()),
                None,
            )
            if existing_child:
                new_node_id = existing_child["node_id"]
            else:
                db.save_session_location(
                    session_id=session_id,
                    location_id=child_node_id,
                    zone_name=pz,
                    primary_name=pp,
                    sub_name=sub_name,
                    atmosphere="Enclosed interior chamber",
                    is_dynamic=1,
                )
                if fac_id:
                    db.save_world_node(
                        session_id=session_id,
                        node_id=child_node_id,
                        parent_id=fac_id,
                        name=sub_name,
                        node_type="ROOM",
                        category=cat,
                        privacy_level="private",
                        is_enclosed=1,
                        is_transit_hub=0,
                        access_tier="open",
                        atmosphere="Enclosed interior chamber",
                        is_dynamic=1,
                    )
                    db.save_world_edge(session_id, fac_id, child_node_id, travel_minutes=1, edge_type="internal", is_bidirectional=1)
                new_node_id = child_node_id
        except Exception:
            pass

    return {
        "matched": True,
        "kind": "architectural_room",
        "location": new_loc,
        "node_id": new_node_id,
        "focal_point": None,
    }


from .hierarchy import (
    _build_session_spatial_index, _build_session_zone_index, _resolve_reverse_hierarchy,
    format_tiered_location_string, get_clean_zone_short_name, parse_tiered_location
)
from .seeding import ensure_session_locations_seeded, get_default_tiered_location
from .attributes import is_location_engine_enabled
