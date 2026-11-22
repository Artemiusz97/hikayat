from __future__ import annotations

import asyncio
import copy
import inspect
import json
import logging
import os
import random
import re
import sys as _sys
import tempfile
import types as _types
from typing import Any, Any as _Any, Callable, Dict, List, Optional, Tuple

import httpx
from openai import APIError as OpenAIAPIError
from pydantic import BaseModel, ConfigDict, Field

import character_data as cd
import db
from db import adb
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

    start_adventure = staticmethod(_embark_mod.start_adventure)
    commit_opening_scene = staticmethod(_embark_mod.commit_opening_scene)
    _await_uninterruptible = staticmethod(_models_mod._await_uninterruptible)
    _finalize_and_save_scene = staticmethod(_resolve_mod._finalize_and_save_scene)
    _reconcile_client_direct_choice = staticmethod(_prepare_mod._reconcile_client_direct_choice)
    prepare_and_roll_action = staticmethod(_prepare_mod.prepare_and_roll_action)
    resolve_action = staticmethod(_resolve_mod.resolve_action)
    _resolve_action_with_crash_capture = staticmethod(_resolve_mod._resolve_action_with_crash_capture)
    _resolve_action_inner = staticmethod(_resolve_mod._resolve_action_inner)
    retry_narration = staticmethod(_resolve_mod.retry_narration)


_SUBMODULES = (_models_mod, _embark_mod, _prepare_mod, _resolve_mod)
_SUBMODULE_NAMES = frozenset({"models", "embark", "prepare", "resolve"})


class _TurnServiceFacadeModule(_types.ModuleType):
    """Propagates module-level monkeypatches on `services.turn_service` into `services.turn.*`."""

    def __setattr__(self, name: str, value: _Any) -> None:
        super().__setattr__(name, value)
        if not name.startswith("__") and name not in _SUBMODULE_NAMES:
            for _sub in _SUBMODULES:
                if name in _sub.__dict__:
                    setattr(_sub, name, value)

    def __delattr__(self, name: str) -> None:
        super().__delattr__(name)
        if not name.startswith("__") and name not in _SUBMODULE_NAMES:
            for _sub in _SUBMODULES:
                if name in _sub.__dict__:
                    delattr(_sub, name)


_sys.modules[__name__].__class__ = _TurnServiceFacadeModule

__all__ = [
    "Any",
    "BaseModel",
    "Callable",
    "ConfigDict",
    "Dict",
    "Field",
    "List",
    "OpenAIAPIError",
    "Optional",
    "Tuple",
    "TurnResponse",
    "TurnService",
    "XP_REWARDS",
    "_BACKGROUND_TASKS",
    "_callable_accepts_kwarg",
    "_is_llm_unavailable_exception",
    "adb",
    "apply_merchant_encounter_result",
    "asyncio",
    "cd",
    "copy",
    "crash_capture",
    "db",
    "game_engine",
    "httpx",
    "inspect",
    "json",
    "llm_client",
    "log",
    "logger",
    "logging",
    "os",
    "random",
    "re",
    "scenario_data",
    "tempfile",
]
