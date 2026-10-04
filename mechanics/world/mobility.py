from __future__ import annotations
"""
Smart Campus Mobility & NPC Presence Mechanics for Hikayat.

Provides:
1. Campus Quad / Co-located zone grouping for high school & campus scenarios.
2. Mobile character vs stationary fixture classification.
3. Intentional travel & quest waypoint rendezvous target detection.
4. Active physical presence validation (distinguishing physical presence from passive rumors).
5. Automatic contact location synchronization upon scene arrival.
"""
import json
import re
from typing import Dict, Any, List, Optional, Set, Tuple

import db


CAMPUS_SCENARIOS = {
    "high_school_drama",
    "nsfw_high_school_drama",
    "furry_high_school_drama",
    "nsfw_furry_high_school_drama",
    "modern",
    "academy",
}

def is_campus_scenario(scen_key: str = "") -> bool:
    """Checks if the scenario is a high school, academy, or campus scenario."""
    if not scen_key:
        return False
    s_low = str(scen_key).lower().strip()
    return s_low in CAMPUS_SCENARIOS or any(k in s_low for k in ("school", "academy", "campus", "high_school"))


# Connected campus zones that form a single shared campus realm
CAMPUS_ZONE_KEYWORDS = {
    "academy", "school", "campus", "high school", "high", "institute", "grounds", "athletics",
    "fieldhouse", "quad", "courtyard", "faculty", "dormitory", "dorms",
    "stadium", "sports complex", "gym", "commons", "plaza", "cultural arts",
    "student union", "arts & union", "club wing", "old campus", "clock tower",
    "derelict", "wing"
}

# ---------------------------------------------------------------- Campus Topological Graph & Area Links
CAMPUS_NODE_ACADEMIC = "academic"       # Gateway / Main Entrance
CAMPUS_NODE_COMMONS = "commons"         # Central Hub of the Cross
CAMPUS_NODE_ATHLETICS = "athletics"     # Sports Complex & Stadium
CAMPUS_NODE_ARTS = "arts"               # Cultural Arts & Student Union
CAMPUS_NODE_ABANDONED = "abandoned"     # Old Campus & Clock Tower

CAMPUS_ADJACENCY: Dict[str, Set[str]] = {
    CAMPUS_NODE_COMMONS: {CAMPUS_NODE_ACADEMIC, CAMPUS_NODE_ATHLETICS, CAMPUS_NODE_ARTS, CAMPUS_NODE_ABANDONED},
    CAMPUS_NODE_ACADEMIC: {CAMPUS_NODE_COMMONS},
    CAMPUS_NODE_ATHLETICS: {CAMPUS_NODE_COMMONS},
    CAMPUS_NODE_ARTS: {CAMPUS_NODE_COMMONS},
    CAMPUS_NODE_ABANDONED: {CAMPUS_NODE_COMMONS},
}

CAMPUS_NODE_DISPLAY_NAMES: Dict[str, str] = {
    CAMPUS_NODE_ACADEMIC: "Main Academic Building",
    CAMPUS_NODE_COMMONS: "Student Commons & Central Plaza",
    CAMPUS_NODE_ATHLETICS: "Varsity Athletics Complex",
    CAMPUS_NODE_ARTS: "Cultural Arts & Student Union",
    CAMPUS_NODE_ABANDONED: "Abandoned Old Campus Building",
}


def classify_campus_zone_node(zone_name: str, scen_key: str = "high_school_drama") -> Optional[str]:
    """Classifies a zone name into one of the 5 campus topological nodes, or None if off-campus."""
    if not zone_name or not is_campus_scenario(scen_key):
        return None
    z = zone_name.lower().strip()

    if any(k in z for k in ("abandoned", "old campus", "clock tower", "derelict", "heritage wing")):
        return CAMPUS_NODE_ABANDONED
    if any(k in z for k in ("cultural arts", "student union", "creative arts", "arts & union", "club annex")):
        return CAMPUS_NODE_ARTS
    if any(k in z for k in ("commons", "central plaza", "courtyard & dining", "promenade & commons", "courtyard")):
        return CAMPUS_NODE_COMMONS
    if any(k in z for k in ("athletics", "sports", "grounds", "gymnasium", "fieldhouse", "stadium", "pool", "dojo", "sheds")):
        return CAMPUS_NODE_ATHLETICS
    if any(k in z for k in ("academy", "school", "campus", "academic", "institute", "high school", "high")):
        return CAMPUS_NODE_ACADEMIC

    return None


