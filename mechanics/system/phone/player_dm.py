from __future__ import annotations
import logging
import random
import re
import db
import scenario_data
import mechanics.system.phone
from .media_captions import (
    generate_player_casual_photo,
    generate_player_spicy_photo
)

log = logging.getLogger("hikayat.phone")


async def generate_player_chat_message(session: dict, contact: dict, player_char: dict, intent: str = "chat") -> str:
    """Generates a dynamic, in-character text message from the player to the NPC contact based on history and context."""
    session_id = session["id"]
    contact_name = contact.get("name", "Contact")
    npc_id = contact.get("npc_id") or contact_name.lower().replace(" ", "_")
    score = contact.get("relationship_score", 0)
    track = contact.get("track", "platonic")
    scen_key = session.get("scenario", "fantasy")
    char_name = player_char.get("name", "Hero")

    basic = contact.get("basic_info", {})
    role = basic.get("role") or basic.get("occupation") or "Contact"
    current_loc = session.get("current_location", "Local Area")

    # Fetch recent message history (up to 8 messages)
    history_rows = db.get_phone_messages(session_id, npc_id, limit=8)
    history_text = "\n".join(f"{'Player' if r['sender'] == 'player' else contact_name}: {r['message']}" for r in history_rows)

    # Active quest / situation context
    active_sq = db.get_active_story_quest(session_id)
    sq_hint = ""
    if active_sq:
        sq_title = active_sq.get("title", "")
        sq_hint = f"- Active Quest Context: '{sq_title}'\n"

    # Pending appointment hint
    clean_npc_id = npc_id.strip().lower().replace(" ", "_")
    pending_appts = [a for a in db.get_phone_appointments(session_id, status="pending") if a.get("npc_id") == clean_npc_id]
    appt_hint = ""
    if pending_appts:
        appt_loc = pending_appts[0].get("rendezvous_location", "")
        appt_hint = f"- Scheduled Meetup: You already have a confirmed plan to meet {contact_name} at: {appt_loc}.\n"

    is_ongoing = bool(history_rows)

    if is_ongoing:
        last_m = history_rows[-1]
        last_sender = "Player" if last_m.get("sender") == "player" else contact_name
        last_content = last_m.get("message", "")

        intent_directive = "Keep the casual conversation moving forward naturally. React to or answer what they just said."
        if intent == "flirt":
            intent_directive = "Tease, flirt playfully, or banter warmly in response to their previous message."
        elif intent == "meetup":
            if pending_appts:
                intent_directive = f"Enthusiastically acknowledge and confirm looking forward to the scheduled meetup at {pending_appts[0].get('rendezvous_location')}."
            else:
                intent_directive = "Suggest hanging out or meeting up soon in a casual, charming way."

        system_prompt = (
            f"You are generating {char_name}'s next text message in an ongoing mobile instant-messaging thread (like Discord, WhatsApp, or iMessage) with {contact_name} in a {scen_key} story.\n"
            f"Contact: {contact_name} (Role: {role}). Relationship: {track.capitalize()} track (Affinity: {score}).\n"
            f"Current Location: {current_loc}.\n"
            + sq_hint
            + appt_hint +
            f"Directive: {intent_directive}\n"
            "STRICT MESSENGER CONVERSATION RULES:\n"
            f"1. NO GREETINGS OR SALUTATIONS: NEVER begin with 'Hey', 'Hi', 'Hello', 'Yo', or '{contact_name}!'. In an ongoing chat, real people reply directly without re-greeting each other.\n"
            f"2. DIRECT REPLY & FLOW: Directly respond to {contact_name}'s last message: \"{last_content}\".\n"
            "   - If they asked a question (e.g. 'How about you?', 'What are you up to?'), you MUST answer the question directly from your perspective.\n"
            "   - If they confirmed or proposed meeting up, acknowledge it enthusiastically or say you're on your way.\n"
            "   - If they teased or bantered, tease or banter back in kind.\n"
            "3. KEEP IT BRIEF & REALISTIC: 1-2 short sentences maximum. Use natural texting tone with 1-2 casual emojis (e.g. 😊, 😉, ✨, 👍, 💬).\n"
            "4. NO DUPLICATION: Never repeat previous messages from the history.\n"
            "Respond with ONLY a single valid JSON object matching:\n"
            '{"message": "string"}'
        )
        user_prompt = (
            f"Conversation History:\n{history_text}\n"
            f"{contact_name}'s last text: \"{last_content}\"\n"
            f"Generate {char_name}'s direct reply (NO greeting):"
        )
    else:
        system_prompt = (
            f"You are generating {char_name}'s opening text message to {contact_name} in a {scen_key} story.\n"
            f"Contact: {contact_name} (Role: {role}). Relationship: {track.capitalize()} track (Affinity: {score}).\n"
            f"Current Location: {current_loc}.\n"
            + sq_hint
            + appt_hint +
            "Guidelines:\n"
            "- Write a single short, natural opening text message (1-2 sentences) from the player's perspective.\n"
            "- Friendly, in-character greeting suited to their role and relationship.\n"
            "- Casual texting style with fitting emojis (e.g. 💬, 😊, 👋, ✨).\n"
            "Respond with ONLY a single valid JSON object matching:\n"
            '{"message": "string"}'
        )
        user_prompt = f"Generate {char_name}'s opening message to {contact_name}:"

    try:
        result = await mechanics.system.phone.call_llm_json(system_prompt, user_prompt, temperature=0.85, is_nsfw=scenario_data.uses_nsfw_model(scen_key), use_utility=True)
        player_msg = (result.get("message") or "").strip()
        if player_msg:
            if is_ongoing:
                # Strip leading greeting if the model inadvertently included one
                first_name = contact_name.split()[0] if contact_name.split() else contact_name
                name_alt = rf"(?:{re.escape(contact_name)}|{re.escape(first_name)})"
                clean_msg = re.sub(
                    rf"^(?:hey(?:a)?|hi|hello|yo)\s*(?:{name_alt}|there)?\s*[,!.:-]*\s*",
                    "",
                    player_msg,
                    flags=re.IGNORECASE
                ).strip()
                clean_msg = re.sub(
                    rf"^{name_alt}\s*[,!.:-]+\s*",
                    "",
                    clean_msg,
                    flags=re.IGNORECASE
                ).strip()
                if len(clean_msg) >= 4:
                    player_msg = clean_msg[0].upper() + clean_msg[1:]
            return player_msg
    except Exception as e:
        log.warning(f"[phone] Failed to generate dynamic player chat message: {e}")

    # Contextual intelligent fallbacks
    if is_ongoing:
        last_m = history_rows[-1]
        last_text = last_m.get("message", "")
        last_sender = last_m.get("sender", "npc")

        if last_sender == "npc":
            last_lower = last_text.lower()
            if any(q in last_lower for q in ["how about you", "what about you", "how are you", "how's your", "how is your", "and you?"]):
                return random.choice([
                    "Just wrapping up a few things myself! Glad you're catching a breath 😊",
                    "Pretty good on my end, just taking it easy right now! ✨",
                    "Not too bad at all! Just wanted to see what you were up to 😊",
                    "Doing well! Was just hoping to hear from you ✨",
                ])
            if any(w in last_lower for w in ["meet at", "see you soon", "see you there", "why don't we meet", "office", "head over", "looking forward to seeing you"]):
                return random.choice([
                    "Sounds like a plan! I'll head over in a few minutes 😊",
                    "Awesome, see you there in a bit! ✨",
                    "Looking forward to it! On my way 👍",
                    "Perfect! See you shortly 😊",
                ])
            if any(w in last_lower for w in ["sweet", "flatter", "tease", "distract", "hard to focus", "blushing", "flirt", "😉", "😘", "❤️"]):
                return random.choice([
                    "Haha, my bad! Guess I'll have to come distract you in person then 😉",
                    "Just speaking the truth! You deserve a good distraction 😉",
                    "Can't help it when it comes to you 😊",
                    "Guilty as charged! Can't let you work too hard 😉",
                ])
            if "?" in last_text:
                return random.choice([
                    "Haha, good question! A bit of everything honestly, but I'm doing well 😊",
                    "Just taking things one step at a time today, but staying busy! ✨",
                    "Honestly, just thinking about what's coming up next 😊",
                ])
            return random.choice([
                "Glad to hear that! Keep me posted on how it goes 😊",
                "Haha, totally! Always fun chatting with you ✨",
                "That makes a lot of sense. Hope the rest of your day goes smoothly!",
                "Sounds like quite a day! Take it easy when you can 😊",
            ])
        else:
            return random.choice([
                "No rush on replying by the way, just wanted to check in! 😊",
                "Take your time with whatever you're working on! ✨",
                "Hope everything's going smoothly on your end 👍",
            ])

    if intent in ("photo_send", "send_photo"):
        photo_obj = generate_player_casual_photo(current_loc)
        return f"Here's what I'm up to right now! {photo_obj['display_text']}"
    elif intent in ("spicy_send", "send_spicy", "nsfw_send"):
        photo_obj = generate_player_spicy_photo(player_char)
        return f"Thinking of you... {photo_obj['display_text']}"
    elif intent in ("photo_ask", "ask_photo", "photo"):
        return f"Hey {contact_name}! What are you up to right now? Send me a quick photo! 😊"
    elif intent in ("spicy_ask", "ask_spicy", "nsfw_photo", "nsfw_video"):
        return f"Thinking of you... can you send me a spicy photo? 😉"
    elif intent in ("rumor", "intel_rumor", "intel"):
        return f"Hey {contact_name}, heard any interesting rumors or gossip going around today? 🕵️"
    elif intent == "meetup":
        if pending_appts:
            return f"Hey, what if we meet somewhere else instead? Can we change our spot from {pending_appts[0].get('rendezvous_location')}? 📍"
        is_romantic = str(contact.get("track", "platonic")).lower() == "romantic"
        return "Are you free later? Would you like to go out on a date with me? 🌹" if is_romantic else "Are you free right now? Want to meet up somewhere quiet to talk? 📍"
    elif intent == "flirt":
        current_day, _, _ = db.get_session_time(session_id)
        d_limits = db.get_phone_daily_limits(session_id, npc_id, current_day)
        flirt_used = d_limits.get("flirt", {}).get("used", 0)
        last_out = d_limits.get("flirt", {}).get("last_outcome", "")
        if flirt_used == 1:
            if last_out in ("success", "crit_success"):
                return random.choice([
                    "You're dangerously charming today, you know that? 😉",
                    "I couldn't help smiling at your last text... you really know how to get my attention 💕",
                    "Is it just me, or does chatting with you make my day ten times better? 😉"
                ])
            else:
                return random.choice([
                    "Haha, my bad! Let me try again with a real compliment without being clumsy 😊",
                    "Okay, that came out a little cheesy, but I genuinely wanted to say you look wonderful today ✨",
                    "Can't blame me for trying when you look that good 😉"
                ])
        elif flirt_used == 2:
            if last_out in ("success", "crit_success"):
                return random.choice([
                    "Honestly, you might be my favorite person to talk to right now ❤️",
                    "You really have a way with words... you've got me completely captivated 💕",
                    "I think you might be my favorite distraction today 😉"
                ])
            else:
                return random.choice([
                    "Alright, last try for today! Promise I'm on my best behavior now 😊",
                    "Just wanted to bring a smile to your face before the day ends ✨"
                ])
        return "Thinking of you... hope you're having a good day 😉"

    fallbacks = [
        f"Hey {contact_name}! How are things going with you? 😊",
        f"Hey, got a quick second to chat? 👋",
        f"Hope you're having a good day, {contact_name}! ✨",
        f"What are you up to right now? 💬",
    ]
    return random.choice(fallbacks)
