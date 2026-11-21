from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import db


_JSON_TAG_TAIL_RE = re.compile(r"\s*\[(?:GEAR|ITEM|CONSUMABLE|SPELLBOOK|DIGITAL)_JSON:.*$", re.IGNORECASE)
_STAT_LEAK_RE = re.compile(
    r"\b(?:(?:HP|MP)\s*:?\s*\d+\s*/\s*\d+|\d+\s*/\s*\d+\s*(?:HP|MP)|DC\s*\d+|\+?\d+\s*(?:HP|MP|XP|ATK|DEF|EVA|CRIT))\b",
    re.IGNORECASE,
)

_PICKABLE_PROP_KEYWORDS = (
    "dropped",
    "floor",
    "ground",
    "table",
    "desk",
    "counter",
    "loose",
    "resting",
    "discarded",
    "left behind",
)


def _strip_item_tags(raw: str) -> str:
    return _JSON_TAG_TAIL_RE.sub("", str(raw or "")).strip()


def _is_anomalous_npc_record(raw_n: Optional[Dict[str, Any]]) -> bool:
    """Matches anomalous entity flags across top-level, basic_info, and role strings."""
    if not isinstance(raw_n, dict):
        return False
    bi = raw_n.get("basic_info")
    sources = (raw_n, bi) if isinstance(bi, dict) else (raw_n,)
    for src in sources:
        if src.get("is_anomalous_entity") or src.get("is_anomalous") or src.get("anomalous"):
            return True
        if str(src.get("npc_type") or "").strip().lower() == "anomaly":
            return True
        if str(src.get("social_role_type") or "").strip().lower() == "anomaly":
            return True
        if str(src.get("anomalous_npc_tag") or "").strip().lower() == "anomaly_entity":
            return True
        role_low = str(src.get("role") or "").strip().lower()
        if any(k in role_low for k in ("non-hostile entity", "non-hostile object", "non-hostile phenomenon")):
            return True
    return False


def get_per_tier(per_value: int) -> str:
    """Maps character Perception (PER) integer to a qualitative examine insight tier."""
    val = int(per_value or 0)
    if val <= 3:
        return "low"
    if val <= 6:
        return "medium"
    if val <= 9:
        return "high"
    return "keen"


def _enemy_condition_label(hp: int, max_hp: int) -> str:
    m_hp = max(1, int(max_hp or 1))
    ratio = float(max(0, int(hp or 0))) / float(m_hp)
    if ratio >= 0.85:
        return "Unscathed"
    if ratio >= 0.50:
        return "Bruised"
    if ratio >= 0.25:
        return "Wounded"
    return "Critical"


def _extract_outer_clothing_summary(
    actor_phys: Optional[Dict[str, Any]],
    fallback_badge: str = "",
    gender: str = "Female",
) -> str:
    """Builds a concise outer-garment summary, never exposing concealed undergarments."""
    clothing = actor_phys.get("clothing") if isinstance(actor_phys, dict) and isinstance(actor_phys.get("clothing"), dict) else {}
    worn_pieces: List[str] = []
    for slot_key in ("outerwear", "top", "bottom", "footwear"):
        layer = clothing.get(slot_key)
        if not isinstance(layer, dict):
            continue
        state = str(layer.get("state") or "worn").strip().lower()
        if state in ("none", "removed", "stripped", "off", "missing"):
            continue
        item_name = str(layer.get("item_name") or "").strip()
        if item_name and item_name.lower() not in ("worn", "default", "clothing"):
            worn_pieces.append(f"{item_name} ({state})" if state not in ("worn", "dressed", "intact") else item_name)
    if worn_pieces:
        return ", ".join(worn_pieces[:4])
    if fallback_badge:
        return str(fallback_badge)
    try:
        from mechanics.social.physical_state import compute_clothing_summary_badge
        if clothing:
            return compute_clothing_summary_badge(clothing, gender=gender)
    except Exception:
        pass
    return ""


def _resolve_privacy_level(
    session: Dict[str, Any],
    bystander_count: int,
    location_name: str,
) -> str:
    loc_low = str(location_name or "").lower()
    private_hints = ("bedroom", "dorm", "quarters", "bathroom", "locker", "apartment", "office", "cabin", "suite", "private")
    if bystander_count == 0 and any(h in loc_low for h in private_hints):
        return "private"
    if bystander_count == 0:
        return "secluded"
    if bystander_count <= 2:
        return "semi_private"
    return "public"


