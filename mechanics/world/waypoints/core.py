from __future__ import annotations
"""
Waypoint LLM prompt blocks, UI markers, and session persistence.
"""
import json
import re
from typing import Optional, Any

import db
from .templates import ensure_multi_stage_waypoints
from .matching import check_location_matches_waypoint, get_story_quest_climax_location



def build_waypoint_prompt_block(session_id: int, current_location: str, destination_location: str = "") -> str:
    """Builds the [ACTIVE QUEST WAYPOINTS] block for the LLM system prompt."""
    active_wps = db.get_all_session_active_waypoints(session_id)
    story_quest, climax_loc = get_story_quest_climax_location(session_id)

    # --- Phone Appointments: inject meetup NPC presence ---
    appointment_lines = []
    pending_appointments = db.get_phone_appointments(session_id, status="pending")
    for appt in pending_appointments:
        appt_loc = appt.get("rendezvous_location", "")
        npc_name = appt.get("npc_name", "")
        npc_id = appt.get("npc_id", "")
        if not appt_loc or not npc_name:
            continue
        at_rendezvous = check_location_matches_waypoint(current_location, appt_loc) or (
            bool(destination_location) and check_location_matches_waypoint(destination_location, appt_loc)
        )
        if at_rendezvous:
            appointment_lines.append(
                f"💌 MEETUP APPOINTMENT — {npc_name} agreed via DM to meet here at {appt_loc}.\n"
                f"   => {npc_name} IS PRESENT AT THIS LOCATION waiting for the player. You MUST include "
                f"them in `npcs_present` and narrate their arrival/presence in the scene. "
                f"Do NOT have them be absent or mention they haven't arrived. They are here."
            )

    if not active_wps and not (story_quest and climax_loc) and not appointment_lines:
        return ""

    lines = []
    if appointment_lines:
        lines.append("PHONE MEETUP APPOINTMENTS (Python-Enforced):")
        lines.extend(appointment_lines)
        lines.append("")

    if not active_wps and not (story_quest and climax_loc):
        return "\n".join(lines)

    lines.append("ACTIVE QUEST WAYPOINTS (Python-Enforced):")


    if story_quest and climax_loc:
        at_climax = check_location_matches_waypoint(current_location, climax_loc)
        lines.append(f"  ⚡ [STORY QUEST CLIMAX ENCOUNTER READY: {story_quest.get('title', 'Story Quest')}]")
        lines.append(f"    Target: {climax_loc}")
        lines.append(f"    Player: {current_location or '(unknown)'} {'(AT CLIMAX TARGET)' if at_climax else '(NOT at climax target)'}")
        if at_climax:
            lines.append("    => ⚡ MANDATORY CLIMAX ENCOUNTER: All sub-objectives complete! Stage the high-stakes confrontation / boss fight / showdown this turn!")
            lines.append("    => You MUST include a dedicated climax choice in `next_choices` marked with ⚡.")
        else:
            lines.append(f"    => Player must travel to: {climax_loc} for the final showdown. Offer travel or direction choices.")
        lines.append("")

    for wp in active_wps:
        quest_title = wp.get("quest_title", "")
        sub_obj_id = wp.get("sub_obj_id")
        target_loc = wp.get("target_location", "")
        target_npc = wp.get("target_npc", "")
        trigger = wp.get("completion_trigger", "arrival")
        label = wp.get("stage_label", "")
        resource_target = int(wp.get("resource_target", 0))
        resource_collected = int(wp.get("resource_collected", 0))

        at_target = check_location_matches_waypoint(current_location, target_loc)

        header = f"  [{quest_title}" + (f" Sub-Obj #{sub_obj_id}]" if sub_obj_id is not None else "]")
        lines.append(header)
        lines.append(f"    Stage: \"{label}\"")
        if target_loc:
            npc_part = f" | Contact: {target_npc}" if target_npc else ""
            lines.append(f"    Target: {target_loc}{npc_part}")
        lines.append(f"    Player: {current_location or '(unknown)'} {'(AT TARGET)' if at_target else '(NOT at target)'}")

        if at_target:
            if trigger == "arrival":
                lines.append("    => ARRIVAL TRIGGER: Auto-completes. Narrate arrival scene and what player finds/meets.")
            elif trigger == "skill_check":
                if resource_target > 0:
                    remaining = resource_target - resource_collected
                    lines.append(f"    => RESOURCE GATHER: {resource_collected}/{resource_target} collected. {remaining} more needed.")
                    lines.append("    => Skill check success tier determines resources found: crit=all, success=half.")
                else:
                    lines.append("    => ⭐ ACTIVE LOCAL QUEST OBJECTIVE AT CURRENT LOCATION:")
                    lines.append(f"       You MUST include at least one dedicated choice in `next_choices` (marked with ⭐ or 🎯) allowing the player to directly interact with or progress this stage ('{label}').")
        else:
            lines.append(f"    => Player must travel to: {target_loc} before this stage can progress.")
            lines.append("    => Do NOT complete this objective. Offer travel or inquiry choices.")
            lines.append("    => [POST-OBJECTIVE / TRAVEL TRANSITION]: If the local objective at the current room was completed, do NOT generate redundant micro-checks on the solved obstacle. Prioritize travel choices toward target locations, speaking with present NPCs, or resting.")
        lines.append("")

    return "\n".join(lines)


