from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Optional

from .core import UnitOfWork, get_conn


def infer_session_turn(session: Optional[dict[str, Any]]) -> int:
    """Safely infers 1-based turn number from a session dict without relying on non-existent turn_count columns."""
    if not isinstance(session, dict):
        return 1
    if isinstance(session.get("turn_count"), int) and session["turn_count"] > 0:
        return int(session["turn_count"])
    hist = session.get("history")
    if isinstance(hist, list):
        return max(1, len(hist) + 1)
    raw_hist = session.get("history_json")
    if isinstance(raw_hist, str) and raw_hist.strip():
        try:
            parsed = json.loads(raw_hist)
            if isinstance(parsed, list):
                return max(1, len(parsed) + 1)
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    return max(1, int(session.get("current_turn_index") or 0) + 1)


def _deserialize_world_event_row(row_dict: dict[str, Any]) -> dict[str, Any]:
    """Deserializes JSON columns into native Python dicts while keeping raw JSON columns intact."""
    d = dict(row_dict)
    for json_col, target in (("modifiers_json", "modifiers"), ("metadata_json", "metadata")):
        raw = d.get(json_col)
        if isinstance(raw, str):
            try:
                d[target] = json.loads(raw or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                d[target] = {}
        elif isinstance(raw, dict):
            d[target] = raw
        else:
            d[target] = {}
    return d


def create_world_event(
    session_id: int,
    event_key: str,
    entity_type: str = "macro_event",
    event_subtype: str = "crisis",
    title: str = "",
    description: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    """Persists a procedural macro world event, minor incident, or rumor into world_events."""
    now = float(kwargs.get("created_at") or time.time())
    template_key = str(kwargs.get("template_key") or "")
    sfw_fallback = str(kwargs.get("sfw_fallback_description") or "")
    faction_id = str(kwargs.get("faction_id") or "")
    implicated_contact_id = kwargs.get("implicated_contact_id")
    if implicated_contact_id is not None:
        try:
            implicated_contact_id = int(implicated_contact_id)
        except (TypeError, ValueError):
            implicated_contact_id = None
    location_node_id = str(kwargs.get("location_node_id") or "")
    location_name = str(kwargs.get("location_name") or "")
    turn_created = int(kwargs.get("turn_created") or kwargs.get("active_since_turn") or 1)
    if entity_type in ("macro_event", "minor_event"):
        is_discovered = 1
        default_disc_src = "world_event" if entity_type == "macro_event" else "bulletin"
        discovery_source = str(kwargs.get("discovery_source") or default_disc_src)
    else:
        is_discovered = int(bool(kwargs.get("is_discovered", 0)))
        discovery_source = str(kwargs.get("discovery_source") or ("world_event" if is_discovered else ""))
    discovered_turn = kwargs.get("discovered_turn")
    if discovered_turn is None and is_discovered:
        discovered_turn = turn_created
    claimed_turn = kwargs.get("claimed_turn")
    linked_quest_id = str(kwargs.get("linked_quest_id") or "")
    status = str(kwargs.get("status") or "active")
    prior_status = str(kwargs.get("prior_status_before_resolve") or "active")
    resolved_turn = kwargs.get("resolved_turn")
    expires_day = kwargs.get("expires_day")
    expires_minute = kwargs.get("expires_minute")
    original_expires_day = kwargs.get("original_expires_day", expires_day)
    original_expires_minute = kwargs.get("original_expires_minute", expires_minute)
    escalation_chance = float(kwargs.get("escalation_chance") or 0.0)
    escalation_event_key = str(kwargs.get("escalation_event_key") or "")
    is_nsfw = int(bool(kwargs.get("is_nsfw", 0)))

    raw_mod = kwargs.get("modifiers") if kwargs.get("modifiers") is not None else kwargs.get("modifiers_json")
    modifiers_json = json.dumps(raw_mod) if isinstance(raw_mod, dict) else str(raw_mod or "{}")
    raw_meta = kwargs.get("metadata") if kwargs.get("metadata") is not None else kwargs.get("metadata_json")
    metadata_json = json.dumps(raw_meta) if isinstance(raw_meta, dict) else str(raw_meta or "{}")

    with UnitOfWork() as conn:
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id, event_key) DO UPDATE SET
                template_key = excluded.template_key,
                entity_type = excluded.entity_type,
                event_subtype = excluded.event_subtype,
                title = excluded.title,
                description = excluded.description,
                sfw_fallback_description = excluded.sfw_fallback_description,
                faction_id = excluded.faction_id,
                implicated_contact_id = excluded.implicated_contact_id,
                location_node_id = excluded.location_node_id,
                location_name = excluded.location_name,
                is_discovered = excluded.is_discovered,
                discovery_source = excluded.discovery_source,
                discovered_turn = excluded.discovered_turn,
                claimed_turn = excluded.claimed_turn,
                linked_quest_id = excluded.linked_quest_id,
                status = excluded.status,
                prior_status_before_resolve = excluded.prior_status_before_resolve,
                turn_created = excluded.turn_created,
                resolved_turn = excluded.resolved_turn,
                original_expires_day = COALESCE(world_events.original_expires_day, excluded.original_expires_day),
                original_expires_minute = COALESCE(world_events.original_expires_minute, excluded.original_expires_minute),
                expires_day = excluded.expires_day,
                expires_minute = excluded.expires_minute,
                escalation_chance = excluded.escalation_chance,
                escalation_event_key = excluded.escalation_event_key,
                is_nsfw = excluded.is_nsfw,
                modifiers_json = excluded.modifiers_json,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at""",
            (
                session_id, event_key, template_key, entity_type, event_subtype,
                title, description, sfw_fallback, faction_id, implicated_contact_id,
                location_node_id, location_name, is_discovered, discovery_source,
                discovered_turn, claimed_turn, linked_quest_id, status,
                prior_status, turn_created, resolved_turn,
                original_expires_day, original_expires_minute,
                expires_day, expires_minute, escalation_chance, escalation_event_key,
                is_nsfw, modifiers_json, metadata_json, now, now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM world_events WHERE session_id = ? AND event_key = ?",
            (session_id, event_key),
        ).fetchone()
        return _deserialize_world_event_row(dict(row))


def get_world_event_by_key(session_id: int, event_key: str) -> dict[str, Any] | None:
    """Retrieves a single deserialized world event by session_id and event_key."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM world_events WHERE session_id = ? AND event_key = ?",
            (session_id, event_key),
        ).fetchone()
        if not row:
            return None
        return _deserialize_world_event_row(dict(row))


