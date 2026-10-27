from __future__ import annotations
"""
Daily Anomalous Incursions, Non-Hostile Entity Pacification/Agitation,
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
        "description": "An acoustic violinist trapped in a 4.7-second temporal loop; its bowstring hums with razor-sharp kinetic tension whenever its melody is rudely interrupted.",
        "preferred_stat": "INT",
        "containment_note": "Stabilized via a metronomic reality anchor; now resides in a soundproofed conservatory suite.",
    },
    {
        "title": "Bioluminescent Moss Spirit",
        "category_tag": "bio_aberration",
        "temperament": "timid",
        "description": "A shy, floating colony of sentient bioluminescent spores drifting near storm grates, ready to disperse into microscopic mist at the slightest alarm.",
        "preferred_stat": "PER",
        "containment_note": "Cultivated inside Bio-Containment Atrium 3; emits a soothing blue glow that lowers nearby psychic static.",
    },
    {
        "title": "Porcelain Mannequin Sentinel",
        "category_tag": "cursed_relic",
        "temperament": "volatile",
        "description": "A display mannequin pacing a closed boutique aisle in silent choreography; its ball-jointed limbs snap into territorial defensive stances when crowded.",
        "preferred_stat": "AGI",
        "containment_note": "Secured upright inside Velvet Vault 07 with silk-padded restraints; remains tranquil when dressed in vintage winter coats.",
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
) -> Dict[str, Any]:
    """
    Spawns 2-3 optional Daily Anomalous Incursions across random city facilities
    (and Tier-3 wings inside consolidated multi-wing complexes) for `current_day`.
    Unresolved incursions from previous days expire at midnight with 0 penalty.
    Returns `{"incursions": [...], "broadcast_sms": "..."}`.
    """
    if not scenario_data.is_anomalous_incursions_scenario(scen_key):
        return {"incursions": [], "broadcast_sms": ""}

    sess = db.get_session(session_id) or {}
    existing = sess.get("daily_incursions") or []
    # If already rolled for current_day, return existing
    today_existing = [inc for inc in existing if int(inc.get("day", 0) or 0) == int(current_day)]
    if today_existing:
        return {
            "incursions": today_existing,
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
            if z_id == "zone_agency_hq":
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
    for idx, loc in enumerate(chosen_locs):
        # Ensure a mix of hostile, non-hostile entity, and phenomenon across the 2-3 spawns
        subtype = INCURSION_SUBTYPES[(idx + int(current_day)) % len(INCURSION_SUBTYPES)]
        inc_id = f"inc_d{current_day}_{idx + 1}_{loc['node_id']}"

        temperament = ""
        if subtype == "hostile_breach":
            cat_tag = rng.choice(["cognitohazard", "spatial_warp", "bio_aberration", "cursed_relic", "spectral_echo"])
            entity_name = namegen.generate_anomalous_entity_name(
                category_tag=cat_tag,
                hash_val=int(session_id or 1) + current_day * 37 + idx * 19,
            )
            title = f"Hostile Breach: {entity_name}"
            desc = (
                f"Sensors detect an aggressive {cat_tag.replace('_', ' ')} manifestation ({entity_name}) "
                f"destabilizing the perimeter at {loc['facility_name']}."
            )
            preferred_stat = "STR"
            containment_note = f"Neutralized and core-harvested during field incursion at {loc['facility_name']}."
        elif subtype == "non_hostile_entity":
            tmpl = rng.choice(NON_HOSTILE_ENTITY_TEMPLATES)
            entity_name = tmpl["title"]
            cat_tag = tmpl["category_tag"]
            temperament = tmpl.get("temperament", "timid")
            title = f"Non-Hostile Entity: {entity_name}"
            desc = tmpl["description"]
            preferred_stat = tmpl["preferred_stat"]
            containment_note = tmpl["containment_note"]
        else:
            tmpl = rng.choice(PHENOMENON_TEMPLATES)
            entity_name = tmpl["title"]
            cat_tag = tmpl["category_tag"]
            title = f"Anomalous Phenomenon: {entity_name}"
            desc = tmpl["description"]
            preferred_stat = tmpl["preferred_stat"]
            containment_note = tmpl["containment_note"]

        incursions.append({
            "incursion_id": inc_id,
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
            "node_id": loc["node_id"],
            "zone_name": loc["zone_name"],
            "facility_name": loc["facility_name"],
            "location": loc["full_location"],
            "reward_gold": 120 + (idx * 35),
            "reward_xp": 85 + (idx * 25),
            "resolved": False,
            "agitated": False,
            "escaped": False,
            "killed_lethally": False,
            "optional": True,
        })

    db.update_session(session_id, extra={"daily_incursions": incursions})
    broadcast_sms = _format_incursion_broadcast_sms(incursions, current_day)
    return {"incursions": incursions, "broadcast_sms": broadcast_sms}


def _format_incursion_broadcast_sms(incursions: List[Dict[str, Any]], current_day: int) -> str:
    if not incursions:
        return ""
    lines = [f"📡 [METROPOLITAN ANOMALY ALERT — DAY {current_day}]"]
    lines.append(f"{len(incursions)} optional Anomalous Incursion(s) detected across the city today (expire at 24:00 with no penalty):")
    for inc in incursions:
        badge = "⚔️ Hostile" if inc["subtype"] == "hostile_breach" else ("🕊️ Non-Hostile" if inc["subtype"] == "non_hostile_entity" else "🌀 Phenomenon")
        lines.append(f"• [{badge}] {inc['entity_name']} @ {inc['location']}")
    return "\n".join(lines)


def get_active_incursion_at_location(
    session_id: int,
    location_str: str = "",
    node_id: str = "",
) -> Optional[Dict[str, Any]]:
    """Returns an unresolved Daily Anomalous Incursion matching the given location/node_id, if any."""
    if not session_id:
        return None
    sess = db.get_session(session_id) or {}
    if not scenario_data.is_anomalous_incursions_scenario(sess.get("scenario", "")):
        return None
    incursions = sess.get("daily_incursions") or []
    loc_low = str(location_str or sess.get("current_location") or "").strip().lower()
    nid_low = str(node_id or sess.get("current_node_id") or "").strip().lower()

    for inc in incursions:
        if inc.get("resolved"):
            continue
        inc_nid = str(inc.get("node_id") or "").strip().lower()
        inc_fac = str(inc.get("facility_name") or "").strip().lower()
        if (inc_nid and inc_nid == nid_low) or (inc_fac and inc_fac in loc_low):
            return dict(inc)
        if inc_nid and nid_low and session_id:
            try:
                if db.is_descendant_of(session_id, nid_low, inc_nid):
                    return dict(inc)
            except Exception:
                pass
    return None


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
    Deterministically returns `'timid'` (Elusive — escapes on max strikes) or
    `'volatile'` (Territorial — turns hostile in combat on max strikes).
    """
    exp_clean = str(explicit or "").strip().lower()
    if exp_clean in ("timid", "volatile"):
        return exp_clean

    m = re.search(r"non_hostile_temperament:(timid|volatile)", str(quest_notes or ""), re.IGNORECASE)
    if m:
        return m.group(1).strip().lower()

    digest = hashlib.md5(str(seed_key or "default_entity").encode("utf-8")).digest()
    return "timid" if (digest[0] % 2 == 0) else "volatile"


