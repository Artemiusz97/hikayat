from __future__ import annotations
"""
tests/simulators/stealth/engine.py
Execution engine for the Hikayat Stealth & Infiltration Simulator.

Simulates multi-turn covert infiltration missions:
- Heist: Infiltrate, steal target objective, extract.
- Evasion: Sneak past heavy patrols to reach safety.
- Silent Takedown: Eliminate sentries sequentially without detection.

Audits strict mathematical invariants, seamless combat hand-offs, and companion noise penalties.
"""
import copy
import json
import random
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import db
import character_data as cd
from mechanics.stealth.core import (
    init_stealth_state,
    get_session_stealth_state,
    set_session_stealth_state,
    toggle_stealth_stance,
    break_stealth,
    apply_stealth_decay_turn,
    apply_stealth_distraction,
    apply_stealth_spatial_transition,
    consume_stealth_turn_transients,
    resolve_distraction_action,
    resolve_stealth_action,
    format_stealth_truth_directive
)
from mechanics.stealth.escalation import reduce_stealth_turn_outcome
from game_engine.npcs.cast_planner import plan_pre_turn
from api.deps import _serializable_action
from mechanics.stealth.alert_tracker import (
    ALERT_UNAWARE,
    ALERT_SUSPICIOUS,
    ALERT_SEARCHING,
    ALERT_DETECTED,
    get_alert_stage
)
from mechanics.combat.enemies import build_enemy_stat_sheet
from tests.simulators.stealth.actor_ai import StealthActorAI, StealthAction, SUPPORTED_PROFILES
from tests.simulators.stealth.auditor import StealthInvariantAuditor, StealthViolation


