from __future__ import annotations
"""
Time & Day/Night Engine for Hikayat.

Provides:
- 24-hour clock simulation (00:00 - 23:59) stored in minutes from midnight (0..1439).
- Weekday tracking (Monday - Sunday).
- Time-of-day phases (Dawn, Morning, Afternoon, Dusk, Night, Midnight) with emoji.
- Setting-aware travel and action time calculations (Modern vs Wilderness/Fantasy).
- Progressive multi-stage fatigue tracking for staying awake past dawn (05:00 AM).
- Bedtime & Sleep resolution (advances to 07:30 AM, restores HP/MP, clears fatigue, rolls Day +1).
- LLM prompt context formatting for narrative atmosphere and lighting.
"""
import json
import logging
import random
import re
from typing import Dict, Any, List, Optional, Tuple

import db

log = logging.getLogger("hikayat.time_engine")

DAYS_OF_WEEK = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

# Time of day phases mapped by minute from midnight (0..1439)
# Format: (start_minute, end_minute, phase_name, emoji, lighting_desc)
TIME_PHASES = [
    (300, 479, "Early Morning", "🌅", "Crisp dawn light, pale morning sky, cool morning air"),
    (480, 719, "Morning", "☀️", "Bright daylight, active morning bustle"),
    (720, 1019, "Afternoon", "☀️", "Warm sun, midday to late afternoon light"),
    (1020, 1199, "Evening", "🌇", "Golden hour dusk, long shadows, twilight glow"),
    (1200, 1439, "Night", "🌙", "Dark night sky, artificial lighting, moonlit atmosphere"),
    (0, 299, "Midnight", "🌌", "Dead of night, dim shadows, late-night stillness"),
]


def is_modern_setting(scen_key: str) -> bool:
    """Checks if scenario has modern/fast transit."""
    if not scen_key:
        return False
    s = str(scen_key).lower()
    return any(m in s for m in [
        "high_school", "school", "cyber", "scifi", "sci_fi", "modern",
        "anomalous", "incursion", "urban_fantasy", "urban_anomalies", "slice_of_life"
    ])


def format_clock(minute: int) -> str:
    """Formats minutes from midnight into 24-hour HH:MM format."""
    safe_min = int(minute or 0) % 1440
    hour = safe_min // 60
    rem_min = safe_min % 60
    return f"{hour:02d}:{rem_min:02d}"


def get_time_of_day_phase(minute: int) -> Tuple[str, str, str]:
    """Returns (phase_name, emoji, lighting_description) for the given minute."""
    safe_min = int(minute or 0) % 1440
    for start, end, name, emoji, lighting in TIME_PHASES:
        if start <= safe_min <= end:
            return name, emoji, lighting
    return "Day", "☀️", "Ambient light"


def get_day_of_week(current_day: int) -> str:
    """Returns standard weekday name for current_day (Day 1 = Monday)."""
    day_idx = max(0, int(current_day or 1) - 1) % len(DAYS_OF_WEEK)
    return DAYS_OF_WEEK[day_idx]


def format_time_header(current_day: int, current_minute: int) -> str:
    """Formats the time display for the adventure dashboard.
    Example: 📅 Monday | 🕒 08:30 (Morning ☀️)
    """
    day_name = get_day_of_week(current_day)
    clock_str = format_clock(current_minute)
    phase_name, emoji, _ = get_time_of_day_phase(current_minute)
    return f"📅 {day_name} | 🕒 {clock_str} ({phase_name} {emoji})"


def is_sleep_time(current_minute: int, scen_key: str | None = None) -> bool:
    """Returns True if it is bedtime (>= 22:00 / 10:00 PM or before morning wake-up: 07:00 AM for High School, 06:00 AM default)."""
    safe_min = int(current_minute or 0) % 1440
    wake_cutoff = 360
    if scen_key:
        try:
            from mechanics.world.world_schedule import is_high_school_setting, get_scenario_wake_minute
            if is_high_school_setting(scen_key):
                wake_cutoff = get_scenario_wake_minute(scen_key)
        except Exception:
            pass
    return safe_min >= 1320 or safe_min < wake_cutoff


def is_sleep_action(action_label: str) -> bool:
    """Checks if an action string represents sleeping / turning in for the night."""
    if not action_label:
        return False
    lbl = str(action_label).lower().strip()
    keywords = [
        "sleep until morning", "sleep through the night", "call it a night",
        "go to sleep", "head to sleep", "sleep in your bed", "sleep in bed",
        "turn in for the night", "rest until morning", "sleep until tomorrow",
        "[rest] sleep", "sleep until 7", "sleep until 07", "sleep until 8"
    ]
    return any(kw in lbl for kw in keywords)


def is_nap_action(action_label: str) -> Tuple[bool, int]:
    """Detects if an action corresponds to taking a nap and returns (is_nap, duration_minutes)."""
    t = str(action_label or "").lower()
    if "nap" not in t:
        return False, 0
    m = re.search(r"\b(\d+)\s*(?:hour|hr)s?\s*nap\b", t)
    if m:
        hours = int(m.group(1))
        return True, max(30, min(360, hours * 60))
    if "power nap" in t or "short nap" in t:
        return True, 60
    return True, 120


def scenario_allows_camp_sleep(scen_key: str = "") -> bool:
    """Returns True if the scenario allows camping/sleeping anywhere (pure wilderness fantasy / post-apocalypse).
    Modern, urban, high school, slice-of-life, cyberpunk, sci-fi, and steampunk settings REQUIRE a bed or sofa/couch.
    """
    s = str(scen_key or "").lower().strip()
    if not s:
        return True
    MODERN_OR_URBAN_TAGS = {
        "anomalous", "incursion", "urban_fantasy", "urban_anomalies", "scp", "control",
        "high_school", "school", "slice_of_life", "modern", "cyberpunk", "cyber",
        "sci_fi", "scifi", "space", "steampunk", "noir"
    }
    if any(k in s for k in MODERN_OR_URBAN_TAGS):
        return False
    try:
        from scenario_data import has_tag
        for t in MODERN_OR_URBAN_TAGS:
            if has_tag(s, t):
                return False
    except Exception:
        pass
    return True


BED_KEYWORDS = {
    "bed", "beds", "bedroom", "bedrooms", "bunk", "bunks", "berth", "berths",
    "futon", "futons", "cot", "cots", "mattress", "hammock", "dorm", "dormitory",
    "dormitories", "stateroom", "suite", "tatami", "studio", "bungalow", "penthouse", "loft", "billet", "quarters"
}

COUCH_KEYWORDS = {
    "sofa", "sofas", "couch", "couches", "divan", "settee", "davenport", "daybed"
}

FALSE_BED_SUBSTRINGS = {
    "planter bed", "flower bed", "riverbed", "bed of nails", "tanning bed", "rockbed", "sea bed", "seabed"
}

