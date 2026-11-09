from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import db
import scenario_data
import skill_check
from game_engine.quest_agency import (
    acquire_quest_macguffin,
    build_fog_of_war_quest_payload,
    build_fog_of_war_quest_prompt_block,
    evaluate_schedule_curfew_and_coop_precedence,
    resolve_caseboard_deduction,
    resolve_quest_turn_in_or_betrayal,
    resolve_suspect_accusation,
)
from game_engine.quest_lifecycle import (
    complete_remediation_bounty_if_linked,
    evaluate_skipped_threatened_optionals,
    resolve_chapter_transition,
    seed_or_discover_dossier_clue,
)
from mechanics.narrative.blueprints import has_quest_note_flag
from mechanics.narrative.campaign_spine import (
    mutate_spine_on_lieutenant_fate,
    promote_escaped_boss_to_nemesis,
    update_campaign_ending_axes,
)
from mechanics.narrative.quest_engines import render_world_scar_spec
from mechanics.world.waypoints.choices import get_active_companion_for_waypoint
from mechanics.world.world_events.engine import spawn_quest_world_scar


def _normalize_target_key(waypoint_or_lead: Dict[str, Any]) -> str:
    raw = (
        waypoint_or_lead.get("lead_id")
        or waypoint_or_lead.get("target_npc")
        or waypoint_or_lead.get("stage_label")
        or waypoint_or_lead.get("title")
        or f"stage_{waypoint_or_lead.get('stage_index', 1)}"
    )
    return str(raw).strip().lower()


def is_approach_burned(
    session_id: int,
    quest_id: str,
    target_key: str,
    approach: str,
) -> bool:
    """Returns True if `approach` was permanently burned on `target_key` for this quest."""
    dossier = db.get_quest_dossier(session_id, quest_id)
    if not dossier:
        return False
    burned_map = dossier.get("burned_approaches") or {}
    norm_t = str(target_key or "").strip().lower()
    norm_a = str(approach or "").strip().upper()
    burned_list = [str(x).upper() for x in (burned_map.get(norm_t) or [])]
    return norm_a in burned_list


