from __future__ import annotations
"""
Daily Anomaly Breaches, Non-Hostile Entity Pacification/Agitation,
Containment Vault Flavor Log, and Faction-Aware Emergency Medical Extraction
for the Anomalous Incursions scenario and its variants.
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
                if nid in ANOMALOUS_SAFE_HQ_FACILITY_IDS or (nid.startswith("loc_hq_") and nid != "loc_hq_containment_sector"):
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
        seed_data = get_scenario_seed_data(scen_key)
        for z in (seed_data.get("zones") or []):
            z_id = z.get("id", "")
            if z_id == "zone_agency_hq" or (scenario_data.is_anomalous_high_school_scenario(scen_key) and z_id == "zone_school_campus"):
                continue
            z_name = get_session_urban_zone_name(session_id, z_id, z.get("name", ""), scen_key)
            for p in (z.get("primary_locations") or []):
                p_id = p.get("id", "")
                if p_id in ANOMALOUS_SAFE_HQ_FACILITY_IDS or p_id.startswith("loc_hq_"):
                    continue
                p_name = get_session_urban_facility_name(session_id, z_id, p_id, p.get("name", ""), scen_key)
                if p_id in ANOMALOUS_CONSOLIDATED_COMPLEX_IDS:
                    for sub in (p.get("sub_locations") or []):
                        s_id = sub.get("id", "")
                        s_name = sub.get("name", "")
                        if s_id and s_name:
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


def is_non_hostile_entity_quest(
    quest_or_wp: Optional[Dict[str, Any]],
    sub_obj: Optional[Dict[str, Any]] = None,
) -> bool:
    """Returns True if `quest_or_wp` (or `sub_obj`) represents a Non-Hostile Anomalous Entity containment task."""
    if not isinstance(quest_or_wp, dict):
        quest_or_wp = {}
    if not isinstance(sub_obj, dict):
        sub_obj = {}

    combined = " | ".join([
        str(quest_or_wp.get("quest_type") or ""),
        str(quest_or_wp.get("archetype") or ""),
        str(quest_or_wp.get("title") or quest_or_wp.get("quest_title") or ""),
        str(quest_or_wp.get("objective") or quest_or_wp.get("quest_objective") or ""),
        str(quest_or_wp.get("quest_notes") or ""),
        str(sub_obj.get("archetype") or ""),
        str(sub_obj.get("text") or ""),
        str(quest_or_wp.get("sub_obj_text") or ""),
    ]).lower()

    return any(
        kw in combined
        for kw in (
            "secure non-hostile anomalous entity",
            "non_hostile_entity_pacification",
            "non-hostile anomalous entity",
            "non-hostile entity",
            "non_hostile_entity",
            "live capture:",
            "non_hostile_temperament:",
        )
    )


def is_non_hostile_entity_containment_waypoint(
    wp: Optional[Dict[str, Any]],
    all_wps: Optional[List[Dict[str, Any]]] = None,
    sub_obj: Optional[Dict[str, Any]] = None,
    quest: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Returns True when `wp` is the active field-containment stage for a Non-Hostile Anomalous Entity
    (excluding Stage 1 pure arrival scouting and Stage 3 post-capture client delivery/turn-in).
    """
    if not isinstance(wp, dict):
        return False
    merged_q = dict(quest or {})
    for k, v in wp.items():
        if v is not None and (k not in merged_q or not merged_q.get(k)):
            merged_q[k] = v

    if not is_non_hostile_entity_quest(merged_q, sub_obj=sub_obj):
        return False

    trigger = str(wp.get("completion_trigger") or "skill_check").strip().lower()
    if trigger not in ("skill_check", "inspect_prop", "talk_to_npc", "action", "defeat_target"):
        return False

    q_notes = str(merged_q.get("quest_notes") or "")
    so_id_val = wp.get("sub_obj_id") if wp.get("sub_obj_id") is not None else (sub_obj.get("id") if isinstance(sub_obj, dict) else None)
    secured_flag = f"entity_secured_so_{so_id_val}:1" if so_id_val is not None else "entity_secured:1"
    if secured_flag in q_notes:
        return False

    stage_idx = int(wp.get("stage_index", 1) or 1)
    total_stages = len(all_wps) if isinstance(all_wps, list) and all_wps else int(wp.get("total_stages") or 0)
    lbl_low = str(wp.get("stage_label") or "").strip().lower()

    # If on Stage >= 3 of a 3+ stage quest and label is clearly client delivery/turn-in, do NOT treat as containment stage
    if stage_idx >= 3 and (total_stages == 0 or stage_idx >= total_stages):
        if any(
            turn_kw in lbl_low
            for turn_kw in ("deliver", "turn in", "hand over", "return to", "report to", "dispatch officer", "confirm receipt")
        ):
            return False

    return True


def get_non_hostile_entity_temperament(
    seed_key: str = "",
    quest_notes: str = "",
    explicit: str = "",
) -> str:
    """
    Deterministically returns one of the 4 non-hostile folklore temperaments:
      - `'timid'` (Elusive — flinches on Strike 1, flees on Strike 2)
      - `'volatile'` (Territorial — bristles on Strike 1, turns hostile in combat on Strike 2)
      - `'mischievous'` (Trickster — pockets 10-15G Trick-Tax on Strike 1, vanishes in illusion prank on Strike 2)
      - `'spook'` (Scare-Only / Odokashi — drains 4 MP on Strike 1, drains 8 MP + `Frightened` & vanishes on Strike 2)
    """
    exp_clean = str(explicit or "").strip().lower()
    if exp_clean in NON_HOSTILE_TEMPERAMENT_TYPES:
        return exp_clean

    notes_str = str(quest_notes or "")
    m = re.search(r"non_hostile_temperament:(timid|volatile|mischievous|spook)", notes_str, re.IGNORECASE)
    if m:
        return m.group(1).strip().lower()

    if "anomaly_bp:" in notes_str or "anomaly_blueprint:" in notes_str:
        bp_parsed = parse_blueprint_from_notes(notes_str)
        if isinstance(bp_parsed, dict):
            bp_t = str(bp_parsed.get("non_hostile_temperament") or bp_parsed.get("temperament") or "").strip().lower()
            if bp_t in NON_HOSTILE_TEMPERAMENT_TYPES:
                return bp_t

    digest = hashlib.md5(str(seed_key or "default_entity").encode("utf-8")).digest()
    return NON_HOSTILE_TEMPERAMENT_TYPES[digest[0] % len(NON_HOSTILE_TEMPERAMENT_TYPES)]


def get_temperament_brief_cue(temperament: str) -> str:
    """Returns a compact 1-line dispatch cue for bounty boards and SMS alerts."""
    t_low = str(temperament or "timid").strip().lower()
    if t_low == "volatile":
        return "Volatile/territorial—provoking risks combat."
    if t_low == "mischievous":
        return "Mischievous/trickster—failed checks risk coin-prank & illusion escape."
    if t_low == "spook":
        return "Spook/startle-seeker—failed checks drain composure & risk vanish."
    return "Timid/elusive—startling risks escape."


def get_temperament_scene_hint(entity_name: str, temperament: str) -> str:
    """Returns a narrative scene hint telegraphing how repeated failures resolve for all 4 temperaments."""
    ent = str(entity_name or "The anomalous entity").strip()
    t_low = str(temperament or "timid").strip().lower()
    if t_low == "volatile":
        return (
            f"{ent} exhibits a **volatile, territorial aura**—static arcs violently whenever cornered, "
            f"signaling it will lash out in combat if provoked by repeated failed containment attempts."
        )
    if t_low == "mischievous":
        return (
            f"{ent} exhibits a **mischievous, trickster demeanor**—playful illusions shimmer around it, "
            f"signaling failed containment checks will invite a coin-pocketing prank before it vanishes in a decoy burst."
        )
    if t_low == "spook":
        return (
            f"{ent} exhibits a **theatrical spook-only demeanor**—looming strictly to elicit a startled gasp, "
            f"signaling failed containment checks will rattle your composure (MP & `Frightened`) before it cackles and vanishes."
        )
    return (
        f"{ent} exhibits a **timid, skittish demeanor**—hovering near an unstable spatial seam, "
        f"poised to slip away and vanish if startled by repeated failed containment attempts."
    )


