from __future__ import annotations
"""
Entity Contract Appraisal, Slot Capacity, Non-Destructive Stat Projection & Symbiotic Gear (Layer 2).

Pure deterministic rules with zero direct SQLite queries:
- Slot cap: 2 base, or 3 when unmodified base `END >= 7`.
- Permanent stat locks: require unmodified base `stat + delta >= 1` (`BASE_STAT_VALUE`).
- Derived projection: `apply_active_pact_modifiers` overlays stat & `% Max HP` locks onto character dicts
  while preserving `_base_stats` and `_base_max_hp` so level-ups and rollbacks never drift.
- `[Pact-Bound]` gear builder: produces `[GEAR_JSON]` equipment envelopes scaled to Player Level + Pact Tier.
"""

import json
import math
from typing import Any, Dict, List, Optional, Tuple

import character_data as cd
from mechanics.combat.equipment.metadata import (
    build_equipment_effect_str,
    normalize_dual_tier_metadata,
)

STAT_COL_MAP: Dict[str, str] = {
    "STR": "str_",
    "PER": "per_",
    "END": "end_",
    "CHA": "cha",
    "INT": "int_",
    "AGI": "agi",
    "LUK": "luk",
}

APPRAISAL_COST_MULTIPLIERS: Dict[str, float] = {
    "favored": 0.65,
    "neutral": 1.00,
    "disdained": 1.50,
}

RESONANCE_XP_THRESHOLDS: Dict[int, int] = {
    1: 0,
    2: 3,   # 3 invocations/offerings to unlock Tier II (unless Favored)
    3: 8,   # 8 cumulative invocations/offerings to unlock Tier III (blocked if Disdained)
}


def get_unmodified_base_stat(char: Dict[str, Any], stat_code: str) -> int:
    """Returns the character's unmodified SQLite base stat (`STR`..`LUK`), ignoring active Pact locks."""
    if not isinstance(char, dict):
        return cd.BASE_STAT_VALUE
    s_up = str(stat_code or "").strip().upper()
    col = STAT_COL_MAP.get(s_up, s_up.lower())
    base_map = char.get("_base_stats")
    if isinstance(base_map, dict):
        if s_up in base_map:
            try:
                return int(base_map[s_up])
            except (TypeError, ValueError):
                pass
        if col in base_map:
            try:
                return int(base_map[col])
            except (TypeError, ValueError):
                pass
    raw = char.get(col)
    if raw is None:
        raw = char.get(s_up, cd.BASE_STAT_VALUE)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return cd.BASE_STAT_VALUE


def get_unmodified_base_max_hp(char: Dict[str, Any]) -> int:
    """Returns the character's unmodified SQLite `max_hp` prior to `% Max HP` Pact leases."""
    if not isinstance(char, dict):
        return 100
    if char.get("_base_max_hp") is not None:
        try:
            return int(char["_base_max_hp"])
        except (TypeError, ValueError):
            pass
    try:
        return int(char.get("max_hp") or cd.calculate_max_hp(get_unmodified_base_stat(char, "END")))
    except (TypeError, ValueError):
        return 100


def get_pact_slot_capacity(char: Optional[Dict[str, Any]]) -> int:
    """Base Pact Slot cap is 2, rising to 3 when unmodified base `END >= 7`."""
    if not isinstance(char, dict):
        return 2
    return 3 if get_unmodified_base_stat(char, "END") >= 7 else 2


