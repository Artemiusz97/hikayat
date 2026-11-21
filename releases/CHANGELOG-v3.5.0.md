# Hikayat Release Changelog — v3.5.0

**Release Date:** 2026-11-22  
**Type:** Minor Release  
**Milestone:** Zero-Turn Scene Examine & Tactical Intel, Declarative 41-Table Session Lifecycle Registry, Acrylic Glassmorphism UI & 12 Scenario Backdrops, Drop-In Custom Fonts, 5-Mode Consumables & Scenario Currencies

---

## 🌟 Overview

Hikayat **v3.5.0** introduces a zero-turn **Scene Examine & Tactical Intel** system with unified Discord and React modals, formalizes database lifecycle integrity via a declarative **41-table session registry** (`db/registry.py`) paired with pooled `ReadUnitOfWork` transactions and typed `TurnExecutionContext` stages, overhauls the React SPA into an **Acrylic Glassmorphism** interface featuring **12 scenario `.webp` backdrops** with live OKLCH time-of-day grading and **drop-in custom fonts**, and adds a **5-mode consumable classifier**, **scenario-native currencies**, deterministic **post-combat auto-loot**, and **quest-cast hydration**.

---

## 🚀 Key Implementations & Enhancements

### 1. Zero-Turn Scene Examine & Tactical Intel (`mechanics/narrative/examine.py`, `services/examine_service.py`, `api/adventure.py`, `cogs/adventure/views/choices.py`, `web/src/components/Modals/ExamineModal.jsx`)
- **Zero-Turn Snapshot Builder (`build_examine_snapshot`)**: Extracts live environment details, adjacent exits, present NPCs (demographics, outer garment summaries, posture, `PER`-tier subtle mood tells, and direct *Use Item* / *Gift* actions), dropped/scene props (with one-click Pick Up), active location/NPC clues, stealth/privacy/witness Fog-of-War telemetry, and combat tactical intel (condition labels, optional HP bars & telegraphed intents, and `PER`-gated or dossier-revealed weaknesses/resistances/immunities) without advancing time or fabricating loot.
- **Cached Omnichannel Delivery (`get_examine_payload`, `scrub_examine_prose`)**: Serves structured inspect state immediately (`include_prose=false`) and asynchronously generates LRU/TTL-cached sensory prose (`include_prose=true`) via `GET /api/adventure/examine` and ephemeral Discord embeds (`_build_examine_embed`, `_send_ephemeral_examine`), invalidated automatically on state transitions and scrubbed against stat/secret leaks.
- **Canonical Choice Cleanup (`game_engine/choices_cleaner.py`)**: Deduplicates generic look-around choices (`_is_generic_examine_choice`) now handled by the dedicated zero-turn Examine modal, and standardizes choice ordering (`order_choices_canonically`).

### 2. Declarative 41-Table Session Registry, Pooled `ReadUnitOfWork` & Typed `TurnExecutionContext` (`db/registry.py`, `db/core.py`, `db/saves.py`, `db/sessions.py`, `game_engine/turn_context.py`, `game_engine/state/reducers.py`, `scripts/static_check.py`)
- **Declarative Session Table Registry (`db/registry.py`)**: Centralizes all 41 session-scoped child tables (`SESSION_TABLE_REGISTRY` / `SessionTableSpec`), plus `GLOBAL_TABLES` and `FTS5_VIRTUAL_TABLES`, driving FK-safe purge order (`get_purge_specs`), tiered save/load slot ID remapping with declarative row/post-load/post-inventory hooks (`db/saves.py`), uniform turn rollback (`db/sessions.py`), and ring-buffer turn snapshot pruning (`prune_session_turn_snapshots`).
- **SQLite Pooling & Batched Preloading (`db/core.py`)**: Adds thread-safe pooled read connections (`_acquire_pooled_conn`, `ReadUnitOfWork`), `PRAGMA user_version` schema fast-path initialization, `ensure_table_group_once`, batched action/party preloaders (`preload_prepare_action_bundle`, `preload_turn_party_bundle`), and periodic WAL maintenance (`maybe_run_wal_maintenance`).
- **Typed Turn Stage Dataclasses & Reducer Decomposition (`game_engine/turn_context.py`, `game_engine/state/reducers.py`)**: Refactors ad-hoc session/outcome transient keys into typed `TurnClockStage`, `CombatStageState`, `EpistemicAndWorldStage`, and `TurnNotices` dataclasses, and extracts focused quest/waypoint and physical-state reducers.
- **Expanded Static Gate (`scripts/static_check.py`)**: Enforces `raw-conn-commit-outside-core` and `unregistered-session-table` invariants at commit time.

