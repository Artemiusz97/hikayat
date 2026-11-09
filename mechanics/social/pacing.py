from __future__ import annotations

"""3-Clock Social Pacing Engine for Hikayat.

Manages:
1. Scene-Shared NPC Composure (persists across same-block exits; +50% block recovery; 100% overnight reset;
   Cold Shoulder shield for quest-stationed NPCs; Focus on the Road pause for permanent party companions).
2. Shared Daily Affinity Digestion Cap (+18/day standard, +30/day on scheduled Dates; shared with Phone DMs;
   pierced by Romantic Confessions and 1/day physical Gift).
3. 3-Speed Topic Depletion & Replenishment (24h fail / 48-72h crit_fail lockouts; Depth Tier 1->2->3 gated by
   +1 day AND next Affinity Tier; circadian/venue refresh for situational & banter topics).
"""

from typing import Any

import db
from mechanics.world.schedules import (
    BLOCK_BOUNDARIES,
    get_detailed_npc_time_phase,
    get_time_block_key,
)

DEFAULT_MAX_COMPOSURE: int = 100
DAILY_DIGESTION_CAP_STANDARD: int = 18
DAILY_DIGESTION_CAP_DATE: int = 30

DEPTH_TIER_2_MIN_SCORE: int = 50
DEPTH_TIER_3_MIN_SCORE: int = 100

DEEPENING_TOPIC_CATEGORIES: frozenset[str] = frozenset(
    {"get_to_know", "flirt_chemistry", "callbacks_history", "friction_rivalry"}
)
CIRCADIAN_TOPIC_CATEGORIES: frozenset[str] = frozenset(
    {"friendly_situational", "humor_banter"}
)


def resolve_schedule_block(
    current_minute: int,
    current_day: int = 1,
    scenario: str = "fantasy",
) -> str:
    safe_min = int(current_minute or 0) % 1440
    try:
        return str(get_detailed_npc_time_phase(safe_min, current_day=int(current_day or 1), scen_key=str(scenario or "fantasy")))
    except Exception:
        return str(get_time_block_key(safe_min))


def next_schedule_boundary_minute(current_minute: int) -> tuple[int, int]:
    """Returns (day_offset, boundary_minute) for the next daily block boundary."""
    safe_min = int(current_minute or 0) % 1440
    for b_min, _ in BLOCK_BOUNDARIES:
        if int(b_min) > safe_min:
            return 0, int(b_min)
    return 1, 420


def derive_mood_and_dc_mod(
    current_composure: int,
    max_composure: int = DEFAULT_MAX_COMPOSURE,
    composure_state: str = "composed",
    clear_the_air_required: bool = False,
) -> tuple[str, int]:
    st = str(composure_state or "composed").strip().lower()
    if clear_the_air_required:
        return "Upset", 2
    if st == "cold_shoulder":
        return "Upset", 3
    if st == "walked_away":
        return "Upset", 2
    if st == "focus_on_road":
        return "Drained", 2

    max_c = max(1, int(max_composure or DEFAULT_MAX_COMPOSURE))
    cur_c = max(0, min(max_c, int(current_composure)))
    pct = (cur_c * 100) // max_c
    if pct <= 25:
        return "Drained", 2
    if pct <= 55:
        return "Guarded", 1
    return "Engaged", 0


def is_composure_locked_out(
    comp_row: dict[str, Any] | None,
    current_day: int,
    current_minute: int,
) -> bool:
    if not comp_row:
        return False
    lock_day = int(comp_row.get("lockout_until_day") or 0)
    lock_min = int(comp_row.get("lockout_until_minute") or 0)
    if lock_day <= 0:
        return False
    cur_d = int(current_day or 1)
    cur_m = int(current_minute or 0)
    return (cur_d < lock_day) or (cur_d == lock_day and cur_m < lock_min)


