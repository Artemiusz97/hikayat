# Changelog — Hikayat v1.5.1

**Release Date:** 2026-08-14  
**Release Type:** Minor (Tactical Combat, Loadouts & Factions Overhaul.)  
**Package:** `hikayat-v1.5.1-clean.zip`

---

## 🌟 Most Recent Changes (v1.5.1 Highlights)

### 1. Tactical Combat & Companions (`mechanics/combat.py`, `cogs/adventure.py`)
* Added friendly companion AI support and multi-target engagement.
* Built detailed Combat Summary and Turn Summary embed breakdowns with companion vitals, party actions, and dedicated combat logs.
* Added 7 code-driven tactical combat choices (Attack, Defend, Magic, Item, Flee).

### 2. Adventure Starting Loadouts (`cogs/character.py`, `cogs/adventure.py`)
* Decoupled class/gear from character creation.
* Scenario-specific classes and equipment are selected interactively upon starting an adventure (`/adventure start`).

### 3. Dual-Model Utility Architecture (`config.py`, `llm_client.py`)
* Added `LLM_UTILITY_MODEL` to offload background tasks (clue parsing, quest matching, bounties, shop restocking) to fast models while saving main models for narration.

### 4. Quest Item Auto-Success (`game_engine.py`, `cogs/adventure.py`)
* Added ITEM stat choices allowing players with quest items to bypass skill checks.

### 5. Dedicated Factions System (`cogs/factions.py`)
* Extracted factions into a standalone cog with `/factions list` and `/factions detail`.

---

## 🏷️ Version System Specification

Hikayat adheres to [Semantic Versioning (SemVer 2.0.0)](https://semver.org/spec/v2.0.0.html):
- **MAJOR (X.0.0):** Architectural overhauls, database engine changes, incompatible configuration breaks.
- **MINOR (X.Y.0):** Substantial new features, new command suites, platform expansions, pipeline subsystems.
- **PATCH (X.Y.Z):** Backwards-compatible bug fixes, timeout protections, platform scraper adjustments, edge-case handling.

---

## 📊 Version History Summary

| Version | Release Date | Type | Primary Milestone / Theme |
| :--- | :--- | :--- | :--- |
| **v1.5.1** | 2026-08-14 | Minor | Tactical Combat, Loadouts & Factions Overhaul. |
| **v1.4.0** | 2026-08-05 | Minor | Quest Log, Bounty Board & 10-Chapter Campaign. |
| **v1.3.0** | 2026-08-03 | Minor | Dynamic NSFW Routing & Fallback Cascade. |
| **v1.2.0** | 2026-08-03 | Minor | Locations, Debug Suite & Roster Expansion. |
| **v1.1.0** | 2026-08-01 | Patch | LLM Reliability & Narrative Balancing. |
| **v1.0.0** | 2026-07-25 | **MAJOR** | Genesis Release: Core RPG Engine, Discord Bot, FastAPI Web UI & Audio Engine. |

---

## 📜 Full Release History

### [v1.5.1] - 2026-08-14
#### Added
- **Tactical Combat & Companions (`mechanics/combat.py`, `cogs/adventure.py`)**:
  - Companion AI, multi-target engagement, Combat/Turn Summary embeds, 7 tactical choices.
- **Adventure Starting Loadouts (`cogs/character.py`, `cogs/adventure.py`)**:
  - Decoupled class/equipment from character creation to adventure start.
- **Dual-Model Utility Architecture (`config.py`, `llm_client.py`)**:
  - `LLM_UTILITY_MODEL` for background tasks.
- **Quest Item Auto-Success**:
  - Automatic skill check bypass when holding relevant quest items.
- **Dedicated Factions System (`cogs/factions.py`)**:
  - Standalone factions cog with `/factions list` and `/factions detail`.
- **Dynamic Intimate Profiles (`mechanics/persona.py`)**:
  - ~30-item pools for sensitive spots and turn-ons.

#### Changed / Refactored
- **Persona Module Consolidation**:
  - Unified appearance, traits, mannerisms into a single module.
- **Traits & Preferences Separation**:
  - Distinct Traits (max 3) and Preferences (max 3).
- **Real-Time Settings Application**:
  - `/settings` changes apply immediately to active sessions.
- **Adventure Reset Flow**:
  - Starting a new adventure cleanly resets stats, conditions, and starting gear.

#### Fixed & Cleaned Up
- **Combat Clue Suppression**:
  - Disabled investigation clues during active combat turns.
- **Combat Narrative Immersion**:
  - Stripped raw HP digits from narrative prose.
- **Status Effect Sanitization**:
  - Capped status effects to concise 1-2 word descriptors.
- **Removed Obsolete Systems**:
  - Deprecated world_events and relic_collection code.

### [v1.4.0] - 2026-08-05
#### Added
- **Quest Log & Bounty Board (`db.py`, `cogs/adventure.py`)**:
  - Interactive `/quest` and `/bounty` commands with objectives and rewards.
- **10-Chapter Procedural Campaign System (`game_engine.py`)**:
  - Structured 10-chapter campaign progression.
- **Physical Appearance Expansion (`mechanics/appearance.py`)**:
  - Expanded physical appearance attributes and gender visibility.

#### Changed & Fixed
- **Structured Schema Quest Updates**:
  - Moved quest updates directly into JSON OUTCOME_SCHEMA.
- **Discord UI Interaction Timeouts**:
  - Added instant `interaction.response.defer()` calls.
- **SSL Certificate Configuration**:
  - Configured certifi CA bundle and unverified SSL context fallback.

### [v1.3.0] - 2026-08-03
#### Added
- **Dynamic NSFW Model Routing**:
  - Dedicated `NSFW_LLM_MODEL` / `NSFW_LLM_API_KEY` environment variables.
- **LLM Fallback Cascade & Timeout Controls**:
  - Multi-model fallback chains with per-attempt timeout management.
- **Opening Narrative Fallback Guardrail**:
  - Embedded SCENE_SCHEMA in initial prompts to prevent blank scenes.

### [v1.2.0] - 2026-08-03
#### Added
- **Location Tree & Dynamic Discovery**:
  - Tiered location navigation, fast travel dropdowns, dynamic location context.
- **Developer Debug Suite**:
  - `/debug` command with stat overrides and success modifiers.
- **Character Roster Expansion**:
  - Increased character slot limit from 3 to 6.

### [v1.1.0] - 2026-08-01
#### Added & Fixed
- **LLM Robustness & Concurrency Control**:
  - Rate-limiting semaphores, 120s timeouts, json_repair fallback extractors.
- **Narrative Length Balancing**:
  - Rebalanced turn narrative lengths between outcome and scene.
- **Active Session State Fix**:
  - Fixed active character session persistence bug on bot restart.

### [v1.0.0] - 2026-07-25
#### Added
- **Core RPG Engine**:
  - Discord bot framework (`bot.py`), SQLite schema (`db.py`), LLM client (`llm_client.py`), and turn resolution engine (`game_engine.py`).
- **Web Application Interface**:
  - FastAPI server (`server.py`), Single-page Web UI (`web/index.html`, `web/app.js`, `web/styles.css`), and Web Speech TTS audio engine (`web/audio.js`).
