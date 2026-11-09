from __future__ import annotations
"""
Daily Anomalous Incursions generation, campus after-hours/school-hours incident rolls,
and active incursion location queries.
"""
import hashlib
import json
import random
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import db
import namegen
import scenario_data
from mechanics.world.anomaly_engine import (
    ANOMALOUS_9_ELEMENTS,
    NON_HOSTILE_TEMPERAMENT_TYPES,
    evaluate_taboo_interaction,
    format_anomaly_dossier_summary,
    generate_anomaly_blueprint,
    instantiate_enemy_from_blueprint,
    parse_blueprint_from_notes,
    serialize_blueprint_note,
)
from mechanics.world.folklore_mechanics import (
    build_dialogue_trap_choices,
    build_offering_counter_rite_choice,
    consume_folklore_offering_item,
    evaluate_dialogue_trap_response,
    evaluate_omen_paradox,
    find_matching_offering_in_inventory,
    get_enemy_tether_state,
    get_public_anomaly_name,
    has_active_dialogue_trap,
    is_blueprint_disguised,
    seal_enemy_tether,
    unmask_blueprint_disguise,
)


INCURSION_SUBTYPES = (
    "hostile_breach",
    "non_hostile_entity",
    "environmental_phenomenon",
)

NON_HOSTILE_SUBDUE_THRESHOLD_PCT = 0.35

# Canonical 4 narrative containment approaches always offered on Non-Hostile Entities
NON_HOSTILE_APPROACH_SPECS: Tuple[Dict[str, str], ...] = (
    {
        "quest_approach": "nh_persuade",
        "incursion_action": "persuade",
        "icon": "🗣️",
        "tag": "Persuade",
        "stat": "CHA",
        "verb_template": "Reason and bargain gently with {entity_name} to enter containment willingly",
        "method_label": "Persuaded & Contained Willingly",
    },
    {
        "quest_approach": "nh_calm",
        "incursion_action": "calm",
        "icon": "🕊️",
        "tag": "Calm",
        "stat": "PER",
        "verb_template": "Read {entity_name}'s distress cues and soothe its anomalous resonance",
        "method_label": "Calmed & Sealed Non-Lethally",
    },
    {
        "quest_approach": "nh_outwit",
        "incursion_action": "outwit",
        "icon": "🧠",
        "tag": "Outwit",
        "stat": "INT",
        "verb_template": "Outsmart {entity_name} and lure it into a pre-calibrated containment snare",
        "method_label": "Outwitted into Containment Snare",
    },
    {
        "quest_approach": "nh_environment",
        "incursion_action": "environment",
        "icon": "🏗️",
        "tag": "Use Environment",
        "stat": "AGI",
        "verb_template": "Use surrounding fixtures and terrain to safely corner and seal {entity_name}",
        "method_label": "Cornered via Environmental Containment",
    },
)

SAPIENCE_APPROACH_SPEC_OVERRIDES: Dict[str, Tuple[Dict[str, str], ...]] = {
    "sapient": NON_HOSTILE_APPROACH_SPECS,
    "compulsive": (
        {
            "quest_approach": "nh_persuade",
            "incursion_action": "persuade",
            "icon": "🗣️",
            "tag": "Persuade",
            "stat": "CHA",
            "verb_template": "Perform the proper threshold courtesy phrase to satisfy {entity_name}'s ritual script",
            "method_label": "Satisfied via Courtesy Script & Contained",
        },
        {
            "quest_approach": "nh_calm",
            "incursion_action": "calm",
            "icon": "🕊️",
            "tag": "Calm",
            "stat": "PER",
            "verb_template": "Time the exact beat of {entity_name}'s repetitive compulsion to slip a seal into its loop",
            "method_label": "Loop-Timed & Sealed Non-Lethally",
        },
        {
            "quest_approach": "nh_outwit",
            "incursion_action": "outwit",
            "icon": "🧠",
            "tag": "Outwit",
            "stat": "INT",
            "verb_template": "Introduce a counting distraction or rule paradox to lock {entity_name} in place",
            "method_label": "Rule-Bound via Counting Snare",
        },
        {
            "quest_approach": "nh_environment",
            "incursion_action": "environment",
            "icon": "🏗️",
            "tag": "Use Environment",
            "stat": "AGI",
            "verb_template": "Step in sync with {entity_name}'s rigid choreography to close the boundary ward",
            "method_label": "Contained via Mirror Choreography",
        },
    ),
    "instinctual": (
        {
            "quest_approach": "nh_persuade",
            "incursion_action": "persuade",
            "icon": "🗣️",
            "tag": "Persuade",
            "stat": "CHA",
            "verb_template": "Project calm dominance and appease {entity_name}'s feral instincts",
            "method_label": "Appeased & Lured into Containment",
        },
        {
            "quest_approach": "nh_calm",
            "incursion_action": "calm",
            "icon": "🕊️",
            "tag": "Calm",
            "stat": "PER",
            "verb_template": "Read {entity_name}'s territorial cues and soothe its anomalous resonance",
            "method_label": "Soothed & Sealed Non-Lethally",
        },
        {
            "quest_approach": "nh_outwit",
            "incursion_action": "outwit",
            "icon": "🧠",
            "tag": "Outwit",
            "stat": "INT",
            "verb_template": "Lay an acoustic-sensory bait trail to lure {entity_name} into a containment snare",
            "method_label": "Baited into Containment Snare",
        },
        {
            "quest_approach": "nh_environment",
            "incursion_action": "environment",
            "icon": "🏗️",
            "tag": "Use Environment",
            "stat": "AGI",
            "verb_template": "Use surrounding terrain and barriers to herd and seal {entity_name}",
            "method_label": "Herded via Environmental Containment",
        },
    ),
    "non_sapient": (
        {
            "quest_approach": "nh_persuade",
            "incursion_action": "persuade",
            "icon": "🗣️",
            "tag": "Persuade",
            "stat": "CHA",
            "verb_template": "Attune your vocal cadence to harmonize with {entity_name}'s ritual waveform",
            "method_label": "Harmonically Attuned & Contained",
        },
        {
            "quest_approach": "nh_calm",
            "incursion_action": "calm",
            "icon": "🕊️",
            "tag": "Calm",
            "stat": "PER",
            "verb_template": "Pinpoint {entity_name}'s phase-shift interval and nullify its emission cycle",
            "method_label": "Phase-Nullified & Sealed",
        },
        {
            "quest_approach": "nh_outwit",
            "incursion_action": "outwit",
            "icon": "🧠",
            "tag": "Outwit",
            "stat": "INT",
            "verb_template": "Decipher {entity_name}'s folklore mechanism and trigger its containment lock",
            "method_label": "Mechanism Deciphered & Locked",
        },
        {
            "quest_approach": "nh_environment",
            "incursion_action": "environment",
            "icon": "🏗️",
            "tag": "Use Environment",
            "stat": "AGI",
            "verb_template": "Deploy grounding anchors and Faraday barriers around {entity_name}",
            "method_label": "Grounded via Environmental Containment",
        },
    ),
}

