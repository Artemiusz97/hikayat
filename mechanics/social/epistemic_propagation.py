from __future__ import annotations

"""
Deterministic Epistemic Propagation, Boundary Resolution, and Signal Fencing (Part B).

Split from `mechanics.social.epistemic_engine` so both modules stay concise and cycle-free:
- Shared actor/role/concealment/kin helpers used across scene detection and propagation.
- Boundary-tick lifecycle transitions (`spotted_window -> active`), B8 daily rumor heat decay,
  B4 1-hop gossip propagation & corroboration, B16 kin/roommate alerts, B5 busted-alibi double
  penalties, and B11 Watch-role faction rep + active summons escalations.
- B15 server-side fencing of LLM `EpistemicSignal` outputs (including B6 `npc_secret_uncovered`).
"""

import json
import random
import time
from typing import Any, Mapping, Sequence

import db
from mechanics.world.world_events.social_hooks import _KIN_AND_PARTNER_TOKENS, _WATCH_ROLE_TOKENS

_CONCEALING_GARMENT_TOKENS: tuple[str, ...] = (
    "mask",
    "veil",
    "balaclava",
    "hood_down",
    "hood pulled",
    "lowered hood",
    "concealed_face",
    "visor",
    "domino",
    "face_scarf",
    "bandana_mask",
)
_REMOVED_GARMENT_PREFIXES: tuple[str, ...] = ("removed", "none (", "stripped")
_CONCEALABLE_EQUIP_SLOTS: frozenset[str] = frozenset({
    "headwear",
    "head",
    "mask",
    "face",
    "accessory",
    "outerwear",
})


def _norm_key(val: Any) -> str:
    return str(val or "").strip().lower()


def _parse_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            loaded = json.loads(raw)
            return dict(loaded) if isinstance(loaded, Mapping) else {}
        except Exception:
            return {}
    return {}


def _actor_key(npc: Any) -> str:
    if isinstance(npc, Mapping):
        for field in ("person_key", "npc_id", "npc_key", "holder_actor_key", "name"):
            v = _norm_key(npc.get(field))
            if v:
                return v
        return ""
    return _norm_key(npc)


def _npc_aliases(npc: Mapping[str, Any]) -> set[str]:
    out: set[str] = set()
    for field in ("person_key", "npc_id", "npc_key", "name"):
        v = _norm_key(npc.get(field))
        if v:
            out.add(v)
    return out


def _is_watch_role(npc: Mapping[str, Any]) -> bool:
    basic = _parse_dict(npc.get("basic_info") or npc.get("basic_info_json"))
    blob = " ".join(
        str(x or "").lower()
        for x in (npc.get("role"), npc.get("occupation"), npc.get("faction"), basic.get("role"), basic.get("occupation"))
    )
    return any(tok in blob for tok in _WATCH_ROLE_TOKENS)


def _is_active_concealing_slot_value(val: Any) -> bool:
    """Returns True only when a garment slot/item string actively conceals the face."""
    if isinstance(val, Mapping):
        st = str(val.get("state") or "").strip().lower()
        if st in ("removed", "none", "stripped"):
            return False
        text = " ".join(str(x or "") for x in (val.get("item_name"), val.get("name"), st)).strip().lower()
    else:
        text = str(val or "").strip().lower()
    if not text or text == "none" or text.startswith(_REMOVED_GARMENT_PREFIXES):
        return False
    return any(tok in text for tok in _CONCEALING_GARMENT_TOKENS)


