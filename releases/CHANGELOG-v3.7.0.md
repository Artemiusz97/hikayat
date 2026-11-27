# Hikayat Release Changelog — v3.7.0

**Release Date:** 2026-11-27  
**Type:** Minor Release  
**Milestone:** Multi-Realm World Hierarchy & Dynamic Ephemeral Rifts, Hidden Veiled Spirit Realm v2 & Three Autonomous Spirit Courts (Kitsune, Bunian, Dual-Form Al-Ghul), Categorized Online Store & SchoolMart, 24h Analog Clock Dial, Stature/Anatomy Reaction Engine, Tailscale Private Remote Play & Monolith Package Completion

---

## 🌟 Overview

Hikayat **v3.7.0** introduces a first-class **Multi-Realm Architecture** (`mechanics/world/locations/realms/`) alongside the full expansion of **The Veiled Spirit Realm** (`realm_veiled_spirit_world` — Migrations 62 & 64), featuring three autonomous **Spirit Courts** (*Kitsune, Orang Bunian, Dual-Form Al-Ghul*), **90+ Sworn Ally Native Combat Summons**, cross-realm commission boards, and nine Spirit World events. Alongside these world expansions, v3.7.0 adds a categorized **Smartphone Online Store & Student SchoolMart**, an interactive **24-hour Analog Clock Dial** for Time Skip, **Stature/Physique/Rear** build customization paired with an anatomy-aware excitement engine, **Teen/Student Employment Policy** safeguards, **Tailscale private remote play** authentication, and completes the monolith-to-package decomposition of all remaining backend and React SPA modules.

---

## 🚀 Key Implementations & Enhancements

### 1. Multi-Realm Hierarchy, Dynamic Ephemeral Rifts & Vessel Travel (`mechanics/world/locations/realms/`, `data/dynamic_realm_templates.json`, Migration 63)
- **First-Class `REALM` Nodes (`hierarchy.py`, `lifecycle.py`, `summary.py`, `choices.py`)**: Extended spatial navigation to a 4-tier hierarchy (*Realm ➔ Zone ➔ Facility ➔ Room*) supporting seeded alternate dimensions, planetary worlds, orbital stations, mobile vessels, temporal scaling/stasis (`time_scale`), realm communication isolation (`check_realm_comms_available`), and `portal_cross` transitions with strict same-realm fast-travel guards (`services/turn/prepare.py`).
- **Dynamic Ephemeral Rifts & Vessel Operations (`vessels.py`, `data/dynamic_realm_templates.json`)**: Added template-driven anomalous pockets (`anomalous_rift_open`, `anomalous_rift_lockdown`) with spawn, pacification, collapse, and turn-rollback lifecycle hooks, plus mobile starship FTL jump plotting (`execute_starship_jump`, `execute_recall_starship`) and bounded `dock_history` rollback.
- **Save-Slot Realm Metadata & World Map Integration (Migration 63, `WorldMapModal.jsx`)**: Added `realm_name` and `show_realm_badge` columns to `adventure_saves` (`adventure_saves_realm_meta_v63`), gateway teleportation cards (`realm_gateways`), and off-realm quest indicators inside the World Map.

