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


def has_caseboard_breakthrough_for_waypoint(
    session_id: int | dict, wp: dict, quest_obj: dict = None
) -> bool:
    """Checks if the quest associated with the waypoint has an active caseboard breakthrough tag."""
    from mechanics.narrative.blueprints import has_quest_note_flag
    if quest_obj and has_quest_note_flag(quest_obj.get("quest_notes"), "caseboard_breakthrough"):
        return True
    if has_quest_note_flag(wp.get("quest_notes"), "caseboard_breakthrough"):
        return True
    sid = session_id if isinstance(session_id, int) else (session_id.get("id") if isinstance(session_id, dict) else 0)
    qid = wp.get("quest_id")
    if sid and qid:
        try:
            q_row = db.get_quest_by_id(sid, qid)
            if q_row and has_quest_note_flag(q_row.get("quest_notes"), "caseboard_breakthrough"):
                return True
        except Exception:
            pass
    return False


def get_active_companion_for_waypoint(session_id: int | dict, wp: dict) -> dict | None:
    """
    Returns the primary active companion in the party (or temporary hangout companion
    in non-combat scenarios) for waypoint assistance, if any.
    Enriches companion role/club from contacts if needed and prefers a role-matching companion.
    """
    sid = session_id if isinstance(session_id, int) else (session_id.get("id") if isinstance(session_id, dict) else 0)
    if not sid:
        return None
    try:
        # Phase 5 A18: Companion Assistance Privacy Gate
        sess = session_id if isinstance(session_id, dict) else db.get_session(sid)
        if isinstance(sess, dict):
            cur_nid = sess.get("current_node_id") or ""
            curr_node = db.get_world_node(sid, cur_nid) if cur_nid else None
            if curr_node and curr_node.get("privacy_level") == "private":
                intimate_active = bool(sess.get("_intimate_active") or sess.get("intimate_contact"))
                if not intimate_active:
                    return None

        party = list(db.get_session_party_npcs(sid) or [])
        temp_comps = list(db.get_temporary_companions(sid) or [])
        all_raw = party + temp_comps
        if not all_raw:
            return None

        target_npc_low = str((wp or {}).get("target_npc") or "").strip().lower()
        contacts_by_name = {}
        try:
            for c in (db.get_contacts(sid) or []):
                if isinstance(c, dict) and c.get("name"):
                    contacts_by_name[str(c["name"]).strip().lower()] = c
        except Exception:
            pass

        candidates = []
        seen_names = set()
        for comp in all_raw:
            if not isinstance(comp, dict) or not comp.get("name"):
                continue
            c_name = str(comp["name"]).strip()
            c_low = c_name.lower()
            if c_low in seen_names:
                continue
            if target_npc_low and c_low == target_npc_low:
                continue
            seen_names.add(c_low)
            enriched = dict(comp)
            if not (enriched.get("role") or enriched.get("club")) and c_low in contacts_by_name:
                c_rec = contacts_by_name[c_low]
                b_info = c_rec.get("basic_info") if isinstance(c_rec.get("basic_info"), dict) else {}
                enriched["role"] = c_rec.get("role") or b_info.get("role") or b_info.get("occupation") or ""
                enriched["club"] = c_rec.get("club") or b_info.get("club") or ""
            candidates.append(enriched)

        if not candidates:
            return None

        if len(candidates) > 1 and wp:
            try:
                from mechanics.narrative.blueprints import evaluate_companion_assist_for_blueprint, get_blueprint_for_archetype
                bp_id = wp.get("blueprint_id") or get_blueprint_for_archetype(wp.get("archetype", ""), wp.get("stage_label", ""))
                for cand in candidates:
                    if evaluate_companion_assist_for_blueprint(cand, bp_id).get("is_role_match"):
                        return cand
            except Exception:
                pass

        return candidates[0]
    except Exception:
        pass
    return None



