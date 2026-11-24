---
name: hikayat-db-lifecycle-checklist
description: "Use this skill whenever adding or modifying SQLite tables, columns, indexes, migrations, save/load slots, turn rollbacks, or db.* functions in Hikayat's persistence layer (db/)."
---

# Hikayat SQLite Schema, Migration & Session Lifecycle Checklist

Whenever you add or alter any table, column, or query helper under `db/`, complete **all 6 lifecycle steps** below so save/load slots, turn rollbacks, AST contracts, and parallel tests never drift.

---

## 1. Schema Definition & Idempotent Migration (`db/core/`)

1. **Fresh DB Schema**: Add new tables (`CREATE TABLE IF NOT EXISTS ...`), columns, and indexes directly to `SCHEMA` in `db/core/schema.py`. Because fresh databases use a `PRAGMA user_version` fast-path (`CURRENT_SCHEMA_VERSION`), `SCHEMA` must stay 100% identical to the result of running `SCHEMA_MIGRATIONS` (enforced by `test_fresh_schema_matches_migrated_schema_parity` in `tests/test_codebase_contracts.py`).
2. **Existing DB Migration**: Append a versioned tuple to `SCHEMA_MIGRATIONS` in `db/core/migrations.py` (which advances `CURRENT_SCHEMA_VERSION`) and ensure any structural/data migration helper in `db/core/migrations_backfills.py` is idempotent when invoked inside `run_schema_migrations(conn)`.
3. **Indexes**: Add `CREATE INDEX IF NOT EXISTS idx_<table>_<cols>` to both `SCHEMA` and the migration tuple for all `(session_id, ...)` and `(character_id, ...)` lookup paths to avoid full-table scans.

---

## 2. Declarative Session Registry & Purge Wiring (`db/registry.py`, `db/core/`)

If the table is scoped to an adventure session (`session_id` column) — or if adding a non-session global table:
- Register every `session_id` table as a `SessionTableSpec` entry in `SESSION_TABLE_REGISTRY` inside `db/registry.py` (`db/core/schema.py` derives `SESSION_CHILD_TABLES` directly from non-optional registry entries). Global tables without `session_id` must be listed in `GLOBAL_TABLES` (`db/registry.py`).
- Set `purge_order` appropriately (lower deletes first; e.g. `contacts` at `20` before `households` at `80`), and verify `_delete_session_child_records_only(conn, session_id)` and `prune_orphaned_and_finished_sessions()` delete cleanly without foreign-key ordering errors.
- If the table stores turn-indexed snapshots that grow every turn, set `snapshot_table_turn_col` and `snapshot_keep_last` (and `save_row_limit_by_turn` / `save_order_col` for checkpoint exports) so `db.prune_session_turn_snapshots()` trims it automatically.

---

## 3. Save & Load Slot Cloning (`db/registry.py`, `db/saves.py`)

1. **Declarative Metadata (`db/registry.py`)**:
   - Set `include_in_save_slot`, `load_tier` (`10` parents before `20`/`30`/`40` dependents), `char_id_policy`, `session_key_cols`, `save_row_limit_by_turn`, and `orig_id_alias` (for tables whose autoincrement `id` is referenced elsewhere, e.g., `_orig_household_id`, `_orig_contact_id`, `_orig_commitment_id`, `_orig_clue_id`).
   - Any non-trivial row rewrite or nested JSON ID remap should use a named hook (`row_transform_hook`, `post_load_hook`, or `post_inventory_hook`) registered in `db/saves.py`.
2. **Embedded Session Key Rule**: If any string key column embeds the session ID (e.g., `hh_<sid>_...`, `rv_<sid>_...`), declare it in `session_key_cols` or rewrite it with `_rewrite_session_key_id(key_str, old_session_id, new_session_id)`—never use naive `.replace(str(old_sid), str(new_sid))`, which corrupts trailing digits when `old_session_id == 1`.

---

## 4. Turn Rollback & Turn 0 Opening Retry (`db/registry.py`, `db/sessions.py`)