def extract_player_concealment_garments(
    session: Mapping[str, Any],
    *,
    session_id: int = 0,
    phys_state: Mapping[str, Any] | None = None,
    party: Sequence[Any] | None = None,
) -> dict[str, str]:
    """Extracts active player garment slots and equipped headwear/mask items for B13 witness anonymization."""
    sess = session if isinstance(session, Mapping) else {}
    sid = int(session_id or sess.get("id") or 0)
    out: dict[str, str] = {}

    party_src = party if party is not None else sess.get("party")
    party_arg = list(party_src) if isinstance(party_src, (list, tuple)) else None

    ps = phys_state if isinstance(phys_state, Mapping) else sess.get("physical_state")
    if (not isinstance(ps, Mapping) or not isinstance(ps.get("actors"), Mapping)) and sid > 0:
        loaded_ps = db.get_session_physical_state(sid)
        if isinstance(loaded_ps, Mapping):
            ps = loaded_ps

    if isinstance(ps, Mapping) and isinstance(ps.get("actors"), Mapping):
        actors_map = ps["actors"]
        player_entry: Mapping[str, Any] | None = None
        for actor_val in actors_map.values():
            if isinstance(actor_val, Mapping) and _norm_key(actor_val.get("actor_type")) == "player":
                player_entry = actor_val
                break
        if player_entry is None:
            from mechanics.social.physical_state import find_player_actor_key

            p_key = find_player_actor_key(dict(actors_map), party=party_arg, session_id=sid)
            if p_key and isinstance(actors_map.get(p_key), Mapping):
                player_entry = actors_map[p_key]
        if player_entry is None and isinstance(actors_map.get("player"), Mapping):
            player_entry = actors_map["player"]
        if isinstance(player_entry, Mapping):
            clothing = player_entry.get("clothing")
            if isinstance(clothing, Mapping):
                for slot_k, slot_v in clothing.items():
                    s_text = str(slot_v or "").strip()
                    s_low = s_text.lower()
                    if not s_text or s_low == "none" or s_low.startswith(_REMOVED_GARMENT_PREFIXES):
                        continue
                    out[str(slot_k)] = s_text

    inv_items: list[Mapping[str, Any]] = []
    if isinstance(party_src, (list, tuple)) and party_src:
        for idx, entry in enumerate(party_src):
            if isinstance(entry, (list, tuple)) and len(entry) >= 2 and isinstance(entry[1], (list, tuple)):
                char_head = entry[0] if isinstance(entry[0], Mapping) else {}
                is_companion_npc = bool(
                    idx > 0 and (
                        char_head.get("is_npc")
                        or _norm_key(char_head.get("actor_type")) == "npc"
                        or char_head.get("npc_id")
                    ) and not char_head.get("user_id")
                )
                if is_companion_npc:
                    continue
                for item in entry[1]:
                    if isinstance(item, Mapping):
                        inv_items.append(item)
            elif isinstance(entry, Mapping):
                is_companion_npc = bool(
                    idx > 0 and (
                        entry.get("is_npc")
                        or _norm_key(entry.get("actor_type")) == "npc"
                        or entry.get("npc_id")
                    ) and not entry.get("user_id")
                )
                if is_companion_npc:
                    continue
                if isinstance(entry.get("inventory"), (list, tuple)):
                    for item in entry["inventory"]:
                        if isinstance(item, Mapping):
                            inv_items.append(item)
                elif isinstance(entry.get("equipment"), Mapping):
                    for eq_slot, eq_item in entry["equipment"].items():
                        if isinstance(eq_item, Mapping):
                            item_copy = dict(eq_item)
                            item_copy.setdefault("slot", eq_slot)
                            item_copy.setdefault("equipped", True)
                            inv_items.append(item_copy)
                elif entry.get("slot") is not None and (entry.get("name") or entry.get("item_name")):
                    inv_items.append(entry)
    elif party is None and not party_src and (sess.get("character_id") or sess.get("host_user_id")):
        char_id = int(sess.get("character_id") or 0)
        host_uid = int(sess.get("host_user_id") or 0)
        char_row = db.get_character_by_id(char_id) if char_id > 0 else None
        effective_uid = host_uid or int((char_row or {}).get("user_id") or 0)
        if effective_uid or char_row:
            for item in db.get_inventory(effective_uid, char=char_row) or ():
                if isinstance(item, Mapping):
                    inv_items.append(item)

    for item in inv_items:
        if "equipped" in item and not bool(item.get("equipped")):
            continue
        if item.get("equipped") is False:
            continue
        slot_low = str(item.get("slot") or "").strip().lower()
        if slot_low in _CONCEALABLE_EQUIP_SLOTS:
            item_name = str(item.get("name") or item.get("item_name") or "").strip()
            if item_name:
                eq_key = f"equipped_{slot_low}"
                out[eq_key] = f"{out[eq_key]}, {item_name}" if eq_key in out else item_name

    return out


