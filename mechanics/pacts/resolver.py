from __future__ import annotations
"""
Deterministic Entity Contract Resolver: Discovery Channels, Rituals, Breaches & Agent Seeding (Layer 2/3).

Handles:
- Field Passives (`compute_pact_field_dc_modifier`, `compute_pact_travel_time_multiplier`) & Kin Authority (`evaluate_kin_authority`).
- 5 Discovery Channels (All 4 Faction Containment Vaults + Companion Sponsorship, Weekly Rotating Black-Market
  Crimson Auction & Syndicate Pens, Campus Seven Mysteries, `<15% HP` Sapient Boss Surrender, `<20% HP` Death's-Door Whispers).
- Remote Ritual Communion (`feed`, `upgrade`, `sever`), Medical/Shrine Scrubs, and Manifestation Exorcism Boss Fights.
- Post-Turn Cost Deduction, Lethal Overdraw -> `pact_blood_debt` 24h Promise, 2-Stage Breach -> Grudge Nemesis,
  VIP Tier III Exclusive Liberation, and School Civilian Witness Panic.
- 30–40% Deterministic Pre-Contracted Special Agent Seeding (`assign_special_agent_contracts`).
"""

import hashlib
import json
import logging
import random
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

import db
import scenario_data
from mechanics.combat.enemies import build_monster_stat_sheet

from .appraisal import (
    RESONANCE_XP_THRESHOLDS,
    apply_active_pact_modifiers,
    can_afford_stat_locks,
    compute_pact_cast_costs,
    compute_tier_locks_for_patron,
    evaluate_patron_appraisal,
    get_pact_slot_capacity,
)
from .catalog import (
    build_pact_spell_def,
    build_pact_spell_id,
    ensure_pact_spells_registered,
    get_bespoke_patrons,
    get_patron_by_id,
    is_entity_contracts_scenario,
    is_patron_allowed_in_scenario,
    synthesize_folklore_patron,
    synthesize_procedural_sapient_patron,
)
from .formatting import build_pact_turn_stage_direction

log = logging.getLogger(__name__)

# Curated Patron pools across all 4 Faction Containment Vaults
VAULT_FACTION_RULES: Dict[str, Dict[str, Any]] = {
    "public_agency": {
        "label": "Public Bureau Containment Vault",
        "node_tokens": ("loc_hq_containment_sector", "containment", "quarantine vault", "bureau vault", "subterranean containment"),
        "patron_ids": (
            "patron_ocular_phenomenon",
            "patron_guillotine_hound",
            "patron_iron_nail_curator",
            "patron_dead_air_fiend",
            "folk_patron_dullahan",
        ),
    },
    "monastic_order": {
        "label": "Five-Story Reliquary Pagoda",
        "node_tokens": ("loc_et_five_story_pagoda", "five_story_pagoda", "pagoda", "inner sanctum", "reliquary", "shrine vault"),
        "patron_ids": (
            "patron_white_incense_sovereign",
            "patron_severed_gale_tengu",
            "patron_weeping_bronze_bell",
            "folk_patron_huli_jing",
            "folk_patron_yuki_onna",
            "folk_patron_bunian_sorok",
            "folk_patron_leshy",
        ),
    },
    "private_agency_1": {
        "label": "Conglomerate Cryogenic Asset Vault",
        "node_tokens": ("cryogenic", "asset vault", "conglomerate vault", "proprietary vault", "containment lab", "research vault"),
        "patron_ids": (
            "patron_mammon_9",
            "patron_zero_kelvin_sarcophagus",
            "patron_dead_air_fiend",
            "folk_patron_smokeless_djinn",
        ),
    },
    "private_agency_2": {
        "label": "Lead-Lined Evidence & Armory Vault",
        "node_tokens": ("lead-lined", "evidence vault", "armory vault", "storefront vault", "surplus vault", "lockup"),
        "patron_ids": (
            "patron_recoil_graft",
            "patron_lye_fog_cleaner",
            "patron_guillotine_hound",
            "folk_patron_hantu_raya",
            "folk_patron_toyol",
        ),
    },
}

BLACK_MARKET_ROTATION_IDS: Tuple[str, ...] = (
    "patron_mammon_9",
    "patron_lye_fog_cleaner",
    "patron_13th_step_mirror_double",
    "patron_1540_clocktower_fiend",
    "patron_arterial_stitch_nurse",
    "patron_hollow_choir_worm",
    "patron_fever_dream_muse",
    "patron_silk_shackle_sovereign",
    "patron_midnight_onsen_siren",
    "folk_patron_pontianak",
    "folk_patron_huapi",
    "folk_patron_leanan_sidhe",
    "folk_patron_penanggalan",
)

CAMPUS_SEVEN_MYSTERIES_IDS: Tuple[str, ...] = (
    "patron_13th_step_mirror_double",
    "patron_1540_clocktower_fiend",
    "patron_arterial_stitch_nurse",
    "patron_hollow_choir_worm",
    "patron_weeping_bronze_bell",
    "patron_ocular_phenomenon",
    "folk_patron_kitsune",
)

DEATHS_DOOR_PATRON_IDS: Tuple[str, ...] = (
    "patron_hollow_choir_worm",
    "patron_arterial_stitch_nurse",
    "patron_ocular_phenomenon",
)


def _stable_seed_int(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:12], 16)


def _extract_location_corpus(session: Optional[Dict[str, Any]]) -> str:
    if not isinstance(session, dict):
        return ""
    parts = [
        str(session.get("current_node_id") or ""),
        str(session.get("current_location") or ""),
        str(session.get("location") or ""),
        str(session.get("focal_point") or ""),
    ]
    return " ".join(parts).strip().lower()


# ---------------------------------------------------------------------------
# 1. Field Passives, Travel Compression & Kin Authority
# ---------------------------------------------------------------------------

def compute_pact_field_dc_modifier(
    pacts: Optional[Iterable[Dict[str, Any]]],
    stat: str,
    *,
    action_category: str = "",
    label_text: str = "",
    scenario_or_key: Any = None,
) -> int:
    """
    Pure read-only calculation of cumulative non-combat skill-check DC reductions
    from active, non-breached Entity Contracts (`clamped -3..0`).
    """
    if not pacts or not stat:
        return 0
    s_up = str(stat).strip().upper()
    if s_up not in ("STR", "PER", "END", "CHA", "INT", "AGI", "LUK"):
        return 0

    total_mod = 0
    for row in pacts:
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "active") != "active":
            continue
        if int(row.get("breach_stage") or 0) >= 1:
            continue
        patron = get_patron_by_id(str(row.get("patron_id") or ""), scenario_or_key=scenario_or_key)
        if not patron:
            continue
        f_util = patron.get("field_utility") or {}
        dc_mods = f_util.get("dc_modifiers") or {}
        if s_up in dc_mods:
            try:
                total_mod += int(dc_mods[s_up])
            except (TypeError, ValueError):
                pass
    return max(-3, min(0, total_mod))


def compute_pact_travel_time_multiplier(
    pacts: Optional[Iterable[Dict[str, Any]]],
    *,
    current_day: int = 1,
    scenario_or_key: Any = None,
) -> Tuple[float, Optional[str]]:
    """
    Returns `(travel_time_multiplier, zero_minute_contract_key)`.
    - Liminal/spatial Patrons compress transit time (e.g. `0.75` = `-25%` travel minutes)
      and grant 1/day `0-minute` threshold step (`zero_minute_step_daily`).
    """
    if not pacts:
        return 1.0, None
    best_mult = 1.0
    zero_min_ckey: Optional[str] = None
    for row in pacts:
        if not isinstance(row, dict) or str(row.get("status") or "active") != "active":
            continue
        if int(row.get("breach_stage") or 0) >= 1:
            continue
        patron = get_patron_by_id(str(row.get("patron_id") or ""), scenario_or_key=scenario_or_key)
        if not patron:
            continue
        f_util = patron.get("field_utility") or {}
        t_mult = float(f_util.get("travel_time_mult") or 1.0)
        if 0.0 < t_mult < best_mult:
            best_mult = t_mult
        if f_util.get("zero_minute_step_daily") and zero_min_ckey is None:
            meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            if int(meta.get("zero_minute_used_day") or 0) != int(current_day):
                zero_min_ckey = str(row.get("contract_key") or "")
    return best_mult, zero_min_ckey


