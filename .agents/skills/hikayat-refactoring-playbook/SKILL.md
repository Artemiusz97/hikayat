---
name: hikayat-refactoring-playbook
description: "Use this skill whenever splitting or refactoring large Python modules (>800-1,500 lines), converting single files into packages (__init__.py), decomposing large React views/modals/hooks in web/src/, or untangling cross-layer imports in Hikayat."
---

# Hikayat Module Decomposition & Layer-Inversion Playbook

Follow this runbook whenever decomposing large logic modules (`~800–1,500+` lines) or lifting cross-layer dependencies across Python and React.

---

## 1. Pre-Split Invariants
- **Keep splits schema-, API-, and locale-neutral**: Separate pure structural splits from feature changes, REST schema tweaks, or i18n key edits so behavior remains 100% invariant.
- **Decompose by lifecycle role**: Split around cohesive domain boundaries (`constants.py`, `repository.py`, `resolver.py`, `formatting.py`, or UI subcomponents/hooks) rather than arbitrary byte caps or `from ... import *`.
- **Enforce 4-layer dependency direction** (`tests/test_codebase_contracts.py`):
  - Layer 3 `db/` must **never** import `services/`, `api/`, or `cogs/`.
  - Layer 2 `mechanics/` must **never** add new imports of delivery frameworks (`discord`, `fastapi`, `cogs`, `api`).

---

## 2. Python File -> Package (`__init__.py`) Split Rules
1. **Facade & Submodule Re-Exports**:
   - Re-export every public symbol AND every test/caller-imported `_` private helper at the package root (`db/__init__.py`, `game_engine/__init__.py`, `llm_client/__init__.py`, or router facades like `api/codex_phone/__init__.py` exporting `codex_phone_router` for `server.py`).
   - Run `python scripts/run_tests.py agent tests/test_codebase_contracts.py` right after splitting so any broken `db.*`, `game_engine.*`, `llm_client.*`, or `self.cog.*` call resolves immediately.
2. **Live Mutable Proxy Forwarding**:
   - Whenever submodules read mutable globals (such as `llm_client._http_client`, `llm_client._embed_http_client`, `llm_client._nsfw_http_client`, or `db.DB_PATH`), install `db/core/module_proxy.py` (`install_submodule_proxy`) or accessor syncing so monkeypatching package globals in `tests/conftest.py` propagates live (`test_module_proxies_preserve_submodule_bindings_on_patch_and_delattr`).
3. **Direct Submodule Coverage Contracts**:
   - Add targeted import and callable checks for newly created submodules in `tests/test_submodule_direct_contracts.py` so static health analyzers that do not expand `__init__.py` barrels still observe direct submodule coverage.

---

## 3. React View, Modal & Hook Splits (`web/src/`)
- **Follow Established Decomposition Patterns**:
  - Hooks: `web/src/hooks/useGameSession.js` -> `web/src/hooks/session/{useSessionSocket,useTurnTransport,useSceneImagePoll}.js`.
  - Views: `web/src/views/GameView.jsx` -> `GameViewModals.jsx`, `GameLeftDrawerContent.jsx`, `GameTopLeftControls.jsx`.
  - Feature Panels/Modals: `CodexPanel.jsx` -> `Codex{Characters,Factions,Agenda,Lore}Tab.jsx`; `PhoneModal.jsx` -> `usePhone{Social,Commerce}Controllers.js`, `PhonePhotoLightbox.jsx`.
- **Preserve UX & Contract Tests**:
  - Wire new overlay modals through `web/src/hooks/useEscapeLayer.js` for deterministic LIFO Escape dismissal.
  - Run source-scanning UI contract suites (`tests/test_ui_audit_contracts.py`, `tests/test_special_actions_overhaul.py`) after moving JSX markup between files.
  - Always rebuild `web/dist/` via `cd web && npm run lint && npm run build` and include the rebuilt assets in the commit.

---

## 4. Inverting Upward Layer Imports
- **Lift orchestration to `services/`**: Move cross-layer flows out of `db/` into service modules (e.g., `services/anomalous_containment_service.py`).
- **Break `db/` -> `services/` rollback hooks cleanly**: Register callbacks at **module level** via `db.register_session_rollback_hook` (e.g. `services/examine_service.py`) rather than importing `services/` inside `db/`.
- **Never insert hook registration inside or above a function's docstring/body**: Keep module-level registration completely outside `def ...` blocks so functions cannot accidentally become no-ops.

---

## 5. Verification & Common Mistakes
Before splitting any file, generate its inbound caller & re-export manifest (or scan repo-wide large logic modules and layer boundaries):
```bash
python .agents/skills/hikayat-refactoring-playbook/scripts/audit_module_boundaries.py
python scripts/static_check.py
python scripts/run_tests.py agent tests/test_codebase_contracts.py tests/test_agent_docs_contracts.py tests/test_submodule_direct_contracts.py
python scripts/package_release.py --dry-run
```
- **Common Mistakes**: Dropping `_`-prefixed helpers when creating a `__init__.py` barrel; replacing live proxy attributes with value copies from `from .sub import _http_client`; forgetting `npm run build` in `web/` after JSX extraction; leaving stale paths in `.agents/` skill docs.
