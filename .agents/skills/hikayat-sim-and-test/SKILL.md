---
name: hikayat-sim-and-test
description: "Use this skill whenever running pytest, reproducing bugs with seeds, running Hikayat's 6 deterministic fuzz simulators (combat, narrative, navigation, social, stealth, intimacy), checking AST/codebase contracts, or packaging clean releases."
---

# Hikayat Testing, Fuzz Simulation & Release Verification Runbook

Hikayat contains 130+ test modules and 6 deterministic fuzzing simulators. Always pick the fastest targeted runner below rather than running the entire test suite blindly. All of `tests/`, `pytest.ini`, `scripts/run_tests.py`, `scripts/simulate_*.py`, and `.desloppify/` are **local-only (gitignored)**: run them via `venv/Scripts/python.exe` (Windows) or `venv/bin/python` (POSIX), and never `git add -f` or commit them.

---

## 1. Static Bug Gate & Strict Mode (`scripts/static_check.py`, `tests/strict_mode.py`)

- **After any Python edit**: Run `python scripts/static_check.py --changed` (fast changed-file gate). Run `python scripts/static_check.py` for the full codebase or `python scripts/static_check.py tests/test_codebase_contracts.py` (or `--include-tests`) for explicit test validation. Keep `scripts/static_baseline.json` at `0` baselined findings.
- **Strict mode is enabled by default** (`HIKAYAT_STRICT=1`): Any test whose code path swallows `NameError`, `UnboundLocalError`, or an internal `ImportError` inside `except` fails immediately (`HIKAYAT_STRICT=2` also catches `TypeError` and `AttributeError`; `HIKAYAT_STRICT=0` disables only for diagnostics).

---

## 2. Accelerated Pytest Runner (`scripts/run_tests.py`)

Prefer these presets to keep execution fast and context output minimal (`agent` buffers stdout until exit, so use it for targeted files; use `full` for streaming parallel progress across `-n auto` workers):

| Goal | Command | Behavior |
| :--- | :--- | :--- |
| **Tight AI Edit Loop** | `python scripts/run_tests.py agent [path/to/test.py]` | `-q --tb=short --maxfail=1 --no-header` (< 200 tokens, buffered until exit) |
| **Fast Unit + Contracts** | `python scripts/run_tests.py quick` | Runs `-m "unit or contract"` |
| **Bytecode Impact Only** | `python scripts/run_tests.py impact` | Runs only tests affected by modified code (`--testmon`) |
| **Git Uncommitted Files** | `python scripts/run_tests.py changed` | Runs tests linked to uncommitted git changes (`--picked`) |
| **Re-run Last Failed** | `python scripts/run_tests.py failed` | `--lf -x -q --tb=short` |
| **Full Parallel CI Gate** | `python scripts/run_tests.py full` | `-n auto --dist=loadscope` with worker DB isolation & live output |

### Mandatory Contract & Cutover Checks After Structural Edits
```bash
python scripts/run_tests.py agent tests/test_codebase_contracts.py tests/test_five_normalized_models_cutover.py
python scripts/run_tests.py agent tests/test_agent_docs_contracts.py   # after editing AGENTS.md or .agents/
```

---

## 3. Deterministic CLI Fuzz Simulators (`scripts/simulate_*.py`)

All 6 simulators automatically create an isolated temporary SQLite DB via `db.isolate_simulation_db()` (never pass `--live-db` unless explicitly requested) and support `--seed <INT>` for exact deterministic replay of any failure:

1. **Tactical Combat Simulator** (`tests/simulators/combat/`):
   ```bash
   python scripts/simulate_combat.py --battles 50 --scenario all --fail-fast
   python scripts/simulate_combat.py --seed 7253080 --scenario fantasy --level 5 --verbose
   ```
2. **Narrative, Intent, Choices & Memory Simulator** (`tests/simulators/narrative/`):
   - Modes: `turn` (multi-turn loop), `intent` (NLU benchmark), `choices` (DC/diversity), `memory-stress` (long-campaign compaction & quest retention).
   ```bash
   python scripts/simulate_narrative.py --mode intent --samples 150 --fuzz adversarial_stress
   python scripts/simulate_narrative.py --mode choices --scenario fantasy
   python scripts/simulate_narrative.py --mode memory-stress --turns 40
   ```
3. **World Navigation & Spatial Graph Simulator** (`tests/simulators/world/`):
   ```bash
   python scripts/simulate_navigation.py --journeys 50 --scenario all --fuzz stress
   python scripts/simulate_navigation.py --seed 42091 --scenario high_school_drama --verbose
   ```
4. **Social Dynamics & Persona Simulator** (`tests/simulators/social/`):
   ```bash
   python scripts/simulate_social.py --simulations 20 --scenario all --fuzz adversarial_stress
   python scripts/simulate_social.py --seed 42091 --scenario high_school_drama --archetype romance_seeker --verbose
   ```
5. **Stealth & Infiltration Simulator** (`tests/simulators/stealth/`):
   ```bash
   python scripts/simulate_stealth.py --count 50 --scenario all
   python scripts/simulate_stealth.py --profile ghost --mission heist --verbose
   ```
6. **Intimacy & Excitement Meter Simulator** (`tests/simulators/intimacy/`):
   ```bash
   python scripts/simulate_intimacy.py --simulations 20 --scenario all --fuzz adversarial_stress
   ```

---

## 4. Writing New Tests Safely

- **Isolate SQLite Paths**: Always isolate tests with `db.use_temporary_db()` or `db.set_db_path(test_db)` (which clears pooled connections and updates `db.DB_PATH`, `db.core.DB_PATH`, and `config.DB_PATH` atomically) before calling `db.init_db()`:
  ```python
  test_db = str(tmp_path / "test_feature.db")
  with db.use_temporary_db(test_db):
      db.init_db()
      ...
  ```
  (If patching via `monkeypatch`, redirect both `db.DB_PATH` and `db.core.DB_PATH` and restore on teardown.)
- **Mock External LLM / Image Calls**: Patch `llm_client` / `TurnService.resolve_action` with `unittest.mock.AsyncMock` or `MagicMock` so unit/integration tests remain fast, offline, and deterministic.
- **Apply Pytest Markers** (`pytest.ini`): Tag new tests with `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.api`, `@pytest.mark.contract`, or `@pytest.mark.slow`.

---

## 5. Pre-Release Packaging Gate

Before cutting a release or committing broad workspace changes, run the release packager dry-run to verify zero personal path leaks and clean archive exclusions:
```bash
python scripts/package_release.py --dry-run
```

---

## 6. Common Mistakes & Red Flags
- **Widening `except` blocks instead of fixing bugs**: Swallowing `NameError` or `UnboundLocalError` fails `HIKAYAT_STRICT=1`; fix the root cause rather than silencing the exception.
- **Partial `DB_PATH` patching**: Mutating `db.DB_PATH` alone leaves pooled connections in `db/core/connection.py` pointing at live `hikayat.db`; always use `db.use_temporary_db()` or `db.set_db_path(...)`.
- **Unseeded RNG in combat/stealth tests**: Leaving random rolls unseeded causes intermittent one-shot/crit flakes during parallel `run_tests.py full` runs.
- **Git-adding local-only files or PowerShell `python -c` multi-line scripts**: Never `git add -f` `tests/`, `scripts/run_tests.py`, `scripts/simulate_*.py`, or `.desloppify/`; write multi-line Python helpers to scratch `.py` files instead of inline PowerShell `-c` strings.
