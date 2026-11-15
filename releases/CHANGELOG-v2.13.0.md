# Hikayat Release Changelog — v2.13.0

**Release Date:** 2026-11-15  
**Type:** Minor Release  
**Milestone:** Closed-World NPC Engine (`world_roster`), Anchor-Node Schedules, Residential Fog-of-War, Lazy Venue Seeder & Staff-Bound Shops, 6-Tier Presence Resolver, and Progressive Routine Disclosure UI

---

## 🌟 Overview

Hikayat **v2.13.0** overhauls how characters inhabit the world by introducing the **Closed-World NPC Engine**. Instead of conjuring ad-hoc NPCs from narration alone, sessions now maintain a normalized SQLite roster (`world_roster`) where venue staff, rotating roamers, students, and roaming merchants follow deterministic work shifts, rest days, and residential fog-of-war rules. Before every turn, a 6-tier presence resolver preloads world state in O(1) queries to determine who is physically on-screen—and across Web and Discord, the new **Contacts | Acquaintances** directory reveals NPC schedules progressively as relationships grow.

---

## 🚀 Key Implementations & Enhancements

### 1. Normalized `world_roster` Persistence & Lifecycle (`db/roster.py`, `db/roster_adapters.py`)
- **Single Closed-World Authority**: Added the SQLite `world_roster` table (`db/core.py`, `db/roster.py`) tracking `npc_id`, `roster_origin`, `tier_status` (`seeded`, `acquaintance`, `promoted`), `shift_profile`, `staff_status`, `workplace_node_id`, and turn-indexed snapshots (`MAX_TURN_SNAPSHOTS = 10`).
- **Lifecycle Parity**: Wired `world_roster` cleanly into save/load slot remapping (`db/saves.py`), turn rollback (`db/sessions.py`, `services/turn_service.py`), and cascade cleanup (`db/core.py`), alongside non-duplicating legacy roster adapters (`db/roster_adapters.py`).

### 2. Anchor-Node Schedules & Residential Fog-of-War (`mechanics/world/anchor_schedule.py`, `residence_fog.py`, `schedule_blocks.py`)
- **Shift-Driven Routines**: Implemented `day`, `evening`, `night`, `student`, `rotating`, and `roaming_merchant` shift profiles mapped across 5 canonical daily blocks (`morning`, `lunch`, `afternoon`, `evening`, `night`) with rest-day handling.
- **Residential Fog-of-War**: Added `mechanics/world/locations/residence_fog.py` so unrevealed NPC homes abstract to `zone_residential_abstract` until explicitly unlocked via `invite`, `friend_tier` (`>= 100`), `quest_lead`, `tailed`, `cohabitant`, or `family`.

### 3. Lazy Venue Seeder, Roamers & Staff-Bound Shops (`mechanics/world/venue_seeder.py`, `venue_templates.py`, `api/inventory_merchant.py`)
- **Deterministic Venue Staffing**: Added pure template definitions (`venue_templates.py`) and seed-deterministic staffing/roamer seeding (`venue_seeder.py`) with role slot-fill rules and crowd flavor fallbacks.
- **Staff-Bound Merchants**: Merchant shop availability (`api/inventory_merchant.py`, `cogs/adventure/merchant_mixin.py`, `mechanics/combat/merchant.py`) now respects on-duty staff status rather than remaining unconditionally open.

### 4. Unified 6-Tier Presence Resolver & Doorbell Etiquette (`mechanics/world/presence_resolver.py`, `presence_preload.py`, `presence_graph.py`, `presence_doorbell.py`)
- **Strict 6-Tier Resolution**: Evaluates physically present characters in strict precedence:
  1. `party` (active party & `in_party` roster members)
  2. `commitment` (active phone appointments within window)
  3. `quest_pin` (active story/bounty waypoints pinned at the node)
  4. `doorbell_answered` (sleep-window, affinity, spare-key, and cohabitant doorbell checks)
  5. `schedule` (active anchor-node shift/hangout presence)
  6. `crowd_flavor` (unnamed atmospheric venue text with zero DB writes)
- **Zero N+1 Overhead**: Consolidated node graph traversal and session preload into `presence_preload.py` and `presence_graph.py`, eliminating N+1 waypoint queries and travel-to-meet bypasses.

### 5. Closed-World Turn Pipeline, 3-Step Promotion & DM Gate (`game_engine/npcs/`, `game_engine/turn/core.py`, `services/turn_service.py`)
- **Stage Plan Authority & 3-Step Promotion**: Updated `stage_manager.py`, `cast_planner.py`, `reconciliation.py`, and `cast_contract.py` so seeded NPCs promote deterministically (`seeded -> acquaintance -> promoted`) across interactions without spawning unanchored characters from narration.
- **Phone & DM Access Gating**: Enforced `can_player_dm_contact` across `mechanics/social/relationships.py`, `mechanics/system/phone/`, `api/codex_phone.py`, and `cogs/contacts.py`.

### 6. Progressive Schedule Disclosure & Omnichannel Contacts | Acquaintances UI (`routine_disclosure.py`, `cogs/contacts_routine_views.py`, `web/`)
- **Progressive Routine Cards**: Added `mechanics/world/routine_disclosure.py` to mask unvisited time slots (`???`) until discovered or unlocked at Affinity `>= 40` while keeping unknown homes fog-masked below Affinity `100`.
- **O(1) Read-Only Omnichannel UI**: Built `web/src/components/Sidebar/AcquaintancesView.jsx`, `KnownRoutineCard.jsx`, updated `ContactsPanel.jsx`, and added `cogs/contacts_routine_views.py` with full 5-language localization parity (`en`, `pl`, `ms`, `de`, `zh`) and rebuilt production bundle.

---

## 📦 Distribution Packages
- **Clean Production Archive**: `releases/hikayat-v2.13.0-clean.zip` (Clean production deployment: 0 tests, 0 icon files, 0 runtime images, 0 databases, 0 personal leaks).
- **Full Development Backup**: Branch `backup/v2.13.0` & Tag `v2.13.0-full` (Preserving tracked source snapshot cleanly alongside local `backups/hikayat-v2.13.0-tests-backup.zip`).
