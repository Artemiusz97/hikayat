from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

import db
import mechanics.system.phone
import scenario_data
from mechanics.social.relationships import clamp_score, is_contact_eligible

log = logging.getLogger("hikayat.phone")


async def handle_dm_over_limit(
    *,
    session_id: int,
    npc_id: str,
    contact_name: str,
    role: str,
    traits: str,
    score: int,
    track: str,
    is_romantic: bool,
    scen_key: str,
    intent: str,
    intent_category: str,
    daily_limits: dict[str, Any],
    existing_appointment: Optional[dict[str, Any]],
    player_char: dict[str, Any],
    user_message: str,
    current_day: int,
) -> dict[str, Any]:
    """Handles over-limit phone DM attempts with escalating badgering penalties."""
    over_count = daily_limits.get(intent_category, {}).get("over_limit_count", 0) + 1
    if intent_category == "chat":
        affinity_delta = 0
    elif over_count == 1:
        affinity_delta = -1 if intent in ("spicy_send", "send_spicy", "nsfw_send") else 0
    elif over_count == 2:
        affinity_delta = -2
    elif over_count == 3:
        affinity_delta = -4
    else:
        affinity_delta = -6

    system_prompt = (
        f"You are {contact_name}, an NPC contact in a {scen_key} story.\n"
        f"Role: {role}. Traits: {traits}. Relationship Affinity: {score} ({track.capitalize()} track).\n"
        f"SITUATION: The player is repeatedly attempting an action ({intent_category}) that has exceeded today's daily limit.\n"
        f"This is over-limit attempt #{over_count} from the player today.\n"
        f"Guidelines for Attempt #{over_count}:\n"
    )
    if over_count == 1:
        system_prompt += (
            "- ATTEMPT #1 (Boundary / Friendly Refusal): Respond in-character by politely or casually declining for today.\n"
            "- Mention you've shared enough for today, have errands/classes to get to, or let's pick it up tomorrow.\n"
        )
    elif over_count == 2:
        system_prompt += (
            "- ATTEMPT #2 (Irritated / Annoyed): Express clear annoyance that they are asking or sending again after being declined.\n"
            "- Remind them firmly to stop pushing it.\n"
        )
    else:
        system_prompt += (
            f"- ATTEMPT #{over_count} (Severe Badgering / Harassment): Express strong irritation, disgust, or cold disapproval.\n"
            "- Call them out for relentlessly badgering you and crossing boundaries.\n"
        )
    system_prompt += (
        "Write a short, realistic mobile text reply (1-2 sentences) in natural messaging style.\n"
        "Respond with ONLY a single valid JSON object matching:\n"
        '{"reply_text": "string"}'
    )
    user_prompt = f"Player ({player_char.get('name', 'Hero')}): {user_message}\nGenerate {contact_name}'s refusal text reply:"

    reply_text = None
    _is_llm_mocked = hasattr(mechanics.system.phone.call_llm_json, "_mock_name")
    if _is_llm_mocked:
        try:
            res_json = await mechanics.system.phone.call_llm_json(
                system_prompt,
                user_prompt,
                temperature=0.7,
                is_nsfw=scenario_data.uses_nsfw_model(scen_key),
                use_utility=True,
            )
            reply_text = (res_json.get("reply_text") or "").strip()
        except Exception as e:
            log.warning(f"[phone] Failed to generate LLM over-limit refusal: {e}")

    if not reply_text:
        if intent_category == "flirt":
            if over_count == 1:
                reply_text = "Haha, you're sweet, but let's give the charm a break for today! Let's talk about something else 😊"
            elif over_count == 2:
                reply_text = "Okay, I told you to take it easy on the flirting. It's getting a bit much right now."
            else:
                reply_text = "Are you listening to me at all? Stop trying to flirt with me, I'm seriously getting annoyed."
        elif intent_category == "meetup":
            if over_count == 1:
                if existing_appointment:
                    reply_text = f"We already settled our plans for today at {existing_appointment.get('rendezvous_location')}! Let's stick with that for now."
                else:
                    reply_text = "I already told you I can't meet up today! Let's catch up another time."
            elif over_count == 2:
                reply_text = "I told you, I can't keep rearranging or meeting up again today. Stop bugging me about it."
            else:
                reply_text = "Enough already. I'm not changing plans or meeting with you today, drop it."
        elif intent_category == "photo":
            if over_count == 1:
                reply_text = "That's enough photos for today! My camera is going away before my battery dies haha 📸"
            elif over_count == 2:
                reply_text = "I already told you no more photos today. Please stop asking."
            else:
                reply_text = "Seriously? Stop badgering me for photos. It's really obnoxious."
        elif intent_category == "spicy":
            if over_count == 1:
                reply_text = "Definitely not sending anything like that anymore today. Let's change the subject."
            elif over_count == 2:
                reply_text = "I said no more spicy stuff today. Stop pushing it, seriously."
            else:
                reply_text = "What is wrong with you? Stop sending or asking for that. You're being genuinely creepy now."
        elif intent_category == "rumor":
            if over_count == 1:
                reply_text = "That's all the gossip I've got for today! I'm not a 24/7 bulletin board haha 🤫"
            elif over_count == 2:
                reply_text = "I told you I don't have any more rumors. Stop digging."
            else:
                reply_text = "I'm not helping you spread or dig up any more gossip today. Drop it."
        elif intent_category == "chat":
            if over_count == 1:
                reply_text = "Hey, I've got my hands full right now—let's catch up in person or text more tomorrow! 😊"
            else:
                reply_text = "Still tied up with things on my end today! Let's pick this up tomorrow 😊"
        else:
            reply_text = "Let's take a break for today."

    db.save_phone_message(session_id, npc_id, sender="player", message=user_message, intent=intent)
    db.save_phone_message(session_id, npc_id, sender="npc", message=reply_text, intent=intent)

    if affinity_delta != 0:
        if is_contact_eligible(name=contact_name, role=role, scenario=scen_key):
            new_score = clamp_score(score + affinity_delta)
            db.update_contact_score(session_id, npc_id, new_score, character_id=player_char.get("id", 0))

    updated_limits = db.record_phone_daily_interaction(
        session_id=session_id,
        npc_id=npc_id,
        current_day=current_day,
        intent=intent_category,
        outcome="over_limit",
        is_over_limit=True,
    )

    return {
        "reply_text": reply_text,
        "affinity_delta": affinity_delta,
        "rendezvous_location": "",
        "is_romantic": is_romantic,
        "intent": intent,
        "new_score": clamp_score(score + affinity_delta),
        "digital_item_id": None,
        "media_type_created": None,
        "daily_limits": updated_limits,
        "check_result": {
            "stat": "CHA",
            "chance": 0,
            "tier": "fail",
            "tier_label": "Over Limit",
            "succeeded": False,
        },
    }


