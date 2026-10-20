from __future__ import annotations
import json
import logging
import sqlite3
import time
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Valid act types and directions
PHYSICAL_ACT_TYPES = {"intercourse", "oral", "manual", "anal", "kiss"}
MILESTONE_ACT_TYPES = {"confession", "date", "media", "first_kiss"}
ALL_VALID_ACT_TYPES = PHYSICAL_ACT_TYPES | MILESTONE_ACT_TYPES

VALID_DIRECTIONS = {"give", "receive", "mutual"}


def normalize_gender(raw_gender: str) -> str:
    """Normalizes gender string to 'female', 'male', or 'unknown'."""
    raw = str(raw_gender or "").strip().lower()
    if any(kw in raw for kw in ("female", "woman", "girl", "lady", "she", "her")):
        return "female"
    if any(kw in raw for kw in ("male", "man", "boy", "lord", "he", "him", "his")):
        return "male"
    return "unknown"


def enforce_biological_invariants(
    gender: str,
    act_type: str,
    direction: str,
    partner_gender: str = ""
) -> str:
    """
    Enforces biological invariants on intimate act directions:
    1. Female characters can ONLY receive anal intimacy. Any 'give' or 'mutual' direction is coerced to 'receive'.
    2. Male characters:
       - If partner is female, male can ONLY give anal intimacy.
       - If partner is male, male can give, receive, or engage mutually.
    Returns sanitized direction string ('give', 'receive', or 'mutual').
    """
    act_norm = str(act_type or "").strip().lower()
    dir_norm = str(direction or "mutual").strip().lower()
    if dir_norm not in VALID_DIRECTIONS:
        dir_norm = "mutual"

    if act_norm != "anal":
        return dir_norm

    char_g = normalize_gender(gender)
    part_g = normalize_gender(partner_gender)

    if char_g == "female":
        if dir_norm in ("give", "mutual"):
            logger.warning(
                "Biological invariant violation: Female character cannot give anal intimacy (direction=%s). Coercing to 'receive'.",
                dir_norm
            )
            return "receive"
        return "receive"

    if char_g == "male":
        if part_g == "female" and dir_norm in ("receive", "mutual"):
            logger.warning(
                "Biological invariant violation: Male character cannot receive anal intimacy from female partner (direction=%s). Coercing to 'give'.",
                dir_norm
            )
            return "give"

    return dir_norm


def invert_direction(direction: str) -> str:
    """Inverts an act direction for reciprocal event recording."""
    d = str(direction or "mutual").strip().lower()
    if d == "give":
        return "receive"
    if d == "receive":
        return "give"
    return "mutual"