def find_campus_travel_path(from_zone: str, to_zone: str, scen_key: str = "high_school_drama") -> List[str]:
    """
    Finds the shortest topological sequence of zones between two zones using BFS on the campus graph.
    Returns a list of zone node identifiers or zone display names.
    """
    node_from = classify_campus_zone_node(from_zone, scen_key)
    node_to = classify_campus_zone_node(to_zone, scen_key)

    # 1. Intra-campus BFS
    if node_from and node_to:
        if node_from == node_to:
            return [node_from]
        queue = [[node_from]]
        visited = {node_from}
        while queue:
            path = queue.pop(0)
            curr = path[-1]
            if curr == node_to:
                return path
            for neighbor in CAMPUS_ADJACENCY.get(curr, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])
        return [node_from, node_to]

    # 2. Campus to Off-Campus: Route through Academic Gateway
    if node_from and not node_to:
        campus_path = find_campus_travel_path(from_zone, "academic", scen_key)
        return campus_path + [to_zone]

    # 3. Off-Campus to Campus: Route through Academic Gateway
    if not node_from and node_to:
        campus_path = find_campus_travel_path("academic", to_zone, scen_key)
        return [from_zone] + campus_path

    # 4. Off-Campus to Off-Campus
    return [from_zone, to_zone]


def calculate_route_travel_time(
    old_loc: str,
    new_loc: str,
    scen_key: str = "high_school_drama",
    session_id: int = 0
) -> int:
    """
    Calculates exact setting-aware travel time in minutes.
    - Same room / Sub-location move: 2 minutes.
    - Same zone, different Primary Place: 5 minutes.
    - Intra-campus travel: 5 minutes per graph link (e.g. Academic ➔ Commons ➔ Athletics = 10 mins).
    - Campus to Off-Campus (or vice-versa): 5 mins per inner campus link + 25 mins from gateway = 25..35 mins.
    - Off-Campus to Off-Campus: 25 minutes (Modern) or 120 minutes (Fantasy).
    """
    if not old_loc or not new_loc or old_loc == new_loc:
        return 2

    from mechanics.world.locations import get_zone_location_name, get_primary_location_name
    old_z = get_zone_location_name(old_loc).strip()
    new_z = get_zone_location_name(new_loc).strip()
    old_p = get_primary_location_name(old_loc).strip()
    new_p = get_primary_location_name(new_loc).strip()

    # Same zone
    if old_z.lower() == new_z.lower():
        if old_p.lower() != new_p.lower():
            return 5
        return 2

    # Different zone
    is_campus = is_campus_scenario(scen_key)
    if is_campus:
        node_from = classify_campus_zone_node(old_z, scen_key)
        node_to = classify_campus_zone_node(new_z, scen_key)

        # 1. Both on-campus
        if node_from and node_to:
            path = find_campus_travel_path(old_z, new_z, scen_key)
            hops = max(1, len(path) - 1)
            return hops * 5

        # 2. Campus to Off-Campus
        if node_from and not node_to:
            campus_path = find_campus_travel_path(old_z, "academic", scen_key)
            campus_hops = max(0, len(campus_path) - 1)
            return (campus_hops * 5) + 25

        # 3. Off-Campus to Campus
        if not node_from and node_to:
            campus_path = find_campus_travel_path("academic", new_z, scen_key)
            campus_hops = max(0, len(campus_path) - 1)
            return 25 + (campus_hops * 5)

        # 4. Off-Campus to Off-Campus
        return 25

    # Non-campus modern scenarios (e.g. cyberpunk)
    from mechanics.system.time_engine import is_modern_setting
    if is_modern_setting(scen_key):
        return 25

    # Fantasy / Wilderness interzone travel
    return 120