def persist_dm_media_item_and_milestone(
    *,
    session: dict[str, Any],
    session_id: int,
    npc_id: str,
    contact: dict[str, Any],
    contact_name: str,
    track: str,
    player_char: dict[str, Any],
    reply_text: str,
    intent: str,
    current_day: int,
) -> Tuple[Optional[int], Optional[str]]:
    """Creates a Digital Media Item and records caption-aware milestone memories when media is received."""
    from mechanics.combat.items import create_digital_media_item

    digital_item_id = None
    media_type_created = None
    media_type = None
    media_caption = None

    if "[Attached Intimate Video:" in reply_text:
        media_type = "nsfw_video"
        media_caption = reply_text.partition("[Attached Intimate Video:")[2].partition("]")[0].strip()
    elif "[Attached Video:" in reply_text:
        media_type = "video"
        media_caption = reply_text.partition("[Attached Video:")[2].partition("]")[0].strip()
    elif "[Attached Intimate Photo:" in reply_text:
        media_type = "nsfw_photo"
        media_caption = reply_text.partition("[Attached Intimate Photo:")[2].partition("]")[0].strip()
    elif "[Attached Photo:" in reply_text:
        media_type = "photo"
        media_caption = reply_text.partition("[Attached Photo:")[2].partition("]")[0].strip()
    elif intent in ("nsfw_photo", "nsfw_video", "spicy_ask", "ask_spicy"):
        media_type = "nsfw_video" if "video" in intent else "nsfw_photo"
        media_caption = reply_text
    elif intent in ("photo", "video", "photo_ask", "ask_photo"):
        media_type = "video" if "video" in intent else "photo"
        media_caption = reply_text

    if media_type and media_caption:
        p_uid = player_char.get("user_id") or session.get("user_id") or session.get("owner_id")
        if p_uid:
            digital_item_id = create_digital_media_item(
                user_id=p_uid,
                contact_name=contact_name,
                media_type=media_type,
                caption=media_caption,
                tags=["misc", "digital"],
            )
            media_type_created = media_type

        clean_cap = media_caption.strip().lstrip("[").rstrip("]").strip()
        for prefix in [
            "Attached Intimate Video:",
            "Attached Video:",
            "Attached Intimate Photo:",
            "Attached Photo:",
            "Intimate Video:",
            "Video:",
            "Intimate Photo:",
            "Photo:",
        ]:
            if clean_cap.startswith(prefix):
                clean_cap = clean_cap[len(prefix):].strip()

        if media_type in ("nsfw_video", "intimate_video"):
            media_mem = f"Exchanged intimate video via DM: {contact_name} ({clean_cap})"
        elif media_type in ("nsfw_photo", "intimate_photo"):
            media_mem = f"Exchanged intimate photo via DM: {contact_name} ({clean_cap})"
        elif media_type == "video":
            media_mem = f"Exchanged video clip via DM: {contact_name} ({clean_cap})"
        else:
            media_mem = f"Exchanged casual photo via DM: {contact_name} ({clean_cap})"

        db.upsert_contact(
            session_id=session_id,
            character_id=player_char.get("id", 0),
            npc_id=npc_id,
            name=contact_name,
            track=track,
            new_memory=media_mem,
        )
        try:
            from mechanics.social.persona.intimacy.ledger import record_intimate_turn_encounter

            turn_dm = max(1, len((session or {}).get("history") or []))
            dm_ev_tag = f"dm_{media_type}"
            record_intimate_turn_encounter(
                session_id=session_id,
                character_id=npc_id,
                character_name=contact_name,
                character_gender=str(contact.get("gender") or ""),
                partner_id="player",
                partner_name=str(player_char.get("name") or "Player"),
                milestone_event=dm_ev_tag,
                turn_number=turn_dm,
                day_number=current_day,
                location="Phone DM",
                custom_summary=media_mem,
                is_physical_override=False,
            )
        except Exception as _dm_med_err:
            log.warning(f"[phone] Failed to record DM media milestone: {_dm_med_err}")

    return digital_item_id, media_type_created
