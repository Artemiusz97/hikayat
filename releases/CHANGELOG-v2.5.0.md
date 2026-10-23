# Changelog — Hikayat v2.5.0

**Release Date:** 2026-10-23  
**Release Type:** MINOR (Deterministic State Engine Phases 1–5, Stealth & Infiltration Package, Tactical Action Dock & Quick Belt, Graph Pathfinding & Access Gating, CI Concurrency Hardening)  
**Package:** `hikayat-v2.5.0-clean.zip`

---

## 🌟 Most Recent Changes (v2.5.0 Highlights)

### 1. Deterministic State Separation & Anti-Hallucination Pipeline (Phases 1–5)
* **Problem:** In traditional LLM RPGs, language models frequently hallucinate stat changes, fabricate unearned inventory items, misunderstand conversational departures, or warp quest progress in ungrounded prose.
* **Feature:** Formally decoupled creative narration from authoritative game state through five deterministic phases:
  - **Phase 1: Cast & Dialogue Authority (`game_engine/npcs/cast_planner.py`)**: `CastPlanner` deterministically arbitrates scene attendance, active dialogue partners, bystanders, and departures. Dialogue exits immediately drop conversational state across all present NPCs, preventing phantom responses.
  - **Phase 2: Physical & Intimacy Milestones (`game_engine/state/reducers.py`, `mechanics/social/`)**: Metaphor Guard ensures metaphorical expressions (*"kiss of death"*, *"penetrate armor"*) never trigger physical milestones. Enforces directional inversion, check failure gates, and strict spectator target isolation.
  - **Phase 3: Vitals, Currency & Economy (`game_engine/state/core.py`, `mechanics/combat/`)**: Ungrounded items invented by the LLM in narrative outcomes are automatically intercepted and rejected. Merchant transactions, item durability, encumbrance limits, and gold balances are strictly code-authorized.
  - **Phase 4: Spatial Movement & Pathfinding (`mechanics/world/locations/pathfinding.py`)**: Multi-edge Dijkstra/BFS shortest-path traversal across SQLite world edges with 3-tier canonical hierarchy (`Zone ➔ Facility ➔ Room`), access key/lockpicking gates, fog of war, combat flee displacement, and transit fare gating.
  - **Phase 5: Quests & Story Progression (`game_engine/quests.py`)**: Deterministic pre-turn quest progression, clue deduplication, suspect evidence extraction upon defeat, and two-phase climax waypoint discovery.

### 2. Stealth & Infiltration Mechanics Package (`mechanics/stealth/`)
* **Problem:** Stealth in text RPGs is typically reduced to binary narrative checks without systemic escalation, lighting, or armor considerations.
* **Feature:** Comprehensive mathematical infiltration package:
  - **4-Stage Alert Tracker**: Models escalation through `UNAWARE` (0–25), `SUSPICIOUS` (26–60), `SEARCHING` (61–99), and `DETECTED` (100) with natural decay over unobserved turns.
  - **Acoustic & Environmental Modifiers**: Computes armor noise penalties, companion noise drag, action noise, and ambient lighting modifiers.
  - **Opposed Perception Checks**: Resolves opposed stealth checks deterministically against NPC perception and provides truth directives bounding narrative prose.
  - **Stealth Stance Toggle**: Allows players to enter or break stealth stances dynamically during exploration.

### 3. Tactical Action Dock & Quick Belt Hotbar (`web/src/components/`)
* **Problem:** Players frequently had to navigate through deep modal menus or type out text commands to use basic consumables, give gifts, or check stealth status.
* **Feature:** Enhanced the React Web SPA with dedicated fast-action controls:
  - **Tactical Action Dock (`TacticalActionDock.jsx`)**: Persistent sidebar dock featuring one-click stealth toggles, combat target selectors, quick phone access, and modal openers.
  - **Quick Belt Popover (`QuickBeltPopover.jsx`)**: Instant-access popover displaying belt potions, remedies, snacks, and consumables for immediate one-click usage.
  - **Give Gift Modal (`GiveGiftModal.jsx`)**: Contextual gift-giving interface filtering player inventory items with immediate affinity calculation and NPC preference tracking.
  - **Time Skip Modal (`TimeSkipModal.jsx`)**: Direct time advancement interface allowing players to wait or rest while triggering appropriate world schedule migrations.

### 4. CI Concurrency Hardening & xdist Database Isolation
* **Problem:** Running parallel test suites (`pytest -n auto`) in clean CI environments produced `sqlite3.IntegrityError: UNIQUE constraint failed: schema_migrations.version` and `sqlite3.OperationalError: database is locked` during test collection.
* **Fix:** 
  - Isolated worker SQLite databases at process import time in `tests/conftest.py` via `PYTEST_XDIST_WORKER`, ensuring complete database separation during the collection phase.
  - Removed top-level unconditional `db.init_db()` from `server.py` (initialization is safely handled by FastAPI's startup lifespan).
  - Configured `PRAGMA busy_timeout = 30000` immediately upon connection in `db/core.py` and converted migration tracking to `INSERT OR IGNORE INTO schema_migrations`.
  - Re-exported `generate_faction_bounty_board` in `game_engine/core.py` to satisfy AST codebase contracts.

---

### Clean Distribution Archive
* Created clean distribution package `releases/hikayat-v2.5.0-clean.zip` excluding development test suites (`tests/`), icon caches (`icon/`), runtime databases (`*.db`), log files (`*.log`), and process locks.
* Verified zero leaks of personal directories, tokens, or local environment paths.