NON_HOSTILE_ENTITY_TEMPLATES = [
    {
        "title": "Wandering Origami Crane Swarm",
        "category_tag": "cursed_relic",
        "temperament": "timid",
        "description": "Hundreds of luminescent paper cranes folding out of discarded transit tickets, hovering skittishly near an open air shaft—poised to scatter on the wind if startled.",
        "preferred_stat": "CHA",
        "containment_note": "Maintained inside a humidity-controlled glass terrarium; folds into auspicious shapes when classical shamisen music is played.",
    },
    {
        "title": "Echoing Telephone Booth Spirit",
        "category_tag": "spectral_echo",
        "temperament": "volatile",
        "description": "A translucent, weeping commutator spirit repeating a final voicemail; the booth's glass spiderwebs with sharp static arcs whenever sudden footsteps approach.",
        "preferred_stat": "CHA",
        "containment_note": "Anchored to a disconnected rotary handset in Acoustic Cell 14-B; ceases weeping when a recorded reassurance loop is played at dusk.",
    },
    {
        "title": "Mirror-Glass Stray Hound",
        "category_tag": "spatial_warp",
        "temperament": "timid",
        "description": "A docile, crystalline canine entity whining softly with half its body poised inside a storefront reflection, ready to slip out of reality if spooked.",
        "preferred_stat": "PER",
        "containment_note": "Housed in a hexagonal mirrored kennel; feeds harmlessly on ambient fluorescent glare.",
    },
    {
        "title": "Chrono-Stutter Street Musician",
        "category_tag": "cognitohazard",
        "temperament": "volatile",
        "sapience": "compulsive",
        "description": "An acoustic violinist trapped in a 4.7-second temporal loop; its bowstring hums with razor-sharp kinetic tension whenever its melody is rudely interrupted.",
        "preferred_stat": "INT",
        "containment_note": "Stabilized via a metronomic reality anchor; now resides in a soundproofed conservatory suite.",
    },
    {
        "title": "Bioluminescent Moss Spirit",
        "category_tag": "bio_aberration",
        "temperament": "timid",
        "sapience": "instinctual",
        "description": "A shy, floating colony of sentient bioluminescent spores drifting near storm grates, ready to disperse into microscopic mist at the slightest alarm.",
        "preferred_stat": "PER",
        "containment_note": "Cultivated inside Bio-Containment Atrium 3; emits a soothing blue glow that lowers nearby psychic static.",
    },
    {
        "title": "Porcelain Mannequin Sentinel",
        "category_tag": "cursed_relic",
        "temperament": "volatile",
        "sapience": "compulsive",
        "description": "A display mannequin pacing a closed boutique aisle in silent choreography; its ball-jointed limbs snap into territorial defensive stances when crowded.",
        "preferred_stat": "AGI",
        "containment_note": "Secured upright inside Velvet Vault 07 with silk-padded restraints; remains tranquil when dressed in vintage winter coats.",
    },
    {
        "title": "Leaf-Counterfeit Vending Tanuki",
        "category_tag": "cursed_relic",
        "temperament": "mischievous",
        "sapience": "sapient",
        "description": "A plump, grinning illusion-spirit crouched atop a vending machine, swapping spare change into camellia leaves and scrambling button labels for a laugh.",
        "preferred_stat": "INT",
        "containment_note": "Coaxed into a cedar shrine-crate with fried tofu; occasionally slips leaf-origami notes through the air vents.",
    },
    {
        "title": "One-Eyed Alley Karakasa",
        "category_tag": "spectral_echo",
        "temperament": "spook",
        "sapience": "compulsive",
        "description": "An antique oiled-paper umbrella hopping on one wooden sandal behind blind corners solely to startle late-night commuters into gasping.",
        "preferred_stat": "CHA",
        "containment_note": "Racked inside Relic Umbrella Stand 04; folds itself neatly whenever greeted with an unflinching bow.",
    },
]

