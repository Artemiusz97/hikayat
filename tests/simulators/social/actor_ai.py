from __future__ import annotations
"""
Social Actor AI for Hikayat Social Dynamics & Persona Simulator.

Implements behavioral archetypes for synthetic social actors:
1. Diplomat: Maximizes broad goodwill, gifts, conflict mediation, and faction balance.
2. Operative: Infiltrates cliques, collects dirt/mannerisms, trades rumors, manipulates factions.
3. Provocateur: Pushes social boundaries, triggers rivalries, tests negative relationship cascades.
4. Romance Seeker: Pursues milestones, tests flirting, attempts romantic confessions at threshold.
"""
import random
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple


@dataclass
class SocialAction:
    """Represents a planned or executed social interaction by a synthetic actor."""
    action_type: str  # "chat", "compliment", "insult", "gift", "gossip", "favor", "confess_romance", "inquire_trait"
    target_npc: str
    action_text: str
    affinity_delta: int = 0
    topic: Optional[str] = None
    gift_item: Optional[str] = None
    is_romantic: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


SUPPORTED_ARCHETYPES = [
    "diplomat",
    "operative",
    "provocateur",
    "romance_seeker",
]


class SocialActorAI:
    """Synthetic social player model driving dialogue, gifting, gossip, and romance milestones."""

    def __init__(self, archetype: str = "diplomat", seed: Optional[int] = None):
        self.archetype = archetype.lower() if archetype in SUPPORTED_ARCHETYPES else "diplomat"
        self.rng = random.Random(seed)
        self.interaction_history: List[SocialAction] = []
        self.confession_attempted_targets: set[str] = set()

    def choose_action(
        self,
        session_id: int,
        contacts: List[Dict[str, Any]],
        directory_candidates: List[Dict[str, Any]],
        factions: List[Dict[str, Any]],
        turn: int,
        scenario_key: str = "high_school_drama",
        location: str = "",
    ) -> SocialAction:
        """Selects the next social action based on the agent's archetype, environment, and location."""
        # 1. Determine eligible targets from contacts or directory
        all_pool = list(contacts)
        if directory_candidates:
            # Sample some directory entries to simulate encountering new peers
            all_pool.extend(directory_candidates[:8])

        if not all_pool:
            # Fallback default target
            default_npc = "Student Council Rep" if "school" in scenario_key else "Guild Handler"
            return SocialAction(
                action_type="chat",
                target_npc=default_npc,
                action_text=f"Engage in friendly introductory chatter with {default_npc}.",
                affinity_delta=2,
            )

        # Separate targets into peers vs non-peers (faculty / adults)
        def is_peer(entry: Dict[str, Any]) -> bool:
            role = str(entry.get("role", "")).lower()
            grade = str(entry.get("grade", "")).lower()
            clique = str(entry.get("clique", "")).lower()
            name = str(entry.get("name", "")).lower()
            if any(k in role for k in ("teacher", "coach", "nurse", "principal", "clerk", "guard", "librarian")):
                return False
            if "faculty" in grade or "faculty" in clique:
                return False
            if any(k in name for k in ("dr.", "coach", "principal", "nurse", "madame")):
                return False
            return True

        peers = [e for e in all_pool if is_peer(e)]
        non_peers = [e for e in all_pool if not is_peer(e)]

        # Dispatch based on archetype
        if self.archetype == "romance_seeker":
            action = self._choose_romance_action(peers, non_peers, factions, turn, scenario_key, location=location)
        elif self.archetype == "operative":
            action = self._choose_operative_action(all_pool, factions, turn, scenario_key, location=location)
        elif self.archetype == "provocateur":
            action = self._choose_provocateur_action(all_pool, factions, turn, scenario_key, location=location)
        else:  # diplomat
            action = self._choose_diplomat_action(all_pool, factions, turn, scenario_key, location=location)

        self.interaction_history.append(action)
        return action

    def _choose_diplomat_action(
        self,
        pool: List[Dict[str, Any]],
        factions: List[Dict[str, Any]],
        turn: int,
        scenario: str,
        location: str = "",
    ) -> SocialAction:
        """Diplomats build rapport, give gifts, inquire about family, and mediate factions."""
        target = self.rng.choice(pool)
        target_name = target.get("name", "Unknown NPC")
        current_score = target.get("relationship_score", 0)

        # 20% chance to inquire about family / siblings
        if self.rng.random() < 0.20:
            return SocialAction(
                action_type="ask_about_family",
                target_npc=target_name,
                action_text=f"Inquire warmly with {target_name} about their family and how their siblings are doing.",
                affinity_delta=self.rng.randint(3, 6),
                topic="family",
            )

        # 15% chance for a considerate phone text check-in
        if self.rng.random() < 0.20:
            return SocialAction(
                action_type="phone_text",
                target_npc=target_name,
                action_text=f"Send a considerate text to {target_name} wishing them a productive day.",
                affinity_delta=self.rng.randint(2, 4),
                topic="phone_chat",
                metadata={"intent": "chat"},
            )

        # 25% chance to offer gift
        if self.rng.random() < 0.30:
            gifts = ["Handmade Bento", "Rare Tea Leaves", "Polished Trinket", "Study Notes", "Artisan Pastry"]
            chosen_gift = self.rng.choice(gifts)
            return SocialAction(
                action_type="gift",
                target_npc=target_name,
                action_text=f"Present a thoughtful gift of {chosen_gift} to {target_name}.",
                affinity_delta=self.rng.randint(6, 12),
                gift_item=chosen_gift,
            )

        # 20% chance to mediate or seek faction favor
        if factions and self.rng.random() < 0.25:
            fac = self.rng.choice(factions)
            fac_name = fac.get("name", "Local Faction")
            return SocialAction(
                action_type="favor",
                target_npc=target_name,
                action_text=f"Discuss mutual assistance and alliance terms with {target_name} regarding {fac_name}.",
                affinity_delta=self.rng.randint(3, 7),
                metadata={"faction_id": fac.get("faction_id", "")},
            )

        # Positive chat or compliment
        if current_score < 30 or self.rng.random() < 0.5:
            return SocialAction(
                action_type="compliment",
                target_npc=target_name,
                action_text=f"Offer genuine praise to {target_name} for their recent dedication and skill.",
                affinity_delta=self.rng.randint(4, 8),
            )
        else:
            return SocialAction(
                action_type="chat",
                target_npc=target_name,
                action_text=f"Share a warm and encouraging conversation with {target_name} about their interests.",
                affinity_delta=self.rng.randint(2, 5),
            )

    def _choose_operative_action(
        self,
        pool: List[Dict[str, Any]],
        factions: List[Dict[str, Any]],
        turn: int,
        scenario: str,
        location: str = "",
    ) -> SocialAction:
        """Operatives interrogate traits, extract hidden mannerisms, probe family webs, and trade rumors."""
        target = self.rng.choice(pool)
        target_name = target.get("name", "Unknown NPC")

        # 25% chance to probe behavioral mannerisms
        if self.rng.random() < 0.25:
            return SocialAction(
                action_type="probe_mannerism",
                target_npc=target_name,
                action_text=f"Observe {target_name}'s speech cadence, subtle gestures, and nervous mannerisms under pressure.",
                affinity_delta=self.rng.randint(1, 3),
                topic="mannerisms",
            )

        # 25% chance to dig for hidden personality traits
        if self.rng.random() < 0.35:
            return SocialAction(
                action_type="inquire_trait",
                target_npc=target_name,
                action_text=f"Observe {target_name} closely during interaction to deduce hidden habits and quirks.",
                affinity_delta=self.rng.randint(1, 4),
                topic="personality_traits",
            )

        # 20% chance to probe family ties & sibling background
        if self.rng.random() < 0.30:
            return SocialAction(
                action_type="ask_about_family",
                target_npc=target_name,
                action_text=f"Subtly probe {target_name} regarding their family ties and sibling dynamics.",
                affinity_delta=self.rng.randint(1, 4),
                topic="family_intel",
            )

        # 15% chance to spread gossip or extract rumors
        if len(pool) > 1 and self.rng.random() < 0.50:
            other_npc = self.rng.choice([e for e in pool if e.get("name") != target_name] or pool)
            other_name = other_npc.get("name", "Someone")
            return SocialAction(
                action_type="gossip",
                target_npc=target_name,
                action_text=f"Subtly probe {target_name} regarding confidential rumors about {other_name}.",
                affinity_delta=self.rng.randint(-2, 4),
                topic=other_name,
            )

        # Pragmatic chat
        return SocialAction(
            action_type="chat",
            target_npc=target_name,
            action_text=f"Conduct a calculated, inquisitive discussion with {target_name} to test their loyalty.",
            affinity_delta=self.rng.randint(1, 3),
        )

    def _choose_provocateur_action(
        self,
        pool: List[Dict[str, Any]],
        factions: List[Dict[str, Any]],
        turn: int,
        scenario: str,
        location: str = "",
    ) -> SocialAction:
        """Provocateurs deliberately test turn-offs, insult peers, incite sibling friction, and test emotional thresholds."""
        target = self.rng.choice(pool)
        target_name = target.get("name", "Unknown NPC")

        # 30% chance to trigger an explicit turn-off or boundary test
        if self.rng.random() < 0.30:
            turn_off_actions = [
                f"Hurry up {target_name}, stop wasting time and get on with it!",
                f"Dismiss {target_name} with cold dead silence and emotional detachment.",
                f"Loudly broadcast private details to draw careless public exposure around {target_name}.",
                f"Yank {target_name} roughly by the sleeve in a clumsy and aggressive display.",
            ]
            return SocialAction(
                action_type="trigger_turn_off",
                target_npc=target_name,
                action_text=self.rng.choice(turn_off_actions),
                affinity_delta=-self.rng.randint(6, 12),
            )

        # 35% severe insult / provocation (tests cross-sibling protective hostility ripple)
        if self.rng.random() < 0.55:
            insults = [
                f"Mock {target_name}'s competence and question their status in the social hierarchy.",
                f"Openly challenge {target_name}'s authority in front of onlookers with harsh ridicule.",
                f"Sardonically dismiss {target_name}'s family upbringing and opinions in public.",
            ]
            return SocialAction(
                action_type="insult",
                target_npc=target_name,
                action_text=self.rng.choice(insults),
                affinity_delta=-self.rng.randint(6, 15),
            )

        # 20% antagonistic gossip
        if len(pool) > 1 and self.rng.random() < 0.50:
            rival = self.rng.choice([e for e in pool if e.get("name") != target_name] or pool)
            rival_name = rival.get("name", "a peer")
            return SocialAction(
                action_type="gossip",
                target_npc=target_name,
                action_text=f"Spread a provocative rumor to {target_name} about {rival_name} to stir conflict.",
                affinity_delta=-self.rng.randint(1, 6),
                topic=rival_name,
            )

        # 15% boundary-probing aggressive conversation
        return SocialAction(
            action_type="chat",
            target_npc=target_name,
            action_text=f"Engage {target_name} in an aggressive, sharp-tongued debate that tests their patience.",
            affinity_delta=-self.rng.randint(1, 4),
        )

    def _choose_romance_action(
        self,
        peers: List[Dict[str, Any]],
        non_peers: List[Dict[str, Any]],
        factions: List[Dict[str, Any]],
        turn: int,
        scenario: str,
        location: str = "",
    ) -> SocialAction:
        """Romance Seekers systematically cultivate intimacy, test sensitive spots, manage phone consent, and trigger milestones."""
        # Focus on one primary peer if possible to build score to 70+
        eligible_peers = peers if peers else non_peers
        target = eligible_peers[0] if eligible_peers else {"name": "Classmate"}
        target_name = target.get("name", "Classmate")
        score = target.get("relationship_score", 0)

        # If affinity >= 70 and not attempted yet, attempt romantic confession milestone!
        if score >= 70 and target_name not in self.confession_attempted_targets:
            self.confession_attempted_targets.add(target_name)
            return SocialAction(
                action_type="confess_romance",
                target_npc=target_name,
                action_text=f"Take {target_name} aside to a quiet spot and confess sincere romantic feelings.",
                affinity_delta=10,
                is_romantic=True,
            )

        # If already dating / high intimacy established, systematically test physical intimacy, tactile spots, and phone media
        is_dating = target_name in self.confession_attempted_targets or target.get("track") == "romantic"
        if is_dating and score >= 70:
            roll = self.rng.random()

            # 20% Tactile exploration of sensitive spots
            if roll < 0.20:
                spots = ["nape of the neck", "earlobes", "lower back", "inner thighs", "waist", "collarbones"]
                spot = self.rng.choice(spots)
                return SocialAction(
                    action_type="explore_sensitive_spot",
                    target_npc=target_name,
                    action_text=f"Gently caress and kiss {target_name}'s {spot} in a quiet moment.",
                    affinity_delta=self.rng.randint(6, 10),
                    is_romantic=True,
                    metadata={"target_spot": spot},
                )

            # 15% Phone photo or media request (tested against erotic openness and DC)
            elif roll < 0.35:
                is_spicy = self.rng.random() < 0.65
                desc = (
                    f"Send a late-night private text asking {target_name} for a sultry photo from their bedroom."
                    if is_spicy else
                    f"Send a casual text asking {target_name} to send a cute snapshot of what they are doing."
                )
                return SocialAction(
                    action_type="phone_photo_request",
                    target_npc=target_name,
                    action_text=desc,
                    affinity_delta=2 if not is_spicy else 0,
                    is_romantic=True,
                    metadata={"is_spicy": is_spicy, "intent": "nsfw_photo" if is_spicy else "photo"},
                )

            # 15% Flirty phone texting
            elif roll < 0.50:
                return SocialAction(
                    action_type="phone_text",
                    target_npc=target_name,
                    action_text=f"Send a warm, flirtatious text to {target_name} expressing how much you look forward to seeing them.",
                    affinity_delta=self.rng.randint(3, 6),
                    is_romantic=True,
                    metadata={"intent": "flirt"},
                )

            # 50% Dedicated physical intimacy track simulation
            intimate_roll = self.rng.random()
            if intimate_roll < 0.20:
                return SocialAction(
                    action_type="kiss",
                    target_npc=target_name,
                    action_text=f"Lean in close and share a passionate, tender kiss on the lips with {target_name}.",
                    affinity_delta=self.rng.randint(6, 10),
                    is_romantic=True,
                    metadata={"milestone_event": "kiss"},
                )
            elif intimate_roll < 0.40:
                is_give = self.rng.random() < 0.5
                ev = "oral_give" if is_give else "oral_receive"
                desc = f"Provide passionate oral intimacy to {target_name} in private." if is_give else f"Pleasure {target_name} and receive oral intimacy together."
                return SocialAction(
                    action_type="oral_intimacy",
                    target_npc=target_name,
                    action_text=desc,
                    affinity_delta=self.rng.randint(8, 12),
                    is_romantic=True,
                    metadata={"milestone_event": ev},
                )
            elif intimate_roll < 0.60:
                is_give = self.rng.random() < 0.5
                ev = "anal_give" if is_give else "anal_receive"
                desc = f"Engage in adventurous backdoor intimacy and perform anal with {target_name}." if is_give else f"Experience intimate backdoor penetration and receive anal intimacy with {target_name}."
                return SocialAction(
                    action_type="anal_intimacy",
                    target_npc=target_name,
                    action_text=desc,
                    affinity_delta=self.rng.randint(8, 14),
                    is_romantic=True,
                    metadata={"milestone_event": ev},
                )
            elif intimate_roll < 0.80:
                is_give = self.rng.random() < 0.5
                ev = "manual_give" if is_give else "manual_receive"
                desc = f"Gently stimulate and caress {target_name} with your hands." if is_give else f"Receive manual stimulation from {target_name} in the bedroom."
                return SocialAction(
                    action_type="manual_intimacy",
                    target_npc=target_name,
                    action_text=desc,
                    affinity_delta=self.rng.randint(6, 10),
                    is_romantic=True,
                    metadata={"milestone_event": ev},
                )
            else:
                return SocialAction(
                    action_type="intercourse",
                    target_npc=target_name,
                    action_text=f"Spend a passionate night together in bed making love to {target_name}.",
                    affinity_delta=self.rng.randint(10, 15),
                    is_romantic=True,
                    metadata={"milestone_event": "intercourse"},
                )

        # Otherwise build affinity towards milestone
        roll = self.rng.random()
        if roll < 0.20:
            # Flirty phone text check-in
            return SocialAction(
                action_type="phone_text",
                target_npc=target_name,
                action_text=f"Send a sweet, flirty text to {target_name} checking in on their day.",
                affinity_delta=self.rng.randint(3, 5),
                is_romantic=True,
                metadata={"intent": "flirt"},
            )
        elif roll < 0.45:
            # Thoughtful romantic/personal gift
            gifts = ["Delicate Silver Pendant", "Handwritten Letter", "Sweet Confectionery", "Favorite Floral Bouquet"]
            gift = self.rng.choice(gifts)
            return SocialAction(
                action_type="gift",
                target_npc=target_name,
                action_text=f"Present {target_name} with a personalized {gift} while holding eye contact.",
                affinity_delta=self.rng.randint(8, 14),
                gift_item=gift,
                is_romantic=True,
            )
        elif roll < 0.75:
            # Heartfelt compliment
            return SocialAction(
                action_type="compliment",
                target_npc=target_name,
                action_text=f"Compliment {target_name}'s charm and tell them how much their company is valued.",
                affinity_delta=self.rng.randint(5, 9),
                is_romantic=True,
            )
        else:
            # Intimate conversation
            return SocialAction(
                action_type="chat",
                target_npc=target_name,
                action_text=f"Share a deep, heartfelt conversation with {target_name} about dreams and vulnerabilities.",
                affinity_delta=self.rng.randint(4, 7),
                is_romantic=True,
            )
