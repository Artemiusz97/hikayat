from __future__ import annotations
"""
World Navigation & Waypoint Simulator Execution Engine.
Orchestrates synthetic player journeys, turn-by-turn spatial updates,
fuzzing injection, invariant auditing, telemetry aggregation, and isolated DB teardown.
"""
import time
import random
import traceback
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple

import db
from mechanics.world.locations.movement import (
    process_llm_location_update,
    auto_heal_incongruous_location,
    parse_tiered_location,
    format_tiered_location_string,
)
from mechanics.world.waypoints.matching import (
    try_advance_on_arrival,
    try_complete_on_skill_check,
)
from mechanics.system.time_engine import (
    calculate_action_time_cost,
    advance_time,
    apply_sleep_rest,
)

from .fuzzer import WaypointFuzzer
from .navigator_ai import NavigatorAI, NavigatorAction
from .auditor import SpatialInvariantAuditor, SpatialViolation


@dataclass
class JourneyResult:
    """Detailed telemetry and outcomes for a single simulated journey."""
    journey_id: int
    scenario: str
    seed: int
    total_turns: int = 0
    completed_stages: int = 0
    total_stages: int = 0
    success: bool = False
    deadlock: bool = False
    auto_heals: int = 0
    fuzz_fallbacks: int = 0
    violations: List[SpatialViolation] = field(default_factory=list)
    duration_ms: float = 0.0
    path_history: List[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class SimulationReport:
    """Aggregated metrics across a batch of simulated journeys."""
    total_journeys: int = 0
    successful_journeys: int = 0
    deadlocks: int = 0
    crashes: int = 0
    total_turns: int = 0
    avg_turns_per_journey: float = 0.0
    avg_turns_per_stage: float = 0.0
    total_auto_heals: int = 0
    total_violations: int = 0
    scenario_stats: Dict[str, Any] = field(default_factory=dict)
    violations_by_category: Dict[str, int] = field(default_factory=dict)
    duration_ms: float = 0.0
    results: List[JourneyResult] = field(default_factory=list)


class WorldNavigationSimulator:
    """Simulation harness for headless testing of world navigation and waypoints."""

    def __init__(self, seed: Optional[int] = None):
        self.master_seed = seed if seed is not None else random.randint(1, 1000000)
        self.rng = random.Random(self.master_seed)

    def run_journey(
        self,
        scenario: str = "fantasy",
        journey_id: int = 1,
        seed: Optional[int] = None,
        fuzz_mode: str = "realistic",
        max_turns: int = 35,
        fail_fast: bool = False,
        chaos_rate: float = 0.15,
        with_llm: bool = False,
    ) -> JourneyResult:
        """Executes a single end-to-end navigation and quest journey."""
        j_seed = seed if seed is not None else self.rng.randint(1, 10000000)
        local_rng = random.Random(j_seed)
        start_time = time.perf_counter()

        fuzzer = WaypointFuzzer(local_rng)
        navigator = NavigatorAI(local_rng, chaos_rate=chaos_rate)
        stagnant_limit = min(25, max(15, int(max_turns * 0.7)))
        auditor = SpatialInvariantAuditor(scenario_key=scenario, max_stagnant_turns=stagnant_limit)

        # 1. Initialize isolated synthetic session
        session_id = local_rng.randint(900000, 999999)
        sess = fuzzer.create_test_session(scenario_key=scenario, session_id=session_id)
        quest, all_wps = fuzzer.generate_story_quest_with_waypoints(session_id, scenario_key=scenario)
        total_stages = len(all_wps)

        result = JourneyResult(
            journey_id=journey_id,
            scenario=scenario,
            seed=j_seed,
            total_stages=total_stages,
        )

        current_loc = sess.get("current_location", "")
        result.path_history.append(current_loc)
        completed_stage_count = 0

        # Initial check: advance arrival waypoints if player spawned directly on target
        for wp in db.get_all_session_active_waypoints(session_id):
            if wp.get("completion_trigger") == "arrival":
                try_advance_on_arrival(
                    session_id=session_id,
                    quest_id=wp.get("quest_id", ""),
                    sub_obj_id=wp.get("sub_obj_id"),
                    current_location=current_loc,
                )

        try:
            for turn in range(1, max_turns + 1):
                result.total_turns = turn

                # A. Check active waypoints
                active_wps = db.get_all_session_active_waypoints(session_id)

                # Count completed stages
                with db.get_conn() as conn:
                    c_row = conn.execute(
                        "SELECT COUNT(*) FROM quest_waypoints WHERE session_id=? AND status='completed'",
                        (session_id,)
                    ).fetchone()
                    completed_stage_count = c_row[0] if c_row else 0
                result.completed_stages = completed_stage_count

                if not active_wps or completed_stage_count >= total_stages:
                    # All waypoint stages successfully fulfilled!
                    result.success = True
                    break

                # B. Navigator AI selects next action
                cur_day, cur_min, _ = db.get_session_time(session_id)
                action = navigator.choose_action(
                    session_id=session_id,
                    current_location=current_loc,
                    current_minute=cur_min,
                    scenario_key=scenario,
                )

                # C. Execute Action
                if action.action_type in ("travel", "backtrack", "stage_jump"):
                    raw_target = action.target_location

                    # Optional live LLM sampling hook
                    if with_llm:
                        try:
                            import asyncio
                            from llm_client import call_llm_json
                            prompt = (
                                f"The player is currently at '{current_loc}' in scenario '{scenario}'. "
                                f"They perform the following action: '{action.action_text}'. "
                                f"Destination target: '{raw_target}'. "
                                f"Return JSON with key 'new_location' formatted as Zone ➔ Primary ➔ Sub, and key 'narrative'."
                            )
                            llm_resp = asyncio.run(call_llm_json("You are the world engine for Hikayat.", prompt, timeout=10.0))
                            if isinstance(llm_resp, dict) and llm_resp.get("new_location"):
                                raw_target = str(llm_resp["new_location"])
                        except Exception:
                            pass

                    # Apply perturbation
                    perturbed_target = fuzzer.perturb_location_string(
                        raw_target,
                        fuzz_mode=fuzz_mode,
                        scenario_key=scenario,
                    )

                    # Auto-heal check
                    z, p, s = parse_tiered_location(perturbed_target, scenario, session_id=session_id)
                    hz, hp, hs = auto_heal_incongruous_location(z, p, s, session_id=session_id, scenario_key=scenario)
                    if (z, p, s) != (hz, hp, hs):
                        result.auto_heals += 1
                        auditor.auto_heals_detected += 1

                    # Process location update through engine
                    new_loc = process_llm_location_update(session_id, perturbed_target, scenario)
                    if not new_loc:
                        result.fuzz_fallbacks += 1
                        new_loc = current_loc

                    # Calculate travel time & advance time
                    time_action = {"label": action.action_text, "stat": "AGI"}
                    time_delta = calculate_action_time_cost(
                        action=time_action,
                        scen_key=scenario,
                        old_loc=current_loc,
                        new_loc=new_loc,
                    )
                    advance_time(session_id, time_delta)

                    # Update session location in DB
                    current_loc = new_loc
                    result.path_history.append(current_loc)
                    db.update_session(session_id, current_location=current_loc)

                    # Trigger arrival waypoint check across all active waypoints
                    for wp in active_wps:
                        try_advance_on_arrival(
                            session_id=session_id,
                            quest_id=wp.get("quest_id", ""),
                            sub_obj_id=wp.get("sub_obj_id"),
                            current_location=current_loc,
                        )

                elif action.action_type == "skill_check":
                    # Execute skill check advance
                    try_complete_on_skill_check(
                        session_id=session_id,
                        quest_id=action.quest_id,
                        sub_obj_id=action.sub_obj_id,
                        current_location=current_loc,
                        check_success=True,
                        check_result_tier="success",
                        action_text=action.action_text,
                        is_quest_action=True,
                        action_quest_id=action.quest_id,
                        action_sub_obj_id=action.sub_obj_id,
                    )
                    # Advance ambient time for skill check (10 mins)
                    advance_time(session_id, 10)

                elif action.action_type == "rest":
                    # Execute sleep rest cycle (wakes at 07:30 AM)
                    apply_sleep_rest(session_id, party_uids=[])

                # D. Refresh state post-action and audit
                active_wps = db.get_all_session_active_waypoints(session_id)
                with db.get_conn() as conn:
                    c_row = conn.execute(
                        "SELECT COUNT(*) FROM quest_waypoints WHERE session_id=? AND status='completed'",
                        (session_id,)
                    ).fetchone()
                    completed_stage_count = c_row[0] if c_row else 0
                result.completed_stages = completed_stage_count

                cur_day, cur_min, _ = db.get_session_time(session_id)
                violations = auditor.audit_turn(
                    turn=turn,
                    session_id=session_id,
                    current_location=current_loc,
                    current_minute=cur_min,
                    current_day=cur_day,
                    active_wps=active_wps,
                    completed_stage_count=completed_stage_count,
                )

                if any("deadlock" in v.category for v in violations):
                    result.deadlock = True
                    break

                if violations and fail_fast:
                    break

                if not active_wps or completed_stage_count >= total_stages:
                    result.success = True
                    break

        except Exception as e:
            result.error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        finally:
            # Complete teardown of synthetic test session rows across all tables
            try:
                with db.get_conn() as conn:
                    for table in (
                        "session_locations",
                        "quest_waypoints",
                        "quests",
                        "session_clues",
                        "session_members",
                        "lorebook",
                        "contacts",
                        "factions",
                        "school_directory",
                    ):
                        conn.execute(f"DELETE FROM {table} WHERE session_id=?", (session_id,))
                    conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
            except Exception:
                pass

        result.violations = auditor.violations
        result.duration_ms = (time.perf_counter() - start_time) * 1000.0
        return result

    def run_batch(
        self,
        journeys: int = 50,
        scenario: str = "all",
        fuzz_mode: str = "realistic",
        fail_fast: bool = False,
        seed: Optional[int] = None,
        chaos_rate: float = 0.15,
        with_llm: bool = False,
    ) -> SimulationReport:
        """Executes a batch of simulated journeys across scenarios."""
        start_time = time.perf_counter()
        report = SimulationReport(total_journeys=journeys)

        all_scenarios = [
            "fantasy",
            "high_school_drama",
            "cyberpunk",
            "postapoc",
            "scifi",
            "steampunk",
            "dark_fantasy",
            "isekai_fantasy",
        ]

        if scenario != "all":
            scenario_pool = [scenario]
        else:
            scenario_pool = all_scenarios

        base_seed = seed if seed is not None else self.master_seed

        for i in range(1, journeys + 1):
            j_scenario = scenario_pool[(i - 1) % len(scenario_pool)]
            j_seed = (base_seed + i * 37) % 100000000

            res = self.run_journey(
                scenario=j_scenario,
                journey_id=i,
                seed=j_seed,
                fuzz_mode=fuzz_mode,
                fail_fast=fail_fast,
                chaos_rate=chaos_rate,
                with_llm=with_llm,
            )

            report.results.append(res)
            report.total_turns += res.total_turns
            report.total_auto_heals += res.auto_heals
            report.total_violations += len(res.violations)

            if res.success:
                report.successful_journeys += 1
            if res.deadlock:
                report.deadlocks += 1
            if res.error:
                report.crashes += 1

            # Update scenario stats
            sc_stat = report.scenario_stats.setdefault(j_scenario, {
                "journeys": 0,
                "successes": 0,
                "deadlocks": 0,
                "crashes": 0,
                "turns": 0,
                "violations": 0,
                "auto_heals": 0,
            })
            sc_stat["journeys"] += 1
            if res.success: sc_stat["successes"] += 1
            if res.deadlock: sc_stat["deadlocks"] += 1
            if res.error: sc_stat["crashes"] += 1
            sc_stat["turns"] += res.total_turns
            sc_stat["violations"] += len(res.violations)
            sc_stat["auto_heals"] += res.auto_heals

            # Update violations by category
            for v in res.violations:
                report.violations_by_category[v.category] = report.violations_by_category.get(v.category, 0) + 1

            if fail_fast and (res.violations or res.error or res.deadlock):
                break

        report.duration_ms = (time.perf_counter() - start_time) * 1000.0
        report.total_journeys = len(report.results)
        if report.total_journeys > 0:
            report.avg_turns_per_journey = report.total_turns / report.total_journeys
            total_stages = sum(r.completed_stages for r in report.results)
            report.avg_turns_per_stage = report.total_turns / max(1, total_stages)

        return report
