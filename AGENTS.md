# Hikayat Engineering Invariants

These architectural contracts apply to **every** code change in Hikayat and are statically verified by `tests/test_codebase_contracts.py` and `scripts/package_release.py`.

## 1. Module Exports & Size Ceilings
- **AST Call Resolution Contract**: Every `db.<fn>()`, `game_engine.<fn>()`, `llm_client.<fn>()`, and `self.cog.<fn>()` call across the repository **must** resolve to a real callable exported at the package root (`db/__init__.py`, `game_engine/__init__.py`, or `AdventureCog` mixins). Never add a function to `db/<submodule>.py` without re-exporting it in `db/__init__.py`.
- **60 KB Split-Module Cap**: `game_engine/core.py`, `cogs/adventure/cog.py`, and `mechanics/system/phone/messaging.py` **must stay strictly under 60 KB**. Place new logic in focused sub-modules or mixins and re-export cleanly.
- **Typing Imports**: Include `from __future__ import annotations` and explicit `typing` imports in Python modules so pytest collection never fails with `NameError`.

## 2. Serialization & Schema Contracts
- **`CheckResult` JSON Safety**: `skill_check.CheckResult` is a dataclass and fails raw `json.dumps()`. Always pass action dicts through `server._serializable_action()` before JSON or WebSocket serialization.
- **Pydantic Dual-Access & Coercion**: LLM schemas in `models/llm_schemas.py` (`TurnOutcome`, `OpeningScene`, `ActionClassification`, `Choice`) must support **both** attribute (`obj.field`) and dict (`obj["field"]`, `obj.get()`) access, and gracefully coerce empty strings `""` or `None` returned by local/open-weights models.

## 3. Database & Test Isolation
- **Never Mutate Live `hikayat.db` in Tests**: In pytest fixtures/tests, always redirect **both** `db.DB_PATH` and `db.core.DB_PATH` via `monkeypatch.setattr`, or call `db.isolate_simulation_db()` in simulators.
- **Async DB Wrapper**: Inside `async def` routes, cogs, and `TurnService`, run synchronous SQLite calls through `await adb(db.<fn>, ...)` and respect `distributed_session_lock` / `distributed_user_lock`.

## 4. Headless Omnichannel Parity & Prose Guardrails
- **Single Source of Truth**: Resolve game mechanics deterministically in `services/turn_service.py`, `game_engine/`, and `mechanics/`. Never fork core game rules exclusively inside Discord `cogs/` or FastAPI `api/`.
- **Zero Stat Leakage in Prose**: Raw HP/MP integers, dice percentages, DC numbers, and internal enum/JSON tags (`[ITEM_JSON]`, `[GEAR_JSON]`) must **never** leak into player-facing narrative prose.
- **Zero Personal Path Leaks**: Never hardcode machine-local user home paths or usernames in tracked files, comments, or skills. `scripts/package_release.py` scans all candidate text files and aborts on personal path tokens.
