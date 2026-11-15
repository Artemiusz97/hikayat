"""mechanics/combat/player_spells.py

Extracted Phase 1 spell resolution handler for Player turns: resolves
Awakened Resonance basic strikes, SPELL_REGISTRY spells, Pact overdraws,
AoE/Chain/Single targeting, metamagic affixes, summoning, and Stagger Surge
interception against telegraphing bosses.
"""
from __future__ import annotations

import json
import random
from typing import Any, Callable, Dict, Optional, Tuple

from mechanics.combat.enemies import get_enemy_armor_profile
from mechanics.combat.spells import SUMMON_TEMPLATES, calculate_spell_damage, get_spell
from mechanics.combat.spells.awakened_kits import get_awakened_basic_strike
from mechanics.social.attributes import calculate_combat_attributes
from mechanics.stealth import set_actor_combat_vanished

from .formulas import get_elemental_multiplier, try_inflict_status
from .status_effects import HARD_CC_NAMES, apply_status_effect, normalize_status_effect
from .targeting import apply_boss_cc_stagger_surge, update_threat_on_action


def apply_status_with_boss_surge(
    enemy_obj: Dict[str, Any],
    enemy_attrs: Optional[Dict[str, Any]],
    status_tag: str,
    boss_telegraph_state: Dict[str, Any],
    combat_log: list[str],
    use_try_inflict: bool = True,
    source: str = "player_spell",
) -> None:
    """Intercepts Hard CC against telegraphing bosses into +50% Stagger Surge."""
    norm_name = normalize_status_effect(status_tag)["name"].strip().lower()
    if (
        enemy_obj.get("telegraphed_skill")
        and norm_name in HARD_CC_NAMES
        and norm_name != "staggered"
        and apply_boss_cc_stagger_surge(
            enemy_obj,
            status_tag,
            boss_telegraph_state,
            combat_log=combat_log,
        )
    ):
        return
    if use_try_inflict:
        try_inflict_status(enemy_obj, enemy_attrs or {}, status_tag, combat_log)
    else:
        apply_status_effect(enemy_obj, status_tag, source=source)