### 2. Hidden Veiled Spirit Realm Expansion, Autonomous Spirit Courts & Dual-Form Al-Ghul (Migrations 62 & 64, `folklore_spirit_realm.py`, `folklore_spirit_courts.py`, `folklore_ghoul.py`)
- **8-Zone Veiled Spirit Realm (`data/locations_seed.json`, `data/folklore_villages_catalog.json`)**: Expanded `realm_veiled_spirit_world` into *Dusk Confluence Bazaar* (`zone_spirit_crossroads` neutral truce zone with 4-wing Night Market), 3 discoverable Spirit Enclaves (*Sato-no-Inari* Kitsune, *Kampung Kayangan* Orang Bunian, *The Pale Ossuary* Al-Ghul plus the Chinatown Shortcut Rite and Undercity *Black Font* threshold), and 4 exploration frontier biomes (`zone_spirit_wilds`, `zone_spirit_peaks`, `zone_spirit_mire`, `zone_spirit_boneyard`).
- **Autonomous Spirit Courts & 90+ Sworn Ally Summons (`folklore_spirit_naming.py`, `spirit_court_perks.py`)**: Added deterministic per-session procedural enclave and court names, 40 Spirit Realm roster templates, friendly sparring drills (`resolve_spirit_sparring_drill`), standing-unlocked Guest-Cottages (`>= 70` rep), court shop price multipliers, and stackable **Sworn Ally (`>= 90` rep) Passive Stat Auras & 3-Turn Native Combat Summons** (*Summon Myōbu Fox-Spirit, Summon Kayangan Mist-Guardian, Summon Mirage Pack Canid*).
- **Dual-Form Al-Ghul Mechanics (`folklore_ghoul.py`)**: Implemented contextual humanoid/canid form shifting across patrol/enclave zones (`striped_hyena`, `wolf`, `coyote`, `jackal`), Distrusted Sentinel Toll/Nerve gates, and Ossuary Blood-Truce Exile & Atonement.
- **Cross-Realm Commission Boards & 9 Spirit World Events (`spirit_court_bounties.py`, `spirit_realm_events.py`, `data/world_events_catalog.json`)**: Added rotating Spirit Court HQ commissions (including Two-Track Ghoul jobs separating dark crimes from zero-splash grey-neutral contracts) and 9 realm-scoped festivals & crises (*Grand Twin-Moon Night Fair, Midnight Shadow-Curio Auction, Tide of Drifting Lanterns, Nine-Tail Kagura Mask Revelry, Malam Berinai Feast, Night of the Pale Wake, Neon-Static Leyline Surge, Syndicate Cold-Iron Raid, Feral Al-Ghūl Pack Hunt*).

### 3. Categorized Online Store, Student SchoolMart & Phone Personalization (`mechanics/combat/online_store.py`, `PhoneShopApp.jsx`, `PhoneSettingsApp.jsx`)
- **Origin-Aware Categorized Online Store & SchoolMart (`online_store.py`, `api/inventory_merchant.py`, `PhoneShopApp.jsx`)**: Replaced flat smartphone item lists with daily-rotating, single-row tabbed catalogs (*All, Food, Drinks, Meds, Gifts, Clothing, Accessories, Weapons, Armor, Arcane, Adult, Study & Stationery, Apparel*), scenario-themed storefronts, automatic **SchoolMart** 20% + CHA student discounts with anti-exploit resale tagging, active-combat courier lockouts, and realm communication / Ossuary Bone-Relay checks.
- **Smartphone Customization Studio (`PhoneSettingsApp.jsx`, `PhonePhotoLightbox.jsx`, `web/public/phone-wallpapers/`)**: Added 11 bundled `.webp` phone wallpapers (`AUTO_SCENARIO_WALLPAPER_ID`, *Aurora Silk*, and scenario presets), frosted-glass vs. classic Phone themes, customizable wallpaper dim/focal point and carousel pools, and an interactive photo lightbox.

