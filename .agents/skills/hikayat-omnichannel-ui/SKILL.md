---
name: hikayat-omnichannel-ui
description: "Use this skill whenever developing, styling, or debugging Hikayat's React 18 Web SPA (web/), FastAPI REST & WebSocket backend (server.py, api/), or Discord Bot UI parity (cogs/)."
---

# Hikayat Omnichannel UI (React SPA, FastAPI & Discord Parity)

Hikayat delivers **100% gameplay parity** across its React 18 Web SPA (`web/`) and Discord Bot (`cogs/`), both backed by headless `services/turn_service.py`.

---

## 1. Real HTTP + WebSocket Turn Protocol (`web/src/hooks/useGameSession.js`, `web/src/hooks/session/{useSessionSocket,useTurnTransport,useSceneImagePoll}.js`)

Do **not** send turn actions over WebSockets. Hikayat separates HTTP command submission (`useTurnTransport.js`) from WebSocket real-time streaming (`useSessionSocket.js`) and deferred image polling (`useSceneImagePoll.js`):

1. **Action Submission (HTTP POST)**:
   - `submitAction()` / `runTurnRequest()` (`useTurnTransport.js`) sends `POST /api/adventure/action` (240s client timeout via `web/src/api/client.js`) with `{ session_id, user_id, choice_index, custom_action_text, direct_choice, combat_target, intent, skip_minutes, sleep_mode, is_stealth, stance, action, async_ws }` guarded by `AbortController` and session-epoch checks so late responses never overwrite a switched session.
   - When the WebSocket is open, `async_ws: true` returns `202 Accepted` immediately and resolves via WebSocket events (`STREAM_THINKING`, `STREAM_START`, `STREAM_CHUNK`, `STREAM_END`, `STREAM_ERROR`, `TURN_CANCELLED`); REST callers omitting `async_ws` retain synchronous `200`/`503`/`500` semantics.
   - `cancelTurn()` calls `POST /api/adventure/cancel` to abort an in-flight background turn task and roll back partial turn state; `GET /api/adventure/active-session/{user_id}` attaches `in_flight_turn` metadata so page refreshes restore active processing/thinking state.
   - In multiplayer, if `data.status === "waiting_for_party"`, the UI sets `waitingForParty = true` until all party members lock picks.
   - On HTTP timeout/network error, `submitAction()` automatically recovers state via `GET /api/adventure/active-session/{user_id}`.
   - If `image_gen_enabled` is active and `scene_image_url` is not yet ready, `pollForSceneImage()` (`useSceneImagePoll.js`) polls `GET /api/adventure/session-image/{sessionId}`.

2. **Real-Time Server Push & Party Chat (`/ws/session/{sessionId}?user_id={userId}`)**:
   - **Client -> Server**: Only `{ type: "PING" }` (15s keepalive) and `{ type: "CHAT", sender, message }`. Auto-reconnects after 2s on close (`useSessionSocket.js`).
   - **Server -> Client Events**:
     - `STREAM_THINKING` / `STREAM_START` / `STREAM_CHUNK` (`field`: `"outcome_narrative"` or `"next_narrative"`) / `STREAM_END` / `STREAM_RESET` / `STREAM_ERROR` / `TURN_CANCELLED`
     - `NEW_SCENE` / `UPDATE_SCENE` / `PICK_LOCKED` / `SCENE_IMAGE`
     - `STEALTH_STATE_UPDATED` (`stealth_state`, `stealth_badge`)
     - `CHAT_MESSAGE` / `PRESENCE_UPDATE` / `HEARTBEAT`

---

## 2. FastAPI Routers (`server.py`, `api/`) & Discord Cogs (`cogs/`)

### FastAPI Backend (`api/`)
- `api/adventure/` (`routes_session.py`, `routes_turn.py`, `locations.py`): Session lifecycle (`/api/adventure/start`, `/join`, `/action`, `/end`, `/active-session/{uid}`, `/session-image/{sid}`).
- `api/codex_phone/` (`common.py`, `party.py`, `lorebook.py`, `contacts.py`, `factions.py`, `quests.py`, `phone.py`): Contacts dossier (`/api/contacts/{sid}`), lorebook & commitments (`/api/lorebook/{sid}`), quests/bounties/clue deduction (`/api/quests/{sid}/...`), factions HQ (`/api/factions/{sid}/...`), and Smartphone/PeerPulse (`/api/phone/{sid}/...`).
- `api/inventory_merchant.py`: Inventory inspector (`vs_equipped` deltas, `[GEAR_JSON]` stripping, Key Item drop protection) & merchant shop/haggle.
- `api/auth_characters.py`: Guest & Discord ID auth, character creation, starter gear regeneration, switching, and deletion.
- `api/settings_ws.py` & `api/deps.py`: User settings, debug sandbox (`GET/POST /api/debug/{uid}`, `/api/settings/debug/telemetry`), WebSocket endpoint, and `ConnectionManager`.
- **Auth & Scope Rule (`api/security.py`)**: Session-scoped routes must verify `verify_session_participant`, user-scoped routes must verify `verify_user_access`, and privileged/debug endpoints must gate on `is_strict_auth_context(request)` (never `is_share_mode_active()`). Keep handler docstrings as the **first** statement before auth checks. Audit routes with `python .agents/skills/hikayat-omnichannel-ui/scripts/audit_route_auth.py`.
- **Serialization Rule**: Always convert `CheckResult` objects via `api/deps.py` (`serializable_action()`; `server._serializable_action` compatibility alias) before returning JSON or calling `ws.send_json()`.