def get_world_events(
    session_id: int,
    entity_type: Optional[str] = None,
    include_hidden: bool = False,
    statuses: Optional[tuple[str, ...]] = None,
) -> list[dict[str, Any]]:
    """Fetches world events/rumors filtered by entity_type, visibility, and statuses."""
    query = "SELECT * FROM world_events WHERE session_id = ?"
    params: list[Any] = [session_id]

    if entity_type:
        query += " AND entity_type = ?"
        params.append(entity_type)

    if not include_hidden:
        query += " AND (is_discovered = 1 OR entity_type IN ('macro_event', 'minor_event'))"

    if statuses:
        placeholders = ",".join("?" * len(statuses))
        query += f" AND status IN ({placeholders})"
        params.extend(statuses)

    query += " ORDER BY id ASC"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [_deserialize_world_event_row(dict(r)) for r in rows]


def get_world_events_snapshot(session_id: int) -> dict[str, Any]:
    """Single-roundtrip snapshot prefetch powering TurnService, pure modifiers, and API serialization."""
    if not session_id:
        return {
            "session_id": 0,
            "active_macro_events": [],
            "active_rumors": [],
            "active_minor_events": [],
            "discovered_rumors": [],
            "all_events": [],
            "pity_state": {
                "event_pity_counter": 0.0,
                "rumor_pity_counter": 0.0,
                "minor_event_pity_counter": 0.0,
                "player_scandal_cooldown_until_day": 0,
                "recent_witness_catches": [],
                "npc_gossip_shared_today": {},
            },
        }
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM world_events WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        all_events = [_deserialize_world_event_row(dict(r)) for r in rows]

    active_macro_events = [
        e for e in all_events
        if e["entity_type"] == "macro_event" and e["status"] in ("active", "resolved_aftermath")
    ]
    active_rumors = [
        e for e in all_events
        if e["entity_type"] == "rumor" and e["status"] in ("active", "resolved_aftermath")
    ]
    active_minor_events = [
        e for e in all_events
        if e["entity_type"] == "minor_event" and e["status"] in ("active", "resolved_aftermath")
    ]
    discovered_rumors = [
        e for e in active_rumors
        if bool(e["is_discovered"])
    ]
    pity_state = get_session_world_pity_state(session_id)

    return {
        "session_id": session_id,
        "active_macro_events": active_macro_events,
        "active_rumors": active_rumors,
        "active_minor_events": active_minor_events,
        "discovered_rumors": discovered_rumors,
        "all_events": all_events,
        "pity_state": pity_state,
    }


def discover_world_event(
    session_id: int,
    event_key: str,
    turn_number: int,
    discovery_source: str = "npc",
) -> bool:
    """Reveals a hidden rumor, stamping discovery turn and narrative source."""
    with UnitOfWork() as conn:
        cur = conn.execute(
            """UPDATE world_events
               SET is_discovered = 1,
                   discovered_turn = ?,
                   discovery_source = ?,
                   updated_at = ?
               WHERE session_id = ? AND event_key = ? AND is_discovered = 0""",
            (int(turn_number), str(discovery_source or "npc"), time.time(), session_id, event_key),
        )
        return cur.rowcount > 0


