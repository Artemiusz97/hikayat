from __future__ import annotations

import time
import db
import game_engine
from fastapi import (
    APIRouter,
    HTTPException,
    Request,
)
from db import adb
from scenario_data import get_scenario_display_name
from services.examine_service import invalidate_examine_cache
from services.turn_service import TurnService
from mechanics.system.concurrency import distributed_adventure_lock
from ..security import (
    verify_session_participant,
    verify_user_access,
)
from ..deps import (
    EndAdventureRequest,
    JoinAdventureRequest,
    LoadSlotRequest,
    ResumeSessionRequest,
    SaveSlotRequest,
    StartAdventureRequest,
    manager,
)
from .in_flight import (
    _LAST_TURN_ERRORS,
    _cancel_session_in_flight_task,
    _cancel_unstarted_in_flight_entry_locked,
    _spawn_background_task,
)
from .enrichment import (
    _trigger_scene_image_broadcast,
    enrich_session_for_client,
)

router = APIRouter()


@router.get("/api/adventure/session-image/{session_id}")
async def get_session_image(session_id: int):
    """Lightweight polling endpoint returning the latest scene_image_url for active turn reconciliation."""
    sess = await adb(db.get_session, session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    raw_hist = list(sess.get("history") or [])
    last_img = raw_hist[-1].get("scene_image_url") if (raw_hist and isinstance(raw_hist[-1], dict)) else None
    return {
        "session_id": session_id,
        "scene_image_url": sess.get("scene_image_url") or last_img,
        "history_image_url": last_img,
        "scene_title": sess.get("scene_title", ""),
    }



@router.get("/api/adventure/lobbies")
async def list_open_lobbies():
    """Lists open multiplayer adventure sessions available to join."""
    raw_lobbies = await adb(db.list_open_lobbies_with_members, 20)
    lobbies = []
    for row in raw_lobbies:
        disp = get_scenario_display_name(row["scenario"])
        lobbies.append({
            **row,
            "scenario_display_name": disp,
            "scene_title": row.get("scene_title") or disp,
        })
    return {"lobbies": lobbies}


@router.get("/api/adventure/character-sessions/{character_id}")
async def get_character_sessions_endpoint(character_id: int, request: Request = None):
    """Returns all active sessions for a character across their 6 slots."""
    char = await adb(db.get_character_by_id, character_id)
    if not char:
        return {"sessions": []}
    await verify_user_access(request, char["user_id"])
    user_id = char["user_id"]

    def _load_and_enrich_char_sessions() -> list[dict]:
        with db.ReadUnitOfWork():
            sessions = db.get_character_sessions(character_id)
            return [enrich_session_for_client(s, user_id, read_only=True) for s in sessions]

    enriched = await adb(_load_and_enrich_char_sessions)
    return {"sessions": enriched}


@router.post("/api/adventure/resume")
async def resume_session_endpoint(req: ResumeSessionRequest, request: Request = None):
    """Switches the active adventure to the selected session/slot and returns enriched session state."""
    session_row, eff_uid = await verify_session_participant(request, req.session_id, req.user_id)
    canonical_id = await adb(db.resolve_canonical_user_id, eff_uid)

    char = None
    if req.character_id is not None:
        char = await adb(db.get_character_by_id, int(req.character_id))
        if not char:
            raise HTTPException(status_code=404, detail="Character not found.")
        if int(char.get("user_id") or 0) != int(canonical_id):
            raise HTTPException(status_code=403, detail="Forbidden: character belongs to another user.")
    if not char:
        char = await adb(db.get_character, canonical_id, session_id=req.session_id)

    if char:
        await adb(db.set_character_active_session, char["id"], req.session_id)

    await adb(db.sync_user_settings_to_session, canonical_id, req.session_id)
    fresh_session = await adb(db.get_session, req.session_id)
    if fresh_session:
        session_row = fresh_session

    try:
        await adb(game_engine.heal_session_quests_on_load, req.session_id)
    except Exception:
        pass

    enriched = await adb(enrich_session_for_client, dict(session_row), canonical_id)
    return {"success": True, "session": enriched}


@router.get("/api/adventure/active-session/{user_id}")
async def get_active_session(user_id: int, request: Request = None):
    """Gets the active adventure session for a user."""
    await verify_user_access(request, user_id)
    session_id = await adb(db.get_active_session_id_for_user, user_id)
    if not session_id:
        return {"has_active_session": False, "session": None}

    session = await adb(db.get_session, session_id)
    if not session:
        return {"has_active_session": False, "session": None}

    session = await adb(enrich_session_for_client, session, user_id, read_only=True)

    return {
        "has_active_session": True,
        "session": session
    }


@router.post("/api/adventure/start")
async def start_adventure(req: StartAdventureRequest, request: Request = None):
    """Starts a new adventure session (Solo or Multiplayer) and generates the opening scene."""
    await verify_user_access(request, req.user_id)
    canonical_id = await adb(db.resolve_canonical_user_id, req.user_id)
    pre_char = None
    if req.character_id is not None:
        pre_char = await adb(db.get_character_by_id, int(req.character_id))
        if not pre_char:
            raise HTTPException(status_code=404, detail="Character not found. Create a character first!")
        if int(pre_char.get("user_id") or 0) != int(canonical_id):
            raise HTTPException(status_code=403, detail="Forbidden: character belongs to another user.")
    if not pre_char:
        pre_char = await adb(db.get_character, canonical_id)
    pre_target_slot = req.slot if req.slot and 1 <= req.slot <= 6 else 1
    pre_slot_sess = (
        await adb(db.get_character_session_in_slot, pre_char["id"], pre_target_slot)
        if pre_char
        else None
    )
    lock_sids = [
        int(s)
        for s in (
            (pre_char or {}).get("active_session_id"),
            (pre_slot_sess or {}).get("id"),
        )
        if s
    ]
    if (pre_slot_sess or {}).get("id"):
        await _cancel_session_in_flight_task(int(pre_slot_sess["id"]))
        _LAST_TURN_ERRORS.pop(int(pre_slot_sess["id"]), None)
    async with distributed_adventure_lock(canonical_id, lock_sids):
        for _l_sid in lock_sids:
            _cancel_unstarted_in_flight_entry_locked(_l_sid)
        from api.auth_characters import rebuild_verified_client_starter_loadout
        try:
            start_result = await TurnService.start_adventure(
                req.user_id,
                character_id=req.character_id,
                scenario=req.scenario,
                tags=req.tags,
                mode=req.mode,
                capacity=req.capacity,
                slot=req.slot,
                char_class=req.char_class,
                class_description=req.class_description,
                weapon_name=req.weapon_name,
                weapon_description=req.weapon_description,
                starter_loadout=req.starter_loadout,
                starter_loadout_builder=rebuild_verified_client_starter_loadout,
                starting_faction=req.starting_faction,
                origin_mode=getattr(req, "origin_mode", None),
                student_grade=getattr(req, "student_grade", None),
                attribute=req.attribute,
                combat_archetype=req.combat_archetype,
                ability_medium=req.ability_medium,
                stats_override={
                    "str": req.str_val,
                    "per": req.per,
                    "end": req.end,
                    "cha": req.cha,
                    "int": req.int_val,
                    "agi": req.agi,
                    "luk": req.luk,
                },
                appearance=req.appearance,
                breast_size=req.breast_size,
                penis_size=req.penis_size,
                asset_texture=req.asset_texture,
                schedule_chapter_plan=True,
            )
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e))

        session_id = start_result["session_id"]
        scenario_key = start_result["scenario_key"]
        scene = start_result["scene"]
        updated_session = start_result["session"]
        updated_session = await adb(enrich_session_for_client, updated_session, req.user_id)

        await manager.broadcast(session_id, {
            "type": "NEW_SCENE",
            "session": updated_session,
            "sync_timestamp": time.time()
        })

        if updated_session.get("image_gen_enabled"):
            _spawn_background_task(
                _trigger_scene_image_broadcast(
                    session_id,
                    updated_session.get("scene_title", ""),
                    updated_session.get("narrative", ""),
                    updated_session.get("current_location", ""),
                    scenario_key,
                    image_prompt=None,
                    outcome=scene,
                )
            )

        return {"success": True, "session": updated_session}


