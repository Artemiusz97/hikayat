"""mechanics/combat/enemy_turn.py

Phase 3 Enemy Counter-Attacks resolution: morale routing & surrender,
normalized breach & Hard-CC turn suppression (zero dict-repr leak),
two-turn hybrid boss telegraph cadence & Phase-2 desperation windup,
solo 1vN 2-attacker direct-strike token cap with non-burst tactical pressure,
threat-hysteresis target selection, and 0-MP caster cantrips.
"""
from __future__ import annotations

import random
from typing import Any, Dict, List

import db
from mechanics.combat.damage import apply_damage_to_combatant
from mechanics.combat.enemies import get_enemy_armor_profile, get_enemy_weapon_profile, get_intent_code
from mechanics.combat.equipment import parse_equipment_metadata
from mechanics.social.attributes import calculate_combat_attributes
from mechanics.stealth import is_actor_combat_vanished

from .formulas import calculate_tactical_damage, try_inflict_status
from .loadouts import is_mundane_combat_scenario
from .status_effects import apply_status_effect, get_status_stat_modifiers, normalize_status_effect
from .targeting import arm_boss_telegraph, populate_enemy_hud_telemetry, resolve_threat_target
from .types import get_combatant_stat

_CC_KEYWORDS = (
    "stunned", "stun", "staggered", "stagger", "frozen", "paralyzed",
    "asleep", "sleep", "surprised", "petrified", "incapacitated",
)
_ROUTING_ARCHETYPES = {
    "Skirmisher", "Scavenger", "Scrap-Scavenger", "Rival Debater", "Gossip Monger", "Coward",
}
_CASTER_ARCHETYPES = {
    "Caster", "Psionic Alien", "Netrunner Spec-Op", "Cognitohazard Caster",
}


def _is_ally_vanished(
    ally_obj: Dict[str, Any],
    session: Any,
    acting_char_name: str,
    acting_user_id: Any,
) -> bool:
    for eff in ally_obj.get("status_effects", []) or []:
        if eff and "hidden in shadows" in normalize_status_effect(eff)["name"].lower():
            return True
    a_uid = ally_obj.get("user_id")
    if isinstance(session, dict):
        if a_uid is not None:
            return is_actor_combat_vanished(session, a_uid)
        if ally_obj.get("name") == acting_char_name:
            return is_actor_combat_vanished(session, acting_user_id)
    return False


def _sync_companion_after_hit(
    chosen_target: Dict[str, Any],
    target_name: str,
    current_npcs: List[Dict[str, Any]],
    active_party_npcs: List[Dict[str, Any]],
) -> None:
    for npc in current_npcs:
        if npc.get("name") == target_name:
            npc["hp"] = chosen_target["hp"]
            npc["mp"] = chosen_target.get("mp", npc.get("mp", 0))
    for p_comp in active_party_npcs:
        if p_comp.get("name") == target_name:
            p_comp["hp"] = chosen_target["hp"]
            p_comp["mp"] = chosen_target.get("mp", p_comp.get("mp", 0))


def _resolve_enemy_target(
    eid_cur: str,
    enemy_arch: str,
    target_pool: List[Dict[str, Any]],
    threat_matrix: Dict[str, Dict[str, float]],
    sticky_taunts: Dict[str, Dict[str, Any]],
    current_aggro_targets: Dict[str, str],
) -> Dict[str, Any]:
    """Sticky Taunt -> Construct Decoy (60%) -> Threat/Stalker-Dive -> Archetype Opener -> Random."""
    if sticky_taunts and eid_cur in sticky_taunts:
        t_info = sticky_taunts[eid_cur]
        if isinstance(t_info, dict) and int(t_info.get("remaining_turns", 0) or 0) > 0:
            forced = resolve_threat_target(
                eid_cur, target_pool, threat_matrix,
                sticky_taunts=sticky_taunts,
                current_aggro_targets=current_aggro_targets,
                enemy_archetype=enemy_arch,
            )
            if forced is not None:
                return forced

    construct_decoys = [a for a in target_pool if a.get("is_autonomous_construct") and a.get("hp", 0) > 0]
    if construct_decoys and random.random() < 0.60:
        decoy = construct_decoys[0]
        current_aggro_targets[eid_cur] = str(decoy.get("name") or decoy.get("id") or "")
        return decoy

    threat_target = resolve_threat_target(
        eid_cur,
        target_pool,
        threat_matrix,
        sticky_taunts=sticky_taunts,
        current_aggro_targets=current_aggro_targets,
        enemy_archetype=enemy_arch,
    )
    if threat_target is not None:
        return threat_target

    if enemy_arch in ("Stalker", "Assassin", "Chrome Cyberhound", "Spatial Stalker"):
        chosen = min(target_pool, key=lambda t: t.get("hp", 100))
    elif enemy_arch in _CASTER_ARCHETYPES:
        chosen = min(target_pool, key=lambda t: get_combatant_stat(t, "LUK"))
    elif enemy_arch in ("Brute", "Heavy Mech", "Heavy Borg", "Bio-Horror Brute"):
        chosen = max(target_pool, key=lambda t: get_combatant_stat(t, "STR"))
    else:
        chosen = random.choice(target_pool)
    current_aggro_targets[eid_cur] = str(chosen.get("name") or chosen.get("id") or "")
    return chosen


