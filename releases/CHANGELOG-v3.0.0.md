# Hikayat Release Changelog — v3.0.0

**Release Date:** 2026-11-15  
**Type:** Major Release  
**Milestone:** Living World NPC Autonomy, Epistemic Asymmetry Matrix (`epistemic_facts` & `epistemic_knowledge`), Venue Activity Tags, Boundary-Tick Simulation & Omnichannel Fog-of-War Parity

---

## 🌟 Overview

Hikayat **v3.0.0** introduces a major simulation paradigm shift: the **Living World NPC Autonomy & Epistemic Asymmetry Matrix**. Rather than treating secrets and off-screen NPC behavior as flat global flags or ungrounded AI prose, Hikayat now tracks **who knows what, how they learned it, how confident they are, and whether they can confront, leak, or corroborate it** inside normalized SQLite tables—paired with deterministic off-screen NPC autonomy across daily time-block boundaries and strict server-side Fog-of-War isolation across Web and Discord.

---

## 🚀 Key Implementations & Enhancements

### 1. Epistemic Asymmetry Matrix Schema & Rollback (`db/epistemic.py`, `db/core.py`, `db/saves.py`)
- **Per-Holder Knowledge Modeling**: Added SQLite schema v55 tables `epistemic_facts` and `epistemic_knowledge` joined by `(session_id, fact_key)` so multi-witness containment (`containment_state`) and conflicting per-holder alibis (`alibi_claim`, `alibi_witness_key`) stay isolated without overwriting one another.
- **Proof Transitions & 10-Turn Rollback**: Implemented `downgrade_or_upgrade_proof_ref` (`clue:<id>`, `inv:<id>`, `photo:<inv_id>`, `dm:<npc>:<turn>`), bounded 10-turn `_turn_snapshots` inside `metadata_json`, save/load slot remapping (`db/saves.py`), and turn rollback parity (`db/sessions.py`, `services/turn_service.py`).
- **Strict Server Fog-of-War Summary**: Added `build_player_fog_of_war_summary` so hidden off-screen gossip hops (`player_aware == 0`) are never leaked to client payloads.

### 2. Deterministic Epistemic Engine & Gossip Propagation (`mechanics/social/epistemic_engine.py`, `epistemic_propagation.py`)
- **Scene Witness Capture**: Focus-weighted witness detection supporting companion alignment, mask/concealment culprit anonymization, and dialogue/public-venue overhearing.
- **Containment & Neutralization**: Deterministic containment actions (hush, bribe, threaten, discretion, confide, deny, proof, leverage) with kin/roommate/best-friend resistance (`+2 DC`), plus deterministic witness neutralization during combat knockout or death.
- **Boundary-Tick Propagation & Signal Fencing**: Across time-block boundaries, the engine executes `spotted_window -> active` transitions, daily rumor heat decay, 1-hop social gossip propagation, 2+ source corroboration, Caught Lying alibi checks, kin/roommate alerts, Watch-role faction escalations, and server-side fencing of LLM `EpistemicSignal` outputs.

### 3. Off-Screen NPC Autonomy & Activity Tags (`mechanics/world/npc_autonomy.py`, `mechanics/social/activity_tags.py`, `mechanics/system/time_engine.py`)
- **Autonomous World Simulation**: Deterministic off-screen schedule overrides, romance shields, and boundary-tick deltas running inside `UnitOfWork` transactions when in-game time crosses schedule boundaries.
- **Venue-Aware Activity Tags**: Mapped normalized NPC activities (`studying`, `sparring`, `tending_stall`, `patrolling`, etc.) into 5-language display labels with context swaps, telltale gating, and join-activity conversation seeds (`mechanics/social/conversation_choices.py`, `deck.py`).

### 4. Presence Cutover, Z2 Filtering & Turn Reconciliation (`mechanics/world/presence_resolver.py`, `game_engine/`, `services/turn_service.py`)
- **Presence & Routine Integration**: Added Tier 5 presence caps, autonomy routine overlays, pair auto-joins, and pre-turn witness feed alignment (`api/adventure.py`, `game_engine/npcs/cast_planner.py`, `stage_manager.py`).
- **Context Filtering & Messaging Integration**: Added Z2 epistemic filtering in `game_engine/context.py`, discreet encounter tracking (`mechanics/social/discreet_encounters.py`), and phone/DM social graph reconciliation (`mechanics/system/phone/messaging.py`, `social_graph.py`).

### 5. Omnichannel Web, Discord & 5-Locale Parity (`api/`, `cogs/`, `web/`)
- **Web & Discord UI**: Updated `WorldOutcomeSidebar.jsx`, `KnownRoutineCard.jsx`, `GameView.jsx`, `api/codex_phone.py`, `cogs/adventure/embeds.py`, and `cogs/contacts_routine_views.py` to surface active spotted witnesses, autonomy outcomes, and Fog-of-War-safe clues.
- **Localization & Bundle**: Synchronized 5-language translations across `en.json`, `pl.json`, `ms.json`, `de.json`, `zh.json` and rebuilt production assets (`web/dist/`).

---

## 📦 Distribution Packages
- **Clean Production Archive**: `releases/hikayat-v3.0.0-clean.zip` (Clean production deployment: 0 tests, 0 icon files, 0 runtime images, 0 databases, 0 personal leaks).
- **Full Development Backup**: Branch `backup/v3.0.0` & Tag `v3.0.0-full` (Preserving tracked source snapshot cleanly alongside local `backups/hikayat-v3.0.0-tests-backup.zip`).
