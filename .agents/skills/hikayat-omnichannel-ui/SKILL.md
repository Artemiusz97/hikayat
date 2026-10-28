---
name: hikayat-omnichannel-ui
description: "Use this skill whenever developing, styling, or debugging Hikayat's React 18 Web SPA (web/), FastAPI REST & WebSocket backend (server.py, api/), or Discord Bot UI parity (cogs/)."
---

# Hikayat Omnichannel UI (React SPA, FastAPI & Discord Parity)

Hikayat delivers **100% gameplay parity** across its React 18 Web SPA (`web/`) and Discord Bot (`cogs/`), both backed by headless `services/turn_service.py`.

---

## 1. Real HTTP + WebSocket Turn Protocol (`web/src/hooks/useGameSession.js`)

Do **not** send turn actions over WebSockets. Hikayat separates HTTP command submission from WebSocket real-time streaming:

1. **Action Submission (HTTP POST)**:
   - `submitAction()` sends `POST /api/adventure/action` (180s client timeout via `web/src/api/client.js`) with `{ session_id, user_id, choice_index, custom_action_text, direct_choice, combat_target, intent, skip_minutes, sleep_mode, is_stealth, stance, action }`.
   - In multiplayer, if `data.status === "waiting_for_party"`, the UI sets `waitingForParty = true` until all party members lock picks.
   - On HTTP timeout/network error, `submitAction()` automatically recovers state via `GET /api/adventure/active-session/{user_id}`.
   - If `image_gen_enabled` is active and `scene_image_url` is not yet ready, `pollForSceneImage()` polls `GET /api/adventure/session-image/{sessionId}`.

2. **Real-Time Server Push & Party Chat (`/ws/session/{sessionId}?user_id={userId}`)**:
   - **Client -> Server**: Only `{ type: "PING" }` (15s keepalive) and `{ type: "CHAT", sender, message }`. Auto-reconnects after 2s on close.
   - **Server -> Client Events**:
     - `STREAM_START` / `STREAM_CHUNK` (`field`: `"outcome_narrative"` or `"next_narrative"`) / `STREAM_END` / `STREAM_ERROR`
     - `NEW_SCENE` / `UPDATE_SCENE` / `PICK_LOCKED` / `SCENE_IMAGE`
     - `STEALTH_STATE_UPDATED` (`stealth_state`, `stealth_badge`)
     - `CHAT_MESSAGE` / `PRESENCE_UPDATE` / `HEARTBEAT`

---

## 2. FastAPI Routers (`server.py`, `api/`) & Discord Cogs (`cogs/`)

### FastAPI Backend (`api/`)
- `api/adventure.py`: Session lifecycle (`/api/adventure/start`, `/join`, `/action`, `/end`, `/active-session/{uid}`), debug sandbox (`/api/debug/{uid}`).
- `api/codex_phone.py`: Contacts dossier (`/api/contacts/{sid}`), lorebook & commitments (`/api/lorebook/{sid}`), quests/bounties/clue deduction (`/api/quests/{sid}/...`), world map (`/api/locations/{sid}`), factions HQ (`/api/factions/{sid}/...`), and Smartphone/PeerPulse (`/api/phone/{sid}/...`).
- `api/inventory_merchant.py`: Inventory inspector (`vs_equipped` deltas, `[GEAR_JSON]` stripping, Key Item drop protection) & merchant shop/haggle.
- `api/auth_characters.py`: Guest & Discord ID auth, character creation, starter gear regeneration, switching, and deletion.
- `api/settings_ws.py` & `api/deps.py`: User settings, WebSocket endpoint, and `ConnectionManager`.
- **Serialization Rule**: Always convert `CheckResult` objects via `server._serializable_action()` before returning JSON or calling `ws.send_json()`.

### Discord Parity (`cogs/`)
- `cogs/adventure/cog.py` composes `game_loop_mixin.py`, `merchant_mixin.py`, `faction_mixin.py`, `embeds.py`, and interactive `discord.ui.View` classes in `cogs/adventure/views/` (`loadout.py`, `locations.py`, `quests.py`, etc.), alongside `cogs/{character,contacts,factions,inventory,settings,debug}.py`.
- When adding a new player-facing capability (e.g., bounty action, faction HQ perk, stealth toggle, phone feature), expose it cleanly through `TurnService` / `mechanics/` so both `api/` + `web/` and `cogs/` stay synchronized.

---

## 3. React SPA Structure, Styling & i18n (`web/`)

- **Views (`web/src/views/`)**: `AuthView.jsx`, `DashboardView.jsx`, `GameView.jsx`.
- **Key Components (`web/src/components/`)**:
  - `Sidebar/`: `TacticalActionDock.jsx`, `InventoryPanel.jsx`, `CodexPanel.jsx`, `QuestLogPanel.jsx`, `PartyWidget.jsx`, `WorldOutcomeSidebar.jsx`.
  - `ActionPanel/TurnOutcomePanel.jsx` & `StoryFeed/` (`StoryFeed.jsx`, `HistoryCard.jsx`).
  - `Modals/` (`WorldMapModal.jsx`, `TimeSkipModal.jsx`, etc.), `Phone/PhoneModal.jsx`, `Character/CharacterCreatorModal.jsx`, `Adventure/EmbarkationModal.jsx`.
- **Tailwind Theme (`web/tailwind.config.js`)**:
  - Surfaces & Borders: `bg-fantasy-dark` (`#0f0f13`), `bg-fantasy-panel` (`#1a1a24`), `border-fantasy-border` (`#2d2d3f`).
  - Accents & Vitals: `text-fantasy-accent` (`#c9a25e`), `hover:text-fantasy-accent-hover` (`#e3b86b`), `health` (`#e53935`), `mana` (`#1e88e5`), `stamina` (`#43a047`).
  - Fonts & Icons: `font-rpg` (`Cinzel`), `font-sans` (`Inter`), icons from `lucide-react`.
- **5-Locale Sync**: Add every new UI string via `useTranslation()` (`react-i18next`) across all 5 files in `web/src/locales/{en,pl,ms,de,zh}.json`.

---

## 4. Build, Dev & Browser Verification

- **Dev Mode**: Run `python server.py` (port `8000`) + `cd web && npm run dev` (Vite port `5173`, proxying `/api` and `/ws` to `8000`).
- **Standalone Production Sync**: `server.py` serves compiled static files from `web/dist`. **Always run `cd web && npm run build`** after modifying `web/src/` so standalone `run_web.bat` reflects your UI changes!
- **Verification**:
  - API parity tests: `pytest tests/test_web_api.py tests/test_codebase_contracts.py -q`
  - Live DOM/CSS/network inspection: Use the `chrome-devtools-mcp` tools (`navigate_page`, `take_snapshot`, `get_css_styles`, `list_console_messages`, `list_network_requests`).
