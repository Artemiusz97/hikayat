from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import secrets
import sys
import time
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, Request, WebSocket

from bin import tunnel
import db
from db import adb

_PROCESS_AUTH_SECRET: str = secrets.token_hex(32)
_TRUSTED_LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})
_TAILSCALE_IPV4_NET = ipaddress.ip_network("100.64.0.0/10")
_TAILSCALE_IPV6_NET = ipaddress.ip_network("fd7a:115c:a1e0::/48")


def _get_auth_secret() -> bytes:
    raw = os.getenv("HIKAYAT_AUTH_SECRET") or _PROCESS_AUTH_SECRET
    return raw.encode("utf-8")


def issue_actor_token(user_id: int) -> str:
    uid = int(user_id)
    ts = int(time.time())
    payload = f"{uid}.{ts}"
    sig = hmac.new(_get_auth_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_actor_token(
    token: Optional[str],
    expected_user_id: int,
    max_age_seconds: int = 86400 * 30,
) -> bool:
    if not token or not isinstance(token, str):
        return False
    parts = token.strip().split(".")
    if len(parts) != 3:
        return False
    uid_str, ts_str, provided_sig = parts
    try:
        tok_uid = int(uid_str)
        tok_ts = int(ts_str)
    except ValueError:
        return False
    if tok_uid != int(expected_user_id):
        return False
    now = int(time.time())
    if tok_ts > now + 300 or (max_age_seconds > 0 and (now - tok_ts) > max_age_seconds):
        return False
    payload = f"{tok_uid}.{tok_ts}"
    expected_sig = hmac.new(_get_auth_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(provided_sig, expected_sig)


def extract_verified_token_uid(
    token: Optional[str],
    max_age_seconds: int = 86400 * 30,
) -> Optional[int]:
    if not token or not isinstance(token, str):
        return None
    parts = token.strip().split(".")
    if len(parts) != 3:
        return None
    try:
        tok_uid = int(parts[0])
    except ValueError:
        return None
    if verify_actor_token(token, tok_uid, max_age_seconds=max_age_seconds):
        return tok_uid
    return None


def is_share_mode_active() -> bool:
    if "--share" in sys.argv:
        return True
    return (
        os.getenv("HIKAYAT_SHARE", "").strip().lower() in ("true", "1", "yes")
        or os.getenv("SHARE", "").strip().lower() in ("true", "1", "yes")
    )


def is_strict_auth_context(request_or_ws: Request | WebSocket | None) -> bool:
    if is_share_mode_active():
        return True
    if os.getenv("HIKAYAT_ENFORCE_AUTH", "").strip().lower() in ("true", "1", "yes"):
        return True
    if request_or_ws is None:
        return False
    headers = getattr(request_or_ws, "headers", None) or {}
    if any(headers.get(h) for h in ("cf-connecting-ip", "x-forwarded-for", "x-real-ip")):
        return True
    client = getattr(request_or_ws, "client", None)
    host = str(getattr(client, "host", "") or "").strip().lower()
    if host and host not in _TRUSTED_LOCAL_HOSTS:
        return True
    return False


def _is_tailscale_mode_enabled() -> bool:
    if os.getenv("HIKAYAT_TRUST_TAILSCALE", "").strip().lower() in ("true", "1", "yes"):
        return True
    active_provider = (tunnel.get_active_provider() or "").strip().lower()
    if active_provider:
        return active_provider == "tailscale"
    configured = (
        os.getenv("HIKAYAT_SHARE_PROVIDER")
        or os.getenv("SHARE_PROVIDER")
        or ""
    ).strip().lower()
    return configured == "tailscale"


def _header_value(headers: Any, name: str) -> str:
    if not headers:
        return ""
    val = headers.get(name) if hasattr(headers, "get") else None
    if val is None and hasattr(headers, "get"):
        val = headers.get(name.lower())
    if val is None and isinstance(headers, dict):
        target = name.lower()
        for k, v in headers.items():
            if str(k).lower() == target:
                val = v
                break
    return str(val or "").strip()


def _is_tailscale_ip(host: str) -> bool:
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        (isinstance(ip, ipaddress.IPv4Address) and ip in _TAILSCALE_IPV4_NET)
        or (isinstance(ip, ipaddress.IPv6Address) and ip in _TAILSCALE_IPV6_NET)
    )


def is_trusted_tailscale_request(request_or_ws: Request | WebSocket | None) -> bool:
    if request_or_ws is None or not _is_tailscale_mode_enabled():
        return False
    headers = getattr(request_or_ws, "headers", None) or {}
    if _header_value(headers, "cf-connecting-ip"):
        return False
    client = getattr(request_or_ws, "client", None)
    host = str(getattr(client, "host", "") or "").strip().lower()
    is_ts_ip = _is_tailscale_ip(host)
    # Path A: Tailscale Serve (tailnet only).
    # Uvicorn's ProxyHeadersMiddleware rewrites client.host from 127.0.0.1 to the
    # forwarded tailnet peer IP (100.64.0.0/10 or fd7a:115c:a1e0::/48) when X-Forwarded-For
    # is set by local tailscaled, while direct ASGI / TestClient leaves host in _TRUSTED_LOCAL_HOSTS.
    if (host in _TRUSTED_LOCAL_HOSTS or is_ts_ip) and _header_value(headers, "tailscale-user-login"):
        return True
    # Path B: Direct connection over the tailnet without a reverse proxy.
    if is_ts_ip and not _header_value(headers, "x-forwarded-for") and not _header_value(headers, "x-real-ip"):
        return True
    return False


def extract_actor_token(request_or_ws: Request | WebSocket | None) -> Optional[str]:
    if request_or_ws is None:
        return None
    headers = getattr(request_or_ws, "headers", None) or {}
    tok = headers.get("x-hikayat-token")
    if tok and str(tok).strip():
        return str(tok).strip()
    auth_hdr = headers.get("authorization") or ""
    if isinstance(auth_hdr, str) and auth_hdr.lower().startswith("bearer "):
        b_tok = auth_hdr[7:].strip()
        if b_tok:
            return b_tok
    q_params = getattr(request_or_ws, "query_params", None)
    if q_params is not None:
        q_tok = q_params.get("token")
        if q_tok and str(q_tok).strip():
            return str(q_tok).strip()
    return None


async def verify_user_access(request_or_ws: Request | WebSocket | None, user_id: int) -> int:
    uid = int(user_id)
    canonical_id = int(await adb(db.resolve_canonical_user_id, uid))
    token = extract_actor_token(request_or_ws)
    strict = is_strict_auth_context(request_or_ws)
    if token is not None or strict:
        valid = verify_actor_token(token, uid) or (
            canonical_id != uid and verify_actor_token(token, canonical_id)
        )
        if not valid:
            raise HTTPException(
                status_code=401,
                detail="Authentication required or invalid actor token.",
            )
    return canonical_id


def _coerce_optional_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, (str, bytes)):
        text = (value.decode("utf-8", errors="ignore") if isinstance(value, bytes) else value).strip()
        if text and text.lstrip("-").isdigit():
            return int(text)
    return None


