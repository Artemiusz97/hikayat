from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import db

from .constants import (
    AFFINITY_LOYALTY_CONVERSION_BONUS,
    NPC_DEFAULT_AWARENESS_RATE,
    PLAYER_SCANDAL_COOLDOWN_DAYS,
    SCANDAL_INVESTIGATION_HOURS,
    WITNESS_CATCH_VIRALITY_THRESHOLD,
    WITNESS_CATCH_WINDOW_DAYS,
)
from .formatting import resolve_session_time_and_turn

_KIN_AND_PARTNER_TOKENS = (
    "spouse", "wife", "husband", "partner", "lover", "fiance", "fiancee",
    "mother", "father", "mom", "dad", "parent", "sister", "brother",
    "sibling", "daughter", "son", "child", "cousin", "aunt", "uncle", "kin",
)

_WATCH_ROLE_TOKENS = (
    "student council", "disciplinary", "journalism", "newspaper",
    "custodian", "janitor", "teacher", "faculty", "dispatch",
    "security", "agent", "operative", "officer", "inspector", "monitor",
)


def is_npc_aware_of_event(
    session_id: int,
    event_key: str,
    npc_id: str,
    spread_rate: float = NPC_DEFAULT_AWARENESS_RATE,
) -> bool:
    """Deterministic sha256 awareness roll so an NPC consistently knows or does not know an event/rumor."""
    rate = float(spread_rate)
    if rate <= 0.0:
        return False
    if rate >= 1.0:
        return True
    norm_npc = str(npc_id or "").strip().lower().replace(" ", "_")
    seed_bytes = f"{int(session_id)}:{str(event_key).strip()}:{norm_npc}".encode("utf-8")
    digest = hashlib.sha256(seed_bytes).digest()
    bucket = int.from_bytes(digest[:4], "big") / float(0xFFFFFFFF)
    return bucket < rate


def is_npc_aware_of_minor_event(
    session_id: int,
    event: dict[str, Any] | str,
    npc_id: str,
    npc_profile: dict[str, Any] | str | None = None,
    current_location: str = "",
) -> bool:
    """
    Pure, zero-SQLite-query deterministic sha256 awareness check for minor/mundane events:
    - Baseline awareness rate: 0.55
    - Boosted awareness rate: 0.95 when at incident venue OR holding a campus/bureau watch role.
    """
    ev_dict = event if isinstance(event, dict) else {}
    ev_key = str(ev_dict.get("event_key") or event or "").strip()
    if not ev_key:
        return False

    ev_loc = str(ev_dict.get("location_name") or "").strip().lower()
    ev_nid = str(ev_dict.get("location_node_id") or "").strip().lower()

    is_venue_match = False
    npc_loc = ""
    npc_nid = ""
    role_text = ""

    if isinstance(npc_profile, dict):
        npc_loc = str(
            npc_profile.get("location")
            or npc_profile.get("current_location")
            or npc_profile.get("scene_location")
            or ""
        ).strip().lower()
        npc_nid = str(npc_profile.get("location_node_id") or npc_profile.get("node_id") or "").strip().lower()
        basic = npc_profile.get("basic_info") if isinstance(npc_profile.get("basic_info"), dict) else {}
        role_text = " ".join(
            str(npc_profile.get(k) or basic.get(k) or "")
            for k in ("role", "occupation", "title", "description", "standing", "faction", "notes")
        ).lower()
    elif isinstance(npc_profile, str) and npc_profile:
        role_text = npc_profile.lower()

    curr_loc = str(current_location or "").strip().lower()
    check_locs = [loc for loc in (curr_loc, npc_loc) if loc]

    if ev_nid and npc_nid and ev_nid == npc_nid:
        is_venue_match = True
    elif ev_loc and check_locs:
        ev_leaf = ev_loc.split("➔")[-1].strip()
        for cl in check_locs:
            cl_leaf = cl.split("➔")[-1].strip()
            if (
                ev_loc == cl
                or ev_loc in cl
                or cl in ev_loc
                or (len(ev_leaf) >= 4 and (ev_leaf in cl_leaf or cl_leaf in ev_leaf))
            ):
                is_venue_match = True
                break
    elif ev_nid and curr_loc:
        ev_nid_words = ev_nid.replace("_", " ").strip()
        if len(ev_nid_words) >= 4 and ev_nid_words in curr_loc:
            is_venue_match = True

    is_watch_role = any(tok in role_text for tok in _WATCH_ROLE_TOKENS)
    spread_rate = 0.95 if (is_venue_match or is_watch_role) else 0.55
    return is_npc_aware_of_event(session_id, ev_key, npc_id, spread_rate=spread_rate)


