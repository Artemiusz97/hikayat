# Changelog — Hikayat v1.3.0

**Release Date:** 2026-08-03  
**Release Type:** Minor (Dynamic NSFW Routing & Fallback Cascade.)  
**Package:** `hikayat-v1.3.0-clean.zip`

---

## 🌟 Most Recent Changes (v1.3.0 Highlights)

### 1. Dynamic NSFW Model Routing (`config.py`, `scenario_data.py`, `llm_client.py`)
* Added dedicated `NSFW_LLM_MODEL` / `NSFW_LLM_API_KEY` environment variables to automatically route adult scenarios to uncensored models.

### 2. LLM Fallback Cascade & Timeout Controls (`config.py`, `llm_client.py`)
* Configured multi-model fallback chains with per-attempt timeout management.

### 3. Opening Narrative Fallback Guardrail (`game_engine.py`, `cogs/adventure.py`)
* Embedded SCENE_SCHEMA in initial prompts to eliminate blank opening scenes on Gemini models.

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
| **v1.3.0** | 2026-08-03 | Minor | Dynamic NSFW Routing & Fallback Cascade. |
| **v1.2.0** | 2026-08-03 | Minor | Locations, Debug Suite & Roster Expansion. |
| **v1.1.0** | 2026-08-01 | Patch | LLM Reliability & Narrative Balancing. |
| **v1.0.0** | 2026-07-25 | **MAJOR** | Genesis Release: Core RPG Engine, Discord Bot, FastAPI Web UI & Audio Engine. |

---

## 📜 Full Release History

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
