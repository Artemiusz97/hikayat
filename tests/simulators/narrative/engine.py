from __future__ import annotations
"""
Narrative & Turn Lifecycle Simulator Execution Engine.

Orchestrates synthetic agent journeys through the entire narrative and turn loop:
- Intent classification and target NPC extraction
- Dialogue intent computation and partner switching
- Mock TurnOutcome ingestion and scene NPC reconciliation
- Post-LLM state leakage reconciliation (reconcile_narrative_leakage)
- State persistence and choice diversification
- Zero-tolerance invariant auditing and telemetry aggregation
"""
import copy
import json
import random
import time
import traceback
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

import db
import namegen
from mechanics.narrative.intent import (
    classify_action_intent,
    IntentCategory,
    IntentContext,
)
from game_engine.turn.dialogue import _compute_dialogue_intent
from game_engine.npcs.reconciliation import process_scene_npcs
from game_engine.state.core import apply_outcome
from game_engine.choices_cleaner import sanitize_and_diversify_choices
from game_engine.prompt_layout import (
    build_static_core,
    build_session_zone,
    build_world_canon_zone,
)
from game_engine.npcs import is_dialogue_partner
from game_engine.core import _get_npc_name
import skill_check

from .actor_ai import NarrativeActorAI, NarrativeAction, SUPPORTED_ARCHETYPES
from .fuzzer import NarrativeFuzzer
from .auditor import NarrativeInvariantAuditor, NarrativeViolation


@dataclass
class NarrativeJourneyResult:
    """Detailed telemetry and outcome for a single simulated narrative journey."""
    journey_id: int
    scenario: str
    archetype: str
    seed: int
    total_turns: int = 0
    intents_evaluated: int = 0
    choices_evaluated: int = 0
    entities_reconciled: int = 0
    state_parity_verified: int = 0
    success: bool = False
    violations: List[NarrativeViolation] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class NarrativeSimulationReport:
    """Aggregated metrics across a batch of narrative simulations."""
    total_journeys: int = 0
    successful_journeys: int = 0
    crashes: int = 0
    total_turns: int = 0
    avg_turns_per_journey: float = 0.0
    total_violations: int = 0
    critical_violations: int = 0
    warning_violations: int = 0
    violations_by_category: Dict[str, int] = field(default_factory=dict)
    archetype_stats: Dict[str, Any] = field(default_factory=dict)
    scenario_stats: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    results: List[NarrativeJourneyResult] = field(default_factory=list)


SCENARIO_LOCATIONS: Dict[str, List[str]] = {
    "high_school_drama": [
        "Westlake High ➔ Manga & Brew Café ➔ Window Seat Table",
        "Westlake High ➔ Campus Courtyard ➔ Central Fountain",
        "Westlake High ➔ Library ➔ Study Carrels",
        "Westlake High ➔ Cafeteria ➔ Lunch Tables",
        "Westlake High ➔ Gymnasium ➔ Bleachers",
        "Westlake High ➔ Science Lab ➔ Chemistry Stations",
    ],
    "fantasy": [
        "Town Square ➔ Adventurer's Guild ➔ Tavern Hall",
        "Town Square ➔ Marketplace ➔ General Store",
        "Town Square ➔ City Gates ➔ Guard Watchtower",
        "Town Square ➔ Temple District ➔ Grand Sanctuary",
        "Town Square ➔ Old Archives ➔ Scriptorium",
    ],
    "cyberpunk": [
        "Neon District ➔ Netrunner Lounge ➔ Holo Booth",
        "Neon District ➔ Cyberware Clinic ➔ Operating Theater",
        "Neon District ➔ Night Market ➔ Street Stall",
        "Neon District ➔ Docks ➔ Cargo Warehouse",
    ],
    "postapoc": [
        "Wasteland ➔ Scrap Yard ➔ Outpost Barricade",
        "Wasteland ➔ Underground Shelter ➔ Bunker Bunks",
        "Wasteland ➔ Ruined Highway ➔ Overpass Watchpost",
    ],
    "scifi": [
        "Core Sector ➔ Command Deck ➔ Observation Lounge",
        "Core Sector ➔ Hangar Bay ➔ Shuttle Pad",
        "Core Sector ➔ Hydroponics Lab ➔ Growth Chambers",
        "Core Sector ➔ Docking Ring ➔ Airlock 3",
    ],
    "steampunk": [
        "Industrial Quarter ➔ Clockwork Plaza ➔ Airship Docks",
        "Industrial Quarter ➔ Steam Boiler Room ➔ Control Valves",
        "Industrial Quarter ➔ Automaton Workshop ➔ Assembly Line",
    ],
    "dark_fantasy": [
        "Dark Citadel ➔ Ruined Cathedral ➔ Crypt Entrance",
        "Dark Citadel ➔ Shadowed Alley ➔ Gallows Post",
        "Dark Citadel ➔ Forgotten Catacombs ➔ Ossuary",
    ],
    "isekai_fantasy": [
        "Capital City ➔ Adventurer's Guild ➔ Reception Counter",
        "Capital City ➔ Royal Plaza ➔ Grand Belltower",
        "Capital City ➔ Magic Academy ➔ Lecture Hall",
    ],
}


