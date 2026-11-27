from __future__ import annotations

"""Deterministic off-screen NPC autonomy, D1-D14 schedule overrides, D2 romance shield, and boundary-tick deltas."""

import hashlib
import json
from typing import Any, Mapping, Sequence

from mechanics.world.anchor_schedule import _ANCHOR_ORIGINS, resolve_anchor_schedule_nodes
from mechanics.world.locations.residence_fog import SHARED_ABSTRACT_RESIDENCE_NODE
from mechanics.world.schedule_blocks import get_time_block_key
from mechanics.world.world_events.modifiers import is_node_locked_by_event

_EXCLUDED_AUTONOMY_VENUES: frozenset[str] = frozenset({
    SHARED_ABSTRACT_RESIDENCE_NODE,
    "loc_rival_academy_away",
})

_BLOCK_SEQUENCE: tuple[str, ...] = ("morning", "lunch", "afternoon", "evening", "night")
_FREE_SOCIAL_BLOCKS: frozenset[str] = frozenset({"lunch", "evening", "night"})
_ROMANTIC_TIE_TYPES: frozenset[str] = frozenset(
    {"crush", "secret_crush", "dating", "engaged", "married", "affair"}
)
_FRIENDLY_TIE_TYPES: frozenset[str] = frozenset(
    {"friend", "best_friend", "dating", "engaged", "married", "crush", "acquaintance"}
)
_ESSENTIAL_STAFF_ROLES: tuple[str, ...] = (
    "merchant", "shopkeeper", "vendor", "clerk", "barkeep", "bartender",
    "innkeeper", "nurse", "doctor", "teacher", "principal", "dean", "librarian",
    "guard", "custodian", "coach",
)


def _norm_key(val: Any) -> str:
    return str(val or "").strip().lower()


def _parse_json_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            loaded = json.loads(raw)
            return dict(loaded) if isinstance(loaded, Mapping) else {}
        except Exception:
            return {}
    return {}


def _det_unit(seed: str) -> int:
    """Deterministic integer in [0, 9999] from sha256."""
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 10000


def _is_weekend_day(day: int) -> bool:
    return int(day or 1) % 7 in (6, 0)


def _is_player_ref(key: Any) -> bool:
    k = _norm_key(key)
    return k in ("player", "you") or k.startswith("player:") or k.startswith("player_") or k.startswith("mp:")


def _contact_affinity(contact: Mapping[str, Any]) -> int:
    for field in ("relationship_score", "affinity", "relationship_level", "aff"):
        val = contact.get(field)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                pass
    return 0


def _npc_aliases(npc: Mapping[str, Any]) -> set[str]:
    out: set[str] = set()
    for field in ("npc_id", "person_key", "npc_key", "name"):
        v = _norm_key(npc.get(field))
        if v:
            out.add(v)
    return out


def _find_matching_contact(npc_key: str, contacts: Sequence[Mapping[str, Any]], npc_row: Mapping[str, Any] | None = None) -> dict[str, Any]:
    targets = {_norm_key(npc_key)}
    if npc_row:
        targets |= _npc_aliases(npc_row)
    for c in contacts or ():
        c_aliases = {_norm_key(c.get(f)) for f in ("npc_id", "person_key", "name") if _norm_key(c.get(f))}
        if targets & c_aliases:
            return dict(c)
    return {}


def _is_unique_proprietor(npc: Mapping[str, Any], basic: Mapping[str, Any]) -> bool:
    if npc.get("is_unique_proprietor") or basic.get("is_unique_proprietor"):
        return True
    role = f"{npc.get('role') or ''} {npc.get('occupation') or ''} {basic.get('role') or ''}".lower()
    if any(k in role for k in ("shopkeeper", "innkeeper", "barkeep", "librarian", "principal", "nurse")):
        return True
    return False