def format_travel_route_breadcrumb(
    old_loc: str,
    new_loc: str,
    scen_key: str = "high_school_drama"
) -> str:
    """Formats an evocative travel route string showing intermediate traversal areas."""
    from mechanics.world.locations import get_zone_location_name, get_primary_location_name
    old_z = get_zone_location_name(old_loc)
    new_z = get_zone_location_name(new_loc)
    old_p = get_primary_location_name(old_loc)
    new_p = get_primary_location_name(new_loc)

    total_mins = calculate_route_travel_time(old_loc, new_loc, scen_key=scen_key)

    if old_z.lower() == new_z.lower():
        if old_p.lower() != new_p.lower():
            return f"Route: {old_p} ➔ {new_p} ({total_mins} mins)"
        return f"Route: Local Movement ({total_mins} mins)"

    if is_campus_scenario(scen_key):
        path = find_campus_travel_path(old_z, new_z, scen_key)
        rendered_steps = []
        for step in path:
            if step in CAMPUS_NODE_DISPLAY_NAMES:
                rendered_steps.append(CAMPUS_NODE_DISPLAY_NAMES[step])
            else:
                rendered_steps.append(step)
        route_str = " ➔ ".join(rendered_steps)
        return f"Route: {route_str} ({total_mins} mins)"

    return f"Route: {old_z} ➔ {new_z} ({total_mins} mins)"


def is_campus_co_located(zone_a: str, zone_b: str, scen_key: str = "high_school_drama") -> bool:
    """
    Checks if two zones belong to the same connected school campus quad.
    For example: 'Westlake Academy' and 'School Grounds & Athletics' are
    adjacent facilities of the same school campus.
    """
    if not zone_a or not zone_b:
        return False
    za = zone_a.lower().strip()
    zb = zone_b.lower().strip()
    if za == zb:
        return True

    if not is_campus_scenario(scen_key):
        return False

    node_a = classify_campus_zone_node(za, scen_key)
    node_b = classify_campus_zone_node(zb, scen_key)
    if node_a is not None and node_b is not None:
        return True

    has_a = any(k in za for k in CAMPUS_ZONE_KEYWORDS)
    has_b = any(k in zb for k in CAMPUS_ZONE_KEYWORDS)
    return has_a and has_b
STATIONARY_ROLES = {
    "nurse",
    "school nurse",
    "librarian",
    "head librarian",
    "shopkeeper",
    "merchant",
    "storekeeper",
    "vendor",
    "bartender",
    "barista",
    "barkeep",
    "innkeeper",
    "clerk",
    "curator",
    "cashier",
    "receptionist",
    "statue",
    "fixture",
    "spirit",
    "guardian",
    "blacksmith",
    "armorer",
    "gatekeeper",
}


def is_character_mobile(npc_name: str, contact_data: dict = None, scen_key: str = "high_school_drama") -> bool:
    """
    Determines if an NPC is a mobile character (student, club president, roaming peer)
    or a stationary fixture (librarian at desk, bound ancient spirit, shop counter keeper).
    """
    if not npc_name:
        return False

    contact_data = contact_data or {}
    basic = contact_data.get("basic_info") or {}
    role = str(basic.get("role", "") or contact_data.get("role", "")).lower().strip()
    desc = str(basic.get("description", "") or contact_data.get("description", "")).lower().strip()

    # Check if explicitly a stationary role
    if any(sr in role for sr in STATIONARY_ROLES) or any(sr in desc for sr in ("bound to", "rooted to", "anchored to", "ancient spirit")):
        return False

    # In campus scenarios, students, club heads, and peer characters are naturally mobile
    if is_campus_scenario(scen_key):
        return True

    # Check for general mobile markers
    mobile_roles = {"companion", "ally", "adventurer", "traveler", "scout", "ranger", "mercenary", "messenger", "diplomat"}
    return any(mr in role for mr in mobile_roles)


