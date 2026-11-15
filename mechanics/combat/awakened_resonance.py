from __future__ import annotations
"""
Awakened Resonance & Anomaly Break Combat Engine for Anomalous Incursions.

Provides deterministic state transitions for:
- Integer 100-Scale Enemy Stability (Minion 60, Standard 100, Elite 140, Boss 200, Rival 80-160)
- Weakness / Catalyst Implant / Breaker / Physical / Earth Tectonic Anchor shred multipliers
- All 9 Attribute Signature Break Payoffs + 1 HP Break Mercy Clamp + +20% ATK Super Break
- 3-Pip (0 MP) Encounter Ultimate economy
- 4 Ability Medium stat-scaling curves & Autonomous Construct decoy lifecycle
- 17 Composable Tier 3 & Tier 5 Resonance Passives
"""

import hashlib
from typing import Any, Dict, List, Optional, Tuple

from mechanics.combat.spells.awakened_kits import (
    ABILITY_MEDIUMS,
    ANOMALOUS_ATTRIBUTES,
    ATTRIBUTE_META,
    COMBAT_ARCHETYPES,
    normalize_anomalous_attribute,
)
from .status_effects import (
    apply_status_effect,
    format_status_badge,
    normalize_status_effect,
)

POSITIVE_BUFF_KEYWORDS: Tuple[str, ...] = (
    "fortified", "enraged", "shield", "ward", "haste", "empower", "barrier", "regen", "+20%", "+25%", "+30%"
)


def _stat_val(actor: Dict[str, Any], code: str, default: int = 5) -> int:
    low = code.lower()
    for k in (code, low, f"{low}_"):
        if k in actor and actor[k] is not None:
            try:
                return int(actor[k])
            except (TypeError, ValueError):
                pass
    stats = actor.get("stats")
    if isinstance(stats, dict):
        for k in (code, low, f"{low}_"):
            if k in stats and stats[k] is not None:
                try:
                    return int(stats[k])
                except (TypeError, ValueError):
                    pass
    return default


def _is_shielded_or_armored(target: Dict[str, Any]) -> bool:
    if int(target.get("temp_hp", 0) or 0) > 0:
        return True
    if target.get("is_armored") or int(target.get("armor_dt", 0) or 0) > 0 or int(target.get("def_bonus", 0) or 0) > 0:
        return True
    tags = [str(t).lower() for t in (target.get("tags") or [])]
    if any(k in t for t in tags for k in ("armor", "shield", "carapace", "golem", "plate", "construct")):
        return True
    for eff in (target.get("status_effects") or []):
        eff_low = format_status_badge(eff).lower()
        if any(k in eff_low for k in ("shield", "ward", "fortified", "barrier", "armor")):
            return True
    return False


def _has_implanted_weakness(target: Dict[str, Any], attr: str) -> bool:
    needle = f"weakness implant ({attr})"
    for eff in (target.get("status_effects") or []):
        if needle in format_status_badge(eff).lower():
            return True
    return False


