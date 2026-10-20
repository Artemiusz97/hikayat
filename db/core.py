from __future__ import annotations
from typing import Any, Optional, Union, Dict, List, Tuple
import db
"""
SQLite persistence layer.

Tables:
- characters      one row per player character (Discord user_id is the PK)
- inventory       items owned by a character
- user_settings   per-user preferences (verbosity, dialogue, image gen)
- sessions        an active/waiting/finished adventure (solo, turn-based
                   multiplayer, or synchronized multiplayer)
- session_members which users are in a given session, in join order
- lorebook        persistent people/places/factions per session, so the
                   narrator stops renaming things
"""
import asyncio
import json
import time
from contextlib import contextmanager
import re
import sqlite3
import contextvars

from config import DB_PATH
import character_data as cd

SCHEMA = """
CREATE TABLE IF NOT EXISTS characters (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL,
    is_active           INTEGER DEFAULT 1,
    name                TEXT NOT NULL,
    char_class          TEXT NOT NULL,
    class_description   TEXT DEFAULT '',
    gender              TEXT DEFAULT '',  -- profile/flavor only, zero mechanical effect (see character_data.GENDER_OPTIONS)
    scenario            TEXT DEFAULT 'fantasy',  -- scenario key from data/scenarios.json
    race                TEXT DEFAULT 'human',
    race_description    TEXT DEFAULT '',
    str_ INTEGER, per_ INTEGER, end_ INTEGER, cha INTEGER, int_ INTEGER, agi INTEGER, luk INTEGER,
    hp INTEGER, max_hp INTEGER, temp_hp INTEGER DEFAULT 0,
    mp INTEGER, max_mp INTEGER,
    level INTEGER DEFAULT 1,
    xp INTEGER DEFAULT 0,
    pending_stat_points INTEGER DEFAULT 0,  -- unallocated stat points, earned ONLY from leveling up (db.add_xp), saved here until spent via spend_stat_point
    gold INTEGER DEFAULT 10,
    status_effects      TEXT DEFAULT '[]',
    skill_progress      TEXT DEFAULT '{}',
    learned_spells      TEXT DEFAULT '[]',
    days_adventured     INTEGER DEFAULT 1,
    active_session_id   INTEGER,
    joined_faction_id   TEXT DEFAULT '',
    faction_rank        INTEGER DEFAULT 0,
    faction_title       TEXT DEFAULT '',
    appearance_json     TEXT DEFAULT '{}',
    created_at          REAL
);

CREATE TABLE IF NOT EXISTS inventory (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    character_id INTEGER DEFAULT NULL,
    name        TEXT NOT NULL,
    item_type   TEXT NOT NULL,
    equipped    INTEGER DEFAULT 0,
    effect      TEXT DEFAULT '',
    slot_cost   INTEGER DEFAULT 1,
    slot        TEXT DEFAULT NULL
);
-- 'slot' holds one of the 6 canonical equipment slots (see
-- character_data.EQUIPMENT_SLOTS: Weapon/Shield/Top/Bottom/Gloves/Shoes) that
-- this item currently occupies, or NULL if it isn't equipped into one. Only
-- meaningful when equipped=1. See db.equip_item/unequip_slot/get_equipment.

CREATE TABLE IF NOT EXISTS user_settings (
    user_id             INTEGER PRIMARY KEY,
    verbosity           TEXT DEFAULT 'vivid',   -- 'vivid' | 'normal' | 'concise'
    dialogue_mode       TEXT DEFAULT 'balanced',
    image_gen_enabled   INTEGER DEFAULT 0,
    image_model         TEXT,
    choices_style       TEXT DEFAULT 'dropdown',  -- 'dropdown' | 'embed' | 'buttons'
    combat_ui_style     TEXT DEFAULT 'battle_deck', -- 'battle_deck' | 'multi_dropdown'
    result_display      TEXT DEFAULT 'detailed', -- 'detailed' | 'compact'
    show_percentages    INTEGER DEFAULT 1,       -- 1 = show raw %, 0 = hide raw %
    stream_narrative    INTEGER DEFAULT 1,       -- 1 = stream real-time, 0 = batch
    debug_stat_mode     TEXT DEFAULT 'off',  -- 'off' | 'max' | 'min'
    debug_check_mode    TEXT DEFAULT 'off',  -- 'off' | 'always_success' | 'always_fail' | 'always_crit_success' | 'always_crit_fail'
    debug_reveal_all_info INTEGER DEFAULT 0, -- 0 | 1 (reveal all predetermined info & history)
    language            TEXT DEFAULT 'en',
    ui_language         TEXT DEFAULT 'en',
    narration_language  TEXT DEFAULT 'en'
);

CREATE TABLE IF NOT EXISTS discord_users (
    user_id             INTEGER PRIMARY KEY,
    username            TEXT DEFAULT '',
    display_name        TEXT DEFAULT '',
    updated_at          REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    mode                TEXT NOT NULL,            -- 'solo' | 'turn' | 'sync'
    capacity            INTEGER NOT NULL,
    status              TEXT NOT NULL DEFAULT 'waiting',  -- waiting | active | finished
    turn_order          TEXT DEFAULT '[]',        -- JSON list of user_ids
    current_turn_index  INTEGER DEFAULT 0,
    scene_title         TEXT,
    narrative           TEXT,
    choices_json        TEXT DEFAULT '[]',
    history_json        TEXT DEFAULT '[]',
    pending_picks_json  TEXT DEFAULT '{}',        -- sync mode only: user_id -> pick
    current_location    TEXT DEFAULT '',
    current_node_id     TEXT DEFAULT '',
    focal_point         TEXT DEFAULT '',
    current_day         INTEGER DEFAULT 1,
    current_minute      INTEGER DEFAULT 480,      -- minutes from 00:00 (default 08:00 AM = 480)
    consecutive_days_awake INTEGER DEFAULT 0,     -- tracks nights stayed up past 05:00 AM without sleep
    current_chapter     INTEGER DEFAULT 1,
    campaign_end_goals_json TEXT DEFAULT '[]',
    nearby_enemies_json TEXT DEFAULT '[]',
    current_npcs_json   TEXT DEFAULT '[]',   -- NPCs (non-hostile people) currently present in the scene, same shape/lifecycle as nearby_enemies_json -- refreshed every scene, not cumulative
    party_npcs_json     TEXT DEFAULT '[]',
    party_recruit_cooldowns_json TEXT DEFAULT '{}',
    confession_cooldowns_json TEXT DEFAULT '{}',
    verbosity           TEXT DEFAULT 'vivid',
    dialogue_mode       TEXT DEFAULT 'balanced',
    image_gen_enabled   INTEGER DEFAULT 0,
    choices_style       TEXT DEFAULT 'dropdown',   -- 'dropdown' | 'embed' | 'buttons'
    combat_ui_style     TEXT DEFAULT 'battle_deck', -- 'battle_deck' | 'multi_dropdown'
    result_display      TEXT DEFAULT 'detailed',  -- 'detailed' | 'compact' -- fixed for the session's lifetime
    merchant_json       TEXT DEFAULT '{}',   -- current merchant encounter/shop state (see db.save_merchant_state); '{}' = no merchant involvement right now
    scenario            TEXT DEFAULT 'fantasy',  -- scenario key from data/scenarios.json (see scenario_data.py)
    physical_state_json TEXT DEFAULT '{}',   -- internal micro-spatial, posture, clothing, and prop state
    dialogue_partner    TEXT DEFAULT NULL,   -- name of NPC the player is currently actively talking to (or NULL if in open hub)
    phone_social_state_json TEXT DEFAULT '{}',
    channel_id          INTEGER,
    host_user_id        INTEGER,
    created_at          REAL,
    updated_at          REAL,
    chapter_digest_json TEXT DEFAULT '[]',   -- JSON list of past-arc digest bullet strings (Tier 2 Memory)
    extra_json          TEXT DEFAULT '{}',   -- flexible extension dict (e.g. pending_promotion)
    faction_reinforcements_used INTEGER DEFAULT 0,
    show_percentages    INTEGER DEFAULT 1,
    last_turn_snapshot_json TEXT DEFAULT '{}',
    language            TEXT DEFAULT 'en',
    narration_language  TEXT DEFAULT 'en',
    temporary_companions_json TEXT DEFAULT '[]',
    scene_image_url     TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS session_members (
    session_id  INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    joined_at   REAL,
    PRIMARY KEY (session_id, user_id)
);

CREATE TABLE IF NOT EXISTS lorebook (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL,
    entity_type     TEXT NOT NULL,   -- person | place | faction
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    disposition     TEXT DEFAULT 'neutral',  -- friendly | neutral | hostile | unknown
    faction         TEXT DEFAULT '',
    traits          TEXT DEFAULT '[]',
    motivation      TEXT DEFAULT '',
    mannerisms      TEXT DEFAULT '',
    gender          TEXT DEFAULT '',
    race            TEXT DEFAULT 'human',
    appearance_json TEXT DEFAULT '{}',
    status          TEXT DEFAULT 'active',   -- active | deceased | captured | ruined
    updated_at      REAL,
    embedding_json  TEXT DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS quests (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    quest_id            TEXT NOT NULL,
    quest_type          TEXT DEFAULT 'Main Quest',
    title               TEXT NOT NULL,
    objective           TEXT NOT NULL,
    sub_objectives_json TEXT DEFAULT '[]',
    progress            TEXT DEFAULT '',
    current_clues       TEXT DEFAULT '',
    status              TEXT DEFAULT 'Active',  -- Available | Active | Completed | Failed
    reward_xp           INTEGER DEFAULT 100,
    reward_gold         INTEGER DEFAULT 25,
    reward_stat_points  INTEGER DEFAULT 0,
    reward_item         TEXT DEFAULT '',
    is_story_quest      INTEGER DEFAULT 0,
    clues_required      INTEGER DEFAULT 3,
    reward_claimed      INTEGER DEFAULT 0,
    quest_notes         TEXT DEFAULT '',
    blueprint_id        TEXT DEFAULT '',
    client_npc          TEXT DEFAULT '',
    client_location     TEXT DEFAULT '',
    required_item       TEXT DEFAULT '',
    required_item_count INTEGER DEFAULT 1,
    strikes             INTEGER DEFAULT 0,
    max_strikes         INTEGER DEFAULT 2,
    deadline_day        INTEGER DEFAULT NULL,
    deadline_minute     INTEGER DEFAULT NULL,
    resolution_approach TEXT DEFAULT '',
    created_at          REAL,
    updated_at          REAL,
    UNIQUE(session_id, quest_id)
);

CREATE TABLE IF NOT EXISTS contacts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    character_id        INTEGER DEFAULT 0,
    npc_id              TEXT NOT NULL,
    name                TEXT NOT NULL,
    basic_info_json     TEXT DEFAULT '{}',
    relationship_score  INTEGER DEFAULT 0,
    track               TEXT DEFAULT 'platonic',
    unlocked_traits_json TEXT DEFAULT '[]',
    preferences_json     TEXT DEFAULT '[]',
    race                TEXT DEFAULT 'human',
    gender              TEXT DEFAULT '',
    appearance_json     TEXT DEFAULT '{}',
    relations_json      TEXT DEFAULT '{}',
    rel_history_json    TEXT DEFAULT '[]',
    intimate_memories_json TEXT DEFAULT '[]',
    intimate_profile_json TEXT DEFAULT '{}',
    emotional_tone      TEXT DEFAULT '',
    open_thread         TEXT DEFAULT '',
    household_id        INTEGER REFERENCES households(id),
    created_at          REAL,
    updated_at          REAL,
    UNIQUE(session_id, character_id, npc_id)
);

CREATE TABLE IF NOT EXISTS households (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    household_key       TEXT NOT NULL,
    surname             TEXT NOT NULL,
    father_json         TEXT NOT NULL DEFAULT '{}',
    mother_json         TEXT NOT NULL DEFAULT '{}',
    narrative_siblings_json TEXT NOT NULL DEFAULT '[]',
    residence_location  TEXT DEFAULT '',
    created_at          REAL,
    updated_at          REAL,
    UNIQUE(session_id, household_key)
);

CREATE TABLE IF NOT EXISTS intimate_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    character_id        TEXT NOT NULL,
    partner_id          TEXT,
    partner_name        TEXT NOT NULL,
    partner_role        TEXT,
    turn_number         INTEGER DEFAULT 0,
    event_origin        TEXT DEFAULT 'past_history',
    act_type            TEXT NOT NULL,
    direction           TEXT NOT NULL,
    is_physical         BOOLEAN DEFAULT 1,
    count               INTEGER DEFAULT 1,
    climax_count        INTEGER DEFAULT 0,
    is_secret_affair    BOOLEAN DEFAULT 0,
    narrative_summary   TEXT,
    created_at          REAL
);

CREATE INDEX IF NOT EXISTS idx_intimate_events_char ON intimate_events(session_id, character_id, is_physical);
CREATE INDEX IF NOT EXISTS idx_intimate_events_session_turn ON intimate_events(session_id, turn_number);

CREATE TABLE IF NOT EXISTS social_persons (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    person_key          TEXT NOT NULL,
    display_name        TEXT NOT NULL,
    gender              TEXT DEFAULT '',
    role                TEXT DEFAULT '',
    origin              TEXT DEFAULT 'procedural',
    contact_npc_id      TEXT DEFAULT NULL,
    created_at          REAL,
    updated_at          REAL,
    UNIQUE(session_id, person_key)
);

CREATE INDEX IF NOT EXISTS idx_social_persons_contact ON social_persons(session_id, contact_npc_id);

CREATE TABLE IF NOT EXISTS social_ties (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    person_a_key        TEXT NOT NULL,
    person_b_key        TEXT NOT NULL,
    tie_type            TEXT NOT NULL,
    is_directed         INTEGER DEFAULT 0,
    status              TEXT DEFAULT 'active',
    closeness           INTEGER DEFAULT 50,
    visibility          TEXT DEFAULT 'public',
    origin              TEXT DEFAULT 'procedural',
    started_turn        INTEGER DEFAULT 0,
    ended_turn          INTEGER DEFAULT NULL,
    end_reason          TEXT DEFAULT '',
    metadata_json       TEXT DEFAULT '{}',
    created_at          REAL,
    updated_at          REAL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_social_ties_active
    ON social_ties(session_id, person_a_key, person_b_key, tie_type) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_social_ties_a ON social_ties(session_id, person_a_key, status);
CREATE INDEX IF NOT EXISTS idx_social_ties_b ON social_ties(session_id, person_b_key, status);

CREATE TABLE IF NOT EXISTS factions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    faction_id          TEXT NOT NULL,
    name                TEXT NOT NULL,
    reputation_score    INTEGER DEFAULT 0,
    perks_json          TEXT DEFAULT '[]',
    notes               TEXT DEFAULT '',
    category            TEXT DEFAULT 'guild',   -- guild | club | delinquents | corpo | syndicate | order
    hq_location_id      TEXT DEFAULT '',        -- matches session_locations.location_id
    hierarchy_template  TEXT DEFAULT 'guild',   -- key into FACTION_HIERARCHIES in mechanics/factions.py
    leadership_roster_json  TEXT DEFAULT '[]',      -- [{rank, title, name, is_player}]
    rival_faction_ids_json  TEXT DEFAULT '[]',      -- list of faction_id strings
    allied_faction_ids_json TEXT DEFAULT '[]',      -- list of allied faction_id strings
    created_at          REAL,
    updated_at          REAL,
    UNIQUE(session_id, faction_id)
);


CREATE TABLE IF NOT EXISTS session_locations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    location_id         TEXT NOT NULL,
    zone_name           TEXT NOT NULL,
    primary_name        TEXT NOT NULL,
    sub_name            TEXT NOT NULL,
    atmosphere          TEXT DEFAULT '',
    is_dynamic          INTEGER DEFAULT 0,
    created_at          REAL,
    UNIQUE(session_id, location_id)
);

CREATE TABLE IF NOT EXISTS world_nodes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    node_id             TEXT NOT NULL,
    parent_id           TEXT DEFAULT NULL,
    name                TEXT NOT NULL,
    node_type           TEXT NOT NULL,               -- 'ZONE' | 'FACILITY' | 'ROOM'
    category            TEXT NOT NULL DEFAULT 'academic',
    privacy_level       TEXT NOT NULL DEFAULT 'public',
    is_enclosed         INTEGER DEFAULT 1,
    is_transit_hub      INTEGER DEFAULT 0,
    access_tier         TEXT DEFAULT 'open',         -- 'open' | 'restricted' | 'curfew_restricted'
    curfew_start_min    INTEGER DEFAULT NULL,
    curfew_end_min      INTEGER DEFAULT NULL,
    atmosphere          TEXT DEFAULT '',
    is_dynamic          INTEGER DEFAULT 0,
    created_at          REAL,
    UNIQUE(session_id, node_id)
);

CREATE INDEX IF NOT EXISTS idx_world_nodes_session ON world_nodes(session_id, node_id);
CREATE INDEX IF NOT EXISTS idx_world_nodes_parent ON world_nodes(session_id, parent_id);

CREATE TABLE IF NOT EXISTS world_edges (
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
);

CREATE INDEX IF NOT EXISTS idx_world_edges_from ON world_edges(session_id, from_node_id);
CREATE INDEX IF NOT EXISTS idx_world_edges_to ON world_edges(session_id, to_node_id);

CREATE TABLE IF NOT EXISTS quest_waypoints (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    quest_id            TEXT NOT NULL,
    sub_obj_id          INTEGER DEFAULT NULL,
    stage_index         INTEGER NOT NULL,
    stage_label         TEXT NOT NULL,
    target_location     TEXT NOT NULL,
    target_node_id      TEXT DEFAULT '',
    target_npc          TEXT DEFAULT '',
    completion_trigger  TEXT DEFAULT 'arrival',
    resource_target     INTEGER DEFAULT 0,
    resource_collected  INTEGER DEFAULT 0,
    status              TEXT DEFAULT 'locked',
    follow_npc_schedule    INTEGER DEFAULT 0,
    required_item          TEXT DEFAULT '',
    valid_time_phases_json TEXT DEFAULT '[]',
    approaches_json        TEXT DEFAULT '[]',
    created_at          REAL,
    updated_at          REAL,
    UNIQUE(session_id, quest_id, stage_index, sub_obj_id)
);

CREATE TABLE IF NOT EXISTS phone_messages (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    contact_npc_id      TEXT NOT NULL,
    sender              TEXT NOT NULL,   -- 'player' or 'npc'
    message             TEXT NOT NULL,
    intent              TEXT DEFAULT 'chat',
    timestamp           REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS session_clues (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id              INTEGER NOT NULL,
    quest_id                TEXT DEFAULT '',
    chapter                 INTEGER DEFAULT 1,
    title                   TEXT NOT NULL,
    lead_text               TEXT NOT NULL,
    category                TEXT DEFAULT 'physical',
    source_location         TEXT DEFAULT '',
    linked_npc              TEXT DEFAULT '',
    is_verified             INTEGER DEFAULT 0,
    deduction_parents_json  TEXT DEFAULT '[]',
    created_at              REAL,
    updated_at              REAL
);

CREATE INDEX IF NOT EXISTS idx_session_clues_sess ON session_clues(session_id);
CREATE INDEX IF NOT EXISTS idx_session_clues_npc ON session_clues(session_id, linked_npc);

CREATE TABLE IF NOT EXISTS phone_gossip_feed (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    author_name         TEXT NOT NULL,
    author_handle       TEXT NOT NULL,
    content             TEXT NOT NULL,
    tag                 TEXT DEFAULT '',
    clue_hook           TEXT DEFAULT '',
    time_ago            TEXT DEFAULT 'Just now',
    created_at          REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS phone_appointments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    npc_id              TEXT NOT NULL,
    npc_name            TEXT NOT NULL,
    rendezvous_location TEXT NOT NULL,
    target_node_id      TEXT DEFAULT '',
    topic               TEXT DEFAULT '',
    is_confidential     INTEGER DEFAULT 0,
    origin              TEXT DEFAULT 'phone',             -- 'phone' | 'dialogue'
    created_minute      INTEGER DEFAULT 0,
    expiry_minute       INTEGER DEFAULT 0,
    reminder_sent       INTEGER DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'arrived' | 'completed' | 'stood_up' | 'cancelled'
    created_at          REAL NOT NULL,
    UNIQUE(session_id, npc_id)
);

CREATE TABLE IF NOT EXISTS phone_daily_interactions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    npc_id              TEXT NOT NULL,
    current_day         INTEGER NOT NULL,
    intent              TEXT NOT NULL,         -- 'flirt', 'meetup', 'photo', 'spicy', 'rumor'
    attempt_count       INTEGER DEFAULT 0,
    success_count       INTEGER DEFAULT 0,
    over_limit_count    INTEGER DEFAULT 0,     -- tracks repeated badgering after limit reached
    last_outcome        TEXT DEFAULT '',       -- 'success', 'fail', 'crit_success', 'crit_fail', 'refused'
    metadata_json       TEXT DEFAULT '{}',     -- tracks attempts history, relocations_used
    updated_at          REAL NOT NULL,
    UNIQUE(session_id, npc_id, current_day, intent)
);
CREATE INDEX IF NOT EXISTS idx_phone_daily_lookup ON phone_daily_interactions(session_id, npc_id, current_day);

CREATE TABLE IF NOT EXISTS school_directory (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    npc_id              TEXT NOT NULL,
    name                TEXT NOT NULL,
    gender              TEXT DEFAULT '',         -- 'male', 'female', etc.
    race                TEXT DEFAULT '',
    role                TEXT NOT NULL,
    grade               TEXT NOT NULL,           -- 'Faculty', 'Senior', 'Junior', 'Sophomore', 'Freshman'
    club                TEXT DEFAULT '',         -- 'Athletic Directorate', 'Student Council', etc.
    clique              TEXT DEFAULT '',         -- 'Jock', 'Class Rep', 'Delinquent', 'Artist', etc.
    primary_facility    TEXT NOT NULL,           -- e.g. 'Science Wing ➔ Chemistry Lab'
    secondary_facility  TEXT DEFAULT '',         -- e.g. 'Central Courtyard ➔ Fountain Benches'
    sibling_name        TEXT DEFAULT '',         -- Name of related student
    personality_summary TEXT DEFAULT '',
    is_hydrated         INTEGER DEFAULT 0,       -- 1 when upgraded to active contact
    created_at          REAL NOT NULL,
    UNIQUE(session_id, npc_id)
);

CREATE TABLE IF NOT EXISTS procedural_spells (
    id          TEXT PRIMARY KEY,
    spell_data  TEXT NOT NULL,
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS adventure_saves (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL,
    character_id        INTEGER NOT NULL,
    slot_name           TEXT NOT NULL,
    scenario            TEXT NOT NULL,
    scene_title         TEXT,
    narrative_snippet   TEXT,
    current_location    TEXT,
    saved_at            REAL NOT NULL,
    snapshot_data       TEXT NOT NULL,
    UNIQUE(character_id, slot_name)
);

CREATE TABLE IF NOT EXISTS commitments_ledger (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    commitment_key      TEXT NOT NULL DEFAULT '',
    commitment_type     TEXT NOT NULL,    -- 'rendezvous' | 'promise'
    source_entity       TEXT NOT NULL,    -- player person_key or npc_id
    target_entity       TEXT NOT NULL,    -- primary counterparty (or 'group')
    participants_json   TEXT NOT NULL DEFAULT '[]', -- list of {person_key, npc_id, name, role, status}
    target_location     TEXT DEFAULT '',  -- room/location name
    target_node_id      TEXT DEFAULT '',  -- world graph node_id
    scheduled_day       INTEGER DEFAULT 1,
    start_minute        INTEGER DEFAULT 0,
    end_minute          INTEGER DEFAULT 1439,
    deadline_turn       INTEGER DEFAULT NULL,
    status              TEXT DEFAULT 'active', -- 'active' | 'pending' | 'arrived' | 'in_progress' | 'fulfilled' | 'flaked' | 'broken' | 'cancelled' | 'voided' | 'abandoned'
    origin              TEXT DEFAULT 'in_person', -- 'phone_dm' | 'in_person' | 'quest' | 'scripted'
    is_confidential     INTEGER DEFAULT 0,
    title               TEXT DEFAULT '',
    description         TEXT NOT NULL,   -- plain-text summary of what was committed
    metadata_json       TEXT DEFAULT '{}',
    turn_created        INTEGER NOT NULL DEFAULT 0,
    created_at          REAL DEFAULT 0,
    updated_at          REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS actor_physical_states (
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
    UNIQUE(session_id, canonical_key),
    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS actor_garments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    actor_key           TEXT NOT NULL,
    slot                TEXT NOT NULL,
    state               TEXT DEFAULT 'worn',
    item_name           TEXT DEFAULT '',
    layer_depth         INTEGER DEFAULT 2,
    updated_at          REAL NOT NULL,
    UNIQUE(session_id, actor_key, slot),
    FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS session_digests (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    turn_start          INTEGER NOT NULL,
    turn_end            INTEGER NOT NULL,
    summary_bullets_json TEXT NOT NULL DEFAULT '[]',  -- JSON list of 2-3 narrative fact strings
    created_at          REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lorebook_session ON lorebook(session_id);
CREATE INDEX IF NOT EXISTS idx_characters_user_active ON characters(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_session_members_user ON session_members(user_id);
CREATE INDEX IF NOT EXISTS idx_contacts_session ON contacts(session_id, npc_id);
CREATE INDEX IF NOT EXISTS idx_contacts_char ON contacts(character_id);
CREATE INDEX IF NOT EXISTS idx_inventory_char_user ON inventory(character_id, user_id);
CREATE INDEX IF NOT EXISTS idx_phone_messages_session ON phone_messages(session_id, contact_npc_id);
CREATE INDEX IF NOT EXISTS idx_phone_appointments_sess ON phone_appointments(session_id);
CREATE INDEX IF NOT EXISTS idx_phone_gossip_sess ON phone_gossip_feed(session_id);
CREATE INDEX IF NOT EXISTS idx_saves_user_char ON adventure_saves(user_id, character_id);
CREATE INDEX IF NOT EXISTS idx_commitments_session ON commitments_ledger(session_id, status);
CREATE INDEX IF NOT EXISTS idx_commitments_time ON commitments_ledger(session_id, scheduled_day, start_minute, end_minute);
CREATE INDEX IF NOT EXISTS idx_commitments_node ON commitments_ledger(session_id, target_node_id, status);
CREATE INDEX IF NOT EXISTS idx_digests_session ON session_digests(session_id);
CREATE INDEX IF NOT EXISTS idx_actor_phys_lookup ON actor_physical_states(session_id, canonical_key);
CREATE INDEX IF NOT EXISTS idx_actor_garments_actor ON actor_garments(session_id, actor_key);

CREATE TABLE IF NOT EXISTS session_digest_vectors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    bullet_text TEXT,
    vector_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_digest_vectors_session ON session_digest_vectors(session_id);

CREATE VIRTUAL TABLE IF NOT EXISTS session_digests_fts USING fts5(
    session_id UNINDEXED,
    bullet_text,
    tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS session_chronicles (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    chapter_number      INTEGER NOT NULL,
    act_title           TEXT NOT NULL,
    summary_narrative   TEXT NOT NULL,
    key_consequences_json TEXT DEFAULT '[]',
    created_at          REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS npc_memories (
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
);

CREATE INDEX IF NOT EXISTS idx_chronicles_session ON session_chronicles(session_id);
CREATE INDEX IF NOT EXISTS idx_npc_memories_session_npc ON npc_memories(session_id, npc_name);
"""



