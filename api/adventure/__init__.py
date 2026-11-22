from __future__ import annotations

import asyncio
from contextlib import nullcontext
import json
import re
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

import character_data as cd
import db
from db import adb
import game_engine
import scenario_data
from scenario_data import get_scenario_display_name
from mechanics.combat.loadouts import ensure_combatant_loadout
from mechanics.narrative.campaign_spine import _PLACEHOLDER_ACTOR_RE
from mechanics.narrative.dossier_compiler import resolve_quest_npc_fallback_gender
from mechanics.social.races import roll_scenario_npc_race
from mechanics.system.concurrency import distributed_adventure_lock, distributed_session_lock
from mechanics.world import resolve_scene_merchant_ui_state
from services.examine_service import invalidate_examine_cache
from services.turn_service import TurnService
from ..deps import (
    ActionRequest,
    CancelTurnRequest,
    EndAdventureRequest,
    JoinAdventureRequest,
    LoadSlotRequest,
    RerollImageRequest,
    ResumeSessionRequest,
    RetryAdventureRequest,
    SaveSlotRequest,
    StartAdventureRequest,
    ToggleNonLethalRequest,
    ToggleStealthRequest,
    _serializable_action,
    enrich_choices_with_odds,
    enrich_session_party_members,
    logger,
    manager,
)
from ..security import verify_session_participant, verify_user_access
from . import (
    enrichment as _mod_enrichment,
    in_flight as _mod_in_flight,
    locations as _mod_locations,
    routes_session as _mod_routes_session,
    routes_turn as _mod_routes_turn,
)
from .in_flight import (
    _BACKGROUND_TASKS,
    _IN_FLIGHT_TURN_TASKS,
    _LAST_TURN_ERRORS,
    _cancel_session_in_flight_task,
    _cancel_unstarted_in_flight_entry_locked,
    _get_active_in_flight_turn,
    _load_error_session_snapshot,
    _make_ws_stream_controls,
    _record_last_turn_error,
    _spawn_background_task,
    check_in_flight_guard,
    fail_or_broadcast_error,
    launch_in_flight_ws_task,
)
from .enrichment import (
    _UNNAMED_ACTOR_TOKENS,
    _enrich_session_for_client,
    _enrich_session_for_client_body,
    _is_unnamed_or_generic_actor,
    _sanitize_enemy_telegraph_view,
    _trigger_scene_image_broadcast,
    enrich_session_for_client,
)
from .routes_session import (
    delete_save,
    end_adventure,
    get_active_session,
    get_character_sessions_endpoint,
    get_session_image,
    join_adventure,
    list_open_lobbies,
    list_saves,
    load_slot,
    resume_session_endpoint,
    save_slot,
    start_adventure,
)
from .routes_turn import (
    _execute_action_locked,
    _execute_opening_retry_locked,
    _execute_retry_dispatch_locked,
    _execute_retry_narration_locked,
    cancel_in_flight_turn,
    examine_adventure_scene,
    execute_action,
    reroll_adventure_image,
    retry_adventure_scene,
    toggle_adventure_non_lethal,
    toggle_adventure_stealth,
)
from .locations import (
    _build_locations_payload,
    get_world_map_locations,
)

router = APIRouter()
router.include_router(_mod_routes_session.router)
router.include_router(_mod_routes_turn.router)
router.include_router(_mod_locations.router)

_SUBMODULES = (
    _mod_in_flight,
    _mod_enrichment,
    _mod_routes_session,
    _mod_routes_turn,
    _mod_locations,
)
_SUBMODULE_NAMES = frozenset(
    {"in_flight", "enrichment", "routes_session", "routes_turn", "locations"}
)

from db.core.module_proxy import install_submodule_proxy as _install_submodule_proxy

_install_submodule_proxy(__name__, _SUBMODULES, _SUBMODULE_NAMES, cls_name="_AdventurePackageModule")

__all__ = [
    "ActionRequest",
    "CancelTurnRequest",
    "EndAdventureRequest",
    "JoinAdventureRequest",
    "LoadSlotRequest",
    "RerollImageRequest",
    "ResumeSessionRequest",
    "RetryAdventureRequest",
    "SaveSlotRequest",
    "StartAdventureRequest",
    "ToggleNonLethalRequest",
    "ToggleStealthRequest",
    "TurnService",
    "_BACKGROUND_TASKS",
    "_IN_FLIGHT_TURN_TASKS",
    "_LAST_TURN_ERRORS",
    "_UNNAMED_ACTOR_TOKENS",
    "_build_locations_payload",
    "_cancel_session_in_flight_task",
    "_cancel_unstarted_in_flight_entry_locked",
    "_enrich_session_for_client",
    "_enrich_session_for_client_body",
    "_execute_action_locked",
    "_execute_opening_retry_locked",
    "_execute_retry_dispatch_locked",
    "_execute_retry_narration_locked",
    "_get_active_in_flight_turn",
    "_is_unnamed_or_generic_actor",
    "_load_error_session_snapshot",
    "_make_ws_stream_controls",
    "_record_last_turn_error",
    "_sanitize_enemy_telegraph_view",
    "_serializable_action",
    "_spawn_background_task",
    "_trigger_scene_image_broadcast",
    "adb",
    "cancel_in_flight_turn",
    "cd",
    "check_in_flight_guard",
    "db",
    "delete_save",
    "end_adventure",
    "enrich_choices_with_odds",
    "enrich_session_for_client",
    "enrich_session_party_members",
    "examine_adventure_scene",
    "execute_action",
    "fail_or_broadcast_error",
    "game_engine",
    "get_active_session",
    "get_character_sessions_endpoint",
    "get_session_image",
    "get_world_map_locations",
    "invalidate_examine_cache",
    "join_adventure",
    "launch_in_flight_ws_task",
    "list_open_lobbies",
    "list_saves",
    "load_slot",
    "logger",
    "manager",
    "reroll_adventure_image",
    "resume_session_endpoint",
    "retry_adventure_scene",
    "router",
    "save_slot",
    "scenario_data",
    "start_adventure",
    "toggle_adventure_non_lethal",
    "toggle_adventure_stealth",
    "verify_session_participant",
    "verify_user_access",
]
