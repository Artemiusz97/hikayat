# Hikayat Engineering Invariants & Best Practices

These architectural contracts apply to **every** code change in Hikayat. They are enforced by `scripts/static_check.py` (crash-class & async/commit static bugs), `tests/test_codebase_contracts.py` (facade call resolution, layer boundaries, serialization, Pydantic dual-access), `tests/test_agent_docs_contracts.py` (agent docs cite only real files, skills, flags, and facade functions), and `scripts/package_release.py` (personal path scan). See §5 for commands.

## 1. Domain-Driven Modularity & Package Contracts
- **4-Layer Separation & Import Direction**:
  1. **Static Data & Catalogs** (`data/*.json`, `constants.py`, `catalog.py`, `prompts.py`, `keywords.py`)
  2. **Deterministic Mechanics & State Machines** (`mechanics/<domain>/`)
  3. **Persistence & Turn Orchestration** (`db/<domain>.py`, `game_engine/`, `services/turn_service.py`)
  4. **Delivery Adapters** (`api/`, `cogs/`, `web/src/`)
  Never mix static lookup catalogs, raw SQLite queries, deterministic state transitions, and LLM prompt formatting in one file. `db/` must never import `services/`, `api/`, or `cogs/`, and `mechanics/` must never add new imports of delivery frameworks (`discord`, `fastapi`, `cogs`, `api`) — enforced by `tests/test_codebase_contracts.py`.
- **Cohesive Single-Window Modules**: Target ~300–800 lines for logic modules organized around one domain responsibility (pure static data/catalog/locale files are exempt; treat ~1,500+ lines in a logic module as a refactor trigger when responsibilities mix). Decompose by lifecycle role (`constants.py`, `repository.py`, `resolver.py`, `formatting.py`) rather than arbitrary byte caps or `import *` dumps.
- **AST Call Resolution & Facade Contract**: Every `db.<fn>()`, `game_engine.<fn>()`, `llm_client.<fn>()`, and `self.cog.<fn>()` call across the repository **must** resolve to a real callable exported at the package root (`db/__init__.py`, `game_engine/__init__.py`, `llm_client/__init__.py`, or `AdventureCog` mixins). Never add or move a function in a submodule without explicitly re-exporting it at the package root, and preserve live mutable `_http_client` / `_embed_http_client` / `_nsfw_http_client` proxy bindings in `llm_client/__init__.py` so `tests/conftest.py` network blocking remains active.

## 2. Type Safety, Serialization & Schema Contracts
- **Explicit Typing & Annotations**: Include `from __future__ import annotations` and explicit `typing` imports in Python modules so static checks and pytest collection never fail with `NameError`.
- **No Shadowing Local Imports or Branch-Only Bindings**: Never re-import a module-level name inside a function (`import db` / `import json` deep in a function makes that name local to the *whole* function → `UnboundLocalError` on earlier lines). Initialize any variable read after an `if`/`try` block *before* that block. `scripts/static_check.py` enforces both.
- **`CheckResult` JSON Safety**: `skill_check.CheckResult` is a dataclass and fails raw `json.dumps()`. Always pass action dicts through `api/deps.py` (`serializable_action()`; `server._serializable_action` is kept as a compatibility alias) before JSON or WebSocket serialization.
- **Pydantic Dual-Access & Defensive Coercion**: LLM schemas in `models/llm_schemas.py` (`TurnOutcome`, `OpeningScene`, `ActionClassification`, `Choice`) must support **both** attribute (`obj.field`) and dict (`obj["field"]`, `obj.get()`) access, and gracefully coerce empty strings `""`, `None`, or malformed outputs returned by local/open-weights models.

## 3. Database, Concurrency & Test Isolation
- **Never Mutate Live `hikayat.db` in Tests**: Always isolate tests and simulators via `db.use_temporary_db()` / `db.set_db_path(...)` (which resets pooled connections and updates `db.DB_PATH`, `db.core.DB_PATH`, and `config.DB_PATH` atomically) or `db.isolate_simulation_db()`, with guaranteed teardown restoration.
- **Async DB Execution, Transactions & Query Hygiene**: Inside `async def` routes, cogs, and `TurnService`, run synchronous SQLite calls through `await adb(...)` using coarse `db.ReadUnitOfWork()` / `db.UnitOfWork()` closures (`scripts/static_check.py` enforces `sync-db-in-async` and `raw-conn-commit-outside-core`). Keep multi-step writes and turn rollbacks in one `db.UnitOfWork()` (never run schema/DDL rebuilds when `db.is_in_uow()` is true), respect `distributed_session_lock` / `distributed_user_lock`, and avoid N+1 `await adb(...)` loops when state is already in memory.
- **Normalized Table Lifecycle Parity**: Any new or modified session-scoped table in `db/` must be registered in `db/registry.py` and wired into save/load slot remapping (`db/saves.py`), turn rollback (`db/sessions.py`), child-record purge (`db/core/lifecycle.py`), and idempotent schema migration (`db.init_db()`). See the `hikayat-db-lifecycle-checklist` skill.

