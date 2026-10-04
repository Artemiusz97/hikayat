# Hikayat (v2.1.0) — Living AI Tabletop RPG & Web Application

[![Tests](https://github.com/Artemiusz97/hikayat/actions/workflows/tests.yml/badge.svg)](https://github.com/Artemiusz97/hikayat/actions/workflows/tests.yml)
[![Version](https://img.shields.io/badge/version-2.1.0-blue.svg)](releases/CHANGELOG-v2.1.0.md)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![React 18](https://img.shields.io/badge/react-18.2-61dafb.svg)](web/)

Hikayat is a comprehensive, multi-genre LLM-driven Tabletop RPG engine powered by an intelligent dual-model architecture. It features a full-featured **Discord Bot interface** and a modern **React Web Application**, bringing living worlds, tactical party combat, persistent lore, deep social simulation, and procedural campaigns to life.

---

## 🌟 Key Features

### 1. Dual-Model LLM Architecture & Fallback Cascade
* **Primary Narration Engine**: Connects to any OpenAI-compatible API endpoint (OpenAI, OpenRouter, Google Gemini, local vLLM/Ollama).
* **Dedicated Utility Model (`LLM_UTILITY_MODEL`)**: Offloads background computational tasks (quest tracking, item generation, clue merging, shop restocking) to fast models while reserving high-parameter models for rich prose.
* **Dynamic NSFW Model Routing**: Automatically routes adult/unrated scenarios to dedicated uncensored models with isolated fallback chains.
* **Fallback Cascade & Headroom Safeguards**: Automatic failover across candidate models on timeout or rate-limits, with minimum 3,500 token headroom enforcement to prevent reasoning model JSON truncation.

### 2. Tactical Combat Engine & 5-Tier Enemy Hierarchy
* **5-Tier Enemy Ladder**: Minions, Standard, Elite, Champions, and Multi-Phase Bosses with dynamic affixes (*Volatile, Phasing, Ethereal, Incorporeal*).
* **Telegraphed Enemy Moves & Intents**: Enemies telegraph intents (charging, casting, defending, swarming), enabling tactical counter-play.
* **Tactical Battle Decks**: 7-slot code-driven combat choices (*Attack, Defend, Magic, Item, Flee, Tactician Moves*) with active enemy target switching.
* **Companion Combat AI**: Friendly companions participate actively in battles, complete with vitals tracking and dedicated combat logs.
* **Narrative Immersion Protocol**: Strict GM rules prevent raw HP numbers from leaking into prose, describing physical trauma dynamically.

### 3. Modular Equipment, FNV Armor DT & Magic Taxonomy
* **Fallout: New Vegas Style Armor**: Armors and shields feature **Damage Threshold (DT)** and percentage **Damage Resistance (DR)** formulas.
* **Weapons as Damage Multipliers**: Weapons function as tactical multipliers and stat scalers with dual-wielding and versatile grip support.
* **Dedicated Clothing Slot & Armor Lockout**: Separates civilian clothing ("Top") from combat armor and headwear/accessories.
* **Modular Items & Spells**: Dedicated packages (`mechanics/items/`, `mechanics/spells/`) with elemental taxonomy and procedural consumable generation.

### 4. Living World, Time Engine & In-Game Smartphone
* **Minute-by-Minute Time Progression**: Persistent in-game clock advancing across 8 distinct time-of-day phases (Dawn, Afternoon, Dusk, Night, etc.).
* **Rest & Fatigue Mechanics**: Dynamic "Sleep / Rest" actions in hub locations with cumulative fatigue penalties for staying awake.
* **In-Game Smartphone (`/phone`)**: Direct NPC texting, date scheduling, meetup waypoints, and cross-zone companion transit.
* **Procedural Biomes & Location Hubs**: Tiered location tree architecture with dynamic discovery, area links, and contextual merchant hubs.

### 5. Social Dynamics, Factions & 3-Track Intimacy
* **Unified Action Intent Engine**: Deterministic classification distinguishing combat, peaceful exploration, romance, gifts, and trade.
* **3-Track Intimate Experience**: Separate progression tracks for Vaginal, Oral, and Manual intimacy with symmetrical act preferences and Disclosure Level 3 gating.
* **Genealogy & Canonical Families**: Preserves consistent family lineages (parents, siblings, spouses) across encounters.
* **Factions System (`/factions`)**: Dynamic faction standings, perks, rivalries, and faction headquarters.

### 6. Procedural 10-Chapter Campaign System
* **Long-Term Procedural Goals**: Story campaigns progress through 10 chapters driven by dynamically generated end goals.
* **Dynamic Bounty Board & Quests**: Interactive `/quest` and `/bounty` views with sub-objectives, item loot rewards, and XP bonuses.

### 7. Dual Platforms: Discord Bot & Modern React Web UI
* **Discord Bot**: Interactive slash commands, button menus, modals, and embeds.
* **React Web Frontend (`frontend/src/`)**: Single-page application featuring Tactical Battle Decks, live Story Feed, in-game Smartphone modal, Party Widget, and Codex panels.
* **FastAPI Modular Backend (`api/`, `services/`)**: REST endpoints and WebSockets for multiplayer synchronization and state streaming.

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
