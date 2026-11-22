from __future__ import annotations

import db
import json
import sqlite3
import time
from ..core import (get_conn)

def _resolve_phone_contact_keys(conn: sqlite3.Connection, session_id: int, contact_npc_id: str) -> tuple[str, list[str]]:
    raw = str(contact_npc_id or "").strip()
    raw_slug = raw.lower().replace(" ", "_")
    try:
        from mechanics.social.relationship_graph import canonical_person_key
        canon_slug = canonical_person_key(raw)
    except Exception:
        canon_slug = raw_slug

    keys: list[str] = []
    for k in (raw_slug, canon_slug):
        if k and k not in keys:
            keys.append(k)

    if session_id and raw:
        row = conn.execute(
            "SELECT npc_id, name FROM contacts WHERE session_id=? AND (lower(npc_id) IN (?, ?) OR lower(name)=?)",
            (session_id, raw_slug, canon_slug, raw.lower()),
        ).fetchone()
        if row:
            db_npc_id = str(row["npc_id"] or "").strip().lower().replace(" ", "_")
            db_name_slug = str(row["name"] or "").strip().lower().replace(" ", "_")
            for k in (db_npc_id, db_name_slug):
                if k and k not in keys:
                    keys.append(k)
            if db_npc_id:
                return db_npc_id, keys

    return (raw_slug or canon_slug), keys

def save_phone_message(session_id: int, contact_npc_id: str, sender: str, message: str, intent: str = "chat"):
    now = time.time()
    with get_conn() as conn:
        primary_key, _ = _resolve_phone_contact_keys(conn, session_id, contact_npc_id)
        conn.execute(
            "INSERT INTO phone_messages (session_id, contact_npc_id, sender, message, intent, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, primary_key, sender, message, intent, now)
        )

def get_phone_messages(session_id: int, contact_npc_id: str, limit: int = 15) -> list[dict]:
    with get_conn() as conn:
        _, keys = _resolve_phone_contact_keys(conn, session_id, contact_npc_id)
        if not keys:
            return []
        placeholders = ",".join("?" for _ in keys)
        rows = conn.execute(
            f"""SELECT * FROM (
                SELECT * FROM phone_messages
                WHERE session_id=? AND contact_npc_id IN ({placeholders})
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
            ) ORDER BY timestamp ASC, id ASC""",
            (session_id, *keys, limit)
        ).fetchall()
        return [dict(r) for r in rows]

def update_contact_in_person_timestamp(session_id: int, npc_name_or_id: str | dict, ts: float = None) -> None:
    """Updates the last_in_person_ts timestamp in contact basic_info to mark recent phone messages as acknowledged in person."""
    if not session_id or not npc_name_or_id:
        return
    if isinstance(npc_name_or_id, dict):
        npc_name_or_id = npc_name_or_id.get("name") or npc_name_or_id.get("npc_id") or ""
    npc_str = str(npc_name_or_id).strip()
    if not npc_str:
        return
    if ts is None:
        ts = time.time()
    clean_id = npc_str.lower().replace(" ", "_")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, basic_info_json FROM contacts WHERE session_id=? AND (npc_id=? OR lower(name)=?)",
            (session_id, clean_id, npc_str.lower())
        ).fetchone()
        if row:
            cid = row["id"]
            try:
                binfo = json.loads(row["basic_info_json"] or "{}")
            except Exception:
                binfo = {}
            binfo["last_in_person_ts"] = ts
            conn.execute(
                "UPDATE contacts SET basic_info_json=? WHERE id=?",
                (json.dumps(binfo), cid)
            )

