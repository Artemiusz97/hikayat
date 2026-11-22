from __future__ import annotations
from .constants import *
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import db
import scenario_data
from .seeds import *
from .seeds import _load_seeds, _slugify, _SEED_PATH

def _is_npc_aware_of_secret_residue(
    npc: Any,
    *,
    participants_low: set[str],
    origin_nid_low: str,
    curr_nid_low: str,
    by_holder: dict[str, list[dict[str, Any]]],
    facts_by_key: dict[str, dict[str, Any]],
) -> bool:
    if not isinstance(npc, dict):
        return True
    aliases = {
        str(npc.get(f) or "").strip().lower()
        for f in ("name", "npc_id", "person_key", "npc_key")
        if str(npc.get(f) or "").strip()
    }
    if not aliases or "player" in aliases:
        return True
    if aliases & participants_low:
        return True
    target_locs = {x for x in (origin_nid_low, curr_nid_low) if x}
    for alias in aliases:
        for kr in (by_holder.get(alias) or ()):
            if str(kr.get("containment_state") or "").strip().lower() == "wiped":
                continue
            fact = facts_by_key.get(str(kr.get("fact_key") or "")) or {}
            if str(fact.get("category") or "").strip().lower() not in ("affair", "crime", "secret"):
                continue
            f_loc = str(fact.get("location_node_id") or "").strip().lower()
            if not f_loc or f_loc in target_locs:
                return True
    return False


