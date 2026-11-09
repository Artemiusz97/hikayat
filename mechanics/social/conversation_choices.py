from __future__ import annotations

"""Deterministic 4-Band Conversation Choice Engine & Departure Facade.

Enforces the 4-Band Conversation Choice Architecture (<= 8 options total):
  1. Band 1 — Quest / Investigation (0-2 slots): ONLY when an active quest, bounty,
     discovered world rumor ([Break the News] / clue press), or claimed minor event applies.
  2. Band 2 — Dynamic Social Suite (4-6 slots, elastically flexing down when utilities stack):
     7-SPECIAL, fixed DC 3-12 Sims-style topics, milestones (Ask on Date / Confess), and ambient gossip.
  3. Band 3 — Pre-Exit Structural Utilities (pinned immediately above Exit):
     Recruit to Party, Move to Quieter Spot / Walk Together, Ask for Contact Info, Convince to Stay.
  4. Band 4 — Pinned Exit (1 final slot): Standardized FREE 'Leave conversation...'.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import db
import namegen
import scenario_data
from mechanics.social import deck, pacing
from mechanics.social.band_fallbacks import (
    _PRONOUNS_BY_GENDER,
    _build_contextual_role_and_leisure_phrases,
    _is_similar_to_recent,
    generate_band1_quest_and_rumor_fallbacks as _gen_b1_impl,
    generate_band2_social_choices as _gen_b2_impl,
    resolve_partner_pronouns,
    sanitize_contextual_dialogue_label,
    synthesize_choice_from_seed,
)
from mechanics.social.departure import (
    _CONVINCE_STAY_RE,
    _apply_stage1_hurry_gate,
    _canon_npc_key,
    _locations_match,
    get_npc_departure_states,
    is_convince_stay_action,
    relocate_departed_npcs_impl,
    run_departure_turn_evaluation,
    save_npc_departure_states,
)
from mechanics.social.relationships import (
    clamp_score,
    get_disclosure_check_requirement,
    get_relationship_tier,
)

log = logging.getLogger(__name__)

SPECIAL_STATS_SET = frozenset({"STR", "PER", "END", "CHA", "INT", "AGI", "LUK"})

_WALK_WITH_RE = re.compile(
    r"^\s*(?:walk\s+with|stroll\s+with|accompany|go\s+with|head\s+(?:out\s+|over\s+)?with|tag\s+along\s+with|escort)\s+(.+)$",
    re.IGNORECASE,
)

_ROMANTIC_ADVANCE_RE = re.compile(
    r"\b(?:flirt\s+with|wink\s+at|seductive|whisper\s+flirtatiously|"
    r"brush\s+(?:her|his|their)\s+(?:her|his|their|hand|cheek|hair|lips)|"
    r"hold\s+(?:her|his|their)\s+hand|pull\s+(?:her|him|them)\s+close)\b",
    re.IGNORECASE,
)

_OPENING_GREETING_RE = re.compile(
    r"^\s*(?:[^\w\s]\s*)*(?:speak\s+with|talk\s+to|talk\s+with|greet|approach|hail|"
    r"check\s+in\s+with|strike\s+up\s+a\s+conversation\s+with|wave\s+(?:over\s+)?to)\s+[^,.;!?]+[.!]?\s*$",
    re.IGNORECASE,
)

_BOLD_SOCIAL_CHECK_RE = re.compile(
    r"\b(?:phone\s+number|contact\s+info|line\s+id|confess\s+(?:your\s+)?feelings|"
    r"pursue\s+a\s+romantic|ask\s+(?:her|him|them|[A-Z][a-z]+)\s+out\s+on\s+a\s+date|"
    r"pry\s+into|press\s+(?:her|him|them)\s+(?:for|about)\s+(?:her|his|their)\s+secret|"
    r"deepest\s+secret|intimate\s+preference|turn-on|fetish|sensitive\s+spot|"
    r"flirt\s+with|kiss\s+|arm-wrestle|friendly\s+wager|challenge\s+)\b",
    re.IGNORECASE,
)


def get_npc_conversation_ledgers(session: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Returns per-day, per-NPC conversation ledger map from session."""
    if not isinstance(session, dict):
        return {}
    raw = session.get("npc_conversation_ledgers")
    if not isinstance(raw, dict):
        extra = session.get("extra")
        if isinstance(extra, dict) and isinstance(extra.get("npc_conversation_ledgers"), dict):
            raw = extra["npc_conversation_ledgers"]
    if not isinstance(raw, dict):
        return {}
    return {str(k): dict(v) for k, v in raw.items() if k and isinstance(v, dict)}


def save_npc_conversation_ledgers(
    session: Optional[Dict[str, Any]],
    ledgers: Dict[str, Dict[str, Any]],
    persist_db: bool = True,
) -> None:
    """Synchronizes npc_conversation_ledgers onto session and persists to SQLite extra_json."""
    clean = {str(k): dict(v) for k, v in (ledgers or {}).items() if k and isinstance(v, dict)}
    if isinstance(session, dict):
        session["npc_conversation_ledgers"] = clean
        if not isinstance(session.get("extra"), dict):
            session["extra"] = {}
        session["extra"]["npc_conversation_ledgers"] = clean
        sess_id = session.get("id")
        if persist_db and sess_id:
            try:
                db.update_session(int(sess_id), extra={"npc_conversation_ledgers": clean})
            except Exception as e:
                log.warning("Failed persisting npc_conversation_ledgers: %s", e)


def compute_base_conversation_budget(profile: Dict[str, Any]) -> int:
    """Computes affinity-scaled daily non-quest conversation turn budget."""
    if bool(profile.get("is_private_meetup")):
        return 9
    score = int(profile.get("score", 0))
    track = str(profile.get("track") or "platonic").strip().lower()
    if score >= 150 or track == "romantic":
        return 9
    if score >= 100:
        return 7
    if score >= 50:
        return 5
    if score >= 0:
        return 3
    return 2


def _extract_topic_signature(label: str, choice: Optional[Dict[str, Any]] = None) -> str:
    if isinstance(choice, dict) and choice.get("topic_id"):
        return str(choice["topic_id"]).strip()
    lbl_low = str(label or "").strip().lower()
    if not lbl_low:
        return ""
    if any(k in lbl_low for k in ("phone number", "contact info", "line id")):
        return "contact_exchange"
    if any(k in lbl_low for k in ("work as ", "role in ", "role as ", "duty as ", "current assignment", "career path")):
        return "work_role"
    if any(k in lbl_low for k in ("off duty", "off-duty", "free time", "outside of work", "hobby", "hobbies", "enjoy doing")):
        return "hobbies_offduty"
    if any(k in lbl_low for k in ("favorite spot", "favourite spot", "grab a bite", "unwind around", "favorite food")):
        return "favorite_spot_food"
    if any(k in lbl_low for k in ("proudest", "personal story", "what inspired", "what got", "hometown", "childhood")):
        return "personal_story"
    if any(k in lbl_low for k in ("holding up", "day is going", "on their mind")):
        return "day_checkin"
    if any(k in lbl_low for k in ("walk with ", "stroll with ", "accompany ")):
        return "walk_together"
    if "clear the air" in lbl_low:
        return "clear_air"
    return ""


