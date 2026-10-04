# Changelog — Hikayat v2.1.0

**Release Date:** 2026-10-04  
**Release Type:** MINOR (Mechanics Domain Restructuring, Unified Web Frontend Architecture, Root Declutter, and Distribution Hardening)  
**Package:** `hikayat-v2.1.0-clean.zip`

---

## 🌟 Most Recent Changes (v2.1.0 Highlights)

### 1. Mechanics Domain Restructuring (Phase 2)
* **Problem:** Domain mechanics had previously resided in a sprawling flat layout under `mechanics/`, mixing combat math, narrative heuristics, social intimacy pipelines, and world locations.
* **Feature:** Restructured `mechanics/` into cohesive, isolated sub-packages:
  - **`mechanics/combat/`**: Encapsulates combat equipment, tactical items, modular spells, trait systems, enemy hierarchy definitions, and battle deck calculations.
  - **`mechanics/narrative/`**: Contains anti-cliche filters, style supremacy framing, dynamic narrative paragraph quotas, and tone enforcement.
  - **`mechanics/social/`**: Houses persona models, family genealogy, canonical relationships, and the 3-track intimate experience pipeline.
  - **`mechanics/system/`**: Manages the persistent minute-by-minute time engine, in-game smartphone actions, and token memory budget compaction.
  - **`mechanics/world/`**: Organizes location trees, waypoint resolution, spatial routing, campus mobility, and World Forge seed mechanics.

### 2. Unified Web Frontend Architecture (Phase 3)
* **Problem:** Frontend sources and build assets were fragmented across legacy locations, causing potential build drift and deployment discrepancies.
* **Feature:** Unified all React SPA components, build scripts, and production bundles into `web/`:
  - Centralized single-page React frontend under `web/src/` with updated Vite and Tailwind configurations.
  - Production distribution assets compiled to `web/dist/` for native FastAPI serving without requiring Node.js at runtime.
  - Updated launcher scripts (`run_web.bat`, `run_web_share.bat`) and `server.py` static mounts to target unified paths.

### 3. Root Declutter & Clean Architecture (Phase 1)
* **Problem:** Auxiliary utilities, debug scripts, and executables clustered in the root directory, complicating repository maintenance.
* **Feature:**
  - Relocated background utilities and cloudflared tunnels to `bin/tunnel.py`.
  - Removed scratch scripts and obsolete debug harnesses from source control.
  - Enforced strict `.gitignore` rules against binary executables, process locks, and root database fallbacks.

### 4. Privacy & Personal Data Sanitization
* **Problem:** Test mock characters and logs risked containing personal developer identifiers or absolute local directory paths.
* **Feature:**
  - Fully sanitized test fixtures and mock models to use generic identifiers (`Hero`, `Player`).
  - Audited codebase paths to ensure 100% relative path resolution (`%~dp0`, `BASE_DIR`), guaranteeing zero personal path leakage.
  - Hardened packaging scripts with automated regex scanning for personal and environment identifiers.

### 5. Automated Release Packaging & Exclusion
* **Problem:** Portable distributions occasionally bundled extraneous development assets (icons, build caches, temporary databases).
* **Feature:**
  - Enhanced `scripts/package_release.py` to produce clean `.zip` archives excluding `icon/`, caches, and binary executables.
  - Output standard clean package: `releases/hikayat-v2.1.0-clean.zip`.

---

## 🏷️ Version System Specification

Hikayat adheres to [Semantic Versioning (SemVer 2.0.0)](https://semver.org/spec/v2.0.0.html):
- **MAJOR (X.0.0):** Architectural overhauls, database engine changes, major operational paradigm transitions.
- **MINOR (X.Y.0):** Substantial new features, new command suites, platform expansions, pipeline subsystems.
- **PATCH (X.Y.Z):** Backwards-compatible bug fixes, timeout protections, platform scraper adjustments, edge-case handling.

---

## 📊 Version History Summary

| Version | Release Date | Type | Primary Milestone / Theme |
| :--- | :--- | :--- | :--- |
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
