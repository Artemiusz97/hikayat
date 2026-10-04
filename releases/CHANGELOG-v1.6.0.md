# Changelog — Hikayat v1.6.0

**Release Date:** 2026-09-01  
**Release Type:** Minor (Living World, Time Engine & Intimate Overhaul.)  
**Package:** `hikayat-v1.6.0-clean.zip`

---

## 🌟 Most Recent Changes (v1.6.0 Highlights)

### 1. Time, Day/Night Cycle & Fatigue System (`mechanics/time_engine.py`)
* Minute-by-minute persistent time tracking advancing realistically per turn.
* 8 distinct time phases (Dawn, Morning, Afternoon, Dusk, Night, Midnight, etc.) with dynamic time-of-day badges on the Game Dashboard embed.
* Days Adventured and Day-of-the-Week progression tracking.
* Dynamic "Sleep / Rest" actions in open hub exploration with fatigue debuffs and full HP/MP recovery upon sleep.

### 2. Smartphone, Texting & Appointment Meetups (`mechanics/phone.py`, `waypoints.py`)
* In-game smartphone interface with `/phone` command and direct NPC texting.
* Dynamic date rendezvous, hangout scheduling, and meetup waypoints.
* Cross-zone companion mobility (`mechanics/mobility.py`): NPCs travel across town and meet the player at agreed hubs/cafes.

### 3. Unified Intent Classification Engine (`mechanics/intent.py`)
* Deterministic intent scanner classifying actions into exploration, social dates, combat, romantic advances, residence visits, and intimate acts.
* Eliminates false-positive combat triggers during peaceful roleplay.

### 4. 3-Track Experience & Act Preferences Overhaul (`mechanics/persona.py`)
* Separated intimate experience progression into 3 independent tracks (Vaginal, Oral, and Manual) with realistic ratcheting.
* Symmetrical act preferences (likes/dislikes) and proactive NPC autonomous initiation.
* 4-tier past partner and encounter scaling (Prude, Moderate, Bold, Shameless).

### 5. Genealogy & Family Line Tracker (`mechanics/genealogy.py`)
* Added generational relationships (parents, siblings, spouses, children) to dynamically maintain consistent family lineages.

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
| **v1.6.0** | 2026-09-01 | Minor | Living World, Time Engine & Intimate Overhaul. |
| **v1.5.2** | 2026-08-20 | Patch | Biome Diversity, Fail-Forward & Map Polish. |
| **v1.5.1** | 2026-08-14 | Minor | Tactical Combat, Loadouts & Factions Overhaul. |
| **v1.4.0** | 2026-08-05 | Minor | Quest Log, Bounty Board & 10-Chapter Campaign. |
| **v1.3.0** | 2026-08-03 | Minor | Dynamic NSFW Routing & Fallback Cascade. |
| **v1.2.0** | 2026-08-03 | Minor | Locations, Debug Suite & Roster Expansion. |
| **v1.1.0** | 2026-08-01 | Patch | LLM Reliability & Narrative Balancing. |
| **v1.0.0** | 2026-07-25 | **MAJOR** | Genesis Release: Core RPG Engine, Discord Bot, FastAPI Web UI & Audio Engine. |

---

## 📜 Full Release History

### [v1.6.0] - 2026-09-01
#### Added
- **Time, Day/Night Cycle & Fatigue System (`mechanics/time_engine.py`)**:
  - Minute-by-minute persistent time, 8 time phases, dynamic time-of-day badges.
  - Sleep/Rest actions, cumulative fatigue debuffs, and full HP/MP recovery.
- **Smartphone & Texting System (`mechanics/phone.py`, `waypoints.py`)**:
  - `/phone` texting interface, appointment scheduling, rendezvous waypoints.
  - Cross-zone companion mobility (`mechanics/mobility.py`).
- **Unified Intent Classification Engine (`mechanics/intent.py`)**:
  - Eliminates false-positive combat triggers during peaceful roleplay.
- **3-Track Experience & Act Preferences Overhaul (`mechanics/persona.py`)**:
  - 3 independent tracks (Vaginal, Oral, Manual), symmetrical act preferences, proactive NPC initiation.
- **Genealogy & Family Line Tracker (`mechanics/genealogy.py`)**:
  - Dynamic generational family relationships.

#### Changed / Refactored
- **Paginated Contact Profile Embeds (`cogs/contacts.py`)**:
  - Dropdown tabs: Overview, Combat Sheet, Persona, Intimate Profile.
- **Social & Date Dialogue Pacing (`game_engine.py`)**:
  - Natural romantic and social dialogue without forced combat triggers.

#### Fixed & Polished
- **Companion & Location Persistence (`mechanics/locations.py`)**:
  - Fixed interior sub-location persistence.
- **Intimate Attribute Disclosure Guard**:
  - Protected intimate attributes behind Info Disclosure Level >= 3.

### [v1.5.2] - 2026-08-20
#### Added
- **Procedural Multi-Pattern Biome Engine (`namegen.py`, `mechanics/locations.py`)**:
  - Procedural generators for fantasy biomes with varied patterns.
- **"Failing Forward" Dramatic Resolution (`game_engine.py`)**:
  - Failed skill checks escalate complications rather than halting gameplay.
- **Success Percentage Toggle (`cogs/settings.py`)**:
  - `/settings percentages` command to show/hide raw success percentages.
- **Dynamic Map UI Badges (`cogs/adventure.py`)**:
  - Zone badges and quest markers on travel menus.

#### Changed / Refactored
- **Location & Scene Decoupling**:
  - Decoupled physical locations from decorative scene titles.
- **Gender-Specific Starter Equipment**:
  - Gender separation on starter gear templates.

#### Fixed & Cleaned Up
- **Intimate Profile Privacy**:
  - Fixed premature visibility of intimate attributes.
- **Combat Victory/Defeat Formatting**:
  - Cleaned up embed newlines.
- **Legacy Code Removal**:
  - Removed obsolete quest update helpers and regex blocks.

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
