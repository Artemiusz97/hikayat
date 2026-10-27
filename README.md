# Hikayat (v2.6.0) — Living AI Tabletop RPG & Web Application

[![Tests](https://github.com/Artemiusz97/hikayat/actions/workflows/tests.yml/badge.svg)](https://github.com/Artemiusz97/hikayat/actions/workflows/tests.yml)
[![Version](https://img.shields.io/badge/version-2.6.0-blue.svg)](releases/CHANGELOG-v2.6.0.md)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![React 18](https://img.shields.io/badge/react-18.2-61dafb.svg)](web/)

Hikayat is a comprehensive, multi-genre LLM-driven Tabletop RPG engine powered by an intelligent dual-model architecture. It features a full-featured **Discord Bot interface** and a modern **React Web Application**, bringing living worlds, tactical party combat, persistent lore, deep social simulation, and procedural campaigns to life.

---

## 🛠️ 10 Unique Technical Implementations
*(What sets Hikayat apart from traditional LLM-powered text RPGs)*

### 1. Deterministic State Separation & Anti-Hallucination Pipeline (Phase 1–5 Directives)
* **True Game State vs. Hallucinated Prose**: Traditional LLM-based text RPGs rely on the language model to guess HP, invent unearned inventory items, and simulate dice rolls in prose, inevitably leading to narrative drift and rule violations.
* **Code-Driven Truth Directives**: In Hikayat, every dice check, combat damage calculation, inventory capacity check, status effect, and quest milestone is deterministically resolved in Python before generation. The LLM acts purely as a narrator bounded by immutable truth directives that prevent hallucinations.

### 2. Deterministic Cast & Dialogue Authority (`CastPlanner`)
* **Phantom Character Elimination**: Scene attendance, active dialogue partners, bystanders, and departures are deterministically tracked in Python (`game_engine/npcs/cast_planner.py`).
* **Quotation Scrape Immunity**: Conversation state is never polluted or resurrected by LLM quotation scraping. Narrator cast suggestions (arrive, depart, engage) are strictly validated against spatial contracts, and dialogue exits immediately close conversational loops across all present NPCs.

### 3. Multi-Edge Graph Pathfinding & 3-Tier Spatial Topology (`mechanics/world/locations/pathfinding.py`)
* **Dijkstra Shortest-Path Traversal**: Models world geography via an SQLite graph of nodes and bidirectional edges with Dijkstra and BFS shortest-path routing.
* **3-Tier Hierarchy & Access Gating**: Enforces granular micro-spatial positioning (*Zone ➔ Facility ➔ Room*) alongside access key/lockpicking gates, curfew stealth verifications, fog-of-war hidden node exclusion, combat flee displacement, and transit fare gating.

### 4. Autonomous Stealth & Infiltration Simulation Engine (`mechanics/stealth/`)
* **Mathematical Infiltration Dynamics**: Replaces hand-wavy narrative sneaking with a 4-stage alert state machine (`UNAWARE`, `SUSPICIOUS`, `SEARCHING`, `DETECTED`) and dynamic detection accumulation with natural decay over unobserved turns.
* **Acoustic & Environmental Modeling**: Calculates armor acoustic noise penalties, companion noise drag, action noise, and ambient lighting modifiers to resolve opposed perception checks deterministically.

### 5. Dual-Model Architecture & Computational Offloading
* **Decoupled Narration & Utility Work**: Separates high-latency, creative prose generation from mechanical background operations.
* **Dedicated Utility Model (`LLM_UTILITY_MODEL`)**: Offloads background calculations (quest tracking, clue merging, shop restocking, item validation) to fast, lightweight models while reserving parameter-heavy models exclusively for rich prose.

### 6. Dynamic Provider Routing, Fallback Cascade & Headroom Margins
* **Automated Multi-Provider Failover**: High-availability resilience automatically shifts across candidate models on timeouts or rate-limits without interrupting the player's turn.
* **Context-Aware NSFW Routing**: Mature scenarios are dynamically channeled to dedicated uncensored models (`NSFW_LLM_MODEL`) with isolated fallback chains.
* **Reasoning Headroom Safeguards**: Enforces strict 3,500 token output headroom margins, completely preventing the JSON truncation errors common to modern reasoning models.

### 7. Semantic Vector Memory Compaction & Context Token Budgeting
* **Semantic Vector Retrieval**: Lorebook entries, historical character encounters, and location knowledge are indexed and retrieved via semantic embeddings (`mechanics/system/memory/`).
* **Active Token Budgeting & Compaction**: Dynamically compacts older conversation turns into persistent contextual summaries, preserving long-term campaign continuity within strict token budgets.

### 8. Headless Omnichannel Turn Engine (`services/turn_service.py`)
* **Presentation-Decoupled Game Loop**: The turn engine operates as a completely headless core.
* **100% Platform Parity**: Both the Discord bot (slash commands, button decks, modal sheets) and the React Web SPA (REST endpoints, WebSockets) consume the exact same underlying service, ensuring synchronized state across platforms.

### 9. 5-Language Internationalization & Anti-Drift Pronoun Engine
* **5-Language Localization Engine (`localization/`, `web/src/locales/`)**: Real-time translation and canonicalization of item affixes, inventory lemmas, movement prefixes, combat choices, and dialogue intents across English (`en`), Polish (`pl`), Malay (`ms`), German (`de`), and Simplified Chinese (`zh`).
* **Multi-Tier Pronoun Resolver**: Post-generation pronoun sanitizers and immutable gender directives ensure zero pronoun drift during long multi-party scenes.

### 10. SDXL Scene Rendering & Automated Visual Grounding (`services/image_service.py`)
* **Prose-to-Art Pipeline**: Dynamically synthesizes environment, lighting, framing, and atmosphere tokens directly from narrative prose to generate high-fidelity SDXL scene artwork.
* **Local Persistence & In-Game Sync**: Persists generated images to local storage with content-hash deduplication, negative prompt aesthetic conditioning, and automatic synchronization with the in-game Smartphone photo vault.

---

## 🌟 10 Core Gameplay Features

### 1. Dual Platforms: Discord Bot & Modern React Web SPA
* **Discord Bot**: Interactive slash commands, button decks, modal sheets, and dynamic embed dialogues.
* **Modern React Web UI (`web/src/`)**: Single-page application featuring interactive Tactical Battle Decks, live Story Feed, in-game Smartphone modal, Turn Outcome panel (`TurnOutcomePanel.jsx`), Party Widget, and redesigned Codex panels.
* **FastAPI Modular Backend (`api/`, `services/`)**: High-performance REST endpoints and WebSockets for multiplayer synchronization and state streaming.

### 2. Tactical Action Dock & Quick Belt Hotbar (`web/src/components/`)
* **Persistent Command Dock (`TacticalActionDock.jsx`)**: Sidebar command deck providing instant one-click access to stealth stances, combat targeting, quick-use consumables, smartphone apps, gifting, and time advancement.
* **Quick Belt Popover (`QuickBeltPopover.jsx`)**: Instant-access popover displaying belt potions, remedies, snacks, and consumables for immediate one-click usage without opening full inventory screens.

### 3. Living World, Time Engine & Circadian Routine Schedules
* **Minute-by-Minute Time Progression**: Persistent in-game clock advancing across 8 distinct time-of-day phases (Dawn, Morning, Afternoon, Dusk, Night, Late Night, etc.).
* **Circadian NPC Schedules**: NPCs follow dynamic schedules across schools and facilities based on grade, club, and role.
* **Rest & Time Manipulation**: Sleep mechanics, fatigue penalties, and deliberate time skipping via the interactive Time Skip modal (`TimeSkipModal.jsx`).

### 4. Tactical Turn-Based Combat Decks & Counter-Play
* **Code-Driven Tactical Battle Decks**: 7-slot combat choices (*Attack, Defend, Magic, Item, Flee, Tactician Moves*) with active enemy target switching and success probability indicators.
* **Telegraphed Enemy Moves & Counter-Play**: Enemies telegraph incoming intents (charging, casting, defending, swarming), enabling strategic defensive guards, interruptions, and counter-attacks.
* **Companion Combat AI**: Friendly companions participate actively in battles with autonomous tactical support, vital tracking, and dedicated combat event logging.
* **Narrative Immersion Protocol**: Strict GM rules prevent raw HP numbers from leaking into prose, describing physical trauma and combat flow dynamically.

### 5. In-Game Smartphone Ecosystem (`/phone`)
* **Contextually Grounded Messaging**: In-universe digital hub featuring direct messaging with NPCs (`dm_grounding.py`), player-initiated texting (`player_dm.py`), date scheduling, and contacts directory.
* **Media Vault & Apps**: Digital codex apps, camera captures, and media photo vault with persistent narrative captions.

### 6. Deep Social Dynamics, Persona & Nuanced Relationships
* **Rich NPC Depth & Memory**: NPCs feature persistent backgrounds, unique mannerisms, emotional moods, evolving dispositions, and contextual memory of player history.
* **Genealogy & Canonical Families**: Preserves consistent family lineages (parents, siblings, spouses) and personal histories across encounters.
* **Contextual Gifting & Milestones**: Gift giving with immediate affinity evaluation (`GiveGiftModal.jsx`), multi-track relationship progression (platonic, romantic, rivalry), and emotional disclosure gating.

### 7. Tactical Infiltration & Opposed Stealth Gameplay
* **Dynamic Covert Operations**: Sneak through restricted facilities, pick locks, bypass curfew patrols, and exploit shadows and silence penalties.
* **Distractions & Evasion**: Create deliberate noise distractions to redirect guards, drop detection meters, or escape search perimeters.

### 8. Modular Equipment & Elemental Magic Systems
* **Expansive Weapon Arsenal**: Over 2,000 lines of specialized weaponry across historical, fantasy, sci-fi, and modern archetypes, acting as tactical damage multipliers with dual-wielding support.
* **Layered Equipment & Armor**: Distinct slots for civilian attire, combat armor, headwear, shields, and accessories, with Fallout: New Vegas-style Damage Threshold (DT) mitigation.
* **Elemental Magic Taxonomy**: Dedicated magic package with elemental tags, spell taxonomy, class-specific spell kits, and dynamic MP cost scaling.

### 9. Living Factions System & Territorial Standings (`/factions`)
* **Dynamic World Influence**: Living faction headquarters, rank progression, territorial control, and faction rivalries.
* **Faction Contract Boards**: Procedural faction bounty boards with exclusive reputation perks, rank advancement, and faction-specific lore.

### 10. Procedural 10-Chapter Campaign System
* **Long-Term Procedural Goals**: Story campaigns progress through 10 progressive chapters driven by dynamically generated end goals and emergent narrative arcs.
* **Dynamic Bounty Board & Quests**: Interactive `/quest` and `/bounty` views with sub-objectives, clue investigations, suspect evidence extraction, item loot rewards, and emergent climax waypoints.

---

## 🎮 How to Play

### Character Creation & Loadouts
1. Use `/character create` to select your name, gender, race, backstory, and allocate your **SPECIAL stats** (Strength, Perception, Endurance, Charisma, Intelligence, Agility, Luck) via an interactive point-buy menu.
2. Launch your adventure with `/adventure start` (Solo, Turn-Based Multiplayer, or Synchronized Co-Op).
3. Select your scenario-specific starting class and weapon loadout interactively at the start of your journey.

### SPECIAL Stat System
| Stat | Core Gameplay Effect |
| :--- | :--- |
| **Strength (STR)** | Melee damage multiplier, physical prowess, inventory capacity (+3 slots per point, baseline 30). |
| **Perception (PER)** | Ranged accuracy, environmental awareness, finding hidden clues. |
| **Endurance (END)** | Max HP, Max MP, innate Damage Threshold, fatigue resilience. |
| **Charisma (CHA)** | Social checks, NPC disposition, merchant haggling discounts, romantic appeal. |
| **Intelligence (INT)** | Magic power, XP gain multiplier (+6% XP per point), tactical insight. |
| **Agility (AGI)** | Evasion, attack speed, stealth covert actions, turn initiative. |
| **Luck (LUK)** | Critical success and mishap odds, high-tier loot drops. |

---

## 📂 Project Architecture

```
hikayat/
├── api/                        # FastAPI modular REST controllers
│   ├── adventure.py            # Session management, turn resolution & save states
│   ├── auth_characters.py      # Authentication & character roster management
│   ├── codex_phone.py          # Lorebook, factions, contacts & smartphone API
│   ├── inventory_merchant.py   # Inventory management & vendor trading
│   └── settings_ws.py          # Real-time WebSocket streaming & user settings
├── bin/                        # Auxiliary binaries and tunnel utilities
│   └── tunnel.py               # Cloudflare tunnel orchestration
├── cogs/                       # Discord Bot slash command cogs
│   ├── adventure/              # /adventure game loop, views & battle decks
│   ├── character.py            # /character creation, sheet & level up
│   ├── contacts.py             # /contacts paginated profile viewer
│   ├── debug.py                # /debug developer testing tools
│   ├── factions.py             # /factions list & faction detail views
│   ├── inventory.py            # /inventory equip & inspection
│   └── settings.py             # /settings & /model status probe
├── db/                         # Modular SQLite database access layer
│   ├── characters.py           # Character persistence & stats
│   ├── core.py                 # Schema initialization, WAL mode & pragmas
│   ├── inventory.py            # Items, equipment slots & DT/DR queries
│   ├── social.py               # Relationships, intimacy & phone messages
│   └── world.py                # Locations, lorebook & factions
├── game_engine/                # Core simulation & LLM orchestration
│   ├── auditor.py              # Runtime state consistency & choice auditor
│   ├── matching.py             # Fuzzy entity matching & collective crowd guard
│   ├── state/                  # State reducers & state machines
│   ├── turn/                   # Turn loop generation & outcome handling
│   ├── context.py              # Known-world prompt assembly & token budget
│   └── core.py                 # Narrative rules & schema constraints
├── localization/               # Multi-language i18n subsystem (en, ms, pl)
├── mechanics/                  # Domain-specific gameplay subsystems
│   ├── combat/                 # Tactical decks, 2000+ line weapons arsenal, armor & spells
│   ├── narrative/              # Anti-cliche filters, paragraph quotas & style supremacy
│   ├── social/                 # Deterministic affinity engine, intimacy excitement & genealogy
│   ├── system/                 # Time engine, grounded smartphone messaging & memory compaction
│   └── world/                  # Location tree, spatial waypoints, mobility & World Forge seeder
├── models/                     # Centralized Pydantic schemas & entity trackers
├── releases/                   # Version changelogs & clean release archives
├── scripts/                    # Maintenance, release packaging & gameplay simulation harnesses
├── services/                   # Decoupled turn execution service
├── tests/                      # Automated unit, integration, simulator & contract test suites
├── web/                        # Unified modern React Single-Page Application
│   ├── dist/                   # Production compiled assets (pre-built, served natively by FastAPI)
│   ├── src/                    # ActionPanel, TurnOutcomePanel, StoryFeed, PhoneModal, CodexPanel, locales & i18n
│   ├── package.json
│   └── vite.config.js
├── config.py                   # Environment configuration loader
├── bot.py                      # Discord Bot entry point
├── server.py                   # FastAPI Web & WebSocket server entry point
├── requirements.txt            # Python dependencies
└── .env.example                # Environment configuration template
```

---

## 🚀 Setup & Installation

### 1. Prerequisites
* Python 3.11+
* Node.js 18+ (only needed if building/modifying the React frontend from source)
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

### 3. Frontend Setup (Optional - Pre-built in `web/dist/`)
The web application is already pre-compiled into `web/dist/` and runs out-of-the-box when you launch the server. If you wish to customize the frontend:
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
* **Launch Web Server & API**:
  ```bash
  python server.py
  # Or on Windows: run_web.bat
  ```

---

## 🧪 Testing

Hikayat features a comprehensive automated test suite enforcing codebase contracts, DT/DR formulas, state reducers, and combat balance:

```bash
# Run the complete test suite
pytest

# Run architectural contract and invariant tests only
pytest tests/test_codebase_contracts.py tests/test_mathematical_invariants.py
```

---

## 📄 License & Versioning
Hikayat adheres to [Semantic Versioning (SemVer 2.0.0)](https://semver.org/spec/v2.0.0.html). For release notes and historical milestones, view [`releases/CHANGELOG.md`](releases/CHANGELOG.md).
