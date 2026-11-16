# Hikayat Release Changelog — v3.2.0

**Release Date:** 2026-11-16  
**Type:** Minor Release  
**Milestone:** Dynamic NPC Wardrobe & Physical State Continuity Engine (`mechanics/social/wardrobe/`), SDXL Attire Tag Synthesis, Fog-of-War `KnownWardrobeCard` Dossier UI & 5-Language Parity

---

## 🌟 Overview

Hikayat **v3.2.0** adds the **Dynamic NPC Wardrobe Engine** (`mechanics/social/wardrobe/`), tying character clothing directly to schedules, venues, activities, wearable gifts, and player requests while preserving strict Fog-of-War secrecy. Discovered outfits persist cleanly across turn rollbacks, feed directly into SDXL image prompt synthesis, and render consistently across both the React Web UI (`KnownWardrobeCard.jsx`) and Discord Contacts embeds in all 5 supported languages.

---

## 🚀 Key Implementations & Enhancements

### 1. Dynamic NPC Wardrobe Package (`mechanics/social/wardrobe/`)
- **Context-Aware Presets & Activity Kits (`constants.py`, `catalog.py`, `resolver.py`)**: Defined genre-aware `duty`, `casual`, and `sleepwear` presets alongside activity kits (`swim`, `sport`, `dojo`, `bath`, `tactical`, `secret_faction`) and contextual overlays (`apron`, `lab_coat`, `modesty_robe`) driven by time windows and sub-locations (`evaluate_turn_wardrobe_transitions`, `resolve_actor_wardrobe_state`).
- **Wearable Gifts & Outfit Requests (`requests.py`)**: Added `classify_wearable_gift_target`, `route_wearable_gift_to_preset`, `detect_outfit_request_intent`, `evaluate_outfit_request_compliance`, and viewer modesty gating (`resolve_viewer_sleepwear_modesty`).
- **Fog-of-War Dossier Tracking (`dossier.py`)**: Added `build_known_wardrobe_payload`, `prepare_witnessed_wardrobe_entries`, and `record_witnessed_wardrobe_preset` so unencountered outfits remain masked (`???`).

### 2. Physical State, Persistence & Turn Pipeline Continuity (`db/`, `game_engine/`, `mechanics/social/physical_state.py`)
- **Schema & Rollback Parity**: Updated `actor_physical_states` in `db/core.py`, wired turn rollback in `db/sessions.py`, and added batched preset discovery persistence (`upsert_wardrobe_preset_discoveries_batch`) in `db/social_pacing.py`.
- **Pipeline Integration**: Extended `mechanics/social/physical_state.py`, `game_engine/state/reducers.py`, `game_engine/state/social.py`, `game_engine/npcs/stage_manager.py`, `mechanics/social/relationships.py`, and `mechanics/system/phone/messaging.py`.

### 3. SDXL Attire Prompt Synthesis (`mechanics/narrative/image_prompt_composer.py`)
- **Visual Wardrobe Consistency**: Added `_synthesize_sdxl_wardrobe_tags` and updated `format_npc_appearance_tags` and `compose_turn_image_prompt` so generated scene artwork reflects each NPC's active outfit.

### 4. Omnichannel UI & 5-Language Localization (`web/`, `cogs/`, `mechanics/social/locales.py`)
- **Web Dossier UI**: Added `web/src/components/Sidebar/KnownWardrobeCard.jsx` inside `ContactsPanel.jsx` and `AcquaintancesView.jsx` featuring the co-located `Currently Wearing` pill and discovered wardrobe rows.
- **Discord Embeds & Translations**: Added `format_discord_known_wardrobe_value` in `cogs/contacts_routine_views.py` and `cogs/contacts.py`, synced `mechanics/social/locales.py` and `web/src/locales/*.json` (`en`, `pl`, `ms`, `de`, `zh`), and rebuilt compiled `web/dist/` assets.

---

## 📦 Distribution Packages
- **Clean Production Archive**: `releases/hikayat-v3.2.0-clean.zip` (Clean production deployment: 0 tests, 0 icon files, 0 runtime images, 0 databases, 0 personal leaks).
- **Full Development Backup**: Branch `backup/v3.2.0` & Tag `v3.2.0-full` (Preserving tracked source snapshot cleanly alongside local `backups/hikayat-v3.2.0-tests-backup.zip`).
