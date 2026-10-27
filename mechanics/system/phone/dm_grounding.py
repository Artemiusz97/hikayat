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


def _get_public_world_node_hierarchy(session_id: int, query_str: str) -> str:
    """Attempts to snap a freeform location string to a non-private (or Love Hotel), non-hidden canonical world_node."""
    if not session_id or not query_str:
        return ""
    try:
        from mechanics.world.locations.pathfinding import format_node_hierarchy, is_node_hidden
        nid = db.resolve_node_id_from_location(session_id, query_str)
        if nid:
            node = db.get_world_node(session_id, nid)
            if node and not is_node_hidden(node):
                priv = str(node.get("privacy_level") or node.get("privacy") or "public").lower()
                if priv != "private" or "love_hotel" in str(node.get("node_id") or "").lower():
                    return format_node_hierarchy(session_id, nid)
        q_low = query_str.lower().strip()
        for wn in (db.get_session_world_nodes(session_id) or []):
            priv = str(wn.get("privacy_level") or wn.get("privacy") or "public").lower()
            wn_id = str(wn.get("node_id") or "").lower()
            if (priv == "private" and "love_hotel" not in wn_id) or is_node_hidden(wn):
                continue
            wn_name = str(wn.get("name") or "").strip()
            if wn_name and len(wn_name) > 3 and (wn_name.lower() in q_low or q_low in wn_name.lower()):
                return format_node_hierarchy(session_id, wn["node_id"])
    except Exception:
        pass
    return ""


_MEETUP_EXCLUDED_KEYWORDS = {
    "bedroom", "bathroom", "restroom", "shower", "your room",
    "staff only", "teachers' staff room", "faculty", "breakroom",
    "locker room", "infirmary", "velvet basement",
}


def is_bold_meetup_contact(contact: dict | None, openness: str = "", traits: list | None = None) -> bool:
    """Returns True if an NPC has bold, uninhibited, shameless, or hedonistic traits/openness."""
    c = contact or {}
    app = c.get("appearance") if isinstance(c.get("appearance"), dict) else {}
    basic = c.get("basic_info") if isinstance(c.get("basic_info"), dict) else {}
    op = str(openness or app.get("erotic_openness") or app.get("openness") or c.get("openness") or "").lower()
    tr_list = traits if traits is not None else (c.get("unlocked_traits") or c.get("traits") or [])
    blob = " ".join([
        op,
        " ".join(str(t) for t in (tr_list or [])),
        str(basic.get("clique") or c.get("clique") or ""),
        str(basic.get("personality_summary") or c.get("personality_summary") or ""),
    ]).lower()
    return any(
        kw in blob
        for kw in ("bold", "uninhibited", "shameless", "lewd", "hedon", "flirtatious", "seductive", "adventurous", "rebel")
    )


