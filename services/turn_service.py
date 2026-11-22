from __future__ import annotations

import functools as _functools
import inspect as _inspect
from typing import Any as _Any

import httpx
from openai import APIError as OpenAIAPIError

import character_data as cd
import db
from db import adb
from db.core.module_proxy import install_submodule_proxy as _install_submodule_proxy
import game_engine
import llm_client
import scenario_data
from character_data import XP_REWARDS
from mechanics.combat.merchant import apply_merchant_encounter_result
from services import crash_capture
from .turn import embark as _embark_mod
from .turn import models as _models_mod
from .turn import prepare as _prepare_mod
from .turn import resolve as _resolve_mod
from .turn.models import (
    TurnResponse,
    _BACKGROUND_TASKS,
    _callable_accepts_kwarg,
    _is_llm_unavailable_exception,
    log,
    logger,
)


class TurnService:
    """Facade preserving canonical `TurnService.<method>` dispatch over `services/turn/`."""

    @staticmethod
    @_functools.wraps(_embark_mod.start_adventure)
    async def start_adventure(*args: _Any, **kwargs: _Any) -> _Any:
        res = _embark_mod.start_adventure(*args, **kwargs)
        return await res if _inspect.isawaitable(res) else res

    @staticmethod
    @_functools.wraps(_embark_mod.commit_opening_scene)
    async def commit_opening_scene(*args: _Any, **kwargs: _Any) -> _Any:
        res = _embark_mod.commit_opening_scene(*args, **kwargs)
        return await res if _inspect.isawaitable(res) else res

    @staticmethod
    @_functools.wraps(_models_mod._await_uninterruptible)
    async def _await_uninterruptible(*args: _Any, **kwargs: _Any) -> _Any:
        res = _models_mod._await_uninterruptible(*args, **kwargs)
        return await res if _inspect.isawaitable(res) else res

    @staticmethod
    @_functools.wraps(_resolve_mod._finalize_and_save_scene)
    async def _finalize_and_save_scene(*args: _Any, **kwargs: _Any) -> _Any:
        res = _resolve_mod._finalize_and_save_scene(*args, **kwargs)
        return await res if _inspect.isawaitable(res) else res

    @staticmethod
    @_functools.wraps(_prepare_mod._reconcile_client_direct_choice)
    async def _reconcile_client_direct_choice(*args: _Any, **kwargs: _Any) -> _Any:
        res = _prepare_mod._reconcile_client_direct_choice(*args, **kwargs)
        return await res if _inspect.isawaitable(res) else res

    @staticmethod
    @_functools.wraps(_prepare_mod.prepare_and_roll_action)
    async def prepare_and_roll_action(*args: _Any, **kwargs: _Any) -> _Any:
        res = _prepare_mod.prepare_and_roll_action(*args, **kwargs)
        return await res if _inspect.isawaitable(res) else res

    @staticmethod
    @_functools.wraps(_resolve_mod.resolve_action)
    async def resolve_action(*args: _Any, **kwargs: _Any) -> _Any:
        res = _resolve_mod.resolve_action(*args, **kwargs)
        return await res if _inspect.isawaitable(res) else res

    @staticmethod
    @_functools.wraps(_resolve_mod._resolve_action_with_crash_capture)
    async def _resolve_action_with_crash_capture(*args: _Any, **kwargs: _Any) -> _Any:
        res = _resolve_mod._resolve_action_with_crash_capture(*args, **kwargs)
        return await res if _inspect.isawaitable(res) else res

    @staticmethod
    @_functools.wraps(_resolve_mod._resolve_action_inner)
    async def _resolve_action_inner(*args: _Any, **kwargs: _Any) -> _Any:
        res = _resolve_mod._resolve_action_inner(*args, **kwargs)
        return await res if _inspect.isawaitable(res) else res

    @staticmethod
    @_functools.wraps(_resolve_mod.retry_narration)
    async def retry_narration(*args: _Any, **kwargs: _Any) -> _Any:
        res = _resolve_mod.retry_narration(*args, **kwargs)
        return await res if _inspect.isawaitable(res) else res


_SUBMODULES = (_models_mod, _embark_mod, _prepare_mod, _resolve_mod)
_SUBMODULE_NAMES = frozenset({"models", "embark", "prepare", "resolve"})

_install_submodule_proxy(__name__, _SUBMODULES, _SUBMODULE_NAMES, cls_name="_TurnServiceFacadeModule")

__all__ = [
    "OpenAIAPIError",
    "TurnResponse",
    "TurnService",
    "XP_REWARDS",
    "_BACKGROUND_TASKS",
    "_callable_accepts_kwarg",
    "_is_llm_unavailable_exception",
    "adb",
    "apply_merchant_encounter_result",
    "cd",
    "crash_capture",
    "db",
    "game_engine",
    "httpx",
    "llm_client",
    "log",
    "logger",
    "scenario_data",
]
