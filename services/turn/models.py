from __future__ import annotations

import asyncio
import logging
import sys
import httpx
from openai import APIError as OpenAIAPIError
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from typing import Any, Dict, List, Optional

from db.core.module_proxy import callable_accepts_kwarg as _callable_accepts_kwarg_impl

log = logging.getLogger(__name__)
logger = log


def _callable_accepts_kwarg(fn: Any, kwarg: str) -> bool:
    """Returns True if callable (or wrapped mock side_effect) accepts `kwarg` or `**kwargs`."""
    return _callable_accepts_kwarg_impl(fn, kwarg)


def _is_llm_unavailable_exception(exc: BaseException) -> bool:
    """Return True only when an exception originates from upstream LLM/network unavailability."""
    if isinstance(exc, (OpenAIAPIError, httpx.HTTPError, TimeoutError, ConnectionError, asyncio.TimeoutError)):
        return True
    if isinstance(exc, RuntimeError) and "all llm candidate models in fallback chain failed" in str(exc).lower():
        return True
    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc:
        return _is_llm_unavailable_exception(cause)
    return False


_BACKGROUND_TASKS: set[asyncio.Task] = set()


class TurnResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    success: bool
    session: Dict[str, Any]
    outcome: Dict[str, Any]          # Always a dict — outcome is coerced before storing here
    action: Dict[str, Any]
    actions: List[Dict[str, Any]] = []
    items_gained_by_user: Dict[Any, List[str]]   # {user_id: [item_name, ...]}
    xp_gained: int
    levels_gained: List[int]
    xp_by_user: Dict[Any, int] = {}
    levels_by_user: Dict[Any, List[int]] = {}
    new_char: Dict[str, Any]
    scene_persisted: bool = False
    scene_title: str = ""
    next_narrative: str = ""
    cleaned_choices: List[Dict[str, Any]] = Field(default_factory=list)


async def _await_uninterruptible(coro, *, reraise_cancel: bool = True):
    """Await a short transactional coroutine without letting task cancellation abort DB cleanup."""
    task = asyncio.ensure_future(coro)
    deferred_cancel: Optional[asyncio.CancelledError] = None
    while True:
        try:
            res = await asyncio.shield(task)
            break
        except asyncio.CancelledError as c_err:
            deferred_cancel = c_err
    if deferred_cancel is not None and reraise_cancel:
        raise deferred_cancel
    return res


def _get_turn_service():
    """Resolve TurnService dynamically so test monkeypatches on services.turn_service.TurnService apply."""
    mod = sys.modules.get("services.turn_service")
    if mod is None:
        import services.turn_service as mod
    return mod.TurnService