NON_SLEEPING_SUBLOC_WORDS = {
    "entrance", "doorway", "foyer", "lobby", "corridor",
    "hallway", "walkway", "stairwell", "elevator", "porch", "mailbox",
    "balcony", "bathroom", "shower", "locker", "lockers", "kitchen", "kitchenette", "galley",
    "garage", "courtyard", "street", "alley", "roof", "rooftop", "airlock",
}


def get_location_sleep_context(
    location_name: str,
    props: Optional[List[str]] = None,
    scenario: str = "",
    session_id: Optional[int] = None,
    node_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Evaluates whether the current environment provides a viable sleeping/napping surface."""
    prop_rest_mult = 1.0
    if not scenario and session_id:
        try:
            scenario = str((db.get_session(int(session_id)) or {}).get("scenario") or "")
        except Exception:
            scenario = ""
    try:
        from mechanics.world.anomalous_sites.domain_rules import is_sleep_blocked_in_anomalous_zone
        cur_min_sleep = 720
        if session_id:
            try:
                cur_min_sleep = int(db.get_session_time(int(session_id))[1] or 720)
            except Exception:
                cur_min_sleep = 720
        blocked_sleep, sleep_block_reason = is_sleep_blocked_in_anomalous_zone(
            session_id=int(session_id or 0),
            location_name=location_name,
            node_id=node_id or "",
            current_minute=cur_min_sleep,
            scen_key=scenario or "fantasy",
        )
        if blocked_sleep:
            return {
                "surface": "none",
                "can_sleep": False,
                "recovery_ratio": 0.0,
                "surface_label": "Quarantine Hazard",
                "blocked_by_anomaly": True,
                "reason": sleep_block_reason,
            }
    except Exception:
        pass
    if scenario_allows_camp_sleep(scenario):
        return {
            "surface": "camp",
            "can_sleep": True,
            "recovery_ratio": round(1.0 * prop_rest_mult, 3),
            "surface_label": "Camp",
            "reason": "Wilderness/fantasy environment permits making camp anywhere."
        }

    if props is None and session_id:
        try:
            phys = db.get_session_physical_state(session_id)
            if isinstance(phys, dict):
                props = phys.get("props")
        except Exception:
            props = None

    loc_str = str(location_name or "").lower()
    props_str = " ".join(str(p).lower() for p in (props or []))

    # Split 3-tier breadcrumb to inspect the active leaf sub-location
    loc_segments = [s.strip() for s in re.split(r"➔|->|\|", loc_str) if s.strip()]
    leaf_loc = loc_segments[-1] if loc_segments else loc_str
    leaf_only_words = set(re.findall(r"[a-z]+", leaf_loc))
    leaf_and_props = f"{leaf_loc} {props_str}"
    for fb in FALSE_BED_SUBSTRINGS:
        leaf_and_props = leaf_and_props.replace(fb, " ")
    leaf_words = set(re.findall(r"[a-z]+", leaf_and_props))

    leaf_has_explicit_bed = (
        any(k in leaf_words for k in ("bed", "beds", "bedroom", "bedrooms", "bunk", "bunks", "berth", "berths", "futon", "futons", "cot", "cots", "mattress", "hammock", "stateroom"))
        or any(k in leaf_and_props for k in ("sleeping quarters", "sleeping cabin", "captain's cabin", "bunk bed", "brass bed", "studio loft"))
    )
    leaf_has_explicit_couch = (
        any(k in leaf_words for k in COUCH_KEYWORDS)
        or any(k in leaf_and_props for k in ("lounge couch", "rec couch", "velvet divan", "lounge seating", "living room", "living lounge", "velvet lounge", "operative lounge", "vip booth", "private karaoke room", "clubroom sofa"))
    )

    # Entrance / Foyer / Non-Sleeping Sub-Location Guard:
    # Standing in a foyer, entrance doorway, porch, bathroom, kitchen, or hallway inside a residential/dorm building
    # does NOT grant a sleeping surface unless that specific leaf room or its props explicitly contain a bed/couch.
    if len(loc_segments) >= 2 and (bool(leaf_only_words & NON_SLEEPING_SUBLOC_WORDS) or "keycard desk" in leaf_loc):
        if not leaf_has_explicit_bed and not leaf_has_explicit_couch:
            return {
                "surface": "none",
                "can_sleep": False,
                "recovery_ratio": 0.0,
                "surface_label": "None",
                "reason": "No bed or sofa/couch in this immediate area. Time skip will only pass time with 0% recovery."
            }

    combined_env = f"{loc_str} {props_str}"
    clean_env = combined_env
    for fb in FALSE_BED_SUBSTRINGS:
        clean_env = clean_env.replace(fb, " ")

    prop_rest_mult = 1.0
    if session_id:
        try:
            from mechanics.world.locations.residences import get_player_owned_or_starter_property_for_node
            sess_sleep = db.get_session(int(session_id)) or {}
            resolved_loc_nid = str(node_id or "") or ((db.resolve_node_id_from_location(int(session_id), location_name) or "") if location_name else "")
            nid_sleep = resolved_loc_nid or str(sess_sleep.get("current_node_id") or "")
            if nid_sleep:
                owned_sleep = get_player_owned_or_starter_property_for_node(int(session_id), nid_sleep, session=sess_sleep)
                if owned_sleep and owned_sleep.get("catalog_entry"):
                    prop_rest_mult = max(1.0, float(owned_sleep["catalog_entry"].get("rest_multiplier") or 1.0))
        except Exception:
            prop_rest_mult = 1.0

    sanctuary_bed_unlocked = False
    spirit_lodging_res: dict[str, Any] | None = None
    if session_id:
        try:
            from mechanics.world.locations.folklore_veil import get_folklore_sanctuary_rest_multiplier
            sess_sanc = db.get_session(int(session_id)) or {}
            res_sanc_nid = str(node_id or "") or ((db.resolve_node_id_from_location(int(session_id), location_name) or "") if location_name else "")
            sanc_nid = res_sanc_nid or str(sess_sanc.get("current_node_id") or "")
            if sanc_nid in ("sub_kitsune_sovereign_pavilion", "sub_bunian_royal_istana"):
                sanc_mult = get_folklore_sanctuary_rest_multiplier(
                    int(session_id),
                    sanc_nid,
                    active_companions=(sess_sanc.get("temporary_companions") or []) + (sess_sanc.get("party_npcs") or []),
                )
                if sanc_mult > 1.0:
                    prop_rest_mult = max(prop_rest_mult, float(sanc_mult))
                    sanctuary_bed_unlocked = True
            elif sanc_nid == "sub_crossroads_inn_chambers":
                spirit_lodging_res = {
                    "surface": "bed",
                    "can_sleep": True,
                    "recovery_ratio": round(1.0 * prop_rest_mult, 3),
                    "surface_label": "Spirit Inn Chambers",
                    "reason": "Clean tatami & cotton bedding at the Two-Moons River Tea-Pavilion Inn Chambers (100% rest recovery).",
                }
            elif sanc_nid in ("sub_kitsune_autumn_rotenburo", "sub_kitsune_bamboo_bath", "sub_bunian_waterfall_grotto"):
                spirit_lodging_res = {
                    "surface": "couch",
                    "can_sleep": True,
                    "recovery_ratio": round(max(1.15, prop_rest_mult), 3),
                    "surface_label": "Spirit Spring / Onsen Respite",
                    "reason": "Warm mineral waters and drifting incense restore vitality deeply (115% restorative spirit soak).",
                }
        except Exception:
            pass
    if sanctuary_bed_unlocked:
        return {
            "surface": "bed",
            "can_sleep": True,
            "recovery_ratio": round(1.0 * prop_rest_mult, 3),
            "surface_label": "Sacred Sanctuary Pavilion",
            "reason": "Welcomed inside the Sovereign/Royal Folklore Pavilion (150% sacred rest recovery).",
        }
    if spirit_lodging_res is not None:
        return spirit_lodging_res

    # If the active leaf sub-location explicitly provides a couch and lacks a dedicated bed,
    # prioritize the local room's couch over facility-wide building nouns (e.g. "studio", "dorm")
    if leaf_has_explicit_couch and not leaf_has_explicit_bed:
        return {
            "surface": "couch",
            "can_sleep": True,
            "recovery_ratio": round(0.5 * prop_rest_mult, 3),
            "surface_label": "Sofa / Couch",
            "reason": "Sofa / couch available (50% recovery)."
        }

    # 1. Check for dedicated bed surfaces (100% recovery)
    words = set(re.findall(r"[a-z]+", clean_env))
    if (
        leaf_has_explicit_bed
        or any(k in words for k in BED_KEYWORDS)
        or any(k in clean_env for k in ("sleeping quarters", "rest quarters", "crew quarters", "personal quarters", "living quarters", "sleeping cabin", "captain's cabin", "bunk bed", "brass bed", "studio loft"))
    ):
        return {
            "surface": "bed",
            "can_sleep": True,
            "recovery_ratio": round(1.0 * prop_rest_mult, 3),
            "surface_label": "Bed",
            "reason": "Dedicated bed / sleeping quarters available (100% recovery)."
        }

    # 2. Check for sofa / couch surfaces (50% recovery)
    if (
        leaf_has_explicit_couch
        or any(k in words for k in COUCH_KEYWORDS)
        or any(k in clean_env for k in ("lounge couch", "rec couch", "velvet divan", "lounge seating", "living room", "living lounge", "velvet lounge", "operative lounge", "vip booth", "private karaoke room", "clubroom sofa"))
    ):
        return {
            "surface": "couch",
            "can_sleep": True,
            "recovery_ratio": round(0.5 * prop_rest_mult, 3),
            "surface_label": "Sofa / Couch",
            "reason": "Sofa / couch available (50% recovery)."
        }

    return {
        "surface": "none",
        "can_sleep": False,
        "recovery_ratio": 0.0,
        "surface_label": "None",
        "reason": "No bed or sofa/couch in vicinity. Time skip will only pass time with 0% recovery."
    }


def calculate_action_time_cost(
    action: dict | str,
    scen_key: str = "fantasy",
    old_loc: str = "",
    new_loc: str = "",
    is_dialogue: bool = False,
    is_combat: bool = False,
    session_id: int = 0
) -> int:
    raw_lbl = action.get("label") if isinstance(action, dict) else action
    lbl = str(raw_lbl or "").lower().strip()
    
    # 1. Free / Ambient Actions (Observation, Redressing, Dropping burden)
    if isinstance(action, dict) and str(action.get("stat", "")).upper() == "FREE":
        return 0

    # 1.5 Sleep Action handled separately by apply_sleep_rest
    if is_sleep_action(lbl):
        return 0

    # 1.75 Explicit Rendezvous / Clock Wait Action ("Wait for X until 4:00 PM")
    if "wait" in lbl and "until" in lbl:
        import re as _re
        m_wait = _re.search(r"until\s+(\d{1,2}):(\d{2})\s*(am|pm)?", lbl, _re.IGNORECASE)
        if m_wait:
            wh = int(m_wait.group(1))
            wm = int(m_wait.group(2))
            ampm = (m_wait.group(3) or "").lower()
            if ampm == "pm" and wh < 12:
                wh += 12
            elif ampm == "am" and wh == 12:
                wh = 0
            target_min = (wh % 24) * 60 + (wm % 60)
            if session_id:
                try:
                    _, curr_min, _ = db.get_session_time(session_id)
                    delta = (target_min - int(curr_min)) % 1440
                    return delta if delta > 0 else 5
                except Exception:
                    pass
            return 30

    # 2. Combat Encounter turn
    if is_combat or any(kw in lbl for kw in ["attack", "strike", "cast ", "shoot", "defend", "brace", "dodge"]):
        return 5

    def _apply_pact_transit_compression(base_mins: int) -> int:
        if base_mins <= 0 or not session_id:
            return base_mins
        try:
            from mechanics.pacts import compute_pact_travel_time_multiplier, is_entity_contracts_scenario
            if not is_entity_contracts_scenario(scen_key):
                return base_mins
            act_uid = int(action.get("user_id") or (action.get("char") or {}).get("user_id") or 0) if isinstance(action, dict) else 0
            if not act_uid:
                sess_tr = db.get_session(int(session_id)) or {}
                act_uid = int(sess_tr.get("host_user_id") or 0)
                cur_day_tr = int(sess_tr.get("current_day") or 1)
            else:
                cur_day_tr, _, _ = db.get_session_time(int(session_id))
            if not act_uid:
                return base_mins
            pacts_tr = db.get_player_active_pacts(int(session_id), act_uid)
            if not pacts_tr:
                return base_mins
            t_mult, zero_ckey = compute_pact_travel_time_multiplier(
                pacts_tr,
                current_day=int(cur_day_tr or 1),
                scenario_or_key=scen_key,
            )
            if zero_ckey:
                db.mark_pact_zero_minute_step_used(int(session_id), zero_ckey, int(cur_day_tr or 1))
                return 0
            if 0.0 < t_mult < 1.0:
                return max(1, int(round(base_mins * t_mult)))
        except Exception:
            pass
        return base_mins

    # 3. Location Travel & Movement
    try:
        if old_loc and new_loc and old_loc != new_loc:
            from mechanics.world.mobility import calculate_route_travel_time
            return _apply_pact_transit_compression(
                calculate_route_travel_time(old_loc, new_loc, scen_key=scen_key, session_id=session_id)
            )
    except Exception:
        pass

    # Check by action keywords if explicit travel was requested in action label
    travel_verbs = ["travel to", "travel toward", "head to", "head toward", "walk to", "journey to", "depart toward", "go to", "move to", "commute to"]
    if any(tv in lbl for tv in travel_verbs):
        is_modern = is_modern_setting(scen_key)
        if any(kw in lbl for kw in ["district", "downtown", "suburb", "city", "zone", "station", "valley", "mountains", "forest"]):
            return _apply_pact_transit_compression(25 if is_modern else 120)
        return _apply_pact_transit_compression(5 if is_modern else 15)

    # 4. Dialogue / Social Turn
    if is_dialogue or any(kw in lbl for kw in ["talk", "speak", "discuss", "chat", "ask", "inquire", "whisper", "comfort", "tease", "flirt", "confess"]):
        return 2

    # 5. Investigation / Search / Examination / Anomalous Site Puzzle or Harvest
    if isinstance(action, dict) and str(action.get("intent") or "").strip().lower() == "anomalous_site_action" and not is_combat:
        return 10
    if any(kw in lbl for kw in ["search", "investigate", "inspect", "examine", "study", "read", "scavenge", "loot", "look around", "survey"]):
        return 10

    # 6. Default Exploration Action
    return 5


def run_boundary_autonomy_and_epistemic_tick(
    session_id: int,
    old_day: int,
    old_minute: int,
    new_day: int,
    new_minute: int,
    *,
    party_uids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Executes Part A off-screen NPC autonomy (`D8–D11`) and Part B epistemic gossip/decay/alibi
    ticks (`B4, B5, B8, B11, B16`) once per crossed time-block or day boundary inside a single `UnitOfWork`.
    """
    from mechanics.world.schedule_blocks import get_time_block_key

    o_day = max(1, int(old_day or 1))
    n_day = max(1, int(new_day or o_day))
    o_min = int(old_minute or 0) % 1440
    n_min = int(new_minute or 0) % 1440
    old_block = get_time_block_key(o_min)
    new_block = get_time_block_key(n_min)
    if n_day == o_day and old_block == new_block:
        return {"boundary_crossed": False}

    from mechanics.social import relationship_graph as rg
    from mechanics.social.epistemic_engine import tick_epistemic_boundary_propagation
    from mechanics.world.npc_autonomy import compute_boundary_autonomy_deltas

    sid = int(session_id or 0)
    if not sid:
        return {"boundary_crossed": False}

    session = db.get_session(sid) or {}
    scen_key = str(session.get("scenario") or "fantasy").strip().lower()
    turn_no = int(db.get_effective_session_turn(sid) or 0)
    roster_rows = db.get_world_roster(sid, include_legacy_rosters=False) or []
    contacts = db.get_contacts(sid) or []
    active_events = db.get_world_events(sid, include_hidden=True, statuses=("active", "escalating")) or []

    all_ties: List[Dict[str, Any]] = []
    with db.get_conn() as read_conn:
        tie_rows = read_conn.execute(
            "SELECT * FROM social_ties WHERE session_id = ? AND status = 'active'",
            (sid,),
        ).fetchall()
        all_ties = [dict(r) for r in tie_rows]

    def _key_of(row: Dict[str, Any]) -> str:
        return str(row.get("person_key") or row.get("npc_id") or row.get("name") or "").strip().lower().replace(" ", "_")

    roster_map: Dict[str, Dict[str, Any]] = {}
    hh_groups: Dict[int, List[str]] = {}
    party_key_set: set[str] = set()
    for row in roster_rows:
        rk = _key_of(row)
        if not rk:
            continue
        roster_map[rk] = row
        if row.get("is_companion"):
            party_key_set.add(rk)
        hh_id = row.get("household_id")
        if hh_id:
            hh_groups.setdefault(int(hh_id), []).append(rk)
    for c_row in contacts:
        ck = _key_of(c_row)
        if not ck:
            continue
        if c_row.get("in_party") or c_row.get("is_companion"):
            party_key_set.add(ck)
        c_hh = c_row.get("household_id")
        if c_hh and ck not in hh_groups.get(int(c_hh), ()):
            hh_groups.setdefault(int(c_hh), []).append(ck)

    households = [{"household_id": hid, "members": mkeys} for hid, mkeys in hh_groups.items() if mkeys]
    deltas = compute_boundary_autonomy_deltas(
        sid,
        old_day=o_day,
        old_min=o_min,
        new_day=n_day,
        new_min=n_min,
        scen_key=scen_key,
        roster_rows=roster_rows,
        contacts=contacts,
        all_ties=all_ties,
        party_keys=frozenset(party_key_set),
        active_events=active_events,
        turn_number=turn_no,
    )

    epistemic_res: Dict[str, Any] = {}
    with db.UnitOfWork() as conn:
        for top in deltas.get("tie_ops") or []:
            t_op = top.get("op")
            if t_op == "nudge":
                rg.record_tie_nudge(
                    sid,
                    str(top.get("person_a") or ""),
                    str(top.get("person_b") or ""),
                    str(top.get("axis") or ""),
                    float(top.get("delta") or 0.0),
                    turn=int(top.get("turn") or turn_no),
                    conn=conn,
                )
            elif t_op == "evolve_tie":
                ttype = str(top.get("tie_type") or "friend")
                rg.form_tie(
                    sid,
                    str(top.get("person_a") or ""),
                    str(top.get("person_b") or ""),
                    ttype,
                    closeness=int(top.get("closeness") or 50),
                    visibility=top.get("visibility"),
                    turn=int(top.get("turn") or turn_no),
                    origin="autonomy_evolution",
                    supersede=ttype in ("dating", "best_friend"),
                    materialize=False,
                    conn=conn,
                )
            elif t_op == "breakup":
                rg.end_all_romantic_ties(
                    sid,
                    str(top.get("person_a") or ""),
                    str(top.get("person_b") or ""),
                    turn=int(top.get("turn") or turn_no),
                    reason=str(top.get("reason") or "breakup"),
                    materialize=False,
                    conn=conn,
                )
        r_muts = deltas.get("roster_mutations") or []
        if r_muts:
            db.apply_world_roster_autonomy_mutations(sid, r_muts, turn_number=turn_no, conn=conn)

        rng_seed = random.Random(f"{sid}:{n_day}:{new_block}:{turn_no}")
        epistemic_res = tick_epistemic_boundary_propagation(
            sid,
            session,
            day=n_day,
            bell_slot=new_block,
            roster_map=roster_map,
            social_ties=all_ties,
            households=households,
            rng=rng_seed,
            turn=turn_no,
            contacts=contacts,
            conn=conn,
        )

    raw_gossip = deltas.get("gossip_posts") or []
    if raw_gossip:
        try:
            formatted_posts = [
                {
                    "author_name": str(gp.get("author_name") or "Campus Pulse"),
                    "author_handle": str(gp.get("author_handle") or "@campuspulse"),
                    "content": str(gp.get("summary") or gp.get("content") or "").strip(),
                    "tag": str(gp.get("tag") or "#Gossip"),
                    "clue_hook": str(gp.get("clue_hook") or ""),
                    "time_ago": str(gp.get("time_ago") or "Just now"),
                }
                for gp in raw_gossip
                if isinstance(gp, dict) and (gp.get("summary") or gp.get("content"))
            ]
            if formatted_posts:
                db.save_gossip_feed(sid, formatted_posts)
        except Exception as _gp_err:
            log.debug("Autonomy gossip feed write skipped for session %s: %s", sid, _gp_err)

    for ping in deltas.get("dm_pings") or []:
        try:
            from mechanics.system.phone.messaging import enqueue_autonomy_hangout_ping
            enqueue_autonomy_hangout_ping(sid, ping)
        except Exception as _ping_err:
            log.debug("Autonomy DM ping skipped for session %s: %s", sid, _ping_err)

    return {
        "boundary_crossed": True,
        "old_block": old_block,
        "new_block": new_block,
        "tie_ops_applied": len(deltas.get("tie_ops") or []),
        "roster_mutations_applied": len(deltas.get("roster_mutations") or []),
        "dm_pings_queued": len(deltas.get("dm_pings") or []),
        "epistemic": epistemic_res,
    }


def advance_time(
    session_id: int,
    delta_minutes: int,
    party_uids: Optional[List[int]] = None
) -> Dict[str, Any]:
    """
    Advances session time by delta_minutes.
    Handles minute overflow, day incrementation, and character days_adventured tracking.
    Returns summary dict of state changes.
    """
    if delta_minutes <= 0:
        sess = db.get_session(session_id) or {}
        return {
            "session_id": session_id,
            "old_day": sess.get("current_day", 1),
            "new_day": sess.get("current_day", 1),
            "old_minute": sess.get("current_minute", 480),
            "new_minute": sess.get("current_minute", 480),
            "days_elapsed": 0,
            "minutes_elapsed": 0,
            "day_rolled_over": False,
            "fatigue_applied": []
        }

    curr_day, curr_min, consecutive_awake = db.get_session_time(session_id)
    total_minutes = curr_min + delta_minutes
    
    days_elapsed = total_minutes // 1440
    new_minute = total_minutes % 1440
    new_day = curr_day + days_elapsed
    day_rolled = days_elapsed > 0

    # Update database
    db.update_session_time(
        session_id=session_id,
        current_day=new_day,
        current_minute=new_minute,
        consecutive_days_awake=consecutive_awake + days_elapsed
    )

    # Check rendezvous appointment reminders & stand-up expirations via unified commitments_ledger
    try:
        from mechanics.system.commitments_engine import audit_and_expire_commitments
        audit_and_expire_commitments(session_id, new_day, new_minute)
    except Exception as e:
        log.warning("Failed processing commitments audit/expiration for session %s: %s", session_id, e)

    # If day rolled over, clear temporary companions (return home)
    if day_rolled:
        try:
            db.clear_temporary_companions(session_id)
        except Exception:
            pass

        # Phase 4 Daily Board Replenishment:
        try:
            from mechanics.narrative.bounty import replenish_daily_bounties_deterministic
            existing_quests = db.get_session_quests(session_id)
            if existing_quests:
                replenish_daily_bounties_deterministic(session_id)
        except Exception as e:
            log.warning("Failed daily bounty replenishment for session %s: %s", session_id, e)

        # Anomalous Incursions Daily Rollover (Salary, Mandatory Bounty Audit & Dispatch, 2-3 Daily Incursions)
        try:
            from mechanics.world.anomalous_events import process_anomalous_daily_rollover
            process_anomalous_daily_rollover(session_id, new_day, party_uids=party_uids)
        except Exception as e:
            log.warning("Failed anomalous daily rollover for session %s: %s", session_id, e)

    # If day rolled over, increment days_adventured for all party members
    if day_rolled and party_uids:
        for uid in party_uids:
            try:
                db.increment_days_adventured(uid, delta=days_elapsed, session_id=session_id)
            except Exception as e:
                log.warning("Failed to increment days_adventured for user %s: %s", uid, e)

    # Check for fatigue escalation if crossing dawn (05:00 AM / minute 300) without sleeping
    fatigue_notices = []
    if (curr_min < 300 and new_minute >= 300) or days_elapsed > 0:
        fatigue_notices = check_and_apply_fatigue(session_id, party_uids or [])

    try:
        from mechanics.world.world_events.engine import advance_world_pulse
        advance_world_pulse(
            session_id=session_id,
            delta_minutes=delta_minutes,
            current_day=new_day,
            current_minute=new_minute,
            is_sleep_skip=False,
        )
    except Exception as e:
        log.warning("Failed advancing world pulse for session %s: %s", session_id, e)

    threat_clock_tick = None
    try:
        from mechanics.narrative.threat_clock import tick_threat_clock
        threat_clock_tick = tick_threat_clock(
            session_id,
            new_day,
            new_minute,
            turn_number=db.get_effective_session_turn(session_id),
        )
    except Exception as e:
        log.warning("Failed ticking Threat Clock for session %s: %s", session_id, e)

    boundary_tick = {}
    try:
        boundary_tick = run_boundary_autonomy_and_epistemic_tick(
            session_id,
            curr_day,
            curr_min,
            new_day,
            new_minute,
            party_uids=party_uids,
        )
    except Exception as e:
        log.warning("Failed running boundary autonomy/epistemic tick for session %s: %s", session_id, e)

    return {
        "session_id": session_id,
        "old_day": curr_day,
        "new_day": new_day,
        "old_minute": curr_min,
        "new_minute": new_minute,
        "days_elapsed": days_elapsed,
        "minutes_elapsed": delta_minutes,
        "day_rolled_over": day_rolled,
        "fatigue_applied": fatigue_notices,
        "threat_clock_tick": threat_clock_tick,
        "boundary_tick": boundary_tick,
    }


def apply_sleep_rest(
    session_id: int,
    party_uids: List[int],
    wake_minute: Optional[int] = None,
    scen_key: str = "",
    recovery_ratio: float = 1.0,
    surface_label: str = "Bed",
    freeze_clock: bool = False,
    override_clock_minutes: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Executes a full night's sleep.
    - Advances clock to wake_minute (07:00 AM / 420 mins for High School, 07:30 AM / 450 mins for others),
      unless freeze_clock=True (stasis) or override_clock_minutes is provided (scaled realm time).
    - Skips external world day-rollover side effects when freeze_clock=True or clock does not cross a day.
    - Restores character HP/MP according to recovery_ratio (100% for Bed/Camp, 50% for Sofa/Couch).
    - Clears all fatigue, knockout/triage recovery, and intimate refractory/arousal status effects.
    - Restores canonical morning outfits and resets refractory state while preserving pockets_emptied.
    - Re-syncs room NPCs to morning schedule (when a normal/overnight sleep rolls the world).
    - Resets consecutive_days_awake to 0.
    """
    curr_day, curr_min, _ = db.get_session_time(session_id)
    session = db.get_session(session_id)
    eff_scen = scen_key or (session.get("scenario", "fantasy") if isinstance(session, dict) else "fantasy")
    if wake_minute is None:
        from mechanics.world.world_schedule import get_scenario_wake_minute
        wake_minute = get_scenario_wake_minute(eff_scen)

    if freeze_clock:
        new_day = int(curr_day)
        new_minute = int(curr_min)
    elif override_clock_minutes is not None:
        ov_m = max(0, int(override_clock_minutes))
        new_day = int(curr_day) + ((int(curr_min) + ov_m) // 1440)
        new_minute = (int(curr_min) + ov_m) % 1440
    else:
        # If sleeping before midnight (e.g. 22:00) or past morning wake-up (e.g. 08:00 AM),
        # sleep until next morning -> Day + 1.
        # If sleeping in early morning hours before wake-up (e.g. 02:00 AM), wake at morning same day.
        new_day = curr_day + 1 if curr_min >= int(wake_minute) else curr_day
        new_minute = int(wake_minute)

    clock_advanced = (not freeze_clock) and (new_day != curr_day or new_minute != curr_min)
    day_rolled_over = (not freeze_clock) and (new_day > curr_day)
    is_normal_overnight = (not freeze_clock) and (override_clock_minutes is None)

    db.update_session_time(
        session_id=session_id,
        current_day=new_day,
        current_minute=new_minute,
        consecutive_days_awake=0
    )

    if clock_advanced:
        try:
            from mechanics.system.commitments_engine import audit_and_expire_commitments
            audit_and_expire_commitments(session_id, new_day, new_minute)
        except Exception as e:
            log.warning("Failed processing commitments audit/expiration on sleep for session %s: %s", session_id, e)

    if not freeze_clock:
        try:
            db.clear_temporary_companions(session_id)
        except Exception:
            pass

    if day_rolled_over:
        try:
            from mechanics.world.anomalous_events import process_anomalous_daily_rollover
            process_anomalous_daily_rollover(session_id, new_day, party_uids=party_uids)
        except Exception as e:
            log.warning("Failed anomalous daily rollover on sleep for session %s: %s", session_id, e)
        try:
            from mechanics.narrative.bounty import replenish_daily_bounties_deterministic
            replenish_daily_bounties_deterministic(session_id)
        except Exception as e:
            log.warning("Failed daily bounty replenishment on sleep for session %s: %s", session_id, e)

    if clock_advanced:
        try:
            from mechanics.world.world_events.engine import advance_world_pulse
            raw_sleep_delta = ((new_day - curr_day) * 1440) + (new_minute - curr_min)
            sleep_delta = max(1, raw_sleep_delta) if override_clock_minutes is not None else max(480, raw_sleep_delta)
            advance_world_pulse(
                session_id=session_id,
                delta_minutes=sleep_delta,
                current_day=new_day,
                current_minute=new_minute,
                is_sleep_skip=True,
            )
        except Exception as e:
            log.warning("Failed advancing world pulse on sleep for session %s: %s", session_id, e)

    sleep_clock_tick = None
    if clock_advanced:
        try:
            from mechanics.narrative.threat_clock import tick_threat_clock
            sleep_clock_tick = tick_threat_clock(
                session_id,
                new_day,
                new_minute,
                turn_number=db.get_effective_session_turn(session_id),
            )
        except Exception as e:
            log.warning("Failed ticking Threat Clock on sleep for session %s: %s", session_id, e)

    # Restock all merchant catalogues upon sleeping / morning wake-up (when world advances a day/normal night)
    if day_rolled_over or is_normal_overnight:
        try:
            if session and "merchant" in session:
                merchant = session["merchant"]
                if isinstance(merchant, dict):
                    merchant["catalogues"] = {}
                    merchant["stock"] = []
                    db.save_merchant_state(session_id, merchant)
        except Exception as e:
            log.error("Failed to clear merchant catalogues on sleep for session %s: %s", session_id, e)

    fatigue_effects_cleared = []
    banquet_bonus = {"active": False, "rest_multiplier": 1.0, "buff_name": ""}
    try:
        from mechanics.world.world_events.spirit_realm_events import get_bunian_banquet_rest_bonus
        banquet_bonus = get_bunian_banquet_rest_bonus(session_id, str((session or {}).get("current_node_id") or ""))
    except Exception:
        pass
    eff_recovery_ratio = max(float(recovery_ratio), float(banquet_bonus.get("rest_multiplier") or 1.0)) if banquet_bonus.get("active") else float(recovery_ratio)

    for uid in party_uids:
        try:
            char = db.get_character(uid, session_id=session_id)
            if not char:
                continue
            
            # 1. Restore HP/MP according to recovery_ratio
            max_hp = char.get("max_hp", 100)
            max_mp = char.get("max_mp", 50)
            curr_hp = char.get("hp", max_hp)
            curr_mp = char.get("mp", max_mp)
            new_hp = min(max_hp, int(curr_hp + max_hp * eff_recovery_ratio)) if eff_recovery_ratio < 1.0 else max_hp
            new_mp = min(max_mp, int(curr_mp + max_mp * eff_recovery_ratio)) if eff_recovery_ratio < 1.0 else max_mp
            db.update_character_fields(uid, session_id=session_id, character_id=char.get("id"), hp=new_hp, mp=new_mp)

            # 2. Increment days adventured only when an external day rolls over or normal overnight sleep
            if day_rolled_over or is_normal_overnight:
                db.increment_days_adventured(uid, delta=1, session_id=session_id, character_id=char.get("id"))

            # 3. Clear fatigue, knockout/triage recovery, and intimate status effects (D17)
            raw_status = char.get("status_effects") or "[]"
            status_list = []
            if isinstance(raw_status, str):
                try:
                    status_list = json.loads(raw_status)
                except Exception:
                    status_list = [raw_status]
            elif isinstance(raw_status, list):
                status_list = list(raw_status)

            fatigue_names = {
                "fatigued",
                "exhausted",
                "delirious",
                "sleep deprived",
                "exhausted / recovering",
                "stabilized / triage recovery",
                "refractory",
                "satisfied",
                "aroused",
                "breathless",
                "spent",
            }
            timed_clear_prefixes = ("aroused [", "refractory [", "satisfied [", "breathless [")
            filtered_status = []
            for s in status_list:
                s_str = (s.get("name", "") if isinstance(s, dict) else str(s)).strip()
                s_low = s_str.lower()
                if s_low in fatigue_names or any(s_low.startswith(pfx) for pfx in timed_clear_prefixes):
                    fatigue_effects_cleared.append(s_str)
                else:
                    filtered_status.append(s_str)

            if banquet_bonus.get("active") and banquet_bonus.get("buff_name"):
                b_tag = str(banquet_bonus["buff_name"])
                if b_tag not in filtered_status:
                    filtered_status.append(b_tag)

            if len(filtered_status) != len(status_list) or banquet_bonus.get("active"):
                db.set_status_effects(uid, filtered_status, session_id=session_id, character_id=char.get("id"))

        except Exception as e:
            log.error("Failed to apply sleep rest to user %s: %s", uid, e, exc_info=True)

    # 4. Reset intimate refractory / excitement & restore morning outfits while preserving pockets_emptied (D17)
    try:
        phys_st = db.get_session_physical_state(session_id)
        if isinstance(phys_st, dict):
            preserved_pockets = list(phys_st.get("pockets_emptied") or [])
            phys_st["intimate_contact"] = "none"
            exc = phys_st.get("excitement")
            if isinstance(exc, dict):
                exc["active"] = False
                exc["level"] = 0
                exc["partner_levels"] = {}
                exc["refractory_until_turn"] = 0
                exc["refractory_until_minute"] = None
                exc["player_in_refractory"] = False
                exc["refractory_partners"] = {}
            from mechanics.social.physical_state import restore_equipped_outfit
            party_for_outfit = [
                (c_obj, db.get_inventory(u_id, char=c_obj, session_id=session_id))
                for u_id in party_uids
                if u_id and (c_obj := db.get_character(u_id, session_id=session_id))
            ]
            phys_st = restore_equipped_outfit(phys_st, party_for_outfit, scen_key=eff_scen, session_id=session_id)
            phys_st["pockets_emptied"] = preserved_pockets
            db.update_session_physical_state(session_id, phys_st)
    except Exception as e:
        log.warning("Failed overnight physical/outfit reset for session %s: %s", session_id, e)

    # 5. Morning NPC schedule re-sync (retaining romantic sleepover partners in private rooms) (D17)
    morning_npcs: Optional[List[Dict[str, Any]]] = None
    if day_rolled_over or is_normal_overnight:
        morning_npcs = []
        try:
            fresh_sess = db.get_session(session_id) or session or {}
            curr_loc = str(fresh_sess.get("current_location") or "").strip()
            curr_nid = str(fresh_sess.get("current_node_id") or "").strip()
            prev_npcs = list(fresh_sess.get("current_npcs") or [])
            if curr_loc:
                from mechanics.world.npc_schedule import get_npc_scheduled_location
                from mechanics.world.waypoints import check_location_matches_waypoint

                is_private_room = any(
                    kw in curr_loc.lower()
                    for kw in ("bedroom", "quarters", "suite", "dorm", "cabin", "inn room", "apartment", "home", "house")
                ) or ("bed" in str(surface_label or "").lower())
                if curr_nid:
                    w_node = db.get_world_node(session_id, curr_nid)
                    if w_node and str(w_node.get("privacy_level") or w_node.get("privacy") or "").lower() == "private":
                        is_private_room = True

                contacts = db.get_contacts(session_id) or []
                contact_by_name = {
                    str(c.get("name") or "").strip().lower(): c
                    for c in contacts
                    if isinstance(c, dict) and c.get("name")
                }
                seen_names: set[str] = set()

                for n in prev_npcs:
                    n_dict = dict(n) if isinstance(n, dict) else {"name": str(n)}
                    nm = str(n_dict.get("name") or "").strip()
                    if not nm:
                        continue
                    nm_low = nm.lower()
                    c_row = contact_by_name.get(nm_low)
                    is_perm_comp = bool(n_dict.get("is_companion") and not n_dict.get("is_temporary"))
                    is_romantic_sleepover = bool(
                        is_private_room
                        and c_row
                        and str(c_row.get("track") or "").lower() == "romantic"
                    )
                    sched_loc = get_npc_scheduled_location(
                        c_row or n_dict,
                        current_minute=new_minute,
                        scen_key=eff_scen,
                        session_id=session_id,
                        current_day=new_day,
                    )
                    is_sched_here = bool(
                        sched_loc
                        and (
                            check_location_matches_waypoint(curr_loc, sched_loc)
                            or check_location_matches_waypoint(sched_loc, curr_loc)
                        )
                    )
                    if is_perm_comp or is_romantic_sleepover or is_sched_here:
                        seen_names.add(nm_low)
                        morning_npcs.append(n_dict)

                for c_row in contacts:
                    nm = str(c_row.get("name") or "").strip()
                    if not nm or nm.lower() in seen_names:
                        continue
                    if str(c_row.get("status") or "").lower() in ("dead", "deceased"):
                        continue
                    sched_loc = get_npc_scheduled_location(
                        c_row,
                        current_minute=new_minute,
                        scen_key=eff_scen,
                        session_id=session_id,
                        current_day=new_day,
                    )
                    if sched_loc and (
                        check_location_matches_waypoint(curr_loc, sched_loc)
                        or check_location_matches_waypoint(sched_loc, curr_loc)
                    ):
                        seen_names.add(nm.lower())
                        morning_npcs.append({
                            "name": nm,
                            "role": c_row.get("role") or "Resident",
                            "status_effects": ["Present"],
                        })

                db.update_session(session_id, current_npcs=morning_npcs)
        except Exception as e:
            log.warning("Failed morning NPC schedule re-sync for session %s: %s", session_id, e)

    sleep_boundary_tick = {}
    if clock_advanced:
        try:
            sleep_boundary_tick = run_boundary_autonomy_and_epistemic_tick(
                session_id,
                curr_day,
                curr_min,
                new_day,
                new_minute,
                party_uids=party_uids,
            )
        except Exception as e:
            log.warning("Failed running sleep boundary autonomy/epistemic tick for session %s: %s", session_id, e)

    return {
        "session_id": session_id,
        "new_day": new_day,
        "new_minute": new_minute,
        "clock_display": format_clock(new_minute),
        "day_name": get_day_of_week(new_day),
        "fatigue_cleared": fatigue_effects_cleared,
        "hp_restored": True,
        "mp_restored": True,
        "recovery_ratio": eff_recovery_ratio,
        "banquet_buff_applied": bool(banquet_bonus.get("active")),
        "banquet_buff_name": str(banquet_bonus.get("buff_name") or ""),
        "surface_label": surface_label,
        "morning_npcs": morning_npcs,
        "threat_clock_tick": sleep_clock_tick,
        "boundary_tick": sleep_boundary_tick,
    }


def apply_nap_rest(
    session_id: int,
    party_uids: List[int],
    nap_minutes: int = 120,
    recovery_ratio: float = 1.0,
    surface_label: str = "Bed",
    freeze_clock: bool = False,
    clock_minutes: Optional[int] = None,
) -> Dict[str, Any]:
    """Advances time by eff_clock_mins (or freezes when freeze_clock=True) and restores proportional HP/MP."""
    curr_day, curr_min, _ = db.get_session_time(session_id)
    eff_clock_mins = 0 if freeze_clock else (
        max(0, int(clock_minutes)) if clock_minutes is not None else max(0, int(nap_minutes))
    )
    new_total = curr_min + eff_clock_mins
    new_day = curr_day + (new_total // 1440)
    new_min = new_total % 1440
    if eff_clock_mins > 0:
        db.update_session_time(session_id=session_id, current_day=new_day, current_minute=new_min)

        try:
            from mechanics.system.commitments_engine import audit_and_expire_commitments
            audit_and_expire_commitments(session_id, new_day, new_min)
        except Exception as e:
            log.warning("Failed processing commitments audit/expiration on nap for session %s: %s", session_id, e)

    eff_ratio = (float(nap_minutes) / 480.0) * float(recovery_ratio)
    for uid in party_uids:
        try:
            char = db.get_character(uid, session_id=session_id)
            if not char:
                continue
            max_hp = char.get("max_hp", 100)
            max_mp = char.get("max_mp", 50)
            curr_hp = char.get("hp", max_hp)
            curr_mp = char.get("mp", max_mp)
            add_hp = int(max_hp * eff_ratio)
            add_mp = int(max_mp * eff_ratio)
            db.update_character_fields(
                uid,
                session_id=session_id,
                character_id=char.get("id"),
                hp=min(max_hp, curr_hp + add_hp),
                mp=min(max_mp, curr_mp + add_mp),
            )

            if nap_minutes >= 120:
                raw_status = char.get("status_effects") or "[]"
                status_list = json.loads(raw_status) if isinstance(raw_status, str) else list(raw_status or [])
                status_low = [str(s.get("name") if isinstance(s, dict) else s).lower() for s in status_list]
                if "delirious" in status_low:
                    status_list = [s for s in status_list if str(s.get("name") if isinstance(s, dict) else s).lower() != "delirious"] + ["Exhausted"]
                    db.set_status_effects(uid, status_list, session_id=session_id, character_id=char.get("id"))
                elif "exhausted" in status_low:
                    status_list = [s for s in status_list if str(s.get("name") if isinstance(s, dict) else s).lower() != "exhausted"] + ["Fatigued"]
                    db.set_status_effects(uid, status_list, session_id=session_id, character_id=char.get("id"))
                elif "fatigued" in status_low:
                    status_list = [s for s in status_list if str(s.get("name") if isinstance(s, dict) else s).lower() != "fatigued"]
                    db.set_status_effects(uid, status_list, session_id=session_id, character_id=char.get("id"))
        except Exception as e:
            log.warning("Failed to apply nap rest: %s", e)

    nap_boundary_tick = {}
    if eff_clock_mins > 0:
        try:
            nap_boundary_tick = run_boundary_autonomy_and_epistemic_tick(
                session_id,
                curr_day,
                curr_min,
                new_day,
                new_min,
                party_uids=party_uids,
            )
        except Exception as e:
            log.warning("Failed running nap boundary autonomy/epistemic tick for session %s: %s", session_id, e)

    return {
        "session_id": session_id,
        "new_day": new_day,
        "new_minute": new_min,
        "clock_display": format_clock(new_min),
        "day_name": get_day_of_week(new_day),
        "nap_minutes": nap_minutes,
        "recovery_ratio": recovery_ratio,
        "surface_label": surface_label,
        "boundary_tick": nap_boundary_tick,
    }


def check_and_apply_fatigue(session_id: int, party_uids: List[int]) -> List[str]:
    """
    Checks if party members pulled an all-nighter past 05:00 AM and applies progressive fatigue.
    - Stage 1 (1 night missed): Fatigued (-1 PER, -1 AGI)
    - Stage 2 (2 nights missed): Exhausted (-2 PER, -2 AGI, -2 INT)
    - Stage 3 (3+ nights missed): Delirious (-3 all stats)
    """
    _, curr_min, consecutive_awake = db.get_session_time(session_id)
    if curr_min < 300 and consecutive_awake == 0:
        return []

    applied_notices = []
    
    stage = 1
    if consecutive_awake >= 2:
        stage = 3
    elif consecutive_awake == 1:
        stage = 2

    stage_tags = {
        1: "Fatigued",
        2: "Exhausted",
        3: "Delirious"
    }
    chosen_tag = stage_tags.get(stage, "Fatigued")

    for uid in party_uids:
        try:
            char = db.get_character(uid, session_id=session_id)
            if not char:
                continue
            
            raw_status = char.get("status_effects") or "[]"
            status_list = []
            if isinstance(raw_status, str):
                try:
                    status_list = json.loads(raw_status)
                except Exception:
                    status_list = [raw_status]
            elif isinstance(raw_status, list):
                status_list = list(raw_status)

            # Remove lower tier fatigue effects if upgrading
            fatigue_names = {"fatigued", "exhausted", "delirious", "sleep deprived"}
            filtered_status = [
                (s.get("name", "") if isinstance(s, dict) else str(s)).strip()
                for s in status_list
                if (s.get("name", "") if isinstance(s, dict) else str(s)).strip().lower() not in fatigue_names
            ]
            
            filtered_status.append(chosen_tag)
            db.set_status_effects(uid, filtered_status, session_id=session_id, character_id=char.get("id"))
            applied_notices.append(f"{char['name']} is now **{chosen_tag}**")
        except Exception as e:
            log.warning("Failed to apply fatigue to user %s: %s", uid, e)

    return applied_notices


def format_llm_time_context(
    current_day: int,
    current_minute: int,
    scen_key: str = "fantasy",
    session: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Formats the time block and World Schedule state for injection into the game engine's user_prompt.
    Provides clear context so the narrator renders accurate ambient lighting,
    crowd levels, school/commercial operating hours, and schedule rules.
    """
    day_name = get_day_of_week(current_day)
    clock_str = format_clock(current_minute)
    phase_name, emoji, lighting = get_time_of_day_phase(current_minute)
    
    context_lines = [
        f"IN-GAME TIME & ENVIRONMENT:",
        f"- Current Time: {day_name} (Day {current_day}), {clock_str} [{phase_name} {emoji}]",
        f"- Atmosphere & Lighting: {lighting}.",
    ]
    
    if is_sleep_time(current_minute, scen_key=scen_key):
        context_lines.append(
            f"- Late-Night Flavor: It is late evening / nighttime ({clock_str}). Most shops and facilities are closed, hallways/streets are quiet, and characters feel natural weariness if active."
        )
    else:
        context_lines.append(
            f"- Day Progression: Daytime activities, ambient NPCs, and normal operations are active."
        )

    try:
        from mechanics.world.world_schedule import get_world_schedule_state
        ws_state = get_world_schedule_state(
            scen_key=scen_key,
            current_day=current_day,
            current_minute=current_minute,
            session=session,
            session_id=int((session or {}).get("id") or 0),
        )
        context_lines.append(
            f"- Active World Schedule [{ws_state.get('day_type', 'weekday').capitalize()} — {ws_state.get('period_label', '')}]: {ws_state.get('narrative_directive', '')}"
        )
    except Exception:
        pass

    return "\n".join(context_lines) + "\n"

