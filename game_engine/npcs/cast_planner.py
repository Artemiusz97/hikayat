from __future__ import annotations
"""
Deterministic Cast & Dialogue Planner for Hikayat.

Authoritative pre-turn cast management and post-narration cast event arbitration.
Guarantees that:
1. Python deterministically owns scene attendance, active dialogue partners, and departures.
2. Narrative prose quotation scraping never pollutes or resurrects conversation state.
3. Narrator cast suggestions (arrive, depart, engage) are validated against strict contracts.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Set

import db
import game_engine
from config import DETERMINISTIC_CAST
from mechanics.narrative.intent import (
    is_dialogue_exit_action,
    get_resolved_intent,
    IntentCategory,
)
from mechanics.world.mobility import (
    get_session_dialogue_partners,
    is_character_mobile,
    is_solo_travel_intent,
    ACCOMPANIED_TRAVEL_PHRASES,
)
from game_engine.npcs.dialogue_tracking import is_npc_invited_in_action

logger = logging.getLogger("hikayat.game_engine.npcs.cast_planner")

_AMBIENT_ROLE_KEYWORDS = {
    "student", "patron", "barista", "guard", "clerk", "bystander", "customer",
    "vendor", "traveler", "courier", "waiter", "waitress", "librarian", "scholar",
    "monk", "priest", "merchant", "nurse", "trainer", "guest", "maid", "butler",
    "officer", "recruit", "apprentice", "alchemist", "innkeeper", "shopkeeper"
}


@dataclass
class CastPlan:
    present_npcs: List[Dict[str, Any]] = field(default_factory=list)
    dialogue_partners: List[str] = field(default_factory=list)
    bystander_npcs: List[str] = field(default_factory=list)
    departing_npcs: List[str] = field(default_factory=list)
    rejections: List[Dict[str, Any]] = field(default_factory=list)
    has_exited_convo: bool = False


def get_cast_state(session: dict) -> dict:
    """Retrieve or initialize persistent cast tracking state."""
    # 1. Directly on session dictionary (e.g. hydrated from db.get_session via extra_dict flattening)
    if isinstance(session.get("cast_state"), dict):
        return session["cast_state"]

    # 2. Inside extra_json or extra
    extra = session.get("extra_json") or session.get("extra") or {}
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except Exception:
            extra = {}
    if isinstance(extra, dict) and isinstance(extra.get("cast_state"), dict):
        state = extra["cast_state"]
        session["cast_state"] = state
        return state

    # 3. Fallback: query DB if session has an id
    session_id = session.get("id")
    if session_id:
        try:
            db_sess = db.get_session(session_id)
            if db_sess and isinstance(db_sess.get("cast_state"), dict):
                session["cast_state"] = db_sess["cast_state"]
                return session["cast_state"]
        except Exception as e:
            logger.debug("[CastPlanner] Could not load cast_state from DB: %s", e)

    state = {
        "disengaged_at_turn": {},
        "idle_turns": {},
    }
    session["cast_state"] = state
    if isinstance(session.get("extra_json"), dict):
        session["extra_json"]["cast_state"] = state
    return state


def save_cast_state(session: dict, state: dict) -> None:
    """Persist cast tracking state back into session and SQLite DB."""
    session["cast_state"] = state
    extra = session.get("extra_json") or session.get("extra") or {}
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except Exception:
            extra = {}
    if not isinstance(extra, dict):
        extra = {}
    extra["cast_state"] = state
    session["extra_json"] = extra

    session_id = session.get("id")
    if session_id:
        try:
            db.update_session(session_id, extra={"cast_state": state})
        except Exception as e:
            logger.warning("[CastPlanner] Failed to persist cast_state to db for session %s: %s", session_id, e)


def plan_pre_turn(
    session: dict,
    party: list,
    actions: list,
    stage_info: Optional[dict] = None,
    is_combat: bool = False,
    new_loc: Optional[str] = None,
) -> CastPlan:
    """
    Computes authoritative cast plan BEFORE narration begins.
    
    Evaluates:
    1. Combat break
    2. Movement & spatial isolation
    3. Schedule departures
    4. Explicit dialogue exits (ends_dialogue / dialogue_exit intent)
    5. Action dismissals
    6. Social intent targeting
    7. Idle turn timeouts (3-turn non-involving rule)
    """
    if not DETERMINISTIC_CAST:
        # Pass-through legacy mode
        return CastPlan(
            present_npcs=list(session.get("current_npcs") or []),
            dialogue_partners=list(get_session_dialogue_partners(session)),
        )

    history = session.get("history") or []
    current_turn_index = len(history) if history else int(session.get("current_turn_index") or 0)
    cast_state = get_cast_state(session)
    disengaged_at_turn = cast_state.setdefault("disengaged_at_turn", {})
    idle_turns = cast_state.setdefault("idle_turns", {})

    raw_npcs = list(session.get("current_npcs") or [])
    current_npcs = [n if isinstance(n, dict) else {"name": str(n)} for n in raw_npcs if n]
    current_partners = list(get_session_dialogue_partners(session))
    departing_npcs: List[str] = []
    has_exited_convo = False

    party_names = set()
    for p_ent in (party or []):
        char_obj = p_ent[0] if isinstance(p_ent, (tuple, list)) else p_ent
        if isinstance(char_obj, dict) and char_obj.get("name"):
            party_names.add(char_obj["name"].strip().lower())

    # 1. Combat break: All peaceful 1-on-1 dialogue locks break when combat starts
    from mechanics.combat import is_in_combat as _check_combat
    if is_combat or _check_combat(session):
        current_partners = []

    # 2. Movement / Location transition
    old_loc = session.get("current_location", "")
    if new_loc and new_loc != old_loc:
        # Check which partners accompany the player
        retained_partners = []
        for p in current_partners:
            p_low = p.strip().lower()
            if p_low in party_names:
                retained_partners.append(p)
            elif is_npc_invited_in_action(p, actions):
                retained_partners.append(p)
            else:
                # Left behind in previous room
                logger.info("[CastPlanner] Dropping partner '%s' due to uninvited zone movement", p)
        current_partners = retained_partners

    # 3. Schedule departures from Stage Manager
    if stage_info and stage_info.get("schedule_departed_npcs"):
        for sn in stage_info["schedule_departed_npcs"]:
            s_name = game_engine._get_npc_name(sn).strip()
            if s_name and s_name not in departing_npcs:
                departing_npcs.append(s_name)
                current_npcs = [n for n in current_npcs if game_engine._get_npc_name(n).strip().lower() != s_name.lower()]
                current_partners = [p for p in current_partners if p.strip().lower() != s_name.lower()]

    # 4. Explicit dialogue exits (Decision Q3 & Q4: ends_dialogue flag or dialogue_exit intent)
    has_exit_action = any(is_dialogue_exit_action(a) for a in actions)
    if has_exit_action:
        has_exited_convo = True
        for p in current_partners:
            p_clean = p.strip()
            p_low = p_clean.lower()
            disengaged_at_turn[p_low] = current_turn_index
            idle_turns[p_low] = 0
            logger.info("[CastPlanner] Dialogue ended with '%s' at turn %d. Cooldown set.", p_clean, current_turn_index)
        current_partners = []

    # 5. Dismissal actions (e.g. asking a visiting NPC to leave the room)
    for a in actions:
        if isinstance(a, dict):
            r_intent = a.get("resolved_intent") or get_resolved_intent(a)
            t_name = str(a.get("target_npc") or r_intent.get("target_npc") or "").strip()
            t_low = t_name.lower()
            a_label = str(a.get("label") or "").lower()
            is_dismiss = bool(
                a.get("dismisses_npc") or
                r_intent.get("dismisses_npc") or
                (r_intent.get("intent") == "dialogue_exit" and any(w in a_label for w in ("leave", "go home", "send away", "dismiss", "head out", "depart")))
            )
            if is_dismiss and t_name:
                if t_name not in departing_npcs:
                    departing_npcs.append(t_name)
                current_npcs = [n for n in current_npcs if game_engine._get_npc_name(n).strip().lower() != t_low]
                current_partners = [p for p in current_partners if p.strip().lower() != t_low]

    # 6. Social intent + target NPC -> Dialogue Initiation (Decision Q5)
    if not has_exited_convo:
        social_intents = {
            "dialogue_init", "social_invite", "romantic_confession", "gift_offer",
            "disclosure_inquiry", "affection_touch", "party_recruit"
        }
        for a in actions:
            if isinstance(a, dict):
                r_intent = a.get("resolved_intent") or get_resolved_intent(a)
                intent_cat = r_intent.get("intent")
                target_npc = r_intent.get("target_npc") or ""
                a_label = str(a.get("label") or a.get("text") or "").lower()
                if intent_cat in social_intents:
                    for n in current_npcs:
                        n_name = game_engine._get_npc_name(n).strip()
                        n_low = n_name.lower()
                        n_first = n_low.split()[0] if n_low else ""
                        matches_target = bool(target_npc and (
                            n_low in target_npc.lower() or
                            target_npc.lower() in n_low or
                            (len(n_first) >= 3 and n_first in target_npc.lower())
                        ))
                        appears_in_label = bool(
                            n_low in a_label or
                            (len(n_first) >= 3 and n_first in a_label)
                        )
                        if matches_target or appears_in_label:
                            if n_name not in current_partners:
                                current_partners.append(n_name)
                            idle_turns[n_low] = 0
                            disengaged_at_turn.pop(n_low, None)
                            logger.info("[CastPlanner] Player initiated dialogue with '%s'", n_name)

    # 7. Idle Turn Counter (Decision Q6: 3 non-involving turns -> automatic disengagement)
    if not has_exited_convo and current_partners:
        action_labels = " ".join(str(a.get("label") or "") for a in actions).lower()
        action_targets = {str(a.get("target_npc") or "").strip().lower() for a in actions if a.get("target_npc")}
        surviving_partners = []
        for p in current_partners:
            p_clean = p.strip()
            p_low = p_clean.lower()
            p_first = p_low.split()[0] if p_low else ""
            is_involved = (
                p_low in action_targets or
                p_low in action_labels or
                (len(p_first) >= 3 and p_first in action_labels)
            )
            if is_involved:
                idle_turns[p_low] = 0
                surviving_partners.append(p_clean)
            else:
                curr_idle = idle_turns.get(p_low, 0) + 1
                idle_turns[p_low] = curr_idle
                if curr_idle >= 3:
                    # Timeout!
                    logger.info("[CastPlanner] Partner '%s' timed out after 3 idle turns. Downgrading to bystander.", p_clean)
                    disengaged_at_turn[p_low] = current_turn_index
                else:
                    surviving_partners.append(p_clean)
        current_partners = surviving_partners

    # Calculate bystanders (all present NPCs not actively conversing or departing)
    partner_lowers = {p.strip().lower() for p in current_partners}
    departing_lowers = {d.strip().lower() for d in departing_npcs}
    bystanders = []
    for n in current_npcs:
        nm = game_engine._get_npc_name(n).strip()
        if nm and nm.lower() not in partner_lowers and nm.lower() not in departing_lowers:
            bystanders.append(nm)

    # Persist updated cast state in session
    save_cast_state(session, cast_state)

    return CastPlan(
        present_npcs=current_npcs,
        dialogue_partners=current_partners,
        bystander_npcs=bystanders,
        departing_npcs=departing_npcs,
        has_exited_convo=has_exited_convo,
    )


def render_stage_plan(plan: CastPlan) -> str:
    """Renders the authoritative STAGE PLAN directive injected into narrator prompt (Decision Q8)."""
    present_names = [game_engine._get_npc_name(n).strip() for n in plan.present_npcs if game_engine._get_npc_name(n)]
    present_str = ", ".join(present_names) if present_names else "None (Room is empty)"
    departing_str = ", ".join(plan.departing_npcs) if plan.departing_npcs else "None"
    partners_str = ", ".join(plan.dialogue_partners) if plan.dialogue_partners else "None (Open exploration / not in dialogue)"
    bystanders_str = ", ".join(plan.bystander_npcs) if plan.bystander_npcs else "None"

    lines = [
        "[STAGE PLAN - DETERMINISTIC CAST CONTRACT]:",
        f"- PRESENT CHARACTERS IN IMMEDIATE SCENE: {present_str}",
        f"- DEPARTING CHARACTERS THIS TURN: {departing_str}",
        f"- ACTIVE DIALOGUE PARTNERS (Speaking directly with player): {partners_str}",
        f"- SILENT ROOM BYSTANDERS (Present in room, but NOT in conversation with player): {bystanders_str}",
        "CRITICAL CAST DIRECTIVES:",
        "- SILENT ROOM BYSTANDERS MUST NOT initiate conversation, interrogate, or speak aloud with the player this turn.",
        "- If Active Dialogue Partners is 'None', EVERY character present in the scene MUST STOP talking with the player.",
        "- You may suggest dynamic scene entries, exits, or conversation initiations via the `cast_events` JSON array."
    ]
    return "\n".join(lines)


def apply_cast_events(
    plan: CastPlan,
    cast_events: list,
    session: dict,
    party: list,
    stage_info: Optional[dict] = None,
) -> Tuple[CastPlan, List[Dict[str, Any]]]:
    """
    Arbitrates narrative-suggested cast_events against deterministic rules (Decisions Q5 & Q7).
    
    Returns (final_plan, rejected_events_list).
    """
    if not DETERMINISTIC_CAST or not cast_events:
        return plan, []

    history = session.get("history") or []
    current_turn_index = len(history) if history else int(session.get("current_turn_index") or 0)
    cast_state = get_cast_state(session)
    disengaged_at_turn = cast_state.get("disengaged_at_turn", {})

    sess_id = session.get("id")
    curr_node = session.get("current_node_id") or ""
    curr_loc = session.get("current_location") or ""
    party_names = {
        (p[0].get("name", "").strip().lower() if isinstance(p, (tuple, list)) and isinstance(p[0], dict) else "")
        for p in (party or [])
    }

    # Fetch active appointments
    active_appt_npcs = set()
    if sess_id:
        try:
            appts = db.get_phone_appointments(sess_id, status="arrived") + db.get_phone_appointments(sess_id, status="pending")
            for a in appts:
                an = str(a.get("npc_name") or "").strip().lower()
                if an:
                    active_appt_npcs.add(an)
        except Exception:
            pass

    rejections: List[Dict[str, Any]] = []
    updated_present = list(plan.present_npcs)
    updated_partners = list(plan.dialogue_partners)
    updated_departures = list(plan.departing_npcs)

    for ev in cast_events:
        if not isinstance(ev, dict):
            if hasattr(ev, "model_dump"):
                ev = ev.model_dump()
            else:
                continue

        ev_type = str(ev.get("type") or "").strip().lower()
        npc_name = str(ev.get("npc") or ev.get("name") or "").strip()
        reason = str(ev.get("reason") or "").strip()
        if not npc_name:
            continue
        npc_low = npc_name.lower()
        npc_first = npc_low.split()[0] if npc_low else ""

        # ── EVENT: ARRIVE (Decision Q7: Strict Roster) ────────────────────────
        if ev_type == "arrive":
            # Check if ambient role extra (e.g. "a barista", "school guard")
            is_ambient_role = any(kw in npc_low for kw in _AMBIENT_ROLE_KEYWORDS)
            # Check if known scheduled NPC at this location
            is_scheduled_here = False
            if sess_id and not is_ambient_role:
                try:
                    c_record = db.get_contact(sess_id, npc_low.replace(" ", "_"), 0)
                    if c_record:
                        c_loc = c_record.get("location") or (c_record.get("basic_info") or {}).get("location") or ""
                        if c_loc and (c_loc.lower() == curr_loc.lower() or curr_loc.lower() in c_loc.lower() or c_loc.lower() in curr_loc.lower()):
                            is_scheduled_here = True
                except Exception:
                    pass

            if is_ambient_role or is_scheduled_here:
                # Approved! Add to room attendance
                if not any(game_engine._get_npc_name(n).strip().lower() == npc_low for n in updated_present):
                    updated_present.append({"name": npc_name, "stage_role": "room_bystander"})
                    logger.info("[CastPlanner] Approved cast event arrive: '%s' (%s)", npc_name, reason)
            else:
                rej = {
                    "type": "arrive",
                    "npc": npc_name,
                    "reason": f"NPC '{npc_name}' is not scheduled at this location and is not an ambient role extra.",
                }
                rejections.append(rej)
                logger.warning("[CastPlanner] Rejected cast event arrive: %s", rej)

        # ── EVENT: DEPART (Decision Q7) ──────────────────────────────────────
        elif ev_type == "depart":
            if npc_low in party_names:
                rej = {
                    "type": "depart",
                    "npc": npc_name,
                    "reason": f"Party member '{npc_name}' cannot depart via ambient cast event.",
                }
                rejections.append(rej)
                logger.warning("[CastPlanner] Rejected cast event depart: %s", rej)
            elif npc_low in active_appt_npcs:
                rej = {
                    "type": "depart",
                    "npc": npc_name,
                    "reason": f"Appointment target '{npc_name}' cannot depart while meetup is active.",
                }
                rejections.append(rej)
                logger.warning("[CastPlanner] Rejected cast event depart: %s", rej)
            else:
                # Approved departure
                if npc_name not in updated_departures:
                    updated_departures.append(npc_name)
                updated_present = [n for n in updated_present if game_engine._get_npc_name(n).strip().lower() != npc_low]
                updated_partners = [p for p in updated_partners if p.strip().lower() != npc_low]
                logger.info("[CastPlanner] Approved cast event depart: '%s' (%s)", npc_name, reason)

        # ── EVENT: ENGAGE (Decision Q5: 2-Turn Re-engage Cooldown) ────────────
        elif ev_type == "engage":
            # Check presence
            is_present = any(game_engine._get_npc_name(n).strip().lower() == npc_low for n in updated_present)
            if not is_present:
                rej = {
                    "type": "engage",
                    "npc": npc_name,
                    "reason": f"NPC '{npc_name}' is not physically present in the room.",
                }
                rejections.append(rej)
                logger.warning("[CastPlanner] Rejected cast event engage: %s", rej)
                continue

            last_disengage = disengaged_at_turn.get(npc_low, -999)
            if (current_turn_index - last_disengage) < 2:
                # Under cooldown!
                rej = {
                    "type": "engage",
                    "npc": npc_name,
                    "reason": f"Re-engage cooldown active for '{npc_name}' (ended conversation {current_turn_index - last_disengage} turns ago; requires 2 turns).",
                }
                rejections.append(rej)
                logger.warning("[CastPlanner] Rejected cast event engage: %s", rej)
            else:
                # Approved engage!
                matched_name = next(game_engine._get_npc_name(n).strip() for n in updated_present if game_engine._get_npc_name(n).strip().lower() == npc_low)
                if matched_name not in updated_partners:
                    updated_partners.append(matched_name)
                logger.info("[CastPlanner] Approved cast event engage: '%s' (%s)", matched_name, reason)

    # Recalculate bystanders
    partner_lowers = {p.strip().lower() for p in updated_partners}
    departing_lowers = {d.strip().lower() for d in updated_departures}
    updated_bystanders = [
        game_engine._get_npc_name(n).strip()
        for n in updated_present
        if game_engine._get_npc_name(n).strip().lower() not in partner_lowers and
           game_engine._get_npc_name(n).strip().lower() not in departing_lowers
    ]

    final_plan = CastPlan(
        present_npcs=updated_present,
        dialogue_partners=updated_partners,
        bystander_npcs=updated_bystanders,
        departing_npcs=updated_departures,
        rejections=rejections,
        has_exited_convo=plan.has_exited_convo,
    )
    return final_plan, rejections