### 3. Acrylic Glassmorphism UI, 12 Scenario Backdrops, Drop-In Custom Fonts & Modal Modularization (`api/fonts.py`, `custom_fonts/`, `web/`)
- **Acrylic Preferences & HUD Customization (`web/src/theme/UiPreferencesProvider.jsx`, `AcrylicModeSwitcher.jsx`)**: Adds 3 acrylic glass modes (`full`, `focused`, `solid`), continuous acrylic opacity (`5%–95%`), UI text scale (`70%–130%`), continuous vs. scene reading modes, `12h`/`24h` clock formatting (`web/src/utils/timeFormat.js`), and persistent HUD section toggles.
- **12 Scenario Backdrops & OKLCH Time Grading (`web/public/backgrounds/`, `web/src/theme/backgrounds.js`, `ScenarioBackdrop.jsx`)**: Bundles 12 `.webp` menu & genre illustrations with smooth Motion crossfades, OKLCH atmospheric time-of-day grading (*Dawn, Day, Dusk, Night*), and optional blurred ambient scene-artwork backdrops.
- **Drop-In Custom Fonts (`api/fonts.py`, `custom_fonts/README.txt`, `web/src/utils/fonts.js`)**: Discovers `.woff2`, `.woff`, `.otf`, and `.ttf` files in `custom_fonts/`, automatically parses weight/italic tokens into unified font families via `GET /api/fonts` and `GET /fonts/{filename}`, and pairs them with curated UI & Narration Google Font presets.
- **Component & Chronicle Refactor (`MotionPrimitives.jsx`, `TurnHistoryModal.jsx`, `web/src/components/Phone/Phone*App.jsx`, `web/src/components/Sidebar/quests/*`)**: Replaces the legacy `TurnOutcomePanel.jsx` with the searchable `TurnHistoryModal.jsx` + `AcrylicModal` stack with ESC-layer management and `LazyMount` error recovery, splits `PhoneModal.jsx` into 8 dedicated app modules (*Home, DMs, Feed, Photos, Planner, Shop, Bounties, Realty*), and modularizes `QuestLogPanel.jsx` into `CampaignTab`, `CaseboardTab`, `BountiesTab`, `ArchiveTab`, and `QuestObjectivesSection`.

### 4. 5-Mode Consumable Classifier, Scenario Currencies & Post-Combat Auto-Loot (`mechanics/combat/items/consumables/`, `mechanics/combat/reconcile.py`, `scenario_data.py`, `web/src/utils/`)
- **5-Mode Consumable Classification (`classify_consumable_usage_mode`, `is_hostile_or_covert_consumable`, `web/src/utils/consumables.js`)**: Categorizes inventory items into `non_consumable`, `throwable`, `mechanical`, `narrative`, and `hybrid` across Python and React, gating instant out-of-combat Quick Use vs. story/targeted turn execution and recording NPC gift possessions (`_record_npc_gift_possession`).
- **Scenario Currencies (`scenario_data.py`, `web/src/utils/currency.js`, `CurrencyBadge.jsx`)**: Adds unified scenario currency definitions across Gold (`G`), Crowns, Credits (`₵`), Yen (`¥`), Cash (`$`), Eurodollars (`€$`), Sovereigns (`£`), and Caps across merchant, quest, phone, and chronicle views.
- **Deterministic Post-Combat Auto-Loot & Inventory Stacking (`award_post_combat_auto_loot`, `transfer_item_between_users`, `sceneTargets.js`)**: Automatically grants defeated combat loot deterministically, supports cross-user item transfers, and groups identical unequipped items into stackable rows.

### 5. Quest Cast Hydration, Inquiry Sanitization, Stealth Toggle Sync & Demographics (`mechanics/narrative/dossier_compiler.py`, `mechanics/world/presence_resolver.py`, `mechanics/social/band_fallbacks.py`, `mechanics/stealth/escalation.py`, `mechanics/social/races.py`, `web/src/utils/npcDemographics.js`)
- **Quest Cast & Race Hydration**: Deterministic quest cast registration (`_resolve_and_register_quest_cast_npc`) and waypoint NPC hydration (`_hydrate_and_backfill_quest_waypoint_npc`) with scenario-aware race rolling (`roll_scenario_npc_race`).
- **Quest Inquiry Cleanup & Stealth Toggle Sync**: Sanitizes dialogue quest prompts against internal text leaks (`_resolve_quest_dialogue_inquiry_spec`, `_clean_quest_inquiry_text`), and dynamically injects/syncs stealth and distraction choices when toggling stealth (`sync_stealth_choices_for_toggle`).
- **Unified NPC Demographic Pills (`npcDemographics.js`)**: Standardizes localized Age Category, Gender, and Scenario Race pills across `PresentNpcsCard`, `ExamineModal`, `ContactsPanel`, and `AcquaintancesView`, and syncs 5-language locales (`en`, `pl`, `ms`, `de`, `zh`).

---

## 📦 Distribution Packages
- **Clean Production Archive**: `releases/hikayat-v3.5.0-clean.zip` (Clean production deployment: 0 tests, 0 icon files, 0 runtime images, 0 user custom fonts, 0 databases, 0 personal leaks).
- **Full Development Backup**: Branch `backup/v3.5.0` & Tag `v3.5.0-full` (Preserving tracked source snapshot cleanly alongside local `backups/hikayat-v3.5.0-tests-backup.zip`).