def is_rendezvous_target(npc_name: str, actions: list = None, session_id: int = None, new_loc: str = "") -> bool:
    """
    Checks if an NPC is the intended target of:
    1. A player travel/meetup action (e.g. 'Travel to gym to meet Sofia Anderson')
    2. An active Story Quest or Side Bounty waypoint at new_loc (e.g. 'Convene meeting with Sofia')
    3. A phone appointment at new_loc
    """
    if not npc_name:
        return False

    n_low = npc_name.lower().strip()
    n_first = n_low.split()[0] if n_low else ""
    first_min_len = 3

    # 1. Inspect player actions (travel-to-meet actions ONLY)
    travel_meetup_verbs = (
        "meet ", "meet with ", "convene with ", "convene meeting with ",
        "rendezvous with ", "catch up with "
    )
    from mechanics.world.locations import is_movement_action
    for a in (actions or []):
        lbl = (a.get("label") if isinstance(a, dict) else str(a)).lower()
        if is_movement_action(lbl) or any(k in lbl for k in ("travel to", "head to", "walk to", "go to", "visit")):
            if n_low in lbl or (len(n_first) >= first_min_len and f" {n_first}" in f" {lbl}"):
                if any(mv in lbl for mv in travel_meetup_verbs) or "meet" in lbl or "rendezvous" in lbl:
                    return True

    # 2. Inspect active Story Quest and Side Quests in database
    if session_id:
        try:
            from mechanics.world.waypoints import check_location_matches_waypoint

            # Check all active quest waypoints
            active_wps = db.get_all_session_active_waypoints(session_id)
            for wp in active_wps:
                wp_text = f"{wp.get('title', '')} {wp.get('objective', '')} {wp.get('notes', '')}".lower()
                wp_loc = wp.get("location", "")
                is_loc_match = not wp_loc or not new_loc or check_location_matches_waypoint(new_loc, wp_loc) or check_location_matches_waypoint(wp_loc, new_loc)
                if is_loc_match:
                    if n_low in wp_text or (len(n_first) >= first_min_len and f" {n_first}" in f" {wp_text}"):
                        return True

            # Check active story quest sub-objectives
            sq = db.get_active_story_quest(session_id)
            if sq:
                sq_text = f"{sq.get('title', '')} {sq.get('objective', '')}".lower()
                sub_objs = sq.get("sub_objectives") or []
                for so in sub_objs:
                    if isinstance(so, dict) and not so.get("completed"):
                        sq_text += " " + str(so.get("text", "")).lower()
                if n_low in sq_text or (len(n_first) >= first_min_len and f" {n_first}" in f" {sq_text}"):
                    return True

            # 3. Inspect phone appointments (only pending appointments or ongoing arrived meetups)
            pending_appts = db.get_phone_appointments(session_id, status="pending")
            sess = db.get_session(session_id) if session_id else None
            arrived_appts = [
                a for a in db.get_phone_appointments(session_id, status="arrived")
                if any(str((x.get("name") or x.get("npc_name")) if isinstance(x, dict) else x).strip().lower() == a.get("npc_name", "").strip().lower() for x in (sess.get("current_npcs") or []))
                or str(sess.get("dialogue_partner") or "").strip().lower() == a.get("npc_name", "").strip().lower()
            ] if sess else []
            for appt in (pending_appts + arrived_appts):
                a_npc = str(appt.get("npc_name", "")).lower().strip()
                a_loc = str(appt.get("rendezvous_location", ""))
                if (n_low in a_npc or a_npc in n_low) and (not a_loc or not new_loc or check_location_matches_waypoint(new_loc, a_loc)):
                    return True
        except Exception:
            pass

    return False


import unicodedata

def _norm_name(text: str) -> str:
    if not text:
        return ""
    return unicodedata.normalize('NFKD', str(text)).encode('ASCII', 'ignore').decode('utf-8').strip().lower()


