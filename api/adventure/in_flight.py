from __future__ import annotations

import asyncio
import sys
import time
import db
from typing import Any, Awaitable, Callable
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from db import adb
from ..deps import (
    logger,
    manager,
)

_BACKGROUND_TASKS: set[asyncio.Task] = set()
_IN_FLIGHT_TURN_TASKS: dict[int, dict[str, Any]] = {}
_LAST_TURN_ERRORS: dict[int, dict[str, Any]] = {}


def _get_enrich_session_fn():
    """Resolve enrich_session_for_client dynamically without circular imports or losing monkeypatches."""
    adv_mod = sys.modules.get("api.adventure")
    if adv_mod is not None and hasattr(adv_mod, "enrich_session_for_client"):
        return adv_mod.enrich_session_for_client
    from .enrichment import enrich_session_for_client
    return enrich_session_for_client


def _record_last_turn_error(session_id: int | None, error: str, turn_id: str | None = None) -> None:
    if not session_id:
        return
    _LAST_TURN_ERRORS[int(session_id)] = {
        "turn_id": turn_id,
        "error": str(error or "Turn failed"),
        "timestamp": time.time(),
    }


def _get_active_in_flight_turn(session_id: int) -> dict[str, Any] | None:
    entry = _IN_FLIGHT_TURN_TASKS.get(int(session_id or 0))
    if not entry:
        return None
    task = entry.get("task")
    if isinstance(task, asyncio.Task) and task.done():
        return None
    return entry


async def _cancel_session_in_flight_task(session_id: int | None) -> bool:
    """Cancels an active background turn task for `session_id`, awaiting rollback cleanup."""
    if not session_id:
        return False
    sid = int(session_id)
    _LAST_TURN_ERRORS.pop(sid, None)
    entry = _get_active_in_flight_turn(sid)
    if not entry:
        return False
    entry["cancelled_by_endpoint"] = True
    task = entry.get("task")
    still_running = False
    if isinstance(task, asyncio.Task) and not task.done():
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=15.0)
        except asyncio.TimeoutError:
            still_running = not task.done()
        except (asyncio.CancelledError, Exception):
            still_running = not task.done()
    if not still_running and _IN_FLIGHT_TURN_TASKS.get(sid) is entry:
        _IN_FLIGHT_TURN_TASKS.pop(sid, None)
    return not still_running


def _cancel_unstarted_in_flight_entry_locked(session_id: int | None) -> None:
    """Marks and removes any newly queued `_IN_FLIGHT_TURN_TASKS` entry while holding `distributed_adventure_lock`."""
    if not session_id:
        return
    sid = int(session_id)
    _LAST_TURN_ERRORS.pop(sid, None)
    entry = _IN_FLIGHT_TURN_TASKS.get(sid)
    if not entry:
        return
    entry["cancelled_by_endpoint"] = True
    task = entry.get("task")
    if isinstance(task, asyncio.Task) and not task.done():
        task.cancel()
    if _IN_FLIGHT_TURN_TASKS.get(sid) is entry:
        _IN_FLIGHT_TURN_TASKS.pop(sid, None)



async def _load_error_session_snapshot(session_id: int, user_id: int | None) -> dict | None:
    """Safely reload and enrich the rolled-back session state for STREAM_ERROR clients."""
    try:
        err_sess_row = await adb(db.get_session, session_id)
        if not err_sess_row:
            return None
        eff_uid = user_id or err_sess_row.get("host_user_id")
        err_sess = await adb(_get_enrich_session_fn(), err_sess_row, eff_uid)
        if isinstance(err_sess, dict):
            err_sess["in_flight_turn"] = None
        return err_sess
    except Exception:
        return None


