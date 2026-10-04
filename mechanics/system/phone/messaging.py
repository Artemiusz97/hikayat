from __future__ import annotations
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
from skill_check import resolve_check, success_chance, CheckResult

from .embeds import *

from .gossip_feed import *
from .social_graph import *

DM_REPLY_SCHEMA = """{
  "reply_text": "string, 1-3 sentences in natural texting style with casual tone/emojis",
  "affinity_delta": integer -5 to 6,
  "rendezvous_location": "string, optional meeting location name or empty string"
}"""


def get_dm_requirement(score: int, intent: str, track: str = "platonic", openness: str = "moderate") -> int:
    """Calculates skill check DC requirement based on relationship affinity bracket, intent, track, and erotic openness."""
    is_romantic = str(track or "platonic").lower() == "romantic"

    # Affinity Brackets:
    # Hostile: score < 0
    # Stranger: 0 <= score < 15
    # Acquaintance: 15 <= score < 35
    # Friend: 35 <= score < 60
    # Close Companion: 60 <= score < 80
    # Confidant / Lover: score >= 80

    if intent == "meetup":
        if score < 0:
            return 15
        elif score < 15:
            return 10
        elif score < 35:
            return 6 if is_romantic else 7
        elif score < 60:
            return 4 if is_romantic else 5
        elif score < 80:
            return 3
        else:
            return 2

    elif intent in ("intel_rumor", "intel", "rumor"):
        if score < 0:
            return 11
        elif score < 15:
            return 8
        elif score < 35:
            return 6
        elif score < 60:
            return 4
        elif score < 80:
            return 3
        else:
            return 3

    elif intent == "chat":
        if score < 0:
            return 8
        elif score < 15:
            return 6
        elif score < 35:
            return 5
        elif score < 60:
            return 4
        else:
            return 3

    elif intent == "flirt":
        if score < 0:
            return 14
        elif score < 15:
            return 9
        elif score < 35:
            return 7
        elif score < 60:
            return 4 if is_romantic else 5
        elif score < 80:
            return 3 if is_romantic else 4
        else:
            return 2 if is_romantic else 3

    elif intent in ("photo", "video"):
        if score < 0:
            return 12
        elif score < 15:
            return 8
        elif score < 35:
            return 6
        elif score < 60:
            return 4
        else:
            return 3

    elif intent in ("nsfw_photo", "nsfw_video"):
        if score < 0:
            req = 18
        elif score < 15:
            req = 14
        elif score < 35:
            req = 11
        elif score < 60:
            req = 5 if is_romantic else 8
        elif score < 80:
            req = 3 if is_romantic else 5
        else:
            req = 2 if is_romantic else 4

        op_clean = str(openness or "").lower()
        if "prude" in op_clean or "modest" in op_clean:
            req += 4
        elif "shameless" in op_clean or "lewd" in op_clean:
            req = max(1, req - 3)
        elif "bold" in op_clean or "uninhibited" in op_clean:
            req = max(1, req - 2)
        return req

    # Default / custom intent
    if score < 0:
        return 8
    elif score < 15:
        return 6
    elif score < 35:
        return 5
    elif score < 60:
        return 4
    else:
        return 3

def detect_custom_message_intent(user_message: str) -> str:
    """Classifies user's freeform text message into mechanical intents via central engine."""
    from mechanics.narrative.intent import classify_message_intent
    return classify_message_intent(user_message)

