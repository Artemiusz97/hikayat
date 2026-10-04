from __future__ import annotations
"""
Quest action choice generation and metadata tagging for the LLM.
"""
import re
import random
import json
from typing import Optional, Any

import db
from .matching import check_location_matches_waypoint, get_story_quest_climax_location

def generate_quest_action_choices(
    session_id: int, current_location: str, scen_key: str = "fantasy", char: dict = None
) -> list[dict]:
    """
    Deterministically synthesizes dedicated Quest Action choices whenever the player is at the
    target location coordinates of an active waypoint stage or ready for a Story Quest Climax.
    Each choice is tagged with explicit quest metadata (quest_id, sub_obj_id, stage_index, is_quest_action=True).
    """
    if not session_id or not current_location:
        return []

    quest_choices = []

    # 1. Check if Story Quest is in Climax Ready state
    story_quest, climax_loc = get_story_quest_climax_location(session_id)
    if story_quest and climax_loc and check_location_matches_waypoint(current_location, climax_loc):
        sq_title = story_quest.get("title", "Story Quest")
        stat = "CHA" if "high_school" in scen_key or "modern" in scen_key else ("INT" if "sci" in scen_key else "STR")
        req = 6
        if char and isinstance(char.get("stats"), dict):
            c_stat = int(char["stats"].get(stat, 5))
            req = max(4, min(10, c_stat))

        if "high_school" in scen_key or "modern" in scen_key:
            climax_label = f"⚡ [Story Climax] Present your resolution plan for '{sq_title}' and coordinate the student body ({stat})"
        elif "cyberpunk" in scen_key or "scifi" in scen_key:
            climax_label = f"⚡ [Story Climax] Execute the final operation and secure '{sq_title}' ({stat})"
        elif "postapoc" in scen_key:
            climax_label = f"⚡ [Story Climax] Rally the survivors and overcome the crisis of '{sq_title}' ({stat})"
        elif "nsfw" in scen_key:
            climax_label = f"⚡ [Story Climax] Take the decisive initiative and resolve '{sq_title}' ({stat})"
        else:
            climax_label = f"⚡ [Story Climax] Confront the threat and bring '{sq_title}' to a decisive resolution ({stat})"

        quest_choices.append({
            "label": climax_label,
            "stat": stat,
            "requirement": req,
            "mp_cost": 0,
            "is_fallback": False,
            "quest_id": story_quest.get("quest_id"),
            "sub_obj_id": None,
            "stage_index": 99,
            "is_quest_action": True,
            "is_climax_action": True,
            "contract_type": "climax"
        })

    active_wps = db.get_all_session_active_waypoints(session_id)
    if not active_wps and not quest_choices:
        return []

    for wp in active_wps:
        target_loc = wp.get("target_location", "")
        if not target_loc or not check_location_matches_waypoint(current_location, target_loc):
            continue

        trigger = wp.get("completion_trigger", "skill_check")
        if trigger not in ("skill_check", "inspect_prop", "talk_to_npc", "resource_progress", "defeat_target"):
            continue

        stage_label = wp.get("stage_label", "").strip()
        if not stage_label:
            continue

        qid = wp.get("quest_id", "")
        sub_obj_id = wp.get("sub_obj_id")
        stage_idx = wp.get("stage_index", 1)
        quest_title = wp.get("quest_title", "Quest")
        is_story = bool(wp.get("is_story_quest") or "SQ-" in str(qid) or "story" in str(qid).lower())
        prefix = "Story Quest" if is_story else "Bounty"
        icon = "⭐" if is_story else "🎯"

        # Deduce primary stat based on stage label and character stats
        label_lower = stage_label.lower()
        if any(w in label_lower for w in ("interrogate", "gossip", "convince", "persuade", "charm", "seduce", "negotiate", "confront", "talk", "speak")):
            stat = "CHA"
        elif any(w in label_lower for w in ("search", "investigate", "analyze", "decipher", "examine", "hack", "study", "identify", "read", "formula", "blueprint", "notes", "evidence")):
            stat = "INT"
        elif any(w in label_lower for w in ("sneak", "eavesdrop", "pick", "steal", "infiltrate", "bypass", "evade", "climb", "slip", "shadow")):
            stat = "AGI"
        elif any(w in label_lower for w in ("force", "pry", "break", "lift", "smash", "strike", "breach")):
            stat = "STR"
        elif any(w in label_lower for w in ("track", "scout", "spot", "perceive", "notice", "detect", "survey")):
            stat = "PER"
        elif any(w in label_lower for w in ("survive", "endure", "shield", "resist", "withstand")):
            stat = "END"
        else:
            stat = "INT" if "high_school" in scen_key or "modern" in scen_key else "AGI"

        req = 3
        if char and isinstance(char.get("stats"), dict):
            c_stat = int(char["stats"].get(stat, 5))
            req = max(2, min(8, c_stat - 1))

        clean_stage = stage_label[0].upper() + stage_label[1:] if len(stage_label) > 1 else stage_label
        if clean_stage.endswith("."):
            clean_stage = clean_stage[:-1]

        choice_label = f"{icon} [{prefix}] {clean_stage} ({stat})"
        quest_choices.append({
            "label": choice_label,
            "stat": stat,
            "requirement": req,
            "mp_cost": 0,
            "is_fallback": False,
            "quest_id": qid,
            "sub_obj_id": sub_obj_id,
            "stage_index": stage_idx,
            "is_quest_action": True,
            "is_story_quest": is_story,
            "contract_type": trigger
        })

        if len(quest_choices) >= 2:
            break

    return quest_choices