def get_active_local_quest_hooks(session_id: int, current_location: str) -> list[dict]:
    """Returns all active quest waypoints that match the player's current location."""
    active_wps = db.get_all_session_active_waypoints(session_id)
    matched = []
    for wp in active_wps:
        target_loc = wp.get("target_location", "")
        if target_loc and check_location_matches_waypoint(current_location, target_loc):
            matched.append(wp)
    return matched


# ---------------------------------------------------------------- Location UI Markers

def ensure_quest_waypoints_exist(session_id: int):
    """Guarantees that active quests with sub-objectives have corresponding waypoints in DB."""
    if not session_id:
        return
    sess = db.get_session(session_id)
    scen_key = sess.get("scenario", "fantasy") if sess else "fantasy"
    quests = db.get_session_quests(session_id, status="Active")
    existing_locs = db.get_session_locations(session_id) if session_id else []

    for q in quests:
        qid = q.get("quest_id")
        sub_objs = q.get("sub_objectives") or []
        if not qid or not sub_objs:
            continue
        with db.get_conn() as conn:
            cnt = conn.execute(
                "SELECT COUNT(*) as cnt FROM quest_waypoints WHERE session_id=? AND quest_id=?",
                (session_id, qid)
            ).fetchone()["cnt"]
        if cnt == 0:
            for so in sub_objs:
                if not isinstance(so, dict) or so.get("completed"):
                    continue
                so_id = so.get("id", 1)
                so_text = so.get("text", "")
                arch = so.get("archetype", "default")
                
                target_loc = ""
                for loc_row in existing_locs:
                    p_name = loc_row.get("primary_name", "")
                    z_name = loc_row.get("zone_name", "")
                    if p_name and (p_name.lower() in so_text.lower() or any(w in so_text.lower() for w in p_name.lower().split() if len(w) > 4)):
                        target_loc = f"{z_name} ➔ {p_name}"
                        break
                
                if not target_loc and existing_locs:
                    idx = (int(so_id) - 1) % len(existing_locs)
                    target_loc = f"{existing_locs[idx].get('zone_name')} ➔ {existing_locs[idx].get('primary_name')}"
                
                wps = ensure_multi_stage_waypoints([], default_loc=target_loc, archetype=arch)
                if wps:
                    db.save_quest_waypoints(session_id, qid, wps, sub_obj_id=so_id)


