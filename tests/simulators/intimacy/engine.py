from __future__ import annotations
"""
Simulation Engine for Hikayat Intimate Moment & Excitement Meter Simulator.

Orchestrates multi-turn intimate encounters:
1. Procedural session and participant generation.
2. Pre-turn intimacy and clothing resolution.
3. Blueprint-guided Actor AI action selection.
4. Fuzzing and perturbation injection.
5. Excitement meter progression and climax evaluation.
6. Progressive Codex disclosure and intimate ledger synchronization.
7. Refractory clock in-game time advancement.
8. Zero-tolerance invariant auditing and telemetry aggregation.
"""
import copy
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

import db
from mechanics.social.intimate_excitement import (
    compute_excitement_step,
    resolve_pre_turn_intimacy_and_clothing,
    check_and_resolve_refractory_clock,
    is_in_refractory_cooldown,
    build_intimate_choice_blueprints,
)
from mechanics.social.persona.intimacy.ledger import (
    record_intimate_event,
    compute_intimate_tracks_from_ledger,
)
from .actor_ai import (
    IntimacyActorAI,
    IntimacyAction,
    SUPPORTED_SCENARIOS,
)
from .fuzzer import (
    IntimacyFuzzer,
    SUPPORTED_PARTNER_CONFIGS,
    SUPPORTED_FUZZ_MODES,
)
from .auditor import (
    IntimacyInvariantAuditor,
    IntimacyViolation,
)

log = logging.getLogger("hikayat.simulator.intimacy")


@dataclass
class IntimacyJourneyResult:
    """Outcome and telemetry from a single simulated intimate journey."""
    journey_id: int
    scenario: str
    partner_config: str
    fuzz_mode: str
    turns: int = 0
    success: bool = True
    crashed: bool = False
    error_message: Optional[str] = None
    player_climaxes: int = 0
    partner_climaxes: int = 0
    multi_climaxes: int = 0
    premature_finishes: int = 0
    demands_resolved: int = 0
    affairs_detected: int = 0
    first_times_logged: int = 0
    violations: List[IntimacyViolation] = field(default_factory=list)
    turn_log: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class IntimacySimulationReport:
    """Consolidated telemetry and invariant audit report across multiple journeys."""
    total_journeys: int = 0
    successful_journeys: int = 0
    crashes: int = 0
    total_turns: int = 0
    avg_turns_per_journey: float = 0.0
    total_player_climaxes: int = 0
    total_partner_climaxes: int = 0
    total_multi_climaxes: int = 0
    total_premature_finishes: int = 0
    total_demands_resolved: int = 0
    total_affairs_detected: int = 0
    total_first_times_logged: int = 0
    total_violations: int = 0
    violations_by_category: Dict[str, int] = field(default_factory=dict)
    scenario_breakdown: Dict[str, Any] = field(default_factory=dict)
    partner_config_breakdown: Dict[str, Any] = field(default_factory=dict)
    journey_results: List[IntimacyJourneyResult] = field(default_factory=list)


