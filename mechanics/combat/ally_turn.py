"""mechanics/combat/ally_turn.py

Phase 1 extra synchronized player actions and Phase 2 Friendly Allies turn
resolution: autonomous construct windups, legacy companion vitals hydration,
genre-gated 3-slot skill priorities (Triage -> Smart Emergency Peel Only ->
Slot 3 Skill -> Slot 2 Tactical -> Slot 1 Tactical Damage / 0-MP Cantrip).
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from mechanics.combat.awakened_resonance import (
    apply_stability_and_break,
    compute_stability_shred,
    update_encounter_pips,
)
from mechanics.combat.enemies import get_enemy_armor_profile, get_enemy_weapon_profile
from mechanics.combat.spells import calculate_spell_damage, get_spell
from mechanics.combat.spells.awakened_kits import normalize_anomalous_attribute
from mechanics.social.attributes import calculate_combat_attributes

from .formulas import calculate_tactical_damage, get_elemental_multiplier
from .loadouts import compute_companion_vitals, ensure_combatant_loadout, tick_combatant_cooldowns
from .status_effects import HARD_CC_NAMES, apply_status_effect, get_status_stat_modifiers, normalize_status_effect
from .targeting import apply_boss_cc_stagger_surge, update_threat_on_action
from .types import get_combatant_stat

_MAGICAL_CALC_TYPES = {
    "magical", "energy", "fire", "shock", "electric", "ice",
    "holy", "dark", "poison", "bio", "acid", "water", "earth", "wind", "aether",
}


def resolve_extra_player_actions(ctx: Dict[str, Any]) -> None:
    """Executes synchronized secondary player actions (co-op turns or batch actions)."""
    actions = ctx["actions"]
    if not isinstance(actions, list) or len(actions) <= 1:
        return

    session = ctx["session"]
    enemies = ctx["enemies"]
    acting_char_data = ctx["acting_char_data"]
    acting_char_name = ctx["acting_char_name"]
    acting_user_id = ctx["acting_user_id"]
    player_attrs = ctx["player_attrs"]
    is_anom_combat = ctx["is_anom_combat"]
    is_non_lethal_active = ctx["is_non_lethal_active"]
    p_attr = ctx["p_attr"]
    p_arch = ctx["p_arch"]
    pips_map = ctx["pips_map"]
    combat_log = ctx["combat_log"]
    player_mp_change_by_name = ctx["player_mp_change_by_name"]
    player_heal_by_name = ctx["player_heal_by_name"]
    boss_telegraph_state = ctx["boss_telegraph_state"]
    apply_damage_to_enemy = ctx["apply_damage_to_enemy"]
    scen = session.get("scenario", "fantasy") if isinstance(session, dict) else "fantasy"

    for extra_act in actions[1:]:
        if not isinstance(extra_act, dict):
            continue
        living_for_extra = [m for m in enemies if m.get("hp", 0) > 0]
        if not living_for_extra:
            break
        ex_foe = living_for_extra[0]
        raw_ex_target = extra_act.get("target_enemy") or extra_act.get("combat_target") or extra_act.get("target")
        if isinstance(raw_ex_target, dict) and raw_ex_target.get("hp", 0) > 0:
            ex_foe = raw_ex_target
        elif isinstance(raw_ex_target, str) and raw_ex_target.strip():
            ex_t_low = raw_ex_target.strip().lower()
            ex_foe = next((m for m in living_for_extra if str(m.get("name") or "").lower() == ex_t_low), ex_foe)
        elif isinstance(extra_act.get("target_index"), int) and 0 <= extra_act["target_index"] < len(enemies):
            cand_foe = enemies[extra_act["target_index"]]
            if isinstance(cand_foe, dict) and cand_foe.get("hp", 0) > 0:
                ex_foe = cand_foe

        ex_char = extra_act.get("char") if isinstance(extra_act.get("char"), dict) else acting_char_data
        ex_name = ex_char.get("name", acting_char_name)
        ex_uid = extra_act.get("user_id") or ex_char.get("user_id") or acting_user_id
        ex_attrs = (
            calculate_combat_attributes(ex_char, scenario=scen, allow_non_combat=True)
            if isinstance(ex_char, dict) and ex_char is not acting_char_data
            else player_attrs
        )
        ex_tier = extra_act.get("tier") or (
            extra_act["check"].tier if "check" in extra_act and hasattr(extra_act["check"], "tier") else "success"
        )
        if ex_tier not in ("crit_success", "success"):
            combat_log.append(f"⚔️ **{ex_name}** attacked **{ex_foe['name']}**: Attack missed.")
            continue

        ex_dmg = max(8, int(ex_attrs.get("atk", 20)))
        if ex_tier == "crit_success":
            ex_dmg = int(round(ex_dmg * 1.5))

        if is_anom_combat:
            ex_attr = normalize_anomalous_attribute(ex_char.get("attribute") or p_attr, fallback=p_attr)
            ex_arch = str(ex_char.get("combat_archetype") or p_arch).strip().lower()
            ex_cat_bonus = 0.25 if any("harmony" in normalize_status_effect(s)["name"].lower() for s in ex_char.get("status_effects", [])) else 0.0
            _sh_ex = compute_stability_shred(12, ex_attr, ex_arch, ex_attr, ex_foe, catalyst_bonus=ex_cat_bonus)
            if not ex_foe.get("is_breached") and int(ex_foe.get("max_stability", 0) or 0) > 0:
                if int(ex_foe.get("stability", 100)) - _sh_ex <= 0:
                    ex_foe["_will_breach_this_hit"] = True
            if ex_attr == "aether":
                ex_foe["_pierce_temp_hp_this_hit"] = True
            apply_damage_to_enemy(ex_foe, ex_dmg)
            ex_foe.pop("_will_breach_this_hit", None)
            ex_foe.pop("_pierce_temp_hp_this_hit", None)
            ex_triggered_break = False
            ex_extra_pips = 0
            if ex_foe.get("hp", 0) > 0:
                ex_atk_power = max(ex_attrs.get("matk", 20), ex_attrs.get("atk", 20))
                ex_br = apply_stability_and_break(ex_foe, _sh_ex, ex_attr, ex_atk_power, combat_log, non_lethal_mode=is_non_lethal_active)
                if ex_br.get("triggered_break"):
                    ex_foe["_breached_this_round"] = True
                    ex_triggered_break = True
                    ex_extra_pips = int(ex_br.get("bonus_pips", 0) or 0)
                    if ex_foe.get("telegraphed_skill"):
                        apply_boss_cc_stagger_surge(
                            ex_foe, "Staggered [1 turn]", boss_telegraph_state, combat_log=combat_log, is_stability_breach=True
                        )
                    if ex_br.get("mp_refund", 0) > 0 and isinstance(ex_char, dict):
                        mp_ref = int(ex_br["mp_refund"])
                        ex_char["mp"] = min(ex_char.get("max_mp", 100), ex_char.get("mp", 0) + mp_ref)
                        player_mp_change_by_name[ex_name] = player_mp_change_by_name.get(ex_name, 0) + mp_ref
                    if ex_br.get("squad_heal", 0) > 0 and isinstance(ex_char, dict):
                        sh_amt = int(ex_br["squad_heal"])
                        ex_char["hp"] = min(ex_char.get("max_hp", 100), ex_char.get("hp", 0) + sh_amt)
                        player_heal_by_name[ex_name] = player_heal_by_name.get(ex_name, 0) + sh_amt
                    ex_other_foes = [f for f in enemies if f is not ex_foe and f.get("hp", 0) > 0]
                    if ex_splash := int(ex_br.get("aoe_splash_damage", 0) or 0):
                        if ex_other_foes:
                            for of in ex_other_foes:
                                apply_damage_to_enemy(of, ex_splash)
                                ctx["total_enemy_damage"] += ex_splash
                            combat_log.append(f"🌪️ **Synchronized Vacuum Shear (AoE Splash):** Dealt **{ex_splash} damage** to secondary foes!")
                    elif ex_chain := int(ex_br.get("chain_damage", 0) or 0):
                        if ex_other_foes:
                            apply_damage_to_enemy(ex_other_foes[0], ex_chain)
                            ctx["total_enemy_damage"] += ex_chain
                            combat_log.append(f"⚡ **Synchronized Grid Overload (Chain Arc):** Arced to **{ex_other_foes[0]['name']}** for **{ex_chain} damage**!")
                elif ex_br.get("super_break_damage", 0) > 0:
                    sb = int(ex_br["super_break_damage"])
                    apply_damage_to_enemy(ex_foe, sb)
                    ctx["total_enemy_damage"] += sb
            ex_pip_key = str(ex_uid or ex_name)
            pips_map[ex_pip_key] = update_encounter_pips(
                pips_map.get(ex_pip_key, 0),
                hit_landed=True,
                triggered_break_this_turn=ex_triggered_break,
                cast_ultimate=False,
                extra_break_pips=ex_extra_pips,
            )
            if isinstance(session, dict):
                session["player_resonance_pips"] = pips_map
        else:
            apply_damage_to_enemy(ex_foe, ex_dmg)
        ctx["total_enemy_damage"] += ex_dmg
        combat_log.append(f"⚔️ **{ex_name}** attacked **{ex_foe['name']}**: Dealt **{ex_dmg} damage**.")


def _pick_safe_target(living_enemies: List[Dict[str, Any]], is_non_lethal_active: bool) -> Dict[str, Any]:
    if is_non_lethal_active:
        return min(living_enemies, key=lambda e: e.get("hp", 100))
    safe_pool = [
        e for e in living_enemies
        if not (
            e.get("requires_non_lethal_subdue") and (
                e.get("is_breached")
                or e.get("hp", 100) <= 1
                or (e.get("hp", 100) / max(1, e.get("max_hp", 100))) <= float(e.get("subdue_threshold_pct") or 0.35)
            )
        )
    ]
    return random.choice(safe_pool) if safe_pool else living_enemies[0]


def _sync_companion_state(
    comp: Dict[str, Any],
    active_party_npcs: List[Dict[str, Any]],
    current_npcs: List[Dict[str, Any]],
    party: List[Any],
    player_user_ids: set[Any],
) -> None:
    """Propagates companion mutations back to session party_npcs, current_npcs, and party dicts."""
    c_name = str(comp.get("name") or "").strip().lower()
    if not c_name:
        return
    fields = ("hp", "max_hp", "mp", "max_mp", "stats", "combat_loadout", "skill_cooldowns", "status_effects", "weapon_profile", "armor_profile")
    targets: List[Dict[str, Any]] = []
    for lst in (active_party_npcs, current_npcs):
        for entry in lst:
            if isinstance(entry, dict) and str(entry.get("name") or "").strip().lower() == c_name:
                targets.append(entry)
    for p in party:
        p_obj = p[0] if isinstance(p, (tuple, list)) else p
        if not isinstance(p_obj, dict):
            continue
        if p_obj.get("user_id") is not None and p_obj.get("user_id") in player_user_ids:
            continue
        if str(p_obj.get("name") or "").strip().lower() == c_name:
            targets.append(p_obj)
    for tgt in targets:
        if tgt is comp:
            continue
        for fld in fields:
            if fld in comp:
                tgt[fld] = comp[fld]


def _apply_companion_status_with_surge(
    target_enemy: Dict[str, Any],
    status_tag: str,
    boss_telegraph_state: Dict[str, Any],
    combat_log: List[str],
    source: str,
) -> None:
    norm_name = normalize_status_effect(status_tag)["name"].strip().lower()
    if (
        target_enemy.get("telegraphed_skill")
        and norm_name in HARD_CC_NAMES
        and norm_name != "staggered"
        and apply_boss_cc_stagger_surge(
            target_enemy,
            status_tag,
            boss_telegraph_state,
            combat_log=combat_log,
        )
    ):
        return
    apply_status_effect(target_enemy, status_tag, source=source)


def _execute_companion_tactical_attack(
    ctx: Dict[str, Any],
    comp: Dict[str, Any],
    skill: Dict[str, Any],
    target_m: Dict[str, Any],
    scen_cbt: str,
) -> int:
    """Executes an offensive companion skill through calculate_tactical_damage & subdue clamps."""
    combat_log = ctx["combat_log"]
    boss_telegraph_state = ctx["boss_telegraph_state"]
    apply_damage_to_enemy = ctx["apply_damage_to_enemy"]
    is_non_lethal_active = ctx["is_non_lethal_active"]

    comp_name = comp.get("name", "Companion")
    comp_arch = comp.get("archetype", "Companion")
    comp_lvl = int(comp.get("level", 1) or 1)

    comp_attrs = calculate_combat_attributes(comp, scenario=scen_cbt, allow_non_combat=True)
    c_mods = get_status_stat_modifiers(comp)
    if c_mods.get("damage_dealt_mult", 1.0) != 1.0:
        d_m = float(c_mods["damage_dealt_mult"])
        comp_attrs["atk"] = max(1, int(round(comp_attrs.get("atk", 15) * d_m)))
        comp_attrs["matk"] = max(1, int(round(comp_attrs.get("matk", 15) * d_m)))
    if c_mods.get("accuracy_bonus"):
        comp_attrs["acc"] = int(comp_attrs.get("acc", 66) + c_mods["accuracy_bonus"])

    base_weapon = dict(comp.get("weapon_profile") or get_enemy_weapon_profile(comp_arch))
    base_weapon.pop("attack_profiles", None)
    raw_dtype = str(skill.get("damage_type") or "physical").lower()
    calc_dtype = "electric" if raw_dtype == "lightning" else raw_dtype
    if skill.get("uses_matk") and calc_dtype not in _MAGICAL_CALC_TYPES:
        calc_dtype = "magical"
    base_weapon["damage_types"] = {calc_dtype: 1.0}
    if skill.get("armor_penetration") is not None:
        base_weapon["armor_penetration"] = float(skill["armor_penetration"])
    base_weapon["multiplier"] = float(skill.get("damage_mult", 1.0) or 1.0)

    t_arch = target_m.get("archetype", "Brute")
    t_armor = dict(target_m.get("armor_profile") or get_enemy_armor_profile(t_arch))
    t_attrs = calculate_combat_attributes(target_m.get("stats", {}))
    t_attrs.update({
        "weaknesses": target_m.get("weaknesses", []),
        "resistances": target_m.get("resistances", []),
        "immunities": target_m.get("immunities", []),
        "physicality": target_m.get("physicality", "corporeal"),
    })
    t_mods = get_status_stat_modifiers(target_m)
    t_attrs["eva"] = max(0, int(round(t_attrs.get("eva", 10) * float(t_mods.get("accuracy_mult", 1.0)))))

    best_stat = max(["STR", "AGI", "INT", "PER"], key=lambda s: get_combatant_stat(comp, s, default=3))
    c_val = get_combatant_stat(comp, best_stat, default=3)
    m_def = get_combatant_stat(target_m, "END", default=3)
    hit_chance = max(30, min(95, 65 + (c_val - m_def) * 6))
    roll = random.randint(1, 100)
    tier = "crit_success" if roll <= 10 else ("success" if roll <= hit_chance else "fail")

    # Resolve linked SPELL_REGISTRY spell if Slot 3 points to one
    spell_id = skill.get("spell_id")
    if spell_id and calc_dtype in _MAGICAL_CALC_TYPES:
        sp_obj = get_spell(str(spell_id))
        if sp_obj:
            if tier == "fail":
                combat_log.append(f"🎯 **{comp_name}** cast **{skill['name']}** on **{target_m['name']}**, but the spell missed.")
                return 0
            elem_mult = get_elemental_multiplier({calc_dtype: 1.0}, t_armor, t_attrs)
            sp_dmg = calculate_spell_damage(
                comp_attrs.get("matk", 18),
                sp_obj,
                elem_mult,
                defender_attrs=t_attrs,
                armor_type_dt=t_armor.get("type_dt", {}),
                armor_base_dt=t_armor.get("base_dt", 0),
            )
            if tier == "crit_success":
                sp_dmg = int(round(sp_dmg * 1.45))
            t_hp = int(target_m.get("hp", 100) or 0)
            if is_non_lethal_active or target_m.get("requires_non_lethal_subdue"):
                sp_dmg = min(max(0, t_hp - 1), sp_dmg)
            sp_dmg = max(1, sp_dmg) if t_hp > 1 or not (is_non_lethal_active or target_m.get("requires_non_lethal_subdue")) else 0
            actual = apply_damage_to_enemy(target_m, sp_dmg, attacker=comp)
            ctx["total_enemy_damage"] += actual
            combat_log.append(f"✨ **{comp_name}** invoked **{skill['name']}** on **{target_m['name']}**: Dealt **{actual} damage**!")
            if skill.get("status_ailment") and target_m.get("hp", 0) > 0:
                _apply_companion_status_with_surge(target_m, str(skill["status_ailment"]), boss_telegraph_state, combat_log, source="ally_spell")
            return actual

    tres = calculate_tactical_damage(
        attacker_attrs=comp_attrs,
        defender_attrs=t_attrs,
        weapon_meta=base_weapon,
        armor_meta=t_armor,
        tier=tier,
        attacker_level=comp_lvl,
        defender_max_hp=int(target_m.get("max_hp", 100) or 100),
    )
    dmg = int(tres.get("damage", 0) or 0)
    if tier in ("crit_success", "success") and dmg > 0:
        t_hp = int(target_m.get("hp", 100) or 0)
        if is_non_lethal_active or target_m.get("requires_non_lethal_subdue"):
            dmg = min(max(0, t_hp - 1), dmg)
        actual = apply_damage_to_enemy(target_m, dmg, attacker=comp)
        ctx["total_enemy_damage"] += actual
        prefix = "🐾" if comp.get("is_summon") else "🎯"
        combat_log.append(f"{prefix} **{comp_name}** used **{skill['name']}** on **{target_m['name']}**: Dealt **{actual} damage**.")
        if skill.get("status_ailment") and target_m.get("hp", 0) > 0 and "taunted" not in str(skill["status_ailment"]).lower():
            _apply_companion_status_with_surge(target_m, str(skill["status_ailment"]), boss_telegraph_state, combat_log, source="ally_skill")
        return actual

    combat_log.append(f"🎯 **{comp_name}** used **{skill['name']}** on **{target_m['name']}**: Attack deflected by {target_m['name']}.")
    return 0


def resolve_ally_combat_phase(ctx: Dict[str, Any]) -> None:
    """Executes Phase 2: Autonomous Constructs + Companion 3-Slot Priority AI."""
    enemies = ctx["enemies"]
    living_allies = ctx["living_allies"]
    acting_char_name = ctx["acting_char_name"]
    is_anom_combat = ctx["is_anom_combat"]
    is_non_lethal_active = ctx["is_non_lethal_active"]
    scen_cbt = ctx["scen_cbt"]
    current_npcs = ctx["current_npcs"]
    active_party_npcs = ctx["active_party_npcs"]
    party = ctx["party"]
    combat_log = ctx["combat_log"]
    player_chars = ctx["player_chars"]
    player_heal_by_name = ctx["player_heal_by_name"]
    threat_matrix = ctx["threat_matrix"]
    sticky_taunts = ctx["sticky_taunts"]
    companion_actions = ctx["companion_actions"]
    apply_damage_to_enemy = ctx["apply_damage_to_enemy"]

    player_user_ids = {p.get("user_id") for p in player_chars if isinstance(p, dict) and p.get("user_id") is not None}
    player_names = {str(p.get("name") or "").strip().lower() for p in player_chars if isinstance(p, dict)}

    if is_anom_combat:
        for c_unit in [a for a in living_allies if a.get("is_autonomous_construct") and a.get("hp", 0) > 0]:
            windup = c_unit.get("queued_windup")
            if not windup:
                continue
            if windup.get("_queued_this_round"):
                windup.pop("_queued_this_round", None)
                combat_log.append(f"⚙️ **{c_unit['name']}** charges **{windup['name']}** for next turn!")
                continue
            engageable_c = [
                e for e in enemies
                if e.get("hp", 0) > 0 and not (
                    e.get("requires_non_lethal_subdue") and (
                        e.get("is_breached")
                        or e.get("hp", 100) <= 1
                        or (e.get("hp", 100) / max(1, e.get("max_hp", 100))) <= float(e.get("subdue_threshold_pct") or 0.35)
                    )
                )
            ]
            c_unit["queued_windup"] = None
            if engageable_c:
                t_foe = engageable_c[0]
                w_dmg = int(windup.get("damage", 16))
                apply_damage_to_enemy(t_foe, w_dmg, attacker=c_unit)
                ctx["total_enemy_damage"] += w_dmg
                if t_foe.get("hp", 0) > 0 and int(t_foe.get("max_stability", 0) or 0) > 0:
                    c_shred = compute_stability_shred(15, str(windup.get("attr") or "aether"), "vanguard", str(windup.get("attr") or "aether"), t_foe)
                    c_br = apply_stability_and_break(t_foe, c_shred, str(windup.get("attr") or "aether"), w_dmg, combat_log)
                    if c_br.get("triggered_break"):
                        t_foe["_breached_this_round"] = True
                    elif c_br.get("super_break_damage", 0) > 0:
                        sb = int(c_br["super_break_damage"])
                        apply_damage_to_enemy(t_foe, sb, attacker=c_unit)
                        ctx["total_enemy_damage"] += sb
                combat_log.append(
                    f"🤖 **{c_unit['name']}** executed queued **{windup['name']}** on **{t_foe['name']}**: Dealt **{w_dmg} damage**!"
                )
                companion_actions.append({"actor": c_unit.get("name", "Construct"), "skill_id": "windup", "skill_name": windup["name"], "target": t_foe.get("name")})

    seen_comp_names: set[str] = {str(acting_char_name or "").strip().lower()}
    living_companions: List[Dict[str, Any]] = []
    for ally in living_allies:
        if not isinstance(ally, dict) or ally.get("hp", 0) <= 0 or ally.get("is_autonomous_construct"):
            continue
        aname_low = str(ally.get("name") or "").strip().lower()
        if not aname_low or aname_low in seen_comp_names:
            continue
        if ally.get("user_id") is not None and ally.get("user_id") in player_user_ids:
            continue
        seen_comp_names.add(aname_low)
        living_companions.append(ally)

    for comp in living_companions:
        living_enemies = [m for m in enemies if m.get("hp", 0) > 0]
        if not living_enemies:
            break

        if is_anom_combat and not comp.get("is_summon") and (
            comp.get("anomalous_npc_tag") in ("special_agent", "civilian", "folklore_villager")
            or comp.get("is_folklore_villager")
        ):
            from mechanics.social.anomalous_npc_tags import resolve_anomalous_ally_combat_action
            resolve_anomalous_ally_combat_action(
                comp=comp,
                living_enemies=living_enemies,
                living_allies=living_allies,
                current_npcs=current_npcs,
                apply_damage_fn=apply_damage_to_enemy,
                combat_log=combat_log,
            )
            companion_actions.append({"actor": comp.get("name", "Ally"), "skill_id": "anomalous_tag_action", "skill_name": "Anomalous Support"})
            _sync_companion_state(comp, active_party_npcs, current_npcs, party, player_user_ids)
            continue

        comp_name = comp.get("name", "Companion")
        comp_arch = comp.get("archetype", "Companion")
        comp_lvl = max(1, int(comp.get("level", 1) or 1))
        anom_tag = str(comp.get("anomalous_npc_tag") or "").strip().lower()
        is_civilian = anom_tag == "civilian"

        if not comp.get("is_summon") and ("max_hp" not in comp or int(comp.get("max_hp") or 0) <= 25):
            old_max = int(comp.get("max_hp") or 0)
            old_hp = comp.get("hp")
            new_max_hp, new_max_mp = compute_companion_vitals(comp_lvl, comp.get("stats") or {}, is_civilian=is_civilian)
            comp["max_hp"] = new_max_hp
            comp["max_mp"] = new_max_mp
            if old_hp is None or (0 < old_max <= 25 and int(old_hp) >= old_max):
                comp["hp"] = new_max_hp
            else:
                comp["hp"] = min(new_max_hp, int(old_hp))
            if comp.get("mp") is None or (0 < old_max <= 25):
                comp["mp"] = new_max_mp
            else:
                comp["mp"] = min(new_max_mp, int(comp["mp"]))

        if "max_mp" not in comp:
            comp["max_mp"] = 0 if is_civilian else 20
        if "mp" not in comp:
            comp["mp"] = comp["max_mp"]

        tick_combatant_cooldowns(comp)
        loadout = ensure_combatant_loadout(comp, scenario_key=scen_cbt)
        cds = comp.setdefault("skill_cooldowns", {})
        slots = {int(s.get("slot", i + 1)): s for i, s in enumerate(loadout) if isinstance(s, dict)}
        slot1: Dict[str, Any] = slots.get(1) or {"id": "weapon_strike", "slot": 1, "name": "Weapon Strike", "category": "attack", "mana_cost": 0, "cooldown": 0, "damage_mult": 1.0}
        slot2: Optional[Dict[str, Any]] = slots.get(2)
        slot3: Optional[Dict[str, Any]] = slots.get(3)

        comp_mp = int(comp.get("mp", 0) or 0)
        comp_stats = comp.get("stats", {})

        # Priority 1: Emergency Triage Heal (ally <= 30% HP)
        critically_wounded = [
            a for a in living_allies
            if a.get("hp", 0) > 0 and (float(a.get("hp", 100)) / max(1.0, float(a.get("max_hp", 100)))) <= 0.30
        ]
        heal_skill: Optional[Dict[str, Any]] = None
        if critically_wounded:
            if slot3 and int(slot3.get("heal_amount", 0) or 0) > 0 and int(cds.get(slot3["id"], 0) or 0) <= 0 and comp_mp >= int(slot3.get("mana_cost", 0) or 0):
                heal_skill = slot3
            elif slot2 and int(slot2.get("heal_amount", 0) or 0) > 0 and int(cds.get(slot2["id"], 0) or 0) <= 0 and comp_mp >= int(slot2.get("mana_cost", 0) or 0):
                heal_skill = slot2
            elif (comp_arch in ("Caster", "Support", "Medic", "Cleric", "Sage") or comp_stats.get("INT", 3) >= 5) and comp_mp >= 6:
                heal_skill = {"id": "emergency_aid", "name": "Restorative Aid", "mana_cost": 6, "cooldown": 0, "heal_amount": comp_lvl * 6 + 15}

        if critically_wounded and heal_skill:
            heal_target = min(critically_wounded, key=lambda a: float(a.get("hp", 100)) / max(1.0, float(a.get("max_hp", 100))))
            heal_cost = int(heal_skill.get("mana_cost", 0) or 0)
            heal_amt = int(heal_skill.get("heal_amount") or (comp_lvl * 6 + 15))
            comp["mp"] = max(0, comp_mp - heal_cost)
            if int(heal_skill.get("cooldown", 0) or 0) > 0:
                cds[str(heal_skill["id"])] = int(heal_skill["cooldown"])
            t_hp = int(heal_target.get("hp", 100) or 0)
            t_max = int(heal_target.get("max_hp", 100) or 100)
            heal_target["hp"] = min(t_max, t_hp + heal_amt)
            actual_healed = heal_target["hp"] - t_hp
            t_name = heal_target.get("name", "Ally")
            if t_name in player_heal_by_name:
                player_heal_by_name[t_name] += actual_healed
            combat_log.append(f"✨ **{comp_name}** channeled **{heal_skill['name']}** into **{t_name}**: Restored **+{actual_healed} HP**!")
            if actual_healed > 0:
                all_eids = [str(e.get("id") or e.get("name")) for e in living_enemies if e.get("hp", 0) > 0]
                update_threat_on_action(
                    threat_matrix, str(comp_name), "heal", [], all_eids,
                    effective_healing=actual_healed, sticky_taunts=sticky_taunts,
                )
            companion_actions.append({"actor": comp_name, "skill_id": str(heal_skill["id"]), "skill_name": str(heal_skill["name"]), "target": t_name, "heal": actual_healed})
            _sync_companion_state(comp, active_party_npcs, current_npcs, party, player_user_ids)
            continue

        target_m = _pick_safe_target(living_enemies, is_non_lethal_active)

        # Priority 2: Smart Emergency Peel Only (Guardian/Vanguard/Tank Intercept Taunt)
        if slot2 and slot2.get("id") == "intercept_taunt" and int(cds.get("intercept_taunt", 0) or 0) <= 0:
            has_stalker_foe = any(
                any(tok in str(e.get("archetype") or "").lower() for tok in ("stalker", "assassin"))
                for e in living_enemies
            )
            needs_peel = False
            comp_name_low = str(comp_name or "").strip().lower()
            for ally in living_allies:
                a_name_low = str(ally.get("name") or "").strip().lower()
                if ally is comp or (comp_name_low and a_name_low == comp_name_low):
                    continue
                a_hp = int(ally.get("hp", 0) or 0)
                a_max = max(1, int(ally.get("max_hp", 1) or 1))
                if a_hp <= 0:
                    continue
                ratio = a_hp / float(a_max)
                a_arch_low = f"{ally.get('archetype', '')} {ally.get('combat_archetype', '')}".lower()
                is_vip = (a_name_low in player_names) or any(h in a_arch_low for h in ("healer", "medic", "cleric", "support", "caster"))
                if (is_vip and ratio < 0.40) or (has_stalker_foe and ratio < 0.25):
                    needs_peel = True
                    break

            if needs_peel:
                cds["intercept_taunt"] = int(slot2.get("cooldown", 3) or 3)
                if slot2.get("self_status"):
                    apply_status_effect(comp, str(slot2["self_status"]), source="intercept_taunt")
                peel_dmg = _execute_companion_tactical_attack(ctx, comp, slot2, target_m, scen_cbt)
                target_eid = str(target_m.get("id") or target_m.get("name"))
                all_eids = [str(e.get("id") or e.get("name")) for e in living_enemies if e.get("hp", 0) > 0]
                update_threat_on_action(
                    threat_matrix, str(comp_name), "taunt", [target_eid], all_eids,
                    damage_dealt=peel_dmg, is_taunt=True, sticky_taunts=sticky_taunts,
                )
                combat_log.append(f"🛡️ **{comp_name}** intercepted the assault with **Intercept Taunt**, drawing **{target_m['name']}** away from wounded allies!")
                companion_actions.append({"actor": comp_name, "skill_id": "intercept_taunt", "skill_name": slot2["name"], "target": target_m.get("name"), "damage": peel_dmg})
                _sync_companion_state(comp, active_party_npcs, current_npcs, party, player_user_ids)
                continue

        # Priority 3: Slot 3 Genre Skill / SPELL_REGISTRY
        if slot3 and int(cds.get(slot3["id"], 0) or 0) <= 0 and comp_mp >= int(slot3.get("mana_cost", 0) or 0):
            s3_cost = int(slot3.get("mana_cost", 0) or 0)
            subdue_safe = not (
                slot3.get("target_type") in ("single_enemy", "all_enemies")
                and target_m.get("requires_non_lethal_subdue")
                and (target_m.get("hp", 100) / max(1, target_m.get("max_hp", 100))) <= float(target_m.get("subdue_threshold_pct") or 0.35)
            )
            if slot3.get("category") == "support":
                comp["mp"] = max(0, comp_mp - s3_cost)
                cds[str(slot3["id"])] = int(slot3.get("cooldown", 2) or 2)
                buff_target = next((a for a in living_allies if str(a.get("name") or "").strip().lower() in player_names and a.get("hp", 0) > 0), comp)
                if slot3.get("status_ailment"):
                    apply_status_effect(buff_target, f"{slot3['status_ailment']} [2 turns]", source="ally_support")
                combat_log.append(f"🛡️ **{comp_name}** cast **{slot3['name']}**, fortifying **{buff_target.get('name', comp_name)}**!")
                companion_actions.append({"actor": comp_name, "skill_id": str(slot3["id"]), "skill_name": str(slot3["name"]), "target": buff_target.get("name")})
                _sync_companion_state(comp, active_party_npcs, current_npcs, party, player_user_ids)
                continue
            elif subdue_safe:
                comp["mp"] = max(0, comp_mp - s3_cost)
                cds[str(slot3["id"])] = int(slot3.get("cooldown", 2) or 2)
                s3_dmg = _execute_companion_tactical_attack(ctx, comp, slot3, target_m, scen_cbt)
                companion_actions.append({"actor": comp_name, "skill_id": str(slot3["id"]), "skill_name": str(slot3["name"]), "target": target_m.get("name"), "damage": s3_dmg})
                _sync_companion_state(comp, active_party_npcs, current_npcs, party, player_user_ids)
                continue

        # Priority 4: Slot 2 Non-Taunt / Non-Heal Tactical Skill
        if slot2 and int(cds.get(slot2["id"], 0) or 0) <= 0:
            s2_id = str(slot2.get("id") or "")
            if s2_id == "take_cover":
                c_hp = int(comp.get("hp", 100) or 0)
                c_max = max(1, int(comp.get("max_hp", 100) or 100))
                if (c_hp / float(c_max)) < 0.60:
                    cds["take_cover"] = int(slot2.get("cooldown", 3) or 3)
                    apply_status_effect(comp, str(slot2.get("status_ailment") or "Braced [+4 DT] [1 turn]"), source="take_cover")
                    combat_log.append(f"🛡️ **{comp_name}** took defensive cover to stay safe!")
                    companion_actions.append({"actor": comp_name, "skill_id": "take_cover", "skill_name": slot2["name"], "target": comp_name})
                    _sync_companion_state(comp, active_party_npcs, current_npcs, party, player_user_ids)
                    continue
            elif s2_id not in ("intercept_taunt", "field_triage", "take_cover"):
                cds[s2_id] = int(slot2.get("cooldown", 2) or 2)
                s2_dmg = _execute_companion_tactical_attack(ctx, comp, slot2, target_m, scen_cbt)
                companion_actions.append({"actor": comp_name, "skill_id": s2_id, "skill_name": slot2["name"], "target": target_m.get("name"), "damage": s2_dmg})
                _sync_companion_state(comp, active_party_npcs, current_npcs, party, player_user_ids)
                continue

        # Priority 5: Slot 1 Basic Weapon / 0-MP Cantrip
        s1_dmg = _execute_companion_tactical_attack(ctx, comp, slot1, target_m, scen_cbt)
        companion_actions.append({"actor": comp_name, "skill_id": str(slot1["id"]), "skill_name": str(slot1["name"]), "target": target_m.get("name"), "damage": s1_dmg})
        _sync_companion_state(comp, active_party_npcs, current_npcs, party, player_user_ids)