def build_node_sensory_and_memory_block(
    session_id: int,
    curr_node: dict,
    current_day: int,
    current_minute: int,
    scen_key: str = "",
    *,
    present_npcs: list | None = None,
    session: dict | None = None,
) -> str:
    """Synthesizes indoor/outdoor time-of-day lighting, acoustics, curfew tension, and persistent room memory."""
    from mechanics.social.origin_mode import is_adult_ahs_operative_fail_closed
    from mechanics.world.schedules import get_time_block_key
    from mechanics.world.locations.access_gate import is_curfew_active, get_node_effective_access_info
    from mechanics.world.world_schedule import (
        is_abandoned_school_node,
        is_high_school_setting,
        is_university_node_or_location,
        is_weekend,
    )

    sess_row: dict | None = dict(session) if isinstance(session, dict) else None
    if sess_row is None and session_id:
        try:
            sess_row = db.get_session(session_id)
        except Exception:
            sess_row = None
    if not scen_key:
        scen_key = str((sess_row or {}).get("scenario") or "high_school_drama")

    is_hs = is_high_school_setting(scen_key)
    is_adult_ahs = is_adult_ahs_operative_fail_closed(sess_row, session_id=session_id, scen_key=scen_key)
    is_anomalous_scen = (
        scenario_data.is_anomalous_incursions_scenario(scen_key)
        or scenario_data.is_anomalous_high_school_scenario(scen_key)
    )
    is_gore_scen = scenario_data.is_gore_scenario(scen_key)
    safe_min = int(current_minute or 0) % 1440
    time_block = get_time_block_key(current_minute)
    is_enc = int(curr_node.get("is_enclosed", 1))
    is_academic = curr_node.get("category") == "academic"
    curr_nid = str(curr_node.get("node_id") or "")
    has_db_node = bool(session_id and curr_nid and db.get_world_node(session_id, curr_nid))
    parent_node = (
        db.get_world_node(session_id, curr_node["parent_id"])
        if (session_id and curr_node.get("parent_id"))
        else None
    )
    is_abandoned_wing = is_abandoned_school_node(curr_node, parent_node)
    is_uni_node = is_university_node_or_location(curr_node, parent_node)
    access_info = get_node_effective_access_info(
        session_id,
        curr_nid,
        current_day=current_day,
        current_minute=current_minute,
        scen_key=scen_key,
        session=sess_row,
    )
    _breach_or_open = bool(
        has_db_node
        and (
            access_info.get("schedule_reason_code") == "after_hours_anomaly_breach"
            or (
                access_info.get("is_unlocked")
                and not access_info.get("curfew_active")
                and access_info.get("status_badge") != "Open"
            )
        )
    )
    is_after_hours_campus = (
        is_hs
        and is_academic
        and not is_abandoned_wing
        and not is_uni_node
        and not is_adult_ahs
        and not _breach_or_open
        and (safe_min >= 1200 or safe_min < 420)
    )
    is_weekend_day = is_weekend(current_day)
    node_probe = f"{curr_node.get('node_id', '')} {curr_node.get('name', '')} {curr_node.get('parent_id', '')}".lower()
    is_theme_park = is_anomalous_scen and any(
        k in node_probe for k in ("zone_theme_park", "loc_theme_park", "theme park", "amusement resort", "loc_tp_")
    )
    is_tp_anomalous_shift = is_theme_park and (safe_min >= 1320 or safe_min < 480)
    is_tp_witching_peak = is_tp_anomalous_shift and (0 <= safe_min < 180)

    from mechanics.world.anomalous_sites.catalog import (
        THEME_PARK_EPICENTER_IDS,
        THEME_PARK_SITE_ID,
        get_anomalous_site_spec,
        is_site_dormant_by_schedule,
        is_site_pacified,
        resolve_anomalous_site,
    )
    anom_spec = resolve_anomalous_site(curr_node=curr_node) if is_anomalous_scen else None

    # Time-of-day sensory profiles (respecting 20:00-07:00 campus lockdown, weekend quiet, & 22:00 Theme Park Anomalous Shift)
    if is_tp_anomalous_shift:
        lighting = (
            "Warped violet-magenta carnival neon and impossible mirror reflections pulsing through stagnant mist"
            if is_enc
            else "Flickering midway bulbs bleeding unnatural violet static into coastal night fog"
        )
        acoustics = (
            "Distorted, backward-looping calliope melodies and glass-chime echoes with zero civilian chatter"
            if is_enc
            else "Creaking phantom roller-coaster tracks, reversed carousel organ notes, and ozone hum"
        )
    elif is_after_hours_campus:
        lighting = "Darkened interior illuminated only by pale moonlight or dim dawn light through glass and security fixtures" if is_enc else "Quiet campus grounds under dim twilight or pale early-dawn sky"
        acoustics = "Hushed, empty after-hours stillness where every whisper and footstep reverberates" if is_enc else "Still, deserted campus air and distant town hum"
    elif time_block == "morning":
        lighting = "Crisp morning sunlight slanting through window panes onto dust motes" if is_enc else "Cool, refreshing morning air under bright early daylight"
        if is_hs and is_academic and is_weekend_day:
            acoustics = "Quiet, empty weekend stillness with only distant practice sounds outside" if is_enc else "Peaceful weekend morning breeze with sparse club activity in the distance"
        else:
            acoustics = "Quiet morning murmur with rhythmic hallway footsteps in the distance" if is_enc else "Chirping birds and gentle breeze blowing across open paths"
    elif time_block == "lunch":
        lighting = "Bright midday illumination casting sharp shadows" if is_enc else "Warm overhead sun shining brightly"
        if is_hs and is_academic and is_weekend_day:
            acoustics = "Calm weekend midday quiet indoors" if is_enc else "Relaxed weekend midday breeze and distant athletic training"
        else:
            acoustics = "Lively laughter, chatter, and clatter of lunch trays echoing throughout" if is_enc else "Bustling social activity and pleasant midday breeze"
    elif time_block == "afternoon":
        lighting = "Warm afternoon light turning golden along polished floors" if is_enc else "Warm golden rays and lengthening afternoon shadows"
        acoustics = "Subtle hum of academic or club activities, turning pages, and focused dialogue" if is_enc else "Distant shouts from practice fields and rustling leaves"
    elif time_block == "evening":
        lighting = "Amber dusk glow outside fading into soft fluorescent corridor lighting" if is_enc else "Crimson-violet sunset twilight sky with streetlamps flickering on"
        acoustics = "Footsteps of late departures echoing in increasingly quiet spaces" if is_enc else "Cooling evening breeze and ambient dusk quiet"
    else:  # night
        lighting = "Darkened interior illuminated only by pale moonlight through glass or dim security fixtures" if is_enc else "Dark night sky under stars, quiet moonlight casting long deep shadows"
        acoustics = "Hushed, secretive acoustics where every whisper and footstep reverberates" if is_enc else "Nocturnal stillness, chilly night wind, and distant city hum"

    lines = [
        f"- Physical Environment & Atmosphere: {'Enclosed Interior' if is_enc else 'Open-Air Exterior'} | {lighting} | {acoustics}."
    ]
    raw_room_atm = str(curr_node.get("atmosphere") or "").strip()
    if raw_room_atm and str(curr_node.get("node_type") or "").upper() == "ROOM":
        room_sensory = raw_room_atm
        if raw_room_atm.startswith("{"):
            try:
                parsed_atm = json.loads(raw_room_atm)
                room_sensory = str(parsed_atm.get("sensory") or "").strip()
            except Exception:
                room_sensory = ""
        if room_sensory and room_sensory not in lines[0]:
            lines.append(f"- Room Atmosphere & Sensory: {room_sensory}")

    # Curfew & After-Hours Trespassing tension check
    c_start = curr_node.get("curfew_start_min")
    c_end = curr_node.get("curfew_end_min")
    _stair_breach_fallback = (
        not has_db_node
        and any(k in node_probe for k in ("loc_13th_stairwell", "sub_4th_floor_landing", "sub_mirror_washroom", "sub_13th_step"))
        and (safe_min >= 1200 or safe_min < 360)
    )
    _curfew_warranted = (
        bool(access_info.get("curfew_active") or access_info.get("is_trespassing"))
        if has_db_node
        else (
            (is_curfew_active(c_start, c_end, current_minute) or safe_min >= 1200 or safe_min < 420)
            and not _stair_breach_fallback
        )
    )
    if is_hs and is_abandoned_wing:
        lines.append(
            "- [ABANDONED SCHOOL BUILDING — UNRESTRICTED 24/7]: "
            "Nobody bothers to lock the doors or patrol this derelict wing. It remains accessible at all hours."
        )
    elif is_hs and is_academic and not is_uni_node and not is_adult_ahs and not _breach_or_open and _curfew_warranted:
        lines.append(
            "- [CAMPUS CURFEW & AFTER-HOURS TRESPASSING (20:00–07:00) — AFTER-HOURS TENSION]: "
            "All students and teachers have returned home, main corridor lights are dark, exterior doors are locked from the outside (exit remains unobstructed), "
            "and security footsteps echo down distant halls. Staying on campus during these hours is considered trespassing; maintain a hushed, illicit after-hours atmosphere."
        )
    elif is_tp_anomalous_shift:
        tp_spec = get_anomalous_site_spec(THEME_PARK_SITE_ID) or {}
        tp_base = str(tp_spec.get("base_horror_sensory") or (
            "The Theme Park & Amusement Resort has closed to the public at night and entered its Anomalous Shift; "
            "all mundane tourists and park staff are gone, rides turn on by themselves, and mirror reflections move independently."
        ))
        tp_line = f"- [THEME PARK ANOMALOUS SHIFT — CARNIVAL NIGHTMARE]: {tp_base}"
        if is_gore_scen and tp_spec.get("gore_horror_sensory"):
            tp_line += f" {tp_spec['gore_horror_sensory']}"
        if is_tp_witching_peak and tp_spec.get("witching_peak_sensory"):
            tp_line += f" {tp_spec['witching_peak_sensory']}"
        lines.append(tp_line)
        tp_rule = tp_spec.get("domain_rule") if isinstance(tp_spec.get("domain_rule"), dict) else {}
        if tp_rule.get("name") and tp_rule.get("hazard_cue"):
            lines.append(f"- [ACTIVE DOMAIN RULE — {tp_rule['name']}]: {tp_rule['hazard_cue']}")
    elif is_theme_park and 1290 <= safe_min < 1320:
        lines.append(
            "- [THEME PARK CLOSING WARNING — PRE-SHIFT EVACUATION]: "
            "Park loudspeakers broadcast final closing chimes urging families toward the exits before nightfall, "
            "while faint ozone static and flickering ride lights foreshadow the impending Anomalous Shift."
        )
    elif is_theme_park and curr_nid.lower() in THEME_PARK_EPICENTER_IDS:
        tp_spec = get_anomalous_site_spec(THEME_PARK_SITE_ID) or {}
        if tp_spec.get("daytime_cordon_sensory"):
            lines.append(f"- [CORDONED DURING PUBLIC HOURS — BUREAU WARNING]: {tp_spec['daytime_cordon_sensory']}")

    if is_anomalous_scen and anom_spec and anom_spec.get("site_type") != "theme_park_night":
        if is_site_dormant_by_schedule(anom_spec, scen_key=scen_key, current_minute=safe_min, node_id=curr_nid):
            lines.append(
                "- [ANOMALOUS SITE DORMANT (DAYTIME HOURS) — DUSTY STILLNESS]: "
                "Daylight keeps the site's darker spatial phenomenon dormant for now; only stale dust and faint chill linger along untouched masonry."
            )
        elif session_id and is_site_pacified(session_id, site_id=anom_spec["site_id"], node_id=curr_nid):
            pac_txt = str(anom_spec.get("pacified_sensory") or "The lethal anomaly has been contained into eerie quiet.")
            amb_txt = str((anom_spec.get("domain_rule") or {}).get("ambient_summary") or "").strip()
            lines.append(
                f"- [STABILIZED ANOMALOUS SITE — PERSISTENT AMBIENT EFFECT]: {pac_txt}"
                + (f" (Ambient Resonance: {amb_txt})" if amb_txt else "")
            )
        else:
            grade_r = str(anom_spec.get("threat_grade_roman") or "I")
            subgenre = str(anom_spec.get("horror_subgenre") or "Anomalous Hazard")
            sensory_txt = str(anom_spec.get("base_horror_sensory") or "")
            if is_gore_scen and anom_spec.get("gore_horror_sensory"):
                sensory_txt = f"{sensory_txt} {anom_spec['gore_horror_sensory']}".strip()
            lines.append(f"- [ANOMALOUS SITE HORROR — GRADE {grade_r} ({subgenre})]: {sensory_txt}")
            rule = anom_spec.get("domain_rule") if isinstance(anom_spec.get("domain_rule"), dict) else {}
            if rule.get("name") and rule.get("hazard_cue"):
                lines.append(f"- [ACTIVE DOMAIN RULE — {rule['name']}]: {rule['hazard_cue']}")

    # Room memory / scene residue check (with Z2 epistemic privacy guard when unaware NPCs are present)
    res_log = list(access_info.get("scene_residue_log") or [])
    fallback_residue = str(access_info.get("scene_residue") or "")
    if not res_log and fallback_residue:
        res_log = [{
            "text": fallback_residue,
            "is_secret_residue": any(tok in fallback_residue.lower() for tok in ("intimate encounter", "bypassed security")),
            "participants": [],
            "origin_node_id": "",
        }]

    curr_node_type = str(curr_node.get("node_type") or "").strip().upper()
    curr_nid_low = curr_nid.strip().lower()
    epistemic_matrix: dict[str, Any] = {}
    has_secret_entry = any(
        isinstance(m, dict)
        and (
            bool(m.get("is_secret_residue"))
            or any(tok in str(m.get("text") or "").lower() for tok in ("intimate encounter", "bypassed security"))
        )
        for m in res_log
    )
    if res_log and present_npcs and has_secret_entry and session_id:
        epistemic_matrix = db.preload_epistemic_matrix(session_id)

    by_holder = epistemic_matrix.get("by_holder") or {}
    facts_by_key = epistemic_matrix.get("facts_by_key") or {}
    visible_log: list[dict[str, Any]] = []
    guard_unaware_names: list[str] = []

    for m in res_log:
        if not isinstance(m, dict) or not m.get("text"):
            continue
        m_txt_low = str(m.get("text") or "").lower()
        is_secret_m = bool(m.get("is_secret_residue")) or any(
            tok in m_txt_low for tok in ("intimate encounter", "bypassed security")
        )
        origin_nid = str(m.get("origin_node_id") or "").strip().lower()
        if is_secret_m and present_npcs:
            parts_low = {str(p or "").strip().lower() for p in (m.get("participants") or ()) if str(p or "").strip()}
            unaware_here: list[str] = []
            for p_npc in present_npcs:
                if not isinstance(p_npc, dict):
                    continue
                p_name = str(p_npc.get("name") or "").strip()
                if not p_name:
                    continue
                if not _is_npc_aware_of_secret_residue(
                    p_npc,
                    participants_low=parts_low,
                    origin_nid_low=origin_nid,
                    curr_nid_low=curr_nid_low,
                    by_holder=by_holder,
                    facts_by_key=facts_by_key,
                ):
                    if p_name not in unaware_here:
                        unaware_here.append(p_name)

            if unaware_here and curr_node_type == "FACILITY" and (not origin_nid or origin_nid != curr_nid_low):
                continue
            for uname in unaware_here:
                if uname not in guard_unaware_names:
                    guard_unaware_names.append(uname)

        visible_log.append(m)

    if visible_log:
        lines.append("- PERSISTENT ROOM MEMORY (Past Moments Recorded in this Space):")
        for m in visible_log:
            lines.append(f"  * {m['text']}")
        if guard_unaware_names:
            lines.append(
                f"  * [EPISTEMIC PRIVACY GUARD]: Present NPC(s) ({', '.join(guard_unaware_names)}) "
                "were NOT part of and do NOT know about this private/illicit room memory—"
                "do NOT have them react to or reference it unless explicitly told."
            )
        lines.append("  (Subtly weave this history or emotional residue into your narration when relevant.)")

    if access_info.get("is_unlocked") and access_info.get("access_tier") in ("restricted", "private"):
        lines.append("- ACCESS PERMISSION: Door unlocked (access granted for this session/day).")

    try:
        from .residences import get_player_owned_or_starter_property_for_node
        owned_res = get_player_owned_or_starter_property_for_node(session_id, curr_node.get("node_id", ""))
        if owned_res:
            cat_meta = owned_res.get("catalog_entry") or {}
            qual_sensory = str(cat_meta.get("luxury_sensory") or cat_meta.get("description") or "").strip()
            if qual_sensory:
                lines.append(
                    f"- PRIVATE RESIDENCE AMBIENCE: Player's personal safe haven ({qual_sensory}). "
                    "Convey comfort and privacy through sensory prose only—never mention game numbers or bonuses."
                )
    except Exception:
        pass

    detailed_props = get_detailed_node_props(session_id, curr_node.get("node_id", ""), scenario_key=scen_key)
    room_props = [p["name"] for p in detailed_props] if detailed_props else get_node_props(session_id, curr_node.get("node_id", ""), scenario_key=scen_key)
    if room_props:
        lines.append(f"- Room Props & Micro-Anchors (for `focal_point` positioning): {', '.join(room_props)}.")
        searched_props = [p["name"] for p in detailed_props if p.get("is_searched") or p.get("is_looted")]
        if searched_props:
            lines.append(f"- Previously Searched Props: {', '.join(searched_props)}.")

    return "\n".join(lines)


