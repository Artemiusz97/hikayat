from __future__ import annotations
"""
Autonomous Navigator AI for Hikayat World Simulation.
Implements a goal-directed waypoint seeker with configurable chaos/deviation rates
(backtracking, jumping directly to stage 2 destinations, exploring unlisted sub-areas, and resting).
"""
import random
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple

import db
from mechanics.world.waypoints.matching import check_location_matches_waypoint
from mechanics.world.locations.movement import (
    parse_tiered_location,
    format_tiered_location_string,
)
from mechanics.system.time_engine import is_sleep_time


def get_connected_locations(session_id: int, current_location: str, scenario_key: str = "fantasy") -> List[str]:
    """Finds navigable adjacent places and sub-areas for current_location."""
    if not session_id:
        return []
    existing = db.get_session_locations(session_id)
    if not existing:
        return []

    curr_z, curr_p, curr_s = parse_tiered_location(current_location, scenario_key, session_id=session_id)
    connected = []

    # 1. Other sub-areas within the same primary place
    for r in existing:
        z = r.get("zone_name") or ""
        p = r.get("primary_name") or ""
        s = r.get("sub_name") or "Main Area"
        if z.lower() == curr_z.lower() and p.lower() == curr_p.lower():
            loc_str = format_tiered_location_string(z, p, s)
            if loc_str != current_location and loc_str not in connected:
                connected.append(loc_str)

    # 2. Other primary places in the same zone
    for r in existing:
        z = r.get("zone_name") or ""
        p = r.get("primary_name") or ""
        s = r.get("sub_name") or "Main Area"
        if z.lower() == curr_z.lower() and p.lower() != curr_p.lower():
            loc_str = format_tiered_location_string(z, p, s)
            if loc_str not in connected:
                connected.append(loc_str)

    # 3. Primary gateways of other zones (for cross-zone travel)
    other_zones = set()
    for r in existing:
        z = r.get("zone_name") or ""
        p = r.get("primary_name") or ""
        s = r.get("sub_name") or "Main Area"
        if z.lower() != curr_z.lower() and z not in other_zones:
            other_zones.add(z)
            connected.append(format_tiered_location_string(z, p, s))

    return connected



@dataclass
class NavigatorAction:
    """Represents a discrete turn action chosen by the Navigator AI."""
    action_type: str  # "travel", "skill_check", "rest", "backtrack", "stage_jump"
    target_location: str
    action_text: str
    is_quest_action: bool = False
    quest_id: str = ""
    sub_obj_id: Optional[int] = None
    stage_index: int = 1
    reasoning: str = ""


class NavigatorAI:
    """Autonomous agent that evaluates current position and waypoints to make traversal decisions."""

    def __init__(self, rng: Optional[random.Random] = None, chaos_rate: float = 0.15):
        self.rng = rng or random.Random()
        self.chaos_rate = chaos_rate
        self.location_history: List[str] = []

    def record_location(self, loc: str):
        if loc:
            self.location_history.append(loc)
            if len(self.location_history) > 20:
                self.location_history.pop(0)

    def choose_action(
        self,
        session_id: int,
        current_location: str,
        current_minute: int = 480,
        scenario_key: str = "fantasy",
    ) -> NavigatorAction:
        """Determines the best next action: travel, skill check, stage jump, or rest."""
        self.record_location(current_location)

        # 1. Check if bedtime and rest makes sense (e.g. night time)
        if is_sleep_time(current_minute) and self.rng.random() < 0.25:
            return NavigatorAction(
                action_type="rest",
                target_location=current_location,
                action_text="I return to camp and sleep through the night until morning in bed",
                reasoning="Night time rest cycle",
            )

        # 2. Query active quest waypoints
        active_wps = db.get_all_session_active_waypoints(session_id)

        if not active_wps:
            # All active waypoints resolved; wander through connected locations
            connected = get_connected_locations(session_id, current_location, scenario_key)
            dest = self.rng.choice(connected) if connected else current_location
            return NavigatorAction(
                action_type="travel",
                target_location=dest,
                action_text=f"I explore onward toward {dest}",
                reasoning="Free exploration after waypoints completed",
            )

        # Prioritize any active waypoint that can be fulfilled at current location
        local_interactive_wps = [
            w for w in active_wps
            if check_location_matches_waypoint(current_location, w.get("target_location", ""))
            and w.get("completion_trigger") in ("skill_check", "resource_progress", "defeat_target", "inspect_prop")
        ]
        target_wp = self.rng.choice(local_interactive_wps) if local_interactive_wps else self.rng.choice(active_wps)
        wp_loc = target_wp.get("target_location", "")
        wp_trigger = target_wp.get("completion_trigger", "arrival")
        stage_idx = int(target_wp.get("stage_index", 1))
        sub_id = target_wp.get("sub_obj_id")
        quest_id = target_wp.get("quest_id", "")
        stage_label = target_wp.get("stage_label", "Objective")

        at_target = check_location_matches_waypoint(current_location, wp_loc)

        # 3. If at target location and requires a skill check -> perform the objective action!
        if at_target and wp_trigger in ("skill_check", "resource_progress", "defeat_target", "inspect_prop"):
            return NavigatorAction(
                action_type="skill_check",
                target_location=current_location,
                action_text=f"I thoroughly search {current_location} and investigate to fulfill: {stage_label}",
                is_quest_action=True,
                quest_id=quest_id,
                sub_obj_id=sub_id,
                stage_index=stage_idx,
                reasoning=f"Executing required skill check for stage #{stage_idx}",
            )

        # 4. Inject Chaos Deviations (15% rate)
        if self.rng.random() < self.chaos_rate:
            chaos_roll = self.rng.random()

            # 4a. Stage-Jump: Travel directly to Stage 2's location to test arrival stage bypass
            if chaos_roll < 0.35 and stage_idx == 1:
                all_wps = db.get_quest_waypoints(session_id, quest_id, sub_id) or []
                stage_2_wp = next((w for w in all_wps if w.get("stage_index") == 2), None)
                if stage_2_wp and stage_2_wp.get("target_location"):
                    s2_loc = stage_2_wp["target_location"]
                    return NavigatorAction(
                        action_type="stage_jump",
                        target_location=s2_loc,
                        action_text=f"I bypass the perimeter and head straight to {s2_loc}",
                        reasoning="Testing direct travel bypass of Stage 1 arrival scout",
                    )

            # 4b. Backtracking to previous location
            if chaos_roll < 0.70 and len(self.location_history) >= 2:
                prev_loc = self.location_history[-2]
                if prev_loc != current_location:
                    return NavigatorAction(
                        action_type="backtrack",
                        target_location=prev_loc,
                        action_text=f"I retrace my steps and backtrack to {prev_loc}",
                        reasoning="Chaos deviation: backtracking",
                    )

            # 4c. Wander to a random adjacent connected spot
            connected = get_connected_locations(session_id, current_location, scenario_key)
            if connected:
                wander_loc = self.rng.choice(connected)
                return NavigatorAction(
                    action_type="travel",
                    target_location=wander_loc,
                    action_text=f"I take a detour to explore {wander_loc}",
                    reasoning="Chaos deviation: random local wander",
                )

        # 5. Goal-Directed Navigation: Travel toward target waypoint location
        dest_loc = wp_loc or current_location
        return NavigatorAction(
            action_type="travel",
            target_location=dest_loc,
            action_text=f"I head directly to {dest_loc} to reach the objective",
            reasoning=f"Navigating to waypoint target: {dest_loc}",
        )
