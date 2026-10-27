from __future__ import annotations
"""
Actor AI for Hikayat Intimate Moment & Excitement Meter Simulator.

Drives turn-by-turn action selection using:
- Hikayat's live choice blueprints (`build_intimate_choice_blueprints`).
- Scenario-driven state machine (full_progression, sudden_initiation, player_stop, npc_interruption, aftercare_only).
- Premature finish demand negotiation (Branch A: AGI/CHA manual/oral rescue, Branch B: selfish exit with -5 penalty).
- Multi-partner targeting and posture progression.
"""
import random
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

from mechanics.social.intimate_excitement import (
    build_intimate_choice_blueprints,
    has_state_contradiction_in_choice,
)


@dataclass
class IntimacyAction:
    """Represents a planned or executed intimate action in a turn."""
    action_type: str  # "foreplay", "oral_give", "oral_receive", "oral_mutual", "manual_give", "manual_receive", "intercourse", "anal_give", "anal_receive", "aftercare", "disengage", "interrupted"
    target_npc: str
    action_text: str
    sub_intent: Optional[str] = None
    posture: str = "embracing"
    stat_check: Optional[Dict[str, Any]] = None
    is_disengagement: bool = False
    is_sensitive_spot_hit: bool = False
    is_turn_off_attempt: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


SUPPORTED_SCENARIOS = [
    "full_progression",
    "sudden_initiation",
    "player_stop",
    "npc_interruption",
    "aftercare_only",
]


