from __future__ import annotations

import json
import random
import re
import db
import game_engine
import scenario_data
from typing import Any, Optional
from contextlib import nullcontext
from db import adb
from game_engine.core import is_nsfw_scenario
from game_engine.turn_context import TurnExecutionContext
from .dialogue import _build_dialogue_prompt_block
from .encounter_narrative import _get_enemy_base_name, _infer_incursion_action_from_label
from .generation import log
from .prompts import _build_history_context, _build_player_actions_text, _build_quest_and_bounty_directives
from mechanics.world.locations import extract_movement_destination, get_primary_location_name, get_zone_location_name, is_hub_location, parse_tiered_location

_PRE_TURN_EXPORT_KEYS: tuple[str, ...] = ('_anom_domain_res', '_in_aftercare_for_core', '_in_intimate_for_core', '_pre_turn_dialogue_partners', '_pre_turn_incursion_notice', '_pre_turn_site_items_by_uid', '_pre_turn_sleep_info', '_pre_turn_time_info', '_staged_domain_vitals', '_staged_time_op', '_we_snap', 'actions_text', 'active_quests_str', 'active_recall_blocks', 'ambush_monsters', 'ambush_triggered', 'budget', 'calculate_action_time_cost', 'caseboard_block', 'cast_plan', 'ctx', 'dialogue_prompt_block', 'directive_note', 'effective_location', 'fow_dossier_block', 'has_exited_convo', 'hist_text', 'hs_turn_events', 'is_in_combat', 'is_sleep_action', 'mode', 'new_partners', 'phys_prompt_block', 'pre_intimate_res', 'pre_quest_res', 'pre_social_res', 'pre_turn_enemy_names', 'pre_turn_stage_npcs', 'pre_vitals_res', 'precomputed', 'raw_scene_ctx', 'scen_key', 'scene_loc', 'scene_npcs_for_prompt', 'session_id_val', 'simultaneity_note', 'stage_info', 'time_prompt_block', 'world_bundle', 'wp_block')