PHENOMENON_TEMPLATES = [
    {
        "title": "Localized Gravity Inversion Pocket",
        "category_tag": "spatial_warp",
        "description": "Raindrops, loose coins, and street debris are falling upward toward an invisible Escher-like seam twenty feet above the pavement.",
        "preferred_stat": "INT",
        "containment_note": "Residual gravimetric core extracted into a lead-lined gyroscope sphere.",
    },
    {
        "title": "Channel-Zero Static Broadcast Leak",
        "category_tag": "cognitohazard",
        "description": "Every digital billboard and smartphone screen on the block is displaying synchronized fractal snow that induces mild déjà vu.",
        "preferred_stat": "INT",
        "containment_note": "Captured on a magnetically shielded Betamax cassette stored in Memetic Locker 09.",
    },
    {
        "title": "Weeping Bronze Statue Effigy",
        "category_tag": "cursed_relic",
        "description": "A public commemorative statue is secreting warm, metallic liquid while whispering backward coordinates to passersby.",
        "preferred_stat": "PER",
        "containment_note": "Wrapped in consecrated shimenawa rope and stored in the Heavy Relic Vault.",
    },
]


ANOMALOUS_CONSOLIDATED_COMPLEX_IDS = {
    "loc_general_hospital",
    "loc_theme_park",
    "loc_eastern_temple",
    "loc_botanical_zoo",
}

ANOMALOUS_SAFE_HQ_FACILITY_IDS = {
    "loc_agency_hq",
    "loc_private_hq_1",
    "loc_private_hq_2",
    "loc_player_house",
    "loc_hidden_kitsune_village",
    "loc_hidden_bunian_village",
}