def _extract_char_trait_tokens(char: Dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    desc = str(char.get("class_description") or "").lower()
    cls_name = str(char.get("char_class") or "").lower()
    for src in (desc, cls_name):
        for w in src.replace(",", " ").replace(".", " ").replace("/", " ").split():
            if len(w) >= 3:
                tokens.add(w.strip())
    app = char.get("appearance")
    if isinstance(app, str):
        try:
            app = json.loads(app)
        except Exception:
            app = {}
    if isinstance(app, dict):
        for k in ("demeanor", "personality", "vibe", "origin_mode"):
            val = str(app.get(k) or "").strip().lower()
            if val:
                tokens.update(val.replace("_", " ").split())
    return tokens


def evaluate_patron_appraisal(
    char: Dict[str, Any],
    patron: Dict[str, Any],
    *,
    is_deaths_door: bool = False,
) -> Dict[str, Any]:
    """Deterministically computes Patron 'Taste' Appraisal (`favored`, `neutral`, `disdained`)."""
    rules = patron.get("appraisal") if isinstance(patron.get("appraisal"), dict) else {}
    fav_score = 0
    dis_score = 0

    char_faction = str(char.get("joined_faction_id") or "").strip().lower()
    char_cls = str(char.get("char_class") or "").strip().lower()
    char_attr = str(char.get("attribute") or "").strip().lower()
    char_arch = str(char.get("combat_archetype") or "").strip().lower()
    char_gold = int(char.get("gold") or 0)
    trait_tokens = _extract_char_trait_tokens(char)

    # Favored checks
    for st, min_v in (rules.get("favored_min_stats") or {}).items():
        if get_unmodified_base_stat(char, st) >= int(min_v):
            fav_score += 2
    for st, max_v in (rules.get("favored_max_stats") or {}).items():
        if get_unmodified_base_stat(char, st) <= int(max_v):
            fav_score += 2
    if rules.get("favored_factions") and char_faction in [str(x).lower() for x in rules["favored_factions"]]:
        fav_score += 2
    if rules.get("favored_archetypes") and char_arch in [str(x).lower() for x in rules["favored_archetypes"]]:
        fav_score += 2
    if rules.get("favored_classes") and any(str(c).lower() in char_cls for c in rules["favored_classes"]):
        fav_score += 2
    if rules.get("favored_traits") and any(str(t).lower() in trait_tokens for t in rules["favored_traits"]):
        fav_score += 2
    if rules.get("favored_min_gold") is not None and char_gold >= int(rules["favored_min_gold"]):
        fav_score += 2
    if rules.get("favored_deaths_door") and is_deaths_door:
        fav_score += 3

    # Disdained checks
    for st, min_v in (rules.get("disdained_min_stats") or {}).items():
        if get_unmodified_base_stat(char, st) >= int(min_v):
            dis_score += 2
    if rules.get("disdained_factions") and char_faction in [str(x).lower() for x in rules["disdained_factions"]]:
        dis_score += 2
    if rules.get("disdained_attributes") and char_attr in [str(x).lower() for x in rules["disdained_attributes"]]:
        dis_score += 2
    if rules.get("disdained_classes") and any(str(c).lower() in char_cls for c in rules["disdained_classes"]):
        dis_score += 2
    if rules.get("disdained_traits") and any(str(t).lower() in trait_tokens for t in rules["disdained_traits"]):
        dis_score += 2
    if rules.get("disdained_max_gold") is not None and char_gold <= int(rules["disdained_max_gold"]):
        dis_score += 2

    if fav_score >= 2 and fav_score > dis_score:
        state = "favored"
    elif dis_score >= 2 and dis_score > fav_score:
        state = "disdained"
    else:
        state = "neutral"

    quote_key = f"{state}_quote"
    quote = str(rules.get(quote_key) or rules.get("neutral_quote") or "Name your price and seal the covenant.")
    return {
        "state": state,
        "cost_mult": APPRAISAL_COST_MULTIPLIERS[state],
        "upfront_tier_cap": 3 if state == "favored" else 1,
        "max_unlocked_tier": 2 if state == "disdained" else 3,
        "quote": quote,
    }


def compute_tier_locks_for_patron(
    patron: Dict[str, Any],
    tier: int,
    appraisal_state: str = "neutral",
) -> Tuple[Dict[str, int], float]:
    """Returns `(stat_locks_dict, max_hp_lock_pct)` for a Patron at `tier` (1..3) and `appraisal_state`."""
    t_idx = max(0, min(2, int(tier or 1) - 1))
    costs = patron.get("costs") or {}

    hp_locks = list(costs.get("tier_max_hp_lock_pct") or [0.0, 0.0, 0.0])
    raw_hp_lock = float(hp_locks[min(t_idx, len(hp_locks) - 1)] or 0.0)

    stat_locks_tiers = list(costs.get("tier_stat_locks") or [{}, {}, {}])
    raw_stat_locks = dict(stat_locks_tiers[min(t_idx, len(stat_locks_tiers) - 1)] or {})
    stat_locks: Dict[str, int] = {str(k).upper(): int(v) for k, v in raw_stat_locks.items() if int(v) != 0}

    app_norm = str(appraisal_state or "neutral").strip().lower()
    if app_norm == "favored":
        if t_idx == 2 and costs.get("favored_waives_tier3_stat_lock"):
            stat_locks = {}
        if t_idx == 2 and costs.get("favored_tier3_max_hp_lock_pct") is not None:
            raw_hp_lock = float(costs["favored_tier3_max_hp_lock_pct"])
        else:
            raw_hp_lock = round(raw_hp_lock * APPRAISAL_COST_MULTIPLIERS["favored"], 4)
    elif app_norm == "disdained" and raw_hp_lock > 0:
        raw_hp_lock = round(min(0.45, raw_hp_lock * APPRAISAL_COST_MULTIPLIERS["disdained"]), 4)

    return stat_locks, max(0.0, min(0.60, raw_hp_lock))


def can_afford_stat_locks(
    char: Dict[str, Any],
    candidate_stat_locks: Dict[str, int],
    existing_pacts: Optional[List[Dict[str, Any]]] = None,
    *,
    replacing_contract_key: str = "",
) -> Tuple[bool, str]:
    """Verifies that cumulative permanent stat locks never drop unmodified base stats below `BASE_STAT_VALUE` (1)."""
    cumulative: Dict[str, int] = {}
    for row in existing_pacts or []:
        if not isinstance(row, dict):
            continue
        if replacing_contract_key and str(row.get("contract_key") or "") == replacing_contract_key:
            continue
        raw_sl = row.get("stat_locks_json") if "stat_locks_json" in row else row.get("stat_locks")
        if isinstance(raw_sl, str):
            try:
                raw_sl = json.loads(raw_sl)
            except Exception:
                raw_sl = {}
        if isinstance(raw_sl, dict):
            for st, delta in raw_sl.items():
                st_u = str(st).upper()
                cumulative[st_u] = cumulative.get(st_u, 0) + int(delta or 0)

    for st, delta in (candidate_stat_locks or {}).items():
        st_u = str(st).upper()
        d_int = int(delta or 0)
        if d_int >= 0:
            continue
        total_delta = cumulative.get(st_u, 0) + d_int
        base_val = get_unmodified_base_stat(char, st_u)
        if base_val + total_delta < cd.BASE_STAT_VALUE:
            req_base = cd.BASE_STAT_VALUE - total_delta
            return False, f"Requires base {st_u} >= {req_base} (current base {st_u} is {base_val})."
    return True, ""


def apply_active_pact_modifiers(
    char: Optional[Dict[str, Any]],
    active_pacts: Optional[List[Dict[str, Any]]],
    active_grudges: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Projects derived stat locks, `% Max HP` leases, and `Soul Scar` penalties onto `char` without mutating SQLite columns."""
    if not isinstance(char, dict):
        return char
    out = dict(char)
    if "_base_stats" not in out or not isinstance(out.get("_base_stats"), dict):
        out["_base_stats"] = {st: int(out.get(col, cd.BASE_STAT_VALUE) or cd.BASE_STAT_VALUE) for st, col in STAT_COL_MAP.items()}
    if "_base_max_hp" not in out or out.get("_base_max_hp") is None:
        out["_base_max_hp"] = int(out.get("max_hp") or 100)

    scar_count = sum(
        1 for g in (active_grudges or [])
        if isinstance(g, dict) and bool(g.get("soul_scar_active")) and str(g.get("status") or "active") == "active"
    )
    if not active_pacts and scar_count <= 0:
        out["active_pact_count"] = 0
        out["pact_slot_capacity"] = get_pact_slot_capacity(out)
        return out

    stat_deltas: Dict[str, int] = {}
    total_hp_lock_pct = 0.10 * scar_count
    valid_count = 0

    for row in active_pacts or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("status") or "active") != "active":
            continue
        valid_count += 1
        raw_sl = row.get("stat_locks_json") if "stat_locks_json" in row else row.get("stat_locks")
        if isinstance(raw_sl, str):
            try:
                raw_sl = json.loads(raw_sl)
            except Exception:
                raw_sl = {}
        if isinstance(raw_sl, dict):
            for st, delta in raw_sl.items():
                col = STAT_COL_MAP.get(str(st).upper())
                if col:
                    stat_deltas[col] = stat_deltas.get(col, 0) + int(delta or 0)

        raw_meta = row.get("metadata_json") if "metadata_json" in row else row.get("metadata")
        if isinstance(raw_meta, str):
            try:
                raw_meta = json.loads(raw_meta)
            except Exception:
                raw_meta = {}
        if isinstance(raw_meta, dict):
            total_hp_lock_pct += float(raw_meta.get("max_hp_lock_pct") or 0.0)

    for st_code, col in STAT_COL_MAP.items():
        base_val = out["_base_stats"].get(st_code, out["_base_stats"].get(col, out.get(col, cd.BASE_STAT_VALUE)))
        delta = stat_deltas.get(col, 0)
        if delta != 0:
            out[col] = max(cd.BASE_STAT_VALUE, min(cd.MAX_STAT_VALUE, int(base_val) + delta))

    capped_lock = max(0.0, min(0.75, total_hp_lock_pct))
    if capped_lock > 0.0:
        eff_max_hp = max(10, int(round(int(out["_base_max_hp"]) * (1.0 - capped_lock))))
        out["max_hp"] = eff_max_hp
        if int(out.get("hp") or 0) > eff_max_hp:
            out["hp"] = eff_max_hp

    out["active_pact_count"] = valid_count
    out["pact_slot_capacity"] = get_pact_slot_capacity(out)
    out["pact_max_hp_lock_pct"] = round(capped_lock, 4)
    return out


def compute_pact_cast_costs(
    char: Dict[str, Any],
    contract_row: Dict[str, Any],
    patron: Dict[str, Any],
) -> Dict[str, Any]:
    """Computes exact deterministic HP/Credit/Daily-Charge cast cost and `is_lethal_overdraw` flag."""
    tier = max(1, min(3, int(contract_row.get("tier") or 1)))
    t_idx = tier - 1
    app_state = str(contract_row.get("appraisal_state") or "neutral").strip().lower()
    cost_mult = APPRAISAL_COST_MULTIPLIERS.get(app_state, 1.0)
    costs = patron.get("costs") or {}

    hp_pcts = list(costs.get("hp_pct_per_cast") or [0.0, 0.0, 0.0])
    raw_hp_pct = float(hp_pcts[min(t_idx, len(hp_pcts) - 1)] or 0.0) * cost_mult
    eff_max_hp = max(10, int(char.get("max_hp") or 100))
    hp_cost = int(math.ceil(eff_max_hp * raw_hp_pct)) if raw_hp_pct > 0 else 0

    lvl = max(1, int(char.get("level") or 1))
    credit_base = int(costs.get("credit_cost_base") or 0)
    credit_per_lvl = int(costs.get("credit_cost_per_level") or 0)
    credit_cost = int(round((credit_base + credit_per_lvl * (lvl - 1)) * cost_mult)) if credit_base > 0 else 0

    daily_tiers = list(costs.get("daily_charges_tiers") or [])
    daily_max = int(daily_tiers[min(t_idx, len(daily_tiers) - 1)]) if daily_tiers else int(costs.get("daily_charges") or 0)

    cur_hp = int(char.get("hp") or 0)
    cur_gold = int(char.get("gold") or 0)
    breach_stage = int(contract_row.get("breach_stage") or 0)

    raw_meta = contract_row.get("metadata_json") if "metadata_json" in contract_row else contract_row.get("metadata")
    if isinstance(raw_meta, str):
        try:
            raw_meta = json.loads(raw_meta)
        except Exception:
            raw_meta = {}
    meta = dict(raw_meta or {})
    charges_used_today = int(meta.get("daily_charges_used") or 0)

    blocked_reason = ""
    if breach_stage >= 1:
        blocked_reason = "Patron is Displeased (Stage 1 Breach). Satisfy your Blood Debt or Offering first."
    elif credit_cost > 0 and cur_gold < credit_cost:
        blocked_reason = f"Insufficient Credits ({cur_gold} / {credit_cost} required)."
    elif daily_max > 0 and charges_used_today >= daily_max:
        blocked_reason = f"Daily Pact charges exhausted ({charges_used_today}/{daily_max}). Rest until tomorrow."

    is_lethal_overdraw = bool(hp_cost > 0 and cur_hp <= hp_cost and not blocked_reason)

    return {
        "mp_cost": 0,
        "hp_cost": hp_cost,
        "hp_pct": round(raw_hp_pct, 4),
        "credit_cost": credit_cost,
        "daily_charges_max": daily_max,
        "daily_charges_used": charges_used_today,
        "exhaust_status_on_final_charge": str(costs.get("exhaust_on_empty") or ""),
        "is_lethal_overdraw": is_lethal_overdraw,
        "can_invoke": not bool(blocked_reason),
        "blocked_reason": blocked_reason,
    }


def build_pact_bound_gear_spec(
    char: Dict[str, Any],
    patron: Dict[str, Any],
    tier: int,
    contract_key: str,
) -> Optional[Dict[str, Any]]:
    """Builds the `[Pact-Bound]` item definition (`name`, `slot`, `item_type`, `effect` `[GEAR_JSON]`) if eligible."""
    gear_cfg = patron.get("bound_gear")
    if not isinstance(gear_cfg, dict):
        return None
    min_tier = int(gear_cfg.get("min_tier") or 1)
    if int(tier or 1) < min_tier:
        return None

    lvl = max(1, int(char.get("level") or 1))
    slot = str(gear_cfg.get("slot") or "Weapon")
    item_type = str(gear_cfg.get("item_type") or ("Gloves" if slot == "Gloves" else "Weapon"))
    name = str(gear_cfg.get("name") or f"[Pact-Bound] {patron.get('name', 'Symbiote')} Armament")
    handedness = str(gear_cfg.get("handedness") or "1H")
    archetype = str(gear_cfg.get("archetype") or ("gauntlet" if slot == "Gloves" else "shortsword"))

    tier_offset = max(0, int(tier) - min_tier)
    q_tier = "masterwork" if tier >= 3 or lvl >= 7 else "high_quality"
    e_tier = "tier_1" if tier >= 3 else "tier_2"

    metadata: Dict[str, Any] = {
        "name": name,
        "item_type": item_type,
        "archetype": archetype,
        "handedness": handedness,
        "quality_tier": q_tier,
        "enchantment_tier": e_tier,
        "is_pact_bound": True,
        "linked_contract_key": contract_key,
        "patron_id": str(patron.get("patron_id") or ""),
        "damage_type": str(gear_cfg.get("damage_type") or patron.get("element") or "aether"),
        "stat_modifiers": {},
    }
    if slot == "Weapon":
        base_mult = float(gear_cfg.get("base_multiplier") or 1.50)
        mult = round(base_mult + tier_offset * float(gear_cfg.get("tier_bonus_mult") or 0.20) + (lvl - 1) * 0.04, 2)
        metadata["multiplier"] = mult
        metadata["base_dt"] = 0
    else:
        base_dt = int(gear_cfg.get("base_dt") or 4)
        dt_val = base_dt + tier_offset * int(gear_cfg.get("tier_bonus_dt") or 2) + (lvl // 2)
        metadata["base_dt"] = dt_val
        metadata["multiplier"] = 1.15

    normalize_dual_tier_metadata(metadata)
    return {
        "name": name,
        "slot": slot,
        "item_type": item_type,
        "slot_cost": 0,  # Symbiotic graft/manifestation takes 0 backpack slots
        "effect": build_equipment_effect_str(metadata),
        "metadata": metadata,
    }