def generate_npc_photo_caption(contact: dict, intent: str = "nsfw_photo", location: str = "") -> str:
    """Fallback generator for NPC photo/video descriptions if LLM omitted the bracketed tag."""
    import random
    contact_name = contact.get("name", "Contact")
    if intent in ("video", "nsfw_video"):
        if "nsfw" in intent:
            captions = [
                f"A private, sultry 10-second video clip of {contact_name} lounging on soft bedsheets, smiling softly and running fingers through hair with a teasing glance",
                f"A short video clip of {contact_name} in relaxed silk loungewear, posing playfully in warm ambient lighting and blowing a gentle kiss to the camera",
                f"A candid video snapshot of {contact_name} catching golden hour light, spinning slowly with an alluring smile"
            ]
        else:
            captions = [
                f"A quick 5-second video clip showing {contact_name} waving cheerfully from {location or 'around town'}",
                f"A short, high-energy video snippet of {contact_name} laughing and showing off the lively surroundings",
                f"A warm video message from {contact_name} smiling brightly into the lens"
            ]
        return random.choice(captions)

    if intent == "photo":
        captions = [
            f"A bright and sunny selfie of {contact_name} at {location or 'a quiet spot'}, smiling warmly with a refreshing drink in hand",
            f"A casual over-the-shoulder snapshot of {contact_name} enjoying the fresh air and relaxed downtime",
            f"A candid snapshot of {contact_name} looking directly into the lens with a happy, radiant smile"
        ]
        return random.choice(captions)

    # nsfw_photo
    captions = [
        f"A sultry bedroom mirror selfie of {contact_name} in an oversized button-down shirt unbuttoned halfway and slipping off bare shoulders",
        f"A candid bed snapshot of {contact_name} in a cropped baby tee pulled up playfully and relaxed loungewear slung low on the hips",
        f"A steamy bathroom selfie of {contact_name} with damp hair wrapped in a soft towel, casting an alluring glance into the camera",
        f"A warm-lit bedside photo of {contact_name} in an unzipped oversized hoodie teasing bare skin underneath, resting on one elbow",
        f"A daring top-down bed selfie of {contact_name} reclining completely nude with white sheets pulled tantalizingly low along the hips",
        f"A steamy mirror selfie of {contact_name} freshly stepped out of the shower, holding up a dropped towel with a flirtatious wink",
        f"A playful photo of {contact_name} in an off-the-shoulder knit sweater falling over bare thighs, smiling with bedroom eyes",
        f"An alluring silhouette snapshot of {contact_name} bathed in soft moonlight by the window, hands teasingly tracing bare collarbones",
    ]
    return random.choice(captions)

