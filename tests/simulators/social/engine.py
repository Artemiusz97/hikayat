from __future__ import annotations
"""
Social Dynamics & Persona Simulator Engine for Hikayat.

Orchestrates synthetic agent interactions across school directories, fantasy courts,
and cyberpunk syndicates, auditing bounds, peer isolation, confession gating, trait monotonicity,
kinship consistency, and schema cleanliness.
"""
import copy
import json
import random
import time
import traceback
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

import db
from mechanics.social.relationships import (
    can_trigger_romantic_confession,
    is_contact_eligible,
    clamp_score,
)
from mechanics.social.school_roster import (
    hydrate_school_character,
)
from mechanics.social.factions import (
    get_faction_tier,
)
from mechanics.social.persona import is_turn_off_triggered
from mechanics.system.phone.messaging import get_dm_requirement
from mechanics.system.phone.media_captions import generate_npc_photo_caption
from .actor_ai import SocialActorAI, SocialAction
from .fuzzer import SocialFuzzer
from .auditor import SocialInvariantAuditor, SocialViolation


def is_public_waypoint(location_str: str) -> bool:
    """Detects if a waypoint represents a public area lacking seclusion."""
    if not location_str:
        return False
    loc = location_str.lower()
    private_kws = ["dorm", "bedroom", "private room", "bathroom", "secluded", "rooftop at night", "secret hideout"]
    if any(k in loc for k in private_kws):
        return False
    public_kws = [
        "classroom", "hallway", "corridor", "cafeteria", "courtyard", "gym",
        "tavern hall", "town square", "market", "guild hall", "street", "plaza"
    ]
    return any(k in loc for k in public_kws)


@dataclass
class SocialJourneyResult:
    """Detailed telemetry and outcome for a single simulated social agent journey."""
    journey_id: int
    scenario: str
    archetype: str
    seed: int
    total_turns: int = 0
    interactions_count: int = 0
    hydrated_contacts: int = 0
    traits_unlocked: int = 0
    confessions_attempted: int = 0
    confessions_accepted: int = 0
    confessions_rejected: int = 0
    illegal_advances_prevented: int = 0
    intimate_milestones_unlocked: int = 0
    anal_acts_simulated: int = 0
    sensitive_spots_discovered: int = 0
    turn_offs_triggered: int = 0
    phone_interactions: int = 0
    spicy_media_gated: int = 0
    sibling_ripples: int = 0
    discretion_breaches_prevented: int = 0
    faction_reputations: Dict[str, int] = field(default_factory=dict)
    success: bool = False
    violations: List[SocialViolation] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class SocialSimulationReport:
    """Aggregated metrics across a batch of social dynamics simulations."""
    total_journeys: int = 0
    successful_journeys: int = 0
    crashes: int = 0
    total_turns: int = 0
    avg_turns_per_journey: float = 0.0
    total_traits_unlocked: int = 0
    total_confessions_accepted: int = 0
    total_confessions_rejected: int = 0
    total_illegal_advances_prevented: int = 0
    total_intimate_milestones: int = 0
    total_anal_acts: int = 0
    total_sensitive_spots: int = 0
    total_turn_offs: int = 0
    total_phone_interactions: int = 0
    total_spicy_media_gated: int = 0
    total_sibling_ripples: int = 0
    total_discretion_prevented: int = 0
    total_violations: int = 0
    violations_by_category: Dict[str, int] = field(default_factory=dict)
    archetype_stats: Dict[str, Any] = field(default_factory=dict)
    scenario_stats: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    results: List[SocialJourneyResult] = field(default_factory=list)


