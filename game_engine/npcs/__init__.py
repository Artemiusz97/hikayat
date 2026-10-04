"""NPC dialogue tracking, room presence, and post-turn entity reconciliation."""
from .dialogue_tracking import (
    DIALOGUE_STALL_VERBS,
    count_dialogue_stall_turns,
    format_dialogue_stall_directive,
    build_scene_escalation_and_consequence_directives,
    get_session_dialogue_partners,
    is_dialogue_partner,
    extract_speaking_npcs_from_narrative,
    is_npc_invited_in_action,
)
from .presence import (
    sync_hostile_entities,
    classify_scene_npcs,
    extract_departed_npcs_from_narrative,
    is_mentioned_only_in_absence_or_memory,
    reset_departed_guest_locations,
    _distribute_fallback_locations,
)
from .reconciliation import (
    process_scene_npcs,
    _sanitize_outcome_person_names,
)

__all__ = [
    "DIALOGUE_STALL_VERBS",
    "count_dialogue_stall_turns",
    "format_dialogue_stall_directive",
    "build_scene_escalation_and_consequence_directives",
    "get_session_dialogue_partners",
    "is_dialogue_partner",
    "extract_speaking_npcs_from_narrative",
    "is_npc_invited_in_action",
    "sync_hostile_entities",
    "classify_scene_npcs",
    "extract_departed_npcs_from_narrative",
    "is_mentioned_only_in_absence_or_memory",
    "reset_departed_guest_locations",
    "_distribute_fallback_locations",
    "process_scene_npcs",
    "_sanitize_outcome_person_names",
]
