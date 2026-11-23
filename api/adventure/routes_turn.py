from __future__ import annotations

import asyncio
import time
import db
import game_engine
import scenario_data
from typing import Any
from contextlib import nullcontext
from fastapi import (
    APIRouter,
    HTTPException,
    Request,
)
from db import adb
from services.examine_service import invalidate_examine_cache
from services.turn_service import TurnService
from mechanics.system.concurrency import distributed_session_lock
from ..security import verify_session_participant
from ..deps import (
    ActionRequest,
    CancelTurnRequest,
    RerollImageRequest,
    RetryAdventureRequest,
    ToggleNonLethalRequest,
    ToggleStealthRequest,
    _serializable_action,
    logger,
    manager,
)
from .in_flight import (
    _IN_FLIGHT_TURN_TASKS,
    _LAST_TURN_ERRORS,
    _cancel_session_in_flight_task,
    _get_active_in_flight_turn,
    _load_error_session_snapshot,
    _make_ws_stream_controls,
    _record_last_turn_error,
    _spawn_background_task,
    check_in_flight_guard,
    fail_or_broadcast_error,
    launch_in_flight_ws_task,
)
from .enrichment import (
    _trigger_scene_image_broadcast,
    enrich_session_for_client,
)

router = APIRouter()


async def _execute_action_locked(
    req: ActionRequest,
    request: Request | None,
    *,
    in_flight_entry: dict[str, Any] | None = None,
    broadcast_error: bool = False,
    pre_locked: bool = False,
) -> dict | None:
    lock_ctx = nullcontext() if pre_locked else distributed_session_lock(req.session_id)
    _turn_id = (in_flight_entry or {}).get("turn_id")
    async with lock_ctx:
        if not check_in_flight_guard(req.session_id, in_flight_entry, pre_locked=pre_locked):
            return None
        session_row = await adb(db.get_session, req.session_id)
        if not session_row:
            await fail_or_broadcast_error(
                req.session_id, 404, "Session not found", broadcast_error=broadcast_error, turn_id=_turn_id
            )
            return None
        session, verified_uid = await verify_session_participant(
            request, req.session_id, req.user_id, require_turn=True, session=session_row
        )
        eff_uid = verified_uid or req.user_id
        if session["status"] != "active":
            await fail_or_broadcast_error(
                req.session_id, 400, "Session is not active", broadcast_error=broadcast_error, turn_id=_turn_id
            )
            return None

        char = await adb(db.get_character, eff_uid)
        if not char:
            await fail_or_broadcast_error(
                req.session_id, 404, "Character not found", broadcast_error=broadcast_error, turn_id=_turn_id
            )
            return None

        raw_db_choices = session.get("choices", []) or []
        if not raw_db_choices or any(not isinstance(c, dict) for c in raw_db_choices):
            choices = await adb(
                game_engine.sanitize_and_diversify_choices,
                raw_db_choices,
                scenario=session.get("scenario", "fantasy"),
                location=session.get("current_location", ""),
                char=dict(char) if char else None,
                dialogue_partner=session.get("dialogue_partner"),
                current_npcs=session.get("current_npcs", []),
                session_id=session.get("id"),
            )
        else:
            choices = [dict(c) for c in raw_db_choices if isinstance(c, dict)]

        from mechanics.social.conversation_choices import (
            ensure_active_dialogue_exit_choice,
            has_dialogue_exit_choice,
        )
        if not has_dialogue_exit_choice(choices):
            choices = await adb(ensure_active_dialogue_exit_choice, choices, session=session)

        is_stealth_req = bool(
            getattr(req, "is_stealth", False)
            or (isinstance(req.action, dict) and req.action.get("is_stealth"))
            or (getattr(req, "stance", "") == "stealth")
            or (isinstance(req.action, dict) and req.action.get("stance") == "stealth")
        )
        stance_req = getattr(req, "stance", None) or (req.action.get("stance") if isinstance(req.action, dict) else None)
        if is_stealth_req and not stance_req:
            stance_req = "stealth"

        raw_pick = {
            "choice_index": req.choice_index,
            "custom_action_text": req.custom_action_text,
            "direct_choice": req.direct_choice,
            "combat_target": req.combat_target,
            "intent": getattr(req, "intent", None) or (req.action.get("intent") if isinstance(req.action, dict) else None),
            "target_npc": getattr(req, "target_npc", None) or (req.action.get("target_npc") if isinstance(req.action, dict) else None),
            "skip_minutes": getattr(req, "skip_minutes", None) if getattr(req, "skip_minutes", None) is not None else (req.action.get("skip_minutes") if isinstance(req.action, dict) else None),
            "sleep_mode": getattr(req, "sleep_mode", None) or (req.action.get("sleep_mode") if isinstance(req.action, dict) else None),
            "is_stealth": is_stealth_req,
            "stance": stance_req,
            "item_id": getattr(req, "item_id", None) if getattr(req, "item_id", None) is not None else (req.action.get("item_id") if isinstance(req.action, dict) else None),
            "target_type": getattr(req, "target_type", None) or (req.action.get("target_type") if isinstance(req.action, dict) else None),
            "target_name": getattr(req, "target_name", None) or (req.action.get("target_name") if isinstance(req.action, dict) else None),
            "target_user_id": getattr(req, "target_user_id", None) if getattr(req, "target_user_id", None) is not None else (req.action.get("target_user_id") if isinstance(req.action, dict) else None),
            "use_mode": getattr(req, "use_mode", None) or (req.action.get("use_mode") if isinstance(req.action, dict) else None),
            "action": req.action if isinstance(req.action, dict) else None,
            "_untrusted_client_pick": True,
        }
        try:
            action = await TurnService.prepare_and_roll_action(
                session_id=req.session_id,
                user_id=eff_uid,
                raw_pick=raw_pick,
                session=session,
                char=dict(char),
                choices=choices,
                enforce_explicit_mp=True,
            )
        except (PermissionError, ValueError) as e:
            if broadcast_error:
                await manager.broadcast(req.session_id, {
                    "type": "STREAM_ERROR",
                    "session_id": req.session_id,
                    "error": str(e),
                    "status_code": 400,
                    **({"turn_id": _turn_id} if _turn_id else {}),
                })
                return None
            raise HTTPException(status_code=400, detail=str(e))

        if session.get("non_lethal_mode"):
            action["is_non_lethal"] = True

        mode = session["mode"]
        is_started_fn = lambda: False
        flush_buffer = None
        safe_action = _serializable_action(action)
        if in_flight_entry is not None:
            in_flight_entry["action"] = safe_action

        try:
            user_settings = await adb(db.get_user_settings, eff_uid)
            stream_enabled = user_settings.get("stream_narrative", 1) == 1
            stream_callback = None

            if stream_enabled:
                stream_callback, flush_buffer, is_started_fn = await _make_ws_stream_controls(
                    req.session_id,
                    eff_uid,
                    safe_action,
                    mode,
                    in_flight_entry=in_flight_entry,
                    eager_start=(mode != "sync"),
                )

            heartbeat_stop = asyncio.Event()

            async def _stream_heartbeat():
                while not heartbeat_stop.is_set():
                    try:
                        await asyncio.wait_for(heartbeat_stop.wait(), timeout=4.0)
                    except asyncio.TimeoutError:
                        await manager.broadcast(req.session_id, {
                            "type": "HEARTBEAT",
                            "status": "processing"
                        })

            hb_task = asyncio.create_task(_stream_heartbeat())

            try:
                turn_response = await TurnService.resolve_action(req.session_id, eff_uid, action, mode=mode, stream_callback=stream_callback)
            finally:
                heartbeat_stop.set()
                try:
                    await hb_task
                except Exception:
                    pass

            if is_started_fn() and flush_buffer is not None:
                await flush_buffer()

            if getattr(turn_response, "scene_persisted", None) is not True:
                from services.turn_service import TurnService as _CanonicalTurnService
                await _CanonicalTurnService._finalize_and_save_scene(
                    session_id=req.session_id,
                    session_obj=turn_response.session,
                    outcome=turn_response.outcome,
                    lead_char=dict(char) if char else None,
                    history=list((turn_response.session or {}).get("history", [])),
                    mode=mode,
                    is_retry=False,
                )
        except ValueError as e:
            if str(e) == "waiting_for_party":
                party = await adb(db.get_session_members, req.session_id)
                fresh_wait_sess = await adb(db.get_session, req.session_id) or session
                picks = fresh_wait_sess.get("pending_picks") or {}
                locked_cnt = len(picks)
                await manager.broadcast(req.session_id, {
                    "type": "PICK_LOCKED",
                    "user_id": eff_uid,
                    "character_name": char["name"],
                    "locked_picks": locked_cnt,
                    "total": len(party),
                    "waiting_count": max(0, len(party) - locked_cnt),
                })
                return {"status": "waiting_for_party", "locked_picks": locked_cnt, "total": len(party)}
            if broadcast_error or is_started_fn():
                _record_last_turn_error(req.session_id, str(e), turn_id=_turn_id)
                err_sess = await _load_error_session_snapshot(req.session_id, eff_uid)
                await manager.broadcast(req.session_id, {
                    "type": "STREAM_ERROR",
                    "session_id": req.session_id,
                    "error": str(e),
                    "status_code": 400,
                    "session": err_sess,
                    **({"turn_id": _turn_id} if _turn_id else {}),
                })
            if broadcast_error:
                return None
            raise
        except Exception as e:
            logger.error("Failed to resolve turn for session %s: %s", req.session_id, e, exc_info=True)
            snapshot = await adb(db.get_turn_snapshot, req.session_id)
            reason = snapshot.get("fallback_reason") if snapshot else None
            if reason == "models_unavailable":
                msg = "The generative models are currently overloaded or unavailable. Your action was saved. Please try again in a moment."
                status_code = 503
            else:
                msg = f"Engine failed to resolve the turn: {str(e)}"
                status_code = 500
            if broadcast_error or is_started_fn():
                _record_last_turn_error(req.session_id, msg, turn_id=_turn_id)
                err_sess = await _load_error_session_snapshot(req.session_id, eff_uid)
                await manager.broadcast(req.session_id, {
                    "type": "STREAM_ERROR",
                    "session_id": req.session_id,
                    "error": msg,
                    "status_code": status_code,
                    "fallback_reason": reason,
                    "session": err_sess,
                    **({"turn_id": _turn_id} if _turn_id else {}),
                })
            if broadcast_error:
                return None
            raise HTTPException(status_code=status_code, detail=msg)

        _LAST_TURN_ERRORS.pop(int(req.session_id), None)
        fresh_session = await adb(db.get_session, req.session_id)
        fresh_session = await adb(enrich_session_for_client, fresh_session, eff_uid)
        if isinstance(fresh_session, dict):
            fresh_session["in_flight_turn"] = None

        msg_type = "STREAM_END" if is_started_fn() else "NEW_SCENE"
        await manager.broadcast(req.session_id, {
            "type": msg_type,
            "session": fresh_session,
            "last_action": safe_action,
            "xp_gained": turn_response.xp_gained,
            "levels_gained": turn_response.levels_gained,
            "sync_timestamp": time.time(),
            **({"turn_id": _turn_id} if _turn_id else {}),
        })

        if fresh_session.get("image_gen_enabled"):
            _spawn_background_task(
                _trigger_scene_image_broadcast(
                    req.session_id,
                    fresh_session.get("scene_title", ""),
                    fresh_session.get("narrative", ""),
                    fresh_session.get("current_location", ""),
                    fresh_session.get("scenario", "fantasy"),
                    image_prompt=None,
                    outcome=turn_response.outcome if isinstance(turn_response.outcome, dict) else None,
                    action=action,
                )
            )

        return {
            "success": True,
            "session": fresh_session,
            "action": safe_action,
            "xp_gained": turn_response.xp_gained,
            "levels_gained": turn_response.levels_gained
        }