def unlock_hidden_quest_optional(
    session_id: int,
    quest_id: str = "",
    optional_id: str = "",
    trigger_source: str = "clue_found",
    turn_number: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Hybrid Discovery Unlocker:
    Reveals hidden (`is_discovered == False`) Optional objectives when triggered by
    Caseboard clues (`clue_found`), NPC dialogue (`npc_dialogue`), or SMS/Courier comms (`incoming_comms`),
    and synchronizes `quests.sub_objectives_json` and `quest_waypoints`.
    """
    if not session_id:
        return []
    sess = db.get_session(session_id) or {}
    eff_turn = int(turn_number if turn_number is not None else db.infer_session_turn(sess))
    trig_norm = str(trigger_source or "clue_found").strip().lower()

    if quest_id:
        d_single = db.get_quest_dossier(session_id, quest_id)
        dossiers = [d_single] if d_single else []
    else:
        dossiers = db.get_session_quest_dossiers(session_id, status_stage="compiled") or []

    unlocked_out: List[Dict[str, Any]] = []
    for dos in dossiers:
        if not dos:
            continue
        qid = str(dos.get("quest_id") or "")
        q_row = db.get_quest_by_id(session_id, qid)
        if q_row and str(q_row.get("status") or "Active") != "Active":
            continue
        prev_leads = [dict(l) for l in (dos.get("leads_graph") or [])]
        leads = [dict(l) for l in prev_leads]
        mutated = False

        for idx, ld in enumerate(leads):
            if not ld.get("is_optional"):
                continue
            if ld.get("is_discovered", True):
                continue
            if str(ld.get("status") or "active").lower() in ("failed", "locked_out", "completed"):
                continue

            if optional_id:
                cand_ids = {
                    str(ld.get("optional_id") or "").lower(),
                    str(ld.get("lead_id") or "").lower(),
                }
                if optional_id.strip().lower() not in cand_ids:
                    continue
            else:
                req_trig = str(ld.get("unlock_trigger") or "clue_found").strip().lower()
                if trig_norm not in ("any", "breakthrough") and req_trig not in ("any", trig_norm):
                    continue

            ld["is_discovered"] = True
            ld["discovered_via"] = trig_norm
            leads[idx] = ld
            mutated = True
            unlocked_out.append(
                {
                    "quest_id": qid,
                    "optional_id": ld.get("optional_id") or ld.get("lead_id"),
                    "sub_obj_id": ld.get("sub_obj_id"),
                    "role": ld.get("role") or "alternative",
                    "title": ld.get("title") or ld.get("label") or "",
                    "stakes_hint": ld.get("stakes_hint") or "",
                    "trigger_source": trig_norm,
                }
            )
            if not optional_id:
                break

        if mutated:
            db.append_dossier_state_event(session_id, qid, eff_turn, "leads_graph", prev_leads, leads)
            saved = db.upsert_quest_dossier(session_id, qid, leads_graph=leads)
            db.sync_quest_projection_from_dossier(session_id, qid, dossier=saved or dos)

    return unlocked_out


def resolve_quest_approach_failure(
    session_id: int,
    quest: Dict[str, Any],
    waypoint: Dict[str, Any],
    approach: str,
    check_result_tier: str,
    party_user_ids: List[int],
    sub_obj: Optional[Dict[str, Any]] = None,
    session: Optional[Dict[str, Any]] = None,
    turn_number: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Unified Quest Skill-Check Failure Resolver (Decision 15):
    - Preserves Stage 1 arrival immunity, `1x`/quest Companion Rescue Shield, and Anomalous containment branching.
    - For compiled `QuestDossier` quests: permanently burns ONLY `approach` on that target, marks `engaged_flag = 1`,
      and ticks `alert_level` (`+1` fail, `+2` crit fail) toward `max_alert`.
    - For legacy quests (`status_stage != 'compiled'`): preserves legacy 2-strike counter compatibility.
    """
    from db.quests import append_quest_note_flag_in_db
    from game_engine.quests import apply_quest_failure_consequences

    qid = str(quest.get("quest_id") or "")
    sub_obj_id = waypoint.get("sub_obj_id")
    stage_idx = int(waypoint.get("stage_index", 1) or 1)
    dossier = db.get_quest_dossier(session_id, qid) if qid else None
    is_compiled = bool(dossier and dossier.get("status_stage") == "compiled")

    all_wps = db.get_quest_waypoints(session_id, qid, sub_obj_id) or []
    if stage_idx <= 1 and len(all_wps) > 1 and (not is_compiled or waypoint.get("completion_trigger") == "arrival"):
        return None

    sess_eff = session if isinstance(session, dict) else (db.get_session(session_id) or {})
    eff_turn = int(turn_number if turn_number is not None else db.infer_session_turn(sess_eff))
    q_fresh = db.get_quest_by_id(session_id, qid) or quest
    q_notes = str(q_fresh.get("quest_notes") or quest.get("quest_notes") or "")

    shield_already_used = has_quest_note_flag(q_notes, "companion_shield_used") or bool(
        dossier and int(dossier.get("rescue_shield_used") or 0) >= 1
    )
    active_comp = get_active_companion_for_waypoint(session_id, waypoint)
    if active_comp and not shield_already_used:
        append_quest_note_flag_in_db(session_id, qid, "companion_shield_used", "1")
        if dossier:
            db.append_dossier_state_event(session_id, qid, eff_turn, "rescue_shield_used", 0, 1)
            db.upsert_quest_dossier(session_id, qid, rescue_shield_used=1)
        comp_name = active_comp.get("name") or "Your companion"
        return {
            "status": "companion_shield_absorbed",
            "shield_absorbed": True,
            "failed": False,
            "companion_name": comp_name,
            "strikes": int(q_fresh.get("strikes") or 0),
            "max_strikes": int(dossier.get("max_alert") if is_compiled and dossier else 2),
            "directive": (
                f"[COMPANION STRIKE SHIELD ACTIVATED]: {comp_name} intervened to deflect the complication! "
                f"Alert / strike count was NOT incremented."
            ),
        }

    scen_chk = str(sess_eff.get("scenario") or "fantasy")
    if scenario_data.is_anomalous_incursions_scenario(scen_chk):
        from mechanics.world.anomalous_events import (
            apply_non_hostile_strike_side_effects,
            extract_non_hostile_entity_name,
            get_non_hostile_entity_temperament,
            is_non_hostile_entity_containment_waypoint,
            prune_anomaly_from_scene_npcs,
            spawn_agitated_non_hostile_entity,
        )

        if is_non_hostile_entity_containment_waypoint(waypoint, all_wps=all_wps, sub_obj=sub_obj, quest=q_fresh):
            from mechanics.world.anomaly_engine import evaluate_taboo_interaction, parse_blueprint_from_notes

            ent_nm = extract_non_hostile_entity_name(q_fresh, sub_obj)
            temp = get_non_hostile_entity_temperament(seed_key=qid, quest_notes=q_notes)
            q_bp = parse_blueprint_from_notes(q_notes)
            lead_uid = party_user_ids[0] if party_user_ids else sess_eff.get("host_user_id")
            if str(approach or "").strip().lower() == "folklore_offering_rite" and lead_uid:
                try:
                    from mechanics.world.folklore_mechanics import consume_folklore_offering_item, find_matching_offering_in_inventory
                    off_fail_m = find_matching_offering_in_inventory(int(lead_uid), q_bp)
                    if off_fail_m:
                        consume_folklore_offering_item(int(lead_uid), off_fail_m["item_name"])
                except Exception:
                    pass
            taboo_res = evaluate_taboo_interaction(
                q_bp,
                action_label=approach,
                incursion_action=approach,
                stat_used="STR" if str(approach).lower() == "force" else "",
            )
            s_delta = 2 if (check_result_tier == "crit_fail" or taboo_res.get("violated")) else 1
            strike_res = db.increment_quest_strikes(session_id, qid, delta=s_delta)
            if not strike_res["failed"]:
                side_fx = {}
                if temp in ("mischievous", "spook"):
                    side_fx = apply_non_hostile_strike_side_effects(
                        session_id=session_id,
                        user_id=lead_uid,
                        entity_name=ent_nm,
                        temperament=temp,
                        is_final_strike=False,
                        seed_key=qid,
                        quest_id=qid,
                    )
                if temp in ("mischievous", "spook") and side_fx.get("directive"):
                    warn_dir = (
                        f"[NON-HOSTILE CONTAINMENT COMPLICATION - {strike_res['strikes']}/{strike_res['max_strikes']} STRIKES]: "
                        f"{side_fx['directive']}"
                    )
                else:
                    warn_dir = (
                        f"[NON-HOSTILE CONTAINMENT COMPLICATION - {strike_res['strikes']}/{strike_res['max_strikes']} STRIKES]: "
                        f"The containment attempt on '{ent_nm}' faltered! "
                        + (
                            f"Startled and skittish, one more failed check and '{ent_nm}' will escape!"
                            if temp == "timid"
                            else f"Territorial static arcs dangerously—one more failed check and '{ent_nm}' will turn hostile!"
                        )
                    )
                return {
                    "status": "strike_warning",
                    "temperament": temp,
                    "strikes": strike_res["strikes"],
                    "max_strikes": strike_res["max_strikes"],
                    "gold_stolen": int(side_fx.get("gold_stolen", 0) or 0),
                    "mp_drained": int(side_fx.get("mp_drained", 0) or 0),
                    "prank_dc_penalty": int(side_fx.get("prank_dc_penalty", 0) or 0),
                    "failed": False,
                    "directive": warn_dir,
                }
            if temp in ("timid", "mischievous", "spook"):
                side_fx_final = {}
                if temp in ("mischievous", "spook"):
                    side_fx_final = apply_non_hostile_strike_side_effects(
                        session_id=session_id,
                        user_id=lead_uid,
                        entity_name=ent_nm,
                        temperament=temp,
                        is_final_strike=True,
                        seed_key=qid,
                        quest_id=qid,
                    )
                _q_extra_names: list[str] = []
                if isinstance(q_bp, dict):
                    _q_disg_alias = str((q_bp.get("disguise_state") or {}).get("disguise_alias") or "").strip()
                    for _nm in (_q_disg_alias, str(q_bp.get("canonical_name") or "").strip(), str(q_bp.get("name") or "").strip()):
                        if _nm and _nm.lower() != str(ent_nm or "").strip().lower() and _nm not in _q_extra_names:
                            _q_extra_names.append(_nm)
                prune_anomaly_from_scene_npcs(
                    session_id,
                    ent_nm,
                    session=session if isinstance(session, dict) else sess_eff,
                    persist_db=True,
                    extra_names=_q_extra_names or None,
                )
                if not q_fresh.get("is_story_quest"):
                    fail_res = apply_quest_failure_consequences(
                        session_id, q_fresh, party_user_ids, reason="entity_escaped", session=sess_eff
                    )
                    fail_res.update({
                        "escaped": True,
                        "temperament": temp,
                        "strikes": strike_res["strikes"],
                        "max_strikes": strike_res["max_strikes"],
                        "gold_stolen": int(side_fx_final.get("gold_stolen", 0) or 0),
                        "total_escrowed_gold": int(side_fx_final.get("total_escrowed_gold", 0) or 0),
                        "mp_drained": int(side_fx_final.get("mp_drained", 0) or 0),
                        "status_applied": str(side_fx_final.get("status_applied") or ""),
                    })
                    promo_part = f" {fail_res['promotion_penalty_notice']}" if fail_res.get("promotion_penalty_notice") else ""
                    if temp in ("mischievous", "spook") and side_fx_final.get("directive"):
                        fail_res["directive"] = (
                            f"[NON-HOSTILE ENTITY ESCAPED — BOUNTY FAILED]: {side_fx_final['directive']} "
                            f"Quest '{q_fresh.get('title')}' has FAILED.{promo_part}"
                        )
                    else:
                        fail_res["directive"] = (
                            f"[NON-HOSTILE ENTITY ESCAPED — BOUNTY FAILED]: Startled by repeated failed containment attempts, "
                            f"'{ent_nm}' slipped through a spatial seam and vanished! Quest '{q_fresh.get('title')}' has FAILED.{promo_part}"
                        )
                    return fail_res
                now = time.time()
                with db.get_conn() as conn:
                    if sub_obj_id is not None:
                        conn.execute("UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=?", (now, session_id, qid, sub_obj_id))
                    else:
                        conn.execute("UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=?", (now, session_id, qid))
                if sub_obj:
                    sub_obj["completed"] = True
                    sub_obj["resolution_approach"] = "dire_cost"
                db.set_quest_resolution_approach(session_id, qid, "dire_cost")
                db.reset_quest_strikes(session_id, qid)
                if temp == "timid" and lead_uid:
                    db.apply_hp_mp_delta(int(lead_uid), hp_delta=-5)
                dire_dir = (
                    f"[MANDATORY DIRE COST — SPECIMEN ESCAPED]: {side_fx_final['directive']} "
                    f"Salvage residual telemetry to press '{q_fresh.get('title')}' forward (0 HP lost)."
                    if (temp in ("mischievous", "spook") and side_fx_final.get("directive"))
                    else (
                        f"[MANDATORY DIRE COST — SPECIMEN ESCAPED]: '{ent_nm}' bolted through a spatial tear, "
                        f"escaping live capture! Salvage residual telemetry to press '{q_fresh.get('title')}' forward."
                    )
                )
                return {
                    "status": "dire_cost",
                    "escaped": True,
                    "temperament": temp,
                    "gold_stolen": int(side_fx_final.get("gold_stolen", 0) or 0),
                    "total_escrowed_gold": int(side_fx_final.get("total_escrowed_gold", 0) or 0),
                    "mp_drained": int(side_fx_final.get("mp_drained", 0) or 0),
                    "status_applied": str(side_fx_final.get("status_applied") or ""),
                    "failed": False,
                    "directive": dire_dir,
                }
            db.reset_quest_strikes(session_id, qid)
            cur_loc_str = str(sess_eff.get("current_location") or waypoint.get("target_location") or "")
            enemy_obj = spawn_agitated_non_hostile_entity(
                session_id=session_id,
                entity_name=ent_nm,
                location=cur_loc_str,
                quest_id=qid,
                sub_obj_id=sub_obj_id,
                is_story_quest=bool(q_fresh.get("is_story_quest")),
                session=session,
            )
            return {
                "status": "agitated_combat",
                "agitated": True,
                "combat_started": True,
                "temperament": "volatile",
                "failed": False,
                "strikes": strike_res["strikes"],
                "max_strikes": strike_res["max_strikes"],
                "enemy": enemy_obj,
                "directive": (
                    f"[NON-HOSTILE ENTITY AGITATED INTO COMBAT]: Repeated failed containment attempts provoked '{ent_nm}' "
                    f"into lashing out! Pacify or subdue it alive—killing it destroys the specimen and fails the bounty."
                ),
            }

    if is_compiled and dossier is not None:
        is_crit = str(check_result_tier or "").lower() in ("crit_fail", "critical_failure")
        delta = 2 if is_crit else 1
        prev_alert = int(dossier.get("alert_level") or 0)
        max_alert = max(2, int(dossier.get("max_alert") or 4))
        new_alert = min(max_alert, prev_alert + delta)

        prev_engaged = int(dossier.get("engaged_flag") or 0)
        prev_burned = {k: list(v) for k, v in (dossier.get("burned_approaches") or {}).items()}
        new_burned = {k: list(v) for k, v in prev_burned.items()}

        target_key = _normalize_target_key(waypoint)
        norm_appr = str(approach or waypoint.get("stat") or "CHECK").strip().upper()
        cur_list = [str(x).upper() for x in (new_burned.get(target_key) or [])]
        if norm_appr not in cur_list:
            cur_list.append(norm_appr)
        new_burned[target_key] = cur_list

        prev_leads_f = [dict(l) for l in (dossier.get("leads_graph") or [])]
        new_leads_f = [dict(l) for l in prev_leads_f]
        wp_lead_id = str(waypoint.get("lead_id") or "").strip().lower()
        wp_opt_id = str(waypoint.get("optional_id") or "").strip().lower()
        wp_sub_id = int(sub_obj_id) if (sub_obj_id is not None and str(sub_obj_id).lstrip("-").isdigit()) else None

        matched_opt_idx: Optional[int] = None
        for idx_l, ld_cand in enumerate(new_leads_f):
            if wp_lead_id and str(ld_cand.get("lead_id") or "").strip().lower() == wp_lead_id:
                matched_opt_idx = idx_l
                break
            if wp_opt_id and str(ld_cand.get("optional_id") or "").strip().lower() == wp_opt_id:
                matched_opt_idx = idx_l
                break
            if wp_sub_id is not None and wp_sub_id >= 1 and int(ld_cand.get("sub_obj_id") or -1) == wp_sub_id:
                matched_opt_idx = idx_l
                break

        lead_match = new_leads_f[matched_opt_idx] if matched_opt_idx is not None else None
        lead_match_status = str((lead_match or {}).get("status") or "active").strip().lower()
        sub_obj_status = str((sub_obj or {}).get("status") or "active").strip().lower()
        is_optional_beat = bool(
            (
                (sub_obj and sub_obj.get("is_optional") and sub_obj_status not in ("failed", "completed", "locked_out", "bypassed"))
                or (waypoint.get("is_optional") and lead_match_status not in ("failed", "completed", "locked_out", "bypassed"))
                or (lead_match and lead_match.get("is_optional") and lead_match_status not in ("failed", "completed", "locked_out", "bypassed"))
            )
        )

        if is_optional_beat:
            prev_climax_f = dict(dossier.get("climax_spec") or {})
            new_climax_f = dict(prev_climax_f)
            failed_opt_id = wp_opt_id or wp_lead_id
            inner_circle_lost_name = ""

            if matched_opt_idx is not None and lead_match is not None:
                lead_upd = dict(lead_match)
                lead_upd["status"] = "failed"
                lead_upd["failed_approach"] = norm_appr
                failed_opt_id = str(lead_upd.get("optional_id") or lead_upd.get("lead_id") or failed_opt_id)
                if lead_upd.get("fair_jeopardy_on_screen_only") or lead_upd.get("is_inner_circle_rescue"):
                    ally_nm = str(lead_upd.get("target_npc") or lead_upd.get("implicated_ally_npc") or "").strip()
                    if ally_nm and q_fresh.get("is_story_quest"):
                        inner_circle_lost_name = ally_nm
                        update_campaign_ending_axes(
                            session_id,
                            turn_number=eff_turn,
                            collateral_delta=1,
                            inner_circle_loss=ally_nm,
                        )
                if lead_upd.get("encounter_roster") and not lead_upd.get("roster_cleared"):
                    reinf_list = list(new_climax_f.get("reinforcements") or [])
                    reinf_list.extend([dict(e) for e in lead_upd["encounter_roster"] if isinstance(e, dict)])
                    new_climax_f["reinforcements"] = reinf_list
                new_leads_f[matched_opt_idx] = lead_upd

            new_climax_f["alert_dc_bonus"] = int(new_climax_f.get("alert_dc_bonus") or 0) + delta
            if not scenario_data.is_non_combat_scenario(scen_chk) and not (lead_match and lead_match.get("encounter_roster")):
                reinf_list = list(new_climax_f.get("reinforcements") or [])
                reinf_list.append(
                    {
                        "name": "Alerted Guard Detail",
                        "tier_label": "Reinforcement",
                        "hp": 35,
                        "max_hp": 35,
                    }
                )
                new_climax_f["reinforcements"] = reinf_list

            # Anti-Softlock on `"secret"` Gates: if ALL viable discovery Optionals are now failed/locked_out,
            # force-unlock Main via an Enemy Counter-Ambush / Messy Trail!
            ambush_unlocked = False
            ambush_scar = None
            viable_opts = [
                l_chk
                for l_chk in new_leads_f
                if l_chk.get("is_optional")
                and str(l_chk.get("status") or "active").strip().lower() not in ("failed", "locked_out")
            ]
            if (
                str(new_climax_f.get("gate_type") or "open").strip().lower() == "secret"
                and not new_climax_f.get("is_unlocked")
                and len(viable_opts) == 0
            ):
                ambush_unlocked = True
                new_alert = max_alert
                new_climax_f["is_unlocked"] = True
                new_climax_f["ambush_unlocked"] = True
                venue_amb = str(new_climax_f.get("location") or sess_eff.get("current_location") or "District")
                ch_amb = int(db.get_session_chapter(session_id) or 1)
                scar_tier_amb = (
                    "peak"
                    if (q_fresh.get("is_story_quest") and ch_amb in (3, 6, 8, 9, 10))
                    else ("buildup" if q_fresh.get("is_story_quest") else "bounty")
                )
                ambush_scar = spawn_quest_world_scar(
                    session_id=session_id,
                    source_quest_id=f"{qid}_AMBUSH",
                    scar_spec=render_world_scar_spec(
                        engine=str(dossier.get("engine") or "MYSTERY_CASE"),
                        venue_name=venue_amb,
                    ),
                    location_name=venue_amb,
                    turn_number=eff_turn,
                    spawn_remediation_bounty=False,
                    scar_tier=scar_tier_amb,
                )
                db.unlock_climax_waypoint(
                    session_id,
                    qid,
                    str(new_climax_f.get("location") or ""),
                    str(new_climax_f.get("true_culprit") or ""),
                )

            if prev_engaged == 0:
                db.append_dossier_state_event(session_id, qid, eff_turn, "engaged_flag", 0, 1)
            db.append_dossier_state_event(session_id, qid, eff_turn, "burned_approaches", prev_burned, new_burned)
            db.append_dossier_state_event(session_id, qid, eff_turn, "alert_level", prev_alert, new_alert)
            db.append_dossier_state_event(session_id, qid, eff_turn, "leads_graph", prev_leads_f, new_leads_f)
            db.append_dossier_state_event(session_id, qid, eff_turn, "climax_spec", prev_climax_f, new_climax_f)

            saved_opt_dos = db.upsert_quest_dossier(
                session_id,
                qid,
                engaged_flag=1,
                burned_approaches=new_burned,
                alert_level=new_alert,
                leads_graph=new_leads_f,
                climax_spec=new_climax_f,
            )
            with db.get_conn() as conn:
                conn.execute(
                    "UPDATE quests SET strikes = ?, max_strikes = ?, updated_at = ? WHERE session_id = ? AND quest_id = ?",
                    (new_alert, max_alert, time.time(), session_id, qid),
                )
            db.sync_quest_projection_from_dossier(session_id, qid, dossier=saved_opt_dos)
            if sub_obj is not None:
                sub_obj["status"] = "failed"
                sub_obj["completed"] = False

            dir_msg = (
                f"[OPTIONAL BURNED & COUNTER-AMBUSH UNLOCKED]: All optional leads on '{q_fresh.get('title')}' collapsed—the enemy launched a counter-ambush, exposing the Main Objective under maximum alert!"
                if ambush_unlocked
                else (
                    f"[OPTIONAL OBJECTIVE BURNED & MAIN HARDENED]: Optional route '{waypoint.get('stage_label') or failed_opt_id}' failed and is closed! "
                    f"Main Objective remains Active with heightened opposition vigilance."
                )
            )
            return {
                "status": "secret_ambush_unlocked" if ambush_unlocked else "optional_burned_and_hardened",
                "failed": False,
                "optional_failed": True,
                "quest_status": "Active",
                "optional_id": failed_opt_id,
                "strikes": new_alert,
                "max_strikes": max_alert,
                "alert_level": new_alert,
                "max_alert": max_alert,
                "alert_dc_bonus": int(new_climax_f.get("alert_dc_bonus") or 0),
                "burned_approach": norm_appr,
                "burned_target": target_key,
                "ambush_unlocked": ambush_unlocked,
                "inner_circle_lost": inner_circle_lost_name,
                "world_scar": ambush_scar,
                "directive": dir_msg,
            }

        if prev_engaged == 0:
            db.append_dossier_state_event(session_id, qid, eff_turn, "engaged_flag", 0, 1)
        db.append_dossier_state_event(session_id, qid, eff_turn, "burned_approaches", prev_burned, new_burned)
        db.append_dossier_state_event(session_id, qid, eff_turn, "alert_level", prev_alert, new_alert)

        db.upsert_quest_dossier(
            session_id,
            qid,
            engaged_flag=1,
            burned_approaches=new_burned,
            alert_level=new_alert,
        )
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE quests SET strikes = ?, max_strikes = ?, updated_at = ? WHERE session_id = ? AND quest_id = ?",
                (new_alert, max_alert, time.time(), session_id, qid),
            )

        if new_alert < max_alert:
            return {
                "status": "strike_warning",
                "strikes": new_alert,
                "max_strikes": max_alert,
                "alert_level": new_alert,
                "max_alert": max_alert,
                "burned_approach": norm_appr,
                "burned_target": target_key,
                "failed": False,
                "directive": (
                    f"[APPROACH BURNED & ALERT ESCALATED ({new_alert}/{max_alert})]: The {norm_appr} approach on "
                    f"'{waypoint.get('target_npc') or waypoint.get('stage_label') or q_fresh.get('title')}' failed and is now burned! "
                    f"Alternative approaches remain open, but opposition vigilance has risen."
                ),
            }

        fam_tier = str(dossier.get("family_tier") or "bounty")
        eng = str(dossier.get("engine") or "MYSTERY_CASE")
        venue = str((dossier.get("climax_spec") or {}).get("location") or sess_eff.get("current_location") or "District")
        scar_spec = (
            ((dossier.get("outcomes_matrix") or {}).get("failure") or {}).get("world_scar")
            or render_world_scar_spec(engine=eng, venue_name=venue)
        )

        if not q_fresh.get("is_story_quest"):
            fail_res = apply_quest_failure_consequences(
                session_id, q_fresh, party_user_ids, reason="max_alert_triggered", session=sess_eff
            )
            scar_ev = spawn_quest_world_scar(
                session_id=session_id,
                source_quest_id=qid,
                scar_spec=scar_spec,
                location_name=venue,
                turn_number=eff_turn,
            )
            companion_scarred = False
            if fam_tier == "loyalty":
                companion_scarred = True
                append_quest_note_flag_in_db(session_id, qid, "companion_arc_scarred", "1")
                c_npc = str(q_fresh.get("client_npc") or "")
                if c_npc:
                    try:
                        db.update_relationship_score(session_id, c_npc, delta_score=-30)
                    except Exception:
                        pass
            db.append_dossier_state_event(session_id, qid, eff_turn, "quest_status", "Active", "Failed")
            db.append_dossier_state_event(session_id, qid, eff_turn, "outcome_tier", dossier.get("outcome_tier", ""), "failure")
            db.upsert_quest_dossier(session_id, qid, outcome_tier="failure")
            fail_res.update(
                {
                    "strikes": new_alert,
                    "max_strikes": max_alert,
                    "alert_level": new_alert,
                    "max_alert": max_alert,
                    "burned_approach": norm_appr,
                    "world_scar": scar_ev,
                    "companion_arc_scarred": companion_scarred,
                }
            )
            return fail_res

        ch_num_sc = int(db.get_session_chapter(session_id) or 1)
        scar_tier_st = "peak" if ch_num_sc in (3, 6, 8, 9, 10) else "buildup"
        scar_ev = spawn_quest_world_scar(
            session_id=session_id,
            source_quest_id=qid,
            scar_spec=scar_spec,
            location_name=venue,
            turn_number=eff_turn,
            scar_tier=scar_tier_st,
        )
        now = time.time()
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=?",
                (now, session_id, qid, sub_obj_id),
            )
        if sub_obj:
            sub_obj["completed"] = True
            sub_obj["resolution_approach"] = "dire_cost"
        db.set_quest_resolution_approach(session_id, qid, "dire_cost")
        db.upsert_quest_dossier(session_id, qid, alert_level=0)
        db.reset_quest_strikes(session_id, qid)
        lead_uid = party_user_ids[0] if party_user_ids else 1
        db.apply_hp_mp_delta(lead_uid, hp_delta=-5)
        return {
            "status": "dire_cost",
            "failed": False,
            "burned_approach": norm_appr,
            "world_scar": scar_ev,
            "directive": (
                f"[MANDATORY PYRRHIC BREAKTHROUGH / WORLD SCAR]: Alert peaked on '{q_fresh.get('title')}'! "
                f"The objective was forced forward at a dire cost, leaving persistent regional fallout ('{scar_ev.get('title', 'Fallout')}')."
            ),
        }

    delta = 2 if (str(check_result_tier or "").lower() in ("crit_fail", "critical_failure") and stage_idx >= 3) else 1
    strike_res = db.increment_quest_strikes(session_id, qid, delta=delta)
    if not strike_res["failed"]:
        return {
            "status": "strike_warning",
            "strikes": strike_res["strikes"],
            "max_strikes": strike_res["max_strikes"],
            "failed": False,
            "directive": (
                f"[QUEST COMPLICATION - {strike_res['strikes']}/{strike_res['max_strikes']} STRIKES]: "
                f"The player failed a check on '{quest.get('title')}'. One more failure will botch the contract."
            ),
        }

    if not quest.get("is_story_quest"):
        fail_res = apply_quest_failure_consequences(session_id, quest, party_user_ids, reason="failed_strikes", session=session)
        fail_res["strikes"] = strike_res["strikes"]
        fail_res["max_strikes"] = strike_res["max_strikes"]
        return fail_res

    now = time.time()
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=?",
            (now, session_id, qid, sub_obj_id),
        )
    if sub_obj:
        sub_obj["completed"] = True
        sub_obj["resolution_approach"] = "dire_cost"
    db.reset_quest_strikes(session_id, qid)
    lead_uid = party_user_ids[0] if party_user_ids else 1
    db.apply_hp_mp_delta(lead_uid, hp_delta=-5)
    return {
        "status": "dire_cost",
        "failed": False,
        "directive": (
            f"[MANDATORY PYRRHIC BREAKTHROUGH / DIRE COST]: The sub-objective for '{quest.get('title')}' "
            f"was forced through at a dire cost! Narrate the narrow escape and physical/social toll."
        ),
    }