def _build_deterministic_fallback_prose(snapshot: Dict[str, Any]) -> str:
    env = snapshot.get("environment") or {}
    loc = str(env.get("location") or "the area").strip()
    sub = str(env.get("sub_location") or "").strip()
    phase = str(env.get("time_of_day") or "").strip().lower()
    place_str = f"{sub} in {loc}" if (sub and sub.lower() not in loc.lower()) else loc

    parts: List[str] = []
    if phase:
        parts.append(f"You take in the {phase} stillness of {place_str}.")
    else:
        parts.append(f"You carefully survey {place_str}.")

    npcs = snapshot.get("present_npcs") or []
    if npcs:
        npc_bits = []
        for n in npcs[:3]:
            nm = n.get("name", "someone")
            act = str(n.get("activity") or "").strip()
            npc_bits.append(f"{nm} ({act.lower()})" if act else nm)
        parts.append(f"Nearby: {', '.join(npc_bits)}.")
    else:
        parts.append("No one else appears to be in immediate view.")

    objs = [o.get("display_name") for o in (snapshot.get("objects") or []) if o.get("display_name")]
    if objs:
        parts.append(f"Within reach you spot {', '.join(objs[:3])}.")

    return " ".join(parts)


def build_examine_snapshot(
    session: Dict[str, Any],
    char: Dict[str, Any],
    *,
    user_settings: Optional[Dict[str, Any]] = None,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Builds a zero-turn, read-only structured Examine snapshot strictly from existing world state.
    Never fabricates random loot or leaks hidden epistemic/intimate secrets.
    """
    session = session if isinstance(session, dict) else {}
    char = char if isinstance(char, dict) else {}
    settings = user_settings if isinstance(user_settings, dict) else {}

    session_id = int(session.get("id") or 0)
    eff_uid = int(user_id or char.get("user_id") or 0)
    scen_key = str(session.get("scenario") or char.get("scenario") or "fantasy").strip()
    per_val = int(char.get("per_", 5) or 5)
    per_tier = get_per_tier(per_val)

    phys = session.get("physical_state")
    if not isinstance(phys, dict) and session_id:
        try:
            phys = db.get_session_physical_state(session_id) or {}
        except Exception:
            phys = {}
    if not isinstance(phys, dict):
        phys = {}

    raw_enemies = [
        e for e in (session.get("nearby_enemies") or session.get("monsters") or [])
        if isinstance(e, dict) and e.get("name") and int(e.get("hp", 1) or 0) > 0
    ]
    in_combat = bool(session.get("is_in_combat") or raw_enemies)

    ic_str = str(phys.get("intimate_contact") or "")
    is_intimate = False
    try:
        from mechanics.social.physical_state import is_erotic_intimate_contact
        is_intimate = bool(is_erotic_intimate_contact(ic_str) or "aftercare" in ic_str.lower())
    except Exception:
        is_intimate = False

    dialogue_partners_list: List[str] = []
    if isinstance(session.get("dialogue_partners"), list) and session["dialogue_partners"]:
        dialogue_partners_list = [str(x).strip() for x in session["dialogue_partners"] if str(x or "").strip()]
    elif session.get("dialogue_partner"):
        dialogue_partners_list = [str(session["dialogue_partner"]).strip()]
    dialogue_partner_lowers = {p.lower() for p in dialogue_partners_list}

    if in_combat:
        scene_mode = "combat"
    elif is_intimate:
        scene_mode = "intimate"
    elif dialogue_partner_lowers:
        scene_mode = "dialogue"
    else:
        scene_mode = "exploration"

    cur_day = int(session.get("current_day", 1) or 1)
    cur_min = int(session.get("current_minute", 480) or 480)
    try:
        from mechanics.system.time_engine import get_day_of_week, get_time_of_day_phase
        day_name = get_day_of_week(cur_day)
        time_phase, _, _ = get_time_of_day_phase(cur_min)
    except Exception:
        _days = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
        day_name = _days[max(0, cur_day - 1) % 7]
        time_phase = "Day"

    location = str(session.get("current_location") or "Unknown Location").strip()
    sub_location = str(session.get("focal_point") or session.get("sub_location") or "").strip()
    cur_node_id = str(session.get("current_node_id") or "").strip()

    exits: List[str] = []
    if session_id and cur_node_id:
        try:
            from mechanics.world.locations.pathfinding import get_adjacent_reachable_exits
            exits = get_adjacent_reachable_exits(session_id, cur_node_id, limit=6)
        except Exception:
            exits = []
    if not exits and isinstance(session.get("connected_locations"), list):
        exits = [str(x).strip() for x in session["connected_locations"][:6] if str(x or "").strip()]

    actors_phys = phys.get("actors") if isinstance(phys.get("actors"), dict) else {}
    party_companion_lowers = {
        str(p.get("name") if isinstance(p, dict) else p).strip().lower()
        for p in (session.get("party_npcs") or [])
        if p
    }

    contacts_by_low: Dict[str, Dict[str, Any]] = {}
    world_roster_by_low: Dict[str, Dict[str, Any]] = {}
    if session_id:
        try:
            for c_row in (db.get_contacts(session_id, int(char.get("id", 0) or 0)) or []):
                if isinstance(c_row, dict) and c_row.get("name"):
                    contacts_by_low[str(c_row["name"]).strip().lower()] = c_row
        except Exception:
            pass
        try:
            for wr_row in (db.get_world_roster(session_id, include_legacy_rosters=True) or []):
                if isinstance(wr_row, dict) and wr_row.get("name"):
                    world_roster_by_low[str(wr_row["name"]).strip().lower()] = wr_row
        except Exception:
            pass

    def _pick_demo(sources: Tuple[Dict[str, Any], ...], key: str) -> str:
        for src in sources:
            if not isinstance(src, dict):
                continue
            val = str(src.get(key) or "").strip()
            if val:
                return val
            bi = src.get("basic_info")
            if isinstance(bi, dict):
                bi_val = str(bi.get(key) or "").strip()
                if bi_val:
                    return bi_val
        return ""

    present_npcs: List[Dict[str, Any]] = []
    for raw_n in (session.get("current_npcs") or []):
        if isinstance(raw_n, dict):
            nm = str(raw_n.get("name") or "").strip()
            if not nm:
                continue
            nm_low = nm.lower()
            matched_actor: Optional[Dict[str, Any]] = None
            for ak, av in actors_phys.items():
                if str(ak).strip().lower() == nm_low and isinstance(av, dict):
                    matched_actor = av
                    break
            matched_contact = contacts_by_low.get(nm_low) or {}
            matched_wr = world_roster_by_low.get(nm_low) or {}
            is_anom = (
                _is_anomalous_npc_record(raw_n)
                or _is_anomalous_npc_record(matched_contact)
                or _is_anomalous_npc_record(matched_wr)
            )
            npc_gender = _pick_demo((raw_n, matched_contact, matched_wr), "gender")
            npc_race = _pick_demo((raw_n, matched_contact, matched_wr), "race")
            npc_age_group = _pick_demo((raw_n, matched_contact, matched_wr), "age_group")

            aff_score = int(
                raw_n.get("relationship_score")
                or raw_n.get("affinity")
                or matched_contact.get("relationship_score")
                or 0
            )
            track = str(raw_n.get("track") or matched_contact.get("track") or "platonic")
            rel_tier = "Stranger"
            try:
                from mechanics.social.relationships import get_relationship_tier
                tier_obj = get_relationship_tier(aff_score, track=track, scenario=scen_key)
                if isinstance(tier_obj, dict) and tier_obj.get("name"):
                    rel_tier = str(tier_obj["name"])
            except Exception:
                pass

            clothing_summary = _extract_outer_clothing_summary(
                matched_actor,
                fallback_badge=str(raw_n.get("clothing_status") or ""),
                gender=npc_gender or "Female",
            )
            activity = str(
                raw_n.get("current_action")
                or raw_n.get("activity")
                or raw_n.get("schedule_activity")
                or ""
            ).strip()
            posture = str((matched_actor or {}).get("posture") or "").strip()
            holding = str((matched_actor or {}).get("holding") or "").strip()
            if holding.lower() in ("none", "empty", "empty hands"):
                holding = ""

            subtle_tell = ""
            if per_tier in ("medium", "high", "keen"):
                tell_bits: List[str] = []
                mood_info = raw_n.get("dialogue_mood") if isinstance(raw_n.get("dialogue_mood"), dict) else {}
                if mood_info.get("mood_label"):
                    tell_bits.append(str(mood_info["mood_label"]))
                elif matched_actor and matched_actor.get("composure"):
                    comp = str(matched_actor["composure"]).strip()
                    if comp and comp.lower() != "composed":
                        tell_bits.append(comp.capitalize())
                if bool(raw_n.get("telltale_revealed")) and raw_n.get("visible_tell_text"):
                    tell_bits.append(str(raw_n["visible_tell_text"]).strip())
                subtle_tell = " • ".join(tell_bits)

            present_npcs.append(
                {
                    "name": nm,
                    "role": str(raw_n.get("role") or raw_n.get("occupation") or "").strip(),
                    "gender": npc_gender,
                    "race": npc_race,
                    "age_group": npc_age_group,
                    "activity": activity,
                    "clothing_summary": clothing_summary,
                    "posture": posture,
                    "holding": holding,
                    "relationship_tier": rel_tier,
                    "is_dialogue_partner": nm_low in dialogue_partner_lowers,
                    "is_party_companion": nm_low in party_companion_lowers or bool(raw_n.get("is_companion")),
                    "is_anomalous": is_anom,
                    "subtle_tell": subtle_tell,
                }
            )
        elif isinstance(raw_n, str) and raw_n.strip():
            nm = raw_n.strip()
            nm_low = nm.lower()
            matched_contact = contacts_by_low.get(nm_low) or {}
            matched_wr = world_roster_by_low.get(nm_low) or {}
            present_npcs.append(
                {
                    "name": nm,
                    "role": "",
                    "gender": _pick_demo((matched_contact, matched_wr), "gender"),
                    "race": _pick_demo((matched_contact, matched_wr), "race"),
                    "age_group": _pick_demo((matched_contact, matched_wr), "age_group"),
                    "activity": "",
                    "clothing_summary": "",
                    "posture": "",
                    "holding": "",
                    "relationship_tier": "Stranger",
                    "is_dialogue_partner": nm_low in dialogue_partner_lowers,
                    "is_party_companion": nm_low in party_companion_lowers,
                    "is_anomalous": _is_anomalous_npc_record(matched_contact) or _is_anomalous_npc_record(matched_wr),
                    "subtle_tell": "",
                }
            )

    objects: List[Dict[str, Any]] = []
    seen_obj_names: set[str] = set()
    for d_item in (phys.get("dropped_items") or []):
        raw_d = str(d_item or "").strip()
        clean_d = _strip_item_tags(raw_d)
        if not clean_d or clean_d.lower() in seen_obj_names:
            continue
        seen_obj_names.add(clean_d.lower())
        objects.append(
            {
                "raw_name": raw_d,
                "display_name": clean_d,
                "description": "Dropped on the floor",
                "pickupable": True,
                "kind": "dropped",
            }
        )

    props_map = phys.get("props") if isinstance(phys.get("props"), dict) else {}
    for pk, pv in props_map.items():
        clean_pk = _strip_item_tags(str(pk or "").strip())
        state_str = str(pv or "").strip()
        if not clean_pk or clean_pk.lower() in seen_obj_names:
            continue
        seen_obj_names.add(clean_pk.lower())
        is_pickable = any(kw in state_str.lower() for kw in _PICKABLE_PROP_KEYWORDS)
        objects.append(
            {
                "raw_name": str(pk),
                "display_name": clean_pk,
                "description": state_str or "Nearby in the scene",
                "pickupable": is_pickable,
                "kind": "prop",
            }
        )

    clues: List[Dict[str, Any]] = []
    if session_id:
        try:
            loc_low = location.lower()
            present_npc_lows = {n["name"].lower() for n in present_npcs}
            for c_row in (db.get_session_clues(session_id) or []):
                if not isinstance(c_row, dict) or c_row.get("is_consumed"):
                    continue
                src_loc = str(c_row.get("source_location") or "").strip().lower()
                lnk_npc = str(c_row.get("linked_npc") or "").strip().lower()
                is_ver = bool(c_row.get("is_verified"))
                loc_match = bool(src_loc and (src_loc in loc_low or loc_low in src_loc))
                npc_match = bool(lnk_npc and lnk_npc in present_npc_lows)
                if not (loc_match or npc_match):
                    continue
                if not is_ver and per_tier == "low" and not loc_match:
                    continue
                clues.append(
                    {
                        "id": c_row.get("id"),
                        "title": str(c_row.get("title") or "Lead").strip(),
                        "lead_text": str(c_row.get("lead_text") or "").strip(),
                        "category": str(c_row.get("category") or "physical").strip(),
                        "is_verified": is_ver,
                    }
                )
        except Exception:
            pass

    st_state = session.get("stealth_state") if isinstance(session.get("stealth_state"), dict) else {}
    try:
        from mechanics.stealth import project_stealth_state_for_user
        if eff_uid:
            st_state = project_stealth_state_for_user(session, eff_uid)
    except Exception:
        pass

    ep_summary: Dict[str, Any] = {}
    if session_id:
        try:
            ep_summary = db.build_player_fog_of_war_summary(session_id) or {}
        except Exception:
            ep_summary = {}

    bystander_count = sum(1 for n in present_npcs if not n.get("is_dialogue_partner") and not n.get("is_party_companion"))
    privacy_level = _resolve_privacy_level(session, bystander_count, location)

    stealth_and_epistemic = {
        "is_hidden": bool(st_state.get("is_hidden")),
        "alert_level": str(st_state.get("alert_level") or "unaware").lower(),
        "detection_meter": int(st_state.get("detection_meter") or 0),
        "bystander_count": bystander_count,
        "witness_count": len(ep_summary.get("known_witnesses") or []) + len(ep_summary.get("spotted_witnesses") or []),
        "privacy_level": privacy_level,
    }

    show_enemy_hp = int(settings.get("show_enemy_hp", 1) if settings.get("show_enemy_hp") is not None else 1) == 1
    show_enemy_intent = int(settings.get("show_enemy_intent", 1) if settings.get("show_enemy_intent") is not None else 1) == 1
    combat_intel: List[Dict[str, Any]] = []
    if scene_mode == "combat":
        for en in raw_enemies:
            e_hp = int(en.get("hp", 30) or 0)
            e_max = max(1, int(en.get("max_hp", 30) or 30))
            dossier_open = bool(en.get("dossier_revealed")) or per_tier in ("high", "keen")
            e_weak = [str(w) for w in (en.get("weaknesses") or []) if w] if dossier_open else []
            e_res = [str(r) for r in (en.get("resistances") or []) if r] if dossier_open else []
            e_imm = [str(im) for im in (en.get("immunities") or []) if im] if dossier_open else []
            e_intent = str(en.get("intent") or "").strip() if (show_enemy_intent and per_tier != "low") else ""

            combat_intel.append(
                {
                    "name": str(en.get("name") or "Enemy").strip(),
                    "condition_label": _enemy_condition_label(e_hp, e_max),
                    "hp": e_hp if show_enemy_hp else None,
                    "max_hp": e_max if show_enemy_hp else None,
                    "status_effects": [str(s) for s in (en.get("status_effects") or []) if s],
                    "intent": e_intent or None,
                    "weaknesses": e_weak,
                    "resistances": e_res,
                    "immunities": e_imm,
                }
            )

    snapshot: Dict[str, Any] = {
        "session_id": session_id,
        "scene_mode": scene_mode,
        "per_tier": per_tier,
        "show_enemy_hp": show_enemy_hp,
        "environment": {
            "location": location,
            "sub_location": sub_location,
            "day_name": day_name,
            "current_day": cur_day,
            "current_minute": cur_min,
            "time_of_day": time_phase,
            "privacy_level": privacy_level,
            "exits": exits,
        },
        "present_npcs": present_npcs,
        "objects": objects,
        "clues": clues,
        "stealth_and_epistemic": stealth_and_epistemic,
        "combat_intel": combat_intel,
    }
    snapshot["fallback_prose"] = _build_deterministic_fallback_prose(snapshot)
    return snapshot


def scrub_examine_prose(raw_text: str) -> str:
    """Strips reasoning blocks, JSON envelopes, and raw stat/DC integers from Examine prose."""
    txt = str(raw_text or "").strip()
    if not txt:
        return ""
    txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.DOTALL | re.IGNORECASE).strip()
    txt = re.sub(r"^```[a-zA-Z0-9_-]*\s*|\s*```$", "", txt).strip()
    txt = re.sub(r"\[(?:ITEM|GEAR|CONSUMABLE|SPELLBOOK|DIGITAL)_JSON:[^\]]*\]", "", txt, flags=re.IGNORECASE)
    txt = _STAT_LEAK_RE.sub("", txt)
    try:
        from game_engine.keywords import sanitize_comparative_cliches
        txt = sanitize_comparative_cliches(txt)
    except Exception:
        pass
    return re.sub(r"\s{2,}", " ", txt).strip()