def _resolve_effective_session_uid(
    request_or_ws: Request | WebSocket | None,
    user_id: Optional[int],
    session_data: Dict[str, Any],
) -> Optional[int]:
    eff_uid = _coerce_optional_int(user_id)
    if eff_uid is not None:
        return eff_uid
    raw_tok = extract_actor_token(request_or_ws)
    if raw_tok is not None:
        tok_uid = extract_verified_token_uid(raw_tok)
        if tok_uid is None:
            raise HTTPException(status_code=401, detail="Invalid actor token.")
        return tok_uid
    if is_strict_auth_context(request_or_ws):
        raise HTTPException(status_code=401, detail="user_id and actor token are required.")
    return _coerce_optional_int(session_data.get("host_user_id"))


def _collect_allowed_session_uids(
    members: list[Any],
    session_data: Dict[str, Any],
) -> set[int]:
    allowed_ids = {int(m) for m in members if m is not None}
    for key in ("host_user_id", "turn_user_id"):
        uid_val = _coerce_optional_int(session_data.get(key))
        if uid_val is not None:
            allowed_ids.add(uid_val)
    for t_uid in (session_data.get("turn_order") or []):
        parsed_uid = _coerce_optional_int(t_uid)
        if parsed_uid is not None:
            allowed_ids.add(parsed_uid)
    return allowed_ids


def _is_direct_inproc_call(request_or_ws: Request | WebSocket | None) -> bool:
    return request_or_ws is None and not is_strict_auth_context(request_or_ws)


def _enforce_turn_ownership(
    session_data: Dict[str, Any],
    eff_uid: int,
    canonical_id: int,
) -> None:
    if str(session_data.get("mode") or "").lower() != "turn":
        return
    curr_turn_uid = db.current_turn_user_id(session_data)
    if curr_turn_uid is not None and int(curr_turn_uid) not in (eff_uid, canonical_id):
        raise HTTPException(
            status_code=403,
            detail="It is not currently your turn in this co-op session.",
        )


async def verify_session_participant(
    request_or_ws: Request | WebSocket | None,
    session_id: int,
    user_id: Optional[int] = None,
    require_turn: bool = False,
    session: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], int]:
    sess_row: Optional[Dict[str, Any]] = session if isinstance(session, dict) else await adb(db.get_session, session_id)
    if not sess_row:
        raise HTTPException(status_code=404, detail="Session not found")

    inproc = _is_direct_inproc_call(request_or_ws)
    eff_uid = _resolve_effective_session_uid(request_or_ws, user_id, sess_row)
    if eff_uid is None:
        if inproc:
            return dict(sess_row), 0
        raise HTTPException(status_code=401, detail="Could not resolve session actor.")

    canonical_id = await verify_user_access(request_or_ws, eff_uid)
    members = await adb(db.get_session_members, session_id) or []
    allowed_ids = _collect_allowed_session_uids(members, sess_row)
    if not allowed_ids and inproc:
        allowed_ids.add(eff_uid)

    if not ({eff_uid, canonical_id} & allowed_ids):
        raise HTTPException(
            status_code=403,
            detail="You are not a member of this adventure session.",
        )

    if require_turn:
        _enforce_turn_ownership(sess_row, eff_uid, canonical_id)

    return dict(sess_row), eff_uid
