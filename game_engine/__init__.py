from __future__ import annotations

from .keywords import *
from .prompts import *
from .schemas import *
from .core import *
from .core import _get_npc_name, _norm_dialogue_name
from .context import *
from .context import _character_sheet_text, _party_sheet_text, _describe_tracked_entity, _history_text, _known_world_text, _style_block, _scenario_block
from .context import _load_known_world, _world_canon_text, _scene_context_text, _quest_board_parts
from .npcs import *
from .npcs import _sanitize_outcome_person_names, _distribute_fallback_locations
from .quests import *
from .quests import _is_valid_investigation_note, _is_similar_clue, can_accept_side_bounty, can_accept_rumor_investigation, can_accept_minor_bounty
from .quest_lifecycle import (
    sanitize_dossier_prose,
    compile_campaign_spine_at_turn_zero,
    seed_or_discover_dossier_clue,
    sync_waypoints_from_dossier,
    enrich_dossier_with_utility_llm,
    accept_bounty_contract,
    accept_bounty_contract_async,
    forfeit_side_bounty,
    hot_swap_dossier_entities,
    prewarm_chapter_ahead,
    build_universal_epilogue_choices,
    evaluate_skipped_threatened_optionals,
    resolve_chapter_transition,
    resolve_epilogue_choice,
    complete_remediation_bounty_if_linked,
    heal_session_quests_on_load,
    sync_dossier_main_stage_advance,
)
from .quest_turn_resolver import (
    is_approach_burned,
    unlock_hidden_quest_optional,
    resolve_quest_optional_objective,
    resolve_quest_approach_failure,
    evaluate_nonlinear_leads_and_climax_gate,
    resolve_quest_combat_outcome,
    evaluate_intimate_liaison_turn,
    handle_npc_death_or_recruitment_fallout,
    resolve_clue_source_claim,
    resolve_post_turn_dossier_hooks,
)
from mechanics.narrative.bounty import generate_faction_bounty_board
from .quest_agency import (
    prune_completed_stage_choices,
    resolve_caseboard_deduction,
    resolve_suspect_accusation,
    acquire_quest_macguffin,
    resolve_quest_turn_in_or_betrayal,
    evaluate_schedule_curfew_and_coop_precedence,
    redact_quest_for_fog_of_war,
    build_fog_of_war_quest_payload,
    build_fog_of_war_quest_prompt_block,
    format_fow_dossier_for_narrator,
)
from .state import *
from .turn import *
from .turn_context import TurnContext
from .choices_cleaner import clean_choices_impl, sanitize_and_diversify_choices, build_hybrid_turn_choices, is_malformed_choice_label
from .prompt_layout import build_language_directive, build_side_channel_language_directive
from .pronoun_resolver import tag_narrative_pronouns, strip_pronoun_tags, annotate_turn_pronouns
from llm_client import call_llm_json, call_llm_json_stream
from mechanics.social.roster_tags import (
    AgeGroup,
    derive_age_group,
    normalize_standing,
    normalize_social_role_type,
    is_contact_eligible_demographic,
    is_merchant_character,
    resolve_character_badges,
    get_dialogue_register,
    format_dialogue_register_directive,
)
