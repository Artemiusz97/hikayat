from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

CharIdPolicy = Literal[
    "none",
    "always_host",
    "if_host_or_empty",
    "if_host_exact",
    "dossier_zero_default",
]

RollbackMode = Literal[
    "handler",
    "delete_gt_turn",
    "derived_rebuild",
    "static_world",
    "none",
]


@dataclass(frozen=True)
class SessionTableSpec:
    """Declarative lifecycle contract for a session-scoped or legacy/virtual session table."""

    name: str
    # --- Purge ---
    purge_order: int = 50
    preserve_on_opening_retry: bool = False
    optional_table: bool = False
    is_fts_virtual: bool = False
    # --- Save / Load Slot ---
    include_in_save_slot: bool = True
    load_tier: int = 30
    orig_id_alias: Optional[str] = None
    char_id_policy: CharIdPolicy = "none"
    session_key_cols: tuple[str, ...] = ()
    save_row_limit_by_turn: Optional[int] = None
    save_order_col: Optional[str] = None
    row_transform_hook: Optional[str] = None
    post_load_hook: Optional[str] = None
    post_inventory_hook: Optional[str] = None
    # --- Turn Rollback ---
    rollback_mode: RollbackMode = "none"
    rollback_turn_col: Optional[str] = None
    rollback_result_key: Optional[str] = None
    rollback_handler: Optional[str] = None
    # --- Snapshot Ring-Buffer Pruning ---
    snapshot_table_turn_col: Optional[str] = None
    snapshot_keep_last: int = 10


# Non-child global / root tables (never purged or cloned as session child rows).
GLOBAL_TABLES: frozenset[str] = frozenset({
    "sessions",
    "characters",
    "inventory",
    "user_settings",
    "discord_users",
    "procedural_spells",
    "adventure_saves",
    "user_folklore_codex",
    "user_patron_compendium",
    "session_locks",
    "schema_migrations",
})

# Virtual FTS5 tables whose internal *_config/*_content/*_data/*_docsize/*_idx shadow
# tables are managed automatically by SQLite.
FTS5_VIRTUAL_TABLES: frozenset[str] = frozenset({
    "session_digests_fts",
})


