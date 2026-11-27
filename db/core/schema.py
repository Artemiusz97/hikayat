from __future__ import annotations

from ..registry import get_session_child_table_names

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
    attribute           TEXT DEFAULT NULL,
    combat_archetype    TEXT DEFAULT NULL,
    ability_medium      TEXT DEFAULT NULL,
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
    slot        TEXT DEFAULT NULL,
    is_quest_locked INTEGER DEFAULT 0,
    linked_quest_id TEXT DEFAULT '',
    is_pact_locked INTEGER DEFAULT 0,
    linked_contract_key TEXT DEFAULT ''
);
-- 'slot' holds one of the 6 canonical equipment slots (see
-- character_data.EQUIPMENT_SLOTS: Weapon/Shield/Top/Bottom/Gloves/Shoes) that
-- this item currently occupies, or NULL if it isn't equipped into one. Only
-- meaningful when equipped=1. See db.equip_item/unequip_slot/get_equipment.

CREATE TABLE IF NOT EXISTS user_settings (
    user_id             INTEGER PRIMARY KEY,
    verbosity           TEXT DEFAULT 'vivid',   -- 'normal' | 'vivid' | 'noir' | 'witty' | 'shakespearean' | 'brainrot'
    narrative_pacing    TEXT DEFAULT 'balanced', -- 'concise' | 'balanced' | 'novelistic'
    dialogue_mode       TEXT DEFAULT 'adaptive',
    image_gen_enabled   INTEGER DEFAULT 0,
    image_model         TEXT,
    choices_style       TEXT DEFAULT 'dropdown',  -- 'dropdown' | 'embed' | 'buttons'
    combat_ui_style     TEXT DEFAULT 'battle_deck', -- 'battle_deck' | 'multi_dropdown'
    result_display      TEXT DEFAULT 'detailed', -- 'detailed' | 'compact'
    show_percentages    INTEGER DEFAULT 1,       -- 1 = show raw %, 0 = hide raw %
    show_enemy_hp       INTEGER DEFAULT 1,       -- 1 = show enemy HP bars, 0 = hide
    show_enemy_intent   INTEGER DEFAULT 1,       -- 1 = show enemy intent, 0 = hide
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
    narrative_pacing    TEXT DEFAULT 'balanced',
    dialogue_mode       TEXT DEFAULT 'adaptive',
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
    show_enemy_hp       INTEGER DEFAULT 1,
    show_enemy_intent   INTEGER DEFAULT 1,
    last_turn_snapshot_json TEXT DEFAULT '{}',
    language            TEXT DEFAULT 'en',
    narration_language  TEXT DEFAULT 'en',
    temporary_companions_json TEXT DEFAULT '[]',
    scene_image_url     TEXT DEFAULT NULL,
    character_id        INTEGER DEFAULT NULL,
    slot                INTEGER DEFAULT 1,
    schema_epoch        INTEGER DEFAULT 2,
    event_pity_counter  REAL DEFAULT 0.0,
    rumor_pity_counter  REAL DEFAULT 0.0,
    minor_event_pity_counter REAL DEFAULT 0.0,
    player_scandal_cooldown_until_day INTEGER DEFAULT 0,
    recent_witness_catches_json TEXT DEFAULT '[]',
    npc_gossip_shared_today_json TEXT DEFAULT '{}',
    combat_threat_ledger_json TEXT NOT NULL DEFAULT '{}',
    combat_boss_telegraph_json TEXT NOT NULL DEFAULT '{}',
    turn_count INTEGER NOT NULL DEFAULT 0,
    last_digested_turn INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS world_events (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id                  INTEGER NOT NULL,
    event_key                   TEXT NOT NULL,
    template_key                TEXT DEFAULT '',
    entity_type                 TEXT NOT NULL,   -- 'macro_event' | 'rumor' | 'minor_event'
    event_subtype               TEXT NOT NULL,   -- 'crisis' | 'festival' | 'scandal' | 'phenomenon' | 'intrigue'
    title                       TEXT NOT NULL,
    description                 TEXT DEFAULT '',
    sfw_fallback_description    TEXT DEFAULT '',
    faction_id                  TEXT DEFAULT '',
    implicated_contact_id       INTEGER DEFAULT NULL,  -- Soft ID (NO hard FK REFERENCES contacts(id))
    location_node_id            TEXT DEFAULT '',
    location_name               TEXT DEFAULT '',
    is_discovered               INTEGER DEFAULT 0,
    discovery_source            TEXT DEFAULT '',
    discovered_turn             INTEGER DEFAULT NULL,
    claimed_turn                INTEGER DEFAULT NULL,
    linked_quest_id             TEXT DEFAULT '',
    status                      TEXT DEFAULT 'active', -- 'active' | 'resolved_aftermath' | 'expired' | 'cold' | 'escalated'
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
    engine              TEXT DEFAULT '',
    dossier_stage       TEXT DEFAULT 'legacy',
    anomaly_blueprint_json TEXT DEFAULT '{}',
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
    household_id        INTEGER REFERENCES households(id) ON DELETE SET NULL,
    household_role      TEXT DEFAULT 'child',
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
CREATE INDEX IF NOT EXISTS idx_social_ties_sess_status ON social_ties(session_id, status);

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
    hq_node_id          TEXT DEFAULT '',        -- foreign key to world_nodes.node_id
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
    state_json          TEXT DEFAULT '{}',
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
    state_json          TEXT DEFAULT '{}',
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
CREATE INDEX IF NOT EXISTS idx_quest_waypoints_sub_obj ON quest_waypoints(session_id, quest_id, sub_obj_id);

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
    is_consumed             INTEGER DEFAULT 0,
    deduction_parents_json  TEXT DEFAULT '[]',
    turn_created            INTEGER DEFAULT 1,
    created_at              REAL,
    updated_at              REAL
);

CREATE INDEX IF NOT EXISTS idx_session_clues_sess ON session_clues(session_id);
CREATE INDEX IF NOT EXISTS idx_session_clues_npc ON session_clues(session_id, linked_npc);
CREATE INDEX IF NOT EXISTS idx_session_clues_sess_turn ON session_clues(session_id, turn_created);

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
    realm_name          TEXT DEFAULT NULL,
    show_realm_badge    INTEGER DEFAULT 0,
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
    end_day             INTEGER DEFAULT NULL,
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
CREATE UNIQUE INDEX IF NOT EXISTS uq_commitments_session_key ON commitments_ledger(session_id, commitment_key) WHERE commitment_key != '';

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
    active_outfit_preset TEXT DEFAULT '',
    wardrobe_meta_json  TEXT DEFAULT '{}',
    created_at          REAL NOT NULL,
    updated_at          REAL NOT NULL,
    UNIQUE(session_id, canonical_key)
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
    UNIQUE(session_id, actor_key, slot)
);

