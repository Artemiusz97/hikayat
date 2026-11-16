from __future__ import annotations
"""
Wearable Gift Routing & Persona-Gated Outfit Request Evaluation (Specs #6, #11, #13).
"""

import re
from typing import Any, Mapping

from mechanics.world.world_schedule import is_weekend

from .catalog import build_npc_wardrobe_presets
from .constants import (
    AFTER_SCHOOL_UNIFORM_END_MIN,
    KIT_SWIM,
    PRESET_CASUAL,
    PRESET_DUTY,
    PRESET_SLEEPWEAR,
    SCHOOL_ARRIVAL_MIN,
    is_change_point_location,
    is_private_bedroom_sublocation,
    is_school_campus_location,
    is_sleep_venue,
    safe_json_dict,
)
from .resolver import is_nsfw_context

_LINGERIE_TOKENS = (
    "lingerie",
    "panties",
    "knickers",
    "thong",
    "g-string",
    "bra",
    "bralette",
    "garter",
    "stockings",
    "babydoll",
    "teddies",
    "lacy underwear",
    "silk underwear",
)

_SLEEPWEAR_TOKENS = (
    "pajama",
    "pyjama",
    "nightgown",
    "nightie",
    "negligee",
    "sleep shirt",
    "sleepwear",
    "sleep shorts",
    "nightshirt",
    "silk slip",
    "bathrobe",
)

_ACCESSORY_TOKENS = (
    "necklace",
    "choker",
    "scarf",
    "ribbon",
    "hairpin",
    "glasses",
    "spectacles",
    "bracelet",
    "earring",
    "ring",
    "brooch",
    "watch",
    "amulet",
    "pendant",
)

_DUTY_UNIFORM_TOKENS = (
    "uniform",
    "armor",
    "breastplate",
    "tactical rig",
    "combat vest",
    "blazer",
)

_OUTFIT_REQUEST_RE = re.compile(
    r"\b(?:wear|put\s+on|change\s+into|slip\s+into|dress\s+in|come\s+in)\s+(?:your|the|my|that|this|a|an|some)?\s*([a-z0-9'\" -]{2,48})",
    re.IGNORECASE,
)


def classify_wearable_gift_target(
    item_dict: Mapping[str, Any] | None,
    item_name: str,
) -> tuple[str, str]:
    """
    Returns (target_preset_bucket, slot_category).
    target_preset_bucket in {'casual', 'sleepwear', 'lingerie', 'accessory', 'duty'}.
    slot_category in {'Top', 'Bottom', 'Outerwear', 'Footwear', 'Lingerie', 'Accessory', ''}.
    """
    name = str(item_name or "").strip()
    d = item_dict if isinstance(item_dict, Mapping) else {}
    low_name = name.lower()
    raw_type = str(d.get("item_type") or d.get("type") or d.get("category") or "").strip().lower()
    raw_slot = str(d.get("slot") or d.get("equip_slot") or "").strip().lower()
    probe = f"{low_name} {raw_type} {raw_slot}".strip()

    if any(t in probe for t in _LINGERIE_TOKENS) or "lingerie" in raw_slot or "underwear" in raw_slot:
        return "lingerie", "Lingerie"
    if any(t in probe for t in _ACCESSORY_TOKENS) or "accessory" in raw_slot or "accessories" in raw_type:
        return "accessory", "Accessory"
    if any(t in probe for t in _SLEEPWEAR_TOKENS):
        slot_cat = "Outerwear" if ("robe" in low_name or "cardigan" in low_name) else "Top"
        return PRESET_SLEEPWEAR, slot_cat
    if any(t in probe for t in _DUTY_UNIFORM_TOKENS) and "pajama" not in low_name:
        if "shoe" in probe or "boot" in probe or "heels" in probe:
            return PRESET_DUTY, "Footwear"
        if "coat" in probe or "jacket" in probe or "cloak" in probe or "blazer" in probe:
            return PRESET_DUTY, "Outerwear"
        if "skirt" in probe or "pants" in probe or "trouser" in probe or "shorts" in probe:
            return PRESET_DUTY, "Bottom"
        return PRESET_DUTY, "Top"

    # Default wearable fashion gifts -> casual preset
    if any(k in probe for k in ("skirt", "jeans", "pants", "trouser", "shorts", "leggings", "slacks")):
        return PRESET_CASUAL, "Bottom"
    if any(k in probe for k in ("shoes", "boots", "sneakers", "heels", "sandals", "slippers")):
        return PRESET_CASUAL, "Footwear"
    if any(k in probe for k in ("jacket", "coat", "cardigan", "hoodie", "shawl", "cloak", "vest")):
        return PRESET_CASUAL, "Outerwear"
    if any(k in probe for k in ("shirt", "blouse", "dress", "sundress", "sweater", "top", "tunic", "kimono", "yukata", "camisole", "tank")):
        return PRESET_CASUAL, "Top"
    if raw_type in ("apparel", "clothing", "garment", "outfit"):
        return PRESET_CASUAL, "Top"
    return "", ""


