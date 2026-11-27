"""
mechanics/social/folklore_roster.py
===================================
Deterministic pregenerated roster generation, catalog lookup, circadian village
stage scheduling, and non-mutating preview helpers for the Hidden Kitsune Village
(6 villagers) and Hidden Orang Bunian Village (7 villagers).

Database mutations, lazy hydration, form shifting, companion recruitment, and turn
rollbacks live in `mechanics/social/folklore_roster_lifecycle.py` and are re-exported
here for facade compatibility.
"""
from __future__ import annotations

import json
import logging
import random
import re
from typing import Any, Dict, List, Optional, Tuple

import db
import scenario_data
from mechanics.world.locations.folklore_veil import (
    get_village_veil_status,
    load_folklore_villages_catalog,
)

log = logging.getLogger("hikayat.social.folklore_roster")

FOLKLORE_RACES: Tuple[str, ...] = (
    "orang_bunian",
    "kitsune:humanoid",
    "kitsune:myobu_fox",
    "ghoul:humanoid",
    "ghoul:canid",
)


def _normalize_pc_gender_bucket(player_gender: str) -> str:
    g = str(player_gender or "").strip().lower()
    if g in ("male", "m", "man", "boy", "he/him"):
        return "male"
    if g in ("female", "f", "woman", "girl", "she/her"):
        return "female"
    return "nonbinary"


def _slugify_id(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text or "").strip().lower()).strip("_") or "folklore_npc"


from mechanics.social.races import (
    is_folklore_beast_race,
    is_folklore_race,
    is_ghoul_canid_race,
    is_ghoul_race,
    is_myobu_fox_race,
)
from mechanics.social.folklore_ghoul import (
    normalize_canid_species,
    resolve_ghoul_contextual_form,
    shift_ghoul_form,
    sync_ghoul_contextual_forms_for_node,
)


def npc_is_folklore_villager(npc_or_info: Any) -> bool:
    """Returns True if a contact/entity dict or basic_info dict belongs to a folklore villager."""
    if not isinstance(npc_or_info, dict):
        return False
    basic = npc_or_info.get("basic_info")
    if isinstance(basic, str):
        try:
            basic = json.loads(basic)
        except Exception:
            basic = {}
    if not isinstance(basic, dict):
        basic = {}
    if npc_or_info.get("is_folklore_villager") or basic.get("is_folklore_villager"):
        return True
    if npc_or_info.get("folklore_village") or basic.get("folklore_village"):
        return True
    race = str(npc_or_info.get("race") or basic.get("race") or "").strip().lower()
    return is_folklore_race(race)


def _build_villager_stats(tier: int, is_mystic: bool = False) -> Dict[str, int]:
    base = 10 + int(tier) * 2
    if is_mystic:
        return {"STR": base - 2, "PER": base + 3, "END": base, "CHA": base + 3, "INT": base + 4, "AGI": base + 2, "LUK": base + 1}
    return {"STR": base + 1, "PER": base + 3, "END": base + 1, "CHA": base + 2, "INT": base + 1, "AGI": base + 4, "LUK": base + 1}


def build_villager_basic_info_dict(spec: Dict[str, Any], is_befriended: bool = False) -> Dict[str, Any]:
    """Constructs the canonical `basic_info` payload shared by stage previews and DB hydration."""
    v_key = str(spec.get("folklore_village") or "").strip().lower()
    ghoul_met_relay = v_key == "ghoul"
    relay_ok = bool(is_befriended or ghoul_met_relay)
    return {
        "role": spec["role"],
        "rank_title": spec["rank_title"],
        "occupation": spec["role"],
        "gender": spec["gender"],
        "race": spec["race"],
        "initial_form": spec.get("initial_form", spec["race"]),
        "age_group": "adult",
        "anomalous_npc_tag": "folklore_villager",
        "social_role_type": "folklore_villager",
        "is_folklore_villager": True,
        "folklore_village": spec["folklore_village"],
        "is_sovereign": bool(spec.get("is_sovereign")),
        "is_royal_heir": bool(spec.get("is_royal_heir")),
        "secret_crush_on_pc": bool(spec.get("secret_crush_on_pc")),
        "predatory_fascination_on_pc": bool(spec.get("predatory_fascination_on_pc")),
        "is_daytime_wanderer": bool(spec.get("is_daytime_wanderer")),
        "is_ghoul_city_wanderer": bool(spec.get("is_ghoul_city_wanderer")),
        "default_humanoid_outside_hunt": bool(spec.get("default_humanoid_outside_hunt")),
        "canid_species": str(spec.get("canid_species") or ""),
        "glamour_tell": str(spec.get("glamour_tell") or ""),
        "tail_count": int(spec.get("tail_count") or 0),
        "agent_tier": int(spec.get("agent_tier") or 3),
        "innate_abilities": list(spec.get("innate_abilities") or []),
        "humanoid_kit_key": spec.get("humanoid_kit_key", ""),
        "combat_kit_key": spec.get("combat_kit_key", ""),
        "stats": dict(spec.get("stats") or {}),
        "home_node": spec.get("home_node", ""),
        "merchant_type": spec.get("merchant_type", ""),
        "description": spec.get("personality_summary", ""),
        "met_in_person": True,
        "contact_added": relay_ok,
        "is_contact": relay_ok,
        "has_contact_info": relay_ok,
        "unlocked_via_friendship": bool(is_befriended),
        "spirit_relay_unlocked": relay_ok,
    }


def has_spirit_relay_contact(contact: Any) -> bool:
    """Returns True when a contact can be messaged over the Spirit Relay (befriended or met Ghoul court contact)."""
    if not isinstance(contact, dict):
        return False
    if contact.get("spirit_relay_unlocked"):
        return True
    bi = contact.get("basic_info")
    if isinstance(bi, str) and bi.strip():
        try:
            bi = json.loads(bi)
        except Exception:
            bi = {}
    if not isinstance(bi, dict) and isinstance(contact.get("basic_info_json"), str):
        try:
            bi = json.loads(contact["basic_info_json"])
        except Exception:
            bi = {}
    if not isinstance(bi, dict):
        return False
    if bi.get("spirit_relay_unlocked"):
        return True
    return (
        str(bi.get("folklore_village") or "").strip().lower() == "ghoul"
        and bool(bi.get("met_in_person"))
    )


