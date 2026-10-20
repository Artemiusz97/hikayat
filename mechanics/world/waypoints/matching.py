from __future__ import annotations
"""
Location matching, arrival triggers, and skill check completion logic.
"""
import re
from typing import Optional, Any

import db
from .templates import parse_zone_primary


def check_location_matches_waypoint(
    current_location: str,
    target_location: str,
    session_id: int = 0,
    current_node_id: str = None,
    target_node_id: str = None
) -> bool:
    """Returns True if current_location matches the waypoint target.
    If session_id is provided, checks strict spatial graph containment (is_descendant_of) first.
    Matches on Zone + Primary only. Empty target always matches.
    Robust to multi-tier inversion (e.g. Student Council Office inside Administration Wing).
    """
    if not target_location or not target_location.strip():
        return True

    if session_id:
        try:
            curr_nid = current_node_id or (db.resolve_node_id_from_location(session_id, current_location) if current_location else None)
            tgt_nid = target_node_id or (db.resolve_node_id_from_location(session_id, target_location) if target_location else None)
            if curr_nid and tgt_nid:
                return db.is_descendant_of(session_id, curr_nid, tgt_nid) or db.is_descendant_of(session_id, tgt_nid, curr_nid)
        except Exception:
            pass

    curr_zone, curr_primary = parse_zone_primary(current_location)
    tgt_zone, tgt_primary = parse_zone_primary(target_location)

    # 1. Full/Sub-string containment check:
    # If the player's primary location is contained anywhere in target_location (e.g. "Student Council Office" in
    # "Westlake Academy -> Administration Wing -> Student Council Office") and zones are compatible, it's a match!
    curr_prim_norm = curr_primary.strip().lower()
    tgt_loc_norm = target_location.strip().lower()
    if curr_prim_norm and len(curr_prim_norm) >= 4 and curr_prim_norm in tgt_loc_norm:
        if not tgt_zone or not curr_zone or tgt_zone in curr_zone or curr_zone in tgt_zone:
            return True

    # Reverse: If target's primary is contained in current_location
    if tgt_primary and len(tgt_primary) >= 4 and tgt_primary in current_location.lower():
        if not tgt_zone or not curr_zone or tgt_zone in curr_zone or curr_zone in tgt_zone:
            return True
    
    # If the target is just a zone (e.g., "Forest"), and we're inside that zone (e.g., "Forest -> Deep Woods")
    if not tgt_zone and curr_zone:
        tgt_words = set(re.findall(r"\b\w{3,}\b", tgt_primary))
        curr_z_words = set(re.findall(r"\b\w{3,}\b", curr_zone))
        if tgt_words and tgt_words.issubset(curr_z_words):
            return True
            
    if tgt_primary and curr_primary:
        tgt_words = set(re.findall(r"\b\w{3,}\b", tgt_primary))
        curr_words = set(re.findall(r"\b\w{3,}\b", curr_primary))
        if tgt_words and tgt_words.issubset(curr_words):
            return True
        if curr_words and curr_words.issubset(tgt_words):
            return True
    if tgt_zone and curr_zone:
        tgt_z_words = set(re.findall(r"\b\w{3,}\b", tgt_zone))
        curr_z_words = set(re.findall(r"\b\w{3,}\b", curr_zone))
        if tgt_z_words and tgt_z_words.issubset(curr_z_words):
            if tgt_primary and curr_primary and (tgt_primary in curr_primary or curr_primary in tgt_primary):
                return True
    return False