@router.post("/api/adventure/action")
async def execute_action(req: ActionRequest, request: Request = None):
    """Executes a player choice or custom action in an adventure session."""
    if not bool(getattr(req, "async_ws", False)):
        return await _execute_action_locked(req, request, broadcast_error=False)

    async with distributed_session_lock(req.session_id):
        if _get_active_in_flight_turn(req.session_id) is not None:
            raise HTTPException(status_code=409, detail="A turn is already in progress for this session.")

        session_row = await adb(db.get_session, req.session_id)
        if not session_row:
            raise HTTPException(status_code=404, detail="Session not found")
        session, verified_uid = await verify_session_participant(
            request, req.session_id, req.user_id, require_turn=True, session=session_row
        )
        eff_uid = verified_uid or req.user_id
        if session["status"] != "active":
            raise HTTPException(status_code=400, detail="Session is not active")
        char = await adb(db.get_character, eff_uid)
        if not char:
            raise HTTPException(status_code=404, detail="Character not found")

        raw_choices = session.get("choices") or []
        has_action_payload = (
            req.choice_index is not None
            or bool((req.custom_action_text or "").strip())
            or bool(req.direct_choice)
            or bool(isinstance(req.action, dict) and req.action)
        )
        if not has_action_payload:
            raise HTTPException(status_code=400, detail="No action specified")
        if req.choice_index is not None and raw_choices and not (0 <= int(req.choice_index) < len(raw_choices)):
            raise HTTPException(status_code=400, detail="Invalid choice index")

        if session.get("mode") == "sync":
            members = await adb(db.get_session_members, req.session_id) or []
            picks = session.get("pending_picks") or {}
            combined_keys = {str(k) for k in picks.keys()} | {str(eff_uid)}
            if len(members) > 1 and len(combined_keys) < len(members):
                return await _execute_action_locked(
                    req, request, broadcast_error=False, pre_locked=True
                )

        turn_id = f"turn_{req.session_id}_{int(time.time() * 1000)}"
        preview_label = (req.custom_action_text or "").strip()
        if not preview_label and req.choice_index is not None and raw_choices:
            chosen_preview = raw_choices[int(req.choice_index)]
            if isinstance(chosen_preview, dict):
                preview_label = str(chosen_preview.get("label") or chosen_preview.get("text") or "").strip()
            elif isinstance(chosen_preview, str):
                preview_label = chosen_preview.strip()
        if not preview_label and isinstance(req.action, dict):
            preview_label = str(req.action.get("label") or req.action.get("text") or req.action.get("custom_action_text") or "").strip()

        entry: dict[str, Any] = {
            "turn_id": turn_id,
            "user_id": eff_uid,
            "status": "resolving",
            "action": {"user_id": eff_uid, "label": preview_label or "Action"},
            "started_at": time.time(),
            "cancelled_by_endpoint": False,
            "task": None,
        }
        _IN_FLIGHT_TURN_TASKS[req.session_id] = entry
        _LAST_TURN_ERRORS.pop(int(req.session_id), None)

    async def _run_action_coro():
        await _execute_action_locked(
            req,
            request,
            in_flight_entry=entry,
            broadcast_error=True,
        )

    return launch_in_flight_ws_task(
        req.session_id,
        eff_uid,
        entry,
        _run_action_coro,
        http_error_fallback="Failed to execute action",
        unhandled_error_prefix="Engine failed to resolve the turn",
        log_label="turn",
    )


