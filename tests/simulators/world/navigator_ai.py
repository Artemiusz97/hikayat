from __future__ import annotations
"""
Autonomous Navigator AI for Hikayat World Simulation.
Implements a goal-directed waypoint seeker with configurable chaos/deviation rates,
Dijkstra shortest-path graph routing across SQLite world_edges, obstacle barrier detection,
and dynamic NPC schedule tracking.
"""
import random
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple

import db
from mechanics.world.waypoints.matching import (
    check_location_matches_waypoint,
    get_waypoint_npc_schedule_info,
)
from mechanics.world.locations.movement import (
    parse_tiered_location,
    format_tiered_location_string,
)
from mechanics.world.locations.pathfinding import (
    find_spatial_path,
    evaluate_spatial_route,
    format_node_hierarchy,
)
from mechanics.system.time_engine import is_sleep_time


def get_connected_locations(session_id: int, current_location: str, scenario_key: str = "fantasy") -> List[str]:
    """Finds navigable adjacent places and sub-areas for current_location."""
    if not session_id:
        return []

    # Check SQLite world_nodes first
    try:
        curr_nid = db.resolve_node_id_from_location(session_id, current_location)
        if curr_nid:
            edges = db.get_world_edges_from(session_id, curr_nid)
            if edges:
                adj_locs = []
                for e in edges:
                    t_nid = e.get("to_node_id")
                    if t_nid:
                        loc_str = format_node_hierarchy(session_id, t_nid)
                        if loc_str and loc_str.strip().lower() != current_location.strip().lower() and loc_str not in adj_locs:
                            adj_locs.append(loc_str)
                if adj_locs:
                    return adj_locs
    except Exception:
        pass

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
            if loc_str.strip().lower() != current_location.strip().lower() and loc_str not in connected:
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

    return connected


@dataclass
class NavigatorAction:
    """Represents a discrete turn action chosen by the Navigator AI."""
    action_type: str  # "travel", "skill_check", "rest", "backtrack", "stage_jump", "barrier_halt"
    target_location: str
    action_text: str
    is_quest_action: bool = False
    quest_id: str = ""
    sub_obj_id: Optional[int] = None
    stage_index: int = 1
    reasoning: str = ""
    blockers: List[str] = field(default_factory=list)


class NavigatorAI:
    """Autonomous agent that evaluates current position, waypoints, and spatial graphs to make decisions."""

    def __init__(self, rng: Optional[random.Random] = None, chaos_rate: float = 0.15):
        self.rng = rng or random.Random()
        self.chaos_rate = chaos_rate
        self.location_history: List[str] = []
        self.last_action_type: str = ""

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
        """Determines the best next action: Dijkstra graph travel, skill check, stage jump, or rest."""
        act = self._decide_action(
            session_id=session_id,
            current_location=current_location,
            current_minute=current_minute,
            scenario_key=scenario_key,
        )
        self.last_action_type = act.action_type
        return act

    def _decide_action(
        self,
        session_id: int,
        current_location: str,
        current_minute: int = 480,
        scenario_key: str = "fantasy",
    ) -> NavigatorAction:
        self.record_location(current_location)

        # 1. Check if bedtime and rest makes sense (e.g. night time)
        if is_sleep_time(current_minute) and self.rng.random() < 0.25:
            return NavigatorAction(
                action_type="rest",
                target_location=current_location,
                action_text="I return to camp and sleep through the night until morning in bed",
                reasoning="Night time rest cycle",
            )

        # 2. Query active quest waypoints and resolve dynamic NPC schedules
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

        # Resolve live dynamic schedule location if waypoint tracks an NPC
        for wp in active_wps:
            sched_info = get_waypoint_npc_schedule_info(session_id, wp, current_minute=current_minute)
            if sched_info.get("scheduled_location"):
                wp["target_location"] = sched_info["scheduled_location"]

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

            # 4b. Backtracking to previous location (guard against ping-pong oscillation loops)
            if chaos_roll < 0.70 and len(self.location_history) >= 2 and self.last_action_type != "backtrack":
                prev_loc = self.location_history[-2]
                is_oscillating = (
                    len(self.location_history) >= 4
                    and self.location_history[-3].strip().lower() == current_location.strip().lower()
                    and self.location_history[-4].strip().lower() == prev_loc.strip().lower()
                )
                if prev_loc.strip().lower() != current_location.strip().lower() and not is_oscillating:
                    self.last_action_type = "backtrack"
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

        # 5. Goal-Directed Navigation: Use Dijkstra Shortest-Path Graph Routing
        dest_loc = wp_loc or current_location

        try:
            curr_node = db.resolve_node_id_from_location(session_id, current_location)
            dest_node = db.resolve_node_id_from_location(session_id, dest_loc)
            if curr_node and dest_node and curr_node != dest_node:
                route = find_spatial_path(session_id, curr_node, dest_node)
                if len(route) >= 2:
                    sess_row = db.get_session(session_id) or {}
                    target_hop_node = None
                    target_hop_loc = None

                    for idx in range(1, len(route)):
                        cand_prev = route[idx - 1]
                        cand_node = route[idx]
                        eval_res = evaluate_spatial_route(session_id, [cand_prev, cand_node], session=dict(sess_row))
                        if eval_res.get("gated"):
                            # Obstacle barrier encountered (e.g. locked door with missing key)
                            blockers = eval_res.get("stage_directives", [])
                            return NavigatorAction(
                                action_type="barrier_halt",
                                target_location=current_location,
                                action_text=f"I halt at {current_location} due to blocked passage: {', '.join(blockers)}",
                                reasoning=f"Dijkstra barrier halt: {blockers}",
                                blockers=blockers
                            )
                        cand_loc = format_node_hierarchy(session_id, cand_node)
                        if cand_loc and cand_loc.strip().lower() != current_location.strip().lower():
                            target_hop_node = cand_node
                            target_hop_loc = cand_loc
                            break

                    if target_hop_loc:
                        return NavigatorAction(
                            action_type="travel",
                            target_location=target_hop_loc,
                            action_text=f"I follow the shortest spatial path toward {target_hop_loc}",
                            reasoning=f"Dijkstra shortest path hop {curr_node} -> {target_hop_node} toward {dest_node}",
                        )
        except Exception:
            pass

        # Standard direct travel fallback
        return NavigatorAction(
            action_type="travel",
            target_location=dest_loc,
            action_text=f"I head directly to {dest_loc} to reach the objective",
            reasoning=f"Navigating to waypoint target: {dest_loc}",
        )
