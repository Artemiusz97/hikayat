# Changelog — Hikayat v2.2.0

**Release Date:** 2026-10-12  
**Release Type:** MINOR (Deterministic Affinity Engine, In-Game Smartphone Narrative Bridge, Engine Auditor, Equipment Expansion & Web UI Overhaul)  
**Package:** `hikayat-v2.2.0-clean.zip`

---

## 🌟 Most Recent Changes (v2.2.0 Highlights)

### 1. Deterministic Affinity Engine (`mechanics/social/affinity_engine.py`)
* **Problem:** Social interactions and disposition shifts previously depended entirely on unstructured narrative descriptions, occasionally leading to inconsistent character attitudes across sessions.
* **Feature:** Introduced a deterministic mathematical affinity engine calculating social dynamics, NPC disposition tiers, and interpersonal standing:
  - Tracks evolving relationship stages with nuanced behavioral triggers and emotional thresholds.
  - Implements multi-dimensional affinity scaling influenced by player choices, dialogue tone, and past historical interactions.
  - Provides strict state safeguards ensuring narrative outcomes align with established relationship parameters.

### 2. In-Game Smartphone Narrative Bridge & Direct Messaging (`mechanics/system/phone/`)
* **Problem:** Smartphone messaging was isolated from main adventure turns, creating a narrative disconnect between real-time text threads and world events.
* **Feature:** Unified smartphone systems with the core game loop:
  - **Narrative Memory Bridge (`dm_grounding.py`)**: Direct messages and text conversations now ground themselves in active quest progress, recent location visits, and party events.
  - **Player-Initiated Direct Messaging (`player_dm.py`)**: Enables players to proactively text any discovered NPC with context-aware responses and daily interaction allowances.
  - **Media Gallery & Photo Captions (`media_captions.py`)**: Dynamic visual attachments and contextual photo descriptions linked to character encounters.
  - **Expanded Phone UI (`PhoneModal.jsx`)**: Overhauled full-screen modal with contact browsing, message threads, delivery shop, and localized feed scouring.

### 3. Runtime Engine Auditor & Matching Architecture (`game_engine/auditor.py`, `matching.py`)
* **Problem:** LLM-generated turns occasionally referenced non-existent entities or attempted contradictory state transitions during complex multi-NPC encounters.
* **Feature:** Built an automated runtime auditing pipeline:
  - **Turn Auditor (`auditor.py`)**: Verifies state consistency, choice plausibility, and entity references before final turn outcomes are dispatched to clients.
  - **Fuzzy Entity Matching (`matching.py`)**: Robust entity and keyword resolution preventing duplicate NPC records and ensuring continuous character identity preservation.
  - **Collective Entity Isolation**: Prevents crowd entities and ambient bystander groups from corrupting persistent individual lorebook entries.

### 4. Massive Equipment & Weapon Arsenal Expansion (`mechanics/combat/items/`)
* **Problem:** Equipment tables lacked diverse weapon archetypes and varied wearable apparel across distinct campaign settings.
* **Feature:** Comprehensive overhaul and expansion of equipment data:
  - **Weapon Expansion (`weapons.py`)**: Over 2,000 lines of specialized weaponry across historical, fantasy, sci-fi, and modern archetypes with distinct damage multiplier scalers.
  - **Apparel & Wearables Expansion (`clothing.py`, `accessories.py`)**: Vastly broadened wardrobe selections, undergarments, footwear, headwear, and protective layering.
  - **Genre-Aware Consumables (`data/genres.json`)**: Dynamic loot tables and restorative consumables tailored to specific world scenarios.

### 5. Nuanced Intimacy & Affection Dynamics (`mechanics/social/persona/intimacy/`)
* **Problem:** Intimate relationship progression required deeper sensory pacing, emotional boundary modeling, and progressive state escalation.
* **Feature:** Sanitized and hardened mature social systems:
  - **Dynamic Excitement Meter (`intimate_excitement.py`)**: Context-aware excitement and arousal tracking reflecting emotional connection, physical pacing, and mutual attraction.
  - **Sensory & Tactile Narrative Fidelity**: Refined narrative directives emphasizing character intimacy, physical state transitions, and emotional resonance without crude or abrupt exposition.
  - **Boundary & Preference Gating**: Comprehensive individual preferences, boundaries, and emotional disclosure safeguards.

### 6. Modern Web SPA Enhancements (`web/src/`)
* **Problem:** Web UI lacked dedicated visual feedback for combat outcome logs, updated codex entries, and deep character sheet inspection.
* **Feature:** Overhauled frontend components:
  - **Turn Outcome Panel (`TurnOutcomePanel.jsx`)**: Rich post-action breakdown highlighting rolls, damage mitigation, and quest notifications.
  - **Codex & Profile Redesign (`CodexPanel.jsx`)**: Deep character profiles, relationship trackers, faction statuses, and physical inspection tabs.
  - **Character Sheet Modernization (`CharacterSheet.jsx`)**: Clear SPECIAL stat visualizations, inventory equipment slots, and active conditions.
  - **Pre-Built Production Assets**: Newly bundled distribution in `web/dist/` for instantaneous deployment.

### 7. Simulation Framework & Automated Test Suites (`scripts/`, `tests/simulators/`)
* **Problem:** Verifying multi-turn balance across navigation, social banter, and tactical combat required manual playthroughs.
* **Feature:** Added automated simulation harness (`simulate_combat.py`, `simulate_narrative.py`, `simulate_navigation.py`, `simulate_social.py`) and over 20 new comprehensive contract test suites.

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
| **v2.2.0** | 2026-10-12 | Minor | Deterministic Affinity Engine, In-Game Smartphone Narrative Bridge, Engine Auditor, Equipment Expansion & Web UI Overhaul. |
| **v2.1.0** | 2026-10-04 | Minor | Mechanics Domain Restructuring, Unified Web Frontend Architecture, Root Declutter, and Distribution Hardening. |
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
