# Hikayat Release Changelog — v3.3.0

**Release Date:** 2026-11-17  
**Type:** Minor Release  
**Milestone:** Migration v57 Anomalous Locations Integrity, Dynamic Urban City Profiles, Unified Shop Staff & Quartermaster Authority, Quest Climax & Remote Travel Hardening, and Code Hygiene Sweep

---

## 🌟 Overview

Hikayat **v3.3.0** strengthens structural world integrity and headless omnichannel consistency across the database, quest engine, urban geography, merchant availability, and UI layers. Highlights include automated schema **Migration v57** for anomalous node/edge/tier integrity, procedural per-session urban city identity profiles (`get_urban_city_profile`) propagated into world seeds, unified server-side merchant/quartermaster availability (`resolve_scene_merchant_ui_state`), remote Story Quest travel choice injection, Story Quest climax & MacGuffin turn-in enforcement, and a repository-wide dead-code and unused-import cleanup.

---

## 🚀 Key Implementations & Enhancements

### 1. Schema Migration v57 & Anomalous Locations Integrity (`db/core.py`, `db/saves.py`, `mechanics/world/anomalous_sites/lifecycle.py`)
- **Automated World Integrity Backfill (`_migrate_anomalous_locations_integrity_v57`)**: Added `backfill_anomalous_locations_integrity_v57` wired into both startup schema migrations and `load_adventure_slot` save restoration. Repairs misparented anomalous nodes and edges (`loc_hilltop_shrine`, `loc_backstage_loft`), normalizes `sub_hosp_isolation_cell_1309` hierarchy, aligns canonical room renames across `world_nodes`, `session_locations`, `sessions`, `quest_waypoints`, `commitments_ledger`, and `school_directory`, and clears false residential/restricted/curfew drift on public and anomalous venues.
- **Catalog Alignment (`data/anomalous_sites_catalog.json`)**: Synced anomalous site zone assignments, sub-room lists, and location keywords with repaired graph topology.

### 2. Dynamic Urban City Profiles & Location Seed Hardening (`namegen.py`, `mechanics/world/`, `scenario_data.py`, `data/`)
- **Per-Session Urban Identity (`get_urban_city_profile`, `generate_urban_city_name`, `get_session_city_name`)**: Replaced static hardcoded urban city names with deterministic per-session city profiles surfaced in `scenario_prompt_block(session_id)`, urban zone/facility naming, town rosters (`remap_town_node_for_scenario`), and `data/scenarios.json`.
- **University & Anomalous Flag Boundaries (`mechanics/world/world_schedule.py`, `locations/`)**: Added `is_university_node_or_location` and `_node_is_anomalous_flag` to cleanly separate academy, university, and anomalous curfew/access checks.
- **Location Seed Graph (`data/locations_seed.json`, `graph_seeder.py`, `formatting.py`, `seeding.py`, `seeds.py`)**: Regenerated location seeds and hardened graph seeding, access tier inference, and LLM location formatting.

### 3. Unified Shop Staff, Faction Quartermaster & Wardrobe Continuity (`mechanics/world/venue_seeder.py`, `db/roster.py`, `api/`, `cogs/`)
- **Headless Merchant UI Authority (`resolve_scene_merchant_ui_state`)**: Consolidated shop staff availability, label resolution, closed-shop reasons, and active merchant detection across `api/adventure.py`, `cogs/adventure/views/choices.py`, and `web/src/components/ActionPanel/ActionPanel.jsx`—eliminating duplicated ad-hoc client/cog role heuristics.
- **Civic HQ & Quartermaster Validation (`heal_stale_civic_hq_staff`, `clear_roster_npc_merchant_archetypes`, `_validate_or_clear_faction_quartermaster`)**: Automatically clears stale merchant archetypes on non-shop civic staff and validates that active Faction Quartermaster state remains anchored to a genuine Faction HQ.
- **Wardrobe & Erotic Dialogue Parity**: Wired `active_incursion` into `_wardrobe_session` in `game_engine/state/reducers.py` and added shared `is_session_in_erotic_dialogue()` detection in `mechanics/social/physical_state.py` across `deck.py`, `embeds.py`, and `api/adventure.py`.

### 4. Quest Climax Enforcement, Remote Travel & Save/Rollback Parity (`game_engine/`, `db/`, `mechanics/world/waypoints/`)
- **Turn-In & Disposal Guards (`game_engine/quest_agency.py`, `quests.py`, `quest_lifecycle.py`)**: Blocked premature completion on already-closed quests, uncompleted main Story Quest stages, or unrecovered required MacGuffin items (`deliver`, `keep`, `fence`, `destroy`), while enforcing Phase 1 vs. Phase 2 climax boss transitions.
- **Remote Story Quest Travel Injection (`mechanics/world/waypoints/choices.py`, `localization/`)**: Added `_is_remote_node_revealed_and_reachable` and `_inject_or_upgrade_remote_quest_travel` to surface deterministic `Travel to {dest}` quest actions when the active objective lies at a revealed remote node, backed by 5-language templates and travel-intent guards in `waypoints/matching.py`.
- **Fog-of-War, Rollback & Save Remapping (`db/dossiers.py`, `db/quests.py`, `db/saves.py`, `campaign_spine.py`)**: Added Hidden Lair Climax destination redaction in `redact_quest_for_fog_of_war`, `bypassed` stage parity in `sync_quest_projection_from_dossier`, `compiled_at_turn` & `reward_claimed` rollback parity, `state_events_json` inventory ID remapping on save load, and `append_spine_state_event` tracking on escaped nemesis updates.
- **Dossier Stage Affinity & Meetup Guards (`dossier_compiler.py`, `dm_grounding.py`, `origin_mode.py`, `stealth/core.py`)**: Prioritized target-venue rooms during dossier compilation, excluded restricted/anomalous venues from phone meetups (`_is_restricted_or_excluded_meetup_target`), added `resolve_authoritative_origin_session` & `is_adult_ahs_operative_fail_closed`, and tightened word-bounded `_HOSTILE_RESTRICTED_RE` stealth keyword matching.

### 5. Web SPA Polish, 5-Language Parity & Code Hygiene (`web/`, `llm_client.py`, `services/turn_service.py`)
- **Frontend Stability & UX**: Added `AbortController` + request sequence guards in `useCodex.js` to prevent stale async overwrites, surfaced `can_travel` gates in `WorldMapModal.jsx`, updated closed-shop badges in `ActionPanel.jsx`, refined single-lead deduction & quest badge counts in `QuestLogPanel.jsx` and `GameView.jsx`, and fixed `StreamingNarrativeExtractor` multi-field early stop & fallback narrative paragraph splitting.
- **5-Language Localization & Dead Code Sweep**: Synced closed-shop, quest stage, travel-blocked, and single-lead keys across `en`, `pl`, `ms`, `de`, and `zh` (`localization/*.py` & `web/src/locales/*.json`); removed unwired dead functions and 100+ unused imports across backend and React source files; and rebuilt `web/dist/`.

---

## 📦 Distribution Packages
- **Clean Production Archive**: `releases/hikayat-v3.3.0-clean.zip` (Clean production deployment: 0 tests, 0 icon files, 0 runtime images, 0 databases, 0 personal leaks).
- **Full Development Backup**: Branch `backup/v3.3.0` & Tag `v3.3.0-full` (Preserving tracked source snapshot cleanly alongside local `backups/hikayat-v3.3.0-tests-backup.zip`).