def _build_kitsune_entry(
    rng: random.Random,
    slot: Dict[str, Any],
    gender: str,
    initial_form: str,
    catalog: Dict[str, Any],
    used_names: set[str],
    name_override: str = "",
    slot_key_override: str = "",
) -> Dict[str, Any]:
    pools = (catalog.get("name_pools") or {}).get("kitsune") or {}
    palettes = catalog.get("appearance_palettes") or {}
    kits = catalog.get("combat_kits") or {}

    g_low = str(gender or "female").strip().lower()
    g_canon = "Female" if g_low == "female" else "Male"
    if name_override:
        full_name = name_override
    elif slot.get("is_sovereign"):
        full_name = str(pools.get("sovereign_female" if g_low == "female" else "sovereign_male"))
    else:
        given_pool = list(pools.get("female_given" if g_low == "female" else "male_given") or ["Kohaku"])
        surnames = list(pools.get("surnames") or ["Inari"])
        full_name = ""
        for _ in range(30):
            cand = f"{rng.choice(given_pool)} {rng.choice(surnames)}"
            if cand.lower() not in used_names:
                full_name = cand
                break
        if not full_name:
            full_name = f"{given_pool[0]} {surnames[0]}"
    used_names.add(full_name.lower())

    s_key = slot_key_override or str(slot["slot_key"])
    npc_id = f"folklore_{s_key}"
    tails = max(1, min(9, int(slot.get("tails") or 1)))
    coat = str(slot.get("coat") or rng.choice(palettes.get("kitsune_coats") or ["Vibrant Rust-Red Fox Fur"]))
    eyes = str(slot.get("eyes") or rng.choice(palettes.get("kitsune_eyes") or ["Sunburst Gold"]))
    humanoid_kit_key = str(slot.get("combat_kit") or "kitsune_mystic")
    active_kit_key = "kitsune_myobu_beast" if initial_form == "kitsune:myobu_fox" else humanoid_kit_key
    active_abilities = list(kits.get(active_kit_key) or [])

    tail_word = "tail" if tails == 1 else "tails"
    humanoid_garment = (
        "Crimson-and-gold hinoki shrine kimono with embroidered nine-tail celestial haori"
        if tails == 9
        else "Vermilion-and-ivory Inari shrine kimono with braided foxfire haori cord"
    )
    appearance = {
        "gender": g_canon,
        "age_appearance": "ageless young adult",
        "eyes": eyes,
        "hair": coat.replace(" Fox Fur", "").replace(" Kitsune Fur", ""),
        "fur_coat": coat,
        "coat_color": coat if initial_form == "kitsune:myobu_fox" else "",
        "tail_count": tails,
        "ears": "Alert Pointed Kitsune Fox Ears",
        "tails_description": f"{tails} plush {coat.lower()} {tail_word}",
        "distinctive_features": f"{tails} plush {coat.lower()} {tail_word} & pointed fox ears",
        "build": "Slender Graceful Lithe" if g_low == "female" else "Lean Poised Lithe",
        "physique": "Slim" if g_low == "female" else "Athletic",
        "outfit_summary": "Unclothed sacred spirit-fox coat wreathed in kitsunebi wisps" if initial_form == "kitsune:myobu_fox" else humanoid_garment,
        "outfit_style": "" if initial_form == "kitsune:myobu_fox" else humanoid_garment,
        "humanoid_outfit": humanoid_garment,
        "kitsune_form": initial_form,
    }
    tier = int(slot.get("agent_tier") or 3)
    return {
        "npc_id": npc_id,
        "slot_key": s_key,
        "name": full_name,
        "gender": g_canon,
        "race": initial_form,
        "initial_form": initial_form,
        "folklore_village": "kitsune",
        "village_id": "loc_hidden_kitsune_village",
        "home_zone_id": "zone_eastern_sanctuary",
        "home_node": str(slot.get("home_node") or "sub_kitsune_inner_plaza"),
        "role": str(slot.get("role") or "Kitsune Shrine Spirit"),
        "rank_title": str(slot.get("rank_title") or "Inari Spirit"),
        "agent_tier": tier,
        "tail_count": tails,
        "is_folklore_villager": True,
        "is_sovereign": bool(slot.get("is_sovereign")),
        "is_royal_heir": False,
        "is_daytime_wanderer": bool(slot.get("is_daytime_wanderer")),
        "glamour_tell": str(slot.get("glamour_tell") or ""),
        "merchant_type": str(slot.get("merchant_type") or ""),
        "humanoid_kit_key": humanoid_kit_key,
        "combat_kit_key": active_kit_key,
        "innate_abilities": active_abilities,
        "stats": _build_villager_stats(tier, is_mystic=("mystic" in humanoid_kit_key or "sovereign" in humanoid_kit_key)),
        "schedule": dict(slot.get("schedule") or {}),
        "personality_summary": str(slot.get("personality") or ""),
        "appearance": appearance,
        "initial_affinity": 10 if slot.get("is_sovereign") else 5,
        "secret_crush_on_pc": False,
        "virgin": False,
        "single": True,
        "hydrated": False,
        "befriended": False,
    }


