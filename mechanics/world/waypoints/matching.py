from __future__ import annotations
"""
Location matching, arrival triggers, and skill check completion logic.
"""
import re
from typing import Optional, Any

import db
from .templates import parse_zone_primary


def check_location_matches_waypoint(current_location: str, target_location: str) -> bool:
    """Returns True if current_location matches the waypoint target.
    Matches on Zone + Primary only. Empty target always matches.
    Robust to multi-tier inversion (e.g. Student Council Office inside Administration Wing).
    """
    if not target_location or not target_location.strip():
        return True
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


# ---------------------------------------------------------------- Waypoint Stage Triggers

def try_advance_on_arrival(session_id: int, quest_id: str, sub_obj_id: Optional[int], current_location: str) -> Optional[dict]:
    """Called every turn. Advances 'arrival' trigger stages when player reaches target,
    or when player travels directly to the next stage's location past an 'arrival'-only scout stage."""
    waypoint = db.get_active_waypoint(session_id, quest_id, sub_obj_id)
    if not waypoint:
        return None
    if waypoint.get("completion_trigger") != "arrival":
        return None
    target_loc = waypoint.get("target_location", "")
    if not check_location_matches_waypoint(current_location, target_loc):
        # Check if the player traveled directly to the immediately following stage's location,
        # bypassing an 'arrival'-only scouting waypoint.
        all_wps = db.get_quest_waypoints(session_id, quest_id, sub_obj_id) or []
        next_stage = next(
            (w for w in all_wps if w.get("stage_index") == waypoint.get("stage_index", 1) + 1 and w.get("status") == "locked"),
            None
        )
        if not next_stage or not check_location_matches_waypoint(current_location, next_stage.get("target_location", "")):
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
        interact_verbs = {"talk", "speak", "ask", "confront", "approach", "deliver", "give", "hand", "tell", "interrogate", "bribe", "persuade", "consult", "meet"}
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
    # To prevent ambient setting nouns (e.g. "prototype", "airship") from falsely completing
    # a stage when the player did a completely different action, the narrative must match
    # at least one operative keyword from the stage label itself.
    if stage_keywords:
        if any(kw in narr_lower for kw in stage_keywords):
            return True
        return False

    if sub_keywords:
        if any(kw in narr_lower for kw in sub_keywords):
            return True
        return False

    return True


def try_complete_on_skill_check(
    session_id: int, quest_id: str, sub_obj_id: Optional[int],
    current_location: str, check_success: bool, check_result_tier: str = "success",
    action_text: str = "", narrative: str = "", sub_obj_text: str = "",
    is_quest_action: bool = False, action_quest_id: str = "", action_sub_obj_id: Optional[int] = None
) -> Optional[dict]:
    """Called when a choice resolves. Advances 'skill_check' trigger stages on success at target."""
    waypoint = db.get_active_waypoint(session_id, quest_id, sub_obj_id)
    if not waypoint:
        return None
    if waypoint.get("completion_trigger") not in ("skill_check", "inspect_prop", "talk_to_npc", "resource_progress", "defeat_target"):
        return None
    target_loc = waypoint.get("target_location", "")
    if not check_location_matches_waypoint(current_location, target_loc):
        return None
    if not check_success:
        return None

    # 1. If this action was an explicit quest-bound action:
    if is_quest_action:
        # Must match this specific quest and sub_obj
        if action_quest_id and str(action_quest_id) != str(quest_id):
            return None
        if action_sub_obj_id is not None and sub_obj_id is not None and int(action_sub_obj_id) != int(sub_obj_id):
            return None
        # Explicit quest action succeeded -> advance immediately (0% false negatives)
    else:
        # 2. For un-tagged / custom / LLM actions, apply strict keyword and NPC relevance checks
        stage_label = waypoint.get("stage_label", "")
        target_npc = waypoint.get("target_npc", "")
        if not check_action_matches_waypoint(action_text, narrative, stage_label, sub_obj_text, target_npc):
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


