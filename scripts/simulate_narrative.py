#!/usr/bin/env python3
"""
CLI Runner for the Hikayat Narrative & Turn Lifecycle Simulator.

Supports 4 execution modes:
1. --mode turn (Default): End-to-end multi-turn journey simulation through the turn loop.
2. --mode intent: Fast NLU benchmark testing intent and target extraction across fuzzed inputs.
3. --mode choices: Evaluates procedural choice generation, diversity, and DC math scaling.
4. --mode memory-stress: Multi-turn stress test for prompt cache headers and quest preservation.

Usage Examples:
    python scripts/simulate_narrative.py --mode turn --simulations 10 --scenario high_school_drama --verbose
    python scripts/simulate_narrative.py --mode intent --samples 150 --fuzz adversarial_stress
    python scripts/simulate_narrative.py --mode choices --scenario fantasy
    python scripts/simulate_narrative.py --mode memory-stress --turns 40
    python scripts/simulate_narrative.py --simulations 20 --scenario all --json-report narrative_report.json
"""
import argparse
import json
import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
from tests.simulators.narrative import (
    NarrativeSimulator,
    NarrativeSimulationReport,
    SUPPORTED_ARCHETYPES,
)

SUPPORTED_SCENARIOS = [
    "high_school_drama",
    "fantasy",
    "cyberpunk",
    "postapoc",
    "scifi",
    "steampunk",
    "dark_fantasy",
    "isekai_fantasy",
]


def safe_print(text: str = ""):
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"), flush=True)