def _spawn_background_task(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task


async def _make_ws_stream_controls(
    session_id: int,
    user_id: int,
    safe_action: dict,
    mode: str,
    *,
    in_flight_entry: dict[str, Any] | None = None,
    eager_start: bool = True,
):
    """Builds the WebSocket streaming token callback (`__thinking__`, `__reset__`, chunks) and buffer flusher."""
    started_streaming = False
    chunk_buffer: list[str] = []
    active_chunk_field = "outcome_narrative"
    last_flush = asyncio.get_running_loop().time()

    async def flush_buffer():
        if chunk_buffer:
            text = "".join(chunk_buffer)
            chunk_buffer.clear()
            await manager.broadcast(session_id, {
                "type": "STREAM_CHUNK",
                "text": text,
                "field": active_chunk_field,
            })

    if eager_start and mode != "sync":
        started_streaming = True
        await manager.broadcast(session_id, {
            "type": "STREAM_START",
            "user_id": user_id,
            "action": safe_action,
        })

    async def on_token(token: str, field: str = "outcome_narrative"):
        nonlocal last_flush, started_streaming, active_chunk_field
        if field == "__thinking__":
            if in_flight_entry is not None:
                in_flight_entry["status"] = "thinking"
            await manager.broadcast(session_id, {
                "type": "STREAM_THINKING",
                "session_id": session_id,
                "user_id": user_id,
                "action": safe_action,
            })
            return
        if field == "__reset__":
            chunk_buffer.clear()
            active_chunk_field = "outcome_narrative"
            if started_streaming:
                await manager.broadcast(session_id, {"type": "STREAM_RESET"})
            return
        if in_flight_entry is not None:
            in_flight_entry["status"] = "streaming"
        if not started_streaming:
            started_streaming = True
            await manager.broadcast(session_id, {
                "type": "STREAM_START",
                "user_id": user_id,
                "action": safe_action,
            })

        if field != active_chunk_field:
            await flush_buffer()
            active_chunk_field = field
            last_flush = asyncio.get_running_loop().time()

        chunk_buffer.append(token)
        now = asyncio.get_running_loop().time()
        if now - last_flush >= 0.025 or "\n" in token:
            await flush_buffer()
            last_flush = now

    on_token._accepts_field = True
    return on_token, flush_buffer, lambda: started_streaming


def check_in_flight_guard(
    session_id: int,
    in_flight_entry: dict[str, Any] | None,
    *,
    pre_locked: bool = False,
) -> bool:
    """Return False if a reserved async task was cancelled/superseded, or raise 409 on active collision."""
    if pre_locked:
        return True
    if in_flight_entry is not None:
        if (
            in_flight_entry.get("cancelled_by_endpoint")
            or _IN_FLIGHT_TURN_TASKS.get(session_id) is not in_flight_entry
        ):
            return False
    elif _get_active_in_flight_turn(session_id) is not None:
        raise HTTPException(status_code=409, detail="A turn is already in progress for this session.")
    return True


async def fail_or_broadcast_error(
    session_id: int,
    status_code: int,
    detail: str,
    *,
    broadcast_error: bool = False,
) -> None:
    """Broadcast STREAM_ERROR in async WS mode or raise HTTPException in sync HTTP mode."""
    if broadcast_error:
        await manager.broadcast(session_id, {
            "type": "STREAM_ERROR",
            "session_id": session_id,
            "error": detail,
            "status_code": status_code,
        })
        return
    raise HTTPException(status_code=status_code, detail=detail)


def launch_in_flight_ws_task(
    session_id: int,
    user_id: int | None,
    entry: dict[str, Any],
    coro_factory: Callable[[], Awaitable[Any]],
    *,
    http_error_fallback: str,
    unhandled_error_prefix: str,
    log_label: str,
) -> JSONResponse:
    """Shared async WS background dispatcher for action and retry endpoints."""
    turn_id = entry["turn_id"]
    release_reservation = True
    try:
        if entry.get("cancelled_by_endpoint"):
            return JSONResponse(
                status_code=200,
                content={"status": "cancelled", "session_id": session_id, "turn_id": turn_id},
            )

        async def _run_bg_task():
            try:
                await coro_factory()
            except asyncio.CancelledError:
                if not entry.get("cancelled_by_endpoint"):
                    try:
                        fresh = await adb(db.get_session, session_id)
                        if fresh:
                            fresh = await adb(_get_enrich_session_fn(), fresh, user_id)
                            if isinstance(fresh, dict):
                                fresh["in_flight_turn"] = None
                        await manager.broadcast(session_id, {
                            "type": "TURN_CANCELLED",
                            "session_id": session_id,
                            "session": fresh,
                            "sync_timestamp": time.time(),
                        })
                    except Exception:
                        pass
                raise
            except HTTPException as http_err:
                err_detail = str(http_err.detail or http_error_fallback)
                _record_last_turn_error(session_id, err_detail, turn_id=turn_id)
                err_sess = await _load_error_session_snapshot(session_id, user_id)
                await manager.broadcast(session_id, {
                    "type": "STREAM_ERROR",
                    "session_id": session_id,
                    "error": err_detail,
                    "status_code": http_err.status_code,
                    "session": err_sess,
                })
            except Exception as bg_err:
                logger.error(
                    "Unhandled async %s error for session %s: %s",
                    log_label,
                    session_id,
                    bg_err,
                    exc_info=True,
                )
                err_detail = f"{unhandled_error_prefix}: {bg_err}"
                _record_last_turn_error(session_id, err_detail, turn_id=turn_id)
                err_sess = await _load_error_session_snapshot(session_id, user_id)
                await manager.broadcast(session_id, {
                    "type": "STREAM_ERROR",
                    "session_id": session_id,
                    "error": err_detail,
                    "status_code": 500,
                    "session": err_sess,
                })
            finally:
                if _IN_FLIGHT_TURN_TASKS.get(session_id) is entry:
                    _IN_FLIGHT_TURN_TASKS.pop(session_id, None)

        bg_task = _spawn_background_task(_run_bg_task())
        entry["task"] = bg_task
        release_reservation = False
        return JSONResponse(
            status_code=202,
            content={"status": "accepted", "session_id": session_id, "turn_id": turn_id},
        )
    finally:
        if release_reservation and _IN_FLIGHT_TURN_TASKS.get(session_id) is entry:
            _IN_FLIGHT_TURN_TASKS.pop(session_id, None)
