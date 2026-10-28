# Hikayat Engineering Invariants & Best Practices

These architectural contracts apply to **every** code change in Hikayat and are statically verified by `tests/test_codebase_contracts.py` and `scripts/package_release.py`.

## 1. Domain-Driven Modularity & Package Contracts
- **4-Layer Separation of Concerns**: Keep clear boundaries between:
  1. **Static Data & Catalogs** (`data/*.json`, `constants.py`, `catalog.py`, `prompts.py`, `keywords.py`)
  2. **Deterministic Mechanics & State Machines** (`mechanics/<domain>/`)
  3. **Persistence & Turn Orchestration** (`db/<domain>.py`, `game_engine/`, `services/turn_service.py`)
  4. **Delivery Adapters** (`api/`, `cogs/`, `web/src/`)
  Never mix large static lookup tables/regex catalogs, raw SQLite queries, deterministic state transitions, and LLM prompt formatting inside a single monolithic file.
- **Cohesive Single-Window Modules**: Organize code around a single domain responsibility (~300–800 lines) so modules remain readable in a single pass. When a domain grows, decompose by lifecycle role (`constants.py`, `repository.py`, `resolver.py`, `formatting.py`) rather than arbitrary byte caps or `import *` dumps.
- **AST Call Resolution & Facade Contract**: Every `db.<fn>()`, `game_engine.<fn>()`, `llm_client.<fn>()`, and `self.cog.<fn>()` call across the repository **must** resolve to a real callable exported at the package root (`db/__init__.py`, `game_engine/__init__.py`, or `AdventureCog` mixins). Never add or move a function in a submodule without explicitly re-exporting it at the package root.

## 2. Type Safety, Serialization & Schema Contracts
- **Explicit Typing & Annotations**: Include `from __future__ import annotations` and explicit `typing` imports in Python modules so static checks and pytest collection never fail with `NameError`.
- **`CheckResult` JSON Safety**: `skill_check.CheckResult` is a dataclass and fails raw `json.dumps()`. Always pass action dicts through `server._serializable_action()` before JSON or WebSocket serialization.
- **Pydantic Dual-Access & Defensive Coercion**: LLM schemas in `models/llm_schemas.py` (`TurnOutcome`, `OpeningScene`, `ActionClassification`, `Choice`) must support **both** attribute (`obj.field`) and dict (`obj["field"]`, `obj.get()`) access, and gracefully coerce empty strings `""`, `None`, or malformed outputs returned by local/open-weights models.

## 3. Database, Concurrency & Test Isolation
- **Never Mutate Live `hikayat.db` in Tests**: In pytest fixtures and `unittest` suites, always redirect **both** `db.DB_PATH` and `db.core.DB_PATH` to an isolated temporary SQLite file (restoring on teardown), or call `db.isolate_simulation_db()` in simulators.
- **Async DB Execution & Query Hygiene**: Inside `async def` routes, cogs, and `TurnService`, run synchronous SQLite calls through `await adb(db.<fn>, ...)`, respect `distributed_session_lock` / `distributed_user_lock`, and avoid redundant N+1 `await adb(...)` round-trips inside loops when state is already in memory.
- **Normalized Table Lifecycle Parity**: Any new or modified session-scoped table in `db/` must be wired into save/load slot remapping (`db/saves.py`), turn rollback (`db/sessions.py`), child-record purge (`db/core.py`), and idempotent schema migration (`db.init_db()`).

## 4. Headless Omnichannel Parity & Prose Guardrails
- **Deterministic Single Source of Truth**: Resolve all game mechanics deterministically in `services/turn_service.py`, `game_engine/`, and `mechanics/` with idempotent retry handling. Never fork core game rules exclusively inside Discord `cogs/` or FastAPI `api/`.
- **Zero Stat Leakage in Prose**: Raw HP/MP integers, dice percentages, DC numbers, and internal enum/JSON tags (`[ITEM_JSON]`, `[GEAR_JSON]`, `[SPELLBOOK_JSON]`) must **never** leak into player-facing narrative prose.
- **Zero Personal Path Leaks**: Never hardcode machine-local user home paths or usernames in tracked files, comments, or skills. `scripts/package_release.py` scans all candidate text files and aborts on personal path tokens.
