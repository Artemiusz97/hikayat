"""mechanics/combat/targeting.py

Dynamic threat matrix with 1.15x pull hysteresis, Stalker <25% HP dive
targeting, two-turn hybrid boss telegraph arming/interruption, Hard-CC &
Stability-Breach stagger surge conversion, and qualitative HUD telemetry.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Set, Union

from .status_effects import HARD_CC_NAMES, apply_status_effect, normalize_status_effect


def compute_party_scaled_interrupt_threshold(
    max_hp: int,
    living_ally_count: int = 1,
) -> int:
    """Computes party-scaled boss interrupt threshold (10% solo + 4% per extra ally, min 10 HP)."""
    hp_cap = max(1, int(max_hp or 100))
    allies = max(1, int(living_ally_count or 1))
    pct = 0.10 + 0.04 * max(0, allies - 1)
    return max(10, int(hp_cap * pct))


def update_threat_on_action(
    threat_matrix: Dict[str, Dict[str, float]],
    acting_id: str,
    action_type: str,
    target_enemy_ids: List[str],
    all_living_enemy_ids: List[str],
    damage_dealt: int = 0,
    effective_healing: int = 0,
    is_taunt: bool = False,
    sticky_taunts: Optional[Dict[str, Dict[str, Any]]] = None,
) -> None:
    """Updates dynamic threat scores across living enemies based on damage, healing, or taunts."""
    if damage_dealt > 0:
        for eid in target_enemy_ids:
            eid_str = str(eid)
            threat_matrix.setdefault(eid_str, {})[acting_id] = (
                threat_matrix.get(eid_str, {}).get(acting_id, 0.0) + (damage_dealt * 1.0)
            )

    if effective_healing > 0 and all_living_enemy_ids:
        heal_threat = (effective_healing * 0.75) / max(1, len(all_living_enemy_ids))
        for eid in all_living_enemy_ids:
            eid_str = str(eid)
            threat_matrix.setdefault(eid_str, {})[acting_id] = (
                threat_matrix.get(eid_str, {}).get(acting_id, 0.0) + round(heal_threat, 2)
            )

    if is_taunt:
        for eid in target_enemy_ids:
            eid_str = str(eid)
            threat_matrix.setdefault(eid_str, {})[acting_id] = (
                threat_matrix.get(eid_str, {}).get(acting_id, 0.0) + 100.0
            )
            if sticky_taunts is not None:
                sticky_taunts[eid_str] = {
                    "target_id": acting_id,
                    "remaining_turns": 2,
                }


def _cand_keys(actor: Dict[str, Any]) -> Set[str]:
    keys: Set[str] = set()
    for k in ("name", "id", "user_id", "npc_id"):
        val = actor.get(k)
        if val is not None:
            s_val = str(val).strip()
            if s_val and s_val.lower() != "none":
                keys.add(s_val)
    return keys


def resolve_threat_target(
    enemy_id: str,
    living_party_actors: List[Dict[str, Any]],
    threat_matrix: Dict[str, Dict[str, float]],
    sticky_taunts: Optional[Dict[str, Dict[str, Any]]] = None,
    current_aggro_targets: Optional[Dict[str, str]] = None,
    enemy_archetype: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Resolves enemy target in priority order:
      1. Sticky Taunt override (active remaining_turns > 0)
      2. Stalker/Assassin conditional dive on severely wounded (<25% HP) ally
      3. Threat matrix highest score with 1.15x pull hysteresis on living holder
      4. None (caller falls back to decoy / archetype opener / random)
    """
    if not living_party_actors:
        return None

    eid = str(enemy_id)

    # 1. Sticky Taunt override
    if sticky_taunts and eid in sticky_taunts:
        t_info = sticky_taunts[eid]
        if isinstance(t_info, dict) and int(t_info.get("remaining_turns", 0) or 0) > 0:
            tid = str(t_info.get("target_id") or "")
            for actor in living_party_actors:
                if tid in _cand_keys(actor):
                    if current_aggro_targets is not None:
                        current_aggro_targets[eid] = str(actor.get("name") or tid)
                    return actor

    # 2. Stalker/Assassin opportunistic dive (<25% HP living ally)
    arch_low = str(enemy_archetype or "").strip().lower()
    if any(tok in arch_low for tok in ("stalker", "assassin")):
        wounded: List[tuple[float, int, Dict[str, Any]]] = []
        for actor in living_party_actors:
            a_hp = int(actor.get("hp", 0) or 0)
            a_max = max(1, int(actor.get("max_hp", 1) or 1))
            ratio = a_hp / float(a_max)
            if 0 < ratio < 0.25:
                wounded.append((ratio, a_hp, actor))
        if wounded:
            wounded.sort(key=lambda item: (item[0], item[1]))
            dive_target = wounded[0][2]
            if current_aggro_targets is not None:
                current_aggro_targets[eid] = str(dive_target.get("name") or dive_target.get("id") or "")
            return dive_target

    # 3. Dynamic threat score ranking with 1.15x pull hysteresis
    e_scores = (threat_matrix or {}).get(eid) or {}
    actor_scores: List[tuple[float, Dict[str, Any]]] = []
    if e_scores:
        for actor in living_party_actors:
            keys = _cand_keys(actor)
            score = max((float(e_scores.get(k, 0.0) or 0.0) for k in keys), default=0.0)
            if score > 0.0:
                actor_scores.append((score, actor))

    if not actor_scores:
        return None

    actor_scores.sort(key=lambda x: x[0], reverse=True)
    top_score, top_actor = actor_scores[0]

    holder_key = current_aggro_targets.get(eid) if isinstance(current_aggro_targets, dict) else None
    if holder_key:
        holder_match = next(
            ((sc, act) for sc, act in actor_scores if holder_key in _cand_keys(act)),
            None,
        )
        if holder_match is not None:
            holder_score, holder_actor = holder_match
            if top_actor is not holder_actor and holder_score > 0.0 and top_score < (holder_score * 1.15):
                return holder_actor

    if isinstance(current_aggro_targets, dict):
        current_aggro_targets[eid] = str(top_actor.get("name") or top_actor.get("id") or "")
    return top_actor