def is_npc_scandal_eligible(
    npc_or_contact: dict[str, Any],
    party_names: set[str] | list[str] | None = None,
) -> bool:
    """Strictly excludes spouses, romantic partners, party companions, and genealogical kin from scandal targeting."""
    if not isinstance(npc_or_contact, dict):
        return False
    name_low = str(npc_or_contact.get("name") or "").strip().lower()
    npc_id_low = str(npc_or_contact.get("npc_id") or "").strip().lower()
    if party_names:
        party_low = {str(p).strip().lower() for p in party_names if p}
        if name_low in party_low or npc_id_low in party_low:
            return False
    if bool(npc_or_contact.get("is_companion")) or bool(npc_or_contact.get("in_party")):
        return False

    track = str(npc_or_contact.get("track") or "").strip().lower()
    if track in ("romantic", "romance", "lover", "spouse", "dating"):
        return False
    try:
        if int(npc_or_contact.get("relationship_score") or 0) >= 70:
            return False
    except (TypeError, ValueError):
        pass

    raw_rel = npc_or_contact.get("relations") or npc_or_contact.get("relations_json") or {}
    if isinstance(raw_rel, str):
        try:
            raw_rel = json.loads(raw_rel)
        except Exception:
            raw_rel = {}
    if isinstance(raw_rel, dict) and raw_rel:
        rel_blob = json.dumps(raw_rel).lower()
        for tok in _KIN_AND_PARTNER_TOKENS:
            if tok in rel_blob:
                return False
    return True


def can_break_news_today(
    session_id: int,
    current_day: int,
    npc_id: str,
    pity_state: dict[str, Any] | None = None,
) -> bool:
    """Returns True if the player has NOT yet used [Break the News] with npc_id on current_day."""
    norm_npc = str(npc_id or "").strip().lower().replace(" ", "_")
    if not norm_npc:
        return False
    state = pity_state if isinstance(pity_state, dict) else db.get_session_world_pity_state(session_id)
    shared = state.get("npc_gossip_shared_today") or {}
    return int(shared.get(norm_npc) or -1) != int(current_day)


def record_break_the_news_gossip(
    session_id: int,
    current_day: int,
    npc_id: str,
    event_key: str,
) -> dict[str, Any]:
    """Records a 1/day [Break the News] rumor share with an unaware NPC."""
    norm_npc = str(npc_id or "").strip().lower().replace(" ", "_")
    if not norm_npc:
        return {"allowed": False, "reason": "Invalid NPC identifier."}

    state = db.get_session_world_pity_state(session_id)
    shared = dict(state.get("npc_gossip_shared_today") or {})
    if int(shared.get(norm_npc) or -1) == int(current_day):
        return {
            "allowed": False,
            "reason": "You have already shared breaking gossip with this character today.",
            "npc_id": norm_npc,
        }

    # Prune stale days to keep JSON tiny
    shared = {k: int(v) for k, v in shared.items() if int(v) == int(current_day)}
    shared[norm_npc] = int(current_day)
    db.update_session_world_pity_state(session_id, npc_gossip_shared_today=shared)
    return {
        "allowed": True,
        "npc_id": norm_npc,
        "event_key": event_key,
        "day": int(current_day),
        "affinity_bonus": 2,
    }


