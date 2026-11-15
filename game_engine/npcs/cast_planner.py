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
import random
import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Set

import db
import game_engine
import scenario_data
from mechanics.narrative.intent import (
    is_dialogue_exit_action,
    get_resolved_intent,
    IntentCategory,
)
from mechanics.world.mobility import (
    get_session_dialogue_partners,
    is_campus_scenario,
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


def _matches_name_boundary(needle: str, text: str) -> bool:
    """Case-insensitive whole-word boundary check so short names like 'Ken' never match 'token'."""
    n_clean = (needle or "").strip()
    t_clean = (text or "").strip()
    if not n_clean or not t_clean:
        return False
    return bool(re.search(r"(?<!\w)" + re.escape(n_clean) + r"(?!\w)", t_clean, re.IGNORECASE))


@dataclass
class CastPlan:
    present_npcs: List[Dict[str, Any]] = field(default_factory=list)
    dialogue_partners: List[str] = field(default_factory=list)
    bystander_npcs: List[str] = field(default_factory=list)
    departing_npcs: List[str] = field(default_factory=list)
    rejections: List[Dict[str, Any]] = field(default_factory=list)
    has_exited_convo: bool = False
    stealth_active: bool = False


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


def save_cast_state(session: dict, state: dict, persist_db: bool = True) -> None:
    """Persist cast tracking state back into session and optionally SQLite DB."""
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
    if persist_db and session_id:
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
    persist_db: bool = True,
) -> CastPlan:
    """
    Computes authoritative cast plan BEFORE narration begins.
    
    Evaluates:
    1. Combat break & Stealth Presence Shield (D16)
    2. Movement & spatial isolation
    3. Schedule departures
    4. Explicit dialogue exits (ends_dialogue / dialogue_exit intent)
    5. Action dismissals
    6. Social intent targeting (whole-word boundary matched)
    7. Idle turn timeouts (3-turn non-involving rule)
    """
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

    # D16: Stealth Presence Shield & Graduated Alert Harmony
    # Below 100% detection (UNAWARE / SUSPICIOUS / SEARCHING), failed covert rolls raise
    # sentry alertness without blowing cover; cover only breaks at 100% (ALERT_DETECTED) or loud actions.
    from mechanics.stealth import any_actor_hidden, break_stealth, get_session_stealth_state
    st_dict = get_session_stealth_state(session)
    meter_now = int(st_dict.get("detection_meter", 0) or 0)
    stage_now = str(st_dict.get("alert_level") or "unaware").lower()
    any_action_stealth = any(
        isinstance(a, dict) and (a.get("is_stealth") or a.get("stance") == "stealth")
        for a in (actions or [])
    )
    if meter_now >= 100 or stage_now == "detected":
        break_stealth(session, reason="detected_at_100_percent", break_all=True)
        stealth_active = False
    else:
        stealth_active = bool(any_actor_hidden(session) or any_action_stealth)

    party_names = set()
    for p_ent in (party or []):
        char_obj = p_ent[0] if isinstance(p_ent, (tuple, list)) else p_ent
        if isinstance(char_obj, dict) and char_obj.get("name"):
            party_names.add(char_obj["name"].strip().lower())
    for comp_list_key in ("party_npcs", "temporary_companions"):
        for comp in (session.get(comp_list_key) or []):
            c_nm = (comp.get("name") if isinstance(comp, dict) else str(comp)).strip().lower()
            if c_nm:
                party_names.add(c_nm)
    if session.get("id"):
        try:
            for comp in (db.get_session_party_npcs(session["id"]) or []) + (db.get_temporary_companions(session["id"]) or []):
                c_nm = (comp.get("name") if isinstance(comp, dict) else str(comp)).strip().lower()
                if c_nm:
                    party_names.add(c_nm)
        except Exception:
            pass

    # 1. Combat break or active stealth: peaceful 1-on-1 dialogue locks do not hold
    from mechanics.combat import is_in_combat as _check_combat
    if is_combat or _check_combat(session) or stealth_active:
        current_partners = []

    # 2. Movement / Location transition
    old_loc = session.get("current_location", "")
    if new_loc and new_loc != old_loc:
        retained_partners = []
        if not stealth_active:
            for p in current_partners:
                p_low = p.strip().lower()
                if p_low in party_names:
                    retained_partners.append(p)
                elif is_npc_invited_in_action(p, actions):
                    retained_partners.append(p)
                else:
                    logger.info("[CastPlanner] Dropping partner '%s' due to uninvited zone movement", p)
        current_partners = retained_partners

        accompanying_names = party_names | {p.strip().lower() for p in retained_partners}
        staged_dest_npcs = [
            n if isinstance(n, dict) else {"name": str(n)}
            for n in ((stage_info.get("stage_npcs") if stage_info else None) or []) if n
        ]
        accompanying_npcs = [
            n for n in current_npcs
            if game_engine._get_npc_name(n).strip().lower() in accompanying_names
        ]
        seen_names = set()
        new_current_npcs = []
        for n in accompanying_npcs + staged_dest_npcs:
            name_val = game_engine._get_npc_name(n).strip().lower()
            if name_val and name_val not in seen_names:
                seen_names.add(name_val)
                new_current_npcs.append(n)
        current_npcs = new_current_npcs

    # Private Room Shield & Crowd Suppression (Decision 4)
    # When entering or situated in a private/restricted/discreet room, filter out non-eligible ambient bystanders.
    effective_node_id = (stage_info.get("effective_node_id") if stage_info else None) or session.get("current_node_id")
    if effective_node_id:
        sess_id = session.get("id") or session.get("session_id")
        if sess_id:
            try:
                node_obj = db.get_world_node(sess_id, effective_node_id)
                if node_obj and str(node_obj.get("privacy_level") or "").lower() in ("private", "restricted", "discreet"):
                    from mechanics.world.npc_schedule import is_npc_eligible_for_private_room
                    shielded_npcs = []
                    for n in current_npcs:
                        n_nm = game_engine._get_npc_name(n)
                        is_bystander = isinstance(n, dict) and str(n.get("stage_role") or "") == "room_bystander"
                        if (
                            not is_bystander
                            or n_nm.strip().lower() in party_names
                            or n_nm.strip().lower() in [p.strip().lower() for p in current_partners]
                            or is_npc_eligible_for_private_room(n_nm, session, node_id=effective_node_id)
                        ):
                            shielded_npcs.append(n)
                        else:
                            logger.info("[CastPlanner] Suppressing ambient bystander '%s' in private room '%s'", n_nm, effective_node_id)
                    current_npcs = shielded_npcs
            except Exception:
                pass

    # 2b. Sync active Non-Hostile Anomaly presence into current_npcs in Anomalous Incursions
    try:
        import scenario_data
        if scenario_data.is_anomalous_incursions_scenario(str(session.get("scenario") or "")):
            from mechanics.world.anomalous_events import sync_non_hostile_anomaly_scene_presence
            temp_sess_for_anom = dict(session, current_npcs=current_npcs)
            current_npcs = sync_non_hostile_anomaly_scene_presence(
                session.get("id") or session.get("session_id"),
                session=temp_sess_for_anom,
                location_str=str(new_loc or old_loc or ""),
                node_id=str(effective_node_id or ""),
                persist_db=False,
            )
            current_partners = [
                p for p in current_partners
                if not any(
                    isinstance(n, dict)
                    and n.get("is_anomalous_entity")
                    and n.get("talkable") is False
                    and game_engine._get_npc_name(n).strip().lower() == p.strip().lower()
                    for n in current_npcs
                )
            ]
    except Exception:
        pass

    # 3. Schedule departures from Stage Manager
    if stage_info and stage_info.get("schedule_departed_npcs"):
        for sn in stage_info["schedule_departed_npcs"]:
            s_name = game_engine._get_npc_name(sn).strip()
            if s_name and s_name not in departing_npcs:
                departing_npcs.append(s_name)
                current_npcs = [n for n in current_npcs if game_engine._get_npc_name(n).strip().lower() != s_name.lower()]
                current_partners = [p for p in current_partners if p.strip().lower() != s_name.lower()]

    # 4. Explicit dialogue exits (ends_dialogue flag or dialogue_exit intent)
    has_exit_action = any(
        (isinstance(a, dict) and a.get("departure_action") != "let_npc_depart" and (a.get("_pinned_dialogue_exit") is True or is_dialogue_exit_action(a)))
        or (not isinstance(a, dict) and is_dialogue_exit_action(a))
        for a in actions
    )
    if has_exit_action:
        has_exited_convo = True
        for p in current_partners:
            p_clean = p.strip()
            p_low = p_clean.lower()
            disengaged_at_turn[p_low] = current_turn_index
            idle_turns[p_low] = 0
            logger.info("[CastPlanner] Dialogue ended with '%s' at turn %d. Cooldown set.", p_clean, current_turn_index)
        current_partners = []
        for n in current_npcs:
            if isinstance(n, dict):
                if n.get("stage_role") == "active_partner":
                    n["stage_role"] = "room_bystander"
                if n.get("attention_ring") == "ring_1_partner":
                    n["attention_ring"] = "ring_3_bystander"
                if isinstance(n.get("micro_blocking"), dict) and n["micro_blocking"].get("proximity") == "conversational_distance":
                    n["micro_blocking"]["proximity"] = "across_room"

    # 5. Dismissal actions (e.g. asking a visiting NPC to leave the room)
    for a in actions:
        if isinstance(a, dict):
            r_intent = a.get("resolved_intent") or get_resolved_intent(a)
            raw_dismiss_val = a.get("dismisses_npc") or r_intent.get("dismisses_npc")
            t_name = str(
                (raw_dismiss_val if isinstance(raw_dismiss_val, str) and raw_dismiss_val.lower() not in ("true", "false", "1", "0") else "")
                or a.get("target_npc")
                or r_intent.get("target_npc")
                or ""
            ).strip()
            a_label = str(a.get("label") or "")
            a_lbl_low = a_label.strip().lower()
            is_player_leaving_convo = bool(
                a.get("_pinned_dialogue_exit")
                or a_lbl_low.startswith("leave conversation")
                or a_lbl_low.startswith("end conversation")
                or a_lbl_low.startswith("step back from observing")
            )
            is_dismiss = bool(
                raw_dismiss_val
                or (
                    not is_player_leaving_convo
                    and r_intent.get("intent") == "dialogue_exit"
                    and any(_matches_name_boundary(w, a_label) for w in ("leave", "go home", "send away", "dismiss", "head out", "depart"))
                )
            )
            if is_dismiss and t_name:
                import namegen
                matched_dismissed = []
                for n in current_npcs:
                    nm = game_engine._get_npc_name(n).strip()
                    n_toks = namegen.get_unique_person_tokens(nm, peer_names=current_npcs) if nm else set()
                    if (
                        nm.lower() == t_name.lower()
                        or _matches_name_boundary(nm, t_name)
                        or any(_matches_name_boundary(tok, t_name) for tok in n_toks if len(tok) >= 2)
                    ):
                        matched_dismissed.append(nm)
                if not matched_dismissed:
                    matched_dismissed.append(t_name)
                for md in matched_dismissed:
                    if md not in departing_npcs:
                        departing_npcs.append(md)
                    md_low = md.lower()
                    current_npcs = [n for n in current_npcs if game_engine._get_npc_name(n).strip().lower() != md_low]
                    current_partners = [p for p in current_partners if p.strip().lower() != md_low]

    # 6. Social intent + target NPC -> Dialogue Initiation (word-boundary matched; blocked while stealth_active)
    if not has_exited_convo and not stealth_active:
        import namegen
        social_intents = {
            "dialogue_init", "social_invite", "romantic_confession", "gift_offer",
            "disclosure_inquiry", "affection_touch", "party_recruit"
        }
        for a in actions:
            if isinstance(a, dict):
                r_intent = a.get("resolved_intent") or get_resolved_intent(a)
                intent_cat = r_intent.get("intent")
                target_npc = str(a.get("target_npc") or r_intent.get("target_npc") or "").strip()
                a_label = str(a.get("label") or a.get("text") or "")
                if (
                    intent_cat in social_intents
                    or a.get("is_anomaly_inquiry")
                    or str(a.get("approach") or "").startswith(("anomaly_inquiry", "anomaly_pattern"))
                ):
                    for n in current_npcs:
                        if isinstance(n, dict) and n.get("is_anomalous_entity") and (n.get("talkable") is False and not n.get("pattern_observable")):
                            continue
                        n_name = game_engine._get_npc_name(n).strip()
                        n_low = n_name.lower()
                        n_toks = namegen.get_unique_person_tokens(n_name, peer_names=current_npcs) if n_name else set()
                        matches_target = bool(
                            target_npc and (
                                n_low == target_npc.lower()
                                or _matches_name_boundary(n_name, target_npc)
                                or _matches_name_boundary(target_npc, n_name)
                                or any(_matches_name_boundary(tok, target_npc) for tok in n_toks if len(tok) >= 2)
                            )
                        )
                        appears_in_label = bool(
                            _matches_name_boundary(n_name, a_label)
                            or any(_matches_name_boundary(tok, a_label) for tok in n_toks if len(tok) >= 2)
                        )
                        if matches_target or appears_in_label:
                            if n_name not in current_partners:
                                current_partners.append(n_name)
                            idle_turns[n_low] = 0
                            disengaged_at_turn.pop(n_low, None)
                            logger.info("[CastPlanner] Player initiated dialogue with '%s'", n_name)

    # 7. Idle Turn Counter (3 non-involving turns -> automatic disengagement)
    if not has_exited_convo and current_partners:
        import namegen
        action_labels = " ".join(str(a.get("label") or "") for a in actions if isinstance(a, dict))
        action_targets = [str(a.get("target_npc") or "").strip() for a in actions if isinstance(a, dict) and a.get("target_npc")]
        surviving_partners = []
        partner_peer_pool = list(current_partners) + [game_engine._get_npc_name(n) for n in current_npcs if game_engine._get_npc_name(n)]
        for p in current_partners:
            p_clean = p.strip()
            p_low = p_clean.lower()
            p_toks = namegen.get_unique_person_tokens(p_clean, peer_names=partner_peer_pool) if p_clean else set()
            is_involved = (
                any(
                    p_low == t.lower()
                    or _matches_name_boundary(p_clean, t)
                    or any(_matches_name_boundary(tok, t) for tok in p_toks if len(tok) >= 2)
                    for t in action_targets
                )
                or _matches_name_boundary(p_clean, action_labels)
                or any(_matches_name_boundary(tok, action_labels) for tok in p_toks if len(tok) >= 2)
            )
            if is_involved:
                idle_turns[p_low] = 0
                surviving_partners.append(p_clean)
            else:
                curr_idle = idle_turns.get(p_low, 0) + 1
                idle_turns[p_low] = curr_idle
                if curr_idle >= 3:
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

    save_cast_state(session, cast_state, persist_db=persist_db)

    return CastPlan(
        present_npcs=current_npcs,
        dialogue_partners=current_partners,
        bystander_npcs=bystanders,
        departing_npcs=departing_npcs,
        has_exited_convo=has_exited_convo,
        stealth_active=stealth_active,
    )