def arm_boss_telegraph(
    enemy: Dict[str, Any],
    turn_count: int,
    boss_telegraph_state: Dict[str, Any],
    living_ally_count: int = 1,
    trigger_mode: str = "cadence",
) -> Optional[Dict[str, Any]]:
    """
    Arms a boss's telegraphed supreme windup.
    Never double-arms or overwrites an already-active telegraph.
    """
    hp = int(enemy.get("hp", 0) or 0)
    if hp <= 0:
        return None
    if not (enemy.get("is_boss") or int(enemy.get("tier_rank", 1) or 1) >= 4):
        return None
    if enemy.get("telegraphed_skill"):
        return None

    max_hp = max(1, int(enemy.get("max_hp", 100) or 100))
    mode = str(trigger_mode or "cadence").strip().lower()

    is_cadence = turn_count > 0 and turn_count % 3 == 0
    is_phase2 = hp <= 0.5 * max_hp and not enemy.get("_phase2_telegraphed")

    if mode == "cadence":
        if not is_cadence:
            return None
    elif mode == "phase2":
        if not is_phase2:
            return None
        enemy["_phase2_telegraphed"] = True
    else:
        if not (is_cadence or is_phase2):
            return None
        if is_phase2 and not is_cadence:
            enemy["_phase2_telegraphed"] = True
            mode = "phase2"
        else:
            mode = "cadence"

    threshold = compute_party_scaled_interrupt_threshold(max_hp, living_ally_count=living_ally_count)
    skill_name = enemy.get("supreme_skill_name") or f"{enemy.get('name', 'Boss')}'s Cataclysmic Onslaught"
    label = enemy.get("supreme_skill_label") or f"charging up an earth-shattering blow ({skill_name})"
    eid = str(enemy.get("id") or enemy.get("name"))

    telegraph: Dict[str, Any] = {
        "enemy_id": eid,
        "skill_name": skill_name,
        "telegraphed_label": label,
        "interrupt_threshold": threshold,
        "accumulated_interrupt_damage": 0,
        "damage_mult": 2.0 if mode == "cadence" else 1.75,
        "turns_remaining": 1,
        "trigger_mode": mode,
    }
    enemy["telegraphed_skill"] = telegraph
    enemy["stagger_pct"] = 0
    boss_telegraph_state[eid] = telegraph
    return telegraph