def select_npc_preferred_meetup_venue(
    session_id: int,
    contact: dict | None,
    scen_key: str,
    *,
    current_day: int = 1,
    current_minute: int = 960,
    openness: str = "",
    traits: list | None = None,
    seed_salt: str = "",
) -> str:
    """
    Deterministically selects an accessible meetup location for an NPC.
    In NSFW scenarios, bold / uninhibited NPCs have a ~65% bias toward `is_discreet` spots
    (or `Mirage Boutique Love Hotel` / `Neon Pulse Nightclub` during evening hours >= 18:00).
    """
    import hashlib
    import scenario_data
    from mechanics.world.locations.pathfinding import format_node_hierarchy, is_node_hidden
    from mechanics.world.world_schedule import evaluate_world_schedule_node_access

    if not session_id:
        return ""
    is_nsfw = scenario_data.is_nsfw_scenario(scen_key)
    is_bold = is_bold_meetup_contact(contact, openness=openness, traits=traits)
    safe_min = int(current_minute or 0) % 1440
    is_evening = safe_min >= 1080 or safe_min < 120

    discreet_pool: list[str] = []
    regular_pool: list[str] = []

    nodes = db.get_session_world_nodes(session_id) or []
    node_by_id = {n["node_id"]: n for n in nodes if n.get("node_id")}

    for wn in nodes:
        nid = str(wn.get("node_id") or "")
        ntype = str(wn.get("node_type") or "").upper()
        if ntype not in ("FACILITY", "ROOM") or is_node_hidden(wn):
            continue
        parent = node_by_id.get(wn.get("parent_id")) if wn.get("parent_id") else None
        h_str = format_node_hierarchy(session_id, nid)
        if not h_str:
            continue
        low_h = h_str.lower()
        if any(ek in low_h for ek in _MEETUP_EXCLUDED_KEYWORDS):
            continue
        priv = str(wn.get("privacy_level") or "public").lower()
        if priv == "private" and "love_hotel" not in nid.lower():
            continue

        sched = evaluate_world_schedule_node_access(
            wn, parent, scen_key=scen_key, current_day=current_day, current_minute=current_minute
        )
        if sched.get("schedule_locked"):
            continue

        st = db.get_world_node_state(session_id, nid)
        pst = db.get_world_node_state(session_id, parent["node_id"]) if parent else {}
        is_disc = bool(st.get("is_discreet") or pst.get("is_discreet"))
        is_evening_nsfw_spot = is_nsfw and is_evening and any(
            k in nid.lower() for k in ("loc_love_hotel", "sub_love_hotel_lobby", "loc_nightclub")
        )
        if is_disc or is_evening_nsfw_spot:
            discreet_pool.append(h_str)
        elif ntype == "FACILITY" or priv == "public":
            regular_pool.append(h_str)

    c_name = str((contact or {}).get("name") or "npc")
    h_hex = hashlib.md5(f"meetup_pick:{session_id}:{c_name}:{current_day}:{safe_min // 60}:{seed_salt}".encode("utf-8")).hexdigest()
    roll_pct = int(h_hex[:6], 16) % 100
    idx_seed = int(h_hex[6:14], 16)

    if is_nsfw and is_bold and discreet_pool and roll_pct < 65:
        return discreet_pool[idx_seed % len(discreet_pool)]
    if regular_pool:
        return regular_pool[idx_seed % len(regular_pool)]
    if discreet_pool:
        return discreet_pool[idx_seed % len(discreet_pool)]
    return ""


