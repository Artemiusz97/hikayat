"""mechanics/combat/damage.py

Centralized damage mutation and intercept engine for Hikayat's Phase 2 Unified Combatant Architecture.
Handles Damage Thresholds, Temp HP absorption, Universal 1 HP Mercy Clamps, and True Execute Breach windows.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .status_effects import apply_status_effect


def apply_damage_to_combatant(
    target: Dict[str, Any],
    dmg: int,
    attacker: Optional[Dict[str, Any]] = None,
    combat_log: Optional[List[str]] = None,
    is_anom_combat: bool = False,
    non_lethal_mode: bool = False,
    pierce_temp_hp: bool = False,
) -> int:
    """Applies incoming damage to any combatant (Player, Companion, or Enemy) with unified rules:
    
    1. Breach Vulnerability: +35% damage if defender is Breached in Anomalous combat.
    2. Temp HP Absorption: Absorbs damage before reducing core HP.
    3. Universal 1 HP Mercy Clamp & Subdue: If non-lethal is active or target requires subdue,
       ally attacks clamp defender at 1 HP with 'is_subdued_ready' flag.
    4. Boss Phase 2 & True Execute Window:
       - If lethal damage strikes during an Anomalous Breach, boss dies outright (Phase 2 bypassed).
       - If non-lethal damage strikes during Breach, Phase 2 is delayed until Breach expires.
       - Otherwise, dropping below 50% triggers standard Phase 2 surge (+20% heal, Enraged, Stability reset).
    5. Clean HP floor clamp at 0.
    """
    if not isinstance(target, dict) or dmg <= 0:
        return 0
    curr_hp = int(target.get("hp", target.get("max_hp", 100)) or 0)
    if curr_hp <= 0:
        return 0

    # 1. Anomalous Breach Damage Amplification
    if is_anom_combat and target.get("is_breached") and not target.get("_breached_this_round"):
        dmg = max(1, int(round(dmg * 1.35)))

    # Status Effect Damage Taken Multipliers (e.g. Staggered +25% damage taken)
    stagger_mult = 1.0
    for eff in (target.get("status_effects") or []):
        if isinstance(eff, dict):
            meta = eff.get("metadata") or {}
            if meta.get("damage_taken_mult"):
                stagger_mult *= float(meta["damage_taken_mult"])
            elif meta.get("stagger_vulnerable"):
                stagger_mult *= 1.25
            elif "stagger" in str(eff.get("name", "")).lower():
                stagger_mult *= 1.25
        elif isinstance(eff, str) and "stagger" in eff.lower():
            stagger_mult *= 1.25
    if stagger_mult > 1.0:
        dmg = max(1, int(round(dmg * stagger_mult)))

    # 2. Temp HP Absorption
    temp_hp = int(target.get("temp_hp", 0) or 0)
    actual_dmg = dmg
    if temp_hp > 0 and not pierce_temp_hp:
        if temp_hp >= dmg:
            target["temp_hp"] = temp_hp - dmg
            return 0
        else:
            actual_dmg = dmg - temp_hp
            target["temp_hp"] = 0

    max_hp = int(target.get("max_hp", 100) or 100)
    tier_rank = int(target.get("tier_rank", 1) or 1)
    is_boss = bool(tier_rank >= 5 or target.get("is_boss"))
    phase_triggered = bool(target.get("phase_2_triggered", False))

    # 3. Universal 1 HP Mercy Clamp & Subdue (Cycle 1 & Cycle 2 Locked Decisions)
    is_ai_ally = bool(
        attacker
        and (
            attacker.get("entity_type") in ("companion", "construct")
            or attacker.get("_is_party_npc")
            or attacker.get("is_summon")
            or attacker.get("is_autonomous_construct")
        )
    )
    is_attacker_ally = (
        attacker is None
        or attacker.get("team") == "ally"
        or attacker.get("entity_type") in ("player", "companion", "construct")
    )
    requires_subdue = bool(
        non_lethal_mode
        or target.get("sparring")
        or (attacker and attacker.get("is_non_lethal"))
        or (target.get("requires_non_lethal_subdue") and is_ai_ally)
    )

    if requires_subdue and is_attacker_ally:
        if (curr_hp - actual_dmg) < 1:
            actual_dmg = max(0, curr_hp - 1)
            target["is_subdued_ready"] = True
            target["is_subdued"] = True
            target["hp"] = max(1, curr_hp - actual_dmg)
            if combat_log is not None and not target.get("_subdue_logged"):
                target["_subdue_logged"] = True
                atk_name = attacker.get("name", "Ally") if attacker else "Ally"
                t_name = target.get("name", "Target")
                combat_log.append(
                    f"🎯 **{atk_name}** held back their strike! **{t_name}** was incapacitated and cornered at 1 HP!"
                )
            return actual_dmg

    new_hp = curr_hp - actual_dmg

    # 4. Boss Phase 2 & True Execute Window (Cycle 3 Locked Decision)
    if is_boss and not phase_triggered and (new_hp < max_hp * 0.5):
        if is_anom_combat and (target.get("_will_breach_this_hit") or target.get("is_breached")):
            if new_hp <= 0:
                target["hp"] = 0
                target["phase_2_bypassed"] = True
                target["phase_2_triggered"] = True
                if combat_log is not None:
                    atk_name = attacker.get("name", "Hero") if attacker else "Hero"
                    b_name = target.get("name", "Boss")
                    combat_log.append(
                        f"💥 **BREACH EXECUTE!** **{atk_name}** shattered **{b_name}** during the Breach window! Phase 2 was completely bypassed!"
                    )
                return actual_dmg
            else:
                was_delayed = bool(target.get("delayed_phase_2"))
                target["delayed_phase_2"] = True
                target["hp"] = new_hp
                if not was_delayed and combat_log is not None:
                    b_name = target.get("name", "Boss")
                    combat_log.append(
                        f"⚡ **BREACH OVERRIDES PHASE 2!** **{b_name}**'s Stability shatters before it can surge — Phase 2 delayed for 1 Breach round!"
                    )
                return actual_dmg

        # Standard Phase 2 Transition (outside breach)
        target["phase_2_triggered"] = True
        if is_anom_combat and int(target.get("max_stability", 0) or 0) > 0:
            target["stability"] = int(target.get("max_stability", 200))
        heal_amt = int(max_hp * 0.2)
        transition_hp = max(int(max_hp * 0.5), new_hp) + heal_amt
        target["hp"] = min(max_hp, max(1, transition_hp))

        cur_eff = target.get("status_effects")
        if isinstance(cur_eff, str):
            try:
                target["status_effects"] = json.loads(cur_eff) if cur_eff.strip().startswith("[") else ([cur_eff] if cur_eff.strip() else [])
            except Exception:
                target["status_effects"] = [cur_eff] if cur_eff.strip() else []
        elif not isinstance(cur_eff, list):
            target["status_effects"] = []

        apply_status_effect(target, "Enraged [3 turns]", source="boss_phase2")

        if combat_log is not None:
            b_name = target.get("name", "Boss")
            combat_log.append(
                f"⚠️ **BOSS PHASE TRANSITION!** **{b_name}** survives the blow and enters Phase 2! Healed **+{heal_amt} HP** and became **Enraged**!"
            )
        return actual_dmg

    # 5. Core HP reduction
    target["hp"] = max(0, new_hp)
    return actual_dmg
