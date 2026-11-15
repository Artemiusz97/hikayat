from __future__ import annotations

"""Deterministic off-screen NPC autonomy, D1-D14 schedule overrides, D2 romance shield, and boundary-tick deltas."""

import hashlib
import json
from typing import Any, Mapping, Sequence

from mechanics.world.schedule_blocks import get_time_block_key
from mechanics.world.world_events.modifiers import is_node_locked_by_event

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
    for field in ("affinity", "relationship_level", "aff"):
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
        if rel_stat in ("crush", "dating", "engaged", "married", "partner", "lover"):
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
        exp_day = int(saved_ov.get("expires_day") or cur_day)
        exp_block = _norm_key(saved_ov.get("expires_block"))
        if exp_day > cur_day or (exp_day == cur_day and (not exp_block or exp_block == cur_block)):
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
    scheduled_node = str(npc.get("scheduled_node_id") or npc.get("workplace_node_id") or "").strip()

    # 2. D3 Crisis / Infirmary redirect when NPC's scheduled venue is locked by active World Pulse event
    events_payload = (
        active_events
        if isinstance(active_events, Mapping)
        else {"active_macro_events": [dict(e) for e in (active_events or ()) if isinstance(e, Mapping)]}
    )
    if scheduled_node and active_events and is_node_locked_by_event(events_payload, scheduled_node):
        safe_fallback = str(npc.get("home_node_id") or npc.get("hangout_node_id") or "").strip()
        if not safe_fallback and "high_school" in _norm_key(scen_key):
            safe_fallback = "loc_school_infirmary"
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
            truant_node = str(npc.get("hangout_node_id") or "loc_rooftop").strip()
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

    # 4. D14 High-affinity (Affinity >= 75) casual drop-by to player home node (~20% on free blocks)
    aff = _contact_affinity(npc)
    if aff < 75:
        aff = max(aff, _contact_affinity(basic))
    home_dest = str(player_home_node_id or "").strip()
    if aff >= 75 and home_dest and home_dest != str(npc.get("home_node_id") or "").strip():
        if _det_unit(f"{session_id}:{cur_day}:{cur_block}:{nkey}:dropby") < 2000:
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
        start_idx = _BLOCK_SEQUENCE.index(old_b) if d_off == 0 and old_b in _BLOCK_SEQUENCE else 0
        end_idx = _BLOCK_SEQUENCE.index(new_b) if cur_d == nd and new_b in _BLOCK_SEQUENCE else len(_BLOCK_SEQUENCE) - 1
        for b_idx in range(start_idx, end_idx + 1):
            ticks.append((cur_d, _BLOCK_SEQUENCE[b_idx]))
    return ticks


def _resolve_npc_block_venue(row: Mapping[str, Any], block: str) -> str:
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
    for t in all_ties or ():
        if str(t.get("status") or "active").lower() != "active":
            continue
        pa = _norm_key(t.get("person_a_key"))
        pb = _norm_key(t.get("person_b_key"))
        if not pa or not pb:
            continue
        if _is_player_ref(pa) or _is_player_ref(pb):
            player_ties.append(t)
        else:
            ties_by_pair[(min(pa, pb), max(pa, pb))] = t

    active_roster = [
        r for r in roster_rows
        if _norm_key(r.get("person_key") or r.get("npc_id") or r.get("name"))
        and _norm_key(r.get("staff_status") or "active") not in ("deceased", "departed", "removed")
    ]
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
            vnode = _resolve_npc_block_venue(r, tick_block)
            if vnode:
                by_venue.setdefault(vnode, []).append(r)

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

                # D8 milestone hangout shift when high closeness forms around a shared hangout venue
                prev_close = float((existing_tie or {}).get("closeness") or 0.0)
                if (prev_close + final_delta) >= 70.0 and len(milestone_shifted) < 2:
                    shared_hangout = str(b_row.get("hangout_node_id") or vnode).strip()
                    if shared_hangout and ka not in milestone_shifted and str(a_row.get("hangout_node_id") or "").strip() != shared_hangout:
                        milestone_shifted.add(ka)
                        roster_mutations.append({
                            "npc_id": str(a_row.get("npc_id") or ka),
                            "hangout_node_id": shared_hangout,
                        })

                # D9 drama gossip on intense affection/rivalry spark
                if (prev_close + final_delta) >= 65.0 and len(gossip_posts) < 1:
                    name_a = str(a_row.get("name") or p_low)
                    name_b = str(b_row.get("name") or p_high)
                    gossip_posts.append({
                        "day": tick_day,
                        "block": tick_block,
                        "actor_keys": [p_low, p_high],
                        "summary": f"{name_a} and {name_b} were spotted together near {vnode}.",
                    })
                    if has_phone and drama_dms_emitted == 0:
                        drama_dms_emitted += 1
                        dm_pings.append({
                            "kind": "drama_gossip",
                            "sender_key": p_low,
                            "subject_keys": [p_low, p_high],
                            "day": tick_day,
                            "summary": f"Did you hear about {name_a} and {name_b}?",
                        })

    # D10 / D11 hangout ping on wake-up (Affinity >= 50, capped at 1 hangout ping + phone gated)
    if has_phone and hangout_pings_emitted == 0:
        last_day, last_block = ticks[-1]
        eligible_friends = []
        for c in contacts or ():
            if _contact_affinity(c) >= 50 and not c.get("in_party") and not c.get("is_blocked"):
                ckey = _norm_key(c.get("npc_id") or c.get("person_key") or c.get("name"))
                if ckey:
                    eligible_friends.append((ckey, c))
        eligible_friends.sort(key=lambda item: item[0])
        for ckey, c in eligible_friends:
            if _det_unit(f"{sid}:{last_day}:{last_block}:{ckey}:hangout_ping") < 3500:
                hangout_pings_emitted += 1
                cname = str(c.get("name") or ckey)
                ping_node = str(c.get("hangout_node_id") or "").strip()
                dm_pings.append({
                    "kind": "hangout_invite",
                    "sender_key": ckey,
                    "sender_name": cname,
                    "node_id": ping_node,
                    "day": last_day,
                    "summary": f"Hey, want to swing by and hang out?",
                })
                roster_mutations.append({
                    "npc_id": str(c.get("npc_id") or ckey),
                    "pending_hangout_ping": {
                        "day": last_day,
                        "block": last_block,
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
