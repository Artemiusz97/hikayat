from __future__ import annotations

"""
Deterministic 3-Band Conversation Choice Engine & Urgent Schedule Departure State Machine.

Responsibilities:
1. Resolves active partner relationship profiles (Stranger / Acquaintance / Friend+ / Romantic,
   Private Meetup, Companion, Home/Office status, and active Quest/Bounty hooks).
2. Enforces the 3-Band Conversation Choice Architecture (up to 7-8 options):
   - Band 1 (2-4 slots): Skill-check quest/bounty/rumor/intel inquiries (quest/bounty prioritized).
   - Band 2 (1-3 slots): Affinity-scaled social/background options (mostly FREE; [CHA] for bold moves).
   - Band 3 (Final pinned slot): Standardized FREE "Leave conversation..." (never truncated).
3. Manages the 2-Stage Urgent Schedule Departure State Machine:
   - Stage 1 Warning ("I need to go soon"): Adds [CHA] Convince to stay + +3 DC / CHA DC 9 hurry checks.
   - Stage 2 Ultimatum: Overrides to strictly 2 choices ([CHA] Convince to stay | Leave / Let head out);
     any Custom Action auto-fails and causes immediate departure.
   - 5-Turn Stay Extension: Capped once per time-block; auto-departs on the 5th bonus turn.
   - Private Meetup Exemption: Suppresses hurry stages; on player Leave Conversation at non-home venues,
     NPC mentions needing to head out too, says goodbye, and physically relocates to scheduled location.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import db
import namegen
import scenario_data
from mechanics.social.relationships import (
    clamp_score,
    get_disclosure_check_requirement,
    get_relationship_tier,
)

log = logging.getLogger(__name__)

# ── Regex Guardrails for Affinity & Action Filtering ─────────────────────────

_CONVINCE_STAY_RE = re.compile(
    r"\b(?:convince|persuade|beg|urge|coax|plead\s+with|ask)\b.*?\b(?:to\s+)?stay\b"
    r"(?:.*?\b(?:longer|here|little|bit|while|minutes|more)\b)?",
    re.IGNORECASE,
)

_WALK_WITH_RE = re.compile(
    r"^\s*(?:walk\s+with|stroll\s+with|accompany|go\s+with|head\s+(?:out\s+|over\s+)?with|tag\s+along\s+with|escort)\s+(.+)$",
    re.IGNORECASE,
)

_COMPLIMENT_RE = re.compile(
    r"\b(?:compliment|flatter|praise\s+(?:her|his|their)|admire\s+(?:her|his|their)|"
    r"tell\s+(?:her|him|them)\s+(?:she|he|they)\s+look|comment\s+on\s+how\s+(?:cute|pretty|handsome|gorgeous|attractive|stunning))\b",
    re.IGNORECASE,
)

_WITTY_OR_BANTER_RE = re.compile(
    r"\b(?:witty\s+(?:observation|remark|comment|quip|banter|line)|"
    r"wry\s+(?:observation|remark|comment|quip|joke)|"
    r"lighthearted\s+(?:observation|tease|banter|joke)|"
    r"playfully\s+(?:tease|rib|poke\s+fun|banter|comment|joke)|"
    r"crack\s+a\s+(?:playful\s+|lighthearted\s+|quick\s+|dry\s+)?joke|"
    r"(?:tell|make|share)\s+a\s+(?:playful\s+|lighthearted\s+|dry\s+|wry\s+)?(?:joke|quip)|"
    r"\btease\s+(?:her|him|them|[A-Z][a-z]+)\b|"
    r"\bbanter\s+(?:with|casually)\b|"
    r"\bflirt\s+with\b|\bwink\s+at\b)\b",
    re.IGNORECASE,
)

_HEAVY_TEASE_OR_FLIRT_RE = re.compile(
    r"\b(?:playfully\s+tease|tease\s+(?:her|him|them|[A-Z][a-z]+)|flirt\s+with|wink\s+at|"
    r"seductive|whisper\s+flirtatiously|brush\s+(?:her|his|their)\s+(?:hand|cheek|hair|lips)|"
    r"hold\s+(?:her|his|their)\s+hand|pull\s+(?:her|him|them)\s+close)\b",
    re.IGNORECASE,
)

_ROMANTIC_ADVANCE_RE = re.compile(
    r"\b(?:flirt\s+with|wink\s+at|seductive|whisper\s+flirtatiously|"
    r"brush\s+(?:her|his|their)\s+(?:hand|cheek|hair|lips)|"
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

_QUEST_OR_INTEL_KEYWORDS = (
    "quest", "bounty", "contract", "case", "clue", "lead", "evidence", "rumor", "rumour",
    "anomaly", "anomalous", "incursion", "breach", "resonance", "containment", "suspect",
    "witness", "incident", "report", "reading", "readings", "patrol", "sector", "intel",
    "investigat", "analyze", "deduce", "examine", "inspect", "interrogate", "question",
    "probe", "query", "gauge", "read her", "read his", "read their", "body language",
    "guild", "dossier", "briefing", "disappearance", "artifact", "signal", "ledger",
)

_SOCIAL_BACKGROUND_KEYWORDS = (
    "background", "how long", "hometown", "family", "hobby", "hobbies", "interest",
    "outside of work", "off duty", "off-duty", "free time", "favorite", "favourite",
    "what got", "what inspired", "inspired", "join the", "joined the", "career",
    "studies", "major", "club", "day is going", "holding up", "compliment", "joke",
    "banter", "tease", "weather", "walk with", "stroll with", "chat casually",
    "get to know", "personal life", "childhood", "dream",
)


def _canon_npc_key(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip().lower())


def _locations_match(loc_a: str, loc_b: str, session_id: Optional[int] = None, node_a: str = "", node_b: str = "") -> bool:
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
        # Same primary building/venue (Tier 2) or same leaf sub-room (Tier 3) counts as same venue
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
                # Pass empty dict (not None) when empty so update_session overwrites rather than deletes or skips
                db.update_session(int(sess_id), extra={"npc_departure_states": clean_states})
            except Exception as e:
                log.warning("Failed persisting npc_departure_states: %s", e)


# ── Per-NPC Daily Conversation Ledger & Pacing Budget ─────────────────────────


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
    out: Dict[str, Dict[str, Any]] = {}
    for k, v in raw.items():
        if k and isinstance(v, dict):
            out[str(k)] = dict(v)
    return out


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


def _extract_topic_signature(label: str) -> str:
    """Maps a social/background choice label to a semantic topic signature so rephrased duplicates don't repeat."""
    lbl_low = str(label or "").strip().lower()
    if not lbl_low:
        return ""
    if any(k in lbl_low for k in ("phone number", "contact info", "line id")):
        return "contact_exchange"
    if any(k in lbl_low for k in ("work as ", "role in ", "role as ", "duty as ", "current assignment", "career path")):
        return "work_role"
    if any(k in lbl_low for k in ("how long", "stationed", "classes or club", "busiest")):
        return "stationed_duration"
    if any(k in lbl_low for k in ("off duty", "off-duty", "free time", "outside of work", "hobby", "hobbies", "enjoy doing")):
        return "hobbies_offduty"
    if any(k in lbl_low for k in ("favorite spot", "favourite spot", "grab a bite", "coffee", "unwind around", "favorite food")):
        return "favorite_spot_food"
    if any(k in lbl_low for k in ("proudest", "personal story", "what inspired", "what got", "growing up", "hometown", "childhood", "fondest memory")):
        return "personal_story"
    if any(k in lbl_low for k in ("really been holding up", "day is going", "on their mind", "how they are holding up")):
        return "day_checkin"
    if any(k in lbl_low for k in ("atmosphere around", "vibe here", "crowd today", "pace around here", "enjoy the moment together")):
        return "venue_atmosphere"
    if _ROMANTIC_ADVANCE_RE.search(label):
        return "flirt_romance"
    if _COMPLIMENT_RE.search(label):
        return "compliment"
    if any(k in lbl_low for k in ("joke", "quip", "playful banter", "wry observation", "lighthearted observation", "playfully tease")):
        return "joke_banter"
    if any(k in lbl_low for k in ("walk with ", "stroll with ", "accompany ")):
        return "walk_together"
    if "clear the air" in lbl_low:
        return "clear_air"
    return ""


