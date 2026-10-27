from __future__ import annotations
"""
Core Stealth & Infiltration Lifecycle Manager.

Manages per-player stealth stances + shared local room detection meters,
executes covert turn actions and anti-spam distractions, handles spatial
suspicion halving/resets and quiet-turn decay, and synthesizes zero-leakage
truth directives for LLM narration.
"""
from typing import Dict, Any, Optional, List, Tuple

from mechanics.stealth.alert_tracker import (
    ALERT_UNAWARE,
    ALERT_SUSPICIOUS,
    ALERT_SEARCHING,
    ALERT_DETECTED,
    get_alert_stage,
    accumulate_detection,
    apply_natural_decay,
    apply_spatial_transition_decay,
    apply_distraction,
    get_alert_badge_data,
)
from mechanics.stealth.formulas import (
    filter_equipped_stealth_items,
    calculate_opposed_stealth_odds,
    resolve_opposed_stealth_check,
    calculate_action_noise,
)

VOLUNTARY_DISENGAGE_REASONS = frozenset({
    "dialogue_init",
    "rest_sleep",
    "manual_disengage",
    "shop_browse",
})

_CIVILIAN_LOCATION_KEYWORDS = (
    "tavern", "inn", "market", "bazaar", "shop", "store", "boutique", "bakery",
    "cafe", "coffee", "plaza", "town square", "village", "residential", "bedroom",
    "living room", "kitchen", "classroom", "hallway", "cafeteria", "library",
    "infirmary", "clinic", "hospital", "guildhall", "lobby", "park", "station",
)

_HOSTILE_RESTRICTED_KEYWORDS = (
    "dungeon", "crypt", "vault", "stronghold", "fortress", "citadel", "lair",
    "den", "bandit", "cult", "syndicate", "armory", "sanctum", "ruins", "sewer",
    "catacomb", "laboratory", "black site", "restricted", "bunker", "incursion",
    "anomaly", "rift", "prison", "cellblock", "watchtower", "barracks",
)


def init_stealth_state(is_hidden: bool = True, user_id: Optional[int] = None) -> Dict[str, Any]:
    """Creates a new canonical stealth_state dictionary."""
    actors: Dict[str, Dict[str, bool]] = {}
    if user_id is not None:
        actors[str(user_id)] = {
            "is_hidden": bool(is_hidden),
            "combat_vanished": False,
        }
    return {
        "is_hidden": bool(is_hidden),
        "alert_level": ALERT_UNAWARE,
        "detection_meter": 0,
        "noise_level": 0,
        "last_alert_cause": None,
        "alert_event": None,
        "unpatrolled_turns": 0,
        "combat_vanished": False,
        "actors": actors,
        "anchor_node_id": None,
        "anchor_facility_id": None,
        "free_distraction_used": False,
    }


def _normalize_stealth_state(st: Dict[str, Any]) -> Dict[str, Any]:
    """Ensures all canonical keys exist on an existing or legacy stealth_state dict."""
    st.setdefault("is_hidden", False)
    st["detection_meter"] = max(0, min(100, int(st.get("detection_meter", 0) or 0)))
    st["alert_level"] = st.get("alert_level") or get_alert_stage(st["detection_meter"])
    st.setdefault("noise_level", 0)
    st.setdefault("last_alert_cause", None)
    st.setdefault("alert_event", None)
    st.setdefault("unpatrolled_turns", 0)
    st.setdefault("combat_vanished", False)
    if not isinstance(st.get("actors"), dict):
        st["actors"] = {}
    st.setdefault("anchor_node_id", None)
    st.setdefault("anchor_facility_id", None)
    st.setdefault("free_distraction_used", False)
    return st


