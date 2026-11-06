from __future__ import annotations
"""
db/memory.py — Long-Term Memory CRUD Layer
==========================================
Provides persistence for the Hierarchical Memory Engine:
  - commitments_ledger: active promises, pacts, secrets, debts between player and NPCs.
  - session_digests / sessions.chapter_digest_json: episodic arc summaries (Tier 2 Memory).
"""
import json
import time
import logging

import db
from .core import get_conn

log = logging.getLogger("hikayat.db.memory")

# ---------------------------------------------------------------------------
# Commitments Ledger
# ---------------------------------------------------------------------------

VALID_COMMITMENT_TYPES = frozenset({"promise", "secret", "debt", "pact", "threat"})


def add_commitment(
    session_id: int,
    source_entity: str,
    target_entity: str,
    commitment_type: str,
    description: str,
    turn_number: int = 0,
    metadata: dict | None = None,
) -> dict:
    """Record a new commitment (promise, pact, secret, etc.) between entities.

    Returns the newly inserted row as a dict, or {} on validation failure.
    """
    if not description or not description.strip():
        return {}
    
    # Delegate to commitments_engine for full unified schema population
    try:
        from mechanics.system.commitments_engine import create_promise
        merged_meta = dict(metadata or {})
        if target_entity and target_entity.strip():
            merged_meta.setdefault("raw_target_entity", target_entity.strip())
        res = create_promise(
            session_id=session_id,
            promiser=source_entity or "player",
            promisee=target_entity or "player",
            description=description.strip(),
            commitment_type=commitment_type or "promise",
            turn_created=turn_number,
            metadata=merged_meta,
        )
        if res:
            if merged_meta.get("raw_target_entity"):
                res["target_entity"] = merged_meta["raw_target_entity"]
            return res
    except Exception:
        pass

    commitment_type = commitment_type.lower().strip()
    if commitment_type not in VALID_COMMITMENT_TYPES:
        commitment_type = "promise"

    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO commitments_ledger
               (session_id, source_entity, target_entity, commitment_type,
                description, status, turn_created, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)""",
            (
                session_id,
                (source_entity or "player").strip(),
                (target_entity or "player").strip(),
                commitment_type,
                description.strip(),
                turn_number,
                now,
                now,
            ),
        )
        row_id = cur.lastrowid
    return get_commitment(session_id, row_id)


def _hydrate_memory_commitment_row(row_dict: dict) -> dict:
    if not row_dict:
        return {}
    meta_raw = row_dict.get("metadata_json")
    if meta_raw:
        try:
            meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
            if isinstance(meta, dict) and meta.get("raw_target_entity"):
                row_dict["target_entity"] = meta["raw_target_entity"]
        except Exception:
            pass
    return row_dict


def get_commitment(session_id: int, commitment_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM commitments_ledger WHERE id=? AND session_id=?",
            (commitment_id, session_id),
        ).fetchone()
    return _hydrate_memory_commitment_row(dict(row)) if row else {}


def get_active_commitments(
    session_id: int,
    entity_name: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Return all active commitments for a session, optionally filtered to
    those involving a specific entity (as source OR target OR in participants_json, case-insensitive).
    """
    with get_conn() as conn:
        if entity_name:
            name_lower = entity_name.strip().lower()
            name_slug = name_lower.replace(" ", "_")
            name_spaced = name_lower.replace("_", " ")
            rows = conn.execute(
                """SELECT * FROM commitments_ledger
                   WHERE session_id=? AND status IN ('active', 'pending', 'approaching', 'arrived', 'in_progress')
                     AND (lower(source_entity) IN (?, ?) OR lower(target_entity) IN (?, ?) OR lower(participants_json) LIKE ? OR lower(participants_json) LIKE ?)
                   ORDER BY turn_created ASC LIMIT ?""",
                (session_id, name_slug, name_spaced, name_slug, name_spaced, f"%{name_slug}%", f"%{name_spaced}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM commitments_ledger
                   WHERE session_id=? AND status IN ('active', 'pending', 'approaching', 'arrived', 'in_progress')
                   ORDER BY turn_created ASC LIMIT ?""",
                (session_id, limit),
            ).fetchall()
    return [_hydrate_memory_commitment_row(dict(r)) for r in rows]


def update_commitment_status(
    session_id: int, commitment_id: int, status: str
) -> bool:
    """Update commitment status via commitments_engine so affinity, memory, and social ties stay synchronized."""
    status = status.lower().strip()
    valid_statuses = ("fulfilled", "broken", "active", "flaked", "completed", "cancelled", "voided", "abandoned")
    if status not in valid_statuses:
        return False
    try:
        from mechanics.system.commitments_engine import (
            fulfill_commitment,
            flake_commitment,
            cancel_commitment,
            void_commitment,
            abandon_rendezvous,
        )
        if status in ("fulfilled", "completed"):
            return fulfill_commitment(session_id, commitment_id)
        if status in ("broken", "flaked"):
            return bool(flake_commitment(session_id, commitment_id, reason="broken promise" if status == "broken" else "time_window_elapsed"))
        if status == "cancelled":
            return cancel_commitment(session_id, commitment_id)
        if status == "voided":
            return void_commitment(session_id, commitment_id)
        if status == "abandoned":
            return bool(abandon_rendezvous(session_id, commitment_id))
    except Exception:
        pass
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "UPDATE commitments_ledger SET status=?, updated_at=? WHERE id=? AND session_id=?",
            (status, now, commitment_id, session_id),
        )
    return True


def bulk_add_commitments(
    session_id: int,
    commitments: list[dict],
    turn_number: int = 0,
) -> int:
    """Bulk-insert a list of commitment dicts (from LLM digest output).
    Each dict must have: source_entity, target_entity, commitment_type, description.
    Returns number of successfully inserted rows.
    """
    inserted = 0
    for c in (commitments or []):
        if not isinstance(c, dict):
            continue
        result = add_commitment(
            session_id=session_id,
            source_entity=str(c.get("source_entity", "player")),
            target_entity=str(c.get("target_entity", "")),
            commitment_type=str(c.get("commitment_type", "promise")),
            description=str(c.get("description", "")),
            turn_number=turn_number,
        )
        if result:
            inserted += 1
    return inserted


# ---------------------------------------------------------------------------
# Chapter Digest (Tier 2 Memory)
# ---------------------------------------------------------------------------

# Maximum number of bullet-point strings kept in the rolling digest.
MAX_ROLLING_DIGEST_BULLETS = 30
MAX_DIGEST_BULLETS = MAX_ROLLING_DIGEST_BULLETS


def _rebuild_session_digests_fts_inner(conn, session_id: int | None = None) -> int:
    """Repopulate 3-column session_digests_fts on an active SQLite connection."""
    from mechanics.system.memory.tokenization import tokenize_for_fts

    has_compaction_cols = True
    try:
        if session_id is not None:
            rows = conn.execute(
                "SELECT session_id, summary_bullets_json, entities_json, location_tag, compacted_count FROM session_digests WHERE session_id = ? AND is_compacted = 0 ORDER BY id ASC",
                (session_id,),
            ).fetchall()
            conn.execute("DELETE FROM session_digests_fts WHERE session_id = ?", (session_id,))
        else:
            rows = conn.execute(
                "SELECT session_id, summary_bullets_json, entities_json, location_tag, compacted_count FROM session_digests WHERE is_compacted = 0 ORDER BY id ASC"
            ).fetchall()
            conn.execute("DELETE FROM session_digests_fts")
    except Exception:
        has_compaction_cols = False
        if session_id is not None:
            rows = conn.execute(
                "SELECT session_id, summary_bullets_json, entities_json, location_tag FROM session_digests WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
            conn.execute("DELETE FROM session_digests_fts WHERE session_id = ?", (session_id,))
        else:
            rows = conn.execute(
                "SELECT session_id, summary_bullets_json, entities_json, location_tag FROM session_digests ORDER BY id ASC"
            ).fetchall()
            conn.execute("DELETE FROM session_digests_fts")

    inserted = 0
    for r in rows:
        sid = r["session_id"]
        try:
            row_bullets = json.loads(r["summary_bullets_json"] or "[]")
        except Exception:
            row_bullets = []
        if not isinstance(row_bullets, list):
            row_bullets = []
        cc = int(r["compacted_count"] or 0) if has_compaction_cols else 0
        active_row_bullets = row_bullets[cc:] if cc > 0 else row_bullets
        try:
            row_entities = json.loads(r["entities_json"] or "[]")
        except Exception:
            row_entities = []
        loc = str(r["location_tag"] or "")
        meta_suffix = " ".join([loc] + [str(e) for e in row_entities if e]).strip()
        for b in active_row_bullets:
            if not isinstance(b, str) or not b.strip():
                continue
            clean_b = b.strip()
            tokens = tokenize_for_fts(f"{clean_b} {meta_suffix}" if meta_suffix else clean_b)
            conn.execute(
                "INSERT INTO session_digests_fts (session_id, bullet_text, search_tokens) VALUES (?, ?, ?)",
                (sid, clean_b, tokens),
            )
            inserted += 1
    return inserted


def rebuild_session_digests_fts(conn_or_session_id=None, session_id: int | None = None) -> int:
    """Repopulate 3-column session_digests_fts from authoritative session_digests rows.

    Polymorphic facade: accepts `(conn, session_id)`, `(conn,)`, `(session_id,)`, or `()`.
    """
    if hasattr(conn_or_session_id, "execute"):
        return _rebuild_session_digests_fts_inner(conn_or_session_id, session_id)
    target_sid = conn_or_session_id if session_id is None else session_id
    with get_conn() as conn:
        return _rebuild_session_digests_fts_inner(conn, target_sid)


def append_chapter_digest(
    session_id: int,
    turn_start: int,
    turn_end: int,
    bullets: list[str],
    embeddings: list[list[float]] = None,  # Deprecated post-Migration 37 compatibility shim (ignored)
    entities: list[str] | None = None,
    location_tag: str = "",
    quest_ids: list[str] | None = None,
) -> list[str]:
    """Append new narrative bullet points to the session's rolling chapter digest.
    Atomically persists session_digests metadata, 3-column multilingual FTS5 tokens,
    and sessions.chapter_digest_json inside one transaction.
    """
    from mechanics.system.memory.tokenization import tokenize_for_fts

    if not bullets:
        return get_chapter_digest(session_id)

    now = time.time()
    clean_bullets = [b.strip() for b in bullets if isinstance(b, str) and b.strip()]
    if not clean_bullets:
        return get_chapter_digest(session_id)

    clean_entities = [str(e).strip() for e in (entities or []) if e and str(e).strip()]
    clean_quests = [str(q).strip() for q in (quest_ids or []) if q and str(q).strip()]
    clean_loc = str(location_tag or "").strip()
    meta_suffix = " ".join([clean_loc] + clean_entities).strip()

    with get_conn() as conn:
        conn.execute(
            """INSERT INTO session_digests
               (session_id, turn_start, turn_end, summary_bullets_json, entities_json, location_tag, quest_ids_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                int(turn_start),
                int(turn_end),
                json.dumps(clean_bullets),
                json.dumps(clean_entities),
                clean_loc,
                json.dumps(clean_quests),
                now,
            ),
        )
        for b in clean_bullets:
            tokens = tokenize_for_fts(f"{b} {meta_suffix}" if meta_suffix else b)
            conn.execute(
                "INSERT INTO session_digests_fts (session_id, bullet_text, search_tokens) VALUES (?, ?, ?)",
                (session_id, b, tokens),
            )

        sess_row = conn.execute(
            "SELECT chapter_digest_json FROM sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        current: list[str] = []
        if sess_row and sess_row["chapter_digest_json"]:
            try:
                parsed = json.loads(sess_row["chapter_digest_json"])
                if isinstance(parsed, list):
                    current = parsed
            except Exception:
                current = []
        trimmed = (current + clean_bullets)[-MAX_DIGEST_BULLETS:]
        conn.execute(
            "UPDATE sessions SET chapter_digest_json=? WHERE id=?",
            (json.dumps(trimmed), session_id),
        )
    return trimmed


def get_session_digests(session_id: int) -> list[dict]:
    """Return all session_digests rows for a session ordered chronologically."""
    if not session_id:
        return []
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM session_digests WHERE session_id = ? ORDER BY turn_end ASC, id ASC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]


_active_tier3_compactions: set[int] = set()


def run_deterministic_tier3_compaction(session_id: int) -> bool:
    """Synchronously compact oldest 15 Tier 2 bullets into a Tier 3 Saga Chronicle when >= 24 bullets accumulate."""
    import os
    import uuid
    from mechanics.system.memory.compaction import build_deterministic_chronicle
    from .core import acquire_distributed_lock, release_distributed_lock

    if not session_id or session_id in _active_tier3_compactions:
        return False

    lock_key = f"tier3_compact_{session_id}"
    owner_id = f"proc_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    if not acquire_distributed_lock(lock_key, owner_id, timeout_seconds=60):
        return False

    _active_tier3_compactions.add(session_id)
    try:
        bullets = get_chapter_digest(session_id)
        if len(bullets) < 24:
            return False

        bullets_to_compact = bullets[:15]
        remaining_active = bullets[len(bullets_to_compact):]
        existing = get_session_chronicles(session_id)
        chapter_number = len(existing) + 1
        result = build_deterministic_chronicle(bullets_to_compact, chapter_number=chapter_number)

        act_title = result.get("act_title", f"Chronicle of Chapter {chapter_number}")
        summary_narrative = result.get("summary_narrative", "")
        key_consequences = result.get("key_consequences", [])
        if not summary_narrative:
            return False

        with get_conn() as conn:
            sess_row = conn.execute(
                "SELECT turn_count FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            current_turn = int((sess_row["turn_count"] if sess_row else 0) or 0)

            uncompacted_rows = conn.execute(
                """SELECT id, turn_start, turn_end, summary_bullets_json, compacted_count
                   FROM session_digests
                   WHERE session_id = ? AND is_compacted = 0
                   ORDER BY turn_end ASC, id ASC""",
                (session_id,),
            ).fetchall()

            parsed_uncompacted: list[tuple[dict, list[str], int]] = []
            total_uncompacted = 0
            for ur in uncompacted_rows:
                try:
                    rb = json.loads(ur["summary_bullets_json"] or "[]")
                except Exception:
                    rb = []
                rb_list = rb if isinstance(rb, list) else []
                old_cc = int(ur["compacted_count"] or 0)
                avail = max(0, len(rb_list) - old_cc)
                total_uncompacted += avail
                parsed_uncompacted.append((dict(ur), rb_list, old_cc))

            to_compact_in_rows = (
                max(len(bullets_to_compact), total_uncompacted - len(remaining_active))
                if parsed_uncompacted
                else len(bullets_to_compact)
            )

            chron_turn_start = 0
            chron_turn_end = 0
            actual_compacted = 0
            rem = to_compact_in_rows

            touched_rows: list[tuple[int, int, int]] = []
            for ur_dict, rb_list, old_cc in parsed_uncompacted:
                if rem <= 0:
                    break
                avail = max(0, len(rb_list) - old_cc)
                if avail <= 0:
                    conn.execute(
                        "UPDATE session_digests SET is_compacted = 1 WHERE id = ?",
                        (ur_dict["id"],),
                    )
                    continue
                take = min(rem, avail)
                new_cc = old_cc + take
                new_is_comp = 1 if new_cc >= len(rb_list) else 0
                if chron_turn_start == 0:
                    chron_turn_start = int(ur_dict.get("turn_start") or 0)
                chron_turn_end = max(chron_turn_end, int(ur_dict.get("turn_end") or 0))
                touched_rows.append((new_cc, new_is_comp, int(ur_dict["id"])))
                rem -= take
                actual_compacted += take

            created_turn = max(current_turn, chron_turn_end)
            for new_cc, new_is_comp, row_id in touched_rows:
                conn.execute(
                    "UPDATE session_digests SET compacted_count = ?, compacted_at_turn = ?, is_compacted = ? WHERE id = ?",
                    (new_cc, created_turn, new_is_comp, row_id),
                )

            conn.execute(
                """INSERT INTO session_chronicles
                   (session_id, chapter_number, act_title, summary_narrative, key_consequences_json,
                    turn_start, turn_end, created_turn, bullet_count, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    chapter_number,
                    act_title,
                    summary_narrative,
                    json.dumps(key_consequences or []),
                    chron_turn_start,
                    chron_turn_end,
                    created_turn,
                    actual_compacted or len(bullets_to_compact),
                    time.time(),
                ),
            )

            _rebuild_session_digests_fts_inner(conn, session_id)
            conn.execute(
                "UPDATE sessions SET chapter_digest_json = ? WHERE id = ?",
                (json.dumps(remaining_active), session_id),
            )

        log.info(
            "Successfully compacted %d bullets into Saga Chronicle Chapter %d: %s",
            len(bullets_to_compact),
            chapter_number,
            act_title,
        )
        return True
    except Exception as exc:
        log.error("Failed to run deterministic Tier 3 Saga Compaction: %s", exc)
        return False
    finally:
        _active_tier3_compactions.discard(session_id)
        release_distributed_lock(lock_key, owner_id)


def finalize_turn_memory(
    session_id: int,
    target_turn: int,
    history: list,
    present_npcs: list[str] | None = None,
    current_location: str = "",
    active_quest_ids: list[str] | None = None,
    arc_boundary: bool = False,
) -> dict:
    """Synchronously finalize post-history Tier 2 digest and Tier 3 chronicle compaction."""
    from mechanics.system.memory.digest import (
        MIN_TURNS_FOR_DIGEST,
        RAW_HISTORY_LIMIT,
        build_deterministic_arc_digest,
        format_digest_bullets_and_commitments,
    )

    if not session_id or target_turn <= 0:
        return {"digested": False, "compacted": False}

    with get_conn() as conn:
        sess_row = conn.execute(
            "SELECT last_digested_turn FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    if not sess_row:
        return {"digested": False, "compacted": False}

    last_digested = int(sess_row["last_digested_turn"] or 0)
    delta = int(target_turn) - last_digested
    should_digest = delta >= RAW_HISTORY_LIMIT or (arc_boundary and delta >= MIN_TURNS_FOR_DIGEST)
    if not should_digest:
        compacted = run_deterministic_tier3_compaction(session_id)
        return {"digested": False, "compacted": compacted}

    action_turns = [
        t for t in (history or [])
        if not (isinstance(t, dict) and t.get("type") == "scene")
    ]
    if not action_turns:
        return {"digested": False, "compacted": False}

    slice_len = min(delta, len(action_turns))
    slice_turns = action_turns[-slice_len:]
    overall_turn_start = max(last_digested + 1, int(target_turn) - len(slice_turns) + 1)

    all_bullets: list[str] = []
    chunk_step = max(1, int(RAW_HISTORY_LIMIT))
    existing_descs = {
        str(c.get("description") or "").strip().lower()
        for c in get_active_commitments(session_id, limit=50)
    }

    for offset in range(0, len(slice_turns), chunk_step):
        chunk = slice_turns[offset : offset + chunk_step]
        if not chunk:
            continue
        c_start = overall_turn_start + offset
        c_end = min(int(target_turn), c_start + len(chunk) - 1)
        is_last_chunk = (offset + chunk_step) >= len(slice_turns)

        digest_res = build_deterministic_arc_digest(chunk)
        bullets, commitments = format_digest_bullets_and_commitments(digest_res)

        merged_entities: list[str] = []
        extra_npcs = list(present_npcs or []) if is_last_chunk else []
        for ent in list(digest_res.get("entities") or []) + extra_npcs:
            clean_e = str(ent or "").strip()
            if clean_e and clean_e.lower() not in {"none", "player", "hero"} and clean_e not in merged_entities:
                merged_entities.append(clean_e)

        merged_quests: list[str] = []
        extra_qids = list(active_quest_ids or []) if is_last_chunk else []
        for qid in list(digest_res.get("quest_ids") or []) + extra_qids:
            clean_q = str(qid or "").strip()
            if clean_q and clean_q not in merged_quests:
                merged_quests.append(clean_q)

        fallback_loc = current_location if is_last_chunk else ""
        loc_raw = str(digest_res.get("location_tag") or fallback_loc or "").strip()
        loc_tag = loc_raw.split("➔")[-1].strip() if "➔" in loc_raw else loc_raw

        if bullets:
            append_chapter_digest(
                session_id=session_id,
                turn_start=c_start,
                turn_end=c_end,
                bullets=bullets,
                entities=merged_entities,
                location_tag=loc_tag,
                quest_ids=merged_quests,
            )
            all_bullets.extend(bullets)

        if commitments:
            fresh_commits = []
            for c in commitments:
                desc_key = str(c.get("description") or "").strip().lower()
                if desc_key and desc_key not in existing_descs:
                    existing_descs.add(desc_key)
                    fresh_commits.append(c)
            if fresh_commits:
                bulk_add_commitments(session_id, fresh_commits, turn_number=c_end)

    turn_end = int(target_turn)
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET last_digested_turn = ? WHERE id = ?",
            (turn_end, session_id),
        )

    compacted = run_deterministic_tier3_compaction(session_id)
    return {
        "digested": True,
        "turn_start": overall_turn_start,
        "turn_end": turn_end,
        "bullets": all_bullets,
        "compacted": compacted,
    }


def resync_latest_digest_turn(session_id: int, history: list) -> bool:
    """Re-synchronize the latest uncompacted session_digests row when manual retry_narration updates prose on an already-digested turn."""
    from mechanics.system.memory.digest import (
        build_deterministic_arc_digest,
        format_digest_bullets_and_commitments,
    )

    if not session_id:
        return False

    action_turns = [
        t for t in (history or [])
        if not (isinstance(t, dict) and t.get("type") == "scene")
    ]
    if not action_turns:
        return False

    with get_conn() as conn:
        sess_row = conn.execute(
            "SELECT turn_count, last_digested_turn FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not sess_row:
            return False
        t_cnt = int(sess_row["turn_count"] or 0)
        l_dig = int(sess_row["last_digested_turn"] or 0)
        if t_cnt <= 0 or l_dig != t_cnt:
            return False

        latest_row = conn.execute(
            """SELECT id, turn_start, turn_end
               FROM session_digests
               WHERE session_id = ? AND turn_end = ? AND is_compacted = 0 AND compacted_count = 0
               ORDER BY id DESC LIMIT 1""",
            (session_id, t_cnt),
        ).fetchone()
        if not latest_row:
            return False

        w_len = max(1, int(latest_row["turn_end"]) - int(latest_row["turn_start"]) + 1)
        window_turns = action_turns[-min(w_len, len(action_turns)):]
        digest_res = build_deterministic_arc_digest(window_turns)
        bullets, _ = format_digest_bullets_and_commitments(digest_res)
        if not bullets:
            return False

        merged_entities: list[str] = []
        for ent in list(digest_res.get("entities") or []):
            clean_e = str(ent or "").strip()
            if clean_e and clean_e.lower() not in {"none", "player", "hero"} and clean_e not in merged_entities:
                merged_entities.append(clean_e)

        merged_quests: list[str] = []
        for qid in list(digest_res.get("quest_ids") or []):
            clean_q = str(qid or "").strip()
            if clean_q and clean_q not in merged_quests:
                merged_quests.append(clean_q)

        loc_raw = str(digest_res.get("location_tag") or "").strip()
        loc_tag = loc_raw.split("➔")[-1].strip() if "➔" in loc_raw else loc_raw

        conn.execute(
            """UPDATE session_digests
               SET summary_bullets_json = ?, entities_json = ?, location_tag = ?, quest_ids_json = ?
               WHERE id = ?""",
            (json.dumps(bullets), json.dumps(merged_entities), loc_tag, json.dumps(merged_quests), latest_row["id"]),
        )
        _rebuild_session_digests_fts_inner(conn, session_id)

        rem_rows = conn.execute(
            "SELECT summary_bullets_json, compacted_count FROM session_digests WHERE session_id = ? AND is_compacted = 0 ORDER BY turn_end ASC, id ASC",
            (session_id,),
        ).fetchall()
        rem_bullets: list[str] = []
        for rr in rem_rows:
            try:
                b_list = json.loads(rr["summary_bullets_json"] or "[]")
                if isinstance(b_list, list):
                    cc = int(rr["compacted_count"] or 0)
                    for b in b_list[cc:]:
                        if isinstance(b, str) and b.strip():
                            rem_bullets.append(b.strip())
            except Exception:
                pass
        conn.execute(
            "UPDATE sessions SET chapter_digest_json = ? WHERE id = ?",
            (json.dumps(rem_bullets[-MAX_ROLLING_DIGEST_BULLETS:]), session_id),
        )
    return True


def remove_oldest_chapter_digest_bullets(session_id: int, count: int):
    """Remove the oldest N bullets from the active rolling digest after Tier 3 compaction."""
    if count <= 0:
        return
    with get_conn() as conn:
        row = conn.execute("SELECT chapter_digest_json FROM sessions WHERE id=?", (session_id,)).fetchone()
        if not row or not row["chapter_digest_json"]:
            return
        try:
            current = json.loads(row["chapter_digest_json"])
            if not isinstance(current, list) or not current:
                return
        except Exception:
            return
        trimmed = current[count:]
        conn.execute(
            "UPDATE sessions SET chapter_digest_json=? WHERE id=?",
            (json.dumps(trimmed), session_id),
        )


def get_chapter_digest(session_id: int) -> list[str]:
    """Return the current list of chapter digest bullet strings for a session."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT chapter_digest_json FROM sessions WHERE id=?",
            (session_id,),
        ).fetchone()
    if not row:
        return []
    raw = row["chapter_digest_json"] or "[]"
    try:
        result = json.loads(raw)
        return result if isinstance(result, list) else []
    except Exception:
        return []


def search_chapter_digests(session_id: int, query_text: str, limit: int = 6, query_embedding: list[float] = None) -> list[str]:
    """Search chapter digest bullets using 5-language + CJK bigram FTS5 BM25 matching."""
    from mechanics.system.memory.tokenization import sanitize_fts_query

    if not session_id or not query_text or not query_text.strip():
        return []

    fts_query = sanitize_fts_query(query_text)
    if not fts_query:
        return []

    with get_conn() as conn:
        try:
            fts_rows = conn.execute(
                """SELECT bullet_text FROM session_digests_fts
                   WHERE session_id=? AND session_digests_fts MATCH ?
                   ORDER BY rank LIMIT 25""",
                (session_id, fts_query),
            ).fetchall()
            seen: set[str] = set()
            deduped: list[str] = []
            for r in fts_rows:
                bt = r["bullet_text"]
                if bt and bt not in seen:
                    seen.add(bt)
                    deduped.append(bt)
            return deduped[:limit]
        except Exception as e:
            log.warning(f"FTS5 chapter digest search failed: {e}")
            return []


def recall_chapter_digests(
    session_id: int,
    query_text: str = "",
    present_npcs: list[str] | None = None,
    current_location: str = "",
    active_quest_ids: list[str] | None = None,
    limit: int = 6,
) -> list[str]:
    """Retrieve contextually relevant historic arc bullets via 2-Signal Scoring (Entity/Location/Quest + FTS5 BM25)."""
    from mechanics.system.memory.tokenization import sanitize_fts_query, score_digest_candidates

    if not session_id:
        return []

    fts_query = sanitize_fts_query(query_text) if query_text else ""
    fts_ranks: dict[str, float] = {}
    parsed_rows: list[dict] = []

    with get_conn() as conn:
        if fts_query:
            try:
                rows = conn.execute(
                    """SELECT bullet_text FROM session_digests_fts
                       WHERE session_id = ? AND session_digests_fts MATCH ?
                       ORDER BY rank LIMIT 25""",
                    (session_id, fts_query),
                ).fetchall()
                for idx, r in enumerate(rows):
                    bt = r["bullet_text"]
                    if bt and bt not in fts_ranks:
                        fts_ranks[bt] = 1.0 / (idx + 1)
            except Exception:
                pass

        raw_digests = conn.execute(
            """SELECT summary_bullets_json, entities_json, location_tag, quest_ids_json, compacted_count
               FROM session_digests
               WHERE session_id = ? AND is_compacted = 0
               ORDER BY turn_end DESC, id DESC LIMIT 30""",
            (session_id,),
        ).fetchall()

    for r in raw_digests:
        try:
            bullets = json.loads(r["summary_bullets_json"] or "[]")
        except Exception:
            bullets = []
        if isinstance(bullets, list):
            cc = int(r["compacted_count"] or 0)
            bullets = bullets[cc:] if cc > 0 else bullets
        else:
            bullets = []
        try:
            entities = json.loads(r["entities_json"] or "[]")
        except Exception:
            entities = []
        try:
            quests = json.loads(r["quest_ids_json"] or "[]")
        except Exception:
            quests = []
        parsed_rows.append(
            {
                "bullets": bullets,
                "entities": entities if isinstance(entities, list) else [],
                "location_tag": str(r["location_tag"] or ""),
                "quest_ids": quests if isinstance(quests, list) else [],
            }
        )

    return score_digest_candidates(
        digest_rows=parsed_rows,
        fts_ranks=fts_ranks,
        present_npcs=present_npcs,
        current_location=current_location,
        active_quest_ids=active_quest_ids,
        limit=limit,
    )


def active_recall_search(session_id: int, query_text: str, limit: int = 10) -> list[str]:
    """Execute a deep FTS5 search across all past chapters specifically for resolving player 'recall' questions."""
    return search_chapter_digests(session_id, query_text, limit=limit)


def format_digest_prompt_block(
    session_id: int,
    query_context: str = "",
    max_recent: int = 6,
    max_relevant: int = 6,
    query_embedding: list[float] = None,
    present_npcs: list[str] | None = None,
    current_location: str = "",
    active_quest_ids: list[str] | None = None,
) -> str:
    """Format Tier 3 Saga Chronicles + Tier 2 Chapter Digest into a compact prompt block."""
    bullets = get_chapter_digest(session_id)
    chronicles = get_session_chronicles(session_id)
    if not bullets and not chronicles:
        return ""

    chronicle_block = ""
    if chronicles:
        recent_chronicles = chronicles[-3:]
        chronicle_lines = ["[SAGA CHRONICLES — Epic events of past chapters]:"]
        if len(chronicles) > len(recent_chronicles):
            chronicle_lines.append(f"• [Earlier chapters 1 through {chronicles[-4]['chapter_number']} have been archived from immediate memory]")
        for c in recent_chronicles:
            chronicle_lines.append(f"• Chapter {c['chapter_number']} ({c['act_title']}): {c['summary_narrative']}")
        chronicle_block = "\n".join(chronicle_lines)

    if not bullets:
        return chronicle_block

    # 1. Grab recent chronological anchor
    recent = bullets[-max_recent:]
    recent_set = set(recent)

    # 2. Grab relevant historic bullets via 2-signal entity + multilingual FTS5 recall
    relevant = []
    if query_context or present_npcs or current_location or active_quest_ids:
        recalled = recall_chapter_digests(
            session_id,
            query_text=query_context,
            present_npcs=present_npcs,
            current_location=current_location,
            active_quest_ids=active_quest_ids,
            limit=max_relevant,
        )
        for match in recalled:
            if match not in recent_set:
                relevant.append(match)

    if not recent and not relevant:
        return chronicle_block

    def _categorize(bullet_list: list[str]) -> tuple[list[str], list[str], list[str]]:
        story, hooks, resources = [], [], []
        for b in bullet_list:
            if b.startswith("[HOOK]"):
                hooks.append(b[len("[HOOK]"):].strip())
            elif b.startswith("[RESOURCE]"):
                resources.append(b[len("[RESOURCE]"):].strip())
            else:
                story.append(b)
        return story, hooks, resources

    lines = ["[PAST ARC MEMORY — Earlier events in this adventure]:"]
    if relevant:
        rel_story, rel_hooks, rel_resources = _categorize(relevant)
        lines.append("(Relevant History):")
        for b in rel_story:
            lines.append(f"• {b}")
        if rel_hooks:
            for b in rel_hooks:
                lines.append(f"• [Hook] {b}")
        if rel_resources:
            for b in rel_resources:
                lines.append(f"• [Resource] {b}")

    if recent:
        rec_story, rec_hooks, rec_resources = _categorize(recent)
        if relevant:
            lines.append("(Recent Arc):")
        if rec_story:
            lines.append("(Story Events):")
            for b in rec_story:
                lines.append(f"• {b}")
        if rec_hooks:
            lines.append("(Active Hooks & Rumors):")
            for b in rec_hooks:
                lines.append(f"• {b}")
        if rec_resources:
            lines.append("(Recent Resource Diffs):")
            for b in rec_resources:
                lines.append(f"• {b}")

    if chronicle_block:
        return chronicle_block + "\n\n" + "\n".join(lines)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Advanced Memory (Tier 3: Chronicles & Tier 1.5: NPC Episodic Memory)
# ---------------------------------------------------------------------------

def add_session_chronicle(
    session_id: int,
    chapter_number: int,
    act_title: str,
    summary_narrative: str,
    consequences: list = None,
    turn_start: int = 0,
    turn_end: int = 0,
    created_turn: int = 0,
    bullet_count: int = 15,
):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO session_chronicles 
               (session_id, chapter_number, act_title, summary_narrative, key_consequences_json,
                turn_start, turn_end, created_turn, bullet_count, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                chapter_number,
                act_title,
                summary_narrative,
                json.dumps(consequences or []),
                int(turn_start or 0),
                int(turn_end or 0),
                int(created_turn or 0),
                int(bullet_count or 15),
                time.time(),
            ),
        )

def get_session_chronicles(session_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM session_chronicles WHERE session_id=? ORDER BY chapter_number ASC", 
            (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]

def add_npc_memory(
    session_id: int,
    npc_name: str,
    turn_index: int,
    memory_fact: str,
    sentiment_delta: int = 0,
    importance: int = 1,
    is_secret: bool = False,
    emotional_tone: str = "",
    open_thread: str = "",
):
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO npc_memories 
               (session_id, npc_name, turn_index, memory_fact, sentiment_delta, importance, is_secret, emotional_tone, open_thread, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, npc_name, turn_index, memory_fact, sentiment_delta, importance, 1 if is_secret else 0, emotional_tone or "", open_thread or "", time.time())
        )

def get_npc_memories(session_id: int, npc_name: str) -> list[dict]:
    with get_conn() as conn:
        # Sort by importance (Salience) first, then recency, to prevent core memories from being pushed out
        rows = conn.execute(
            "SELECT * FROM npc_memories WHERE session_id=? AND lower(npc_name)=lower(?) ORDER BY importance DESC, turn_index DESC", 
            (session_id, npc_name)
        ).fetchall()
        return [dict(r) for r in rows]


def get_npc_memories_batch(
    session_id: int,
    npc_names: list[str] | None,
    per_npc_limit: int = 5,
) -> dict[str, list[dict]]:
    """Fetch top-N memories per NPC in a single SQLite window query (`ROW_NUMBER() OVER`)."""
    if not session_id or per_npc_limit <= 0 or not npc_names:
        return {}
    clean_names = sorted({str(n).strip().lower() for n in npc_names if n and str(n).strip()})
    if not clean_names:
        return {}

    placeholders = ",".join("?" for _ in clean_names)
    sql = f"""
        WITH ranked AS (
            SELECT id, session_id, npc_name, turn_index, memory_fact, sentiment_delta,
                   importance, is_secret, emotional_tone, open_thread, created_at,
                   LOWER(npc_name) AS npc_key,
                   ROW_NUMBER() OVER (
                       PARTITION BY LOWER(npc_name)
                       ORDER BY importance DESC, turn_index DESC, id DESC
                   ) AS rn
            FROM npc_memories
            WHERE session_id = ? AND LOWER(npc_name) IN ({placeholders})
        )
        SELECT id, session_id, npc_name, turn_index, memory_fact, sentiment_delta,
               importance, is_secret, emotional_tone, open_thread, created_at, npc_key
        FROM ranked
        WHERE rn <= ?
        ORDER BY npc_key ASC, importance DESC, turn_index DESC, id DESC
    """
    params = [int(session_id), *clean_names, int(per_npc_limit)]
    grouped: dict[str, list[dict]] = {}
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        for r in rows:
            d = dict(r)
            key = d.pop("npc_key", str(d.get("npc_name") or "").strip().lower())
            grouped.setdefault(key, []).append(d)
    return grouped
