# Changelog — Hikayat v2.0.0

**Release Date:** 2026-09-30  
**Release Type:** MAJOR (Modern Modular Architecture, React Web Application, Decoupled API & Services, 3-Track Intimacy Consolidation, and Test Suite Modernization)  
**Package:** `hikayat_v2.0.0.zip`

---

## 🌟 Most Recent Changes (v2.0.0 Highlights)

### 1. Modern Modular Architecture Overhaul (Waves 1–9)
* **Problem:** Monolithic architecture files (`game_engine.py`, `db.py`, `server.py`) had grown exceedingly complex, coupling UI presentation, game loop execution, database queries, and LLM prompt assembly into single scripts.
* **Feature:** Deconstructed and re-architected Hikayat into clean, domain-driven modular packages:
  - **`api/`**: Modular FastAPI controllers (`adventure.py`, `auth_characters.py`, `codex_phone.py`, `deps.py`, `inventory_merchant.py`, `settings_ws.py`).
  - **`services/`**: Decoupled `turn_service.py` providing a standalone game loop and turn engine accessible by both Discord bot and Web API.
  - **`game_engine/`**: Reorganized into `state/` (state reducers and state machines) and `turn/` (core turn execution and prompt assembly).
  - **`db/`**: Modularized SQLite data access across `core.py`, `social.py`, `world.py`, `inventory.py`, and `characters.py`.
  - **`models/`**: Centralized Pydantic schemas for LLM inputs/outputs and live entity trackers (`llm_schemas.py`, `trackers.py`).
  - **`mechanics/memory/`**: Contextual token memory budget manager, memory compaction, and vector retrieval (`budget.py`, `compaction.py`, `vector.py`).

### 2. Modern React Web Application (`frontend/src/`)
* **Problem:** The original web interface was a minimal prototype with limited interactivity that did not reflect the advanced combat, phone, codex, and party systems available in the backend.
* **Feature:** Built a modern single-page React frontend in `frontend/src/`:
  - **Tactical Battle Deck (`ActionPanel.jsx`)**: Interactive combat action cards with dynamic enemy target switching and success odds.
  - **Interactive Story Feed (`StoryFeed.jsx`, `HistoryCard.jsx`)**: Renders scenes, active monster cards, conversation lock states, outcome summaries, and skill check roll badges.
  - **Live Party Widget (`PartyWidget.jsx`)**: Companion vitals (HP/MP) with 3 quick-interaction shortcuts for NPC party members.
  - **In-Game Smartphone (`PhoneModal.jsx`)**: Full smartphone modal supporting 6-intent direct messaging, e-shop purchases, and photo vault filters.
  - **Codex & Quest Log (`CodexPanel.jsx`, `QuestLogPanel.jsx`)**: 3-tab contact sub-switcher, faction perks and bounties, campaign milestones, climax-ready indicators, and waypoint leads.
  - **State Hooks**: Custom hooks (`useAuth`, `useGameSession`, `useCodex`, `useInventory`, `usePhone`, `useSettings`) managing live state via REST and WebSockets.

### 3. Thematic Starting Equipment & Loadout Generation
* **Problem:** Regerating starting equipment often produced mismatched items that contradicted the player character's chosen class and scenario setting.
* **Feature:** Hardened starter gear generation in `cogs/adventure/views/` and `game_engine/` to strictly align generated armor, weapons, and accessories with character class archetypes, race, and scenario themes.

### 4. Schema Modernization & 3-Track Intimacy Consolidation
* **Problem:** Residual legacy fields in `SCENE_SCHEMA` and `OUTCOME_SCHEMA` still referenced obsolete binary virginity flags, causing occasional prompt confusion and state desynchronization.
* **Feature:** Excised all deprecated binary virginity fields from LLM schemas in favor of the unified 3-track intimate experience system (Vaginal, Oral, Manual) in `mechanics/persona.py`, with relationship Disclosure Level 3 gating.

### 5. Architectural Contracts & Test Suite Modernization
* **Problem:** Test suites had accumulated broken assertions following the Fallout: New Vegas Damage Threshold (DT) and Damage Resistance (DR) migration.
* **Feature:**
  - Modernized the test runner with `pytest.ini` markers and centralized fixtures in `tests/conftest.py`.
  - Added architectural invariant test suites (`test_codebase_contracts.py`, `test_mathematical_invariants.py`, `test_turn_service.py`, `test_web_api.py`).
  - Updated all combat and equipment test assertions to validate DT/DR formulas and modular item properties.

---

## 🏷️ Version System Specification

Hikayat adheres to [Semantic Versioning (SemVer 2.0.0)](https://semver.org/spec/v2.0.0.html):
- **MAJOR (X.0.0):** Architectural overhauls, database engine changes, major operational paradigm transitions.
- **MINOR (X.Y.0):** Substantial new features, new command suites, platform expansions, pipeline subsystems.
- **PATCH (X.Y.Z):** Backwards-compatible bug fixes, timeout protections, platform scraper adjustments, edge-case handling.

---

## 📊 Version History Summary

| Version | Release Date | Type | Primary Milestone / Theme |
| :--- | :--- | :--- | :--- |
| **v2.0.0** | 2026-09-30 | **MAJOR** | Modern Modular Architecture, React Web Application, Decoupled API & Services, 3-Track Intimacy Consolidation. |
| **v1.8.1** | 2026-09-16 | Patch | Narrative Style Supremacy, Dynamic Paragraph Quotas, Equipment Slot Archetype Hardening & Loadout Isolation. |
| **v1.8.0** | 2026-09-15 | Minor | Modular Items & FNV Armor DT, 5-Tier Enemy Hierarchy, SQLite WAL Backend. |
| **v1.7.0** | 2026-09-06 | Minor | Action Intents, Quest UI & Model Headroom Safeguards. |
| **v1.6.0** | 2026-09-01 | Minor | Living World, Time Engine & Intimate Overhaul. |
| **v1.5.2** | 2026-08-20 | Patch | Biome Diversity, Fail-Forward & Map Polish. |
| **v1.5.1** | 2026-08-14 | Minor | Tactical Combat, Loadouts & Factions Overhaul. |
| **v1.4.0** | 2026-08-05 | Minor | Quest Log, Bounty Board & 10-Chapter Campaign. |
| **v1.3.0** | 2026-08-03 | Minor | Dynamic NSFW Routing & Fallback Cascade. |
| **v1.2.0** | 2026-08-03 | Minor | Locations, Debug Suite & Roster Expansion. |
| **v1.1.0** | 2026-08-01 | Patch | LLM Reliability & Narrative Balancing. |
| **v1.0.0** | 2026-07-25 | **MAJOR** | Genesis Release: Core RPG Engine, Discord Bot, FastAPI Web UI & Audio Engine. |