def init_enemy_stability_profile(enemy: Dict[str, Any], rng: Any = None) -> Dict[str, Any]:
    """Initializes integer 100-scale Stability and 2-3 Weaknesses on an Anomalous Incursions foe."""
    npc_tag = str(enemy.get("npc_tag") or "").lower()
    tags_low = {str(t).lower() for t in (enemy.get("tags") or [])}
    if npc_tag == "civilian" or "civilian" in tags_low:
        enemy["max_stability"] = 0
        enemy["stability"] = 0
        enemy["weaknesses"] = []
        enemy["revealed_weaknesses"] = []
        enemy["hidden_weakness"] = None
        enemy["is_breached"] = False
        enemy["breached_turns_left"] = 0
        return enemy

    rank = str(enemy.get("rank") or "").lower()
    is_boss = bool(enemy.get("is_boss") or rank == "boss")
    is_elite = bool(enemy.get("is_elite") or rank == "elite")
    is_minion = bool(enemy.get("is_minion") or rank == "minion")
    is_rival = bool(npc_tag == "special_agent" or enemy.get("is_rival_agent") or "special_agent" in tags_low)

    if is_rival and not is_boss:
        tier = max(2, min(5, int(enemy.get("tier") or 3)))
        max_stab = {2: 80, 3: 110, 4: 135, 5: 160}[tier]
    elif is_boss:
        max_stab = 200
    elif is_elite:
        max_stab = 140
    elif is_minion:
        max_stab = 60
    else:
        max_stab = 100

    existing_weak = [
        normalize_anomalous_attribute(w)
        for w in (enemy.get("weaknesses") or [])
        if str(w).strip()
    ]
    dedup_weak: List[str] = []
    for w in existing_weak:
        if w in ANOMALOUS_ATTRIBUTES and w not in dedup_weak:
            dedup_weak.append(w)

    if len(dedup_weak) < 2:
        seed_str = f"{enemy.get('name', 'anomaly')}:{max_stab}"
        digest = hashlib.sha256(seed_str.encode("utf-8")).digest()
        want_count = 3 if (is_boss or is_elite) else 2
        idx = 0
        while len(dedup_weak) < want_count:
            cand = (
                rng.choice(ANOMALOUS_ATTRIBUTES)
                if rng is not None and hasattr(rng, "choice")
                else ANOMALOUS_ATTRIBUTES[digest[idx % len(digest)] % len(ANOMALOUS_ATTRIBUTES)]
            )
            idx += 1
            if cand not in dedup_weak:
                dedup_weak.append(cand)
            if idx > 32:
                for fallback_a in ANOMALOUS_ATTRIBUTES:
                    if fallback_a not in dedup_weak:
                        dedup_weak.append(fallback_a)
                        break

    enemy["max_stability"] = int(enemy.get("max_stability") or max_stab)
    if "stability" not in enemy or enemy["stability"] is None:
        enemy["stability"] = enemy["max_stability"]
    enemy["weaknesses"] = dedup_weak
    if (is_boss or is_elite) and len(dedup_weak) >= 2 and "hidden_weakness" not in enemy:
        enemy["hidden_weakness"] = dedup_weak[-1]
        enemy["revealed_weaknesses"] = list(dedup_weak[:-1])
    else:
        enemy.setdefault("hidden_weakness", None)
        enemy.setdefault("revealed_weaknesses", list(dedup_weak))
    enemy.setdefault("is_breached", False)
    enemy.setdefault("breached_turns_left", 0)
    return enemy


def resolve_medium_scaling_stat(
    actor: Dict[str, Any],
    medium: str,
    equipped_weapon: Optional[Dict[str, Any]] = None,
) -> Tuple[str, int, int]:
    """
    Returns (primary_stat_code, effective_power_score, construct_max_hp) for the actor's Medium.
    """
    med = str(medium or "direct_manifestation").strip().lower()
    lvl = max(1, int(actor.get("level") or actor.get("tier") or 1))
    s_str = _stat_val(actor, "STR")
    s_per = _stat_val(actor, "PER")
    s_end = _stat_val(actor, "END")
    s_cha = _stat_val(actor, "CHA")
    s_int = _stat_val(actor, "INT")
    s_agi = _stat_val(actor, "AGI")

    if med == "ordnance_imbuement":
        candidates = [("PER", s_per), ("STR", s_str), ("AGI", s_agi)]
        best_code, best_val = max(candidates, key=lambda x: x[1])
        wpn_bonus = 6
        if isinstance(equipped_weapon, dict):
            meta = equipped_weapon.get("metadata") if isinstance(equipped_weapon.get("metadata"), dict) else equipped_weapon
            wpn_bonus = max(6, int(meta.get("base_damage") or meta.get("atk_bonus") or 10))
        eff = max(10, int(round(best_val * 2.6 + wpn_bonus + lvl * 2)))
        return best_code, eff, 0

    if med == "somatic_overdrive":
        candidates = [("STR", s_str), ("AGI", s_agi), ("END", s_end)]
        best_code, best_val = max(candidates, key=lambda x: x[1])
        eff = max(10, int(round(best_val * 2.7 + s_end * 1.1 + lvl * 2)))
        return best_code, eff, 0

    if med == "autonomous_construct":
        candidates = [("INT", s_int), ("PER", s_per)]
        best_code, best_val = max(candidates, key=lambda x: x[1])
        eff = max(10, int(round(best_val * 2.6 + min(s_int, s_per) * 0.8 + lvl * 2)))
        construct_hp = max(35, 25 + s_end * 8 + lvl * 5)
        return best_code, eff, construct_hp

    # direct_manifestation default
    best_code = "INT" if s_int >= s_cha else "CHA"
    best_val = max(s_int, s_cha)
    sec_val = min(s_int, s_cha)
    eff = max(10, int(round(best_val * 2.9 + sec_val * 0.9 + lvl * 2)))
    return best_code, eff, 0


