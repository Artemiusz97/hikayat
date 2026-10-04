from __future__ import annotations
"""
Waypoint templates and multi-stage fallback generators.
"""
import json
import random
from typing import Optional, Any

import db

ARCHETYPE_WAYPOINT_TEMPLATES: dict[str, list[dict]] = {
    "escort": [
        {"stage_index": 1, "stage_label": "Rendezvous with your client at the meeting point", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Guide and protect your client through hazardous territory", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "Safely deliver your client to the sanctuary destination", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "monster hunting": [
        {"stage_index": 1, "stage_label": "Track the creature's spoor and locate its territory", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Bypass local hazards and corner the beast at its lair", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "Confront and eliminate the creature", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "extermination": [
        {"stage_index": 1, "stage_label": "Travel to the infestation threshold", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Infiltrate the nesting grounds and destroy the spawn", "target_location": "", "target_npc": "", "completion_trigger": "skill_check", "resource_target": 3},
        {"stage_index": 3, "stage_label": "Eliminate the broodmaster and secure the perimeter", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "bounty hunting": [
        {"stage_index": 1, "stage_label": "Track the bounty target to their last known hideout", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Breach the hideout and cut off their escape routes", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "Capture or neutralize the target", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "investigation": [
        {"stage_index": 1, "stage_label": "Travel to the scene and locate the initial leads", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Investigate anomalies and uncover the 3 key clues or evidence fragments", "target_location": "", "target_npc": "", "completion_trigger": "skill_check", "resource_target": 3},
        {"stage_index": 3, "stage_label": "Analyze the findings and secure the critical proof", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "infiltration": [
        {"stage_index": 1, "stage_label": "Scout the perimeter and identify an entry point", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Bypass security systems and slip into the inner sector", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "Execute the objective inside and extract safely", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "rescue": [
        {"stage_index": 1, "stage_label": "Locate where the captive is being held", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Neutralize the guards and unlock the holding cell", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "Extract the captive safely to a secure extraction point", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "gathering": [
        {"stage_index": 1, "stage_label": "Travel to the resource harvest territory", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Harvest the required rare materials from the site", "target_location": "", "target_npc": "", "completion_trigger": "skill_check", "resource_target": 3},
        {"stage_index": 3, "stage_label": "Secure and preserve the collected resources", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "alchemy": [
        {"stage_index": 1, "stage_label": "Travel to the rare reagent source territory", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Harvest the volatile essential reagents", "target_location": "", "target_npc": "", "completion_trigger": "skill_check", "resource_target": 3},
        {"stage_index": 3, "stage_label": "Refine, brew, and stabilize the concoction at the alchemy station", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "allure": [
        {"stage_index": 1, "stage_label": "Locate your target at their usual social venue", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Engage the target and establish an intimate rapport", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "Proceed with the decisive encounter", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "seduction": [
        {"stage_index": 1, "stage_label": "Find your target at the social haunt", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Draw the target into a private setting and charm them", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "Execute the seduction successfully", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "espionage": [
        {"stage_index": 1, "stage_label": "Reach the intelligence source undetected", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Infiltrate the archives and extract the 3 classified intelligence fragments", "target_location": "", "target_npc": "", "completion_trigger": "skill_check", "resource_target": 3},
        {"stage_index": 3, "stage_label": "Retreat through the escape corridor without raising alarms", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "heist": [
        {"stage_index": 1, "stage_label": "Infiltrate the perimeter and identify vault security", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Disable the 3 security countermeasures and crack the vault", "target_location": "", "target_npc": "", "completion_trigger": "skill_check", "resource_target": 3},
        {"stage_index": 3, "stage_label": "Secure the payload and execute the escape plan", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "secret admirer": [
        {"stage_index": 1, "stage_label": "Rendezvous with the admirer to receive the discreet note and delivery instructions", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Infiltrate the recipient's location and slip the note into place undetected", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "Return to the admirer or observe from the shadows to confirm the delivery", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "matchmaking": [
        {"stage_index": 1, "stage_label": "Meet with your client to learn about their crush and devise a plan", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Travel to the crush's location and orchestrate the romantic opportunity", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "Facilitate their private conversation and secure a positive connection", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "romance": [
        {"stage_index": 1, "stage_label": "Meet with your contact to discuss the romantic endeavor", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Travel to the rendezvous point and prepare the romantic gesture", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "Confront the moment and secure an intimate bond", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "courier": [
        {"stage_index": 1, "stage_label": "Collect the package or parcel from the sender at the pickup point", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Transport the goods safely through the area and locate the recipient", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "Safely hand over the delivery and secure confirmation of receipt", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "delivery": [
        {"stage_index": 1, "stage_label": "Receive the items and delivery instructions from the client", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Navigate the route to the drop-off location and find the recipient", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "Deliver the consignment safely into the recipient's hands", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "academic rescue": [
        {"stage_index": 1, "stage_label": "Meet with the struggling student to review the coursework crisis", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Relocate to the study grounds and conduct an intensive tutoring session", "target_location": "", "target_npc": "", "completion_trigger": "skill_check", "resource_target": 3},
        {"stage_index": 3, "stage_label": "Test comprehension with practice problems and finalize the study plan", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "academic": [
        {"stage_index": 1, "stage_label": "Consult with the instructor or peer regarding the academic task", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Analyze the research materials or missed syllabus coursework", "target_location": "", "target_npc": "", "completion_trigger": "skill_check", "resource_target": 3},
        {"stage_index": 3, "stage_label": "Complete and submit the finalized academic assignment", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "exam heist": [
        {"stage_index": 1, "stage_label": "Meet your co-conspirator to review the faculty layout and shift schedules", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Bypass hallway supervision and pick the lock to the examination archives", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "Extract the test copies and deliver them safely to the drop point", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "gossip control": [
        {"stage_index": 1, "stage_label": "Locate the rumor's source and discreetly gather details on who is spreading it", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Confront the source or plant compelling counter-evidence to dispel the rumor", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "Verify with your client that the gossip has subsided and reputation is restored", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "gossip": [
        {"stage_index": 1, "stage_label": "Eavesdrop on conversations at the local gathering spot to trace the rumor", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Uncover the secret truth or evidence behind the circulating rumors", "target_location": "", "target_npc": "", "completion_trigger": "skill_check", "resource_target": 3},
        {"stage_index": 3, "stage_label": "Report the verified findings back to your client", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "rumor": [
        {"stage_index": 1, "stage_label": "Follow up on the rumor lead at the designated meeting area", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Separate fact from fiction through investigation and inquiry", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "Resolve the situation sparked by the rumors", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "club showdown": [
        {"stage_index": 1, "stage_label": "Rendezvous with the club representatives to assess the rival challenge", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Travel to the competition arena and represent the club in the showdown event", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "Secure the decisive club victory and formalize the standing agreement", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "club": [
        {"stage_index": 1, "stage_label": "Visit the club room and discuss current operations with members", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Tackle the primary club dispute, challenge, or preparation", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "Achieve the club objective and celebrate the milestone", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "campus infiltration": [
        {"stage_index": 1, "stage_label": "Scout campus security routes and rendezvous near the target wing", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Slip past hall monitors and security cameras into the restricted facility", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "Complete the covert campus task and extract cleanly before detection", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
    "default": [
        {"stage_index": 1, "stage_label": "Travel to the quest objective threshold", "target_location": "", "target_npc": "", "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": "Investigate the site and overcome the local obstacle", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
        {"stage_index": 3, "stage_label": "Complete and secure the objective", "target_location": "", "target_npc": "", "completion_trigger": "skill_check"},
    ],
}


def get_archetype_fallback_waypoints(
    quest_type: str,
    target_location: str = "",
    target_npc: str = "",
    intermediate_location: str = "",
    final_location: str = ""
) -> list[dict]:
    """Returns default 3-stage waypoint templates for a given quest archetype, supporting multi-location routing."""
    q_lower = (quest_type or "").lower()
    template = None
    for key in ARCHETYPE_WAYPOINT_TEMPLATES:
        if key in q_lower:
            template = ARCHETYPE_WAYPOINT_TEMPLATES[key]
            break
    if template is None:
        template = ARCHETYPE_WAYPOINT_TEMPLATES["default"]
    import copy
    result = copy.deepcopy(template)
    
    stage_locs = [
        target_location,
        intermediate_location or target_location,
        final_location or intermediate_location or target_location
    ]
    for idx, stage in enumerate(result):
        if not stage.get("target_location") and idx < len(stage_locs) and stage_locs[idx]:
            stage["target_location"] = stage_locs[idx]
        elif not stage.get("target_location") and target_location:
            stage["target_location"] = target_location
        if not stage.get("target_npc") and target_npc:
            stage["target_npc"] = target_npc
    return result


def ensure_multi_stage_waypoints(
    waypoints: list[dict],
    default_loc: str = "",
    archetype: str = "default",
    secondary_loc: str = "",
    tertiary_loc: str = ""
) -> list[dict]:
    """Ensures a sub-objective has at least 3 progressive stages (Arrival/Travel -> Investigation/Barrier -> Action/Resolution).
    Prevents single-turn instant completions and supports multi-location routing."""
    if not waypoints:
        return get_archetype_fallback_waypoints(
            archetype,
            target_location=default_loc,
            intermediate_location=secondary_loc,
            final_location=tertiary_loc
        )

    validated = []
    for idx, wp in enumerate(waypoints, 1):
        if isinstance(wp, dict) and wp.get("stage_label"):
            target_loc = wp.get("target_location") or default_loc
            validated.append({
                "stage_index": idx,
                "stage_label": str(wp.get("stage_label", ""))[:200],
                "target_location": str(target_loc)[:200],
                "target_npc": str(wp.get("target_npc", "") or "")[:100],
                "completion_trigger": str(wp.get("completion_trigger", "skill_check" if idx > 1 else "arrival")),
                "resource_target": int(wp.get("resource_target", 0)) if any(k in str(wp.get("stage_label", "")).lower() for k in ("harvest", "gather", "collect", "fragments", "clues", "countermeasures", "destroy the spawn", "samples", "parts", "items", "ore", "herbs")) else 0,
            })

    if len(validated) == 1:
        single = validated[0]
        loc1 = single["target_location"] or default_loc
        loc2 = secondary_loc or loc1
        loc3 = tertiary_loc or loc2 or loc1
        zone, prim = parse_zone_primary(loc1) if loc1 else ("", "")
        place_name1 = prim or zone or "the objective area"
        _, prim2 = parse_zone_primary(loc2) if loc2 else ("", "")
        place_name2 = prim2 or place_name1

        stage1 = {
            "stage_index": 1,
            "stage_label": f"Travel to and scout {place_name1}",
            "target_location": loc1,
            "target_npc": single.get("target_npc", ""),
            "completion_trigger": "arrival",
            "resource_target": 0
        }
        stage2 = {
            "stage_index": 2,
            "stage_label": f"Investigate the site and overcome the local obstacle at {place_name2}",
            "target_location": loc2,
            "target_npc": single.get("target_npc", ""),
            "completion_trigger": "skill_check",
            "resource_target": 0
        }
        stage3 = {
            "stage_index": 3,
            "stage_label": single["stage_label"],
            "target_location": loc3,
            "target_npc": single.get("target_npc", ""),
            "completion_trigger": single.get("completion_trigger", "skill_check"),
            "resource_target": single.get("resource_target", 0)
        }
        return [stage1, stage2, stage3]

    if len(validated) == 2:
        stage1 = validated[0]
        stage2 = validated[1]
        loc1 = stage1.get("target_location") or default_loc
        loc2 = stage2.get("target_location") or secondary_loc or loc1
        loc3 = tertiary_loc or loc2 or loc1
        zone, prim = parse_zone_primary(loc2) if loc2 else ("", "")
        place_name = prim or zone or "the site"

        arch_low = (archetype or "").lower()
        if any(k in arch_low for k in ("secret admirer", "matchmaking", "romance", "courier", "delivery")):
            stage2_label = f"Travel to {place_name} and discreetly locate the delivery destination"
        elif any(k in arch_low for k in ("academic", "study", "exam")):
            stage2_label = f"Gather study materials and review coursework at {place_name}"
        elif any(k in arch_low for k in ("gossip", "rumor")):
            stage2_label = f"Investigate active rumors and track leads at {place_name}"
        elif any(k in arch_low for k in ("club", "election", "campaign")):
            stage2_label = f"Rally peer support and prepare strategic arguments at {place_name}"
        elif any(k in arch_low for k in ("infiltration", "heist", "stealth")):
            stage2_label = f"Bypass security checkpoints and slip inside {place_name}"
        else:
            stage2_label = f"Investigate the site and overcome the local obstacle at {place_name}"

        expanded_stage2 = {
            "stage_index": 2,
            "stage_label": stage2_label,
            "target_location": loc2,
            "target_npc": stage1.get("target_npc", "") or stage2.get("target_npc", ""),
            "completion_trigger": "skill_check",
            "resource_target": 0
        }
        expanded_stage3 = {
            "stage_index": 3,
            "stage_label": stage2["stage_label"],
            "target_location": loc3,
            "target_npc": stage2.get("target_npc", ""),
            "completion_trigger": stage2.get("completion_trigger", "skill_check"),
            "resource_target": stage2.get("resource_target", 0)
        }
        return [stage1, expanded_stage2, expanded_stage3]

    return validated


# ---------------------------------------------------------------- Location Matching


def parse_zone_primary(location_str: str) -> tuple[str, str]:
    if not location_str:
        return ("", "")
    delimiters = ["->", ">", "|"]
    parts = [location_str]
    # Handle arrow character separately to avoid encoding issues
    arrow = "\u2794"
    if arrow in location_str:
        parts = [p.strip() for p in location_str.split(arrow) if p.strip()]
    else:
        for d in delimiters:
            if d in location_str:
                parts = [p.strip() for p in location_str.split(d) if p.strip()]
                break
    if not parts:
        return ("", "")
    if len(parts) >= 2:
        return (parts[0].lower().strip(), parts[1].lower().strip())
    return ("", parts[0].lower().strip())