def resolve_enemy_combat_phase(ctx: Dict[str, Any]) -> None:
    """Executes Phase 3: Enemy turns, 2-turn telegraph lifecycle, 1vN cap, and HUD telemetry."""
    session = ctx["session"]
    enemies = ctx["enemies"]
    living_allies = ctx["living_allies"]
    player_chars = ctx["player_chars"]
    acting_char_name = ctx["acting_char_name"]
    acting_user_id = ctx.get("acting_user_id")
    action = ctx.get("action") or {}
    c_type = ctx.get("c_type", "")
    is_anom_combat = ctx["is_anom_combat"]
    is_non_lethal_active = ctx["is_non_lethal_active"]
    sess_id_cbt = ctx["sess_id_cbt"]
    scen_cbt = ctx["scen_cbt"]
    turn_count_cbt = ctx["turn_count_cbt"]
    combat_log = ctx["combat_log"]
    player_damage_by_name = ctx["player_damage_by_name"]
    companion_damage_by_name = ctx["companion_damage_by_name"]
    attackers_against_player = ctx["attackers_against_player"]
    surrendered_enemies = ctx["surrendered_enemies"]
    surrendered_enemy_dicts = ctx["surrendered_enemy_dicts"]
    fled_enemies = ctx["fled_enemies"]
    slain_civilians = ctx["slain_civilians"]
    active_party_npcs = ctx["active_party_npcs"]
    threat_ledger = ctx["threat_ledger"]
    threat_matrix = ctx["threat_matrix"]
    sticky_taunts = ctx["sticky_taunts"]
    boss_telegraph_state = ctx["boss_telegraph_state"]

    current_aggro_targets: Dict[str, str] = threat_ledger.setdefault("current_aggro_targets", {})

    living_enemies = [m for m in enemies if m.get("hp", 0) > 0]
    if not living_enemies or ctx.get("fled_battle"):
        populate_enemy_hud_telemetry(enemies, threat_ledger, living_allies)
        return

    non_construct_allies = [
        a for a in living_allies
        if isinstance(a, dict) and a.get("hp", 0) > 0 and not a.get("is_autonomous_construct")
    ]
    living_ally_count = max(
        1,
        len(non_construct_allies) if non_construct_allies else len([a for a in living_allies if isinstance(a, dict) and a.get("hp", 0) > 0]),
    )

    armed_prior_ids = {
        id(e) for e in living_enemies
        if isinstance(e.get("telegraphed_skill"), dict) and e.get("telegraphed_skill")
    }
    cap_solo_1vn = living_ally_count == 1 and len(living_enemies) >= 3
    direct_strike_tokens_used = 0

    ordered_enemies = sorted(
        living_enemies,
        key=lambda e: (
            1 if id(e) in armed_prior_ids else 0,
            int(e.get("tier_rank", 2) or 2),
            get_combatant_stat(e, "AGI", 3),
            int(e.get("level", 1) or 1),
        ),
        reverse=True,
    )

    player_names = {p.get("name") for p in player_chars if isinstance(p, dict)}
    is_mundane = is_mundane_combat_scenario(scen_cbt)
    scen_low = str(scen_cbt or "fantasy").strip().lower()
    is_scifi = any(t in scen_low for t in ("cyber", "sci_fi", "scifi", "space"))
    raw_preloaded_eq = session.get("_preloaded_equipment_by_uid") if isinstance(session, dict) else None
    equip_cache_by_uid: Dict[int, Dict[str, Any]] = (
        {int(k): v for k, v in raw_preloaded_eq.items() if k is not None}
        if isinstance(raw_preloaded_eq, dict)
        else {}
    )

    for idx_e, enemy in enumerate(ordered_enemies):
        if enemy.get("hp", 0) <= 0:
            continue

        enemy_arch = enemy.get("archetype", "Brute")
        tier_rank = int(enemy.get("tier_rank", 2) or 2)
        eid_cur = str(enemy.get("id") or enemy.get("name"))

        norm_statuses = [normalize_status_effect(s) for s in (enemy.get("status_effects") or []) if s]
        is_demoralized = any("demoralized" in st["name"].lower() for st in norm_statuses)
        hp_pct = enemy.get("hp", 100) / max(1, enemy.get("max_hp", 100))

        # Low-Morale Routing & Surrender for Tier <= 2 Minions & Skirmishers
        if tier_rank <= 2 and (enemy_arch in _ROUTING_ARCHETYPES or is_demoralized):
            if hp_pct < 0.15 or is_demoralized:
                stats = enemy.get("stats", {})
                morale = stats.get("END", 1) + stats.get("CHA", 1)
                if random.random() > (morale / 20.0):
                    capture_mode = (
                        is_non_lethal_active
                        or enemy.get("requires_non_lethal_subdue")
                        or (isinstance(session, dict) and session.get("active_capture_quest"))
                    )
                    if capture_mode:
                        surrendered_enemies.append(enemy["name"])
                        surrendered_enemy_dicts.append(dict(enemy))
                        enemy["hp"] = 1
                        enemy["is_subdued"] = True
                        enemy["is_subdued_ready"] = True
                        combat_log.append(f"🏳️ **{enemy['name']}** threw down their weapons and surrendered as a captive!")
                    else:
                        fled_enemies.append(enemy["name"])
                        enemy["hp"] = 0
                        combat_log.append(f"🏃💨 **{enemy['name']}**'s morale broke! They dropped their weapon and fled the battlefield!")
                    continue

        # Normalized Breach & Hard-CC turn suppression (zero dict-repr leak)
        if is_anom_combat and enemy.get("is_breached") and enemy.get("_breached_this_round"):
            combat_log.append(f"⚡ **{enemy['name']}** is **ANOMALY BREACHED** and staggered this turn!")
            continue

        active_cc_inst = next(
            (st for st in norm_statuses if any(k in st["name"].lower() for k in _CC_KEYWORDS)),
            None,
        )
        if active_cc_inst:
            cc_label = active_cc_inst["name"].strip().title()
            combat_log.append(f"💫 **{enemy['name']}** is **{cc_label}** and cannot act this turn!")
            continue

        # Two-Turn Hybrid Boss Telegraph: Cadence windup arms in Phase 3 & skips Turn-N basic swing
        if id(enemy) not in armed_prior_ids and not enemy.get("telegraphed_skill"):
            tel_armed = arm_boss_telegraph(
                enemy,
                turn_count_cbt,
                boss_telegraph_state,
                living_ally_count=living_ally_count,
                trigger_mode="cadence",
            )
            if tel_armed:
                skill_disp = tel_armed.get("skill_name") or "Cataclysmic Onslaught"
                combat_log.append(
                    f"⚠️ **TELEGRAPHED WINDUP!** **{enemy['name']}** gathers overwhelming power for **{skill_disp}**! "
                    f"*(Strike decisively or trigger a Stability Breach before next turn to interrupt!)*"
                )
                continue

        active_targets = [a for a in living_allies if a.get("hp", 0) > 0]
        if not active_targets:
            break

        visible_targets = [a for a in active_targets if not _is_ally_vanished(a, session, acting_char_name, acting_user_id)]
        target_pool = visible_targets if visible_targets else active_targets

        # Solo 1vN Action-Economy Cap: Max 2 direct damage strikes; excess foes apply non-burst pressure
        if cap_solo_1vn and direct_strike_tokens_used >= 2:
            if enemy_arch in ("Guardian", "Heavy Mech", "Heavy Borg", "Corrupted Treant", "Hall Monitor") or idx_e % 3 == 1:
                apply_status_effect(enemy, "Defensive Posture [+6 DT] [2 turns]", source="tactical_pressure")
                combat_log.append(f"🛡️ **{enemy['name']}** tightens its guard into a defensive posture, waiting for an opening!")
            elif idx_e % 3 == 2 and enemy.get("intent_code") != "heavy":
                enemy["intent_code"] = "heavy"
                enemy["intent"] = "Winding up a heavy swing"
                enemy["_primed_intent_this_turn"] = True
                combat_log.append(f"⚠️ **{enemy['name']}** maneuvers along the flank, winding up a heavy blow for next round!")
            else:
                p_tgt = _resolve_enemy_target(eid_cur, enemy_arch, target_pool, threat_matrix, sticky_taunts, current_aggro_targets)
                try_inflict_status(p_tgt, {}, "Swarmed [-10% ACC] [2 turns]", combat_log)
                combat_log.append(f"🌪️ **{enemy['name']}** harries **{p_tgt.get('name', 'Hero')}** from the flank (Swarmed)!")
            continue

        direct_strike_tokens_used += 1
        chosen_target = _resolve_enemy_target(eid_cur, enemy_arch, target_pool, threat_matrix, sticky_taunts, current_aggro_targets)
        target_name = chosen_target.get("name", "Hero")
        target_max_hp = chosen_target.get("max_hp", 100)

        enemy_weapon = dict(get_enemy_weapon_profile(enemy_arch))
        if isinstance(enemy.get("weapon_profile"), dict) and enemy["weapon_profile"]:
            enemy_weapon.update(enemy["weapon_profile"])
        enemy_atk_attrs = calculate_combat_attributes(enemy.get("stats", {}))
        enemy_atk_attrs.update({
            "weaknesses": enemy.get("weaknesses", []),
            "resistances": enemy.get("resistances", []),
            "immunities": enemy.get("immunities", []),
        })

        e_mods = get_status_stat_modifiers(enemy)
        if e_mods.get("damage_dealt_mult", 1.0) != 1.0:
            dm = float(e_mods["damage_dealt_mult"])
            enemy_atk_attrs["atk"] = max(1, int(round(enemy_atk_attrs.get("atk", 10) * dm)))
            enemy_atk_attrs["matk"] = max(1, int(round(enemy_atk_attrs.get("matk", 10) * dm)))
        if e_mods.get("accuracy_mult", 1.0) != 1.0:
            enemy_atk_attrs["acc"] = max(10, int(round(enemy_atk_attrs.get("acc", 66) * float(e_mods["accuracy_mult"]))))
        if e_mods.get("accuracy_bonus"):
            enemy_atk_attrs["acc"] = int(enemy_atk_attrs.get("acc", 66) + e_mods["accuracy_bonus"])
        if any(st["name"].lower() == "defensive posture" for st in norm_statuses):
            enemy_atk_attrs["base_dt"] = enemy_atk_attrs.get("base_dt", 0) + 6

        if "Overclocked" in enemy.get("affixes", []):
            enemy_atk_attrs["atk"] = int(enemy_atk_attrs.get("atk", 10) * 1.25)
            enemy_atk_attrs["matk"] = int(enemy_atk_attrs.get("matk", 10) * 1.25)
            enemy_atk_attrs["acc"] = enemy_atk_attrs.get("acc", 66) + 15

        enemy_atk_attrs["atk"] += enemy_weapon.get("atk_bonus", 0)
        enemy_atk_attrs["matk"] += enemy_weapon.get("matk_bonus", 0)

        t_user_id = chosen_target.get("user_id", 0)
        t_uid_int = int(t_user_id or 0) if t_user_id else 0
        if t_uid_int:
            if t_uid_int not in equip_cache_by_uid:
                equip_cache_by_uid[t_uid_int] = db.get_equipment(t_uid_int)
            t_equipped = equip_cache_by_uid[t_uid_int]
        else:
            t_equipped = {}
        t_equipped_items = [i for i in t_equipped.values() if i] if t_equipped else []
        target_attrs = calculate_combat_attributes(chosen_target, t_equipped_items, allow_non_combat=True)
        target_armor = parse_equipment_metadata(t_equipped.get("Armor") or t_equipped.get("Top") or {})

        if "Phasing" in enemy.get("affixes", []):
            target_attrs["base_dt"] = max(0, int(target_attrs.get("base_dt", 0) * 0.5))
            target_attrs["block_chance"] = 0

        cur_intent = str(enemy.get("intent") or "").strip()
        cur_intent_code = enemy.get("intent_code") or get_intent_code(cur_intent)
        is_heavy_intent = cur_intent_code == "heavy"
        is_magic_intent = (cur_intent_code == "magic") or (not cur_intent_code and enemy_arch in _CASTER_ARCHETYPES and not is_mundane)
        is_ambush_intent = cur_intent_code == "ambush"
        is_defensive_intent = cur_intent_code == "defensive"
        is_swarm_intent = cur_intent_code == "swarm"

        if is_defensive_intent:
            enemy_atk_attrs["base_dt"] = enemy_atk_attrs.get("base_dt", 0) + 8
            enemy_atk_attrs["block_chance"] = min(85, enemy_atk_attrs.get("block_chance", 0) + 25)
            combat_log.append(f"🛡️ **{enemy['name']}** holds their defensive posture! (+8 DT, +25% Block)")

        if is_swarm_intent:
            if "multiplying" in cur_intent.lower():
                heal_amt = int(enemy.get("max_hp", 50) * 0.20)
                enemy["hp"] = min(enemy.get("max_hp", 50), enemy.get("hp", 0) + heal_amt)
                combat_log.append(f"🌀 **{enemy['name']}** multiplies rapidly! Restored **+{heal_amt} HP** and expanded the swarm!")
            else:
                enemy_atk_attrs["acc"] = enemy_atk_attrs.get("acc", 66) + 15
                try_inflict_status(chosen_target, target_attrs, "Swarmed [-10% ACC] [2 turns]", combat_log)

        enemy_anom_tag = str(enemy.get("anomalous_npc_tag") or "").strip().lower()
        hostile_sa_cast_note = ""
        if enemy_anom_tag == "civilian":
            enemy["mp"] = 0
            enemy["max_mp"] = 0
            is_magic_intent = False
        elif enemy_anom_tag == "special_agent":
            from mechanics.social.anomalous_npc_tags import resolve_hostile_special_agent_ability_modifier
            sa_mod = resolve_hostile_special_agent_ability_modifier(enemy, combat_log)
            if isinstance(sa_mod, dict):
                if sa_mod.get("skip_attack"):
                    continue
                sp_e = sa_mod.get("spell") or {}
                mult_e = float(sa_mod.get("damage_mult", 1.25) or 1.25)
                enemy_atk_attrs["atk"] = int(enemy_atk_attrs.get("atk", 12) * mult_e)
                enemy_atk_attrs["matk"] = int(enemy_atk_attrs.get("matk", 12) * mult_e)
                if sp_e.get("damage_type"):
                    enemy_weapon.pop("attack_profiles", None)
                    enemy_weapon["damage_types"] = {str(sp_e["damage_type"]): 1.0}
                if sp_e.get("name"):
                    hostile_sa_cast_note = f" *(Cast **{sp_e['name']}** — -{sa_mod.get('cost', 8)} MP!)*"
            is_magic_intent = False

        if is_magic_intent:
            mana_cost = 6 + (int(enemy.get("level", 1) or 1) * 2)
            current_mp = int(enemy.get("mp", enemy.get("max_mp", 20)) or 0)
            enemy_weapon.pop("attack_profiles", None)
            if current_mp >= mana_cost:
                enemy["mp"] = current_mp - mana_cost
                enemy_atk_attrs["matk"] = int(enemy_atk_attrs.get("matk", 15) * 1.3)
                enemy_weapon["damage_types"] = {"magical": 1.0}
            elif is_mundane:
                enemy_atk_attrs["atk"] = max(1, int(round(enemy_atk_attrs.get("atk", 12) * 0.85)))
                enemy_weapon["damage_types"] = {"physical": 1.0}
            else:
                cantrip_name = "Tech Pulse" if is_scifi else ("Resonance Bolt" if is_anom_combat else "Arcane Cantrip")
                cantrip_dmg_type = "electric" if is_scifi else ("aether" if is_anom_combat else "magical")
                enemy_atk_attrs["matk"] = max(1, int(round(enemy_atk_attrs.get("matk", 15) * 0.85)))
                enemy_weapon["damage_types"] = {cantrip_dmg_type: 1.0}
                hostile_sa_cast_note = f" *(Channeled **{cantrip_name}**)*"

        if is_ambush_intent:
            enemy_weapon["armor_penetration"] = 0.40

        if t_user_id == acting_user_id and action.get("stance") == "2H":
            shield_item = t_equipped.get("Shield")
            if shield_item:
                shield_meta = parse_equipment_metadata(shield_item)
                shield_dt = shield_meta.get("base_dt", shield_meta.get("dt_contribution", 0))
                target_attrs["block_chance"] = 0
                if shield_dt > 0:
                    target_attrs["base_dt"] = max(0, target_attrs.get("base_dt", 0) - shield_dt)

        if t_user_id == acting_user_id and (c_type == "DEFENSIVE_GUARD" or action.get("action_category") == "guard"):
            target_attrs["base_dt"] = target_attrs.get("base_dt", 0) + 6
            target_attrs["block_chance"] = min(90, target_attrs.get("block_chance", 0) + 30)

        has_optics = any(t in enemy_atk_attrs.get("tags", []) for t in ("precision", "optics", "hud", "smart_link"))
        optics_bonus = 5 if has_optics else 0
        base_hit = 50 + (enemy_atk_attrs.get("acc", 66) - (target_attrs.get("eva", 11) - optics_bonus))
        if t_user_id == acting_user_id and action.get("tier") in ("fail", "failure", "crit_fail"):
            base_hit += 25
        hit_chance = max(20, min(95, base_hit))
        roll = random.randint(1, 100)
        e_tier = "crit_success" if roll <= 10 else ("success" if roll <= hit_chance else "fail")

        e_res = calculate_tactical_damage(
            attacker_attrs=enemy_atk_attrs,
            defender_attrs=target_attrs,
            weapon_meta=enemy_weapon,
            armor_meta=target_armor,
            tier=e_tier,
            attacker_level=enemy.get("level") or 1,
            defender_max_hp=target_max_hp,
            is_enemy_attacker=True,
        )
        e_dmg = e_res["damage"]

        telegraph = enemy.get("telegraphed_skill")
        supreme_note = ""
        if id(enemy) in armed_prior_ids and isinstance(telegraph, dict) and telegraph:
            s_name = telegraph.get("skill_name", "Supreme Strike")
            supreme_note = f" *(Supreme Attack: {s_name}!)*"
            if e_tier != "fail":
                dmg_mult = float(telegraph.get("damage_mult", 1.75))
                e_dmg = max(1, int(e_dmg * dmg_mult))
                combat_log.append(f"💥 **SUPREME ATTACK UNLEASHED!** **{enemy['name']}** unleashed **{s_name}**!")
            else:
                combat_log.append(f"💨 **{enemy['name']}** unleashed **{s_name}**, but **{target_name}** narrowly dodged the apocalyptic blow!")
            enemy["telegraphed_skill"] = None
            enemy["stagger_pct"] = 0
            boss_telegraph_state.pop(eid_cur, None)

        if is_heavy_intent and not e_res["blocked"]:
            e_dmg = int(e_dmg * 1.35)
            if target_name in player_names:
                if not (c_type == "DEFENSIVE_GUARD" or action.get("action_category") == "guard"):
                    try_inflict_status(chosen_target, target_attrs, "Staggered [2 turns]", combat_log)

        if e_res["blocked"]:
            combat_log.append(f"🛡️ **{target_name}** blocked **{enemy['name']}**'s strike with their shield!")

        if e_res.get("stagger_inflicted"):
            apply_status_effect(enemy, "Staggered [2 turns]", source="tank_counter")
            combat_log.append(f"🛡️ **{target_name}**'s heavy tank armor countered the blow! **{enemy['name']}** is Staggered!")

        if e_dmg > 0:
            e_dmg = max(1, e_dmg)
            if enemy_weapon.get("damage_types", {}).get("poison", 0) > 0 or any(w in enemy_arch.lower() for w in ["poison", "toxic", "venom", "spider", "snake"]):
                try_inflict_status(chosen_target, target_attrs, "Poisoned [2 turns]", combat_log)

            actual_dmg = apply_damage_to_combatant(
                target=chosen_target,
                dmg=e_dmg,
                attacker=enemy,
                combat_log=combat_log,
                is_anom_combat=is_anom_combat,
            )

            if target_name in player_names:
                if enemy["name"] not in attackers_against_player:
                    attackers_against_player.append(enemy["name"])
                player_damage_by_name[target_name] = player_damage_by_name.get(target_name, 0) + actual_dmg
                ctx["total_player_damage"] += actual_dmg
                intent_note = hostile_sa_cast_note or supreme_note
                if not intent_note:
                    if is_heavy_intent:
                        intent_note = " *(Telegraphed Heavy Strike!)*"
                    elif is_magic_intent:
                        intent_note = " *(Telegraphed Arcane Burst!)*"
                    elif is_ambush_intent:
                        intent_note = " *(Telegraphed Ambush!)*"
                combat_log.append(f"💥 **{enemy['name']}** attacked **{target_name}**: Dealt **{e_dmg} damage**{intent_note}.")

                if is_anom_combat and enemy.get("hp", 0) > 0 and target_attrs.get("on_hit_debuffs"):
                    for _r_deb in (target_attrs.get("on_hit_debuffs") or []):
                        if isinstance(_r_deb, dict) and random.random() < float(_r_deb.get("proc_chance", 0.0) or 0.0):
                            _r_ail = str(_r_deb.get("ailment") or "Staggered")
                            if not any(_r_ail.lower() in normalize_status_effect(s)["name"].lower() for s in enemy.get("status_effects", [])):
                                apply_status_effect(enemy, f"{_r_ail} [2 turns]", source="retaliation_ward")
                                combat_log.append(
                                    f"⚡ **Anomalous Retaliation Ward:** **{target_name}**'s gear inflicted **{_r_ail}** on **{enemy['name']}**!"
                                )

                has_combat_armor = bool(t_equipped.get("Armor")) or (target_attrs.get("base_dt", 0) > 2)
                if not has_combat_armor:
                    is_severe = (
                        e_dmg >= 8
                        or e_tier == "crit_success"
                        or any(d in enemy_weapon.get("damage_types", {}) for d in ("fire", "acid", "slashing"))
                        or any(a in enemy_weapon.get("attack_types", []) for a in ("slash", "hack", "thrust"))
                    )
                    if is_severe and try_inflict_status(chosen_target, target_attrs, "Torn / Scorched Clothes [-1 CHA] [2 turns]", combat_log):
                        combat_log.append(f"🧵 **{target_name}**'s civilian clothes were torn and scorched by the blow! (-1 CHA for 2 turns)")
                        ctx.setdefault("player_status_sync_by_name", {})[target_name] = list(chosen_target.get("status_effects", []))
            else:
                companion_damage_by_name[target_name] = companion_damage_by_name.get(target_name, 0) + actual_dmg
                _sync_companion_after_hit(chosen_target, target_name, ctx["current_npcs"], active_party_npcs)
                h_note = hostile_sa_cast_note or supreme_note
                if chosen_target.get("is_summon"):
                    combat_log.append(f"💥 **{enemy['name']}** struck summon **{target_name}**: Dealt **{e_dmg} damage**{h_note}.")
                    if chosen_target["hp"] <= 0:
                        combat_log.append(f"💀 **{target_name}** was destroyed!")
                elif is_anom_combat and chosen_target.get("anomalous_npc_tag") == "civilian":
                    combat_log.append(f"💥 **{enemy['name']}** attacked **{target_name}** (*Civilian*): Dealt **{e_dmg} damage**{h_note}.")
                    if chosen_target["hp"] <= 0:
                        from mechanics.social.anomalous_npc_tags import apply_civilian_permadeath, is_supernatural_anomalous_entity
                        if is_supernatural_anomalous_entity(enemy):
                            apply_civilian_permadeath(sess_id_cbt, session, target_name, enemy.get("name", "Anomalous Entity"))
                            slain_civilians.append({"name": target_name, "killer": enemy.get("name", "Anomalous Entity")})
                            ctx["current_npcs"] = [n for n in ctx["current_npcs"] if n.get("name") != target_name]
                            combat_log.append(
                                f"💀 **{target_name}** (*Civilian — No Mana Barrier*) could not withstand **{enemy['name']}** and was **permanently killed**!"
                            )
                        else:
                            apply_status_effect(chosen_target, "Incapacitated", source="knockout")
                            combat_log.append(f"⚠️ **{target_name}** (*Civilian*) was knocked unconscious!")
                elif is_anom_combat and chosen_target.get("anomalous_npc_tag") == "special_agent":
                    combat_log.append(f"💥 **{enemy['name']}** attacked **{target_name}** (*Special Agent*): Dealt **{e_dmg} damage**{h_note}.")
                    if chosen_target["hp"] <= 0:
                        apply_status_effect(chosen_target, "Incapacitated", source="barrier_shatter")
                        for p_comp in active_party_npcs:
                            if p_comp.get("name") == target_name:
                                apply_status_effect(p_comp, "Incapacitated", source="barrier_shatter")
                        combat_log.append(f"⚠️ **{target_name}**'s mana barrier shattered — they are **Knocked Out / Incapacitated**!")
                else:
                    combat_log.append(f"💥 **{enemy['name']}** attacked **{target_name}**: Dealt **{e_dmg} damage**{h_note}.")
                    if chosen_target["hp"] <= 0:
                        combat_log.append(f"⚠️ **{target_name}** was knocked down!")

            is_boss_unit = bool(tier_rank >= 4 or enemy.get("is_boss"))
            if is_boss_unit and e_dmg > 0 and len(target_pool) > 1:
                sec_pool = [a for a in target_pool if a.get("name") != target_name and a.get("hp", 0) > 0]
                if sec_pool:
                    sec_target = max(sec_pool, key=lambda t: get_combatant_stat(t, "END") + get_combatant_stat(t, "STR"))
                    sec_name = sec_target.get("name", "Ally")
                    splash_dmg = max(1, int(e_dmg * 0.50))
                    actual_splash = apply_damage_to_combatant(
                        target=sec_target,
                        dmg=splash_dmg,
                        attacker=enemy,
                        combat_log=combat_log,
                        is_anom_combat=is_anom_combat,
                    )
                    if sec_name in player_names:
                        player_damage_by_name[sec_name] = player_damage_by_name.get(sec_name, 0) + actual_splash
                        ctx["total_player_damage"] += actual_splash
                    else:
                        companion_damage_by_name[sec_name] = companion_damage_by_name.get(sec_name, 0) + actual_splash
                        _sync_companion_after_hit(sec_target, sec_name, ctx["current_npcs"], active_party_npcs)
                    combat_log.append(f"🌊 **CLEAVE!** **{enemy['name']}**'s sweeping strike cleaved into **{sec_name}**: Dealt **{splash_dmg} splash damage**!")

            if "Vampiric" in enemy.get("affixes", []):
                leech = max(1, int(e_dmg * 0.25))
                enemy["hp"] = min(enemy.get("max_hp", 100), enemy.get("hp", 0) + leech)
                combat_log.append(f"🩸 **{enemy['name']}** siphoned life! Healed **+{leech} HP**.")

            if "Corrosive" in enemy.get("affixes", []):
                try_inflict_status(chosen_target, target_attrs, "Corroded Armor [-2 DT] [2 turns]", combat_log)

        elif e_res.get("blocked"):
            pass
        elif e_res.get("hit"):
            combat_log.append(f"🛡️ **{enemy['name']}** struck **{target_name}**, but the blow was completely absorbed by their armor!")
        elif not supreme_note:
            combat_log.append(f"💨 **{enemy['name']}** attacked **{target_name}**: Attack missed.")

    # End-of-round Phase-2 desperation arming for surviving <50% HP bosses without an active windup
    for enemy in living_enemies:
        if enemy.get("hp", 0) > 0 and not enemy.get("telegraphed_skill") and not enemy.get("_phase2_telegraphed"):
            p2_tel = arm_boss_telegraph(
                enemy,
                turn_count_cbt,
                boss_telegraph_state,
                living_ally_count=living_ally_count,
                trigger_mode="phase2",
            )
            if p2_tel:
                s_disp = p2_tel.get("skill_name") or "Cataclysmic Onslaught"
                combat_log.append(
                    f"⚠️ **PHASE 2 DESPERATION!** **{enemy['name']}** erupts with desperate fury, winding up **{s_disp}** for next turn!"
                )

    populate_enemy_hud_telemetry(enemies, threat_ledger, living_allies)
