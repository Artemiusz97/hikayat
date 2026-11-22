# Hikayat (v3.6.0) — Living AI Tabletop RPG & Web Application

[![Version](https://img.shields.io/badge/version-3.6.0-blue.svg)](releases/CHANGELOG-v3.6.0.md)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![React 18](https://img.shields.io/badge/react-18.2-61dafb.svg)](web/)

Hikayat is a text-based role-playing game (RPG) where an AI language model generates the story and dialogue, while a deterministic Python game engine calculates the actual rules, rolls, and state changes. It can be played either as a Discord bot or as a web application in your browser.

---

## 🛠️ 10 Technical Innovations
*(How the engine actually works under the hood)*

### 1. Deterministic Rule Engine vs. AI Narration (Phases 1–5 Pipeline & Typed Stage Contexts)
* **What problem it solves**: In typical AI dungeon masters, the language model invents dice rolls, changes character health arbitrarily, and forgets inventory constraints, leading to hallucinations and broken rules.
* **How Hikayat works**: The game separates logic from storytelling. Every player action is first processed deterministically through the modular `services/turn/` pipeline, `game_engine/turn/` stage runners (`PreTurnState`, `PromptAssemblyState` in `game_engine/turn/phase_state.py`), and modular state reducers (`game_engine/state/reducers.py`), coordinating typed stage dataclasses in `TurnExecutionContext` (`TurnClockStage`, `CombatStageState`, `EpistemicAndWorldStage`, `TurnNotices` in `game_engine/turn_context.py`). The engine resolves skill checks, applies Fallout-style Armor DT/DR, deducts item charges, awards post-combat auto-loot recovery, and advances quest state before locking the numbers and asking the LLM to narrate what happened.

### 2. Closed-World NPC Engine, 3-Stage Population Seeder & 6-Tier Presence Resolver (`CastPlanner`, `population_seeder.py`, `presence_resolver.py`)
* **What problem it solves**: AI story games often suffer from "phantom NPCs"—characters who speak when they are not in the room, invent random shopkeepers every visit, or disappear mid-conversation.
* **How Hikayat works**: Every character belongs to a persistent closed-world database roster (`db/roster.py`) seeded with Stage 0 zero-LLM skeletons (~180–310 NPCs per world plus 68 special agent blueprints in `population_seeder.py`), lazily hydrated on first scene encounter (Stage 1), and automatically backfilled for active quests. Before each turn, a 6-tier presence resolver (`mechanics/world/presence_resolver.py`) and stage manager (`game_engine/npcs/cast_planner.py`, `stage_manager.py`) determine physically present characters—checking party companions, scheduled commitments, quest pins, home doorbell rules, and shift schedules—so the AI only writes dialogue for people who are actually there.

### 3. Graph-Based World Map, Procedural Urban Profiles & Dijkstra Pathfinding (`locations/pathfinding.py`)
* **What problem it solves**: Instead of letting the player teleport or describe traveling across impossible distances, the world needs realistic distances, access rules, and movement costs.
* **How Hikayat works**: World geography is stored in SQLite as nodes and connections across a 3-tier hierarchy (*Zone ➔ Facility ➔ Room*), enriched with procedural per-session urban city profiles (`namegen.py`) and 10-wing faction headquarters. When a player travels, the engine runs Dijkstra’s shortest-path algorithm to calculate transit time, stamina cost, travel fares, locked door requirements, and curfew checks before moving the player.

### 4. Mathematical Alert State Machine & Live Stealth Projection (`mechanics/stealth/`)
* **What problem it solves**: Stealth in text games usually relies on the AI guessing whether a guard notices you, or fails to keep action choices synchronized with your stealth posture.
* **How Hikayat works**: Stealth uses a mathematical alert state machine per NPC (`UNAWARE`, `SUSPICIOUS`, `SEARCHING`, `DETECTED`). The engine calculates noise levels from armor weight, companion footsteps, lighting conditions, and player action loudness, projects per-user stealth states (`project_stealth_state_for_user`), and dynamically synchronizes stealth/distraction choices (`sync_stealth_choices_for_toggle`) when toggling stealth on or off.

### 5. Multi-Engine Quest Architecture, Threat Clocks & Forensic Dossiers (`game_engine/quest_agency.py`, `mechanics/narrative/dossier_compiler.py`)
* **What problem it solves**: Quests in AI games easily lose focus, forget objectives, or conclude abruptly without resolving clues or cast identities.
* **How Hikayat works**: Quests run on specialized operational engines (Investigation, Bounty, Social Infiltration, Survival) backed by 6-segment Threat Clocks, Chapter Plans, and relational database tables (`quests`, `quest_dossiers`, `session_clues`). As players uncover evidence and interview witnesses, the system compiles structured forensic dossiers with verifiable leads, registers quest cast NPCs deterministically, and prevents premature turn-ins until stage conditions are satisfied.

### 6. Living World Autonomy & Epistemic Asymmetry Matrix (`npc_autonomy.py`, `epistemic_engine.py`, `db/epistemic.py`)
* **What problem it solves**: In most RPGs, NPCs never interact with each other off-screen, and every character magically knows secrets the moment something happens—or never hears rumors at all.
* **How Hikayat works**: Across time-block boundaries, the engine runs deterministic off-screen NPC autonomy (`mechanics/world/npc_autonomy.py`) alongside World Pulse regional events (`mechanics/world/world_events/`) and an Epistemic Asymmetry Matrix (`mechanics/social/epistemic_engine.py`, `epistemic_propagation.py`). Witnesses track what they saw, rumors decay or spread 1-hop across social ties with server-side Fog-of-War isolation, alibis are checked for lies, and players can confront, hush, bribe, or leverage secrets deterministically.

### 7. Declarative 41-Table Session Lifecycle Registry, Pooled `ReadUnitOfWork` & Hybrid Memory (`db/registry.py`, `db/core/`, `mechanics/system/memory/`)
* **What problem it solves**: Multi-table SQLite RPGs risk orphaned save-slot rows, broken turn rollbacks, and redundant database round-trips or bloated LLM context windows as campaigns grow.
* **How Hikayat works**: All 41 session-scoped child tables are governed by a declarative lifecycle contract (`SESSION_TABLE_REGISTRY` / `SessionTableSpec` in `db/registry.py`) driving FK-safe purge ordering, tiered save/load slot ID remapping (`db/saves.py`), deterministic turn rollback (`db/sessions.py`), and ring-buffer snapshot pruning inside the modular `db/core/` and `db/social/` packages—enforced statically alongside unused/shadow import and facade gates by `scripts/static_check.py`. Thread-safe read connection pooling (`ReadUnitOfWork`), `PRAGMA user_version` fast-path checks, and batched turn preloaders keep queries fast, while FTS5 and vector memory compaction condense older turns so long campaigns stay within token budgets.

### 8. Hybrid Reasoning Streaming, Dual-Model Cascade & Split Stall Guardrails (`llm_client.py`)
* **What problem it solves**: Streaming structured JSON from local or hybrid-reasoning models often stalls on long KV prefills, leaks `<think>` blocks, or wastes large-model latency on routine utility classification.
* **How Hikayat works**: Live turns stream prose in real time via `DualModeStreamingExtractor` (`@@TITLE:`, `@@OUTCOME`, `@@NEXT`, `@@CHOICES`, `@@META`) with transparent JSON fallback, split Time-To-First-Token (`LLM_TTFT_TIMEOUT`) and inter-chunk idle timers (`LLM_CHUNK_IDLE_TIMEOUT`), hybrid reasoning token ceilings (`LLM_THINKING_MAX_TOKENS`), and Chain-of-Thought suppression (`LLM_SUPPRESS_NARRATION_COT`). Meanwhile, `LLM_UTILITY_MODEL` handles fast background extraction/classification, `NSFW_LLM_*` isolates mature scenarios, and fallback cascades handle rate limits seamlessly.

### 9. 5-Language Dictionary Canonicalization & Anti-Drift Pronoun Engine (`localization/`, `game_engine/pronoun_resolver.py`)
* **What problem it solves**: Multi-language support often breaks formatting, and language models frequently mix up character pronouns or demographic traits during long scenes.
* **How Hikayat works**: Game actions, combat choices, UI labels, and inventory metadata synchronize across English, Polish, Malay, German, and Simplified Chinese in both Python dictionaries and React i18n JSON bundles. An automated pronoun resolver checks entity genders against database IDs to prevent models from drifting mid-scene.

### 10. Headless Omnichannel Game Loop & Zero-Turn Inspection Service (`services/turn/`, `services/examine_service.py`)
* **What problem it solves**: Supporting both a Discord bot and a web application usually means duplicating game logic or drifting between interfaces.
* **How Hikayat works**: Both `TurnService` (`services/turn/` behind `services/turn_service.py` for turns Phases 1–5) and `get_examine_payload` (`services/examine_service.py` for zero-turn scene and tactical inspection with LRU/TTL prose caching and strict stat/secret scrubbing) run headlessly in Python services, driving Discord slash commands/buttons and the modular FastAPI `api/adventure/` REST/WebSocket routes from a single source of truth.

---

## 🎮 10 Unique Gameplay Features
*(What you actually experience as a player)*

### 1. Acrylic Glassmorphism Web UI, 12 Scenario Backdrops & Discord Parity
* **What it looks like**: Play on Discord using slash commands and interactive decks, or launch the React 18 Web SPA featuring frosted Acrylic panels (`Full`, `Focused`, and `Solid` modes with 5%–95% opacity), drop-in custom fonts (`custom_fonts/`) or curated Google Font presets, adjustable text scaling (`70%–130%`), and 12 illustrated `.webp` scenario backdrops.
* **How it plays**: Backdrops smoothly crossfade per campaign with OKLCH time-of-day atmospheric color grading (*Dawn, Day, Dusk, Night*) and an optional blurred ambient scene-artwork mode. Explore your chronicle through the searchable **Turn History Modal** and navigate connected zones in a native `<dialog>` **World Map Modal** with active quest tabs and sub-room access badges.

### 2. Zero-Turn Scene Examine, Tactical Action Dock & 5-Mode Quick Belt (`ExamineModal.jsx`, `TacticalActionDock.jsx`, `QuickBeltPopover.jsx`)
* **What it looks like**: A persistent sidebar action dock, quick-use consumable belt, and a dedicated **Examine** button (`0 Turns`) on both Web and Discord.
* **How it plays**: Inspecting a scene costs zero turns and presents live structured snapshots—present NPCs (with posture, visible attire, `PER`-tier mood tells, and instant *Use Item* / *Gift* buttons), dropped items ready for one-click pickup, active leads, stealth/privacy/witness awareness, and enemy combat weaknesses/intents. Out of combat, the 5-mode consumable classifier automatically separates instant **Quick Use** healing/buffs from turn-consuming food, drinks, gifts, and covert items.

### 3. Turn-Based Tactical Combat with Telegraphed Moves, Armor DT/DR & Auto-Loot
* **What it looks like**: A structured 7-slot combat menu (*Attack, Defend, Magic, Item, Flee, Tactician, Switch Target*) with toggleable enemy HP bars and intent readouts.
* **How it plays**: Enemies telegraph upcoming actions so you can time blocks, dodges, counters, or interrupts against Fallout-style flat Damage Threshold (DT) and percentage Damage Resistance (DR). Defeating foes deterministically awards post-combat auto-loot into your inventory without losing drops to narration gaps.

### 4. Modular 8-App In-Game Smartphone (`/phone`, `web/src/components/Phone/`)
* **What it looks like**: A sleek in-game smartphone modal organized into 8 purpose-built apps (*Home, DMs, Feed, Photos, Planner, Shop, Bounties, Realty*).
* **How it plays**: Text NPCs directly, scroll through local town or school gossip feeds that evolve with World Pulse events, browse saved zero-slot digital photos and videos (`[DIGITAL_JSON]`), book calendar meetups, order deliveries, pick up local bounties, and scout apartment listings.

### 5. Real-Time Clock, Circadian Schedules & Dynamic NPC Wardrobes (`KnownRoutineCard.jsx`, `KnownWardrobeCard.jsx`)
* **What it looks like**: A toggleable `12h`/`24h` world clock paired with progressive Acquaintances & Contacts cards showing discovered 5-block weekly schedules and tracked attire presets.
* **How it plays**: Persistent characters follow work shifts, rest days, hangout habits, and sleep schedules. Shops only open when assigned staff are on duty, private residences remain gated until invited, and NPCs dynamically shift outfits between *Duty, Casual, Sleepwear*, and contextual activity kits—including wearable gifts you give them.

### 6. Normalized Social Relationships, Households & Demographic Depth
* **What it looks like**: NPC cards display localized demographic pills (*Age Category, Gender, Scenario Race*), family trees, personal preferences, and relationship tiers.
* **How it plays**: Relationships evolve across platonic, rivalry, professional, and romantic tracks within normalized Household, Commitment, Relationship Graph, and Intimacy tables, unlocking milestone dialogue, household introductions, and persistent NPC gift ownership.

### 7. Entity Contracts & Eldritch Pacts (`/contracts`, `EntityContractsModal.jsx`)
* **What it looks like**: A formal covenant agreement modal displaying terms, tithes, taboos, and granted powers.
* **How it plays**: Negotiate pacts with mysterious patrons and anomalous entities. Accepting a pact grants passive combat bonuses or special traits while binding your character to behavioral taboos and penalties if violated.

### 8. Realty, Safehouse Ownership & Scenario Currencies (`/realty`, `CurrencyBadge.jsx`)
* **What it looks like**: Real estate listings and merchant interfaces tailored with scenario-native currency symbols (*Gold `G`, Crowns, Credits `₵`, Yen `¥`, Cash `$`, Eurodollars `€$`, Sovereigns `£`, Caps*).
* **How it plays**: Purchase or rent apartments, cabins, and safehouses as private bases to rest safely, store valuable gear away from pickpockets, ward against anomalies, and host private meetings.

### 9. Interactive Folklore Codex, 36 Anomalous Sites & Field Log (`EncyclopediaSubTab.jsx`)
* **What it looks like**: An in-game encyclopedia tab with Folklore, Anomalous Sites, and Field Log views tracking supernatural entities and stabilized zones.
* **How it plays**: Exploring anomalous zones lets you solve multi-step spatial puzzles, use wards and stabilization flares to survive domain hazards, seal and reclaim 36 pacifiable wild sites (`anomalous_sites/`), and study creature weaknesses for tactical combat bonuses.

### 10. World Pulse Regional Crises, Outlaw Syndicates & Custom Narrative Pacing (`/factions`, `/settings`)
* **What it looks like**: Live faction & regional crisis dashboards paired with dedicated **Narrative Pacing** (*Concise, Balanced, Novelistic*) and **Prose Style** (*Normal, Vivid, Noir, Witty, Shakespearean, Brainrot*) controls.
* **How it plays**: Compete or align with lawful agencies, ancient orders, and outlaw syndicates (*Occult Cult*, *Clandestine Syndicate*) featuring 10-wing headquarters, 5-tier promotion ladders, and archetype perks, while tailoring narration length and atmospheric voice to your preference.

---

## 🕹️ How to Play

### Character Creation & SPECIAL Stats
1. Launch character creation using `/character create` or the web character creator modal.
2. Distribute points across the 7 core **SPECIAL** attributes:
   * **Strength (STR)**: Melee damage and inventory weight limit (+3 slots per point).
   * **Perception (PER)**: Ranged accuracy, environmental awareness, examine insight detail, and spotting clues.
   * **Endurance (END)**: Maximum Health (HP), Mana (MP), and innate damage threshold.
   * **Charisma (CHA)**: Social skill checks, NPC disposition, and merchant discounts.
   * **Intelligence (INT)**: Magic strength, tactical options, and XP gain multiplier (+6% XP per point).
   * **Agility (AGI)**: Evasion, turn initiative, and stealth movement.
   * **Luck (LUK)**: Critical hit chances, finding rare loot, and avoiding hazards.
3. Start the adventure with `/adventure start` on Discord or by creating a session on the Web UI.

---

## 📂 Project Architecture

```
hikayat/
├── api/                        # FastAPI REST endpoints (adventure/, codex_phone, contracts, fonts, realty, auth)
├── bin/                        # Auxiliary network & tunnel utilities (tunnel.py)
├── cogs/                       # Discord Bot slash command cogs & interactive button views
├── custom_fonts/               # Drop-in user font files (.woff2, .woff, .ttf, .otf) served dynamically
├── data/                       # Static game catalogs (classes, scenarios, locations, folklore, storylets)
├── db/                         # Modular SQLite persistence packages (core/, social/, saves, sessions, registry.py)
├── game_engine/                # Core turn pipeline (turn/ & phase_state.py), TurnExecutionContext, reducers & quests
├── localization/               # Multi-language translation dictionaries (en, pl, ms, de, zh)
├── mechanics/                  # Domain-specific simulation modules
│   ├── combat/                 # Combat formulas, weapon/armor DT & DR, 5-mode consumables, spells & auto-loot
│   ├── narrative/              # Quest engines, dossiers, zero-turn examine snapshots, blueprints & intent parser
│   ├── pacts/                  # Entity contracts, patrons, geas rules & pact lifecycle
│   ├── social/                 # 3-stage population seeder, relationship graph, wardrobe engine & social pacing
│   ├── stealth/                # Mathematical alert state machine, noise formulas & toggle sync
│   ├── system/                 # In-game smartphone, time engine, memory compaction & input sanitizer
│   └── world/                  # 3-tier spatial graph, Dijkstra pathfinding, 36 anomalous sites, realty & world events
├── models/                     # Centralized Pydantic schemas & state models
├── releases/                   # Version changelogs & clean release archives
├── scripts/                    # Maintenance, release packaging, static bug gate & session cleanup utilities
├── services/                   # Decoupled headless services (turn/ package, TurnService, ExamineService, CrashCapture)
├── web/                        # React 18 Single-Page Application (Vite, Tailwind, ESLint 9, i18n, Motion)
│   ├── dist/                   # Compiled production frontend bundle (served by FastAPI)
│   ├── public/backgrounds/     # 12 bundled .webp scenario & menu backdrop illustrations
│   ├── eslint.config.js        # Flat ESLint configuration (React & Hooks rules)
│   └── src/                    # StoryFeed, ActionPanel, ExamineModal, WorldMapModal, 8 Phone apps, modals & themes
├── config.py                   # Central configuration, deferred secret validation & test-mode isolation
├── bot.py                      # Discord Bot entry point
├── server.py                   # FastAPI Web & WebSocket server entry point
├── requirements.txt            # Python dependencies
└── .env.example                # Environment configuration template
```

---

## 🚀 Setup & Installation

### 1. Prerequisites
* Python 3.11+
* Node.js 18+ (only needed if building the React frontend from source)
* A Discord Bot Token ([Discord Developer Portal](https://discord.com/developers/applications))
* An API key for any OpenAI-compatible LLM endpoint

### 2. Backend Setup
```bash
# Clone the repository
git clone https://github.com/Artemiusz97/hikayat.git
cd hikayat

# Create and activate Python virtual environment
python -m venv venv
source venv/bin/activate       # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your DISCORD_TOKEN, LLM_API_KEY, LLM_BASE_URL, and LLM_MODEL
```

### 3. Frontend Setup (Pre-built in `web/dist/`)
The web application is already pre-compiled into `web/dist/` and runs out-of-the-box when you launch `server.py`. If you wish to build it yourself:
```bash
cd web
npm install
npm run build
cd ..
```

### 4. Running Hikayat
* **Launch Discord Bot**:
  ```bash
  python bot.py
  # Or on Windows: run_bot.bat
  ```
* **Launch Web Server**:
  ```bash
  python server.py
  # Or on Windows: run_web.bat
  ```

---

## 📄 License & Versioning
Hikayat adheres to [Semantic Versioning (SemVer 2.0.0)](https://semver.org/spec/v2.0.0.html). For release notes and historical milestones, view [`releases/CHANGELOG.md`](releases/CHANGELOG.md).
