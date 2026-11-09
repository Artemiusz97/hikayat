from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import db
import skill_check
from game_engine.quest_lifecycle import (
    complete_remediation_bounty_if_linked,
    evaluate_skipped_threatened_optionals,
    resolve_chapter_transition,
    sanitize_dossier_prose,
)
from mechanics.narrative.campaign_spine import update_campaign_ending_axes
from mechanics.narrative.clues import evaluate_clue_deduction
from mechanics.narrative.quest_engines import render_world_scar_spec
from mechanics.world.locations.access_gate import get_node_effective_access_info
from mechanics.world.world_events.engine import spawn_quest_world_scar


def _normalize_lead_target_key(waypoint_or_lead: Dict[str, Any]) -> str:
    raw = (
        waypoint_or_lead.get("lead_id")
        or waypoint_or_lead.get("target_npc")
        or waypoint_or_lead.get("stage_label")
        or waypoint_or_lead.get("title")
        or f"stage_{waypoint_or_lead.get('stage_index', 1)}"
    )
    return str(raw).strip().lower()


def resolve_caseboard_deduction(
    session_id: int,
    clue_a_id: int,
    clue_b_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Deterministic Logic Caseboard Pairing (Decision 16):
    - Evaluates `clue_graph` edges deterministically (ZERO fake percentage RNG rolls!).
    - Rejects red herrings cleanly without consuming genuine leads.
    - Valid corroborating pairs unlock `climax_spec['is_unlocked'] = True`, reveal `twist_spec['is_discovered'] = True`,
      synthesize a Breakthrough clue, and award `+50 XP`.
    """
    if not clue_a_id:
        return {"is_valid": False, "title": "Missing Lead", "detail_text": "Select an initial evidence lead."}
    # Folklore Recognition (-1 Stage 1 Clue Requirement, min 1) for previously Verified/Contained Codex entities
    clue_a = db.get_session_clue_by_id(int(clue_a_id)) if clue_a_id else None
    if clue_a and not clue_a.get("is_consumed"):
        qid_rec = str(clue_a.get("quest_id") or "")
        q_rec = db.get_quest_by_id(session_id, qid_rec) if qid_rec else None
        if q_rec and ("anomaly_bp:" in str(q_rec.get("quest_notes") or "") or "anomaly_blueprint:" in str(q_rec.get("quest_notes") or "")):
            try:
                from mechanics.world.anomaly_engine import parse_blueprint_from_notes
                from mechanics.world.anomalous_events import reveal_anomaly_dossier
                bp_rec = parse_blueprint_from_notes(str(q_rec.get("quest_notes") or ""))
                uids_rec = db.get_session_participant_user_ids(session_id) or ([int(user_id)] if user_id else [])
                if bp_rec and bp_rec.get("codex_id") and db.user_has_folklore_recognition(
                    uids_rec, str(bp_rec["codex_id"]), session_id=session_id
                ):
                    dos_rec = db.get_quest_dossier(session_id, qid_rec)
                    cg_rec = list((dos_rec or {}).get("clue_graph") or [])
                    is_rh = any(
                        (n.get("clue_id") and int(n["clue_id"]) == int(clue_a_id) and n.get("is_red_herring"))
                        for n in cg_rec
                    )
                    if not is_rh and (not clue_b_id or int(clue_a_id) == int(clue_b_id)):
                        rev_rec = reveal_anomaly_dossier(session_id, quest_id=qid_rec)
                        bp_unm = rev_rec.get("blueprint") or bp_rec
                        canon_nm = str(bp_unm.get("canonical_name") or bp_unm.get("name") or "Known Folklore Entity")
                        if dos_rec:
                            prev_c = dict(dos_rec.get("climax_spec") or {})
                            climax_r = dict(prev_c)
                            climax_r["is_unlocked"] = True
                            db.unlock_climax_waypoint(session_id, qid_rec, str(climax_r.get("location") or ""), str(climax_r.get("true_culprit") or canon_nm))
                            eff_t = int(db.infer_session_turn(db.get_session(session_id) or {}))
                            if climax_r != prev_c:
                                db.append_dossier_state_event(session_id, qid_rec, eff_t, "climax_spec", prev_c, climax_r)
                            db.upsert_quest_dossier(session_id, qid_rec, climax_spec=climax_r, engaged_flag=1)
                        unlocked_opts_r = []
                        try:
                            from game_engine.quest_turn_resolver import unlock_hidden_quest_optional
                            unlocked_opts_r = unlock_hidden_quest_optional(session_id, quest_id=qid_rec, trigger_source="clue_found")
                        except Exception:
                            pass
                        cur_ch_r = int(db.get_session_chapter(session_id) or 1)
                        title_r = f"Folklore Recognition: {canon_nm}"
                        detail_r = f"Prior Codex knowledge immediately identified {canon_nm}'s signature from a single field clue!"
                        synth_r = db.synthesize_deduction_clue(session_id, [int(clue_a_id)], title_r, detail_r, chapter=cur_ch_r)
                        for uid_r in uids_rec:
                            try:
                                db.add_xp(int(uid_r), 50)
                            except Exception:
                                pass
                        return {
                            "is_valid": True,
                            "folklore_recognition": True,
                            "quest_id": qid_rec,
                            "synthesized_clue_id": synth_r,
                            "title": title_r,
                            "detail_text": detail_r,
                            "climax_unlocked": True,
                            "unlocked_optionals": unlocked_opts_r,
                            "xp_awarded": 50,
                        }
            except Exception:
                pass

    if clue_a and clue_a.get("is_consumed"):
        return {
            "is_valid": False,
            "title": "Lead Already Consumed",
            "detail_text": "This evidence lead was already consumed in a prior breakthrough.",
        }

    if not clue_b_id or (clue_b_id and int(clue_a_id) == int(clue_b_id)):
        return {
            "is_valid": False,
            "title": "Folklore Recognition Required",
            "detail_text": "Single-clue deduction requires prior Folklore Recognition (verified in Codex) for this entity.",
        }

    clue_b = db.get_session_clue_by_id(int(clue_b_id))
    if not clue_a or not clue_b:
        return {"is_valid": False, "title": "Missing Evidence", "detail_text": "One or both evidence records were not found."}
    if clue_a.get("is_consumed") or clue_b.get("is_consumed"):
        return {"is_valid": False, "title": "Already Synthesized", "detail_text": "One or both leads have already been consumed."}

    qids_to_check = [q for q in (clue_a.get("quest_id"), clue_b.get("quest_id")) if q]
    dossiers = (
        [d for qid in dict.fromkeys(qids_to_check) if (d := db.get_quest_dossier(session_id, str(qid)))]
        or db.get_session_quest_dossiers(session_id, status_stage="compiled")
    )

    for dos in dossiers:
        cg = list(dos.get("clue_graph") or [])
        if not cg:
            continue

        def _match_node(clue_row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            cid_int = int(clue_row["id"])
            c_title = str(clue_row.get("title") or "").strip().lower()
            for n in cg:
                if n.get("clue_id") and int(n["clue_id"]) == cid_int:
                    return n
                if str(n.get("title") or "").strip().lower() == c_title and c_title:
                    return n
            return None

        node_a = _match_node(clue_a)
        node_b = _match_node(clue_b)
        if node_a or node_b:
            if (node_a and node_a.get("is_red_herring")) or (node_b and node_b.get("is_red_herring")):
                return {
                    "is_valid": False,
                    "is_red_herring": True,
                    "title": "Red Herring Rejected",
                    "detail_text": "Cross-referencing exposes one of these items as an uncorroborated plant. Genuine leads remain unconsumed.",
                    "xp_awarded": 0,
                }
            def _nodes_paired(na: Dict[str, Any], nb: Dict[str, Any], other_cid: int) -> bool:
                pw_raw = na.get("paired_with")
                pw_list = pw_raw if isinstance(pw_raw, list) else ([pw_raw] if pw_raw is not None else [])
                pw_strs = {str(x).strip() for x in pw_list if x is not None and str(x).strip()}
                cand_strs = {
                    str(nb.get("clue_key") or "").strip(),
                    str(nb.get("clue_id") or "").strip(),
                    str(other_cid).strip(),
                } - {""}
                return bool(pw_strs & cand_strs)

            if node_a and node_b and (_nodes_paired(node_a, node_b, int(clue_b_id)) or _nodes_paired(node_b, node_a, int(clue_a_id))):
                qid = str(dos["quest_id"])
                prev_climax = dict(dos.get("climax_spec") or {})
                prev_twist = dict(dos.get("twist_spec") or {})
                climax = dict(prev_climax)
                twist = dict(prev_twist)
                if node_a.get("unlocks_climax") or node_b.get("unlocks_climax"):
                    climax["is_unlocked"] = True
                    db.unlock_climax_waypoint(
                        session_id,
                        qid,
                        str(climax.get("location") or ""),
                        str(climax.get("true_culprit") or ""),
                    )
                if (node_a.get("reveals_twist") or node_b.get("reveals_twist")) and twist.get("has_twist"):
                    twist["is_discovered"] = True
                sess_for_turn = db.get_session(session_id) or {}
                eff_turn = int(db.infer_session_turn(sess_for_turn))
                if climax != prev_climax:
                    db.append_dossier_state_event(session_id, qid, eff_turn, "climax_spec", prev_climax, climax)
                if twist != prev_twist:
                    db.append_dossier_state_event(session_id, qid, eff_turn, "twist_spec", prev_twist, twist)
                db.upsert_quest_dossier(session_id, qid, climax_spec=climax, twist_spec=twist, engaged_flag=1)
                unlocked_opts = []
                try:
                    from game_engine.quest_turn_resolver import unlock_hidden_quest_optional
                    unlocked_opts = unlock_hidden_quest_optional(session_id, quest_id=qid, trigger_source="clue_found", turn_number=eff_turn)
                except Exception:
                    pass
                q_chk_anom = db.get_quest_by_id(session_id, qid) or {}
                if "anomaly_bp:" in str(q_chk_anom.get("quest_notes") or "") or "anomaly_blueprint:" in str(q_chk_anom.get("quest_notes") or ""):
                    try:
                        from mechanics.world.anomalous_events import reveal_anomaly_dossier
                        reveal_anomaly_dossier(session_id, quest_id=qid)
                    except Exception:
                        pass

                cur_ch = int(db.get_session_chapter(session_id) or 1)
                conclusion = sanitize_dossier_prose(str(node_a.get("conclusion") or "Corroborated culprit and hidden operational hub."))
                title_out = f"Breakthrough: {climax.get('true_culprit') or 'Confirmed Trail'}"
                synth_id = db.synthesize_deduction_clue(
                    session_id,
                    [int(clue_a_id), int(clue_b_id)],
                    title_out,
                    conclusion,
                    chapter=cur_ch,
                )
                for uid in (db.get_session_members(session_id) or ([int(user_id)] if user_id else [])):
                    try:
                        db.add_xp(int(uid), 50)
                    except Exception:
                        pass
                return {
                    "is_valid": True,
                    "quest_id": qid,
                    "synthesized_clue_id": synth_id,
                    "title": title_out,
                    "detail_text": conclusion,
                    "climax_unlocked": bool(climax.get("is_unlocked")),
                    "twist_revealed": bool(twist.get("is_discovered")),
                    "unlocked_optionals": unlocked_opts,
                    "xp_awarded": 50,
                }

    sess = db.get_session(session_id) or {}
    scen_key = str(sess.get("scenario") or "fantasy")
    is_valid, title, detail_text = evaluate_clue_deduction(clue_a, clue_b, scen_key=scen_key)
    if not is_valid:
        return {"is_valid": False, "title": title or "No Logical Link", "detail_text": detail_text, "xp_awarded": 0}

    cur_ch = int(db.get_session_chapter(session_id) or 1)
    synth_id = db.synthesize_deduction_clue(
        session_id,
        [int(clue_a_id), int(clue_b_id)],
        title,
        detail_text,
        chapter=cur_ch,
    )
    for uid in (db.get_session_members(session_id) or ([int(user_id)] if user_id else [])):
        try:
            db.add_xp(int(uid), 50)
        except Exception:
            pass
    return {
        "is_valid": True,
        "synthesized_clue_id": synth_id,
        "title": title,
        "detail_text": detail_text,
        "xp_awarded": 50,
    }


def resolve_suspect_accusation(
    session_id: int,
    quest_id: str,
    suspect_name: str,
    mode: str = "private",
    user_id: Optional[int] = None,
    turn_number: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Private Confrontation vs. Formal Public Accusation (Decision 16):
    - Correct culprit -> unlocks Climax confrontation + reveals twist if client/accomplice.
    - Wrong suspect (`mode == 'private'`) -> `-5` rapport with suspect + `+1` `alert_level` (quest stays Active unless Alert maxes).
    - Wrong suspect (`mode == 'formal'`) -> Quest `Failed` immediately + persistent `WorldScar`!
    """
    from game_engine.quests import apply_quest_failure_consequences

    q = db.get_quest_by_id(session_id, quest_id)
    dossier = db.get_quest_dossier(session_id, quest_id)
    if not q or not dossier:
        return {"success": False, "status_code": 404, "reason": "Quest dossier not found."}

    sess = db.get_session(session_id) or {}
    eff_turn = int(turn_number if turn_number is not None else db.infer_session_turn(sess))
    climax = dict(dossier.get("climax_spec") or {})
    twist = dict(dossier.get("twist_spec") or {})
    true_culprit = str(climax.get("true_culprit") or "").strip()
    accused_clean = str(suspect_name or "").strip()

    if true_culprit and accused_clean.lower() == true_culprit.lower():
        climax["is_unlocked"] = True
        db.unlock_climax_waypoint(session_id, quest_id, str(climax.get("location") or ""), true_culprit)
        if twist.get("has_twist"):
            twist["is_discovered"] = True
        db.upsert_quest_dossier(session_id, quest_id, engaged_flag=1, climax_spec=climax, twist_spec=twist)
        return {
            "success": True,
            "correct": True,
            "suspect": true_culprit,
            "mode": mode,
            "climax_unlocked": True,
            "twist_discovered": bool(twist.get("is_discovered")),
            "message": f"Confirmed! {true_culprit} is the true culprit—final confrontation unlocked.",
        }

    if str(mode or "private").strip().lower() == "private":
        if accused_clean:
            try:
                db.update_relationship_score(session_id, accused_clean, delta_score=-5)
            except Exception:
                pass
        prev_alert = int(dossier.get("alert_level") or 0)
        max_alert = int(dossier.get("max_alert") or 4)
        new_alert = min(max_alert, prev_alert + 1)
        db.append_dossier_state_event(session_id, quest_id, eff_turn, "alert_level", prev_alert, new_alert)
        db.upsert_quest_dossier(session_id, quest_id, engaged_flag=1, alert_level=new_alert)
        return {
            "success": True,
            "correct": False,
            "mode": "private",
            "quest_status": "Active",
            "alert_level": new_alert,
            "max_alert": max_alert,
            "rapport_delta": -5,
            "message": f"{accused_clean} angrily denies the private accusation (-5 Rapport, +1 Alert).",
        }

    uids = [int(user_id)] if user_id else (db.get_session_members(session_id) or [])
    fail_res = apply_quest_failure_consequences(session_id, q, uids, reason="false_public_accusation", session=sess)
    venue = str(climax.get("location") or sess.get("current_location") or "Tribunal")
    scar_ev = spawn_quest_world_scar(
        session_id=session_id,
        source_quest_id=quest_id,
        scar_spec=render_world_scar_spec(engine="SOCIAL_BROKERAGE", venue_name=venue),
        location_name=venue,
        turn_number=eff_turn,
    )
    db.append_dossier_state_event(session_id, quest_id, eff_turn, "quest_status", "Active", "Failed")
    db.append_dossier_state_event(session_id, quest_id, eff_turn, "outcome_tier", dossier.get("outcome_tier", ""), "failure")
    db.upsert_quest_dossier(session_id, quest_id, engaged_flag=1, outcome_tier="failure")
    return {
        "success": True,
        "correct": False,
        "mode": "formal",
        "quest_status": "Failed",
        "outcome_tier": "failure",
        "world_scar": scar_ev,
        "failure_details": fail_res,
        "message": f"False formal accusation against {accused_clean} collapsed the case in public scandal!",
    }


def acquire_quest_macguffin(
    session_id: int,
    quest_id: str,
    user_id: int,
) -> Optional[Dict[str, Any]]:
    """Spawns the quest's tangible `[ITEM_JSON]`/`[GEAR_JSON]` MacGuffin into player inventory with `is_quest_locked=1`."""
    dossier = db.get_quest_dossier(session_id, quest_id)
    if not dossier:
        return None
    t_item = dict(dossier.get("tangible_item") or {})
    if not t_item.get("has_item") or t_item.get("disposition") not in ("unclaimed", None, ""):
        return t_item

    item_id = db.add_item(
        int(user_id),
        str(t_item["name"]),
        str(t_item.get("item_type") or "Quest Item"),
        str(t_item.get("effect_payload") or "[ITEM_JSON]{\"category\":\"artifact\"}"),
        force=True,
        is_quest_locked=1,
        linked_quest_id=quest_id,
    )
    t_item["disposition"] = "acquired"
    t_item["inventory_id"] = item_id
    db.upsert_quest_dossier(session_id, quest_id, engaged_flag=1, tangible_item=t_item)
    return t_item


def resolve_quest_turn_in_or_betrayal(
    session_id: int,
    quest_id: str,
    user_id: int,
    disposition: str = "deliver",
    party_user_ids: Optional[List[int]] = None,
    current_location: str = "",
    turn_number: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Context-Smart Turn-In, `2x` Twist Blackmail, Side-Switching & Tangible MacGuffin Agency (Decisions 12 & 17):
    Supported `disposition`:
    - `'deliver'`: Standard completion (`in_field` vs `direct_client` check).
    - `'side_switch'`: Side with uncovered twist target (`twist_resolution`, `1.25x` gold).
    - `'blackmail_client'`: Leverage uncovered client twist for `2x` hush-money gold.
    - `'keep'`: Unlock & keep/equip/consume tangible MacGuffin (`is_quest_locked=0` + client betrayal fallout).
    - `'destroy'`: Destroy dangerous MacGuffin.
    - `'fence'`: Sell MacGuffin to black market (`fencing_gold` + `pending_retaliation` + `WorldScar`).
    """
    from game_engine.quests import apply_quest_failure_consequences

    q = db.get_quest_by_id(session_id, quest_id)
    dossier = db.get_quest_dossier(session_id, quest_id)
    if not q or not dossier:
        return {"success": False, "status_code": 404, "reason": "Quest or dossier not found."}

    sess = db.get_session(session_id) or {}
    eff_turn = int(turn_number if turn_number is not None else db.infer_session_turn(sess))
    uids = list(party_user_ids or db.get_session_members(session_id) or [int(user_id)])
    prev_item = dict(dossier.get("tangible_item") or {})
    prev_twist = dict(dossier.get("twist_spec") or {})
    prev_status = str(q.get("status") or "Active")
    prev_tier = str(dossier.get("outcome_tier") or "")
    prev_alert = int(dossier.get("alert_level") or 0)
    t_item = dict(prev_item)
    twist = dict(prev_twist)
    econ = dict(dossier.get("contract_economy") or {})
    t_rules = dict(dossier.get("turn_in_rules") or {})
    climax = dict(dossier.get("climax_spec") or {})
    client_npc = str(q.get("client_npc") or (dossier.get("cast_bindings") or {}).get("client", {}).get("name") or "")
    base_gold = int(econ.get("base_gold") or q.get("reward_gold") or 50)
    adv_paid = int(econ.get("upfront_advance_gold") or 0) if econ.get("advance_taken") else 0
    base_xp = int(q.get("reward_xp") or 100)
    disp = str(disposition or "deliver").strip().lower()

    if disp == "deliver":
        if t_rules.get("mode") == "direct_client" and current_location:
            req_loc = str(q.get("client_location") or "").strip()
            if req_loc and req_loc.lower() not in current_location.strip().lower() and current_location.strip().lower() not in req_loc.lower():
                return {
                    "success": False,
                    "status_code": 400,
                    "requires_client_return": True,
                    "client_location": req_loc,
                    "reason": f"Direct handoff required: return to {client_npc or 'the client'} at {req_loc}.",
                }
        if t_item.get("has_item") and t_item.get("name"):
            db.set_item_quest_lock(int(user_id), quest_id, locked=0)
            db.remove_item_by_name(int(user_id), str(t_item["name"]))
            t_item["disposition"] = "delivered"

        net_gold = max(0, base_gold - adv_paid)
        try:
            from scenario_data import is_anomalous_incursions_scenario
            if is_anomalous_incursions_scenario(str(sess.get("scenario") or "")):
                res_tax = db.persist_anomalous_quest_containment(session_id, q, int(user_id), party_user_ids=uids)
                if res_tax.get("confiscate_gold"):
                    net_gold = 0
        except Exception:
            pass
        prev_climax = dict(climax)
        if climax.get("main_stages"):
            m_stages = [dict(ms) for ms in (climax.get("main_stages") or [])]
            for ms in m_stages:
                ms["status"] = "completed"
                ms["completed"] = True
            climax["main_stages"] = m_stages
            climax["completed"] = True
        with db.get_conn() as conn:
            conn.execute("UPDATE quests SET status='Completed', reward_claimed=1, updated_at=? WHERE session_id=? AND quest_id=?", (time.time(), session_id, quest_id))
        for uid in uids:
            db.apply_hp_mp_delta(int(uid), gold_delta=net_gold)
            db.add_xp(int(uid), base_xp)
        if t_item != prev_item:
            db.append_dossier_state_event(session_id, quest_id, eff_turn, "tangible_item", prev_item, t_item)
        if climax != prev_climax:
            db.append_dossier_state_event(session_id, quest_id, eff_turn, "climax_spec", prev_climax, climax)
        db.append_dossier_state_event(session_id, quest_id, eff_turn, "quest_status", prev_status, "Completed")
        db.append_dossier_state_event(session_id, quest_id, eff_turn, "outcome_tier", prev_tier, "clean_success")
        saved_del = db.upsert_quest_dossier(session_id, quest_id, climax_spec=climax, tangible_item=t_item, outcome_tier="clean_success")
        if climax.get("main_stages") or any(l.get("is_optional") for l in (dossier.get("leads_graph") or [])):
            db.sync_quest_projection_from_dossier(session_id, quest_id, dossier=saved_del)
        lifted_scars = complete_remediation_bounty_if_linked(session_id, quest_id, turn_number=eff_turn)
        if not q.get("is_story_quest"):
            evaluate_skipped_threatened_optionals(session_id, quest_id, dossier=saved_del, turn_number=eff_turn)
        ch_res = resolve_chapter_transition(session_id, q, status="Completed", party_user_ids=uids) if q.get("is_story_quest") else None
        return {
            "success": True,
            "disposition": "deliver",
            "quest_status": "Completed",
            "outcome_tier": "clean_success",
            "gold_awarded": net_gold,
            "xp_awarded": base_xp,
            "lifted_world_scars": lifted_scars,
            "chapter_transition": ch_res,
        }

    if disp == "side_switch":
        if not (twist.get("has_twist") and twist.get("is_discovered") and twist.get("side_switch_available")):
            return {"success": False, "status_code": 400, "reason": "No uncovered side-switch twist is available on this contract."}
        if t_item.get("has_item") and t_item.get("name"):
            db.set_item_quest_lock(int(user_id), quest_id, locked=0)
            db.remove_item_by_name(int(user_id), str(t_item["name"]))
            t_item["disposition"] = "delivered_to_twist_ally"
        twist["sided_with_twist"] = True
        payout = max(0, int(round(base_gold * 1.25)) - adv_paid)
        try:
            from scenario_data import is_anomalous_incursions_scenario
            if is_anomalous_incursions_scenario(str(sess.get("scenario") or "")):
                res_tax = db.persist_anomalous_quest_containment(session_id, q, int(user_id), party_user_ids=uids)
                if res_tax.get("confiscate_gold"):
                    payout = 0
        except Exception:
            pass
        xp_out = int(round(base_xp * 1.15))
        with db.get_conn() as conn:
            conn.execute("UPDATE quests SET status='Completed', reward_claimed=1, updated_at=? WHERE session_id=? AND quest_id=?", (time.time(), session_id, quest_id))
        for uid in uids:
            db.apply_hp_mp_delta(int(uid), gold_delta=payout)
            db.add_xp(int(uid), xp_out)
        if client_npc:
            try:
                db.update_relationship_score(session_id, client_npc, delta_score=-15)
            except Exception:
                pass
        prev_climax_sw = dict(climax)
        if climax.get("main_stages"):
            m_stages_sw = [dict(ms) for ms in (climax.get("main_stages") or [])]
            for ms in m_stages_sw:
                ms["status"] = "completed"
                ms["completed"] = True
            climax["main_stages"] = m_stages_sw
            climax["completed"] = True
        if t_item != prev_item:
            db.append_dossier_state_event(session_id, quest_id, eff_turn, "tangible_item", prev_item, t_item)
        if climax != prev_climax_sw:
            db.append_dossier_state_event(session_id, quest_id, eff_turn, "climax_spec", prev_climax_sw, climax)
        db.append_dossier_state_event(session_id, quest_id, eff_turn, "twist_spec", prev_twist, twist)
        db.append_dossier_state_event(session_id, quest_id, eff_turn, "quest_status", prev_status, "Completed")
        db.append_dossier_state_event(session_id, quest_id, eff_turn, "outcome_tier", prev_tier, "twist_resolution")
        saved_sw = db.upsert_quest_dossier(session_id, quest_id, climax_spec=climax, twist_spec=twist, tangible_item=t_item, outcome_tier="twist_resolution")
        if climax.get("main_stages") or any(l.get("is_optional") for l in (dossier.get("leads_graph") or [])):
            db.sync_quest_projection_from_dossier(session_id, quest_id, dossier=saved_sw)
        ch_res_sw = None
        if not q.get("is_story_quest"):
            evaluate_skipped_threatened_optionals(session_id, quest_id, dossier=saved_sw, turn_number=eff_turn)
        else:
            update_campaign_ending_axes(session_id, turn_number=eff_turn, faction_pillar="reform", truth_stance="exposed")
            ch_res_sw = resolve_chapter_transition(session_id, q, status="Completed", party_user_ids=uids)
        return {
            "success": True,
            "disposition": "side_switch",
            "quest_status": "Completed",
            "outcome_tier": "twist_resolution",
            "gold_awarded": payout,
            "xp_awarded": xp_out,
            "chapter_transition": ch_res_sw,
        }

    if disp == "blackmail_client":
        if not (twist.get("has_twist") and twist.get("is_discovered") and twist.get("blackmail_available")):
            return {"success": False, "status_code": 400, "reason": "Uncover incriminating client twist evidence before attempting blackmail."}
        char = db.get_character(int(user_id)) or {}
        cha_val = int(char.get("cha", 5) or 5)
        chk = skill_check.resolve_check(stat_name="CHA", stat_value=cha_val, requirement=6)
        if chk.succeeded:
            hush_gold = max(0, int(round(base_gold * float(twist.get("blackmail_multiplier") or 2.0))) - adv_paid)
            twist["hush_money_claimed"] = True
            prev_climax_bm = dict(climax)
            if climax.get("main_stages"):
                m_stages_bm = [dict(ms) for ms in (climax.get("main_stages") or [])]
                for ms in m_stages_bm:
                    ms["status"] = "completed"
                    ms["completed"] = True
                climax["main_stages"] = m_stages_bm
                climax["completed"] = True
            with db.get_conn() as conn:
                conn.execute("UPDATE quests SET status='Completed', reward_claimed=1, updated_at=? WHERE session_id=? AND quest_id=?", (time.time(), session_id, quest_id))
            db.apply_hp_mp_delta(int(user_id), gold_delta=hush_gold)
            db.add_xp(int(user_id), base_xp)
            if climax != prev_climax_bm:
                db.append_dossier_state_event(session_id, quest_id, eff_turn, "climax_spec", prev_climax_bm, climax)
            db.append_dossier_state_event(session_id, quest_id, eff_turn, "twist_spec", prev_twist, twist)
            db.append_dossier_state_event(session_id, quest_id, eff_turn, "quest_status", prev_status, "Completed")
            db.append_dossier_state_event(session_id, quest_id, eff_turn, "outcome_tier", prev_tier, "twist_resolution")
            saved_bm = db.upsert_quest_dossier(session_id, quest_id, climax_spec=climax, twist_spec=twist, outcome_tier="twist_resolution")
            if climax.get("main_stages") or any(l.get("is_optional") for l in (dossier.get("leads_graph") or [])):
                db.sync_quest_projection_from_dossier(session_id, quest_id, dossier=saved_bm)
            ch_res_bm = None
            if not q.get("is_story_quest"):
                evaluate_skipped_threatened_optionals(session_id, quest_id, dossier=saved_bm, turn_number=eff_turn)
            else:
                update_campaign_ending_axes(session_id, turn_number=eff_turn, faction_pillar="shadow", truth_stance="buried", lock_golden=True)
                ch_res_bm = resolve_chapter_transition(session_id, q, status="Completed", party_user_ids=uids)
            return {
                "success": True,
                "disposition": "blackmail_client",
                "blackmail_succeeded": True,
                "quest_status": "Completed",
                "outcome_tier": "twist_resolution",
                "gold_awarded": hush_gold,
                "xp_awarded": base_xp,
                "chapter_transition": ch_res_bm,
            }
        db.update_session(
            session_id,
            extra={
                "pending_retaliation": {
                    "quest_id": quest_id,
                    "quest_title": q.get("title", "Contract"),
                    "enemy_name": f"{client_npc or 'Client'}'s Enforcer",
                    "origin_location": str(sess.get("current_location") or ""),
                }
            },
        )
        new_alert = min(int(dossier.get("max_alert") or 4), prev_alert + 2)
        db.append_dossier_state_event(session_id, quest_id, eff_turn, "alert_level", prev_alert, new_alert)
        db.upsert_quest_dossier(session_id, quest_id, alert_level=new_alert, engaged_flag=1)
        return {
            "success": True,
            "disposition": "blackmail_client",
            "blackmail_succeeded": False,
            "quest_status": "Active",
            "alert_level": new_alert,
            "retaliation_queued": True,
        }

    if disp in ("keep", "fence", "destroy"):
        if not t_item.get("has_item"):
            return {"success": False, "status_code": 400, "reason": "This contract has no tangible MacGuffin item."}
        item_name = str(t_item["name"])
        db.set_item_quest_lock(int(user_id), quest_id, locked=0)

        fenced_gold = 0
        if disp == "fence":
            db.remove_item_by_name(int(user_id), item_name)
            fenced_gold = int(t_item.get("fencing_gold") or round(base_gold * 1.5))
            db.apply_hp_mp_delta(int(user_id), gold_delta=fenced_gold)
            t_item["disposition"] = "fenced"
            t_item["pending_retaliation"] = True
        elif disp == "destroy":
            db.remove_item_by_name(int(user_id), item_name)
            t_item["disposition"] = "destroyed"
        else:
            t_item["disposition"] = "kept"
            t_item["is_quest_locked"] = 0
            t_item["pending_retaliation"] = True

        if disp == "destroy" and twist.get("twist_type") == "cursed_payload":
            with db.get_conn() as conn:
                conn.execute("UPDATE quests SET status='Completed', reward_claimed=1, updated_at=? WHERE session_id=? AND quest_id=?", (time.time(), session_id, quest_id))
            db.add_xp(int(user_id), base_xp)
            db.append_dossier_state_event(session_id, quest_id, eff_turn, "tangible_item", prev_item, t_item)
            db.append_dossier_state_event(session_id, quest_id, eff_turn, "quest_status", prev_status, "Completed")
            db.append_dossier_state_event(session_id, quest_id, eff_turn, "outcome_tier", prev_tier, "twist_resolution")
            db.upsert_quest_dossier(session_id, quest_id, tangible_item=t_item, outcome_tier="twist_resolution")
            return {
                "success": True,
                "disposition": "destroy",
                "quest_status": "Completed",
                "outcome_tier": "twist_resolution",
                "gold_awarded": 0,
                "xp_awarded": base_xp,
            }

        apply_quest_failure_consequences(session_id, q, uids, reason=f"macguffin_{disp}", session=sess)
        if client_npc:
            try:
                db.update_relationship_score(session_id, client_npc, delta_score=-20)
            except Exception:
                pass
        db.update_session(
            session_id,
            extra={
                "pending_retaliation": {
                    "quest_id": quest_id,
                    "quest_title": q.get("title", "Contract"),
                    "enemy_name": f"{client_npc or 'Syndicate'}'s Bounty Hunter",
                    "origin_location": str(sess.get("current_location") or ""),
                }
            },
        )
        venue = str(climax.get("location") or sess.get("current_location") or "District")
        scar_ev = spawn_quest_world_scar(
            session_id=session_id,
            source_quest_id=quest_id,
            scar_spec=render_world_scar_spec(engine=str(dossier.get("engine") or "ACQUISITION_EXCHANGE"), venue_name=venue),
            location_name=venue,
            turn_number=eff_turn,
        )
        db.append_dossier_state_event(session_id, quest_id, eff_turn, "tangible_item", prev_item, t_item)
        db.append_dossier_state_event(session_id, quest_id, eff_turn, "quest_status", prev_status, "Failed")
        db.append_dossier_state_event(session_id, quest_id, eff_turn, "outcome_tier", prev_tier, "failure")
        db.upsert_quest_dossier(session_id, quest_id, tangible_item=t_item, outcome_tier="failure")
        return {
            "success": True,
            "disposition": disp,
            "quest_status": "Failed",
            "outcome_tier": "failure",
            "gold_awarded": fenced_gold,
            "retaliation_queued": True,
            "world_scar": scar_ev,
        }

    return {"success": False, "status_code": 400, "reason": f"Unsupported disposition '{disposition}'."}


def evaluate_schedule_curfew_and_coop_precedence(
    session_id: int,
    session: Optional[Dict[str, Any]],
    actions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Live NPC Schedules, Curfew Stealth Pivot, Phone Meetup Luring & Co-op Conflict Precedence (Decision 18):
    - Detects `curfew_active` / `is_trespassing` via `access_gate` to unlock after-hours stealth (`HEIST_BREACH`).
    - Detects active `commitments` Phone meetup luring for quest targets.
    - Resolves simultaneous Co-op conflicts: destructive/attack actions break simultaneous dialogue negotiations
      unless an ally explicitly intervenes and wins a `CHA`/`AGI` check.
    """
    sess = session or db.get_session(session_id) or {}
    cur_node = str(sess.get("current_node_id") or sess.get("current_location") or "")
    cur_day = int(sess.get("current_day", 1) or 1)
    cur_min = int(sess.get("current_minute", 480) or 480)
    scen = str(sess.get("scenario") or "")
    access_info = (
        get_node_effective_access_info(session_id, cur_node, current_day=cur_day, current_minute=cur_min, scen_key=scen)
        if (session_id and cur_node)
        else {}
    )
    curfew_stealth_open = bool(access_info.get("curfew_active") or access_info.get("is_trespassing"))

    lured_npcs: List[str] = []
    if session_id:
        try:
            for cm in (db.get_active_commitments(session_id) or []):
                if str(cm.get("status") or "").lower() in ("active", "accepted", "arrived") and cm.get("npc_name"):
                    lured_npcs.append(str(cm["npc_name"]))
        except Exception:
            pass

    negotiation_broken = False
    ally_intervened = False
    if len(actions or []) > 1:
        destructive_acts = [
            a for a in actions
            if isinstance(a, dict)
            and (
                str(a.get("intent") or "").lower() in ("combat", "attack", "hostile")
                or any(w in str(a.get("label") or "").lower() for w in ("attack", "strike", "shoot", "stab", "smash", "detonate", "ambush"))
            )
        ]
        social_acts = [
            a for a in actions
            if isinstance(a, dict)
            and (
                str(a.get("stat") or "").upper() == "CHA"
                or str(a.get("intent") or "").lower() in ("dialogue", "persuade", "negotiate")
            )
        ]
        if destructive_acts and social_acts:
            intervention_acts = [
                a for a in actions
                if isinstance(a, dict)
                and any(w in str(a.get("label") or "").lower() for w in ("intervene", "restrain", "hold back", "defuse", "stop"))
                and (
                    (hasattr(a.get("check"), "succeeded") and a["check"].succeeded)
                    or (isinstance(a.get("check"), dict) and a["check"].get("succeeded"))
                )
            ]
            if intervention_acts:
                ally_intervened = True
            else:
                negotiation_broken = True

    return {
        "curfew_stealth_open": curfew_stealth_open,
        "access_info": access_info,
        "lured_meetup_npcs": lured_npcs,
        "coop_negotiation_broken": negotiation_broken,
        "coop_ally_intervened": ally_intervened,
    }


def redact_quest_for_fog_of_war(
    session_id: int,
    quest: Dict[str, Any],
    reveal_all: bool = False,
) -> Dict[str, Any]:
    """
    Diegetic Fog-of-War Quest Dict Sanitizer for REST/WebSocket/Discord adapters:
    - Filters `is_discovered == False` Optionals out of BOTH `optional_objectives` and `sub_objectives`.
    - Strips internal JSON tags and raw `DC`/`HP`/`MP` leaks via `sanitize_dossier_prose`.
    - Hides locked `secret`-gate `true_culprit` and secret climax venue from `stages` / `main_objective`.
    - Attaches `fow` (`build_fog_of_war_quest_payload`) and removes raw internal `dossier` blob.
    """
    q_out = dict(quest or {})
    dos = q_out.get("dossier")
    fow = build_fog_of_war_quest_payload(session_id, q_out, dossier=dos, reveal_all=reveal_all)
    q_out["fow"] = fow
    q_out.pop("dossier", None)
    q_out.pop("quest_notes", None)
    q_out.pop("sub_objectives_json", None)
    q_out.pop("anomaly_blueprint", None)
    q_out.pop("anomaly_blueprint_json", None)

    q_out["title"] = sanitize_dossier_prose(str(q_out.get("title") or ""))
    q_out["objective"] = sanitize_dossier_prose(str(q_out.get("objective") or ""))
    q_out["is_peak_chapter"] = bool(fow.get("is_peak_chapter"))
    if q_out.get("is_story_quest"):
        q_out["deadline_day"] = None
        q_out["deadline_minute"] = None

    raw_subs = list(q_out.get("sub_objectives") or [])
    filtered_subs: List[Dict[str, Any]] = []
    climax_unlocked = bool((fow.get("climax") or {}).get("is_unlocked", True))

    for so in raw_subs:
        if not isinstance(so, dict):
            continue
        if not reveal_all and bool(so.get("is_optional")) and not bool(so.get("is_discovered", True)):
            continue
        so_clean = dict(so)
        so_clean["text"] = sanitize_dossier_prose(str(so_clean.get("text") or so_clean.get("label") or ""))
        if so_clean.get("stakes_hint"):
            so_clean["stakes_hint"] = sanitize_dossier_prose(str(so_clean["stakes_hint"]))
        if so_clean.get("stages"):
            clean_st: List[Dict[str, Any]] = []
            tot_st = len(so_clean["stages"])
            for idx_s, st in enumerate(so_clean["stages"]):
                st_c = dict(st)
                is_final_secret = (
                    not bool(so_clean.get("is_optional"))
                    and not climax_unlocked
                    and not reveal_all
                    and idx_s == tot_st - 1
                )
                if is_final_secret:
                    st_c["stage_label"] = "Uncover leads or Caseboard clues to expose the final confrontation"
                    st_c["text"] = st_c["stage_label"]
                    st_c["target_location"] = "Hidden Lair"
                    st_c["target_npc"] = ""
                else:
                    st_c["stage_label"] = sanitize_dossier_prose(str(st_c.get("stage_label") or st_c.get("text") or ""))
                    st_c["text"] = st_c["stage_label"]
                clean_st.append(st_c)
            so_clean["stages"] = clean_st
        so_clean.pop("waypoints", None)
        filtered_subs.append(so_clean)

    q_out["sub_objectives"] = filtered_subs
    if fow.get("has_structured_objectives"):
        q_out["has_structured_objectives"] = True
        q_out["main_objective"] = fow.get("main_objective")
        q_out["optional_objectives"] = fow.get("optional_objectives") or []
        if fow.get("main_objective") and (fow["main_objective"].get("stages") or []):
            q_out["stages"] = fow["main_objective"]["stages"]
    elif q_out.get("stages"):
        q_out["stages"] = [
            {
                **dict(st),
                "stage_label": sanitize_dossier_prose(str(st.get("stage_label") or st.get("text") or "")),
                "text": sanitize_dossier_prose(str(st.get("text") or st.get("stage_label") or "")),
            }
            for st in q_out["stages"]
            if isinstance(st, dict)
        ]

    if q_out.get("waypoints"):
        q_out["waypoints"] = [
            w
            for w in q_out["waypoints"]
            if isinstance(w, dict)
            and (
                reveal_all
                or not any(
                    isinstance(s, dict)
                    and int(s.get("id", -99)) == int(w.get("sub_obj_id", -98) if w.get("sub_obj_id") is not None else -98)
                    and not bool(s.get("is_discovered", True))
                    for s in raw_subs
                )
            )
        ]
    return q_out


def build_fog_of_war_quest_payload(
    session_id: int,
    quest: Dict[str, Any],
    dossier: Optional[Dict[str, Any]] = None,
    reveal_all: bool = False,
) -> Dict[str, Any]:
    """
    Progressive Fog-of-War Serializer (Decision 10):
    Exposes Main Objective stages, discovered `(Optional)` objectives (with role badge & 1-line `stakes_hint`),
    Alert meter, Burned approaches, and Turn-In mode while hiding `is_discovered == False` optionals,
    un-scouted enemy rosters, secret climax culprits, ending math, and undiscovered twists.
    """
    qid = str(quest.get("quest_id") or "")
    dos = dossier if dossier is not None else (quest.get("dossier") or (db.get_quest_dossier(session_id, qid) if session_id and qid else None))
    if not dos:
        return {"dossier_stage": quest.get("dossier_stage") or "legacy", "has_structured_objectives": False}

    stage = str(dos.get("status_stage") or quest.get("dossier_stage") or "pitch")
    if stage == "pitch":
        stub = dict(dos.get("pitch_stub") or {})
        return {
            "dossier_stage": "pitch",
            "has_structured_objectives": False,
            "engine": dos.get("engine") or stub.get("engine") or "",
            "danger_tier": int(dos.get("danger_tier") or stub.get("danger_tier") or 1),
            "public_pitch": sanitize_dossier_prose(str(stub.get("public_pitch") or quest.get("objective") or "")),
            "client_npc": stub.get("client_npc") or quest.get("client_npc") or "",
            "client_location": stub.get("client_location") or quest.get("client_location") or "",
            "allows_upfront_advance": True,
        }

    climax = dict(dos.get("climax_spec") or {})
    twist = dict(dos.get("twist_spec") or {})
    t_item = dict(dos.get("tangible_item") or {})
    t_rules = dict(dos.get("turn_in_rules") or {})
    econ = dict(dos.get("contract_economy") or {})
    burned_map = dict(dos.get("burned_approaches") or {})
    climax_unlocked = bool(reveal_all or climax.get("gate_type") == "open" or climax.get("is_unlocked"))
    twist_visible = bool(twist.get("has_twist") and (reveal_all or twist.get("is_discovered")))
    raw_leads = list(dos.get("leads_graph") or [])
    has_structured = bool(climax.get("main_stages") or any(isinstance(l, dict) and l.get("is_optional") for l in raw_leads))

    visible_leads: List[Dict[str, Any]] = []
    optional_objectives: List[Dict[str, Any]] = []
    for ld in raw_leads:
        if not reveal_all and not ld.get("is_discovered", True):
            continue
        t_key = _normalize_lead_target_key(ld)
        burned_here = [str(x).upper() for x in (burned_map.get(t_key) or [])]
        scouted = bool(reveal_all or ld.get("roster_scouted") or ld.get("roster_cleared"))
        roster = list(ld.get("encounter_roster") or [])
        approaches_out = [
            {
                "approach_id": a.get("approach_id"),
                "stat": a.get("stat"),
                "label": sanitize_dossier_prose(str(a.get("label") or "")),
                "gold_cost": a.get("gold_cost", 0),
                "after_hours_pivot": bool(a.get("after_hours_pivot")),
                "burned": str(a.get("stat") or "").upper() in burned_here
                or str(a.get("approach_id") or "").upper() in burned_here,
            }
            for a in (ld.get("approaches") or [])
        ]
        clean_title = sanitize_dossier_prose(str(ld.get("title") or ld.get("label") or ""))
        clean_hint = sanitize_dossier_prose(str(ld.get("stakes_hint") or ""))
        ld_status = str(ld.get("status") or "active")
        lead_entry = {
            "lead_id": ld.get("lead_id"),
            "optional_id": ld.get("optional_id") or ld.get("lead_id"),
            "sub_obj_id": ld.get("sub_obj_id"),
            "is_optional": bool(ld.get("is_optional")),
            "role": ld.get("role") or "aid",
            "badge": sanitize_dossier_prose(str(ld.get("badge") or "")),
            "stakes_hint": clean_hint,
            "title": clean_title,
            "flavor_note": sanitize_dossier_prose(str(ld.get("flavor_note") or "")),
            "status": ld_status,
            "lockout_reason": str(ld.get("lockout_reason") or ""),
            "bonus_claimed": bool(ld.get("bonus_claimed")),
            "target_npc": ld.get("target_npc") or "",
            "target_location": ld.get("target_location") or "",
            "approaches": approaches_out,
            "has_combat_pack": len(roster) > 0,
            "roster_scouted": scouted,
            "roster_cleared": bool(ld.get("roster_cleared")),
            "scouted_enemies": (
                [{"name": sanitize_dossier_prose(str(e.get("name") or "")), "role": e.get("archetype") or e.get("tier_label") or "Hostile"} for e in roster]
                if scouted and roster
                else []
            ),
            "supports_phone_lure": bool(ld.get("supports_phone_lure")),
        }
        visible_leads.append(lead_entry)
        if ld.get("is_optional"):
            optional_objectives.append(
                {
                    "id": int(ld.get("sub_obj_id") or len(optional_objectives) + 1),
                    "optional_id": ld.get("optional_id") or ld.get("lead_id"),
                    "lead_id": ld.get("lead_id"),
                    "is_optional": True,
                    "role": str(ld.get("role") or "aid"),
                    "badge": sanitize_dossier_prose(str(ld.get("badge") or f"Optional — {str(ld.get('role') or 'aid').title()}")),
                    "title": clean_title,
                    "text": clean_title,
                    "stakes_hint": clean_hint,
                    "flavor_note": sanitize_dossier_prose(str(ld.get("flavor_note") or "")),
                    "status": ld_status,
                    "completed": ld_status == "completed",
                    "failed": ld_status == "failed",
                    "bypassed": ld_status == "bypassed",
                    "locked_out": ld_status == "locked_out",
                    "lockout_reason": str(ld.get("lockout_reason") or ""),
                    "bonus_claimed": bool(ld.get("bonus_claimed")),
                    "target_npc": ld.get("target_npc") or "",
                    "target_location": ld.get("target_location") or "",
                    "approaches": approaches_out,
                }
            )

    main_objective: Optional[Dict[str, Any]] = None
    if has_structured:
        raw_main_stages = list(climax.get("main_stages") or [])
        fow_main_stages: List[Dict[str, Any]] = []
        for idx_ms, ms in enumerate(raw_main_stages):
            is_secret_climax = bool(ms.get("is_climax_stage") and not climax_unlocked and not reveal_all)
            ms_stat = str(ms.get("status") or "locked")
            ms_done = ms_stat.lower() in ("completed", "bypassed") or bool(ms.get("completed"))
            ms_lbl = (
                "Uncover leads or Caseboard clues to expose the final confrontation"
                if is_secret_climax
                else sanitize_dossier_prose(str(ms.get("stage_label") or ms.get("label") or ""))
            )
            fow_main_stages.append(
                {
                    "stage_index": int(ms.get("stage_index", idx_ms + 1) or (idx_ms + 1)),
                    "stage_label": ms_lbl,
                    "text": ms_lbl,
                    "target_location": "Hidden Lair" if is_secret_climax else str(ms.get("target_location") or ""),
                    "target_npc": "" if is_secret_climax else str(ms.get("target_npc") or ""),
                    "status": ms_stat,
                    "completed": ms_done,
                    "bypassed": ms_stat.lower() == "bypassed",
                }
            )
        cur_stage_obj = next((s for s in fow_main_stages if not s["completed"]), fow_main_stages[-1] if fow_main_stages else None)
        all_main_done = bool(
            climax.get("completed")
            or climax.get("boss_defeated")
            or (fow_main_stages and all(s["completed"] for s in fow_main_stages))
        )
        main_title = sanitize_dossier_prose(
            str(climax.get("main_objective_text") or climax.get("label") or quest.get("objective") or quest.get("title") or "")
        )
        main_objective = {
            "id": 0,
            "is_optional": False,
            "title": main_title,
            "text": main_title,
            "stages": fow_main_stages,
            "current_stage": int(cur_stage_obj["stage_index"]) if cur_stage_obj else 1,
            "total_stages": len(fow_main_stages),
            "completed_stages": sum(1 for s in fow_main_stages if s["completed"]),
            "completed": all_main_done,
            "aid_dc_reduction": int(climax.get("aid_dc_reduction") or 0),
            "bypass_unlocked": bool(climax.get("bypass_unlocked")),
        }

    suspect_pool: List[str] = []
    cb = dos.get("cast_bindings") or {}
    if reveal_all or climax_unlocked or twist_visible:
        for r_key in ("target", "accomplice", "client", "informant"):
            nm = (cb.get(r_key) or {}).get("name") if isinstance(cb.get(r_key), dict) else ""
            if nm and nm not in suspect_pool:
                suspect_pool.append(str(nm))
    else:
        known_npcs = set()
        client_nm = (cb.get("client") or {}).get("name") if isinstance(cb.get("client"), dict) else ""
        if client_nm:
            known_npcs.add(str(client_nm).strip().lower())
        for c in (db.get_session_clues(session_id) or []):
            if c.get("linked_npc"):
                known_npcs.add(str(c["linked_npc"]).strip().lower())
        for ld in raw_leads:
            if ld.get("is_discovered", True) and (
                ld.get("status") in ("unlocked", "active", "completed") or ld.get("roster_cleared")
            ):
                tn = ld.get("target_npc")
                if tn:
                    known_npcs.add(str(tn).strip().lower())
        for r_key in ("client", "informant", "target", "accomplice"):
            nm = (cb.get(r_key) or {}).get("name") if isinstance(cb.get(r_key), dict) else ""
            if nm and (r_key == "client" or str(nm).strip().lower() in known_npcs) and nm not in suspect_pool:
                suspect_pool.append(str(nm))

    return {
        "dossier_stage": "compiled",
        "has_structured_objectives": has_structured,
        "is_peak_chapter": bool(climax.get("is_peak_chapter")),
        "engine": dos.get("engine") or "",
        "family_tier": dos.get("family_tier") or "bounty",
        "danger_tier": int(dos.get("danger_tier") or 1),
        "alert_level": int(dos.get("alert_level") or 0),
        "max_alert": int(dos.get("max_alert") or 4),
        "engaged_flag": int(dos.get("engaged_flag") or 0),
        "rescue_shield_used": int(dos.get("rescue_shield_used") or 0),
        "outcome_tier": dos.get("outcome_tier") or "",
        "main_objective": main_objective,
        "optional_objectives": optional_objectives,
        "leads": visible_leads,
        "climax": {
            "gate_type": climax.get("gate_type") or "open",
            "is_unlocked": climax_unlocked,
            "location": climax.get("location") if climax_unlocked else "Hidden Lair (Uncover Leads / Caseboard)",
            "true_culprit": climax.get("true_culprit") if climax_unlocked else "",
            "has_boss_encounter": climax.get("boss_sheet") is not None,
            "boss_name": sanitize_dossier_prose(str((climax.get("boss_sheet") or {}).get("name") or "")) if climax_unlocked and climax.get("boss_sheet") else "",
            "reinforcements_count": len(climax.get("reinforcements") or []),
            "aid_dc_reduction": int(climax.get("aid_dc_reduction") or 0),
            "bypass_unlocked": bool(climax.get("bypass_unlocked")),
        },
        "twist": (
            {
                "is_discovered": True,
                "twist_type": twist.get("twist_type"),
                "summary": sanitize_dossier_prose(str(twist.get("summary") or "")),
                "side_switch_available": bool(twist.get("side_switch_available")),
                "blackmail_available": bool(twist.get("blackmail_available")),
            }
            if twist_visible
            else {"is_discovered": False}
        ),
        "tangible_item": (
            {
                "has_item": True,
                "name": sanitize_dossier_prose(str(t_item.get("name") or "")),
                "disposition": t_item.get("disposition"),
                "is_quest_locked": int(t_item.get("is_quest_locked") or 0),
                "fencing_gold": int(t_item.get("fencing_gold") or 0),
            }
            if t_item.get("has_item")
            else {"has_item": False}
        ),
        "turn_in_rules": t_rules,
        "contract_economy": {
            "base_gold": int(econ.get("base_gold") or quest.get("reward_gold") or 0),
            "advance_taken": bool(econ.get("advance_taken")),
            "upfront_advance_gold": int(econ.get("upfront_advance_gold") or 0),
            "bribes_spent_gold": int(econ.get("bribes_spent_gold") or 0),
        },
        "suspect_pool": suspect_pool,
        "clue_pair_hints_available": len(dos.get("clue_graph") or []) >= 2,
    }


def build_fog_of_war_quest_prompt_block(
    session_id: int,
    session: Optional[Dict[str, Any]] = None,
    in_intimate_scene: bool = False,
) -> str:
    """
    Builds a compact, stat-leak-free narrator context block for active `QuestDossier` & `CampaignSpine`.
    Strictly suppresses mid-act waypoint reminders during intimate acts (`in_intimate_scene=True`).
    """
    if not session_id or in_intimate_scene:
        return ""

    lines: List[str] = []
    spine = db.get_campaign_spine(session_id)
    cur_ch = int(db.get_session_chapter(session_id) or 1)
    if spine:
        ch_bp = (spine.get("chapters_blueprint") or {}).get(str(cur_ch)) or {}
        pacing = sanitize_dossier_prose(str(ch_bp.get("pacing_directive") or ""))
        peak_tag = " [PEAK SET-PIECE CHAPTER]" if ch_bp.get("is_peak") else ""
        if pacing:
            lines.append(f"[CAMPAIGN CHAPTER {cur_ch}{peak_tag} FOCUS]: {pacing}")

    for q in (db.get_session_quests(session_id, status="Active") or [])[:4]:
        dos = q.get("dossier")
        if not dos or dos.get("status_stage") != "compiled":
            continue
        if dos.get("engine") == "INTIMATE_LIAISON" and in_intimate_scene:
            continue
        fow = build_fog_of_war_quest_payload(session_id, q, dossier=dos, reveal_all=False)
        if fow.get("has_structured_objectives") and fow.get("main_objective"):
            mo = fow["main_objective"]
            cur_st_lbl = next(
                (s["stage_label"] for s in (mo.get("stages") or []) if not s.get("completed")),
                mo.get("title") or "Final resolution",
            )
            disc_opts = [
                f"{opt['title']} [{str(opt.get('role') or 'aid').upper()}]"
                for opt in (fow.get("optional_objectives") or [])
                if opt.get("status") == "active"
            ]
            opt_part = f" | Optional Routes: {'; '.join(disc_opts[:2])}" if disc_opts else ""
            twist_note = f" | Uncovered Twist: {fow['twist']['summary']}" if (fow.get("twist") or {}).get("is_discovered") else ""
            lines.append(
                f"- {sanitize_dossier_prose(q.get('title', 'Contract'))} "
                f"(Main {mo.get('current_stage', 1)}/{mo.get('total_stages', 2)}: {cur_st_lbl}{opt_part}{twist_note})"
            )
        else:
            active_titles = [ld["title"] for ld in (fow.get("leads") or []) if ld.get("status") == "active"]
            lead_summary = "; ".join(active_titles[:2]) if active_titles else "Ready for final resolution"
            twist_note = f" | Uncovered Twist: {fow['twist']['summary']}" if (fow.get("twist") or {}).get("is_discovered") else ""
            lines.append(
                f"- {sanitize_dossier_prose(q.get('title', 'Contract'))} ({dos.get('engine')}): {lead_summary}{twist_note}"
            )

    return "\n".join(lines)
