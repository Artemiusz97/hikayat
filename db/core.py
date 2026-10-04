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
    debug_reveal_all_info INTEGER DEFAULT 0  -- 0 | 1 (reveal all predetermined info & history)
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
    last_turn_snapshot_json TEXT DEFAULT '{}'
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
    created_at          REAL,
    updated_at          REAL,
    UNIQUE(session_id, character_id, npc_id)
);

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

CREATE TABLE IF NOT EXISTS quest_waypoints (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    quest_id            TEXT NOT NULL,
    sub_obj_id          INTEGER DEFAULT NULL,
    stage_index         INTEGER NOT NULL,
    stage_label         TEXT NOT NULL,
    target_location     TEXT NOT NULL,
    target_npc          TEXT DEFAULT '',
    completion_trigger  TEXT DEFAULT 'arrival',
    resource_target     INTEGER DEFAULT 0,
    resource_collected  INTEGER DEFAULT 0,
    status              TEXT DEFAULT 'locked',
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
    status              TEXT NOT NULL DEFAULT 'pending',  -- 'pending' | 'arrived' | 'cancelled'
    created_at          REAL NOT NULL,
    UNIQUE(session_id, npc_id)
);

CREATE TABLE IF NOT EXISTS school_directory (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          INTEGER NOT NULL,
    npc_id              TEXT NOT NULL,
    name                TEXT NOT NULL,
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
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL,
    source_entity   TEXT NOT NULL,    -- 'player' or NPC name who made the commitment
    target_entity   TEXT NOT NULL,    -- NPC name or 'player' who it is directed at
    commitment_type TEXT NOT NULL,    -- 'promise' | 'secret' | 'debt' | 'pact' | 'threat'
    description     TEXT NOT NULL,   -- plain-text summary of what was committed
    status          TEXT DEFAULT 'active',  -- 'active' | 'fulfilled' | 'broken'
    turn_created    INTEGER NOT NULL,
    updated_at      REAL NOT NULL
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
CREATE INDEX IF NOT EXISTS idx_digests_session ON session_digests(session_id);

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

    return newly_applied


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

    for npc in npcs:
        if isinstance(npc, dict):
            raw_name = str(npc.get("name", "")).strip()
            if not raw_name or _is_suspicious_entity_text(raw_name):
                continue
            if namegen.is_generic_role_name(raw_name):
                matched = fac_map.get(raw_name.lower())
                proper_name = matched or namegen.generate_person_name()
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
            clean_list.append(clean_entry)
        elif isinstance(npc, str):
            raw_str = str(npc).strip()
            if not raw_str or _is_suspicious_entity_text(raw_str):
                continue
            if namegen.is_generic_role_name(raw_str):
                matched = fac_map.get(raw_str.lower())
                proper_name = matched or namegen.generate_person_name()
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
            for field in ("level", "hp", "max_hp", "mp", "max_mp", "mood"):
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
    "session_locations", "lorebook", "school_directory", "contacts", "factions",
    "quests", "quest_waypoints", "session_clues", "phone_messages",
    "phone_appointments", "phone_gossip_feed", "commitments_ledger", "session_digests",
    "session_chronicles", "npc_memories", "session_members"
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

