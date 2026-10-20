"""
mechanics/world/schedules.py — Unified Facade for World Schedule & NPC Schedule
===============================================================================
Re-exports all World Schedule (`mechanics.world.world_schedule`) and
NPC Schedule (`mechanics.world.npc_schedule`) functions and constants
for seamless integration and backward compatibility across the engine.
"""
from __future__ import annotations

from .world_schedule import (
    SCENARIO_WORLD_SCHEDULES,
    is_weekend,
    get_day_type,
    is_high_school_setting,
    resolve_genre_schedule_key,
    get_scenario_schedule_profile,
    get_scenario_wake_minute,
    get_scenario_sleep_minute,
    is_abandoned_school_node,
    is_campus_node_or_location,
    get_world_schedule_state,
    evaluate_world_schedule_node_access,
)

from .npc_schedule import (
    SCHEDULE_TIME_BLOCKS,
    BLOCK_BOUNDARIES,
    get_time_block_key,
    get_detailed_npc_time_phase,
    is_schedule_transition_imminent,
    detect_schedule_boundary_crossed,
    get_npc_schedule_node_ids,
    get_npc_scheduled_node_id,
    get_npc_schedule,
    get_npc_scheduled_location,
)

__all__ = [
    # World Schedule
    "SCENARIO_WORLD_SCHEDULES",
    "is_weekend",
    "get_day_type",
    "is_high_school_setting",
    "resolve_genre_schedule_key",
    "get_scenario_schedule_profile",
    "get_scenario_wake_minute",
    "get_scenario_sleep_minute",
    "is_abandoned_school_node",
    "is_campus_node_or_location",
    "get_world_schedule_state",
    "evaluate_world_schedule_node_access",
    # NPC Schedule
    "SCHEDULE_TIME_BLOCKS",
    "BLOCK_BOUNDARIES",
    "get_time_block_key",
    "get_detailed_npc_time_phase",
    "is_schedule_transition_imminent",
    "detect_schedule_boundary_crossed",
    "get_npc_schedule_node_ids",
    "get_npc_scheduled_node_id",
    "get_npc_schedule",
    "get_npc_scheduled_location",
]