def format_llm_location_context(
    session_id: int,
    current_location_raw: str,
    scenario_key: str,
    char_name: str = "",
    *,
    present_npcs: list | None = None,
    ensure_seeded: bool = True,
) -> str:
    """Formats the location context string and real-time movement rules for the LLM prompt."""

    if not is_location_engine_enabled(scenario_key):

        return ""



    if ensure_seeded:
        ensure_session_locations_seeded(session_id, scenario_key, char_name=char_name)

    zone, primary, sub = parse_tiered_location(current_location_raw, scenario_key, session_id=session_id, char_name=char_name)

    formatted_current = format_tiered_location_string(zone, primary, sub)



    existing = db.get_session_locations(session_id)
    world_nodes = db.get_session_world_nodes(session_id) if hasattr(db, "get_session_world_nodes") else []

    zone_atm = ""
    fac_atm = ""

    # 1. First probe spatial graph world_nodes for explicit tier atmosphere
    for n in world_nodes:
        if n.get("node_type") == "ZONE" and n.get("name") == zone and n.get("atmosphere"):
            zone_atm = n.get("atmosphere")
        elif n.get("node_type") == "FACILITY" and n.get("name") == primary and n.get("atmosphere"):
            fac_atm = n.get("atmosphere")

    # 2. Fall back to session_locations rows
    if not fac_atm:
        for r in existing:
            if r.get("zone_name") == zone and r.get("primary_name") == primary and r.get("atmosphere"):
                fac_atm = r.get("atmosphere")
                break

    if not zone_atm:
        for r in existing:
            if r.get("zone_name") == zone and r.get("atmosphere"):
                zone_atm = r.get("atmosphere")
                break

    zone_data = parse_zone_environment_data(zone_atm)
    fac_data = parse_zone_environment_data(fac_atm)

    env_lines = []
    if zone_data.get("theme"):
        env_lines.append(f"- Zone Theme: {zone_data['theme']}")
    if fac_data.get("theme") and fac_data.get("theme") != zone_data.get("theme"):
        env_lines.append(f"- Facility Architecture & Theme: {fac_data['theme']}")

    fac_features = fac_data.get("features")
    zone_features = zone_data.get("features")
    if fac_features:
        env_lines.append(f"- Facility Features: {fac_features}")
    elif zone_features:
        env_lines.append(f"- Environmental Features: {zone_features}")

    fac_sensory = fac_data.get("sensory")
    zone_sensory = zone_data.get("sensory")
    if fac_sensory:
        env_lines.append(f"- Ambient Facility Atmosphere: {fac_sensory}")
    elif zone_sensory:
        env_lines.append(f"- Ambient Sensory: {zone_sensory}")

    env_text = ("\n" + "\n".join(env_lines)) if env_lines else ""



    arch_label, _ = get_location_archetype(primary, zone_name=zone, scen_key=scenario_key)



    has_school_campus = scenario_data.has_school_campus_mechanics(scenario_key)
    is_ahs_scen = scenario_data.is_anomalous_high_school_scenario(scenario_key)
    campus_name = get_session_school_name(session_id, scenario_key) if has_school_campus else ""
    athletics_name = get_session_athletics_complex_name(session_id, scenario_key) if has_school_campus else ""
    commons_name = get_session_student_commons_name(session_id, scenario_key) if has_school_campus else ""
    arts_name = get_session_cultural_arts_name(session_id, scenario_key) if has_school_campus else ""
    abandoned_name = get_session_abandoned_campus_name(session_id, scenario_key) if has_school_campus else ""
    comm_name = get_session_commercial_district_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""
    res_name = get_session_residential_neighborhood_name(session_id, scenario_key) if is_school_scenario(scenario_key) else ""

    district_lines = []
    if is_school_scenario(scenario_key):
        if campus_name:
            district_lines.append(f"- [Campus - Academic Wing & Entrance Gate]: '{campus_name}' (Classrooms, Homeroom, Teachers' Staff Room, Library, Chemistry Lab, Rooftop, Shoe Lockers & Main Gate)")
        if athletics_name:
            district_lines.append(f"- [Campus - Athletics Complex]: '{athletics_name}' (Main Gymnasium, 400m Running Track, Stadium Field, Swimming Pool Facility, Martial Arts Dojo, Behind Gym Sheds)")
        if commons_name:
            district_lines.append(f"- [Campus - Social Commons & Dining]: '{commons_name}' (Central Courtyard Fountain, Cherry Tree, Campus Dining Hall & Cafeteria, Vending Machine Pavilion, Botanical Glasshouse)")
        if arts_name:
            district_lines.append(f"- [Campus - Cultural Arts & Student Union]: '{arts_name}' (Student Council Office, School Auditorium Stage, Music Wing Rehearsal Hall, Fine Arts Studio, Broadcasting Room, Clubrooms)")
        if abandoned_name:
            district_lines.append(f"- [Campus - Abandoned Old Campus]: '{abandoned_name}' (Decaying Clock Tower, Old Storage Room 3-B, Derelict Old Gymnasium, Boarded Old Infirmary, Overgrown Wings)")
    elif is_ahs_scen and campus_name:
        district_lines.append(
            f"- [Campus - Unified High School Zone]: '{campus_name}' "
            f"(Main Academic Building, Courtyard & Cafeteria, Athletics & Track, Cultural Arts & Student Union, "
            f"and {abandoned_name or 'Abandoned Old Campus Wing'} with Dusty Annex Clockwork Archive)"
        )
    elif campus_name:
        district_lines.append(f"- [Campus]: '{campus_name}' (Classrooms, Facilities, School Grounds)")

    if comm_name:
        district_lines.append(f"- [Commercial]: '{comm_name}' (Shops, Cafés, Entertainment & Arcades)")
    if res_name:
        district_lines.append(f"- [Residential]: '{res_name}' (Family Residences, Houses, Apartments, Neighborhood Parks)")

    regional_block = ("REGIONAL DISTRICT HIGHLIGHTS:\n" + "\n".join(district_lines) + "\n\n") if district_lines else ""

    res_rule = f"- RESIDENTIAL ZONE RULE: All NPC and Player houses, family residences, apartments, and residential cul-de-sacs MUST ALWAYS be placed in the zone tagged [Residential] ('{res_name}'). NEVER place a character's house inside the Commercial District or School Campus.\n- HOUSEHOLD NAMING CONVENTION: Use the family surname for character residences (e.g. '{res_name} ➔ Anderson Residence ➔ Living Room'). Sibling/family characters share the same household.\n" if res_name else ""

    campus_rules = ""
    if has_school_campus:
        campus_rules = (
            f"- CAMPUS ZONE & BUILDING TOPOGRAPHY: The school campus is unified under the Zone '{campus_name}', which contains dedicated Tier 2 building complexes: 'Main Campus Building' (Academic classrooms, Homeroom, Library, Staff Room, Main Gates), '{athletics_name}' (Gymnasium & Varsity Court, Track, Pool, Dojo, Behind-Gym Sheds), '{commons_name}' (Central Courtyard, Cafeteria, Botanical Glasshouse), 'Student Council Office' (dedicated council suite, directive board, requisition counter & archive vault), 'Campus Auditorium & Drama Theater' (proscenium stage, box office, callboard, costume wardrobe & dressing suite), '{arts_name}' (Music/Art Studios, Media Room, Occult Room 3-B & Esports Clubroom), and '{abandoned_name}' (Old Campus, Boiler-Room Den & hidden underground wings). Place specific rooms/facilities in Tier 3, and use `focal_point` for room furniture/micro-spots.\n"
            f"- CHARACTER'S DESK RULE: A student character's personal desk (e.g. 'Player's Desk' / '<Name>'s Desk') ONLY exists in their designated homeroom classroom. In the Student Council Office, use 'President's Desk', 'Meeting Table', or 'Archive Files & Safe'—NEVER place or generate a student's personal homeroom desk in the council office or other rooms.\n"
        )



    # Format established nearby destinations catalog

    nearby_blocks = []

    curr_zone_places: Dict[str, List[str]] = {}

    for r in existing:

        if r.get("zone_name", "").strip().lower() == zone.strip().lower():

            p_name = r.get("primary_name", "")

            s_name = r.get("sub_name", "")

            if p_name:

                curr_zone_places.setdefault(p_name, [])

                if s_name and s_name not in ("Main Area", "") and s_name not in curr_zone_places[p_name]:

                    curr_zone_places[p_name].append(s_name)



    if curr_zone_places:

        p_lines = []

        for p_k, p_subs in list(curr_zone_places.items())[:6]:

            subs_str = f" ({', '.join(p_subs[:3])})" if p_subs else ""

            p_lines.append(f"  * {p_k}{subs_str}")

        nearby_blocks.append(f"- [Current Zone: {zone}]:\n" + "\n".join(p_lines))



    # Connected zones (e.g. Student Commons if in Arts, Academic, Athletics, Abandoned)
    connected_zones = []
    if has_school_campus:

        if zone.strip().lower() == arts_name.strip().lower() and commons_name:

            connected_zones.append(commons_name)

        elif zone.strip().lower() == athletics_name.strip().lower() and commons_name:

            connected_zones.append(commons_name)

        elif zone.strip().lower() == abandoned_name.strip().lower() and commons_name:

            connected_zones.append(commons_name)

        elif zone.strip().lower() == campus_name.strip().lower() and commons_name:

            connected_zones.append(commons_name)

        elif zone.strip().lower() == commons_name.strip().lower():

            connected_zones.extend([z for z in (arts_name, campus_name, athletics_name) if z])



    for cz in connected_zones:

        cz_places: Dict[str, List[str]] = {}

        for r in existing:

            if r.get("zone_name", "").strip().lower() == cz.strip().lower():

                p_name = r.get("primary_name", "")

                s_name = r.get("sub_name", "")

                if p_name:

                    cz_places.setdefault(p_name, [])

                    if s_name and s_name not in ("Main Area", "") and s_name not in cz_places[p_name]:

                        cz_places[p_name].append(s_name)

        if cz_places:

            p_lines = []

            for p_k, p_subs in list(cz_places.items())[:5]:

                subs_str = f" ({', '.join(p_subs[:3])})" if p_subs else ""

                p_lines.append(f"  * {p_k}{subs_str}")

            nearby_blocks.append(f"- [Connected Zone (5m walk): {cz}]:\n" + "\n".join(p_lines))



    nearby_dest_section = ""
    if nearby_blocks:
        nearby_dest_section = (
            "ESTABLISHED NEARBY DESTINATIONS (PREFER MATCHING THESE BEFORE CREATING NEW PLACES):\n"
            + "\n".join(nearby_blocks)
            + "\n\n"
        )

    session = db.get_session(session_id) if session_id else None
    curr_node_id = session.get("current_node_id") if session else None
    curr_node = db.get_world_node(session_id, curr_node_id) if (session_id and curr_node_id) else None
    curr_day, curr_min, _ = db.get_session_time(session_id) if session_id else (1, 480, "morning")

    graph_section = ""
    if session_id and curr_node:
        outgoing = db.get_outgoing_edges(session_id, curr_node_id)
        edge_lines = []
        from .pathfinding import is_node_hidden
        for e in outgoing:
            to_id = e.get("to_node_id")
            if str(e.get("edge_type") or "") == "leyline_spirit_passage" and int(e.get("is_locked") or 0) == 1:
                continue
            target_w_node = db.get_world_node(session_id, to_id) if to_id else None
            if target_w_node and is_node_hidden(target_w_node):
                continue
            to_name = e.get("to_node_name") or to_id
            t_min = e.get("travel_minutes", 1)
            is_locked = e.get("is_locked", 0)
            lock_desc = " [LOCKED]" if is_locked else ""
            edge_lines.append(f"  * Node [{to_id}] '{to_name}' ({t_min}m travel{lock_desc})")

        edges_text = "\n".join(edge_lines) if edge_lines else "  * (No outgoing paths; enclosed dead-end)"
        sample_node_id = outgoing[0]['to_node_id'] if outgoing else 'node_id'
        is_thub = db.is_node_or_parent_transit_hub(session_id, curr_node_id)
        thub_note = " [Transit Hub Fast-Travel Enabled]" if is_thub else ""

        sensory_memory_text = build_node_sensory_and_memory_block(
            session_id,
            curr_node,
            curr_day,
            curr_min,
            scen_key=scenario_key,
            present_npcs=present_npcs,
        )

        graph_section = (
            f"SPATIAL GRAPH TOPOGRAPHY & DIRECTLY CONNECTED EDGES:\n"
            f"- Current Spatial Node: [{curr_node['node_id']}] '{curr_node['name']}' (Type: {curr_node['node_type']}, Privacy: {curr_node.get('privacy_level', 'semi_private')}, Access: {curr_node.get('access_tier', 'open')}){thub_note}\n"
            f"{sensory_memory_text}\n"
            f"- Directly Traversable Adjacent Pathways (Edges):\n{edges_text}\n\n"
            f"- SPATIAL MOVEMENT & DIALOGUE GATING RULE:\n"
            f"  1. If the player's choice is a TRAVEL / MOVEMENT action: select one of the adjacent nodes above and output its node ID in `destination_node_id` (e.g. '{sample_node_id}').\n"
            f"  2. If the player is NOT traveling (dialogue, social chat, skill check, observation, romantic/intimate encounter, sitting down): leave `destination_node_id` as null/empty, keep `location` identical, and update `focal_point` for micro-positioning (e.g. 'Leaning against the glass panes', 'At the teacher\\'s desk'). The macro location will strictly NOT change.\n\n"
        )

    return (
        f"CURRENT SCENE LOCATION (Tiered 3-Level Spatial System):\n"
        f"- Current Position: {formatted_current}{env_text}\n"
        f"- Current Breakdown: [Tier 1: Zone/Biome] = '{zone}' | [Tier 2: Physical Place ({arch_label})] = '{primary}' | [Tier 3: Sub-Location/Spot] = '{sub}'\n\n"
        f"{graph_section}"
        f"{regional_block}"
        f"{nearby_dest_section}"

        f"SPATIAL SYSTEM RULES:\n"

        f"- Instruction: Report `location` in your JSON response as `Zone Name ➔ Primary Place ➔ Sub-Location`.\n"

        f"- GROUNDED PHYSICAL RULE FOR TIER 2: Tier 2 (Primary Place) MUST ALWAYS be a concrete physical structure, settlement, building, establishment, or distinct geographical feature (e.g. 'Hunter\'s Outpost', 'Old Timber Mill', 'Gnarled Root Archway', 'Bramble-Choked Den', 'Class 1-A (Homeroom)'). NEVER output poetic event titles or abstract phrases (e.g. 'The Blue Flame Beyond the Roots', 'A Quiet Moment', 'The Meeting') as Tier 2.\n"

        f"- EXISTING-LOCATION-FIRST DIRECTIVE: When characters leave an enclosed room to talk privately, seek fresh air, go to gardens/courtyard, or visit a terrace, YOU MUST ALWAYS MATCH AN ESTABLISHED NEARBY VENUE from the catalog above (e.g. use 'Old Garden Terrace', 'Botanical Glasshouse', 'Central Courtyard', or 'Student Clubroom Corridor'). NEVER fabricate a duplicate location or nest outdoor environments inside an indoor room.\n"

        f"- PHYSICAL CONTAINER COMPATIBILITY RULE: Enclosed interior rooms (e.g. '{primary}', 'Homeroom Classroom', 'Teachers\' Staff Room', 'Chemistry Lab') CAN NEVER physically contain outdoor or transitional spaces like a terrace, garden, courtyard, balcony, or rooftop as Tier 3. If characters step out to a terrace or garden, Tier 2 MUST change to that terrace or garden!\n"

        f"- HIERARCHY CONTINUITY RULE: ONLY keep Tier 2 identical if characters remain physically inside '{primary}' (e.g. sitting at a desk, looking through files, walking to the window). As soon as characters leave '{primary}' (e.g. walking through halls, heading out to a terrace or courtyard), Tier 2 MUST be updated to the new place.\n"

        f"{campus_rules}"

        f"{res_rule}"

        f"- REAL-TIME MOVEMENT DIRECTIVE: If the narration describes characters leaving a room/building, walking into a hallway/corridor, traveling to another building, or visiting someone's house, you MUST update `location` in your output to reflect their new setting (e.g. '{zone} ➔ 2F Hallway ➔ Secluded Alcove' or '{res_name or 'Residential Area'} ➔ Anderson Residence ➔ Living Room'). NEVER leave `location` pointing to the previous room if the characters have exited it.\n"

    )