def _is_face_concealed(session: Mapping[str, Any], act_payload: Mapping[str, Any]) -> bool:
    if act_payload.get("culprit_masked") or act_payload.get("face_concealed"):
        return True
    containers: list[Any] = []
    if act_payload.get("actor_garments"):
        containers.append(act_payload.get("actor_garments"))
    if session.get("actor_garments"):
        containers.append(session.get("actor_garments"))
    if not containers:
        extracted = extract_player_concealment_garments(session, session_id=int(session.get("id") or 0))
        if extracted:
            containers.append(extracted)
    for container in containers:
        if isinstance(container, str) and not container.strip().startswith("{"):
            if _is_active_concealing_slot_value(container):
                return True
            continue
        garments = _parse_dict(container)
        player_g = garments.get("player") if isinstance(garments.get("player"), Mapping) else garments
        if isinstance(player_g, Mapping):
            for slot_v in player_g.values():
                if isinstance(slot_v, Mapping):
                    if "state" in slot_v or "item_name" in slot_v:
                        if _is_active_concealing_slot_value(slot_v):
                            return True
                    else:
                        for nested_v in slot_v.values():
                            if _is_active_concealing_slot_value(nested_v):
                                return True
                elif isinstance(slot_v, (list, tuple)):
                    if any(_is_active_concealing_slot_value(x) for x in slot_v):
                        return True
                elif _is_active_concealing_slot_value(slot_v):
                    return True
    return False


def _is_kin_roommate_or_best_friend(
    subject_key: str,
    holder_key: str,
    *,
    social_ties: Sequence[Mapping[str, Any]] = (),
    households: Sequence[Mapping[str, Any]] = (),
    contacts: Sequence[Mapping[str, Any]] = (),
    roster_map: Mapping[str, Mapping[str, Any]] | None = None,
) -> bool:
    skey = _norm_key(subject_key)
    hkey = _norm_key(holder_key)
    if not skey or not hkey or skey == hkey:
        return False

    # 1. Social ties: best_friend, romantic partners, or explicit kin metadata
    for t in social_ties or ():
        if str(t.get("status") or "active").lower() != "active":
            continue
        pa = _norm_key(t.get("person_a_key"))
        pb = _norm_key(t.get("person_b_key"))
        if {pa, pb} != {skey, hkey}:
            continue
        ttype = _norm_key(t.get("tie_type"))
        if ttype in ("best_friend", "married", "engaged", "dating", "sibling", "family", "roommate"):
            return True
        meta_blob = f"{ttype} {t.get('role') or ''} {json.dumps(t.get('metadata') or {}, default=str)}".lower()
        if any(tok in meta_blob for tok in (*_KIN_AND_PARTNER_TOKENS, "best_friend", "best friend", "roommate", "housemate")):
            return True

    # 2. Households (either normalized household dicts with member_keys, or roster rows sharing household_id)
    for hh in households or ():
        members: set[str] = set()
        raw_m = hh.get("members") or hh.get("member_keys") or ()
        for m in raw_m:
            mk = _actor_key(m)
            if mk:
                members.add(mk)
        if skey in members and hkey in members:
            return True

    if roster_map:
        s_row = roster_map.get(skey) or {}
        h_row = roster_map.get(hkey) or {}
        shid = s_row.get("household_id")
        hhid = h_row.get("household_id")
        if shid and hhid and str(shid) == str(hhid):
            return True
        shome = _norm_key(s_row.get("home_node_id"))
        hhome = _norm_key(h_row.get("home_node_id"))
        if shome and hhome and shome == hhome and (shome != "" and not shome.startswith("loc_dorm_public")):
            return True

    # 3. Contacts relationship text fallback
    for c in contacts or ():
        ck = _actor_key(c)
        if ck in (skey, hkey):
            rel_blob = f"{c.get('relationship') or ''} {c.get('kinship') or ''} {c.get('family_role') or ''}".lower()
            if (skey in rel_blob or hkey in rel_blob) and any(
                tok in rel_blob for tok in (*_KIN_AND_PARTNER_TOKENS, "best friend", "roommate")
            ):
                return True

    return False


def _resolve_npc_schedule_node(row: Mapping[str, Any], bell_slot: str) -> str:
    b = _norm_key(bell_slot)
    if b in ("morning", "afternoon"):
        return str(row.get("workplace_node_id") or row.get("home_node_id") or "").strip()
    if b in ("lunch", "evening"):
        return str(row.get("hangout_node_id") or row.get("workplace_node_id") or "").strip()
    return str(row.get("home_node_id") or "").strip()


