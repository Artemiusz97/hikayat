#!/usr/bin/env python3
"""
CLI Runner for the Hikayat Intimate Moment & Excitement Meter Simulator.

Usage Examples:
    python scripts/simulate_intimacy.py --simulations 20 --scenario all
    python scripts/simulate_intimacy.py --simulations 10 --scenario full_progression --partner-config hetero --verbose
    python scripts/simulate_intimacy.py --simulations 15 --partner-config mixed_group --fuzz realistic_llm
    python scripts/simulate_intimacy.py --seed 42091 --scenario sudden_initiation --partner-config multi_female --verbose
    python scripts/simulate_intimacy.py --simulations 25 --fuzz adversarial_stress --json-report intimacy_report.json
"""
import argparse
import json
import os
import sys
import time

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import db
from tests.simulators.intimacy import (
    IntimacySimulator,
    IntimacySimulationReport,
    IntimacyJourneyResult,
    SUPPORTED_SCENARIOS,
    SUPPORTED_PARTNER_CONFIGS,
    SUPPORTED_FUZZ_MODES,
)


def safe_print(text: str = ""):
    """Safe console output preventing cp1252 Windows encoding exceptions."""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"), flush=True)


def format_gauge_bar(meter: int, length: int = 10) -> str:
    """Renders a visual meter gauge bar: [████░░░░░░] or [####------]"""
    clamped = max(0, min(100, meter))
    filled = int(round((clamped / 100.0) * length))
    empty = length - filled
    is_cp = getattr(sys.stdout, "encoding", "utf-8") and "cp" in str(sys.stdout.encoding).lower()
    f_char = "#" if is_cp else "█"
    e_char = "-" if is_cp else "░"
    return f"[{f_char * filled}{e_char * empty}] {clamped:3d}%"


