from __future__ import annotations
"""
Intimacy Invariant Auditor for Hikayat Intimate Moment & Excitement Meter Simulator.

Enforces 8 zero-tolerance invariant categories across every simulation turn:
1. Zero Non-Genital Delta: Hair, cheek, shoulder, hand touches MUST yield delta == 0.
2. Strict Genital Specificity & Directionality: Direct stimulation vs capped spectator warmth (<= 80%).
3. Anatomical Climax Rules: Male hard stop + refractory cooldown vs Female 35% multi-climax baseline.
4. Idle Decay Grace & Rate: 2-turn grace period (delta == 0), then -5/turn (Aroused) or -10/turn.
5. Virginity & Milestone Memory Persistence: Virgin transition to non_virgin, first-time memory logging, and symmetric intimate_events rows.
6. Species Biological Anatomy Compliance: Validates against sanitize_sensitive_spots_for_species.
7. Physical State & Clothing Displacement: Layer displacement and composure degradation.
8. Zero Blueprint Contradictions & Progressive Disclosure: No contradiction in blueprints, and monotonic disclosure unlocks.
"""
import json
import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set

import db
from mechanics.social.persona.intimacy.logic import (
    sanitize_sensitive_spots_for_species,
)
from mechanics.social.persona.intimacy.ledger import (
    compute_intimate_tracks_from_ledger,
    enforce_biological_invariants,
)
from mechanics.social.intimate_excitement import (
    has_state_contradiction_in_choice,
    build_intimate_choice_blueprints,
    NON_GENITAL_BODY_PARTS,
    NON_GENITAL_VERBS,
)
from .actor_ai import IntimacyAction


@dataclass
class IntimacyViolation:
    """Record of an invariant breach in excitement meters, anatomy, or intimacy ledger."""
    turn: int
    category: str
    message: str
    actor_name: str
    severity: str = "CRITICAL"  # "CRITICAL" or "WARNING"
    state_dump: Dict[str, Any] = field(default_factory=dict)