def get_session_stealth_state(session: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Retrieve or initialize the persistent stealth_state from a session."""
    if not isinstance(session, dict):
        return init_stealth_state(False)

    st = session.get("stealth_state")
    if not isinstance(st, dict):
        st = init_stealth_state(False)
        session["stealth_state"] = st
    else:
        _normalize_stealth_state(st)
    return st


def set_session_stealth_state(session: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    """Update and normalize the session's in-memory stealth_state."""
    norm = _normalize_stealth_state(dict(state))
    if isinstance(session, dict):
        session["stealth_state"] = norm
    return norm


def _ensure_actor_entry(st: Dict[str, Any], user_id: int) -> Dict[str, bool]:
    """Gets or initializes a per-player stance entry inside st['actors']."""
    actors = st.setdefault("actors", {})
    uid_key = str(user_id)
    if uid_key not in actors or not isinstance(actors[uid_key], dict):
        if not actors:
            actors[uid_key] = {
                "is_hidden": bool(st.get("is_hidden", False)),
                "combat_vanished": bool(st.get("combat_vanished", False)),
            }
        else:
            actors[uid_key] = {
                "is_hidden": False,
                "combat_vanished": False,
            }
    return actors[uid_key]


def _recompute_top_level_flags(st: Dict[str, Any]) -> None:
    """Keeps top-level summary booleans synced with the actors map when populated."""
    actors = st.get("actors")
    if isinstance(actors, dict) and actors:
        st["is_hidden"] = any(bool(a.get("is_hidden")) for a in actors.values() if isinstance(a, dict))
        st["combat_vanished"] = any(bool(a.get("combat_vanished")) for a in actors.values() if isinstance(a, dict))


def is_actor_hidden(session: Optional[Dict[str, Any]], user_id: Optional[int] = None) -> bool:
    """Returns whether the specific user (or the session in solo mode) is currently in stealth stance."""
    st = get_session_stealth_state(session)
    actors = st.get("actors") or {}
    if user_id is not None and isinstance(actors, dict) and actors:
        uid_key = str(user_id)
        if uid_key in actors and isinstance(actors[uid_key], dict):
            return bool(actors[uid_key].get("is_hidden", False))
        return False
    return bool(st.get("is_hidden", False))


def is_actor_combat_vanished(session: Optional[Dict[str, Any]], user_id: Optional[int] = None) -> bool:
    """Returns whether the specific user (or the session in solo mode) is currently vanished in combat."""
    st = get_session_stealth_state(session)
    actors = st.get("actors") or {}
    if user_id is not None and isinstance(actors, dict) and actors:
        uid_key = str(user_id)
        if uid_key in actors and isinstance(actors[uid_key], dict):
            return bool(actors[uid_key].get("combat_vanished", False))
        return False
    return bool(st.get("combat_vanished", False))


def any_actor_hidden(session: Optional[Dict[str, Any]]) -> bool:
    """Returns True if at least one player in the session is currently in stealth stance."""
    st = get_session_stealth_state(session)
    actors = st.get("actors") or {}
    if isinstance(actors, dict) and actors:
        return any(bool(a.get("is_hidden")) for a in actors.values() if isinstance(a, dict))
    return bool(st.get("is_hidden", False))


def set_actor_combat_vanished(
    session: Dict[str, Any],
    vanished: bool,
    user_id: Optional[int] = None,
    also_set_hidden: Optional[bool] = None,
) -> Dict[str, Any]:
    """Sets or clears combat_vanished scoped to user_id (and syncs top-level summary)."""
    st = get_session_stealth_state(session)
    if user_id is not None:
        entry = _ensure_actor_entry(st, user_id)
        entry["combat_vanished"] = bool(vanished)
        if also_set_hidden is not None:
            entry["is_hidden"] = bool(also_set_hidden)
        elif vanished:
            entry["is_hidden"] = True
        _recompute_top_level_flags(st)
    else:
        st["combat_vanished"] = bool(vanished)
        if also_set_hidden is not None:
            st["is_hidden"] = bool(also_set_hidden)
        elif vanished:
            st["is_hidden"] = True
        for a in (st.get("actors") or {}).values():
            if isinstance(a, dict) and not vanished:
                a["combat_vanished"] = False
    return set_session_stealth_state(session, st)


def clear_all_combat_vanished(session: Dict[str, Any]) -> Dict[str, Any]:
    """Clears combat_vanished across all actors when a combat encounter ends."""
    st = get_session_stealth_state(session)
    st["combat_vanished"] = False
    for a in (st.get("actors") or {}).values():
        if isinstance(a, dict):
            a["combat_vanished"] = False
    return set_session_stealth_state(session, st)


def project_stealth_state_for_user(session: Optional[Dict[str, Any]], user_id: Optional[int] = None) -> Dict[str, Any]:
    """Returns a client-facing copy of stealth_state with is_hidden/combat_vanished projected for user_id."""
    st = dict(get_session_stealth_state(session))
    st["actors"] = {k: dict(v) for k, v in (st.get("actors") or {}).items() if isinstance(v, dict)}
    if user_id is not None and st["actors"]:
        st["is_hidden"] = is_actor_hidden(session, user_id)
        st["combat_vanished"] = is_actor_combat_vanished(session, user_id)
    return st


def toggle_stealth_stance(
    session: Dict[str, Any],
    active: bool,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Toggles the persistent covert stance ON or OFF (scoped per user_id in co-op).
    Clears stale alert causes so normal turns are never poisoned.
    """
    st = get_session_stealth_state(session)
    if user_id is not None:
        entry = _ensure_actor_entry(st, user_id)
        entry["is_hidden"] = bool(active)
        if not active:
            entry["combat_vanished"] = False
        _recompute_top_level_flags(st)
    else:
        st["is_hidden"] = bool(active)
        for a in (st.get("actors") or {}).values():
            if isinstance(a, dict):
                a["is_hidden"] = bool(active)
                if not active:
                    a["combat_vanished"] = False
        if not active:
            st["combat_vanished"] = False

    if not st["is_hidden"]:
        st["unpatrolled_turns"] = 0
    st["last_alert_cause"] = None
    st["alert_event"] = None
    return set_session_stealth_state(session, st)


def break_stealth(
    session: Dict[str, Any],
    reason: str = "detected",
    user_id: Optional[int] = None,
    break_all: bool = False,
) -> Dict[str, Any]:
    """
    Breaks cover immediately.
    - When user_id is provided and break_all is False, only that player's cover breaks,
      preserving covert positioning for hidden co-op teammates.
    - Voluntary disengagements (dialogue_init, rest_sleep) do not set hostile sentry alert_event.
    """
    st = get_session_stealth_state(session)
    reason_str = str(reason or "detected")

    if user_id is not None and not break_all:
        entry = _ensure_actor_entry(st, user_id)
        entry["is_hidden"] = False
        entry["combat_vanished"] = False
        _recompute_top_level_flags(st)
    else:
        st["is_hidden"] = False
        st["combat_vanished"] = False
        for a in (st.get("actors") or {}).values():
            if isinstance(a, dict):
                a["is_hidden"] = False
                a["combat_vanished"] = False

    st["last_alert_cause"] = reason_str
    if reason_str in VOLUNTARY_DISENGAGE_REASONS:
        st["alert_event"] = None
    else:
        st["alert_event"] = reason_str
    return set_session_stealth_state(session, st)


def consume_stealth_turn_transients(session: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clears single-turn transient alert_event / last_alert_cause after turn narration
    is generated so old cover-break directives never bleed into future normal turns.
    """
    st = get_session_stealth_state(session)
    st["alert_event"] = None
    if not st.get("is_hidden"):
        st["last_alert_cause"] = None
        if st.get("detection_meter", 0) >= 100:
            st["detection_meter"] = 0
            st["alert_level"] = ALERT_UNAWARE
            st["free_distraction_used"] = False
    return set_session_stealth_state(session, st)


def apply_stealth_decay_turn(
    session: Dict[str, Any],
    is_waiting_still: bool = False,
) -> Dict[str, Any]:
    """
    Applies natural passive decay over a quiet turn (-10% standard, -15% if waiting/blending still).
    """
    st = get_session_stealth_state(session)
    if not any_actor_hidden(session):
        return st

    turns = int(st.get("unpatrolled_turns", 0) or 0) + 1
    st["unpatrolled_turns"] = turns

    step = 15 if is_waiting_still else 10
    new_meter, new_stage = apply_natural_decay(st.get("detection_meter", 0), quiet_turns=1, per_turn_decay=step)
    st["detection_meter"] = new_meter
    st["alert_level"] = new_stage
    if new_meter == 0:
        st["free_distraction_used"] = False
    return set_session_stealth_state(session, st)


def _resolve_node_facility_key(session_id: Optional[int], node_id: Optional[str], location_str: str = "") -> Tuple[str, str]:
    """Returns (room_or_node_key, facility_or_zone_key) for spatial suspicion transitions."""
    nid = str(node_id or "").strip()
    if session_id and nid:
        try:
            import db
            node = db.get_world_node(int(session_id), nid)
            if isinstance(node, dict):
                ntype = str(node.get("node_type") or "").upper()
                parent_id = str(node.get("parent_id") or "").strip()
                if ntype == "ROOM" and parent_id:
                    return nid, parent_id
                return nid, nid
        except Exception:
            pass

    loc = str(location_str or "").strip()
    if loc:
        parts = [p.strip().lower() for p in loc.replace("->", "➔").replace("•", "➔").split("➔") if p.strip()]
        if len(parts) >= 2:
            return parts[-1], "::".join(parts[:2]) if len(parts) >= 3 else parts[0]
        if len(parts) == 1:
            return parts[0], parts[0]
    return nid, nid


def apply_stealth_spatial_transition(
    session: Dict[str, Any],
    prev_node_id: Optional[str] = None,
    new_node_id: Optional[str] = None,
    prev_location: str = "",
    new_location: str = "",
) -> Dict[str, Any]:
    """
    Applies spatial suspicion rules when the party moves:
    - Leaving a facility/zone resets detection_meter to 0%.
    - Moving to an adjacent room inside the same facility halves detection_meter (// 2).
    """
    st = get_session_stealth_state(session)
    sid = session.get("id") if isinstance(session, dict) else None

    old_room, old_fac = _resolve_node_facility_key(sid, prev_node_id or st.get("anchor_node_id"), prev_location)
    new_room, new_fac = _resolve_node_facility_key(sid, new_node_id, new_location)

    if not new_room and not new_fac:
        return st

    st["anchor_node_id"] = new_node_id or new_room
    st["anchor_facility_id"] = new_fac

    if not old_room and not old_fac:
        return set_session_stealth_state(session, st)

    if old_room == new_room and old_fac == new_fac:
        return set_session_stealth_state(session, st)

    same_facility = bool(old_fac and new_fac and old_fac == new_fac)
    new_meter, new_stage = apply_spatial_transition_decay(st.get("detection_meter", 0), same_facility=same_facility)
    st["detection_meter"] = new_meter
    st["alert_level"] = new_stage
    st["free_distraction_used"] = False
    st["unpatrolled_turns"] = 0
    return set_session_stealth_state(session, st)


def apply_stealth_distraction(session: Dict[str, Any], reduction: int = 30) -> Dict[str, Any]:
    """
    Applies a direct active distraction reduction (e.g. first free pebble throw in a room/cycle).
    """
    st = get_session_stealth_state(session)
    new_meter, new_stage = apply_distraction(st.get("detection_meter", 0), reduction=reduction)
    st["detection_meter"] = new_meter
    st["alert_level"] = new_stage
    st["last_alert_cause"] = "distraction_deployed"
    st["alert_event"] = "distraction_deployed"
    st["free_distraction_used"] = True
    if new_meter == 0:
        st["free_distraction_used"] = False
    return set_session_stealth_state(session, st)


def resolve_distraction_action(
    session: Dict[str, Any],
    actor_char: Dict[str, Any],
    equipped_items: Optional[List[Dict[str, Any]]] = None,
    current_minute: Optional[int] = None,
    party: Optional[List[Any]] = None,
    environment: str = "",
    check_mode: str = "off",
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Resolves a distraction action with anti-spam protection:
    - First distraction per room/alert cycle reliably sheds -30% roll-free.
    - Repeat distractions in the same cycle require a contested trick check (-25% on success, +15%/+25% backfire on failure).
    """
    from skill_check import CheckResult
    st = get_session_stealth_state(session)
    eff_uid = user_id if user_id is not None else actor_char.get("user_id")

    if not st.get("free_distraction_used", False):
        apply_stealth_distraction(session, reduction=30)
        st = get_session_stealth_state(session)
        free_res = CheckResult(
            chance=100,
            roll=50.0,
            tier="success",
            tier_label="Success",
            succeeded=True,
            requirement=0,
        )
        return {
            "check": free_res,
            "was_free_distraction": True,
            "stealth_state": dict(st),
            "alert_badge": get_alert_badge_data(st["detection_meter"], is_hidden=is_actor_hidden(session, eff_uid)),
            "trigger_combat": False,
            "trigger_confrontation": False,
        }

    target_per = resolve_scene_target_per(session)
    actor_stats = actor_char.get("stats") or actor_char
    luck = int(actor_stats.get("LUK", actor_stats.get("luk", 3)) or 3)
    check_res, odds = resolve_opposed_stealth_check(
        actor_stats=actor_stats,
        target_per=target_per,
        equipped_items=equipped_items,
        current_minute=current_minute,
        party=party,
        alert_stage=st.get("alert_level", ALERT_UNAWARE),
        is_invisible=False,
        environment=environment,
        action_noise=0,
        luck=luck,
        check_mode=check_mode,
        dc_modifier=2,
    )

    if check_res.succeeded:
        red = 30 if check_res.tier == "crit_success" else 25
        new_meter, new_stage = apply_distraction(st.get("detection_meter", 0), reduction=red)
        st["detection_meter"] = new_meter
        st["alert_level"] = new_stage
        st["last_alert_cause"] = "distraction_deployed"
        st["alert_event"] = "distraction_deployed"
    else:
        backfire = 25 if check_res.tier in ("crit_fail", "critical_failure") else 15
        new_meter = min(100, int(st.get("detection_meter", 0) or 0) + backfire)
        new_stage = get_alert_stage(new_meter)
        st["detection_meter"] = new_meter
        st["alert_level"] = new_stage
        st["last_alert_cause"] = "distraction_backfired"
        st["alert_event"] = "distraction_backfired"

    trigger_combat = False
    trigger_confrontation = False
    if st["detection_meter"] >= 100 or st["alert_level"] == ALERT_DETECTED:
        break_stealth(session, reason="detected_at_100_percent", user_id=eff_uid)
        st = get_session_stealth_state(session)
        trigger_combat, trigger_confrontation = classify_detection_escalation(session)
    else:
        set_session_stealth_state(session, st)

    return {
        "check": check_res,
        "odds": odds,
        "was_free_distraction": False,
        "stealth_state": dict(st),
        "alert_badge": get_alert_badge_data(st["detection_meter"], is_hidden=is_actor_hidden(session, eff_uid)),
        "trigger_combat": trigger_combat,
        "trigger_confrontation": trigger_confrontation,
    }


def resolve_scene_target_per(
    session: Optional[Dict[str, Any]],
    target_entity: Optional[Dict[str, Any]] = None,
    target_name: str = "",
) -> int:
    """
    Deterministically resolves the opposing sentry/NPC Perception stat from target_entity,
    nearby_enemies, current_npcs, or restricted node security tier.
    """
    if isinstance(target_entity, dict):
        t_stats = target_entity.get("stats") if isinstance(target_entity.get("stats"), dict) else target_entity
        for k in ("PER", "per", "per_"):
            if k in t_stats and t_stats[k] is not None:
                try:
                    return max(1, int(t_stats[k]))
                except (TypeError, ValueError):
                    pass

    if not isinstance(session, dict):
        return 3

    t_low = str(target_name or (target_entity.get("name") if isinstance(target_entity, dict) else "") or "").strip().lower()

    enemies = [e for e in (session.get("nearby_enemies") or session.get("monsters") or []) if isinstance(e, dict) and int(e.get("hp", 1) or 0) > 0]
    if t_low:
        matched_e = next((e for e in enemies if t_low in str(e.get("name") or "").lower() or str(e.get("name") or "").lower() in t_low), None)
        if matched_e:
            e_stats = matched_e.get("stats") if isinstance(matched_e.get("stats"), dict) else matched_e
            return max(1, int(e_stats.get("PER", e_stats.get("per", e_stats.get("per_", 4))) or 4))

    if enemies:
        best_per = 3
        for e in enemies:
            e_stats = e.get("stats") if isinstance(e.get("stats"), dict) else e
            val = int(e_stats.get("PER", e_stats.get("per", e_stats.get("per_", 3))) or 3)
            if val > best_per:
                best_per = val
        return best_per

    npcs = [n for n in (session.get("current_npcs") or []) if isinstance(n, dict)]
    if t_low:
        matched_n = next((n for n in npcs if t_low in str(n.get("name") or "").lower() or str(n.get("name") or "").lower() in t_low), None)
        if matched_n:
            n_stats = matched_n.get("stats") if isinstance(matched_n.get("stats"), dict) else matched_n
            for k in ("PER", "per", "per_"):
                if k in n_stats and n_stats[k] is not None:
                    return max(1, int(n_stats[k]))
            role_txt = str(matched_n.get("role") or matched_n.get("occupation") or "").lower()
            if any(w in role_txt for w in ("guard", "sentry", "captain", "warden", "detective", "security", "officer", "assassin", "scout", "ranger", "teacher", "prefect")):
                return 5
            return 3

    for n in npcs:
        role_txt = str(n.get("role") or n.get("occupation") or "").lower()
        if any(w in role_txt for w in ("guard", "sentry", "captain", "warden", "security", "officer", "watchman", "patrol", "prefect", "hall monitor")):
            return 5

    loc_low = str(session.get("current_location") or "").lower()
    w_node = session.get("current_world_node") if isinstance(session.get("current_world_node"), dict) else {}
    tier_low = str(w_node.get("access_tier") or "").lower()
    if tier_low in ("restricted", "locked", "private") or any(k in loc_low for k in _HOSTILE_RESTRICTED_KEYWORDS):
        return 4

    return 3


def resolve_scene_environment_context(session: Optional[Dict[str, Any]], explicit_env: str = "") -> str:
    """Combines explicit environment hints with session weather, location, and focal_point."""
    if explicit_env:
        return explicit_env
    if not isinstance(session, dict):
        return ""
    parts = [
        str(session.get("weather") or ""),
        str(session.get("environment") or ""),
        str(session.get("current_location") or ""),
        str(session.get("focal_point") or ""),
    ]
    return " ".join(p for p in parts if p).strip()


def classify_detection_escalation(session: Optional[Dict[str, Any]]) -> Tuple[bool, bool]:
    """
    Context-aware 100% detection escalation (User Decision A2):
    Returns (trigger_combat, trigger_confrontation).
    - Non-combat scenarios -> always confrontation (False, True).
    - Combat scenarios -> immediate combat (True, False) if living hostiles are present
      or inside a hostile/restricted dungeon/vault (or unspecified infiltration zone);
      active guard/bystander confrontation first (False, True) in neutral civilian settlements.
    """
    if not isinstance(session, dict):
        return True, False

    from scenario_data import is_non_combat_scenario
    scen = str(session.get("scenario") or "fantasy").strip().lower()
    if is_non_combat_scenario(scen) or scen in ("high_school_drama", "highschool", "slice_of_life"):
        return False, True

    enemies = [e for e in (session.get("nearby_enemies") or session.get("monsters") or []) if isinstance(e, dict) and int(e.get("hp", 1) or 0) > 0]
    if enemies:
        return True, False

    loc_low = str(session.get("current_location") or "").lower()
    focal_low = str(session.get("focal_point") or "").lower()
    combined_loc = f"{loc_low} {focal_low}".strip()
    w_node = session.get("current_world_node") if isinstance(session.get("current_world_node"), dict) else {}
    tier_low = str(w_node.get("access_tier") or "").lower()

    if tier_low == "restricted" or any(k in combined_loc for k in _HOSTILE_RESTRICTED_KEYWORDS):
        return True, False

    if combined_loc and any(k in combined_loc for k in _CIVILIAN_LOCATION_KEYWORDS):
        return False, True

    return True, False


def compute_choice_stealth_odds(
    session: Optional[Dict[str, Any]],
    actor_char: Optional[Dict[str, Any]],
    choice: Dict[str, Any],
    equipped_items: Optional[List[Dict[str, Any]]] = None,
    party: Optional[List[Any]] = None,
    user_id: Optional[int] = None,
) -> Optional[int]:
    """
    Computes unified opposed stealth success_pct for UI choice enrichment (Web & Discord)
    when the choice is a covert action or the actor is actively sneaking outside combat.
    Returns None if standard stat-vs-DC odds should be used instead.
    """
    if not isinstance(actor_char, dict) or not isinstance(choice, dict):
        return None
    if isinstance(session, dict):
        from mechanics.combat import is_in_combat
        if is_in_combat(session):
            return None

    stat = str(choice.get("stat") or "").upper()
    req = int(choice.get("requirement", 0) or 0)
    if stat in ("NONE", "FREE", "ITEM") or req <= 0:
        return None

    lbl_low = str(choice.get("label") or "").lower()
    intent_low = str(choice.get("intent") or choice.get("action_category") or "").lower()
    if any(w in lbl_low for w in ("distract", "diversion", "throw a stone", "throw stone", "pebble", "freeze & blend", "hold still")):
        st_chk = get_session_stealth_state(session)
        if not st_chk.get("free_distraction_used", False) and any(w in lbl_low for w in ("distract", "diversion", "stone", "pebble")):
            return 100

    eff_uid = user_id if user_id is not None else actor_char.get("user_id")
    hidden_now = is_actor_hidden(session, eff_uid) or bool(choice.get("is_stealth")) or choice.get("stance") == "stealth"
    is_covert_choice = (
        intent_low in ("stealth_covert", "stealth")
        or any(w in lbl_low for w in ("sneak", "stealth", "creep", "infiltrate", "pickpocket", "shadow step", "silent takedown", "slip past", "pick the lock", "lockpick"))
    )
    if not (is_covert_choice or (hidden_now and stat == "AGI" and not any(w in lbl_low for w in ("flee", "sprint", "dodge", "chase")))):
        return None

    st = get_session_stealth_state(session)
    target_per = resolve_scene_target_per(session, target_name=str(choice.get("target_npc") or choice.get("target_entity") or ""))
    curr_min = session.get("current_minute") if isinstance(session, dict) else None
    env = resolve_scene_environment_context(session)
    status_effects = actor_char.get("status_effects") or []
    is_invisible = any("invisib" in str(eff).lower() or "optical_camo" in str(eff).lower() for eff in status_effects)
    action_noise = calculate_action_noise(choice.get("action_type", ""), lbl_low)

    odds = calculate_opposed_stealth_odds(
        actor_stats=actor_char.get("stats") or actor_char,
        target_per=target_per,
        equipped_items=filter_equipped_stealth_items(equipped_items),
        current_minute=curr_min,
        party=party,
        alert_stage=st.get("alert_level", ALERT_UNAWARE),
        is_invisible=is_invisible,
        environment=env,
        action_noise=action_noise,
    )
    return int(odds["success_chance"])


def resolve_stealth_action(
    session: Dict[str, Any],
    actor_char: Dict[str, Any],
    action_data: Dict[str, Any],
    target_entity: Optional[Dict[str, Any]] = None,
    party: Optional[List[Any]] = None,
    equipped_items: Optional[List[Dict[str, Any]]] = None,
    current_minute: Optional[int] = None,
    environment: str = "",
    check_mode: str = "off",
    dc_modifier: int = 0,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Executes a covert action within a session, deterministically computing
    opposed check odds, resolving rolls, adjusting detection meter,
    and evaluating context-aware 100% escalation.
    """
    st = get_session_stealth_state(session)
    eff_uid = user_id if user_id is not None else actor_char.get("user_id")
    actor_stats = actor_char.get("stats") or actor_char

    target_name = str(
        action_data.get("target_npc")
        or action_data.get("target_entity")
        or (target_entity.get("name") if isinstance(target_entity, dict) else "")
        or ""
    )
    target_per = resolve_scene_target_per(session, target_entity=target_entity, target_name=target_name)
    eff_env = resolve_scene_environment_context(session, explicit_env=environment)

    action_label = str(action_data.get("label") or action_data.get("custom_action_text") or "")
    action_noise = calculate_action_noise(action_data.get("action_type", ""), action_label)

    status_effects = actor_char.get("status_effects") or []
    is_invisible = any("invisib" in str(eff).lower() or "optical_camo" in str(eff).lower() for eff in status_effects)

    current_stage = st.get("alert_level", ALERT_UNAWARE)
    luck = int(actor_stats.get("LUK", actor_stats.get("luk", 3)) or 3)

    check_res, odds = resolve_opposed_stealth_check(
        actor_stats=actor_stats,
        target_per=target_per,
        equipped_items=filter_equipped_stealth_items(equipped_items),
        current_minute=current_minute,
        party=party,
        alert_stage=current_stage,
        is_invisible=is_invisible,
        environment=eff_env,
        action_noise=action_noise,
        luck=luck,
        check_mode=check_mode,
        dc_modifier=dc_modifier,
    )

    new_meter, new_stage = accumulate_detection(
        current_meter=st.get("detection_meter", 0),
        check_tier=check_res.tier,
        margin=abs(odds["diff"]) / 10.0 if not check_res.succeeded else 0.0,
        action_noise=action_noise,
    )

    st["detection_meter"] = new_meter
    st["alert_level"] = new_stage
    st["noise_level"] = action_noise
    if check_res.succeeded:
        st["alert_event"] = None
    else:
        st["unpatrolled_turns"] = 0
        st["alert_event"] = "suspicion_raised"

    trigger_combat = False
    trigger_confrontation = False

    if new_stage == ALERT_DETECTED or new_meter >= 100:
        break_stealth(session, reason="detected_at_100_percent", user_id=eff_uid)
        st = get_session_stealth_state(session)
        trigger_combat, trigger_confrontation = classify_detection_escalation(session)
    else:
        set_session_stealth_state(session, st)

    hidden_for_actor = is_actor_hidden(session, eff_uid)
    badge = get_alert_badge_data(new_meter, is_hidden=hidden_for_actor)

    return {
        "check": check_res,
        "odds": odds,
        "stealth_state": dict(st),
        "alert_badge": badge,
        "trigger_combat": trigger_combat,
        "trigger_confrontation": trigger_confrontation,
        "directive": format_stealth_truth_directive(session, st, user_id=eff_uid),
    }


def format_stealth_truth_directive(
    session: Dict[str, Any],
    state: Optional[Dict[str, Any]] = None,
    user_id: Optional[int] = None,
) -> str:
    """
    Synthesizes an immutable prompt directive enforcing covert rules for narration
    while strictly forbidding raw meter/percentage stat leakage in prose.
    """
    st = state if isinstance(state, dict) else get_session_stealth_state(session)
    is_hidden = is_actor_hidden(session, user_id) if (user_id is not None and isinstance(session, dict)) else bool(st.get("is_hidden", False))
    stage = str(st.get("alert_level", ALERT_UNAWARE) or ALERT_UNAWARE).upper()
    meter = int(st.get("detection_meter", 0) or 0)

    if not is_hidden:
        cause = st.get("alert_event") or st.get("last_alert_cause")
        if cause and str(cause) not in VOLUNTARY_DISENGAGE_REASONS:
            human_cause = str(cause).replace("_", " ")
            return (
                f"\n[MANDATORY STEALTH DIRECTIVE]: PLAYER COVER WAS JUST BROKEN ({human_cause}). "
                f"Sentries or bystanders have spotted the actor. Narrate immediate open confrontation, reaction, or inquiry. "
                f"NEVER mention raw percentages, meter numbers, or internal code tags in narrative prose.\n"
            )
        return ""

    if stage == "UNAWARE":
        stage_desc = "Sentries maintain relaxed, routine duties and have no suspicion."
        tension_desc = "minimal"
    elif stage == "SUSPICIOUS":
        stage_desc = "A nearby guard heard a subtle sound or saw a shifting shadow and is pausing to inspect the area, WITHOUT seeing who caused it."
        tension_desc = "rising" if meter < 45 else "tense"
    elif stage == "SEARCHING":
        stage_desc = "Guards are actively searching with lanterns, weapons drawn, or sweeping scanners, WITHOUT yet locking eyes on the hidden actor."
        tension_desc = "high" if meter < 85 else "razor-thin"
    else:
        stage_desc = "Guards are fully alerted and searching aggressively."
        tension_desc = "critical"

    return (
        f"\n[MANDATORY STEALTH & CONCEALMENT DIRECTIVE]:\n"
        f"- Covert Stance: ACTIVE (actor concealed in shadow/cover).\n"
        f"- Alert Stage: {stage} (suspicion tension: {tension_desc}).\n"
        f"- Sentry Awareness: {stage_desc}\n"
        f"- TRUTH RULE: The actor remains UNSEEN in shadow/cover. Sentries have NOT visually identified the actor yet. "
        f"Do NOT narrate casual open conversation, walking in plain sight, or sentries addressing the hidden actor face-to-face.\n"
        f"- PROSE GUARDRAIL: NEVER mention raw detection numbers, percentages, stage enums, or internal flags in player-facing prose.\n"
    )
