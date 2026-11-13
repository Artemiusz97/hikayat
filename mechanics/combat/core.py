from __future__ import annotations
"""
mechanics/combat/core.py

Lightweight backward-compatible re-export facade for Hikayat Combat Architecture.
Preserves all legacy public call paths while delegating to specialized modules:
  - precompute.py (Phases 1-3, threat ledger, boss telegraphing, ephemeral deck cache)
  - reconcile.py (Phases 4-5, post-LLM outcome reconciliation, threat decay)
"""
from .formulas import (
    calculate_opposed_dc,
    calculate_tactical_damage,
    calculate_turn_damage,
    get_elemental_multiplier,
    tick_status_timers,
    try_inflict_status,
)
from .sparring import (
    call_faction_reinforcements,
    is_sparring_monster,
    make_sparring_monster,
    resolve_sparring_defeat,
)
from .status_effects import (
    apply_status_effect,
    format_status_badge,
    get_status_stat_modifiers,
    normalize_status_effect,
    tick_status_instance_timers,
)
from .types import (
    BossTelegraphState,
    CombatAction,
    CombatThreatLedger,
    CombatantState,
    StatusEffectInstance,
    get_combatant_stat,
)
from .precompute import (
    COMBAT_CHOICE_SCHEMA,
    COMBAT_SYSTEM_PROMPT,
    arm_boss_telegraph,
    check_boss_telegraph_interrupt,
    get_combat_prompt_and_schema,
    is_in_combat,
    precompute_combat_turn,
    resolve_threat_target,
    update_threat_on_action,
)
from .reconcile import (
    _enemy_has_unsealed_tether,
    _record_non_incursion_anomaly_kills,
    cleanup_anomalous_combat_session_state,
    decay_round_threat,
    reconcile_combat_results,
)

__all__ = [
    # Prompts & Schemas
    "COMBAT_SYSTEM_PROMPT",
    "COMBAT_CHOICE_SCHEMA",
    "is_in_combat",
    "get_combat_prompt_and_schema",
    # Precompute & Reconcile Pipelines
    "precompute_combat_turn",
    "reconcile_combat_results",
    "_enemy_has_unsealed_tether",
    "_record_non_incursion_anomaly_kills",
    "cleanup_anomalous_combat_session_state",
    # Threat & Telegraph
    "update_threat_on_action",
    "resolve_threat_target",
    "arm_boss_telegraph",
    "check_boss_telegraph_interrupt",
    "decay_round_threat",
    # Formulas & Sparring
    "calculate_opposed_dc",
    "calculate_tactical_damage",
    "calculate_turn_damage",
    "get_elemental_multiplier",
    "tick_status_timers",
    "try_inflict_status",
    "call_faction_reinforcements",
    "is_sparring_monster",
    "make_sparring_monster",
    "resolve_sparring_defeat",
    # Status Effects
    "apply_status_effect",
    "format_status_badge",
    "get_status_stat_modifiers",
    "normalize_status_effect",
    "tick_status_instance_timers",
    # Types
    "BossTelegraphState",
    "CombatAction",
    "CombatThreatLedger",
    "CombatantState",
    "StatusEffectInstance",
    "get_combatant_stat",
]