## 4. Headless Omnichannel Parity, Security & Prose Guardrails
- **Deterministic Single Source of Truth**: Resolve all game mechanics deterministically in `services/turn_service.py`, `game_engine/`, and `mechanics/` with idempotent retry handling. Never fork core game rules exclusively inside Discord `cogs/` or FastAPI `api/`.
- **FastAPI Auth & Scope Boundaries (`api/security.py`)**: Session-scoped routes must verify `verify_session_participant`, user-scoped routes must verify `verify_user_access`, and privileged/debug routes must gate on `is_strict_auth_context(request)` rather than `is_share_mode_active()`.
- **5-Language Locale Parity**: Keep every user-visible UI string and localized keyword table synchronized across all 5 languages (`en`, `pl`, `ms`, `de`, `zh`) in both `localization/{en,pl,ms,zh,de}.py` and `web/src/locales/{en,pl,ms,de,zh}.json`.
- **Zero Stat Leakage in Prose**: Raw HP/MP integers, dice percentages, DC numbers, and internal enum/JSON tags (`[ITEM_JSON]`, `[GEAR_JSON]`, `[SPELLBOOK_JSON]`) must **never** leak into player-facing narrative prose.
- **Zero Personal Path Leaks**: Never hardcode machine-local user home paths or usernames in tracked files, comments, or skills. `scripts/package_release.py` scans all candidate text files and aborts on personal path tokens.

## 5. Verification & the Local-Only Test Suite
- **Local-Only Tooling & Venv**: `tests/`, `pytest.ini`, `scripts/run_tests.py`, `scripts/simulate_*.py`, and `.desloppify/` exist in the working tree but are **gitignored** (kept out of the public repo). Use them freely, never `git add -f` or commit them, and run Python commands through the repo virtualenv (`venv/Scripts/python.exe` on Windows, `venv/bin/python` on POSIX).
- **After any Python edit**: `python scripts/static_check.py --changed` must report 0 new findings (keep `scripts/static_baseline.json` at `0`). Full scan: `python scripts/static_check.py`. Install the commit gate once with `python scripts/static_check.py --install-hook`.
- **After any `web/src/` edit**: Run `npm run lint` and `npm run build` in `web/` (`0` ESLint errors/warnings) and commit rebuilt `web/dist/` (`server.py` serves `web/dist/` directly).
- **Strict mode is on by default** in pytest and the fuzz simulators (`tests/strict_mode.py`): a test fails if its code path *swallowed* a `NameError`, `UnboundLocalError`, or an `ImportError` of a Hikayat module inside an `except` block. Fix the bug; don't widen the `except`. `HIKAYAT_STRICT=0` disables, `HIKAYAT_STRICT=2` also reports `TypeError`/`AttributeError`.
- **After structural or `db/` edits**: `python scripts/run_tests.py agent tests/test_codebase_contracts.py tests/test_five_normalized_models_cutover.py`
- **After editing `AGENTS.md` or `.agents/`**: `python scripts/run_tests.py agent tests/test_agent_docs_contracts.py`
- **Before a release**: `python scripts/package_release.py --dry-run`

## 6. Domain Skill Routing (Read Before Editing)
| Touching | Skill |
| :--- | :--- |
| `db/` schemas, migrations, saves, rollbacks | `hikayat-db-lifecycle-checklist` |
| `services/turn_service.py`, `game_engine/turn/`, 5 normalized models | `hikayat-turn-and-social-engine` |
| `llm_client/`, `game_engine/prompts.py`, `game_engine/choices_cleaner/`, `image_client.py` | `hikayat-llm-prose-and-prompts` |
| `api/`, `cogs/`, `web/src/` (REST/WS protocol, SPA UI, Discord parity) | `hikayat-omnichannel-ui` |
| `data/*.json`, scenarios, items, spells, `localization/`, `web/src/locales/` | `hikayat-scenario-and-content` |
| Pytest presets, 6 fuzz simulators, seed replay, release packaging | `hikayat-sim-and-test` |
| Splitting >800L Python/React modules, package barrels, layer inversions | `hikayat-refactoring-playbook` |
