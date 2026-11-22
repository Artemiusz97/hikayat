from __future__ import annotations
from typing import Any
import mechanics.system.phone
import json
import logging
import random
import re
import time
import discord
from discord import app_commands
import db
import scenario_data
from llm_client import call_llm_json
log = logging.getLogger("hikayat.phone")
from game_engine.prompt_layout import build_side_channel_language_directive
from skill_check import resolve_check, success_chance, CheckResult
from mechanics.social.relationships import clamp_score, is_contact_eligible
from mechanics.system.input_sanitizer import fence_player_message, sanitize_prompt_lore

from .embeds import *

from .gossip_feed import *
from .social_graph import *

DM_REPLY_SCHEMA = """{
  "reply_text": "string, 1-3 sentences in natural texting style with casual tone/emojis",
  "affinity_delta": integer -5 to 6,
  "rendezvous_location": "string, optional meeting location name or empty string"
}"""


from .dm_grounding import (
    get_dm_requirement,
    detect_custom_message_intent,
    is_meetup_reschedule_request,
    is_meetup_confirmation_message,
    resolve_rendezvous_location,
    evaluate_dm_in_person_gate,
    build_meetup_candidates_and_hint,
)
from .player_dm import generate_player_chat_message
from .dm_outcomes import handle_dm_over_limit, persist_dm_media_item_and_milestone

from .media_captions import (
    generate_npc_photo_caption,
    generate_player_photo_caption,
    generate_player_casual_photo,
    generate_player_spicy_photo
)

def build_dm_epistemic_context(
    session_id: int,
    actor_keys: list[str],
    *,
    sibling_key: str = "",
) -> dict[str, Any]:
    """
    B12 / D-5: Computes holder-filtered epistemic context for 1-on-1 or group DMs.
    - 1-on-1 DM: returns facts held by that NPC (confidence, containment_state, summary).
    - Group DM (2+ actor_keys): returns ONLY facts held by EVERY participant in the group.
    - Sibling romance gate: returns `sibling_romance_known=True` ONLY if a public non-secret
      romantic `social_tie` exists with the sibling OR the recipient holds an `epistemic_knowledge`
      row revealing it (never inferred raw from `contacts.track`).
    """
    sid = int(session_id or 0)
    norm_actors = [
        str(a or "").strip().lower().replace(" ", "_")
        for a in (actor_keys or [])
        if str(a or "").strip()
    ]
    sib_k = str(sibling_key or "").strip().lower().replace(" ", "_")
    if not sid or not norm_actors:
        return {"known_facts": [], "sibling_romance_known": False, "prompt_block": ""}

    matrix = db.preload_epistemic_matrix(sid, actor_keys=norm_actors)
    facts_by_key = matrix.get("facts_by_key") or {}
    by_holder = matrix.get("by_holder") or {}
    holder_maps: dict[str, dict[str, dict[str, Any]]] = {
        ak: {
            str(kr.get("fact_key") or ""): kr
            for kr in (by_holder.get(ak) or [])
            if isinstance(kr, dict) and kr.get("fact_key")
        }
        for ak in norm_actors
    }

    shared_keys: set[str] | None = None
    for ak in norm_actors:
        held = set(holder_maps.get(ak, {}).keys())
        shared_keys = held if shared_keys is None else (shared_keys & held)
    shared_keys = shared_keys or set()

    known_facts: list[dict[str, Any]] = []
    for fkey in sorted(shared_keys):
        fact = facts_by_key.get(fkey) or {}
        if str(fact.get("status") or "active").lower() in ("wiped", "decayed"):
            continue
        # For group DMs use lowest common knowledge confidence; for solo DM use the NPC row
        holder_rows = [holder_maps.get(ak, {}).get(fkey) or {} for ak in norm_actors]
        if any(str(hr.get("containment_state") or "") in ("wiped", "incapacitated") for hr in holder_rows):
            continue
        known_facts.append({
            "fact_key": fkey,
            "category": fact.get("category") or "",
            "summary": fact.get("summary") or fkey,
            "confidence": holder_rows[0].get("confidence") or "rumor",
            "containment_state": holder_rows[0].get("containment_state") or "active",
            "subject_actor_key": fact.get("subject_actor_key") or "",
            "culprit_actor_key": fact.get("culprit_actor_key") or "",
        })

    sibling_romance_known = False
    if sib_k:
        try:
            from mechanics.social import relationship_graph as rg
            sib_ties = rg.get_ties(sid, sib_k) or []
            for t in sib_ties:
                if str(t.get("status") or "active").lower() != "active":
                    continue
                if int(t.get("is_secret") or 0) == 1:
                    continue
                ttype = str(t.get("tie_type") or "").strip().lower()
                if ttype not in (
                    rg.TIETYPE_DATING,
                    rg.TIETYPE_ENGAGED,
                    rg.TIETYPE_MARRIED,
                    "dating",
                    "engaged",
                    "married",
                ):
                    continue
                pa = str(t.get("person_a_key") or "").strip().lower()
                pb = str(t.get("person_b_key") or "").strip().lower()
                if rg.is_player_person_key(pa) or rg.is_player_person_key(pb):
                    sibling_romance_known = True
                    break
        except Exception:
            pass

        if not sibling_romance_known:
            for kf in known_facts:
                blob = f"{kf.get('fact_key')} {kf.get('category')} {kf.get('summary')}".lower()
                subj = str(kf.get("subject_actor_key") or "").lower()
                culp = str(kf.get("culprit_actor_key") or "").lower()
                if (sib_k in (subj, culp) or sib_k in blob) and any(
                    tok in blob for tok in ("romanc", "dat", "affair", "lover", "kiss", "confess", "crush", "couple")
                ):
                    sibling_romance_known = True
                    break

    prompt_lines: list[str] = []
    if known_facts:
        prompt_lines.append("- EPISTEMIC KNOWLEDGE (Things YOU personally know / heard):")
        for kf in known_facts[:4]:
            c_state = str(kf.get("containment_state") or "active")
            state_note = " (you promised to stay quiet)" if c_state in ("hushed", "co_conspirator") else ""
            prompt_lines.append(f"  * [{kf['confidence']}] {kf['summary']}{state_note}")
    prompt_lines.append("- EPISTEMIC BOUNDARY: Never mention, confront, or hint at off-screen events or romances that are NOT listed in your knowledge above or in conversation history.")
    return {
        "known_facts": known_facts,
        "sibling_romance_known": sibling_romance_known,
        "prompt_block": "\n".join(prompt_lines) + "\n",
    }


def enqueue_autonomy_hangout_ping(session_id: int, ping: dict) -> bool:
    """
    D10: Queues an autonomous DM hangout invite or local gossip text when the scenario supports smartphones,
    enforcing at most 1 autonomous invite DM queued per NPC session streak without spam.
    """
    sid = int(session_id or 0)
    if not sid or not isinstance(ping, dict):
        return False
    sess = db.get_session(sid) or {}
    scen_key = str(sess.get("scenario") or "fantasy").strip().lower()
    if not scenario_has_smartphone(scen_key):
        return False
    sender_id = str(ping.get("sender_key") or "").strip().lower().replace(" ", "_")
    summary = str(ping.get("summary") or "").strip()
    if not sender_id or not summary:
        return False
    recent = db.get_phone_messages(sid, sender_id, limit=4) or []
    if recent and str(recent[-1].get("message") or "").strip() == summary:
        return False
    db.save_phone_message(sid, sender_id, sender="npc", message=summary, intent="meetup" if ping.get("kind") == "hangout_invite" else "chat")
    return True