import queue
import threading

_POOL: dict[str, queue.Queue] = {}
_POOL_LOCK = threading.Lock()
MAX_CONNECTIONS = 15

_uow_conn_var = contextvars.ContextVar("_uow_conn_var", default=None)

def close_all_connections():
    """Drains all connection pools. Vital for test teardown on Windows."""
    with _POOL_LOCK:
        for path, q in _POOL.items():
            while not q.empty():
                try:
                    conn = q.get_nowait()
                    conn.close()
                except queue.Empty:
                    break
        _POOL.clear()

def _create_new_connection(db_path: str):
    conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA cache_size = -64000")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA mmap_size = 268435456")
    return conn

@contextmanager
def UnitOfWork(db_path: str = None):
    """Context manager that begins a transaction and yields the connection."""
    if db_path is None:
        db_path = __import__('db').DB_PATH

    # If we are already in a transaction, just yield the existing connection
    if _uow_conn_var.get() is not None:
        yield _uow_conn_var.get()
        return

    with _POOL_LOCK:
        if db_path not in _POOL:
            _POOL[db_path] = queue.Queue(maxsize=MAX_CONNECTIONS)
        pool = _POOL[db_path]

    try:
        conn = pool.get_nowait()
    except queue.Empty:
        conn = _create_new_connection(db_path)

    # Begin the transaction explicitly
    conn.execute("BEGIN IMMEDIATE")
    
    token = _uow_conn_var.set(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _uow_conn_var.reset(token)
        try:
            pool.put_nowait(conn)
        except queue.Full:
            conn.close()

@contextmanager
def get_conn():
    """Returns the UoW connection if inside one, else creates an auto-commit one."""
    existing_conn = _uow_conn_var.get()
    if existing_conn is not None:
        yield existing_conn
    else:
        db_path = __import__('db').DB_PATH
        
        with _POOL_LOCK:
            if db_path not in _POOL:
                _POOL[db_path] = queue.Queue(maxsize=MAX_CONNECTIONS)
            pool = _POOL[db_path]
            
        try:
            conn = pool.get_nowait()
        except queue.Empty:
            conn = _create_new_connection(db_path)
            
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            try:
                pool.put_nowait(conn)
            except queue.Full:
                conn.close()

async def adb(fn, /, *args, **kwargs):
    """Async wrapper for any synchronous ``db.*`` function.

    Offloads the blocking SQLite call to the default thread-pool executor so
    the asyncio event loop (and Discord gateway heartbeat) are never stalled.

    Usage inside an ``async def`` Discord handler::

        char = await adb(db.get_character, user_id)
        session = await adb(db.get_session, session_id)
    """
    return await asyncio.to_thread(fn, *args, **kwargs)

def _delete_session_records(conn, session_id: int):
    """Deletes a session and all its related child records on an existing connection."""
    for tbl in SESSION_CHILD_TABLES:
        conn.execute(f"DELETE FROM {tbl} WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))

CREATE_SESSION_LOCKS_TABLE = '''
CREATE TABLE IF NOT EXISTS session_locks (
    lock_key TEXT PRIMARY KEY,
    locked_at REAL,
    locked_by TEXT
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at REAL NOT NULL
);
'''

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
                UNIQUE(session_id, canonical_key),
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
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
                UNIQUE(session_id, actor_key, slot),
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )""",
            "CREATE INDEX IF NOT EXISTS idx_actor_garments_actor ON actor_garments(session_id, actor_key)",
        ],
    ),
]


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
                if "duplicate column name" not in str(e).lower():
                    raise
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
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

    # Ensure backfill is run if social_ties is empty but contacts exist
    try:
        ties_cnt = conn.execute("SELECT COUNT(*) FROM social_ties").fetchone()[0]
        contacts_cnt = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        if ties_cnt == 0 and contacts_cnt > 0:
            from mechanics.social.relationship_graph import migrate_legacy_relations
            migrate_legacy_relations(conn)
    except Exception as e:
        pass

    # Ensure commitments backfill is run if appointments exist but no rendezvous in ledger
    try:
        appts_cnt = conn.execute("SELECT COUNT(*) FROM phone_appointments").fetchone()[0]
        rendezvous_cnt = conn.execute("SELECT COUNT(*) FROM commitments_ledger WHERE commitment_type='rendezvous'").fetchone()[0]
        if appts_cnt > 0 and rendezvous_cnt == 0:
            _migrate_phone_appointments_to_commitments(conn)
    except Exception as e:
        pass

    return newly_applied


def _migrate_phone_appointments_to_commitments(conn: sqlite3.Connection) -> int:
    """Migrates existing phone_appointments rows into the unified commitments_ledger table."""
    import json
    import time
    cursor = conn.cursor()
    tbl = cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='phone_appointments'").fetchone()
    if not tbl:
        return 0
    rows = cursor.execute("SELECT * FROM phone_appointments").fetchall()
    migrated = 0
    now = time.time()
    for row in rows:
        d = dict(row)
        sess_id = d.get("session_id")
        npc_id = d.get("npc_id", "")
        npc_name = d.get("npc_name", "") or npc_id
        loc = d.get("rendezvous_location", "")
        node_id = d.get("target_node_id", "") or ""
        created_min = d.get("created_minute", 0) or 0
        expiry_min = d.get("expiry_minute", 0) or (created_min + 45 if created_min else 1439)
        created_at = d.get("created_at") or now
        status = d.get("status", "pending")
        if status == "stood_up":
            status = "flaked"

        c_key = f"rendezvous_{sess_id}_{npc_id}_{int(created_at)}"
        existing = cursor.execute(
            "SELECT id FROM commitments_ledger WHERE session_id=? AND commitment_key=?",
            (sess_id, c_key)
        ).fetchone()
        if existing:
            continue

        participants = [
            {"person_key": "player", "role": "organizer", "status": "active"},
            {"person_key": npc_id, "npc_id": npc_id, "name": npc_name, "role": "participant", "status": status}
        ]
        meta = {
            "reminder_sent": bool(d.get("reminder_sent", 0)),
            "legacy_phone_appt_id": d.get("id"),
        }
        day = (created_min // 1440) + 1 if created_min > 0 else 1
        start_m = created_min % 1440 if created_min > 0 else 0
        end_m = expiry_min % 1440 if expiry_min > 0 else 1439
        title = f"Meetup with {npc_name}"
        desc = d.get("topic") or f"Rendezvous at {loc}"

        cursor.execute(
            """INSERT INTO commitments_ledger (
                session_id, commitment_key, commitment_type, source_entity, target_entity,
                participants_json, target_location, target_node_id, scheduled_day,
                start_minute, end_minute, deadline_turn, status, origin,
                is_confidential, title, description, metadata_json, turn_created,
                created_at, updated_at
            ) VALUES (?, ?, 'rendezvous', 'player', ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, 0, ?, ?)""",
            (
                sess_id, c_key, npc_id, json.dumps(participants), loc, node_id,
                day, start_m, end_m, status, d.get("origin") or "phone_dm",
                d.get("is_confidential", 0), title, desc, json.dumps(meta),
                created_at, created_at
            )
        )
        migrated += 1
    return migrated


def _migrate_contacts_intimacy_profiles(conn: sqlite3.Connection) -> int:
    """
    Migrates existing contacts:
    1. Extracts intimacy attributes from appearance_json into intimate_profile_json.
    2. Backfills pre-game backstory rows into intimate_events table.
    3. Backfills gameplay milestone rows into intimate_events table from intimate_memories_json.
    4. Computes deterministic tracks and caches them in intimate_profile_json['tracks'].
    5. Cleans up appearance_json so it only contains physical traits.
    """
    import json
    import hashlib
    from mechanics.social.persona.intimacy.ledger import (
        record_intimate_event,
        compute_intimate_tracks_from_ledger,
    )
    from mechanics.social.persona.intimacy.generation import (
        generate_past_intimate_history,
        persist_generated_past_history
    )
    from mechanics.social.persona.intimacy.formatting import is_romantic_milestone_str

    rows = conn.execute("SELECT * FROM contacts").fetchall()
    migrated_count = 0

    for r in rows:
        d = dict(r)
        sess_id = d["session_id"]
        char_ref = str(d.get("npc_id") or d["id"])
        c_name = d.get("name") or "Unknown"
        c_gender = d.get("gender") or ""
        c_race = d.get("race") or "human"

        try:
            app = json.loads(d.get("appearance_json") or "{}")
        except Exception:
            app = {}

        try:
            prof = json.loads(d.get("intimate_profile_json") or "{}")
        except Exception:
            prof = {}

        try:
            mems = json.loads(d.get("intimate_memories_json") or "[]")
        except Exception:
            mems = []

        intimate_keys = (
            "sensitive_spots", "turn_ons", "turn_offs", "fetishes", "desires_and_kinks",
            "combined_turn_ons", "act_likes", "act_dislikes", "favorite_acts", "disliked_acts",
            "intimate_demeanor", "intimate_dynamic", "erotic_openness", "undergarments",
            "bra", "underwear", "predetermined_intercourse", "had_first_time_with_player",
            "intercourse_experience", "oral_experience", "manual_experience", "anal_experience",
            "intimate_revealed", "intercourse_revealed", "oral_revealed", "manual_revealed",
            "anal_revealed", "sensitive_spots_revealed", "turn_ons_revealed", "turn_offs_revealed",
            "fetishes_revealed", "act_preferences_revealed", "underwear_revealed",
            "demeanor_revealed", "dynamic_revealed", "openness_revealed", "all_revealed"
        )

        # Read experience & openness before modifying app
        cur_i = prof.get("intercourse_experience") or app.get("intercourse_experience") or "virgin"
        cur_o = prof.get("oral_experience") or app.get("oral_experience") or "inexperienced"
        cur_m = prof.get("manual_experience") or app.get("manual_experience") or "inexperienced"
        cur_a = prof.get("anal_experience") or app.get("anal_experience") or "inexperienced"
        openness = prof.get("erotic_openness") or app.get("erotic_openness") or "moderate"

        for k in intimate_keys:
            if k in app and k not in prof:
                prof[k] = app[k]

        disc_flags = prof.get("disclosure_flags", {})
        for k in intimate_keys:
            if k.endswith("_revealed"):
                disc_flags[k] = bool(prof.get(k, False))
        prof["disclosure_flags"] = disc_flags

        if "undergarments" not in prof or not isinstance(prof.get("undergarments"), dict):
            if prof.get("bra") or prof.get("underwear"):
                prof["undergarments"] = {
                    "bra": prof.get("bra", ""),
                    "underwear": prof.get("underwear", "")
                }

        # Gather any legacy past history memories
        past_memories = [m for m in mems if isinstance(m, str) and m.strip().startswith("Past History:")]
        if not past_memories and app.get("past_intimate_history"):
            past_memories.append(str(app.get("past_intimate_history")))
        if isinstance(app.get("past_intimate_entries"), list):
            for pe in app["past_intimate_entries"]:
                if pe and pe not in past_memories:
                    past_memories.append(str(pe))

        # Clean physical appearance dict
        for k in intimate_keys:
            app.pop(k, None)
        for k in ("intercourse_experience", "oral_experience", "manual_experience", "anal_experience",
                  "past_intimate_history", "past_intimate_entries", "intimate_memories"):
            app.pop(k, None)

        # Check existing events
        ev_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM intimate_events WHERE session_id = ? AND character_id = ?",
            (sess_id, char_ref)
        ).fetchone()
        has_events = ev_count and ev_count["cnt"] > 0

        if not has_events:
            events_created = 0
            if past_memories:
                from mechanics.social.persona.intimacy.ledger import parse_past_history_entry_to_events
                for pm in past_memories:
                    parsed_evs = parse_past_history_entry_to_events(pm, char_gender=c_gender)
                    for pev in parsed_evs:
                        record_intimate_event(
                            session_id=sess_id,
                            character_id=char_ref,
                            partner_name=pev.get("partner_name", "Past Partner"),
                            act_type=pev.get("act_type", "intercourse"),
                            direction=pev.get("direction", "mutual"),
                            partner_id=None,
                            partner_role=pev.get("partner_role", "Former Classmate"),
                            turn_number=0,
                            event_origin="past_history",
                            is_physical=bool(pev.get("is_physical", True)),
                            count=pev.get("count", 1),
                            climax_count=0,
                            is_secret_affair=bool(pev.get("is_secret_affair", False)),
                            narrative_summary=pm,
                            character_gender=c_gender,
                            conn=conn
                        )
                        events_created += 1

            seed_str = f"{c_name}_{c_race}_{sess_id}".encode("utf-8")
            h_val = int(hashlib.md5(seed_str).hexdigest(), 16)

            if events_created == 0 and (cur_i == "non_virgin" or cur_o != "inexperienced" or cur_m != "inexperienced" or cur_a != "inexperienced"):
                past_hist = generate_past_intimate_history(
                    hash_val=h_val,
                    race=c_race,
                    gender=c_gender,
                    openness=openness,
                    intercourse=cur_i,
                    oral=cur_o,
                    manual=cur_m,
                    anal=cur_a
                )
                if past_hist:
                    persist_generated_past_history(
                        session_id=sess_id,
                        character_id=char_ref,
                        history_dict=past_hist,
                        character_gender=c_gender,
                        conn=conn
                    )

            # Backfill any gameplay milestone memories
            for m in mems:
                m_str = str(m).strip() if m else ""
                if not m_str or m_str.startswith("Past History:"):
                    continue
                if is_romantic_milestone_str(m_str):
                    low = m_str.lower()
                    act = "kiss"
                    dirn = "mutual"
                    if "intercourse" in low or "intimate night" in low:
                        act = "intercourse"
                    elif "oral" in low:
                        act = "oral"
                        dirn = "receive" if "received" in low else ("give" if "provided" in low or "performed" in low else "mutual")
                    elif "manual" in low or "handjob" in low or "fingered" in low:
                        act = "manual"
                        dirn = "receive" if "received" in low else ("give" if "stimulated" in low or "gave" in low else "mutual")
                    elif "anal" in low:
                        act = "anal"
                        dirn = "receive" if "received" in low else "give"
                    elif "confess" in low:
                        act = "confession"
                    elif "date" in low:
                        act = "date"

                    record_intimate_event(
                        session_id=sess_id,
                        character_id=char_ref,
                        partner_name="Player",
                        act_type=act,
                        direction=dirn,
                        partner_id="player",
                        partner_role="Player",
                        turn_number=1,
                        event_origin="gameplay",
                        is_physical=(act in ("intercourse", "oral", "manual", "anal", "kiss")),
                        narrative_summary=m_str,
                        character_gender=c_gender,
                        partner_gender="unknown",
                        conn=conn
                    )

        ev_rows = conn.execute(
            "SELECT * FROM intimate_events WHERE session_id = ? AND character_id = ? AND is_physical = 1",
            (sess_id, char_ref)
        ).fetchall()
        tracks = compute_intimate_tracks_from_ledger([dict(er) for er in ev_rows])
        prof["tracks"] = tracks

        conn.execute(
            """UPDATE contacts
               SET appearance_json = ?, intimate_profile_json = ?
               WHERE id = ?""",
            (json.dumps(app), json.dumps(prof), d["id"])
        )
        migrated_count += 1

    return migrated_count


def init_db(force: bool = False):
    with get_conn() as conn:
        if not force:
            try:
                has_migrations = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
                ).fetchone()
                has_sessions = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sessions'"
                ).fetchone()
                if has_migrations and has_sessions:
                    run_schema_migrations(conn)
                    return
            except Exception:
                pass
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        conn.executescript(CREATE_SESSION_LOCKS_TABLE)
        run_schema_migrations(conn)


def vacuum_database() -> None:
    """Reclaims unused disk space by rebuilding the database file."""
    with get_conn() as conn:
        conn.execute("VACUUM")

def _to_str(val, default: str = "") -> str:
    if val is None:
        return default
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        if any("tier" in str(k).lower() for k in val.keys()):
            try:
                from mechanics.world.locations.hierarchy import parse_structured_location_dict, format_tiered_location_string
                parsed = parse_structured_location_dict(val)
                if parsed:
                    return format_tiered_location_string(*parsed)
            except Exception:
                pass
        return str(val.get("name") or val.get("title") or val.get("location") or val.get("text") or json.dumps(val))
    if isinstance(val, (list, tuple)):
        return json.dumps(val)
    return str(val)

def _is_suspicious_entity_text(text: str) -> bool:
    if not text or len(text) > 80:
        return True
    t_lower = text.lower()
    suspicious = ("return result", "function", "javascript", "const ", "let ", "var ", "this.", "=>", "};", "});", "//", "/*", ")),-1")
    return any(s in t_lower for s in suspicious)

def _safe_int_db(val, default=None) -> int | None:
    if val is None:
        return default
    if isinstance(val, int) and not isinstance(val, bool):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        cleaned = val.strip().lstrip("+")
        try:
            return int(cleaned)
        except (ValueError, TypeError):
            pass
    return default

def _sanitize_npcs_list(session_id: int, npcs: list) -> list:
    """Ensure any NPC in current_npcs has a proper character name instead of a generic role title,
    and filter out malformed or code-injected artifacts. Deduplicates by name (case-insensitive),
    merging stat data from later occurrences into the first so no HP/status info is lost."""
    if not isinstance(npcs, list):
        return []
    import namegen
    clean_list = []
    fac_map = {}
    try:
        with get_conn() as conn:
            fac_rows = conn.execute("SELECT leadership_roster_json FROM factions WHERE session_id=?", (session_id,)).fetchall()
            for fr in fac_rows:
                r_list = json.loads(fr["leadership_roster_json"] or "[]")
                for r in r_list:
                    if r.get("title") and r.get("name"):
                        fac_map[r["title"].lower()] = r["name"]
    except Exception:
        pass

    scen = "fantasy"
    try:
        with get_conn() as conn:
            s_row = conn.execute("SELECT scenario FROM sessions WHERE id=?", (session_id,)).fetchone()
            if s_row and s_row["scenario"]:
                scen = s_row["scenario"]
    except Exception:
        pass

    for npc in npcs:
        if isinstance(npc, dict):
            raw_name = str(npc.get("name", "")).strip()
            if not raw_name or _is_suspicious_entity_text(raw_name):
                continue
            if namegen.is_generic_role_name(raw_name) or not namegen.is_valid_entity_name(raw_name):
                matched = fac_map.get(raw_name.lower())
                proper_name = matched or namegen.generate_person_name(scen)
                role_val = str(npc.get("role") or raw_name)[:60]
            else:
                proper_name = raw_name[:60]
                role_val = str(npc.get("role", ""))[:60]

            clean_entry = {
                "name": proper_name,
                "role": role_val,
                "level": _safe_int_db(npc.get("level")),
                "hp": _safe_int_db(npc.get("hp")),
                "max_hp": _safe_int_db(npc.get("max_hp")),
                "mp": _safe_int_db(npc.get("mp")),
                "max_mp": _safe_int_db(npc.get("max_mp")),
                "status_effects": [str(s.get("name", s)) if isinstance(s, dict) else str(s) for s in (npc.get("status_effects") or []) if s and not _is_suspicious_entity_text(str(s))]
            }
            if npc.get("mood"):
                clean_entry["mood"] = str(npc["mood"]).strip()[:40]
            if isinstance(npc.get("micro_blocking"), dict):
                clean_entry["micro_blocking"] = dict(npc["micro_blocking"])
            for k in ("composure_state", "stage_role", "attention_ring"):
                if npc.get(k):
                    clean_entry[k] = str(npc[k]).strip()[:40]
            if npc.get("composure_ttl") is not None:
                clean_entry["composure_ttl"] = _safe_int_db(npc.get("composure_ttl"), 0)
            clean_list.append(clean_entry)
        elif isinstance(npc, str):
            raw_str = str(npc).strip()
            if not raw_str or _is_suspicious_entity_text(raw_str):
                continue
            if namegen.is_generic_role_name(raw_str) or not namegen.is_valid_entity_name(raw_str):
                matched = fac_map.get(raw_str.lower())
                proper_name = matched or namegen.generate_person_name(scen)
                clean_list.append({"name": proper_name, "role": raw_str[:60]})
            else:
                clean_list.append({"name": raw_str[:60], "role": ""})

    # Deduplicate by name (case-insensitive), preserving order.
    # If a later entry has hp/status data that the first lacks, merge it in.
    seen: dict[str, int] = {}  # name_lower -> index in deduped
    deduped: list[dict] = []
    for entry in clean_list:
        key = entry["name"].lower()
        if key in seen:
            existing = deduped[seen[key]]
            # Merge: prefer non-None values from the later entry for stat fields
            for field in ("level", "hp", "max_hp", "mp", "max_mp", "mood", "micro_blocking", "composure_state", "composure_ttl", "stage_role", "attention_ring"):
                if existing.get(field) is None and entry.get(field) is not None:
                    existing[field] = entry[field]

            # Merge status_effects: union without duplicates
            existing_se = set(existing.get("status_effects") or [])
            for se in (entry.get("status_effects") or []):
                if se not in existing_se:
                    existing.setdefault("status_effects", []).append(se)
                    existing_se.add(se)
        else:
            seen[key] = len(deduped)
            deduped.append(entry)
    return deduped

SESSION_CHILD_TABLES = (
    "session_locations", "world_nodes", "world_edges", "lorebook", "school_directory", "contacts", "factions",
    "quests", "quest_waypoints", "session_clues", "phone_messages",
    "phone_appointments", "phone_gossip_feed", "commitments_ledger", "session_digests",
    "session_chronicles", "npc_memories", "session_members", "households", "intimate_events",
    "social_persons", "social_ties", "actor_physical_states", "actor_garments"
)

STAT_COLUMN = {"STR": "str_", "PER": "per_", "END": "end_", "CHA": "cha",
               "INT": "int_", "AGI": "agi", "LUK": "luk"}


def acquire_distributed_lock(lock_key: str, owner_id: str, timeout_seconds: int = 45) -> bool:
    """Attempts to acquire a database-backed distributed lock.
    Returns True if successfully acquired (or already held by this owner), False if locked by someone else.
    """
    import time
    now = time.time()
    with get_conn() as conn:
        # Clear expired locks safely inside the transaction
        conn.execute("DELETE FROM session_locks WHERE locked_at < ?", (now - timeout_seconds,))
        
        try:
            conn.execute(
                "INSERT INTO session_locks (lock_key, locked_at, locked_by) VALUES (?, ?, ?)",
                (lock_key, now, owner_id)
            )
            return True
        except sqlite3.IntegrityError:
            # Check if we already own it
            row = conn.execute("SELECT locked_by FROM session_locks WHERE lock_key=?", (lock_key,)).fetchone()
            if row and row["locked_by"] == owner_id:
                # Refresh it
                conn.execute("UPDATE session_locks SET locked_at=? WHERE lock_key=?", (now, lock_key))
                return True
            return False

def release_distributed_lock(lock_key: str, owner_id: str):
    """Releases a database-backed distributed lock if we own it."""
    with get_conn() as conn:
        conn.execute("DELETE FROM session_locks WHERE lock_key=? AND locked_by=?", (lock_key, owner_id))


DISCORD_SNOWFLAKE_MIN = 10_000_000_000_000_000  # 10^16 (covers all 17-19 digit Discord snowflakes, back to 2015)


def is_discord_snowflake(user_id: Any) -> bool:
    """Returns True if the ID falls in the 64-bit Discord snowflake range (17-19 digits)."""
    try:
        val = int(str(user_id).strip())
        return val >= DISCORD_SNOWFLAKE_MIN
    except (ValueError, TypeError):
        return False


def create_database_snapshot(tag: str = "auto", max_backups: int = 5, custom_dir: str = "backups") -> str:
    """Creates a non-blocking SQLite online backup using SQLite's backup API.
    Maintains a rolling window of the last `max_backups` snapshot files.
    """
    import os
    import time

    if not os.path.isabs(custom_dir):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        custom_dir = os.path.join(project_root, custom_dir)

    os.makedirs(custom_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_filename = f"hikayat_{tag}_{timestamp}.db"
    backup_path = os.path.join(custom_dir, backup_filename)

    with get_conn() as src:
        dest = sqlite3.connect(backup_path)
        try:
            src.backup(dest)
        finally:
            dest.close()

    # Rolling retention: purge oldest snapshots if exceeding max_backups
    try:
        existing = [
            os.path.join(custom_dir, f)
            for f in os.listdir(custom_dir)
            if f.startswith("hikayat_") and f.endswith(".db")
        ]
        existing.sort(key=lambda p: os.path.getmtime(p))
        if len(existing) > max_backups:
            to_remove = existing[: len(existing) - max_backups]
            for old_path in to_remove:
                for ext in ["", "-wal", "-shm", "-journal"]:
                    try:
                        p = old_path + ext if ext else old_path
                        if os.path.exists(p):
                            os.remove(p)
                    except OSError:
                        pass
    except Exception:
        pass

    return backup_path


def safe_cleanup_test_records(min_user_id: int = 800_000, max_user_id: int = 999_999) -> dict[str, int]:
    """Safely cleans up test users and inventory within a strictly bounded range.
    Refuses to delete any ID matching Discord snowflakes (>= 10^16).
    """
    if min_user_id >= DISCORD_SNOWFLAKE_MIN or max_user_id >= DISCORD_SNOWFLAKE_MIN:
        raise ValueError(
            f"Safety guardrail triggered! Range [{min_user_id}, {max_user_id}] overlaps Discord snowflake range."
        )
    if min_user_id <= 0 or max_user_id < min_user_id:
        raise ValueError(f"Invalid test cleanup range [{min_user_id}, {max_user_id}].")

    deleted_counts = {}
    with get_conn() as conn:
        c1 = conn.execute(
            "DELETE FROM inventory WHERE user_id BETWEEN ? AND ?",
            (min_user_id, max_user_id)
        ).rowcount
        c2 = conn.execute(
            "DELETE FROM user_settings WHERE user_id BETWEEN ? AND ?",
            (min_user_id, max_user_id)
        ).rowcount
        c3 = conn.execute(
            "DELETE FROM characters WHERE user_id BETWEEN ? AND ?",
            (min_user_id, max_user_id)
        ).rowcount
        c4 = conn.execute(
            "DELETE FROM adventure_saves WHERE user_id BETWEEN ? AND ?",
            (min_user_id, max_user_id)
        ).rowcount
        c5 = conn.execute(
            "DELETE FROM session_members WHERE user_id BETWEEN ? AND ?",
            (min_user_id, max_user_id)
        ).rowcount
        deleted_counts["inventory"] = c1
        deleted_counts["user_settings"] = c2
        deleted_counts["characters"] = c3
        deleted_counts["adventure_saves"] = c4
        deleted_counts["session_members"] = c5
    return deleted_counts


def set_db_path(new_path: str):
    """Dynamically switches the active SQLite database path and resets connection pools."""
    import db
    import config
    close_all_connections()
    db.DB_PATH = new_path
    db.core.DB_PATH = new_path
    config.DB_PATH = new_path


def isolate_simulation_db(explicit_path: str | None = None, prefix: str = "hikayat_sim_") -> tuple[str, bool]:
    """Switches the active database to an isolated database for simulation/testing.
    Returns:
        (db_path, is_temporary)
    """
    import tempfile

    if explicit_path:
        target_path = explicit_path
        is_temp = False
    else:
        tf = tempfile.NamedTemporaryFile(prefix=prefix, suffix=".db", delete=False)
        target_path = tf.name
        tf.close()
        is_temp = True

    set_db_path(target_path)
    init_db()
    return target_path, is_temp


def cleanup_simulation_db(target_path: str, keep: bool = False, is_temp: bool = True):
    """Safely closes connections and cleans up temporary simulation database files on disk."""
    import os
    import gc
    import time

    close_all_connections()
    if is_temp and not keep:
        gc.collect()
        for ext in ["", "-wal", "-shm", "-journal"]:
            f_path = target_path + ext if ext else target_path
            if os.path.exists(f_path):
                for _ in range(5):
                    try:
                        os.unlink(f_path)
                        break
                    except (PermissionError, OSError):
                        time.sleep(0.05)


@contextmanager
def use_temporary_db(custom_path: str | None = None, keep_on_exit: bool = False, prefix: str = "hikayat_sim_"):
    """Context manager for running tests or simulations against an isolated SQLite database."""
    import db
    old_path = db.DB_PATH
    target_path, is_temp = isolate_simulation_db(explicit_path=custom_path, prefix=prefix)
    try:
        yield target_path
    finally:
        set_db_path(old_path)
        cleanup_simulation_db(target_path, keep=keep_on_exit, is_temp=is_temp)