def get_temperament_scene_hint(entity_name: str, temperament: str) -> str:
    """Returns a narrative scene hint telegraphing whether repeated failures cause escape or combat."""
    ent = str(entity_name or "The anomalous entity").strip()
    if str(temperament or "").strip().lower() == "volatile":
        return (
            f"{ent} exhibits a **volatile, territorial aura**—static arcs violently whenever cornered, "
            f"signaling it will lash out in combat if provoked by repeated failed containment attempts."
        )
    return (
        f"{ent} exhibits a **timid, skittish demeanor**—hovering near an unstable spatial seam, "
        f"poised to slip away and vanish if startled by repeated failed containment attempts."
    )


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
) -> List[Dict[str, Any]]:
    """
    Builds all 4 guaranteed out-of-combat narrative containment choices:
      1. Persuade (CHA)
      2. Calm (PER)
      3. Outwit (INT)
      4. Use Environment (AGI)
    Supports both `mode='quest'` (Bounties / Story Quests) and `mode='incursion'` (Daily Incursions).
    """
    ent = str(entity_name or "the Anomalous Entity").strip()
    stats_dict = (char or {}).get("stats") if isinstance((char or {}).get("stats"), dict) else {}
    stat_col_map = {"STR": "str_", "PER": "per_", "END": "end_", "CHA": "cha", "INT": "int_", "AGI": "agi", "LUK": "luk"}

    prefix = "Story Quest" if is_story_quest else "Bounty"
    q_icon = "⭐" if is_story_quest else "🎯"

    choices: List[Dict[str, Any]] = []
    for spec in NON_HOSTILE_APPROACH_SPECS:
        stat = spec["stat"]
        if stats_dict and stat in stats_dict:
            c_stat_val = int(stats_dict.get(stat, 5) or 5)
        elif isinstance(char, dict) and stat_col_map.get(stat) in char:
            c_stat_val = int(char.get(stat_col_map[stat], 5) or 5)
        else:
            c_stat_val = 6

        if mode == "incursion":
            req = 7
            lbl = f"{spec['icon']} [{spec['tag']}] {spec['verb_template'].format(entity_name=ent)} (Optional)"
            choices.append({
                "label": lbl[:190],
                "stat": stat,
                "requirement": req,
                "mp_cost": 0,
                "intent": "anomalous_incursion_action",
                "incursion_action": spec["incursion_action"],
                "incursion_id": incursion_id,
            })
        else:
            req = max(3, min(8, c_stat_val))
            if dc_mod > 0:
                req = min(12, req + dc_mod)
            lbl = f"{q_icon} [{prefix}] [{spec['tag']}] {spec['verb_template'].format(entity_name=ent)} ({stat})"
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
                "dc_mod": dc_mod,
            })
    return choices


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
) -> Dict[str, Any]:
    """
    Appends a secured Non-Hostile Entity or Altered Item/Phenomenon to `session['contained_anomalies_log']`
    for display in the Containment Vaults, Reliquary Pagoda, Private Vault, and Agent Dossier UI.
    Strictly flavor registry only (no passive buffs or combat summons). Deduplicates per quest/sub_obj.
    """
    from mechanics.social.factions import get_anomalous_faction_state

    sess = db.get_session(session_id) or {}
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
        "day_captured": int(sess.get("current_day", 1) or 1),
        "resolution_method": resolution_method,
        "vault_facility": vault_facility,
        "containment_note": containment_note or f"Safely contained at {vault_facility}.",
    }
    if quest_id:
        entry["quest_id"] = str(quest_id)
        if sub_obj_id is not None:
            entry["sub_obj_id"] = sub_obj_id

    log_list.append(entry)
    db.update_session(session_id, extra={"contained_anomalies_log": log_list})
    return entry


