# Hikayat (v3.7.0) — Living AI Tabletop RPG & Web Application

[![Version](https://img.shields.io/badge/version-3.7.0-blue.svg)](releases/CHANGELOG-v3.7.0.md)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![React 18](https://img.shields.io/badge/react-18.2-61dafb.svg)](web/)

Hikayat is a text-based role-playing game (RPG) where an AI language model generates the story and dialogue, while a deterministic Python game engine calculates the actual rules, rolls, and state changes. It can be played either as a Discord bot or as a web application in your browser.

---

## 🛠️ What Makes Hikayat Different

### 1. Deterministic Simulation Before AI Narration
* **The problem with typical AI RPGs**: Language models fudge dice rolls, arbitrarily invent HP or inventory changes, and let persuasive prompts break game rules.
* **How Hikayat solves it**: Every turn runs through a 5-phase deterministic Python engine first—resolving intent, SPECIAL skill checks, Fallout-style Armor DT/DR, cooldowns, stamina, item charges, and quest progression. Only after locking the exact outcome into an immutable turn snapshot does Hikayat ask the LLM to narrate what happened, scrubbing raw numbers and internal tags so stats never leak into prose.

### 2. Closed-World Persistent NPC Roster & 6-Tier Presence Resolution
* **The problem with typical AI RPGs**: "Phantom NPCs" speak when they are not in the room, disappear mid-conversation, or turn into throwaway characters regenerated on every visit.
* **How Hikayat solves it**: Every character belongs to a persistent closed-world SQLite roster (seeded lazily on demand). Before each turn, a 6-tier presence resolver checks party companions, circadian work/sleep schedules, active commitments, quest pins, and private-residence access rules so the AI can only write dialogue for characters physically present in the scene.

### 3. Structured 4-Tier World Graph & Dijkstra Pathfinding
* **The problem with typical AI RPGs**: Geography exists only as loose prose, allowing impossible teleportation or contradicting room layouts two turns later.
* **How Hikayat solves it**: World topology is modeled in SQLite across a 4-tier relational graph (*Realm ➔ Zone ➔ Facility ➔ Room*) with explicit connections, access tiers, curfews, temporal scaling, and dimensional communication boundaries. Travel executes Dijkstra’s shortest-path algorithm to enforce transit time, stamina, fares, and locked barriers deterministically.

### 4. Epistemic Asymmetry & Server-Side Fog-of-War
* **The problem with typical AI RPGs**: Either every NPC telepathically knows everything the player has done, or characters never hear rumors or react to past actions.
* **How Hikayat solves it**: Hikayat explicitly tracks *who knows what* in normalized tables. Witnesses log observed events, rumors decay or spread one hop across social ties over time, NPC alibis are checked for contradictions, and server-side Fog-of-War withholds undiscovered schedules, secrets, and locations from both the UI and the narrator until genuinely learned.

### 5. Physical Continuity, Garment Layering & Posture State Machine
* **The problem with typical AI RPGs**: Characters juggle impossible combinations of gear, change outfits randomly between paragraphs, or ignore physical constraints like restraints.
* **How Hikayat solves it**: A dedicated physical-state engine tracks posture, held items, restraints/tethers, 12 equipment slots, layered garments, and contextual NPC wardrobes (*Duty, Casual, Sleepwear*, and activity presets)—enforcing physical constraints mechanically and grounding both prose and optional scene artwork.

### 6. Mathematical Stealth & Per-NPC Alert State Machine
* **The problem with typical AI RPGs**: Sneaking depends entirely on prompt luck rather than consistent rules for sound, visibility, or escalation.
* **How Hikayat solves it**: Each NPC runs an explicit alert state machine (`UNAWARE` ➔ `SUSPICIOUS` ➔ `SEARCHING` ➔ `DETECTED`). Noise and detection math factor in armor weight, companion footsteps, lighting, and action loudness, automatically syncing stealth and distraction choices whenever stealth posture is toggled.

### 7. Hybrid Long-Term Memory (Normalized SQLite + FTS5 + Vector Compaction)
* **The problem with typical AI RPGs**: Long campaigns collapse once chat transcripts overflow the model's context window—forgetting quests, inventory, or relationships while burning tokens on raw history.
* **How Hikayat solves it**: Authoritative world state lives in normalized SQLite tables rather than chat logs alone. Older turns are deterministically compacted into searchable chapter digests indexed with multilingual FTS5 and semantic embeddings, keeping long-running campaigns coherent within tight KV-cache-friendly prompt budgets.

### 8. Atomic Turn Transactions, Deterministic Rollback & Portable Save Slots
* **The problem with typical AI RPGs**: A stalled generation or bad turn leaves story state half-mutated, and rewinding or branching campaigns risks orphaned data.
* **How Hikayat solves it**: Multi-step turn mutations execute inside atomic SQLite Units of Work governed by a declarative 44-table session lifecycle registry. Failed turns roll back cleanly without corrupting state, players can rewind turns deterministically, and save/load slots remap every child record cleanly across branches.

### 9. Dual-Mode Streaming, Multi-Model Routing & Anti-Drift Guardrails
* **The problem with typical AI RPGs**: Local or reasoning models stall on structured JSON streaming, leak `<think>` blocks into prose, waste expensive tokens on utility tasks, or drift on character pronouns mid-scene.
* **How Hikayat solves it**: Live narration streams through a dual-mode sentinel/JSON extractor with split Time-To-First-Token and idle stall timers, Chain-of-Thought suppression, fallback cascades, lightweight utility-model offloading, optional isolated mature-model routing, and database-backed pronoun grounding across 5 languages.

### 10. Headless Single-Engine Architecture for Web, Discord & Co-Op
* **The problem with typical AI RPGs**: Games are either trapped in a single chat box or split across separate web and bot implementations whose rules drift apart.
* **How Hikayat solves it**: Turn execution, state reducers, and zero-turn scene inspection run headlessly behind one authoritative Python service layer with distributed session locking—powering a real-time WebSocket React SPA, full Discord bot views, and synchronized multiplayer parties from a single source of truth, with built-in Cloudflare Tunnel and private Tailscale remote play.

---

## 🎮 Gameplay Features

### 1. Hybrid Action Loop: Smart Choices, Free-Text Input & Zero-Turn Examine
* **What it looks like**: Pick from context-aware choices (with optional skill-check odds), type any custom action in plain text, or open **Examine (`0 Turns`)** from the persistent action dock.
* **How it plays**: Free-text inputs are classified into real mechanics and dice rolls rather than hand-waved prose. Examining a scene costs zero turns and reveals live structured intel—present NPCs (posture, visible attire, `PER`-gated mood tells, instant *Use Item* / *Gift* actions), dropped floor items for one-click pickup, active leads, stealth/witness status, and enemy weaknesses.

### 2. Turn-Based Tactical Combat with Telegraphed Moves, Armor DT/DR & Auto-Loot
* **What it looks like**: A structured 7-slot battle menu (*Attack, Defend, Magic/Skills, Item, Flee, Tactician, Switch Target*) with toggleable enemy HP bars and intent badges.
* **How it plays**: Enemies telegraph upcoming attacks so you can time blocks, dodges, counters, or interrupts against Fallout-style flat Damage Threshold (DT) and percentage Damage Resistance (DR). Defeating foes deterministically deposits auto-loot directly into your inventory so rewards are never lost to narration gaps.

### 3. Deep Character Creation, SPECIAL Progression & 12-Slot Loadouts
* **What it looks like**: Full character sheets with 7 **SPECIAL** attributes, customizable demographics and build traits, 12 dedicated equipment slots (*Head, Armor, Top, Bottom, Weapon, Shield, Gloves, Shoes, 4 Accessories*), and a **Quick Belt**.
* **How it plays**: Attributes mechanically shape carry weight, examine detail, XP scaling, evasion, crits, and haggling discounts. A 5-mode consumable system automatically separates instant out-of-combat quick-use healing/buffs from turn-consuming meals, gifts, and covert items.

### 4. Living World Clock, 24-Hour Analog Time Skip & Circadian NPC Routines
* **What it looks like**: A toggleable `12h`/`24h` world clock, an interactive draggable **24-Hour Analog Clock Dial** (or slider) for skipping time, and progressive Contacts & Acquaintances cards.
* **How it plays**: Time advances realistically as you travel, wait, or rest. Persistent NPCs follow weekly work shifts, hangout habits, and sleep schedules—shops close when staff are off duty, private homes stay gated until you are invited, and NPCs swap outfits naturally across contexts (including wearable gifts you give them).

### 5. Multi-Track Relationships, Households & Living Rumor Networks
* **What it looks like**: Rich NPC dossiers tracking relationship tiers, family trees, discovered preferences, shared memories, and faction standing.
* **How it plays**: Bonds evolve independently across platonic, professional, rivalry, and romantic tracks with persistent gift ownership and milestone unlocks. Witnesses remember what they saw—rumors spread across local social circles, NPCs can be caught in lies, and you can confront, persuade, or hush witnesses instead of playing in a memoryless sandbox.

### 6. Interactive World Map, Real Travel & Multi-Realm Exploration
* **What it looks like**: A native `<dialog>` **World Map** displaying connected regions, facilities, sub-rooms, access badges, active quest markers, and realm gateways.
* **How it plays**: Moving between places calculates real transit time, stamina, and travel fares while enforcing locked doors, curfews, and Fog-of-War discovery—extending seamlessly from neighborhood rooms up to alternate planes, starships, and distant worlds depending on your campaign.

### 7. True Stealth & Infiltration Mechanics
* **What it looks like**: A one-click Stealth toggle with live per-NPC alert status and stealth-adapted action choices.
* **How it plays**: Toggling stealth dynamically swaps scene options toward sneaking, distractions, pickpocketing, or ambushes. Armor noise, lighting, companions, and risky actions shift individual guard alert levels from *Unaware* to *Detected*, rewarding careful positioning and timing.

### 8. Structured Quests, Forensic Caseboards & Ticking Threat Clocks
* **What it looks like**: Dedicated Quest Log, Bounty Board, and Forensic Dossier views tracking active objectives, clues, suspects, and regional crises.
* **How it plays**: Investigations, bounties, infiltration jobs, and survival arcs run on structured quest engines backed by 6-segment **Threat Clocks** and Chapter Plans—preventing quests from stalling out, advancing world consequences if threats go unchecked, and tying witnesses and clues together cleanly.

### 9. Omnichannel Web & Discord Play, Co-Op, Save Slots, Rollback & Optional Scene Artwork
* **What it looks like**: A customizable React 18 Web SPA (frosted Acrylic modes, opacity/text scaling, drop-in custom fonts, 12 time-of-day graded backdrops, searchable **Turn History**) with full Discord bot parity.
* **How it plays**: Play solo or join synchronized multiplayer co-op sessions from browser or Discord (including remote play via Cloudflare Tunnel or private Tailscale). Branch stories with multiple **Save Slots**, rewind turns cleanly, and optionally generate live SDXL scene illustrations grounded in present characters, attire, and lighting.

### 10. Genre-Adaptive Worlds, Narrative Pacing & 5-Language Play
* **What it looks like**: 21 playable scenario presets paired with dedicated **Narrative Pacing** (*Concise, Balanced, Novelistic*), **Prose Style** (*Normal, Vivid, Noir, Witty, Shakespearean, Brainrot*), and instant language switching.
* **How it plays**: Play across Fantasy, Dark Fantasy, Isekai, Sci-Fi, Cyberpunk, Steampunk, High School Drama, Slice of Life, Post-Apocalypse, and Urban Supernatural worlds—with native currencies, classes, and setting-appropriate systems adapting automatically—in **English, Polish, Malay, German, or Simplified Chinese**.

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
