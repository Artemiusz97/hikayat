from __future__ import annotations

from .catalog import (
    PATRONS_DATA_PATH,
    VALID_ARCHETYPES,
    apply_patron_variant_and_locale,
    build_pact_spell_def,
    build_pact_spell_id,
    ensure_pact_spells_registered,
    get_bespoke_patrons,
    get_patron_by_id,
    is_entity_contracts_scenario,
    is_patron_allowed_in_scenario,
    load_entity_patrons_catalog,
    synthesize_folklore_patron,
    synthesize_procedural_sapient_patron,
)
from .appraisal import (
    APPRAISAL_COST_MULTIPLIERS,
    RESONANCE_XP_THRESHOLDS,
    STAT_COL_MAP,
    apply_active_pact_modifiers,
    build_pact_bound_gear_spec,
    can_afford_stat_locks,
    compute_pact_cast_costs,
    compute_tier_locks_for_patron,
    evaluate_patron_appraisal,
    get_pact_slot_capacity,
    get_unmodified_base_max_hp,
    get_unmodified_base_stat,
)
from .formatting import (
    build_actor_pact_tell_phrase,
    build_pact_turn_stage_direction,
    collect_pact_sdxl_tags,
)
from .resolver import (
    BLACK_MARKET_ROTATION_IDS,
    CAMPUS_SEVEN_MYSTERIES_IDS,
    DEATHS_DOOR_PATRON_IDS,
    VAULT_FACTION_RULES,
    assign_special_agent_contracts,
    build_contracts_overview_payload,
    can_perform_peaceful_medical_or_shrine_scrub,
    can_perform_remote_pact_ritual,
    compute_pact_field_dc_modifier,
    compute_pact_travel_time_multiplier,
    evaluate_kin_authority,
    evaluate_post_turn_pact_costs_and_breaches,
    execute_pact_ritual_action,
    get_available_patrons_for_context,
    has_companion_vault_sponsorship,
    spawn_manifestation_exorcism_boss,
)
