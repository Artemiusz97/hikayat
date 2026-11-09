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

FOLKLORE_RACES: Tuple[str, str, str] = (
    "orang_bunian",
    "kitsune:humanoid",
    "kitsune:myobu_fox",
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


from mechanics.social.races import is_folklore_race, is_myobu_fox_race


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
        "is_daytime_wanderer": bool(spec.get("is_daytime_wanderer")),
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
        "contact_added": is_befriended,
        "is_contact": is_befriended,
        "unlocked_via_friendship": is_befriended,
        "spirit_relay_unlocked": is_befriended,
    }


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
        "physique": "Hourglass & Slender" if g_low == "female" else "Broad Shoulders & Lean",
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
        "physique": "Hourglass & Slender" if g_low == "female" else "Broad Shoulders & Lean",
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
    Deterministically builds the veiled folklore roster (6 Kitsune + 7 Orang Bunian):
    - Exact 50/50 initial Kitsune split (3 kitsune:humanoid + 3 kitsune:myobu_fox)
    - Opposite-gender Sovereign & Puteri/Putera for Male/Female PCs; Royal Twins for Non-binary PCs
    - Zero database contact/lorebook side effects (pure deterministic list)
    """
    catalog = load_folklore_villages_catalog()
    pc_bucket = _normalize_pc_gender_bucket(player_gender)
    rng = random.Random(f"hikayat_folklore_v1:{session_id}:{scen_key}:{pc_bucket}")
    used_names: set[str] = set()
    roster: List[Dict[str, Any]] = []

    k_slots = list(catalog.get("kitsune_roster_slots") or [])[:6]
    b_slots = list(catalog.get("bunian_roster_slots") or [])[:7]
    k_pools = (catalog.get("name_pools") or {}).get("kitsune") or {}
    b_pools = (catalog.get("name_pools") or {}).get("bunian") or {}

    if pc_bucket == "nonbinary" and len(k_slots) >= 6:
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
        slot_by_key = {s["slot_key"]: s for s in k_slots}
        for sk, form in (
            ("kitsune_merchant", "kitsune:humanoid"),
            ("kitsune_wanderer", "kitsune:humanoid"),
            ("kitsune_elder", "kitsune:myobu_fox"),
            ("kitsune_guardian", "kitsune:myobu_fox"),
        ):
            if sk in slot_by_key:
                g = _pick_non_sovereign_gender(rng, scen_key, player_gender)
                roster.append(_build_kitsune_entry(rng, slot_by_key[sk], g, form, catalog, used_names))
    else:
        opp_gender = "female" if pc_bucket == "male" else "male"
        humanoid_keys = {"kitsune_sovereign", "kitsune_merchant", "kitsune_wanderer"}
        for s in k_slots:
            sk = str(s.get("slot_key") or "")
            g = opp_gender if s.get("opposite_gender_to_pc") else _pick_non_sovereign_gender(rng, scen_key, player_gender)
            form = "kitsune:humanoid" if sk in humanoid_keys else "kitsune:myobu_fox"
            roster.append(_build_kitsune_entry(rng, s, g, form, catalog, used_names))

    if pc_bucket == "nonbinary" and len(b_slots) >= 6:
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
        for s in b_slots[1:6]:
            g = _pick_non_sovereign_gender(rng, scen_key, player_gender)
            roster.append(_build_bunian_entry(rng, s, g, catalog, used_names))
    else:
        opp_gender = "female" if pc_bucket == "male" else "male"
        for s in b_slots:
            g = opp_gender if s.get("opposite_gender_to_pc") else _pick_non_sovereign_gender(rng, scen_key, player_gender)
            roster.append(_build_bunian_entry(rng, s, g, catalog, used_names))

    return roster


def ensure_folklore_villager_roster(
    session_id: int,
    scen_key: str = "",
    player_gender: str = "",
    session: Optional[Dict[str, Any]] = None,
    persist_db: bool = True,
) -> List[Dict[str, Any]]:
    """
    Ensures the session has its pregenerated folklore villager roster in `sessions.extra_json`
    WITHOUT inserting any Turn-0 rows into contacts or lorebook.
    When `persist_db=False`, computes/caches in-memory on `session` with zero DB writes.
    """
    if not session_id:
        return []
    sess = session if isinstance(session, dict) else db.get_session(session_id)
    if not isinstance(sess, dict):
        return []
    eff_scen = str(scen_key or sess.get("scenario") or "")
    if (
        not scenario_data.is_anomalous_incursions_scenario(eff_scen)
        and not scenario_data.is_anomalous_high_school_scenario(eff_scen)
        and "urban_anomalies" not in eff_scen.lower()
    ):
        return []

    existing = sess.get("folklore_villager_roster")
    if isinstance(existing, list) and len(existing) >= 12 and not player_gender and sess.get("folklore_roster_pc_bucket"):
        return existing

    if not player_gender:
        try:
            chars = db.get_session_characters(session_id) or []
            if chars and isinstance(chars[0], dict):
                player_gender = str(chars[0].get("gender") or "")
            elif sess.get("host_user_id"):
                hc = db.get_character(int(sess["host_user_id"])) or {}
                player_gender = str(hc.get("gender") or "")
        except Exception:
            player_gender = ""

    pc_bucket = _normalize_pc_gender_bucket(player_gender)
    if isinstance(existing, list) and len(existing) >= 12 and sess.get("folklore_roster_pc_bucket") == pc_bucket:
        return existing

    roster = generate_folklore_villager_roster(session_id, scen_key=eff_scen, player_gender=player_gender)
    if isinstance(session, dict):
        session["folklore_villager_roster"] = roster
        session["folklore_roster_pc_bucket"] = pc_bucket
    if persist_db:
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
) -> Optional[Dict[str, Any]]:
    """Looks up a pregenerated villager spec by npc_id, slot_key, twin alias, or display name."""
    if not session_id or not npc_id_or_name:
        return None
    roster = ensure_folklore_villager_roster(session_id, session=session, persist_db=persist_db)
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
    }
    present: List[Dict[str, Any]] = []
    veil_cache: Dict[str, Dict[str, Any]] = {}
    for entry in roster:
        sched = entry.get("schedule") or {}
        target_nid = str(sched.get(slot_name) or entry.get("home_node") or "")
        equiv_set = outer_wanderer_equiv.get(target_nid, {target_nid}) if entry.get("is_daytime_wanderer") else {target_nid}
        if node_id not in equiv_set:
            continue
        if node_id in ("loc_et_fox_torii_tunnel", "loc_bunian_threshold_glade") and not entry.get("is_daytime_wanderer"):
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


from .folklore_roster_lifecycle import (  # noqa: E402
    befriend_folklore_villager,
    commit_staged_folklore_ops,
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
    "befriend_folklore_villager",
    "build_villager_basic_info_dict",
    "commit_staged_folklore_ops",
    "ensure_folklore_villager_roster",
    "generate_folklore_villager_roster",
    "get_folklore_villager_spec",
    "get_scheduled_villagers_for_node",
    "hydrate_folklore_villager_on_encounter",
    "hydrate_village_cast_for_node",
    "is_folklore_race",
    "is_myobu_fox_race",
    "npc_is_folklore_villager",
    "recruit_folklore_companion",
    "resolve_glamour_wanderer_interaction",
    "rollback_folklore_roster_state_after_turn",
    "shift_kitsune_form",
    "sync_kitsune_circadian_forms_for_node",
]