def evaluate_kin_authority(
    pacts: Optional[Iterable[Dict[str, Any]]],
    target_entity: Any,
    *,
    scenario_or_key: Any = None,
) -> Optional[Dict[str, Any]]:
    """
    Checks if the player holds an active Pact sharing `codex_id` (or folklore lineage)
    with `target_entity`. Grants automatic taboo reveal + `+40%` (`-8 DC`) pacify authority!
    """
    if not pacts or not isinstance(target_entity, dict):
        return None
    bp = target_entity.get("anomaly_blueprint") if isinstance(target_entity.get("anomaly_blueprint"), dict) else {}
    target_cid = str(target_entity.get("codex_id") or bp.get("codex_id") or "").strip()
    if not target_cid:
        return None

    for row in pacts:
        if not isinstance(row, dict) or str(row.get("status") or "active") != "active":
            continue
        if int(row.get("breach_stage") or 0) >= 1:
            continue
        row_cid = str(row.get("codex_id") or "").strip()
        if not row_cid:
            p_def = get_patron_by_id(str(row.get("patron_id") or ""), scenario_or_key=scenario_or_key)
            row_cid = str((p_def or {}).get("codex_id") or "").strip()
        if row_cid and row_cid == target_cid:
            return {
                "matched": True,
                "contract_key": str(row.get("contract_key") or ""),
                "patron_id": str(row.get("patron_id") or ""),
                "entity_name": str(row.get("entity_name") or row_cid),
                "patron_name": str(row.get("entity_name") or row_cid),
                "codex_id": target_cid,
                "pacify_dc_bonus": -8,
                "pacify_pct_bonus": 40,
                "auto_reveal_taboo": True,
            }
    return None


# ---------------------------------------------------------------------------
# 2. Companion Sponsorship, Discovery Channels & Remote Communion
# ---------------------------------------------------------------------------

def has_companion_vault_sponsorship(
    session: Optional[Dict[str, Any]],
    user_id: int,
    target_faction_key: str,
) -> Tuple[bool, str]:
    """
    Returns `(True, sponsor_name)` if a Special Agent from `target_faction_key` is present
    or recruited with Friendly+ affinity (`>= 50`).
    """
    if not isinstance(session, dict) or not session.get("id"):
        return False, ""
    sid = int(session["id"])
    t_fac = str(target_faction_key or "").strip().lower()
    if not t_fac:
        return False, ""

    candidates: List[str] = []
    for n in (session.get("current_npcs") or []):
        if isinstance(n, dict):
            n_fac = str(n.get("faction_id") or "").strip().lower()
            n_name = str(n.get("name") or "").strip()
            if n_name and (n_fac == t_fac or n.get("is_companion") or n.get("in_party")):
                candidates.append(n_name)
        elif isinstance(n, str) and n.strip():
            candidates.append(n.strip())

    try:
        contacts = db.get_contacts(sid) or []
    except Exception:
        contacts = []

    for c in contacts:
        if not isinstance(c, dict):
            continue
        c_name = str(c.get("name") or "").strip()
        if not c_name:
            continue
        raw_score = c.get("relationship_score")
        if raw_score is None:
            raw_score = c.get("affinity") if c.get("affinity") is not None else (c.get("score") or 0)
        score = int(raw_score or 0)
        b_info = c.get("basic_info") if isinstance(c.get("basic_info"), dict) else {}
        in_party = bool(b_info.get("in_party") or b_info.get("is_companion") or c_name in candidates)
        if score < 50 and not in_party:
            continue
        c_fac = str(b_info.get("faction_id") or c.get("faction_id") or "").strip().lower()
        if not c_fac:
            try:
                from mechanics.social.agent_roster import find_special_agent_by_name
                ag = find_special_agent_by_name(sid, c_name, scen_key=str(session.get("scenario") or ""))
                if ag:
                    c_fac = str(ag.get("faction_id") or "").strip().lower()
            except Exception:
                pass
        if c_fac == t_fac and score >= 50:
            return True, c_name
    return False, ""


