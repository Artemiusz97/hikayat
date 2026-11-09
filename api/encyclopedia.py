from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Query, Request

import db
from db import adb
from mechanics.world.folklore_codex import build_encyclopedia_payload
from .security import verify_session_participant, verify_user_access

router = APIRouter()


@router.get("/api/codex/encyclopedia")
async def get_codex_encyclopedia(
    session_id: Optional[int] = Query(default=None),
    user_id: Optional[int] = Query(default=None),
    lang: Optional[str] = Query(default=None),
    request: Request = None,
) -> dict[str, Any]:
    """Returns the account-wide Canonical Folklore Codex [X/50] and session Field Log & Containment Vault."""
    eff_uid = int(user_id) if isinstance(user_id, int) and int(user_id) > 0 else None
    eff_sid = int(session_id) if isinstance(session_id, int) and int(session_id) > 0 else None

    if eff_uid is not None:
        eff_uid = await verify_user_access(request, eff_uid)

    if eff_sid is not None:
        sess = await adb(db.get_session, eff_sid)
        if not sess or eff_uid is None:
            eff_sid = None
        else:
            _, eff_uid = await verify_session_participant(request, eff_sid, eff_uid, session=sess)

    payload = await adb(build_encyclopedia_payload, session_id=eff_sid, user_id=eff_uid, lang=lang)
    return payload