def _apply_b5_contact_trust_penalty(session_id: int, holder_key: str, *, conn=None) -> None:
    sql = (
        "UPDATE contacts SET relationship_score = MAX(-100, COALESCE(relationship_score, 0) - 20) "
        "WHERE session_id = ? AND (LOWER(npc_id) = ? OR LOWER(REPLACE(TRIM(name), ' ', '_')) = ?)"
    )
    if conn is not None:
        conn.execute(sql, (session_id, holder_key, holder_key))
        return
    with db.get_conn() as local_conn:
        local_conn.execute(sql, (session_id, holder_key, holder_key))


def _apply_b11_watch_escalation_effects(
    session_id: int,
    fact_key: str,
    faction_name: str,
    severity: int,
    summary: str,
    turn: int,
    *,
    conn=None,
) -> None:
    """Applies B11 Watch faction reputation loss and active summons notice without nested write locks."""
    fac_name = (faction_name or "Town Watch").strip() or "Town Watch"
    rep_delta = -20 if severity >= 3 else -10
    if conn is None:
        db.upsert_faction(session_id, fac_name, delta_score=rep_delta)
        if severity >= 3:
            db.create_world_event(
                session_id,
                event_key=f"watch_summons_{fact_key}",
                entity_type="minor_event",
                event_subtype="summons",
                title=f"Authority Summons: {fac_name}",
                description=summary or "Summoned for questioning regarding reported misconduct.",
                faction_id=fac_name.lower().replace(" ", "_"),
                turn_created=turn,
            )
        return

    fac_id = fac_name.lower().replace(" ", "_")
    now = time.time()
    existing_fac = conn.execute(
        "SELECT id, reputation_score FROM factions WHERE session_id = ? AND faction_id = ?",
        (session_id, fac_id),
    ).fetchone()
    if existing_fac:
        cur_score = int(existing_fac["reputation_score"] if hasattr(existing_fac, "keys") else existing_fac[1])
        row_id = existing_fac["id"] if hasattr(existing_fac, "keys") else existing_fac[0]
        conn.execute(
            "UPDATE factions SET reputation_score = ?, updated_at = ? WHERE id = ?",
            (max(-100, min(100, cur_score + rep_delta)), now, row_id),
        )
    else:
        conn.execute(
            """INSERT INTO factions (
                session_id, faction_id, name, reputation_score, perks_json, notes,
                category, hq_location_id, hq_node_id, hierarchy_template,
                leadership_roster_json, rival_faction_ids_json, allied_faction_ids_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, '[]', '', 'default', '', '', 'default', '[]', '[]', '[]', ?, ?)""",
            (session_id, fac_id, fac_name, max(-100, min(100, rep_delta)), now, now),
        )

    if severity >= 3:
        evt_key = f"watch_summons_{fact_key}"
        exists_evt = conn.execute(
            "SELECT id FROM world_events WHERE session_id = ? AND event_key = ?",
            (session_id, evt_key),
        ).fetchone()
        if not exists_evt:
            desc = summary or "Summoned for questioning regarding reported misconduct."
            conn.execute(
                """INSERT INTO world_events (
                    session_id, event_key, template_key, entity_type, event_subtype,
                    title, description, sfw_fallback_description, faction_id, implicated_contact_id,
                    location_node_id, location_name, is_discovered, discovery_source,
                    discovered_turn, claimed_turn, linked_quest_id, status,
                    prior_status_before_resolve, turn_created, resolved_turn,
                    original_expires_day, original_expires_minute,
                    expires_day, expires_minute, escalation_chance, escalation_event_key,
                    is_nsfw, modifiers_json, metadata_json, created_at, updated_at
                ) VALUES (?, ?, '', 'minor_event', 'summons', ?, ?, '', ?, NULL, '', '', 1, 'bulletin', ?, NULL, '', 'active', 'active', ?, NULL, NULL, NULL, NULL, NULL, 0.0, '', 0, '{}', '{}', ?, ?)""",
                (session_id, evt_key, f"Authority Summons: {fac_name}", desc, fac_id, turn, turn, now, now),
            )