class IntimacySimulator:
    """Simulation engine driving intimate encounters with exhaustive invariant checking."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        if db_path:
            import os
            os.environ["HIKAYAT_DB_PATH"] = db_path
        db.init_db()

    def run_simulation(
        self,
        scenario: str = "full_progression",
        partner_config: str = "hetero",
        fuzz_mode: str = "realistic_llm",
        max_turns: int = 12,
        seed: Optional[int] = None,
        journey_id: int = 1,
        is_secret_affair_test: bool = False,
        verbose: bool = False,
    ) -> IntimacyJourneyResult:
        """Runs a complete end-to-end simulated intimate encounter."""
        scenario_key = scenario.lower() if scenario in SUPPORTED_SCENARIOS else "full_progression"
        config_key = partner_config.lower() if partner_config in SUPPORTED_PARTNER_CONFIGS else "hetero"
        fuzz_key = fuzz_mode.lower() if fuzz_mode in SUPPORTED_FUZZ_MODES else "realistic_llm"

        rng = random.Random(seed)
        fuzzer = IntimacyFuzzer(fuzz_mode=fuzz_key, seed=seed)
        demand_branch = "exit" if (journey_id % 2 == 0 and scenario_key == "full_progression") else "rescue"
        actor_ai = IntimacyActorAI(scenario=scenario_key, seed=seed, test_demand_branch=demand_branch)
        auditor = IntimacyInvariantAuditor(partner_config=config_key, scenario=scenario_key)

        result = IntimacyJourneyResult(
            journey_id=journey_id,
            scenario=scenario_key,
            partner_config=config_key,
            fuzz_mode=fuzz_key,
        )

        try:
            # 1. Create Isolated Test Session
            session_doc, player_char, partner_contacts = fuzzer.create_test_session(
                partner_config=config_key,
                scenario=scenario_key,
                is_secret_affair_test=is_secret_affair_test,
            )
            sess_id = session_doc["id"]
            player_name = player_char["name"]
            primary_contact = partner_contacts[0]

            turn = 0
            is_active_encounter = True

            while turn < max_turns and is_active_encounter:
                turn += 1
                result.turns += 1

                # Snapshot pre-turn physical state
                pre_physical_state = copy.deepcopy(session_doc.get("physical_state", {}))

                # 2. Actor AI chooses action
                exc_res_prev = pre_physical_state.get("excitement", {})
                raw_action = actor_ai.choose_action(
                    turn=turn,
                    player_char=player_char,
                    partner_contacts=partner_contacts,
                    physical_state=pre_physical_state,
                    excitement_res=exc_res_prev,
                    location=session_doc.get("current_location", "Private Master Bedroom"),
                )

                # 3. Fuzzer mutates action
                target_contact = next(
                    (c for c in partner_contacts if c.get("name") == raw_action.target_npc),
                    primary_contact
                )
                action = fuzzer.fuzz_action(raw_action, turn=turn, target_contact=target_contact)

                # Handle NPC Interruption Scenario
                if action.action_type == "interrupted":
                    # External intrusion terminates intimacy cleanly
                    pre_physical_state["intimate_contact"] = "Interrupted by outside intrusion"
                    pre_physical_state.setdefault("actors", {}).setdefault(player_name, {})["composure"] = "flustered"
                    session_doc["physical_state"] = pre_physical_state
                    result.turn_log.append({
                        "turn": turn,
                        "action": action.action_text,
                        "type": "interrupted",
                        "status": "Session interrupted by outside intrusion",
                    })
                    break

                # 4. Resolve Pre-Turn Intimacy & Clothing
                pre_res = resolve_pre_turn_intimacy_and_clothing(
                    session=session_doc,
                    party=[(player_char, [])],
                    actions=[{"label": action.action_text, "action": action.action_text, "sub_intent": action.sub_intent, "target_npc": action.target_npc}],
                    new_partners=[c["name"] for c in partner_contacts],
                )

                # 5. Compute Excitement Step
                excitement_res = compute_excitement_step(
                    physical_state=session_doc["physical_state"],
                    action_str=action.action_text,
                    player_char=player_char,
                    partner_contact=primary_contact,
                    session=session_doc,
                    partner_contacts=partner_contacts,
                    sub_intent=action.sub_intent,
                    target_npc=action.target_npc,
                )

                # 6. Database Synchronization: Intimate Ledger & Progressive Disclosure
                act_type = excitement_res.get("act_type", "none")
                is_physical_act = act_type not in ("none", "foreplay_nongenital")

                if is_physical_act:
                    # Direction mapping
                    direction = "mutual"
                    if action.sub_intent in ("oral_give", "manual_give", "anal_give"):
                        direction = "give"
                    elif action.sub_intent in ("oral_receive", "manual_receive", "anal_receive"):
                        direction = "receive"

                    # Record in SQLite intimate_events table
                    target_npc_id = target_contact.get("npc_id", "0")
                    record_intimate_event(
                        session_id=sess_id,
                        character_id=player_char.get("id", "0"),
                        partner_id=target_npc_id,
                        partner_name=action.target_npc,
                        act_type="intercourse" if act_type == "penetrative" else ("oral" if "oral" in act_type else ("manual" if "manual" in act_type else "anal")),
                        direction=direction,
                        is_physical=True,
                        turn_number=turn,
                        event_origin="gameplay",
                        partner_role="group_participant" if len(partner_contacts) > 1 else "partner",
                        character_gender=player_char.get("gender", "Male"),
                        partner_gender=target_contact.get("gender", "Female"),
                        character_name=player_name,
                        narrative_summary=f"Turn {turn}: {action.action_text} [Participants: {', '.join([c['name'] for c in partner_contacts])}]",
                    )

                    # Virginity loss check for predetermined virgin NPC
                    target_app = target_contact.setdefault("appearance", {})
                    if act_type == "penetrative" and target_app.get("predetermined_intercourse") == "virgin":
                        target_app["predetermined_intercourse"] = "non_virgin"
                        target_app["intercourse_experience"] = "non_virgin"
                        target_app["had_first_time_with_player"] = True
                        mems = target_app.setdefault("intimate_memories", [])
                        mems.append(f"Shared her first time with {player_name} in intimate union.")
                        result.first_times_logged += 1

                    # Progressive Codex Disclosure Unlocking
                    target_app["demeanor_revealed"] = True
                    target_app["dynamic_revealed"] = True
                    target_app["sensitive_spots_revealed"] = True
                    target_app["turn_ons_revealed"] = True
                    if "oral" in act_type:
                        target_app["oral_revealed"] = True
                        target_app["underwear_revealed"] = True
                    elif "manual" in act_type:
                        target_app["manual_revealed"] = True
                    elif act_type == "penetrative":
                        target_app["intercourse_revealed"] = True
                        target_app["underwear_revealed"] = True
                        target_app["intimate_revealed"] = True

                    db.upsert_contact(
                        session_id=sess_id,
                        npc_id=target_npc_id,
                        name=action.target_npc,
                        character_id=player_char.get("id", 0),
                        appearance=target_app,
                    )

                # Check secret affair
                if is_secret_affair_test:
                    with db.get_conn() as conn:
                        aff_count = conn.execute(
                            "SELECT count(*) FROM intimate_events WHERE session_id = ? AND is_secret_affair = 1",
                            (sess_id,)
                        ).fetchone()[0]
                        if aff_count > 0:
                            result.affairs_detected = aff_count

                post_physical_state = session_doc["physical_state"]

                # Telemetry Tracking
                post_actors_dict = post_physical_state.get("excitement", {}).get("actors", {})
                pre_actors_dict = pre_physical_state.get("excitement", {}).get("actors", {})

                p_post_climaxes = post_actors_dict.get(player_name, {}).get("climaxes_count", 0)
                p_pre_climaxes = pre_actors_dict.get(player_name, {}).get("climaxes_count", 0)
                if p_post_climaxes > p_pre_climaxes:
                    delta_p_climaxes = p_post_climaxes - p_pre_climaxes
                    result.player_climaxes += delta_p_climaxes
                    if p_post_climaxes > 1:
                        result.multi_climaxes += max(0, p_post_climaxes - max(1, p_pre_climaxes))

                for c in partner_contacts:
                    c_name = c.get("name")
                    c_post_climaxes = post_actors_dict.get(c_name, {}).get("climaxes_count", 0)
                    c_pre_climaxes = pre_actors_dict.get(c_name, {}).get("climaxes_count", 0)
                    if c_post_climaxes > c_pre_climaxes:
                        delta_c_climaxes = c_post_climaxes - c_pre_climaxes
                        result.partner_climaxes += delta_c_climaxes
                        if c_post_climaxes > 1:
                            result.multi_climaxes += max(0, c_post_climaxes - max(1, c_pre_climaxes))

                pre_premature = bool(pre_physical_state.get("excitement", {}).get("premature_finish", False))
                post_premature = bool(excitement_res.get("premature_finish", False))
                if post_premature and not pre_premature:
                    result.premature_finishes += 1

                if action.metadata.get("is_demand_rescue") or action.metadata.get("demand_exit_penalty_expected"):
                    result.demands_resolved += 1

                # 7. Invariant Audit
                turn_blueprints = build_intimate_choice_blueprints(
                    partner_name=primary_contact["name"],
                    last_act=act_type,
                    player_meter=int(excitement_res.get("player_meter", 0)),
                    partner_meter=int(excitement_res.get("partner_meter", 0)),
                    player_climaxed=bool(excitement_res.get("player_climaxed")),
                    partner_climaxed=bool(excitement_res.get("partner_climaxed")),
                    partner_actors=[
                        {"name": c.get("name"), "meter": pm.get("meter", 0), "climaxed": pm.get("climaxed", False)}
                        for c, pm in zip(partner_contacts, excitement_res.get("partner_meters", []))
                    ],
                )

                turn_violations = auditor.audit_turn(
                    turn=turn,
                    session_id=sess_id,
                    player_char=player_char,
                    partner_contacts=partner_contacts,
                    action=action,
                    pre_physical_state=pre_physical_state,
                    post_physical_state=post_physical_state,
                    excitement_res=excitement_res,
                    blueprints=turn_blueprints,
                )

                result.violations.extend(turn_violations)

                # Log turn summary
                result.turn_log.append({
                    "turn": turn,
                    "action": action.action_text,
                    "act_type": act_type,
                    "player_meter": excitement_res.get("player_meter", 0),
                    "player_delta": excitement_res.get("player_delta", 0),
                    "partner_meter": excitement_res.get("partner_meter", 0),
                    "partner_delta": excitement_res.get("partner_delta", 0),
                    "partner_meters": excitement_res.get("partner_meters", []),
                    "violations": len(turn_violations),
                })

                # Voluntary disengagement or aftercare conclusion
                if action.is_disengagement or (action.action_type == "aftercare" and turn >= 4):
                    is_active_encounter = False

            # 8. Post-Session: Clock Fast-Forward Phase (Refractory Cooldown Expiration)
            target_refr = post_physical_state.get("excitement", {}).get("refractory_until_minute")
            if target_refr:
                # Advance clock 5 minutes past target_refr, normalizing day and minute
                target_abs = target_refr + 5
                session_doc["current_day"] = target_abs // 1440
                session_doc["current_minute"] = target_abs % 1440
                refr_cleared, toast = check_and_resolve_refractory_clock(session_doc, post_physical_state)
                in_refr_now, _ = is_in_refractory_cooldown(session_doc, post_physical_state)
                if in_refr_now:
                    result.violations.append(IntimacyViolation(
                        turn=turn,
                        category="REFRACTORY_CLOCK_NOT_CLEARED",
                        message=f"In-game clock was advanced past cooldown duration (target_refr={target_refr}), but refractory status failed to clear.",
                        actor_name=player_name,
                        state_dump={"current_minute": session_doc["current_minute"], "excitement": post_physical_state["excitement"]}
                    ))

            # 9. Final Journey Invariant Audit (SQLite ledger & social graph)
            final_violations = auditor.audit_final_journey(
                session_id=sess_id,
                player_char=player_char,
                partner_contacts=partner_contacts,
                is_secret_affair_test=is_secret_affair_test,
            )
            result.violations.extend(final_violations)

            result.success = len(result.violations) == 0

        except Exception as e:
            log.exception(f"Unhandled exception during intimacy simulation: {e}")
            result.crashed = True
            result.success = False
            result.error_message = str(e)

        return result

    def run_batch(
        self,
        num_simulations: int = 10,
        scenario: str = "all",
        partner_config: str = "all",
        fuzz_mode: str = "realistic_llm",
        seed: Optional[int] = None,
        fail_fast: bool = False,
        verbose: bool = False,
    ) -> IntimacySimulationReport:
        """Runs a batch of simulations across scenarios and partner configurations."""
        report = IntimacySimulationReport()
        rng = random.Random(seed)

        scenarios_pool = (
            SUPPORTED_SCENARIOS
            if scenario.lower() == "all"
            else [s.strip().lower() for s in scenario.split(",") if s.strip().lower() in SUPPORTED_SCENARIOS]
        ) or ["full_progression"]
        configs_pool = (
            SUPPORTED_PARTNER_CONFIGS
            if partner_config.lower() == "all"
            else [c.strip().lower() for c in partner_config.split(",") if c.strip().lower() in SUPPORTED_PARTNER_CONFIGS]
        ) or ["hetero"]

        for i in range(1, num_simulations + 1):
            chosen_scenario = scenarios_pool[(i - 1) % len(scenarios_pool)]
            chosen_config = configs_pool[(i - 1) % len(configs_pool)]
            sub_seed = rng.randint(1000, 999999) if seed is not None else None
            is_affair = (i % 3 == 0)

            res = self.run_simulation(
                scenario=chosen_scenario,
                partner_config=chosen_config,
                fuzz_mode=fuzz_mode,
                seed=sub_seed,
                journey_id=i,
                is_secret_affair_test=is_affair,
                verbose=verbose,
            )

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

            # Scenario breakdown
            s_entry = report.scenario_breakdown.setdefault(chosen_scenario, {"journeys": 0, "successful": 0})
            s_entry["journeys"] += 1
            if res.success:
                s_entry["successful"] += 1

            # Config breakdown
            c_entry = report.partner_config_breakdown.setdefault(chosen_config, {"journeys": 0, "successful": 0})
            c_entry["journeys"] += 1
            if res.success:
                c_entry["successful"] += 1

            report.journey_results.append(res)

            if fail_fast and (not res.success or res.crashed):
                break

        if report.total_journeys > 0:
            report.avg_turns_per_journey = report.total_turns / report.total_journeys

        return report
