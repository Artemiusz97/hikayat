"""
mechanics/system/commitments_engine.py — Unified Commitments & Rendezvous Engine
================================================================================
Central service coordinator for all player and NPC commitments across both
modern (phone) and fantasy/historical scenarios.

Taxonomy (Minimal Binary Split):
  - 'rendezvous': Physical meetups at a specific location and time window.
  - 'promise': All non-spatial obligations (tasks, debts, pacts, secrets, oaths).

Lifecycle Statuses:
  - 'pending': Scheduled or agreed, waiting for start window or deadline.
  - 'approaching': 15 minutes before start window (triggers NPC schedule transit override).
  - 'arrived': Player or counterparty has arrived at the rendezvous location.
  - 'in_progress': In active dialogue or interaction at the location.
  - 'fulfilled': Successfully completed, debt repaid, or task resolved.
  - 'flaked': Missed deadline or appointment time elapsed (affinity loss & hurt memory).
  - 'abandoned': Player walked out mid-rendezvous without saying goodbye.
  - 'broken': Broken pledge, oath, or exposed secret.
  - 'cancelled': Gracefully cancelled in advance by player or NPC without penalty.
  - 'voided': NPC became incapacitated, arrested, or departed town.
"""
from __future__ import annotations
from contextlib import contextmanager
import json
import logging
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

import db
from db.core import get_conn

log = logging.getLogger("hikayat.commitments_engine")

VALID_COMMITMENT_TYPES = frozenset({"rendezvous", "promise"})
ACTIVE_STATUSES = frozenset({"pending", "approaching", "arrived", "in_progress", "active"})


@contextmanager
def _use_conn(conn_override: Optional[sqlite3.Connection] = None):
    if conn_override is not None:
        yield conn_override
    else:
        with get_conn() as conn:
            yield conn


def _canon_key(val: str) -> str:
    raw = str(val or "").strip()
    if not raw:
        return ""
    try:
        from mechanics.social.relationship_graph import canonical_person_key, is_player_person_key
        if is_player_person_key(raw):
            return "player"
        return canonical_person_key(raw)
    except Exception:
        return raw.lower().replace(" ", "_")


def _resolve_contact_row(session_id: int, entity_key: str) -> Optional[Dict[str, Any]]:
    """Resolves a contact row across slug/hyphen/space/case variations."""
    raw = str(entity_key or "").strip()
    if not session_id or not raw or raw == "group":
        return None
    if hasattr(db, "get_contact"):
        try:
            direct = db.get_contact(session_id, raw)
            if direct:
                return direct
        except Exception:
            pass
    if hasattr(db, "get_contacts"):
        try:
            target_ck = _canon_key(raw)
            for row in (db.get_contacts(session_id) or []):
                if (
                    str(row.get("npc_id") or "").strip().lower() == raw.lower()
                    or str(row.get("name") or "").strip().lower() == raw.lower()
                    or _canon_key(row.get("npc_id") or "") == target_ck
                    or _canon_key(row.get("name") or "") == target_ck
                ):
                    return row
        except Exception:
            pass
    return None


def _adjust_contact_affinity_delta(session_id: int, entity_key: str, delta: int) -> Optional[Dict[str, Any]]:
    """Applies a signed affinity delta to the matched contact via db.update_contact_score."""
    row = _resolve_contact_row(session_id, entity_key)
    if not row:
        return None
    new_score = max(-100, min(100, int(row.get("relationship_score") or 0) + int(delta)))
    if hasattr(db, "update_contact_score"):
        db.update_contact_score(session_id, row["npc_id"], new_score)
    row["relationship_score"] = new_score
    return row


def _compute_abs_window(c: Dict[str, Any]) -> Tuple[int, int]:
    """Computes monotonic absolute [start_min, end_min] across day boundaries (including midnight wrap-around)."""
    s_day = max(1, int(c.get("scheduled_day") or 1))
    s_min = max(0, int(c.get("start_minute") if c.get("start_minute") is not None else 0))
    raw_end = int(c.get("end_minute") if c.get("end_minute") is not None else 1439)
    if raw_end >= 1440:
        extra_days, e_min = divmod(raw_end, 1440)
        e_day = s_day + extra_days
    else:
        e_min = max(0, raw_end)
        if c.get("end_day") is not None:
            e_day = max(s_day, int(c["end_day"]))
        elif e_min < s_min:
            e_day = s_day + 1
        else:
            e_day = s_day
    abs_start = (s_day - 1) * 1440 + s_min
    abs_end = (e_day - 1) * 1440 + e_min
    return abs_start, abs_end


