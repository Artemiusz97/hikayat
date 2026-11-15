"""mechanics/combat/player_turn.py

Phase 1 Active Player Turn resolution: equipment & attribute modifiers,
Anomalous Resonance stability shred / break / pips, taboo evaluation,
Guard Focus (+15% Max MP), tactical maneuvers, physical attacks, and
synchronized multi-player / co-op actions.
"""
from __future__ import annotations

import random
import re
from typing import Any, Dict, Tuple

import db
from mechanics.combat.awakened_resonance import (
    apply_stability_and_break, compute_stability_shred,
    ensure_autonomous_construct, get_starting_encounter_pips, update_encounter_pips,
)
from mechanics.combat.enemies import get_enemy_armor_profile, get_enemy_weapon_profile
from mechanics.combat.equipment import parse_equipment_metadata
from mechanics.combat.items.anomalous_gear import aggregate_equipped_anomalous_passives
from mechanics.combat.items.consumables import parse_item_effect
from mechanics.combat.spells.awakened_kits import (
    derive_default_3axis, get_awakened_basic_strike, normalize_anomalous_attribute,
)
from mechanics.social.attributes import calculate_combat_attributes
from mechanics.stealth import is_actor_combat_vanished, is_actor_hidden, set_actor_combat_vanished
from skill_check import resolve_check

from .ally_turn import resolve_extra_player_actions
from .formulas import calculate_tactical_damage, try_inflict_status
from .player_spells import apply_status_with_boss_surge, resolve_player_spell_action
from .reconcile import _enemy_has_unsealed_tether
from .status_effects import apply_status_effect, get_status_stat_modifiers, normalize_status_effect
from .targeting import apply_boss_cc_stagger_surge, update_threat_on_action


def _apply_status_or_boss_surge(target_obj: Dict[str, Any], status_tag: str, boss_telegraph_state: Dict[str, Any], combat_log: list[str], source: str = "player_action") -> None:
    apply_status_with_boss_surge(target_obj, None, status_tag, boss_telegraph_state, combat_log, use_try_inflict=False, source=source)