### Discord Parity (`cogs/`)
- `cogs/adventure/cog.py` composes `game_loop_mixin.py`, `merchant_mixin.py`, `faction_mixin.py`, `cogs/adventure/embeds/`, and interactive `discord.ui.View` classes in `cogs/adventure/views/` (`loadout.py`, `locations.py`, `quests.py`, etc.), alongside `cogs/{character,contacts,factions,inventory,settings,debug}.py`.
- When adding a new player-facing capability (e.g., bounty action, faction HQ perk, stealth toggle, phone feature), expose it cleanly through `TurnService` / `mechanics/` so both `api/` + `web/` and `cogs/` stay synchronized.

---

## 3. React SPA Structure, Styling & i18n (`web/`)

- **Views (`web/src/views/`)**: `AuthView.jsx`, `DashboardView.jsx`, `GameView.jsx` (decomposed with `GameViewModals.jsx`, `GameLeftDrawerContent.jsx`, `GameTopLeftControls.jsx`).
- **Key Components (`web/src/components/`)** — representative, not exhaustive; list the directory for the current set:
  - `Sidebar/`: `TacticalActionDock.jsx`, `InventoryPanel.jsx`, `CodexPanel.jsx` (`Codex{Characters,Factions,Agenda,Lore}Tab.jsx`), `ContactsPanel.jsx` (`NpcDossierBody.jsx`), `QuestLogPanel.jsx`, `PartyWidget.jsx`, `WorldOutcomeSidebar.jsx`.
  - `ActionPanel/ActionPanel.jsx` & `StoryFeed/` (`StoryFeed.jsx`, `HistoryCard.jsx`).
  - `Modals/` (`WorldMapModal.jsx`, `TimeSkipModal.jsx`, etc.), `Phone/PhoneModal.jsx` (`usePhone{Social,Commerce}Controllers.js`, `PhonePhotoLightbox.jsx`), `Character/CharacterCreatorModal.jsx`, `Adventure/EmbarkationModal.jsx`.
  - **Shared UI Hooks**: `web/src/hooks/useEscapeLayer.js` for LIFO Escape dismissal on modals/lightboxes.
- **Tailwind Theme (`web/tailwind.config.js`)** — values below are a snapshot; confirm in the config before relying on exact hex codes:
  - Surfaces & Borders: `bg-fantasy-dark` (`#0f0f13`), `bg-fantasy-panel` (`#1a1a24`), `border-fantasy-border` (`#2d2d3f`).
  - Accents & Vitals: `text-fantasy-accent` (`#c9a25e`), `hover:text-fantasy-accent-hover` (`#e3b86b`), `health` (`#e53935`), `mana` (`#1e88e5`), `stamina` (`#43a047`).
  - Fonts & Icons: `font-rpg` (`Cinzel`), `font-sans` (`Inter`), icons from `lucide-react`.
- **5-Locale Sync**: Add every new UI string via `useTranslation()` (`react-i18next`) across all 5 files in `web/src/locales/{en,pl,ms,de,zh}.json`.

---

## 4. Build, Dev & Browser Verification

- **Dev Mode**: Run `python server.py` (port `8000`) + `cd web && npm run dev` (Vite port `5173`, proxying `/api` and `/ws` to `8000`).
- **Standalone Production Sync**: `server.py` serves compiled static files from `web/dist`. **Always run `cd web && npm run lint && npm run build`** after modifying `web/src/` and include rebuilt `web/dist/` so standalone `run_web.bat` reflects your UI changes!
- **Verification**:
  - Route auth & API parity checks:
    ```bash
    python .agents/skills/hikayat-omnichannel-ui/scripts/audit_route_auth.py
    python scripts/run_tests.py agent tests/test_web_api.py tests/test_codebase_contracts.py
    ```
  - Live DOM/CSS/network inspection: Use the `chrome-devtools-mcp` tools (`navigate_page`, `take_snapshot`, `get_css_styles`, `list_console_messages`, `list_network_requests`).

---

## 5. Common Mistakes & Red Flags
- **Missing route/debug auth**: Adding `{session_id}` routes without `verify_session_participant` or gating debug endpoints on `is_share_mode_active()` instead of `is_strict_auth_context(request)`.
- **Displaced handler docstrings**: Placing `await verify_user_access(...)` *before* a FastAPI handler's triple-quoted docstring turns `handler.__doc__` into `None`.
- **`window.location.reload()` or stale races in React**: Never reload the browser in `ActionPanel.jsx` / views; use state updates + `useTurnTransport.js` / `useAuth.js` abort + epoch guards.
- **Skipping `useEscapeLayer.js`**: Building new modals with raw `keydown` listeners instead of `useEscapeLayer.js` breaks stacked Escape dismissal.
- **Forgetting `web/dist/` sync**: Editing `web/src/` without `npm run lint && npm run build` leaves `server.py` serving stale frontend bundles.
