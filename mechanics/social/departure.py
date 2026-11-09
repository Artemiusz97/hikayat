from __future__ import annotations

"""2-Stage Urgent Schedule Departure State Machine & Relocation Helpers."""

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

import db

log = logging.getLogger(__name__)

_CONVINCE_STAY_RE = re.compile(
    r"\b(?:convince|persuade|beg|urge|coax|plead\s+with|ask)\b.*?\b(?:to\s+)?stay\b"
    r"(?:.*?\b(?:longer|here|little|bit|while|minutes|more)\b)?",
    re.IGNORECASE,
)


def _canon_npc_key(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip().lower())


def _locations_match(
    loc_a: str,
    loc_b: str,
    session_id: Optional[int] = None,
    node_a: str = "",
    node_b: str = "",
) -> bool:
    if node_a and node_b and str(node_a).strip() == str(node_b).strip():
        return True
    if session_id and node_a and node_b:
        try:
            if db.is_descendant_of(session_id, node_a, node_b) or db.is_descendant_of(session_id, node_b, node_a):
                return True
        except Exception:
            pass
    a = str(loc_a or "").strip().lower()
    b = str(loc_b or "").strip().lower()
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    a_parts = [p.strip() for p in a.split("➔") if p.strip()]
    b_parts = [p.strip() for p in b.split("➔") if p.strip()]
    if a_parts and b_parts:
        a_leaf, b_leaf = a_parts[-1], b_parts[-1]
        if a_leaf == b_leaf or (len(a_leaf) >= 5 and (a_leaf in b_leaf or b_leaf in a_leaf)):
            return True
        if len(a_parts) >= 2 and len(b_parts) >= 2 and a_parts[1] == b_parts[1]:
            return True
    return False


