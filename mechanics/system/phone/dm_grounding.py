from __future__ import annotations
import re
import logging
import db

log = logging.getLogger("hikayat.phone")


def get_dm_requirement(
    score: int,
    intent: str,
    track: str = "platonic",
    openness: str = "moderate",
    traits: list = None,
    attempt_num: int = 1,
    prev_succeeded: bool = False,
    relocation_num: int = 0,
    is_player_sending: bool = False
) -> int:
    """Calculates skill check DC requirement based on affinity bracket, intent, track, traits, and progression."""
    is_romantic = str(track or "platonic").lower() == "romantic"
    traits_clean = [str(t).lower() for t in (traits or [])]

    # Affinity Brackets:
    # Hostile: score < 0
    # Stranger: 0 <= score < 15
    # Acquaintance: 15 <= score < 35
    # Friend: 35 <= score < 60
    # Close Companion: 60 <= score < 80
    # Confidant / Lover: score >= 80

    if intent == "meetup":
        if score < 0:
            req = 15
        elif score < 15:
            req = 10
        elif score < 35:
            req = 6 if is_romantic else 7
        elif score < 60:
            req = 4 if is_romantic else 5
        elif score < 80:
            req = 3
        else:
            req = 2

        # Escalating difficulty on location relocation requests
        if relocation_num == 1:
            req += 3
        elif relocation_num >= 2:
            req += 6

        # Personality trait modifiers on meetup
        if any(t in traits_clean for t in ("flexible", "adventurous", "easygoing", "relaxed")):
            req = max(1, req - 1)
        elif any(t in traits_clean for t in ("rigid", "busy", "disciplined", "cautious", "strict")):
            req += 2
        return max(1, req)

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
            req = 14
        elif score < 15:
            req = 10
        elif score < 35:
            req = 7
        elif score < 60:
            req = 4 if is_romantic else 5
        elif score < 80:
            req = 3 if is_romantic else 4
        else:
            req = 2 if is_romantic else 3

        # Trait modifiers on flirt DC
        if any(t in traits_clean for t in ("flirtatious", "playful", "romantic", "bold", "charming")):
            req = max(1, req - 2)
        elif any(t in traits_clean for t in ("shy", "tsundere", "reserved", "serious", "timid")):
            req += 2
        elif any(t in traits_clean for t in ("prude", "strict", "cold", "distant")):
            req += 3

        # Multi-attempt progression modifiers
        if attempt_num == 2:
            req = max(1, req - 1) if prev_succeeded else req + 2
        elif attempt_num >= 3:
            req = max(1, req - 1) if prev_succeeded else req + 3
        return max(1, req)

    elif intent in ("photo", "video", "photo_ask"):
        if score < 0:
            req = 11
        elif score < 15:
            req = 8
        elif score < 35:
            req = 6
        elif score < 60:
            req = 4
        else:
            req = 3

        if any(t in traits_clean for t in ("outgoing", "popular", "confident", "vain")):
            req = max(1, req - 2)
        elif any(t in traits_clean for t in ("shy", "private", "camera-shy", "reserved")):
            req += 2
        return max(1, req)

    elif intent == "photo_send":
        # Evaluating casual media sent by player
        if score < 15:
            return 5
        elif score < 60:
            return 3
        return 2

    elif intent in ("nsfw_photo", "nsfw_video", "spicy_ask"):
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

    elif intent in ("spicy_send", "nsfw_send"):
        # Evaluating unsolicited intimate media sent by player
        if score < 35:
            req = 11
        elif score < 60:
            req = 6 if is_romantic else 8
        else:
            req = 3 if is_romantic else 5

        op_clean = str(openness or "").lower()
        if "prude" in op_clean or "modest" in op_clean:
            req += 5
        elif "shameless" in op_clean or "lewd" in op_clean:
            req = max(1, req - 4)
        elif "bold" in op_clean or "uninhibited" in op_clean:
            req = max(1, req - 2)
        return max(1, req)

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


def is_meetup_reschedule_request(message: str) -> bool:
    """Detects if user message is requesting to reschedule, change, or relocate a meetup."""
    if not message:
        return False
    msg_low = message.strip().lower()

    # Direct keywords/phrases
    reschedule_patterns = [
        r"\b(?:reschedule|change\s+the\s+(?:time|date|spot|location|place)|different\s+(?:time|date|spot|location|place))\b",
        r"\b(?:move\s+(?:it|our\s+meetup|our\s+date)\s+to|change\s+plans|somewhere\s+else|another\s+place)\b",
        r"\b(?:can\s+we\s+meet\s+at|what\s+if\s+we\s+meet\s+at|how\s+about\s+(?:meeting\s+at|we\s+go\s+to|the))\b",
        r"\b(?:can\s+we\s+change|switch\s+to|switch\s+the\s+spot|change\s+our\s+spot)\b",
        r"\b(?:instead|rather\s+than|meet\s+somewhere\s+else)\b",
        r"\b(?:can\s+we|could\s+we|what\s+if\s+we)\s+(?:meet|go)\s+somewhere\b",
        r"\bhow\s+about\s+(?:the\s+)?[a-z0-9_\-\s]+"
    ]
    for pattern in reschedule_patterns:
        if re.search(pattern, msg_low):
            return True

    # Check for question/proposal offering an alternate place: "What about the library?", "Let's go to the cafe instead"
    if ("instead" in msg_low or "what about" in msg_low or "how about" in msg_low) and any(
        loc_term in msg_low for loc_term in [
            "cafe", "café", "library", "park", "garden", "rooftop", "diner", "plaza", "gym",
            "fountain", "hall", "lounge", "shop", "bar", "station", "courtyard", "arcade"
        ]
    ):
        return True

    # "Meet me at [X]" or "Let's meet at [X]"
    if re.search(r"\bmeet\s+(?:me\s+)?(?:at|in)\s+[a-z0-9_\-\s]+", msg_low):
        return True

    return False


