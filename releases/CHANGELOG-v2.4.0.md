# Changelog — Hikayat v2.4.0

**Release Date:** 2026-10-21  
**Release Type:** MINOR (SDXL Scene Image Generation, Pre-Turn Stage Manager, Dynamic World Schedules, Spatial Graph & Dijkstra Navigation, Commitments Engine, Intimacy Ledger & Relationship Graph, 5-Language Localization)  
**Package:** `hikayat-v2.4.0-clean.zip`

---

## 🌟 Most Recent Changes (v2.4.0 Highlights)

### 1. SDXL Scene Image Generation & Local Media Persistence (`mechanics/media/`, `services/image_service.py`, `api/`)
* **Problem:** Text-only narratives lacked dynamic visual grounding, while remote image URLs often suffered from rate limits, broken CDNs, or ephemeral hosting loss.
* **Feature:** Built a local-first SDXL scene rendering engine:
  - **Dynamic Scene Prompt Synthesis**: Automatically compiles rich environment, lighting, character framing, and artistic atmosphere tokens from the latest turn prose.
  - **Negative Conditioning & Aesthetic Presets**: Injects style-calibrated negative prompts to eliminate visual artifacts and ensure consistent art direction across fantasy, sci-fi, and modern drama genres.
  - **Local Media Storage & Streaming**: Persists generated images to local storage with content-hash deduplication, serving assets directly via FastAPI static endpoints (`/api/media/{hash}.png`).
  - **Media Gallery & Smartphone Integration**: Photos, scene captures, and character snapshots are cataloged in the in-game Smartphone gallery with persistent narrative captions.

### 2. Pre-Turn Stage Manager & Living Scene NPC Presence Arbitration (`mechanics/world/stage_manager.py`, `game_engine/turn/`)
* **Problem:** NPCs in traditional text RPGs often appear and disappear haphazardly, speaking when not physically present or vanishing mid-conversation due to lack of spatial grounding.
* **Feature:** Introduced a deterministic Pre-Turn Stage Manager:
  - **Physical Presence Invariants**: Strictly categorizes characters as *Present in Scene*, *Nearby in Facility*, or *Off-Site*, preventing phantom dialogue from characters miles away.
  - **Dynamic Arrival & Departure Arbitration**: Arbitrates plausible arrivals, interruptions, and departures before choices and narration are generated.
  - **Ambient Crowd vs. Persistent Characters**: Isolates transient background patrons and crowd murmurs from registered school/codex NPCs, ensuring unique identities are never diluted.

### 3. World Routine & Dynamic NPC Schedules Engine (`mechanics/world/schedules.py`, `mechanics/world/locations/`)
* **Problem:** World characters felt static, lingering at fixed coordinates regardless of the time of day or academic calendar.
* **Feature:** Full daily schedule simulation driven by in-game time:
  - **Time-of-Day Activity Matrices**: Characters migrate across designated facilities throughout 8 distinct daily phases (Dawn, Morning Classes, Lunch, Afternoon Clubs, Study/Library, Evening Commercials, Dorms/Home, Night).
  - **Personality & Role Scoping**: Class officers, athletes, and loners follow distinct behavioral routines reflecting their clubs, grades, and disposition.
  - **Proactive Rendezvous Tracking**: When player appointments are scheduled, NPCs travel to designated meeting points and arrive on schedule, transitioning states from `pending` to `arrived`.

### 4. Spatial Graph Architecture, Dijkstra Navigation & Sub-Facility Waypoints (`mechanics/world/locations/spatial_graph.py`, `mechanics/world/locations/movement.py`)
* **Problem:** Spatial movements between complex buildings and campuses risked losing micro-spatial fidelity (e.g. collapsing specific conference tables or desks into generic room names) or allowing unrealistic teleportation through locked barriers.
* **Feature:** Formally modeled world geography as an explicit bidirectional spatial graph:
  - **Dijkstra Shortest-Path Traversal**: Computes legitimate travel paths, travel times, and distance penalties between world zones and micro-facilities.
  - **Granular Waypoint Preservation**: Maintains strict 3-tier precision (*Zone ➔ Establishment ➔ Sub-Facility*) across movement reconciliations, anchoring encounters to specific furniture and meeting stations.
  - **Access Gates & Keycards**: Restricts access to gated campus zones and private offices without required clearances, quest objectives, or staff escorts.

### 5. Commitments, Promises & Scheduled Rendezvous Engine (`mechanics/system/commitments_engine.py`)
* **Problem:** Promises, deadlines, and social appointments made in dialogue were easily forgotten by the LLM over multi-turn conversations.
* **Feature:** Engineered a centralized Commitments & Obligations Ledger:
  - **Two-Way Synchronization**: Synchronizes player commitments, study dates, and party rendezvous across SQLite tables.
  - **Lifecycle State Machine**: Tracks state transitions from `scheduled` to `reminder_sent`, `arrived`, `fulfilled`, `broken`, or `expired`.
  - **Social Repercussions**: Failing to honor scheduled appointments dynamically impacts relationship standing, reliability ratings, and character disposition.

### 6. Intimacy Ledger & Normalized Relationship Graph (`mechanics/social/relationship_graph.py`, `mechanics/social/persona/intimacy/ledger.py`)
* **Problem:** Interpersonal relationships and physical intimacy previously relied on flat scores, risking state corruption or loss of relationship history when tracks transitioned.
* **Feature:** Dual-engine social simulation architecture:
  - **Physical Intimacy Ledger**: Tracks granular physical milestones, partner preferences, and disclosure gating with immutable physical safeguard invariants (protecting predetermined virginity/experience status).
  - **Normalized Relationship Graph (`social_ties`, `social_persons`)**: Graph database schema tracking directed and mutual ties (dating, affairs, friendships, rivalries) with complete historical ex-partner retention.
  - **Write-Through Materialization**: Automatically materializes graph edges into legacy relations dictionaries, providing full backward compatibility for web UI codex panels.

### 7. 5-Language Internationalization Expansion (`localization/`, `web/src/locales/`)
* **Problem:** Internationalization was previously limited to three languages, restricting European and East Asian player accessibility.
* **Feature:** Expanded localization to five comprehensive languages across backend and frontend:
  - **5 Supported Locales**: English (`en`), Polish (`pl`), Malay (`ms`), German (`de`), and Simplified Chinese (`zh`).
  - **Full Dictionary Parity**: Real-time translation of item affixes, inventory lemmas, combat actions, dialogue intents, and UI interface strings.
  - **Responsive UI Language Switcher**: Persistent language preference selector integrated across web UI navigation and settings modals.

### 8. Anti-Hallucination Pronoun Consistency & Deterministic Turn Pipeline (`game_engine/pronoun_resolver.py`, `game_engine/turn/narration.py`)
* **Feature:** Robust anti-drift narrative pipeline:
  - **Multi-Tier Pronoun Resolver**: Validates narrative mentions against registered contact cards, preventing gender-drift in complex scenes with multiple third parties.
  - **Deterministic Turn Narration**: Decouples structured game outcome calculations (HP, damage, status effects, inventory changes) from creative prose generation, ensuring the LLM acts purely as a narrator bounded by code truth.

---

## 📦 Distribution & Packaging
* **Clean Distribution Archive**: Created `releases/hikayat-v2.4.0-clean.zip` excluding development test suites (`tests/`), icons (`icon/`), runtime databases (`*.db`), logs (`*.log`), and process locks.
* **Zero Private Information**: Automated audit ensures absolute absence of local file paths or developer credentials.