def build_meetup_candidates_and_hint(
    session_id: int,
    session: dict | None,
    scen_key: str,
    curr_day_val: int,
    curr_min_val: int,
    *,
    contact: dict | None = None,
    openness: str = "",
    traits: list | None = None,
    is_romantic: bool = False,
    is_reschedule_request: bool = False,
    existing_appointment: dict | None = None,
) -> tuple[list[dict], str]:
    """
    Builds `(known_locations, meetup_location_hint)` for Smartphone DM meetup negotiation,
    allowing `is_discreet` spots (and NSFW evening venues) and weighting ~65% of candidate/persona
    guidance toward discreet spots for bold/uninhibited NPCs in NSFW scenarios.
    """
    import scenario_data
    from mechanics.world.waypoints import check_location_matches_waypoint
    from mechanics.world.world_schedule import (
        evaluate_world_schedule_node_access,
        is_campus_node_or_location,
        is_high_school_setting,
        is_weekend,
    )

    all_locs = db.get_session_locations(session_id) or []
    active_wps = db.get_all_session_active_waypoints(session_id) or []
    quest_occupied_locs = [wp.get("target_location", "") for wp in active_wps if wp.get("target_location")]
    player_curr_loc = (session.get("current_location") if isinstance(session, dict) else "") or ""
    safe_min_val = int(curr_min_val or 0) % 1440

    def _is_loc_schedule_accessible(loc_row: dict) -> bool:
        z_str = str(loc_row.get("zone_name") or "")
        p_str = str(loc_row.get("primary_name") or "")
        s_str = str(loc_row.get("sub_name") or "")
        full_str = f"{z_str} ➔ {p_str} ➔ {s_str}"
        comb = f"{z_str} {p_str} {s_str}".lower()
        cat = "academic" if any(k in comb for k in ("campus", "school", "academy", "classroom", "gym", "club", "courtyard", "auditorium", "library", "cafeteria")) else (
            "commercial" if any(k in comb for k in ("downtown", "commercial", "cafe", "café", "arcade", "store", "mall", "shop", "karaoke", "ramen", "restaurant", "bookstore", "boutique", "market", "nightclub")) else "public"
        )
        synth_node = {"node_id": s_str or p_str, "name": s_str or p_str, "node_type": "ROOM", "category": cat}
        synth_parent = {"node_id": p_str, "name": f"{z_str} {p_str}", "node_type": "FACILITY", "category": cat}
        access = evaluate_world_schedule_node_access(
            synth_node, synth_parent, scen_key=scen_key, current_day=curr_day_val, current_minute=curr_min_val
        )
        if access.get("schedule_locked"):
            return False
        if is_high_school_setting(scen_key) and not is_weekend(curr_day_val) and (480 <= safe_min_val < 900) and player_curr_loc:
            p_on_campus = is_campus_node_or_location(location_str=player_curr_loc, session_id=session_id, scen_key=scen_key)
            t_on_campus = is_campus_node_or_location(synth_node, synth_parent, location_str=full_str, session_id=session_id, scen_key=scen_key)
            if p_on_campus and not t_on_campus:
                return False
        return True

    public_locs: list[dict] = []
    for loc in all_locs:
        loc_label = " ".join(filter(None, [loc.get("zone_name", ""), loc.get("primary_name", ""), loc.get("sub_name", "")])).lower()
        if any(pk in loc_label for pk in _MEETUP_EXCLUDED_KEYWORDS):
            continue
        if not _is_loc_schedule_accessible(loc):
            continue
        full_loc = f"{loc.get('zone_name', '')} ➔ {loc.get('primary_name', '')} ➔ {loc.get('sub_name', '')}"
        prim_loc = f"{loc.get('zone_name', '')} -> {loc.get('primary_name', '')}"
        is_quest_loc = any(
            check_location_matches_waypoint(full_loc, ql) or check_location_matches_waypoint(prim_loc, ql) or check_location_matches_waypoint(ql, full_loc)
            for ql in quest_occupied_locs
        )
        if not is_quest_loc:
            public_locs.append(loc)

    # Also surface accessible `is_discreet` world_nodes (and Love Hotel / Nightclub in NSFW evening)
    is_nsfw = scenario_data.is_nsfw_scenario(scen_key)
    is_bold = is_bold_meetup_contact(contact, openness=openness, traits=traits)
    discreet_loc_rows: list[dict] = []
    if is_nsfw:
        try:
            from mechanics.world.locations.pathfinding import format_node_hierarchy, is_node_hidden
            w_nodes = db.get_session_world_nodes(session_id) or []
            n_map = {n["node_id"]: n for n in w_nodes if n.get("node_id")}
            for wn in w_nodes:
                nid = str(wn.get("node_id") or "")
                if is_node_hidden(wn) or str(wn.get("node_type") or "").upper() not in ("FACILITY", "ROOM"):
                    continue
                parent = n_map.get(wn.get("parent_id")) if wn.get("parent_id") else None
                st = db.get_world_node_state(session_id, nid)
                pst = db.get_world_node_state(session_id, parent["node_id"]) if parent else {}
                is_disc = bool(st.get("is_discreet") or pst.get("is_discreet"))
                is_lh_or_club = nid.lower() in ("loc_love_hotel", "loc_nightclub") and (safe_min_val >= 1080 or safe_min_val < 120)
                if not (is_disc or is_lh_or_club):
                    continue
                h_str = format_node_hierarchy(session_id, nid)
                parts = [p.strip() for p in h_str.split("➔") if p.strip()]
                if len(parts) >= 2:
                    row_d = {
                        "zone_name": parts[0],
                        "primary_name": parts[1],
                        "sub_name": parts[2] if len(parts) > 2 else "",
                        "_is_discreet": True,
                    }
                    if _is_loc_schedule_accessible(row_d):
                        discreet_loc_rows.append(row_d)
        except Exception:
            pass

    if not public_locs:
        public_locs = [
            loc for loc in all_locs
            if not any(pk in " ".join(filter(None, [loc.get("zone_name", ""), loc.get("primary_name", ""), loc.get("sub_name", "")])).lower() for pk in _MEETUP_EXCLUDED_KEYWORDS)
            and _is_loc_schedule_accessible(loc)
        ]
    if not public_locs:
        public_locs = [
            loc for loc in all_locs
            if not any(pk in " ".join(filter(None, [loc.get("zone_name", ""), loc.get("primary_name", ""), loc.get("sub_name", "")])).lower() for pk in _MEETUP_EXCLUDED_KEYWORDS)
        ]

    combined_locs = (discreet_loc_rows + public_locs) if (is_nsfw and is_bold) else (public_locs + discreet_loc_rows)
    if not combined_locs:
        return [], ""

    seen: set[str] = set()
    loc_lines: list[str] = []
    for loc in combined_locs:
        primary = loc.get("primary_name", "")
        sub = loc.get("sub_name", "")
        label = f"{primary}" + (f" ({sub})" if sub else "")
        if label and label not in seen:
            seen.add(label)
            loc_lines.append(label)

    meet_term = "Date" if is_romantic else "Meetup"
    reschedule_header = ""
    if is_reschedule_request and existing_appointment:
        old_loc = existing_appointment.get("rendezvous_location", "previous spot")
        reschedule_header = (
            f"- RESCHEDULING / LOCATION CHANGE REQUEST: The player is asking to change or relocate the meeting place (previously: '{old_loc}'). "
            f"Agree to change the location and pick a suitable new spot from the list below!\n"
        )
    bold_bias_note = ""
    if is_nsfw and is_bold and discreet_loc_rows:
        bold_bias_note = (
            "- BOLD / UNINHIBITED PERSONA PREFERENCE: Because you are bold and uninhibited, strongly prefer (~65% of the time) "
            "inviting the player to one of the secluded/discreet spots (or Mirage Boutique Love Hotel / Neon Pulse Nightclub at night) "
            "listed near the top rather than a crowded hallway!\n"
        )

    meetup_location_hint = (
        reschedule_header
        + bold_bias_note
        + f"- IMPORTANT — {meet_term} Location: You MUST suggest one of these REAL known locations from the world map. "
        f"Do NOT invent fictional place names. Choose one that fits your personality and relationship:\n"
        + "\n".join(f"  • {l}" for l in loc_lines[:30])
        + "\n- Set rendezvous_location to the EXACT primary name (or 'Primary (Sub)') from the list above.\n"
    )
    return combined_locs, meetup_location_hint