def get_partner_conversation_budget_state(
    session: Optional[Dict[str, Any]],
    profile: Dict[str, Any],
) -> Dict[str, Any]:
    sess = session if isinstance(session, dict) else {}
    curr_day = int(sess.get("current_day") or 1)
    curr_min = int(sess.get("current_minute") if sess.get("current_minute") is not None else 480)
    from mechanics.world.schedules import get_time_block_key

    curr_blk = get_time_block_key(curr_min)
    partner_name = str(profile.get("name") or "").strip()
    l_key = f"{curr_day}:{_canon_npc_key(partner_name)}"
    ledgers = get_npc_conversation_ledgers(sess)
    entry = dict(ledgers.get(l_key) or {})

    base_budget = compute_base_conversation_budget(profile)
    turns_used = int(entry.get("turns_used") or 0)
    bonus_turns = int(entry.get("bonus_turns") or 0)
    last_blk = str(entry.get("last_time_block") or "")
    rechecked = list(entry.get("rechecked_blocks") or [])
    is_meetup = bool(profile.get("is_private_meetup"))
    meetup_loc = str(profile.get("meetup_location") or sess.get("current_location") or "meetup").strip().lower()
    meetup_key = f"{curr_day}:meetup:{meetup_loc}"

    if is_meetup and entry.get("active_meetup_key") != meetup_key:
        turns_used = 0
        bonus_turns = 0
    elif last_blk and last_blk != curr_blk and curr_blk not in rechecked:
        bonus_turns += 2

    remaining = max(0, base_budget + bonus_turns - turns_used)
    return {
        "ledger_key": l_key,
        "base_budget": base_budget,
        "bonus_turns": bonus_turns,
        "turns_used": turns_used,
        "remaining_budget": remaining,
        "is_exhausted": (base_budget + bonus_turns - turns_used) <= 0,
        "asked_labels": [str(x).strip().lower() for x in (entry.get("asked_labels") or []) if str(x).strip()],
        "asked_topic_signatures": [str(x).strip() for x in (entry.get("asked_topic_signatures") or []) if str(x).strip()],
        "current_block": curr_blk,
        "meetup_key": meetup_key if is_meetup else "",
    }


def is_non_quest_social_turn_action(
    action_dict: Dict[str, Any],
    was_already_partner: bool = True,
) -> bool:
    if not isinstance(action_dict, dict):
        return False
    lbl = str(action_dict.get("label") or action_dict.get("text") or action_dict.get("action") or "").strip()
    if not lbl:
        return False
    lbl_low = lbl.lower()
    intent = str(action_dict.get("intent") or "").lower()
    if (
        action_dict.get("_pinned_dialogue_exit")
        or action_dict.get("is_anomaly_inquiry")
        or str(action_dict.get("approach") or "").startswith("anomaly_inquiry")
        or intent in ("dialogue_exit", "movement", "rest_sleep", "gift_offer", "anomalous_incursion_action")
        or action_dict.get("ends_dialogue")
        or action_dict.get("dismisses_npc")
        or action_dict.get("_convince_stay")
        or action_dict.get("item_name")
    ):
        return False
    from mechanics.narrative.intent import is_conversational_exit

    if is_conversational_exit(lbl):
        return False
    if (
        action_dict.get("is_quest_action")
        or action_dict.get("quest_id")
        or action_dict.get("clue_pair_ids")
        or action_dict.get("is_climax_action")
        or action_dict.get("is_story_quest")
        or action_dict.get("_active_quest_inquiry")
        or action_dict.get("_is_world_rumor_inquiry")
        or action_dict.get("_is_break_the_news")
        or str(action_dict.get("linked_quest_id") or "").upper().startswith("MNR-")
        or str(action_dict.get("quest_id") or "").upper().startswith("MNR-")
    ):
        return False
    if not was_already_partner and _OPENING_GREETING_RE.match(lbl) and " about " not in lbl_low:
        return False
    return True


def record_partner_conversation_turn(
    session: Optional[Dict[str, Any]],
    partner_name: str,
    actions: Optional[List[Any]],
    party: Optional[List[Any]] = None,
    current_npcs: Optional[List[Any]] = None,
    was_already_partner: bool = True,
    persist_db: bool = True,
) -> Dict[str, Any]:
    if not isinstance(session, dict) or not partner_name:
        return {}
    try:
        from mechanics.world.anomalous_events import is_anomalous_scene_entity
        if is_anomalous_scene_entity(partner_name, session=session, current_npcs=current_npcs):
            return {}
    except Exception:
        pass
    profile = resolve_partner_conversation_profile(session, partner_name, party=party, current_npcs=current_npcs)
    curr_day = int(session.get("current_day") or 1)
    curr_min = int(session.get("current_minute") if session.get("current_minute") is not None else 480)
    from mechanics.world.schedules import get_time_block_key

    curr_blk = get_time_block_key(curr_min)
    l_key = f"{curr_day}:{_canon_npc_key(partner_name)}"
    ledgers = get_npc_conversation_ledgers(session)
    entry = dict(ledgers.get(l_key) or {
        "turns_used": 0,
        "bonus_turns": 0,
        "last_time_block": "",
        "rechecked_blocks": [],
        "active_meetup_key": "",
        "asked_labels": [],
        "asked_topic_signatures": [],
    })

    is_meetup = bool(profile.get("is_private_meetup"))
    meetup_loc = str(profile.get("meetup_location") or session.get("current_location") or "meetup").strip().lower()
    meetup_key = f"{curr_day}:meetup:{meetup_loc}"
    if is_meetup and entry.get("active_meetup_key") != meetup_key:
        entry["turns_used"] = 0
        entry["bonus_turns"] = 0
        entry["active_meetup_key"] = meetup_key
    else:
        last_blk = str(entry.get("last_time_block") or "")
        rechecked = list(entry.get("rechecked_blocks") or [])
        if last_blk and last_blk != curr_blk and curr_blk not in rechecked:
            entry["bonus_turns"] = int(entry.get("bonus_turns") or 0) + 2
            rechecked.append(curr_blk)
            entry["rechecked_blocks"] = rechecked

    asked_labels = [str(x).strip().lower() for x in (entry.get("asked_labels") or []) if str(x).strip()]
    asked_sigs = [str(x).strip() for x in (entry.get("asked_topic_signatures") or []) if str(x).strip()]
    pre_base = compute_base_conversation_budget(profile)
    pre_rem = pre_base + int(entry.get("bonus_turns") or 0) - int(entry.get("turns_used") or 0)

    consumed_budget = False
    for a in (actions or []):
        if not isinstance(a, dict):
            continue
        lbl = str(a.get("label") or a.get("text") or a.get("action") or "").strip()
        lbl_low = lbl.lower()
        if not lbl_low:
            continue
        if not _OPENING_GREETING_RE.match(lbl) or " about " in lbl_low:
            if lbl_low not in asked_labels:
                asked_labels.append(lbl_low)
            sig = str(a.get("_topic_sig") or _extract_topic_signature(lbl, a) or "").strip()
            if sig and sig != "contact_exchange" and sig not in asked_sigs:
                asked_sigs.append(sig)
        if is_non_quest_social_turn_action(a, was_already_partner=was_already_partner):
            if pre_rem <= 0:
                a["_post_budget_zero_affinity"] = True
            else:
                a["_within_social_budget"] = True
            if not consumed_budget:
                entry["turns_used"] = int(entry.get("turns_used") or 0) + 1
                consumed_budget = True

    entry["last_time_block"] = curr_blk
    entry["asked_labels"] = asked_labels[-40:]
    entry["asked_topic_signatures"] = asked_sigs[-30:]
    ledgers[l_key] = entry
    save_npc_conversation_ledgers(session, ledgers, persist_db=persist_db)
    return get_partner_conversation_budget_state(session, profile)