@router.get("/api/adventure/examine")
async def examine_adventure_scene(
    session_id: int,
    user_id: int,
    include_prose: bool = False,
    request: Request = None,
):
    """Zero-turn read-only scene inspection snapshot + optional cached async sensory prose."""
    await verify_session_participant(request, session_id, user_id)
    from services.examine_service import get_examine_payload
    try:
        return await get_examine_payload(session_id, user_id, include_prose=bool(include_prose))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/api/adventure/toggle_stealth")
async def toggle_adventure_stealth(req: ToggleStealthRequest, request: Request = None):
    """Toggles persistent stealth stance ON/OFF for an active adventure session."""
    await verify_session_participant(request, req.session_id, req.user_id)
    async with distributed_session_lock(req.session_id):
        session_row = await adb(db.get_session, req.session_id)
        if not session_row:
            raise HTTPException(status_code=404, detail="Session not found")

        session = dict(session_row)
        if session["status"] != "active":
            raise HTTPException(status_code=400, detail="Session is not active")

        from mechanics.stealth import (
            toggle_stealth_stance,
            is_actor_hidden,
            project_stealth_state_for_user,
            get_alert_badge_data,
            sync_stealth_choices_for_toggle,
        )
        currently_hidden = is_actor_hidden(session, req.user_id)
        new_active = req.active if req.active is not None else not currently_hidden
        toggle_stealth_stance(session, new_active, user_id=req.user_id)
        updated_choices = await adb(sync_stealth_choices_for_toggle, session, req.user_id, bool(new_active))
        await adb(db.update_session, req.session_id, stealth_state=session["stealth_state"], choices=updated_choices)
        try:
            invalidate_examine_cache(req.session_id)
        except Exception:
            pass
        fresh = await adb(db.get_session, req.session_id)
        fresh = await adb(enrich_session_for_client, dict(fresh), req.user_id)

        projected_st = project_stealth_state_for_user(session, req.user_id)
        badge_data = get_alert_badge_data(
            projected_st.get("detection_meter", 0),
            is_hidden=projected_st.get("is_hidden", False),
        )

        await manager.broadcast(req.session_id, {
            "type": "STEALTH_STATE_UPDATED",
            "user_id": req.user_id,
            "stealth_state": projected_st,
            "stealth_badge": badge_data,
            "choices": fresh.get("choices", []),
            "session": fresh,
        })

        return {
            "success": True,
            "stealth_state": projected_st,
            "stealth_badge": badge_data,
            "choices": fresh.get("choices", []),
            "session": fresh,
        }