def route_wearable_gift_to_preset(
    item_dict: Mapping[str, Any] | None,
    item_name: str,
    npc_or_contact: Mapping[str, Any] | None = None,
    *,
    scen_key: str = "",
    location_str: str = "",
    node_id: str = "",
    current_day: int = 1,
    current_minute: int = 480,
    current_active_preset: str = "",
) -> dict[str, Any]:
    """
    Spec #6: Routes wearable gifts into matching preset buckets (`casual`, `sleepwear`,
    `lingerie`, `accessory`, `duty`) and determines whether equipping right now is
    venue-appropriate.
    """
    target_bucket, slot_cat = classify_wearable_gift_target(item_dict, item_name)
    npc = npc_or_contact if isinstance(npc_or_contact, Mapping) else {}
    basic = safe_json_dict(npc.get("basic_info") or npc.get("basic_info_json"))

    if not target_bucket or not slot_cat:
        return {
            "routed": False,
            "target_preset": "",
            "slot_category": "",
            "should_equip_now": False,
            "defer_note": "",
            "basic_info": basic,
        }

    label = str(item_name or "").strip()
    by_preset = safe_json_dict(basic.get("gifted_wardrobe_by_preset"))
    bucket_map = safe_json_dict(by_preset.get(target_bucket))
    bucket_map[slot_cat] = label
    by_preset[target_bucket] = bucket_map
    basic["gifted_wardrobe_by_preset"] = by_preset

    # Mirror into legacy flat gifted_wardrobe dict for backwards compat with older callers
    legacy = safe_json_dict(basic.get("gifted_wardrobe"))
    if target_bucket == PRESET_SLEEPWEAR:
        legacy["Sleepwear"] = label
    else:
        legacy[slot_cat] = label
    basic["gifted_wardrobe"] = legacy

    safe_min = int(current_minute if current_minute is not None else 480) % 1440
    in_sleep = is_sleep_venue(location_str, node_id, npc_home_node_id=str(npc.get("home_node_id") or basic.get("home_node_id") or ""))
    in_private = is_private_bedroom_sublocation(location_str, node_id)
    in_change_pt = is_change_point_location(location_str, node_id, npc_home_node_id=str(npc.get("home_node_id") or basic.get("home_node_id") or ""))
    active_p = str(current_active_preset or "").strip().lower()

    should_equip_now = False
    defer_note = ""

    if target_bucket == "accessory":
        should_equip_now = True
    elif target_bucket == "lingerie":
        should_equip_now = bool(in_private or in_sleep or in_change_pt)
        if not should_equip_now:
            defer_note = f"saved '{label}' in lingerie drawer for private/bedroom wear"
    elif target_bucket == PRESET_SLEEPWEAR:
        should_equip_now = bool(active_p == PRESET_SLEEPWEAR or in_private or in_sleep)
        if not should_equip_now:
            defer_note = f"folded '{label}' into Sleepwear preset for tonight at home"
    elif target_bucket == PRESET_DUTY:
        should_equip_now = bool(active_p == PRESET_DUTY or in_change_pt)
        if not should_equip_now:
            defer_note = f"stored '{label}' in Main/Duty wardrobe"
    else:  # PRESET_CASUAL
        on_school_hours = is_school_campus_location(location_str, node_id) and not is_weekend(current_day) and (SCHOOL_ARRIVAL_MIN <= safe_min < AFTER_SCHOOL_UNIFORM_END_MIN)
        should_equip_now = bool(active_p == PRESET_CASUAL or (not on_school_hours and (in_change_pt or active_p != PRESET_DUTY)))
        if not should_equip_now:
            defer_note = f"tucked '{label}' into Casual wardrobe for after-school or weekend dates"

    return {
        "routed": True,
        "target_preset": target_bucket,
        "slot_category": slot_cat,
        "item_label": label,
        "should_equip_now": should_equip_now,
        "defer_note": defer_note,
        "basic_info": basic,
    }