def can_perform_remote_pact_ritual(
    session: Optional[Dict[str, Any]],
    char: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Once signed, feeding offerings, deepening tiers, and petitioning release work remotely
    from home/dorm/apartment, any shrine/temple/pagoda, or agency sanctuary outside active combat.
    """
    if not isinstance(session, dict):
        return False
    enemies = [e for e in (session.get("nearby_enemies") or []) if isinstance(e, dict) and int(e.get("hp", 0) or 0) > 0]
    if enemies:
        return False
    loc_text = _extract_location_corpus(session)
    if not loc_text:
        return True
    safe_tokens = (
        "home", "bedroom", "dorm", "apartment", "residence", "house", "quarters", "safehouse",
        "shrine", "temple", "pagoda", "sanctuary", "chapel", "altar", "meditation", "hq",
        "headquarters", "lounge", "infirmary", "clinic", "medical", "vault", "clubroom", "rest",
    )
    return any(tok in loc_text for tok in safe_tokens)


def can_perform_peaceful_medical_or_shrine_scrub(
    session: Optional[Dict[str, Any]],
    contract_row: Dict[str, Any],
) -> Tuple[bool, int, str]:
    """
    Determines whether a contract can be peacefully scrubbed (regulated Tier I–II with no active breach)
    vs. requiring a **Manifestation Exorcism Boss Fight** (Tier III Exclusive, Cult/Black-Market unregulated, or breached).
    Returns `(is_peaceful_scrub, credit_fee, method_label)`.
    """
    tier = int(contract_row.get("tier") or 1)
    breach = int(contract_row.get("breach_stage") or 0)
    meta = contract_row.get("metadata") if isinstance(contract_row.get("metadata"), dict) else {}
    regulated = bool(meta.get("regulated", True))
    source_pool = str(contract_row.get("source_pool") or "bespoke")

    if tier >= 3 or not regulated or breach >= 1:
        return False, 0, "Manifestation Exorcism Duel Required"

    loc_text = _extract_location_corpus(session)
    at_medical_or_shrine = any(
        k in loc_text
        for k in ("medical", "infirmary", "hospital", "clinic", "shrine", "temple", "pagoda", "sanctuary", "containment")
    )
    fee = (80 if at_medical_or_shrine else 140) * max(1, tier)
    method = "Clinical / Shrine Cleansing Rite" if at_medical_or_shrine else "Remote Sanctuary Cleansing Rite"
    return True, fee, method


def _annotate_patron_for_player(
    session_id: int,
    user_id: int,
    char: Dict[str, Any],
    patron: Dict[str, Any],
    active_pacts: List[Dict[str, Any]],
    *,
    channel: str,
    channel_label: str,
    is_deaths_door: bool = False,
    surrender_enemy_name: str = "",
) -> Dict[str, Any]:
    pid = str(patron["patron_id"])
    appraisal = evaluate_patron_appraisal(char, patron, is_deaths_door=is_deaths_door)
    stat_locks_t1, hp_lock_t1 = compute_tier_locks_for_patron(patron, 1, appraisal["state"])
    ok_stats, stat_err = can_afford_stat_locks(char, stat_locks_t1, active_pacts)
    slot_cap = get_pact_slot_capacity(char)
    already_signed = any(str(p.get("patron_id")) == pid for p in active_pacts)
    spurned = db.is_patron_spurned_for_holder(session_id, user_id, pid) if session_id else False
    ex_holder = db.get_exclusive_tier3_holder(session_id, pid, exclude_holder_id=str(user_id)) if session_id else None

    blocked_reason = ""
    if already_signed:
        blocked_reason = "Already contracted."
    elif spurned:
        blocked_reason = "Spurned (permanent breach)."
    elif len(active_pacts) >= slot_cap:
        blocked_reason = f"Pact Slots full ({len(active_pacts)}/{slot_cap})."
    elif not ok_stats:
        blocked_reason = stat_err

    spell_t1 = build_pact_spell_def(patron, 1)
    return {
        "patron_id": pid,
        "codex_id": str(patron.get("codex_id") or ""),
        "source_pool": str(patron.get("source_pool") or "bespoke"),
        "regulated": bool(patron.get("regulated", True)),
        "name": str(patron.get("display_name") or patron.get("name") or pid),
        "canonical_name": str(patron.get("canonical_name") or patron.get("name") or pid),
        "title": str(patron.get("display_title") or patron.get("title") or ""),
        "summary": str(patron.get("summary") or spell_t1.get("description") or ""),
        "element": str(patron.get("element") or "aether"),
        "synergy_stat": str(patron.get("synergy_stat") or "INT"),
        "channel": channel,
        "channel_label": channel_label,
        "is_deaths_door_offer": is_deaths_door,
        "surrender_enemy_name": surrender_enemy_name,
        "appraisal": appraisal,
        "tier1_stat_locks": stat_locks_t1,
        "tier1_max_hp_lock_pct": hp_lock_t1,
        "combat_skill": spell_t1,
        "field_utility": dict(patron.get("field_utility") or {}),
        "taboo_desc": str((patron.get("costs") or {}).get("taboo_desc") or ""),
        "tithe": (patron.get("costs") or {}).get("tithe"),
        "has_bound_gear": bool(patron.get("bound_gear")),
        "bound_gear_slot": str((patron.get("bound_gear") or {}).get("slot") or ""),
        "exclusive_tier3_holder": (
            str((ex_holder.get("metadata") or {}).get("holder_name") or ex_holder.get("holder_id"))
            if ex_holder else ""
        ),
        "is_spurned": spurned,
        "already_signed": already_signed,
        "can_sign": not bool(blocked_reason),
        "blocked_reason": blocked_reason,
    }


def get_available_patrons_for_context(
    session: Optional[Dict[str, Any]],
    char: Optional[Dict[str, Any]],
    user_id: int,
    *,
    lang: str = "en",
) -> Dict[str, Any]:
    """
    Evaluates all 5 Discovery Channels for `(session, char, user_id)` and returns
    localized, appraised Patron offers ready for UI inspection or signing.
    """
    if not isinstance(session, dict) or not isinstance(char, dict):
        return {"channels_active": [], "patrons": [], "remote_communion_available": False}
    scen_key = str(session.get("scenario") or "")
    if not is_entity_contracts_scenario(scen_key):
        return {"channels_active": [], "patrons": [], "remote_communion_available": False}

    sid = int(session.get("id") or 0)
    cur_day = max(1, int(session.get("current_day") or 1))
    loc_text = _extract_location_corpus(session)
    contained_records = list(session.get("contained_anomalies_log") or [])
    active_pacts = db.get_player_active_pacts(sid, user_id) if sid else []

    seen_pids: set[str] = set()
    offers: List[Dict[str, Any]] = []
    channels_active: List[Dict[str, Any]] = []

    def _add_offer(p_obj: Optional[Dict[str, Any]], ch_key: str, ch_lbl: str, *, dd: bool = False, surr_name: str = "") -> None:
        if not p_obj or not is_patron_allowed_in_scenario(p_obj, scen_key):
            return
        pid = str(p_obj.get("patron_id") or "")
        if not pid or pid in seen_pids:
            return
        seen_pids.add(pid)
        offers.append(
            _annotate_patron_for_player(
                sid,
                user_id,
                char,
                p_obj,
                active_pacts,
                channel=ch_key,
                channel_label=ch_lbl,
                is_deaths_door=dd,
                surrender_enemy_name=surr_name,
            )
        )

    # Channel 1: All 4 Faction Containment Vaults (+ Captured Sapient Anomalies)
    player_fac_key = ""
    player_fac_rank = 1
    if sid:
        try:
            from mechanics.social.factions import get_anomalous_faction_state
            f_st = get_anomalous_faction_state(sid, user_id=user_id)
            player_fac_key = str(f_st.get("faction_archetype_key") or "").strip().lower()
            player_fac_rank = int(f_st.get("rank_tier") or f_st.get("rank") or 1)
        except Exception:
            player_fac_key = str(char.get("joined_faction_id") or "").strip().lower()

    for v_key, v_cfg in VAULT_FACTION_RULES.items():
        at_this_vault = any(tok in loc_text for tok in v_cfg["node_tokens"])
        sponsored, sponsor_name = has_companion_vault_sponsorship(session, user_id, v_key)
        authorized = (player_fac_key == v_key) or (player_fac_rank >= 3 and at_this_vault) or sponsored
        if at_this_vault and authorized:
            lbl = f"{v_cfg['label']}" + (f" (Sponsored by {sponsor_name})" if sponsored and player_fac_key != v_key else "")
            channels_active.append({"channel": f"vault:{v_key}", "label": lbl})
            for pid in v_cfg["patron_ids"]:
                p_def = get_patron_by_id(pid, scenario_or_key=scen_key, lang=lang, contained_records=contained_records)
                _add_offer(p_def, f"vault:{v_key}", lbl)
            for rec in contained_records:
                synth = synthesize_procedural_sapient_patron(rec, scenario_or_key=scen_key, lang=lang)
                _add_offer(synth, f"vault:{v_key}", f"{lbl} — Contained Specimen")

    # Also allow player's own joined faction vault archive if they have captured sapient specimens and are in HQ
    if contained_records and any(k in loc_text for k in ("hq", "headquarters", "vault", "pagoda", "sanctum", "agency")):
        for rec in contained_records:
            synth = synthesize_procedural_sapient_patron(rec, scenario_or_key=scen_key, lang=lang)
            _add_offer(synth, "vault:captured", "Contained Sapient Specimen Archive")

    # Channel 2: Weekly Rotating Black-Market Crimson Auction & Syndicate Pens
    at_black_market = any(
        tok in loc_text
        for tok in (
            "sub_auction_amphitheater",
            "sub_synd_pens",
            "crimson auction",
            "syndicate pen",
            "black market",
            "black-market",
            "underground auction",
            "smuggler",
            "night market",
        )
    )
    if at_black_market:
        week_idx = cur_day // 7
        rng_bm = random.Random(_stable_seed_int(f"bm_rotation:{sid}:{week_idx}"))
        allowed_bm_pool = []
        for pid in BLACK_MARKET_ROTATION_IDS:
            p_def = get_patron_by_id(pid, scenario_or_key=scen_key, lang=lang)
            if p_def and is_patron_allowed_in_scenario(p_def, scen_key):
                allowed_bm_pool.append(p_def)
        sample_cnt = min(len(allowed_bm_pool), 5)
        weekly_picks = rng_bm.sample(allowed_bm_pool, sample_cnt) if sample_cnt > 0 else []
        bm_lbl = f"Crimson Auction Lot (Week {week_idx + 1})"
        channels_active.append({"channel": "black_market", "label": bm_lbl})
        for p_def in weekly_picks:
            _add_offer(p_def, "black_market", bm_lbl)

    # Channel 3: Campus Seven Mysteries (Anomalous High School + variants)
    if scenario_data.is_anomalous_high_school_scenario(scen_key):
        at_school_mystery = any(
            tok in loc_text
            for tok in (
                "school", "academy", "campus", "rooftop", "music", "infirmary", "nurse",
                "library", "stair", "mirror", "restroom", "occult", "clubroom", "basement", "auditorium",
            )
        )
        if at_school_mystery:
            sm_lbl = "Campus Seven Mysteries"
            channels_active.append({"channel": "seven_mysteries", "label": sm_lbl})
            day_rot = _stable_seed_int(f"campus_mystery:{sid}:{cur_day // 3}") % max(1, len(CAMPUS_SEVEN_MYSTERIES_IDS))
            rotated_ids = list(CAMPUS_SEVEN_MYSTERIES_IDS[day_rot:]) + list(CAMPUS_SEVEN_MYSTERIES_IDS[:day_rot])
            for pid in rotated_ids[:4]:
                p_def = get_patron_by_id(pid, scenario_or_key=scen_key, lang=lang)
                _add_offer(p_def, "seven_mysteries", sm_lbl)

    # Channel 4: Mid-Delve <= 15% HP Sapient Boss Surrender
    for enem in (session.get("nearby_enemies") or []):
        if not isinstance(enem, dict):
            continue
        if enem.get("is_pact_exorcism_boss") or enem.get("sparring") or enem.get("is_human_npc"):
            continue
        e_hp = int(enem.get("hp") or 0)
        e_max = max(1, int(enem.get("max_hp") or 100))
        if e_hp <= 0 or e_hp > max(1, int(e_max * 0.15)):
            continue
        bp = enem.get("anomaly_blueprint") if isinstance(enem.get("anomaly_blueprint"), dict) else {}
        sap = str(enem.get("sapience") or bp.get("sapience") or "sapient").strip().lower()
        if sap not in ("sapient",) and not (enem.get("codex_id") or bp.get("codex_id")):
            continue
        cid = str(enem.get("codex_id") or bp.get("codex_id") or "").strip()
        if cid:
            surr_patron = synthesize_folklore_patron(cid, scenario_or_key=scen_key, lang=lang)
        else:
            rec_src = {
                "anomaly_id": enem.get("incursion_id") or enem.get("name"),
                "name": enem.get("name"),
                "primary_element": enem.get("primary_element") or bp.get("primary_element") or "aether",
                "archetype": enem.get("archetype") or "catalyst",
                "sapience": "sapient",
                "form": enem.get("form") or bp.get("form") or "default",
                "threat_tier": enem.get("tier_rank") or 3,
                "taboo": enem.get("taboo") or bp.get("taboo") or {},
            }
            surr_patron = synthesize_procedural_sapient_patron(rec_src, scenario_or_key=scen_key, lang=lang)
        if surr_patron:
            s_lbl = f"Boss Surrender Plea — {enem.get('name', 'Weakened Entity')}"
            channels_active.append({"channel": "boss_surrender", "label": s_lbl})
            _add_offer(surr_patron, "boss_surrender", s_lbl, surr_name=str(enem.get("name") or ""))

    # Channel 5: <= 20% HP Death's-Door Emergency Whispers
    c_hp = int(char.get("hp") or 0)
    c_max = max(1, int(char.get("max_hp") or 100))
    if 0 < c_hp <= max(1, int(c_max * 0.20)):
        dd_lbl = "Death's-Door Emergency Whisper"
        channels_active.append({"channel": "deaths_door", "label": dd_lbl})
        for pid in DEATHS_DOOR_PATRON_IDS:
            p_def = get_patron_by_id(pid, scenario_or_key=scen_key, lang=lang)
            _add_offer(p_def, "deaths_door", dd_lbl, dd=True)

    return {
        "channels_active": channels_active,
        "patrons": offers,
        "remote_communion_available": can_perform_remote_pact_ritual(session, char),
    }


# ---------------------------------------------------------------------------
# 3. Omnichannel Contracts Overview & Ritual Execution
# ---------------------------------------------------------------------------

def build_contracts_overview_payload(
    session_id: int,
    user_id: int,
    *,
    lang: str = "en",
) -> Dict[str, Any]:
    """
    N+1-free headless contract state payload shared by `GET /api/contracts/{session_id}`
    and Discord `EntityContractsView`.
    """
    ensure_pact_spells_registered()
    sess = db.get_session(int(session_id)) if session_id else None
    if not sess:
        return {"enabled": False, "active_pacts": [], "available_patrons": [], "compendium": []}
    scen_key = str(sess.get("scenario") or "")
    if not is_entity_contracts_scenario(scen_key):
        return {"enabled": False, "scenario": scen_key, "active_pacts": [], "available_patrons": [], "compendium": []}

    char = db.get_character(int(user_id), session_id=int(session_id)) or {}
    contained_records = list(sess.get("contained_anomalies_log") or [])
    active_rows = db.get_player_active_pacts(int(session_id), int(user_id))
    grudges = db.get_session_active_grudges(int(session_id), holder_id=str(user_id))
    compendium_rows = db.get_user_patron_compendium(int(user_id))
    remote_ok = can_perform_remote_pact_ritual(sess, char)

    enriched_active: List[Dict[str, Any]] = []
    for row in active_rows:
        pid = str(row.get("patron_id") or "")
        patron = get_patron_by_id(pid, scenario_or_key=scen_key, lang=lang, contained_records=contained_records)
        tier = int(row.get("tier") or 1)
        if not patron:
            continue
        sp_def = build_pact_spell_def(patron, tier)
        cast_cost = compute_pact_cast_costs(char, row, patron)
        peaceful_scrub, scrub_fee, scrub_method = can_perform_peaceful_medical_or_shrine_scrub(sess, row)
        next_tier = tier + 1 if tier < 3 else None
        req_xp = RESONANCE_XP_THRESHOLDS.get(next_tier, 99) if next_tier else 0
        app_state = str(row.get("appraisal_state") or "neutral")
        ex_holder = (
            db.get_exclusive_tier3_holder(int(session_id), pid, exclude_holder_id=str(user_id))
            if next_tier == 3 else None
        )
        can_upgrade = bool(
            next_tier
            and int(row.get("breach_stage") or 0) == 0
            and not (app_state == "disdained" and next_tier >= 3)
            and (app_state == "favored" or int(row.get("resonance_xp") or 0) >= req_xp)
            and not ex_holder
            and remote_ok
        )
        enriched_active.append({
            "contract_key": row["contract_key"],
            "patron_id": pid,
            "codex_id": str(row.get("codex_id") or ""),
            "source_pool": str(row.get("source_pool") or "bespoke"),
            "name": str(patron.get("display_name") or row.get("entity_name") or pid),
            "title": str(patron.get("display_title") or patron.get("title") or ""),
            "element": str(row.get("element") or patron.get("element") or "aether"),
            "synergy_stat": str(row.get("synergy_stat") or patron.get("synergy_stat") or "INT"),
            "tier": tier,
            "resonance_xp": int(row.get("resonance_xp") or 0),
            "next_tier_xp_required": req_xp,
            "appraisal_state": app_state,
            "breach_stage": int(row.get("breach_stage") or 0),
            "unpaid_blood_debt": int(row.get("unpaid_blood_debt") or 0),
            "stat_locks": dict(row.get("stat_locks") or {}),
            "max_hp_lock_pct": float((row.get("metadata") or {}).get("max_hp_lock_pct") or 0.0),
            "bound_gear_slot": str(row.get("bound_gear_slot") or ""),
            "taboo_desc": str((patron.get("costs") or {}).get("taboo_desc") or ""),
            "tithe_schedule": dict(row.get("tithe_schedule") or {}),
            "combat_skill": sp_def,
            "cast_costs": cast_cost,
            "field_utility": dict(patron.get("field_utility") or {}),
            "visual_tell": str((patron.get("visuals") or {}).get("rest_tell_prose") or ""),
            "can_upgrade": can_upgrade,
            "peaceful_scrub_available": peaceful_scrub,
            "scrub_credit_fee": scrub_fee,
            "sever_method_label": scrub_method,
        })

    avail_ctx = get_available_patrons_for_context(sess, char, int(user_id), lang=lang)
    enriched_compendium: List[Dict[str, Any]] = []
    for c_row in compendium_rows:
        c_pid = str(c_row.get("patron_id") or "")
        p_def = get_patron_by_id(c_pid, scenario_or_key=scen_key, lang=lang, contained_records=contained_records)
        if p_def and not is_patron_allowed_in_scenario(p_def, scen_key) and not c_row.get("is_currently_contracted"):
            continue
        enriched_compendium.append({
            **c_row,
            "display_name": str((p_def or {}).get("display_name") or c_row.get("entity_name") or c_pid),
            "display_title": str((p_def or {}).get("display_title") or (p_def or {}).get("title") or ""),
            "element": str((p_def or {}).get("element") or "aether"),
        })

    return {
        "enabled": True,
        "scenario": scen_key,
        "slot_used": len(enriched_active),
        "slot_capacity": get_pact_slot_capacity(char),
        "remote_communion_available": avail_ctx["remote_communion_available"],
        "channels_active": avail_ctx["channels_active"],
        "active_pacts": enriched_active,
        "available_patrons": avail_ctx["patrons"],
        "active_grudges": grudges,
        "compendium": enriched_compendium,
    }


def _fulfill_patron_blood_debt_commitments(session_id: int, patron_id: str, entity_name: str) -> int:
    """Marks active `pact_blood_debt` or `pact_tithe` promises for `patron_id` as `fulfilled`."""
    if not session_id:
        return 0
    now = time.time()
    fulfilled = 0
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, metadata_json, target_entity FROM commitments_ledger WHERE session_id = ? AND status = 'active'",
            (int(session_id),),
        ).fetchall()
        for r in rows:
            try:
                meta = json.loads(r["metadata_json"] or "{}")
            except Exception:
                meta = {}
            sub = str(meta.get("subtype") or "")
            if sub not in ("pact_blood_debt", "pact_tithe"):
                continue
            if str(meta.get("patron_id") or "") == str(patron_id) or str(r["target_entity"] or "").lower() == entity_name.lower().replace(" ", "_"):
                conn.execute(
                    "UPDATE commitments_ledger SET status = 'fulfilled', updated_at = ? WHERE id = ?",
                    (now, r["id"]),
                )
                fulfilled += 1
    return fulfilled


def spawn_manifestation_exorcism_boss(
    session_id: int,
    session: Dict[str, Any],
    char: Dict[str, Any],
    contract_row: Dict[str, Any],
    patron: Dict[str, Any],
) -> Dict[str, Any]:
    """Spawns `Manifested <Patron>` into `session['nearby_enemies']` for Tier III / Unregulated / Breached severance."""
    lvl = max(2, int(char.get("level") or 1) + int(contract_row.get("tier") or 1))
    tier_rank = max(3, min(5, int(contract_row.get("tier") or 1) + 2))
    max_hp = 95 + lvl * 22 + tier_rank * 20
    stats = build_monster_stat_sheet(lvl, "Caster")
    elem = str(patron.get("element") or "aether")
    entity_name = str(patron.get("display_name") or contract_row.get("entity_name") or patron["patron_id"])
    boss_dict: Dict[str, Any] = {
        "name": f"Manifested {entity_name}",
        "archetype": "Patron Manifestation",
        "level": lvl,
        "tier_rank": tier_rank,
        "hp": max_hp,
        "max_hp": max_hp,
        "mp": 80,
        "max_mp": 80,
        "stability": 100,
        "max_stability": 100,
        "primary_element": elem,
        "sapience": "sapient",
        "physicality": "corporeal",
        "stats": stats,
        "status_effects": [],
        "weaknesses": [],
        "resistances": [elem],
        "immunities": [],
        "affixes": ["Covenant Warden"],
        "is_anomalous_manifestation": True,
        "is_pact_exorcism_boss": True,
        "exorcism_patron_id": str(patron["patron_id"]),
        "exorcism_holder_id": str(contract_row.get("holder_id") or char.get("user_id") or ""),
        "exorcism_contract_key": str(contract_row.get("contract_key") or ""),
        "xp_multiplier": 1.25,
        "gold_drop": 0,
        "intent": f"Enforcing {entity_name}'s binding covenant in ritual combat",
    }
    enemies = [e for e in (session.get("nearby_enemies") or []) if isinstance(e, dict) and int(e.get("hp", 1) or 0) > 0]
    if not any(e.get("exorcism_contract_key") == boss_dict["exorcism_contract_key"] for e in enemies if isinstance(e, dict)):
        enemies.append(boss_dict)
    session["nearby_enemies"] = enemies
    db.update_session(int(session_id), nearby_enemies=enemies)
    return boss_dict


def execute_pact_ritual_action(
    session_id: int,
    user_id: int,
    ritual_action: str,
    patron_id: str,
    *,
    tier: int = 1,
    use_credits: bool = True,
    lang: str = "en",
) -> Dict[str, Any]:
    """
    Executes `sign`, `upgrade`, `feed`, or `sever` deterministically and returns
    `{ok, action, message, stage_direction, spawned_exorcism_boss, overview}`.
    """
    ensure_pact_spells_registered()
    sid = int(session_id)
    uid = int(user_id)
    act = str(ritual_action or "").strip().lower()
    pid = str(patron_id or "").strip()

    sess = db.get_session(sid)
    if not sess:
        raise ValueError("Session not found.")
    scen_key = str(sess.get("scenario") or "")
    if not is_entity_contracts_scenario(scen_key):
        raise ValueError("Entity Contracts are not active in this scenario.")

    char = db.get_character(uid, session_id=sid)
    if not char:
        raise ValueError("Active character not found.")

    cur_turn = max(1, int(sess.get("turn_count") or 1))
    cur_day = max(1, int(sess.get("current_day") or 1))
    contained_records = list(sess.get("contained_anomalies_log") or [])

    if act == "sign":
        avail = get_available_patrons_for_context(sess, char, uid, lang=lang)
        matched_offer = next((o for o in avail["patrons"] if o["patron_id"] == pid), None)
        if not matched_offer:
            raise ValueError("That Patron is not reachable through any active channel at your current location.")
        if not matched_offer.get("can_sign"):
            raise ValueError(str(matched_offer.get("blocked_reason") or "Cannot sign contract."))

        patron = get_patron_by_id(pid, scenario_or_key=scen_key, lang=lang, contained_records=contained_records)
        if not patron:
            raise ValueError("Patron definition could not be resolved.")

        is_dd = bool(matched_offer.get("is_deaths_door_offer"))
        extra_meta = {"discovery_channel": matched_offer.get("channel", "")}
        signed = db.sign_entity_contract(
            sid,
            uid,
            patron,
            tier=tier,
            turn_number=cur_turn,
            current_day=cur_day,
            is_deaths_door=is_dd,
            extra_metadata=extra_meta,
        )

        events: List[Dict[str, Any]] = []
        # If signed via Mid-Delve <=15% HP Boss Surrender, pacify enemy & forfeit kill bounty!
        is_boss_surrender = False
        surr_name = str(matched_offer.get("surrender_enemy_name") or "").strip()
        if matched_offer.get("channel") == "boss_surrender" and surr_name:
            is_boss_surrender = True
            updated_enemies = []
            for enem in (sess.get("nearby_enemies") or []):
                if isinstance(enem, dict) and str(enem.get("name") or "").strip().lower() == surr_name.lower():
                    enem = dict(enem)
                    enem["hp"] = 0
                    enem["surrendered"] = True
                    enem["_surrendered_for_pact"] = True
                    enem["gold_drop"] = 0
                    continue
                updated_enemies.append(enem)
            sess["nearby_enemies"] = updated_enemies
            db.update_session(sid, nearby_enemies=updated_enemies)
            events.append({"type": "boss_surrender_sealed", "actor": char.get("name", "You"), "patron_name": patron.get("display_name")})

        # Register recurring tithe obligation in commitments_ledger if applicable
        tithe_sched = signed.get("tithe_schedule") or {}
        if tithe_sched.get("next_due_day"):
            try:
                from mechanics.system.commitments_engine import create_promise
                create_promise(
                    sid,
                    promiser="player",
                    promisee=str(patron.get("name") or pid),
                    description=f"Offer {tithe_sched.get('label', 'tribute')} to {patron.get('name', pid)} before Day {tithe_sched['next_due_day']}.",
                    subtype="pact_tithe",
                    deadline_day=int(tithe_sched["next_due_day"]),
                    deadline_minute=1439,
                    metadata={"patron_id": pid, "contract_key": signed["contract_key"], "holder_id": str(uid)},
                    turn_created=cur_turn,
                )
            except Exception as exc:
                log.debug("pact_tithe promise creation skipped: %s", exc)

        p_disp = str(patron.get("display_name") or patron.get("name") or pid)
        return {
            "ok": True,
            "action": "sign",
            "contract": signed,
            "message": f"Sealed Tier {signed['tier']} covenant with {p_disp}.",
            "stage_direction": build_pact_turn_stage_direction(events),
            "spawned_exorcism_boss": None,
            "boss_surrender": is_boss_surrender,
            "overview": build_contracts_overview_payload(sid, uid, lang=lang),
        }

    if act == "upgrade":
        if not can_perform_remote_pact_ritual(sess, char):
            raise ValueError("Return to a sanctuary, shrine, vault, or your quarters outside combat to deepen a covenant.")
        patron = get_patron_by_id(pid, scenario_or_key=scen_key, lang=lang, contained_records=contained_records)
        if not patron:
            raise ValueError("Patron definition not found.")
        upgraded = db.upgrade_entity_contract_tier(
            sid, uid, pid, patron, target_tier=tier if tier > 1 else None, turn_number=cur_turn
        )
        return {
            "ok": True,
            "action": "upgrade",
            "contract": upgraded,
            "message": f"Deepened covenant with {patron.get('display_name', pid)} to Tier {upgraded['tier']}.",
            "stage_direction": "",
            "spawned_exorcism_boss": None,
            "boss_surrender": False,
            "overview": build_contracts_overview_payload(sid, uid, lang=lang),
        }

    if act == "feed":
        active_pacts = db.get_player_active_pacts(sid, uid)
        cur_row = next((r for r in active_pacts if r["patron_id"] == pid), None)
        if not cur_row:
            raise ValueError("No active contract found for that Patron.")
        patron = get_patron_by_id(pid, scenario_or_key=scen_key, lang=lang, contained_records=contained_records)
        tithe = cur_row.get("tithe_schedule") or {}
        keywords = [str(k).lower() for k in (tithe.get("item_keywords") or ["incense", "charm", "ration", "tonic"])]
        credit_cost = int(tithe.get("credit_fallback") or (50 + int(cur_row.get("unpaid_blood_debt") or 0) * 2))

        inv = db.get_inventory(uid) or []
        matched_item = None
        for it in inv:
            if not isinstance(it, dict) or it.get("equipped") or it.get("is_pact_locked") or it.get("is_quest_locked"):
                continue
            nm_low = str(it.get("name") or "").lower()
            if any(kw in nm_low for kw in keywords):
                matched_item = it
                break

        payment_desc = ""
        if matched_item and not use_credits:
            db.remove_item(uid, int(matched_item["id"]))
            payment_desc = f"offered {matched_item['name']}"
        elif matched_item and int(char.get("gold") or 0) < credit_cost:
            db.remove_item(uid, int(matched_item["id"]))
            payment_desc = f"offered {matched_item['name']}"
        else:
            if int(char.get("gold") or 0) < credit_cost:
                if matched_item:
                    db.remove_item(uid, int(matched_item["id"]))
                    payment_desc = f"offered {matched_item['name']}"
                else:
                    raise ValueError(
                        f"Offering requires an item matching ({', '.join(keywords[:3])}) or {credit_cost} Credits."
                    )
            else:
                db.apply_hp_mp_delta(uid, gold_delta=-credit_cost, character_id=char.get("id"))
                payment_desc = f"paid {credit_cost} Credits in ritual tribute"

        updated = db.record_pact_resonance_and_charges(
            sid,
            cur_row["contract_key"],
            user_id=uid,
            patron=patron,
            xp_delta=1,
            current_day=cur_day,
            clear_breach=True,
            advance_tithe=True,
            turn_number=cur_turn,
        )
        _fulfill_patron_blood_debt_commitments(sid, pid, str(cur_row.get("entity_name") or pid))
        return {
            "ok": True,
            "action": "feed",
            "contract": updated,
            "message": f"Communed with {cur_row['entity_name']} ({payment_desc}); Resonance +1 and displeasure cleared.",
            "stage_direction": "",
            "spawned_exorcism_boss": None,
            "boss_surrender": False,
            "overview": build_contracts_overview_payload(sid, uid, lang=lang),
        }

    if act == "sever":
        active_pacts = db.get_player_active_pacts(sid, uid)
        cur_row = next((r for r in active_pacts if r["patron_id"] == pid), None)
        if not cur_row:
            raise ValueError("No active contract found for that Patron.")
        patron = get_patron_by_id(pid, scenario_or_key=scen_key, lang=lang, contained_records=contained_records)
        if not patron:
            raise ValueError("Patron definition not found.")

        peaceful_ok, fee, method_lbl = can_perform_peaceful_medical_or_shrine_scrub(sess, cur_row)
        if peaceful_ok:
            if not can_perform_remote_pact_ritual(sess, char):
                raise ValueError("Visit a clinic, shrine, containment bay, or safe sanctuary outside combat to cleanse this pact.")
            if int(char.get("gold") or 0) < fee:
                raise ValueError(f"{method_lbl} requires {fee} Credits (current: {int(char.get('gold') or 0)}).")
            if fee > 0:
                db.apply_hp_mp_delta(uid, gold_delta=-fee, character_id=char.get("id"))
            sev = db.sever_entity_contract(sid, uid, pid, turn_number=cur_turn, mark_spurned=False)
            _fulfill_patron_blood_debt_commitments(sid, pid, str(cur_row.get("entity_name") or pid))
            return {
                "ok": True,
                "action": "sever",
                "contract": sev,
                "message": f"{method_lbl} complete: cleanly severed covenant with {cur_row['entity_name']}.",
                "stage_direction": "",
                "spawned_exorcism_boss": None,
                "overview": build_contracts_overview_payload(sid, uid, lang=lang),
            }

        # Tier III Exclusive, Unregulated Black-Market/Cult, or Breached -> Spawn Manifestation Exorcism Boss Fight!
        boss = spawn_manifestation_exorcism_boss(sid, sess, char, cur_row, patron)
        st_dir = build_pact_turn_stage_direction([
            {"type": "exorcism_spawned", "actor": char.get("name", "You"), "patron_name": cur_row["entity_name"]}
        ])
        return {
            "ok": True,
            "action": "sever_exorcism",
            "contract": cur_row,
            "message": f"{cur_row['entity_name']} refuses peaceful release! Defeat {boss['name']} to sever the covenant!",
            "stage_direction": st_dir,
            "spawned_exorcism_boss": boss,
            "overview": build_contracts_overview_payload(sid, uid, lang=lang),
        }

    raise ValueError(f"Unsupported contract ritual action: '{ritual_action}'.")


# ---------------------------------------------------------------------------
# 4. Post-Turn Atomic Costs, Lethal Overdraw, Breaches & Exorcism / VIP Liberation
# ---------------------------------------------------------------------------

def _spawn_grudge_nemesis_enemy(
    session_id: int,
    session: Dict[str, Any],
    char: Dict[str, Any],
    entity_name: str,
    patron_id: str,
    element: str = "aether",
) -> Dict[str, Any]:
    lvl = max(2, int(char.get("level") or 1) + 2)
    max_hp = 105 + lvl * 20
    stats = build_monster_stat_sheet(lvl, "Stalker")
    nemesis = {
        "name": f"{entity_name} (Grudge Nemesis)",
        "archetype": "Spurned Patron Nemesis",
        "level": lvl,
        "tier_rank": 4,
        "hp": max_hp,
        "max_hp": max_hp,
        "mp": 60,
        "max_mp": 60,
        "stability": 100,
        "max_stability": 100,
        "primary_element": element,
        "sapience": "sapient",
        "physicality": "corporeal",
        "stats": stats,
        "status_effects": ["Enraged [+30% ATK] [3 turns]"],
        "weaknesses": [],
        "resistances": [element],
        "immunities": [],
        "affixes": ["Vengeful Grudge"],
        "is_anomalous_manifestation": True,
        "is_grudge_nemesis": True,
        "grudge_patron_id": patron_id,
        "intent": f"Hunting the oathbreaker who spurned {entity_name}",
    }
    enemies = [e for e in (session.get("nearby_enemies") or []) if isinstance(e, dict) and int(e.get("hp", 1) or 0) > 0]
    if not any(e.get("grudge_patron_id") == patron_id for e in enemies if isinstance(e, dict)):
        enemies.append(nemesis)
    session["nearby_enemies"] = enemies
    db.update_session(int(session_id), nearby_enemies=enemies)
    return nemesis


def evaluate_post_turn_pact_costs_and_breaches(
    session_id: int,
    session: Dict[str, Any],
    party: List[Any],
    outcome: Dict[str, Any],
    actions: Optional[List[Dict[str, Any]]],
    turn_number: int,
) -> List[Dict[str, Any]]:
    """
    Atomically applies Pact cast costs, Lethal Overdraw (`0 HP` + 24h `pact_blood_debt` promise),
    overdue Tithe/Blood-Debt breach escalations, Exorcism Boss victories, VIP Tier III liberations,
    and School Civilian witness panic.

    Idempotent per `turn_number` (`session['_last_pact_eval_turn']`) so frozen-state narration retries
    never double-deduct HP/credits or double-escalate breaches!
    """
    if not session_id or not isinstance(session, dict):
        return []
    scen_key = str(session.get("scenario") or "")
    if not is_entity_contracts_scenario(scen_key):
        return []

    t_num = max(1, int(turn_number or 1))
    if int(session.get("_last_pact_eval_turn") or 0) == t_num:
        return list(session.get("_last_pact_turn_events") or [])

    cur_day = max(1, int(session.get("current_day") or 1))
    cur_min = max(0, int(session.get("current_minute") or 480))
    contained_records = list(session.get("contained_anomalies_log") or [])
    events: List[Dict[str, Any]] = []

    party_chars: Dict[int, Dict[str, Any]] = {}
    for member in party or []:
        c_dict = member[0] if isinstance(member, (tuple, list)) else member
        if isinstance(c_dict, dict) and c_dict.get("user_id"):
            party_chars[int(c_dict["user_id"])] = c_dict

    # A. Process Pact Skill Invocations from `actions`
    for act in actions or []:
        if not isinstance(act, dict):
            continue
        meta = act.get("_pact_cast_meta")
        spell_id = str(act.get("spell_id") or "").strip()
        if not meta and not spell_id.startswith("pact_"):
            continue
        uid = int(act.get("user_id") or (act.get("char") or {}).get("user_id") or 0)
        if not uid:
            continue
        char = db.get_character(uid, session_id=int(session_id)) or party_chars.get(uid) or {}
        active_pacts = db.get_player_active_pacts(int(session_id), uid)
        if isinstance(meta, dict) and meta.get("contract_key"):
            c_row = next((r for r in active_pacts if r["contract_key"] == meta["contract_key"]), None)
        else:
            c_row = next(
                (
                    r for r in active_pacts
                    if build_pact_spell_id(
                        get_patron_by_id(r["patron_id"], scenario_or_key=scen_key, contained_records=contained_records) or {},
                        int(r.get("tier") or 1),
                    ) == spell_id
                ),
                active_pacts[0] if active_pacts else None,
            )
        if not c_row:
            continue
        patron = get_patron_by_id(c_row["patron_id"], scenario_or_key=scen_key, contained_records=contained_records)
        if not patron:
            continue

        costs = meta if isinstance(meta, dict) else compute_pact_cast_costs(char, c_row, patron)
        hp_cost = int(costs.get("hp_cost") or 0)
        credit_cost = int(costs.get("credit_cost") or 0)
        cur_hp = int(char.get("hp") or 1)
        is_overdraw = bool(costs.get("is_lethal_overdraw") or (hp_cost > 0 and cur_hp <= hp_cost))

        if credit_cost > 0:
            db.apply_hp_mp_delta(uid, gold_delta=-credit_cost, character_id=char.get("id"))
        if hp_cost > 0:
            if is_overdraw:
                # Drop directly to 0 HP so emergency extraction fires cleanly!
                db.apply_hp_mp_delta(uid, hp_delta=-max(cur_hp, hp_cost), character_id=char.get("id"))
                if uid in party_chars:
                    party_chars[uid]["hp"] = 0
            else:
                db.apply_hp_mp_delta(uid, hp_delta=-hp_cost, character_id=char.get("id"))
                if uid in party_chars:
                    party_chars[uid]["hp"] = max(1, cur_hp - hp_cost)

        updated_row = db.record_pact_resonance_and_charges(
            int(session_id),
            c_row["contract_key"],
            user_id=uid,
            patron=patron,
            xp_delta=1,
            charge_delta=1,
            current_day=cur_day,
            turn_number=t_num,
        )

        # Apply Exhausted status if final daily charge was spent
        exhaust_tag = str(costs.get("exhaust_status_on_final_charge") or "").strip()
        max_chg = int(costs.get("daily_charges_max") or 0)
        used_after = int(((updated_row or {}).get("metadata") or {}).get("daily_charges_used") or 0)
        if exhaust_tag and max_chg > 0 and used_after >= max_chg:
            db.add_status_effect(uid, exhaust_tag)

        sp_def = build_pact_spell_def(patron, int(c_row.get("tier") or 1))
        actor_name = str(char.get("name") or "Player")
        p_name = str(patron.get("display_name") or c_row["entity_name"])

        if is_overdraw:
            debt_amt = max(10, hp_cost - max(0, cur_hp) + 10)
            db.apply_contract_breach_strike(
                int(session_id),
                c_row["contract_key"],
                reason="lethal_overdraw_blood_debt",
                blood_debt_amount=debt_amt,
                turn_number=t_num,
            )
            try:
                from mechanics.system.commitments_engine import create_promise
                create_promise(
                    int(session_id),
                    promiser="player",
                    promisee=p_name,
                    description=f"Settle your Lethal Overdraw Blood Debt to {p_name} within 24 hours or suffer Violent Severance.",
                    subtype="pact_blood_debt",
                    deadline_day=cur_day + 1,
                    deadline_minute=cur_min,
                    metadata={"patron_id": c_row["patron_id"], "contract_key": c_row["contract_key"], "holder_id": str(uid)},
                    turn_created=t_num,
                )
            except Exception as exc:
                log.debug("Failed creating pact_blood_debt promise: %s", exc)
            events.append({"type": "lethal_overdraw", "actor": actor_name, "patron_name": p_name, "skill_name": sp_def["name"], "patron_id": c_row["patron_id"]})
        else:
            events.append({"type": "pact_cast", "actor": actor_name, "patron_name": p_name, "skill_name": sp_def["name"], "patron_id": c_row["patron_id"]})

        # School Civilian Witness Panic Check (Anomalous High School only; pragmatic tolerance in agency ops & sparring!)
        if scenario_data.is_anomalous_high_school_scenario(scen_key):
            is_sparring_bout = any(isinstance(e, dict) and e.get("sparring") for e in (session.get("nearby_enemies") or []))
            loc_low = _extract_location_corpus(session)
            on_campus = any(w in loc_low for w in ("school", "academy", "campus", "classroom", "hallway", "courtyard", "cafeteria", "gym"))
            if on_campus and not is_sparring_bout:
                from mechanics.social.anomalous_npc_tags import TAG_CIVILIAN, classify_anomalous_npc_tag
                civ_witnesses = [
                    n for n in (session.get("current_npcs") or [])
                    if isinstance(n, dict) and classify_anomalous_npc_tag(n, session_id=int(session_id), scen_key=scen_key) == TAG_CIVILIAN
                ]
                if civ_witnesses:
                    events.append({"type": "school_civilian_panic", "actor": actor_name, "patron_name": p_name})

    # B. Check Defeated Enemies for Exorcism Victory & Hostile VIP Tier III Liberation
    cbt_res = outcome.get("_combat_result") if isinstance(outcome, dict) else None
    defeated_dicts: List[Dict[str, Any]] = []
    if isinstance(cbt_res, dict):
        for de in (cbt_res.get("defeated_enemy_dicts") or []):
            if isinstance(de, dict):
                defeated_dicts.append(de)
        defeated_names_low = {str(n).strip().lower() for n in (cbt_res.get("defeated_enemies") or []) if n}
        for e_prev in (session.get("_pre_combat_enemies") or session.get("nearby_enemies") or []):
            if isinstance(e_prev, dict):
                nm = str(e_prev.get("name") or "").strip()
                if nm.lower() in defeated_names_low or int(e_prev.get("hp", 1) or 0) <= 0:
                    defeated_dicts.append(e_prev)

    seen_exorcisms: set[str] = set()
    for de in defeated_dicts:
        if de.get("is_pact_exorcism_boss") and de.get("exorcism_patron_id"):
            ex_key = f"{de.get('exorcism_holder_id')}:{de.get('exorcism_patron_id')}"
            if ex_key in seen_exorcisms:
                continue
            seen_exorcisms.add(ex_key)
            h_uid_str = str(de.get("exorcism_holder_id") or "")
            if h_uid_str.isdigit():
                try:
                    sev = db.sever_entity_contract(int(session_id), int(h_uid_str), str(de["exorcism_patron_id"]), turn_number=t_num)
                    _fulfill_patron_blood_debt_commitments(int(session_id), str(de["exorcism_patron_id"]), sev["entity_name"])
                    events.append({"type": "exorcism_victory", "actor": party_chars.get(int(h_uid_str), {}).get("name", "Player"), "patron_name": sev["entity_name"]})
                except Exception:
                    pass
        elif de.get("is_special_agent") or str(de.get("anomalous_npc_tag") or "") == "special_agent":
            freed_pids = db.liberate_npc_exclusive_pacts(int(session_id), str(de.get("name") or ""), turn_number=t_num)
            for f_pid in freed_pids:
                events.append({"type": "vip_exclusive_liberated", "actor": de.get("name", "VIP Operative"), "patron_name": f_pid})

    # C. Check Overdue Blood Debts & Tithe Deadlines across all party members
    pending_soul_scar_uids: List[int] = []
    processed_breach_ckeys: set[str] = set()
    with db.get_conn() as conn:
        expired_debts = conn.execute(
            """SELECT id, metadata_json FROM commitments_ledger
               WHERE session_id = ? AND status = 'active'
                 AND scheduled_day IS NOT NULL
                 AND (scheduled_day < ? OR (scheduled_day = ? AND end_minute < ?))""",
            (int(session_id), cur_day, cur_day, cur_min),
        ).fetchall()
        for ed in expired_debts:
            try:
                em = json.loads(ed["metadata_json"] or "{}")
            except Exception:
                em = {}
            if em.get("subtype") not in ("pact_blood_debt", "pact_tithe"):
                continue
            ckey = str(em.get("contract_key") or "")
            if not ckey:
                continue
            conn.execute("UPDATE commitments_ledger SET status = 'flaked', updated_at = ? WHERE id = ?", (time.time(), ed["id"]))
            if ckey in processed_breach_ckeys:
                continue
            processed_breach_ckeys.add(ckey)
            if em.get("subtype") == "pact_tithe":
                db.record_pact_resonance_and_charges(
                    int(session_id), ckey, xp_delta=0, current_day=cur_day, advance_tithe=True, turn_number=t_num, conn=conn
                )
            strike = db.apply_contract_breach_strike(
                int(session_id), ckey, reason=f"expired_{em['subtype']}", turn_number=t_num, conn=conn
            )
            h_uid = int(strike["holder_id"]) if str(strike.get("holder_id") or "").isdigit() else 0
            c_obj = party_chars.get(h_uid) or {}
            if strike.get("escalated_to") == 1:
                events.append({"type": "breach_stage1", "actor": c_obj.get("name", "Player"), "patron_name": strike.get("entity_name", "Patron")})
            elif strike.get("escalated_to") == 2:
                if h_uid:
                    pending_soul_scar_uids.append(h_uid)
                events.append({
                    "type": "breach_stage2",
                    "actor": c_obj.get("name", "Player"),
                    "patron_name": strike.get("entity_name", "Patron"),
                    "grudge_nemesis_spawned": strike.get("grudge_nemesis_spawned", False),
                    "_spawn_nemesis_for": (h_uid, strike.get("entity_name", "Patron"), strike.get("patron_id", "")),
                })

    for _scar_uid in dict.fromkeys(pending_soul_scar_uids):
        db.add_status_effect(_scar_uid, "Soul Scar")

    # Also check raw `tithe_schedule.next_due_day` on active contracts if no commitment row caught it
    batch_pacts = db.get_session_pacts_batch(int(session_id), holder_type="player", active_only=True)
    for hid_str, p_list in batch_pacts.items():
        if not hid_str.isdigit():
            continue
        h_uid = int(hid_str)
        c_obj = party_chars.get(h_uid) or db.get_character(h_uid, session_id=int(session_id)) or {}
        for row in p_list:
            if row.get("contract_key") in processed_breach_ckeys:
                continue
            tithe = row.get("tithe_schedule") or {}
            due_day = tithe.get("next_due_day")
            if due_day is not None and cur_day > int(due_day):
                # Advance due day so it strikes once per missed cycle rather than every single turn on the same day
                db.record_pact_resonance_and_charges(
                    int(session_id), row["contract_key"], xp_delta=0, current_day=cur_day, advance_tithe=True, turn_number=t_num
                )
                strike = db.apply_contract_breach_strike(
                    int(session_id), row["contract_key"], reason="missed_tithe_offering", turn_number=t_num
                )
                if strike.get("escalated_to") == 1:
                    events.append({"type": "breach_stage1", "actor": c_obj.get("name", "Player"), "patron_name": strike.get("entity_name", "Patron")})
                elif strike.get("escalated_to") == 2:
                    db.add_status_effect(h_uid, "Soul Scar")
                    events.append({
                        "type": "breach_stage2",
                        "actor": c_obj.get("name", "Player"),
                        "patron_name": strike.get("entity_name", "Patron"),
                        "grudge_nemesis_spawned": strike.get("grudge_nemesis_spawned", False),
                        "_spawn_nemesis_for": (h_uid, strike.get("entity_name", "Patron"), strike.get("patron_id", "")),
                    })

    if isinstance(outcome, dict) and "nearby_enemies" in outcome and outcome["nearby_enemies"] is not None:
        session["nearby_enemies"] = list(outcome["nearby_enemies"])

    nemesis_spawned = False
    for ev in events:
        nem_info = ev.pop("_spawn_nemesis_for", None)
        if nem_info and ev.get("grudge_nemesis_spawned"):
            n_uid, n_ename, n_pid = nem_info
            c_obj = party_chars.get(n_uid) or (db.get_character(n_uid, session_id=int(session_id)) if n_uid else {}) or {}
            p_def = get_patron_by_id(n_pid, scenario_or_key=scen_key) or {}
            _spawn_grudge_nemesis_enemy(
                int(session_id), session, c_obj, str(n_ename), str(n_pid), str(p_def.get("element") or "aether")
            )
            nemesis_spawned = True

    if nemesis_spawned and isinstance(outcome, dict) and "nearby_enemies" in session:
        outcome["nearby_enemies"] = list(session["nearby_enemies"])

    session["_last_pact_eval_turn"] = t_num
    session["_last_pact_turn_events"] = events
    return events


# ---------------------------------------------------------------------------
# 5. 30–40% Pre-Contracted Special Agent Roster Seeding
# ---------------------------------------------------------------------------

def assign_special_agent_contracts(
    session_id: int,
    roster: List[Dict[str, Any]],
    scen_key: str = "anomalous_incursions",
) -> List[Dict[str, Any]]:
    """
    Deterministically assigns Entity Contracts to 30–40% (~35% target) of the Special Agent roster,
    weighted by `agent_tier` and `faction_id`, and registers them in `session_entity_contracts`
    so Tier III Exclusive Cores remain globally unique across players + NPCs!
    """
    if not roster or not is_entity_contracts_scenario(scen_key):
        return roster

    ensure_pact_spells_registered()
    pool = get_bespoke_patrons(scen_key)
    for fk_cid in ("folk_hantu_raya", "folk_yuki_onna", "folk_bunian_sorok", "folk_harimau_jadian", "folk_pontianak"):
        fp = synthesize_folklore_patron(fk_cid, scenario_or_key=scen_key)
        if fp:
            pool.append(fp)
    if not pool:
        return roster

    # Score each agent deterministically so exactly ~35% (strictly within 30%..40%) receive a contract
    scored_indices: List[Tuple[float, int]] = []
    for idx, ag in enumerate(roster):
        if not isinstance(ag, dict):
            continue
        ag_id = str(ag.get("agent_id") or ag.get("name") or idx)
        tier = max(1, min(5, int(ag.get("agent_tier") or 1)))
        fac = str(ag.get("faction_id") or "").strip().lower()
        fac_bonus = 0.18 if fac in ("cult_faction", "clandestine_faction") else (0.08 if fac == "monastic_order" else 0.0)
        tier_bonus = (tier - 1) * 0.09
        base_roll = (_stable_seed_int(f"agent_pact:{session_id}:{ag_id}") % 10000) / 10000.0
        scored_indices.append((base_roll + fac_bonus + tier_bonus, idx))

    scored_indices.sort(key=lambda pair: pair[0], reverse=True)
    target_count = max(1, int(round(len(scored_indices) * 0.35)))
    chosen_idx_set = {idx for _sc, idx in scored_indices[:target_count]}

    exclusive_taken: set[str] = set()
    for idx, ag in enumerate(roster):
        if not isinstance(ag, dict):
            continue
        if idx not in chosen_idx_set:
            ag.setdefault("has_entity_contract", False)
            continue

        ag_id = str(ag.get("agent_id") or ag.get("name") or f"agent_{idx}")
        ag_name = str(ag.get("name") or ag_id)
        ag_tier = max(1, min(5, int(ag.get("agent_tier") or 1)))
        fac = str(ag.get("faction_id") or "").strip().lower()
        rng = random.Random(_stable_seed_int(f"agent_patron_pick:{session_id}:{ag_id}"))

        # Prefer faction-aligned Patrons first
        preferred_ids = VAULT_FACTION_RULES.get(fac, {}).get("patron_ids") or ()
        pref_candidates = [p for p in pool if p["patron_id"] in preferred_ids]
        patron = rng.choice(pref_candidates) if pref_candidates and rng.random() < 0.70 else rng.choice(pool)

        # Only Tier 4–5 elite VIPs can hold Exclusive Tier III Pacts (and max 1 per Patron)
        if ag_tier >= 4 and patron["patron_id"] not in exclusive_taken and rng.random() < 0.45:
            pact_tier = 3
        elif ag_tier >= 3:
            pact_tier = 2
        else:
            pact_tier = 1

        if session_id:
            seeded = db.seed_npc_entity_contract(
                int(session_id), ag_id, ag_name, patron, tier=pact_tier, turn_number=0
            )
            if seeded is None and pact_tier >= 3:
                pact_tier = 2
                db.seed_npc_entity_contract(int(session_id), ag_id, ag_name, patron, tier=2, turn_number=0)

        if pact_tier >= 3:
            exclusive_taken.add(patron["patron_id"])

        sp_id = build_pact_spell_id(patron, pact_tier)
        ag["has_entity_contract"] = True
        ag["pact_id"] = patron["patron_id"]
        ag["pact_name"] = str(patron.get("display_name") or patron.get("name") or patron["patron_id"])
        ag["pact_tier"] = pact_tier
        ag["pact_spell_id"] = sp_id
        ag["pact_tell"] = str((patron.get("visuals") or {}).get("rest_tell_prose") or "a subtle occult covenant mark")

    return roster
