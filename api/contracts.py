from __future__ import annotations

"""
FastAPI router for Entity Contracts & Devil Pacts (`anomalous_incursions`,
`anomalous_high_school`, and all `gore` / `furry` / `nsfw` variants).
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

import db
from db import adb
from mechanics.pacts import build_contracts_overview_payload, execute_pact_ritual_action
from mechanics.system.concurrency import distributed_adventure_lock
from .adventure import _enrich_session_for_client
from .deps import _serializable_action, manager
from .security import verify_session_participant

router = APIRouter()


class ContractRitualRequest(BaseModel):
    user_id: Optional[int] = None
    patron_id: str
    tier: int = 1
    use_credits: bool = True
    lang: Optional[str] = None


def _require_active_session(session: Optional[Dict[str, Any]]) -> None:
    if not session or str(session.get("status") or "active").strip().lower() != "active":
        raise HTTPException(status_code=400, detail="This adventure session is no longer active.")


def _resolve_request_lang(explicit_lang: Optional[str], settings: Optional[Dict[str, Any]]) -> str:
    cand = str(explicit_lang or (settings or {}).get("language") or "en").strip().lower()[:2]
    return cand if cand in ("en", "pl", "ms", "zh", "de") else "en"


@router.get("/api/contracts/{session_id}")
async def get_entity_contracts_overview(
    session_id: int,
    user_id: Optional[int] = Query(None),
    lang: Optional[str] = Query(None),
    request: Request = None,
) -> Dict[str, Any]:
    """Fetches active covenants, discovery channel offers with Taste Appraisal, and Patron Compendium."""
    uid = user_id if isinstance(user_id, int) and not isinstance(user_id, bool) else None
    pre_session, canonical_uid = await verify_session_participant(request, session_id, uid)
    eff_uid = int(canonical_uid or uid or (pre_session or {}).get("host_user_id") or 0)
    settings = await adb(db.get_settings, eff_uid) if eff_uid else {}
    eff_lang = _resolve_request_lang(lang, settings)
    payload = await adb(build_contracts_overview_payload, session_id, eff_uid, lang=eff_lang)
    return _serializable_action(payload)


@router.post("/api/contracts/{session_id}/{ritual_action}")
async def perform_entity_contract_ritual(
    session_id: int,
    ritual_action: str,
    req: ContractRitualRequest,
    request: Request = None,
) -> Dict[str, Any]:
    """
    Executes `sign`, `upgrade`, `feed`, or `sever` deterministically under
    `distributed_adventure_lock(eff_uid, session_id)` and broadcasts scene updates
    whenever an Exorcism Manifestation Boss or Boss Surrender alters combat state.
    """
    act_norm = str(ritual_action or "").strip().lower()
    if act_norm not in ("sign", "upgrade", "feed", "sever"):
        raise HTTPException(status_code=400, detail=f"Unsupported contract action: '{ritual_action}'.")

    pre_session, canonical_uid = await verify_session_participant(request, session_id, req.user_id)
    _require_active_session(pre_session)
    eff_uid = int(canonical_uid or req.user_id or (pre_session or {}).get("host_user_id") or 0)

    async with distributed_adventure_lock(eff_uid, session_id):
        session, _ = await verify_session_participant(request, session_id, eff_uid or req.user_id)
        _require_active_session(session)
        if not eff_uid:
            eff_uid = int(session.get("host_user_id") or 0)
        settings = await adb(db.get_settings, eff_uid) if eff_uid else {}
        eff_lang = _resolve_request_lang(req.lang, settings)

        try:
            res = await adb(
                execute_pact_ritual_action,
                session_id,
                eff_uid,
                act_norm,
                req.patron_id,
                tier=max(1, min(3, int(req.tier or 1))),
                use_credits=bool(req.use_credits),
                lang=eff_lang,
            )
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err))

        enriched_session: Optional[Dict[str, Any]] = None
        if res.get("spawned_exorcism_boss") or act_norm in ("sign", "sever"):
            fresh_sess = await adb(db.get_session, session_id)
            if fresh_sess:
                enriched_session = await adb(_enrich_session_for_client, dict(fresh_sess), eff_uid, eff_lang)

    safe_res = _serializable_action({
        "success": True,
        **res,
        **({"updated_session": enriched_session} if enriched_session else {}),
    })
    await manager.broadcast(
        session_id,
        {
            "type": "CONTRACTS_STATE_SYNC",
            "user_id": eff_uid,
            "overview": safe_res.get("overview") or {},
        },
    )
    if enriched_session and (res.get("spawned_exorcism_boss") or res.get("boss_surrender")):
        await manager.broadcast(
            session_id,
            {
                "type": "UPDATE_SCENE",
                "session": safe_res.get("updated_session"),
            },
        )
    return safe_res