def get_discovered_location_tree(session_id: int, scenario_key: str = "high_school_drama") -> Dict[str, Dict[str, List[str]]]:

    """

    Returns discovered locations grouped by Zone ➔ Primary Place ➔ Sub-Locations.

    Useful for building /map commands and detailed location queries.

    """

    ensure_session_locations_seeded(session_id, scenario_key)

    rows = db.get_session_locations(session_id)



    tree: Dict[str, Dict[str, List[str]]] = {}

    for r in rows:

        z = r.get("zone_name") or "Starting Zone"

        p = r.get("primary_name") or "Starting Location"

        s = r.get("sub_name") or "Focal Spot"

        if "{" in z or "{" in p or "{" in s:
            from .hierarchy import resolve_session_location_tokens
            z = resolve_session_location_tokens(session_id, z, scenario_key)
            p = resolve_session_location_tokens(session_id, p, scenario_key)
            s = resolve_session_location_tokens(session_id, s, scenario_key)

        if z not in tree:

            tree[z] = {}

        if p not in tree[z]:

            tree[z][p] = []

        if s not in tree[z][p]:

            tree[z][p].append(s)



    return tree

def get_discovered_primary_locations(session_id: int, scenario_key: str = "high_school_drama") -> Dict[str, List[str]]:

    """

    Returns unique Primary Locations grouped by Zone.

    Used for the 'Move Location' button dropdown so players select rooms/buildings rather than micro-spots.

    """

    tree = get_discovered_location_tree(session_id, scenario_key)

    result: Dict[str, List[str]] = {}

    for zone_name, primaries in tree.items():

        result[zone_name] = list(primaries.keys())

    return result

def format_travel_eta_tag(minutes: int, is_same_zone: bool = False, scen_key: str = "fantasy", is_here: bool = False) -> str:
    """Formats a human-readable ETA badge string (e.g. 'Here', '~3m walk', '~12m transit', '~45m trek')."""
    if is_here or int(minutes or 0) <= 0:
        return "Here"
    mins = max(1, int(minutes))
    if mins < 60:
        dur = f"~{mins}m"
    else:
        hrs, rem = divmod(mins, 60)
        dur = f"~{hrs}h {rem}m" if rem else f"~{hrs}h"

    if is_same_zone or mins <= 6:
        return f"{dur} walk"

    sk = str(scen_key or "").lower()
    if any(k in sk for k in ("anomalous", "urban", "school", "slice_of_life", "cyberpunk", "sci_fi", "space", "steampunk")):
        return f"{dur} transit"
    return f"{dur} trek"


_QUEST_TAG_PRIORITY = (
    "⚡ Story Climax",
    "⭐ Story Quest",
    "🎯 Bounty Target",
    "💌 Meetup",
)
_QUEST_TAG_KIND = {
    "⚡ Story Climax": "climax",
    "⭐ Story Quest": "story",
    "🎯 Bounty Target": "bounty",
    "💌 Meetup": "meetup",
}


def _summarize_quest_markers(markers_list: list[str], classify_fn) -> tuple[list[str], str, str]:
    """Returns (distinct_tags_in_priority_order, primary_tag, primary_kind) for a list of marker strings."""
    found_tags: set[str] = set()
    for qm in (markers_list or []):
        _kind, tag = classify_fn(qm)
        if tag:
            found_tags.add(tag)
    ordered_tags = [t for t in _QUEST_TAG_PRIORITY if t in found_tags]
    primary_tag = ordered_tags[0] if ordered_tags else ""
    primary_kind = _QUEST_TAG_KIND.get(primary_tag, "")
    return ordered_tags, primary_tag, primary_kind


def _entry_matches_building(entry: dict, zone_name: str, place_name: str) -> bool:
    """Returns True when a waypoint entry's zone/primary hints are compatible with this building."""
    eh_p = str(entry.get("primary_hint") or "").strip().lower()
    eh_z = str(entry.get("zone_hint") or "").strip().lower()
    p_low = str(place_name or "").strip().lower()
    z_low = str(zone_name or "").strip().lower()
    p_ok = (not eh_p) or (eh_p == p_low) or (len(eh_p) >= 4 and (eh_p in p_low or p_low in eh_p))
    z_ok = (not eh_z) or (eh_z == z_low) or (len(eh_z) >= 4 and (eh_z in z_low or z_low in eh_z))
    return p_ok and z_ok


