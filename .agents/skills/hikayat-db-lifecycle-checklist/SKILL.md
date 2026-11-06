---
name: hikayat-db-lifecycle-checklist
description: "Use this skill whenever adding or modifying SQLite tables, columns, indexes, migrations, save/load slots, turn rollbacks, or db.* functions in Hikayat's persistence layer (db/)."
---

# Hikayat SQLite Schema, Migration & Session Lifecycle Checklist

Whenever you add or alter any table, column, or query helper under `db/`, complete **all 6 lifecycle steps** below so save/load slots, turn rollbacks, AST contracts, and parallel tests never drift.

---

## 1. Schema Definition & Idempotent Migration (`db/core.py`)

1. **Fresh DB Schema**: Add new tables (`CREATE TABLE IF NOT EXISTS ...`) or columns directly to `SCHEMA` in `db/core.py`.
2. **Existing DB Migration**: Write an idempotent migration helper (inspecting `PRAGMA table_info(<table>)` before `ALTER TABLE` or backfilling rows inside a `with get_conn() as conn:` transaction) and invoke it inside `init_db()`.
3. **Indexes**: Add `CREATE INDEX IF NOT EXISTS idx_<table>_<cols>` for all `(session_id, ...)` and `(character_id, ...)` lookup paths to avoid full-table scans.

---

## 2. Session Child Table Purge Wiring (`db/core.py`)

If the table is scoped to an adventure session (`session_id` column):
- Add the exact table name to the `SESSION_CHILD_TABLES` tuple in `db/core.py`.
- Confirm `_delete_session_child_records_only(conn, session_id)` and `_delete_session_records(conn, session_id)` cleanly delete rows without foreign-key ordering errors.

---

## 3. Save & Load Slot Cloning (`db/saves.py`)

1. **Snapshot Capture (`save_adventure_slot`)**:
   - Tables in `SESSION_CHILD_TABLES` are automatically iterated and serialized (`id` stripped).
   - If another table references this table's autoincrement `id` (like `households.id`, `contacts.id`, `commitments_ledger.id`, `session_clues.id`), stash `rd["_orig_<entity>_id"] = rd.get("id")` before `rd.pop("id", None)`.
2. **Slot Restoration (`load_adventure_slot`)**:
   - Remap `row_dict["session_id"] = new_session_id` (and `character_id = char_id` where present).
   - Remap any cross-table integer foreign keys using an `orig_id -> new_id` dictionary populated in parent-first order.
   - **Embedded Session Key Rule**: If any string key column embeds the session ID (e.g., `hh_<sid>_...`, `rv_<sid>_...`), rewrite it with `_rewrite_session_key_id(key_str, old_session_id, new_session_id)`—never use naive `.replace(str(old_sid), str(new_sid))`, which corrupts trailing digits when `old_session_id == 1`.

---

## 4. Turn Rollback & Turn 0 Opening Retry (`db/sessions.py`)

1. **Mid-Session Turn Rollback (`rollback_session_normalized_state_after_turn`)**:
   - If the table records turn-stamped events or edges (`turn_number` / `turn_created`), delete or revert rows where `turn > turn_number` inside the single atomic `with get_conn() as conn:` block and re-materialize any cached summary JSON (such as `contacts.relations_json`).
2. **Turn 0 Opening Retry (`reset_session_for_opening_retry`)**:
   - Ensure any new session-level state columns on `sessions` or keys in `sessions.extra_json` are reset cleanly while keeping character starter gear intact.

---

## 5. Facade Re-Exports & Async Concurrency Hygiene

1. **Package Root Facade (`db/__init__.py`)**:
   - Every new public function added to `db/core.py`, `db/sessions.py`, `db/saves.py`, `db/social.py`, `db/memory.py`, `db/world.py`, or `db/inventory.py` **must** be re-exported in `db/__init__.py` so `db.<fn>()` passes `tests/test_codebase_contracts.py`.
2. **Non-Blocking Async Access**:
   - Inside `async def` functions (`api/`, `cogs/`, `services/turn_service.py`, `game_engine/`), always execute synchronous SQLite helpers via `await adb(db.<fn>, ...)`.
   - Batch lookups outside loops instead of issuing sequential `await adb(...)` calls per NPC or per party member.

---

## 6. Mandatory Isolated Test Verification

Never let a test touch the live repository `hikayat.db`. Use the isolation fixture pattern in the `hikayat-sim-and-test` skill (§3, "Isolate SQLite Paths"), which redirects **both** `db.DB_PATH` and `db.core.DB_PATH` before `db.init_db()`.

Run both contract and normalized-lifecycle suites before finishing:
```bash
python scripts/run_tests.py agent tests/test_five_normalized_models_cutover.py tests/test_codebase_contracts.py
```
