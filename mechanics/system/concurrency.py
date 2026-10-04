import asyncio
import uuid
from typing import AsyncGenerator
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
