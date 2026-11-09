from __future__ import annotations

"""
FastAPI router for Smartphone Realty (property deeds, Primary Home selection,
and Spare Key management) in Anomalous Incursions & Anomalous High School.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

import db
from db import adb
from mechanics.system.concurrency import distributed_adventure_lock, distributed_session_lock
from mechanics.world.locations.residences import build_realty_payload
from .deps import _serializable_action, manager
from .security import verify_session_participant

router = APIRouter()


class RealtyPurchaseRequest(BaseModel):
    user_id: int | None = None
    property_id: str
    set_primary: bool | None = None


class RealtyPrimaryRequest(BaseModel):
    user_id: int | None = None
    property_id: str


class RealtySpareKeyRequest(BaseModel):
    user_id: int | None = None
    property_id: str
    npc_id: str
    revoke: bool = False


_REASON_ERROR_MAP: dict[str, tuple[int, str]] = {
    "insufficient_gold": (400, "Not enough Gold to purchase this property deed."),
    "already_owned": (400, "You already own the deed to this property."),
    "starter_quarters_disallowed": (
        400,
        "Spare keys can only be granted for permanently purchased property deeds, not temporary starter quarters.",
    ),
    "insufficient_affinity": (
        400,
        "Only romantic partners or deeply trusted contacts (Affinity 70+) can receive a spare key.",
    ),
    "contact_not_found": (404, "Contact not found in this session."),
    "contact_deceased": (400, "Cannot grant a spare key to this contact."),
    "not_owned": (400, "You do not own this property."),
    "unknown_property": (404, "Unknown property listing."),
    "unsupported_scenario": (400, "Property deeds are not available in this scenario."),
    "not_supported_scenario": (400, "Property deeds are not available in this scenario."),
    "character_not_found": (404, "Active character not found."),
    "session_not_found": (404, "Session not found."),
    "invalid_request": (400, "Invalid realty request."),
}


def _require_active_session(session: dict[str, Any] | None) -> None:
    if not session or str(session.get("status") or "active").strip().lower() != "active":
        raise HTTPException(status_code=400, detail="This adventure session is no longer active.")


def _raise_for_realty_failure(res: dict[str, Any]) -> None:
    reason = str(res.get("reason") or "invalid_request")
    code, msg = _REASON_ERROR_MAP.get(reason, (400, f"Realty action failed ({reason})."))
    if reason == "insufficient_gold" and res.get("price") is not None and res.get("gold") is not None:
        msg = f"Not enough Gold ({res['gold']}g / {res['price']}g required)."
    raise HTTPException(status_code=code, detail=msg)


@router.get("/api/realty/{session_id}")
async def get_realty_state(
    session_id: int,
    user_id: int | None = Query(None),
    request: Request = None,
) -> dict[str, Any]:
    """Fetches Starter Quarters, Owned Deeds, 9-Tier Market Listings, and Spare Key state."""
    uid = user_id if isinstance(user_id, int) and not isinstance(user_id, bool) else None
    _, canonical_uid = await verify_session_participant(request, session_id, uid)
    return await adb(build_realty_payload, session_id, canonical_uid or uid)


@router.post("/api/realty/{session_id}/purchase")
async def purchase_realty_property(
    session_id: int,
    req: RealtyPurchaseRequest,
    request: Request = None,
) -> dict[str, Any]:
    """Atomically purchases a property deed, unlocks all interior rooms, and updates inventory slots."""
    pre_session, canonical_uid = await verify_session_participant(request, session_id, req.user_id)
    _require_active_session(pre_session)
    eff_uid = int(canonical_uid or req.user_id or (pre_session or {}).get("host_user_id") or 0)

    async with distributed_adventure_lock(eff_uid, session_id):
        session, _ = await verify_session_participant(request, session_id, eff_uid or req.user_id)
        _require_active_session(session)
        if not eff_uid:
            eff_uid = int(session.get("host_user_id") or 0)
        res = await adb(
            db.atomic_purchase_property,
            session_id,
            eff_uid,
            req.property_id,
            req.set_primary,
        )
        if not res.get("ok"):
            _raise_for_realty_failure(res)
        payload = await adb(build_realty_payload, session_id, eff_uid)

    prop_name = (res.get("catalog_entry") or {}).get("name") or req.property_id
    out = _serializable_action({
        "success": True,
        "message": f"Purchased deed to {prop_name}!",
        **payload,
    })
    await manager.broadcast(session_id, {"type": "REALTY_STATE_SYNC", "realty": payload})
    return out


@router.post("/api/realty/{session_id}/primary")
async def set_realty_primary_home(
    session_id: int,
    req: RealtyPrimaryRequest,
    request: Request = None,
) -> dict[str, Any]:
    """Designates an owned deed or active starter quarters as the player's Primary Home."""
    pre_session, canonical_uid = await verify_session_participant(request, session_id, req.user_id)
    _require_active_session(pre_session)
    eff_uid = int(canonical_uid or req.user_id or 0)

    async with distributed_session_lock(session_id):
        session, _ = await verify_session_participant(request, session_id, eff_uid or req.user_id)
        _require_active_session(session)
        res = await adb(db.set_primary_property, session_id, req.property_id)
        if not res.get("ok"):
            _raise_for_realty_failure(res)
        payload = await adb(build_realty_payload, session_id, eff_uid or None)

    out = _serializable_action({
        "success": True,
        "message": "Primary Home updated.",
        **payload,
    })
    await manager.broadcast(session_id, {"type": "REALTY_STATE_SYNC", "realty": payload})
    return out


@router.post("/api/realty/{session_id}/spare-key")
async def manage_realty_spare_key(
    session_id: int,
    req: RealtySpareKeyRequest,
    request: Request = None,
) -> dict[str, Any]:
    """Grants or revokes a Spare Key on a permanently purchased deed (`is_starter == 0`)."""
    pre_session, canonical_uid = await verify_session_participant(request, session_id, req.user_id)
    _require_active_session(pre_session)
    eff_uid = int(canonical_uid or req.user_id or 0)

    async with distributed_session_lock(session_id):
        session, _ = await verify_session_participant(request, session_id, eff_uid or req.user_id)
        _require_active_session(session)
        if req.revoke:
            res = await adb(db.revoke_property_spare_key, session_id, req.property_id, req.npc_id)
        else:
            res = await adb(db.grant_property_spare_key, session_id, req.property_id, req.npc_id)
        if not res.get("ok"):
            _raise_for_realty_failure(res)
        payload = await adb(build_realty_payload, session_id, eff_uid or None)

    msg = (
        "Spare key revoked."
        if req.revoke
        else f"Gave a spare key to {res.get('npc_name') or req.npc_id}!"
    )
    out = _serializable_action({
        "success": True,
        "message": msg,
        **payload,
    })
    await manager.broadcast(session_id, {"type": "REALTY_STATE_SYNC", "realty": payload})
    return out
