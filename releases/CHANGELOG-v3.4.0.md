# Hikayat Release Changelog — v3.4.0

**Release Date:** 2026-11-20  
**Type:** Minor Release  
**Milestone:** Outlaw Factions & 10-Wing HQs (Migration v60), 68 Special Agent Blueprints & 3-Stage Procedural Population Engine, Native `<dialog>` World Map Modal Overhaul, Narrative Pacing & Prose Styles (Migrations v58 & v59), and Hybrid Reasoning Streaming Engine

---

## 🌟 Overview

Hikayat **v3.4.0** delivers a major expansion to world population density, factional depth, prose customizability, navigation UX, and streaming LLM performance. Highlights include **Schema Migration v60** introducing fully fledged 10-wing Headquarters and starter safehouses for outlaw factions (*The Occult Cult* and *The Clandestine Syndicate*), an expanded roster of 68 specialized agent blueprints coupled with a **3-stage procedural world population engine** (`population_seeder.py`), a comprehensive rewrite of the **World Map Modal** using native HTML `<dialog>` with active quest routing and mobile split navigation, **Narrative Pacing & Prose Styles** (Migrations v58 and v59) giving players fine-grained control over narrative lengths and atmospheric tones, and an optimized **hybrid reasoning streaming pipeline** with split stall timeouts and batched database snapshot transactions.

---

## 🚀 Key Implementations & Enhancements

### 1. Outlaw Factions, 10-Wing HQs & Starter Safehouses (`db/core.py`, `mechanics/social/factions.py`, `mechanics/world/anomalous_sites/lifecycle.py`)
- **Schema Migration v60 (`_migrate_outlaw_factions_v60`)**: Idempotently backfills 10-wing spatial headquarters for `loc_cult_sanctum_hq` and `loc_clandestine_syndicate_hq`, alongside starter safehouses and faction-restricted subrooms (`backfill_outlaw_faction_hqs_and_residences_v60`).
- **Faction Authority & Rank Promotion (`mechanics/social/factions.py`)**:
  - Implemented 5-tier anomalous faction promotion progression with archetype-specific perks (`get_anomalous_promotion_tiers_for_archetype`, `get_active_perks`, `get_anomalous_faction_spec`).
  - Added strict faction HQ action access validation (`validate_faction_hq_action_access`), quartermaster and bounty board eligibility gates, and clean transfer protocols (`join_or_transfer_anomalous_faction`) that escort players out of revoked wings, synchronize lorebook dispositions, and evict incompatible party companions.

### 2. 68 Special Agent Blueprints & 3-Stage Procedural Population Engine (`mechanics/social/`, `db/roster.py`)
- **Expanded Agent Blueprints (`agent_roster.py`)**: Authored 48 adult special agent blueprints across 6 factions (8 per faction) and 20 anomalous high school student special agents (5 per grade, with 12 junior faction-affiliated operatives). Added personality quirks, attribute pools, and faction-aware recruitment evaluation (`evaluate_anomalous_companion_recruitment`).
- **Procedural Population Architecture (`population_catalog.py`, `population_seeder.py`)**:
  - **Stage 0 (`ensure_world_population_seeded`)**: Zero-LLM single-transaction bulk seeding of persistent `world_roster` skeletons (~240 Anomalous Incursions, ~180 High School Drama, ~310 Anomalous High School casts) with pre-wired social ties and shared residence groups.
  - **Stage 1 (`hydrate_roster_npc_on_scene`)**: Lazy zero-LLM procedural hydration of appearance, quirks, likes, dislikes, and drives upon first co-located scene encounter.
- **Roster Database Parity (`db/roster.py`)**: Added `bulk_upsert_world_roster` and `hydrate_world_roster_visuals` for high-throughput population transactions without N+1 overhead.

### 3. Native `<dialog>` World Map Modal Overhaul (`web/src/components/Modals/WorldMapModal.jsx`, `web/src/index.css`)
- **Native `<dialog>` Architecture**: Migrated modal implementation to the native HTML `<dialog>` element with backdrop handling, ESC auto-close, click-outside dismissal, and progressive enhancement fallbacks.
- **Mobile Responsive Split Navigation**: Introduced responsive `list` vs. `detail` dual-view layout on mobile viewports for fluid zone browsing and place inspection.
- **Active Quest Destinations & Deep Linking**:
  - Added dedicated `regions` vs. `quests` left rail tabs surfacing all active quest objectives, markers, and tags directly on the map.
  - Added deep-link target routing (`highlightedTarget`) with smooth auto-scroll into targeted places and sub-rooms.
  - Interactive sub-room accordion displays real-time access badges (*Curfew, Closed, Locked, Owned Residence, For Sale*), travel ETAs, and fast-travel buttons.

### 4. Narrative Pacing, Prose Styles & Combat Display Settings (`db/core.py`, `db/settings.py`, `cogs/settings.py`, `web/`)
- **Schema Migrations v58 & v59**:
  - Added `narrative_pacing` (*concise*, *balanced*, *novelistic*) to decouple prose volume from stylistic voice.
  - Added stylized `verbosity` registers (*normal*, *vivid*, *noir*, *witty*, *shakespearean*, *brainrot*).
  - Added toggles for `show_enemy_hp` and `show_enemy_intent` across `user_settings` and active `sessions`.
- **Omnichannel Settings Parity**:
  - Updated Discord bot `/settings` command and button views in `cogs/settings.py`.
  - Updated React `SettingsModal.jsx`, `useSettings.js`, and synchronized settings across WebSockets in `api/settings_ws.py`.

### 5. Hybrid Reasoning LLM Streaming & Bundled Turn Transactions (`services/turn_service.py`, `game_engine/turn/`, `llm_client.py`)
- **Reasoning Model Support & Split Timeouts (`config.py`, `llm_client.py`)**:
  - Added split stall thresholds: generous Time-To-First-Token (`LLM_TTFT_TIMEOUT` = 75s) for heavy local KV prefill, rapid inter-chunk stall detection (`LLM_CHUNK_IDLE_TIMEOUT` = 25s), and overall turn streaming deadline (`LLM_STREAM_TOTAL_DEADLINE` = 150s).
  - Added support for hybrid reasoning models (`LLM_THINKING_MAX_TOKENS`, `LLM_REASONING_EFFORT`, `LLM_SUPPRESS_NARRATION_COT`).
- **Turn Transaction Bundling (`services/turn_service.py`, `game_engine/turn/core.py`)**:
  - Consolidated pre-turn snapshot reads (`_pre_turn_snapshot_bundle`), post-turn snapshot writes (`_post_turn_snapshot_bundle`), and final post-turn commits (`_post_turn_commit_bundle`) into atomic batched transactions.
  - Replaced ad-hoc paragraph splits with centralized `split_outcome_and_next_paragraphs` (`game_engine/choice_icons.py`).
  - Streamlined ambient action classification with micro-context classifier (<250 tokens) and fast-path general action dispatch.

---

## 📦 Distribution Packages
- **Clean Production Archive**: `releases/hikayat-v3.4.0-clean.zip` (Clean production deployment: 0 tests, 0 icon files, 0 runtime images, 0 databases, 0 personal leaks).
- **Full Development Backup**: Branch `backup/v3.4.0` & Tag `v3.4.0-full` (Preserving tracked source snapshot cleanly alongside local `backups/hikayat-v3.4.0-tests-backup.zip`).