def evaluate_dm_in_person_gate(
    session_id: int,
    contact_name: str,
    track: str,
    user_message: str,
    intent: str,
) -> dict:
    """
    D14: Enforces in-person gates on Smartphone DMs:
    1. Romantic confessions while track != 'romantic' never promote track over text (caps delta <= 2, prompts face-to-face meeting).
    2. Active Story Quest / Caseboard clue interrogations never unlock clues over text (prompts meeting in person).
    """
    from mechanics.social.relationships import is_romantic_confession_intent

    msg_clean = str(user_message or "").strip()
    msg_low = msg_clean.lower()
    is_confession_gated = (
        str(track or "platonic").strip().lower() != "romantic"
        and bool(msg_clean)
        and is_romantic_confession_intent(msg_clean)
    )

    is_quest_gated = False
    if session_id and msg_low:
        _probe_kws = (
            "clue", "evidence", "suspect", "culprit", "alibi", "witness",
            "testimony", "caseboard", "murder", "disappearance", "investigat",
            "confess to the", "who killed", "who stole", "where were you",
        )
        has_probe_kw = any(kw in msg_low for kw in _probe_kws)
        try:
            active_quests = db.get_quests(session_id, status="active") or []
        except Exception:
            active_quests = []
        c_low = str(contact_name or "").lower().strip()
        c_first = (c_low.split() or [""])[0]
        for q in active_quests:
            q_blob = " ".join([
                str(q.get("title") or ""),
                str(q.get("objective") or ""),
                str(q.get("description") or ""),
                str(q.get("notes") or ""),
            ]).lower()
            npc_in_quest = bool(c_low and (c_low in q_blob or (len(c_first) >= 3 and c_first in q_blob)))
            title_words = [w for w in re.findall(r"[a-z]{4,}", str(q.get("title") or "").lower()) if w not in {"quest", "chapter", "bounty", "the", "with", "from", "into"}]
            msg_mentions_quest = any(tw in msg_low for tw in title_words)
            if (has_probe_kw and (npc_in_quest or msg_mentions_quest or active_quests)) or (
                intent in ("intel_rumor", "intel", "rumor") and npc_in_quest and has_probe_kw
            ):
                is_quest_gated = True
                break

    directives: list[str] = []
    if is_confession_gated:
        directives.append(
            "- MANDATORY IN-PERSON CONFESSION GATE: The player is confessing romantic feelings over text while you are on the Platonic track. "
            "Do NOT enter a romantic relationship over text! Respond warmly/flustered in-character and tell them something this meaningful must be said face-to-face in person.\n"
        )
    if is_quest_gated:
        directives.append(
            "- MANDATORY IN-PERSON INVESTIGATION GATE: The player is pressing for sensitive quest/case evidence over text. "
            "Do NOT reveal hard clues, culprits, or case breakthroughs over DM — explain it isn't safe or appropriate to text about this and ask to meet in person.\n"
        )

    return {
        "is_confession_gated": is_confession_gated,
        "is_quest_gated": is_quest_gated,
        "max_affinity_delta": 2 if is_confession_gated else None,
        "directive": "".join(directives),
    }


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
    history_rows: list = None,
    scenario: str = "",
) -> tuple[str, str]:
    """
    Validates, snaps to canonical session_locations / world_nodes, or seeds an open-world rendezvous location.
    Returns (resolved_rendezvous, intent).
    """
    # Fallback: If meetup intent and check succeeded but rendezvous was left blank, check if reply_text named a known location or world_node
    if intent == "meetup" and not rendezvous and check_succeeded:
        for loc in (known_locations or []):
            prim = loc.get("primary_name", "")
            sub = loc.get("sub_name", "")
            if prim and len(prim) > 3 and prim.lower() in reply_text.lower():
                rendezvous = prim
                break
            if sub and len(sub) > 3 and sub.lower() in reply_text.lower():
                rendezvous = sub
                break
        if not rendezvous and reply_text:
            snapped_from_reply = _get_public_world_node_hierarchy(session_id, reply_text)
            if snapped_from_reply:
                rendezvous = snapped_from_reply

    # Follow-up confirmation detection: player confirms an agreed meetup proposed by contact
    if intent in ("custom", "chat") and is_meetup_confirmation_message(user_message) and history_rows:
        last_contact_msg = next((r["message"] for r in reversed(history_rows) if r.get("sender") == "npc"), "")
        if last_contact_msg:
            if not known_locations:
                all_locs = db.get_session_locations(session_id)
                known_locations = [
                    loc for loc in all_locs
                    if not any(pk in " ".join(filter(None, [loc.get("zone_name", ""), loc.get("primary_name", ""), loc.get("sub_name", "")])).lower() for pk in _MEETUP_EXCLUDED_KEYWORDS)
                ]
            for loc in (known_locations or []):
                prim = loc.get("primary_name", "")
                sub = loc.get("sub_name", "")
                if (prim and len(prim) > 3 and prim.lower() in last_contact_msg.lower()) or (sub and len(sub) > 3 and sub.lower() in last_contact_msg.lower()):
                    zone = loc.get("zone_name", "")
                    rendezvous = f"{zone} ➔ {prim}" + (f" ➔ {sub}" if sub else "")
                    intent = "meetup"
                    break
            if intent != "meetup":
                snapped_hist = _get_public_world_node_hierarchy(session_id, last_contact_msg)
                if snapped_hist:
                    rendezvous = snapped_hist
                    intent = "meetup"

    # Strictly for meetup intent
    resolved_rendezvous = rendezvous if intent == "meetup" else ""
    if intent == "meetup":
        if existing_appointment and not is_reschedule_request:
            resolved_rendezvous = existing_appointment["rendezvous_location"]
        elif rendezvous:
            best_match = None
            best_score_val = 0
            if known_locations:
                rendezvous_lower = rendezvous.lower().strip()
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
                # D14: Snap unmatched rendezvous to canonical world_nodes
                snapped_node_loc = _get_public_world_node_hierarchy(session_id, rendezvous)
                if snapped_node_loc:
                    resolved_rendezvous = snapped_node_loc
                else:
                    from mechanics.world.mobility import is_campus_scenario
                    scen_low = str(scenario or "").lower().strip()
                    if not scen_low and session_id:
                        try:
                            s_row = db.get_session(session_id) or {}
                            scen_low = str(s_row.get("scenario") or "").lower().strip()
                        except Exception:
                            scen_low = ""
                    is_closed_campus = bool(
                        is_campus_scenario(scen_low)
                        or "school" in scen_low
                        or "slice" in scen_low
                    )
                    if is_closed_campus:
                        # Closed campus/slice-of-life: prefer persona-weighted accessible venue (bold -> ~65% discreet)
                        fallback_public = ""
                        try:
                            c_day, c_min, _ = db.get_session_time(session_id)
                            c_obj = db.get_contact(session_id, str(contact_name or "").lower().replace(" ", "_"), 0)
                            fallback_public = select_npc_preferred_meetup_venue(
                                session_id,
                                c_obj,
                                scen_low,
                                current_day=c_day,
                                current_minute=c_min,
                            )
                        except Exception:
                            fallback_public = ""
                        if not fallback_public:
                            try:
                                from mechanics.world.locations.pathfinding import format_node_hierarchy, is_node_hidden
                                for wn in (db.get_session_world_nodes(session_id) or []):
                                    wn_priv = str(wn.get("privacy_level") or wn.get("privacy") or "public").lower()
                                    wn_type = str(wn.get("node_type") or wn.get("tier") or "").lower()
                                    if wn_priv != "private" and not is_node_hidden(wn) and wn_type in ("facility", "room"):
                                        fallback_public = format_node_hierarchy(session_id, wn["node_id"])
                                        if fallback_public:
                                            break
                            except Exception:
                                fallback_public = ""
                        if fallback_public:
                            resolved_rendezvous = fallback_public
                        elif known_locations:
                            loc0 = known_locations[0]
                            z0 = loc0.get("zone_name", "")
                            p0 = loc0.get("primary_name", "")
                            s0 = loc0.get("sub_name", "")
                            resolved_rendezvous = f"{z0} ➔ {p0}" + (f" ➔ {s0}" if s0 else "")
                        else:
                            resolved_rendezvous = current_loc or rendezvous.strip()
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
                        try:
                            w_nodes = db.get_session_world_nodes(session_id) or []
                            if w_nodes:
                                from mechanics.world.locations.pathfinding import format_node_hierarchy
                                parent_nid = db.resolve_node_id_from_location(session_id, seed_zone) or w_nodes[0]["node_id"]
                                new_nid = f"dm_spot_{re.sub(r'[^a-z0-9_]', '_', seed_primary.lower()).strip('_')[:36]}"
                                db.save_world_node(
                                    session_id=session_id,
                                    node_id=new_nid,
                                    parent_id=parent_nid,
                                    name=seed_primary,
                                    node_type="facility",
                                    privacy_level="public",
                                    is_dynamic=1,
                                )
                                db.save_world_edge(
                                    session_id=session_id,
                                    from_node_id=parent_nid,
                                    to_node_id=new_nid,
                                    travel_minutes=3,
                                    is_bidirectional=1,
                                )
                                resolved_rendezvous = format_node_hierarchy(session_id, new_nid)
                        except Exception:
                            pass
                        log.info(f"[phone] Seeded new dynamic meetup location: {resolved_rendezvous} for session {session_id}")
        elif check_succeeded and session_id:
            try:
                c_day, c_min, _ = db.get_session_time(session_id)
                c_obj = db.get_contact(session_id, str(contact_name or "").lower().replace(" ", "_"), 0)
                resolved_rendezvous = select_npc_preferred_meetup_venue(
                    session_id, c_obj, scenario, current_day=c_day, current_minute=c_min
                )
            except Exception:
                pass

    if resolved_rendezvous and intent == "meetup" and session_id:
        low_rv = resolved_rendezvous.lower()
        low_reply = str(reply_text or "").lower()
        if ("love hotel" in low_rv or "mirage boutique" in low_rv) and any(
            kw in low_reply for kw in ("my treat", "treat you", "on me", "i'll cover", "already booked", "got us a room", "i've got the room")
        ):
            try:
                c_day, _, _ = db.get_session_time(session_id)
                db.update_session(session_id, extra={"love_hotel_waived_day": int(c_day)})
            except Exception:
                pass

    return resolved_rendezvous, intent
