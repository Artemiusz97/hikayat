"""Discord AdventureCog embed builders package."""
from __future__ import annotations

import db
import game_engine
from character_data import get_item_icon
from db.core.module_proxy import install_submodule_proxy as _install_submodule_proxy
from localization import get_quest_ui_label
from mechanics.combat.status_effects import format_status_badge
from mechanics.world.locations import (
    clean_narrative_location_arrows,
    format_clean_location_badge,
    format_tiered_location_string,
)
from scenario_data import DEFAULT_SCENARIO, ScenarioError, load_scenarios
from . import (
    caseboard as _mod_caseboard,
    party as _mod_party,
    quests as _mod_quests,
    scene as _mod_scene,
)
from .caseboard import (
    _build_bounties_embed,
    _build_bounty_board_embed,
    _build_caseboard_embed,
    _build_history_embed,
    _build_quest_log_embed,
)
from .party import (
    MODE_LABELS,
    _RESULT_COLORS,
    _RESULT_TITLES,
    _choice_button_label,
    _format_companion_kit_summary,
    _format_items_gained,
    _format_items_gained_multi,
    _format_status_list_for_embed,
    _format_tracker_entity,
    _get_choice_emoji,
    _get_choice_quest_icon,
    _get_choice_skill_emoji,
    _is_dialogue_partner,
    _location_text,
    _norm_name,
    _parse_status_effects,
    _party_vitals_text,
    _safe_add_field,
    _safe_int,
    _scenario_command_choices,
    _strip_leading_emojis,
    _tracker_group_text,
    _tracker_header,
    _truncate_embed_text,
    _truncate_field_name,
    _truncate_field_value,
    is_matching_contact_dialogue_partner,
)
from .quests import (
    _build_campaign_goals_embed,
    _build_chronicle_tapestry_embed,
    _build_main_quest_embed,
    _format_fow_dossier_embed_fields,
    _format_structured_quest_embed_fields,
    _get_quest_scenario_labels,
    _resolve_reveal_all,
    _resolve_session_ui_lang,
    format_threat_consequence,
)
from .scene import (
    _append_conversation_pause_field,
    _append_dialogue_mood_field,
    _crowd_density_badge,
    _format_epistemic_watch_text,
    build_facility_rooms_embed,
    build_outcome_embeds,
    build_world_map_embed,
    build_zone_places_embed,
    prepare_discord_image,
    scene_embed,
    sync_scene_embed,
)

_SUBMODULES = (_mod_party, _mod_scene, _mod_quests, _mod_caseboard)
_SUBMODULE_NAMES = frozenset({"party", "scene", "quests", "caseboard"})

_PRIVATE_EXPORTS = (
    db,
    game_engine,
    _RESULT_COLORS,
    _RESULT_TITLES,
    _append_conversation_pause_field,
    _append_dialogue_mood_field,
    _build_bounties_embed,
    _build_bounty_board_embed,
    _build_campaign_goals_embed,
    _build_caseboard_embed,
    _build_chronicle_tapestry_embed,
    _build_history_embed,
    _build_main_quest_embed,
    _build_quest_log_embed,
    _choice_button_label,
    _crowd_density_badge,
    _format_companion_kit_summary,
    _format_epistemic_watch_text,
    _format_fow_dossier_embed_fields,
    _format_items_gained,
    _format_items_gained_multi,
    _format_status_list_for_embed,
    _format_structured_quest_embed_fields,
    _format_tracker_entity,
    _get_choice_emoji,
    _get_choice_quest_icon,
    _get_choice_skill_emoji,
    _get_quest_scenario_labels,
    _is_dialogue_partner,
    _location_text,
    _norm_name,
    _parse_status_effects,
    _party_vitals_text,
    _resolve_reveal_all,
    _resolve_session_ui_lang,
    _safe_add_field,
    _safe_int,
    _scenario_command_choices,
    _strip_leading_emojis,
    _tracker_group_text,
    _tracker_header,
    _truncate_embed_text,
    _truncate_field_name,
    _truncate_field_value,
)

_install_submodule_proxy(__name__, _SUBMODULES, _SUBMODULE_NAMES, cls_name="_AdventureEmbedsPackageModule")

__all__ = [
    "DEFAULT_SCENARIO",
    "MODE_LABELS",
    "ScenarioError",
    "build_facility_rooms_embed",
    "build_outcome_embeds",
    "build_world_map_embed",
    "build_zone_places_embed",
    "clean_narrative_location_arrows",
    "format_clean_location_badge",
    "format_status_badge",
    "format_threat_consequence",
    "format_tiered_location_string",
    "get_item_icon",
    "get_quest_ui_label",
    "is_matching_contact_dialogue_partner",
    "load_scenarios",
    "prepare_discord_image",
    "scene_embed",
    "sync_scene_embed",
]
