#!/usr/bin/env python3
"""
CLI Runner for the Hikayat World Navigation & Waypoint Simulator.

Usage Examples:
    python scripts/simulate_navigation.py --journeys 50 --scenario all
    python scripts/simulate_navigation.py --journeys 20 --scenario high_school_drama --fuzz realistic --verbose
    python scripts/simulate_navigation.py --seed 42091 --scenario fantasy --verbose
    python scripts/simulate_navigation.py --journeys 100 --fuzz stress --json-report nav_report.json
"""
import argparse
import json
import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
from tests.simulators.world import (
    WorldNavigationSimulator,
    SimulationReport,
    JourneyResult,
)

SUPPORTED_SCENARIOS = [
    "fantasy",
    "high_school_drama",
    "cyberpunk",
    "postapoc",
    "scifi",
    "steampunk",
    "dark_fantasy",
    "isekai_fantasy",
]


def safe_print(text: str = ""):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"))


def format_report_summary(report: SimulationReport) -> str:
    lines = [
        "=" * 60,
        "         WORLD NAVIGATION & WAYPOINT SIMULATION REPORT          ",
        "=" * 60,
        f" Total Journeys Simulated : {report.total_journeys}",
        f" Completed Journeys       : {report.successful_journeys} ({(report.successful_journeys / max(1, report.total_journeys)) * 100:.1f}%)",
        f" Deadlocks / Stagnant     : {report.deadlocks}",
        f" Crashes / Uncaught Errs  : {report.crashes}",
        f" Total Turns Executed     : {report.total_turns}",
        f" Average Turns / Journey  : {report.avg_turns_per_journey:.2f}",
        f" Average Turns / Stage    : {report.avg_turns_per_stage:.2f}",
        f" Incongruous Auto-Heals   : {report.total_auto_heals}",
        f" Total Simulation Time    : {report.duration_ms:.1f} ms",
        "-" * 60,
        " SCENARIO BREAKDOWN:",
    ]

    for sc, stat in sorted(report.scenario_stats.items()):
        total_j = stat["journeys"]
        succ = stat["successes"]
        succ_pct = (succ / total_j * 100) if total_j else 0
        avg_t = (stat["turns"] / total_j) if total_j else 0
        lines.append(
            f"   * {sc:<18}: {total_j:>3} journeys | Complete: {succ_pct:>5.1f}% | Avg Turns: {avg_t:>4.1f} | Auto-heals: {stat['auto_heals']} | Crashes: {stat['crashes']}"
        )

    lines.append("-" * 60)
    lines.append(" INVARIANT VIOLATIONS & ANOMALIES:")

    if not report.violations_by_category:
        lines.append("   🎉 ZERO INVARIANT VIOLATIONS DETECTED!")
    else:
        for cat, cnt in sorted(report.violations_by_category.items(), key=lambda x: -x[1]):
            lines.append(f"   ⚠️  {cat:<30}: {cnt} occurrences")

    lines.append("=" * 60)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Hikayat World Navigation & Waypoint Simulator Harness")
    parser.add_argument("--journeys", "-n", type=int, default=50, help="Number of journeys to simulate (default: 50)")
    parser.add_argument(
        "--scenario", "-s", type=str, default="all",
        help=f"Scenario to test (default: 'all' or one of {', '.join(SUPPORTED_SCENARIOS)})"
    )
    parser.add_argument(
        "--fuzz", "-f", type=str, default="realistic", choices=["clean", "realistic", "stress", "all"],
        help="Fuzzing perturbation profile (clean, realistic, stress, all)"
    )
    parser.add_argument("--chaos", type=float, default=0.15, help="Navigator AI chaos/deviation probability (default: 0.15)")
    parser.add_argument("--max-turns", type=int, default=35, help="Maximum turns allowed per journey (default: 35)")
    parser.add_argument("--seed", type=int, default=None, help="Deterministic random seed to reproduce a run")
    parser.add_argument("--fail-fast", action="store_true", help="Halt simulation on the first invariant violation or crash")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print turn-by-turn path traversal logs")
    parser.add_argument("--json-report", type=str, default=None, help="Path to write JSON telemetry report")
    parser.add_argument("--with-llm", action="store_true", help="Enable optional live LLM sampling turns")
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
        simulator = WorldNavigationSimulator(seed=args.seed)

        # Single deterministic journey mode
        if args.seed is not None and args.journeys == 1:
            scen = "fantasy" if args.scenario == "all" else args.scenario
            safe_print(f"Executing Single Deterministic Journey with Seed {args.seed} in {scen}...")
            res = simulator.run_journey(
                scenario=scen,
                journey_id=1,
                seed=args.seed,
                fuzz_mode=args.fuzz,
                max_turns=args.max_turns,
                fail_fast=args.fail_fast,
                chaos_rate=args.chaos,
                with_llm=args.with_llm,
            )

            safe_print("\n" + "=" * 60)
            safe_print(f" OUTCOME: {'SUCCESS' if res.success else ('DEADLOCK' if res.deadlock else 'INCOMPLETE')}")
            safe_print(f" Turns: {res.total_turns} | Stages: {res.completed_stages}/{res.total_stages} | Auto-heals: {res.auto_heals}")
            safe_print(f" Path Traversed ({len(res.path_history)} steps):")
            for idx, step in enumerate(res.path_history, 1):
                safe_print(f"   [{idx:02d}] {step}")

            if res.violations:
                safe_print(f"\n VIOLATIONS DETECTED ({len(res.violations)}):")
                for v in res.violations:
                    safe_print(f"   ⚠️  Turn {v.turn}: [{v.category}] {v.message}")
            else:
                safe_print("\n 🎉 ZERO INVARIANT VIOLATIONS DETECTED!")
            safe_print("=" * 60)

            if args.json_report:
                with open(args.json_report, "w", encoding="utf-8") as f:
                    json.dump({
                        "journey_id": res.journey_id,
                        "seed": res.seed,
                        "scenario": res.scenario,
                        "success": res.success,
                        "deadlock": res.deadlock,
                        "total_turns": res.total_turns,
                        "completed_stages": res.completed_stages,
                        "total_stages": res.total_stages,
                        "auto_heals": res.auto_heals,
                        "path_history": res.path_history,
                        "violations": [v.__dict__ for v in res.violations],
                    }, f, indent=2, default=str)
                safe_print(f"Exported single-journey telemetry to {args.json_report}")

            has_failures = bool(res.violations or res.error or res.deadlock)
            sys.exit(1 if has_failures else 0)

        # Batch simulation mode
        safe_print(f"Starting World Navigation Simulation ({args.journeys} journeys, scenario: {args.scenario}, fuzz: {args.fuzz})...")

        report = simulator.run_batch(
            journeys=args.journeys,
            scenario=args.scenario,
            fuzz_mode=args.fuzz,
            fail_fast=args.fail_fast,
            seed=args.seed,
            chaos_rate=args.chaos,
            with_llm=args.with_llm,
        )

        safe_print("\n" + format_report_summary(report))

        if args.json_report:
            with open(args.json_report, "w", encoding="utf-8") as f:
                json.dump({
                    "total_journeys": report.total_journeys,
                    "successful_journeys": report.successful_journeys,
                    "deadlocks": report.deadlocks,
                    "crashes": report.crashes,
                    "total_turns": report.total_turns,
                    "avg_turns_per_journey": report.avg_turns_per_journey,
                    "avg_turns_per_stage": report.avg_turns_per_stage,
                    "total_auto_heals": report.total_auto_heals,
                    "total_violations": report.total_violations,
                    "scenario_stats": report.scenario_stats,
                    "violations_by_category": report.violations_by_category,
                    "duration_ms": report.duration_ms,
                }, f, indent=2, default=str)
            safe_print(f"\nExported simulation report to {args.json_report}")

        has_failures = bool(report.crashes > 0 or report.total_violations > 0)
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