def sync_and_get_composure(
    session_id: int,
    npc_name: str,
    *,
    current_day: int = 1,
    current_minute: int = 480,
    scenario: str = "fantasy",
    max_composure: int = DEFAULT_MAX_COMPOSURE,
    turn_updated: int = 0,
) -> dict[str, Any]:
    """Reads NPC composure and applies deterministic block (+50%) or overnight (100%) recovery."""
    cur_d = int(current_day or 1)
    cur_m = int(current_minute or 0) % 1440
    cur_block = resolve_schedule_block(cur_m, current_day=cur_d, scenario=scenario)
    existing = db.get_npc_social_composure(session_id, npc_name)

    if not existing:
        return db.upsert_npc_social_composure(
            session_id,
            npc_name,
            current_composure=max_composure,
            max_composure=max_composure,
            composure_state="composed",
            mood="Engaged",
            mood_dc_mod=0,
            last_schedule_block=cur_block,
            last_interaction_day=cur_d,
            last_interaction_minute=cur_m,
            lockout_until_day=0,
            lockout_until_minute=0,
            clear_the_air_required=0,
            clear_the_air_reason="",
            turn_updated=turn_updated,
        )

    max_c = max(1, int(existing.get("max_composure") or max_composure))
    cur_c = max(0, min(max_c, int(existing.get("current_composure") if existing.get("current_composure") is not None else max_c)))
    last_d = int(existing.get("last_interaction_day") or cur_d)
    last_m = int(existing.get("last_interaction_minute") or 0)
    last_block = str(existing.get("last_schedule_block") or cur_block)
    state = str(existing.get("composure_state") or "composed")
    clear_req = bool(existing.get("clear_the_air_required"))
    clear_reason = str(existing.get("clear_the_air_reason") or "")
    lock_day = int(existing.get("lockout_until_day") or 0)
    lock_min = int(existing.get("lockout_until_minute") or 0)

    locked = is_composure_locked_out(existing, cur_d, cur_m)
    changed = False

    if cur_d > last_d:
        if not locked:
            cur_c = max_c
            state = "composed"
            lock_day = 0
            lock_min = 0
            changed = True
    elif cur_d == last_d and cur_block != last_block and cur_m > last_m:
        if not locked:
            cur_c = min(max_c, cur_c + (max_c // 2))
            lock_day = 0
            lock_min = 0
            state = "strained" if cur_c <= (max_c // 2) else "composed"
            changed = True
        else:
            changed = True

    mood, dc_mod = derive_mood_and_dc_mod(cur_c, max_c, state, clear_the_air_required=clear_req)
    if (
        changed
        or mood != existing.get("mood")
        or int(existing.get("mood_dc_mod") or 0) != dc_mod
    ):
        return db.upsert_npc_social_composure(
            session_id,
            npc_name,
            current_composure=cur_c,
            max_composure=max_c,
            composure_state=state,
            mood=mood,
            mood_dc_mod=dc_mod,
            last_schedule_block=cur_block,
            last_interaction_day=cur_d,
            last_interaction_minute=cur_m,
            lockout_until_day=lock_day,
            lockout_until_minute=lock_min,
            clear_the_air_required=1 if clear_req else 0,
            clear_the_air_reason=clear_reason,
            turn_updated=int(turn_updated or existing.get("turn_updated") or 0),
        )
    return existing


def compute_turn_composure_delta(
    outcome_tier: str,
    *,
    category: str = "",
    stat: str = "",
    is_bold_or_prying: bool = False,
    is_magic_backfire: bool = False,
) -> int:
    tier = str(outcome_tier or "").strip().lower()
    cat = str(category or "").strip().lower()
    st = str(stat or "").strip().upper()

    if is_magic_backfire:
        return -65
    if tier in ("crit_success", "critical_success"):
        return -10
    if tier in ("success", "partial_success", "mixed_success"):
        return -20 if (is_bold_or_prying or cat in ("flirt_chemistry", "friction_rivalry")) else -15
    if tier in ("crit_fail", "critical_failure"):
        return -50
    if tier in ("fail", "failure"):
        return -20 if st == "CHA" else -28
    return -12


def apply_composure_delta(
    session_id: int,
    npc_name: str,
    *,
    delta: int,
    current_day: int = 1,
    current_minute: int = 480,
    scenario: str = "fantasy",
    outcome_tier: str = "",
    is_quest_stationed_here: bool = False,
    is_party_member: bool = False,
    turn_updated: int = 0,
) -> dict[str, Any]:
    synced = sync_and_get_composure(
        session_id,
        npc_name,
        current_day=current_day,
        current_minute=current_minute,
        scenario=scenario,
        turn_updated=turn_updated,
    )
    max_c = max(1, int(synced.get("max_composure") or DEFAULT_MAX_COMPOSURE))
    prev_c = int(synced.get("current_composure") if synced.get("current_composure") is not None else max_c)
    new_c = max(0, min(max_c, prev_c + int(delta)))

    cur_d = int(current_day or 1)
    cur_m = int(current_minute or 0) % 1440
    cur_block = resolve_schedule_block(cur_m, current_day=cur_d, scenario=scenario)
    tier = str(outcome_tier or "").strip().lower()

    clear_req = bool(synced.get("clear_the_air_required"))
    clear_reason = str(synced.get("clear_the_air_reason") or "")
    lock_day = int(synced.get("lockout_until_day") or 0)
    lock_min = int(synced.get("lockout_until_minute") or 0)

    if new_c <= 0:
        if tier in ("crit_fail", "critical_failure"):
            lock_day = cur_d + 1
            lock_min = 420
            clear_req = True
            clear_reason = clear_reason or "crit_fail_walkaway"
        else:
            d_off, b_min = next_schedule_boundary_minute(cur_m)
            lock_day = cur_d + d_off
            lock_min = b_min

        if is_quest_stationed_here:
            new_state = "cold_shoulder"
        elif is_party_member:
            new_state = "focus_on_road"
        else:
            new_state = "walked_away"
    else:
        new_state = "strained" if new_c <= (max_c // 2) else "composed"

    mood, dc_mod = derive_mood_and_dc_mod(new_c, max_c, new_state, clear_the_air_required=clear_req)
    return db.upsert_npc_social_composure(
        session_id,
        npc_name,
        current_composure=new_c,
        max_composure=max_c,
        composure_state=new_state,
        mood=mood,
        mood_dc_mod=dc_mod,
        last_schedule_block=cur_block,
        last_interaction_day=cur_d,
        last_interaction_minute=cur_m,
        lockout_until_day=lock_day,
        lockout_until_minute=lock_min,
        clear_the_air_required=1 if clear_req else 0,
        clear_the_air_reason=clear_reason,
        turn_updated=int(turn_updated or synced.get("turn_updated") or 0),
    )


def apply_shared_daily_digestion(
    session_id: int,
    character_id: int,
    npc_name: str,
    *,
    raw_delta: int,
    current_day: int = 1,
    is_on_date: bool = False,
    is_gift: bool = False,
    is_confession: bool = False,
    turn_updated: int = 0,
) -> dict[str, Any]:
    """Meters positive affinity gains against the shared +18 (+30 Date) daily digestion cap."""
    cur_d = int(current_day or 1)
    cid = int(character_id or 0)
    existing = db.get_character_social_daily(session_id, cid, npc_name, current_day=cur_d)

    eff_on_date = bool(is_on_date or (existing and existing.get("is_on_date")))
    cap = DAILY_DIGESTION_CAP_DATE if eff_on_date else DAILY_DIGESTION_CAP_STANDARD
    earned = int((existing or {}).get("daily_affinity_earned") or 0)
    gift_used = bool((existing or {}).get("gift_given_today"))
    conf_used = bool((existing or {}).get("confession_given_today"))

    r_val = int(raw_delta or 0)
    if r_val <= 0:
        db.upsert_character_social_daily(
            session_id,
            cid,
            npc_name,
            current_day=cur_d,
            daily_affinity_earned=earned,
            is_on_date=eff_on_date,
            gift_given_today=gift_used,
            confession_given_today=conf_used,
            turn_updated=int(turn_updated or (existing or {}).get("turn_updated") or 0),
        )
        return {
            "applied_delta": r_val,
            "capped": False,
            "pierced": False,
            "daily_earned": earned,
            "daily_cap": cap,
        }

    pierces_cap = bool(is_confession) or (bool(is_gift) and not gift_used)
    new_gift_used = gift_used or bool(is_gift)
    new_conf_used = conf_used or bool(is_confession)

    if pierces_cap:
        applied = r_val
        capped = False
        new_earned = earned
    else:
        headroom = max(0, cap - earned)
        applied = min(r_val, headroom)
        capped = applied < r_val
        new_earned = earned + applied

    db.upsert_character_social_daily(
        session_id,
        cid,
        npc_name,
        current_day=cur_d,
        daily_affinity_earned=new_earned,
        is_on_date=eff_on_date,
        gift_given_today=new_gift_used,
        confession_given_today=new_conf_used,
        turn_updated=int(turn_updated or (existing or {}).get("turn_updated") or 0),
    )
    return {
        "applied_delta": applied,
        "capped": capped,
        "pierced": pierces_cap,
        "daily_earned": new_earned,
        "daily_cap": cap,
    }


def record_topic_resolution(
    session_id: int,
    character_id: int,
    npc_name: str,
    *,
    topic_id: str,
    category: str = "",
    outcome_tier: str = "success",
    current_day: int = 1,
    current_minute: int = 480,
    venue_leaf: str = "",
    turn_updated: int = 0,
) -> dict[str, Any]:
    """Updates per-topic lockout window and Depth Tier 1->2->3 state."""
    cid = int(character_id or 0)
    t_key = str(topic_id or "").strip()
    if not t_key:
        return {}

    cat = str(category or (t_key.split(":", 1)[0] if ":" in t_key else "friendly_situational")).strip().lower()
    tier = str(outcome_tier or "success").strip().lower()
    cur_d = int(current_day or 1)
    cur_m = int(current_minute or 0) % 1440
    now_total = cur_d * 1440 + cur_m

    states = db.get_social_topic_states(session_id, cid, npc_name)
    prev = states.get(t_key)
    prev_depth = int((prev or {}).get("depth_tier") or 1)

    if tier in ("crit_fail", "critical_failure"):
        until_total = now_total + (60 * 60)  # 60h (inside 48-72h lockout window)
        cd_day, cd_min = until_total // 1440, until_total % 1440
        next_depth = prev_depth
    elif tier in ("fail", "failure"):
        until_total = now_total + (24 * 60)  # 24h cooldown
        cd_day, cd_min = until_total // 1440, until_total % 1440
        next_depth = prev_depth
    else:
        if cat in DEEPENING_TOPIC_CATEGORIES:
            next_depth = min(4, prev_depth + 1)
            if next_depth >= 4:
                cd_day, cd_min = cur_d + 7, cur_m
            else:
                cd_day, cd_min = cur_d + 1, 0
        elif cat in CIRCADIAN_TOPIC_CATEGORIES:
            until_total = now_total + (8 * 60)  # ~8h circadian refresh (or earlier if venue changes)
            cd_day, cd_min = until_total // 1440, until_total % 1440
            next_depth = prev_depth
        else:
            until_total = now_total + (24 * 60)
            cd_day, cd_min = until_total // 1440, until_total % 1440
            next_depth = prev_depth

    return db.upsert_social_topic_state(
        session_id,
        cid,
        npc_name,
        t_key,
        category=cat,
        depth_tier=next_depth,
        last_outcome=tier,
        cooldown_until_day=cd_day,
        cooldown_until_minute=cd_min,
        last_venue_leaf=str(venue_leaf or "").strip(),
        turn_updated=turn_updated,
    )


def is_topic_available(
    session_id: int,
    character_id: int,
    npc_name: str,
    topic_id: str,
    *,
    category: str = "",
    current_day: int = 1,
    current_minute: int = 480,
    venue_leaf: str = "",
    relationship_score: int = 0,
    preloaded_states: dict[str, dict[str, Any]] | None = None,
) -> bool:
    """Checks whether a topic_id is currently unlocked and cooled down."""
    t_key = str(topic_id or "").strip()
    if not t_key:
        return True

    states = preloaded_states if preloaded_states is not None else db.get_social_topic_states(session_id, int(character_id or 0), npc_name)
    st = states.get(t_key)
    if not st:
        return True

    cat = str(category or st.get("category") or (t_key.split(":", 1)[0] if ":" in t_key else "")).strip().lower()
    last_out = str(st.get("last_outcome") or "").strip().lower()
    cur_d = int(current_day or 1)
    cur_m = int(current_minute or 0) % 1440
    cd_day = int(st.get("cooldown_until_day") or 0)
    cd_min = int(st.get("cooldown_until_minute") or 0)

    # Venue change refreshes situational / banter topics when not on a fail/crit_fail lockout
    cur_venue = str(venue_leaf or "").strip().lower()
    prev_venue = str(st.get("last_venue_leaf") or "").strip().lower()
    if (
        cat in CIRCADIAN_TOPIC_CATEGORIES
        and last_out not in ("fail", "failure", "crit_fail", "critical_failure")
        and cur_venue
        and prev_venue
        and cur_venue != prev_venue
    ):
        return True

    if cd_day > 0:
        if (cur_d < cd_day) or (cur_d == cd_day and cur_m < cd_min):
            return False

    depth = int(st.get("depth_tier") or 1)
    score = int(relationship_score or 0)
    if cat in DEEPENING_TOPIC_CATEGORIES:
        if depth >= 4:
            return False
        if depth == 2 and score < DEPTH_TIER_2_MIN_SCORE:
            return False
        if depth == 3 and score < DEPTH_TIER_3_MIN_SCORE:
            return False

    return True
