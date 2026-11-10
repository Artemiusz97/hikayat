# Hikayat Release Changelog — v2.10.0

**Release Date:** 2026-11-10  
**Type:** Minor Release  
**Milestone:** Flow-Sensitive Static Bug Gate, Deterministic Social State Snapshots, Privacy Nudge Hierarchy, Contract Indexing & Packaging Hardening

---

## 🌟 Overview

Hikayat **v2.10.0** delivers a major stability, verification, and engine integrity release. It introduces the **Flow-Sensitive Static Bug Gate** (`scripts/static_check.py`) enforcing definite-assignment invariants across all 260+ Python modules, wires **Full Social & Contract State Snapshots** into the turn lifecycle with atomic rollback parity, refines the **Privacy Nudge & Spatial Access Engine** for discreet encounters, adds specialized SQLite partial indexing for active covenants, and hardens the clean distribution packaging pipeline.

---

## 🚀 Key Implementations & Enhancements

### 1. Flow-Sensitive Static Bug Gate & Definite Assignment (`scripts/static_check.py`)
- **Dual-Engine Static Gate**: Introduced `scripts/static_check.py`, pairing high-signal pylint error checks with a custom flow-sensitive definite assignment analyzer designed specifically for long-form game engine dispatchers.
- **Zero-Unbound Guarantee**: Scans and enforces that no local variable can be read across conditional branches or exception handlers without prior assignment, and flags shadowed module imports.
- **Contract Verification Gate**: Verified 0 findings across all 262 project files with `scripts/static_baseline.json`.

### 2. Full-Fidelity Social & Contract Turn Snapshots (`services/turn_service.py`, `db/`)
- **Atomic Pre/Post Turn State Snapshots**: Integrated `db.snapshot_session_social_state_for_turn` alongside physical state snapshots and contract turn snapshots into `TurnService` before and after turn execution.
- **Robust Session Rollback & Retry**: Enhanced `reset_session_for_opening_retry` and `reset_character_for_new_adventure` in `db/sessions.py` to safely reset scenario bindings, unlink stale active sessions, and clean up pact-locked inventory items without constraint violations.
- **Database Index Optimization**: Added partial index `idx_inventory_pact_contract` in `db/core.py` for high-throughput pact-bound item lookups.

### 3. Privacy Nudge & Spatial Access Hierarchy (`mechanics/world/locations/access_gate.py`)
- **Affiliated Sibling Room Ranking**: Re-architected `get_privacy_nudge_choice` to prioritize affiliated sub-nodes and secluded sibling rooms (balconies, alcoves, corners, terraces) within the current facility.
- **Context-Preserving Transition Fallbacks**: Prevents invalid room jumping by falling back to secluded sibling rooms under the same facility hierarchy before defaulting to generic room props.

### 4. Opening Scene & Intent Generation Resilience (`game_engine/turn/generation.py`)
- **Exception Containment & Fallbacks**: Wrapped LLM schema parsing and starting hook context generation in defensive exception guards with deterministic fallback narratives.
- **Definite Assignment Scoping**: Fixed variable scoping for scenario keys and starting hook contexts across narrative generation pipelines.

### 5. Contract & Pact Cost Computation Refinements (`mechanics/pacts/resolver.py`)
- **Streamlined Pact Invocations**: Standardized pact casting cost calculation (`compute_pact_cast_costs`) and invocation permission enforcement in `TurnService`.
- **Patron Compendium Cleanup**: Ensured `user_patron_compendium` correctly updates active contract flags upon session lifecycle events.

### 6. Clean Distribution Packaging Hardening (`scripts/package_release.py`)
- **Strict Test & Tool Exclusion**: Updated `scripts/package_release.py` to strictly exclude local-only testmon metadata (`.testmondata*`), test runners (`run_tests.py`), simulation harnesses (`simulate_*.py`), and static check utilities from production distribution zips.
- **Zero Personal Path Verification**: Automated scanning strictly guarantees zero personal directories, machine usernames, or local filesystem leaks.

---

## 📦 Distribution Packages
- **Clean Production Archive**: `releases/hikayat-v2.10.0-clean.zip` (Clean production deployment: 373 clean files, 0 tests, 0 icon files, 0 runtime images, 0 databases, 0 personal leaks).
- **Full Development Backup**: Branch `backup/v2.10.0` & Tag `v2.10.0-full` (Preserving 100% of test suites, test runners, and simulation harnesses).
