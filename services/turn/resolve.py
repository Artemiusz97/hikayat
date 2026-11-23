from __future__ import annotations

import asyncio
import copy
import json
import os
import random
import tempfile
from character_data import XP_REWARDS
import db
from db import adb
import game_engine
import llm_client
import scenario_data
from mechanics.combat.merchant import apply_merchant_encounter_result
from services import crash_capture
from typing import Any, Dict, List, Optional, Tuple
from .models import TurnResponse, _BACKGROUND_TASKS, _callable_accepts_kwarg, _get_turn_service, _is_llm_unavailable_exception, log

async def _finalize_and_save_scene(
    session_id: int,
    session_obj: Dict[str, Any],
    outcome: Dict[str, Any],
    lead_char: Optional[Dict[str, Any]],
    history: List[Dict[str, Any]],
    mode: Optional[str] = None,
    is_retry: bool = False,
) -> Tuple[str, str, List[Dict[str, Any]]]:
    """Single source of truth for extracting, sanitizing, and persisting post-turn scene state."""
    sess_dict = session_obj if isinstance(session_obj, dict) else {}
    raw_choices, next_narrative, scene_title, partner_arg, npcs_arg = game_engine.extract_scene_fields(
        outcome, session=sess_dict
    )
    if isinstance(outcome, dict) and outcome.get("fallback_reason") == "empty_prose":
        warn_prefix = "⚠️ *The engine struggled to narrate the outcome. Showing placeholder.* ⚠️\n\n"
        if not str(next_narrative or "").startswith("⚠️ *The engine struggled"):
            next_narrative = warn_prefix + (next_narrative or "")

    effective_partner = sess_dict.get("dialogue_partner") if partner_arg is ... else partner_arg
    effective_npcs = sess_dict.get("current_npcs", []) if npcs_arg is None else npcs_arg

    if isinstance(outcome, dict) and outcome.get("_hybrid_choices_built") and raw_choices:
        cleaned_choices = list(raw_choices)
    else:
        cleaned_choices = await adb(
            game_engine.sanitize_and_diversify_choices,
            raw_choices,
            scenario=sess_dict.get("scenario", "fantasy"),
            location=(outcome.get("location") if isinstance(outcome, dict) else None) or sess_dict.get("current_location", ""),
            char=dict(lead_char) if isinstance(lead_char, dict) else None,
            dialogue_partner=effective_partner,
            current_npcs=effective_npcs,
            session_id=session_id,
            departed_npcs=(
                outcome.get("departed_characters") or outcome.get("departed_npcs")
                if isinstance(outcome, dict)
                else None
            ),
        )
        cleaned_choices = list(cleaned_choices or [])

    from mechanics.social.conversation_choices import (
        ensure_active_dialogue_exit_choice,
        has_dialogue_exit_choice,
    )
    had_exit_before = has_dialogue_exit_choice(cleaned_choices)
    cleaned_choices = await adb(
        ensure_active_dialogue_exit_choice,
        cleaned_choices,
        session=sess_dict,
        partners=effective_partner,
        outcome=outcome if isinstance(outcome, dict) else None,
    )
    if not had_exit_before and has_dialogue_exit_choice(cleaned_choices):
        log.warning(
            "Healed missing dialogue exit choice in _finalize_and_save_scene "
            "(session_id=%s, partner=%r, hybrid_built=%r, pre_labels=%r)",
            session_id,
            effective_partner,
            outcome.get("_hybrid_choices_built") if isinstance(outcome, dict) else None,
            [c.get("label") for c in (raw_choices or []) if isinstance(c, dict)],
        )

    _in_dlg_fin = bool(
        effective_partner
        if isinstance(effective_partner, list)
        else ([effective_partner] if isinstance(effective_partner, str) and effective_partner.strip() else [])
    )
    _in_cbt_fin = bool(
        game_engine.get_active_enemies(outcome if isinstance(outcome, dict) else sess_dict)
        or game_engine.get_active_enemies(sess_dict)
    )
    cleaned_choices = game_engine.order_choices_canonically(
        cleaned_choices,
        in_dialogue=_in_dlg_fin,
        in_combat=_in_cbt_fin,
    )

    if isinstance(outcome, dict):
        outcome["next_narrative"] = next_narrative
        outcome["scene_title"] = scene_title

    def _commit_scene_tx() -> None:
        with db.UnitOfWork():
            if is_retry or mode == "sync":
                db.clear_pending_picks(session_id)
            elif mode in ("turn", "multi"):
                db.advance_turn(session_id)

            db.save_session_scene(
                session_id,
                scene_title,
                next_narrative,
                cleaned_choices,
                list(history or []),
                location=outcome.get("location") if isinstance(outcome, dict) else None,
                nearby_enemies=outcome.get("nearby_enemies") if isinstance(outcome, dict) else None,
                current_npcs=npcs_arg,
                dialogue_partner=partner_arg,
                current_node_id=outcome.get("current_node_id") if isinstance(outcome, dict) else None,
                focal_point=outcome.get("focal_point") if isinstance(outcome, dict) else None,
                combat_threat_ledger=outcome.get("combat_threat_ledger") if isinstance(outcome, dict) else None,
                combat_boss_telegraph=outcome.get("combat_boss_telegraph") if isinstance(outcome, dict) else None,
            )

    await adb(_commit_scene_tx)
    try:
        from services.examine_service import invalidate_examine_cache
        invalidate_examine_cache(int(session_id))
    except Exception:
        pass
    return scene_title, next_narrative, cleaned_choices


async def resolve_action(
    session_id: int,
    user_id: int,
    action: Dict[str, Any],
    mode: str = "solo",
    stream_callback=None,
    actions: Optional[List[Dict[str, Any]]] = None,
) -> TurnResponse:
    """
    Unifies the turn resolution process across Discord and Web API using non-blocking DB access.
    """
    if os.environ.get("HIKAYAT_CRASH_CAPTURE", "").strip() == "1" and not crash_capture.is_in_crash_capture():
        return await _get_turn_service()._resolve_action_with_crash_capture(
            session_id=session_id,
            user_id=user_id,
            action=action,
            mode=mode,
            stream_callback=stream_callback,
            actions=actions,
        )
    return await _get_turn_service()._resolve_action_inner(
        session_id=session_id,
        user_id=user_id,
        action=action,
        mode=mode,
        stream_callback=stream_callback,
        actions=actions,
    )


async def _resolve_action_with_crash_capture(
    *,
    session_id: int,
    user_id: int,
    action: Dict[str, Any],
    mode: str = "solo",
    stream_callback=None,
    actions: Optional[List[Dict[str, Any]]] = None,
) -> TurnResponse:
    """Captures pre-turn SQLite snapshot and LLM tape when `HIKAYAT_CRASH_CAPTURE=1`."""
    sess_meta = await adb(db.get_session, session_id) or {}
    scenario_val = str(sess_meta.get("scenario") or "fantasy")
    turn_num = int(sess_meta.get("turn_count") or 0) + 1
    action_copy = copy.deepcopy(action)
    actions_copy = copy.deepcopy(actions) if actions is not None else None
    rng_state_json = crash_capture.encode_rng_state(random.getstate())

    tf = tempfile.NamedTemporaryFile(prefix="hikayat_preturn_", suffix=".db", delete=False)
    pre_db_path = tf.name
    tf.close()
    try:
        await adb(crash_capture.snapshot_sqlite_to_file, db.DB_PATH, pre_db_path, read_only=True)
    except Exception as snap_err:
        log.warning("Crash-capture pre-turn snapshot failed: %s", snap_err)

    strict_mod = crash_capture.load_optional_strict_mode()
    strict_ctx = (
        strict_mod.capture()
        if (strict_mod is not None and callable(getattr(strict_mod, "level", None)) and strict_mod.level() > 0)
        else None
    )
    bundle_dir_env = os.environ.get("HIKAYAT_CRASH_DIR", "").strip() or None

    try:
        with crash_capture.crash_capture_scope(), llm_client.record_llm_tape() as tape:
            if strict_ctx is not None:
                with strict_ctx as hits:
                    try:
                        resp = await _get_turn_service()._resolve_action_inner(
                            session_id=session_id,
                            user_id=user_id,
                            action=action,
                            mode=mode,
                            stream_callback=stream_callback,
                            actions=actions,
                        )
                    except BaseException as exc:
                        if not (isinstance(exc, ValueError) and str(exc) == "waiting_for_party"):
                            try:
                                crash_capture.write_crash_bundle(
                                    bundle_root=bundle_dir_env,
                                    scenario=scenario_val,
                                    session_id=session_id,
                                    user_id=user_id,
                                    turn_number=turn_num,
                                    seed=None,
                                    stage="resolve_action",
                                    mode=mode,
                                    action=action_copy,
                                    actions=actions_copy,
                                    rng_state_json=rng_state_json,
                                    llm_tape=tape,
                                    strict_hits=list(hits),
                                    exc=exc,
                                    pre_turn_db_source=pre_db_path,
                                )
                            except Exception as write_err:
                                log.warning("Failed writing crash bundle: %s", write_err)
                        raise
                    if hits:
                        try:
                            crash_capture.write_crash_bundle(
                                bundle_root=bundle_dir_env,
                                scenario=scenario_val,
                                session_id=session_id,
                                user_id=user_id,
                                turn_number=turn_num,
                                seed=None,
                                stage="resolve_action",
                                mode=mode,
                                action=action_copy,
                                actions=actions_copy,
                                rng_state_json=rng_state_json,
                                llm_tape=tape,
                                strict_hits=list(hits),
                                exc=None,
                                error_summary=f"Swallowed strict-mode error(s): {len(hits)}",
                                pre_turn_db_source=pre_db_path,
                            )
                        except Exception as write_err:
                            log.warning("Failed writing strict-mode crash bundle: %s", write_err)
                    return resp
            else:
                try:
                    return await _get_turn_service()._resolve_action_inner(
                        session_id=session_id,
                        user_id=user_id,
                        action=action,
                        mode=mode,
                        stream_callback=stream_callback,
                        actions=actions,
                    )
                except BaseException as exc:
                    if not (isinstance(exc, ValueError) and str(exc) == "waiting_for_party"):
                        try:
                            crash_capture.write_crash_bundle(
                                bundle_root=bundle_dir_env,
                                scenario=scenario_val,
                                session_id=session_id,
                                user_id=user_id,
                                turn_number=turn_num,
                                seed=None,
                                stage="resolve_action",
                                mode=mode,
                                action=action_copy,
                                actions=actions_copy,
                                rng_state_json=rng_state_json,
                                llm_tape=tape,
                                strict_hits=[],
                                exc=exc,
                                pre_turn_db_source=pre_db_path,
                            )
                        except Exception as write_err:
                            log.warning("Failed writing crash bundle: %s", write_err)
                    raise
    finally:
        if os.path.exists(pre_db_path):
            try:
                os.unlink(pre_db_path)
            except OSError:
                pass