def generate_player_photo_caption(char: dict, intent: str = "nsfw_photo", location: str = "") -> str:
    """Generate dynamic, randomized, and descriptive photo captions for the player."""
    import random
    if intent == "photo":
        activities = [
            f"taking a break and relaxing at {location or 'a quiet spot'}, smiling warmly into the camera",
            f"enjoying the fresh air around {location or 'town'}, catching natural golden lighting",
            f"holding up a warm drink with a relaxed, happy expression",
            f"a candid over-the-shoulder snapshot with a playful, easy grin",
            f"sitting comfortably by a window enjoying peaceful downtime",
            f"walking through {location or 'the area'}, looking directly into the lens with a soft smile",
            f"leaning casually against a railing under the open sky, hair ruffled slightly by the breeze",
        ]
        return random.choice(activities)

    # nsfw_photo
    gender = (char.get("gender") or "neutral").lower() if char else "neutral"
    if "f" in gender:
        attire_poses = [
            "A bedroom mirror selfie wearing an oversized button-down shirt unbuttoned halfway and slipping off bare shoulders",
            "Lounging on the bed in a cropped tank top pulled up teasingly and unbuttoned low-rise denim shorts",
            "Leaning against the doorframe in an off-the-shoulder oversized knit sweater draped over bare thighs",
            "A candid bed selfie wearing an unzipped oversized hoodie with nothing underneath, teasing bare collarbones and hips",
            "A steamy bathroom mirror selfie with wet hair wrapped in a towel and a teasing glimpse of bare collarbones and hips",
            "Laying back across tangled bedsheets in an unbuttoned silk pajama top slipping open, biting lip playfully",
            "A steamy vanity mirror selfie in a damp, form-fitting white tee clinging softly to skin with a playful wink",
            "Laying face-down across plush pillows with bare back and hips arched gracefully, looking back with a sultry bedroom gaze",
            "A daring high-angle bed selfie lying completely nude with tangled silk sheets pulled teasingly low across hips",
            "Fresh out of the shower with towel dropped to the floor, posing by the steamy vanity with wet hair and a flirtatious smirk",
            "Kneeling on the mattress in an unfastened satin robe falling open off bare shoulders and hips, blowing a gentle kiss",
        ]
    elif "m" in gender:
        attire_poses = [
            "A bold mirror selfie showing off a defined, toned physique in low-slung boxer-briefs, smiling playfully into the camera",
            "Laying relaxed across the bed with an unbuttoned linen shirt exposing chest and abs, giving a teasing wink",
            "Fresh out of the shower with damp hair, a dark towel slung dangerously low on the hips, smirking confidently at the camera",
            "Leaning back against the headboard in relaxed sweatpants sitting low on the waist, giving a sultry look",
            "A warm-lit mirror selfie highlighting broad shoulders and bare torso with a confident, flirtatious grin",
            "A candid high-angle shot lounging on the couch in comfortable loungewear, gaze locked intensely with the lens",
            "Unbuttoning a fitted dress shirt halfway in front of the mirror, glancing sideways with an alluring smirk",
            "Resting on one elbow across the bed, bare shoulders and chest catching soft ambient bedroom lighting",
            "A daring bed selfie reclining completely bare-chested with tangled sheets pulled low across the waist, giving an intense stare",
            "Stepping out of the bathroom with damp hair and a towel slung over broad shoulders, offering a teasing, confident grin",
            "Leaning against the vanity with unfastened sleep pants riding low, torso highlighted by dramatic ambient mood lighting",
        ]
    else:
        attire_poses = [
            "An alluring mirror selfie showing bare skin and a teasing, sultry glance under soft ambient lighting",
            "Relaxing across tangled sheets in loosely tied silk loungewear, smirking playfully at the camera",
            "A steamy post-shower mirror selfie wrapped in a plush towel, hair still damp, offering a flirtatious wink",
            "Lounging comfortably in soft low-slung loungewear, collarbones and torso bathed in warm evening light",
            "A sultry close-up selfie teasing curves and bare shoulders with an intense, captivating smile",
            "Leaning against the vanity in an unbuttoned nightshirt, casting an alluring gaze into the camera",
            "A daring high-angle bed selfie lounging across tangled sheets with bare skin bathed in soft golden ambient lighting",
            "Fresh out of the shower with damp hair and a dropped towel, casting an alluring, flirtatious gaze into the mirror",
            "Posing gracefully across plush velvet cushions in an unfastened silk robe falling open off the shoulders with a sultry smirk",
        ]
    return random.choice(attire_poses)

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
        result = await mechanics.system.phone.call_llm_json(system_prompt, user_prompt, temperature=0.85, is_nsfw=scenario_data.is_nsfw_scenario(scen_key), use_utility=True)
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

    if intent == "meetup":
        is_romantic = str(contact.get("track", "platonic")).lower() == "romantic"
        return "Are you free later? Would you like to go out on a date with me? 🌹" if is_romantic else "Are you free right now? Want to meet up somewhere quiet to talk? 📍"
    elif intent == "flirt":
        return "Thinking of you... hope you're having a good day 😉"

    fallbacks = [
        f"Hey {contact_name}! How are things going with you? 😊",
        f"Hey, got a quick second to chat? 👋",
        f"Hope you're having a good day, {contact_name}! ✨",
        f"What are you up to right now? 💬",
    ]
    return random.choice(fallbacks)

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
    traits = ", ".join(contact.get("unlocked_traits") or basic.get("traits") or ["Observant"])
    current_loc = session.get("current_location", "Local Area")

    msg_lower = (user_message or "").lower()
    is_intimate = any(k in msg_lower for k in ["intimate", "spicy", "nsfw", "nude", "nudes", "naked", "sexy", "lewd", "lingerie", "boudoir", "underwear", "undies"])
    is_video = any(k in msg_lower for k in ["video", "vid", "clip", "recording", "footage", "film"])
    is_photo = any(k in msg_lower for k in ["photo", "pic", "picture", "selfie", "snapshot", "image", "look like"])

    # Check if there is an active pending appointment with this contact
    clean_npc_id = npc_id.strip().lower().replace(" ", "_")
    pending_appts = [a for a in db.get_phone_appointments(session_id, status="pending") if a.get("npc_id") == clean_npc_id]
    existing_appointment = pending_appts[0] if pending_appts else None

    # Auto-classify intent for custom or generic chat messages
    if intent in ("custom", "chat"):
        detected = detect_custom_message_intent(user_message)
        if detected != "custom":
            # If an appointment is ALREADY pending and detected intent is "meetup",
            # do not convert custom chat into a new meetup unless player explicitly asks to reschedule/change location!
            if detected == "meetup" and existing_appointment:
                is_reschedule = any(w in msg_lower for w in ["change location", "change place", "meet somewhere else", "different place", "different spot", "reschedule", "instead of"])
                if not is_reschedule:
                    detected = "custom"
            if detected != "custom":
                intent = detected

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

    req = get_dm_requirement(score, intent, track=track, openness=erotic_open)
    user_settings = db.get_settings(player_char.get("user_id", 0))
    check_mode = user_settings.get("debug_check_mode", "off") if user_settings else "off"
    check_result = resolve_check(stat_val, req, luck=player_char.get("luk", 3), check_mode=check_mode)

    is_prude = any(k in str(erotic_open).lower() for k in ("prude", "modest"))
    is_shameless = any(k in str(erotic_open).lower() for k in ("shameless", "lewd"))
    is_bold = any(k in str(erotic_open).lower() for k in ("bold", "uninhibited"))

    # Strict prude barrier on NSFW media requests: requires 70+ affinity AND romantic track
    if is_prude and intent in ("nsfw_photo", "nsfw_video") and (score < 70 or not is_romantic):
        check_result = CheckResult(
            chance=0,
            roll=1.0,
            tier="fail",
            tier_label="Failure",
            succeeded=False
        )

    # Fetch recent message history
    history_rows = db.get_phone_messages(session_id, npc_id, limit=6)
    history_text = "\n".join(f"{'Player' if r['sender'] == 'player' else contact_name}: {r['message']}" for r in history_rows)

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
            if sib_track.lower() == "romantic" or sib_score >= 30:
                lines.append(f"- SIBLING RELATIONSHIP NOTE: You are aware the player is very close to / romantically involved with your sibling ({sibling_name}). You may tease them or show protective/curious interest!")
            elif sib_score < 0:
                lines.append(f"- SIBLING RELATIONSHIP NOTE: You know the player has bad blood or tension with your sibling ({sibling_name}).")

            if intent == "meetup" and grade in ("Freshman", "Sophomore"):
                lines.append("- Meetup Note: If you agree to meet up, you might playfully mention hoping your older sibling doesn't catch you.")

        if lines:
            family_and_grade_hint = "\nFAMILY & GRADE DYNAMICS:\n" + "\n".join(lines) + "\n"

    # --- Meetup location grounding: build a list of known public locations ---
    known_locations: list[dict] = []
    meetup_location_hint = ""
    is_reschedule_request = any(w in (user_message or "").lower() for w in ["change location", "change place", "meet somewhere else", "different place", "different spot", "reschedule", "instead of"])
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
            all_locs = db.get_session_locations(session_id)
            # Filter to public/semi-public places (exclude bedrooms, private rooms, storage etc.)
            _PRIVATE_KEYWORDS = {"bedroom", "bathroom", "shower", "your room", "storage", "closet", "staff only", "breakroom", "locker room"}

            # Query active quest and bounty waypoints to exclude locations occupied by active objectives
            active_wps = db.get_all_session_active_waypoints(session_id)
            from mechanics.world.waypoints import check_location_matches_waypoint
            quest_occupied_locs = [wp.get("target_location", "") for wp in active_wps if wp.get("target_location")]

            public_locs = []
            for loc in all_locs:
                loc_label = " ".join(filter(None, [loc.get("zone_name", ""), loc.get("primary_name", ""), loc.get("sub_name", "")])).lower()
                if any(pk in loc_label for pk in _PRIVATE_KEYWORDS):
                    continue
                full_loc = f"{loc.get('zone_name', '')} ➔ {loc.get('primary_name', '')} ➔ {loc.get('sub_name', '')}"
                prim_loc = f"{loc.get('zone_name', '')} -> {loc.get('primary_name', '')}"
                is_quest_loc = any(
                    check_location_matches_waypoint(full_loc, ql) or check_location_matches_waypoint(prim_loc, ql) or check_location_matches_waypoint(ql, full_loc)
                    for ql in quest_occupied_locs
                )
                if not is_quest_loc:
                    public_locs.append(loc)

            # Fallback: if all public locations happen to be occupied by quests, allow non-private locations
            if not public_locs:
                public_locs = [
                    loc for loc in all_locs
                    if not any(pk in " ".join(filter(None, [loc.get("zone_name", ""), loc.get("primary_name", ""), loc.get("sub_name", "")])).lower() for pk in _PRIVATE_KEYWORDS)
                ]
            known_locations = public_locs
            if public_locs:
                # Build a compact readable list (primary + sub_name, deduplicated)
                seen = set()
                loc_lines = []
                for loc in public_locs:
                    primary = loc.get("primary_name", "")
                    sub = loc.get("sub_name", "")
                    label = f"{primary}" + (f" ({sub})" if sub else "")
                    if label not in seen:
                        seen.add(label)
                        loc_lines.append(label)
                meet_term = "Date" if is_romantic else "Meetup"
                meetup_location_hint = (
                    f"- IMPORTANT — {meet_term} Location: You MUST suggest one of these REAL known locations from the world map. "
                    f"Do NOT invent fictional place names. Choose one that fits your personality and relationship:\n"
                    + "\n".join(f"  • {l}" for l in loc_lines[:30])
                    + "\n- Set rendezvous_location to the EXACT primary name (or 'Primary (Sub)') from the list above.\n"
                )

    # Dynamic Intent Specific Prompt Instructions
    if intent == "meetup":
        if existing_appointment and not is_reschedule_request:
            existing_loc = existing_appointment["rendezvous_location"]
            intent_guidelines = (
                f"- Intent: Player is talking about or confirming your upcoming meetup.\n"
                f"- If check Succeeded / Critical Success: Happy, warm confirmation that you'll see them at '{existing_loc}'.\n"
                f"- If check Failed / Critical Failure: Mention you might be a little delayed or ask for a rain check.\n"
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
        intent_guidelines = (
            "- Intent: Flirting and teasing banter.\n"
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
    elif intent == "photo":
        intent_guidelines = (
            "- Intent: Exchanging everyday photos / selfies.\n"
            "- CRITICAL CREATIVITY & VARIETY MANDATE:\n"
            "  * If check Succeeded / Critical Success: You MUST invent an entirely ORIGINAL, VIVID bracketed photo description: '[Attached Photo: ...]'.\n"
            "  * ANTI-REPETITION: Never repeat settings or activities from history. Vary the activity, outfit, lighting, and expressions (e.g. sipping a beverage at a sunlit cafe, holding up a cute find, sitting on bedroom floor with study notes, posing outdoors under trees, laughing candidly at something off-camera).\n"
            "  * If check Failed / Critical Failure: Say your camera is glitching, you look a mess, or politely decline.\n"
        )
    elif intent == "nsfw_photo":
        intent_guidelines = (
            "- Intent: NSFW intimate photo swap. Player sent an intimate selfie.\n"
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
        + intent_guidelines
        + sq_hint
        + feed_hint
        + family_and_grade_hint
        + meetup_location_hint
        + f"Respond with ONLY a single valid JSON object matching the schema:\n{dm_schema}"
    )

    user_prompt = (
        f"Conversation History:\n{history_text}\n"
        f"Player ({player_char.get('name', 'Hero')}): {user_message}\n"
        f"Intent: {intent}\n"
        f"Generate {contact_name}'s text reply JSON:"
    )

    call_temp = 0.9 if intent in ("photo", "nsfw_photo", "video", "nsfw_video", "flirt") else 0.8
    result = await mechanics.system.phone.call_llm_json(system_prompt, user_prompt, temperature=call_temp, is_nsfw=scenario_data.is_nsfw_scenario(scen_key), use_utility=True)
    reply_text = result.get("reply_text") or f"Hey {player_char.get('name', 'there')}! Got your message, let's catch up soon."

    # Safeguard: if check succeeded and intent is a photo/video intent, ensure bracketed media description is attached
    if check_result.succeeded and intent in ("nsfw_photo", "nsfw_video", "photo", "video"):
        has_attachment = any(tag in reply_text for tag in [
            "[Attached Intimate Video:", "[Attached Video:",
            "[Attached Intimate Photo:", "[Attached Photo:"
        ])
        if not has_attachment:
            fallback_caption = generate_npc_photo_caption(contact, intent=intent, location=current_loc)
            if intent == "nsfw_video":
                reply_text += f"\n[Attached Intimate Video: {fallback_caption}]"
            elif intent == "video":
                reply_text += f"\n[Attached Video: {fallback_caption}]"
            elif intent == "nsfw_photo":
                reply_text += f"\n[Attached Intimate Photo: {fallback_caption}]"
            else:
                reply_text += f"\n[Attached Photo: {fallback_caption}]"

    # Shameless / Lewd bonus media drop (chance for second media attachment unprompted)
    if check_result.succeeded and is_shameless and intent == "nsfw_photo":
        if "[Attached Intimate Video:" not in reply_text and "[Attached Bonus Intimate Video:" not in reply_text:
            import hashlib
            seed_bonus = (contact_name + str(session_id) + str(int(time.time()))).encode("utf-8")
            if (int(hashlib.md5(seed_bonus).hexdigest(), 16) % 100) < 50:
                bonus_caption = generate_npc_photo_caption(contact, intent="nsfw_video", location=current_loc)
                reply_text += f"\n[Attached Bonus Intimate Video: {bonus_caption}]"

    # Enforce deterministic bounds based on check tier and intent
    if check_result.tier == "crit_success":
        if intent == "nsfw_photo":
            affinity_delta = max(4, min(6, int(result.get("affinity_delta", 4))))
        else:
            affinity_delta = max(3, min(5, int(result.get("affinity_delta", 3))))
        rendezvous = result.get("rendezvous_location", "") if intent == "meetup" else ""
    elif check_result.tier == "success":
        if intent == "nsfw_photo":
            affinity_delta = max(2, min(4, int(result.get("affinity_delta", 2))))
        else:
            affinity_delta = max(1, min(3, int(result.get("affinity_delta", 1))))
        rendezvous = result.get("rendezvous_location", "") if intent == "meetup" else ""
    elif check_result.tier == "fail":
        if intent == "nsfw_photo":
            # Guaranteed negative consequence on failing intimate photo swap
            raw_delta = int(result.get("affinity_delta", -1))
            affinity_delta = min(-1, max(-2, raw_delta if raw_delta < 0 else -1))
        else:
            affinity_delta = 0
        rendezvous = ""
    else:  # crit_fail
        if intent == "nsfw_photo":
            # Guaranteed strong penalty on critical failure
            raw_delta = int(result.get("affinity_delta", -3))
            affinity_delta = min(-3, max(-5, raw_delta if raw_delta < 0 else -3))
        else:
            raw_delta = int(result.get("affinity_delta", -2))
            affinity_delta = min(-1, max(-3, raw_delta if raw_delta < 0 else -2))
        rendezvous = ""

    # --- Rendezvous location validation & seeding (STRICTLY for meetup intent) ---
    resolved_rendezvous = rendezvous if intent == "meetup" else ""
    if intent == "meetup" and rendezvous:
        if existing_appointment and not is_reschedule_request:
            resolved_rendezvous = existing_appointment["rendezvous_location"]
        elif known_locations:
            rendezvous_lower = rendezvous.lower().strip()
            best_match = None
            best_score_val = 0
            for loc in known_locations:
                primary = loc.get("primary_name", "")
                sub = loc.get("sub_name", "")
                zone = loc.get("zone_name", "")
                candidates = [primary.lower(), sub.lower(), f"{primary} {sub}".lower(), f"{zone} {primary}".lower()]
                for cand in candidates:
                    if not cand.strip():
                        continue
                    # Token overlap score
                    r_tokens = set(rendezvous_lower.split())
                    c_tokens = set(cand.split())
                    overlap = len(r_tokens & c_tokens)
                    # Also check substring containment
                    sub_match = rendezvous_lower in cand or cand in rendezvous_lower
                    score_val = overlap * 2 + (3 if sub_match else 0)
                    if score_val > best_score_val:
                        best_score_val = score_val
                        best_match = loc

            if best_match and best_score_val >= 2:
                # Resolve to canonical full location path
                primary = best_match.get("primary_name", "")
                sub = best_match.get("sub_name", "")
                zone = best_match.get("zone_name", "")
                resolved_rendezvous = f"{zone} ➔ {primary}" + (f" ➔ {sub}" if sub else "")
            else:
                # No match — seed the invented location as a new dynamic discoverable location
                # so the player can actually travel there via the world map
                import re as _re
                # Derive zone from current_loc if possible
                seed_zone = current_loc.split("➔")[0].strip() if "➔" in current_loc else (
                    known_locations[0].get("zone_name", "Local Area") if known_locations else "Local Area"
                )
                seed_primary = rendezvous.strip()
                seed_sub = "Meeting Spot"
                seed_loc_id = _re.sub(r"[^a-z0-9_]", "_", f"{seed_zone}_{seed_primary}_{seed_sub}".lower())[:80]
                db.save_session_location(
                    session_id=session_id,
                    location_id=seed_loc_id,
                    zone_name=seed_zone,
                    primary_name=seed_primary,
                    sub_name=seed_sub,
                    atmosphere=f"A quiet meeting spot suggested by {contact_name}.",
                    is_dynamic=1
                )
                resolved_rendezvous = f"{seed_zone} ➔ {seed_primary} ➔ {seed_sub}"
                log.info(f"[phone] Seeded new dynamic meetup location: {resolved_rendezvous} for session {session_id}")

    # Save messages to SQLite
    db.save_phone_message(session_id, npc_id, sender="player", message=user_message, intent=intent)
    db.save_phone_message(session_id, npc_id, sender="npc", message=reply_text, intent=intent)

    # Persist meetup appointment so the NPC appears at the rendezvous location
    if resolved_rendezvous and intent == "meetup":
        # Only save if there is no active appointment for this contact or the location has changed
        if not existing_appointment or existing_appointment.get("rendezvous_location") != resolved_rendezvous:
            db.save_phone_appointment(session_id, npc_id, contact_name, resolved_rendezvous)
            # Update contact known location so spatial queries and world tracker recognize where they are situated
            existing_basic = dict(contact.get("basic_info") or {})
            existing_basic["location"] = resolved_rendezvous
            db.upsert_contact(
                session_id=session_id,
                character_id=player_char.get("id", 0),
                npc_id=npc_id,
                name=contact_name,
                basic_info=existing_basic,
                track=track
            )
            log.info(f"[phone] Appointment saved: {contact_name} @ {resolved_rendezvous} for session {session_id}")

    # Update affinity score — guard against ineligible NPCs (teachers, parents, store clerks) slipping through
    if affinity_delta != 0:
        from mechanics.social.relationships import is_contact_eligible
        if is_contact_eligible(name=contact_name, role=role, scenario=scen_key):
            new_score = max(-100, min(100, score + affinity_delta))
            db.update_contact_score(session_id, npc_id, new_score, character_id=player_char.get("id", 0))
        else:
            log.info(f"[phone] Skipping affinity update for ineligible contact '{contact_name}' (role: {role}).")


    # Automatically create Digital Media Item in player inventory if a photo/video was received
    digital_item_id = None
    media_type_created = None
    if check_result.succeeded:
        from mechanics.combat.items import create_digital_media_item
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
        elif intent in ("nsfw_photo", "nsfw_video"):
            media_type = intent
            media_caption = reply_text
        elif intent in ("photo", "video"):
            media_type = intent
            media_caption = reply_text

        if media_type and media_caption:
            p_uid = player_char.get("user_id") or session.get("user_id") or session.get("owner_id")
            if p_uid:
                digital_item_id = create_digital_media_item(
                    user_id=p_uid,
                    contact_name=contact_name,
                    media_type=media_type,
                    caption=media_caption,
                    tags=["misc", "digital"]
                )
                media_type_created = media_type

    return {
        "reply_text": reply_text,
        "affinity_delta": affinity_delta,
        "rendezvous_location": resolved_rendezvous,
        "is_romantic": is_romantic,
        "intent": intent,
        "new_score": max(-100, min(100, score + affinity_delta)),
        "digital_item_id": digital_item_id,
        "media_type_created": media_type_created,
        "check_result": {
            "stat": stat_name,
            "chance": check_result.chance,
            "tier": check_result.tier,
            "tier_label": check_result.tier_label,
            "succeeded": check_result.succeeded
        }
    }