def compute_stability_shred(
    base_shred: int,
    attack_attr: str,
    attacker_arch: str,
    attacker_attr: str = "",
    target: Optional[Dict[str, Any]] = None,
    catalyst_bonus: float = 0.0,
) -> int:
    """Computes integer Stability shred against an anomaly or Rival Special Agent."""
    if not target or int(target.get("max_stability", 0) or 0) <= 0 or target.get("is_breached"):
        return 0
    if base_shred <= 0:
        return 0

    atk_a = normalize_anomalous_attribute(attack_attr)
    arch = str(attacker_arch or "vanguard").strip().lower()
    weak_list = [normalize_anomalous_attribute(w) for w in (target.get("weaknesses") or [])]
    hits_weakness = (atk_a in weak_list) or _has_implanted_weakness(target, atk_a)

    if target.get("hidden_weakness") and normalize_anomalous_attribute(target.get("hidden_weakness")) == atk_a:
        target["hidden_weakness"] = None
        rev = list(target.get("revealed_weaknesses") or [])
        if atk_a not in rev:
            rev.append(atk_a)
        target["revealed_weaknesses"] = rev

    if hits_weakness:
        mult = 2.0
    elif arch == "breaker":
        mult = 1.6
    elif atk_a == "physical":
        mult = 1.25
    else:
        mult = 1.0

    if atk_a == "earth" and _is_shielded_or_armored(target):
        mult *= 1.25

    total = base_shred * mult * (1.0 + max(0.0, float(catalyst_bonus or 0.0)))
    return max(1, int(round(total)))