def is_hostile_or_lair_waypoint(wp: dict) -> bool:
    """Returns True if the waypoint represents a hostile boss/outlaw/monster hideout stage."""
    bp = str(wp.get("blueprint_id") or "").upper()
    lbl = str(wp.get("stage_label") or "").lower()
    target_npc = str(wp.get("target_npc") or "").strip().lower()
    client_npc = str(wp.get("client_npc") or "").strip().lower()
    if client_npc and target_npc == client_npc:
        return False
    if any(w in lbl for w in ("turn in", "deliver", "report to", "return to", "hand over")):
        return False
    if bp in ("NEUTRALIZATION", "EXPLORATION_HAZARD", "SITE_DEFENSE_RITUAL"):
        return True
    if any(w in lbl for w in ("confront", "eliminate", "slay", "assassinate", "capture", "defeat", "outlaw", "poacher", "smuggler", "bandit", "hideout", "lair")):
        return True
    return False


def get_waypoint_npc_schedule_info(session_id: int, wp: dict, current_minute: Optional[int] = None) -> dict:
    """
    Resolves live NPC schedule routing and Nighttime Off-Duty Guard for a waypoint.
    Returns:
      {
        "effective_location": str,
        "static_location": str,
        "is_off_duty": bool,
        "schedule_phase": str,
        "wait_until_morning_minutes": int,
        "wake_clock": str,
      }
    """
    from mechanics.system.time_engine import format_clock
    static_loc = wp.get("static_target_location") or wp.get("target_location", "")
    default_res = {
        "effective_location": static_loc,
        "static_location": static_loc,
        "scheduled_location": static_loc,
        "is_off_duty": False,
        "schedule_phase": "",
        "status_label": "On-Duty",
        "wait_until_morning_minutes": 0,
        "wake_clock": "07:30",
        "wake_minute": 420,
    }
    if not wp.get("follow_npc_schedule") or not wp.get("target_npc") or not session_id:
        return default_res
    if is_hostile_or_lair_waypoint(wp):
        return default_res

    target_npc = str(wp.get("target_npc") or "").strip()
    try:
        curr_day, db_curr_min, _ = db.get_session_time(session_id)
        curr_min = current_minute if current_minute is not None else db_curr_min
        session = db.get_session(session_id) or {}
        scen_key = str(session.get("scenario") or "fantasy")
        from mechanics.world.world_schedule import get_scenario_wake_minute
        from mechanics.world.npc_schedule import get_npc_scheduled_location, get_detailed_npc_time_phase
        wake_min = int(get_scenario_wake_minute(scen_key) or 420)
        safe_min = int(curr_min or 0) % 1440
        phase_key = get_detailed_npc_time_phase(safe_min, current_day=curr_day, scen_key=scen_key)

        contact = db.get_contact(session_id, target_npc)
        affinity = int((contact or {}).get("relationship_score") or 0)

        # Check if waypoint explicitly expects Night/Midnight
        v_phases = [str(p).lower() for p in (wp.get("valid_time_phases") or [])]
        night_allowed = any(p in ("night", "midnight") for p in v_phases)

        is_night = (safe_min >= 1200 or safe_min < wake_min)
        if is_night and not night_allowed and affinity < 40:
            wait_mins = (wake_min - safe_min) % 1440
            if wait_mins == 0:
                wait_mins = 60
            return {
                "effective_location": static_loc,
                "static_location": static_loc,
                "scheduled_location": static_loc,
                "is_off_duty": True,
                "schedule_phase": "night",
                "status_label": "Off-Duty: Sleeping",
                "wait_until_morning_minutes": wait_mins,
                "wake_clock": format_clock(wake_min),
                "wake_minute": wake_min,
            }

        # Only override static_loc with dynamic schedule if contact exists in DB
        if contact:
            npc_dict = dict(contact)
            if not npc_dict.get("name"):
                npc_dict["name"] = target_npc
            sched_loc = get_npc_scheduled_location(
                npc_dict,
                current_minute=safe_min,
                scen_key=scen_key,
                session_id=session_id,
                current_day=curr_day,
            )
            if sched_loc and str(sched_loc).strip():
                return {
                    "effective_location": str(sched_loc).strip(),
                    "static_location": static_loc,
                    "scheduled_location": str(sched_loc).strip(),
                    "is_off_duty": False,
                    "schedule_phase": phase_key,
                    "status_label": "On-Duty",
                    "wait_until_morning_minutes": 0,
                    "wake_clock": format_clock(wake_min),
                    "wake_minute": wake_min,
                }
    except Exception:
        pass

    return default_res