def save_gossip_feed(session_id: int, posts: list[dict]):
    now = time.time()
    with get_conn() as conn:
        for p in posts:
            conn.execute(
                """INSERT INTO phone_gossip_feed (session_id, author_name, author_handle, content, tag, clue_hook, time_ago, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    p.get("author_name", "Anonymous"),
                    p.get("author_handle", "@anon"),
                    p.get("content", ""),
                    p.get("tag", ""),
                    p.get("clue_hook", ""),
                    p.get("time_ago", "Just now"),
                    now
                )
            )

def get_gossip_feed(session_id: int, limit: int = 10) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM phone_gossip_feed WHERE session_id=? ORDER BY id DESC LIMIT ?",
            (session_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]

def _commitment_row_to_appointment_dict(r: sqlite3.Row | dict) -> dict:
    """Projects a normalized commitments_ledger row into the phone appointment dict view."""
    d = dict(r)
    try:
        participants = json.loads(d.get("participants_json") or "[]")
    except Exception:
        participants = []
    try:
        meta = json.loads(d.get("metadata_json") or "{}")
    except Exception:
        meta = {}

    npc_id = ""
    npc_name = ""
    for p in participants:
        if not isinstance(p, dict):
            continue
        pk = str(p.get("npc_id") or p.get("person_key") or "").strip()
        if pk and pk.lower() != "player" and not pk.lower().startswith("player:"):
            npc_id = pk.lower().replace(" ", "_")
            npc_name = str(p.get("name") or pk.replace("_", " ").title()).strip()
            break
    if not npc_id:
        tgt = str(d.get("target_entity") or "").strip()
        src = str(d.get("source_entity") or "").strip()
        cand = tgt if (tgt and tgt.lower() != "player") else src
        npc_id = cand.lower().replace(" ", "_")
        npc_name = cand.replace("_", " ").title()

    s_day = max(1, int(d.get("scheduled_day") or 1))
    s_min = max(0, int(d.get("start_minute") or 0))
    e_min = max(0, int(d.get("end_minute") if d.get("end_minute") is not None else 1439))
    raw_end_day = d.get("end_day")
    if raw_end_day is not None:
        e_day = max(s_day, int(raw_end_day))
    else:
        e_day = s_day + 1 if e_min < s_min else s_day

    created_min = (s_day - 1) * 1440 + s_min
    expiry_min = (e_day - 1) * 1440 + e_min

    raw_status = str(d.get("status") or "pending").strip().lower()
    if raw_status == "fulfilled":
        mapped_status = "completed"
    elif raw_status in ("flaked", "broken", "expired"):
        mapped_status = "stood_up"
    elif raw_status in ("arrived", "in_progress"):
        mapped_status = "arrived"
    elif raw_status == "cancelled":
        mapped_status = "cancelled"
    else:
        mapped_status = "pending"

    return {
        "id": d.get("id"),
        "commitment_id": d.get("id"),
        "session_id": d.get("session_id"),
        "npc_id": npc_id,
        "npc_name": npc_name,
        "rendezvous_location": d.get("target_location") or "",
        "target_node_id": d.get("target_node_id") or "",
        "topic": d.get("description") or d.get("title") or "",
        "is_confidential": 1 if d.get("is_confidential") else 0,
        "origin": d.get("origin") or "phone",
        "created_minute": created_min,
        "expiry_minute": expiry_min,
        "reminder_sent": 1 if meta.get("reminder_sent") else 0,
        "status": mapped_status,
        "ledger_status": raw_status,
        "scheduled_day": s_day,
        "end_day": e_day,
        "start_minute": s_min,
        "end_minute": e_min,
        "created_at": d.get("created_at") or 0.0,
    }

def save_phone_appointment(
    session_id: int,
    npc_id: str,
    npc_name: str,
    rendezvous_location: str,
    topic: str = "",
    is_confidential: bool = False,
    origin: str = "phone",
    created_minute: int = 0,
    expiry_minute: int = 0,
    expiry_minutes: int = 0,
    target_node_id: str = "",
) -> bool:
    """Upserts a pending meetup appointment into commitments_ledger. Returns True if saved."""
    if not rendezvous_location or not npc_id:
        return False
    clean_npc_id = npc_id.strip().lower().replace(" ", "_")
    now = time.time()
    if created_minute == 0 and session_id:
        try:
            curr_day, curr_min, _ = db.get_session_time(session_id)
            created_minute = max(0, curr_day - 1) * 1440 + curr_min
        except Exception:
            pass
    if not expiry_minute and expiry_minutes > 0 and created_minute >= 0:
        expiry_minute = created_minute + int(expiry_minutes)
    elif not expiry_minute and created_minute:
        expiry_minute = created_minute + 45

    day_val = (created_minute // 1440) + 1 if created_minute > 0 else 1
    start_m = created_minute % 1440 if created_minute > 0 else 0
    end_day_val = (expiry_minute // 1440) + 1 if expiry_minute > 0 else day_val
    end_m = expiry_minute % 1440 if expiry_minute > 0 else (min(1439, start_m + 45) if created_minute > 0 else 1439)
    if end_day_val < day_val:
        end_day_val = day_val

    try:
        from mechanics.social.relationship_graph import canonical_person_key
        canon_npc_id = canonical_person_key(npc_id)
    except Exception:
        canon_npc_id = clean_npc_id

    with get_conn() as conn:
        # Supersede any prior pending/approaching 1-on-1 rendezvous with this exact NPC (e.g. meetup relocation)
        conn.execute(
            """UPDATE commitments_ledger
               SET status = 'cancelled', updated_at = ?
               WHERE session_id = ? AND commitment_type = 'rendezvous'
                 AND status IN ('pending', 'approaching')
                 AND (lower(target_entity) IN (?, ?) OR lower(source_entity) IN (?, ?))""",
            (now, session_id, clean_npc_id, canon_npc_id, clean_npc_id, canon_npc_id)
        )
        from mechanics.system.commitments_engine import create_rendezvous
        created = create_rendezvous(
            session_id=session_id,
            organizer="player",
            participants=[{"npc_id": clean_npc_id, "name": npc_name.strip()}],
            location=rendezvous_location.strip(),
            day=day_val,
            end_day=end_day_val,
            start_minute=start_m,
            end_minute=end_m,
            title=f"Meetup with {npc_name.strip()}",
            description=topic.strip() or f"Meet at {rendezvous_location.strip()}",
            origin=origin,
            node_id=target_node_id or None,
            is_confidential=is_confidential,
            conn=conn,
        )
        return bool(created)

def save_rendezvous_appointment(
    session_id: int,
    npc_id: str,
    npc_name: str,
    rendezvous_location: str,
    topic: str = "",
    is_confidential: bool = True,
    created_minute: int = 0,
    expiry_minute: int = 0,
    expiry_minutes: int = 0,
    target_node_id: str = "",
) -> bool:
    """Specialized helper for in-person dialogue rendezvous appointments."""
    return save_phone_appointment(
        session_id=session_id,
        npc_id=npc_id,
        npc_name=npc_name,
        rendezvous_location=rendezvous_location,
        topic=topic,
        is_confidential=is_confidential,
        origin="dialogue",
        created_minute=created_minute,
        expiry_minute=expiry_minute,
        expiry_minutes=expiry_minutes,
        target_node_id=target_node_id,
    )

def get_phone_appointments(session_id: int, status: str = "pending") -> list[dict]:
    """Returns all rendezvous appointments for a session matching the requested status."""
    st_clean = str(status or "pending").strip().lower()
    if st_clean == "completed":
        ledger_statuses = ("fulfilled",)
    elif st_clean in ("stood_up", "flaked", "missed"):
        ledger_statuses = ("flaked", "broken", "expired")
    elif st_clean == "arrived":
        ledger_statuses = ("arrived", "in_progress")
    elif st_clean == "cancelled":
        ledger_statuses = ("cancelled",)
    else:
        ledger_statuses = ("pending", "approaching")

    placeholders = ",".join("?" for _ in ledger_statuses)
    with get_conn() as conn:
        rows = conn.execute(
            f"""SELECT * FROM commitments_ledger
                WHERE session_id=? AND commitment_type='rendezvous'
                  AND status IN ({placeholders})
                ORDER BY created_at ASC, id ASC""",
            (session_id, *ledger_statuses)
        ).fetchall()
        return [_commitment_row_to_appointment_dict(r) for r in rows]

def get_active_rendezvous_appointments(session_id: int) -> list[dict]:
    """Returns all active rendezvous appointments (pending, approaching, arrived, in_progress) for a session."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM commitments_ledger
               WHERE session_id=? AND commitment_type='rendezvous'
                 AND status IN ('pending', 'approaching', 'arrived', 'in_progress')
               ORDER BY created_at ASC, id ASC""",
            (session_id,)
        ).fetchall()
        return [_commitment_row_to_appointment_dict(r) for r in rows]

def update_phone_appointment_status(session_id: int, npc_id: str, status: str):
    """Updates a meetup appointment status in commitments_ledger."""
    clean_npc_id = npc_id.strip().lower().replace(" ", "_")
    ledger_status = str(status or "").strip().lower()
    if ledger_status == "stood_up":
        ledger_status = "flaked"
    elif ledger_status == "completed":
        ledger_status = "fulfilled"
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            """UPDATE commitments_ledger
               SET status=?, updated_at=?
               WHERE session_id=? AND commitment_type='rendezvous'
                 AND (lower(target_entity)=? OR lower(source_entity)=? OR lower(participants_json) LIKE ?)
                 AND status IN ('pending', 'approaching', 'arrived', 'in_progress', 'active')""",
            (ledger_status, now, session_id, clean_npc_id, clean_npc_id, f"%{clean_npc_id}%")
        )

def get_due_reminder_appointments(session_id: int, current_minute: int) -> list[dict]:
    """Finds pending rendezvous appointments waiting >= 30 minutes without a reminder sent."""
    if not current_minute or current_minute <= 0:
        return []
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM commitments_ledger
               WHERE session_id=? AND commitment_type='rendezvous'
                 AND status IN ('pending', 'approaching')""",
            (session_id,)
        ).fetchall()
        due = []
        for r in rows:
            appt = _commitment_row_to_appointment_dict(r)
            if appt.get("reminder_sent"):
                continue
            c_min = appt.get("created_minute", 0)
            if c_min > 0 and (current_minute - c_min) >= 30:
                due.append(appt)
        return due

