from __future__ import annotations
"""
Waypoint and Spatial Fuzzing Harness for Hikayat.
Generates isolated test sessions, 3-tier location seeds, 3-stage progressive waypoints,
and realistic / stress perturbations simulating noisy LLM location outputs.
"""
import re
import random
import uuid
import time
from typing import Dict, Any, List, Optional, Tuple

import db
import scenario_data
from mechanics.world.locations.seeding import ensure_session_locations_seeded
from mechanics.world.locations.movement import (
    get_default_tiered_location,
    format_tiered_location_string,
    parse_tiered_location,
)
from mechanics.world.locations import get_discovered_primary_locations
from mechanics.world.waypoints.templates import ensure_multi_stage_waypoints
from db.quests import save_quest_waypoints, upsert_quest


REALISTIC_ACTION_SUFFIXES = [
    " to investigate the strange disturbance",
    " in order to find the encrypted datapad",
    " to confront the local syndicate enforcer",
    " and search for clues regarding the missing student",
    " to avoid the security patrols in the corridor",
    " to meet up with the informant at dusk",
    " and retrieve the ancient parchment",
    " to bypass the locked heavy gate",
    " to gather samples from the contaminated zone",
]

INCONGRUOUS_SUB_SPOTS = [
    "Terrace Overlook",
    "Rooftop Garden",
    "Observation Point",
    "Courtyard Fountain",
    "Exterior Balcony",
    "Garden Pavilion",
]


