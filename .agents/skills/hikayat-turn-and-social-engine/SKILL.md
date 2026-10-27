---
name: hikayat-turn-and-social-engine
description: "Use this skill whenever modifying, extending, or debugging Hikayat's deterministic turn pipeline (TurnService, Phases 1-5), action/intent classification, CastPlanner & NPC presence, LLM schema validation, or the Five Normalized Models (Household/Genealogy, Intimacy Ledger, Social/Relationship Graph, Commitments & Schedules, Actor Physical State & Garment Layers)."
---

# Hikayat Turn Pipeline & Normalized Social Engine

Use this runbook when working on `services/turn_service.py`, `game_engine/`, `models/llm_schemas.py`, `mechanics/social/`, `mechanics/system/`, `mechanics/stealth/`, or `db/`.

---

## 1. End-to-End Turn Lifecycle

1. **Pre-Turn Preparation (`services/turn_service.py` -> `TurnService.prepare_and_roll_action`)**
   - Normalizes inputs across Web and Discord (`choice_index`, `direct_choice`, `custom_action_text`, `combat_target`, `intent`, `skip_minutes`, `sleep_mode`, `is_stealth` / `stance == "stealth"`, `is_item_action` / `stat == "ITEM"`).
   - Classifies custom text via `mechanics/narrative/intent.py` (`classify_action_intent`) into canonical `_VALID_INTENTS` and `_VALID_SUB_INTENTS` (`models/llm_schemas.py`).
   - Applies trait DC modifiers (`mechanics/combat/traits`) and persona/intimacy DC modifiers (`mechanics/social/persona`), deducts MP/consumables/currency, and rolls `skill_check.CheckResult`.
   - **Idempotency Guard**: If `raw_pick` already carries a resolved `check` + `char`, `prepare_and_roll_action` coerces dict `check` back into `CheckResult` without double-rolling or double-charging MP.

2. **Deterministic Phases 1–5 (`game_engine/turn/`, `game_engine/npcs/`, `game_engine/state/`)**
   - **Phase 1 — Cast & Dialogue Authority (`DETERMINISTIC_CAST`)**:
     - Managed by `game_engine/npcs/cast_planner.py` (`CastPlan`), `presence.py`, `stage_manager.py`, `dialogue_tracking.py`, and `reconciliation.py`.
     - Python owns `present_npcs`, `dialogue_partners`, `bystander_npcs`, and `departing_npcs`. Never resurrect departed NPCs via prose quotation scraping; `dialogue_exit` closes active loops immediately.
   - **Phase 2 — Social, Intimacy & Physical State (`DETERMINISTIC_INTIMACY`)**:
     - Pre-turn disclosures and witness checks (`resolve_pre_turn_social_and_disclosures`, `evaluate_pre_turn_witness_detection`).
     - Post-turn reductions in `game_engine/state/social.py` and `reducers.py` (`_reduce_social_and_milestones`, `_evaluate_npc_milestones`).
   - **Phase 3 — Vitals, Economy, Combat & Inventory (`DETERMINISTIC_ECONOMY`)**:
     - State reducers in `game_engine/state/reducers.py` + `mechanics/combat/` (`core.py`, `formulas.py`, `enemies.py`, `merchant.py`).
     - Emits domain events on `mechanics/narrative/events.py` (`bus`: `LocationChangedEvent`, `NPCSpawnedEvent`, `ItemGainedEvent`, `QuestCompletedEvent`, etc.).
   - **Phase 4 — Spatial Movement & Access Gating (`DETERMINISTIC_MOVEMENT`)**:
     - Dijkstra/BFS graph routing and gate validation in `mechanics/world/locations/` (`movement.py`, `pathfinding.py`, `access_gate.py`, `hierarchy.py`).
     - Stealth state updates (`UNAWARE`, `SUSPICIOUS`, `SEARCHING`, `DETECTED`) in `mechanics/stealth/`.
   - **Phase 5 — Bounded Narration & Post-Sanitizers**:
     - Dual-model routing in `llm_client.py` (`LLM_MODEL` for prose, `LLM_UTILITY_MODEL` for background tasks, `NSFW_LLM_*` isolation for mature scenarios, 3,500-token reasoning headroom).
     - Post-generation passes: `ensure_enemy_encounter_narrative` (`game_engine/turn/core.py`), `pronoun_resolver.py`, `sanitize_comparative_cliches`, and `choices_cleaner.py`.

---

## 2. The Five Normalized Models (Critical State Invariants)

Hikayat persists complex social/world state in normalized SQLite tables rather than fragile JSON blobs (verified by `tests/test_five_normalized_models_cutover.py`):

1. **Normalized Household & Genealogy Model** (`mechanics/social/genealogy.py`, `db/social.py`)
   - Tracks canonical family trees (parents, siblings, spouses), shared residences, and household concurrency.
2. **Normalized Intimacy Ledger & Excitement Model** (`mechanics/social/persona/intimacy/ledger.py`, `mechanics/social/intimate_excitement.py`)
   - Records structured intimate events (`record_intimate_event`, `get_intimate_events`), experience transitions, and immutable appearance profiles (`appearance.py`).
3. **Normalized Social Graph & Relationship Network** (`mechanics/social/relationship_graph.py`, `relationships.py`, `affinity_engine.py`)
   - Tracks multi-axis NPC-to-player and NPC-to-NPC ties, mutual friends (`mechanics/system/phone/social_graph.py`), and romance tracks.
4. **Unified Commitments & Circadian Schedule Engine** (`mechanics/system/commitments_engine.py`, `mechanics/world/npc_schedule.py`, `time_engine.py`)
   - Commitments track promises, dates, and rendezvous windows (`add_commitment`, `get_commitment`, `cancel_commitment`).
   - `npc_schedule.py` uses **5 daily minute blocks** (`0..1439`): `morning` (360–719), `lunch` (720–779), `afternoon` (780–1019), `evening` (1020–1199), `night` (1200–1439 & 0–359), with `BLOCK_BOUNDARIES` (`commute` 420, `extracurricular` 900) and weekday vs. weekend station rules.
5. **Normalized Actor Physical State & Garment Layer Model** (`mechanics/social/physical_state.py`)
   - Tracks posture, stance, composure, wetness, held props, and layered clothing/undergarment states per actor.

### Mandatory Lifecycle Hooks When Adding Normalized Tables/Columns
Whenever you add or alter normalized session-scoped tables in `db/`:
1. **Save/Load Slot Rewriting**: Register table/session-ID remapping in `db/saves.py` (`save_adventure_slot`, `load_adventure_slot`, `_rewrite_session_key_id`).
2. **Turn Rollback & Retry Cleanup**: Update `db/sessions.py` (`rollback_session_normalized_state_after_turn`, `reset_session_for_opening_retry`) and `db/core.py` (`_delete_session_child_records_only`).
3. **Schema Migration**: Add an idempotent migration helper in `db/core.py` invoked from `init_db()`, and re-export new public helpers in `db/__init__.py`.

---

## 3. Verification Checklist
```bash
pytest tests/test_five_normalized_models_cutover.py tests/test_codebase_contracts.py -q
python scripts/run_tests.py impact
```