def spawn_agitated_non_hostile_entity(
    session_id: int,
    entity_name: str,
    *,
    location: str = "",
    category_tag: str = "spatial_warp",
    incursion_id: str = "",
    quest_id: str = "",
    sub_obj_id: Optional[int] = None,
    is_story_quest: bool = False,
    session: Optional[Dict[str, Any]] = None,
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
    enemy_obj["subdue_threshold_pct"] = NON_HOSTILE_SUBDUE_THRESHOLD_PCT
    enemy_obj["temperament"] = "volatile"
    enemy_obj["category_tag"] = category_tag
    if incursion_id:
        enemy_obj["incursion_id"] = incursion_id
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
    user_id: Optional[int],
    action_type: str = "subdue",
    incursion_id: str = "",
    quest_id: str = "",
    force_roll: Optional[int] = None,
    pre_rolled_check: Any = None,
    party_user_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Resolves in-combat Non-Lethal Containment on an agitated `requires_non_lethal_subdue` entity:
    - `action_type == 'subdue'`:
      Requires `0 < hp <= max(1, int(max_hp * 0.35))` (`<= 35%` HP). Automatically captures & seals!
    - `action_type == 'combat_persuade'`:
      Available at ANY `hp > 0` (`CHA` de-escalation check; DC `6` if `<= 50%` HP else DC `8`).
      On success, calms & contains the entity alive! On failure, combat continues (`combat_continues=True`).
    Works for BOTH Daily Anomalous Incursions (`incursion_id`) and Agitated Quest/Bounty Entities (`linked_quest_id`).
    """
    sess = db.get_session(session_id) or {}
    scen_key = str(sess.get("scenario") or "anomalous_incursions")
    enemies = list(sess.get("nearby_enemies") or [])
    target_enemy = next(
        (
            e for e in enemies
            if isinstance(e, dict)
            and (
                (incursion_id and e.get("incursion_id") == incursion_id)
                or (quest_id and e.get("linked_quest_id") == quest_id)
                or e.get("requires_non_lethal_subdue")
            )
        ),
        enemies[0] if enemies else None,
    )
    if not target_enemy:
        return {"success": False, "error": "No agitated anomalous entity present to contain."}

    ent_name = str(target_enemy.get("name") or "Anomalous Entity")
    hp = int(target_enemy.get("hp", 10) or 10)
    max_hp = max(1, int(target_enemy.get("max_hp", 40) or 40))
    threshold_pct = float(target_enemy.get("subdue_threshold_pct") or NON_HOSTILE_SUBDUE_THRESHOLD_PCT)
    threshold_hp = max(1, int(max_hp * threshold_pct))
    act = str(action_type or "subdue").strip().lower()

    p_uids = list(party_user_ids or ([user_id] if user_id else ([sess.get("host_user_id")] if sess.get("host_user_id") else [1])))
    lead_uid = user_id or (p_uids[0] if p_uids else 1)
    char = db.get_character(lead_uid) or {}

    if act == "combat_persuade":
        dc = 6 if hp <= max(1, int(max_hp * 0.50)) else 8
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
        method_str = f"De-escalated & Contained in Combat (CHA {total_check})"
    else:
        if hp > threshold_hp and force_roll is None:
            return {
                "success": False,
                "agitated": True,
                "combat_continues": True,
                "message": (
                    f"⚠️ **{ent_name}** is still too thrashing to seal ({hp}/{max_hp} HP)! "
                    f"Carefully weaken it to <= {int(threshold_pct * 100)}% HP ({threshold_hp} HP) without killing it, "
                    f"or attempt **[🗣️ Persuade / Calm]**!"
                ),
            }
        method_str = "Subdued Non-Lethally & Contained"

    # Remove subdued/de-escalated entity from combat!
    remaining = [e for e in enemies if e is not target_enemy]
    db.update_session(session_id, nearby_enemies=remaining)

    eff_inc_id = str(incursion_id or target_enemy.get("incursion_id") or "")
    eff_quest_id = str(quest_id or target_enemy.get("linked_quest_id") or "")
    eff_sub_obj_id = target_enemy.get("linked_sub_obj_id")
    cat_tag = str(target_enemy.get("category_tag") or "spatial_warp")

    # Path A: Linked Daily Anomalous Incursion
    incursions = list(sess.get("daily_incursions") or [])
    target_inc = next((inc for inc in incursions if eff_inc_id and inc.get("incursion_id") == eff_inc_id), None)
    if target_inc:
        for inc in incursions:
            if inc.get("incursion_id") == eff_inc_id:
                inc["resolved"] = True
                inc["agitated"] = False
        db.update_session(session_id, extra={"daily_incursions": incursions})

        gold_gain = int(target_inc.get("reward_gold", 120) or 120)
        xp_gain = int(target_inc.get("reward_xp", 85) or 85)
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
        dropped_gear = _roll_optional_incursion_gear_drop(lead_uid, scen_key)
        gear_suffix = f" Recovered salvage: **{dropped_gear}**!" if dropped_gear else ""
        icon_used = "🗣️" if act == "combat_persuade" else "🛡️"
        return {
            "success": True,
            "resolved": True,
            "subdued": True,
            "reward_gold": gold_gain,
            "reward_xp": xp_gain,
            "reward_item": dropped_gear,
            "vault_entry": vault_entry,
            "message": (
                f"{icon_used} Contained **{target_inc['entity_name']}** alive! "
                f"Earned +{gold_gain}G, +{xp_gain} XP, and logged into {vault_entry['vault_facility']}.{gear_suffix}"
            ),
        }

    # Path B: Linked Bounty or Story Quest Sub-Objective
    if not eff_quest_id:
        for q_cand in (db.get_session_quests(session_id, status="Active") or []):
            if is_non_hostile_entity_quest(q_cand):
                eff_quest_id = str(q_cand.get("quest_id") or "")
                break

    quest_res = {}
    if eff_quest_id:
        quest_res = _complete_or_advance_linked_quest_containment(
            session_id=session_id,
            quest_id=eff_quest_id,
            sub_obj_id=eff_sub_obj_id,
            entity_name=ent_name,
            category_tag=cat_tag,
            resolution_method=method_str,
            party_user_ids=p_uids,
        )

    vault_entry = quest_res.get("vault_entry") or record_contained_anomaly_to_vault_log(
        session_id=session_id,
        entity_name=ent_name,
        category_tag=cat_tag,
        subtype="non_hostile_entity",
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

    icon_used = "🗣️" if act == "combat_persuade" else "🛡️"
    return {
        "success": True,
        "resolved": True,
        "subdued": True,
        "quest_containment": quest_res,
        "vault_entry": vault_entry,
        "message": (
            f"{icon_used} Contained **{ent_name}** alive and sealed it into a containment unit! "
            f"Logged to {vault_entry['vault_facility']}.{follow_note}"
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

    inc_id = str(dead_enemy.get("incursion_id") or "")
    if inc_id:
        fresh_sess = db.get_session(session_id) or sess
        incursions = list(fresh_sess.get("daily_incursions") or [])
        for inc in incursions:
            if inc.get("incursion_id") == inc_id:
                inc["resolved"] = True
                inc["agitated"] = False
                inc["killed_lethally"] = True
        db.update_session(session_id, extra={"daily_incursions": incursions})
        if isinstance(session, dict):
            session["daily_incursions"] = incursions
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
    incursion_id: str,
    action_type: str = "pacify",
    stat_used: str = "CHA",
    force_roll: Optional[int] = None,
    pre_rolled_check: Any = None,
) -> Dict[str, Any]:
    """
    Resolves an interaction with a Daily Anomalous Incursion:
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
    sess = db.get_session(session_id) or {}
    scen_key = str(sess.get("scenario") or "anomalous_incursions")
    incursions = list(sess.get("daily_incursions") or [])
    target_inc = next((inc for inc in incursions if inc.get("incursion_id") == incursion_id), None)
    if not target_inc:
        target_inc = get_active_incursion_at_location(session_id)
        if target_inc:
            incursion_id = target_inc["incursion_id"]
    if not target_inc:
        return {"success": False, "error": "No active Anomalous Incursion found."}
    if target_inc.get("resolved"):
        return {"success": False, "already_resolved": True, "error": "This Anomalous Incursion has already been contained."}

    act = str(action_type or "pacify").strip().lower()
    if act in ("subdue", "combat_persuade"):
        return resolve_anomalous_combat_containment(
            session_id=session_id,
            user_id=user_id,
            action_type=act,
            incursion_id=incursion_id,
            force_roll=force_roll,
            pre_rolled_check=pre_rolled_check,
        )

    if target_inc.get("subtype") == "hostile_breach":
        act = "attack"

    approach_default_stats = {
        "persuade": "CHA",
        "calm": "PER",
        "outwit": "INT",
        "environment": "AGI",
        "pacify": str(target_inc.get("preferred_stat") or "CHA").upper(),
        "analyze": "INT",
        "observe": "PER",
    }
    approach_method_labels = {
        "persuade": "Persuaded & Contained Willingly",
        "calm": "Calmed & Sealed Non-Lethally",
        "outwit": "Outwitted into Containment Snare",
        "environment": "Cornered via Environmental Containment",
        "analyze": "Analyzed & Sealed",
        "pacify": "Pacified & Contained",
    }

    char = db.get_character(user_id) or {}
    stat_key = str(stat_used or approach_default_stats.get(act) or target_inc.get("preferred_stat") or "CHA").upper()

    # Intentional attack on hostile_breach or non_hostile_entity immediately starts combat
    if act == "attack" and target_inc.get("subtype") in ("non_hostile_entity", "hostile_breach"):
        if target_inc.get("subtype") == "non_hostile_entity":
            enemy_obj = spawn_agitated_non_hostile_entity(
                session_id=session_id,
                entity_name=target_inc["entity_name"],
                location=target_inc.get("location", "City"),
                category_tag=target_inc.get("category_tag", "spatial_warp"),
                incursion_id=incursion_id,
            )
            breach_msg = (
                f"⚠️ **{target_inc['entity_name']}** has turned hostile in self-defense! "
                f"Carefully weaken it to <= 35% HP to use **[🛡️ Subdue & Contain]**, or use **[🗣️ Persuade / Calm]** "
                f"(killing it destroys the specimen and forfeits all rewards)!"
            )
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
            enemy_obj["incursion_id"] = incursion_id
            enemies = list(sess.get("nearby_enemies") or [])
            enemies.append(enemy_obj)
            db.update_session(session_id, nearby_enemies=enemies)
            breach_msg = f"⚔️ Hostile Breach Engaged: **{target_inc['entity_name']}** lunges from the spatial tear! Defeat it in combat to seal the incursion!"

        for inc in incursions:
            if inc.get("incursion_id") == incursion_id:
                inc["agitated"] = True
        db.update_session(session_id, extra={"daily_incursions": incursions})
        return {
            "success": False,
            "agitated": True,
            "combat_started": True,
            "enemy": enemy_obj,
            "message": breach_msg,
        }

    nat_roll, total_check, check_succeeded = _extract_check_roll_and_success(
        char=char,
        stat_key=stat_key,
        dc=10,
        force_roll=force_roll,
        pre_rolled_check=pre_rolled_check,
    )

    # Success resolution (seal_ability or check_succeeded)
    if act == "seal_ability" or check_succeeded:
        for inc in incursions:
            if inc.get("incursion_id") == incursion_id:
                inc["resolved"] = True
                inc["agitated"] = False
        db.update_session(session_id, extra={"daily_incursions": incursions})

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
        dropped_gear = _roll_optional_incursion_gear_drop(user_id, scen_key)
        gear_suffix = f" Recovered salvage: **{dropped_gear}**!" if dropped_gear else ""
        return {
            "success": True,
            "resolved": True,
            "approach": act,
            "reward_gold": gold_gain,
            "reward_xp": xp_gain,
            "reward_item": dropped_gear,
            "vault_entry": vault_entry,
            "message": (
                f"✨ Successfully contained **{target_inc['entity_name']}** via {approach_method_labels.get(act, 'Containment Protocol')}! "
                f"Earned +{gold_gain}G, +{xp_gain} XP, and logged into {vault_entry['vault_facility']}.{gear_suffix}"
            ),
        }

    # Failed check handling on Non-Hostile Entity: Temperament-Driven Strike Escalation!
    if target_inc.get("subtype") == "non_hostile_entity":
        temperament = get_non_hostile_entity_temperament(
            seed_key=incursion_id,
            explicit=str(target_inc.get("temperament") or ""),
        )
        prev_strikes = int(target_inc.get("strikes", 0) or 0)
        max_strikes = int(target_inc.get("max_strikes", 2) or 2)
        strike_delta = 2 if nat_roll <= 2 else 1
        new_strikes = prev_strikes + strike_delta

        if new_strikes < max_strikes:
            for inc in incursions:
                if inc.get("incursion_id") == incursion_id:
                    inc["strikes"] = new_strikes
                    inc["temperament"] = temperament
            db.update_session(session_id, extra={"daily_incursions": incursions})
            if temperament == "timid":
                warn_msg = (
                    f"⚠️ Containment attempt on **{target_inc['entity_name']}** faltered ({stat_key} {total_check} vs DC 10) "
                    f"[{new_strikes}/{max_strikes} Strikes]! Startled, it edges toward an escape seam—one more failed check and it will vanish!"
                )
            else:
                warn_msg = (
                    f"⚠️ Containment attempt on **{target_inc['entity_name']}** faltered ({stat_key} {total_check} vs DC 10) "
                    f"[{new_strikes}/{max_strikes} Strikes]! Its anomalous aura bristles aggressively—one more failed check and it will turn hostile!"
                )
            return {
                "success": False,
                "resolved": False,
                "agitated": False,
                "escaped": False,
                "temperament": temperament,
                "strikes": new_strikes,
                "max_strikes": max_strikes,
                "roll": nat_roll,
                "total": total_check,
                "message": warn_msg,
            }

        # Max strikes reached (>= 2): branch by temperament!
        if temperament == "timid":
            for inc in incursions:
                if inc.get("incursion_id") == incursion_id:
                    inc["strikes"] = new_strikes
                    inc["resolved"] = True
                    inc["escaped"] = True
                    inc["agitated"] = False
            db.update_session(session_id, extra={"daily_incursions": incursions})
            return {
                "success": False,
                "resolved": True,
                "escaped": True,
                "agitated": False,
                "temperament": "timid",
                "strikes": new_strikes,
                "max_strikes": max_strikes,
                "roll": nat_roll,
                "total": total_check,
                "message": (
                    f"💨 **Entity Escaped!** Startled by repeated failed containment attempts ({stat_key} {total_check} vs DC 10), "
                    f"**{target_inc['entity_name']}** slipped through a spatial seam and vanished! Live-containment rewards forfeited."
                ),
            }

        # Volatile temperament -> Agitated Combat!
        enemy_obj = spawn_agitated_non_hostile_entity(
            session_id=session_id,
            entity_name=target_inc["entity_name"],
            location=target_inc.get("location", "City"),
            category_tag=target_inc.get("category_tag", "spatial_warp"),
            incursion_id=incursion_id,
        )
        for inc in incursions:
            if inc.get("incursion_id") == incursion_id:
                inc["strikes"] = new_strikes
                inc["agitated"] = True
                inc["temperament"] = "volatile"
        db.update_session(session_id, extra={"daily_incursions": incursions})
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
                f"⚠️ **Entity Agitated into Combat!** Provoked by repeated containment failures ({stat_key} {total_check} vs DC 10), "
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
        "message": f"Containment attempt on {target_inc['entity_name']} faltered ({stat_key} check {total_check} vs DC 10), but the anomaly remains stable enough to try again.",
    }


