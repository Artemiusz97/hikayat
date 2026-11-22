from __future__ import annotations
"""
Deterministic Dynamic NPC Wardrobe State Machine & Hybrid Change-Point Latching.

Governs off-screen preset resolution, On-Screen Freeze, Change-Point transitions,
Wednesday Sport Day, sub-location bathing/swim/athletic/secret-HQ kits, SFW/NSFW
visitor sleepwear modesty, soiled cleanup, romantic date prep, and non-armored
player cosmetic sync.
"""

from typing import Any, Dict, Iterable, Mapping

from mechanics.world.world_schedule import is_weekend

from .catalog import build_npc_wardrobe_presets
from .constants import (
    AFTER_SCHOOL_UNIFORM_END_MIN,
    KIT_BATH,
    KIT_DOJO,
    KIT_SECRET_FACTION,
    KIT_SPORT,
    KIT_SWIM,
    KIT_TACTICAL,
    OVERLAY_APRON,
    OVERLAY_LAB_COAT,
    OVERLAY_MODESTY_ROBE,
    PRESET_CASUAL,
    PRESET_DUTY,
    PRESET_SLEEPWEAR,
    RENDEZVOUS_PREP_BUFFER_MIN,
    SCHOOL_ARRIVAL_MIN,
    TIME_SKIP_FREEZE_BREAK_MIN,
    is_bathing_sublocation,
    is_breach_or_tactical_zone,
    is_change_point_location,
    is_private_bedroom_sublocation,
    is_recreational_water_sublocation,
    is_school_campus_location,
    is_school_context_scenario,
    is_secret_faction_venue,
    is_sleep_venue,
    is_sleepwear_window,
    is_wednesday_sport_window,
    resolve_athletic_kit_for_venue,
    safe_json_dict,
)

_ATHLETIC_CLUB_TOKENS = (
    "track",
    "swim",
    "kendo",
    "martial",
    "dojo",
    "basketball",
    "volleyball",
    "soccer",
    "football",
    "tennis",
    "badminton",
    "archery",
    "athletic",
    "sport",
    "pe teacher",
    "coach",
    "gym",
)

_COMBAT_RESPONDER_ROLE_TOKENS = (
    "agent",
    "operative",
    "officer",
    "police",
    "guard",
    "knight",
    "paladin",
    "soldier",
    "enforcer",
    "exorcist",
    "witch-hunter",
    "inquisitor",
    "marine",
    "vanguard",
    "mercenary",
    "ranger",
)

_SHOP_APRON_ROLE_TOKENS = (
    "barista",
    "baker",
    "chef",
    "cook",
    "shopkeeper",
    "merchant",
    "waiter",
    "waitress",
    "clerk",
    "florist",
    "cafe",
    "tavern",
    "innkeeper",
)

_LAB_COAT_ROLE_TOKENS = (
    "scientist",
    "researcher",
    "doctor",
    "nurse",
    "chemist",
    "biologist",
    "infirmary",
    "medic",
    "engineer",
)

_REAL_ARMOR_KEYWORDS = (
    "plate armor",
    "full plate",
    "half plate",
    "chainmail",
    "chain mail",
    "scale mail",
    "kevlar",
    "ballistic vest",
    "tactical vest",
    "tactical armor",
    "riot armor",
    "power armor",
    "exosuit",
    "cuirass",
    "breastplate",
    "brigandine",
    "leather armor",
    "studded leather",
    "knight armor",
    "combat armor",
)


def is_nsfw_context(session: Mapping[str, Any] | None = None, scen_key: str = "") -> bool:
    """Returns True when NSFW scenario/session gates allow unrobed bedroom/visitor checks."""
    if isinstance(session, Mapping) and bool(session.get("nsfw_enabled")):
        return True
    key = str(scen_key or (session or {}).get("scenario_key") or "").strip()
    if key:
        try:
            import scenario_data
            if scenario_data.is_nsfw_scenario(key):
                return True
        except Exception:
            pass
    low = key.lower()
    return any(tok in low for tok in ("nsfw", "erotica", "velvet", "adult", "harem"))