def _normalize_participants(
    organizer: str,
    participants: Optional[Union[List[Union[Dict[str, Any], str]], str]],
    primary_target: str = ""
) -> Tuple[str, List[Dict[str, Any]]]:
    """Normalizes participant lists into structured dicts with canonical person_key/npc_id, name, and status."""
    org_canon = _canon_key(organizer) or "player"
    norm: List[Dict[str, Any]] = [
        {"person_key": org_canon, "role": "organizer", "status": "active"}
    ]
    primary = _canon_key(primary_target) if primary_target else ""
    
    raw_list: List[Any] = []
    if isinstance(participants, list):
        raw_list = participants
    elif isinstance(participants, str) and participants.strip():
        raw_list = [participants.strip()]
    elif primary:
        raw_list = [primary]

    for p in raw_list:
        if isinstance(p, dict):
            raw_k = str(p.get("person_key") or p.get("npc_id") or p.get("name") or "").strip()
            p_key = _canon_key(raw_k)
            p_name = str(p.get("name") or p.get("npc_name") or raw_k or p_key).strip()
            if "_" in p_name and p_name == p_name.lower():
                p_name = p_name.replace("_", " ").title()
            p_role = str(p.get("role") or "participant").strip()
            p_stat = str(p.get("status") or "pending").strip()
            if p_key and p_key != org_canon:
                norm.append({
                    "person_key": p_key,
                    "npc_id": p_key,
                    "name": p_name or p_key,
                    "role": p_role,
                    "status": p_stat
                })
                if not primary:
                    primary = p_key
        elif isinstance(p, str) and p.strip():
            clean = p.strip()
            clean_key = _canon_key(clean)
            if clean_key and clean_key != org_canon:
                display_name = clean.replace("_", " ").title() if "_" in clean else clean
                norm.append({
                    "person_key": clean_key,
                    "npc_id": clean_key,
                    "name": display_name,
                    "role": "participant",
                    "status": "pending"
                })
                if not primary:
                    primary = clean_key

    return primary or (norm[1]["person_key"] if len(norm) > 1 else "target"), norm


# ---------------------------------------------------------------------------
# Creation & Ingestion
# ---------------------------------------------------------------------------