def _extract_word_stems(words: set[str] | list[str]) -> set[str]:
    """Returns a set of normalized root stems (>= 4 chars) for fuzzy keyword matching."""
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


def tag_and_enrich_quest_choices(
    choices: list[dict],
    session_id: int,
    current_location: str,
    scen_key: str = "fantasy",
    char: dict = None,
    dialogue_partner: Any = ...,
    current_npcs: list = None,
    allow_fallback: bool = True,
) -> list[dict]:
    """
    Seamlessly inspects LLM-generated choices against active quest waypoints at the current location.
    1. Identifies if any LLM choice aligns with the active quest/waypoint (contextually or by keywords).
    2. Dynamically tags the best matching choice with ⭐ [Story Quest] / 🎯 [Bounty] and metadata.
    3. If no LLM choice matches the active quest at a required location, provides a fallback quest choice.
    4. Deduplicates redundant choices so the menu remains natural, distinct, and responsive.
    """
    if not choices:
        choices = []

    active_wps = db.get_all_session_active_waypoints(session_id)
    story_quest, climax_loc = get_story_quest_climax_location(session_id)
    climax_ready_at_loc = bool(story_quest and climax_loc and check_location_matches_waypoint(current_location, climax_loc))

    # Detect if characters are in active 1-on-1 or group dialogue
    from mechanics.world.mobility import get_session_dialogue_partners
    session_row = db.get_session(session_id)
    if dialogue_partner is not ...:
        if isinstance(dialogue_partner, list):
            active_dps = [str(p).strip() for p in dialogue_partner if str(p).strip()]
        elif isinstance(dialogue_partner, str) and dialogue_partner.strip():
            active_dps = [dialogue_partner.strip()]
        else:
            active_dps = []
    else:
        active_dps = get_session_dialogue_partners(session_row)
    in_active_dialogue = bool(active_dps)
    dp_name = active_dps[0].lower() if in_active_dialogue else ""

    # Check if there are active phone appointments at this location
    appts_at_loc = []
    try:
        appts = db.get_phone_appointments(session_id, status="pending") + db.get_phone_appointments(session_id, status="arrived")
        for appt in appts:
            appt_loc = appt.get("rendezvous_location", "")
            if appt_loc and check_location_matches_waypoint(current_location, appt_loc):
                appts_at_loc.append(appt)
    except Exception:
        pass

    if not active_wps and not climax_ready_at_loc and not appts_at_loc:
        return choices

    # Find active waypoints matching current location
    matching_wps = [
        wp for wp in active_wps
        if wp.get("target_location") and check_location_matches_waypoint(current_location, wp["target_location"])
    ]

    if not matching_wps and not climax_ready_at_loc and not appts_at_loc:
        return choices

    result_choices = []
    seen_labels = set()
    for c in choices:
        if not isinstance(c, dict):
            continue
        c_label = str(c.get("label", "")).strip()
        c_label_clean = re.sub(r"^[⭐🎯⚡🔹\s\[\]]+", "", c_label).lower().strip()
        if not c_label_clean or c_label_clean in seen_labels:
            continue
        seen_labels.add(c_label_clean)
        result_choices.append(dict(c))

    # 1. Check for Climax Ready Story Quest at current location
    if climax_ready_at_loc:
        sq_id = story_quest.get("quest_id", "")
        sq_title = story_quest.get("title", "Story Quest")
        
        already_tagged_climax = any(
            c.get("is_climax_action") or (c.get("is_quest_action") and c.get("quest_id") == sq_id)
            for c in result_choices
        )
        if not already_tagged_climax:
            climax_keywords = {
                "assert", "confront", "resolve", "implement", "plan", "order", "expose",
                "execute", "authority", "evidence", "sabotage", "lead", "demand", "challenge",
                "propose", "reorganization", "mandate", "climax", "showdown", "truth",
                "discuss", "negotiate", "convince", "persuade", "reassure", "address", "steps",
                "take charge", "rally", "unite", "reorganize", "stabilize", "settle", "present",
                "explain", "prove", "delegate", "action", "initiative", "next steps", "coordinate"
            }
            for w in re.findall(r"\w{3,}", sq_title.lower()):
                if w not in ("the", "and", "for", "with", "from", "that", "this"):
                    climax_keywords.add(w)
            for so in (story_quest.get("sub_objectives") or []):
                for w in re.findall(r"\w{3,}", (so.get("text", "") if isinstance(so, dict) else "").lower()):
                    if w not in ("the", "and", "for", "with", "from", "that", "this"):
                        climax_keywords.add(w)

            best_climax_choice = None
            best_climax_score = 0

            for c in result_choices:
                if c.get("is_quest_action"):
                    continue
                lbl = str(c.get("label", "")).lower()
                # Don't tag purely passive exits as the climax
                from mechanics.narrative.intent import is_conversational_exit
                if c.get("stat") == "NONE" and c.get("requirement", 0) == 0 and (is_conversational_exit(lbl) or "look around" in lbl):
                    continue
                score = sum(1 for kw in climax_keywords if kw in lbl)
                if c.get("stat") not in ("NONE", None) and c.get("requirement", 0) > 0:
                    score += 1
                if score > best_climax_score:
                    best_climax_score = score
                    best_climax_choice = c

            if best_climax_choice and best_climax_score >= 1:
                best_climax_choice["is_quest_action"] = True
                best_climax_choice["is_climax_action"] = True
                best_climax_choice["is_story_quest"] = True
                best_climax_choice["quest_id"] = sq_id
                best_climax_choice["sub_obj_id"] = None
                best_climax_choice["stage_index"] = 99
                best_climax_choice["contract_type"] = "climax"
                # Upgrade stat to a meaningful check if it was NONE/0
                if best_climax_choice.get("stat") in ("NONE", None, "FREE") or best_climax_choice.get("requirement", 0) == 0:
                    c_stat = "CHA" if "high_school" in scen_key or "modern" in scen_key else "INT"
                    best_climax_choice["stat"] = c_stat
                    req = 6
                    if char and isinstance(char.get("stats"), dict):
                        req = max(4, min(10, int(char["stats"].get(c_stat, 5))))
                    best_climax_choice["requirement"] = req

                raw_label = best_climax_choice.get("label", "")
                if not raw_label.startswith("⚡ [Story Climax]") and not raw_label.startswith("[Story Climax]"):
                    clean_lbl = re.sub(r"^\[.*?\]\s*", "", raw_label).strip()
                    best_climax_choice["label"] = f"⚡ [Story Climax] {clean_lbl}"
            else:
                if not in_active_dialogue and allow_fallback:
                    fallback_choices = generate_quest_action_choices(session_id, current_location, scen_key=scen_key, char=char)
                    if fallback_choices:
                        result_choices.insert(0, fallback_choices[0])

        for c in result_choices:
            if c.get("is_climax_action") or str(c.get("contract_type", "")).lower() == "climax":
                raw_label = c.get("label", "")
                if not raw_label.startswith("⚡ [Story Climax]") and not raw_label.startswith("[Story Climax]"):
                    clean_lbl = re.sub(r"^\[.*?\]\s*", "", raw_label).strip()
                    c["label"] = f"⚡ [Story Climax] {clean_lbl}"

    scene_npcs = current_npcs if current_npcs is not None else (session_row.get("current_npcs", []) if session_row else [])
    present_names = {str((n.get("name") or n.get("npc_name")) if isinstance(n, dict) else n).strip().lower() for n in (scene_npcs or []) if n}

    # For each matching waypoint, find the best matching choice
    for wp in matching_wps:
        qid = wp.get("quest_id", "")
        sub_obj_id = wp.get("sub_obj_id")
        stage_idx = wp.get("stage_index", 1)
        trigger = wp.get("completion_trigger", "skill_check")
        stage_label = str(wp.get("stage_label", "")).strip()
        target_npc = str(wp.get("target_npc", "")).strip().lower()
        is_story = bool(wp.get("is_story_quest") or "SQ-" in str(qid) or "story" in str(qid).lower())
        prefix = "Story Quest" if is_story else "Bounty"
        icon = "⭐" if is_story else "🎯"

        # Check if already tagged; if so, ensure its label prefix and story flag are intact
        already_tagged = False
        for c in result_choices:
            if c.get("is_quest_action") and c.get("quest_id") == qid:
                already_tagged = True
                c["is_story_quest"] = is_story
                raw_label = c.get("label", "")
                if not raw_label.startswith(f"{icon} [{prefix}]") and not raw_label.startswith(f"[{prefix}]"):
                    clean_lbl = re.sub(r"^(?:[⭐🎯⚡🔹\s]+|\s*\[[A-Za-z0-9/ _-]+\]\s*)+", "", raw_label).strip()
                    c["label"] = f"{icon} [{prefix}] {clean_lbl}"
        if already_tagged:
            continue

        npc_tokens = set()
        if target_npc:
            for w in target_npc.lower().split():
                if len(w) >= 3:
                    npc_tokens.add(w)
                    if w.startswith("arch") and len(w) >= 7:
                        npc_tokens.add(w[4:])

        # Check dialogue partner and room presence compatibility
        is_dp_match = True
        if in_active_dialogue:
            if not target_npc:
                is_dp_match = False
            elif dp_name and not (target_npc in dp_name or dp_name in target_npc or any(tok in dp_name for tok in npc_tokens)):
                is_dp_match = False

        is_npc_present = True
        if target_npc and present_names:
            is_npc_present = any(
                target_npc in pn or any(tok in pn for tok in npc_tokens)
                for pn in present_names
            )

        # Extract sub_obj_text from sub_objectives_json if not directly present on wp
        sub_obj_text = str(wp.get("sub_obj_text") or "").strip()
        if not sub_obj_text and wp.get("sub_objectives_json"):
            try:
                raw_subs = wp["sub_objectives_json"]
                subs_list = json.loads(raw_subs) if isinstance(raw_subs, str) else raw_subs
                if isinstance(subs_list, list):
                    for so in subs_list:
                        if isinstance(so, dict) and str(so.get("id")) == str(sub_obj_id):
                            sub_obj_text = str(so.get("text", "")).strip()
                            break
            except Exception:
                pass

        # Keywords for scoring
        conversational_verbs = {"discuss", "talk", "ask", "chat", "speak", "greet", "inquire", "explain", "introduce"}
        generic_quest_words = {
            "with", "that", "this", "from", "into", "your", "their", "have", "about", "meet",
            "main", "quest", "story", "bounty", "find", "work", "then", "finally", "around",
            "where", "when", "what", "before", "after", "reach", "travel", "return", "collect"
        }
        ignore_words = generic_quest_words | npc_tokens | conversational_verbs

        stage_words = {
            w for w in re.findall(r"\w{4,}", stage_label.lower())
            if w not in ignore_words
        }
        sub_words = {
            w for w in re.findall(r"\w{4,}", sub_obj_text.lower())
            if w not in ignore_words
        }
        title_words = {
            w for w in re.findall(r"\w{4,}", str(wp.get("quest_title", "")).lower())
            if w not in ignore_words
        }

        stage_stems = _extract_word_stems(stage_words)
        sub_stems = _extract_word_stems(sub_words | title_words)
        substantive_task_keywords = stage_stems | sub_stems

        extra_keywords = set()
        if not in_active_dialogue:
            extra_keywords.update(npc_tokens)
            action_verbs = {"negotiate", "report", "submit", "evidence", "sabotage", "investigate", "present", "convince", "sanitized", "terms"}
            extra_keywords.update(action_verbs)

        # Unrelated NPC names present in the room (to prevent tagging a choice talking to Maya when Michael is the target)
        unrelated_npc_tokens = set()
        for pn in (present_names | ({dp_name} if dp_name else set())):
            if not pn:
                continue
            if target_npc and (target_npc in pn or any(tok in pn for tok in npc_tokens)):
                continue
            for tok in pn.split():
                if len(tok) >= 3 and tok not in ("the", "elder", "lord", "lady", "sir", "madam", "captain", "druid", "scholar", "guard"):
                    unrelated_npc_tokens.add(tok)

        best_choice = None
        best_score = 0.0

        for c in result_choices:
            if c.get("is_quest_action"):
                continue
            lbl = str(c.get("label", "")).lower()
            # Don't tag conversational exit choices as the quest action
            from mechanics.narrative.intent import is_conversational_exit
            if c.get("stat") == "NONE" and c.get("requirement", 0) == 0 and (is_conversational_exit(lbl) or "look around" in lbl):
                continue

            score = 0.0
            substantive_matches = 0
            has_stage_match = False

            for kw in stage_stems:
                if kw in lbl:
                    score += 3.0 if kw in stage_words else 2.0
                    substantive_matches += 1
                    has_stage_match = True

            for kw in (sub_stems - stage_stems):
                if kw in lbl:
                    score += 2.0 if kw in sub_words else 1.5
                    substantive_matches += 1

            for kw in extra_keywords:
                if kw in lbl:
                    score += 1.0

            has_substantive_match = substantive_matches >= 1

            # In active dialogue, require at least one substantive task keyword match so off-topic chatting isn't tagged as quest action
            if in_active_dialogue and not has_substantive_match:
                continue

            # If target_npc is not detected in present_names or dialogue_partner, only allow tagging an existing choice
            # if it has strong substantive task matches (>= 2 task keywords or a direct stage keyword) and does NOT address an unrelated NPC
            if not is_dp_match or not is_npc_present:
                addresses_unrelated_npc = any(f" {ut}" in f" {lbl}" for ut in unrelated_npc_tokens)
                if addresses_unrelated_npc or (substantive_matches < 2 and not has_stage_match):
                    continue

            if has_substantive_match and c.get("stat") not in ("NONE", "FREE", None) and (c.get("requirement") or 0) > 0:
                score += 0.5

            if score > best_score:
                best_score = score
                best_choice = c

        if best_choice and best_score >= 1.0:
            # Enrich and tag this choice
            best_choice["is_quest_action"] = True
            best_choice["is_story_quest"] = is_story
            best_choice["quest_id"] = qid
            best_choice["sub_obj_id"] = sub_obj_id
            best_choice["stage_index"] = stage_idx
            best_choice["contract_type"] = trigger
            raw_label = best_choice.get("label", "")
            if not raw_label.startswith(f"{icon} [{prefix}]") and not raw_label.startswith(f"[{prefix}]"):
                clean_lbl = re.sub(r"^\[.*?\]\s*", "", raw_label).strip()
                best_choice["label"] = f"{icon} [{prefix}] {clean_lbl}"
        elif allow_fallback and is_dp_match and is_npc_present:
            # Fallback: LLM generated no quest-relevant option and target NPC guard passed
            if not in_active_dialogue:
                fallback_choices = generate_quest_action_choices(session_id, current_location, scen_key=scen_key, char=char)
                if fallback_choices:
                    result_choices.insert(0, fallback_choices[0])
            elif in_active_dialogue and target_npc:
                # In active dialogue with the target NPC, but LLM choices drifted off-topic: guarantee a dedicated in-dialogue choice
                tgt_disp = target_npc.title()
                c_lbl = f"{icon} [{prefix}] Discuss the task with {tgt_disp}: {stage_label}"
                in_dialogue_bounty_choice = {
                    "label": c_lbl[:190],
                    "stat": "CHA",
                    "requirement": 6,
                    "mp_cost": 0,
                    "is_quest_action": True,
                    "is_story_quest": is_story,
                    "quest_id": qid,
                    "sub_obj_id": sub_obj_id,
                    "stage_index": stage_idx,
                    "contract_type": trigger,
                }
                result_choices.insert(0, in_dialogue_bounty_choice)

    # Phone meetup appointment choices: guarantee interaction option at rendezvous ONLY when in open exploration (not in dialogue)
    try:
        from mechanics.world.mobility import get_session_dialogue_partners
        dp_list = [p.lower() for p in active_dps]

        pending_appts = db.get_phone_appointments(session_id, status="pending")
        arrived_appts = [
            a for a in db.get_phone_appointments(session_id, status="arrived")
            if any(str((x.get("name") or x.get("npc_name")) if isinstance(x, dict) else x).strip().lower() == a.get("npc_name", "").strip().lower() for x in (scene_npcs or []))
            or any(dp == a.get("npc_name", "").strip().lower() for dp in dp_list)
        ] if session_row else []
        for appt in (pending_appts + arrived_appts):
            appt_loc = appt.get("rendezvous_location", "")
            npc_name = appt.get("npc_name", "")
            if appt_loc and npc_name and check_location_matches_waypoint(current_location, appt_loc):
                npc_low = npc_name.lower().strip()
                # If already in active dialogue with this NPC, NEVER inject an initiation/greeting choice!
                if any(dp in npc_low or npc_low in dp for dp in dp_list):
                    continue
                npc_first = npc_low.split()[0] if npc_low else ""
                has_npc_choice = any(
                    npc_low in str(c.get("label", "")).lower() or
                    (len(npc_first) >= 3 and f" {npc_first}" in f" {str(c.get('label', '')).lower()}")
                    for c in result_choices
                )
                if not has_npc_choice and not dp_list:
                    result_choices.insert(0, {
                        "label": f"💌 [Meetup] Greet and talk with {npc_name}",
                        "stat": "NONE",
                        "requirement": 0,
                        "is_quest_action": False
                    })
    except Exception:
        pass

    return result_choices


# ---------------------------------------------------------------- LLM System Prompt Block