def generate_quest_action_choices(
    session_id: int | dict,
    current_location: str = "",
    scen_key: str = "fantasy",
    char: dict = None,
    dossier: Optional[dict] = None,
    session: Optional[dict] = None,
    session_time: Optional[tuple] = None,
) -> list[dict]:
    """
    Deterministically synthesizes dedicated Quest Action choices whenever the player is at the
    target location coordinates of an active waypoint stage or ready for a Story Quest Climax.
    Each choice is tagged with explicit quest metadata (quest_id, sub_obj_id, stage_index, is_quest_action=True).
    """
    _sess_cache: Optional[dict] = session if isinstance(session, dict) else None
    if isinstance(session_id, dict):
        sess_dict = session_id
        _sess_cache = sess_dict
        session_id = sess_dict.get("id") or 0
        if not current_location or isinstance(current_location, (list, tuple)):
            current_location = sess_dict.get("current_location", "")
        if scen_key == "fantasy" and sess_dict.get("scenario"):
            scen_key = sess_dict.get("scenario")

    if not session_id or not current_location:
        return []

    quest_choices = []

    # 1. Check if Story Quest is in Climax Ready state (or premature showdown)
    story_quest, climax_loc = get_story_quest_climax_location(session_id, allow_premature=True)
    if story_quest and climax_loc and check_location_matches_waypoint(current_location, climax_loc):
        sq_title = story_quest.get("title", "Story Quest")
        sub_objs = story_quest.get("sub_objectives", []) or []
        is_premature = bool(sub_objs and not db.is_quest_main_objectives_complete(sub_objs))
        stat = "CHA" if "high_school" in scen_key or "modern" in scen_key else ("INT" if "sci" in scen_key else "STR")
        req = 6
        if char and isinstance(char.get("stats"), dict):
            c_stat = int(char["stats"].get(stat, 5))
            req = max(4, min(10, c_stat))
        _sq_cs = ((story_quest.get("dossier") or {}).get("climax_spec") or {})
        req = max(2, min(14, req - int(_sq_cs.get("aid_dc_reduction") or 0) + int(_sq_cs.get("alert_dc_bonus") or 0)))
        if is_premature:
            req += 4  # Phase 5 A11: +4 DC penalty for premature confrontation

        if is_premature:
            climax_label = f"Confront the threat for '{sq_title}' without full evidence ({stat})"
        elif "high_school" in scen_key or "modern" in scen_key:
            climax_label = f"Present your resolution plan for '{sq_title}' and coordinate the student body ({stat})"
        elif "cyberpunk" in scen_key or "scifi" in scen_key:
            climax_label = f"Execute the final operation and secure '{sq_title}' ({stat})"
        elif "postapoc" in scen_key:
            climax_label = f"Rally the survivors and overcome the crisis of '{sq_title}' ({stat})"
        elif "nsfw" in scen_key:
            climax_label = f"Take the decisive initiative and resolve '{sq_title}' ({stat})"
        else:
            climax_label = f"Confront the threat and bring '{sq_title}' to a decisive resolution ({stat})"

        quest_choices.append({
            "label": climax_label,
            "stat": stat,
            "requirement": req,
            "mp_cost": 0,
            "intent": "general_action",
            "sub_intent": "",
            "target_npc": "",
            "is_fallback": False,
            "quest_id": story_quest.get("quest_id"),
            "sub_obj_id": None,
            "stage_index": 99,
            "is_quest_action": True,
            "is_story_quest": True,
            "is_climax_action": True,
            "is_premature_climax": is_premature,
            "contract_type": "climax"
        })

    active_wps = db.get_all_session_active_waypoints(session_id)
    if not active_wps and not quest_choices:
        return []

    _dossier_cache: dict[str, Any] = {}
    if isinstance(dossier, dict) and dossier.get("quest_id"):
        _dossier_cache[str(dossier["quest_id"])] = dossier
    _wps_cache: dict[tuple, list] = {}
    _char_cache: dict[Any, Any] = {}
    _time_cache = (
        session_time
        if session_time is not None
        else (db.get_session_time(session_id) if session_id else (1, 480, 0))
    )

    for wp in active_wps:
        from .matching import (
            resolve_effective_waypoint_location,
            is_waypoint_npc_present_in_scene,
            resolve_waypoint_target_npc,
            can_waypoint_match_via_npc_presence,
            get_matching_clue_sources_for_location,
        )
        qid = wp.get("quest_id", "")
        qid_key = str(qid or "")
        if session_id and qid_key and qid_key not in _dossier_cache:
            _dossier_cache[qid_key] = db.get_quest_dossier(session_id, qid_key)
        _wp_dos = _dossier_cache.get(qid_key)
        target_loc = wp.get("target_location", "")
        target_npc = resolve_waypoint_target_npc(session_id, wp) or wp.get("target_npc", "")
        eff_loc = resolve_effective_waypoint_location(session_id, wp, session=_sess_cache, session_time=_time_cache) if session_id else target_loc
        static_loc = wp.get("static_target_location") or target_loc
        can_npc_match = can_waypoint_match_via_npc_presence(target_npc, wp.get("stage_key", ""), current_location, wp)
        clue_info = get_matching_clue_sources_for_location(
            session_id,
            qid,
            wp.get("sub_obj_id"),
            current_location,
            waypoint=wp,
            include_bonus=True,
            dossier=_wp_dos,
        )
        has_open_clue_here = bool(clue_info.get("matching_open_sources"))
        has_bonus_clue_here = bool(clue_info.get("matching_bonus_sources"))
        if clue_info.get("is_clue_stage") or str(wp.get("completion_trigger") or "") == "key_clue":
            loc_matched = has_open_clue_here
        else:
            loc_matched = (
                (eff_loc and check_location_matches_waypoint(current_location, eff_loc, session_id=session_id))
                or (static_loc and check_location_matches_waypoint(current_location, static_loc, session_id=session_id))
                or (bool(target_npc) and can_npc_match and is_waypoint_npc_present_in_scene(session_id, target_npc))
            )

        # Emit E2 bonus corroborating clue choices even when active stage is in another room
        if has_bonus_clue_here and len(quest_choices) < 3:
            b_qid = wp.get("quest_id", "")
            b_is_story = bool(wp.get("is_story_quest") or "SQ-" in str(b_qid) or "story" in str(b_qid).lower())
            for bsrc in (clue_info.get("matching_bonus_sources") or []):
                if len(quest_choices) >= 3:
                    break
                b_stat = str(bsrc.get("stat") or ("CHA" if bsrc.get("kind") == "witness" else "PER")).upper()
                b_req = 3
                if char and isinstance(char.get("stats"), dict):
                    b_req = max(2, min(8, int(char["stats"].get(b_stat, 5)) - 1))
                b_hint = str(bsrc.get("approach_hint") or f"Corroborate {(bsrc.get('_key_clue') or {}).get('title') or 'earlier lead'}").strip()
                quest_choices.append({
                    "label": f"{b_hint} ({b_stat})",
                    "stat": b_stat,
                    "requirement": b_req,
                    "mp_cost": 0,
                    "intent": "dialogue_init" if bsrc.get("kind") == "witness" else "investigate_clue",
                    "sub_intent": "",
                    "target_npc": str(bsrc.get("npc_name") or ""),
                    "is_fallback": False,
                    "quest_id": b_qid,
                    "sub_obj_id": wp.get("sub_obj_id"),
                    "stage_index": int(bsrc.get("_stage_index") or 1),
                    "is_quest_action": True,
                    "is_story_quest": b_is_story,
                    "contract_type": "key_clue",
                    "approach": str(bsrc.get("kind") or "record"),
                    "clue_source_id": str(bsrc.get("source_id") or ""),
                    "is_bonus_clue": True,
                    "gold_cost": 0,
                    "dc_mod": 0,
                })

        if not loc_matched:
            continue

        trigger = wp.get("completion_trigger", "skill_check")
        if trigger not in ("skill_check", "inspect_prop", "talk_to_npc", "resource_progress", "defeat_target", "action", "key_clue"):
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
        bp_id = wp.get("blueprint_id") or ""
        _wp_cs = (_wp_dos or {}).get("climax_spec") or {}
        _wp_opt_lead = next(
            (ld for ld in ((_wp_dos or {}).get("leads_graph") or []) if isinstance(ld, dict) and ld.get("is_optional") and int(ld.get("sub_obj_id") or -1) == int(sub_obj_id if sub_obj_id is not None else -2)),
            None,
        )
        if _wp_opt_lead:
            _opt_badge = str(_wp_opt_lead.get("badge") or f"Optional — {str(_wp_opt_lead.get('role') or 'aid').title()}")
            prefix = f"{prefix} | {_opt_badge}"
        res_approach = str(wp.get("resolution_approach") or "")
        reward_gold = int(wp.get("reward_gold") or 30)

        # Check total stages for this sub_obj or quest
        _wp_cache_key = (session_id, qid, sub_obj_id)
        if _wp_cache_key not in _wps_cache:
            _wps_cache[_wp_cache_key] = db.get_quest_waypoints(session_id, qid, sub_obj_id) or []
        all_wps = _wps_cache[_wp_cache_key]
        total_stages = len(all_wps) or 1

        # Check player gold
        player_gold = 0
        if char and isinstance(char.get("gold"), (int, float)):
            player_gold = int(char["gold"])
        elif session_id:
            try:
                if _sess_cache is None:
                    _sess_cache = db.get_session(session_id) if not isinstance(session_id, dict) else session_id
                sess_obj = _sess_cache
                h_uid = (sess_obj.get("turn_order") or [sess_obj.get("host_user_id")])[0] if sess_obj else None
                if h_uid:
                    if h_uid not in _char_cache:
                        _char_cache[h_uid] = db.get_character(h_uid)
                    h_char = _char_cache.get(h_uid)
                    if h_char and isinstance(h_char.get("gold"), (int, float)):
                        player_gold = int(h_char["gold"])
            except Exception:
                pass

        # Phase 3: Off-Duty Guard & Time Window Evaluation
        from .matching import get_waypoint_npc_schedule_info
        from mechanics.narrative.blueprints import evaluate_waypoint_time_window, is_purely_time_locked_stage

        curr_day, curr_min = _time_cache[0], _time_cache[1]
        sched_info = get_waypoint_npc_schedule_info(session_id, wp, session=_sess_cache, session_time=_time_cache) if session_id else {"is_off_duty": False}
        if sched_info.get("is_off_duty"):
            wait_m = int(sched_info.get("wait_until_morning_minutes") or 480)
            wake_clk = sched_info.get("wake_clock") or "07:30"
            quest_choices.append({
                "label": f"Wait until {wake_clk} to meet {target_npc} after their rest",
                "stat": "FREE",
                "requirement": 0,
                "mp_cost": 0,
                "intent": "general_action",
                "sub_intent": "",
                "target_npc": target_npc or "",
                "is_fallback": False,
                "quest_id": qid,
                "sub_obj_id": sub_obj_id,
                "stage_index": stage_idx,
                "is_quest_action": True,
                "is_story_quest": is_story,
                "contract_type": trigger,
                "approach": "wait_until_morning",
                "gold_cost": 0,
                "wait_minutes": wait_m,
            })
            if len(quest_choices) >= 3:
                break
            continue

        v_phases = wp.get("valid_time_phases") or []
        time_eval = evaluate_waypoint_time_window(curr_min, v_phases)
        out_of_window_dc_penalty = 0
        if v_phases and not time_eval["is_valid"]:
            t_phase = time_eval["target_phase"]
            t_clock = time_eval["target_clock"]
            wait_m = int(time_eval["wait_minutes"] or 60)
            quest_choices.append({
                "label": f"Stake out the area until {t_clock} ({t_phase})",
                "stat": "FREE",
                "requirement": 0,
                "mp_cost": 0,
                "intent": "general_action",
                "sub_intent": "",
                "target_npc": target_npc or "",
                "is_fallback": False,
                "quest_id": qid,
                "sub_obj_id": sub_obj_id,
                "stage_index": stage_idx,
                "is_quest_action": True,
                "is_story_quest": is_story,
                "contract_type": trigger,
                "approach": "wait_for_window",
                "gold_cost": 0,
                "wait_minutes": wait_m,
            })
            if is_purely_time_locked_stage(stage_label, quest_title):
                if len(quest_choices) >= 3:
                    break
                continue
            out_of_window_dc_penalty = 3

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
        _main_dc_adj = (
            -int(_wp_cs.get("aid_dc_reduction") or 0) + int(_wp_cs.get("alert_dc_bonus") or 0)
            if (_wp_cs and not _wp_opt_lead)
            else 0
        )
        if char and isinstance(char.get("stats"), dict):
            c_stat = int(char["stats"].get(stat, 5))
            req = max(2, min(8, c_stat - 1))
        if out_of_window_dc_penalty > 0:
            req = min(12, req + out_of_window_dc_penalty)

        if _main_dc_adj != 0:
            req = max(2, min(14, req + _main_dc_adj))
        clean_stage = stage_label[0].upper() + stage_label[1:] if len(stage_label) > 1 else stage_label
        if clean_stage.endswith("."):
            clean_stage = clean_stage[:-1]

        req_item = wp.get("required_item") or wp.get("quest_required_item") or ""

        # Special Case: Anomalous Incursions Out-of-Combat Non-Hostile Entity Containment (all 4 narrative approaches)
        try:
            import scenario_data
            if scenario_data.is_anomalous_incursions_scenario(scen_key):
                from mechanics.world.anomalous_events import (
                    is_non_hostile_entity_containment_waypoint,
                    extract_non_hostile_entity_name,
                    build_non_hostile_narrative_choices,
                )
                if is_non_hostile_entity_containment_waypoint(wp, all_wps=all_wps):
                    ent_nm = extract_non_hostile_entity_name(wp)
                    nh_choices = build_non_hostile_narrative_choices(
                        ent_nm,
                        mode="quest",
                        char=char,
                        quest_id=qid,
                        sub_obj_id=sub_obj_id,
                        stage_index=stage_idx,
                        is_story_quest=is_story,
                        contract_type=trigger,
                        dc_mod=out_of_window_dc_penalty, session_id=session_id,
                    )
                    quest_choices.extend(nh_choices)
                    break
        except Exception:
            pass

        # Special Case: Guaranteed Stage 3 Turn-In after sparing the target
        if res_approach == "spared_deception" and stage_idx >= 3:
            choice_label = f"Present the staged proof of elimination to {target_npc or 'your client'} (Auto-Success)"
            quest_choices.append({
                "label": choice_label,
                "stat": "NONE",
                "requirement": 0,
                "mp_cost": 0,
                "intent": "dialogue_init" if trigger == "talk_to_npc" else "general_action",
                "sub_intent": "",
                "target_npc": target_npc or "",
                "is_fallback": False,
                "quest_id": qid,
                "sub_obj_id": sub_obj_id,
                "stage_index": stage_idx,
                "is_quest_action": True,
                "is_story_quest": is_story,
                "contract_type": trigger,
                "approach": "spared_turn_in",
                "gold_cost": 0,
                "dc_mod": 0,
            })
            if len(quest_choices) >= 3:
                break
            continue

        q_intent = "dialogue_init" if trigger == "talk_to_npc" else "investigate_clue"
        if trigger == "key_clue" and clue_info.get("matching_open_sources"):
            for ksrc in (clue_info.get("matching_open_sources") or []):
                if len(quest_choices) >= 3:
                    break
                k_kind = str(ksrc.get("kind") or "record").lower()
                q_intent = "dialogue_init" if k_kind == "witness" else "investigate_clue"
                k_stat = str(ksrc.get("stat") or ("CHA" if k_kind == "witness" else "PER")).upper()
                k_req = req
                if char and isinstance(char.get("stats"), dict):
                    k_req = max(2, min(8, int(char["stats"].get(k_stat, 5)) - 1))
                if out_of_window_dc_penalty > 0:
                    k_req = min(12, k_req + out_of_window_dc_penalty)
                if _main_dc_adj != 0 or ksrc.get("dc_offset"):
                    k_req = max(2, min(14, k_req + _main_dc_adj + int(ksrc.get("dc_offset") or 0)))
                k_hint = str(ksrc.get("approach_hint") or clean_stage).strip().rstrip(".")
                k_npc = str(ksrc.get("npc_name") or target_npc or "").strip() if k_kind == "witness" else ""
                quest_choices.append({
                    "label": f"{k_hint} ({k_stat})",
                    "stat": k_stat,
                    "requirement": k_req,
                    "mp_cost": 0,
                    "intent": "dialogue_init" if k_kind == "witness" else "investigate_clue",
                    "sub_intent": "",
                    "target_npc": k_npc,
                    "is_fallback": False,
                    "quest_id": qid,
                    "sub_obj_id": sub_obj_id,
                    "stage_index": stage_idx,
                    "is_quest_action": True,
                    "is_story_quest": is_story,
                    "contract_type": "key_clue",
                    "approach": k_kind,
                    "clue_source_id": str(ksrc.get("source_id") or ""),
                    "gold_cost": 0,
                    "dc_mod": out_of_window_dc_penalty + int(ksrc.get("dc_offset") or 0),
                })
        else:
            if req_item and (target_npc or any(k in stage_label.lower() for k in ("deliver", "return", "give", "hand", "turn in"))):
                if req_item.lower() in clean_stage.lower():
                    choice_label = f"{clean_stage} ({stat})"
                else:
                    choice_label = f"Deliver {req_item} to {target_npc or clean_stage} ({stat})"
            elif target_npc and target_npc.lower() not in clean_stage.lower():
                choice_label = f"Speak with {target_npc} about {clean_stage} ({stat})"
            else:
                choice_label = f"{clean_stage} ({stat})"

            q_intent = "dialogue_init" if trigger == "talk_to_npc" else "investigate_clue"
            quest_choices.append({
                "label": choice_label,
                "stat": stat,
                "requirement": req,
                "mp_cost": 0,
                "intent": q_intent,
                "sub_intent": "",
                "target_npc": target_npc or "",
                "is_fallback": False,
                "quest_id": qid,
                "sub_obj_id": sub_obj_id,
                "stage_index": stage_idx,
                "is_quest_action": True,
                "is_story_quest": is_story,
                "contract_type": trigger,
                "approach": "direct",
                "gold_cost": 0,
                "dc_mod": out_of_window_dc_penalty,
            })

        # Phase 4: Caseboard Deduction Breakthrough Shortcut Choice
        if len(quest_choices) < 3 and has_caseboard_breakthrough_for_waypoint(session_id, wp):
            target_disp = target_npc or "the target"
            quest_choices.append({
                "label": f"Confront {target_disp} with verified caseboard deductions (Auto-Success)",
                "stat": "FREE",
                "requirement": 0,
                "mp_cost": 0,
                "intent": "dialogue_init" if trigger == "talk_to_npc" else "investigate_clue",
                "sub_intent": "",
                "target_npc": target_npc or "",
                "is_fallback": False,
                "quest_id": qid,
                "sub_obj_id": sub_obj_id,
                "stage_index": stage_idx,
                "is_quest_action": True,
                "is_story_quest": is_story,
                "contract_type": trigger,
                "approach": "breakthrough_leverage",
                "gold_cost": 0,
                "dc_mod": 0,
            })

        # Phase 4: Active Companion Assist Choice
        if len(quest_choices) < 3:
            active_companion = get_active_companion_for_waypoint(session_id, wp)
            if active_companion:
                from mechanics.narrative.blueprints import evaluate_companion_assist_for_blueprint
                assist_info = evaluate_companion_assist_for_blueprint(active_companion, bp_id)
                comp_name = assist_info["companion_name"]
                if assist_info["is_role_match"]:
                    role_lbl = assist_info["matched_role_label"]
                    comp_lbl = f"Ask {comp_name} to use their {role_lbl} expertise to bypass the challenge (Auto-Success)"
                    c_stat = "FREE"
                    c_req = 0
                    c_dc_mod = 0
                else:
                    comp_lbl = f"Have {comp_name} assist and cover you (-3 DC) ({stat})"
                    c_stat = stat
                    c_req = max(2, req - 3)
                    c_dc_mod = -3

                quest_choices.append({
                    "label": comp_lbl,
                    "stat": c_stat,
                    "requirement": c_req,
                    "mp_cost": 0,
                    "intent": q_intent,
                    "sub_intent": "",
                    "target_npc": target_npc or "",
                    "is_fallback": False,
                    "quest_id": qid,
                    "sub_obj_id": sub_obj_id,
                    "stage_index": stage_idx,
                    "is_quest_action": True,
                    "is_story_quest": is_story,
                    "contract_type": trigger,
                    "approach": "companion_assist",
                    "gold_cost": 0,
                    "dc_mod": c_dc_mod,
                    "companion_name": comp_name,
                })

        # Multi-Approach Contrasting choices on active resolution stages (Stage >= 2 or single-stage action)
        if len(quest_choices) < 3 and (stage_idx >= 2 or total_stages == 1):
            try:
                from mechanics.narrative.blueprints import build_stage_contrasting_approaches
                from mechanics.stealth import is_stealth_context_warranted, is_stealth_choice_locked_out
                sess_wp = db.get_session(session_id) if session_id else {"scenario": scen_key, "current_location": current_location}
                if isinstance(sess_wp, dict) and current_location:
                    sess_wp = dict(sess_wp)
                    sess_wp["current_location"] = current_location
                st_warranted = is_stealth_context_warranted(sess_wp)
                contrasting = build_stage_contrasting_approaches(
                    blueprint_id=bp_id,
                    stage_index=stage_idx,
                    total_stages=total_stages,
                    stage_label=stage_label,
                    target_npc=target_npc,
                    required_item=req_item,
                    reward_gold=reward_gold,
                    player_gold=player_gold,
                    is_story_quest=is_story,
                    stealth_warranted=st_warranted,
                )
                for ca in contrasting:
                    if len(quest_choices) >= 3:
                        break
                    ca_lbl = str(ca['label']).strip()
                    if ca.get("approach") == "stealth_guile" and is_stealth_choice_locked_out(sess_wp, label=ca_lbl):
                        continue
                    ca_stat = ca.get("stat", "AGI")
                    ca_req = 0
                    if ca_stat not in ("NONE", "FREE", None, ""):
                        ca_req = req if ca_stat == stat else max(2, min(8, int((char or {}).get("stats", {}).get(ca_stat, 5)) - 1))
                        if out_of_window_dc_penalty > 0:
                            ca_req = min(12, ca_req + out_of_window_dc_penalty)
                    quest_choices.append({
                        "label": ca_lbl,
                        "stat": ca_stat,
                        "requirement": ca_req,
                        "mp_cost": 0,
                        "intent": ca.get("intent", "general_action"),
                        "sub_intent": "",
                        "target_npc": target_npc or "",
                        "is_fallback": False,
                        "quest_id": qid,
                        "sub_obj_id": sub_obj_id,
                        "stage_index": stage_idx,
                        "is_quest_action": True,
                        "is_story_quest": is_story,
                        "contract_type": trigger,
                        "approach": ca.get("approach", "direct"),
                        "gold_cost": int(ca.get("gold_cost") or 0),
                        "dc_mod": out_of_window_dc_penalty,
                    })
            except Exception:
                pass

        if len(quest_choices) >= 3:
            break

    for qc in quest_choices:
        if isinstance(qc, dict) and qc.get("is_quest_action"):
            qc["_python_verified_quest"] = True
            qc["_server_stamped"] = True
            if int(qc.get("gold_cost") or 0) > 0 and not qc.get("gold_spent"):
                qc["gold_spent"] = int(qc["gold_cost"])
            if qc.get("approach") == "breakthrough_leverage":
                qc["breakthrough_leveraged"] = True
            if int(qc.get("wait_minutes") or 0) > 0 and not qc.get("skip_minutes"):
                qc["skip_minutes"] = int(qc["wait_minutes"])

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


