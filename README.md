# Hikayat (v2.1.0) — Living AI Tabletop RPG & Web Application

[![Tests](https://github.com/Artemiusz97/hikayat/actions/workflows/tests.yml/badge.svg)](https://github.com/Artemiusz97/hikayat/actions/workflows/tests.yml)
[![Version](https://img.shields.io/badge/version-2.1.0-blue.svg)](releases/CHANGELOG-v2.1.0.md)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![React 18](https://img.shields.io/badge/react-18.2-61dafb.svg)](web/)

Hikayat is a comprehensive, multi-genre LLM-driven Tabletop RPG engine powered by an intelligent dual-model architecture. It features a full-featured **Discord Bot interface** and a modern **React Web Application**, bringing living worlds, tactical party combat, persistent lore, deep social simulation, and procedural campaigns to life.

---

## 🛠️ Technical Architecture & Innovations
*(What sets Hikayat apart from traditional LLM-powered text RPGs)*

### 1. Deterministic State Separation & Anti-Hallucination Pipeline
* **True Game State vs. Hallucinated Prose**: Most LLM-based text RPGs rely on the language model to guess HP, invent inventory changes, and simulate dice rolls in prose, inevitably leading to narrative drift and broken rules.
* **Code-Driven Truth Directives**: In Hikayat, every dice check, combat damage calculation, inventory capacity check, and status effect is deterministically computed in Python first. The LLM acts purely as a narrator, bounded by immutable truth directives that prevent hallucinations.

### 2. Dual-Model Architecture & Computational Offloading
* **Decoupled Narration & Utility Work**: Separates high-latency, creative prose generation from mechanical background operations.
* **Dedicated Utility Model (`LLM_UTILITY_MODEL`)**: Offloads background calculations (quest tracking, clue merging, shop restocking, item validation) to fast, lightweight models while reserving parameter-heavy models exclusively for rich prose.

### 3. Dynamic Model Routing & Fallback Cascade
* **Automated Provider Failover**: Multi-provider resilience automatically shifts across candidate models on timeouts or rate-limits without interrupting the player's turn.
* **Context-Aware NSFW Routing**: Adult/unrated scenarios are dynamically channeled to dedicated uncensored models (`NSFW_LLM_MODEL`) with isolated fallback chains, keeping mainstream models clean.
* **Reasoning Headroom Safeguards**: Enforces strict 3,500 token output headroom margins, completely preventing the JSON truncation errors common to modern reasoning models.

### 4. Vector Memory Compaction & Context Token Budgeting
* **Semantic Vector Retrieval**: Lorebook entries, historical character encounters, and location knowledge are indexed and retrieved via semantic embeddings (`mechanics/system/memory/`).
* **Active Token Budgeting & Compaction**: Dynamically compacts older conversation turns into persistent contextual summaries, preserving long-term campaign continuity within strict token budgets.

### 5. Headless Turn Service & Omnichannel Architecture
* **Presentation-Decoupled Game Loop**: The turn engine (`services/turn_service.py`) operates as a completely headless core.
* **100% Platform Parity**: Both the Discord bot (slash commands, button decks, modal sheets) and the React Web SPA (REST endpoints, WebSockets) consume the exact same underlying service, ensuring synchronized state across platforms.

---

## 🌟 Core Gameplay Systems

### 1. Dual Platforms: Discord Bot & Modern React Web UI
* **Discord Bot**: Interactive slash commands, button menus, modals, and dynamic embed dialogues.
* **Modern React Web UI (`web/src/`)**: Single-page application featuring interactive Tactical Battle Decks, live Story Feed, in-game Smartphone modal, Party Widget, and Codex panels.
* **FastAPI Modular Backend (`api/`, `services/`)**: High-performance REST endpoints and WebSockets for multiplayer synchronization and state streaming.

### 2. Living World, Time Engine & In-Game Smartphone
* **Minute-by-Minute Time Progression**: Persistent in-game clock advancing across 8 distinct time-of-day phases (Dawn, Afternoon, Dusk, Night, etc.).
* **Rest & Fatigue Mechanics**: Dynamic "Sleep / Rest" actions in hub locations with cumulative fatigue penalties for staying awake.
* **In-Game Smartphone (`/phone`)**: Direct NPC texting, date scheduling, meetup waypoints, and cross-zone companion transit.
* **Procedural Biomes & Location Hubs**: Tiered location tree architecture with dynamic discovery, area links, and contextual merchant hubs.

### 3. Deep Social Dynamics, NPC Depth & Factions
* **Rich NPC Depth & Memory**: NPCs feature persistent backgrounds, unique mannerisms, emotional moods, evolving dispositions, and contextual memory of player history.
* **Genealogy & Canonical Families**: Preserves consistent family lineages (parents, siblings, spouses) and personal histories across encounters.
* **Unified Action Intent Engine**: Intelligently distinguishes diplomatic banter, peaceful exploration, romantic advances, gift giving, and commerce.
* **Nuanced Relationship & Intimacy Progression**: Multi-stage relationship milestones with mutual preference tracking, emotional disclosure gating, and gradual intimacy evolution across physical and emotional dimensions.
* **Living Factions System (`/factions`)**: Dynamic faction standings, territorial influence, rivalries, and faction headquarters with reputation perks.

### 4. Tactical Combat Engine & Battle Decks
* **Code-Driven Tactical Battle Decks**: 7-slot combat choices (*Attack, Defend, Magic, Item, Flee, Tactician Moves*) with active enemy target switching and success probability indicators.
* **Telegraphed Enemy Moves & Counter-Play**: Enemies telegraph incoming intents (charging, casting, defending, swarming), enabling strategic defensive guards, interruptions, and counter-attacks.
* **Companion Combat AI**: Friendly companions participate actively in battles with autonomous tactical support, vital tracking, and dedicated combat event logging.
* **Scalable Threat Hierarchy**: Dynamic encounter scaling from skirmishers to champions and multi-phase bosses with distinctive combat affixes.
* **Narrative Immersion Protocol**: Strict GM rules prevent raw HP numbers from leaking into prose, describing physical trauma and flow dynamically.

### 5. Modular Equipment & Elemental Magic Systems
* **Versatile Weapon Mechanics**: Weapons act as tactical multipliers and stat scalers, supporting diverse playstyles including dual-wielding and versatile grips.
* **Layered Equipment & Armor**: Distinct slots for civilian attire, combat armor, headwear, shields, and accessories, with balanced damage mitigation formulas.
* **Elemental Magic Taxonomy**: Dedicated magic package with elemental tags, spell taxonomy, class-specific spell kits, and dynamic MP cost scaling.
* **Procedural Consumables & Items**: Scenario-appropriate potions, consumables, and gear dynamically seeded into world containers and merchant shops.

### 6. Procedural 10-Chapter Campaign System
* **Long-Term Procedural Goals**: Story campaigns progress through 10 chapters driven by dynamically generated end goals and emergent narrative arcs.
* **Dynamic Bounty Board & Quests**: Interactive `/quest` and `/bounty` views with sub-objectives, item loot rewards, and XP bonuses.

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
│   ├── state/                  # State reducers & state machines
│   ├── turn/                   # Turn loop generation & outcome handling
│   ├── context.py              # Known-world prompt assembly & token budget
│   └── core.py                 # Narrative rules & schema constraints
├── mechanics/                  # Domain-specific gameplay subsystems
│   ├── combat/                 # 5-tier enemies, tactical decks, equipment, spells, items & tags
│   ├── narrative/              # Anti-cliche filters, paragraph quotas & style supremacy
│   ├── social/                 # 3-track intimacy, genealogy, intent classification & persona
│   ├── system/                 # Minute-by-minute time engine, in-game smartphone & memory budgeting
│   └── world/                  # Location tree, spatial waypoints, mobility & World Forge seeder
├── models/                     # Centralized Pydantic schemas & entity trackers
├── releases/                   # Version changelogs & clean release archives
├── scripts/                    # Maintenance & release packaging utilities
├── services/                   # Decoupled turn execution service
├── tests/                      # Automated unit, integration & contract test suites
├── web/                        # Unified modern React Single-Page Application
│   ├── dist/                   # Production compiled assets (pre-built, served natively by FastAPI)
│   ├── src/                    # ActionPanel, StoryFeed, PhoneModal, CodexPanel, PartyWidget
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