class WaypointFuzzer:
    """Procedural generator for spatial locations, waypoints, and noisy LLM perturbations."""

    def __init__(self, rng: Optional[random.Random] = None):
        self.rng = rng or random.Random()

    def create_test_session(self, scenario_key: str = "fantasy", session_id: Optional[int] = None) -> dict:
        """Creates an isolated synthetic session in SQLite seeded with full spatial locations."""
        sid = session_id or self.rng.randint(900000, 999999)
        uid = self.rng.randint(800000, 899999)

        # 1. Clean any preexisting collision for this test ID
        with db.get_conn() as conn:
            for table in (
                "session_locations",
                "quest_waypoints",
                "quests",
                "session_clues",
                "session_members",
                "lorebook",
                "contacts",
                "factions",
                "school_directory",
            ):
                conn.execute(f"DELETE FROM {table} WHERE session_id=?", (sid,))
            conn.execute("DELETE FROM sessions WHERE id=?", (sid,))

        # 2. Seed locations for this scenario
        ensure_session_locations_seeded(sid, scenario_key, char_name="Explorer")

        # 3. Determine starting location
        z, p, s = get_default_tiered_location(scenario_key, session_id=sid, char_name="Explorer")
        start_loc = format_tiered_location_string(z, p, s)

        # 4. Insert session row
        now = time.time()
        with db.get_conn() as conn:
            conn.execute(
                """INSERT INTO sessions
                   (id, scenario, mode, capacity, status, current_location, current_minute, current_day,
                    narrative, history_json, created_at, updated_at)
                   VALUES (?, ?, 'solo', 1, 'active', ?, ?, ?, ?, '[]', ?, ?)""",
                (sid, scenario_key, start_loc, 480, 1, "The journey begins.", now, now),
            )

        sess = db.get_session(sid)
        return sess or {"id": sid, "scenario": scenario_key, "current_location": start_loc, "current_minute": 480, "current_day": 1}

    def generate_story_quest_with_waypoints(
        self,
        session_id: int,
        scenario_key: str = "fantasy",
        sub_obj_count: int = 3,
        stages_per_sub: int = 3,
    ) -> Tuple[dict, List[dict]]:
        """Generates a realistic Story Quest with 3 distinct sub-quests targeting distinct locations,
        each having progressive 3-stage waypoints (Arrival -> Skill Check -> Skill Check)."""
        quest_id = f"SQ-TEST-{uuid.uuid4().hex[:6].upper()}"

        # Fetch discovered primary locations in session
        zones_dict = get_discovered_primary_locations(session_id, scenario_key)
        all_places: List[Tuple[str, str]] = []
        for z, primaries in zones_dict.items():
            for p in primaries:
                all_places.append((z, p))

        if not all_places:
            z, p, s = get_default_tiered_location(scenario_key, session_id=session_id)
            all_places = [(z, p)]

        # Shuffle places so each sub-objective gets distinct destinations
        shuffled_places = list(all_places)
        self.rng.shuffle(shuffled_places)

        sub_objectives = []
        all_generated_wps: List[dict] = []

        archetype_pool = [
            ("Investigation", "Investigate the primary disturbance and collect critical clues"),
            ("Infiltration", "Infiltrate the restricted sector and gather vital intelligence"),
            ("Diplomacy", "Form an alliance or confront the regional instigator"),
        ]

        for sub_id in range(1, sub_obj_count + 1):
            arch, default_desc = archetype_pool[(sub_id - 1) % len(archetype_pool)]
            sub_objectives.append({
                "id": sub_id,
                "archetype": arch,
                "text": f"{default_desc} in sector #{sub_id}",
                "completed": False,
            })

            # Pick 2-3 distinct locations for the stages of this sub-objective
            wps = []
            for st_idx in range(1, stages_per_sub + 1):
                place_idx = (sub_id * 2 + st_idx) % len(shuffled_places)
                target_z, target_p = shuffled_places[place_idx]
                target_loc = format_tiered_location_string(target_z, target_p, "Main Area")

                if st_idx == 1:
                    trigger = "arrival"
                    label = f"Travel to {target_p} to establish a forward presence"
                elif st_idx == 2:
                    trigger = "skill_check"
                    label = f"Search {target_p} and collect vital intel"
                else:
                    trigger = "skill_check"
                    label = f"Confront the operative or resolve the breach at {target_p}"

                wps.append({
                    "stage_index": st_idx,
                    "stage_label": label,
                    "target_location": target_loc,
                    "target_npc": "",
                    "completion_trigger": trigger,
                    "resource_target": 0,
                    "status": "active" if st_idx == 1 else "locked",
                })

            save_quest_waypoints(session_id, quest_id, wps, sub_obj_id=sub_id)
            all_generated_wps.extend(wps)

        # Upsert Story Quest into quests table
        quest = upsert_quest(
            session_id=session_id,
            quest_id=quest_id,
            quest_type="Story Quest",
            title=f"Simulation Campaign: Chapter #{self.rng.randint(1, 10)}",
            objective="Navigate regional sectors and resolve tactical sub-objectives.",
            progress="Chapter Active",
            current_clues="",
            status="Active",
            reward_xp=300,
            reward_gold=75,
            is_story_quest=1,
            sub_objectives=sub_objectives,
        )

        return quest, all_generated_wps

    def perturb_location_string(
        self,
        clean_location: str,
        fuzz_mode: str = "realistic",
        scenario_key: str = "fantasy",
    ) -> str:
        """Injects realistic or stress perturbations into a location string mimicking LLM noise."""
        if fuzz_mode == "clean" or not clean_location:
            return clean_location

        mode = fuzz_mode.lower()
        roll = self.rng.random()

        # Handle 'stress' or 'all' with boundary noise
        if (mode in ("stress", "all")) and roll < 0.20:
            stress_choice = self.rng.choice([
                "empty",
                "excessive_length",
                "unicode_emojis",
                "sql_path_traversal",
                "whitespace_newlines",
            ])
            if stress_choice == "empty":
                return ""
            elif stress_choice == "excessive_length":
                return clean_location + (" -> Endless Hallway" * 25)
            elif stress_choice == "unicode_emojis":
                return f"🏰 ⚡ {clean_location} 🔮 ➔ [Sanctuary] 🔥"
            elif stress_choice == "sql_path_traversal":
                return f"../../zones/{clean_location}'; DROP TABLE session_locations;--"
            elif stress_choice == "whitespace_newlines":
                return f"\n\n\t  {clean_location}  \r\n\t"

        # Realistic LLM Perturbations
        clean_norm = re.sub(r"\s*(?:-->|->|—>|➔|\||>)\s*", " ➔ ", str(clean_location))
        parts = [p.strip() for p in clean_norm.split("➔") if p.strip()]
        if not parts:
            return clean_location

        perturbation_type = self.rng.choice([
            "action_suffix",
            "delimiter_variation",
            "markdown_syntax",
            "reverse_hierarchy",
            "drop_zone_prefix",
            "incongruous_sub_spot",
            "case_and_spacing",
        ])

        if perturbation_type == "action_suffix":
            # E.g. "Zone ➔ Primary to investigate the strange disturbance"
            suffix = self.rng.choice(REALISTIC_ACTION_SUFFIXES)
            return clean_location + suffix

        elif perturbation_type == "delimiter_variation":
            # E.g. using '->', '-->', ' | ', or '>' instead of standard '➔'
            delim = self.rng.choice([" -> ", " --> ", " | ", " > ", "   ->   "])
            return delim.join(parts)

        elif perturbation_type == "markdown_syntax":
            # E.g. "**Zone** ➔ *Primary* ➔ Sub"
            if len(parts) >= 2:
                parts[1] = f"**{parts[1]}**"
            else:
                parts[0] = f"**{parts[0]}**"
            return " ➔ ".join(parts)

        elif perturbation_type == "reverse_hierarchy":
            # E.g. "Room -> Primary -> Zone"
            return " ➔ ".join(reversed(parts))

        elif perturbation_type == "drop_zone_prefix":
            # E.g. "Primary ➔ SubArea" without Zone
            if len(parts) >= 2:
                return " ➔ ".join(parts[1:])
            return parts[0]

        elif perturbation_type == "incongruous_sub_spot":
            # E.g. "Zone ➔ Headmaster's Office ➔ Terrace Overlook"
            if len(parts) >= 2:
                inc_sub = self.rng.choice(INCONGRUOUS_SUB_SPOTS)
                return f"{parts[0]} ➔ {parts[1]} ➔ {inc_sub}"
            return clean_location

        elif perturbation_type == "case_and_spacing":
            # Jittering case and leading/trailing whitespace
            return "  " + clean_location.lower() + "  "

        return clean_location