SESSION_TABLE_REGISTRY: tuple[SessionTableSpec, ...] = (
    # --- Optional / Legacy / Virtual Tables (excluded from active SESSION_CHILD_TABLES) ---
    SessionTableSpec(
        name="session_digest_vectors",
        purge_order=10,
        optional_table=True,
        include_in_save_slot=False,
        rollback_mode="none",
    ),
    SessionTableSpec(
        name="session_digests_fts",
        purge_order=10,
        optional_table=True,
        is_fts_virtual=True,
        include_in_save_slot=False,
        rollback_mode="derived_rebuild",
        rollback_handler="db.memory.rebuild_session_digests_fts",
    ),
    SessionTableSpec(
        name="phone_appointments",
        purge_order=10,
        optional_table=True,
        include_in_save_slot=False,
        rollback_mode="none",
    ),
    # --- Active Session Child Tables (exact 41 tables in SESSION_CHILD_TABLES) ---
    SessionTableSpec(
        name="session_locations",
        rollback_mode="static_world",
    ),
    SessionTableSpec(
        name="world_nodes",
        rollback_mode="handler",
        rollback_handler="mechanics.world.locations.folklore_veil.rollback_folklore_veil_state_after_turn",
    ),
    SessionTableSpec(
        name="world_edges",
        rollback_mode="handler",
        rollback_handler="mechanics.world.locations.folklore_veil.rollback_folklore_veil_state_after_turn",
    ),
    SessionTableSpec(
        name="lorebook",
        rollback_mode="none",
    ),
    SessionTableSpec(
        name="school_directory",
        rollback_mode="static_world",
    ),
    # contacts must purge BEFORE households because contacts.household_id REFERENCES households(id)
    # and must load AFTER households (load_tier=20 > 10) to remap household_id.
    SessionTableSpec(
        name="contacts",
        purge_order=20,
        load_tier=20,
        orig_id_alias="_orig_contact_id",
        char_id_policy="always_host",
        row_transform_hook="restore_contact_row",
        post_load_hook="rematerialize_contacts_relations",
        rollback_mode="handler",
        rollback_handler="db.sessions.rollback_session_normalized_state_after_turn",
    ),
    SessionTableSpec(
        name="factions",
        rollback_mode="static_world",
    ),
    SessionTableSpec(
        name="quests",
        row_transform_hook="rewrite_quest_remediation_scar",
        rollback_mode="handler",
        rollback_handler="db.dossiers.rollback_quest_dossiers_after_turn",
    ),
    SessionTableSpec(
        name="quest_waypoints",
        rollback_mode="handler",
        rollback_handler="db.dossiers.rollback_quest_dossiers_after_turn",
    ),
    SessionTableSpec(
        name="session_clues",
        orig_id_alias="_orig_clue_id",
        post_load_hook="remap_clue_deduction_parents",
        rollback_mode="delete_gt_turn",
        rollback_turn_col="turn_created",
        rollback_result_key="session_clues_deleted",
    ),
    SessionTableSpec(
        name="phone_messages",
        rollback_mode="none",
    ),
    SessionTableSpec(
        name="phone_daily_interactions",
        rollback_mode="none",
    ),
    SessionTableSpec(
        name="phone_gossip_feed",
        rollback_mode="none",
    ),
    SessionTableSpec(
        name="commitments_ledger",
        orig_id_alias="_orig_commitment_id",
        session_key_cols=("commitment_key",),
        post_load_hook="remap_commitments_conflicting_ids",
        rollback_mode="delete_gt_turn",
        rollback_turn_col="turn_created",
        rollback_result_key="commitments_deleted",
    ),
    SessionTableSpec(
        name="session_digests",
        post_load_hook="rebuild_session_digests_fts",
        rollback_mode="handler",
        rollback_handler="db.sessions.rollback_session_normalized_state_after_turn",
    ),
    SessionTableSpec(
        name="session_chronicles",
        rollback_mode="handler",
        rollback_handler="db.sessions.rollback_session_normalized_state_after_turn",
    ),
    SessionTableSpec(
        name="npc_memories",
        rollback_mode="delete_gt_turn",
        rollback_turn_col="turn_index",
        rollback_result_key="npc_memories_deleted",
    ),
    SessionTableSpec(
        name="session_members",
        preserve_on_opening_retry=True,
        include_in_save_slot=False,
        rollback_mode="static_world",
    ),
    SessionTableSpec(
        name="households",
        purge_order=80,
        load_tier=10,
        orig_id_alias="_orig_household_id",
        session_key_cols=("household_key",),
        rollback_mode="static_world",
    ),
    SessionTableSpec(
        name="intimate_events",
        rollback_mode="handler",
        rollback_handler="mechanics.social.persona.intimacy.ledger.delete_intimate_events_after_turn",
    ),
    SessionTableSpec(
        name="social_persons",
        rollback_mode="static_world",
    ),
    SessionTableSpec(
        name="social_ties",
        rollback_mode="handler",
        rollback_handler="mechanics.social.relationship_graph.rollback_ties_after_turn",
    ),
    SessionTableSpec(
        name="actor_physical_states",
        rollback_mode="handler",
        rollback_handler="db.social.rollback_actor_physical_state_after_turn",
    ),
    SessionTableSpec(
        name="actor_garments",
        rollback_mode="handler",
        rollback_handler="db.social.rollback_actor_physical_state_after_turn",
    ),
    SessionTableSpec(
        name="actor_physical_turn_snapshots",
        save_row_limit_by_turn=3,
        save_order_col="turn_number",
        rollback_mode="handler",
        rollback_handler="db.social.rollback_actor_physical_state_after_turn",
        snapshot_table_turn_col="turn_number",
        snapshot_keep_last=10,
    ),
    SessionTableSpec(
        name="world_events",
        load_tier=40,
        session_key_cols=("event_key", "escalation_event_key"),
        row_transform_hook="remap_world_event_contact_id",
        rollback_mode="handler",
        rollback_handler="db.world_events.rollback_world_events_after_turn",
    ),
    SessionTableSpec(
        name="campaign_spines",
        load_tier=40,
        row_transform_hook="rewrite_campaign_spine_session_keys",
        post_load_hook="remap_campaign_spines_nested_ids",
        rollback_mode="handler",
        rollback_handler="db.dossiers.rollback_quest_dossiers_after_turn",
    ),
    SessionTableSpec(
        name="quest_dossiers",
        load_tier=40,
        post_load_hook="remap_quest_dossiers_nested_ids",
        post_inventory_hook="remap_quest_dossiers_inventory_ids",
        rollback_mode="handler",
        rollback_handler="db.dossiers.rollback_quest_dossiers_after_turn",
    ),
    SessionTableSpec(
        name="session_anomaly_records",
        rollback_mode="handler",
        rollback_handler="db.dossiers.rollback_session_anomaly_logs_after_turn",
    ),
    SessionTableSpec(
        name="player_properties",
        post_load_hook="sync_loaded_player_properties",
        rollback_mode="handler",
        rollback_handler="db.properties.rollback_player_properties_after_turn",
    ),
    SessionTableSpec(
        name="npc_social_composure",
        rollback_mode="handler",
        rollback_handler="db.social_pacing.rollback_social_pacing_state_after_turn",
    ),
    SessionTableSpec(
        name="character_social_daily",
        char_id_policy="if_host_or_empty",
        rollback_mode="handler",
        rollback_handler="db.social_pacing.rollback_social_pacing_state_after_turn",
    ),
    SessionTableSpec(
        name="social_topic_states",
        char_id_policy="if_host_or_empty",
        rollback_mode="handler",
        rollback_handler="db.social_pacing.rollback_social_pacing_state_after_turn",
    ),
    SessionTableSpec(
        name="contact_dossier_discoveries",
        char_id_policy="dossier_zero_default",
        rollback_mode="handler",
        rollback_handler="db.social_pacing.rollback_social_pacing_state_after_turn",
    ),
    SessionTableSpec(
        name="social_turn_snapshots",
        save_row_limit_by_turn=3,
        save_order_col="turn_number",
        row_transform_hook="remap_social_turn_snapshot_json",
        rollback_mode="handler",
        rollback_handler="db.social_pacing.rollback_social_pacing_state_after_turn",
        snapshot_table_turn_col="turn_number",
        snapshot_keep_last=10,
    ),
    SessionTableSpec(
        name="session_entity_contracts",
        session_key_cols=("contract_key",),
        row_transform_hook="remap_entity_contract_holder",
        rollback_mode="handler",
        rollback_handler="db.contracts.rollback_entity_contracts_after_turn",
    ),
    SessionTableSpec(
        name="session_contract_grudges",
        char_id_policy="if_host_exact",
        session_key_cols=("grudge_key",),
        rollback_mode="handler",
        rollback_handler="db.contracts.rollback_entity_contracts_after_turn",
    ),
    SessionTableSpec(
        name="session_contract_turn_snapshots",
        save_row_limit_by_turn=3,
        save_order_col="turn_number",
        row_transform_hook="remap_contract_turn_snapshot_json",
        rollback_mode="handler",
        rollback_handler="db.contracts.rollback_entity_contracts_after_turn",
        snapshot_table_turn_col="turn_number",
        snapshot_keep_last=10,
    ),
    SessionTableSpec(
        name="world_roster",
        row_transform_hook="normalize_world_roster_row",
        rollback_mode="handler",
        rollback_handler="db.roster.rollback_world_roster_after_turn",
    ),
    SessionTableSpec(
        name="epistemic_facts",
        load_tier=40,
        post_inventory_hook="remap_epistemic_proof_refs",
        rollback_mode="handler",
        rollback_handler="db.epistemic.rollback_epistemic_state_after_turn",
    ),
    SessionTableSpec(
        name="epistemic_knowledge",
        load_tier=40,
        rollback_mode="handler",
        rollback_handler="db.epistemic.rollback_epistemic_state_after_turn",
    ),
)