def resolve_player_combat_phase(ctx: Dict[str, Any]) -> None:
    """Executes Phase 1: primary player action + extra synchronized actions."""
    session = ctx["session"]
    party = ctx["party"]
    actions = ctx["actions"]
    enemies = ctx["enemies"]
    living_allies = ctx["living_allies"]
    current_npcs = ctx["current_npcs"]
    acting_char_data = ctx["acting_char_data"]
    acting_char_name = ctx["acting_char_name"]
    player_luk_val = ctx["player_luk_val"]
    is_anom_combat = ctx["is_anom_combat"]
    sess_id_cbt = ctx["sess_id_cbt"]
    combat_log = ctx["combat_log"]
    player_damage_by_name = ctx["player_damage_by_name"]
    player_heal_by_name = ctx["player_heal_by_name"]
    player_mp_change_by_name = ctx["player_mp_change_by_name"]
    threat_matrix = ctx["threat_matrix"]
    sticky_taunts = ctx["sticky_taunts"]
    boss_telegraph_state = ctx["boss_telegraph_state"]
    surrendered_enemies = ctx["surrendered_enemies"]
    surrendered_enemy_dicts = ctx["surrendered_enemy_dicts"]
    fled_enemies = ctx["fled_enemies"]
    items_consumed_this_turn = ctx["items_consumed_this_turn"]
    is_non_lethal_active = ctx["is_non_lethal_active"]
    apply_damage_to_enemy = ctx["apply_damage_to_enemy"]
    register_kill = ctx["register_kill"]

    acting_user_id = acting_char_data.get("user_id")
    preloaded_eq = session.get("_preloaded_equipment_by_uid") if isinstance(session, dict) else None
    acting_uid_int = int(acting_user_id or 0) if acting_user_id else 0
    if acting_uid_int and isinstance(preloaded_eq, dict) and acting_uid_int in preloaded_eq:
        player_equip = preloaded_eq[acting_uid_int] or {}
    else:
        player_equip = db.get_equipment(acting_user_id) if acting_user_id else {}
    equipped_list = [item for item in player_equip.values() if item] if player_equip else []

    weapon_item = player_equip.get("Weapon") if player_equip else None
    armor_item = player_equip.get("Armor") if player_equip else None

    player_weapon = parse_equipment_metadata(weapon_item) if weapon_item else {}
    player_armor = parse_equipment_metadata(armor_item) if armor_item else {}
    player_attrs = calculate_combat_attributes(acting_char_data, equipped_list, scenario=session.get("scenario", "fantasy"), allow_non_combat=True)
    player_attrs["combat_turn"] = session.get("combat_turn", 1)
    if any(t in player_attrs.get("tags", []) for t in ("precision", "optics", "hud", "smart_link")):
        player_attrs["acc"] += 5

    # Wire canonical StatusEffectInstance stat modifiers for player
    p_mods = get_status_stat_modifiers(acting_char_data)
    if p_mods.get("accuracy_bonus"):
        player_attrs["acc"] = int(player_attrs.get("acc", 66) + p_mods["accuracy_bonus"])
    if p_mods.get("damage_dealt_mult", 1.0) != 1.0:
        d_mult = float(p_mods["damage_dealt_mult"])
        player_attrs["atk"] = max(1, int(round(player_attrs.get("atk", 15) * d_mult)))
        player_attrs["matk"] = max(1, int(round(player_attrs.get("matk", 15) * d_mult)))

    anom_passives: dict = dict(player_attrs.get("anomalous_passives") or {})
    if is_anom_combat and not anom_passives:
        try:
            anom_passives = aggregate_equipped_anomalous_passives(player_equip)
            if anom_passives.get("elemental_amp"):
                player_attrs["elemental_amp"] = dict(anom_passives["elemental_amp"])
        except Exception:
            anom_passives = {}

    action = actions[0] if actions else {"choice_type": "MELEE_ATTACK", "label": "Attack"}
    is_hidden_now = bool(is_actor_hidden(session, acting_user_id) or action.get("is_stealth") or action.get("stance") == "stealth")
    is_vanished = bool(
        is_actor_combat_vanished(session, acting_user_id)
        or any("hidden in shadows" in normalize_status_effect(s)["name"].lower() for s in acting_char_data.get("status_effects", []))
    )
    player_attrs["combat_vanished"] = is_vanished
    player_attrs["is_ambush"] = bool(session.get("is_ambush") or (is_hidden_now and player_attrs["combat_turn"] <= 1))

    if player_attrs["is_ambush"] and player_attrs["combat_turn"] <= 1:
        for m in enemies:
            if m.get("hp", 0) > 0 and not any("surprised" in normalize_status_effect(s)["name"].lower() for s in m.get("status_effects", [])):
                _apply_status_or_boss_surge(m, "Surprised [1 turn]", boss_telegraph_state, combat_log, source="ambush")
        combat_log.append("⚡ **Surprise Round!** Caught completely off-guard by the ambush, enemies are stunned for Turn 1!")

    c_type = action.get("choice_type", "MELEE_ATTACK")
    stat_name = action.get("stat", "STR")
    req_val = action.get("requirement", 10)

    p_attr, p_arch, p_med = ("physical", "vanguard", "direct_manifestation")
    pips_map: dict[str, int] = {}
    uid_pip_key = str(acting_user_id or acting_char_name)

    if is_anom_combat:
        def_a, def_ar, def_m = derive_default_3axis(
            char_class=str(acting_char_data.get("char_class") or ""),
            seed=acting_char_name,
        )
        p_attr = normalize_anomalous_attribute(acting_char_data.get("attribute") or def_a, fallback=def_a)
        p_arch = str(acting_char_data.get("combat_archetype") or def_ar).strip().lower()
        p_med = str(acting_char_data.get("ability_medium") or def_m).strip().lower()
        if isinstance(session, dict):
            raw_pm = session.get("player_resonance_pips")
            if isinstance(raw_pm, dict):
                pips_map = dict(raw_pm)
            elif isinstance(raw_pm, (int, float)):
                pips_map = {uid_pip_key: max(0, min(3, int(raw_pm)))}
            else:
                pips_map = {}
            if uid_pip_key not in pips_map:
                pips_map[uid_pip_key] = get_starting_encounter_pips(int(acting_char_data.get("level", 1) or 1))

    ctx.update({
        "action": action,
        "acting_user_id": acting_user_id,
        "player_weapon": player_weapon,
        "player_armor": player_armor,
        "player_attrs": player_attrs,
        "anom_passives": anom_passives,
        "weapon_item": weapon_item,
        "c_type": c_type,
        "is_vanished": is_vanished,
        "p_attr": p_attr,
        "p_arch": p_arch,
        "p_med": p_med,
        "pips_map": pips_map,
        "uid_pip_key": uid_pip_key,
        "turn_hit_landed": False,
        "turn_triggered_break": False,
        "turn_extra_pips": 0,
        "turn_cast_ultimate": False,
    })

    def _pre_mark_anomalous_hit(m_obj: dict, base_shred: int, atk_attr: str) -> Tuple[int, str]:
        if not is_anom_combat:
            return 0, "physical"
        norm_atk_a = normalize_anomalous_attribute(atk_attr, fallback=p_attr)
        cat_bonus = 0.25 if any("harmony" in normalize_status_effect(s)["name"].lower() for s in acting_char_data.get("status_effects", [])) else 0.0
        shred_val = compute_stability_shred(base_shred, norm_atk_a, p_arch, p_attr, m_obj, catalyst_bonus=cat_bonus)
        if not m_obj.get("is_breached") and int(m_obj.get("max_stability", 0) or 0) > 0:
            if int(m_obj.get("stability", 100)) - shred_val <= 0:
                m_obj["_will_breach_this_hit"] = True
        if norm_atk_a == "aether":
            m_obj["_pierce_temp_hp_this_hit"] = True
        return shred_val, norm_atk_a

    def _post_resolve_anomalous_hit(m_obj: dict, shred_val: int, norm_atk_a: str) -> None:
        if not is_anom_combat:
            return
        m_obj.pop("_will_breach_this_hit", None)
        m_obj.pop("_pierce_temp_hp_this_hit", None)
        ctx["turn_hit_landed"] = True
        if m_obj.get("hp", 0) <= 0 and not m_obj.get("is_breached"):
            return
        atk_power = max(player_attrs.get("matk", 20), player_attrs.get("atk", 20))
        br_res = apply_stability_and_break(m_obj, shred_val, norm_atk_a, atk_power, combat_log, non_lethal_mode=is_non_lethal_active)
        if br_res["triggered_break"]:
            m_obj["_breached_this_round"] = True
            ctx["turn_triggered_break"] = True
            ctx["turn_extra_pips"] += int(br_res.get("bonus_pips", 0) or 0)
            if m_obj.get("telegraphed_skill"):
                apply_boss_cc_stagger_surge(
                    m_obj,
                    "Staggered [1 turn]",
                    boss_telegraph_state,
                    combat_log=combat_log,
                    is_stability_breach=True,
                )
            if br_res.get("mp_refund", 0) > 0:
                mp_ref = int(br_res["mp_refund"])
                acting_char_data["mp"] = min(acting_char_data.get("max_mp", 100), acting_char_data.get("mp", 0) + mp_ref)
                player_mp_change_by_name[acting_char_name] = player_mp_change_by_name.get(acting_char_name, 0) + mp_ref
            if br_res.get("squad_heal", 0) > 0:
                sh_amt = int(br_res["squad_heal"])
                acting_char_data["hp"] = min(acting_char_data.get("max_hp", 100), acting_char_data.get("hp", 0) + sh_amt)
                player_heal_by_name[acting_char_name] = player_heal_by_name.get(acting_char_name, 0) + sh_amt
            other_foes = [f for f in enemies if f is not m_obj and f.get("hp", 0) > 0]
            if splash := int(br_res.get("aoe_splash_damage", 0) or 0):
                if other_foes:
                    for of in other_foes:
                        apply_damage_to_enemy(of, splash)
                        ctx["total_enemy_damage"] += splash
                    combat_log.append(f"🌪️ **Vacuum Shear (AoE Splash):** Dealt **{splash} damage** to secondary foes!")
            elif chain := int(br_res.get("chain_damage", 0) or 0):
                if other_foes:
                    apply_damage_to_enemy(other_foes[0], chain)
                    ctx["total_enemy_damage"] += chain
                    combat_log.append(f"⚡ **Grid Overload (Chain Arc):** Arced to **{other_foes[0]['name']}** for **{chain} damage**!")
        elif br_res.get("super_break_damage", 0) > 0:
            sb = int(br_res["super_break_damage"])
            apply_damage_to_enemy(m_obj, sb)
            ctx["total_enemy_damage"] += sb

    req_target = str(
        action.get("combat_target") or action.get("target_entity") or action.get("target_npc") or action.get("target_enemy") or action.get("target") or ""
    ).strip().lower()
    target_enemy = None

    if req_target:
        target_enemy = next(
            (m for m in enemies if m.get("hp", 0) > 0 and (
                str(m.get("id")) == req_target or str(m.get("enemy_id")) == req_target or m["name"].lower() == req_target
            )), None
        ) or next(
            (m for m in enemies if m.get("hp", 0) > 0 and (
                req_target in m["name"].lower() or m["name"].lower() in req_target
            )), None
        )

    if not target_enemy and action.get("label"):
        lbl_lower = action["label"].lower()
        target_enemy = next(
            (m for m in enemies if m.get("hp", 0) > 0 and m["name"].lower() in lbl_lower),
            None,
        )

    if not target_enemy:
        target_enemy = next((m for m in enemies if m.get("hp", 0) > 0), enemies[0] if enemies else None)

    if target_enemy:
        enemy_arch = target_enemy.get("archetype", "Brute")
        enemy_armor = get_enemy_armor_profile(enemy_arch)
        enemy_weapon = get_enemy_weapon_profile(enemy_arch)
        enemy_attrs = calculate_combat_attributes(target_enemy.get("stats", {}))
        enemy_attrs.update({
            "weaknesses": target_enemy.get("weaknesses", []),
            "resistances": target_enemy.get("resistances", []),
            "immunities": target_enemy.get("immunities", []),
            "physicality": target_enemy.get("physicality", "corporeal"),
        })

        if is_anom_combat and not action.get("incursion_non_damage_turn") and not action.get("is_subdue_contain") and (target_enemy.get("taboo") or isinstance(target_enemy.get("anomaly_blueprint"), dict)):
            try:
                from mechanics.world.anomaly_engine import evaluate_taboo_interaction
                bp_eval = target_enemy.get("anomaly_blueprint") if isinstance(target_enemy.get("anomaly_blueprint"), dict) else {
                    "name": target_enemy.get("name", "Anomaly"),
                    "taboo": target_enemy.get("taboo") or {},
                }
                act_cat_low = str(action.get("action_category") or "").lower()
                is_non_attack_tactic = (
                    c_type in ("DEFENSIVE_GUARD", "DIPLOMACY_TAUNT", "WEAKNESS_EXPLOIT", "EVADE_TACTICAL_FLEE", "STEALTH_VANISH")
                    or act_cat_low in ("tactics", "flee", "item", "consumable")
                    or bool(action.get("is_subdue_contain"))
                    or bool(action.get("is_taboo_exploit"))
                    or str(action.get("incursion_action") or "").lower() in ("subdue", "combat_persuade", "exploit_taboo", "sever_tether", "folklore_offering_rite")
                )
                if is_non_attack_tactic:
                    elem_eval = str(action.get("element") or "").lower()
                elif action.get("spell_id"):
                    from mechanics.combat.spells import get_spell as _get_sp_tb
                    sp_id_tb = action.get("spell_id")
                    if action.get("is_basic_strike") or str(sp_id_tb or "").startswith("awk_basic_"):
                        sp_tb = get_awakened_basic_strike(p_attr, p_med, equipped_weapon=weapon_item)
                    else:
                        sp_tb = _get_sp_tb(sp_id_tb)
                    sp_disc_tb = str((sp_tb or {}).get("discipline") or "attack").lower()
                    if sp_disc_tb in ("heal", "buff", "support", "shield", "cleanse"):
                        elem_eval = str(action.get("element") or "").lower()
                    else:
                        elem_eval = str(
                            action.get("element")
                            or (sp_tb or {}).get("damage_type")
                            or (sp_tb or {}).get("element")
                            or ""
                        ).lower()
                else:
                    elem_eval = str(
                        action.get("element")
                        or player_weapon.get("anomalous_element")
                        or p_attr
                        or ""
                    ).lower()
                taboo_res = evaluate_taboo_interaction(
                    bp_eval,
                    action=action,
                    stat_used=stat_name,
                    element_used=elem_eval,
                    action_text=str(action.get("label") or ""),
                )
                if taboo_res.get("exploited"):
                    target_enemy["taboo_exploited"] = True
                    target_enemy["taboo_seal_unlocked"] = True
                    req_val = max(2, int(req_val) - 3)
                    enemy_attrs["def"] = max(1, int(enemy_attrs.get("def", 15)) - 6)
                    enemy_attrs["mdef"] = max(1, int(enemy_attrs.get("mdef", 15)) - 6)
                    combat_log.append(f"🔓 **Taboo Exploited!** {taboo_res['message']} (**[🛡️ Subdue & Contain]** seal unlocked!)")
                elif taboo_res.get("violated"):
                    v_eff = taboo_res.get("violation_effect") or {}
                    combat_log.append(f"⚠️ **Taboo Violated!** {taboo_res['message']}")
                    if v_eff.get("type") == "heal_enemy":
                        h_e = max(4, int(target_enemy.get("max_hp", 80) * 0.12))
                        target_enemy["hp"] = min(target_enemy.get("max_hp", 80), target_enemy.get("hp", 10) + h_e)
                    else:
                        b_dmg = int(v_eff.get("value", 8) or 8)
                        acting_char_data["hp"] = max(1, acting_char_data.get("hp", 50) - b_dmg)
                        player_damage_by_name[acting_char_name] = player_damage_by_name.get(acting_char_name, 0) + b_dmg
            except Exception:
                pass

        if "check" in action:
            tier = action["check"].tier if hasattr(action["check"], "tier") else getattr(action["check"], "get", lambda k, d=None: d)("tier", "success")
        elif "tier" in action:
            tier = action["tier"]
        else:
            actor_stat = acting_char_data.get(f"{stat_name.lower()}_", acting_char_data.get(stat_name, 5))
            res = resolve_check(actor_stat, req_val, player_luk_val)
            tier = res.tier

        if action.get("incursion_non_damage_turn"):
            combat_log.append(
                f"🛡️ **{acting_char_name}** focused on containment procedures against **{target_enemy['name']}** without dealing lethal damage!"
            )

        elif (
            c_type in ("MAGIC_SPELL", "MAGIC_ATTACK")
            or action.get("action_category") == "magic"
            or "spell_id" in action
            or (stat_name == "INT" and c_type not in ("DEFENSIVE_GUARD", "DIPLOMACY_TAUNT", "WEAKNESS_EXPLOIT", "EVADE_TACTICAL_FLEE", "ENVIRONMENTAL_TRAP"))
        ):
            ctx["ensure_autonomous_construct"] = ensure_autonomous_construct
            resolve_player_spell_action(
                ctx,
                tier,
                target_enemy,
                enemy_attrs,
                enemy_armor,
                _pre_mark_anomalous_hit,
                _post_resolve_anomalous_hit,
            )

        elif stat_name == "ITEM":
            label_lower = action.get("label", "").lower()
            item_obj = action.get("item") or {}
            parsed_item = parse_item_effect(item_obj) if item_obj else parse_item_effect({"name": action.get("label", ""), "effect": ""})

            item_available = True
            if not action.get("item_consumed") and acting_user_id:
                consume_item_name = (action.get("item") or {}).get("name") or action.get("item_name")
                if not consume_item_name:
                    m_use = re.search(r"^(?:Use|Throw)\s+(.+?)(?:\s+on|\s+at|$)", action.get("label", ""), re.IGNORECASE)
                    consume_item_name = m_use.group(1).strip() if m_use else action.get("label", "").strip()
                if consume_item_name:
                    found_in_inv = False
                    if party and isinstance(party[0], (tuple, list)) and len(party[0]) > 1:
                        p_inv = party[0][1]
                        if isinstance(p_inv, list):
                            for idx, itm in enumerate(p_inv):
                                if isinstance(itm, dict) and itm.get("name", "").strip().lower() == consume_item_name.lower():
                                    p_inv.pop(idx)
                                    found_in_inv = True
                                    break
                    elif acting_user_id:
                        found_in_inv = any(i.get("name", "").strip().lower() == consume_item_name.lower() for i in db.get_inventory(acting_user_id))
                    else:
                        found_in_inv = True

                    if not found_in_inv:
                        item_available = False
                        combat_log.append(f"⚠️ **{acting_char_name}** reached for **{consume_item_name}**, but had none left in inventory!")
                    else:
                        action["item_consumed"] = True
                        items_consumed_this_turn.append(consume_item_name)

            if not item_available:
                pass
            elif parsed_item.get("damage", 0) > 0 or any(w in label_lower for w in ["bomb", "grenade", "flask", "throw", "acid", "poison", "molotov", "damage"]):
                base_throw_dmg = parsed_item.get("damage", 0)
                if base_throw_dmg <= 0:
                    base_throw_dmg = max(20, int(target_enemy.get("max_hp", 100) * 0.40) + 15)
                applied_dmg = apply_damage_to_enemy(target_enemy, base_throw_dmg)
                ctx["total_enemy_damage"] += applied_dmg
                combat_log.append(f"💣 **{acting_char_name}** threw **{action.get('label', 'Explosive')}**: Dealt **{applied_dmg} damage** to {target_enemy['name']}!")
                if parsed_item.get("inflict_status"):
                    for inf_st in parsed_item["inflict_status"]:
                        _apply_status_or_boss_surge(target_enemy, str(inf_st), boss_telegraph_state, combat_log, source="item_throw")
            elif parsed_item.get("hp_restore", 0) > 0 or parsed_item.get("mp_restore", 0) > 0:
                h_val = parsed_item.get("hp_restore", 0)
                m_val = parsed_item.get("mp_restore", 0)
                acting_char_data["hp"] = min(acting_char_data.get("max_hp", 100), acting_char_data.get("hp", 0) + h_val)
                player_heal_by_name[acting_char_name] = player_heal_by_name.get(acting_char_name, 0) + h_val
                if m_val > 0:
                    acting_char_data["mp"] = min(acting_char_data.get("max_mp", 100), acting_char_data.get("mp", 0) + m_val)
                    player_mp_change_by_name[acting_char_name] = player_mp_change_by_name.get(acting_char_name, 0) + m_val
                combat_log.append(f"🧪 **{acting_char_name}** consumed **{action.get('label', 'Potion')}**: Restored **+{h_val} HP**" + (f", **+{m_val} MP**" if m_val > 0 else "") + ".")
                if h_val > 0:
                    all_eids = [str(e.get("id") or e.get("name")) for e in enemies if e.get("hp", 0) > 0]
                    update_threat_on_action(threat_matrix, str(acting_char_name), "heal", [], all_eids, effective_healing=h_val, sticky_taunts=sticky_taunts)
            elif parsed_item.get("buffs"):
                buffs = parsed_item["buffs"]
                log_buffs = []
                dur = 3
                if "dt" in buffs:
                    apply_status_effect(acting_char_data, f"Iron Skin [+{buffs['dt']} DT] [{dur} turns]", source="item")
                    log_buffs.append(f"+{buffs['dt']} DT")
                if "dr" in buffs:
                    apply_status_effect(acting_char_data, f"Aegis Warding [+{int(buffs['dr'] * 100)}% DR] [{dur} turns]", source="item")
                    log_buffs.append(f"+{int(buffs['dr'] * 100)}% DR")
                if "atk_pct" in buffs:
                    apply_status_effect(acting_char_data, f"Combat Booster [+{int(buffs['atk_pct'] * 100)}% ATK] [{dur} turns]", source="item")
                    log_buffs.append(f"+{int(buffs['atk_pct'] * 100)}% ATK")
                if "eva" in buffs:
                    apply_status_effect(acting_char_data, f"Quickstep [+{buffs['eva']}% EVA] [{dur} turns]", source="item")
                    log_buffs.append(f"+{buffs['eva']}% EVA")
                combat_log.append(f"✨ **{acting_char_name}** consumed **{action.get('label', 'Booster')}**: Gained **{', '.join(log_buffs)}** for {dur} turns.")
            else:
                combat_log.append(f"🎒 **{acting_char_name}** used item: {action.get('label', 'Item')}.")

        elif c_type == "DEFENSIVE_GUARD" or action.get("action_category") == "guard":
            apply_status_effect(acting_char_data, "Defensive Guard [+6 DT, +30% Block] [1 turn]", source="guard")
            player_attrs["base_dt"] = player_attrs.get("base_dt", 0) + 6
            player_attrs["block_chance"] = player_attrs.get("block_chance", 0) + 30
            max_mp = int(acting_char_data.get("max_mp", 0) or 0)
            guard_mp_note = ""
            if max_mp > 0:
                cur_mp = int(acting_char_data.get("mp", 0) or 0)
                rec_mp = max(2, int(round(max_mp * 0.15)))
                new_mp = min(max_mp, cur_mp + rec_mp)
                gained_mp = max(0, new_mp - cur_mp)
                acting_char_data["mp"] = new_mp
                if gained_mp > 0:
                    player_mp_change_by_name[acting_char_name] = player_mp_change_by_name.get(acting_char_name, 0) + gained_mp
                    guard_mp_note = f" Restored **+{gained_mp} MP** via Guard Focus!"
            combat_log.append(
                f"🛡️ **{acting_char_name}** braces and assumes a defensive guard! (+6 DT and +30% Block chance for incoming attacks!){guard_mp_note}"
            )

        elif c_type == "DIPLOMACY_TAUNT" or action.get("action_category") == "taunt":
            if tier in ("crit_success", "success"):
                debuff_val = 25 if tier == "crit_success" else 15
                apply_status_effect(target_enemy, f"Demoralized [-{debuff_val}% ATK] [2 turns]", source="taunt")
                combat_log.append(f"🗣️ **{acting_char_name}** intimidates **{target_enemy['name']}**! They are demoralized and suffer -{debuff_val}% ATK!")
                target_eid = str(target_enemy.get("id") or target_enemy.get("name"))
                all_eids = [str(e.get("id") or e.get("name")) for e in enemies if e.get("hp", 0) > 0]
                update_threat_on_action(threat_matrix, str(acting_char_name), "taunt", [target_eid], all_eids, is_taunt=True, sticky_taunts=sticky_taunts)
            else:
                combat_log.append(f"🗣️ **{acting_char_name}** attempted to taunt **{target_enemy['name']}**, but they brushed off the insult!")

        elif c_type == "WEAKNESS_EXPLOIT" or action.get("action_category") == "exploit" or "scan" in action.get("label", "").lower():
            if tier in ("crit_success", "success"):
                res_list = target_enemy.get("resistances", [])
                weak_list = target_enemy.get("weaknesses", [])
                imm_list = target_enemy.get("immunities", [])
                r_str = f"Resistances: {', '.join(res_list)}" if res_list else "No resistances"
                w_str = f"Weaknesses: {', '.join(weak_list)}" if weak_list else "No weaknesses"
                i_str = f" | Immunities: {', '.join(imm_list)}" if imm_list else ""
                apply_status_effect(acting_char_data, "Weakpoint Analyzed [+15% ACC] [2 turns]", source="scan")
                scan_extra = ""
                if target_enemy.get("taboo") or isinstance(target_enemy.get("anomaly_blueprint"), dict):
                    target_enemy["dossier_revealed"] = True
                    if isinstance(target_enemy.get("anomaly_blueprint"), dict):
                        from mechanics.world.folklore_mechanics import unmask_blueprint_disguise
                        unmasked_bp, unmask_msg = unmask_blueprint_disguise(target_enemy["anomaly_blueprint"])
                        unmasked_bp["dossier_revealed"] = True
                        target_enemy["anomaly_blueprint"] = unmasked_bp
                        if unmask_msg:
                            target_enemy["name"] = str(unmasked_bp.get("canonical_name") or unmasked_bp.get("name") or target_enemy["name"])
                            target_enemy["is_disguised"] = False
                            scan_extra += f" | {unmask_msg}"
                        if sess_id_cbt:
                            try:
                                db.record_session_anomaly_field_log(int(sess_id_cbt), unmasked_bp, stage="verified")
                                if unmasked_bp.get("codex_id"):
                                    db.record_folklore_codex_progress(
                                        db.get_session_participant_user_ids(int(sess_id_cbt)) or ([acting_user_id] if acting_user_id else []),
                                        str(unmasked_bp["codex_id"]),
                                        stage="verified",
                                    )
                            except Exception:
                                pass
                        if sess_id_cbt and (target_enemy.get("incursion_id") or target_enemy.get("breach_id") or target_enemy.get("linked_quest_id")):
                            try:
                                from mechanics.world.anomalous_events import reveal_anomaly_dossier
                                _scan_inc = str(target_enemy.get("incursion_id") or target_enemy.get("breach_id") or "")
                                reveal_anomaly_dossier(
                                    session_id=int(sess_id_cbt),
                                    quest_id=str(target_enemy.get("linked_quest_id") or ""),
                                    incursion_id=_scan_inc,
                                    breach_id=_scan_inc,
                                )
                            except Exception:
                                pass
                    tb_scan = target_enemy.get("taboo") or (target_enemy.get("anomaly_blueprint") or {}).get("taboo") or {}
                    rule_txt = tb_scan.get("rule_text") or tb_scan.get("taboo_rule") or ""
                    hint_txt = tb_scan.get("exploit_hint") or tb_scan.get("containment_protocol") or ""
                    if isinstance(tb_scan, dict) and (rule_txt or hint_txt):
                        scan_extra += f" | 📜 Taboo: {rule_txt} ({hint_txt})"
                combat_log.append(f"👁️ **{acting_char_name}** scanned **{target_enemy['name']}**! {w_str} | {r_str}{i_str}.{scan_extra}")
            else:
                combat_log.append(f"👁️ **{acting_char_name}** scanned **{target_enemy['name']}**, but could not expose a clear weakness.")

        elif c_type == "EVADE_TACTICAL_FLEE" or action.get("action_category") == "flee" or "flee" in action.get("label", "").lower() or "disengage" in action.get("label", "").lower():
            if tier in ("crit_success", "success"):
                ctx["fled_battle"] = True
                combat_log.append(f"🏃 **{acting_char_name}** successfully disengaged and fled from combat!")
            else:
                combat_log.append(f"🏃 **{acting_char_name}** attempted to disengage, but was cut off by **{target_enemy['name']}**!")

        elif (
            c_type == "STEALTH_VANISH"
            or action.get("action_category") == "stealth"
            or "vanish" in action.get("label", "").lower()
            or "hide in shadows" in action.get("label", "").lower()
        ):
            if tier in ("crit_success", "success"):
                if isinstance(session, dict):
                    set_actor_combat_vanished(session, True, user_id=acting_user_id, also_set_hidden=True)
                crit_note = " *(Perfect Shadow Blend!)*" if tier == "crit_success" else ""
                apply_status_effect(acting_char_data, "Hidden in Shadows [+50% Next Attack, Aggro Shed] [1 turn]", source="stealth")
                combat_log.append(f"💨 **{acting_char_name}** slipped into the shadows and vanished from enemy sight!{crit_note}")
            else:
                combat_log.append(f"💨 **{acting_char_name}** attempted to vanish into the shadows, but **{target_enemy['name']}** kept line-of-sight!")

        elif (
            c_type == "ENVIRONMENTAL_TRAP"
            or action.get("action_category") == "trap"
            or action.get("combat_tactical_archetype") == "environmental_hazard"
        ):
            if tier in ("crit_success", "success"):
                trap_stat = max(player_attrs.get("matk", 20), player_attrs.get("atk", 20))
                mult = 1.85 if tier == "crit_success" else 1.25
                trap_dmg = max(12, int(round(trap_stat * mult)))
                applied_dmg = apply_damage_to_enemy(target_enemy, trap_dmg)
                ctx["total_enemy_damage"] += applied_dmg
                if not target_enemy.get("telegraphed_skill"):
                    _apply_status_or_boss_surge(target_enemy, "Staggered [1 turn]", boss_telegraph_state, combat_log, source="trap")
                crit_tag = " *(Critical hit!)*" if tier == "crit_success" else ""
                combat_log.append(f"⚙️ **{acting_char_name}** triggered an environmental hazard on **{target_enemy['name']}**: Dealt **{applied_dmg} damage** and Staggered them{crit_tag}!")
            else:
                combat_log.append(f"⚙️ **{acting_char_name}** attempted to use the environment against **{target_enemy['name']}**, but it failed to trigger!")

        elif action.get("combat_tactical_archetype") == "combat_parley":
            enemy_tier_rank = int(target_enemy.get("tier_rank", 2) or 2)
            enemy_hp_pct = target_enemy.get("hp", 100) / max(1, target_enemy.get("max_hp", 100))
            if target_enemy.get("requires_non_lethal_subdue"):
                if tier in ("crit_success", "success"):
                    target_enemy["hp"] = 0
                    target_enemy["surrendered"] = True
                    target_enemy["contained_via_parley"] = True
                    surrendered_enemies.append(target_enemy["name"])
                    surrendered_enemy_dicts.append(dict(target_enemy))
                    fled_enemies.append(target_enemy["name"])
                    combat_log.append(
                        f"🗣️ **{acting_char_name}** calmed **{target_enemy['name']}**'s agitation! "
                        f"**{target_enemy['name']}** lowered its guard and entered containment willingly!"
                    )
                else:
                    combat_log.append(
                        f"🗣️ **{acting_char_name}** attempted to calm **{target_enemy['name']}**, "
                        f"but its agitated resonance lashed back!"
                    )
            elif (
                target_enemy.get("is_anomalous_manifestation")
                and str(target_enemy.get("sapience") or "").lower() in ("instinctual", "non_sapient")
                and not target_enemy.get("taboo_seal_unlocked")
            ):
                combat_log.append(
                    f"🗣️ **{acting_char_name}** attempted to parley with **{target_enemy['name']}**, "
                    f"but the {target_enemy.get('sapience', 'non-sapient')} anomaly cannot be reasoned with verbally!"
                )
            elif (
                target_enemy.get("is_anomalous_manifestation")
                and str(target_enemy.get("sapience") or "").lower() == "compulsive"
                and not (
                    target_enemy.get("dossier_revealed")
                    or (target_enemy.get("anomaly_blueprint") or {}).get("dossier_revealed")
                    or target_enemy.get("taboo_seal_unlocked")
                )
            ):
                combat_log.append(
                    f"🗣️ **{acting_char_name}** tried to talk **{target_enemy['name']}** down, but its compulsive loop "
                    f"ignores words until its folklore pattern is understood!"
                )
            elif _enemy_has_unsealed_tether(target_enemy):
                combat_log.append(
                    f"🏺 **{target_enemy['name']}** wavers at **{acting_char_name}**'s words, but its bound vessel keeps "
                    f"re-anchoring it—seal the tether before it can be contained!"
                )
            elif tier == "crit_success" or (tier == "success" and enemy_tier_rank <= 3 and enemy_hp_pct <= 0.50):
                surrendered_enemies.append(target_enemy["name"])
                fled_enemies.append(target_enemy["name"])
                target_enemy["hp"] = 0
                target_enemy["surrendered"] = True
                if target_enemy.get("is_anomalous_manifestation"):
                    target_enemy["contained_via_parley"] = True
                    surrendered_enemy_dicts.append(dict(target_enemy))
                combat_log.append(
                    f"🏳️ **{acting_char_name}** broke **{target_enemy['name']}**'s will to fight! "
                    f"**{target_enemy['name']}** dropped their weapon and surrendered!"
                )
            elif tier == "success":
                apply_status_effect(target_enemy, "Hesitating / Demoralized [-25% ATK] [2 turns]", source="parley")
                _apply_status_or_boss_surge(target_enemy, "Staggered [1 turn]", boss_telegraph_state, combat_log, source="parley")
                combat_log.append(
                    f"🗣️ **{acting_char_name}** shook **{target_enemy['name']}**'s resolve! "
                    f"They are **Hesitating / Demoralized (-25% ATK)** and **Staggered** for 1 turn!"
                )
            else:
                combat_log.append(f"🗣️ **{acting_char_name}** attempted to parley with **{target_enemy['name']}**, but they refused to yield!")

        elif action.get("combat_tactical_archetype") == "tactical_debuff":
            if tier in ("crit_success", "success"):
                apply_status_effect(target_enemy, "Vulnerable [-25% EVA, -20% ATK] [2 turns]", source="debuff")
                _apply_status_or_boss_surge(target_enemy, "Staggered [1 turn]", boss_telegraph_state, combat_log, source="debuff")
                combat_log.append(
                    f"🎯 **{acting_char_name}** executed a tactical disruption on **{target_enemy['name']}**: "
                    f"Inflicted **Vulnerable (-25% EVA, -20% ATK)** and **Staggered [1 turn]**!"
                )
            else:
                combat_log.append(f"🎯 **{acting_char_name}** attempted a tactical disruption against **{target_enemy['name']}**, but they anticipated the feint!")

        elif action.get("combat_tactical_archetype") == "reposition":
            if tier in ("crit_success", "success"):
                apply_status_effect(acting_char_data, "Evasive Maneuver [+30% EVA] [1 turn]", source="reposition")
                apply_status_effect(acting_char_data, "Flanking Advantage [+25% ACC, +20% ATK] [2 turns]", source="reposition")
                player_attrs["dodge_chance"] = min(85, player_attrs.get("dodge_chance", 5) + 30)
                try:
                    phys = session.get("physical_state") if isinstance(session, dict) else None
                    if isinstance(phys, dict) and isinstance(phys.get("actors"), dict):
                        for ak, av in phys["actors"].items():
                            if ak.lower() == acting_char_name.lower() and isinstance(av, dict):
                                av["tether"] = "none"
                except Exception:
                    pass
                combat_log.append(
                    f"💨 **{acting_char_name}** repositioned with agile footwork! "
                    f"Cleared restraints, gained **+30% Evasion** this turn, and secured **Flanking Advantage (+25% ACC, +20% ATK)**!"
                )
            else:
                combat_log.append(f"💨 **{acting_char_name}** tried to reposition around **{target_enemy['name']}**, but was forced back!")

        elif action.get("combat_tactical_archetype") == "called_shot":
            if is_vanished:
                acting_char_data["status_effects"] = [
                    s for s in acting_char_data.get("status_effects", [])
                    if "hidden in shadows" not in normalize_status_effect(s)["name"].lower()
                ]
                if isinstance(session, dict):
                    set_actor_combat_vanished(session, False, user_id=acting_user_id)
            if tier in ("crit_success", "success"):
                reduced_armor = dict(enemy_armor)
                reduced_armor["base_dt"] = int(reduced_armor.get("base_dt", 0) * 0.60)
                tactical_res = calculate_tactical_damage(
                    attacker_attrs=player_attrs,
                    defender_attrs=enemy_attrs,
                    weapon_meta=player_weapon,
                    armor_meta=reduced_armor,
                    tier="success",
                    attacker_level=acting_char_data.get("level", 1),
                    defender_max_hp=target_enemy.get("max_hp", 100),
                )
                mult = 1.60 if tier == "crit_success" else 1.15
                cs_dmg = max(6, int(round(tactical_res["damage"] * mult)))
                applied_dmg = apply_damage_to_enemy(target_enemy, cs_dmg)
                ctx["total_enemy_damage"] += applied_dmg
                lbl_low = str(action.get("label", "")).lower()
                if any(w in lbl_low for w in ("eye", "eyes", "head", "face", "visor", "sensor", "helm")):
                    part_status = "Blinded [-25% ACC] [2 turns]"
                elif any(w in lbl_low for w in ("hand", "wrist", "arm", "weapon", "grip", "blade", "gun")):
                    part_status = "Disarmed [-25% ATK] [2 turns]"
                else:
                    part_status = "Crippled [-25% EVA] [2 turns]"
                    _apply_status_or_boss_surge(target_enemy, "Staggered [1 turn]", boss_telegraph_state, combat_log, source="called_shot")
                apply_status_effect(target_enemy, part_status, source="called_shot")
                crit_tag = " *(Critical Called Shot!)*" if tier == "crit_success" else ""
                combat_log.append(
                    f"🎯 **{acting_char_name}** landed a precision called shot on **{target_enemy['name']}**: "
                    f"Dealt **{applied_dmg} damage** (piercing 40% armor) and inflicted **{part_status.split('[')[0].strip()}**{crit_tag}!"
                )
            else:
                combat_log.append(
                    f"🎯 **{acting_char_name}** aimed a called shot at **{target_enemy['name']}**, but the narrow target slipped out of reach!"
                )

        else:
            action_stance = action.get("stance")
            attack_type = action.get("attack_type")
            tactical_res = calculate_tactical_damage(
                attacker_attrs=player_attrs,
                defender_attrs=enemy_attrs,
                weapon_meta=player_weapon,
                armor_meta=enemy_armor,
                tier=tier,
                attacker_level=acting_char_data.get("level", 1),
                defender_max_hp=target_enemy.get("max_hp", 100),
                attack_type=attack_type,
                stance=action_stance,
            )
            m_dmg = tactical_res["damage"]
            if tactical_res["blocked"]:
                combat_log.append(f"🛡️ **{target_enemy['name']}** raised their guard, mitigating 60% damage!")

            if not target_enemy.get("requires_non_lethal_subdue") and tier == "crit_success" and (target_enemy.get("hp", 100) / max(1, target_enemy.get("max_hp", 100))) <= 0.60:
                if random.random() < 0.30:
                    m_dmg = target_enemy.get("hp", 100)

            if tier in ("crit_success", "success") and m_dmg > 0:
                ctx["total_enemy_damage"] += m_dmg
                _basic_info = get_awakened_basic_strike(p_attr, p_med, equipped_weapon=weapon_item) if is_anom_combat else {}
                _shred_m, _attr_m = _pre_mark_anomalous_hit(
                    target_enemy, int(_basic_info.get("stability_shred", 12) or 12), _basic_info.get("attack_attribute", p_attr)
                )
                apply_damage_to_enemy(target_enemy, m_dmg)
                _post_resolve_anomalous_hit(target_enemy, _shred_m, _attr_m)

                tags_log = []
                if tactical_res.get("dual_wield") or action_stance == "dual_wield" or action.get("dual_wield"):
                    tags_log.append("*(Dual-Wield Flurry! +15% damage)*")
                if tactical_res.get("versatile_2h"):
                    tags_log.append("*(Two-Handed Grip! +15% damage)*")
                if tactical_res.get("flanking_backstab"):
                    tags_log.append("*(Flanking Backstab! +50% damage)*")
                    acting_char_data["status_effects"] = [
                        s for s in acting_char_data.get("status_effects", [])
                        if "hidden in shadows" not in normalize_status_effect(s)["name"].lower()
                    ]
                    if isinstance(session, dict):
                        set_actor_combat_vanished(session, False, user_id=acting_user_id)
                elif tactical_res.get("ambush_strike"):
                    tags_log.append("*(Ambush Strike! +50% surprise damage)*")
                    if isinstance(session, dict):
                        set_actor_combat_vanished(session, False, user_id=acting_user_id, also_set_hidden=False)
                if tactical_res.get("brawler_synergy"):
                    tags_log.append("*(Brawler Synergy! +25% unarmed strike)*")
                if tactical_res.get("ap_ratio", 0) > 0:
                    ap_pct = int(round(tactical_res["ap_ratio"] * 100))
                    tags_log.append(f"*(Armor Pierced {ap_pct}%)*")
                tag_str = (" " + " ".join(tags_log)) if tags_log else ""
                combat_log.append(f"⚔️ **{acting_char_name}** attacked **{target_enemy['name']}**: Dealt **{m_dmg} damage**{tag_str}.")
            else:
                if tactical_res.get("flanking_backstab") or is_vanished:
                    acting_char_data["status_effects"] = [
                        s for s in acting_char_data.get("status_effects", [])
                        if "hidden in shadows" not in normalize_status_effect(s)["name"].lower()
                    ]
                    if isinstance(session, dict):
                        set_actor_combat_vanished(session, False, user_id=acting_user_id)
                if tactical_res.get("ambush_strike") or player_attrs.get("is_ambush"):
                    if isinstance(session, dict):
                        set_actor_combat_vanished(session, False, user_id=acting_user_id, also_set_hidden=False)
                combat_log.append(f"⚔️ **{acting_char_name}** attacked **{target_enemy['name']}**: Attack failed / deflected.")

            if tactical_res.get("stagger_inflicted"):
                apply_status_effect(acting_char_data, "Staggered [1 turn]", source="counter")
                combat_log.append(f"🛡️ **{target_enemy['name']}**'s heavy tank armor countered the blow! **{acting_char_name}** is Staggered!")

        if is_anom_combat and ctx["turn_hit_landed"] and target_enemy and target_enemy.get("hp", 0) > 0:
            for db_proc in (anom_passives.get("on_hit_debuffs") or []):
                if isinstance(db_proc, dict) and db_proc.get("status") and random.random() < float(db_proc.get("chance", 0.20)):
                    try_inflict_status(target_enemy, enemy_attrs, f"{db_proc['status']} [2 turns]", combat_log)

    if is_anom_combat and isinstance(session, dict):
        pips_map[uid_pip_key] = update_encounter_pips(
            pips_map.get(uid_pip_key, 0),
            hit_landed=ctx["turn_hit_landed"],
            triggered_break_this_turn=ctx["turn_triggered_break"],
            cast_ultimate=ctx["turn_cast_ultimate"],
            extra_break_pips=ctx["turn_extra_pips"],
        )
        session["player_resonance_pips"] = pips_map

    resolve_extra_player_actions(ctx)