async def _resolve_action_inner(
    session_id: int,
    user_id: int,
    action: Dict[str, Any],
    mode: str = "solo",
    stream_callback=None,
    actions: Optional[List[Dict[str, Any]]] = None,
) -> TurnResponse:
    """
    Unifies the turn resolution process across Discord and Web API using non-blocking DB access.
    """
    session, party = await adb(db.preload_turn_party_bundle, session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    import dataclasses
    from skill_check import CheckResult as _SkillCheckResult

    def _json_pick_default(obj: Any) -> Any:
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return dataclasses.asdict(obj)
        return str(obj)

    def _rehydrate_check_obj(c_val: Any, fallback_req: int = 10) -> Any:
        if isinstance(c_val, dict):
            return _SkillCheckResult(
                chance=int(c_val.get("chance") or 0),
                roll=float(c_val.get("roll") or 0.0),
                tier=str(c_val.get("tier") or "fail"),
                tier_label=str(c_val.get("tier_label") or "Action"),
                succeeded=bool(c_val.get("succeeded", False)),
                requirement=int(c_val.get("requirement") if c_val.get("requirement") is not None else fallback_req),
            )
        return c_val

    def _rehydrate_action_dict(act_obj: Any) -> Any:
        if not isinstance(act_obj, dict):
            return act_obj
        if isinstance(act_obj.get("check"), dict):
            act_obj["check"] = _rehydrate_check_obj(act_obj["check"], int(act_obj.get("requirement") or 10))
        st_out = act_obj.get("stealth_outcome")
        if isinstance(st_out, dict) and isinstance(st_out.get("check"), dict):
            st_out["check"] = _rehydrate_check_obj(st_out["check"], int(act_obj.get("requirement") or 10))
        return act_obj

    sync_picks_rollback_json: Optional[str] = None
    if actions is not None:
        actions = [_rehydrate_action_dict(a) for a in list(actions)]
        if actions and not action:
            action = actions[0]
        mp_already_spent = {
            (a.get("user_id") or (a.get("char") or {}).get("user_id", user_id)): a.get("mp_spent", 0)
            for a in actions
            if isinstance(a, dict) and a.get("_mp_already_deducted")
        }
        if mode == "sync":
            sync_picks_rollback_json = json.dumps(session.get("pending_picks") or {}, default=_json_pick_default)
            await adb(db.update_session, session_id, pending_picks_json="{}")
    elif mode == "sync" and len(party) > 1:
        picks = session.get("pending_picks", {})
        picks[str(user_id)] = action
        serialized_picks = json.dumps(picks, default=_json_pick_default)
        await adb(db.update_session, session_id, pending_picks_json=serialized_picks)

        if len(picks) < len(party):
            raise ValueError("waiting_for_party")

        # Everyone locked in
        sync_picks_rollback_json = serialized_picks
        actions = [_rehydrate_action_dict(a) for a in picks.values()]
        mp_already_spent = {
            (a.get("user_id") or (a.get("char") or {}).get("user_id", user_id)): a.get("mp_spent", 0)
            for a in actions
            if a.get("_mp_already_deducted")
        }
        await adb(db.update_session, session_id, pending_picks_json="{}")
    else:
        actions = [_rehydrate_action_dict(action)]
        mp_already_spent = (
            {user_id: action.get("mp_spent", 0)}
            if action.get("_mp_already_deducted")
            else {}
        )

    # Serialize action helper
    def _serialize_action(a):
        c = a.get("check")
        check_dict = None
        if c:
            check_dict = {
                "chance": getattr(c, "chance", a.get("rate")),
                "roll": getattr(c, "roll", None),
                "tier": getattr(c, "tier", a.get("tier", "fail")),
                "tier_label": getattr(c, "tier_label", "Action"),
                "succeeded": getattr(c, "succeeded", False)
            }
        return {
            "user_id": a.get("user_id", a.get("char", {}).get("user_id", 0)),
            "label": a.get("label", ""),
            "stat": a.get("stat", ""),
            "requirement": getattr(c, "requirement", a.get("requirement", 0)),
            "mp_spent": a.get("mp_spent", 0),
            "gold_spent": a.get("gold_spent", 0),
            "check": check_dict,
            "item_name": a.get("item_name"),
            "intent": a.get("intent"),
            "property_id": a.get("property_id") or "",
            "price": a.get("price") or 0,
            "sub_intent": a.get("sub_intent"),
            "ends_dialogue": a.get("ends_dialogue", False),
            "_quest_dialogue_handoff": bool(a.get("_quest_dialogue_handoff", False)),
            "dismisses_npc": a.get("dismisses_npc", ""),
            "target_name": a.get("target_name") or a.get("target_npc") or a.get("combat_target"),
            "target_npc": a.get("target_npc") or a.get("target_name") or a.get("combat_target"),
            "combat_target": a.get("combat_target") or a.get("target_npc") or a.get("target_name"),
            "target_node_id": a.get("target_node_id") or "",
            "target_location": a.get("target_location") or "",
            "spell_id": a.get("spell_id"),
            "is_pact_skill": bool(a.get("is_pact_skill", False)),
            "is_lethal_overdraw": bool(a.get("is_lethal_overdraw", False)),
            "_pact_cast_meta": dict(a["_pact_cast_meta"]) if isinstance(a.get("_pact_cast_meta"), dict) else None,
            "incursion_action": a.get("incursion_action") or "",
            "site_action": a.get("site_action") or "",
            "site_id": a.get("site_id") or "",
            "step_index": a.get("step_index"),
            "use_ward": bool(a.get("use_ward", False)),
            "ward_item_name": a.get("ward_item_name") or "",
            "quest_id": a.get("quest_id"),
            "sub_obj_id": a.get("sub_obj_id"),
            "stage_index": a.get("stage_index"),
            "approach": a.get("approach") or "",
            "quest_approach": a.get("quest_approach") or "",
            "rush_climax": bool(a.get("rush_climax", False)),
            "is_quest_action": bool(a.get("is_quest_action", False)),
            "is_climax_action": bool(a.get("is_climax_action", False)),
            "is_story_quest": bool(a.get("is_story_quest", False)),
            "contract_type": a.get("contract_type") or "",
            "breakthrough_leveraged": bool(a.get("breakthrough_leveraged", False)),
            "clue_pair_ids": list(a.get("clue_pair_ids") or []),
            "active_recall": a.get("active_recall"),
            "is_stealth": a.get("is_stealth", False),
            "stance": a.get("stance", "normal"),
            "stealth_state": a.get("stealth_state"),
            "stealth_outcome": {
                k: (v.__dict__ if hasattr(v, "__dict__") and not isinstance(v, dict) else v)
                for k, v in a["stealth_outcome"].items()
            } if isinstance(a.get("stealth_outcome"), dict) else None,
        }

    import uuid
    turn_id = str(uuid.uuid4())
    prev_st_rollback = None
    for a in actions:
        if isinstance(a, dict) and isinstance(a.get("_prev_stealth_state"), dict) and prev_st_rollback is None:
            prev_st_rollback = a.get("_prev_stealth_state")
        if isinstance(a, dict) and isinstance(a.get("stealth_state"), dict):
            session["stealth_state"] = copy.deepcopy(a["stealth_state"])
    # Compute 1-based monotonic gameplay turn number before snapshot & resolve_turn
    _hist_actions_cnt = sum(
        1 for _h in (session.get("history") or [])
        if not (isinstance(_h, dict) and _h.get("type") == "scene")
    )
    pre_turn_count_val = int(session.get("turn_count") or 0)
    pre_turn_history_snapshot = copy.deepcopy(list(session.get("history") or []))
    target_turn = max(pre_turn_count_val, _hist_actions_cnt) + 1
    pre_turn_daily_incursions_snapshot = copy.deepcopy(
        session.get("daily_incursions") if "daily_incursions" in session else session.get("daily_breaches")
    )
    # Snapshot every tracked key unconditionally (None when absent) so a hard failure on the FIRST turn
    # that creates one of these keys clears it on rollback instead of committing partial anomaly state.
    pre_turn_anomaly_extra_snapshot = {
        _ek: copy.deepcopy(session.get(_ek))
        for _ek in (
            "anomaly_field_log",
            "retired_folklore_ids",
            "folklore_cooldowns",
            "contained_anomalies_log",
            "anomalous_vault_log",
            "anomalous_vault_requisitions",
            "anomalous_faction_state",
            "last_school_hours_incident_day",
            "dialogue_partners",
            "folklore_villager_roster",
            "folklore_roster_pc_bucket",
            "folklore_free_tokens_granted",
            "leyline_spirit_passage_unlocked",
            "leyline_unlocked_turn",
            "leyline_unlock_reason",
            "prompt_epoch",
            "_just_advanced_quest_ids",
        )
    }
    pre_turn_dialogue_partner = session.get("dialogue_partner")

    pre_turn_char_status_effects: Dict[int, list] = {}
    for _p_entry in (party or []):
        _p_char = _p_entry[0] if isinstance(_p_entry, (tuple, list)) and _p_entry else _p_entry
        if isinstance(_p_char, dict) and _p_char.get("user_id"):
            try:
                pre_turn_char_status_effects[int(_p_char["user_id"])] = copy.deepcopy(
                    list(_p_char.get("status_effects") or [])
                )
            except Exception:
                pass

    snapshot = {
        "turn_id": turn_id,
        "status": "pending",
        "target_turn": target_turn,
        "fallback_reason": None,
        "retry_attempts": 0,
        "mode": mode,
        "actions": [_serialize_action(a) for a in actions],
        "pre_turn": {
            "pre_turn_count": pre_turn_count_val,
            "location": session.get("current_location", ""),
            "current_node_id": session.get("current_node_id", ""),
            "focal_point": session.get("focal_point", ""),
            "narrative": session.get("narrative", ""),
            "scene_title": session.get("scene_title", ""),
            "npcs": copy.deepcopy(list(session.get("current_npcs") or [])),
            "party_npcs": copy.deepcopy(list(session.get("party_npcs") or [])),
            "enemies": copy.deepcopy(list(session.get("nearby_enemies") or [])),
            "combat_threat_ledger": copy.deepcopy(session.get("combat_threat_ledger") or {}),
            "combat_boss_telegraph": copy.deepcopy(session.get("combat_boss_telegraph") or {}),
            "char_status_effects": {str(k): copy.deepcopy(v) for k, v in pre_turn_char_status_effects.items()},
            "daily_incursions": copy.deepcopy(pre_turn_daily_incursions_snapshot),
            "stealth_state": prev_st_rollback,
            "player_resonance_pips": (
                copy.deepcopy(session["player_resonance_pips"])
                if isinstance(session.get("player_resonance_pips"), dict)
                else int(session.get("player_resonance_pips") or 0)
            ),
            "telemetry_calibrations_used": copy.deepcopy(session.get("telemetry_calibrations_used") or {}),
            "event_pity_counter": float(session.get("event_pity_counter") or 0.0),
            "rumor_pity_counter": float(session.get("rumor_pity_counter") or 0.0),
            "minor_event_pity_counter": float(session.get("minor_event_pity_counter") or 0.0),
            "anomalous_faction_state": copy.deepcopy(session.get("anomalous_faction_state")),
            "party_factions": {
                int(c["user_id"]): {
                    "joined_faction_id": c.get("joined_faction_id"),
                    "joined_faction_name": c.get("joined_faction_name"),
                    "faction_rank": int(c.get("faction_rank") or 0),
                    "faction_title": str(c.get("faction_title") or ""),
                }
                for c, _ in (party or [])
                if isinstance(c, dict) and c.get("user_id")
            },
        },
        "applied": {}
    }
    def _pre_turn_setup_bundle() -> dict[str, Any]:
        with db.UnitOfWork():
            db.set_turn_snapshot(session_id, snapshot)
            we_snap_res: dict[str, Any] = {}
            try:
                we_snap_res = db.get_world_events_snapshot(session_id) or {}
            except Exception:
                we_snap_res = {}
            try:
                db.snapshot_session_physical_state_for_turn(session_id, pre_turn_count_val)
                db.snapshot_session_social_state_for_turn(session_id, pre_turn_count_val)
                db.save_contract_turn_snapshot(session_id, pre_turn_count_val)
            except Exception as _ps_pre_err:
                log.warning("Pre-turn physical/social snapshot failed (non-fatal): %s", _ps_pre_err)
            return we_snap_res

    we_snap = await adb(_pre_turn_setup_bundle)
    if isinstance(session, dict):
        session["_target_turn"] = target_turn
        session["_just_advanced_quest_ids"] = []
        session["_world_events_snapshot"] = dict(we_snap or {})
    turn_ctx = game_engine.TurnExecutionContext(session_id, session, party=party, actions=actions)
    turn_ctx.clock.target_turn = target_turn
    turn_ctx.world_stage.world_events_snapshot = dict(we_snap or {})
    turn_ctx.world_stage.just_advanced_quest_ids = []

    pre_turn_nearby_enemies_snapshot = copy.deepcopy(list(session.get("nearby_enemies") or []))
    pre_turn_had_threat_ledger = isinstance(session, dict) and "combat_threat_ledger" in session
    pre_turn_had_boss_telegraph = isinstance(session, dict) and "combat_boss_telegraph" in session

    async def _rollback_turn_failure(err: BaseException) -> None:
        if isinstance(session, dict):
            session.pop("_target_turn", None)
            session.pop("_pre_turn_quest_res", None)
            session["nearby_enemies"] = copy.deepcopy(pre_turn_nearby_enemies_snapshot)
            session["current_npcs"] = copy.deepcopy(snapshot["pre_turn"]["npcs"])
            if pre_turn_had_threat_ledger:
                session["combat_threat_ledger"] = copy.deepcopy(snapshot["pre_turn"]["combat_threat_ledger"])
            else:
                session.pop("combat_threat_ledger", None)
            if pre_turn_had_boss_telegraph:
                session["combat_boss_telegraph"] = copy.deepcopy(snapshot["pre_turn"]["combat_boss_telegraph"])
            else:
                session.pop("combat_boss_telegraph", None)
        if isinstance(err, Exception):
            log.error("Hard failure during turn execution for session %s: %s", session_id, err, exc_info=True)
        snapshot["status"] = "failed_hard"
        if _is_llm_unavailable_exception(err):
            snapshot["fallback_reason"] = "models_unavailable"
        else:
            snapshot["fallback_reason"] = "engine_error"
            snapshot["error"] = f"{type(err).__name__}: {err}"

        rollback_kwargs: Dict[str, Any] = {
            "turn_count": pre_turn_count_val,
            "history_json": json.dumps(pre_turn_history_snapshot, default=str),
            "nearby_enemies": pre_turn_nearby_enemies_snapshot,
            "current_npcs": snapshot["pre_turn"]["npcs"],
            "dialogue_partner": pre_turn_dialogue_partner,
            "combat_threat_ledger": copy.deepcopy(snapshot["pre_turn"]["combat_threat_ledger"]),
            "combat_boss_telegraph": copy.deepcopy(snapshot["pre_turn"]["combat_boss_telegraph"]),
        }
        has_party_npcs_rb = "party_npcs" in snapshot["pre_turn"]
        if has_party_npcs_rb:
            rollback_kwargs["party_npcs"] = snapshot["pre_turn"]["party_npcs"]
        if prev_st_rollback is not None:
            rollback_kwargs["stealth_state"] = prev_st_rollback
        if sync_picks_rollback_json is not None:
            rollback_kwargs["pending_picks_json"] = sync_picks_rollback_json
        extra_restore: Dict[str, Any] = dict(pre_turn_anomaly_extra_snapshot)
        extra_restore["player_resonance_pips"] = copy.deepcopy(snapshot["pre_turn"]["player_resonance_pips"])
        extra_restore["telemetry_calibrations_used"] = copy.deepcopy(snapshot["pre_turn"]["telemetry_calibrations_used"])
        if pre_turn_daily_incursions_snapshot is not None:
            extra_restore["daily_incursions"] = pre_turn_daily_incursions_snapshot
            extra_restore["daily_breaches"] = pre_turn_daily_incursions_snapshot
        if extra_restore:
            rollback_kwargs["extra"] = extra_restore

        from services.examine_service import invalidate_examine_cache

        def _apply_turn_failure_rollback_bundle() -> None:
            with db.UnitOfWork():
                db.rollback_session_normalized_state_after_turn(
                    session_id,
                    pre_turn_count_val,
                    invalidate_cache_cb=invalidate_examine_cache,
                )
                if has_party_npcs_rb:
                    db.set_session_party_npcs(session_id, snapshot["pre_turn"]["party_npcs"])
                for _rb_uid, _rb_effs in pre_turn_char_status_effects.items():
                    db.set_status_effects(int(_rb_uid), copy.deepcopy(_rb_effs))
                db.update_session(session_id, **rollback_kwargs)
                db.set_turn_snapshot(session_id, snapshot)

        try:
            await adb(_apply_turn_failure_rollback_bundle)
            if has_party_npcs_rb and isinstance(session, dict):
                session["party_npcs"] = copy.deepcopy(snapshot["pre_turn"]["party_npcs"])
            for _rb_uid, _rb_effs in pre_turn_char_status_effects.items():
                for _p_entry in (party or []):
                    _p_char = _p_entry[0] if isinstance(_p_entry, (tuple, list)) and _p_entry else _p_entry
                    if isinstance(_p_char, dict) and _p_char.get("user_id") and int(_p_char["user_id"]) == int(_rb_uid):
                        _p_char["status_effects"] = copy.deepcopy(_rb_effs)
        except Exception as _rb_err:
            log.error(
                "Atomic turn failure rollback failed for session %s: %s",
                session_id,
                _rb_err,
                exc_info=True,
            )
            await adb(db.set_turn_snapshot, session_id, snapshot)

    # Resolve the turn with the LLM — resolve_turn now always returns a dict
    try:
        for _pa in actions:
            if isinstance(_pa, dict) and str(_pa.get("intent") or "").strip().lower() == "property_purchase":
                _p_uid = int(_pa.get("user_id") or (_pa.get("char") or {}).get("user_id") or user_id)
                _p_id = str(_pa.get("property_id") or "").strip()
                if not _p_id and _pa.get("target_node_id"):
                    from mechanics.world.locations.realty_catalog import find_realty_by_node_id
                    _c_fb = await adb(find_realty_by_node_id, str(_pa["target_node_id"]), session_or_id=session or session_id)
                    if _c_fb:
                        _p_id = _c_fb["property_id"]
                if _p_id:
                    _buy_res = await adb(db.atomic_purchase_property, session_id, _p_uid, _p_id, turn_number=target_turn)
                    if _buy_res.get("ok"):
                        _pa["gold_spent"] = 0
                        _pa["_gold_already_deducted"] = True
                        _updated_gold = _buy_res.get("new_gold")
                        if _updated_gold is None:
                            _updated_gold = _buy_res.get("gold")
                        for _idx_m, (_pc, _pinv) in enumerate(party):
                            if int(_pc.get("user_id") or 0) == _p_uid:
                                if _updated_gold is not None:
                                    _pc["gold"] = int(_updated_gold)
                                party[_idx_m] = (_pc, _pinv)
                    else:
                        _pa["target_node_id"] = ""
                        _pa["target_location"] = ""
                        _pa["label"] = f"Inspect the realty listing outside ({_buy_res.get('message') or _buy_res.get('reason') or 'purchase declined'})"

        resolve_kwargs: Dict[str, Any] = {"stream_callback": stream_callback}
        if _callable_accepts_kwarg(game_engine.resolve_turn, "ctx"):
            resolve_kwargs["ctx"] = turn_ctx
        outcome = await game_engine.resolve_turn(
            session,
            party,
            actions,
            **resolve_kwargs,
        )
        if isinstance(outcome, dict) and isinstance(session, dict) and "stealth_state" not in outcome:
            outcome["stealth_state"] = session.get("stealth_state")
    except BaseException as e:
        await _get_turn_service()._await_uninterruptible(_rollback_turn_failure(e), reraise_cancel=False)
        raise e

    if isinstance(outcome, dict):
        outcome["_target_turn"] = target_turn

    # Apply mechanics (includes quest & waypoint updates via _reduce_quests_and_waypoints)
    try:
        apply_kwargs: Dict[str, Any] = {"actions": actions}
        if _callable_accepts_kwarg(game_engine.apply_outcome, "ctx"):
            apply_kwargs["ctx"] = turn_ctx
        items_gained = await _get_turn_service()._await_uninterruptible(
            adb(
                game_engine.apply_outcome,
                session_id,
                party,
                outcome,
                mp_already_spent,
                **apply_kwargs,
            ),
            reraise_cancel=True,
        )
    except BaseException as e:
        await _get_turn_service()._await_uninterruptible(_rollback_turn_failure(e), reraise_cancel=False)
        raise e
    finally:
        if isinstance(outcome, dict):
            outcome.pop("_target_turn", None)
        if isinstance(session, dict):
            session.pop("_target_turn", None)
    if not isinstance(items_gained, dict):
        items_gained = {}
    if user_id not in items_gained:
        items_gained[user_id] = []

    raw_hist_pre = list(session.get("history") or [])
    if not raw_hist_pre and session.get("narrative"):
        raw_hist_pre.append({
            "type": "scene",
            "scene_title": session.get("scene_title") or "Beginning",
            "narrative": session.get("narrative") or "",
            "next_narrative": session.get("narrative") or "",
            "location": session.get("current_location") or "",
            "scene_image_url": session.get("scene_image_url"),
        })
    new_hist_ref: List[List[Any]] = [list(raw_hist_pre)]

    from mechanics.world.world_events import build_client_world_pulse_payload as _build_wp_payload

    def _post_turn_finalize_and_commit_bundle() -> Tuple[
        Optional[Dict[str, Any]],
        Optional[Dict[str, Any]],
        List[Any],
        int,
        List[int],
        Dict[Any, int],
        Dict[Any, List[int]],
        Optional[Tuple[int, int]],
    ]:
        prewarm_args: Optional[Tuple[int, int]] = None
        with db.UnitOfWork() as uow_conn:
            # Post-turn World Event & Rumor Resolution + Mid-Rumor Companion/Romance Loyalty Promotion
            if isinstance(outcome, dict):
                try:
                    from mechanics.world.world_events import handle_mid_rumor_npc_promotion, on_quest_or_bounty_completed
                    _completed_qids = set()
                    for _qu in (outcome.get("quest_updates") or []):
                        if isinstance(_qu, dict) and str(_qu.get("status") or "").strip().lower() == "completed" and _qu.get("quest_id"):
                            _qid = str(_qu["quest_id"])
                            _completed_qids.add(_qid)
                            on_quest_or_bounty_completed(
                                session_id,
                                _qid,
                                quest_type=str(_qu.get("quest_type") or "bounty"),
                                is_story_quest=bool(_qu.get("is_story_quest")),
                            )
                    for _rn in (outcome.get("_quest_reward_notices") or []):
                        if isinstance(_rn, dict) and _rn.get("claimed") and _rn.get("quest_id"):
                            _qid = str(_rn["quest_id"])
                            if _qid not in _completed_qids:
                                _completed_qids.add(_qid)
                                on_quest_or_bounty_completed(
                                    session_id,
                                    _qid,
                                    quest_type=str(_rn.get("quest_type") or "bounty"),
                                    is_story_quest=bool(_rn.get("is_story_quest")),
                                )

                    _fk_scen_key = str((session or {}).get("scenario") or "fantasy")
                    _is_fk_scen = bool(
                        scenario_data.is_anomalous_incursions_scenario(_fk_scen_key)
                        or scenario_data.is_anomalous_high_school_scenario(_fk_scen_key)
                        or "urban_anomalies" in _fk_scen_key.lower()
                    )
                    for _ru in (outcome.get("relationship_updates") or []):
                        if isinstance(_ru, dict) and _ru.get("name"):
                            _trk = str(_ru.get("track") or "").strip().lower()
                            _new_sc = int(_ru.get("new_score") if _ru.get("new_score") is not None else (_ru.get("score") or 0))
                            if _trk in ("romantic", "romance", "lover", "spouse") or _new_sc >= 70:
                                handle_mid_rumor_npc_promotion(session_id, npc_name=str(_ru["name"]))
                            if _is_fk_scen and (_trk in ("romantic", "romance", "lover", "spouse", "friend") or _new_sc >= 30):
                                from mechanics.social.folklore_roster import (
                                    befriend_folklore_villager,
                                    get_folklore_villager_spec,
                                    shift_kitsune_form,
                                )
                                _fk_spec = get_folklore_villager_spec(
                                    session_id,
                                    str(_ru["name"]),
                                    session=session,
                                    persist_db=False,
                                )
                                if _fk_spec:
                                    befriend_folklore_villager(
                                        session_id,
                                        str(_ru["name"]),
                                        turn_number=target_turn,
                                    )
                                    if (
                                        _new_sc >= 45
                                        and str(_fk_spec.get("folklore_village") or "") == "kitsune"
                                        and str(_fk_spec.get("race") or "") == "kitsune:myobu_fox"
                                    ):
                                        shift_kitsune_form(
                                            session_id,
                                            str(_ru["name"]),
                                            "kitsune:humanoid",
                                            turn_number=target_turn,
                                            shift_reason="bond_affinity",
                                        )
                except Exception as _we_post_err:
                    log.warning("World event post-turn hooks failed (non-fatal): %s", _we_post_err)

                # Campaign Epilogue Choice, Zero-Plot-Armor NPC Fallout, Combat & Partner-Verified Intimate Hooks
                try:
                    game_engine.resolve_post_turn_dossier_hooks(
                        session_id,
                        session,
                        outcome,
                        actions,
                        user_id,
                    )
                except Exception as _qd_post_err:
                    log.warning("Quest dossier post-turn hooks failed (non-fatal): %s", _qd_post_err)

                # Single post-turn snapshot bundle capturing both apply_outcome & post-turn dossier hooks
                try:
                    db.snapshot_session_physical_state_for_turn(session_id, target_turn)
                    db.snapshot_session_social_state_for_turn(session_id, target_turn)
                    db.save_contract_turn_snapshot(session_id, target_turn, overwrite=True)
                except Exception as _ps_post_err:
                    log.warning("Post-turn physical/social snapshot failed (non-fatal): %s", _ps_post_err)

                # Surface Threat Clock ticks & directives if time/sleep advanced during the turn
                tc_tick = (
                    (outcome.get("_sleep_info") or {}).get("threat_clock_tick")
                    or (outcome.get("_time_info") or {}).get("threat_clock_tick")
                    or outcome.get("threat_clock_tick")
                )
                if isinstance(tc_tick, dict) and tc_tick.get("ticked"):
                    outcome["threat_clock_tick"] = tc_tick
                    tc_dirs = [str(d) for d in (tc_tick.get("directives") or []) if d]
                    if tc_dirs:
                        existing_qd = list(outcome.get("quest_directives") or [])
                        outcome["quest_directives"] = existing_qd + tc_dirs

                # Option C Mid-Chapter Stage 2 Prewarm Hook check
                cur_ch = int(db.get_session_chapter(session_id) or 1)
                if cur_ch < 11:
                    next_ch = cur_ch + 1
                    last_pw_ch = (
                        turn_ctx.world_stage.last_prewarmed_chapter
                        if turn_ctx.world_stage.last_prewarmed_chapter is not None
                        else session.get("_last_prewarmed_chapter")
                    )
                    if last_pw_ch != next_ch:
                        active_sq = db.get_active_story_quest(session_id)
                        if active_sq:
                            sq_dos = db.get_quest_dossier(session_id, str(active_sq.get("quest_id") or ""))
                            climax_sp = (sq_dos or {}).get("climax_spec") or {}
                            m_stages = climax_sp.get("main_stages") or []
                            stage2_active = any(
                                (int(ms.get("stage_index") or 0) >= 2 and ms.get("status") in ("active", "completed"))
                                for ms in m_stages
                            ) or any(
                                bool(int(so.get("completed_stages") or 0) >= 1 or int(so.get("stage_index") or 1) >= 2)
                                for so in (active_sq.get("sub_objectives") or [])
                                if isinstance(so, dict)
                            )
                            if stage2_active:
                                session["_last_prewarmed_chapter"] = next_ch
                                turn_ctx.world_stage.last_prewarmed_chapter = next_ch
                                try:
                                    db.update_session(session_id, extra={"_last_prewarmed_chapter": next_ch})
                                except Exception:
                                    pass
                                prewarm_args = (cur_ch, next_ch)

            else:
                try:
                    db.snapshot_session_physical_state_for_turn(session_id, target_turn)
                    db.snapshot_session_social_state_for_turn(session_id, target_turn)
                    db.save_contract_turn_snapshot(session_id, target_turn, overwrite=True)
                except Exception as _ps_post_err:
                    log.warning("Post-turn physical/social snapshot failed (non-fatal): %s", _ps_post_err)

            if isinstance(outcome, dict):
                turn_ctx.notices.sync_from_outcome(outcome)

            # Re-tag quest choices now that arrival/skill_check waypoint progression has unlocked next stages
            from mechanics.social.physical_state import is_erotic_intimate_contact as _ts_is_erotic
            _ts_phys = (
                (outcome.get("_physical_state") if isinstance(outcome, dict) else None)
                or turn_ctx.world_stage.physical_state
                or {}
            )
            _ts_ic_str = str(_ts_phys.get("intimate_contact", "") if isinstance(_ts_phys, dict) else "")
            _ts_in_intimate = _ts_is_erotic(_ts_ic_str) or ("aftercare" in _ts_ic_str.lower())
            if (
                isinstance(outcome, dict)
                and (
                    outcome.get("_waypoint_notices")
                    or outcome.get("_quests_advanced_this_turn")
                    or turn_ctx.world_stage.just_advanced_quest_ids
                )
                and not _ts_in_intimate
                and not (game_engine.get_active_enemies(session) or game_engine.get_active_enemies(outcome))
            ):
                try:
                    from game_engine import prune_completed_stage_choices
                    from mechanics.world.waypoints import tag_and_enrich_quest_choices
                    lead_char = party[0][0] if party and party[0] else None
                    raw_c = prune_completed_stage_choices(
                        list(outcome.get("next_choices") or outcome.get("choices") or []),
                        outcome.get("_waypoint_notices") or [],
                    )

                    eff_loc = outcome.get("location") or session.get("current_location", "")
                    if outcome.get("dialogue_partners") is not None:
                        eff_dp = outcome.get("dialogue_partners")
                    elif "dialogue_partner" in outcome:
                        eff_dp = outcome.get("dialogue_partner")
                    else:
                        eff_dp = ...
                    eff_npcs = outcome.get("npcs_present")
                    if eff_dp is ...:
                        dp_raw = session.get("dialogue_partners")
                        if isinstance(dp_raw, list) and dp_raw:
                            eff_dp_list = [str(p).strip() for p in dp_raw if str(p).strip()]
                        elif session.get("dialogue_partner"):
                            eff_dp_list = [str(session["dialogue_partner"]).strip()]
                        else:
                            eff_dp_list = []
                    elif isinstance(eff_dp, list):
                        eff_dp_list = [str(p).strip() for p in eff_dp if str(p).strip()]
                    elif isinstance(eff_dp, str) and eff_dp.strip():
                        eff_dp_list = [eff_dp.strip()]
                    else:
                        eff_dp_list = []

                    adv_qids_for_enrich = (
                        outcome.get("_quests_advanced_this_turn")
                        or turn_ctx.world_stage.just_advanced_quest_ids
                        or None
                    )
                    enriched_c = tag_and_enrich_quest_choices(
                        raw_c,
                        session_id,
                        eff_loc,
                        scen_key=session.get("scenario", "fantasy"),
                        char=lead_char,
                        dialogue_partner=eff_dp,
                        current_npcs=eff_npcs,
                        just_advanced_quest_ids=adv_qids_for_enrich,
                    )

                    enriched_c = prune_completed_stage_choices(enriched_c, outcome.get("_waypoint_notices") or [])
                    if enriched_c:
                        if eff_dp_list:
                            from mechanics.social.conversation_choices import (
                                enforce_conversation_choice_bands,
                                pin_dialogue_exit_last,
                            )
                            sess_post = {
                                **session,
                                "current_location": eff_loc,
                                "dialogue_partners": eff_dp_list,
                                "dialogue_partner": eff_dp_list[0],
                            }
                            final_c = enforce_conversation_choice_bands(
                                enriched_c,
                                sess_post,
                                eff_dp_list,
                                party=party,
                                current_npcs=eff_npcs,
                            )
                            final_c = pin_dialogue_exit_last(final_c, eff_dp_list, max_total=8)
                        else:
                            from mechanics.narrative.intent import is_conversational_exit
                            filler_budget = 3
                            filler_used = 0
                            final_c = []
                            seen_post_lbls: set[str] = set()
                            for ec in enriched_c:
                                if not isinstance(ec, dict):
                                    continue
                                lbl_k = str(ec.get("label") or "").strip().lower()
                                if not lbl_k or lbl_k in seen_post_lbls:
                                    continue
                                stat_u = str(ec.get("stat") or "").upper()
                                int_l = str(ec.get("intent") or "").lower()
                                is_ess = bool(
                                    ec.get("is_quest_action")
                                    or ec.get("is_climax_action")
                                    or ec.get("_quest_dialogue_handoff")
                                    or ec.get("ends_dialogue")
                                    or ec.get("_pinned_dialogue_exit")
                                    or int_l == "dialogue_exit"
                                    or is_conversational_exit(lbl_k)
                                    or ec.get("_priority_slot")
                                    or ec.get("_npc_speak_choice")
                                    or stat_u == "FREE"
                                    or int_l in ("dialogue_init", "dialogue", "social_talk")
                                    or lbl_k.startswith(("speak with ", "talk to ", "talk with "))
                                )
                                if is_ess:
                                    seen_post_lbls.add(lbl_k)
                                    final_c.append(ec)
                                elif filler_used < filler_budget:
                                    filler_used += 1
                                    seen_post_lbls.add(lbl_k)
                                    final_c.append(ec)
                        final_c = game_engine.order_choices_canonically(
                            final_c,
                            in_dialogue=bool(eff_dp_list),
                        )
                        outcome["next_choices"] = final_c
                        outcome["choices"] = final_c
                except Exception as e:
                    log.warning("tag_and_enrich_quest_choices post-update failed (non-fatal): %s", e)

            # Apply merchant encounter state deterministically (clears stale availability when omitted)
            if isinstance(outcome, dict):
                try:
                    apply_merchant_encounter_result(session_id, outcome.get("merchant_encounter"))
                except Exception as e:
                    log.warning("apply_merchant_encounter_result failed (non-fatal): %s", e)

            # Calculate XP across all acting party members
            xp_l_gained = 0
            lvls_l_gained: List[int] = []
            xp_by_u: Dict[Any, int] = {}
            levels_by_u: Dict[Any, List[int]] = {}
            uid_char_cache: Dict[Any, Any] = {
                int(c["user_id"]): c
                for c in (db.get_session_characters(session_id) or [])
                if isinstance(c, dict) and c.get("user_id") is not None
            }
            if user_id not in uid_char_cache:
                uid_char_cache[user_id] = db.get_character(user_id)
            char_row_main = uid_char_cache.get(user_id)

            deduction_xp_bonus = int(outcome.get("_deduction_xp_bonus") or 0) if isinstance(outcome, dict) else 0
            for a in actions:
                uid = a.get("user_id") or (a.get("char") or {}).get("user_id", user_id)
                if uid not in uid_char_cache:
                    uid_char_cache[uid] = db.get_character(uid)
                char_for_xp = uid_char_cache[uid]
                if not char_for_xp:
                    continue

                check_a = a.get("check")
                if isinstance(check_a, dict):
                    check_tier = check_a.get("tier", "fail")
                elif hasattr(check_a, "tier"):
                    check_tier = check_a.tier
                else:
                    check_tier = a.get("tier", "fail")
                base_xp = XP_REWARDS.get(check_tier, 0)

                bonus_xp = deduction_xp_bonus
                auth_xp_map = (outcome.get("_auth_combat_xp") if isinstance(outcome, dict) else None) or {}
                if isinstance(auth_xp_map, dict):
                    bonus_xp += max(0, int(auth_xp_map.get(char_for_xp["name"].lower(), 0) or 0))

                total_xp = base_xp + bonus_xp
                lvls = db.add_xp(uid, total_xp)
                xp_by_u[uid] = total_xp
                levels_by_u[uid] = list(lvls or [])

                if uid == user_id:
                    xp_l_gained = total_xp
                    lvls_l_gained = list(lvls or [])

            # Build history entry
            outcome_only_nar = str(outcome.get("outcome_narrative") or "").strip()
            next_only_nar = str(outcome.get("next_narrative") or outcome.get("narrative") or "").strip()
            outcome_nar = outcome_only_nar or next_only_nar
            next_scene_title = str(outcome.get("scene_title") or session.get("scene_title") or "").strip()
            check = action.get("check")
            tier_label = check.tier_label if hasattr(check, "tier_label") else action.get("tier", "action")
            label = action.get("label", "Action")

            char_name = char_row_main["name"] if char_row_main else "Hero"

            witnesses = [char_name]
            npcs_present = outcome.get("npcs_present") or []
            for npc in npcs_present:
                n_name = game_engine._get_npc_name(npc)
                if n_name and n_name.lower() != "none" and n_name not in witnesses:
                    witnesses.append(n_name)

            history_entry = {
                "type": "action",
                "character_name": char_name,
                "label": label,
                "tier": check.tier if hasattr(check, "tier") else action.get("tier", "action"),
                "tier_label": tier_label,
                "stat": action.get("stat"),
                "roll": check.roll if hasattr(check, "roll") else action.get("roll"),
                "chance": check.chance if hasattr(check, "chance") else action.get("rate"),
                "requirement": action.get("requirement"),
                "success": check.succeeded if hasattr(check, "succeeded") else action.get("success", False),
                "narrative": outcome_nar,
                "outcome_narrative": outcome_only_nar,
                "next_narrative": next_only_nar,
                "scene_title": next_scene_title,
                "location": outcome.get("location") or session.get("current_location") or "",
                "items_gained": items_gained.get(user_id, []),
                "xp_gained": xp_l_gained,
                "levels_gained": lvls_l_gained,
                "mp_spent": action.get("mp_spent", 0),
                "character_outcomes": outcome.get("character_outcomes") or [],
                "relationship_updates": outcome.get("relationship_updates") or [],
                "social_feedback_pills": list(outcome.get("social_feedback_pills") or []),
                "active_dialogue_mood": outcome.get("active_dialogue_mood"),
                "faction_updates": outcome.get("faction_updates") or [],
                "quest_updates": outcome.get("quest_updates") or [],
                "witnessed_by": witnesses,
                "is_fallback": bool(outcome.get("_is_fallback_narrative") or outcome.get("is_fallback")),
            }
            combat_log = outcome.get("combat_log") or outcome.get("_combat_log")
            if combat_log:
                history_entry["combat_log"] = combat_log
            if outcome.get("_enemy_attack_notice"):
                history_entry["enemy_attack_notice"] = outcome["_enemy_attack_notice"]
            if outcome.get("intimate_update"):
                history_entry["intimate_update"] = outcome["intimate_update"]
            if outcome.get("_refractory_recovered_notice"):
                history_entry["_refractory_recovered_notice"] = outcome["_refractory_recovered_notice"]
            if outcome.get("threat_clock_tick"):
                history_entry["threat_clock_tick"] = outcome["threat_clock_tick"]

            has_dialogue = bool(outcome.get("dialogue_partners") or outcome.get("dialogue_partner"))
            dyn_limit = 12 if has_dialogue else 4
            built_hist = game_engine.push_history(raw_hist_pre, history_entry, limit=dyn_limit)
            new_hist_ref[0] = built_hist
            _epoch_to_save = outcome.pop("_prompt_epoch", None) if isinstance(outcome, dict) else None

            update_kwargs: Dict[str, Any] = {
                "history_json": json.dumps(built_hist, default=str),
                "turn_count": target_turn,
            }
            if isinstance(_epoch_to_save, dict):
                update_kwargs["extra"] = {"prompt_epoch": _epoch_to_save}
            db.update_session(session_id, **update_kwargs)
            f_sess = db.get_session(session_id)
            n_char = db.get_character(user_id)
            if isinstance(f_sess, dict):
                f_sess["world_pulse"] = _build_wp_payload(session_id)
            snapshot["status"] = "completed"
            snapshot["applied"] = {
                "character_outcomes": outcome.get("character_outcomes", []),
                "items_gained": items_gained,
                "xp_gained": dict(xp_by_u),
                "location": outcome.get("location", ""),
                "current_node_id": outcome.get("current_node_id") or (f_sess or {}).get("current_node_id", ""),
                "focal_point": outcome.get("focal_point") or (f_sess or {}).get("focal_point", ""),
                "npcs_present": (
                    outcome.get("npcs_present")
                    if outcome.get("npcs_present") is not None
                    else list((f_sess or {}).get("current_npcs") or [])
                ),
                "nearby_enemies": (
                    outcome.get("nearby_enemies")
                    if outcome.get("nearby_enemies") is not None
                    else list((f_sess or {}).get("nearby_enemies") or [])
                ),
                "deceased_characters": outcome.get("deceased_characters", []),
                "dead_enemies": outcome.get("dead_enemies", []),
                "time_info": outcome.get("_time_info", {}),
                "sleep_info": outcome.get("_sleep_info"),
                "quest_updates": outcome.get("quest_updates", []),
                "relationship_updates": outcome.get("relationship_updates", []),
                "social_feedback_pills": list(outcome.get("social_feedback_pills") or []),
                "active_dialogue_mood": outcome.get("active_dialogue_mood"),
                "dialogue_partner": (
                    outcome.get("dialogue_partner")
                    if "dialogue_partner" in outcome
                    else (f_sess or {}).get("dialogue_partner")
                ),
                "dialogue_partners": outcome.get("dialogue_partners", []),
                "cast_state": outcome.get("_staged_cast_state") or (f_sess or {}).get("cast_state"),
                "intimate_update": outcome.get("intimate_update"),
                "_physical_state": outcome.get("_physical_state"),
                "_refractory_recovered_notice": outcome.get("_refractory_recovered_notice"),
                "event_pity_counter": float((f_sess or {}).get("event_pity_counter") or 0.0),
                "rumor_pity_counter": float((f_sess or {}).get("rumor_pity_counter") or 0.0),
                "minor_event_pity_counter": float((f_sess or {}).get("minor_event_pity_counter") or 0.0),
            }
            db.set_turn_snapshot(session_id, snapshot)
            try:
                db.prune_session_turn_snapshots(uow_conn, session_id)
            except Exception as _prune_err:
                log.warning("Turn snapshot prune failed for session %s: %s", session_id, _prune_err)

        try:
            db.maybe_run_wal_maintenance()
        except Exception as _wal_err:
            log.warning("WAL maintenance check failed for session %s: %s", session_id, _wal_err)

        return f_sess, n_char, built_hist, xp_l_gained, lvls_l_gained, xp_by_u, levels_by_u, prewarm_args

    try:
        (
            fresh_session,
            new_char,
            new_hist,
            xp_gained,
            levels_gained,
            xp_by_user,
            levels_by_user,
            prewarm_args,
        ) = await _get_turn_service()._await_uninterruptible(
            adb(_post_turn_finalize_and_commit_bundle), reraise_cancel=True
        )
        if prewarm_args is not None:
            pw_cur_ch, pw_next_ch = prewarm_args
            from game_engine.quest_lifecycle import prewarm_chapter_ahead
            pw_task = asyncio.create_task(
                prewarm_chapter_ahead(
                    session_id=session_id,
                    current_chapter=pw_cur_ch,
                    target_chapter=pw_next_ch,
                )
            )
            _BACKGROUND_TASKS.add(pw_task)
            pw_task.add_done_callback(_BACKGROUND_TASKS.discard)
    except asyncio.CancelledError:
        latest_sess = None
        try:
            latest_sess = await _get_turn_service()._await_uninterruptible(
                adb(db.get_session, session_id), reraise_cancel=False
            )
        except Exception:
            latest_sess = None
        await _get_turn_service()._await_uninterruptible(
            _get_turn_service()._finalize_and_save_scene(
                session_id=session_id,
                session_obj=latest_sess or session,
                outcome=outcome,
                lead_char=(dict(party[0][0]) if party and party[0] else None),
                history=new_hist_ref[0],
                mode=mode,
                is_retry=False,
            ),
            reraise_cancel=False,
        )
        raise
    except Exception as post_err:
        await _get_turn_service()._await_uninterruptible(_rollback_turn_failure(post_err), reraise_cancel=False)
        raise

    async def _run_finalize_memory_after_prose(final_hist: list, final_outcome: dict) -> None:
        try:
            from mechanics.system.memory.digest import is_arc_boundary_event
            _arc_boundary = is_arc_boundary_event(
                session if isinstance(session, dict) else {},
                actions,
                final_outcome if isinstance(final_outcome, dict) else {},
            )
            _present_npc_names = [
                n_nm for npc in ((final_outcome or {}).get("npcs_present") or outcome.get("npcs_present") or [])
                for n_nm in [game_engine._get_npc_name(npc)]
                if n_nm and n_nm.lower() != "none"
            ]
            _active_qids = [
                str(qu.get("quest_id") or qu.get("title") or "").strip()
                for qu in ((final_outcome or {}).get("quest_updates") or outcome.get("quest_updates") or [])
                if isinstance(qu, dict) and (qu.get("quest_id") or qu.get("title"))
            ]
            await adb(
                db.finalize_turn_memory,
                session_id,
                target_turn,
                final_hist,
                _present_npc_names,
                str((final_outcome or {}).get("location") or outcome.get("location") or session.get("current_location") or ""),
                _active_qids,
                _arc_boundary,
            )
        except Exception as _mem_err:
            log.warning("Post-turn finalize_turn_memory failed for session %s: %s", session_id, _mem_err)

    lead_char_for_scene = dict(new_char) if new_char else (dict(party[0][0]) if party and party[0] else None)
    from mechanics.world.locations import is_anomalous_realty_scenario, build_realty_payload

    if outcome.get("_is_fallback_narrative"):
        if outcome.get("fallback_reason") == "models_unavailable":
            snapshot["fallback_reason"] = "models_unavailable"
            await adb(db.set_turn_snapshot, session_id, snapshot)
            log.info(
                "Skipping auto-recovery narration pass for session %s because models are unavailable.",
                session_id,
            )
        else:
            log.info(f"Auto-recovery triggered for session {session_id} due to empty prose.")
            try:
                recovered_response = await _get_turn_service().retry_narration(session_id, user_id, stream_callback=stream_callback)
                if mode in ("turn", "multi"):
                    await adb(db.advance_turn, session_id)
                recovered_hist = list((recovered_response.session or {}).get("history") or new_hist)
                await _run_finalize_memory_after_prose(recovered_hist, recovered_response.outcome)
                refreshed_sess = await adb(db.get_session, session_id)
                if isinstance(refreshed_sess, dict):
                    refreshed_sess["world_pulse"] = await adb(_build_wp_payload, session_id)
                    try:
                        if is_anomalous_realty_scenario(str(refreshed_sess.get("scenario") or "")):
                            refreshed_sess["realty"] = await adb(build_realty_payload, session_id, user_id)
                    except Exception:
                        pass
                    recovered_response.session = refreshed_sess
                recovered_response.actions = actions
                recovered_response.items_gained_by_user = items_gained
                recovered_response.xp_gained = xp_gained
                recovered_response.levels_gained = levels_gained
                recovered_response.xp_by_user = xp_by_user
                recovered_response.levels_by_user = levels_by_user
                return recovered_response
            except asyncio.CancelledError:
                await _get_turn_service()._await_uninterruptible(
                    _get_turn_service()._finalize_and_save_scene(
                        session_id=session_id,
                        session_obj=fresh_session,
                        outcome=outcome,
                        lead_char=lead_char_for_scene,
                        history=new_hist,
                        mode=mode,
                        is_retry=False,
                    ),
                    reraise_cancel=False,
                )
                raise
            except Exception as e:
                log.warning("Auto-recovery narration pass failed: %s", e)
                snapshot["fallback_reason"] = "empty_prose"
                await adb(db.set_turn_snapshot, session_id, snapshot)
                outcome["fallback_reason"] = "empty_prose"

    scene_title, next_narrative, cleaned_choices = await _get_turn_service()._await_uninterruptible(
        _get_turn_service()._finalize_and_save_scene(
            session_id=session_id,
            session_obj=fresh_session,
            outcome=outcome,
            lead_char=lead_char_for_scene,
            history=new_hist,
            mode=mode,
            is_retry=False,
        ),
        reraise_cancel=False,
    )

    await _get_turn_service()._await_uninterruptible(
        _run_finalize_memory_after_prose(new_hist, outcome), reraise_cancel=False
    )
    def _load_final_session_with_realty() -> Optional[Dict[str, Any]]:
        try:
            scen_hint = str((fresh_session or {}).get("scenario") or "")
            if not scen_hint:
                _s_hint_row = db.get_session(session_id)
                scen_hint = str((_s_hint_row or {}).get("scenario") or "")
            if is_anomalous_realty_scenario(scen_hint):
                if not any(p.get("is_starter") for p in db.get_player_properties(session_id)):
                    db.grant_or_relocate_starter_quarters(session_id)
        except Exception:
            pass
        with db.ReadUnitOfWork():
            s_row = db.get_session(session_id)
            if not isinstance(s_row, dict):
                return None
            s_row["world_pulse"] = fresh_session.get("world_pulse") if isinstance(fresh_session, dict) else None
            try:
                if is_anomalous_realty_scenario(str(s_row.get("scenario") or "")):
                    s_row["realty"] = build_realty_payload(session_id, user_id, persist_db=False)
            except Exception:
                pass
            return s_row

    refreshed_base_sess = await adb(_load_final_session_with_realty)
    if not isinstance(refreshed_base_sess, dict):
        refreshed_base_sess = fresh_session

    return TurnResponse(
        success=True,
        session=refreshed_base_sess,
        outcome=outcome,
        action=action,
        actions=actions,
        items_gained_by_user=items_gained,
        xp_gained=xp_gained,
        levels_gained=levels_gained,
        xp_by_user=xp_by_user,
        levels_by_user=levels_by_user,
        new_char=new_char,
        scene_persisted=True,
        scene_title=scene_title,
        next_narrative=next_narrative,
        cleaned_choices=cleaned_choices,
    )


async def retry_narration(session_id: int, user_id: int, stream_callback=None) -> TurnResponse:
    """Runs the lightweight narration pass for a retry, updating only prose and choices while freezing cast & spatial state (D13)."""
    session = await adb(db.get_session, session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    try:
        await adb(game_engine.heal_session_quests_on_load, session_id)
    except Exception as _heal_err:
        log.debug("heal_session_quests_on_load failed (non-fatal): %s", _heal_err)

    snapshot = await adb(db.get_turn_snapshot, session_id)
    if not snapshot or snapshot.get("status") != "completed":
        raise ValueError("No completed snapshot available to retry")

    attempt = snapshot.get("retry_attempts", 0) + 1

    from game_engine.turn.narration import run_narration_pass

    # Narration pass (cast_events on retry output are strictly ignored per D13)
    new_outcome = await run_narration_pass(session, snapshot, attempt=attempt, stream_callback=stream_callback)
    if isinstance(new_outcome, dict):
        new_outcome.pop("cast_events", None)

    # 1. Update the DB history directly like resolve_action does
    raw_hist = list(session.get("history") or [])
    if raw_hist and isinstance(raw_hist[-1], dict) and raw_hist[-1].get("type") == "action":
        last_entry = dict(raw_hist[-1])
        new_outcome_narr = (new_outcome.get("outcome_narrative") or "").strip()
        new_next_narr = (new_outcome.get("next_narrative") or "").strip()

        # Check if previous outcome_narrative was an emergency fallback
        prev_outcome = str(last_entry.get("outcome_narrative") or "")
        is_prev_fallback = (
            bool(last_entry.get("is_fallback") or last_entry.get("_is_fallback_narrative"))
            or any(ph in prev_outcome.lower() for ph in (
                "deliberate intent",
                "carefully observe",
                "temporary fallback",
                "threads of fate shimmer",
                "fallback generation",
            ))
        )

        if new_outcome_narr:
            last_entry["outcome_narrative"] = new_outcome_narr
            last_entry["narrative"] = new_outcome_narr
            last_entry.pop("is_fallback", None)
            last_entry.pop("_is_fallback_narrative", None)
            if not new_next_narr and is_prev_fallback:
                split_out, split_nxt = game_engine.split_outcome_and_next_paragraphs(
                    new_outcome_narr, new_next_narr
                )
                if split_nxt:
                    last_entry["outcome_narrative"] = split_out
                    last_entry["narrative"] = split_out
                    last_entry["next_narrative"] = split_nxt
                    new_next_narr = split_nxt
                else:
                    last_entry["next_narrative"] = ""
        elif is_prev_fallback and new_next_narr:
            last_entry["outcome_narrative"] = ""
            last_entry["narrative"] = new_next_narr
            last_entry.pop("is_fallback", None)
            last_entry.pop("_is_fallback_narrative", None)
        elif not new_outcome_narr and not new_next_narr and isinstance(new_outcome, dict):
            new_outcome["_is_fallback_narrative"] = True

        if new_next_narr:
            last_entry["next_narrative"] = new_next_narr
        if new_outcome.get("scene_title"):
            last_entry["scene_title"] = new_outcome["scene_title"]
        raw_hist[-1] = last_entry

    async def _commit_retry_result():
        def _commit_retry_tx():
            with db.UnitOfWork() as uow_conn:
                if raw_hist and isinstance(raw_hist[-1], dict) and raw_hist[-1].get("type") == "action":
                    db.update_session(session_id, history_json=json.dumps(raw_hist, default=str))
                    try:
                        with db.savepoint(uow_conn, "sp_retry_resync_digest"):
                            db.resync_latest_digest_turn(session_id, raw_hist)
                    except Exception as _resync_err:
                        log.warning("resync_latest_digest_turn during retry_narration failed (non-fatal): %s", _resync_err)

                snapshot["retry_attempts"] = attempt
                snapshot["fallback_reason"] = None
                db.set_turn_snapshot(session_id, snapshot)

                s_row = db.get_session(session_id)
                ch_row = db.get_character(user_id, session_id=session_id)
                if isinstance(s_row, dict):
                    from mechanics.world.world_events.engine import build_client_world_pulse_payload as _build_wp_retry
                    s_row["world_pulse"] = _build_wp_retry(session_id)
                return s_row, ch_row

        fresh_s, n_char = await adb(_commit_retry_tx)

        applied_state = dict(snapshot.get("applied", {}))
        merged = dict(applied_state)
        for k in ("outcome_narrative", "next_narrative", "scene_title", "next_choices", "choices", "_is_fallback_narrative"):
            if k in new_outcome:
                merged[k] = new_outcome[k]
        for frozen_k in ("location", "current_node_id", "focal_point", "npcs_present", "dialogue_partner", "dialogue_partners"):
            if frozen_k in applied_state:
                merged[frozen_k] = applied_state[frozen_k]

        raw_retry_choices = merged.get("next_choices") or merged.get("choices") or []
        if raw_retry_choices and hasattr(game_engine, "build_hybrid_turn_choices"):
            try:
                retry_party = [(dict(n_char), [])] if isinstance(n_char, dict) and n_char else None
                rebuilt_choices = await adb(
                    game_engine.build_hybrid_turn_choices,
                    raw_retry_choices,
                    session=fresh_s,
                    party=retry_party,
                    result=merged,
                )
                if rebuilt_choices:
                    merged["next_choices"] = rebuilt_choices
                    merged["choices"] = rebuilt_choices
                    merged["_hybrid_choices_built"] = True
            except Exception as e:
                log.warning("build_hybrid_turn_choices during retry_narration failed (non-fatal): %s", e)

        retry_hist = list((fresh_s or {}).get("history") or raw_hist)
        s_title, nxt_narr, cl_choices = await _get_turn_service()._finalize_and_save_scene(
            session_id=session_id,
            session_obj=fresh_s,
            outcome=merged,
            lead_char=dict(n_char) if n_char else None,
            history=retry_hist,
            mode=snapshot.get("mode"),
            is_retry=True,
        )
        return fresh_s, n_char, merged, s_title, nxt_narr, cl_choices

    fresh_session, new_char, merged_outcome, scene_title, next_narrative, cleaned_choices = await _get_turn_service()._await_uninterruptible(
        _commit_retry_result(), reraise_cancel=False
    )
    saved_retry_session = await adb(db.get_session, session_id)
    if isinstance(saved_retry_session, dict):
        saved_retry_session["world_pulse"] = fresh_session.get("world_pulse") if isinstance(fresh_session, dict) else None
    else:
        saved_retry_session = fresh_session

    action = snapshot.get("actions", [{}])[0]
    return TurnResponse(
        success=True,
        session=saved_retry_session,
        outcome=merged_outcome,
        action=action,
        items_gained_by_user={},
        xp_gained=0,
        levels_gained=[],
        new_char=new_char,
        scene_persisted=True,
        scene_title=scene_title,
        next_narrative=next_narrative,
        cleaned_choices=cleaned_choices,
    )