def roll_daily_anomalous_incursions(
    session_id: int,
    current_day: int,
    scen_key: str = "anomalous_incursions",
    scenario: Optional[str] = None,
) -> Dict[str, Any]:
    if scenario:
        scen_key = scenario
    """
    Spawns 2-3 optional Daily Anomaly Breaches across random city facilities
    (and Tier-3 wings inside consolidated multi-wing complexes) for `current_day`.
    Unresolved breaches from previous days expire at midnight with 0 penalty.
    Returns `{"incursions": [...], "broadcast_sms": "..."}`.
    """
    if not scenario_data.is_anomalous_incursions_scenario(scen_key):
        return {"incursions": [], "broadcast_sms": ""}

    sess = db.get_session(session_id) or {}
    existing = sess.get("daily_incursions") or sess.get("daily_breaches") or []
    # If already rolled for current_day, return existing
    today_existing = [inc for inc in existing if int(inc.get("day", 0) or 0) == int(current_day)]
    if today_existing:
        return {
            "incursions": today_existing,
            "breaches": today_existing,
            "daily_incursions": today_existing,
            "daily_breaches": today_existing,
            "broadcast_sms": _format_incursion_broadcast_sms(today_existing, current_day),
        }

    rng = random.Random(int(session_id or 1) * 313 + int(current_day or 1) * 79)
    count = rng.choice([2, 3])

    # Gather candidate Tier-2 facilities (and Tier-3 wings inside consolidated complexes)
    candidates: List[Dict[str, str]] = []
    try:
        nodes = db.get_session_world_nodes(session_id) or []
        node_map = {n["node_id"]: n for n in nodes}
        rooms_by_parent: Dict[str, List[Dict[str, Any]]] = {}
        for n in nodes:
            if n.get("node_type") == "ROOM" and n.get("parent_id"):
                rooms_by_parent.setdefault(str(n["parent_id"]), []).append(n)
        for n in nodes:
            if n.get("node_type") == "FACILITY":
                nid = str(n.get("node_id") or "")
                # Skip safe Agency HQs & Player House so incursions happen out in the city
                from mechanics.world.locations.residences import is_excluded_from_random_incursions
                if nid in ANOMALOUS_SAFE_HQ_FACILITY_IDS or (nid.startswith("loc_hq_") and nid != "loc_hq_containment_sector") or is_excluded_from_random_incursions(session_id, node_id=nid, parent_id=str(n.get("parent_id") or "")):
                    continue
                if scenario_data.is_anomalous_high_school_scenario(scen_key) and (
                    str(n.get("parent_id") or "") == "zone_school_campus"
                    or nid.startswith("loc_school_")
                    or nid in ("loc_main_academic", "loc_school_commons", "loc_school_athletics", "loc_school_club_annex", "loc_abandoned_school_wing", "loc_13th_stairwell")
                ):
                    continue
                parent = node_map.get(n.get("parent_id"))
                z_name = parent["name"] if parent else "Metropolitan Grid"
                if nid in ANOMALOUS_CONSOLIDATED_COMPLEX_IDS:
                    for w in rooms_by_parent.get(nid, []):
                        w_id = str(w.get("node_id") or "")
                        if not w_id:
                            continue
                        candidates.append({
                            "node_id": w_id,
                            "facility_name": w["name"],
                            "zone_name": z_name,
                            "full_location": f"{z_name} ➔ {n['name']} ➔ {w['name']}",
                        })
                else:
                    candidates.append({
                        "node_id": nid,
                        "facility_name": n["name"],
                        "zone_name": z_name,
                        "full_location": f"{z_name} ➔ {n['name']}",
                    })
    except Exception:
        pass

    if not candidates:
        from mechanics.world.locations.seeds import get_scenario_seed_data, get_session_urban_zone_name, get_session_urban_facility_name
        from mechanics.world.locations.realty_catalog import ALL_STATIC_RESIDENTIAL_FACILITY_IDS
        from mechanics.world.locations.residences import is_excluded_from_random_incursions
        seed_data = get_scenario_seed_data(scen_key)
        for z in (seed_data.get("zones") or []):
            z_id = z.get("id", "")
            if z_id == "zone_agency_hq" or (scenario_data.is_anomalous_high_school_scenario(scen_key) and z_id == "zone_school_campus"):
                continue
            z_name = get_session_urban_zone_name(session_id, z_id, z.get("name", ""), scen_key)
            for p in (z.get("primary_locations") or []):
                p_id = p.get("id", "")
                if (
                    p_id in ANOMALOUS_SAFE_HQ_FACILITY_IDS
                    or p_id.startswith("loc_hq_")
                    or p_id in ALL_STATIC_RESIDENTIAL_FACILITY_IDS
                    or is_excluded_from_random_incursions(session_id, node_id=p_id)
                ):
                    continue
                p_name = p.get("name", "") if p_id in ALL_STATIC_RESIDENTIAL_FACILITY_IDS else get_session_urban_facility_name(session_id, z_id, p_id, p.get("name", ""), scen_key)
                if p_id in ANOMALOUS_CONSOLIDATED_COMPLEX_IDS:
                    for sub in (p.get("sub_locations") or []):
                        s_id = sub.get("id", "")
                        s_name = sub.get("name", "")
                        if s_id and s_name and not is_excluded_from_random_incursions(session_id, node_id=s_id, parent_id=p_id):
                            candidates.append({
                                "node_id": s_id,
                                "facility_name": s_name,
                                "zone_name": z_name,
                                "full_location": f"{z_name} ➔ {p_name} ➔ {s_name}",
                            })
                else:
                    candidates.append({
                        "node_id": p_id,
                        "facility_name": p_name,
                        "zone_name": z_name,
                        "full_location": f"{z_name} ➔ {p_name}",
                    })

    rng.shuffle(candidates)
    chosen_locs = candidates[:count] if len(candidates) >= count else candidates

    incursions: List[Dict[str, Any]] = []
    cur_min = int(sess.get("current_minute", 480) or 480)
    for idx, loc in enumerate(chosen_locs):
        # Ensure a mix of hostile, non-hostile entity, and phenomenon across the 2-3 spawns
        subtype = INCURSION_SUBTYPES[(idx + int(current_day)) % len(INCURSION_SUBTYPES)]
        inc_id = f"inc_d{current_day}_{idx + 1}_{loc['node_id']}"

        # Cycle anomaly type ("entity", "object", "phenomenon") so all 3 types appear across breaches
        type_cycle = ("entity", "object", "phenomenon")[(idx + int(current_day)) % 3]
        force_disp = "hostile" if subtype == "hostile_breach" else "non_hostile"
        force_tp = "phenomenon" if subtype == "environmental_phenomenon" else type_cycle

        base_tier = max(1, min(5, 1 + (int(current_day or 1) - 1) // 3))
        eff_tier = max(1, min(5, base_tier + (idx - 1)))

        bp = generate_anomaly_blueprint(
            session_id=session_id,
            seed_key=inc_id,
            scenario=scen_key,
            location=loc["full_location"],
            current_minute=cur_min,
            force_type=force_tp,
            force_disposition=force_disp,
            tier=eff_tier,
        )

        temperament = ""
        is_disg_spawn = is_blueprint_disguised(bp, dossier_revealed=False)
        pub_bp_name = get_public_anomaly_name(bp, dossier_revealed=False, fallback=bp["name"])
        disg_cover = str((bp.get("disguise_state") or {}).get("cover_desc") or bp["sensory_omen"])
        if subtype == "hostile_breach":
            cat_tag = bp["category_tag"]
            entity_name = pub_bp_name
            title = f"Hostile Breach: {entity_name}"
            desc = (
                f"Sensors detect an uncanny disturbance ({entity_name}) destabilizing the perimeter at {loc['facility_name']}. {disg_cover}"
                if is_disg_spawn
                else (
                    f"Sensors detect an aggressive {bp['type']} manifestation ({entity_name} — {bp['form_label']}) "
                    f"destabilizing the perimeter at {loc['facility_name']}. {bp['sensory_omen']}"
                )
            )
            preferred_stat = "STR"
            containment_note = bp["containment_note"]
        elif subtype == "non_hostile_entity":
            # Preserve Track B Canonical Folklore blueprints intact; blend templates only into half of Track A procedural rolls
            if idx % 2 == 0 or bp.get("is_canonical_folklore"):
                entity_name = pub_bp_name
                cat_tag = bp["category_tag"]
                temperament = bp["temperament"]
                desc = (
                    f"Uncanny figure reported at {loc['facility_name']}: {disg_cover}"
                    if is_disg_spawn
                    else f"{bp['description']} {bp['sensory_omen']}"
                )
                preferred_stat = bp["preferred_stat"]
                containment_note = bp["containment_note"]
            else:
                tmpl = rng.choice(NON_HOSTILE_ENTITY_TEMPLATES)
                entity_name = tmpl["title"]
                cat_tag = tmpl["category_tag"]
                temperament = tmpl.get("temperament", "timid")
                desc = tmpl["description"]
                preferred_stat = tmpl["preferred_stat"]
                containment_note = tmpl["containment_note"]
                bp["name"] = entity_name
                bp["canonical_name"] = entity_name
                bp.pop("codex_id", None)
                bp["is_canonical_folklore"] = False
                bp["disguise_state"] = None
                # Creature templates are always entities: never leave an "object" type (relic conversion) or object tether
                bp["type"] = "entity"
                bp["tether_state"] = None
                bp["category_tag"] = cat_tag
                bp["temperament"] = temperament
                bp["non_hostile_temperament"] = temperament
                if tmpl.get("sapience"):
                    bp["sapience"] = tmpl["sapience"]
                bp["description"] = desc
                bp["preferred_stat"] = preferred_stat
                bp["containment_note"] = containment_note
            title = f"Non-Hostile Entity: {entity_name}"
        else:
            if idx % 2 == 0 or bp.get("is_canonical_folklore"):
                entity_name = pub_bp_name
                cat_tag = bp["category_tag"]
                desc = (
                    f"Uncanny fixture reported at {loc['facility_name']}: {disg_cover}"
                    if is_disg_spawn
                    else f"{bp['description']} {bp['sensory_omen']}"
                )
                preferred_stat = bp["preferred_stat"]
                containment_note = bp["containment_note"]
            else:
                tmpl = rng.choice(PHENOMENON_TEMPLATES)
                entity_name = tmpl["title"]
                cat_tag = tmpl["category_tag"]
                desc = tmpl["description"]
                preferred_stat = tmpl["preferred_stat"]
                containment_note = tmpl["containment_note"]
                bp["name"] = entity_name
                bp["canonical_name"] = entity_name
                bp.pop("codex_id", None)
                bp["is_canonical_folklore"] = False
                bp["disguise_state"] = None
                bp["type"] = "phenomenon"
                bp["category_tag"] = cat_tag
                bp["description"] = desc
                bp["preferred_stat"] = preferred_stat
                bp["containment_note"] = containment_note
            title = f"Anomalous Phenomenon: {entity_name}"

        incursions.append({
            "incursion_id": inc_id,
            "breach_id": inc_id,
            "day": int(current_day),
            "subtype": subtype,
            "temperament": temperament,
            "strikes": 0,
            "max_strikes": 2,
            "title": title,
            "entity_name": entity_name,
            "category_tag": cat_tag,
            "description": desc,
            "preferred_stat": preferred_stat,
            "containment_note": containment_note,
            "anomaly_type": bp["type"],
            "physicality": bp["physicality"],
            "form": bp["form"],
            "form_label": bp["form_label"],
            "sapience": bp["sapience"],
            "disposition": bp["disposition"],
            "element": bp["element"],
            "resistances": bp["resistances"],
            "weaknesses": bp["weaknesses"],
            "taboo": bp["taboo"],
            "sensory_omen": bp["sensory_omen"],
            "dossier_revealed": False,
            "anomaly_blueprint": bp,
            "node_id": loc["node_id"],
            "zone_name": loc["zone_name"],
            "facility_name": loc["facility_name"],
            "location": loc["full_location"],
            "reward_gold": 60 + (35 * eff_tier) + (idx * 15),
            "reward_xp": 40 + (25 * eff_tier) + (idx * 10),
            "resolved": False,
            "agitated": False,
            "escaped": False,
            "killed_lethally": False,
            "optional": True,
        })

    if scenario_data.is_anomalous_high_school_scenario(scen_key):
        incursions.extend(_spawn_after_hours_campus_incursions(session_id, int(current_day), scen_key, rng))

    db.update_session(session_id, extra={"daily_incursions": incursions, "daily_breaches": None})
    broadcast_sms = _format_incursion_broadcast_sms(incursions, current_day)
    return {"incursions": incursions, "breaches": incursions, "daily_incursions": incursions, "daily_breaches": incursions, "broadcast_sms": broadcast_sms}


generate_daily_anomalous_incursions = roll_daily_anomalous_incursions


def _format_incursion_broadcast_sms(incursions: List[Dict[str, Any]], current_day: int) -> str:
    if not incursions:
        return ""
    lines = [f"📡 [METROPOLITAN ANOMALY ALERT — DAY {current_day}]"]
    lines.append(f"{len(incursions)} optional Anomaly Breach(es) detected across the city today (expire at 24:00 with no penalty):")
    for inc in incursions:
        badge = "⚔️ Hostile" if inc["subtype"] == "hostile_breach" else ("🕊️ Non-Hostile" if inc["subtype"] == "non_hostile_entity" else "🌀 Phenomenon")
        lines.append(f"• [{badge}] {inc['entity_name']} @ {inc['location']}")
    return "\n".join(lines)


def get_active_incursion_at_location(
    session_id: int,
    location_str: str = "",
    node_id: str = "",
    *,
    current_minute: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Returns an unresolved Daily Anomaly Breach matching the given location/node_id, if any."""
    if not session_id:
        return None
    sess = db.get_session(session_id) or {}
    if not scenario_data.is_anomalous_incursions_scenario(sess.get("scenario", "")):
        return None
    incursions = sess.get("daily_incursions") or []
    loc_low = str(location_str or sess.get("current_location") or "").strip().lower()
    nid_low = str(node_id or sess.get("current_node_id") or "").strip().lower()

    for inc in incursions:
        if not isinstance(inc, dict) or inc.get("resolved"):
            continue
        if str(inc.get("time_window") or "") == "after_hours":
            eff_min = current_minute if current_minute is not None else sess.get("current_minute", 480)
            cur_min = int(eff_min or 480) % 1440
            if not (cur_min >= 1200 or cur_min < 360):
                continue
        inc_nid = str(inc.get("node_id") or "").strip().lower()
        inc_fac = str(inc.get("facility_name") or "").strip().lower()
        if (inc_nid and inc_nid == nid_low) or (inc_fac and inc_fac in loc_low):
            res = dict(inc)
            res.setdefault("breach_id", res.get("incursion_id", ""))
            res.setdefault("incursion_id", res.get("breach_id", ""))
            return res
        if inc_nid and nid_low and session_id:
            try:
                if db.is_descendant_of(session_id, nid_low, inc_nid) or db.is_descendant_of(session_id, inc_nid, nid_low):
                    res = dict(inc)
                    res.setdefault("breach_id", res.get("incursion_id", ""))
                    res.setdefault("incursion_id", res.get("breach_id", ""))
                    return res
            except Exception:
                pass
    return None


def _spawn_after_hours_campus_incursions(
    session_id: int,
    current_day: int,
    scen_key: str,
    rng: random.Random,
) -> List[Dict[str, Any]]:
    """
    Spawns 2-3 After-Hours School Facility Anomalies (active 20:00–06:00 only, dormant with foreshadowing clues 06:00–19:59)
    across haunted/isolated school campus facilities in `anomalous_high_school`.
    """
    from mechanics.world.locations.seeds import get_session_school_name
    school_name = get_session_school_name(session_id, scen_key) or "Main Academy Campus"
    after_hours_pool = [
        {
            "node_id": "loc_13th_stairwell",
            "facility_name": "The 13th Stairwell (Spatial Anomaly)",
            "zone_name": school_name,
            "full_location": f"{school_name} ➔ Abandoned Old Wing ➔ The 13th Stairwell (Spatial Anomaly)",
        },
        {
            "node_id": "sub_old_storage_3b",
            "facility_name": "Sealed Classroom 3-B",
            "zone_name": school_name,
            "full_location": f"{school_name} ➔ Abandoned Old Wing ➔ Sealed Classroom 3-B",
        },
        {
            "node_id": "loc_pool",
            "facility_name": "Indoor Swimming Pool",
            "zone_name": school_name,
            "full_location": f"{school_name} ➔ Athletics & Gymnasium Complex ➔ Indoor Swimming Pool",
        },
        {
            "node_id": "loc_science_lab",
            "facility_name": "Science & Chemistry Lab",
            "zone_name": school_name,
            "full_location": f"{school_name} ➔ Main Academic Building ➔ Science & Chemistry Lab",
        },
        {
            "node_id": "loc_old_east_music_room",
            "facility_name": "Dusty Old Music Room",
            "zone_name": school_name,
            "full_location": f"{school_name} ➔ Abandoned Old Wing ➔ Dusty Old Music Room",
        },
    ]
    # Resolve actual node names from spatial graph if seeded
    for entry in after_hours_pool:
        try:
            nd = db.get_world_node(session_id, entry["node_id"])
            if nd:
                entry["facility_name"] = nd["name"]
                anc = db.get_node_ancestors(session_id, entry["node_id"])
                chain = [a["name"] for a in reversed(anc)] + [nd["name"]]
                if chain:
                    entry["full_location"] = " ➔ ".join(chain)
                    entry["zone_name"] = chain[0]
        except Exception:
            pass

    pool_copy = list(after_hours_pool)
    rng.shuffle(pool_copy)
    ah_count = rng.choice([2, 3])
    chosen = pool_copy[:ah_count]
    ah_incursions: List[Dict[str, Any]] = []
    base_tier = max(1, min(5, 1 + (int(current_day or 1) - 1) // 3))

    for idx, loc in enumerate(chosen):
        subtype = INCURSION_SUBTYPES[(idx + int(current_day) + 1) % len(INCURSION_SUBTYPES)]
        inc_id = f"inc_ah_d{current_day}_{idx + 1}_{loc['node_id']}"
        force_disp = "hostile" if subtype == "hostile_breach" else "non_hostile"
        force_tp = "phenomenon" if subtype == "environmental_phenomenon" else ("entity" if idx % 2 == 0 else "object")
        eff_tier = max(1, min(5, base_tier))

        bp = generate_anomaly_blueprint(
            session_id=session_id,
            seed_key=inc_id,
            scenario=scen_key,
            location=loc["full_location"],
            current_minute=1260,
            force_type=force_tp,
            force_disposition=force_disp,
            tier=eff_tier,
        )
        entity_name = get_public_anomaly_name(bp, dossier_revealed=False, fallback=bp["name"])
        foreshadow = (
            f"Faint nocturnal resonance readings and unsettling schoolyard rumors linger around {loc['facility_name']} "
            f"({bp['sensory_omen']})—the anomaly is dormant during school hours and will fully manifest after 20:00 once the campus locks down."
        )
        title_prefix = (
            "After-Hours Campus Breach"
            if subtype == "hostile_breach"
            else ("After-Hours Campus Entity" if subtype == "non_hostile_entity" else "After-Hours Campus Phenomenon")
        )
        ah_incursions.append({
            "incursion_id": inc_id,
            "breach_id": inc_id,
            "day": int(current_day),
            "subtype": subtype,
            "temperament": bp.get("temperament", ""),
            "strikes": 0,
            "max_strikes": 2,
            "title": f"{title_prefix}: {entity_name}",
            "entity_name": entity_name,
            "category_tag": bp["category_tag"],
            "description": f"{bp['description']} {bp['sensory_omen']} (Active 20:00–06:00)",
            "preferred_stat": "STR" if subtype == "hostile_breach" else bp["preferred_stat"],
            "containment_note": bp["containment_note"],
            "anomaly_type": bp["type"],
            "physicality": bp["physicality"],
            "form": bp["form"],
            "form_label": bp["form_label"],
            "sapience": bp["sapience"],
            "disposition": bp["disposition"],
            "element": bp["element"],
            "resistances": bp["resistances"],
            "weaknesses": bp["weaknesses"],
            "taboo": bp["taboo"],
            "sensory_omen": bp["sensory_omen"],
            "dossier_revealed": False,
            "anomaly_blueprint": bp,
            "node_id": loc["node_id"],
            "zone_name": loc["zone_name"],
            "facility_name": loc["facility_name"],
            "location": loc["full_location"],
            "reward_gold": 75 + (35 * eff_tier),
            "reward_xp": 50 + (25 * eff_tier),
            "resolved": False,
            "agitated": False,
            "escaped": False,
            "killed_lethally": False,
            "optional": True,
            "time_window": "after_hours",
            "active_start_minute": 1200,
            "active_end_minute": 360,
            "is_campus_after_hours": True,
            "foreshadow_clue": foreshadow,
        })
    return ah_incursions


def get_dormant_after_hours_incursion_at_location(
    session_id: int,
    location_str: str = "",
    node_id: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Returns an unresolved After-Hours Campus Anomaly during its dormant daytime window (06:00–19:59)
    so visiting the facility during school hours exposes foreshadowing clues without triggering the encounter early.
    """
    if not session_id:
        return None
    sess = db.get_session(session_id) or {}
    if not scenario_data.is_anomalous_high_school_scenario(sess.get("scenario", "")):
        return None
    cur_min = int(sess.get("current_minute", 480) or 480) % 1440
    if cur_min >= 1200 or cur_min < 360:
        return None
    incursions = sess.get("daily_incursions") or []
    loc_low = str(location_str or sess.get("current_location") or "").strip().lower()
    nid_low = str(node_id or sess.get("current_node_id") or "").strip().lower()
    for inc in incursions:
        if not isinstance(inc, dict) or inc.get("resolved") or str(inc.get("time_window") or "") != "after_hours":
            continue
        inc_nid = str(inc.get("node_id") or "").strip().lower()
        inc_fac = str(inc.get("facility_name") or "").strip().lower()
        if (inc_nid and inc_nid == nid_low) or (inc_fac and inc_fac in loc_low):
            return dict(inc)
        if inc_nid and nid_low:
            try:
                if db.is_descendant_of(session_id, nid_low, inc_nid):
                    return dict(inc)
            except Exception:
                pass
    return None


def check_or_roll_school_hours_anomalous_incident(
    session_id: int,
    current_day: int = 1,
    current_minute: int = 480,
    force_roll: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """
    During weekday school hours (08:00–15:00) in `anomalous_high_school` when playing as a Student Special Agent on campus,
    rolls a 20% chance per turn (capped at max 1 per day) to trigger a spontaneous Daytime Campus Anomaly Incident
    at the student's current campus location.
    """
    if not session_id:
        return None
    sess = db.get_session(session_id) or {}
    scen_key = str(sess.get("scenario") or "")
    if not scenario_data.is_anomalous_high_school_scenario(scen_key):
        return None
    from mechanics.social.origin_mode import is_student_operative, is_school_hours
    from mechanics.world.world_schedule import is_campus_node_or_location
    if not is_student_operative(sess):
        return None
    eff_day = int(current_day or sess.get("current_day", 1) or 1)
    eff_min = int(current_minute if current_minute is not None else (sess.get("current_minute", 480) or 480))
    if not is_school_hours(eff_day, eff_min):
        return None
    if int(sess.get("last_school_hours_incident_day", 0) or 0) >= eff_day:
        return None

    curr_loc = str(sess.get("current_location") or "")
    curr_nid = str(sess.get("current_node_id") or "")
    curr_node = db.get_world_node(session_id, curr_nid) if curr_nid else None
    parent_node = db.get_world_node(session_id, curr_node["parent_id"]) if (curr_node and curr_node.get("parent_id")) else None
    if not is_campus_node_or_location(curr_node, parent_node, location_str=curr_loc, session_id=session_id, scen_key=scen_key):
        return None
    if get_active_incursion_at_location(session_id, curr_loc, curr_nid):
        return None

    rng = random.Random(f"school_hours_inc:{session_id}:{eff_day}:{eff_min}:{curr_nid}")
    roll_val = float(force_roll) if force_roll is not None else rng.random()
    if roll_val >= 0.20:
        return None

    fac_name = (curr_node.get("name") if curr_node else "") or curr_loc.split("➔")[-1].strip() or "Campus Corridor"
    zone_name = (parent_node.get("name") if parent_node else "") or curr_loc.split("➔")[0].strip() or "Main Academy Campus"
    inc_id = f"inc_school_d{eff_day}_{curr_nid or 'campus'}"
    subtype = rng.choice(["non_hostile_entity", "environmental_phenomenon", "hostile_breach"])
    force_disp = "hostile" if subtype == "hostile_breach" else "non_hostile"
    force_tp = "phenomenon" if subtype == "environmental_phenomenon" else "entity"
    eff_tier = max(1, min(4, 1 + (eff_day - 1) // 3))

    bp = generate_anomaly_blueprint(
        session_id=session_id,
        seed_key=inc_id,
        scenario=scen_key,
        location=curr_loc or fac_name,
        current_minute=eff_min,
        force_type=force_tp,
        force_disposition=force_disp,
        tier=eff_tier,
    )
    entity_name = get_public_anomaly_name(bp, dossier_revealed=False, fallback=bp["name"])
    inc_obj = {
        "incursion_id": inc_id,
        "breach_id": inc_id,
        "day": eff_day,
        "subtype": subtype,
        "temperament": bp.get("temperament", ""),
        "strikes": 0,
        "max_strikes": 2,
        "title": f"Campus Class-Hours Incident: {entity_name}",
        "entity_name": entity_name,
        "category_tag": bp["category_tag"],
        "description": f"Mid-day campus anomaly outbreak at {fac_name}! {bp['description']} {bp['sensory_omen']}",
        "preferred_stat": "STR" if subtype == "hostile_breach" else bp["preferred_stat"],
        "containment_note": bp["containment_note"],
        "anomaly_type": bp["type"],
        "physicality": bp["physicality"],
        "form": bp["form"],
        "form_label": bp["form_label"],
        "sapience": bp["sapience"],
        "disposition": bp["disposition"],
        "element": bp["element"],
        "resistances": bp["resistances"],
        "weaknesses": bp["weaknesses"],
        "taboo": bp["taboo"],
        "sensory_omen": bp["sensory_omen"],
        "dossier_revealed": False,
        "anomaly_blueprint": bp,
        "node_id": curr_nid or "loc_main_academic",
        "zone_name": zone_name,
        "facility_name": fac_name,
        "location": curr_loc or f"{zone_name} ➔ {fac_name}",
        "reward_gold": 65 + (30 * eff_tier),
        "reward_xp": 45 + (25 * eff_tier),
        "resolved": False,
        "agitated": False,
        "escaped": False,
        "killed_lethally": False,
        "optional": True,
        "time_window": "school_hours",
        "is_school_hours_incident": True,
        "spawn_turn": int(sess.get("turn_count", 0)),
    }
    incursions = list(sess.get("daily_incursions") or [])
    incursions.append(inc_obj)
    db.update_session(
        session_id,
        extra={
            "daily_incursions": incursions,
            "daily_breaches": None,
            "last_school_hours_incident_day": eff_day,
        },
    )
    return inc_obj


def _resolve_session_turn_number(session_id: Optional[int], sess: Optional[Dict[str, Any]] = None) -> int:
    """Resolves the active 1-based turn number via the persistence repository layer."""
    return db.get_effective_session_turn(session_id, sess)


roll_daily_anomaly_breaches = roll_daily_anomalous_incursions
get_active_breach_at_location = get_active_incursion_at_location
