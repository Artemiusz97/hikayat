from __future__ import annotations
"""
mechanics/combat/core.py

Lightweight backward-compatible re-export facade for Hikayat Combat Architecture.
Preserves all legacy public call paths while delegating to specialized modules:
  - precompute.py (Phases 1-3, threat ledger, boss telegraphing, 1vN cap)
  - reconcile.py (Phases 4-5, post-LLM outcome reconciliation, post_combat delegator)
  - post_combat.py (defeat triage, companion scaling, threat decay, DoT cleanup)
  - enemies.py & enemy_profiles.py (scenario rosters, stats, armor/weapon profiles, danger zones)
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
    normalize_status_list,
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
    get_combat_prompt_and_schema,
    is_in_combat,
    precompute_combat_turn,
)
from .player_spells import apply_status_with_boss_surge, resolve_player_spell_action
from .player_turn import resolve_player_combat_phase
from .ally_turn import resolve_ally_combat_phase, resolve_extra_player_actions
from .enemy_turn import resolve_enemy_combat_phase
from .loadouts import (
    ALL_STATS,
    ARCHETYPE_RULES,
    MUNDANE_COMBAT_SCENARIOS,
    ROLE_TIER_MULTIPLIERS,
    TIER_RANK_TO_ROLE,
    build_combatant_stat_sheet,
    compute_companion_vitals,
    ensure_combatant_loadout,
    is_mundane_combat_scenario,
    reset_combatant_cooldowns,
    tick_combatant_cooldowns,
)
from .reconcile import (
    _enemy_has_unsealed_tether,
    _record_non_incursion_anomaly_kills,
    cleanup_anomalous_combat_session_state,
    decay_round_threat,
    finalize_post_combat_state,
    prune_dead_combat_state,
    reconcile_combat_results,
)
from .enemies import (
    AFFIX_REGISTRY,
    CANONICAL_INTENT_CODES,
    GENERIC_ENEMY_KEYWORDS,
    SCENARIO_ENEMIES,
    SCENARIO_ENEMY_TEMPLATES,
    _resolve_enemy_scenario_key,
    build_companion_stat_sheet,
    build_enemy_stat_sheet,
    build_monster_stat_sheet,
    derive_taxonomy_weaknesses,
    disambiguate_enemy_list,
    generate_balanced_encounter,
    generate_scenario_enemy,
    generate_scenario_monster,
    get_intent_code,
    infer_taxonomy_from_archetype,
    is_generic_enemy_name,
    resolve_party_member_actions,
    roll_encounter_difficulty,
    roll_enemy_affixes,
    roll_enemy_intent,
)
from .enemy_profiles import (
    ANOMALOUS_FACILITY_NAME_KEYWORDS,
    ANOMALOUS_TIER2_FACILITY_IDS,
    get_enemy_armor_profile,
    get_enemy_weapon_profile,
    is_anomalous_danger_zone,
    should_allow_random_encounter,
)
from .targeting import (
    apply_boss_cc_stagger_surge,
    arm_boss_telegraph,
    check_boss_telegraph_interrupt,
    compute_party_scaled_interrupt_threshold,
    populate_enemy_hud_telemetry,
    resolve_threat_target,
    update_threat_on_action,
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
    "resolve_player_combat_phase",
    "resolve_player_spell_action",
    "resolve_extra_player_actions",
    "resolve_ally_combat_phase",
    "resolve_enemy_combat_phase",
    "apply_status_with_boss_surge",
    "_enemy_has_unsealed_tether",
    "_record_non_incursion_anomaly_kills",
    "cleanup_anomalous_combat_session_state",
    # Loadouts & Stat Sheets
    "ALL_STATS",
    "ARCHETYPE_RULES",
    "MUNDANE_COMBAT_SCENARIOS",
    "ROLE_TIER_MULTIPLIERS",
    "TIER_RANK_TO_ROLE",
    "build_combatant_stat_sheet",
    "compute_companion_vitals",
    "ensure_combatant_loadout",
    "is_mundane_combat_scenario",
    "reset_combatant_cooldowns",
    "tick_combatant_cooldowns",
    # Threat & Telegraph
    "update_threat_on_action",
    "resolve_threat_target",
    "arm_boss_telegraph",
    "apply_boss_cc_stagger_surge",
    "check_boss_telegraph_interrupt",
    "compute_party_scaled_interrupt_threshold",
    "populate_enemy_hud_telemetry",
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
    "normalize_status_list",
    "tick_status_instance_timers",
    # Types
    "BossTelegraphState",
    "CombatAction",
    "CombatThreatLedger",
    "CombatantState",
    "StatusEffectInstance",
    "get_combatant_stat",
    # Post-Combat & Telegraph Cleanup
    "finalize_post_combat_state",
    "prune_dead_combat_state",
    # Enemies & Profiles
    "AFFIX_REGISTRY",
    "ANOMALOUS_FACILITY_NAME_KEYWORDS",
    "ANOMALOUS_TIER2_FACILITY_IDS",
    "CANONICAL_INTENT_CODES",
    "GENERIC_ENEMY_KEYWORDS",
    "SCENARIO_ENEMIES",
    "SCENARIO_ENEMY_TEMPLATES",
    "build_companion_stat_sheet",
    "build_enemy_stat_sheet",
    "build_monster_stat_sheet",
    "derive_taxonomy_weaknesses",
    "disambiguate_enemy_list",
    "generate_balanced_encounter",
    "generate_scenario_enemy",
    "generate_scenario_monster",
    "get_enemy_armor_profile",
    "get_enemy_weapon_profile",
    "get_intent_code",
    "infer_taxonomy_from_archetype",
    "is_anomalous_danger_zone",
    "is_generic_enemy_name",
    "resolve_party_member_actions",
    "roll_encounter_difficulty",
    "roll_enemy_affixes",
    "roll_enemy_intent",
    "should_allow_random_encounter",
]