### 4. Analog Clock Dial, Build/Anatomy Reaction Engine, Employment Policy & Omnichannel Parity (`AnalogClockDial.jsx`, `anatomyOptions.js`, `intimate_excitement.py`, `employment_policy.py`, `cogs/character.py`)
- **Interactive 24-Hour Analog Clock Dial (`AnalogClockDial.jsx`, `TimeSkipModal.jsx`, `SettingsModal.jsx`)**: Added a draggable 24h radial SVG clock dial with 15-minute snapping, dawn/day/dusk/night sweep indicators, temporal stasis display, and user-selectable Dial vs. Slider preference toggle (`timeSkipControl`).
- **Stature, Physique, Rear Build & Anatomy Reaction Engine (`CharacterCreatorModal.jsx`, `CharacterSheet.jsx`, `cogs/character.py`, `intimate_excitement.py`)**: Added hero & NPC `stature`, `physique`, `rear_size`, `rear_texture`, `species_surface`, and partner `body_preferences` across React Web UI, `/character appearance` Discord editor, and 5-language dictionaries (`localization/`), plus anatomy- and preference-aware excitement multipliers with zero-number narrative reaction cues (`evaluate_anatomy_excitement_modifiers`).
- **Unified Operative & Intimate Dossier Cards (`OperativeCombatDossierCard.jsx`, `IntimateDossierPanel.jsx`)**: Standardized combat/civilian classification and intimate dossier rendering across Scene Side Cards, Contacts, Acquaintances, and Known Characters.
- **Teen/Student Civilian Employment Policy (`employment_policy.py`)**: Enforced age-appropriate commercial part-time shift policies for teen/student civilians with automatic save healing while exempting teen Special Agents.

### 5. Complete Package Decomposition, Layer-Boundary Inversion, Security & Launchers (`llm_client/`, `game_engine/choices_cleaner/`, `db/quests/`, `db/dossiers/`, `cogs/adventure/embeds/`, `api/codex_phone/`, `launchers/`)
- **Backend & React Package Splits**: Extracted the remaining monolithic modules into cohesive domain packages (`llm_client/`, `game_engine/choices_cleaner/`, `db/quests/`, `db/dossiers/`, `cogs/adventure/embeds/`, `api/codex_phone/`) and decomposed `GameView.jsx`, `useGameSession.js`, `PhoneModal.jsx`, `CodexPanel.jsx`, and `ContactsPanel.jsx` backed by shared `useEscapeLayer.js` LIFO Escape handling.
- **Layer Boundary Purification & Concurrency Hardening**: Inverted upward `db/` imports via `services/anomalous_containment_service.py` and module-level `db.register_session_rollback_hook` (0 layer violations across 530 logic files), eliminated N+1 hydration loops, unified multi-step writes/rollbacks under atomic `UnitOfWork`, offloaded remaining asyncio loop DB calls (`bot.py`, `ZoneSelectView`), and fixed SPA start/auth/turn race conditions.
- **Tailscale Remote Play & Launcher Organization (`api/security.py`, `bin/tunnel.py`, `launchers/`)**: Added verified `is_trusted_tailscale_request` IP/header authentication, refactored tunnel management (`bin/tunnel.py`), relocated `run_web_share.bat` and `run_web_tailscale.bat` into `launchers/`, defaulted `DB_PATH=data/hikayat.db` in `.env.example`, and hardened `scripts/package_release.py` to scan for embedded LAN IPs and secret tokens.

### 6. Automated Quality Gates & 5-Language Parity (`.agents/`, `web/src/locales/`, `localization/`)
- **Agentic Audit & Release Gate Tooling (`.agents/`)**: Added the `safety_guard.py` PreToolUse hook, static audit helpers (`run_release_gate.py`, `audit_module_boundaries.py`, `audit_prompt_hygiene.py`, `audit_route_auth.py`, `check_locale_parity.py`, `check_table_wiring.py`), and specialized auditor subagents.
- **5-Language Locale Backfill & Contract Parity (`en`, `pl`, `ms`, `zh`, `de`)**: Expanded and synchronized `1,971` web i18n JSON keys and Python localization dictionaries covering `NpcDossierBody`, Spirit Courts, Online Store/SchoolMart, Stature/Physique/Anatomy, and Analog Clock controls.

---

## 📦 Distribution Packages
- **Clean Production Archive**: `releases/hikayat-v3.7.0-clean.zip` (Zero tests, zero icon assets, zero generated images, zero user fonts, zero `.exe` binaries, zero databases, zero secrets or personal path leaks).
- **Full Development Backup**: Branch `backup/v3.7.0` & Tag `v3.7.0-full` (Tracked repository snapshot mirrored to remote GitHub alongside local full test/dev backup archive `data/backups/hikayat-v3.7.0-tests-backup.zip`).