async def run_pre_turn_phase(
    session: dict,
    party: list,
    actions: list,
    *,
    is_retry: bool = False,
    ctx: Optional[TurnExecutionContext] = None,
) -> dict[str, Any]:
    from mechanics.system.time_engine import format_llm_time_context, calculate_action_time_cost, is_sleep_action
    session_id_val = session.get('id')
    if ctx is None:
        if session_id_val:
            ctx = await adb(TurnExecutionContext.load_snapshot, session_id_val, session, party, actions)
        else:
            ctx = TurnExecutionContext(session_id_val, session, party=party, actions=actions)
    elif session_id_val and "world_bundle" not in ctx._cache:
        await adb(ctx.hydrate_snapshot)
    if isinstance(session, dict):
        session["_ctx"] = ctx

    pre_turn_enemy_names = {
        _get_enemy_base_name(m.get("name", "")).lower()
        for m in (session.get("nearby_enemies") or [])
        if isinstance(m, dict) and m.get("hp", 1) > 0 and m.get("name")
    }

    actions_text = _build_player_actions_text(actions, session=session)

    # Pre-turn deterministic causal pipeline (D3):
    # Spatial/Dijkstra runs FIRST inside compute_pre_turn_stage, then _stage_clock_after_movement
    # computes the exact clock advancement in memory WITHOUT mutating SQLite before the LLM finishes!
    _pre_turn_sleep_info = None
    _pre_turn_time_info = None
    _staged_time_op = None
    scen_key = session.get("scenario", "fantasy") if isinstance(session, dict) else "fantasy"

    prev_day = int(session.get("current_day", 1) or 1) if isinstance(session, dict) else 1
    prev_min = int(session.get("current_minute", 480) or 480) if isinstance(session, dict) else 480
    party_uids: list = []
    if not is_retry:
        if session_id_val:
            try:
                prev_day, prev_min, _ = await db.adb(db.get_session_time, session_id_val)
            except Exception:
                prev_day = int(session.get("current_day", 1) or 1)
                prev_min = int(session.get("current_minute", 480) or 480)
        else:
            prev_day = int(session.get("current_day", 1) or 1)
            prev_min = int(session.get("current_minute", 480) or 480)

        session["_prev_turn_day"] = prev_day
        session["_prev_turn_minute"] = prev_min
        ctx.clock.prev_turn_day = prev_day
        ctx.clock.prev_turn_minute = prev_min

        party_uids = []
        for char in (party or []):
            if isinstance(char, dict) and "user_id" in char:
                party_uids.append(char["user_id"])
            elif isinstance(char, (tuple, list)) and char and isinstance(char[0], dict) and "user_id" in char[0]:
                party_uids.append(char[0]["user_id"])

        def _stage_clock_after_movement(
            is_movement: bool = False,
            effective_location: str = "",
            travel_minutes: int | None = None,
            blocked_invalid_exit: bool = False,
        ) -> None:
            nonlocal _pre_turn_sleep_info, _pre_turn_time_info, _staged_time_op
            from mechanics.system.time_engine import (
                get_location_sleep_context,
                is_nap_action,
                format_clock,
                get_day_of_week,
            )
            from mechanics.world.world_schedule import get_scenario_wake_minute

            first_act = actions[0] if actions else {}
            first_lbl = str(first_act.get("label") or "") if isinstance(first_act, dict) else str(first_act)
            explicit_skip = max(
                [int((a.get("skip_minutes") or 0) if isinstance(a, dict) else 0) for a in (actions or [])] or [0]
            )
            sleep_mode = ""
            for a_sm in (actions or []):
                if isinstance(a_sm, dict) and a_sm.get("sleep_mode"):
                    sleep_mode = str(a_sm["sleep_mode"]).lower()
                    break

            curr_loc_str = effective_location or session.get("current_location", "")
            sleep_ctx = get_location_sleep_context(
                curr_loc_str,
                props=session.get("physical_state", {}).get("props") if isinstance(session.get("physical_state"), dict) else None,
                scenario=scen_key,
                session_id=session_id_val,
            )

            is_sleep = any(is_sleep_action(a.get("label", "") if isinstance(a, dict) else str(a)) for a in (actions or [])) or sleep_mode == "sleep"
            is_nap, nap_dur = is_nap_action(first_lbl)
            if sleep_mode == "nap" and explicit_skip > 0:
                is_nap, nap_dur = True, explicit_skip

            if not session_id_val:
                if is_sleep:
                    session["current_day"] = prev_day + 1
                    session["current_minute"] = 420
                else:
                    time_delta = 0 if blocked_invalid_exit else (
                        max(0, int(travel_minutes))
                        if (is_movement and travel_minutes is not None)
                        else calculate_action_time_cost(
                            first_act,
                            scen_key=scen_key,
                            old_loc=session.get("current_location", ""),
                            new_loc=curr_loc_str,
                            is_dialogue=False,
                            is_combat=False,
                            session_id=0,
                        )
                    )
                    session["current_day"] = prev_day + ((prev_min + time_delta) // 1440)
                    session["current_minute"] = (prev_min + time_delta) % 1440
                return

            if is_sleep:
                wake_m = int(get_scenario_wake_minute(scen_key))
                if sleep_ctx.get("can_sleep", False):
                    rec_ratio = float(sleep_ctx.get("recovery_ratio", 1.0))
                    new_day = prev_day + 1 if prev_min >= wake_m else prev_day
                    new_min = wake_m
                    surf_lbl = sleep_ctx.get("surface_label", "Bed")
                    _staged_time_op = {
                        "op": "sleep",
                        "scen_key": scen_key,
                        "recovery_ratio": rec_ratio,
                        "surface_label": surf_lbl,
                        "party_uids": party_uids,
                    }
                    _pre_turn_sleep_info = {
                        "session_id": session_id_val,
                        "new_day": new_day,
                        "new_minute": new_min,
                        "clock_display": format_clock(new_min),
                        "day_name": get_day_of_week(new_day),
                        "fatigue_cleared": [],
                        "hp_restored": True,
                        "mp_restored": True,
                        "recovery_ratio": rec_ratio,
                        "surface_label": surf_lbl,
                    }
                    session["current_day"] = new_day
                    session["current_minute"] = new_min
                else:
                    wait_minutes = (wake_m - prev_min) if wake_m > prev_min else (1440 - prev_min + wake_m)
                    new_day = prev_day + ((prev_min + wait_minutes) // 1440)
                    new_min = (prev_min + wait_minutes) % 1440
                    _staged_time_op = {"op": "advance", "delta_minutes": wait_minutes, "party_uids": party_uids}
                    _pre_turn_time_info = {
                        "session_id": session_id_val,
                        "old_day": prev_day,
                        "new_day": new_day,
                        "old_minute": prev_min,
                        "new_minute": new_min,
                        "days_elapsed": new_day - prev_day,
                        "minutes_elapsed": wait_minutes,
                        "day_rolled_over": new_day > prev_day,
                        "fatigue_applied": [],
                    }
                    session["current_day"] = new_day
                    session["current_minute"] = new_min
            elif is_nap:
                new_day = prev_day + ((prev_min + nap_dur) // 1440)
                new_min = (prev_min + nap_dur) % 1440
                if sleep_ctx.get("can_sleep", False):
                    rec_ratio = float(sleep_ctx.get("recovery_ratio", 1.0))
                    surf_lbl = sleep_ctx.get("surface_label", "Bed")
                    _staged_time_op = {
                        "op": "nap",
                        "nap_minutes": nap_dur,
                        "recovery_ratio": rec_ratio,
                        "surface_label": surf_lbl,
                        "party_uids": party_uids,
                    }
                    _pre_turn_sleep_info = {
                        "session_id": session_id_val,
                        "new_day": new_day,
                        "new_minute": new_min,
                        "clock_display": format_clock(new_min),
                        "day_name": get_day_of_week(new_day),
                        "nap_minutes": nap_dur,
                        "recovery_ratio": rec_ratio,
                        "surface_label": surf_lbl,
                    }
                else:
                    _staged_time_op = {"op": "advance", "delta_minutes": nap_dur, "party_uids": party_uids}
                    _pre_turn_time_info = {
                        "session_id": session_id_val,
                        "old_day": prev_day,
                        "new_day": new_day,
                        "old_minute": prev_min,
                        "new_minute": new_min,
                        "days_elapsed": new_day - prev_day,
                        "minutes_elapsed": nap_dur,
                        "day_rolled_over": new_day > prev_day,
                        "fatigue_applied": [],
                    }
                session["current_day"] = new_day
                session["current_minute"] = new_min
            elif explicit_skip > 0 or sleep_mode == "wait":
                skip_m = explicit_skip if explicit_skip > 0 else 60
                new_day = prev_day + ((prev_min + skip_m) // 1440)
                new_min = (prev_min + skip_m) % 1440
                _staged_time_op = {"op": "advance", "delta_minutes": skip_m, "party_uids": party_uids}
                _pre_turn_time_info = {
                    "session_id": session_id_val,
                    "old_day": prev_day,
                    "new_day": new_day,
                    "old_minute": prev_min,
                    "new_minute": new_min,
                    "days_elapsed": new_day - prev_day,
                    "minutes_elapsed": skip_m,
                    "day_rolled_over": new_day > prev_day,
                    "fatigue_applied": [],
                }
                session["current_day"] = new_day
                session["current_minute"] = new_min
            else:
                from mechanics.world.mobility import get_session_dialogue_partners
                from mechanics.combat import is_in_combat
                is_dialogue_active = bool(get_session_dialogue_partners(session))
                is_combat_active = bool(is_in_combat(session))
                old_loc_val = session.get("current_location", "")
                if blocked_invalid_exit:
                    time_delta = 0
                elif is_movement and travel_minutes is not None:
                    time_delta = max(0, int(travel_minutes))
                else:
                    time_delta = calculate_action_time_cost(
                        first_act,
                        scen_key=scen_key,
                        old_loc=old_loc_val,
                        new_loc=curr_loc_str,
                        is_dialogue=is_dialogue_active,
                        is_combat=is_combat_active,
                        session_id=session_id_val,
                    )
                new_day = prev_day + ((prev_min + time_delta) // 1440)
                new_min = (prev_min + time_delta) % 1440
                _staged_time_op = {"op": "advance", "delta_minutes": time_delta, "party_uids": party_uids}
                _pre_turn_time_info = {
                    "session_id": session_id_val,
                    "old_day": prev_day,
                    "new_day": new_day,
                    "old_minute": prev_min,
                    "new_minute": new_min,
                    "days_elapsed": new_day - prev_day,
                    "minutes_elapsed": time_delta,
                    "day_rolled_over": new_day > prev_day,
                    "fatigue_applied": [],
                }
                session["current_day"] = new_day
                session["current_minute"] = new_min

            if _staged_time_op is not None:
                session["_staged_time_op"] = _staged_time_op
                ctx.clock.staged_time_op = _staged_time_op
    else:
        _stage_clock_after_movement = None

    from game_engine.npcs import compute_pre_turn_stage
    from mechanics.combat import is_in_combat
    from game_engine.npcs.cast_planner import plan_pre_turn, render_stage_plan

    def _run_pre_turn_stage_and_cast_bundle() -> tuple[dict, Any]:
        nonlocal _pre_turn_sleep_info, _staged_time_op, _pre_turn_time_info
        _st = compute_pre_turn_stage(
            session,
            actions,
            party=party,
            ctx=ctx,
            persist_db=False,
            stage_clock_cb=_stage_clock_after_movement,
        )
        if (_st.get("pending_folklore_ops") or {}).get("treaty_violation_village") and not is_retry:
            exp_new_day = prev_day + ((prev_min + 30) // 1440)
            exp_new_min = (prev_min + 30) % 1440
            session["current_day"] = exp_new_day
            session["current_minute"] = exp_new_min
            if session_id_val:
                _pre_turn_sleep_info = None
                _staged_time_op = {"op": "advance", "delta_minutes": 30, "party_uids": party_uids}
                _pre_turn_time_info = {
                    "session_id": session_id_val,
                    "old_day": prev_day,
                    "new_day": exp_new_day,
                    "old_minute": prev_min,
                    "new_minute": exp_new_min,
                    "days_elapsed": exp_new_day - prev_day,
                    "minutes_elapsed": 30,
                    "day_rolled_over": exp_new_day > prev_day,
                    "fatigue_applied": [],
                }
                session["_staged_time_op"] = _staged_time_op
                ctx.clock.staged_time_op = _staged_time_op
        _cp = plan_pre_turn(
            session,
            party,
            actions,
            stage_info=_st,
            is_combat=bool(is_in_combat(session)),
            new_loc=_st["effective_location"],
            persist_db=False,
        )
        return _st, _cp

    stage_info, cast_plan = await adb(_run_pre_turn_stage_and_cast_bundle)
    new_partners = stage_info["new_partners"]
    has_exited_convo = stage_info["has_exited_convo"]
    effective_location = stage_info["effective_location"]
    pre_turn_stage_npcs = stage_info["stage_npcs"]
    movement_dest_str = stage_info["movement_dest_str"]
    new_partners = cast_plan.dialogue_partners
    if cast_plan.has_exited_convo:
        has_exited_convo = True

    from mechanics.world.mobility import get_session_dialogue_partners
    from mechanics.social.physical_state import (
        build_physical_prompt_block,
        is_erotic_intimate_contact as _core_is_erotic,
        detect_intimate_disengagement as _core_is_disengage,
    )
    from mechanics.social.intimate_excitement import classify_intimate_act as _core_classify_act

    _pre_phys = ((await adb(db.get_session_physical_state, session.get("id"))) if session.get("id") else None) or session.get("physical_state") or {}
    _pre_ic_str = str(_pre_phys.get("intimate_contact", "") if isinstance(_pre_phys, dict) else "")
    _cand_core_partners = list(new_partners or [])
    for _existing_dp in get_session_dialogue_partners(session):
        if _existing_dp and _existing_dp not in _cand_core_partners:
            _cand_core_partners.append(_existing_dp)
    if not _cand_core_partners:
        _cand_core_partners = ["Partner"]

    _EROTIC_SUB_INTENTS_CORE = {
        "intercourse", "oral_give", "oral_receive", "oral_mutual",
        "manual_give", "manual_receive", "manual_mutual",
        "anal_give", "anal_receive", "anal_mutual",
    }
    _initiating_erotic_act = False
    _has_redress_or_aftercare_act = False
    for _pa in (actions or []):
        if not isinstance(_pa, dict):
            continue
        _pchk = _pa.get("check")
        _ptier = getattr(_pchk, "tier", None) or (_pchk.get("tier") if isinstance(_pchk, dict) else None)
        _pa_ok = not (_pa.get("success") is False or _ptier in ("fail", "crit_fail"))
        _pa_ri = _pa.get("resolved_intent") if isinstance(_pa.get("resolved_intent"), dict) else {}
        _pa_sub = str(_pa_ri.get("sub_intent") or _pa.get("sub_intent") or "").lower().strip()
        _pa_int = str(_pa_ri.get("intent") or _pa.get("intent") or "").lower().strip()
        if _pa_sub in ("aftercare", "redress"):
            _has_redress_or_aftercare_act = True
        if not _pa_ok:
            continue
        if _pa_sub in _EROTIC_SUB_INTENTS_CORE or (_pa_int == "intimate_act" and _pa_sub not in ("kiss", "foreplay", "aftercare", "redress", "")):
            _initiating_erotic_act = True
            break
        if not _pa_sub and not _pa_int:
            _pa_lbl = str(_pa.get("label") or "")
            if _pa_lbl:
                for _cp_cand in _cand_core_partners:
                    if _core_classify_act(_pa_lbl, intimate_contact_str=_pre_ic_str, partner_name=_cp_cand).get("act_type", "none") not in ("none", "foreplay_nongenital"):
                        _initiating_erotic_act = True
                        break
            if _initiating_erotic_act:
                break

    _in_intimate_for_core = (
        not _core_is_disengage(actions)
        and (_core_is_erotic(_pre_ic_str) or _initiating_erotic_act)
    )
    _should_run_pre_intimacy = bool(
        _in_intimate_for_core
        or _core_is_erotic(_pre_ic_str)
        or _has_redress_or_aftercare_act
    )
    _in_aftercare_for_core = (not _core_is_disengage(actions)) and ("aftercare" in _pre_ic_str.lower() or _has_redress_or_aftercare_act)

    simultaneity_note = ""
    if len(actions) > 1:
        simultaneity_note = (
            "\nThese actions happened AT THE SAME TIME, not in sequence. Decide "
            "whether they synergize (e.g. a flanking attack plus a distraction "
            "compound for a better result), conflict/waste each other (e.g. one "
            "blocks the other's approach), or are simply independent -- and let "
            "that shape how the actions play out across `@@OUTCOME` and `@@NEXT`.\n"
        )

    active_quests_str = ""
    if not _in_intimate_for_core and not _in_aftercare_for_core:
        story_quest_context, side_bounties_context = _build_quest_and_bounty_directives(session, ctx, include_fow=False)
        if story_quest_context.strip():
            active_quests_str += f"### PRIMARY STORY QUEST\n{story_quest_context}\n\n"
        if side_bounties_context.strip():
            active_quests_str += f"### SECONDARY SIDE BOUNTIES\n{side_bounties_context}\n\n"
        if active_quests_str:
            active_quests_str += "[QUEST PRESENCE NOTE: Characters mentioned in the above quests or bounties are NOT necessarily in the current room. Do NOT include them in the scene or dialogue unless they are explicitly listed in `NPCs currently present` or actively introduced.]\n\n"

    from mechanics.combat import is_in_combat, precompute_combat_turn
    _pre_turn_incursion_notice = ""
    _pre_turn_incursion_directive = ""
    _skip_precompute_for_incursion = False
    _pre_turn_site_items_by_uid: dict[int, list[str]] = {}
    if scenario_data.is_anomalous_incursions_scenario(session.get("scenario", "")) and actions and session.get("id"):
        first_inc_act = actions[0] if isinstance(actions[0], dict) else {}
        inc_lbl_low = str(first_inc_act.get("label") or "").strip().lower()
        inc_action_key = str(first_inc_act.get("incursion_action") or "").strip().lower()
        is_inc_tagged = bool(
            first_inc_act.get("incursion_id")
            or first_inc_act.get("intent") == "anomalous_incursion_action"
            or "(optional)" in inc_lbl_low
        )
        has_subdue_enemy_now = any(
            isinstance(e, dict)
            and (e.get("requires_non_lethal_subdue") or e.get("is_anomalous_manifestation"))
            and e.get("hp", 0) > 0
            for e in (session.get("nearby_enemies") or [])
        )
        if not inc_action_key:
            inc_action_key = _infer_incursion_action_from_label(
                inc_lbl_low,
                is_inc_tagged=is_inc_tagged,
                has_subdue_enemy_now=has_subdue_enemy_now,
                first_inc_act=first_inc_act,
            )
            if not inc_action_key and session.get("dialogue_partner"):
                _cand_freeform = str(
                    first_inc_act.get("raw_text")
                    or ("" if first_inc_act.get("_server_stamped") else (first_inc_act.get("text") or first_inc_act.get("label") or ""))
                ).strip()
                if _cand_freeform:
                    try:
                        from mechanics.world.anomalous_events import _resolve_active_non_hostile_anomaly_context
                        from mechanics.world.folklore_mechanics import has_active_dialogue_trap, evaluate_dialogue_trap_response
                        _dp_ctx = _resolve_active_non_hostile_anomaly_context(
                            int(session["id"]),
                            session=session,
                            entity_name=str(session.get("dialogue_partner") or ""),
                        )
                        if _dp_ctx and has_active_dialogue_trap(_dp_ctx.get("blueprint")):
                            if evaluate_dialogue_trap_response(_dp_ctx.get("blueprint"), player_text=_cand_freeform).get("matched"):
                                inc_action_key = "question_trap_freeform"
                    except Exception:
                        pass
        site_action_key = str(first_inc_act.get("site_action") or "").strip().lower()
        if first_inc_act.get("intent") == "anomalous_site_action" and site_action_key in ("puzzle_step", "harvest", "overdraw"):
            try:
                from mechanics.world.anomalous_sites import (
                    resolve_anomalous_site_puzzle_step,
                    resolve_site_harvest_action,
                )
                party_uids_s = [uid for uid in party_uids if uid]
                lead_s_uid = party_uids_s[0] if party_uids_s else session.get("host_user_id")
                site_id_s = str(first_inc_act.get("site_id") or session.get("current_node_id") or "").strip()
                turn_num_s = len(session.get("history") or []) + 1
                scen_s = str(session.get("scenario") or "anomalous_incursions")
                chk_s = first_inc_act.get("check") or first_inc_act.get("check_result")
                if site_action_key == "puzzle_step":
                    site_res = await adb(
                        resolve_anomalous_site_puzzle_step,
                        int(session["id"]),
                        int(lead_s_uid or 1),
                        site_id_s,
                        step_index=first_inc_act.get("step_index"),
                        stat_used=str(first_inc_act.get("stat") or ""),
                        pre_rolled_check=chk_s,
                        use_ward=bool(first_inc_act.get("use_ward")),
                        ward_item_name=str(first_inc_act.get("ward_item_name") or ""),
                        session=session,
                        party=party,
                        scen_key=scen_s,
                        turn_number=turn_num_s,
                    )
                else:
                    site_res = await adb(
                        resolve_site_harvest_action,
                        int(session["id"]),
                        int(lead_s_uid or 1),
                        site_id_s,
                        mode=site_action_key,
                        pre_rolled_check=chk_s,
                        scen_key=scen_s,
                        turn_number=turn_num_s,
                    )
                fresh_site_sess = await adb(db.get_session, int(session["id"])) or {}
                session["nearby_enemies"] = fresh_site_sess.get("nearby_enemies", [])
                if lead_s_uid:
                    fresh_lead_char = await adb(db.get_character, int(lead_s_uid))
                    if isinstance(fresh_lead_char, dict) and party and isinstance(party[0], (tuple, list)) and isinstance(party[0][0], dict):
                        party[0][0].update(fresh_lead_char)
                if site_res.get("items_gained_names") and lead_s_uid:
                    _pre_turn_site_items_by_uid.setdefault(int(lead_s_uid), []).extend(
                        str(x) for x in site_res["items_gained_names"] if x
                    )
                if site_res.get("composure_shift") and isinstance(session.get("physical_state"), dict):
                    _p_actors_s = session["physical_state"].get("actors")
                    if isinstance(_p_actors_s, dict) and isinstance(_p_actors_s.get("player"), dict):
                        _p_actors_s["player"]["composure"] = site_res["composure_shift"]
                if site_res.get("directive"):
                    _pre_turn_incursion_directive = str(site_res["directive"])
                if site_res.get("message"):
                    _pre_turn_incursion_notice = str(site_res["message"])
                if site_res.get("combat_started") or site_res.get("resolved") or site_res.get("pacified"):
                    _skip_precompute_for_incursion = True
            except Exception as _site_err:
                log.warning("Failed pre-turn anomalous site action: %s", _site_err)
        elif inc_action_key:
            try:
                from mechanics.world.anomalous_events import (
                    resolve_non_hostile_incursion_action,
                    resolve_anomalous_combat_containment,
                    resolve_anomaly_dialogue_inquiry,
                )
                party_uids_inc = [uid for uid in party_uids if uid]
                lead_inc_uid = party_uids_inc[0] if party_uids_inc else session.get("host_user_id")
                _freeform_inc_txt = str(
                    first_inc_act.get("raw_text")
                    or ("" if first_inc_act.get("_server_stamped") else (first_inc_act.get("text") or first_inc_act.get("label") or ""))
                ).strip()
                if inc_action_key.startswith(("anomaly_inquiry", "anomaly_pattern", "question_trap")) or inc_action_key in ("converse", "study_pattern"):
                    inc_res = await adb(
                        resolve_anomaly_dialogue_inquiry,
                        session_id=int(session["id"]),
                        entity_name=str(first_inc_act.get("target_npc") or session.get("dialogue_partner") or ""),
                        quest_id=str(first_inc_act.get("quest_id") or ""),
                        sub_obj_id=first_inc_act.get("sub_obj_id"),
                        incursion_id=str(first_inc_act.get("incursion_id") or ""),
                        breach_id=str(first_inc_act.get("breach_id") or first_inc_act.get("incursion_id") or ""),
                        inquiry_type=inc_action_key,
                        player_text=_freeform_inc_txt,
                        user_id=lead_inc_uid,
                        session=session,
                    )
                elif (
                    inc_action_key in ("subdue", "combat_persuade", "sever_tether", "invoke_patron_authority", "accept_boss_pact_surrender")
                    or (inc_action_key == "folklore_offering_rite" and has_subdue_enemy_now)
                ):
                    inc_res = await adb(
                        resolve_anomalous_combat_containment,
                        session_id=int(session["id"]),
                        user_id=lead_inc_uid,
                        action_type=inc_action_key,
                        incursion_id=str(first_inc_act.get("incursion_id") or ""),
                        quest_id=str(first_inc_act.get("quest_id") or ""),
                        pre_rolled_check=first_inc_act.get("check"),
                        party_user_ids=party_uids_inc,
                    )
                else:
                    inc_res = await adb(
                        resolve_non_hostile_incursion_action,
                        session_id=int(session["id"]),
                        incursion_id=str(first_inc_act.get("incursion_id") or ""),
                        user_id=lead_inc_uid,
                        action_type=inc_action_key,
                        stat_used=str(first_inc_act.get("stat") or ""),
                        pre_rolled_check=first_inc_act.get("check"),
                        player_text=_freeform_inc_txt,
                    )
                fresh_inc_sess = await adb(db.get_session, int(session["id"])) or {}
                session["nearby_enemies"] = fresh_inc_sess.get("nearby_enemies", [])
                session["current_npcs"] = fresh_inc_sess.get("current_npcs", session.get("current_npcs", []))
                session["daily_incursions"] = fresh_inc_sess.get("daily_incursions", session.get("daily_incursions", []))
                session["daily_breaches"] = fresh_inc_sess.get("daily_breaches", session.get("daily_breaches", []))
                _unmasked_prev = str(inc_res.get("unmasked_from") or "").strip()
                if _unmasked_prev:
                    _um_low = _unmasked_prev.lower()
                    new_partners[:] = [p for p in new_partners if str(p or "").strip().lower() != _um_low]
                    if cast_plan is not None:
                        cast_plan.dialogue_partners = [p for p in cast_plan.dialogue_partners if str(p or "").strip().lower() != _um_low]
                        cast_plan.present_npcs = [p for p in cast_plan.present_npcs if str(p or "").strip().lower() != _um_low]
                if inc_res.get("dialogue_partner"):
                    dp_anom = str(inc_res["dialogue_partner"]).strip()
                    session["dialogue_partner"] = dp_anom
                    session["dialogue_partners"] = [dp_anom]
                    if dp_anom not in new_partners:
                        new_partners.append(dp_anom)
                    if cast_plan is not None and dp_anom not in cast_plan.dialogue_partners:
                        cast_plan.dialogue_partners.append(dp_anom)
                elif inc_res.get("resolved") or inc_res.get("combat_started") or inc_res.get("escaped") or fresh_inc_sess.get("dialogue_partner") is None:
                    if not fresh_inc_sess.get("dialogue_partner"):
                        _prev_dp = str(session.get("dialogue_partner") or "").strip().lower()
                        session["dialogue_partner"] = None
                        session["dialogue_partners"] = []
                        if _prev_dp:
                            new_partners[:] = [p for p in new_partners if str(p or "").strip().lower() != _prev_dp]
                            if cast_plan is not None:
                                cast_plan.dialogue_partners = [p for p in cast_plan.dialogue_partners if str(p or "").strip().lower() != _prev_dp]
                                cast_plan.present_npcs = [p for p in cast_plan.present_npcs if str(p or "").strip().lower() != _prev_dp]
                if inc_res.get("directive"):
                    _pre_turn_incursion_directive = str(inc_res["directive"])
                if inc_res.get("message"):
                    _pre_turn_incursion_notice = str(inc_res["message"])
                    if not _pre_turn_incursion_directive:
                        _clean_inc_msg = re.sub(r"\s*\([A-Z]{3}(?:\s+check)?\s+\d+\s+vs\s+DC\s+\d+[^)]*\)", "", str(inc_res["message"]))
                        _clean_inc_msg = re.sub(r"<=\s*\d+%\s*HP", "critically weakened", _clean_inc_msg)
                        _clean_inc_msg = re.sub(r"\(?\b\d+\s*/\s*\d+\s*HP\b\)?", "", _clean_inc_msg)
                        _clean_inc_msg = re.sub(r"\(\s*[^()]*?[+-]\d+\s*(?:DC|HP|MP|XP|G)\b[^()]*\)", "", _clean_inc_msg)
                        _pre_turn_incursion_directive = (
                            f"[ANOMALOUS CONTAINMENT OUTCOME DIRECTIVE]:\n"
                            f"- {_clean_inc_msg}\n"
                            f"- Narrate this containment/engagement outcome vividly in `outcome_narrative` and `next_narrative`.\n"
                            f"- Do NOT echo raw DC integers, roll totals, or HP percentages in narrative prose."
                        )
                if inc_res.get("combat_started") or inc_res.get("subdued") or inc_res.get("resolved"):
                    _skip_precompute_for_incursion = True
                    if inc_res.get("subdued") or inc_res.get("resolved"):
                        try:
                            from mechanics.combat import cleanup_anomalous_combat_session_state
                            cleanup_anomalous_combat_session_state(session)
                        except Exception:
                            pass
                elif inc_res.get("combat_continues") and isinstance(first_inc_act, dict):
                    # Non-damage containment turn (Persuade/Calm/Tether/Rite or premature Subdue): enemy still acts,
                    # but the player deals no lethal damage. Only FAILED attempts are stamped as a failed tier
                    # (which grants the enemy its accuracy punish); a successful mid-combat tether seal stays a success.
                    first_inc_act["incursion_non_damage_turn"] = True
                    first_inc_act["combat_tactical_archetype"] = "combat_parley"
                    first_inc_act.pop("check", None)
                    if inc_res.get("success"):
                        first_inc_act["tier"] = "success"
                        first_inc_act["success"] = True
                    else:
                        first_inc_act["tier"] = "fail"
                        first_inc_act["success"] = False
            except Exception as _inc_err:
                log.warning("Failed pre-turn anomalous incursion resolution: %s", _inc_err)

    mode = "combat" if (is_in_combat(session) and not _skip_precompute_for_incursion) else "narrative"
    _breach_round_dirs: list[str] = []
    try:
        from mechanics.social.anomalous_npc_tags import apply_breach_civilian_round_rules
        _, _breach_round_dirs = apply_breach_civilian_round_rules(
            session,
            str(session.get("scenario") or ""),
            stage_info=stage_info,
        )
        if _breach_round_dirs and isinstance(stage_info, dict) and isinstance(stage_info.get("stage_npcs"), list):
            pre_turn_stage_npcs = stage_info["stage_npcs"]
    except Exception as _br_err:
        log.debug("Breach civilian round rules check skipped: %s", _br_err)

    precomputed = None
    if mode == "combat":
        def _load_combat_precomputed_bundle() -> tuple[dict[int, dict], dict | None]:
            import character_data as _cd_eq
            eq_by_uid: dict[int, dict] = {}
            with db.UnitOfWork():
                for _p_entry in (party or []):
                    _p_char = _p_entry[0] if isinstance(_p_entry, (tuple, list)) and _p_entry else _p_entry
                    _p_inv = (
                        _p_entry[1]
                        if isinstance(_p_entry, (tuple, list)) and len(_p_entry) > 1 and isinstance(_p_entry[1], list)
                        else None
                    )
                    if isinstance(_p_char, dict) and _p_char.get("user_id"):
                        _p_uid = int(_p_char["user_id"])
                        if _p_uid not in eq_by_uid:
                            if _p_inv is not None:
                                _by_slot = {
                                    str(it["slot"]): dict(it)
                                    for it in _p_inv
                                    if isinstance(it, dict) and it.get("equipped") and it.get("slot")
                                }
                                eq_by_uid[_p_uid] = {slot: _by_slot.get(slot) for slot in _cd_eq.EQUIPMENT_SLOTS}
                            else:
                                eq_by_uid[_p_uid] = db.get_equipment(_p_uid) or {}
                ctx.combat.preloaded_equipment_by_uid = eq_by_uid
                if isinstance(session, dict):
                    session["_preloaded_equipment_by_uid"] = eq_by_uid
                return eq_by_uid, precompute_combat_turn(session, party, actions, persist_db=False)

        try:
            _, precomputed = await adb(_load_combat_precomputed_bundle)
        finally:
            ctx.combat.preloaded_equipment_by_uid = {}
            if isinstance(session, dict):
                session.pop("_preloaded_equipment_by_uid", None)

    from mechanics.system.memory.budget import DynamicTokenBudget
    budget = DynamicTokenBudget.from_session(session, party, actions)

    hist_text = await _build_history_context(
        session,
        ctx,
        budget=budget,
        actions=actions,
        effective_location=effective_location or "",
        pre_turn_stage_npcs=pre_turn_stage_npcs if (stage_info.get("is_movement") or pre_turn_stage_npcs) else None,
    )
    
    directive_note = ""
    if precomputed and precomputed.get("directive"):
        directive_note = f"\n{precomputed['directive']}\n"
    if _pre_turn_incursion_directive:
        directive_note += f"\n{_pre_turn_incursion_directive}\n"
    try:
        if scenario_data.is_anomalous_incursions_scenario(session.get("scenario", "")):
            from mechanics.pacts import build_pact_turn_stage_direction
            _pact_z3_events = []
            for _pa_z3 in (actions or []):
                if isinstance(_pa_z3, dict) and (_pa_z3.get("is_pact_skill") or str(_pa_z3.get("spell_id") or "").startswith("pact_")):
                    _meta_z3 = _pa_z3.get("_pact_cast_meta") if isinstance(_pa_z3.get("_pact_cast_meta"), dict) else {}
                    _actor_nm_z3 = str((_pa_z3.get("char") or {}).get("name") or "You")
                    _pat_nm_z3 = str(_meta_z3.get("patron_name") or _pa_z3.get("patron_name") or "the covenanted entity")
                    _pact_z3_events.append({
                        "type": "lethal_overdraw" if _pa_z3.get("is_lethal_overdraw") else "pact_cast",
                        "actor": _actor_nm_z3,
                        "patron_name": _pat_nm_z3,
                    })
            if _pact_z3_events:
                _pact_z3_dir = build_pact_turn_stage_direction(_pact_z3_events)
                if _pact_z3_dir:
                    directive_note += f"\n{_pact_z3_dir}\n"
    except Exception:
        pass

    # Pre-turn stage directives (hybrid sublocations, schedule shifts, canonical role spawns, tension timers)
    if stage_info.get("stage_directives"):
        for sdir in stage_info["stage_directives"]:
            if sdir and sdir not in directive_note:
                directive_note += f"\n{sdir}\n"
    for bdir in _breach_round_dirs:
        if bdir and bdir not in directive_note:
            directive_note += f"\n{bdir}\n"

    if cast_plan is not None:
        stage_plan_text = render_stage_plan(cast_plan)
        directive_note += f"\n{stage_plan_text}\n"

    # --- DETERMINISTIC PRE-TURN ENGINES (Python-First, 0 Arbiter LLM calls) ---
    from game_engine.state.core import resolve_pre_turn_vitals_and_resources
    from game_engine.state.social import resolve_pre_turn_social_and_disclosures

    def _run_pre_turn_deterministic_engines() -> tuple[dict, dict, dict]:
        _vitals = resolve_pre_turn_vitals_and_resources(
            session, party, actions, persist_db=False
        )
        _social = resolve_pre_turn_social_and_disclosures(
            session, party, actions, new_dialogue_partners=new_partners, persist_db=False
        )
        _hs_events: dict = {}
        try:
            from mechanics.world.locations.seeds import is_school_scenario as _is_hs_scen
            if _is_hs_scen(session.get("scenario", "")):
                from mechanics.social.discreet_encounters import evaluate_high_school_turn_events
                _hs_events = evaluate_high_school_turn_events(
                    session,
                    party,
                    actions,
                    effective_location=str(effective_location or session.get("current_location") or ""),
                    effective_node_id=str(stage_info.get("effective_node_id") or session.get("current_node_id") or ""),
                )
        except Exception as _hs_ev_err:
            log.warning("Failed evaluating High School turn events: %s", _hs_ev_err)
        return _vitals, _social, _hs_events

    pre_vitals_res, pre_social_res, hs_turn_events = await adb(_run_pre_turn_deterministic_engines)
    for p_dir in (pre_vitals_res.get("stage_directives") or pre_vitals_res.get("directives") or []):
        if p_dir and p_dir not in directive_note:
            directive_note += f"\n{p_dir}\n"
    for s_dir in (pre_social_res.get("directives") or []):
        if s_dir and s_dir not in directive_note:
            directive_note += f"\n{s_dir}\n"
    if isinstance(hs_turn_events, dict) and hs_turn_events:
        if hs_turn_events.get("override_location"):
            effective_location = hs_turn_events["override_location"]
            session["current_location"] = effective_location
        if hs_turn_events.get("override_node_id"):
            stage_info["effective_node_id"] = hs_turn_events["override_node_id"]
            session["current_node_id"] = hs_turn_events["override_node_id"]
        if hs_turn_events.get("dialogue_partners"):
            session["dialogue_partners"] = list(hs_turn_events["dialogue_partners"])
            session["dialogue_partner"] = hs_turn_events["dialogue_partners"][0]
        for hs_dir in (hs_turn_events.get("directives") or []):
            if hs_dir and hs_dir not in directive_note:
                directive_note += f"\n{hs_dir}\n"

    _anom_domain_res: dict = {}
    _staged_domain_vitals: dict | None = None
    try:
        from mechanics.world.anomalous_sites.domain_rules import evaluate_turn_domain_effects

        def _eval_domain_effects_bundle() -> dict:
            _dom_node = None
            _dom_sid = int(session.get("id") or 0)
            if _dom_sid:
                _dom_nid = str(stage_info.get("effective_node_id") or session.get("current_node_id") or "")
                with db.UnitOfWork():
                    if _dom_nid:
                        _dom_node = db.get_world_node(_dom_sid, _dom_nid)
                    _res_dom = evaluate_turn_domain_effects(
                        _dom_sid,
                        session,
                        party,
                        curr_node=_dom_node,
                        actions=actions,
                        persist_db=False,
                        is_retry=is_retry,
                    )
                    if _res_dom.get("composure_shift") or _res_dom.get("wet_flag"):
                        from mechanics.social.physical_state import find_player_actor_key, upsert_actor_physical_state
                        _phys_dom = db.get_session_physical_state(_dom_sid)
                        if isinstance(_phys_dom, dict) and isinstance(_phys_dom.get("actors"), dict):
                            _pk_dom = find_player_actor_key(_phys_dom["actors"], party=party, session_id=_dom_sid)
                            if _pk_dom:
                                _u_dom = {}
                                if _res_dom.get("composure_shift"):
                                    _u_dom["composure"] = _res_dom["composure_shift"]
                                if _res_dom.get("wet_flag"):
                                    _u_dom["is_wet"] = True
                                upsert_actor_physical_state(_dom_sid, _pk_dom, _u_dom)
                    return _res_dom
            return evaluate_turn_domain_effects(
                0,
                session,
                party,
                curr_node=None,
                actions=actions,
                persist_db=False,
                is_retry=is_retry,
            )

        _anom_domain_res = await adb(_eval_domain_effects_bundle)
        _dom_hp_d = int(_anom_domain_res.get("hp_delta") or 0)
        _dom_mp_d = int(_anom_domain_res.get("mp_delta") or 0)
        if _dom_hp_d != 0 or _dom_mp_d != 0:
            _dom_lead_c = (
                party[0][0]
                if party and isinstance(party[0], (tuple, list)) and party[0]
                else (party[0] if party else None)
            )
            _dom_uid = (
                int(_dom_lead_c["user_id"])
                if isinstance(_dom_lead_c, dict) and _dom_lead_c.get("user_id")
                else session.get("host_user_id")
            )
            if _dom_uid:
                _staged_domain_vitals = {
                    "user_id": int(_dom_uid),
                    "hp_delta": _dom_hp_d,
                    "mp_delta": _dom_mp_d,
                }
        for _dd in (_anom_domain_res.get("stage_directives") or []):
            if _dd and _dd not in directive_note:
                directive_note += f"\n{_dd}\n"
    except (NameError, UnboundLocalError, ImportError):
        raise
    except Exception as _dom_err:
        log.warning("Failed evaluating anomalous domain effects: %s", _dom_err)

    pre_intimate_res = None
    if _should_run_pre_intimacy:
        from mechanics.social.intimate_excitement import resolve_pre_turn_intimacy_and_clothing
        pre_intimate_res = resolve_pre_turn_intimacy_and_clothing(
            session, party, actions, new_partners=new_partners
        )
        for i_dir in (pre_intimate_res.get("directives") or []):
            if i_dir and i_dir not in directive_note:
                directive_note += f"\n{i_dir}\n"

    from game_engine.quests import resolve_pre_turn_quests_and_clues
    _old_loc_for_quests = session.get("current_location")
    if effective_location:
        session["current_location"] = effective_location
    pre_quest_res = await adb(
        resolve_pre_turn_quests_and_clues, session, party, actions, persist_db=False
    )
    if isinstance(pre_quest_res, dict):
        ctx.world_stage.pre_turn_quest_res = pre_quest_res
    if _old_loc_for_quests:
        session["current_location"] = _old_loc_for_quests
    for q_dir in (pre_quest_res.get("directives") or []):
        if q_dir and q_dir not in directive_note:
            directive_note += f"\n{q_dir}\n"

    # in_dialogue_mode prevents duplicate stall directive injection — dialogue_prompt_block
    # is the single authoritative prompt section for dialogue stall notes.
    _pre_turn_dialogue_partners = [str(p).strip().lower() for p in (get_session_dialogue_partners(session) or []) if p]
    _in_dialogue_mode = bool(_pre_turn_dialogue_partners)

    if not _in_intimate_for_core and not _in_aftercare_for_core:
        escalation_directives = game_engine.build_scene_escalation_and_consequence_directives(
            session, party, actions, ctx.story_quest, in_dialogue_mode=_in_dialogue_mode
        )
        if escalation_directives:
            directive_note += f"\n{escalation_directives}\n"

    # --- HYBRID ENCOUNTER ENGINE (5-10% chance in dangerous/non-combat locations) ---
    ambush_triggered = False
    ambush_monsters = []
    scen_key = session.get("scenario", "fantasy")
    _enc_loc = str(effective_location or session.get("current_location") or "")
    _enc_nid = str(stage_info.get("effective_node_id") or session.get("current_node_id") or "")
    _has_active_incursion_here = False
    if scenario_data.is_anomalous_incursions_scenario(scen_key) and session.get("id"):
        try:
            from mechanics.world.anomalous_events import (
                get_active_incursion_at_location,
                is_non_hostile_entity_containment_waypoint,
            )
            from mechanics.world.waypoints.core import get_active_local_quest_hooks
            _has_active_incursion_here = bool(await adb(get_active_incursion_at_location, int(session["id"]), _enc_loc, _enc_nid))
            if not _has_active_incursion_here:
                _local_q_hooks = (await adb(get_active_local_quest_hooks, int(session["id"]), _enc_loc)) or []
                _has_active_incursion_here = any(is_non_hostile_entity_containment_waypoint(w) for w in _local_q_hooks)
            if scenario_data.is_anomalous_high_school_scenario(scen_key) and not _has_active_incursion_here:
                try:
                    from mechanics.world.anomalous_events import check_or_roll_school_hours_anomalous_incident, get_dormant_after_hours_incursion_at_location
                    _day_inc = await db.adb(
                        check_or_roll_school_hours_anomalous_incident,
                        int(session["id"]),
                        int(session.get("current_day", 1) or 1),
                        int(session.get("current_minute", 480) or 480),
                    )
                    if _day_inc:
                        _has_active_incursion_here = True
                    else:
                        _dormant_inc = await db.adb(
                            get_dormant_after_hours_incursion_at_location,
                            int(session["id"]),
                            _enc_loc,
                            _enc_nid,
                        )
                        if _dormant_inc and _dormant_inc.get("foreshadow_clue"):
                            directive_note += f"\n[ATMOSPHERE / FORESHADOWING]: {_dormant_inc['foreshadow_clue']}\n"
                except Exception:
                    pass
        except Exception:
            _has_active_incursion_here = False
    # --- Post-combat breathing room & peaceful-dialogue protection ---
    _turn_now = int(session.get("turn_count") or 0)
    if is_in_combat(session) and session.get("id"):
        session["_last_combat_turn"] = _turn_now
        session["_last_combat_location"] = _enc_loc
        ctx.combat.last_combat_turn = _turn_now
        ctx.combat.last_combat_location = _enc_loc
        try:
            await adb(
                db.update_session,
                int(session["id"]),
                extra={"_last_combat_turn": _turn_now, "_last_combat_location": _enc_loc},
            )
        except Exception:
            pass
    _last_cbt_turn = ctx.combat.last_combat_turn if ctx.combat.last_combat_turn is not None else session.get("_last_combat_turn")
    _turns_since_combat = (_turn_now - int(_last_cbt_turn)) if isinstance(_last_cbt_turn, (int, float)) else 99
    _eff_last_combat_loc = ctx.combat.last_combat_location or str(session.get("_last_combat_location") or "")
    _same_room_as_last_combat = bool(
        _enc_loc and _eff_last_combat_loc.strip().lower() == _enc_loc.strip().lower()
    )
    _random_ambush_on_cooldown = _turns_since_combat <= 2
    _act_dicts = [a for a in (actions or []) if isinstance(a, dict)]
    _explicit_quest_action = any(
        a.get("quest_id") or a.get("lead_id") or "quest" in str(a.get("intent") or "").lower()
        for a in _act_dicts
    )
    _hostile_action = any(
        str(a.get("intent") or "").lower() in ("attack", "combat", "combat_action", "ability", "spell", "confront")
        or any(w in str(a.get("label") or "").lower() for w in ("attack", "confront", "ambush", "fight", "strike"))
        for a in _act_dicts
    )
    _peaceful_dialogue_action = bool(_in_dialogue_mode) and not _explicit_quest_action and not _hostile_action and all(
        str(a.get("intent") or "").lower() in ("", "dialogue", "social", "general_action", "persuade", "negotiate", "ask", "talk")
        for a in _act_dicts
    )
    _quest_spawn_on_cooldown = _same_room_as_last_combat and _turns_since_combat <= 1 and not _explicit_quest_action
    try:
        from mechanics.narrative.dossier_compiler import is_safe_sanctuary_location as _is_sanctuary
        _in_safe_sanctuary = _is_sanctuary(_enc_loc)
    except Exception:
        _in_safe_sanctuary = False
    # Deterministic Predetermined Quest Encounter Spawner (Climax Boss & Lead Combat Rosters)
    if (
        not is_in_combat(session)
        and not _has_active_incursion_here
        and not is_retry
        and not _in_intimate_for_core
        and not _in_aftercare_for_core
        and not _quest_spawn_on_cooldown
        and not (_in_safe_sanctuary and not _explicit_quest_action)
        and scenario_data.is_mechanic_enabled(scen_key, "tactical_combat")
        and session.get("id")
        and _enc_loc
    ):
        try:
            _completed_qids_pre = {
                str(cq) for cq in ((pre_quest_res or {}).get("completed_quests") or []) if cq
            }
            from mechanics.world.waypoints.matching import check_location_matches_waypoint as _chk_loc_match
            _enc_loc_low = _enc_loc.strip().lower()
            _q_sp_sid = int(session["id"])

            def _eval_quest_encounter_spawner() -> Optional[tuple[list[dict], dict, bool]]:
                with db.UnitOfWork():
                    _q_dossiers = db.get_session_quest_dossiers(_q_sp_sid, status_stage="compiled") or []
                    for _qd in _q_dossiers:
                        _qid = str(_qd.get("quest_id") or "")
                        if not _qid or _qid in _completed_qids_pre:
                            continue
                        _q_row = db.get_quest_by_id(_q_sp_sid, _qid)
                        if not _q_row or str(_q_row.get("status") or "").lower() != "active":
                            continue
                        _climax = _qd.get("climax_spec") or {}
                        _c_loc = str(_climax.get("location") or "").strip().lower()
                        _c_target = str(_climax.get("target_npc") or "").strip().lower()
                        _talking_to_target = bool(_c_target) and any(_c_target in p or p in _c_target for p in _pre_turn_dialogue_partners)
                        _has_incomplete_main = any(
                            isinstance(_ms, dict)
                            and not _ms.get("is_climax_stage")
                            and str(_ms.get("status") or "").lower() not in ("completed", "bypassed")
                            for _ms in (_climax.get("main_stages") or [])
                        )
                        _boss_raw_cur = _climax.get("boss_sheet") if isinstance(_climax.get("boss_sheet"), dict) else {}
                        _already_rushed_climax = bool(_boss_raw_cur.get("rushed_un_nerfed"))
                        _is_rush_action = any(
                            bool(a.get("rush_climax")) and str(a.get("quest_id") or "") == _qid
                            for a in _act_dicts
                        )
                        if _has_incomplete_main and not _is_rush_action and not _already_rushed_climax:
                            continue
                        _climax_escalated = bool(
                            not _climax.get("boss_escalation_only")
                            or _climax.get("escalated")
                            or _climax.get("ambush_unlocked")
                            or _hostile_action
                            or _is_rush_action
                        )
                        if (
                            _climax.get("is_unlocked")
                            and not _climax.get("boss_defeated")
                            and isinstance(_climax.get("boss_sheet"), dict)
                            and _climax_escalated
                            and not (_peaceful_dialogue_action and not _talking_to_target)
                            and _c_loc
                            and _chk_loc_match(_enc_loc, str(_climax.get("location") or ""), session_id=_q_sp_sid)
                        ):
                            if _is_rush_action:
                                try:
                                    from game_engine.quest_turn_resolver import evaluate_nonlinear_leads_and_climax_gate as _eval_rush
                                    _eval_rush(_q_sp_sid, _qid, rush_climax=True)
                                    _qd_rushed = db.get_quest_dossier(_q_sp_sid, _qid)
                                    if _qd_rushed and isinstance(_qd_rushed.get("climax_spec"), dict):
                                        _climax = _qd_rushed["climax_spec"]
                                except (NameError, UnboundLocalError, ImportError):
                                    raise
                                except Exception as _rush_exc:
                                    log.warning("Climax rush evaluation failed for %s: %s", _qid, _rush_exc, exc_info=True)
                            _boss_unit = dict(_climax["boss_sheet"])
                            try:
                                from mechanics.narrative.dossier_compiler import hydrate_boss_sheet_from_quest_blueprint
                                _boss_unit = hydrate_boss_sheet_from_quest_blueprint(_boss_unit, _q_row)
                            except Exception:
                                pass
                            _boss_unit["linked_quest_id"] = _qid
                            _reinf_units = []
                            for _rf in (_climax.get("reinforcements") or []):
                                if isinstance(_rf, dict) and int(_rf.get("hp", 1) or 1) > 0:
                                    _rf_copy = dict(_rf)
                                    _rf_copy["linked_quest_id"] = _qid
                                    _reinf_units.append(_rf_copy)
                            return (
                                [_boss_unit] + _reinf_units,
                                {"quest_id": _qid, "is_climax_boss": True},
                                True,
                            )
                        for _ld in (_qd.get("leads_graph") or []):
                            if not isinstance(_ld, dict):
                                continue
                            _ld_loc = str(_ld.get("target_location") or _ld.get("location") or "").strip().lower()
                            if (
                                _ld.get("encounter_roster")
                                and not _ld.get("roster_cleared")
                                and not _peaceful_dialogue_action
                                and str(_ld.get("status") or "").lower() != "completed"
                                and _ld_loc
                                and (_ld_loc in _enc_loc_low or _enc_loc_low in _ld_loc)
                            ):
                                _spawned_lead = []
                                for _le in (_ld.get("encounter_roster") or []):
                                    if isinstance(_le, dict):
                                        _le_copy = dict(_le)
                                        _le_copy.setdefault("hp", int(_le_copy.get("max_hp") or 24))
                                        _le_copy["linked_quest_id"] = _qid
                                        _spawned_lead.append(_le_copy)
                                if _spawned_lead:
                                    return (
                                        _spawned_lead,
                                        {"quest_id": _qid, "is_climax_boss": False, "lead_id": _ld.get("lead_id")},
                                        False,
                                    )
                    return None

            _q_sp_res = await adb(_eval_quest_encounter_spawner)
            if _q_sp_res is not None:
                _spawned_units, _q_enc_meta, _is_climax_enc = _q_sp_res
                session["nearby_enemies"] = _spawned_units
                session["_active_quest_encounter"] = _q_enc_meta
                ctx.combat.active_quest_encounter = _q_enc_meta
                new_partners = []
                _in_dialogue_mode = False
                _names = ", ".join(m["name"] for m in _spawned_units if m.get("name"))
                party_names_str = ", ".join(
                    c.get("name", "Hero")
                    for c, _ in (party or [])
                    if isinstance(c, dict) and c.get("name")
                ) or "the player"
                present_npc_names = [
                    game_engine._get_npc_name(n)
                    for n in (session.get("current_npcs") or [])
                    if game_engine._get_npc_name(n) and game_engine._get_npc_name(n).lower() != "none"
                ]
                npc_react_clause = f" and present characters ({', '.join(present_npc_names)})" if present_npc_names else ""
                if _is_climax_enc:
                    directive_note += (
                        f"\n[MANDATORY QUEST ENCOUNTER DIRECTIVE]: Predetermined quest adversaries ({_names}) confront the party! "
                        f"You MUST dramatically narrate their reveal and hostile confrontation in `@@OUTCOME` and `@@NEXT`, "
                        f"and explicitly describe how {party_names_str}{npc_react_clause} react to the encounter. "
                        f"DO NOT resolve the battle this turn; set the stage for combat!\n"
                    )
                else:
                    directive_note += (
                        f"\n[MANDATORY QUEST ENCOUNTER DIRECTIVE]: Hostile guards/adversaries ({_names}) confront the party! "
                        f"You MUST dramatically narrate their confrontation in `@@OUTCOME` and `@@NEXT`, "
                        f"and explicitly describe how {party_names_str}{npc_react_clause} react to the encounter. "
                        f"DO NOT resolve the battle this turn; set the stage for combat!\n"
                    )
        except (NameError, UnboundLocalError, ImportError):
            raise
        except Exception:
            pass
    if (
        not is_in_combat(session)
        and not _has_active_incursion_here
        and not is_retry
        and not _in_intimate_for_core
        and not _in_aftercare_for_core
        and not _random_ambush_on_cooldown
        and not _peaceful_dialogue_action
        and scenario_data.is_mechanic_enabled(scen_key, "tactical_combat")
        and (
            (scenario_data.is_anomalous_incursions_scenario(scen_key) and _turn_now > 1)
            or (not scenario_data.is_anomalous_incursions_scenario(scen_key) and not is_hub_location(_enc_loc))
        )
    ):
        from mechanics.combat.enemies import generate_balanced_encounter, should_allow_random_encounter
        _cur_min_enc = int(session.get("current_minute", 720) or 720)
        allow_enc, enc_prob = should_allow_random_encounter(
            scen_key=scen_key,
            location_name=_enc_loc,
            location_id=_enc_nid,
            current_minute=_cur_min_enc,
            session_id=int(session.get("id") or 0),
            turn_count=_turn_now,
        )
        if allow_enc and random.random() < enc_prob:
            party_dicts = [char for char, _ in party] if party else []
            cur_chapter = int(session.get("current_chapter", 1) or 1)
            _is_tp_wp = (
                scenario_data.is_anomalous_incursions_scenario(scen_key)
                and (0 <= (_cur_min_enc % 1440) < 180)
                and any(k in f"{_enc_nid} {_enc_loc}".lower() for k in ("loc_theme_park", "loc_tp_", "theme park", "amusement resort"))
            )
            eff_chapter = cur_chapter + 1 if _is_tp_wp else cur_chapter
            new_monsters, xp_mult = generate_balanced_encounter(
                party_dicts, scen_key, _enc_loc or "area", eff_chapter,
                language=session.get("narration_language") or session.get("language", "en"),
                current_minute=_cur_min_enc,
            )
            for _m in new_monsters:
                if isinstance(_m, dict):
                    _m["is_random_encounter"] = True
                    if _is_tp_wp:
                        _m["is_witching_peak"] = True
                        _m["anomalous_loot_bonus"] = 0.20
            # Pre-inject them into session so they appear in prompt
            session["nearby_enemies"] = new_monsters
            ambush_triggered = True
            ambush_monsters = list(new_monsters)
            # Break peaceful 1-on-1 dialogue lock when an ambush interrupts the scene
            new_partners = []
            _in_dialogue_mode = False
            names = ", ".join(m["name"] for m in new_monsters if m.get("name"))
            party_names_str = ", ".join(
                c.get("name", "Hero")
                for c, _ in (party or [])
                if isinstance(c, dict) and c.get("name")
            ) or "the player"
            present_npc_names = [
                game_engine._get_npc_name(n)
                for n in (session.get("current_npcs") or [])
                if game_engine._get_npc_name(n) and game_engine._get_npc_name(n).lower() != "none"
            ]
            npc_react_clause = (
                f" and present characters ({', '.join(present_npc_names)})"
                if present_npc_names
                else ""
            )
            directive_note += (
                f"\n[MANDATORY AMBUSH DIRECTIVE]: Enemies ({names}) have suddenly ambushed the party! "
                f"You MUST narrate their sudden appearance and attack in `@@OUTCOME` and `@@NEXT`, "
                f"and explicitly describe how {party_names_str}{npc_react_clause} react to the encounter "
                f"(drawing weapons, shouting warnings, taking defensive stances). "
                f"DO NOT resolve the fight this turn; just spring the trap!\n"
            )



    movement_dest_str = stage_info.get("movement_dest_str") or ""
    # --- TRAVEL & TRANSIT DIRECTIVE ---

    if not is_in_combat(session):

        for a in actions:
            a_int = str(a.get("intent") or "").strip().lower() if isinstance(a, dict) else ""
            if a_int and a_int not in ("general_action", "movement", "travel", "fast_travel", "move"):
                continue

            label = a.get("label", "") if isinstance(a, dict) else str(a)

            raw_curr = session.get("current_location", "")

            parsed_z = get_zone_location_name(raw_curr) if raw_curr else ""

            action_dest = extract_movement_destination(label, session["id"], current_zone=parsed_z, scen_key=scen_key)

            if action_dest:

                dest_z, dest_p = action_dest
                movement_dest_str = f'{dest_z} \u2794 {dest_p}'

                cur_loc = session.get("current_location", "")

                old_primary = get_primary_location_name(cur_loc)

                is_crit_fail = bool(a.get("check") and getattr(a["check"], "tier", "") == "crit_fail")

                if is_crit_fail:

                    directive_note += (

                        f"\n[TRAVEL COMPLICATION DIRECTIVE]: The party attempted to travel to [{dest_z} ➔ {dest_p}] but suffered a Critical Failure! "

                        f"Narrate a sudden catastrophe, ambush, or hazard blocking their journey on route.\n"

                    )

                else:

                    traveling_companions, left_behind_patrons = game_engine.classify_scene_npcs(session, actions, old_primary=old_primary, dest_primary=dest_p)

                    comp_names = [c["name"] for c in traveling_companions if c.get("name")]

                    patron_names = [p["name"] for p in left_behind_patrons if p.get("name")]

                    

                    comp_str = ", ".join(comp_names) if comp_names else "None (traveling solo)"

                    # Check if action or active quest specifies a target resident / station within dest_p
                    target_station_sub = None
                    target_resident_name = None
                    lbl_lower = (label or "").lower()

                    facility_residents = []
                    try:
                        facility_residents = await adb(
                            db.get_school_characters_by_facility,
                            session["id"],
                            f"{dest_z} ➔ {dest_p}",
                            limit=6,
                        )
                    except Exception:
                        facility_residents = []

                    # 1. Check if action mentions one of the facility residents
                    for fr in facility_residents:
                        fr_nm = (fr.get("name") or "").strip().lower()
                        if fr_nm and (fr_nm in lbl_lower or (len(fr_nm.split()) > 1 and fr_nm.split()[0] in lbl_lower)):
                            fr_fac = fr.get("primary_facility") or ""
                            if fr_fac:
                                _, _, fr_s = parse_tiered_location(fr_fac, scen_key, session_id=session["id"])
                                if fr_s and fr_s not in ("Main Area", ""):
                                    target_station_sub = fr_s
                                    target_resident_name = fr.get("name")
                                    break

                    # 2. Check active quest sub-objectives if not found yet
                    if not target_station_sub:
                        try:
                            def _load_active_quest_sub_objs(sid_q: int) -> list:
                                with db.get_conn() as _c_conn:
                                    return _c_conn.execute(
                                        "SELECT sub_objectives_json FROM quests WHERE session_id=? AND status='Active'",
                                        (sid_q,),
                                    ).fetchall()

                            q_rows = await adb(_load_active_quest_sub_objs, session["id"])
                            for qr in q_rows:
                                sub_objs = json.loads(qr["sub_objectives_json"] or "[]")
                                for so in sub_objs:
                                    if not so.get("completed"):
                                        t_loc = so.get("target_location", "")
                                        t_npc = (so.get("target_npc") or "").strip().lower()
                                        if t_loc:
                                            qz, qp, qs = parse_tiered_location(t_loc, scen_key, session_id=session["id"])
                                            if qp.lower() == dest_p.lower() and qs and qs not in ("Main Area", ""):
                                                if not t_npc or (t_npc in lbl_lower or (len(t_npc.split()) > 1 and t_npc.split()[0] in lbl_lower)):
                                                    target_station_sub = qs
                                                    target_resident_name = so.get("target_npc")
                                                    break
                                if target_station_sub:
                                    break
                        except Exception:
                            pass

                    is_gated = bool(stage_info.get("access_gate", {}).get("gated"))
                    if not is_gated:
                        from mechanics.world.locations import get_clean_leaf_location
                        eff_leaf = get_clean_leaf_location(effective_location) if effective_location else ""
                        loc_prompt_target = target_station_sub or eff_leaf or "Main Area"
                        directive_note += (
                            f"\n[TRAVEL ARRIVAL & ESTABLISHMENT DEPARTURE DIRECTIVE]:\n"
                            f"- The party has departed [{old_primary}] and arrived at [{dest_z} ➔ {dest_p}].\n"
                            f"- Arrival Destination: '{dest_z} ➔ {dest_p} ➔ {loc_prompt_target}'. Depict the party arriving at this exact sub-area.\n"
                        )
                    if target_resident_name and target_station_sub:
                        directive_note += f"- Target Resident: {target_resident_name} is stationed at {target_station_sub}.\n"
                    directive_note += f"- Companions traveling with the party: {comp_str}.\n"

                    if patron_names:
                        patron_str = ", ".join(patron_names)
                        directive_note += (
                            f"- Patrons left behind at {old_primary} (DO NOT NARRATE OR DEPICT IN THIS SCENE): {patron_str}.\n"
                        )
                    directive_note += f"- Local environment: Introduce or focus on local NPCs native to {dest_p}.\n"

                    if facility_residents:
                        resident_lines = []
                        for fr in facility_residents:
                            fr_name = fr.get("name")
                            fr_role = fr.get("role") or ""
                            fr_gender = fr.get("gender") or ""
                            fr_fac = fr.get("primary_facility") or ""
                            _, _, fr_s = parse_tiered_location(fr_fac, scen_key, session_id=session["id"]) if fr_fac else ("", "", "")
                            station_txt = f" @ {fr_s}" if fr_s and fr_s not in ("Main Area", "") else ""
                            gender_txt = f", {fr_gender}" if fr_gender else ""
                            resident_lines.append(f"  * {fr_name} ({fr_role}{gender_txt}){station_txt}")
                        if resident_lines:
                            directive_note += (
                                f"- Canonical Facility Occupants stationed at {dest_p}:\n"
                                + "\n".join(resident_lines) + "\n"
                                f"- Roster & Presence Guidance: Focus interaction on the active scene characters. Other room occupants may be working quietly at their designated stations or away in class. Do not seat one character at another occupant's specific desk or station.\n"
                            )



                    # Check for pending phone appointments at this arrival destination

                    try:

                        from mechanics.world.waypoints import check_location_matches_waypoint

                        dest_full = f"{dest_z} ➔ {dest_p}"

                        pending_appts = ctx.pending_appointments

                        for appt in pending_appts:

                            appt_loc = appt.get("rendezvous_location", "")

                            npc_name = appt.get("npc_name", "")

                            if appt_loc and npc_name and check_location_matches_waypoint(dest_full, appt_loc):

                                directive_note += (

                                    f"\n[MANDATORY MEETUP RENDEZVOUS ON ARRIVAL ({npc_name})]:\n"

                                    f"- {npc_name} agreed via DM to meet here at {appt_loc} and is actively waiting for the player.\n"

                                    f"- This is a PRIVATE meeting/rendezvous between the player and {npc_name}. Uninvited peers or classmates from prior locations (such as homeroom or hallways) are NOT present and must NOT be mentioned in this scene.\n"

                                    f"- You MUST narrate {npc_name}'s greeting and presence in `@@OUTCOME` and `@@NEXT`.\n"

                                    f"- You MUST depict {npc_name} physically present in the scene and generate direct conversational choices with {npc_name} in `@@CHOICES` (emit `cast: engage | {npc_name} | meetup` in `@@META` if initiating dialogue).\n"

                                    f"- Ensure the scene reflects the rendezvous area (e.g. '{appt_loc}').\n"

                                )

                    except Exception:

                        pass

                break



    session_for_phys = dict(session)
    if stage_info.get("is_movement"):
        session_for_phys["current_location"] = effective_location
        session_for_phys["current_npcs"] = pre_turn_stage_npcs
    phys_prompt_block = build_physical_prompt_block(
        session_for_phys, party,
        is_combat=is_in_combat(session),
        is_nsfw=is_nsfw_scenario(session.get("scenario")),
        actions=actions
    )




    scene_loc = effective_location if effective_location else session.get('current_location', '')
    scene_npcs_for_prompt = pre_turn_stage_npcs if (stage_info.get("is_movement") or pre_turn_stage_npcs) else session.get('current_npcs', [])
    from game_engine.turn.generation import extract_deterministic_recall_query

    def _pre_prompt_read_bundle() -> tuple:
        sid_val = session.get("id")
        _seeded_locs_pre_read = False
        if sid_val:
            from mechanics.world.locations import is_location_engine_enabled, ensure_session_locations_seeded
            if is_location_engine_enabled(scen_key):
                _lead_nm_seed = (
                    party[0][0].get("name", "")
                    if (party and isinstance(party[0], (tuple, list)) and isinstance(party[0][0], dict))
                    else ""
                )
                ensure_session_locations_seeded(sid_val, scen_key, char_name=_lead_nm_seed)
                _seeded_locs_pre_read = True

        uow_cm = db.ReadUnitOfWork() if sid_val else nullcontext()
        with uow_cm:
            dlg_blk = _build_dialogue_prompt_block(session, ctx, new_partners, party, actions)
            if sid_val:
                try:
                    c_day, c_min, _ = db.get_session_time(sid_val)
                except Exception:
                    c_day, c_min = int(session.get("current_day", 1) or 1), int(session.get("current_minute", 480) or 480)
            else:
                c_day, c_min = int(session.get("current_day", 1) or 1), int(session.get("current_minute", 480) or 480)

            w_bundle = dict(ctx.world_bundle) if sid_val else game_engine._load_known_world(sid_val, seed_factions=False)
            w_bundle["session"] = session
            w_bundle["_ctx"] = ctx
            r_scene_ctx = game_engine._scene_context_text(
                sid_val,
                scene_loc,
                scene_npcs_for_prompt,
                4,
                hist_text,
                w_bundle,
                ensure_locations_seeded=(not _seeded_locs_pre_read),
            )
            wp_blk = ""
            cb_blk = ""
            fow_blk = ""
            if not _in_intimate_for_core and not _in_aftercare_for_core:
                wp_blk, cb_blk = game_engine._quest_board_parts(
                    sid_val,
                    scene_loc,
                    movement_dest_str,
                    session=session,
                )
                fow_blk = game_engine.build_fog_of_war_quest_prompt_block(
                    sid_val,
                    session,
                    bool(_in_intimate_for_core),
                )

            recall_hits: list[str] = []
            for a in (actions or []):
                if isinstance(a, dict) and a.get("active_recall"):
                    recall_hits.extend(a["active_recall"])
                elif isinstance(a, dict) and sid_val:
                    recall_q = extract_deterministic_recall_query(a.get("label", ""), session_id=sid_val)
                    if recall_q:
                        try:
                            det_recalls = db.active_recall_search(sid_val, recall_q)
                            if det_recalls:
                                a["active_recall"] = det_recalls
                                recall_hits.extend(det_recalls)
                        except Exception:
                            pass

            we_snap_res = (
                ctx.world_stage.world_events_snapshot
                if ctx.world_stage.world_events_snapshot
                else session.get("_world_events_snapshot")
            )
            if not we_snap_res and session.get("_world_events_snapshot") is None and sid_val:
                try:
                    we_snap_res = db.get_world_events_snapshot(int(sid_val))
                    if isinstance(we_snap_res, dict):
                        ctx.world_stage.world_events_snapshot = we_snap_res
                except Exception:
                    we_snap_res = None

            return dlg_blk, c_day, c_min, w_bundle, r_scene_ctx, wp_blk, cb_blk, fow_blk, recall_hits, we_snap_res

    (
        dialogue_prompt_block,
        curr_day,
        curr_min,
        world_bundle,
        raw_scene_ctx,
        wp_block,
        caseboard_block,
        fow_dossier_block,
        active_recall_blocks,
        _we_snap,
    ) = await adb(_pre_prompt_read_bundle)

    time_prompt_block = format_llm_time_context(curr_day, curr_min, scen_key, session=session)

    _loc = locals()
    return {k: _loc[k] for k in _PRE_TURN_EXPORT_KEYS if k in _loc}