def detect_outfit_request_intent(
    user_text: str,
    *,
    target_npc_name: str = "",
) -> dict[str, Any]:
    """Detects player outfit requests in dialogue or Phone DM messages."""
    text = str(user_text or "").strip()
    if not text:
        return {"detected": False}
    low = text.lower()

    if any(k in low for k in ("without a bra", "no bra", "bra-less", "braless", "take off your bra")):
        return {
            "detected": True,
            "requested_preset": "bra_less",
            "requested_item_phrase": "no bra",
            "target_npc": target_npc_name,
            "is_date_request": "date" in low or "tonight" in low or "meet" in low,
        }
    if any(k in low for k in ("no panties", "no underwear", "without underwear", "without panties", "go commando")):
        return {
            "detected": True,
            "requested_preset": "commando",
            "requested_item_phrase": "commando",
            "target_npc": target_npc_name,
            "is_date_request": "date" in low or "tonight" in low or "meet" in low,
        }

    if any(k in low for k in (
        "unbutton your blazer",
        "unbutton your jacket",
        "unbutton your coat",
        "take off your jacket",
        "take off your blazer",
        "remove your coat",
        "remove your jacket",
        "take off your cardigan",
        "put on your jacket",
        "put on your coat",
        "put on your blazer",
    )):
        return {
            "detected": True,
            "requested_preset": "outerwear_toggle",
            "requested_item_phrase": text[:64].strip(),
            "target_npc": target_npc_name,
            "is_date_request": False,
        }

    has_wear_verb = any(
        k in low
        for k in ("wear ", "put on", "change into", "slip into", "dress in", "come wearing", "in your ")
    )
    if not has_wear_verb:
        return {"detected": False}

    m = _OUTFIT_REQUEST_RE.search(text)
    phrase = m.group(1).strip(" .,!?;:\"'") if m else ""

    requested_preset = ""
    if any(k in low for k in _ACCESSORY_TOKENS):
        requested_preset = "accessory"
    elif any(k in low for k in ("pajama", "pyjama", "nightgown", "negligee", "sleepwear")):
        requested_preset = PRESET_SLEEPWEAR
    elif any(k in low for k in ("bikini", "swimsuit", "swimwear")):
        requested_preset = KIT_SWIM
    elif any(k in low for k in ("lingerie", "lace", "stockings")):
        requested_preset = "lingerie"
    elif any(k in low for k in ("casual", "sundress", "hoodie", "jeans", "skirt", "dress")):
        requested_preset = PRESET_CASUAL
    elif any(k in low for k in ("uniform", "work outfit", "suit")):
        requested_preset = PRESET_DUTY
    elif phrase:
        requested_preset = PRESET_CASUAL

    if not requested_preset and not phrase:
        return {"detected": False}

    return {
        "detected": True,
        "requested_preset": requested_preset or PRESET_CASUAL,
        "requested_item_phrase": phrase or requested_preset,
        "target_npc": target_npc_name,
        "is_date_request": any(k in low for k in ("date", "tonight", "later", "meetup", "rendezvous", "meet me")),
    }