def safe_print(msg: str = "") -> None:
    """Print helper that safely handles console encoding on Windows without crashing on emojis."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        try:
            sys.stdout.buffer.write((str(msg) + "\n").encode("utf-8", errors="replace"))
            sys.stdout.buffer.flush()
        except Exception:
            print(str(msg).encode("ascii", errors="replace").decode("ascii"), flush=True)


@dataclass
class StealthMissionResult:
    """Detailed outcome and telemetry for a single simulated stealth mission."""
    mission_id: int
    scenario: str
    mission_type: str
    profile: str
    seed: int
    party_size: int
    total_turns: int = 0
    success: bool = False
    detected: bool = False
    combat_triggered: bool = False
    combat_outcome: Optional[str] = None
    final_meter: int = 0
    final_stage: str = "unaware"
    distractions_used: int = 0
    takedowns_executed: int = 0
    violations: List[StealthViolation] = field(default_factory=list)
    trace_log: List[str] = field(default_factory=list)
    duration_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class StealthSimulationReport:
    """Aggregated metrics across a batch of stealth missions."""
    total_missions: int = 0
    successes: int = 0
    detected_count: int = 0
    combat_escalations: int = 0
    crashes: int = 0
    total_turns: int = 0
    total_duration_ms: float = 0.0
    profile_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    scenario_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    violations_by_category: Dict[str, int] = field(default_factory=dict)
    failing_seeds: List[Dict[str, Any]] = field(default_factory=list)
    results: List[StealthMissionResult] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return (self.successes / max(1, self.total_missions)) * 100.0

    @property
    def detection_rate(self) -> float:
        return (self.detected_count / max(1, self.total_missions)) * 100.0

    @property
    def avg_turns(self) -> float:
        return (self.total_turns / max(1, self.total_missions))

    def add_result(self, res: StealthMissionResult) -> None:
        self.total_missions += 1
        self.total_turns += res.total_turns
        self.total_duration_ms += res.duration_ms
        self.results.append(res)

        if res.success:
            self.successes += 1
        if res.detected:
            self.detected_count += 1
        if res.combat_triggered:
            self.combat_escalations += 1
        if res.error:
            self.crashes += 1

        # Profile breakdown
        p = res.profile
        if p not in self.profile_stats:
            self.profile_stats[p] = {"total": 0, "success": 0, "detected": 0, "combat": 0, "turns": 0}
        self.profile_stats[p]["total"] += 1
        self.profile_stats[p]["turns"] += res.total_turns
        if res.success:
            self.profile_stats[p]["success"] += 1
        if res.detected:
            self.profile_stats[p]["detected"] += 1
        if res.combat_triggered:
            self.profile_stats[p]["combat"] += 1

        # Scenario breakdown
        sc = res.scenario
        if sc not in self.scenario_stats:
            self.scenario_stats[sc] = {"total": 0, "success": 0, "detected": 0, "combat": 0}
        self.scenario_stats[sc]["total"] += 1
        if res.success:
            self.scenario_stats[sc]["success"] += 1
        if res.detected:
            self.scenario_stats[sc]["detected"] += 1
        if res.combat_triggered:
            self.scenario_stats[sc]["combat"] += 1

        # Violations
        if res.violations or res.error:
            for v in res.violations:
                self.violations_by_category[v.category] = self.violations_by_category.get(v.category, 0) + 1
            if res.error:
                self.violations_by_category["CRASH_EXCEPTION"] = self.violations_by_category.get("CRASH_EXCEPTION", 0) + 1

            self.failing_seeds.append({
                "mission_id": res.mission_id,
                "seed": res.seed,
                "scenario": res.scenario,
                "profile": res.profile,
                "mission_type": res.mission_type,
                "violations": [f"{v.category}: {v.message}" for v in res.violations],
                "error": res.error
            })

    def format_summary(self) -> str:
        lines = [
            "=" * 60,
            "         STEALTH & INFILTRATION SIMULATION REPORT          ",
            "=" * 60,
            f" Total Missions Simulated : {self.total_missions}",
            f" Successful Infiltrations : {self.successes} ({self.success_rate:.1f}%)",
            f" Detected Covers Broken   : {self.detected_count} ({self.detection_rate:.1f}%)",
            f" Combat Handoffs Triggered: {self.combat_escalations}",
            f" Crashes / Uncaught Errs  : {self.crashes}",
            f" Total Turns Executed     : {self.total_turns}",
            f" Average Turns / Mission  : {self.avg_turns:.2f}",
            f" Total Simulation Time    : {self.total_duration_ms:.1f} ms",
            "-" * 60,
            " PROFILE BREAKDOWN:",
        ]
        for prof, stat in sorted(self.profile_stats.items()):
            tot = stat["total"]
            s_pct = (stat["success"] / tot * 100.0) if tot else 0
            d_pct = (stat["detected"] / tot * 100.0) if tot else 0
            lines.append(
                f"   * {prof:<12}: {tot:>3} missions | Clear: {s_pct:>5.1f}% | Caught: {d_pct:>5.1f}% | Combat: {stat['combat']}"
            )

        lines.append("-" * 60)
        lines.append(" SCENARIO BREAKDOWN:")
        for sc, stat in sorted(self.scenario_stats.items()):
            tot = stat["total"]
            s_pct = (stat["success"] / tot * 100.0) if tot else 0
            lines.append(f"   * {sc:<16}: {tot:>3} missions | Clear: {s_pct:>5.1f}% | Combat: {stat['combat']}")

        lines.append("-" * 60)
        lines.append(" INVARIANT VIOLATIONS & ANOMALIES:")
        if not self.violations_by_category:
            lines.append("   🎉 ZERO INVARIANT VIOLATIONS DETECTED!")
        else:
            for cat, cnt in sorted(self.violations_by_category.items(), key=lambda x: -x[1]):
                lines.append(f"   ⚠️  [{cnt}x] {cat}")

        if self.failing_seeds:
            lines.append("-" * 60)
            lines.append(f" REPRODUCTION COMMANDS ({len(self.failing_seeds)} failure seeds):")
            for fs in self.failing_seeds[:5]:
                lines.append(f"   python scripts/simulate_stealth.py --seed {fs['seed']} --scenario {fs['scenario']} --profile {fs['profile']} -v")
            if len(self.failing_seeds) > 5:
                lines.append(f"   ... and {len(self.failing_seeds) - 5} more.")

        lines.append("=" * 60)
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_missions": self.total_missions,
            "successes": self.successes,
            "success_rate": round(self.success_rate, 2),
            "detected_count": self.detected_count,
            "detection_rate": round(self.detection_rate, 2),
            "combat_escalations": self.combat_escalations,
            "crashes": self.crashes,
            "total_turns": self.total_turns,
            "avg_turns": round(self.avg_turns, 2),
            "total_duration_ms": round(self.total_duration_ms, 2),
            "profile_stats": self.profile_stats,
            "scenario_stats": self.scenario_stats,
            "violations_by_category": self.violations_by_category,
            "failing_seeds": self.failing_seeds[:50],
        }


class StealthMissionFuzzer:
    """Procedurally generates sectors, lighting environments, sentries, and agent equipment."""

    def __init__(self, rng: random.Random):
        self.rng = rng

    def generate_player(self, scenario: str, profile: str, user_id: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Generates an in-memory character with gear tailored to the agent's profile."""
        if profile == "ghost":
            stats = {"STR": 3, "PER": 8, "END": 4, "CHA": 4, "INT": 6, "AGI": 9, "LUK": 6}
            gear = [
                {"name": "Shadowweave Cloak", "item_type": "Armor", "slot": "Armor", "effect": "+2 AGI", "equipped": 1, "weight": 2},
                {"name": "Silent Stalkers", "item_type": "Shoes", "slot": "Shoes", "effect": "+1 PER", "equipped": 1, "weight": 1},
                {"name": "Ceramic Dagger", "item_type": "Weapon", "slot": "Weapon", "effect": "+3 ATK", "equipped": 1, "weight": 2},
                # Unequipped heavy loot in backpack MUST NOT penalize stealth odds
                {"name": "Looted Full Plate", "item_type": "Armor", "slot": "Armor", "effect": "+15 DEF", "equipped": 0, "weight": 28, "tags": {"weight": ["heavy", "plate"]}},
            ]
        elif profile == "heavy":
            stats = {"STR": 9, "PER": 3, "END": 8, "CHA": 4, "INT": 4, "AGI": 3, "LUK": 4}
            gear = [
                {"name": "Heavy Plate Armor", "item_type": "Armor", "slot": "Armor", "effect": "+15 DEF, noise_penalty", "equipped": 1, "weight": 25},
                {"name": "Iron Greaves", "item_type": "Shoes", "slot": "Shoes", "effect": "+5 DEF", "equipped": 1, "weight": 10},
                {"name": "Greatsword", "item_type": "Weapon", "slot": "Weapon", "effect": "+12 ATK", "equipped": 1, "weight": 14}
            ]
        else:  # specialist or chaos
            stats = {"STR": 5, "PER": 7, "END": 5, "CHA": 5, "INT": 7, "AGI": 6, "LUK": 7}
            gear = [
                {"name": "Tactical Vest", "item_type": "Armor", "slot": "Armor", "effect": "+5 DEF", "equipped": 1, "weight": 6},
                {"name": "Utility Belt", "item_type": "Accessory", "slot": "Accessory", "effect": "+2 INT", "equipped": 1, "weight": 3},
                {"name": "Silenced Pistol", "item_type": "Weapon", "slot": "Weapon", "effect": "+6 ATK", "equipped": 1, "weight": 4}
            ]

        char = {
            "id": user_id,
            "user_id": user_id,
            "name": f"Agent_{profile.capitalize()}",
            "level": 3,
            "hp": 100,
            "max_hp": 100,
            "mp": 50,
            "max_mp": 50,
            "stats": stats,
            "status_effects": [],
            "scenario": scenario
        }
        for k, v in stats.items():
            char[f"{k.lower()}_"] = v
            char[k] = v

        return char, gear

    def generate_companions(self, scenario: str, party_size: int) -> List[Dict[str, Any]]:
        """Generates party companions with noise attributes."""
        companions = []
        for i in range(max(0, party_size - 1)):
            comp = {
                "name": f"Operative_Ally_{i+1}",
                "level": 3,
                "hp": 90,
                "max_hp": 90,
                "stats": {"STR": 5, "PER": 5, "END": 5, "CHA": 5, "INT": 5, "AGI": 5, "LUK": 5},
                # Second companion is noisy to stress companion noise drag
                "equipped_items": [
                    {"name": "Steel Bulwark" if i == 1 else "Scout Leathers", "item_type": "Armor", "weight": 18 if i == 1 else 3}
                ]
            }
            companions.append(comp)
        return companions

    def generate_facility_sectors(self, scenario: str, mission_type: str) -> List[Dict[str, Any]]:
        """Generates 4 connected infiltration sectors with lighting and sentries."""
        lighting_pool = [
            ("pitch_black", -20, "Pitch-black darkness concealing all shadows."),
            ("dim_lighting", -10, "Faint emergency luminescence, shadows are deep."),
            ("normal_light", 0, "Standard interior hallway illumination."),
            ("bright_neon", 15, "Blinding overhead spotlights with security beams.")
        ]

        sectors = [
            {
                "id": "sector_perimeter",
                "name": "Blackwood Facility • Outer Perimeter",
                "lighting": lighting_pool[0][0],
                "lighting_penalty": lighting_pool[0][1],
                "has_objective": False,
                "is_exit": True,
                "sentries": [
                    {"name": "Perimeter Patrol", "hp": 60, "stats": {"PER": 3, "STR": 5, "END": 5}}
                ]
            },
            {
                "id": "sector_corridor",
                "name": "Blackwood Facility • Access Corridor Beta",
                "lighting": lighting_pool[1][0],
                "lighting_penalty": lighting_pool[1][1],
                "has_objective": False,
                "is_exit": False,
                "sentries": [
                    {"name": "Corridor Guard", "hp": 70, "stats": {"PER": 5, "STR": 6, "END": 6}}
                ]
            },
            {
                "id": "sector_vault",
                "name": "Blackwood Facility • Secure Data Vault",
                "lighting": lighting_pool[2][0],
                "lighting_penalty": lighting_pool[2][1],
                "has_objective": True,
                "is_exit": False,
                "sentries": [
                    {"name": "Elite Sentry Alpha", "hp": 90, "stats": {"PER": 6, "STR": 7, "END": 7}}
                ]
            },
            {
                "id": "sector_rooftop",
                "name": "Blackwood Facility • Extraction Heli-Pad",
                "lighting": lighting_pool[3][0],
                "lighting_penalty": lighting_pool[3][1],
                "has_objective": False,
                "is_exit": True,
                "sentries": []
            }
        ]
        return sectors


