# Changelog — Hikayat v2.3.0

**Release Date:** 2026-10-13  
**Release Type:** MINOR (Multi-Language Localization, NPC Gender & Pronoun Consistency, Combat Stance & Affinity Synergy, Sub-Facility Waypoint Preservation, Web UI Internationalization)  
**Package:** `hikayat-v2.3.0-clean.zip`

---

## 🌟 Most Recent Changes (v2.3.0 Highlights)

### 1. Multi-Language & Internationalization Subsystem (`localization/`, `web/src/locales/`, `web/src/i18n.js`)
* **Problem:** Hikayat was previously tied exclusively to English strings and lemmas, limiting accessibility for non-English players and preventing localized gameplay narrative.
* **Feature:** Implemented full trilingual internationalization across both Python backend and React frontend:
  - **Trilingual Core Support**: Full support for English (`en`), Polish (`pl`), and Malay (`ms`).
  - **Affix Translations & Canonicalization (`translate_affix`, `canonicalize_affix`)**: Equipment affixes and modifiers are seamlessly translated while canonicalizing internally for consistent combat formulas.
  - **Multilingual Item Lemmas & Icon Resolvers (`get_item_icon`)**: Unicode item icons dynamically map across localized vocabulary (e.g., weapons, shields, scrolls, potions).
  - **Localized Intent & Navigation Phrasing**: Conversation exit phrases, movement prefixes, and scenario enemy generation recognize localized commands and keywords.
  - **React Frontend Integration**: Configured `i18next` with `LanguageSwitcher.jsx` component, dynamic locale loading, and persistent user language preferences.

### 2. NPC Identity, Gender & Pronoun Consistency Engine (`game_engine/keywords.py`, `game_engine/prompts.py`, `llm_client.py`)
* **Problem:** LLMs occasionally suffer from gender drift or pronoun confusion during extended narrative scenes involving multiple companions or NPCs.
* **Feature:** Built an anti-hallucination pronoun consistency engine:
  - **Post-Generation Pronoun Sanitizer (`sanitize_npc_pronoun_consistency`)**: Deterministically scans and corrects gender and pronoun mismatches in generated narrative against registered NPC directory records.
  - **Immutable Identity Directives**: Reinforced `SYSTEM_PROMPT` and `GM_SHARED_RULES` with strict `MANDATORY GENDER & PRONOUN CANON` rules.
  - **Prompt Context Enrichment**: `_describe_tracked_entity` and `format_persona_summary` explicitly tag active NPCs with canonical gender and pronouns (e.g., `he/him`, `she/her`).

### 3. Combat Stance & Affinity Mechanics Synergy (`mechanics/social/relationships.py`, `cogs/contacts.py`)
* **Problem:** Companion combat readiness and martial roles operated largely in isolation from interpersonal social dynamics.
* **Feature:** Synchronized affinity standing with companion combat cooperation:
  - **0-300 Affinity Scale Milestones**: Structured progression tiers (*Stranger*, *Acquaintance*, *Friend*, *Close Friend*, *Confidant*) mathematically clamped and calculated.
  - **Affinity-Driven Recruitment & Readiness**: Companion recruitment costs and tactical cooperation scale with affinity standing.
  - **Combat Stance Mechanics**: Enhanced party member stance selection reflecting interpersonal bond and martial disposition.

### 4. Sub-Facility Waypoint Preservation & Multi-Occupant Roster (`mechanics/world/locations/movement.py`, `db/world.py`)
* **Problem:** Movement between sub-zones occasionally collapsed granular micro-spatial locations (e.g. desks, meeting tables) into generic parent facility names.
* **Feature:** Granular waypoint architecture and multi-occupant directory support:
  - **Hierarchical Waypoint Retention**: Preserves complete navigation paths (*Zone ➔ Facility ➔ Sub-Facility*) across state changes and movement reconciliations.
  - **Multi-Occupant Facility Directory**: Enables multiple NPCs to inhabit shared rooms and sub-facilities without overwriting or losing micro-spatial lorebook references.
  - **Lorebook Gender Parity**: Synchronized school directory and lorebook entity schemas with verified gender attributes.

### 5. Modern Web Application Enhancements & Internationalization (`web/src/`)
* **Problem:** Web UI needed integrated language selection controls and enhanced settings persistence.
* **Feature:** Frontend enhancements and component polish:
  - **Language Switcher Component (`LanguageSwitcher.jsx`)**: Responsive language selector integrated across top navigation and settings menus.
  - **Settings & Saves Modals Polish**: Localized UI strings, enhanced settings synchronization via WebSockets and REST APIs.
  - **Updated Production Bundle**: Pre-compiled production build in `web/dist/` ready for immediate out-of-the-box deployment.

### 6. Expanded Automated Contract Test Suites (`tests/`)
* **Feature:** Added dedicated unit and integration suites ensuring zero regressions:
  - `test_localization_mechanics.py`: Validates trilingual affix translations, item icon lemmas, and dialogue exit phrasing.
  - `test_npc_gender_and_pronoun_consistency.py`: Verifies pronoun immutability rules, context formatting, and narrative sanitization.
  - `test_affinity_and_combat_stance.py`: Tests 0-300 affinity milestones, clamp functions, and combat stance integration.
  - `test_subfacility_waypoint_preservation.py`: Confirms multi-occupant facility directories and micro-spatial waypoint preservation.

---

## 📦 Distribution & Packaging
* **Clean Distribution Archive**: Excludes development test suites (`tests/`), icons (`icon/`), runtime databases (`*.db`), logs (`*.log`), and process locks.
* **Zero Private Information**: Automated audit ensures absolute absence of local file paths or developer credentials.
