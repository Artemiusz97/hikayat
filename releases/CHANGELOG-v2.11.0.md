# Hikayat Release Changelog — v2.11.0

**Release Date:** 2026-11-13  
**Type:** Minor Release  
**Milestone:** Modular Combat Engine Decomposition, Chapter Plan & Clue Progression, 6-Segment Threat Clock, Quest Agency Overhaul, and 5-Language Parity

---

## 🌟 Overview

Hikayat **v2.11.0** represents a comprehensive gameplay mechanics and architectural upgrade. It decomposes the massive combat engine into single-responsibility modules (`damage`, `precompute`, `reconcile`, `status_effects`, `types`), introduces the **Chapter Plan** procedural clue pipeline for story quests and mystery bounties, implements a tabletop-inspired **6-Segment Threat Clock** that advances dynamically with in-game time, significantly expands the **Multi-Engine Quest & Dossier System**, and synchronizes 5-language localization across both Python backends and the React frontend.

---

## 🚀 Key Implementations & Enhancements

### 1. Combat Engine Domain Decomposition (`mechanics/combat/`)
- **Single-Responsibility Architecture**: Decomposed the monolithic `mechanics/combat/core.py` into dedicated submodules:
  - `damage.py`: Fallout-style damage reduction, damage thresholds (DT), critical strike multipliers, and weapon damage scaling.
  - `precompute.py`: Enemy intent calculation, turn initiative sequencing, and telegraphed combat forecasting.
  - `reconcile.py`: Post-turn outcome reconciliation, HP/MP synchronization, XP/loot distribution, and defeat/flee handling.
  - `status_effects.py`: Tick-based condition processing, elemental burns, stuns, bleeds, and awakened resonance interactions.
  - `types.py`: Strongly typed data models and phase contexts eliminating dictionary key guessing.

### 2. Chapter Plan & Clue-Based Progression (`mechanics/narrative/chapter_plan.py`)
- **Structured Clue Progression**: Added `ChapterPlan` in `models/llm_schemas.py` and procedural generation in `chapter_plan.py` for Story Quests and clue-eligible bounty engines (`MYSTERY_CASE`, `SOCIAL_BROKERAGE`).
- **5-Locale Clue Prose & Discovery**: Generates localized discovery verbs and narrative snippets across English, Polish, Malay, German, and Simplified Chinese without stat leaks or format drift.
- **Anti-Leak Defense**: Strict regex sanitizers verify clue descriptions never expose raw damage numbers, DC stats, or JSON control tags.

### 3. 6-Segment Threat Clock Countdown (`mechanics/narrative/threat_clock.py`)
- **Tabletop Doom Countdown**: Implemented a 6-segment Threat Clock for Chapters 1–10 story campaigns.
- **Circadian Integration**: Clocks tick forward every 4 in-game hours (240 minutes), escalating regional danger, increasing adversary aggression, and pushing storyline crises if neglected.
- **UI Parity**: Integrated visual Threat Clock meters into `cogs/adventure/embeds.py` on Discord and `QuestLogPanel.jsx` on the Web UI.

### 4. Multi-Engine Quest Agency & Dossier Expansion (`game_engine/quests.py`, `mechanics/narrative/dossier_compiler.py`)
- **Expanded Quest Engine Catalog**: Added over 1,400 lines of operational templates and lead resolution mechanics in `data/quest_engines_catalog.json`.
- **Forensic Dossier Compiler**: Enhanced `dossier_compiler.py` with multi-step witness interviews, physical evidence tracking, and case conclusion state transitions in SQLite.
- **Turn Resolver Upgrades**: Streamlined `quest_turn_resolver.py` and `quest_lifecycle.py` for atomic quest advancement during exploration and dialogue turns.

### 5. 5-Language Localization Sync & Frontend Upgrades
- **Backend & Frontend Translation Parity**: Synchronized all new quest engine terms, threat clock states, and combat condition strings across Python (`localization/*.py`) and React (`web/src/locales/*.json`).
- **UI Ergonomics**: Updated `ActionPanel.jsx`, `CodexPanel.jsx`, `ContactsPanel.jsx`, and `QuestLogPanel.jsx` with enhanced status meters, clean location badges, and responsive action layouts.
- **Compiled Production Bundle**: Built clean Vite distribution assets (`dist/assets/index-DinMBlv-.css`, `dist/assets/index-C94Dvpsg.js`).

---

## 📦 Distribution Packages
- **Clean Production Archive**: `releases/hikayat-v2.11.0-clean.zip` (Clean production deployment: 378 clean files, 0 tests, 0 icon files, 0 runtime images, 0 databases, 0 personal leaks).
- **Full Development Backup**: Branch `backup/v2.11.0` & Tag `v2.11.0-full` (Preserving 100% of test suites, test runners, and simulation harnesses).