def _build_bunian_entry(
    rng: random.Random,
    slot: Dict[str, Any],
    gender: str,
    catalog: Dict[str, Any],
    used_names: set[str],
    name_override: str = "",
    slot_key_override: str = "",
) -> Dict[str, Any]:
    pools = (catalog.get("name_pools") or {}).get("bunian") or {}
    palettes = catalog.get("appearance_palettes") or {}
    kits = catalog.get("combat_kits") or {}
    honorifics = pools.get("honorifics") or {}

    g_low = str(gender or "female").strip().lower()
    g_canon = "Female" if g_low == "female" else "Male"
    s_key = slot_key_override or str(slot["slot_key"])
    if name_override:
        full_name = name_override
    elif slot.get("is_royal_heir"):
        full_name = str(pools.get("royal_female" if g_low == "female" else "royal_male"))
    else:
        role_tag = "scout"
        for cand_tag in ("elder", "merchant", "guardian", "healer", "scout"):
            if cand_tag in s_key:
                role_tag = cand_tag
                break
        title_prefix = str(honorifics.get(f"{role_tag}_{g_low}") or ("Dayang" if g_low == "female" else "Awang"))
        given_pool = list(pools.get("female_given" if g_low == "female" else "male_given") or ["Kirana"])
        full_name = ""
        for _ in range(30):
            cand = f"{title_prefix} {rng.choice(given_pool)}"
            if cand.lower() not in used_names:
                full_name = cand
                break
        if not full_name:
            full_name = f"{title_prefix} {given_pool[0]}"
    used_names.add(full_name.lower())

    npc_id = f"folklore_{s_key}"
    skin = rng.choice(palettes.get("bunian_skin_tones") or ["Luminous Ivory-Fair Porcelain"])
    build_pool = palettes.get("bunian_female_builds" if g_low == "female" else "bunian_male_builds") or ["Graceful Lithe Sculpted"]
    build = rng.choice(build_pool)
    regalia_pool = palettes.get("bunian_female_regalia" if g_low == "female" else "bunian_male_regalia") or [
        "Ivory-and-gold Nusantara royal songket attire"
    ]
    regalia = regalia_pool[0] if slot.get("is_royal_heir") else rng.choice(regalia_pool)

    kit_key = str(slot.get("combat_kit") or "bunian_pawang")
    tier = int(slot.get("agent_tier") or 3)
    is_royal = bool(slot.get("is_royal_heir"))

    appearance = {
        "gender": g_canon,
        "age_appearance": "timeless luminous youth",
        "skin_tone": skin,
        "skin_color": skin,
        "ears": "Slender Pointed Elf Ears",
        "distinctive_features": "Slender Pointed Elf Ears & Luminous Kayangan Aura",
        "eyes": rng.choice(["Warm Starlit Hazel", "Luminous Emerald-Gold", "Clear Obsidian-Amber", "Soft Moonlit Topaz"]),
        "hair": rng.choice(["Flowing Glossy Raven Silk", "Long Midnight-Chestnut Waves", "Lustrous Ebony Silk"]),
        "build": build,
        "body_type": build,
        "physique": "Slim" if g_low == "female" else "Athletic",
        "outfit_summary": regalia,
        "outfit_style": regalia,
        "humanoid_outfit": regalia,
    }
    if is_royal:
        appearance["predetermined_intercourse"] = "virgin"
        appearance["intercourse_experience"] = "virgin"

    return {
        "npc_id": npc_id,
        "slot_key": s_key,
        "name": full_name,
        "gender": g_canon,
        "race": "orang_bunian",
        "initial_form": "orang_bunian",
        "folklore_village": "bunian",
        "village_id": "loc_hidden_bunian_village",
        "home_zone_id": "zone_woods_reserve",
        "home_node": str(slot.get("home_node") or "sub_bunian_inner_plaza"),
        "role": ("Puteri Diraja of Kampung Kayangan" if g_low == "female" else "Putera Diraja of Kampung Kayangan")
        if is_royal
        else str(slot.get("role") or "Orang Bunian Noble"),
        "rank_title": ("Puteri Diraja" if g_low == "female" else "Putera Diraja") if is_royal else str(slot.get("rank_title") or "Kayangan Courtier"),
        "agent_tier": tier,
        "tail_count": 0,
        "is_folklore_villager": True,
        "is_sovereign": bool(slot.get("is_sovereign")),
        "is_royal_heir": is_royal,
        "is_daytime_wanderer": bool(slot.get("is_daytime_wanderer")),
        "glamour_tell": str(slot.get("glamour_tell") or ""),
        "merchant_type": str(slot.get("merchant_type") or ""),
        "humanoid_kit_key": kit_key,
        "combat_kit_key": kit_key,
        "innate_abilities": list(kits.get(kit_key) or []),
        "stats": _build_villager_stats(tier, is_mystic=("royal" in kit_key or "pawang" in kit_key)),
        "schedule": dict(slot.get("schedule") or {}),
        "personality_summary": str(slot.get("personality") or ""),
        "appearance": appearance,
        "initial_affinity": int(slot.get("initial_affinity") or (20 if is_royal else 5)),
        "secret_crush_on_pc": bool(slot.get("secret_crush_on_pc") and is_royal),
        "virgin": bool(slot.get("virgin") and is_royal),
        "single": True,
        "hydrated": False,
        "befriended": False,
    }


