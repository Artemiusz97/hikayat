from __future__ import annotations

"""Deterministic Band 1 (Quest/Rumor) & Band 2 (Sims-Style Social) Fallback Synthesizers & Pronoun Sanitizers."""

import re
from typing import Any, Callable, Dict, List, Optional, Set

import db
import scenario_data
from mechanics.social import deck
from mechanics.social.departure import _canon_npc_key

_PRONOUNS_BY_GENDER: Dict[str, Dict[str, str]] = {
    "female": {
        "subj": "she",
        "obj": "her",
        "poss": "her",
        "refl": "herself",
        "is_are": "is",
        "has_have": "has",
        "loves_love": "loves",
        "enjoys_enjoy": "enjoys",
        "likes_like": "likes",
        "wants_want": "wants",
        "shares_share": "shares",
        "handles_handle": "handles",
        "knows_know": "knows",
    },
    "male": {
        "subj": "he",
        "obj": "him",
        "poss": "his",
        "refl": "himself",
        "is_are": "is",
        "has_have": "has",
        "loves_love": "loves",
        "enjoys_enjoy": "enjoys",
        "likes_like": "likes",
        "wants_want": "wants",
        "shares_share": "shares",
        "handles_handle": "handles",
        "knows_know": "knows",
    },
    "they": {
        "subj": "they",
        "obj": "them",
        "poss": "their",
        "refl": "themselves",
        "is_are": "are",
        "has_have": "have",
        "loves_love": "love",
        "enjoys_enjoy": "enjoy",
        "likes_like": "like",
        "wants_want": "want",
        "shares_share": "share",
        "handles_handle": "handle",
        "knows_know": "know",
    },
}


def resolve_partner_pronouns(
    profile: Optional[Dict[str, Any]] = None,
    partner_name: str = "",
) -> Dict[str, str]:
    """Deterministically resolves gender and pronoun conjugations for a conversational partner."""
    if isinstance(profile, dict) and isinstance(profile.get("pronouns"), dict):
        return profile["pronouns"]

    gender = ""
    if isinstance(profile, dict):
        raw_g = profile.get("gender") or profile.get("sex")
        if raw_g:
            norm_g = str(raw_g).strip().lower()
            if norm_g in ("they", "them", "nonbinary", "non-binary", "neutral", "unspecified"):
                return _PRONOUNS_BY_GENDER["they"]
            if norm_g in ("female", "woman", "girl"):
                return _PRONOUNS_BY_GENDER["female"]
            if norm_g in ("male", "man", "boy"):
                return _PRONOUNS_BY_GENDER["male"]
            gender = norm_g

    if not gender or gender not in ("female", "male"):
        from mechanics.social.persona.core import infer_contact_gender
        ref = profile if isinstance(profile, dict) else {}
        name = partner_name or str(ref.get("name") or "")
        contact_ref = ref.get("contact") or ref.get("scene_npc") or ref.get("lore_entity") or ref
        if not isinstance(contact_ref, dict):
            contact_ref = {"name": name}
        elif "name" not in contact_ref and name:
            contact_ref = dict(contact_ref)
            contact_ref["name"] = name
        inferred = infer_contact_gender(contact_ref)
        if inferred in ("female", "male"):
            gender = inferred

    if gender not in _PRONOUNS_BY_GENDER:
        gender = "they"
    return _PRONOUNS_BY_GENDER[gender]