def resolve_effective_waypoint_location(session_id: int, wp: dict) -> str:
    """Returns the effective live target location for a waypoint, resolving NPC schedule if tagged."""
    info = get_waypoint_npc_schedule_info(session_id, wp)
    return info["effective_location"]


def resolve_waypoint_target_npc(session_id: int, wp: dict) -> str:
    """
    Returns the target NPC for a waypoint, resolving or inferring from stage_label/session if empty.
    Checks:
    1. Explicit wp.get('target_npc')
    2. Active dialogue partner name mentioned in stage_label
    3. Room present NPCs mentioned in stage_label
    4. Known contacts mentioned in stage_label
    """
    t_npc = str((wp or {}).get("target_npc") or "").strip()
    if t_npc:
        return t_npc

    stage_label = str((wp or {}).get("stage_label") or "")
    if not stage_label or not session_id:
        return ""

    try:
        session = db.get_session(session_id)
        if not session:
            return ""

        stage_low = stage_label.lower()

        from mechanics.world.mobility import get_session_dialogue_partners
        dps = get_session_dialogue_partners(session) or []
        for dp in dps:
            dp_clean = str(dp).strip()
            if dp_clean and len(dp_clean) >= 3 and dp_clean.lower() in stage_low:
                return dp_clean

        curr_npcs = session.get("current_npcs")
        if curr_npcs:
            if isinstance(curr_npcs, str):
                import json
                try:
                    curr_npcs = json.loads(curr_npcs)
                except Exception:
                    curr_npcs = [curr_npcs]
            if isinstance(curr_npcs, list):
                for npc in curr_npcs:
                    npc_name = (npc.get("name") if isinstance(npc, dict) else str(npc)).strip()
                    if npc_name and len(npc_name) >= 3 and npc_name.lower() in stage_low:
                        return npc_name

        contacts = db.get_contacts(session_id) or []
        for c in contacts:
            c_name = str(c.get("name") or "").strip()
            if c_name and len(c_name) >= 3 and c_name.lower() in stage_low:
                return c_name
    except Exception:
        pass

    return ""


def is_waypoint_npc_present_in_scene(session_id: int, target_npc: str) -> bool:
    """Returns True if target_npc is physically present at the player's current scene or active dialogue."""
    if not session_id or not target_npc or not str(target_npc).strip():
        return False

    try:
        session = db.get_session(session_id)
        if not session:
            return False

        t_clean = str(target_npc).strip().lower()
        t_words = [w for w in t_clean.split() if len(w) >= 3]

        from mechanics.world.mobility import get_session_dialogue_partners
        dps = get_session_dialogue_partners(session) or []
        for dp in dps:
            dp_low = str(dp).strip().lower()
            if t_clean in dp_low or dp_low in t_clean or any(w in dp_low for w in t_words):
                return True

        curr_npcs = session.get("current_npcs")
        if curr_npcs:
            if isinstance(curr_npcs, str):
                import json
                try:
                    curr_npcs = json.loads(curr_npcs)
                except Exception:
                    curr_npcs = [curr_npcs]
            if isinstance(curr_npcs, list):
                for npc in curr_npcs:
                    npc_name = (npc.get("name") if isinstance(npc, dict) else str(npc)).strip().lower()
                    if t_clean in npc_name or npc_name in t_clean or any(w in npc_name for w in t_words):
                        return True
    except Exception:
        pass

    return False


# ---------------------------------------------------------------- Waypoint Stage Triggers