SESSION_TABLE_MAP: dict[str, SessionTableSpec] = {
    spec.name: spec for spec in SESSION_TABLE_REGISTRY
}


def get_session_child_table_names() -> tuple[str, ...]:
    """Returns active session-scoped child table names (preserving legacy SESSION_CHILD_TABLES)."""
    return tuple(spec.name for spec in SESSION_TABLE_REGISTRY if not spec.optional_table)


def get_purge_specs(preserve_members: bool = False) -> list[SessionTableSpec]:
    """Returns registry specs sorted in FK-safe deletion order (children before parents)."""
    specs = [
        spec
        for spec in SESSION_TABLE_REGISTRY
        if not (preserve_members and spec.preserve_on_opening_retry)
    ]
    specs.sort(key=lambda s: s.purge_order)
    return specs


def get_save_specs() -> list[SessionTableSpec]:
    """Returns registry specs eligible for checkpoint serialization in save_adventure_slot()."""
    return [spec for spec in SESSION_TABLE_REGISTRY if spec.include_in_save_slot]


def get_load_specs() -> list[SessionTableSpec]:
    """Returns registry specs eligible for checkpoint restoration, sorted in parent-first tier order."""
    specs = [spec for spec in SESSION_TABLE_REGISTRY if spec.include_in_save_slot]
    specs.sort(key=lambda s: s.load_tier)
    return specs


def get_snapshot_prune_specs() -> list[SessionTableSpec]:
    """Returns registry specs for turn-indexed snapshot tables subject to ring-buffer GC."""
    return [spec for spec in SESSION_TABLE_REGISTRY if spec.snapshot_table_turn_col]


def get_simple_rollback_specs() -> list[SessionTableSpec]:
    """Returns registry specs handled by uniform DELETE WHERE session_id = ? AND <turn_col> > ?."""
    return [spec for spec in SESSION_TABLE_REGISTRY if spec.rollback_mode == "delete_gt_turn"]
