#!/usr/bin/env python3
"""
CLI runner for the Hikayat Stealth & Infiltration Simulator.

Usage Examples:
    python scripts/simulate_stealth.py --count 50 --scenario all
    python scripts/simulate_stealth.py --profile ghost --mission heist --verbose
    python scripts/simulate_stealth.py --seed 7253080 --scenario cyberpunk --profile heavy --verbose
    python scripts/simulate_stealth.py --count 100 --json-report stealth_report.json
"""
import argparse
import json
import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
from tests.simulators.stealth import (
    StealthSimulator,
    SUPPORTED_PROFILES
)


def safe_print(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            sys.stdout.buffer.write((str(msg) + "\n").encode("utf-8", errors="replace"))
            sys.stdout.buffer.flush()
        except Exception:
            print(str(msg).encode("ascii", errors="replace").decode("ascii"), flush=True)


def main():
    parser = argparse.ArgumentParser(description="Hikayat Stealth & Infiltration Simulator Harness")
    parser.add_argument("--count", "--missions", "--simulations", "--journeys", "-n", type=int, default=50, dest="count", help="Number of missions to simulate (default: 50)")
    parser.add_argument("--scenario", "-s", type=str, default="all", help="Scenario to simulate ('all' or scenario key)")
    parser.add_argument("--profile", "-p", type=str, default="all", help=f"Agent profile ('all' or one of {', '.join(SUPPORTED_PROFILES)})")
    parser.add_argument("--mission", "-m", type=str, default="all", choices=["all", "heist", "evasion", "silent_takedown"], help="Mission archetype")
    parser.add_argument("--party-range", type=int, nargs=2, default=[1, 3], metavar=("MIN", "MAX"), help="Party size range (default: 1 3)")
    parser.add_argument("--party-size", type=int, default=None, help="Explicit party size when running single seed")
    parser.add_argument("--seed", type=int, default=None, help="Deterministic random seed to reproduce a run")
    parser.add_argument("--fail-fast", action="store_true", help="Halt execution on first invariant violation or crash")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print turn-by-turn trace logs")
    parser.add_argument("--json-report", type=str, default=None, help="Path to write JSON telemetry report")
    parser.add_argument("--keep-db", action="store_true", help="Preserve the simulation database after execution")
    parser.add_argument("--db-path", type=str, default=None, help="Explicit database path (defaults to isolated temp DB)")
    parser.add_argument("--live-db", action="store_true", help="Run against production database (NOT recommended)")

    args = parser.parse_args()

    if args.live_db:
        safe_print("\n⚠️  [WARNING] Running simulation directly against LIVE database!\n")
        sim_db_path = db.DB_PATH
        is_temp = False
    else:
        sim_db_path, is_temp = db.isolate_simulation_db(explicit_path=args.db_path)
        safe_print(f"🔒 [DB Isolation] Active isolated simulation database: {sim_db_path}")

    has_failures = False
    try:
        simulator = StealthSimulator()

        # Single deterministic mission mode
        if args.seed is not None and (args.count == 1 or args.party_size is not None):
            scen = "cyberpunk" if args.scenario == "all" else args.scenario
            prof = "ghost" if args.profile == "all" else args.profile
            m_type = "heist" if args.mission == "all" else args.mission
            p_size = args.party_size or args.party_range[0]

            safe_print(f"Executing Single Deterministic Stealth Mission with Seed {args.seed}...")
            res = simulator.run_mission(
                mission_id=1,
                scenario=scen,
                mission_type=m_type,
                profile=prof,
                party_size=p_size,
                seed=args.seed,
                verbose=True,
                fail_fast=args.fail_fast
            )

            safe_print("\n" + "=" * 60)
            status_str = "CLEAN INFILTRATION" if res.success and not res.detected else ("DETECTED / COMBAT" if res.detected else "FAILED")
            safe_print(f" OUTCOME: {status_str} | Turns: {res.total_turns} | Final Meter: {res.final_meter}% ({res.final_stage})")
            if res.combat_triggered:
                safe_print(f" COMBAT HANDOFF: {res.combat_outcome}")
            if res.violations:
                safe_print(f" VIOLATIONS DETECTED ({len(res.violations)}):")
                for v in res.violations:
                    safe_print(f"   ⚠️  [{v.category}] {v.message}")
            else:
                safe_print(" 🎉 ZERO INVARIANT VIOLATIONS DETECTED!")
            safe_print("=" * 60)

            if args.json_report:
                with open(args.json_report, "w", encoding="utf-8") as f:
                    json.dump({
                        "mission_id": res.mission_id,
                        "seed": res.seed,
                        "scenario": res.scenario,
                        "profile": res.profile,
                        "success": res.success,
                        "detected": res.detected,
                        "combat_outcome": res.combat_outcome,
                        "violations": [{"category": v.category, "message": v.message} for v in res.violations],
                        "trace_log": res.trace_log
                    }, f, indent=2, default=str)
                safe_print(f"Exported single-mission telemetry to {args.json_report}")

            has_failures = bool(res.violations or res.error)
            sys.exit(1 if has_failures else 0)

        # Batch simulation mode
        safe_print(f"Starting Stealth Infiltration Simulation ({args.count} missions, scenario: {args.scenario}, profile: {args.profile})...\n")
        report = simulator.run_batch(
            count=args.count,
            scenario=args.scenario,
            profile=args.profile,
            mission_type=args.mission,
            party_range=tuple(args.party_range),
            fail_fast=args.fail_fast,
            verbose=args.verbose
        )

        safe_print("\n" + report.format_summary())

        # If failing seeds occurred, dump automated reproduction reports
        if report.failing_seeds:
            os.makedirs("reports/failures", exist_ok=True)
            for fs in report.failing_seeds[:10]:
                failure_path = f"reports/failures/stealth_seed_{fs['seed']}.json"
                with open(failure_path, "w", encoding="utf-8") as f:
                    json.dump(fs, f, indent=2, default=str)
            safe_print(f"\nSaved {min(10, len(report.failing_seeds))} failure reproduction payloads to reports/failures/")

        if args.json_report:
            with open(args.json_report, "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, indent=2, default=str)
            safe_print(f"\nExported simulation report to {args.json_report}")

        has_failures = bool(report.crashes > 0 or report.violations_by_category)
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