def _match_marker_to_sub_rooms(
    qm: str,
    entries_for_marker: list[dict],
    sub_details: list[dict],
    zone_name: str,
    place_name: str,
) -> list[int]:
    """Resolves a marker to matching Tier 3 room indices within this building in strict priority order."""
    if not sub_details:
        return []

    # Priority 1: Exact Room node_id match
    entry_node_ids = {
        str(e.get("target_node_id") or "").strip()
        for e in entries_for_marker
        if str(e.get("target_node_id") or "").strip()
    }
    if entry_node_ids:
        nid_hits = [
            idx for idx, sd in enumerate(sub_details)
            if str(sd.get("node_id") or "").strip() in entry_node_ids
        ]
        if nid_hits:
            return nid_hits

    # Priority 2: Scoped sub_hint match inside THIS building (prevents cross-building collisions)
    p_low = str(place_name or "").strip().lower()
    z_low = str(zone_name or "").strip().lower()
    scoped_hints: list[str] = []
    for e in entries_for_marker:
        s_hint = str(e.get("sub_hint") or "").strip()
        if s_hint and _entry_matches_building(e, zone_name, place_name):
            scoped_hints.append(s_hint.lower())
        elif not s_hint:
            # Handle 2-tier shortcut 'Zone ➔ RoomName' scoped to this zone when primary_hint is NOT the building
            eh_p = str(e.get("primary_hint") or "").strip().lower()
            eh_z = str(e.get("zone_hint") or "").strip().lower()
            z_ok = (not eh_z) or (eh_z == z_low) or (len(eh_z) >= 4 and (eh_z in z_low or z_low in eh_z))
            not_building = bool(eh_p) and eh_p != p_low and eh_p not in p_low and p_low not in eh_p
            if z_ok and not_building:
                scoped_hints.append(eh_p)

    if scoped_hints:
        exact_hits = [
            idx for idx, sd in enumerate(sub_details)
            if str(sd.get("name") or "").strip().lower() in scoped_hints
        ]
        if exact_hits:
            return exact_hits
        partial_hits = [
            idx for idx, sd in enumerate(sub_details)
            if (sd_low := str(sd.get("name") or "").strip().lower())
            and any(
                (len(sh) >= 4 and len(sd_low) >= 4 and (sh in sd_low or sd_low in sh))
                for sh in scoped_hints
            )
        ]
        if partial_hits:
            return partial_hits

    # Priority 3: Explicit room name appearing in marker text
    qm_low = str(qm or "").lower()
    wb_hits: list[tuple[int, int]] = []
    sub_hits: list[tuple[int, int]] = []
    for idx, sd in enumerate(sub_details):
        sd_low = str(sd.get("name") or "").strip().lower()
        if len(sd_low) < 5:
            continue
        if re.search(rf"(?<!\w){re.escape(sd_low)}(?!\w)", qm_low):
            wb_hits.append((idx, len(sd_low)))
        elif sd_low in qm_low:
            sub_hits.append((idx, len(sd_low)))
    chosen = wb_hits or sub_hits
    if chosen:
        max_len = max(length for _i, length in chosen)
        return [idx for idx, length in chosen if length == max_len]

    # Priority 4: Target NPC room inside THIS building
    npc_candidates: set[str] = set()
    for e in entries_for_marker:
        if _entry_matches_building(e, zone_name, place_name):
            npc = str(e.get("target_npc") or "").strip().lower()
            if npc:
                npc_candidates.add(npc)
    m_npc = re.search(r"\(👤\s*([^)]+)\)", str(qm or ""))
    if m_npc:
        npc_txt = m_npc.group(1).strip().lower()
        if npc_txt:
            npc_candidates.add(npc_txt)
    if npc_candidates:
        npc_hits = [
            idx for idx, sd in enumerate(sub_details)
            if any(
                str(kn.get("name") or "").strip().lower() in npc_candidates
                for kn in (sd.get("known_npcs_here") or [])
            )
        ]
        if npc_hits:
            return npc_hits

    return []


def _assign_tier3_markers_for_place(
    p_item: dict,
    z_nm: str,
    entries_by_marker: dict[str, list[dict]],
    entries_by_node_id: dict[str, list[dict]],
    child_rooms: list[dict],
    curr_sub: str,
    is_here_place: bool,
    is_same_z: bool,
    scen_key: str,
    classify_fn,
) -> None:
    """Pins Tier 3 quest/bounty markers onto sub_location_details and computes direct vs. sub quest metadata."""
    p_nm = p_item.get("name", "")
    is_unpurchased = bool(p_item.get("is_unpurchased_realty"))
    sub_details = list(p_item.get("sub_location_details") or []) if not is_unpurchased else []

    if not is_unpurchased and not sub_details and p_item.get("sub_locations"):
        p_mins = int(p_item.get("travel_minutes") or (4 if is_same_z else 15))
        for s_name in (p_item.get("sub_locations") or []):
            s_str = str(s_name or "").strip()
            if not s_str:
                continue
            cr_here = bool(is_here_place and curr_sub and curr_sub.strip().lower() == s_str.lower())
            cr_mins = 0 if cr_here else (1 if is_here_place else max(1, p_mins + 1))
            sub_details.append({
                "node_id": "",
                "name": s_str,
                "is_current_room": cr_here,
                "travel_minutes": cr_mins,
                "travel_tag": format_travel_eta_tag(cr_mins, is_same_zone=is_same_z, scen_key=scen_key, is_here=cr_here),
                "props": [],
                "access_tier": "open",
                "access_badge": "Open",
                "is_unlocked": False,
                "scene_residue": "",
                "known_npcs_here": [],
                "unmet_activity_count": 0,
                "is_transit_hub": False,
                "is_faction_hq": False,
                "is_minor_club_hq": False,
                "has_bounty_board": False,
                "has_merchant_shop": False,
                "is_discreet": False,
                "badges": [],
                "anomalous_site_meta": None,
            })

    all_markers = list(p_item.get("quest_markers") or [])
    pnid = str(p_item.get("node_id") or "").strip()
    if pnid:
        for wpe in entries_by_node_id.get(pnid, ()):
            mk = wpe.get("marker") or ""
            if mk and mk not in all_markers:
                all_markers.append(mk)
    for cr in (child_rooms or []):
        cr_id = str(cr.get("node_id") or "").strip()
        if not cr_id:
            continue
        for wpe in entries_by_node_id.get(cr_id, ()):
            mk = wpe.get("marker") or ""
            if mk and mk not in all_markers:
                all_markers.append(mk)

    p_item["quest_markers"] = all_markers
    building_node_ids = {
        nid for nid in (
            [pnid]
            + [str(sd.get("node_id") or "").strip() for sd in sub_details]
            + [str(cr.get("node_id") or "").strip() for cr in (child_rooms or [])]
        )
        if nid
    }
    room_names_low = {
        str(sd.get("name") or "").strip().lower()
        for sd in sub_details
        if str(sd.get("name") or "").strip()
    }
    z_low = str(z_nm or "").strip().lower()

    filtered_markers: list[str] = []
    for qm in all_markers:
        qm_entries = entries_by_marker.get(qm) or []
        if not qm_entries:
            filtered_markers.append(qm)
            continue
        keep = False
        for e in qm_entries:
            e_nid = str(e.get("target_node_id") or "").strip()
            if e_nid and e_nid in building_node_ids:
                keep = True
                break
            if _entry_matches_building(e, z_nm, p_nm):
                keep = True
                break
            if not e.get("sub_hint"):
                eh_p = str(e.get("primary_hint") or "").strip().lower()
                eh_z = str(e.get("zone_hint") or "").strip().lower()
                z_ok = (not eh_z) or (eh_z == z_low) or (len(eh_z) >= 4 and (eh_z in z_low or z_low in eh_z))
                if z_ok and eh_p and eh_p in room_names_low:
                    keep = True
                    break
        if keep and qm not in filtered_markers:
            filtered_markers.append(qm)

    all_markers = filtered_markers
    p_item["quest_markers"] = all_markers
    all_tags, all_primary_tag, _ = _summarize_quest_markers(all_markers, classify_fn)
    p_item["quest_tag"] = all_primary_tag

    room_markers: dict[int, list[str]] = {idx: [] for idx in range(len(sub_details))}
    direct_markers: list[str] = []

    for qm in all_markers:
        matched_indices = (
            _match_marker_to_sub_rooms(qm, entries_by_marker.get(qm, ()), sub_details, z_nm, p_nm)
            if not is_unpurchased and sub_details
            else []
        )
        if matched_indices:
            for idx in matched_indices:
                if qm not in room_markers[idx]:
                    room_markers[idx].append(qm)
        else:
            if qm not in direct_markers:
                direct_markers.append(qm)

    sub_tags_acc: set[str] = set()
    for idx, sd in enumerate(sub_details):
        r_mks = room_markers.get(idx, [])
        r_tags, r_primary, r_kind = _summarize_quest_markers(r_mks, classify_fn)
        sd["value"] = f"{z_nm} ➔ {p_nm} ➔ {sd['name']}"
        sd["quest_markers"] = list(r_mks)
        sd["quest_tags"] = r_tags
        sd["quest_tag"] = r_primary
        sd["quest_kind"] = r_kind
        sub_tags_acc.update(r_tags)

    if not is_unpurchased and sub_details:
        sub_details.sort(key=lambda sd: (0 if sd.get("is_current_room") else 1, 0 if sd.get("quest_markers") else 1))
        p_item["sub_location_details"] = sub_details

    d_tags, d_primary, _ = _summarize_quest_markers(direct_markers, classify_fn)
    p_item["direct_quest_markers"] = list(direct_markers)
    p_item["direct_quest_tag"] = d_primary
    p_item["direct_quest_tags"] = d_tags
    p_item["sub_quest_count"] = sum(len(sd.get("quest_markers") or []) for sd in sub_details)
    p_item["sub_quest_tags"] = [t for t in _QUEST_TAG_PRIORITY if t in sub_tags_acc]