def tick_epistemic_boundary_propagation(
    session_id: int,
    session: Mapping[str, Any],
    day: int,
    bell_slot: str,
    roster_map: Mapping[str, Mapping[str, Any]],
    social_ties: Sequence[Mapping[str, Any]],
    households: Sequence[Mapping[str, Any]],
    rng: random.Random | Any,
    turn: int,
    *,
    contacts: Sequence[Mapping[str, Any]] = (),
    conn=None,
) -> dict[str, Any]:
    """
    Runs boundary-tick epistemic simulation:
    - B3 `spotted_window -> active` transition on bell crossing
    - B8 daily rumor heat decay (`-10/day`, `status='decayed'` at 0)
    - B4 1-hop gossip propagation (`player_aware=0`) + 2+ firsthand source corroboration
    - B5 Caught Lying busted-alibi check (-20 trust penalty & +20 heat)
    - B16 kin/roommate/best_friend automatic next-block alert on active uncontained facts
    - B11 Watch-role faction rep deductions & summons notices
    """
    sid = int(session_id or 0)
    cur_day = max(1, int(day or 1))
    t_num = int(turn or 0)
    empty = {
        "propagated": [],
        "corroborated": [],
        "busted_alibis": [],
        "decayed": [],
        "escalations": [],
        "kin_alerts": [],
    }
    if not sid:
        return empty

    matrix = db.preload_epistemic_matrix(sid, conn=conn)
    facts_by_key = matrix["facts_by_key"]
    by_fact = matrix["by_fact"]
    if not facts_by_key:
        return empty

    norm_roster: dict[str, Mapping[str, Any]] = {_norm_key(k): v for k, v in (roster_map or {}).items() if _norm_key(k)}
    propagated: list[dict[str, Any]] = []
    corroborated: list[dict[str, Any]] = []
    busted_alibis: list[dict[str, Any]] = []
    decayed: list[dict[str, Any]] = []
    escalations: list[dict[str, Any]] = []
    kin_alerts: list[dict[str, Any]] = []

    # Build neighbor map from social_ties + households + same schedule node
    neighbors: dict[str, set[str]] = {}
    for t in social_ties or ():
        if str(t.get("status") or "active").lower() != "active":
            continue
        pa = _norm_key(t.get("person_a_key"))
        pb = _norm_key(t.get("person_b_key"))
        if not pa or not pb or pa == "player" or pb == "player":
            continue
        closeness = float(t.get("closeness") or 0.0)
        ttype = _norm_key(t.get("tie_type"))
        if closeness >= 35.0 or ttype in ("friend", "best_friend", "dating", "engaged", "married", "rival"):
            neighbors.setdefault(pa, set()).add(pb)
            neighbors.setdefault(pb, set()).add(pa)

    node_groups: dict[str, list[str]] = {}
    for nk, r in norm_roster.items():
        if _norm_key(r.get("staff_status") or "active") in ("deceased", "wiped", "removed"):
            continue
        node = _resolve_npc_schedule_node(r, bell_slot)
        if node:
            node_groups.setdefault(node, []).append(nk)
    for group in node_groups.values():
        if len(group) >= 2:
            for a in group:
                for b in group:
                    if a != b:
                        neighbors.setdefault(a, set()).add(b)

    for hh in households or ():
        mkeys = [_actor_key(m) for m in (hh.get("members") or hh.get("member_keys") or ()) if _actor_key(m)]
        for a in mkeys:
            for b in mkeys:
                if a != b:
                    neighbors.setdefault(a, set()).add(b)

    # 0. B3 Transition uncontained spotted_window holders -> active on boundary tick
    for fkey, fact in facts_by_key.items():
        if fact.get("status") != "active":
            continue
        holders = by_fact.get(fkey) or {}
        for hk, hrow in list(holders.items()):
            if hrow.get("containment_state") == "spotted_window":
                holders[hk] = db.upsert_epistemic_knowledge(
                    sid,
                    fkey,
                    hk,
                    containment_state="active",
                    turn=t_num,
                    conn=conn,
                )

    # 1. B8 Decay on uncorroborated rumor-only facts
    for fkey, fact in list(facts_by_key.items()):
        if fact.get("status") != "active":
            continue
        last_tick = int(fact.get("decay_day_last_ticked") or cur_day)
        holders = by_fact.get(fkey) or {}
        if cur_day > last_tick:
            has_hard_or_firsthand = any(
                h.get("confidence") in ("firsthand", "hard_proof")
                and h.get("containment_state") not in ("wiped", "incapacitated", "decayed")
                for h in holders.values()
            )
            if not has_hard_or_firsthand:
                elapsed = max(1, cur_day - last_tick)
                old_heat = int(fact.get("heat_score") or 0)
                new_heat = max(0, old_heat - 10 * elapsed)
                new_status = "decayed" if new_heat == 0 else "active"
                db.upsert_epistemic_fact(
                    sid,
                    fkey,
                    heat_score=new_heat,
                    decay_day_last_ticked=cur_day,
                    status=new_status,
                    turn=t_num,
                    conn=conn,
                )
                fact["heat_score"] = new_heat
                fact["status"] = new_status
                if new_status == "decayed":
                    decayed.append({"fact_key": fkey, "heat_score": 0})
            else:
                db.upsert_epistemic_fact(sid, fkey, decay_day_last_ticked=cur_day, turn=t_num, conn=conn)

    # 2. B4 Propagation, Corroboration, B16 Kin Alert, B5 Alibi Bust & B11 Escalation
    for fkey, fact in facts_by_key.items():
        if fact.get("status") != "active":
            continue
        holders = by_fact.get(fkey) or {}
        firsthand_active_holders = [
            hk for hk, h in holders.items()
            if h.get("containment_state") == "active" and h.get("confidence") in ("firsthand", "hard_proof")
        ]
        active_holders = [
            (hk, h) for hk, h in holders.items()
            if h.get("containment_state") == "active"
        ]

        # B16: Alert wronged subject's kin/roommate/best_friend when uncontained high-severity active witness exists
        subject_k = _norm_key(fact.get("subject_actor_key"))
        if subject_k and int(fact.get("severity") or 1) >= 2 and active_holders:
            for cand_k in sorted(norm_roster.keys()):
                if cand_k in holders or cand_k == subject_k:
                    continue
                if _is_kin_roommate_or_best_friend(
                    subject_k,
                    cand_k,
                    social_ties=social_ties,
                    households=households,
                    contacts=contacts,
                    roster_map=norm_roster,
                ):
                    src_k = active_holders[0][0]
                    new_row = db.upsert_epistemic_knowledge(
                        sid,
                        fkey,
                        cand_k,
                        confidence="firsthand",
                        containment_state="active",
                        source_actor_key=src_k,
                        acquisition_channel="kin_alert",
                        hop_count=1,
                        player_aware=0,
                        turn=t_num,
                        conn=conn,
                    )
                    holders[cand_k] = new_row
                    kin_alerts.append({"fact_key": fkey, "holder_actor_key": cand_k, "subject_actor_key": subject_k})

        # B4: 1-hop gossip propagation (player_aware=0) & multi-source corroboration
        new_hops_this_fact = 0
        for src_k, src_row in sorted(active_holders):
            if new_hops_this_fact >= 4:
                break
            src_hop = int(src_row.get("hop_count") or 0)
            src_conf = str(src_row.get("confidence") or "rumor")
            for rec_k in sorted(neighbors.get(src_k, ())):
                if rec_k in norm_roster and _norm_key(norm_roster[rec_k].get("staff_status")) in ("deceased", "wiped"):
                    continue
                rec_existing = holders.get(rec_k)
                if rec_existing:
                    # Track independent firsthand corroboration
                    if src_conf in ("firsthand", "hard_proof") and rec_existing.get("confidence") == "rumor":
                        meta = _parse_dict(rec_existing.get("metadata"))
                        sources = {str(s) for s in (meta.get("corroborating_sources") or ()) if s}
                        if rec_existing.get("source_actor_key"):
                            sources.add(str(rec_existing["source_actor_key"]))
                        sources.add(src_k)
                        if len(sources) >= 2:
                            updated = db.upsert_epistemic_knowledge(
                                sid,
                                fkey,
                                rec_k,
                                confidence="firsthand",
                                metadata={**meta, "corroborating_sources": sorted(sources)},
                                turn=t_num,
                                conn=conn,
                            )
                            holders[rec_k] = updated
                            corroborated.append({"fact_key": fkey, "holder_actor_key": rec_k, "sources": sorted(sources)})
                    continue

                if len(firsthand_active_holders) >= 2:
                    prob = 0.75
                else:
                    prob = 0.50 if src_conf in ("firsthand", "hard_proof") else 0.25
                roll = float(rng.random()) if hasattr(rng, "random") else 0.0
                if roll >= prob:
                    continue

                inserted = db.upsert_epistemic_knowledge(
                    sid,
                    fkey,
                    rec_k,
                    confidence="rumor",
                    containment_state="active",
                    source_actor_key=src_k,
                    acquisition_channel="gossip",
                    hop_count=src_hop + 1,
                    player_aware=0,
                    metadata={"corroborating_sources": [src_k]},
                    turn=t_num,
                    conn=conn,
                )
                holders[rec_k] = inserted
                propagated.append({
                    "fact_key": fkey,
                    "holder_actor_key": rec_k,
                    "source_actor_key": src_k,
                    "hop_count": src_hop + 1,
                    "player_aware": 0,
                })
                new_hops_this_fact += 1
                if new_hops_this_fact >= 4:
                    break

        # B5: Caught Lying check across all holders with an unbusted alibi_claim
        for hk, hrow in list(holders.items()):
            if not str(hrow.get("alibi_claim") or "").strip() or int(hrow.get("is_alibi_busted") or 0):
                continue
            wkey = _norm_key(hrow.get("alibi_witness_key"))
            w_prepped = bool(
                wkey
                and holders.get(wkey, {}).get("containment_state") in ("co_conspirator", "hushed")
            )
            meets_witness = bool(wkey and (wkey in neighbors.get(hk, ()) or not norm_roster))
            unprepped_witness_contradicts = bool(wkey and meets_witness and not w_prepped)
            h_meta = _parse_dict(hrow.get("metadata"))
            h_sources = {str(s) for s in (h_meta.get("corroborating_sources") or ()) if s}
            hard_contradiction = (
                hrow.get("confidence") == "hard_proof"
                or len(h_sources) >= 2
                or len([x for x in firsthand_active_holders if x != hk]) >= 2
            )
            if unprepped_witness_contradicts or hard_contradiction:
                already_penalized = bool(h_meta.get("b5_trust_penalty_applied"))
                new_meta = dict(h_meta)
                new_meta["b5_trust_penalty_applied"] = True
                holders[hk] = db.upsert_epistemic_knowledge(
                    sid,
                    fkey,
                    hk,
                    containment_state="active",
                    is_alibi_busted=1,
                    player_aware=1,
                    metadata=new_meta,
                    turn=t_num,
                    conn=conn,
                )
                db.upsert_epistemic_fact(
                    sid,
                    fkey,
                    heat_score=min(100, int(fact.get("heat_score") or 50) + 20),
                    turn=t_num,
                    conn=conn,
                )
                if not already_penalized:
                    _apply_b5_contact_trust_penalty(sid, hk, conn=conn)
                busted_alibis.append({
                    "fact_key": fkey,
                    "holder_actor_key": hk,
                    "alibi_witness_key": wkey,
                    "trust_delta": -20,
                    "double_penalty": True,
                })

        # B11: Watch-role authority escalation (faction rep + active summons notice)
        if fact.get("category") in ("crime", "faction_breach", "anomaly"):
            for hk, hrow in list(holders.items()):
                if hrow.get("containment_state") != "active":
                    continue
                npc_meta = norm_roster.get(hk) or {}
                if not _is_watch_role(npc_meta):
                    continue
                w_meta = _parse_dict(hrow.get("metadata"))
                if w_meta.get("b11_escalated"):
                    continue
                if hrow.get("confidence") in ("firsthand", "hard_proof") or int(fact.get("heat_score") or 0) >= 60:
                    sev = int(fact.get("severity") or 1)
                    esc_type = "summons" if sev >= 3 else "faction_rep"
                    fac_name = str(npc_meta.get("faction") or "Town Watch").strip() or "Town Watch"
                    holders[hk] = db.upsert_epistemic_knowledge(
                        sid,
                        fkey,
                        hk,
                        metadata={**w_meta, "b11_escalated": True},
                        turn=t_num,
                        conn=conn,
                    )
                    _apply_b11_watch_escalation_effects(
                        sid,
                        fkey,
                        fac_name,
                        sev,
                        str(fact.get("summary") or ""),
                        t_num,
                        conn=conn,
                    )
                    escalations.append({
                        "fact_key": fkey,
                        "holder_actor_key": hk,
                        "escalation_type": esc_type,
                        "severity": sev,
                        "faction": fac_name,
                        "rep_delta": -20 if sev >= 3 else -10,
                    })
                    break

    return {
        "propagated": propagated,
        "corroborated": corroborated,
        "busted_alibis": busted_alibis,
        "decayed": decayed,
        "escalations": escalations,
        "kin_alerts": kin_alerts,
    }


