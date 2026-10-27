# Changelog — Hikayat v2.6.0

**Release Date:** 2026-10-27  
**Release Type:** MINOR (Five Normalized World Models, Anomalous Incursions, Stealth Escalation, Town & Campus Rosters, Web Contacts & Theme Dock, Test Concurrency Hardening)  
**Package:** `hikayat-v2.6.0-clean.zip`

---

## 🌟 Most Recent Changes (v2.6.0 Highlights)

### 1. Five Normalized World Models Cutover (`tests/test_five_normalized_models_cutover.py`)
* **Problem:** In previous versions, relational and stateful world entities (family lineages, intimate history, dynamic promises, social ties, and garment/physical state) were stored in fragmented JSON blobs across contact and session records, risking state desynchronization and difficult migrations.
* **Feature:** Formally implemented and cut over to the **Five Normalized Models Architecture**:
  - **Model 1: Household & Genealogy (`households` table, `father_json`, `mother_json`, `narrative_siblings_json`)**: Normalized familial lineage linking characters to structured households with maiden name inheritance, sibling trees, and occupation matrices.
  - **Model 2: Intimacy Ledger (`intimate_events` table)**: Fine-grained, transactional intimacy ledger tracking event timestamps, act types, consent grounding, origin markers (`past_history` vs. `live_turn`), and memory grounding without stat leakage into prose.
  - **Model 3: Social & Relationship Graph (`social_persons`, `social_ties`, `npc_ties`)**: Fully normalized social network graph modeling exclusive partnerships, secret affairs, rivalries, mentorships, and familial ties with bidirectional query authority (`get_current_partner`, `get_secret_affairs`, `get_ex_partners`).
  - **Model 4: Commitments & Dynamic Schedules (`commitments` table)**: Normalized appointment and rendezvous tracker with multi-stage verification, custom cancellation guards, arrival tracking, and stale appointment cleanup.
  - **Model 5: Actor Physical State & Garments (`physical_state_json`)**: 6-slot garment layer system (outer, top, bottom, undergarment, footwear, headwear) coupled with stamina, fatigue, excitement meters, and posture tracking.

### 2. Anomalous Incursions & Reality Distortion Mechanics
* **Feature:** Integrated high-concept anomalous mechanics across tactical and social pipelines:
  - **Anomalous Gear & Artifacts (`mechanics/combat/items/anomalous_gear.py`)**: Exotic equipment carrying specialized passive traits, reality distortion multipliers, and containment requirements.
  - **Anomalous World Events (`mechanics/world/anomalous_events.py`)**: Spatially bounded reality anomalies, extraction gates, and story arc bounties with confiscation merchant protocols.
  - **Anomalous NPC Tags & Roster (`mechanics/social/anomalous_npc_tags.py`, `mechanics/social/agent_roster.py`)**: Entity classification flags allowing narrative grounding for paranormal, dimensional, and covert agent encounters.

### 3. Stealth & Infiltration Escalation Simulation
* **Problem:** Stealth gameplay required deeper AI response dynamics when guards investigate distractions or search perimeters.
* **Feature:** Added the **Stealth Escalation System (`mechanics/stealth/escalation.py`)**:
  - Models realistic guard awareness shifts, patrol reinforcements, search radius expansions, and combat escalation when alarm thresholds are breached.
  - Deterministic stealth fuzz simulator (`tests/simulators/stealth/`, `scripts/simulate_stealth.py`) running automated Monte Carlo sweeps verifying detection curves across diverse loadouts and noise profiles.

### 4. Town & Campus Rosters, Part-Time Shifts & Discreet Encounters
* **Feature:** Expanded non-combat and contemporary life simulation:
  - **Town & Campus Rosters (`mechanics/social/town_roster.py`)**: Populates living towns with working professionals, shopkeepers, service workers, and classmates.
  - **Part-Time Shifts & Curfew Yielding**: Students and working NPCs adhere to shift schedules, curfew cutoffs, and conflict-resolution rules when social events overlap with work commitments.
  - **Discreet Encounters (`mechanics/social/discreet_encounters.py`)**: Multi-stage private interactions handling co-location, secret affair discovery, witness rumors, and emotional confrontation resolution.

### 5. Web SPA Omnichannel Modernization & UI Parity
* **Feature:** Major frontend enhancements in the React 18 Web Application (`web/src/`):
  - **Contacts Panel (`web/src/components/Sidebar/ContactsPanel.jsx`)**: Dedicated sidebar panel with live entity search, affinity meters, track badges (platonic, romantic, rivalry), and one-click smartphone DM shortcuts.
  - **Theme Switcher & Anchored Popovers (`web/src/components/Common/ThemeSwitcher.jsx`, `web/src/theme/`, `AnchoredPopover.jsx`)**: Instant runtime theme switching supporting dark, high-contrast, fantasy parchment, and sci-fi aesthetic palettes.
  - **Game Menu & Quick Navigation (`web/src/components/Common/GameMenu.jsx`)**: Streamlined navigation deck providing centralized access to character sheet, world map, saves, and codex panels.
  - **5-Language Localization (`web/src/locales/`)**: Synchronized new UI components and game terms across English (`en`), Polish (`pl`), Malay (`ms`), German (`de`), and Simplified Chinese (`zh`).

### 6. Parallel Test Hardening & Concurrency Isolation
* **Problem:** High-concurrency test runs with `pytest-xdist` on multi-core runners experienced foreign key integrity failures in household concurrency tests and session variable shadowing in romance intent tests.
* **Fix:**
  - **Foreign Key Deletion Order**: Fixed `tests/test_household_concurrency.py` to unlink and delete dependent `contacts` records before deleting `households` rows, eliminating `sqlite3.IntegrityError: FOREIGN KEY constraint failed`.
  - **Romance Intent Variable Shadowing**: Refactored `can_trigger_romantic_confession` in `mechanics/social/relationships.py` to prevent parameter shadowing of `session_id`, and updated `tests/test_romance_intent_engine.py` with unique randomized session/user IDs.
  - **Culture-Aware Sibling Extraction**: Updated genealogy sibling checks in `tests/test_school_social_systems_integration.py` to use `genealogy.extract_surname_and_firstname()` instead of naive whitespace splitting, properly supporting East Asian surname-first nomenclature.

---

### Clean Distribution Archive
* Created clean distribution package `releases/hikayat-v2.6.0-clean.zip` excluding development test suites (`tests/`), icon caches (`icon/`), runtime databases (`*.db`), log files (`*.log`), and process locks.
* Verified zero leaks of personal directories, machine usernames, or local environment paths via automated release audit.