def _build_ghoul_entry(
    rng: random.Random,
    slot: Dict[str, Any],
    gender: str,
    catalog: Dict[str, Any],
    used_names: set[str],
    name_override: str = "",
    slot_key_override: str = "",
) -> Dict[str, Any]:
    pools = (catalog.get("name_pools") or {}).get("ghoul") or {}
    palettes = catalog.get("appearance_palettes") or {}
    kits = catalog.get("combat_kits") or {}

    g_low = str(gender or "female").strip().lower()
    g_canon = "Female" if g_low == "female" else "Male"
    s_key = slot_key_override or str(slot["slot_key"])
    if name_override:
        full_name = name_override
    elif slot.get("is_royal_heir"):
        full_name = str(pools.get("heir_female" if g_low == "female" else "heir_male") or ("Nadia Haddad" if g_low == "female" else "Tariq Haddad"))
    else:
        given_pool = list(pools.get("female_given" if g_low == "female" else "male_given") or ["Nadia"])
        surnames = list(pools.get("surnames") or ["Haddad"])
        full_name = ""
        for _ in range(30):
            cand = f"{rng.choice(given_pool)} {rng.choice(surnames)}"
            if cand.lower() not in used_names:
                full_name = cand
                break
        if not full_name:
            full_name = f"{given_pool[0]} {surnames[0]}"
    used_names.add(full_name.lower())

    npc_id = f"folklore_{s_key}"
    canid_sp = normalize_canid_species(slot.get("canid_species"), seed=s_key)
    initial_form = str(
        slot.get("forced_initial_form")
        or ("ghoul:humanoid" if slot.get("default_humanoid_outside_hunt", True) else "ghoul:canid")
    ).strip().lower()
    if initial_form not in ("ghoul:humanoid", "ghoul:canid"):
        initial_form = "ghoul:humanoid"

    skin = rng.choice(palettes.get("ghoul_skin_tones") or ["Pale Cool Alabaster Porcelain"])
    eyes = rng.choice(palettes.get("ghoul_eyes") or ["Pale Slate-Amber"])
    build_pool = palettes.get("ghoul_female_builds" if g_low == "female" else "ghoul_male_builds") or ["Tall Slender Poised Sculpted"]
    build = rng.choice(build_pool)
    attire_pool = palettes.get("ghoul_attire") or ["Tailored dark charcoal wool overcoat over black silk attire"]
    humanoid_outfit = attire_pool[0] if slot.get("is_royal_heir") else rng.choice(attire_pool)
    hair = rng.choice(["Sleek Raven-Black Cut", "Dark Espresso Waves", "Moonlit Obsidian Hair"])
    fur_coat = f"Ash-grey silver-tipped {canid_sp.replace('_', ' ')} fur"

    humanoid_kit_key = str(slot.get("combat_kit") or "ghoul_humanoid_duelist")
    active_kit_key = "ghoul_canid_beast" if initial_form == "ghoul:canid" else humanoid_kit_key
    is_heir = bool(slot.get("is_royal_heir"))

    appearance = {
        "gender": g_canon,
        "age_appearance": "poised ageless young adult",
        "skin_tone": skin,
        "skin_color": skin,
        "eyes": eyes,
        "hair": hair,
        "fur_coat": fur_coat,
        "coat_color": fur_coat if initial_form == "ghoul:canid" else "",
        "canid_species": canid_sp,
        "ghoul_form": initial_form,
        "ears": "Near-Human Pale Ears" if initial_form == "ghoul:humanoid" else f"Alert {canid_sp.replace('_', ' ').title()} Ears",
        "distinctive_features": "Pale porcelain-cool complexion, sharp silver-amber gaze, and subtle elongated canines",
        "build": build,
        "body_type": build,
        "physique": "Slim" if g_low == "female" else "Athletic",
        "outfit_summary": (
            f"Quadruped {canid_sp.replace('_', ' ')} canid form wearing only an iron-silver pack collar"
            if initial_form == "ghoul:canid"
            else humanoid_outfit
        ),
        "outfit_style": "" if initial_form == "ghoul:canid" else humanoid_outfit,
        "humanoid_outfit": humanoid_outfit,
    }
    if is_heir or slot.get("virgin"):
        appearance["predetermined_intercourse"] = "virgin"
        appearance["intercourse_experience"] = "virgin"

    tier = int(slot.get("agent_tier") or 3)
    return {
        "npc_id": npc_id,
        "slot_key": s_key,
        "name": full_name,
        "gender": g_canon,
        "race": initial_form,
        "initial_form": initial_form,
        "canid_species": canid_sp,
        "folklore_village": "ghoul",
        "village_id": "loc_hidden_ghoul_village",
        "home_zone_id": "zone_spirit_ghoul",
        "home_node": str(slot.get("home_node") or "sub_ghoul_inner_plaza"),
        "role": str(slot.get("role") or "Al-Ghul Ossuary Citizen"),
        "rank_title": str(slot.get("rank_title") or "Ossuary Courtier"),
        "agent_tier": tier,
        "tail_count": 0,
        "is_folklore_villager": True,
        "is_sovereign": False,
        "is_royal_heir": is_heir,
        "is_daytime_wanderer": bool(slot.get("is_daytime_wanderer")),
        "is_ghoul_city_wanderer": bool(slot.get("is_ghoul_city_wanderer")),
        "default_humanoid_outside_hunt": bool(slot.get("default_humanoid_outside_hunt", True)),
        "glamour_tell": str(slot.get("glamour_tell") or ""),
        "merchant_type": str(slot.get("merchant_type") or ""),
        "humanoid_kit_key": humanoid_kit_key,
        "combat_kit_key": active_kit_key,
        "innate_abilities": list(kits.get(active_kit_key) or []),
        "stats": _build_villager_stats(tier, is_mystic=("sovereign" in humanoid_kit_key)),
        "schedule": dict(slot.get("schedule") or {}),
        "personality_summary": str(slot.get("personality") or ""),
        "appearance": appearance,
        "initial_affinity": int(slot.get("initial_affinity") or (10 if is_heir else 5)),
        "secret_crush_on_pc": False,
        "predatory_fascination_on_pc": bool(slot.get("predatory_fascination_on_pc") and is_heir),
        "virgin": bool(slot.get("virgin") or is_heir),
        "single": True,
        "hydrated": False,
        "befriended": False,
    }


def _pick_non_sovereign_gender(rng: random.Random, scen_key: str, player_gender: str) -> str:
    if scenario_data.should_skew_female_npcs(scen_key, player_gender):
        return "female" if rng.random() < 0.80 else "male"
    return "female" if rng.random() < 0.50 else "male"