@router.post("/api/adventure/toggle_non_lethal")
async def toggle_adventure_non_lethal(req: ToggleNonLethalRequest, request: Request = None):
    """Toggles persistent non-lethal combat mode ON/OFF for an active adventure session."""
    await verify_session_participant(request, req.session_id, req.user_id)
    async with distributed_session_lock(req.session_id):
        session_row = await adb(db.get_session, req.session_id)
        if not session_row:
            raise HTTPException(status_code=404, detail="Session not found")

        session = dict(session_row)
        if session["status"] != "active":
            raise HTTPException(status_code=400, detail="Session is not active")

        cur_val = bool(session.get("non_lethal_mode", False))
        new_val = req.active if req.active is not None else not cur_val
        await adb(db.update_session, req.session_id, extra={"non_lethal_mode": new_val})
        fresh = await adb(db.get_session, req.session_id)
        fresh = await adb(enrich_session_for_client, dict(fresh), req.user_id)

        await manager.broadcast(req.session_id, {
            "type": "SESSION_UPDATED",
            "session": fresh,
            "non_lethal_mode": new_val,
        })

        return {
            "success": True,
            "session_id": req.session_id,
            "non_lethal_mode": new_val,
            "session": fresh,
        }


async def _execute_retry_narration_locked(
    req: RetryAdventureRequest,
    uid: int | None,
    *,
    in_flight_entry: dict[str, Any] | None = None,
    broadcast_error: bool = False,
    pre_locked: bool = False,
    session_row: dict[str, Any] | None = None,
) -> dict | None:
    lock_ctx = nullcontext() if pre_locked else distributed_session_lock(req.session_id)
    _turn_id = (in_flight_entry or {}).get("turn_id")
    async with lock_ctx:
        if not check_in_flight_guard(req.session_id, in_flight_entry, pre_locked=pre_locked):
            return None
        if session_row is None:
            session_row = await adb(db.get_session, req.session_id)
        if not session_row:
            await fail_or_broadcast_error(
                req.session_id, 404, "Session not found", broadcast_error=broadcast_error, turn_id=_turn_id
            )
            return None

        session = dict(session_row)
        eff_uid = uid or session.get("host_user_id")
        _, party = await adb(db.preload_turn_party_bundle, req.session_id)
        if not party and eff_uid:
            c = await adb(db.get_character, eff_uid, session_id=req.session_id)
            if c:
                inv = await adb(db.get_inventory, eff_uid, char=c)
                party = [(dict(c), list(inv or []))]

        actor_char = party[0][0] if party else {"user_id": eff_uid or 0, "name": "Adventurer", "max_hp": 100, "per_": 5, "luk": 5}
        is_started_fn = lambda: False
        flush_buffer = None
        stream_callback = None
        if in_flight_entry is not None:
            retry_action = dict(in_flight_entry.get("action") or {"label": "Regenerating scene..."})
            user_settings = await adb(db.get_user_settings, eff_uid) if eff_uid else {}
            if (user_settings or {}).get("stream_narrative", 1) == 1:
                stream_callback, flush_buffer, is_started_fn = await _make_ws_stream_controls(
                    req.session_id,
                    int(eff_uid or 0),
                    retry_action,
                    str(session.get("mode") or "solo"),
                    in_flight_entry=in_flight_entry,
                    eager_start=False,
                )

        heartbeat_stop = asyncio.Event()

        async def _retry_heartbeat():
            while not heartbeat_stop.is_set():
                try:
                    await asyncio.wait_for(heartbeat_stop.wait(), timeout=4.0)
                except asyncio.TimeoutError:
                    await manager.broadcast(req.session_id, {
                        "type": "HEARTBEAT",
                        "status": "processing",
                    })

        hb_task = asyncio.create_task(_retry_heartbeat()) if in_flight_entry is not None else None
        try:
            if stream_callback is not None:
                turn_response = await TurnService.retry_narration(req.session_id, eff_uid, stream_callback=stream_callback)
            else:
                turn_response = await TurnService.retry_narration(req.session_id, eff_uid)
            if is_started_fn() and flush_buffer is not None:
                await flush_buffer()
            if getattr(turn_response, "scene_persisted", None) is not True:
                from services.turn_service import TurnService as _CanonicalTurnService
                await _CanonicalTurnService._finalize_and_save_scene(
                    session_id=req.session_id,
                    session_obj=session,
                    outcome=turn_response.outcome,
                    lead_char=dict(actor_char) if actor_char else None,
                    history=list((turn_response.session or {}).get("history", [])),
                    mode=session.get("mode"),
                    is_retry=True,
                )
        except Exception as e:
            logger.error(f"Error retrying adventure scene: {e}")
            snapshot = await adb(db.get_turn_snapshot, req.session_id)
            reason = snapshot.get("fallback_reason") if snapshot else None
            if reason == "models_unavailable":
                msg = "The generative models are currently overloaded or unavailable. Please try again in a moment."
                status_code = 503
            else:
                msg = f"Failed to retry scene: {str(e)}"
                status_code = 500
            if broadcast_error or is_started_fn():
                _record_last_turn_error(req.session_id, msg, turn_id=_turn_id)
                err_sess = await _load_error_session_snapshot(req.session_id, eff_uid)
                await manager.broadcast(req.session_id, {
                    "type": "STREAM_ERROR",
                    "session_id": req.session_id,
                    "error": msg,
                    "status_code": status_code,
                    "fallback_reason": reason,
                    "session": err_sess,
                    **({"turn_id": _turn_id} if _turn_id else {}),
                })
            if broadcast_error:
                return None
            raise HTTPException(status_code=status_code, detail=msg)
        finally:
            heartbeat_stop.set()
            if hb_task is not None:
                try:
                    await hb_task
                except Exception:
                    pass

        _LAST_TURN_ERRORS.pop(int(req.session_id), None)
        updated_session = await adb(db.get_session, req.session_id)
        enriched_session = await adb(enrich_session_for_client, updated_session, eff_uid)
        if isinstance(enriched_session, dict):
            enriched_session["in_flight_turn"] = None

        msg_type = "STREAM_END" if is_started_fn() else "NEW_SCENE"
        await manager.broadcast(req.session_id, {
            "type": msg_type,
            "session": enriched_session,
            "sync_timestamp": time.time(),
            **({"turn_id": _turn_id} if _turn_id else {}),
        })

        if enriched_session.get("image_gen_enabled"):
            _spawn_background_task(
                _trigger_scene_image_broadcast(
                    req.session_id,
                    enriched_session.get("scene_title", ""),
                    enriched_session.get("narrative", ""),
                    enriched_session.get("current_location", ""),
                    enriched_session.get("scenario", "fantasy"),
                    image_prompt=None,
                    outcome=turn_response.outcome
                    if isinstance(getattr(turn_response, "outcome", None), dict)
                    else None,
                )
            )

        return {"success": True, "session": enriched_session}


