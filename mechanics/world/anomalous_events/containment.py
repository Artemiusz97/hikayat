from __future__ import annotations
"""
Combat & narrative anomaly containment resolution, agitated entity spawning,
killed non-hostile fallout, and hostile incursion victory handling.
"""
import hashlib
import json
import random
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import db
import namegen
import scenario_data
from mechanics.world.anomaly_engine import (
    ANOMALOUS_9_ELEMENTS,
    NON_HOSTILE_TEMPERAMENT_TYPES,
    evaluate_taboo_interaction,
    format_anomaly_dossier_summary,
    generate_anomaly_blueprint,
    instantiate_enemy_from_blueprint,
    parse_blueprint_from_notes,
    serialize_blueprint_note,
)
from mechanics.world.folklore_mechanics import (
    build_dialogue_trap_choices,
    build_offering_counter_rite_choice,
    consume_folklore_offering_item,
    evaluate_dialogue_trap_response,
    evaluate_omen_paradox,
    find_matching_offering_in_inventory,
    get_enemy_tether_state,
    get_public_anomaly_name,
    has_active_dialogue_trap,
    is_blueprint_disguised,
    seal_enemy_tether,
    unmask_blueprint_disguise,
)

from .generation import (
    NON_HOSTILE_SUBDUE_THRESHOLD_PCT,
    _resolve_session_turn_number,
    get_active_incursion_at_location,
)
from .inquiries import (
    _prune_anomaly_from_scene_npcs,
    apply_non_hostile_strike_side_effects,
    get_blueprint_alias_names,
    get_non_hostile_entity_temperament,
    is_non_hostile_entity_quest,
    refund_trick_tax_gold_on_containment,
    resolve_anomaly_dialogue_inquiry,
    reveal_anomaly_dossier,
)
from .vault import (
    handle_secured_object_anomaly_conversion,
    record_contained_anomaly_to_vault_log,
)