def format_report_summary(report: IntimacySimulationReport, duration_ms: float = 0.0) -> str:
    """Formats a structured summary of the intimacy simulation run."""
    clean_pct = (report.successful_journeys / max(1, report.total_journeys)) * 100.0
    is_cp = getattr(sys.stdout, "encoding", "utf-8") and "cp" in str(sys.stdout.encoding).lower()
    bullet = "*" if is_cp else "•"
    lines = [
        "=" * 68,
        "         INTIMATE MOMENT & EXCITEMENT METER SIMULATION REPORT        ",
        "=" * 68,
        f" Total Journeys Simulated        : {report.total_journeys}",
        f" Completed / Invariant-Clean     : {report.successful_journeys} ({clean_pct:.1f}%)",
        f" Crashes / Uncaught Exceptions   : {report.crashes}",
        f" Total Turns Executed            : {report.total_turns}",
        f" Average Turns / Journey         : {report.avg_turns_per_journey:.2f}",
        f" Total Player Climaxes           : {report.total_player_climaxes}",
        f" Total Partner Climaxes          : {report.total_partner_climaxes}",
        f" Total Multi-Climaxes (Female)   : {report.total_multi_climaxes}",
        f" Premature Finishes Handled      : {report.total_premature_finishes}",
        f" Demand Negotiations Resolved    : {report.total_demands_resolved}",
        f" Secret Affairs Detected         : {report.total_affairs_detected}",
        f" First-Time Milestones Logged    : {report.total_first_times_logged}",
        f" Total Invariant Violations      : {report.total_violations}",
        f" Total Simulation Time           : {duration_ms:.1f} ms",
        "-" * 68,
        " PARTNER CONFIGURATION BREAKDOWN:",
    ]

    for cfg, stats in report.partner_config_breakdown.items():
        total = stats.get("journeys", 0)
        succ = stats.get("successful", 0)
        lines.append(f"   {bullet} {cfg.upper():<16} | Journeys: {total:<3} | Clean: {succ:<3}")

    lines.append("-" * 68)
    lines.append(" SCENARIO BREAKDOWN:")
    for scen, stats in report.scenario_breakdown.items():
        total = stats.get("journeys", 0)
        succ = stats.get("successful", 0)
        lines.append(f"   {bullet} {scen:<20} | Journeys: {total:<3} | Clean: {succ:<3}")

    if report.violations_by_category:
        lines.append("-" * 68)
        lines.append(" VIOLATIONS BY CATEGORY:")
        for cat, count in sorted(report.violations_by_category.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"   [!] {cat:<32} : {count}")

    lines.append("=" * 68)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Hikayat Intimate Moment & Excitement Meter Simulator")
    parser.add_argument(
        "--simulations", "--count", "-n",
        type=int,
        default=10,
        dest="simulations",
        help="Number of simulated journeys (default: 10)",
    )
    parser.add_argument(
        "--scenario", "-s",
        type=str,
        default="all",
        help=f"Scenario to simulate ('all' or one of {', '.join(SUPPORTED_SCENARIOS)})",
    )
    parser.add_argument(
        "--partner-config", "-p",
        type=str,
        default="all",
        help=f"Partner configuration ('all' or one of {', '.join(SUPPORTED_PARTNER_CONFIGS)})",
    )
    parser.add_argument(
        "--fuzz",
        type=str,
        default="realistic_llm",
        choices=SUPPORTED_FUZZ_MODES,
        help="Fuzzing mode: 'none', 'realistic_llm', or 'adversarial_stress' (default: realistic_llm)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Deterministic pseudo-random seed for reproducible runs",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Abort simulation batch immediately on first invariant violation or crash",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print turn-by-turn action and visual excitement gauge telemetry",
    )
    parser.add_argument(
        "--json-report",
        type=str,
        default=None,
        help="Save simulation results and audit report to specified JSON file path",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Path to custom SQLite database file (default: in-memory / configured DB)",
    )

    args = parser.parse_args()

    simulator = IntimacySimulator(db_path=args.db_path)

    safe_print("\n" + "=" * 68)
    safe_print("    HIKAYAT INTIMATE MOMENT & EXCITEMENT METER SIMULATOR")
    safe_print("=" * 68)
    safe_print(f" Simulations Requested : {args.simulations}")
    safe_print(f" Target Scenario       : {args.scenario}")
    safe_print(f" Partner Configuration : {args.partner_config}")
    safe_print(f" Fuzzing Mode          : {args.fuzz}")
    if args.seed is not None:
        safe_print(f" Master RNG Seed       : {args.seed}")
    safe_print(f" Fail-Fast Enabled     : {args.fail_fast}")
    safe_print(f" Verbose Telemetry     : {args.verbose}")
    safe_print("-" * 68 + "\n")

    t_start = time.perf_counter()

    if args.verbose:
        # Run journeys individually to stream real-time gauge telemetry
        report = IntimacySimulationReport()
        scenarios_pool = (
            SUPPORTED_SCENARIOS
            if args.scenario.lower() == "all"
            else [s.strip().lower() for s in args.scenario.split(",") if s.strip().lower() in SUPPORTED_SCENARIOS]
        ) or ["full_progression"]
        configs_pool = (
            SUPPORTED_PARTNER_CONFIGS
            if args.partner_config.lower() == "all"
            else [c.strip().lower() for c in args.partner_config.split(",") if c.strip().lower() in SUPPORTED_PARTNER_CONFIGS]
        ) or ["hetero"]

        for i in range(1, args.simulations + 1):
            chosen_scenario = scenarios_pool[(i - 1) % len(scenarios_pool)]
            chosen_config = configs_pool[(i - 1) % len(configs_pool)]
            is_affair = (i % 3 == 0)

            safe_print(f"\n--- JOURNEY #{i} | Scenario: {chosen_scenario} | Config: {chosen_config} ---")
            res = simulator.run_simulation(
                scenario=chosen_scenario,
                partner_config=chosen_config,
                fuzz_mode=args.fuzz,
                seed=args.seed + i if args.seed is not None else None,
                journey_id=i,
                is_secret_affair_test=is_affair,
                verbose=True,
            )

            # Stream turn details
            for t_info in res.turn_log:
                p_bar = format_gauge_bar(t_info.get("player_meter", 0))
                p_delta = t_info.get("player_delta", 0)
                sign = "+" if p_delta >= 0 else ""
                turn_num = t_info["turn"]
                act_str = t_info.get("action", "")

                partner_bars = []
                for pm in t_info.get("partner_meters", []):
                    nm = pm.get("name", "Partner")
                    m_bar = format_gauge_bar(pm.get("meter", 0))
                    d_val = pm.get("delta", 0)
                    d_sign = "+" if d_val >= 0 else ""
                    partner_bars.append(f"[{nm}]: {m_bar} ({d_sign}{d_val})")

                part_str = " | ".join(partner_bars) if partner_bars else f"[Partner]: {format_gauge_bar(t_info.get('partner_meter', 0))}"
                safe_print(f"  T{turn_num:02d} | [Player]: {p_bar} ({sign}{p_delta}) | {part_str}")
                safe_print(f"       Act: {act_str}")

            if res.violations:
                safe_print(f"  [!] VIOLATIONS ({len(res.violations)}):")
                for v in res.violations:
                    safe_print(f"      - [{v.category}] {v.message}")
            else:
                ok_marker = "[OK]" if (getattr(sys.stdout, "encoding", "utf-8") and "cp" in str(sys.stdout.encoding).lower()) else "[✓]"
                safe_print(f"  {ok_marker} Journey #{i} Completed Invariant-Clean ({res.turns} turns)")

            # Aggregate into report
            report.total_journeys += 1
            report.total_turns += res.turns
            report.total_player_climaxes += res.player_climaxes
            report.total_partner_climaxes += res.partner_climaxes
            report.total_multi_climaxes += res.multi_climaxes
            report.total_premature_finishes += res.premature_finishes
            report.total_demands_resolved += res.demands_resolved
            report.total_affairs_detected += res.affairs_detected
            report.total_first_times_logged += res.first_times_logged

            if res.crashed:
                report.crashes += 1
            if res.success:
                report.successful_journeys += 1

            for v in res.violations:
                report.total_violations += 1
                report.violations_by_category[v.category] = report.violations_by_category.get(v.category, 0) + 1

            s_entry = report.scenario_breakdown.setdefault(chosen_scenario, {"journeys": 0, "successful": 0})
            s_entry["journeys"] += 1
            if res.success:
                s_entry["successful"] += 1

            c_entry = report.partner_config_breakdown.setdefault(chosen_config, {"journeys": 0, "successful": 0})
            c_entry["journeys"] += 1
            if res.success:
                c_entry["successful"] += 1

            report.journey_results.append(res)

            if args.fail_fast and (not res.success or res.crashed):
                safe_print("\n[!] Fail-fast triggered. Aborting batch execution.")
                break

        if report.total_journeys > 0:
            report.avg_turns_per_journey = report.total_turns / report.total_journeys
    else:
        report = simulator.run_batch(
            num_simulations=args.simulations,
            scenario=args.scenario,
            partner_config=args.partner_config,
            fuzz_mode=args.fuzz,
            seed=args.seed,
            fail_fast=args.fail_fast,
            verbose=False,
        )

    t_end = time.perf_counter()
    duration_ms = (t_end - t_start) * 1000.0

    summary_text = format_report_summary(report, duration_ms=duration_ms)
    safe_print("\n" + summary_text)

    if args.json_report:
        report_data = {
            "total_journeys": report.total_journeys,
            "successful_journeys": report.successful_journeys,
            "crashes": report.crashes,
            "total_turns": report.total_turns,
            "avg_turns_per_journey": report.avg_turns_per_journey,
            "total_player_climaxes": report.total_player_climaxes,
            "total_partner_climaxes": report.total_partner_climaxes,
            "total_multi_climaxes": report.total_multi_climaxes,
            "total_premature_finishes": report.total_premature_finishes,
            "total_demands_resolved": report.total_demands_resolved,
            "total_affairs_detected": report.total_affairs_detected,
            "total_first_times_logged": report.total_first_times_logged,
            "total_violations": report.total_violations,
            "violations_by_category": report.violations_by_category,
            "scenario_breakdown": report.scenario_breakdown,
            "partner_config_breakdown": report.partner_config_breakdown,
            "duration_ms": duration_ms,
            "results": [
                {
                    "journey_id": r.journey_id,
                    "scenario": r.scenario,
                    "partner_config": r.partner_config,
                    "fuzz_mode": r.fuzz_mode,
                    "turns": r.turns,
                    "success": r.success,
                    "crashed": r.crashed,
                    "error_message": r.error_message,
                    "player_climaxes": r.player_climaxes,
                    "partner_climaxes": r.partner_climaxes,
                    "multi_climaxes": r.multi_climaxes,
                    "premature_finishes": r.premature_finishes,
                    "demands_resolved": r.demands_resolved,
                    "affairs_detected": r.affairs_detected,
                    "first_times_logged": r.first_times_logged,
                    "violations": [
                        {
                            "category": v.category,
                            "turn": v.turn,
                            "message": v.message,
                            "actor_name": v.actor_name,
                            "severity": v.severity,
                        }
                        for v in r.violations
                    ],
                }
                for r in report.journey_results
            ],
        }
        with open(args.json_report, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)
        ok_marker = "[OK]" if (getattr(sys.stdout, "encoding", "utf-8") and "cp" in str(sys.stdout.encoding).lower()) else "[✓]"
        safe_print(f"\n{ok_marker} Detailed JSON report written to: {args.json_report}")

    sys.exit(0 if report.total_violations == 0 and report.crashes == 0 else 1)


if __name__ == "__main__":
    main()
