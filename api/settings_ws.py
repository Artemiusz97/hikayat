from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

import config
import db
from db import adb
import llm_client
from mechanics.combat.enemies import generate_scenario_enemy
from .deps import (
    logger,
    manager,
    SettingsUpdateRequest,
    DebugUpdateRequest,
)

if not hasattr(db, "apply_stat_mode"):
    def _apply_stat_mode(user_id: int, mode: str):
        db.update_settings(user_id, debug_stat_mode=mode)
        return db.get_character(user_id)
    db.apply_stat_mode = _apply_stat_mode

router = APIRouter()


@router.get("/api/settings/debug/telemetry")
async def get_telemetry():
    """Returns rolling LLM token/latency telemetry and active circuit-breaker cooldowns."""
    raw = llm_client.get_llm_telemetry()
    data = dict(raw) if isinstance(raw, dict) else {}
    primary_model = data.get("primary_model") or getattr(config, "LLM_MODEL", "")
    fallback_models = data.get("fallback_models") or list(getattr(config, "LLM_FALLBACK_MODELS", []))
    data.setdefault("primary_model", primary_model)
    data.setdefault("fallback_models", fallback_models)
    return {
        "telemetry": data,
        "primary_model": primary_model,
        "fallback_models": fallback_models,
    }


@router.get("/api/settings/{user_id}")
async def get_settings(user_id: int):
    """Gets user preferences."""
    s = await adb(db.get_user_settings, user_id)
    return {"settings": s}


@router.post("/api/settings/{user_id}")
async def save_settings(user_id: int, req: SettingsUpdateRequest):
    """Saves user preferences."""
    await adb(
        db.save_user_settings,
        user_id=user_id,
        verbosity=req.verbosity,
        dialogue_mode=req.dialogue_mode,
        image_gen_enabled=req.image_gen_enabled,
        choices_style=req.choices_style,
        result_display=req.result_display,
        stream_narrative=req.stream_narrative,
        show_percentages=req.show_percentages,
        combat_ui_style=req.combat_ui_style,
        image_model=req.image_model,
    )
    settings = await adb(db.get_user_settings, user_id)
    return {"success": True, "settings": settings}


@router.get("/api/debug/{user_id}")
async def get_debug_settings(user_id: int):
    s = await adb(db.get_settings, user_id)
    return {
        "user_id": user_id,
        "debug_stat_mode": s.get("debug_stat_mode", "off"),
        "debug_check_mode": s.get("debug_check_mode", "off"),
        "debug_reveal_all_info": s.get("debug_reveal_all_info", 0),
        "telemetry": llm_client.get_llm_telemetry(),
    }


@router.post("/api/debug/{user_id}")
async def save_debug_settings(user_id: int, req: DebugUpdateRequest):
    updates = {}
    if req.debug_stat_mode is not None:
        await adb(db.apply_stat_mode, user_id, req.debug_stat_mode)
        updates["debug_stat_mode"] = req.debug_stat_mode
    if req.debug_check_mode is not None:
        updates["debug_check_mode"] = req.debug_check_mode
    if req.debug_reveal_all_info is not None:
        updates["debug_reveal_all_info"] = req.debug_reveal_all_info
    if updates:
        await adb(db.update_settings, user_id, **updates)

    extra_payload = {}
    if req.action == "hp_to_1":
        await adb(db.set_hp_to_one, user_id)
    elif req.action == "full_heal":
        await adb(db.heal_full, user_id)
    elif req.action == "force_enemy":
        sid = req.session_id or await adb(db.get_active_session_id_for_user, user_id)
        if sid:
            session = await adb(db.get_session, sid)
            if session:
                scen = session.get("scenario", "fantasy")
                loc = session.get("current_location") or "Unknown"
                chap = await adb(db.get_session_chapter, sid) or 1
                enemy = await adb(generate_scenario_enemy, scen, loc, chap)
                enemy["hp"] = 100
                enemy["max_hp"] = 100
                enemies = list(session.get("nearby_enemies") or [])
                enemies.append(enemy)
                await adb(db.update_session_enemies, sid, enemies)
                updated_session = await adb(db.get_session, sid)
                extra_payload["enemy_spawned"] = enemy
                extra_payload["nearby_enemies"] = enemies
                extra_payload["session"] = updated_session
    elif req.action == "reset_all":
        await adb(db.apply_stat_mode, user_id, "off")
        await adb(
            db.update_settings,
            user_id,
            debug_stat_mode="off",
            debug_check_mode="off",
            debug_reveal_all_info=0,
        )

    s = await adb(db.get_settings, user_id)
    char = await adb(db.get_character, user_id)
    return {
        "success": True,
        "user_id": user_id,
        "debug_stat_mode": s.get("debug_stat_mode", "off"),
        "debug_check_mode": s.get("debug_check_mode", "off"),
        "debug_reveal_all_info": s.get("debug_reveal_all_info", 0),
        "hp": char.get("hp") if char else None,
        "max_hp": char.get("max_hp") if char else None,
        **extra_payload,
    }


@router.websocket("/ws/session/{session_id}")
async def websocket_session(websocket: WebSocket, session_id: int, user_id: int = Query(...)):
    await manager.connect(session_id, user_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "PING":
                await websocket.send_json({"type": "PONG"})
            elif msg_type == "CHAT":
                await manager.broadcast(session_id, {
                    "type": "CHAT_MESSAGE",
                    "user_id": user_id,
                    "sender": data.get("sender", f"User {user_id}"),
                    "message": data.get("message", "")
                })
    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)
        await manager.broadcast_presence(session_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(session_id, websocket)