def try_advance_on_arrival(session_id: int, quest_id: str, sub_obj_id: Optional[int], current_location: str) -> Optional[dict]:
    """Called every turn. Advances 'arrival' trigger stages when player reaches target,
    reaches the target NPC's live scheduled location, or encounters the NPC in the scene."""
    waypoint = db.get_active_waypoint(session_id, quest_id, sub_obj_id)
    if not waypoint:
        return None
    if waypoint.get("completion_trigger") != "arrival":
        return None
    # Spatial Graph & Hierarchy Matching
    session = db.get_session(session_id)
    curr_min = session.get("current_minute", 480) if session else 480
    from mechanics.narrative.blueprints import evaluate_waypoint_time_window
    time_eval = evaluate_waypoint_time_window(curr_min, waypoint.get("valid_time_phases"))
    if not time_eval.get("is_valid", True):
        return None

    curr_node = session.get("current_node_id") if session else None
    target_node = waypoint.get("target_node_id")
    target_loc = resolve_effective_waypoint_location(session_id, waypoint)
    static_target_loc = waypoint.get("static_target_location") or waypoint.get("target_location", "")
    target_npc = resolve_waypoint_target_npc(session_id, waypoint) or waypoint.get("target_npc", "")

    if not target_node and target_loc:
        try:
            target_node = db.resolve_node_id_from_location(session_id, target_loc)
        except Exception:
            target_node = None

    matched = False
    if curr_node and target_node:
        matched = (
            curr_node == target_node
            or db.is_descendant_of(session_id, curr_node, target_node)
            or db.is_descendant_of(session_id, target_node, curr_node)
        )
    if not matched and target_loc:
        matched = check_location_matches_waypoint(current_location, target_loc)
    if not matched and static_target_loc:
        matched = check_location_matches_waypoint(current_location, static_target_loc)
    if not matched and target_npc and is_waypoint_npc_present_in_scene(session_id, target_npc):
        matched = True
    elif not matched and not curr_node and not target_loc and not target_npc:
        matched = True

    # Spared deception guaranteed turn-in arrival check
    if not matched:
        quest = db.get_quest_by_id(session_id, quest_id)
        if quest and quest.get("resolution_approach") == "spared_deception":
            c_npc = quest.get("client_npc", "")
            c_loc = quest.get("client_location", "")
            if (c_loc and check_location_matches_waypoint(current_location, c_loc)) or (
                c_npc and is_waypoint_npc_present_in_scene(session_id, c_npc)
            ):
                matched = True

    if not matched:
        # Check if the player traveled directly to the immediately following stage's location,
        # bypassing an 'arrival'-only scouting waypoint.
        all_wps = db.get_quest_waypoints(session_id, quest_id, sub_obj_id) or []
        next_stage = next(
            (w for w in all_wps if w.get("stage_index") == waypoint.get("stage_index", 1) + 1 and w.get("status") == "locked"),
            None
        )
        if not next_stage:
            return None
        next_target_node = next_stage.get("target_node_id")
        next_target_loc = next_stage.get("target_location", "")
        if not next_target_node and next_target_loc:
            try:
                next_target_node = db.resolve_node_id_from_location(session_id, next_target_loc)
            except Exception:
                next_target_node = None
        next_matched = False
        if curr_node and next_target_node:
            next_matched = db.is_descendant_of(session_id, curr_node, next_target_node) or db.is_descendant_of(session_id, next_target_node, curr_node)
        elif next_target_loc:
            next_matched = check_location_matches_waypoint(current_location, next_target_loc)
        if not next_matched:
            return None

    next_wp = db.advance_waypoint(session_id, quest_id, waypoint["stage_index"], sub_obj_id)
    stage_complete = next_wp is None

    notice = {
        "quest_id": quest_id,
        "sub_obj_id": sub_obj_id,
        "stage_completed": waypoint["stage_index"],
        "stage_label": waypoint.get("stage_label", ""),
        "next_waypoint": dict(next_wp) if next_wp else None,
        "all_stages_complete": stage_complete,
        "trigger": "arrival",
    }

    if stage_complete:
        if sub_obj_id is not None:
            db.mark_sub_objective_completed_in_quest(session_id, quest_id, sub_obj_id)
            notice["sub_obj_completed"] = True
        else:
            notice["quest_completed"] = True

    return notice


