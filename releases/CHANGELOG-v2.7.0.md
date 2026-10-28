# Hikayat Release Changelog — v2.7.0

**Release Date:** 2026-10-28  
**Type:** Minor Release  
**Milestone:** Cast Contract Authority, Dynamic Scenery & Atmospheric Lighting, Investigatory Spatial Immunity, Romance Intent Auto-Injection, Clean Headless Pruning & Production Release

---

## 🌟 Overview

Hikayat **v2.7.0** introduces critical narrative rendering and social orchestration enhancements: Cast Contract Authority ensuring deterministic cast presence and protagonist uniqueness, Dynamic Scenery and Atmospheric Lighting injection grounded in world state and time-of-day, Investigatory Action Spatial Immunity preventing movement penalties during in-scene inspection, Romance Intent Auto-Injection at high affinity milestones, Culture-Aware Genealogy Sibling Extraction, and complete production repository pruning with zero personal info leaks and untracked test suites.

---

## 🚀 Key Implementations & Enhancements

### 1. Cast Contract Authority & Protagonist Title Guardrails
- **Deterministic Single Source of Truth**: Enforces rigid cast presence validation across `TurnService` and `CastPlanner`. Eliminates phantom duplicates and ensures the protagonist's name, class, and titles never collide with ambient or named NPCs.
- **Protagonist Presence Validation**: Hardens protagonist title and epithet handling in dialogue and narrative generation, preventing internal enum leakage or duplicate character rendering.

### 2. Dynamic Scenery, Weather & Atmospheric Lighting Injection
- **Atmospheric Visuals**: Injects real-time lighting (dawn, noon, dusk, twilight, starlight, storm illumination) into scene generation based on current time-of-day and weather simulation.
- **Narrative Ambient Anchoring**: Synchronizes narrative descriptive prose with physical world lighting and environmental conditions without breaking conversational pacing.

### 3. Investigatory Action Spatial Immunity
- **In-Scene Examination Without Displacement**: Refactored `mechanics/world/locations.py` and `TurnService` so that investigative, analytical, search, or perception actions within a scene maintain full spatial continuity without triggering waypoint transitions or travel stamina penalties.
- **Contextual Clue Board Synchronization**: Seamlessly connects investigative actions with the clue and caseboard engines while preserving current local coordinates.

### 4. Romance Intent Dedicated Choice Auto-Injection
- **Milestone Choice Guarantee**: Auto-injects dedicated confession, romantic escalation, and milestone dialogue choices in `mechanics/social/relationships.py` when relationship affinity thresholds are reached, ensuring high-stakes social interactions are always accessible to the player.
- **Agency Preservation**: Balances automatic choice injection with standard navigational and tactical choices, guaranteeing player agency is never restricted.

### 5. Culture-Aware Genealogy & Directory Sibling Extraction
- **Surname & Heritage Consistency**: Refactored genealogy generation in `mechanics/social/genealogy.py` and `namegen.py` to correctly preserve culture-specific naming conventions, maiden names, and maternal lineage across family trees.
- **Campus & Town Directory Integration**: Guaranteed bidirectional consistency between household sibling records and active campus/town student directories.

### 6. Concurrency & Foreign Key Safe Household Lifecycle
- **Database Cascade Resilience**: Hardened `db/households.py` against race conditions during concurrent session creation and deletion, ordering foreign key unlinking before table cleanup.
- **Multi-Worker Isolation**: Verified complete transactional safety under multi-threaded and asynchronous SQLite access patterns.

### 7. Clean Headless Distribution & Privacy Sanitization
- **Repository Optimization**: Pruned development test suites (`tests/`), test runner scripts, and CI workflows from git tracking to deliver a lean, production-ready headless distribution.
- **Zero Personal Path Leakage**: Verified complete absence of local machine paths, usernames, or internal tokens across all tracked files.
- **Dual Backup Guarantee**: Fully preserved the entire development history, test suites, and simulators on remote branch `origin/backup/v2.7.0`, tag `v2.7.0-full`, and local archive `backups/hikayat-v2.6.0-tests-backup.zip`.

---

## 📦 Distribution Packages
- **Clean Production Archive**: `releases/hikayat-v2.7.0-clean.zip` (Clean production deployment: 0 tests, 0 icon files, 0 database files, 0 personal leaks).
- **Full Development Backup**: Branch `backup/v2.7.0` & Tag `v2.7.0-full` (Preserving 100% of tests, fixtures, and simulators).