def evaluate_outfit_request_compliance(
    npc: Mapping[str, Any],
    request_intent: Mapping[str, Any],
    *,
    scen_key: str = "",
    session: Mapping[str, Any] | None = None,
    location_str: str = "",
    node_id: str = "",
    current_day: int = 1,
    current_minute: int = 480,
    relationship: Mapping[str, Any] | None = None,
    current_turn: int = 0,
    is_dm: bool = False,
    current_clothing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Spec #11: Persona-gated outfit request compliance/refusal evaluator.
    Checks dress-code mismatches (`casual` in class, `sleepwear` outdoors, `bra_less`/`commando`
    in public), persona traits, and romantic affinity.
    """
    if not isinstance(request_intent, Mapping) or not request_intent.get("detected"):
        return {"status": "none", "directive_text": "", "dress_code_violation": False}

    bundle = build_npc_wardrobe_presets(npc, scen_key=scen_key or str((session or {}).get("scenario_key") or "fantasy"))
    meta = bundle["meta"]
    rel = relationship if isinstance(relationship, Mapping) else {}
    aff = 0
    try:
        aff = int(rel.get("affinity") if rel.get("affinity") is not None else (npc.get("affinity") or 0))
    except Exception:
        aff = 0
    track = str(rel.get("track") or npc.get("relationship_track") or "").strip().lower()
    is_romantic = track == "romantic" or aff >= 100
    nsfw = is_nsfw_context(session, scen_key)

    req_preset = str(request_intent.get("requested_preset") or PRESET_CASUAL).strip().lower()
    req_phrase = str(request_intent.get("requested_item_phrase") or req_preset).strip()
    is_date_req = bool(request_intent.get("is_date_request")) or is_dm

    safe_min = int(current_minute if current_minute is not None else 480) % 1440
    in_campus_class = (
        is_school_campus_location(location_str, node_id)
        and not is_weekend(current_day)
        and (SCHOOL_ARRIVAL_MIN <= safe_min < AFTER_SCHOOL_UNIFORM_END_MIN)
    )
    in_sleep_or_private = is_sleep_venue(location_str, node_id) or is_private_bedroom_sublocation(location_str, node_id)

    is_public_dress_violation = False
    if not is_dm:
        if req_preset == PRESET_SLEEPWEAR and not in_sleep_or_private:
            is_public_dress_violation = True
        elif req_preset == KIT_SWIM and not in_sleep_or_private and "pool" not in location_str.lower() and "beach" not in location_str.lower():
            is_public_dress_violation = True
        elif req_preset == PRESET_CASUAL and in_campus_class and meta.get("is_student"):
            is_public_dress_violation = True
        elif req_preset in ("bra_less", "commando", "lingerie") and not in_sleep_or_private:
            is_public_dress_violation = True

    npc_name = meta["name"]
    subj_pron = "he" if meta.get("is_male") else "she"
    basic_meta = meta.get("basic") if isinstance(meta.get("basic"), Mapping) else {}
    at_change_point = is_change_point_location(
        location_str,
        node_id,
        npc_home_node_id=str(npc.get("home_node_id") or basic_meta.get("home_node_id") or ""),
    )
    can_violate = bool(
        meta.get("is_shameless")
        or meta.get("is_rebellious")
        or (meta.get("is_bold_or_shameless") and aff >= 60)
        or (nsfw and is_romantic and aff >= 100)
    )
    is_public_micro = req_preset in ("bra_less", "commando", "accessory", "outerwear_toggle")
    is_slot_patch = is_public_micro or req_preset == "lingerie"
    if is_slot_patch and isinstance(current_clothing, Mapping) and current_clothing:
        base_slots = dict(current_clothing)
    else:
        base_slots = dict(
            bundle["presets"].get(req_preset)
            or bundle["activity_kits"].get(req_preset)
            or bundle["presets"][PRESET_DUTY if in_campus_class else PRESET_CASUAL]
        )

    # Defer future date requests, DM prep requests, or public non-change-point full swaps
    if (is_date_req and not is_public_dress_violation) or (
        not is_dm and not is_public_dress_violation and not is_public_micro and not at_change_point
    ):
        pending = {
            "requested_preset": req_preset,
            "requested_item_phrase": req_phrase,
            "status": "deferred_to_venue_or_date",
            "is_violation": False,
            "turn_requested": int(current_turn or 0),
        }
        return {
            "status": "deferred_to_venue_or_date",
            "dress_code_violation": False,
            "pending_request_payload": pending,
            "directive_text": (
                f"[PRE-TURN OUTFIT REQUEST — AGREED FOR CHANGE POINT / DATE]\n"
                f"{npc_name} gladly agrees to wear '{req_phrase}' once at home, a changing area, or on your date."
            ),
        }

    if is_public_dress_violation:
        if meta.get("is_prude") or not can_violate:
            return {
                "status": "refused",
                "dress_code_violation": False,
                "pending_request_payload": None,
                "directive_text": (
                    f"[PRE-TURN OUTFIT REQUEST — REFUSAL]\n"
                    f"The player asked {npc_name} to wear '{req_phrase}' in an inappropriate public setting "
                    f"({location_str or 'current venue'}). Because {npc_name} respects modesty / dress code, "
                    f"{subj_pron} refuses or gently postpones the request until they are somewhere private."
                ),
            }

        # Rebellious / Bold / High-intimacy NSFW partner complies with violation flag
        if req_preset == PRESET_SLEEPWEAR and not nsfw:
            # SFW public sleepwear compromise wraps an outerwear coat/cardigan over sleepwear
            base_slots["outerwear"] = "Long casual overcoat over sleepwear"
        if req_preset == "bra_less":
            base_slots["under_top"] = "None (Bra-less)"
        elif req_preset == "commando":
            base_slots["under_bottom"] = "None (Commando)"
        base_slots["top"] = f"{base_slots.get('top', 'Outfit')} [provocative] [dress_code_violation]"

        pending = {
            "requested_preset": req_preset,
            "requested_item_phrase": req_phrase,
            "status": "complied_violation",
            "is_violation": True,
            "turn_requested": int(current_turn or 0),
        }
        return {
            "status": "complied_violation",
            "dress_code_violation": True,
            "pending_request_payload": pending,
            "clothing_override": base_slots,
            "directive_text": (
                f"[PRE-TURN OUTFIT REQUEST — COMPLIED (#DressCodeViolation)]\n"
                f"{npc_name} daringly indulges the request ('{req_phrase}') despite public rules. "
                f"Nearby onlookers or strict faculty may react to the `#DressCodeViolation`."
            ),
        }

    # Immediate compliance (at Change Point, private bedroom, or micro-adjustment)
    phrase_low = req_phrase.lower()
    if req_preset == "accessory":
        if phrase_low and phrase_low not in base_slots.get("top", "").lower():
            base_slots["top"] = f"{base_slots.get('top', 'Outfit')} (wearing {req_phrase})"
    elif req_preset == "outerwear_toggle":
        if "take off" in phrase_low or "remove" in phrase_low:
            base_slots["outerwear"] = "none"
        elif "unbutton" in phrase_low:
            cur_out = str(base_slots.get("outerwear") or "none").strip()
            if cur_out.lower() not in ("none", ""):
                base_slots["outerwear"] = f"Unbuttoned ({cur_out})"
    elif req_preset == "lingerie":
        clean_l = req_phrase if phrase_low not in ("lingerie", "") else "lacy lingerie set"
        if not meta.get("is_male"):
            base_slots["under_top"] = f"Worn ({clean_l})"
        base_slots["under_bottom"] = f"Worn ({clean_l})"
    elif req_preset == "bra_less":
        base_slots["under_top"] = "None (Bra-less)"
    elif req_preset == "commando":
        base_slots["under_bottom"] = "None (Commando)"

    pending = {
        "requested_preset": req_preset,
        "requested_item_phrase": req_phrase,
        "status": "complied_immediate",
        "is_violation": False,
        "turn_requested": int(current_turn or 0),
    }
    return {
        "status": "complied_immediate",
        "dress_code_violation": False,
        "pending_request_payload": pending,
        "clothing_override": base_slots,
        "directive_text": (
            f"[PRE-TURN OUTFIT REQUEST — COMPLIED]\n"
            f"{npc_name} wears '{req_phrase}' as requested."
        ),
    }