def is_npc_romance_shielded(
    npc_key: str,
    *,
    contacts: Sequence[Mapping[str, Any]] = (),
    party_keys: frozenset[str] | set[str] = frozenset(),
    player_ties: Sequence[Mapping[str, Any]] = (),
    npc_row: Mapping[str, Any] | None = None,
) -> bool:
    """D2: Returns True when an NPC is on ANY player romantic track, in party, crush-marked, or Affinity >= 30."""
    nkey = _norm_key(npc_key)
    norm_party = {_norm_key(k) for k in party_keys if _norm_key(k)}
    if nkey and nkey in norm_party:
        return True

    row = dict(npc_row or {})
    basic = _parse_json_dict(row.get("basic_info") or row.get("basic_info_json"))
    if row.get("in_party") or basic.get("in_party"):
        return True
    if row.get("secret_crush_on_pc") or basic.get("secret_crush_on_pc"):
        return True

    aliases = ({nkey} if nkey else set()) | _npc_aliases(row)
    if aliases & norm_party:
        return True

    c = _find_matching_contact(nkey, contacts, row)
    if c:
        if c.get("in_party") or c.get("secret_crush_on_pc"):
            return True
        if _contact_affinity(c) >= 30:
            return True
        rel_stat = _norm_key(c.get("relationship_status") or c.get("romance_stage"))
        track_val = _norm_key(c.get("track"))
        if track_val == "romantic" or rel_stat in ("romantic", "crush", "dating", "engaged", "married", "partner", "lover"):
            return True

    for t in player_ties or ():
        if str(t.get("status") or "active").lower() not in ("active", ""):
            continue
        pa = _norm_key(t.get("person_a_key"))
        pb = _norm_key(t.get("person_b_key"))
        ttype = _norm_key(t.get("tie_type"))
        other = pb if _is_player_ref(pa) else (pa if _is_player_ref(pb) else "")
        if not other:
            continue
        if other in aliases:
            if ttype in _ROMANTIC_TIE_TYPES:
                return True
            meta = _parse_json_dict(t.get("metadata") or t.get("metadata_json"))
            if float(meta.get("romance_progress") or 0) > 0:
                return True

    return False


def _pick_friend_outing_target(
    npc_key: str,
    *,
    active_ties_by_person: Mapping[str, Sequence[Mapping[str, Any]]] | None,
    roster_by_key: Mapping[str, Mapping[str, Any]] | None,
    session_id: int,
    day: int,
    block: str,
) -> tuple[str, str] | None:
    if not active_ties_by_person or not roster_by_key:
        return None
    ties = active_ties_by_person.get(npc_key) or ()
    candidates: list[tuple[int, str, str, str]] = []
    for t in ties:
        if str(t.get("status") or "active").lower() != "active":
            continue
        ttype = _norm_key(t.get("tie_type"))
        if ttype not in _FRIENDLY_TIE_TYPES:
            continue
        pa = _norm_key(t.get("person_a_key"))
        pb = _norm_key(t.get("person_b_key"))
        other_k = pb if pa == npc_key else pa
        if not other_k or _is_player_ref(other_k):
            continue
        other_npc = roster_by_key.get(other_k)
        if not other_npc:
            continue
        node = str(
            other_npc.get("hangout_node_id")
            or other_npc.get("home_node_id")
            or ""
        ).strip()
        if not node:
            continue
        closeness = int(t.get("closeness") or 0)
        candidates.append((-closeness, other_k, node, str(other_npc.get("name") or other_k)))
    if not candidates:
        return None
    candidates.sort()
    idx = _det_unit(f"{session_id}:{day}:{block}:{npc_key}:friend_pick") % len(candidates)
    _, _, node_id, friend_name = candidates[idx]
    return node_id, friend_name


def _contact_openness_comfort(npc_row: Mapping[str, Any], aff_score: int) -> tuple[str, str]:
    """Derives (openness_tier, comfort_stage) cleanly for autonomy pacing."""
    app = _parse_json_dict(npc_row.get("appearance") or npc_row.get("appearance_json"))
    raw_op = app.get("erotic_openness") or app.get("openness")
    if raw_op in (None, ""):
        return "moderate", "guarded"
    from mechanics.social.persona import compute_with_you_comfort, normalize_openness_tier

    op_tier = normalize_openness_tier(raw_op)
    track = str(npc_row.get("relationship_track") or npc_row.get("track") or "platonic")
    shared_cnt = len(npc_row.get("gameplay_intimate_events") or [])
    is_hostile = str(npc_row.get("disposition") or "").strip().lower() == "hostile"
    comfort = compute_with_you_comfort(
        op_tier,
        relationship_score=aff_score,
        relationship_track=track,
        shared_intimate_count=shared_cnt,
        is_hostile=is_hostile,
    )
    return op_tier, str(comfort.get("stage") or "guarded")


