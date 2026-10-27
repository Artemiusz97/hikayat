---
name: hikayat-sim-and-test
description: "Use this skill whenever running pytest, reproducing bugs with seeds, running Hikayat's 6 deterministic fuzz simulators (combat, narrative, navigation, social, stealth, intimacy), checking AST/codebase contracts, or packaging clean releases."
---

# Hikayat Testing, Fuzz Simulation & Release Verification Runbook

Hikayat contains 200+ test modules and 6 deterministic fuzzing simulators. Always pick the fastest targeted runner below rather than running the entire test suite blindly.

---

## 1. Accelerated Pytest Runner (`scripts/run_tests.py`)

Prefer these presets to keep execution fast and context output minimal:

| Goal | Command | Behavior |
| :--- | :--- | :--- |
| **Tight AI Edit Loop** | `python scripts/run_tests.py agent [path/to/test.py]` | `-q --tb=short --maxfail=1 --no-header` (< 200 tokens) |
| **Fast Unit + Contracts** | `python scripts/run_tests.py quick` | Runs `-m "unit or contract"` |
| **Bytecode Impact Only** | `python scripts/run_tests.py impact` | Runs only tests affected by modified code (`--testmon`) |
| **Git Uncommitted Files** | `python scripts/run_tests.py changed` | Runs tests linked to uncommitted git changes (`--picked`) |
| **Re-run Last Failed** | `python scripts/run_tests.py failed` | `--lf -x -q --tb=short` |
| **Full Parallel CI Gate** | `python scripts/run_tests.py full` | `-n auto --dist=loadscope` with worker DB isolation |

### Mandatory Contract & Cutover Checks After Structural Edits
```bash
pytest tests/test_codebase_contracts.py tests/test_five_normalized_models_cutover.py -q
```

---

## 2. Deterministic CLI Fuzz Simulators (`scripts/simulate_*.py`)

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

## 3. Writing New Tests Safely

- **Isolate SQLite Paths**: Always redirect **both** `db.DB_PATH` and `db.core.DB_PATH` before calling `db.init_db()`:
  ```python
  test_db = str(tmp_path / "test_feature.db")
  monkeypatch.setattr(db, "DB_PATH", test_db)
  monkeypatch.setattr(db.core, "DB_PATH", test_db)
  db.init_db()
  ```
- **Mock External LLM / Image Calls**: Patch `llm_client` / `TurnService.resolve_action` with `unittest.mock.AsyncMock` or `MagicMock` so unit/integration tests remain fast, offline, and deterministic.
- **Apply Pytest Markers** (`pytest.ini`): Tag new tests with `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.api`, `@pytest.mark.contract`, or `@pytest.mark.slow`.

---

## 4. Pre-Release Packaging Gate

Before cutting a release or committing broad workspace changes, run the release packager dry-run to verify zero personal path leaks and clean archive exclusions:
```bash
python scripts/package_release.py --dry-run
```