def expire_overdue_appointments(session_id: int, current_minute: int) -> list[dict]:
    """Delegates overdue rendezvous expiration to commitments_ledger using monotonic absolute minutes."""
    if not current_minute or current_minute <= 0:
        return []
    curr_day = (int(current_minute) // 1440) + 1
    curr_min_of_day = int(current_minute) % 1440
    from mechanics.system.commitments_engine import flake_commitment
    expired_appts = []
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM commitments_ledger
               WHERE session_id=? AND commitment_type='rendezvous'
                 AND status IN ('pending', 'approaching')""",
            (session_id,)
        ).fetchall()
        overdue_rows = []
        for r in rows:
            appt = _commitment_row_to_appointment_dict(r)
            exp_min = appt.get("expiry_minute", 0)
            if exp_min > 0 and int(current_minute) >= exp_min:
                overdue_rows.append((r["id"], appt))

    for cid, appt in overdue_rows:
        flake_commitment(
            session_id,
            cid,
            flaked_entity="player",
            reason="deadline_elapsed",
        )
        appt["status"] = "stood_up"
        appt["ledger_status"] = "flaked"
        expired_appts.append(appt)
    return expired_appts

def get_phone_daily_limits(session_id: int, npc_id: str, current_day: int) -> dict:
    """Returns structured daily action allowances, usage counts, and status for a contact on current_day."""
    clean_npc_id = str(npc_id).strip().lower().replace(" ", "_")
    raw_npc_low = str(npc_id).strip().lower()
    limits = {
        "chat": {"used": 0, "max": 3, "locked": False, "over_limit_count": 0},
        "flirt": {"used": 0, "max": 3, "locked": False, "history": [], "last_outcome": "", "over_limit_count": 0},
        "meetup": {"used": 0, "max": 1, "locked": False, "status": "available", "relocations_left": 0, "relocations_used": 0, "last_outcome": "", "over_limit_count": 0},
        "photo": {"used": 0, "max": 3, "locked": False, "over_limit_count": 0},
        "spicy": {"used": 0, "max": 3, "locked": False, "over_limit_count": 0},
        "rumor": {"used": 0, "max": 1, "locked": False, "over_limit_count": 0},
    }
    with get_conn() as conn:
        c_row = conn.execute(
            """SELECT relationship_score FROM contacts
               WHERE session_id=? AND (lower(npc_id)=? OR lower(name)=? OR lower(name)=?)
               ORDER BY relationship_score DESC LIMIT 1""",
            (session_id, clean_npc_id, raw_npc_low, clean_npc_id.replace("_", " ")),
        ).fetchone()
        contact_score = int(c_row["relationship_score"] or 0) if c_row else 0
        max_chat = 5 if contact_score >= 100 else 3
        limits["chat"]["max"] = max_chat

        # Check active rendezvous commitments for this NPC
        appt_row = conn.execute(
            """SELECT target_location AS rendezvous_location, status FROM commitments_ledger
               WHERE session_id=? AND commitment_type='rendezvous'
                 AND status IN ('pending', 'approaching')
                 AND (lower(target_entity)=? OR lower(source_entity)=? OR lower(participants_json) LIKE ?)
               ORDER BY id DESC LIMIT 1""",
            (session_id, clean_npc_id, clean_npc_id, f"%{clean_npc_id}%")
        ).fetchone()
        has_active_appt = bool(appt_row)

        rows = conn.execute(
            "SELECT intent, attempt_count, success_count, over_limit_count, last_outcome, metadata_json "
            "FROM phone_daily_interactions WHERE session_id=? AND npc_id=? AND current_day=?",
            (session_id, clean_npc_id, int(current_day))
        ).fetchall()

        for r in rows:
            intent = r["intent"]
            used = int(r["attempt_count"] or 0)
            over_limit = int(r["over_limit_count"] or 0)
            outcome = r["last_outcome"] or ""
            meta = {}
            if r["metadata_json"]:
                try:
                    meta = json.loads(r["metadata_json"])
                except Exception:
                    meta = {}

            if intent == "flirt":
                limits["flirt"]["used"] = used
                limits["flirt"]["locked"] = used >= 3
                limits["flirt"]["history"] = meta.get("history", [])
                limits["flirt"]["last_outcome"] = outcome
                limits["flirt"]["over_limit_count"] = over_limit
            elif intent == "meetup":
                limits["meetup"]["used"] = used
                relocations_used = meta.get("relocations_used", 0)
                limits["meetup"]["relocations_used"] = relocations_used
                if has_active_appt:
                    limits["meetup"]["status"] = "accepted"
                    limits["meetup"]["relocations_left"] = max(0, 2 - relocations_used)
                    limits["meetup"]["locked"] = relocations_used >= 2
                    limits["meetup"]["rendezvous_location"] = appt_row["rendezvous_location"]
                else:
                    limits["meetup"]["status"] = "failed" if used >= 1 else "available"
                    limits["meetup"]["relocations_left"] = 0
                    limits["meetup"]["locked"] = used >= 1
                limits["meetup"]["last_outcome"] = outcome
                limits["meetup"]["over_limit_count"] = over_limit
            elif intent in ("photo", "photo_ask", "photo_send"):
                limits["photo"]["used"] += used
                limits["photo"]["over_limit_count"] = limits["photo"].get("over_limit_count", 0) + over_limit
            elif intent in ("spicy", "spicy_ask", "spicy_send", "nsfw_photo", "nsfw_video"):
                limits["spicy"]["used"] += used
                limits["spicy"]["over_limit_count"] = limits["spicy"].get("over_limit_count", 0) + over_limit
            elif intent in ("rumor", "intel_rumor", "intel"):
                limits["rumor"]["used"] += used
                limits["rumor"]["locked"] = limits["rumor"]["used"] >= 1
                limits["rumor"]["over_limit_count"] += over_limit
            elif intent in ("chat", "custom"):
                limits["chat"]["used"] += used
                limits["chat"]["over_limit_count"] += over_limit

        limits["chat"]["locked"] = limits["chat"]["used"] >= limits["chat"]["max"]
        limits["photo"]["locked"] = limits["photo"]["used"] >= 3
        limits["spicy"]["locked"] = limits["spicy"]["used"] >= 3
        limits["flirt"]["locked"] = limits["flirt"]["used"] >= 3
        limits["rumor"]["locked"] = limits["rumor"]["used"] >= 1

        if has_active_appt and limits["meetup"]["status"] != "accepted":
            limits["meetup"]["status"] = "accepted"
            relocations_used = limits["meetup"].get("relocations_used", 0)
            limits["meetup"]["relocations_left"] = max(0, 2 - relocations_used)
            limits["meetup"]["locked"] = relocations_used >= 2
            limits["meetup"]["rendezvous_location"] = appt_row["rendezvous_location"]

    return limits

def record_phone_daily_interaction(session_id: int, npc_id: str, current_day: int, intent: str, outcome: str, metadata: dict = None, is_over_limit: bool = False) -> dict:
    """Atomically records or updates a daily interaction attempt."""
    clean_npc_id = str(npc_id).strip().lower().replace(" ", "_")
    norm_intent = intent
    if intent in ("photo_ask", "photo_send"):
        norm_intent = "photo"
    elif intent in ("spicy_ask", "spicy_send", "nsfw_photo", "nsfw_video"):
        norm_intent = "spicy"
    elif intent in ("intel_rumor", "intel"):
        norm_intent = "rumor"
    elif intent in ("chat", "custom"):
        norm_intent = "chat"

    with get_conn() as conn:
        row = conn.execute(
            "SELECT attempt_count, success_count, over_limit_count, metadata_json FROM phone_daily_interactions "
            "WHERE session_id=? AND npc_id=? AND current_day=? AND intent=?",
            (session_id, clean_npc_id, int(current_day), norm_intent)
        ).fetchone()

        now = time.time()
        succeeded = outcome in ("success", "crit_success")

        if row:
            curr_attempts = int(row["attempt_count"] or 0)
            curr_successes = int(row["success_count"] or 0)
            curr_over = int(row["over_limit_count"] or 0)
            existing_meta = {}
            if row["metadata_json"]:
                try:
                    existing_meta = json.loads(row["metadata_json"])
                except Exception:
                    existing_meta = {}

            if is_over_limit:
                new_over = curr_over + 1
                new_attempts = curr_attempts
                new_successes = curr_successes
            else:
                new_over = curr_over
                new_attempts = curr_attempts + 1
                new_successes = curr_successes + (1 if succeeded else 0)

            if metadata:
                existing_meta.update(metadata)

            conn.execute(
                """UPDATE phone_daily_interactions
                   SET attempt_count=?, success_count=?, over_limit_count=?, last_outcome=?, metadata_json=?, updated_at=?
                   WHERE session_id=? AND npc_id=? AND current_day=? AND intent=?""",
                (new_attempts, new_successes, new_over, outcome, json.dumps(existing_meta), now,
                 session_id, clean_npc_id, int(current_day), norm_intent)
            )
        else:
            new_attempts = 0 if is_over_limit else 1
            new_successes = 1 if (succeeded and not is_over_limit) else 0
            new_over = 1 if is_over_limit else 0
            meta_json = json.dumps(metadata or {})
            conn.execute(
                """INSERT INTO phone_daily_interactions
                   (session_id, npc_id, current_day, intent, attempt_count, success_count, over_limit_count, last_outcome, metadata_json, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, clean_npc_id, int(current_day), norm_intent, new_attempts, new_successes, new_over, outcome, meta_json, now)
            )

    return get_phone_daily_limits(session_id, clean_npc_id, current_day)