def resolve_quest_optional_objective(
    session_id: int,
    quest_id: str,
    optional_id: str = "",
    sub_obj_id: Optional[int] = None,
    approach: str = "PER",
    succeeded: bool = True,
    check_result_tier: str = "success",
    user_id: Optional[int] = None,
    party_user_ids: Optional[List[int]] = None,
    turn_number: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Typed `1`-Beat Optional Objective Resolver (`aid` | `bypass` | `alternative` | `threatened`):
    - Idempotent Field Bonus award (`bonus_claimed` guard).
    - `aid`: lowers Main DC (`aid_dc_reduction += 2`), strips `reinforcements` & `rush_un_nerfed_buffs`,
      attaches allied striker, and records faction aid (while keeping rival `alternative` open!).
    - `bypass`: marks Main Stage 1 `status='bypassed'` (`completed=True`) and promotes Stage 2.
    - `threatened`: averts crisis fallout (`saved_from_threat=True`, `+10` ally affinity).
    - `alternative`: resolves & closes the Main Objective via rival faction pact / Lieutenant turn / `1.5x` counter-offer;
      triggers **Eleventh-Hour Double-Cross** (`-25` betrayed faction Rep + ambush) if opposing `aid` was already claimed;
      locks out ONLY when physically impossible (`status == 'locked_out'`).
    """
    dossier = db.get_quest_dossier(session_id, quest_id)
    q_row = db.get_quest_by_id(session_id, quest_id)
    if not dossier or not q_row:
        return {"success": False, "reason": "Quest or dossier not found."}

    sess = db.get_session(session_id) or {}
    eff_turn = int(turn_number if turn_number is not None else db.infer_session_turn(sess))
    uids = list(
        party_user_ids
        or ([int(user_id)] if user_id else [])
        or (db.get_session_members(session_id) or [])
    )
    prev_leads = [dict(l) for l in (dossier.get("leads_graph") or [])]
    leads = [dict(l) for l in prev_leads]
    prev_climax = dict(dossier.get("climax_spec") or {})
    climax = dict(prev_climax)
    econ = dict(dossier.get("contract_economy") or {})

    opt_low = str(optional_id or "").strip().lower()
    target_idx: Optional[int] = None
    for idx, ld in enumerate(leads):
        if opt_low and opt_low in {
            str(ld.get("optional_id") or "").strip().lower(),
            str(ld.get("lead_id") or "").strip().lower(),
        }:
            target_idx = idx
            break
        if sub_obj_id is not None and int(ld.get("sub_obj_id") or -1) == int(sub_obj_id):
            target_idx = idx
            break
    if target_idx is None:
        target_idx = next(
            (i for i, l in enumerate(leads) if l.get("is_optional") and str(l.get("status") or "active") == "active"),
            None,
        )
    if target_idx is None:
        return {"success": False, "reason": "No matching optional objective found."}

    lead = dict(leads[target_idx])
    cur_status = str(lead.get("status") or "active").strip().lower()
    t_key = _normalize_target_key(lead)
    norm_appr = str(approach or "PER").strip().upper()
    if cur_status == "locked_out":
        return {
            "success": False,
            "blocked": True,
            "reason": str(lead.get("lockout_reason") or "optional_locked_out"),
            "message": "This optional route is no longer physically possible.",
        }
    if is_approach_burned(session_id, quest_id, t_key, norm_appr):
        return {
            "success": False,
            "blocked": True,
            "reason": "approach_burned",
            "message": f"Approach '{norm_appr}' is permanently burned on this optional objective.",
        }
    if cur_status == "failed":
        return {
            "success": False,
            "blocked": True,
            "reason": "optional_failed",
            "message": "This optional route already failed and is closed.",
        }
    if cur_status == "completed" and lead.get("bonus_claimed") and succeeded:
        return {
            "success": True,
            "idempotent_replay": True,
            "lead_id": lead.get("lead_id"),
            "optional_id": lead.get("optional_id") or lead.get("lead_id"),
            "role": lead.get("role") or "aid",
            "lead_status": "completed",
            "status": "completed",
            "field_bonus_awarded": {"xp": 0, "gold": 0, "affinity": 0},
            "quest_status": str(q_row.get("status") or "Active"),
            "climax_unlocked": bool(climax.get("is_unlocked")),
            "dossier": dossier,
        }

    if norm_appr == "BRIBE" and user_id:
        appr_obj = next(
            (a for a in (lead.get("approaches") or []) if str(a.get("approach_id") or "").lower() == "bribe"),
            None,
        )
        cost = int((appr_obj or {}).get("gold_cost") or 20)
        char = db.get_character(int(user_id)) or {}
        if int(char.get("gold") or 0) < cost:
            return {"success": False, "blocked": True, "reason": "insufficient_gold", "required_gold": cost}
        db.apply_hp_mp_delta(int(user_id), gold_delta=-cost)
        econ["bribes_spent_gold"] = int(econ.get("bribes_spent_gold") or 0) + cost

    if not succeeded:
        fail_out = resolve_quest_approach_failure(
            session_id=session_id,
            quest=q_row,
            waypoint={
                "lead_id": lead.get("lead_id"),
                "optional_id": lead.get("optional_id"),
                "sub_obj_id": lead.get("sub_obj_id", target_idx + 1),
                "is_optional": True,
                "stage_index": 1,
                "target_npc": lead.get("target_npc"),
                "stage_label": lead.get("title"),
            },
            approach=norm_appr,
            check_result_tier=check_result_tier or "failure",
            party_user_ids=uids,
            session=sess,
            turn_number=eff_turn,
        )
        return {"success": False, "check_failed": True, "failure_outcome": fail_out}

    role = str(lead.get("role") or "aid").strip().lower()
    lead["is_discovered"] = True
    lead["roster_scouted"] = True
    lead["roster_cleared"] = True
    lead["status"] = "completed"
    lead["resolved_approach"] = norm_appr

    # Idempotent Field Bonus Award
    fb_awarded = {"xp": 0, "gold": 0, "affinity": 0}
    if not lead.get("bonus_claimed"):
        fb_spec = dict(lead.get("field_bonus") or {})
        fb_xp = int(fb_spec.get("xp") or 25)
        fb_gold = int(fb_spec.get("gold") or 0)
        fb_aff = int(fb_spec.get("affinity") or 0)
        for uid in uids:
            if fb_xp > 0:
                db.add_xp(int(uid), fb_xp)
            if fb_gold > 0:
                db.apply_hp_mp_delta(int(uid), gold_delta=fb_gold)
        if fb_aff > 0 and lead.get("target_npc"):
            try:
                db.update_relationship_score(session_id, str(lead["target_npc"]), delta_score=fb_aff)
            except Exception:
                pass
        lead["bonus_claimed"] = True
        fb_awarded = {"xp": fb_xp, "gold": fb_gold, "affinity": fb_aff}

    discovered_clue = seed_or_discover_dossier_clue(
        session_id=session_id,
        quest_id=quest_id,
        clue_index=min(target_idx, 1),
        source_location=str(lead.get("target_location") or ""),
    )

    q_notes_rec = str(q_row.get("quest_notes") or "")
    if "anomaly_bp:" in q_notes_rec or "anomaly_blueprint:" in q_notes_rec:
        try:
            from mechanics.world.anomalous_events import reveal_anomaly_dossier
            reveal_anomaly_dossier(session_id, quest_id=quest_id)
        except Exception:
            pass

    if str(climax.get("gate_type") or "open").lower() == "secret":
        climax["is_unlocked"] = True
        db.unlock_climax_waypoint(
            session_id,
            quest_id,
            str(climax.get("location") or ""),
            str(climax.get("true_culprit") or ""),
        )

    double_crossed = False
    betrayed_faction = ""
    main_stages = [dict(ms) for ms in (climax.get("main_stages") or [])]

    if role == "aid":
        climax["aid_dc_reduction"] = int(climax.get("aid_dc_reduction") or 0) + 2
        climax["reinforcements"] = []
        climax["rush_un_nerfed_buffs"] = {}
        if lead.get("target_npc") and not climax.get("aid_ally_striker"):
            climax["aid_ally_striker"] = str(lead["target_npc"])
        aid_slug = str(lead.get("rival_faction_slug") or "order_faction").strip()
        claimed_factions = list(climax.get("claimed_aid_factions") or [])
        if aid_slug and aid_slug not in claimed_factions:
            claimed_factions.append(aid_slug)
        climax["claimed_aid_factions"] = claimed_factions

    elif role == "bypass":
        climax["bypass_unlocked"] = True
        if main_stages:
            if str(main_stages[0].get("status") or "active") not in ("completed", "bypassed"):
                main_stages[0]["status"] = "bypassed"
                main_stages[0]["completed"] = True
            if len(main_stages) >= 2 and str(main_stages[1].get("status") or "locked") == "locked":
                main_stages[1]["status"] = "active"
            final_approaches = list(main_stages[-1].get("approaches") or [])
            if not any(str(a.get("approach_id") or "") == "bypass_route" for a in final_approaches):
                final_approaches.append(
                    {
                        "approach_id": "bypass_route",
                        "stat": "AGI",
                        "label": "[Bypass] Exploit the secured shortcut route",
                        "gold_cost": 0,
                        "after_hours_pivot": False,
                    }
                )
                main_stages[-1]["approaches"] = final_approaches
            climax["main_stages"] = main_stages

    elif role == "threatened":
        lead["saved_from_threat"] = True
        if lead.get("target_npc"):
            try:
                db.update_relationship_score(session_id, str(lead["target_npc"]), delta_score=10)
            except Exception:
                pass

    elif role == "alternative":
        climax["is_unlocked"] = True
        climax["completed"] = True
        climax["resolved_via_alternative"] = str(lead.get("optional_id") or lead.get("lead_id") or "")
        for ms in main_stages:
            ms["status"] = "completed"
            ms["completed"] = True
        if main_stages:
            climax["main_stages"] = main_stages

        prior_aid_claimed = bool(climax.get("claimed_aid_factions")) or any(
            i != target_idx
            and str(l_other.get("role") or "").lower() == "aid"
            and str(l_other.get("status") or "").lower() == "completed"
            for i, l_other in enumerate(leads)
        )
        rival_slug = str(lead.get("rival_faction_slug") or "").strip()
        if prior_aid_claimed:
            double_crossed = True
            all_betrayed_slugs: List[str] = []
            if lead.get("opposing_faction_slug"):
                all_betrayed_slugs.append(str(lead["opposing_faction_slug"]).strip())
            for f_slug in (climax.get("claimed_aid_factions") or []):
                s_str = str(f_slug).strip()
                if s_str and s_str not in all_betrayed_slugs and s_str != rival_slug:
                    all_betrayed_slugs.append(s_str)
            if not all_betrayed_slugs:
                all_betrayed_slugs.append("order_faction")

            betrayed_names: List[str] = []
            for b_slug in all_betrayed_slugs:
                existing_bet = db.get_faction(session_id, b_slug) if b_slug else None
                if existing_bet and existing_bet.get("name"):
                    b_name = str(existing_bet["name"])
                    db.upsert_faction(session_id, b_name, delta_score=-25)
                    betrayed_names.append(b_name)
            betrayed_faction = ", ".join(betrayed_names) if betrayed_names else "Coalition"

            if rival_slug:
                ex_riv = db.get_faction(session_id, rival_slug)
                riv_name = str(ex_riv["name"]) if ex_riv and ex_riv.get("name") else rival_slug.replace("_", " ").title()
                db.upsert_faction(session_id, riv_name, delta_score=15)
            db.update_session(
                session_id,
                extra={
                    "pending_retaliation": {
                        "quest_id": quest_id,
                        "quest_title": q_row.get("title", "Contract"),
                        "enemy_name": f"Betrayed {betrayed_faction or 'Coalition'} Strike Team",
                        "origin_location": str(sess.get("current_location") or ""),
                        "double_cross": True,
                    }
                },
            )
            for p_npc in (db.get_session_party_npcs(session_id) or []):
                p_fac = str(p_npc.get("faction") or p_npc.get("affiliation") or "").lower()
                for b_s, b_n in zip(all_betrayed_slugs, betrayed_names):
                    if (b_s and b_s.lower() in p_fac) or (b_n and b_n.lower() in p_fac):
                        try:
                            db.update_relationship_score(session_id, str(p_npc["name"]), delta_score=-15)
                        except Exception:
                            pass
                        break
            if q_row.get("is_story_quest"):
                cur_ch_dc = int(db.get_session_chapter(session_id) or 1)
                update_campaign_ending_axes(
                    session_id,
                    turn_number=eff_turn,
                    faction_pillar="shadow",
                    double_cross_delta=1,
                    usurper_delta=1 if cur_ch_dc >= 6 else 0,
                )
        else:
            if rival_slug:
                ex_riv = db.get_faction(session_id, rival_slug)
                riv_name = str(ex_riv["name"]) if ex_riv and ex_riv.get("name") else rival_slug.replace("_", " ").title()
                db.upsert_faction(session_id, riv_name, delta_score=15)
            if q_row.get("is_story_quest"):
                update_campaign_ending_axes(
                    session_id,
                    turn_number=eff_turn,
                    faction_pillar="reform",
                )

        if lead.get("target_npc"):
            lt_mut = mutate_spine_on_lieutenant_fate(
                session_id=session_id,
                npc_name=str(lead["target_npc"]),
                fate="recruited",
                turn_number=eff_turn,
            )
            if lt_mut and q_row.get("is_story_quest"):
                update_campaign_ending_axes(
                    session_id,
                    turn_number=eff_turn,
                    recruited_lieutenant=str(lead["target_npc"]),
                )

    leads[target_idx] = lead
    db.append_dossier_state_event(session_id, quest_id, eff_turn, "leads_graph", prev_leads, leads)
    db.append_dossier_state_event(session_id, quest_id, eff_turn, "climax_spec", prev_climax, climax)
    if int(dossier.get("engaged_flag") or 0) == 0:
        db.append_dossier_state_event(session_id, quest_id, eff_turn, "engaged_flag", 0, 1)

    if role == "alternative":
        base_gold = int(econ.get("base_gold") or q_row.get("reward_gold") or 50)
        adv_paid = int(econ.get("upfront_advance_gold") or 0) if econ.get("advance_taken") else 0
        gold_mult = 1.0 if q_row.get("is_story_quest") else 1.5
        final_gold = max(0, int(round(base_gold * gold_mult)) - adv_paid)
        final_xp = int(q_row.get("reward_xp") or 100)
        if scenario_data.is_anomalous_incursions_scenario(str(sess.get("scenario") or "")) and uids:
            try:
                res_tax = db.persist_anomalous_quest_containment(session_id, q_row, int(uids[0]), party_user_ids=uids)
                if res_tax.get("confiscate_gold"):
                    final_gold = 0
            except Exception:
                pass

        with db.get_conn() as conn:
            conn.execute(
                "UPDATE quests SET status='Completed', reward_claimed=1, updated_at=? WHERE session_id=? AND quest_id=?",
                (time.time(), session_id, quest_id),
            )
        for uid in uids:
            db.apply_hp_mp_delta(int(uid), gold_delta=final_gold)
            db.add_xp(int(uid), final_xp)

        db.append_dossier_state_event(session_id, quest_id, eff_turn, "quest_status", str(q_row.get("status") or "Active"), "Completed")
        db.append_dossier_state_event(session_id, quest_id, eff_turn, "outcome_tier", str(dossier.get("outcome_tier") or ""), "alternative_deal")
        updated_alt = db.upsert_quest_dossier(
            session_id,
            quest_id,
            engaged_flag=1,
            leads_graph=leads,
            climax_spec=climax,
            contract_economy=econ,
            outcome_tier="alternative_deal",
        )
        db.sync_quest_projection_from_dossier(session_id, quest_id, dossier=updated_alt)
        lifted_scars = complete_remediation_bounty_if_linked(session_id, quest_id, turn_number=eff_turn)
        threat_fallout = (
            []
            if q_row.get("is_story_quest")
            else evaluate_skipped_threatened_optionals(session_id, quest_id, dossier=updated_alt, turn_number=eff_turn)
        )
        ch_res = (
            resolve_chapter_transition(session_id=session_id, quest=q_row, status="Completed", party_user_ids=uids)
            if q_row.get("is_story_quest")
            else None
        )
        return {
            "success": True,
            "lead_id": lead.get("lead_id"),
            "optional_id": lead.get("optional_id") or lead.get("lead_id"),
            "role": "alternative",
            "lead_status": "completed",
            "status": "completed",
            "quest_status": "Completed",
            "outcome_tier": "alternative_deal",
            "double_crossed": double_crossed,
            "betrayed_faction": betrayed_faction,
            "gold_awarded": final_gold,
            "xp_awarded": final_xp,
            "field_bonus_awarded": fb_awarded,
            "roster_scouted": True,
            "roster_cleared": True,
            "climax_unlocked": True,
            "discovered_clue": discovered_clue,
            "lifted_world_scars": lifted_scars,
            "skipped_threatened_fallout": threat_fallout,
            "chapter_transition": ch_res,
            "dossier": updated_alt,
        }

    updated = db.upsert_quest_dossier(
        session_id,
        quest_id,
        engaged_flag=1,
        leads_graph=leads,
        climax_spec=climax,
        contract_economy=econ,
    )
    db.sync_quest_projection_from_dossier(session_id, quest_id, dossier=updated)
    return {
        "success": True,
        "lead_id": lead.get("lead_id"),
        "optional_id": lead.get("optional_id") or lead.get("lead_id"),
        "role": role,
        "lead_status": "completed",
        "status": "completed",
        "quest_status": str(q_row.get("status") or "Active"),
        "field_bonus_awarded": fb_awarded,
        "aid_dc_reduction": int(climax.get("aid_dc_reduction") or 0),
        "bypass_unlocked": bool(climax.get("bypass_unlocked")),
        "roster_scouted": True,
        "roster_cleared": True,
        "climax_unlocked": bool(climax.get("is_unlocked")),
        "discovered_clue": discovered_clue,
        "dossier": updated,
    }


def evaluate_nonlinear_leads_and_climax_gate(
    session_id: int,
    quest_id: str,
    lead_id: str = "",
    approach: str = "PER",
    succeeded: bool = True,
    is_scout_only: bool = False,
    rush_climax: bool = False,
    user_id: Optional[int] = None,
    turn_number: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Non-Linear Lead / Optional Graph & Climax Sequence-Break Evaluator (Decisions 7 & 9):
    - Optionals & leads can be completed in ANY order via any unburned approach (`STR`/`PER`/`CHA`/`INT`/`AGI`/`BRIBE`/`ITEM`).
    - Scouting (`is_scout_only=True`) reveals `encounter_roster` (`roster_scouted = True`).
    - Typed Optionals (`is_optional == True`) delegate to `resolve_quest_optional_objective`.
    - Open-gate climaxes (`gate_type == 'open'`) can be rushed directly on Turn 1.
    - Secret-gate climaxes (`gate_type == 'secret'`) block direct rush until a discovery optional or Caseboard deduction unlocks it.
    """
    dossier = db.get_quest_dossier(session_id, quest_id)
    if not dossier:
        return {"success": False, "reason": "Quest dossier not found."}

    sess = db.get_session(session_id) or {}
    eff_turn = int(turn_number if turn_number is not None else db.infer_session_turn(sess))
    prev_leads = [dict(l) for l in (dossier.get("leads_graph") or [])]
    leads = [dict(l) for l in prev_leads]
    prev_climax = dict(dossier.get("climax_spec") or {})
    climax = dict(prev_climax)
    econ = dict(dossier.get("contract_economy") or {})

    if rush_climax:
        gate_type = str(climax.get("gate_type") or "open")
        if gate_type == "secret" and not climax.get("is_unlocked"):
            return {
                "success": False,
                "allowed": False,
                "gate_type": "secret",
                "reason": "Climax location or true culprit remains hidden—uncover a lead or pair Caseboard clues first.",
            }

        cascaded_enemies: List[Dict[str, Any]] = list(climax.get("reinforcements") or [])
        bypassed_ids: List[str] = []
        for ld in leads:
            if ld.get("status") == "active":
                if ld.get("is_optional") and str(ld.get("role") or "").lower() in ("threatened", "alternative"):
                    # Keep `threatened` evaluable on completion and rival `alternative` open for 11th-hour Double-Cross!
                    continue
                ld["status"] = "bypassed"
                bypassed_ids.append(str(ld.get("lead_id") or ""))
                if ld.get("encounter_roster") and not ld.get("roster_cleared"):
                    cascaded_enemies.extend(list(ld["encounter_roster"]))

        climax["is_unlocked"] = True
        climax["reinforcements"] = cascaded_enemies
        if bypassed_ids and climax.get("boss_sheet") and climax.get("rush_un_nerfed_buffs"):
            boss = dict(climax["boss_sheet"])
            bonus_dt = int((climax["rush_un_nerfed_buffs"] or {}).get("bonus_dt") or 4)
            boss["dt"] = int(boss.get("dt") or 2) + bonus_dt
            boss["max_hp"] = int(round(int(boss.get("max_hp") or 120) * 1.15))
            boss["hp"] = boss["max_hp"]
            boss["rushed_un_nerfed"] = True
            climax["boss_sheet"] = boss

        db.append_dossier_state_event(session_id, quest_id, eff_turn, "leads_graph", prev_leads, leads)
        db.append_dossier_state_event(session_id, quest_id, eff_turn, "climax_spec", prev_climax, climax)
        if int(dossier.get("engaged_flag") or 0) == 0:
            db.append_dossier_state_event(session_id, quest_id, eff_turn, "engaged_flag", 0, 1)
        updated = db.upsert_quest_dossier(
            session_id,
            quest_id,
            engaged_flag=1,
            leads_graph=leads,
            climax_spec=climax,
        )
        if climax.get("main_stages") or any(l.get("is_optional") for l in leads):
            db.sync_quest_projection_from_dossier(session_id, quest_id, dossier=updated)
        return {
            "success": True,
            "allowed": True,
            "rushed": len(bypassed_ids) > 0,
            "bypassed_leads": bypassed_ids,
            "reinforcements_count": len(cascaded_enemies),
            "dossier": updated,
        }

    target_lead_idx = next(
        (
            i
            for i, l in enumerate(leads)
            if lead_id
            and lead_id.lower() in {str(l.get("lead_id") or "").lower(), str(l.get("optional_id") or "").lower()}
        ),
        next((i for i, l in enumerate(leads) if l.get("status") == "active"), None),
    )
    if target_lead_idx is None:
        return {"success": False, "reason": "No active lead matched."}

    lead = dict(leads[target_lead_idx])
    if lead.get("is_optional") and not is_scout_only:
        return resolve_quest_optional_objective(
            session_id=session_id,
            quest_id=quest_id,
            optional_id=str(lead.get("optional_id") or lead.get("lead_id") or lead_id),
            sub_obj_id=lead.get("sub_obj_id"),
            approach=approach,
            succeeded=succeeded,
            check_result_tier="success" if succeeded else "failure",
            user_id=user_id,
            turn_number=eff_turn,
        )

    t_key = _normalize_target_key(lead)
    norm_appr = str(approach or "PER").strip().upper()
    if is_approach_burned(session_id, quest_id, t_key, norm_appr):
        return {
            "success": False,
            "blocked": True,
            "reason": "approach_burned",
            "message": f"Approach '{norm_appr}' is permanently burned on this lead—choose a different tactic.",
        }

    if norm_appr == "BRIBE" and user_id:
        appr_obj = next((a for a in (lead.get("approaches") or []) if str(a.get("approach_id") or "").lower() == "bribe"), None)
        cost = int((appr_obj or {}).get("gold_cost") or 20)
        char = db.get_character(int(user_id)) or {}
        if int(char.get("gold") or 0) < cost:
            return {"success": False, "blocked": True, "reason": "insufficient_gold", "required_gold": cost}
        db.apply_hp_mp_delta(int(user_id), gold_delta=-cost)
        econ["bribes_spent_gold"] = int(econ.get("bribes_spent_gold") or 0) + cost

    if not succeeded:
        q_row = db.get_quest_by_id(session_id, quest_id) or {"quest_id": quest_id, "title": quest_id}
        fail_out = resolve_quest_approach_failure(
            session_id=session_id,
            quest=q_row,
            waypoint={"lead_id": lead.get("lead_id"), "stage_index": 2, "target_npc": lead.get("target_npc"), "stage_label": lead.get("title")},
            approach=norm_appr,
            check_result_tier="failure",
            party_user_ids=[int(user_id)] if user_id else [],
            session=sess,
            turn_number=eff_turn,
        )
        return {"success": False, "check_failed": True, "failure_outcome": fail_out}

    discovered_clue = None
    min_req_lead_out = int(climax.get("min_leads_required") or 2)
    lead["roster_scouted"] = True
    if not is_scout_only:
        lead["roster_cleared"] = True
        lead["status"] = "completed"
        lead["resolved_approach"] = norm_appr
        discovered_clue = seed_or_discover_dossier_clue(
            session_id=session_id,
            quest_id=quest_id,
            clue_index=min(target_lead_idx, 1),
            source_location=str(lead.get("target_location") or ""),
        )
        has_folklore_rec = False
        q_row_rec = db.get_quest_by_id(session_id, quest_id) or {}
        q_notes_rec = str(q_row_rec.get("quest_notes") or "")
        if "anomaly_bp:" in q_notes_rec or "anomaly_blueprint:" in q_notes_rec:
            try:
                from mechanics.world.anomalous_events import reveal_anomaly_dossier
                from mechanics.world.anomaly_engine import parse_blueprint_from_notes
                bp_lead = parse_blueprint_from_notes(q_notes_rec)
                if bp_lead and bp_lead.get("codex_id"):
                    has_folklore_rec = db.user_has_folklore_recognition(
                        db.get_session_participant_user_ids(session_id),
                        str(bp_lead["codex_id"]),
                        session_id=session_id,
                    )
                reveal_anomaly_dossier(session_id, quest_id=quest_id)
            except Exception:
                pass
        gate_str = str(climax.get("gate_type") or climax.get("unlock_gate") or "").lower()
        completed_after = sum(
            1 for idx_l, l_item in enumerate(leads)
            if idx_l == target_lead_idx or l_item.get("status") == "completed" or l_item.get("roster_cleared")
        )
        min_req_lead = int(climax.get("min_leads_required") or 2)
        if has_folklore_rec:
            min_req_lead = max(1, min_req_lead - 1)
        min_req_lead_out = min_req_lead
        if "secret" in gate_str or completed_after >= min_req_lead:
            climax["is_unlocked"] = True
            db.unlock_climax_waypoint(
                session_id,
                quest_id,
                str(climax.get("location") or ""),
                str(climax.get("true_culprit") or ""),
            )

    leads[target_lead_idx] = lead
    db.append_dossier_state_event(session_id, quest_id, eff_turn, "leads_graph", prev_leads, leads)
    db.append_dossier_state_event(session_id, quest_id, eff_turn, "climax_spec", prev_climax, climax)
    if int(dossier.get("engaged_flag") or 0) == 0:
        db.append_dossier_state_event(session_id, quest_id, eff_turn, "engaged_flag", 0, 1)

    updated = db.upsert_quest_dossier(
        session_id,
        quest_id,
        engaged_flag=1,
        leads_graph=leads,
        climax_spec=climax,
        contract_economy=econ,
    )
    return {
        "success": True,
        "lead_id": lead.get("lead_id"),
        "lead_status": lead.get("status"),
        "roster_scouted": bool(lead.get("roster_scouted")),
        "roster_cleared": bool(lead.get("roster_cleared")),
        "required_leads": min_req_lead_out,
        "climax_unlocked": bool(climax.get("is_unlocked")),
        "discovered_clue": discovered_clue,
        "dossier": updated,
    }


def resolve_quest_combat_outcome(
    session_id: int,
    quest_id: str,
    is_climax_boss: bool = False,
    party_wiped: bool = False,
    fled_battle: bool = False,
    surviving_enemies: Optional[List[Dict[str, Any]]] = None,
    surrendered_enemies: Optional[List[Any]] = None,
    fled_enemies: Optional[List[Any]] = None,
    surrender_choice: str = "capture_alive",
    party_user_ids: Optional[List[int]] = None,
    turn_number: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Combat Defeat Split, Surrender & Nemesis Escape Resolver (Decisions 6, 8 & 11):
    - Intermediate `encounter_roster` wipe/flee -> raises `alert_level`, cascades `surviving_enemies` into
      `climax_spec['reinforcements']`, keeps quest `Active`!
    - Climax Boss wipe (0 HP) or `EVADE_TACTICAL_FLEE` -> marks quest `Failed` + `WorldScar`
      (and triggers **Hard Game Over** on Story Chapter 10 Final Boss!).
    - `surrendered_enemies` -> live capture (`clean_success`) or spare/fake-death (`twist_resolution`).
    - `fled_enemies` (Boss escaped) -> promotes Boss into `campaign_spines.nemeses_json`;
      resolves `failure` on strict Elimination else `partial_success` (`0.5x` gold).
    """
    from game_engine.quests import apply_quest_failure_consequences

    q = db.get_quest_by_id(session_id, quest_id)
    dossier = db.get_quest_dossier(session_id, quest_id)
    if not q or not dossier:
        return {"handled": False}

    sess = db.get_session(session_id) or {}
    eff_turn = int(turn_number if turn_number is not None else db.infer_session_turn(sess))
    uids = list(party_user_ids or db.get_session_members(session_id) or [])
    climax = dict(dossier.get("climax_spec") or {})
    leads = [dict(l) for l in (dossier.get("leads_graph") or [])]

    if not is_climax_boss:
        if party_wiped or fled_battle:
            prev_alert = int(dossier.get("alert_level") or 0)
            new_alert = min(int(dossier.get("max_alert") or 4) - 1, prev_alert + 1)
            reinf = list(climax.get("reinforcements") or [])
            if surviving_enemies:
                reinf.extend([dict(e) for e in surviving_enemies if isinstance(e, dict)])
            prev_climax = dict(dossier.get("climax_spec") or {})
            climax["reinforcements"] = reinf
            db.append_dossier_state_event(session_id, quest_id, eff_turn, "alert_level", prev_alert, new_alert)
            db.append_dossier_state_event(session_id, quest_id, eff_turn, "climax_spec", prev_climax, climax)
            db.upsert_quest_dossier(session_id, quest_id, engaged_flag=1, alert_level=new_alert, climax_spec=climax)
            return {
                "handled": True,
                "quest_status": "Active",
                "alert_level": new_alert,
                "reinforcements_added": len(surviving_enemies or []),
            }

        prev_leads = [dict(l) for l in leads]
        prev_climax = dict(climax)
        cleared_any = False
        for ld in leads:
            if ld.get("encounter_roster") and not ld.get("roster_cleared"):
                ld["roster_cleared"] = True
                ld["status"] = "completed"
                cleared_any = True
        looted_clue = None
        if cleared_any:
            looted_clue = seed_or_discover_dossier_clue(
                session_id,
                quest_id,
                clue_index=0,
                source_location=str(sess.get("current_location") or ""),
            )
            has_folklore_rec_cbt = False
            if "anomaly_bp:" in str(q.get("quest_notes") or "") or "anomaly_blueprint:" in str(q.get("quest_notes") or ""):
                try:
                    from mechanics.world.anomalous_events import reveal_anomaly_dossier
                    from mechanics.world.anomaly_engine import parse_blueprint_from_notes
                    bp_cbt_l = parse_blueprint_from_notes(str(q.get("quest_notes") or ""))
                    if bp_cbt_l and bp_cbt_l.get("codex_id"):
                        has_folklore_rec_cbt = db.user_has_folklore_recognition(
                            db.get_session_participant_user_ids(session_id),
                            str(bp_cbt_l["codex_id"]),
                            session_id=session_id,
                        )
                    reveal_anomaly_dossier(session_id, quest_id=quest_id)
                except Exception:
                    pass
            gate_str = str(climax.get("gate_type") or climax.get("unlock_gate") or "").lower()
            completed_leads = sum(1 for l in leads if l.get("status") == "completed" or l.get("roster_cleared"))
            min_req = int(climax.get("min_leads_required") or 2)
            if has_folklore_rec_cbt:
                min_req = max(1, min_req - 1)
            if "secret" in gate_str or completed_leads >= min_req:
                climax["is_unlocked"] = True
                db.unlock_climax_waypoint(
                    session_id,
                    quest_id,
                    str(climax.get("location") or ""),
                    str(climax.get("true_culprit") or ""),
                )
        db.append_dossier_state_event(session_id, quest_id, eff_turn, "leads_graph", prev_leads, leads)
        if climax != prev_climax:
            db.append_dossier_state_event(session_id, quest_id, eff_turn, "climax_spec", prev_climax, climax)
        db.upsert_quest_dossier(session_id, quest_id, engaged_flag=1, leads_graph=leads, climax_spec=climax)
        return {
            "handled": True,
            "quest_status": "Active",
            "roster_cleared": True,
            "climax_unlocked": bool(climax.get("is_unlocked")),
            "looted_clue": looted_clue,
        }

    if party_wiped or fled_battle:
        reason_code = "boss_wipe" if party_wiped else "EVADE_TACTICAL_FLEE"
        if q.get("is_story_quest"):
            with db.get_conn() as conn:
                conn.execute(
                    "UPDATE quests SET status='Failed', updated_at=? WHERE session_id=? AND quest_id=?",
                    (time.time(), session_id, quest_id),
                )
            db.append_dossier_state_event(session_id, quest_id, eff_turn, "quest_status", "Active", "Failed")
            db.append_dossier_state_event(session_id, quest_id, eff_turn, "outcome_tier", dossier.get("outcome_tier", ""), "failure")
            db.upsert_quest_dossier(session_id, quest_id, outcome_tier="failure")
            ch_res = resolve_chapter_transition(
                session_id=session_id,
                quest=q,
                status="Failed",
                reason=reason_code,
                party_user_ids=uids,
            )
            return {
                "handled": True,
                "quest_status": "Failed",
                "outcome_tier": "failure",
                "hard_game_over": bool(ch_res.get("hard_game_over")),
                "fallen_world": bool(ch_res.get("fallen_world")),
                "chapter_transition": ch_res,
            }

        fail_res = apply_quest_failure_consequences(session_id, q, uids, reason=reason_code, session=sess)
        venue = str(climax.get("location") or sess.get("current_location") or "District")
        scar_spec = (
            ((dossier.get("outcomes_matrix") or {}).get("failure") or {}).get("world_scar")
            or render_world_scar_spec(engine=str(dossier.get("engine") or "HUNT_CONTAINMENT"), venue_name=venue)
        )
        scar_ev = spawn_quest_world_scar(
            session_id=session_id,
            source_quest_id=quest_id,
            scar_spec=scar_spec,
            location_name=venue,
            turn_number=eff_turn,
        )
        db.append_dossier_state_event(session_id, quest_id, eff_turn, "quest_status", "Active", "Failed")
        db.append_dossier_state_event(session_id, quest_id, eff_turn, "outcome_tier", dossier.get("outcome_tier", ""), "failure")
        db.upsert_quest_dossier(session_id, quest_id, outcome_tier="failure")
        return {
            "handled": True,
            "quest_status": "Failed",
            "outcome_tier": "failure",
            "world_scar": scar_ev,
            "failure_details": fail_res,
        }

    boss_sheet = climax.get("boss_sheet") or {"name": climax.get("true_culprit") or q.get("title") or "Escaped Boss"}
    if fled_enemies:
        promote_escaped_boss_to_nemesis(
            session_id=session_id,
            boss_sheet=boss_sheet,
            quest_id=quest_id,
            turn_number=eff_turn,
            reason="fled_climax",
        )
        if climax.get("is_elimination_strict"):
            apply_quest_failure_consequences(session_id, q, uids, reason="target_escaped", session=sess)
            venue = str(climax.get("location") or sess.get("current_location") or "District")
            scar_ev = spawn_quest_world_scar(
                session_id=session_id,
                source_quest_id=quest_id,
                scar_spec=render_world_scar_spec(engine=str(dossier.get("engine") or "HUNT_CONTAINMENT"), venue_name=venue),
                location_name=venue,
                turn_number=eff_turn,
            )
            db.upsert_quest_dossier(session_id, quest_id, outcome_tier="failure")
            return {
                "handled": True,
                "quest_status": "Failed",
                "outcome_tier": "failure",
                "nemesis_promoted": True,
                "world_scar": scar_ev,
            }

        part_gold = int(round(int(q.get("reward_gold") or 50) * 0.5))
        part_xp = int(round(int(q.get("reward_xp") or 100) * 0.75))
        try:
            from scenario_data import is_anomalous_incursions_scenario
            if is_anomalous_incursions_scenario(str(sess.get("scenario") or "")) and uids:
                res_tax = db.persist_anomalous_quest_containment(session_id, q, int(uids[0]), party_user_ids=uids)
                if res_tax.get("confiscate_gold"):
                    part_gold = 0
        except Exception:
            pass
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE quests SET status='Completed', reward_gold=?, reward_xp=?, reward_claimed=1, updated_at=? WHERE session_id=? AND quest_id=?",
                (part_gold, part_xp, time.time(), session_id, quest_id),
            )
        for uid in uids:
            db.apply_hp_mp_delta(int(uid), gold_delta=part_gold)
            db.add_xp(int(uid), part_xp)
        db.upsert_quest_dossier(session_id, quest_id, outcome_tier="partial_success")
        return {
            "handled": True,
            "quest_status": "Completed",
            "outcome_tier": "partial_success",
            "gold_awarded": part_gold,
            "xp_awarded": part_xp,
            "nemesis_promoted": True,
        }

    tier = "twist_resolution" if (surrendered_enemies and surrender_choice == "spare_fake_death") else "clean_success"
    mult = 1.25 if tier == "twist_resolution" else 1.0
    econ = dossier.get("contract_economy") or {}
    adv_paid = int(econ.get("upfront_advance_gold") or 0) if econ.get("advance_taken") else 0
    final_gold = max(0, int(round(int(q.get("reward_gold") or 50) * mult)) - adv_paid)
    try:
        from scenario_data import is_anomalous_incursions_scenario
        if is_anomalous_incursions_scenario(str(sess.get("scenario") or "")) and uids:
            res_tax = db.persist_anomalous_quest_containment(session_id, q, int(uids[0]), party_user_ids=uids)
            if res_tax.get("confiscate_gold"):
                final_gold = 0
    except Exception:
        pass
    final_xp = int(round(int(q.get("reward_xp") or 100) * (1.15 if tier == "twist_resolution" else 1.0)))

    prev_climax = dict(climax)
    climax["boss_defeated"] = True
    if climax.get("main_stages"):
        m_stages = [dict(ms) for ms in (climax.get("main_stages") or [])]
        for ms in m_stages:
            ms["status"] = "completed"
            ms["completed"] = True
        climax["main_stages"] = m_stages
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE quests SET status='Completed', reward_claimed=1, updated_at=? WHERE session_id=? AND quest_id=?",
            (time.time(), session_id, quest_id),
        )
    for uid in uids:
        db.apply_hp_mp_delta(int(uid), gold_delta=final_gold)
        db.add_xp(int(uid), final_xp)
    db.append_dossier_state_event(session_id, quest_id, eff_turn, "climax_spec", prev_climax, climax)
    db.append_dossier_state_event(session_id, quest_id, eff_turn, "quest_status", str(q.get("status") or "Active"), "Completed")
    db.append_dossier_state_event(session_id, quest_id, eff_turn, "outcome_tier", str(dossier.get("outcome_tier") or ""), tier)
    saved_cbt_dos = db.upsert_quest_dossier(session_id, quest_id, climax_spec=climax, outcome_tier=tier)
    if climax.get("main_stages") or any(l.get("is_optional") for l in leads):
        db.sync_quest_projection_from_dossier(session_id, quest_id, dossier=saved_cbt_dos)
    complete_remediation_bounty_if_linked(session_id, quest_id, turn_number=eff_turn)
    if not q.get("is_story_quest"):
        evaluate_skipped_threatened_optionals(session_id, quest_id, dossier=saved_cbt_dos, turn_number=eff_turn)

    ch_res = None
    if q.get("is_story_quest"):
        ch_res = resolve_chapter_transition(session_id=session_id, quest=q, status="Completed", party_user_ids=uids)

    return {
        "handled": True,
        "quest_status": "Completed",
        "outcome_tier": tier,
        "captured_alive": bool(surrendered_enemies and surrender_choice == "capture_alive"),
        "gold_awarded": final_gold,
        "xp_awarded": final_xp,
        "chapter_transition": ch_res,
    }


def evaluate_intimate_liaison_turn(
    session_id: int,
    quest_id: str,
    act_concluded: bool = False,
    forced_non_consent: bool = False,
    walk_in_triggered: bool = False,
    salvage_approach: str = "CHA",
    user_id: Optional[int] = None,
    turn_number: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Silent Post-Act NSFW `INTIMATE_LIAISON` Evaluator (Decision 2):
    - Hard non-consent immediately fails quest + adds Heat + estranges NPC (`-40` affinity) + Scandal `WorldScar`.
    - Risky-venue / `#SecretAffair` walk-ins trigger a 1-shot salvage check (`CHA`/`AGI`/`BRIBE`) before Scandal failure.
    - Concluded consensual encounter silently completes quest (`clean_success`) with zero mid-act UI/prompt spam.
    """
    from game_engine.quests import apply_quest_failure_consequences

    q = db.get_quest_by_id(session_id, quest_id)
    dossier = db.get_quest_dossier(session_id, quest_id)
    if not q or not dossier or dossier.get("engine") != "INTIMATE_LIAISON":
        return {"handled": False}

    sess = db.get_session(session_id) or {}
    eff_turn = int(turn_number if turn_number is not None else db.infer_session_turn(sess))
    climax = dict(dossier.get("climax_spec") or {})
    int_spec = dict(climax.get("intimacy_spec") or {})
    target_npc = str(int_spec.get("target_npc") or (dossier.get("cast_bindings") or {}).get("target", {}).get("name") or "")
    venue = str(climax.get("location") or sess.get("current_location") or "Private Quarters")
    uids = [int(user_id)] if user_id else (db.get_session_members(session_id) or [])

    if forced_non_consent:
        apply_quest_failure_consequences(session_id, q, uids, reason="non_consensual_violation", session=sess)
        if target_npc:
            try:
                db.update_relationship_score(session_id, target_npc, delta_score=-40)
            except Exception:
                pass
        scar_ev = spawn_quest_world_scar(
            session_id=session_id,
            source_quest_id=quest_id,
            scar_spec=render_world_scar_spec(engine="INTIMATE_LIAISON", venue_name=venue),
            location_name=venue,
            turn_number=eff_turn,
        )
        db.upsert_quest_dossier(session_id, quest_id, outcome_tier="failure")
        return {
            "handled": True,
            "quest_status": "Failed",
            "outcome_tier": "failure",
            "estranged_npc": target_npc,
            "world_scar": scar_ev,
        }

    if walk_in_triggered:
        salvage_cfg = dict(int_spec.get("walk_in_salvage") or {})
        already_salvaged = bool(int_spec.get("salvage_used"))
        norm_appr = str(salvage_approach or "CHA").upper()
        salvage_ok = False

        if not already_salvaged and user_id:
            char = db.get_character(int(user_id)) or {}
            if norm_appr == "BRIBE":
                b_cost = int(salvage_cfg.get("bribe_gold") or 35)
                if int(char.get("gold") or 0) >= b_cost:
                    db.apply_hp_mp_delta(int(user_id), gold_delta=-b_cost)
                    salvage_ok = True
            else:
                st_col = "agi" if norm_appr == "AGI" else "cha"
                chk = skill_check.resolve_check(stat_name=norm_appr, stat_value=int(char.get(st_col, 5) or 5), requirement=6)
                salvage_ok = bool(chk.succeeded)

        if salvage_ok:
            int_spec["salvage_used"] = True
            climax["intimacy_spec"] = int_spec
            db.upsert_quest_dossier(session_id, quest_id, engaged_flag=1, climax_spec=climax)
            return {
                "handled": True,
                "quest_status": "Active",
                "salvaged": True,
                "salvage_approach": norm_appr,
            }

        apply_quest_failure_consequences(session_id, q, uids, reason="exposed_scandal", session=sess)
        scar_ev = spawn_quest_world_scar(
            session_id=session_id,
            source_quest_id=quest_id,
            scar_spec=render_world_scar_spec(engine="INTIMATE_LIAISON", venue_name=venue),
            location_name=venue,
            turn_number=eff_turn,
        )
        db.upsert_quest_dossier(session_id, quest_id, outcome_tier="failure")
        return {
            "handled": True,
            "quest_status": "Failed",
            "outcome_tier": "failure",
            "salvaged": False,
            "world_scar": scar_ev,
        }

    if act_concluded:
        gold = int(q.get("reward_gold") or 50)
        xp = int(q.get("reward_xp") or 100)
        prev_climax_int = dict(climax)
        if climax.get("main_stages"):
            m_stages_int = [dict(ms) for ms in (climax.get("main_stages") or [])]
            for ms in m_stages_int:
                ms["status"] = "completed"
                ms["completed"] = True
            climax["main_stages"] = m_stages_int
            climax["completed"] = True
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE quests SET status='Completed', reward_claimed=1, updated_at=? WHERE session_id=? AND quest_id=?",
                (time.time(), session_id, quest_id),
            )
        for uid in uids:
            db.apply_hp_mp_delta(int(uid), gold_delta=gold)
            db.add_xp(int(uid), xp)
        if climax != prev_climax_int:
            db.append_dossier_state_event(session_id, quest_id, eff_turn, "climax_spec", prev_climax_int, climax)
        db.append_dossier_state_event(session_id, quest_id, eff_turn, "quest_status", str(q.get("status") or "Active"), "Completed")
        db.append_dossier_state_event(session_id, quest_id, eff_turn, "outcome_tier", str(dossier.get("outcome_tier") or ""), "clean_success")
        saved_int = db.upsert_quest_dossier(session_id, quest_id, engaged_flag=1, climax_spec=climax, outcome_tier="clean_success")
        if climax.get("main_stages") or any(l.get("is_optional") for l in (dossier.get("leads_graph") or [])):
            db.sync_quest_projection_from_dossier(session_id, quest_id, dossier=saved_int)
        if not q.get("is_story_quest"):
            evaluate_skipped_threatened_optionals(session_id, quest_id, dossier=saved_int, turn_number=eff_turn)
        ch_res_int = resolve_chapter_transition(session_id=session_id, quest=q, status="Completed", party_user_ids=uids) if q.get("is_story_quest") else None
        return {
            "handled": True,
            "quest_status": "Completed",
            "outcome_tier": "clean_success",
            "gold_awarded": gold,
            "xp_awarded": xp,
            "chapter_transition": ch_res_int,
        }

    return {"handled": False}


def handle_npc_death_or_recruitment_fallout(
    session_id: int,
    npc_name: str,
    event_kind: str = "dead",
    current_location: str = "",
    turn_number: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Zero-Plot-Armor NPC Death & Early Recruitment Fallout (Decision 13):
    - CampaignSpine Lieutenant killed/recruited -> promotes vengeful successor & escalates Mastermind.
    - Quest Informant killed -> shifts clue to physical cipher/ledger in room (+1 Alert) so quest never soft-locks.
    - Quest Client killed -> flips `client_culprit` twist or voids contract.
    """
    target_low = str(npc_name or "").strip().lower()
    if not session_id or not target_low:
        return {"spine_mutated": False, "affected_quests": []}

    sess = db.get_session(session_id) or {}
    eff_turn = int(turn_number if turn_number is not None else db.infer_session_turn(sess))
    loc = str(current_location or sess.get("current_location") or "Crime Scene")

    spine_after = mutate_spine_on_lieutenant_fate(
        session_id=session_id,
        npc_name=npc_name,
        fate=event_kind,
        turn_number=eff_turn,
    )

    affected: List[Dict[str, Any]] = []
    for dos in (db.get_session_quest_dossiers(session_id, status_stage="compiled") or []):
        qid = str(dos.get("quest_id") or "")
        q_row = db.get_quest_by_id(session_id, qid)
        if not q_row or q_row.get("status") != "Active":
            continue

        cb = {k: dict(v) if isinstance(v, dict) else v for k, v in (dos.get("cast_bindings") or {}).items()}
        inf_name = str((cb.get("informant") or {}).get("name") or "").strip().lower()
        cli_name = str((cb.get("client") or {}).get("name") or "").strip().lower()
        acc_name = str((cb.get("accomplice") or {}).get("name") or "").strip().lower()

        if event_kind == "dead":
            prev_leads_fo = [dict(l) for l in (dos.get("leads_graph") or [])]
            new_leads_fo = [dict(l) for l in prev_leads_fo]
            locked_opts: List[str] = []
            for idx_lo, ld_lo in enumerate(new_leads_fo):
                if (
                    ld_lo.get("is_optional")
                    and str(ld_lo.get("role") or "").strip().lower() == "alternative"
                    and str(ld_lo.get("status") or "active").strip().lower() not in ("completed", "failed", "locked_out")
                ):
                    opt_npc = str(ld_lo.get("target_npc") or "").strip().lower()
                    if opt_npc == target_low or (acc_name and acc_name == target_low and not opt_npc):
                        ld_lo["status"] = "locked_out"
                        ld_lo["lockout_reason"] = "envoy_killed"
                        new_leads_fo[idx_lo] = ld_lo
                        locked_opts.append(str(ld_lo.get("optional_id") or ld_lo.get("lead_id") or ""))
            if locked_opts:
                if "accomplice" in cb and isinstance(cb["accomplice"], dict) and acc_name == target_low:
                    cb["accomplice"]["status"] = "dead"
                db.append_dossier_state_event(session_id, qid, eff_turn, "leads_graph", prev_leads_fo, new_leads_fo)
                saved_lo = db.upsert_quest_dossier(session_id, qid, cast_bindings=cb, leads_graph=new_leads_fo, engaged_flag=1)
                db.sync_quest_projection_from_dossier(session_id, qid, dossier=saved_lo)
                affected.append(
                    {
                        "quest_id": qid,
                        "role": "alternative_envoy",
                        "fallback": "optional_locked_out",
                        "locked_optionals": locked_opts,
                    }
                )

        if event_kind == "dead" and inf_name == target_low:
            cb["informant"]["status"] = "dead"
            fallback_clue = seed_or_discover_dossier_clue(session_id, qid, clue_index=0, source_location=loc)
            new_alert = min(int(dos.get("max_alert") or 4) - 1, int(dos.get("alert_level") or 0) + 1)
            climax = dict(dos.get("climax_spec") or {})
            climax["is_unlocked"] = True
            db.upsert_quest_dossier(session_id, qid, cast_bindings=cb, alert_level=new_alert, climax_spec=climax, engaged_flag=1)
            affected.append({"quest_id": qid, "role": "informant", "fallback": "lootable_cipher_spawned", "clue": fallback_clue})

        elif event_kind == "dead" and cli_name == target_low:
            cb["client"]["status"] = "dead"
            twist = dict(dos.get("twist_spec") or {})
            if twist.get("twist_type") == "client_culprit":
                twist["is_discovered"] = True
                with db.get_conn() as conn:
                    conn.execute("UPDATE quests SET status='Completed', updated_at=? WHERE session_id=? AND quest_id=?", (time.time(), session_id, qid))
                db.upsert_quest_dossier(session_id, qid, cast_bindings=cb, twist_spec=twist, outcome_tier="twist_resolution")
                affected.append({"quest_id": qid, "role": "client", "fallback": "twist_culprit_neutralized"})
            else:
                with db.get_conn() as conn:
                    conn.execute("UPDATE quests SET status='Failed', updated_at=? WHERE session_id=? AND quest_id=?", (time.time(), session_id, qid))
                db.upsert_quest_dossier(session_id, qid, cast_bindings=cb, outcome_tier="failure")
                affected.append({"quest_id": qid, "role": "client", "fallback": "contract_voided"})

    return {
        "spine_mutated": spine_after is not None,
        "spine": spine_after,
        "affected_quests": affected,
    }


def resolve_post_turn_dossier_hooks(
    session_id: int,
    session: Optional[Dict[str, Any]],
    outcome: Optional[Dict[str, Any]],
    actions: Optional[List[Dict[str, Any]]] = None,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Unified post-turn orchestrator for epilogue choices, NPC death/recruitment fallout,
    partner-verified INTIMATE_LIAISON resolution, and quest combat outcomes."""
    from game_engine.quest_lifecycle import resolve_epilogue_choice

    sess = session if isinstance(session, dict) else (db.get_session(session_id) or {})
    out = outcome if isinstance(outcome, dict) else {}
    eff_turn = int(db.infer_session_turn(sess))
    cur_loc = str(out.get("location") or sess.get("current_location") or "")

    summary: Dict[str, Any] = {
        "epilogue_resolution": None,
        "npc_fallout": [],
        "intimate_liaisons": [],
        "quest_combat": None,
        "unlocked_optionals": [],
    }

    # 1. Campaign Epilogue Choice intents
    for act in (actions or []):
        if isinstance(act, dict):
            ep_int = str(act.get("intent") or "").strip().lower()
            if ep_int in ("epilogue_conclude_campaign", "epilogue_endless_mode"):
                ep_res = resolve_epilogue_choice(session_id, ep_int, eff_turn)
                out["_epilogue_resolution"] = ep_res
                summary["epilogue_resolution"] = ep_res

    # 1b. Hybrid Optional Discovery Hooks (Clues, NPC Dialogue, Incoming SMS/Courier)
    if out.get("new_clues") or out.get("discovered_clue"):
        summary["unlocked_optionals"].extend(
            unlock_hidden_quest_optional(session_id, trigger_source="clue_found", turn_number=eff_turn)
        )
    if out.get("dialogue_partner") or any(
        isinstance(a, dict) and str(a.get("intent") or "").lower() in ("dialogue", "social", "persuade", "negotiate")
        for a in (actions or [])
    ):
        summary["unlocked_optionals"].extend(
            unlock_hidden_quest_optional(session_id, trigger_source="npc_dialogue", turn_number=eff_turn)
        )
    if out.get("incoming_sms") or out.get("phone_notifications") or out.get("new_messages"):
        summary["unlocked_optionals"].extend(
            unlock_hidden_quest_optional(session_id, trigger_source="incoming_comms", turn_number=eff_turn)
        )

    # 2. Zero-Plot-Armor NPC Death & Turn-Pipeline Recruitment Fallout
    for dead_item in list(out.get("dead_npcs") or []) + list(out.get("_dead_enemies") or []):
        dn_str = str(dead_item.get("name") if isinstance(dead_item, dict) else dead_item).strip()
        if dn_str:
            f_res = handle_npc_death_or_recruitment_fallout(
                session_id,
                dn_str,
                event_kind="dead",
                current_location=cur_loc,
                turn_number=eff_turn,
            )
            summary["npc_fallout"].append(f_res)

    recruited_raw = list(out.get("recruited_npcs") or []) + list(out.get("new_party_npcs") or [])
    if out.get("recruited_companion"):
        recruited_raw.append(out["recruited_companion"])
    for rec_item in recruited_raw:
        rn_str = str(rec_item.get("name") if isinstance(rec_item, dict) else rec_item).strip()
        if rn_str:
            f_res = handle_npc_death_or_recruitment_fallout(
                session_id,
                rn_str,
                event_kind="recruited",
                current_location=cur_loc,
                turn_number=eff_turn,
            )
            summary["npc_fallout"].append(f_res)

    # 3. Quest Combat Outcome Resolution (when a quest-linked encounter ends)
    q_enc = sess.get("_active_quest_encounter") or out.get("_active_quest_encounter")
    if isinstance(q_enc, dict) and q_enc.get("quest_id") and not out.get("_quest_combat_resolved"):
        rem_enemies = [
            e for e in (sess.get("nearby_enemies") or out.get("nearby_enemies") or [])
            if isinstance(e, dict) and int(e.get("hp", 0) or 0) > 0
        ]
        fled_btl = bool(out.get("fled_combat") or out.get("_fled_battle"))
        wiped = bool(out.get("party_wiped") or out.get("game_over"))
        if not rem_enemies or fled_btl or wiped:
            c_res = resolve_quest_combat_outcome(
                session_id=session_id,
                quest_id=str(q_enc["quest_id"]),
                is_climax_boss=bool(q_enc.get("is_climax_boss")),
                party_wiped=wiped,
                fled_battle=fled_btl,
                surviving_enemies=rem_enemies,
                fled_enemies=list(out.get("fled_enemies") or []),
                surrendered_enemies=list(out.get("surrendered_enemies") or []),
                surrender_choice=str(out.get("surrender_choice") or "capture_alive"),
                turn_number=eff_turn,
            )
            out["_quest_combat_resolved"] = c_res
            summary["quest_combat"] = c_res
            if isinstance(session, dict):
                session.pop("_active_quest_encounter", None)
            try:
                db.update_session(session_id, extra={"_active_quest_encounter": None})
            except Exception:
                pass

    # 4. Partner-Verified Silent INTIMATE_LIAISON Evaluation
    iu = out.get("intimate_update") if isinstance(out.get("intimate_update"), dict) else {}
    act_done = bool(
        str(iu.get("phase") or "").lower() in ("aftercare", "resolved", "ended")
    ) or bool(out.get("_resolved_milestone_event"))
    if act_done:
        partner_cand = str(
            iu.get("partner")
            or iu.get("npc_name")
            or out.get("dialogue_partner")
            or sess.get("intimate_partner")
            or sess.get("dialogue_partner")
            or ""
        ).strip()
        p_low = partner_cand.lower()
        comp_dos = db.get_session_quest_dossiers(session_id, status_stage="compiled") or []
        for cd in comp_dos:
            if cd.get("engine") != "INTIMATE_LIAISON":
                continue
            qid_il = str(cd.get("quest_id") or "")
            q_row = db.get_quest_by_id(session_id, qid_il)
            if not q_row or str(q_row.get("status") or "") != "Active":
                continue
            cb_il = cd.get("cast_bindings") or {}
            target_npc = str(
                (cb_il.get("target") or {}).get("name")
                or (cb_il.get("client") or {}).get("name")
                or q_row.get("client_npc")
                or ""
            ).strip()
            if target_npc:
                t_low = target_npc.lower()
                if not p_low or not (p_low == t_low or t_low in p_low or p_low in t_low):
                    continue
            il_res = evaluate_intimate_liaison_turn(
                session_id=session_id,
                quest_id=qid_il,
                act_concluded=True,
                forced_non_consent=bool(iu.get("forced_non_consent")),
                walk_in_triggered=bool(iu.get("walk_in_triggered")),
                salvage_approach=str(iu.get("salvage_approach") or "CHA"),
                user_id=user_id,
                turn_number=eff_turn,
            )
            summary["intimate_liaisons"].append(il_res)

    return summary