def get_partner_conversation_budget_state(
    session: Optional[Dict[str, Any]],
    profile: Dict[str, Any],
) -> Dict[str, Any]:
    """Pure reader returning remaining daily non-quest conversation budget and asked topics for an NPC."""
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
        # Entering a scheduled Private Meetup / Date grants a fresh full budget
        turns_used = 0
        bonus_turns = 0
    elif last_blk and last_blk != curr_blk and curr_blk not in rechecked:
        # Catching up again in a later time block grants +2 check-in turns
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
    """Determines whether an action consumes 1 turn of the NPC's non-quest social conversation budget."""
    if not isinstance(action_dict, dict):
        return False
    lbl = str(action_dict.get("label") or action_dict.get("text") or action_dict.get("action") or "").strip()
    if not lbl:
        return False
    lbl_low = lbl.lower()
    intent = str(action_dict.get("intent") or "").lower()
    if (
        action_dict.get("_pinned_dialogue_exit")
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
    ):
        return False
    # Pure conversation-opening greeting ("Speak with Putri Wijaya") on Turn 0 does NOT burn a question slot
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
    """Records asked labels/topics and increments turns_used for non-quest social dialogue turns."""
    if not isinstance(session, dict) or not partner_name:
        return {}
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
        # Record non-opening-greeting labels so the exact option does not repeat back-to-back
        if not _OPENING_GREETING_RE.match(lbl) or " about " in lbl_low:
            if lbl_low not in asked_labels:
                asked_labels.append(lbl_low)
            sig = str(a.get("_topic_sig") or _extract_topic_signature(lbl) or "").strip()
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


