# Hikayat Release Changelog — v2.8.0

**Release Date:** 2026-11-06  
**Type:** Minor Release  
**Milestone:** Folklore Codex, World Pulse Background Simulation, Multi-Engine Quest Architecture, Forensic Dossiers, and Awakened Resonance

---

## 🌟 Overview

Hikayat **v2.8.0** introduces major world simulation and narrative intelligence systems: the **Folklore Codex** for occult research and bestiary knowledge, the autonomous **World Pulse** simulation for dynamic background events and faction crises, the **Multi-Engine Quest Architecture** with structured forensic dossiers and campaign spines, **Awakened Resonance** elemental combat mechanics, expanded **Procedural Anomaly Engines**, and updated web and Discord interfaces with full omnichannel parity.

---

## 🚀 Key Implementations & Enhancements

### 1. Folklore Codex & Occult Research Engine
- **Structured Myth & Bestiary Database**: Added `data/folklore_codex.json` alongside deterministic mechanics in `mechanics/world/folklore_codex.py` and `mechanics/world/folklore_mechanics.py`.
- **In-Game Encyclopedia**: Implemented the `EncyclopediaSubTab.jsx` component in the Web UI, allowing players to research folklore, decipher occult weaknesses, and unlock concrete tactical advantages against supernatural entities.

### 2. World Pulse & Background Event Simulation
- **Autonomous Regional Events**: Implemented `mechanics/world/world_events/`, `data/world_events_catalog.json`, `db/world_events.py`, and `api/world_events.py` to simulate rumors, crises, scandals, faction skirmishes, and seasonal festivals across map zones independently of player turns.
- **Omnichannel Interfaces**: Added interactive Discord select menus (`cogs/adventure/views/world_pulse.py`, `world_pulse_mixin.py`) and a dedicated Web UI tab (`WorldPulseLoreSubTab.jsx`) with real-time escalation tracking and countdown timers.

### 3. Multi-Engine Quest Architecture & Forensic Dossiers
- **Specialized Quest Engines**: Replaced generic quest prompts with dedicated operational engines (Investigation, Bounty, Social Infiltration, Survival) in `mechanics/narrative/quest_engines.py` and `data/quest_engines_catalog.json`.
- **Intelligence Dossier Compiler**: Added `mechanics/narrative/dossier_compiler.py` and `db/dossiers.py` to track suspect motives, witness testimony, verifiable evidence, and sub-objectives in relational SQLite tables.
- **Campaign Spine Framework**: Added `mechanics/narrative/campaign_spine.py` to coordinate overarching story arcs across procedural chapters without losing track of unresolved leads.

### 4. Awakened Resonance & Combat Overdrive
- **Attunement Mechanics**: Added `mechanics/combat/awakened_resonance.py` and `mechanics/combat/spells/awakened_kits.py`, introducing elemental resonance, combat stances, and tiered spell overcharging.

### 5. Origin Modes & Specialized Roster Tags
- **Character Backgrounds**: Added `mechanics/social/origin_mode.py` and `mechanics/social/roster_tags.py` to govern initial social standing, starting affiliations, and dialogue predispositions across diverse scenarios.

### 6. Procedural Anomaly Engine Expansion
- **Spatial Rifts & Distortion Pools**: Implemented `mechanics/world/anomaly_engine.py` with expanded procedural pools in `data/anomaly_procedural_pools.json`, generating anomalous artifacts, environmental hazards, and reality distortions.

### 7. Memory Tokenization & Context Budgeting
- **Token-Aware Compaction**: Added `mechanics/system/memory/tokenization.py` to calculate exact token budgets and compact long campaign histories into digestible bullet points without losing factual anchors.

### 8. Web UI Enhancements & Theme System
- **Updated Interfaces**: Refactored `ActionPanel.jsx`, `QuestLogPanel.jsx`, `CodexPanel.jsx`, and `EmbarkationModal.jsx` for improved responsiveness and keyboard navigation.
- **Visual Branding**: Added high-resolution vector favicons (`web/public/`, `web/dist/`) and expanded theme options in `web/src/theme/themes.js`.

---

## 📦 Distribution Packages
- **Clean Production Archive**: `releases/hikayat-v2.8.0-clean.zip` (Clean production deployment: 0 tests, 0 icon files, 0 runtime images, 0 databases, 0 personal leaks).
- **Full Development Backup**: Branch `backup/v2.8.0` & Tag `v2.8.0-full` (Preserving 100% of test suites, test runners, and simulation harnesses).