def check_boss_telegraph_interrupt(
    enemy: Dict[str, Any],
    accumulated_damage: int,
    boss_telegraph_state: Dict[str, Any],
    combat_log: Optional[List[str]] = None,
) -> bool:
    """Checks if accumulated party damage/stagger interrupts the boss telegraph into Staggered."""
    telegraph = enemy.get("telegraphed_skill")
    if not isinstance(telegraph, dict) or not telegraph:
        return False

    threshold = max(1, int(telegraph.get("interrupt_threshold", 9999) or 9999))
    acc = max(0, int(accumulated_damage or 0))
    if acc >= threshold:
        enemy["telegraphed_skill"] = None
        enemy["stagger_pct"] = 0
        eid = str(enemy.get("id") or enemy.get("name"))
        boss_telegraph_state.pop(eid, None)

        apply_status_effect(
            enemy,
            {
                "name": "Staggered",
                "category": "combat",
                "duration_type": "turns",
                "remaining_duration": 1,
                "max_duration": 1,
                "duration": 1,
                "intensity_stacks": 1,
                "potency": 0.0,
                "metadata": {"damage_taken_mult": 1.25, "stagger_vulnerable": True},
            },
            source="party_interrupt",
        )
        if combat_log is not None:
            enemy_name = enemy.get("name", "The foe")
            combat_log.append(
                f"⚡ **CRITICAL INTERRUPTION!** The concentrated assault shatters **{enemy_name}**'s stance! "
                f"Its deadly strike is aborted and it is **Staggered**!"
            )
        return True

    enemy["stagger_pct"] = max(0, min(100, int(round((acc / float(threshold)) * 100))))
    return False


def apply_boss_cc_stagger_surge(
    enemy: Dict[str, Any],
    status_input: Union[str, Dict[str, Any]],
    boss_telegraph_state: Dict[str, Any],
    combat_log: Optional[List[str]] = None,
    is_stability_breach: bool = False,
) -> bool:
    """
    Unstoppable Windup + Stagger Surge:
    When a boss is actively charging a telegraphed skill, Hard CC cannot immediately
    skip its windup; instead it converts into +50% Stagger Surge (or +100% for Anomalous
    Stability Breach). Returns True when the boss's charging poise intercepted the CC.
    """
    telegraph = enemy.get("telegraphed_skill")
    if not isinstance(telegraph, dict) or not telegraph:
        return False

    norm_name = normalize_status_effect(status_input)["name"].strip().lower()
    is_interceptable_cc = norm_name in HARD_CC_NAMES and norm_name != "staggered"
    if not (is_stability_breach or is_interceptable_cc):
        return False

    threshold = max(1, int(telegraph.get("interrupt_threshold", 20) or 20))
    surge = threshold if is_stability_breach else max(1, int(math.ceil(0.50 * threshold)))
    acc = max(0, int(telegraph.get("accumulated_interrupt_damage", 0) or 0)) + surge
    telegraph["accumulated_interrupt_damage"] = acc

    broke = check_boss_telegraph_interrupt(
        enemy,
        acc,
        boss_telegraph_state,
        combat_log=combat_log,
    )
    if not broke and combat_log is not None:
        e_name = enemy.get("name", "The boss")
        combat_log.append(
            f"🛡️ **POISE SURGE!** **{e_name}** braces through the crowd-control effect, "
            f"though its charging stance fractures significantly!"
        )
    return True