def render_stage_plan(plan: CastPlan) -> str:
    """Renders the authoritative STAGE PLAN directive injected into narrator prompt."""
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
        "- You may suggest dynamic scene entries, exits, or conversation initiations via the `cast_events` JSON array.",
        "- CAST CONTINUITY: Characters from RECENT HISTORY who are NOT listed in PRESENT CHARACTERS are NOT in the scene. "
        "Do NOT narrate them acting or speaking. If a person must (re)enter or is newly on-screen, emit a `cast_events` "
        "`arrive` with a personal name (invent one for an unnamed person), `gender`, and `descriptor`, and use that name in the prose."
    ]
    if plan.stealth_active:
        lines.append(
            "[STAGE PLAN — STEALTH ACTIVE]: The protagonist is hidden in active stealth. "
            "Present characters are UNAWARE of the protagonist's presence and MUST NOT initiate conversation, greet, or address the protagonist."
        )
    return "\n".join(lines)


def _locations_overlap(loc_a: str, loc_b: str) -> bool:
    a = (loc_a or "").strip().lower()
    b = (loc_b or "").strip().lower()
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    a_leaf = a.split("➔")[-1].strip()
    b_leaf = b.split("➔")[-1].strip()
    return bool(a_leaf and b_leaf and (a_leaf == b_leaf or a_leaf in b_leaf or b_leaf in a_leaf))


