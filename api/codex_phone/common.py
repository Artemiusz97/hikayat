from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel

from db import adb
import mechanics.social.relationships
from ..security import (
    extract_actor_token,
    extract_verified_token_uid,
    is_strict_auth_context,
    verify_user_access,
)


class CancelCommitmentRequest(BaseModel):
    user_id: int | None = None
    reason: str = "player_cancelled"


async def _verify_missing_session_codex_auth(request: Request | None, user_id: int | str | None) -> None:
    if request is None and not is_strict_auth_context(None):
        return
    tok = extract_actor_token(request)
    if tok is not None or is_strict_auth_context(request):
        valid_uid = int(user_id) if isinstance(user_id, int) or (isinstance(user_id, str) and user_id.isdigit()) else None
        if valid_uid is not None:
            await verify_user_access(request, valid_uid)
        elif not tok or extract_verified_token_uid(tok) is None:
            raise HTTPException(status_code=401, detail="user_id and actor token are required.")


async def _get_contacts_ro(session_id: int, character_id: int | None = None) -> list[dict[str, Any]]:
    """Read-only safe_get_contacts wrapper compatible with 1/2-arg test monkeypatches."""
    return await adb(
        mechanics.social.relationships.safe_get_contacts,
        session_id,
        character_id,
        resolve_relations=False,
        ensure_scene=False,
    ) or []


def _infer_school_grade_badge(role: str, current_grade: str, scen_key: str) -> str:
    """Infers academic standing or faculty/staff badge for school characters."""
    if current_grade and str(current_grade).strip():
        return str(current_grade).strip()
    from mechanics.social.roster_tags import is_school_scenario, normalize_standing

    if not is_school_scenario(scen_key):
        return ""
    return normalize_standing(role=role, grade=current_grade, scen_key=scen_key)


def _fmt_hhmm(minute_val: int | None) -> str:
    if minute_val is None:
        return "00:00"
    m = int(minute_val) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def _enrich_commitments_for_ui(
    session_id: int,
    raw_commitments: list[dict] | None,
    contacts: list[dict] | None = None,
) -> list[dict]:
    """Enriches commitment rows with friendly display names, subtype badges, and formatted time windows."""
    _ = session_id
    if not raw_commitments:
        return []
    contact_by_key: dict[str, dict] = {}
    for c in (contacts or []):
        if not isinstance(c, dict):
            continue
        c_nm = str(c.get("name") or "").strip()
        c_id = str(c.get("npc_id") or "").strip()
        if c_id:
            contact_by_key[c_id.lower()] = c
            contact_by_key[c_id.lower().replace("-", "_")] = c
        if c_nm:
            contact_by_key[c_nm.lower()] = c
            contact_by_key[c_nm.lower().replace(" ", "_").replace("-", "_")] = c

    out: list[dict] = []
    for item in raw_commitments:
        if not isinstance(item, dict):
            continue
        d = dict(item)
        d.setdefault("commitment_id", d.get("id"))
        meta = d.get("metadata")
        if not isinstance(meta, dict):
            try:
                meta = json.loads(d.get("metadata_json") or "{}")
            except (json.JSONDecodeError, TypeError, ValueError):
                meta = {}
        d["metadata"] = meta

        parts = d.get("participants")
        if not isinstance(parts, list):
            try:
                parts = json.loads(d.get("participants_json") or "[]")
            except (json.JSONDecodeError, TypeError, ValueError):
                parts = []
        d["participants"] = parts

        src = str(d.get("source_entity") or "").strip()
        tgt = str(d.get("target_entity") or "").strip()
        counterparty_key = tgt if src.lower() in ("player", "") else src
        matched_c = contact_by_key.get(counterparty_key.lower()) or contact_by_key.get(
            counterparty_key.lower().replace("-", "_")
        )

        display_name = ""
        npc_id_val = ""
        if matched_c:
            display_name = str(matched_c.get("name") or "").strip()
            npc_id_val = str(matched_c.get("npc_id") or matched_c.get("name") or "").strip()
        if not display_name:
            for p in parts:
                if isinstance(p, dict):
                    pk = str(p.get("person_key") or p.get("npc_id") or "").strip()
                    if pk.lower() not in ("player", ""):
                        display_name = str(p.get("name") or pk).strip()
                        npc_id_val = npc_id_val or str(p.get("npc_id") or pk).strip()
                        break
        if not display_name:
            raw_lbl = str(d.get("npc_name") or counterparty_key or "Counterparty").strip()
            display_name = (
                raw_lbl.replace("_", " ").title() if "_" in raw_lbl and raw_lbl == raw_lbl.lower() else raw_lbl
            )
        if not npc_id_val:
            npc_id_val = str(d.get("npc_id") or counterparty_key or display_name).strip()

        d["target_display_name"] = display_name
        d.setdefault("npc_name", display_name)
        d.setdefault("npc_id", npc_id_val)

        c_type = str(d.get("commitment_type") or "promise").lower()
        subtype = str(meta.get("subtype") or meta.get("purpose") or c_type).strip().lower()
        d["subtype"] = subtype

        s_day = d.get("scheduled_day")
        e_day = d.get("end_day") if d.get("end_day") is not None else s_day
        s_min = d.get("start_minute")
        e_min = d.get("end_minute")
        if c_type == "rendezvous" and s_day is not None:
            if e_day is not None and int(e_day) > int(s_day):
                d["time_window_label"] = f"Day {s_day} {_fmt_hhmm(s_min)} – Day {e_day} {_fmt_hhmm(e_min)}"
            else:
                d["time_window_label"] = f"Day {s_day} • {_fmt_hhmm(s_min)}–{_fmt_hhmm(e_min)}"
        elif meta.get("has_deadline") and s_day is not None:
            d["time_window_label"] = f"Due Day {s_day} • {_fmt_hhmm(e_min)}"
        elif d.get("deadline_turn") is not None:
            d["time_window_label"] = f"Due by Turn #{d['deadline_turn']}"
        else:
            d["time_window_label"] = f"Day {s_day}" if s_day is not None else "Open Obligation"

        out.append(d)
    return out
