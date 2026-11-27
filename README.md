# Hikayat (v3.7.0) — Living AI Tabletop RPG & Web Application

[![Version](https://img.shields.io/badge/version-3.7.0-blue.svg)](releases/CHANGELOG-v3.7.0.md)
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
* **How Hikayat works**: Every character belongs to a persistent closed-world database roster (`db/roster.py`) seeded with Stage 0 zero-LLM skeletons (~180–310 NPCs per world plus 68 special agent blueprints in `population_seeder.py` and 40 Spirit Realm slots in `folklore_villages_catalog.json`), lazily hydrated on first scene encounter (Stage 1), and automatically backfilled for active quests alongside teen/student civilian job validation (`employment_policy.py`). Before each turn, a 6-tier presence resolver (`mechanics/world/presence_resolver.py`) and stage manager (`game_engine/npcs/cast_planner.py`, `stage_manager.py`) determine physically present characters—checking party companions, scheduled commitments, quest pins, home doorbell rules, and shift schedules—so the AI only writes dialogue for people who are actually there.

### 3. Multi-Realm World Graph, Ephemeral Anomaly Rifts & Dijkstra Pathfinding (`locations/realms/`, `locations/pathfinding.py`)
* **What problem it solves**: Instead of letting the player teleport across worlds, ignore dimensional communication limits, or travel across impossible distances, multi-setting RPGs need explicit dimensional boundaries, realistic transit costs, and strict access rules.
* **How Hikayat works**: World geography is stored in SQLite across a 4-tier hierarchy (*Realm ➔ Zone ➔ Facility ➔ Room*), encompassing multi-realm settings (Fantasy *Underworld*, 9 Sci-Fi orbital/starship/planetary realms with FTL vessel jumping and multi-jump dock rollback, and Anomalous dimensions including the 8-zone *Veiled Spirit Realm*), ephemeral dynamic rifts (`data/dynamic_realm_templates.json`), realm-scoped `time_scale` & communication isolation (`check_realm_comms_available`), procedural urban profiles (`namegen.py`), and 10-wing faction headquarters. When a player travels, Dijkstra’s shortest-path algorithm calculates transit time, stamina cost, travel fares, locked door requirements, curfew checks, and same-realm fast-travel guards before moving the player.

### 4. Mathematical Alert State Machine & Live Stealth Projection (`mechanics/stealth/`)
* **What problem it solves**: Stealth in text games usually relies on the AI guessing whether a guard notices you, or fails to keep action choices synchronized with your stealth posture.
* **How Hikayat works**: Stealth uses a mathematical alert state machine per NPC (`UNAWARE`, `SUSPICIOUS`, `SEARCHING`, `DETECTED`). The engine calculates noise levels from armor weight, companion footsteps, lighting conditions, and player action loudness, projects per-user stealth states (`project_stealth_state_for_user`), and dynamically synchronizes stealth/distraction choices (`sync_stealth_choices_for_toggle`) when toggling stealth on or off.

### 5. Multi-Engine Quest Architecture, Threat Clocks & Forensic Dossiers (`game_engine/quest_agency.py`, `mechanics/narrative/dossier_compiler.py`)
* **What problem it solves**: Quests in AI games easily lose focus, forget objectives, or conclude abruptly without resolving clues or cast identities.
* **How Hikayat works**: Quests run on specialized operational engines (Investigation, Bounty, Social Infiltration, Survival) backed by 6-segment Threat Clocks, Chapter Plans, cross-realm Spirit Court commissions (`spirit_court_bounties.py`), and relational database tables (`quests`, `quest_dossiers`, `session_clues`). As players uncover evidence and interview witnesses, the system compiles structured forensic dossiers with verifiable leads, registers quest cast NPCs deterministically, and prevents premature turn-ins until stage conditions are satisfied.

### 6. Living World Autonomy & Epistemic Asymmetry Matrix (`npc_autonomy.py`, `epistemic_engine.py`, `db/epistemic.py`)
* **What problem it solves**: In most RPGs, NPCs never interact with each other off-screen, and every character magically knows secrets the moment something happens—or never hears rumors at all.
* **How Hikayat works**: Across time-block boundaries, the engine runs deterministic off-screen NPC autonomy (`mechanics/world/npc_autonomy.py`) alongside World Pulse regional & Spirit Realm events (`mechanics/world/world_events/`) and an Epistemic Asymmetry Matrix (`mechanics/social/epistemic_engine.py`, `epistemic_propagation.py`). Witnesses track what they saw, rumors decay or spread 1-hop across social ties with server-side Fog-of-War isolation, alibis are checked for lies, and players can confront, hush, bribe, or leverage secrets deterministically.

### 7. Declarative 44-Table Session Lifecycle Registry, Pooled `ReadUnitOfWork` & Hybrid Memory (`db/registry.py`, `db/core/`, `mechanics/system/memory/`)
* **What problem it solves**: Multi-table SQLite RPGs risk orphaned save-slot rows, broken turn rollbacks, redundant database round-trips, or upward architecture layer leaks as campaigns grow.
* **How Hikayat works**: All 44 session-scoped child specs are governed by a declarative lifecycle contract (`SESSION_TABLE_REGISTRY` / `SessionTableSpec` in `db/registry.py`, validated alongside 53 schema tables and 11 global tables) driving FK-safe purge ordering, tiered save/load slot ID remapping (`db/saves.py` with realm badge metadata), deterministic turn rollback (`db/sessions.py`), and ring-buffer snapshot pruning across modular `db/core/`, `db/social/`, `db/quests/`, and `db/dossiers/` packages—while enforcing strict 4-layer dependency boundaries, raw-SQL isolation, unused/shadow import detection, and package facade integrity via `scripts/static_check.py`. Thread-safe read connection pooling (`ReadUnitOfWork`), `PRAGMA user_version` fast-path checks, and batched turn preloaders keep queries fast, while FTS5 and vector memory compaction condense older turns within token budgets.

### 8. Hybrid Reasoning Streaming, Dual-Model Cascade & Split Stall Guardrails (`llm_client/`)
* **What problem it solves**: Streaming structured JSON from local or hybrid-reasoning models often stalls on long KV prefills, leaks `<think>` blocks, or wastes large-model latency on routine utility classification.
* **How Hikayat works**: Live turns stream prose in real time through the modular `llm_client/` package via `DualModeStreamingExtractor` (`@@TITLE:`, `@@OUTCOME`, `@@NEXT`, `@@CHOICES`, `@@META`) with transparent JSON fallback, split Time-To-First-Token (`LLM_TTFT_TIMEOUT`) and inter-chunk idle timers (`LLM_CHUNK_IDLE_TIMEOUT`), hybrid reasoning token ceilings (`LLM_THINKING_MAX_TOKENS`), and Chain-of-Thought suppression (`LLM_SUPPRESS_NARRATION_COT`). Meanwhile, `LLM_UTILITY_MODEL` handles fast background extraction/classification, `NSFW_LLM_*` isolates mature scenarios, and fallback cascades handle rate limits seamlessly.

### 9. 5-Language Dictionary Canonicalization, Build/Anatomy Rules & Anti-Drift Pronoun Engine (`localization/`, `game_engine/pronoun_resolver.py`)
* **What problem it solves**: Multi-language support often breaks formatting, and language models frequently mix up character pronouns or demographic traits during long scenes.
* **How Hikayat works**: Game actions, combat choices, UI labels (`1,971` web i18n keys), character build/anatomy taxonomies (`stature`, `physique`, `rear_size`, `species_surface`), and inventory metadata synchronize across English, Polish, Malay, German, and Simplified Chinese in both Python dictionaries and React i18n JSON bundles. An automated pronoun resolver checks entity genders against database IDs to prevent models from drifting mid-scene.

### 10. Headless Omnichannel Game Loop, Zero-Turn Inspection & Remote Access Security (`services/turn/`, `services/examine_service.py`, `api/security.py`)
* **What problem it solves**: Supporting both a Discord bot and a web application across local, tunneled, or private remote networks usually leads to duplicated game logic or inconsistent auth gates.
* **How Hikayat works**: Both `TurnService` (`services/turn/` behind `services/turn_service.py` for turns Phases 1–5) and `get_examine_payload` (`services/examine_service.py` for zero-turn scene and tactical inspection with LRU/TTL prose caching and strict stat/secret scrubbing) run headlessly in Python services, driving Discord slash commands/buttons (`cogs/adventure/embeds/`, `cogs/character.py`) and the modular FastAPI `api/adventure/` & `api/codex_phone/` REST/WebSocket routes from a single source of truth—backed by optional Cloudflare Tunnel sharing and verified Tailscale remote-play headers (`bin/tunnel.py`, `launchers/`).

---

## 🎮 10 Unique Gameplay Features
*(What you actually experience as a player)*

### 1. Acrylic Glassmorphism Web UI, 12 Scenario Backdrops, Phone Wallpapers & Discord Parity
* **What it looks like**: Play on Discord using slash commands and interactive decks, or launch the React 18 Web SPA featuring frosted Acrylic panels (`Full`, `Focused`, and `Solid` modes with 5%–95% opacity), drop-in custom fonts (`custom_fonts/`) or curated Google Font presets, adjustable text scaling (`70%–130%`), 12 illustrated `.webp` scenario backdrops, and 11 bundled `.webp` smartphone wallpapers.
* **How it plays**: Backdrops smoothly crossfade per campaign with OKLCH time-of-day atmospheric color grading (*Dawn, Day, Dusk, Night*) and an optional blurred ambient scene-artwork mode. Explore your chronicle through the searchable **Turn History Modal**, spot dimensional context via **Save-Slot Realm Badges**, and navigate multi-realm gateways & active quest tabs in a native `<dialog>` **World Map Modal**.

### 2. Zero-Turn Scene Examine, Tactical Action Dock & 5-Mode Quick Belt (`ExamineModal.jsx`, `TacticalActionDock.jsx`, `QuickBeltPopover.jsx`)
* **What it looks like**: A persistent sidebar action dock, quick-use consumable belt, and a dedicated **Examine** button (`0 Turns`) on both Web and Discord.
* **How it plays**: Inspecting a scene costs zero turns and presents live structured snapshots—present NPCs (with posture, visible attire, `PER`-tier mood tells, and instant *Use Item* / *Gift* buttons), dropped items ready for one-click pickup, active leads, stealth/privacy/witness awareness, and enemy combat weaknesses/intents. Out of combat, the 5-mode consumable classifier automatically separates instant **Quick Use** healing/buffs from turn-consuming food, drinks, gifts, and covert items.

### 3. Turn-Based Tactical Combat with Telegraphed Moves, Armor DT/DR, Summons & Auto-Loot
* **What it looks like**: A structured 7-slot combat menu (*Attack, Defend, Magic, Item, Flee, Tactician, Switch Target*) with toggleable enemy HP bars and intent readouts.
* **How it plays**: Enemies telegraph upcoming actions so you can time blocks, dodges, counters, or interrupts against Fallout-style flat Damage Threshold (DT) and percentage Damage Resistance (DR), invoke 3-turn **Sworn Ally Spirit Court Summons** (*Myōbu Fox-Spirit, Kayangan Mist-Guardian, Mirage Pack Canid*) once court standing hits `90+`, and receive deterministic post-combat auto-loot into your inventory without losing drops to narration gaps.

### 4. Modular 8-App In-Game Smartphone, Categorized Online Store & SchoolMart (`PhoneModal.jsx`, `online_store.py`)
* **What it looks like**: A sleek in-game smartphone modal organized into 8 purpose-built apps (*Home, DMs, Feed, Photos, Planner, Shop, Bounties, Realty*) plus **Phone Settings** (`PhoneSettingsApp.jsx`) and an interactive **Photo Lightbox**.
* **How it plays**: Text NPCs (bridged across dimensions via *Spirit Relay* or *Ossuary Bone-Relay* when signal permits), scroll local gossip feeds, customize glass UI & phone wallpapers, schedule calendar meetups, scout realty, and shop a daily-rotating **Categorized Online Store** or 20% discounted student **SchoolMart** storefront (locked safely during combat or realm blackout zones).

### 5. Interactive 24h Analog Clock Dial, Circadian Schedules & Dynamic NPC Wardrobes (`AnalogClockDial.jsx`, `KnownRoutineCard.jsx`, `KnownWardrobeCard.jsx`)
* **What it looks like**: An interactive radial **24-Hour Analog Clock Dial** (`AnalogClockDial.jsx` or horizontal slider toggle) paired with `12h`/`24h` world clock formats, temporal stasis (`0x`) indicators, and progressive Contacts & Acquaintances cards showing 5-block weekly routines and tracked outfits.
* **How it plays**: Persistent characters follow work shifts, rest days, hangout habits, and sleep schedules. Shops only open when assigned staff are on duty, private residences remain gated until invited, and NPCs dynamically shift outfits between *Duty, Casual, Sleepwear*, and contextual activity kits—including wearable gifts you give them.

### 6. Build/Anatomy Customization, Reaction Engine, Normalized Social Graph & Dossier Cards (`anatomyOptions.js`, `IntimateDossierPanel.jsx`, `OperativeCombatDossierCard.jsx`)
* **What it looks like**: Hero and NPC dossiers display localized demographic pills (*Age Category, Gender, Scenario Race, Stature, Physique*), family trees, personal body preferences, relationship tiers, and unified **Operative Combat Dossiers** or **Civilian Classifications**—editable on both Web (`CharacterCreatorModal.jsx`, `CharacterSheet.jsx`) and Discord (`/character appearance`).
* **How it plays**: Relationships evolve across platonic, rivalry, professional, and romantic tracks within normalized Household, Commitment, Relationship Graph, and Intimacy tables, while anatomy proportions and partner preferences scale excitement multipliers with zero-number narrative cues (`intimate_excitement.py`) and unlock persistent NPC gift ownership and Guest-Cottage hospitality.

### 7. Entity Contracts & Eldritch Pacts (`/contracts`, `EntityContractsModal.jsx`)
* **What it looks like**: A formal covenant agreement modal displaying terms, tithes, taboos, and granted powers.
* **How it plays**: Negotiate pacts with mysterious patrons and anomalous entities. Accepting a pact grants passive combat bonuses or special traits while binding your character to behavioral taboos and penalties if violated.

### 8. Realty, Safehouse Ownership & Scenario Currencies (`/realty`, `CurrencyBadge.jsx`)
* **What it looks like**: Real estate listings and merchant interfaces tailored with scenario-native currency symbols (*Gold `G`, Crowns, Credits `₵`, Yen `¥`, Cash `$`, Eurodollars `€$`, Sovereigns `£`, Caps*).
* **How it plays**: Purchase or rent apartments, cabins, safehouses, or Spirit Court Guest-Cottages as private bases to rest safely, store valuable gear away from pickpockets, ward against anomalies, and host private meetings.

### 9. Hidden Veiled Spirit Realm, 3 Spirit Courts, Folklore Codex & 39 Anomalous Sites (`folklore_spirit_realm.py`, `folklore_ghoul.py`, `EncyclopediaSubTab.jsx`)
* **What it looks like**: A navigable multi-zone **Veiled Spirit Realm** alongside an in-game encyclopedia tab with Folklore, Anomalous Sites, and Field Log views tracking supernatural entities and stabilized zones.
* **How it plays**: Cross thresholds from *Chinatown, Mount Ryujin, Woods Reserve*, or *Undercity Catacombs* into *Dusk Confluence Bazaar* and its 4-wing Night Market; explore 4 dangerous frontier biomes; gain standing through friendly sparring drills and cross-realm commissions across the **Kitsune Shrine Court**, **Royal Bunian Court**, and **Dual-Form Al-Ghul Ossuary Court** (`ghoul:humanoid` / `ghoul:canid`); or seal **39 pacifiable Anomalous Sites** (`anomalous_sites/`) by solving spatial puzzles and surviving domain hazards.

### 10. World Pulse Regional & Spirit Crises, Outlaw Syndicates & Custom Narrative Pacing (`/factions`, `/settings`)
* **What it looks like**: Live faction & regional crisis dashboards paired with dedicated **Narrative Pacing** (*Concise, Balanced, Novelistic*) and **Prose Style** (*Normal, Vivid, Noir, Witty, Shakespearean, Brainrot*) controls.
* **How it plays**: Compete or align with lawful agencies, monastic orders, outlaw syndicates (*Occult Cult*, *Clandestine Syndicate*) featuring 10-wing headquarters and 5-tier promotion ladders, and 3 autonomous Spirit Courts while witnessing dynamic festivals and crises across both human districts and the Veiled Spirit Realm.

---

## 🕹️ How to Play

### Character Creation & SPECIAL Stats
1. Launch character creation using `/character create` or the web character creator modal (customizing demographics, stature, physique, and starting appearance).
2. Distribute points across the 7 core **SPECIAL** attributes:
   * **Strength (STR)**: Melee damage and inventory weight limit (+3 slots per point).
   * **Perception (PER)**: Ranged accuracy, environmental awareness, examine insight detail, and spotting clues.
   * **Endurance (END)**: Maximum Health (HP), Mana (MP), and innate damage threshold.
   * **Charisma (CHA)**: Social skill checks, NPC disposition, and merchant/SchoolMart discounts.
   * **Intelligence (INT)**: Magic strength, tactical options, and XP gain multiplier (+6% XP per point).
   * **Agility (AGI)**: Evasion, turn initiative, and stealth movement.
   * **Luck (LUK)**: Critical hit chances, finding rare loot, and avoiding hazards.
3. Start the adventure with `/adventure start` on Discord or by creating a session on the Web UI across **21 scenario presets** (*Fantasy, Dark Fantasy, Isekai, Sci-Fi, Cyberpunk, Steampunk, High School Drama, Slice of Life, Nuclear Post-Apocalypse, Anomalous Incursions*, and *Anomalous High School* variants).

---

## 📂 Project Architecture

```
hikayat/
├── api/                        # Modular FastAPI routers (adventure/, codex_phone/, contracts, fonts, inventory_merchant, realty, auth_characters, security, settings_ws)
├── bin/                        # Auxiliary network & tunnel utilities (tunnel.py for Cloudflare & Tailscale)
├── cogs/                       # Discord Bot slash command cogs & interactive views (adventure/embeds/, adventure/views/, character, contacts, factions)
├── custom_fonts/               # Drop-in user font files (.woff2, .woff, .ttf, .otf) served dynamically
├── data/                       # Static JSON catalogs (scenarios, locations_seed, dynamic_realm_templates, folklore_villages, 39 anomalous sites) + runtime SQLite DB (data/hikayat.db) & backups (data/backups/)
├── db/                         # Modular SQLite persistence packages (core/, social/, quests/, dossiers/, saves, sessions, registry.py)
├── game_engine/                # Core turn pipeline (turn/ & phase_state.py), choices_cleaner/, TurnExecutionContext, reducers & quests
├── launchers/                  # Secondary Windows launchers (run_web_share.bat, run_web_tailscale.bat)
├── llm_client/                 # Modular LLM streaming/batch transport, capability detection, response parsing & cascade state
├── localization/               # 5-language Python localization dictionaries (en, pl, ms, de, zh)
├── mechanics/                  # Domain-specific simulation modules
│   ├── combat/                 # Combat formulas, weapon/armor DT & DR, 5-mode consumables, Online Store/SchoolMart, Spirit Court perks & spells
│   ├── narrative/              # Quest engines, dossiers, Spirit Court commissions, zero-turn examine snapshots & intent parser
│   ├── pacts/                  # Entity contracts, patrons, geas rules & pact lifecycle
│   ├── social/                 # 3-stage population seeder, Dual-Form Al-Ghul, employment policy, wardrobe & anatomy/excitement engine
│   ├── stealth/                # Mathematical alert state machine, noise formulas & toggle sync
│   ├── system/                 # In-game smartphone, time engine, memory compaction & input sanitizer
│   └── world/                  # Multi-realm graph (realms/), Veiled Spirit Realm, Dijkstra pathfinding, 39 anomalous sites, realty & world events
├── models/                     # Centralized Pydantic schemas & state models
├── releases/                   # Version changelogs & clean release archives
├── scripts/                    # Maintenance, release packaging & session cleanup utilities
├── services/                   # Decoupled headless services (turn/ package, TurnService, ExamineService, anomalous_containment_service, CrashCapture)
├── web/                        # React 18 Single-Page Application (Vite, Tailwind, ESLint 9, i18n, Motion)
│   ├── dist/                   # Compiled production frontend bundle (served by FastAPI)
│   ├── public/                 # 12 bundled .webp scenario backdrops + 11 .webp phone wallpapers
│   ├── eslint.config.js        # Flat ESLint 9 configuration (React & Hooks rules)
│   └── src/                    # Modular views, session/ hooks, AnalogClockDial, PhoneModal (8 apps + PhoneSettings), Dossier & Codex tabs
├── config.py                   # Central configuration, deferred secret validation & test-mode isolation
├── bot.py                      # Discord Bot entry point
├── server.py                   # FastAPI Web & WebSocket server entry point
├── requirements.txt            # Python dependencies
└── .env.example                # Environment configuration template (DB_PATH=data/hikayat.db)
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
  # Or on Windows: run_web.bat (see launchers/ for public share or private Tailscale modes)
  ```

---

## 📄 License & Versioning
Hikayat adheres to [Semantic Versioning (SemVer 2.0.0)](https://semver.org/spec/v2.0.0.html). For release notes and historical milestones, view [`releases/CHANGELOG.md`](releases/CHANGELOG.md).