def resolve_autonomy_node_override(
    npc: Mapping[str, Any],
    *,
    session_id: int,
    day: int,
    block: str,
    scen_key: str = "fantasy",
    active_ties_by_person: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    roster_by_key: Mapping[str, Mapping[str, Any]] | None = None,
    active_events: Sequence[Mapping[str, Any]] = (),
    has_active_rendezvous_or_quest: bool = False,
    player_home_node_id: str = "",
    scheduled_node_id: str = "",
) -> dict[str, Any] | None:
    """
    Computes an ephemeral current-day autonomy override without mutating baseline anchor schedules (`F4`).
    Priority: Tier 2/3 quests & commitments ALWAYS stay exempt (`None`).
    """
    if has_active_rendezvous_or_quest:
        return None

    basic = _parse_json_dict(npc.get("basic_info") or npc.get("basic_info_json"))
    nkey = _norm_key(npc.get("person_key") or npc.get("npc_id") or npc.get("name"))
    cur_day = max(1, int(day or 1))
    cur_block = _norm_key(block) or "afternoon"

    # 1. Persistent non-expired autonomy_override stored in basic_info (D8/D3 boundary deltas)
    saved_ov = basic.get("autonomy_override")
    if isinstance(saved_ov, Mapping) and str(saved_ov.get("node_id") or "").strip():
        raw_exp_day = saved_ov.get("expires_day") if saved_ov.get("expires_day") is not None else saved_ov.get("expiry_day")
        exp_day = int(raw_exp_day or cur_day)
        exp_block = _norm_key(saved_ov.get("expires_block") or saved_ov.get("expiry_block"))
        block_ok = (
            not exp_block
            or exp_block == cur_block
            or (
                cur_block in _BLOCK_SEQUENCE
                and exp_block in _BLOCK_SEQUENCE
                and _BLOCK_SEQUENCE.index(cur_block) <= _BLOCK_SEQUENCE.index(exp_block)
            )
        )
        if exp_day > cur_day or (exp_day == cur_day and block_ok):
            return {
                "node_id": str(saved_ov["node_id"]).strip(),
                "reason": str(saved_ov.get("reason") or "autonomy_override"),
                "visit_label": str(saved_ov.get("visit_label") or ""),
                "visiting_npc": str(saved_ov.get("visiting_npc") or ""),
                "is_outing": bool(saved_ov.get("is_outing")),
                "is_dropby": bool(saved_ov.get("is_dropby")),
                "is_truant": bool(saved_ov.get("is_truant")),
                "is_crisis_redirect": bool(saved_ov.get("is_crisis_redirect")),
            }

    unique_prop = _is_unique_proprietor(npc, basic)
    scheduled_node = str(scheduled_node_id or npc.get("scheduled_node_id") or npc.get("workplace_node_id") or "").strip()

    # 2. D3 Crisis / Infirmary redirect when NPC's scheduled venue is locked by active World Pulse event
    events_payload = (
        active_events
        if isinstance(active_events, Mapping)
        else {"active_macro_events": [dict(e) for e in (active_events or ()) if isinstance(e, Mapping)]}
    )
    if scheduled_node and active_events and is_node_locked_by_event(events_payload, scheduled_node):
        safe_fallback = ""
        for cand in (npc.get("home_node_id"), basic.get("home_node_id"), npc.get("hangout_node_id")):
            c_id = str(cand or "").strip()
            if c_id and c_id != scheduled_node and not is_node_locked_by_event(events_payload, c_id):
                safe_fallback = c_id
                break
        if not safe_fallback:
            if "high_school" in _norm_key(scen_key) and not "anomalous" in _norm_key(scen_key):
                safe_fallback = "loc_school_infirmary"
            else:
                safe_fallback = "zone_residential_abstract"
        if safe_fallback and safe_fallback != scheduled_node:
            return {
                "node_id": safe_fallback,
                "reason": "crisis_redirect",
                "visit_label": "Sheltering",
                "visiting_npc": "",
                "is_outing": False,
                "is_dropby": False,
                "is_truant": False,
                "is_crisis_redirect": True,
            }

    if unique_prop:
        return None

    # 3. D3 Rare truancy (~8%) for delinquent / rebellious traits during school hours
    traits_probe = " ".join(
        str(x or "").lower()
        for x in (npc.get("traits"), npc.get("personality"), basic.get("traits"), npc.get("archetype"))
    )
    if (
        "high_school" in _norm_key(scen_key)
        and not _is_weekend_day(cur_day)
        and cur_block in ("morning", "afternoon")
        and any(tok in traits_probe for tok in ("delinquent", "rebellious", "truant", "slacker", "troublemaker"))
    ):
        if _det_unit(f"{session_id}:{cur_day}:{cur_block}:{nkey}:truant") < 800:
            truant_node = str(npc.get("hangout_node_id") or basic.get("hangout_node_id") or "loc_school_rooftop").strip()
            return {
                "node_id": truant_node,
                "reason": "truancy",
                "visit_label": "Skipping Class",
                "visiting_npc": "",
                "is_outing": False,
                "is_dropby": False,
                "is_truant": True,
                "is_crisis_redirect": False,
            }

    is_free = (cur_block in _FREE_SOCIAL_BLOCKS) or _is_weekend_day(cur_day)
    if not is_free:
        return None

    # 4. D14 Free-block casual drop-by scaled gently by Openness + With-You Comfort
    aff = _contact_affinity(npc)
    if aff < 75:
        aff = max(aff, _contact_affinity(basic))
    op_tier_db, comfort_stage_db = _contact_openness_comfort(npc, aff)
    if op_tier_db in ("bold", "shameless"):
        dropby_min_aff, dropby_odds = 65, 2400
    elif op_tier_db == "prude" and comfort_stage_db == "guarded":
        dropby_min_aff, dropby_odds = 90, 1400
    else:
        dropby_min_aff, dropby_odds = 75, 2000
    home_dest = str(player_home_node_id or "").strip()
    if aff >= dropby_min_aff and home_dest and home_dest != str(npc.get("home_node_id") or "").strip():
        if _det_unit(f"{session_id}:{cur_day}:{cur_block}:{nkey}:dropby") < dropby_odds:
            return {
                "node_id": home_dest,
                "reason": "player_dropby",
                "visit_label": "Dropping by",
                "visiting_npc": str(npc.get("name") or nkey),
                "is_outing": False,
                "is_dropby": True,
                "is_truant": False,
                "is_crisis_redirect": False,
            }

    # 5. D1 ~25% deterministic friend outing on free blocks
    if _det_unit(f"{session_id}:{cur_day}:{cur_block}:{nkey}:outing") < 2500:
        picked = _pick_friend_outing_target(
            nkey,
            active_ties_by_person=active_ties_by_person,
            roster_by_key=roster_by_key,
            session_id=int(session_id or 0),
            day=cur_day,
            block=cur_block,
        )
        if picked is not None:
            target_node, friend_name = picked
            return {
                "node_id": target_node,
                "reason": "friend_outing",
                "visit_label": "At a friend's place",
                "visiting_npc": friend_name,
                "is_outing": True,
                "is_dropby": False,
                "is_truant": False,
                "is_crisis_redirect": False,
            }

    return None