def get_npc_departure_states(session: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Returns normalized per-NPC urgent departure state map from session."""
    if not isinstance(session, dict):
        return {}
    raw = session.get("npc_departure_states")
    if not isinstance(raw, dict):
        extra = session.get("extra")
        if isinstance(extra, dict) and isinstance(extra.get("npc_departure_states"), dict):
            raw = extra["npc_departure_states"]
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            out[_canon_npc_key(k)] = dict(v)
    return out


def save_npc_departure_states(
    session: Optional[Dict[str, Any]],
    states: Dict[str, Dict[str, Any]],
    persist_db: bool = True,
) -> None:
    """Synchronizes npc_departure_states onto session and persists to SQLite extra_json."""
    clean_states = {_canon_npc_key(k): dict(v) for k, v in (states or {}).items() if k and isinstance(v, dict)}
    if isinstance(session, dict):
        session["npc_departure_states"] = clean_states
        if isinstance(session.get("extra"), dict):
            session["extra"]["npc_departure_states"] = clean_states
        sess_id = session.get("id")
        if persist_db and sess_id:
            try:
                db.update_session(int(sess_id), extra={"npc_departure_states": clean_states})
            except Exception as e:
                log.warning("Failed persisting npc_departure_states: %s", e)


def is_convince_stay_action(action_or_label: Any) -> bool:
    if isinstance(action_or_label, dict):
        if action_or_label.get("_convince_stay") or action_or_label.get("departure_action") == "convince_stay":
            return True
        lbl = str(action_or_label.get("label") or action_or_label.get("text") or action_or_label.get("action") or "")
    else:
        lbl = str(action_or_label or "")
    return bool(_CONVINCE_STAY_RE.search(lbl))


def _apply_stage1_hurry_gate(c: Dict[str, Any]) -> Dict[str, Any]:
    """Applies the Stage 1 urgent-departure hurry difficulty gate (+3 DC, or FREE -> CHA DC 9)."""
    out = dict(c)
    stat = str(out.get("stat") or "NONE").upper()
    req = int(out.get("requirement") or 0)
    if stat in ("NONE", "FREE", "") or req <= 0:
        out["stat"] = "CHA"
        out["requirement"] = 9
        out.pop("_free_social", None)
    elif stat != "ITEM":
        out["requirement"] = min(15, max(9, req + 3))
    out["_hurry_gated"] = True
    return out


def run_departure_turn_evaluation(
    session: Dict[str, Any],
    actions: Optional[List[Any]],
    new_partners: List[str],
    has_exited_convo: bool,
    *,
    profile_resolver: Callable[..., Dict[str, Any]],
    party: Optional[List[Any]] = None,
    stage_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluates Urgent Schedule Departure transitions & Private Meetup exit rules pre-LLM."""
    from game_engine.npcs.dialogue_tracking import compute_scene_beat_linger_turns
    from mechanics.world.mobility import get_session_dialogue_partners
    from mechanics.world.schedules import (
        detect_schedule_boundary_crossed,
        get_npc_scheduled_location,
        get_npc_scheduled_node_id,
        get_time_block_key,
        is_schedule_transition_imminent,
    )
    from skill_check import is_check_success

    sess_id = session.get("id")
    scen_key = str(session.get("scenario") or "fantasy")
    scene_loc = str((stage_info or {}).get("effective_location") or session.get("current_location") or "")
    scene_nid = str((stage_info or {}).get("effective_node_id") or session.get("current_node_id") or "")
    curr_min = int(session.get("current_minute") if session.get("current_minute") is not None else 480)
    curr_day = int(session.get("current_day") or 1)
    prev_min = session.get("_prev_turn_minute")
    prev_day = session.get("_prev_turn_day")
    curr_blk = get_time_block_key(curr_min)
    history = session.get("history") or []

    prev_partners = list(get_session_dialogue_partners(session))
    states = get_npc_departure_states(session)
    directives: List[str] = []
    departing_records: List[Dict[str, str]] = []
    updated_partners = [str(p).strip() for p in (new_partners or []) if str(p).strip()]

    norm_actions = [a for a in (actions or []) if isinstance(a, dict)]
    lead_act = norm_actions[0] if norm_actions else {}
    act_succeeded = is_check_success(lead_act.get("check"), default_if_none=bool(lead_act.get("success", True)))
    is_custom_act = bool(lead_act.get("type") == "custom" or lead_act.get("_stage2_custom_auto_fail"))
    is_convince_act = is_convince_stay_action(lead_act)
    is_let_depart_act = bool(
        lead_act.get("departure_action") == "let_npc_depart"
        or (lead_act.get("dismisses_npc") and "head out" in str(lead_act.get("label") or "").lower())
    )

    def _resolve_npc_dest(npc_nm: str, prof: Dict[str, Any]) -> Tuple[str, str]:
        if prof.get("has_other_commitment_loc"):
            return str(prof["has_other_commitment_loc"]), ""
        npc_ref = prof.get("contact") or prof.get("scene_npc") or {"name": npc_nm, "role": prof.get("role", "")}
        is_imm, _, next_b, mins_r = is_schedule_transition_imminent(
            curr_min, window_minutes=15, current_day=curr_day, scen_key=scen_key
        )
        t_blk = next_b if (is_imm and next_b) else curr_blk
        t_min = (curr_min + mins_r) if (is_imm and mins_r) else curr_min
        s_loc = get_npc_scheduled_location(
            npc_ref, current_minute=t_min, current_day=curr_day, scen_key=scen_key, time_slot=t_blk, session_id=sess_id
        )
        s_nid = get_npc_scheduled_node_id(
            npc_ref, current_minute=t_min, current_day=curr_day, scen_key=scen_key, time_slot=t_blk
        ) or ""
        return str(s_loc or ""), str(s_nid or "")

    def _queue_departure(npc_nm: str, dest_loc: str, dest_nid: str, reason: str) -> None:
        if any(r["name"].lower() == npc_nm.lower() for r in departing_records):
            return
        departing_records.append({
            "name": npc_nm,
            "target_location": dest_loc,
            "target_node_id": dest_nid,
            "reason": reason,
        })
        nonlocal updated_partners
        updated_partners = [p for p in updated_partners if p.lower() != npc_nm.lower()]

    if has_exited_convo:
        for p_nm in prev_partners:
            p_key = _canon_npc_key(p_nm)
            st = states.pop(p_key, None)
            prof = profile_resolver(session, p_nm, party=party)
            if prof["is_private_meetup"]:
                if sess_id:
                    try:
                        db.update_phone_appointment_status(int(sess_id), p_nm, "completed")
                        db.update_phone_appointment_status(int(sess_id), p_nm.lower().replace(" ", "_"), "completed")
                    except Exception:
                        pass
                if prof["is_npc_home_or_office"]:
                    directives.append(
                        f"\n[PRIVATE MEETUP GOODBYE (AT {p_nm.upper()}'S SPACE)]: The player is wrapping up the meetup. "
                        f"Have {p_nm} give the player a warm, proper goodbye while remaining in their own space (do NOT reopen dialogue).\n"
                    )
                else:
                    dest_loc, dest_nid = _resolve_npc_dest(p_nm, prof)
                    if not dest_loc or _locations_match(scene_loc, dest_loc, session_id=sess_id, node_a=scene_nid, node_b=dest_nid):
                        dest_loc = "their next obligation"
                    dest_clean = dest_loc.split("➔")[-1].strip()
                    _queue_departure(p_nm, dest_loc, dest_nid, "private_meetup_exit")
                    directives.append(
                        f"\n[PRIVATE MEETUP CONCLUSION & DEPARTURE]: The player has ended the conversation to wrap up the meetup. "
                        f"In `outcome_narrative`, have {p_nm} explicitly mention that they need to get going too (toward {dest_clean}), "
                        f"give the player a proper goodbye, and physically leave the scene! Do NOT keep {p_nm} in `npcs_present`.\n"
                    )
            elif st and st.get("stage") in ("stage_1_warning", "stage_2_ultimatum", "extended_stay"):
                dest_loc = str(st.get("target_location") or "")
                dest_nid = str(st.get("target_node_id") or "")
                dest_clean = dest_loc.split("➔")[-1].strip() if dest_loc else "their scheduled obligation"
                _queue_departure(p_nm, dest_loc, dest_nid, "schedule_departure_on_exit")
                directives.append(
                    f"\n[SCHEDULE DEPARTURE]: As the conversation ends, {p_nm} bids farewell and physically leaves the scene for {dest_clean}.\n"
                )
        save_npc_departure_states(session, states, persist_db=True)
        return {
            "directive_note": "".join(directives),
            "departing_for_schedule": departing_records,
            "active_partners": [],
        }

    bound_crossed = False
    if prev_min is not None and prev_min != curr_min:
        try:
            b_info = detect_schedule_boundary_crossed(prev_day or curr_day, int(prev_min), curr_day, curr_min, scen_key=scen_key)
            bound_crossed = bool(b_info.get("crossed"))
        except Exception:
            bound_crossed = False
    is_imm_now, _, next_blk_now, mins_rem_now = is_schedule_transition_imminent(
        curr_min, window_minutes=15, current_day=curr_day, scen_key=scen_key
    )

    for p_nm in list(updated_partners):
        p_key = _canon_npc_key(p_nm)
        prof = profile_resolver(session, p_nm, party=party)

        if prof["is_private_meetup"] or prof["is_party_member"]:
            states.pop(p_key, None)
            continue

        st = states.get(p_key)
        act_targets_this_npc = (
            len(updated_partners) == 1
            or str(lead_act.get("target_npc") or "").strip().lower() == p_nm.lower()
            or p_nm.lower() in str(lead_act.get("label") or "").lower()
        )

        if st:
            stage_val = str(st.get("stage") or "none")
            dest_loc = str(st.get("target_location") or "")
            dest_nid = str(st.get("target_node_id") or "")
            dest_clean = dest_loc.split("➔")[-1].strip() if dest_loc else "their next obligation"

            if is_let_depart_act and act_targets_this_npc:
                states.pop(p_key, None)
                _queue_departure(p_nm, dest_loc, dest_nid, "let_npc_depart")
                directives.append(
                    f"\n[SCHEDULE DEPARTURE]: The player lets {p_nm} head out. {p_nm} excuses themself with a brief farewell and leaves the scene for {dest_clean}.\n"
                )
                continue

            if stage_val == "stage_1_warning" and act_targets_this_npc:
                if is_convince_act:
                    if act_succeeded and st.get("extended_block") != curr_blk:
                        st["stage"] = "extended_stay"
                        st["turns_remaining"] = 5
                        st["extended_block"] = curr_blk
                        states[p_key] = st
                        directives.append(
                            f"\n[STAY EXTENSION GRANTED (5 TURNS)]: The player convinced {p_nm} to stay! "
                            f"{p_nm} agrees to spare a few more minutes before heading to {dest_clean}.\n"
                        )
                    else:
                        states.pop(p_key, None)
                        _queue_departure(p_nm, dest_loc, dest_nid, "convince_stay_failed")
                        directives.append(
                            f"\n[SCHEDULE DEPARTURE — CONVINCE FAILED]: The player failed to convince {p_nm} to stay. "
                            f"{p_nm} apologetically excuses themself right now and physically leaves the scene for {dest_clean}!\n"
                        )
                else:
                    if act_succeeded:
                        st["stage"] = "stage_2_ultimatum"
                        states[p_key] = st
                        directives.append(
                            f"\n[URGENT SCHEDULE DEPARTURE — STAGE 2 ULTIMATUM]: {p_nm} answers the player's question/action normally, "
                            f"then checks the time and states firmly that they MUST leave for {dest_clean} right now.\n"
                        )
                    else:
                        states.pop(p_key, None)
                        _queue_departure(p_nm, dest_loc, dest_nid, "stage1_hurry_check_failed")
                        directives.append(
                            f"\n[SCHEDULE DEPARTURE — HURRIED EXIT]: Because {p_nm} is late for {dest_clean} and the player's check failed, "
                            f"{p_nm} cuts the exchange short, ignores the request, excuses themself immediately, and physically leaves the scene!\n"
                        )
                continue

            if stage_val == "stage_2_ultimatum" and act_targets_this_npc:
                if is_custom_act:
                    states.pop(p_key, None)
                    _queue_departure(p_nm, dest_loc, dest_nid, "stage2_custom_action_failed")
                    directives.append(
                        f"\n[SCHEDULE DEPARTURE — OUT OF TIME]: {p_nm} has no time left to entertain anything else—they excuse themself immediately and physically leave the scene for {dest_clean}!\n"
                    )
                elif is_convince_act:
                    if act_succeeded and st.get("extended_block") != curr_blk:
                        st["stage"] = "extended_stay"
                        st["turns_remaining"] = 5
                        st["extended_block"] = curr_blk
                        states[p_key] = st
                        directives.append(
                            f"\n[STAY EXTENSION GRANTED (5 TURNS)]: At the last moment, the player convinced {p_nm} to stay a bit longer before heading to {dest_clean}!\n"
                        )
                    else:
                        states.pop(p_key, None)
                        _queue_departure(p_nm, dest_loc, dest_nid, "stage2_convince_failed")
                        directives.append(
                            f"\n[SCHEDULE DEPARTURE — CONVINCE FAILED]: The player failed to convince {p_nm} to stay. "
                            f"{p_nm} excuses themself immediately and physically leaves the scene for {dest_clean}!\n"
                        )
                else:
                    states.pop(p_key, None)
                    _queue_departure(p_nm, dest_loc, dest_nid, "stage2_departed")
                    directives.append(
                        f"\n[SCHEDULE DEPARTURE]: {p_nm} bids farewell and physically leaves the scene for {dest_clean}.\n"
                    )
                continue

            if stage_val == "extended_stay":
                rem = int(st.get("turns_remaining", 5)) - 1
                if rem <= 0:
                    st["stage"] = "completed_block"
                    st["turns_remaining"] = 0
                    states[p_key] = st
                    _queue_departure(p_nm, dest_loc, dest_nid, "extended_stay_expired")
                    directives.append(
                        f"\n[STAY EXTENSION COMPLETE — FINAL TURN DEPARTURE]: {p_nm}'s 5 bonus turns are up. "
                        f"Have {p_nm} respond warmly to the player's action, give a polite heads-up and goodbye that they truly cannot delay any longer, "
                        f"and physically depart the scene for {dest_clean}!\n"
                    )
                else:
                    st["turns_remaining"] = rem
                    states[p_key] = st
                continue

            if stage_val == "completed_block":
                if st.get("extended_block") != curr_blk:
                    states.pop(p_key, None)
                else:
                    continue

        dest_loc, dest_nid = _resolve_npc_dest(p_nm, prof)
        if not dest_loc or _locations_match(scene_loc, dest_loc, session_id=sess_id, node_a=scene_nid, node_b=dest_nid):
            continue
        if prof["is_quest_stationed_here"]:
            continue

        non_scene_turns = sum(1 for h in history if isinstance(h, dict) and h.get("type") != "scene")
        linger_turns = compute_scene_beat_linger_turns(history, session=session, active_partners=[p_nm])
        has_real_clock_shift = bool((bound_crossed and non_scene_turns >= 1) or (is_imm_now and linger_turns >= 1 and non_scene_turns >= 1))
        has_commitment_elsewhere = bool(prof.get("has_other_commitment_loc") and (linger_turns >= 1 or non_scene_turns >= 1))
        has_prolonged_linger = bool(linger_turns >= 4)

        if has_real_clock_shift or has_commitment_elsewhere or has_prolonged_linger:
            dest_clean = dest_loc.split("➔")[-1].strip()
            t_blk = next_blk_now if (is_imm_now and next_blk_now) else curr_blk
            states[p_key] = {
                "stage": "stage_1_warning",
                "target_location": dest_loc,
                "target_node_id": dest_nid,
                "triggered_block": t_blk,
                "turns_remaining": 0,
                "extended_block": "",
            }
            timing_str = f"in about {mins_rem_now} minutes" if (is_imm_now and mins_rem_now) else "now"
            directives.append(
                f"\n[URGENT SCHEDULE DEPARTURE — STAGE 1 WARNING]: {p_nm} is supposed to be at {dest_clean} {timing_str}. "
                f"In their spoken reply this turn, {p_nm} MUST explicitly mention that they need to get going to {dest_clean} soon!\n"
            )

    active_keys = {_canon_npc_key(p) for p in updated_partners}
    for k in list(states.keys()):
        if k not in active_keys and states[k].get("stage") != "completed_block":
            states.pop(k, None)

    save_npc_departure_states(session, states, persist_db=True)
    return {
        "directive_note": "".join(directives),
        "departing_for_schedule": departing_records,
        "active_partners": updated_partners,
    }


def relocate_departed_npcs_impl(
    session: Dict[str, Any],
    result: Dict[str, Any],
    departing_records: List[Dict[str, str]],
    *,
    find_contact_and_lore_fn: Callable[[int, str], Tuple[Optional[Dict[str, Any]], Dict[str, Any]]],
    stage_info: Optional[Dict[str, Any]] = None,
) -> None:
    """Physically removes departed NPCs from scene and persists destination location."""
    if not departing_records:
        return
    sess_id = session.get("id")
    curr_day = int(session.get("current_day") or 1)
    curr_min = int(session.get("current_minute") if session.get("current_minute") is not None else 480)
    from mechanics.world.schedules import get_time_block_key

    curr_blk = get_time_block_key(curr_min)
    history = session.get("history") or []
    turn_idx = len(history)

    dep_names_low = {str(r.get("name") or "").strip().lower() for r in departing_records if r.get("name")}
    if not dep_names_low:
        return

    if isinstance(result, dict):
        if isinstance(result.get("npcs_present"), list):
            result["npcs_present"] = [
                n for n in result["npcs_present"]
                if str(n.get("name") if isinstance(n, dict) else n).strip().lower() not in dep_names_low
            ]
        dep_list = list(result.get("npc_departures") or [])
        dep_chars = list(result.get("departed_characters") or [])
        for r in departing_records:
            nm = str(r.get("name") or "").strip()
            if nm and nm not in dep_list:
                dep_list.append(nm)
            if nm and nm not in dep_chars:
                dep_chars.append(nm)
        result["npc_departures"] = dep_list
        result["departed_characters"] = dep_chars

        rem_dps = [p for p in (result.get("dialogue_partners") or []) if str(p).strip().lower() not in dep_names_low]
        result["dialogue_partners"] = rem_dps
        result["dialogue_partner"] = rem_dps[0] if rem_dps else None

    if isinstance(session.get("current_npcs"), list):
        session["current_npcs"] = [
            n for n in session["current_npcs"]
            if str(n.get("name") if isinstance(n, dict) else n).strip().lower() not in dep_names_low
        ]

    if isinstance(stage_info, dict):
        sd = list(stage_info.get("schedule_departed_npcs") or [])
        for r in departing_records:
            nm = str(r.get("name") or "").strip()
            if nm and nm not in sd:
                sd.append(nm)
        stage_info["schedule_departed_npcs"] = sd

    try:
        from game_engine.npcs.cast_planner import get_cast_state, save_cast_state
        cs = get_cast_state(session)
        dis_map = cs.setdefault("disengaged_at_turn", {})
        for dn in dep_names_low:
            dis_map[dn] = turn_idx
        save_cast_state(session, cs, persist_db=bool(sess_id))
        if isinstance(result, dict):
            result["_staged_cast_state"] = cs
    except Exception:
        pass

    relocated_overrides = dict(session.get("npc_relocated_overrides") or {})
    for r in departing_records:
        nm = str(r.get("name") or "").strip()
        dest_loc = str(r.get("target_location") or "").strip()
        dest_nid = str(r.get("target_node_id") or "").strip()
        if not nm:
            continue
        if sess_id:
            try:
                db.remove_temporary_companion(int(sess_id), nm)
            except Exception:
                pass
        if not dest_loc or dest_loc == "their next obligation":
            continue

        relocated_overrides[_canon_npc_key(nm)] = {
            "name": nm,
            "location": dest_loc,
            "node_id": dest_nid,
            "day": curr_day,
            "minute": curr_min,
            "block": curr_blk,
        }
        if sess_id:
            try:
                c_existing, lore_ent = find_contact_and_lore_fn(int(sess_id), nm)
                if c_existing:
                    b_inf = dict(c_existing.get("basic_info") or {})
                    b_inf["location"] = dest_loc
                    db.upsert_contact(
                        session_id=int(sess_id),
                        character_id=int(c_existing.get("character_id") or 0),
                        npc_id=str(c_existing.get("npc_id") or nm),
                        name=nm,
                        basic_info=b_inf,
                        delta_score=0,
                    )
                if lore_ent:
                    db.upsert_lorebook_entity(
                        int(sess_id),
                        "person",
                        nm,
                        str(lore_ent.get("description") or ""),
                        str(lore_ent.get("disposition") or "neutral"),
                        faction=str(lore_ent.get("faction") or ""),
                    )
            except Exception as e:
                log.warning("Failed updating relocated NPC destination for '%s': %s", nm, e)

    session["npc_relocated_overrides"] = relocated_overrides
    if sess_id:
        try:
            db.update_session(int(sess_id), extra={"npc_relocated_overrides": relocated_overrides})
        except Exception:
            pass