def _extract_keyword_stems(words: list[str] | set[str]) -> set[str]:
    stems = set()
    for w in words:
        w = w.lower().strip()
        if len(w) < 4:
            continue
        stems.add(w)
        for suf in ("tions", "tion", "ings", "ing", "ments", "ment", "ness", "ities", "ity", "ed", "es", "ic", "al", "ly", "s"):
            if w.endswith(suf) and len(w) - len(suf) >= 4:
                stems.add(w[:-len(suf)])
                break
    return stems


def check_action_matches_waypoint(
    action_text: str, narrative: str, stage_label: str,
    sub_obj_text: str = "", target_npc: str = ""
) -> bool:
    """
    Verifies that the player's action or resulting narrative actually pertains
    to the specific waypoint stage or sub-objective before marking it completed.
    Prevents unrelated skill checks (e.g. asking gossip) from completing unrelated
    objectives (e.g. searching for a dropped notebook in the debris).
    """
    if not action_text and not narrative:
        return True

    act_lower = str(action_text or "").lower()
    narr_lower = str(narrative or "").lower()

    # Movement and travel actions must NOT complete interaction/skill check waypoints
    from mechanics.narrative.intent import is_travel_action, is_conversational_action
    if is_travel_action(action_text):
        return False

    # Conversational / social dialogue actions must NOT complete physical / mechanical / environmental waypoints
    # unless the waypoint explicitly targets that NPC or is a dialogue objective.
    is_conversational_action_flag = is_conversational_action(action_text)

    stage_lower = str(stage_label or "").lower()
    is_dialogue_stage = any(
        dw in stage_lower
        for dw in ("talk", "speak", "ask", "interrogate", "question", "interview", "convince", "persuade", "negotiate", "consult", "inquire", "gossip", "bribe", "confront", "discuss", "chat")
    ) or bool(target_npc and str(target_npc).strip())

    if is_conversational_action_flag and not is_dialogue_stage:
        return False

    # 1. Target NPC match
    if target_npc and str(target_npc).strip():
        t_npc_words = [w for w in str(target_npc).lower().split() if len(w) >= 3]
        # Target NPC must be actively mentioned or addressed in the player's action
        if any(w in act_lower for w in t_npc_words):
            return True
        # Or if player action has interaction verbs and NPC is actively interacted with in narrative
        interact_verbs = {"talk", "speak", "ask", "confront", "approach", "deliver", "give", "hand", "tell", "interrogate", "bribe", "persuade", "consult", "meet", "spare"}
        if any(v in act_lower for v in interact_verbs) and any(w in narr_lower for w in t_npc_words):
            return True

    # 2. Substantive keyword extraction from stage label and sub objective
    stop_words = {
        "the", "and", "for", "with", "from", "into", "onto", "among", "using", "about",
        "your", "their", "this", "that", "some", "what", "which", "when", "where",
        "search", "check", "area", "place", "room", "rooms", "zone", "find", "reach", "travel",
        "examine", "inspect", "investigate", "look", "stage", "task", "objective",
        "make", "take", "give", "help", "need", "must", "will", "have",
        "classroom", "classrooms", "office", "offices", "hallway", "hallways", "corridor",
        "corridors", "building", "buildings", "desk", "desks", "return", "returning",
        "arrive", "arrival", "arriving", "student", "students", "homeroom", "school",
        "before", "after", "through", "across", "under", "over", "between", "while", "during",
        "again", "then"
    }

    stage_words = re.findall(r"\b[a-z]{3,}\b", stage_lower)
    stage_keywords = _extract_keyword_stems([w for w in stage_words if w not in stop_words])

    sub_words = re.findall(r"\b[a-z]{4,}\b", str(sub_obj_text or "").lower())
    sub_keywords = _extract_keyword_stems([w for w in sub_words if w not in stop_words])

    # Priority A: Player's action text directly targets stage keywords or sub-objective keywords
    if stage_keywords and any(kw in act_lower for kw in stage_keywords):
        return True
    if sub_keywords and any(kw in act_lower for kw in sub_keywords):
        return True

    # Priority B: Outcome narrative describes completing the stage.
    if stage_keywords:
        if any(kw in narr_lower for kw in stage_keywords):
            return True
        return False

    if sub_keywords:
        if any(kw in narr_lower for kw in sub_keywords):
            return True
        return False

    return True