def get_location_waypoint_markers(session_id: int) -> dict[str, list[str]]:
    """Returns dict mapping 'Zone ➔ Primary' (and bare 'Primary') -> [marker labels] for LocationSelectView."""
    ensure_quest_waypoints_exist(session_id)
    active_wps = db.get_all_session_active_waypoints(session_id)
    markers: dict[str, list[str]] = {}
    arrow = "\u2794"
    delimiters = [arrow, "->", ">", "|"]
    existing_locs = db.get_session_locations(session_id) if session_id else []

    generic_template_zones = {
        "ancient woods", "woodlands & forest", "capital city", "central farmlands & plains",
        "high mountain range", "coastal harbor town", "deep cave network", "ancient dungeon complex",
        "desert dunes & oasis", "swamp & marshes", "volcanic ashlands", "frozen snow & tundra",
        "cursed shadowlands", "underworld chasm", "main academy campus", "main academy building"
    }

    def _register_location_marker(loc_string: str, tag: str):
        """Resolve a location string to map keys and append the tag, stacking alongside existing markers."""
        parts = [loc_string]
        for d in delimiters:
            if d in loc_string:
                parts = [p.strip() for p in loc_string.split(d) if p.strip()]
                break
        keys = []
        if len(parts) >= 2:
            z_tgt, p_tgt = parts[0], parts[1]
            keys.extend([f"{z_tgt} {arrow} {p_tgt}", f"{z_tgt} -> {p_tgt}", p_tgt])
            if existing_locs:
                z_words = set(re.findall(r"\b\w{3,}\b", z_tgt.lower()))
                for r in existing_locs:
                    r_p = r.get("primary_name", "")
                    r_z = r.get("zone_name", "")
                    if r_p and r_z and (r_p.lower() == p_tgt.lower() or p_tgt.lower() in r_p.lower() or r_p.lower() in p_tgt.lower()):
                        r_z_words = set(re.findall(r"\b\w{3,}\b", r_z.lower()))
                        if z_tgt.lower() in generic_template_zones or not z_tgt or (z_words & r_z_words) or z_words.issubset(r_z_words):
                            keys.extend([f"{r_z} {arrow} {r_p}", f"{r_z} -> {r_p}"])
        elif len(parts) == 1:
            p_tgt = parts[0]
            keys.append(p_tgt)
            if existing_locs:
                for r in existing_locs:
                    if r.get("primary_name", "").lower() == p_tgt.lower() and r.get("zone_name"):
                        keys.extend([f"{r['zone_name']} {arrow} {r['primary_name']}", f"{r['zone_name']} -> {r['primary_name']}"])
        for k in keys:
            if k not in markers:
                markers[k] = []
            if tag not in markers[k]:
                markers[k].append(tag)

    # 0. Phone Meetup Appointments — 💌 marker on rendezvous location
    pending_appointments = db.get_phone_appointments(session_id, status="pending")
    for appt in pending_appointments:
        appt_loc = appt.get("rendezvous_location", "")
        npc_name = appt.get("npc_name", "")
        if appt_loc and npc_name:
            _register_location_marker(appt_loc, f"💌 [Meetup] {npc_name} is waiting here")

    # 1. Check for active Story Quest in Climax Ready state
    story_quest, climax_loc = get_story_quest_climax_location(session_id)
    if story_quest and climax_loc:
        climax_title = story_quest.get("title", "Story Quest")
        tag = f"⚡ [Story Climax] {climax_title} — Final Showdown"

        parts = [climax_loc]
        for d in delimiters:
            if d in climax_loc:
                parts = [p.strip() for p in climax_loc.split(d) if p.strip()]
                break

        keys_to_register = []
        if len(parts) >= 2:
            z_tgt = parts[0]
            p_tgt = parts[1]
            keys_to_register.extend([
                f"{z_tgt} {arrow} {p_tgt}",
                f"{z_tgt} -> {p_tgt}",
                p_tgt,
            ])
            if existing_locs:
                z_words = set(re.findall(r"\b\w{3,}\b", z_tgt.lower()))
                for r in existing_locs:
                    r_p = r.get("primary_name", "")
                    r_z = r.get("zone_name", "")
                    if r_p and r_z and (r_p.lower() == p_tgt.lower() or p_tgt.lower() in r_p.lower() or r_p.lower() in p_tgt.lower()):
                        r_z_words = set(re.findall(r"\b\w{3,}\b", r_z.lower()))
                        if z_tgt.lower() in generic_template_zones or not z_tgt or (z_words & r_z_words) or z_words.issubset(r_z_words):
                            keys_to_register.extend([
                                f"{r_z} {arrow} {r_p}",
                                f"{r_z} -> {r_p}",
                            ])
        elif len(parts) == 1:
            p_tgt = parts[0]
            keys_to_register.append(p_tgt)
            if existing_locs:
                for r in existing_locs:
                    if r.get("primary_name", "").lower() == p_tgt.lower() and r.get("zone_name"):
                        keys_to_register.extend([
                            f"{r['zone_name']} {arrow} {r['primary_name']}",
                            f"{r['zone_name']} -> {r['primary_name']}",
                        ])

        for k in keys_to_register:
            if k not in markers:
                markers[k] = []
            if tag not in markers[k]:
                markers[k].append(tag)

    for wp in active_wps:
        target_loc = wp.get("target_location", "").strip()
        if not target_loc:
            continue
        parts = [target_loc]
        for d in delimiters:
            if d in target_loc:
                parts = [p.strip() for p in target_loc.split(d) if p.strip()]
                break

        keys_to_register = []
        if len(parts) >= 2:
            z_tgt = parts[0]
            p_tgt = parts[1]
            keys_to_register.extend([
                f"{z_tgt} {arrow} {p_tgt}",
                f"{z_tgt} -> {p_tgt}",
                p_tgt,
            ])
            # If z_tgt is a generic template zone (e.g. "Ancient Woods"), resolve to the session's actual seeded zone
            if existing_locs:
                z_words = set(re.findall(r"\b\w{3,}\b", z_tgt.lower()))
                for r in existing_locs:
                    r_p = r.get("primary_name", "")
                    r_z = r.get("zone_name", "")
                    if r_p and r_z and (r_p.lower() == p_tgt.lower() or p_tgt.lower() in r_p.lower() or r_p.lower() in p_tgt.lower()):
                        r_z_words = set(re.findall(r"\b\w{3,}\b", r_z.lower()))
                        if z_tgt.lower() in generic_template_zones or not z_tgt or (z_words & r_z_words) or z_words.issubset(r_z_words):
                            keys_to_register.extend([
                                f"{r_z} {arrow} {r_p}",
                                f"{r_z} -> {r_p}",
                            ])
        elif len(parts) == 1:
            p_tgt = parts[0]
            keys_to_register.append(p_tgt)
            if existing_locs:
                for r in existing_locs:
                    if r.get("primary_name", "").lower() == p_tgt.lower() and r.get("zone_name"):
                        keys_to_register.extend([
                            f"{r['zone_name']} {arrow} {r['primary_name']}",
                            f"{r['zone_name']} -> {r['primary_name']}",
                        ])
        else:
            continue

        quest_title = wp.get("quest_title", "Quest")
        is_story = bool(wp.get("is_story_quest"))
        sub_obj_id = wp.get("sub_obj_id")
        sub_label = wp.get("stage_label", "")
        target_npc = (wp.get("target_npc") or "").strip()
        npc_suffix = f" (👤 {target_npc})" if target_npc else ""

        if is_story and sub_obj_id is not None:
            icon = "\u2b50"
            tag = f"{icon} [Story] {sub_label}{npc_suffix}"
        else:
            q_type = (wp.get("quest_type") or "Bounty").lower()
            if any(k in q_type for k in ("escort", "rescue")):
                icon = "\U0001f6e1\ufe0f"
            elif any(k in q_type for k in ("hunt", "extermination")):
                icon = "\U0001f479"
            elif any(k in q_type for k in ("allure", "seduction")):
                icon = "\U0001f48b"
            elif any(k in q_type for k in ("infiltration", "heist", "espionage")):
                icon = "\U0001f575\ufe0f"
            else:
                icon = "\U0001f3af"
            stage_part = f" — {sub_label}" if sub_label else ""
            tag = f"{icon} [Bounty] {quest_title}{stage_part}{npc_suffix}"

        for k in keys_to_register:
            if k not in markers:
                markers[k] = []
            if tag not in markers[k]:
                markers[k].append(tag)

    return markers