def _extract_present_actor_keys(present_npcs: Sequence[Any]) -> set[str]:
    keys: set[str] = set()
    for item in present_npcs or ():
        if isinstance(item, Mapping):
            keys |= _npc_aliases(item)
        else:
            k = _norm_key(item)
            if k:
                keys.add(k)
    return keys


def _is_proof_ref_held(
    proof_ref: str,
    held_item_ids: Sequence[Any],
    clue_ids: Sequence[Any],
) -> bool:
    pref = str(proof_ref or "").strip()
    if not pref:
        return False
    norm_items = {str(x).strip() for x in (held_item_ids or ()) if str(x or "").strip()}
    norm_clues = {str(x).strip() for x in (clue_ids or ()) if str(x or "").strip()}
    if ":" in pref:
        prefix, ident = pref.split(":", 1)
        prefix = prefix.lower().strip()
        if prefix in ("inv", "photo"):
            return ident in norm_items or pref in norm_items
        if prefix == "clue":
            return ident in norm_clues or pref in norm_clues
        if prefix == "dm":
            return (pref in norm_items) or (pref in norm_clues)
    return (pref in norm_items) or (pref in norm_clues)


def resolve_fenced_epistemic_signal(
    session_id: int,
    raw_signal: Any,
    *,
    present_npcs: Sequence[Any],
    held_item_ids: Sequence[Any] = (),
    clue_ids: Sequence[Any] = (),
    turn: int = 0,
    conn=None,
) -> list[dict[str, Any]]:
    """
    B15: Validates narrator `EpistemicSignal` outputs against present scene NPCs and real held proofs.
    Supports B6 `npc_secret_uncovered` (player becomes aware holder of target NPC's secret)
    and drops hallucinated actors/proofs while capping commits to <= 3 per turn.
    """
    sid = int(session_id or 0)
    if not sid or not raw_signal:
        return []

    signals = [raw_signal] if isinstance(raw_signal, Mapping) else (list(raw_signal) if isinstance(raw_signal, (list, tuple)) else [])
    present_keys = _extract_present_actor_keys(present_npcs)
    committed: list[dict[str, Any]] = []
    t_num = int(turn or 0)

    for sig in signals[:3]:
        if isinstance(sig, Mapping):
            sig_d = dict(sig)
        elif hasattr(sig, "model_dump"):
            sig_d = sig.model_dump()
        else:
            continue

        target_npc = _norm_key(sig_d.get("target_npc"))
        if target_npc and target_npc not in present_keys:
            continue
        if not target_npc and present_keys:
            continue

        raw_proof = str(sig_d.get("proof_ref") or "").strip()
        verified_proof = raw_proof if _is_proof_ref_held(raw_proof, held_item_ids, clue_ids) else ""
        conf = _norm_key(sig_d.get("confidence")) or "rumor"
        if conf == "hard_proof" and not verified_proof:
            conf = "rumor"
        if conf not in ("rumor", "firsthand", "hard_proof"):
            conf = "rumor"

        kind = _norm_key(sig_d.get("kind")) or "secret_revealed"
        fkey = str(sig_d.get("fact_key") or f"sig_{kind}_{target_npc}_{t_num}").strip()
        summary = str(sig_d.get("summary") or f"{kind} involving {target_npc}").strip()[:220]
        cat = str(sig_d.get("category") or "secret").strip().lower()

        is_npc_secret = kind in ("npc_secret_uncovered", "npc_secret_learned", "uncovered_npc_secret") and bool(target_npc)
        culprit = target_npc if is_npc_secret else "player"
        cat_final = "npc_secret" if is_npc_secret else (cat if cat in db.ALLOWED_FACT_CATEGORIES else "secret")
        holder_key = "player" if is_npc_secret else target_npc
        source_key = target_npc if is_npc_secret else "player"

        db.upsert_epistemic_fact(
            sid,
            fkey,
            category=cat_final,
            culprit_actor_key=culprit,
            summary=summary,
            proof_artifact_ref=verified_proof,
            status="active",
            turn=t_num,
            conn=conn,
        )
        if holder_key:
            db.upsert_epistemic_knowledge(
                sid,
                fkey,
                holder_key,
                confidence=conf,
                containment_state="active",
                source_actor_key=source_key,
                acquisition_channel=kind,
                player_aware=1,
                turn=t_num,
                conn=conn,
            )
        committed.append({
            "fact_key": fkey,
            "target_npc": target_npc,
            "holder_actor_key": holder_key,
            "confidence": conf,
            "proof_ref": verified_proof,
            "kind": kind,
        })

    return committed