def get_session_dialogue_partners(session: dict | None) -> list[str]:
    """
    Consolidates the legacy string 'dialogue_partner' and the list/JSON 'dialogue_partners'
    into a canonical, deduplicated list of partner name strings.
    Guards against character-by-character iteration bugs when a string is evaluated.
    """
    if not session or not isinstance(session, dict):
        return []

    partners: list[str] = []

    dps = session.get("dialogue_partners")
    if dps:
        if isinstance(dps, str):
            try:
                parsed = json.loads(dps)
                if isinstance(parsed, list):
                    partners.extend(str(x).strip() for x in parsed if x and str(x).strip())
                elif parsed and str(parsed).strip():
                    partners.append(str(parsed).strip())
            except Exception:
                # If it looks like JSON structure, discard on error rather than treating as NPC name
                cleaned = dps.strip()
                if cleaned and not cleaned.startswith(("{", "[")):
                    partners.append(cleaned)
        elif isinstance(dps, list):
            for p in dps:
                if isinstance(p, list):
                    partners.extend(str(x).strip() for x in p if x and str(x).strip())
                elif p and str(p).strip():
                    partners.append(str(p).strip())

    dp = session.get("dialogue_partner")
    if dp and isinstance(dp, str):
        dp_clean = dp.strip()
        if dp_clean and not any(dp_clean.lower() == existing.lower() for existing in partners):
            if dp_clean.startswith("[") and dp_clean.endswith("]"):
                try:
                    parsed = json.loads(dp_clean)
                    if isinstance(parsed, list):
                        for x in parsed:
                            if x and str(x).strip() and not any(str(x).strip().lower() == existing.lower() for existing in partners):
                                partners.append(str(x).strip())
                except Exception:
                    partners.append(dp_clean)
            else:
                partners.append(dp_clean)

    # Deduplicate while preserving order (case-insensitive)
    seen = set()
    result = []
    for p in partners:
        plow = p.lower()
        if plow not in seen:
            seen.add(plow)
            result.append(p)
    return result


def is_dialogue_partner(name: str, dialogue_partners: list | str = None, session: dict = None) -> bool:
    """Checks if a character name matches any active dialogue partner."""
    if not name:
        return False
    if dialogue_partners is None and session:
        partners_list = get_session_dialogue_partners(session)
    elif not dialogue_partners:
        return False
    elif isinstance(dialogue_partners, str):
        try:
            parsed = json.loads(dialogue_partners)
            partners_list = parsed if isinstance(parsed, list) else [dialogue_partners]
        except Exception:
            partners_list = [dialogue_partners]
    elif isinstance(dialogue_partners, list):
        partners_list = []
        for p in dialogue_partners:
            if isinstance(p, list):
                partners_list.extend(str(x) for x in p if x)
            elif p:
                partners_list.append(str(p))
    else:
        partners_list = [str(dialogue_partners)]

    n_raw = name.strip().lower()
    n_clean = _norm_name(name)
    title_words = {
        "the", "elder", "lord", "lady", "sir", "madam", "captain", "dr", "mr", "ms", "mrs",
        "scholar", "guardian", "druid", "student", "council", "president", "vice", "secretary",
        "representative", "officer", "member", "guildmaster", "archivist", "warden"
    }
    n_tokens = [t for t in n_clean.split() if len(t) > 2 and t not in title_words]
    if not n_tokens and len(n_clean) > 2:
        n_tokens = [n_clean]

    for p in partners_list:
        p_raw = str(p).strip().lower()
        p_clean = _norm_name(p)
        if p_raw in n_raw or n_raw in p_raw or p_clean in n_clean or n_clean in p_clean:
            return True
        for t in n_tokens:
            if t in p_clean or t in p_raw:
                return True
    return False


THIRD_PLACE_KEYWORDS = {
    "cafe", "café", "coffee", "bakery", "tea", "diner", "bistro", "restaurant",
    "park", "gardens", "plaza", "courtyard", "commons", "mall", "arcade",
    "lounge", "bar", "pub", "tavern", "commercial", "strip", "bookstore"
}

MEETUP_INTENT_KEYWORDS = (
    "meet", "meetup", "date", "hangout", "hang out", "catch up",
    "rendezvous", "coffee", "lunch", "dinner", "walk together",
    "walk home", "walk back", "study together", "go together",
    "accompany", "come with", "join me", "tag along", "head out together"
)