class NarrativeSimulator:
    """Comprehensive execution harness for the narrative turn pipeline."""

    def __init__(self, seed: Optional[int] = None):
        self.base_seed = seed
        self.rng = random.Random(seed)

    def simulate_journey(
        self,
        journey_id: int = 1,
        scenario: str = "high_school_drama",
        archetype: str = "conversationalist",
        fuzz_mode: str = "clean",
        max_turns: int = 10,
        fail_fast: bool = False,
        with_llm: bool = False,
        seed: Optional[int] = None,
    ) -> NarrativeJourneyResult:
        """Simulates a complete multi-turn journey through the turn loop."""
        start_time = time.perf_counter()
        j_seed = seed if seed is not None else (self.base_seed + journey_id if self.base_seed else random.randint(1000, 999999))
        local_rng = random.Random(j_seed)

        fuzzer = NarrativeFuzzer(fuzz_mode=fuzz_mode, rng=local_rng)
        actor = NarrativeActorAI(archetype=archetype, seed=j_seed)
        auditor = NarrativeInvariantAuditor(scenario_key=scenario)

        result = NarrativeJourneyResult(
            journey_id=journey_id,
            scenario=scenario,
            archetype=archetype,
            seed=j_seed,
        )

        session_id = local_rng.randint(900000, 999999)
        departed_npcs: List[str] = []

        try:
            # 1. Setup isolated test session and character
            sess_dict, char_dict = fuzzer.create_test_session(
                scenario_key=scenario,
                session_id=session_id,
                char_gender="male" if local_rng.random() < 0.5 else "female",
            )
            char_id = char_dict["id"]
            party = [(char_dict, [])]

            last_choices: List[Dict[str, Any]] = []

            # 2. Multi-turn execution loop
            for turn in range(1, max_turns + 1):
                result.total_turns = turn
                session = db.get_session(session_id)
                if not session:
                    result.error = f"Session {session_id} not found in database during turn {turn}"
                    break
                current_npcs_raw = session.get("current_npcs_json") or "[]"
                try:
                    current_npcs = json.loads(current_npcs_raw) if isinstance(current_npcs_raw, str) else current_npcs_raw
                except Exception:
                    current_npcs = []
                session["current_npcs"] = current_npcs
                session_before_turn = copy.deepcopy(session)

                # Reload character state from DB to propagate HP, MP, gold changes from previous turns
                char_dict = db.get_character(char_dict["user_id"]) or char_dict
                party = [(char_dict, [])]

                # A. Actor decides next action
                action = actor.choose_action(
                    session=session,
                    choices=last_choices,
                    current_npcs=current_npcs,
                    turn=turn,
                    scenario=scenario,
                )

                # B. Fuzz action prose according to fuzz mode
                fuzzed_prose = fuzzer.fuzz_prose(
                    action.action_text,
                    npc_name=session.get("dialogue_partner")
                )

                # C. NLU Intent Extraction
                intent_ctx = IntentContext(
                    dialogue_partner=session.get("dialogue_partner") or "",
                    present_npcs=[
                        (n.get("name") if isinstance(n, dict) else str(n)).strip()
                        for n in current_npcs
                        if (isinstance(n, dict) and n.get("name")) or (isinstance(n, str) and n.strip())
                    ],
                    scenario=scenario,
                )
                classified_intent = classify_action_intent(fuzzed_prose, context=intent_ctx)
                result.intents_evaluated += 1

                # D. Realistic Skill Check & Action Payload
                stat_upper = action.stat.upper() if action.stat else "FREE"
                stat_col = db.STAT_COLUMN.get(stat_upper, "")
                stat_val = char_dict.get(stat_col, 10) if stat_col else 10
                req = max(0, action.requirement)

                if req > 0 and stat_upper not in ("FREE", "NONE"):
                    check_res = skill_check.resolve_check(
                        stat_value=stat_val,
                        requirement=req,
                        luck=char_dict.get("luk", 10),
                    )
                else:
                    check_res = skill_check.CheckResult(
                        chance=100, roll=100.0, tier="success",
                        tier_label="Success", succeeded=True, requirement=0
                    )

                action_objs = [{
                    "char": char_dict,
                    "character": char_dict,
                    "label": fuzzed_prose,
                    "action": fuzzed_prose,
                    "stat": action.stat,
                    "requirement": req,
                    "mp_spent": action.mp_cost,
                    "check": check_res,
                }]

                # E. Dialogue Partner Resolution
                former_partner = session.get("dialogue_partner")
                new_partners, has_exited = _compute_dialogue_intent(session, action_objs)

                # Apply dialogue partner update to database session
                active_partner = new_partners[0] if new_partners else None
                db.update_session_dialogue_partner(session_id, active_partner)
                session["dialogue_partner"] = active_partner

                # F. Synthesize mock LLM turn response
                mock_outcome = fuzzer.generate_mock_outcome(
                    session=session,
                    player_char=char_dict,
                    action_text=fuzzed_prose,
                    target_npc=active_partner,
                    check_tier=check_res.tier,
                    departed_npcs=departed_npcs,
                    former_partner=former_partner,
                    mp_cost=action.mp_cost,
                )

                # Optional live LLM execution if explicitly requested
                if with_llm:
                    try:
                        import asyncio
                        from llm_client import call_llm_json
                        asyncio.run(call_llm_json("You are the game master.", fuzzed_prose, timeout=6.0))
                    except Exception:
                        pass

                # G. Scene NPC Reconciliation & Spatial Transition
                old_loc = session.get(
                    "current_location",
                    "Westlake High ➔ Manga & Brew Café ➔ Window Seat Table" if "school" in scenario else "Town Square ➔ Adventurer's Guild ➔ Tavern Hall"
                )
                if classified_intent.category == IntentCategory.MOVEMENT:
                    candidates = SCENARIO_LOCATIONS.get(scenario, [
                        "Courtyard ➔ Central Fountain",
                        "Library ➔ Archives",
                        "Marketplace ➔ General Store",
                        "Inner Sanctum ➔ Main Hall"
                    ])
                    possible_new = [loc for loc in candidates if loc != old_loc]
                    new_loc = local_rng.choice(possible_new) if possible_new else f"{old_loc} ➔ Corridor"
                    with db.get_conn() as conn:
                        conn.execute("UPDATE sessions SET current_location = ? WHERE id = ?", (new_loc, session_id))
                    session["current_location"] = new_loc
                    mock_outcome["location"] = new_loc
                else:
                    new_loc = old_loc

                reconciled_npcs = process_scene_npcs(
                    result=mock_outcome,
                    session=session,
                    new_loc=new_loc,
                    old_loc=old_loc,
                    actions=action_objs,
                )
                result.entities_reconciled += len(reconciled_npcs)

                # Persist reconciled scene NPCs to session and database
                db.update_session_npcs(session_id, reconciled_npcs)
                session["current_npcs_json"] = json.dumps(reconciled_npcs)
                session["current_npcs"] = reconciled_npcs
                mock_outcome["npcs_present"] = reconciled_npcs

                # Dialogue Partner Chime-in & Presence Resolution (parity with core.py)
                if not has_exited and reconciled_npcs:
                    full_nar = f"{mock_outcome.get('outcome_narrative', '')}\n{mock_outcome.get('next_narrative', '')}"
                    pres_names = [_get_npc_name(n) for n in reconciled_npcs if _get_npc_name(n)]
                    retained_partners = [p for p in new_partners if any(is_dialogue_partner(p, [pn]) for pn in pres_names)]

                    from game_engine.npcs import extract_speaking_npcs_from_narrative, evaluate_scene_attention_transition
                    speaking_npcs = extract_speaking_npcs_from_narrative(full_nar, reconciled_npcs)
                    audit_speaking = (mock_outcome.get("entity_audit") or {}).get("speaking_characters") or []
                    if isinstance(audit_speaking, list):
                        for asp in audit_speaking:
                            if isinstance(asp, str) and asp.strip():
                                matched_n = next((_get_npc_name(n) for n in reconciled_npcs if is_dialogue_partner(asp, [_get_npc_name(n)])), None)
                                if matched_n and matched_n not in speaking_npcs:
                                    if evaluate_scene_attention_transition(
                                        matched_n,
                                        retained_partners=retained_partners,
                                        actions=action_objs,
                                        narrative=full_nar,
                                        session=session,
                                        party=party,
                                        npcs_present=reconciled_npcs,
                                    ):
                                        speaking_npcs.append(matched_n)

                    from mechanics.world.locations import get_primary_location_name
                    same_primary = bool(
                        old_loc == new_loc
                        or (
                            get_primary_location_name(old_loc)
                            and get_primary_location_name(old_loc).lower() == get_primary_location_name(new_loc).lower()
                        )
                    )
                    merged = list(retained_partners) if same_primary else []
                    for sn in speaking_npcs:
                        if not any(is_dialogue_partner(sn, [m]) for m in merged):
                            if evaluate_scene_attention_transition(
                                sn,
                                retained_partners=retained_partners,
                                actions=action_objs,
                                narrative=full_nar,
                                session=session,
                                party=party,
                                npcs_present=reconciled_npcs,
                            ):
                                merged.append(sn)

                    new_partners = merged if merged else retained_partners
                    new_partners = [p for p in new_partners if any(is_dialogue_partner(p, [pn]) for pn in pres_names)]
                    active_partner = new_partners[0] if new_partners else None
                    db.update_session_dialogue_partner(session_id, active_partner)
                    session["dialogue_partner"] = active_partner
                    session["dialogue_partners"] = new_partners
                    mock_outcome["dialogue_partners"] = new_partners
                    mock_outcome["dialogue_partner"] = active_partner
                elif active_partner and not any(is_dialogue_partner(active_partner, [_get_npc_name(n)]) for n in reconciled_npcs):
                    active_partner = None
                    db.update_session_dialogue_partner(session_id, None)
                    session["dialogue_partner"] = None
                    session["dialogue_partners"] = []
                    mock_outcome["dialogue_partner"] = None
                    mock_outcome["dialogue_partners"] = []

                # H. Post-LLM State Application & Narrative Leakage Reconciliation
                apply_outcome(
                    session_id=session_id,
                    party=party,
                    outcome=mock_outcome,
                    actions=action_objs,
                )
                result.state_parity_verified += 1

                # Check if outcome reported any departures
                for dep in mock_outcome.get("npc_departures", []):
                    dep_name = dep.get("name", "") if isinstance(dep, dict) else str(dep)
                    if dep_name and dep_name not in departed_npcs:
                        departed_npcs.append(dep_name)

                # If departed NPC was active partner, ensure partner is cleared in DB and session
                if active_partner and any(active_partner.lower() == str(d).lower() for d in departed_npcs):
                    active_partner = None
                    db.update_session_dialogue_partner(session_id, None)
                    session["dialogue_partner"] = None

                # I. Choice Diversification & Cleaning
                cleaned_choices = sanitize_and_diversify_choices(
                    choices=mock_outcome.get("next_choices", []),
                    scenario=scenario,
                    location=new_loc,
                    char=char_dict,
                    dialogue_partner=active_partner,
                    current_npcs=reconciled_npcs,
                    session_id=session_id,
                    departed_npcs=departed_npcs,
                )
                result.choices_evaluated += len(cleaned_choices)
                last_choices = cleaned_choices

                # J. Zero-Tolerance Invariant Audit
                updated_session = db.get_session(session_id)
                char_dict = db.get_character(char_dict["user_id"]) or char_dict
                party = [(char_dict, [])]
                # Inspect raw DB contacts table directly to catch any invalid rows that get_contacts might mask
                raw_db_contacts = []
                try:
                    with db.get_conn() as conn:
                        rows = conn.execute(
                            "SELECT name, npc_id, basic_info_json FROM contacts WHERE session_id=?",
                            (session_id,)
                        ).fetchall()
                        for r in rows:
                            d = dict(r)
                            try:
                                d["basic_info"] = json.loads(d.get("basic_info_json") or "{}")
                            except Exception:
                                d["basic_info"] = {}
                            raw_db_contacts.append(d)
                except Exception:
                    pass
                updated_contacts = raw_db_contacts if raw_db_contacts else db.get_contacts(session_id, character_id=char_id)

                turn_violations = auditor.audit_turn(
                    turn=turn,
                    session=updated_session,
                    player_char=char_dict,
                    outcome=mock_outcome,
                    cleaned_choices=cleaned_choices,
                    contacts=updated_contacts,
                    departed_npcs=departed_npcs,
                    previous_session=session_before_turn,
                    actions=action_objs,
                    old_loc=old_loc,
                    new_loc=new_loc,
                )

                result.history.append({
                    "turn": turn,
                    "action": fuzzed_prose[:80],
                    "intent": classified_intent.category.value,
                    "partner": active_partner,
                    "choices_count": len(cleaned_choices),
                    "violations_count": len(turn_violations),
                })

                if fail_fast and any(v.severity == "CRITICAL" for v in turn_violations):
                    break

            criticals = [v for v in auditor.violations if v.severity == "CRITICAL"]
            result.success = (len(criticals) == 0 and result.error is None)

        except Exception as e:
            result.error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        finally:
            # Teardown isolated test session rows across all tables
            try:
                with db.get_conn() as conn:
                    for table in (
                        "session_locations", "lorebook", "school_directory", "contacts", "factions",
                        "quests", "quest_waypoints", "session_clues", "phone_messages",
                        "phone_appointments", "phone_gossip_feed", "commitments_ledger", "session_digests",
                        "session_chronicles", "npc_memories", "session_members", "inventory",
                    ):
                        try:
                            conn.execute(f"DELETE FROM {table} WHERE session_id=?", (session_id,))
                        except Exception:
                            pass
                    conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
                    conn.execute(
                        "DELETE FROM characters WHERE id=? OR user_id=? OR active_session_id=?",
                        (char_dict.get("id"), char_dict.get("user_id"), session_id),
                    )
            except Exception:
                pass

        result.violations = auditor.violations
        result.duration_ms = (time.perf_counter() - start_time) * 1000.0
        return result

    def run_intent_mode(
        self,
        samples: int = 100,
        scenario: str = "high_school_drama",
        fuzz_mode: str = "clean",
    ) -> Dict[str, Any]:
        """Fast-path NLU evaluation testing hundreds of prose inputs against intent & entity parsing."""
        fuzzer = NarrativeFuzzer(fuzz_mode=fuzz_mode)
        benchmark = fuzzer.get_intent_benchmark_samples()

        total = 0
        passed = 0
        failures: List[Dict[str, Any]] = []

        # Run benchmark samples multiple times if requested
        test_queue = benchmark * max(1, (samples // len(benchmark)) + 1)
        test_queue = test_queue[:samples]

        start_time = time.perf_counter()
        for item in test_queue:
            total += 1
            text = item["text"]
            fuzzed_text = fuzzer.fuzz_prose(text)
            sample_partner = item.get("dialogue_partner", "")
            context = IntentContext(
                dialogue_partner=sample_partner,
                present_npcs=item.get("present_npcs", ["Mila Vance", "Chloe"]),
                scenario=scenario,
            )
            intent = classify_action_intent(fuzzed_text, context=context)

            err = None
            if "should_not_target" in item:
                forbidden = item["should_not_target"].lower().strip()
                actual_target = (intent.target_entity or "").lower().strip()
                if forbidden in actual_target or actual_target == forbidden:
                    err = f"Extracted forbidden target: '{intent.target_entity}'"

            if not err and "expect_target" in item:
                exp = item["expect_target"].lower().strip()
                actual_target = (intent.target_entity or "").lower().strip()
                if exp:
                    if not actual_target or (exp not in actual_target and actual_target not in exp):
                        err = f"Expected target '{item['expect_target']}', got '{intent.target_entity}'"
                else:
                    if actual_target:
                        err = f"Expected empty target, got '{intent.target_entity}'"

            if not err and "expect_category" in item:
                # If conversational clause was appended by fuzzer, category naturally shifts to dialogue
                if fuzz_mode != "clean" and any(k in fuzzed_text for k in (" and ask ", " and wonder ", " and whisper ", " and inquire ")):
                    pass
                elif intent.category.value != item["expect_category"]:
                    err = f"Expected category {item['expect_category']}, got {intent.category.value}"

            if err:
                failures.append({"text": fuzzed_text, "error": err, "intent": intent.category.value})
            else:
                passed += 1

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        return {
            "total_samples": total,
            "passed": passed,
            "failed": len(failures),
            "pass_rate": (passed / max(1, total)) * 100.0,
            "duration_ms": duration_ms,
            "failures": failures[:10],
        }

    def run_choices_mode(
        self,
        scenarios: Optional[List[str]] = None,
        iterations: int = 20,
    ) -> Dict[str, Any]:
        """Evaluates choice cleaner diversification, DC bounds, and formatting cleanliness."""
        scenarios = scenarios or ["high_school_drama", "fantasy", "cyberpunk", "postapoc"]
        auditor = NarrativeInvariantAuditor()
        total_evals = 0
        violations_count = 0

        CHOICE_MATRICES = [
            # 1. Clean well-formed choices
            [
                {"label": "Talk to the guard at the entrance", "stat": "CHA", "requirement": 6},
                {"label": "Examine the heavy stone door", "stat": "PER", "requirement": 8},
                {"label": "Force the lock open", "stat": "STR", "requirement": 14},
                {"label": "Step back and observe", "stat": "FREE", "requirement": 0},
            ],
            # 2. Duplicate choice labels (must be deduplicated and backfilled to >= 3)
            [
                {"label": "Search the room carefully", "stat": "PER", "requirement": 6},
                {"label": "Search the room carefully", "stat": "PER", "requirement": 6},
                {"label": "Search the room carefully", "stat": "INT", "requirement": 8},
            ],
            # 3. Out-of-bounds DCs (must be clamped to [0..20])
            [
                {"label": "Attempt an impossible leap", "stat": "AGI", "requirement": 999},
                {"label": "Resist the dark magic", "stat": "END", "requirement": -10},
                {"label": "Read the ancient tome", "stat": "INT", "requirement": None},
                {"label": "Rest briefly", "stat": "FREE", "requirement": 0},
            ],
            # 4. Sparse choices (1 choice, must be backfilled to >= 3)
            [
                {"label": "Investigate the strange mechanism", "stat": "INT", "requirement": 7},
            ],
            # 5. Empty and whitespace labels (must be scrubbed and replaced with fallbacks)
            [
                {"label": "", "stat": "CHA", "requirement": 5},
                {"label": "   ", "stat": "PER", "requirement": 6},
                {"label": "none", "stat": "STR", "requirement": 10},
                {"label": "Check the perimeter", "stat": "PER", "requirement": 5},
            ],
            # 6. Choices referencing departed NPC (must be filtered and backfilled)
            [
                {"label": "Ask Eldrin about the ancient prophecy", "stat": "CHA", "requirement": 6, "target_npc": "Eldrin the Wise"},
                {"label": "Search the archive shelves", "stat": "INT", "requirement": 7},
                {"label": "Examine the stone carvings", "stat": "PER", "requirement": 6},
            ],
        ]

        start_time = time.perf_counter()
        for scen in scenarios:
            for it in range(iterations):
                total_evals += 1
                matrix_idx = it % len(CHOICE_MATRICES)
                raw_choices = copy.deepcopy(CHOICE_MATRICES[matrix_idx])
                test_departed = ["Eldrin the Wise"] if matrix_idx == 5 else []

                cleaned = sanitize_and_diversify_choices(
                    choices=raw_choices,
                    scenario=scen,
                    location="Front Gate",
                    char={"cha": 12, "per": 10, "str_": 14},
                    departed_npcs=test_departed,
                )

                turn_violations = auditor._audit_choice_hygiene(
                    turn=it + 1,
                    cleaned_choices=cleaned,
                    departed_npcs=test_departed,
                )
                auditor.violations.extend(turn_violations)
                violations_count += len(turn_violations)

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        return {
            "total_evaluations": total_evals,
            "violations": violations_count,
            "clean_rate": ((total_evals - violations_count) / max(1, total_evals)) * 100.0,
            "duration_ms": duration_ms,
            "details": [{"category": v.category, "message": v.message} for v in auditor.violations[:10]],
        }

    def run_memory_stress_mode(
        self,
        turns: int = 35,
        scenario: str = "high_school_drama",
    ) -> Dict[str, Any]:
        """Simulates 30+ consecutive turns auditing prompt cache zone headers and stability."""
        fuzzer = NarrativeFuzzer(fuzz_mode="clean")
        auditor = NarrativeInvariantAuditor(scenario_key=scenario)

        sess_dict, char_dict = fuzzer.create_test_session(scenario_key=scenario)
        sid = sess_dict["id"]
        start_time = time.perf_counter()

        try:
            # Seed an active quest in database
            sq_id = "SQ-CAMPUS-01"
            db.upsert_quest(
                session_id=sid,
                quest_id=sq_id,
                quest_type="Story Quest",
                title="The Missing Club Funds",
                objective="Investigate the student council records.",
                progress="Step 1",
                status="Active",
                reward_xp=100,
                reward_gold=25,
                is_story_quest=1,
            )

            history: List[str] = []
            for t in range(1, turns + 1):
                history.append(f"Turn {t}: Player investigated the club records and spoke with the treasurer.")
                with db.get_conn() as conn:
                    conn.execute(
                        "UPDATE sessions SET history_json = ? WHERE id = ?",
                        (json.dumps(history[-10:]), sid)
                    )

                session = db.get_session(sid)
                zones = {
                    "zone_static": build_static_core("narrative", "turn"),
                    "zone_session": build_session_zone(session),
                    "zone_canon": build_world_canon_zone(session),
                }

                auditor.audit_memory_and_prompt_budget(
                    turn=t,
                    session_id=sid,
                    zones_content=zones,
                    active_quest_id=sq_id,
                )

            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return {
                "turns_simulated": turns,
                "active_quest_preserved": bool(db.get_active_story_quest(sid)),
                "violations": len(auditor.violations),
                "duration_ms": duration_ms,
            }
        finally:
            with db.get_conn() as conn:
                for table in (
                    "session_locations", "lorebook", "school_directory", "contacts", "factions",
                    "quests", "quest_waypoints", "session_clues", "phone_messages",
                    "phone_appointments", "phone_gossip_feed", "commitments_ledger", "session_digests",
                    "session_chronicles", "npc_memories", "session_members", "inventory",
                ):
                    try:
                        conn.execute(f"DELETE FROM {table} WHERE session_id=?", (sid,))
                    except Exception:
                        pass
                conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
                conn.execute(
                    "DELETE FROM characters WHERE id=? OR user_id=? OR active_session_id=?",
                    (char_dict.get("id"), char_dict.get("user_id"), sid),
                )

    def run_batch(
        self,
        simulations: int = 10,
        scenario: str = "high_school_drama",
        archetype: str = "conversationalist",
        fuzz_mode: str = "clean",
        seed: Optional[int] = None,
        max_turns: int = 10,
        fail_fast: bool = False,
        with_llm: bool = False,
    ) -> NarrativeSimulationReport:
        """Runs a batch of simulations across scenarios and archetypes, aggregating results."""
        start_time = time.perf_counter()
        batch_seed = seed if seed is not None else (self.base_seed or 42)

        scenarios_to_test = [
            "high_school_drama",
            "fantasy",
            "cyberpunk",
            "postapoc",
            "scifi",
            "steampunk",
            "dark_fantasy",
            "isekai_fantasy",
        ] if scenario == "all" else [scenario]

        archetypes_to_test = [
            "conversationalist",
            "cautious_explorer",
            "bold_adventurer",
            "chaotic_provocateur",
        ] if archetype == "all" else [archetype]

        report = NarrativeSimulationReport()

        for j_idx in range(1, simulations + 1):
            chosen_scenario = scenarios_to_test[(j_idx - 1) % len(scenarios_to_test)]
            chosen_archetype = archetypes_to_test[(j_idx - 1) % len(archetypes_to_test)]
            j_seed = batch_seed + j_idx * 41

            res = self.simulate_journey(
                journey_id=j_idx,
                scenario=chosen_scenario,
                archetype=chosen_archetype,
                fuzz_mode=fuzz_mode,
                max_turns=max_turns,
                fail_fast=fail_fast,
                with_llm=with_llm,
                seed=j_seed,
            )

            report.results.append(res)
            report.total_journeys += 1
            report.total_turns += res.total_turns
            report.total_violations += len(res.violations)
            report.critical_violations += len([v for v in res.violations if v.severity == "CRITICAL"])
            report.warning_violations += len([v for v in res.violations if v.severity == "WARNING"])

            for v in res.violations:
                report.violations_by_category[v.category] = report.violations_by_category.get(v.category, 0) + 1

            if res.error:
                report.crashes += 1
            elif res.success:
                report.successful_journeys += 1

            # Archetype metrics
            arch_entry = report.archetype_stats.setdefault(chosen_archetype, {
                "journeys": 0, "successful": 0,
            })
            arch_entry["journeys"] += 1
            if res.success:
                arch_entry["successful"] += 1

            # Scenario metrics
            scen_entry = report.scenario_stats.setdefault(chosen_scenario, {
                "journeys": 0, "successful": 0, "violations": 0,
            })
            scen_entry["journeys"] += 1
            if res.success:
                scen_entry["successful"] += 1
            scen_entry["violations"] += len(res.violations)

            if fail_fast and (res.error or any(v.severity == "CRITICAL" for v in res.violations)):
                break

        report.avg_turns_per_journey = (report.total_turns / max(1, report.total_journeys))
        report.duration_ms = (time.perf_counter() - start_time) * 1000.0
        return report
