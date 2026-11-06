from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

import db
from db import adb
from mechanics.system.concurrency import distributed_session_lock
from mechanics.world.world_events.engine import build_client_world_pulse_payload
from mechanics.world.world_events.social_hooks import record_break_the_news_gossip
from .deps import manager

router = APIRouter()


class TrackRumorRequest(BaseModel):
    user_id: int | None = None


class BreakNewsRequest(BaseModel):
    user_id: int | None = None
    npc_id: str


@router.get("/api/adventure/{session_id}/world-events")
async def get_session_world_events(
    session_id: int,
    user_id: int | None = Query(None),
) -> dict[str, Any]:
    """Returns safe omnichannel World Pulse state (active macro events + ONLY discovered rumors)."""
    session = await adb(db.get_session, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return await adb(build_client_world_pulse_payload, session_id)


@router.post("/api/adventure/{session_id}/rumors/{event_key}/track")
async def track_session_rumor(
    session_id: int,
    event_key: str,
    req: TrackRumorRequest,
) -> dict[str, Any]:
    """Atomically tracks a discovered rumor under the independent 2-slot rumor investigation cap."""
    async with distributed_session_lock(session_id):
        session = await adb(db.get_session, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found.")

        c_day, c_min, _ = await adb(db.get_session_time, session_id)
        turn_num = await adb(db.infer_session_turn, session)
        try:
            claimed = await adb(
                db.claim_rumor_investigation,
                session_id,
                event_key,
                int(c_day),
                int(c_min),
                int(turn_num),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        world_pulse = await adb(build_client_world_pulse_payload, session_id)
        quests = await adb(db.get_session_quests, session_id)

    await manager.broadcast(
        session_id,
        {
            "type": "WORLD_PULSE_SYNC",
            "session_id": int(session_id),
            "world_pulse": world_pulse,
            "sync_timestamp": time.time(),
        },
    )
    return {
        "success": True,
        "event_key": event_key,
        "quest_id": claimed["quest_id"],
        "quest": claimed["quest"],
        "quests": quests,
        "world_pulse": world_pulse,
    }


@router.post("/api/adventure/{session_id}/rumors/{event_key}/break-news")
async def break_rumor_news_to_npc(
    session_id: int,
    event_key: str,
    req: BreakNewsRequest,
) -> dict[str, Any]:
    """Records a 1/day per-NPC [Break the News] gossip share for an unaware NPC."""
    async with distributed_session_lock(session_id):
        session = await adb(db.get_session, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found.")

        rumors = await adb(
            db.get_world_events,
            session_id,
            "rumor",
            False,
            ("active",),
        )
        if not any(r.get("event_key") == event_key for r in rumors):
            raise HTTPException(status_code=404, detail="Active discovered rumor not found.")

        c_day, _, _ = await adb(db.get_session_time, session_id)
        result = await adb(
            record_break_the_news_gossip,
            session_id,
            int(c_day),
            req.npc_id,
            event_key,
        )
        if not result.get("allowed"):
            raise HTTPException(status_code=400, detail=str(result.get("reason") or "Already shared gossip today."))

        world_pulse = await adb(build_client_world_pulse_payload, session_id)

    await manager.broadcast(
        session_id,
        {
            "type": "WORLD_PULSE_SYNC",
            "session_id": int(session_id),
            "world_pulse": world_pulse,
            "sync_timestamp": time.time(),
        },
    )
    return {
        "success": True,
        "recorded": True,
        "event_key": event_key,
        "npc_id": result["npc_id"],
        "affinity_bonus": result.get("affinity_bonus", 2),
        "world_pulse": world_pulse,
    }