class SocialDynamicsSimulator:
    """Harness for headless and LLM-assisted simulation of social dynamics and personas."""

    def __init__(self, seed: Optional[int] = None):
        self.base_seed = seed
        self.rng = random.Random(seed)

    def simulate_journey(
        self,
        journey_id: int = 1,
        scenario: str = "high_school_drama",
        archetype: str = "diplomat",
        fuzz_mode: str = "clean",
        max_turns: int = 15,
        fail_fast: bool = False,
        with_llm: bool = False,
        seed: Optional[int] = None,
    ) -> SocialJourneyResult:
        """Simulates a single social journey over max_turns turns."""
        start_time = time.perf_counter()
        j_seed = seed if seed is not None else (self.base_seed + journey_id if self.base_seed else random.randint(1000, 999999))
        local_rng = random.Random(j_seed)

        fuzzer = SocialFuzzer(fuzz_mode=fuzz_mode, rng=local_rng)
        actor = SocialActorAI(archetype=archetype, seed=j_seed)
        auditor = SocialInvariantAuditor(scenario_key=scenario)

        result = SocialJourneyResult(
            journey_id=journey_id,
            scenario=scenario,
            archetype=archetype,
            seed=j_seed,
        )

        session_id = local_rng.randint(900000, 999999)

        try:
            # 1. Setup isolated session and character
            sess_dict, char_dict = fuzzer.create_test_session(
                scenario_key=scenario,
                session_id=session_id,
                char_gender="male" if local_rng.random() < 0.5 else "female",
            )
            char_id = char_dict["id"]

            # 2. Simulation turn loop
            for turn in range(1, max_turns + 1):
                result.total_turns = turn

                # A. Query current ecosystem state
                contacts = db.get_contacts(session_id, character_id=char_id)
                directory = db.get_school_roster(session_id) if "school" in scenario else []
                factions = db.get_factions(session_id)

                # B. Actor AI decides next action
                action = actor.choose_action(
                    session_id=session_id,
                    contacts=contacts,
                    directory_candidates=directory,
                    factions=factions,
                    turn=turn,
                    scenario_key=scenario,
                    location=sess_dict.get("current_location", ""),
                )

                # C. Fuzz action according to fuzz_mode
                fuzzed_action = fuzzer.fuzz_action(action, contacts, directory, char_dict)

                # D. Target resolution & hydration
                target_name = fuzzed_action.target_npc
                existing_contact = db.get_contact(session_id, target_name, character_id=char_id)

                if not existing_contact and directory:
                    # Check if target is in school directory and hydrate
                    dir_match = next((d for d in directory if d.get("name", "").lower() == target_name.lower()), None)
                    if dir_match:
                        hydrate_school_character(session_id, dir_match)
                        result.hydrated_contacts += 1
                        existing_contact = db.get_contact(session_id, target_name, character_id=char_id)

                if not existing_contact:
                    # Generic contact upsert for fantasy / cyberpunk NPCs with rich persona appearance
                    gen = "female" if local_rng.random() < 0.5 else "male"
                    import hashlib
                    from mechanics.social.persona.intimacy.generation import generate_dynamic_intimate_attributes
                    h_val = int(hashlib.md5(f"{session_id}:{target_name}".encode()).hexdigest(), 16)
                    dyn_attrs = generate_dynamic_intimate_attributes(h_val, race="Human", gender=gen, openness="moderate")
                    dyn_app = {
                        "sensitive_spots": dyn_attrs["sensitive_spots"],
                        "sensitive_spots_revealed": False,
                        "turn_ons": dyn_attrs["turn_ons"],
                        "turn_offs": dyn_attrs["turn_offs"],
                        "erotic_openness": "moderate",
                        "intercourse_experience": dyn_attrs["intercourse"],
                        "oral_experience": dyn_attrs["oral"],
                        "manual_experience": dyn_attrs["manual"],
                        "anal_experience": dyn_attrs["anal"],
                    }
                    db.upsert_contact(
                        session_id=session_id,
                        character_id=char_id,
                        npc_id=target_name,
                        name=target_name,
                        delta_score=0,
                        track="platonic",
                        race="Human",
                        gender=gen,
                        appearance=dyn_app,
                    )
                    existing_contact = db.get_contact(session_id, target_name, character_id=char_id)

                result.interactions_count += 1

                outcome_label = ""
                # E. Execute action mechanics
                app_dict = dict(existing_contact.get("appearance") or {}) if existing_contact else {}

                if fuzzed_action.action_type == "confess_romance":
                    result.confessions_attempted += 1
                    can_confess = can_trigger_romantic_confession(
                        session_id=session_id,
                        character_id=char_id,
                        npc_name=target_name,
                        scenario=scenario,
                    )

                    if can_confess:
                        # Success! Milestone unlocked
                        db.update_contact_track(session_id, target_name, "romantic", character_id=char_id)
                        rels = (existing_contact.get("relations") or {}) if existing_contact else {}
                        rels["romance"] = {
                            "status": "dating",
                            "current_partner": {"name": char_dict["name"]},
                        }
                        db.update_contact_relations(session_id, target_name, rels, character_id=char_id)
                        db.upsert_contact(
                            session_id=session_id,
                            npc_id=target_name,
                            name=target_name,
                            character_id=char_id,
                            new_memory=f"{char_dict['name']} confessed feelings to {target_name} and they agreed to date.",
                        )
                        result.confessions_accepted += 1
                        outcome_label = "Milestone Confession Accepted (Now Dating!)"

                        # Sibling dating awareness ripple
                        sib_name = None
                        if directory:
                            for d_ent in directory:
                                if d_ent.get("name", "").lower() == target_name.lower() and d_ent.get("sibling_name"):
                                    sib_name = d_ent.get("sibling_name")
                                    break
                        if sib_name:
                            result.sibling_ripples += 1
                            db.upsert_contact(
                                session_id=session_id,
                                character_id=char_id,
                                npc_id=sib_name,
                                name=sib_name,
                                new_general_memory=f"Heard that {char_dict['name']} and {target_name} started dating.",
                            )
                    else:
                        # Rejection or gated boundary
                        result.confessions_rejected += 1
                        db.set_confession_cooldown(session_id, target_name, 3)
                        db.update_relationship_score(session_id, target_name, -5, character_id=char_id)

                        if not is_contact_eligible(target_name, scenario=scenario, session_id=session_id):
                            result.illegal_advances_prevented += 1
                            outcome_label = "Confession Rejected (Non-Peer / Faculty Gated)"
                        else:
                            outcome_label = "Confession Rejected (Score < 70 or Cooldown)"

                elif fuzzed_action.action_type == "explore_sensitive_spot":
                    result.sensitive_spots_discovered += 1
                    target_spot = fuzzed_action.metadata.get("target_spot", "neck")
                    app_dict["sensitive_spots_revealed"] = True
                    delta = fuzzed_action.affinity_delta
                    db.update_relationship_score(session_id, target_name, delta, character_id=char_id)
                    db.upsert_contact(
                        session_id=session_id,
                        npc_id=target_name,
                        name=target_name,
                        character_id=char_id,
                        appearance=app_dict,
                        new_memory=f"{char_dict['name']} learned that {target_name}'s sensitive spot is the {target_spot}.",
                    )
                    outcome_label = f"Discovered Sensitive Spot: {target_spot} (+{delta})"

                elif fuzzed_action.action_type == "trigger_turn_off":
                    result.turn_offs_triggered += 1
                    delta = min(-6, fuzzed_action.affinity_delta)
                    db.update_relationship_score(session_id, target_name, delta, character_id=char_id)
                    db.upsert_contact(
                        session_id=session_id,
                        npc_id=target_name,
                        name=target_name,
                        character_id=char_id,
                        new_memory=f"{target_name} was deeply uncomfortable and put off by {char_dict['name']}'s behavior.",
                    )
                    outcome_label = f"Turn-Off Aversion Triggered ({delta})"

                elif fuzzed_action.action_type == "phone_text":
                    result.phone_interactions += 1
                    intent = fuzzed_action.metadata.get("intent", "chat")
                    openness = str(app_dict.get("erotic_openness") or "moderate")
                    track = existing_contact.get("track", "platonic") if existing_contact else "platonic"
                    score = existing_contact.get("relationship_score", 0) if existing_contact else 0
                    req = get_dm_requirement(score, intent, track, openness)
                    roll = local_rng.randint(1, 20) + (char_dict.get("cha", 10) - 10) // 2
                    if roll >= req:
                        delta = fuzzed_action.affinity_delta
                        db.update_relationship_score(session_id, target_name, delta, character_id=char_id)
                        outcome_label = f"Phone {intent.capitalize()} Sent (+{delta})"
                    else:
                        outcome_label = f"Phone {intent.capitalize()} Left on Read (Roll {roll} < DC {req})"

                elif fuzzed_action.action_type == "phone_photo_request":
                    result.phone_interactions += 1
                    is_spicy = bool(fuzzed_action.metadata.get("is_spicy", False))
                    intent = "nsfw_photo" if is_spicy else "photo"
                    openness = str(app_dict.get("erotic_openness") or "moderate")
                    track = existing_contact.get("track", "platonic") if existing_contact else "platonic"
                    score = existing_contact.get("relationship_score", 0) if existing_contact else 0
                    req = get_dm_requirement(score, intent, track, openness)
                    roll = local_rng.randint(1, 20) + (char_dict.get("cha", 10) - 10) // 2
                    if is_spicy:
                        result.spicy_media_gated += 1

                    if roll >= req:
                        delta = 4 if is_spicy else 2
                        caption = generate_npc_photo_caption(existing_contact or {"name": target_name}, intent=intent)
                        db.update_relationship_score(session_id, target_name, delta, character_id=char_id)
                        db.upsert_contact(
                            session_id=session_id,
                            npc_id=target_name,
                            name=target_name,
                            character_id=char_id,
                            new_memory=f"{target_name} sent a photo: \"{caption[:60]}...\"",
                        )
                        outcome_label = f"Photo Received: {intent} (+{delta})"
                    else:
                        outcome_label = f"Photo Request Declined (Score {score}, Roll {roll} < DC {req})"

                elif fuzzed_action.action_type == "schedule_rendezvous":
                    from mechanics.system.commitments_engine import create_rendezvous
                    create_rendezvous(
                        session_id=session_id,
                        organizer=char_dict["name"],
                        participants=[target_name],
                        location="Greenwood Academy ➔ Library ➔ Study Carrels",
                        day=1,
                        start_minute=600,
                        end_minute=660,
                        title=f"Study Session with {target_name}",
                        origin="in_person"
                    )
                    outcome_label = f"Scheduled Rendezvous with {target_name} at Library"

                elif fuzzed_action.action_type == "fulfill_rendezvous":
                    from mechanics.system.commitments_engine import create_rendezvous, advance_rendezvous_to_arrived, fulfill_commitment
                    r_res = create_rendezvous(
                        session_id=session_id,
                        organizer=char_dict["name"],
                        participants=[target_name],
                        location="Greenwood Academy ➔ Library ➔ Study Carrels",
                        day=1,
                        start_minute=600,
                        end_minute=660,
                        title=f"Study Session with {target_name}",
                        origin="in_person"
                    )
                    c_id = r_res.get("id") or r_res.get("commitment_key")
                    if c_id:
                        advance_rendezvous_to_arrived(session_id, c_id)
                        fulfill_commitment(session_id, c_id)
                    db.update_relationship_score(session_id, target_name, 10, character_id=char_id)
                    outcome_label = f"Fulfilled Punctual Rendezvous with {target_name} (+10)"

                elif fuzzed_action.action_type == "flake_rendezvous":
                    from mechanics.system.commitments_engine import create_rendezvous, flake_commitment
                    r_res = create_rendezvous(
                        session_id=session_id,
                        organizer=char_dict["name"],
                        participants=[target_name],
                        location="Greenwood Academy ➔ Cafeteria ➔ Lunch Tables",
                        day=1,
                        start_minute=540,
                        end_minute=600,
                        title=f"Lunch with {target_name}",
                        origin="in_person"
                    )
                    c_id = r_res.get("id") or r_res.get("commitment_key")
                    if c_id:
                        flake_commitment(session_id, c_id)
                    db.update_relationship_score(session_id, target_name, -15, character_id=char_id)
                    outcome_label = f"Flaked on Rendezvous with {target_name} (-15 Penalty)"

                elif fuzzed_action.action_type == "combat_metaphor_chat":
                    delta = 3
                    db.update_relationship_score(session_id, target_name, delta, character_id=char_id)
                    outcome_label = f"Friendly Banter: We engaged in verbal combat with razor-sharp retorts (+{delta})"

                elif fuzzed_action.action_type == "ask_about_family":
                    sib_name = None
                    if directory:
                        for entry in directory:
                            if entry.get("name", "").lower() == target_name.lower() and entry.get("sibling_name"):
                                sib_name = entry.get("sibling_name")
                                break
                    if not sib_name and existing_contact:
                        rels = existing_contact.get("relations") or {}
                        for fam in rels.get("family", []):
                            if any(k in str(fam.get("relation", "")).lower() for k in ("brother", "sister", "sibling", "twin")):
                                sib_name = fam.get("name") or f"{fam.get('first_name', '')} {fam.get('surname', '')}".strip()
                                if sib_name:
                                    break
                    delta = fuzzed_action.affinity_delta
                    db.update_relationship_score(session_id, target_name, delta, character_id=char_id)
                    if sib_name:
                        result.sibling_ripples += 1
                        sib_delta = 2 if delta > 0 else -2
                        db.update_relationship_score(session_id, sib_name, sib_delta, character_id=char_id)
                        sib_mem = (
                            f"{char_dict['name']} asked warmly about my family through {target_name}."
                            if sib_delta > 0 else
                            f"{char_dict['name']} probed disrespectfully into my family through {target_name}."
                        )
                        db.upsert_contact(
                            session_id=session_id,
                            character_id=char_id,
                            npc_id=sib_name,
                            name=sib_name,
                            new_general_memory=sib_mem,
                        )
                        sign_d = "+" if delta > 0 else ""
                        sign_s = "+" if sib_delta > 0 else ""
                        outcome_label = f"Family Inquiry ({sign_d}{delta}) & Sibling Ripple to {sib_name} ({sign_s}{sib_delta})"
                    else:
                        sign_d = "+" if delta > 0 else ""
                        outcome_label = f"Family Inquiry with {target_name} ({sign_d}{delta})"

                elif fuzzed_action.action_type == "probe_mannerism":
                    b_info = dict(existing_contact.get("basic_info") or {}) if existing_contact else {}
                    b_info["mannerisms_revealed"] = True
                    if not b_info.get("mannerisms"):
                        b_info["mannerisms"] = "Twirls hair thoughtfully when listening closely."
                    db.upsert_contact(
                        session_id=session_id,
                        npc_id=target_name,
                        name=target_name,
                        character_id=char_id,
                        basic_info=b_info,
                    )
                    outcome_label = "Mannerism Deduced & Unlocked"

                elif fuzzed_action.action_type == "inquire_trait":
                    result.traits_unlocked += 1
                    cur_traits = existing_contact.get("unlocked_traits", []) if existing_contact else []
                    new_trait_pool = ["Observant", "Loyal", "Ambitious", "Secretive", "Perfectionist", "Impulsive"]
                    candidate = local_rng.choice([t for t in new_trait_pool if t not in cur_traits] or ["Determined"])
                    updated_traits = list(cur_traits) + [candidate]
                    db.upsert_contact(
                        session_id=session_id,
                        npc_id=target_name,
                        name=target_name,
                        character_id=char_id,
                        new_traits=updated_traits,
                    )
                    outcome_label = f"Unlocked Trait: {candidate}"

                elif fuzzed_action.action_type in ("compliment", "insult", "gift", "chat", "gossip"):
                    turn_offs = str(app_dict.get("turn_offs") or "")
                    if turn_offs and is_turn_off_triggered(fuzzed_action.action_text, turn_offs):
                        result.turn_offs_triggered += 1
                        delta = min(-6, fuzzed_action.affinity_delta)
                        outcome_label = f"Turn-Off Aversion Triggered ({delta})"
                    else:
                        delta = fuzzed_action.affinity_delta
                        sign = "+" if delta > 0 else ""
                        prefix = "Gossip & " if fuzzed_action.action_type == "gossip" else ""
                        outcome_label = f"{prefix}Affinity ({sign}{delta})"

                    db.update_relationship_score(session_id, target_name, delta, character_id=char_id)

                    # Hostile Action Sibling Ripple (delta <= -5 ripples as -2 to sibling)
                    if delta <= -5:
                        sib_name = None
                        if directory:
                            for entry in directory:
                                if entry.get("name", "").lower() == target_name.lower() and entry.get("sibling_name"):
                                    sib_name = entry.get("sibling_name")
                                    break
                        if not sib_name and existing_contact:
                            rels = existing_contact.get("relations") or {}
                            for fam in rels.get("family", []):
                                if any(k in str(fam.get("relation", "")).lower() for k in ("brother", "sister", "sibling", "twin")):
                                    sib_name = fam.get("name") or f"{fam.get('first_name', '')} {fam.get('surname', '')}".strip()
                                    if sib_name:
                                        break
                        if sib_name:
                            result.sibling_ripples += 1
                            db.update_relationship_score(session_id, sib_name, -2, character_id=char_id)
                            db.upsert_contact(
                                session_id=session_id,
                                character_id=char_id,
                                npc_id=sib_name,
                                name=sib_name,
                                new_general_memory=f"{char_dict['name']} was hostile towards my sibling {target_name}."
                            )

                elif fuzzed_action.action_type == "favor":
                    fac_id = fuzzed_action.metadata.get("faction_id")
                    if fac_id:
                        db.upsert_faction(session_id, name=fac_id, delta_score=5)
                    delta = fuzzed_action.affinity_delta
                    db.update_relationship_score(session_id, target_name, delta, character_id=char_id)
                    sign = "+" if delta > 0 else ""
                    outcome_label = f"Faction Favor & Affinity ({sign}{delta})"

                elif fuzzed_action.action_type in ("kiss", "oral_intimacy", "manual_intimacy", "anal_intimacy", "intercourse"):
                    # Waypoint Public Discretion Check
                    curr_loc = sess_dict.get("current_location", "")
                    openness = str(app_dict.get("erotic_openness") or "moderate").lower()
                    if is_public_waypoint(curr_loc) and "shameless" not in openness:
                        result.discretion_breaches_prevented += 1
                        outcome_label = "Intimacy Rebuffed (Public Discretion: Not in public!)"
                    else:
                        result.intimate_milestones_unlocked += 1
                        if fuzzed_action.action_type == "anal_intimacy":
                            result.anal_acts_simulated += 1

                        milestone_ev = fuzzed_action.metadata.get("milestone_event", fuzzed_action.action_type)
                        orig_track = (existing_contact.get("track") or "romantic") if existing_contact else "romantic"

                        from game_engine.state.reducers import _evaluate_npc_milestones
                        (
                            new_mem,
                            curr_i,
                            curr_o,
                            curr_m,
                            up_track,
                            is_intimate,
                            delta_boost,
                        ) = _evaluate_npc_milestones(
                            npc_name=target_name,
                            app_dict=app_dict,
                            track=orig_track,
                            milestone_ev=milestone_ev,
                            custom_summary=None,
                            intercourse_exp="",
                            oral_exp="",
                            actions=[{"label": fuzzed_action.action_text}],
                            narrative_text=fuzzed_action.action_text,
                            overall_check_success=True,
                            is_player_romantic_action=True,
                            is_player_intimate_action=True,
                            is_player_oral_action=(fuzzed_action.action_type == "oral_intimacy"),
                            is_player_intercourse_action=(fuzzed_action.action_type == "intercourse"),
                            is_player_confession_action=False,
                            is_player_affection_action=False,
                            affection_target_npc=None,
                            gift_target_npc=None,
                            gift_item_name=None,
                            confession_target_npc=None,
                            first_char_name=target_name,
                        )

                        app_dict["intercourse_experience"] = curr_i
                        app_dict["oral_experience"] = curr_o
                        app_dict["manual_experience"] = curr_m

                        delta = fuzzed_action.affinity_delta + delta_boost
                        db.update_relationship_score(session_id, target_name, delta, character_id=char_id)
                        db.upsert_contact(
                            session_id=session_id,
                            npc_id=target_name,
                            name=target_name,
                            character_id=char_id,
                            appearance=app_dict,
                            track=up_track,
                            new_memory=new_mem,
                        )
                        outcome_label = f"Intimate Milestone: {milestone_ev} (+{delta})"

                result.history.append({
                    "turn": turn,
                    "action_type": fuzzed_action.action_type,
                    "target": target_name,
                    "delta": fuzzed_action.affinity_delta,
                    "outcome": outcome_label,
                    "text": fuzzed_action.action_text[:120],
                })

                # Always decrement active confession cooldowns per turn
                db.decrement_confession_cooldowns(session_id)

                # Optional live LLM evaluation hook
                if with_llm:
                    try:
                        import asyncio
                        from llm_client import call_llm_json
                        llm_prompt = (
                            f"In scenario '{scenario}', player character '{char_dict['name']}' performs action: '{fuzzed_action.action_text}' "
                            f"towards NPC '{target_name}'. "
                            f"Generate a short dialogue response from '{target_name}' in JSON with keys 'dialogue' and 'reaction'."
                        )
                        asyncio.run(call_llm_json("You are the NPC dialogue generator for Hikayat.", llm_prompt, timeout=8.0))
                    except Exception:
                        pass

                # Relationship breakup check: if affinity drops to negative (< 0), demote romantic track to platonic
                for c in db.get_contacts(session_id, character_id=char_id):
                    if str(c.get("track", "")).lower() == "romantic" and c.get("relationship_score", 0) < 0:
                        c_name = c.get("name")
                        db.update_contact_track(session_id, c_name, "platonic", character_id=char_id)
                        rels = c.get("relations") or {}
                        rels["romance"] = {"status": "single", "current_partner": None}
                        db.update_contact_relations(session_id, c_name, rels, character_id=char_id)
                        db.upsert_contact(
                            session_id=session_id,
                            character_id=char_id,
                            npc_id=c_name,
                            name=c_name,
                            new_general_memory=f"{char_dict['name']} and {c_name} broke up due to falling relationship affinity.",
                        )

                # F. Post-turn audit
                updated_contacts = db.get_contacts(session_id, character_id=char_id)
                updated_factions = db.get_factions(session_id)
                sess = db.get_session(session_id)
                phys_state = json.loads(sess.get("physical_state_json") or "{}") if sess else {}

                turn_violations = auditor.audit_turn(
                    turn=turn,
                    session_id=session_id,
                    character_id=char_id,
                    contacts=updated_contacts,
                    school_directory=directory,
                    factions=updated_factions,
                    physical_state=phys_state,
                    action=fuzzed_action,
                    outcome_label=outcome_label,
                    location=sess_dict.get("current_location", ""),
                )

                if fail_fast and any(v.severity == "CRITICAL" for v in turn_violations):
                    break

            # Capture ending faction reps
            for f in db.get_factions(session_id):
                result.faction_reputations[f.get("name", "")] = f.get("reputation_score", 0)

            result.success = (len(auditor.violations) == 0)

        except Exception as e:
            result.error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        finally:
            # Clean up test session rows across all tables
            try:
                with db.get_conn() as conn:
                    for table in (
                        "contacts",
                        "school_directory",
                        "factions",
                        "session_locations",
                        "quest_waypoints",
                        "quests",
                        "session_members",
                        "lorebook",
                    ):
                        conn.execute(f"DELETE FROM {table} WHERE session_id=?", (session_id,))
                    conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
                    conn.execute("DELETE FROM characters WHERE active_session_id=?", (session_id,))
            except Exception:
                pass

        result.violations = auditor.violations
        result.duration_ms = (time.perf_counter() - start_time) * 1000.0
        return result

    def run_batch(
        self,
        simulations: int = 10,
        scenario: str = "high_school_drama",
        archetype: str = "diplomat",
        fuzz_mode: str = "clean",
        seed: Optional[int] = None,
        max_turns: int = 15,
        fail_fast: bool = False,
        with_llm: bool = False,
    ) -> SocialSimulationReport:
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
            "slice_of_life",
            "anomalous_incursions",
        ] if scenario == "all" else [scenario]

        archetypes_to_test = [
            "diplomat",
            "operative",
            "provocateur",
            "romance_seeker",
        ] if archetype == "all" else [archetype]

        report = SocialSimulationReport()

        for j_idx in range(1, simulations + 1):
            chosen_scenario = scenarios_to_test[(j_idx - 1) % len(scenarios_to_test)]
            chosen_archetype = archetypes_to_test[(j_idx - 1) % len(archetypes_to_test)]
            j_seed = batch_seed + j_idx * 37

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
            report.total_traits_unlocked += res.traits_unlocked
            report.total_confessions_accepted += res.confessions_accepted
            report.total_confessions_rejected += res.confessions_rejected
            report.total_illegal_advances_prevented += res.illegal_advances_prevented
            report.total_intimate_milestones += res.intimate_milestones_unlocked
            report.total_anal_acts += res.anal_acts_simulated
            report.total_sensitive_spots += res.sensitive_spots_discovered
            report.total_turn_offs += res.turn_offs_triggered
            report.total_phone_interactions += res.phone_interactions
            report.total_spicy_media_gated += res.spicy_media_gated
            report.total_sibling_ripples += res.sibling_ripples
            report.total_discretion_prevented += res.discretion_breaches_prevented
            report.total_violations += len(res.violations)

            for v in res.violations:
                report.violations_by_category[v.category] = report.violations_by_category.get(v.category, 0) + 1

            if res.error:
                report.crashes += 1
            elif res.success:
                report.successful_journeys += 1

            # Archetype metrics
            arch_entry = report.archetype_stats.setdefault(chosen_archetype, {
                "journeys": 0, "successful": 0, "confessions": 0, "traits": 0, "intimate": 0, "anal": 0,
                "spots": 0, "turn_offs": 0, "phone": 0, "ripples": 0,
            })
            arch_entry["journeys"] += 1
            if res.success:
                arch_entry["successful"] += 1
            arch_entry["confessions"] += res.confessions_accepted
            arch_entry["traits"] += res.traits_unlocked
            arch_entry["intimate"] += res.intimate_milestones_unlocked
            arch_entry["anal"] += res.anal_acts_simulated
            arch_entry["spots"] += res.sensitive_spots_discovered
            arch_entry["turn_offs"] += res.turn_offs_triggered
            arch_entry["phone"] += res.phone_interactions
            arch_entry["ripples"] += res.sibling_ripples

            # Scenario metrics
            scen_entry = report.scenario_stats.setdefault(chosen_scenario, {
                "journeys": 0, "successful": 0, "violations": 0,
            })
            scen_entry["journeys"] += 1
            if res.success:
                scen_entry["successful"] += 1
            scen_entry["violations"] += len(res.violations)

            if fail_fast and (res.error or len(res.violations) > 0):
                break

        report.avg_turns_per_journey = (report.total_turns / max(1, report.total_journeys))
        report.duration_ms = (time.perf_counter() - start_time) * 1000.0
        return report