def generate_folklore_villager_roster(
    session_id: int,
    scen_key: str = "anomalous_incursions",
    player_gender: str = "",
) -> List[Dict[str, Any]]:
    """
    Deterministically builds the veiled folklore roster across all 3 enclaves
    (11 Kitsune + 11 Orang Bunian + 10 Al-Ghul = 32 villagers, or royal/heir twins for Non-binary PCs):
    - Zero database contact/lorebook side effects (pure deterministic list)
    """
    catalog = load_folklore_villages_catalog()
    pc_bucket = _normalize_pc_gender_bucket(player_gender)
    rng = random.Random(f"hikayat_folklore_v1:{session_id}:{scen_key}:{pc_bucket}")
    used_names: set[str] = set()
    roster: List[Dict[str, Any]] = []

    k_slots = list(catalog.get("kitsune_roster_slots") or [])
    b_slots = list(catalog.get("bunian_roster_slots") or [])
    g_slots = list(catalog.get("ghoul_roster_slots") or [])
    k_pools = (catalog.get("name_pools") or {}).get("kitsune") or {}
    b_pools = (catalog.get("name_pools") or {}).get("bunian") or {}
    g_pools = (catalog.get("name_pools") or {}).get("ghoul") or {}

    humanoid_keys = {
        "kitsune_sovereign",
        "kitsune_merchant",
        "kitsune_wanderer",
        "kitsune_onsen_host",
        "kitsune_mask_artisan",
    }

    if pc_bucket == "nonbinary" and k_slots:
        sov_slot = k_slots[0]
        roster.append(
            _build_kitsune_entry(
                rng, sov_slot, "female", "kitsune:humanoid", catalog, used_names,
                name_override=str(k_pools.get("sovereign_female") or "Lady Tamamo-no-Shirakawa"),
                slot_key_override="kitsune_sovereign_f",
            )
        )
        roster.append(
            _build_kitsune_entry(
                rng, sov_slot, "male", "kitsune:myobu_fox", catalog, used_names,
                name_override=str(k_pools.get("sovereign_male") or "Lord Hakumen-no-Shirakawa"),
                slot_key_override="kitsune_sovereign_m",
            )
        )
        for s in k_slots[1:]:
            sk = str(s.get("slot_key") or "")
            g = _pick_non_sovereign_gender(rng, scen_key, player_gender)
            form = str(s.get("forced_initial_form") or ("kitsune:humanoid" if sk in humanoid_keys else "kitsune:myobu_fox"))
            roster.append(_build_kitsune_entry(rng, s, g, form, catalog, used_names))
    else:
        opp_gender = "female" if pc_bucket == "male" else "male"
        for s in k_slots:
            sk = str(s.get("slot_key") or "")
            g = opp_gender if s.get("opposite_gender_to_pc") else _pick_non_sovereign_gender(rng, scen_key, player_gender)
            form = str(s.get("forced_initial_form") or ("kitsune:humanoid" if sk in humanoid_keys else "kitsune:myobu_fox"))
            roster.append(_build_kitsune_entry(rng, s, g, form, catalog, used_names))

    if pc_bucket == "nonbinary" and b_slots:
        royal_slot = b_slots[0]
        roster.append(
            _build_bunian_entry(
                rng, royal_slot, "female", catalog, used_names,
                name_override=str(b_pools.get("royal_female") or "Puteri Seri Cempaka"),
                slot_key_override="bunian_royal_puteri",
            )
        )
        roster.append(
            _build_bunian_entry(
                rng, royal_slot, "male", catalog, used_names,
                name_override=str(b_pools.get("royal_male") or "Putera Indera Purnama"),
                slot_key_override="bunian_royal_putera",
            )
        )
        for s in b_slots[1:]:
            g = _pick_non_sovereign_gender(rng, scen_key, player_gender)
            roster.append(_build_bunian_entry(rng, s, g, catalog, used_names))
    else:
        opp_gender = "female" if pc_bucket == "male" else "male"
        for s in b_slots:
            g = opp_gender if s.get("opposite_gender_to_pc") else _pick_non_sovereign_gender(rng, scen_key, player_gender)
            roster.append(_build_bunian_entry(rng, s, g, catalog, used_names))

    if pc_bucket == "nonbinary" and g_slots:
        heir_slot = g_slots[0]
        roster.append(
            _build_ghoul_entry(
                rng, heir_slot, "female", catalog, used_names,
                name_override=str(g_pools.get("heir_female") or "Nadia Haddad"),
                slot_key_override="ghoul_heir_f",
            )
        )
        roster.append(
            _build_ghoul_entry(
                rng, heir_slot, "male", catalog, used_names,
                name_override=str(g_pools.get("heir_male") or "Tariq Haddad"),
                slot_key_override="ghoul_heir_m",
            )
        )
        for s in g_slots[1:]:
            g = _pick_non_sovereign_gender(rng, scen_key, player_gender)
            roster.append(_build_ghoul_entry(rng, s, g, catalog, used_names))
    else:
        opp_gender = "female" if pc_bucket == "male" else "male"
        for s in g_slots:
            g = opp_gender if s.get("opposite_gender_to_pc") else _pick_non_sovereign_gender(rng, scen_key, player_gender)
            roster.append(_build_ghoul_entry(rng, s, g, catalog, used_names))

    return roster


def ensure_folklore_villager_roster(
    session_id: int,
    scen_key: str = "",
    player_gender: str = "",
    session: Optional[Dict[str, Any]] = None,
    persist_db: bool = True,
    read_only: bool = False,
    conn: Any = None,
) -> List[Dict[str, Any]]:
    """
    Ensures the session has its pregenerated folklore villager roster in `sessions.extra_json`
    WITHOUT inserting any Turn-0 rows into contacts or lorebook.
    When `persist_db=False` or `read_only=True`, computes/caches without DB writes;
    when `read_only=True`, performs zero DB reads as well.
    """
    if not session_id:
        return []
    if isinstance(session, dict):
        sess = session
    elif read_only:
        return []
    elif conn is not None:
        s_row = conn.execute(
            "SELECT id, scenario, host_user_id, extra_json FROM sessions WHERE id = ?",
            (int(session_id),),
        ).fetchone()
        if not s_row:
            return []
        try:
            ex_parsed = json.loads(s_row["extra_json"] or "{}") if s_row["extra_json"] else {}
        except Exception:
            ex_parsed = {}
        sess = {
            "id": s_row["id"],
            "scenario": s_row["scenario"],
            "host_user_id": s_row["host_user_id"],
            "extra": ex_parsed if isinstance(ex_parsed, dict) else {},
        }
    else:
        sess = db.get_session(session_id)
    if not isinstance(sess, dict):
        return []
    eff_scen = str(scen_key or sess.get("scenario") or "")
    if (
        not scenario_data.is_anomalous_incursions_scenario(eff_scen)
        and not scenario_data.is_anomalous_high_school_scenario(eff_scen)
        and "urban_anomalies" not in eff_scen.lower()
    ):
        return []

    sess_extra = sess.get("extra") if isinstance(sess.get("extra"), dict) else {}
    existing = sess.get("folklore_villager_roster") or sess_extra.get("folklore_villager_roster")
    existing_bucket = sess.get("folklore_roster_pc_bucket") or sess_extra.get("folklore_roster_pc_bucket")
    if isinstance(existing, list) and len(existing) >= 31 and any(e.get("folklore_village") == "ghoul" for e in existing if isinstance(e, dict)) and not player_gender and existing_bucket:
        return existing

    if not player_gender and not read_only:
        try:
            if conn is not None:
                ch_row = conn.execute(
                    "SELECT gender FROM characters WHERE active_session_id = ? ORDER BY id ASC LIMIT 1",
                    (int(session_id),),
                ).fetchone()
                if ch_row and ch_row["gender"]:
                    player_gender = str(ch_row["gender"])
                elif sess.get("host_user_id"):
                    hc_r = conn.execute(
                        "SELECT gender FROM characters WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                        (int(sess["host_user_id"]),),
                    ).fetchone()
                    player_gender = str((hc_r["gender"] if hc_r else "") or "")
            else:
                chars = db.get_session_characters(session_id) or []
                if chars and isinstance(chars[0], dict):
                    player_gender = str(chars[0].get("gender") or "")
                elif sess.get("host_user_id"):
                    hc = db.get_character(int(sess["host_user_id"])) or {}
                    player_gender = str(hc.get("gender") or "")
        except Exception:
            player_gender = ""

    pc_bucket = _normalize_pc_gender_bucket(player_gender)
    if isinstance(existing, list) and len(existing) >= 31 and any(e.get("folklore_village") == "ghoul" for e in existing if isinstance(e, dict)) and existing_bucket == pc_bucket:
        return existing

    fresh_roster = generate_folklore_villager_roster(session_id, scen_key=eff_scen, player_gender=player_gender)
    if isinstance(existing, list) and existing and (not existing_bucket or existing_bucket == pc_bucket):
        existing_by_id = {
            str(e.get("npc_id") or ""): e
            for e in existing
            if isinstance(e, dict) and e.get("npc_id")
        }
        roster: List[Dict[str, Any]] = [
            existing_by_id[str(entry["npc_id"])]
            if str(entry.get("npc_id") or "") in existing_by_id
            else entry
            for entry in fresh_roster
        ]
    else:
        roster = fresh_roster
    if isinstance(session, dict) and not read_only:
        session["folklore_villager_roster"] = roster
        session["folklore_roster_pc_bucket"] = pc_bucket
    if persist_db and not read_only:
        if conn is not None:
            ex_cur = dict(sess_extra)
            ex_cur["folklore_villager_roster"] = roster
            ex_cur["folklore_roster_pc_bucket"] = pc_bucket
            conn.execute(
                "UPDATE sessions SET extra_json = ? WHERE id = ?",
                (json.dumps(ex_cur, default=str), int(session_id)),
            )
        else:
            db.update_session(
                session_id,
                extra={
                    "folklore_villager_roster": roster,
                    "folklore_roster_pc_bucket": pc_bucket,
                },
            )
    return roster