class StealthSimulator:
    """Headless simulation harness for covert infiltration missions."""

    def __init__(self, base_user_id: int = 9980000, seed: Optional[int] = None):
        self.base_user_id = base_user_id
        self.master_seed = seed if seed is not None else random.randint(100000, 999999)
        self.rng = random.Random(self.master_seed)

    def run_mission(
        self,
        mission_id: int = 1,
        scenario: str = "fantasy",
        mission_type: str = "heist",
        profile: str = "ghost",
        party_size: int = 1,
        max_turns: int = 25,
        seed: Optional[int] = None,
        verbose: bool = False,
        fail_fast: bool = False
    ) -> StealthMissionResult:
        """Executes a single multi-turn covert infiltration mission."""
        m_seed = seed if seed is not None else self.rng.randint(100000, 9999999)
        local_rng = random.Random(m_seed)
        random.seed(m_seed)
        start_time = time.perf_counter()

        user_id = self.base_user_id + (mission_id % 1000)
        fuzzer = StealthMissionFuzzer(local_rng)
        actor_ai = StealthActorAI(profile=profile, rng=local_rng)
        auditor = StealthInvariantAuditor(scenario=scenario)

        # 1. Setup Actor, Equipment & Party
        player_char, equipped_items = fuzzer.generate_player(scenario, profile, user_id)
        companions = fuzzer.generate_companions(scenario, party_size)
        party = [(player_char, equipped_items)] + [(c, c.get("equipped_items", [])) for c in companions]

        # 2. Setup Infiltration Sectors
        sectors = fuzzer.generate_facility_sectors(scenario, mission_type)
        current_sector_idx = 0
        objective_secured = False

        # 3. Setup Session & Stealth State
        session = {
            "id": mission_id,
            "scenario": scenario,
            "current_location": sectors[0]["name"],
            "stealth_state": init_stealth_state(is_hidden=True),
            "nearby_enemies": sectors[0]["sentries"],
            "current_npcs": companions
        }

        result = StealthMissionResult(
            mission_id=mission_id,
            scenario=scenario,
            mission_type=mission_type,
            profile=profile,
            seed=m_seed,
            party_size=party_size
        )

        if verbose:
            safe_print(f"\n--- STEALTH MISSION #{mission_id} [{scenario.upper()} | Type: {mission_type} | Profile: {profile} | Party: {party_size} | Seed: {m_seed}] ---")

        try:
            for turn in range(1, max_turns + 1):
                result.total_turns = turn
                current_sector = sectors[current_sector_idx]
                session["current_location"] = current_sector["name"]
                st_state = get_session_stealth_state(session)
                sentries = current_sector.get("sentries", [])

                # Adjacent sectors available to move to
                adjacent = []
                if current_sector_idx > 0:
                    adjacent.append(sectors[current_sector_idx - 1])
                if current_sector_idx < len(sectors) - 1:
                    adjacent.append(sectors[current_sector_idx + 1])

                # A. Actor decides next covert action
                action = actor_ai.choose_action(
                    session=session,
                    stealth_state=st_state,
                    current_sector=current_sector,
                    adjacent_sectors=adjacent,
                    sentries_present=sentries,
                    turn=turn,
                    objective_reached=objective_secured
                )

                log_entry = f"Turn {turn:02d} [{current_sector['name']}] Actor -> {action.label} (Alert: {st_state['detection_meter']}%)"
                result.trace_log.append(log_entry)
                if verbose:
                    safe_print(f"   * {log_entry}")

                # B. Execute Action Mechanics
                quiet_turn = False
                resolution = {}

                if action.action_type == "distraction":
                    result.distractions_used += 1
                    resolution = resolve_distraction_action(
                        session=session,
                        actor_char=player_char,
                        user_id=user_id,
                    )

                elif action.action_type == "wait_quietly":
                    quiet_turn = True
                    apply_stealth_decay_turn(session, is_waiting_still=True)
                    st_state = get_session_stealth_state(session)
                    resolution = {
                        "check": None,
                        "odds": {},
                        "stealth_state": st_state,
                        "directive": format_stealth_truth_directive(session, st_state),
                        "trigger_combat": False,
                        "trigger_confrontation": False,
                    }

                elif action.action_type == "sneak_move":
                    # Move to adjacent sector inside the same facility (halves suspicion)
                    prev_loc_name = current_sector["name"]
                    dest_sector = next((s for s in adjacent if s.get("name") == action.target_room), None)
                    if dest_sector:
                        current_sector_idx = sectors.index(dest_sector)
                        current_sector = dest_sector
                        sentries = current_sector.get("sentries", [])
                        session["current_location"] = current_sector["name"]
                        session["nearby_enemies"] = sentries
                        apply_stealth_spatial_transition(
                            session,
                            prev_location=prev_loc_name,
                            new_location=current_sector["name"],
                        )
                        auditor.previous_meter = get_session_stealth_state(session).get("detection_meter", 0)

                    # Resolve stealth check on movement
                    sentry_target = sentries[0] if sentries else None
                    action_payload = {
                        "label": action.label,
                        "action_type": "sneak",
                        "custom_action_text": action.custom_action_text
                    }
                    resolution = resolve_stealth_action(
                        session=session,
                        actor_char=player_char,
                        action_data=action_payload,
                        target_entity=sentry_target,
                        party=party,
                        equipped_items=equipped_items,
                        environment=current_sector.get("lighting", "normal"),
                        user_id=user_id,
                    )

                elif action.action_type == "silent_takedown":
                    # Opposed check for instant takedown
                    sentry_target = sentries[0] if sentries else None
                    action_payload = {
                        "label": action.label,
                        "action_type": "takedown",
                        "custom_action_text": action.custom_action_text
                    }
                    resolution = resolve_stealth_action(
                        session=session,
                        actor_char=player_char,
                        action_data=action_payload,
                        target_entity=sentry_target,
                        party=party,
                        equipped_items=equipped_items,
                        environment=current_sector.get("lighting", "normal"),
                        user_id=user_id,
                    )
                    chk = resolution.get("check")
                    if chk and chk.succeeded:
                        result.takedowns_executed += 1
                        if sentries:
                            current_sector["sentries"].pop(0)
                            session["nearby_enemies"] = current_sector["sentries"]

                elif action.action_type == "interact_objective":
                    objective_secured = True
                    action_payload = {
                        "label": action.label,
                        "action_type": "interact",
                        "custom_action_text": action.custom_action_text
                    }
                    resolution = resolve_stealth_action(
                        session=session,
                        actor_char=player_char,
                        action_data=action_payload,
                        target_entity=sentries[0] if sentries else None,
                        party=party,
                        equipped_items=equipped_items,
                        environment=current_sector.get("lighting", "normal"),
                        user_id=user_id,
                    )

                elif action.action_type == "ambush_strike" or action.is_ambush:
                    # Player voluntarily triggers an ambush strike!
                    resolution = {
                        "stealth_state": get_session_stealth_state(session),
                        "trigger_combat": True,
                        "directive": ""
                    }
                    break_stealth(session, reason="ambush_initiated")

                else:  # recon / default
                    quiet_turn = True
                    apply_stealth_decay_turn(session)
                    st_state = get_session_stealth_state(session)
                    resolution = {
                        "check": None,
                        "odds": {},
                        "stealth_state": st_state,
                        "directive": format_stealth_truth_directive(session, st_state),
                        "trigger_combat": False
                    }

                # C. Verify CastPlanner & Action JSON Serialization Safety, then Audit Invariants
                if profile == "ghost":
                    resolution["expect_zero_armor_noise"] = True
                try:
                    safe_act = _serializable_action({
                        "label": action.label,
                        "is_stealth": True,
                        "check": resolution.get("check"),
                        "stealth_outcome": resolution,
                    })
                    json.dumps(safe_act)
                except Exception as ser_exc:
                    resolution["serialization_error"] = str(ser_exc)

                st_state = get_session_stealth_state(session)
                if st_state.get("is_hidden") and st_state.get("detection_meter", 0) < 100:
                    cast_plan = plan_pre_turn(
                        session=session,
                        party=party,
                        actions=[{
                            "label": action.label,
                            "is_stealth": True,
                            "stance": "stealth",
                            "intent": "stealth_covert",
                            "check": resolution.get("check"),
                        }],
                        is_combat=False,
                        persist_db=False,
                    )
                    resolution["cast_plan"] = {"stealth_active": cast_plan.stealth_active}

                violations = auditor.audit_turn(
                    turn=turn,
                    session=session,
                    stealth_state=st_state,
                    action={"label": action.label, "type": action.action_type},
                    resolution=resolution,
                    quiet_turn=quiet_turn
                )
                consume_stealth_turn_transients(session)
                if violations:
                    result.violations.extend(violations)
                    if fail_fast:
                        raise AssertionError(f"Stealth Invariant Violation on turn {turn}: {violations[0].message}")

                # D. Check Escalation at 100% Detection or Voluntary Ambush
                if resolution.get("trigger_confrontation") and not resolution.get("trigger_combat"):
                    result.detected = True
                    outcome_probe: Dict[str, Any] = {"next_narrative": "Security closes in.", "choices": []}
                    reduce_stealth_turn_outcome(
                        session_id=0,
                        session=session,
                        party=party,
                        outcome=outcome_probe,
                        actions=[{"stealth_outcome": resolution}],
                        scen_key=scenario,
                        is_combat=False,
                    )
                    result.trace_log.append(
                        f"Turn {turn:02d} [ALERT 100 / CONFRONTATION] Authority confrontation triggered with {outcome_probe.get('dialogue_partner')}!"
                    )
                    break

                if resolution.get("trigger_combat") or st_state.get("detection_meter", 0) >= 100 or action.is_ambush:
                    result.detected = True
                    result.combat_triggered = True
                    result.trace_log.append(f"Turn {turn:02d} [ALERT 100 / AMBUSH] Seamless hand-off to Combat Simulator!")
                    if verbose:
                        safe_print("   ⚔️  Cover blown or ambush launched! Transitioning to Combat Simulator...")

                    # Call Combat Simulator seamless handoff
                    from tests.simulators.combat import CombatSimulator
                    combat_sim = CombatSimulator(base_user_id=user_id + 500)
                    combat_res = combat_sim.run_battle(
                        battle_id=mission_id,
                        scenario=scenario,
                        level=player_char.get("level", 3),
                        party_size=party_size,
                        seed=m_seed,
                        verbose=verbose
                    )
                    result.combat_outcome = combat_res.outcome
                    result.success = (combat_res.outcome == "victory" and objective_secured)
                    break

                # E. Check Mission Completion (Exit reached with objective)
                if objective_secured and current_sector.get("is_exit") and current_sector_idx == len(sectors) - 1:
                    result.success = True
                    result.trace_log.append(f"Turn {turn:02d} [SUCCESS] Objective secured and extraction reached clean!")
                    if verbose:
                        safe_print(f"   🎉 Mission Complete: Infiltration successful in {turn} turns!")
                    break

            # Finalize results
            final_st = get_session_stealth_state(session)
            result.final_meter = final_st.get("detection_meter", 0)
            result.final_stage = final_st.get("alert_level", "unaware")

        except Exception as e:
            result.error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            if verbose:
                safe_print(f"   ❌ Mission Crash: {result.error}")
            if fail_fast:
                raise

        finally:
            result.duration_ms = (time.perf_counter() - start_time) * 1000.0

        return result

    def run_batch(
        self,
        count: int = 10,
        scenario: str = "all",
        profile: str = "all",
        mission_type: str = "all",
        party_range: Tuple[int, int] = (1, 3),
        fail_fast: bool = False,
        verbose: bool = False
    ) -> StealthSimulationReport:
        """Executes a batch of simulated stealth missions."""
        report = StealthSimulationReport()
        supported_scens = [
            "fantasy", "cyberpunk", "scifi", "steampunk",
            "dark_fantasy", "isekai_fantasy", "high_school_drama",
            "slice_of_life", "anomalous_incursions", "urban_anomalies", "urban_fantasy",
        ]

        for i in range(1, count + 1):
            scen = self.rng.choice(supported_scens) if scenario == "all" else scenario
            prof = self.rng.choice(SUPPORTED_PROFILES) if profile == "all" else profile
            m_type = self.rng.choice(["heist", "evasion", "silent_takedown"]) if mission_type == "all" else mission_type
            p_size = self.rng.randint(party_range[0], party_range[1])

            res = self.run_mission(
                mission_id=i,
                scenario=scen,
                mission_type=m_type,
                profile=prof,
                party_size=p_size,
                fail_fast=fail_fast,
                verbose=verbose
            )
            report.add_result(res)

        return report