def _strip_unverified_quest_flags(raw_choices: list) -> list:
    """Strips unverified quest tags, badges, and prefixes from choices when no quest matches the current location."""
    cleaned = []
    for c in raw_choices:
        if not isinstance(c, dict):
            cleaned.append(c)
            continue
        c_copy = dict(c)
        c_copy["is_quest_action"] = False
        c_copy["is_story_quest"] = False
        c_copy["is_climax_action"] = False
        c_copy["_python_verified_quest"] = False
        c_copy["quest_id"] = ""
        c_copy["sub_obj_id"] = None
        c_copy["stage_index"] = None
        c_copy["contract_type"] = ""
        lbl = str(c_copy.get("label", ""))
        lbl_clean = re.sub(r"^[⭐🎯⚡🔹\s\[\]]+(?:bounty|story quest|story climax|quest)?\]?\s*", "", lbl, flags=re.IGNORECASE).strip()
        if lbl_clean:
            c_copy["label"] = lbl_clean
        cleaned.append(c_copy)
    return cleaned


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

    from mechanics.social.intimate_excitement import is_intimate_action_label
    intimate_excl_words = (
        "climax", "orgasm", "rhythm", "thrust", "tongue", "fingers",
        "aftercare", "aftershocks", "tremors", "arousal", "pleasure", "lick",
        "fuck", "fucking", "fucked", "pussy", "cock", "clit", "straddle",
    )

    session_row = db.get_session(session_id) if session_id else None

    if session_id:
        try:
            from mechanics.social.physical_state import (
                is_erotic_intimate_contact,
                check_venue_indecency_exposure,
                find_player_actor_key,
                is_actor_restrained,
            )
            phys_st = db.get_session_physical_state(session_id)
            if phys_st:
                ic_str = str(phys_st.get("intimate_contact", "") or "")
                actors_map = phys_st.get("actors") or {}
                p_key = find_player_actor_key(actors_map, party=[char] if char else None, session_id=session_id)
                player_actor = actors_map.get(p_key) if p_key else (actors_map.get("player") or actors_map.get("Player") or {})
                player_cloth = player_actor.get("clothing") or {}

                # Invariant 12: Restraint check & Travel inhibition
                if is_actor_restrained(player_actor):
                    from mechanics.world.locations.movement import is_movement_action
                    choices = [c for c in choices if not (isinstance(c, dict) and is_movement_action(c.get("label") or c.get("action") or ""))]
                    break_free_choice = {
                        "label": "⛓️ [Struggle] Attempt to slip out or break your restraints",
                        "action": "struggle to break free",
                        "intent": "break_free",
                        "is_emergency": True,
                        "is_quest_action": False,
                        "is_story_quest": False,
                    }
                    if not any("break" in str(c.get("label", "")).lower() or "struggle" in str(c.get("label", "")).lower() for c in choices if isinstance(c, dict)):
                        choices.insert(0, break_free_choice)

                    has_companions = bool(
                        current_npcs
                        or (session_row and (session_row.get("party_npcs") or session_row.get("party_npcs_json") or session_row.get("temporary_companions")))
                    )
                    if has_companions:
                        companion_cut_choice = {
                            "label": "🗣️ [Ask for Help] Signal your companion to cut and untie your bonds",
                            "action": "ask companion to cut bonds",
                            "intent": "companion_free",
                            "is_emergency": True,
                            "is_quest_action": False,
                            "is_story_quest": False,
                        }
                        if not any("companion" in str(c.get("label", "")).lower() and "cut" in str(c.get("label", "")).lower() for c in choices if isinstance(c, dict)):
                            choices.insert(1, companion_cut_choice)

                # Invariant 4: Check public venue indecency exposure
                p_gender = str(char.get("gender") or "female") if char else "female"
                exposure = check_venue_indecency_exposure(player_cloth, current_location, gender=p_gender)
                if exposure.get("requires_reaction"):
                    cover_choice = {
                        "label": "🛡️ [Cover Up] Quickly pull your garments together to hide your exposure",
                        "action": "cover_up",
                        "intent": "cover_up",
                        "is_emergency": True,
                        "is_quest_action": False,
                        "is_story_quest": False,
                    }
                    if not any("cover up" in str(c.get("label", "")).lower() for c in choices if isinstance(c, dict)):
                        choices.insert(0, cover_choice)

                # Invariant 2: Contextual Aftercare & Redressing
                is_aftercare = "aftercare" in ic_str.lower()
                is_erotic = is_erotic_intimate_contact(ic_str)
                if is_aftercare or is_erotic:
                    is_disheveled_or_stripped = any(
                        any(w in str(v).lower() for w in ("removed", "none", "disheveled", "displaced"))
                        for v in player_cloth.values()
                    )
                    if is_disheveled_or_stripped:
                        get_dressed_choice = {
                            "label": "👔 [Get Dressed] Gather your clothes and redress yourself",
                            "action": "get dressed",
                            "intent": "redress",
                            "is_emergency": False,
                            "is_quest_action": False,
                            "is_story_quest": False,
                        }
                        if not any("get dressed" in str(c.get("label", "")).lower() or "redress" in str(c.get("label", "")).lower() for c in choices if isinstance(c, dict)):
                            choices.append(get_dressed_choice)

                    for c in choices:
                        if isinstance(c, dict):
                            c["is_quest_action"] = False
                            c["is_story_quest"] = False
                            c["is_climax_action"] = False
                            c["quest_id"] = ""
                            c["sub_obj_id"] = None
                            c["stage_index"] = None
                            c["contract_type"] = ""
                    return choices
        except Exception:
            pass

    active_wps = db.get_all_session_active_waypoints(session_id)
    story_quest, climax_loc = get_story_quest_climax_location(session_id)
    climax_ready_at_loc = bool(story_quest and climax_loc and check_location_matches_waypoint(current_location, climax_loc, session_id=session_id))

    # Detect if characters are in active 1-on-1 or group dialogue
    from mechanics.world.mobility import get_session_dialogue_partners
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

    # Check if there are active rendezvous commitments at this location
    appts_at_loc = []
    try:
        from mechanics.system.commitments_engine import get_active_commitments
        appts = get_active_commitments(session_id, commitment_type="rendezvous", limit=20)
        for appt in appts:
            appt_loc = appt.get("target_location") or appt.get("rendezvous_location") or ""
            if appt_loc and check_location_matches_waypoint(current_location, appt_loc, session_id=session_id):
                appts_at_loc.append(appt)
    except Exception:
        pass

    if not active_wps and not climax_ready_at_loc and not appts_at_loc:
        return _strip_unverified_quest_flags(choices)

    # Find active waypoints matching current location or NPC presence
    from .matching import (
        resolve_effective_waypoint_location,
        is_waypoint_npc_present_in_scene,
        resolve_waypoint_target_npc,
        can_waypoint_match_via_npc_presence,
        get_matching_clue_sources_for_location,
    )
    matching_wps = []
    _dossier_cache: dict[str, Any] = {}
    _sess_time = db.get_session_time(session_id) if session_id else None
    for wp in active_wps:
        eff_loc = resolve_effective_waypoint_location(session_id, wp, session=session_row, session_time=_sess_time) if session_id else wp.get("target_location", "")
        t_npc = resolve_waypoint_target_npc(session_id, wp) or wp.get("target_npc", "")
        can_npc_match = can_waypoint_match_via_npc_presence(t_npc, wp.get("stage_key", ""), current_location, wp)
        wp_qid = str(wp.get("quest_id") or "")
        if wp_qid and wp_qid not in _dossier_cache:
            _dossier_cache[wp_qid] = db.get_quest_dossier(session_id, wp_qid) if session_id else None
        clue_m = get_matching_clue_sources_for_location(
            session_id,
            wp_qid,
            wp.get("sub_obj_id"),
            current_location,
            waypoint=wp,
            include_bonus=True,
            dossier=_dossier_cache.get(wp_qid),
        )
        if clue_m.get("is_clue_stage") or str(wp.get("completion_trigger") or "") == "key_clue":
            wp_matches_loc = bool(clue_m.get("matching_open_sources") or clue_m.get("matching_bonus_sources"))
        else:
            wp_matches_loc = bool(
                (eff_loc and check_location_matches_waypoint(current_location, eff_loc, session_id=session_id))
                or (bool(t_npc) and can_npc_match and is_waypoint_npc_present_in_scene(session_id, t_npc))
            )
        if wp_matches_loc:
            wp_tag_copy = dict(wp)
            wp_tag_copy["_clue_match_info"] = clue_m
            matching_wps.append(wp_tag_copy)

    if not matching_wps and not climax_ready_at_loc and not appts_at_loc:
        return _strip_unverified_quest_flags(choices)

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
        c_copy = dict(c)
        if is_intimate_action_label(c_label_clean) or any(iw in c_label_clean for iw in intimate_excl_words):
            c_copy["is_quest_action"] = False
            c_copy["is_story_quest"] = False
            c_copy["is_climax_action"] = False
            c_copy["quest_id"] = ""
            c_copy["sub_obj_id"] = None
            c_copy["stage_index"] = None
            c_copy["contract_type"] = ""
        result_choices.append(c_copy)

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
                "propose", "reorganization", "mandate", "showdown", "truth",
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
                if is_intimate_action_label(lbl) or any(iw in lbl for iw in intimate_excl_words):
                    continue
                # Don't tag purely passive exits as the climax
                from mechanics.narrative.intent import is_conversational_exit
                if c.get("stat") == "NONE" and c.get("requirement", 0) == 0 and (is_conversational_exit(lbl) or "look around" in lbl):
                    continue
                score = sum(1 for kw in climax_keywords if kw in lbl)
                if score > 0 and c.get("stat") not in ("NONE", None) and c.get("requirement", 0) > 0:
                    score += 1
                if score > best_climax_score:
                    best_climax_score = score
                    best_climax_choice = c

            if best_climax_choice and best_climax_score >= 1:
                best_climax_choice["is_quest_action"] = True
                best_climax_choice["is_climax_action"] = True
                best_climax_choice["is_story_quest"] = True
                best_climax_choice["_python_verified_quest"] = True
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

                raw_label = str(best_climax_choice.get("label", ""))
                clean_lbl = re.sub(
                    r"^(?:[⭐🎯⚡💌🔹🌙⏳🤝\s]+|\s*\[(?:Main|Side|Optional[^\]\r\n]*|Story Quest(?:\s*\|[^\]\r\n]+)?|Bounty(?:\s*\|[^\]\r\n]+)?|Story Climax(?:\s*-\s*Premature Showdown)?|Quest|[^\]]+)\]\s*)+",
                    "",
                    raw_label,
                    flags=re.IGNORECASE,
                ).strip()
                if clean_lbl:
                    best_climax_choice["label"] = clean_lbl
            else:
                if not in_active_dialogue and allow_fallback:
                    fallback_choices = generate_quest_action_choices(session_id, current_location, scen_key=scen_key, char=char)
                    if fallback_choices:
                        result_choices.insert(0, fallback_choices[0])

        for c in result_choices:
            if c.get("is_climax_action") or str(c.get("contract_type", "")).lower() == "climax":
                c["is_story_quest"] = True
                c["is_quest_action"] = True
                c["_python_verified_quest"] = True
                c["_server_stamped"] = True
                raw_label = str(c.get("label", ""))
                clean_lbl = re.sub(
                    r"^(?:[⭐🎯⚡💌🔹🌙⏳🤝\s]+|\s*\[(?:Main|Side|Optional[^\]\r\n]*|Story Quest(?:\s*\|[^\]\r\n]+)?|Bounty(?:\s*\|[^\]\r\n]+)?|Story Climax(?:\s*-\s*Premature Showdown)?|Quest|[^\]]+)\]\s*)+",
                    "",
                    raw_label,
                    flags=re.IGNORECASE,
                ).strip()
                if clean_lbl:
                    c["label"] = clean_lbl

    scene_npcs = current_npcs if current_npcs is not None else (session_row.get("current_npcs", []) if session_row else [])
    present_names = {str((n.get("name") or n.get("npc_name")) if isinstance(n, dict) else n).strip().lower() for n in (scene_npcs or []) if n}

    # For each matching waypoint, find the best matching choice
    for wp in matching_wps:
        qid = wp.get("quest_id", "")
        sub_obj_id = wp.get("sub_obj_id")
        stage_idx = wp.get("stage_index", 1)
        trigger = wp.get("completion_trigger", "skill_check")
        stage_label = str(wp.get("stage_label", "")).strip()
        target_npc = str(resolve_waypoint_target_npc(session_id, wp) or wp.get("target_npc", "")).strip().lower()
        is_story = bool(wp.get("is_story_quest") or "SQ-" in str(qid) or "story" in str(qid).lower())
        prefix = "Story Quest" if is_story else "Bounty"
        icon = "⭐" if is_story else "🎯"

        from mechanics.narrative.blueprints import classify_choice_approach, calculate_quest_buyout_cost

        # Collect already tagged approaches for this quest
        tagged_approaches = set()
        for c in result_choices:
            if c.get("is_quest_action") and c.get("quest_id") == qid and c.get("_python_verified_quest"):
                c["is_story_quest"] = is_story
                raw_label = str(c.get("label", ""))
                clean_lbl = re.sub(
                    r"^(?:[⭐🎯⚡💌🔹🌙⏳🤝\s]+|\s*\[(?:Main|Side|Optional[^\]\r\n]*|Story Quest(?:\s*\|[^\]\r\n]+)?|Bounty(?:\s*\|[^\]\r\n]+)?|Story Climax(?:\s*-\s*Premature Showdown)?|Quest)\]\s*)+",
                    "",
                    raw_label,
                    flags=re.IGNORECASE,
                ).strip()
                if clean_lbl:
                    c["label"] = clean_lbl
                app = c.get("approach") or classify_choice_approach(raw_label)
                c["approach"] = app
                tagged_approaches.add(app)

        if len(tagged_approaches) >= 3:
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

        if target_npc:
            is_npc_present = any(
                target_npc in pn or any(tok in pn for tok in npc_tokens)
                for pn in present_names
            ) if present_names else False
        else:
            is_npc_present = True

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

        b_contract = wp.get("beat_contract") or {}
        if not b_contract and session_id and qid:
            try:
                _dos_tmp = db.get_quest_dossier(session_id, qid)
                if _dos_tmp:
                    for _ms in ((_dos_tmp.get("climax_spec") or {}).get("main_stages") or []):
                        if int(_ms.get("stage_index") or 0) == stage_idx and _ms.get("beat_contract"):
                            b_contract = _ms["beat_contract"]
                            break
            except Exception:
                pass

        if b_contract:
            c_text = f"{b_contract.get('player_verb', '')} {b_contract.get('reveal', '')} {b_contract.get('handover', '')}".lower()
            stage_words.update(w for w in re.findall(r"\w{4,}", c_text) if w not in ignore_words)

        clue_m = wp.get("_clue_match_info") or {}
        for msrc in (clue_m.get("matching_open_sources") or []) + (clue_m.get("matching_bonus_sources") or []):
            m_txt = f"{msrc.get('approach_hint', '')} {msrc.get('npc_name', '')}".lower()
            stage_words.update(w for w in re.findall(r"\w{4,}", m_txt) if w not in ignore_words)
            for tok in str(msrc.get("npc_name") or "").lower().split():
                if len(tok) >= 3:
                    npc_tokens.add(tok)

        stage_stems = _extract_word_stems(stage_words)
        sub_stems = _extract_word_stems(sub_words | title_words)

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

        # Score candidate choices and tag up to 3 distinct approaches
        candidate_matches = []
        for c in result_choices:
            if c.get("is_quest_action"):
                continue
            lbl = str(c.get("label", "")).lower()
            if is_intimate_action_label(lbl) or any(iw in lbl for iw in intimate_excl_words):
                continue
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

            if in_active_dialogue and is_dp_match and not has_substantive_match:
                if any(w in lbl for w in ("ask", "question", "inquire", "confront", "press", "discuss", "demand", "show", "bribe", "negotiate", "tell", "explain", "clue", "ledger", "mission")):
                    substantive_matches += 1
                    has_substantive_match = True
                    score += 2.0

            if in_active_dialogue and not has_substantive_match:
                continue

            if not is_dp_match or not is_npc_present:
                addresses_unrelated_npc = any(f" {ut}" in f" {lbl}" for ut in unrelated_npc_tokens)
                if addresses_unrelated_npc or (substantive_matches < 2 and not has_stage_match):
                    continue

            if has_substantive_match and c.get("stat") not in ("NONE", "FREE", None) and (c.get("requirement") or 0) > 0:
                score += 0.5

            app_type = classify_choice_approach(lbl)
            if app_type != "direct":
                score += 1.0

            if score >= 1.0:
                candidate_matches.append((score, app_type, c))

        # Sort candidate matches by score DESC
        candidate_matches.sort(key=lambda x: x[0], reverse=True)
        for cand_score, cand_app, cand_choice in candidate_matches:
            if len(tagged_approaches) >= 3:
                break
            if cand_app in tagged_approaches:
                continue

            # Tag this distinct approach choice
            cand_choice["is_quest_action"] = True
            cand_choice["is_story_quest"] = is_story
            cand_choice["_python_verified_quest"] = True
            cand_choice["_server_stamped"] = True
            cand_choice["quest_id"] = qid
            cand_choice["sub_obj_id"] = sub_obj_id
            cand_choice["stage_index"] = stage_idx
            cand_choice["contract_type"] = trigger
            cand_choice["approach"] = cand_app
            if cand_app == "breakthrough_leverage":
                cand_choice["breakthrough_leveraged"] = True

            raw_label = str(cand_choice.get("label", ""))
            clean_lbl = re.sub(
                r"^(?:[⭐🎯⚡💌🔹🌙⏳🤝\s]+|\s*\[(?:Main|Side|Optional[^\]\r\n]*|Story Quest(?:\s*\|[^\]\r\n]+)?|Bounty(?:\s*\|[^\]\r\n]+)?|Story Climax(?:\s*-\s*Premature Showdown)?|Quest|Breakthrough Leverage|Companion Assist:[^\]\r\n]*|Turn-In[^\]\r\n]*)\]\s*)+",
                "",
                raw_label,
                flags=re.IGNORECASE,
            ).strip()
            if clean_lbl:
                cand_choice["label"] = clean_lbl

            lbl_low = str(cand_choice.get("label", "")).lower()
            if cand_app in ("counter_offer", "buyout_bribe", "wait_for_window", "wait_until_morning", "breakthrough_leverage") or (cand_app == "companion_assist" and cand_choice.get("stat") == "FREE"):
                cand_choice["stat"] = "FREE"
                cand_choice["requirement"] = 0
                if cand_app == "buyout_bribe" and not cand_choice.get("gold_cost"):
                    cand_choice["gold_cost"] = calculate_quest_buyout_cost(wp)
                if cand_app == "buyout_bribe" and int(cand_choice.get("gold_cost") or 0) > 0:
                    cand_choice["gold_spent"] = int(cand_choice["gold_cost"])
            elif cand_app == "companion_assist":
                cand_choice["requirement"] = max(2, int(cand_choice.get("requirement") or 6) - 3)
                cand_choice["dc_mod"] = -3
            else:
                from mechanics.narrative.intent import classify_action_intent, IntentCategory
                is_travel_quest = classify_action_intent(lbl_low).category == IntentCategory.MOVEMENT
                if not is_travel_quest:
                    if cand_choice.get("stat") in ("NONE", "FREE", None, "") or cand_choice.get("requirement", 0) <= 0:
                        stat_val = "CHA" if any(w in lbl_low for w in ("talk", "speak", "convince", "persuade", "question", "ask", "confront", "interrogate", "spare")) else ("INT" if any(w in lbl_low for w in ("search", "investigate", "examine", "analyze", "read", "hack", "evidence", "clue", "study", "forge")) else "PER")
                        cand_choice["stat"] = stat_val
                        req_val = 6
                        if char and isinstance(char.get("stats"), dict):
                            req_val = max(5, min(8, int(char["stats"].get(stat_val, 6))))
                        cand_choice["requirement"] = req_val

            tagged_approaches.add(cand_app)

        # Anomalous Incursions Non-Hostile Containment: ensure all 4 narrative approaches are offered in open exploration
        if not in_active_dialogue and allow_fallback:
            try:
                import scenario_data
                if scenario_data.is_anomalous_incursions_scenario(scen_key):
                    from mechanics.world.anomalous_events import (
                        is_non_hostile_entity_containment_waypoint,
                        extract_non_hostile_entity_name,
                        build_non_hostile_narrative_choices,
                    )
                    wp_all = db.get_quest_waypoints(session_id, qid, sub_obj_id) or []
                    if is_non_hostile_entity_containment_waypoint(wp, all_wps=wp_all):
                        ent_nm = extract_non_hostile_entity_name(wp)
                        nh_choices = build_non_hostile_narrative_choices(
                            ent_nm,
                            mode="quest",
                            char=char,
                            quest_id=qid,
                            sub_obj_id=sub_obj_id,
                            stage_index=stage_idx,
                            is_story_quest=is_story,
                            contract_type=trigger, session_id=session_id,
                        )
                        inserted_idx = 0
                        for nh_c in nh_choices:
                            nh_c["_python_verified_quest"] = True
                            nh_app = nh_c.get("approach", "")
                            if nh_app and nh_app not in tagged_approaches:
                                result_choices.insert(inserted_idx, nh_c)
                                inserted_idx += 1
                                tagged_approaches.add(nh_app)
                        continue
            except Exception:
                pass

        # Fallback handling
        if len(tagged_approaches) == 0 and is_dp_match and is_npc_present:
            if not in_active_dialogue and allow_fallback:
                fallback_choices = generate_quest_action_choices(session_id, current_location, scen_key=scen_key, char=char)
                if fallback_choices:
                    for fb in fallback_choices[:2]:
                        fb["_python_verified_quest"] = True
                        result_choices.insert(0, fb)
                        tagged_approaches.add(fb.get("approach", "direct"))
            elif in_active_dialogue and target_npc and allow_fallback:
                is_physical = bool(trigger in ("inspect_prop", "defeat_target", "combat_victory") or any(kw in stage_label.lower() for kw in ("inspect physical", "traces", "search site", "breach the outer")))
                if not is_physical:
                    tgt_disp = target_npc.title()
                    verb = (b_contract.get("player_verb") or "").strip()
                    if verb:
                        c_lbl = verb
                    else:
                        clean_stg = re.sub(r"^(?:[⭐🎯⚡💌🔹🌙⏳🤝\s]+|\s*\[[^\]]+\]\s*)+", "", stage_label).strip() or stage_label
                        c_lbl = f"Speak with {tgt_disp} — {clean_stg}" if tgt_disp.lower() not in clean_stg.lower() else clean_stg
                    if not any(c_lbl.lower() in str(rc.get("label", "")).lower() for rc in result_choices if isinstance(rc, dict)):
                        in_dialogue_bounty_choice = {
                            "label": c_lbl[:190],
                            "stat": "CHA",
                            "requirement": 6,
                            "mp_cost": 0,
                            "is_quest_action": True,
                            "is_story_quest": is_story,
                            "_python_verified_quest": True,
                            "_server_stamped": True,
                            "quest_id": qid,
                            "sub_obj_id": sub_obj_id,
                            "stage_index": stage_idx,
                            "contract_type": trigger,
                            "approach": "direct",
                        }
                        result_choices.insert(0, in_dialogue_bounty_choice)
                        tagged_approaches.add("direct")

        # Guarantee at least 2 contrasting approaches at Stage >= 2 if in open exploration and choice budget permits
        elif stage_idx >= 2 and len(tagged_approaches) < 2 and not in_active_dialogue and allow_fallback and len(result_choices) < 5:
            fallback_choices = generate_quest_action_choices(session_id, current_location, scen_key=scen_key, char=char)
            for fb in fallback_choices:
                fb["_python_verified_quest"] = True
                fb_app = fb.get("approach", "direct")
                if fb_app not in tagged_approaches and len(result_choices) < 5:
                    result_choices.append(fb)
                    tagged_approaches.add(fb_app)
                    break

    # Rendezvous meetup choices: guarantee interaction/wait option ONLY when in open exploration (not in dialogue)
    try:
        dp_list = [p.lower() for p in active_dps]

        from mechanics.system.commitments_engine import get_active_commitments, _compute_abs_window, _canon_key
        active_commitments = get_active_commitments(session_id, commitment_type="rendezvous", limit=20)
        pending_appts = [c for c in active_commitments if c.get("status") in ("pending", "approaching")]
        arrived_appts = [c for c in active_commitments if c.get("status") in ("arrived", "in_progress")]

        # Build contact name lookup for resolving friendly display names
        known_contacts_map = {}
        if hasattr(db, "get_contacts") and session_id:
            try:
                for c in (db.get_contacts(session_id) or []):
                    c_nm = str(c.get("name") or "").strip()
                    if not c_nm:
                        continue
                    for ck in (c.get("npc_id"), c_nm, _canon_key(c_nm)):
                        if ck:
                            known_contacts_map[str(ck).strip().lower()] = c_nm
            except Exception:
                pass

        curr_day, curr_min, _ = db.get_session_time(session_id) if hasattr(db, "get_session_time") else (1, 480, "")
        abs_now = (max(1, int(curr_day)) - 1) * 1440 + max(0, int(curr_min))
        scene_npc_names = {
            str((x.get("name") or x.get("npc_name")) if isinstance(x, dict) else x).strip().lower()
            for x in (current_npcs or [])
            if x
        }

        for appt in (pending_appts + arrived_appts):
            appt_loc = appt.get("target_location") or appt.get("rendezvous_location") or ""
            npc_name = appt.get("npc_name") or ""
            if (not npc_name or "_" in npc_name) and appt.get("participants"):
                for p in appt["participants"]:
                    p_key = str(p.get("person_key") or p.get("npc_id") or "").strip().lower()
                    if p.get("role") == "organizer" and p_key == "player":
                        continue
                    if p_key == "player":
                        continue
                    p_name = known_contacts_map.get(p_key) or p.get("name")
                    if p_name:
                        npc_name = p_name
                        break
            if not npc_name and appt.get("target_entity"):
                t_ent = str(appt["target_entity"]).strip().lower()
                npc_name = known_contacts_map.get(t_ent) or known_contacts_map.get(_canon_key(t_ent)) or t_ent.replace("_", " ").title()
            elif "_" in npc_name:
                npc_name = known_contacts_map.get(npc_name.strip().lower()) or npc_name.replace("_", " ").title()

            if not (appt_loc and npc_name and check_location_matches_waypoint(current_location, appt_loc, session_id=session_id)):
                continue

            s_day = max(1, int(appt.get("scheduled_day") or 1))
            start_min = int(appt.get("start_minute") or 0)
            abs_start, abs_end = _compute_abs_window(appt)
            appt_status = appt.get("status")

            is_same_day_early = (s_day == int(curr_day) and start_min > 0 and int(curr_min) < start_min and appt_status in ("pending", "approaching"))
            is_within_window = ((abs_start - 15) <= abs_now <= abs_end) or appt_status in ("arrived", "in_progress")

            if not is_same_day_early and not is_within_window:
                continue

            npc_low = npc_name.lower().strip()
            if appt_status in ("arrived", "in_progress") and scene_npc_names and npc_low not in scene_npc_names and not any(dp == npc_low for dp in dp_list):
                if not ((abs_start - 15) <= abs_now <= abs_end):
                    continue

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
                # Invariant 12: Contextual Early Arrival Wait Action
                if is_same_day_early and npc_low not in scene_npc_names:
                    disp_h = ((start_min // 60) % 24)
                    ampm = "AM" if disp_h < 12 else "PM"
                    clock_h = disp_h % 12 or 12
                    time_str = f"{clock_h}:{start_min % 60:02d} {ampm}"
                    result_choices.insert(0, {
                        "label": f"⏳ [Wait] Wait for {npc_name} until {time_str}",
                        "stat": "NONE",
                        "requirement": 0,
                        "is_quest_action": False
                    })
                else:
                    result_choices.insert(0, {
                        "label": f"💌 [Meetup] Greet and talk with {npc_name}",
                        "stat": "NONE",
                        "requirement": 0,
                        "is_quest_action": False
                    })
    except Exception:
        pass

    # Strict Final Location Lock Guard:
    # Any choice not verified against an active local waypoint at this location
    # MUST have is_quest_action set to False and all hallucinated quest badges removed.
    for c in result_choices:
        if isinstance(c, dict):
            if not c.get("_python_verified_quest"):
                c["is_quest_action"] = False
                c["is_story_quest"] = False
                c["is_climax_action"] = False
                c["quest_id"] = ""
                c["sub_obj_id"] = None
                c["stage_index"] = None
                c["contract_type"] = ""
                raw_lbl = str(c.get("label", ""))
                if any(k in raw_lbl.lower() for k in ("[bounty]", "[story quest]", "[story climax]", "[quest]", "🎯", "⭐", "⚡")):
                    clean_lbl = re.sub(r"^[⭐🎯⚡🔹\s\[\]]+(?:bounty|story quest|story climax|quest)?\]?\s*", "", raw_lbl, flags=re.IGNORECASE).strip()
                    if clean_lbl:
                        c["label"] = clean_lbl

    try:
        from game_engine.choices_cleaner import deduplicate_redundant_choices
        result_choices = deduplicate_redundant_choices(result_choices)
    except Exception:
        pass

    return result_choices


# ---------------------------------------------------------------- LLM System Prompt Block