def apply_stability_and_break(
    target: Dict[str, Any],
    shred: int,
    breaker_attr: str,
    attacker_atk: int,
    combat_log: Optional[List[str]] = None,
    non_lethal_mode: bool = False,
) -> Dict[str, Any]:
    """
    Applies integer Stability shred, triggers 9-Attribute Signature Break Payoffs on 0 Stability,
    enforces the 1 HP Break Mercy Clamp strictly on `requires_non_lethal_subdue` Break bursts,
    and triggers +20% ATK Super Break when striking an already-BREACHED target.
    """
    if combat_log is None:
        combat_log = []
    attr = normalize_anomalous_attribute(breaker_attr)
    atk_val = max(10, int(attacker_atk or 25))
    max_stab = int(target.get("max_stability", 0) or 0)

    result: Dict[str, Any] = {
        "triggered_break": False,
        "payoff_name": "",
        "payoff_damage": 0,
        "super_break_damage": 0,
        "aoe_splash_damage": 0,
        "chain_damage": 0,
        "squad_heal": 0,
        "bonus_pips": 0,
        "mp_refund": 0,
    }
    if max_stab <= 0:
        return result

    t_name = str(target.get("name") or "Anomaly")

    # Already BREACHED -> Super Break (+20% ATK)
    if target.get("is_breached"):
        sb_dmg = max(1, int(round(atk_val * 0.20)))
        result["super_break_damage"] = sb_dmg
        combat_log.append(f"💥 **SUPER BREAK!** {t_name} suffers +{sb_dmg} resonance trauma while Breached!")
        return result

    cur_stab = int(target.get("stability", max_stab))
    new_stab = max(0, cur_stab - max(0, int(shred or 0)))
    target["stability"] = new_stab
    if new_stab > 0:
        return result

    # Discrete Depletion -> ANOMALY BREACHED!
    target["is_breached"] = True
    target["breached_turns_left"] = 1
    result["triggered_break"] = True

    max_hp = max(1, int(target.get("max_hp") or target.get("hp") or 100))
    pierce_shield = False

    if attr == "fire":
        result["payoff_name"] = "Thermokinetic Detonation"
        result["payoff_damage"] = max(6, int(round(atk_val * 0.65)))
        apply_status_effect(target, "Burned [2 turns]", source="anomaly_break")
    elif attr == "water":
        result["payoff_name"] = "Abyssal Undertow"
        result["payoff_damage"] = max(4, int(round(atk_val * 0.35)))
        result["squad_heal"] = 12
        apply_status_effect(target, "Slowed [2 turns]", source="anomaly_break")
    elif attr == "wind":
        result["payoff_name"] = "Vacuum Shear"
        result["payoff_damage"] = max(5, int(round(atk_val * 0.45)))
        result["aoe_splash_damage"] = max(3, int(round(atk_val * 0.25)))
        apply_status_effect(target, "Exposed [2 turns]", source="anomaly_break")
    elif attr == "earth":
        result["payoff_name"] = "Tectonic Lock"
        result["payoff_damage"] = max(5, int(round(atk_val * 0.40)))
        apply_status_effect(target, "Petrified (Tectonic Lock) [1 turn]", source="anomaly_break")
        apply_status_effect(target, "Grounded (-20% EVA) [2 turns]", source="anomaly_break")
    elif attr == "ice":
        result["payoff_name"] = "Zero-Kelvin Freeze"
        result["payoff_damage"] = max(5, int(round(atk_val * 0.40)))
        apply_status_effect(target, "Frozen [1 turn]", source="anomaly_break")
        apply_status_effect(target, "Shatter Vulnerable (+25% Crit) [1 turn]", source="anomaly_break")
    elif attr == "electric":
        result["payoff_name"] = "Grid Overload"
        result["payoff_damage"] = max(5, int(round(atk_val * 0.45)))
        result["chain_damage"] = max(3, int(round(atk_val * 0.25)))
        apply_status_effect(target, "Grid Overloaded [2 turns]", source="anomaly_break")
    elif attr == "bio":
        result["payoff_name"] = "Spore Rupture"
        result["payoff_damage"] = max(5, int(round(atk_val * 0.40)))
        apply_status_effect(target, "Spore Rupture (-30% DEF, Anti-Heal) [2 turns]", source="anomaly_break")
    elif attr == "physical":
        result["payoff_name"] = "Trauma Rupture"
        result["payoff_damage"] = max(8, int(round(max_hp * 0.12)))
        apply_status_effect(target, "Trauma Bleed [2 turns]", source="anomaly_break")
    else:  # aether
        result["payoff_name"] = "Rift Collapse"
        result["payoff_damage"] = max(6, int(round(atk_val * 0.50)))
        result["bonus_pips"] = 1
        result["mp_refund"] = 8
        pierce_shield = True
        target["status_effects"] = [
            e for e in (target.get("status_effects") or [])
            if normalize_status_effect(e)["category"] != "buff"
            and not any(
                pk in (
                    f"{format_status_badge(e)} "
                    f"{(e.get('metadata') or {}).get('raw_tag', '') if isinstance(e, dict) else e}"
                ).lower()
                for pk in POSITIVE_BUFF_KEYWORDS
            )
        ]

    # Apply payoff burst (respecting temp_hp unless Aether pierces, and 1 HP Mercy Clamp on capture targets)
    dmg = result["payoff_damage"]
    cur_hp = int(target.get("hp", 0) or 0)
    if cur_hp > 0 and dmg > 0:
        rem = dmg
        if not pierce_shield and int(target.get("temp_hp", 0) or 0) > 0:
            thp = int(target.get("temp_hp", 0))
            absorbed = min(thp, rem)
            target["temp_hp"] = thp - absorbed
            rem -= absorbed
        if rem > 0:
            if target.get("requires_non_lethal_subdue") or target.get("delayed_phase_2") or non_lethal_mode:
                target["hp"] = max(1, cur_hp - rem)
            else:
                target["hp"] = max(0, cur_hp - rem)

    emoji = ATTRIBUTE_META[attr]["emoji"]
    combat_log.append(
        f"⚡ **ANOMALY BREACHED!** {t_name}'s Stability collapses — {emoji} **{result['payoff_name']}** deals {dmg} Break damage!"
    )
    return result