async def _execute_opening_retry_locked(
    req: RetryAdventureRequest,
    uid: int | None,
    *,
    session_row: dict[str, Any] | None = None,
    in_flight_entry: dict[str, Any] | None = None,
    broadcast_error: bool = False,
    pre_locked: bool = False,
) -> dict | None:
    lock_ctx = nullcontext() if pre_locked else distributed_session_lock(req.session_id)
    _turn_id = (in_flight_entry or {}).get("turn_id")
    async with lock_ctx:
        if not check_in_flight_guard(req.session_id, in_flight_entry, pre_locked=pre_locked):
            return None

        if session_row is None:
            session_row = await adb(db.get_session, req.session_id)
        if not session_row:
            await fail_or_broadcast_error(
                req.session_id, 404, "Session not found", broadcast_error=broadcast_error, turn_id=_turn_id
            )
            return None

        session = dict(session_row)
        eff_uid = uid or session.get("host_user_id")
        _, party = await adb(db.preload_turn_party_bundle, req.session_id)
        if not party and eff_uid:
            c = await adb(db.get_character, eff_uid, session_id=req.session_id)
            if c:
                inv = await adb(db.get_inventory, eff_uid, char=c)
                party = [(dict(c), list(inv or []))]

        actor_char = party[0][0] if party else {"user_id": eff_uid or 0, "name": "Adventurer", "max_hp": 100, "per_": 5, "luk": 5}

        # Turn 0: Opening scene retry
        # Capture Anomalous scenario starting faction & origin metadata BEFORE reset_session_for_opening_retry wipes child tables
        _retry_scen = str(session.get("scenario") or "fantasy")
        _prev_fac_state = session.get("anomalous_faction_state") if isinstance(session.get("anomalous_faction_state"), dict) else {}
        _prev_origin = str(session.get("origin_mode") or "")
        _prev_grade = str(session.get("student_grade") or "Sophomore")
        _prev_faction = str(
            session.get("anomalous_starting_faction")
            or _prev_fac_state.get("faction_archetype_key")
            or ("student_freelancer" if _prev_origin == "student" else "public_agency")
        )
        # Purge Turn 0 child rows + previously granted starting_prop so stale entities/props never bleed into fresh scene rolls
        pre_retry_snap = await adb(db.snapshot_opening_retry_state, req.session_id)
        await adb(db.reset_session_for_opening_retry, req.session_id, eff_uid or 0)
        if scenario_data.is_anomalous_incursions_scenario(_retry_scen):
            from mechanics.world.anomalous_events import bootstrap_anomalous_session
            await adb(
                bootstrap_anomalous_session,
                req.session_id,
                _retry_scen,
                eff_uid or 0,
                _prev_faction,
                actor_char.get("name", "") if isinstance(actor_char, dict) else "",
                _prev_origin,
                _prev_grade,
            )
        session = await adb(db.get_session, req.session_id) or session
        _, reloaded_party = await adb(db.preload_turn_party_bundle, req.session_id)
        if not reloaded_party and eff_uid:
            c = await adb(db.get_character, eff_uid, session_id=req.session_id)
            if c:
                inv = await adb(db.get_inventory, eff_uid, char=c)
                reloaded_party = [(dict(c), list(inv or []))]
        if reloaded_party:
            party = reloaded_party
        elif not party:
            party = []
        actor_char = party[0][0] if party else actor_char
        session["current_npcs"] = []
        session["dialogue_partner"] = None
        session["nearby_enemies"] = []
        try:
            async def _run_eager_retry_plan(sq_qid: str) -> Any:
                try:
                    from mechanics.narrative.chapter_plan import compile_or_apply_eager_quest_plan
                    return await compile_or_apply_eager_quest_plan(
                        req.session_id, sq_qid, timeout_seconds=25.0, defer_apply=True
                    )
                except Exception as _bg_retry_err:
                    logger.debug("Ch.1 retry eager ChapterPlan skipped: %s", _bg_retry_err)
                    return None

            sq_retry = await adb(game_engine.ensure_story_quest_exists, session)
            sq_retry_id = str((sq_retry or {}).get("quest_id") or "")
            if sq_retry_id:
                scene, eager_retry_plan = await asyncio.gather(
                    game_engine.generate_opening_scene(session, party),
                    _run_eager_retry_plan(sq_retry_id),
                )
                if eager_retry_plan:
                    try:
                        from mechanics.narrative.chapter_plan import apply_chapter_plan_to_dossier
                        await adb(apply_chapter_plan_to_dossier, req.session_id, sq_retry_id, eager_retry_plan)
                    except Exception as _apply_retry_err:
                        logger.debug("Ch.1 retry eager ChapterPlan apply skipped: %s", _apply_retry_err)
            else:
                scene = await game_engine.generate_opening_scene(session, party)
            await TurnService.commit_opening_scene(
                req.session_id,
                session,
                party,
                scene,
                char_row=actor_char if isinstance(actor_char, dict) else None,
                scenario_key=_retry_scen,
            )
        except Exception as e:
            logger.error(f"Error retrying opening scene: {e}", exc_info=True)
            if pre_retry_snap is not None:
                try:
                    await adb(db.restore_opening_retry_state, pre_retry_snap)
                except Exception as restore_err:
                    logger.warning("Failed restoring Turn-0 retry state for session %s: %s", req.session_id, restore_err)
            msg = f"Failed to retry opening scene: {str(e)}"
            if broadcast_error:
                _record_last_turn_error(req.session_id, msg, turn_id=_turn_id)
                err_sess = await _load_error_session_snapshot(req.session_id, eff_uid)
                await manager.broadcast(req.session_id, {
                    "type": "STREAM_ERROR",
                    "session_id": req.session_id,
                    "error": msg,
                    "status_code": 500,
                    "session": err_sess,
                    **({"turn_id": _turn_id} if _turn_id else {}),
                })
                return None
            raise HTTPException(status_code=500, detail=msg)

        _LAST_TURN_ERRORS.pop(int(req.session_id), None)
        updated_session = await adb(db.get_session, req.session_id)
        enriched_session = await adb(enrich_session_for_client, updated_session, eff_uid)
        if isinstance(enriched_session, dict):
            enriched_session["in_flight_turn"] = None

        await manager.broadcast(req.session_id, {
            "type": "NEW_SCENE",
            "session": enriched_session,
            "sync_timestamp": time.time(),
            **({"turn_id": _turn_id} if _turn_id else {}),
        })
        return {"success": True, "session": enriched_session}


