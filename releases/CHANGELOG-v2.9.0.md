# Hikayat Release Changelog — v2.9.0

**Release Date:** 2026-11-10  
**Type:** Minor Release  
**Milestone:** Entity Contracts & Eldritch Pacts, Realty & Property Ownership, Folklore Veil Mechanics, Social Pacing Engine, Chronicle Tapestry, and Security Sanitization Layer

---

## 🌟 Overview

Hikayat **v2.9.0** introduces significant expansion across occult, economic, and social simulation systems: the **Entity Contracts** subsystem for binding covenants with supernatural patrons, the **Realty & Safehouse** property system, the hidden **Folklore Veil** settlement engine, a mathematical **Social Pacing & Deck** engine, an interactive **Chronicle Tapestry** campaign timeline, and a comprehensive **Security & Input Sanitization Layer** protecting prompt and game state integrity.

---

## 🚀 Key Implementations & Enhancements

### 1. Entity Contracts & Eldritch Covenants
- **Binding Covenants Subsystem**: Implemented `api/contracts.py`, `cogs/adventure/views/contracts.py`, `db/contracts.py`, `mechanics/pacts/`, and `data/entity_patrons.json`. Players can negotiate formal covenants with patrons, anomalous entities, and deity archetypes.
- **Deterministic Geas & Tithes**: Pacts grant specialized traits and combat awakening buffs in exchange for deterministic rules (such as dietary restrictions, regular tithes, behavioral bans, or geas penalties).
- **Omnichannel UI**: Added interactive pact negotiation views in Discord (`views/contracts.py`) and a dedicated modal in the Web UI (`EntityContractsModal.jsx`).

### 2. Realty & Property Ownership Subsystem
- **Safehouse & Real Estate Economy**: Added `api/realty.py`, `db/properties.py`, `mechanics/world/locations/realty_catalog.py`, and `mechanics/world/locations/residences.py`.
- **Functional Housing**: Players can browse listings, lease or purchase apartments, abandoned shrines, rural cabins, and workshops across town and campus zones. Owned residences provide resting bonuses, private item stashes, warding wards against anomalies, and discrete rendezvous locations for social encounters.

### 3. Folklore Veil & Rural Settlements
- **Occult Concealment Layers**: Implemented `mechanics/world/locations/folklore_veil.py` and `mechanics/world/locations/folklore_veil_lifecycle.py` alongside `data/folklore_villages_catalog.json`.
- **Deterministic Veil Penetration**: Mythological settlements, hidden shrines, and occult landmarks remain cloaked behind spiritual veils until specific unlock conditions (folklore codex research, relic possession, or high perception checks) are met.

### 4. Social Pacing & Conversational Action Deck
- **Anti-Exhaustion Pacing Curves**: Implemented `db/social_pacing.py`, `mechanics/social/pacing.py`, and `mechanics/social/consequences.py` to prevent abrupt conversational burnout or erratic affinity swings during extended social encounters.
- **Conversational Action Deck**: Added `mechanics/social/deck.py`, providing structured social initiatives (*Inquire, Flatter, Probe, Challenge*) with predictable cooldowns and affinity outcomes.

### 5. Folklore Roster & Persistence Lifecycle
- **Mythical Entity Directory**: Implemented `mechanics/social/folklore_roster.py`, `mechanics/social/folklore_roster_lifecycle.py`, and `mechanics/social/folklore_roster_rollback.py`.
- **Database Parity**: Wired folklore NPCs into save/load slot remapping (`db/saves.py`), turn rollback (`db/sessions.py`), and child-record purging (`db/core.py`).

### 6. Chronicle Tapestry & Storylet History
- **Interactive Campaign Timeline**: Added `web/src/components/Modals/ChronicleTapestryModal.jsx` and `data/campaign_storylets_catalog.json`.
- **Visual Milestone Navigation**: Players can review completed storylets, major world state shifts, key decisions, and historical campaign records through an interactive timeline tapestry.

### 7. Security & Input Sanitization Layer
- **Defense-in-Depth Protection**: Added `api/security.py` and `mechanics/system/input_sanitizer.py` to inspect and sanitize incoming player input strings.
- **Tag Spoofing Prevention**: Automatically strips malicious prompt injection patterns, unauthorized control tags (`[ITEM_JSON]`, `[GEAR_JSON]`), and malformed characters before passing text to the LLM or SQLite.

### 8. Modular Anomalous Events Refactoring
- **Decomposed Package Structure**: Replaced the monolithic `mechanics/world/anomalous_events.py` with the modular `mechanics/world/anomalous_events/` package, segregating crisis catalogs, hazard resolvers, and spatial markers into dedicated single-responsibility modules.

---

## 📦 Distribution Packages
- **Clean Production Archive**: `releases/hikayat-v2.9.0-clean.zip` (Clean production deployment: 382 clean files, 0 tests, 0 icon files, 0 runtime images, 0 databases, 0 personal leaks).
- **Full Development Backup**: Branch `backup/v2.9.0` & Tag `v2.9.0-full` (Preserving 100% of test suites, test runners, and simulation harnesses).
