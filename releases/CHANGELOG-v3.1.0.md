# Hikayat Release Changelog — v3.1.0

**Release Date:** 2026-11-16  
**Type:** Minor Release  
**Milestone:** Anomalous Sites Package (36 Pacifiable Wild Sites, Puzzles & Harvesting), School Club & Rival Turf Hardening, Private Residence Access Gates & Omnichannel UI Parity

---

## 🌟 Overview

Hikayat **v3.1.0** introduces a dedicated **Anomalous Sites** simulation subsystem (`mechanics/world/anomalous_sites/` paired with `data/anomalous_sites_catalog.json`), allowing players to investigate, stabilize, and harvest 36 pacifiable supernatural sites across the world. Alongside site exploration, this release hardens school club subroom rules, rival turf blocking, private residence access gates, phone DM grounding, and expands the Web Encyclopedia with Anomalous Sites and Field Log views.

---

## 🚀 Key Implementations & Enhancements

### 1. Anomalous Sites Engine & Catalog (`mechanics/world/anomalous_sites/`, `data/anomalous_sites_catalog.json`)
- **Catalog & Site State (`catalog.py`)**: Loaded 36 `pacifiable_wild_site_ids` and hostile HQ sites (`loc_cult_sanctum_hq`, `loc_clandestine_syndicate_hq`) alongside Theme Park night-shift / witching-peak rules and site state persistence.
- **Domain Rules & Hazards (`domain_rules.py`)**: Implemented domain skill-check modifiers, combat attribute mitigation, spatial loop travel checks, resonator charge tracking, and sleep blocking inside active anomalous zones.
- **Interactive Site Puzzles (`puzzles.py`)**: Added step-by-step anomaly puzzle resolution, companion assists, passive ward/flare detection, and freeform verb matching.
- **Pacification Harvesting & Lifecycle (`harvest.py`, `lifecycle.py`)**: Added relic gear/spell & elemental ward rewards on `complete_site_pacification`, extraction collapse (`collapse_anomalous_site_on_extraction`), midnight unpacified puzzle re-knitting (`lazy_midnight_reknit_site`), and atomic turn rollback (`rollback_anomalous_sites_after_turn`).

### 2. School Clubs, Rival Turf & Spatial Seeding (`mechanics/social/factions.py`, `mechanics/world/locations/seeding.py`, `data/locations_seed.json`)
- **Club & Salon Mechanics**: Added `validate_major_club_subroom_action`, `check_rival_or_hostile_turf_block`, `validate_club_quartermaster_hours`, and school starter faction/HQ reconciliation (`_reconcile_school_starter_factions_and_rivals`).
- **Hidden Facility Discovery & Rollback**: Added `reveal_hidden_club_facility` and `rollback_hidden_club_discoveries_after_turn` wired into `db/saves.py` and `db/sessions.py`, plus expanded `data/locations_seed.json`.

### 3. Access Gates, DM Grounding & Combat/Turn Integration (`access_gate.py`, `dm_grounding.py`, `services/turn_service.py`)
- **Residence & HQ Gates**: Added `_is_npc_private_residence_node` and stricter anomalous HQ access checks in `mechanics/world/locations/access_gate.py` and `attributes.py` / `formatting.py`.
- **Pipeline, Bounty & Combat Polish**: Updated `mechanics/narrative/bounty.py` (`_build_school_club_fallback_bounties`), `mechanics/system/phone/dm_grounding.py`, `mechanics/social/epistemic_propagation.py`, `mechanics/combat/` modules, `game_engine/turn/core.py`, and `services/turn_service.py`.

### 4. Omnichannel UI, Encyclopedia Sites Tab & 5-Language Parity (`web/`, `cogs/`, `localization/`)
- **Encyclopedia & World Map**: Upgraded `web/src/components/Sidebar/EncyclopediaSubTab.jsx` with `folklore` | `sites` | `field_log` views and updated `WorldMapModal.jsx` and `MerchantModal.jsx`.
- **Discord, API & Locales**: Updated `cogs/adventure/faction_mixin.py`, `cogs/contacts.py`, `api/codex_phone.py`, `api/inventory_merchant.py`, and all 5 language packs (`en`, `pl`, `ms`, `de`, `zh`) in `localization/` and `web/src/locales/`, with freshly compiled `web/dist/` production assets.

---

## 📦 Distribution Packages
- **Clean Production Archive**: `releases/hikayat-v3.1.0-clean.zip` (Clean production deployment: 0 tests, 0 icon files, 0 runtime images, 0 databases, 0 personal leaks).
- **Full Development Backup**: Branch `backup/v3.1.0` & Tag `v3.1.0-full` (Preserving tracked source snapshot cleanly alongside local `backups/hikayat-v3.1.0-tests-backup.zip`).