def _match_villager_entry(roster: List[Dict[str, Any]], npc_id_or_name: str) -> Optional[Dict[str, Any]]:
    target = str(npc_id_or_name or "").strip().lower()
    if not target or not roster:
        return None
    for entry in roster:
        if (
            str(entry.get("npc_id") or "").lower() == target
            or str(entry.get("slot_key") or "").lower() == target
            or str(entry.get("name") or "").strip().lower() == target
        ):
            return entry
    twin_aliases = {
        "bunian_royal_heir": "bunian_royal_puteri",
        "folklore_bunian_royal_heir": "bunian_royal_puteri",
        "bunian_royal_heir_twin": "bunian_royal_putera",
        "folklore_bunian_royal_heir_twin": "bunian_royal_putera",
        "kitsune_sovereign": "kitsune_sovereign_f",
        "folklore_kitsune_sovereign": "kitsune_sovereign_f",
        "kitsune_sovereign_twin": "kitsune_sovereign_m",
        "folklore_kitsune_sovereign_twin": "kitsune_sovereign_m",
        "ghoul_heir": "ghoul_heir_f",
        "folklore_ghoul_heir": "ghoul_heir_f",
        "ghoul_heir_twin": "ghoul_heir_m",
        "folklore_ghoul_heir_twin": "ghoul_heir_m",
    }
    alias_slot = twin_aliases.get(target)
    if alias_slot:
        for entry in roster:
            if str(entry.get("slot_key") or "").lower() == alias_slot:
                return entry
    return None


def get_folklore_villager_spec(
    session_id: int,
    npc_id_or_name: str,
    session: Optional[Dict[str, Any]] = None,
    persist_db: bool = True,
    read_only: bool = False,
) -> Optional[Dict[str, Any]]:
    """Looks up a pregenerated villager spec by npc_id, slot_key, twin alias, or display name."""
    if not session_id or not npc_id_or_name:
        return None
    roster = ensure_folklore_villager_roster(
        session_id, session=session, persist_db=persist_db, read_only=read_only
    )
    return _match_villager_entry(roster, npc_id_or_name)