def _validate_event_bounty_claim(
    conn: sqlite3.Connection,
    session_id: int,
    event_key: str,
    *,
    require_minor: bool = False,
) -> tuple[dict[str, Any], bool, dict[str, Any]]:
    ev_row = conn.execute(
        "SELECT * FROM world_events WHERE session_id = ? AND event_key = ?",
        (session_id, event_key),
    ).fetchone()
    if not ev_row:
        raise ValueError(f"Event '{event_key}' not found.")
    ev_dict = _deserialize_world_event_row(dict(ev_row))
    ent_type = str(ev_dict.get("entity_type") or "")
    if require_minor and ent_type != "minor_event":
        raise ValueError(f"Event '{event_key}' is not a minor event (type: {ent_type}).")
    if ent_type not in ("rumor", "minor_event"):
        raise ValueError(f"Event '{event_key}' (type: {ent_type}) cannot be tracked as an investigation.")

    is_minor = ent_type == "minor_event"
    meta = ev_dict.get("metadata") or {}
    if is_minor:
        if not bool(meta.get("can_spawn_bounty")):
            raise ValueError(f"Minor event '{event_key}' cannot be tracked as a bounty.")
    elif not ev_dict["is_discovered"]:
        raise ValueError(f"Rumor '{event_key}' has not been discovered yet.")

    if ev_dict["status"] != "active":
        raise ValueError(f"Event '{event_key}' is not active (status: {ev_dict['status']}).")
    if ev_dict["claimed_turn"] is not None and ev_dict["linked_quest_id"]:
        raise ValueError(f"Event '{event_key}' is already being tracked.")

    if is_minor:
        cnt_row = conn.execute(
            """SELECT COUNT(*) as cnt FROM quests
               WHERE session_id = ?
                 AND (quest_id LIKE 'MNR-%' OR quest_notes LIKE '%minor_bounty:1%')
                 AND status = 'Active'""",
            (session_id,),
        ).fetchone()
        if (cnt_row["cnt"] if cnt_row else 0) >= 2:
            raise ValueError("Maximum active minor bounties (2/2) reached.")
    else:
        cnt_row = conn.execute(
            """SELECT COUNT(*) as cnt FROM quests
               WHERE session_id = ?
                 AND (quest_id LIKE 'RMR-%' OR quest_notes LIKE '%rumor_investigation:1%')
                 AND status = 'Active'""",
            (session_id,),
        ).fetchone()
        if (cnt_row["cnt"] if cnt_row else 0) >= 2:
            raise ValueError("Maximum active rumor investigations (2/2) reached.")
    return ev_dict, is_minor, meta


def _persist_event_bounty_claim(
    conn: sqlite3.Connection,
    ev_dict: dict[str, Any],
    *,
    is_minor: bool,
    meta: dict[str, Any],
    current_day: int,
    current_minute: int,
    turn_number: int,
    investigation_days: int = 4,
) -> dict[str, Any]:
    import db as _db_pkg

    now = time.time()
    session_id = int(ev_dict["session_id"])
    event_key = str(ev_dict["event_key"])
    deadline_day = int(current_day) + int(investigation_days)
    deadline_minute = int(current_minute)
    quest_seq = (int(now * 1000) % 900_000) + 100_000
    prefix = "MNR" if is_minor else "RMR"
    quest_id = f"{prefix}-{session_id}-{ev_dict['id']}-{quest_seq}"

    q_type = "Minor Incident" if is_minor else "Rumor Investigation"
    q_notes = "minor_bounty:1" if is_minor else "rumor_investigation:1"
    q_reward_xp = 25 if is_minor else 50
    q_reward_gold = 10 if is_minor else 20
    wp_label = "Address Incident" if is_minor else "Investigate Rumor Lead"
    q_title = str(meta.get("bounty_title") or f"{'Look Into' if is_minor else 'Investigate'}: {ev_dict['title']}")
    q_obj = str(
        meta.get("bounty_objective")
        or f"{'Address the incident' if is_minor else 'Track leads and uncover the truth'} regarding: {ev_dict['title']}"
    )
    loc_label = str(ev_dict["location_name"] or "Local District")
    loc_node_id = str(ev_dict.get("location_node_id") or "")
    if not loc_node_id and loc_label:
        try:
            resolved_nid = _db_pkg.resolve_node_id_from_location(session_id, loc_label)
            if resolved_nid:
                loc_node_id = str(resolved_nid)
            else:
                sess_row = conn.execute(
                    "SELECT current_location, current_node_id FROM sessions WHERE id = ?",
                    (session_id,),
                ).fetchone()
                if sess_row:
                    if not loc_label or loc_label == "Local District":
                        loc_label = str(sess_row["current_location"] or "District Center")
                    loc_node_id = str(sess_row["current_node_id"] or "")
        except (sqlite3.Error, AttributeError, KeyError, TypeError, ValueError):
            loc_node_id = loc_node_id or ""

    micro_engine = "CRISIS_DEFENSE" if is_minor else "SOCIAL_BROKERAGE"
    conn.execute(
        """INSERT INTO quests (
            session_id, quest_id, quest_type, title, objective, status,
            reward_xp, reward_gold, quest_notes, client_location,
            deadline_day, deadline_minute, engine, dossier_stage, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 'Active', ?, ?, ?, ?, ?, ?, ?, 'compiled', ?, ?)""",
        (
            session_id, quest_id, q_type, q_title, q_obj,
            q_reward_xp, q_reward_gold, q_notes,
            loc_label, deadline_day, deadline_minute, micro_engine, now, now,
        ),
    )
    try:
        from mechanics.narrative.dossier_compiler import compile_micro_dossier
        compile_micro_dossier(
            session_id=session_id,
            quest_id=quest_id,
            title=q_title,
            objective=q_obj,
            location_name=loc_label,
            is_minor=is_minor,
            turn_number=int(turn_number),
            conn=conn,
        )
    except Exception:
        pass

    conn.execute(
        """INSERT INTO quest_waypoints (
            session_id, quest_id, stage_index, stage_label,
            target_location, target_node_id, completion_trigger, status,
            created_at, updated_at
        ) VALUES (?, ?, 0, ?, ?, ?, 'arrival', 'active', ?, ?)""",
        (
            session_id, quest_id, wp_label, loc_label,
            loc_node_id, now, now,
        ),
    )

    conn.execute(
        """UPDATE world_events
           SET original_expires_day = COALESCE(original_expires_day, expires_day),
               original_expires_minute = COALESCE(original_expires_minute, expires_minute),
               claimed_turn = ?,
               linked_quest_id = ?,
               expires_day = ?,
               expires_minute = ?,
               updated_at = ?
           WHERE session_id = ? AND event_key = ?""",
        (int(turn_number), quest_id, deadline_day, deadline_minute, now, session_id, event_key),
    )

    q_row = conn.execute(
        "SELECT * FROM quests WHERE session_id = ? AND quest_id = ?",
        (session_id, quest_id),
    ).fetchone()

    return {
        "success": True,
        "status": "claimed",
        "session_id": session_id,
        "event_key": event_key,
        "quest_id": quest_id,
        "quest": dict(q_row) if q_row else {"quest_id": quest_id, "title": q_title, "status": "Active"},
        "deadline_day": deadline_day,
        "deadline_minute": deadline_minute,
        "claimed_turn": int(turn_number),
    }