def mark_hostile_incursion_resolved_on_victory(
    session_id: int,
    incursion_id: str,
    user_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Marks a hostile Daily Anomalous Incursion resolved upon defeating its breach entity in combat."""
    if not session_id or not incursion_id:
        return None
    sess = db.get_session(session_id) or {}
    scen_key = str(sess.get("scenario") or "anomalous_incursions")
    incursions = list(sess.get("daily_incursions") or [])
    target_inc = next(
        (inc for inc in incursions if inc.get("incursion_id") == incursion_id and not inc.get("resolved")),
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

    for inc in incursions:
        if inc.get("incursion_id") == incursion_id:
            inc["resolved"] = True
            inc["agitated"] = False
    db.update_session(session_id, extra={"daily_incursions": incursions})

    gold_gain = int(target_inc.get("reward_gold", 140) or 140)
    xp_gain = int(target_inc.get("reward_xp", 100) or 100)
    dropped_gear = _roll_optional_incursion_gear_drop(user_id, scen_key)
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
    )
    gear_suffix = f" Salvaged **{dropped_gear}**!" if dropped_gear else ""
    return {
        "resolved": True,
        "reward_gold": gold_gain,
        "reward_xp": xp_gain,
        "reward_item": dropped_gear,
        "vault_entry": vault_entry,
        "message": (
            f"🌀 **Anomalous Breach Sealed!** Contained **{target_inc['entity_name']}** "
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
    if arch == "public_agency":
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

    cur_min = int(sess.get("current_minute", 480) or 480)
    cur_day = int(sess.get("current_day", 1) or 1)
    new_min = cur_min + 120
    new_day = cur_day
    while new_min >= 1440:
        new_min -= 1440
        new_day += 1

    db.update_session(
        session_id,
        current_location=dest_location,
        current_node_id=dest_node_id,
        nearby_enemies=[],
        current_minute=new_min,
        current_day=new_day,
    )
    if new_day > cur_day:
        try:
            process_anomalous_daily_rollover(session_id, new_day, party_uids=[user_id] if user_id else None)
        except Exception:
            pass

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
    if int(new_day) <= last_rollover and sess.get("daily_incursions"):
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

    # 5. Roll 2-3 Optional Daily Anomalous Incursions
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
      - private_agency_1 -> Private Agency #1 HQ -> Corporate Security Lobby & Entrance
      - private_agency_2 -> Private Agency #2 HQ -> Executive Security Lobby & Entrance
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

    if fac_clean == "private_agency_1":
        candidate_ids = ["sub_priv1_dispatch", "sub_priv1_entrance", "loc_private_hq_1"]
        h_val = int(session_id) if session_id else 1
        urban_core_zones = ["zone_city_center", "zone_downtown", "zone_uptown"]
        p1_z_id = urban_core_zones[h_val % 3]
        z_name = get_session_urban_zone_name(session_id, p1_z_id, "City Center", scen_key)
        p1_name = namegen.generate_private_agency_name(scen_key, hash_val=h_val, agency_index=1)
        fallback_loc = f"{z_name} ➔ {p1_name} Regional Tower HQ ➔ Executive Contract Board"
    elif fac_clean == "private_agency_2":
        candidate_ids = ["sub_priv2_dispatch", "sub_priv2_entrance", "loc_private_hq_2"]
        h_val = int(session_id) if session_id else 1
        urban_core_zones = ["zone_city_center", "zone_downtown", "zone_uptown"]
        p2_z_id = urban_core_zones[(h_val + 1) % 3]
        z_name = get_session_urban_zone_name(session_id, p2_z_id, "Downtown", scen_key)
        p1_name = namegen.generate_private_agency_name(scen_key, hash_val=h_val, agency_index=1)
        p2_name = namegen.generate_private_agency_name(scen_key, hash_val=h_val, agency_index=2)
        if p2_name == p1_name:
            p2_name = namegen.generate_private_agency_name(scen_key, hash_val=h_val + 99, agency_index=3)
        fallback_loc = f"{z_name} ➔ {p2_name} Operations Spire HQ ➔ Executive Contract Board"
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
    }