def get_scheduled_villagers_for_node(
    session_id: int,
    node_id: str,
    current_minute: int = 480,
    session: Optional[Dict[str, Any]] = None,
    persist_db: bool = False,
) -> List[Dict[str, Any]]:
    """
    Returns stage-ready villager dicts currently scheduled at `node_id` according to synchronized city time.
    Always attaches a complete `basic_info` dict and previews circadian Kitsune form shifts without mutating DB.
    """
    if not session_id or not node_id:
        return []
    roster = ensure_folklore_villager_roster(session_id, session=session, persist_db=persist_db)
    if not roster:
        return []
    safe_min = int(current_minute or 0) % 1440
    if 360 <= safe_min < 720:
        slot_name = "morning"
    elif 720 <= safe_min < 1080:
        slot_name = "afternoon"
    elif 1080 <= safe_min < 1320:
        slot_name = "evening"
    else:
        slot_name = "night"

    is_evening = 1080 <= safe_min < 1440
    is_daytime = 360 <= safe_min < 1080
    contacts_by_name: Dict[str, Dict[str, Any]] = {}
    try:
        for ct in (db.get_contacts(session_id) or []):
            if isinstance(ct, dict) and ct.get("name"):
                contacts_by_name[str(ct["name"]).strip().lower()] = ct
    except Exception:
        pass

    outer_wanderer_equiv = {
        "loc_es_lantern_tea_street": {"loc_es_lantern_tea_street", "sub_es_lantern_steps"},
        "sub_es_lantern_steps": {"loc_es_lantern_tea_street", "sub_es_lantern_steps"},
        "loc_es_bamboo_footbath_bridge": {"loc_es_bamboo_footbath_bridge", "sub_es_vermilion_bridge"},
        "sub_es_vermilion_bridge": {"loc_es_bamboo_footbath_bridge", "sub_es_vermilion_bridge"},
        "loc_forest_trails": {"loc_forest_trails", "sub_trail_gateway"},
        "sub_trail_gateway": {"loc_forest_trails", "sub_trail_gateway"},
        "loc_hosp_morgue": {"loc_hosp_morgue", "loc_general_hospital"},
        "loc_hosp_emergency_triage": {"loc_hosp_emergency_triage", "loc_general_hospital"},
        "sub_crypt_ossuary": {"sub_crypt_ossuary", "loc_weeping_crypt"},
        "sub_uc_salvage_stalls": {"sub_uc_salvage_stalls", "loc_uc_drifter_bazaar"},
        "sub_uc_tunnel_cantina": {"sub_uc_tunnel_cantina", "loc_uc_drifter_bazaar"},
    }
    present: List[Dict[str, Any]] = []
    veil_cache: Dict[str, Dict[str, Any]] = {}
    for entry in roster:
        sched = entry.get("schedule") or {}
        target_nid = str(sched.get(slot_name) or entry.get("home_node") or "")
        equiv_set = outer_wanderer_equiv.get(target_nid, {target_nid}) if entry.get("is_daytime_wanderer") else {target_nid}
        if node_id not in equiv_set:
            continue
        if node_id in ("loc_et_fox_torii_tunnel", "loc_bunian_threshold_glade", "sub_uc_black_font") and not entry.get("is_daytime_wanderer"):
            v_key_c = str(entry.get("folklore_village") or "")
            if v_key_c not in veil_cache:
                veil_cache[v_key_c] = get_village_veil_status(session_id, v_key_c, session=session)
            if not veil_cache[v_key_c].get("attuned"):
                continue

        view = dict(entry)
        app = dict(entry.get("appearance") or {})
        ct_row = contacts_by_name.get(str(entry.get("name") or "").strip().lower())
        score = int((ct_row or {}).get("relationship_score") or entry.get("initial_affinity") or 5)
        track = str((ct_row or {}).get("track") or "platonic")
        cur_race = str((ct_row or {}).get("race") or entry.get("race") or "")

        if entry.get("folklore_village") == "kitsune":
            init_form = str(entry.get("initial_form") or cur_race)
            last_hist = (entry.get("form_history") or [{}])[-1]
            if is_evening and cur_race == "kitsune:myobu_fox":
                cur_race = "kitsune:humanoid"
            elif is_daytime and init_form == "kitsune:myobu_fox" and cur_race == "kitsune:humanoid":
                if score < 45 and not entry.get("bond_humanoid_unlocked") and last_hist.get("reason") == "circadian_evening":
                    cur_race = "kitsune:myobu_fox"
            h_outfit = str(app.get("humanoid_outfit") or "Vermilion-and-ivory Inari shrine kimono")
            app["kitsune_form"] = cur_race
            app["coat_color"] = str(app.get("fur_coat") or "") if cur_race == "kitsune:myobu_fox" else ""
            app["outfit_style"] = "" if cur_race == "kitsune:myobu_fox" else h_outfit
            app["outfit_summary"] = (
                "Unclothed sacred spirit-fox coat wreathed in kitsunebi wisps"
                if cur_race == "kitsune:myobu_fox"
                else h_outfit
            )
        elif entry.get("folklore_village") == "ghoul":
            cur_race = resolve_ghoul_contextual_form(
                node_id,
                current_minute=safe_min,
                in_combat=False,
                default_humanoid_outside_hunt=bool(entry.get("default_humanoid_outside_hunt")),
                slot_key=str(entry.get("slot_key") or ""),
            )
            canid_sp = normalize_canid_species(entry.get("canid_species") or app.get("canid_species"), seed=str(entry.get("name") or ""))
            h_outfit = str(app.get("humanoid_outfit") or "Tailored dark charcoal wool coat over black silk attire")
            app["ghoul_form"] = cur_race
            app["canid_species"] = canid_sp
            app["coat_color"] = str(app.get("fur_coat") or "") if cur_race == "ghoul:canid" else ""
            app["outfit_style"] = "" if cur_race == "ghoul:canid" else h_outfit
            app["outfit_summary"] = (
                f"Quadruped {canid_sp.replace('_', ' ')} canid form wearing only an iron-silver pack collar"
                if cur_race == "ghoul:canid"
                else h_outfit
            )

        view["race"] = cur_race
        view["appearance"] = app
        view["relationship_score"] = score
        view["track"] = track
        is_bef = bool(entry.get("befriended") or score >= 30 or ((ct_row or {}).get("basic_info") or {}).get("contact_added"))
        base_bi = build_villager_basic_info_dict(view, is_befriended=is_bef)
        if isinstance(ct_row, dict) and isinstance(ct_row.get("basic_info"), dict):
            base_bi = {**base_bi, **ct_row["basic_info"], "race": cur_race}
        view["basic_info"] = base_bi
        present.append(view)
    return present


def ensure_spirit_crossroads_roster(
    session_id: int,
    scen_key: str = "",
    session: Optional[Dict[str, Any]] = None,
    persist_db: bool = True,
    read_only: bool = False,
) -> List[Dict[str, Any]]:
    """
    Ensures the session has its 3 neutral Crossroads/Outpost spirit NPCs in
    `sessions.extra_json['spirit_crossroads_roster']` (separate from the 13-villager roster).
    """
    if not session_id:
        return []
    if isinstance(session, dict):
        sess = session
    elif read_only:
        return []
    else:
        sess = db.get_session(session_id)
    if not isinstance(sess, dict):
        return []
    eff_scen = str(scen_key or sess.get("scenario") or "")
    if (
        not scenario_data.is_anomalous_incursions_scenario(eff_scen)
        and not scenario_data.is_anomalous_high_school_scenario(eff_scen)
        and "urban_anomalies" not in eff_scen.lower()
    ):
        return []
    catalog = load_folklore_villages_catalog()
    slots = list(catalog.get("crossroads_roster_slots") or [])
    sess_extra = sess.get("extra") if isinstance(sess.get("extra"), dict) else {}
    existing = sess.get("spirit_crossroads_roster") or sess_extra.get("spirit_crossroads_roster")
    if isinstance(existing, list) and len(existing) >= len(slots):
        return existing

    existing_by_id = {
        str(e.get("npc_id") or ""): e
        for e in (existing if isinstance(existing, list) else [])
        if isinstance(e, dict) and e.get("npc_id")
    }
    roster: List[Dict[str, Any]] = []
    for slot in slots:
        sk = str(slot.get("slot_key") or "crossroads_npc")
        npc_id_xr = f"folklore_{sk}"
        if npc_id_xr in existing_by_id:
            roster.append(existing_by_id[npc_id_xr])
            continue
        roster.append({
            "npc_id": npc_id_xr,
            "slot_key": sk,
            "name": str(slot.get("name") or sk.replace("_", " ").title()),
            "gender": str(slot.get("gender") or "female"),
            "race": str(slot.get("race") or "spirit_broker"),
            "role": str(slot.get("role") or "Spirit Confluence Resident"),
            "rank_title": str(slot.get("rank_title") or "Confluence Resident"),
            "agent_tier": int(slot.get("agent_tier") or 3),
            "merchant_type": str(slot.get("merchant_type") or ""),
            "home_node": str(slot.get("home_node") or "sub_crossroads_bazaar_walk"),
            "outfit": str(slot.get("outfit") or "Confluence lantern attire"),
            "schedule": dict(slot.get("schedule") or {}),
            "personality_summary": str(slot.get("personality") or ""),
            "is_crossroads_npc": True,
            "is_folklore_villager": False,
            "initial_affinity": 10,
            "hydrated": False,
            "befriended": False,
        })
    if isinstance(session, dict) and not read_only:
        session["spirit_crossroads_roster"] = roster
    if persist_db and not read_only:
        db.update_session(session_id, extra={"spirit_crossroads_roster": roster})
    return roster


