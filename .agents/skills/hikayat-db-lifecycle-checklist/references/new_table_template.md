# New Table Lifecycle Blueprint (`db/`)

Copy and adapt these 4 blocks whenever adding a session-scoped SQLite table under `db/`. Run `python .agents/skills/hikayat-db-lifecycle-checklist/scripts/check_table_wiring.py <table_name>` afterward to confirm all touchpoints are wired.

---

## 1. Fresh DB Schema (`db/core/schema.py`)

Add both the `CREATE TABLE IF NOT EXISTS` statement and lookup index inside `SCHEMA`:

```sql
CREATE TABLE IF NOT EXISTS <table_name> (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL,
    turn_number     INTEGER NOT NULL DEFAULT 0,
    payload_json    TEXT NOT NULL DEFAULT '{}',
    created_at      REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_<table_name>_session_turn
    ON <table_name>(session_id, turn_number);
```

---

## 2. Versioned Schema Migration (`db/core/migrations.py`)

Append the next integer migration tuple to `SCHEMA_MIGRATIONS` using the **exact same DDL** as `SCHEMA` so `test_fresh_schema_matches_migrated_schema_parity` passes:

```python
(
    <NEXT_VERSION>,
    "add_<table_name>_table",
    [
        """CREATE TABLE IF NOT EXISTS <table_name> (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL,
            turn_number     INTEGER NOT NULL DEFAULT 0,
            payload_json    TEXT NOT NULL DEFAULT '{}',
            created_at      REAL NOT NULL DEFAULT 0
        )""",
        "CREATE INDEX IF NOT EXISTS idx_<table_name>_session_turn ON <table_name>(session_id, turn_number)",
    ],
),
```

- If a migration also backfills rows or alters constraints, call a helper in `db/core/migrations_backfills.py` and keep it idempotent.
- Never run DDL/migration rebuilds inside an active transaction (`if db.is_in_uow(): raise RuntimeError(...)`).

---

## 3. Declarative Registry (`db/registry.py` -> `SESSION_TABLE_REGISTRY`)

### Option A — Simple Turn-Indexed Table (`rollback_mode="delete_gt_turn"`)

```python
SessionTableSpec(
    name="<table_name>",
    purge_order=30,
    load_tier=30,
    rollback_mode="delete_gt_turn",
    rollback_turn_col="turn_number",
    rollback_result_key="<table_name>_deleted",
),
```

### Option B — Stateful Parent/Child Table (`rollback_mode="handler"`)

Note opposite FK ordering: **purge** deletes children before parents (`20 < 80`), while **load** clones parents before children (`10 < 20`).

```python
SessionTableSpec(
    name="<table_name>",
    purge_order=20,          # children delete BEFORE parents (e.g. households=80)
    load_tier=20,            # children insert AFTER parents (e.g. households=10)
    orig_id_alias="_orig_<entity>_id",
    char_id_policy="none",   # or: "always_host", "if_host_or_empty", "if_host_exact", "dossier_zero_default"
    session_key_cols=("<key_col>",),
    row_transform_hook=None, # optional key in db/saves.py _ROW_TRANSFORM_HOOKS
    post_load_hook=None,     # optional key in db/saves.py _POST_LOAD_HOOKS
    rollback_mode="handler",
    rollback_handler="db.sessions.rollback_session_normalized_state_after_turn",
),
```

---

## 4. Isolated Pytest Verification Skeleton

Always isolate SQLite paths with `db.use_temporary_db()` (or `db.set_db_path(...)`) and group multi-step reads/writes in `db.ReadUnitOfWork()` / `db.UnitOfWork()`:

```python
def test_<table_name>_lifecycle(tmp_path):
    with db.use_temporary_db(str(tmp_path / "case.db")):
        db.init_db()
        with db.UnitOfWork():
            ...
        with db.ReadUnitOfWork():
            ...
```