def _recent_action_labels_lower(
    session: Optional[Dict[str, Any]],
    limit: int = 25,
    actions: Optional[List[Any]] = None,
    partner_name: str = "",
    ledgers_getter: Optional[Callable[[Optional[Dict[str, Any]]], Dict[str, Dict[str, Any]]]] = None,
) -> List[str]:
    labels: List[str] = []
    seen: Set[str] = set()

    def _add(val: Any) -> None:
        s = str(val or "").strip().lower()
        if s and s not in seen:
            seen.add(s)
            labels.append(s)

    for a in (actions or []):
        if isinstance(a, dict):
            _add(a.get("label") or a.get("text") or a.get("action"))

    if isinstance(session, dict):
        if partner_name and ledgers_getter:
            curr_day = int(session.get("current_day") or 1)
            l_key = f"{curr_day}:{_canon_npc_key(partner_name)}"
            ledgers = ledgers_getter(session)
            entry = ledgers.get(l_key) or {}
            for asked in (entry.get("asked_labels") or []):
                _add(asked)

        hist = session.get("history") or []
        for h in reversed(hist):
            if isinstance(h, dict):
                _add(h.get("label") or h.get("action_label") or h.get("action"))
                for sub_a in (h.get("actions") or []):
                    if isinstance(sub_a, dict):
                        _add(sub_a.get("label") or sub_a.get("text") or sub_a.get("action"))
            elif isinstance(h, str):
                m_str = re.search(r":\s*([^->]+?)(?:\s*->|$)", h)
                if m_str:
                    _add(m_str.group(1))
            if len(labels) >= limit:
                break
    return labels[:limit]


def _is_similar_to_recent(label: str, recent_labels: List[str]) -> bool:
    l_low = str(label or "").strip().lower()
    if not l_low or not recent_labels:
        return False
    if l_low in recent_labels:
        return True
    toks = {w for w in re.findall(r"\b[a-z]{4,}\b", l_low) if w not in {"with", "about", "what", "have", "from", "that", "this", "their", "your", "ask", "inquire"}}
    if len(toks) < 2:
        return False
    for rl in recent_labels:
        r_toks = set(re.findall(r"\b[a-z]{4,}\b", rl))
        if toks and len(toks & r_toks) >= max(2, len(toks) - 1):
            return True
    return False