def handle_mid_rumor_npc_promotion(
    session_id: int,
    npc_name: str = "",
    npc_id: str = "",
    current_day: int | None = None,
    current_minute: int | None = None,
    turn_number: int | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Converts any active rumor implicating an NPC who becomes a partner/companion into a 'Clear Their Name' loyalty quest (+15 affinity)."""
    current_day, current_minute, turn_number = resolve_session_time_and_turn(
        session_id, current_day, current_minute, turn_number
    )

    target_name = str(npc_name or npc_id or "").strip()
    norm_candidates = {
        str(npc_name or "").strip().lower(),
        str(npc_id or "").strip().lower(),
        str(npc_name or "").strip().lower().replace(" ", "_"),
    } - {""}

    matched_contact_ids, matched_name = db.find_contacts_by_identity_candidates(session_id, norm_candidates)
    if not target_name and matched_name:
        target_name = matched_name

    active_rumors = db.get_world_events(session_id, entity_type="rumor", include_hidden=True, statuses=("active",))
    loyalty_quests: list[dict[str, Any]] = []
    for rm in active_rumors:
        imp_cid = rm.get("implicated_contact_id")
        meta = rm.get("metadata") or {}
        imp_names = {
            str(meta.get("implicated_npc_name") or "").strip().lower(),
            str(meta.get("implicated_npc_id") or "").strip().lower(),
        } - {""}
        if (imp_cid is not None and int(imp_cid) in matched_contact_ids) or (norm_candidates & imp_names):
            conv = db.convert_rumor_to_loyalty_quest(
                session_id=session_id,
                event_key=rm["event_key"],
                npc_name=target_name or "Companion",
                current_day=int(current_day),
                current_minute=int(current_minute),
                turn_number=int(turn_number),
            )
            loyalty_quests.append(conv)

    if loyalty_quests and matched_contact_ids:
        db.apply_contact_loyalty_bonus(matched_contact_ids, AFFINITY_LOYALTY_CONVERSION_BONUS)

    return {
        "converted": len(loyalty_quests) > 0,
        "loyalty_quests": loyalty_quests,
        "affinity_bonus_applied": AFFINITY_LOYALTY_CONVERSION_BONUS if loyalty_quests else 0,
    }


def evaluate_witness_catch_scandal_gate(
    session_id: int,
    current_day: int | None = None,
    current_minute: int | None = None,
    turn_number: int | None = None,
    witness_name: str = "",
    partner_name: str = "",
    location_display: str = "",
    event_kind: str = "",
    is_high_profile: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    """Catch #1 stays cosmetic; Catch #2 within 3 days (or high-profile) spawns a 48h RMR-SCANDAL Damage Control quest (max 1 active, 7d cooldown)."""
    current_day, current_minute, turn_number = resolve_session_time_and_turn(
        session_id, current_day, current_minute, turn_number
    )

    witness = str(witness_name or kwargs.get("witness_npc_id") or "an onlooker").strip()
    partner = str(partner_name or kwargs.get("target_npc_id") or "someone").strip()
    zone_txt = str(location_display or kwargs.get("zone") or "the district").split("➔")[-1].strip() or "the district"

    state = db.get_session_world_pity_state(session_id)
    cooldown_until = int(state.get("player_scandal_cooldown_until_day") or 0)
    if int(current_day) < cooldown_until:
        return {"spawned_scandal": False, "reason": "cooldown_active", "cooldown_until_day": cooldown_until}

    active_quests = db.get_session_quests(session_id, status="Active") or []
    if any(str(q.get("quest_id") or "").startswith("RMR-SCANDAL-") for q in active_quests):
        return {"spawned_scandal": False, "reason": "scandal_already_active"}

    catches = [
        c for c in (state.get("recent_witness_catches") or [])
        if isinstance(c, dict) and (int(current_day) - int(c.get("day") or 0)) <= WITNESS_CATCH_WINDOW_DAYS
    ]
    catches.append({"day": int(current_day), "minute": int(current_minute), "witness": witness, "kind": str(event_kind or kwargs.get("act_type") or "tryst")})

    if len(catches) < WITNESS_CATCH_VIRALITY_THRESHOLD and not is_high_profile:
        db.update_session_world_pity_state(session_id, recent_witness_catches=catches)
        return {
            "spawned_scandal": False,
            "reason": "cosmetic_first_catch",
            "catch_count_in_window": len(catches),
        }

    now = time.time()
    total_deadline_min = int(current_minute) + (SCANDAL_INVESTIGATION_HOURS * 60)
    deadline_day = int(current_day) + (total_deadline_min // 1440)
    deadline_minute = total_deadline_min % 1440
    seq = (int(now * 1000) % 900_000) + 100_000
    quest_id = f"RMR-SCANDAL-{session_id}-{seq}"
    ev_key = f"we_{session_id}_scandal_{seq}"
    title = f"Viral Scandal Near {zone_txt}"
    desc = f"After {witness} spotted a compromising moment with {partner} at {zone_txt}, gossip is threatening to spiral out of control."

    db.create_witness_scandal_event(
        session_id=session_id,
        quest_id=quest_id,
        event_key=ev_key,
        title=title,
        description=desc,
        witness=witness,
        zone_txt=zone_txt,
        deadline_day=deadline_day,
        deadline_minute=deadline_minute,
        turn_number=int(turn_number),
        scandal_cooldown_day=int(current_day) + PLAYER_SCANDAL_COOLDOWN_DAYS,
    )
    return {
        "spawned_scandal": True,
        "quest_id": quest_id,
        "event_key": ev_key,
        "deadline_day": deadline_day,
        "deadline_minute": deadline_minute,
        "catch_count_in_window": len(catches),
    }