def build_crossroads_basic_info_dict(spec: Dict[str, Any], is_befriended: bool = False) -> Dict[str, Any]:
    """Constructs the canonical `basic_info` payload for a neutral Crossroads/Wilds spirit NPC."""
    return {
        "role": spec.get("role", "Spirit Confluence Resident"),
        "rank_title": spec.get("rank_title", "Confluence Resident"),
        "occupation": spec.get("role", "Spirit Confluence Resident"),
        "gender": spec.get("gender", ""),
        "race": spec.get("race", "spirit_broker"),
        "age_group": "adult",
        "anomalous_npc_tag": "civilian",
        "social_role_type": "spirit_crossroads_resident",
        "is_folklore_villager": False,
        "is_crossroads_npc": True,
        "agent_tier": int(spec.get("agent_tier") or 3),
        "home_node": spec.get("home_node", ""),
        "merchant_type": spec.get("merchant_type", ""),
        "description": spec.get("personality_summary", ""),
        "met_in_person": True,
        "contact_added": is_befriended,
        "is_contact": is_befriended,
        "unlocked_via_friendship": is_befriended,
        "spirit_relay_unlocked": is_befriended,
    }


def get_scheduled_crossroads_npcs_for_node(
    session_id: int,
    node_id: str,
    current_minute: int = 480,
    session: Optional[Dict[str, Any]] = None,
    persist_db: bool = False,
) -> List[Dict[str, Any]]:
    """Returns neutral Dusk Confluence / Bleedwood Outpost NPCs scheduled at `node_id`."""
    if not session_id or not node_id:
        return []
    roster = ensure_spirit_crossroads_roster(session_id, session=session, persist_db=persist_db)
    if not roster:
        return []
    safe_min = int(current_minute or 0) % 1440
    if 360 <= safe_min < 720:
        slot_name = "morning"
    elif 720 <= safe_min < 1080:
        slot_name = "afternoon"
    elif 1080 <= safe_min < 1320:
        slot_name = "evening"
    else:
        slot_name = "night"

    contacts_by_name: Dict[str, Dict[str, Any]] = {}
    try:
        for ct in (db.get_contacts(session_id) or []):
            if isinstance(ct, dict) and ct.get("name"):
                contacts_by_name[str(ct["name"]).strip().lower()] = ct
    except Exception:
        pass

    present: List[Dict[str, Any]] = []
    for entry in roster:
        sched = entry.get("schedule") or {}
        if str(sched.get(slot_name) or entry.get("home_node") or "") != node_id:
            continue
        view = dict(entry)
        ct_row = contacts_by_name.get(str(entry.get("name") or "").strip().lower())
        score = int((ct_row or {}).get("relationship_score") or entry.get("initial_affinity") or 10)
        is_bef = bool(entry.get("befriended") or score >= 30 or ((ct_row or {}).get("basic_info") or {}).get("contact_added"))
        view["relationship_score"] = score
        view["track"] = str((ct_row or {}).get("track") or "platonic")
        base_bi = build_crossroads_basic_info_dict(view, is_befriended=is_bef)
        if isinstance(ct_row, dict) and isinstance(ct_row.get("basic_info"), dict):
            base_bi = {**base_bi, **ct_row["basic_info"]}
        view["basic_info"] = base_bi
        present.append(view)
    return present


from .folklore_roster_lifecycle import (  # noqa: E402
    befriend_crossroads_npc,
    befriend_folklore_villager,
    commit_staged_folklore_ops,
    hydrate_crossroads_cast_for_node,
    hydrate_folklore_villager_on_encounter,
    hydrate_village_cast_for_node,
    recruit_folklore_companion,
    resolve_glamour_wanderer_interaction,
    rollback_folklore_roster_state_after_turn,
    shift_kitsune_form,
    sync_kitsune_circadian_forms_for_node,
)

__all__ = [
    "FOLKLORE_RACES",
    "befriend_crossroads_npc",
    "befriend_folklore_villager",
    "build_crossroads_basic_info_dict",
    "build_villager_basic_info_dict",
    "commit_staged_folklore_ops",
    "ensure_folklore_villager_roster",
    "ensure_spirit_crossroads_roster",
    "generate_folklore_villager_roster",
    "get_folklore_villager_spec",
    "get_scheduled_crossroads_npcs_for_node",
    "get_scheduled_villagers_for_node",
    "has_spirit_relay_contact",
    "hydrate_crossroads_cast_for_node",
    "hydrate_folklore_villager_on_encounter",
    "hydrate_village_cast_for_node",
    "is_folklore_beast_race",
    "is_folklore_race",
    "is_ghoul_canid_race",
    "is_ghoul_race",
    "is_myobu_fox_race",
    "npc_is_folklore_villager",
    "recruit_folklore_companion",
    "resolve_glamour_wanderer_interaction",
    "rollback_folklore_roster_state_after_turn",
    "shift_ghoul_form",
    "shift_kitsune_form",
    "sync_ghoul_contextual_forms_for_node",
    "sync_kitsune_circadian_forms_for_node",
]