async def _execute_retry_dispatch_locked(
    req: RetryAdventureRequest,
    uid: int | None,
    *,
    in_flight_entry: dict[str, Any] | None = None,
    broadcast_error: bool = False,
) -> dict | None:
    _turn_id = (in_flight_entry or {}).get("turn_id")
    async with distributed_session_lock(req.session_id):
        if not check_in_flight_guard(req.session_id, in_flight_entry):
            return None

        session_row = await adb(db.get_session, req.session_id)
        if not session_row:
            await fail_or_broadcast_error(
                req.session_id, 404, "Session not found", broadcast_error=broadcast_error, turn_id=_turn_id
            )
            return None

        history = list((session_row or {}).get("history") or [])
        if not history:
            return await _execute_opening_retry_locked(
                req,
                uid,
                session_row=session_row,
                in_flight_entry=in_flight_entry,
                broadcast_error=broadcast_error,
                pre_locked=True,
            )
        return await _execute_retry_narration_locked(
            req,
            uid,
            in_flight_entry=in_flight_entry,
            broadcast_error=broadcast_error,
            pre_locked=True,
            session_row=session_row,
        )


@router.post("/api/adventure/retry")
async def retry_adventure_scene(req: RetryAdventureRequest, request: Request = None):
    """Re-generates the current scene when fallback generation occurred or retry is requested."""
    if not bool(getattr(req, "async_ws", False)):
        _, verified_uid = await verify_session_participant(request, req.session_id, req.user_id)
        eff_uid = verified_uid or req.user_id
        return await _execute_retry_dispatch_locked(req, eff_uid, broadcast_error=False)

    async with distributed_session_lock(req.session_id):
        if _get_active_in_flight_turn(req.session_id) is not None:
            raise HTTPException(status_code=409, detail="A turn is already in progress for this session.")
        session_row = await adb(db.get_session, req.session_id)
        if not session_row:
            raise HTTPException(status_code=404, detail="Session not found")
        session_peek, verified_uid = await verify_session_participant(
            request, req.session_id, req.user_id, session=session_row
        )
        eff_uid = (verified_uid or req.user_id) or session_peek.get("host_user_id")
        turn_id = f"retry_{req.session_id}_{int(time.time() * 1000)}"
        entry: dict[str, Any] = {
            "turn_id": turn_id,
            "user_id": eff_uid,
            "status": "resolving",
            "action": {"user_id": eff_uid, "label": "Regenerating scene..."},
            "started_at": time.time(),
            "cancelled_by_endpoint": False,
            "task": None,
        }
        _IN_FLIGHT_TURN_TASKS[req.session_id] = entry
        _LAST_TURN_ERRORS.pop(int(req.session_id), None)

    async def _run_retry_coro():
        await _execute_retry_dispatch_locked(
            req,
            eff_uid,
            in_flight_entry=entry,
            broadcast_error=True,
        )

    return launch_in_flight_ws_task(
        req.session_id,
        eff_uid,
        entry,
        _run_retry_coro,
        http_error_fallback="Failed to retry scene",
        unhandled_error_prefix="Failed to retry scene",
        log_label="retry",
    )


