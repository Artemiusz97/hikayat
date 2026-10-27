from __future__ import annotations
"""
tests/simulators/stealth/actor_ai.py
Heuristic AI decision maker for simulated covert infiltration missions.

Supports distinct agent profiles:
- 'ghost': Maximizes stealth checks, stays in shadows, avoids confrontation, patient.
- 'heavy': Clumsy infiltrator wearing heavy gear with noise drag, testing detection escalation.
- 'specialist': Actively deploys environmental distractions and tools to shed detection meter.
- 'chaos': Randomized actions exploring edge cases and strange transitions.
"""
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class StealthAction:
    """Action payload selected by the covert AI actor."""
    action_type: str  # "sneak_move", "hide_in_shadows", "distraction", "lockpick", "recon", "ambush_strike", "wait_quietly"
    label: str
    target_entity: Optional[str] = None
    target_room: Optional[str] = None
    noise_category: str = "quiet"
    custom_action_text: str = ""
    is_ambush: bool = False


SUPPORTED_PROFILES = ["ghost", "heavy", "specialist", "chaos"]


class StealthActorAI:
    """Actor decision engine for stealth simulation missions."""

    def __init__(self, profile: str = "ghost", rng: Optional[random.Random] = None):
        self.profile = profile.lower() if profile.lower() in SUPPORTED_PROFILES else "ghost"
        self.rng = rng or random.Random()

    def choose_action(
        self,
        session: Dict[str, Any],
        stealth_state: Dict[str, Any],
        current_sector: Dict[str, Any],
        adjacent_sectors: List[Dict[str, Any]],
        sentries_present: List[Dict[str, Any]],
        turn: int,
        objective_reached: bool = False,
    ) -> StealthAction:
        """Determines the next covert action based on the agent's profile and situational danger."""
        detection_meter = stealth_state.get("detection_meter", 0)
        alert_stage = stealth_state.get("alert_level", "unaware").lower()
        is_hidden = stealth_state.get("is_hidden", True)
        unpatrolled_turns = stealth_state.get("unpatrolled_turns", 0)

        # CHAOS PROFILE: Pure random permutations
        if self.profile == "chaos":
            return self._choose_chaos_action(sentries_present, adjacent_sectors)

        # SPECIALIST PROFILE: Proactively sheds meter with distractions when suspicion rises
        if self.profile == "specialist":
            if detection_meter >= 35 or alert_stage in ("suspicious", "searching"):
                if self.rng.random() < 0.75:
                    return StealthAction(
                        action_type="distraction",
                        label="Throw stone to distract sentry away from corridor",
                        custom_action_text="Throws a small ceramic pebble against the far bulkhead to redirect guard attention.",
                        noise_category="distraction"
                    )

        # GHOST PROFILE: Super patient, waits in shadows to allow natural decay if meter is high
        if self.profile == "ghost":
            if detection_meter > 50 and not sentries_present and unpatrolled_turns < 3:
                return StealthAction(
                    action_type="wait_quietly",
                    label="Wait motionless in shadows to let guard patrol pass",
                    custom_action_text="Holds breath, clinging to the dark recesses of the ceiling alcove until footsteps fade.",
                    noise_category="silent"
                )

        # HEAVY PROFILE: Tends to rush forward or strike directly, occasionally failing stealth
        if self.profile == "heavy":
            if sentries_present and (detection_meter >= 50 or alert_stage == "searching"):
                # Attempt preemptive ambush strike or clumsy rush before getting caught
                target_sentry = sentries_present[0].get("name", "Sentry")
                return StealthAction(
                    action_type="ambush_strike",
                    label=f"Launch preemptive ambush strike against {target_sentry}",
                    target_entity=target_sentry,
                    custom_action_text=f"Breaks cover with a heavy forward lunge, striking at {target_sentry}!",
                    noise_category="loud",
                    is_ambush=True
                )

        # STANDARD PROGRESSION:
        # If objective is reached, move toward extraction
        if objective_reached:
            exit_candidates = [s for s in reversed(adjacent_sectors) if s.get("is_exit")]
            next_sector = exit_candidates[0] if exit_candidates else (adjacent_sectors[-1] if adjacent_sectors else None)
            dest_name = next_sector.get("name", "Extraction Point") if next_sector else "Exit"
            return StealthAction(
                action_type="sneak_move",
                label=f"Slip quietly toward extraction route at {dest_name}",
                target_room=dest_name,
                custom_action_text=f"Quietly slips along the perimeter toward {dest_name}.",
                noise_category="normal" if self.profile == "heavy" else "quiet"
            )

        # If current sector has an objective item and sentry is unaware or absent (or heavy forces it), interact/loot
        if current_sector.get("has_objective") and (not sentries_present or detection_meter < 30 or self.profile == "heavy"):
            return StealthAction(
                action_type="interact_objective",
                label="Carefully pick vault lock to retrieve target objective",
                custom_action_text="Applies fine-tuned lockpicks to the electronic data terminal with steady hands.",
                noise_category="normal" if self.profile == "heavy" else "quiet"
            )

        # If sentry is blocking the current room with high alertness, ghost/specialist hide or distract
        if sentries_present and self.profile != "heavy":
            if detection_meter >= 50 or alert_stage in ("suspicious", "searching"):
                if self.rng.random() < 0.5:
                    return StealthAction(
                        action_type="distraction",
                        label="Deploy sound decoy to draw sentry away",
                        custom_action_text="Taps the metal railing lightly, creating an echo down the opposite hallway.",
                        noise_category="distraction"
                    )
                else:
                    return StealthAction(
                        action_type="hide_in_shadows",
                        label="Crouch behind storage crates and freeze",
                        custom_action_text="Dives into the deep shadow behind cargo containers, pressing flat against the cold floor.",
                        noise_category="silent"
                    )
            elif self.profile == "ghost" and self.rng.random() < 0.4:
                # Ghost tries silent takedown
                target_sentry = sentries_present[0].get("name", "Sentry")
                return StealthAction(
                    action_type="silent_takedown",
                    label=f"Execute silent takedown on {target_sentry}",
                    target_entity=target_sentry,
                    custom_action_text=f"Creeps up silently behind {target_sentry} and applies a rapid sleeper hold.",
                    noise_category="quiet"
                )

        # Otherwise, move forward to adjacent sector toward the objective
        if adjacent_sectors:
            best_sector = next((s for s in adjacent_sectors if s.get("has_objective")), adjacent_sectors[-1])
            dest_name = best_sector.get("name", "Next Chamber")
            return StealthAction(
                action_type="sneak_move",
                label=f"Advance quietly toward {dest_name}",
                target_room=dest_name,
                custom_action_text=f"Stalks through the shadows toward {dest_name}.",
                noise_category="quiet"
            )

        # Fallback quiet recon
        return StealthAction(
            action_type="recon",
            label="Scout security cameras and sentry patrol patterns",
            custom_action_text="Carefully peers around the corner, observing camera blind spots.",
            noise_category="silent"
        )

    def _choose_chaos_action(self, sentries: List[Dict[str, Any]], adjacent: List[Dict[str, Any]]) -> StealthAction:
        """Selects a random action to stress test permutations and edge boundaries."""
        actions = [
            StealthAction("sneak_move", "Advance recklessly", noise_category="normal"),
            StealthAction("hide_in_shadows", "Drop to ground", noise_category="silent"),
            StealthAction("distraction", "Throw random object", noise_category="distraction"),
            StealthAction("wait_quietly", "Wait motionless", noise_category="silent"),
            StealthAction("recon", "Analyze surroundings", noise_category="silent"),
        ]
        if sentries:
            s_name = sentries[0].get("name", "Guard")
            actions.append(StealthAction("ambush_strike", f"Ambush {s_name}", target_entity=s_name, noise_category="loud", is_ambush=True))
            actions.append(StealthAction("silent_takedown", f"Takedown {s_name}", target_entity=s_name, noise_category="quiet"))

        return self.rng.choice(actions)