class IntimacyActorAI:
    """
    Blueprint-guided synthetic actor that navigates intimate encounters,
    respecting live physical state, partner meters, and scenario objectives.
    """

    def __init__(
        self,
        scenario: str = "full_progression",
        seed: Optional[int] = None,
        test_demand_branch: str = "rescue",  # "rescue" (Branch A) or "exit" (Branch B)
    ):
        self.scenario = scenario.lower() if scenario in SUPPORTED_SCENARIOS else "full_progression"
        self.rng = random.Random(seed)
        self.test_demand_branch = test_demand_branch
        self.current_stage = "init"
        self.turns_in_stage = 0
        self.selected_history: List[IntimacyAction] = []

    def choose_action(
        self,
        turn: int,
        player_char: Dict[str, Any],
        partner_contacts: List[Dict[str, Any]],
        physical_state: Dict[str, Any],
        excitement_res: Optional[Dict[str, Any]] = None,
        location: str = "Private Master Bedroom",
    ) -> IntimacyAction:
        """
        Determines the next intimate action based on current scenario,
        active excitement meters, and choice blueprints.
        """
        player_name = str(player_char.get("name", "Player"))
        player_gender = str(player_char.get("gender", "Male")).lower()
        is_female_player = "female" in player_gender or "woman" in player_gender

        primary_contact = partner_contacts[0] if partner_contacts else {"name": "Partner", "gender": "Female"}
        primary_name = str(primary_contact.get("name", "Partner"))
        primary_gender = str(primary_contact.get("gender", "Female"))

        excitement_dict = physical_state.get("excitement") or {}
        actors_dict = excitement_dict.get("actors") or {}
        player_data = actors_dict.get(player_name) or {}
        player_meter = int(player_data.get("meter", 0))
        player_climaxed = bool(player_data.get("climaxes_count", 0) > 0)
        player_spent = bool((not is_female_player) and player_climaxed)

        primary_actor_data = actors_dict.get(primary_name) or {}
        primary_meter = int(primary_actor_data.get("meter", 0))
        partner_climaxed = bool(primary_actor_data.get("climaxes_count", 0) > 0)
        all_partners_climaxed = all(
            bool((actors_dict.get(c.get("name")) or {}).get("climaxes_count", 0) > 0)
            for c in partner_contacts
        ) if partner_contacts else partner_climaxed

        premature_finish = bool(excitement_dict.get("premature_finish", False))
        partner_demanded = bool(excitement_dict.get("partner_demanded", False))
        unsatisfied_partners = excitement_dict.get("unsatisfied_partners") or []

        # Target partner selection: rotate or focus on unsatisfied
        target_contact = primary_contact
        if len(partner_contacts) > 1:
            if unsatisfied_partners:
                un_c = next((c for c in partner_contacts if c.get("name") in unsatisfied_partners), None)
                if un_c:
                    target_contact = un_c
            else:
                target_contact = partner_contacts[turn % len(partner_contacts)]

        target_name = str(target_contact.get("name", primary_name))
        target_gender = str(target_contact.get("gender", primary_gender))

        # Retrieve blueprints from engine
        last_act = str(excitement_dict.get("last_act") or "foreplay_nongenital")
        partner_actors_list = [
            {"name": c.get("name"), "meter": (actors_dict.get(c.get("name")) or {}).get("meter", 0),
             "climaxed": (actors_dict.get(c.get("name")) or {}).get("climaxes_count", 0) > 0,
             "gender": c.get("gender", "Female"),
             "spots": (c.get("appearance") or {}).get("sensitive_spots")}
            for c in partner_contacts
        ]

        blueprints = build_intimate_choice_blueprints(
            partner_name=primary_name,
            last_act=last_act,
            player_posture=str(physical_state.get("posture") or "embracing"),
            partner_posture="supine",
            player_meter=player_meter,
            partner_meter=primary_meter,
            partner_climaxed=partner_climaxed,
            player_climaxed=player_climaxed,
            premature_finish=premature_finish,
            partner_demanded=partner_demanded,
            sensitive_spots=(target_contact.get("appearance") or {}).get("sensitive_spots"),
            partner_actors=partner_actors_list,
            partner_gender=target_gender,
        )
        choices = blueprints.get("choices") or []

        # ── SCENARIO-SPECIFIC DECISION LOGIC ─────────────────────────────────

        # Scenario: NPC Interruption
        if self.scenario == "npc_interruption" and turn >= 2:
            return IntimacyAction(
                action_type="interrupted",
                target_npc=target_name,
                action_text="An abrupt knock on the unlocked door interrupts the quiet intimacy.",
                sub_intent="disengage",
                is_disengagement=True,
                metadata={"interruption_cause": "unlocked_door_intrusion", "waypoint": location}
            )

        # Scenario: Player Stop / Voluntary Pull-Out
        if self.scenario == "player_stop" and (turn >= 3 or player_meter >= 50 or primary_meter >= 50):
            return IntimacyAction(
                action_type="disengage",
                target_npc=target_name,
                action_text=f"Gently step back, ease away from {target_name}, and pause to catch your breath.",
                sub_intent="disengage",
                is_disengagement=True,
                posture="standing",
                metadata={"voluntary_stop": True}
            )

        # Premature Finish Demand Negotiation
        if premature_finish and partner_demanded:
            if self.test_demand_branch == "exit":
                # Branch B: Selfish dialogue exit -> triggers -5 affinity penalty in reducers
                return IntimacyAction(
                    action_type="disengage",
                    target_npc=target_name,
                    action_text=f"Step back gently, excuse yourself, and catch your breath away from {target_name}.",
                    sub_intent="aftercare",
                    is_disengagement=True,
                    metadata={"demand_exit_penalty_expected": True, "ends_dialogue": True}
                )
            else:
                # Branch A: Rescue unsatisfied partner via AGI / CHA skill checks
                skill_choice = next(
                    (c for c in choices if c.get("stat") in ("AGI", "CHA")),
                    None
                )
                if skill_choice:
                    stat_name = skill_choice.get("stat", "AGI")
                    req = int(skill_choice.get("requirement", 6))
                    return IntimacyAction(
                        action_type="manual_give" if stat_name == "AGI" else "oral_give",
                        target_npc=target_name,
                        action_text=str(skill_choice.get("label")),
                        sub_intent=skill_choice.get("sub_intent", "manual_give"),
                        stat_check={"stat": stat_name, "requirement": req, "is_success": True, "tier": "SUCCESS"},
                        metadata={"is_demand_rescue": True}
                    )

        # Scenario: Aftercare Only
        if self.scenario == "aftercare_only" or (player_climaxed and all_partners_climaxed):
            aftercare_choice = next(
                (c for c in choices if "aftercare" in str(c.get("sub_intent", "")).lower() or c.get("intent") in ("affection_touch", "dialogue_exit")),
                None
            )
            if aftercare_choice:
                return IntimacyAction(
                    action_type="aftercare",
                    target_npc=target_name,
                    action_text=str(aftercare_choice.get("label")),
                    sub_intent="aftercare",
                    posture="resting",
                    metadata={"is_aftercare": True}
                )
            return IntimacyAction(
                action_type="aftercare",
                target_npc=target_name,
                action_text=f"Pull blankets close, hold {target_name} tenderly, and rest in the warm afterglow.",
                sub_intent="aftercare",
                posture="resting",
                metadata={"is_aftercare": True}
            )

        # Scenario: Sudden Initiation (begins directly at oral/manual/intercourse)
        if self.scenario == "sudden_initiation" and turn == 1:
            escalated_choice = next(
                (c for c in choices if c.get("sub_intent") in ("oral_give", "manual_give", "intercourse")),
                None
            )
            if escalated_choice:
                return IntimacyAction(
                    action_type=escalated_choice.get("sub_intent", "manual_give"),
                    target_npc=target_name,
                    action_text=str(escalated_choice.get("label")),
                    sub_intent=escalated_choice.get("sub_intent"),
                    posture="straddling",
                    metadata={"sudden_initiation": True}
                )
            return IntimacyAction(
                action_type="manual_give",
                target_npc=target_name,
                action_text=f"Impulsively slide your hands beneath {target_name}'s clothes, stroking intimately.",
                sub_intent="manual_give",
                posture="straddling",
                metadata={"sudden_initiation": True}
            )

        # Full Progression Lifecycle:
        # Turn 1-2: Foreplay / Kissing / Gentle Caresses
        # Turn 3-4: Oral / Manual Stimulation
        # Turn 5-7: Intercourse / Peak Excitement
        # Turn 8+: Climax & Release
        if turn <= 2 and self.scenario == "full_progression":
            foreplay_choice = next(
                (c for c in choices if c.get("sub_intent") in ("kiss", "foreplay")),
                None
            )
            if foreplay_choice:
                return IntimacyAction(
                    action_type="foreplay",
                    target_npc=target_name,
                    action_text=str(foreplay_choice.get("label")),
                    sub_intent="foreplay",
                    posture="embracing",
                )

        if turn in (3, 4) and self.scenario == "full_progression":
            oral_manual_choice = next(
                (c for c in choices if c.get("sub_intent") in ("oral_give", "oral_receive", "oral_mutual", "manual_give", "manual_receive")),
                None
            )
            if oral_manual_choice:
                return IntimacyAction(
                    action_type=oral_manual_choice.get("sub_intent", "oral_give"),
                    target_npc=target_name,
                    action_text=str(oral_manual_choice.get("label")),
                    sub_intent=oral_manual_choice.get("sub_intent"),
                    posture="kneeling" if "oral" in str(oral_manual_choice.get("sub_intent")) else "embracing",
                )

        # Escalated penetrative or peak choice
        pen_choice = next(
            (c for c in choices if c.get("sub_intent") in ("intercourse", "anal_give", "anal_receive") and not player_spent),
            None
        )
        if pen_choice:
            return IntimacyAction(
                action_type=pen_choice.get("sub_intent", "intercourse"),
                target_npc=target_name,
                action_text=str(pen_choice.get("label")),
                sub_intent=pen_choice.get("sub_intent"),
                posture="straddling",
            )

        # Fallback to any non-exit choice
        valid_choices = [c for c in choices if not c.get("ends_dialogue")]
        if valid_choices:
            chosen = self.rng.choice(valid_choices)
            return IntimacyAction(
                action_type=chosen.get("sub_intent") or "intimate_act",
                target_npc=target_name,
                action_text=str(chosen.get("label")),
                sub_intent=chosen.get("sub_intent"),
            )

        # Default fallback
        return IntimacyAction(
            action_type="foreplay",
            target_npc=target_name,
            action_text=f"Hold {target_name} close, maintaining warm and tender physical contact.",
            sub_intent="foreplay",
            posture="embracing",
        )