SOLO_TRAVEL_PHRASES = (
    "go alone", "going alone", "travel alone", "head alone", "walk alone", "leave alone",
    "by myself", "on my own", "without you", "without her", "without him",
    "stay here", "stay behind", "wait for me", "wait here",
    "i'll go alone", "i want to go alone", "just me", "just myself",
    "don't come", "don't follow", "leave you here"
)

ACCOMPANIED_TRAVEL_PHRASES = (
    "together", "with her", "with him", "with them", "both of us",
    "hand in hand", "holding hands", "walk together", "head out together",
    "our walk", "leave together", "step out together", "join me", "accompany",
    "come with", "tag along"
)

_SOLO_TRAVEL_REGEX = re.compile(
    r"\b(?:go|going|travel|traveling|head|heading|walk|walking|leave|leaving|depart|departing|return|returning|step|stepping|excuse|excusing)\b[^.!?]*\balone\b",
    re.IGNORECASE,
)


def is_solo_travel_intent(actions: list = None) -> bool:
    """Returns True if the player's action explicitly expresses intent to travel or leave alone."""
    if not actions:
        return False
    for a in actions:
        lbl = (
            (str(a.get("label", "")) + " " + str(a.get("text", "")))
            if isinstance(a, dict)
            else str(a)
        ).lower()
        
        # Guard 1: Accompanied Travel (Keywords or RegEx)
        if any(term in lbl for term in ACCOMPANIED_TRAVEL_PHRASES) or re.search(r"\b(?:with|accompany|follow)\s+[a-z]+", lbl) or re.search(r"\b(?:together|both of us)\b", lbl):
            continue
            
        # Guard 2: Conversational Privacy / Intimacy
        if re.search(r"\b(?:where we can be alone|be alone with|spend some time alone|speak with .* alone|talk to .* alone|confer with .* alone|time alone)\b", lbl):
            continue
            
        # Guard 3: Protective / Defensive
        if re.search(r"\b(?:leave\s+(?:[a-z]+|her|him|them)\s+alone)\b", lbl):
            continue
            
        # Guard 4: Negation
        if re.search(r"\b(?:not\s+alone|don't\s+go\s+alone|won't\s+leave\s+alone|never\s+alone)\b", lbl):
            continue

        if any(p in lbl for p in SOLO_TRAVEL_PHRASES) or _SOLO_TRAVEL_REGEX.search(lbl):
            return True
    return False


def is_social_third_place(loc_str: str) -> bool:
    """Checks if a location is a public social third place (cafe, mall, park, diner, etc.)."""
    if not loc_str:
        return False
    l_low = str(loc_str).lower()
    return any(tp in l_low for tp in THIRD_PLACE_KEYWORDS)