def resolve_player_spell_action(
    ctx: Dict[str, Any],
    tier: str,
    target_enemy: Dict[str, Any],
    enemy_attrs: Dict[str, Any],
    enemy_armor: Dict[str, Any],
    pre_mark_fn: Callable[[Dict[str, Any], int, str], Tuple[int, str]],
    post_resolve_fn: Callable[[Dict[str, Any], int, str], None],
) -> None:
    """Resolves a player spell or innate awakened attack during Phase 1."""
    action = ctx["action"]
    acting_char_data = ctx["acting_char_data"]
    acting_char_name = ctx["acting_char_name"]
    acting_user_id = ctx["acting_user_id"]
    session = ctx["session"]
    enemies = ctx["enemies"]
    living_allies = ctx["living_allies"]
    current_npcs = ctx["current_npcs"]
    active_constructs = ctx["active_constructs"]
    combat_log = ctx["combat_log"]
    player_attrs = ctx["player_attrs"]
    weapon_item = ctx["weapon_item"]
    is_anom_combat = ctx["is_anom_combat"]
    is_vanished = ctx["is_vanished"]
    p_attr = ctx["p_attr"]
    p_med = ctx["p_med"]
    boss_telegraph_state = ctx["boss_telegraph_state"]
    threat_matrix = ctx["threat_matrix"]
    sticky_taunts = ctx["sticky_taunts"]
    player_mp_change_by_name = ctx["player_mp_change_by_name"]
    player_heal_by_name = ctx["player_heal_by_name"]
    apply_damage_to_enemy = ctx["apply_damage_to_enemy"]
    register_kill = ctx["register_kill"]
    ensure_construct_fn = ctx.get("ensure_autonomous_construct")

    spell_id = action.get("spell_id")
    if is_anom_combat and (action.get("is_basic_strike") or str(spell_id or "").startswith("awk_basic_")):
        spell = get_awakened_basic_strike(p_attr, p_med, equipped_weapon=weapon_item)
    else:
        spell = get_spell(spell_id) if spell_id else None

    mp_cost = spell.get("mp_cost", action.get("mp_cost", 0)) if spell else action.get("mp_cost", 0)
    if mp_cost > 0:
        acting_char_data["mp"] = max(0, acting_char_data.get("mp", 0) - mp_cost)
        player_mp_change_by_name[acting_char_name] = player_mp_change_by_name.get(acting_char_name, 0) - mp_cost

    if not spell:
        if tier in ("fail", "failure", "crit_fail"):
            combat_log.append(f"💨 **{acting_char_name}** cast magic on **{target_enemy['name']}**, but the spell missed!")
        else:
            m_dmg = max(10, int(player_attrs.get("matk", 20) * 1.2))
            if tier == "crit_success":
                m_dmg = int(round(m_dmg * 1.5))
            applied_dmg = apply_damage_to_enemy(target_enemy, m_dmg)
            ctx["total_enemy_damage"] += applied_dmg
            crit_tag = " *(Critical hit!)*" if tier == "crit_success" else ""
            combat_log.append(f"🔮 **{acting_char_name}** cast magic on **{target_enemy['name']}**: Dealt **{applied_dmg} damage**{crit_tag}.")
        return

    raw_sp_prog = acting_char_data.get("skill_progress") if isinstance(acting_char_data, dict) else None
    if isinstance(raw_sp_prog, str):
        try:
            raw_sp_prog = json.loads(raw_sp_prog)
        except Exception:
            raw_sp_prog = {}
    emp_list = (raw_sp_prog or {}).get("empowered_granted_spells") if isinstance(raw_sp_prog, dict) else None
    is_dup_emp = bool(spell_id in emp_list) if isinstance(emp_list, list) else bool(spell.get("duplicate_empowered"))
    eff_spell = dict(spell, duplicate_empowered=is_dup_emp)
    emp_mult = 1.20 if is_dup_emp else 1.0
    if spell.get("unavoidable") and tier in ("fail", "failure", "crit_fail"):
        tier = "success"
    if spell.get("is_pact_skill") and action.get("is_lethal_overdraw"):
        combat_log.append(
            f"🩸 **LETHAL OVERDRAW!** **{acting_char_name}** pours their remaining lifeblood into **{spell['name']}** — the invocation erupts at full power before collapse!"
        )

    discipline = spell.get("discipline", "attack")
    target_type = spell.get("target_type", "single")
    if is_anom_combat:
        if spell.get("is_ultimate"):
            ctx["turn_cast_ultimate"] = True
        if spell.get("resummons_construct") and p_med == "autonomous_construct" and ensure_construct_fn:
            re_c = ensure_construct_fn(acting_char_data, living_allies, force_resummon=True, current_npcs=current_npcs)
            if re_c and re_c not in active_constructs:
                active_constructs.append(re_c)
            combat_log.append(f"🤖 **{acting_char_name}** re-deployed **{re_c['name']}** via Heavy Resonance!")

    crit_bonus = spell.get("crit_bonus", 0.0)
    glance_floor = spell.get("glance_floor", 0.35)

    def _apply_spell_to_enemy(m: Dict[str, Any], damage_mult: float = 1.0) -> Tuple[int, Dict[str, Any], Dict[str, Any]]:
        m_arch = m.get("archetype", "Brute")
        m_armor = get_enemy_armor_profile(m_arch)
        m_attrs = calculate_combat_attributes(m.get("stats", {}))
        m_attrs.update({
            "weaknesses": m.get("weaknesses", []),
            "resistances": m.get("resistances", []),
            "immunities": m.get("immunities", []),
            "physicality": m.get("physicality", "corporeal"),
        })
        sp_dmg_t = str(spell.get("damage_type") or spell.get("source_element") or "magical").lower()
        if str(m.get("physicality") or "").lower() == "non_corporeal" and sp_dmg_t in ("physical", "ballistic", "slash", "blunt", "thrust"):
            return 0, m_armor, m_attrs
        elem_mult = get_elemental_multiplier({sp_dmg_t: 1.0}, m_armor, m_attrs)
        amp_map = player_attrs.get("elemental_amp") or {}
        if isinstance(amp_map, dict) and sp_dmg_t in amp_map:
            elem_mult *= (1.0 + max(0.0, float(amp_map[sp_dmg_t])))
        base_dmg = calculate_spell_damage(
            player_attrs.get("matk", 20),
            eff_spell,
            elem_mult,
            defender_attrs=m_attrs,
            armor_type_dt={} if spell.get("pierces_dt") else m_armor.get("type_dt", {}),
            armor_base_dt=0 if spell.get("pierces_dt") else m_armor.get("base_dt", 0),
        )
        if spell.get("strips_shields") and int(m.get("temp_hp", 0) or 0) > 0:
            m["temp_hp"] = 0
        base_dmg = int(round(base_dmg * damage_mult))
        return base_dmg, m_armor, m_attrs

    def _resolve_hit_tier(dmg: int, tier_val: str, is_chain_bounce: bool = False) -> int:
        if tier_val == "crit_success":
            return int(round(dmg * (1.5 + crit_bonus)))
        if tier_val in ("fail", "failure", "crit_fail"):
            if target_type == "aoe":
                return max(1, int(round(dmg * glance_floor)))
            if is_chain_bounce:
                return max(1, int(round(dmg * 0.5)))
            return 0
        return dmg

    if discipline == "attack":
        if is_vanished or any("invisib" in normalize_status_effect(s)["name"].lower() for s in acting_char_data.get("status_effects", [])):
            acting_char_data["status_effects"] = [
                s for s in acting_char_data.get("status_effects", [])
                if "hidden in shadows" not in normalize_status_effect(s)["name"].lower()
                and "invisib" not in normalize_status_effect(s)["name"].lower()
            ]
            if isinstance(session, dict):
                set_actor_combat_vanished(session, False, user_id=acting_user_id, also_set_hidden=False)

        if target_type == "aoe":
            is_glancing = tier in ("fail", "failure", "crit_fail")
            first = True
            for m in enemies:
                if m.get("hp", 0) <= 0:
                    continue
                raw_dmg, _, m_attrs = _apply_spell_to_enemy(m)
                dmg = _resolve_hit_tier(raw_dmg, tier)
                _shred_aoe, _attr_aoe = pre_mark_fn(
                    m, int(spell.get("stability_shred", 20) or 20), spell.get("awakened_attribute") or spell.get("source_element") or p_attr
                )
                apply_damage_to_enemy(m, dmg)
                if dmg > 0:
                    post_resolve_fn(m, _shred_aoe, _attr_aoe)
                ctx["total_enemy_damage"] += dmg
                glance_tag = " *(Glancing blast!)*" if is_glancing else ""
                if first:
                    combat_log.append(
                        f"🔮 **{acting_char_name}** cast **{spell['name']}** on **{m['name']}**: Dealt **{dmg} damage**{glance_tag}."
                    )
                    first = False
                else:
                    combat_log.append(f"   ↳ **{m['name']}**: **{dmg} damage**{glance_tag}.")
                if spell.get("status_ailment"):
                    apply_status_with_boss_surge(
                        m, m_attrs, f"{spell['status_ailment']} [{spell.get('duration', 2)} turns]", boss_telegraph_state, combat_log
                    )

        elif target_type == "chain":
            living = [m for m in enemies if m.get("hp", 0) > 0]
            max_bounces = spell.get("max_bounces", 3)
            decay_rate = spell.get("decay_rate", 0.25)
            targets = living[:max_bounces]
            for bounce_idx, m in enumerate(targets):
                bounce_mult = (1.0 - decay_rate) ** bounce_idx
                raw_dmg, _, m_attrs = _apply_spell_to_enemy(m, damage_mult=bounce_mult)
                dmg = _resolve_hit_tier(raw_dmg, tier, is_chain_bounce=(bounce_idx > 0))
                _shred_ch, _attr_ch = pre_mark_fn(
                    m, int(spell.get("stability_shred", 20) or 20), spell.get("awakened_attribute") or spell.get("source_element") or p_attr
                )
                apply_damage_to_enemy(m, dmg)
                if dmg > 0:
                    post_resolve_fn(m, _shred_ch, _attr_ch)
                ctx["total_enemy_damage"] += dmg
                if bounce_idx == 0:
                    combat_log.append(
                        f"⚡ **{acting_char_name}** cast **{spell['name']}** on **{m['name']}**: Dealt **{dmg} damage**."
                    )
                else:
                    pct = int(bounce_mult * 100)
                    combat_log.append(f"   ↳ Arc ricochets to **{m['name']}** ({pct}%): **{dmg} damage**.")
                if spell.get("status_ailment"):
                    apply_status_with_boss_surge(
                        m, m_attrs, f"{spell['status_ailment']} [{spell.get('duration', 2)} turns]", boss_telegraph_state, combat_log
                    )

        else:
            sp_dmg_st = str(spell.get("damage_type") or spell.get("source_element") or "magical").lower()
            if str(target_enemy.get("physicality") or "").lower() == "non_corporeal" and sp_dmg_st in ("physical", "ballistic", "slash", "blunt", "thrust"):
                m_dmg = 0
                combat_log.append(
                    f"🛡️ **{target_enemy['name']}** is **Non-Corporeal** — physical resonance from **{spell['name']}** phased harmlessly through it (0 damage)!"
                )
            else:
                elem_mult = get_elemental_multiplier({sp_dmg_st: 1.0}, enemy_armor, enemy_attrs)
                amp_map_st = player_attrs.get("elemental_amp") or {}
                if isinstance(amp_map_st, dict) and sp_dmg_st in amp_map_st:
                    elem_mult *= (1.0 + max(0.0, float(amp_map_st[sp_dmg_st])))
                if spell.get("strips_shields") and int(target_enemy.get("temp_hp", 0) or 0) > 0:
                    target_enemy["temp_hp"] = 0
                m_dmg = calculate_spell_damage(
                    player_attrs.get("matk", 20),
                    eff_spell,
                    elem_mult,
                    defender_attrs=enemy_attrs,
                    armor_type_dt={} if spell.get("pierces_dt") else enemy_armor.get("type_dt", {}),
                    armor_base_dt=0 if spell.get("pierces_dt") else enemy_armor.get("base_dt", 0),
                )
                m_dmg = _resolve_hit_tier(m_dmg, tier)

            if m_dmg > 0:
                _shred_st, _attr_st = pre_mark_fn(
                    target_enemy,
                    int(spell.get("stability_shred", 20) or 20),
                    spell.get("attack_attribute") or spell.get("awakened_attribute") or spell.get("source_element") or p_attr,
                )
                apply_damage_to_enemy(target_enemy, m_dmg)
                post_resolve_fn(target_enemy, _shred_st, _attr_st)
                ctx["total_enemy_damage"] += m_dmg
                crit_tag = " *(Critical hit!)*" if tier == "crit_success" else ""
                combat_log.append(
                    f"🔮 **{acting_char_name}** cast **{spell['name']}** on **{target_enemy['name']}**: Dealt **{m_dmg} damage**{crit_tag}."
                )
                if spell.get("status_ailment"):
                    apply_status_with_boss_surge(
                        target_enemy, enemy_attrs, f"{spell['status_ailment']} [{spell.get('duration', 2)} turns]", boss_telegraph_state, combat_log
                    )
            else:
                combat_log.append(
                    f"💨 **{acting_char_name}** cast **{spell['name']}** on **{target_enemy['name']}**, but the spell missed!"
                )

        spell_affixes = spell.get("affixes", [])
        if ctx["total_enemy_damage"] > 0:
            if "vampiric" in spell_affixes:
                leech_val = max(1, int(round(ctx["total_enemy_damage"] * 0.25)))
                max_hp = acting_char_data.get("max_hp", 100)
                old_hp = acting_char_data.get("hp", 0)
                acting_char_data["hp"] = min(max_hp, old_hp + leech_val)
                actual_leech = acting_char_data["hp"] - old_hp
                player_heal_by_name[acting_char_name] = player_heal_by_name.get(acting_char_name, 0) + actual_leech
                combat_log.append(f"🩸 **{acting_char_name}** siphoned **{actual_leech} HP** with Vampiric Touch!")

            if "twinned" in spell_affixes and random.random() < 0.25 and target_enemy.get("hp", 0) > 0:
                echo_dmg = max(1, int(round(ctx["total_enemy_damage"] * 0.5)))
                apply_damage_to_enemy(target_enemy, echo_dmg)
                ctx["total_enemy_damage"] += echo_dmg
                combat_log.append(f"✨ **Twinned** echo triggers! **{target_enemy['name']}** struck for **{echo_dmg} damage**!")

        if ("cleansing" in spell_affixes or spell.get("cleanses_debuff") or spell.get("cleanses_party")) and acting_char_data.get("status_effects"):
            if spell.get("cleanses_party"):
                acting_char_data["status_effects"] = [
                    s for s in acting_char_data["status_effects"]
                    if not any(neg in normalize_status_effect(s)["name"] for neg in ("Bleed", "Poison", "Burn", "Stun", "Weak", "Blind", "Chill", "Curse", "Disrupt"))
                ]
                combat_log.append(f"✨ **{acting_char_name}**'s Entity Covenant purged negative afflictions!")
            else:
                cleansed = acting_char_data["status_effects"].pop(0)
                cleansed_nm = normalize_status_effect(cleansed)["name"]
                combat_log.append(f"✨ **{acting_char_name}** cleansed **{cleansed_nm}**!")

        if spell.get("is_pact_skill"):
            if ctx["total_enemy_damage"] > 0 and spell.get("lifesteal_pct") and not action.get("is_lethal_overdraw"):
                _ls_val = max(1, int(round(ctx["total_enemy_damage"] * float(spell["lifesteal_pct"]))))
                _old_h = int(acting_char_data.get("hp", 0) or 0)
                acting_char_data["hp"] = min(int(acting_char_data.get("max_hp", 100) or 100), _old_h + _ls_val)
                _gained_h = acting_char_data["hp"] - _old_h
                if _gained_h > 0:
                    player_heal_by_name[acting_char_name] = player_heal_by_name.get(acting_char_name, 0) + _gained_h
                    combat_log.append(f"🩸 **{acting_char_name}** devoured **{_gained_h} HP** via **{spell['name']}**!")
            if spell.get("execute_threshold") and target_enemy.get("hp", 0) > 0 and not target_enemy.get("is_boss") and not target_enemy.get("sparring"):
                _ex_cap = max(1, int(round(target_enemy.get("max_hp", 100) * float(spell["execute_threshold"]))))
                if target_enemy["hp"] <= _ex_cap:
                    target_enemy["hp"] = 0
                    register_kill(target_enemy)
                    combat_log.append(f"⚰️ **COVENANT EXECUTION!** **{spell['name']}** reaped **{target_enemy['name']}** outright!")
            if spell.get("enters_stealth"):
                apply_status_effect(acting_char_data, "Hidden in Shadows [2 turns]", source="pact_skill")
                if isinstance(session, dict):
                    set_actor_combat_vanished(session, True, user_id=acting_user_id, also_set_hidden=False)
                combat_log.append(f"🌑 **{acting_char_name}** slipped into anomalous shadow veil!")
            if spell.get("grants_temp_hp_pct"):
                _thp_p = max(4, int(round(acting_char_data.get("max_hp", 70) * float(spell["grants_temp_hp_pct"]))))
                acting_char_data["temp_hp"] = max(int(acting_char_data.get("temp_hp", 0) or 0), _thp_p)
                combat_log.append(f"🛡️ **{acting_char_name}** gained **+{_thp_p} Temp Barrier**!")
            if spell.get("self_status_ailment"):
                apply_status_effect(acting_char_data, str(spell["self_status_ailment"]), source="pact_skill")
        if is_anom_combat and spell.get("party_temp_hp_shield"):
            sh_v = int(spell["party_temp_hp_shield"])
            acting_char_data["temp_hp"] = max(int(acting_char_data.get("temp_hp", 0) or 0), sh_v)
        if is_anom_combat and p_med == "autonomous_construct" and not spell.get("is_ultimate"):
            c_unit = next((c for c in living_allies if c.get("is_autonomous_construct") and c.get("hp", 0) > 0), None)
            if c_unit is not None:
                c_unit["queued_windup"] = {
                    "name": f"{spell['name']} Overdrive",
                    "damage": max(12, int(round(c_unit.get("atk", 15) * 1.35))),
                    "attr": p_attr,
                    "_queued_this_round": True,
                }

    elif discipline == "support":
        if spell.get("temp_hp_shield"):
            acting_char_data["temp_hp"] = max(int(acting_char_data.get("temp_hp", 0) or 0), int(spell["temp_hp_shield"]))
        if spell.get("grants_temp_hp_pct"):
            _sup_thp = max(4, int(round(acting_char_data.get("max_hp", 70) * float(spell["grants_temp_hp_pct"]))))
            acting_char_data["temp_hp"] = max(int(acting_char_data.get("temp_hp", 0) or 0), _sup_thp)
        if spell.get("cleanses_party") and acting_char_data.get("status_effects"):
            acting_char_data["status_effects"] = [
                s for s in acting_char_data["status_effects"]
                if not any(neg in normalize_status_effect(s)["name"] for neg in ("Bleed", "Poison", "Burn", "Stun", "Weak", "Blind", "Chill", "Curse", "Disrupt"))
            ]
        if spell.get("enters_stealth"):
            apply_status_effect(acting_char_data, "Hidden in Shadows [2 turns]", source="support_spell")
            if isinstance(session, dict):
                set_actor_combat_vanished(session, True, user_id=acting_user_id, also_set_hidden=False)
        if spell.get("self_status_ailment"):
            apply_status_effect(acting_char_data, str(spell["self_status_ailment"]), source="support_spell")
        if spell.get("mono_attribute_buff"):
            apply_status_effect(acting_char_data, f"Harmony ({spell['mono_attribute_buff'].title()}) [2 turns]", source="support_spell")
        if spell.get("heal_self_pct") or spell.get("heals_party_pct"):
            _hp_pct_s = float(spell.get("heals_party_pct") or spell.get("heal_self_pct") or 0.25)
            heal_val = max(4, int(round(acting_char_data.get("max_hp", 70) * _hp_pct_s * emp_mult)))
            if not action.get("is_lethal_overdraw"):
                acting_char_data["hp"] = min(acting_char_data.get("max_hp", 100), acting_char_data.get("hp", 0) + heal_val)
                player_heal_by_name[acting_char_name] = player_heal_by_name.get(acting_char_name, 0) + heal_val
            combat_log.append(f"💚 **{acting_char_name}** invoked **{spell['name']}**: Restored **{heal_val} HP**.")
        elif "heal_amount" in spell:
            heal_val = int(round(spell["heal_amount"] * emp_mult))
            if tier == "crit_success":
                heal_val = int(round(heal_val * 1.4))
            acting_char_data["hp"] = min(acting_char_data.get("max_hp", 100), acting_char_data.get("hp", 0) + heal_val)
            player_heal_by_name[acting_char_name] = player_heal_by_name.get(acting_char_name, 0) + heal_val
            combat_log.append(f"💚 **{acting_char_name}** cast **{spell['name']}**: Restored **{heal_val} HP**.")
        elif "mp_amount" in spell:
            mp_gain = int(round(spell["mp_amount"] * emp_mult))
            acting_char_data["mp"] = min(acting_char_data.get("max_mp", 100), acting_char_data.get("mp", 0) + mp_gain)
            player_mp_change_by_name[acting_char_name] = player_mp_change_by_name.get(acting_char_name, 0) + mp_gain
            combat_log.append(f"💙 **{acting_char_name}** cast **{spell['name']}**: Restored **{mp_gain} MP**.")
        else:
            buff_tag = spell.get("status_ailment", "Fortified")
            dur = spell.get("duration", 2)
            apply_status_effect(acting_char_data, f"{buff_tag} [{dur} turns]", source="support_spell")
            buff_pct = int(round(spell.get("buff_pct", 0.15) * emp_mult * 100))
            combat_log.append(f"✨ **{acting_char_name}** cast **{spell['name']}**: Gained **+{buff_pct}% {spell.get('stat_target', 'DEF')}** for {dur} turns.")

    elif discipline == "curse":
        debuff_tag = spell.get("status_ailment", "Weakened")
        dur = spell.get("duration", 2)
        debuff_pct = int(round(spell.get("debuff_pct", 0.15) * emp_mult * 100))
        eff_str = f"{debuff_tag} [{dur} turns]"
        if target_type == "aoe":
            for m in enemies:
                apply_status_with_boss_surge(m, enemy_attrs, eff_str, boss_telegraph_state, combat_log, use_try_inflict=False)
            combat_log.append(
                f"💀 **{acting_char_name}** cast **{spell['name']}** over all enemies: Inflicted **-{debuff_pct}% {spell.get('stat_target', 'ATK')}** for {dur} turns."
            )
        else:
            apply_status_with_boss_surge(target_enemy, enemy_attrs, eff_str, boss_telegraph_state, combat_log, use_try_inflict=False)
            combat_log.append(
                f"💀 **{acting_char_name}** cast **{spell['name']}** on **{target_enemy['name']}**: Inflicted **-{debuff_pct}% {spell.get('stat_target', 'ATK')}** for {dur} turns."
            )

    elif discipline == "summon":
        template_key = spell.get("summon_template", "spirit_wolf")
        template = SUMMON_TEMPLATES.get(template_key, SUMMON_TEMPLATES["spirit_wolf"])
        s_count = spell.get("summon_count", template.get("count", 1))
        s_dur = spell.get("summon_duration", template.get("duration", 3))
        s_arch = spell.get("summon_archetype", template.get("archetype", "Skirmisher"))
        c_lvl = acting_char_data.get("level", 1)
        s_hp = template.get("base_hp", 20) + (c_lvl * template.get("hp_per_level", 5))
        s_name = template.get("name", "Summoned Minion")
        for idx in range(s_count):
            minion_name = f"{s_name} #{idx+1}" if s_count > 1 else s_name
            summon_npc = {
                "name": minion_name,
                "archetype": s_arch,
                "level": c_lvl,
                "hp": s_hp,
                "max_hp": s_hp,
                "summon_duration": s_dur,
                "is_summon": True,
                "stats": {
                    "STR": 4 + c_lvl, "AGI": 4 + c_lvl, "INT": 4 + c_lvl,
                    "PER": 4 + c_lvl, "END": 4 + c_lvl, "CHA": 1, "LUK": 1,
                },
            }
            current_npcs.append(summon_npc)
            living_allies.append(summon_npc)
        combat_log.append(f"🔮 **{acting_char_name}** cast **{spell['name']}**: Summoned **{s_count}x {s_name}** for {s_dur} turns!")

    if player_heal_by_name.get(acting_char_name, 0) > 0 and discipline == "support":
        all_eids = [str(e.get("id") or e.get("name")) for e in enemies if e.get("hp", 0) > 0]
        update_threat_on_action(
            threat_matrix,
            str(acting_char_name),
            "heal",
            [],
            all_eids,
            effective_healing=int(player_heal_by_name[acting_char_name]),
            sticky_taunts=sticky_taunts,
        )