def spawn_agitated_non_hostile_entity(
    session_id: int,
    entity_name: str,
    *,
    location: str = "",
    category_tag: str = "spatial_warp",
    incursion_id: str = "",
    breach_id: str = "",
    quest_id: str = "",
    sub_obj_id: Optional[int] = None,
    is_story_quest: bool = False,
    session: Optional[Dict[str, Any]] = None,
    blueprint: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Spawns an agitated volatile Non-Hostile Entity into `nearby_enemies` for combat containment.
    - All regular combat attacks remain lethal (killing it fails bounties / forfeits rewards!).
    - Player can either weaken it to <= 35% HP to unlock `[🛡️ Subdue & Contain]` OR use `[🗣️ Persuade / Calm]` in combat.
    """
    from mechanics.combat.enemies import generate_scenario_enemy

    sess = session if isinstance(session, dict) else (db.get_session(session_id) or {})
    scen_key = str(sess.get("scenario") or "anomalous_incursions")
    loc_str = location or str(sess.get("current_location") or "Metropolitan Grid")
    eff_inc_id = str(incursion_id or breach_id or "").strip()

    bp = dict(blueprint) if isinstance(blueprint, dict) else None
    if bp is None and quest_id and session_id:
        q_row = db.get_quest_by_id(session_id, quest_id) or {}
        bp = parse_blueprint_from_notes(q_row)
    if bp is None and eff_inc_id:
        for inc in (sess.get("daily_incursions") or sess.get("daily_breaches") or []):
            if isinstance(inc, dict) and (inc.get("incursion_id") == eff_inc_id or inc.get("breach_id") == eff_inc_id):
                if isinstance(inc.get("anomaly_blueprint"), dict):
                    bp = dict(inc["anomaly_blueprint"])
                break

    orig_ag_name = str(entity_name or "").strip()
    disg_ag_alias = ""
    if bp:
        disg_ag_alias = str((bp.get("disguise_state") or {}).get("disguise_alias") or "").strip()
        bp, _unmask_ag = unmask_blueprint_disguise(bp)
        if _unmask_ag and bp.get("canonical_name"):
            entity_name = str(bp["canonical_name"])
        if session_id:
            try:
                db.record_session_anomaly_field_log(session_id, bp, stage="sighted", location=loc_str)
                if bp.get("codex_id"):
                    db.record_folklore_codex_progress(
                        db.get_session_participant_user_ids(session_id),
                        str(bp["codex_id"]),
                        stage="sighted",
                    )
            except Exception:
                pass
        enemy_obj = instantiate_enemy_from_blueprint(
            bp,
            tier=2,
            is_agitated_non_hostile=True,
            incursion_id=eff_inc_id,
            linked_quest_id=quest_id,
            linked_sub_obj_id=sub_obj_id,
            is_story_quest=bool(is_story_quest),
        )
        enemy_obj["name"] = entity_name
        enemy_obj["subdue_threshold_pct"] = NON_HOSTILE_SUBDUE_THRESHOLD_PCT
    else:
        arch_name = "Spatial Stalker" if category_tag == "spatial_warp" else "Cognitohazard Caster"
        enemy_obj = generate_scenario_enemy(
            scenario=scen_key,
            location=loc_str,
            chapter=int(sess.get("current_chapter", 1) or 1),
            custom_name=entity_name,
            custom_archetype=arch_name,
            exact_tier=2,
        )
        enemy_obj["name"] = entity_name
        enemy_obj["affixes"] = []
        enemy_obj["requires_non_lethal_subdue"] = True
        enemy_obj["born_disposition"] = "non_hostile"
        enemy_obj["subdue_threshold_pct"] = NON_HOSTILE_SUBDUE_THRESHOLD_PCT
        enemy_obj["temperament"] = "volatile"
        enemy_obj["category_tag"] = category_tag
        if eff_inc_id:
            enemy_obj["incursion_id"] = eff_inc_id
            enemy_obj["breach_id"] = eff_inc_id
        if quest_id:
            enemy_obj["linked_quest_id"] = quest_id
            enemy_obj["linked_sub_obj_id"] = sub_obj_id
            enemy_obj["is_story_quest"] = bool(is_story_quest)

    enemies = list(sess.get("nearby_enemies") or [])
    if not any(isinstance(e, dict) and e.get("name") == entity_name and e.get("requires_non_lethal_subdue") for e in enemies):
        enemies.append(enemy_obj)
    if isinstance(session, dict):
        session["nearby_enemies"] = enemies
    if session_id:
        db.update_session(session_id, nearby_enemies=enemies)
    _prune_anomaly_from_scene_npcs(
        session_id,
        entity_name,
        extra_names=[orig_ag_name, disg_ag_alias],
        session=sess,
        persist_db=True,
    )
    return enemy_obj


def _roll_optional_incursion_gear_drop(user_id: Optional[int], scen_key: str) -> str:
    if not user_id or random.random() >= 0.35:
        return ""
    try:
        from mechanics.combat.items.weapons import generate_random_equipment
        eq = generate_random_equipment(
            scenario=scen_key,
            slot=random.choice(["Weapon", "Armor", "Accessory 1"]),
            tier=2,
        )
        if isinstance(eq, dict) and eq.get("name"):
            db.add_item(
                user_id,
                eq["name"],
                item_type=eq.get("item_type", "Weapon"),
                effect=eq.get("effect", ""),
                slot_cost=int(eq.get("slot_cost", 1) or 1),
            )
            return str(eq["name"])
    except Exception:
        pass
    return ""


def _extract_check_roll_and_success(
    char: Dict[str, Any],
    stat_key: str,
    dc: int,
    force_roll: Optional[int] = None,
    pre_rolled_check: Any = None,
) -> Tuple[int, int, bool]:
    """Resolves `(nat_roll, total_check, succeeded)` honoring `force_roll` or UI `pre_rolled_check`."""
    stat_col_map = {"STR": "str_", "PER": "per_", "END": "end_", "CHA": "cha", "INT": "int_", "AGI": "agi", "LUK": "luk"}
    s_upper = str(stat_key or "CHA").upper()
    stat_val = int((char or {}).get(stat_col_map.get(s_upper, "cha"), 3) or 3)
    if isinstance((char or {}).get("stats"), dict) and s_upper in char["stats"]:
        stat_val = int(char["stats"].get(s_upper, stat_val) or stat_val)

    if force_roll is not None:
        nat_roll = int(force_roll)
        total_check = nat_roll + stat_val
        return nat_roll, total_check, (total_check >= dc and nat_roll > 1)

    if pre_rolled_check is not None:
        from skill_check import is_check_success
        succeeded = bool(is_check_success(pre_rolled_check, default_if_none=False))
        nat_roll = getattr(pre_rolled_check, "roll", None)
        if nat_roll is None and isinstance(pre_rolled_check, dict):
            nat_roll = pre_rolled_check.get("roll") or pre_rolled_check.get("natural_roll")
        nat_roll = int(nat_roll) if nat_roll is not None else (15 if succeeded else 4)
        total_val = getattr(pre_rolled_check, "total", None)
        if total_val is None and isinstance(pre_rolled_check, dict):
            total_val = pre_rolled_check.get("total")
        total_check = int(total_val) if total_val is not None else (nat_roll + stat_val)
        return nat_roll, total_check, succeeded

    nat_roll = random.randint(1, 20)
    total_check = nat_roll + stat_val
    return nat_roll, total_check, (total_check >= dc and nat_roll > 1)


def _complete_or_advance_linked_quest_containment(
    session_id: int,
    quest_id: str,
    sub_obj_id: Optional[int],
    entity_name: str,
    category_tag: str,
    resolution_method: str,
    party_user_ids: List[int],
    forfeit_bounty_gold: bool = False,
) -> Dict[str, Any]:
    """Advances or completes a Bounty / Story Quest sub-objective when an agitated Non-Hostile Entity is contained in combat."""
    from db.quests import append_quest_note_flag_in_db
    from game_engine.quests import grant_stage_acquisition_item_if_needed

    quest = db.get_quest_by_id(session_id, quest_id)
    if not quest or quest.get("status") != "Active":
        return {}

    sess = db.get_session(session_id) or {}
    loc = str(sess.get("current_location") or quest.get("client_location") or "Metropolitan Grid")
    lead_uid = party_user_ids[0] if party_user_ids else sess.get("host_user_id")

    vault_entry = record_contained_anomaly_to_vault_log(
        session_id=session_id,
        entity_name=entity_name,
        category_tag=category_tag or "spatial_warp",
        subtype="non_hostile_entity",
        location=loc,
        containment_note=f"Contained alive during field operation '{quest.get('title', 'Containment Bounty')}'.",
        resolution_method=resolution_method,
        user_id=lead_uid,
        quest_id=quest_id,
        sub_obj_id=sub_obj_id,
    )
    secured_key = f"entity_secured_so_{sub_obj_id}" if sub_obj_id is not None else "entity_secured"
    append_quest_note_flag_in_db(session_id, quest_id, secured_key, "1")
    append_quest_note_flag_in_db(session_id, quest_id, "vault_logged", "1")
    db.reset_quest_strikes(session_id, quest_id)

    active_wp = db.get_active_waypoint(session_id, quest_id, sub_obj_id)
    all_wps = db.get_quest_waypoints(session_id, quest_id, sub_obj_id) or []
    total_stages = len(all_wps) or 1
    next_wp = None
    all_done = True

    if active_wp:
        cur_stage_idx = int(active_wp.get("stage_index", 1) or 1)
        next_wp = db.advance_waypoint(session_id, quest_id, cur_stage_idx, sub_obj_id)
        all_done = next_wp is None
        if not all_done:
            sub_obj_dict = None
            if sub_obj_id is not None:
                for so in (quest.get("sub_objectives") or []):
                    if isinstance(so, dict) and str(so.get("id")) == str(sub_obj_id):
                        sub_obj_dict = so
                        break
            grant_stage_acquisition_item_if_needed(
                session_id=session_id,
                quest=quest,
                completed_stage_index=cur_stage_idx,
                total_stages=total_stages,
                party_user_ids=party_user_ids,
                sub_obj=sub_obj_dict,
            )

    claim_res = None
    if all_done:
        if sub_obj_id is not None:
            db.mark_sub_objective_completed_in_quest(session_id, quest_id, sub_obj_id)
        else:
            db.update_quest_status(session_id, quest_id, "Completed")
            if party_user_ids:
                if forfeit_bounty_gold:
                    q_xp_only = int(quest.get("reward_xp", 0) or 0)
                    if q_xp_only > 0:
                        for _p_uid in party_user_ids:
                            db.add_xp(_p_uid, q_xp_only)
                    claim_res = {"ok": True, "gold_awarded": 0, "xp_awarded": q_xp_only, "forfeited_bounty_gold": True}
                else:
                    claim_res = db.claim_quest_reward(session_id, quest_id, party_user_ids)

    return {
        "quest_id": quest_id,
        "sub_obj_id": sub_obj_id,
        "quest_title": quest.get("title", "Containment Bounty"),
        "all_stages_complete": all_done,
        "next_waypoint": dict(next_wp) if next_wp else None,
        "claim_result": claim_res,
        "vault_entry": vault_entry,
    }


def resolve_anomalous_combat_containment(
    session_id: int,
    user_id: Optional[int] = None,
    action_type: str = "subdue",
    incursion_id: str = "",
    breach_id: str = "",
    quest_id: str = "",
    force_roll: Optional[int] = None,
    pre_rolled_check: Any = None,
    party_user_ids: Optional[List[int]] = None,
    target_enemy: Optional[Dict[str, Any]] = None,
    resolution_method: str = "",
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Resolves in-combat Non-Lethal Containment on an agitated `requires_non_lethal_subdue` entity
    OR Live-Capture on a Born-Hostile Anomalous Manifestation:
    - `action_type == 'subdue'`:
      Requires `0 < hp <= max(1, int(max_hp * threshold_pct))` (`<= 35%` HP, or `<= 50%` for instinctual hostiles),
      OR `is_breached`, OR `taboo_exploited` (allowing non-damage containment of `non_corporeal` anomalies!).
    - `action_type == 'combat_persuade'`:
      Available at ANY `hp > 0` for `sapient` anomalies (and legacy agitated entities).
      Born-hostile `instinctual` or `non_sapient` anomalies cannot be reasoned with verbally and require weakening or Taboo exploitation first.
    - Live-Capture Bonus on Born-Hostile Anomalies:
      Grants **+20% bonus XP** and **+5 Promotion Rep**, logs to Containment Vault, and triggers Object-to-Gear conversion if `anomaly_type == 'object'`.
    """
    eff_inc_id = str(incursion_id or breach_id or "").strip()
    sess = db.get_session(session_id) or {}
    scen_key = str(sess.get("scenario") or "anomalous_incursions")
    enemies = list(sess.get("nearby_enemies") or [])
    if target_enemy is None:
        target_enemy = next(
            (
                e for e in enemies
                if isinstance(e, dict)
                and (
                    (eff_inc_id and (e.get("incursion_id") == eff_inc_id or e.get("breach_id") == eff_inc_id))
                    or (quest_id and e.get("linked_quest_id") == quest_id)
                    or e.get("requires_non_lethal_subdue")
                    or e.get("is_anomalous_manifestation")
                )
            ),
            enemies[0] if enemies else None,
        )
    if not target_enemy:
        return {"success": False, "error": "No agitated anomalous entity present to contain."}

    ent_name = str(target_enemy.get("name") or "Anomalous Entity")
    hp = int(target_enemy.get("hp", 10) or 10)
    max_hp = max(1, int(target_enemy.get("max_hp", 40) or 40))
    sapience = str(target_enemy.get("sapience") or "").strip().lower()
    born_disp = str(target_enemy.get("born_disposition") or "").strip().lower()
    is_born_hostile = bool(
        not target_enemy.get("requires_non_lethal_subdue")
        and (born_disp == "hostile" or target_enemy.get("is_anomalous_manifestation"))
    )

    default_pct = 0.50 if (is_born_hostile and sapience == "instinctual") else NON_HOSTILE_SUBDUE_THRESHOLD_PCT
    threshold_pct = float(target_enemy.get("subdue_threshold_pct") or default_pct)
    threshold_hp = max(1, int(max_hp * threshold_pct))
    act = str(action_type or "subdue").strip().lower()

    p_uids = list(party_user_ids or ([user_id] if user_id else ([sess.get("host_user_id")] if sess.get("host_user_id") else [1])))
    lead_uid = user_id or (p_uids[0] if p_uids else 1)
    char = db.get_character(lead_uid) or {}

    forfeit_bounty_gold = False
    if resolution_method or target_enemy.get("contained_via_parley"):
        method_str = str(resolution_method or "Live Capture (Mid-Combat Parley)")
    elif act == "invoke_patron_authority":
        from mechanics.pacts import evaluate_kin_authority
        active_pacts_kin = db.get_player_active_pacts(session_id, lead_uid) if lead_uid else []
        kin_res = evaluate_kin_authority(active_pacts_kin, target_enemy, scenario_or_key=scen_key)
        if not kin_res or not kin_res.get("matched"):
            return {
                "success": False,
                "resolved": False,
                "combat_continues": True,
                "message": f"⚠️ None of your active Entity Contracts hold Kin Authority over **{ent_name}**!",
            }
        dc_kin = 3
        nat_roll, total_check, succeeded = _extract_check_roll_and_success(
            char=char,
            stat_key="CHA",
            dc=dc_kin,
            force_roll=force_roll,
            pre_rolled_check=pre_rolled_check,
        )
        if not succeeded:
            return {
                "success": False,
                "resolved": False,
                "agitated": True,
                "combat_continues": True,
                "roll": nat_roll,
                "total": total_check,
                "dc": dc_kin,
                "message": f"👑 Invoked **{kin_res['patron_name']}** Kin Authority (CHA {total_check} vs DC {dc_kin}), but **{ent_name}** resisted in frenzy!",
            }
        method_str = f"Pacified via Patron Kin Authority ({kin_res['patron_name']})"
    elif act == "accept_boss_pact_surrender":
        if hp <= 0 or hp > max(1, int(max_hp * 0.15)):
            return {
                "success": False,
                "resolved": False,
                "combat_continues": True,
                "message": f"⚠️ **{ent_name}** has not yet yielded! Weaken it to <= 15% HP before demanding an Entity Covenant!",
            }
        from mechanics.pacts import (
            execute_pact_ritual_action,
            synthesize_folklore_patron,
            synthesize_procedural_sapient_patron,
        )
        bp_surr = target_enemy.get("anomaly_blueprint") if isinstance(target_enemy.get("anomaly_blueprint"), dict) else {}
        cid_surr = str(target_enemy.get("codex_id") or bp_surr.get("codex_id") or "").strip()
        if cid_surr:
            surr_patron = synthesize_folklore_patron(cid_surr, scenario_or_key=scen_key)
        else:
            surr_patron = synthesize_procedural_sapient_patron(
                {
                    "anomaly_id": target_enemy.get("incursion_id") or ent_name,
                    "name": ent_name,
                    "primary_element": target_enemy.get("primary_element") or bp_surr.get("primary_element") or "aether",
                    "archetype": target_enemy.get("archetype") or "catalyst",
                    "sapience": "sapient",
                    "form": target_enemy.get("form") or bp_surr.get("form") or "default",
                    "taboo": target_enemy.get("taboo") or bp_surr.get("taboo") or {},
                },
                scenario_or_key=scen_key,
            )
        if not surr_patron:
            return {
                "success": False,
                "resolved": False,
                "combat_continues": True,
                "message": f"⚠️ **{ent_name}** cannot form a sapient Entity Covenant!",
            }
        try:
            sign_res = execute_pact_ritual_action(
                session_id,
                lead_uid,
                "sign",
                patron_id=surr_patron["patron_id"],
                tier=1,
            )
        except ValueError as sign_err:
            return {
                "success": False,
                "resolved": False,
                "combat_continues": True,
                "message": f"⚠️ Cannot bind **{ent_name}**: {sign_err}",
            }
        forfeit_bounty_gold = True
        method_str = f"Bound into Tier I Entity Covenant ({surr_patron.get('canonical_name', ent_name)}) — Bounty Cash Forfeited"
    elif act == "sever_tether":
        ts_cbt = get_enemy_tether_state(target_enemy)
        if not ts_cbt:
            return {
                "success": False,
                "resolved": False,
                "combat_continues": True,
                "message": f"⚠️ **{ent_name}** has no active external tether or vessel to seal.",
            }
        sever_stat = str(ts_cbt.get("sever_stat") or "INT").upper()
        is_dossier_known_t = bool(
            target_enemy.get("dossier_revealed")
            or (isinstance(target_enemy.get("anomaly_blueprint"), dict) and target_enemy["anomaly_blueprint"].get("dossier_revealed"))
        )
        dc_t = 5 if is_dossier_known_t else 7
        nat_roll, total_check, succeeded = _extract_check_roll_and_success(
            char=char,
            stat_key=sever_stat,
            dc=dc_t,
            force_roll=force_roll,
            pre_rolled_check=pre_rolled_check,
        )
        if not succeeded:
            return {
                "success": False,
                "resolved": False,
                "agitated": True,
                "combat_continues": True,
                "roll": nat_roll,
                "total": total_check,
                "dc": dc_t,
                "message": (
                    f"🏺 Attempted to seal **{ts_cbt.get('vessel_name', 'Binding Vessel')}** ({sever_stat} {total_check} vs DC {dc_t}), "
                    f"but **{ent_name}**'s resonance warded off the lock!"
                ),
            }
        seal_res = seal_enemy_tether(target_enemy)
        if (
            hp <= max(1, int(max_hp * 0.50))
            or bool(target_enemy.get("tether_reformed_once"))
            or bool(ts_cbt.get("reformed_once"))
            or bool(target_enemy.get("is_breached"))
        ):
            method_str = f"Tether Sealed ({seal_res['vessel_name']}) & Contained ({sever_stat} {total_check})"
        else:
            db.update_session(session_id, nearby_enemies=enemies)
            return {
                "success": True,
                "resolved": False,
                "tether_sealed": True,
                "combat_continues": True,
                "roll": nat_roll,
                "total": total_check,
                "message": f"{seal_res['message']} Weaken **{ent_name}** to <= 50% HP or defeat it to complete Vault containment!",
            }
    elif act == "folklore_offering_rite":
        bp_off_cbt = target_enemy.get("anomaly_blueprint") if isinstance(target_enemy.get("anomaly_blueprint"), dict) else None
        off_match_cbt = find_matching_offering_in_inventory(lead_uid, bp_off_cbt)
        if not off_match_cbt:
            return {
                "success": False,
                "resolved": False,
                "combat_continues": True,
                "message": f"⚠️ You do not have a matching Folklore Ward or Offering in your inventory for **{ent_name}**!",
            }
        consume_folklore_offering_item(lead_uid, off_match_cbt["item_name"])
        nat_roll, total_check, succeeded = _extract_check_roll_and_success(
            char=char,
            stat_key="INT",
            dc=5,
            force_roll=force_roll,
            pre_rolled_check=pre_rolled_check,
        )
        if not succeeded:
            return {
                "success": False,
                "resolved": False,
                "agitated": True,
                "combat_continues": True,
                "roll": nat_roll,
                "total": total_check,
                "message": f"🎁 Presented **{off_match_cbt['item_name']}** (INT {total_check} vs DC 5), but **{ent_name}** batted the offering aside!",
            }
        method_str = f"Appeased via Folklore Counter-Rite ({off_match_cbt['item_name']})"
    elif act == "combat_persuade":
        if is_born_hostile and sapience in ("instinctual", "non_sapient"):
            return {
                "success": False,
                "resolved": False,
                "agitated": True,
                "combat_continues": True,
                "message": (
                    f"⚠️ **{ent_name}** is **{sapience.replace('_', '-')}** and cannot be reasoned with verbally! "
                    f"Weaken it to <= {int(threshold_pct * 100)}% HP or exploit its Folklore/SCP Taboo to use **[🛡️ Subdue & Contain]**!"
                ),
            }
        is_dossier_known = bool(
            target_enemy.get("dossier_revealed")
            or (isinstance(target_enemy.get("anomaly_blueprint"), dict) and target_enemy["anomaly_blueprint"].get("dossier_revealed"))
        )
        if not is_dossier_known:
            eff_inc_chk = eff_inc_id or str(target_enemy.get("incursion_id") or target_enemy.get("breach_id") or "")
            eff_qid_chk = quest_id or str(target_enemy.get("linked_quest_id") or "")
            if eff_qid_chk:
                q_chk = db.get_quest_by_id(session_id, eff_qid_chk) or {}
                if "dossier_revealed:1" in str(q_chk.get("quest_notes") or ""):
                    is_dossier_known = True
            elif eff_inc_chk:
                for inc_chk in (sess.get("daily_incursions") or sess.get("daily_breaches") or []):
                    if isinstance(inc_chk, dict) and (inc_chk.get("incursion_id") == eff_inc_chk or inc_chk.get("breach_id") == eff_inc_chk):
                        if inc_chk.get("dossier_revealed"):
                            is_dossier_known = True
                        break
        is_taboo_exp = bool(target_enemy.get("taboo_exploited"))
        if is_born_hostile and sapience == "compulsive" and not (is_dossier_known or is_taboo_exp):
            return {
                "success": False,
                "resolved": False,
                "agitated": True,
                "combat_continues": True,
                "message": (
                    f"⚠️ **{ent_name}** is locked in a **Compulsive** folklore loop and ignores blind verbal pleading! "
                    f"Unseal its **Anomaly Dossier**, exploit its **Taboo** first to unlock **[🗣️ Enact Counter-Rite]**, "
                    f"or weaken it to <= {int(threshold_pct * 100)}% HP to use **[🛡️ Subdue & Contain]**!"
                ),
            }
        dc = 6 if (hp <= max(1, int(max_hp * 0.50)) or is_taboo_exp) else 8
        if is_dossier_known:
            dc = max(4, dc - 2)
        nat_roll, total_check, succeeded = _extract_check_roll_and_success(
            char=char,
            stat_key="CHA",
            dc=dc,
            force_roll=force_roll,
            pre_rolled_check=pre_rolled_check,
        )
        if not succeeded:
            return {
                "success": False,
                "resolved": False,
                "agitated": True,
                "combat_continues": True,
                "roll": nat_roll,
                "total": total_check,
                "dc": dc,
                "message": (
                    f"🗣️ Attempted to calm **{ent_name}** mid-combat (CHA {total_check} vs DC {dc}), "
                    f"but its panicked resonance rejected your words!"
                ),
            }
        method_str = (
            f"Enacted Counter-Rite & Contained in Combat (CHA {total_check})"
            if sapience == "compulsive"
            else f"De-escalated & Contained in Combat (CHA {total_check})"
        )
    else:
        can_subdue_now = (
            hp <= threshold_hp
            or bool(target_enemy.get("is_breached"))
            or bool(target_enemy.get("taboo_exploited"))
            or force_roll is not None
        )
        if not can_subdue_now:
            return {
                "success": False,
                "agitated": True,
                "combat_continues": True,
                "message": (
                    f"⚠️ **{ent_name}** is still too thrashing to seal ({hp}/{max_hp} HP)! "
                    f"Carefully weaken it to <= {int(threshold_pct * 100)}% HP ({threshold_hp} HP) without killing it, "
                    f"exploit its Taboo, or attempt **[🗣️ Persuade / Calm]**!"
                ),
            }
        method_str = "Subdued Non-Lethally & Contained"

    # Remove subdued/de-escalated entity from combat if still in nearby_enemies!
    if any(e is target_enemy for e in enemies):
        remaining = [e for e in enemies if e is not target_enemy]
        db.update_session(session_id, nearby_enemies=remaining)

    if not eff_inc_id and target_enemy:
        eff_inc_id = str(target_enemy.get("breach_id") or target_enemy.get("incursion_id") or "")
    eff_quest_id = str(quest_id or target_enemy.get("linked_quest_id") or "")
    eff_sub_obj_id = target_enemy.get("linked_sub_obj_id")
    cat_tag = str(target_enemy.get("category_tag") or "spatial_warp")

    bp_enemy = target_enemy.get("anomaly_blueprint") if isinstance(target_enemy.get("anomaly_blueprint"), dict) else None
    if bp_enemy is None and target_enemy.get("anomaly_type"):
        bp_enemy = {
            "name": ent_name,
            "type": target_enemy.get("anomaly_type"),
            "form": target_enemy.get("form", "cursed_weapon"),
            "element": target_enemy.get("element", "aether"),
            "tier": int(target_enemy.get("tier", 2) or 2),
        }

    # Path A: Linked Daily Anomaly Breach
    incursions = list(sess.get("daily_incursions") or sess.get("daily_breaches") or [])
    target_inc = next((inc for inc in incursions if eff_inc_id and (inc.get("incursion_id") == eff_inc_id or inc.get("breach_id") == eff_inc_id)), None)
    if target_inc:
        if bp_enemy is None and isinstance(target_inc.get("anomaly_blueprint"), dict):
            bp_enemy = target_inc["anomaly_blueprint"]
        if target_inc.get("subtype") == "hostile_breach":
            is_born_hostile = True

        refund_res = refund_trick_tax_gold_on_containment(session_id, lead_uid, target_inc=target_inc)
        turn_now = _resolve_session_turn_number(session_id, sess)
        for inc in incursions:
            if inc.get("incursion_id") == eff_inc_id or inc.get("breach_id") == eff_inc_id:
                inc["resolved"] = True
                inc["agitated"] = False
                inc["resolved_at_turn"] = turn_now

        db.update_session(session_id, extra={"daily_incursions": incursions, "daily_breaches": None})

        gold_gain = 0 if forfeit_bounty_gold else int(target_inc.get("reward_gold", 120) or 120)
        xp_gain = int(target_inc.get("reward_xp", 85) or 85)
        rep_bonus = 0
        if is_born_hostile:
            xp_gain = int(round(xp_gain * 1.20))
            rep_bonus = 5
            try:
                from mechanics.social.factions import update_agent_promotion_reputation
                update_agent_promotion_reputation(
                    session_id=session_id,
                    delta_rep=5,
                    reason=f"Live-Captured Hostile Anomaly '{target_inc['entity_name']}'",
                    user_id=lead_uid,
                )
            except Exception:
                pass
        if lead_uid:
            db.apply_hp_mp_delta(lead_uid, gold_delta=gold_gain)
            db.add_xp(lead_uid, xp_gain)

        vault_entry = record_contained_anomaly_to_vault_log(
            session_id=session_id,
            entity_name=target_inc["entity_name"],
            category_tag=target_inc["category_tag"],
            subtype=target_inc["subtype"],
            location=target_inc["location"],
            containment_note=target_inc.get("containment_note", ""),
            resolution_method=method_str,
            user_id=lead_uid,
        )
        converted_res = handle_secured_object_anomaly_conversion(
            session_id=session_id,
            user_id=lead_uid,
            blueprint=bp_enemy,
            scen_key=scen_key,
            entity_name=target_inc["entity_name"],
            skip_codex_progress=True,
        )
        dropped_gear = (converted_res["item"]["name"] if converted_res and converted_res.get("item") else "") or _roll_optional_incursion_gear_drop(lead_uid, scen_key)
        gear_suffix = f" {converted_res['notice']}" if converted_res else (f" Recovered salvage: **{dropped_gear}**!" if dropped_gear else "")
        refund_suffix = f" {refund_res['notice']}" if refund_res.get("notice") else ""
        live_bonus_suffix = " *(+20% Live-Capture XP & +5 Promotion Rep)*" if is_born_hostile else ""
        icon_used = "🗣️" if act == "combat_persuade" else "🛡️"
        return {
            "success": True,
            "resolved": True,
            "subdued": True,
            "live_capture_bonus": is_born_hostile,
            "rep_bonus": rep_bonus,
            "trick_tax_refunded": int(refund_res.get("refunded_gold", 0) or 0),
            "converted_gear": converted_res,
            "reward_gold": gold_gain,
            "reward_xp": xp_gain,
            "reward_item": dropped_gear,
            "vault_entry": vault_entry,
            "message": (
                f"{icon_used} Contained **{target_inc['entity_name']}** alive!{live_bonus_suffix} "
                f"Earned +{gold_gain}G, +{xp_gain} XP, and logged into {vault_entry['vault_facility']}.{refund_suffix}{gear_suffix}"
            ),
        }

    # Path B: Linked Bounty or Story Quest Sub-Objective
    if not eff_quest_id:
        for q_cand in (db.get_session_quests(session_id, status="Active") or []):
            if (not is_born_hostile and is_non_hostile_entity_quest(q_cand)) or (
                is_born_hostile and ent_name.lower() in str(q_cand.get("objective") or "").lower()
            ):
                eff_quest_id = str(q_cand.get("quest_id") or "")
                break

    if bp_enemy is None and eff_quest_id:
        q_row_bp = db.get_quest_by_id(session_id, eff_quest_id) or {}
        bp_enemy = parse_blueprint_from_notes(q_row_bp)

    quest_res = {}
    refund_res_q = {"refunded_gold": 0, "notice": ""}
    if eff_quest_id:
        refund_res_q = refund_trick_tax_gold_on_containment(session_id, lead_uid, quest_id=eff_quest_id)
        quest_res = _complete_or_advance_linked_quest_containment(
            session_id=session_id,
            quest_id=eff_quest_id,
            sub_obj_id=eff_sub_obj_id,
            entity_name=ent_name,
            category_tag=cat_tag,
            resolution_method=method_str,
            party_user_ids=p_uids,
            forfeit_bounty_gold=forfeit_bounty_gold,
        )

    rep_bonus = 0
    bonus_xp_awarded = 0
    if is_born_hostile:
        base_q_xp = int(((db.get_quest_by_id(session_id, eff_quest_id) if eff_quest_id else None) or {}).get("reward_xp", 150) or 150)
        bonus_xp_awarded = max(20, int(round(base_q_xp * 0.20)))
        rep_bonus = 5
        if lead_uid:
            db.add_xp(lead_uid, bonus_xp_awarded)
        try:
            from mechanics.social.factions import update_agent_promotion_reputation
            update_agent_promotion_reputation(
                session_id=session_id,
                delta_rep=5,
                reason=f"Live-Captured Hostile Target '{ent_name}'",
                user_id=lead_uid,
            )
        except Exception:
            pass

    converted_res = handle_secured_object_anomaly_conversion(
        session_id=session_id,
        user_id=lead_uid,
        blueprint=bp_enemy,
        scen_key=scen_key,
        entity_name=ent_name,
    )

    vault_entry = quest_res.get("vault_entry") or record_contained_anomaly_to_vault_log(
        session_id=session_id,
        entity_name=ent_name,
        category_tag=cat_tag,
        subtype="hostile_breach" if is_born_hostile else "non_hostile_entity",
        location=str(sess.get("current_location") or "Metropolitan Grid"),
        resolution_method=method_str,
        user_id=lead_uid,
        quest_id=eff_quest_id,
        sub_obj_id=eff_sub_obj_id,
    )
    next_wp = quest_res.get("next_waypoint")
    if quest_res.get("all_stages_complete") and quest_res.get("quest_title"):
        follow_note = f" Objective **'{quest_res['quest_title']}'** completed!"
    elif next_wp and next_wp.get("stage_label"):
        follow_note = f" Next Stage: *{next_wp['stage_label']}*."
    else:
        follow_note = ""

    live_bonus_suffix = f" *(+{bonus_xp_awarded} Live-Capture Bonus XP & +5 Promotion Rep)*" if is_born_hostile else ""
    refund_q_suffix = f" {refund_res_q['notice']}" if refund_res_q.get("notice") else ""
    conv_suffix = f" {converted_res['notice']}" if converted_res else ""
    icon_used = "🗣️" if act == "combat_persuade" else "🛡️"
    return {
        "success": True,
        "resolved": True,
        "subdued": True,
        "live_capture_bonus": is_born_hostile,
        "bonus_xp": bonus_xp_awarded,
        "rep_bonus": rep_bonus,
        "trick_tax_refunded": int(refund_res_q.get("refunded_gold", 0) or 0),
        "converted_gear": converted_res,
        "quest_containment": quest_res,
        "vault_entry": vault_entry,
        "message": (
            f"{icon_used} Contained **{ent_name}** alive and sealed it into a containment unit!{live_bonus_suffix} "
            f"Logged to {vault_entry['vault_facility']}.{follow_note}{refund_q_suffix}{conv_suffix}"
        ),
    }


def handle_killed_non_hostile_entity(
    session_id: int,
    dead_enemy: Dict[str, Any],
    user_id: Optional[int] = None,
    party_user_ids: Optional[List[int]] = None,
    session: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Handles the fallout of LETHALLY KILLING (`0 HP`) a `requires_non_lethal_subdue` Non-Hostile Entity:
    - Daily Non-Hostile Incursion: Marks resolved (`killed_lethally=True`), forfeits all rewards (`0G`, `0 XP`, `0` gear, NO Vault Log).
    - Side Bounty / Mandatory Daily Bounty (`not is_story_quest`): Hard-fails the bounty (`status='Failed'`),
      applies client/faction penalties, and deducts `-15` Promotion Rep (`is_missed_mandatory=True`) if Mandatory Daily!
    - Story Quest Sub-Objective (`is_story_quest == 1`): Applies `dire_cost` fail-forward (`-5 HP` backlash,
      advances sub-objective without soft-locking campaign, NO Vault Log).
    """
    if not session_id or not isinstance(dead_enemy, dict):
        return {}

    sess = session if isinstance(session, dict) else (db.get_session(session_id) or {})
    ent_name = str(dead_enemy.get("name") or "Non-Hostile Entity")
    p_uids = list(party_user_ids or ([user_id] if user_id else ([sess.get("host_user_id")] if sess.get("host_user_id") else [1])))
    lead_uid = user_id or (p_uids[0] if p_uids else 1)

    inc_id = str(dead_enemy.get("incursion_id") or dead_enemy.get("breach_id") or "")
    if inc_id:
        fresh_sess = db.get_session(session_id) or sess
        incursions = list(fresh_sess.get("daily_incursions") or fresh_sess.get("daily_breaches") or [])
        turn_now = _resolve_session_turn_number(session_id, fresh_sess)
        for inc in incursions:
            if inc.get("incursion_id") == inc_id or inc.get("breach_id") == inc_id:
                inc["resolved"] = True
                inc["agitated"] = False
                inc["killed_lethally"] = True
                inc["resolved_at_turn"] = turn_now

        db.update_session(session_id, extra={"daily_incursions": incursions, "daily_breaches": None})
        if isinstance(session, dict):
            session["daily_incursions"] = incursions
            session["daily_breaches"] = incursions
        msg = (
            f"❌ **Containment Failed (Target Destroyed)!** Lethal force shattered **{ent_name}**—"
            f"all live-containment rewards forfeited (+0 XP, +0 Gold, not logged to Containment Vault)."
        )
        return {"handled": True, "type": "incursion_forfeited", "killed_lethally": True, "message": msg}

    linked_qid = str(dead_enemy.get("linked_quest_id") or "")
    linked_so_id = dead_enemy.get("linked_sub_obj_id")
    quest = db.get_quest_by_id(session_id, linked_qid) if linked_qid else None
    if not quest:
        for q_cand in (db.get_session_quests(session_id, status="Active") or []):
            if is_non_hostile_entity_quest(q_cand):
                quest = q_cand
                linked_qid = str(q_cand.get("quest_id") or "")
                break

    if not quest or quest.get("status") != "Active":
        return {
            "handled": True,
            "type": "unlinked_non_hostile_killed",
            "killed_lethally": True,
            "message": f"❌ **Non-Hostile Specimen Destroyed!** **{ent_name}** dissolved under lethal force (+0 Gold).",
        }

    if not quest.get("is_story_quest"):
        from game_engine.quests import apply_quest_failure_consequences
        fail_res = apply_quest_failure_consequences(
            session_id=session_id,
            quest=quest,
            party_user_ids=p_uids,
            reason="killed_non_hostile_target",
            session=sess,
        )
        promo_suffix = f" {fail_res['promotion_penalty_notice']}" if fail_res.get("promotion_penalty_notice") else ""
        msg = (
            f"❌ **Bounty Failed — Non-Hostile Target Killed!** Lethal damage destroyed **{ent_name}**, "
            f"failing **'{quest.get('title', 'Live Capture Bounty')}'**!{promo_suffix}"
        )
        return {
            "handled": True,
            "type": "bounty_failed",
            "quest_id": linked_qid,
            "killed_lethally": True,
            "fail_result": fail_res,
            "message": msg,
        }

    # Story Quest Sub-Objective: Fail-Forward at a Dire Cost (-5 HP backlash, no Vault Log)
    now = time.time()
    with db.get_conn() as conn:
        if linked_so_id is not None:
            conn.execute(
                "UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=?",
                (now, session_id, linked_qid, linked_so_id),
            )
        else:
            conn.execute(
                "UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=?",
                (now, session_id, linked_qid),
            )

    sub_objs = list(quest.get("sub_objectives") or [])
    if sub_objs:
        for so in sub_objs:
            if isinstance(so, dict) and (linked_so_id is None or str(so.get("id")) == str(linked_so_id)):
                so["completed"] = True
                so["resolution_approach"] = "dire_cost"
                break
        done_cnt = sum(1 for s in sub_objs if isinstance(s, dict) and s.get("completed"))
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE quests SET sub_objectives_json=?, progress=?, resolution_approach='dire_cost', updated_at=? WHERE session_id=? AND quest_id=?",
                (json.dumps(sub_objs), f"{done_cnt}/{len(sub_objs)} Cleared", now, session_id, linked_qid),
            )
    else:
        db.set_quest_resolution_approach(session_id, linked_qid, "dire_cost")

    db.reset_quest_strikes(session_id, linked_qid)
    if lead_uid:
        db.apply_hp_mp_delta(lead_uid, hp_delta=-5)

    msg = (
        f"⚠️ **Dire Cost — Specimen Shattered!** Lethal force destroyed **{ent_name}**, unleashing a violent "
        f"anomalous backlash (-5 HP). You salvage only fragmented residual readings to press the chapter forward "
        f"(specimen lost; not logged to Containment Vault)."
    )
    return {
        "handled": True,
        "type": "story_dire_cost",
        "quest_id": linked_qid,
        "sub_obj_id": linked_so_id,
        "killed_lethally": True,
        "message": msg,
    }


def resolve_non_hostile_incursion_action(
    session_id: int,
    user_id: int,
    incursion_id: str = "",
    action_type: str = "pacify",
    stat_used: str = "CHA",
    force_roll: Optional[int] = None,
    pre_rolled_check: Any = None,
    breach_id: str = "",
    player_text: str = "",
) -> Dict[str, Any]:
    """
    Resolves an interaction with a Daily Anomaly Breach:
    - Out-of-combat narrative containment (`persuade` [CHA], `calm` [PER], `outwit` [INT], `environment` [AGI],
      plus legacy `pacify`/`analyze`/`observe` and `seal_ability`):
      - Success (`total >= 10` or `seal_ability`):
        Marks incursion resolved, grants 100% Gold & XP + Anomalous Gear drop chance,
        and logs the entity/phenomenon into `contained_anomalies_log`.
      - Failure on `non_hostile_entity` increments strikes (`max_strikes = 2`; `nat_roll <= 2` deals 2 strikes):
        - Strike 1/2: Emits temperament-specific warning (`timid` poised to flee vs `volatile` poised to lash out).
        - Strike 2/2:
          - `'timid'` entity -> **Escapes!** Marks resolved (`escaped=True`), 0 rewards, no Vault Log.
          - `'volatile'` entity -> **Becomes Hostile!** Spawns into `nearby_enemies` (`requires_non_lethal_subdue=True`, `<= 35%` HP subdue).
    - `action_type == "attack"`:
      Immediately engages a `hostile_breach` or agitates a `non_hostile_entity` into combat.
    - `action_type in ("subdue", "combat_persuade")`:
      Delegates to `resolve_anomalous_combat_containment` (`<= 35%` HP subdue or in-combat `CHA` de-escalation).
    """
    eff_id = str(incursion_id or breach_id or "").strip()
    sess = db.get_session(session_id) or {}
    scen_key = str(sess.get("scenario") or "anomalous_incursions")
    incursions = list(sess.get("daily_incursions") or sess.get("daily_breaches") or [])
    target_inc = next((inc for inc in incursions if eff_id and (inc.get("incursion_id") == eff_id or inc.get("breach_id") == eff_id)), None)
    if not target_inc:
        loc_inc = get_active_incursion_at_location(session_id)
        if loc_inc:
            eff_id = str(loc_inc.get("breach_id") or loc_inc.get("incursion_id") or "")
            incursion_id = eff_id
            target_inc = next(
                (inc for inc in incursions if eff_id and (inc.get("incursion_id") == eff_id or inc.get("breach_id") == eff_id)),
                loc_inc,
            )
    if not target_inc:
        return {"success": False, "error": "No active Anomaly Breach found."}
    if target_inc.get("resolved"):
        return {"success": False, "already_resolved": True, "error": "This Anomaly Breach has already been contained."}

    act = str(action_type or "pacify").strip().lower()
    if (
        act.startswith("anomaly_inquiry")
        or act.startswith("anomaly_pattern")
        or act.startswith("question_trap")
        or act in ("converse", "study_pattern")
    ):
        return resolve_anomaly_dialogue_inquiry(
            session_id=session_id,
            entity_name=str(target_inc.get("entity_name") or ""),
            incursion_id=eff_id,
            breach_id=eff_id,
            inquiry_type=act,
            player_text=player_text,
            user_id=user_id,
            session=sess,
        )
    if act in ("reveal_dossier", "scan_dossier", "investigate_dossier"):
        rev_res = reveal_anomaly_dossier(session_id=session_id, incursion_id=eff_id, breach_id=eff_id)
        d_sum = rev_res.get("dossier_summary") or "Anomaly Taboo and Containment Protocol unsealed."
        return {
            "success": True,
            "resolved": False,
            "dossier_revealed": True,
            "dossier_summary": d_sum,
            "message": f"🔍 **Anomaly Dossier Unsealed:** {d_sum}",
        }
    has_live_combat_enemies = any(
        isinstance(e, dict) and int(e.get("hp", 0) or 0) > 0
        for e in (sess.get("nearby_enemies") or [])
    )
    if act in ("subdue", "combat_persuade", "sever_tether") or (act == "folklore_offering_rite" and has_live_combat_enemies):
        return resolve_anomalous_combat_containment(
            session_id=session_id,
            user_id=user_id,
            action_type=act,
            incursion_id=eff_id,
            breach_id=eff_id,
            force_roll=force_roll,
            pre_rolled_check=pre_rolled_check,
        )

    if target_inc.get("subtype") == "hostile_breach":
        act = "attack"

    approach_default_stats = {
        "persuade": "CHA",
        "nh_persuade": "CHA",
        "calm": "PER",
        "nh_calm": "PER",
        "outwit": "INT",
        "nh_outwit": "INT",
        "environment": "AGI",
        "nh_environment": "AGI",
        "exploit_taboo": "INT",
        "pacify": str(target_inc.get("preferred_stat") or "CHA").upper(),
        "analyze": "INT",
        "observe": "PER",
    }
    approach_method_labels = {
        "persuade": "Persuaded & Contained Willingly",
        "nh_persuade": "Persuaded & Contained Willingly",
        "calm": "Calmed & Sealed Non-Lethally",
        "nh_calm": "Calmed & Sealed Non-Lethally",
        "outwit": "Outwitted into Containment Snare",
        "nh_outwit": "Outwitted into Containment Snare",
        "environment": "Cornered via Environmental Containment",
        "nh_environment": "Cornered via Environmental Containment",
        "exploit_taboo": "Contained via Folklore/SCP Taboo Exploit",
        "analyze": "Analyzed & Sealed",
        "pacify": "Pacified & Contained",
    }

    char = db.get_character(user_id) or {}
    stat_key = str(stat_used or approach_default_stats.get(act) or target_inc.get("preferred_stat") or "CHA").upper()

    # Intentional attack on hostile_breach or non_hostile_entity immediately starts combat
    if act == "attack" and target_inc.get("subtype") in ("non_hostile_entity", "hostile_breach"):
        bp_inc = target_inc.get("anomaly_blueprint") if isinstance(target_inc.get("anomaly_blueprint"), dict) else None
        if target_inc.get("subtype") == "non_hostile_entity":
            enemy_obj = spawn_agitated_non_hostile_entity(
                session_id=session_id,
                entity_name=target_inc["entity_name"],
                location=target_inc.get("location", "City"),
                category_tag=target_inc.get("category_tag", "spatial_warp"),
                incursion_id=eff_id,
                breach_id=eff_id,
                blueprint=bp_inc,
            )
            breach_msg = (
                f"⚠️ **{target_inc['entity_name']}** has turned hostile in self-defense! "
                f"Carefully weaken it to <= 35% HP to use **[🛡️ Subdue & Contain]**, or use **[🗣️ Persuade / Calm]** "
                f"(killing it destroys the specimen and forfeits all rewards)!"
            )
        else:
            if bp_inc:
                bp_inc, _unmask_hb = unmask_blueprint_disguise(bp_inc)
                if _unmask_hb and bp_inc.get("canonical_name"):
                    target_inc["entity_name"] = str(bp_inc["canonical_name"])
                    target_inc["anomaly_blueprint"] = bp_inc
                try:
                    db.record_session_anomaly_field_log(session_id, bp_inc, stage="sighted", location=str(target_inc.get("location") or ""))
                    if bp_inc.get("codex_id"):
                        db.record_folklore_codex_progress(
                            db.get_session_participant_user_ids(session_id) or ([user_id] if user_id else []),
                            str(bp_inc["codex_id"]),
                            stage="sighted",
                        )
                except Exception:
                    pass
                enemy_obj = instantiate_enemy_from_blueprint(
                    bp_inc,
                    tier=3,
                    is_agitated_non_hostile=False,
                    incursion_id=eff_id,
                )
                enemy_obj["name"] = target_inc["entity_name"]
            else:
                from mechanics.combat.enemies import generate_scenario_enemy
                enemy_obj = generate_scenario_enemy(
                    scenario=scen_key,
                    location=target_inc.get("location", "City"),
                    chapter=int(sess.get("current_chapter", 1) or 1),
                    custom_name=target_inc["entity_name"],
                    custom_archetype="Spatial Stalker" if target_inc.get("category_tag") == "spatial_warp" else "Cognitohazard Caster",
                    exact_tier=3,
                )
                enemy_obj["incursion_id"] = eff_id
                enemy_obj["breach_id"] = eff_id
            enemies = list(sess.get("nearby_enemies") or [])
            enemies.append(enemy_obj)
            db.update_session(session_id, nearby_enemies=enemies)
            breach_msg = f"⚔️ Hostile Breach Engaged: **{target_inc['entity_name']}** lunges from the spatial tear! Defeat it in combat to seal the breach!"

        for inc in incursions:
            if inc.get("incursion_id") == eff_id or inc.get("breach_id") == eff_id:
                inc["agitated"] = True

        db.update_session(session_id, extra={"daily_incursions": incursions, "daily_breaches": None})
        return {
            "success": False,
            "agitated": True,
            "combat_started": True,
            "enemy": enemy_obj,
            "message": breach_msg,
        }

    # Evaluate Folklore/SCP Taboo, Offering Rite, Paradoxical Omen & Dossier Bonus on containment check
    bp_inc = target_inc.get("anomaly_blueprint") if isinstance(target_inc.get("anomaly_blueprint"), dict) else None
    offering_used_note = ""
    if act == "folklore_offering_rite":
        off_match_inc = find_matching_offering_in_inventory(user_id, bp_inc)
        if not off_match_inc:
            return {
                "success": False,
                "resolved": False,
                "agitated": False,
                "message": f"⚠️ You do not have a matching Folklore Ward or Offering in your inventory for **{target_inc['entity_name']}**!",
            }
        consume_folklore_offering_item(user_id, off_match_inc["item_name"])
        rev_off = reveal_anomaly_dossier(session_id=session_id, incursion_id=eff_id, breach_id=eff_id)
        bp_inc = rev_off.get("blueprint") or bp_inc
        target_inc["dossier_revealed"] = True
        if bp_inc and bp_inc.get("canonical_name"):
            target_inc["entity_name"] = str(bp_inc["canonical_name"])
        approach_method_labels["folklore_offering_rite"] = f"Appeased via Folklore Offering ({off_match_inc['item_name']})"
        offering_used_note = f" 🎁 Consumed **{off_match_inc['item_name']}** (-5 DC Folklore Counter-Rite)!"

    taboo_eval = evaluate_taboo_interaction(bp_inc, action_label=act, stat_used=stat_key, incursion_action=act)
    dc_eff = 10
    if act == "folklore_offering_rite":
        dc_eff = max(4, dc_eff - 5)
    elif target_inc.get("dossier_revealed") or (bp_inc and bp_inc.get("dossier_revealed")):
        dc_eff -= 2
    if taboo_eval.get("exploited"):
        dc_eff = max(4, dc_eff - int(taboo_eval.get("check_bonus", 3) or 3))
    elif int(target_inc.get("prank_dc_penalty", 0) or 0) != 0:
        dc_eff = max(4, dc_eff + int(target_inc.get("prank_dc_penalty", 0) or 0))

    paradox_eval = (
        evaluate_omen_paradox(
            bp_inc,
            dossier_revealed=bool(target_inc.get("dossier_revealed") or (bp_inc and bp_inc.get("dossier_revealed"))),
            is_observation=act in ("calm", "nh_calm", "observe", "analyze"),
        )
        if act in ("calm", "nh_calm", "observe", "analyze")
        else {"has_paradox": False, "dc_mod": 0, "note": ""}
    )
    if paradox_eval.get("has_paradox") and int(paradox_eval.get("dc_mod", 0) or 0) < 0:
        dc_eff = max(4, dc_eff + int(paradox_eval["dc_mod"]))

    nat_roll, total_check, check_succeeded = _extract_check_roll_and_success(
        char=char,
        stat_key=stat_key,
        dc=dc_eff,
        force_roll=force_roll,
        pre_rolled_check=pre_rolled_check,
    )

    # Success resolution (seal_ability or check_succeeded)
    if act == "seal_ability" or check_succeeded:
        refund_res = refund_trick_tax_gold_on_containment(session_id, user_id, target_inc=target_inc)
        turn_now = _resolve_session_turn_number(session_id, sess)
        for inc in incursions:
            if inc.get("incursion_id") == eff_id or inc.get("breach_id") == eff_id:
                inc["resolved"] = True
                inc["agitated"] = False
                inc["prank_dc_penalty"] = 0
                inc["resolved_at_turn"] = turn_now

        db.update_session(session_id, extra={"daily_incursions": incursions, "daily_breaches": None})

        gold_gain = int(target_inc.get("reward_gold", 120) or 120)
        xp_gain = int(target_inc.get("reward_xp", 85) or 85)
        if user_id:
            db.apply_hp_mp_delta(user_id, gold_delta=gold_gain)
            db.add_xp(user_id, xp_gain)

        method_desc = (
            "Sacred Seal / Ability Containment"
            if act == "seal_ability"
            else f"{approach_method_labels.get(act, 'Pacified')} ({stat_key} Check {total_check})"
        )
        vault_entry = record_contained_anomaly_to_vault_log(
            session_id=session_id,
            entity_name=target_inc["entity_name"],
            category_tag=target_inc["category_tag"],
            subtype=target_inc["subtype"],
            location=target_inc["location"],
            containment_note=target_inc.get("containment_note", ""),
            resolution_method=method_desc,
            user_id=user_id,
        )
        converted_res = handle_secured_object_anomaly_conversion(
            session_id=session_id,
            user_id=user_id,
            blueprint=bp_inc or {"name": target_inc["entity_name"], "type": target_inc.get("anomaly_type", "")},
            scen_key=scen_key,
            entity_name=target_inc["entity_name"],
            skip_codex_progress=True,
        )
        dropped_gear = (converted_res["item"]["name"] if converted_res and converted_res.get("item") else "") or _roll_optional_incursion_gear_drop(user_id, scen_key)
        gear_suffix = f" {converted_res['notice']}" if converted_res else (f" Recovered salvage: **{dropped_gear}**!" if dropped_gear else "")
        refund_suffix = f" {refund_res['notice']}" if refund_res.get("notice") else ""
        taboo_note = f" {taboo_eval['log_message']}" if taboo_eval.get("exploited") else ""
        paradox_note_s = f" {paradox_eval['note']}" if paradox_eval.get("has_paradox") and paradox_eval.get("note") else ""
        return {
            "success": True,
            "resolved": True,
            "approach": act,
            "taboo_exploited": bool(taboo_eval.get("exploited")),
            "trick_tax_refunded": int(refund_res.get("refunded_gold", 0) or 0),
            "converted_gear": converted_res,
            "reward_gold": gold_gain,
            "reward_xp": xp_gain,
            "reward_item": dropped_gear,
            "vault_entry": vault_entry,
            "message": (
                f"✨ Successfully contained **{target_inc['entity_name']}** via {approach_method_labels.get(act, 'Containment Protocol')}!{offering_used_note}{taboo_note}{paradox_note_s} "
                f"Earned +{gold_gain}G, +{xp_gain} XP, and logged into {vault_entry['vault_facility']}.{refund_suffix}{gear_suffix}"
            ),
        }

    # Failed check handling on Non-Hostile Entity: Temperament-Driven Strike Escalation!
    if target_inc.get("subtype") == "non_hostile_entity":
        temperament = get_non_hostile_entity_temperament(
            seed_key=incursion_id,
            explicit=str(target_inc.get("temperament") or (bp_inc or {}).get("non_hostile_temperament") or ""),
        )
        prev_strikes = int(target_inc.get("strikes", 0) or 0)
        max_strikes = int(target_inc.get("max_strikes", 2) or 2)
        strike_delta = 2 if nat_roll <= 2 else 1
        if taboo_eval.get("violated") and int(taboo_eval.get("strike_delta", 0) or 0) > 0:
            strike_delta = max(strike_delta, strike_delta + 1)
            if temperament not in ("mischievous", "spook") and user_id and int(taboo_eval.get("player_backlash_dmg", 0) or 0) > 0:
                db.apply_hp_mp_delta(user_id, hp_delta=-4)
        new_strikes = prev_strikes + strike_delta

        if new_strikes < max_strikes:
            side_fx: Dict[str, Any] = {}
            if temperament in ("mischievous", "spook"):
                side_fx = apply_non_hostile_strike_side_effects(
                    session_id=session_id,
                    user_id=user_id,
                    entity_name=str(target_inc.get("entity_name") or ""),
                    temperament=temperament,
                    is_final_strike=False,
                    seed_key=eff_id,
                    incursion_id=eff_id,
                    target_inc=target_inc,
                )
            for inc in incursions:
                if inc.get("incursion_id") == eff_id or inc.get("breach_id") == eff_id:
                    inc["strikes"] = new_strikes
                    inc["temperament"] = temperament

            db.update_session(session_id, extra={"daily_incursions": incursions, "daily_breaches": None})
            if temperament in ("mischievous", "spook") and side_fx.get("warn_suffix"):
                warn_msg = (
                    f"⚠️ Containment attempt on **{target_inc['entity_name']}** faltered ({stat_key} {total_check} vs DC {dc_eff}) "
                    f"[{new_strikes}/{max_strikes} Strikes]! {side_fx['warn_suffix']}"
                )
            elif temperament == "timid":
                warn_msg = (
                    f"⚠️ Containment attempt on **{target_inc['entity_name']}** faltered ({stat_key} {total_check} vs DC {dc_eff}) "
                    f"[{new_strikes}/{max_strikes} Strikes]! Startled, it edges toward an escape seam—one more failed check and it will vanish!"
                )
            else:
                warn_msg = (
                    f"⚠️ Containment attempt on **{target_inc['entity_name']}** faltered ({stat_key} {total_check} vs DC {dc_eff}) "
                    f"[{new_strikes}/{max_strikes} Strikes]! Its anomalous aura bristles aggressively—one more failed check and it will turn hostile!"
                )
            return {
                "success": False,
                "resolved": False,
                "agitated": False,
                "escaped": False,
                "combat_started": False,
                "temperament": temperament,
                "strikes": new_strikes,
                "max_strikes": max_strikes,
                "gold_stolen": int(side_fx.get("gold_stolen", 0) or 0),
                "mp_drained": int(side_fx.get("mp_drained", 0) or 0),
                "prank_dc_penalty": int(side_fx.get("prank_dc_penalty", 0) or 0),
                "directive": str(side_fx.get("directive") or ""),
                "roll": nat_roll,
                "total": total_check,
                "message": warn_msg,
            }

        # Max strikes reached (>= 2): branch by temperament!
        if temperament in ("timid", "mischievous", "spook"):
            side_fx_final: Dict[str, Any] = {}
            if temperament in ("mischievous", "spook"):
                side_fx_final = apply_non_hostile_strike_side_effects(
                    session_id=session_id,
                    user_id=user_id,
                    entity_name=str(target_inc.get("entity_name") or ""),
                    temperament=temperament,
                    is_final_strike=True,
                    seed_key=eff_id,
                    incursion_id=eff_id,
                    target_inc=target_inc,
                )
            turn_now = _resolve_session_turn_number(session_id, sess)
            for inc in incursions:
                if inc.get("incursion_id") == eff_id or inc.get("breach_id") == eff_id:
                    inc["strikes"] = new_strikes
                    inc["resolved"] = True
                    inc["escaped"] = True
                    inc["agitated"] = False
                    inc["temperament"] = temperament
                    inc["resolved_at_turn"] = turn_now

            db.update_session(session_id, extra={"daily_incursions": incursions, "daily_breaches": None})
            _esc_names = get_blueprint_alias_names(target_inc.get("anomaly_blueprint"), str(target_inc.get("entity_name") or ""))
            _prune_anomaly_from_scene_npcs(
                session_id,
                _esc_names[0] if _esc_names else "",
                extra_names=_esc_names[1:],
                session=sess,
                persist_db=True,
            )
            esc_msg = str(side_fx_final.get("escape_message") or "") or (
                f"💨 **Entity Escaped!** Startled by repeated failed containment attempts ({stat_key} {total_check} vs DC {dc_eff}), "
                f"**{target_inc['entity_name']}** slipped through a spatial seam and vanished! Live-containment rewards forfeited."
            )
            return {
                "success": False,
                "resolved": True,
                "escaped": True,
                "agitated": False,
                "combat_started": False,
                "temperament": temperament,
                "strikes": new_strikes,
                "max_strikes": max_strikes,
                "gold_stolen": int(side_fx_final.get("gold_stolen", 0) or 0),
                "total_escrowed_gold": int(side_fx_final.get("total_escrowed_gold", 0) or 0),
                "mp_drained": int(side_fx_final.get("mp_drained", 0) or 0),
                "status_applied": str(side_fx_final.get("status_applied") or ""),
                "directive": str(side_fx_final.get("directive") or ""),
                "roll": nat_roll,
                "total": total_check,
                "message": esc_msg,
            }

        # Volatile temperament -> Agitated Combat!
        enemy_obj = spawn_agitated_non_hostile_entity(
            session_id=session_id,
            entity_name=target_inc["entity_name"],
            location=target_inc.get("location", "City"),
            category_tag=target_inc.get("category_tag", "spatial_warp"),
            incursion_id=eff_id,
            breach_id=eff_id,
            blueprint=bp_inc,
        )
        for inc in incursions:
            if inc.get("incursion_id") == eff_id or inc.get("breach_id") == eff_id:
                inc["strikes"] = new_strikes
                inc["agitated"] = True
                inc["temperament"] = "volatile"

        db.update_session(session_id, extra={"daily_incursions": incursions, "daily_breaches": None})
        return {
            "success": False,
            "resolved": False,
            "agitated": True,
            "combat_started": True,
            "temperament": "volatile",
            "strikes": new_strikes,
            "max_strikes": max_strikes,
            "enemy": enemy_obj,
            "roll": nat_roll,
            "total": total_check,
            "message": (
                f"⚠️ **Entity Agitated into Combat!** Provoked by repeated containment failures ({stat_key} {total_check} vs DC {dc_eff}), "
                f"**{target_inc['entity_name']}** lashes out violently! Weaken it to <= 35% HP to use **[🛡️ Subdue & Contain]** "
                f"or attempt **[🗣️ Persuade / Calm]**—killing it will destroy the specimen and forfeit all rewards!"
            ),
        }

    return {
        "success": False,
        "resolved": False,
        "agitated": False,
        "roll": nat_roll,
        "total": total_check,
        "message": f"Containment attempt on {target_inc['entity_name']} faltered ({stat_key} check {total_check} vs DC {dc_eff}), but the anomaly remains stable enough to try again.",
    }


def mark_hostile_incursion_resolved_on_victory(
    session_id: int,
    incursion_id: str = "",
    user_id: Optional[int] = None,
    breach_id: str = "",
    prevent_vault_capture: bool = False,
) -> Optional[Dict[str, Any]]:
    """Marks a hostile Daily Anomaly Breach resolved upon defeating its breach entity in combat."""
    eff_id = str(incursion_id or breach_id or "").strip()
    if not session_id or not eff_id:
        return None
    sess = db.get_session(session_id) or {}
    scen_key = str(sess.get("scenario") or "anomalous_incursions")
    incursions = list(sess.get("daily_incursions") or sess.get("daily_breaches") or [])
    target_inc = next(
        (inc for inc in incursions if (inc.get("incursion_id") == eff_id or inc.get("breach_id") == eff_id) and not inc.get("resolved")),
        None,
    )
    if not target_inc:
        return None

    # Safety guard: killing a non_hostile_entity in combat NEVER awards hostile victory rewards!
    if target_inc.get("subtype") == "non_hostile_entity":
        kill_res = handle_killed_non_hostile_entity(
            session_id=session_id,
            dead_enemy={"name": target_inc.get("entity_name", "Entity"), "incursion_id": incursion_id, "requires_non_lethal_subdue": True},
            user_id=user_id,
            session=sess,
        )
        return {
            "resolved": True,
            "killed_lethally": True,
            "reward_gold": 0,
            "reward_xp": 0,
            "reward_item": "",
            "message": kill_res.get("message", ""),
        }

    turn_now = _resolve_session_turn_number(session_id, sess)
    for inc in incursions:
        if inc.get("incursion_id") == eff_id or inc.get("breach_id") == eff_id:
            inc["resolved"] = True
            inc["agitated"] = False
            if prevent_vault_capture:
                inc["dispersed_unsealed"] = True
            inc["resolved_at_turn"] = turn_now

    db.update_session(session_id, extra={"daily_incursions": incursions, "daily_breaches": None})

    gold_gain = int(target_inc.get("reward_gold", 140) or 140)
    xp_gain = int(target_inc.get("reward_xp", 100) or 100)
    bp_inc = target_inc.get("anomaly_blueprint") if isinstance(target_inc.get("anomaly_blueprint"), dict) else {"name": target_inc["entity_name"], "type": target_inc.get("anomaly_type", "")}

    if prevent_vault_capture:
        gold_gain = int(round(gold_gain * 0.60))
        xp_gain = int(round(xp_gain * 0.60))
        if user_id:
            db.apply_hp_mp_delta(user_id, gold_delta=gold_gain)
            db.add_xp(user_id, xp_gain)
        if isinstance(bp_inc, dict) and (bp_inc.get("blueprint_id") or bp_inc.get("codex_id")):
            try:
                db.record_session_anomaly_field_log(session_id, bp_inc, stage="sighted", location=str(target_inc.get("location") or ""))
                if bp_inc.get("codex_id"):
                    db.record_folklore_codex_progress(
                        db.get_session_participant_user_ids(session_id) or ([user_id] if user_id else []),
                        str(bp_inc["codex_id"]),
                        stage="sighted",
                    )
            except Exception:
                pass
        return {
            "resolved": True,
            "dispersed_unsealed": True,
            "prevent_vault_capture": True,
            "reward_gold": gold_gain,
            "reward_xp": xp_gain,
            "reward_item": "",
            "vault_entry": None,
            "message": (
                f"💨 **Anomaly Breach Dispersed (Unsealed Tether):** Forced **{target_inc['entity_name']}** to scatter "
                f"(+{gold_gain}G, +{xp_gain} XP [60%]; seal its tether vessel next time for permanent Vault capture!)."
            ),
        }

    converted_res = handle_secured_object_anomaly_conversion(
        session_id=session_id,
        user_id=user_id,
        blueprint=bp_inc,
        scen_key=scen_key,
        entity_name=target_inc["entity_name"],
        skip_codex_progress=True,
    )
    dropped_gear = (converted_res["item"]["name"] if converted_res and converted_res.get("item") else "") or _roll_optional_incursion_gear_drop(user_id, scen_key)
    if user_id:
        db.apply_hp_mp_delta(user_id, gold_delta=gold_gain)
        db.add_xp(user_id, xp_gain)

    vault_entry = record_contained_anomaly_to_vault_log(
        session_id=session_id,
        entity_name=target_inc["entity_name"],
        category_tag=target_inc["category_tag"],
        subtype=target_inc["subtype"],
        location=target_inc["location"],
        containment_note=target_inc.get("containment_note", ""),
        resolution_method="Hostile Breach Eliminated & Contained",
        user_id=user_id,
        blueprint=bp_inc,
        incursion_id=eff_id,
    )
    gear_suffix = f" {converted_res['notice']}" if converted_res else (f" Salvaged **{dropped_gear}**!" if dropped_gear else "")
    return {
        "resolved": True,
        "converted_gear": converted_res,
        "reward_gold": gold_gain,
        "reward_xp": xp_gain,
        "reward_item": dropped_gear,
        "vault_entry": vault_entry,
        "message": (
            f"🌀 **Anomaly Breach Sealed!** Contained **{target_inc['entity_name']}** "
            f"(+{gold_gain}G, +{xp_gain} XP • Logged to {vault_entry['vault_facility']}).{gear_suffix}"
        ),
    }


resolve_non_hostile_breach_action = resolve_non_hostile_incursion_action
mark_hostile_breach_resolved_on_victory = mark_hostile_incursion_resolved_on_victory