def claim_rumor_investigation(
    session_id: int,
    event_key: str,
    current_day: int,
    current_minute: int,
    turn_number: int,
    investigation_days: int = 4,
    *,
    _require_minor: bool = False,
) -> dict[str, Any]:
    """Atomically accepts a rumor investigation (RMR-) or minor event bounty (MNR-) under its dedicated 2-slot cap."""
    with UnitOfWork() as conn:
        ev_dict, is_minor, meta = _validate_event_bounty_claim(
            conn, int(session_id), str(event_key).strip(), require_minor=_require_minor
        )
        return _persist_event_bounty_claim(
            conn,
            ev_dict,
            is_minor=is_minor,
            meta=meta,
            current_day=int(current_day),
            current_minute=int(current_minute),
            turn_number=int(turn_number),
            investigation_days=int(investigation_days),
        )


def claim_minor_event_bounty(
    session_id: int,
    event_key: str,
    current_day: int,
    current_minute: int,
    turn_number: int,
    investigation_days: int = 4,
) -> dict[str, Any]:
    """Atomically accepts an opt-in micro-bounty (MNR-) for a claimable minor_event under the independent 2-slot cap."""
    if not session_id or not event_key:
        raise ValueError("Valid session_id and event_key are required to claim a minor event bounty.")
    with UnitOfWork() as conn:
        ev_dict, is_minor, meta = _validate_event_bounty_claim(
            conn, int(session_id), str(event_key).strip(), require_minor=True
        )
        return _persist_event_bounty_claim(
            conn,
            ev_dict,
            is_minor=is_minor,
            meta=meta,
            current_day=int(current_day),
            current_minute=int(current_minute),
            turn_number=int(turn_number),
            investigation_days=int(investigation_days),
        )


