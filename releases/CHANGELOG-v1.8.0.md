# Changelog — Hikayat v1.8.0

**Release Date:** 2026-09-15  
**Release Type:** Minor (Modular Items & FNV Armor DT, 5-Tier Enemy Hierarchy, SQLite WAL Backend.)  
**Package:** `hikayat-v1.8.0-clean.zip`

---

## 🌟 Most Recent Changes (v1.8.0 Highlights)

### 1. Modular Item & Equipment Architecture (`mechanics/items/`)
* Modularized item subsystems into dedicated packages: weapons, armors, clothing, shields, accessories, consumables, and tags.
* Implemented Fallout: New Vegas style Damage Threshold (DT) and Damage Resistance (DR) mechanics for armor and shields.
* Separated civilian clothing ("Top") from dedicated combat body armor, headwear, and accessories.
* Re-architected weapons to function as tactical damage multipliers and stat scalers rather than flat static numbers.
* Added dual-wielding weapon mechanics and versatile weapon handling.

### 2. Modular Magic & Spells Architecture (`mechanics/spells/`)
* Modularized spells into a dedicated package with elemental tags, spell taxonomy, MP cost scaling, and class kits.

### 3. 5-Tier Enemy Hierarchy & Telegraphed Moves (`mechanics/combat/`, `enemies.py`)
* 5-tier enemy hierarchy: Minion, Standard, Elite, Champion, and Boss.
* Telegraphed intent execution (charging, casting, defending, swarming) allowing players to anticipate enemy moves and react tactically.
* Added dedicated tactical combat actions: Defensive Guard, Diplomacy Taunt, Weakness Exploit, and Evade/Tactical Flee.
* Enemy passives & affixes: Volatile, Phasing, Ethereal, Incorporeal, morale routing/fleeing, and crowd control checks.

### 4. Backend SQLite WAL Mode & Performance Indexing
* Added critical database indexes across lorebook, characters, and session_members.
* Enabled SQLite Write-Ahead Logging (WAL) mode and optimized PRAGMAs for concurrent stability.

### 5. Persistent Merchant Inventory & Timed Restocks (`mechanics/merchant.py`)
* Store item inventories now persist between visits and restock on in-game timer cycles.

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

---

## 📜 Full Release History

### [v1.8.0] - 2026-09-15
#### Added
- **Modular Item & Equipment Architecture (`mechanics/items/`)**:
  - Subsystems modularized: weapons, armors, clothing, shields, accessories, consumables, tags.
  - Fallout: New Vegas style Damage Threshold (DT) and Damage Resistance (DR) mechanics.
  - Dedicated Clothing Slot ("Top") separate from combat body armor.
  - Weapons as tactical damage multipliers and stat scalers.
  - Dual-wielding weapon mechanics and versatile weapon handling.
  - Dynamically generated starter weapons and scenario loadouts.
- **Modular Magic & Spells Architecture (`mechanics/spells/`)**:
  - Dedicated package with elemental tags, spell taxonomy, MP cost scaling, and class kits.
- **5-Tier Enemy Hierarchy & Telegraphed Moves (`mechanics/combat/`, `enemies.py`)**:
  - 5-tier ladder: Minion, Standard, Elite, Champion, Boss.
  - Telegraphed moves (charging, casting, defending, swarming) and tactical responses (Defensive Guard, Diplomacy Taunt, Weakness Exploit, Evade/Flee).
  - Affixes: Volatile, Phasing, Ethereal, Incorporeal, morale routing.
- **Backend SQLite WAL Mode & Indexing**:
  - Added critical database indexes and enabled Write-Ahead Logging (WAL) mode.
- **Persistent Merchant Inventory (`mechanics/merchant.py`)**:
  - Persistent store stocks with timer-based restocks.

#### Fixed & Polished
- **Web API Endpoint Crashes (`server.py`)**:
  - Fixed NONE stat crashes and missing character action keys in choice_index and custom action paths.
  - Restored party tuple formatting and XP awards in turn resolution.
- **NSFW LLM Startup Probing**:
  - Validates both primary and NSFW LLM endpoints on bot launch.
- **Contact Command UI Error**:
  - Fixed command syntax error in contacts view.

### [v1.7.0] - 2026-09-06
#### Added
- **Action Intent Engine Expansion (`mechanics/intent.py`)**:
  - 8 new intent categories and fast-pathing execution in `game_engine.py`.
  - Gift consumption and affection milestone memories.
- **Model Reasoning Safeguards (`llm_client.py`, `bot.py`)**:
  - Minimum 3,500 token buffer in `call_llm_json` preventing truncated JSON.
  - Startup model capability probing and alert banners.
  - 4096 token limit for story quest generation.
- **Quest UI Overhaul (`cogs/adventure.py`)**:
  - Distinct Main Story Quest and Bounty Board interactive buttons.
  - Decluttered expandable bounty cards.
- **Campus Map Expansion (`data/locations_seed.json`)**:
  - Sports Complex, Arts Wing, Tech Laboratories, Rooftop Garden.

#### Changed / Refactored
- **Contact Profile Decluttering (`cogs/contacts.py`)**:
  - Streamlined primary profile view cards.
- **Unified Item Tagging Taxonomy**:
  - Standardized item tagging taxonomy across scenarios.

#### Fixed & Polished
- **Intimate Experience & Virginity Synchronization (`mechanics/persona.py`)**:
  - Single-source-of-truth priority preventing profile desync.
- **Canonical Family Member Locking**:
  - Locked family records on creation to prevent hallucinated relatives.
- **Romance Bleed Guard**:
  - Prevented platonic characters from unintentionally flipping to romantic status.
- **Beastfolk Subspecies Appearance**:
  - Scaled beastfolk correctly receive scale descriptions instead of fur.

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
