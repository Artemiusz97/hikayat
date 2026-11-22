# Hikayat Release Changelog — v3.6.0

**Release Date:** 2026-11-22  
**Type:** Minor Release  
**Milestone:** Core Monolith Package Decompositions (`db/core/`, `db/social/`, `api/adventure/`, `services/turn/`, `game_engine/turn/`), Persistence SQL Purity, Expanded Python & ESLint Quality Gates, and Concurrency/Audit Hardening

---

## 🌟 Overview

Hikayat **v3.6.0** completes a comprehensive architectural decomposition and reliability hardening pass across the persistence layer, turn orchestration pipeline, FastAPI routes, Discord cogs, and React SPA. Monolithic multi-thousand-line modules (`db/core.py`, `db/social.py`, `api/adventure.py`, `services/turn_service.py`, and `game_engine/turn/core.py`) are extracted into cohesive, single-responsibility packages backed by lossless submodule proxies (`db/core/module_proxy.py`), strict raw-SQL repository boundaries, expanded static bug gates paired with ESLint 9 (`web/eslint.config.js`), and hardened async/WebSocket concurrency guarantees.

---

## 🚀 Key Implementations & Enhancements

### 1. Core Monolith-to-Package Decompositions (`db/core/`, `db/social/`, `api/adventure/`, `services/turn/`, `game_engine/turn/`)
- **`db/core/` Package (`connection.py`, `lifecycle.py`, `migrations.py`, `migrations_backfills.py`, `module_proxy.py`, `schema.py`)**: Extracted the 4,378-line persistence core into focused lifecycle modules with a lossless `_SubmoduleProxyModule` (`install_submodule_proxy`, `unwrap_callable_target`, `callable_accepts_kwarg`) preserving monkeypatch and dynamic reload semantics across package facades.
- **`db/social/` Package & `db/world_constants.py` (`contacts_enrichment.py`, `contacts_repo.py`, `cooldowns.py`, `households_factions.py`, `phone_commitments.py`, `rosters_snapshots.py`)**: Replaced the 4,363-line social monolith with domain-scoped repositories and cleaned explicit package-root exports in `db/__init__.py`.
- **`services/turn/` Package (`embark.py`, `models.py`, `prepare.py`, `resolve.py`)**: Extracted turn preparation, execution, and embarkation workflows out of the 4,009-line `services/turn_service.py` while keeping `services/turn_service.py` as a lightweight compatibility facade.
- **`game_engine/turn/` Decomposition (`pre_turn.py`, `post_turn.py`, `encounter_narrative.py`, `prompt_assembly.py`, `phase_state.py`)**: Split `game_engine/turn/core.py` into typed stage handoffs (`PreTurnState`, `PromptAssemblyState` in `game_engine/turn/phase_state.py`) and dedicated phase runners.
- **`api/adventure/` Package (`enrichment.py`, `in_flight.py`, `locations.py`, `routes_session.py`, `routes_turn.py`)**: Modularized the 3,122-line FastAPI adventure router into cohesive endpoint, enrichment, location, and in-flight tracking modules.

### 2. Expanded Static Analysis Gate & React ESLint Integration (`scripts/static_check.py`, `web/eslint.config.js`)
- **Expanded Python Static Bug Gate (`scripts/static_check.py`)**: Added unused-import, shadowed-import, and package-facade signature checks on top of flow-sensitive unbound-local, async-DB-call, and session-registry gates.
- **Flat-Config ESLint 9 for React SPA (`web/eslint.config.js`, `web/package.json`)**: Integrated ESLint with `eslint-plugin-react` and `eslint-plugin-react-hooks` (`rules-of-hooks`, `exhaustive-deps`) via `npm run lint`, resolving unused variables and hook dependency findings across `web/src/`.

### 3. Persistence SQL Purity, Shim Retirement & Transaction Hardening (`db/`, `api/`, `services/`, `config.py`)
- **Raw SQL Boundary Enforcement**: Migrated remaining raw SQLite queries out of `api/` and `services/` into `db/` repository functions, consolidated duplicate helpers, and retired obsolete post-v37 compatibility shims.
- **Database & Boot Integrity**: Fixed phantom roster SQL queries, hardened `v53` save migration backfills, eliminated redundant N+1 DB round-trips inside turn/roster loops, restored Turn-0 opening parity, and introduced deferred runtime config validation (`validate_runtime_config` + `HIKAYAT_TEST_MODE` isolation in `config.py`).

### 4. Concurrency, Async DB Offloading, Proxy & WebSocket/SPA Race Hardening (`c88d806`, `ed49614`, `e68c274`)
- **Backend Async & Pooling Audit**: Offloaded synchronous SQLite work off asyncio event loops across `api/`, `cogs/`, `services/`, and `mechanics/system/` (`memory/`, `phone/`), hardened `ReadUnitOfWork` pooling, and tightened `db/registry.py` and `services/crash_capture.py` reliability.
- **SPA & WebSocket Race Fixes (`web/src/hooks/`, `web/src/components/`)**: Resolved race conditions in `useAuth.js`, `useGameSession.js`, `useSettings.js`, `ActionPanel.jsx`, `EmbarkationModal.jsx`, and `PhoneModal.jsx`, and rebuilt production assets into `web/dist/`.

### 5. Clean Release Packaging Refinement (`scripts/package_release.py`)
- **Portable Release Archives**: Updated `collect_release_files` in `scripts/package_release.py` to include `bin/tunnel.py` while excluding `.exe` executables (`bin/cloudflared.exe`) and `.testmon*` artifacts, ensuring clean cross-platform distribution.

---

## 📦 Distribution Packages
- **Clean Production Archive**: `releases/hikayat-v3.6.0-clean.zip` (Clean production deployment: 0 tests, 0 icon files, 0 runtime images, 0 user custom fonts, 0 `.exe` binaries, 0 databases, 0 personal leaks).
- **Full Development Backup**: Branch `backup/v3.6.0` & Tag `v3.6.0-full` (Preserving tracked source snapshot cleanly alongside local `backups/hikayat-v3.6.0-tests-backup.zip`).
