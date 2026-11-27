from __future__ import annotations

import asyncio
import uuid
from typing import AsyncGenerator, Iterable, Optional
import logging
from contextlib import asynccontextmanager
from fastapi import HTTPException
import db

log = logging.getLogger("hikayat.concurrency")

class LockAcquisitionError(Exception):
    pass


async def _resolve_lock_user_id(loop: asyncio.AbstractEventLoop, user_id: int) -> int:
    uid = int(user_id)
    if uid > 10**16:
        try:
            canon = await loop.run_in_executor(None, db.resolve_canonical_user_id, uid)
            if canon and int(canon) > 0:
                return int(canon)
        except Exception:
            pass
    return uid


async def _release_lock_cancel_safe(loop: asyncio.AbstractEventLoop, lock_key: str, owner_id: str) -> None:
    fut = loop.run_in_executor(None, db.release_distributed_lock, lock_key, owner_id)
    try:
        await asyncio.shield(fut)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.exception("Failed to release distributed lock %s: %s", lock_key, e)


async def _acquire_lock_cancel_safe(loop: asyncio.AbstractEventLoop, lock_key: str, owner_id: str) -> bool:
    fut = loop.run_in_executor(None, db.acquire_distributed_lock, lock_key, owner_id)
    try:
        return bool(await asyncio.shield(fut))
    except asyncio.CancelledError:
        def _cleanup_on_done(done_fut):
            try:
                if not done_fut.cancelled() and done_fut.exception() is None and bool(done_fut.result()):
                    loop.run_in_executor(None, db.release_distributed_lock, lock_key, owner_id)
            except Exception as exc:
                log.exception("Failed scheduling deferred release for %s: %s", lock_key, exc)

        try:
            acquired_late = bool(await asyncio.shield(fut))
            if acquired_late:
                await _release_lock_cancel_safe(loop, lock_key, owner_id)
        except asyncio.CancelledError:
            if fut.done():
                _cleanup_on_done(fut)
            else:
                fut.add_done_callback(_cleanup_on_done)
        raise


@asynccontextmanager
async def distributed_session_lock(session_id: int, owner_id: str = None, raise_http_error: bool = True) -> AsyncGenerator[None, None]:
    """
    A distributed-safe lock for session state mutations.
    Raises HTTPException(409) if the lock is already held.
    """
    if not owner_id:
        owner_id = str(uuid.uuid4())
    lock_key = f"session_{session_id}"
    
    # Run the DB lock acquisition in a threadpool so it doesn't block the loop
    loop = asyncio.get_running_loop()
    acquired = await _acquire_lock_cancel_safe(loop, lock_key, owner_id)
    
    if not acquired:
        log.warning(f"Failed to acquire distributed lock for session {session_id} by {owner_id}")
        if raise_http_error:
            raise HTTPException(
                status_code=409,
                detail="Turn resolution currently in progress for this session. Please wait."
            )
        else:
            raise LockAcquisitionError("Turn resolution currently in progress for this session. Please wait.")
        
    try:
        yield
    finally:
        await _release_lock_cancel_safe(loop, lock_key, owner_id)

@asynccontextmanager
async def distributed_user_lock(user_id: int, owner_id: str = None) -> AsyncGenerator[None, None]:
    """
    A distributed-safe lock for user-level operations (like starting an adventure).
    Raises HTTPException(409) if the lock is already held.
    """
    if not owner_id:
        owner_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    canon_uid = await _resolve_lock_user_id(loop, user_id)
    lock_key = f"user_{canon_uid}"
    
    acquired = await _acquire_lock_cancel_safe(loop, lock_key, owner_id)
    
    if not acquired:
        log.warning(f"Failed to acquire distributed lock for user {canon_uid} by {owner_id}")
        raise HTTPException(
            status_code=409,
            detail="Adventure start already in progress for this user."
        )
        
    try:
        yield
    finally:
        await _release_lock_cancel_safe(loop, lock_key, owner_id)


@asynccontextmanager
async def distributed_adventure_lock(
    user_id: Optional[int],
    session_ids: int | Iterable[int] | None = None,
    owner_id: Optional[str] = None,
    raise_http_error: bool = True,
) -> AsyncGenerator[None, None]:
    """
    Canonical hierarchical lock acquiring `user_{user_id}` BEFORE sorted `session_{sid}` locks,
    eliminating cross-endpoint races and ABBA deadlocks across start/load/save/end/companion flows.
    """
    if not owner_id:
        owner_id = str(uuid.uuid4())

    loop = asyncio.get_running_loop()
    lock_keys: list[str] = []
    if user_id is not None and int(user_id) > 0:
        canon_uid = await _resolve_lock_user_id(loop, int(user_id))
        lock_keys.append(f"user_{canon_uid}")

    raw_sids: list[int] = []
    if isinstance(session_ids, int):
        raw_sids = [session_ids]
    elif session_ids is not None:
        raw_sids = [int(s) for s in session_ids if s is not None and int(s) > 0]

    for sid in sorted({s for s in raw_sids if s > 0}):
        lock_keys.append(f"session_{sid}")

    acquired_keys: list[str] = []
    try:
        for lk in lock_keys:
            ok = await _acquire_lock_cancel_safe(loop, lk, owner_id)
            if not ok:
                log.warning("Failed to acquire hierarchical lock %s by %s", lk, owner_id)
                err_msg = (
                    "Adventure start already in progress for this user. Please wait."
                    if lk.startswith("user_")
                    else "Another action is currently in progress for this adventure session. Please wait."
                )
                if raise_http_error:
                    raise HTTPException(
                        status_code=409,
                        detail=err_msg,
                    )
                raise LockAcquisitionError(err_msg)
            acquired_keys.append(lk)
        yield
    finally:
        rel_keys = list(reversed(acquired_keys))
        for idx, lk in enumerate(rel_keys):
            try:
                await _release_lock_cancel_safe(loop, lk, owner_id)
            except asyncio.CancelledError:
                for rem_lk in rel_keys[idx + 1:]:
                    try:
                        loop.run_in_executor(None, db.release_distributed_lock, rem_lk, owner_id)
                    except Exception as exc:
                        log.exception("Failed scheduling remaining lock release for %s: %s", rem_lk, exc)
                raise


@asynccontextmanager
async def acquire_background_session_lock(
    session_id: int,
    *,
    retries: int = 12,
    delay_seconds: float = 0.5,
) -> AsyncGenerator[bool, None]:
    """Retries non-blocking session lock briefly so background jobs serialize behind an active turn."""
    lock_key = f"session_{session_id}"
    owner_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    acquired = False
    try:
        attempts = max(1, int(retries or 1))
        for attempt in range(attempts):
            acquired = await _acquire_lock_cancel_safe(loop, lock_key, owner_id)
            if acquired:
                break
            if attempt + 1 < attempts:
                await asyncio.sleep(delay_seconds)
        yield acquired
    finally:
        if acquired:
            await _release_lock_cancel_safe(loop, lock_key, owner_id)