1. **Mid-Session Turn Rollback (`rollback_session_normalized_state_after_turn`)**:
   - Set `rollback_mode` on the `SessionTableSpec` in `db/registry.py`:
     - `"delete_gt_turn"` with `rollback_turn_col` and `rollback_result_key` for simple `DELETE FROM <table> WHERE session_id = ? AND <turn_col> > ?` tables.
     - `"handler"` with `rollback_handler` (and wire the domain rollback call inside `rollback_session_normalized_state_after_turn` in `db/sessions.py`) for stateful restoration and cached summary JSON re-materialization.
     - `"derived_rebuild"`, `"static_world"`, or `"none"` when appropriate so every table's rollback contract is explicitly accounted for.
2. **Turn 0 Opening Retry (`reset_session_for_opening_retry`)**:
   - Ensure any new session-level state columns on `sessions` or keys in `sessions.extra_json` are reset cleanly while keeping character starter gear intact.

---

## 5. Facade Re-Exports & Async Concurrency Hygiene

1. **Package Root Facade (`db/__init__.py`)**:
   - Every new public function added to `db/core/`, `db/sessions.py`, `db/saves.py`, `db/social/`, `db/memory.py`, `db/world.py`, or `db/inventory.py` **must** be re-exported in `db/__init__.py` so `db.<fn>()` passes `tests/test_codebase_contracts.py`.
2. **Non-Blocking Async Access, Read Envelopes & Savepoint Safety**:
   - Inside `async def` functions (`api/`, `cogs/`, `services/`, `game_engine/turn/`), always execute blocking `db.*` calls via `await adb(...)` using coarse `db.ReadUnitOfWork()` (multi-read snapshots) or `db.UnitOfWork()` (multi-write mutations) closures rather than per-query event-loop hops. Only pure in-memory helpers listed in `db.PURE_IN_MEMORY_DB_HELPERS` may be called directly inside `async def` (enforced by `sync-db-in-async` in `scripts/static_check.py`).
   - Lazy schema helpers must guard repeated runs with `db.ensure_table_group_once()`.
   - Never call raw `conn.commit()` outside `db/core/` (would break active SQLite savepoints; enforced by `raw-conn-commit-outside-core`), and register every `session_id` table in `SCHEMA` inside `db/registry.py` (enforced by `unregistered-session-table`).

---

## 6. Mandatory Isolated Test Verification

Never let a test touch the live repository `hikayat.db`. Use the isolation pattern in the `hikayat-sim-and-test` skill (§4, "Isolate SQLite Paths") via `db.use_temporary_db()` / `db.set_db_path(...)` (or monkeypatching both `db.DB_PATH` and `db.core.DB_PATH`) before `db.init_db()`.

Copy-pasteable `SCHEMA`, `SCHEMA_MIGRATIONS`, and `SessionTableSpec` snippets live in `references/new_table_template.md`. Run both the table-wiring checker and contract suites before finishing:
```bash
python .agents/skills/hikayat-db-lifecycle-checklist/scripts/check_table_wiring.py
python scripts/run_tests.py agent tests/test_five_normalized_models_cutover.py tests/test_codebase_contracts.py
```

---

## 7. Common Mistakes & Red Flags
- **Fresh vs. migrated drift**: Editing `SCHEMA` in `db/core/schema.py` without an identical tuple in `SCHEMA_MIGRATIONS` (`db/core/migrations.py`) — or vice versa — fails `test_fresh_schema_matches_migrated_schema_parity`.
- **Running DDL inside `UnitOfWork`**: Invoking schema/table-rebuild helpers when `db.is_in_uow()` is `True` breaks active savepoint/transaction guarantees.
- **Inverted FK ordering**: Setting `purge_order` higher on children than parents or `load_tier` lower on children than parents causes FK failures (`purge` must delete children before parents, e.g. `20 < 80`; `load` must clone parents before children, e.g. `10 < 20`).
- **Naive session ID string replacement**: Using `.replace(str(old_sid), str(new_sid))` on composite key columns corrupts trailing digits when `old_session_id == 1`; declare `session_key_cols` in `db/registry.py` or use `_rewrite_session_key_id`.
- **Bypassing `adb(...)` or `db/core/`**: Calling blocking `db` helpers directly inside `async def`, importing `services/`/`api/`/`cogs/` from `db/`, or calling raw `conn.commit()` outside `db/core/` fails `scripts/static_check.py` and `tests/test_codebase_contracts.py`.