def has_narrative_continuity_bridge(npc_name: str, session: dict = None, actions: list = None, new_loc: str = "") -> bool:
    """
    Checks if an NPC has a verifiable conversational or narrative link to appear at new_loc:
    1. Within the same primary venue (or no location change): active dialogue partner or co-located NPC.
    2. Across different primary venues/zones:
       - Explicit invitation or accompanied travel in current action, OR
       - Recent history (last 1-3 turns) shows a proposal/agreement to meet up, hang out, date, or travel.
    """
    if not npc_name:
        return False

    if is_solo_travel_intent(actions):
        return False

    from mechanics.world.locations import get_primary_location_name

    n_low = npc_name.lower().strip()
    n_first = n_low.split()[0] if n_low else ""

    old_loc = (session.get("current_location") or "") if session else ""
    old_primary = get_primary_location_name(old_loc) if old_loc else ""
    new_primary = get_primary_location_name(new_loc) if new_loc else ""
    is_different_primary = bool(old_primary and new_primary and old_primary.lower() != new_primary.lower())


    is_dp = is_dialogue_partner(npc_name, session=session) if session else False

    # 1. Same primary venue (or no destination change): active dialogue partner or co-located NPC retains continuity
    if session and not is_different_primary:
        if is_dp:
            return True
        old_npcs = session.get("current_npcs") or []
        for on in old_npcs:
            on_name = str((on.get("name") or on.get("npc_name")) if isinstance(on, dict) else on).strip().lower()
            if on_name and (on_name == n_low or (len(n_first) >= 3 and on_name.startswith(n_first))):
                return True

    # 2. Check actions for travel/meetup/accompanied intent
    if actions:
        for a in actions:
            lbl = (
                (str(a.get("label", "")) + " " + str(a.get("text", "")))
                if isinstance(a, dict)
                else str(a)
            ).lower()
            # Active dialogue partner with accompanied travel phrase (e.g., "Step out together")
            if is_dp and any(term in lbl for term in ACCOMPANIED_TRAVEL_PHRASES):
                return True
            if n_low in lbl or (len(n_first) >= 3 and f" {n_first}" in f" {lbl}"):
                if any(k in lbl for k in MEETUP_INTENT_KEYWORDS) or any(
                    k in lbl for k in ("travel to", "head to", "go to", "visit", "with", "invite", "bring", "follow")
                ):
                    return True

    # 3. Check recent conversation history for date / meetup agreements
    if session:
        hist_raw = session.get("history") or session.get("history_json") or []
        if isinstance(hist_raw, str):
            try:
                hist_list = json.loads(hist_raw)
            except Exception:
                hist_list = [hist_raw]
        elif isinstance(hist_raw, list):
            hist_list = hist_raw
        else:
            hist_list = []

        recent_hist = hist_list[-3:] if len(hist_list) > 3 else hist_list
        for h in recent_hist:
            h_str = str(h).lower()
            if n_low in h_str or (len(n_first) >= 3 and f" {n_first}" in f" {h_str}"):
                if any(k in h_str for k in MEETUP_INTENT_KEYWORDS):
                    return True

    return False



def is_mentioned_only_in_dialogue(npc_name: str, text: str) -> bool:
    """Checks if an NPC is mentioned exclusively inside spoken dialogue (in quotation marks)."""
    if not npc_name or not text:
        return False
    n_lower = npc_name.lower().strip()
    first_name = n_lower.split()[0] if len(n_lower.split()) > 1 else n_lower

    # Strip paired double quotes and curly quotes
    without_quotes = re.sub(r'["“][^"”]*["”]', ' ', text)
    without_quotes = re.sub(r'‘[^’]*’', ' ', without_quotes)
    without_quotes = re.sub(r'「[^」]*」', ' ', without_quotes)

    pattern = r'\b' + re.escape(n_lower) + r'\b'
    if len(first_name) >= 3 and first_name != n_lower:
        pattern += r'|\b' + re.escape(first_name) + r'\b'

    in_full = bool(re.search(pattern, text, re.IGNORECASE))
    in_outside = bool(re.search(pattern, without_quotes, re.IGNORECASE))
    return in_full and not in_outside


