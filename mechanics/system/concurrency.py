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
    acquired = await loop.run_in_executor(None, db.acquire_distributed_lock, lock_key, owner_id)
    
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
        try:
            await loop.run_in_executor(None, db.release_distributed_lock, lock_key, owner_id)
        except Exception as e:
            log.exception(f"Failed to release distributed lock for session {session_id}: {e}")

@asynccontextmanager
async def distributed_user_lock(user_id: int, owner_id: str = None) -> AsyncGenerator[None, None]:
    """
    A distributed-safe lock for user-level operations (like starting an adventure).
    Raises HTTPException(409) if the lock is already held.
    """
    if not owner_id:
        owner_id = str(uuid.uuid4())
    lock_key = f"user_{user_id}"
    
    loop = asyncio.get_running_loop()
    acquired = await loop.run_in_executor(None, db.acquire_distributed_lock, lock_key, owner_id)
    
    if not acquired:
        log.warning(f"Failed to acquire distributed lock for user {user_id} by {owner_id}")
        raise HTTPException(
            status_code=409,
            detail="Adventure start already in progress for this user."
        )
        
    try:
        yield
    finally:
        try:
            await loop.run_in_executor(None, db.release_distributed_lock, lock_key, owner_id)
        except Exception as e:
            log.exception(f"Failed to release distributed lock for user {user_id}: {e}")


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

    lock_keys: list[str] = []
    if user_id is not None and int(user_id) > 0:
        lock_keys.append(f"user_{int(user_id)}")

    raw_sids: list[int] = []
    if isinstance(session_ids, int):
        raw_sids = [session_ids]
    elif session_ids is not None:
        raw_sids = [int(s) for s in session_ids if s is not None and int(s) > 0]

    for sid in sorted({s for s in raw_sids if s > 0}):
        lock_keys.append(f"session_{sid}")

    loop = asyncio.get_running_loop()
    acquired_keys: list[str] = []
    try:
        for lk in lock_keys:
            ok = await loop.run_in_executor(None, db.acquire_distributed_lock, lk, owner_id)
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
        for lk in reversed(acquired_keys):
            try:
                await loop.run_in_executor(None, db.release_distributed_lock, lk, owner_id)
            except Exception as e:
                log.exception("Failed to release hierarchical lock %s: %s", lk, e)
