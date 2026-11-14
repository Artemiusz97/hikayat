# Hikayat (v2.12.0) — Living AI Tabletop RPG & Web Application

[![Version](https://img.shields.io/badge/version-2.12.0-blue.svg)](releases/CHANGELOG-v2.12.0.md)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![React 18](https://img.shields.io/badge/react-18.2-61dafb.svg)](web/)

Hikayat is a text-based role-playing game (RPG) where an AI language model generates the story and dialogue, while a deterministic Python game engine calculates the actual rules, rolls, and state changes. It can be played either as a Discord bot or as a web application in your browser.

---

## 🛠️ 10 Technical Innovations
*(How the engine actually works under the hood)*

### 1. Deterministic Rule Engine vs. AI Narration (Phases 1–5 Pipeline)
* **What problem it solves**: In typical AI dungeon masters, the language model invents dice rolls, changes character health arbitrarily, and forgets inventory constraints, leading to hallucinations and broken rules.
* **How Hikayat works**: The game separates logic from storytelling. Every player action is first processed by Python code in `TurnService`: the engine calculates dice rolls, applies Fallout-style damage reduction, deducts item charges, and checks quest status. Only after the numbers are locked does the AI receive a prompt instructing it to describe what just happened without altering the math.

### 2. Deterministic Stage Manager & Cast Tracking (`CastPlanner`)
* **What problem it solves**: AI story games often suffer from "phantom NPCs"—characters who speak when they are not in the room, or disappear mid-conversation.
* **How Hikayat works**: The engine maintains a stage state machine (`game_engine/npcs/cast_planner.py` and `presence.py`) that tracks who is physically present in the scene, who is speaking, and who is an onlooker. When a character leaves the area, their conversation thread is closed by code, preventing the AI from continuing to generate dialogue for absent characters.

### 3. Graph-Based World Map & Dijkstra Pathfinding (`locations/pathfinding.py`)
* **What problem it solves**: Instead of letting the player teleport or describe traveling across impossible distances, the world needs realistic distances and movement costs.
* **How Hikayat works**: World geography is stored in SQLite as nodes and connections across a 3-tier hierarchy (*Zone ➔ Facility ➔ Room*). When a player travels, the engine runs Dijkstra’s shortest-path algorithm to calculate transit time, stamina cost, travel fares, locked door requirements, and curfew checks before moving the player.

### 4. Mathematical Alert State Machine for Stealth Gameplay (`mechanics/stealth/`)
* **What problem it solves**: Stealth in text games usually relies on the AI guessing whether a guard notices you.
* **How Hikayat works**: Stealth uses a mathematical alert state machine per NPC (`UNAWARE`, `SUSPICIOUS`, `SEARCHING`, `DETECTED`). The code calculates noise levels based on armor weight, companion footsteps, lighting conditions, and player action loudness to determine detection accumulation and alert decay deterministically over time.

### 5. Multi-Engine Quest Architecture & Forensic Dossiers (`game_engine/quest_agency.py`, `mechanics/narrative/dossier_compiler.py`)
* **What problem it solves**: Quests in AI games easily lose focus, forget objectives, or conclude abruptly without resolving clues.
* **How Hikayat works**: Quests are categorized into specific operational engines (Investigation, Bounty, Social Infiltration, Survival) and tracked in relational database tables (`quests`, `quest_dossiers`, `session_clues`). As players uncover evidence and interview witnesses, the system compiles structured forensic dossiers with verifiable leads and sub-objectives in SQLite.

### 6. World Pulse & Autonomous Background Simulation (`mechanics/world/world_events/`)
* **What problem it solves**: Static RPG worlds feel frozen in place whenever the player is not actively looking at an area.
* **How Hikayat works**: Alongside player turns, the engine simulates background rumors, weather shifts, faction skirmishes, political scandals, and economic crises across different map zones. Events have countdown timers and can escalate into larger emergencies if the player neglects them.

### 7. Vector Memory Compaction & Sliding Token Budgets (`mechanics/system/memory/`)
* **What problem it solves**: Large language models have strict context limits and become slow or expensive as chat history grows.
* **How Hikayat works**: The engine uses SQLite-based vector retrieval alongside a multi-tier memory system. Recent turns remain in high detail, while older events are automatically digested into condensed factual bullet points and indexed by embeddings. This allows multi-hundred-turn campaigns to maintain long-term memory without hitting context limits.

### 8. Dual-Model Cascade & Output Headroom Management (`llm_client.py`)
* **What problem it solves**: Creative prose generation is slow and expensive, while routine data tasks don't need a large model.
* **How Hikayat works**: The engine divides workloads between two models: an expressive model for rich narrative prose, and a fast, lightweight utility model (`LLM_UTILITY_MODEL`) for background parsing, clue extraction, and choice generation. The client also includes automatic fallback to secondary API providers on rate limits and enforces a 3,500-token output headroom margin to prevent JSON truncation errors.

### 9. 5-Language Dictionary Canonicalization & Anti-Drift Pronoun Engine (`localization/`, `game_engine/pronoun_resolver.py`)
* **What problem it solves**: Multi-language support often breaks formatting, and language models frequently mix up character pronouns during long scenes.
* **How Hikayat works**: The game maps game actions, combat choices, and inventory terms through localized dictionary files in English, Polish, Malay, German, and Simplified Chinese. An automated pronoun scanner checks entity genders against database IDs to prevent language models from mistakenly swapping pronouns during complex multi-character scenes.

### 10. Headless Omnichannel Game Loop (`services/turn_service.py`)
* **What problem it solves**: Supporting both a Discord bot and a web application usually means duplicating game logic or risking feature divergence.
* **How Hikayat works**: The core game logic in `TurnService` is completely headless. Both the Discord bot (using slash commands, buttons, and modals) and the modern React web application (using REST endpoints and WebSockets) interact with the exact same Python service and database backend.

---

## 🎮 10 Unique Gameplay Features
*(What you actually experience as a player)*

### 1. Play in Your Browser or on Discord
* **What it looks like**: You can play either using Discord slash commands and button decks, or open the modern React web application in your browser.
* **How it plays**: The web version provides a dark-fantasy interface with a live story feed, clickable choices, an inventory drawer, character status meters, and an interactive world map modal.

### 2. Tactical Action Dock & Belt Hotbar (`web/src/components/`)
* **What it looks like**: A persistent sidebar on the web screen with dedicated action buttons.
* **How it plays**: You can click buttons to enter stealth mode, drink a potion from your belt hotbar, check the time, or examine the room immediately without typing text commands or opening separate menus.

### 3. Turn-Based Tactical Combat with Telegraphed Enemy Moves
* **What it looks like**: A structured 7-slot combat menu (*Attack, Defend, Magic, Item, Flee, Tactician, Switch Target*) with calculated hit and damage numbers.
* **How it plays**: Enemies clearly display what they plan to do on the next turn (such as charging a heavy blow, casting a spell, or ducking into cover), allowing you to choose whether to block, counter-attack, dodge, or interrupt their action.

### 4. Functional In-Game Smartphone (`/phone`)
* **What it looks like**: An in-game smartphone interface with messaging, contacts, camera, and apps.
* **How it plays**: Your character carries a phone that you can use to browse contacts, text NPCs, receive photos, schedule meetups, and read local town or school gossip feeds that update as the story develops.

### 5. Real-Time Clock & Circadian NPC Schedules
* **What it looks like**: An in-game clock advancing across 8 distinct daily phases (Dawn, Morning, Afternoon, Dusk, Night, etc.).
* **How it plays**: Non-player characters follow daily schedules based on their jobs, grades, or factions. They commute to work, attend classes, eat at restaurants, and sleep at home. If you visit a shop after hours, the owner will not be there.

### 6. Detailed Social Relationships & Family Trees
* **What it looks like**: NPCs have documented family members, occupations, personal traits, and relationship levels.
* **How it plays**: Interacting with an NPC builds relationship points across platonic, rivalry, professional, or romantic tracks. High affinity unlocks milestone dialogue choices and new quest leads.

### 7. Entity Contracts & Eldritch Pacts (`/contracts`)
* **What it looks like**: A formal covenant agreement window displaying terms, tithes, taboos, and granted powers.
* **How it plays**: You can negotiate pacts with mysterious patrons and anomalous entities. Accepting a pact grants passive combat bonuses or special traits, but binds your character to behavioral restrictions and penalties if you violate the agreement.

### 8. Realty & Safehouse Ownership (`/realty`)
* **What it looks like**: Real estate listings allowing you to purchase or rent apartments, cabins, and safehouses across map zones.
* **How it plays**: Owned properties act as private bases where you can rest safely, store valuable gear away from pickpockets, set up protective wards against anomalies, and invite contacts for discreet meetings.

### 9. Interactive Folklore Codex & Occult Research (`EncyclopediaSubTab.jsx`)
* **What it looks like**: An in-game encyclopedia tab detailing local legends, mythical beasts, and occult lore.
* **How it plays**: Exploring old ruins or investigating urban myths unlocks entries in the codex. Studying monster weaknesses and ancient rituals gives your character concrete dialogue options and tactical bonuses when facing supernatural threats.

### 10. World Pulse Regional Crises & Living Factions (`/factions`)
* **What it looks like**: A live dashboard displaying ongoing faction skirmishes, resource shortages, and seasonal events.
* **How it plays**: The game world is divided among competing factions. You can track their territorial influence, complete bounty contracts for specific groups, and change how different factions treat you.

---

## 🕹️ How to Play

### Character Creation & SPECIAL Stats
1. Launch character creation using `/character create` or the web character creator modal.
2. Distribute points across the 7 core **SPECIAL** attributes:
   * **Strength (STR)**: Melee damage and inventory weight limit (+3 slots per point).
   * **Perception (PER)**: Ranged accuracy, environmental awareness, and spotting clues.
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
├── api/                        # FastAPI REST endpoints (adventure, codex, contracts, realty, security)
├── bin/                        # Auxiliary network & tunnel utilities
├── cogs/                       # Discord Bot slash command cogs & interactive button views
├── data/                       # Static game catalogs (classes, scenarios, locations, folklore, storylets)
├── db/                         # Modular SQLite persistence layer (sessions, characters, properties, contracts)
├── game_engine/                # Core turn pipeline, state reducers, cast planner & quest resolvers
├── localization/               # Multi-language translation dictionaries (en, pl, ms, de, zh)
├── mechanics/                  # Domain-specific simulation modules
│   ├── combat/                 # Combat formulas, weapon tables, armor DT, spells & awakened resonance
│   ├── narrative/              # Quest engines, dossiers, campaign spine, blueprints & intent parser
│   ├── pacts/                  # Entity contracts, patrons, geas rules & pact lifecycle
│   ├── social/                 # Roster generation, relationship graph, social pacing & deck
│   ├── stealth/                # Mathematical alert state machine, noise formulas & escalation
│   ├── system/                 # In-game smartphone, time engine, memory compaction & input sanitizer
│   └── world/                  # 3-tier spatial graph, Dijkstra pathfinding, realty & world events
├── models/                     # Centralized Pydantic schemas & state models
├── releases/                   # Version changelogs & clean release archives
├── scripts/                    # Maintenance, release packaging & session cleanup utilities
├── services/                   # Decoupled turn execution service (TurnService)
├── web/                        # React Single-Page Application (Vite, Tailwind, i18n)
│   ├── dist/                   # Compiled production frontend bundle (served by FastAPI)
│   └── src/                    # ActionPanel, CodexPanel, StoryFeed, modals & themes
├── config.py                   # Central configuration & environment loader
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