@router.post("/api/adventure/cancel")
async def cancel_in_flight_turn(req: CancelTurnRequest, request: Request = None):
    """Cancels an in-flight asynchronous turn task, awaits rollback, and broadcasts TURN_CANCELLED."""
    _, verified_uid = await verify_session_participant(request, req.session_id, req.user_id)
    eff_uid = verified_uid or req.user_id or 0
    pre_sess = await adb(db.get_session, req.session_id)
    pre_turn_count = int((pre_sess or {}).get("turn_count") or 0)
    active_entry = _get_active_in_flight_turn(req.session_id)
    had_active = active_entry is not None
    cancelled_turn_id = active_entry.get("turn_id") if isinstance(active_entry, dict) else None
    stopped = await _cancel_session_in_flight_task(req.session_id)
    if had_active and not stopped:
        raise HTTPException(
            status_code=504,
            detail="Turn cancellation is still finalizing; please retry in a moment.",
        )

    async with distributed_session_lock(req.session_id):
        fresh_session = await adb(db.get_session, req.session_id)
        enriched_session = (
            await adb(enrich_session_for_client, fresh_session, eff_uid)
            if fresh_session
            else None
        )
        if isinstance(enriched_session, dict):
            enriched_session["in_flight_turn"] = None

        post_turn_count = int((fresh_session or {}).get("turn_count") or 0)
        already_committed = bool(had_active and fresh_session and post_turn_count > pre_turn_count)

    if already_committed:
        await manager.broadcast(req.session_id, {
            "type": "NEW_SCENE",
            "session": enriched_session,
            "sync_timestamp": time.time(),
            **({"turn_id": cancelled_turn_id} if cancelled_turn_id else {}),
        })
        return {
            "status": "completed",
            "session_id": req.session_id,
            "session": enriched_session,
            **({"turn_id": cancelled_turn_id} if cancelled_turn_id else {}),
        }

    await manager.broadcast(req.session_id, {
        "type": "TURN_CANCELLED",
        "session_id": req.session_id,
        "session": enriched_session,
        "sync_timestamp": time.time(),
        **({"turn_id": cancelled_turn_id} if cancelled_turn_id else {}),
    })
    return {
        "status": "cancelled",
        "session_id": req.session_id,
        "session": enriched_session,
        **({"turn_id": cancelled_turn_id} if cancelled_turn_id else {}),
    }


@router.post("/api/adventure/reroll_image")
async def reroll_adventure_image(req: RerollImageRequest, request: Request = None):
    """Regenerates only the scene image for the active turn without touching the story narrative."""
    session, _ = await verify_session_participant(request, req.session_id, req.user_id)
    if str(session.get("image_gen_enabled") or "0").lower() in ("0", "disabled", "false"):
        raise HTTPException(status_code=400, detail="Image generation is disabled in settings")

    # Extract last history outcome if available to rebuild accurate context
    raw_hist = list(session.get("history") or [])
    last_entry = raw_hist[-1] if (raw_hist and isinstance(raw_hist[-1], dict)) else {}

    local_url = await _trigger_scene_image_broadcast(
        req.session_id,
        scene_title=session.get("scene_title", ""),
        narrative=session.get("narrative", ""),
        location=session.get("current_location", ""),
        scenario=session.get("scenario", "fantasy"),
        outcome=last_entry,
        force=True,
    )
    return {"success": True, "image_url": local_url}