def _build_contextual_role_and_leisure_phrases(
    profile: Dict[str, Any],
    session: Optional[Dict[str, Any]],
    venue_leaf: str,
) -> Dict[str, str]:
    from mechanics.social.relationships import format_public_character_role

    sess = session if isinstance(session, dict) else {}
    scen_key = str(sess.get("scenario") or "fantasy").lower()
    partner = str(profile.get("name") or "them").strip()
    pron = profile.get("_cached_pronouns")
    if not isinstance(pron, dict):
        pron = resolve_partner_pronouns(profile=profile, partner_name=partner)
        profile["_cached_pronouns"] = pron
    raw_role = str(profile.get("role") or "").strip()
    faction = str(profile.get("faction") or "").strip()
    contact = profile.get("contact") if isinstance(profile.get("contact"), dict) else {}
    b_info = (contact.get("basic_info") or {}) if isinstance(contact.get("basic_info"), dict) else {}
    scene_npc = profile.get("scene_npc") if isinstance(profile.get("scene_npc"), dict) else {}

    grade = str(b_info.get("grade") or contact.get("grade") or scene_npc.get("grade") or "").strip()
    club = str(b_info.get("club") or contact.get("club") or scene_npc.get("club") or faction or "").strip()
    activity = str(scene_npc.get("activity") or b_info.get("initial_activity") or "").strip()

    role_low = raw_role.lower()
    grade_low = grade.lower()
    club_low = club.lower()
    has_real_club = club_low not in ("", "none", "unaffiliated", "general", "faculty", "town", "staff", "administration")

    is_faculty_or_adult = bool(
        grade_low in ("faculty", "citizen", "staff")
        or b_info.get("is_faculty")
        or b_info.get("social_role_type") in ("faculty_staff", "adult_service")
        or any(
            w in role_low
            for w in (
                "teacher", "professor", "principal", "vice-principal", "dean", "counselor",
                "nurse", "librarian", "coach", "chef", "custodian", "groundskeeper", "janitor",
                "officer", "detective", "doctor", "barista", "clerk", "owner", "merchant",
                "shopkeeper", "guard", "captain", "agent", "commander", "director", "broker",
            )
        )
        and "student" not in role_low
        and "varsity" not in role_low
        and "club" not in role_low
        and "team" not in role_low
        and "class " not in role_low
    )

    is_student_or_peer = (not is_faculty_or_adult) and bool(
        grade_low in ("freshman", "sophomore", "junior", "senior", "student", "youth peer")
        or b_info.get("social_role_type") == "student_peer"
        or any(k in scen_key for k in ("high_school", "academy", "school"))
        or any(
            w in role_low
            for w in (
                "student", "classmate", "freshman", "sophomore", "junior", "senior",
                "clown", "slacker", "delinquent", "bookworm", "informant", "gamer",
                "tinkerer", "trendsetter", "sketch artist", "musician", "volunteer",
                "tutor", "skateboarder", "representative", "council", "varsity",
                "sprinter", "runner", "swimmer", "prodigy", "rookie", "columnist",
            )
        )
    )

    public_role = format_public_character_role(raw_role, grade=grade, club=club, scen_key=scen_key)
    v_clean = venue_leaf if venue_leaf not in ("", "here", "this spot") else ""

    if is_student_or_peer:
        if has_real_club:
            role_phrase = f"{pron['poss']} activities with the {club}"
            handle_phrase = f"everything with the {club} and classes"
            inspire_phrase = f"what first got {pron['obj']} into the {club}"
        elif activity and len(activity) <= 48:
            role_phrase = f"what {pron['subj']} {pron['is_are']} up to right now ({activity.lower()})"
            handle_phrase = "keeping up with classes and campus life"
            inspire_phrase = f"what {pron['subj']} {pron['enjoys_enjoy']} most about life at the academy"
        elif v_clean:
            role_phrase = f"what brings {pron['obj']} to the {v_clean} today"
            handle_phrase = "keeping up with classes and campus life"
            inspire_phrase = f"what {pron['subj']} {pron['enjoys_enjoy']} most about life at the academy"
        else:
            role_phrase = f"how {pron['poss']} classes and semester are going"
            handle_phrase = "keeping up with classes and campus life"
            inspire_phrase = f"what {pron['subj']} {pron['wants_want']} to pursue after graduation"

        return {
            "is_student_or_peer": "1",
            "public_role": public_role,
            "role_phrase": role_phrase,
            "handle_phrase": handle_phrase,
            "inspire_phrase": inspire_phrase,
            "unwind_outside_phrase": "after class and on weekends",
            "off_duty_phrase": "after school and on weekends",
            "outside_work_phrase": "outside of class",
            "duration_question": f"Ask {partner} which classes, clubs, or campus hangouts {pron['subj']} {pron['likes_like']} best",
        }

    clean_r = public_role or raw_role
    if clean_r:
        if any(k in scen_key for k in ("high_school", "academy", "school")) and is_faculty_or_adult:
            role_phrase = f"{pron['poss']} role on campus as {clean_r}"
            handle_phrase = f"{pron['poss']} responsibilities as {clean_r}"
            inspire_phrase = f"what inspired {pron['obj']} to become a {clean_r}"
            unwind_outside = "outside of school hours"
            off_duty = "outside of school hours"
            outside_work = "outside of campus life"
            duration_q = f"Ask {partner} how long {pron['subj']} {pron['has_have']} been with the academy"
        else:
            role_phrase = f"{pron['poss']} work as {clean_r}"
            handle_phrase = f"{pron['poss']} responsibilities as {clean_r}"
            inspire_phrase = f"what originally inspired {pron['obj']} to pursue being a {clean_r}"
            unwind_outside = f"outside of {pron['poss']} duties as {clean_r}"
            off_duty = f"in {pron['poss']} free time off duty"
            outside_work = "outside of work"
            duration_q = f"Ask {partner} how long {pron['subj']} {pron['has_have']} been around {v_clean or 'here'}"
    elif faction:
        role_phrase = f"{pron['poss']} involvement with {faction}"
        handle_phrase = f"{pron['poss']} role in {faction}"
        inspire_phrase = f"how {pron['subj']} first got involved with {faction}"
        unwind_outside = f"in {pron['poss']} free time"
        off_duty = f"in {pron['poss']} free time"
        outside_work = f"from {pron['poss']} personal life"
        duration_q = f"Ask {partner} how long {pron['subj']} {pron['has_have']} been around {v_clean or 'here'}"
    else:
        role_phrase = f"what brings {pron['obj']} to {v_clean}" if v_clean else f"{pron['poss']} background and daily routine"
        handle_phrase = f"{pron['poss']} daily routine"
        inspire_phrase = f"{pron['poss']} background and what drives {pron['obj']}"
        unwind_outside = f"in {pron['poss']} free time"
        off_duty = f"in {pron['poss']} free time"
        outside_work = f"from {pron['poss']} personal life"
        duration_q = f"Ask {partner} how long {pron['subj']} {pron['has_have']} been around {v_clean or 'here'}"

    return {
        "is_student_or_peer": "",
        "public_role": clean_r,
        "role_phrase": role_phrase,
        "handle_phrase": handle_phrase,
        "inspire_phrase": inspire_phrase,
        "unwind_outside_phrase": unwind_outside,
        "off_duty_phrase": off_duty,
        "outside_work_phrase": outside_work,
        "duration_question": duration_q,
    }