def apply_non_hostile_strike_side_effects(
    session_id: int,
    user_id: Optional[int],
    entity_name: str,
    temperament: str,
    is_final_strike: bool,
    *,
    seed_key: str = "",
    quest_id: str = "",
    incursion_id: str = "",
    target_inc: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Applies deterministic Strike 1 & Strike 2 non-combat folklore consequences for `mischievous` and `spook`:
      - `mischievous`:
        - Strike 1: Pockets 10-15G (`min(gold, tax)`) in escrow (refunded on capture) or +1 next-check DC if at 0G; 0 HP loss.
        - Strike 2: Vanishes in an illusion prank keeping pocketed coins (`escaped=True`, 0 HP loss, no combat).
      - `spook`:
        - Strike 1: Eerie fake-out draining 4 MP (floored at 0; +1 next-check DC if already at 0 MP); 0 HP loss.
        - Strike 2: Full jump-scare draining 8 MP + applying native `'Frightened'` status condition, then vanishes (`escaped=True`, 0 HP loss).
    """
    from db.quests import append_quest_note_flag_in_db

    t_low = str(temperament or "timid").strip().lower()
    ent = str(entity_name or "the Anomalous Entity").strip()
    out: Dict[str, Any] = {
        "temperament": t_low,
        "gold_stolen": 0,
        "total_escrowed_gold": 0,
        "mp_drained": 0,
        "status_applied": "",
        "prank_dc_penalty": 0,
        "hp_delta": 0,
        "warn_suffix": "",
        "escape_message": "",
        "directive": "",
    }
    if t_low not in ("mischievous", "spook"):
        return out

    char = (db.get_character(int(user_id)) or {}) if user_id else {}
    prev_tax = 0
    if quest_id and session_id:
        q_row = db.get_quest_by_id(session_id, quest_id) or {}
        m_tx = re.search(r"trick_tax_gold:(\d+)", str(q_row.get("quest_notes") or ""))
        if m_tx:
            prev_tax = int(m_tx.group(1))
    elif isinstance(target_inc, dict):
        prev_tax = int(target_inc.get("trick_tax_gold", 0) or 0)

    if t_low == "mischievous":
        h_hex = hashlib.md5(f"{session_id}:{seed_key or quest_id or incursion_id}:{ent}".encode("utf-8")).hexdigest()
        tax_roll = 10 + (int(h_hex[:6], 16) % 6)  # 10..15G
        cur_gold = max(0, int(char.get("gold", 0) or 0))
        if not is_final_strike:
            stolen = min(cur_gold, tax_roll) if user_id else 0
            if stolen > 0 and user_id:
                db.apply_hp_mp_delta(int(user_id), gold_delta=-stolen)
                new_escrow = prev_tax + stolen
                out["gold_stolen"] = stolen
                out["total_escrowed_gold"] = new_escrow
                if quest_id and session_id:
                    append_quest_note_flag_in_db(session_id, quest_id, "trick_tax_gold", str(new_escrow))
                if isinstance(target_inc, dict):
                    target_inc["trick_tax_gold"] = new_escrow
                out["warn_suffix"] = (
                    f"Giggling at your slip, **{ent}** picks your pocket for **{stolen}G** in loose coins "
                    f"*(contain it on the next attempt to recover your {new_escrow}G, or one more failure and it will vanish with them)*!"
                )
            else:
                out["prank_dc_penalty"] = 1
                if quest_id and session_id:
                    append_quest_note_flag_in_db(session_id, quest_id, "prank_dc", "1")
                if isinstance(target_inc, dict):
                    target_inc["prank_dc_penalty"] = 1
                out["warn_suffix"] = (
                    f"Finding your pockets empty, **{ent}** scrambles nearby decoys in a teasing laugh (**+1 DC** on next check unless Taboo exploited)—"
                    f"one more failed check and it will vanish in an illusion prank!"
                )
            out["directive"] = (
                f"[MISCHIEVOUS TRICKSTER PRANK — STRIKE 1]: '{ent}' played a harmless prank ({out['warn_suffix']}). "
                f"Zero HP damage occurred; one more failed check and it escapes in a burst of illusions."
            )
            return out

        # Final strike (Strike >= 2): Illusion Escape!
        stolen_final = 0
        if prev_tax == 0 and cur_gold > 0 and user_id:
            stolen_final = min(cur_gold, tax_roll)
            db.apply_hp_mp_delta(int(user_id), gold_delta=-stolen_final)
        kept_total = prev_tax + stolen_final
        out["gold_stolen"] = stolen_final
        out["total_escrowed_gold"] = kept_total
        if quest_id and session_id:
            append_quest_note_flag_in_db(session_id, quest_id, "trick_tax_forfeited", "1")
        if isinstance(target_inc, dict):
            target_inc["trick_tax_forfeited"] = True
        coin_clause = f" keeping your **{kept_total}G** in pocketed coins and leaving a counterfeit leaf behind" if kept_total > 0 else " leaving a teasing counterfeit leaf behind"
        out["escape_message"] = (
            f"🃏 **Trickster Prank Escape!** Outwitting your repeated containment attempts, **{ent}** bursts into illusory confetti and vanishes,{coin_clause}! "
            f"Live-containment rewards forfeited as it slips away unharmed."
        )
        out["directive"] = (
            f"[MISCHIEVOUS TRICKSTER ESCAPED]: '{ent}' pulled a playful parting illusion prank ({coin_clause.strip()}) "
            f"and vanished without combat or injury!"
        )
        return out

    # `spook` temperament (Scare-Only / Odokashi)
    cur_mp = max(0, int(char.get("mp", 0) or 0))
    if not is_final_strike:
        drained = min(cur_mp, 4) if user_id else 0
        if drained > 0 and user_id:
            db.apply_hp_mp_delta(int(user_id), mp_delta=-drained)
            out["mp_drained"] = drained
            out["warn_suffix"] = (
                f"Delighted by your hesitation, **{ent}** lunges in an eerie fake-out that rattles your composure—"
                f"one more failed check and its full scare will send it vanishing in triumph!"
            )
        else:
            out["prank_dc_penalty"] = 1
            if quest_id and session_id:
                append_quest_note_flag_in_db(session_id, quest_id, "prank_dc", "1")
            if isinstance(target_inc, dict):
                target_inc["prank_dc_penalty"] = 1
            out["warn_suffix"] = (
                f"Sensing your drained composure, **{ent}** looms closer with an uncanny grin (containment challenge heightened unless Taboo exploited)—"
                f"one more failed check and it will unleash its jump-scare and vanish!"
            )
        out["directive"] = (
            f"[SPOOK FAKE-OUT — STRIKE 1]: '{ent}' staged an eerie non-lethal startle ({out['warn_suffix']}). "
            f"Zero physical harm occurred; one more failed check and it spooks the player and vanishes."
        )
        return out

    # Final strike (Strike >= 2): Full Jump-Scare + `Frightened` + Satisfied Vanish!
    drained_final = min(cur_mp, 8) if user_id else 0
    if user_id:
        if drained_final > 0:
            db.apply_hp_mp_delta(int(user_id), mp_delta=-drained_final)
        char_after = db.get_character(int(user_id)) or {}
        eff_list = list(char_after.get("status_effects") or [])
        has_fright = any(
            (isinstance(s, dict) and str(s.get("name") or "").lower() == "frightened")
            or (isinstance(s, str) and s.strip().lower() == "frightened")
            for s in eff_list
        )
        if not has_fright:
            eff_list.append("Frightened")
            db.set_status_effects(int(user_id), eff_list)
        out["status_applied"] = "Frightened"
    out["mp_drained"] = drained_final
    out["escape_message"] = (
        f"👻 **Startled & Spooked!** **{ent}** pulls a theatrical folklore jump-scare (leaving you shaken and **Frightened**)! "
        f"Satisfied by your startled gasp, it cackles and dissolves into mist—live-containment rewards forfeited."
    )
    out["directive"] = (
        f"[SPOOK ANOMALY VANISHED IN SATISFACTION]: '{ent}' startled the player (applied 'Frightened') "
        f"and vanished happily into mist now that its scare succeeded!"
    )
    return out


def refund_trick_tax_gold_on_containment(
    session_id: int,
    user_id: Optional[int],
    *,
    quest_id: str = "",
    incursion_id: str = "",
    target_inc: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Idempotently refunds any `trick_tax_gold` pocketed on Strike 1 when a `mischievous`
    anomaly is successfully contained peacefully or subdued/de-escalated in combat.
    """
    from db.quests import append_quest_note_flag_in_db

    refund_amt = 0
    if isinstance(target_inc, dict) and not target_inc.get("trick_tax_forfeited") and not target_inc.get("trick_tax_refunded"):
        refund_amt = max(0, int(target_inc.get("trick_tax_gold", 0) or 0))
        if refund_amt > 0:
            target_inc["trick_tax_gold"] = 0
            target_inc["trick_tax_refunded"] = True
    elif incursion_id and session_id:
        sess = db.get_session(session_id) or {}
        incursions = list(sess.get("daily_incursions") or sess.get("daily_breaches") or [])
        changed = False
        for inc in incursions:
            if isinstance(inc, dict) and (inc.get("incursion_id") == incursion_id or inc.get("breach_id") == incursion_id):
                if not inc.get("trick_tax_forfeited") and not inc.get("trick_tax_refunded"):
                    refund_amt = max(0, int(inc.get("trick_tax_gold", 0) or 0))
                    if refund_amt > 0:
                        inc["trick_tax_gold"] = 0
                        inc["trick_tax_refunded"] = True
                        changed = True
                break
        if changed:

            db.update_session(session_id, extra={"daily_incursions": incursions, "daily_breaches": None})

    if refund_amt == 0 and quest_id and session_id:
        q_row = db.get_quest_by_id(session_id, quest_id) or {}
        notes = str(q_row.get("quest_notes") or "")
        if "trick_tax_forfeited:1" not in notes and "trick_tax_refunded:1" not in notes:
            m_tx = re.search(r"trick_tax_gold:(\d+)", notes)
            if m_tx and int(m_tx.group(1)) > 0:
                refund_amt = int(m_tx.group(1))
                append_quest_note_flag_in_db(session_id, quest_id, "trick_tax_refunded", "1")
                append_quest_note_flag_in_db(session_id, quest_id, "trick_tax_gold", "0")

    if refund_amt > 0 and user_id:
        db.apply_hp_mp_delta(int(user_id), gold_delta=refund_amt)
        return {
            "refunded_gold": refund_amt,
            "notice": f"🪙 Recovered **+{refund_amt}G** in pocketed coins!",
        }
    return {"refunded_gold": 0, "notice": ""}


def extract_non_hostile_entity_name(
    quest_or_wp: Optional[Dict[str, Any]],
    sub_obj: Optional[Dict[str, Any]] = None,
) -> str:
    """Extracts a clean display name for the target Non-Hostile Entity from quest/waypoint metadata."""
    if not isinstance(quest_or_wp, dict):
        quest_or_wp = {}
    if not isinstance(sub_obj, dict):
        sub_obj = {}

    notes = str(quest_or_wp.get("quest_notes") or "")
    m_note = re.search(r"entity_name:([^|\n]+)", notes)
    if m_note and m_note.group(1).strip():
        return m_note.group(1).strip()

    for candidate in (
        str(quest_or_wp.get("title") or quest_or_wp.get("quest_title") or ""),
        str(quest_or_wp.get("stage_label") or ""),
        str(sub_obj.get("text") or ""),
        str(quest_or_wp.get("objective") or quest_or_wp.get("quest_objective") or ""),
    ):
        if not candidate:
            continue
        m_colon = re.search(r"(?:Live Capture|Non-Hostile Entity|Containment)\s*:\s*([^(\n|]+)", candidate, re.IGNORECASE)
        if m_colon and m_colon.group(1).strip():
            return m_colon.group(1).strip()
        m_quote = re.search(r"'([^']{3,60})'", candidate)
        if m_quote and m_quote.group(1).strip():
            val = m_quote.group(1).strip()
            if not any(skip in val.lower() for skip in ("live capture:", "[mandatory]")):
                return val

    req_item = str(quest_or_wp.get("required_item") or "").strip()
    if req_item and "containment" not in req_item.lower():
        return req_item
    return "the Anomalous Entity"


def _resolve_session_turn_number(session_id: Optional[int], sess: Optional[Dict[str, Any]] = None) -> int:
    if isinstance(sess, dict) and sess.get("_target_turn") is not None:
        return int(sess["_target_turn"])
    if session_id:
        try:
            with db.get_conn() as c:
                row = c.execute(
                    "SELECT turn_count, last_turn_snapshot_json FROM sessions WHERE id = ?",
                    (int(session_id),),
                ).fetchone()
                if row:
                    from db.dossiers import _effective_session_turn
                    return _effective_session_turn(row, None)
        except Exception:
            pass
    return int((sess or {}).get("turn_count", 0) or 0)


def reveal_anomaly_dossier(
    session_id: int,
    quest_id: str = "",
    incursion_id: str = "",
    breach_id: str = "",
) -> Dict[str, Any]:
    """
    Marks an Anomaly Dossier as fully investigated (`dossier_revealed = True`),
    revealing Physicality, Sapience, Elemental Resistances/Weaknesses, and Folklore/SCP Taboo,
    and unlocking the +2 Investigation Bonus & Taboo Exploitation!
    """
    from db.quests import append_quest_note_flag_in_db

    sess = db.get_session(session_id) or {}
    eff_inc = str(incursion_id or breach_id or "").strip()
    bp: Optional[Dict[str, Any]] = None
    unmask_msg = ""
    unmasked_from = ""

    if quest_id:
        q = db.get_quest_by_id(session_id, quest_id) or {}
        notes = str(q.get("quest_notes") or "")
        bp = parse_blueprint_from_notes(notes)
        if bp:
            prev_alias_q = str((bp.get("disguise_state") or {}).get("disguise_alias") or "").strip()
            bp, unmask_msg = unmask_blueprint_disguise(bp)
            bp["dossier_revealed"] = True
            new_bp_token = serialize_blueprint_note(bp).split("|", 1)[0]
            cleaned_notes = re.sub(r"anomaly_(?:bp|blueprint):[A-Za-z0-9+/=_-]+", new_bp_token, notes)
            true_nm = str(bp.get("canonical_name") or bp.get("name") or "").strip()
            if unmask_msg and true_nm:
                unmasked_from = prev_alias_q
                if "entity_name:" in cleaned_notes:
                    cleaned_notes = re.sub(r"entity_name:[^|]+", f"entity_name:{true_nm}", cleaned_notes)
                else:
                    cleaned_notes = f"{cleaned_notes}|entity_name:{true_nm}"
            with db.get_conn() as conn:
                conn.execute(
                    "UPDATE quests SET quest_notes = ? WHERE session_id = ? AND quest_id = ?",
                    (cleaned_notes, session_id, quest_id),
                )
        append_quest_note_flag_in_db(session_id, quest_id, "dossier_revealed", "1")

    if eff_inc:
        incursions = list(sess.get("daily_incursions") or sess.get("daily_breaches") or [])
        for inc in incursions:
            if isinstance(inc, dict) and (inc.get("incursion_id") == eff_inc or inc.get("breach_id") == eff_inc):
                inc["dossier_revealed"] = True
                inc["revealed_at_turn"] = _resolve_session_turn_number(session_id, sess)
                if inc.get("original_entity_name") is None:
                    inc["original_entity_name"] = str(inc.get("entity_name") or "")
                if isinstance(inc.get("anomaly_blueprint"), dict):
                    prev_alias_i = str((inc["anomaly_blueprint"].get("disguise_state") or {}).get("disguise_alias") or inc.get("entity_name") or "").strip()
                    inc_bp, inc_unmask = unmask_blueprint_disguise(inc["anomaly_blueprint"])
                    inc_bp["dossier_revealed"] = True
                    inc["anomaly_blueprint"] = inc_bp
                    bp = inc_bp
                    if inc_unmask:
                        unmask_msg = inc_unmask
                        unmasked_from = prev_alias_i
                        true_inc_nm = str(inc_bp.get("canonical_name") or inc_bp.get("name") or inc.get("entity_name") or "")
                        old_nm = str(inc.get("entity_name") or "")
                        if true_inc_nm:
                            inc["entity_name"] = true_inc_nm
                            if old_nm and old_nm in str(inc.get("title") or ""):
                                inc["title"] = str(inc["title"]).replace(old_nm, true_inc_nm)

        db.update_session(session_id, extra={"daily_incursions": incursions, "daily_breaches": None})

    if bp and session_id:
        try:
            fresh_sess = db.get_session(session_id) or sess
            true_canon_nm = str(bp.get("canonical_name") or bp.get("name") or "").strip()
            if unmasked_from and true_canon_nm:
                cur_dp = str(fresh_sess.get("dialogue_partner") or "").strip()
                if cur_dp and cur_dp.lower() == unmasked_from.lower():
                    fresh_sess["dialogue_partner"] = true_canon_nm
                    fresh_sess["dialogue_partners"] = [true_canon_nm]
                    db.update_session(
                        session_id,
                        dialogue_partner=true_canon_nm,
                        extra={"dialogue_partners": [true_canon_nm]},
                    )
            sync_non_hostile_anomaly_scene_presence(session_id, session=fresh_sess, persist_db=True)
            db.record_session_anomaly_field_log(
                session_id,
                bp,
                stage="verified",
                location=str(fresh_sess.get("current_location") or ""),
            )
            if bp.get("codex_id"):
                db.record_folklore_codex_progress(
                    db.get_session_participant_user_ids(session_id),
                    str(bp["codex_id"]),
                    stage="verified",
                )
        except Exception:
            pass

    summary_obj = format_anomaly_dossier_summary(bp, revealed=True) if bp else None
    summary = (
        (summary_obj.get("summary_text") if isinstance(summary_obj, dict) else str(summary_obj))
        if summary_obj
        else "Dossier Revealed (+2 Containment Bonus)"
    )
    if unmask_msg:
        summary = f"{unmask_msg} {summary}"
    return {
        "revealed": True,
        "dossier_revealed": True,
        "unmask_notice": unmask_msg,
        "unmasked_from": unmasked_from,
        "blueprint": bp,
        "dossier_summary": summary,
        "dossier": summary_obj,
    }


def handle_secured_object_anomaly_conversion(
    session_id: int,
    user_id: Optional[int],
    blueprint: Optional[Dict[str, Any]],
    scen_key: str = "anomalous_incursions",
    entity_name: str = "",
    *,
    skip_codex_progress: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Converts a secured or neutralized `object` anomaly into a usable `[Anomalous]` Weapon, Accessory, or Wearable:
    - Private Agencies (`private_agency_1`, `private_agency_2`), Monastic Order (`monastic_order`), & Freelancers (`freelancer`):
      Immediately keep the converted `[Anomalous]` relic in player inventory!
    - Public Agency (`public_agency`):
      Logs the relic to the Bureau Containment Vault (`session['anomalous_vault_requisitions']`), awards `+5` Promotion Rep,
      and unlocks it for **50%-off Requisition** at the HQ Tactical Armory (`loc_hq_tactical_armory`)!
    """
    from mechanics.combat.items.anomalous_gear import convert_object_anomaly_to_gear
    from mechanics.social.factions import get_anomalous_faction_state, update_agent_promotion_reputation

    bp = dict(blueprint) if isinstance(blueprint, dict) else {}
    anom_type = str(bp.get("type") or bp.get("anomaly_type") or "").strip().lower()
    if anom_type != "object":
        return None
    if entity_name and not bp.get("name"):
        bp["name"] = entity_name

    gear_item = convert_object_anomaly_to_gear(bp, scenario=scen_key)
    if session_id and not skip_codex_progress:
        try:
            sess_obj_log = db.get_session(session_id) or {}
            db.record_session_anomaly_field_log(
                session_id,
                bp,
                stage="contained",
                location=str(sess_obj_log.get("current_location") or ""),
                resolution_method="Object Relic Secured & Converted",
            )
            if bp.get("codex_id"):
                uids_obj = db.get_session_participant_user_ids(session_id) or ([int(user_id)] if user_id else [])
                db.record_folklore_codex_progress(uids_obj, str(bp["codex_id"]), stage="contained")
                db.retire_or_cooldown_folklore_in_session(
                    session_id,
                    str(bp["codex_id"]),
                    uniqueness=str(bp.get("uniqueness") or "species"),
                    current_day=int(sess_obj_log.get("current_day") or sess_obj_log.get("in_game_day") or 1),
                    cooldown_days=int(bp.get("cooldown_days", 4) or 4),
                )
        except Exception:
            pass
    fac_state = get_anomalous_faction_state(session_id, user_id=user_id)
    arch = str(fac_state.get("faction_archetype_key") or "public_agency")

    if arch == "public_agency":
        sess = db.get_session(session_id) or {}
        gear_item["turn_captured"] = _resolve_session_turn_number(session_id, sess)
        req_list = list(sess.get("anomalous_vault_requisitions") or [])
        if not any(isinstance(r, dict) and r.get("name") == gear_item["name"] for r in req_list):
            req_list.append(gear_item)
            db.update_session(session_id, extra={"anomalous_vault_requisitions": req_list})
        update_agent_promotion_reputation(
            session_id=session_id,
            delta_rep=5,
            reason=f"Logged Object Anomaly '{gear_item['name']}' to Bureau Vault",
            user_id=user_id,
        )
        return {
            "converted": True,
            "mode": "public_agency_requisition",
            "faction_archetype_key": arch,
            "item": gear_item,
            "rep_bonus": 5,
            "notice": (
                f"🏛️ **Object Relic Logged to Bureau Vault:** **{gear_item['name']}** ({gear_item['item_type']}) "
                f"earned **+5 Promotion Rep** and is now unlocked for **50%-off Requisition** at the HQ Tactical Armory!"
            ),
        }

    if user_id:
        db.add_item(
            user_id,
            gear_item["name"],
            item_type=gear_item.get("item_type", "Weapon"),
            effect=gear_item.get("effect", ""),
            slot_cost=int(gear_item.get("slot_cost", 1) or 1),
        )
    return {
        "converted": True,
        "mode": "direct_keep",
        "faction_archetype_key": arch,
        "item": gear_item,
        "rep_bonus": 0,
        "notice": (
            f"🔮 **Anomalous Object Converted:** Harnessed **{gear_item['name']}** ({gear_item['item_type']}) "
            f"directly into your inventory!"
        ),
    }


_BIOME_CONTAINMENT_FIXTURES: Dict[str, str] = {
    "transit": "platform safety gates & conductive rails",
    "hospital": "quarantine ward bulkheads & lead shielding",
    "shrine": "sacred torii boundary ropes & stone lanterns",
    "broadcast": "relay Faraday cages & grounded antennae",
    "subterranean": "floodgate bulkheads & maintenance conduits",
    "commercial": "security shutters & mirrored display alcoves",
    "residential": "threshold doorframes & hallway ward-seals",
    "industrial": "hydraulic containment bay clamps & grounding grids",
    "natural": "ley-line boundary stones & canopy clearings",
    "nature": "ley-line boundary stones & canopy clearings",
    "coastal": "tide-gate sluices & salt-crusted pier pilings",
    "urban": "alley threshold doorframes & streetlamp ward-seals",
}


def _build_contextual_containment_verb(
    spec: Dict[str, str],
    entity_name: str,
    bp: Optional[Dict[str, Any]],
    eff_sap: str,
    is_revealed: bool,
    stat: str,
    exploit_stats: set[str],
) -> str:
    """
    Weaves the anomaly's specific form, biome fixtures, and—when `is_revealed` is True—its
    Folklore/SCP Taboo & Containment Protocol directly into the containment choice verb.
    """
    if not isinstance(bp, dict) or not bp:
        return spec["verb_template"].format(entity_name=entity_name)

    form_lbl = (
        "uncanny presence"
        if is_blueprint_disguised(bp, dossier_revealed=is_revealed)
        else str(bp.get("form_label") or bp.get("type") or "anomalous manifestation").strip().lower()
    )
    biome_key = str(bp.get("biome") or "urban").strip().lower()
    fixture = _BIOME_CONTAINMENT_FIXTURES.get(biome_key, "local structural geometry & ward-anchors")
    taboo = bp.get("taboo") if isinstance(bp.get("taboo"), dict) else {}
    taboo_name = str(bp.get("taboo_name") or taboo.get("name") or "").strip()
    protocol_str = str(bp.get("containment_protocol") or taboo.get("containment_protocol") or "").strip()
    short_proto = protocol_str.split(".")[0].strip() if protocol_str else ""

    if is_revealed and stat in exploit_stats and (taboo_name or short_proto):
        proto_tag = f"{taboo_name}: {short_proto[:48]}" if (taboo_name and short_proto) else (taboo_name or short_proto[:55])
        if stat == "CHA":
            if eff_sap == "compulsive":
                return f"Recite {proto_tag} courtesy script to satisfy {entity_name}"
            return f"Invoke {proto_tag} to bargain with {entity_name}"
        if stat == "PER":
            return f"Observe {proto_tag} to soothe {entity_name}"
        if stat == "INT":
            return f"Exploit {proto_tag} to snare {entity_name}"
        return f"Execute {proto_tag} across {fixture} to seal {entity_name}"

    if is_revealed and taboo_name:
        if stat == "CHA":
            if eff_sap == "sapient":
                return f"Negotiate containment terms with {entity_name} while honoring {taboo_name}"
            if eff_sap == "compulsive":
                return f"Recite the formal courtesy script for {entity_name} ({form_lbl}) under {taboo_name}"
            if eff_sap == "instinctual":
                return f"Project a non-threatening presence toward {entity_name} ({form_lbl}) under {taboo_name}"
            return f"Attune your vocal cadence to harmonize with {entity_name}'s {form_lbl} frequency"
        if stat == "PER":
            if eff_sap == "compulsive":
                return f"Time the ritual loop cadence of {entity_name} ({form_lbl}) under {taboo_name}"
            return f"Read {entity_name}'s {form_lbl} tells and calm its resonance under {taboo_name}"
        if stat == "INT":
            if eff_sap == "compulsive":
                return f"Spring a counting or rule snare on {entity_name} ({form_lbl}) under {taboo_name}"
            return f"Configure a calibrated containment snare for {entity_name} ({form_lbl})"
        if eff_sap == "compulsive":
            return f"Mirror {entity_name}'s ritual choreography across {fixture} to seal it"
        return f"Leverage {fixture} to box in and seal {entity_name}"

    if stat == "CHA":
        if eff_sap == "sapient":
            return f"Reason with {entity_name} ({form_lbl}) and negotiate peaceful containment"
        if eff_sap == "compulsive":
            return f"Offer formal folklore courtesy to satisfy {entity_name}'s ({form_lbl}) ritual script"
        if eff_sap == "instinctual":
            return f"Project a calm, non-threatening posture to coax {entity_name} ({form_lbl})"
        return f"Attune your vocal cadence to stabilize {entity_name} ({form_lbl})"
    if stat == "PER":
        if eff_sap == "compulsive":
            return f"Study the exact repetition cadence of {entity_name}'s ({form_lbl}) loop"
        if eff_sap == "non_sapient":
            return f"Track the harmonic pulse of {entity_name} ({form_lbl}) and dampen its surge"
        return f"Read {entity_name}'s {form_lbl} aura and soothe its agitation"
    if stat == "INT":
        if eff_sap == "sapient":
            return f"Outmaneuver {entity_name} ({form_lbl}) into a field containment snare"
        if eff_sap == "compulsive":
            return f"Introduce a counting distraction to loop-lock {entity_name} ({form_lbl})"
        if eff_sap == "instinctual":
            return f"Lure {entity_name} ({form_lbl}) into a baited containment snare"
        return f"Triangulate the phase-pattern of {entity_name} ({form_lbl}) to lock a seal"
    if eff_sap == "compulsive":
        return f"Step in rhythm with {entity_name}'s choreography across {fixture} to seal it"
    return f"Use {fixture} to corner and seal {entity_name}"


def build_sapient_anomaly_converse_choice(
    entity_name: str,
    *,
    mode: str = "quest",
    quest_id: str = "",
    sub_obj_id: Optional[int] = None,
    stage_index: int = 2,
    is_story_quest: bool = False,
    incursion_id: str = "",
    breach_id: str = "",
    blueprint: Optional[Dict[str, Any]] = None,
    sapience: str = "sapient",
) -> Dict[str, Any]:
    """
    Builds the strike-free '💬 Converse with {entity_name}' choice for Sapient anomalies,
    or '👁️ Study {entity_name}'s Pattern' choice for Compulsive (Pattern-Bound) anomalies.
    """
    ent = str(entity_name or "the Anomalous Entity").strip()
    eff_id = str(incursion_id or breach_id or "").strip()
    eff_sap = "compulsive" if str(sapience or (blueprint or {}).get("sapience") or "").strip().lower() == "compulsive" else "sapient"
    form_lbl = (
        "uncanny figure"
        if is_blueprint_disguised(blueprint or {}, dossier_revealed=bool((blueprint or {}).get("dossier_revealed")))
        else str((blueprint or {}).get("form_label") or "anomalous entity").strip().lower()
    )
    if eff_sap == "compulsive":
        lbl = f"👁️ Study {ent}'s Pattern: Observe this {form_lbl}'s compulsive loop & folklore rules (FREE)"
        act_key = "anomaly_pattern_study"
    else:
        lbl = f"💬 Converse with {ent}: Question this {form_lbl} about its origins, nature & motive (FREE)"
        act_key = "anomaly_inquiry"
    if mode == "incursion":
        return {
            "label": lbl[:190],
            "stat": "FREE",
            "requirement": 0,
            "mp_cost": 0,
            "intent": "dialogue_init",
            "target_npc": ent,
            "incursion_action": act_key,
            "incursion_id": eff_id,
            "breach_id": eff_id,
            "sapience": eff_sap,
            "is_anomaly_inquiry": True,
            "_npc_speak_choice": True,
            "_server_stamped": True,
        }
    return {
        "label": lbl[:190],
        "stat": "FREE",
        "requirement": 0,
        "mp_cost": 0,
        "intent": "dialogue_init",
        "sub_intent": act_key,
        "target_npc": ent,
        "is_fallback": False,
        "quest_id": quest_id,
        "sub_obj_id": sub_obj_id,
        "stage_index": stage_index,
        "is_quest_action": False,
        "is_story_quest": bool(is_story_quest),
        "approach": act_key,
        "incursion_action": act_key,
        "sapience": eff_sap,
        "is_anomaly_inquiry": True,
        "_npc_speak_choice": True,
        "_server_stamped": True,
    }


def build_non_hostile_narrative_choices(
    entity_name: str,
    mode: str = "quest",
    *,
    char: Optional[Dict[str, Any]] = None,
    quest_id: str = "",
    sub_obj_id: Optional[int] = None,
    stage_index: int = 2,
    is_story_quest: bool = False,
    contract_type: str = "skill_check",
    dc_mod: int = 0,
    incursion_id: str = "",
    breach_id: str = "",
    sapience: str = "",
    blueprint: Optional[Dict[str, Any]] = None,
    dossier_revealed: Optional[bool] = None,
    session_id: Optional[int] = None,
    include_converse: bool = False,
) -> List[Dict[str, Any]]:
    """
    Builds all 4 guaranteed out-of-combat narrative containment choices:
      1. Persuade (CHA)
      2. Calm (PER)
      3. Outwit (INT)
      4. Use Environment (AGI)
    Dynamically weaves in the anomaly's form, biome fixtures, and—when `dossier_revealed` is True—
    its Folklore/SCP Taboo & Containment Protocol, and applies `-2` DC (`-3` DC on Taboo `exploit_stats`).
    When `include_converse=True`, prepends a strike-free `💬 Converse` (`sapient`) or
    `👁️ Study Pattern` (`compulsive`) choice before containing the entity.
    """
    eff_id = str(incursion_id or breach_id or "").strip()
    ent = str(entity_name or "the Anomalous Entity").strip()
    stats_dict = (char or {}).get("stats") if isinstance((char or {}).get("stats"), dict) else {}
    stat_col_map = {"STR": "str_", "PER": "per_", "END": "end_", "CHA": "cha", "INT": "int_", "AGI": "agi", "LUK": "luk"}

    if session_id is None and isinstance(char, dict) and char.get("active_session_id"):
        try:
            session_id = int(char["active_session_id"])
        except Exception:
            pass
    bp = dict(blueprint) if isinstance(blueprint, dict) else None
    prank_dc_pen = 0
    if session_id:
        if quest_id:
            q_row = db.get_quest_by_id(session_id, quest_id) or {}
            q_notes = str(q_row.get("quest_notes") or "")
            if bp is None:
                bp = parse_blueprint_from_notes(q_notes)
            if dossier_revealed is None and "dossier_revealed:1" in q_notes:
                dossier_revealed = True
            if "prank_dc:1" in q_notes:
                prank_dc_pen = 1
        elif eff_id:
            sess_row = db.get_session(session_id) or {}
            for inc in (sess_row.get("daily_incursions") or sess_row.get("daily_breaches") or []):
                if isinstance(inc, dict) and (inc.get("incursion_id") == eff_id or inc.get("breach_id") == eff_id):
                    if bp is None and isinstance(inc.get("anomaly_blueprint"), dict):
                        bp = dict(inc["anomaly_blueprint"])
                    if dossier_revealed is None:
                        dossier_revealed = bool(inc.get("dossier_revealed"))
                    if not sapience and inc.get("sapience"):
                        sapience = str(inc.get("sapience"))
                    prank_dc_pen = int(inc.get("prank_dc_penalty", 0) or 0)
                    break

    eff_sap = str(sapience or (bp.get("sapience") if bp else "") or "sapient").strip().lower()
    if eff_sap not in SAPIENCE_APPROACH_SPEC_OVERRIDES:
        eff_sap = "sapient"
    is_revealed = bool(dossier_revealed if dossier_revealed is not None else (bp.get("dossier_revealed") if bp else False))
    taboo = (bp.get("taboo") if bp else None) or {}
    exploit_stats = {str(s).upper() for s in (taboo.get("exploit_stats") or (bp.get("exploit_stats") if bp else []) or [])}

    prefix = "Story Quest" if is_story_quest else "Bounty"
    q_icon = "⭐" if is_story_quest else "🎯"
    specs = SAPIENCE_APPROACH_SPEC_OVERRIDES.get(eff_sap, NON_HOSTILE_APPROACH_SPECS)

    choices: List[Dict[str, Any]] = []
    if include_converse and eff_sap in ("sapient", "compulsive"):
        choices.append(
            build_sapient_anomaly_converse_choice(
                ent,
                mode=mode,
                quest_id=quest_id,
                sub_obj_id=sub_obj_id,
                stage_index=stage_index,
                is_story_quest=is_story_quest,
                incursion_id=eff_id,
                breach_id=eff_id,
                blueprint=bp,
                sapience=eff_sap,
            )
        )

    char_uid = int(char.get("user_id")) if isinstance(char, dict) and char.get("user_id") else None
    off_ch = build_offering_counter_rite_choice(
        bp,
        ent,
        user_id=char_uid,
        base_dc=7 if mode == "incursion" else 6,
        quest_id=quest_id if mode != "incursion" else "",
        sub_obj_id=sub_obj_id,
        incursion_id=eff_id,
        is_story_quest=bool(is_story_quest),
    )
    if off_ch:
        if mode == "incursion":
            choices.append({
                "label": off_ch["label"][:190],
                "stat": "INT",
                "requirement": max(2, int(off_ch.get("dc", 3))),
                "mp_cost": 0,
                "intent": "anomalous_incursion_action",
                "incursion_action": "folklore_offering_rite",
                "offering_item_name": off_ch["offering_item_name"],
                "incursion_id": eff_id,
                "breach_id": eff_id,
                "sapience": eff_sap,
                "dossier_revealed": is_revealed,
                "_server_stamped": True,
            })
        else:
            choices.append({
                "label": f"{q_icon} [{prefix}] {off_ch['label']}"[:190],
                "stat": "INT",
                "requirement": max(2, int(off_ch.get("dc", 3))),
                "mp_cost": 0,
                "intent": "investigate_clue",
                "sub_intent": "folklore_offering_rite",
                "target_npc": "",
                "is_fallback": False,
                "quest_id": quest_id,
                "sub_obj_id": sub_obj_id,
                "stage_index": stage_index,
                "is_quest_action": True,
                "is_story_quest": bool(is_story_quest),
                "contract_type": contract_type,
                "approach": "folklore_offering_rite",
                "offering_item_name": off_ch["offering_item_name"],
                "gold_cost": 0,
                "dc_mod": -5,
                "sapience": eff_sap,
                "dossier_revealed": is_revealed,
                "_server_stamped": True,
            })

    for spec in specs:
        stat = spec["stat"]
        if stats_dict and stat in stats_dict:
            c_stat_val = int(stats_dict.get(stat, 5) or 5)
        elif isinstance(char, dict) and stat_col_map.get(stat) in char:
            c_stat_val = int(char.get(stat_col_map[stat], 5) or 5)
        else:
            c_stat_val = 6

        dossier_dc_reduction = 2 if is_revealed else 0
        taboo_dc_reduction = 1 if (is_revealed and stat in exploit_stats) else 0
        total_reduction = dossier_dc_reduction + taboo_dc_reduction
        prank_add = prank_dc_pen if (prank_dc_pen < 0 or not (is_revealed and stat in exploit_stats)) else 0
        verb_str = _build_contextual_containment_verb(spec, ent, bp, eff_sap, is_revealed, stat, exploit_stats)

        if mode == "incursion":
            req = min(12, max(3, 7 - total_reduction) + prank_add)
            lbl = f"{spec['icon']} [{spec['tag']}] {verb_str} (Optional)"
            choices.append({
                "label": lbl[:190],
                "stat": stat,
                "requirement": req,
                "mp_cost": 0,
                "intent": "anomalous_incursion_action",
                "incursion_action": spec["incursion_action"],
                "incursion_id": eff_id,
                "breach_id": eff_id,
                "sapience": eff_sap,
                "dossier_revealed": is_revealed,
                "taboo_exploited_stat": bool(stat in exploit_stats),
                "_server_stamped": True,
            })
        else:
            base_req = max(4, min(8, c_stat_val))
            req = max(1, base_req - total_reduction)
            eff_dc_mod = dc_mod + prank_add
            if eff_dc_mod > 0:
                req = min(12, req + eff_dc_mod)
            lbl = f"{q_icon} [{prefix}] [{spec['tag']}] {verb_str} ({stat})"
            choices.append({
                "label": lbl[:190],
                "stat": stat,
                "requirement": req,
                "mp_cost": 0,
                "intent": "investigate_clue",
                "sub_intent": "",
                "target_npc": "",
                "is_fallback": False,
                "quest_id": quest_id,
                "sub_obj_id": sub_obj_id,
                "stage_index": stage_index,
                "is_quest_action": True,
                "is_story_quest": bool(is_story_quest),
                "contract_type": contract_type,
                "approach": spec["quest_approach"],
                "gold_cost": 0,
                "dc_mod": eff_dc_mod,
                "sapience": eff_sap,
                "dossier_revealed": is_revealed,
                "taboo_exploited_stat": bool(stat in exploit_stats),
                "_server_stamped": True,
            })
    return choices


def _resolve_active_non_hostile_anomaly_context(
    session_id: Optional[int],
    *,
    session: Optional[Dict[str, Any]] = None,
    entity_name: str = "",
    quest_id: str = "",
    sub_obj_id: Optional[int] = None,
    incursion_id: str = "",
    breach_id: str = "",
    location_str: str = "",
    node_id: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Resolves the active non-hostile anomaly at the player's location (from either an active Quest
    containment waypoint or an unresolved Daily Anomaly Breach) and returns its unified metadata.
    """
    sess = session if isinstance(session, dict) else (db.get_session(session_id) if session_id else {}) or {}
    sid = int(session_id or sess.get("id") or 0)
    eff_loc = str(location_str or sess.get("current_location") or "").strip()
    eff_nid = str(node_id or sess.get("current_node_id") or "").strip()
    eff_inc = str(incursion_id or breach_id or "").strip()
    ent_low = str(entity_name or "").strip().lower()

    # 1. Explicit quest_id or local quest containment waypoint
    if sid:
        try:
            from mechanics.world.waypoints.core import get_active_local_quest_hooks
            candidate_wps: List[Dict[str, Any]] = []
            if quest_id:
                q_row = db.get_quest_by_id(sid, quest_id) or {}
                if str(q_row.get("status") or "").lower() == "active":
                    all_wps = db.get_quest_waypoints(sid, quest_id, sub_obj_id) or []
                    act_wp = db.get_active_waypoint(sid, quest_id, sub_obj_id) or (all_wps[-1] if all_wps else {})
                    wp_merged = {**q_row, **(act_wp or {}), "quest_id": quest_id, "sub_obj_id": sub_obj_id}
                    if is_non_hostile_entity_containment_waypoint(wp_merged, all_wps=all_wps, quest=q_row):
                        candidate_wps.append(wp_merged)
            if not candidate_wps and eff_loc:
                for w in (get_active_local_quest_hooks(sid, eff_loc) or []):
                    w_qid = str(w.get("quest_id") or "")
                    w_all = db.get_quest_waypoints(sid, w_qid, w.get("sub_obj_id")) or []
                    if is_non_hostile_entity_containment_waypoint(w, all_wps=w_all):
                        candidate_wps.append(w)

            for wp in candidate_wps:
                w_qid = str(wp.get("quest_id") or "")
                q_row = db.get_quest_by_id(sid, w_qid) or wp
                q_notes = str(q_row.get("quest_notes") or wp.get("quest_notes") or "")
                if "entity_secured" in q_notes or "vault_logged:1" in q_notes:
                    continue
                ent_nm = extract_non_hostile_entity_name(q_row, wp)
                if ent_low and ent_low != ent_nm.lower() and ent_low not in ent_nm.lower() and ent_nm.lower() not in ent_low:
                    continue
                bp = parse_blueprint_from_notes(q_notes)
                sap = str((bp.get("sapience") if bp else "") or "sapient").strip().lower()
                if not bp:
                    m_sap = re.search(r"sapience:(sapient|compulsive|instinctual|non_sapient)", q_notes, re.IGNORECASE)
                    if m_sap:
                        sap = m_sap.group(1).strip().lower()
                is_rev = bool("dossier_revealed:1" in q_notes or (bp and bp.get("dossier_revealed")))
                temp = get_non_hostile_entity_temperament(
                    seed_key=w_qid,
                    quest_notes=q_notes,
                    explicit=str((bp or {}).get("non_hostile_temperament") or ""),
                )
                return {
                    "mode": "quest",
                    "entity_name": ent_nm,
                    "quest_id": w_qid,
                    "sub_obj_id": wp.get("sub_obj_id"),
                    "stage_index": int(wp.get("stage_index", 2) or 2),
                    "is_story_quest": bool(q_row.get("is_story_quest") or wp.get("is_story_quest")),
                    "contract_type": str(wp.get("completion_trigger") or "skill_check"),
                    "incursion_id": "",
                    "blueprint": bp,
                    "sapience": sap,
                    "temperament": temp,
                    "dossier_revealed": is_rev,
                }
        except Exception:
            pass

    # 2. Explicit incursion_id or active non-hostile Daily Anomaly Breach at location
    incursions = list(sess.get("daily_incursions") or sess.get("daily_breaches") or [])
    target_inc = None
    if eff_inc:
        target_inc = next(
            (inc for inc in incursions if isinstance(inc, dict) and (inc.get("incursion_id") == eff_inc or inc.get("breach_id") == eff_inc)),
            None,
        )
    if not target_inc and sid:
        target_inc = get_active_incursion_at_location(sid, location_str=eff_loc, node_id=eff_nid)
    if not target_inc and ent_low:
        target_inc = next(
            (
                inc for inc in incursions
                if isinstance(inc, dict)
                and not inc.get("resolved")
                and str(inc.get("entity_name") or "").strip().lower() == ent_low
            ),
            None,
        )
    if target_inc and not target_inc.get("resolved") and not target_inc.get("agitated") and target_inc.get("subtype") != "hostile_breach":
        ent_nm = str(target_inc.get("entity_name") or "Anomalous Entity").strip()
        if not ent_low or ent_low == ent_nm.lower() or ent_low in ent_nm.lower() or ent_nm.lower() in ent_low:
            bp = target_inc.get("anomaly_blueprint") if isinstance(target_inc.get("anomaly_blueprint"), dict) else None
            sap = str(target_inc.get("sapience") or (bp.get("sapience") if bp else "") or "sapient").strip().lower()
            inc_id_val = str(target_inc.get("incursion_id") or target_inc.get("breach_id") or "")
            temp = get_non_hostile_entity_temperament(
                seed_key=inc_id_val,
                explicit=str(target_inc.get("temperament") or (bp or {}).get("non_hostile_temperament") or ""),
            )
            is_rev = bool(target_inc.get("dossier_revealed") or (bp and bp.get("dossier_revealed")))
            return {
                "mode": "incursion",
                "entity_name": ent_nm,
                "quest_id": "",
                "sub_obj_id": None,
                "stage_index": 2,
                "is_story_quest": False,
                "contract_type": "skill_check",
                "incursion_id": inc_id_val,
                "blueprint": bp,
                "sapience": sap,
                "temperament": temp,
                "dossier_revealed": is_rev,
            }
    return None


def is_anomalous_scene_entity(
    npc_or_name: Any,
    *,
    session: Optional[Dict[str, Any]] = None,
    current_npcs: Optional[List[Any]] = None,
) -> bool:
    """Returns True if `npc_or_name` is an anomalous entity in the scene (`is_anomalous_entity: True`)."""
    if isinstance(npc_or_name, dict):
        if (
            npc_or_name.get("is_anomalous_entity")
            or str(npc_or_name.get("npc_type") or "").lower() == "anomaly"
            or str(npc_or_name.get("social_role_type") or "").lower() == "anomaly"
            or str(npc_or_name.get("anomalous_npc_tag") or "").lower() == "anomaly_entity"
        ):
            return True
        role_low = str(npc_or_name.get("role") or "").lower()
        if "non-hostile entity" in role_low or "non-hostile object" in role_low or "non-hostile phenomenon" in role_low:
            return True
        name_str = str(npc_or_name.get("name") or "").strip()
    else:
        name_str = str(npc_or_name or "").strip()

    if not name_str:
        return False
    nm_low = name_str.lower()
    npc_list = list(current_npcs or [])
    if isinstance(session, dict) and isinstance(session.get("current_npcs"), list):
        npc_list.extend(session["current_npcs"])
    for n in npc_list:
        if isinstance(n, dict) and str(n.get("name") or "").strip().lower() == nm_low:
            if (
                n.get("is_anomalous_entity")
                or str(n.get("npc_type") or "").lower() == "anomaly"
                or str(n.get("social_role_type") or "").lower() == "anomaly"
                or str(n.get("anomalous_npc_tag") or "").lower() == "anomaly_entity"
            ):
                return True
    return False


def prune_anomaly_from_scene_npcs(
    session_id: Optional[int],
    entity_name: str = "",
    *,
    extra_names: Optional[List[str]] = None,
    session: Optional[Dict[str, Any]] = None,
    persist_db: bool = True,
) -> None:
    """Removes a contained, escaped, or agitated anomaly (including any disguise alias) from `current_npcs` and `dialogue_partners`."""
    sess = session if isinstance(session, dict) else (db.get_session(session_id) if session_id else None)
    if not isinstance(sess, dict):
        return
    name_targets = {str(entity_name or "").strip().lower()} - {""}
    for ex_nm in (extra_names or []):
        ex_clean = str(ex_nm or "").strip().lower()
        if ex_clean:
            name_targets.add(ex_clean)
    changed = False
    if isinstance(sess.get("current_npcs"), list):
        new_npcs = []
        for n in sess["current_npcs"]:
            if isinstance(n, dict):
                n_nm = str(n.get("name") or "").strip().lower()
                is_anom = bool(
                    n.get("is_anomalous_entity")
                    or str(n.get("npc_type") or "").lower() == "anomaly"
                    or str(n.get("anomalous_npc_tag") or "").lower() == "anomaly_entity"
                )
                if (is_anom and (not name_targets or n_nm in name_targets)) or (name_targets and n_nm in name_targets):
                    changed = True
                    continue
            new_npcs.append(n)
        if changed:
            sess["current_npcs"] = new_npcs

    if name_targets:
        dp_single = str(sess.get("dialogue_partner") or "").strip()
        if dp_single and dp_single.lower() in name_targets:
            sess["dialogue_partner"] = None
            changed = True
        if isinstance(sess.get("dialogue_partners"), list):
            new_dps = [p for p in sess["dialogue_partners"] if str(p).strip().lower() not in name_targets]
            if len(new_dps) != len(sess["dialogue_partners"]):
                sess["dialogue_partners"] = new_dps
                sess["dialogue_partner"] = new_dps[0] if new_dps else None
                changed = True

    if changed and persist_db and session_id:
        try:
            db.update_session(
                int(session_id),
                current_npcs=sess.get("current_npcs", []),
                dialogue_partner=sess.get("dialogue_partner"),
                extra={"dialogue_partners": sess.get("dialogue_partners", [])},
            )
        except Exception:
            pass


_prune_anomaly_from_scene_npcs = prune_anomaly_from_scene_npcs


def get_blueprint_alias_names(blueprint: Optional[Dict[str, Any]], entity_name: str = "") -> List[str]:
    """Every name an anomaly may appear under in scene state: public/entity name, canonical name, and disguise alias."""
    names: List[str] = []
    bp = blueprint if isinstance(blueprint, dict) else {}
    ds = bp.get("disguise_state") if isinstance(bp.get("disguise_state"), dict) else {}
    for cand in (entity_name, bp.get("entity_name"), bp.get("name"), bp.get("canonical_name"), ds.get("disguise_alias")):
        c_clean = str(cand or "").strip()
        if c_clean and c_clean not in names:
            names.append(c_clean)
    return names


def prune_expired_incursion_anomalies_from_scene(
    session_id: Optional[int],
    incursions: Optional[List[Dict[str, Any]]],
    session: Optional[Dict[str, Any]] = None,
) -> None:
    """At midnight rollover, removes every still-unresolved breach (and disguise alias) of the expiring day from the scene."""
    alias_pool: List[str] = []
    sess = session or (db.get_session(session_id) if session_id else {}) or {}
    for inc in (incursions or []):
        if not isinstance(inc, dict) or inc.get("resolved"):
            continue
        if str(inc.get("time_window") or "") == "after_hours":
            cur_min = int(sess.get("current_minute", 480) or 480) % 1440
            if not (cur_min >= 1200 or cur_min < 360):
                continue
        for nm in get_blueprint_alias_names(inc.get("anomaly_blueprint"), str(inc.get("entity_name") or "")):
            if nm not in alias_pool:
                alias_pool.append(nm)
    if alias_pool and session_id:
        prune_anomaly_from_scene_npcs(session_id, alias_pool[0], extra_names=alias_pool[1:], persist_db=True)


def sync_non_hostile_anomaly_scene_presence(
    session_id: Optional[int],
    *,
    session: Optional[Dict[str, Any]] = None,
    location_str: str = "",
    node_id: str = "",
    persist_db: bool = False,
) -> List[Dict[str, Any]]:
    """
    Synchronizes active non-hostile anomalies at the player's current location into `session['current_npcs']`
    so they appear in the 'Present in Scene' UI with the `[👁️ Anomaly]` badge:
      - `sapient` anomalies have `talkable: True` (`Talking` badge when focused).
      - `compulsive` anomalies have `talkable: False, pattern_observable: True` (`Observing` badge when focused).
      - `instinctual` and `non_sapient` anomalies have `talkable: False, pattern_observable: False`.
      - Automatically prunes stale anomalies from `current_npcs` when contained, escaped, agitated into
        `nearby_enemies`, or when the player moves to another location.
    """
    sess = session if isinstance(session, dict) else (db.get_session(session_id) if session_id else {}) or {}
    sid = int(session_id or sess.get("id") or 0)
    scen_key = str(sess.get("scenario") or "")
    if not scenario_data.is_anomalous_incursions_scenario(scen_key):
        return list(sess.get("current_npcs") or [])

    cur_enemies = sess.get("nearby_enemies") or []
    in_combat_now = any(isinstance(e, dict) and int(e.get("hp", 0) or 0) > 0 for e in cur_enemies)

    anom_ctx = None
    if not in_combat_now:
        anom_ctx = _resolve_active_non_hostile_anomaly_context(
            sid,
            session=sess,
            location_str=location_str,
            node_id=node_id,
        )

    cur_npcs = list(sess.get("current_npcs") or [])
    cleaned_npcs: List[Any] = []
    pruned_anom_names: set[str] = set()
    for n in cur_npcs:
        if isinstance(n, dict) and (
            n.get("is_anomalous_entity")
            or str(n.get("npc_type") or "").lower() == "anomaly"
            or str(n.get("anomalous_npc_tag") or "").lower() == "anomaly_entity"
        ):
            n_nm_low = str(n.get("name") or "").strip().lower()
            if n_nm_low:
                pruned_anom_names.add(n_nm_low)
            continue
        cleaned_npcs.append(n)

    active_focusable_anom_low = ""
    dp_changed = False
    if anom_ctx:
        bp = anom_ctx.get("blueprint") or {}
        is_rev_anom = bool(anom_ctx.get("dossier_revealed") or bp.get("dossier_revealed"))
        is_disg = is_blueprint_disguised(bp, dossier_revealed=is_rev_anom)
        ent_nm = (
            get_public_anomaly_name(bp, dossier_revealed=is_rev_anom, fallback=anom_ctx["entity_name"])
            if is_disg
            else anom_ctx["entity_name"]
        )
        eff_sap = str(anom_ctx.get("sapience") or "sapient").strip().lower()
        is_talkable = bool(eff_sap == "sapient")
        is_pattern_observable = bool(eff_sap == "compulsive")
        can_focus_interact = bool(is_talkable or is_pattern_observable)
        if can_focus_interact:
            active_focusable_anom_low = ent_nm.strip().lower()
        else:
            pruned_anom_names.add(ent_nm.strip().lower())
        temp = str(anom_ctx.get("temperament") or "timid").strip().lower()
        a_type = str(bp.get("type") or "entity").strip().title()
        form_lbl = str(bp.get("form_label") or "Anomalous Manifestation").strip()
        if eff_sap == "sapient":
            sap_disp = "Sapient — Can Converse"
        elif eff_sap == "compulsive":
            sap_disp = "Compulsive — Pattern-Bound"
        elif eff_sap == "instinctual":
            sap_disp = "Instinctual — Non-Verbal"
        else:
            sap_disp = "Non-Sapient — Automaton/Hazard"
        temp_disp_map = {
            "timid": "Timid / Skittish",
            "volatile": "Volatile / Territorial",
            "mischievous": "Mischievous / Trickster",
            "spook": "Spook / Startle-Seeker",
        }
        temp_disp = temp_disp_map.get(temp, "Timid / Skittish")
        dp_now = str(sess.get("dialogue_partner") or "").strip().lower() == ent_nm.lower()
        disg_cover = str((bp.get("disguise_state") or {}).get("cover_desc") or "")
        anom_entry = {
            "name": ent_nm,
            "role": (
                f"[Uncanny Presence] ({sap_disp})"
                if is_disg
                else f"Non-Hostile {a_type} • {form_lbl} ({sap_disp})"
            ),
            "description": (
                disg_cover
                if (is_disg and disg_cover)
                else str(
                    bp.get("sensory_omen")
                    or bp.get("description")
                    or f"An active non-hostile {form_lbl.lower()} ({temp_disp})."
                )
            ),
            "disposition": "neutral",
            "mood": temp_disp,
            "is_anomalous_entity": True,
            "is_disguised": is_disg,
            "uncanny_presence": is_disg,
            "npc_type": "anomaly",
            "social_role_type": "anomaly",
            "anomalous_npc_tag": "anomaly_entity",
            "sapience": eff_sap,
            "talkable": is_talkable,
            "pattern_observable": is_pattern_observable,
            "temperament": temp,
            "quest_id": str(anom_ctx.get("quest_id") or ""),
            "sub_obj_id": anom_ctx.get("sub_obj_id"),
            "incursion_id": str(anom_ctx.get("incursion_id") or ""),
            "dossier_revealed": is_rev_anom,
            "stage_role": "active_partner" if (dp_now and can_focus_interact) else "room_bystander",
        }
        if sid and isinstance(bp, dict) and (bp.get("blueprint_id") or bp.get("codex_id")):
            anom_sight_key = str(anom_ctx.get("incursion_id") or bp.get("blueprint_id") or bp.get("codex_id") or ent_nm)
            sighted_set = set(sess.get("_sighted_anomalies") or [])
            if anom_sight_key not in sighted_set:
                sighted_set.add(anom_sight_key)
                try:
                    db.update_session(sid, extra={"_sighted_anomalies": list(sighted_set)})
                    db.record_session_anomaly_field_log(
                        sid,
                        bp,
                        stage="sighted",
                        location=str(sess.get("current_location") or ""),
                    )
                    if bp.get("codex_id") and not is_disg:
                        db.record_folklore_codex_progress(
                            db.get_session_participant_user_ids(sid),
                            str(bp["codex_id"]),
                            stage="sighted",
                        )
                except Exception:
                    pass
        if not any(
            isinstance(x, dict) and str(x.get("name") or "").strip().lower() == ent_nm.lower()
            for x in cleaned_npcs
        ):
            cleaned_npcs.append(anom_entry)

    stale_anom_dps = {nm for nm in pruned_anom_names if nm and nm != active_focusable_anom_low}
    if stale_anom_dps:
        dp_cur = str(sess.get("dialogue_partner") or "").strip()
        if dp_cur and dp_cur.lower() in stale_anom_dps:
            sess["dialogue_partner"] = None
            dp_changed = True
        if isinstance(sess.get("dialogue_partners"), list):
            filtered_dps = [p for p in sess["dialogue_partners"] if str(p).strip().lower() not in stale_anom_dps]
            if len(filtered_dps) != len(sess["dialogue_partners"]):
                sess["dialogue_partners"] = filtered_dps
                sess["dialogue_partner"] = filtered_dps[0] if filtered_dps else None
                dp_changed = True

    sess["current_npcs"] = cleaned_npcs
    if persist_db and sid:
        try:
            if dp_changed:
                db.update_session(
                    sid,
                    current_npcs=cleaned_npcs,
                    dialogue_partner=sess.get("dialogue_partner"),
                    extra={"dialogue_partners": sess.get("dialogue_partners", [])},
                )
            else:
                db.update_session(sid, current_npcs=cleaned_npcs)
        except Exception:
            pass
    return cleaned_npcs


def build_sapient_anomaly_dialogue_choices(
    entity_name: str,
    *,
    session_id: Optional[int] = None,
    session: Optional[Dict[str, Any]] = None,
    char: Optional[Dict[str, Any]] = None,
    quest_id: str = "",
    sub_obj_id: Optional[int] = None,
    incursion_id: str = "",
    breach_id: str = "",
    blueprint: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Builds the specialized interaction submenu for `sapient` (Lore Dialogue) and `compulsive` (Pattern Study) anomalies:
      - 3 strike-free Lore Inquiry (`sapient`) or Ritual Pattern Observation (`compulsive`) prompts
        that automatically reveal the Anomaly Dossier (`dossier_revealed = True`, `-2`/`-3` DC containment bonus).
      - The 4 contextual Containment choices.
      - Standardized FREE exit option (`Leave conversation with ...` or `Step back from observing ...`).
    """
    anom_ctx = _resolve_active_non_hostile_anomaly_context(
        session_id,
        session=session,
        entity_name=entity_name,
        quest_id=quest_id,
        sub_obj_id=sub_obj_id,
        incursion_id=incursion_id,
        breach_id=breach_id,
    )
    ent = str((anom_ctx or {}).get("entity_name") or entity_name or "the Anomalous Entity").strip()
    bp = blueprint or ((anom_ctx or {}).get("blueprint") if anom_ctx else None) or {}
    eff_sap = str((anom_ctx or {}).get("sapience") or bp.get("sapience") or "sapient").strip().lower()
    if eff_sap not in ("sapient", "compulsive"):
        eff_sap = "sapient"
    mode = str((anom_ctx or {}).get("mode") or ("incursion" if (incursion_id or breach_id) else "quest"))
    eff_qid = str(quest_id or (anom_ctx or {}).get("quest_id") or "")
    eff_so_id = sub_obj_id if sub_obj_id is not None else (anom_ctx or {}).get("sub_obj_id")
    eff_inc = str(incursion_id or breach_id or (anom_ctx or {}).get("incursion_id") or "")
    is_story = bool((anom_ctx or {}).get("is_story_quest"))
    stage_idx = int((anom_ctx or {}).get("stage_index", 2) or 2)
    is_rev = bool((anom_ctx or {}).get("dossier_revealed") or bp.get("dossier_revealed"))

    form_lbl = (
        "uncanny figure"
        if is_blueprint_disguised(bp, dossier_revealed=is_rev)
        else str(bp.get("form_label") or "anomalous manifestation").strip().lower()
    )
    if eff_sap == "compulsive":
        inquiry_specs = [
            (
                "anomaly_pattern_loop",
                f"👁️ [Vocal / Gesture Loop] Listen closely to {ent}'s repetitive phrases and count its exact cadence",
            ),
            (
                "anomaly_pattern_trigger",
                f"🔍 [Trigger & Reset] Observe what interrupts or resets this {form_lbl}'s ritual script",
            ),
            (
                "anomaly_pattern_courtesy",
                f"🕯️ [Courtesy & Taboo Test] Study the folklore threshold or rule binding {ent} to this spot",
            ),
        ]
        exit_lbl = f"Step back from observing {ent}"
    else:
        inquiry_specs = [
            (
                "anomaly_inquiry_origins",
                f"💬 [Origins & Folklore] Ask {ent} about its origins and how this {form_lbl} manifested here",
            ),
            (
                "anomaly_inquiry_nature",
                f"🔍 [Nature & Taboo] Question {ent} about its anomalous nature and what agitates its resonance",
            ),
            (
                "anomaly_inquiry_motive",
                f"🧭 [Motive & Bargain] Ask {ent} what it seeks here and what would convince it to yield peacefully",
            ),
        ]
        exit_lbl = f"Leave conversation with {ent}"

    inquiry_choices: List[Dict[str, Any]] = []
    if has_active_dialogue_trap(bp):
        raw_trap_choices = build_dialogue_trap_choices(
            bp,
            ent,
            quest_id=eff_qid if mode != "incursion" else "",
            sub_obj_id=eff_so_id,
            incursion_id=eff_inc,
            is_story_quest=is_story,
        )
        for tc in raw_trap_choices:
            t_act = str(tc.get("incursion_action") or "question_trap_evasive")
            if mode == "incursion":
                inquiry_choices.append({
                    "label": tc["label"][:190],
                    "stat": "FREE",
                    "requirement": 0,
                    "mp_cost": 0,
                    "intent": "dialogue_init",
                    "target_npc": ent,
                    "incursion_action": t_act,
                    "trap_choice_kind": tc.get("trap_choice_kind", ""),
                    "incursion_id": eff_inc,
                    "breach_id": eff_inc,
                    "sapience": eff_sap,
                    "is_anomaly_inquiry": True,
                    "_priority_slot": True,
                    "_server_stamped": True,
                })
            else:
                inquiry_choices.append({
                    "label": tc["label"][:190],
                    "stat": "FREE",
                    "requirement": 0,
                    "mp_cost": 0,
                    "intent": "dialogue_init",
                    "sub_intent": t_act,
                    "target_npc": ent,
                    "quest_id": eff_qid,
                    "sub_obj_id": eff_so_id,
                    "stage_index": stage_idx,
                    "is_quest_action": False,
                    "is_story_quest": is_story,
                    "approach": t_act,
                    "incursion_action": t_act,
                    "trap_choice_kind": tc.get("trap_choice_kind", ""),
                    "sapience": eff_sap,
                    "is_anomaly_inquiry": True,
                    "_priority_slot": True,
                    "_server_stamped": True,
                })
    else:
        for inq_key, inq_lbl in inquiry_specs:
            if mode == "incursion":
                inquiry_choices.append({
                    "label": inq_lbl[:190],
                    "stat": "FREE",
                    "requirement": 0,
                    "mp_cost": 0,
                    "intent": "dialogue_init",
                    "target_npc": ent,
                    "incursion_action": inq_key,
                    "incursion_id": eff_inc,
                    "breach_id": eff_inc,
                    "sapience": eff_sap,
                    "is_anomaly_inquiry": True,
                    "_priority_slot": False,
                    "_server_stamped": True,
                })
            else:
                inquiry_choices.append({
                    "label": inq_lbl[:190],
                    "stat": "FREE",
                    "requirement": 0,
                    "mp_cost": 0,
                    "intent": "dialogue_init",
                    "sub_intent": inq_key,
                    "target_npc": ent,
                    "quest_id": eff_qid,
                    "sub_obj_id": eff_so_id,
                    "stage_index": stage_idx,
                    "is_quest_action": False,
                    "is_story_quest": is_story,
                    "approach": inq_key,
                    "incursion_action": inq_key,
                    "sapience": eff_sap,
                    "is_anomaly_inquiry": True,
                    "_priority_slot": False,
                    "_server_stamped": True,
                })

    containment_choices = build_non_hostile_narrative_choices(
        ent,
        mode=mode,
        char=char,
        quest_id=eff_qid,
        sub_obj_id=eff_so_id,
        stage_index=stage_idx,
        is_story_quest=is_story,
        incursion_id=eff_inc,
        breach_id=eff_inc,
        sapience=eff_sap,
        blueprint=bp if bp else None,
        dossier_revealed=is_rev,
        session_id=session_id,
        include_converse=False,
    )

    exit_choice = {
        "label": exit_lbl,
        "stat": "NONE",
        "requirement": 0,
        "mp_cost": 0,
        "is_fallback": False,
        "intent": "dialogue_exit",
        "ends_dialogue": True,
        "_pinned_dialogue_exit": True,
        "_server_stamped": True,
    }
    return inquiry_choices + containment_choices + [exit_choice]


def resolve_anomaly_dialogue_inquiry(
    session_id: int,
    *,
    entity_name: str = "",
    quest_id: str = "",
    sub_obj_id: Optional[int] = None,
    incursion_id: str = "",
    breach_id: str = "",
    inquiry_type: str = "anomaly_inquiry",
    player_text: str = "",
    user_id: Optional[int] = None,
    session: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Resolves a strike-free Lore Inquiry (`sapient`) or Ritual Pattern Study (`compulsive`) with a non-hostile anomaly:
      - Rejects interaction if the anomaly is `instinctual` or `non_sapient`.
      - Automatically unseals the Anomaly Dossier (`reveal_anomaly_dossier`), unlocking the `-2` DC
        containment bonus (`-3` DC on Taboo `exploit_stats`).
      - Sets `dialogue_partner = entity_name` (rendered as `Talking` for `sapient`, `Observing` for `compulsive`).
      - For `compulsive` entities, enforces strict non-rational repetition/mimicry directives (zero Q&A small talk).
    """
    sess = session if isinstance(session, dict) else (db.get_session(session_id) or {})
    anom_ctx = _resolve_active_non_hostile_anomaly_context(
        session_id,
        session=sess,
        entity_name=entity_name,
        quest_id=quest_id,
        sub_obj_id=sub_obj_id,
        incursion_id=incursion_id,
        breach_id=breach_id,
    )
    ent = str((anom_ctx or {}).get("entity_name") or entity_name or "the Anomalous Entity").strip()
    eff_qid = str(quest_id or (anom_ctx or {}).get("quest_id") or "")
    eff_inc = str(incursion_id or breach_id or (anom_ctx or {}).get("incursion_id") or "")
    bp = ((anom_ctx or {}).get("blueprint") if anom_ctx else None) or {}
    eff_sap = str((anom_ctx or {}).get("sapience") or bp.get("sapience") or "sapient").strip().lower()

    if eff_sap not in ("sapient", "compulsive"):
        return {
            "success": False,
            "talkable": False,
            "pattern_observable": False,
            "resolved": False,
            "sapience": eff_sap,
            "message": (
                f"⚠️ **{ent}** is **{eff_sap.replace('_', '-').title()}** and lacks human speech or ritual loop scripts—"
                f"use field containment tactics instead of verbal conversation."
            ),
        }

    inq_low = str(inquiry_type or "anomaly_inquiry").strip().lower()
    if has_active_dialogue_trap(bp) and inq_low in ("converse", "study_pattern") and not str(player_text or "").strip():
        pub_ent = get_public_anomaly_name(bp, fallback=ent)
        dt_prompt = str((bp.get("dialogue_trap") or {}).get("prompt_question") or "Do you recognize what I am?")
        sess["dialogue_partner"] = pub_ent
        sess["dialogue_partners"] = [pub_ent]
        sync_non_hostile_anomaly_scene_presence(session_id, session=sess, persist_db=False)
        try:
            db.update_session(
                session_id,
                current_npcs=sess.get("current_npcs", []),
                dialogue_partner=pub_ent,
                extra={"dialogue_partners": [pub_ent]},
            )
        except Exception:
            pass
        trap_open_msg = (
            f"❓ **Folklore Riddle Trap:** **{pub_ent}** fixes an unblinking gaze on you and asks: *\"{dt_prompt}\"* "
            f"(Beware answering a direct Yes or No—folklore riddles often punish both binary answers!)"
        )
        return {
            "success": True,
            "question_trap_presented": True,
            "talkable": eff_sap == "sapient",
            "pattern_observable": eff_sap == "compulsive",
            "sapience": eff_sap,
            "resolved": False,
            "dossier_revealed": bool(bp.get("dossier_revealed")),
            "dialogue_partner": pub_ent,
            "message": trap_open_msg,
            "directive": (
                f"[MANDATORY FOLKLORE RIDDLE TRAP OPENING]:\n"
                f"- **{pub_ent}** confronts the player with a binding folklore question-trap: \"{dt_prompt}\".\n"
                f"- Keep **{pub_ent}**'s true identity veiled if disguised, and end the turn waiting for the player's answer (`dialogue_partner` = `{pub_ent}`)."
            ),
        }

    trap_kind = (
        "evasive"
        if "evasive" in inq_low
        else ("trap_yes" if "trap_yes" in inq_low else ("trap_no" if "trap_no" in inq_low else ""))
    )
    pre_trap_eval: Dict[str, Any] = {}
    if (trap_kind or player_text) and isinstance((bp or {}).get("dialogue_trap"), dict) and not (bp or {}).get("dialogue_trap", {}).get("resolved"):
        pre_trap_eval = evaluate_dialogue_trap_response(bp, player_text=player_text, trap_choice_kind=trap_kind)
    trap_sprung = bool(pre_trap_eval.get("matched") and pre_trap_eval.get("triggered_trap"))

    # Falling into a binary Question-Trap never rewards the player with a Dossier reveal / unmasking
    rev_res = {} if trap_sprung else reveal_anomaly_dossier(
        session_id=session_id,
        quest_id=eff_qid,
        incursion_id=eff_inc,
        breach_id=eff_inc,
    )
    bp = rev_res.get("blueprint") or bp or {}
    d_sum = str(rev_res.get("dossier_summary") or "Anomaly Taboo and Containment Protocol unsealed.")
    unmasked_from = str(rev_res.get("unmasked_from") or "").strip()
    if rev_res.get("unmask_notice") and bp.get("canonical_name"):
        ent = str(bp["canonical_name"])
    if trap_sprung:
        ent = get_public_anomaly_name(bp, dossier_revealed=bool(bp.get("dossier_revealed")), fallback=ent)

    if session_id:
        fresh_after_rev = db.get_session(session_id) or {}
        if "daily_incursions" in fresh_after_rev:
            sess["daily_incursions"] = fresh_after_rev["daily_incursions"]
        if "daily_breaches" in fresh_after_rev:
            sess["daily_breaches"] = fresh_after_rev["daily_breaches"]

    sess["dialogue_partner"] = ent
    sess["dialogue_partners"] = [ent]
    sync_non_hostile_anomaly_scene_presence(session_id, session=sess, persist_db=False)
    try:
        db.update_session(
            session_id,
            current_npcs=sess.get("current_npcs", []),
            dialogue_partner=ent,
            extra={"dialogue_partners": [ent]},
        )
    except Exception:
        pass

    form_lbl = str(bp.get("form_label") or "anomalous manifestation")
    trad_lbl = str(bp.get("folklore_tradition") or "urban_legend").replace("_", " ").title()
    omen_str = str(bp.get("sensory_omen") or "A localized distortion hums around the entity.")
    taboo_name = str(bp.get("taboo_name") or (bp.get("taboo") or {}).get("name") or "Folklore Taboo")
    taboo_rule = str(bp.get("taboo_rule") or (bp.get("taboo") or {}).get("taboo_rule") or "Avoid sudden aggressive force.")
    proto_str = str(bp.get("containment_protocol") or (bp.get("taboo") or {}).get("containment_protocol") or "Approach with calm, measured protocol.")

    if pre_trap_eval and isinstance(bp.get("dialogue_trap"), dict):
        trap_eval = pre_trap_eval
        if trap_eval.get("matched"):
            bp["dialogue_trap"] = {**dict(bp["dialogue_trap"]), "resolved": True}
            lead_uid_trap = int(user_id or sess.get("host_user_id") or 1)
            if eff_inc:
                incs_t = list((db.get_session(session_id) or sess).get("daily_incursions") or [])
                for inc_t in incs_t:
                    if isinstance(inc_t, dict) and (inc_t.get("incursion_id") == eff_inc or inc_t.get("breach_id") == eff_inc):
                        inc_t["anomaly_blueprint"] = bp
                        if trap_eval.get("satisfied"):
                            inc_t["prank_dc_penalty"] = -3
                        elif trap_eval.get("triggered_trap"):
                            # A sprung trap is a warning strike; it never silently exhausts the final escape strike
                            max_st = int(inc_t.get("max_strikes", 2) or 2)
                            inc_t["strikes"] = min(
                                max(0, max_st - 1),
                                int(inc_t.get("strikes", 0) or 0) + int(trap_eval.get("strike_delta", 1) or 1),
                            )
                db.update_session(session_id, extra={"daily_incursions": incs_t, "daily_breaches": None})
                sess["daily_incursions"] = incs_t
                sess["daily_breaches"] = incs_t
            elif eff_qid:
                q_t = db.get_quest_by_id(session_id, eff_qid) or {}
                notes_t = str(q_t.get("quest_notes") or "")
                new_tok = serialize_blueprint_note(bp).split("|", 1)[0]
                cleaned_t = re.sub(r"anomaly_(?:bp|blueprint):[A-Za-z0-9+/=_-]+", new_tok, notes_t)
                with db.get_conn() as conn:
                    conn.execute(
                        "UPDATE quests SET quest_notes = ? WHERE session_id = ? AND quest_id = ?",
                        (cleaned_t, session_id, eff_qid),
                    )
            if trap_eval.get("triggered_trap") and lead_uid_trap:
                try:
                    db.apply_hp_mp_delta(lead_uid_trap, hp_delta=-int(trap_eval.get("backlash_damage", 8) or 8))
                except Exception:
                    pass
            trap_msg = (
                f"{trap_eval['message']} 🔍 **Anomaly Dossier Unsealed:** {d_sum}"
                if not trap_sprung
                else f"{trap_eval['message']} *(Its true nature remains veiled.)*"
            )
            return {
                "success": bool(trap_eval.get("satisfied")),
                "question_trap_evaluated": True,
                "trap_satisfied": bool(trap_eval.get("satisfied")),
                "trap_triggered": bool(trap_eval.get("triggered_trap")),
                "talkable": eff_sap == "sapient",
                "pattern_observable": eff_sap == "compulsive",
                "sapience": eff_sap,
                "resolved": False,
                "dossier_revealed": not trap_sprung,
                "dialogue_partner": ent,
                "unmasked_from": unmasked_from,
                "dossier_summary": "" if trap_sprung else d_sum,
                "message": trap_msg,
                "directive": (
                    f"[MANDATORY FOLKLORE QUESTION-TRAP OUTCOME]: {trap_eval['message']} "
                    f"Narrate how **{ent}** reacts to the player's answer without leaking raw HP or DC integers."
                ),
            }

    paradox_obs = evaluate_omen_paradox(bp, dossier_revealed=True, is_observation=True)
    paradox_suffix = f" {paradox_obs['note']}" if paradox_obs.get("has_paradox") else ""
    if eff_sap == "compulsive":
        if "loop" in inq_low:
            obs_focus = f"its clockwork repetition cadence as a {form_lbl} rooted in {trad_lbl} lore ({omen_str})"
        elif "trigger" in inq_low:
            obs_focus = f"what interrupts or agitates its ritual loop (**{taboo_name}**: *{taboo_rule}*)"
        elif "courtesy" in inq_low:
            obs_focus = f"the exact folklore counter-script that satisfies its compulsion (*{proto_str}*)"
        else:
            obs_focus = f"its repetitive {form_lbl.lower()} loop, **{taboo_name}** (*{taboo_rule}*), and ritual counter-script (*{proto_str}*)"

        msg = (
            f"👁️ **Studied {ent}'s Ritual Pattern (Strike-Free Observation):** Watching the pattern-bound {form_lbl.lower()} "
            f"from a careful distance, you decipher {obs_focus}. 🔍 **Anomaly Dossier Unsealed:** {d_sum}{paradox_suffix}"
        )
        directive = (
            f"[MANDATORY COMPULSIVE ANOMALY PATTERN STUDY & DOSSIER REVEAL]:\n"
            f"- The player is quietly observing the **Compulsive (Pattern-Bound)** non-hostile anomaly **{ent}** ({form_lbl}, {trad_lbl}).\n"
            f"- Focus of observation: {obs_focus}.\n"
            f"- CRITICAL PROSE RULE: **{ent}** is NOT rationally sapient and CANNOT hold a normal Q&A conversation or explain its backstory in lucid prose!\n"
            f"- Depict **{ent}** ONLY repeating eerie scripted phrases, counting, mimicking sounds, or performing clockwork folklore gestures that reveal **{taboo_name}** ({taboo_rule}) and its ritual counter-protocol ({proto_str}) without leaking raw game numbers or DC stats.\n"
            f"- Keep `dialogue_partner` set to `{ent}` while observing; the anomaly is NOT yet contained until the player executes a containment action."
        )
        return {
            "success": True,
            "talkable": False,
            "pattern_observable": True,
            "sapience": "compulsive",
            "resolved": False,
            "dossier_revealed": True,
            "dialogue_partner": ent,
            "unmasked_from": unmasked_from,
            "dossier_summary": d_sum,
            "message": msg,
            "directive": directive,
        }

    if "origin" in inq_low:
        topic_focus = f"its origins as a {form_lbl} rooted in {trad_lbl} lore ({omen_str})"
    elif "nature" in inq_low or "taboo" in inq_low:
        topic_focus = f"its anomalous nature and **{taboo_name}** (*{taboo_rule}*)"
    elif "motive" in inq_low or "bargain" in inq_low:
        topic_focus = f"why it lingers at this anchor point and the terms required for peaceful containment (*{proto_str}*)"
    else:
        topic_focus = f"its origins ({form_lbl}), **{taboo_name}** (*{taboo_rule}*), and peaceful containment terms (*{proto_str}*)"

    msg = (
        f"💬 **Conversed with {ent} (Strike-Free Lore Inquiry):** Through direct dialogue with the sapient {form_lbl.lower()}, "
        f"you uncover {topic_focus}. 🔍 **Anomaly Dossier Unsealed:** {d_sum}{paradox_suffix}"
    )
    directive = (
        f"[MANDATORY SAPIENT ANOMALY DIALOGUE & DOSSIER REVEAL]:\n"
        f"- The player is conversing directly with the sapient non-hostile anomaly **{ent}** ({form_lbl}, {trad_lbl}).\n"
        f"- Focus of inquiry: {topic_focus}.\n"
        f"- Voice **{ent}** in-character as an eerie, otherworldly yet articulate {form_lbl.lower()}—NEVER as a mundane human peer making small talk.\n"
        f"- Have **{ent}** reveal its nature, taboo (**{taboo_name}**: {taboo_rule}), and what would convince it to yield peacefully ({proto_str}) without leaking raw game numbers or DC stats.\n"
        f"- Keep `dialogue_partner` set to `{ent}`; the anomaly is NOT yet contained until the player executes a containment action."
    )
    return {
        "success": True,
        "talkable": True,
        "pattern_observable": False,
        "sapience": "sapient",
        "resolved": False,
        "dossier_revealed": True,
        "dialogue_partner": ent,
        "unmasked_from": unmasked_from,
        "dossier_summary": d_sum,
        "message": msg,
        "directive": directive,
    }


def record_contained_anomaly_to_vault_log(
    session_id: int,
    entity_name: str,
    category_tag: str,
    subtype: str,
    location: str,
    containment_note: str = "",
    resolution_method: str = "Pacified & Sealed",
    user_id: Optional[int] = None,
    quest_id: str = "",
    sub_obj_id: Optional[int] = None,
    blueprint: Optional[Dict[str, Any]] = None,
    incursion_id: str = "",
) -> Dict[str, Any]:
    """
    Appends a secured Non-Hostile Entity or Altered Item/Phenomenon to `session['contained_anomalies_log']`
    for display in the Containment Vaults, Reliquary Pagoda, Private Vault, and Agent Dossier UI.
    Also ratchets the account-wide `user_folklore_codex` + session `anomaly_field_log` & cooldowns!
    """
    from mechanics.social.factions import get_anomalous_faction_state

    sess = db.get_session(session_id) or {}
    bp_resolved = dict(blueprint) if isinstance(blueprint, dict) else None
    if bp_resolved is None and quest_id:
        q_v = db.get_quest_by_id(session_id, quest_id) or {}
        bp_resolved = parse_blueprint_from_notes(str(q_v.get("quest_notes") or ""))
    if bp_resolved is None:
        for inc_v in (sess.get("daily_incursions") or sess.get("daily_breaches") or []):
            if not isinstance(inc_v, dict):
                continue
            if (incursion_id and (inc_v.get("incursion_id") == incursion_id or inc_v.get("breach_id") == incursion_id)) or (
                str(inc_v.get("entity_name") or "").strip().lower() == str(entity_name or "").strip().lower()
            ):
                if isinstance(inc_v.get("anomaly_blueprint"), dict):
                    bp_resolved = dict(inc_v["anomaly_blueprint"])
                break

    orig_entity_name = str(entity_name or "").strip()
    disguise_alias_prune = ""
    if isinstance(bp_resolved, dict):
        disguise_alias_prune = str((bp_resolved.get("disguise_state") or {}).get("disguise_alias") or "").strip()
        bp_resolved, _ = unmask_blueprint_disguise(bp_resolved)
        if bp_resolved.get("canonical_name"):
            entity_name = str(bp_resolved["canonical_name"])
        try:
            db.record_session_anomaly_field_log(
                session_id,
                bp_resolved,
                stage="contained",
                location=location,
                resolution_method=resolution_method,
            )
            if bp_resolved.get("codex_id"):
                uids_v = db.get_session_participant_user_ids(session_id) or ([int(user_id)] if user_id else [])
                db.record_folklore_codex_progress(uids_v, str(bp_resolved["codex_id"]), stage="contained")
                db.retire_or_cooldown_folklore_in_session(
                    session_id,
                    str(bp_resolved["codex_id"]),
                    uniqueness=str(bp_resolved.get("uniqueness") or "species"),
                    current_day=int(sess.get("current_day") or sess.get("in_game_day") or 1),
                    cooldown_days=int(bp_resolved.get("cooldown_days", 4) or 4),
                )
                sess = db.get_session(session_id) or sess
        except Exception:
            pass

    log_list = list(sess.get("contained_anomalies_log") or [])
    if quest_id:
        for existing_entry in log_list:
            if (
                isinstance(existing_entry, dict)
                and str(existing_entry.get("quest_id") or "") == str(quest_id)
                and existing_entry.get("sub_obj_id") == sub_obj_id
            ):
                return existing_entry

    fac_state = get_anomalous_faction_state(session_id, user_id=user_id)
    arch = str(fac_state.get("faction_archetype_key") or "public_agency")

    if arch == "monastic_order":
        vault_facility = "Inner Sanctum & Reliquary Pagoda"
    elif arch in ("private_agency_1", "private_agency_2"):
        vault_facility = f"{fac_state.get('joined_faction_name', 'Syndicate')} Executive Containment Vault"
    else:
        vault_facility = "Subterranean Containment & Quarantine Vaults"

    entry = {
        "entry_id": f"vault_{len(log_list) + 1}_{int(time.time())}",
        "entity_name": entity_name,
        "category_tag": category_tag,
        "subtype": subtype,
        "captured_at": location,
        "location": location,
        "day_captured": int(sess.get("current_day", 1) or 1),
        "turn_captured": _resolve_session_turn_number(session_id, sess),
        "resolution_method": resolution_method,
        "vault_facility": vault_facility,
        "containment_note": containment_note or f"Safely contained at {vault_facility}.",
    }
    if quest_id:
        entry["quest_id"] = str(quest_id)
        if sub_obj_id is not None:
            entry["sub_obj_id"] = sub_obj_id
    if isinstance(bp_resolved, dict):
        if bp_resolved.get("codex_id"):
            entry["codex_id"] = str(bp_resolved["codex_id"])
            entry["is_canonical_folklore"] = True
        if bp_resolved.get("folklore_tradition"):
            entry["folklore_tradition"] = str(bp_resolved["folklore_tradition"])

    log_list.append(entry)
    db.update_session(session_id, extra={"contained_anomalies_log": log_list})
    _prune_anomaly_from_scene_npcs(
        session_id,
        entity_name,
        extra_names=[orig_entity_name, disguise_alias_prune],
        session=sess,
        persist_db=True,
    )
    return entry


def spawn_agitated_non_hostile_entity(
    session_id: int,
    entity_name: str,
    *,
    location: str = "",
    category_tag: str = "spatial_warp",
    incursion_id: str = "",
    breach_id: str = "",
    quest_id: str = "",
    sub_obj_id: Optional[int] = None,
    is_story_quest: bool = False,
    session: Optional[Dict[str, Any]] = None,
    blueprint: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Spawns an agitated volatile Non-Hostile Entity into `nearby_enemies` for combat containment.
    - All regular combat attacks remain lethal (killing it fails bounties / forfeits rewards!).
    - Player can either weaken it to <= 35% HP to unlock `[🛡️ Subdue & Contain]` OR use `[🗣️ Persuade / Calm]` in combat.
    """
    from mechanics.combat.enemies import generate_scenario_enemy

    sess = session if isinstance(session, dict) else (db.get_session(session_id) or {})
    scen_key = str(sess.get("scenario") or "anomalous_incursions")
    loc_str = location or str(sess.get("current_location") or "Metropolitan Grid")
    eff_inc_id = str(incursion_id or breach_id or "").strip()

    bp = dict(blueprint) if isinstance(blueprint, dict) else None
    if bp is None and quest_id and session_id:
        q_row = db.get_quest_by_id(session_id, quest_id) or {}
        bp = parse_blueprint_from_notes(str(q_row.get("quest_notes") or ""))
    if bp is None and eff_inc_id:
        for inc in (sess.get("daily_incursions") or sess.get("daily_breaches") or []):
            if isinstance(inc, dict) and (inc.get("incursion_id") == eff_inc_id or inc.get("breach_id") == eff_inc_id):
                if isinstance(inc.get("anomaly_blueprint"), dict):
                    bp = dict(inc["anomaly_blueprint"])
                break

    orig_ag_name = str(entity_name or "").strip()
    disg_ag_alias = ""
    if bp:
        disg_ag_alias = str((bp.get("disguise_state") or {}).get("disguise_alias") or "").strip()
        bp, _unmask_ag = unmask_blueprint_disguise(bp)
        if _unmask_ag and bp.get("canonical_name"):
            entity_name = str(bp["canonical_name"])
        if session_id:
            try:
                db.record_session_anomaly_field_log(session_id, bp, stage="sighted", location=loc_str)
                if bp.get("codex_id"):
                    db.record_folklore_codex_progress(
                        db.get_session_participant_user_ids(session_id),
                        str(bp["codex_id"]),
                        stage="sighted",
                    )
            except Exception:
                pass
        enemy_obj = instantiate_enemy_from_blueprint(
            bp,
            tier=2,
            is_agitated_non_hostile=True,
            incursion_id=eff_inc_id,
            linked_quest_id=quest_id,
            linked_sub_obj_id=sub_obj_id,
            is_story_quest=bool(is_story_quest),
        )
        enemy_obj["name"] = entity_name
        enemy_obj["subdue_threshold_pct"] = NON_HOSTILE_SUBDUE_THRESHOLD_PCT
    else:
        arch_name = "Spatial Stalker" if category_tag == "spatial_warp" else "Cognitohazard Caster"
        enemy_obj = generate_scenario_enemy(
            scenario=scen_key,
            location=loc_str,
            chapter=int(sess.get("current_chapter", 1) or 1),
            custom_name=entity_name,
            custom_archetype=arch_name,
            exact_tier=2,
        )
        enemy_obj["name"] = entity_name
        enemy_obj["affixes"] = []
        enemy_obj["requires_non_lethal_subdue"] = True
        enemy_obj["born_disposition"] = "non_hostile"
        enemy_obj["subdue_threshold_pct"] = NON_HOSTILE_SUBDUE_THRESHOLD_PCT
        enemy_obj["temperament"] = "volatile"
        enemy_obj["category_tag"] = category_tag
        if eff_inc_id:
            enemy_obj["incursion_id"] = eff_inc_id
            enemy_obj["breach_id"] = eff_inc_id
        if quest_id:
            enemy_obj["linked_quest_id"] = quest_id
            enemy_obj["linked_sub_obj_id"] = sub_obj_id
            enemy_obj["is_story_quest"] = bool(is_story_quest)

    enemies = list(sess.get("nearby_enemies") or [])
    if not any(isinstance(e, dict) and e.get("name") == entity_name and e.get("requires_non_lethal_subdue") for e in enemies):
        enemies.append(enemy_obj)
    if isinstance(session, dict):
        session["nearby_enemies"] = enemies
    if session_id:
        db.update_session(session_id, nearby_enemies=enemies)
    _prune_anomaly_from_scene_npcs(
        session_id,
        entity_name,
        extra_names=[orig_ag_name, disg_ag_alias],
        session=sess,
        persist_db=True,
    )
    return enemy_obj


def _roll_optional_incursion_gear_drop(user_id: Optional[int], scen_key: str) -> str:
    if not user_id or random.random() >= 0.35:
        return ""
    try:
        from mechanics.combat.items.weapons import generate_random_equipment
        eq = generate_random_equipment(
            scenario=scen_key,
            slot=random.choice(["Weapon", "Armor", "Accessory 1"]),
            tier=2,
        )
        if isinstance(eq, dict) and eq.get("name"):
            db.add_item(
                user_id,
                eq["name"],
                item_type=eq.get("item_type", "Weapon"),
                effect=eq.get("effect", ""),
                slot_cost=int(eq.get("slot_cost", 1) or 1),
            )
            return str(eq["name"])
    except Exception:
        pass
    return ""


def _extract_check_roll_and_success(
    char: Dict[str, Any],
    stat_key: str,
    dc: int,
    force_roll: Optional[int] = None,
    pre_rolled_check: Any = None,
) -> Tuple[int, int, bool]:
    """Resolves `(nat_roll, total_check, succeeded)` honoring `force_roll` or UI `pre_rolled_check`."""
    stat_col_map = {"STR": "str_", "PER": "per_", "END": "end_", "CHA": "cha", "INT": "int_", "AGI": "agi", "LUK": "luk"}
    s_upper = str(stat_key or "CHA").upper()
    stat_val = int((char or {}).get(stat_col_map.get(s_upper, "cha"), 3) or 3)
    if isinstance((char or {}).get("stats"), dict) and s_upper in char["stats"]:
        stat_val = int(char["stats"].get(s_upper, stat_val) or stat_val)

    if force_roll is not None:
        nat_roll = int(force_roll)
        total_check = nat_roll + stat_val
        return nat_roll, total_check, (total_check >= dc and nat_roll > 1)

    if pre_rolled_check is not None:
        from skill_check import is_check_success
        succeeded = bool(is_check_success(pre_rolled_check, default_if_none=False))
        nat_roll = getattr(pre_rolled_check, "roll", None)
        if nat_roll is None and isinstance(pre_rolled_check, dict):
            nat_roll = pre_rolled_check.get("roll") or pre_rolled_check.get("natural_roll")
        nat_roll = int(nat_roll) if nat_roll is not None else (15 if succeeded else 4)
        total_val = getattr(pre_rolled_check, "total", None)
        if total_val is None and isinstance(pre_rolled_check, dict):
            total_val = pre_rolled_check.get("total")
        total_check = int(total_val) if total_val is not None else (nat_roll + stat_val)
        return nat_roll, total_check, succeeded

    nat_roll = random.randint(1, 20)
    total_check = nat_roll + stat_val
    return nat_roll, total_check, (total_check >= dc and nat_roll > 1)


def _complete_or_advance_linked_quest_containment(
    session_id: int,
    quest_id: str,
    sub_obj_id: Optional[int],
    entity_name: str,
    category_tag: str,
    resolution_method: str,
    party_user_ids: List[int],
) -> Dict[str, Any]:
    """Advances or completes a Bounty / Story Quest sub-objective when an agitated Non-Hostile Entity is contained in combat."""
    from db.quests import append_quest_note_flag_in_db
    from game_engine.quests import grant_stage_acquisition_item_if_needed

    quest = db.get_quest_by_id(session_id, quest_id)
    if not quest or quest.get("status") != "Active":
        return {}

    sess = db.get_session(session_id) or {}
    loc = str(sess.get("current_location") or quest.get("client_location") or "Metropolitan Grid")
    lead_uid = party_user_ids[0] if party_user_ids else sess.get("host_user_id")

    vault_entry = record_contained_anomaly_to_vault_log(
        session_id=session_id,
        entity_name=entity_name,
        category_tag=category_tag or "spatial_warp",
        subtype="non_hostile_entity",
        location=loc,
        containment_note=f"Contained alive during field operation '{quest.get('title', 'Containment Bounty')}'.",
        resolution_method=resolution_method,
        user_id=lead_uid,
        quest_id=quest_id,
        sub_obj_id=sub_obj_id,
    )
    secured_key = f"entity_secured_so_{sub_obj_id}" if sub_obj_id is not None else "entity_secured"
    append_quest_note_flag_in_db(session_id, quest_id, secured_key, "1")
    append_quest_note_flag_in_db(session_id, quest_id, "vault_logged", "1")
    db.reset_quest_strikes(session_id, quest_id)

    active_wp = db.get_active_waypoint(session_id, quest_id, sub_obj_id)
    all_wps = db.get_quest_waypoints(session_id, quest_id, sub_obj_id) or []
    total_stages = len(all_wps) or 1
    next_wp = None
    all_done = True

    if active_wp:
        cur_stage_idx = int(active_wp.get("stage_index", 1) or 1)
        next_wp = db.advance_waypoint(session_id, quest_id, cur_stage_idx, sub_obj_id)
        all_done = next_wp is None
        if not all_done:
            sub_obj_dict = None
            if sub_obj_id is not None:
                for so in (quest.get("sub_objectives") or []):
                    if isinstance(so, dict) and str(so.get("id")) == str(sub_obj_id):
                        sub_obj_dict = so
                        break
            grant_stage_acquisition_item_if_needed(
                session_id=session_id,
                quest=quest,
                completed_stage_index=cur_stage_idx,
                total_stages=total_stages,
                party_user_ids=party_user_ids,
                sub_obj=sub_obj_dict,
            )

    claim_res = None
    if all_done:
        if sub_obj_id is not None:
            db.mark_sub_objective_completed_in_quest(session_id, quest_id, sub_obj_id)
        else:
            db.update_quest_status(session_id, quest_id, "Completed")
            if party_user_ids:
                claim_res = db.claim_quest_reward(session_id, quest_id, party_user_ids)

    return {
        "quest_id": quest_id,
        "sub_obj_id": sub_obj_id,
        "quest_title": quest.get("title", "Containment Bounty"),
        "all_stages_complete": all_done,
        "next_waypoint": dict(next_wp) if next_wp else None,
        "claim_result": claim_res,
        "vault_entry": vault_entry,
    }


def resolve_anomalous_combat_containment(
    session_id: int,
    user_id: Optional[int] = None,
    action_type: str = "subdue",
    incursion_id: str = "",
    breach_id: str = "",
    quest_id: str = "",
    force_roll: Optional[int] = None,
    pre_rolled_check: Any = None,
    party_user_ids: Optional[List[int]] = None,
    target_enemy: Optional[Dict[str, Any]] = None,
    resolution_method: str = "",
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Resolves in-combat Non-Lethal Containment on an agitated `requires_non_lethal_subdue` entity
    OR Live-Capture on a Born-Hostile Anomalous Manifestation:
    - `action_type == 'subdue'`:
      Requires `0 < hp <= max(1, int(max_hp * threshold_pct))` (`<= 35%` HP, or `<= 50%` for instinctual hostiles),
      OR `is_breached`, OR `taboo_exploited` (allowing non-damage containment of `non_corporeal` anomalies!).
    - `action_type == 'combat_persuade'`:
      Available at ANY `hp > 0` for `sapient` anomalies (and legacy agitated entities).
      Born-hostile `instinctual` or `non_sapient` anomalies cannot be reasoned with verbally and require weakening or Taboo exploitation first.
    - Live-Capture Bonus on Born-Hostile Anomalies:
      Grants **+20% bonus XP** and **+5 Promotion Rep**, logs to Containment Vault, and triggers Object-to-Gear conversion if `anomaly_type == 'object'`.
    """
    eff_inc_id = str(incursion_id or breach_id or "").strip()
    sess = db.get_session(session_id) or {}
    scen_key = str(sess.get("scenario") or "anomalous_incursions")
    enemies = list(sess.get("nearby_enemies") or [])
    if target_enemy is None:
        target_enemy = next(
            (
                e for e in enemies
                if isinstance(e, dict)
                and (
                    (eff_inc_id and (e.get("incursion_id") == eff_inc_id or e.get("breach_id") == eff_inc_id))
                    or (quest_id and e.get("linked_quest_id") == quest_id)
                    or e.get("requires_non_lethal_subdue")
                    or e.get("is_anomalous_manifestation")
                )
            ),
            enemies[0] if enemies else None,
        )
    if not target_enemy:
        return {"success": False, "error": "No agitated anomalous entity present to contain."}

    ent_name = str(target_enemy.get("name") or "Anomalous Entity")
    hp = int(target_enemy.get("hp", 10) or 10)
    max_hp = max(1, int(target_enemy.get("max_hp", 40) or 40))
    sapience = str(target_enemy.get("sapience") or "").strip().lower()
    born_disp = str(target_enemy.get("born_disposition") or "").strip().lower()
    is_born_hostile = bool(
        not target_enemy.get("requires_non_lethal_subdue")
        and (born_disp == "hostile" or target_enemy.get("is_anomalous_manifestation"))
    )

    default_pct = 0.50 if (is_born_hostile and sapience == "instinctual") else NON_HOSTILE_SUBDUE_THRESHOLD_PCT
    threshold_pct = float(target_enemy.get("subdue_threshold_pct") or default_pct)
    threshold_hp = max(1, int(max_hp * threshold_pct))
    act = str(action_type or "subdue").strip().lower()

    p_uids = list(party_user_ids or ([user_id] if user_id else ([sess.get("host_user_id")] if sess.get("host_user_id") else [1])))
    lead_uid = user_id or (p_uids[0] if p_uids else 1)
    char = db.get_character(lead_uid) or {}

    if resolution_method or target_enemy.get("contained_via_parley"):
        method_str = str(resolution_method or "Live Capture (Mid-Combat Parley)")
    elif act == "sever_tether":
        ts_cbt = get_enemy_tether_state(target_enemy)
        if not ts_cbt:
            return {
                "success": False,
                "resolved": False,
                "combat_continues": True,
                "message": f"⚠️ **{ent_name}** has no active external tether or vessel to seal.",
            }
        sever_stat = str(ts_cbt.get("sever_stat") or "INT").upper()
        is_dossier_known_t = bool(
            target_enemy.get("dossier_revealed")
            or (isinstance(target_enemy.get("anomaly_blueprint"), dict) and target_enemy["anomaly_blueprint"].get("dossier_revealed"))
        )
        dc_t = 5 if is_dossier_known_t else 7
        nat_roll, total_check, succeeded = _extract_check_roll_and_success(
            char=char,
            stat_key=sever_stat,
            dc=dc_t,
            force_roll=force_roll,
            pre_rolled_check=pre_rolled_check,
        )
        if not succeeded:
            return {
                "success": False,
                "resolved": False,
                "agitated": True,
                "combat_continues": True,
                "roll": nat_roll,
                "total": total_check,
                "dc": dc_t,
                "message": (
                    f"🏺 Attempted to seal **{ts_cbt.get('vessel_name', 'Binding Vessel')}** ({sever_stat} {total_check} vs DC {dc_t}), "
                    f"but **{ent_name}**'s resonance warded off the lock!"
                ),
            }
        seal_res = seal_enemy_tether(target_enemy)
        if (
            hp <= max(1, int(max_hp * 0.50))
            or bool(target_enemy.get("tether_reformed_once"))
            or bool(ts_cbt.get("reformed_once"))
            or bool(target_enemy.get("is_breached"))
        ):
            method_str = f"Tether Sealed ({seal_res['vessel_name']}) & Contained ({sever_stat} {total_check})"
        else:
            db.update_session(session_id, nearby_enemies=enemies)
            return {
                "success": True,
                "resolved": False,
                "tether_sealed": True,
                "combat_continues": True,
                "roll": nat_roll,
                "total": total_check,
                "message": f"{seal_res['message']} Weaken **{ent_name}** to <= 50% HP or defeat it to complete Vault containment!",
            }
    elif act == "folklore_offering_rite":
        bp_off_cbt = target_enemy.get("anomaly_blueprint") if isinstance(target_enemy.get("anomaly_blueprint"), dict) else None
        off_match_cbt = find_matching_offering_in_inventory(lead_uid, bp_off_cbt)
        if not off_match_cbt:
            return {
                "success": False,
                "resolved": False,
                "combat_continues": True,
                "message": f"⚠️ You do not have a matching Folklore Ward or Offering in your inventory for **{ent_name}**!",
            }
        consume_folklore_offering_item(lead_uid, off_match_cbt["item_name"])
        nat_roll, total_check, succeeded = _extract_check_roll_and_success(
            char=char,
            stat_key="INT",
            dc=5,
            force_roll=force_roll,
            pre_rolled_check=pre_rolled_check,
        )
        if not succeeded:
            return {
                "success": False,
                "resolved": False,
                "agitated": True,
                "combat_continues": True,
                "roll": nat_roll,
                "total": total_check,
                "message": f"🎁 Presented **{off_match_cbt['item_name']}** (INT {total_check} vs DC 5), but **{ent_name}** batted the offering aside!",
            }
        method_str = f"Appeased via Folklore Counter-Rite ({off_match_cbt['item_name']})"
    elif act == "combat_persuade":
        if is_born_hostile and sapience in ("instinctual", "non_sapient"):
            return {
                "success": False,
                "resolved": False,
                "agitated": True,
                "combat_continues": True,
                "message": (
                    f"⚠️ **{ent_name}** is **{sapience.replace('_', '-')}** and cannot be reasoned with verbally! "
                    f"Weaken it to <= {int(threshold_pct * 100)}% HP or exploit its Folklore/SCP Taboo to use **[🛡️ Subdue & Contain]**!"
                ),
            }
        is_dossier_known = bool(
            target_enemy.get("dossier_revealed")
            or (isinstance(target_enemy.get("anomaly_blueprint"), dict) and target_enemy["anomaly_blueprint"].get("dossier_revealed"))
        )
        if not is_dossier_known:
            eff_inc_chk = eff_inc_id or str(target_enemy.get("incursion_id") or target_enemy.get("breach_id") or "")
            eff_qid_chk = quest_id or str(target_enemy.get("linked_quest_id") or "")
            if eff_qid_chk:
                q_chk = db.get_quest_by_id(session_id, eff_qid_chk) or {}
                if "dossier_revealed:1" in str(q_chk.get("quest_notes") or ""):
                    is_dossier_known = True
            elif eff_inc_chk:
                for inc_chk in (sess.get("daily_incursions") or sess.get("daily_breaches") or []):
                    if isinstance(inc_chk, dict) and (inc_chk.get("incursion_id") == eff_inc_chk or inc_chk.get("breach_id") == eff_inc_chk):
                        if inc_chk.get("dossier_revealed"):
                            is_dossier_known = True
                        break
        is_taboo_exp = bool(target_enemy.get("taboo_exploited"))
        if is_born_hostile and sapience == "compulsive" and not (is_dossier_known or is_taboo_exp):
            return {
                "success": False,
                "resolved": False,
                "agitated": True,
                "combat_continues": True,
                "message": (
                    f"⚠️ **{ent_name}** is locked in a **Compulsive** folklore loop and ignores blind verbal pleading! "
                    f"Unseal its **Anomaly Dossier**, exploit its **Taboo** first to unlock **[🗣️ Enact Counter-Rite]**, "
                    f"or weaken it to <= {int(threshold_pct * 100)}% HP to use **[🛡️ Subdue & Contain]**!"
                ),
            }
        dc = 6 if (hp <= max(1, int(max_hp * 0.50)) or is_taboo_exp) else 8
        if is_dossier_known:
            dc = max(4, dc - 2)
        nat_roll, total_check, succeeded = _extract_check_roll_and_success(
            char=char,
            stat_key="CHA",
            dc=dc,
            force_roll=force_roll,
            pre_rolled_check=pre_rolled_check,
        )
        if not succeeded:
            return {
                "success": False,
                "resolved": False,
                "agitated": True,
                "combat_continues": True,
                "roll": nat_roll,
                "total": total_check,
                "dc": dc,
                "message": (
                    f"🗣️ Attempted to calm **{ent_name}** mid-combat (CHA {total_check} vs DC {dc}), "
                    f"but its panicked resonance rejected your words!"
                ),
            }
        method_str = (
            f"Enacted Counter-Rite & Contained in Combat (CHA {total_check})"
            if sapience == "compulsive"
            else f"De-escalated & Contained in Combat (CHA {total_check})"
        )
    else:
        can_subdue_now = (
            hp <= threshold_hp
            or bool(target_enemy.get("is_breached"))
            or bool(target_enemy.get("taboo_exploited"))
            or force_roll is not None
        )
        if not can_subdue_now:
            return {
                "success": False,
                "agitated": True,
                "combat_continues": True,
                "message": (
                    f"⚠️ **{ent_name}** is still too thrashing to seal ({hp}/{max_hp} HP)! "
                    f"Carefully weaken it to <= {int(threshold_pct * 100)}% HP ({threshold_hp} HP) without killing it, "
                    f"exploit its Taboo, or attempt **[🗣️ Persuade / Calm]**!"
                ),
            }
        method_str = "Subdued Non-Lethally & Contained"

    # Remove subdued/de-escalated entity from combat if still in nearby_enemies!
    if any(e is target_enemy for e in enemies):
        remaining = [e for e in enemies if e is not target_enemy]
        db.update_session(session_id, nearby_enemies=remaining)

    if not eff_inc_id and target_enemy:
        eff_inc_id = str(target_enemy.get("breach_id") or target_enemy.get("incursion_id") or "")
    eff_quest_id = str(quest_id or target_enemy.get("linked_quest_id") or "")
    eff_sub_obj_id = target_enemy.get("linked_sub_obj_id")
    cat_tag = str(target_enemy.get("category_tag") or "spatial_warp")

    bp_enemy = target_enemy.get("anomaly_blueprint") if isinstance(target_enemy.get("anomaly_blueprint"), dict) else None
    if bp_enemy is None and target_enemy.get("anomaly_type"):
        bp_enemy = {
            "name": ent_name,
            "type": target_enemy.get("anomaly_type"),
            "form": target_enemy.get("form", "cursed_weapon"),
            "element": target_enemy.get("element", "aether"),
            "tier": int(target_enemy.get("tier", 2) or 2),
        }

    # Path A: Linked Daily Anomaly Breach
    incursions = list(sess.get("daily_incursions") or sess.get("daily_breaches") or [])
    target_inc = next((inc for inc in incursions if eff_inc_id and (inc.get("incursion_id") == eff_inc_id or inc.get("breach_id") == eff_inc_id)), None)
    if target_inc:
        if bp_enemy is None and isinstance(target_inc.get("anomaly_blueprint"), dict):
            bp_enemy = target_inc["anomaly_blueprint"]
        if target_inc.get("subtype") == "hostile_breach":
            is_born_hostile = True

        refund_res = refund_trick_tax_gold_on_containment(session_id, lead_uid, target_inc=target_inc)
        turn_now = _resolve_session_turn_number(session_id, sess)
        for inc in incursions:
            if inc.get("incursion_id") == eff_inc_id or inc.get("breach_id") == eff_inc_id:
                inc["resolved"] = True
                inc["agitated"] = False
                inc["resolved_at_turn"] = turn_now

        db.update_session(session_id, extra={"daily_incursions": incursions, "daily_breaches": None})

        gold_gain = int(target_inc.get("reward_gold", 120) or 120)
        xp_gain = int(target_inc.get("reward_xp", 85) or 85)
        rep_bonus = 0
        if is_born_hostile:
            xp_gain = int(round(xp_gain * 1.20))
            rep_bonus = 5
            try:
                from mechanics.social.factions import update_agent_promotion_reputation
                update_agent_promotion_reputation(
                    session_id=session_id,
                    delta_rep=5,
                    reason=f"Live-Captured Hostile Anomaly '{target_inc['entity_name']}'",
                    user_id=lead_uid,
                )
            except Exception:
                pass
        if lead_uid:
            db.apply_hp_mp_delta(lead_uid, gold_delta=gold_gain)
            db.add_xp(lead_uid, xp_gain)

        vault_entry = record_contained_anomaly_to_vault_log(
            session_id=session_id,
            entity_name=target_inc["entity_name"],
            category_tag=target_inc["category_tag"],
            subtype=target_inc["subtype"],
            location=target_inc["location"],
            containment_note=target_inc.get("containment_note", ""),
            resolution_method=method_str,
            user_id=lead_uid,
        )
        converted_res = handle_secured_object_anomaly_conversion(
            session_id=session_id,
            user_id=lead_uid,
            blueprint=bp_enemy,
            scen_key=scen_key,
            entity_name=target_inc["entity_name"],
            skip_codex_progress=True,
        )
        dropped_gear = (converted_res["item"]["name"] if converted_res and converted_res.get("item") else "") or _roll_optional_incursion_gear_drop(lead_uid, scen_key)
        gear_suffix = f" {converted_res['notice']}" if converted_res else (f" Recovered salvage: **{dropped_gear}**!" if dropped_gear else "")
        refund_suffix = f" {refund_res['notice']}" if refund_res.get("notice") else ""
        live_bonus_suffix = " *(+20% Live-Capture XP & +5 Promotion Rep)*" if is_born_hostile else ""
        icon_used = "🗣️" if act == "combat_persuade" else "🛡️"
        return {
            "success": True,
            "resolved": True,
            "subdued": True,
            "live_capture_bonus": is_born_hostile,
            "rep_bonus": rep_bonus,
            "trick_tax_refunded": int(refund_res.get("refunded_gold", 0) or 0),
            "converted_gear": converted_res,
            "reward_gold": gold_gain,
            "reward_xp": xp_gain,
            "reward_item": dropped_gear,
            "vault_entry": vault_entry,
            "message": (
                f"{icon_used} Contained **{target_inc['entity_name']}** alive!{live_bonus_suffix} "
                f"Earned +{gold_gain}G, +{xp_gain} XP, and logged into {vault_entry['vault_facility']}.{refund_suffix}{gear_suffix}"
            ),
        }

    # Path B: Linked Bounty or Story Quest Sub-Objective
    if not eff_quest_id:
        for q_cand in (db.get_session_quests(session_id, status="Active") or []):
            if (not is_born_hostile and is_non_hostile_entity_quest(q_cand)) or (
                is_born_hostile and ent_name.lower() in str(q_cand.get("objective") or "").lower()
            ):
                eff_quest_id = str(q_cand.get("quest_id") or "")
                break

    if bp_enemy is None and eff_quest_id:
        q_row_bp = db.get_quest_by_id(session_id, eff_quest_id) or {}
        bp_enemy = parse_blueprint_from_notes(str(q_row_bp.get("quest_notes") or ""))

    quest_res = {}
    refund_res_q = {"refunded_gold": 0, "notice": ""}
    if eff_quest_id:
        refund_res_q = refund_trick_tax_gold_on_containment(session_id, lead_uid, quest_id=eff_quest_id)
        quest_res = _complete_or_advance_linked_quest_containment(
            session_id=session_id,
            quest_id=eff_quest_id,
            sub_obj_id=eff_sub_obj_id,
            entity_name=ent_name,
            category_tag=cat_tag,
            resolution_method=method_str,
            party_user_ids=p_uids,
        )

    rep_bonus = 0
    bonus_xp_awarded = 0
    if is_born_hostile:
        base_q_xp = int(((db.get_quest_by_id(session_id, eff_quest_id) if eff_quest_id else None) or {}).get("reward_xp", 150) or 150)
        bonus_xp_awarded = max(20, int(round(base_q_xp * 0.20)))
        rep_bonus = 5
        if lead_uid:
            db.add_xp(lead_uid, bonus_xp_awarded)
        try:
            from mechanics.social.factions import update_agent_promotion_reputation
            update_agent_promotion_reputation(
                session_id=session_id,
                delta_rep=5,
                reason=f"Live-Captured Hostile Target '{ent_name}'",
                user_id=lead_uid,
            )
        except Exception:
            pass

    converted_res = handle_secured_object_anomaly_conversion(
        session_id=session_id,
        user_id=lead_uid,
        blueprint=bp_enemy,
        scen_key=scen_key,
        entity_name=ent_name,
    )

    vault_entry = quest_res.get("vault_entry") or record_contained_anomaly_to_vault_log(
        session_id=session_id,
        entity_name=ent_name,
        category_tag=cat_tag,
        subtype="hostile_breach" if is_born_hostile else "non_hostile_entity",
        location=str(sess.get("current_location") or "Metropolitan Grid"),
        resolution_method=method_str,
        user_id=lead_uid,
        quest_id=eff_quest_id,
        sub_obj_id=eff_sub_obj_id,
    )
    next_wp = quest_res.get("next_waypoint")
    if quest_res.get("all_stages_complete") and quest_res.get("quest_title"):
        follow_note = f" Objective **'{quest_res['quest_title']}'** completed!"
    elif next_wp and next_wp.get("stage_label"):
        follow_note = f" Next Stage: *{next_wp['stage_label']}*."
    else:
        follow_note = ""

    live_bonus_suffix = f" *(+{bonus_xp_awarded} Live-Capture Bonus XP & +5 Promotion Rep)*" if is_born_hostile else ""
    refund_q_suffix = f" {refund_res_q['notice']}" if refund_res_q.get("notice") else ""
    conv_suffix = f" {converted_res['notice']}" if converted_res else ""
    icon_used = "🗣️" if act == "combat_persuade" else "🛡️"
    return {
        "success": True,
        "resolved": True,
        "subdued": True,
        "live_capture_bonus": is_born_hostile,
        "bonus_xp": bonus_xp_awarded,
        "rep_bonus": rep_bonus,
        "trick_tax_refunded": int(refund_res_q.get("refunded_gold", 0) or 0),
        "converted_gear": converted_res,
        "quest_containment": quest_res,
        "vault_entry": vault_entry,
        "message": (
            f"{icon_used} Contained **{ent_name}** alive and sealed it into a containment unit!{live_bonus_suffix} "
            f"Logged to {vault_entry['vault_facility']}.{follow_note}{refund_q_suffix}{conv_suffix}"
        ),
    }


def handle_killed_non_hostile_entity(
    session_id: int,
    dead_enemy: Dict[str, Any],
    user_id: Optional[int] = None,
    party_user_ids: Optional[List[int]] = None,
    session: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Handles the fallout of LETHALLY KILLING (`0 HP`) a `requires_non_lethal_subdue` Non-Hostile Entity:
    - Daily Non-Hostile Incursion: Marks resolved (`killed_lethally=True`), forfeits all rewards (`0G`, `0 XP`, `0` gear, NO Vault Log).
    - Side Bounty / Mandatory Daily Bounty (`not is_story_quest`): Hard-fails the bounty (`status='Failed'`),
      applies client/faction penalties, and deducts `-15` Promotion Rep (`is_missed_mandatory=True`) if Mandatory Daily!
    - Story Quest Sub-Objective (`is_story_quest == 1`): Applies `dire_cost` fail-forward (`-5 HP` backlash,
      advances sub-objective without soft-locking campaign, NO Vault Log).
    """
    if not session_id or not isinstance(dead_enemy, dict):
        return {}

    sess = session if isinstance(session, dict) else (db.get_session(session_id) or {})
    ent_name = str(dead_enemy.get("name") or "Non-Hostile Entity")
    p_uids = list(party_user_ids or ([user_id] if user_id else ([sess.get("host_user_id")] if sess.get("host_user_id") else [1])))
    lead_uid = user_id or (p_uids[0] if p_uids else 1)

    inc_id = str(dead_enemy.get("incursion_id") or dead_enemy.get("breach_id") or "")
    if inc_id:
        fresh_sess = db.get_session(session_id) or sess
        incursions = list(fresh_sess.get("daily_incursions") or fresh_sess.get("daily_breaches") or [])
        turn_now = _resolve_session_turn_number(session_id, fresh_sess)
        for inc in incursions:
            if inc.get("incursion_id") == inc_id or inc.get("breach_id") == inc_id:
                inc["resolved"] = True
                inc["agitated"] = False
                inc["killed_lethally"] = True
                inc["resolved_at_turn"] = turn_now

        db.update_session(session_id, extra={"daily_incursions": incursions, "daily_breaches": None})
        if isinstance(session, dict):
            session["daily_incursions"] = incursions
            session["daily_breaches"] = incursions
        msg = (
            f"❌ **Containment Failed (Target Destroyed)!** Lethal force shattered **{ent_name}**—"
            f"all live-containment rewards forfeited (+0 XP, +0 Gold, not logged to Containment Vault)."
        )
        return {"handled": True, "type": "incursion_forfeited", "killed_lethally": True, "message": msg}

    linked_qid = str(dead_enemy.get("linked_quest_id") or "")
    linked_so_id = dead_enemy.get("linked_sub_obj_id")
    quest = db.get_quest_by_id(session_id, linked_qid) if linked_qid else None
    if not quest:
        for q_cand in (db.get_session_quests(session_id, status="Active") or []):
            if is_non_hostile_entity_quest(q_cand):
                quest = q_cand
                linked_qid = str(q_cand.get("quest_id") or "")
                break

    if not quest or quest.get("status") != "Active":
        return {
            "handled": True,
            "type": "unlinked_non_hostile_killed",
            "killed_lethally": True,
            "message": f"❌ **Non-Hostile Specimen Destroyed!** **{ent_name}** dissolved under lethal force (+0 Gold).",
        }

    if not quest.get("is_story_quest"):
        from game_engine.quests import apply_quest_failure_consequences
        fail_res = apply_quest_failure_consequences(
            session_id=session_id,
            quest=quest,
            party_user_ids=p_uids,
            reason="killed_non_hostile_target",
            session=sess,
        )
        promo_suffix = f" {fail_res['promotion_penalty_notice']}" if fail_res.get("promotion_penalty_notice") else ""
        msg = (
            f"❌ **Bounty Failed — Non-Hostile Target Killed!** Lethal damage destroyed **{ent_name}**, "
            f"failing **'{quest.get('title', 'Live Capture Bounty')}'**!{promo_suffix}"
        )
        return {
            "handled": True,
            "type": "bounty_failed",
            "quest_id": linked_qid,
            "killed_lethally": True,
            "fail_result": fail_res,
            "message": msg,
        }

    # Story Quest Sub-Objective: Fail-Forward at a Dire Cost (-5 HP backlash, no Vault Log)
    now = time.time()
    with db.get_conn() as conn:
        if linked_so_id is not None:
            conn.execute(
                "UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=?",
                (now, session_id, linked_qid, linked_so_id),
            )
        else:
            conn.execute(
                "UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=?",
                (now, session_id, linked_qid),
            )

    sub_objs = list(quest.get("sub_objectives") or [])
    if sub_objs:
        for so in sub_objs:
            if isinstance(so, dict) and (linked_so_id is None or str(so.get("id")) == str(linked_so_id)):
                so["completed"] = True
                so["resolution_approach"] = "dire_cost"
                break
        done_cnt = sum(1 for s in sub_objs if isinstance(s, dict) and s.get("completed"))
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE quests SET sub_objectives_json=?, progress=?, resolution_approach='dire_cost', updated_at=? WHERE session_id=? AND quest_id=?",
                (json.dumps(sub_objs), f"{done_cnt}/{len(sub_objs)} Cleared", now, session_id, linked_qid),
            )
    else:
        db.set_quest_resolution_approach(session_id, linked_qid, "dire_cost")

    db.reset_quest_strikes(session_id, linked_qid)
    if lead_uid:
        db.apply_hp_mp_delta(lead_uid, hp_delta=-5)

    msg = (
        f"⚠️ **Dire Cost — Specimen Shattered!** Lethal force destroyed **{ent_name}**, unleashing a violent "
        f"anomalous backlash (-5 HP). You salvage only fragmented residual readings to press the chapter forward "
        f"(specimen lost; not logged to Containment Vault)."
    )
    return {
        "handled": True,
        "type": "story_dire_cost",
        "quest_id": linked_qid,
        "sub_obj_id": linked_so_id,
        "killed_lethally": True,
        "message": msg,
    }


def resolve_non_hostile_incursion_action(
    session_id: int,
    user_id: int,
    incursion_id: str = "",
    action_type: str = "pacify",
    stat_used: str = "CHA",
    force_roll: Optional[int] = None,
    pre_rolled_check: Any = None,
    breach_id: str = "",
    player_text: str = "",
) -> Dict[str, Any]:
    """
    Resolves an interaction with a Daily Anomaly Breach:
    - Out-of-combat narrative containment (`persuade` [CHA], `calm` [PER], `outwit` [INT], `environment` [AGI],
      plus legacy `pacify`/`analyze`/`observe` and `seal_ability`):
      - Success (`total >= 10` or `seal_ability`):
        Marks incursion resolved, grants 100% Gold & XP + Anomalous Gear drop chance,
        and logs the entity/phenomenon into `contained_anomalies_log`.
      - Failure on `non_hostile_entity` increments strikes (`max_strikes = 2`; `nat_roll <= 2` deals 2 strikes):
        - Strike 1/2: Emits temperament-specific warning (`timid` poised to flee vs `volatile` poised to lash out).
        - Strike 2/2:
          - `'timid'` entity -> **Escapes!** Marks resolved (`escaped=True`), 0 rewards, no Vault Log.
          - `'volatile'` entity -> **Becomes Hostile!** Spawns into `nearby_enemies` (`requires_non_lethal_subdue=True`, `<= 35%` HP subdue).
    - `action_type == "attack"`:
      Immediately engages a `hostile_breach` or agitates a `non_hostile_entity` into combat.
    - `action_type in ("subdue", "combat_persuade")`:
      Delegates to `resolve_anomalous_combat_containment` (`<= 35%` HP subdue or in-combat `CHA` de-escalation).
    """
    eff_id = str(incursion_id or breach_id or "").strip()
    sess = db.get_session(session_id) or {}
    scen_key = str(sess.get("scenario") or "anomalous_incursions")
    incursions = list(sess.get("daily_incursions") or sess.get("daily_breaches") or [])
    target_inc = next((inc for inc in incursions if eff_id and (inc.get("incursion_id") == eff_id or inc.get("breach_id") == eff_id)), None)
    if not target_inc:
        loc_inc = get_active_incursion_at_location(session_id)
        if loc_inc:
            eff_id = str(loc_inc.get("breach_id") or loc_inc.get("incursion_id") or "")
            incursion_id = eff_id
            target_inc = next(
                (inc for inc in incursions if eff_id and (inc.get("incursion_id") == eff_id or inc.get("breach_id") == eff_id)),
                loc_inc,
            )
    if not target_inc:
        return {"success": False, "error": "No active Anomaly Breach found."}
    if target_inc.get("resolved"):
        return {"success": False, "already_resolved": True, "error": "This Anomaly Breach has already been contained."}

    act = str(action_type or "pacify").strip().lower()
    if (
        act.startswith("anomaly_inquiry")
        or act.startswith("anomaly_pattern")
        or act.startswith("question_trap")
        or act in ("converse", "study_pattern")
    ):
        return resolve_anomaly_dialogue_inquiry(
            session_id=session_id,
            entity_name=str(target_inc.get("entity_name") or ""),
            incursion_id=eff_id,
            breach_id=eff_id,
            inquiry_type=act,
            player_text=player_text,
            user_id=user_id,
            session=sess,
        )
    if act in ("reveal_dossier", "scan_dossier", "investigate_dossier"):
        rev_res = reveal_anomaly_dossier(session_id=session_id, incursion_id=eff_id, breach_id=eff_id)
        d_sum = rev_res.get("dossier_summary") or "Anomaly Taboo and Containment Protocol unsealed."
        return {
            "success": True,
            "resolved": False,
            "dossier_revealed": True,
            "dossier_summary": d_sum,
            "message": f"🔍 **Anomaly Dossier Unsealed:** {d_sum}",
        }
    has_live_combat_enemies = any(
        isinstance(e, dict) and int(e.get("hp", 0) or 0) > 0
        for e in (sess.get("nearby_enemies") or [])
    )
    if act in ("subdue", "combat_persuade", "sever_tether") or (act == "folklore_offering_rite" and has_live_combat_enemies):
        return resolve_anomalous_combat_containment(
            session_id=session_id,
            user_id=user_id,
            action_type=act,
            incursion_id=eff_id,
            breach_id=eff_id,
            force_roll=force_roll,
            pre_rolled_check=pre_rolled_check,
        )

    if target_inc.get("subtype") == "hostile_breach":
        act = "attack"

    approach_default_stats = {
        "persuade": "CHA",
        "nh_persuade": "CHA",
        "calm": "PER",
        "nh_calm": "PER",
        "outwit": "INT",
        "nh_outwit": "INT",
        "environment": "AGI",
        "nh_environment": "AGI",
        "exploit_taboo": "INT",
        "pacify": str(target_inc.get("preferred_stat") or "CHA").upper(),
        "analyze": "INT",
        "observe": "PER",
    }
    approach_method_labels = {
        "persuade": "Persuaded & Contained Willingly",
        "nh_persuade": "Persuaded & Contained Willingly",
        "calm": "Calmed & Sealed Non-Lethally",
        "nh_calm": "Calmed & Sealed Non-Lethally",
        "outwit": "Outwitted into Containment Snare",
        "nh_outwit": "Outwitted into Containment Snare",
        "environment": "Cornered via Environmental Containment",
        "nh_environment": "Cornered via Environmental Containment",
        "exploit_taboo": "Contained via Folklore/SCP Taboo Exploit",
        "analyze": "Analyzed & Sealed",
        "pacify": "Pacified & Contained",
    }

    char = db.get_character(user_id) or {}
    stat_key = str(stat_used or approach_default_stats.get(act) or target_inc.get("preferred_stat") or "CHA").upper()

    # Intentional attack on hostile_breach or non_hostile_entity immediately starts combat
    if act == "attack" and target_inc.get("subtype") in ("non_hostile_entity", "hostile_breach"):
        bp_inc = target_inc.get("anomaly_blueprint") if isinstance(target_inc.get("anomaly_blueprint"), dict) else None
        if target_inc.get("subtype") == "non_hostile_entity":
            enemy_obj = spawn_agitated_non_hostile_entity(
                session_id=session_id,
                entity_name=target_inc["entity_name"],
                location=target_inc.get("location", "City"),
                category_tag=target_inc.get("category_tag", "spatial_warp"),
                incursion_id=eff_id,
                breach_id=eff_id,
                blueprint=bp_inc,
            )
            breach_msg = (
                f"⚠️ **{target_inc['entity_name']}** has turned hostile in self-defense! "
                f"Carefully weaken it to <= 35% HP to use **[🛡️ Subdue & Contain]**, or use **[🗣️ Persuade / Calm]** "
                f"(killing it destroys the specimen and forfeits all rewards)!"
            )
        else:
            if bp_inc:
                bp_inc, _unmask_hb = unmask_blueprint_disguise(bp_inc)
                if _unmask_hb and bp_inc.get("canonical_name"):
                    target_inc["entity_name"] = str(bp_inc["canonical_name"])
                    target_inc["anomaly_blueprint"] = bp_inc
                try:
                    db.record_session_anomaly_field_log(session_id, bp_inc, stage="sighted", location=str(target_inc.get("location") or ""))
                    if bp_inc.get("codex_id"):
                        db.record_folklore_codex_progress(
                            db.get_session_participant_user_ids(session_id) or ([user_id] if user_id else []),
                            str(bp_inc["codex_id"]),
                            stage="sighted",
                        )
                except Exception:
                    pass
                enemy_obj = instantiate_enemy_from_blueprint(
                    bp_inc,
                    tier=3,
                    is_agitated_non_hostile=False,
                    incursion_id=eff_id,
                )
                enemy_obj["name"] = target_inc["entity_name"]
            else:
                from mechanics.combat.enemies import generate_scenario_enemy
                enemy_obj = generate_scenario_enemy(
                    scenario=scen_key,
                    location=target_inc.get("location", "City"),
                    chapter=int(sess.get("current_chapter", 1) or 1),
                    custom_name=target_inc["entity_name"],
                    custom_archetype="Spatial Stalker" if target_inc.get("category_tag") == "spatial_warp" else "Cognitohazard Caster",
                    exact_tier=3,
                )
                enemy_obj["incursion_id"] = eff_id
                enemy_obj["breach_id"] = eff_id
            enemies = list(sess.get("nearby_enemies") or [])
            enemies.append(enemy_obj)
            db.update_session(session_id, nearby_enemies=enemies)
            breach_msg = f"⚔️ Hostile Breach Engaged: **{target_inc['entity_name']}** lunges from the spatial tear! Defeat it in combat to seal the breach!"

        for inc in incursions:
            if inc.get("incursion_id") == eff_id or inc.get("breach_id") == eff_id:
                inc["agitated"] = True

        db.update_session(session_id, extra={"daily_incursions": incursions, "daily_breaches": None})
        return {
            "success": False,
            "agitated": True,
            "combat_started": True,
            "enemy": enemy_obj,
            "message": breach_msg,
        }

    # Evaluate Folklore/SCP Taboo, Offering Rite, Paradoxical Omen & Dossier Bonus on containment check
    bp_inc = target_inc.get("anomaly_blueprint") if isinstance(target_inc.get("anomaly_blueprint"), dict) else None
    offering_used_note = ""
    if act == "folklore_offering_rite":
        off_match_inc = find_matching_offering_in_inventory(user_id, bp_inc)
        if not off_match_inc:
            return {
                "success": False,
                "resolved": False,
                "agitated": False,
                "message": f"⚠️ You do not have a matching Folklore Ward or Offering in your inventory for **{target_inc['entity_name']}**!",
            }
        consume_folklore_offering_item(user_id, off_match_inc["item_name"])
        rev_off = reveal_anomaly_dossier(session_id=session_id, incursion_id=eff_id, breach_id=eff_id)
        bp_inc = rev_off.get("blueprint") or bp_inc
        target_inc["dossier_revealed"] = True
        if bp_inc and bp_inc.get("canonical_name"):
            target_inc["entity_name"] = str(bp_inc["canonical_name"])
        approach_method_labels["folklore_offering_rite"] = f"Appeased via Folklore Offering ({off_match_inc['item_name']})"
        offering_used_note = f" 🎁 Consumed **{off_match_inc['item_name']}** (-5 DC Folklore Counter-Rite)!"

    taboo_eval = evaluate_taboo_interaction(bp_inc, action_label=act, stat_used=stat_key, incursion_action=act)
    dc_eff = 10
    if act == "folklore_offering_rite":
        dc_eff = max(4, dc_eff - 5)
    elif target_inc.get("dossier_revealed") or (bp_inc and bp_inc.get("dossier_revealed")):
        dc_eff -= 2
    if taboo_eval.get("exploited"):
        dc_eff = max(4, dc_eff - int(taboo_eval.get("check_bonus", 3) or 3))
    elif int(target_inc.get("prank_dc_penalty", 0) or 0) != 0:
        dc_eff = max(4, dc_eff + int(target_inc.get("prank_dc_penalty", 0) or 0))

    paradox_eval = (
        evaluate_omen_paradox(
            bp_inc,
            dossier_revealed=bool(target_inc.get("dossier_revealed") or (bp_inc and bp_inc.get("dossier_revealed"))),
            is_observation=act in ("calm", "nh_calm", "observe", "analyze"),
        )
        if act in ("calm", "nh_calm", "observe", "analyze")
        else {"has_paradox": False, "dc_mod": 0, "note": ""}
    )
    if paradox_eval.get("has_paradox") and int(paradox_eval.get("dc_mod", 0) or 0) < 0:
        dc_eff = max(4, dc_eff + int(paradox_eval["dc_mod"]))

    nat_roll, total_check, check_succeeded = _extract_check_roll_and_success(
        char=char,
        stat_key=stat_key,
        dc=dc_eff,
        force_roll=force_roll,
        pre_rolled_check=pre_rolled_check,
    )

    # Success resolution (seal_ability or check_succeeded)
    if act == "seal_ability" or check_succeeded:
        refund_res = refund_trick_tax_gold_on_containment(session_id, user_id, target_inc=target_inc)
        turn_now = _resolve_session_turn_number(session_id, sess)
        for inc in incursions:
            if inc.get("incursion_id") == eff_id or inc.get("breach_id") == eff_id:
                inc["resolved"] = True
                inc["agitated"] = False
                inc["prank_dc_penalty"] = 0
                inc["resolved_at_turn"] = turn_now

        db.update_session(session_id, extra={"daily_incursions": incursions, "daily_breaches": None})

        gold_gain = int(target_inc.get("reward_gold", 120) or 120)
        xp_gain = int(target_inc.get("reward_xp", 85) or 85)
        if user_id:
            db.apply_hp_mp_delta(user_id, gold_delta=gold_gain)
            db.add_xp(user_id, xp_gain)

        method_desc = (
            "Sacred Seal / Ability Containment"
            if act == "seal_ability"
            else f"{approach_method_labels.get(act, 'Pacified')} ({stat_key} Check {total_check})"
        )
        vault_entry = record_contained_anomaly_to_vault_log(
            session_id=session_id,
            entity_name=target_inc["entity_name"],
            category_tag=target_inc["category_tag"],
            subtype=target_inc["subtype"],
            location=target_inc["location"],
            containment_note=target_inc.get("containment_note", ""),
            resolution_method=method_desc,
            user_id=user_id,
        )
        converted_res = handle_secured_object_anomaly_conversion(
            session_id=session_id,
            user_id=user_id,
            blueprint=bp_inc or {"name": target_inc["entity_name"], "type": target_inc.get("anomaly_type", "")},
            scen_key=scen_key,
            entity_name=target_inc["entity_name"],
            skip_codex_progress=True,
        )
        dropped_gear = (converted_res["item"]["name"] if converted_res and converted_res.get("item") else "") or _roll_optional_incursion_gear_drop(user_id, scen_key)
        gear_suffix = f" {converted_res['notice']}" if converted_res else (f" Recovered salvage: **{dropped_gear}**!" if dropped_gear else "")
        refund_suffix = f" {refund_res['notice']}" if refund_res.get("notice") else ""
        taboo_note = f" {taboo_eval['log_message']}" if taboo_eval.get("exploited") else ""
        paradox_note_s = f" {paradox_eval['note']}" if paradox_eval.get("has_paradox") and paradox_eval.get("note") else ""
        return {
            "success": True,
            "resolved": True,
            "approach": act,
            "taboo_exploited": bool(taboo_eval.get("exploited")),
            "trick_tax_refunded": int(refund_res.get("refunded_gold", 0) or 0),
            "converted_gear": converted_res,
            "reward_gold": gold_gain,
            "reward_xp": xp_gain,
            "reward_item": dropped_gear,
            "vault_entry": vault_entry,
            "message": (
                f"✨ Successfully contained **{target_inc['entity_name']}** via {approach_method_labels.get(act, 'Containment Protocol')}!{offering_used_note}{taboo_note}{paradox_note_s} "
                f"Earned +{gold_gain}G, +{xp_gain} XP, and logged into {vault_entry['vault_facility']}.{refund_suffix}{gear_suffix}"
            ),
        }

    # Failed check handling on Non-Hostile Entity: Temperament-Driven Strike Escalation!
    if target_inc.get("subtype") == "non_hostile_entity":
        temperament = get_non_hostile_entity_temperament(
            seed_key=incursion_id,
            explicit=str(target_inc.get("temperament") or (bp_inc or {}).get("non_hostile_temperament") or ""),
        )
        prev_strikes = int(target_inc.get("strikes", 0) or 0)
        max_strikes = int(target_inc.get("max_strikes", 2) or 2)
        strike_delta = 2 if nat_roll <= 2 else 1
        if taboo_eval.get("violated") and int(taboo_eval.get("strike_delta", 0) or 0) > 0:
            strike_delta = max(strike_delta, strike_delta + 1)
            if temperament not in ("mischievous", "spook") and user_id and int(taboo_eval.get("player_backlash_dmg", 0) or 0) > 0:
                db.apply_hp_mp_delta(user_id, hp_delta=-4)
        new_strikes = prev_strikes + strike_delta

        if new_strikes < max_strikes:
            side_fx: Dict[str, Any] = {}
            if temperament in ("mischievous", "spook"):
                side_fx = apply_non_hostile_strike_side_effects(
                    session_id=session_id,
                    user_id=user_id,
                    entity_name=str(target_inc.get("entity_name") or ""),
                    temperament=temperament,
                    is_final_strike=False,
                    seed_key=eff_id,
                    incursion_id=eff_id,
                    target_inc=target_inc,
                )
            for inc in incursions:
                if inc.get("incursion_id") == eff_id or inc.get("breach_id") == eff_id:
                    inc["strikes"] = new_strikes
                    inc["temperament"] = temperament

            db.update_session(session_id, extra={"daily_incursions": incursions, "daily_breaches": None})
            if temperament in ("mischievous", "spook") and side_fx.get("warn_suffix"):
                warn_msg = (
                    f"⚠️ Containment attempt on **{target_inc['entity_name']}** faltered ({stat_key} {total_check} vs DC {dc_eff}) "
                    f"[{new_strikes}/{max_strikes} Strikes]! {side_fx['warn_suffix']}"
                )
            elif temperament == "timid":
                warn_msg = (
                    f"⚠️ Containment attempt on **{target_inc['entity_name']}** faltered ({stat_key} {total_check} vs DC {dc_eff}) "
                    f"[{new_strikes}/{max_strikes} Strikes]! Startled, it edges toward an escape seam—one more failed check and it will vanish!"
                )
            else:
                warn_msg = (
                    f"⚠️ Containment attempt on **{target_inc['entity_name']}** faltered ({stat_key} {total_check} vs DC {dc_eff}) "
                    f"[{new_strikes}/{max_strikes} Strikes]! Its anomalous aura bristles aggressively—one more failed check and it will turn hostile!"
                )
            return {
                "success": False,
                "resolved": False,
                "agitated": False,
                "escaped": False,
                "combat_started": False,
                "temperament": temperament,
                "strikes": new_strikes,
                "max_strikes": max_strikes,
                "gold_stolen": int(side_fx.get("gold_stolen", 0) or 0),
                "mp_drained": int(side_fx.get("mp_drained", 0) or 0),
                "prank_dc_penalty": int(side_fx.get("prank_dc_penalty", 0) or 0),
                "directive": str(side_fx.get("directive") or ""),
                "roll": nat_roll,
                "total": total_check,
                "message": warn_msg,
            }

        # Max strikes reached (>= 2): branch by temperament!
        if temperament in ("timid", "mischievous", "spook"):
            side_fx_final: Dict[str, Any] = {}
            if temperament in ("mischievous", "spook"):
                side_fx_final = apply_non_hostile_strike_side_effects(
                    session_id=session_id,
                    user_id=user_id,
                    entity_name=str(target_inc.get("entity_name") or ""),
                    temperament=temperament,
                    is_final_strike=True,
                    seed_key=eff_id,
                    incursion_id=eff_id,
                    target_inc=target_inc,
                )
            turn_now = _resolve_session_turn_number(session_id, sess)
            for inc in incursions:
                if inc.get("incursion_id") == eff_id or inc.get("breach_id") == eff_id:
                    inc["strikes"] = new_strikes
                    inc["resolved"] = True
                    inc["escaped"] = True
                    inc["agitated"] = False
                    inc["temperament"] = temperament
                    inc["resolved_at_turn"] = turn_now

            db.update_session(session_id, extra={"daily_incursions": incursions, "daily_breaches": None})
            _esc_names = get_blueprint_alias_names(target_inc.get("anomaly_blueprint"), str(target_inc.get("entity_name") or ""))
            _prune_anomaly_from_scene_npcs(
                session_id,
                _esc_names[0] if _esc_names else "",
                extra_names=_esc_names[1:],
                session=sess,
                persist_db=True,
            )
            esc_msg = str(side_fx_final.get("escape_message") or "") or (
                f"💨 **Entity Escaped!** Startled by repeated failed containment attempts ({stat_key} {total_check} vs DC {dc_eff}), "
                f"**{target_inc['entity_name']}** slipped through a spatial seam and vanished! Live-containment rewards forfeited."
            )
            return {
                "success": False,
                "resolved": True,
                "escaped": True,
                "agitated": False,
                "combat_started": False,
                "temperament": temperament,
                "strikes": new_strikes,
                "max_strikes": max_strikes,
                "gold_stolen": int(side_fx_final.get("gold_stolen", 0) or 0),
                "total_escrowed_gold": int(side_fx_final.get("total_escrowed_gold", 0) or 0),
                "mp_drained": int(side_fx_final.get("mp_drained", 0) or 0),
                "status_applied": str(side_fx_final.get("status_applied") or ""),
                "directive": str(side_fx_final.get("directive") or ""),
                "roll": nat_roll,
                "total": total_check,
                "message": esc_msg,
            }

        # Volatile temperament -> Agitated Combat!
        enemy_obj = spawn_agitated_non_hostile_entity(
            session_id=session_id,
            entity_name=target_inc["entity_name"],
            location=target_inc.get("location", "City"),
            category_tag=target_inc.get("category_tag", "spatial_warp"),
            incursion_id=eff_id,
            breach_id=eff_id,
            blueprint=bp_inc,
        )
        for inc in incursions:
            if inc.get("incursion_id") == eff_id or inc.get("breach_id") == eff_id:
                inc["strikes"] = new_strikes
                inc["agitated"] = True
                inc["temperament"] = "volatile"

        db.update_session(session_id, extra={"daily_incursions": incursions, "daily_breaches": None})
        return {
            "success": False,
            "resolved": False,
            "agitated": True,
            "combat_started": True,
            "temperament": "volatile",
            "strikes": new_strikes,
            "max_strikes": max_strikes,
            "enemy": enemy_obj,
            "roll": nat_roll,
            "total": total_check,
            "message": (
                f"⚠️ **Entity Agitated into Combat!** Provoked by repeated containment failures ({stat_key} {total_check} vs DC {dc_eff}), "
                f"**{target_inc['entity_name']}** lashes out violently! Weaken it to <= 35% HP to use **[🛡️ Subdue & Contain]** "
                f"or attempt **[🗣️ Persuade / Calm]**—killing it will destroy the specimen and forfeit all rewards!"
            ),
        }

    return {
        "success": False,
        "resolved": False,
        "agitated": False,
        "roll": nat_roll,
        "total": total_check,
        "message": f"Containment attempt on {target_inc['entity_name']} faltered ({stat_key} check {total_check} vs DC {dc_eff}), but the anomaly remains stable enough to try again.",
    }


def mark_hostile_incursion_resolved_on_victory(
    session_id: int,
    incursion_id: str = "",
    user_id: Optional[int] = None,
    breach_id: str = "",
    prevent_vault_capture: bool = False,
) -> Optional[Dict[str, Any]]:
    """Marks a hostile Daily Anomaly Breach resolved upon defeating its breach entity in combat."""
    eff_id = str(incursion_id or breach_id or "").strip()
    if not session_id or not eff_id:
        return None
    sess = db.get_session(session_id) or {}
    scen_key = str(sess.get("scenario") or "anomalous_incursions")
    incursions = list(sess.get("daily_incursions") or sess.get("daily_breaches") or [])
    target_inc = next(
        (inc for inc in incursions if (inc.get("incursion_id") == eff_id or inc.get("breach_id") == eff_id) and not inc.get("resolved")),
        None,
    )
    if not target_inc:
        return None

    # Safety guard: killing a non_hostile_entity in combat NEVER awards hostile victory rewards!
    if target_inc.get("subtype") == "non_hostile_entity":
        kill_res = handle_killed_non_hostile_entity(
            session_id=session_id,
            dead_enemy={"name": target_inc.get("entity_name", "Entity"), "incursion_id": incursion_id, "requires_non_lethal_subdue": True},
            user_id=user_id,
            session=sess,
        )
        return {
            "resolved": True,
            "killed_lethally": True,
            "reward_gold": 0,
            "reward_xp": 0,
            "reward_item": "",
            "message": kill_res.get("message", ""),
        }

    turn_now = _resolve_session_turn_number(session_id, sess)
    for inc in incursions:
        if inc.get("incursion_id") == eff_id or inc.get("breach_id") == eff_id:
            inc["resolved"] = True
            inc["agitated"] = False
            if prevent_vault_capture:
                inc["dispersed_unsealed"] = True
            inc["resolved_at_turn"] = turn_now

    db.update_session(session_id, extra={"daily_incursions": incursions, "daily_breaches": None})

    gold_gain = int(target_inc.get("reward_gold", 140) or 140)
    xp_gain = int(target_inc.get("reward_xp", 100) or 100)
    bp_inc = target_inc.get("anomaly_blueprint") if isinstance(target_inc.get("anomaly_blueprint"), dict) else {"name": target_inc["entity_name"], "type": target_inc.get("anomaly_type", "")}

    if prevent_vault_capture:
        gold_gain = int(round(gold_gain * 0.60))
        xp_gain = int(round(xp_gain * 0.60))
        if user_id:
            db.apply_hp_mp_delta(user_id, gold_delta=gold_gain)
            db.add_xp(user_id, xp_gain)
        if isinstance(bp_inc, dict) and (bp_inc.get("blueprint_id") or bp_inc.get("codex_id")):
            try:
                db.record_session_anomaly_field_log(session_id, bp_inc, stage="sighted", location=str(target_inc.get("location") or ""))
                if bp_inc.get("codex_id"):
                    db.record_folklore_codex_progress(
                        db.get_session_participant_user_ids(session_id) or ([user_id] if user_id else []),
                        str(bp_inc["codex_id"]),
                        stage="sighted",
                    )
            except Exception:
                pass
        return {
            "resolved": True,
            "dispersed_unsealed": True,
            "prevent_vault_capture": True,
            "reward_gold": gold_gain,
            "reward_xp": xp_gain,
            "reward_item": "",
            "vault_entry": None,
            "message": (
                f"💨 **Anomaly Breach Dispersed (Unsealed Tether):** Forced **{target_inc['entity_name']}** to scatter "
                f"(+{gold_gain}G, +{xp_gain} XP [60%]; seal its tether vessel next time for permanent Vault capture!)."
            ),
        }

    converted_res = handle_secured_object_anomaly_conversion(
        session_id=session_id,
        user_id=user_id,
        blueprint=bp_inc,
        scen_key=scen_key,
        entity_name=target_inc["entity_name"],
        skip_codex_progress=True,
    )
    dropped_gear = (converted_res["item"]["name"] if converted_res and converted_res.get("item") else "") or _roll_optional_incursion_gear_drop(user_id, scen_key)
    if user_id:
        db.apply_hp_mp_delta(user_id, gold_delta=gold_gain)
        db.add_xp(user_id, xp_gain)

    vault_entry = record_contained_anomaly_to_vault_log(
        session_id=session_id,
        entity_name=target_inc["entity_name"],
        category_tag=target_inc["category_tag"],
        subtype=target_inc["subtype"],
        location=target_inc["location"],
        containment_note=target_inc.get("containment_note", ""),
        resolution_method="Hostile Breach Eliminated & Contained",
        user_id=user_id,
        blueprint=bp_inc,
        incursion_id=eff_id,
    )
    gear_suffix = f" {converted_res['notice']}" if converted_res else (f" Salvaged **{dropped_gear}**!" if dropped_gear else "")
    return {
        "resolved": True,
        "converted_gear": converted_res,
        "reward_gold": gold_gain,
        "reward_xp": xp_gain,
        "reward_item": dropped_gear,
        "vault_entry": vault_entry,
        "message": (
            f"🌀 **Anomaly Breach Sealed!** Contained **{target_inc['entity_name']}** "
            f"(+{gold_gain}G, +{xp_gain} XP • Logged to {vault_entry['vault_facility']}).{gear_suffix}"
        ),
    }


def resolve_anomalous_emergency_extraction(
    session_id: int,
    user_id: int,
    apply_vitals_to_db: bool = True,
) -> Dict[str, Any]:
    """
    Faction-Aware Emergency Medical Extraction when the player drops to 0 HP in Anomalous Incursions:
    - Public Agency (`public_agency`):
      Extracted to *Medical & Psychic Cleansing Bay (`zone_agency_hq`)* — `0G` Free.
    - Monastic Shrine Order (`monastic_order`):
      Extracted to *Temple Healing Sanctuary (`zone_eastern_temple`)* — `0G` Free.
    - Private Agencies (`private_agency_1`, `private_agency_2`) & Independent Freelancers (`freelancer`):
      Extracted to *Metropolitan Hospital (`zone_hospital`)* — `10%` of current gold, capped at max `100G`.
    - Restores Player HP & MP to 50% of Max, clears `nearby_enemies`, advances time by +120 minutes,
      and preserves active quests/bounties so the player can retry.
    """
    from mechanics.social.factions import get_anomalous_faction_state
    from mechanics.world.locations.seeds import get_session_urban_zone_name, get_session_urban_facility_name

    sess = db.get_session(session_id) or {}
    scen_key = str(sess.get("scenario") or "anomalous_incursions")
    char = db.get_character(user_id) or {}
    fac_state = get_anomalous_faction_state(session_id, user_id=user_id)
    arch = str(fac_state.get("faction_archetype_key") or "public_agency")

    current_gold = max(0, int(char.get("gold", 0) or 0))
    from mechanics.social.origin_mode import is_student_operative
    from mechanics.world.world_schedule import is_campus_node_or_location
    if scenario_data.is_anomalous_high_school_scenario(scen_key) and is_student_operative(sess):
        cur_loc = str(sess.get("current_location") or "")
        cur_nid = str(sess.get("current_node_id") or "")
        cur_node = db.get_world_node(session_id, cur_nid) if cur_nid else None
        p_node = db.get_world_node(session_id, cur_node["parent_id"]) if (cur_node and cur_node.get("parent_id")) else None
        on_campus = is_campus_node_or_location(cur_node, p_node, location_str=cur_loc, session_id=session_id, scen_key=scen_key)
        if on_campus:
            dest_node_id = "loc_school_infirmary"
            dest_location = "Main Academy Campus ➔ Main Academic Building ➔ School Nurse's Infirmary"
            fee = 0
            provider_label = "Campus Nurse & Student Council First-Aid Detail"
        else:
            z_name = get_session_urban_zone_name(session_id, "zone_city_center", "City Center", scen_key)
            c_name = get_session_urban_facility_name(session_id, "zone_city_center", "loc_general_hospital", "Metropolitan General Hospital", scen_key)
            dest_node_id = "loc_hosp_emergency_triage"
            dest_location = f"{z_name} ➔ {c_name} ➔ Emergency Trauma & Ambulance Triage"
            fee = min(50, int(current_gold * 0.05))
            provider_label = "Metropolitan Paramedic Evacuation Unit (Student Subsidy)"
    elif arch == "public_agency":
        z_name = get_session_urban_zone_name(session_id, "zone_city_center", "City Center", scen_key)
        hq_name = namegen.generate_agency_hq_name(scen_key, hash_val=int(session_id or 1))
        f_name = get_session_urban_facility_name(session_id, "zone_agency_hq", "loc_hq_medical_bay", "Medical & Psychic Cleansing Bay", scen_key)
        dest_node_id = "loc_hq_medical_bay"
        dest_location = f"{z_name} ➔ {hq_name} ➔ {f_name}"
        fee = 0
        provider_label = "Bureau Emergency Extraction Team (Taxpayer-Funded)"
    elif arch == "monastic_order":
        z_name = get_session_urban_zone_name(session_id, "zone_woods_reserve", "Woods & Mountain Reserve", scen_key)
        c_name = get_session_urban_facility_name(session_id, "zone_woods_reserve", "loc_eastern_temple", "Eastern Grand Temple & Sanctuary", scen_key)
        dest_node_id = "loc_et_main_sanctuary"
        dest_location = f"{z_name} ➔ {c_name} ➔ Main Worship Hall & Incense Courtyard"
        fee = 0
        provider_label = "Shrine Crow-Talisman Rescue Ascetics (Sacred Sanctuary)"
    else:
        z_name = get_session_urban_zone_name(session_id, "zone_city_center", "City Center", scen_key)
        c_name = get_session_urban_facility_name(session_id, "zone_city_center", "loc_general_hospital", "Metropolitan General Hospital", scen_key)
        dest_node_id = "loc_hosp_emergency_triage"
        dest_location = f"{z_name} ➔ {c_name} ➔ Emergency Trauma & Ambulance Triage"
        fee = min(100, int(current_gold * 0.10))
        provider_label = "Metropolitan Paramedic Evacuation Unit"

    try:
        dest_node = db.get_world_node(session_id, dest_node_id)
        if dest_node:
            ancestors = db.get_node_ancestors(session_id, dest_node_id)
            chain = [a["name"] for a in reversed(ancestors)] + [dest_node["name"]]
            if chain:
                dest_location = " ➔ ".join(chain)
    except Exception:
        pass

    max_hp = max(10, int(char.get("max_hp", 20) or 20))
    max_mp = max(10, int(char.get("max_mp", 10) or 10))
    cur_hp = int(char.get("hp", 0) or 0)
    cur_mp = int(char.get("mp", 0) or 0)
    target_hp = max(1, max_hp // 2)
    target_mp = max(1, max_mp // 2)

    hp_delta = max(0, target_hp - cur_hp)
    mp_delta = max(0, target_mp - cur_mp)
    if user_id and apply_vitals_to_db:
        db.apply_hp_mp_delta(user_id, hp_delta=hp_delta, mp_delta=mp_delta, gold_delta=-fee)

    from mechanics.system.time_engine import advance_time
    t_res = advance_time(session_id, 120, party_uids=[user_id] if user_id else None)
    new_day = int(t_res.get("new_day", 1) or 1)
    new_min = int(t_res.get("new_minute", 480) or 480)

    db.update_session(
        session_id,
        current_location=dest_location,
        current_node_id=dest_node_id,
        nearby_enemies=[],
        current_npcs=[],
    )

    fee_text = "0G (covered by faction medical benefits)" if fee == 0 else f"{fee}G emergency copay"
    return {
        "extracted": True,
        "faction_archetype_key": arch,
        "destination_location": dest_location,
        "destination_node_id": dest_node_id,
        "fee_paid": fee,
        "fee_charged": fee,
        "restored_hp": target_hp,
        "restored_mp": target_mp,
        "minutes_elapsed": 120,
        "new_day": new_day,
        "new_minute": new_min,
        "provider_label": provider_label,
        "narrative": (
            f"🚨 **[EMERGENCY MEDICAL EXTRACTION]**: Critical vitals triggered your emergency transponder! "
            f"{provider_label} evacuated you from the breach zone to **{dest_location}** ({fee_text}). "
            f"After two hours of stabilization, you regain consciousness at {target_hp}/{max_hp} HP and {target_mp}/{max_mp} MP."
        ),
    }


def process_anomalous_daily_rollover(
    session_id: int,
    new_day: int,
    party_uids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Executes the daily rollover routine for Anomalous Incursions when the day advances:
    1. Audits yesterday's Mandatory Daily Bounty (-15 Rep if missed; suspends salary/rations if at 0 Rep).
    2. Pays Public Agency Daily Salary (50G-300G by Promotion Tier) if not suspended.
    3. Resets Monastic Shrine daily free claim counter (`shrine_free_claims_today = 0`).
    4. Auto-dispatches today's Mandatory Daily Bounty via Morning SMS into Active Quests.
    5. Rolls 2-3 new optional Daily Anomalous Incursions (expiring yesterday's with 0 penalty).
    """
    from mechanics.social.factions import (
        get_anomalous_faction_state,
        save_anomalous_faction_state,
        update_agent_promotion_reputation,
        get_anomalous_promotion_tier_info,
    )

    sess = db.get_session(session_id) or {}
    scen_key = str(sess.get("scenario") or "fantasy")
    if not scenario_data.is_anomalous_incursions_scenario(scen_key):
        return {"processed": False}

    host_uid = (party_uids[0] if party_uids else None) or sess.get("host_user_id")
    state = get_anomalous_faction_state(session_id, user_id=host_uid)
    last_rollover = int(state.get("last_rollover_day", 1) or 1)
    if int(new_day) <= last_rollover and (sess.get("daily_incursions") or sess.get("daily_breaches")):
        return {"processed": False, "state": state}

    notices: List[str] = []
    arch = str(state.get("faction_archetype_key") or "public_agency")

    # 1. Audit yesterday's Mandatory Daily Bounty (only if advancing from a previous active day)
    if int(new_day) > last_rollover and arch != "freelancer":
        if (
            not state.get("mandatory_bounty_completed_today", False)
            and not state.get("mandatory_bounty_penalized_today", False)
            and state.get("mandatory_bounty_id")
        ):
            audit_res = update_agent_promotion_reputation(
                session_id=session_id,
                delta_rep=-15,
                reason="Missed Yesterday's Mandatory Daily Dispatch",
                is_missed_mandatory=True,
                user_id=host_uid,
            )
            state = audit_res.get("state") or get_anomalous_faction_state(session_id, user_id=host_uid)
            if audit_res.get("message"):
                notices.append(audit_res["message"])

    # 2. Public Agency Daily Salary Payout (50G - 300G by Tier)
    salary_paid = 0
    days_elapsed = max(1, int(new_day) - last_rollover) if int(new_day) > last_rollover else 1
    if arch == "public_agency":
        if state.get("salary_ration_suspended", False):
            notices.append("⚠️ Public Agency Daily Salary SUSPENDED (0 Rep Disciplinary Hold — complete today's Mandatory Dispatch to restore).")
        else:
            t_info = get_anomalous_promotion_tier_info(int(state.get("promotion_rep", 0) or 0))
            salary_paid = int(t_info.get("daily_salary", 50) or 50) * days_elapsed
            target_uids = party_uids if party_uids else ([host_uid] if host_uid else [])
            for uid in target_uids:
                if uid:
                    db.apply_hp_mp_delta(uid, gold_delta=salary_paid)
            notices.append(f"💳 Direct Deposit: +{salary_paid}G Public Agency Daily Salary ({t_info['title']}).")

    from mechanics.social.origin_mode import is_student_operative, STUDENT_DAILY_ALLOWANCE_GOLD
    if scenario_data.is_anomalous_high_school_scenario(scen_key) and is_student_operative(sess):
        allowance = STUDENT_DAILY_ALLOWANCE_GOLD * days_elapsed
        target_uids = party_uids if party_uids else ([host_uid] if host_uid else [])
        for uid in target_uids:
            if uid:
                db.apply_hp_mp_delta(uid, gold_delta=allowance)
        notices.append(f"💵 Daily Parent Allowance: +{allowance}G pocket money received.")

    # 3. Reset daily counters
    state["shrine_free_claims_today"] = 0
    state["shrine_free_claimed_today"] = 0
    state["mandatory_bounty_completed_today"] = False
    state["mandatory_bounty_penalized_today"] = False
    state["last_rollover_day"] = int(new_day)

    # 4. Auto-dispatch Today's Mandatory Daily Bounty via Morning SMS (for faction members)
    mandatory_quest = None
    if arch != "freelancer":
        try:
            from mechanics.narrative.bounty import dispatch_anomalous_mandatory_daily_bounty
            fac_disp_name = state.get("joined_faction_name", "Agency")
            mandatory_quest = dispatch_anomalous_mandatory_daily_bounty(
                session_id=session_id,
                current_day=int(new_day),
                faction_archetype_key=arch,
                faction_name=fac_disp_name,
                scen_key=scen_key,
            )
            if mandatory_quest:
                state["mandatory_bounty_id"] = str(mandatory_quest.get("quest_id") or "")
                sms_msg = (
                    f"[MANDATORY DAILY DISPATCH — Day {int(new_day)}] "
                    f"{mandatory_quest.get('title')}: {mandatory_quest.get('objective')}"
                )
                notices.append(f"📱 Mandatory Daily Dispatch assigned: [{mandatory_quest.get('title')}] at {mandatory_quest.get('location')}.")
                try:
                    db.save_phone_message(session_id, f"{fac_disp_name} Dispatch", "npc", sms_msg, intent="quest_comms")
                except Exception:
                    pass
        except Exception:
            pass

    save_anomalous_faction_state(session_id, state, user_id=host_uid)

    # 5. Roll 2-3 Optional Daily Anomalous Incursions (first clearing yesterday's expired breaches out of the scene)
    try:
        prune_expired_incursion_anomalies_from_scene(
            session_id, list(sess.get("daily_incursions") or sess.get("daily_breaches") or []), session=sess
        )
    except Exception:
        pass
    inc_res = roll_daily_anomalous_incursions(session_id, int(new_day), scen_key=scen_key)
    if inc_res.get("broadcast_sms"):
        notices.append(inc_res["broadcast_sms"])
        try:
            db.save_phone_message(session_id, "Metropolitan Anomaly Watch", "npc", inc_res["broadcast_sms"], intent="quest_comms")
        except Exception:
            pass

    return {
        "processed": True,
        "day": int(new_day),
        "salary_paid": salary_paid,
        "mandatory_bounty": mandatory_quest,
        "daily_incursions": inc_res.get("incursions", []),
        "daily_breaches": inc_res.get("incursions", []),
        "notices": notices,
        "state": state,
    }


def resolve_anomalous_starting_location(
    session_id: int,
    starting_faction: str = "public_agency",
    scen_key: str = "anomalous_incursions",
    char_name: str = "",
) -> Dict[str, str]:
    """
    Resolves the exact starting world_node_id and tiered 3-level location string
    for an Anomalous Incursions session based on the player's chosen starting_faction:
      - public_agency   -> Agency HQ -> Main Lobby & Security Hub -> Reception Rotunda
      - private_agency_1 -> Corporate Tower HQ -> Corporate Atrium & Biometric Lobby
      - private_agency_2 -> Field Office HQ -> Walk-Up Commercial Foyer & Reception Desk
      - monastic_order  -> Eastern Grand Temple -> Main Worship Hall -> Incense Courtyard
      - freelancer      -> Suburban Residential District -> Player's House -> Living Room
    """
    from mechanics.world.locations.graph_seeder import ensure_session_spatial_graph_seeded
    from mechanics.world.locations.seeds import (
        get_session_urban_zone_name,
        get_session_urban_facility_name,
        get_session_player_house_name,
    )
    import namegen

    ensure_session_spatial_graph_seeded(session_id, scen_key, char_name=char_name)

    fac_clean = str(starting_faction or "public_agency").strip().lower()
    if fac_clean in ("private_agency", "private_1"):
        fac_clean = "private_agency_1"
    elif fac_clean == "private_2":
        fac_clean = "private_agency_2"
    elif fac_clean in ("leave", "none", "independent"):
        fac_clean = "freelancer"
    elif fac_clean in ("student_freelancer", "student", "high_school", "school"):
        fac_clean = "student_freelancer"

    if fac_clean == "private_agency_1":
        candidate_ids = ["sub_priv1_entrance", "sub_priv1_dispatch", "loc_private_hq_1"]
        h_val = int(session_id) if session_id else 1
        urban_core_zones = ["zone_city_center", "zone_downtown", "zone_uptown"]
        p1_z_id = urban_core_zones[h_val % 3]
        z_name = get_session_urban_zone_name(session_id, p1_z_id, "City Center", scen_key)
        p1_name = namegen.generate_private_agency_name(scen_key, hash_val=h_val, agency_index=1)
        p1_acr = namegen.format_org_acronym(p1_name)
        p1_hq = f"{p1_acr} Corporate Tower HQ" if p1_acr else f"{p1_name} Tower HQ"
        fallback_loc = f"{z_name} ➔ {p1_hq} ➔ Corporate Atrium & Biometric Lobby"
    elif fac_clean == "private_agency_2":
        candidate_ids = ["sub_priv2_entrance", "sub_priv2_dispatch", "loc_private_hq_2"]
        h_val = int(session_id) if session_id else 1
        urban_core_zones = ["zone_city_center", "zone_downtown", "zone_uptown"]
        p2_z_id = urban_core_zones[(h_val + 1) % 3]
        z_name = get_session_urban_zone_name(session_id, p2_z_id, "Downtown", scen_key)
        p1_name = namegen.generate_private_agency_name(scen_key, hash_val=h_val, agency_index=1)
        p2_name = namegen.generate_private_agency_name(scen_key, hash_val=h_val, agency_index=2)
        if p2_name == p1_name:
            p2_name = namegen.generate_private_agency_name(scen_key, hash_val=h_val + 99, agency_index=3)
        p2_acr = namegen.format_org_acronym(p2_name)
        p2_hq = f"{p2_acr} Field Office HQ" if p2_acr else f"{p2_name} Office HQ"
        fallback_loc = f"{z_name} ➔ {p2_hq} ➔ Walk-Up Commercial Foyer & Reception Desk"
    elif fac_clean == "monastic_order":
        candidate_ids = ["loc_et_main_sanctuary"]
        z_name = get_session_urban_zone_name(session_id, "zone_woods_reserve", "Woods & Mountain Reserve", scen_key)
        c_name = get_session_urban_facility_name(session_id, "zone_woods_reserve", "loc_eastern_temple", "Eastern Grand Temple & Sanctuary", scen_key)
        fallback_loc = f"{z_name} ➔ {c_name} ➔ Main Worship Hall & Incense Courtyard"
    elif fac_clean == "freelancer":
        candidate_ids = ["sub_player_living_room", "sub_player_front_porch", "loc_player_house"]
        z_name = get_session_urban_zone_name(session_id, "zone_suburbs", "Suburban Residential District", scen_key)
        f_name = get_session_player_house_name(session_id, char_name=char_name, scenario_key=scen_key)
        fallback_loc = f"{z_name} ➔ {f_name} ➔ Cozy Living Room & Kitchenette"
    elif fac_clean == "student_freelancer":
        from mechanics.social.origin_mode import get_session_student_grade
        from mechanics.world.locations.seeds import get_session_school_name
        grade = get_session_student_grade(db.get_session(session_id) or {})
        grade_node_map = {
            "freshman": "loc_freshman_class",
            "sophomore": "loc_sophomore_class",
            "junior": "loc_junior_class",
            "senior": "loc_senior_class",
        }
        target_class_id = grade_node_map.get(str(grade or "sophomore").lower(), "loc_sophomore_class")
        candidate_ids = [target_class_id, "loc_homeroom", "loc_main_academic", "loc_school_gate"]
        school_name = get_session_school_name(session_id, scen_key) or "Main Academy Campus"
        fallback_loc = f"{school_name} ➔ Main Academic Building ➔ Homeroom & Classrooms"
    else:
        candidate_ids = ["loc_hq_main_lobby"]
        z_name = get_session_urban_zone_name(session_id, "zone_city_center", "City Center", scen_key)
        hq_name = namegen.generate_agency_hq_name(scen_key, hash_val=int(session_id or 1))
        f_name = get_session_urban_facility_name(session_id, "zone_agency_hq", "loc_hq_main_lobby", "Main Lobby & Security Hub", scen_key)
        fallback_loc = f"{z_name} ➔ {hq_name} ➔ {f_name}"

    chosen_node_id = candidate_ids[-1]
    location_display = fallback_loc
    for cid in candidate_ids:
        node = db.get_world_node(session_id, cid)
        if node:
            chosen_node_id = cid
            ancestors = db.get_node_ancestors(session_id, cid)
            chain = [a["name"] for a in reversed(ancestors)] + [node["name"]]
            if chain:
                location_display = " ➔ ".join(chain)
            break

    return {
        "node_id": chosen_node_id,
        "location_display": location_display,
        "faction_archetype_key": fac_clean,
    }


def bootstrap_anomalous_session(
    session_id: int,
    scenario_key: str,
    user_id: int,
    starting_faction: str = "public_agency",
    char_name: str = "",
    origin_mode: str = "",
    student_grade: str = "Sophomore",
) -> Dict[str, Any]:
    """
    Shared Day-1 bootstrap for Anomalous Incursions across Web API and Discord:
    seeds 6 fixed factions, joins `starting_faction`, seeds 44 Special Agents,
    seeds World-Ending Anomaly blueprint, sets starting HQ/Home location,
    and dispatches Day 1 Mandatory Bounty + Daily Incursions + Morning SMS alerts.
    """
    from mechanics.social.factions import (
        ensure_starter_factions,
        join_or_transfer_anomalous_faction,
        get_anomalous_faction_state,
        save_anomalous_faction_state,
    )
    from mechanics.social.origin_mode import set_session_origin


    if scenario_data.is_anomalous_high_school_scenario(scenario_key):
        eff_origin = "student" if (origin_mode == "student" or starting_faction in ("student_freelancer", "student")) else "adult"
        set_session_origin(session_id, eff_origin, student_grade)

        if eff_origin == "student":
            starting_faction = "student_freelancer"
    from mechanics.social.agent_roster import ensure_anomalous_agent_roster
    from mechanics.narrative.blueprints import ensure_world_ending_anomaly_blueprint
    from mechanics.narrative.bounty import dispatch_anomalous_mandatory_daily_bounty

    ensure_starter_factions(session_id, scenario_key)
    join_or_transfer_anomalous_faction(session_id, starting_faction, user_id=user_id)

    start_loc = resolve_anomalous_starting_location(
        session_id=session_id,
        starting_faction=starting_faction,
        scen_key=scenario_key,
        char_name=char_name,
    )
    ensure_anomalous_agent_roster(session_id, scenario_key)
    ensure_world_ending_anomaly_blueprint(session_id)
    db.update_session(
        session_id,
        current_node_id=start_loc["node_id"],
        current_location=start_loc["location_display"],
        extra={"anomalous_starting_location": start_loc["location_display"]},
    )

    fac_state = get_anomalous_faction_state(session_id, user_id=user_id)
    f_arch = str(fac_state.get("faction_archetype_key") or "public_agency")
    mand_q = None
    if f_arch != "freelancer":
        fac_disp_name = fac_state.get("joined_faction_name", "Agency")
        mand_q = dispatch_anomalous_mandatory_daily_bounty(
            session_id=session_id,
            current_day=1,
            faction_archetype_key=f_arch,
            faction_name=fac_disp_name,
            scen_key=scenario_key,
        )
        if mand_q:
            fac_state["mandatory_bounty_id"] = str(mand_q.get("quest_id") or "")
            save_anomalous_faction_state(session_id, fac_state, user_id=user_id)
            try:
                sms_msg = f"[MANDATORY DAILY DISPATCH — Day 1] {mand_q.get('title')}: {mand_q.get('objective')}"
                db.save_phone_message(session_id, f"{fac_disp_name} Dispatch", "npc", sms_msg, intent="quest_comms")
            except Exception:
                pass

    inc_res = roll_daily_anomalous_incursions(session_id, 1, scen_key=scenario_key)
    if inc_res.get("broadcast_sms"):
        try:
            db.save_phone_message(session_id, "Metropolitan Anomaly Watch", "npc", inc_res["broadcast_sms"], intent="quest_comms")
        except Exception:
            pass

    return {
        "start_location": start_loc,
        "mandatory_bounty": mand_q,
        "daily_incursions": inc_res.get("incursions", []),
        "daily_breaches": inc_res.get("incursions", []),
    }




# ---------------------------------------------------------------------------
# Package Aliases & Facades
# ---------------------------------------------------------------------------
roll_daily_anomaly_breaches = roll_daily_anomalous_incursions
get_active_breach_at_location = get_active_incursion_at_location
resolve_non_hostile_breach_action = resolve_non_hostile_incursion_action
mark_hostile_breach_resolved_on_victory = mark_hostile_incursion_resolved_on_victory