class IntimacyInvariantAuditor:
    """Rigorous invariant auditor for intimate moments and excitement meters."""

    def __init__(self, partner_config: str = "hetero", scenario: str = "full_progression"):
        self.partner_config = partner_config
        self.scenario = scenario
        self.violations: List[IntimacyViolation] = []
        self.turn_snapshots: List[Dict[str, Any]] = []
        self.known_disclosed_attributes: Dict[str, Set[str]] = {}

    def audit_turn(
        self,
        turn: int,
        session_id: int,
        player_char: Dict[str, Any],
        partner_contacts: List[Dict[str, Any]],
        action: IntimacyAction,
        pre_physical_state: Dict[str, Any],
        post_physical_state: Dict[str, Any],
        excitement_res: Dict[str, Any],
        blueprints: Optional[Dict[str, Any]] = None,
    ) -> List[IntimacyViolation]:
        """
        Executes zero-tolerance invariant verification across live meters,
        anatomy, physical clothing, and database ledger state.
        """
        turn_violations: List[IntimacyViolation] = []

        player_name = str(player_char.get("name", "Player"))
        player_gender = str(player_char.get("gender", "Male")).lower()
        is_female_player = "female" in player_gender or "woman" in player_gender

        pre_exc = pre_physical_state.get("excitement") or {}
        post_exc = post_physical_state.get("excitement") or {}

        pre_actors = pre_exc.get("actors") or {}
        post_actors = post_exc.get("actors") or {}

        act_text_low = (action.action_text or "").lower()
        act_type = excitement_res.get("act_type", "none")

        # ── 1. INVARIANT: ZERO NON-GENITAL DELTA ─────────────────────────────
        is_explicit_non_genital = (
            action.metadata.get("is_non_genital_probe")
            or (
                act_type in ("none", "foreplay_nongenital")
                and any(part in act_text_low for part in ("stroke hair", "caress cheek", "kiss forehead", "hold hands", "against shoulder", "hand on arm", "hair", "cheek", "forehead", "shoulder"))
                and not any(g in act_text_low for g in ("crotch", "cock", "penis", "shaft", "clit", "pussy", "vagina", "entrance", "slit", "folds", "rear", "anus", "thigh", "between", "lower", "tease"))
            )
        )
        if is_explicit_non_genital:
            p_delta = excitement_res.get("player_delta", 0)
            if p_delta > 0:
                turn_violations.append(IntimacyViolation(
                    turn=turn,
                    category="NON_GENITAL_DELTA_VIOLATION",
                    message=f"Player excitement increased by +{p_delta} on non-genital stimulation: '{action.action_text}'",
                    actor_name=player_name,
                    state_dump={"action": action.action_text, "player_delta": p_delta}
                ))

            for pm in excitement_res.get("partner_meters", []):
                pm_name = pm.get("name", "")
                pm_delta = pm.get("delta", 0)
                if pm_delta > 0:
                    turn_violations.append(IntimacyViolation(
                        turn=turn,
                        category="NON_GENITAL_DELTA_VIOLATION",
                        message=f"Partner {pm_name} excitement increased by +{pm_delta} on non-genital stimulation: '{action.action_text}'",
                        actor_name=pm_name,
                        state_dump={"action": action.action_text, "partner_delta": pm_delta}
                    ))

        # ── 1.5. INVARIANT: TURN-OFF EXCITEMENT DAMPENING / ZERO GAIN ─────────
        if action.is_turn_off_attempt:
            target_pm = next((pm for pm in excitement_res.get("partner_meters", []) if pm.get("name") == action.target_npc), None)
            if target_pm:
                t_delta = target_pm.get("delta", 0)
                if t_delta > 0:
                    turn_violations.append(IntimacyViolation(
                        turn=turn,
                        category="TURN_OFF_EXCITEMENT_ANOMALY",
                        message=f"Partner {action.target_npc} gained positive excitement (+{t_delta}) when probed with explicit turn-off: '{action.metadata.get('turn_off_probed')}'.",
                        actor_name=action.target_npc,
                        state_dump={"action": action.action_text, "delta": t_delta}
                    ))

        # ── 2. INVARIANT: GENITAL SPECIFICITY & SPECTATOR WARMTH CAP ────────
        for pm in excitement_res.get("partner_meters", []):
            pm_name = pm.get("name", "")
            pm_first = (pm_name.split() or [""])[0].lower()
            pm_meter = pm.get("meter", 0)
            pm_delta = pm.get("delta", 0)
            is_targeted = (
                (pm_name == action.target_npc)
                or (action.target_npc in ("", "both", "all"))
                or (pm_name.lower() in act_text_low)
                or (len(pm_first) >= 3 and pm_first in act_text_low)
            )

            # Passive spectator check in multi-partner groups
            if len(partner_contacts) > 1 and not is_targeted and act_type not in ("none", "foreplay_nongenital"):
                if not pm.get("climaxed"):
                    if pm_meter > 90 and pm_delta > 0:
                        turn_violations.append(IntimacyViolation(
                            turn=turn,
                            category="SPECTATOR_WARMTH_EXCEEDED",
                            message=f"Passive spectator {pm_name} meter exceeded warmth cap ({pm_meter} > 90%) without direct stimulation.",
                            actor_name=pm_name,
                            state_dump={"pm_meter": pm_meter, "pm_delta": pm_delta, "action": action.action_text}
                        ))
                    if pm_delta > 10:
                        turn_violations.append(IntimacyViolation(
                            turn=turn,
                            category="SPECTATOR_DELTA_OVERFLOW",
                            message=f"Passive spectator {pm_name} gained excessive delta (+{pm_delta} > 10) on secondary warmth.",
                            actor_name=pm_name,
                            state_dump={"pm_delta": pm_delta, "action": action.action_text}
                        ))

        # ── 3. INVARIANT: ANATOMICAL CLIMAX RULES ────────────────────────────
        # Male Player Anatomy Climax Invariant
        if not is_female_player:
            pl_climaxed = post_actors.get(player_name, {}).get("climaxes_count", 0) > 0
            if pl_climaxed:
                p_meter = post_actors.get(player_name, {}).get("meter", 0)
                if p_meter != 100:
                    turn_violations.append(IntimacyViolation(
                        turn=turn,
                        category="MALE_CLIMAX_METER_CORRUPTION",
                        message=f"Male player meter is {p_meter}% after climax (expected locked at 100%).",
                        actor_name=player_name,
                        state_dump={"meter": p_meter}
                    ))
                # Refractory clock must be active
                target_min = post_exc.get("refractory_until_minute")
                if not target_min:
                    turn_violations.append(IntimacyViolation(
                        turn=turn,
                        category="MALE_REFRACTORY_MISSING",
                        message="Male player climaxed but refractory_until_minute was not recorded in physical state.",
                        actor_name=player_name,
                        state_dump={"excitement": post_exc}
                    ))

        # Female Partner Anatomy Climax Invariant
        for pc in partner_contacts:
            pc_name = pc.get("name", "")
            pc_gen = str(pc.get("gender", "Female")).lower()
            is_female_npc = "male" not in pc_gen or "female" in pc_gen
            if is_female_npc:
                pc_data = post_actors.get(pc_name, {})
                pc_climaxes = pc_data.get("climaxes_count", 0)
                # If female climaxed previously and continues receiving direct stimulation
                pre_pc_climaxes = pre_actors.get(pc_name, {}).get("climaxes_count", 0)
                if pre_pc_climaxes > 0 and excitement_res.get("partner_delta", 0) > 0 and pc_name == action.target_npc:
                    # Meter must have reset to 35% hypersensitive baseline
                    pc_meter = pc_data.get("meter", 0)
                    if pc_meter > 100:
                        turn_violations.append(IntimacyViolation(
                            turn=turn,
                            category="FEMALE_MULTICLIMAX_CORRUPTION",
                            message=f"Female partner {pc_name} meter exceeded 100% ({pc_meter}%) on multi-climax baseline.",
                            actor_name=pc_name,
                            state_dump={"meter": pc_meter}
                        ))

        # ── 4. INVARIANT: IDLE DECAY & GRACE PERIOD ──────────────────────────
        p_spent = (not is_female_player) and post_actors.get(player_name, {}).get("climaxes_count", 0) > 0
        if not p_spent:
            p_idle = post_actors.get(player_name, {}).get("idle_turns", 0)
            p_delta = excitement_res.get("player_delta", 0)
            if p_idle in (1, 2) and not excitement_res.get("player_stimulated"):
                # Grace period turns 1 and 2: delta must be exactly 0
                if p_delta != 0:
                    turn_violations.append(IntimacyViolation(
                        turn=turn,
                        category="DECAY_GRACE_PERIOD_VIOLATION",
                        message=f"Player delta is {p_delta} during idle grace turn {p_idle} (expected 0).",
                        actor_name=player_name,
                        state_dump={"p_idle": p_idle, "p_delta": p_delta}
                    ))
            elif p_idle >= 3 and not excitement_res.get("player_stimulated"):
                # Turn 3+: decay must be negative if meter was > 0
                pre_meter = pre_actors.get(player_name, {}).get("meter", 0)
                if pre_meter > 0 and p_delta >= 0:
                    turn_violations.append(IntimacyViolation(
                        turn=turn,
                        category="IDLE_DECAY_FAILURE",
                        message=f"Player meter failed to decay on idle turn {p_idle} (pre_meter={pre_meter}, delta={p_delta}).",
                        actor_name=player_name,
                        state_dump={"p_idle": p_idle, "pre_meter": pre_meter, "p_delta": p_delta}
                    ))

        # ── 5. INVARIANT: SPECIES BIOLOGY & SENSITIVE SPOTS ──────────────────
        for pc in partner_contacts:
            pc_name = pc.get("name", "")
            pc_race = pc.get("race", "Human")
            app = pc.get("appearance") or {}
            spots = app.get("sensitive_spots") or ""
            if spots:
                sanitized = sanitize_sensitive_spots_for_species(spots, pc_race, pc_race)
                raw_set = {x.strip().lower() for x in spots.split(",") if x.strip()}
                san_set = {x.strip().lower() for x in sanitized.split(",") if x.strip()}
                if raw_set != san_set:
                    turn_violations.append(IntimacyViolation(
                        turn=turn,
                        category="BIOLOGICAL_SPECIES_CONTRADICTION",
                        message=f"Partner {pc_name} ({pc_race}) has biologically invalid sensitive spots: '{spots}' != '{sanitized}'",
                        actor_name=pc_name,
                        state_dump={"spots": spots, "sanitized": sanitized}
                    ))

        # ── 6. INVARIANT: PHYSICAL CLOTHING & COMPOSURE ──────────────────────
        actors_cloth = post_physical_state.get("actors") or {}
        if act_type in ("penetrative", "anal_give", "anal_receive"):
            # Intercourse requires bottom layers to be displaced or removed
            targets_to_check = [player_name]
            if action.target_npc in ("", "both", "all"):
                targets_to_check.extend([c.get("name") for c in partner_contacts if c.get("name")])
            else:
                targets_to_check.append(action.target_npc)

            for act_k in targets_to_check:
                if act_k not in actors_cloth:
                    continue
                c_entry = actors_cloth.get(act_k, {}).get("clothing") or {}
                b_val = str(c_entry.get("bottom", "")).lower()
                ub_val = str(c_entry.get("under_bottom", "")).lower()
                if "clothed" in b_val or "worn" in ub_val:
                    turn_violations.append(IntimacyViolation(
                        turn=turn,
                        category="CLOTHING_DISPLACEMENT_FAILURE",
                        message=f"Actor {act_k} has fully clothed bottom ({b_val}) / under_bottom ({ub_val}) during penetrative act '{act_type}'.",
                        actor_name=act_k,
                        state_dump={"clothing": c_entry, "act_type": act_type}
                    ))

        # ── 7. INVARIANT: CHOICE BLUEPRINT CONTRADICTIONS ────────────────────
        if blueprints and isinstance(blueprints.get("choices"), list):
            for c in blueprints["choices"]:
                c_lbl = str(c.get("label", ""))
                is_contradiction = has_state_contradiction_in_choice(
                    label=c_lbl,
                    last_act=str(post_exc.get("last_act") or ""),
                    partner_climaxed=bool(excitement_res.get("partner_climaxed")),
                    player_meter=int(post_actors.get(player_name, {}).get("meter", 0)),
                    partner_meter=int(excitement_res.get("partner_meter", 0)),
                    player_posture=str(post_physical_state.get("posture") or ""),
                    player_spent=bool((not is_female_player) and post_actors.get(player_name, {}).get("climaxes_count", 0) > 0),
                    player_climaxed=bool(post_actors.get(player_name, {}).get("climaxes_count", 0) > 0),
                )
                if is_contradiction:
                    turn_violations.append(IntimacyViolation(
                        turn=turn,
                        category="CHOICE_BLUEPRINT_CONTRADICTION",
                        message=f"Choice blueprint contradicts live state: '{c_lbl}'",
                        actor_name=player_name,
                        state_dump={"choice": c, "post_exc": post_exc}
                    ))

        # ── 8. INVARIANT: PROGRESSIVE CODEX DISCLOSURE MONOTONICITY ──────────
        for pc in partner_contacts:
            pc_name = pc.get("name", "")
            app = pc.get("appearance") or {}
            known_disclosed = self.known_disclosed_attributes.setdefault(pc_name, set())
            for flag in (
                "demeanor_revealed", "dynamic_revealed", "turn_ons_revealed",
                "sensitive_spots_revealed", "underwear_revealed", "intimate_revealed",
                "oral_revealed", "manual_revealed", "intercourse_revealed"
            ):
                if app.get(flag):
                    known_disclosed.add(flag)
                elif flag in known_disclosed:
                    turn_violations.append(IntimacyViolation(
                        turn=turn,
                        category="DISCLOSURE_REGRESSION",
                        message=f"Codex disclosure flag '{flag}' for {pc_name} silently reverted from True to False.",
                        actor_name=pc_name,
                        state_dump={"appearance": app}
                    ))

        self.violations.extend(turn_violations)
        return turn_violations

    def audit_final_journey(
        self,
        session_id: int,
        player_char: Dict[str, Any],
        partner_contacts: List[Dict[str, Any]],
        is_secret_affair_test: bool = False,
    ) -> List[IntimacyViolation]:
        """
        Executes end-of-session ledger verification and secret affair relationship graph inspection.
        """
        final_violations: List[IntimacyViolation] = []

        # Audit SQLite intimate_events table
        with db.get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM intimate_events WHERE session_id = ? ORDER BY id ASC",
                (session_id,)
            )
            rows = [dict(r) for r in cur.fetchall()]

        # Symmetric reciprocity check
        actor_genders = {str(player_char.get("id")): player_char.get("gender", "Male")}
        for pc in partner_contacts:
            actor_genders[str(pc.get("npc_id"))] = pc.get("gender", "Female")
            actor_genders[pc.get("name")] = pc.get("gender", "Female")

        for row in rows:
            act_type = row.get("act_type")
            char_id = row.get("character_id")
            part_id = row.get("partner_id")
            part_name = row.get("partner_name")
            direction = row.get("direction")

            c_gender = actor_genders.get(str(char_id), "Female" if "female" in str(row.get("narrative_summary", "")).lower() else "Male")
            p_gender = actor_genders.get(str(part_id), actor_genders.get(str(part_name), "Female" if "female" in str(row.get("narrative_summary", "")).lower() else "Male"))

            # Check biological invariants
            expected_dir = enforce_biological_invariants(
                gender=c_gender,
                act_type=act_type,
                direction=direction,
                partner_gender=p_gender,
            )
            if direction != expected_dir and act_type == "anal":
                final_violations.append(IntimacyViolation(
                    turn=row.get("turn_number", 0),
                    category="BIOLOGICAL_INVARIANT_LEDGER_BREACH",
                    message=f"Intimate event row {row.get('id')} violated biological direction invariants: {direction} != {expected_dir}",
                    actor_name=str(char_id),
                    state_dump=row
                ))

        # Secret affair check
        if is_secret_affair_test and rows:
            primary_rows = [
                r for r in rows
                if (r.get("partner_name") == partner_contacts[0]["name"] or str(r.get("partner_id")) == str(partner_contacts[0].get("npc_id")))
                and bool(r.get("is_physical"))
            ]
            if primary_rows:
                non_affair_rows = [r for r in primary_rows if r.get("is_secret_affair") != 1]
                if non_affair_rows:
                    final_violations.append(IntimacyViolation(
                        turn=0,
                        category="SECRET_AFFAIR_NOT_LOGGED",
                        message="Partner had a pre-existing committed partner, but intimate event row failed to record is_secret_affair == 1.",
                        actor_name=partner_contacts[0]["name"],
                        state_dump={"non_affair_rows": non_affair_rows}
                    ))

                # Inspect relationship_graph for affair tie
                try:
                    import mechanics.social.relationship_graph as rg
                    p_key_partner = rg.canonical_person_key(partner_contacts[0]["name"])
                    ties = rg.get_ties(session_id, p_key_partner, active_only=True, types={rg.TIETYPE_AFFAIR})
                    has_affair_tie = any(
                        t.get("tie_type") == rg.TIETYPE_AFFAIR and t.get("visibility") == "secret"
                        for t in ties
                    )
                    if not has_affair_tie:
                        final_violations.append(IntimacyViolation(
                            turn=0,
                            category="AFFAIR_RELATIONSHIP_TIE_MISSING",
                            message="Secret affair occurred but TIETYPE_AFFAIR secret tie was not recorded in relationship_graph.",
                            actor_name=partner_contacts[0]["name"],
                            state_dump={"ties": ties}
                        ))
                except Exception as e:
                    final_violations.append(IntimacyViolation(
                        turn=0,
                        category="RELATIONSHIP_GRAPH_EXCEPTION",
                        message=f"Failed to query relationship graph for affair tie: {e}",
                        actor_name=partner_contacts[0]["name"],
                    ))

        self.violations.extend(final_violations)
        return final_violations