def format_report_summary(report: NarrativeSimulationReport) -> str:
    lines = [
        "=" * 65,
        "         NARRATIVE & TURN LIFECYCLE SIMULATION REPORT            ",
        "=" * 65,
        f" Total Journeys Simulated        : {report.total_journeys}",
        f" Completed / Invariant-Clean     : {report.successful_journeys} ({(report.successful_journeys / max(1, report.total_journeys)) * 100:.1f}%)",
        f" Crashes / Uncaught Exceptions   : {report.crashes}",
        f" Total Turns Executed            : {report.total_turns}",
        f" Total Invariant Violations      : {report.total_violations} ({report.critical_violations} Critical, {report.warning_violations} Advisory Warnings)",
        f" Total Simulation Time           : {report.duration_ms:.1f} ms",
        "-" * 65,
        " ARCHETYPE BREAKDOWN:",
    ]

    for arch, stats in report.archetype_stats.items():
        total = stats["journeys"]
        succ = stats["successful"]
        lines.append(f"   • {arch.upper():<20} | Journeys: {total:<3} | Clean: {succ:<3}")

    lines.append("-" * 65)
    lines.append(" SCENARIO BREAKDOWN:")
    for scen, stats in report.scenario_stats.items():
        total = stats["journeys"]
        succ = stats["successful"]
        lines.append(f"   • {scen:<20} | Journeys: {total:<3} | Clean: {succ:<3} | Violations: {stats['violations']}")

    if report.violations_by_category:
        lines.append("-" * 65)
        lines.append(" VIOLATIONS BY CATEGORY:")
        for cat, count in sorted(report.violations_by_category.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"   [!] {cat:<26} : {count}")

    lines.append("=" * 65)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Hikayat Narrative & Turn Lifecycle Simulator")
    parser.add_argument(
        "--mode", "-m",
        type=str,
        default="turn",
        choices=["turn", "intent", "choices", "memory-stress"],
        help="Execution mode (default: turn)",
    )
    parser.add_argument("--simulations", "-n", type=int, default=10, help="Number of simulated journeys (default: 10)")
    parser.add_argument(
        "--scenario", "-s",
        type=str,
        default="all",
        help=f"Scenario to simulate ('all' or one of {', '.join(SUPPORTED_SCENARIOS)})",
    )
    parser.add_argument(
        "--archetype", "-a",
        type=str,
        default="all",
        help=f"Player archetype ('all' or one of {', '.join(SUPPORTED_ARCHETYPES)})",
    )
    parser.add_argument(
        "--fuzz", "-f",
        type=str,
        default="clean",
        choices=["clean", "realistic_llm", "adversarial_stress"],
        help="Fuzzing perturbation level (default: clean)",
    )
    parser.add_argument("--turns", "-t", type=int, default=10, help="Max turns per journey (default: 10)")
    parser.add_argument("--samples", type=int, default=100, help="Number of samples for intent mode (default: 100)")
    parser.add_argument("--seed", type=int, default=None, help="Deterministic random seed")
    parser.add_argument("--fail-fast", action="store_true", help="Halt immediately upon first critical violation")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print per-journey telemetry")
    parser.add_argument("--json-report", type=str, default=None, help="Path to write JSON telemetry report")
    parser.add_argument("--with-llm", action="store_true", help="Enable live LLM sampling for turns")
    parser.add_argument("--keep-db", action="store_true", help="Preserve the simulation database after execution")
    parser.add_argument("--db-path", type=str, default=None, help="Explicit database path (defaults to isolated temp DB)")
    parser.add_argument("--live-db", action="store_true", help="Run against production database (NOT recommended)")

    args = parser.parse_args()

    if args.with_llm:
        os.environ.setdefault("LLM_VERIFY_SSL", "false")

    if args.live_db:
        safe_print("\n⚠️  [WARNING] Running simulation directly against LIVE database!\n")
        sim_db_path = db.DB_PATH
        is_temp = False
    else:
        sim_db_path, is_temp = db.isolate_simulation_db(explicit_path=args.db_path)
        safe_print(f"🔒 [DB Isolation] Active isolated simulation database: {sim_db_path}")

    has_failures = False
    try:
        simulator = NarrativeSimulator(seed=args.seed)

        # 1. Mode: Intent
        if args.mode == "intent":
            safe_print(f"Running NLU Intent Benchmark ({args.samples} samples, fuzz={args.fuzz})...")
            res = simulator.run_intent_mode(
                samples=args.samples,
                scenario=args.scenario if args.scenario != "all" else "high_school_drama",
                fuzz_mode=args.fuzz,
            )
            safe_print("\n" + "=" * 55)
            safe_print("           INTENT BENCHMARK REPORT               ")
            safe_print("=" * 55)
            safe_print(f" Total Samples Evaluated : {res['total_samples']}")
            safe_print(f" Passed Cleanly          : {res['passed']} ({res['pass_rate']:.1f}%)")
            safe_print(f" Failures / Target Leaks : {res['failed']}")
            safe_print(f" Total Execution Time    : {res['duration_ms']:.1f} ms")
            safe_print("=" * 55)
            if res["failures"]:
                safe_print("\nSample Failures:")
                for f in res["failures"][:5]:
                    safe_print(f"  • '{f['text']}' -> {f['error']}")
            if args.json_report:
                with open(args.json_report, "w", encoding="utf-8") as f:
                    json.dump(res, f, indent=2)
                safe_print(f"\nWrote JSON report to: {args.json_report}")
            has_failures = (res["failed"] > 0 and args.fuzz == "clean")

        # 2. Mode: Choices
        elif args.mode == "choices":
            safe_print("Running Procedural Choice & Deadlock Audit...")
            scenarios = [args.scenario] if args.scenario != "all" else None
            iterations = args.simulations if (args.simulations and args.simulations > 0) else 20
            res = simulator.run_choices_mode(scenarios=scenarios, iterations=iterations)
            safe_print("\n" + "=" * 55)
            safe_print("         CHOICE DIVERSITY AUDIT REPORT           ")
            safe_print("=" * 55)
            safe_print(f" Total Scenes Evaluated  : {res['total_evaluations']}")
            safe_print(f" Invariant Violations    : {res['violations']}")
            safe_print(f" Clean Scene Rate        : {res['clean_rate']:.1f}%")
            safe_print(f" Total Execution Time    : {res['duration_ms']:.1f} ms")
            safe_print("=" * 55)
            if args.json_report:
                with open(args.json_report, "w", encoding="utf-8") as f:
                    json.dump(res, f, indent=2)
                safe_print(f"\nWrote JSON report to: {args.json_report}")
            has_failures = (res["violations"] > 0)

        # 3. Mode: Memory Stress
        elif args.mode == "memory-stress":
            safe_print(f"Running Long-Horizon Memory & Compaction Stress ({args.turns} turns)...")
            res = simulator.run_memory_stress_mode(
                turns=args.turns,
                scenario=args.scenario if args.scenario != "all" else "high_school_drama",
            )
            safe_print("\n" + "=" * 55)
            safe_print("       LONG-HORIZON MEMORY STRESS REPORT         ")
            safe_print("=" * 55)
            safe_print(f" Turns Simulated         : {res['turns_simulated']}")
            safe_print(f" Active Quest Preserved  : {'YES' if res['active_quest_preserved'] else 'NO'}")
            safe_print(f" Invariant Violations    : {res['violations']}")
            safe_print(f" Total Execution Time    : {res['duration_ms']:.1f} ms")
            safe_print("=" * 55)
            if args.json_report:
                with open(args.json_report, "w", encoding="utf-8") as f:
                    json.dump(res, f, indent=2)
                safe_print(f"\nWrote JSON report to: {args.json_report}")
            has_failures = (res["violations"] > 0 or not res["active_quest_preserved"])

        # 4. Mode: Turn (Default)
        else:
            safe_print(
                f"Starting Narrative & Turn Simulator ({args.simulations} journeys, "
                f"scenario={args.scenario}, archetype={args.archetype}, fuzz={args.fuzz})..."
            )
            report = simulator.run_batch(
                simulations=args.simulations,
                scenario=args.scenario,
                archetype=args.archetype,
                fuzz_mode=args.fuzz,
                seed=args.seed,
                max_turns=args.turns,
                fail_fast=args.fail_fast,
                with_llm=args.with_llm,
            )

            if args.verbose:
                for res in report.results:
                    status = "PASS" if res.success else "FAIL"
                    safe_print(
                        f"\n[Journey #{res.journey_id:03d} | {res.scenario} | {res.archetype}] "
                        f"Status: {status} | Turns: {res.total_turns} | Intents: {res.intents_evaluated} | "
                        f"Choices: {res.choices_evaluated} | Reconciled: {res.entities_reconciled} | Time: {res.duration_ms:.1f}ms"
                    )
                    if res.history and (args.simulations <= 5 or args.seed is not None):
                        safe_print("    Turn-by-Turn Trace:")
                        for step in res.history:
                            safe_print(
                                f"      Turn {step['turn']:02d}: [{step['intent']:<16}] "
                                f"Partner: {str(step['partner']):<16} | Action: {step['action']}"
                            )
                    if res.violations:
                        for v in res.violations:
                            safe_print(f"    -> [{v.severity}] {v.category}: {v.message}")
                    if res.error:
                        safe_print(f"    -> [CRASH] {res.error}")

            safe_print("\n" + format_report_summary(report))

            if args.json_report:
                report_data = {
                    "total_journeys": report.total_journeys,
                    "successful_journeys": report.successful_journeys,
                    "crashes": report.crashes,
                    "total_turns": report.total_turns,
                    "avg_turns_per_journey": report.avg_turns_per_journey,
                    "total_violations": report.total_violations,
                    "violations_by_category": report.violations_by_category,
                    "archetype_stats": report.archetype_stats,
                    "scenario_stats": report.scenario_stats,
                    "duration_ms": report.duration_ms,
                    "results": [
                        {
                            "journey_id": r.journey_id,
                            "scenario": r.scenario,
                            "archetype": r.archetype,
                            "turns": r.total_turns,
                            "success": r.success,
                            "violations": [
                                {"category": v.category, "message": v.message, "severity": v.severity}
                                for v in r.violations
                            ],
                            "error": r.error,
                        }
                        for r in report.results
                    ],
                }
                with open(args.json_report, "w", encoding="utf-8") as f:
                    json.dump(report_data, f, indent=2)
                safe_print(f"\nWrote JSON report to: {args.json_report}")

            has_failures = bool(report.crashes > 0 or (args.fuzz == "clean" and report.total_violations > 0))

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
