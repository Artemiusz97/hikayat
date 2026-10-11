from __future__ import annotations
"""
Spatial & Waypoint Invariant Auditor for Hikayat.
Enforces rigorous spatial integrity, 3-tier formatting, reverse spatial symmetry,
waypoint isolation, temporal continuity, and oscillation loop detection.
"""
import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple

import db
from mechanics.world.waypoints.matching import check_location_matches_waypoint
from mechanics.world.locations.movement import parse_tiered_location


@dataclass
class SpatialViolation:
    """Record of an invariant violation or anomalous state transition."""
    turn: int
    category: str
    message: str
    location: str
    minute: int
    state_dump: Dict[str, Any] = field(default_factory=dict)


class SpatialInvariantAuditor:
    """Performs rigorous post-turn audit checks on spatial, temporal, and waypoint state."""

    def __init__(self, scenario_key: str = "fantasy", max_stagnant_turns: int = 25):
        self.scenario_key = scenario_key
        self.max_stagnant_turns = max_stagnant_turns
        self.violations: List[SpatialViolation] = []
        self.location_history: List[Tuple[int, str, int, int]] = []  # (turn, loc, minute, day)
        self.last_progress_turn = 0
        self.last_completed_count = 0
        self.auto_heals_detected = 0

    def audit_turn(
        self,
        turn: int,
        session_id: int,
        current_location: str,
        current_minute: int,
        current_day: int,
        active_wps: List[dict],
        completed_stage_count: int,
    ) -> List[SpatialViolation]:
        """Runs all spatial, waypoint, and temporal invariant audits for a turn."""
        turn_violations: List[SpatialViolation] = []

        # Record history
        self.location_history.append((turn, current_location, current_minute, current_day))

        # Check if progress occurred
        if completed_stage_count > self.last_completed_count:
            self.last_completed_count = completed_stage_count
            self.last_progress_turn = turn

        # ---------------------------------------------------------
        # 1. FORMAT & HIERARCHY INVARIANT
        # ---------------------------------------------------------
        if not current_location or not isinstance(current_location, str):
            turn_violations.append(SpatialViolation(
                turn=turn,
                category="format_empty_location",
                message="Current location is empty or not a valid string.",
                location=str(current_location),
                minute=current_minute,
            ))
        else:
            # Must not contain unrendered markdown
            if "**" in current_location or "__" in current_location:
                turn_violations.append(SpatialViolation(
                    turn=turn,
                    category="format_markdown_leak",
                    message=f"Markdown formatting syntax detected in location string: '{current_location}'",
                    location=current_location,
                    minute=current_minute,
                ))

            # Must not contain raw action clauses
            raw_low = current_location.lower()
            action_markers = [
                "to investigate", "in order to", "to find", "to confront",
                "and search", "to avoid", "to retrieve", "to bypass",
            ]
            for am in action_markers:
                if am in raw_low:
                    turn_violations.append(SpatialViolation(
                        turn=turn,
                        category="format_action_verb_leak",
                        message=f"Action/objective clause '{am}' leaked into stored location: '{current_location}'",
                        location=current_location,
                        minute=current_minute,
                    ))

            # Delimiter should be normalized to '➔' if multi-tiered
            if any(d in current_location for d in (" -> ", " --> ", " | ", " > ")):
                turn_violations.append(SpatialViolation(
                    turn=turn,
                    category="format_delimiter_unnormalized",
                    message=f"Unnormalized delimiter in location: '{current_location}'",
                    location=current_location,
                    minute=current_minute,
                ))

        # ---------------------------------------------------------
        # 2. REVERSE SPATIAL SYMMETRY INVARIANT
        # ---------------------------------------------------------
        if current_location and isinstance(current_location, str):
            # A location must always match itself
            if not check_location_matches_waypoint(current_location, current_location):
                turn_violations.append(SpatialViolation(
                    turn=turn,
                    category="reverse_spatial_reflexivity",
                    message=f"Location fails to match itself: '{current_location}'",
                    location=current_location,
                    minute=current_minute,
                ))

            # Sub-areas must match parent Primary Place
            zone, primary, sub = parse_tiered_location(current_location, self.scenario_key, session_id=session_id)
            if zone and primary:
                parent_primary = f"{zone} ➔ {primary}"
                if not check_location_matches_waypoint(current_location, parent_primary):
                    turn_violations.append(SpatialViolation(
                        turn=turn,
                        category="reverse_spatial_parent_mismatch",
                        message=f"Location '{current_location}' failed to match its parent '{parent_primary}'",
                        location=current_location,
                        minute=current_minute,
                    ))

        # ---------------------------------------------------------
        # 3. WAYPOINT ISOLATION & PROGRESSION INVARIANT
        # ---------------------------------------------------------
        if session_id:
            try:
                with db.get_conn() as conn:
                    rows = conn.execute(
                        "SELECT quest_id, sub_obj_id, stage_index, status FROM quest_waypoints WHERE session_id=? ORDER BY sub_obj_id, stage_index",
                        (session_id,)
                    ).fetchall()
                
                # Group by (quest_id, sub_obj_id)
                by_sub: Dict[Any, List[dict]] = {}
                for r in rows:
                    key = (r["quest_id"], r["sub_obj_id"])
                    by_sub.setdefault(key, []).append(dict(r))

                for key, wps in by_sub.items():
                    active_count = sum(1 for w in wps if w["status"] == "active")
                    if active_count > 1:
                        turn_violations.append(SpatialViolation(
                            turn=turn,
                            category="waypoint_multiple_active",
                            message=f"Sub-objective {key} has {active_count} active waypoints simultaneously! Expected at most 1.",
                            location=current_location,
                            minute=current_minute,
                            state_dump={"waypoints": wps},
                        ))

                    # Check ordering: completed stages must precede active/locked
                    saw_uncompleted = False
                    for w in wps:
                        if w["status"] != "completed":
                            saw_uncompleted = True
                        elif saw_uncompleted and w["status"] == "completed":
                            turn_violations.append(SpatialViolation(
                                turn=turn,
                                category="waypoint_out_of_order",
                                message=f"Sub-objective {key} has completed stage after incomplete stage (Stage #{w['stage_index']})",
                                location=current_location,
                                minute=current_minute,
                                state_dump={"waypoints": wps},
                            ))
            except Exception as e:
                pass

        # ---------------------------------------------------------
        # 4. TEMPORAL CONTINUITY INVARIANT
        # ---------------------------------------------------------
        if not (0 <= int(current_minute or 0) <= 1439):
            turn_violations.append(SpatialViolation(
                turn=turn,
                category="temporal_clock_bounds",
                message=f"Clock minute out of bounds: {current_minute} (must be in 0..1439)",
                location=current_location,
                minute=current_minute,
            ))

        if len(self.location_history) >= 2:
            prev_t, prev_loc, prev_min, prev_day = self.location_history[-2]
            day_delta = current_day - prev_day
            if day_delta < 0:
                turn_violations.append(SpatialViolation(
                    turn=turn,
                    category="temporal_day_regression",
                    message=f"Day regressed from {prev_day} to {current_day}",
                    location=current_location,
                    minute=current_minute,
                ))
            elif day_delta == 0 and current_minute < prev_min:
                turn_violations.append(SpatialViolation(
                    turn=turn,
                    category="temporal_minute_regression",
                    message=f"Minute regressed from {prev_min} to {current_minute} on Day {current_day}",
                    location=current_location,
                    minute=current_minute,
                ))

        # ---------------------------------------------------------
        # 5. OSCILLATION LOOP DETECTION (A -> B -> A -> B -> A -> B)
        # ---------------------------------------------------------
        if len(self.location_history) >= 6:
            recent_locs = [h[1] for h in self.location_history[-6:]]
            if recent_locs[0] == recent_locs[2] == recent_locs[4] and recent_locs[1] == recent_locs[3] == recent_locs[5] and recent_locs[0] != recent_locs[1]:
                if (turn - self.last_progress_turn) >= 4:
                    turn_violations.append(SpatialViolation(
                        turn=turn,
                        category="deadlock_oscillation_loop",
                        message=f"Oscillation loop detected between '{recent_locs[0]}' and '{recent_locs[1]}'",
                        location=current_location,
                        minute=current_minute,
                        state_dump={"loop_history": recent_locs},
                    ))

        # ---------------------------------------------------------
        # 6. STAGNANT DEADLOCK TIMEOUT
        # ---------------------------------------------------------
        if active_wps and (turn - self.last_progress_turn) > self.max_stagnant_turns:
            turn_violations.append(SpatialViolation(
                turn=turn,
                category="deadlock_stagnant_timeout",
                message=f"Journey stagnant for {turn - self.last_progress_turn} turns without waypoint progression.",
                location=current_location,
                minute=current_minute,
                state_dump={"active_wps": active_wps},
            ))

        self.violations.extend(turn_violations)
        return turn_violations
