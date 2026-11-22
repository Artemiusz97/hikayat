from __future__ import annotations

import sqlite3
import time

from .connection import _VERIFIED_TABLE_GROUPS, _VERIFIED_TABLE_GROUPS_LOCK, get_conn
from .migrations_backfills import (
    _migrate_narrative_pacing_values_v58,
    _ensure_living_world_indexes_v55,
    _migrate_zone_split_and_hidden_villages_v49,
    _migrate_anomalous_locations_integrity_v57,
    _migrate_outlaw_factions_v60,
    _migrate_dynamic_social_overhaul_v50,
    _migrate_main_quest_bounty_overhaul_v51,
    _migrate_combat_evolution_v53,
    _backfill_session_anomaly_records_v45,
    _backfill_campaign_spines_from_legacy_sessions,
    _strip_legacy_session_fk_constraints,
    _migrate_clean_cutover_v30,
    _migrate_self_heal_main_area_and_roster_drift_v32,
    _migrate_phone_appointments_to_commitments,
    _migrate_contacts_intimacy_profiles,
)
from .schema import CREATE_SESSION_LOCKS_TABLE, SCHEMA

SCHEMA_MIGRATIONS: list[tuple[int, str, list[str]]] = [
    (1, "add_sessions_extra_json", ["ALTER TABLE sessions ADD COLUMN extra_json TEXT DEFAULT '{}'"]),
    (2, "add_user_settings_stream_narrative", ["ALTER TABLE user_settings ADD COLUMN stream_narrative INTEGER DEFAULT 1"]),
    (3, "add_lorebook_embedding_json", ["ALTER TABLE lorebook ADD COLUMN embedding_json TEXT DEFAULT '[]'"]),
    (
        4,
        "add_characters_faction_membership_columns",
        [
            "ALTER TABLE characters ADD COLUMN joined_faction_id TEXT DEFAULT ''",
            "ALTER TABLE characters ADD COLUMN faction_rank INTEGER DEFAULT 0",
            "ALTER TABLE characters ADD COLUMN faction_title TEXT DEFAULT ''",
        ],
    ),
    (5, "add_sessions_faction_reinforcements_used", ["ALTER TABLE sessions ADD COLUMN faction_reinforcements_used INTEGER DEFAULT 0"]),
    (6, "add_sessions_show_percentages", ["ALTER TABLE sessions ADD COLUMN show_percentages INTEGER DEFAULT 1"]),
    (7, "add_sessions_last_turn_snapshot", ["ALTER TABLE sessions ADD COLUMN last_turn_snapshot_json TEXT DEFAULT '{}'"]),
    (
        8,
        "add_school_directory_gender_and_race",
        [
            "ALTER TABLE school_directory ADD COLUMN gender TEXT DEFAULT ''",
            "ALTER TABLE school_directory ADD COLUMN race TEXT DEFAULT ''",
        ],
    ),
    (
        9,
        "add_discord_users_table",
        [
            """CREATE TABLE IF NOT EXISTS discord_users (
                user_id             INTEGER PRIMARY KEY,
                username            TEXT DEFAULT '',
                display_name        TEXT DEFAULT '',
                updated_at          REAL NOT NULL
            )"""
        ],
    ),
    (
        10,
        "add_contacts_rel_history_json",
        [
            "ALTER TABLE contacts ADD COLUMN rel_history_json TEXT DEFAULT '[]'"
        ],
    ),
    (
        11,
        "add_phone_daily_interactions_table",
        [
            """CREATE TABLE IF NOT EXISTS phone_daily_interactions (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id          INTEGER NOT NULL,
                npc_id              TEXT NOT NULL,
                current_day         INTEGER NOT NULL,
                intent              TEXT NOT NULL,
                attempt_count       INTEGER DEFAULT 0,
                success_count       INTEGER DEFAULT 0,
                over_limit_count    INTEGER DEFAULT 0,
                last_outcome        TEXT DEFAULT '',
                metadata_json       TEXT DEFAULT '{}',
                updated_at          REAL NOT NULL,
                UNIQUE(session_id, npc_id, current_day, intent)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_phone_daily_lookup ON phone_daily_interactions(session_id, npc_id, current_day)",
        ],
    ),
    (
        12,
        "add_characters_appearance_json",
        [
            "ALTER TABLE characters ADD COLUMN appearance_json TEXT DEFAULT '{}'"
        ],
    ),
    (
        13,
        "add_user_settings_language",
        [
            "ALTER TABLE user_settings ADD COLUMN language TEXT DEFAULT 'en'"
        ],
    ),
    (
        14,
        "add_sessions_language",
        [
            "ALTER TABLE sessions ADD COLUMN language TEXT DEFAULT 'en'"
        ],
    ),
    (
        15,
        "add_user_settings_ui_and_narration_language",
        [
            "ALTER TABLE user_settings ADD COLUMN ui_language TEXT DEFAULT 'en'",
            "ALTER TABLE user_settings ADD COLUMN narration_language TEXT DEFAULT 'en'",
        ],
    ),
    (
        16,
        "add_sessions_narration_language",
        [
            "ALTER TABLE sessions ADD COLUMN narration_language TEXT DEFAULT 'en'",
        ],
    ),
    (
        17,
        "add_lorebook_gender",
        [
            "ALTER TABLE lorebook ADD COLUMN gender TEXT DEFAULT ''",
        ],
    ),
    (
        18,
        "add_rendezvous_and_temporary_companions",
        [
            "ALTER TABLE phone_appointments ADD COLUMN topic TEXT DEFAULT ''",
            "ALTER TABLE phone_appointments ADD COLUMN is_confidential INTEGER DEFAULT 0",
            "ALTER TABLE phone_appointments ADD COLUMN origin TEXT DEFAULT 'phone'",
            "ALTER TABLE phone_appointments ADD COLUMN created_minute INTEGER DEFAULT 0",
            "ALTER TABLE phone_appointments ADD COLUMN expiry_minute INTEGER DEFAULT 0",
            "ALTER TABLE phone_appointments ADD COLUMN reminder_sent INTEGER DEFAULT 0",
            "ALTER TABLE sessions ADD COLUMN temporary_companions_json TEXT DEFAULT '[]'",
        ],
    ),
    (
        19,
        "add_spatial_graph_tables_and_session_pointers",
        [
            """CREATE TABLE IF NOT EXISTS world_nodes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    node_id             TEXT NOT NULL,
    parent_id           TEXT DEFAULT NULL,
    name                TEXT NOT NULL,
    node_type           TEXT NOT NULL,
    category            TEXT NOT NULL DEFAULT 'academic',
    privacy_level       TEXT NOT NULL DEFAULT 'public',
    is_enclosed         INTEGER DEFAULT 1,
    is_transit_hub      INTEGER DEFAULT 0,
    access_tier         TEXT DEFAULT 'open',
    curfew_start_min    INTEGER DEFAULT NULL,
    curfew_end_min      INTEGER DEFAULT NULL,
    atmosphere          TEXT DEFAULT '',
    is_dynamic          INTEGER DEFAULT 0,
    state_json          TEXT DEFAULT '{}',
    created_at          REAL,
    UNIQUE(session_id, node_id)
)""",
            "CREATE INDEX IF NOT EXISTS idx_world_nodes_session ON world_nodes(session_id, node_id)",
            "CREATE INDEX IF NOT EXISTS idx_world_nodes_parent ON world_nodes(session_id, parent_id)",
            """CREATE TABLE IF NOT EXISTS world_edges (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    from_node_id        TEXT NOT NULL,
    to_node_id          TEXT NOT NULL,
    travel_minutes      INTEGER DEFAULT 2,
    edge_type           TEXT DEFAULT 'hallway',
    is_bidirectional    INTEGER DEFAULT 1,
    is_locked           INTEGER DEFAULT 0,
    lock_key_item       TEXT DEFAULT '',
    skill_check_type    TEXT DEFAULT '',
    skill_check_dc      INTEGER DEFAULT 0,
    created_at          REAL,
    UNIQUE(session_id, from_node_id, to_node_id)
)""",
            "CREATE INDEX IF NOT EXISTS idx_world_edges_from ON world_edges(session_id, from_node_id)",
            "CREATE INDEX IF NOT EXISTS idx_world_edges_to ON world_edges(session_id, to_node_id)",
            "ALTER TABLE sessions ADD COLUMN current_node_id TEXT DEFAULT ''",
            "ALTER TABLE sessions ADD COLUMN focal_point TEXT DEFAULT ''",
            "ALTER TABLE quest_waypoints ADD COLUMN target_node_id TEXT DEFAULT ''",
            "ALTER TABLE phone_appointments ADD COLUMN target_node_id TEXT DEFAULT ''",
        ],
    ),
    (
        20,
        "add_emotional_tone_and_open_thread",
        [
            "ALTER TABLE npc_memories ADD COLUMN emotional_tone TEXT DEFAULT ''",
            "ALTER TABLE npc_memories ADD COLUMN open_thread TEXT DEFAULT ''",
            "ALTER TABLE contacts ADD COLUMN emotional_tone TEXT DEFAULT ''",
            "ALTER TABLE contacts ADD COLUMN open_thread TEXT DEFAULT ''",
        ],
    ),
    (
        21,
        "add_world_nodes_state_json",
        [
            "ALTER TABLE world_nodes ADD COLUMN state_json TEXT DEFAULT '{}'",
        ],
    ),
    (
        22,
        "add_quest_overhaul_phase1_columns",
        [
            "ALTER TABLE quests ADD COLUMN blueprint_id TEXT DEFAULT ''",
            "ALTER TABLE quests ADD COLUMN client_npc TEXT DEFAULT ''",
            "ALTER TABLE quests ADD COLUMN client_location TEXT DEFAULT ''",
            "ALTER TABLE quests ADD COLUMN required_item TEXT DEFAULT ''",
            "ALTER TABLE quests ADD COLUMN required_item_count INTEGER DEFAULT 1",
            "ALTER TABLE quests ADD COLUMN strikes INTEGER DEFAULT 0",
            "ALTER TABLE quests ADD COLUMN max_strikes INTEGER DEFAULT 2",
            "ALTER TABLE quests ADD COLUMN deadline_day INTEGER DEFAULT NULL",
            "ALTER TABLE quests ADD COLUMN deadline_minute INTEGER DEFAULT NULL",
            "ALTER TABLE quests ADD COLUMN resolution_approach TEXT DEFAULT ''",
            "ALTER TABLE quest_waypoints ADD COLUMN follow_npc_schedule INTEGER DEFAULT 0",
            "ALTER TABLE quest_waypoints ADD COLUMN required_item TEXT DEFAULT ''",
            "ALTER TABLE quest_waypoints ADD COLUMN valid_time_phases_json TEXT DEFAULT '[]'",
            "ALTER TABLE quest_waypoints ADD COLUMN approaches_json TEXT DEFAULT '[]'",
        ],
    ),
    (
        23,
        "add_sessions_scene_image_url",
        [
            "ALTER TABLE sessions ADD COLUMN scene_image_url TEXT DEFAULT NULL",
        ],
    ),
    (
        24,
        "add_households_table_and_contact_household_id",
        [
            """CREATE TABLE IF NOT EXISTS households (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                household_key TEXT NOT NULL,
                surname TEXT NOT NULL,
                father_json TEXT NOT NULL DEFAULT '{}',
                mother_json TEXT NOT NULL DEFAULT '{}',
                narrative_siblings_json TEXT NOT NULL DEFAULT '[]',
                residence_location TEXT DEFAULT '',
                created_at REAL,
                updated_at REAL,
                UNIQUE(session_id, household_key)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_households_session_surname ON households(session_id, surname)",
            "ALTER TABLE contacts ADD COLUMN household_id INTEGER REFERENCES households(id)",
            "CREATE INDEX IF NOT EXISTS idx_contacts_household_id ON contacts(household_id)",
        ],
    ),
    (
        25,
        "add_intimate_events_table_and_contact_intimate_profile_json",
        [
            """CREATE TABLE IF NOT EXISTS intimate_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                character_id TEXT NOT NULL,
                partner_id TEXT,
                partner_name TEXT NOT NULL,
                partner_role TEXT,
                turn_number INTEGER DEFAULT 0,
                event_origin TEXT DEFAULT 'past_history',
                act_type TEXT NOT NULL,
                direction TEXT NOT NULL,
                is_physical BOOLEAN DEFAULT 1,
                count INTEGER DEFAULT 1,
                climax_count INTEGER DEFAULT 0,
                is_secret_affair BOOLEAN DEFAULT 0,
                narrative_summary TEXT,
                created_at REAL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_intimate_events_char ON intimate_events(session_id, character_id, is_physical)",
            "CREATE INDEX IF NOT EXISTS idx_intimate_events_session_turn ON intimate_events(session_id, turn_number)",
            "ALTER TABLE contacts ADD COLUMN intimate_profile_json TEXT DEFAULT '{}'",
        ],
    ),
    (
        26,
        "add_social_persons_and_social_ties_tables",
        [
            """CREATE TABLE IF NOT EXISTS social_persons (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id      INTEGER NOT NULL,
                person_key      TEXT NOT NULL,
                display_name    TEXT NOT NULL,
                gender          TEXT DEFAULT '',
                role            TEXT DEFAULT '',
                origin          TEXT DEFAULT 'procedural',
                contact_npc_id  TEXT DEFAULT NULL,
                created_at      REAL,
                updated_at      REAL,
                UNIQUE(session_id, person_key)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_social_persons_contact ON social_persons(session_id, contact_npc_id)",
            """CREATE TABLE IF NOT EXISTS social_ties (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id      INTEGER NOT NULL,
                person_a_key    TEXT NOT NULL,
                person_b_key    TEXT NOT NULL,
                tie_type        TEXT NOT NULL,
                is_directed     INTEGER DEFAULT 0,
                status          TEXT DEFAULT 'active',
                closeness       INTEGER DEFAULT 50,
                visibility      TEXT DEFAULT 'public',
                origin          TEXT DEFAULT 'procedural',
                started_turn    INTEGER DEFAULT 0,
                ended_turn      INTEGER DEFAULT NULL,
                end_reason      TEXT DEFAULT '',
                metadata_json   TEXT DEFAULT '{}',
                created_at      REAL,
                updated_at      REAL
            )""",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_social_ties_active ON social_ties(session_id, person_a_key, person_b_key, tie_type) WHERE status = 'active'",
            "CREATE INDEX IF NOT EXISTS idx_social_ties_a ON social_ties(session_id, person_a_key, status)",
            "CREATE INDEX IF NOT EXISTS idx_social_ties_b ON social_ties(session_id, person_b_key, status)",
        ],
    ),
    (
        27,
        "consolidate_commitments_ledger_and_rendezvous",
        [
            "ALTER TABLE commitments_ledger ADD COLUMN commitment_key TEXT DEFAULT ''",
            "ALTER TABLE commitments_ledger ADD COLUMN participants_json TEXT DEFAULT '[]'",
            "ALTER TABLE commitments_ledger ADD COLUMN target_location TEXT DEFAULT ''",
            "ALTER TABLE commitments_ledger ADD COLUMN target_node_id TEXT DEFAULT ''",
            "ALTER TABLE commitments_ledger ADD COLUMN scheduled_day INTEGER DEFAULT 1",
            "ALTER TABLE commitments_ledger ADD COLUMN start_minute INTEGER DEFAULT 0",
            "ALTER TABLE commitments_ledger ADD COLUMN end_minute INTEGER DEFAULT 1439",
            "ALTER TABLE commitments_ledger ADD COLUMN deadline_turn INTEGER DEFAULT NULL",
            "ALTER TABLE commitments_ledger ADD COLUMN origin TEXT DEFAULT 'in_person'",
            "ALTER TABLE commitments_ledger ADD COLUMN is_confidential INTEGER DEFAULT 0",
            "ALTER TABLE commitments_ledger ADD COLUMN title TEXT DEFAULT ''",
            "ALTER TABLE commitments_ledger ADD COLUMN metadata_json TEXT DEFAULT '{}'",
            "ALTER TABLE commitments_ledger ADD COLUMN created_at REAL DEFAULT 0",
            "CREATE INDEX IF NOT EXISTS idx_commitments_time ON commitments_ledger(session_id, scheduled_day, start_minute, end_minute)",
            "CREATE INDEX IF NOT EXISTS idx_commitments_node ON commitments_ledger(session_id, target_node_id, status)",
        ],
    ),
    (
        28,
        "create_actor_physical_states_and_garments",
        [
            """CREATE TABLE IF NOT EXISTS actor_physical_states (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id          INTEGER NOT NULL,
                actor_name          TEXT NOT NULL,
                canonical_key       TEXT NOT NULL,
                actor_type          TEXT DEFAULT 'npc',
                posture             TEXT DEFAULT 'standing',
                posture_qualifier   TEXT DEFAULT '',
                relative_target     TEXT DEFAULT '',
                relative_relation   TEXT DEFAULT '',
                holding             TEXT DEFAULT 'Empty hands',
                stance              TEXT DEFAULT 'Neutral',
                tether_type         TEXT DEFAULT 'none',
                tether_partner      TEXT DEFAULT '',
                composure           TEXT DEFAULT 'composed',
                is_wet              INTEGER DEFAULT 0,
                is_bloodied         INTEGER DEFAULT 0,
                climax_count        INTEGER DEFAULT 0,
                in_refractory       INTEGER DEFAULT 0,
                canonical_outfit_json TEXT DEFAULT '{}',
                created_at          REAL NOT NULL,
                updated_at          REAL NOT NULL,
                UNIQUE(session_id, canonical_key)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_actor_phys_lookup ON actor_physical_states(session_id, canonical_key)",
            """CREATE TABLE IF NOT EXISTS actor_garments (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id          INTEGER NOT NULL,
                actor_key           TEXT NOT NULL,
                slot                TEXT NOT NULL,
                state               TEXT DEFAULT 'worn',
                item_name           TEXT DEFAULT '',
                layer_depth         INTEGER DEFAULT 2,
                updated_at          REAL NOT NULL,
                UNIQUE(session_id, actor_key, slot)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_actor_garments_actor ON actor_garments(session_id, actor_key)",
        ],
    ),
    (
        29,
        "add_sessions_character_id_and_slot",
        [
            "ALTER TABLE sessions ADD COLUMN character_id INTEGER DEFAULT NULL",
            "ALTER TABLE sessions ADD COLUMN slot INTEGER DEFAULT 1",
            "CREATE INDEX IF NOT EXISTS idx_sessions_char_slot ON sessions(character_id, slot, status)",
        ],
    ),
    (
        30,
        "clean_cutover_normalized_models_v30",
        [
            "ALTER TABLE contacts ADD COLUMN household_role TEXT DEFAULT 'child'",
            "ALTER TABLE commitments_ledger ADD COLUMN end_day INTEGER DEFAULT NULL",
        ],
    ),
    (
        31,
        "add_session_clues_is_consumed",
        [
            "ALTER TABLE session_clues ADD COLUMN is_consumed INTEGER DEFAULT 0",
        ],
    ),
    (
        32,
        "self_heal_main_area_and_roster_npc_drift",
        [
            "SELECT 1",
        ],
    ),
    (
        33,
        "add_sessions_schema_epoch",
        [
            "ALTER TABLE sessions ADD COLUMN schema_epoch INTEGER DEFAULT 1",
        ],
    ),
    (
        34,
        "add_world_events_and_pity_counters",
        [
            """CREATE TABLE IF NOT EXISTS world_events (
                id                          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id                  INTEGER NOT NULL,
                event_key                   TEXT NOT NULL,
                template_key                TEXT DEFAULT '',
                entity_type                 TEXT NOT NULL,
                event_subtype               TEXT NOT NULL,
                title                       TEXT NOT NULL,
                description                 TEXT DEFAULT '',
                sfw_fallback_description    TEXT DEFAULT '',
                faction_id                  TEXT DEFAULT '',
                implicated_contact_id       INTEGER DEFAULT NULL,
                location_node_id            TEXT DEFAULT '',
                location_name               TEXT DEFAULT '',
                is_discovered               INTEGER DEFAULT 0,
                discovery_source            TEXT DEFAULT '',
                discovered_turn             INTEGER DEFAULT NULL,
                claimed_turn                INTEGER DEFAULT NULL,
                linked_quest_id             TEXT DEFAULT '',
                status                      TEXT DEFAULT 'active',
                prior_status_before_resolve TEXT DEFAULT 'active',
                turn_created                INTEGER DEFAULT 1,
                resolved_turn               INTEGER DEFAULT NULL,
                original_expires_day        INTEGER DEFAULT NULL,
                original_expires_minute     INTEGER DEFAULT NULL,
                expires_day                 INTEGER DEFAULT NULL,
                expires_minute              INTEGER DEFAULT NULL,
                escalation_chance           REAL DEFAULT 0.0,
                escalation_event_key        TEXT DEFAULT '',
                is_nsfw                     INTEGER DEFAULT 0,
                modifiers_json              TEXT DEFAULT '{}',
                metadata_json               TEXT DEFAULT '{}',
                created_at                  REAL NOT NULL,
                updated_at                  REAL NOT NULL,
                UNIQUE(session_id, event_key)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_world_events_session ON world_events(session_id, status)",
            "CREATE INDEX IF NOT EXISTS idx_world_events_type ON world_events(session_id, entity_type, status)",
            "CREATE INDEX IF NOT EXISTS idx_world_events_contact ON world_events(session_id, implicated_contact_id)",
            "ALTER TABLE sessions ADD COLUMN event_pity_counter REAL DEFAULT 0.0",
            "ALTER TABLE sessions ADD COLUMN rumor_pity_counter REAL DEFAULT 0.0",
            "ALTER TABLE sessions ADD COLUMN player_scandal_cooldown_until_day INTEGER DEFAULT 0",
            "ALTER TABLE sessions ADD COLUMN recent_witness_catches_json TEXT DEFAULT '[]'",
            "ALTER TABLE sessions ADD COLUMN npc_gossip_shared_today_json TEXT DEFAULT '{}'",
        ],
    ),
    (
        35,
        "add_sessions_minor_event_pity_counter",
        [
            "ALTER TABLE sessions ADD COLUMN minor_event_pity_counter REAL DEFAULT 0.0",
        ],
    ),
    (
        36,
        "add_contact_deletion_cleanup_trigger_and_nullify_orphaned_implicated",
        [
            """CREATE TRIGGER IF NOT EXISTS trg_cleanup_implicated_contact
AFTER DELETE ON contacts
BEGIN
    UPDATE world_events SET implicated_contact_id = NULL WHERE implicated_contact_id = OLD.id;
END;""",
            """UPDATE world_events
SET implicated_contact_id = NULL
WHERE implicated_contact_id IS NOT NULL
  AND implicated_contact_id NOT IN (SELECT id FROM contacts);""",
        ],
    ),
    (
        37,
        "caching_and_memory_upgrade_v37",
        [
            """CREATE TABLE IF NOT EXISTS session_digests (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id          INTEGER NOT NULL,
                turn_start          INTEGER NOT NULL,
                turn_end            INTEGER NOT NULL,
                summary_bullets_json TEXT NOT NULL DEFAULT '[]',
                created_at          REAL NOT NULL
            )""",
            """CREATE VIRTUAL TABLE IF NOT EXISTS session_digests_fts USING fts5(
                session_id UNINDEXED,
                bullet_text UNINDEXED,
                search_tokens,
                tokenize='unicode61 remove_diacritics 2'
            )""",
            """CREATE TABLE IF NOT EXISTS session_chronicles (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id          INTEGER NOT NULL,
                chapter_number      INTEGER NOT NULL,
                act_title           TEXT NOT NULL,
                summary_narrative   TEXT NOT NULL,
                key_consequences_json TEXT DEFAULT '[]',
                created_at          REAL NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS npc_memories (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id          INTEGER NOT NULL,
                npc_name            TEXT NOT NULL,
                turn_index          INTEGER NOT NULL,
                memory_fact         TEXT NOT NULL,
                sentiment_delta     INTEGER DEFAULT 0,
                importance          INTEGER DEFAULT 1,
                is_secret           INTEGER DEFAULT 0,
                emotional_tone      TEXT DEFAULT '',
                open_thread         TEXT DEFAULT '',
                created_at          REAL NOT NULL
            )""",
            "ALTER TABLE sessions ADD COLUMN turn_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE sessions ADD COLUMN last_digested_turn INTEGER NOT NULL DEFAULT 0",
            "UPDATE sessions SET turn_count = MAX(0, json_array_length(history_json) - (CASE WHEN json_extract(history_json, '$[0].type') = 'scene' THEN 1 ELSE 0 END)) WHERE turn_count = 0 AND history_json IS NOT NULL AND json_valid(history_json)",
            "ALTER TABLE session_digests ADD COLUMN entities_json TEXT NOT NULL DEFAULT '[]'",
            "ALTER TABLE session_digests ADD COLUMN location_tag TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE session_digests ADD COLUMN quest_ids_json TEXT NOT NULL DEFAULT '[]'",
            "CREATE INDEX IF NOT EXISTS idx_digests_session_turn ON session_digests(session_id, turn_end)",
            "DROP TABLE IF EXISTS session_digest_vectors",
        ],
    ),
    (
        38,
        "compaction_and_chronicle_rollback_v38",
        [
            "ALTER TABLE session_digests ADD COLUMN compacted_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE session_digests ADD COLUMN compacted_at_turn INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE session_digests ADD COLUMN is_compacted INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE session_chronicles ADD COLUMN turn_start INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE session_chronicles ADD COLUMN turn_end INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE session_chronicles ADD COLUMN created_turn INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE session_chronicles ADD COLUMN bullet_count INTEGER NOT NULL DEFAULT 15",
            "CREATE INDEX IF NOT EXISTS idx_digests_session_compacted ON session_digests(session_id, is_compacted)",
            "CREATE INDEX IF NOT EXISTS idx_chronicles_session_turn ON session_chronicles(session_id, turn_end)",
            "UPDATE sessions SET turn_count = MAX(0, turn_count - 1) WHERE turn_count > 0 AND history_json IS NOT NULL AND json_valid(history_json) AND json_extract(history_json, '$[0].type') = 'scene' AND turn_count = json_array_length(history_json)",
        ],
    ),
    (
        39,
        "add_campaign_spines_and_quest_dossiers_v39",
        [
            "ALTER TABLE quests ADD COLUMN engine TEXT DEFAULT ''",
            "ALTER TABLE quests ADD COLUMN dossier_stage TEXT DEFAULT 'legacy'",
            "ALTER TABLE inventory ADD COLUMN is_quest_locked INTEGER DEFAULT 0",
            "ALTER TABLE inventory ADD COLUMN linked_quest_id TEXT DEFAULT ''",
            """CREATE TABLE IF NOT EXISTS campaign_spines (
                id                      INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id              INTEGER NOT NULL,
                scenario                TEXT NOT NULL,
                mastermind_profile_json TEXT NOT NULL DEFAULT '{}',
                lieutenants_roster_json TEXT NOT NULL DEFAULT '[]',
                chapters_blueprint_json TEXT NOT NULL DEFAULT '{}',
                nemeses_json            TEXT NOT NULL DEFAULT '[]',
                climax_status           TEXT NOT NULL DEFAULT 'pending',
                epilogue_status         TEXT NOT NULL DEFAULT 'pending',
                state_events_json       TEXT NOT NULL DEFAULT '[]',
                created_at              REAL NOT NULL,
                updated_at              REAL NOT NULL,
                UNIQUE(session_id)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_campaign_spines_sess ON campaign_spines(session_id)",
            """CREATE TABLE IF NOT EXISTS quest_dossiers (
                id                       INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id               INTEGER NOT NULL,
                quest_id                 TEXT NOT NULL,
                engine                   TEXT NOT NULL,
                family_tier              TEXT NOT NULL,
                danger_tier              INTEGER NOT NULL DEFAULT 1,
                status_stage             TEXT NOT NULL DEFAULT 'pitch',
                compiled_at_turn         INTEGER NOT NULL DEFAULT 0,
                pitch_stub_json          TEXT NOT NULL DEFAULT '{}',
                cast_bindings_json       TEXT NOT NULL DEFAULT '{}',
                leads_graph_json         TEXT NOT NULL DEFAULT '[]',
                clue_graph_json          TEXT NOT NULL DEFAULT '[]',
                climax_spec_json         TEXT NOT NULL DEFAULT '{}',
                twist_spec_json          TEXT NOT NULL DEFAULT '{}',
                tangible_item_json       TEXT NOT NULL DEFAULT '{}',
                contract_economy_json    TEXT NOT NULL DEFAULT '{}',
                turn_in_rules_json       TEXT NOT NULL DEFAULT '{}',
                outcomes_matrix_json     TEXT NOT NULL DEFAULT '{}',
                alert_level              INTEGER NOT NULL DEFAULT 0,
                max_alert                INTEGER NOT NULL DEFAULT 4,
                rescue_shield_used       INTEGER NOT NULL DEFAULT 0,
                engaged_flag             INTEGER NOT NULL DEFAULT 0,
                burned_approaches_json   TEXT NOT NULL DEFAULT '{}',
                state_events_json        TEXT NOT NULL DEFAULT '[]',
                outcome_tier             TEXT NOT NULL DEFAULT '',
                created_at               REAL NOT NULL,
                updated_at               REAL NOT NULL,
                UNIQUE(session_id, quest_id)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_quest_dossiers_sess_qid ON quest_dossiers(session_id, quest_id)",
            "CREATE INDEX IF NOT EXISTS idx_quest_dossiers_sess_stage ON quest_dossiers(session_id, status_stage)",
            "CREATE INDEX IF NOT EXISTS idx_quests_session_status ON quests(session_id, status)",
        ],
    ),
    (
        40,
        "add_session_clues_turn_created_and_relational_indexes_v40",
        [
            "ALTER TABLE session_clues ADD COLUMN turn_created INTEGER DEFAULT 1",
            "CREATE INDEX IF NOT EXISTS idx_session_clues_sess_turn ON session_clues(session_id, turn_created)",
            "CREATE INDEX IF NOT EXISTS idx_inventory_user_linked_quest ON inventory(user_id, linked_quest_id)",
            "CREATE INDEX IF NOT EXISTS idx_world_events_session_linked_quest ON world_events(session_id, linked_quest_id)",
        ],
    ),
    (
        41,
        "ensure_memory_and_chronicle_tables_bootstrap_v41",
        [
            """CREATE TABLE IF NOT EXISTS session_digests (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id          INTEGER NOT NULL,
                turn_start          INTEGER NOT NULL,
                turn_end            INTEGER NOT NULL,
                summary_bullets_json TEXT NOT NULL DEFAULT '[]',
                entities_json       TEXT NOT NULL DEFAULT '[]',
                location_tag        TEXT NOT NULL DEFAULT '',
                quest_ids_json      TEXT NOT NULL DEFAULT '[]',
                compacted_count     INTEGER NOT NULL DEFAULT 0,
                compacted_at_turn   INTEGER NOT NULL DEFAULT 0,
                is_compacted        INTEGER NOT NULL DEFAULT 0,
                created_at          REAL NOT NULL
            )""",
            """CREATE VIRTUAL TABLE IF NOT EXISTS session_digests_fts USING fts5(
                session_id UNINDEXED,
                bullet_text UNINDEXED,
                search_tokens,
                tokenize='unicode61 remove_diacritics 2'
            )""",
            """CREATE TABLE IF NOT EXISTS session_chronicles (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id          INTEGER NOT NULL,
                chapter_number      INTEGER NOT NULL,
                act_title           TEXT NOT NULL,
                summary_narrative   TEXT NOT NULL,
                key_consequences_json TEXT DEFAULT '[]',
                turn_start          INTEGER NOT NULL DEFAULT 0,
                turn_end            INTEGER NOT NULL DEFAULT 0,
                created_turn        INTEGER NOT NULL DEFAULT 0,
                bullet_count        INTEGER NOT NULL DEFAULT 15,
                created_at          REAL NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS npc_memories (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id          INTEGER NOT NULL,
                npc_name            TEXT NOT NULL,
                turn_index          INTEGER NOT NULL,
                memory_fact         TEXT NOT NULL,
                sentiment_delta     INTEGER DEFAULT 0,
                importance          INTEGER DEFAULT 1,
                is_secret           INTEGER DEFAULT 0,
                emotional_tone      TEXT DEFAULT '',
                open_thread         TEXT DEFAULT '',
                created_at          REAL NOT NULL
            )""",
            "CREATE INDEX IF NOT EXISTS idx_digests_session ON session_digests(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_digests_session_turn ON session_digests(session_id, turn_end)",
            "CREATE INDEX IF NOT EXISTS idx_digests_session_compacted ON session_digests(session_id, is_compacted)",
            "CREATE INDEX IF NOT EXISTS idx_chronicles_session ON session_chronicles(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_chronicles_session_turn ON session_chronicles(session_id, turn_end)",
            "CREATE INDEX IF NOT EXISTS idx_npc_memories_session_npc ON npc_memories(session_id, npc_name)",
        ],
    ),
    (
        42,
        "add_characters_anomalous_3axis_v42",
        [
            "ALTER TABLE characters ADD COLUMN attribute TEXT DEFAULT NULL",
            "ALTER TABLE characters ADD COLUMN combat_archetype TEXT DEFAULT NULL",
            "ALTER TABLE characters ADD COLUMN ability_medium TEXT DEFAULT NULL",
        ],
    ),
    (
        43,
        "add_user_folklore_codex_v43",
        [
            """CREATE TABLE IF NOT EXISTS user_folklore_codex (
                user_id             INTEGER NOT NULL,
                codex_id            TEXT NOT NULL,
                unlock_stage        TEXT NOT NULL DEFAULT 'sighted',
                times_sighted       INTEGER NOT NULL DEFAULT 1,
                times_contained     INTEGER NOT NULL DEFAULT 0,
                first_discovered_at REAL,
                updated_at          REAL,
                PRIMARY KEY (user_id, codex_id)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_user_folklore_codex_uid ON user_folklore_codex(user_id)",
        ],
    ),
    (
        44,
        "add_factions_hq_node_id_v44",
        [
            "ALTER TABLE factions ADD COLUMN hq_node_id TEXT DEFAULT ''",
            "CREATE INDEX IF NOT EXISTS idx_factions_session_hq_node ON factions(session_id, hq_node_id)",
            "UPDATE session_locations SET sub_name = 'School Library & Study Stacks' WHERE sub_name = 'Quiet School Library & Study Stacks'",
            "UPDATE world_nodes SET name = 'School Library & Study Stacks' WHERE name = 'Quiet School Library & Study Stacks'",
        ],
    ),
    (
        45,
        "add_session_anomaly_records_and_quest_blueprint_v45",
        [
            """CREATE TABLE IF NOT EXISTS session_anomaly_records (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id          INTEGER NOT NULL,
                record_type         TEXT NOT NULL,
                entity_key          TEXT NOT NULL DEFAULT '',
                codex_id            TEXT NOT NULL DEFAULT '',
                stage               TEXT NOT NULL DEFAULT 'sighted',
                first_turn          INTEGER NOT NULL DEFAULT 0,
                turn_updated        INTEGER NOT NULL DEFAULT 0,
                payload_json        TEXT NOT NULL DEFAULT '{}',
                created_at          REAL NOT NULL,
                updated_at          REAL NOT NULL
            )""",
            """CREATE UNIQUE INDEX IF NOT EXISTS uq_session_anom_field_log
                ON session_anomaly_records(session_id, record_type, entity_key)
                WHERE record_type = 'field_log' AND entity_key != ''""",
            "CREATE INDEX IF NOT EXISTS idx_session_anom_sess_type ON session_anomaly_records(session_id, record_type)",
            "CREATE INDEX IF NOT EXISTS idx_session_anom_sess_turn ON session_anomaly_records(session_id, first_turn, turn_updated)",
            "ALTER TABLE quests ADD COLUMN anomaly_blueprint_json TEXT DEFAULT '{}'",
            "ALTER TABLE user_folklore_codex ADD COLUMN first_session_id INTEGER DEFAULT NULL",
            "ALTER TABLE user_folklore_codex ADD COLUMN first_turn INTEGER DEFAULT NULL",
        ],
    ),
]


SCHEMA_MIGRATIONS.append(
    (
        46,
        "add_actor_physical_turn_snapshots_v46",
        [
            """CREATE TABLE IF NOT EXISTS actor_physical_turn_snapshots (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id          INTEGER NOT NULL,
                turn_number         INTEGER NOT NULL,
                states_json         TEXT NOT NULL DEFAULT '[]',
                garments_json       TEXT NOT NULL DEFAULT '[]',
                updated_at          REAL NOT NULL,
                UNIQUE(session_id, turn_number)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_phys_turn_snap_sess_turn ON actor_physical_turn_snapshots(session_id, turn_number)",
        ],
    )
)

SCHEMA_MIGRATIONS.append(
    (
        47,
        "add_actor_physical_turn_snapshots_room_meta_v47",
        [
            "ALTER TABLE actor_physical_turn_snapshots ADD COLUMN room_meta_json TEXT NOT NULL DEFAULT '{}'",
        ],
    )
)


SCHEMA_MIGRATIONS.append(
    (
        48,
        "add_player_properties_v48",
        [
            """CREATE TABLE IF NOT EXISTS player_properties (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id          INTEGER NOT NULL,
                property_id         TEXT NOT NULL,
                facility_node_id    TEXT NOT NULL,
                zone_id             TEXT NOT NULL,
                tier                INTEGER NOT NULL DEFAULT 0,
                price_paid          INTEGER NOT NULL DEFAULT 0,
                is_primary          INTEGER NOT NULL DEFAULT 0,
                is_starter          INTEGER NOT NULL DEFAULT 0,
                spare_keys_json     TEXT NOT NULL DEFAULT '{}',
                purchased_turn      INTEGER NOT NULL DEFAULT 0,
                purchased_day       INTEGER NOT NULL DEFAULT 1,
                created_at          REAL NOT NULL,
                updated_at          REAL NOT NULL,
                UNIQUE(session_id, property_id)
            )""",
            "CREATE INDEX IF NOT EXISTS idx_player_properties_sess ON player_properties(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_player_properties_node ON player_properties(session_id, facility_node_id)",
            "CREATE INDEX IF NOT EXISTS idx_player_properties_primary ON player_properties(session_id, is_primary)",
        ],
    )
)


SCHEMA_MIGRATIONS.append(
    (
        49,
        "zone_split_eastern_sanctuary_and_hidden_villages_v49",
        [],
    )
)

from ..social_pacing import SOCIAL_V50_DDL_STATEMENTS as _SOCIAL_V50_DDL

SCHEMA_MIGRATIONS.append(
    (
        50,
        "dynamic_social_overhaul_v50",
        list(_SOCIAL_V50_DDL),
    )
)

SCHEMA_MIGRATIONS.append(
    (
        51,
        "main_quest_bounty_overhaul_v51",
        [
            "ALTER TABLE campaign_spines ADD COLUMN hidden_bible_json TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE campaign_spines ADD COLUMN ending_axes_json TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE campaign_spines ADD COLUMN chronicle_tapestry_json TEXT NOT NULL DEFAULT '{}'",
        ],
    )
)

from ..contracts import ENTITY_CONTRACTS_V52_DDL as _ENTITY_CONTRACTS_V52_DDL

SCHEMA_MIGRATIONS.append(
    (
        52,
        "entity_contracts_and_patron_compendium_v52",
        list(_ENTITY_CONTRACTS_V52_DDL),
    )
)

SCHEMA_MIGRATIONS.append(
    (
        53,
        "combat_evolution_phase3_v53",
        [
            "ALTER TABLE sessions ADD COLUMN combat_threat_ledger_json TEXT NOT NULL DEFAULT '{}'",
            "ALTER TABLE sessions ADD COLUMN combat_boss_telegraph_json TEXT NOT NULL DEFAULT '{}'",
        ],
    )
)

from ..roster import WORLD_ROSTER_V54_DDL as _WORLD_ROSTER_V54_DDL

SCHEMA_MIGRATIONS.append(
    (
        54,
        "world_roster_closed_world_v54",
        list(_WORLD_ROSTER_V54_DDL),
    )
)

from ..epistemic import EPISTEMIC_V55_DDL as _EPISTEMIC_V55_DDL

_LIVING_WORLD_V55_DDL: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_world_roster_sess_nodes ON world_roster(session_id, staff_status, home_node_id, workplace_node_id, hangout_node_id)",
)

SCHEMA_MIGRATIONS.append(
    (
        55,
        "epistemic_and_living_world_v55",
        list(_EPISTEMIC_V55_DDL) + list(_LIVING_WORLD_V55_DDL),
    )
)

_WARDROBE_V56_DDL = [
    "ALTER TABLE actor_physical_states ADD COLUMN active_outfit_preset TEXT DEFAULT ''",
    "ALTER TABLE actor_physical_states ADD COLUMN wardrobe_meta_json TEXT DEFAULT '{}'",
]

SCHEMA_MIGRATIONS.append(
    (
        56,
        "dynamic_npc_wardrobe_v56",
        list(_WARDROBE_V56_DDL),
    )
)

SCHEMA_MIGRATIONS.append(
    (
        57,
        "anomalous_locations_integrity_v57",
        [],
    )
)

_NARRATION_PACING_V58_DDL = [
    "ALTER TABLE user_settings ADD COLUMN narrative_pacing TEXT DEFAULT 'balanced'",
    "ALTER TABLE sessions ADD COLUMN narrative_pacing TEXT DEFAULT 'balanced'",
]

SCHEMA_MIGRATIONS.append(
    (
        58,
        "narrative_pacing_and_style_v58",
        list(_NARRATION_PACING_V58_DDL),
    )
)

SCHEMA_MIGRATIONS.append(
    (
        59,
        "combat_display_and_session_parity_v59",
        [
            "ALTER TABLE user_settings ADD COLUMN show_enemy_hp INTEGER DEFAULT 1",
            "ALTER TABLE user_settings ADD COLUMN show_enemy_intent INTEGER DEFAULT 1",
            "ALTER TABLE sessions ADD COLUMN show_enemy_hp INTEGER DEFAULT 1",
            "ALTER TABLE sessions ADD COLUMN show_enemy_intent INTEGER DEFAULT 1",
        ],
    )
)

SCHEMA_MIGRATIONS.append(
    (
        60,
        "outlaw_factions_10wing_and_safehouses_v60",
        [],
    )
)

SCHEMA_MIGRATIONS.append(
    (
        61,
        "player_properties_buyer_character_id_v61",
        [
            "ALTER TABLE player_properties ADD COLUMN buyer_character_id INTEGER",
        ],
    )
)

CURRENT_SCHEMA_VERSION: int = SCHEMA_MIGRATIONS[-1][0]


def run_schema_migrations(conn: sqlite3.Connection) -> list[int]:
    """Executes pending versioned schema migrations deterministically and records applied versions."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at REAL NOT NULL)"
    )
    applied_rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    applied_versions = {row["version"] if isinstance(row, sqlite3.Row) else row[0] for row in applied_rows}
    newly_applied: list[int] = []

    for version, name, statements in SCHEMA_MIGRATIONS:
        if version in applied_versions:
            continue
        for sql in statements:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError as e:
                msg = str(e).lower()
                if "duplicate column name" in msg:
                    pass
                elif version in (18, 19) and "no such table: phone_appointments" in msg:
                    pass
                else:
                    raise
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
            (version, name, time.time()),
        )
        newly_applied.append(version)

    if 25 in newly_applied:
        try:
            _migrate_contacts_intimacy_profiles(conn)
        except Exception as e:
            print(f"[migration 25] Warning: intimacy profile data migration encountered: {e}")

    if 26 in newly_applied:
        try:
            from mechanics.social.relationship_graph import migrate_legacy_relations
            migrate_legacy_relations(conn)
        except Exception as e:
            print(f"[migration 26] Warning: social graph migration encountered: {e}")

    if 27 in newly_applied:
        try:
            _migrate_phone_appointments_to_commitments(conn)
        except Exception as e:
            print(f"[migration 27] Warning: commitments backfill encountered: {e}")

    if 30 in newly_applied:
        try:
            _migrate_clean_cutover_v30(conn)
        except Exception as e:
            print(f"[migration 30] Warning: clean cutover v30 migration encountered: {e}")

    if 32 in newly_applied:
        try:
            _migrate_self_heal_main_area_and_roster_drift_v32(conn)
        except Exception as e:
            print(f"[migration 32] Warning: self-heal migration encountered: {e}")

    if 37 in newly_applied:
        try:
            fts_cols = {
                (r["name"] if isinstance(r, sqlite3.Row) else r[1])
                for r in conn.execute("PRAGMA table_info(session_digests_fts)").fetchall()
            }
            if "search_tokens" not in fts_cols:
                conn.execute("DROP TABLE IF EXISTS session_digests_fts")
                conn.execute(
                    """CREATE VIRTUAL TABLE IF NOT EXISTS session_digests_fts USING fts5(
                        session_id UNINDEXED,
                        bullet_text UNINDEXED,
                        search_tokens,
                        tokenize='unicode61 remove_diacritics 2'
                    )"""
                )
                from ..memory import rebuild_session_digests_fts
                rebuild_session_digests_fts(conn)
        except Exception as e:
            print(f"[migration 37] Warning: multilingual FTS5 migration encountered: {e}")

    if 39 in newly_applied:
        try:
            _backfill_campaign_spines_from_legacy_sessions(conn)
        except Exception as e:
            print(f"[migration 39] Warning: campaign spine legacy backfill encountered: {e}")

    if 45 in newly_applied:
        try:
            _backfill_session_anomaly_records_v45(conn)
        except Exception as e:
            print(f"[migration 45] Warning: session anomaly records backfill encountered: {e}")
    if 49 in newly_applied:
        try:
            _migrate_zone_split_and_hidden_villages_v49(conn)
        except Exception as e:
            print(f"[migration 49] Warning: zone split & hidden folklore villages backfill encountered: {e}")
    if 50 in newly_applied:
        try:
            _migrate_dynamic_social_overhaul_v50(conn)
        except Exception as e:
            print(f"[migration 50] Warning: dynamic social overhaul backfill encountered: {e}")
    if 51 in newly_applied:
        try:
            _migrate_main_quest_bounty_overhaul_v51(conn)
        except Exception as e:
            print(f"[migration 51] Warning: main quest & bounty overhaul backfill encountered: {e}")
    if 53 in newly_applied:
        try:
            _migrate_combat_evolution_v53(conn)
        except Exception as e:
            print(f"[migration 53] Warning: combat evolution phase 3 backfill encountered: {e}")
    if 55 in newly_applied:
        try:
            _ensure_living_world_indexes_v55(conn)
        except Exception as e:
            print(f"[migration 55] Warning: living world index creation encountered: {e}")
    if 57 in newly_applied:
        try:
            _migrate_anomalous_locations_integrity_v57(conn)
        except Exception as e:
            print(f"[migration 57] Warning: anomalous locations integrity backfill encountered: {e}")

    if 58 in newly_applied or 59 in newly_applied:
        try:
            _migrate_narrative_pacing_values_v58(conn)
        except Exception as e:
            print(f"[migration 58] Warning: narrative pacing backfill encountered: {e}")

    if 60 in newly_applied:
        try:
            _migrate_outlaw_factions_v60(conn)
        except Exception as e:
            print(f"[migration 60] Warning: outlaw factions 10-wing HQ & safehouses backfill encountered: {e}")

    try:
        _strip_legacy_session_fk_constraints(conn)
    except Exception as e:
        print(f"[schema] Warning: session FK cleanup encountered: {e}")

    return newly_applied

def _get_user_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row else 0

def _set_user_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(f"PRAGMA user_version = {int(version)}")

def _all_migrations_recorded(conn: sqlite3.Connection) -> bool:
    try:
        expected = {int(v) for v, _, _ in SCHEMA_MIGRATIONS}
        recorded = {
            int(row[0])
            for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
            if row and row[0] is not None
        }
        return expected.issubset(recorded)
    except (sqlite3.OperationalError, TypeError, ValueError):
        return False

def _exec_schema_with_legacy_fallback(conn: sqlite3.Connection) -> None:
    """Applies SCHEMA on pre-schema_migrations legacy DBs, deferring index creation until columns exist."""
    try:
        conn.executescript(SCHEMA)
        run_schema_migrations(conn)
    except sqlite3.OperationalError as e:
        if "no such column" not in str(e).lower():
            raise
        buf: list[str] = []
        post_stmts: list[str] = []
        for line in SCHEMA.splitlines():
            stripped = line.strip()
            if not buf and (not stripped or stripped.startswith("--")):
                continue
            buf.append(line)
            candidate = "\n".join(buf) + "\n"
            if sqlite3.complete_statement(candidate):
                stmt_sql = candidate.strip()
                buf = []
                if stmt_sql.upper().startswith(("CREATE TABLE", "CREATE VIRTUAL TABLE")):
                    conn.execute(stmt_sql)
                else:
                    post_stmts.append(stmt_sql)
        run_schema_migrations(conn)
        for p_sql in post_stmts:
            try:
                conn.execute(p_sql)
            except sqlite3.OperationalError as idx_err:
                if "no such column" not in str(idx_err).lower():
                    raise

def init_db(force: bool = False):
    with get_conn() as conn:
        # 1. Warm fast-path: user_version matches AND schema_migrations table is complete.
        #    Dual-check preserves compatibility with tests that DELETE rows from schema_migrations.
        if not force and _get_user_version(conn) == CURRENT_SCHEMA_VERSION and _all_migrations_recorded(conn):
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='session_locks'"
            ).fetchone() is None:
                conn.executescript(CREATE_SESSION_LOCKS_TABLE)
            return

        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(CREATE_SESSION_LOCKS_TABLE)

        has_sessions = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sessions'"
        ).fetchone() is not None

        if not force:
            # 2. Brand-new DB fast-path: canonical SCHEMA already includes all v60 tables/columns/indexes.
            if not has_sessions:
                conn.executescript(SCHEMA)
                now = time.time()
                conn.executemany(
                    "INSERT OR IGNORE INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    [(v, name, now) for v, name, _ in SCHEMA_MIGRATIONS],
                )
                _set_user_version(conn, CURRENT_SCHEMA_VERSION)
                return

            # 3. Existing legacy DB (user_version == 0, partial migrations, or deleted migration rows).
            has_migrations = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone() is not None
            if has_migrations and _get_user_version(conn) == CURRENT_SCHEMA_VERSION:
                try:
                    run_schema_migrations(conn)
                    if _all_migrations_recorded(conn):
                        _set_user_version(conn, CURRENT_SCHEMA_VERSION)
                    return
                except Exception:
                    if conn.in_transaction:
                        conn.rollback()
            _exec_schema_with_legacy_fallback(conn)

            if _all_migrations_recorded(conn):
                _set_user_version(conn, CURRENT_SCHEMA_VERSION)
            return

        if force:
            with _VERIFIED_TABLE_GROUPS_LOCK:
                _VERIFIED_TABLE_GROUPS.clear()
        _exec_schema_with_legacy_fallback(conn)
        if _all_migrations_recorded(conn):
            _set_user_version(conn, CURRENT_SCHEMA_VERSION)