def populate_enemy_hud_telemetry(
    enemies: List[Dict[str, Any]],
    threat_ledger: Optional[Dict[str, Any]],
    party_actors: List[Dict[str, Any]],
) -> None:
    """
    Stamps UI-safe qualitative telemetry onto living enemy dicts:
      - stagger_pct: 0..100 int (zero raw HP threshold numbers)
      - aggro_target_name: str | None
      - aggro_mode: "taunted" | "aggro" | None
    """
    ledger = threat_ledger if isinstance(threat_ledger, dict) else {}
    sticky_taunts = ledger.get("sticky_taunts") if isinstance(ledger.get("sticky_taunts"), dict) else {}
    holders = ledger.get("current_aggro_targets") if isinstance(ledger.get("current_aggro_targets"), dict) else {}
    matrix = ledger.get("threat_matrix") if isinstance(ledger.get("threat_matrix"), dict) else {}

    living_actors = [a for a in (party_actors or []) if isinstance(a, dict) and int(a.get("hp", 0) or 0) > 0]
    key_to_name: Dict[str, str] = {}
    for actor in living_actors:
        disp = str(actor.get("name") or actor.get("id") or "").strip()
        if not disp:
            continue
        for k in _cand_keys(actor):
            key_to_name[k] = disp

    for enemy in enemies or []:
        if not isinstance(enemy, dict):
            continue
        if int(enemy.get("hp", 0) or 0) <= 0:
            enemy["stagger_pct"] = 0
            enemy["aggro_target_name"] = None
            enemy["aggro_mode"] = None
            continue

        tel = enemy.get("telegraphed_skill")
        if isinstance(tel, dict) and tel:
            thr = max(1, int(tel.get("interrupt_threshold", 1) or 1))
            acc = max(0, int(tel.get("accumulated_interrupt_damage", 0) or 0))
            enemy["stagger_pct"] = max(0, min(100, int(round((acc / float(thr)) * 100))))
        else:
            enemy["stagger_pct"] = 0

        e_keys = [
            str(v)
            for v in (enemy.get("id"), enemy.get("name"), enemy.get("base_name"))
            if v is not None and str(v).strip()
        ]

        taunted_name: Optional[str] = None
        for ek in e_keys:
            t_info = sticky_taunts.get(ek)
            if isinstance(t_info, dict) and int(t_info.get("remaining_turns", 0) or 0) > 0:
                tid = str(t_info.get("target_id") or "").strip()
                if tid in key_to_name:
                    taunted_name = key_to_name[tid]
                    break
        if taunted_name:
            enemy["aggro_target_name"] = taunted_name
            enemy["aggro_mode"] = "taunted"
            continue

        aggro_name: Optional[str] = None
        for ek in e_keys:
            h_key = str(holders.get(ek) or "").strip()
            if h_key and h_key in key_to_name:
                aggro_name = key_to_name[h_key]
                break

        if not aggro_name:
            best_score = 0.0
            for ek in e_keys:
                e_scores = matrix.get(ek)
                if isinstance(e_scores, dict):
                    for k, sc in e_scores.items():
                        val = float(sc or 0.0)
                        if val > best_score and str(k) in key_to_name:
                            best_score = val
                            aggro_name = key_to_name[str(k)]

        if aggro_name:
            enemy["aggro_target_name"] = aggro_name
            enemy["aggro_mode"] = "aggro"
        else:
            enemy["aggro_target_name"] = None
            enemy["aggro_mode"] = None


__all__ = [
    "apply_boss_cc_stagger_surge",
    "arm_boss_telegraph",
    "check_boss_telegraph_interrupt",
    "compute_party_scaled_interrupt_threshold",
    "populate_enemy_hud_telemetry",
    "resolve_threat_target",
    "update_threat_on_action",
]