@router.post("/api/adventure/join")
async def join_adventure(req: JoinAdventureRequest, request: Request = None):
    """Joins an existing multiplayer adventure session by invite/session code."""
    eff_uid = await verify_user_access(request, req.user_id)
    canonical_id = await adb(db.resolve_canonical_user_id, eff_uid)
    try:
        session_id = int(str(req.join_code).strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid join code. Must be numeric session ID.")

    async with distributed_adventure_lock(canonical_id, session_id):
        session_row = await adb(db.get_session, session_id)
        if not session_row or session_row.get("status") not in ("waiting", "active"):
            raise HTTPException(status_code=404, detail="Active adventure session not found with that invite code.")

        mode = str(session_row.get("mode") or "solo").strip().lower()
        capacity = int(session_row.get("capacity") or 1)
        if mode == "solo" or capacity <= 1:
            raise HTTPException(status_code=403, detail="Cannot join a private solo adventure session.")

        char = await adb(db.get_character, canonical_id)
        if not char:
            raise HTTPException(status_code=404, detail="Character not found. Create a character first.")

        session_fresh, join_err = await adb(db.join_multiplayer_session, session_id, canonical_id, char["id"])
        if join_err == "not_found":
            raise HTTPException(status_code=404, detail="Active adventure session not found with that invite code.")
        if join_err == "full":
            raise HTTPException(status_code=400, detail="This adventure session is already full.")
        session = await adb(enrich_session_for_client, dict(session_fresh), canonical_id)

    return {"success": True, "session": session}


@router.post("/api/adventure/end")
async def end_adventure(req: EndAdventureRequest, request: Request = None):
    """Ends/finishes an active adventure session."""
    _, verified_uid = await verify_session_participant(request, req.session_id, req.user_id)
    await _cancel_session_in_flight_task(req.session_id)
    async with distributed_adventure_lock(verified_uid, req.session_id):
        _cancel_unstarted_in_flight_entry_locked(req.session_id)
        await adb(db.finish_session, req.session_id)
    return {"success": True, "session_id": req.session_id}


@router.get("/api/saves/{user_id}")
async def list_saves(user_id: int, request: Request = None):
    """Lists all adventure save slots for the user's active character."""
    await verify_user_access(request, user_id)
    saves = await adb(db.list_adventure_saves, user_id)
    enriched_saves = []
    for s in saves:
        sd = dict(s)
        if sd.get("scenario"):
            sd["scenario_display_name"] = get_scenario_display_name(sd["scenario"])
        enriched_saves.append(sd)
    return {"saves": enriched_saves}


@router.post("/api/saves/save")
async def save_slot(req: SaveSlotRequest, request: Request = None):
    """Creates or overwrites a named adventure checkpoint save slot."""
    await verify_user_access(request, req.user_id)
    active_sid = await adb(db.get_active_session_id_for_user, req.user_id)
    async with distributed_adventure_lock(req.user_id, active_sid):
        try:
            res = await adb(db.save_adventure_slot, req.user_id, req.slot_name, overwrite=req.overwrite)
            return res
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/saves/load")
async def load_slot(req: LoadSlotRequest, request: Request = None):
    """Restores a named adventure save slot into a fresh active session."""
    await verify_user_access(request, req.user_id)
    active_sid = await adb(db.get_active_session_id_for_user, req.user_id)
    if active_sid:
        await _cancel_session_in_flight_task(active_sid)
    async with distributed_adventure_lock(req.user_id, active_sid):
        _cancel_unstarted_in_flight_entry_locked(active_sid)
        try:
            res = await adb(db.load_adventure_slot, req.user_id, req.slot_name)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))

    session_id = res.get("id") or res.get("session_id")
    try:
        if active_sid:
            invalidate_examine_cache(active_sid)
        if session_id and session_id != active_sid:
            invalidate_examine_cache(session_id)
    except Exception:
        pass
    updated_session = await adb(db.get_session, session_id) if session_id else res
    if updated_session:
        updated_session = await adb(enrich_session_for_client, updated_session, req.user_id)
        await manager.broadcast(session_id, {
            "type": "NEW_SCENE",
            "session": updated_session,
            "sync_timestamp": time.time()
        })

    return {
        "success": True,
        "loaded": res,
        "session": updated_session
    }


@router.delete("/api/saves/{user_id}/{slot_name}")
async def delete_save(user_id: int, slot_name: str, request: Request = None):
    """Deletes a named adventure save slot."""
    await verify_user_access(request, user_id)
    deleted = await adb(db.delete_adventure_save, user_id, slot_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Save slot not found")
    return {"success": True}