def is_meetup_confirmation_message(message: str) -> bool:
    """Detects if user message is agreeing to or confirming a proposed meetup/location."""
    if not message:
        return False
    msg_low = message.strip().lower()
    confirm_phrases = [
        "sounds nice", "sounds good", "sounds great", "sounds perfect", "sounds fun",
        "deal", "see you there", "see ya there", "works for me", "let's do it",
        "let's do that", "sure thing", "perfect", "i'll be there", "on my way",
        "agreed", "that works", "see you then", "alright see you", "ok see you"
    ]
    return any(re.search(r"\b" + re.escape(p) + r"\b", msg_low) for p in confirm_phrases)


def resolve_rendezvous_location(
    session_id: int,
    contact_name: str,
    current_loc: str,
    rendezvous: str,
    reply_text: str,
    known_locations: list,
    existing_appointment: dict | None,
    is_reschedule_request: bool,
    intent: str,
    check_succeeded: bool,
    user_message: str = "",
    history_rows: list = None
) -> tuple[str, str]:
    """
    Validates, matches against known locations, or dynamically seeds an in-world rendezvous location.
    Returns (resolved_rendezvous, intent).
    """
    # Fallback: If meetup intent and check succeeded but rendezvous was left blank, check if reply_text named a known location
    if intent == "meetup" and not rendezvous and check_succeeded and known_locations:
        for loc in known_locations:
            prim = loc.get("primary_name", "")
            sub = loc.get("sub_name", "")
            if prim and len(prim) > 3 and prim.lower() in reply_text.lower():
                rendezvous = prim
                break
            if sub and len(sub) > 3 and sub.lower() in reply_text.lower():
                rendezvous = sub
                break

    # Follow-up confirmation detection: player confirms an agreed meetup proposed by contact
    if intent in ("custom", "chat") and is_meetup_confirmation_message(user_message) and history_rows:
        last_contact_msg = next((r["message"] for r in reversed(history_rows) if r.get("sender") == "npc"), "")
        if last_contact_msg:
            if not known_locations:
                all_locs = db.get_session_locations(session_id)
                known_locations = [
                    loc for loc in all_locs
                    if not any(pk in " ".join(filter(None, [loc.get("zone_name", ""), loc.get("primary_name", ""), loc.get("sub_name", "")])).lower() for pk in {"bedroom", "bathroom", "shower", "storage", "closet"})
                ]
            for loc in known_locations:
                prim = loc.get("primary_name", "")
                sub = loc.get("sub_name", "")
                if (prim and len(prim) > 3 and prim.lower() in last_contact_msg.lower()) or (sub and len(sub) > 3 and sub.lower() in last_contact_msg.lower()):
                    zone = loc.get("zone_name", "")
                    rendezvous = f"{zone} ➔ {prim}" + (f" ➔ {sub}" if sub else "")
                    intent = "meetup"
                    break

    # Strictly for meetup intent
    resolved_rendezvous = rendezvous if intent == "meetup" else ""
    if intent == "meetup":
        if existing_appointment and not is_reschedule_request:
            resolved_rendezvous = existing_appointment["rendezvous_location"]
        elif rendezvous and known_locations:
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
                    r_tokens = set(rendezvous_lower.split())
                    c_tokens = set(cand.split())
                    overlap = len(r_tokens & c_tokens)
                    sub_match = rendezvous_lower in cand or cand in rendezvous_lower
                    score_val = overlap * 2 + (3 if sub_match else 0)
                    if score_val > best_score_val:
                        best_score_val = score_val
                        best_match = loc

            if best_match and best_score_val >= 2:
                primary = best_match.get("primary_name", "")
                sub = best_match.get("sub_name", "")
                zone = best_match.get("zone_name", "")
                resolved_rendezvous = f"{zone} ➔ {primary}" + (f" ➔ {sub}" if sub else "")
            else:
                seed_zone = current_loc.split("➔")[0].strip() if "➔" in current_loc else (
                    known_locations[0].get("zone_name", "Local Area") if known_locations else "Local Area"
                )
                seed_primary = rendezvous.strip()
                seed_sub = "Meeting Spot"
                seed_loc_id = re.sub(r"[^a-z0-9_]", "_", f"{seed_zone}_{seed_primary}_{seed_sub}".lower())[:80]
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

    return resolved_rendezvous, intent