def has_active_physical_presence(npc_name: str, result: dict, narrative_text: str = "") -> bool:
    """
    Determines if an NPC is physically present in the scene (speaking aloud,
    physically described as present in entity_audit, or acting in narrative),
    distinguishing real presence from passive conversational rumors or departures.
    """
    if not npc_name:
        return False

    n_low = npc_name.lower().strip()
    n_first = n_low.split()[0] if n_low else ""

    # Check if explicitly departed
    departures = [str(x).lower().strip() for x in (result.get("npc_departures") or [])]
    entity_audit = result.get("entity_audit") or {}
    if isinstance(entity_audit, dict):
        departures.extend(str(x).lower().strip() for x in (entity_audit.get("departed_characters") or []))
    if any(n_low in d or (len(n_first) >= 3 and n_first in d) for d in departures):
        return False

    # If mentioned ONLY inside spoken dialogue quotes, they are being talked about, NOT present
    if narrative_text and is_mentioned_only_in_dialogue(npc_name, narrative_text):
        return False

    # 1. Check entity_audit speaking_characters & present_named_characters
    if isinstance(entity_audit, dict):
        speaking = [str(x).lower().strip() for x in (entity_audit.get("speaking_characters") or [])]
        if any(n_low == s or (len(n_first) >= 3 and n_first == s) or (n_low in s or s in n_low) for s in speaking if s):
            return True

        present = [str(x).lower().strip() for x in (entity_audit.get("present_named_characters") or [])]
        if any(n_low == p or (len(n_first) >= 3 and n_first == p) or (n_low in p or p in n_low) for p in present if p):
            return True

    # 2. Check speaking characters and physical action in narrative
    if narrative_text:
        nar_norm = narrative_text.lower()
        nar_without_dialogue = re.sub(r'["“][^"”]*["”]', ' ', nar_norm)
        nar_without_dialogue = re.sub(r'‘[^’]*’', ' ', nar_without_dialogue)
        nar_without_dialogue = re.sub(r'「[^」]*」', ' ', nar_without_dialogue)

        pattern = r'\b' + re.escape(n_low) + r'\b'
        if len(n_first) >= 3 and n_first != n_low:
            pattern += r'|\b' + re.escape(n_first) + r'\b'

        has_in_prose = bool(re.search(pattern, nar_without_dialogue))

        if has_in_prose:
            # Check for direct speech verbs, physical actions, and clause action verbs
            nar_cleaned = re.sub(r'[—–]', ' ', nar_norm)
            action_verbs = {
                "says", "said", "asks", "asked", "replies", "replied", "greets", "greeted",
                "pushes", "stands", "stood", "leans", "leaned", "looks", "looked", "shifts",
                "shifted", "smiles", "smiled", "smirks", "smirked", "steps", "stepped",
                "waves", "waved", "nods", "nodded", "sits", "sat", "takes", "took", "waits",
                "waited", "waiting", "arrives", "arrived", "watches", "watched", "watch",
                "laughs", "laughed", "remarks", "remarked", "sips", "sipped", "orders",
                "ordered", "pauses", "paused", "tilts", "tilted", "cuts", "walks", "walked",
                "joins", "joined", "listen", "listens", "listened", "gathers", "gathered",
                "beside", "behind", "surrounding", "flanked", "accompanied", "seated"
            }
            # Direct name + verb
            if any(re.search(r'\b' + re.escape(f"{n_first} {v}") + r'\b', nar_cleaned) for v in action_verbs):
                return True
            # Clause window check: name and action verb within 60 chars in prose
            for m in re.finditer(pattern, nar_without_dialogue):
                start = max(0, m.start() - 60)
                end = min(len(nar_cleaned), m.end() + 60)
                clause = nar_cleaned[start:end]
                if any(re.search(r'\b' + re.escape(v) + r'\b', clause) for v in action_verbs):
                    return True

    return False



def sync_contact_locations(final_npcs: list, new_loc: str, session_id: int):
    """
    Automatically synchronizes and updates the canonical 'location' field in contacts
    for all NPCs verified to be physically present in the scene.
    """
    if not final_npcs or not new_loc or not session_id:
        return

    try:
        known_contacts = db.get_contacts(session_id)
        for npc in final_npcs:
            if not isinstance(npc, dict):
                continue
            n_name = (npc.get("name") or "").strip()
            if not n_name:
                continue
            n_low = n_name.lower()

            matched_c = next((
                c for c in known_contacts
                if str(c.get("name", "")).strip().lower() == n_low or
                str(c.get("npc_id", "")).strip().lower() == n_low.replace(" ", "_")
            ), None)

            if matched_c:
                basic = dict(matched_c.get("basic_info") or {})
                curr_c_loc = basic.get("location", "")
                if curr_c_loc != new_loc:
                    basic["location"] = new_loc
                    db.upsert_contact(
                        session_id=session_id,
                        character_id=matched_c.get("character_id", 0),
                        npc_id=matched_c.get("npc_id") or n_name,
                        name=n_name,
                        basic_info=basic,
                        track=matched_c.get("track", "platonic")
                    )
    except Exception:
        pass