def tick_enemy_breach_recovery(
    target: Dict[str, Any],
    combat_log: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Decrements `breached_turns_left`; when the 1-round Breach window closes, refills Stability to 100%
    and fires any `delayed_phase_2` Boss transition that was deferred by Breach Priority.
    """
    if combat_log is None:
        combat_log = []
    info = {"recovered": False, "triggered_delayed_phase_2": False}
    if not target.get("is_breached"):
        return info

    turns_left = int(target.get("breached_turns_left", 1)) - 1
    target["breached_turns_left"] = max(0, turns_left)
    if target["breached_turns_left"] > 0:
        return info

    target["is_breached"] = False
    target["stability"] = int(target.get("max_stability", 100) or 100)
    info["recovered"] = True
    t_name = str(target.get("name") or "Anomaly")
    combat_log.append(f"🔄 **{t_name}** re-stabilizes its anomalous poise!")

    if target.get("delayed_phase_2") and int(target.get("hp", 0) or 0) > 0 and not target.get("phase_2_triggered"):
        target["delayed_phase_2"] = False
        target["phase_2_triggered"] = True
        max_hp = max(1, int(target.get("max_hp") or 100))
        heal_amt = max(1, int(max_hp * 0.20))
        target["hp"] = min(max_hp, int(target.get("hp", 1)) + heal_amt)
        if not any("enraged" in format_status_badge(x).lower() for x in (target.get("status_effects") or [])):
            apply_status_effect(target, "Enraged [3 turns]", source="boss_phase2")
        info["triggered_delayed_phase_2"] = True
        combat_log.append(
            f"🔥 **PHASE 2 SURGE!** **{t_name}** erupts from its Breach state, revitalizing vitality and becoming **Enraged**!"
        )
    return info


def compute_attribute_matchup_modifiers(
    attack_attr: str,
    attacker_actor: Optional[Dict[str, Any]],
    defender: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Evaluates Physical & Aether non-reaction trade-offs, Earth Anchor, and Aether Warden shield neutralization."""
    atk_a = normalize_anomalous_attribute(attack_attr)
    actor = attacker_actor or {}
    dfd = defender or {}

    dfd_tags = {str(t).lower() for t in (dfd.get("tags") or [])}
    is_ethereal = bool(dfd.get("is_ethereal") or "ethereal" in dfd_tags or "spirit" in dfd_tags or "phantom" in dfd_tags)
    is_boss = bool(dfd.get("is_boss") or str(dfd.get("rank") or "").lower() == "boss")

    dt_pierce = 0.25 if atk_a == "physical" else 0.0
    crit_bonus = 0.10 if atk_a == "physical" else 0.0
    pierces_temp_hp = atk_a == "aether"
    outgoing_mult = 1.0

    if atk_a == "physical" and is_ethereal:
        outgoing_mult = 0.65
    elif atk_a == "aether" and (is_ethereal or is_boss):
        outgoing_mult = 1.35

    actor_attr = normalize_anomalous_attribute(actor.get("attribute"), fallback="") if actor.get("attribute") else ""
    actor_arch = str(actor.get("combat_archetype") or "").strip().lower()
    actor_thp = int(actor.get("temp_hp", 0) or 0)

    incoming_rift_mult = 1.0
    if actor_attr == "aether":
        if actor_arch == "warden" and actor_thp > 0:
            incoming_rift_mult = 1.0
        else:
            incoming_rift_mult = 1.15

    return {
        "dt_pierce": dt_pierce,
        "crit_bonus": crit_bonus,
        "pierces_temp_hp": pierces_temp_hp,
        "outgoing_mult": outgoing_mult,
        "incoming_rift_mult": incoming_rift_mult,
        "elem_dr_zero": actor_attr == "physical",
        "immune_knockback_interrupt": actor_attr == "earth",
    }


def get_starting_encounter_pips(tier: int = 1) -> int:
    return 1 if int(tier or 1) >= 4 else 0


def update_encounter_pips(
    current_pips: int,
    hit_landed: bool,
    triggered_break_this_turn: bool,
    cast_ultimate: bool,
    extra_break_pips: int = 0,
) -> int:
    """Updates 0..3 Ultimate Pips (+1/hit, max +1 standard Break bonus/turn, 0 earned on Ult cast)."""
    if cast_ultimate:
        return 0
    gained = (1 if hit_landed else 0) + (1 if triggered_break_this_turn else 0) + max(0, int(extra_break_pips or 0))
    return max(0, min(3, int(current_pips or 0) + gained))


TIER3_ARCHETYPE_PASSIVES: Dict[str, Dict[str, Any]] = {
    "vanguard": {"id": "t3_arch_vanguard_executioner", "name": "Executioner's Momentum", "breach_dmg_bonus": 0.20},
    "catalyst": {"id": "t3_arch_catalyst_overclock", "name": "Harmonic Overclock", "mono_attr_buff_bonus": 0.10},
    "breaker": {"id": "t3_arch_breaker_faultline", "name": "Faultline Seeker", "shred_flat_bonus": 6},
    "warden": {"id": "t3_arch_warden_capacitor", "name": "Hume Capacitor", "shield_strength_mult": 1.25},
}

TIER5_ATTRIBUTE_KEYSTONES: Dict[str, Dict[str, Any]] = {
    "fire": {"id": "t5_attr_fire_cremation", "name": "Cremation Core", "break_payoff_mult": 1.20},
    "water": {"id": "t5_attr_water_abyssal", "name": "Abyssal Pressure", "break_mp_regen": 5},
    "wind": {"id": "t5_attr_wind_supersonic", "name": "Supersonic Shear", "aoe_power_bonus": 0.15},
    "earth": {"id": "t5_attr_earth_continental", "name": "Continental Anchor", "def_bonus_pct": 0.15},
    "ice": {"id": "t5_attr_ice_zero", "name": "Absolute Zero", "frozen_crit_dmg_bonus": 0.25},
    "electric": {"id": "t5_attr_electric_grid", "name": "Dead-Channel Grid", "extra_chain_bounce": 1},
    "bio": {"id": "t5_attr_bio_contagion", "name": "Apex Contagion", "spore_atk_debuff": 0.15},
    "physical": {"id": "t5_attr_physical_monomolecular", "name": "Monomolecular Edge", "extra_dt_pierce": 0.15},
    "aether": {"id": "t5_attr_aether_horizon", "name": "Event Horizon Sovereign", "boss_dmg_bonus": 0.20},
}

TIER5_MEDIUM_KEYSTONES: Dict[str, Dict[str, Any]] = {
    "direct_manifestation": {"id": "t5_med_direct_locus", "name": "Zero-Latency Locus", "mp_discount": 2},
    "ordnance_imbuement": {"id": "t5_med_ordnance_chamber", "name": "Hyper-Velocity Chamber", "extra_imbue_turns": 1},
    "somatic_overdrive": {"id": "t5_med_somatic_gates", "name": "Eight-Gate Overdrive", "stance_eva_bonus": 0.15},
    "autonomous_construct": {"id": "t5_med_construct_sovereign", "name": "Sovereign Automaton", "construct_hp_mult": 1.35},
}


def evaluate_tier_passives(
    actor: Dict[str, Any],
    tier: int,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluates all 17 composable Tier 3 Archetype & Tier 5 Attribute/Medium Keystone passives."""
    t_lvl = int(tier or actor.get("tier") or 1)
    attr = normalize_anomalous_attribute(actor.get("attribute"), fallback="physical")
    arch = str(actor.get("combat_archetype") or "vanguard").strip().lower()
    if arch not in COMBAT_ARCHETYPES:
        arch = "vanguard"
    med = str(actor.get("ability_medium") or "direct_manifestation").strip().lower()
    if med not in ABILITY_MEDIUMS:
        med = "direct_manifestation"

    active_ids: List[str] = []
    active_names: List[str] = []
    modifiers: Dict[str, Any] = {}

    if t_lvl >= 3 and arch in TIER3_ARCHETYPE_PASSIVES:
        p3 = TIER3_ARCHETYPE_PASSIVES[arch]
        active_ids.append(p3["id"])
        active_names.append(p3["name"])
        modifiers.update({k: v for k, v in p3.items() if k not in ("id", "name")})

    if t_lvl >= 5:
        pa = TIER5_ATTRIBUTE_KEYSTONES[attr]
        pm = TIER5_MEDIUM_KEYSTONES[med]
        active_ids.extend([pa["id"], pm["id"]])
        active_names.extend([pa["name"], pm["name"]])
        modifiers.update({k: v for k, v in pa.items() if k not in ("id", "name")})
        modifiers.update({k: v for k, v in pm.items() if k not in ("id", "name")})

    return {
        "active_passive_ids": active_ids,
        "active_passive_names": active_names,
        "modifiers": modifiers,
    }


def ensure_autonomous_construct(
    actor: Dict[str, Any],
    living_allies: List[Dict[str, Any]],
    force_resummon: bool = False,
    current_npcs: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Spawns or re-summons a combat-only `is_summon=True` Autonomous Construct decoy for an
    `autonomous_construct` agent. Never enters social `contacts` or dialogue.
    """
    med = str(actor.get("ability_medium") or "").strip().lower()
    if med != "autonomous_construct":
        return None

    owner_key = str(actor.get("id") or actor.get("name") or "player")
    owner_uid = actor.get("user_id") or actor.get("id")
    attr = normalize_anomalous_attribute(actor.get("attribute"), fallback="aether")
    _, eff_pow, max_hp = resolve_medium_scaling_stat(actor, med)
    t_passives = evaluate_tier_passives(actor, int(actor.get("tier") or actor.get("level") or 1))
    hp_mult = float(t_passives["modifiers"].get("construct_hp_mult", 1.0))
    max_hp = max(35, int(round(max_hp * hp_mult)))

    search_pool = list(living_allies) + (list(current_npcs) if isinstance(current_npcs, list) else [])
    existing = next(
        (
            a for a in search_pool
            if isinstance(a, dict)
            and a.get("is_summon")
            and (
                a.get("summoner_key") == owner_key
                or (owner_uid is not None and a.get("owner_id") == owner_uid)
            )
        ),
        None,
    )
    if existing is not None:
        if int(existing.get("hp", 0) or 0) > 0:
            if existing not in living_allies:
                living_allies.append(existing)
            if isinstance(current_npcs, list) and existing not in current_npcs:
                current_npcs.append(existing)
            return existing
        if not force_resummon:
            return None
        existing["hp"] = max_hp
        existing["max_hp"] = max_hp
        existing["status_effects"] = []
        if existing not in living_allies:
            living_allies.append(existing)
        if isinstance(current_npcs, list) and existing not in current_npcs:
            current_npcs.append(existing)
        return existing

    am = ATTRIBUTE_META[attr]
    construct = {
        "name": f"{am['adj']} Construct",
        "is_summon": True,
        "is_autonomous_construct": True,
        "summoner_key": owner_key,
        "owner_id": owner_uid,
        "attribute": attr,
        "combat_archetype": actor.get("combat_archetype") or "vanguard",
        "level": max(1, int(actor.get("level") or actor.get("tier") or 1)),
        "hp": max_hp,
        "max_hp": max_hp,
        "atk": max(10, int(round(eff_pow * 0.55))),
        "taunt_weight": 2.0,
        "queued_windup": None,
        "status_effects": [],
    }
    living_allies.append(construct)
    if isinstance(current_npcs, list) and construct not in current_npcs:
        current_npcs.append(construct)
    return construct


def get_actor_resonance_pips(session: Optional[Dict[str, Any]], user_id: Any = None) -> int:
    """Safely extracts an actor's clamped [0, 3] Resonance Pips whether stored as per-actor dict or scalar int."""
    if not isinstance(session, dict):
        return 0
    raw = session.get("player_resonance_pips", 0)
    if isinstance(raw, dict):
        val = None
        if user_id is not None:
            if str(user_id) in raw:
                val = raw.get(str(user_id), 0)
            elif user_id in raw:
                val = raw.get(user_id, 0)
            else:
                try:
                    int_uid = int(user_id)
                    if int_uid in raw:
                        val = raw.get(int_uid, 0)
                except (TypeError, ValueError):
                    pass
        if val is None:
            if "0" in raw and user_id in (None, 0, "0"):
                val = raw.get("0", 0)
            elif 0 in raw and user_id in (None, 0, "0"):
                val = raw.get(0, 0)
            elif raw:
                val = next(iter(raw.values()))
            else:
                val = 0
        try:
            return max(0, min(3, int(val or 0)))
        except (TypeError, ValueError):
            return 0
    try:
        return max(0, min(3, int(raw or 0)))
    except (TypeError, ValueError):
        return 0