def does_action_target_waypoint(
    session_id: int, quest_id: str, sub_obj_id: Optional[int],
    current_location: str, action_text: str = "", narrative: str = "", sub_obj_text: str = "",
    is_quest_action: bool = False, action_quest_id: str = "", action_sub_obj_id: Optional[int] = None
) -> Optional[dict]:
    """
    Checks if the player is at the active waypoint's location (or NPC present)
    AND verifies that the action targets this waypoint.
    Returns the active waypoint dict on match, or None.
    """
    waypoint = db.get_active_waypoint(session_id, quest_id, sub_obj_id)
    if not waypoint:
        return None
    if waypoint.get("completion_trigger") not in ("skill_check", "inspect_prop", "talk_to_npc", "resource_progress", "defeat_target", "action"):
        return None
    target_node = waypoint.get("target_node_id")
    target_loc = resolve_effective_waypoint_location(session_id, waypoint)
    static_target_loc = waypoint.get("static_target_location") or waypoint.get("target_location", "")
    target_npc = waypoint.get("target_npc", "")
    session = db.get_session(session_id)
    curr_node = session.get("current_node_id") if session else None

    if not target_node and target_loc:
        try:
            target_node = db.resolve_node_id_from_location(session_id, target_loc)
        except Exception:
            target_node = None

    matched = False
    if curr_node and target_node:
        matched = (
            curr_node == target_node
            or db.is_descendant_of(session_id, curr_node, target_node)
            or db.is_descendant_of(session_id, target_node, curr_node)
        )
    if not matched and target_loc:
        matched = check_location_matches_waypoint(current_location, target_loc)
    if not matched and static_target_loc:
        matched = check_location_matches_waypoint(current_location, static_target_loc)
    if not matched and target_npc and is_waypoint_npc_present_in_scene(session_id, target_npc):
        matched = True
    elif not matched and not curr_node and not target_loc and not target_npc:
        matched = True

    if not matched:
        return None

    # 1. If this action was an explicit quest-bound action:
    if is_quest_action:
        if action_quest_id and str(action_quest_id) != str(quest_id):
            return None
        if action_sub_obj_id is not None and sub_obj_id is not None and int(action_sub_obj_id) != int(sub_obj_id):
            return None
        return waypoint

    # 2. For un-tagged / custom / LLM actions:
    stage_label = waypoint.get("stage_label", "")
    target_npc = waypoint.get("target_npc", "")
    if check_action_matches_waypoint(action_text, narrative, stage_label, sub_obj_text, target_npc):
        return waypoint

    return None