def get_zone_summary_tree(session_id: int, scen_key: str = "fantasy", current_loc: str = "", char_name: str = "") -> list[dict]:

    """

    Returns an aggregated list of discovered Zones with their metadata, primary locations,

    atmosphere, tags, and waypoint markers. Used by the interactive World Map UI.

    """

    ensure_session_locations_seeded(session_id, scen_key, char_name=char_name)

    tree = get_discovered_location_tree(session_id, scen_key)

    from mechanics.world.waypoints import get_location_waypoint_markers, get_location_waypoint_entries
    from mechanics.world.waypoints.core import _classify_waypoint_marker
    from mechanics.world.mobility import calculate_route_travel_time

    waypoint_markers = get_location_waypoint_markers(session_id)

    sess_row = db.get_session(session_id) if session_id else None
    eff_curr_loc = current_loc or (sess_row.get("current_location") if sess_row else "") or ""

    curr_z, curr_p, curr_sub = (
        parse_tiered_location(eff_curr_loc, scen_key, session_id=session_id, char_name=char_name)
        if eff_curr_loc else ("", "", "")
    )



    # Fetch atmosphere for each zone, preferring authoritative ZONE world_nodes before session_locations

    rows = db.get_session_locations(session_id)

    zone_atm_map: dict[str, str] = {}

    try:
        for zn in (db.get_session_world_nodes(session_id) or []):
            if zn.get("node_type") == "ZONE" and zn.get("name") and zn.get("atmosphere"):
                zone_atm_map[zn["name"]] = zn["atmosphere"]
    except Exception:
        pass

    for r in rows:

        z = r.get("zone_name")

        atm = r.get("atmosphere")

        if z and atm:
            existing_atm = zone_atm_map.get(z, "")
            if not existing_atm or (
                existing_atm.startswith("The dedicated headquarters of ")
                and str(atm).strip().startswith("{")
            ):
                zone_atm_map[z] = atm



    summary_list = []

    for zone_name in sorted(tree.keys()):

        primaries_dict = tree[zone_name]

        primary_items = []

        zone_tags_set = set()



        for primary_name in sorted(primaries_dict.keys()):

            val_str = f"{zone_name} ➔ {primary_name}"

            emoji = get_location_emoji(primary_name, zone_name=zone_name, waypoint_markers=waypoint_markers, session_id=session_id, scen_key=scen_key, char_name=char_name)

            

            # Check waypoint tags
            wp_tags = waypoint_markers.get(val_str)
            if not wp_tags:
                val_low = val_str.lower()
                for mk_k, mk_v in waypoint_markers.items():
                    if mk_k.lower() == val_low:
                        wp_tags = mk_v
                        break
            if not wp_tags:
                wp_tags = waypoint_markers.get(primary_name) or []
            if not wp_tags:
                sub_tag_acc = []
                for sub_loc_nm in primaries_dict.get(primary_name, []):
                    for cand_k in (f"{zone_name} ➔ {primary_name} ➔ {sub_loc_nm}", f"{zone_name} ➔ {sub_loc_nm}", sub_loc_nm):
                        for t_item in (waypoint_markers.get(cand_k) or []):
                            if t_item not in sub_tag_acc:
                                sub_tag_acc.append(t_item)
                wp_tags = sub_tag_acc

            desc_parts = []
            if wp_tags:
                for t in wp_tags:
                    clean_t = t.split("]", 1)[-1].strip() if "]" in t else t
                    if clean_t and clean_t not in desc_parts:
                        desc_parts.append(clean_t)

            loc_badges = []
            if wp_tags:
                if any("⚡" in t or "[Story Climax]" in t for t in wp_tags):
                    loc_badges.append("⚡")
                    zone_tags_set.add("⚡ Story Climax")
                if any("⭐" in t or "[Story]" in t for t in wp_tags):
                    loc_badges.append("⭐")
                    zone_tags_set.add("⭐ Story Quest")
                if any("🎯" in t or "[Bounty]" in t for t in wp_tags):
                    loc_badges.append("🎯")
                    zone_tags_set.add("🎯 Bounty Target")
                if any("💌" in t or "[Meetup]" in t for t in wp_tags):
                    loc_badges.append("💌")
                    zone_tags_set.add("💌 Meetup")

            if location_has_bounty_board(primary_name, scen_key=scen_key):
                nb_label, nb_emoji = get_notice_board_label(scen_key)
                loc_badges.append(nb_emoji)

            if location_has_merchant_shop(primary_name, scen_key=scen_key):
                loc_badges.append("🛍️")

            if location_has_faction_hq(primary_name, session_id=session_id):
                loc_badges.append("🏛️")
                zone_tags_set.add("🏛️ Faction HQ")

            try:
                p_house = get_session_player_house_name(session_id, char_name=char_name, scenario_key=scen_key)
                if primary_name == p_house:
                    loc_badges.append("🏠")
                    zone_tags_set.add("🏠 Home")
            except Exception:
                pass

            arch_label, arch_emoji = get_location_archetype(primary_name, zone_name=zone_name, scen_key=scen_key)
            final_emoji = "🏠" if emoji == "🏠" else (arch_emoji or emoji)
            badge_str = " ".join(loc_badges)

            primary_items.append({
                "name": primary_name,
                "emoji": final_emoji,
                "archetype": arch_label,
                "archetype_emoji": arch_emoji,
                "badges": badge_str,
                "quest_tag": "⚡ Story Climax" if "⚡" in loc_badges else ("⭐ Story Quest" if "⭐" in loc_badges else ("🎯 Bounty Target" if "🎯" in loc_badges else ("💌 Meetup" if "💌" in loc_badges else ""))),
                "quest_markers": list(wp_tags),
                "value": val_str,
                "description": badge_str,
                "sub_locations": primaries_dict[primary_name]
            })

        # Safe Hub / Frontier / Environmental Hazard tags only apply to wilderness/expedition genres.
        # Grounded modern, slice-of-life, high school, and anomalous incursion scenarios omit them.
        from scenario_data import is_mechanic_enabled, is_anomalous_incursions_scenario
        scen_low = str(scen_key or "").lower()
        is_modern_grounded_scen = (
            is_school_scenario(scen_key)
            or is_anomalous_incursions_scenario(scen_key)
            or any(k in scen_low for k in ("slice_of_life", "modern", "urban", "romance", "drama"))
        )
        combat_enabled = is_mechanic_enabled(scen_key, "tactical_combat")
        is_quest_only_hostility = is_anomalous_incursions_scenario(scen_key)
        show_danger_zone_tags = combat_enabled and not is_quest_only_hostility and not is_modern_grounded_scen

        # Check hazard and frontier tags based on zone name / theme (only in wilderness/expedition genres)
        z_lower = zone_name.lower()
        if not is_modern_grounded_scen:
            if not is_quest_only_hostility and any(
                re.search(rf"\b{re.escape(k)}\b", z_lower)
                for k in (
                    "frontier", "chasm", "crag", "crags", "badlands", "waste", "wasteland", "cursed", "dungeon", "crater", "ruins",
                    "swamp", "marsh", "planet", "asteroid", "tundra", "ashland", "moors", "catacombs",
                    "caldera", "lava", "magma", "cinder", "pyre", "volcanic", "volcano", "abyss", "fissure", "trench", "rift", "crypt",
                    "vault", "labyrinth", "mire", "bog", "fen", "permafrost", "dreadfall", "shadowveil", "void"
                )
            ):
                if not is_hub_location(zone_name):
                    zone_tags_set.add("🧭 Frontier")

            if any(re.search(rf"\b{re.escape(k)}\b", z_lower) for k in ("volcanic", "ashland", "caldera", "foundry", "desert", "dunes", "sands", "magma", "lava", "cinder", "infernal", "pyre", "sunscorched")):
                zone_tags_set.add("🌋 Extreme Heat")
            elif any(re.search(rf"\b{re.escape(k)}\b", z_lower) for k in ("ice", "tundra", "frost", "snow", "glacial", "cryo", "everwinter", "permafrost", "blizzard", "rimewind")):
                zone_tags_set.add("❄️ Freezing Tundra")
            elif any(re.search(rf"\b{re.escape(k)}\b", z_lower) for k in ("irradiated", "toxic", "radiation", "fallout")):
                zone_tags_set.add("☢️ Radiation Hazard")
            elif any(re.search(rf"\b{re.escape(k)}\b", z_lower) for k in ("seaside", "coastal", "beach", "harbor", "ocean", "bay", "port", "quay", "pier", "tidehaven")):
                zone_tags_set.add("🌊 Coastal")
            elif any(re.search(rf"\b{re.escape(k)}\b", z_lower) for k in ("airship", "zeppelin", "leviathan", "sovereign", "ironclad", "kraken", "dreadnought", "titan", "swallow", "hms", "zephyr", "aether", "celestial", "gargantuan")):
                zone_tags_set.add("🎈 Airship")

        if is_hub_location(zone_name) and show_danger_zone_tags:
            zone_tags_set.add("🛡️ Safe Hub")

        is_curr = bool(curr_z and zone_name.strip().lower() == curr_z.strip().lower())
        atm_raw = zone_atm_map.get(zone_name, "")
        env_data = parse_zone_environment_data(atm_raw)
        theme_tagline = env_data.get("theme") or (env_data.get("sensory") if not env_data.get("features") else "")
        if not theme_tagline:
            theme_tagline = infer_zone_theme_fallback(zone_name, scen_key)

        zone_quest_markers = []
        for p_item in primary_items:
            for qm in (p_item.get("quest_markers") or []):
                zone_quest_markers.append({
                    "place_name": p_item["name"],
                    "value": p_item["value"],
                    "marker": qm,
                    "quest_tag": p_item.get("quest_tag", ""),
                })

        summary_list.append({
            "zone_name": zone_name,
            "emoji": get_zone_emoji(zone_name, scen_key),
            "theme": theme_tagline,
            "atmosphere": env_data.get("sensory") or atm_raw,
            "is_current": is_curr,
            "is_hub": is_hub_location(zone_name) if show_danger_zone_tags else False,
            "places_count": len(primary_items),
            "primary_locations": primary_items,
            "active_tags": sorted(list(zone_tags_set)),
            "quest_markers": zone_quest_markers,
            "quest_count": len(zone_quest_markers),
        })

    if session_id:
        try:
            from mechanics.world.schedules import get_npc_scheduled_node_id
            from mechanics.world.locations.access_gate import get_node_effective_access_info

            curr_day, curr_min, _ = db.get_session_time(session_id)
            contacts = db.get_contacts(session_id) or []
            roster = db.get_school_roster(session_id) if hasattr(db, "get_school_roster") else []
            all_nodes = db.get_session_world_nodes(session_id) or []
            _is_anom_atlas = (
                scenario_data.is_anomalous_incursions_scenario(scen_key)
                or scenario_data.is_anomalous_high_school_scenario(scen_key)
            )
            _anom_res_stat = None
            if _is_anom_atlas:
                try:
                    from mechanics.world.anomalous_sites.domain_rules import get_resonator_charges_status
                    _anom_res_stat = get_resonator_charges_status(
                        session_id, world_nodes=all_nodes, current_day=curr_day, session=sess_row
                    )
                except Exception:
                    _anom_res_stat = None

            occ_by_node: dict[str, dict] = {}
            def _get_occ(nid: str):
                if nid not in occ_by_node:
                    occ_by_node[nid] = {"known_npcs": [], "unmet_count": 0}
                return occ_by_node[nid]

            def _record_npc_occ(raw_nid: str, npc_name: str, status: str) -> None:
                n_obj = next((n for n in all_nodes if n["node_id"] == raw_nid), None)
                is_room = bool(n_obj and n_obj.get("node_type") == "ROOM")
                fac_id = n_obj.get("parent_id") if is_room else raw_nid
                target_ids = [raw_nid, fac_id] if (is_room and fac_id) else ([fac_id] if fac_id else [raw_nid])
                for oid in target_ids:
                    if not oid:
                        continue
                    occ = _get_occ(oid)
                    if not any(kn["name"].lower() == npc_name.lower() for kn in occ["known_npcs"]):
                        occ["known_npcs"].append({"name": npc_name, "status": status})

            appts = []
            if hasattr(db, "get_phone_appointments"):
                appts = (db.get_phone_appointments(session_id, status="pending") or []) + (db.get_phone_appointments(session_id, status="arrived") or [])
            for appt in appts:
                tgt = appt.get("target_node_id")
                if not tgt and appt.get("rendezvous_location"):
                    tgt = db.resolve_node_id_from_location(session_id, appt["rendezvous_location"], prefer_facility=False)
                if tgt:
                    an = appt.get("npc_name", "")
                    if an:
                        _record_npc_occ(tgt, an, "Rendezvous")

            c_names_lower = set()
            for c in contacts:
                cn = (c.get("name") or "").strip()
                if not cn: continue
                c_names_lower.add(cn.lower())
                snid = get_npc_scheduled_node_id(c, current_minute=curr_min, scen_key=scen_key, current_day=curr_day)
                if snid:
                    _record_npc_occ(snid, cn, "Routine")

            for r in roster:
                rn = (r.get("name") or "").strip()
                if not rn or rn.lower() in c_names_lower: continue
                snid = get_npc_scheduled_node_id(r, current_minute=curr_min, scen_key=scen_key, current_day=curr_day)
                if snid:
                    sn = next((n for n in all_nodes if n["node_id"] == snid), None)
                    is_room_r = bool(sn and sn.get("node_type") == "ROOM")
                    fac_id = sn.get("parent_id") if is_room_r else snid
                    for oid in ([snid, fac_id] if (is_room_r and fac_id) else ([fac_id] if fac_id else [])):
                        if oid:
                            _get_occ(oid)["unmet_count"] += 1

            # Single-source Dijkstra from current node across world_edges + room/facility links
            import heapq
            from collections import defaultdict
            all_edges = db.get_session_world_edges(session_id) or []
            curr_node_id = None
            if current_loc:
                curr_node_id = db.resolve_node_id_from_location(session_id, eff_curr_loc)
            if not curr_node_id and sess_row:
                curr_node_id = sess_row.get("current_node_id")
            if not curr_node_id and eff_curr_loc:
                curr_node_id = db.resolve_node_id_from_location(session_id, eff_curr_loc)

            node_by_id = {n["node_id"]: n for n in all_nodes}
            if curr_node_id and curr_node_id not in node_by_id and hasattr(db.world, "_LEGACY_NODE_ID_ALIASES"):
                curr_node_id = db.world._LEGACY_NODE_ID_ALIASES.get(curr_node_id, curr_node_id)

            dist_map: dict[str, int] = {}
            if curr_node_id and all_nodes:
                adj = defaultdict(list)
                for e in all_edges:
                    u, v = e.get("from_node_id"), e.get("to_node_id")
                    w = max(1, int(e.get("travel_minutes") or 2))
                    if u and v:
                        adj[u].append((v, w))
                        if e.get("is_bidirectional", 1):
                            adj[v].append((u, w))
                mega_ids = {
                    "loc_agency_hq", "loc_private_hq_1", "loc_private_hq_2",
                    "loc_general_hospital", "loc_theme_park", "loc_eastern_temple",
                    "loc_botanical_zoo", "loc_cult_sanctum_hq", "loc_clandestine_syndicate_hq",
                }
                for n in all_nodes:
                    pid, nid = n.get("parent_id"), n.get("node_id")
                    if pid and nid and ((n.get("node_type") == "ROOM" and pid not in mega_ids) or pid == curr_node_id):
                        adj[pid].append((nid, 1))
                        adj[nid].append((pid, 1))
                dist_map[curr_node_id] = 0
                pq = [(0, curr_node_id)]
                while pq:
                    d_u, u_id = heapq.heappop(pq)
                    if d_u > dist_map.get(u_id, 10**9):
                        continue
                    for v_id, w_uv in adj.get(u_id, []):
                        nd = d_u + w_uv
                        if nd < dist_map.get(v_id, 10**9):
                            dist_map[v_id] = nd
                            heapq.heappush(pq, (nd, v_id))

            curr_node_obj = node_by_id.get(curr_node_id) if curr_node_id else None
            curr_fac_id = (
                curr_node_obj.get("parent_id")
                if (curr_node_obj and curr_node_obj.get("node_type") == "ROOM")
                else curr_node_id
            )

            from .seeding import has_player_nsfw_salon_membership_or_standing, reveal_hidden_club_facility
            has_nsfw_club_access = has_player_nsfw_salon_membership_or_standing(
                session_id,
                session=sess_row if isinstance(sess_row, dict) else None,
                for_atlas_visibility=True,
            )

            wp_entries = get_location_waypoint_entries(session_id)
            entries_by_marker: dict[str, list[dict]] = {}
            entries_by_node_id: dict[str, list[dict]] = {}
            for wpe in wp_entries:
                m_key = wpe.get("marker") or ""
                if m_key:
                    entries_by_marker.setdefault(m_key, []).append(wpe)
                n_key = wpe.get("target_node_id") or ""
                if n_key:
                    entries_by_node_id.setdefault(n_key, []).append(wpe)

            for z_item in summary_list:
                z_nm = z_item["zone_name"]
                is_same_z = bool(z_item.get("is_current"))
                zone_min_candidates = []
                visible_primaries = []
                for p_item in z_item.get("primary_locations", []):
                    p_nm = p_item["name"]
                    val_str = f"{z_nm} ➔ {p_nm}"
                    pnid = db.resolve_node_id_from_location(session_id, val_str, prefer_facility=True)
                    is_here_place = bool(
                        (pnid and pnid == curr_fac_id)
                        or (is_same_z and curr_p and curr_p.strip().lower() == p_nm.strip().lower())
                    )
                    p_item["is_current_place"] = is_here_place
                    child_rooms = [n for n in all_nodes if n.get("node_type") == "ROOM" and n.get("parent_id") == pnid] if pnid else []

                    if is_here_place:
                        p_mins = 0
                    elif pnid and pnid in dist_map:
                        p_mins = max(1, dist_map[pnid])
                    elif child_rooms and any(cr["node_id"] in dist_map for cr in child_rooms):
                        p_mins = max(1, min(dist_map[cr["node_id"]] for cr in child_rooms if cr["node_id"] in dist_map))
                    elif eff_curr_loc:
                        p_mins = calculate_route_travel_time(eff_curr_loc, val_str, scen_key=scen_key, session_id=0)
                    else:
                        p_mins = 4 if is_same_z else 15

                    p_item["travel_minutes"] = p_mins
                    p_item["travel_tag"] = format_travel_eta_tag(p_mins, is_same_zone=is_same_z, scen_key=scen_key, is_here=is_here_place)
                    if not is_here_place:
                        zone_min_candidates.append(p_mins)

                    if pnid:
                        acc = get_node_effective_access_info(session_id, pnid, current_day=curr_day, current_minute=curr_min, scen_key=scen_key)
                        p_occ = occ_by_node.get(pnid, {"known_npcs": [], "unmet_count": 0})
                        p_item["node_id"] = pnid
                        p_item["access_tier"] = acc.get("access_tier", "open")
                        p_item["access_badge"] = acc.get("status_badge", "Open")
                        p_item["is_curfew_active"] = acc.get("curfew_active", False)
                        p_item["schedule_locked"] = acc.get("schedule_locked", False)
                        p_item["is_trespassing"] = acc.get("is_trespassing", False)
                        p_item["is_unlocked"] = acc.get("is_unlocked", False)
                        p_item["scene_residue"] = acc.get("scene_residue") or p_item.get("scene_residue") or ""
                        p_item["known_npcs_here"] = p_occ["known_npcs"][:3]
                        p_item["unmet_activity_count"] = p_occ["unmet_count"]
                        if _is_anom_atlas:
                            try:
                                from mechanics.world.anomalous_sites.catalog import resolve_anomalous_site
                                from mechanics.world.anomalous_sites.domain_rules import build_site_map_meta
                                _p_anom_spec = resolve_anomalous_site(node_id=pnid, location_str=val_str, session_nodes=all_nodes)
                                if _p_anom_spec and _p_anom_spec.get("site_type") != "embedded_wing":
                                    p_item["anomalous_site_meta"] = build_site_map_meta(
                                        session_id,
                                        _p_anom_spec,
                                        current_minute=curr_min,
                                        current_day=curr_day,
                                        scen_key=scen_key,
                                        world_nodes=all_nodes,
                                        resonator_status=_anom_res_stat,
                                    )
                            except Exception:
                                pass

                        from .residences import is_unpurchased_realty_node
                        unbought_realty = is_unpurchased_realty_node(session_id, pnid, session=sess_row)
                        if unbought_realty:
                            p_item["is_unpurchased_realty"] = True
                            p_item["realty_price"] = int(unbought_realty.get("price") or 0)
                            p_item["realty_property_id"] = str(unbought_realty.get("property_id") or "")
                            p_item["sub_location_details"] = []
                            p_item["sub_locations"] = []
                            child_rooms = []

                        sub_details = []
                        for cr in child_rooms:
                            cr_id = cr["node_id"]
                            cr_name = cr.get("name", "")
                            cr_is_here = bool(
                                cr_id == curr_node_id
                                or (is_here_place and curr_sub and curr_sub.strip().lower() == cr_name.strip().lower())
                            )
                            if cr_is_here:
                                cr_mins = 0
                            elif cr_id in dist_map:
                                cr_mins = max(1, dist_map[cr_id])
                            elif is_here_place:
                                cr_mins = 3 if pnid in {
                                    "loc_agency_hq", "loc_private_hq_1", "loc_private_hq_2",
                                    "loc_general_hospital", "loc_theme_park", "loc_eastern_temple",
                                    "loc_botanical_zoo", "loc_cult_sanctum_hq", "loc_clandestine_syndicate_hq",
                                } else 1
                            else:
                                cr_mins = max(1, p_mins + 1)

                            cr_acc = get_node_effective_access_info(session_id, cr_id, current_day=curr_day, current_minute=curr_min, scen_key=scen_key)
                            cr_occ = occ_by_node.get(cr_id, {"known_npcs": [], "unmet_count": 0})
                            if not p_item.get("scene_residue") and cr_acc.get("scene_residue"):
                                p_item["scene_residue"] = cr_acc.get("scene_residue")
                            cr_meta: dict[str, Any] = {}
                            if cr.get("state_json"):
                                try:
                                    raw_cr_st = cr["state_json"]
                                    cr_meta = json.loads(raw_cr_st) if isinstance(raw_cr_st, str) else dict(raw_cr_st)
                                except Exception:
                                    cr_meta = {}
                            cr_is_transit = bool(cr.get("is_transit_hub") or cr_meta.get("is_transit_hub"))
                            cr_is_faction_hq = bool(
                                cr_meta.get("is_faction_hq")
                                or location_has_faction_hq(cr_name, session_id=session_id)
                            )
                            cr_is_minor_hq = bool(cr_meta.get("is_minor_club_hq"))
                            cr_has_board = bool(
                                cr_meta.get("has_bounty_board")
                                or cr_is_minor_hq
                                or location_has_bounty_board(cr_name, scen_key=scen_key)
                            )
                            cr_has_shop = bool(
                                cr_meta.get("has_merchant_shop")
                                or cr_is_minor_hq
                                or location_has_merchant_shop(cr_name, scen_key=scen_key)
                            )
                            cr_is_discreet = bool(
                                cr_meta.get("is_discreet")
                                or cr_meta.get("is_private_intimate")
                                or cr.get("privacy_level") == "private"
                            )
                            cr_badges: list[str] = []
                            if cr_is_faction_hq:
                                cr_badges.append("🏛️")
                            if cr_has_board:
                                _, cr_nb_emoji = get_notice_board_label(scen_key)
                                cr_badges.append(cr_nb_emoji)
                            if cr_has_shop:
                                cr_badges.append("🛍️")
                            if cr_is_transit:
                                cr_badges.append("🚀")
                            if cr_is_discreet:
                                cr_badges.append("🤫")
                            cr_sub_meta = None
                            if _is_anom_atlas:
                                try:
                                    from mechanics.world.anomalous_sites.catalog import resolve_anomalous_site
                                    from mechanics.world.anomalous_sites.domain_rules import build_site_map_meta
                                    _cr_spec = resolve_anomalous_site(node_id=cr_id, location_str=cr_name, session_nodes=all_nodes)
                                    if _cr_spec and _cr_spec.get("site_type") == "embedded_wing":
                                        cr_sub_meta = build_site_map_meta(
                                            session_id,
                                            _cr_spec,
                                            current_minute=curr_min,
                                            current_day=curr_day,
                                            scen_key=scen_key,
                                            world_nodes=all_nodes,
                                            resonator_status=_anom_res_stat,
                                        )
                                except Exception:
                                    cr_sub_meta = None
                            sub_details.append({
                                "node_id": cr_id,
                                "name": cr_name,
                                "is_current_room": cr_is_here,
                                "travel_minutes": cr_mins,
                                "travel_tag": format_travel_eta_tag(cr_mins, is_same_zone=is_same_z, scen_key=scen_key, is_here=cr_is_here),
                                "props": get_node_props(session_id, cr_id, scenario_key=scen_key),
                                "access_tier": cr_acc.get("access_tier", "open"),
                                "access_badge": cr_acc.get("status_badge", "Open"),
                                "is_unlocked": cr_acc.get("is_unlocked", False),
                                "scene_residue": cr_acc.get("scene_residue") or "",
                                "known_npcs_here": cr_occ["known_npcs"][:3],
                                "unmet_activity_count": cr_occ["unmet_count"],
                                "is_transit_hub": cr_is_transit,
                                "is_faction_hq": cr_is_faction_hq,
                                "is_minor_club_hq": cr_is_minor_hq,
                                "has_bounty_board": cr_has_board,
                                "has_merchant_shop": cr_has_shop,
                                "is_discreet": cr_is_discreet,
                                "badges": cr_badges,
                                "anomalous_site_meta": cr_sub_meta,
                            })
                        p_item["sub_location_details"] = sub_details

                    _assign_tier3_markers_for_place(
                        p_item,
                        z_nm,
                        entries_by_marker,
                        entries_by_node_id,
                        child_rooms,
                        curr_sub,
                        is_here_place,
                        is_same_z,
                        scen_key,
                        _classify_waypoint_marker,
                    )

                    p_node_obj = node_by_id.get(pnid) if pnid else None
                    p_state_meta = {}
                    if p_node_obj and p_node_obj.get("state_json"):
                        try:
                            raw_st = p_node_obj["state_json"]
                            p_state_meta = json.loads(raw_st) if isinstance(raw_st, str) else dict(raw_st)
                        except Exception:
                            p_state_meta = {}
                    if p_state_meta.get("is_hidden") and not p_state_meta.get("discovered"):
                        is_club_revealed = bool(
                            is_here_place
                            or p_item.get("quest_markers")
                            or (pnid and (pnid == "loc_nsfw_club_facility" or p_state_meta.get("nsfw_only")) and (has_nsfw_club_access or p_item.get("is_unlocked")))
                        )
                        if not is_club_revealed:
                            continue
                        if pnid and session_id:
                            try:
                                reveal_hidden_club_facility(session_id, pnid)
                            except Exception:
                                pass
                    visible_primaries.append(p_item)
                if len(visible_primaries) != len(z_item.get("primary_locations", [])):
                    z_item["primary_locations"] = visible_primaries
                    z_item["places_count"] = len(visible_primaries)

                rebuilt_z_markers: list[dict] = []
                z_tag_merge = {t for t in (z_item.get("active_tags") or []) if t not in _QUEST_TAG_PRIORITY}
                for p_vis in z_item.get("primary_locations", []):
                    for sd in (p_vis.get("sub_location_details") or []):
                        for qm in (sd.get("quest_markers") or []):
                            rebuilt_z_markers.append({
                                "place_name": p_vis["name"],
                                "sub_name": sd["name"],
                                "value": sd.get("value") or f"{z_nm} ➔ {p_vis['name']} ➔ {sd['name']}",
                                "marker": qm,
                                "quest_tag": sd.get("quest_tag") or p_vis.get("quest_tag", ""),
                            })
                    for qm in (p_vis.get("direct_quest_markers") or []):
                        rebuilt_z_markers.append({
                            "place_name": p_vis["name"],
                            "sub_name": "",
                            "value": p_vis.get("value") or f"{z_nm} ➔ {p_vis['name']}",
                            "marker": qm,
                            "quest_tag": p_vis.get("direct_quest_tag") or p_vis.get("quest_tag", ""),
                        })
                    z_tag_merge.update(p_vis.get("sub_quest_tags") or [])
                    z_tag_merge.update(p_vis.get("direct_quest_tags") or [])
                z_item["quest_markers"] = rebuilt_z_markers
                z_item["quest_count"] = len(rebuilt_z_markers)
                z_item["active_tags"] = sorted(z_tag_merge)

                if is_same_z:
                    z_item["travel_minutes"] = 0
                    z_item["travel_tag"] = "Here"
                else:
                    z_mins = min(zone_min_candidates) if zone_min_candidates else (
                        calculate_route_travel_time(eff_curr_loc, z_nm, scen_key=scen_key, session_id=0) if eff_curr_loc else 15
                    )
                    z_item["travel_minutes"] = z_mins
                    z_item["travel_tag"] = format_travel_eta_tag(z_mins, is_same_zone=False, scen_key=scen_key, is_here=False)
        except Exception:
            pass

    for z_item in summary_list:
        is_same_z = bool(z_item.get("is_current"))
        if "travel_tag" not in z_item:
            z_mins = 0 if is_same_z else (calculate_route_travel_time(eff_curr_loc, z_item["zone_name"], scen_key=scen_key, session_id=0) if eff_curr_loc else 15)
            z_item["travel_minutes"] = z_mins
            z_item["travel_tag"] = format_travel_eta_tag(z_mins, is_same_zone=False, scen_key=scen_key, is_here=is_same_z)
        for p_item in z_item.get("primary_locations", []):
            if "travel_tag" not in p_item:
                is_here_p = bool(is_same_z and curr_p and curr_p.strip().lower() == p_item["name"].strip().lower())
                p_mins = 0 if is_here_p else (calculate_route_travel_time(eff_curr_loc, p_item["value"], scen_key=scen_key, session_id=0) if eff_curr_loc else (4 if is_same_z else 15))
                p_item["is_current_place"] = is_here_p
                p_item["travel_minutes"] = p_mins
                p_item["travel_tag"] = format_travel_eta_tag(p_mins, is_same_zone=is_same_z, scen_key=scen_key, is_here=is_here_p)
            p_item.setdefault("direct_quest_markers", list(p_item.get("quest_markers") or []))
            p_item.setdefault("direct_quest_tag", p_item.get("quest_tag", ""))
            p_item.setdefault("direct_quest_tags", _summarize_quest_markers(p_item["direct_quest_markers"], _classify_waypoint_marker)[0])
            p_item.setdefault("sub_quest_count", 0)
            p_item.setdefault("sub_quest_tags", [])

    return summary_list


from .seeding import ensure_session_locations_seeded
from .hierarchy import format_tiered_location_string, infer_zone_theme_fallback, parse_tiered_location, parse_zone_environment_data
from .attributes import (
    get_location_archetype, get_location_emoji, get_notice_board_label,
    get_zone_emoji, is_hub_location, is_location_engine_enabled,
    location_has_bounty_board, location_has_faction_hq, location_has_merchant_shop
)