def _find_contact_and_lore(session_id: Optional[int], partner_name: str, char_id: int = 0) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
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

    # 1. Check Party & Temporary Companion Status
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

    # 2. Check Active Private Meetup / Rendezvous Status
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

    # 3. Check if Current Scene is the NPC's Own Home / Bedroom / Personal Office
    is_npc_home_or_office = False
    loc_low = curr_loc.lower()
    home_loc = str(
        b_info.get("residence")
        or b_info.get("home_location")
        or b_info.get("residence_location")
        or ""
    ).strip()
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
            sched_map = get_npc_schedule(
                npc_ref, scen_key=scen_key, session_id=session_id, current_day=curr_day, current_minute=curr_min
            )
            night_home = str((sched_map or {}).get("night") or "").strip()
            if night_home and any(
                w in loc_low for w in ("bedroom", "apartment", "residence", "dorm", "house", "quarters", "suite")
            ) and _locations_match(curr_loc, night_home, session_id=session_id):
                is_npc_home_or_office = True
        except Exception:
            pass

    # 4. Active Quest / Bounty Stationing Check
    is_quest_stationed_here = False
    relevant_quests: List[Dict[str, Any]] = []
    if session_id:
        try:
            active_wps = db.get_all_session_active_waypoints(session_id) or []
            for wp in active_wps:
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

    can_walk_together = bool(
        is_private_meetup
        or is_companion
        or score >= 100
        or track == "romantic"
    )

    if score >= 100 or track == "romantic":
        convince_stay_dc = 6
    elif score >= 50:
        convince_stay_dc = 9
    else:
        convince_stay_dc = 12

    traits_list: List[str] = []
    for t_cand in ((contact or {}).get("traits") or b_info.get("traits") or lore_ent.get("traits") or []):
        t_str = str(t_cand or "").strip()
        if t_str and len(t_str) <= 36 and t_str not in traits_list:
            traits_list.append(t_str)

    prefs_obj = ((contact or {}).get("preferences") or {}) if isinstance((contact or {}).get("preferences"), dict) else {}
    likes_list: List[str] = []
    for raw_lk in (
        prefs_obj.get("likes")
        or prefs_obj.get("hobbies")
        or b_info.get("hobbies")
        or b_info.get("likes")
        or []
    ):
        lk_str = str(raw_lk or "").strip()
        if lk_str and len(lk_str) <= 44 and lk_str not in likes_list:
            likes_list.append(lk_str)

    return {
        "name": partner_name,
        "score": score,
        "track": track,
        "tier_level": tier_level,
        "tier_name": tier_name,
        "role": role,
        "faction": faction,
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
    """Collects contextual walk-with destinations: meetup spot, active quest waypoints, and current-zone sub-locations."""
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
        wloc = str(wp.get("target_location") or wp.get("location") or "")
        for part in wloc.split("➔"):
            if part.strip():
                valid.add(part.strip().lower())

    if sess_id:
        try:
            for q in (db.get_session_quests(int(sess_id), status="Active") or []):
                qloc = str(q.get("location") or "")
                for part in qloc.split("➔"):
                    if part.strip():
                        valid.add(part.strip().lower())
        except Exception:
            pass

        if curr_zone:
            try:
                for loc_row in (db.get_session_locations(int(sess_id)) or []):
                    zn = str(loc_row.get("zone_name") or "").strip().lower()
                    if zn == curr_zone:
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

    # Generic nearby within-venue descriptors (e.g. "a quieter corner", "the hallway", "nearby bench")
    for generic_spot in (
        "quieter corner", "quiet corner", "quieter spot", "hallway", "corridor",
        "courtyard", "balcony", "terrace", "nearby bench", "lounge", "foyer",
    ):
        valid.add(generic_spot)
    return valid


def is_convince_stay_action(action_or_label: Any) -> bool:
    if isinstance(action_or_label, dict):
        if action_or_label.get("_convince_stay") or action_or_label.get("departure_action") == "convince_stay":
            return True
        lbl = str(action_or_label.get("label") or action_or_label.get("text") or action_or_label.get("action") or "")
    else:
        lbl = str(action_or_label or "")
    return bool(_CONVINCE_STAY_RE.search(lbl))


def is_choice_allowed_for_partner_profile(
    choice: Dict[str, Any] | str,
    profile: Dict[str, Any],
    session: Optional[Dict[str, Any]] = None,
    allow_convince_stay: bool = False,
) -> bool:
    """Deterministically filters out premature flattery/banter, invalid walk-alongs, and unprompted stay checks."""
    c_dict = choice if isinstance(choice, dict) else {"label": str(choice or "")}
    lbl = str(c_dict.get("label") or c_dict.get("text") or "").strip()
    if not lbl:
        return False
    lbl_low = lbl.lower()

    # 1. Pinned exit or quest-stamped actions are always allowed (unless convince_stay check below)
    if c_dict.get("_pinned_dialogue_exit") or c_dict.get("intent") == "dialogue_exit" or c_dict.get("ends_dialogue"):
        return True

    # 2. "Convince [NPC] to stay" is strictly forbidden unless explicitly stamped in Stage 1 / Stage 2
    if is_convince_stay_action(c_dict):
        return bool(allow_convince_stay and c_dict.get("_convince_stay"))

    # 3. "Propose moving to a quieter spot" privacy nudge: block for Strangers/Negative outside meetups
    if "quieter" in lbl_low and ("propose moving" in lbl_low or "suggest moving" in lbl_low or "speak in private" in lbl_low):
        if profile["score"] < 50 and not profile["is_private_meetup"] and profile["track"] != "romantic":
            return False

    # 4. "Walk with [NPC]..." / accompany check
    m_walk = _WALK_WITH_RE.match(lbl)
    if m_walk or any(p in lbl_low for p in ("walk with ", "stroll with ", "accompany ", "tag along with ")):
        if not profile.get("can_walk_together"):
            return False
        # Validate destination if " to " / " toward " is present
        dest_match = re.search(r"\b(?:to|toward|towards|into)\s+(.+)$", lbl, re.IGNORECASE)
        if dest_match:
            dest_raw = dest_match.group(1).strip(" .,!?)(").lower()
            dest_raw = re.sub(r"^(?:the|a|an)\s+", "", dest_raw).strip()
            valid_dests = _collect_valid_walk_destinations(session, profile)
            if dest_raw and valid_dests:
                if not any(vd in dest_raw or dest_raw in vd for vd in valid_dests if len(vd) >= 4):
                    return False

    # 5. 4-Tier Affinity Social Filter (+1 tier loosening during scheduled Private Meetups / Dates)
    score = int(profile.get("score", 0))
    track = str(profile.get("track") or "platonic").lower()
    is_meetup = bool(profile.get("is_private_meetup"))
    eff_score = score + (50 if (is_meetup and score >= 0) else 0)

    if track != "romantic":
        if eff_score < 50:
            # Negative (< 0) and Stranger (0-49 outside meetup): strictly NO compliments, witty observations, jokes, banter, or teasing
            if _COMPLIMENT_RE.search(lbl) or _WITTY_OR_BANTER_RE.search(lbl):
                return False
        elif eff_score < 100:
            # Acquaintance (50-99, or Stranger on Meetup): polite compliments & light jokes allowed,
            # but block heavy teasing, flirting, or physical affection unless romantic confession milestone
            if c_dict.get("intent") != "romantic_confession" and _HEAVY_TEASE_OR_FLIRT_RE.search(lbl):
                return False
        elif eff_score < 150:
            # Friend (100-149, or Acquaintance on Meetup): playful teasing & banter allowed,
            # overt romantic/seductive flirtation unlocks at Close (150+) / Romantic / Friend+ Meetup
            if c_dict.get("intent") != "romantic_confession" and _ROMANTIC_ADVANCE_RE.search(lbl):
                return False

    return True


def build_pinned_leave_choice(partners: List[str]) -> Dict[str, Any]:
    """Builds the standardized, pinned Band 3 Leave Conversation choice."""
    clean_partners = [str(p).strip() for p in (partners or []) if str(p).strip()]
    if len(clean_partners) == 1:
        label = f"Leave conversation with {clean_partners[0]}"
    else:
        label = "Leave conversation"
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


def _recent_action_labels_lower(
    session: Optional[Dict[str, Any]],
    limit: int = 25,
    actions: Optional[List[Any]] = None,
    partner_name: str = "",
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
        if partner_name:
            curr_day = int(session.get("current_day") or 1)
            l_key = f"{curr_day}:{_canon_npc_key(partner_name)}"
            ledgers = get_npc_conversation_ledgers(session)
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
                # Support formatted string history "[SUCCESS] Hero: Action label -> ..."
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


def generate_band1_quest_and_rumor_fallbacks(
    profile: Dict[str, Any],
    session: Optional[Dict[str, Any]],
    char: Optional[Dict[str, Any]] = None,
    actions: Optional[List[Any]] = None,
) -> List[Dict[str, Any]]:
    """Generates deterministic Band 1 skill-check choices prioritizing active quests/bounties, then local rumors/intel."""
    sess = session if isinstance(session, dict) else {}
    sess_id = sess.get("id")
    scen_key = str(sess.get("scenario") or "fantasy").lower()
    partner = str(profile.get("name") or "them").strip()
    role = str(profile.get("role") or "").strip()
    recent = _recent_action_labels_lower(sess, actions=actions, partner_name=partner)

    candidates: List[Dict[str, Any]] = []

    # Priority 1: Active quests / bounties from DB
    if sess_id:
        try:
            active_quests = db.get_session_quests(int(sess_id), status="Active") or []
            for q in active_quests[:3]:
                q_title = str(q.get("title") or "").strip()
                q_id = str(q.get("id") or q.get("quest_id") or "")
                is_bounty = "bounty" in str(q.get("quest_type") or "").lower() or q_id.lower().startswith("bnt-")
                if q_title:
                    lbl = (
                        f"Question {partner} for field leads on '{q_title}'"
                        if is_bounty
                        else f"Ask {partner} what they know regarding '{q_title}'"
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
                    lbl_int = f"Cross-check details about '{q_title}' with {partner}"
                    candidates.append({
                        "label": lbl_int[:180],
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

    # Priority 2: Scenario-grounded rumor & situational intel skill checks
    if scenario_data.is_anomalous_incursions_scenario(scen_key):
        rumor_specs = [
            ("INT", f"Query {partner} about recent anomalous readings or breach reports nearby", 6),
            ("CHA", f"Ask {partner} about unlogged agency rumors or active containment bounties", 6),
            ("PER", f"Read {partner}'s demeanor and tactical readiness for anything they are holding back", 5),
            ("INT", f"Compare notes with {partner} on sector patrol patterns and recent dispatch alerts", 6),
        ]
    elif any(k in scen_key for k in ("high_school", "academy", "school")):
        rumor_specs = [
            ("CHA", f"Ask {partner} if they have heard any notable campus rumors lately", 6),
            ("INT", f"Inquire with {partner} about upcoming school events or student council news", 5),
            ("PER", f"Observe {partner}'s expression closely to gauge what is on their mind", 5),
            ("CHA", f"Ask {partner} what clubs or homerooms have been making noise this week", 5),
        ]
    elif "cyber" in scen_key:
        rumor_specs = [
            ("CHA", f"Ask {partner} about current street rumors, fixer jobs, or local heat", 6),
            ("INT", f"Probe {partner} for district intel and recent network anomalies", 6),
            ("PER", f"Read {partner}'s body language and subtle tells during the exchange", 5),
            ("CHA", f"Check with {partner} on who has been moving heavy chrome through this block", 6),
        ]
    else:
        role_hint = f" as {role}" if role and len(role) < 28 else ""
        rumor_specs = [
            ("CHA", f"Ask {partner} about recent local rumors, bounties, or trouble in the area", 6),
            ("INT", f"Question {partner} for practical intel they have noticed{role_hint}", 6),
            ("PER", f"Study {partner}'s expression and posture to gauge what they know", 5),
            ("CHA", f"Ask {partner} whether any unusual travelers or incidents turned up today", 5),
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
) -> List[Dict[str, Any]]:
    """Generates dynamic, non-repeating 4-tier + Meetup/Date social choices for Band 2."""
    sess = session if isinstance(session, dict) else {}
    scen_key = str(sess.get("scenario") or "fantasy").lower()
    partner = str(profile.get("name") or "them").strip()
    role = str(profile.get("role") or "").strip()
    faction = str(profile.get("faction") or "").strip()
    score = int(profile.get("score", 0))
    track = str(profile.get("track") or "platonic").lower()
    is_meetup = bool(profile.get("is_private_meetup"))
    can_walk = bool(profile.get("can_walk_together"))
    likes = [str(x).strip() for x in (profile.get("likes") or []) if str(x).strip()]
    traits = [str(x).strip() for x in (profile.get("traits") or []) if str(x).strip()]

    curr_loc = str(sess.get("current_location") or "").strip()
    venue_leaf = curr_loc.split("➔")[-1].strip() if curr_loc else "here"
    if len(venue_leaf) > 36 or not venue_leaf:
        venue_leaf = "this spot"

    budget_state = get_partner_conversation_budget_state(sess, profile)
    asked_sigs = set(budget_state.get("asked_topic_signatures") or [])
    recent = _recent_action_labels_lower(sess, actions=actions, partner_name=partner)

    role_phrase = f"their work as {role}" if role else ("their role in " + faction if faction else "their background and daily routine")
    eff_score = score + (50 if (is_meetup and score >= 0) else 0)
    options: List[Dict[str, Any]] = []

    def _social_check(
        lbl: str,
        stat: str = "CHA",
        req: int = 5,
        intent: str = "dialogue_init",
        sig: str = "",
    ) -> Dict[str, Any]:
        st_clean = stat if stat in ("CHA", "INT", "PER") else "CHA"
        topic_sig = sig or _extract_topic_signature(lbl)
        return {
            "label": lbl[:180],
            "stat": st_clean,
            "requirement": max(5, int(req)),
            "mp_cost": 0,
            "intent": intent,
            "target_npc": partner,
            "_topic_sig": topic_sig,
            "is_fallback": False,
            "_deterministic_supplement": True,
            "_band": 2,
            "_server_stamped": True,
        }

    if score < 0 and not is_meetup:
        options.append(_social_check(f"Keep your tone measured and ask {partner} directly about {role_phrase}", stat="CHA", req=7, sig="work_role"))
        options.append(_social_check(f"Ask {partner} plainly what it would take to clear the air between you", stat="CHA", req=8, sig="clear_air"))
        options.append(_social_check(f"Listen calmly and read {partner}'s reservations without pressing", stat="PER", req=7, sig="day_checkin"))
    else:
        # Scheduled Private Meetup / Date prioritized personal & venue options
        if is_meetup:
            options.append(_social_check(f"Take in the vibe at {venue_leaf} with {partner} and ask how their day has been", stat="CHA", req=5, sig="venue_atmosphere"))
            if likes:
                options.append(_social_check(f"Ask {partner} more about their fondness for {likes[0]}", stat="INT", req=5, sig="hobbies_offduty"))
            else:
                options.append(_social_check(f"Ask {partner} what they love doing most to unwind outside of {role or 'work'}", stat="CHA", req=5, sig="hobbies_offduty"))
            options.append(_social_check(f"Share a lighthearted joke with {partner} over your meetup", stat="CHA", req=5, sig="joke_banter"))
            options.append(_social_check(f"Offer {partner} a warm, sincere compliment on their style today", stat="CHA", req=5, sig="compliment"))
            if eff_score >= 100 or track == "romantic":
                options.append(_social_check(f"Playfully tease {partner} and trade warm, easygoing banter", stat="CHA", req=6, sig="personal_story"))
            if eff_score >= 150 or track == "romantic":
                options.append(_social_check(f"Flirt charmingly with {partner} and lean into the chemistry between you", stat="CHA", req=6, sig="flirt_romance"))

        # Tier 1: Stranger (0-49) — Polite icebreakers, role/work, venue small talk, day check-in
        if eff_score < 50 and track != "romantic":
            options.append(_social_check(f"Ask {partner} about {role_phrase}", stat="INT", req=5, sig="work_role"))
            if any(k in scen_key for k in ("high_school", "academy", "school")):
                options.append(_social_check(f"Ask {partner} which classes or club activities keep them busiest", stat="CHA", req=5, sig="stationed_duration"))
            else:
                options.append(_social_check(f"Ask {partner} how long they have been stationed around here", stat="CHA", req=5, sig="stationed_duration"))
            options.append(_social_check(f"Make polite small talk with {partner} about the pace around {venue_leaf} today", stat="CHA", req=5, sig="venue_atmosphere"))
            options.append(_social_check(f"Gauge {partner}'s mood and ask politely how their day is going", stat="PER", req=5, sig="day_checkin"))
            options.append(_social_check(f"Ask {partner} what local spot nearby they would recommend for a break", stat="INT", req=5, sig="favorite_spot_food"))

        # Tier 2: Acquaintance (50-99) — Off-duty hobbies, known likes, light situational jokes, polite compliments
        elif eff_score < 100 and track != "romantic":
            if likes:
                options.append(_social_check(f"Ask {partner} how they first got into {likes[0]}", stat="INT", req=5, sig="hobbies_offduty"))
            else:
                options.append(_social_check(f"Ask {partner} what they usually enjoy doing when they are off duty", stat="CHA", req=5, sig="hobbies_offduty"))
            options.append(_social_check(f"Offer {partner} a polite compliment on how capably they handle {role_phrase}", stat="CHA", req=6, sig="compliment"))
            options.append(_social_check(f"Crack a lighthearted joke with {partner} about the day's routine", stat="CHA", req=5, sig="joke_banter"))
            options.append(_social_check(f"Ask {partner} about their favorite spot in town to grab food or unwind", stat="INT", req=5, sig="favorite_spot_food"))
            options.append(_social_check(f"Ask {partner} what originally inspired them to pursue {role or 'their path'}", stat="PER", req=5, sig="personal_story"))

        # Tier 3 & 4: Friend (100-149) & Close / Romantic (150+ or Romantic Track)
        else:
            options.append(_social_check(f"Share some playful banter and crack a lighthearted joke with {partner}", stat="CHA", req=5, sig="joke_banter"))
            if eff_score >= 150 or track == "romantic":
                options.append(_social_check(f"Flirt with {partner} and offer a warm, personal compliment", stat="CHA", req=6, sig="flirt_romance"))
                options.append(_social_check(f"Ask {partner} softly about a personal dream or secret they rarely share", stat="PER", req=6, sig="personal_story"))
            else:
                options.append(_social_check(f"Compliment {partner} warmly and ask how they have really been holding up", stat="CHA", req=5, sig="compliment"))
                options.append(_social_check(f"Ask {partner} to share a favorite personal story or memory from outside work", stat="INT", req=5, sig="personal_story"))
            if likes:
                options.append(_social_check(f"Trade lively opinions with {partner} about {likes[0]}", stat="INT", req=5, sig="hobbies_offduty"))
            elif traits:
                options.append(_social_check(f"Playfully tease {partner} about their {traits[0].lower()} streak", stat="CHA", req=5, sig="hobbies_offduty"))
            if can_walk:
                valid_spots = [
                    s for s in _collect_valid_walk_destinations(sess, profile)
                    if s not in {"quieter corner", "quiet corner", "quieter spot", "hallway", "corridor", "nearby bench", "foyer"}
                    and s not in str(sess.get("current_location") or "").lower()
                ]
                walk_dest = valid_spots[0].title() if valid_spots else "a nearby spot in the area"
                options.append(_social_check(f"Walk with {partner} toward {walk_dest}", stat="CHA", req=5, intent="social_invite", sig="walk_together"))

    filtered: List[Dict[str, Any]] = []
    seen_sigs_local: Set[str] = set()
    for o in options:
        sig = str(o.get("_topic_sig") or "")
        if sig and (sig in asked_sigs or sig in seen_sigs_local):
            continue
        if _is_similar_to_recent(o["label"], recent):
            continue
        if sig:
            seen_sigs_local.add(sig)
        filtered.append(o)
    return filtered


def _classify_choice_band(c: Dict[str, Any]) -> int:
    """Classifies a non-exit dialogue choice into Band 1 (Quest/Bounty/Intel Check) or Band 2 (Social/Background)."""
    if c.get("_pinned_dialogue_exit") or c.get("intent") == "dialogue_exit" or c.get("ends_dialogue"):
        return 3
    if c.get("_band") in (1, 2):
        return int(c["_band"])
    if c.get("is_quest_action") or c.get("quest_id") or c.get("clue_pair_ids"):
        return 1
    intent = str(c.get("intent") or "").lower()
    if intent in ("phone_contact_exchange", "romantic_confession", "social_invite", "affection_touch", "gift_offer"):
        return 2
    lbl_low = str(c.get("label") or "").lower()
    if any(skw in lbl_low for skw in _SOCIAL_BACKGROUND_KEYWORDS):
        return 2
    if intent == "investigate_clue" or any(qkw in lbl_low for qkw in _QUEST_OR_INTEL_KEYWORDS):
        return 1
    stat = str(c.get("stat") or "NONE").upper()
    if stat in ("INT", "PER"):
        return 1
    # CHA / NONE conversational lines without quest/intel markers belong to Band 2 social
    if any(w in lbl_low for w in ("ask ", "chat ", "talk ", "share ", "tell ", "comment ", "compliment", "joke", "banter")):
        return 2
    return 1


def _normalize_band2_stat_and_dc(
    c: Dict[str, Any],
    profile: Dict[str, Any],
    char: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ensures every Band 2 dialogue choice (questions, queries, jokes, teases, flirts, compliments) requires a skill check."""
    out = dict(c)
    out.pop("_free_social", None)
    lbl = str(out.get("label") or "")
    intent = str(out.get("intent") or "").lower()
    is_bold = bool(
        intent in ("phone_contact_exchange", "romantic_confession", "gift_offer")
        or _BOLD_SOCIAL_CHECK_RE.search(lbl)
        or (int(out.get("requirement") or 0) >= 10)
    )
    if is_bold:
        if str(out.get("stat") or "NONE").upper() in ("NONE", "FREE", ""):
            out["stat"] = "CHA"
        if int(out.get("requirement") or 0) <= 0:
            out["requirement"] = get_disclosure_check_requirement(7, int(profile.get("score", 0)), 2)
    else:
        st_u = str(out.get("stat") or "NONE").upper()
        req_u = int(out.get("requirement") or 0)
        if st_u in ("NONE", "FREE", "") or req_u <= 0:
            from game_engine.choices_cleaner import infer_choice_stat_and_dc
            new_st, new_dc = infer_choice_stat_and_dc(lbl, default_stat="CHA", default_dc=5, char=char)
            out["stat"] = new_st if new_st not in ("NONE", "FREE") else "CHA"
            out["requirement"] = max(5, int(new_dc))
        else:
            out["requirement"] = max(5, req_u)
    return out


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


def _is_verified_quest_choice(c: Dict[str, Any]) -> bool:
    return bool(
        c.get("is_climax_action")
        or c.get("is_story_quest")
        or c.get("is_quest_action")
        or c.get("quest_id")
        or c.get("clue_pair_ids")
        or c.get("_active_quest_inquiry")
    )


def enforce_conversation_choice_bands(
    cleaned_choices: List[Dict[str, Any]],
    session: Optional[Dict[str, Any]],
    partners: List[str],
    party: Optional[List[Any]] = None,
    current_npcs: Optional[List[Any]] = None,
    priority_buttons: Optional[List[Dict[str, Any]]] = None,
    actions: Optional[List[Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Organizes active conversation choices into:
      - Stage 2 Ultimatum Override (strictly 2 choices: Convince to Stay | Leave / Let Head Out), OR
      - Progressive Budget Taper (when remaining_budget == 0: ONLY Active Quest/Bounty choices + Pinned Leave), OR
      - [Optional Stage 1 Convince] + Band 1 (Skill-Check Quest/Bounty/Rumor)
        + Band 2 (Affinity-Scaled Dynamic Social/Background) + Band 3 (Pinned Leave Conversation).
    """
    clean_partners = [str(p).strip() for p in (partners or []) if str(p).strip()]
    if not clean_partners:
        return list(cleaned_choices or [])

    sess = session if isinstance(session, dict) else {}
    lead_partner = clean_partners[0]
    lead_char = None
    if party and isinstance(party, list) and party[0]:
        lead_char = party[0][0] if isinstance(party[0], (tuple, list)) else party[0]

    dep_states = get_npc_departure_states(sess)

    # Check if ANY active partner is in Stage 2 Ultimatum or Stage 1 Warning
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
    remaining_budget = int(budget_state.get("remaining_budget", 3))
    asked_sigs = set(budget_state.get("asked_topic_signatures") or [])
    recent_labels = _recent_action_labels_lower(sess, actions=actions, partner_name=lead_partner)

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

    # Combine priority buttons + cleaned choices while filtering against partner profile & anti-repeat ledger
    combined_raw: List[Dict[str, Any]] = []
    seen_lbls: Set[str] = set()
    for src in list(priority_buttons or []) + list(cleaned_choices or []):
        if not isinstance(src, dict):
            continue
        lbl = str(src.get("label") or "").strip()
        lbl_k = lbl.lower()
        if not lbl_k or lbl_k in seen_lbls:
            continue
        # Ignore old verbose exit choices; we always attach standardized Band 3 at the end
        if src.get("_pinned_dialogue_exit") or src.get("intent") == "dialogue_exit" or src.get("ends_dialogue"):
            continue
        from mechanics.narrative.intent import is_conversational_exit
        if is_conversational_exit(lbl):
            continue
        if not is_choice_allowed_for_partner_profile(
            src,
            lead_profile,
            session=sess,
            allow_convince_stay=in_stage_1,
        ):
            continue

        is_quest_c = _is_verified_quest_choice(src)
        is_contact_ex = str(src.get("intent") or "").lower() == "phone_contact_exchange"
        if not is_quest_c and not is_contact_ex and not src.get("_convince_stay"):
            if _is_similar_to_recent(lbl, recent_labels):
                continue
            sig_c = str(src.get("_topic_sig") or _extract_topic_signature(lbl) or "")
            if sig_c and sig_c in asked_sigs:
                continue

        seen_lbls.add(lbl_k)
        combined_raw.append(dict(src))

    try:
        from game_engine.choices_cleaner import deduplicate_redundant_choices
        combined_raw = deduplicate_redundant_choices(combined_raw, ignore_names=clean_partners)
    except Exception:
        pass

    band1: List[Dict[str, Any]] = []
    band2: List[Dict[str, Any]] = []

    for c in combined_raw:
        if c.get("_convince_stay"):
            continue
        b_idx = _classify_choice_band(c)
        if b_idx == 1:
            band1.append(c)
        elif b_idx == 2:
            band2.append(c)

    # Sort Band 1 so verified quest/bounty choices come first
    band1.sort(
        key=lambda x: (
            0 if _is_verified_quest_choice(x) else 1,
            0 if x.get("clue_pair_ids") else 1,
        )
    )

    # Ensure every Band 1 choice is a genuine skill check
    from game_engine.choices_cleaner import infer_choice_stat_and_dc
    for b1 in band1:
        st_u = str(b1.get("stat") or "NONE").upper()
        req_u = int(b1.get("requirement") or 0)
        if st_u in ("NONE", "FREE", "") or req_u <= 0:
            new_st, new_dc = infer_choice_stat_and_dc(b1.get("label", ""), default_stat="INT", default_dc=6, char=lead_char)
            b1["stat"] = new_st if new_st not in ("NONE", "FREE") else "INT"
            b1["requirement"] = max(5, new_dc)

    stage1_prefix: List[Dict[str, Any]] = []
    if in_stage_1 and urg_profile:
        if urg_state.get("extended_block") != curr_blk:
            stage1_prefix.append({
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

    pinned_exit = build_pinned_leave_choice(clean_partners)

    # ── CONVERSATION BUDGET EXHAUSTION: Keep ONLY Active Quest/Bounty Hooks + Leave Conversation ──
    if remaining_budget <= 0:
        quest_only_b1 = [c for c in band1 if _is_verified_quest_choice(c)]
        if not quest_only_b1:
            for fb1 in generate_band1_quest_and_rumor_fallbacks(lead_profile, sess, char=lead_char, actions=actions):
                if _is_verified_quest_choice(fb1):
                    fb_k = fb1["label"].strip().lower()
                    if fb_k not in seen_lbls:
                        seen_lbls.add(fb_k)
                        quest_only_b1.append(fb1)
                if len(quest_only_b1) >= 2:
                    break
        quest_only_b1 = quest_only_b1[:4]
        if in_stage_1 and urg_profile:
            quest_only_b1 = [_apply_stage1_hurry_gate(c) for c in quest_only_b1]
        return stage1_prefix + quest_only_b1 + [pinned_exit]

    is_meetup_social_focus = bool(lead_profile.get("is_private_meetup") and not lead_profile.get("is_quest_stationed_here"))

    if is_meetup_social_focus:
        # On scheduled Private Meetups / Dates without a stationed quest hook, suppress generic agency/street rumor fillers
        band1 = [c for c in band1 if _is_verified_quest_choice(c)][:2]
    else:
        # Backfill Band 1 if fewer than 2 quest/bounty/rumor skill-check options exist
        if len(band1) < 2:
            for fb1 in generate_band1_quest_and_rumor_fallbacks(lead_profile, sess, char=lead_char, actions=actions):
                fb_k = fb1["label"].strip().lower()
                if fb_k not in seen_lbls:
                    seen_lbls.add(fb_k)
                    band1.append(fb1)
                if len(band1) >= 2:
                    break
        band1 = band1[:4]

    # Normalize Band 2 & pin phone_contact_exchange ahead of generic social fillers so it is never popped
    band2 = [_normalize_band2_stat_and_dc(c, lead_profile, char=lead_char) for c in band2]
    band2.sort(key=lambda x: 0 if str(x.get("intent") or "").lower() == "phone_contact_exchange" else 1)

    has_contact_btn = any(str(c.get("intent") or "").lower() == "phone_contact_exchange" for c in band2)
    if is_meetup_social_focus:
        min_band2 = min(4, max(2, remaining_budget))
        max_band2 = 5
    else:
        min_band2 = 3 if has_contact_btn else (2 if len(band1) <= 3 else 1)
        max_band2 = 4 if has_contact_btn else 3

    if len(band2) < min_band2:
        for fb2 in generate_band2_social_choices(lead_profile, sess, actions=actions):
            fb_k = fb2["label"].strip().lower()
            if fb_k not in seen_lbls and is_choice_allowed_for_partner_profile(fb2, lead_profile, session=sess):
                seen_lbls.add(fb_k)
                band2.append(fb2)
            if len(band2) >= min_band2:
                break
    band2 = band2[:max_band2]

    # Progressive Taper when remaining_budget is low (1 or 2 turns left)
    quest_b1 = [c for c in band1 if _is_verified_quest_choice(c)]
    non_quest_b1 = [c for c in band1 if not _is_verified_quest_choice(c)]
    if remaining_budget == 1:
        # Down to final wrap-up exchange: cap non-quest options to at most 2
        allowed_nq = 2
        kept_b2 = band2[:allowed_nq]
        rem_slots = max(0, allowed_nq - len(kept_b2))
        band2 = kept_b2
        band1 = quest_b1 + non_quest_b1[:rem_slots]
    elif remaining_budget == 2:
        # Winding down: cap non-quest options to at most 3
        allowed_nq = 3
        kept_b2 = band2[: min(2, len(band2))]
        rem_slots = max(0, allowed_nq - len(kept_b2))
        kept_nq_b1 = non_quest_b1[:rem_slots]
        extra_b2_slots = max(0, allowed_nq - len(kept_b2) - len(kept_nq_b1))
        band2 = (kept_b2 + band2[len(kept_b2) : len(kept_b2) + extra_b2_slots])
        band1 = quest_b1 + kept_nq_b1

    if in_stage_1 and urg_profile:
        band1 = [_apply_stage1_hurry_gate(c) for c in band1]
        band2 = [_apply_stage1_hurry_gate(c) for c in band2]

    # Cap total choices at <= 8 while preserving pinned phone_contact_exchange and Band 3 Leave Conversation
    max_body = 6 if stage1_prefix else 7
    while len(band1) + len(band2) > max_body and len(band2) > (2 if has_contact_btn else 1):
        band2.pop()
    while len(band1) + len(band2) > max_body and len(band1) > len(quest_b1) and len(band1) > 1:
        band1.pop()
    while len(band1) + len(band2) > max_body and len(band2) > 1:
        band2.pop()

    pinned_exit = build_pinned_leave_choice(clean_partners)
    return stage1_prefix + band1 + band2 + [pinned_exit]


def pin_dialogue_exit_last(
    choices: List[Dict[str, Any]],
    partners: Optional[List[str]],
    max_total: int = 8,
) -> List[Dict[str, Any]]:
    """
    Guarantees that in active non-intimate dialogue:
      1. Stage 2 ultimatum 2-choice locks are never overwritten by ambient injectors.
      2. Standardized 'Leave conversation...' is ALWAYS present as the final choice and never sliced off.
    """
    clean_partners = [str(p).strip() for p in (partners or []) if str(p).strip()]
    if not clean_partners:
        return list(choices or [])

    if any(isinstance(c, dict) and c.get("_stage_2_ultimatum_locked") for c in (choices or [])):
        return [c for c in (choices or []) if isinstance(c, dict) and c.get("_stage_2_ultimatum_locked")]

    body: List[Dict[str, Any]] = []
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
        body.append(c)

    if exit_choice is None:
        exit_choice = build_pinned_leave_choice(clean_partners)

    body_cap = max(1, max_total - 1)
    return body[:body_cap] + [exit_choice]


def evaluate_conversation_departure_turn(
    session: Dict[str, Any],
    actions: Optional[List[Any]],
    new_partners: List[str],
    has_exited_convo: bool,
    party: Optional[List[Any]] = None,
    stage_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluates Urgent Schedule Departure transitions & Private Meetup exit rules pre-LLM.
    Returns:
      {
        "directive_note": str,
        "departing_for_schedule": List[Dict[str, str]],  # [{"name", "target_location", "target_node_id", "reason"}]
        "active_partners": List[str],
      }
    """
    from skill_check import is_check_success
    from mechanics.world.schedules import (
        detect_schedule_boundary_crossed,
        get_npc_scheduled_location,
        get_npc_scheduled_node_id,
        get_time_block_key,
        is_schedule_transition_imminent,
    )
    from mechanics.world.mobility import get_session_dialogue_partners
    from game_engine.npcs.dialogue_tracking import compute_scene_beat_linger_turns

    sess_id = session.get("id")
    scen_key = str(session.get("scenario") or "fantasy")
    scene_loc = str(
        (stage_info or {}).get("effective_location")
        or session.get("current_location")
        or ""
    )
    scene_nid = str(
        (stage_info or {}).get("effective_node_id")
        or session.get("current_node_id")
        or ""
    )
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
    is_custom_act = bool(
        lead_act.get("type") == "custom"
        or lead_act.get("_stage2_custom_auto_fail")
    )
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

    # ── 1. Handle Explicit Conversational Exit (including Private Meetup Exit & Active Departure States) ──
    if has_exited_convo:
        for p_nm in prev_partners:
            p_key = _canon_npc_key(p_nm)
            st = states.pop(p_key, None)
            prof = resolve_partner_conversation_profile(session, p_nm, party=party)
            if prof["is_private_meetup"]:
                # Mark active meetup appointment completed on clean exit
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

    # ── 2. Advance Existing Departure State Machine for Active Partners ──────
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
        prof = resolve_partner_conversation_profile(session, p_nm, party=party)

        # Private meetups & permanent party companions never trigger Stage 1 / Stage 2 hurry
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
                    # 5th bonus turn reached -> respond warmly, then depart (one-time cap per block)
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

        # ── 3. Check Fresh Trigger Into Stage 1 Warning ──────────────────────
        dest_loc, dest_nid = _resolve_npc_dest(p_nm, prof)
        if not dest_loc or _locations_match(scene_loc, dest_loc, session_id=sess_id, node_a=scene_nid, node_b=dest_nid):
            continue

        if prof["is_quest_stationed_here"]:
            continue

        non_scene_turns = sum(1 for h in history if isinstance(h, dict) and h.get("type") != "scene")
        linger_turns = compute_scene_beat_linger_turns(history, session=session, active_partners=[p_nm])
        has_real_clock_shift = bool(
            (bound_crossed and non_scene_turns >= 1)
            or (is_imm_now and linger_turns >= 1 and non_scene_turns >= 1)
        )
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
            if is_imm_now and mins_rem_now:
                timing_str = f"in about {mins_rem_now} minutes"
            else:
                timing_str = "now"
            directives.append(
                f"\n[URGENT SCHEDULE DEPARTURE — STAGE 1 WARNING]: {p_nm} is supposed to be at {dest_clean} {timing_str}. "
                f"In their spoken reply this turn, {p_nm} MUST explicitly mention that they need to get going to {dest_clean} soon!\n"
            )

    # Prune stale non-completed states for NPCs no longer in conversation
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


def relocate_departed_schedule_npcs(
    session: Dict[str, Any],
    result: Dict[str, Any],
    departing_records: List[Dict[str, str]],
    stage_info: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Physically removes departed NPCs from the current scene, records cast disengagement cooldowns,
    clears temporary walk-along state, and persists their new destination location to SQLite so they
    actually appear at that destination when the player visits it.
    """
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

    # 1. Remove from result["npcs_present"] & session["current_npcs"]
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

        rem_dps = [
            p for p in (result.get("dialogue_partners") or [])
            if str(p).strip().lower() not in dep_names_low
        ]
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

    # 2. Record disengagement in cast_state so LLM cannot re-engage them
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

    # 3. Persist destination location to contacts, lorebook, and session relocated overrides
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
                c_existing, lore_ent = _find_contact_and_lore(int(sess_id), nm)
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


def build_conversation_prompt_directive(
    session: Optional[Dict[str, Any]],
    partners: List[str],
    party: Optional[List[Any]] = None,
) -> str:
    """Builds the LLM prompt block instructing 3-Band choice generation & affinity-tier social rules."""
    clean_partners = [str(p).strip() for p in (partners or []) if str(p).strip()]
    if not clean_partners:
        return ""
    prof = resolve_partner_conversation_profile(session, clean_partners[0], party=party)
    partner = clean_partners[0]
    score = prof["score"]
    tier_name = prof["tier_name"]
    is_meetup = prof["is_private_meetup"]
    track = prof["track"]

    if is_meetup or score >= 100 or track == "romantic":
        social_rule = (
            f"{partner} is at '{tier_name}' ({score}, track={track}, meetup={is_meetup}): "
            f"generate 1-3 warm skill-check (`stat='CHA'`, `'INT'`, or `'PER'`, `requirement=5-7`) social options (personal compliments, playful banter, jokes, teasing, flirting, deeper backstory questions, or walking together to a contextual spot in the area)."
        )
    elif score >= 50:
        social_rule = (
            f"{partner} is an '{tier_name}' ({score}): "
            f"generate 1-2 polite skill-check (`stat='CHA'`, `'INT'`, or `'PER'`, `requirement=5-7`) social options (hobbies/background questions, light polite compliments, or mild situational observations). "
            f"DO NOT generate 'Walk with {partner}', heavy teasing, or flirting."
        )
    else:
        social_rule = (
            f"{partner} is '{tier_name}' ({score}): "
            f"generate 1-2 polite, neutral skill-check (`stat='INT'`, `'PER'`, or `'CHA'`, `requirement=5-7`) background/role questions ONLY (e.g., their work, duties, or immediate situation). "
            f"STRICTLY FORBIDDEN for Strangers: DO NOT generate compliments, flattery, 'offer a witty observation', jokes, banter, teasing, or 'Walk with {partner}'!"
        )

    return (
        "\n[CONVERSATION CHOICE ARCHITECTURE — PYTHON-ENFORCED]:\n"
        f"- Active Dialogue Partner(s): {', '.join(clean_partners)}\n"
        "- Structure `choices` into these exact bands:\n"
        "  1. FIRST 2-4 OPTIONS (Skill Checks: `INT`, `PER`, `CHA`, DC 5-8): Action/dialogue options that PRIORITIZE active quests/bounties or query the character for quest/bounty intel and local rumors.\n"
        f"  2. NEXT 1-3 OPTIONS (Affinity-Scaled Social/Background Skill Checks: `CHA`, `INT`, `PER`, DC 5-8): {social_rule}\n"
        "  3. DO NOT generate 'Convince ... to stay' unless instructed by an [URGENT SCHEDULE DEPARTURE] directive. Only the final 'Leave conversation...' option has `stat='NONE'`, `requirement=0`.\n"
    )