async def generate_contact_dm_reply(session: dict, contact: dict, player_char: dict, user_message: str, intent: str = "chat") -> dict:
    """Generates an in-character text message reply from an NPC contact resolved via skill check and fast LLM."""
    session_id = session["id"]
    contact_name = contact.get("name", "Contact")
    npc_id = contact.get("npc_id") or contact_name.lower().replace(" ", "_")
    score = contact.get("relationship_score", 0)
    track = contact.get("track", "platonic")
    is_romantic = track.lower() == "romantic"
    scen_key = session.get("scenario", "fantasy")
    branding = get_phone_branding(scen_key)

    basic = contact.get("basic_info", {})
    role = basic.get("role") or basic.get("occupation") or "Contact"
    traits_list = contact.get("unlocked_traits") or basic.get("traits") or ["Observant"]
    traits = ", ".join(traits_list)
    current_loc = session.get("current_location", "Local Area")

    msg_lower = (user_message or "").lower()
    is_intimate = any(k in msg_lower for k in ["intimate", "spicy", "nsfw", "nude", "nudes", "naked", "sexy", "lewd", "lingerie", "boudoir", "underwear", "undies"])
    is_video = any(k in msg_lower for k in ["video", "vid", "clip", "recording", "footage", "film"])
    is_photo = any(k in msg_lower for k in ["photo", "pic", "picture", "selfie", "snapshot", "image", "look like"])

    # Invariant 7: Apology mitigation recovery for missed appointments
    clean_npc_id = npc_id.strip().lower().replace(" ", "_")
    apology_kws = ["sorry", "apologize", "forgive", "couldn't make it", "could not make it", "held up", "emergency", "didn't show", "flaked"]
    if any(k in msg_lower for k in apology_kws):
        try:
            from mechanics.system.commitments_engine import apply_apology_recovery
            apply_apology_recovery(session_id, clean_npc_id, excuse_text=user_message)
        except Exception:
            pass

    # Check if there is an active pending appointment with this contact
    pending_appts = [a for a in db.get_phone_appointments(session_id, status="pending") if a.get("npc_id") == clean_npc_id]
    existing_appointment = pending_appts[0] if pending_appts else None

    # Retrieve current day & daily interaction limits
    current_day, current_minute, _ = db.get_session_time(session_id)
    daily_limits = db.get_phone_daily_limits(session_id, npc_id, current_day)

    # D10: Detect active pending_hangout_ping reply/decline before intent classification & quota checks
    active_ping = basic.get("pending_hangout_ping") if isinstance(basic, dict) else None
    if not isinstance(active_ping, dict) or not active_ping:
        try:
            _roster_ping_row = db.get_world_roster_npc(session_id, clean_npc_id or npc_id)
            if isinstance(_roster_ping_row, dict):
                _roster_bi = _roster_ping_row.get("basic_info") or {}
                if isinstance(_roster_bi, dict) and isinstance(_roster_bi.get("pending_hangout_ping"), dict):
                    active_ping = _roster_bi.get("pending_hangout_ping")
        except Exception:
            active_ping = None
    if isinstance(active_ping, dict) and active_ping.get("expires_day") is not None:
        try:
            if int(current_day) > int(active_ping["expires_day"]):
                active_ping = None
        except Exception:
            pass
    _norm_msg_words = "".join(ch if (ch.isalnum() or ch == "'") else " " for ch in msg_lower).split()
    _norm_msg_set = set(_norm_msg_words)
    _norm_msg_joined = " ".join(_norm_msg_words)
    _norm_msg_plain = _norm_msg_joined.replace("'", "")
    _is_ping_refusal = bool(
        (_norm_msg_set & {"no", "busy", "can't", "cant", "pass"})
        or any(ph in _norm_msg_plain for ph in ("not now", "rain check", "maybe later"))
    )
    _is_ping_affirm = bool(
        intent == "meetup"
        or (_norm_msg_set & {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "alright", "omw"})
        or any(
            ph in _norm_msg_plain
            for ph in (
                "sounds good", "on my way", "be right there", "lets hang",
                "hang out", "im in", "see you", "meet you", "count me in",
            )
        )
    )
    _has_active_ping = isinstance(active_ping, dict) and bool(active_ping)
    is_autonomy_ping_reply = bool(_has_active_ping and _is_ping_affirm and not _is_ping_refusal)
    is_autonomy_ping_decline = bool(_has_active_ping and _is_ping_refusal)
    if is_autonomy_ping_reply:
        intent = "meetup"

    # Auto-classify intent for custom or generic chat messages
    if intent in ("custom", "chat"):
        if is_meetup_reschedule_request(user_message):
            intent = "meetup"
        else:
            detected = detect_custom_message_intent(user_message)
            if detected != "custom":
                # If an appointment is ALREADY pending and detected intent is "meetup",
                # do not convert custom chat into a new meetup unless player explicitly asks to reschedule/change location!
                if detected == "meetup" and existing_appointment:
                    if not is_meetup_reschedule_request(user_message):
                        detected = "custom"
                if detected != "custom":
                    intent = detected

    def _get_intent_category(intnt: str) -> str | None:
        if intnt == "flirt":
            return "flirt"
        if intnt == "meetup":
            return "meetup"
        if intnt in ("photo", "video", "photo_ask", "photo_send", "send_photo", "ask_photo"):
            return "photo"
        if intnt in ("nsfw_photo", "nsfw_video", "spicy_ask", "spicy_send", "send_spicy", "ask_spicy", "nsfw_send"):
            return "spicy"
        if intnt in ("intel_rumor", "intel", "rumor"):
            return "rumor"
        if intnt in ("chat", "custom"):
            return "chat"
        return None

    intent_category = _get_intent_category(intent)
    is_reschedule_request = is_meetup_reschedule_request(user_message)

    # Check daily limits for capped intents
    is_over_limit = False
    if intent_category == "chat":
        chat_lim = daily_limits.get("chat") or {"used": 0, "max": 5 if score >= 100 else 3}
        if int(chat_lim.get("used", 0)) >= int(chat_lim.get("max", 5 if score >= 100 else 3)):
            is_over_limit = True
    elif intent_category == "flirt":
        if daily_limits["flirt"]["used"] >= 3:
            is_over_limit = True
    elif intent_category == "meetup":
        if is_autonomy_ping_reply:
            pass
        elif existing_appointment:
            if is_reschedule_request and daily_limits["meetup"].get("relocations_used", 0) >= 2:
                is_over_limit = True
        elif daily_limits["meetup"]["status"] == "failed":
            is_over_limit = True
        elif daily_limits["meetup"]["used"] >= 1:
            is_over_limit = True
    elif intent_category == "photo":
        if daily_limits["photo"]["used"] >= 3:
            is_over_limit = True
    elif intent_category == "spicy":
        if daily_limits["spicy"]["used"] >= 3:
            is_over_limit = True
    elif intent_category == "rumor":
        if daily_limits["rumor"]["used"] >= 1:
            is_over_limit = True

    # Handle Over-Limit Attempts: In-character refusal with escalating badgering penalty
    if is_over_limit:
        return await handle_dm_over_limit(
            session=session,
            speaker_gender=str(contact.get("gender") or basic.get("gender") or ""),
            session_id=session_id,
            npc_id=npc_id,
            contact_name=contact_name,
            role=role,
            traits=traits,
            score=score,
            track=track,
            is_romantic=is_romantic,
            scen_key=scen_key,
            intent=intent,
            intent_category=intent_category,
            daily_limits=daily_limits,
            existing_appointment=existing_appointment,
            player_char=player_char,
            user_message=user_message,
            current_day=current_day,
        )

    # Determine stat to check
    cha_val = player_char.get("cha", 5)
    per_val = player_char.get("per_", player_char.get("per", 5))
    int_val = player_char.get("int_", player_char.get("int", 5))

    if intent in ("intel_rumor", "intel", "rumor"):
        best_val = max(cha_val, per_val, int_val)
        if best_val == cha_val:
            stat_name = "CHA"
            stat_val = cha_val
        elif best_val == per_val:
            stat_name = "PER"
            stat_val = per_val
        else:
            stat_name = "INT"
            stat_val = int_val
    else:
        stat_name = "CHA"
        stat_val = cha_val

    app_data = contact.get("appearance", {})
    if not isinstance(app_data, dict):
        app_data = {}
    erotic_open = app_data.get("erotic_openness") or app_data.get("openness") or "moderate"
    under_data = app_data.get("undergarments") or {}
    if isinstance(under_data, str):
        under_data = {"underwear": under_data}
    bra_str = str(under_data.get("bra") or app_data.get("bra") or "").strip()
    und_str = str(under_data.get("underwear") or app_data.get("underwear") or "").strip()
    intimate_dem = app_data.get("intimate_demeanor") or ""
    intimate_dyn = app_data.get("intimate_dynamic") or ""

    flirt_attempt_num = (daily_limits["flirt"]["used"] + 1) if intent_category == "flirt" else 1
    flirt_prev_succeeded = (daily_limits["flirt"].get("last_outcome") in ("success", "crit_success")) if intent_category == "flirt" else False
    relocation_num = (daily_limits["meetup"].get("relocations_used", 0) + 1) if (intent_category == "meetup" and is_reschedule_request) else 0
    is_player_sending = intent in ("photo_send", "send_photo", "spicy_send", "send_spicy", "nsfw_send")

    req = get_dm_requirement(
        score,
        intent,
        track=track,
        openness=erotic_open,
        traits=traits_list,
        attempt_num=flirt_attempt_num,
        prev_succeeded=flirt_prev_succeeded,
        relocation_num=relocation_num,
        is_player_sending=is_player_sending
    )
    user_settings = db.get_settings(player_char.get("user_id", 0))
    check_mode = user_settings.get("debug_check_mode", "off") if user_settings else "off"
    check_result = resolve_check(stat_val, req, luck=player_char.get("luk", 3), check_mode=check_mode)
    if is_autonomy_ping_reply:
        check_result = CheckResult(
            chance=100,
            roll=0.0,
            tier="success",
            tier_label="Success",
            succeeded=True,
        )

    is_prude = any(k in str(erotic_open).lower() for k in ("prude", "modest"))
    is_shameless = any(k in str(erotic_open).lower() for k in ("shameless", "lewd"))
    is_bold = any(k in str(erotic_open).lower() for k in ("bold", "uninhibited"))

    # Strict prude barrier on NSFW media requests: requires 70+ affinity AND romantic track
    if is_prude and intent in ("nsfw_photo", "nsfw_video", "spicy_ask", "ask_spicy") and (score < 70 or not is_romantic):
        check_result = CheckResult(
            chance=0,
            roll=1.0,
            tier="fail",
            tier_label="Failure",
            succeeded=False
        )

    # Fetch recent message history
    history_rows = db.get_phone_messages(session_id, npc_id, limit=6)
    history_text = "\n".join(
        f"Player: {fence_player_message(r['message'], max_len=500)}"
        if r["sender"] == "player"
        else f"{contact_name}: {sanitize_prompt_lore(r['message'], max_len=500)}"
        for r in history_rows
    )

    # In-Game Time & World Schedule Context
    curr_day_val, curr_min_val, _ = db.get_session_time(session_id)
    from mechanics.system.time_engine import format_time_header
    from mechanics.world.world_schedule import get_world_schedule_state
    time_str = format_time_header(curr_day_val, curr_min_val)
    world_sched = get_world_schedule_state(
        scen_key,
        current_day=curr_day_val,
        current_minute=curr_min_val,
        session=session,
        session_id=session_id,
    )
    time_schedule_hint = (
        f"- Current In-Game Time & Schedule: {time_str} [{world_sched.get('period_label', '')}]. "
        f"Reflect the current setting and time of day in your reply when natural (e.g. discreetly texting during class, mentioning club activities, chatting on weekends, or winding down for bed).\n"
    )
    npc_sched_nid = ""
    npc_sched_loc = ""
    try:
        from mechanics.social.wardrobe.constants import is_sleepwear_window
        from mechanics.world.anchor_schedule import is_npc_on_active_shift
        from mechanics.world.locations.residence_fog import SHARED_ABSTRACT_RESIDENCE_NODE
        from mechanics.world.npc_schedule import get_npc_scheduled_location, get_npc_scheduled_node_id

        npc_sched_nid = get_npc_scheduled_node_id(
            contact,
            current_minute=curr_min_val,
            scen_key=scen_key,
            session_id=session_id,
            current_day=curr_day_val,
        ) or ""
        npc_sched_loc = get_npc_scheduled_location(
            contact,
            current_minute=curr_min_val,
            scen_key=scen_key,
            session_id=session_id,
            current_day=curr_day_val,
        ) or ""
        on_shift_now, _ = is_npc_on_active_shift(
            contact,
            curr_min_val,
            current_day=curr_day_val,
            scen_key=scen_key,
            session_id=session_id,
        )
        shift_prof_dm = str(contact.get("shift_profile") or basic.get("shift_profile") or "day").strip().lower()
        in_sleep_dm = is_sleepwear_window(
            curr_day_val,
            curr_min_val,
            shift_profile=shift_prof_dm,
            is_nocturnal=bool(contact.get("nocturnal") or basic.get("nocturnal")),
            closes_at_22=bool(contact.get("closes_at_22") or basic.get("closes_at_22")),
            closes_at_20=bool(contact.get("closes_at_20") or basic.get("closes_at_20")),
        )
        if npc_sched_nid == SHARED_ABSTRACT_RESIDENCE_NODE or "unknown address" in npc_sched_loc.lower():
            place_lbl = "home"
        elif npc_sched_loc:
            place_lbl = npc_sched_loc.split("➔")[-1].strip() or npc_sched_loc
        else:
            place_lbl = "nearby"
        if in_sleep_dm and place_lbl == "home":
            status_phrase = "winding down at home"
        elif on_shift_now:
            status_phrase = f"on active duty/shift at {place_lbl}"
        else:
            status_phrase = f"currently at {place_lbl}"
        time_schedule_hint += (
            f"- Your Current Situation: You are {status_phrase} right now; keep your response consistent with where you are.\n"
        )
    except Exception:
        pass
    try:
        from mechanics.social.wardrobe import (
            format_wardrobe_summary,
            detect_outfit_request_intent,
            evaluate_outfit_request_compliance,
            resolve_actor_wardrobe_state,
        )

        offscreen_loc_str = npc_sched_loc or str(current_loc or "")
        offscreen_w = resolve_actor_wardrobe_state(
            contact,
            session=session,
            scen_key=scen_key,
            location_str=offscreen_loc_str,
            node_id=npc_sched_nid,
            current_day=curr_day_val,
            current_minute=curr_min_val,
            is_colocated_with_player=False,
            viewer_relationship={"track": track, "affinity": score},
        )
        off_preset = str(offscreen_w.get("active_outfit_preset") or "").strip()
        off_sum = format_wardrobe_summary(offscreen_w.get("clothing"))
        if off_sum and off_preset != "natural":
            time_schedule_hint += (
                f"- Current Off-Screen Attire ({off_preset}): {off_sum}. "
                f"When sending casual selfies or mentioning what you're currently wearing at this hour, stay consistent with this outfit.\n"
            )
        dm_req = detect_outfit_request_intent(user_message, target_npc_name=contact_name)
        if dm_req.get("detected"):
            dm_eval = evaluate_outfit_request_compliance(
                contact,
                dm_req,
                scen_key=scen_key,
                session=session,
                location_str=offscreen_loc_str,
                node_id=npc_sched_nid,
                current_day=curr_day_val,
                current_minute=curr_min_val,
                relationship={"track": track, "affinity": score},
                current_turn=int(session.get("turn_count") or 0),
                is_dm=True,
            )
            if dm_eval.get("directive_text"):
                time_schedule_hint += dm_eval["directive_text"] + "\n"
            if check_result.succeeded and dm_eval.get("pending_request_payload"):
                upd_basic = dict(basic)
                upd_basic["pending_outfit_request"] = dm_eval["pending_request_payload"]
                db.upsert_contact(
                    session_id=session_id,
                    character_id=player_char.get("id", 0),
                    npc_id=str(contact.get("npc_id") or clean_npc_id),
                    name=contact_name,
                    basic_info=upd_basic,
                )
    except Exception:
        pass

    # Contextual knowledge hints (Read-only from active quest & gossip feed)
    active_sq = db.get_active_story_quest(session_id)
    sq_hint = ""
    if active_sq:
        sq_title = active_sq.get("title", "")
        sq_obj = active_sq.get("objective", "")
        sq_hint = f"- Active Situation Context: '{sq_title}' — {sq_obj[:120]} (Provide thematic flavor/perspective if asked, but DO NOT invent canon story reveals that alter official quest evidence).\n"

    feed_posts = db.get_gossip_feed(session_id, limit=3)
    feed_hint = ""
    if feed_posts:
        snippets = "; ".join(f"'{p.get('content', '')[:60]}'" for p in feed_posts if p.get("content"))
        feed_hint = f"- Recent Local Rumors on Feed: {snippets}\n"

    # Family & Grade dynamics
    family_and_grade_hint = ""
    grade = basic.get("grade")
    sibling_name = basic.get("sibling_name")
    epistemic_ctx = build_dm_epistemic_context(session_id, [clean_npc_id], sibling_key=str(sibling_name or ""))
    epistemic_hint = str(epistemic_ctx.get("prompt_block") or "")
    if grade or sibling_name:
        lines = []
        if grade:
            if grade == "Senior":
                lines.append("- Grade Dynamics: You are a Senior (Upperclassman). Speak with upperclassman maturity, confidence, or mention college prep/graduation/council duties.")
            elif grade in ("Freshman", "Sophomore"):
                lines.append(f"- Grade Dynamics: You are an Underclassman ({grade}). Speak with slight deference or casual junior energy, and feel free to ask about difficult classes or school advice.")
            elif grade == "Junior":
                lines.append("- Grade Dynamics: You are a Junior (same grade as player). Speak comfortably as an equal classmate.")
            elif grade == "Faculty":
                lines.append("- Role Dynamics: You are a Faculty teacher/staff member. Maintain a professional yet characterful educator tone.")

        if sibling_name:
            all_contacts = db.get_contacts(session_id)
            sibling_clean = sibling_name.lower().replace(" ", "_")
            sib_contact = next((c for c in all_contacts if c.get("npc_id") == sibling_clean or c.get("name", "").lower() == sibling_name.lower()), None)
            sib_score = sib_contact.get("relationship_score", 0) if sib_contact else 0
            sib_track = sib_contact.get("track", "platonic") if sib_contact else "platonic"

            lines.append(f"- Family / Sibling: You are the biological sibling of {sibling_name}.")
            if epistemic_ctx.get("sibling_romance_known"):
                lines.append(f"- SIBLING RELATIONSHIP NOTE: You are aware the player is very close to / romantically involved with your sibling ({sibling_name}). You may tease them or show protective/curious interest!")
            elif sib_score >= 30 and sib_track.lower() != "romantic":
                lines.append(f"- SIBLING RELATIONSHIP NOTE: You know the player gets along warmly with your sibling ({sibling_name}) as a friend.")
            elif sib_score < 0:
                lines.append(f"- SIBLING RELATIONSHIP NOTE: You know the player has bad blood or tension with your sibling ({sibling_name}).")

            if intent == "meetup" and grade in ("Freshman", "Sophomore"):
                lines.append("- Meetup Note: If you agree to meet up, you might playfully mention hoping your older sibling doesn't catch you.")

        if lines:
            family_and_grade_hint = "\nFAMILY & GRADE DYNAMICS:\n" + "\n".join(lines) + "\n"

    # --- Meetup location grounding: build a list of known public locations ---
    known_locations: list[dict] = []
    meetup_location_hint = ""
    is_reschedule_request = is_meetup_reschedule_request(user_message)
    if intent == "meetup":
        if existing_appointment and not is_reschedule_request:
            existing_loc = existing_appointment["rendezvous_location"]
            meetup_location_hint = (
                f"- IMPORTANT — EXISTING CONFIRMED MEETUP: You and the player ALREADY agreed to meet up at: '{existing_loc}'.\n"
                f"- Acknowledge your existing plan to meet at '{existing_loc}' (e.g. say you're looking forward to seeing them there, confirming you're on your way, or teasing them affectionately).\n"
                f"- Do NOT suggest a different or new meeting location.\n"
                f"- You MUST set rendezvous_location to EXACTLY: '{existing_loc}'.\n"
            )
        else:
            known_locations, meetup_location_hint = build_meetup_candidates_and_hint(
                session_id=session_id,
                session=session,
                scen_key=scen_key,
                curr_day_val=curr_day_val,
                curr_min_val=curr_min_val,
                contact=contact,
                openness=erotic_open,
                traits=traits_list,
                is_romantic=is_romantic,
                is_reschedule_request=is_reschedule_request,
                existing_appointment=existing_appointment,
            )

    p_gender = str(player_char.get("gender") or player_char.get("sex") or "male").strip().lower()
    n_gender = str(basic.get("gender") or basic.get("sex") or "female").strip().lower()
    is_player_male = any(w in p_gender for w in ("male", "man", "boy")) and not any(w in p_gender for w in ("female", "woman"))
    is_player_female = any(w in p_gender for w in ("female", "woman", "girl"))
    is_npc_male = any(w in n_gender for w in ("male", "man", "boy")) and not any(w in n_gender for w in ("female", "woman"))
    is_npc_female = any(w in n_gender for w in ("female", "woman", "girl"))

    # Dynamic Intent Specific Prompt Instructions
    if intent == "meetup":
        if existing_appointment and not is_reschedule_request:
            existing_loc = existing_appointment["rendezvous_location"]
            intent_guidelines = (
                f"- Intent: Player is talking about or confirming your upcoming meetup.\n"
                f"- If check Succeeded / Critical Success: Happy, warm confirmation that you'll see them at '{existing_loc}'.\n"
                f"- If check Failed / Critical Failure: Mention you might be a little delayed or ask for a rain check.\n"
            )
        elif existing_appointment and is_reschedule_request:
            intent_guidelines = (
                f"- Intent: Player is asking to reschedule or relocate the meetup to a different/more private location.\n"
                f"- If check Succeeded / Critical Success: Agree warmly, and suggest or confirm a new meeting spot from the known locations list.\n"
                f"- If check Failed / Critical Failure: Mention you're on a tight schedule or prefer the original location.\n"
            )
        elif is_romantic:
            intent_guidelines = (
                "- Intent: Player is asking you out on a Romantic Date.\n"
                "- If check Succeeded / Critical Success: You are thrilled/flattered, agree happily to the date, and suggest a charming meeting spot from the known locations.\n"
                "- If check Failed: You are flustered/busy, politely decline or ask for a rain check. Do not set a rendezvous.\n"
                "- If check Critical Failure: You turn down the romantic offer firmly.\n"
            )
        else:
            intent_guidelines = (
                "- Intent: Player is asking to meet up.\n"
                "- If check Succeeded / Critical Success: You agree and suggest a meeting spot from the known locations.\n"
                "- If check Failed / Critical Failure: You are busy or polite, declining the meetup.\n"
            )
    elif intent == "chat":
        intent_guidelines = (
            "- Intent: Casual friendly check-in.\n"
            "- If check Succeeded / Critical Success: Warm, engaging chat sharing something about your day or mood.\n"
            "- If check Failed / Critical Failure: Brief, distracted, or neutral reply.\n"
        )
    elif intent == "flirt":
        if flirt_attempt_num == 1:
            prog_note = "This is Flirt Attempt #1 today. Keep it light, charming, and responsive."
        elif flirt_attempt_num == 2:
            prog_note = f"This is Flirt Attempt #2 today (Previous attempt was: {'a hit' if flirt_prev_succeeded else 'clumsy'}). " + (
                "Escalate the banter with confident warmth or playful teasing." if flirt_prev_succeeded else "Let them recover playfully or tease them about their clumsy line."
            )
        else:
            prog_note = f"This is Flirt Attempt #3 today (Previous attempt was: {'a hit' if flirt_prev_succeeded else 'clumsy'}). " + (
                "Climax of today's flirting: share genuine sweet affection, blushing chemistry, or a memorable romantic spark." if flirt_prev_succeeded else "Set a firm but lighthearted boundary or tease them that they've reached their charm quota for today."
            )
        intent_guidelines = (
            f"- Intent: Flirting and teasing banter. {prog_note}\n"
            "- If check Succeeded / Critical Success: Playful, charmed, blushing, or teasing back.\n"
            "- If check Failed: Mildly awkward, deflects, or changes subject.\n"
            "- If check Critical Failure: Disapproving, annoyed, or cringing.\n"
        )
    elif intent in ("intel_rumor", "intel", "rumor"):
        intent_guidelines = (
            "- Intent: Inquiring about local intel, rumors, and what's going on.\n"
            "- If check Succeeded / Critical Success: Share helpful advice, perspective on active events, or validate/debunk local rumors.\n"
            "- If check Failed: You haven't heard much or keep details to yourself.\n"
            "- If check Critical Failure: Suspicious of prying or dismissive of gossip.\n"
        )
    elif intent in ("photo_send", "send_photo"):
        intent_guidelines = (
            "- Intent: Player sent you a casual photo/selfie/picture of their day.\n"
            "- If check Succeeded / Critical Success: React with warmth, humor, or compliments about what they sent (e.g. admiring the view, commenting on their expression or item).\n"
            "- If check Failed / Critical Failure: Neutral, brief acknowledgment or distracted response.\n"
            "- Do NOT attach a photo yourself in reply.\n"
        )
    elif intent in ("photo", "video", "photo_ask", "ask_photo"):
        intent_guidelines = (
            "- Intent: Exchanging everyday photos / selfies. Player asked you to send a photo.\n"
            "- CRITICAL CREATIVITY & VARIETY MANDATE:\n"
            "  * If check Succeeded / Critical Success: You MUST invent an entirely ORIGINAL, VIVID bracketed photo description: '[Attached Photo: ...]'.\n"
            "  * ANTI-REPETITION: Never repeat settings or activities from history. Vary the activity, outfit, lighting, and expressions (e.g. sipping a beverage at a sunlit cafe, holding up a cute find, sitting on bedroom floor with study notes, posing outdoors under trees, laughing candidly at something off-camera).\n"
            "  * If check Failed / Critical Failure: Say your camera is glitching, you look a mess, or politely decline.\n"
        )
    elif intent in ("spicy_send", "send_spicy", "nsfw_send"):
        gender_tone = ""
        if is_player_male and is_npc_female:
            gender_tone = (
                "- GENDER DYNAMIC (Male player sent intimate photo to Female contact):\n"
                "  * If check Succeeded / Critical Success: Flattered, turned on, or boldly teases back.\n"
                "  * If check Failed / Critical Failure: Deeply offended, creeped out, or angry at the unsolicited intimate picture! Scold them harshly."
            )
        elif is_player_female and is_npc_male:
            gender_tone = (
                "- GENDER DYNAMIC (Female player sent intimate photo to Male contact):\n"
                "  * If check Succeeded / Critical Success: Highly enthusiastic, captivated, praising her looks with flustered eagerness.\n"
                "  * If check Failed / Critical Failure: " + (
                    "Scold her for indecency (modest/prude demeanor)." if is_prude else "Flustered awkwardness and confusion ('Whoa... wasn't expecting that right now 😳'), but not hateful."
                )
            )
        intent_guidelines = (
            "- Intent: Player sent an unsolicited intimate/spicy photo of themselves.\n"
            f"{gender_tone}\n"
            "- Do NOT attach a photo yourself in reply.\n"
        )
    elif intent in ("nsfw_photo", "nsfw_video", "spicy_ask", "ask_spicy"):
        npc_b_size = app_data.get("breast_size") if is_npc_female else app_data.get("penis_size")
        asset_photo_cue = ""
        if npc_b_size:
            from mechanics.social.persona import classify_asset_size_tier
            tier_npc = classify_asset_size_tier(npc_b_size, gender="male" if is_npc_male else "female")
            if tier_npc in ("flat", "small"):
                if is_prude:
                    asset_photo_cue = f"  * BODY ASSET FLAVOR (Small Assets: {npc_b_size} & Insecure): Cropped slightly higher or partially obscured by folded arms/blanket; includes a nervous, blushing text (*'I know there's not much to see... don't tease me, okay?'*).\n"
                elif is_bold or is_shameless:
                    asset_photo_cue = f"  * BODY ASSET FLAVOR (Small Assets: {npc_b_size} & Bold): Confident close-up showing cute perky contour or collarbones with a sassy caption (*'More than a handful is a waste anyway 😉'*).\n"
            elif tier_npc in ("large", "huge"):
                if is_prude:
                    asset_photo_cue = f"  * BODY ASSET FLAVOR (Large Assets: {npc_b_size} & Proud Hesitation): Bashful angle hiding face behind phone while prominent curves and cleavage spill softly across the sheets (*'I felt so embarrassed taking this... you better like it...'*).\n"
                elif is_bold or is_shameless:
                    asset_photo_cue = f"  * BODY ASSET FLAVOR (Large Assets: {npc_b_size} & Boastful): Sultry, audacious angle proudly showcasing cleavage and curves (*'Drooling yet? Take a good look'*).\n"

        intent_guidelines = (
            "- Intent: NSFW intimate photo swap. Player asked you to send an intimate photo.\n"
            "- CRITICAL CREATIVITY & VARIETY MANDATE FOR INTIMATE PHOTOS:\n"
            "  * If check Succeeded / Critical Success: You MUST write a 100% UNIQUE, CUSTOM, and IMAGINATIVE bracketed description: '[Attached Intimate Photo: ...]'.\n"
            "  * ANTI-REPETITION MANDATE: Do NOT repeat previous outfits, poses, or tropes (avoid repeating 'sheer lace slip', 'hand on hip', or 'confident smirk')! Review Conversation History and invent something completely distinct and fresh.\n"
            "  * VARY THE SETTING: tangled satin bedsheets, misted bathroom vanity glass after a hot shower, dimly lit velvet sofa, plush bedroom rug with scattered pillows, soft starlight/moonlight by window blinds, warm candlelit bedside table, or ambient neon mood lighting.\n"
            "  * VARY THE ATTIRE (OR LACK THEREOF):\n"
            "    - Provocative Everyday & Casual Clothing: an oversized dress shirt or flannel unbuttoned halfway down slipping off one shoulder, cropped tank top or baby tee pulled up teasingly, unzipped hoodie worn with nothing underneath teasing bare torso, unfastened low-rise jeans or cutoff shorts with waistband rolled down, slouchy oversized knit sweater falling off bare shoulders over thighs, form-fitting ribbed white tee clinging to skin, or relaxed sweatpants slung low on the hips.\n"
            "    - Bare Skin / Lack Thereof: completely nude lying back across tangled sheets with strategic shadows, freshly out of the shower with towel discarded nearby, nude silhouette against backlit glass, sheets draped tantalizingly low on hips, or hands/arms teasingly covering just enough.\n"
            "  * VARY THE POSE & ANGLE:\n"
            "    - Poses: kneeling upright on the mattress with arched back and hands woven into hair, laying face-down looking back over bare hips with an alluring smirk, leaning forward close to the lens teasing collarbones and chest, reclining casually with one leg pulled up, or playfully tugging down the waistband/fabric.\n"
            "    - Angles: high-angle top-down bed shot, steamy mirror reflection with wet hair, close-up focused shot with heavy-lidded bedroom eyes, or full-length candid silhouette.\n"
            "    - Mood: shy blushing glance, sultry confident grin, teasing lip-bite with a wink, drowsy late-night bedroom intimacy, or daring seductive stare.\n"
            f"{asset_photo_cue}"
            "  * PERSONALITY FIT: Make the outfit, pose, and attitude reflect your character's unique personality ({traits}) and relationship dynamic!\n"
            "  * If check Failed: You are flustered or embarrassed, telling them it's too fast or asking them to delete it. Do NOT send a photo.\n"
            "  * If check Critical Failure: You are deeply offended, disgusted, or furious at the unsolicited intimacy. Do NOT send a photo.\n"
        )
    else:
        custom_media_guidelines = ""
        if (is_photo or is_video) and is_intimate:
            tag_example = "[Attached Intimate Video: ...]" if is_video else "[Attached Intimate Photo: ...]"
            custom_media_guidelines = (
                f"- The player appears to be asking for or exchanging intimate/spicy media.\n"
                f"- If check Succeeded / Critical Success: Agree playfully or seductively and attach a vivid description formatted exactly as `{tag_example}`.\n"
                f"- If check Failed: You are flustered/embarrassed or decline politely. Do NOT attach media.\n"
                f"- If check Critical Failure: You are offended or reject the advance firmly. Do NOT attach media.\n"
            )
        elif is_video:
            custom_media_guidelines = (
                "- The player appears to be asking for or exchanging a video.\n"
                "- If check Succeeded / Critical Success: Agree happily and attach a vivid description formatted exactly as `[Attached Video: ...] `.\n"
                "- If check Failed / Critical Failure: Decline or say your camera/connection is acting up. Do NOT attach media.\n"
            )
        elif is_photo:
            custom_media_guidelines = (
                "- The player appears to be asking for or exchanging a photo/selfie.\n"
                "- If check Succeeded / Critical Success: Agree happily and attach a vivid description formatted exactly as `[Attached Photo: ...] `.\n"
                "- If check Failed / Critical Failure: Decline or say you look a mess. Do NOT attach media.\n"
            )

        intent_guidelines = (
            f"- Intent: Custom message from player. Respond in-character matching your personality and relationship standing.\n"
            + custom_media_guidelines
        )
        if existing_appointment:
            existing_loc = existing_appointment["rendezvous_location"]
            intent_guidelines += (
                f"- EXISTING APPOINTMENT NOTE: You and the player ALREADY have a confirmed plan to meet up at '{existing_loc}'. "
                f"You may reference seeing them there soon if relevant, but do NOT schedule a new or different rendezvous location.\n"
            )

    if is_prude and intent in ("nsfw_photo", "nsfw_video"):
        intent_guidelines += (
            "- EROTIC OPENNESS (Prude / Modest): You are deeply modest and protective of your decency. "
            "You firmly refuse to send any spicy or indecent photo/video and scold or blush with flustered indignation (e.g. 'A-Are you out of your mind?!', 'I'm not sending that!'). Do NOT attach media.\n"
        )
    elif is_shameless and intent in ("nsfw_photo", "nsfw_video"):
        intent_guidelines += (
            "- EROTIC OPENNESS (Shameless / Lewd): You have zero modesty barrier and love teasing the player with bold, spicy remarks! "
            "If check succeeded, enthusiastically send the photo/video with playful, sultry confidence.\n"
        )

    # Ground intimate media descriptions in canonical undergarments and intimate demeanor
    if intent in ("nsfw_photo", "nsfw_video") or "nsfw" in intent or is_intimate:
        under_lines = []
        if bra_str or und_str:
            under_lines.append(
                f"- CANONICAL UNDERGARMENTS: When depicting intimate photos/videos in undergarments, loungewear, or bedroom attire, "
                f"STRICTLY depict your canonical undergarments [Bra: {bra_str or 'None (Bra-less)'}, Underwear: {und_str or 'None (Commando)'}]. "
                f"Never depict garments you do not wear!"
            )
        if intimate_dem:
            under_lines.append(f"- INTIMATE DEMEANOR: Express your defined intimate demeanor ({intimate_dem}) in your camera gaze, body language, and text tone.")
        if intimate_dyn:
            under_lines.append(f"- INTIMATE DYNAMIC: Reflect your dynamic ({intimate_dyn}) in your pose confidence and proactivity.")
        if under_lines:
            intent_guidelines += "\n" + "\n".join(under_lines) + "\n"

    if intent == "meetup":
        dm_schema = """{
  "reply_text": "string, 1-3 sentences in natural texting style with casual tone/emojis",
  "affinity_delta": integer -5 to 6,
  "rendezvous_location": "string, meeting location name from the provided list"
}"""
    else:
        dm_schema = """{
  "reply_text": "string, 1-3 sentences in natural texting style with casual tone/emojis",
  "affinity_delta": integer -5 to 6
}"""

    # In-person shared memories grounding (Bidirectional recall)
    in_person_hint = ""
    def _coerce_mem_list(raw_val):
        if not raw_val:
            return []
        if isinstance(raw_val, list):
            return list(raw_val)
        if isinstance(raw_val, str):
            try:
                parsed = json.loads(raw_val)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
            return [raw_val.strip()]
        return []

    recent_in_person_mems = _coerce_mem_list(contact.get("recent_memories") or contact.get("rel_history"))
    intimate_in_person_mems = [m for m in _coerce_mem_list(contact.get("intimate_memories")) if not str(m).startswith("Past History:")]
    in_person_snippets = []
    for m in (recent_in_person_mems + intimate_in_person_mems)[-8:]:
        m_str = str(m).strip()
        if m_str and not m_str.startswith("Exchanged ") and not m_str.startswith("Agreed via DM"):
            if m_str not in in_person_snippets:
                in_person_snippets.append(m_str)
    if in_person_snippets:
        in_person_hint = (
            "- RECENT IN-PERSON SHARED EXPERIENCES & MEMORIES:\n"
            + "\n".join(f"  • {s}" for s in in_person_snippets[-4:]) + "\n"
            + "- DIRECTIVE: You remember these real shared experiences from your time together in person with the player. If natural or relevant to the conversation topic, you may casually reminisce, reference, or tease them about these moments in your texts!\n"
        )

    dm_gate = evaluate_dm_in_person_gate(
        session_id=session_id,
        contact_name=contact_name,
        track=track,
        user_message=user_message,
        intent=intent,
    )
    if dm_gate.get("directive"):
        intent_guidelines += dm_gate["directive"]

    dm_lang_dir = build_side_channel_language_directive(
        session,
        text_fields=("reply_text",),
        preserve_fields=("rendezvous_location", "[Attached Photo:/Video: ...] bracket prefix"),
        style="sms",
        speaker_gender=str(contact.get("gender") or basic.get("gender") or ""),
        recipient_gender=str(player_char.get("gender") or session.get("lead_character_gender") or ""),
    )
    system_prompt = (
        f"You are roleplaying as {contact_name}, an NPC contact in a {scen_key} story.\n"
        f"Your Role: {role}. Personality Traits: {traits}. Relationship Affinity: {score} ({track.capitalize()} track).\n"
        f"Player's Skill Check Outcome: {check_result.tier_label} (Tier: {check_result.tier}).\n"
        f"Format: Mobile text message reply in {branding['dm_app_name']}.\n"
        f"Guidelines:\n"
        f"- Write a short, in-character text message reply (1-3 sentences).\n"
        f"- Use emojis, casual punctuation, and tone matching your personality.\n"
        f"- ANTI-REPETITION MANDATE: Do NOT reuse the same phrasing, adjectives, poses, or outfit descriptions that appear in recent messages in Conversation History. Always keep it fresh and varied!\n"
        f"- Tone & Reaction MUST match the skill check tier:\n"
        f"  * Critical Success: Deeply impressed, thrilled, or charmed. Set positive affinity_delta.\n"
        f"  * Success: Respond warmly, positively, or playfully. Set positive affinity_delta.\n"
        f"  * Failure: Distracted, awkward, or polite refusal.\n"
        f"  * Critical Failure: Cringe, annoyed, offended, or firm rejection.\n"
        + time_schedule_hint
        + intent_guidelines
        + sq_hint
        + feed_hint
        + in_person_hint
        + family_and_grade_hint
        + epistemic_hint
        + meetup_location_hint
        + (f"{dm_lang_dir}\n" if dm_lang_dir else "")
        + f"Respond with ONLY a single valid JSON object matching the schema:\n{dm_schema}"
    )

    user_prompt = (
        f"Conversation History:\n{history_text}\n"
        f"Player ({player_char.get('name', 'Hero')}): {fence_player_message(user_message, max_len=500)}\n"
        f"Intent: {intent}\n"
        f"Generate {contact_name}'s text reply JSON:"
    )

    call_temp = 0.9 if intent in ("photo", "nsfw_photo", "video", "nsfw_video", "flirt") else 0.8
    try:
        result = await mechanics.system.phone.call_llm_json(system_prompt, user_prompt, temperature=call_temp, is_nsfw=scenario_data.uses_nsfw_model(scen_key), use_utility=True)
    except Exception as e:
        log.warning(f"[phone] Failed to generate dynamic contact reply: {e}")
        result = {}
    reply_text = result.get("reply_text")
    if not reply_text:
        if intent == "meetup":
            if check_result.succeeded:
                rend_cand = result.get("rendezvous_location", "")
                if not rend_cand and known_locations:
                    loc_item = known_locations[0]
                    p_name = loc_item.get("primary_name", "")
                    s_name = loc_item.get("sub_name", "")
                    rend_cand = f"{p_name}" + (f" ({s_name})" if s_name else "")
                    result["rendezvous_location"] = rend_cand
                venue_str = rend_cand or "our favorite spot"
                if is_romantic:
                    reply_text = f"I'd love that! Why don't we meet at {venue_str} in a bit? 🌹"
                else:
                    reply_text = f"Sounds great! Let's meet at {venue_str} in a bit 👍"
            else:
                reply_text = "I'm a bit tied up right now, but let's definitely catch up another time! 😊"
        else:
            reply_text = f"Hey {player_char.get('name', 'there')}! Got your message, let's catch up soon."

    # Safeguard: if check succeeded and intent is an ask for photo/video, ensure bracketed media description is attached
    if check_result.succeeded and intent in ("nsfw_photo", "nsfw_video", "spicy_ask", "ask_spicy", "photo", "video", "photo_ask", "ask_photo"):
        has_attachment = any(tag in reply_text for tag in [
            "[Attached Intimate Video:", "[Attached Video:",
            "[Attached Intimate Photo:", "[Attached Photo:"
        ])
        if not has_attachment:
            fallback_caption = generate_npc_photo_caption(contact, intent=intent, location=current_loc)
            if intent in ("nsfw_video",):
                reply_text += f"\n[Attached Intimate Video: {fallback_caption}]"
            elif intent in ("video",):
                reply_text += f"\n[Attached Video: {fallback_caption}]"
            elif intent in ("nsfw_photo", "spicy_ask", "ask_spicy"):
                reply_text += f"\n[Attached Intimate Photo: {fallback_caption}]"
            else:
                reply_text += f"\n[Attached Photo: {fallback_caption}]"

    # Shameless / Lewd bonus media drop (chance for second media attachment unprompted)
    if check_result.succeeded and is_shameless and intent in ("nsfw_photo", "spicy_ask", "ask_spicy"):
        if "[Attached Intimate Video:" not in reply_text and "[Attached Bonus Intimate Video:" not in reply_text:
            import hashlib
            seed_bonus = (contact_name + str(session_id) + str(int(time.time()))).encode("utf-8")
            if (int(hashlib.md5(seed_bonus).hexdigest(), 16) % 100) < 50:
                bonus_caption = generate_npc_photo_caption(contact, intent="nsfw_video", location=current_loc)
                reply_text += f"\n[Attached Bonus Intimate Video: {bonus_caption}]"

    # Enforce deterministic bounds based on check tier, intent, and gender dynamics
    if intent in ("spicy_send", "send_spicy", "nsfw_send"):
        if check_result.succeeded:
            affinity_delta = 4 if check_result.tier == "crit_success" else 2
            if is_player_female and is_npc_male:
                affinity_delta = min(5, affinity_delta + 1)
        else:
            if is_player_male and is_npc_female:
                if is_shameless:
                    affinity_delta = 0
                elif check_result.tier == "crit_fail":
                    affinity_delta = -6
                else:
                    affinity_delta = -4
            elif is_player_female and is_npc_male:
                if is_prude:
                    affinity_delta = -3 if check_result.tier == "crit_fail" else -2
                else:
                    affinity_delta = -1 if check_result.tier == "crit_fail" else 0
            else:
                affinity_delta = -4 if check_result.tier == "crit_fail" else -2
        rendezvous = ""
    elif check_result.tier == "crit_success":
        if intent in ("nsfw_photo", "nsfw_video", "spicy_ask", "ask_spicy"):
            affinity_delta = max(4, min(6, int(result.get("affinity_delta", 4))))
        elif intent == "flirt":
            affinity_delta = max(3, min(4, int(result.get("affinity_delta", 3))))
        elif intent in ("photo_send", "send_photo"):
            affinity_delta = 2
        elif intent in ("chat", "custom"):
            affinity_delta = 5 if score < 50 else 3
        else:
            affinity_delta = max(3, min(5, int(result.get("affinity_delta", 3))))
        rendezvous = result.get("rendezvous_location", "") if intent == "meetup" else ""
    elif check_result.tier == "success":
        if intent in ("nsfw_photo", "nsfw_video", "spicy_ask", "ask_spicy"):
            affinity_delta = max(2, min(4, int(result.get("affinity_delta", 2))))
        elif intent == "flirt":
            affinity_delta = 2
        elif intent in ("photo_send", "send_photo"):
            affinity_delta = 1
        elif intent in ("chat", "custom"):
            affinity_delta = 4 if score < 50 else 2
        else:
            affinity_delta = max(1, min(3, int(result.get("affinity_delta", 1))))
        rendezvous = result.get("rendezvous_location", "") if intent == "meetup" else ""
    elif check_result.tier == "fail":
        if intent in ("nsfw_photo", "nsfw_video", "spicy_ask", "ask_spicy"):
            raw_delta = int(result.get("affinity_delta", -1))
            affinity_delta = min(-1, max(-2, raw_delta if raw_delta < 0 else -1))
        elif intent == "flirt":
            affinity_delta = -1
        elif intent in ("photo_send", "send_photo"):
            affinity_delta = 0
        else:
            affinity_delta = 0
        rendezvous = ""
    else:  # crit_fail
        if intent in ("nsfw_photo", "nsfw_video", "spicy_ask", "ask_spicy"):
            raw_delta = int(result.get("affinity_delta", -3))
            affinity_delta = min(-3, max(-5, raw_delta if raw_delta < 0 else -3))
        elif intent == "flirt":
            affinity_delta = -2
        elif intent in ("photo_send", "send_photo"):
            affinity_delta = -1
        else:
            raw_delta = int(result.get("affinity_delta", -2))
            affinity_delta = min(-1, max(-3, raw_delta if raw_delta < 0 else -2))
        rendezvous = ""

    if dm_gate.get("max_affinity_delta") is not None and affinity_delta > int(dm_gate["max_affinity_delta"]):
        affinity_delta = int(dm_gate["max_affinity_delta"])
    if is_autonomy_ping_decline:
        affinity_delta = max(0, affinity_delta)

    _pre_resolve_intent = intent
    resolved_rendezvous, intent = resolve_rendezvous_location(
        session_id=session_id,
        contact_name=contact_name,
        current_loc=current_loc,
        rendezvous=rendezvous,
        reply_text=reply_text,
        known_locations=known_locations,
        existing_appointment=existing_appointment,
        is_reschedule_request=is_reschedule_request,
        intent=intent,
        check_succeeded=check_result.succeeded,
        user_message=user_message,
        history_rows=history_rows,
        scenario=scen_key,
    )
    if _pre_resolve_intent == "meetup" and intent == "chat" and not resolved_rendezvous:
        reply_text = (
            (reply_text.rstrip() + "\n\n" if reply_text.strip() else "")
            + "*(Quarantine Refusal: Civilian contacts decline meetups inside active anomalous quarantine zones.)*"
        )
    if scenario_data.is_anomalous_incursions_scenario(scen_key):
        try:
            from mechanics.world.anomalous_sites import compute_domain_skill_check_modifiers
            _dom_msg_mod = await db.adb(
                compute_domain_skill_check_modifiers,
                session_id,
                session,
                int((player_char or {}).get("user_id") or 0),
                player_char,
                "INT",
            )
            if _dom_msg_mod.get("jam_comms"):
                reply_text = (
                    (reply_text.rstrip() + "\n\n" if reply_text.strip() else "")
                    + "*(Numbers-Station Interference: Subterranean Faraday jamming distorts carrier signal with rhythmic static.)*"
                )
        except Exception:
            pass

    # Save messages to SQLite
    await db.adb(db.save_phone_message, session_id, npc_id, sender="player", message=user_message, intent=intent)
    await db.adb(db.save_phone_message, session_id, npc_id, sender="npc", message=reply_text, intent=intent)
    dm_turn_idx = max(1, len((session or {}).get("history") or []))
    proof_ref = f"dm:{clean_npc_id}:{dm_turn_idx}"
    _dm_trust_delta = 0

    # B12: Bitter rival screenshot/DM receipt (mints/upgrades hard_proof regardless of check outcome)
    is_bitter_rival = score <= -25
    if not is_bitter_rival:
        try:
            from mechanics.social import relationship_graph as _rg_dm
            _rival_ties = await db.adb(_rg_dm.get_ties, session_id, clean_npc_id or contact_name) or []
            for _rt in _rival_ties:
                if str(_rt.get("status") or "active").lower() != "active":
                    continue
                if str(_rt.get("tie_type") or "").strip().lower() not in ("rival", "enemy"):
                    continue
                _rpa = str(_rt.get("person_a_key") or "").strip().lower()
                _rpb = str(_rt.get("person_b_key") or "").strip().lower()
                if _rg_dm.is_player_person_key(_rpa) or _rg_dm.is_player_person_key(_rpb):
                    is_bitter_rival = True
                    break
        except Exception:
            pass

    _incrim_kws = (
        "secret", "stole", "steal", "affair", "cheating", "bribe",
        "confess", "killed", "broke in", "love you",
    )
    is_incriminating_dm = bool(
        is_intimate
        or intent in ("flirt", "nsfw_photo", "nsfw_video", "spicy_ask", "spicy_send", "send_spicy", "ask_spicy", "nsfw_send", "confess")
        or any(_kw in msg_lower for _kw in _incrim_kws)
    )
    if is_bitter_rival and is_incriminating_dm:
        _rival_fkey = ""
        for _kf in epistemic_ctx.get("known_facts") or []:
            if str(_kf.get("category") or "") in ("affair", "romance", "secret_romance", "intimate", "confession", "secret", "crime"):
                _rival_fkey = str(_kf.get("fact_key") or "")
                break
        if not _rival_fkey and (epistemic_ctx.get("known_facts") or []):
            _rival_fkey = str((epistemic_ctx.get("known_facts") or [])[0].get("fact_key") or "")
        if not _rival_fkey:
            _rival_fkey = f"dm_receipt:{clean_npc_id}:{dm_turn_idx}"
        await db.adb(
            db.upsert_epistemic_fact,
            session_id,
            _rival_fkey,
            category="affair" if (is_intimate or is_romantic or intent == "flirt") else "secret",
            culprit_actor_key="player",
            subject_actor_key=clean_npc_id,
            summary=f"Incriminating DM receipt kept by {contact_name}",
            proof_artifact_ref=proof_ref,
            severity=2,
            heat_score=65,
            decay_day_last_ticked=current_day,
            status="active",
            turn=dm_turn_idx,
        )
        await db.adb(
            db.upsert_epistemic_knowledge,
            session_id,
            _rival_fkey,
            clean_npc_id,
            confidence="hard_proof",
            containment_state="active",
            source_actor_key="player",
            acquisition_channel="dm",
            hop_count=0,
            player_aware=1,
            metadata={"screenshot_risk": True},
            turn=dm_turn_idx,
        )
    elif check_result.succeeded and (is_intimate or intent in ("flirt", "nsfw_photo", "spicy_ask", "spicy_send", "confess")):
        for kf in epistemic_ctx.get("known_facts") or []:
            if str(kf.get("category") or "") in ("affair", "romance", "secret_romance", "intimate", "confession"):
                await db.adb(db.upsert_epistemic_fact, session_id, kf["fact_key"], proof_artifact_ref=proof_ref, turn=dm_turn_idx)
                break

    # B12: Remote DM epistemic containment (hush / discretion / alibi / proof sharing)
    _contain_phrases = (
        "keep this quiet", "stay quiet", "don't tell", "dont tell", "do not tell",
        "alibi", "between us", "hush", "cover for me", "keep my secret", "swear not to tell",
    )
    is_dm_containment = bool(
        intent in ("epistemic_containment", "hush", "alibi")
        or any(_cph in msg_lower for _cph in _contain_phrases)
    )
    if is_dm_containment:
        if intent == "alibi" or "alibi" in msg_lower or "cover for me" in msg_lower:
            _dm_subtype = "deny"
        elif "bribe" in msg_lower or "pay you" in msg_lower:
            _dm_subtype = "hush_bribe"
        elif "proof" in msg_lower or "evidence" in msg_lower:
            _dm_subtype = "present_proof"
        else:
            _dm_subtype = "discretion_request"

        _dm_fact_key = ""
        for _kf in epistemic_ctx.get("known_facts") or []:
            if str(_kf.get("containment_state") or "active") in ("spotted_window", "active"):
                _dm_fact_key = str(_kf.get("fact_key") or "")
                break
        if not _dm_fact_key and (epistemic_ctx.get("known_facts") or []):
            _dm_fact_key = str((epistemic_ctx.get("known_facts") or [])[0].get("fact_key") or "")
        if not _dm_fact_key:
            try:
                _holder_rows = await db.adb(db.get_epistemic_knowledge_rows, session_id, holder_actor_key=clean_npc_id) or []
                for _hr in _holder_rows:
                    if str(_hr.get("containment_state") or "active") in ("spotted_window", "active"):
                        _dm_fact_key = str(_hr.get("fact_key") or "")
                        break
                if not _dm_fact_key:
                    for _hr in _holder_rows:
                        if str(_hr.get("containment_state") or "active") not in ("wiped", "incapacitated"):
                            _dm_fact_key = str(_hr.get("fact_key") or "")
                            break
            except Exception:
                _dm_fact_key = ""
        if _dm_fact_key:
            try:
                from mechanics.social.epistemic_engine import resolve_containment_or_epistemic_action as _resolve_dm_ep
                _dm_ep_res = await db.adb(
                    _resolve_dm_ep,
                    session_id,
                    session,
                    _dm_subtype,
                    _dm_fact_key,
                    clean_npc_id,
                    check_result,
                    dm_turn_idx,
                    alibi_claim=user_message if _dm_subtype == "deny" else "",
                    proof_artifact_ref=proof_ref if _dm_subtype == "present_proof" else "",
                )
                if isinstance(_dm_ep_res, dict):
                    _dm_trust_delta = int(_dm_ep_res.get("trust_delta") or 0)
                    affinity_delta += _dm_trust_delta
            except Exception as _dm_ep_err:
                log.warning(f"[phone] Remote DM epistemic containment failed: {_dm_ep_err}")

    # D10: Fall back autonomy ping rendezvous to ping node/current location & clear ping after response
    if is_autonomy_ping_reply and intent == "meetup" and not resolved_rendezvous:
        _ping_node_id = str((active_ping or {}).get("node_id") or "").strip()
        if _ping_node_id:
            try:
                _ping_node = await db.adb(db.get_world_node, session_id, _ping_node_id)
            except Exception:
                _ping_node = None
            if isinstance(_ping_node, dict):
                _pn_primary = str(_ping_node.get("primary_name") or _ping_node.get("name") or "").strip()
                _pn_sub = str(_ping_node.get("sub_name") or "").strip()
                if _pn_primary:
                    resolved_rendezvous = f"{_pn_primary}" + (f" ({_pn_sub})" if _pn_sub else "")
        if not resolved_rendezvous:
            resolved_rendezvous = str(
                (active_ping or {}).get("location_name")
                or (active_ping or {}).get("node_name")
                or current_loc
                or ""
            ).strip()

    # Persist meetup appointment so the NPC appears at the rendezvous location
    if resolved_rendezvous and intent == "meetup":
        # Only save if there is no active appointment for this contact or the location has changed
        if not existing_appointment or existing_appointment.get("rendezvous_location") != resolved_rendezvous:
            await db.adb(db.save_phone_appointment, session_id, npc_id, contact_name, resolved_rendezvous, is_confidential=is_romantic)
            # Update contact known location so spatial queries and world tracker recognize where they are situated
            existing_basic = dict(contact.get("basic_info") or {})
            existing_basic["location"] = resolved_rendezvous
            meet_term = "a romantic date" if is_romantic else "a meetup"
            meet_mem = f"Agreed via DM to meet for {meet_term} at {resolved_rendezvous}"
            await db.adb(
                db.upsert_contact,
                session_id=session_id,
                character_id=player_char.get("id", 0),
                npc_id=npc_id,
                name=contact_name,
                basic_info=existing_basic,
                track=track,
                new_memory=meet_mem
            )
            log.info(f"[phone] Appointment saved: {contact_name} @ {resolved_rendezvous} for session {session_id}")

    if is_autonomy_ping_reply or is_autonomy_ping_decline:
        try:
            await db.adb(
                db.apply_world_roster_autonomy_mutations,
                session_id,
                [{"npc_id": clean_npc_id or npc_id, "clear_pending_hangout_ping": True}],
                turn_number=dm_turn_idx,
            )
        except Exception as _ping_clr_err:
            log.warning(f"[phone] Failed to clear pending_hangout_ping for {npc_id}: {_ping_clr_err}")

    # Record memorable flirtation milestone
    if intent == "flirt" and check_result.succeeded and affinity_delta >= 2:
        flirt_mem = f"Shared playful, affectionate flirtation via DM with {contact_name}"
        await db.adb(
            db.upsert_contact,
            session_id=session_id,
            character_id=player_char.get("id", 0),
            npc_id=npc_id,
            name=contact_name,
            track=track,
            new_memory=flirt_mem
        )
        try:
            from mechanics.social.persona.intimacy.ledger import record_intimate_turn_encounter
            turn_dm = max(1, len((session or {}).get("history") or []))
            record_intimate_turn_encounter(
                session_id=session_id,
                character_id=npc_id,
                character_name=contact_name,
                character_gender=str(contact.get("gender") or ""),
                partner_id="player",
                partner_name=str(player_char.get("name") or "Player"),
                milestone_event="dm_flirt",
                turn_number=turn_dm,
                day_number=current_day,
                location="Phone DM",
                custom_summary=flirt_mem,
                is_physical_override=False,
            )
        except Exception as _dm_led_err:
            log.warning(f"[phone] Failed to record DM flirt milestone: {_dm_led_err}")

    # Shared +18/+30 Daily Digestion Cap & Tier 1 Dossier Unlock (no room Composure drain)
    dm_digestion_capped = False
    dm_discovered_facts = []
    if is_contact_eligible(name=contact_name, role=role, scenario=scen_key):
        from mechanics.social import consequences as _soc_conseq
        from mechanics.social import pacing as _soc_pacing

        turn_dm_idx = max(1, len((session or {}).get("history") or []))
        char_id_val = int(player_char.get("id", 0) or 0)
        if affinity_delta > 0:
            digestion_res = await db.adb(
                _soc_pacing.apply_shared_daily_digestion,
                session_id,
                char_id_val,
                contact_name,
                raw_delta=affinity_delta,
                current_day=current_day,
                is_on_date=bool(is_romantic and existing_appointment),
                is_confession=False,
                is_gift=False,
                turn_updated=turn_dm_idx,
            )
            affinity_delta = int(digestion_res.get("applied_delta", affinity_delta))
            dm_digestion_capped = bool(digestion_res.get("capped"))
        if check_result.succeeded and str(intent_category or intent or "").lower() in ("chat", "friendly", "personal", "flirt"):
            dm_cat = "flirt_chemistry" if str(intent_category or intent or "").lower() == "flirt" else "get_to_know"
            dm_discovered_facts = await db.adb(
                _soc_conseq.select_and_record_dialogue_discoveries,
                session_id,
                char_id_val,
                contact_name,
                category=dm_cat,
                topic_id=f"dm_{intent or 'chat'}",
                outcome_tier="success",
                contact_obj=contact,
                scenario=scen_key,
                turn_number=turn_dm_idx,
            )

    # Update affinity score — guard against ineligible NPCs (teachers, parents, store clerks) slipping through
    if affinity_delta != 0 or _dm_trust_delta != 0:
        if is_contact_eligible(name=contact_name, role=role, scenario=scen_key):
            delta = affinity_delta if affinity_delta != 0 else _dm_trust_delta
            new_score = clamp_score(score + delta)
            await db.adb(db.update_contact_score, session_id, npc_id, new_score, character_id=player_char.get("id", 0))
        else:
            log.info(f"[phone] Skipping affinity update for ineligible contact '{contact_name}' (role: {role}).")


    # Automatically create Digital Media Item in player inventory if a photo/video was received
    digital_item_id = None
    media_type_created = None
    if check_result.succeeded:
        digital_item_id, media_type_created = await db.adb(
            persist_dm_media_item_and_milestone,
            session=session,
            session_id=session_id,
            npc_id=npc_id,
            contact=contact,
            contact_name=contact_name,
            track=track,
            player_char=player_char,
            reply_text=reply_text,
            intent=intent,
            current_day=current_day,
        )

    if intent_category and not (is_autonomy_ping_reply and intent_category == "meetup"):
        meta = {}
        if intent_category == "flirt":
            existing_hist = list(daily_limits["flirt"].get("history", []))
            existing_hist.append({
                "attempt": flirt_attempt_num,
                "outcome": check_result.tier,
                "succeeded": check_result.succeeded,
            })
            meta["history"] = existing_hist
        elif intent_category == "meetup":
            if is_reschedule_request:
                meta["relocations_used"] = relocation_num
            else:
                meta["relocations_used"] = 0

        await db.adb(
            db.record_phone_daily_interaction,
            session_id=session_id,
            npc_id=npc_id,
            current_day=current_day,
            intent=intent_category,
            outcome=check_result.tier,
            metadata=meta,
            is_over_limit=False
        )

    updated_limits = await db.adb(db.get_phone_daily_limits, session_id, npc_id, current_day)

    return {
        "reply_text": reply_text,
        "affinity_delta": affinity_delta,
        "rendezvous_location": resolved_rendezvous,
        "is_romantic": is_romantic,
        "intent": intent,
        "new_score": clamp_score(score + affinity_delta),
        "digital_item_id": digital_item_id,
        "media_type_created": media_type_created,
        "daily_limits": updated_limits,
        "daily_digestion_capped": dm_digestion_capped,
        "discovered_facts": dm_discovered_facts,
        "check_result": {
            "stat": stat_name,
            "chance": check_result.chance,
            "tier": check_result.tier,
            "tier_label": check_result.tier_label,
            "succeeded": check_result.succeeded
        }
    }

