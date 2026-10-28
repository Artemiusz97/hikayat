# Changelog

All notable changes to **Hikayat** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning (SemVer 2.0.0)](https://semver.org/spec/v2.0.0.html).

---

## 🏷️ Version System Specification

Hikayat uses the standard **Semantic Versioning 2.0.0** scheme (`MAJOR.MINOR.PATCH`):

| Level | Identifier | Trigger Criteria | Examples |
| :--- | :--- | :--- | :--- |
| **MAJOR** | `X.0.0` | Architectural overhauls, database engine changes, incompatible configuration breaks, major operational paradigm transitions. | Genesis release with core RPG engine, SQLite schema, Discord bot & FastAPI web app (`v1.0.0`). |
| **MINOR** | `X.Y.0` | Substantial new gameplay mechanics, new systems/commands suites, platform expansions, content frameworks introduced backwards-compatibly. | Locations tree & debug suite (`v1.2.0`), NSFW routing cascade (`v1.3.0`), 10-Chapter Campaign & Quests (`v1.4.0`), Tactical Combat & Factions (`v1.5.1`), Living World & Time Engine (`v1.6.0`), Action Intents & Quest UI (`v1.7.0`), Modular Items & FNV Armor DT & 5-Tier Enemies (`v1.8.0`). |
| **PATCH** | `X.Y.Z` | Backwards-compatible bug fixes, prompt tuning & instruction supremacy, edge-case handling, gear slot hardening, performance optimizations. | LLM Reliability & Semaphore limits (`v1.1.0`), Biome Diversity & Fail-Forward Polish (`v1.5.2`), Narrative Style Supremacy & Equipment Slot Hardening (`v1.8.1`). |

---

## 📊 Version History Summary

| Version | Release Date | Type | Primary Milestone / Theme |
| :--- | :--- | :--- | :--- |
| **v2.7.0** | 2026-10-28 | Minor | Cast Contract Authority, Dynamic Scenery & Lighting, Investigatory Spatial Immunity, Romance Choice Auto-Injection, Clean Headless Pruning & Production Release. |
| **v2.6.0** | 2026-10-27 | Minor | Five Normalized World Models, Anomalous Incursions, Stealth Escalation, Town & Campus Rosters, Web Contacts & Theme Dock, Test Concurrency Hardening. |
| **v2.5.0** | 2026-10-23 | Minor | Deterministic State Engine Phases 1–5, Stealth & Infiltration Package, Tactical Action Dock & Quick Belt, Graph Pathfinding & Access Gating, CI Concurrency Hardening. |
| **v2.4.0** | 2026-10-21 | Minor | SDXL Scene Image Generation, Living Scene Stage Manager, World Schedules, Spatial Graph & Dijkstra Navigation, Commitments Engine, Intimacy Ledger & 5-Language Localization. |
| **v2.3.0** | 2026-10-13 | Minor | Multi-Language Localization, NPC Gender & Pronoun Consistency, Combat Stance & Affinity Synergy, Sub-Facility Waypoints, Web UI Internationalization. |
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

---

## Release Details

### [v2.7.0] - 2026-10-28

#### Added & Enhanced
- **Cast Contract Authority & Protagonist Title Guardrails**:
  - Enforced rigid cast presence validation across `TurnService` and `CastPlanner`.
  - Guaranteed zero collision between protagonist titles/epithets and NPC presence in narrative dialogue.
- **Dynamic Scenery, Weather & Atmospheric Lighting Injection**:
  - Dynamic daylight, weather, and ambient light rendering injected into narrative generation and UI.
  - Pacing-safe ambient anchoring connecting scene generation with physical world state.
- **Investigatory Action Spatial Immunity**:
  - Examination and search actions maintain complete spatial continuity without triggering waypoint transitions or travel penalties.
- **Romance Intent Dedicated Choice Auto-Injection**:
  - Automatic injection of critical romantic milestone choices at high affinity thresholds without overriding player agency.
- **Culture-Aware Genealogy & Directory Sibling Extraction**:
  - Culture-specific surname inheritance and family tree consistency across Japanese, Canid, Felid, and standard rosters.
- **Household Concurrency & Foreign Key Resilience**:
  - Race-condition resilience during concurrent household table creation and cascade deletion.
- **Clean Headless Release & Zero Privacy Leaks**:
  - Test suites, test runners, and dev configurations untracked from git for lean production release.
  - Zero personal path tokens, local directory references, or machine usernames across the repository.

### [v2.6.0] - 2026-10-27

#### Added & Enhanced
- **Five Normalized World Models Cutover (`tests/test_five_normalized_models_cutover.py`)**:
  - **Model 1: Household & Genealogy (`households` table)**: Structured household units with mother/father matrices, sibling links, maiden names, and occupation profiles.
  - **Model 2: Intimacy Ledger (`intimate_events` table)**: Transactional intimacy history tracking timestamps, consent, and memory anchors with zero prose stat leakage.
  - **Model 3: Social & Relationship Graph (`social_persons`, `social_ties`, `npc_ties`)**: Multi-edge relationship network resolving partners, secret affairs, rivalries, and mentorships.
  - **Model 4: Commitments & Dynamic Schedules (`commitments` table)**: Persistent appointments, rendezvous arrival verification, and stale cleanup.
  - **Model 5: Actor Physical State & Garments (`physical_state_json`)**: 6-slot garment layers, stamina, fatigue, excitement meters, and posture tracking.
- **Anomalous Incursions & Reality Distortion Mechanics**:
  - Anomalous gear, weapons, and accessories with reality distortion multipliers (`mechanics/combat/items/anomalous_gear.py`).
  - Spatially bounded anomalous incursions, extraction gates, and story arc bounties with confiscation merchant protocols (`mechanics/world/anomalous_events.py`).
  - Specialized anomalous tags and covert agent roster resolution (`mechanics/social/agent_roster.py`).
- **Stealth Escalation & Infiltration System (`mechanics/stealth/escalation.py`)**:
  - Dynamic AI awareness shifts, patrol reinforcements, search pattern expansions, and combat escalation.
  - Deterministic Monte Carlo stealth fuzz simulator (`tests/simulators/stealth/`, `scripts/simulate_stealth.py`).
- **Town & Campus Rosters, Part-Time Shifts & Discreet Encounters**:
  - Comprehensive town resident schedules and facility presence (`mechanics/social/town_roster.py`).
  - Student and worker part-time shifts with curfew cutoffs and conflict resolution.
  - Discreet encounter mechanics resolving secret affair discovery, witness rumors, and emotional confrontations.
- **Web SPA Omnichannel Modernization**:
  - **Contacts Panel (`web/src/components/Sidebar/ContactsPanel.jsx`)**: Filterable directory with live search, tier badges, and phone shortcuts.
  - **Theme Switcher (`web/src/components/Common/ThemeSwitcher.jsx`, `web/src/theme/`)**: Instant visual palette switching (dark, parchment fantasy, sci-fi).
  - **Game Menu & Anchored Popovers (`AnchoredPopover.jsx`, `GameMenu.jsx`)**: Clean navigation and quick belt hotbars.
  - Full 5-language localization alignment across all new components (`web/src/locales/`).
- **Parallel Test Hardening & Concurrency Isolation**:
  - Resolved foreign key constraint race condition in `tests/test_household_concurrency.py` by ensuring dependent contacts are unlinked before household deletions.
  - Eliminated variable shadowing of `session_id` in `can_trigger_romantic_confession` (`mechanics/social/relationships.py`).
  - Culture-aware East Asian surname-first extraction in `tests/test_school_social_systems_integration.py`.

### [v2.5.0] - 2026-10-23

#### Added & Enhanced
- **Deterministic State Engine Architecture (Phases 1–5)**:
  - **Phase 1: Cast & Dialogue Authority (`game_engine/npcs/cast_planner.py`)**: `CastPlanner` deterministically arbitrates scene attendance, active dialogue partners, bystanders, and departures. Dialogue exits immediately drop conversational state across all present NPCs, preventing phantom responses.
  - **Phase 2: Physical & Intimacy Milestones (`game_engine/state/reducers.py`, `mechanics/social/`)**: Metaphor Guard ensures metaphorical expressions (*"kiss of death"*, *"penetrate armor"*) never trigger physical milestones. Enforces directional inversion, check failure gates, and strict spectator target isolation.
  - **Phase 3: Vitals, Currency & Economy (`game_engine/state/core.py`, `mechanics/combat/`)**: Ungrounded items invented by the LLM in narrative outcomes are automatically intercepted and rejected. Merchant transactions, item durability, encumbrance limits, and gold balances are strictly code-authorized.
  - **Phase 4: Spatial Movement & Pathfinding (`mechanics/world/locations/pathfinding.py`)**: Multi-edge Dijkstra/BFS shortest-path traversal across SQLite world edges with 3-tier canonical hierarchy (`Zone ➔ Facility ➔ Room`), access key/lockpicking gates, fog of war, combat flee displacement, and transit fare gating.
  - **Phase 5: Quests & Story Progression (`game_engine/quests.py`)**: Deterministic pre-turn quest progression, clue deduplication, suspect evidence extraction upon defeat, and two-phase climax waypoint discovery.
- **Stealth & Infiltration Mechanics Package (`mechanics/stealth/`)**:
  - **4-Stage Alert Tracker**: Models escalation through `UNAWARE` (0–25), `SUSPICIOUS` (26–60), `SEARCHING` (61–99), and `DETECTED` (100) with natural decay over unobserved turns.
  - **Acoustic & Environmental Modifiers**: Computes armor noise penalties, companion noise drag, action noise, and ambient lighting modifiers.
  - **Opposed Perception Checks**: Resolves opposed stealth checks deterministically against NPC perception and provides truth directives bounding narrative prose.
  - **Stealth Stance Toggle**: Allows players to enter or break stealth stances dynamically during exploration.
- **Tactical Action Dock & Quick Belt Hotbar (`web/src/components/`)**:
  - **Tactical Action Dock (`TacticalActionDock.jsx`)**: Persistent sidebar dock featuring one-click stealth toggles, combat target selectors, quick phone access, and modal openers.
  - **Quick Belt Popover (`QuickBeltPopover.jsx`)**: Instant-access popover displaying belt potions, remedies, snacks, and consumables for immediate one-click usage.
  - **Give Gift Modal (`GiveGiftModal.jsx`)**: Contextual gift-giving interface filtering player inventory items with immediate affinity calculation and NPC preference tracking.
  - **Time Skip Modal (`TimeSkipModal.jsx`)**: Direct time advancement interface allowing players to wait or rest while triggering appropriate world schedule migrations.
- **CI Concurrency Hardening & xdist Database Isolation**:
  - Isolated worker SQLite databases at process import time in `tests/conftest.py` via `PYTEST_XDIST_WORKER`, ensuring complete database separation during the collection phase.
  - Removed top-level unconditional `db.init_db()` from `server.py` (initialization is safely handled by FastAPI's startup lifespan).
  - Configured `PRAGMA busy_timeout = 30000` immediately upon connection in `db/core.py` and converted migration tracking to `INSERT OR IGNORE INTO schema_migrations`.
  - Re-exported `generate_faction_bounty_board` in `game_engine/core.py` to satisfy AST codebase contracts.

### [v2.4.0] - 2026-10-21

#### Added & Enhanced
- **SDXL Scene Image Generation & Local Media Persistence (mechanics/media/, services/image_service.py, pi/)**:
  - Local-first SDXL scene rendering engine synthesizing environment, lighting, character framing, and artistic atmosphere tokens directly from narrative prose.
  - Negative prompt conditioning and aesthetic genre presets eliminating visual artifacts.
  - Local disk persistence with content-hash deduplication and high-performance static asset streaming (/api/media/{hash}.png).
  - In-game Smartphone photo vault and media gallery integration with persistent captions.
- **Pre-Turn Stage Manager & Living Scene NPC Presence Arbitration (mechanics/world/stage_manager.py, game_engine/turn/)**:
  - Deterministic living scene orchestrator tracking NPC spatial presence (*Present in Scene*, *Nearby in Facility*, *Off-Site*).
  - Dynamic arrival and departure arbitration preventing phantom dialogue from distant characters.
  - Ambient crowd separation isolating transient background murmurs from persistent codex and directory characters.
- **World Routine & Dynamic NPC Schedules Engine (mechanics/world/schedules.py, mechanics/world/locations/)**:
  - Time-of-day activity matrices cycling characters through 8 distinct daily routine phases.
  - Behavioral scheduling reflecting character club, grade, role, and personality disposition.
  - Proactive rendezvous tracking allowing NPCs to travel and arrive on schedule for player appointments.
- **Spatial Graph Architecture, Dijkstra Navigation & Access Gates (mechanics/world/locations/spatial_graph.py, mechanics/world/locations/movement.py)**:
  - Formally modeled bidirectional spatial graph with Dijkstra shortest-path pathfinding and travel distance calculations.
  - Sub-facility waypoint preservation maintaining granular 3-tier precision (*Zone ➔ Facility ➔ Sub-Facility*).
  - Access control gates restricting unauthorized passage into private staff offices or restricted campus facilities.
- **Commitments, Promises & Scheduled Rendezvous Engine (mechanics/system/commitments_engine.py)**:
  - Centralized commitments ledger tracking player promises, deadlines, and social rendezvous across SQLite tables.
  - Multi-state lifecycle tracking (scheduled, 
eminder_sent, rrived, ulfilled, roken, xpired) with dynamic social consequences.
- **Intimacy Ledger & Normalized Relationship Graph (mechanics/social/relationship_graph.py, mechanics/social/persona/intimacy/ledger.py)**:
  - Physical intimacy ledger tracking intimate milestones and disclosure gating with immutable physical safeguard invariants.
  - Normalized relationship graph (social_ties, social_persons) tracking directed and mutual ties (dating, affairs, friendships, rivalries).
  - Automatic write-through materialization to legacy relations dictionaries for full web UI backward compatibility.
- **5-Language Internationalization Expansion (localization/, web/src/locales/)**:
  - Comprehensive 5-language localization across backend and frontend: English (n), Polish (pl), Malay (ms), German (de), and Simplified Chinese (zh).
  - Localized item lemmas, unicode icons, combat actions, dialogue intents, and UI interface strings.
- **Anti-Hallucination Pronoun Consistency & Deterministic Turn Pipeline (game_engine/pronoun_resolver.py, game_engine/turn/narration.py)**:
  - Multi-tier pronoun resolver eliminating gender drift in multi-character scenes.
  - Deterministic Turn Narration pipeline decoupling state calculation from creative prose.

### [v2.3.0] - 2026-10-13

#### Added & Enhanced
- **Multi-Language & Internationalization Subsystem (`localization/`, `web/src/locales/`, `web/src/i18n.js`)**:
  - Trilingual core support across Python backend and React frontend: English (`en`), Polish (`pl`), and Malay (`ms`).
  - Affix translations and canonicalization (`translate_affix`, `canonicalize_affix`) for equipment and combat modifiers.
  - Localized item lemmas and unicode icon resolvers (`get_item_icon`).
  - Localized intent recognizers, conversation exit phrasing, and movement prefixes.
  - React frontend `i18next` integration with dedicated `LanguageSwitcher.jsx` component and settings persistence.
- **NPC Identity, Gender & Pronoun Consistency Engine (`game_engine/keywords.py`, `game_engine/prompts.py`, `llm_client.py`)**:
  - Post-generation pronoun sanitizer (`sanitize_npc_pronoun_consistency`) matching narrative text against registered NPC directory records.
  - Explicit prompt directives (`MANDATORY GENDER & PRONOUN CANON`) preventing gender drift and pronoun hallucinations across turns.
  - Context formatters (`_describe_tracked_entity`, `format_persona_summary`) explicitly formatting pronouns (`he/him`, `she/her`).
- **Combat Stance & Affinity Mechanics Synergy (`mechanics/social/relationships.py`, `cogs/contacts.py`)**:
  - Deterministic 0-300 affinity scale milestones (*Stranger*, *Acquaintance*, *Friend*, *Close Friend*, *Confidant*).
  - Scaled companion recruitment costs and tactical cooperation based on affinity standing.
  - Combat stance mechanics synchronized with affinity tiers and martial roles.
- **Sub-Facility Waypoint Preservation & Multi-Occupant Roster (`mechanics/world/locations/movement.py`, `db/world.py`)**:
  - Hierarchical waypoint retention preserving complete navigation paths (*Zone ➔ Facility ➔ Sub-Facility*) across movement reconciliations.
  - Multi-occupant facility roster allowing multiple distinct NPCs to inhabit shared sub-locations without record collisions.
  - School directory and lorebook schema gender parity synchronization.
- **Modern Web Application Enhancements & Internationalization (`web/src/`)**:
  - Responsive language switcher component in top navigation and Settings modal.
  - Settings Modal and Saves Modal updated with localized strings and responsive drawers.
  - Fresh production bundle built in `web/dist/`.
- **Automated Contract Test Suites (`tests/`)**:
  - Added `test_localization_mechanics.py`, `test_npc_gender_and_pronoun_consistency.py`, `test_affinity_and_combat_stance.py`, and `test_subfacility_waypoint_preservation.py`.

### [v2.2.0] - 2026-10-12

#### Added & Enhanced
- **Deterministic Affinity Engine (`mechanics/social/affinity_engine.py`)**:
  - Algorithmic relationship tier progression, disposition shifts, and social consequence safeguards.
- **In-Game Smartphone Narrative Bridge (`mechanics/system/phone/`)**:
  - Narrative memory grounding for text messaging (`dm_grounding.py`), player-initiated DMs (`player_dm.py`), and media captions (`media_captions.py`).
- **Engine Runtime Auditor & Matching Architecture (`game_engine/auditor.py`, `matching.py`)**:
  - Automated state consistency audits, choice validation, fuzzy entity matching, and collective entity isolation.
- **Arsenal & Apparel Expansion (`mechanics/combat/items/`)**:
  - Over 2,000 lines of specialized weapons across genres (`weapons.py`), expanded clothing (`clothing.py`), and scenario consumables (`genres.json`).
- **Nuanced Intimacy & Affection Dynamics (`mechanics/social/persona/intimacy/`)**:
  - Dynamic excitement tracking (`intimate_excitement.py`), sensory narrative fidelity, and emotional boundary progression.
- **Modern Web SPA Overhaul (`web/src/`)**:
  - Turn outcome breakdown panel (`TurnOutcomePanel.jsx`), redesigned codex (`CodexPanel.jsx`), character sheet inspection, and bundled assets.
- **Simulation Harness & Test Suites (`scripts/`, `tests/simulators/`)**:
  - Automated gameplay simulators for combat, narrative, navigation, and social interactions with 20+ new contract tests.

### [v2.1.0] - 2026-10-04

#### Added & Enhanced
- **Mechanics Domain Restructuring (Phase 2)**:
  - Modularized domain systems from flat directory into organized sub-packages: `mechanics/combat/`, `mechanics/narrative/`, `mechanics/social/`, `mechanics/system/`, and `mechanics/world/`.
- **Unified Web Frontend Architecture (Phase 3)**:
  - Unified React frontend sources, configs, and production assets under `web/` (`web/src/`, `web/dist/`).
  - Integrated zero-configuration native FastAPI static asset serving.
- **Root Declutter (Phase 1)**:
  - Reorganized project root, relocating tunnels and background utilities to `bin/tunnel.py`.
- **Distribution & Packaging Hardening**:
  - Excluded asset and development artifacts from clean distribution archives (`scripts/package_release.py`).
  - Enforced strict privacy safeguards with automated personal information scanning.

### [v2.0.0] - 2026-09-30

#### Major Overhaul & Architecture Modernization
- **Modern Modular Architecture (Waves 1–9)**:
  - Deconstructed monolithic engine into modular packages: `api/` (modular FastAPI controllers), `services/` (`turn_service.py`), `game_engine/state/`, `game_engine/turn/`, `db/` (`core.py`, `social.py`, `world.py`, `inventory.py`, `characters.py`), and `models/` (`llm_schemas.py`, `trackers.py`).
  - Added token memory budgeting and vector compaction in `mechanics/memory/`.
- **Modern React Web Application (`frontend/src/`)**:
  - Full single-page React frontend featuring Tactical Battle Deck (`ActionPanel.jsx`), interactive Story Feed (`StoryFeed.jsx`), live Party Widget (`PartyWidget.jsx`), in-game Smartphone Modal (`PhoneModal.jsx`), and Codex & Quest Log (`CodexPanel.jsx`, `QuestLogPanel.jsx`).
- **Thematic Starting Gear Generation**:
  - Starter equipment dynamically generated to match chosen character class, race, and scenario setting.
- **Intimacy Schema Modernization**:
  - Fully excised legacy binary virginity fields from schemas in favor of the unified 3-track intimate experience system (Vaginal, Oral, Manual) in `mechanics/persona.py`.
- **Automated Test Suite Hardening**:
  - Modernized with `pytest.ini`, centralized fixtures in `tests/conftest.py`, and architectural contract verification tests.

### [v1.8.1] - 2026-09-16

#### Added & Enhanced
- **Dynamic Narrative Paragraph Quotas (`game_engine/turn.py`)**:
  - Implemented `get_narrative_requirements(verbosity, dialogue_mode)` providing dynamic per-turn constraints (`concise`, `direct`, `normal`, `vivid`, `shakespearean`) with `STRICTLY FORBIDDEN` negative constraints.
- **Two-Way Spoken Dialogue Mandate (`game_engine/core.py`)**:
  - Rewrote `DIALOGUE_INSTRUCTIONS` across all modes (`balanced`, `adaptive`, `rich`, `minimal`, `off`) to guarantee both characters participate in dialogue and eliminate one-sided exposition.
- **Style & Dialogue Supremacy Framing (`game_engine/context.py`, `llm_client.py`)**:
  - Stripped hardcoded vivid/paragraph requirements from `OUTCOME_SCHEMA`, `SCENE_SCHEMA`, and `SYSTEM_PROMPT`.
  - Added `STRICT SUPREMACY` header and footer framing in `_style_block()`.

#### Fixed & Hardened
- **Equipment Archetype Heuristics (`mechanics/equipment/metadata.py`)**:
  - Refactored `get_equipment_metadata()` with slot-aware keyword matching for Gloves, Shoes, Headwear, Accessories, and Shields, preventing erroneous fallback to `"sword"`.
- **Adventure Loadout Gear Application (`db/inventory.py`, `db/characters.py`)**:
  - Refined `is_combat_armor` predicate to exclude non-armor slots and non-armor item types, ensuring seamless starting gear equipping across all classes.
  - Added comprehensive test suites: `test_verbosity_and_dialogue_overhaul.py` and template class adventure loadout test suite.

### [v1.8.0] - 2026-09-15

#### Added
- **Modular Item & Equipment Architecture (`mechanics/items/`)**:
  - Subsystems modularized: weapons, armors, clothing, shields, accessories, consumables, tags.
  - Fallout: New Vegas style Damage Threshold (DT) and Damage Resistance (DR) mechanics.
  - Dedicated Clothing Slot ("Top") separate from combat body armor.
  - Weapons as tactical damage multipliers and stat scalers.
  - Dual-wielding weapon mechanics and versatile weapon handling.
  - Dynamically generated starter weapons and scenario loadouts.
- **Modular Magic & Spells Architecture (`mechanics/spells/`)**:
  - Dedicated package with elemental tags, spell taxonomy, MP cost scaling, and class kits.
- **5-Tier Enemy Hierarchy & Telegraphed Moves (`mechanics/combat/`, `enemies.py`)**:
  - 5-tier ladder: Minion, Standard, Elite, Champion, Boss.
  - Telegraphed moves (charging, casting, defending, swarming) and tactical responses (Defensive Guard, Diplomacy Taunt, Weakness Exploit, Evade/Flee).
  - Affixes: Volatile, Phasing, Ethereal, Incorporeal, morale routing.
- **Backend SQLite WAL Mode & Indexing**:
  - Added critical database indexes and enabled Write-Ahead Logging (WAL) mode.
- **Persistent Merchant Inventory (`mechanics/merchant.py`)**:
  - Persistent store stocks with timer-based restocks.

#### Fixed & Polished
- **Web API Endpoint Crashes (`server.py`)**:
  - Fixed NONE stat crashes and missing character action keys in choice_index and custom action paths.
  - Restored party tuple formatting and XP awards in turn resolution.
- **NSFW LLM Startup Probing**:
  - Validates both primary and NSFW LLM endpoints on bot launch.
- **Contact Command UI Error**:
  - Fixed command syntax error in contacts view.

### [v1.7.0] - 2026-09-06

#### Added
- **Action Intent Engine Expansion (`mechanics/intent.py`)**:
  - 8 new intent categories and fast-pathing execution in `game_engine.py`.
  - Gift consumption and affection milestone memories.
- **Model Reasoning Safeguards (`llm_client.py`, `bot.py`)**:
  - Minimum 3,500 token buffer in `call_llm_json` preventing truncated JSON.
  - Startup model capability probing and alert banners.
  - 4096 token limit for story quest generation.
- **Quest UI Overhaul (`cogs/adventure.py`)**:
  - Distinct Main Story Quest and Bounty Board interactive buttons.
  - Decluttered expandable bounty cards.
- **Campus Map Expansion (`data/locations_seed.json`)**:
  - Sports Complex, Arts Wing, Tech Laboratories, Rooftop Garden.

#### Changed / Refactored
- **Contact Profile Decluttering (`cogs/contacts.py`)**:
  - Streamlined primary profile view cards.
- **Unified Item Tagging Taxonomy**:
  - Standardized item tagging taxonomy across scenarios.

#### Fixed & Polished
- **Intimate Experience & Virginity Synchronization (`mechanics/persona.py`)**:
  - Single-source-of-truth priority preventing profile desync.
- **Canonical Family Member Locking**:
  - Locked family records on creation to prevent hallucinated relatives.
- **Romance Bleed Guard**:
  - Prevented platonic characters from unintentionally flipping to romantic status.
- **Beastfolk Subspecies Appearance**:
  - Scaled beastfolk correctly receive scale descriptions instead of fur.

### [v1.6.0] - 2026-09-01

#### Added
- **Time, Day/Night Cycle & Fatigue System (`mechanics/time_engine.py`)**:
  - Minute-by-minute persistent time, 8 time phases, dynamic time-of-day badges.
  - Sleep/Rest actions, cumulative fatigue debuffs, and full HP/MP recovery.
- **Smartphone & Texting System (`mechanics/phone.py`, `waypoints.py`)**:
  - `/phone` texting interface, appointment scheduling, rendezvous waypoints.
  - Cross-zone companion mobility (`mechanics/mobility.py`).
- **Unified Intent Classification Engine (`mechanics/intent.py`)**:
  - Eliminates false-positive combat triggers during peaceful roleplay.
- **3-Track Experience & Act Preferences Overhaul (`mechanics/persona.py`)**:
  - 3 independent tracks (Vaginal, Oral, Manual), symmetrical act preferences, proactive NPC initiation.
- **Genealogy & Family Line Tracker (`mechanics/genealogy.py`)**:
  - Dynamic generational family relationships.

#### Changed / Refactored
- **Paginated Contact Profile Embeds (`cogs/contacts.py`)**:
  - Dropdown tabs: Overview, Combat Sheet, Persona, Intimate Profile.
- **Social & Date Dialogue Pacing (`game_engine.py`)**:
  - Natural romantic and social dialogue without forced combat triggers.

#### Fixed & Polished
- **Companion & Location Persistence (`mechanics/locations.py`)**:
  - Fixed interior sub-location persistence.
- **Intimate Attribute Disclosure Guard**:
  - Protected intimate attributes behind Info Disclosure Level >= 3.

### [v1.5.2] - 2026-08-20

#### Added
- **Procedural Multi-Pattern Biome Engine (`namegen.py`, `mechanics/locations.py`)**:
  - Procedural generators for fantasy biomes with varied patterns.
- **"Failing Forward" Dramatic Resolution (`game_engine.py`)**:
  - Failed skill checks escalate complications rather than halting gameplay.
- **Success Percentage Toggle (`cogs/settings.py`)**:
  - `/settings percentages` command to show/hide raw success percentages.
- **Dynamic Map UI Badges (`cogs/adventure.py`)**:
  - Zone badges and quest markers on travel menus.

#### Changed / Refactored
- **Location & Scene Decoupling**:
  - Decoupled physical locations from decorative scene titles.
- **Gender-Specific Starter Equipment**:
  - Gender separation on starter gear templates.

#### Fixed & Cleaned Up
- **Intimate Profile Privacy**:
  - Fixed premature visibility of intimate attributes.
- **Combat Victory/Defeat Formatting**:
  - Cleaned up embed newlines.
- **Legacy Code Removal**:
  - Removed obsolete quest update helpers and regex blocks.

### [v1.5.1] - 2026-08-14

#### Added
- **Tactical Combat & Companions (`mechanics/combat.py`, `cogs/adventure.py`)**:
  - Companion AI, multi-target engagement, Combat/Turn Summary embeds, 7 tactical choices.
- **Adventure Starting Loadouts (`cogs/character.py`, `cogs/adventure.py`)**:
  - Decoupled class/equipment from character creation to adventure start.
- **Dual-Model Utility Architecture (`config.py`, `llm_client.py`)**:
  - `LLM_UTILITY_MODEL` for background tasks.
- **Quest Item Auto-Success**:
  - Automatic skill check bypass when holding relevant quest items.
- **Dedicated Factions System (`cogs/factions.py`)**:
  - Standalone factions cog with `/factions list` and `/factions detail`.
- **Dynamic Intimate Profiles (`mechanics/persona.py`)**:
  - ~30-item pools for sensitive spots and turn-ons.

#### Changed / Refactored
- **Persona Module Consolidation**:
  - Unified appearance, traits, mannerisms into a single module.
- **Traits & Preferences Separation**:
  - Distinct Traits (max 3) and Preferences (max 3).
- **Real-Time Settings Application**:
  - `/settings` changes apply immediately to active sessions.
- **Adventure Reset Flow**:
  - Starting a new adventure cleanly resets stats, conditions, and starting gear.

#### Fixed & Cleaned Up
- **Combat Clue Suppression**:
  - Disabled investigation clues during active combat turns.
- **Combat Narrative Immersion**:
  - Stripped raw HP digits from narrative prose.
- **Status Effect Sanitization**:
  - Capped status effects to concise 1-2 word descriptors.
- **Removed Obsolete Systems**:
  - Deprecated world_events and relic_collection code.

### [v1.4.0] - 2026-08-05

#### Added
- **Quest Log & Bounty Board (`db.py`, `cogs/adventure.py`)**:
  - Interactive `/quest` and `/bounty` commands with objectives and rewards.
- **10-Chapter Procedural Campaign System (`game_engine.py`)**:
  - Structured 10-chapter campaign progression.
- **Physical Appearance Expansion (`mechanics/appearance.py`)**:
  - Expanded physical appearance attributes and gender visibility.

#### Changed & Fixed
- **Structured Schema Quest Updates**:
  - Moved quest updates directly into JSON OUTCOME_SCHEMA.
- **Discord UI Interaction Timeouts**:
  - Added instant `interaction.response.defer()` calls.
- **SSL Certificate Configuration**:
  - Configured certifi CA bundle and unverified SSL context fallback.

### [v1.3.0] - 2026-08-03

#### Added
- **Dynamic NSFW Model Routing**:
  - Dedicated `NSFW_LLM_MODEL` / `NSFW_LLM_API_KEY` environment variables.
- **LLM Fallback Cascade & Timeout Controls**:
  - Multi-model fallback chains with per-attempt timeout management.
- **Opening Narrative Fallback Guardrail**:
  - Embedded SCENE_SCHEMA in initial prompts to prevent blank scenes.

### [v1.2.0] - 2026-08-03

#### Added
- **Location Tree & Dynamic Discovery**:
  - Tiered location navigation, fast travel dropdowns, dynamic location context.
- **Developer Debug Suite**:
  - `/debug` command with stat overrides and success modifiers.
- **Character Roster Expansion**:
  - Increased character slot limit from 3 to 6.

### [v1.1.0] - 2026-08-01

#### Added & Fixed
- **LLM Robustness & Concurrency Control**:
  - Rate-limiting semaphores, 120s timeouts, json_repair fallback extractors.
- **Narrative Length Balancing**:
  - Rebalanced turn narrative lengths between outcome and scene.
- **Active Session State Fix**:
  - Fixed active character session persistence bug on bot restart.

### [v1.0.0] - 2026-07-25

#### Added
- **Core RPG Engine**:
  - Discord bot framework (`bot.py`), SQLite schema (`db.py`), LLM client (`llm_client.py`), and turn resolution engine (`game_engine.py`).
- **Web Application Interface**:
  - FastAPI server (`server.py`), Single-page Web UI (`web/index.html`, `web/app.js`, `web/styles.css`), and Web Speech TTS audio engine (`web/audio.js`).
