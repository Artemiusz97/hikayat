#!/usr/bin/env python3
"""
CLI runner for the Hikayat Tactical Combat Simulator.

Usage Examples:
    python scripts/simulate_combat.py --battles 100 --scenario all
    python scripts/simulate_combat.py --battles 20 --scenario highschool --verbose
    python scripts/simulate_combat.py --seed 7253080 --scenario highschool --level 2 --verbose
    python scripts/simulate_combat.py --battles 500 --json-report sim_report.json
"""
import argparse
import json
import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
from tests.simulators.combat import CombatSimulator, safe_print, SUPPORTED_SCENARIOS


def main():
    parser = argparse.ArgumentParser(description="Hikayat Tactical Combat Simulator & Fuzzing Harness")
    parser.add_argument("--battles", "-n", type=int, default=100, help="Number of battles to simulate (default: 100)")
    parser.add_argument("--scenario", "-s", type=str, default="all", help=f"Scenario to test (default: 'all' or one of {', '.join(SUPPORTED_SCENARIOS)})")
    parser.add_argument("--level-range", type=int, nargs=2, default=[1, 15], metavar=("MIN", "MAX"), help="Character level range (default: 1 15)")
    parser.add_argument("--party-range", type=int, nargs=2, default=[1, 4], metavar=("MIN", "MAX"), help="Party size range (default: 1 4)")
    parser.add_argument("--level", "-l", type=int, default=None, help="Explicit level when simulating with --seed")
    parser.add_argument("--party-size", "-p", type=int, default=None, help="Explicit party size when simulating with --seed")
    parser.add_argument("--seed", type=int, default=None, help="Specific random seed to reproduce a single battle")
    parser.add_argument("--fail-fast", action="store_true", help="Halt execution on the first invariant violation or crash")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print turn-by-turn combat logs")
    parser.add_argument("--json-report", type=str, default=None, help="Path to write JSON telemetry report")
    parser.add_argument("--keep-db", action="store_true", help="Preserve the simulation database after execution")
    parser.add_argument("--db-path", type=str, default=None, help="Explicit database path to use (defaults to isolated temp DB)")
    parser.add_argument("--live-db", action="store_true", help="Run against production database (NOT recommended)")

    args = parser.parse_args()

    valid_scenarios = list(SUPPORTED_SCENARIOS) + ["all"]
    if args.scenario not in valid_scenarios:
        safe_print(f"Error: Invalid scenario '{args.scenario}'. Supported scenarios: {', '.join(valid_scenarios)}")
        sys.exit(1)

    if args.live_db:
        safe_print("\n⚠️  [WARNING] Running simulation directly against LIVE database!\n")
        sim_db_path = db.DB_PATH
        is_temp = False
    else:
        sim_db_path, is_temp = db.isolate_simulation_db(explicit_path=args.db_path)
        safe_print(f"🔒 [DB Isolation] Active isolated simulation database: {sim_db_path}")

    has_failures = False
    try:
        simulator = CombatSimulator()

        # Single deterministic battle mode
        if args.seed is not None and (args.battles == 1 or args.level is not None or args.party_size is not None):
            scen = "fantasy" if args.scenario == "all" else args.scenario
            lvl = args.level or args.level_range[0]
            p_size = args.party_size or args.party_range[0]

            safe_print(f"Executing Single Deterministic Battle with Seed {args.seed}...")
            res = simulator.run_battle(
                battle_id=1,
                scenario=scen,
                level=lvl,
                party_size=p_size,
                seed=args.seed,
                verbose=True
            )

            safe_print("\n" + "=" * 60)
            safe_print(f" OUTCOME: {res.outcome.upper()} | Turns: {res.turns_taken} | Player HP: {res.player_end_hp}/{res.player_start_hp}")
            if res.violations:
                safe_print(f" VIOLATIONS DETECTED ({len(res.violations)}):")
                for v in res.violations:
                    safe_print(f"   ⚠️  {v}")
            else:
                safe_print(" 🎉 ZERO INVARIANT VIOLATIONS DETECTED!")
            safe_print("=" * 60)

            if args.json_report:
                with open(args.json_report, "w", encoding="utf-8") as f:
                    json.dump({
                        "battle_id": res.battle_id,
                        "seed": res.seed,
                        "scenario": res.scenario,
                        "level": res.level,
                        "outcome": res.outcome,
                        "turns_taken": res.turns_taken,
                        "violations": res.violations,
                        "combat_log": res.combat_log
                    }, f, indent=2, default=str)
                safe_print(f"Exported single-battle telemetry to {args.json_report}")

            has_failures = bool(res.violations or res.outcome == "crash")
            sys.exit(1 if has_failures else 0)

        # Batch simulation mode
        scenarios_to_run = None if args.scenario == "all" else [args.scenario]
        safe_print(f"Starting Combat Simulation ({args.battles} battles, scenarios: {args.scenario}, levels: {args.level_range[0]}-{args.level_range[1]})...")

        report = simulator.run_batch(
            count=args.battles,
            scenarios=scenarios_to_run,
            level_range=(args.level_range[0], args.level_range[1]),
            party_range=(args.party_range[0], args.party_range[1]),
            fail_fast=args.fail_fast,
            verbose=args.verbose,
            seed=args.seed
        )

        safe_print("\n" + report.format_summary())

        if args.json_report:
            with open(args.json_report, "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, indent=2, default=str)
            safe_print(f"\nExported simulation report to {args.json_report}")

        has_failures = bool(report.crashes > 0 or report.violations_by_type)
        sys.exit(1 if has_failures else 0)
    except Exception:
        has_failures = True
        raise
    finally:
        if is_temp:
            if args.keep_db or has_failures:
                safe_print(f"💾 [DB Isolation] Preserving simulation database for inspection: {sim_db_path}")
            else:
                db.cleanup_simulation_db(sim_db_path, keep=False, is_temp=True)


if __name__ == "__main__":
    main()
