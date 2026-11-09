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
    SESSION_ANOMALY_KEY_TO_RECORD_TYPE,
    append_dossier_state_event,
    append_spine_state_event,
    get_campaign_spine,
    get_effective_session_turn,
    get_quest_dossier,
    get_session_anomaly_records,
    get_session_participant_user_ids,
    get_session_quest_dossiers,
    get_user_folklore_codex,
    get_users_folklore_codex_batch,
    hydrate_session_anomaly_records,
    persist_anomalous_quest_containment,
    record_folklore_codex_progress,
    record_session_anomaly_field_log,
    retire_or_cooldown_folklore_in_session,
    rollback_quest_dossiers_after_turn,
    rollback_session_anomaly_logs_after_turn,
    sync_session_anomaly_records_from_extra,
    upsert_campaign_spine,
    upsert_quest_dossier,
    user_has_folklore_recognition,
)
from .sessions import get_session_characters
from .inventory import (
    atomic_merchant_purchase,
    get_inventories_for_characters,
    sell_inventory_item,
    set_item_quest_lock,
)
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
    _backfill_session_anomaly_records_v45,
    _migrate_zone_split_and_hidden_villages_v49,
    _migrate_dynamic_social_overhaul_v50,
    _migrate_main_quest_bounty_overhaul_v51,
    _delete_session_child_records_only,
    _delete_session_records,
    _is_suspicious_entity_text,
    _safe_int_db,
    _sanitize_npcs_list,
    _to_str,
    nullify_orphaned_implicated_contacts,
)
from .characters import _apply_debug_stat_override, delete_character_by_id, get_character_3axis, set_character_3axis
from .quests import (
    _enrich_quest_dict,
    compute_quest_main_progress_ratio,
    is_quest_main_objectives_complete,
    promote_locked_quest_waypoints,
    sync_quest_projection_from_dossier,
    unlock_climax_waypoint,
    update_quest_anomaly_blueprint,
)
from .social import (
    _active_resolving_contacts,
    _parse_faction_row,
    backfill_exempt_and_legacy_contact_discoveries,
    canon_social_npc_id,
    clear_clear_the_air_gate,
    delete_contact,
    get_character_social_daily,
    get_character_social_daily_batch,
    get_contact_dossier_discoveries,
    get_contact_dossier_discoveries_batch,
    get_npc_social_composure,
    get_npc_social_composure_batch,
    get_player_fow_exemption_sets,
    get_school_directory_batch,
    get_social_topic_states,
    get_social_topic_states_batch,
    record_contact_dossier_discoveries,
    rollback_actor_physical_state_after_turn,
    rollback_social_pacing_state_after_turn,
    set_clear_the_air_gate,
    snapshot_session_physical_state_for_turn,
    snapshot_session_social_state_for_turn,
    upsert_character_social_daily,
    upsert_npc_social_composure,
    upsert_social_topic_state,
)
from .properties import *
from .properties import (
    atomic_purchase_property,
    get_character_inventory_capacity,
    get_player_properties,
    get_primary_property,
    grant_or_relocate_starter_quarters,
    grant_property_spare_key,
    revoke_property_spare_key,
    rollback_player_properties_after_turn,
    set_primary_property,
)
from .contracts import *
from .contracts import (
    ENTITY_CONTRACTS_V52_DDL,
    apply_contract_breach_strike,
    build_contract_key,
    build_grudge_key,
    get_exclusive_tier3_holder,
    get_player_active_pacts,
    get_session_active_grudges,
    get_session_pacts_batch,
    get_user_patron_compendium,
    get_users_contracted_codex_map,
    is_patron_spurned_for_holder,
    liberate_npc_exclusive_pacts,
    mark_pact_zero_minute_step_used,
    record_pact_resonance_and_charges,
    rollback_entity_contracts_after_turn,
    save_contract_turn_snapshot,
    seed_npc_entity_contract,
    sever_entity_contract,
    sign_entity_contract,
    upgrade_entity_contract_tier,
    upsert_user_patron_compendium,
)