def create_rendezvous(
    session_id: int,
    organizer: str = "player",
    participants: Optional[Union[List[Union[Dict[str, Any], str]], str]] = None,
    location: str = "",
    day: int = 1,
    start_minute: int = 0,
    end_minute: int = 1439,
    *,
    end_day: Optional[int] = None,
    title: str = "",
    description: str = "",
    purpose: str = "",
    origin: str = "in_person",
    source_channel: str = "",
    node_id: Optional[str] = None,
    is_confidential: bool = False,
    metadata: Optional[Dict[str, Any]] = None,
    current_turn: int = 0,
    conn: Optional[sqlite3.Connection] = None,
    sync_legacy: bool = False
) -> Dict[str, Any]:
    """Creates a new physical rendezvous commitment in commitments_ledger."""
    if not location or not session_id:
        return {}

    org_canon = _canon_key(organizer) or "player"
    target_entity, norm_participants = _normalize_participants(org_canon, participants)
    if not node_id and hasattr(db, "resolve_node_id_from_location"):
        try:
            node_id = db.resolve_node_id_from_location(session_id, location)
        except Exception:
            node_id = ""

    s_day = max(1, int(day or 1))
    s_min = max(0, int(start_minute or 0))
    raw_end_min = int(end_minute if end_minute is not None else 1439)
    if raw_end_min >= 1440:
        extra_days, e_min = divmod(raw_end_min, 1440)
        resolved_end_day = s_day + extra_days
    else:
        e_min = max(0, raw_end_min)
        if end_day is not None:
            resolved_end_day = max(s_day, int(end_day))
        elif e_min < s_min:
            resolved_end_day = s_day + 1
        else:
            resolved_end_day = s_day

    eff_origin = (source_channel or origin or "in_person").strip()
    now = time.time()
    c_key = f"rendezvous_{session_id}_{target_entity}_{int(now)}_{uuid.uuid4().hex[:6]}"
    
    first_npc_name = target_entity
    # Try resolving contact display names from database
    if session_id and hasattr(db, "get_contacts"):
        try:
            contacts = db.get_contacts(session_id) or []
            for c in contacts:
                c_id = _canon_key(c.get("npc_id") or c.get("name") or "")
                c_nm = str(c.get("name") or "").strip()
                if not c_nm:
                    continue
                for p in norm_participants:
                    if p.get("person_key") == c_id:
                        p["name"] = c_nm
        except Exception:
            pass

    for p in norm_participants:
        if p.get("role") != "organizer":
            first_npc_name = p.get("name") or p.get("person_key")
            break

    if not title:
        disp_title = first_npc_name.title() if isinstance(first_npc_name, str) and first_npc_name == first_npc_name.lower() else (first_npc_name or "Group")
        title = f"Meetup with {disp_title}"
    if not description:
        description = f"Meet at {location}"

    meta = dict(metadata or {})
    meta.setdefault("reminder_sent", False)
    if purpose:
        meta["purpose"] = purpose
    is_rom = bool(meta.get("is_romantic") or meta.get("romantic") or purpose == "date" or is_confidential)

    # Invariant 1: Incest Guard - strictly prevent romantic rendezvous between household family members
    if (is_rom or is_confidential) and target_entity and target_entity != "group":
        try:
            import mechanics.social.relationship_graph as rg
            org_k = rg.canonical_person_key(org_canon)
            tgt_k = rg.canonical_person_key(target_entity)
            if rg.is_incestuous(session_id, org_k, tgt_k, conn=conn):
                is_confidential = False
                is_rom = False
                meta["is_romantic"] = False
                meta["incest_guarded"] = True
                log.info("Romantic rendezvous blocked by Incest Guard between %s and %s", org_k, tgt_k)
        except Exception:
            pass

    meta["is_romantic"] = is_rom

    # Invariant 5: Emergent Secret Affair detection via Social Graph
    if is_rom and target_entity and target_entity != "group":
        try:
            import mechanics.social.relationship_graph as rg
            org_k = rg.canonical_person_key(org_canon)
            tgt_k = rg.canonical_person_key(target_entity)
            partner_org = rg.get_current_partner(session_id, org_k, conn=conn)
            partner_tgt = rg.get_current_partner(session_id, tgt_k, conn=conn)
            if (partner_org and partner_org.get("person_key") != tgt_k) or (partner_tgt and partner_tgt.get("person_key") != org_k):
                meta["is_secret_affair"] = True
                meta.setdefault("exposure_risk", 0.5)
        except Exception:
            pass

    # Invariant 3: Permissive Double-Booking detection
    conflicts = check_double_booking(session_id, day=s_day, start_minute=s_min, end_minute=e_min, end_day=resolved_end_day, conn=conn)
    if conflicts:
        meta["has_conflicts"] = True
        meta["conflicting_ids"] = [c.get("id") for c in conflicts if c.get("id")]

    with _use_conn(conn) as active_conn:
        cur = active_conn.execute(
            """INSERT INTO commitments_ledger (
                session_id, commitment_key, commitment_type, source_entity, target_entity,
                participants_json, target_location, target_node_id, scheduled_day, end_day,
                start_minute, end_minute, deadline_turn, status, origin,
                is_confidential, title, description, metadata_json, turn_created,
                created_at, updated_at
            ) VALUES (?, ?, 'rendezvous', ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'pending', ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id, c_key, org_canon, target_entity, json.dumps(norm_participants),
                location.strip(), (node_id or "").strip(), s_day, resolved_end_day,
                s_min, e_min,
                eff_origin, 1 if is_confidential else 0, title.strip(), description.strip(),
                json.dumps(meta), max(0, int(current_turn or 0)), now, now
            )
        )
        row_id = cur.lastrowid
        created = get_commitment(session_id, row_id, conn=active_conn)
    if created and "id" in created:
        created["commitment_id"] = created["id"]
    return created


def create_promise(
    session_id: int,
    promiser: str = "player",
    promisee: str = "",
    description: str = "",
    *,
    commitment_type: str = "promise",
    subtype: str = "",
    deadline_day: Optional[int] = None,
    deadline_minute: Optional[int] = None,
    deadline_turn: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
    turn_created: int = 0
) -> Dict[str, Any]:
    """Creates a non-spatial obligation (promise, pact, debt, secret, task)."""
    if not description or not description.strip() or not session_id:
        return {}

    c_type = commitment_type.lower().strip()
    if c_type not in VALID_COMMITMENT_TYPES:
        if not subtype and c_type in ("secret", "debt", "pact", "threat", "task", "oath"):
            subtype = c_type
        c_type = "promise"

    meta = dict(metadata or {})
    if subtype:
        meta["subtype"] = subtype
    has_time_deadline = (deadline_day is not None) or (deadline_minute is not None)
    if has_time_deadline:
        meta["has_deadline"] = True

    now = time.time()
    raw_target = (promisee or "player").strip()
    clean_target = _canon_key(raw_target) or raw_target
    promiser_canon = _canon_key(promiser) or "player"
    c_key = f"promise_{session_id}_{clean_target}_{int(now)}_{uuid.uuid4().hex[:6]}"
    disp_target = raw_target.replace("_", " ").title() if "_" in raw_target else raw_target
    title = f"Promise to {disp_target}" if raw_target else "Pledge"

    participants = [
        {"person_key": promiser_canon, "role": "promiser", "status": "active"},
        {"person_key": clean_target, "name": disp_target or clean_target, "role": "promisee", "status": "pending"}
    ]
    sched_day_val = max(1, int(deadline_day or 1)) if has_time_deadline else None
    end_min_val = max(0, int(deadline_minute if deadline_minute is not None else 1439)) if has_time_deadline else 1439

    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO commitments_ledger (
                session_id, commitment_key, commitment_type, source_entity, target_entity,
                participants_json, target_location, target_node_id, scheduled_day, end_day,
                start_minute, end_minute, deadline_turn, status, origin,
                is_confidential, title, description, metadata_json, turn_created,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, '', '', ?, ?, ?, ?, ?, 'active', 'in_person', ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id, c_key, c_type, promiser_canon, clean_target,
                json.dumps(participants), sched_day_val, sched_day_val,
                max(0, int(deadline_minute or 0)) if deadline_minute is not None else 0,
                end_min_val,
                deadline_turn, 1 if meta.get("is_confidential") or subtype == "secret" else 0,
                title, description.strip(), json.dumps(meta), turn_created, now, now
            )
        )
        row_id = cur.lastrowid

    return get_commitment(session_id, row_id)


# ---------------------------------------------------------------------------
# State Lifecycle Transitions
# ---------------------------------------------------------------------------

def advance_rendezvous_to_arrived(
    session_id: int,
    commitment_id_or_key: Union[int, str],
    arriving_entity: str = "player"
) -> bool:
    """Marks a rendezvous as 'arrived' upon player or entity reaching the venue."""
    c = get_commitment(session_id, commitment_id_or_key)
    if not c or c.get("status") in ("fulfilled", "completed", "flaked", "cancelled", "voided"):
        return False

    now = time.time()
    raw_parts = c.get("participants_json") or "[]"
    try:
        parts = json.loads(raw_parts) if isinstance(raw_parts, str) else list(raw_parts)
    except Exception:
        parts = []

    entity_low = arriving_entity.strip().lower()
    for p in parts:
        if p.get("person_key", "").lower() == entity_low or p.get("npc_id", "").lower() == entity_low:
            p["status"] = "arrived"

    with get_conn() as conn:
        conn.execute(
            """UPDATE commitments_ledger
               SET status='arrived', participants_json=?, updated_at=?
               WHERE session_id=? AND (id=? OR commitment_key=?)""",
            (json.dumps(parts), now, session_id, c.get("id"), str(commitment_id_or_key))
        )

    # Invariant 5: Secret Affair Exposure Risk (Flat probability roll generating rumors in Phone Gossip + A2 suspicion counter)
    meta = c.get("metadata") or {}
    if (meta.get("is_secret_affair") or meta.get("affair")) and hasattr(db, "save_gossip_feed"):
        import random
        if random.random() < 0.30 or meta.get("force_rumor"):
            try:
                affair_disp = str(c.get("target_entity", "someone")).replace("_", " ").title()
                db.save_gossip_feed(session_id, [{
                    "author_name": "Anonymous Insider",
                    "author_handle": "@school_whispers",
                    "content": f"Spotted someone having a secretive rendezvous with {affair_disp}... What's going on between them?",
                    "tag": "#SecretAffair",
                    "clue_hook": "affair_rumor",
                    "time_ago": "Just now"
                }])
                # Phase 2.4 (A2): Increment primary partner suspicion counter on witness leaks; 2+ leaks trigger angry DM confrontation
                import mechanics.social.relationship_graph as rg
                prim = rg.get_current_partner(session_id, "player")
                tgt_k = rg.canonical_person_key(c.get("target_entity", ""))
                if prim and prim.get("person_key") != tgt_k:
                    prim_key = str(prim.get("person_key") or "")
                    prim_npc_id = rg.resolve_npc_id_for_person(session_id, prim_key) or prim_key
                    prim_disp = str(prim.get("display_name") or prim_key.replace("_", " ").title())
                    with get_conn() as conn:
                        tie_row = conn.execute(
                            """SELECT id, metadata_json FROM social_ties
                               WHERE session_id = ? AND status = 'active'
                                 AND ((person_a_key = 'player' AND person_b_key = ?) OR (person_a_key = ? AND person_b_key = 'player'))
                               ORDER BY closeness DESC LIMIT 1""",
                            (session_id, prim_key, prim_key),
                        ).fetchone()
                        if tie_row:
                            try:
                                t_meta = json.loads(tie_row["metadata_json"] or "{}")
                            except Exception:
                                t_meta = {}
                            leaks = int(t_meta.get("affair_leak_count") or 0) + 1
                            t_meta["affair_leak_count"] = leaks
                            should_confront = (leaks >= 2 and not t_meta.get("affair_confronted"))
                            if should_confront:
                                t_meta["affair_confronted"] = True
                            conn.execute(
                                "UPDATE social_ties SET metadata_json = ?, updated_at = ? WHERE id = ?",
                                (json.dumps(t_meta), now, tie_row["id"]),
                            )
                            if should_confront:
                                if hasattr(db, "update_relationship_score"):
                                    db.update_relationship_score(session_id, prim_npc_id, delta_score=-25)
                                rg.adjust_closeness(session_id, "player", prim_key, delta=-25, conn=conn)
                                if hasattr(db, "save_phone_message"):
                                    db.save_phone_message(
                                        session_id=session_id,
                                        contact_npc_id=prim_npc_id,
                                        sender="npc",
                                        message=f"People keep posting #SecretAffair rumors about you sneaking around behind my back... Tell me the truth right now. Are you cheating on me?!",
                                        intent="refusal",
                                    )
                                if hasattr(db, "add_npc_memory"):
                                    db.add_npc_memory(
                                        session_id=session_id,
                                        npc_name=prim_disp,
                                        turn_index=0,
                                        memory_fact="Saw repeated #SecretAffair gossip leaks on the phone feed and confronted player via DM.",
                                        importance=4,
                                        emotional_tone="suspicious",
                                        open_thread="affair_suspicion",
                                    )
            except Exception as _gossip_err:
                log.debug("Affair rumor / suspicion processing skipped: %s", _gossip_err)

    return True


def fulfill_commitment(
    session_id: int,
    commitment_id_or_key: Union[int, str],
    *,
    notes: str = "",
    fulfilled_by: str = "player",
    current_turn: int = 0
) -> bool:
    """Marks commitment as successfully fulfilled/completed."""
    c = get_commitment(session_id, commitment_id_or_key)
    if not c:
        return False
    if c.get("status") in ("fulfilled", "completed"):
        return True

    now = time.time()
    meta = c.get("metadata") or {}
    if notes:
        meta["fulfillment_notes"] = notes
    meta["fulfilled_by"] = fulfilled_by
    if current_turn:
        meta["fulfilled_turn"] = int(current_turn)

    with get_conn() as conn:
        conn.execute(
            """UPDATE commitments_ledger
               SET status='fulfilled', metadata_json=?, updated_at=?
               WHERE session_id=? AND (id=? OR commitment_key=?)""",
            (json.dumps(meta), now, session_id, c.get("id"), str(commitment_id_or_key))
        )
        tgt = c.get("target_entity", "")
        if tgt and tgt != "group":
            try:
                import mechanics.social.relationship_graph as rg
                p_k = rg.canonical_person_key(fulfilled_by)
                tgt_k = rg.canonical_person_key(tgt)
                rg.adjust_closeness(session_id, p_k, tgt_k, delta=5, conn=conn)
            except Exception:
                pass
            if c.get("commitment_type") == "promise":
                try:
                    _adjust_contact_affinity_delta(session_id, tgt, 5)
                except Exception:
                    pass

    return True


def flake_commitment(
    session_id: int,
    commitment_id_or_key: Union[int, str],
    *,
    flaked_entity: str = "player",
    reason: str = "time_window_elapsed",
    current_turn: int = 0
) -> Dict[str, Any]:
    """Applies flaking consequences: tiered affinity loss, hurt memory, and notification."""
    c = get_commitment(session_id, commitment_id_or_key)
    if not c or c.get("status") in ("fulfilled", "completed", "cancelled", "voided", "flaked", "broken"):
        return {}

    now = time.time()
    meta = c.get("metadata") or {}
    meta["flaked_by"] = flaked_entity
    meta["flake_reason"] = reason
    if current_turn:
        meta["flaked_turn"] = int(current_turn)

    is_romantic = bool(meta.get("is_romantic") or c.get("is_confidential"))
    is_rendezvous = c.get("commitment_type") == "rendezvous"
    
    # Tiered affinity penalty: -25 for romantic date, -15 for casual hangout or promise
    penalty = -25 if (is_rendezvous and is_romantic) else -15
    meta["applied_penalty"] = penalty

    npc_id = c.get("target_entity", "")
    short_loc = c.get("target_location", "the meetup location")
    if "➔" in short_loc:
        short_loc = short_loc.split("➔")[-1].strip()

    new_status = "broken" if (not is_rendezvous and "broken" in str(reason).lower()) else "flaked"
    with get_conn() as conn:
        conn.execute(
            """UPDATE commitments_ledger
               SET status=?, metadata_json=?, updated_at=?
               WHERE session_id=? AND (id=? OR commitment_key=?)""",
            (new_status, json.dumps(meta), now, session_id, c.get("id"), str(commitment_id_or_key))
        )

    # Apply affinity deduction and sync with social graph
    contact_row = None
    if npc_id and npc_id != "group":
        try:
            contact_row = _adjust_contact_affinity_delta(session_id, npc_id, penalty)
        except Exception as e:
            log.warning("Affinity penalty deduction failed: %s", e)

        try:
            import mechanics.social.relationship_graph as rg
            p_k = rg.canonical_person_key(flaked_entity)
            tgt_k = rg.canonical_person_key(npc_id)
            rg.adjust_closeness(session_id, p_k, tgt_k, delta=penalty)

            # If affinity collapsed below 0 on romantic track, trigger breakup in graph
            if contact_row is None:
                contact_row = _resolve_contact_row(session_id, npc_id)
            if contact_row and str(contact_row.get("track", "")).lower() == "romantic" and int(contact_row.get("relationship_score", 0)) < 0:
                eff_npc_id = contact_row.get("npc_id") or npc_id
                if hasattr(db, "update_contact_track"):
                    db.update_contact_track(session_id, eff_npc_id, "platonic")
                rg.end_all_romantic_ties(session_id, p_k, tgt_k, turn=current_turn, reason="flake_affinity_collapse")
                rg.materialize_and_save_relations(session_id, eff_npc_id)
        except Exception as e:
            log.debug("Social graph tie sync on flake skipped: %s", e)

    # Log hurt memory
    if npc_id and npc_id != "group" and hasattr(db, "add_npc_memory"):
        try:
            mem_msg = (
                f"Stood up and hurt when {flaked_entity} flaked on scheduled meetup at {short_loc}."
                if is_rendezvous
                else f"Felt betrayed when {flaked_entity} broke or failed their promise: '{c.get('description', '')}'."
            )
            db.add_npc_memory(
                session_id=session_id,
                npc_name=(contact_row.get("name") if contact_row else None) or c.get("target_entity", npc_id),
                turn_index=current_turn,
                memory_fact=mem_msg,
                importance=4 if is_romantic else 3,
                emotional_tone="hurt",
                open_thread="unresolved_flake"
            )
        except Exception as e:
            log.warning("Hurt memory logging failed: %s", e)

    # Send angry text message if modern phone scenario and rendezvous
    if is_rendezvous and npc_id and npc_id != "group" and hasattr(db, "save_phone_message"):
        try:
            msg_npc_id = (contact_row.get("npc_id") if contact_row else None) or npc_id
            db.save_phone_message(
                session_id=session_id,
                contact_npc_id=msg_npc_id,
                sender="npc",
                message=f"I waited at {short_loc}, but you never showed up. Don't make plans if you're just going to flake.",
                intent="refusal"
            )
        except Exception:
            pass

    return {
        "status": new_status,
        "penalty": penalty,
        "npc_id": npc_id,
        "is_romantic": is_romantic,
        "commitment_id": c.get("id")
    }


def abandon_rendezvous(
    session_id: int,
    commitment_id_or_key: Union[int, str],
    *,
    reason: str = "walked out mid-meeting"
) -> Dict[str, Any]:
    """Invariant 13: Player walked out during an active rendezvous without saying goodbye."""
    c = get_commitment(session_id, commitment_id_or_key)
    if not c or c.get("status") not in ("arrived", "in_progress", "pending"):
        return {}

    now = time.time()
    meta = c.get("metadata") or {}
    meta["abandoned"] = True
    meta["abandon_reason"] = reason
    penalty = -10
    meta["applied_penalty"] = penalty

    npc_id = c.get("target_entity", "")
    short_loc = c.get("target_location", "the venue")
    if "➔" in short_loc:
        short_loc = short_loc.split("➔")[-1].strip()

    with get_conn() as conn:
        conn.execute(
            """UPDATE commitments_ledger
               SET status='abandoned', metadata_json=?, updated_at=?
               WHERE session_id=? AND (id=? OR commitment_key=?)""",
            (json.dumps(meta), now, session_id, c.get("id"), str(commitment_id_or_key))
        )

    if npc_id and npc_id != "group":
        try:
            _adjust_contact_affinity_delta(session_id, npc_id, penalty)
        except Exception:
            pass
        try:
            import mechanics.social.relationship_graph as rg
            p_k = rg.canonical_person_key("player")
            tgt_k = rg.canonical_person_key(npc_id)
            rg.adjust_closeness(session_id, p_k, tgt_k, delta=penalty)
        except Exception:
            pass

    if npc_id and npc_id != "group" and hasattr(db, "add_npc_memory"):
        try:
            db.add_npc_memory(
                session_id=session_id,
                npc_name=c.get("target_entity", npc_id),
                turn_index=0,
                memory_fact=f"Felt insulted and abandoned when player abruptly walked out of their meetup at {short_loc}.",
                importance=3,
                emotional_tone="irritated",
                open_thread="unresolved_walkout"
            )
        except Exception:
            pass

    return {
        "status": "abandoned",
        "penalty": penalty,
        "npc_id": npc_id,
        "commitment_id": c.get("id")
    }


def cancel_commitment(
    session_id: int,
    commitment_id_or_key: Union[int, str],
    *,
    reason: str = "",
    cancelled_by: str = "player"
) -> bool:
    """Cancels a commitment gracefully without penalties."""
    c = get_commitment(session_id, commitment_id_or_key)
    if not c:
        return False

    now = time.time()
    meta = c.get("metadata") or {}
    meta["cancelled_by"] = cancelled_by
    if reason:
        meta["cancel_reason"] = reason

    with get_conn() as conn:
        conn.execute(
            """UPDATE commitments_ledger
               SET status='cancelled', metadata_json=?, updated_at=?
               WHERE session_id=? AND (id=? OR commitment_key=?)""",
            (json.dumps(meta), now, session_id, c.get("id"), str(commitment_id_or_key))
        )

    return True


def void_commitment(
    session_id: int,
    commitment_id_or_key: Union[int, str],
    *,
    reason: str = "counterparty_unavailable"
) -> bool:
    """Cleanly voids a commitment due to world disruption (NPC arrested, departed, or incapacitated)."""
    c = get_commitment(session_id, commitment_id_or_key)
    if not c:
        return False

    now = time.time()
    meta = c.get("metadata") or {}
    meta["void_reason"] = reason

    with get_conn() as conn:
        conn.execute(
            """UPDATE commitments_ledger
               SET status='voided', metadata_json=?, updated_at=?
               WHERE session_id=? AND (id=? OR commitment_key=?)""",
            (json.dumps(meta), now, session_id, c.get("id"), str(commitment_id_or_key))
        )

    return True


def apply_apology_recovery(
    session_id: int,
    npc_id: str,
    excuse_text: str = ""
) -> Dict[str, Any]:
    """Invariant 7: Apologizing for a flaked commitment recovers up to 50% of the lost affinity."""
    if not session_id or not npc_id:
        return {}

    clean_npc = npc_id.strip().lower().replace(" ", "_")
    canon_npc = _canon_key(npc_id)
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM commitments_ledger
               WHERE session_id=? AND status='flaked'
                 AND (lower(target_entity) IN (?, ?) OR lower(source_entity) IN (?, ?))
               ORDER BY updated_at DESC LIMIT 1""",
            (session_id, clean_npc, canon_npc, clean_npc, canon_npc)
        ).fetchone()

        if not row:
            return {}

        c = dict(row)
        try:
            meta = json.loads(c.get("metadata_json") or "{}")
        except Exception:
            meta = {}

        if meta.get("apologized"):
            return {}  # Already recovered

        applied_pen = abs(int(meta.get("applied_penalty", 15)))
        recover_amount = max(1, applied_pen // 2)

        meta["apologized"] = True
        meta["apology_text"] = excuse_text
        meta["recovered_affinity"] = recover_amount
        now = time.time()

        conn.execute(
            "UPDATE commitments_ledger SET metadata_json=?, updated_at=? WHERE id=?",
            (json.dumps(meta), now, c["id"])
        )

    try:
        _adjust_contact_affinity_delta(session_id, npc_id, recover_amount)
    except Exception:
        pass

    try:
        import mechanics.social.relationship_graph as rg
        p_k = rg.canonical_person_key("player")
        tgt_k = rg.canonical_person_key(npc_id)
        rg.adjust_closeness(session_id, p_k, tgt_k, delta=recover_amount)
    except Exception:
        pass

    if hasattr(db, "add_npc_memory"):
        try:
            db.add_npc_memory(
                session_id=session_id,
                npc_name=c.get("target_entity", npc_id),
                turn_index=0,
                memory_fact=f"Accepted apology for the missed rendezvous: '{excuse_text or 'sincere apology'}'. Relieved the tension somewhat.",
                importance=2,
                emotional_tone="relieved",
                open_thread=""
            )
        except Exception:
            pass

    return {
        "recovered": True,
        "recovered_affinity": recover_amount,
        "npc_id": npc_id,
        "commitment_id": c["id"]
    }


# ---------------------------------------------------------------------------
# Queries & Living World Overrides
# ---------------------------------------------------------------------------

def get_commitment(session_id: int, commitment_id_or_key: Union[int, str], conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """Retrieves a single commitment by ID or unique commitment_key."""
    with _use_conn(conn) as active_conn:
        row = None
        if isinstance(commitment_id_or_key, int) or (isinstance(commitment_id_or_key, str) and str(commitment_id_or_key).isdigit()):
            row = active_conn.execute(
                "SELECT * FROM commitments_ledger WHERE session_id=? AND id=?",
                (session_id, int(commitment_id_or_key))
            ).fetchone()
        if not row and isinstance(commitment_id_or_key, str):
            row = active_conn.execute(
                "SELECT * FROM commitments_ledger WHERE session_id=? AND commitment_key=?",
                (session_id, commitment_id_or_key)
            ).fetchone()

        if not row:
            return {}

        d = dict(row)
        try:
            d["participants"] = json.loads(d.get("participants_json") or "[]")
        except Exception:
            d["participants"] = []
        try:
            d["metadata"] = json.loads(d.get("metadata_json") or "{}")
        except Exception:
            d["metadata"] = {}
        return d


def get_active_commitments(
    session_id: int,
    entity_name: Optional[str] = None,
    commitment_type: Optional[str] = None,
    limit: int = 20,
    conn: Optional[sqlite3.Connection] = None
) -> List[Dict[str, Any]]:
    """Returns active commitments for a session."""
    with _use_conn(conn) as active_conn:
        query = (
            "SELECT * FROM commitments_ledger WHERE session_id=? "
            "AND status IN ('pending', 'approaching', 'arrived', 'in_progress', 'active') "
        )
        params: List[Any] = [session_id]

        if commitment_type:
            query += "AND commitment_type=? "
            params.append(commitment_type.lower().strip())

        if entity_name:
            ent = entity_name.strip().lower()
            ent_canon = _canon_key(entity_name)
            query += "AND (lower(source_entity) IN (?, ?) OR lower(target_entity) IN (?, ?) OR participants_json LIKE ? OR participants_json LIKE ?) "
            params.extend([ent, ent_canon, ent, ent_canon, f"%{ent}%", f"%{ent_canon}%"])

        query += "ORDER BY COALESCE(scheduled_day, 999999) ASC, start_minute ASC, turn_created ASC LIMIT ?"
        params.append(limit)

        rows = active_conn.execute(query, params).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            try:
                d["participants"] = json.loads(d.get("participants_json") or "[]")
            except Exception:
                d["participants"] = []
            try:
                d["metadata"] = json.loads(d.get("metadata_json") or "{}")
            except Exception:
                d["metadata"] = {}
            results.append(d)
        return results


def get_active_rendezvous_at_node(
    session_id: int,
    node_id_or_loc: str,
    current_day: Optional[int] = None,
    current_minute: Optional[int] = None,
    enforce_window: bool = True
) -> List[Dict[str, Any]]:
    """Finds active rendezvous appointments scheduled at the given node or location name within [start_min - 15, end_min]."""
    if not session_id or not node_id_or_loc:
        return []

    if current_day is None or current_minute is None:
        try:
            s_day, s_min, _ = db.get_session_time(session_id)
            if current_day is None:
                current_day = s_day
            if current_minute is None:
                current_minute = s_min
        except Exception:
            current_day = current_day or 1
            current_minute = current_minute or 0

    abs_now = (max(1, int(current_day)) - 1) * 1440 + max(0, int(current_minute))
    target = node_id_or_loc.strip()
    active_rendezvous = get_active_commitments(session_id, commitment_type="rendezvous", limit=50)
    matched = []

    from mechanics.world.waypoints import check_location_matches_waypoint

    for r in active_rendezvous:
        abs_start, abs_end = _compute_abs_window(r)
        if enforce_window and r.get("status") not in ("arrived", "in_progress"):
            if not ((abs_start - 15) <= abs_now <= abs_end):
                continue

        loc = r.get("target_location") or ""
        nid = r.get("target_node_id") or ""

        is_match = False
        if nid and (nid == target or db.is_descendant_of(session_id, target, nid) or db.is_descendant_of(session_id, nid, target)):
            is_match = True
        if not is_match and loc:
            is_match = (
                check_location_matches_waypoint(target, loc, session_id=session_id, target_node_id=nid or None)
                or check_location_matches_waypoint(loc, target, session_id=session_id)
            )

        if is_match:
            matched.append(r)

    return matched


def inject_npc_schedule_overrides(
    session_id: int,
    npc_id: str,
    current_day: int,
    current_minute: int
) -> Optional[Dict[str, Any]]:
    """Invariant 8: Overrides NPC routine schedule 15 minutes before rendezvous start (including midnight wrap-around)."""
    if not session_id or not npc_id:
        return None

    clean_npc = _canon_key(npc_id)
    active_rendezvous = get_active_commitments(session_id, entity_name=clean_npc, commitment_type="rendezvous", limit=10)
    abs_now = (max(1, int(current_day)) - 1) * 1440 + max(0, int(current_minute))

    for r in active_rendezvous:
        abs_start, abs_end = _compute_abs_window(r)
        lead_start = max(0, abs_start - 15)
        if lead_start <= abs_now <= abs_end:
            phase = "appointment_transit" if abs_now < abs_start else "appointment_waiting"
            return {
                "node_id": r.get("target_node_id") or "",
                "location": r.get("target_location") or "",
                "schedule_phase": phase,
                "commitment_id": r.get("id"),
                "is_confidential": bool(r.get("is_confidential")),
                "title": r.get("title")
            }

    return None


def check_double_booking(
    session_id: int,
    day: int,
    start_minute: int,
    end_minute: int,
    exclude_id: Optional[int] = None,
    end_day: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None
) -> List[Dict[str, Any]]:
    """Invariant 3: Permissive double-booking detector using monotonic absolute minutes."""
    active = get_active_commitments(session_id, commitment_type="rendezvous", limit=50, conn=conn)
    conflicts = []

    probe_start, probe_end = _compute_abs_window({
        "scheduled_day": day,
        "end_day": end_day,
        "start_minute": start_minute,
        "end_minute": end_minute,
    })

    for r in active:
        if exclude_id and r.get("id") == exclude_id:
            continue
        r_start, r_end = _compute_abs_window(r)
        if max(probe_start, r_start) < min(probe_end, r_end):
            conflicts.append(r)

    return conflicts


def audit_and_expire_commitments(
    session_id: int,
    current_day: int,
    current_minute: int,
    current_turn: int = 0
) -> List[Dict[str, Any]]:
    """Invariants 7 & 11: Audits all commitments against monotonic in-game clock and turns.
    
    Any scheduled appointment or timed promise whose window has passed without completion is flaked.
    Also sends 30-minute waiting reminders.
    """
    if not session_id:
        return []

    abs_current_min = max(0, int(current_day) - 1) * 1440 + max(0, int(current_minute))
    active = get_active_commitments(session_id, limit=100)
    flaked_events: List[Dict[str, Any]] = []

    for c in active:
        c_status = c.get("status")
        c_type = c.get("commitment_type")
        meta = c.get("metadata") or {}
        abs_start_min, abs_end_min = _compute_abs_window(c)

        # 1. Turn fallback expiration (applies to both rendezvous and 'active' promises)
        turn_expired = False
        deadline_turn = c.get("deadline_turn")
        if deadline_turn is not None and current_turn > 0 and current_turn > int(deadline_turn):
            turn_expired = True

        # 2. Time-of-day expiration (rendezvous in pending/approaching OR timed promises with has_deadline)
        time_expired = False
        if c_type == "rendezvous" and c_status in ("pending", "approaching") and abs_current_min > abs_end_min:
            time_expired = True
        elif c_type == "promise" and c_status in ("active", "pending") and meta.get("has_deadline") and abs_current_min > abs_end_min:
            time_expired = True

        if turn_expired or time_expired:
            res = flake_commitment(session_id, c["id"], reason="deadline_elapsed", current_turn=current_turn)
            if res:
                flaked_events.append(res)
            continue

        # 3. 30-minute reminder for waiting appointments
        if c_status == "pending" and c_type == "rendezvous":
            if not meta.get("reminder_sent") and abs_current_min >= abs_start_min + 30:
                meta["reminder_sent"] = True
                with get_conn() as conn:
                    conn.execute(
                        "UPDATE commitments_ledger SET metadata_json=? WHERE id=?",
                        (json.dumps(meta), c["id"])
                    )
                npc_id = c.get("target_entity", "")
                if npc_id and npc_id != "group" and hasattr(db, "save_phone_message"):
                    short_loc = c.get("target_location", "our meetup location")
                    if "➔" in short_loc:
                        short_loc = short_loc.split("➔")[-1].strip()
                    try:
                        c_row = _resolve_contact_row(session_id, npc_id)
                        msg_npc_id = (c_row.get("npc_id") if c_row else None) or npc_id
                        db.save_phone_message(
                            session_id=session_id,
                            contact_npc_id=msg_npc_id,
                            sender="npc",
                            message=f"Are you still coming? I'm waiting at {short_loc}.",
                            intent="reminder"
                        )
                    except Exception:
                        pass

    return flaked_events
