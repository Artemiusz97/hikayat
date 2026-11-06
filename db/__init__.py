from __future__ import annotations

from .core import *
from .characters import *
from .inventory import *
from .settings import *
from .sessions import *
from .saves import *
from .quests import *
from .dossiers import *
from .dossiers import (
    append_dossier_state_event,
    get_campaign_spine,
    get_quest_dossier,
    get_session_participant_user_ids,
    get_session_quest_dossiers,
    get_user_folklore_codex,
    record_folklore_codex_progress,
    record_session_anomaly_field_log,
    retire_or_cooldown_folklore_in_session,
    rollback_quest_dossiers_after_turn,
    rollback_session_anomaly_logs_after_turn,
    upsert_campaign_spine,
    upsert_quest_dossier,
    user_has_folklore_recognition,
)
from .sessions import get_session_characters
from .inventory import set_item_quest_lock
from .social import *
from .world import *
from .memory import *
from .memory import (
    MAX_DIGEST_BULLETS,
    MAX_ROLLING_DIGEST_BULLETS,
    active_recall_search,
    add_npc_memory,
    add_session_chronicle,
    finalize_turn_memory,
    get_npc_memories_batch,
    get_session_chronicles,
    get_session_digests,
    rebuild_session_digests_fts,
    recall_chapter_digests,
    resync_latest_digest_turn,
    run_deterministic_tier3_compaction,
)
from .world_events import *
from .world_events import (
    apply_contact_loyalty_bonus,
    claim_minor_event_bounty,
    claim_rumor_investigation,
    create_witness_scandal_event,
    defer_world_event_expiry,
    find_contacts_by_identity_candidates,
    get_world_event_by_key,
    get_world_event_candidate_context,
    get_world_events,
    get_world_events as get_active_world_events,
    mark_world_event_cold,
)
from .core import (
    _delete_session_child_records_only,
    _delete_session_records,
    _is_suspicious_entity_text,
    _safe_int_db,
    _sanitize_npcs_list,
    _to_str,
    nullify_orphaned_implicated_contacts,
)
from .characters import _apply_debug_stat_override, get_character_3axis, set_character_3axis
from .quests import _enrich_quest_dict, unlock_climax_waypoint, promote_locked_quest_waypoints
from .social import _active_resolving_contacts, _parse_faction_row, delete_contact, get_school_directory_batch