def _resolve_present_npc_name(npc_name: str, present_list: list, party_names: set) -> Optional[str]:
    """Resolves exact or unambiguous cultural/title partial NPC name against present_list (rejecting particles & player collisions)."""
    q = (npc_name or "").strip()
    if not q:
        return None
    q_low = q.lower()
    for n in present_list:
        nm = game_engine._get_npc_name(n).strip()
        if nm and nm.lower() == q_low:
            return nm
    if q_low in party_names:
        return None
    matches = []
    for n in present_list:
        nm = game_engine._get_npc_name(n).strip()
        if nm and game_engine.is_dialogue_partner(nm, [q]):
            matches.append(nm)
    if len(matches) == 1:
        return matches[0]
    return None


def apply_cast_events(
    plan: CastPlan,
    cast_events: list,
    session: dict,
    party: list,
    stage_info: Optional[dict] = None,
    persist_db: bool = True,
    narrative_text: Optional[str] = None,
) -> Tuple[CastPlan, List[Dict[str, Any]]]:
    """
    Arbitrates narrative-suggested cast_events against deterministic rules (D4 & D16).

    When ``narrative_text`` is provided, brand-new open-world arrivals must be grounded in the
    narration (named outside quoted dialogue, or matched by descriptor as physically acting),
    or be pre-confirmed by the stage-plan contract check (``_contract_confirmed``).
    
    Returns (final_plan, rejected_events_list).
    """
    if not cast_events:
        return plan, []

    history = session.get("history") or []
    current_turn_index = len(history) if history else int(session.get("current_turn_index") or 0)
    cast_state = get_cast_state(session)
    disengaged_at_turn = cast_state.get("disengaged_at_turn", {})

    sess_id = session.get("id")
    scen_key = str(session.get("scenario") or "fantasy")
    curr_node = str((stage_info or {}).get("effective_node_id") or session.get("current_node_id") or "")
    curr_loc = str((stage_info or {}).get("effective_location") or session.get("current_location") or "")
    eff_day = int(session.get("_staged_day") or session.get("current_day") or 1)
    eff_min = int(
        session.get("_staged_minute")
        if session.get("_staged_minute") is not None
        else (session.get("current_minute") if session.get("current_minute") is not None else 480)
    )
    eff_slot = str(session.get("_staged_time_slot") or session.get("time_slot") or "")

    party_names = {
        (p[0].get("name", "").strip().lower() if isinstance(p, (tuple, list)) and isinstance(p[0], dict) else "")
        for p in (party or [])
    }

    # Fetch active appointments & commitments in-window at current node/location
    active_appt_npcs = set()
    if sess_id:
        try:
            from mechanics.system.commitments_engine import get_active_rendezvous_at_node
            probes = [p for p in (curr_node, curr_loc) if p]
            for loc_probe in probes:
                rdvs = get_active_rendezvous_at_node(sess_id, loc_probe, current_day=eff_day, current_minute=eff_min)
                for r in (rdvs or []):
                    for p in (r.get("participants") or []):
                        if isinstance(p, dict):
                            p_nm = str(p.get("name") or p.get("npc_name") or "").strip().lower()
                            p_id = str(p.get("npc_id") or p.get("person_key") or "").strip().lower()
                            if p_nm and p_nm != "player":
                                active_appt_npcs.add(p_nm)
                            if p_id and p_id != "player" and not p_id.startswith("player:"):
                                active_appt_npcs.add(p_id.replace("_", " "))
                    for k in ("npc_name", "target_npc", "target_entity"):
                        rn = str(r.get(k) or "").strip().lower()
                        if rn and rn not in ("player", "group"):
                            active_appt_npcs.add(rn.replace("_", " ") if "_" in rn else rn)
        except Exception:
            pass

    # Closed-world blocked residents from Tier 4 doorbell evaluation
    doorbell_blocked_lows = set()
    for dbell in ((stage_info or {}).get("doorbell_events") or []):
        if isinstance(dbell, dict) and dbell.get("applicable") and not dbell.get("allowed"):
            for dk in (dbell.get("name"), dbell.get("npc_id")):
                if dk:
                    doorbell_blocked_lows.add(str(dk).strip().lower())

    staged_allowed_low = set()
    for st_n in ((stage_info or {}).get("stage_npcs") or []) + (plan.present_npcs or []):
        st_nm = game_engine._get_npc_name(st_n).strip().lower()
        if st_nm:
            staged_allowed_low.add(st_nm)

    # Build lookup of known contacts, closed-world roster, folklore roster & legacy rosters
    known_npcs_by_low: Dict[str, dict] = {}
    if sess_id:
        try:
            for c_rec in (db.get_contacts(sess_id, ensure_scene=False) or []):
                cn = str(c_rec.get("name") or "").strip()
                if cn:
                    known_npcs_by_low[cn.lower()] = c_rec
        except Exception:
            pass
        try:
            for wr in (db.get_world_roster(sess_id, include_legacy_rosters=False) or []):
                wn = str(wr.get("name") or "").strip()
                if wn and wn.lower() not in known_npcs_by_low:
                    known_npcs_by_low[wn.lower()] = wr
        except Exception:
            pass
        _fk_list = session.get("folklore_villager_roster")
        if _fk_list is None:
            _sess_fk = db.get_session(sess_id) or {}
            _fk_list = _sess_fk.get("folklore_villager_roster") or []
        for fv in (_fk_list or []):
            if isinstance(fv, dict):
                fn = str(fv.get("name") or "").strip()
                if fn and fn.lower() not in known_npcs_by_low:
                    known_npcs_by_low[fn.lower()] = fv
        try:
            for fac in (db.get_factions(sess_id) or []):
                for mem in (fac.get("leadership_roster") or []):
                    mn = str(mem.get("name") or "").strip()
                    if mn and not mem.get("is_player") and mn.lower() not in known_npcs_by_low:
                        known_npcs_by_low[mn.lower()] = mem
        except Exception:
            pass
        try:
            for sr in (db.get_school_roster(sess_id) or []):
                sn = str(sr.get("name") or "").strip()
                if sn and sn.lower() not in known_npcs_by_low:
                    known_npcs_by_low[sn.lower()] = sr
        except Exception:
            pass
        try:
            for ar in (db.get_anomalous_agent_roster(sess_id) or []):
                an = str(ar.get("name") or "").strip()
                if an and an.lower() not in known_npcs_by_low:
                    known_npcs_by_low[an.lower()] = ar
        except Exception:
            pass
    for st_n in ((stage_info or {}).get("stage_npcs") or []):
        if isinstance(st_n, dict) and st_n.get("name"):
            sn_low = str(st_n["name"]).strip().lower()
            if sn_low not in known_npcs_by_low:
                known_npcs_by_low[sn_low] = st_n

    # Determine room privacy for private-room gating
    is_private_room = False
    if sess_id and curr_node:
        try:
            wn = db.get_world_node(sess_id, curr_node)
            if wn and str(wn.get("privacy_level") or "").lower() == "private":
                is_private_room = True
        except Exception:
            pass
    if not is_private_room and curr_loc:
        try:
            from mechanics.social.physical_state import is_private_intimate_venue
            if is_private_intimate_venue(curr_loc, node_id=str(curr_node or ""), session_id=int(sess_id or 0)):
                is_private_room = True
        except Exception:
            pass

    rejections: List[Dict[str, Any]] = []
    updated_present = list(plan.present_npcs)
    updated_partners = list(plan.dialogue_partners)
    updated_departures = list(plan.departing_npcs)

    from mechanics.world.npc_schedule import get_npc_scheduled_location
    from mechanics.world import resolve_anchor_schedule_nodes, is_npc_on_active_shift
    from mechanics.world.schedule_blocks import get_time_block_key

    curr_block = get_time_block_key(eff_min)

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

        # ── EVENT: ARRIVE (Closed-World: Schedule / Appointment / Staged / Party only) ──
        if ev_type == "arrive":
            known_rec = known_npcs_by_low.get(npc_low)
            if known_rec is None and sess_id:
                try:
                    known_rec = db.get_contact(sess_id, npc_low.replace(" ", "_"), 0)
                except Exception:
                    known_rec = None

            if npc_low in doorbell_blocked_lows and npc_low not in active_appt_npcs and npc_low not in party_names:
                rej = {
                    "type": "arrive",
                    "npc": npc_name,
                    "reason": f"Resident '{npc_name}' blocked by doorbell etiquette.",
                }
                rejections.append(rej)
                logger.warning("[CastPlanner] Rejected doorbell-blocked arrive: %s", rej)
                continue

            is_staged_here = npc_low in staged_allowed_low
            has_appt_here = npc_low in active_appt_npcs
            is_party_here = npc_low in party_names
            is_scheduled_here = False

            if not (has_appt_here or is_staged_here or is_party_here) and known_rec is not None:
                if str(known_rec.get("origin") or "").lower() not in ("", "legacy_adapter") and str(known_rec.get("staff_status") or "active").lower() == "active":
                    try:
                        a_map = resolve_anchor_schedule_nodes(
                            known_rec,
                            current_day=eff_day,
                            scen_key=scen_key,
                            session_id=sess_id,
                            current_minute=eff_min,
                        )
                        on_shift, work_nid = is_npc_on_active_shift(
                            known_rec, eff_min, current_day=eff_day, scen_key=scen_key, session_id=sess_id
                        )
                        sched_nid = str((a_map or {}).get(curr_block) or "").strip()
                        for cand_nid in (work_nid if on_shift else "", sched_nid):
                            if cand_nid and curr_node and (
                                cand_nid == curr_node
                                or (sess_id and (db.is_descendant_of(sess_id, curr_node, cand_nid) or db.is_descendant_of(sess_id, cand_nid, curr_node)))
                            ):
                                is_scheduled_here = True
                                break
                    except Exception:
                        pass
                if not is_scheduled_here:
                    try:
                        sched_loc = get_npc_scheduled_location(
                            known_rec,
                            current_minute=eff_min,
                            scen_key=scen_key,
                            time_slot=eff_slot,
                            session_id=sess_id,
                            current_day=eff_day,
                        )
                    except Exception:
                        sched_loc = ""
                    if not sched_loc:
                        sched_loc = str(
                            known_rec.get("location")
                            or (known_rec.get("basic_info") or {}).get("location")
                            or ""
                        )
                    if sched_loc and _locations_overlap(sched_loc, curr_loc):
                        is_scheduled_here = True

            if is_private_room and not (is_staged_here or has_appt_here or is_party_here):
                is_scheduled_here = False

            if is_staged_here or has_appt_here or is_party_here or is_scheduled_here:
                arrival_meta: Dict[str, Any] = {}
                for meta_key in ("gender", "descriptor", "role"):
                    meta_val = ev.get(meta_key)
                    if isinstance(meta_val, str) and meta_val.strip():
                        arrival_meta[meta_key] = meta_val.strip()
                if not any(game_engine._get_npc_name(n).strip().lower() == npc_low for n in updated_present):
                    updated_present.append({"name": npc_name, "stage_role": "room_bystander", **arrival_meta})
                    logger.info("[CastPlanner] Approved cast event arrive: '%s' (%s)", npc_name, reason)
            else:
                rej = {
                    "type": "arrive",
                    "npc": npc_name,
                    "reason": (
                        f"Known NPC '{npc_name}' is scheduled elsewhere without an active appointment here."
                        if known_rec is not None
                        else f"Unscheduled/unseeded NPC '{npc_name}' arrival rejected under closed-world cast closure."
                    ),
                }
                rejections.append(rej)
                logger.warning("[CastPlanner] Rejected cast event arrive: %s", rej)

        # ── EVENT: DEPART ────────────────────────────────────────────────────
        elif ev_type == "depart":
            resolved_depart = _resolve_present_npc_name(npc_name, updated_present, party_names) or npc_name
            dep_low = resolved_depart.lower()
            if npc_low in party_names or dep_low in party_names:
                rej = {
                    "type": "depart",
                    "npc": npc_name,
                    "reason": f"Party member '{npc_name}' cannot depart via ambient cast event.",
                }
                rejections.append(rej)
                logger.warning("[CastPlanner] Rejected cast event depart: %s", rej)
            elif npc_low in active_appt_npcs or dep_low in active_appt_npcs:
                rej = {
                    "type": "depart",
                    "npc": npc_name,
                    "reason": f"Appointment target '{npc_name}' cannot depart while meetup is active.",
                }
                rejections.append(rej)
                logger.warning("[CastPlanner] Rejected cast event depart: %s", rej)
            else:
                if resolved_depart not in updated_departures:
                    updated_departures.append(resolved_depart)
                disengaged_at_turn[dep_low] = current_turn_index
                updated_present = [n for n in updated_present if game_engine._get_npc_name(n).strip().lower() != dep_low]
                updated_partners = [p for p in updated_partners if p.strip().lower() != dep_low]
                logger.info("[CastPlanner] Approved cast event depart: '%s' (%s)", resolved_depart, reason)

        # ── EVENT: ENGAGE (D16 Stealth Shield + Explicit Exit Block + 2-Turn Re-engage Cooldown) ───
        elif ev_type == "engage":
            if plan.has_exited_convo:
                rej = {
                    "type": "engage",
                    "npc": npc_name,
                    "reason": f"Player explicitly exited conversation this turn; '{npc_name}' cannot re-engage.",
                }
                rejections.append(rej)
                logger.warning("[CastPlanner] Rejected cast event engage on explicit dialogue exit: %s", rej)
                continue
            if plan.stealth_active:
                rej = {
                    "type": "engage",
                    "npc": npc_name,
                    "reason": f"Player is hidden in active stealth; '{npc_name}' cannot initiate conversation.",
                }
                rejections.append(rej)
                logger.warning("[CastPlanner] Rejected cast event engage under stealth: %s", rej)
                continue

            matched_name = _resolve_present_npc_name(npc_name, updated_present, party_names)
            if not matched_name:
                rej = {
                    "type": "engage",
                    "npc": npc_name,
                    "reason": f"NPC '{npc_name}' is not physically present in the room.",
                }
                rejections.append(rej)
                logger.warning("[CastPlanner] Rejected cast event engage: %s", rej)
                continue

            matched_low = matched_name.lower()
            matched_ent = next(
                (n for n in updated_present if isinstance(n, dict) and game_engine._get_npc_name(n).strip().lower() == matched_low),
                None,
            )
            if isinstance(matched_ent, dict) and matched_ent.get("is_anomalous_entity") and matched_ent.get("talkable") is False:
                rej = {
                    "type": "engage",
                    "npc": matched_name,
                    "reason": f"Anomalous entity '{matched_name}' is non-sapient/instinctual and cannot engage in verbal dialogue.",
                }
                rejections.append(rej)
                continue
            last_disengage = disengaged_at_turn.get(matched_low, disengaged_at_turn.get(npc_low, -999))
            if (current_turn_index - last_disengage) < 2:
                rej = {
                    "type": "engage",
                    "npc": matched_name,
                    "reason": f"Re-engage cooldown active for '{matched_name}' (ended conversation {current_turn_index - last_disengage} turns ago; requires 2 turns).",
                }
                rejections.append(rej)
                logger.warning("[CastPlanner] Rejected cast event engage: %s", rej)
            else:
                if matched_name not in updated_partners:
                    updated_partners.append(matched_name)
                logger.info("[CastPlanner] Approved cast event engage: '%s' (%s)", matched_name, reason)

    partner_lowers = {p.strip().lower() for p in updated_partners}
    departing_lowers = {d.strip().lower() for d in updated_departures}
    updated_bystanders = [
        game_engine._get_npc_name(n).strip()
        for n in updated_present
        if game_engine._get_npc_name(n).strip().lower() not in partner_lowers
        and game_engine._get_npc_name(n).strip().lower() not in departing_lowers
    ]

    cast_state["disengaged_at_turn"] = disengaged_at_turn
    save_cast_state(session, cast_state, persist_db=persist_db)

    final_plan = CastPlan(
        present_npcs=updated_present,
        dialogue_partners=updated_partners,
        bystander_npcs=updated_bystanders,
        departing_npcs=updated_departures,
        rejections=rejections,
        has_exited_convo=plan.has_exited_convo,
        stealth_active=plan.stealth_active,
    )
    return final_plan, rejections