def _enumerate_crossed_ticks(old_day: int, old_min: int, new_day: int, new_min: int) -> list[tuple[int, str]]:
    od, om = max(1, int(old_day or 1)), max(0, int(old_min or 0))
    nd, nm = max(1, int(new_day or 1)), max(0, int(new_min or 0))
    if nd < od or (nd == od and nm <= om):
        return []
    old_b = get_time_block_key(om % 1440)
    new_b = get_time_block_key(nm % 1440)
    if nd == od and old_b == new_b and (nm - om) < 240:
        return []

    ticks: list[tuple[int, str]] = []
    max_days = min(nd - od + 1, 7)
    for d_off in range(max_days):
        cur_d = od + d_off
        if d_off == 0:
            if old_b == "night" and (om % 1440) < 360:
                start_idx = 0
            else:
                start_idx = _BLOCK_SEQUENCE.index(old_b) if old_b in _BLOCK_SEQUENCE else 0
        else:
            start_idx = 0
        if cur_d == nd:
            if new_b == "night" and (nm % 1440) < 360:
                if d_off == 0:
                    ticks.append((cur_d, "night"))
                continue
            end_idx = _BLOCK_SEQUENCE.index(new_b) if new_b in _BLOCK_SEQUENCE else len(_BLOCK_SEQUENCE) - 1
        else:
            end_idx = len(_BLOCK_SEQUENCE) - 1
        for b_idx in range(start_idx, end_idx + 1):
            ticks.append((cur_d, _BLOCK_SEQUENCE[b_idx]))
    return ticks


def _resolve_npc_block_venue(
    row: Mapping[str, Any],
    block: str,
    *,
    day: int = 1,
    scen_key: str = "fantasy",
) -> str:
    basic = _parse_json_dict(row.get("basic_info") or row.get("basic_info_json"))
    origin_low = _norm_key(row.get("origin") or basic.get("origin"))
    shift_prof = _norm_key(row.get("shift_profile") or basic.get("shift_profile"))
    has_route = bool(row.get("roaming_route") or basic.get("roaming_route") or basic.get("weekend_route"))
    if (origin_low in _ANCHOR_ORIGINS and origin_low != "legacy_adapter") or shift_prof or has_route:
        rep_min = {"morning": 540, "lunch": 750, "afternoon": 960, "evening": 1140, "night": 1350}.get(block, 960)
        a_sched = resolve_anchor_schedule_nodes(
            {**dict(row), "_roster_premerged": True},
            current_day=day,
            scen_key=scen_key,
            session_id=None,
            current_minute=rep_min,
        )
        if isinstance(a_sched, dict):
            return str(a_sched.get(block) or "").strip()

    if block in ("morning", "afternoon"):
        return str(row.get("workplace_node_id") or row.get("home_node_id") or "").strip()
    if block in ("lunch", "evening"):
        return str(row.get("hangout_node_id") or row.get("workplace_node_id") or row.get("home_node_id") or "").strip()
    return str(row.get("home_node_id") or row.get("hangout_node_id") or "").strip()


