from __future__ import annotations
"""
Narrative Actor AI for Hikayat Narrative & Turn Lifecycle Simulator.

Implements synthetic behavioral archetypes to drive narrative choice selection
and generate varied, scenario-grounded natural language action prose:
1. Conversationalist: Prioritizes social interactions, dialogue, gossip, and phone comms.
2. Cautious Explorer: Investigates clues, inspects boards, scouts areas, chooses safe skill checks.
3. Bold Adventurer: Pursues quest objectives, combat encounters, and high-difficulty actions.
4. Chaotic Provocateur: Tests boundary conditions, exits conversations abruptly, mixes item actions.
"""
import random
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class NarrativeAction:
    """Represents a planned action chosen or formulated by a synthetic narrative actor."""
    action_type: str  # "choice", "dialogue", "examine", "travel", "combat", "rest", "custom_prose"
    action_text: str
    target_entity: Optional[str] = None
    stat: str = "FREE"
    requirement: int = 0
    mp_cost: int = 0
    is_quest_action: bool = False
    is_free_action: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


SUPPORTED_ARCHETYPES = [
    "conversationalist",
    "cautious_explorer",
    "bold_adventurer",
    "chaotic_provocateur",
]


class NarrativeActorAI:
    """Autonomous agent driving choice selection and free-form prose formulation."""

    def __init__(self, archetype: str = "conversationalist", seed: Optional[int] = None):
        self.archetype = archetype.lower() if archetype in SUPPORTED_ARCHETYPES else "conversationalist"
        self.rng = random.Random(seed)
        self.action_history: List[NarrativeAction] = []

    def choose_action(
        self,
        session: Dict[str, Any],
        choices: List[Dict[str, Any]],
        current_npcs: Optional[List[Dict[str, Any]]] = None,
        turn: int = 1,
        scenario: str = "fantasy",
    ) -> NarrativeAction:
        """Selects the next action given available structured choices and environment state."""
        current_npcs = current_npcs or []
        dialogue_partner = session.get("dialogue_partner")

        # 1. If choices are provided, evaluate and rank based on archetype
        if choices:
            valid_choices = [c for c in choices if isinstance(c, dict) and c.get("label")]
            if valid_choices:
                action = self._rank_and_pick_choice(valid_choices, dialogue_partner, current_npcs, scenario)
                self.action_history.append(action)
                return action

        # 2. Fallback: Generate free-form natural language action prose
        prose = self.generate_free_form_prose(
            location=session.get("current_location", "Main Area"),
            current_npcs=current_npcs,
            scenario=scenario,
            dialogue_partner=dialogue_partner,
        )
        target_name = dialogue_partner
        if not target_name and current_npcs:
            first_npc = current_npcs[0]
            target_name = first_npc.get("name") if isinstance(first_npc, dict) else str(first_npc).strip()

        action = NarrativeAction(
            action_type="custom_prose",
            action_text=prose,
            target_entity=target_name,
        )
        self.action_history.append(action)
        return action

    def _rank_and_pick_choice(
        self,
        choices: List[Dict[str, Any]],
        dialogue_partner: Optional[str],
        current_npcs: List[Dict[str, Any]],
        scenario: str,
    ) -> NarrativeAction:
        """Ranks candidate choices according to behavioral archetype preferences."""
        def score_choice(c: Dict[str, Any]) -> float:
            label = str(c.get("label", "")).lower()
            stat = str(c.get("stat", "FREE")).upper()
            raw_req = c.get("requirement")
            try:
                req = int(raw_req or 0)
            except (ValueError, TypeError):
                req = 0
            is_quest = bool(c.get("is_quest_action", False))

            base_score = self.rng.uniform(0.1, 1.0)
            if self.action_history and c.get("label") == self.action_history[-1].action_text:
                base_score -= 15.0

            if self.archetype == "conversationalist":
                if any(w in label for w in ("talk", "ask", "speak", "greet", "whisper", "tell", "discuss", "chat")):
                    base_score += 10.0
                if stat == "CHA":
                    base_score += 4.0
                if dialogue_partner and dialogue_partner.lower() in label:
                    base_score += 5.0

            elif self.archetype == "cautious_explorer":
                if any(w in label for w in ("examine", "inspect", "look", "search", "investigate", "read", "study")):
                    base_score += 10.0
                if stat in ("PER", "INT"):
                    base_score += 4.0
                if req <= 6:  # Prefers safe DCs
                    base_score += 3.0

            elif self.archetype == "bold_adventurer":
                if is_quest:
                    base_score += 12.0
                if any(w in label for w in ("strike", "attack", "advance", "charge", "cast", "enter", "confront")):
                    base_score += 8.0
                if stat in ("STR", "AGI", "END"):
                    base_score += 3.0

            elif self.archetype == "chaotic_provocateur":
                if any(w in label for w in ("leave", "walk away", "ignore", "take", "open", "distract", "push")):
                    base_score += 8.0
                if req >= 12:  # Likes risky challenges
                    base_score += 5.0

            return base_score

        best_choice = max(choices, key=score_choice)
        raw_req = best_choice.get("requirement")
        try:
            choice_req = int(raw_req or 0)
        except (ValueError, TypeError):
            choice_req = 0

        raw_mp = best_choice.get("mp_cost")
        try:
            choice_mp = int(raw_mp or 0)
        except (ValueError, TypeError):
            choice_mp = 0

        return NarrativeAction(
            action_type="choice",
            action_text=best_choice.get("label", "Take action"),
            target_entity=best_choice.get("target_npc"),
            stat=best_choice.get("stat", "FREE"),
            requirement=choice_req,
            mp_cost=choice_mp,
            is_quest_action=bool(best_choice.get("is_quest_action", False)),
            is_free_action=(best_choice.get("stat", "FREE") in ("FREE", "NONE") or choice_req == 0),
            metadata=best_choice,
        )

    def generate_free_form_prose(
        self,
        location: str,
        current_npcs: List[Any],
        scenario: str = "fantasy",
        dialogue_partner: Optional[str] = None,
    ) -> str:
        """Generates realistic natural language prose reflecting the actor's archetype."""
        npc_names = [
            n.get("name") if isinstance(n, dict) else str(n).strip()
            for n in current_npcs
            if (isinstance(n, dict) and n.get("name")) or (isinstance(n, str) and n.strip())
        ]
        lead_npc = dialogue_partner or (npc_names[0] if npc_names else None)

        if self.archetype == "conversationalist":
            if lead_npc:
                templates = [
                    f"Turn towards {lead_npc} and ask how their day has been going.",
                    f"Offer a friendly greeting to {lead_npc} and bring up the recent campus news.",
                    f"Ask {lead_npc} if they want to sit down and discuss the upcoming schedule.",
                    f"Lean in and whisper to {lead_npc} about what happened earlier today.",
                ]
            else:
                templates = [
                    "Look around the room to see if anyone familiar is nearby.",
                    "Step toward the counter and introduce myself to whoever is working.",
                    "Check my phone messages to see if anyone reached out.",
                ]

        elif self.archetype == "cautious_explorer":
            templates = [
                f"Carefully survey {location}, checking for anything unusual or out of place.",
                "Inspect the desk and examine the documents resting on top.",
                "Look closely at the notice board for new announcements and job postings.",
                "Search the corner of the room to see what items might be stored there.",
            ]

        elif self.archetype == "bold_adventurer":
            templates = [
                f"Confidently step through the doorway and announce my arrival in {location}.",
                "Ready my gear and inspect the immediate perimeter for any sign of trouble.",
                "Take the lead and press forward into the next adjoining corridor.",
                "Directly approach the main objective marker and prepare for whatever comes next.",
            ]

        else:  # chaotic_provocateur
            if lead_npc:
                templates = [
                    f"Nod briefly to {lead_npc}, then immediately turn around and inspect the back window.",
                    f"Adjust my coat while glancing past {lead_npc} toward the opposite doorway.",
                    f"Interrupt the conversation to examine the strange mechanism nearby.",
                ]
            else:
                templates = [
                    "Rummage through my bag while examining the nearest exit.",
                    "Test the lock on the side door to see if it gives way.",
                    "Step past the entryway without stopping to greet anyone.",
                ]

        return self.rng.choice(templates)