def resolve_world_event(
    session_id: int,
    event_key: str,
    new_status: str,
    current_day: int,
    current_minute: int,
    turn_number: int,
    aftermath_hours: int = 24,
) -> bool:
    """Transitions a macro event, rumor, or minor event into resolved_aftermath or expired state while preserving original expiry."""
    now = time.time()
    active_linked_qid = ""
    party_uids: list[int] = []
    with UnitOfWork() as conn:
        ev_row = conn.execute(
            "SELECT * FROM world_events WHERE session_id = ? AND event_key = ?",
            (session_id, event_key),
        ).fetchone()
        if not ev_row:
            return False

        ev_dict = dict(ev_row)
        prior_status = ev_dict["status"] if ev_dict["status"] != new_status else (ev_dict.get("prior_status_before_resolve") or "active")
        expires_day = ev_dict["expires_day"]
        expires_minute = ev_dict["expires_minute"]

        if new_status == "resolved_aftermath":
            total_minutes = int(current_minute) + (int(aftermath_hours) * 60)
            expires_day = int(current_day) + (total_minutes // 1440)
            expires_minute = total_minutes % 1440

        conn.execute(
            """UPDATE world_events
               SET original_expires_day = COALESCE(original_expires_day, expires_day),
                   original_expires_minute = COALESCE(original_expires_minute, expires_minute),
                   prior_status_before_resolve = ?,
                   status = ?,
                   resolved_turn = ?,
                   expires_day = ?,
                   expires_minute = ?,
                   updated_at = ?
               WHERE session_id = ? AND event_key = ?""",
            (prior_status, new_status, int(turn_number), expires_day, expires_minute, now, session_id, event_key),
        )

        linked_qid = str(ev_dict.get("linked_quest_id") or "")
        if linked_qid:
            if new_status in ("expired", "cold"):
                conn.execute(
                    "UPDATE quests SET status = 'Expired', updated_at = ? WHERE session_id = ? AND quest_id = ? AND status = 'Active'",
                    (now, session_id, linked_qid),
                )
            elif new_status == "resolved_aftermath":
                q_row = conn.execute(
                    "SELECT status FROM quests WHERE session_id = ? AND quest_id = ?",
                    (session_id, linked_qid),
                ).fetchone()
                if q_row and q_row["status"] == "Active":
                    active_linked_qid = linked_qid
                    m_rows = conn.execute(
                        "SELECT user_id FROM session_members WHERE session_id = ? ORDER BY joined_at ASC",
                        (session_id,),
                    ).fetchall()
                    party_uids = [int(r["user_id"]) for r in m_rows if r["user_id"]]
                    if not party_uids:
                        s_row = conn.execute(
                            "SELECT host_user_id FROM sessions WHERE id = ?",
                            (session_id,),
                        ).fetchone()
                        if s_row and s_row["host_user_id"]:
                            party_uids = [int(s_row["host_user_id"])]
                    if not party_uids:
                        c_rows = conn.execute("SELECT user_id FROM characters ORDER BY user_id ASC LIMIT 1").fetchall()
                        party_uids = [int(r["user_id"]) for r in c_rows if r["user_id"]] or [1]

    if active_linked_qid:
        from .quests import claim_quest_reward

        claim_quest_reward(session_id, active_linked_qid, party_user_ids=party_uids)

    return True


def mark_world_event_cold(
    session_id: int,
    event_key: str,
    turn_number: int,
    linked_quest_id: str = "",
) -> bool:
    """Atomically transitions an overdue claimed rumor or minor bounty to 'cold' while preserving linked_quest_id and resolved_turn for rollback."""
    now = time.time()
    with UnitOfWork() as conn:
        ev_row = conn.execute(
            "SELECT status, linked_quest_id, prior_status_before_resolve FROM world_events WHERE session_id = ? AND event_key = ?",
            (session_id, event_key),
        ).fetchone()
        if not ev_row:
            return False
        prior_status = ev_row["status"] if ev_row["status"] != "cold" else (ev_row["prior_status_before_resolve"] or "active")
        eff_qid = str(linked_quest_id or ev_row["linked_quest_id"] or "")
        conn.execute(
            """UPDATE world_events
               SET original_expires_day = COALESCE(original_expires_day, expires_day),
                   original_expires_minute = COALESCE(original_expires_minute, expires_minute),
                   prior_status_before_resolve = ?,
                   status = 'cold',
                   linked_quest_id = '',
                   metadata_json = json_set(COALESCE(NULLIF(metadata_json, ''), '{}'), '$._cold_linked_quest_id', ?),
                   resolved_turn = ?,
                   updated_at = ?
               WHERE session_id = ? AND event_key = ?""",
            (prior_status, eff_qid, int(turn_number), now, session_id, event_key),
        )
        if eff_qid:
            conn.execute(
                "UPDATE quests SET status = 'Expired', updated_at = ? WHERE session_id = ? AND quest_id = ? AND status = 'Active'",
                (now, session_id, eff_qid),
            )
        return True


def defer_world_event_expiry(
    session_id: int,
    event_key: str,
    expires_day: int,
    expires_minute: int,
) -> bool:
    """Defers an active world event or rumor expiry timestamp without mutating resolution state."""
    with UnitOfWork() as conn:
        cur = conn.execute(
            "UPDATE world_events SET expires_day = ?, expires_minute = ?, updated_at = ? WHERE session_id = ? AND event_key = ?",
            (int(expires_day), int(expires_minute), time.time(), int(session_id), str(event_key)),
        )
        return cur.rowcount > 0


def convert_rumor_to_loyalty_quest(
    session_id: int,
    event_key: str,
    npc_name: str,
    current_day: int,
    current_minute: int,
    turn_number: int,
) -> dict[str, Any]:
    """Promotes an active rumor into a 'Clear Their Name' loyalty quest when a romantic/companion bond forms."""
    now = time.time()
    with UnitOfWork() as conn:
        ev_row = conn.execute(
            "SELECT * FROM world_events WHERE session_id = ? AND event_key = ?",
            (session_id, event_key),
        ).fetchone()
        if not ev_row:
            raise ValueError(f"Rumor '{event_key}' not found.")
        ev_dict = dict(ev_row)

        old_qid = ev_dict.get("linked_quest_id")
        if old_qid:
            conn.execute("DELETE FROM quest_waypoints WHERE session_id = ? AND quest_id = ?", (session_id, old_qid))
            conn.execute("DELETE FROM quests WHERE session_id = ? AND quest_id = ?", (session_id, old_qid))

        quest_seq = (int(now * 1000) % 900_000) + 100_000
        new_qid = f"CLR-{session_id}-{ev_dict['id']}-{quest_seq}"
        q_title = f"Clear Their Name: {npc_name}"
        q_obj = f"Investigate the malicious rumors surrounding {npc_name} and vindicate their reputation."
        loc_label = str(ev_dict["location_name"] or "Local District")

        conn.execute(
            """INSERT INTO quests (
                session_id, quest_id, quest_type, title, objective, status,
                reward_xp, reward_gold, quest_notes, client_npc, client_location,
                deadline_day, deadline_minute, created_at, updated_at
            ) VALUES (?, ?, 'Loyalty Quest', ?, ?, 'Active', 100, 30, 'loyalty_quest:1', ?, ?, ?, ?, ?, ?)""",
            (
                session_id, new_qid, q_title, q_obj,
                npc_name, loc_label,
                int(current_day) + 7, int(current_minute), now, now,
            ),
        )

        conn.execute(
            """INSERT INTO quest_waypoints (
                session_id, quest_id, stage_index, stage_label,
                target_location, target_node_id, completion_trigger, status,
                created_at, updated_at
            ) VALUES (?, ?, 0, 'Investigate Malicious Source', ?, ?, 'arrival', 'active', ?, ?)""",
            (
                session_id, new_qid, loc_label,
                str(ev_dict["location_node_id"] or ""), now, now,
            ),
        )

        conn.execute(
            """UPDATE world_events
               SET is_discovered = 1,
                   discovered_turn = COALESCE(discovered_turn, ?),
                   claimed_turn = ?,
                   linked_quest_id = ?,
                   original_expires_day = COALESCE(original_expires_day, expires_day),
                   original_expires_minute = COALESCE(original_expires_minute, expires_minute),
                   expires_day = ?,
                   expires_minute = ?,
                   updated_at = ?
               WHERE session_id = ? AND event_key = ?""",
            (int(turn_number), int(turn_number), new_qid, int(current_day) + 7, int(current_minute), now, session_id, event_key),
        )

        return {
            "status": "converted",
            "session_id": session_id,
            "event_key": event_key,
            "quest_id": new_qid,
            "title": q_title,
            "npc_name": npc_name,
            "claimed_turn": int(turn_number),
        }


def get_session_world_pity_state(session_id: int) -> dict[str, Any]:
    """Retrieves session-scoped procedural event and rumor pity counters and scandal states."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT event_pity_counter, rumor_pity_counter, minor_event_pity_counter,
                      player_scandal_cooldown_until_day, recent_witness_catches_json,
                      npc_gossip_shared_today_json
               FROM sessions WHERE id = ?""",
            (session_id,),
        ).fetchone()
        if not row:
            return {
                "event_pity_counter": 0.0,
                "rumor_pity_counter": 0.0,
                "minor_event_pity_counter": 0.0,
                "player_scandal_cooldown_until_day": 0,
                "recent_witness_catches": [],
                "npc_gossip_shared_today": {},
            }
        d = dict(row)
        catches: list[Any] = []
        if d.get("recent_witness_catches_json"):
            try:
                catches = json.loads(d["recent_witness_catches_json"] or "[]")
            except (TypeError, ValueError, json.JSONDecodeError):
                catches = []
        gossip: dict[str, Any] = {}
        if d.get("npc_gossip_shared_today_json"):
            try:
                gossip = json.loads(d["npc_gossip_shared_today_json"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                gossip = {}
        return {
            "event_pity_counter": float(d.get("event_pity_counter") or 0.0),
            "rumor_pity_counter": float(d.get("rumor_pity_counter") or 0.0),
            "minor_event_pity_counter": float(d.get("minor_event_pity_counter") or 0.0),
            "player_scandal_cooldown_until_day": int(d.get("player_scandal_cooldown_until_day") or 0),
            "recent_witness_catches": catches if isinstance(catches, list) else [],
            "npc_gossip_shared_today": gossip if isinstance(gossip, dict) else {},
        }


_SAFE_WORLD_PITY_SET_CLAUSES: dict[str, str] = {
    "event_pity_counter": "event_pity_counter = ?",
    "rumor_pity_counter": "rumor_pity_counter = ?",
    "minor_event_pity_counter": "minor_event_pity_counter = ?",
    "player_scandal_cooldown_until_day": "player_scandal_cooldown_until_day = ?",
    "recent_witness_catches_json": "recent_witness_catches_json = ?",
    "npc_gossip_shared_today_json": "npc_gossip_shared_today_json = ?",
}


def update_session_world_pity_state(session_id: int, **updates: Any) -> dict[str, Any]:
    """Updates procedural event pity counters and scandal tracker columns on the sessions row."""
    col_updates: dict[str, Any] = {}
    for k, v in updates.items():
        if k in ("recent_witness_catches", "recent_witness_catches_json"):
            col_updates["recent_witness_catches_json"] = json.dumps(v) if not isinstance(v, str) else v
        elif k in ("npc_gossip_shared_today", "npc_gossip_shared_today_json"):
            col_updates["npc_gossip_shared_today_json"] = json.dumps(v) if not isinstance(v, str) else v
        elif k in _SAFE_WORLD_PITY_SET_CLAUSES:
            col_updates[k] = v

    if not col_updates:
        return get_session_world_pity_state(session_id)

    set_clauses = [_SAFE_WORLD_PITY_SET_CLAUSES[col] for col in col_updates if col in _SAFE_WORLD_PITY_SET_CLAUSES]
    values = [col_updates[col] for col in col_updates if col in _SAFE_WORLD_PITY_SET_CLAUSES] + [time.time(), session_id]

    with UnitOfWork() as conn:
        conn.execute(
            f"UPDATE sessions SET {', '.join(set_clauses)}, updated_at = ? WHERE id = ?",  # nosec B608
            values,
        )
    return get_session_world_pity_state(session_id)


def rollback_world_events_after_turn(
    session_id: int,
    turn_number: int,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, int]:
    """
    Executes 4-case rollback of world_events when rolling back to turn_number:
    1. Events/Rumors with turn_created > T are deleted alongside their RMR-/CLR- quests & waypoints.
    2. Rumors with turn_created <= T and claimed_turn > T delete linked RMR-/CLR- quests & waypoints,
       clear claimed_turn & linked_quest_id, and restore original_expires_day/minute.
    3. Events/Rumors with turn_created <= T and resolved_turn > T revert status to prior_status_before_resolve
       and restore original_expires_day/minute.
    4. Rumors with turn_created <= T and discovered_turn > T revert to is_discovered = 0.
    """
    def _execute(c: sqlite3.Connection) -> dict[str, int]:
        t = int(turn_number)

        # Case 1: Purge quests/waypoints for events created after turn T
        c.execute(
            """DELETE FROM quest_waypoints WHERE session_id = ? AND quest_id IN (
                SELECT linked_quest_id FROM world_events
                WHERE session_id = ? AND turn_created > ? AND linked_quest_id != ''
            )""",
            (session_id, session_id, t),
        )
        c.execute(
            """DELETE FROM quests WHERE session_id = ? AND quest_id IN (
                SELECT linked_quest_id FROM world_events
                WHERE session_id = ? AND turn_created > ? AND linked_quest_id != ''
            )""",
            (session_id, session_id, t),
        )
        cur_del = c.execute(
            "DELETE FROM world_events WHERE session_id = ? AND turn_created > ?",
            (session_id, t),
        )
        deleted_created_cnt = cur_del.rowcount

        # Case 2: Claimed after turn T (turn_created <= T)
        c.execute(
            """DELETE FROM quest_waypoints WHERE session_id = ? AND quest_id IN (
                SELECT COALESCE(NULLIF(linked_quest_id, ''), json_extract(COALESCE(NULLIF(metadata_json, ''), '{}'), '$._cold_linked_quest_id'))
                FROM world_events
                WHERE session_id = ? AND turn_created <= ? AND claimed_turn > ?
                  AND COALESCE(NULLIF(linked_quest_id, ''), json_extract(COALESCE(NULLIF(metadata_json, ''), '{}'), '$._cold_linked_quest_id'), '') != ''
            )""",
            (session_id, session_id, t, t),
        )
        c.execute(
            """DELETE FROM quests WHERE session_id = ? AND quest_id IN (
                SELECT COALESCE(NULLIF(linked_quest_id, ''), json_extract(COALESCE(NULLIF(metadata_json, ''), '{}'), '$._cold_linked_quest_id'))
                FROM world_events
                WHERE session_id = ? AND turn_created <= ? AND claimed_turn > ?
                  AND COALESCE(NULLIF(linked_quest_id, ''), json_extract(COALESCE(NULLIF(metadata_json, ''), '{}'), '$._cold_linked_quest_id'), '') != ''
            )""",
            (session_id, session_id, t, t),
        )
        cur_unclaim = c.execute(
            """UPDATE world_events
               SET claimed_turn = NULL,
                   linked_quest_id = '',
                   resolved_turn = CASE WHEN resolved_turn > ? THEN NULL ELSE resolved_turn END,
                   metadata_json = json_remove(COALESCE(NULLIF(metadata_json, ''), '{}'), '$._cold_linked_quest_id'),
                   status = CASE WHEN status IN ('investigating', 'cold') THEN 'active' ELSE status END,
                   expires_day = COALESCE(original_expires_day, expires_day),
                   expires_minute = COALESCE(original_expires_minute, expires_minute)
               WHERE session_id = ? AND turn_created <= ? AND claimed_turn > ?""",
            (t, session_id, t, t),
        )
        unclaimed_cnt = cur_unclaim.rowcount

        # Case 3: Resolved or went cold after turn T (turn_created <= T)
        c.execute(
            """UPDATE quests
               SET status = 'Active',
                   updated_at = ?
               WHERE session_id = ?
                 AND status IN ('Completed', 'Expired', 'Failed')
                 AND quest_id IN (
                     SELECT COALESCE(NULLIF(linked_quest_id, ''), json_extract(COALESCE(NULLIF(metadata_json, ''), '{}'), '$._cold_linked_quest_id'))
                     FROM world_events
                     WHERE session_id = ? AND turn_created <= ? AND resolved_turn > ?
                       AND claimed_turn IS NOT NULL AND claimed_turn <= ?
                       AND COALESCE(NULLIF(linked_quest_id, ''), json_extract(COALESCE(NULLIF(metadata_json, ''), '{}'), '$._cold_linked_quest_id'), '') != ''
                 )""",
            (time.time(), session_id, session_id, t, t, t),
        )
        cur_unresolve = c.execute(
            """UPDATE world_events
               SET status = CASE WHEN prior_status_before_resolve != '' THEN prior_status_before_resolve ELSE 'active' END,
                   linked_quest_id = COALESCE(NULLIF(linked_quest_id, ''), COALESCE(json_extract(COALESCE(NULLIF(metadata_json, ''), '{}'), '$._cold_linked_quest_id'), '')),
                   metadata_json = json_remove(COALESCE(NULLIF(metadata_json, ''), '{}'), '$._cold_linked_quest_id'),
                   resolved_turn = NULL,
                   expires_day = CASE WHEN linked_quest_id != '' OR COALESCE(json_extract(COALESCE(NULLIF(metadata_json, ''), '{}'), '$._cold_linked_quest_id'), '') != '' THEN expires_day ELSE COALESCE(original_expires_day, expires_day) END,
                   expires_minute = CASE WHEN linked_quest_id != '' OR COALESCE(json_extract(COALESCE(NULLIF(metadata_json, ''), '{}'), '$._cold_linked_quest_id'), '') != '' THEN expires_minute ELSE COALESCE(original_expires_minute, expires_minute) END
               WHERE session_id = ? AND turn_created <= ? AND resolved_turn > ?""",
            (session_id, t, t),
        )
        unresolved_cnt = cur_unresolve.rowcount

        # Case 4: Discovered after turn T (turn_created <= T)
        cur_undiscover = c.execute(
            """UPDATE world_events
               SET is_discovered = 0,
                   discovered_turn = NULL,
                   discovery_source = ''
               WHERE session_id = ? AND turn_created <= ? AND discovered_turn > ?
                 AND entity_type NOT IN ('macro_event', 'minor_event')""",
            (session_id, t, t),
        )
        undiscovered_cnt = cur_undiscover.rowcount

        return {
            "deleted_created_after_turn": deleted_created_cnt,
            "unclaimed_after_turn": unclaimed_cnt,
            "unresolved_after_turn": unresolved_cnt,
            "undiscovered_after_turn": undiscovered_cnt,
            "total_rolled_back": deleted_created_cnt + unclaimed_cnt + unresolved_cnt + undiscovered_cnt,
        }

    if conn is not None:
        return _execute(conn)
    with UnitOfWork() as c:
        return _execute(c)


def get_world_event_candidate_context(session_id: int) -> dict[str, list[dict[str, Any]]]:
    """Fetches factions, facility/room world_nodes, and contacts in one read query block for world event slot gathering."""
    with get_conn() as conn:
        fac_rows = conn.execute(
            "SELECT faction_id, name FROM factions WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        node_rows = conn.execute(
            "SELECT node_id, name, node_type FROM world_nodes WHERE session_id = ? LIMIT 40",
            (session_id,),
        ).fetchall()
        c_rows = conn.execute(
            "SELECT * FROM contacts WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        return {
            "factions": [dict(r) for r in fac_rows],
            "facilities": [
                dict(r)
                for r in node_rows
                if str(r["node_type"] or "").upper() in ("FACILITY", "ROOM")
            ],
            "contacts": [dict(r) for r in c_rows],
        }


def find_contacts_by_identity_candidates(
    session_id: int,
    candidates: set[str],
) -> tuple[set[int], str]:
    """Resolves matching contact row IDs and canonical display name against normalized lowercase name/npc_id candidates."""
    if not candidates:
        return set(), ""
    matched_ids: set[int] = set()
    first_name = ""
    with get_conn() as conn:
        c_rows = conn.execute(
            "SELECT id, name, npc_id FROM contacts WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        for cr in c_rows:
            c_name = str(cr["name"] or "").strip()
            c_npc_id = str(cr["npc_id"] or "").strip()
            if c_name.lower() in candidates or c_npc_id.lower() in candidates:
                matched_ids.add(int(cr["id"]))
                if not first_name and c_name:
                    first_name = c_name
    return matched_ids, first_name


def apply_contact_loyalty_bonus(contact_ids: set[int] | list[int], bonus: int) -> int:
    """Atomically grants a capped relationship affinity bonus to matched contact rows."""
    if not contact_ids or not bonus:
        return 0
    now = time.time()
    updated = 0
    with UnitOfWork() as conn:
        for cid in contact_ids:
            cur = conn.execute(
                "UPDATE contacts SET relationship_score = MIN(100, COALESCE(relationship_score, 0) + ?), updated_at = ? WHERE id = ?",
                (int(bonus), now, int(cid)),
            )
            updated += cur.rowcount
    return updated


def create_witness_scandal_event(
    session_id: int,
    quest_id: str,
    event_key: str,
    title: str,
    description: str,
    witness: str,
    zone_txt: str,
    deadline_day: int | None = None,
    deadline_minute: int | None = None,
    turn_number: int = 1,
    scandal_cooldown_day: int = 0,
    expires_day: int | None = None,
    expires_minute: int | None = None,
) -> dict[str, Any]:
    """Atomically inserts the Damage Control quest, stage-0 waypoint, scandal rumor, and pity cooldown in a single UnitOfWork."""
    eff_day = int(expires_day if expires_day is not None else (deadline_day if deadline_day is not None else 1))
    eff_min = int(expires_minute if expires_minute is not None else (deadline_minute if deadline_minute is not None else 480))
    now = time.time()
    with UnitOfWork() as conn:
        conn.execute(
            """INSERT INTO quests (
                session_id, quest_id, quest_type, title, objective, status,
                reward_xp, reward_gold, quest_notes, client_npc, client_location,
                deadline_day, deadline_minute, created_at, updated_at
            ) VALUES (?, ?, 'Damage Control', ?, ?, 'Active', 60, 0, 'rumor_investigation:1;player_scandal:1', ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                quest_id,
                f"Damage Control: {title}",
                f"Quiet {witness} or spin the narrative around {zone_txt} before the rumor hardens.",
                witness,
                zone_txt,
                eff_day,
                eff_min,
                now,
                now,
            ),
        )
        conn.execute(
            """INSERT INTO quest_waypoints (
                session_id, quest_id, stage_index, stage_label,
                target_location, target_node_id, completion_trigger, status,
                created_at, updated_at
            ) VALUES (?, ?, 0, 'Contain the Witness Gossip', ?, '', 'arrival', 'active', ?, ?)""",
            (session_id, quest_id, zone_txt, now, now),
        )
        ev = create_world_event(
            session_id=session_id,
            event_key=event_key,
            entity_type="rumor",
            event_subtype="scandal",
            title=title,
            description=description,
            sfw_fallback_description=description,
            location_name=zone_txt,
            is_discovered=1,
            discovery_source="witness_catch",
            discovered_turn=int(turn_number),
            claimed_turn=int(turn_number),
            linked_quest_id=quest_id,
            turn_created=int(turn_number),
            expires_day=eff_day,
            expires_minute=eff_min,
            is_nsfw=1,
        )
        update_session_world_pity_state(
            session_id,
            recent_witness_catches=[],
            player_scandal_cooldown_until_day=int(scandal_cooldown_day),
        )
        return ev