def _lookup_pair_tie(
    pair_key: tuple[str, str],
    ties_by_pair: Mapping[tuple[str, str], Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    return ties_by_pair.get(pair_key) or ties_by_pair.get((pair_key[1], pair_key[0]))


def compute_boundary_autonomy_deltas(
    session_id: int,
    *,
    old_day: int,
    old_min: int,
    new_day: int,
    new_min: int,
    scen_key: str = "fantasy",
    roster_rows: Sequence[Mapping[str, Any]] = (),
    contacts: Sequence[Mapping[str, Any]] = (),
    all_ties: Sequence[Mapping[str, Any]] = (),
    party_keys: frozenset[str] | set[str] = frozenset(),
    active_events: Sequence[Mapping[str, Any]] = (),
    turn_number: int = 1,
) -> dict[str, list[dict[str, Any]]]:
    """
    Pure boundary-tick planner producing delta-only `tie_ops`, `roster_mutations`, `gossip_posts`, and `dm_pings`.
    Enforces D2 romance shield, axis `nudge_weights`, D8 milestone hangout shifts, and D11 multi-day caps.
    """
    ticks = _enumerate_crossed_ticks(old_day, old_min, new_day, new_min)
    empty: dict[str, list[dict[str, Any]]] = {
        "tie_ops": [],
        "roster_mutations": [],
        "gossip_posts": [],
        "dm_pings": [],
    }
    if not ticks or not roster_rows:
        return empty

    sid = int(session_id or 0)
    ties_by_pair: dict[tuple[str, str], Mapping[str, Any]] = {}
    player_ties: list[Mapping[str, Any]] = []
    partnered_npcs: dict[str, str] = {}
    for t in all_ties or ():
        if str(t.get("status") or "active").lower() != "active":
            continue
        pa = _norm_key(t.get("person_a_key"))
        pb = _norm_key(t.get("person_b_key"))
        if not pa or not pb:
            continue
        tt = _norm_key(t.get("tie_type"))
        if tt in ("dating", "engaged", "married"):
            partnered_npcs[pa] = pb
            partnered_npcs[pb] = pa
        if _is_player_ref(pa) or _is_player_ref(pb):
            player_ties.append(t)
        else:
            ties_by_pair[(min(pa, pb), max(pa, pb))] = t

    active_roster = []
    priority_keys: set[str] = set()
    for c in contacts or ():
        for f in ("npc_id", "person_key", "npc_key", "name"):
            kv = _norm_key(c.get(f))
            if kv:
                priority_keys.add(kv)
    for t in all_ties or ():
        if str(t.get("status") or "active").lower() != "active":
            continue
        for f in ("person_a_key", "person_b_key"):
            kv = _norm_key(t.get(f))
            if kv and not _is_player_ref(kv):
                priority_keys.add(kv)

    for r in roster_rows:
        pk = _norm_key(r.get("person_key") or r.get("npc_id") or r.get("name"))
        if not pk:
            continue
        r_basic = _parse_json_dict(r.get("basic_info") or r.get("basic_info_json"))
        r_stat = _norm_key(r.get("staff_status") or r_basic.get("staff_status") or "active")
        if r_stat in ("dead", "arrested", "deceased", "departed", "removed"):
            continue
        if bool(r.get("is_deceased") or r_basic.get("is_deceased")):
            continue
        if r.get("alive") is False or r_basic.get("alive") is False:
            continue
        active_roster.append(r)
        r_aff = 0
        try:
            r_aff = int(r.get("affinity_score") or r.get("affinity") or r_basic.get("affinity_score") or 0)
        except (TypeError, ValueError):
            r_aff = 0
        if bool(r.get("met_in_person") or r_basic.get("met_in_person")) or r_aff > 0:
            priority_keys |= _npc_aliases(r)

    shield_cache: dict[str, bool] = {}
    for r in active_roster:
        pk = _norm_key(r.get("person_key") or r.get("npc_id") or r.get("name"))
        shield_cache[pk] = is_npc_romance_shielded(
            pk, contacts=contacts, party_keys=party_keys, player_ties=player_ties, npc_row=r,
        )

    from mechanics.system.phone.embeds import scenario_has_smartphone

    has_phone = bool(scenario_has_smartphone(scen_key))
    pair_day_seen: set[tuple[int, str, str]] = set()
    milestone_shifted: set[str] = set()
    tie_ops: list[dict[str, Any]] = []
    roster_mutations: list[dict[str, Any]] = []
    gossip_posts: list[dict[str, Any]] = []
    dm_pings: list[dict[str, Any]] = []
    drama_dms_emitted = 0
    hangout_pings_emitted = 0

    for tick_day, tick_block in ticks:
        by_venue: dict[str, list[Mapping[str, Any]]] = {}
        for r in active_roster:
            vnode = _resolve_npc_block_venue(r, tick_block, day=tick_day, scen_key=scen_key)
            if vnode and vnode not in _EXCLUDED_AUTONOMY_VENUES:
                by_venue.setdefault(vnode, []).append(r)

        priority_pairs: list[tuple[Mapping[str, Any], Mapping[str, Any], str, str, str, str, str, bool]] = []
        ambient_pairs: list[tuple[int, str, str, Mapping[str, Any], Mapping[str, Any], str, str, str, bool]] = []
        for vnode, occupants in sorted(by_venue.items()):
            if len(occupants) < 2:
                continue
            ordered = sorted(
                occupants,
                key=lambda x: _norm_key(x.get("person_key") or x.get("npc_id") or x.get("name")),
            )
            for idx in range(0, len(ordered) - 1, 2):
                a_row, b_row = ordered[idx], ordered[idx + 1]
                ka = _norm_key(a_row.get("person_key") or a_row.get("npc_id") or a_row.get("name"))
                kb = _norm_key(b_row.get("person_key") or b_row.get("npc_id") or b_row.get("name"))
                p_low, p_high = (ka, kb) if ka <= kb else (kb, ka)
                a_aliases = _npc_aliases(a_row)
                b_aliases = _npc_aliases(b_row)
                is_prio = bool(
                    (a_aliases & priority_keys)
                    or (b_aliases & priority_keys)
                    or _lookup_pair_tie((p_low, p_high), ties_by_pair) is not None
                )
                if is_prio:
                    priority_pairs.append((a_row, b_row, ka, kb, p_low, p_high, vnode, True))
                else:
                    rank = _det_unit(f"{sid}:{tick_day}:{tick_block}:{p_low}:{p_high}:ambient_rank")
                    ambient_pairs.append((rank, p_low, p_high, a_row, b_row, ka, kb, vnode, False))

        ambient_pairs.sort(key=lambda item: (item[0], item[1], item[2]))
        selected_pairs: list[tuple[Mapping[str, Any], Mapping[str, Any], str, str, str, str, str, bool]] = (
            priority_pairs
            + [(a, b, ka, kb, p_l, p_h, vn, pr) for _, p_l, p_h, a, b, ka, kb, vn, pr in ambient_pairs[:3]]
        )

        for a_row, b_row, ka, kb, p_low, p_high, vnode, is_priority_pair in selected_pairs:
            # D11 cap: max 1 tie step per pair per simulated day
            if (tick_day, p_low, p_high) in pair_day_seen:
                continue
            if _det_unit(f"{sid}:{tick_day}:{tick_block}:{p_low}:{p_high}:interact") >= 4000:
                continue

            pair_day_seen.add((tick_day, p_low, p_high))
            existing_tie = _lookup_pair_tie((p_low, p_high), ties_by_pair)
            meta = _parse_json_dict(
                (existing_tie or {}).get("metadata") or (existing_tie or {}).get("metadata_json")
            )
            weights = _parse_json_dict((existing_tie or {}).get("nudge_weights") or meta.get("nudge_weights"))

            either_shielded = shield_cache.get(p_low, False) or shield_cache.get(p_high, False)
            roll = _det_unit(f"{sid}:{tick_day}:{tick_block}:{p_low}:{p_high}:axis")
            if roll < 1800 and not either_shielded:
                axis = "affection"
            elif roll < 8200:
                axis = "friendship"
            else:
                axis = "rivalry"

            axis_weight = float(weights.get(axis, 1.0)) if weights else 1.0
            if axis in ("affection", "romance") and either_shielded:
                axis = "friendship"
                axis_weight = float(weights.get("friendship", 1.0)) if weights else 1.0
            if axis_weight <= 0.0:
                continue

            base_delta = 3.0 if axis in ("friendship", "affection") else 2.5
            final_delta = round(base_delta * axis_weight, 2)
            tie_ops.append({
                "op": "nudge",
                "person_a": p_low,
                "person_b": p_high,
                "axis": axis,
                "delta": final_delta,
                "day": tick_day,
                "block": tick_block,
                "turn": int(turn_number),
            })

            # D2 & D8 concrete tie evolution & breakup handling
            cur_type = _norm_key((existing_tie or {}).get("tie_type"))
            prev_close = float((existing_tie or {}).get("closeness") or 35.0)
            aff_w = float(weights.get("affection", weights.get("romance", 0.0)) or 0.0)
            riv_w = float(weights.get("rivalry", 0.0) or 0.0)
            new_close = max(0.0, min(100.0, prev_close + (final_delta if axis != "rivalry" else -final_delta)))
            name_a = str(a_row.get("name") or p_low)
            name_b = str(b_row.get("name") or p_high)

            evolved_type = ""
            if cur_type in ("dating", "engaged", "married") and axis == "rivalry" and (new_close <= 25.0 or riv_w >= 2.0):
                tie_ops.append({
                    "op": "breakup",
                    "person_a": p_low,
                    "person_b": p_high,
                    "tie_type": cur_type,
                    "reason": "rivalry_breakup",
                    "day": tick_day,
                    "block": tick_block,
                    "turn": int(turn_number),
                })
                partnered_npcs.pop(p_low, None)
                partnered_npcs.pop(p_high, None)
                for r_m, k_m in ((a_row, ka), (b_row, kb)):
                    r_bi = _parse_json_dict(r_m.get("basic_info") or r_m.get("basic_info_json"))
                    prev_hang = str(r_bi.get("pre_couple_hangout_node_id") or r_m.get("home_node_id") or "").strip()
                    if prev_hang in _EXCLUDED_AUTONOMY_VENUES:
                        prev_hang = ""
                    if k_m not in milestone_shifted and prev_hang:
                        milestone_shifted.add(k_m)
                        roster_mutations.append({
                            "npc_id": str(r_m.get("npc_id") or k_m),
                            "hangout_node_id": prev_hang,
                            "basic_info_updates": {"shared_couple_hangout_node_id": ""},
                        })
                if len(gossip_posts) < 1:
                    gossip_posts.append({
                        "day": tick_day,
                        "block": tick_block,
                        "actor_keys": [p_low, p_high],
                        "tag": "#BreakupWatch",
                        "summary": f"Word is {name_a} and {name_b} just called it quits after a tense fallout.",
                    })
            elif (
                axis == "affection"
                and not either_shielded
                and (cur_type in ("friend", "best_friend", "crush", "secret_crush") or aff_w >= 1.5)
                and new_close >= 65.0
                and partnered_npcs.get(p_low) in (None, p_high)
                and partnered_npcs.get(p_high) in (None, p_low)
                and cur_type not in ("dating", "engaged", "married")
            ):
                evolved_type = "dating"
                partnered_npcs[p_low] = p_high
                partnered_npcs[p_high] = p_low
                tie_ops.append({
                    "op": "evolve_tie",
                    "person_a": p_low,
                    "person_b": p_high,
                    "tie_type": "dating",
                    "closeness": max(65, int(round(new_close))),
                    "visibility": "rumored" if aff_w < 2.0 else "public",
                    "day": tick_day,
                    "block": tick_block,
                    "turn": int(turn_number),
                })
            elif (
                axis == "affection"
                and not either_shielded
                and cur_type in ("", "acquaintance", "friend")
                and (aff_w >= 1.2 or new_close >= 50.0)
                and cur_type not in ("crush", "secret_crush", "dating", "engaged", "married")
            ):
                evolved_type = "crush"
                tie_ops.append({
                    "op": "evolve_tie",
                    "person_a": p_low,
                    "person_b": p_high,
                    "tie_type": "crush",
                    "closeness": max(50, int(round(new_close))),
                    "visibility": "private",
                    "day": tick_day,
                    "block": tick_block,
                    "turn": int(turn_number),
                })
            elif axis == "friendship" and cur_type in ("", "acquaintance") and new_close >= 45.0:
                evolved_type = "friend"
                tie_ops.append({
                    "op": "evolve_tie",
                    "person_a": p_low,
                    "person_b": p_high,
                    "tie_type": "friend",
                    "closeness": int(round(new_close)),
                    "visibility": "public",
                    "day": tick_day,
                    "block": tick_block,
                    "turn": int(turn_number),
                })
            elif axis == "friendship" and cur_type == "friend" and new_close >= 80.0:
                evolved_type = "best_friend"
                tie_ops.append({
                    "op": "evolve_tie",
                    "person_a": p_low,
                    "person_b": p_high,
                    "tie_type": "best_friend",
                    "closeness": int(round(new_close)),
                    "visibility": "public",
                    "day": tick_day,
                    "block": tick_block,
                    "turn": int(turn_number),
                })
            elif axis == "rivalry" and (riv_w >= 1.5 or new_close <= 25.0) and cur_type not in ("rival", "enemy"):
                evolved_type = "rival"
                tie_ops.append({
                    "op": "evolve_tie",
                    "person_a": p_low,
                    "person_b": p_high,
                    "tie_type": "rival",
                    "closeness": max(10, int(round(new_close))),
                    "visibility": "rumored",
                    "day": tick_day,
                    "block": tick_block,
                    "turn": int(turn_number),
                })

            # D8 milestone hangout shift when high closeness forms around a shared hangout venue
            if (new_close >= 70.0 or evolved_type == "dating") and len(milestone_shifted) < 2:
                shared_hangout = str(b_row.get("hangout_node_id") or vnode).strip()
                if shared_hangout in _EXCLUDED_AUTONOMY_VENUES:
                    shared_hangout = vnode if vnode not in _EXCLUDED_AUTONOMY_VENUES else ""
                orig_hangout = str(a_row.get("hangout_node_id") or "").strip()
                if orig_hangout in _EXCLUDED_AUTONOMY_VENUES:
                    orig_hangout = ""
                if shared_hangout and ka not in milestone_shifted and orig_hangout != shared_hangout:
                    milestone_shifted.add(ka)
                    a_bi = _parse_json_dict(a_row.get("basic_info") or a_row.get("basic_info_json"))
                    pre_hang = str(a_bi.get("pre_couple_hangout_node_id") or orig_hangout or shared_hangout).strip()
                    if pre_hang in _EXCLUDED_AUTONOMY_VENUES:
                        pre_hang = shared_hangout
                    roster_mutations.append({
                        "npc_id": str(a_row.get("npc_id") or ka),
                        "hangout_node_id": shared_hangout,
                        "basic_info_updates": {
                            "pre_couple_hangout_node_id": pre_hang,
                            "shared_couple_hangout_node_id": shared_hangout,
                        },
                    })

            # D9 drama gossip on intense affection/rivalry spark
            if (new_close >= 65.0 or evolved_type in ("dating", "rival")) and len(gossip_posts) < 1:
                gossip_posts.append({
                    "day": tick_day,
                    "block": tick_block,
                    "actor_keys": [p_low, p_high],
                    "tag": "#CampusWatch" if evolved_type != "dating" else "#CoupleAlert",
                    "summary": f"{name_a} and {name_b} were spotted together near {vnode}.",
                })
                if has_phone and drama_dms_emitted == 0 and is_priority_pair:
                    drama_dms_emitted += 1
                    dm_pings.append({
                        "kind": "drama_gossip",
                        "sender_key": p_low,
                        "subject_keys": [p_low, p_high],
                        "day": tick_day,
                        "summary": f"Did you hear about {name_a} and {name_b}?",
                    })

    # D10 / D11 hangout ping on wake-up (Affinity >= 50, capped at 1 hangout ping + phone gated)
    morning_ticks = [(td, tb) for td, tb in ticks if tb == "morning"]
    if has_phone and hangout_pings_emitted == 0 and morning_ticks:
        last_day, last_block = morning_ticks[-1]
        eligible_friends = []
        for c in contacts or ():
            if _contact_affinity(c) >= 50 and not c.get("in_party") and not c.get("is_blocked"):
                ckey = _norm_key(c.get("npc_id") or c.get("person_key") or c.get("name"))
                if ckey:
                    eligible_friends.append((ckey, c))
        eligible_friends.sort(key=lambda item: item[0])
        for ckey, c in eligible_friends:
            c_aff = _contact_affinity(c)
            op_tier_ping, comf_stage_ping = _contact_openness_comfort(c, c_aff)
            ping_odds = 4000 if op_tier_ping in ("bold", "shameless") else (2600 if (op_tier_ping == "prude" and comf_stage_ping == "guarded") else 3500)
            if _det_unit(f"{sid}:{last_day}:{last_block}:{ckey}:hangout_ping") < ping_odds:
                hangout_pings_emitted += 1
                cname = str(c.get("name") or ckey)
                c_basic = _parse_json_dict(c.get("basic_info") or c.get("basic_info_json"))
                ping_node = str(c.get("hangout_node_id") or c_basic.get("hangout_node_id") or "").strip()
                if op_tier_ping == "shameless":
                    ping_summary = "Don't leave me waiting—come keep me company?"
                elif op_tier_ping == "bold":
                    ping_summary = "Free right now? Come swing by and distract me."
                elif op_tier_ping == "prude":
                    ping_summary = "If you aren't too busy today, would you like to meet up?"
                else:
                    ping_summary = "Hey, want to swing by and hang out?"
                dm_pings.append({
                    "kind": "hangout_invite",
                    "sender_key": ckey,
                    "sender_name": cname,
                    "node_id": ping_node,
                    "day": last_day,
                    "summary": ping_summary,
                })
                roster_mutations.append({
                    "npc_id": str(c.get("npc_id") or ckey),
                    "pending_hangout_ping": {
                        "day": last_day,
                        "block": last_block,
                        "expires_day": last_day,
                        "node_id": ping_node,
                    },
                })
                break

    # D3 inactive staff replacement notice (World Pulse / retired unique proprietor safeguard)
    for ev in active_events or ():
        if str(ev.get("status") or "").lower() != "active":
            continue
        rep_role = str(ev.get("replacement_role") or "").strip()
        rep_node = str(ev.get("location_node_id") or "").strip()
        if rep_role and rep_node and len(roster_mutations) < 6:
            rep_name = str(ev.get("replacement_name") or f"Relief {rep_role.title()}")
            roster_mutations.append({
                "replacement_npc": {
                    "name": rep_name,
                    "role": rep_role,
                    "workplace_node_id": rep_node,
                    "origin": "replacement_hire",
                    "is_unique_proprietor": True,
                }
            })

    return {
        "tie_ops": tie_ops,
        "roster_mutations": roster_mutations,
        "gossip_posts": gossip_posts,
        "dm_pings": dm_pings,
    }