def try_complete_on_skill_check(
    session_id: int, quest_id: str, sub_obj_id: Optional[int],
    current_location: str, check_success: bool, check_result_tier: str = "success",
    action_text: str = "", narrative: str = "", sub_obj_text: str = "",
    is_quest_action: bool = False, action_quest_id: str = "", action_sub_obj_id: Optional[int] = None
) -> Optional[dict]:
    """Called when a choice resolves. Advances 'skill_check' trigger stages on success at target."""
    waypoint = does_action_target_waypoint(
        session_id=session_id,
        quest_id=quest_id,
        sub_obj_id=sub_obj_id,
        current_location=current_location,
        action_text=action_text,
        narrative=narrative,
        sub_obj_text=sub_obj_text,
        is_quest_action=is_quest_action,
        action_quest_id=action_quest_id,
        action_sub_obj_id=action_sub_obj_id,
    )
    if not waypoint:
        return None
    if not check_success:
        return None

    resource_target = int(waypoint.get("resource_target", 0))

    if resource_target > 0:
        tier_gains = {
            "critical_success": resource_target,
            "success": max(1, resource_target // 2),
            "partial": max(1, resource_target // 4),
            "failure": 0,
        }
        gain = tier_gains.get(check_result_tier, tier_gains["success"])
        progress = db.update_waypoint_resource_progress(session_id, quest_id, waypoint["stage_index"], gain, sub_obj_id)
        if not progress.get("complete"):
            return {
                "quest_id": quest_id,
                "sub_obj_id": sub_obj_id,
                "stage_completed": None,
                "stage_label": waypoint.get("stage_label", ""),
                "next_waypoint": dict(waypoint),
                "all_stages_complete": False,
                "trigger": "resource_progress",
                "resource_collected": progress["collected"],
                "resource_target": progress["target"],
            }

    next_wp = db.advance_waypoint(session_id, quest_id, waypoint["stage_index"], sub_obj_id)
    stage_complete = next_wp is None

    notice = {
        "quest_id": quest_id,
        "sub_obj_id": sub_obj_id,
        "stage_completed": waypoint["stage_index"],
        "stage_label": waypoint.get("stage_label", ""),
        "next_waypoint": dict(next_wp) if next_wp else None,
        "all_stages_complete": stage_complete,
        "trigger": waypoint.get("completion_trigger", "skill_check"),
    }

    if resource_target > 0:
        notice["resource_collected"] = resource_target
        notice["resource_target"] = resource_target

    if stage_complete:
        if sub_obj_id is not None:
            db.mark_sub_objective_completed_in_quest(session_id, quest_id, sub_obj_id)
            notice["sub_obj_completed"] = True
        else:
            notice["quest_completed"] = True

    return notice


def get_story_quest_climax_location(session_id: int) -> tuple[Optional[dict], Optional[str]]:
    """
    Returns (story_quest_dict, climax_location_str) if the active story quest has
    completed all sub-objectives and is ready for the Climax Encounter.
    """
    if not session_id:
        return None, None
    story_quest = db.get_active_story_quest(session_id)
    if not story_quest or story_quest.get("status") != "Active":
        return None, None

    sub_objs = story_quest.get("sub_objectives", []) or []
    if not sub_objs or not all(isinstance(so, dict) and so.get("completed") for so in sub_objs):
        return None, None

    # All sub-objectives are done! Resolve the Climax Encounter location
    qid = story_quest.get("quest_id", "")

    with db.get_conn() as conn:
        # 1. Check if an explicit whole-quest / climax waypoint exists in DB
        row = conn.execute(
            "SELECT target_location FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND status IN ('active', 'locked') LIMIT 1",
            (session_id, qid)
        ).fetchone()
        if row and row["target_location"]:
            return story_quest, row["target_location"]

        # 2. Check the target location of the highest sub_obj_id waypoint
        row_sub = conn.execute(
            "SELECT target_location FROM quest_waypoints WHERE session_id=? AND quest_id=? AND target_location IS NOT NULL AND target_location != '' ORDER BY sub_obj_id DESC, stage_index DESC LIMIT 1",
            (session_id, qid)
        ).fetchone()
        if row_sub and row_sub["target_location"]:
            return story_quest, row_sub["target_location"]

    # 3. Check session's current location or seeded locations
    session = db.get_session(session_id)
    cur_loc = session.get("current_location", "") if session else ""
    if cur_loc:
        return story_quest, cur_loc

    locs = db.get_session_locations(session_id)
    if locs:
        z = locs[0].get("zone_name", "")
        p = locs[0].get("primary_name", "")
        if z and p:
            return story_quest, f"{z} ➔ {p}"

    return story_quest, "Local Area"