def _seed_percent(seed_text: str) -> int:
    import hashlib
    digest = hashlib.md5(seed_text.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def _is_household_or_partner(
    meta: Mapping[str, Any],
    npc: Mapping[str, Any],
    viewer_relationship: Mapping[str, Any] | None = None,
) -> tuple[bool, bool]:
    rel = viewer_relationship if isinstance(viewer_relationship, Mapping) else {}
    basic = safe_json_dict(npc.get("basic_info") or npc.get("basic_info_json"))
    rel_track = str(rel.get("track") or npc.get("relationship_track") or "").strip().lower()
    rel_type = str(rel.get("relationship_type") or npc.get("relationship_type") or "").strip().lower()
    kinship = str(rel.get("kinship") or basic.get("kinship") or npc.get("household_role") or "").strip().lower()
    aff = 0
    try:
        aff = int(rel.get("affinity") if rel.get("affinity") is not None else (npc.get("affinity") or 0))
    except Exception:
        aff = 0

    is_family = bool(
        rel.get("is_household_member")
        or npc.get("is_household_member")
        or rel_track == "family"
        or "family" in rel_type
        or any(k in kinship for k in ("sister", "brother", "mother", "father", "mom", "dad", "cousin", "aunt", "uncle", "parent", "sibling", "spouse", "wife", "husband", "roommate", "household"))
    )
    is_partner = bool(rel_track == "romantic" or "partner" in rel_type or "lover" in rel_type or aff >= 100)
    return is_family, is_partner


def _is_player_safe_res_for_context(session: Mapping[str, Any] | None, location_str: str, node_id: str) -> bool:
    sess_safe = bool((session or {}).get("is_player_safe_res"))
    if sess_safe:
        return True
    probe = f"{node_id or ''} {location_str or ''}".lower()
    return any(tok in probe for tok in ("loc_player_house", "sub_player_", "player's house", "player's apartment", "player safe house"))


def resolve_viewer_sleepwear_modesty(
    clothing: Mapping[str, Any],
    meta: Mapping[str, Any],
    *,
    scen_key: str = "",
    session: Mapping[str, Any] | None = None,
    npc: Mapping[str, Any] | None = None,
    location_str: str = "",
    node_id: str = "",
    is_colocated_with_player: bool = False,
    viewer_relationship: Mapping[str, Any] | None = None,
    session_id: int = 0,
    current_day: int = 1,
    robe_text: str = "",
) -> tuple[dict[str, Any], bool]:
    """
    Enforces Spec #5 SFW/NSFW Sleepwear Visitor Modesty.
    Returns (adjusted_clothing, robe_applied_bool).
    """
    out = dict(clothing or {})
    if is_private_bedroom_sublocation(location_str, node_id):
        return out, False

    is_family, is_partner = _is_household_or_partner(meta, npc or {}, viewer_relationship)
    if is_family or is_partner or bool(meta.get("is_bold_or_shameless")):
        return out, False

    robe = str(robe_text or "").strip()
    if not robe:
        robe = "Flannel bathrobe over sleepwear" if meta.get("is_male") else "Soft knit cardigan over sleepwear"

    if is_nsfw_context(session, scen_key):
        if bool(meta.get("is_prude")):
            out["outerwear"] = robe
            return out, True
        seed_val = _seed_percent(f"{session_id}:{meta.get('name', 'NPC')}:nsfw_sleepwear:{current_day}")
        if seed_val < 75:
            return out, False
        out["outerwear"] = robe
        return out, True

    # SFW default: low-affinity non-family visitors outside bedrooms see a modesty robe
    if is_colocated_with_player or viewer_relationship is not None:
        out["outerwear"] = robe
        return out, True
    out["outerwear"] = robe
    return out, True


def _is_athlete_or_sport_club(meta: Mapping[str, Any]) -> bool:
    probe = f"{meta.get('club', '')} {meta.get('role', '')} {meta.get('clique', '')}".lower()
    return any(tok in probe for tok in _ATHLETIC_CLUB_TOKENS)


def _matches_npc_name_or_id(item: Mapping[str, Any], npc_name: str, npc_id: Any) -> bool:
    item_cid = item.get("contact_id")
    if npc_id is not None and item_cid is not None:
        try:
            if int(item_cid) == int(npc_id):
                return True
        except Exception:
            pass
    item_name = str(item.get("contact_name") or item.get("npc_name") or item.get("partner_name") or "").strip().lower()
    return bool(npc_name and item_name and item_name == npc_name.strip().lower())


def _has_active_romantic_rendezvous_prep(
    npc: Mapping[str, Any],
    session: Mapping[str, Any] | None,
    current_day: int,
    current_minute: int,
) -> tuple[bool, dict[str, Any] | None]:
    """True when NPC has a scheduled romantic rendezvous with >= 30m prep buffer."""
    npc_name = str(npc.get("name") or "").strip()
    npc_id = npc.get("id") or npc.get("contact_id")
    candidates: list[Mapping[str, Any]] = []
    if isinstance(npc.get("active_rendezvous"), Mapping):
        candidates.append(npc["active_rendezvous"])
    if isinstance(session, Mapping):
        raw_list = session.get("_active_commitments") or session.get("commitments") or []
        if isinstance(raw_list, list):
            for c in raw_list:
                if isinstance(c, Mapping):
                    candidates.append(c)

    safe_day = max(1, int(current_day or 1))
    safe_min = int(current_minute if current_minute is not None else 480) % 1440

    for c in candidates:
        ctype = str(c.get("commitment_type") or c.get("type") or "").strip().lower()
        status = str(c.get("status") or "pending").strip().lower()
        if ctype not in ("rendezvous", "date", "romantic_date"):
            continue
        if status not in ("pending", "accepted", "active"):
            continue
        if c not in (npc.get("active_rendezvous"),) and not _matches_npc_name_or_id(c, npc_name, npc_id):
            continue

        lead_min = c.get("prep_buffer_minutes")
        if lead_min is None and c.get("booked_day") is not None and c.get("booked_minute") is not None:
            try:
                t_day = int(c.get("target_day") or c.get("scheduled_day") or safe_day)
                t_min = int(c.get("target_minute") or c.get("scheduled_minute") or safe_min)
                b_day = int(c.get("booked_day"))
                b_min = int(c.get("booked_minute"))
                lead_min = (t_day - b_day) * 1440 + (t_min - b_min)
            except Exception:
                lead_min = None

        if lead_min is not None:
            try:
                if int(lead_min) < RENDEZVOUS_PREP_BUFFER_MIN:
                    continue
            except Exception:
                pass

        t_day = int(c.get("target_day") or c.get("scheduled_day") or safe_day)
        t_min = c.get("target_minute") if c.get("target_minute") is not None else c.get("scheduled_minute")
        if t_min is None:
            if t_day == safe_day:
                return True, dict(c)
            continue

        diff = (t_day - safe_day) * 1440 + (int(t_min) - safe_min)
        if -120 <= diff <= RENDEZVOUS_PREP_BUFFER_MIN * 2:
            return True, dict(c)

    return False, None


def _compute_target_preset_and_kit(
    npc: Mapping[str, Any],
    meta: Mapping[str, Any],
    *,
    session: Mapping[str, Any] | None = None,
    scen_key: str = "fantasy",
    location_str: str = "",
    node_id: str = "",
    current_day: int = 1,
    current_minute: int = 480,
    active_incursion: Any = None,
    is_combat_breach_responder: bool = False,
) -> tuple[str, str, str]:
    """
    Determines off-screen target (base_preset, activity_kit, overlay_key).
    Returns e.g. ('duty', 'activity:sport', '') or ('sleepwear', '', '').
    """
    if meta.get("is_myobu_fox"):
        return "natural", "", ""

    basic = safe_json_dict(npc.get("basic_info") or npc.get("basic_info_json"))
    safe_day = max(1, int(current_day or 1))
    safe_min = int(current_minute if current_minute is not None else 480) % 1440
    weekday_idx = (safe_day - 1) % 7

    shift_profile = str(
        npc.get("shift_profile")
        or basic.get("shift_profile")
        or ("student" if meta.get("is_student") else "day")
    ).strip().lower()
    is_nocturnal = bool(npc.get("nocturnal") or basic.get("nocturnal"))
    closes_at_22 = bool(npc.get("closes_at_22") or basic.get("closes_at_22"))
    closes_at_20 = bool(npc.get("closes_at_20") or basic.get("closes_at_20"))
    rest_days = npc.get("rest_days") or basic.get("rest_days") or []
    part_time_days = npc.get("part_time_days") or basic.get("part_time_days") or []
    home_node_id = str(
        npc.get("home_node_id")
        or npc.get("household_home_node_id")
        or basic.get("home_node_id")
        or ""
    ).strip()
    workplace_node_id = str(npc.get("workplace_node_id") or basic.get("workplace_node_id") or "").strip()
    workplace_name = str(npc.get("workplace_name") or basic.get("workplace_name") or "").strip().lower()
    is_player_safe_res = _is_player_safe_res_for_context(session, location_str, node_id)

    on_rest_day = False
    if isinstance(rest_days, list) and rest_days:
        on_rest_day = weekday_idx in rest_days or safe_day in rest_days
    elif shift_profile in ("day", "student"):
        on_rest_day = is_weekend(safe_day)

    loc_low = str(location_str or "").lower()
    nid_low = str(node_id or "").lower()
    at_workplace = bool(
        (workplace_node_id and nid_low and (nid_low == workplace_node_id.lower() or workplace_node_id.lower() in nid_low))
        or (workplace_name and workplace_name in loc_low)
    )

    role_low = str(meta.get("role") or "").lower()
    desc_low = str(meta.get("desc") or "").lower()
    fac_low = str(meta.get("faction_id") or "").lower()

    # 1. Sub-location bathing / swim kits (Spec #10)
    if is_bathing_sublocation(location_str, node_id):
        base = PRESET_CASUAL if on_rest_day or safe_min >= AFTER_SCHOOL_UNIFORM_END_MIN else PRESET_DUTY
        return base, KIT_BATH, ""

    if is_recreational_water_sublocation(location_str, node_id):
        return PRESET_CASUAL, KIT_SWIM, ""

    # 2. Double-Life Secret Faction Sanctum (Spec #9)
    if is_secret_faction_venue(location_str, node_id):
        if meta.get("is_double_life") or "cult" in fac_low or "syndicate" in fac_low or "velvet" in str(meta.get("club") or "").lower():
            return PRESET_DUTY, KIT_SECRET_FACTION, ""

    # 3. Breach / Tactical Emergency Responder (Spec #6)
    is_responder_role = bool(
        meta.get("is_special_agent")
        or meta.get("is_double_life")
        or any(tok in role_low or tok in desc_low for tok in _COMBAT_RESPONDER_ROLE_TOKENS)
    )
    if is_combat_breach_responder or (is_breach_or_tactical_zone(location_str, node_id, active_incursion) and is_responder_role):
        return PRESET_DUTY, KIT_TACTICAL, ""

    # 4. Circadian Sleepwear Window strictly inside a Sleep Venue (Spec #5)
    at_sleep_venue = is_sleep_venue(
        location_str,
        node_id,
        npc_home_node_id=home_node_id,
        is_player_safe_res=is_player_safe_res,
    )
    if at_sleep_venue and is_sleepwear_window(
        safe_day,
        safe_min,
        shift_profile=shift_profile,
        on_rest_day=on_rest_day,
        is_nocturnal=is_nocturnal,
        closes_at_22=closes_at_22,
        closes_at_20=closes_at_20,
    ):
        return PRESET_SLEEPWEAR, "", ""

    # 5. Athletic Practice Venues & Wednesday Sport Day (Spec #4)
    ath_kit = resolve_athletic_kit_for_venue(location_str, node_id)
    is_pe_or_coach = any(tok in role_low for tok in ("pe ", "physical education", "coach", "gym teacher"))
    if ath_kit and (meta.get("is_student") or _is_athlete_or_sport_club(meta) or is_pe_or_coach) and not at_sleep_venue:
        return PRESET_DUTY, ath_kit, ""

    if is_wednesday_sport_window(safe_day, safe_min, scen_key) and (meta.get("is_student") or is_pe_or_coach):
        if is_school_campus_location(location_str, node_id) or safe_min < 900:
            return PRESET_DUTY, KIT_SPORT, ""

    # 6. Scheduled Romantic Rendezvous Date Prep (Spec #13) & Pending Outfit Requests
    on_date_prep, _ = _has_active_romantic_rendezvous_prep(npc, session, safe_day, safe_min)
    pending_req = basic.get("pending_outfit_request") if isinstance(basic.get("pending_outfit_request"), Mapping) else {}
    pending_status = str(pending_req.get("status") or "").strip().lower()
    pending_preset = str(pending_req.get("requested_preset") or "").strip().lower()

    if on_date_prep:
        if pending_status in ("deferred_to_venue_or_date", "complied_immediate") and pending_preset == PRESET_SLEEPWEAR and at_sleep_venue:
            return PRESET_SLEEPWEAR, "", ""
        if pending_status in ("deferred_to_venue_or_date", "complied_immediate") and pending_preset == PRESET_DUTY:
            return PRESET_DUTY, "", ""
        return PRESET_CASUAL, "", ""

    if pending_status in ("deferred_to_venue_or_date", "complied_immediate"):
        if pending_preset == PRESET_SLEEPWEAR and at_sleep_venue:
            return PRESET_SLEEPWEAR, "", ""
        if pending_preset == KIT_SWIM and is_recreational_water_sublocation(location_str, node_id):
            return PRESET_CASUAL, KIT_SWIM, ""
        if pending_preset == PRESET_CASUAL and (at_sleep_venue or not is_school_campus_location(location_str, node_id) or safe_min >= AFTER_SCHOOL_UNIFORM_END_MIN or on_rest_day):
            return PRESET_CASUAL, "", ""
        if pending_preset == PRESET_DUTY and (at_sleep_venue or at_workplace or is_school_campus_location(location_str, node_id) or on_rest_day or safe_min >= AFTER_SCHOOL_UNIFORM_END_MIN):
            return PRESET_DUTY, "", ""

    # 7. Student Campus vs Off-Campus Rules (Spec #3 & #9)
    if meta.get("is_student") or shift_profile == "student":
        if basic.get("part_time_shift") or npc.get("part_time_shift"):
            from mechanics.social.town_roster import is_student_on_part_time_shift, remap_town_node_for_scenario
            pt_sid = int((session.get("id") if isinstance(session, Mapping) else 0) or npc.get("session_id") or basic.get("session_id") or 0)
            pt_spec = is_student_on_part_time_shift(npc, safe_day, safe_min, session_id=pt_sid)
            if pt_spec and pt_spec.get("venue_node_id"):
                pt_nid = remap_town_node_for_scenario(str(pt_spec["venue_node_id"]), scen_key).lower()
                if (pt_nid and pt_nid == nid_low) or at_workplace:
                    return PRESET_CASUAL, "", OVERLAY_APRON
        if on_rest_day or is_weekend(safe_day):
            return PRESET_CASUAL, "", ""
        if safe_min < SCHOOL_ARRIVAL_MIN or safe_min >= AFTER_SCHOOL_UNIFORM_END_MIN:
            return PRESET_CASUAL, "", ""
        if 900 <= safe_min < AFTER_SCHOOL_UNIFORM_END_MIN:
            # 15:00 - 17:29: Uniform strictly if on campus; off-campus shops -> casual + apron; town -> casual
            if at_workplace and not is_school_campus_location(location_str, node_id):
                return PRESET_CASUAL, "", OVERLAY_APRON
            if is_school_campus_location(location_str, node_id):
                return PRESET_DUTY, "", ""
            return PRESET_CASUAL, "", ""
        # 07:00 - 14:59 weekday
        return PRESET_DUTY, "", ""

    # 8. Adult Shift Profiles (Spec #3 & #5)
    if shift_profile == "pedestrian":
        return PRESET_CASUAL, "", ""

    work_overlay = ""
    if any(tok in role_low for tok in _SHOP_APRON_ROLE_TOKENS):
        work_overlay = OVERLAY_APRON
    elif any(tok in role_low for tok in _LAB_COAT_ROLE_TOKENS):
        work_overlay = OVERLAY_LAB_COAT

    if shift_profile == "street_vendor":
        if is_nocturnal:
            is_working = safe_min >= 1140 or safe_min < 180
            if is_working and not on_rest_day:
                return PRESET_DUTY, "", ""
            return PRESET_CASUAL, "", ""
        is_working = 480 <= safe_min < 1200
        if (is_working and not on_rest_day) or at_workplace:
            return PRESET_DUTY, "", OVERLAY_APRON
        return PRESET_CASUAL, "", ""

    if shift_profile == "night":
        is_working = safe_min >= 1200 or safe_min < 300
        if is_working and not on_rest_day:
            return PRESET_DUTY, "", (work_overlay if at_workplace else "")
        return PRESET_CASUAL, "", ""

    if shift_profile == "evening":
        eve_end = 1200 if closes_at_20 else (1320 if closes_at_22 else 1380)
        is_working = 840 <= safe_min < eve_end
        if (is_working and not on_rest_day) or at_workplace:
            return PRESET_DUTY, "", (work_overlay if at_workplace else "")
        return PRESET_CASUAL, "", ""

    if shift_profile == "rotating":
        is_working = (420 <= safe_min < 660) or (960 <= safe_min < 1200)
        if (is_working and not on_rest_day) or at_workplace:
            return PRESET_DUTY, "", (work_overlay if at_workplace else "")
        return PRESET_CASUAL, "", ""

    # Default 'day' / 'roaming_merchant'
    if on_rest_day and not at_workplace:
        return PRESET_CASUAL, "", ""

    in_day_hours = 480 <= safe_min < AFTER_SCHOOL_UNIFORM_END_MIN
    if at_sleep_venue and not at_workplace:
        if safe_min < 480 or safe_min >= AFTER_SCHOOL_UNIFORM_END_MIN:
            return PRESET_CASUAL, "", ""
    if in_day_hours or at_workplace:
        return PRESET_DUTY, "", (work_overlay if at_workplace else "")
    return PRESET_CASUAL, "", ""


_GENERIC_REQUEST_PHRASES = {
    "casual",
    "sleepwear",
    "pajama",
    "pajamas",
    "pyjama",
    "pyjamas",
    "uniform",
    "duty",
    "suit",
    "work outfit",
    "swimsuit",
    "swimwear",
    "bikini",
    "lingerie",
    "no bra",
    "bra-less",
    "braless",
    "commando",
    "none",
}


def _apply_pending_outfit_request_if_applicable(
    clothing: dict[str, Any],
    base_preset: str,
    activity_kit: str,
    npc: Mapping[str, Any],
    *,
    location_str: str = "",
    node_id: str = "",
) -> tuple[dict[str, Any], str]:
    """Applies accepted pending_outfit_request if venue/preset matches; returns (clothing, flag_suffix)."""
    basic = safe_json_dict(npc.get("basic_info") or npc.get("basic_info_json"))
    req = basic.get("pending_outfit_request")
    if not isinstance(req, Mapping):
        return clothing, ""
    status = str(req.get("status") or "").strip().lower()
    if status not in ("deferred_to_venue_or_date", "complied_immediate", "complied_violation"):
        return clothing, ""

    req_preset = str(req.get("requested_preset") or "").strip().lower()
    req_phrase = str(req.get("requested_item_phrase") or "").strip()
    is_violation = status == "complied_violation" or bool(req.get("is_violation"))
    out = dict(clothing)

    if req_preset == "bra_less":
        out["under_top"] = "None (Bra-less)"
        if is_violation:
            out["top"] = f"{out.get('top', 'Top')} [provocative] [dress_code_violation]"
        return out, "bra_less"
    if req_preset == "commando":
        out["under_bottom"] = "None (Commando)"
        if is_violation:
            out["bottom"] = f"{out.get('bottom', 'Bottom')} [provocative] [dress_code_violation]"
        return out, "commando"
    if req_preset == "lingerie":
        clean_l = req_phrase if req_phrase.lower() not in _GENERIC_REQUEST_PHRASES else "lacy lingerie set"
        if "none (n/a)" not in str(out.get("under_top", "")).lower():
            out["under_top"] = f"Worn ({clean_l})"
        out["under_bottom"] = f"Worn ({clean_l})"
        if is_violation:
            out["top"] = f"{out.get('top', 'Top')} [provocative] [dress_code_violation]"
        return out, "lingerie"
    if req_preset == "accessory" and req_phrase:
        top_cur = str(out.get("top") or "").strip()
        if req_phrase.lower() not in top_cur.lower():
            out["top"] = f"{top_cur} (wearing {req_phrase})"
        return out, "accessory"
    if (
        req_preset == base_preset
        or req_preset == activity_kit
        or is_violation
        or (req_preset == "casual" and base_preset == PRESET_CASUAL)
    ):
        top_cur = str(out.get("top") or "").strip()
        if req_phrase and req_phrase.lower() not in _GENERIC_REQUEST_PHRASES and req_phrase.lower() not in top_cur.lower():
            out["top"] = req_phrase if len(req_phrase) > 10 else f"{req_phrase} ({top_cur})"
        if is_violation:
            out["top"] = f"{out['top']} [provocative] [dress_code_violation]"
        return out, req_preset or "custom"
    return out, ""


def resolve_actor_wardrobe_state(
    npc: Mapping[str, Any],
    *,
    session: Mapping[str, Any] | None = None,
    scen_key: str = "",
    location_str: str = "",
    node_id: str = "",
    current_day: int | None = None,
    current_minute: int | None = None,
    is_colocated_with_player: bool = False,
    viewer_relationship: Mapping[str, Any] | None = None,
    is_combat_breach_responder: bool = False,
    active_incursion: Any = None,
) -> dict[str, Any]:
    """
    Computes the complete resolved 6-slot wardrobe state for an NPC at the given
    time, location, and viewer relationship. Zero LLM calls.
    """
    sess = session if isinstance(session, Mapping) else {}
    resolved_scen = str(scen_key or sess.get("scenario_key") or npc.get("scenario_key") or "fantasy").strip()
    sess_id = int(sess.get("id") or sess.get("session_id") or npc.get("session_id") or 0)
    day_val = int(current_day if current_day is not None else (sess.get("current_day") or 1))
    min_val = int(current_minute if current_minute is not None else (sess.get("current_minute") if sess.get("current_minute") is not None else 480))
    loc_val = str(location_str or sess.get("current_location") or "")
    nid_val = str(node_id or sess.get("current_node_id") or "")

    bundle = build_npc_wardrobe_presets(npc, scen_key=resolved_scen, session_id=sess_id)
    meta = bundle["meta"]
    presets = bundle["presets"]
    kits = bundle["activity_kits"]
    overlays = bundle["overlays"]

    base_preset, active_kit, overlay_key = _compute_target_preset_and_kit(
        npc,
        meta,
        session=sess,
        scen_key=resolved_scen,
        location_str=loc_val,
        node_id=nid_val,
        current_day=day_val,
        current_minute=min_val,
        active_incursion=active_incursion if active_incursion is not None else sess.get("active_incursion"),
        is_combat_breach_responder=is_combat_breach_responder,
    )

    if base_preset == "natural":
        empty_slots = dict(presets[PRESET_DUTY])
        return {
            "active_outfit_preset": "natural",
            "base_preset": "natural",
            "activity_kit": "",
            "overlay": "",
            "clothing": dict(empty_slots),
            "canonical_outfit": dict(empty_slots),
            "wardrobe_meta": {
                "base_preset": "natural",
                "activity_kit": "",
                "overlay": "",
                "preset_catalog_version": 1,
            },
            "presets": presets,
            "activity_kits": kits,
            "overlays": overlays,
            "meta": meta,
        }

    if active_kit and active_kit in kits:
        clothing = dict(kits[active_kit])
        effective_preset = active_kit
    else:
        clothing = dict(presets.get(base_preset, presets[PRESET_DUTY]))
        effective_preset = base_preset

    applied_overlay = ""
    if overlay_key and overlay_key in overlays:
        cur_out = str(clothing.get("outerwear") or "none").strip()
        if cur_out.lower() in ("none", ""):
            clothing["outerwear"] = overlays[overlay_key]
        else:
            clothing["outerwear"] = f"{overlays[overlay_key]} over {cur_out}"
        applied_overlay = overlay_key

    if base_preset == PRESET_SLEEPWEAR and not active_kit:
        clothing, robe_applied = resolve_viewer_sleepwear_modesty(
            clothing,
            meta,
            scen_key=resolved_scen,
            session=sess,
            npc=npc,
            location_str=loc_val,
            node_id=nid_val,
            is_colocated_with_player=is_colocated_with_player,
            viewer_relationship=viewer_relationship,
            session_id=sess_id,
            current_day=day_val,
            robe_text=overlays.get(OVERLAY_MODESTY_ROBE, ""),
        )
        if robe_applied:
            applied_overlay = OVERLAY_MODESTY_ROBE

    clothing, req_tag = _apply_pending_outfit_request_if_applicable(
        clothing,
        base_preset,
        active_kit,
        npc,
        location_str=loc_val,
        node_id=nid_val,
    )
    _raw_bi = safe_json_dict(npc.get("basic_info") or npc.get("basic_info_json"))
    _raw_pend = _raw_bi.get("pending_outfit_request")
    _pend_st = str(_raw_pend.get("status") or "").strip().lower() if isinstance(_raw_pend, Mapping) else ""

    return {
        "active_outfit_preset": effective_preset,
        "base_preset": base_preset,
        "activity_kit": active_kit,
        "overlay": applied_overlay,
        "request_tag": req_tag,
        "clothing": dict(clothing),
        "canonical_outfit": dict(clothing),
        "wardrobe_meta": {
            "base_preset": base_preset,
            "activity_kit": active_kit,
            "overlay": applied_overlay,
            "preset_catalog_version": 1,
            "fulfilled_pending_request": bool(req_tag and _pend_st == "deferred_to_venue_or_date"),
        },
        "presets": presets,
        "activity_kits": kits,
        "overlays": overlays,
        "meta": meta,
    }


def _clothing_is_disheveled(clothing: Any) -> bool:
    if not isinstance(clothing, Mapping):
        return False
    probe = " ".join(str(v) for v in clothing.values()).lower()
    return any(tok in probe for tok in ("disheveled", "pulled_aside", "torn", "soaked", "stained"))


def _clean_disheveled_slots(fresh_slots: Mapping[str, Any]) -> dict[str, Any]:
    return dict(fresh_slots)


def _is_gear_change_point(
    location_str: str = "",
    node_id: str = "",
    *,
    npc_home_node_id: str = "",
    is_player_safe_res: bool = False,
) -> bool:
    """True at tactical armories, outfitters, homes, inns, and camps where party companions gear up."""
    if is_sleep_venue(location_str, node_id, npc_home_node_id=npc_home_node_id, is_player_safe_res=is_player_safe_res):
        return True
    probe = f"{node_id or ''} {location_str or ''}".lower()
    return any(
        tok in probe
        for tok in (
            "loc_hq_tactical_armory",
            "loc_hq_field_outfitter",
            "armory",
            "outfitter",
            "barracks",
            "camp",
            "campsite",
            "guild hall",
        )
    )


def evaluate_turn_wardrobe_transitions(
    current_state: dict[str, Any],
    *,
    session: Mapping[str, Any] | None = None,
    party: list[dict[str, Any]] | None = None,
    npcs_by_name: Mapping[str, Mapping[str, Any]] | None = None,
    old_loc: str = "",
    new_loc: str = "",
    old_node_id: str = "",
    new_node_id: str = "",
    old_day: int = 1,
    old_min: int = 480,
    new_day: int = 1,
    new_min: int = 480,
    skip_minutes: int = 0,
    sleep_mode: str = "",
    retained_names: Iterable[str] | None = None,
    active_incursion: Any = None,
    location_changed: bool | None = None,
    relationships_by_name: Mapping[str, Mapping[str, Any]] | None = None,
    newly_soiled_actors: Iterable[str] | None = None,
) -> dict[str, Any]:
    """
    Runs the Hybrid Change-Point Latching + On-Screen Freeze transition step across
    all actors present in `current_state["actors"]`.
    """
    if not isinstance(current_state, dict):
        return current_state
    actors = current_state.get("actors")
    if not isinstance(actors, dict) or not actors:
        return current_state

    sess = session if isinstance(session, Mapping) else {}
    scen_key = str(sess.get("scenario_key") or sess.get("scenario") or "fantasy").strip()
    loc_changed = (
        bool(location_changed)
        if location_changed is not None
        else (bool(new_loc and old_loc and new_loc != old_loc) or bool(new_node_id and old_node_id and new_node_id != old_node_id))
    )
    delta_min = max(0, (int(new_day) - int(old_day)) * 1440 + (int(new_min) - int(old_min)))
    effective_skip = max(int(skip_minutes or 0), delta_min if delta_min >= TIME_SKIP_FREEZE_BREAK_MIN else 0)
    is_sleep_action = str(sleep_mode or "").strip().lower() in ("sleep", "nap", "rest_sleep")
    retained_lower = {str(x).strip().lower() for x in (retained_names or []) if str(x).strip()}
    newly_soiled_lower = {str(x).strip().lower() for x in (newly_soiled_actors or []) if str(x).strip()}

    # Build NPC metadata lookup from party + npcs_by_name
    npc_lookup: dict[str, Mapping[str, Any]] = {}
    companion_lower: set[str] = set()
    for p in (party or []):
        if isinstance(p, Mapping) and p.get("name"):
            nm = str(p["name"]).strip().lower()
            npc_lookup[nm] = p
            if not p.get("is_player") and str(p.get("actor_type") or "").lower() != "player":
                companion_lower.add(nm)
    if isinstance(npcs_by_name, Mapping):
        for k, v in npcs_by_name.items():
            if isinstance(v, Mapping):
                npc_lookup[str(k).strip().lower()] = v
                if v.get("name"):
                    npc_lookup[str(v["name"]).strip().lower()] = v

    rels_lower: dict[str, Mapping[str, Any]] = {}
    if isinstance(relationships_by_name, Mapping):
        for rk, rv in relationships_by_name.items():
            if isinstance(rv, Mapping):
                rels_lower[str(rk).strip().lower()] = rv

    is_player_safe_res = _is_player_safe_res_for_context(sess, new_loc, new_node_id)

    for _akey, a_data in list(actors.items()):
        if not isinstance(a_data, dict):
            continue
        if str(a_data.get("actor_type") or "").lower() == "player":
            continue

        actor_name = str(a_data.get("actor_name") or _akey).strip()
        low_name = actor_name.lower()
        npc_obj = npc_lookup.get(low_name)
        latched_preset = str(a_data.get("active_outfit_preset") or "").strip()
        latched_meta = safe_json_dict(a_data.get("wardrobe_meta"))

        # Preserve bare legacy unit-test fixtures that have no NPC record and no wardrobe latch
        if npc_obj is None and not latched_preset and not latched_meta:
            continue

        npc_input = npc_obj if isinstance(npc_obj, Mapping) else {"name": actor_name, "basic_info": {}}
        basic = safe_json_dict(npc_input.get("basic_info") or npc_input.get("basic_info_json"))
        home_node_id = str(npc_input.get("home_node_id") or basic.get("home_node_id") or "").strip()
        workplace_node_id = str(npc_input.get("workplace_node_id") or basic.get("workplace_node_id") or "").strip()

        resolved = resolve_actor_wardrobe_state(
            npc_input,
            session=sess,
            scen_key=scen_key,
            location_str=new_loc,
            node_id=new_node_id,
            current_day=new_day,
            current_minute=new_min,
            is_colocated_with_player=True,
            viewer_relationship=rels_lower.get(low_name),
            active_incursion=active_incursion,
        )

        # Case 1: Newly materialized or off-screen arriving actor with no prior latch
        if not latched_preset:
            a_data["active_outfit_preset"] = resolved["active_outfit_preset"]
            a_data["wardrobe_meta"] = dict(resolved["wardrobe_meta"])
            a_data["canonical_outfit"] = dict(resolved["canonical_outfit"])
            a_data["clothing"] = dict(resolved["clothing"])
            continue

        old_kit = str(latched_meta.get("activity_kit") or "").strip()
        old_base = str(latched_meta.get("base_preset") or latched_preset).strip()
        new_kit = str(resolved.get("activity_kit") or "").strip()
        new_base = str(resolved.get("base_preset") or PRESET_DUTY).strip()
        is_companion = low_name in companion_lower or str(a_data.get("actor_type") or "").lower() == "companion"

        # Case 2: Spec #13 Post-22:00 Exit Guardrail — leaving sleep venue in sleepwear forces casual
        if latched_preset == PRESET_SLEEPWEAR and not is_sleep_venue(
            new_loc,
            new_node_id,
            npc_home_node_id=home_node_id,
            is_player_safe_res=is_player_safe_res,
        ):
            casual_slots = dict(resolved["presets"][PRESET_CASUAL])
            a_data["active_outfit_preset"] = PRESET_CASUAL
            a_data["wardrobe_meta"] = {**latched_meta, "base_preset": PRESET_CASUAL, "activity_kit": "", "overlay": ""}
            a_data["canonical_outfit"] = dict(casual_slots)
            a_data["clothing"] = dict(casual_slots)
            a_data["is_wet"] = 0
            a_data["is_bloodied"] = 0
            continue

        # Case 3: Sub-Location entry/exit (Bath/Pool/Beach Shore/Boardwalk/Dojo/Secret HQ) (Spec #9, #10)
        if new_kit != old_kit:
            if new_kit:
                a_data["active_outfit_preset"] = new_kit
                a_data["wardrobe_meta"] = dict(resolved["wardrobe_meta"])
                a_data["canonical_outfit"] = dict(resolved["canonical_outfit"])
                a_data["clothing"] = dict(resolved["clothing"])
                if old_kit in (KIT_BATH, KIT_SWIM):
                    a_data["is_wet"] = 0
                continue
            elif old_kit in (KIT_BATH, KIT_SWIM, KIT_DOJO, KIT_SPORT, KIT_SECRET_FACTION):
                # Exiting sub-location to dry venue restores prior base preset (or resolved base preset if changed)
                restore_preset = old_base if old_base in resolved["presets"] else new_base
                restored_slots = dict(resolved["presets"].get(restore_preset, resolved["clothing"]))
                a_data["active_outfit_preset"] = restore_preset
                a_data["wardrobe_meta"] = {
                    **latched_meta,
                    "base_preset": restore_preset,
                    "activity_kit": "",
                    "overlay": "",
                }
                a_data["canonical_outfit"] = dict(restored_slots)
                a_data["clothing"] = dict(restored_slots)
                a_data["is_wet"] = 0
                a_data["is_bloodied"] = 0
                continue

        # Case 4: Combat Companion Realism (Spec #6)
        if is_companion and latched_preset == PRESET_CASUAL and resolved["active_outfit_preset"] in (PRESET_DUTY, KIT_TACTICAL):
            if _is_gear_change_point(
                new_loc,
                new_node_id,
                npc_home_node_id=home_node_id,
                is_player_safe_res=is_player_safe_res,
            ):
                a_data["active_outfit_preset"] = resolved["active_outfit_preset"]
                a_data["wardrobe_meta"] = dict(resolved["wardrobe_meta"])
                a_data["canonical_outfit"] = dict(resolved["canonical_outfit"])
                a_data["clothing"] = dict(resolved["clothing"])
                a_data["is_wet"] = 0
                a_data["is_bloodied"] = 0
            # Else keep casual on-screen instead of magically spawning combat armor
            continue

        # Case 5: Spec #12 Soiled Auto-Clean & Change-Point Freeze Break (Spec #3, #8, #12 + Audit A2)
        is_soiled = bool(a_data.get("is_wet") or a_data.get("is_bloodied") or _clothing_is_disheveled(a_data.get("clothing")))
        at_change_point = is_change_point_location(
            new_loc,
            new_node_id,
            npc_home_node_id=home_node_id,
            is_player_safe_res=is_player_safe_res,
            workplace_node_id=workplace_node_id,
        )
        can_clean_soiled = (
            is_soiled
            and (low_name not in newly_soiled_lower)
            and (
                loc_changed
                or effective_skip >= TIME_SKIP_FREEZE_BREAK_MIN
                or is_sleep_action
                or resolved["active_outfit_preset"] != latched_preset
            )
        )
        should_break_freeze = False
        if at_change_point:
            if loc_changed or effective_skip >= TIME_SKIP_FREEZE_BREAK_MIN or is_sleep_action or can_clean_soiled:
                should_break_freeze = True
        elif not retained_lower and loc_changed and resolved["active_outfit_preset"] != latched_preset:
            # Non-retained actor entering new area
            should_break_freeze = True

        if should_break_freeze:
            target_changed = (
                resolved["active_outfit_preset"] != latched_preset
                or can_clean_soiled
                or bool((resolved.get("wardrobe_meta") or {}).get("fulfilled_pending_request"))
            )
            if target_changed:
                clean_slots = _clean_disheveled_slots(resolved["clothing"])
                a_data["active_outfit_preset"] = resolved["active_outfit_preset"]
                a_data["wardrobe_meta"] = dict(resolved["wardrobe_meta"])
                a_data["canonical_outfit"] = dict(clean_slots)
                a_data["clothing"] = dict(clean_slots)
                a_data["is_wet"] = 0
                a_data["is_bloodied"] = 0
        # Otherwise On-Screen Freeze preserves latched_preset and live garment states!

    return current_state


def _player_has_combat_armor(player_data: Mapping[str, Any], p_actor: Mapping[str, Any]) -> bool:
    eq = safe_json_dict(player_data.get("equipment") or player_data.get("equipment_json"))
    if eq.get("armor") or eq.get("chest") or eq.get("Armor"):
        armor_str = str(eq.get("armor") or eq.get("chest") or eq.get("Armor") or "").lower()
        if armor_str and armor_str not in ("none", "clothes", "casual", "uniform", "sleepwear"):
            return True
    clothing = p_actor.get("clothing") if isinstance(p_actor.get("clothing"), Mapping) else {}
    probe = " ".join(str(v) for v in clothing.values()).lower()
    return any(tok in probe for tok in _REAL_ARMOR_KEYWORDS)


def sync_player_cosmetic_slice_of_life_attire(
    state: dict[str, Any],
    *,
    session: Mapping[str, Any] | None = None,
    party: list[dict[str, Any]] | None = None,
    scen_key: str = "",
    location_str: str = "",
    node_id: str = "",
    current_day: int = 1,
    current_minute: int = 480,
    sleep_mode: str = "",
) -> dict[str, Any]:
    """
    Spec #7: Softly synchronizes narrative `physical_state["actors"][player_key]["clothing"]`
    during non-armored slice-of-life contexts (Student Wednesday Sport Day, Pool/Beach Shore,
    Onsen/Bathhouse, Sleep Mode in Sleep Venue) WITHOUT mutating SQLite `inventory` or DT stats.
    """
    if not isinstance(state, dict):
        return state
    actors = state.get("actors")
    if not isinstance(actors, dict):
        return state

    sess = session if isinstance(session, Mapping) else {}
    resolved_scen = str(scen_key or sess.get("scenario_key") or "fantasy").strip()
    loc_val = str(location_str or sess.get("current_location") or "")
    nid_val = str(node_id or sess.get("current_node_id") or "")

    player_key = ""
    player_data: Mapping[str, Any] = {}
    for p in (party or []):
        if isinstance(p, Mapping) and (p.get("is_player") or str(p.get("actor_type") or "").lower() == "player"):
            player_data = p
            break
    for k, v in actors.items():
        if isinstance(v, Mapping) and str(v.get("actor_type") or "").lower() == "player":
            player_key = k
            break
    if not player_key:
        return state

    p_actor = actors[player_key]
    if _player_has_combat_armor(player_data, p_actor):
        return state

    p_meta = safe_json_dict(p_actor.get("wardrobe_meta"))
    is_sleep_action = str(sleep_mode or "").strip().lower() in ("sleep", "nap", "rest_sleep")
    is_player_safe_res = _is_player_safe_res_for_context(sess, loc_val, nid_val)
    in_sleep_venue = is_sleep_venue(loc_val, nid_val, is_player_safe_res=is_player_safe_res)

    target_cosmetic = ""
    if is_sleep_action and in_sleep_venue:
        target_cosmetic = PRESET_SLEEPWEAR
    elif is_bathing_sublocation(loc_val, nid_val):
        target_cosmetic = KIT_BATH
    elif is_recreational_water_sublocation(loc_val, nid_val):
        target_cosmetic = KIT_SWIM
    elif is_wednesday_sport_window(current_day, current_minute, resolved_scen) and (
        is_school_campus_location(loc_val, nid_val)
        or is_school_context_scenario(resolved_scen)
    ):
        target_cosmetic = KIT_SPORT

    cur_cosmetic = str(p_meta.get("cosmetic_mode") or "").strip()
    if target_cosmetic == cur_cosmetic:
        return state

    if target_cosmetic:
        if "pre_activity_clothing" not in p_meta and isinstance(p_actor.get("clothing"), Mapping):
            p_meta["pre_activity_clothing"] = dict(p_actor["clothing"])
        bundle = build_npc_wardrobe_presets(player_data or {"name": p_actor.get("actor_name", "Player")}, scen_key=resolved_scen)
        if target_cosmetic == PRESET_SLEEPWEAR:
            new_slots = dict(bundle["presets"][PRESET_SLEEPWEAR])
        else:
            new_slots = dict(bundle["activity_kits"][target_cosmetic])
        p_meta["cosmetic_mode"] = target_cosmetic
        p_actor["active_outfit_preset"] = target_cosmetic
        p_actor["wardrobe_meta"] = p_meta
        p_actor["clothing"] = dict(new_slots)
        p_actor["canonical_outfit"] = dict(new_slots)
    elif cur_cosmetic:
        restored = p_meta.pop("pre_activity_clothing", None)
        p_meta.pop("cosmetic_mode", None)
        p_actor["active_outfit_preset"] = ""
        p_actor["wardrobe_meta"] = p_meta
        if isinstance(restored, dict) and restored:
            p_actor["clothing"] = dict(restored)
            p_actor["canonical_outfit"] = dict(restored)

    return state
