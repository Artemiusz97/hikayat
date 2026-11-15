# Hikayat Release Changelog — v2.12.0

**Release Date:** 2026-11-14  
**Type:** Minor Release  
**Milestone:** Full Combat Submodule Extraction, Boss Telegraph Sanitization & Stagger Meters, Deterministic Crash Replay & LLM Tapes, Cancellation-Shielded Rollback, and Web/Bot Parity

---

## 🌟 Overview

Hikayat **v2.12.0** deepens engine reliability, combat modularity, and deterministic observability. It extracts combat turn resolution into focused domain submodules (`ally_turn`, `enemy_turn`, `player_turn`, `player_spells`, `enemy_profiles`, `loadouts`, `post_combat`, `targeting`), introduces a qualitative **Boss Stagger Meter** (`stagger_pct`) while stripping raw interrupt HP internals from client payloads, hardens `TurnService` against async cancellation during turn failures, and adds **ContextVar LLM Tape Recording & Crash Replay Bundles** (`services/crash_capture.py`) with automatic machine-path scrubbing.

---

## 🚀 Key Implementations & Enhancements

### 1. Combat Phase Submodule Extraction (`mechanics/combat/`)
- **Cohesive Turn Handlers**: Extracted turn execution and resolution pipelines out of `precompute.py`, `reconcile.py`, and `enemies.py` into focused, single-purpose submodules:
  - `player_turn.py` & `player_spells.py`: Player attack, defend, skill, and spell resolution chains.
  - `ally_turn.py` & `loadouts.py`: Party companion AI combat turns and automatic combatant loadout initialization (`ensure_combatant_loadout`).
  - `enemy_turn.py` & `enemy_profiles.py`: Adversary combat turn logic and creature archetype stat/ability definitions.
  - `targeting.py` & `post_combat.py`: Target prioritization, AoE scoping, and post-battle resolution hooks.

### 2. Enemy & Boss Telegraph Sanitization + Stagger Meter (`api/adventure.py`, `web/`)
- **Zero Stat Leak Telegraphing**: Added `_sanitize_enemy_telegraph_view` to scrub internal `interrupt_threshold` and `accumulated_interrupt_damage` integers from `nearby_enemies` and `combat_boss_telegraph` payloads.
- **Qualitative Stagger UI**: Exposes a clamped percentage (`stagger_pct`) so Web and Discord UIs render enemy interrupt progress clearly without leaking underlying math.

### 3. Deterministic Crash Capture & LLM Tape Replay (`services/crash_capture.py`, `llm_client.py`)
- **ContextVar LLM Recording & Interception**: Added `use_llm_handler` and `record_llm_tape` in `llm_client.py` to capture ordered JSON, text, and embedding calls with zero global state pollution.
- **Portable Crash Bundles**: Added opt-in `services/crash_capture.py` (`HIKAYAT_CRASH_CAPTURE=1`) producing pre-turn SQLite snapshots and sanitized `repro.json` replay bundles that automatically strip local filesystem paths and usernames.

### 4. Cancellation-Shielded Rollback & State Atomicity (`services/turn_service.py`)
- **Shielded Error Recovery**: Wrapped `_rollback_turn_failure` calls inside `asyncio.shield` so cancelled tasks cannot interrupt database state restoration.
- **Extended Rollback Scope**: Added deterministic restoration of `combat_threat_ledger`, `combat_boss_telegraph`, `party_npcs`, and per-character `status_effects` upon failed or aborted turns.
- **Circuit Breaker Precision**: `llm_client.py` now trips model circuit breakers strictly when retried attempts (`retries > 0`) exhaust.

### 5. Frontend, Discord & 5-Language Parity
- **UI Refinements**: Updated `CharacterSheet.jsx`, `PartyWidget.jsx`, `QuestLogPanel.jsx`, `StoryFeed.jsx`, and `ActionPanel.jsx` alongside Discord `cogs/adventure/embeds.py` and `views/quests.py`.
- **Locale & Bundle Sync**: Synchronized 5-language strings across `localization/*.py` and `web/src/locales/*.json`, with compiled Vite distribution assets (`index-BAcdG7_s.js`, `index-h3KvT_y1.css`).

---

## 📦 Distribution Packages
- **Clean Production Archive**: `releases/hikayat-v2.12.0-clean.zip` (Clean production deployment: 0 tests, 0 icon files, 0 runtime images, 0 databases, 0 personal leaks).
- **Full Development Backup**: Branch `backup/v2.12.0` & Tag `v2.12.0-full` (Preserving 100% of test suites, test runners, and simulation harnesses).
