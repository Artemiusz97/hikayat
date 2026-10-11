#!/usr/bin/env python3
"""
CLI Runner for the Hikayat Social Dynamics & Persona Simulator.

Usage Examples:
    python scripts/simulate_social.py --simulations 20 --scenario all
    python scripts/simulate_social.py --simulations 10 --scenario high_school_drama --archetype romance_seeker --verbose
    python scripts/simulate_social.py --simulations 15 --archetype operative --fuzz realistic_llm
    python scripts/simulate_social.py --seed 42091 --scenario fantasy --archetype diplomat --verbose
    python scripts/simulate_social.py --simulations 25 --fuzz adversarial_stress --json-report social_report.json
"""
import argparse
import json
import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
from tests.simulators.social import (
    SocialDynamicsSimulator,
    SocialSimulationReport,
    SocialJourneyResult,
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


def format_report_summary(report: SocialSimulationReport) -> str:
    lines = [
        "=" * 65,
        "         SOCIAL DYNAMICS & PERSONA SIMULATION REPORT             ",
        "=" * 65,
        f" Total Journeys Simulated        : {report.total_journeys}",
        f" Completed / Invariant-Clean     : {report.successful_journeys} ({(report.successful_journeys / max(1, report.total_journeys)) * 100:.1f}%)",
        f" Crashes / Uncaught Exceptions   : {report.crashes}",
        f" Total Turns Executed            : {report.total_turns}",
        f" Average Turns / Journey         : {report.avg_turns_per_journey:.2f}",
        f" Hidden Traits Unlocked          : {report.total_traits_unlocked}",
        f" Confessions Accepted (Milestone): {report.total_confessions_accepted}",
        f" Confessions Rejected (Cooldown) : {report.total_confessions_rejected}",
        f" Illegal Advances Prevented      : {report.total_illegal_advances_prevented}",
        f" Intimate Milestones Unlocked  : {report.total_intimate_milestones}",
        f" Anal Intimacy Acts Simulated   : {report.total_anal_acts}",
        f" Sensitive Spots Discovered     : {report.total_sensitive_spots}",
        f" Turn-Off Aversions Verified    : {report.total_turn_offs}",
        f" Phone Interactions Simulated    : {report.total_phone_interactions}",
        f" Spicy Media Consents Gated      : {report.total_spicy_media_gated}",
        f" Sibling Ripples Observed        : {report.total_sibling_ripples}",
        f" Discretion Rebuffs Enforced     : {report.total_discretion_prevented}",
        f" Total Invariant Violations      : {report.total_violations}",
        f" Total Simulation Time           : {report.duration_ms:.1f} ms",
        "-" * 65,
        " ARCHETYPE BREAKDOWN:",
    ]

    for arch, stats in report.archetype_stats.items():
        total = stats["journeys"]
        succ = stats["successful"]
        lines.append(
            f"   • {arch.upper():<16} | Journeys: {total:<3} | Clean: {succ:<3} | "
            f"Confessions: {stats['confessions']:<2} | Traits: {stats['traits']:<2} | "
            f"Spots: {stats.get('spots', 0):<2} | Ripples: {stats.get('ripples', 0):<2} | "
            f"Intimate: {stats.get('intimate', 0):<2} | Anal: {stats.get('anal', 0):<2}"
        )

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
            lines.append(f"   [!] {cat:<30} : {count}")

    lines.append("=" * 65)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Hikayat Social Dynamics & Persona Simulator")
    parser.add_argument("--simulations", "-n", type=int, default=20, help="Number of simulated journeys (default: 20)")
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
        help=f"Player behavioral archetype ('all' or one of {', '.join(SUPPORTED_ARCHETYPES)})",
    )
    parser.add_argument(
        "--fuzz", "-f",
        type=str,
        default="clean",
        choices=["clean", "realistic_llm", "adversarial_stress"],
        help="Fuzzing perturbation level (default: clean)",
    )
    parser.add_argument("--turns", "-t", type=int, default=15, help="Max turns per journey (default: 15)")
    parser.add_argument("--seed", type=int, default=None, help="Deterministic random seed")
    parser.add_argument("--fail-fast", action="store_true", help="Halt immediately upon first critical violation")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print per-journey telemetry")
    parser.add_argument("--json-report", type=str, default=None, help="Path to write JSON telemetry report")
    parser.add_argument("--with-llm", action="store_true", help="Enable live LLM sampling for NPC dialogue reactions")
    parser.add_argument("--keep-db", action="store_true", help="Preserve the simulation database after execution")
    parser.add_argument("--db-path", type=str, default=None, help="Explicit database path to use (defaults to isolated temp DB)")
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
        simulator = SocialDynamicsSimulator(seed=args.seed)

        safe_print(
            f"Starting Social Dynamics Simulator ({args.simulations} journeys, "
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
                    f"Status: {status} | Turns: {res.total_turns} | Hydrated: {res.hydrated_contacts} | "
                    f"Confessions: {res.confessions_accepted}/{res.confessions_attempted} | "
                    f"Intimate: {res.intimate_milestones_unlocked} | Anal: {res.anal_acts_simulated} | "
                    f"Traits: {res.traits_unlocked} | Time: {res.duration_ms:.1f}ms"
                )
                if res.history and (args.simulations <= 5 or args.seed is not None):
                    safe_print("    Turn-by-Turn Trace:")
                    for step in res.history:
                        t_num = step.get("turn", 0)
                        a_type = step.get("action_type", "").upper()
                        target = step.get("target", "")
                        outcome = step.get("outcome", "")
                        safe_print(f"      Turn {t_num:02d}: [{a_type:<15}] -> {target:<22} | {outcome}")
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
                "total_traits_unlocked": report.total_traits_unlocked,
                "total_confessions_accepted": report.total_confessions_accepted,
                "total_confessions_rejected": report.total_confessions_rejected,
                "illegal_advances_prevented": report.total_illegal_advances_prevented,
                "total_intimate_milestones": report.total_intimate_milestones,
                "total_anal_acts": report.total_anal_acts,
                "total_sensitive_spots": report.total_sensitive_spots,
                "total_turn_offs": report.total_turn_offs,
                "total_phone_interactions": report.total_phone_interactions,
                "total_spicy_media_gated": report.total_spicy_media_gated,
                "total_sibling_ripples": report.total_sibling_ripples,
                "total_discretion_prevented": report.total_discretion_prevented,
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
                        "seed": r.seed,
                        "turns": r.total_turns,
                        "success": r.success,
                        "traits_unlocked": r.traits_unlocked,
                        "confessions_accepted": r.confessions_accepted,
                        "confessions_rejected": r.confessions_rejected,
                        "illegal_advances_prevented": r.illegal_advances_prevented,
                        "intimate_milestones_unlocked": r.intimate_milestones_unlocked,
                        "anal_acts_simulated": r.anal_acts_simulated,
                        "sensitive_spots_discovered": r.sensitive_spots_discovered,
                        "turn_offs_triggered": r.turn_offs_triggered,
                        "phone_interactions": r.phone_interactions,
                        "spicy_media_gated": r.spicy_media_gated,
                        "sibling_ripples": r.sibling_ripples,
                        "discretion_breaches_prevented": r.discretion_breaches_prevented,
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
