from __future__ import annotations
"""
Combat formulas, DC calculation, damage modifiers, and status effect logic.
"""
from typing import Optional, Dict, Any, List, Tuple
import random
import re

def calculate_opposed_dc(player_stat_val: int, enemy_stat_val: int, player_luk: int = 5) -> int:
    """Calculates dynamic DC requirement (2-12) based on Player Stat vs Enemy Stat."""
    luk_bonus = max(0, (player_luk - 5) // 2)
    diff = enemy_stat_val - player_stat_val
    base_dc = 6 + diff - luk_bonus
    return max(2, min(12, base_dc))

TYPE_AFFINITIES: dict[str, dict[str, float]] = {
    "slash": {
        "plate": 0.70, "chainmail": 0.70, "ceramic": 0.75, "composite": 0.75,
        "magic_robe": 1.30, "unarmored": 1.30, "clothes": 1.30, "leather": 1.00, "kevlar": 1.00
    },
    "thrust": {
        "chainmail": 1.30, "leather": 1.15, "plate": 0.80, "composite": 0.80,
        "magic_robe": 1.20, "unarmored": 1.20, "clothes": 1.20, "ceramic": 0.85
    },
    "hack": {
        "plate": 1.20, "chainmail": 1.30, "leather": 1.10, "composite": 1.10,
        "magic_robe": 1.15, "unarmored": 1.20, "clothes": 1.20
    },
    "blunt": {
        "plate": 1.20, "chainmail": 1.30, "ceramic": 1.25, "composite": 1.15,
        "magic_robe": 1.00, "unarmored": 1.10, "clothes": 1.10, "leather": 1.10
    },
    "ranged": {
        "kevlar": 0.70, "plate": 0.75, "composite": 0.70,
        "magic_robe": 1.30, "unarmored": 1.30, "clothes": 1.30, "chainmail": 0.80, "leather": 0.90
    },
    "explosive": {
        "power_armor": 0.80, "composite": 0.75, "unarmored": 1.40,
        "magic_robe": 1.40, "clothes": 1.40, "leather": 1.25
    },
    "magical": {
        "magic_robe": 0.60, "leather": 1.00, "chainmail": 1.00, "plate": 1.10, "unarmored": 1.20
    },
    "shock": {
        "plate": 1.40, "chainmail": 1.30, "magic_robe": 0.60, "power_armor": 1.30, "unarmored": 1.10
    },
    "lightning": {
        "plate": 1.40, "chainmail": 1.30, "magic_robe": 0.60, "power_armor": 1.30, "unarmored": 1.10
    },
    "fire": {
        "leather": 1.25, "magic_robe": 0.60, "unarmored": 1.30, "clothes": 1.30, "plate": 0.90
    },
    "ice": {
        "leather": 0.85, "magic_robe": 0.65, "plate": 1.20, "unarmored": 1.20
    },
    "water": {
        "magic_robe": 0.70, "plate": 1.10, "unarmored": 1.10
    },
    "earth": {
        "magic_robe": 1.10, "plate": 0.80, "chainmail": 0.90, "unarmored": 1.20
    },
    "wind": {
        "magic_robe": 0.70, "plate": 0.80, "leather": 1.10, "unarmored": 1.20
    },
    "poison": {
        "plate": 0.70, "power_armor": 0.50, "unarmored": 1.40, "clothes": 1.40, "magic_robe": 1.00
    },
    "holy": {
        "magic_robe": 0.60, "unarmored": 1.10, "plate": 0.90
    },
    "dark": {
        "magic_robe": 0.60, "plate": 1.20, "unarmored": 1.20
    },
    "energy": {
        "power_armor": 0.80, "composite": 0.80, "magic_robe": 0.70, "ceramic": 0.80
    }
}

DAMAGE_TYPE_ALIASES: dict[str, set[str]] = {
    "slash": {"slash", "slashing", "hack"},
    "slashing": {"slash", "slashing", "hack"},
    "hack": {"slash", "slashing", "hack"},
    "thrust": {"thrust", "pierce", "piercing", "stabbing"},
    "pierce": {"thrust", "pierce", "piercing", "stabbing"},
    "piercing": {"thrust", "pierce", "piercing", "stabbing"},
    "stabbing": {"thrust", "pierce", "piercing", "stabbing"},
    "blunt": {"blunt", "strike", "crush", "crushing", "slam", "bludgeoning"},
    "bludgeoning": {"blunt", "strike", "crush", "crushing", "slam", "bludgeoning"},
    "ranged": {"ranged", "ballistic", "shot", "bullet", "arrow"},
    "ballistic": {"ranged", "ballistic", "shot", "bullet", "arrow"},
    "fire": {"fire", "flame", "burn", "heat"},
    "ice": {"ice", "cold", "frost", "chill"},
    "cold": {"ice", "cold", "frost", "chill"},
    "frost": {"ice", "cold", "frost", "chill"},
    "shock": {"shock", "lightning", "electric", "electricity"},
    "lightning": {"shock", "lightning", "electric", "electricity"},
    "poison": {"poison", "toxic", "venom", "acid", "corrosive"},
    "acid": {"poison", "toxic", "venom", "acid", "corrosive"},
    "holy": {"holy", "radiant", "divine", "sacred"},
    "dark": {"dark", "shadow", "necrotic", "void", "evil"},
    "energy": {"energy", "plasma", "laser"},
    "physical": {"physical"},
    "magical": {"magical", "arcane", "sorcery"}
}

def get_damage_type_aliases(dmg_type: str) -> set[str]:
    """Returns a set of canonical and equivalent damage/attack type names."""
    if not dmg_type:
        return set()
    dt = str(dmg_type).strip().lower()
    return DAMAGE_TYPE_ALIASES.get(dt, {dt})

def matches_damage_type(tag_list: list, *incoming_types: str) -> bool:
    """Checks if any incoming damage/attack type matches any tag in tag_list, accounting for aliases."""
    if not tag_list:
        return False
    target_tags = {str(t).strip().lower() for t in tag_list if t}
    for inc in incoming_types:
        if not inc:
            continue
        aliases = get_damage_type_aliases(inc)
        if target_tags & aliases:
            return True
    return False


def get_attack_type_multiplier(attack_types: list[str], armor_meta: dict) -> float:
    """Calculates tactical matchup multiplier for physical attack types (slash, thrust, blunt, ranged) vs armor."""
    armor_type = armor_meta.get("armor_type", "medium").lower()
    mults = []
    for atk_t in attack_types:
        atk_key = atk_t.lower()
        if atk_key in TYPE_AFFINITIES and armor_type in TYPE_AFFINITIES[atk_key]:
            mults.append(TYPE_AFFINITIES[atk_key][armor_type])
    return (sum(mults) / len(mults)) if mults else 1.0


def get_elemental_multiplier(
    damage_types: dict[str, float],
    armor_meta: dict,
    defender_attrs: Optional[dict] = None
) -> float:
    """
    Returns the TYPE_AFFINITIES matchup multiplier for elemental/energy vs armor class.

    NOTE: Resistance (DR%) from *_res affixes is no longer applied here.
    It is now consumed in the unified FNV DR→DT→Floor pipeline inside _apply_dt().
    This function only returns the base affinity multiplier (e.g. shock vs plate = 1.4×).
    """
    armor_type = armor_meta.get("armor_type", "medium").lower() if armor_meta else "medium"
    mults = []
    for dmg_t in damage_types:
        dmg_key = dmg_t.lower()
        base_m = TYPE_AFFINITIES.get(dmg_key, {}).get(armor_type, 1.0)
        mults.append(base_m)
    return (sum(mults) / len(mults)) if mults else 1.0



def try_inflict_status(target: dict, target_attrs: dict, status_str: str, combat_log: Optional[list] = None) -> bool:
    """
    Inflicts a status effect on the target, checking for defensive gear tag immunities
    (e.g. Hazmat / gas_mask repelling toxic, corrosive, acid, poison, or radiation hazards).
    Returns True if applied, False if repelled.
    """
    status_lower = status_str.lower()
    target_tags = set(target_attrs.get("tags", [])) | set(target_attrs.get("gear_tags", []))
    for eff in target.get("status_effects", []):
        if isinstance(eff, str):
            for part in eff.lower().split():
                target_tags.add(part)
                
    is_toxic = any(k in status_lower for k in ("poison", "toxic", "acid", "corros", "gas", "suffocat", "chemical", "radiation", "fallout"))
    if is_toxic:
        hazmat_active = any(t in target_tags for t in ("hazmat", "gas_mask", "gas_immune", "environmental_isolation", "sealed_environment"))
        if hazmat_active:
            target_name = target.get("name", "The target")
            if combat_log is not None:
                combat_log.append(f"🛡️ **{target_name}**'s sealed Hazmat gear repelled the toxic hazard (*{status_str.split('[')[0].strip()}*)!")
            return False
    cur_eff = target.get("status_effects")
    if isinstance(cur_eff, str):
        try:
            import json
            target["status_effects"] = json.loads(cur_eff) if cur_eff.strip().startswith("[") else ([cur_eff] if cur_eff.strip() else [])
        except Exception:
            target["status_effects"] = [cur_eff] if cur_eff.strip() else []
    elif not isinstance(cur_eff, list):
        target["status_effects"] = []
    target["status_effects"].append(status_str)
    return True


def calculate_tactical_damage(
    attacker_attrs: dict,
    defender_attrs: dict,
    weapon_meta: dict,
    armor_meta: dict,
    tier: str = "success",
    attacker_level: int = 1,
    defender_max_hp: int = 100,
    is_enemy_attacker: bool = False,
    attack_type: Optional[str] = None,
    stance: Optional[str] = None
) -> dict:
    """
    Unified 4-Phase Combat Resolution:
    1. Hit Check & Tier Scaling
    2. Shield Block Check
    3. Core ATK vs DEF & MATK vs MDEF base calculation
    4. Tactical Type Matchup (Attack Types vs Armor Class)
    5. Armor Penetration & Reactive Tag Synergies
    """
    if tier in ("crit_fail", "fail", "failure"):
        return {"damage": 0, "base_damage": 0, "blocked": False, "hit": False, "matchup_mult": 1.0, "details": "Miss"}

    atk = attacker_attrs.get("atk", 22)
    matk = attacker_attrs.get("matk", 22)
    def_ = defender_attrs.get("def", 22)
    mdef = defender_attrs.get("mdef", 22)
    block_chance = defender_attrs.get("block_chance", 0)

    # Collect tags from attacker and defender
    attacker_tags = set(attacker_attrs.get("tags", [])) | set(attacker_attrs.get("gear_tags", []))
    defender_tags = set(defender_attrs.get("tags", [])) | set(defender_attrs.get("gear_tags", []))
    w_tags = weapon_meta.get("tags", {})
    if isinstance(w_tags, dict):
        for v in w_tags.values():
            if isinstance(v, list):
                for x in v: attacker_tags.add(str(x).lower())
            elif isinstance(v, str):
                attacker_tags.add(v.lower())
    elif isinstance(w_tags, list):
        for x in w_tags: attacker_tags.add(str(x).lower())
    for t in weapon_meta.get("special_traits", []):
        attacker_tags.add(str(t).lower())

    # Tag Synergy: Precision / Optics (negates enemy evasion buffs, reduces glancing penalty)
    has_precision = any(t in attacker_tags for t in ("precision", "optics", "hud", "smart_link"))

    # Resolve active attack profile
    profiles = weapon_meta.get("attack_profiles") or {}
    all_attack_types = weapon_meta.get("attack_types", ["slash"])
    active_type = attack_type if attack_type in all_attack_types else (all_attack_types[0] if all_attack_types else "slash")
    
    profile = profiles.get(active_type)
    if profile:
        chosen_dmg_type = profile.get("damage_type", "physical")
        profile_mult = profile.get("multiplier", 1.0)
    else:
        chosen_dmg_type = list(weapon_meta.get("damage_types", {"physical": 1.0}).keys())[0]
        profile_mult = weapon_meta.get("multiplier", 1.0)

    # Tag Synergy: Brawler / Unarmed (+25% strike damage with fist/wraps/unarmed)
    w_arch = str(weapon_meta.get("archetype", "")).lower()
    is_unarmed_weapon = w_arch in ("unarmed", "fists", "cloth_wraps", "brass_knuckles", "fist") or "unarmed" in attacker_tags
    has_brawler = "brawler" in attacker_tags
    brawler_synergy_active = False
    if is_unarmed_weapon and has_brawler:
        profile_mult *= 1.25
        brawler_synergy_active = True

    is_magical = chosen_dmg_type in ("magical", "energy", "fire", "shock", "ice", "holy", "dark", "poison", "acid")
    phys_mult = get_attack_type_multiplier([active_type], armor_meta)
    elem_mult = get_elemental_multiplier({chosen_dmg_type: 1.0}, armor_meta, defender_attrs)

    target_immunities = defender_attrs.get("immunities", [])
    target_resistances = defender_attrs.get("resistances", [])
    target_weaknesses = defender_attrs.get("weaknesses", [])

    is_immune = matches_damage_type(target_immunities, chosen_dmg_type, active_type)
    if matches_damage_type(target_resistances, chosen_dmg_type, active_type):
        phys_mult *= 0.5
        elem_mult *= 0.5
    if matches_damage_type(target_weaknesses, chosen_dmg_type, active_type):
        phys_mult *= 1.5
        elem_mult *= 1.5

    # Projectile type resolution
    proj_type = weapon_meta.get("projectile_type") if active_type == "ranged" else None

    # FNV Damage Threshold Resolution (from armor + gear DT aggregation)
    base_dt = armor_meta.get("base_dt", 0)
    type_dt_map = armor_meta.get("type_dt", {})

    # Pull innate DT and DR values from defender attributes
    innate_phys_dt = defender_attrs.get("innate_phys_dt", 0)
    innate_magic_dt = defender_attrs.get("innate_magic_dt", 0)
    innate_magic_dr = defender_attrs.get("innate_magic_dr", 0.0)
    gear_dr: dict = defender_attrs.get("gear_dr", {})

    def _apply_dt(raw: float, damage_type: str, active_proj: Optional[str] = None) -> tuple[float, bool]:
        """
        Unified FNV DR → DT → Floor pipeline with Armor Penetration.
        Armor Penetration is strictly capped at 75% maximum (0.75).
        """
        # Step 1: Resolve total DR for this damage channel
        is_elem = damage_type in ("magical", "fire", "shock", "ice", "poison", "holy", "dark", "energy", "acid")
        if is_elem:
            ch_gear_dr = gear_dr.get(damage_type, 0.0)
            total_dr = max(-0.25, min(0.85, ch_gear_dr + innate_magic_dr))
        else:
            ch_gear_dr = gear_dr.get(damage_type, gear_dr.get("physical", 0.0))
            total_dr = max(-0.25, min(0.85, ch_gear_dr))
        damage_after_dr = raw * (1.0 - total_dr)

        # Step 2: Resolve effective DT (gear armor + innate SPECIAL)
        if active_proj and active_proj in type_dt_map:
            gear_dt = type_dt_map[active_proj]
        else:
            gear_dt = type_dt_map.get(damage_type, base_dt)

        if is_elem:
            effective_dt = gear_dt + innate_magic_dt
        else:
            effective_dt = gear_dt + innate_phys_dt

        # Armor Penetration resolution (strictly capped at 75% max = 0.75)
        raw_ap = float(weapon_meta.get("armor_penetration", weapon_meta.get("armor_piercing", 0.0)))
        if raw_ap <= 0:
            raw_ap = float(weapon_meta.get("stat_modifiers", {}).get("armor_penetration", 0.0))
        ap_ratio = min(0.75, max(0.0, raw_ap))
        if ap_ratio > 0:
            effective_dt = max(0.0, effective_dt * (1.0 - ap_ratio))

        # Step 3: Apply DT with bleed-through floor (30% if precision, 20% standard)
        penetrating = damage_after_dr - effective_dt
        floor_damage = raw * (0.30 if has_precision else 0.20)
        is_glancing = penetrating <= floor_damage
        return max(floor_damage, penetrating), is_glancing

    # Check for elemental conversion on weapon
    convert_pct = float(weapon_meta.get("elem_convert_pct", 0.0))
    convert_type = weapon_meta.get("elem_convert_type")
    if convert_pct <= 0:
        stat_mods = weapon_meta.get("stat_modifiers", {})
        for sm_k, sm_v in stat_mods.items():
            if sm_k.endswith("_convert") and float(sm_v) > 0:
                convert_type = sm_k.split("_")[0]
                convert_pct = float(sm_v)
                break

    if is_enemy_attacker:
        target_hp = max(30, defender_max_hp)
        offensive_stat = matk if is_magical else atk
        stat_mult = max(0.60, min(1.60, float(offensive_stat) / 20.0))
        base_incoming = ((target_hp * random.uniform(0.11, 0.16)) + ((attacker_level or 1) * 0.75)) * stat_mult
        raw_incoming = base_incoming * (elem_mult if is_magical else phys_mult)
        net_after_dt, is_glancing = _apply_dt(raw_incoming, chosen_dmg_type, active_proj=proj_type)
        base_dmg = max(2.0, net_after_dt)
        base_dmg = min(base_dmg, target_hp * 0.25)  # keep safety ceiling
    else:
        # Player -> Monster: use active attack profile multiplier
        strike_stat = matk if is_magical else atk
        base_w_mult = max(0.1, float(weapon_meta.get("multiplier", 1.0)))
        adjusted_stat = float(strike_stat) * (profile_mult / base_w_mult)

        if convert_pct > 0 and convert_type:
            phys_portion = max(0.0, 1.0 - convert_pct)
            raw_phys = max(1.0, adjusted_stat * phys_portion * phys_mult)
            net_phys, is_glancing_p = _apply_dt(raw_phys, chosen_dmg_type, active_proj=proj_type)

            elem_mult_conv = get_elemental_multiplier({convert_type: 1.0}, armor_meta, defender_attrs)
            raw_elem = max(1.0, adjusted_stat * convert_pct * elem_mult_conv)
            net_elem, is_glancing_e = _apply_dt(raw_elem, convert_type)

            net_after_dt = net_phys + net_elem
            is_glancing = is_glancing_p and is_glancing_e
        else:
            raw_attack = max(2.0, adjusted_stat * (elem_mult if is_magical else phys_mult))
            net_after_dt, is_glancing = _apply_dt(raw_attack, chosen_dmg_type, active_proj=proj_type)

        base_dmg = max(6.0, net_after_dt * 0.75 + (attacker_level * 2.2))

        # Versatile 2H Stance strike bonus (+15% damage)
        is_versatile_2h = (stance == "2H")
        if is_versatile_2h:
            base_dmg *= 1.15

        # Dual-Wield Flurry bonus (+15% damage)
        is_dual_wield = (stance == "dual_wield")
        if is_dual_wield:
            base_dmg *= 1.15

        # Tag Synergy: Stealth / Silent Step (Ambush Strike +20% on Turn 1)
        has_stealth = any(t in attacker_tags for t in ("stealth", "silent_step"))
        turn_one = attacker_attrs.get("combat_turn", 1) <= 1
        is_ambush = bool(attacker_attrs.get("is_ambush") or (has_stealth and turn_one))
        if is_ambush:
            base_dmg *= 1.20

    effective_matchup = elem_mult if is_magical else phys_mult

    if tier == "crit_success":
        tier_mult = random.uniform(1.35, 1.60)
    elif tier == "success":
        tier_mult = random.uniform(0.90, 1.10)
    elif tier in ("fail", "failure"):
        tier_mult = random.uniform(0.15, 0.30)
    else:
        tier_mult = 1.0

    final_dmg = base_dmg * tier_mult

    is_blocked = False
    if block_chance > 0 and tier != "crit_success":
        if random.randint(1, 100) <= block_chance:
            is_blocked = True
            final_dmg *= 0.40  # Shield absorbs 60% of damage

    final_damage_int = max(1 if tier in ("success", "crit_success") else 0, int(round(final_dmg)))
    
    if is_immune:
        final_damage_int = 0
        effective_matchup = 0.0
        
    if is_enemy_attacker and tier in ("success", "crit_success"):
        max_cap = int(round(defender_max_hp * (0.30 if tier == "crit_success" else 0.22)))
        final_damage_int = min(final_damage_int, max(4, max_cap))

    # Tag Synergy: Tank / Stomp counter-stagger on block or glancing blow (25% chance)
    has_tank = any(t in defender_tags for t in ("tank", "stomp", "heavy", "fortress"))
    stagger_inflicted = False
    if has_tank and (is_blocked or is_glancing) and tier != "crit_fail":
        if random.random() < 0.25:
            stagger_inflicted = True

    raw_ap = float(weapon_meta.get("armor_penetration", weapon_meta.get("armor_piercing", 0.0)))
    if raw_ap <= 0:
        raw_ap = float(weapon_meta.get("stat_modifiers", {}).get("armor_penetration", 0.0))
    final_ap = min(0.75, max(0.0, raw_ap))

    return {
        "damage": final_damage_int,
        "base_damage": int(round(base_dmg)),
        "blocked": is_blocked,
        "hit": True,
        "matchup_mult": effective_matchup,
        "glancing_strike": is_glancing,
        "ap_ratio": final_ap,
        "brawler_synergy": brawler_synergy_active,
        "ambush_strike": is_ambush if not is_enemy_attacker else False,
        "versatile_2h": is_versatile_2h if not is_enemy_attacker else False,
        "dual_wield": (stance == "dual_wield") if not is_enemy_attacker else False,
        "stagger_inflicted": stagger_inflicted,
        "details": f"{final_damage_int} dmg (Matchup: {effective_matchup:.2f}x)"
    }



def calculate_turn_damage(action: dict, player_stats: dict, monster_stats: dict) -> tuple[int, int]:
    """Resolves opposed turn damage using tactical calculation."""
    res = calculate_tactical_damage(
        player_stats,
        monster_stats,
        weapon_meta={},
        armor_meta={},
        tier="success"
    )
    enemy_damage = res["damage"]
    player_damage = max(0, int(monster_stats.get("ATK", 10) * 0.5))
    return max(0, enemy_damage), max(0, player_damage)

def tick_status_timers(entity: dict) -> dict:
    """
    Hybrid Status Effect Timer System & DoT Lifecycle.
    Decrements turn timers on any status effect tagged as "<effect> [N turns]".
    Applies DoT damage (Burn, Poison, Bleed) and removes effects when timer reaches 0.
    Attaches timers to new un-timed effects (default 2 turns).
    Mutates entity['status_effects'] in-place and returns it.
    """
    import re
    raw = entity.get("status_effects")
    if not raw:
        return entity

    if isinstance(raw, str):
        try:
            import json
            effects = json.loads(raw)
        except Exception:
            effects = [raw]
    else:
        effects = list(raw)

    new_effects = []
    total_dot = 0
    for effect in effects:
        if not isinstance(effect, str) or not effect.strip():
            continue
        effect = effect.strip()

        # Apply DoT damage
        eff_lower = effect.lower()
        if "burn" in eff_lower or "ignite" in eff_lower:
            total_dot += 8
        elif "poison" in eff_lower or "venom" in eff_lower:
            total_dot += 10
        elif "bleed" in eff_lower:
            total_dot += 6

        # Check if timer tag already exists: "Stunned [2 turns]"
        match = re.search(r"\s*\[(\d+)\s*turns?\]$", effect, re.IGNORECASE)
        if match:
            turns = int(match.group(1)) - 1
            base = effect[:match.start()].strip()
            if turns > 0:
                new_effects.append(f"{base} [{turns} turn{'s' if turns != 1 else ''}]")
            # If turns == 0: effect expired, drop it
        else:
            # New effect without timer - attach default 2-turn timer
            new_effects.append(f"{effect} [2 turns]")

    if total_dot > 0:
        temp = entity.get("temp_hp", 0)
        actual = total_dot
        if temp > 0:
            if temp >= total_dot:
                entity["temp_hp"] = temp - total_dot
                actual = 0
            else:
                actual = total_dot - temp
                entity["temp_hp"] = 0
        entity["hp"] = max(0, entity.get("hp", 0) - actual)

    entity["status_effects"] = new_effects
    return entity