CREATE TABLE IF NOT EXISTS session_digests (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    turn_start          INTEGER NOT NULL,
    turn_end            INTEGER NOT NULL,
    summary_bullets_json TEXT NOT NULL DEFAULT '[]',  -- JSON list of 2-3 narrative fact strings
    entities_json       TEXT NOT NULL DEFAULT '[]',
    location_tag        TEXT NOT NULL DEFAULT '',
    quest_ids_json      TEXT NOT NULL DEFAULT '[]',
    compacted_count     INTEGER NOT NULL DEFAULT 0,
    compacted_at_turn   INTEGER NOT NULL DEFAULT 0,
    is_compacted        INTEGER NOT NULL DEFAULT 0,
    created_at          REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_lorebook_session ON lorebook(session_id);
CREATE INDEX IF NOT EXISTS idx_characters_user_active ON characters(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_session_members_user ON session_members(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_char_slot ON sessions(character_id, slot, status);
CREATE INDEX IF NOT EXISTS idx_contacts_session ON contacts(session_id, npc_id);
CREATE INDEX IF NOT EXISTS idx_contacts_char ON contacts(character_id);
CREATE INDEX IF NOT EXISTS idx_contacts_household_id ON contacts(household_id);
CREATE INDEX IF NOT EXISTS idx_households_session_surname ON households(session_id, surname);
CREATE INDEX IF NOT EXISTS idx_factions_session_hq_node ON factions(session_id, hq_node_id);
CREATE INDEX IF NOT EXISTS idx_inventory_char_user ON inventory(character_id, user_id);
CREATE INDEX IF NOT EXISTS idx_inventory_user_linked_quest ON inventory(user_id, linked_quest_id);
CREATE INDEX IF NOT EXISTS idx_inventory_pact_contract ON inventory(linked_contract_key) WHERE linked_contract_key != '';
CREATE INDEX IF NOT EXISTS idx_phone_messages_session ON phone_messages(session_id, contact_npc_id);
CREATE INDEX IF NOT EXISTS idx_phone_gossip_sess ON phone_gossip_feed(session_id);
CREATE INDEX IF NOT EXISTS idx_saves_user_char ON adventure_saves(user_id, character_id);
CREATE INDEX IF NOT EXISTS idx_commitments_session ON commitments_ledger(session_id, status);
CREATE INDEX IF NOT EXISTS idx_commitments_time ON commitments_ledger(session_id, scheduled_day, start_minute, end_minute);
CREATE INDEX IF NOT EXISTS idx_commitments_node ON commitments_ledger(session_id, target_node_id, status);
CREATE INDEX IF NOT EXISTS idx_digests_session ON session_digests(session_id);
CREATE INDEX IF NOT EXISTS idx_digests_session_turn ON session_digests(session_id, turn_end);
CREATE INDEX IF NOT EXISTS idx_digests_session_compacted ON session_digests(session_id, is_compacted);
CREATE INDEX IF NOT EXISTS idx_actor_phys_lookup ON actor_physical_states(session_id, canonical_key);
CREATE INDEX IF NOT EXISTS idx_actor_garments_actor ON actor_garments(session_id, actor_key);

CREATE VIRTUAL TABLE IF NOT EXISTS session_digests_fts USING fts5(
    session_id UNINDEXED,
    bullet_text UNINDEXED,
    search_tokens,
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS session_chronicles (
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
CREATE INDEX IF NOT EXISTS idx_chronicles_session_turn ON session_chronicles(session_id, turn_end);
CREATE INDEX IF NOT EXISTS idx_npc_memories_session_npc ON npc_memories(session_id, npc_name);
CREATE INDEX IF NOT EXISTS idx_world_events_session ON world_events(session_id, status);
CREATE INDEX IF NOT EXISTS idx_world_events_type ON world_events(session_id, entity_type, status);
CREATE INDEX IF NOT EXISTS idx_world_events_contact ON world_events(session_id, implicated_contact_id);
CREATE INDEX IF NOT EXISTS idx_world_events_session_linked_quest ON world_events(session_id, linked_quest_id);

CREATE TRIGGER IF NOT EXISTS trg_cleanup_implicated_contact
AFTER DELETE ON contacts
BEGIN
    UPDATE world_events SET implicated_contact_id = NULL WHERE implicated_contact_id = OLD.id;
END;

CREATE TABLE IF NOT EXISTS campaign_spines (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id              INTEGER NOT NULL,
    scenario                TEXT NOT NULL,
    mastermind_profile_json TEXT NOT NULL DEFAULT '{}',
    lieutenants_roster_json TEXT NOT NULL DEFAULT '[]',
    chapters_blueprint_json TEXT NOT NULL DEFAULT '{}',
    nemeses_json            TEXT NOT NULL DEFAULT '[]',
    hidden_bible_json       TEXT NOT NULL DEFAULT '{}',
    ending_axes_json        TEXT NOT NULL DEFAULT '{}',
    chronicle_tapestry_json TEXT NOT NULL DEFAULT '{}',
    climax_status           TEXT NOT NULL DEFAULT 'pending',
    epilogue_status         TEXT NOT NULL DEFAULT 'pending',
    state_events_json       TEXT NOT NULL DEFAULT '[]',
    created_at              REAL NOT NULL,
    updated_at              REAL NOT NULL,
    UNIQUE(session_id)
);
CREATE INDEX IF NOT EXISTS idx_campaign_spines_sess ON campaign_spines(session_id);

CREATE TABLE IF NOT EXISTS quest_dossiers (
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
);
CREATE INDEX IF NOT EXISTS idx_quest_dossiers_sess_qid ON quest_dossiers(session_id, quest_id);
CREATE INDEX IF NOT EXISTS idx_quest_dossiers_sess_stage ON quest_dossiers(session_id, status_stage);
CREATE INDEX IF NOT EXISTS idx_quests_session_status ON quests(session_id, status);

CREATE TABLE IF NOT EXISTS user_folklore_codex (
    user_id             INTEGER NOT NULL,
    codex_id            TEXT NOT NULL,
    unlock_stage        TEXT NOT NULL DEFAULT 'sighted',
    times_sighted       INTEGER NOT NULL DEFAULT 1,
    times_contained     INTEGER NOT NULL DEFAULT 0,
    first_discovered_at REAL,
    updated_at          REAL,
    first_session_id    INTEGER DEFAULT NULL,
    first_turn          INTEGER DEFAULT NULL,
    PRIMARY KEY (user_id, codex_id)
);
CREATE INDEX IF NOT EXISTS idx_user_folklore_codex_uid ON user_folklore_codex(user_id);

CREATE TABLE IF NOT EXISTS session_anomaly_records (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    record_type         TEXT NOT NULL, -- 'field_log' | 'vault_requisition' | 'vault_log' | 'contained_log'
    entity_key          TEXT NOT NULL DEFAULT '',
    codex_id            TEXT NOT NULL DEFAULT '',
    stage               TEXT NOT NULL DEFAULT 'sighted',
    first_turn          INTEGER NOT NULL DEFAULT 0,
    turn_updated        INTEGER NOT NULL DEFAULT 0,
    payload_json        TEXT NOT NULL DEFAULT '{}',
    created_at          REAL NOT NULL,
    updated_at          REAL NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_session_anom_field_log
    ON session_anomaly_records(session_id, record_type, entity_key)
    WHERE record_type = 'field_log' AND entity_key != '';
CREATE INDEX IF NOT EXISTS idx_session_anom_sess_type ON session_anomaly_records(session_id, record_type);
CREATE INDEX IF NOT EXISTS idx_session_anom_sess_turn ON session_anomaly_records(session_id, first_turn, turn_updated);

CREATE TABLE IF NOT EXISTS actor_physical_turn_snapshots (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    turn_number         INTEGER NOT NULL,
    states_json         TEXT NOT NULL DEFAULT '[]',
    garments_json       TEXT NOT NULL DEFAULT '[]',
    room_meta_json      TEXT NOT NULL DEFAULT '{}',
    updated_at          REAL NOT NULL,
    UNIQUE(session_id, turn_number)
);
CREATE INDEX IF NOT EXISTS idx_phys_turn_snap_sess_turn ON actor_physical_turn_snapshots(session_id, turn_number);

CREATE TABLE IF NOT EXISTS player_properties (
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
    buyer_character_id  INTEGER,
    UNIQUE(session_id, property_id)
);
CREATE INDEX IF NOT EXISTS idx_player_properties_sess ON player_properties(session_id);
CREATE INDEX IF NOT EXISTS idx_player_properties_node ON player_properties(session_id, facility_node_id);
CREATE INDEX IF NOT EXISTS idx_player_properties_primary ON player_properties(session_id, is_primary);

CREATE TABLE IF NOT EXISTS npc_social_composure (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id              INTEGER NOT NULL,
    npc_id                  TEXT NOT NULL,
    current_composure       INTEGER NOT NULL DEFAULT 100,
    max_composure           INTEGER NOT NULL DEFAULT 100,
    composure_state         TEXT NOT NULL DEFAULT 'composed',
    mood                    TEXT NOT NULL DEFAULT 'Engaged',
    mood_dc_mod             INTEGER NOT NULL DEFAULT 0,
    last_schedule_block     TEXT NOT NULL DEFAULT '',
    last_interaction_day    INTEGER NOT NULL DEFAULT 1,
    last_interaction_minute INTEGER NOT NULL DEFAULT 0,
    lockout_until_day       INTEGER NOT NULL DEFAULT 0,
    lockout_until_minute    INTEGER NOT NULL DEFAULT 0,
    clear_the_air_required  INTEGER NOT NULL DEFAULT 0,
    clear_the_air_reason    TEXT NOT NULL DEFAULT '',
    turn_updated            INTEGER NOT NULL DEFAULT 0,
    updated_at              REAL NOT NULL,
    UNIQUE(session_id, npc_id)
);
CREATE INDEX IF NOT EXISTS idx_npc_social_composure_sess ON npc_social_composure(session_id, npc_id);

CREATE TABLE IF NOT EXISTS character_social_daily (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id              INTEGER NOT NULL,
    character_id            INTEGER NOT NULL DEFAULT 0,
    npc_id                  TEXT NOT NULL,
    current_day             INTEGER NOT NULL DEFAULT 1,
    daily_affinity_earned   INTEGER NOT NULL DEFAULT 0,
    is_on_date              INTEGER NOT NULL DEFAULT 0,
    gift_given_today        INTEGER NOT NULL DEFAULT 0,
    confession_given_today  INTEGER NOT NULL DEFAULT 0,
    turn_updated            INTEGER NOT NULL DEFAULT 0,
    updated_at              REAL NOT NULL,
    UNIQUE(session_id, character_id, npc_id, current_day)
);
CREATE INDEX IF NOT EXISTS idx_char_social_daily_lookup ON character_social_daily(session_id, character_id, current_day);

CREATE TABLE IF NOT EXISTS social_topic_states (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id              INTEGER NOT NULL,
    character_id            INTEGER NOT NULL DEFAULT 0,
    npc_id                  TEXT NOT NULL,
    topic_id                TEXT NOT NULL,
    category                TEXT NOT NULL DEFAULT '',
    depth_tier              INTEGER NOT NULL DEFAULT 1,
    last_outcome            TEXT NOT NULL DEFAULT '',
    last_discussed_day      INTEGER NOT NULL DEFAULT 0,
    cooldown_until_day      INTEGER NOT NULL DEFAULT 0,
    cooldown_until_minute   INTEGER NOT NULL DEFAULT 0,
    last_venue_leaf         TEXT NOT NULL DEFAULT '',
    turn_updated            INTEGER NOT NULL DEFAULT 0,
    updated_at              REAL NOT NULL,
    UNIQUE(session_id, character_id, npc_id, topic_id)
);
CREATE INDEX IF NOT EXISTS idx_social_topic_states_lookup ON social_topic_states(session_id, character_id, npc_id);

CREATE TABLE IF NOT EXISTS contact_dossier_discoveries (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id              INTEGER NOT NULL,
    character_id            INTEGER NOT NULL DEFAULT 0,
    npc_id                  TEXT NOT NULL,
    fact_category           TEXT NOT NULL,
    fact_key                TEXT NOT NULL,
    fact_value              TEXT NOT NULL DEFAULT '',
    discovered_turn         INTEGER NOT NULL DEFAULT 0,
    discovery_source        TEXT NOT NULL DEFAULT 'dialogue',
    created_at              REAL NOT NULL,
    UNIQUE(session_id, character_id, npc_id, fact_category, fact_key)
);
CREATE INDEX IF NOT EXISTS idx_contact_discoveries_lookup ON contact_dossier_discoveries(session_id, character_id, npc_id);
CREATE INDEX IF NOT EXISTS idx_contact_discoveries_turn ON contact_dossier_discoveries(session_id, discovered_turn);

CREATE TABLE IF NOT EXISTS social_turn_snapshots (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id              INTEGER NOT NULL,
    turn_number             INTEGER NOT NULL,
    composure_json          TEXT NOT NULL DEFAULT '[]',
    daily_json              TEXT NOT NULL DEFAULT '[]',
    topic_states_json       TEXT NOT NULL DEFAULT '[]',
    updated_at              REAL NOT NULL,
    UNIQUE(session_id, turn_number)
);
CREATE INDEX IF NOT EXISTS idx_social_turn_snap_sess_turn ON social_turn_snapshots(session_id, turn_number);

CREATE TABLE IF NOT EXISTS session_entity_contracts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    character_id        INTEGER DEFAULT NULL,
    contract_key        TEXT NOT NULL,
    patron_id           TEXT NOT NULL,
    source_pool         TEXT NOT NULL DEFAULT 'bespoke',
    codex_id            TEXT NOT NULL DEFAULT '',
    entity_name         TEXT NOT NULL,
    element             TEXT NOT NULL DEFAULT 'aether',
    synergy_stat        TEXT NOT NULL DEFAULT 'INT',
    holder_type         TEXT NOT NULL DEFAULT 'player',
    holder_id           TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'active',
    tier                INTEGER NOT NULL DEFAULT 1,
    resonance_xp        INTEGER NOT NULL DEFAULT 0,
    appraisal_state     TEXT NOT NULL DEFAULT 'neutral',
    breach_stage        INTEGER NOT NULL DEFAULT 0,
    unpaid_blood_debt   INTEGER NOT NULL DEFAULT 0,
    bound_gear_item_id  INTEGER DEFAULT NULL,
    bound_gear_slot     TEXT NOT NULL DEFAULT '',
    taboo_id            TEXT NOT NULL DEFAULT '',
    tithe_schedule_json TEXT NOT NULL DEFAULT '{}',
    stat_locks_json     TEXT NOT NULL DEFAULT '{}',
    metadata_json       TEXT NOT NULL DEFAULT '{}',
    turn_signed         INTEGER NOT NULL DEFAULT 1,
    turn_updated        INTEGER NOT NULL DEFAULT 1,
    created_at          REAL NOT NULL,
    updated_at          REAL NOT NULL,
    UNIQUE(session_id, contract_key)
);
CREATE INDEX IF NOT EXISTS idx_entity_contracts_sess_holder ON session_entity_contracts(session_id, holder_type, holder_id, status);
CREATE INDEX IF NOT EXISTS idx_entity_contracts_sess_patron ON session_entity_contracts(session_id, patron_id, tier, status);
CREATE INDEX IF NOT EXISTS idx_entity_contracts_char ON session_entity_contracts(character_id, status);

CREATE TABLE IF NOT EXISTS session_contract_grudges (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    character_id        INTEGER DEFAULT NULL,
    grudge_key          TEXT NOT NULL,
    patron_id           TEXT NOT NULL,
    entity_name         TEXT NOT NULL,
    holder_id           TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'active',
    soul_scar_active    INTEGER NOT NULL DEFAULT 1,
    nemesis_spawned     INTEGER NOT NULL DEFAULT 0,
    metadata_json       TEXT NOT NULL DEFAULT '{}',
    severance_turn      INTEGER NOT NULL DEFAULT 1,
    resolved_turn       INTEGER DEFAULT NULL,
    created_at          REAL NOT NULL,
    updated_at          REAL NOT NULL,
    UNIQUE(session_id, grudge_key)
);
CREATE INDEX IF NOT EXISTS idx_contract_grudges_sess_holder ON session_contract_grudges(session_id, holder_id, status);

CREATE TABLE IF NOT EXISTS session_contract_turn_snapshots (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    turn_number         INTEGER NOT NULL,
    contracts_json      TEXT NOT NULL DEFAULT '[]',
    grudges_json        TEXT NOT NULL DEFAULT '[]',
    created_at          REAL NOT NULL,
    UNIQUE(session_id, turn_number)
);
CREATE INDEX IF NOT EXISTS idx_contract_snaps_sess_turn ON session_contract_turn_snapshots(session_id, turn_number);

CREATE TABLE IF NOT EXISTS user_patron_compendium (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                 INTEGER NOT NULL,
    patron_id               TEXT NOT NULL,
    source_pool             TEXT NOT NULL DEFAULT 'bespoke',
    codex_id                TEXT NOT NULL DEFAULT '',
    entity_name             TEXT NOT NULL DEFAULT '',
    max_tier_reached        INTEGER NOT NULL DEFAULT 1,
    times_signed            INTEGER NOT NULL DEFAULT 1,
    times_invoked           INTEGER NOT NULL DEFAULT 0,
    times_severed           INTEGER NOT NULL DEFAULT 0,
    is_currently_contracted INTEGER NOT NULL DEFAULT 1,
    metadata_json           TEXT NOT NULL DEFAULT '{}',
    first_discovered_at     REAL NOT NULL,
    updated_at              REAL NOT NULL,
    UNIQUE(user_id, patron_id)
);
CREATE INDEX IF NOT EXISTS idx_user_patron_comp_uid ON user_patron_compendium(user_id);
CREATE INDEX IF NOT EXISTS idx_user_patron_comp_codex ON user_patron_compendium(user_id, codex_id);

CREATE TABLE IF NOT EXISTS world_roster (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id              INTEGER NOT NULL,
    npc_id                  TEXT NOT NULL,
    name                    TEXT NOT NULL,
    gender                  TEXT NOT NULL DEFAULT '',
    race                    TEXT NOT NULL DEFAULT 'human',
    role                    TEXT NOT NULL DEFAULT '',
    origin                  TEXT NOT NULL DEFAULT 'venue_seed',
    tier_status             TEXT NOT NULL DEFAULT 'seeded',
    affinity_score          INTEGER NOT NULL DEFAULT 0,
    met_in_person           INTEGER NOT NULL DEFAULT 0,
    first_met_turn          INTEGER DEFAULT NULL,
    workplace_node_id       TEXT NOT NULL DEFAULT '',
    home_node_id            TEXT NOT NULL DEFAULT '',
    hangout_node_id         TEXT NOT NULL DEFAULT '',
    roaming_route_json      TEXT NOT NULL DEFAULT '[]',
    shift_profile           TEXT NOT NULL DEFAULT 'day',
    staff_status            TEXT NOT NULL DEFAULT 'active',
    staff_status_day        INTEGER NOT NULL DEFAULT 0,
    is_unique_proprietor    INTEGER NOT NULL DEFAULT 0,
    residence_unlocked      INTEGER NOT NULL DEFAULT 0,
    residence_unlock_reason TEXT NOT NULL DEFAULT '',
    discovered_slots_json   TEXT NOT NULL DEFAULT '{}',
    basic_info_json         TEXT NOT NULL DEFAULT '{}',
    appearance_json         TEXT NOT NULL DEFAULT '{}',
    traits_json             TEXT NOT NULL DEFAULT '[]',
    turn_snapshots_json     TEXT NOT NULL DEFAULT '{}',
    turn_created            INTEGER NOT NULL DEFAULT 0,
    turn_updated            INTEGER NOT NULL DEFAULT 0,
    created_at              REAL NOT NULL,
    updated_at              REAL NOT NULL,
    UNIQUE(session_id, npc_id)
);
CREATE INDEX IF NOT EXISTS idx_world_roster_sess_tier ON world_roster(session_id, tier_status);
CREATE INDEX IF NOT EXISTS idx_world_roster_workplace ON world_roster(session_id, workplace_node_id, staff_status);
CREATE INDEX IF NOT EXISTS idx_world_roster_sess_nodes ON world_roster(session_id, staff_status, home_node_id, workplace_node_id, hangout_node_id);

CREATE TABLE IF NOT EXISTS epistemic_facts (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id              INTEGER NOT NULL,
    fact_key                TEXT NOT NULL,
    category                TEXT NOT NULL DEFAULT 'secret',
    culprit_actor_key       TEXT NOT NULL DEFAULT 'player',
    subject_actor_key       TEXT NOT NULL DEFAULT '',
    location_node_id        TEXT NOT NULL DEFAULT '',
    summary                 TEXT NOT NULL DEFAULT '',
    severity                INTEGER NOT NULL DEFAULT 1,
    proof_artifact_ref      TEXT NOT NULL DEFAULT '',
    heat_score              INTEGER NOT NULL DEFAULT 50,
    decay_day_last_ticked   INTEGER NOT NULL DEFAULT 0,
    status                  TEXT NOT NULL DEFAULT 'active',
    metadata_json           TEXT NOT NULL DEFAULT '{}',
    turn_created            INTEGER NOT NULL DEFAULT 0,
    turn_updated            INTEGER NOT NULL DEFAULT 0,
    created_at              REAL NOT NULL,
    updated_at              REAL NOT NULL,
    UNIQUE(session_id, fact_key)
);
CREATE INDEX IF NOT EXISTS idx_ep_facts_session_status ON epistemic_facts(session_id, status);

CREATE TABLE IF NOT EXISTS epistemic_knowledge (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id              INTEGER NOT NULL,
    fact_key                TEXT NOT NULL,
    holder_actor_key        TEXT NOT NULL,
    confidence              TEXT NOT NULL DEFAULT 'rumor',
    containment_state       TEXT NOT NULL DEFAULT 'active',
    source_actor_key        TEXT NOT NULL DEFAULT '',
    acquisition_channel     TEXT NOT NULL DEFAULT 'witness',
    hop_count               INTEGER NOT NULL DEFAULT 0,
    player_aware            INTEGER NOT NULL DEFAULT 0,
    alibi_claim             TEXT NOT NULL DEFAULT '',
    alibi_witness_key       TEXT NOT NULL DEFAULT '',
    is_alibi_busted         INTEGER NOT NULL DEFAULT 0,
    metadata_json           TEXT NOT NULL DEFAULT '{}',
    turn_acquired           INTEGER NOT NULL DEFAULT 0,
    turn_updated            INTEGER NOT NULL DEFAULT 0,
    created_at              REAL NOT NULL,
    updated_at              REAL NOT NULL,
    UNIQUE(session_id, fact_key, holder_actor_key)
);
CREATE INDEX IF NOT EXISTS idx_ep_know_session_holder ON epistemic_knowledge(session_id, holder_actor_key);
CREATE INDEX IF NOT EXISTS idx_ep_know_session_fact ON epistemic_knowledge(session_id, fact_key);
"""

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

SESSION_CHILD_TABLES = get_session_child_table_names()

STAT_COLUMN = {"STR": "str_", "PER": "per_", "END": "end_", "CHA": "cha",
               "INT": "int_", "AGI": "agi", "LUK": "luk"}

DISCORD_SNOWFLAKE_MIN = 10_000_000_000_000_000  # 10^16 (covers all 17-19 digit Discord snowflakes, back to 2015)

DEFAULT_SNAPSHOT_KEEP_LAST = 10

WAL_MAINTENANCE_TURN_INTERVAL = 25