def _find_contact_and_lore(
    session_id: Optional[int],
    partner_name: str,
    char_id: int = 0,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    contact: Optional[Dict[str, Any]] = None
    lore_ent: Dict[str, Any] = {}
    if not session_id or not partner_name:
        return None, {}
    p_clean = str(partner_name).strip()
    p_low = p_clean.lower()
    p_slug = p_low.replace(" ", "_")
    try:
        contact = db.get_contact(session_id, p_clean, char_id) or db.get_contact(session_id, p_slug, char_id)
        if not contact:
            for c_row in (db.get_contacts(session_id, char_id) or db.get_contacts(session_id) or []):
                if str(c_row.get("name") or "").strip().lower() == p_low or str(c_row.get("npc_id") or "").strip().lower() in (p_low, p_slug):
                    contact = c_row
                    break
    except Exception:
        contact = None

    try:
        l_row = db.get_lorebook_entity(session_id, p_clean)
        if isinstance(l_row, dict):
            lore_ent = l_row
        else:
            lb = db.get_lorebook(session_id) or {}
            for p_ent in (lb.get("person") or []):
                if isinstance(p_ent, dict) and str(p_ent.get("name") or "").strip().lower() == p_low:
                    lore_ent = p_ent
                    break
    except Exception:
        lore_ent = {}
    return contact, lore_ent


def resolve_partner_conversation_profile(
    session: Optional[Dict[str, Any]],
    partner_name: str,
    party: Optional[List[Any]] = None,
    current_npcs: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """Computes relationship tier, scene meetup/companion flags, home/office check, and quest hooks."""
    sess = session if isinstance(session, dict) else {}
    session_id = sess.get("id")
    scen_key = str(sess.get("scenario") or "fantasy")
    curr_loc = str(sess.get("current_location") or "")
    curr_nid = str(sess.get("current_node_id") or "")
    curr_day = int(sess.get("current_day") or 1)
    curr_min = int(sess.get("current_minute") if sess.get("current_minute") is not None else 480)

    char_id = 0
    if party and isinstance(party, list) and party[0]:
        lead = party[0][0] if isinstance(party[0], (tuple, list)) else party[0]
        if isinstance(lead, dict):
            char_id = int(lead.get("id") or 0)

    contact, lore_ent = _find_contact_and_lore(session_id, partner_name, char_id=char_id)
    npc_scene_obj: Dict[str, Any] = {}
    for n in (current_npcs or sess.get("current_npcs") or []):
        if isinstance(n, dict) and str(n.get("name") or "").strip().lower() == str(partner_name or "").strip().lower():
            npc_scene_obj = n
            break

    score = clamp_score(int((contact or {}).get("relationship_score") or 0))
    track = str((contact or {}).get("track") or "platonic").strip().lower()
    tier_obj = get_relationship_tier(score, track=track, scenario=scen_key)
    tier_level = int(tier_obj.get("tier_level", 0))
    tier_name = str(tier_obj.get("name") or "Stranger")

    b_info = ((contact or {}).get("basic_info") or {}) if isinstance((contact or {}).get("basic_info"), dict) else {}
    role = str(
        npc_scene_obj.get("role")
        or b_info.get("role")
        or b_info.get("occupation")
        or (contact or {}).get("role")
        or lore_ent.get("role")
        or lore_ent.get("occupation")
        or ""
    ).strip()
    faction = str(
        npc_scene_obj.get("faction")
        or b_info.get("faction")
        or b_info.get("club")
        or lore_ent.get("faction")
        or ""
    ).strip()

    p_low = str(partner_name or "").strip().lower()
    p_first = namegen.extract_first_and_last_name(partner_name)[0].strip().lower() if partner_name else ""
    p_last = namegen.extract_first_and_last_name(partner_name)[1].strip().lower() if partner_name else ""

    is_party_member = False
    is_temp_companion = False
    for pm in (sess.get("party_npcs") or []):
        if isinstance(pm, dict) and str(pm.get("name") or "").strip().lower() == p_low:
            is_party_member = True
            break
    if not is_party_member and session_id:
        try:
            for pm in (db.get_session_party_npcs(session_id) or []):
                if isinstance(pm, dict) and str(pm.get("name") or "").strip().lower() == p_low:
                    is_party_member = True
                    break
        except Exception:
            pass

    for tc in (sess.get("temporary_companions") or []):
        if isinstance(tc, dict) and str(tc.get("name") or "").strip().lower() == p_low:
            is_temp_companion = True
            break
    if not is_temp_companion and session_id:
        try:
            for tc in (db.get_temporary_companions(session_id) or []):
                if isinstance(tc, dict) and str(tc.get("name") or "").strip().lower() == p_low:
                    is_temp_companion = True
                    break
        except Exception:
            pass
    is_companion = bool(is_party_member or is_temp_companion)

    is_private_meetup = False
    meetup_location = ""
    has_other_commitment_loc = ""
    if session_id:
        try:
            for st_k in ("pending", "arrived", "in_progress"):
                for appt in (db.get_phone_appointments(session_id, status=st_k) or []):
                    an = str(appt.get("npc_name") or appt.get("npc_id") or "").strip().lower()
                    if an and (an == p_low or an == p_low.replace(" ", "_")):
                        r_loc = str(appt.get("rendezvous_location") or appt.get("location") or "").strip()
                        if not r_loc or _locations_match(curr_loc, r_loc, session_id=session_id):
                            is_private_meetup = True
                            meetup_location = r_loc or curr_loc
                        elif r_loc:
                            has_other_commitment_loc = r_loc
        except Exception:
            pass

        try:
            from mechanics.system.commitments_engine import get_active_commitments
            for cm in (get_active_commitments(session_id, npc_key=partner_name) or []):
                if str(cm.get("commitment_type") or "") == "rendezvous":
                    cm_loc = str(cm.get("location") or cm.get("target_location") or "").strip()
                    cm_nid = str(cm.get("node_id") or cm.get("target_node_id") or "").strip()
                    participants = [str(x).lower() for x in (cm.get("participants") or [])]
                    involves_player = "player" in participants or not participants
                    if involves_player and (
                        (cm_nid and curr_nid and _locations_match("", "", session_id=session_id, node_a=curr_nid, node_b=cm_nid))
                        or (cm_loc and _locations_match(curr_loc, cm_loc, session_id=session_id))
                    ):
                        is_private_meetup = True
                        meetup_location = cm_loc or curr_loc
                    elif not involves_player and cm_loc and not _locations_match(curr_loc, cm_loc, session_id=session_id):
                        has_other_commitment_loc = cm_loc
        except Exception:
            pass

    is_npc_home_or_office = False
    loc_low = curr_loc.lower()
    home_loc = str(b_info.get("residence") or b_info.get("home_location") or b_info.get("residence_location") or "").strip()
    if home_loc and _locations_match(curr_loc, home_loc, session_id=session_id):
        is_npc_home_or_office = True
    if not is_npc_home_or_office:
        for tok in (p_low, p_first, p_last):
            if tok and len(tok) >= 3 and re.search(
                rf"\b{re.escape(tok)}(?:'s|s')\s+(?:room|bedroom|apartment|home|house|dorm|suite|quarters|office|study|residence)\b",
                loc_low,
            ):
                is_npc_home_or_office = True
                break
    if not is_npc_home_or_office and session_id:
        try:
            from mechanics.world.npc_schedule import get_npc_schedule
            npc_ref = contact or npc_scene_obj or {"name": partner_name, "role": role}
            sched_map = get_npc_schedule(npc_ref, scen_key=scen_key, session_id=session_id, current_day=curr_day, current_minute=curr_min)
            night_home = str((sched_map or {}).get("night") or "").strip()
            if night_home and any(
                w in loc_low for w in ("bedroom", "apartment", "residence", "dorm", "house", "quarters", "suite")
            ) and _locations_match(curr_loc, night_home, session_id=session_id):
                is_npc_home_or_office = True
        except Exception:
            pass

    is_quest_stationed_here = False
    relevant_quests: List[Dict[str, Any]] = []
    if session_id:
        try:
            for wp in (db.get_all_session_active_waypoints(session_id) or []):
                wp_npc = str(wp.get("target_npc") or "").strip().lower()
                wp_loc = str(wp.get("target_location") or wp.get("location") or "").strip()
                if wp_npc and (wp_npc == p_low or (p_first and len(p_first) >= 3 and p_first in wp_npc)):
                    relevant_quests.append(wp)
                    if not wp_loc or _locations_match(curr_loc, wp_loc, session_id=session_id):
                        is_quest_stationed_here = True
                elif wp_loc and _locations_match(curr_loc, wp_loc, session_id=session_id):
                    relevant_quests.append(wp)
        except Exception:
            pass

    can_walk_together = bool(is_private_meetup or is_companion or score >= 100 or track == "romantic")
    convince_stay_dc = 6 if (score >= 100 or track == "romantic") else (9 if score >= 50 else 12)

    traits_list: List[str] = []
    for t_cand in ((contact or {}).get("traits") or b_info.get("traits") or lore_ent.get("traits") or []):
        t_str = str(t_cand or "").strip()
        if t_str and len(t_str) <= 36 and "???" not in t_str and t_str not in traits_list:
            traits_list.append(t_str)

    prefs_obj = ((contact or {}).get("preferences") or {}) if isinstance((contact or {}).get("preferences"), dict) else {}
    likes_list: List[str] = []
    for raw_lk in (prefs_obj.get("likes") or prefs_obj.get("hobbies") or b_info.get("hobbies") or b_info.get("likes") or []):
        lk_str = str(raw_lk or "").strip()
        if lk_str and len(lk_str) <= 44 and "???" not in lk_str and lk_str not in likes_list:
            likes_list.append(lk_str)

    pron = resolve_partner_pronouns(
        profile={
            "name": partner_name,
            "role": role,
            "contact": contact,
            "lore_entity": lore_ent,
            "scene_npc": npc_scene_obj,
            "gender": (
                (contact or {}).get("gender")
                or (contact or {}).get("sex")
                or b_info.get("gender")
                or b_info.get("sex")
                or (npc_scene_obj or {}).get("gender")
                or (npc_scene_obj or {}).get("sex")
                or ""
            ),
        },
        partner_name=partner_name,
    )
    res_gender = "female" if pron["subj"] == "she" else ("male" if pron["subj"] == "he" else "they")

    return {
        "name": partner_name,
        "score": score,
        "track": track,
        "tier_level": tier_level,
        "tier_name": tier_name,
        "role": role,
        "faction": faction,
        "gender": res_gender,
        "pronouns": pron,
        "traits": traits_list[:4],
        "likes": likes_list[:4],
        "is_party_member": is_party_member,
        "is_temp_companion": is_temp_companion,
        "is_companion": is_companion,
        "is_private_meetup": is_private_meetup,
        "meetup_location": meetup_location,
        "has_other_commitment_loc": has_other_commitment_loc,
        "is_npc_home_or_office": is_npc_home_or_office,
        "is_quest_stationed_here": is_quest_stationed_here,
        "relevant_quests": relevant_quests,
        "can_walk_together": can_walk_together,
        "convince_stay_dc": convince_stay_dc,
        "contact": contact,
        "lore_entity": lore_ent,
        "scene_npc": npc_scene_obj,
    }


def _collect_valid_walk_destinations(
    session: Optional[Dict[str, Any]],
    profile: Dict[str, Any],
) -> Set[str]:
    valid: Set[str] = set()
    if not isinstance(session, dict):
        return valid
    sess_id = session.get("id")
    curr_loc = str(session.get("current_location") or "")
    curr_zone = curr_loc.split("➔")[0].strip().lower() if curr_loc else ""

    if profile.get("meetup_location"):
        for part in str(profile["meetup_location"]).split("➔"):
            if part.strip():
                valid.add(part.strip().lower())
    for wp in (profile.get("relevant_quests") or []):
        for part in str(wp.get("target_location") or wp.get("location") or "").split("➔"):
            if part.strip():
                valid.add(part.strip().lower())
    if sess_id:
        try:
            for q in (db.get_session_quests(int(sess_id), status="Active") or []):
                for part in str(q.get("location") or "").split("➔"):
                    if part.strip():
                        valid.add(part.strip().lower())
        except Exception:
            pass
        if curr_zone:
            try:
                for loc_row in (db.get_session_locations(int(sess_id)) or []):
                    if str(loc_row.get("zone_name") or "").strip().lower() == curr_zone:
                        for k in ("primary_name", "sub_name"):
                            v = str(loc_row.get(k) or "").strip().lower()
                            if v:
                                valid.add(v)
            except Exception:
                pass
            try:
                curr_nid = session.get("current_node_id")
                if curr_nid:
                    for edge in (db.get_outgoing_edges(int(sess_id), str(curr_nid)) or []):
                        to_nid = edge.get("to_node_id") or edge.get("target_node_id")
                        if to_nid:
                            wn = db.get_world_node(int(sess_id), str(to_nid))
                            if isinstance(wn, dict) and wn.get("name"):
                                valid.add(str(wn["name"]).strip().lower())
            except Exception:
                pass

    for generic_spot in (
        "quieter corner", "quiet corner", "quieter spot", "hallway", "corridor",
        "courtyard", "balcony", "terrace", "nearby bench", "lounge", "foyer",
    ):
        valid.add(generic_spot)
    return valid


def is_choice_allowed_for_partner_profile(
    choice: Dict[str, Any] | str,
    profile: Dict[str, Any],
    session: Optional[Dict[str, Any]] = None,
    allow_convince_stay: bool = False,
) -> bool:
    """Validates structural gates (Convince Stay, Walk-Along destinations, Merchant/Faculty flirt block)."""
    c_dict = choice if isinstance(choice, dict) else {"label": str(choice or "")}
    lbl = str(c_dict.get("label") or c_dict.get("text") or "").strip()
    if not lbl:
        return False
    lbl_low = lbl.lower()

    if c_dict.get("_pinned_dialogue_exit") or c_dict.get("intent") == "dialogue_exit" or c_dict.get("ends_dialogue"):
        return True

    if is_convince_stay_action(c_dict):
        return bool(allow_convince_stay and c_dict.get("_convince_stay"))

    if "quieter" in lbl_low and ("propose moving" in lbl_low or "suggest moving" in lbl_low or "speak in private" in lbl_low):
        if int(profile.get("score", 0)) < 50 and not profile.get("is_private_meetup") and profile.get("track") != "romantic":
            return False

    m_walk = _WALK_WITH_RE.match(lbl)
    if c_dict.get("intent") != "party_recruit" and (m_walk or any(p in lbl_low for p in ("walk with ", "stroll with ", "accompany ", "tag along with "))):
        if c_dict.get("_priority_slot"):
            return True
        if not profile.get("can_walk_together"):
            return False
        dest_match = re.search(r"\b(?:to|toward|towards|into)\s+(.+)$", lbl, re.IGNORECASE)
        if dest_match:
            dest_raw = re.sub(r"^(?:the|a|an)\s+", "", dest_match.group(1).strip(" .,!?)(").lower()).strip()
            valid_dests = _collect_valid_walk_destinations(session, profile)
            if dest_raw and valid_dests:
                if not any(vd in dest_raw or dest_raw in vd for vd in valid_dests if len(vd) >= 4):
                    return False

    # Block flirt_chemistry / romantic advances on Faculty, Merchants, Clerks, and non-contact roles
    scen_key = str((session or {}).get("scenario") or "fantasy")
    if str(c_dict.get("intent") or "").lower() == "party_recruit":
        scen_low = scen_key.lower()
        if int(profile.get("score", 0)) < 0 or "slice_of_life" in scen_low or ("high_school" in scen_low and "anomalous" not in scen_low):
            return False
    allows_flirt = deck._npc_allows_flirt(
        str(profile.get("name") or ""),
        profile.get("scene_npc"),
        profile.get("contact"),
        scen_key,
    )
    if not allows_flirt:
        if (
            str(c_dict.get("category") or "").lower() == "flirt_chemistry"
            or str(c_dict.get("intent") or "").lower() in ("romantic_confession", "phone_contact_exchange")
            or _ROMANTIC_ADVANCE_RE.search(lbl)
        ):
            return False

    return True


def build_pinned_leave_choice(partners: List[str]) -> Dict[str, Any]:
    """Builds the standardized, pinned Band 4 Leave Conversation choice."""
    clean_partners = [str(p).strip() for p in (partners or []) if str(p).strip()]
    label = f"Leave conversation with {clean_partners[0]}" if len(clean_partners) == 1 else "Leave conversation"
    return {
        "label": label,
        "stat": "NONE",
        "requirement": 0,
        "mp_cost": 0,
        "is_fallback": False,
        "intent": "dialogue_exit",
        "ends_dialogue": True,
        "_pinned_dialogue_exit": True,
        "_server_stamped": True,
    }


def generate_band1_quest_and_rumor_fallbacks(
    profile: Dict[str, Any],
    session: Optional[Dict[str, Any]],
    char: Optional[Dict[str, Any]] = None,
    actions: Optional[List[Any]] = None,
    active_quests: Optional[List[Any]] = None,
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    return _gen_b1_impl(
        profile=profile,
        session=session,
        char=char,
        actions=actions,
        active_quests=active_quests,
        ledgers_getter=get_npc_conversation_ledgers,
        **kwargs,
    )


def generate_band2_social_choices(
    profile: Dict[str, Any],
    session: Optional[Dict[str, Any]],
    actions: Optional[List[Any]] = None,
    party: Optional[List[Any]] = None,
) -> List[Dict[str, Any]]:
    return _gen_b2_impl(
        profile=profile,
        session=session,
        actions=actions,
        party=party,
        ledgers_getter=get_npc_conversation_ledgers,
    )


def _is_verified_quest_choice(c: Dict[str, Any]) -> bool:
    return bool(
        c.get("is_climax_action")
        or c.get("is_story_quest")
        or c.get("is_quest_action")
        or c.get("quest_id")
        or c.get("clue_pair_ids")
        or c.get("_active_quest_inquiry")
        or c.get("_is_world_rumor_inquiry")
        or c.get("_is_break_the_news")
    )


def _is_pre_exit_utility_choice(c: Dict[str, Any]) -> bool:
    if c.get("_convince_stay") or c.get("departure_action") == "convince_stay":
        return True
    intent = str(c.get("intent") or "").lower()
    if intent in ("phone_contact_exchange", "party_recruit"):
        return True
    lbl_low = str(c.get("label") or "").lower()
    if c.get("_privacy_nudge") or str(c.get("sub_intent") or "").lower() == "privacy_nudge" or "for privacy" in lbl_low:
        return True
    if _WALK_WITH_RE.match(str(c.get("label") or "")) or "walk with " in lbl_low:
        return True
    if intent == "movement" and "quieter" in lbl_low:
        return True
    return False


def _utility_sort_rank(c: Dict[str, Any]) -> int:
    """Orders Band 3 Pre-Exit Utilities: Recruit (0) -> Quiet Spot/Walk (1) -> Contact Info (2) -> Convince Stay (3)."""
    intent = str(c.get("intent") or "").lower()
    if intent == "party_recruit":
        return 0
    if c.get("_convince_stay") or c.get("departure_action") == "convince_stay":
        return 3
    if intent == "phone_contact_exchange":
        return 2
    return 1


def _classify_choice_band(c: Dict[str, Any]) -> int:
    """Classifies a dialogue choice into Band 1 (Quest/Rumor), Band 2 (Social), Band 3 (Utility), or Band 4 (Exit)."""
    if c.get("_pinned_dialogue_exit") or c.get("intent") == "dialogue_exit" or c.get("ends_dialogue"):
        return 4
    if _is_pre_exit_utility_choice(c):
        return 3
    if _is_verified_quest_choice(c):
        return 1
    if c.get("topic_id") or c.get("category") or c.get("_band") == 2:
        return 2
    if c.get("_band") == 1:
        return 1
    return 2


def _normalize_band2_stat_and_dc(
    c: Dict[str, Any],
    profile: Dict[str, Any],
    char: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ensures every Band 2 / Band 3 social or utility button has a valid 7-SPECIAL stat and fixed DC 3-12."""
    out = dict(c)
    out.pop("_free_social", None)
    lbl = str(out.get("label") or "")
    st_u = str(out.get("stat") or "NONE").upper()
    req_u = int(out.get("requirement") or 0)

    if out.get("_server_stamped") and str(out.get("intent") or "").lower() == "party_recruit" and st_u == "NONE":
        out["stat"] = "NONE"
        out["requirement"] = 0
        return out

    if (_WALK_WITH_RE.match(lbl) or "walk with " in lbl.lower()) and st_u == "NONE" and (profile.get("can_walk_together") or out.get("_priority_slot")):
        out["stat"] = "NONE"
        out["requirement"] = 0
        out.setdefault("intent", "movement")
        return out

    if out.get("_privacy_nudge") or str(out.get("sub_intent") or "").lower() == "privacy_nudge" or "for privacy" in lbl.lower():
        if st_u not in SPECIAL_STATS_SET:
            out["stat"] = "CHA"
        out["requirement"] = max(3, min(12, req_u if req_u > 0 else 8))
        return out

    intent = str(out.get("intent") or "").lower()
    is_bold_stranger = (
        int(profile.get("score", 0)) < 50
        and profile.get("track") != "romantic"
        and (
            _infer_social_category_from_choice(out) == "flirt_chemistry"
            or _ROMANTIC_ADVANCE_RE.search(lbl)
        )
    )
    if st_u not in SPECIAL_STATS_SET and st_u != "ITEM":
        from game_engine.choices_cleaner import infer_choice_stat_and_dc
        new_st, new_dc = infer_choice_stat_and_dc(lbl, default_stat="CHA", default_dc=5, char=char)
        out["stat"] = new_st if new_st in SPECIAL_STATS_SET else "CHA"
        req_u = req_u if req_u > 0 else int(new_dc)

    if req_u <= 0:
        if intent in ("phone_contact_exchange", "romantic_confession") or _BOLD_SOCIAL_CHECK_RE.search(lbl):
            req_u = get_disclosure_check_requirement(7, int(profile.get("score", 0)), 2)
        else:
            req_u = 5

    if is_bold_stranger and not out.get("_seed_reconciled"):
        req_u = max(9, req_u)

    if out.get("stat") != "ITEM":
        out["requirement"] = max(3, min(12, req_u))
    return out


def _infer_social_category_from_choice(c: Dict[str, Any]) -> str:
    raw_cat = str(c.get("category") or "").strip().lower()
    if raw_cat in (
        "get_to_know", "friendly_situational", "humor_banter",
        "flirt_chemistry", "friction_rivalry", "callbacks_history", "clear_the_air",
    ):
        return raw_cat
    lbl = str(c.get("label") or "").lower()
    if any(w in lbl for w in ("apologize", "make amends", "clear the air", "own up", "explain why")):
        return "clear_the_air"
    if any(w in lbl for w in ("flirt", "tease", "wink", "compliment", "gaze", "brush", "charm", "chemistry", "blush")):
        return "flirt_chemistry"
    if any(w in lbl for w in ("challenge", "call out", "confront", "push back", "rival", "insult", "bluff", "stand firm")):
        return "friction_rivalry"
    if any(w in lbl for w in ("joke", "laugh", "banter", "quip", "wit", "crack a", "dry humor")):
        return "humor_banter"
    if any(w in lbl for w in ("remember", "promise", "last time", "shared", "earlier", "mutual")):
        return "callbacks_history"
    if any(w in lbl for w in ("rumor", "heard", "lately", "weather", "atmosphere", "drink", "snack", "lend a hand")):
        return "friendly_situational"
    return "get_to_know"


def _stamp_choice_from_seed(
    choice: Dict[str, Any],
    seed: Dict[str, Any],
    default_partner: str,
) -> Dict[str, Any]:
    out = dict(choice)
    out["topic_id"] = str(seed.get("topic_id") or out.get("topic_id") or "")
    out["category"] = str(seed.get("category") or out.get("category") or "")
    st = str(seed.get("stat") or out.get("stat") or "CHA").upper()
    out["stat"] = st if st in SPECIAL_STATS_SET else "CHA"
    out["requirement"] = max(3, min(12, int(seed.get("dc") or out.get("requirement") or 6)))
    out["mp_cost"] = max(0, int(seed.get("mp_cost") or 0))
    out["target_npc"] = str(seed.get("target_npc") or out.get("target_npc") or default_partner)
    out["is_covert_ability"] = bool(seed.get("is_covert_ability"))
    out["is_direct_reply"] = bool(seed.get("is_direct_reply"))
    if seed.get("is_cruel"):
        out["is_cruel"] = True
    if seed.get("event_key"):
        out["event_key"] = str(seed["event_key"])
    out["_seed_reconciled"] = True
    out["_band"] = 2
    return out


def _reconcile_band2_with_dealt_seeds(
    band2_raw: List[Dict[str, Any]],
    dealt_seeds: List[Dict[str, Any]],
    lead_profile: Dict[str, Any],
    sess: Dict[str, Any],
    clean_partners: List[str],
    party: Optional[List[Any]],
    current_npcs: Optional[List[Any]],
    desired_min_b2: int,
    desired_max_b2: int,
    seen_lbls: Set[str],
    clear_the_air_required: bool = False,
    lead_char: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """3-pass seed reconciliation: Pass 1 exact topic_id -> Pass 2 category slot -> Pass 3 deterministic fallback."""
    lead_partner = clean_partners[0]
    seeds = [dict(s) for s in (dealt_seeds or []) if isinstance(s, dict) and s.get("topic_id")]
    if not seeds:
        return band2_raw

    claimed_seed_idx: Set[int] = set()
    milestones: List[Dict[str, Any]] = []
    pass1_matched: List[Dict[str, Any]] = []
    unmatched_after_p1: List[Dict[str, Any]] = []

    for c in band2_raw:
        c_int = str(c.get("intent") or "").lower()
        c_sub = str(c.get("sub_intent") or "").lower()
        if c_int == "romantic_confession" or c_sub in ("confession", "date") or c.get("_privacy_nudge"):
            if not clear_the_air_required:
                milestones.append(_normalize_band2_stat_and_dc(c, lead_profile, char=lead_char))
            continue

        c_tid = str(c.get("topic_id") or "").strip()
        matched_i: Optional[int] = None
        if c_tid:
            for idx, s in enumerate(seeds):
                if idx not in claimed_seed_idx and str(s.get("topic_id") or "").strip() == c_tid:
                    matched_i = idx
                    break
        if matched_i is not None:
            claimed_seed_idx.add(matched_i)
            pass1_matched.append(_stamp_choice_from_seed(c, seeds[matched_i], lead_partner))
        else:
            unmatched_after_p1.append(c)

    # Pass 2: Category / Semantic Slot Match
    pass2_matched: List[Dict[str, Any]] = []
    leftover_llm: List[Dict[str, Any]] = []
    for c in unmatched_after_p1:
        inferred_cat = _infer_social_category_from_choice(c)
        matched_i = None
        for idx, s in enumerate(seeds):
            if idx not in claimed_seed_idx and str(s.get("category") or "").strip().lower() == inferred_cat:
                matched_i = idx
                break
        if matched_i is not None:
            claimed_seed_idx.add(matched_i)
            pass2_matched.append(_stamp_choice_from_seed(c, seeds[matched_i], lead_partner))
        elif not clear_the_air_required:
            leftover_llm.append(_normalize_band2_stat_and_dc(c, lead_profile, char=lead_char))

    reconciled: List[Dict[str, Any]] = list(milestones) + pass1_matched + pass2_matched

    # Pass 3: Ensure top non-CHA wildcard stat from dealt seeds is present, then fill up to desired_min_b2
    wildcard_non_cha_seeds = [
        (idx, s) for idx, s in enumerate(seeds)
        if idx not in claimed_seed_idx and str(s.get("stat") or "CHA").upper() != "CHA"
    ]
    present_stats = {str(ch.get("stat") or "").upper() for ch in reconciled}
    if wildcard_non_cha_seeds:
        w_idx, w_seed = wildcard_non_cha_seeds[0]
        w_stat = str(w_seed.get("stat") or "").upper()
        if w_stat and w_stat not in present_stats and len(reconciled) < desired_max_b2:
            prof_for_w = (
                lead_profile
                if str(w_seed.get("target_npc") or lead_partner).strip().lower() == lead_partner.lower()
                else resolve_partner_conversation_profile(sess, str(w_seed.get("target_npc")), party=party, current_npcs=current_npcs)
            )
            syn_w = synthesize_choice_from_seed(w_seed, prof_for_w, session=sess)
            wk = syn_w["label"].strip().lower()
            if wk not in seen_lbls and is_choice_allowed_for_partner_profile(syn_w, prof_for_w, session=sess):
                claimed_seed_idx.add(w_idx)
                seen_lbls.add(wk)
                reconciled.append(_normalize_band2_stat_and_dc(syn_w, prof_for_w, char=lead_char))
                present_stats.add(w_stat)

    for lf in leftover_llm:
        if len(reconciled) >= desired_max_b2:
            break
        reconciled.append(lf)

    for idx, s in enumerate(seeds):
        if len(reconciled) >= desired_min_b2:
            break
        if idx in claimed_seed_idx:
            continue
        t_p = str(s.get("target_npc") or lead_partner).strip() or lead_partner
        prof_s = (
            lead_profile
            if t_p.lower() == lead_partner.lower()
            else resolve_partner_conversation_profile(sess, t_p, party=party, current_npcs=current_npcs)
        )
        syn = synthesize_choice_from_seed(s, prof_s, session=sess)
        sk = syn["label"].strip().lower()
        if sk not in seen_lbls and is_choice_allowed_for_partner_profile(syn, prof_s, session=sess):
            claimed_seed_idx.add(idx)
            seen_lbls.add(sk)
            reconciled.append(_normalize_band2_stat_and_dc(syn, prof_s, char=lead_char))

    return reconciled[:desired_max_b2]


def enforce_conversation_choice_bands(
    cleaned_choices: List[Dict[str, Any]],
    session: Optional[Dict[str, Any]],
    partners: List[str],
    party: Optional[List[Any]] = None,
    current_npcs: Optional[List[Any]] = None,
    priority_buttons: Optional[List[Dict[str, Any]]] = None,
    actions: Optional[List[Any]] = None,
) -> List[Dict[str, Any]]:
    """Enforces [Band 1: Quest (0-2)] -> [Band 2: Social (4-6)] -> [Band 3: Pre-Exit Utilities] -> [Band 4: Leave] (<= 8)."""
    clean_partners = [str(p).strip() for p in (partners or []) if str(p).strip()]
    if not clean_partners:
        return list(cleaned_choices or [])

    sess = session if isinstance(session, dict) else {}
    sess_id = sess.get("id")
    lead_partner = clean_partners[0]
    lead_char = None
    if party and isinstance(party, list) and party[0]:
        lead_char = party[0][0] if isinstance(party[0], (tuple, list)) else party[0]

    if scenario_data.is_anomalous_incursions_scenario(str(sess.get("scenario") or "")):
        from mechanics.world.anomalous_events import (
            build_sapient_anomaly_dialogue_choices,
            is_anomalous_scene_entity,
        )
        if is_anomalous_scene_entity(lead_partner, session=sess, current_npcs=current_npcs):
            return build_sapient_anomaly_dialogue_choices(
                lead_partner,
                session_id=int(sess_id) if sess_id else None,
                session=sess,
                char=lead_char if isinstance(lead_char, dict) else None,
            )

    dep_states = get_npc_departure_states(sess)
    urg_partner = ""
    urg_state: Dict[str, Any] = {}
    for p_nm in clean_partners:
        st_cand = dep_states.get(_canon_npc_key(p_nm))
        if st_cand and st_cand.get("stage") in ("stage_2_ultimatum", "stage_1_warning"):
            urg_partner = p_nm
            urg_state = st_cand
            if st_cand.get("stage") == "stage_2_ultimatum":
                break

    urg_profile = (
        resolve_partner_conversation_profile(sess, urg_partner, party=party, current_npcs=current_npcs)
        if urg_partner
        else None
    )
    lead_profile = resolve_partner_conversation_profile(sess, lead_partner, party=party, current_npcs=current_npcs)
    budget_state = get_partner_conversation_budget_state(sess, lead_profile)
    remaining_budget = int(budget_state.get("remaining_budget", 5))
    asked_sigs = set(budget_state.get("asked_topic_signatures") or [])
    from mechanics.social.band_fallbacks import _recent_action_labels_lower
    recent_labels = _recent_action_labels_lower(
        sess, actions=actions, partner_name=lead_partner, ledgers_getter=get_npc_conversation_ledgers
    )

    curr_day = int(sess.get("current_day") or 1)
    curr_min = int(sess.get("current_minute") if sess.get("current_minute") is not None else 480)
    from mechanics.world.schedules import get_time_block_key
    curr_blk = get_time_block_key(curr_min)

    # ── STAGE 2 ULTIMATUM OVERRIDE: Strictly 2 Choices ──────────────────────
    if urg_partner and urg_state.get("stage") == "stage_2_ultimatum" and urg_profile:
        ultimatum_choices: List[Dict[str, Any]] = []
        if urg_state.get("extended_block") != curr_blk:
            ultimatum_choices.append({
                "label": f"Convince {urg_partner} to stay a little longer",
                "stat": "CHA",
                "requirement": int(urg_profile["convince_stay_dc"]),
                "mp_cost": 0,
                "intent": "social_invite",
                "target_npc": urg_partner,
                "_convince_stay": True,
                "departure_action": "convince_stay",
                "_priority_slot": True,
                "_server_stamped": True,
                "_stage_2_ultimatum_locked": True,
            })
        if len(clean_partners) >= 2:
            exit_opt = {
                "label": f"Let {urg_partner} head out",
                "stat": "NONE",
                "requirement": 0,
                "mp_cost": 0,
                "is_fallback": False,
                "intent": "general_action",
                "dismisses_npc": urg_partner,
                "target_npc": urg_partner,
                "departure_action": "let_npc_depart",
                "_pinned_dialogue_exit": True,
                "_server_stamped": True,
                "_stage_2_ultimatum_locked": True,
            }
        else:
            exit_opt = build_pinned_leave_choice(clean_partners)
            exit_opt["_stage_2_ultimatum_locked"] = True
        ultimatum_choices.append(exit_opt)
        return ultimatum_choices

    in_stage_1 = bool(urg_partner and urg_state.get("stage") == "stage_1_warning" and urg_profile)
    pinned_exit = build_pinned_leave_choice(clean_partners)

    # Check Composure Cold-Shoulder / Focus-on-Road lockouts
    comp_row = None
    if sess_id:
        try:
            comp_row = pacing.sync_and_get_composure(
                int(sess_id),
                lead_partner,
                current_day=curr_day,
                current_minute=curr_min,
                scenario=str(sess.get("scenario") or "fantasy"),
            )
        except Exception:
            comp_row = None

    comp_locked = bool(
        comp_row
        and int(comp_row.get("current_composure") if comp_row.get("current_composure") is not None else 100) <= 0
        and pacing.is_composure_locked_out(comp_row, curr_day, curr_min)
    )
    comp_state = str((comp_row or {}).get("composure_state") or "")

    combined_raw: List[Dict[str, Any]] = []
    seen_lbls: Set[str] = set()
    for src in list(priority_buttons or []) + list(cleaned_choices or []):
        if not isinstance(src, dict):
            continue
        lbl = sanitize_contextual_dialogue_label(str(src.get("label") or "").strip(), lead_profile, session=sess)
        src = dict(src, label=lbl)
        lbl_k = lbl.lower()
        if not lbl_k or lbl_k in seen_lbls:
            continue
        if src.get("_pinned_dialogue_exit") or src.get("intent") == "dialogue_exit" or src.get("ends_dialogue"):
            continue
        from mechanics.narrative.intent import is_conversational_exit
        if is_conversational_exit(lbl):
            continue
        if not is_choice_allowed_for_partner_profile(src, lead_profile, session=sess, allow_convince_stay=in_stage_1):
            continue

        is_quest_c = _is_verified_quest_choice(src)
        is_util_c = _is_pre_exit_utility_choice(src)
        if not is_quest_c and not is_util_c:
            if _is_similar_to_recent(lbl, recent_labels):
                continue
            sig_c = str(src.get("_topic_sig") or _extract_topic_signature(lbl, src) or "")
            if sig_c and sig_c in asked_sigs:
                continue

        seen_lbls.add(lbl_k)
        combined_raw.append(src)

    try:
        from game_engine.choices_cleaner import deduplicate_redundant_choices
        combined_raw = deduplicate_redundant_choices(combined_raw, ignore_names=clean_partners)
    except Exception:
        pass

    band1: List[Dict[str, Any]] = []
    band2: List[Dict[str, Any]] = []
    band3_utils: List[Dict[str, Any]] = []

    for c in combined_raw:
        if c.get("_convince_stay"):
            continue
        b_idx = _classify_choice_band(c)
        if b_idx == 1:
            band1.append(c)
        elif b_idx == 3:
            band3_utils.append(_normalize_band2_stat_and_dc(c, lead_profile, char=lead_char))
        elif b_idx == 2:
            band2.append(_normalize_band2_stat_and_dc(c, lead_profile, char=lead_char))

    # Backfill verified Band 1 quest / discovered rumor / claimed MNR hooks (0-2 slots ONLY when genuinely applicable!)
    if len(band1) < 2:
        for fb1 in generate_band1_quest_and_rumor_fallbacks(lead_profile, sess, char=lead_char, actions=actions):
            if not _is_verified_quest_choice(fb1):
                continue
            fb_k = fb1["label"].strip().lower()
            if fb_k not in seen_lbls:
                seen_lbls.add(fb_k)
                band1.append(fb1)
            if len(band1) >= 2:
                break

    band1.sort(key=lambda x: (0 if x.get("clue_pair_ids") else 1, 0 if x.get("quest_id") else 1))
    from game_engine.choices_cleaner import infer_choice_stat_and_dc
    for b1 in band1:
        st_u = str(b1.get("stat") or "NONE").upper()
        req_u = int(b1.get("requirement") or 0)
        if st_u not in SPECIAL_STATS_SET or req_u <= 0:
            new_st, new_dc = infer_choice_stat_and_dc(b1.get("label", ""), default_stat="INT", default_dc=6, char=lead_char)
            b1["stat"] = new_st if new_st in SPECIAL_STATS_SET else "INT"
            b1["requirement"] = max(4, min(12, new_dc))
    band1 = band1[:2]

    # Attach Stage 1 Convince to Stay to Band 3 Pre-Exit Utilities (pinned right before Leave Conversation!)
    if in_stage_1 and urg_profile and urg_state.get("extended_block") != curr_blk:
        band3_utils.append({
            "label": f"Convince {urg_partner} to stay a little longer",
            "stat": "CHA",
            "requirement": int(urg_profile["convince_stay_dc"]),
            "mp_cost": 0,
            "intent": "social_invite",
            "target_npc": urg_partner,
            "_convince_stay": True,
            "departure_action": "convince_stay",
            "_priority_slot": True,
            "_server_stamped": True,
        })
    band3_utils.sort(key=_utility_sort_rank)
    band3_utils = band3_utils[:3]

    # ── COLD SHOULDER / FOCUS ON ROAD / BUDGET EXHAUSTION GATES ─────────────
    if comp_locked and comp_state == "cold_shoulder":
        cold_b1 = []
        for b1 in band1:
            cb = dict(b1)
            cb["requirement"] = min(12, int(cb.get("requirement") or 6) + 3)
            cold_b1.append(cb)
        return cold_b1 + [pinned_exit]

    if comp_locked and comp_state in ("focus_on_road", "walked_away"):
        return band1 + [pinned_exit]

    if remaining_budget <= 0:
        convince_only = [u for u in band3_utils if u.get("_convince_stay")]
        out_b1 = [_apply_stage1_hurry_gate(c) for c in band1] if (in_stage_1 and urg_profile) else band1
        return out_b1 + convince_only + [pinned_exit]

    # ── ELASTIC BAND 2 DYNAMIC SOCIAL SUITE (4-6 slots, <= 8 total) ─────────
    avail_for_b2 = max(1, 8 - 1 - len(band1) - len(band3_utils))
    desired_min_b2 = min(avail_for_b2, 4)
    desired_max_b2 = min(avail_for_b2, 6)

    clear_the_air_req = bool(int((comp_row or {}).get("clear_the_air_required") or 0) == 1)
    dealt_seeds = sess.get("_dealt_social_seeds")
    if clear_the_air_req and not (isinstance(dealt_seeds, list) and dealt_seeds):
        dealt_seeds = deck.deal_social_deck_seeds(
            session=sess,
            partners=clean_partners,
            party=party,
            current_npcs=current_npcs,
            desired_count=max(4, desired_max_b2),
        )

    if isinstance(dealt_seeds, list) and dealt_seeds:
        band2 = _reconcile_band2_with_dealt_seeds(
            band2_raw=band2,
            dealt_seeds=dealt_seeds,
            lead_profile=lead_profile,
            sess=sess,
            clean_partners=clean_partners,
            party=party,
            current_npcs=current_npcs,
            desired_min_b2=desired_min_b2,
            desired_max_b2=desired_max_b2,
            seen_lbls=seen_lbls,
            clear_the_air_required=clear_the_air_req,
            lead_char=lead_char,
        )

    if len(band2) < desired_min_b2:
        for fb2 in generate_band2_social_choices(lead_profile, sess, actions=actions, party=party):
            fb_k = fb2["label"].strip().lower()
            if fb_k not in seen_lbls and is_choice_allowed_for_partner_profile(fb2, lead_profile, session=sess):
                seen_lbls.add(fb_k)
                band2.append(_normalize_band2_stat_and_dc(fb2, lead_profile, char=lead_char))
            if len(band2) >= desired_max_b2:
                break

    if remaining_budget == 1:
        band2 = band2[:min(2, desired_max_b2)]
    elif remaining_budget == 2:
        band2 = band2[:min(3, desired_max_b2)]
    else:
        band2 = band2[:desired_max_b2]

    if in_stage_1 and urg_profile:
        band1 = [_apply_stage1_hurry_gate(c) for c in band1]
        band2 = [_apply_stage1_hurry_gate(c) for c in band2]
        band3_utils = [
            u if u.get("_convince_stay") else _apply_stage1_hurry_gate(u)
            for u in band3_utils
        ]

    # Final hard <= 8 ceiling: trim social slots first so Band 1 quests, Band 3 pre-exit utilities, and Band 4 exit never drop
    while len(band1) + len(band2) + len(band3_utils) + 1 > 8 and len(band2) > 1:
        band2.pop()

    return band1 + band2 + band3_utils + [pinned_exit]


def pin_dialogue_exit_last(
    choices: List[Dict[str, Any]],
    partners: Optional[List[str]],
    max_total: int = 8,
) -> List[Dict[str, Any]]:
    """Keeps Stage 2 locks intact, pins Pre-Exit Utilities right above Leave Conversation, and caps at max_total."""
    clean_partners = [str(p).strip() for p in (partners or []) if str(p).strip()]
    if not clean_partners:
        return list(choices or [])

    if any(isinstance(c, dict) and c.get("_stage_2_ultimatum_locked") for c in (choices or [])):
        return [c for c in (choices or []) if isinstance(c, dict) and c.get("_stage_2_ultimatum_locked")]

    body: List[Dict[str, Any]] = []
    utilities: List[Dict[str, Any]] = []
    exit_choice: Optional[Dict[str, Any]] = None
    from mechanics.narrative.intent import is_conversational_exit

    for c in (choices or []):
        if not isinstance(c, dict):
            continue
        lbl = str(c.get("label") or "").strip()
        if (
            c.get("_pinned_dialogue_exit")
            or c.get("intent") == "dialogue_exit"
            or c.get("ends_dialogue")
            or is_conversational_exit(lbl)
        ):
            if exit_choice is None:
                exit_choice = c if c.get("_pinned_dialogue_exit") else build_pinned_leave_choice(clean_partners)
            continue
        if _is_pre_exit_utility_choice(c):
            utilities.append(c)
        else:
            body.append(c)

    if exit_choice is None:
        exit_choice = build_pinned_leave_choice(clean_partners)

    utilities.sort(key=_utility_sort_rank)
    avail_body = max(0, max_total - 1 - len(utilities))
    return body[:avail_body] + utilities[: max(0, max_total - 1)] + [exit_choice]


def evaluate_conversation_departure_turn(
    session: Dict[str, Any],
    actions: Optional[List[Any]],
    new_partners: List[str],
    has_exited_convo: bool,
    party: Optional[List[Any]] = None,
    stage_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return run_departure_turn_evaluation(
        session=session,
        actions=actions,
        new_partners=new_partners,
        has_exited_convo=has_exited_convo,
        profile_resolver=resolve_partner_conversation_profile,
        party=party,
        stage_info=stage_info,
    )


def relocate_departed_schedule_npcs(
    session: Dict[str, Any],
    result: Dict[str, Any],
    departing_records: List[Dict[str, str]],
    stage_info: Optional[Dict[str, Any]] = None,
) -> None:
    relocate_departed_npcs_impl(
        session=session,
        result=result,
        departing_records=departing_records,
        find_contact_and_lore_fn=_find_contact_and_lore,
        stage_info=stage_info,
    )


def build_conversation_prompt_directive(
    session: Optional[Dict[str, Any]],
    partners: List[str],
    party: Optional[List[Any]] = None,
) -> str:
    """Builds the Z3 LLM prompt block instructing 4-Band choice generation & contextual seed authoring."""
    clean_partners = [str(p).strip() for p in (partners or []) if str(p).strip()]
    if not clean_partners:
        return ""
    prof = resolve_partner_conversation_profile(session, clean_partners[0], party=party)
    if isinstance(session, dict) and scenario_data.is_anomalous_incursions_scenario(str(session.get("scenario") or "")):
        from mechanics.world.anomalous_events import is_anomalous_scene_entity
        if is_anomalous_scene_entity(clean_partners[0], session=session):
            return (
                f"\n[SAPIENT ANOMALY DIALOGUE DIRECTIVE — {clean_partners[0]}]:\n"
                f"- Active Anomalous Entity Partner: {clean_partners[0]}\n"
                f"- Voice {clean_partners[0]} strictly as an eerie, otherworldly sapient anomalous manifestation answering about its origins, taboo/nature, or bargain terms—NEVER as a mundane human peer making small talk.\n"
            )

    partner = clean_partners[0]
    tier_name = prof["tier_name"]
    score = prof["score"]
    seeds = (session or {}).get("_dealt_social_seeds") if isinstance(session, dict) else None
    seed_lines = ""
    if isinstance(seeds, list) and seeds:
        formatted = []
        for s in seeds:
            if not isinstance(s, dict):
                continue
            reply_tag = " [DIRECT REPLY TO QUESTION]" if s.get("is_direct_reply") else ""
            formatted.append(
                f"    * topic_id='{s.get('topic_id')}' | category='{s.get('category')}' | stat='{s.get('stat')}' | target='{s.get('target_npc')}'{reply_tag}: {s.get('prompt_cue')}"
            )
        if formatted:
            seed_lines = (
                "  - [PRE-TURN SOCIAL SEEDS — AUTHOR BESPOKE CONTEXTUAL LABELS]:\n"
                "    Write natural, scene-grounded dialogue choice `label` strings for each seed below (never formulaic templates; never mention raw DC numbers), "
                "and copy its exact `topic_id` and `category` onto the emitted `Choice` object:\n"
                + "\n".join(formatted)
                + "\n"
            )

    return (
        "\n[CONVERSATION CHOICE ARCHITECTURE — 4-BAND PYTHON-ENFORCED]:\n"
        f"- Active Dialogue Partner(s): {', '.join(clean_partners)} ({partner}: '{tier_name}', score={score})\n"
        "- Structure `choices` cleanly (total <= 8):\n"
        "  1. QUEST / INVESTIGATION (0-2 slots ONLY if an active quest, bounty, or discovered rumor genuinely applies).\n"
        "  2. DYNAMIC SOCIAL SUITE (4-6 slots across `STR, PER, END, CHA, INT, AGI, LUK`): Contextual Sims-style get-to-know, situational props, banter, early/warm flirt gambles, rivalry pushback, callbacks, or casual local event gossip. Never treat student/personality tropes ('Class Clown', 'Delinquent') as paid jobs.\n"
        f"{seed_lines}"
        "  3. PRE-EXIT UTILITIES & LEAVE: Do NOT generate 'Convince ... to stay' unless instructed by [URGENT SCHEDULE DEPARTURE]. Python pins structural utilities and 'Leave conversation...' last.\n"
    )
