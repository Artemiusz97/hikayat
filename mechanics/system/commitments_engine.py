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


def _normalize_participants(
    organizer: str,
    participants: Optional[Union[List[Union[Dict[str, Any], str]], str]],
    primary_target: str = ""
) -> Tuple[str, List[Dict[str, Any]]]:
    """Normalizes participant lists into structured dicts with person_key/npc_id, name, and status."""
    norm: List[Dict[str, Any]] = [
        {"person_key": organizer or "player", "role": "organizer", "status": "active"}
    ]
    primary = primary_target.strip()
    
    raw_list: List[Any] = []
    if isinstance(participants, list):
        raw_list = participants
    elif isinstance(participants, str) and participants.strip():
        raw_list = [participants.strip()]
    elif primary:
        raw_list = [primary]

    for p in raw_list:
        if isinstance(p, dict):
            p_key = str(p.get("person_key") or p.get("npc_id") or p.get("name") or "").strip().lower()
            p_name = str(p.get("name") or p.get("npc_name") or p_key).strip()
            p_role = str(p.get("role") or "participant").strip()
            p_stat = str(p.get("status") or "pending").strip()
            if p_key and p_key != organizer.lower():
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
            clean_low = clean.lower()
            if clean_low != organizer.lower():
                display_name = clean.replace("_", " ").title() if "_" in clean else clean
                norm.append({
                    "person_key": clean_low,
                    "npc_id": clean_low,
                    "name": display_name,
                    "role": "participant",
                    "status": "pending"
                })
                if not primary:
                    primary = clean_low

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
    title: str = "",
    description: str = "",
    origin: str = "in_person",
    node_id: Optional[str] = None,
    is_confidential: bool = False,
    metadata: Optional[Dict[str, Any]] = None,
    conn: Optional[sqlite3.Connection] = None,
    sync_legacy: bool = True
) -> Dict[str, Any]:
    """Creates a new physical rendezvous commitment.
    
    Also synchronizes legacy phone_appointments if 1-on-1 meetup with an NPC.
    """
    if not location or not session_id:
        return {}

    target_entity, norm_participants = _normalize_participants(organizer, participants)
    if not node_id and hasattr(db, "resolve_node_id_from_location"):
        try:
            node_id = db.resolve_node_id_from_location(session_id, location)
        except Exception:
            node_id = ""

    now = time.time()
    c_key = f"rendezvous_{session_id}_{target_entity}_{int(now)}_{uuid.uuid4().hex[:6]}"
    
    first_npc_name = target_entity
    # Try resolving contact display names from database
    if session_id and hasattr(db, "get_contacts"):
        try:
            contacts = db.get_contacts(session_id) or []
            for c in contacts:
                c_id = str(c.get("npc_id") or "").strip().lower()
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
        disp_title = first_npc_name.title() if isinstance(first_npc_name, str) else 'Group'
        title = f"Meetup with {disp_title}"
    if not description:
        description = f"Meet at {location}"

    meta = dict(metadata or {})
    meta.setdefault("reminder_sent", False)
    is_rom = bool(meta.get("is_romantic") or meta.get("romantic") or is_confidential)

    # Invariant 1: Incest Guard - strictly prevent romantic rendezvous between household family members
    if (is_rom or is_confidential) and target_entity and target_entity != "group":
        try:
            import mechanics.social.relationship_graph as rg
            org_k = rg.canonical_person_key(organizer)
            tgt_k = rg.canonical_person_key(target_entity)
            if rg.is_incestuous(session_id, org_k, tgt_k):
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
            org_k = rg.canonical_person_key(organizer)
            tgt_k = rg.canonical_person_key(target_entity)
            partner_org = rg.get_current_partner(session_id, org_k)
            partner_tgt = rg.get_current_partner(session_id, tgt_k)
            if (partner_org and partner_org.get("person_key") != tgt_k) or (partner_tgt and partner_tgt.get("person_key") != org_k):
                meta["is_secret_affair"] = True
                meta.setdefault("exposure_risk", 0.5)
        except Exception:
            pass

    # Invariant 3: Permissive Double-Booking detection
    conflicts = check_double_booking(session_id, day=day, start_minute=start_minute, end_minute=end_minute)
    if conflicts:
        meta["has_conflicts"] = True
        meta["conflicting_ids"] = [c.get("id") for c in conflicts if c.get("id")]

    with _use_conn(conn) as active_conn:
        cur = active_conn.execute(
            """INSERT INTO commitments_ledger (
                session_id, commitment_key, commitment_type, source_entity, target_entity,
                participants_json, target_location, target_node_id, scheduled_day,
                start_minute, end_minute, deadline_turn, status, origin,
                is_confidential, title, description, metadata_json, turn_created,
                created_at, updated_at
            ) VALUES (?, ?, 'rendezvous', ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'pending', ?, ?, ?, ?, ?, 0, ?, ?)""",
            (
                session_id, c_key, organizer, target_entity, json.dumps(norm_participants),
                location.strip(), (node_id or "").strip(), max(1, int(day or 1)),
                max(0, int(start_minute or 0)), max(0, int(end_minute or 1439)),
                origin, 1 if is_confidential else 0, title.strip(), description.strip(),
                json.dumps(meta), now, now
            )
        )
        row_id = cur.lastrowid

        # Backward-compatibility sync with phone_appointments table for single NPC meetups
        if sync_legacy and target_entity and target_entity != "group":
            clean_npc = target_entity.strip().lower().replace(" ", "_")
            created_min = (max(0, int(day or 1) - 1) * 1440) + max(0, int(start_minute or 0))
            expiry_min = (max(0, int(day or 1) - 1) * 1440) + max(0, int(end_minute or 1439))
            try:
                active_conn.execute(
                    """INSERT INTO phone_appointments (
                        session_id, npc_id, npc_name, rendezvous_location, target_node_id,
                        topic, is_confidential, origin, created_minute, expiry_minute, reminder_sent,
                        status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'pending', ?)
                    ON CONFLICT(session_id, npc_id) DO UPDATE SET
                        rendezvous_location=excluded.rendezvous_location,
                        target_node_id=excluded.target_node_id,
                        topic=excluded.topic,
                        is_confidential=excluded.is_confidential,
                        origin=excluded.origin,
                        created_minute=excluded.created_minute,
                        expiry_minute=excluded.expiry_minute,
                        reminder_sent=0,
                        status='pending',
                        created_at=excluded.created_at""",
                    (
                        session_id, clean_npc, first_npc_name, location.strip(), (node_id or "").strip(),
                        description.strip(), 1 if is_confidential else 0, origin,
                        created_min, expiry_min, now
                    )
                )
            except Exception as e:
                log.debug("Legacy phone_appointments sync skipped: %s", e)

    return get_commitment(session_id, row_id, conn=conn)


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

    now = time.time()
    clean_target = (promisee or "player").strip()
    c_key = f"promise_{session_id}_{clean_target}_{int(now)}_{uuid.uuid4().hex[:6]}"
    title = f"Promise to {clean_target.title()}" if clean_target else "Pledge"

    participants = [
        {"person_key": promiser or "player", "role": "promiser", "status": "active"},
        {"person_key": clean_target, "name": clean_target, "role": "promisee", "status": "pending"}
    ]

    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO commitments_ledger (
                session_id, commitment_key, commitment_type, source_entity, target_entity,
                participants_json, target_location, target_node_id, scheduled_day,
                start_minute, end_minute, deadline_turn, status, origin,
                is_confidential, title, description, metadata_json, turn_created,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, '', '', ?, ?, ?, ?, 'active', 'in_person', ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id, c_key, c_type, (promiser or "player").strip(), clean_target,
                json.dumps(participants), max(1, int(deadline_day or 1)) if deadline_day else 1,
                max(0, int(deadline_minute or 0)) if deadline_minute is not None else 0,
                max(0, int(deadline_minute or 1439)) if deadline_minute is not None else 1439,
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
        # Keep legacy phone_appointments synced
        tgt = c.get("target_entity", "")
        if tgt and tgt != "group":
            try:
                conn.execute(
                    "UPDATE phone_appointments SET status='arrived' WHERE session_id=? AND npc_id=?",
                    (session_id, tgt.strip().lower().replace(" ", "_"))
                )
            except Exception:
                pass

    # Invariant 5: Secret Affair Exposure Risk (Flat probability roll generating rumors in Phone Gossip)
    meta = c.get("metadata") or {}
    if (meta.get("is_secret_affair") or meta.get("affair")) and hasattr(db, "save_gossip_feed"):
        import random
        if random.random() < 0.30 or meta.get("force_rumor"):
            try:
                db.save_gossip_feed(session_id, [{
                    "author_name": "Anonymous Insider",
                    "author_handle": "@school_whispers",
                    "content": f"Spotted someone having a secretive rendezvous with {c.get('target_entity', 'someone').title()}... What's going on between them?",
                    "tag": "#SecretAffair",
                    "clue_hook": "affair_rumor",
                    "time_ago": "Just now"
                }])
            except Exception:
                pass

    return True


def fulfill_commitment(
    session_id: int,
    commitment_id_or_key: Union[int, str],
    *,
    notes: str = "",
    fulfilled_by: str = "player"
) -> bool:
    """Marks commitment as successfully fulfilled/completed."""
    c = get_commitment(session_id, commitment_id_or_key)
    if not c:
        return False

    now = time.time()
    meta = c.get("metadata") or {}
    if notes:
        meta["fulfillment_notes"] = notes
    meta["fulfilled_by"] = fulfilled_by

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
                conn.execute(
                    "UPDATE phone_appointments SET status='completed' WHERE session_id=? AND npc_id=?",
                    (session_id, tgt.strip().lower().replace(" ", "_"))
                )
            except Exception:
                pass
            try:
                import mechanics.social.relationship_graph as rg
                p_k = rg.canonical_person_key(fulfilled_by)
                tgt_k = rg.canonical_person_key(tgt)
                rg.adjust_closeness(session_id, p_k, tgt_k, delta=5)
            except Exception:
                pass

    return True


def flake_commitment(
    session_id: int,
    commitment_id_or_key: Union[int, str],
    *,
    flaked_entity: str = "player",
    reason: str = "time_window_elapsed"
) -> Dict[str, Any]:
    """Applies flaking consequences: tiered affinity loss, hurt memory, and notification."""
    c = get_commitment(session_id, commitment_id_or_key)
    if not c or c.get("status") in ("fulfilled", "completed", "cancelled", "voided", "flaked"):
        return {}

    now = time.time()
    meta = c.get("metadata") or {}
    meta["flaked_by"] = flaked_entity
    meta["flake_reason"] = reason

    is_romantic = bool(meta.get("is_romantic") or c.get("is_confidential"))
    is_rendezvous = c.get("commitment_type") == "rendezvous"
    
    # Tiered affinity penalty: -25 for romantic date, -15 for casual hangout or promise
    penalty = -25 if (is_rendezvous and is_romantic) else -15
    meta["applied_penalty"] = penalty

    npc_id = c.get("target_entity", "")
    short_loc = c.get("target_location", "the meetup location")
    if "➔" in short_loc:
        short_loc = short_loc.split("➔")[-1].strip()

    with get_conn() as conn:
        conn.execute(
            """UPDATE commitments_ledger
               SET status='flaked', metadata_json=?, updated_at=?
               WHERE session_id=? AND (id=? OR commitment_key=?)""",
            (json.dumps(meta), now, session_id, c.get("id"), str(commitment_id_or_key))
        )
        if npc_id and npc_id != "group":
            clean_npc = npc_id.strip().lower().replace(" ", "_")
            try:
                conn.execute(
                    "UPDATE phone_appointments SET status='stood_up' WHERE session_id=? AND npc_id=?",
                    (session_id, clean_npc)
                )
            except Exception:
                pass

    # Apply affinity deduction and sync with social graph
    if npc_id and npc_id != "group":
        if hasattr(db, "update_relationship_score"):
            try:
                db.update_relationship_score(session_id, npc_id, delta_score=penalty)
            except Exception as e:
                log.warning("Affinity penalty deduction failed: %s", e)

        try:
            import mechanics.social.relationship_graph as rg
            p_k = rg.canonical_person_key(flaked_entity)
            tgt_k = rg.canonical_person_key(npc_id)
            rg.adjust_closeness(session_id, p_k, tgt_k, delta=penalty)

            # If affinity collapsed below 0 on romantic track, trigger breakup in graph
            contact_row = db.get_contact(session_id, npc_id) if hasattr(db, "get_contact") else None
            if contact_row and str(contact_row.get("track", "")).lower() == "romantic" and int(contact_row.get("relationship_score", 0)) < 0:
                if hasattr(db, "update_contact_track"):
                    db.update_contact_track(session_id, npc_id, "platonic")
                rg.end_tie(session_id, p_k, tgt_k, tie_type=None, reason="flake_affinity_collapse")
                rg.materialize_and_save_relations(session_id, npc_id)
        except Exception as e:
            log.debug("Social graph tie sync on flake skipped: %s", e)

    # Log hurt memory
    if npc_id and npc_id != "group" and hasattr(db, "add_npc_memory"):
        try:
            db.add_npc_memory(
                session_id=session_id,
                npc_name=c.get("target_entity", npc_id),
                turn_index=0,
                memory_fact=f"Stood up and hurt when {flaked_entity} flaked on scheduled meetup at {short_loc}.",
                importance=4 if is_romantic else 3,
                emotional_tone="hurt",
                open_thread="unresolved_flake"
            )
        except Exception as e:
            log.warning("Hurt memory logging failed: %s", e)

    # Send angry text message if modern phone scenario
    if npc_id and npc_id != "group" and hasattr(db, "save_phone_message"):
        try:
            db.save_phone_message(
                session_id=session_id,
                contact_npc_id=npc_id,
                sender="npc",
                message=f"I waited at {short_loc}, but you never showed up. Don't make plans if you're just going to flake.",
                intent="refusal"
            )
        except Exception:
            pass

    return {
        "status": "flaked",
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
            clean_npc = npc_id.strip().lower().replace(" ", "_")
            try:
                conn.execute(
                    "UPDATE phone_appointments SET status='completed' WHERE session_id=? AND npc_id=?",
                    (session_id, clean_npc)
                )
            except Exception:
                pass

    if npc_id and npc_id != "group":
        if hasattr(db, "update_relationship_score"):
            try:
                db.update_relationship_score(session_id, npc_id, delta_score=penalty)
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
        tgt = c.get("target_entity", "")
        if tgt and tgt != "group":
            try:
                conn.execute(
                    "UPDATE phone_appointments SET status='cancelled' WHERE session_id=? AND npc_id=?",
                    (session_id, tgt.strip().lower().replace(" ", "_"))
                )
            except Exception:
                pass

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
        tgt = c.get("target_entity", "")
        if tgt and tgt != "group":
            try:
                conn.execute(
                    "UPDATE phone_appointments SET status='cancelled' WHERE session_id=? AND npc_id=?",
                    (session_id, tgt.strip().lower().replace(" ", "_"))
                )
            except Exception:
                pass

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
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM commitments_ledger
               WHERE session_id=? AND status='flaked'
                 AND (lower(target_entity)=? OR lower(source_entity)=?)
               ORDER BY updated_at DESC LIMIT 1""",
            (session_id, clean_npc, clean_npc)
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

    if hasattr(db, "update_relationship_score"):
        try:
            db.update_relationship_score(session_id, npc_id, delta_score=recover_amount)
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
    limit: int = 20
) -> List[Dict[str, Any]]:
    """Returns active commitments for a session."""
    with get_conn() as conn:
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
            query += "AND (lower(source_entity)=? OR lower(target_entity)=? OR participants_json LIKE ?) "
            params.extend([ent, ent, f"%{ent}%"])

        query += "ORDER BY scheduled_day ASC, start_minute ASC, turn_created ASC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
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
    current_day: int = 1,
    current_minute: int = 0
) -> List[Dict[str, Any]]:
    """Finds active rendezvous appointments scheduled at the given node or location name."""
    if not session_id or not node_id_or_loc:
        return []

    target = node_id_or_loc.strip()
    active_rendezvous = get_active_commitments(session_id, commitment_type="rendezvous", limit=50)
    matched = []

    from mechanics.world.waypoints import check_location_matches_waypoint

    for r in active_rendezvous:
        # Check day match
        if r.get("scheduled_day") and int(r["scheduled_day"]) != int(current_day):
            continue

        loc = r.get("target_location") or ""
        nid = r.get("target_node_id") or ""

        is_match = False
        if nid and (nid == target or db.is_descendant_of(session_id, target, nid) or db.is_descendant_of(session_id, nid, target)):
            is_match = True
        elif loc:
            is_match = check_location_matches_waypoint(target, loc) or check_location_matches_waypoint(loc, target)

        if is_match:
            matched.append(r)

    return matched


def inject_npc_schedule_overrides(
    session_id: int,
    npc_id: str,
    current_day: int,
    current_minute: int
) -> Optional[Dict[str, Any]]:
    """Invariant 8: Overrides NPC routine schedule 15 minutes before rendezvous start."""
    if not session_id or not npc_id:
        return None

    clean_npc = npc_id.strip().lower().replace(" ", "_")
    active_rendezvous = get_active_commitments(session_id, entity_name=clean_npc, commitment_type="rendezvous", limit=10)

    for r in active_rendezvous:
        r_day = int(r.get("scheduled_day") or 1)
        if r_day != int(current_day):
            continue

        start_min = int(r.get("start_minute") or 0)
        end_min = int(r.get("end_minute") or 1439)

        # 15-minute lead-up until end of window
        lead_start = max(0, start_min - 15)
        if lead_start <= current_minute <= end_min:
            phase = "appointment_transit" if current_minute < start_min else "appointment_waiting"
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
    exclude_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Invariant 3: Permissive double-booking detector. Returns overlapping active appointments."""
    active = get_active_commitments(session_id, commitment_type="rendezvous", limit=50)
    conflicts = []

    for r in active:
        if exclude_id and r.get("id") == exclude_id:
            continue
        if int(r.get("scheduled_day") or 1) != int(day):
            continue

        r_start = int(r.get("start_minute") or 0)
        r_end = int(r.get("end_minute") or 1439)

        # Check overlap
        if max(start_minute, r_start) < min(end_minute, r_end):
            conflicts.append(r)

    return conflicts


def audit_and_expire_commitments(
    session_id: int,
    current_day: int,
    current_minute: int,
    current_turn: int = 0
) -> List[Dict[str, Any]]:
    """Invariants 7 & 11: Audits all commitments against in-game clock and turns.
    
    Any scheduled appointment whose window has passed without arrival is flaked.
    Also sends 30-minute waiting reminders.
    """
    if not session_id:
        return []

    abs_current_min = max(0, int(current_day) - 1) * 1440 + max(0, int(current_minute))
    active = get_active_commitments(session_id, limit=100)
    flaked_events: List[Dict[str, Any]] = []

    for c in active:
        c_status = c.get("status")
        c_day = int(c.get("scheduled_day") or 1)
        end_min = int(c.get("end_minute") or 1439)
        abs_end_min = max(0, c_day - 1) * 1440 + end_min

        # 1. Turn fallback expiration
        turn_expired = False
        deadline_turn = c.get("deadline_turn")
        if deadline_turn is not None and current_turn > 0 and current_turn > int(deadline_turn):
            turn_expired = True

        # 2. Time-of-day expiration
        time_expired = False
        if abs_current_min > abs_end_min and c_status in ("pending", "approaching"):
            time_expired = True

        if turn_expired or time_expired:
            res = flake_commitment(session_id, c["id"], reason="deadline_elapsed")
            if res:
                flaked_events.append(res)
            continue

        # 3. 30-minute reminder for waiting appointments
        if c_status == "pending" and c.get("commitment_type") == "rendezvous":
            meta = c.get("metadata") or {}
            if not meta.get("reminder_sent"):
                start_min = int(c.get("start_minute") or 0)
                abs_start_min = max(0, c_day - 1) * 1440 + start_min
                if abs_current_min >= abs_start_min + 30:
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
                            db.save_phone_message(
                                session_id=session_id,
                                contact_npc_id=npc_id,
                                sender="npc",
                                message=f"Are you still coming? I'm waiting at {short_loc}.",
                                intent="reminder"
                            )
                        except Exception:
                            pass

    return flaked_events
