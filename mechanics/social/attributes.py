from __future__ import annotations
"""
Base Combat Attributes Engine for Hikayat.

Derives dynamic combat attributes from a character's SPECIAL stats:
- Physical Attack (ATK):    10 + (STR * 10) + (AGI * 2)
- Magic Attack (MATK):      10 + (INT * 10) + (PER * 2)
- Physical Accuracy (ACC):  60% + (PER * 4%) + (AGI * 2%)
- Magic Accuracy (MACC):    60% + (PER * 4%) + (AGI * 2%)
- Evasion (EVA):            5% + (AGI * 4%) + (LUK * 2%)

Unified FNV DT + DR Defense System (Option A):
- Innate Physical DT (from END): floor(END / 3) + floor(Level / 5)
- Innate Magic DT (from INT):    floor(INT / 3) + floor(Level / 5)
- Innate Magic DR (from INT):    INT * 1.5%  [hard-capped at 85%]
  Applied as: damage_after_dr = raw * (1.0 - min(0.85, innate_magic_dr + gear_dr))
  Final net = max(raw * 0.20, damage_after_dr - effective_DT)

unified DR → DT → Floor pipeline in mechanics/combat.py.
"""
from typing import Dict, Any, List, Optional
import re
import character_data as cd


def calculate_combat_attributes(
    character: Dict[str, Any],
    equipped_items: Optional[List[Dict[str, Any]]] = None,
    scenario: Optional[str] = None
) -> Dict[str, Any]:
    """
    Computes base combat attributes dynamically from a character's SPECIAL stats
    and any equipped gear modifiers.
    If the character's scenario is non-combat, returns 0 values with is_non_combat=True.
    """
    from scenario_data import is_non_combat_scenario
    scen = scenario or character.get("scenario")
    if scen and is_non_combat_scenario(scen):
        return {
            "atk": 0, "matk": 0,
            "acc": 0, "macc": 0, "eva": 0, "block_chance": 0,
            "crit_success": 0.0, "crit_fail": 0.0,
            "base_atk": 0, "base_matk": 0,
            "base_acc": 0, "base_macc": 0, "base_eva": 0,
            "innate_phys_dt": 0, "innate_magic_dt": 0, "innate_magic_dr": 0.0,
            "is_non_combat": True
        }

    # Normalize stat extraction supporting both 'str_' and 'STR' keys
    str_ = character.get("str_", character.get("STR", cd.BASE_STAT_VALUE))
    per_ = character.get("per_", character.get("PER", cd.BASE_STAT_VALUE))
    end_ = character.get("end_", character.get("END", cd.BASE_STAT_VALUE))
    cha = character.get("cha", character.get("CHA", cd.BASE_STAT_VALUE))
    int_ = character.get("int_", character.get("INT", cd.BASE_STAT_VALUE))
    agi = character.get("agi", character.get("AGI", cd.BASE_STAT_VALUE))
    luk = character.get("luk", character.get("LUK", cd.BASE_STAT_VALUE))
    level = character.get("level", 1)

    # 1. Base SPECIAL scaling
    base_atk = 10 + (str_ * 10) + (agi * 2)
    base_matk = 10 + (int_ * 10) + (per_ * 2)
    base_acc = 60 + (per_ * 4) + (agi * 2)
    base_macc = 60 + (per_ * 4) + (agi * 2)
    base_eva = 5 + (agi * 4) + (luk * 2)

    # Innate DT / DR from SPECIAL (Unified FNV Defense)
    innate_phys_dt = int(end_ // 3) + int(level // 5)
    innate_magic_dt = int(int_ // 3) + int(level // 5)
    innate_magic_dr = min(0.85, int_ * 0.015)  # INT * 1.5%, hard-cap 85%

    # 2. Equipment modifiers (flat additions and percentage multipliers)
    flat_atk, mult_atk = 0, 0.0
    flat_def, mult_def = 0, 0.0
    flat_matk, mult_matk = 0, 0.0
    flat_mdef, mult_mdef = 0, 0.0
    flat_acc, flat_macc, flat_eva = 0, 0, 0
    flat_per, flat_cha = 0, 0
    flat_crit = 0.0
    block_chance = 0

    # Elemental attack bonuses
    elem_atks = {
        "fire_atk": 0, "shock_atk": 0, "ice_atk": 0,
        "poison_atk": 0, "holy_atk": 0, "dark_atk": 0
    }
    # Elemental and damage resistance affixes (DR%)
    elem_res = {
        "fire_res": 0, "shock_res": 0, "ice_res": 0,
        "poison_res": 0, "holy_res": 0, "dark_res": 0, "omni_res": 0,
        "physical_res": 0, "energy_res": 0
    }
    # Vitals & regeneration
    bonus_max_hp, bonus_max_mp = 0, 0
    hp_regen, mp_regen = 0, 0

    # Check if dedicated combat Armor is equipped
    has_combat_armor = False
    clothing_suppressed = False
    if equipped_items:
        from mechanics.combat.equipment import parse_equipment_metadata
        for item in equipped_items:
            if not isinstance(item, dict):
                continue
            s = item.get("slot", "") or ""
            t = (item.get("item_type") or "").lower()
            m = parse_equipment_metadata(item)
            arch = (m.get("archetype") or "").lower()
            if s == "Armor" or t == "armor" or (arch and arch not in ("clothes", "tunic", "casual_shirt", "blouse", "school_uniform_top", "jacket", "hoodie", "robe") and (m.get("base_dt", 0) > 2 or "armor" in t)):
                has_combat_armor = True
                break

    if equipped_items:
        from mechanics.combat.equipment import parse_equipment_metadata
        gear_tags = set()
        for item in equipped_items:
            if not isinstance(item, dict):
                continue
            meta = parse_equipment_metadata(item)
            slot_name = item.get("slot", "") or meta.get("slot", "")
            item_type_str = (item.get("item_type") or meta.get("item_type") or "").lower()
            arch_str = (meta.get("archetype") or "").lower()
            is_clothing_item = (
                item_type_str == "clothing"
                or slot_name in ("Top", "Bottom")
                or arch_str in ("clothes", "casual_shirt", "blouse", "school_uniform_top", "jacket", "hoodie", "robe", "tunic", "trousers", "skirt", "shorts", "slacks", "jeans")
            ) and slot_name != "Armor" and item_type_str != "armor"

            if has_combat_armor and is_clothing_item:
                clothing_suppressed = True
                # Skip stats and social modifiers from layered civilian clothing while encased in combat armor
                mods = {}
                social_mods = {}
            else:
                mods = meta.get("stat_modifiers") or {}
                social_mods = meta.get("social_modifiers") or {}

            # Fold in clothing social_modifiers if present (eva, luck, cha)
            if isinstance(mods, dict) or isinstance(social_mods, dict):
                m_dict = dict(mods) if isinstance(mods, dict) else {}
                if isinstance(social_mods, dict):
                    for sk, sv in social_mods.items():
                        m_dict[sk] = m_dict.get(sk, 0) + sv
                mods = m_dict

                flat_atk += mods.get("atk", 0)
                mult_atk += mods.get("atk_pct", 0.0)
                flat_def += mods.get("def", mods.get("def_", 0))
                mult_def += mods.get("def_pct", 0.0)
                flat_matk += mods.get("matk", 0)
                mult_matk += mods.get("matk_pct", 0.0)
                flat_mdef += mods.get("mdef", 0)
                mult_mdef += mods.get("mdef_pct", 0.0)
                flat_acc += mods.get("acc", 0)
                flat_macc += mods.get("macc", 0)
                
                # Evasion resolution: inspect mods, fallback to base_eva, then stats
                eva_val = mods.get("eva")
                if eva_val is None:
                    eva_val = meta.get("base_eva")
                if eva_val is None:
                    eva_val = meta.get("stats", {}).get("eva", 0)
                flat_eva += (eva_val or 0)

                flat_crit += mods.get("crit", 0.0)
                if "luck" in mods:
                    luk += mods["luck"]

                # Perception modifier from gear (helmets, visors, eyewear)
                item_per = mods.get("per", 0)
                if item_per < 0:
                    # Enforce strict maximum penalty of -1 PER for full-face helmets / sensory occlusion
                    flat_per += max(-1, item_per)
                else:
                    flat_per += item_per

                # Charisma modifier from gear (formal clothing, jewelry)
                flat_cha += mods.get("cha", 0)

                for e_k in elem_atks:
                    elem_atks[e_k] += mods.get(e_k, 0)
                for r_k in elem_res:
                    elem_res[r_k] += mods.get(r_k, 0)
                if "phys_res" in mods:
                    elem_res["physical_res"] += mods.get("phys_res", 0)

                bonus_max_hp += mods.get("max_hp", 0)
                bonus_max_mp += mods.get("max_mp", 0)
                hp_regen += mods.get("hp_regen", 0)
                mp_regen += mods.get("mp_regen", 0)
            
            if "block_chance" in meta:
                block_chance += meta.get("block_chance", 0)

            # Collect gear tags & special traits
            tags_obj = meta.get("tags") or {}
            if isinstance(tags_obj, dict):
                for val in tags_obj.values():
                    if isinstance(val, list):
                        for v in val: gear_tags.add(str(v).lower())
                    elif isinstance(val, str):
                        gear_tags.add(val.lower())
            elif isinstance(tags_obj, list):
                for v in tags_obj: gear_tags.add(str(v).lower())
            for trait in meta.get("special_traits", []):
                gear_tags.add(str(trait).lower())
            if meta.get("archetype"):
                gear_tags.add(str(meta["archetype"]).lower())
    else:
        gear_tags = set()

    # Active Status Effects & Consumable Buffs/Debuffs Resolution
    buff_dt = 0
    dt_degrade_pct = 0.0
    buff_dr = 0.0
    status_effects = character.get("status_effects") or []
    for eff in status_effects:
        eff_str = str(eff).strip()
        eff_lower = eff_str.lower()
        
        # Parse positive DT buff: "Iron Skin [+8 DT] [3 turns]" or "[4 DT]"
        dt_m = re.search(r"\[\+(\d+)\s*DT\]", eff_str, re.IGNORECASE)
        if dt_m:
            buff_dt += int(dt_m.group(1))

        # Parse temporary DT degradation / sunder: "Armor Cracked [-10 DT] [3 turns]"
        dt_debuff_m = re.search(r"\[-(\d+)\s*DT\]", eff_str, re.IGNORECASE)
        if dt_debuff_m:
            buff_dt -= int(dt_debuff_m.group(1))

        # Parse temporary DT percentage corrosion: "Acid Corroded [-50% DT] [2 turns]"
        dt_pct_debuff_m = re.search(r"\[-(\d+)%\s*DT\]", eff_str, re.IGNORECASE)
        if dt_pct_debuff_m:
            dt_degrade_pct += int(dt_pct_debuff_m.group(1)) / 100.0

        # Parse patterns like "Subdermal Barrier [+20% DR] [3 turns]" or "[0.20 DR]"
        dr_m = re.search(r"\[\+?(\d+)%\s*DR\]", eff_str, re.IGNORECASE)
        if dr_m:
            buff_dr += int(dr_m.group(1)) / 100.0

        # Parse patterns like "Combat Booster [+25% ATK] [3 turns]"
        atk_m = re.search(r"\[\+?(\d+)%\s*ATK\]", eff_str, re.IGNORECASE)
        if atk_m:
            mult_atk += int(atk_m.group(1)) / 100.0

        # Parse patterns like "Quickstep Phial [+15% EVA] [3 turns]"
        eva_m = re.search(r"\[\+?(\d+)%?\s*EVA\]", eff_str, re.IGNORECASE)
        if eva_m:
            flat_eva += int(eva_m.group(1))

        # Parse patterns like "Torn / Scorched Clothes [-1 CHA] [2 turns]"
        cha_m = re.search(r"\[([+-]?\d+)\s*CHA\]", eff_str, re.IGNORECASE)
        if cha_m:
            flat_cha += int(cha_m.group(1))

        # Parse patterns like "Sensory Daze [-1 PER] [2 turns]"
        per_m = re.search(r"\[([+-]?\d+)\s*PER\]", eff_str, re.IGNORECASE)
        if per_m:
            flat_per += int(per_m.group(1))


    # Check if a shield or off-hand weapon is equipped
    from mechanics.combat.equipment import parse_equipment_metadata
    has_shield = False
    offhand_weapon_meta = None
    offhand_item = None

    for item in (equipped_items or []):
        if not isinstance(item, dict):
            continue
        slot_check = item.get("slot", "") or ""
        type_check = (item.get("item_type") or "").lower()
        if slot_check == "Shield":
            meta = parse_equipment_metadata(item)
            if type_check == "weapon" or "multiplier" in meta or meta.get("slot") == "Weapon":
                offhand_weapon_meta = meta
                offhand_item = item
            else:
                has_shield = True
        elif type_check == "shield":
            has_shield = True

    # Weapon Multiplier Resolution
    weapon_mult = 1.0
    crit_bonus_from_weapon = 0.0
    versatile_bonus_applied = False
    equipped_weapon_handedness = None
    dual_wield_active = False
    finesse_single_wield_applied = False

    main_weapon_meta = None
    for item in (equipped_items or []):
        if not isinstance(item, dict):
            continue
        slot_check = item.get("slot", "") or ""
        type_check = (item.get("item_type") or "").lower()
        if slot_check == "Weapon" or (type_check == "weapon" and item is not offhand_item):
            w_meta = parse_equipment_metadata(item)
            main_weapon_meta = w_meta
            # Check for new multiplier field first, fall back to old flat atk scaling
            if "multiplier" in w_meta:
                weapon_mult = float(w_meta["multiplier"])
                tier = w_meta.get("tier", 3)
                if tier == 2: weapon_mult *= 1.20
                elif tier == 1: weapon_mult *= 1.45
            else:
                weapon_mult = 1.0
            crit_bonus_from_weapon = float(w_meta.get("crit_bonus", 0.0))
            equipped_weapon_handedness = w_meta.get("handedness", "1H")
            break

    # Loadout Resolution: Dual-Wielding vs Versatile Two-Handed vs Finesse Single-Wield
    if main_weapon_meta and offhand_weapon_meta:
        # Dual-Wielding (1H Main + 1H Off-Hand):
        dual_wield_active = True
        # Off-hand flurry damage bonus (+15% damage multiplier)
        weapon_mult *= 1.15
        # Inherit off-hand weapon's critical bonus
        crit_bonus_from_weapon += float(offhand_weapon_meta.get("crit_bonus", 0.0))
        # Drawback: -3 Accuracy (coordination penalty) and -2 Evasion (aggressive flurry stance)
        flat_acc -= 3
        flat_eva -= 2
    elif equipped_weapon_handedness == "Versatile" and not has_shield and not offhand_weapon_meta:
        # Generalized Versatile Grip Resolution:
        weapon_mult *= 1.15
        crit_bonus_from_weapon += 4.0
        flat_acc += 2
        flat_eva -= 2
        versatile_bonus_applied = True
    elif equipped_weapon_handedness == "1H" and not has_shield and not offhand_weapon_meta:
        # Finesse Single-Wield with free off-hand (+2 EVA agility/balance)
        flat_eva += 2
        finesse_single_wield_applied = True

    # Effective SPECIAL after gear and temporary status effects
    effective_per = max(1, per_ + flat_per)
    effective_cha = max(1, cha + flat_cha)

    # Recalculate base accuracy and arcane power using effective perception
    base_acc = 60 + (effective_per * 4) + (agi * 2)
    base_macc = 60 + (effective_per * 4) + (agi * 2)

    # Recalculate ATK using multiplier (base from SPECIAL + level scaling + flat bonuses)
    level = character.get("level", 1)
    level_bonus = max(0, (level - 1) * 2)
    base_strike_power = 10 + (str_ * 10) + (agi * 2) + level_bonus
    base_arcane_power = 10 + (int_ * 10) + (effective_per * 2) + level_bonus
    final_atk = int(round((base_strike_power + flat_atk) * weapon_mult * (1.0 + mult_atk)))
    final_matk = int(round((base_arcane_power + flat_matk) * weapon_mult * (1.0 + mult_matk)))


    final_acc = int(round(base_acc + flat_acc))
    final_macc = int(round(base_macc + flat_macc))
    final_eva = int(round(base_eva + flat_eva))

    base_crit_success, crit_fail = cd.crit_chances(luk)
    final_crit_success = round(base_crit_success + flat_crit + crit_bonus_from_weapon, 1)

    # DT Aggregation from Armor, Shield, Accessories, and Affixes (gear-provided)
    total_base_dt = 0
    total_type_dt = {}
    gear_dr: Dict[str, float] = {}
    for item in (equipped_items or []):
        if not isinstance(item, dict):
            continue
        from mechanics.combat.equipment import parse_equipment_metadata
        a_meta = parse_equipment_metadata(item)
        mods = a_meta.get("stat_modifiers") or {}
        
        # Base DT from item metadata or stat modifiers
        item_base_dt = a_meta.get("base_dt", a_meta.get("dt_contribution", 0))
        if item_base_dt == 0:
            item_base_dt = mods.get("base_dt", 0)
        item_base_dt += mods.get("dt_bonus", 0)

        total_base_dt += item_base_dt
        
        # Type DT from metadata
        for dtype, dtval in (a_meta.get("type_dt") or {}).items():
            total_type_dt[dtype] = total_type_dt.get(dtype, 0) + dtval
            
        # Magic DT from affixes
        if "magic_dt" in mods:
            total_type_dt["magical"] = total_type_dt.get("magical", 0) + mods["magic_dt"]


        # Ballistic affixes
        if "ballistic_weave" in mods:
            total_type_dt["pistol_round"] = total_type_dt.get("pistol_round", 0) + mods["ballistic_weave"]
            total_type_dt["scatter_shot"] = total_type_dt.get("scatter_shot", 0) + mods["ballistic_weave"]
        if "ceramic_insert" in mods:
            total_type_dt["rifle_round"] = total_type_dt.get("rifle_round", 0) + mods["ceramic_insert"]
            total_type_dt["high_caliber_round"] = total_type_dt.get("high_caliber_round", 0) + mods["ceramic_insert"]
        if "anti_puncture" in mods:
            total_type_dt["arrow"] = total_type_dt.get("arrow", 0) + mods["anti_puncture"]
            total_type_dt["bolt"] = total_type_dt.get("bolt", 0) + mods["anti_puncture"]
        if "ablative_coating" in mods:
            total_type_dt["energy_cell"] = total_type_dt.get("energy_cell", 0) + mods["ablative_coating"]
            total_type_dt["energy"] = total_type_dt.get("energy", 0) + mods["ablative_coating"]

    # Collect gear-based DR% from *_res affixes and omni_res
    _elem_channels = ("fire", "shock", "ice", "poison", "holy", "dark", "magical", "energy", "physical")
    omni = elem_res.get("omni_res", 0) / 100.0
    for ch in _elem_channels:
        res_key = f"{ch}_res"
        ch_res = elem_res.get(res_key, 0) / 100.0
        ch_omni = omni if ch != "physical" else 0.0
        ch_dr = ch_res + ch_omni
        if ch_dr != 0:
            gear_dr[ch] = max(-0.25, min(0.85, ch_dr))

    # Incorporate consumable buff/debuff DT and DR
    total_base_dt += buff_dt
    if dt_degrade_pct > 0:
        scale = max(0.0, 1.0 - min(0.90, dt_degrade_pct))
        total_base_dt = int(round(total_base_dt * scale))
        total_type_dt = {k: int(round(v * scale)) for k, v in total_type_dt.items()}
    total_base_dt = max(0, total_base_dt)

    if buff_dr > 0:
        for ch in ("physical", "magical", "fire", "shock", "ice", "poison", "energy"):
            gear_dr[ch] = min(0.85, gear_dr.get(ch, 0.0) + buff_dr)

    # Add innate DT to the aggregated pool (keyed as "physical_innate" / "magical_innate")
    # These are added into the result dict separately so combat.py can apply them per channel
    final_innate_phys_dt = innate_phys_dt
    final_innate_magic_dt = innate_magic_dt
    # Innate magic DR combines with gear-based magic DR (hard-capped per channel in combat.py)
    final_innate_magic_dr = innate_magic_dr

    result = {
        "atk": final_atk,
        "matk": final_matk,
        "acc": final_acc,
        "macc": final_macc,
        "eva": final_eva,
        "block_chance": int(round(block_chance)),
        "crit_success": final_crit_success,
        "crit_fail": crit_fail,
        "base_atk": base_atk,
        "base_matk": base_matk,
        "base_acc": base_acc,
        "base_macc": base_macc,
        "base_eva": base_eva,
        "bonus_max_hp": bonus_max_hp,
        "bonus_max_mp": bonus_max_mp,
        "hp_regen": hp_regen,
        "mp_regen": mp_regen,
        "weapon_mult": weapon_mult,
        "versatile_stance": "2H" if versatile_bonus_applied else ("1H" if equipped_weapon_handedness == "Versatile" else None),
        "dual_wield": dual_wield_active,
        "offhand_weapon": offhand_weapon_meta,
        "finesse_single_wield": finesse_single_wield_applied,
        "base_dt": total_base_dt,
        "type_dt": total_type_dt,
        "gear_tags": list(gear_tags),
        "tags": list(gear_tags),
        # Innate FNV defense values
        "innate_phys_dt": final_innate_phys_dt,
        "innate_magic_dt": final_innate_magic_dt,
        "innate_magic_dr": final_innate_magic_dr,
        "gear_dr": gear_dr,
        "clothing_suppressed": clothing_suppressed,
        "per": effective_per,
        "cha": effective_cha,
    }
    result.update(elem_atks)
    result.update(elem_res)
    return result


def format_combat_attributes_text(attrs: Dict[str, Any]) -> str:
    """Formats combat attributes for display in Discord embeds or character sheets."""
    line1 = (
        f"⚔️ **ATK:** {attrs['atk']}  |  "
        f"🛡️ **DT:** {attrs.get('base_dt', 0) + attrs.get('innate_phys_dt', 0)}  |  "
        f"🔮 **MATK:** {attrs['matk']}  |  "
        f"✨ **M-DT:** {attrs.get('innate_magic_dt', 0)}"
    )
    line2 = (
        f"🎯 **ACC:** {attrs['acc']}%  |  "
        f"💫 **MACC:** {attrs['macc']}%  |  "
        f"💨 **EVA:** {attrs['eva']}%"
    )
    if attrs.get("block_chance", 0) > 0:
        line2 += f"  |  🛡️ **BLOCK:** {attrs['block_chance']}%"
    elif attrs.get("dual_wield"):
        line2 += "  |  ⚔️ **DUAL-WIELD**"
    elif attrs.get("versatile_stance") == "2H":
        line2 += "  |  🔄 **2H GRIP**"
    elif attrs.get("finesse_single_wield"):
        line2 += "  |  🤺 **FINESSE**"
    lines = [line1, line2]

    # Display active elemental resistances if equipped
    res_parts = []
    if attrs.get("fire_res", 0) > 0:
        res_parts.append(f"🔥 {attrs['fire_res']}%")
    if attrs.get("shock_res", 0) > 0:
        res_parts.append(f"⚡ {attrs['shock_res']}%")
    if attrs.get("ice_res", 0) > 0:
        res_parts.append(f"❄️ {attrs['ice_res']}%")
    if attrs.get("poison_res", 0) > 0:
        res_parts.append(f"🧪 {attrs['poison_res']}%")
    if attrs.get("holy_res", 0) > 0:
        res_parts.append(f"✨ {attrs['holy_res']}%")
    if attrs.get("dark_res", 0) > 0:
        res_parts.append(f"🌑 {attrs['dark_res']}%")
    if attrs.get("omni_res", 0) > 0:
        res_parts.append(f"🌈 {attrs['omni_res']}%")

    if res_parts:
        lines.append("🛡️ **Resistances:** " + " • ".join(res_parts))

    return "\n".join(lines)