def sanitize_contextual_dialogue_label(
    label: str,
    profile: Optional[Dict[str, Any]],
    session: Optional[Dict[str, Any]] = None,
) -> str:
    """Rewrites meta-trope 'job' phrasing for students and aligns gendered pronouns."""
    raw = str(label or "").strip()
    if not raw or not isinstance(profile, dict):
        return raw
    sess = session if isinstance(session, dict) else {}
    curr_loc = str(sess.get("current_location") or "").strip()
    venue_leaf = curr_loc.split("➔")[-1].strip() if curr_loc else "here"
    ctx_phrases = _build_contextual_role_and_leisure_phrases(profile, sess, venue_leaf)
    is_student = bool(ctx_phrases.get("is_student_or_peer"))
    partner = str(profile.get("name") or "").strip()
    pron = profile.get("_cached_pronouns")
    if not isinstance(pron, dict):
        pron = resolve_partner_pronouns(profile=profile, partner_name=partner)
        profile["_cached_pronouns"] = pron
    subj = pron["subj"]
    poss = pron["poss"]
    low = raw.lower()

    if is_student or any(
        t in low
        for t in (
            "class clown", "slacker", "rebellious delinquent", "introverted bookworm",
            "gossip informant", "cafeteria gamer", "tech tinkerer", "trendsetter",
        )
    ):
        if re.search(r"\b(?:their|her|his\s+)?(?:work|job|career|profession|duties)\s+as\b", low):
            raw = re.sub(
                r"\b(?:their|her|his\s+)?(?:work|job|career|profession|duties)\s+as\s+[^,.?!]+",
                ctx_phrases["role_phrase"],
                raw,
                flags=re.IGNORECASE,
            )
        if "when they are off duty" in low or "when off duty" in low:
            raw = re.sub(r"\bwhen\s+(?:they\s+are\s+)?off\s+duty\b", ctx_phrases["off_duty_phrase"], raw, flags=re.IGNORECASE)
        if "outside of work" in low or "outside work" in low:
            raw = re.sub(r"\boutside\s+(?:of\s+)?work\b", ctx_phrases["outside_work_phrase"], raw, flags=re.IGNORECASE)

    if subj in ("she", "he"):
        raw = re.sub(r"\bask\s+how\s+their\s+day\b", f"ask how {poss} day", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\bpolitely\s+how\s+their\s+day\b", f"politely how {poss} day", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\bwhat\s+they\s+love\s+doing\b", f"what {subj} {pron['loves_love']} doing", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\bwhat\s+they\s+usually\s+enjoy\s+doing\b", f"what {subj} usually {pron['enjoys_enjoy']} doing", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\bcompliment\s+on\s+their\s+style\b", f"compliment on {poss} style", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\bhow\s+capably\s+they\s+handle\b", f"how capably {subj} {pron['handles_handle']}", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\bhow\s+they\s+first\s+got\s+into\b", f"how {subj} first got into", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\bhow\s+they\s+have\s+really\s+been\s+holding\s+up\b", f"how {subj} {pron['has_have']} really been holding up", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\babout\s+their\s+([a-z0-9_-]+)\s+streak\b", rf"about {poss} \g<1> streak", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\babout\s+their\s+fondness\s+for\b", f"about {poss} fondness for", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\babout\s+their\s+favorite\s+spot\b", f"about {poss} favorite spot", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\bwhat\s+they\s+know\s+regarding\b", f"what {subj} {pron['knows_know']} regarding", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\bif\s+they\s+have\s+heard\b", f"if {subj} {pron['has_have']} heard", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\bwhat\s+is\s+on\s+their\s+mind\b", f"what is on {poss} mind", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\bwhat\s+they\s+know\b", f"what {subj} {pron['knows_know']}", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\bsecret\s+they\s+rarely\s+share\b", f"secret {subj} rarely {pron['shares_share']}", raw, flags=re.IGNORECASE)

    return raw


def synthesize_choice_from_seed(
    seed: Dict[str, Any],
    profile: Dict[str, Any],
    session: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Builds a grounded player-facing choice button from a server-dealt social seed when an LLM slot is missing."""
    sess = session if isinstance(session, dict) else {}
    target = str(seed.get("target_npc") or profile.get("name") or "them").strip()
    pron = resolve_partner_pronouns(profile=profile, partner_name=target)
    curr_loc = str(sess.get("current_location") or "").strip()
    venue_leaf = curr_loc.split("➔")[-1].strip() if curr_loc else "here"
    ctx_phrases = _build_contextual_role_and_leisure_phrases(profile, sess, venue_leaf)

    t_id = str(seed.get("topic_id") or "friendly_situational:chat").strip()
    cat = str(seed.get("category") or "friendly_situational").strip()
    stat = str(seed.get("stat") or "CHA").strip().upper()
    dc = max(3, min(12, int(seed.get("dc") or 5)))

    label_map = {
        "clear_the_air:sincere_apology": f"Own up sincerely and apologize to {target} without making excuses",
        "clear_the_air:steady_accountability": f"Hear {target} out patiently and promise concrete follow-through",
        "clear_the_air:plausible_explanation": f"Calmly explain your side to {target} so {pron['subj']} sees the full picture",
        "clear_the_air:peace_offering": f"Offer a thoughtful peace gesture to {target} to break the tension",
        "clear_the_air:stand_ground": f"Stand your ground with {target} and address the friction head-on",
        "get_to_know:interests": f"Ask {target} what {pron['subj']} genuinely {pron['enjoys_enjoy']} {ctx_phrases['unwind_outside_phrase']}",
        "get_to_know:ambitions": f"Ask {target} about {ctx_phrases['inspire_phrase']}",
        "get_to_know:peeves": f"Lightly ask {target} what everyday habits get under {pron['poss']} skin",
        "get_to_know:routine": f"Ask {target} how {pron['subj']} usually spends {pron['poss']} days around {venue_leaf or 'here'}",
        "get_to_know:covert_aura_read": f"Subtly attune your senses to read {target}'s guarded emotions",
        "friendly_situational:room_prop": f"Strike up easy conversation with {target} about {ctx_phrases['role_phrase']}",
        "friendly_situational:lend_hand": f"Offer {target} a steady, practical hand with what {pron['subj']} {pron['is_are']} doing",
        "friendly_situational:unwind": f"Share a grounded breather with {target} about the pace around {venue_leaf or 'here'}",
        "humor_banter:witty_remark": f"Trade a dry, observational quip with {target} about the moment",
        "humor_banter:playful_tease": f"Offer {target} some light, good-natured banter",
        "humor_banter:lucky_riff": f"Crack an off-the-cuff, disarming joke with {target}",
        "humor_banter:deft_bit": f"Play off the moment with {target} using quick, nimble humor",
        "flirt_chemistry:subtle_charm": f"Offer {target} a warm, attentive compliment with a hint of charm",
        "flirt_chemistry:lingering_gaze": f"Hold {target}'s gaze and remark on something striking about {pron['obj']}",
        "flirt_chemistry:bold_chemistry": f"Flirt boldly with {target} to test the chemistry between you",
        "friction_rivalry:friendly_challenge": f"Issue {target} a spirited, competitive challenge to test {pron['poss']} mettle",
        "friction_rivalry:sharp_pushback": f"Push back firmly on {target}'s stance and hold your ground",
        "friction_rivalry:call_bluff": f"Call {target} out directly on what {pron['subj']} {pron['is_are']} holding back",
        "callbacks_history:shared_moment": f"Check in with {target} on how {pron['subj']} {pron['has_have']} been holding up lately",
        "callbacks_history:mutual_ties": f"Ask {target} about mutual acquaintances and local happenings",
    }

    if t_id.startswith("friendly_situational:gossip_"):
        cue = str(seed.get("prompt_cue") or "")
        m_ev = re.search(r"'([^']+)'", cue)
        ev_title = m_ev.group(1) if m_ev else "the latest talk around town"
        lbl = f"Chat casually with {target} about '{ev_title}'"
    else:
        lbl = label_map.get(t_id) or f"Talk with {target}: {str(seed.get('prompt_cue') or 'keep the conversation going').split('(')[0].strip()}"

    if seed.get("is_direct_reply") and not lbl.lower().startswith(("answer ", "reply ", "own up", "calmly")):
        lbl = f"Answer {target} and {lbl[0].lower() + lbl[1:]}"

    return {
        "label": sanitize_contextual_dialogue_label(lbl[:180], profile, session=sess),
        "stat": stat,
        "requirement": dc,
        "mp_cost": int(seed.get("mp_cost") or 0),
        "intent": "dialogue_init",
        "topic_id": t_id,
        "category": cat,
        "target_npc": target,
        "is_direct_reply": bool(seed.get("is_direct_reply")),
        "is_covert_ability": bool(seed.get("is_covert_ability")),
        "is_fallback": False,
        "_deterministic_supplement": True,
        "_band": 2,
        "_server_stamped": True,
    }


def generate_band1_quest_and_rumor_fallbacks(
    profile: Dict[str, Any],
    session: Optional[Dict[str, Any]],
    char: Optional[Dict[str, Any]] = None,
    actions: Optional[List[Any]] = None,
    active_quests: Optional[List[Any]] = None,
    ledgers_getter: Optional[Callable[[Optional[Dict[str, Any]]], Dict[str, Dict[str, Any]]]] = None,
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    """Generates deterministic Band 1 skill-check choices prioritizing active quests/bounties and discovered rumors."""
    sess = session if isinstance(session, dict) else {}
    sess_id = sess.get("id")
    scen_key = str(sess.get("scenario") or "fantasy").lower()
    partner = str(profile.get("name") or "them").strip()
    pron = profile.get("_cached_pronouns")
    if not isinstance(pron, dict):
        pron = resolve_partner_pronouns(profile=profile, partner_name=partner)
        profile["_cached_pronouns"] = pron
    role = str(profile.get("role") or "").strip()
    recent = _recent_action_labels_lower(sess, actions=actions, partner_name=partner, ledgers_getter=ledgers_getter)

    candidates: List[Dict[str, Any]] = []

    if sess_id:
        try:
            if active_quests is None:
                active_quests = db.get_session_quests(int(sess_id), status="Active") or []
            for q in active_quests[:3]:
                q_title = str(q.get("title") or "").strip()
                q_id = str(q.get("quest_id") or q.get("id") or "")
                is_bounty = "bounty" in str(q.get("quest_type") or "").lower() or q_id.lower().startswith("bnt-")
                if q_title:
                    lbl = (
                        f"Question {partner} for field leads on '{q_title}'"
                        if is_bounty
                        else f"Ask {partner} what {pron['subj']} {pron['knows_know']} regarding '{q_title}'"
                    )
                    candidates.append({
                        "label": lbl[:180],
                        "stat": "CHA",
                        "requirement": 6,
                        "mp_cost": 0,
                        "intent": "investigate_clue",
                        "target_npc": partner,
                        "quest_id": q_id,
                        "_active_quest_inquiry": True,
                        "is_fallback": False,
                        "_deterministic_supplement": True,
                        "_band": 1,
                    })
                    candidates.append({
                        "label": f"Cross-check details about '{q_title}' with {partner}"[:180],
                        "stat": "INT",
                        "requirement": 6,
                        "mp_cost": 0,
                        "intent": "investigate_clue",
                        "target_npc": partner,
                        "quest_id": q_id,
                        "_active_quest_inquiry": True,
                        "is_fallback": False,
                        "_deterministic_supplement": True,
                        "_band": 1,
                    })
        except Exception:
            pass

    _snap_b1_local = (sess.get("_world_events_snapshot") or db.get_world_events_snapshot(int(sess["id"]))) if sess.get("id") else None

    if sess.get("id") and isinstance(_snap_b1_local, dict):
        try:
            from mechanics.world.world_events.modifiers import compute_rumor_defensive_dc
            from mechanics.world.world_events.social_hooks import can_break_news_today, is_npc_aware_of_event
            _sid_we = int(sess["id"])
            _npc_slug = str(partner or "").strip().lower().replace(" ", "_")
            _curr_d = int(sess.get("current_day") or 1)
            _def_dc = compute_rumor_defensive_dc(_snap_b1_local, npc_name=partner)
            for _rm in (_snap_b1_local.get("discovered_rumors") or [])[:2]:
                if _rm.get("status") != "active":
                    continue
                _rm_title = str(_rm.get("title") or "the rumor").strip()
                _ev_k = str(_rm.get("event_key") or "")
                _rm_qid = str(_rm.get("linked_quest_id") or "")
                if is_npc_aware_of_event(_sid_we, _ev_k, _npc_slug):
                    _cand_rm = {
                        "label": f"Press {partner} for leads on '{_rm_title}'"[:180],
                        "stat": "CHA",
                        "requirement": 6 + _def_dc,
                        "mp_cost": 0,
                        "intent": "investigate_clue",
                        "target_npc": partner,
                        "event_key": _ev_k,
                        "_is_world_rumor_inquiry": True,
                        "is_fallback": False,
                        "_deterministic_supplement": True,
                        "_band": 1,
                    }
                    if _rm_qid:
                        _cand_rm["quest_id"] = _rm_qid
                        _cand_rm["linked_quest_id"] = _rm_qid
                        _cand_rm["is_quest_action"] = True
                    candidates.append(_cand_rm)
                elif can_break_news_today(_sid_we, _curr_d, _npc_slug, pity_state=_snap_b1_local.get("pity_state")):
                    candidates.append({
                        "label": f"[Break the News] Share what you heard about '{_rm_title}' with {partner}"[:180],
                        "stat": "CHA",
                        "requirement": 5,
                        "mp_cost": 0,
                        "intent": "break_the_news",
                        "target_npc": partner,
                        "event_key": _ev_k,
                        "_is_break_the_news": True,
                        "is_fallback": False,
                        "_deterministic_supplement": True,
                        "_band": 1,
                    })
        except Exception:
            pass

    if sess.get("id") and isinstance(_snap_b1_local, dict):
        try:
            from mechanics.world.world_events import extract_minor_events, is_npc_aware_of_minor_event
            _sid_mnr = int(sess["id"])
            _npc_slug_mnr = str(partner or "").strip().lower().replace(" ", "_")
            _curr_loc_mnr = str(sess.get("current_location") or "")
            for _mev in extract_minor_events(_snap_b1_local, statuses=("active",)):
                _l_qid = str(_mev.get("linked_quest_id") or "")
                if _mev.get("status") == "active" and _l_qid.upper().startswith("MNR-"):
                    if is_npc_aware_of_minor_event(_sid_mnr, _mev, _npc_slug_mnr, npc_profile=profile, current_location=_curr_loc_mnr):
                        _m_title = str(_mev.get("title") or "the local incident").strip()
                        candidates.append({
                            "label": f"Ask {partner} what {pron['subj']} noticed about '{_m_title}'"[:180],
                            "stat": "PER",
                            "requirement": 5,
                            "mp_cost": 0,
                            "intent": "investigate_clue",
                            "target_npc": partner,
                            "event_key": str(_mev.get("event_key") or ""),
                            "quest_id": _l_qid,
                            "linked_quest_id": _l_qid,
                            "is_quest_action": True,
                            "_is_world_rumor_inquiry": True,
                            "is_fallback": False,
                            "_deterministic_supplement": True,
                            "_band": 1,
                        })
                        break
        except Exception:
            pass

    if scenario_data.is_anomalous_high_school_scenario(scen_key) or scenario_data.is_anomalous_incursions_scenario(scen_key):
        rumor_specs = [
            ("INT", f"Query {partner} about strange occurrences or anomalous readings nearby", 6),
            ("CHA", f"Ask {partner} if {pron['subj']} {pron['has_have']} heard any notable rumors lately", 6),
        ]
    elif any(k in scen_key for k in ("high_school", "academy", "school")):
        rumor_specs = [
            ("CHA", f"Ask {partner} if {pron['subj']} {pron['has_have']} heard any notable campus rumors lately", 6),
            ("INT", f"Inquire with {partner} about upcoming school events or student council news", 5),
        ]
    else:
        from mechanics.social.relationships import format_public_character_role
        pub_role = format_public_character_role(role, scen_key=scen_key)
        role_hint = f" as {pub_role}" if (pub_role and len(pub_role) < 28) else ""
        rumor_specs = [
            ("CHA", f"Ask {partner} about recent local rumors, bounties, or trouble in the area", 6),
            ("INT", f"Question {partner} for practical intel {pron['subj']} {pron['has_have']} noticed{role_hint}", 6),
        ]

    for st, lbl, dc in rumor_specs:
        candidates.append({
            "label": lbl,
            "stat": st,
            "requirement": dc,
            "mp_cost": 0,
            "intent": "investigate_clue",
            "target_npc": partner,
            "_is_generic_rumor": True,
            "is_fallback": False,
            "_deterministic_supplement": True,
            "_band": 1,
        })

    return [c for c in candidates if not _is_similar_to_recent(c["label"], recent)]


def generate_band2_social_choices(
    profile: Dict[str, Any],
    session: Optional[Dict[str, Any]],
    actions: Optional[List[Any]] = None,
    party: Optional[List[Any]] = None,
    ledgers_getter: Optional[Callable[[Optional[Dict[str, Any]]], Dict[str, Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """Generates dynamic 7-SPECIAL, fixed DC 3-12 Sims-style social choices for Band 2."""
    sess = session if isinstance(session, dict) else {}
    partner = str(profile.get("name") or "them").strip()
    recent = _recent_action_labels_lower(sess, actions=actions, partner_name=partner, ledgers_getter=ledgers_getter)

    pre_seeds = sess.get("_dealt_social_seeds")
    if isinstance(pre_seeds, list) and pre_seeds:
        seeds = [s for s in pre_seeds if isinstance(s, dict)]
    else:
        seeds = deck.deal_social_deck_seeds(
            session=sess,
            partners=[partner],
            party=party,
            desired_count=6,
        )

    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for s in seeds:
        ch = synthesize_choice_from_seed(s, profile, session=sess)
        lk = ch["label"].lower()
        if lk in seen or _is_similar_to_recent(ch["label"], recent):
            continue
        seen.add(lk)
        out.append(ch)
    return out