def compute_intimate_tracks_from_ledger(events: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Deterministically computes the 4-track discrete states:
    - intercourse: 'virgin' | 'non_virgin'
    - oral: 'inexperienced' | 'has_done_oral' | 'has_received_oral' | 'has_done_and_received_oral'
    - manual: 'inexperienced' | 'has_done_manual' | 'has_received_manual' | 'has_done_and_received_manual'
    - anal: 'inexperienced' | 'has_done_anal' | 'has_received_anal' | 'has_done_and_received_anal'
    """
    physical_events = [e for e in (events or []) if bool(e.get("is_physical", True))]

    # 1. Intercourse Track
    has_sex = any(e.get("act_type") == "intercourse" for e in physical_events)
    intercourse_state = "non_virgin" if has_sex else "virgin"

    # Helper for 3-way directional tracks
    def _compute_directional_track(act: str) -> str:
        gives = any(e.get("act_type") == act and e.get("direction") in ("give", "mutual") for e in physical_events)
        recs = any(e.get("act_type") == act and e.get("direction") in ("receive", "mutual") for e in physical_events)
        if gives and recs:
            return f"has_done_and_received_{act}"
        if gives:
            return f"has_done_{act}"
        if recs:
            return f"has_received_{act}"
        return "inexperienced"

    return {
        "intercourse": intercourse_state,
        "oral": _compute_directional_track("oral"),
        "manual": _compute_directional_track("manual"),
        "anal": _compute_directional_track("anal")
    }


def record_intimate_event(
    session_id: int,
    character_id: str,
    partner_name: str,
    act_type: str,
    direction: str,
    partner_id: Optional[str] = None,
    partner_role: str = "",
    turn_number: int = 0,
    event_origin: str = "past_history",
    is_physical: bool = True,
    count: int = 1,
    climax_count: int = 0,
    is_secret_affair: bool = False,
    narrative_summary: str = "",
    character_gender: str = "",
    partner_gender: str = "",
    is_reciprocal: bool = False,
    character_name: str = "",
    conn: Optional[sqlite3.Connection] = None
) -> int:
    """
    Records an intimate act event into the 'intimate_events' table.
    Enforces biological invariants on direction.
    If partner_id is an active NPC and is_reciprocal is False, automatically records
    the symmetric reciprocal row for partner_id with inverted direction.
    """
    from db.core import get_conn

    sanitized_direction = enforce_biological_invariants(
        gender=character_gender,
        act_type=act_type,
        direction=direction,
        partner_gender=partner_gender
    )

    now = time.time()

    # Dynamic secret affair detection with interpersonal social graph
    effective_secret_affair = is_secret_affair
    if session_id and event_origin == "gameplay" and is_physical:
        try:
            import mechanics.social.relationship_graph as rg
            # Resolve a_key
            p_a = rg.get_person_by_contact_id(session_id, str(character_id))
            a_key = p_a["person_key"] if p_a else rg.canonical_person_key(str(character_id))

            if str(partner_id or "").lower() in ("player", "0", ""):
                # Find character_id for player in this session
                from db.core import get_conn
                char_id_val = partner_id or "0"
                try:
                    with get_conn() as conn_check:
                        c_row = conn_check.execute("SELECT character_id FROM contacts WHERE session_id = ? AND character_id IS NOT NULL LIMIT 1", (session_id,)).fetchone()
                        if c_row and c_row["character_id"]:
                            char_id_val = c_row["character_id"]
                except Exception:
                    pass
                b_key = rg.player_person_key(char_id_val)
            else:
                p_b = rg.get_person_by_contact_id(session_id, str(partner_id))
                b_key = p_b["person_key"] if p_b else rg.canonical_person_key(str(partner_id or partner_name))

            part_a = rg.get_current_partner(session_id, a_key)
            part_b = rg.get_current_partner(session_id, b_key)
            if (part_a and part_a.get("person_key") != b_key) or (part_b and part_b.get("person_key") != a_key):
                effective_secret_affair = True
                rg.form_tie(session_id, a_key, b_key, rg.TIETYPE_AFFAIR, visibility="secret", turn=turn_number, origin="gameplay")
        except Exception:
            pass

    def _execute_insert(c: sqlite3.Connection) -> int:
        cur = c.execute(
            """INSERT INTO intimate_events (
                session_id, character_id, partner_id, partner_name, partner_role,
                turn_number, event_origin, act_type, direction, is_physical,
                count, climax_count, is_secret_affair, narrative_summary, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                str(character_id),
                str(partner_id) if partner_id is not None else None,
                partner_name,
                partner_role,
                turn_number,
                event_origin,
                act_type,
                sanitized_direction,
                1 if is_physical else 0,
                max(1, count),
                max(0, climax_count),
                1 if effective_secret_affair else 0,
                narrative_summary or "",
                now
            )
        )
        primary_id = cur.lastrowid

        # Write symmetric reciprocal row for partner if partner_id is a tracked NPC
        if partner_id and str(partner_id).lower() not in ("player", "0", "") and not is_reciprocal:
            try:
                # Invert direction for reciprocal partner
                recip_dir = invert_direction(sanitized_direction)
                recip_sanitized = enforce_biological_invariants(
                    gender=partner_gender,
                    act_type=act_type,
                    direction=recip_dir,
                    partner_gender=character_gender
                )

                # Resolve human-readable name for reciprocal row's partner_name
                resolved_char_name = character_name.strip()
                if not resolved_char_name:
                    if str(character_id).isdigit():
                        r_row = c.execute("SELECT name FROM contacts WHERE id = ?", (int(character_id),)).fetchone()
                        if r_row:
                            resolved_char_name = r_row["name"] if isinstance(r_row, dict) or hasattr(r_row, "keys") else r_row[0]
                    else:
                        r_row = c.execute("SELECT name FROM contacts WHERE session_id = ? AND npc_id = ?", (session_id, str(character_id))).fetchone()
                        if r_row:
                            resolved_char_name = r_row["name"] if isinstance(r_row, dict) or hasattr(r_row, "keys") else r_row[0]
                if not resolved_char_name:
                    resolved_char_name = str(character_id).replace("_", " ").title()

                c.execute(
                    """INSERT INTO intimate_events (
                        session_id, character_id, partner_id, partner_name, partner_role,
                        turn_number, event_origin, act_type, direction, is_physical,
                        count, climax_count, is_secret_affair, narrative_summary, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session_id,
                        str(partner_id),
                        str(character_id),
                        resolved_char_name,  # human-readable partner_name for reciprocal row
                        partner_role,
                        turn_number,
                        event_origin,
                        act_type,
                        recip_sanitized,
                        1 if is_physical else 0,
                        max(1, count),
                        0,  # partner's own climax count can be updated separately if recorded
                        1 if is_secret_affair else 0,
                        narrative_summary or "",
                        now
                    )
                )
            except Exception as e:
                logger.warning("Failed to record reciprocal intimate event: %s", e)

        return primary_id

    if conn is not None:
        return _execute_insert(conn)
    else:
        with get_conn() as c:
            return _execute_insert(c)


def get_intimate_events(
    session_id: int,
    character_id: str,
    physical_only: bool = False,
    origin: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None
) -> List[Dict[str, Any]]:
    """Retrieves all intimate events for a character in a session."""
    from db.core import get_conn

    def _query(c: sqlite3.Connection) -> List[Dict[str, Any]]:
        char_ids = {str(character_id)}
        try:
            c_row = c.execute(
                "SELECT id, npc_id FROM contacts WHERE session_id = ? AND (id = ? OR npc_id = ? OR lower(name) = ?)",
                (session_id, str(character_id), str(character_id), str(character_id).lower())
            ).fetchone()
            if c_row:
                if c_row["id"]:
                    char_ids.add(str(c_row["id"]))
                if c_row["npc_id"]:
                    char_ids.add(str(c_row["npc_id"]))
        except Exception:
            pass

        placeholders = ",".join("?" for _ in char_ids)
        sql = f"SELECT * FROM intimate_events WHERE session_id = ? AND character_id IN ({placeholders})"
        params: List[Any] = [session_id, *char_ids]
        if physical_only:
            sql += " AND is_physical = 1"
        if origin:
            sql += " AND event_origin = ?"
            params.append(origin)
        sql += " ORDER BY turn_number ASC, id ASC"
        rows = c.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    if conn is not None:
        return _query(conn)
    else:
        with get_conn() as c:
            return _query(c)


def recompute_and_cache_character_intimacy(
    session_id: int,
    character_id: str,
    conn: Optional[sqlite3.Connection] = None
) -> Dict[str, str]:
    """
    Queries all intimate events for a character, derives their 4-track states,
    and caches them into contacts.intimate_profile_json['tracks'].
    Returns the updated tracks dict.
    """
    from db.core import get_conn

    def _recompute(c: sqlite3.Connection) -> Dict[str, str]:
        events = get_intimate_events(session_id, character_id, physical_only=True, conn=c)
        tracks = compute_intimate_tracks_from_ledger(events)

        # Fetch current intimate_profile_json
        row = c.execute(
            "SELECT id, intimate_profile_json FROM contacts WHERE session_id = ? AND (id = ? OR npc_id = ? OR lower(name) = ?)",
            (session_id, str(character_id), str(character_id), str(character_id).lower())
        ).fetchone()

        if row:
            try:
                prof = json.loads(row["intimate_profile_json"] or "{}")
            except Exception:
                prof = {}
            prof["tracks"] = tracks
            c.execute(
                "UPDATE contacts SET intimate_profile_json = ? WHERE id = ?",
                (json.dumps(prof), row["id"])
            )
        return tracks

    if conn is not None:
        return _recompute(conn)
    else:
        with get_conn() as c:
            return _recompute(c)


def record_intimate_turn_encounter(
    session_id: int,
    character_id: str,
    partner_id: str = "player",
    partner_name: str = "Player",
    milestone_event: str = "",
    turn_number: int = 1,
    custom_summary: Optional[str] = None,
    climax_count: int = 0,
    character_gender: str = "",
    partner_gender: str = "",
    character_name: str = "",
    conn: Optional[sqlite3.Connection] = None
) -> Tuple[Optional[str], Dict[str, str]]:
    """
    Unified Service Helper for live gameplay turns:
    1. Maps milestone_event to act_type, direction, is_physical.
    2. Formats narrative memory string via format_milestone_memory().
    3. Records the event into intimate_events table.
    4. Unlocks disclosure flags in contacts.intimate_profile_json.
    5. Recomputes and caches 4-track states in contacts.intimate_profile_json.
    6. Returns (memory_string, updated_tracks).
    """
    from .formatting import format_milestone_memory

    ev_low = str(milestone_event or "").strip().lower()
    if not ev_low:
        return None, {}

    # Map milestone event to act_type and direction
    act_type = "kiss"
    direction = "mutual"
    is_physical = True

    if ev_low == "intercourse":
        act_type = "intercourse"
        direction = "mutual"
    elif ev_low == "oral_give":
        act_type = "oral"
        direction = "give"
    elif ev_low == "oral_receive":
        act_type = "oral"
        direction = "receive"
    elif ev_low == "oral":
        act_type = "oral"
        direction = "mutual"
    elif ev_low == "manual_give":
        act_type = "manual"
        direction = "give"
    elif ev_low == "manual_receive":
        act_type = "manual"
        direction = "receive"
    elif ev_low == "manual":
        act_type = "manual"
        direction = "mutual"
    elif ev_low == "anal_give":
        act_type = "anal"
        direction = "give"
    elif ev_low in ("anal_receive", "anal"):
        act_type = "anal"
        direction = "receive"
    elif ev_low in ("first_kiss", "kiss"):
        act_type = "kiss"
        direction = "mutual"
    elif ev_low == "confession":
        act_type = "confession"
        direction = "mutual"
        is_physical = False
    elif ev_low == "date":
        act_type = "date"
        direction = "mutual"
        is_physical = False
    elif "dm_" in ev_low:
        act_type = "media"
        direction = "mutual"
        is_physical = False

    # Format narrative memory string
    new_mem = format_milestone_memory(ev_low, partner_name, custom_summary)

    # Insert event into intimate_events
    record_intimate_event(
        session_id=session_id,
        character_id=character_id,
        partner_name=partner_name,
        act_type=act_type,
        direction=direction,
        partner_id=partner_id,
        partner_role="Player" if partner_id == "player" else "",
        turn_number=max(1, turn_number),
        event_origin="gameplay",
        is_physical=is_physical,
        count=1,
        climax_count=climax_count,
        narrative_summary=new_mem,
        character_gender=character_gender,
        partner_gender=partner_gender,
        character_name=character_name,
        conn=conn
    )

    from db.core import get_conn

    def _update_profile_and_tracks(c: sqlite3.Connection) -> Dict[str, str]:
        events = get_intimate_events(session_id, character_id, physical_only=True, conn=c)
        tracks = compute_intimate_tracks_from_ledger(events)

        row = c.execute(
            "SELECT id, intimate_profile_json FROM contacts WHERE session_id = ? AND (id = ? OR npc_id = ? OR lower(name) = ?)",
            (session_id, str(character_id), str(character_id), str(character_id).lower())
        ).fetchone()

        if row:
            try:
                prof = json.loads(row["intimate_profile_json"] or "{}")
            except Exception:
                prof = {}

            prof["tracks"] = tracks

            disc = prof.get("disclosure_flags", {})
            disc["intimate_revealed"] = True
            if act_type == "intercourse":
                disc["intercourse_revealed"] = True
                prof["had_first_time_with_player"] = True
            elif act_type == "oral":
                disc["oral_revealed"] = True
            elif act_type == "manual":
                disc["manual_revealed"] = True
            elif act_type == "anal":
                disc["anal_revealed"] = True
            elif act_type == "confession":
                disc["demeanor_revealed"] = True

            prof["disclosure_flags"] = disc
            for k, v in disc.items():
                prof[k] = v

            c.execute(
                "UPDATE contacts SET intimate_profile_json = ? WHERE id = ?",
                (json.dumps(prof), row["id"])
            )
        return tracks

    if conn is not None:
        updated_tracks = _update_profile_and_tracks(conn)
    else:
        with get_conn() as c:
            updated_tracks = _update_profile_and_tracks(c)

    return new_mem, updated_tracks


def delete_intimate_events_after_turn(
    session_id: int,
    turn_number: int,
    conn: Optional[sqlite3.Connection] = None
) -> int:
    """
    Rollback helper: Prunes events with turn_number > turn_number
    and refreshes cached tracks for all affected characters.
    """
    from db.core import get_conn

    def _prune(c: sqlite3.Connection) -> int:
        # 1. Identify affected characters
        rows = c.execute(
            "SELECT DISTINCT character_id FROM intimate_events WHERE session_id = ? AND turn_number > ?",
            (session_id, turn_number)
        ).fetchall()
        affected_chars = [r["character_id"] if isinstance(r, sqlite3.Row) else r[0] for r in rows]

        # 2. Delete future events
        cur = c.execute(
            "DELETE FROM intimate_events WHERE session_id = ? AND turn_number > ?",
            (session_id, turn_number)
        )
        deleted_count = cur.rowcount

        # 3. Refresh cached tracks for all affected characters
        for char_id in affected_chars:
            recompute_and_cache_character_intimacy(session_id, char_id, conn=c)

        return deleted_count

    if conn is not None:
        return _prune(conn)
    else:
        with get_conn() as c:
            return _prune(c)


def parse_past_history_entry_to_events(entry_str: str, char_gender: str = "") -> List[Dict[str, Any]]:
    """
    Parses a synthesized 'Past History: ...' string into structured event dicts.
    Useful for lossless backward compatibility during database migration.
    """
    import re
    if not entry_str or not isinstance(entry_str, str) or not entry_str.strip().startswith("Past History:"):
        return []

    text = entry_str.strip()
    low = text.lower()

    # 1. Partner and Role
    partner_name = "Past Partner"
    partner_role = "Former Classmate"
    m_partner = re.search(r"['\"]([^'\"]+)['\"]\s*\(([^)]+)\)", text)
    if m_partner:
        partner_name = m_partner.group(1).strip()
        partner_role = m_partner.group(2).strip()

    # 2. General Count
    m_count = re.search(r"(\d+)\s+times?", text)
    default_count = int(m_count.group(1)) if m_count else 1
    is_affair = "secret affair" in low or "behind partner" in low

    events = []

    # 3. Intercourse
    if any(k in low for k in ("intercourse", "lost virginity", "slept together", "first time")):
        ic_count = default_count
        m_ic = re.search(r"intercourse\s*\((\d+)\s*times?\)", low)
        if m_ic:
            ic_count = int(m_ic.group(1))
        events.append({
            "act_type": "intercourse",
            "direction": "mutual",
            "count": ic_count,
            "partner_name": partner_name,
            "partner_role": partner_role,
            "is_secret_affair": is_affair,
            "is_physical": True,
            "turn_number": 0,
            "event_origin": "past_history"
        })

    # 4. Oral
    if any(k in low for k in ("oral", "fellatio", "cunnilingus", "blowjob")):
        o_count = default_count
        m_o = re.search(r"oral\s*\((\d+)\s*times?\)", low)
        if m_o:
            o_count = int(m_o.group(1))
        o_dir = "give"
        if "performed & received" in low or "mutual oral" in low:
            o_dir = "mutual"
        elif "received oral" in low or "receiving oral" in low:
            o_dir = "receive"
        elif "performed oral" in low or "performing oral" in low or "gave oral" in low:
            o_dir = "give"
        events.append({
            "act_type": "oral",
            "direction": o_dir,
            "count": o_count,
            "partner_name": partner_name,
            "partner_role": partner_role,
            "is_secret_affair": is_affair,
            "is_physical": True,
            "turn_number": 0,
            "event_origin": "past_history"
        })

    # 5. Manual
    if any(k in low for k in ("manual", "stimulated", "foreplay", "handjob", "fingered")):
        m_count = default_count
        m_m = re.search(r"manual[^\(]*\((\d+)\s*times?\)", low)
        if m_m:
            m_count = int(m_m.group(1))
        m_dir = "give"
        if "mutual manual" in low or "mutual foreplay" in low:
            m_dir = "mutual"
        elif "received manual" in low or "receiving manual" in low:
            m_dir = "receive"
        elif "manually stimulated" in low or "stimulating" in low:
            m_dir = "give"
        events.append({
            "act_type": "manual",
            "direction": m_dir,
            "count": m_count,
            "partner_name": partner_name,
            "partner_role": partner_role,
            "is_secret_affair": is_affair,
            "is_physical": True,
            "turn_number": 0,
            "event_origin": "past_history"
        })

    # 6. Anal
    if any(k in low for k in ("anal", "backdoor")):
        a_count = default_count
        m_a = re.search(r"anal[^\(]*\((\d+)\s*times?\)", low)
        if m_a:
            a_count = int(m_a.group(1))
        a_dir = "receive"
        if "performed anal" in low or "performing anal" in low:
            a_dir = "give"
        elif "engaged in anal intimacy" in low:
            a_dir = "mutual"
        a_dir = enforce_biological_invariants(char_gender, "anal", a_dir)
        events.append({
            "act_type": "anal",
            "direction": a_dir,
            "count": a_count,
            "partner_name": partner_name,
            "partner_role": partner_role,
            "is_secret_affair": is_affair,
            "is_physical": True,
            "turn_number": 0,
            "event_origin": "past_history"
        })

    return events
