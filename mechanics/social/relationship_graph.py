"""
mechanics/social/relationship_graph.py

Normalized Interpersonal Social Graph & Relationship Network Service Layer.
Enforces invariants (incest guard, mutual exclusivity of friendship and rivalry,
romantic exclusivity and secret affairs, canonical pair ordering), maintains
social_persons and social_ties tables, and materializes backward-compatible
relations_json caches for contacts.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Set, Tuple

import db

logger = logging.getLogger(__name__)

# --- Tie Types & Taxonomies ---
TIETYPE_ACQUAINTANCE = "acquaintance"
TIETYPE_FRIEND = "friend"
TIETYPE_BEST_FRIEND = "best_friend"
TIETYPE_RIVAL = "rival"
TIETYPE_ENEMY = "enemy"
TIETYPE_CRUSH = "crush"
TIETYPE_ADMIRES = "admires"
TIETYPE_GRUDGE = "grudge"
TIETYPE_DATING = "dating"
TIETYPE_ENGAGED = "engaged"
TIETYPE_MARRIED = "married"
TIETYPE_AFFAIR = "affair"

PLATONIC_TYPES: Set[str] = {
    TIETYPE_ACQUAINTANCE,
    TIETYPE_FRIEND,
    TIETYPE_BEST_FRIEND,
}

ANTAGONISTIC_TYPES: Set[str] = {
    TIETYPE_RIVAL,
    TIETYPE_ENEMY,
}

DIRECTED_TYPES: Set[str] = {
    TIETYPE_CRUSH,
    TIETYPE_ADMIRES,
    TIETYPE_GRUDGE,
}

EXCLUSIVE_ROMANTIC_TYPES: Set[str] = {
    TIETYPE_DATING,
    TIETYPE_ENGAGED,
    TIETYPE_MARRIED,
}

ROMANTIC_TYPES: Set[str] = EXCLUSIVE_ROMANTIC_TYPES | {TIETYPE_AFFAIR}


@contextmanager
def _get_connection(conn: Optional[sqlite3.Connection] = None):
    """Context manager yielding the provided connection or acquiring a fresh one from db."""
    if conn is not None:
        yield conn
    else:
        with db.get_conn() as c:
            yield c


# --- Person Registry & Key Helpers ---

def player_person_key(character_id: Any) -> str:
    """Returns canonical person key for a player character."""
    return f"player:{character_id}"


def is_player_person_key(key: Any) -> bool:
    """Checks if a person key refers to the player."""
    clean = str(key or "").strip().lower()
    return clean in ("player", "you") or clean.startswith("player:")


def canonical_person_key(name: str, disambiguator: str = "") -> str:
    """Produces a clean canonical text key from a name."""
    clean = re.sub(r"[^a-z0-9]+", "_", (name or "").lower().strip()).strip("_")
    if disambiguator:
        d_clean = re.sub(r"[^a-z0-9]+", "_", str(disambiguator).lower().strip()).strip("_")
        if d_clean:
            clean = f"{clean}_{d_clean}"
    return clean or "unknown_person"


def canonical_pair(a: str, b: str, is_directed: bool = False) -> Tuple[str, str]:
    """Returns canonical ordering for a pair of keys. Undirected ties enforce a < b."""
    if is_directed:
        return a, b
    return (a, b) if a < b else (b, a)


def get_or_create_person(
    session_id: int,
    name: str,
    *,
    person_key: Optional[str] = None,
    gender: str = "",
    role: str = "",
    origin: str = "procedural",
    contact_npc_id: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> str:
    """
    Registers a person node in social_persons if not already present,
    or enriches existing metadata. Returns the stable person_key.
    """
    now = time.time()
    p_key = person_key or canonical_person_key(name)
    display = (name or "").strip() or p_key

    with _get_connection(conn) as c:
        row = c.execute(
            "SELECT id, display_name, gender, role, contact_npc_id FROM social_persons WHERE session_id = ? AND person_key = ?",
            (session_id, p_key),
        ).fetchone()

        if row:
            updates = []
            params: list[Any] = []
            if contact_npc_id and not row["contact_npc_id"]:
                updates.append("contact_npc_id = ?")
                params.append(contact_npc_id)
            if gender and not row["gender"]:
                updates.append("gender = ?")
                params.append(gender)
            if role and not row["role"]:
                updates.append("role = ?")
                params.append(role)
            if updates:
                updates.append("updated_at = ?")
                params.append(now)
                params.extend([session_id, p_key])
                c.execute(
                    f"UPDATE social_persons SET {', '.join(updates)} WHERE session_id = ? AND person_key = ?",
                    params,
                )
            return p_key

        c.execute(
            """INSERT INTO social_persons
               (session_id, person_key, display_name, gender, role, origin, contact_npc_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, p_key, display, gender, role, origin, contact_npc_id, now, now),
        )
        return p_key


def link_person_to_contact(
    session_id: int,
    person_key: str,
    contact_npc_id: str,
    conn: Optional[sqlite3.Connection] = None,
) -> bool:
    """Links a social_persons row to a contact_npc_id upon hydration."""
    with _get_connection(conn) as c:
        cur = c.execute(
            "UPDATE social_persons SET contact_npc_id = ?, updated_at = ? WHERE session_id = ? AND person_key = ?",
            (contact_npc_id, time.time(), session_id, person_key),
        )
        return cur.rowcount > 0


def get_person_by_key(
    session_id: int,
    person_key: str,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[dict]:
    """Retrieves person record dict by person_key."""
    with _get_connection(conn) as c:
        row = c.execute(
            "SELECT * FROM social_persons WHERE session_id = ? AND person_key = ?",
            (session_id, person_key),
        ).fetchone()
        return dict(row) if row else None


def get_person_by_contact_id(
    session_id: int,
    contact_npc_id: str,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[dict]:
    """Retrieves person record dict by contact_npc_id."""
    with _get_connection(conn) as c:
        row = c.execute(
            "SELECT * FROM social_persons WHERE session_id = ? AND contact_npc_id = ?",
            (session_id, contact_npc_id),
        ).fetchone()
        return dict(row) if row else None


# --- Invariants & Checks ---

def is_incestuous(
    session_id: int,
    a_key: str,
    b_key: str,
    conn: Optional[sqlite3.Connection] = None,
) -> bool:
    """
    Checks if person a and person b are related in the same household or family lineage.
    Romance between household family members is strictly guarded.
    """
    with _get_connection(conn) as c:
        pa = get_person_by_key(session_id, a_key, conn=c)
        pb = get_person_by_key(session_id, b_key, conn=c)

        # 1. Check contact household_id match
        a_cid = pa.get("contact_npc_id") if pa else None
        b_cid = pb.get("contact_npc_id") if pb else None

        a_hid = None
        b_hid = None
        if a_cid:
            row_a = c.execute("SELECT household_id FROM contacts WHERE session_id = ? AND npc_id = ?", (session_id, a_cid)).fetchone()
            if row_a and row_a["household_id"]:
                a_hid = row_a["household_id"]
        else:
            row_a = c.execute("SELECT household_id, npc_id FROM contacts WHERE session_id = ? AND (npc_id = ? OR lower(name) = ?)", (session_id, a_key, a_key.replace("_", " "))).fetchone()
            if row_a and row_a["household_id"]:
                a_hid = row_a["household_id"]
                link_person_to_contact(session_id, a_key, row_a["npc_id"], conn=c)

        if b_cid:
            row_b = c.execute("SELECT household_id FROM contacts WHERE session_id = ? AND npc_id = ?", (session_id, b_cid)).fetchone()
            if row_b and row_b["household_id"]:
                b_hid = row_b["household_id"]
        else:
            row_b = c.execute("SELECT household_id, npc_id FROM contacts WHERE session_id = ? AND (npc_id = ? OR lower(name) = ?)", (session_id, b_key, b_key.replace("_", " "))).fetchone()
            if row_b and row_b["household_id"]:
                b_hid = row_b["household_id"]
                link_person_to_contact(session_id, b_key, row_b["npc_id"], conn=c)

        if a_hid and b_hid and a_hid == b_hid:
            return True

        # 2. Check if either person appears in the other's household parent/sibling records
        for target_hid, check_person in ((a_hid, pb), (b_hid, pa)):
            if not target_hid or not check_person:
                continue
            hh_row = c.execute("SELECT * FROM households WHERE id = ?", (target_hid,)).fetchone()
            if not hh_row:
                continue
            name_lower = (check_person.get("display_name") or "").lower().strip()
            if not name_lower:
                continue

            try:
                father = json.loads(hh_row["father_json"] or "{}")
                if father.get("name", "").lower().strip() == name_lower:
                    return True
            except Exception:
                pass

            try:
                mother = json.loads(hh_row["mother_json"] or "{}")
                if mother.get("name", "").lower().strip() == name_lower:
                    return True
            except Exception:
                pass

            try:
                sibs = json.loads(hh_row["narrative_siblings_json"] or "[]")
                for s in sibs:
                    s_name = (s.get("name") if isinstance(s, dict) else str(s)).lower().strip()
                    if s_name == name_lower:
                        return True
            except Exception:
                pass

    return False


# --- Mutations ---

def form_tie(
    session_id: int,
    a: str,
    b: str,
    tie_type: str,
    *,
    closeness: int = 50,
    visibility: Optional[str] = None,
    turn: int = 0,
    origin: str = "gameplay",
    supersede: bool = False,
    affair: bool = False,
    metadata: Optional[dict] = None,
    materialize: bool = True,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    """
    Forms or updates a tie between person a and person b.
    Enforces all invariants:
    - No self-ties
    - Incest guard on romantic ties
    - Mutual exclusivity between friendship and rivalry (Decision 2)
    - Romantic exclusivity / secret affair conversion (Decision 1)
    - Canonical pair ordering
    - Write-through materialization to legacy relations_json
    """
    if a == b:
        raise ValueError(f"Cannot form tie between a person and themselves ({a})")

    is_directed = 1 if tie_type in DIRECTED_TYPES else 0
    a_canon, b_canon = canonical_pair(a, b, is_directed=bool(is_directed))
    now = time.time()
    closeness_clamped = max(0, min(100, int(closeness)))
    meta_json = json.dumps(metadata or {})

    with _get_connection(conn) as c:
        # Ensure both nodes exist in registry
        get_or_create_person(session_id, a_canon, conn=c)
        get_or_create_person(session_id, b_canon, conn=c)

        # 1. Incest guard
        if tie_type in ROMANTIC_TYPES:
            if is_incestuous(session_id, a_canon, b_canon, conn=c):
                raise ValueError(f"Incest guard blocked romantic tie between {a_canon} and {b_canon}")

        # 2. Decision 2: Antagonism & Friendship auto-transition
        if tie_type in PLATONIC_TYPES:
            # Forming friendship reconciles any active rivalry/enemy tie
            antag_ties = c.execute(
                """SELECT id, tie_type FROM social_ties
                   WHERE session_id = ? AND person_a_key = ? AND person_b_key = ?
                     AND tie_type IN ('rival', 'enemy') AND status = 'active'""",
                (session_id, a_canon, b_canon),
            ).fetchall()
            for at in antag_ties:
                c.execute(
                    """UPDATE social_ties
                       SET status = 'ended', ended_turn = ?, end_reason = 'reconciled', updated_at = ?
                       WHERE id = ?""",
                    (turn, now, at["id"]),
                )

        elif tie_type in ANTAGONISTIC_TYPES:
            # Forming rivalry breaks any active friendship/best_friend/acquaintance tie
            plat_ties = c.execute(
                """SELECT id, tie_type FROM social_ties
                   WHERE session_id = ? AND person_a_key = ? AND person_b_key = ?
                     AND tie_type IN ('acquaintance', 'friend', 'best_friend') AND status = 'active'""",
                (session_id, a_canon, b_canon),
            ).fetchall()
            for pt in plat_ties:
                c.execute(
                    """UPDATE social_ties
                       SET status = 'ended', ended_turn = ?, end_reason = 'falling_out', updated_at = ?
                       WHERE id = ?""",
                    (turn, now, pt["id"]),
                )

        # 3. Decision 1 & Romantic Exclusivity
        actual_tie_type = tie_type
        actual_visibility = visibility

        if tie_type in EXCLUSIVE_ROMANTIC_TYPES:
            # Check if either party has an active exclusive partner
            partner_a = get_current_partner(session_id, a_canon, conn=c)
            partner_b = get_current_partner(session_id, b_canon, conn=c)

            is_player_involved = is_player_person_key(a_canon) or is_player_person_key(b_canon)

            # Are either currently in an exclusive relationship with a 3rd party?
            conflict_a = partner_a and partner_a["person_key"] != b_canon
            conflict_b = partner_b and partner_b["person_key"] != a_canon

            if conflict_a or conflict_b:
                if supersede:
                    # Break old tie
                    if conflict_a:
                        reason = "left_for_player" if is_player_involved else "left_for_partner"
                        end_tie(session_id, a_canon, partner_a["person_key"], partner_a["tie_type"], turn=turn, reason=reason, materialize=False, conn=c)
                    if conflict_b:
                        reason = "left_for_player" if is_player_involved else "left_for_partner"
                        end_tie(session_id, b_canon, partner_b["person_key"], partner_b["tie_type"], turn=turn, reason=reason, materialize=False, conn=c)
                elif is_player_involved or affair:
                    # Decision 1: Allow multi-dating as Secret Affair
                    actual_tie_type = TIETYPE_AFFAIR
                    if not actual_visibility:
                        actual_visibility = "secret"
                else:
                    raise ValueError(
                        f"Cannot form exclusive romantic tie: person already in active relationship "
                        f"(a: {partner_a}, b: {partner_b})"
                    )

        elif tie_type == TIETYPE_AFFAIR:
            if not actual_visibility:
                actual_visibility = "secret"
            # Affair Invariant: If neither has a third-party partner, normalize to dating
            partner_a = get_current_partner(session_id, a_canon, conn=c)
            partner_b = get_current_partner(session_id, b_canon, conn=c)
            has_3rd_party = (partner_a and partner_a["person_key"] != b_canon) or \
                            (partner_b and partner_b["person_key"] != a_canon)
            if not has_3rd_party:
                actual_tie_type = TIETYPE_DATING
                actual_visibility = "public"

        if not actual_visibility:
            if actual_tie_type == TIETYPE_AFFAIR:
                actual_visibility = "secret"
            elif is_directed:
                actual_visibility = "private"
            else:
                actual_visibility = "public"

        # 4. Upsert active tie
        existing = c.execute(
            """SELECT id FROM social_ties
               WHERE session_id = ? AND person_a_key = ? AND person_b_key = ? AND tie_type = ? AND status = 'active'""",
            (session_id, a_canon, b_canon, actual_tie_type),
        ).fetchone()

        if existing:
            tie_id = existing["id"]
            c.execute(
                """UPDATE social_ties
                   SET closeness = ?, visibility = ?, origin = ?, metadata_json = ?, updated_at = ?
                   WHERE id = ?""",
                (closeness_clamped, actual_visibility, origin, meta_json, now, tie_id),
            )
        else:
            cur = c.execute(
                """INSERT INTO social_ties
                   (session_id, person_a_key, person_b_key, tie_type, is_directed, status,
                    closeness, visibility, origin, started_turn, metadata_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, a_canon, b_canon, actual_tie_type, is_directed, closeness_clamped,
                 actual_visibility, origin, turn, meta_json, now, now),
            )
            tie_id = cur.lastrowid

        # 5. Write-through materialization
        if materialize:
            _materialize_endpoints(session_id, a_canon, b_canon, conn=c)

        return tie_id


def end_tie(
    session_id: int,
    a: str,
    b: str,
    tie_type: Optional[str] = None,
    *,
    turn: int = 0,
    reason: str = "",
    materialize: bool = True,
    conn: Optional[sqlite3.Connection] = None,
) -> bool:
    """
    Ends an active tie between a and b, preserving it as an ended historical tie.
    """
    now = time.time()
    a_is_p = is_player_person_key(a)
    b_is_p = is_player_person_key(b)

    with _get_connection(conn) as c:
        is_directed = bool(tie_type and tie_type in DIRECTED_TYPES)
        a_canon, b_canon = canonical_pair(a, b, is_directed=is_directed)

        if tie_type:
            if a_is_p or b_is_p:
                cond_a = "(person_a_key = ? OR person_a_key = 'player' OR person_a_key LIKE 'player:%')" if a_is_p else "person_a_key = ?"
                cond_b = "(person_b_key = ? OR person_b_key = 'player' OR person_b_key LIKE 'player:%')" if b_is_p else "person_b_key = ?"
                cond_rev_a = "(person_a_key = ? OR person_a_key = 'player' OR person_a_key LIKE 'player:%')" if b_is_p else "person_a_key = ?"
                cond_rev_b = "(person_b_key = ? OR person_b_key = 'player' OR person_b_key LIKE 'player:%')" if a_is_p else "person_b_key = ?"
                cur = c.execute(
                    f"""UPDATE social_ties
                       SET status = 'ended', ended_turn = ?, end_reason = ?, updated_at = ?
                       WHERE session_id = ? AND (({cond_a} AND {cond_b}) OR ({cond_rev_a} AND {cond_rev_b})) AND tie_type = ? AND status = 'active'""",
                    (turn, reason, now, session_id, a, b, b, a, tie_type),
                )
            else:
                cur = c.execute(
                    """UPDATE social_ties
                       SET status = 'ended', ended_turn = ?, end_reason = ?, updated_at = ?
                       WHERE session_id = ? AND person_a_key = ? AND person_b_key = ? AND tie_type = ? AND status = 'active'""",
                    (turn, reason, now, session_id, a_canon, b_canon, tie_type),
                )
        else:
            if a_is_p or b_is_p:
                cond_a = "(person_a_key = ? OR person_a_key = 'player' OR person_a_key LIKE 'player:%')" if a_is_p else "person_a_key = ?"
                cond_b = "(person_b_key = ? OR person_b_key = 'player' OR person_b_key LIKE 'player:%')" if b_is_p else "person_b_key = ?"
                cond_rev_a = "(person_a_key = ? OR person_a_key = 'player' OR person_a_key LIKE 'player:%')" if b_is_p else "person_a_key = ?"
                cond_rev_b = "(person_b_key = ? OR person_b_key = 'player' OR person_b_key LIKE 'player:%')" if a_is_p else "person_b_key = ?"
                cur = c.execute(
                    f"""UPDATE social_ties
                       SET status = 'ended', ended_turn = ?, end_reason = ?, updated_at = ?
                       WHERE session_id = ? AND (({cond_a} AND {cond_b}) OR ({cond_rev_a} AND {cond_rev_b}))
                         AND status = 'active'""",
                    (turn, reason, now, session_id, a, b, b, a),
                )
            else:
                cur = c.execute(
                    """UPDATE social_ties
                       SET status = 'ended', ended_turn = ?, end_reason = ?, updated_at = ?
                       WHERE session_id = ? AND ((person_a_key = ? AND person_b_key = ?) OR (person_a_key = ? AND person_b_key = ?))
                         AND status = 'active'""",
                    (turn, reason, now, session_id, a, b, b, a),
                )

        changed = cur.rowcount > 0
        if changed and materialize:
            _materialize_endpoints(session_id, a, b, conn=c)
        return changed


def transition_tie(
    session_id: int,
    a: str,
    b: str,
    from_type: str,
    to_type: str,
    *,
    turn: int = 0,
    materialize: bool = True,
    conn: Optional[sqlite3.Connection] = None,
) -> bool:
    """
    Transitions an existing tie from one type to another (e.g. dating -> engaged -> married).
    Preserves closeness and metadata.
    """
    with _get_connection(conn) as c:
        is_dir = bool(from_type in DIRECTED_TYPES)
        a_canon, b_canon = canonical_pair(a, b, is_directed=is_dir)
        row = c.execute(
            """SELECT closeness, visibility, metadata_json FROM social_ties
               WHERE session_id = ? AND person_a_key = ? AND person_b_key = ? AND tie_type = ? AND status = 'active'""",
            (session_id, a_canon, b_canon, from_type),
        ).fetchone()

        if not row:
            return False

        closeness = row["closeness"]
        visibility = row["visibility"]
        try:
            meta = json.loads(row["metadata_json"] or "{}")
        except Exception:
            meta = {}

        end_tie(session_id, a, b, from_type, turn=turn, reason="transitioned", materialize=False, conn=c)
        form_tie(session_id, a, b, to_type, closeness=closeness, visibility=visibility, turn=turn, metadata=meta, materialize=materialize, conn=c)
        return True


def adjust_closeness(
    session_id: int,
    a: str,
    b: str,
    tie_type: Optional[Union[str, int]] = None,
    delta: int = 0,
    *,
    materialize: bool = True,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    """Adjusts closeness on an active tie, clamped between 0 and 100."""
    if isinstance(tie_type, (int, float)):
        delta = int(tie_type)
        tie_type = None

    a_is_p = is_player_person_key(a)
    b_is_p = is_player_person_key(b)

    with _get_connection(conn) as c:
        if tie_type:
            is_dir = bool(tie_type in DIRECTED_TYPES)
            a_canon, b_canon = canonical_pair(a, b, is_directed=is_dir)
            if a_is_p or b_is_p:
                cond_a = "(person_a_key = ? OR person_a_key = 'player' OR person_a_key LIKE 'player:%')" if a_is_p else "person_a_key = ?"
                cond_b = "(person_b_key = ? OR person_b_key = 'player' OR person_b_key LIKE 'player:%')" if b_is_p else "person_b_key = ?"
                cond_rev_a = "(person_a_key = ? OR person_a_key = 'player' OR person_a_key LIKE 'player:%')" if b_is_p else "person_a_key = ?"
                cond_rev_b = "(person_b_key = ? OR person_b_key = 'player' OR person_b_key LIKE 'player:%')" if a_is_p else "person_b_key = ?"
                row = c.execute(
                    f"""SELECT id, closeness FROM social_ties
                        WHERE session_id = ? AND (({cond_a} AND {cond_b}) OR ({cond_rev_a} AND {cond_rev_b}))
                          AND tie_type = ? AND status = 'active'
                        ORDER BY updated_at DESC LIMIT 1""",
                    (session_id, a, b, b, a, tie_type),
                ).fetchone()
            else:
                row = c.execute(
                    """SELECT id, closeness FROM social_ties
                       WHERE session_id = ? AND person_a_key = ? AND person_b_key = ? AND tie_type = ? AND status = 'active'""",
                    (session_id, a_canon, b_canon, tie_type),
                ).fetchone()
        else:
            if a_is_p or b_is_p:
                cond_a = "(person_a_key = ? OR person_a_key = 'player' OR person_a_key LIKE 'player:%')" if a_is_p else "person_a_key = ?"
                cond_b = "(person_b_key = ? OR person_b_key = 'player' OR person_b_key LIKE 'player:%')" if b_is_p else "person_b_key = ?"
                cond_rev_a = "(person_a_key = ? OR person_a_key = 'player' OR person_a_key LIKE 'player:%')" if b_is_p else "person_a_key = ?"
                cond_rev_b = "(person_b_key = ? OR person_b_key = 'player' OR person_b_key LIKE 'player:%')" if a_is_p else "person_b_key = ?"
                row = c.execute(
                    f"""SELECT id, closeness FROM social_ties
                        WHERE session_id = ? AND (({cond_a} AND {cond_b}) OR ({cond_rev_a} AND {cond_rev_b}))
                          AND status = 'active'
                        ORDER BY updated_at DESC LIMIT 1""",
                    (session_id, a, b, b, a),
                ).fetchone()
            else:
                row = c.execute(
                    """SELECT id, closeness FROM social_ties
                       WHERE session_id = ? AND ((person_a_key = ? AND person_b_key = ?) OR (person_a_key = ? AND person_b_key = ?))
                         AND status = 'active'
                       ORDER BY updated_at DESC LIMIT 1""",
                    (session_id, a, b, b, a),
                ).fetchone()

        if not row:
            return 50
        new_val = max(0, min(100, int(row["closeness"]) + int(delta)))
        c.execute(
            "UPDATE social_ties SET closeness = ?, updated_at = ? WHERE id = ?",
            (new_val, time.time(), row["id"]),
        )
        if materialize:
            _materialize_endpoints(session_id, a, b, conn=c)
        return new_val


# --- Queries ---

def get_ties(
    session_id: int,
    person_key: str,
    *,
    active_only: bool = True,
    types: Optional[Set[str]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> List[dict]:
    """
    Returns all ties connected to person_key, enriched with the other person's details.
    """
    is_player_query = is_player_person_key(person_key)
    with _get_connection(conn) as c:
        query = [
            "SELECT t.*, pa.display_name AS a_name, pa.role AS a_role, pa.gender AS a_gender, pa.contact_npc_id AS a_contact,",
            "pb.display_name AS b_name, pb.role AS b_role, pb.gender AS b_gender, pb.contact_npc_id AS b_contact",
            "FROM social_ties t",
            "LEFT JOIN social_persons pa ON pa.session_id = t.session_id AND pa.person_key = t.person_a_key",
            "LEFT JOIN social_persons pb ON pb.session_id = t.session_id AND pb.person_key = t.person_b_key",
        ]
        if is_player_query:
            query.append("WHERE t.session_id = ? AND (t.person_a_key = 'player' OR t.person_a_key LIKE 'player:%' OR t.person_b_key = 'player' OR t.person_b_key LIKE 'player:%')")
            params: list[Any] = [session_id]
        else:
            query.append("WHERE t.session_id = ? AND (t.person_a_key = ? OR t.person_b_key = ?)")
            params = [session_id, person_key, person_key]

        if active_only:
            query.append("AND t.status = 'active'")
        if types:
            placeholders = ",".join("?" for _ in types)
            query.append(f"AND t.tie_type IN ({placeholders})")
            params.extend(list(types))

        query.append("ORDER BY t.updated_at DESC")
        rows = c.execute(" ".join(query), params).fetchall()

        results = []
        for r in rows:
            d = dict(r)
            a_is_target = is_player_person_key(d["person_a_key"]) if is_player_query else (d["person_a_key"] == person_key)
            if a_is_target:
                d["other_person_key"] = d["person_b_key"]
                d["other_display_name"] = "Player" if is_player_person_key(d["person_b_key"]) else (d.get("b_name") or d["person_b_key"])
                d["other_role"] = d.get("b_role") or ""
                d["other_gender"] = d.get("b_gender") or ""
                d["other_contact_id"] = d.get("b_contact")
                d["direction"] = "outbound" if d["is_directed"] else "mutual"
            else:
                d["other_person_key"] = d["person_a_key"]
                d["other_display_name"] = "Player" if is_player_person_key(d["person_a_key"]) else (d.get("a_name") or d["person_a_key"])
                d["other_role"] = d.get("a_role") or ""
                d["other_gender"] = d.get("a_gender") or ""
                d["other_contact_id"] = d.get("a_contact")
                d["direction"] = "inbound" if d["is_directed"] else "mutual"
            results.append(d)
        return results


def get_current_partner(
    session_id: int,
    person_key: str,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[dict]:
    """Returns active exclusive romantic partner dict or None."""
    ties = get_ties(session_id, person_key, active_only=True, types=EXCLUSIVE_ROMANTIC_TYPES, conn=conn)
    if not ties:
        return None
    top = ties[0]
    return {
        "person_key": top["other_person_key"],
        "name": top["other_display_name"],
        "role": top["other_role"],
        "relationship_type": top["tie_type"].capitalize(),
        "is_contactable": bool(top["other_contact_id"]),
        "npc_id": top["other_contact_id"],
        "closeness": top["closeness"],
        "tie_type": top["tie_type"],
    }


def get_secret_affairs(
    session_id: int,
    person_key: str,
    conn: Optional[sqlite3.Connection] = None,
) -> List[dict]:
    """Returns list of active illicit romantic affairs."""
    ties = get_ties(session_id, person_key, active_only=True, types={TIETYPE_AFFAIR}, conn=conn)
    affairs = []
    for t in ties:
        affairs.append({
            "person_key": t["other_person_key"],
            "name": t["other_display_name"],
            "role": t["other_role"],
            "relationship_type": "Secret Affair",
            "is_contactable": bool(t["other_contact_id"]),
            "npc_id": t["other_contact_id"],
            "closeness": t["closeness"],
        })
    return affairs


def get_ex_partners(
    session_id: int,
    person_key: str,
    conn: Optional[sqlite3.Connection] = None,
) -> List[dict]:
    """
    Returns ex-partners derived from ended romantic and affair ties.
    Fixes the bug in social.py where breakup overwrote ex history.
    """
    is_player = is_player_person_key(person_key)
    with _get_connection(conn) as c:
        if is_player:
            query = """
                SELECT t.*, pa.display_name AS a_name, pa.role AS a_role, pa.gender AS a_gender, pa.contact_npc_id AS a_contact,
                       pb.display_name AS b_name, pb.role AS b_role, pb.gender AS b_gender, pb.contact_npc_id AS b_contact
                FROM social_ties t
                LEFT JOIN social_persons pa ON pa.session_id = t.session_id AND pa.person_key = t.person_a_key
                LEFT JOIN social_persons pb ON pb.session_id = t.session_id AND pb.person_key = t.person_b_key
                WHERE t.session_id = ? AND (t.person_a_key = 'player' OR t.person_a_key LIKE 'player:%' OR t.person_b_key = 'player' OR t.person_b_key LIKE 'player:%')
                  AND t.tie_type IN ('dating', 'engaged', 'married', 'affair')
                  AND t.status = 'ended'
                ORDER BY t.ended_turn DESC, t.updated_at DESC
            """
            rows = c.execute(query, (session_id,)).fetchall()
        else:
            query = """
                SELECT t.*, pa.display_name AS a_name, pa.role AS a_role, pa.gender AS a_gender, pa.contact_npc_id AS a_contact,
                       pb.display_name AS b_name, pb.role AS b_role, pb.gender AS b_gender, pb.contact_npc_id AS b_contact
                FROM social_ties t
                LEFT JOIN social_persons pa ON pa.session_id = t.session_id AND pa.person_key = t.person_a_key
                LEFT JOIN social_persons pb ON pb.session_id = t.session_id AND pb.person_key = t.person_b_key
                WHERE t.session_id = ? AND (t.person_a_key = ? OR t.person_b_key = ?)
                  AND t.tie_type IN ('dating', 'engaged', 'married', 'affair')
                  AND t.status = 'ended'
                ORDER BY t.ended_turn DESC, t.updated_at DESC
            """
            rows = c.execute(query, (session_id, person_key, person_key)).fetchall()
        exes = []
        for r in rows:
            is_a = is_player_person_key(r["person_a_key"]) if is_player else (r["person_a_key"] == person_key)
            other_key = r["person_b_key"] if is_a else r["person_a_key"]
            other_name = (r["b_name"] if is_a else r["a_name"]) or other_key
            other_role = (r["b_role"] if is_a else r["a_role"]) or ""
            other_contact = r["b_contact"] if is_a else r["a_contact"]
            exes.append({
                "person_key": other_key,
                "name": other_name,
                "role": other_role,
                "notes": f"Ended on turn {r['ended_turn'] or 0} ({r['end_reason'] or 'breakup'})",
                "ended_turn": r["ended_turn"] or 0,
                "end_reason": r["end_reason"] or "breakup",
                "is_contactable": bool(other_contact),
                "npc_id": other_contact,
            })
        return exes


def get_mutual_friends(
    session_id: int,
    a_key: str,
    b_key: str,
    conn: Optional[sqlite3.Connection] = None,
) -> List[dict]:
    """Computes real graph intersection of mutual friends between a and b."""
    a_friends = {t["other_person_key"]: t for t in get_ties(session_id, a_key, active_only=True, types=PLATONIC_TYPES, conn=conn)}
    b_friends = {t["other_person_key"]: t for t in get_ties(session_id, b_key, active_only=True, types=PLATONIC_TYPES, conn=conn)}
    common_keys = set(a_friends.keys()) & set(b_friends.keys())

    mutuals = []
    for k in common_keys:
        t = a_friends[k]
        mutuals.append({
            "person_key": k,
            "name": t["other_display_name"],
            "role": t["other_role"],
            "is_contactable": bool(t["other_contact_id"]),
            "npc_id": t["other_contact_id"],
        })
    return mutuals


# --- Materialization ---

def materialize_relations(
    session_id: int,
    contact: dict | sqlite3.Row,
    conn: Optional[sqlite3.Connection] = None,
) -> dict:
    """
    Rebuilds the legacy relations_json dictionary from the normalized graph + household data.
    Guarantees 100% backward compatibility for CodexPanel.jsx, cogs/contacts.py, and actor_card.
    """
    c_dict = dict(contact)
    npc_id = c_dict.get("npc_id", "")
    name = c_dict.get("name", "")
    hid = c_dict.get("household_id")

    with _get_connection(conn) as c:
        # Resolve person key
        p_row = get_person_by_contact_id(session_id, npc_id, conn=c)
        person_key = p_row["person_key"] if p_row else canonical_person_key(name)

        # 1. Family: hydrated directly from households table
        family_tree: list[dict] = []
        residence = ""
        if hid:
            try:
                from mechanics.social.genealogy import build_family_tree_from_household, _hydrate_household_entity
                hh_row = c.execute("SELECT * FROM households WHERE id = ?", (hid,)).fetchone()
                if hh_row:
                    residence = hh_row["residence_location"] or ""
                    hh_dict = dict(hh_row)
                    hh_dict["father"] = hh_dict.get("father_json", "{}")
                    hh_dict["mother"] = hh_dict.get("mother_json", "{}")
                    hh_dict["narrative_siblings"] = hh_dict.get("narrative_siblings_json", "[]")
                    hydrated_hh = _hydrate_household_entity(hh_dict, c_dict, "fantasy")
                    family_tree = build_family_tree_from_household(hydrated_hh, name)
            except Exception as e:
                logger.warning(f"Failed to build family tree from household {hid}: {e}")

        # 2. Romance: current_partner, secret_partner, ex_partners
        curr_partner = get_current_partner(session_id, person_key, conn=c)
        secret_affairs = get_secret_affairs(session_id, person_key, conn=c)
        secret_partner = secret_affairs[0] if secret_affairs else None
        exes = get_ex_partners(session_id, person_key, conn=c)

        if curr_partner:
            rel_type = curr_partner.get("relationship_type", "Dating")
            if rel_type.lower() == "dating":
                romance_status = "In a Relationship"
            elif rel_type.lower() == "engaged":
                romance_status = "Engaged"
            elif rel_type.lower() == "married":
                romance_status = "Married"
            else:
                romance_status = "In a Relationship"
        else:
            romance_status = "Single"

        # 3. Friends
        plat_ties = get_ties(session_id, person_key, active_only=True, types=PLATONIC_TYPES, conn=conn)
        friends = []
        for t in plat_ties:
            friends.append({
                "name": t["other_display_name"],
                "role": t["other_role"],
                "closeness": t["closeness"],
                "is_contactable": bool(t["other_contact_id"]),
                "npc_id": t["other_contact_id"],
                "person_key": t["other_person_key"],
            })

        # 4. Rivals
        antag_ties = get_ties(session_id, person_key, active_only=True, types=ANTAGONISTIC_TYPES, conn=conn)
        rivals = []
        for t in antag_ties:
            rivals.append({
                "name": t["other_display_name"],
                "role": t["other_role"],
                "type": t["tie_type"].capitalize(),
                "is_contactable": bool(t["other_contact_id"]),
                "npc_id": t["other_contact_id"],
                "person_key": t["other_person_key"],
            })

        return {
            "family": family_tree,
            "romance": {
                "status": romance_status,
                "current_partner": curr_partner,
                "secret_partner": secret_partner,
                "ex_partners": exes,
            },
            "friends": friends,
            "rivals": rivals,
            "household_id": hid,
            "residence_location": residence,
        }


def materialize_and_save_relations(
    session_id: int,
    contact_npc_id: str,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[dict]:
    """
    Materializes relations for a contact and writes them to contacts.relations_json.
    Also synchronizes contacts.track if romantically linked to the player.
    """
    with _get_connection(conn) as c:
        contact_row = c.execute(
            "SELECT * FROM contacts WHERE session_id = ? AND npc_id = ?",
            (session_id, contact_npc_id),
        ).fetchone()
        if not contact_row:
            return None

        mat = materialize_relations(session_id, contact_row, conn=c)
        mat_json = json.dumps(mat)

        # Sync track: if player is current partner, track is 'romantic'
        curr = mat.get("romance", {}).get("current_partner")
        track_update = ""
        track_param = None
        if curr and is_player_person_key(curr.get("person_key", "")):
            track_update = ", track = 'romantic'"
        elif contact_row["track"] == "romantic":
            # Was romantic, but no longer dating player
            track_update = ", track = 'platonic'"

        c.execute(
            f"UPDATE contacts SET relations_json = ?, updated_at = ?{track_update} WHERE id = ?",
            (mat_json, time.time(), contact_row["id"]),
        )
        return mat


def _materialize_endpoints(
    session_id: int,
    a_key: str,
    b_key: str,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """Helper to re-materialize both endpoints if they correspond to contacts."""
    with _get_connection(conn) as c:
        for k in (a_key, b_key):
            if is_player_person_key(k):
                continue
            p = get_person_by_key(session_id, k, conn=c)
            npc_id = p.get("contact_npc_id") if p else None
            if not npc_id:
                # Self-healing: check contacts by npc_id or canonical name match
                c_row = c.execute(
                    "SELECT npc_id, name FROM contacts WHERE session_id = ? AND (npc_id = ? OR lower(name) = ?)",
                    (session_id, k, k.replace("_", " ")),
                ).fetchone()
                if c_row:
                    npc_id = c_row["npc_id"]
                    link_person_to_contact(session_id, k, npc_id, conn=c)
            if npc_id:
                materialize_and_save_relations(session_id, npc_id, conn=c)


# --- Rollback Helpers ---

def rollback_ties_after_turn(
    session_id: int,
    turn: int,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    """
    Rolls back graph ties to the state at turn:
    1. Deletes active/ended ties that started after turn (origin != 'migration').
    2. Reopens ties that ended after turn (status='active', ended_turn=NULL, end_reason='').
    3. Re-materializes all contacts in the session.
    """
    with _get_connection(conn) as c:
        now = time.time()
        # 1. Delete ties formed after turn
        del_cur = c.execute(
            "DELETE FROM social_ties WHERE session_id = ? AND started_turn > ? AND origin != 'migration'",
            (session_id, turn),
        )
        deleted_count = del_cur.rowcount

        # 2. Re-open ties ended after turn
        reopen_cur = c.execute(
            """UPDATE social_ties
               SET status = 'active', ended_turn = NULL, end_reason = '', updated_at = ?
               WHERE session_id = ? AND ended_turn > ?""",
            (now, session_id, turn),
        )
        reopened_count = reopen_cur.rowcount

        # 3. Re-materialize all contacts
        contacts = c.execute("SELECT npc_id FROM contacts WHERE session_id = ?", (session_id,)).fetchall()
        for cont in contacts:
            materialize_and_save_relations(session_id, cont["npc_id"], conn=c)

        return deleted_count + reopened_count


def rollback_intimate_events_after_turn(
    session_id: int,
    turn: int,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    """Rolls back intimacy ledger events after turn."""
    try:
        from mechanics.social.persona.intimacy.ledger import delete_intimate_events_after_turn
        return delete_intimate_events_after_turn(session_id, turn, conn=conn)
    except Exception as e:
        logger.warning(f"Could not rollback intimate events: {e}")
        return 0


# --- Migration 26: Backfill Legacy Relations ---

def migrate_legacy_relations(conn: Optional[sqlite3.Connection] = None) -> dict:
    """
    Backfills existing contacts.relations_json and track into social_persons and social_ties tables.
    Implements Decision 5 priority tiering:
    - Player relationships always win.
    - Most recently updated contact wins for romantic conflicts (losing tie marked ended with 'migration_conflict').
    - Rivalry supersedes friendship for contradictory claims.
    Returns summary report of migrated sessions, ties, and resolved conflicts.
    """
    report = {
        "sessions_processed": 0,
        "persons_created": 0,
        "ties_created": 0,
        "conflicts_resolved": 0,
    }

    with _get_connection(conn) as c:
        session_ids = [r[0] for r in c.execute("SELECT DISTINCT session_id FROM contacts").fetchall()]
        now = time.time()

        for session_id in session_ids:
            report["sessions_processed"] += 1

            # 1. Identify player person
            char_id = "default"
            c_first = c.execute("SELECT character_id FROM contacts WHERE session_id = ? AND character_id IS NOT NULL LIMIT 1", (session_id,)).fetchone()
            if c_first and c_first["character_id"]:
                char_id = str(c_first["character_id"])
            else:
                sm_row = c.execute("SELECT user_id FROM session_members WHERE session_id = ? LIMIT 1", (session_id,)).fetchone()
                if sm_row and sm_row["user_id"]:
                    ch_row = c.execute("SELECT id FROM characters WHERE user_id = ? LIMIT 1", (sm_row["user_id"],)).fetchone()
                    if ch_row and ch_row["id"]:
                        char_id = str(ch_row["id"])

            p_key = player_person_key(char_id)
            p_name = "Player"
            p_gender = ""
            if char_id != "default":
                c_row = c.execute("SELECT name, gender FROM characters WHERE id = ?", (char_id,)).fetchone()
                if c_row:
                    p_name = c_row["name"] or "Player"
                    p_gender = c_row["gender"] or ""
            get_or_create_person(session_id, p_name, person_key=p_key, gender=p_gender, origin="player", conn=c)

            # 2. Map contacts and school directory
            contacts = c.execute("SELECT * FROM contacts WHERE session_id = ?", (session_id,)).fetchall()
            contact_by_name = {}
            for cont in contacts:
                c_dict = dict(cont)
                c_name = c_dict.get("name", "")
                c_key = canonical_person_key(c_name)
                contact_by_name[c_name.lower().strip()] = (c_key, c_dict)
                role = ""
                try:
                    binfo = json.loads(c_dict.get("basic_info_json") or "{}")
                    role = binfo.get("role", "")
                except Exception:
                    pass
                get_or_create_person(
                    session_id,
                    c_name,
                    person_key=c_key,
                    gender=c_dict.get("gender") or "",
                    role=role,
                    origin="contact",
                    contact_npc_id=c_dict.get("npc_id"),
                    conn=c,
                )

            sd_rows = c.execute("SELECT * FROM school_directory WHERE session_id = ?", (session_id,)).fetchall()
            sd_by_name = {dict(r).get("name", "").lower().strip(): dict(r) for r in sd_rows}

            def resolve_target(name_str: str, role_hint: str = "") -> str:
                clean = (name_str or "").strip()
                if not clean:
                    return ""
                lower = clean.lower()
                if lower in ("player", "you", p_name.lower()):
                    return p_key
                if lower in contact_by_name:
                    return contact_by_name[lower][0]
                if lower in sd_by_name:
                    sd_ent = sd_by_name[lower]
                    sd_key = canonical_person_key(sd_ent.get("name", ""))
                    get_or_create_person(
                        session_id,
                        sd_ent.get("name", clean),
                        person_key=sd_key,
                        gender=sd_ent.get("gender") or "",
                        role=sd_ent.get("role") or role_hint,
                        origin="roster",
                        contact_npc_id=sd_ent.get("npc_id") if sd_ent.get("is_hydrated") else None,
                        conn=c,
                    )
                    return sd_key
                proc_key = canonical_person_key(clean)
                get_or_create_person(session_id, clean, person_key=proc_key, role=role_hint, origin="procedural", conn=c)
                return proc_key

            # 3. Harvest relationship claims
            romantic_claims: list[dict] = []
            affair_claims: list[dict] = []
            ex_claims: list[dict] = []
            platonic_claims: dict[tuple[str, str], dict] = {}
            antagonistic_claims: dict[tuple[str, str], dict] = {}

            for cont in contacts:
                c_dict = dict(cont)
                c_name = c_dict.get("name", "")
                c_key = canonical_person_key(c_name)
                c_updated = float(c_dict.get("updated_at") or 0.0)

                # A. Romantic track
                if str(c_dict.get("track") or "").strip().lower() == "romantic":
                    romantic_claims.append({
                        "a": p_key,
                        "b": c_key,
                        "tie_type": TIETYPE_DATING,
                        "closeness": 80,
                        "visibility": "public",
                        "updated_at": c_updated,
                        "is_player": True,
                    })

                # B. Parse relations_json
                try:
                    rel = json.loads(c_dict.get("relations_json") or "{}")
                except Exception:
                    rel = {}

                rom = rel.get("romance", {})
                curr_p = rom.get("current_partner") or rel.get("current_partner")
                if curr_p:
                    cp_name = curr_p.get("name") if isinstance(curr_p, dict) else str(curr_p)
                    cp_role = curr_p.get("role", "") if isinstance(curr_p, dict) else ""
                    cp_type = curr_p.get("relationship_type", "Dating") if isinstance(curr_p, dict) else "Dating"
                    tgt = resolve_target(cp_name, cp_role)
                    if tgt and tgt != c_key:
                        t_type = TIETYPE_DATING
                        if "married" in cp_type.lower():
                            t_type = TIETYPE_MARRIED
                        elif "engaged" in cp_type.lower():
                            t_type = TIETYPE_ENGAGED
                        is_p = (tgt == p_key)
                        romantic_claims.append({
                            "a": c_key,
                            "b": tgt,
                            "tie_type": t_type,
                            "closeness": 70,
                            "visibility": "public",
                            "updated_at": c_updated,
                            "is_player": is_p,
                        })

                sec_p = rom.get("secret_partner") or rel.get("secret_partner")
                if sec_p:
                    sp_name = sec_p.get("name") if isinstance(sec_p, dict) else str(sec_p)
                    sp_role = sec_p.get("role", "") if isinstance(sec_p, dict) else ""
                    tgt = resolve_target(sp_name, sp_role)
                    if tgt and tgt != c_key:
                        affair_claims.append({
                            "a": c_key,
                            "b": tgt,
                            "closeness": 60,
                            "updated_at": c_updated,
                        })

                for ex in (rom.get("ex_partners") or rel.get("ex_partners") or []):
                    ex_name = ex.get("name") if isinstance(ex, dict) else str(ex)
                    ex_role = ex.get("role", "") if isinstance(ex, dict) else ""
                    ex_reason = ex.get("end_reason", "breakup") if isinstance(ex, dict) else "breakup"
                    ex_turn = int(ex.get("ended_turn", 0)) if isinstance(ex, dict) else 0
                    tgt = resolve_target(ex_name, ex_role)
                    if tgt and tgt != c_key:
                        ex_claims.append({
                            "a": c_key,
                            "b": tgt,
                            "turn": ex_turn,
                            "reason": ex_reason,
                        })

                for f in (rel.get("friends") or []):
                    f_name = f.get("name") if isinstance(f, dict) else str(f)
                    f_role = f.get("role", "") if isinstance(f, dict) else ""
                    f_close = f.get("closeness", 50) if isinstance(f, dict) else 50
                    if isinstance(f_close, str):
                        f_close = 80 if any(k in f_close.lower() for k in ("close", "best")) else 65
                    tgt = resolve_target(f_name, f_role)
                    if tgt and tgt != c_key:
                        pair = canonical_pair(c_key, tgt)
                        platonic_claims[pair] = {
                            "closeness": int(f_close),
                            "updated_at": c_updated,
                        }

                for r in (rel.get("rivals") or []):
                    r_name = r.get("name") if isinstance(r, dict) else str(r)
                    r_role = r.get("role", "") if isinstance(r, dict) else ""
                    tgt = resolve_target(r_name, r_role)
                    if tgt and tgt != c_key:
                        pair = canonical_pair(c_key, tgt)
                        antagonistic_claims[pair] = {
                            "closeness": 50,
                            "updated_at": c_updated,
                        }

            # 4. Resolve Romantic Claims with Priority Tiering (Decision 5)
            # Sort claims: Player ties first, then highest updated_at
            romantic_claims.sort(
                key=lambda x: (1 if x["is_player"] else 0, x["updated_at"]),
                reverse=True,
            )

            partnered_nodes: set[str] = set()
            active_romantic_pairs: set[tuple[str, str]] = set()

            for claim in romantic_claims:
                a_canon, b_canon = canonical_pair(claim["a"], claim["b"])
                pair = (a_canon, b_canon)
                if pair in active_romantic_pairs:
                    continue

                conflict_a = a_canon in partnered_nodes and not is_player_person_key(a_canon)
                conflict_b = b_canon in partnered_nodes and not is_player_person_key(b_canon)

                if conflict_a or conflict_b:
                    report["conflicts_resolved"] += 1
                    if claim["is_player"]:
                        # Multi-dating allowed as Secret Affair (Decision 1)
                        c.execute(
                            """INSERT OR IGNORE INTO social_ties
                               (session_id, person_a_key, person_b_key, tie_type, is_directed, status,
                                closeness, visibility, origin, started_turn, created_at, updated_at)
                               VALUES (?, ?, ?, 'affair', 0, 'active', ?, 'secret', 'migration', 0, ?, ?)""",
                            (session_id, a_canon, b_canon, claim["closeness"], now, now),
                        )
                        report["ties_created"] += 1
                    else:
                        # Loser tie marked ended with 'migration_conflict' (Decision 5)
                        c.execute(
                            """INSERT OR IGNORE INTO social_ties
                               (session_id, person_a_key, person_b_key, tie_type, is_directed, status,
                                closeness, visibility, origin, started_turn, ended_turn, end_reason, created_at, updated_at)
                               VALUES (?, ?, ?, ?, 0, 'ended', ?, 'public', 'migration', 0, 0, 'migration_conflict', ?, ?)""",
                            (session_id, a_canon, b_canon, claim["tie_type"], claim["closeness"], now, now),
                        )
                        report["ties_created"] += 1
                else:
                    partnered_nodes.add(a_canon)
                    partnered_nodes.add(b_canon)
                    active_romantic_pairs.add(pair)
                    c.execute(
                        """INSERT OR IGNORE INTO social_ties
                           (session_id, person_a_key, person_b_key, tie_type, is_directed, status,
                            closeness, visibility, origin, started_turn, created_at, updated_at)
                           VALUES (?, ?, ?, ?, 0, 'active', ?, ?, 'migration', 0, ?, ?)""",
                        (session_id, a_canon, b_canon, claim["tie_type"], claim["closeness"], claim["visibility"], now, now),
                    )
                    report["ties_created"] += 1

            # 5. Insert Affairs
            for aff in affair_claims:
                a_canon, b_canon = canonical_pair(aff["a"], aff["b"])
                c.execute(
                    """INSERT OR IGNORE INTO social_ties
                       (session_id, person_a_key, person_b_key, tie_type, is_directed, status,
                        closeness, visibility, origin, started_turn, created_at, updated_at)
                       VALUES (?, ?, ?, 'affair', 0, 'active', ?, 'secret', 'migration', 0, ?, ?)""",
                    (session_id, a_canon, b_canon, aff["closeness"], now, now),
                )
                report["ties_created"] += 1

            # 6. Insert Exes
            for ex in ex_claims:
                a_canon, b_canon = canonical_pair(ex["a"], ex["b"])
                c.execute(
                    """INSERT OR IGNORE INTO social_ties
                       (session_id, person_a_key, person_b_key, tie_type, is_directed, status,
                        closeness, visibility, origin, started_turn, ended_turn, end_reason, created_at, updated_at)
                       VALUES (?, ?, ?, 'dating', 0, 'ended', 50, 'public', 'migration', 0, ?, ?, ?, ?)""",
                    (session_id, a_canon, b_canon, ex["turn"], ex["reason"], now, now),
                )
                report["ties_created"] += 1

            # 7. Resolve Platonic vs Antagonistic (Decision 5: Rivalry supersedes friendship)
            all_pairs = set(platonic_claims.keys()) | set(antagonistic_claims.keys())
            for pair in all_pairs:
                a_canon, b_canon = pair
                has_friend = pair in platonic_claims
                has_rival = pair in antagonistic_claims

                if has_friend and has_rival:
                    report["conflicts_resolved"] += 1
                    # Rival wins active tie
                    c.execute(
                        """INSERT OR IGNORE INTO social_ties
                           (session_id, person_a_key, person_b_key, tie_type, is_directed, status,
                            closeness, visibility, origin, started_turn, created_at, updated_at)
                           VALUES (?, ?, ?, 'rival', 0, 'active', 50, 'public', 'migration', 0, ?, ?)""",
                        (session_id, a_canon, b_canon, now, now),
                    )
                    # Friend marked ended with migration_conflict
                    c.execute(
                        """INSERT OR IGNORE INTO social_ties
                           (session_id, person_a_key, person_b_key, tie_type, is_directed, status,
                            closeness, visibility, origin, started_turn, ended_turn, end_reason, created_at, updated_at)
                           VALUES (?, ?, ?, 'friend', 0, 'ended', ?, 'public', 'migration', 0, 0, 'migration_conflict', ?, ?)""",
                        (session_id, a_canon, b_canon, platonic_claims[pair]["closeness"], now, now),
                    )
                    report["ties_created"] += 2
                elif has_rival:
                    c.execute(
                        """INSERT OR IGNORE INTO social_ties
                           (session_id, person_a_key, person_b_key, tie_type, is_directed, status,
                            closeness, visibility, origin, started_turn, created_at, updated_at)
                           VALUES (?, ?, ?, 'rival', 0, 'active', 50, 'public', 'migration', 0, ?, ?)""",
                        (session_id, a_canon, b_canon, now, now),
                    )
                    report["ties_created"] += 1
                elif has_friend:
                    c.execute(
                        """INSERT OR IGNORE INTO social_ties
                           (session_id, person_a_key, person_b_key, tie_type, is_directed, status,
                            closeness, visibility, origin, started_turn, created_at, updated_at)
                           VALUES (?, ?, ?, 'friend', 0, 'active', ?, 'public', 'migration', 0, ?, ?)""",
                        (session_id, a_canon, b_canon, platonic_claims[pair]["closeness"], now, now),
                    )
                    report["ties_created"] += 1

            # 8. Re-materialize all contacts in the session
            for cont in contacts:
                c_dict = dict(cont)
                materialize_and_save_relations(session_id, c_dict["npc_id"], conn=c)

    return report


# --- Phase 3: Seeder & Social Circle Initializer ---

def seed_contact_social_graph(
    contact: dict,
    session_id: int,
    scenario: str = "fantasy",
    hash_val: int = 0,
    conn: Optional[sqlite3.Connection] = None,
) -> None:
    """
    Seeds a contact's social circle into social_persons and social_ties tables (Phase 3).
    - Enforces Decision 4: Background romantic partner (15% roll) is a procedural peer
      (leaving real contacts open for player romance).
    - Enforces Decision 4: Friends and rivals query candidate pool (school_directory / contacts),
      falling back to deterministic procedural generation.
    - Sinks ex-partners from intimacy ledger past history (intimate_events) so the Codex
      ex list and intimate ledger never contradict each other (Finding 6).
    """
    name = contact.get("name", "Unknown NPC")
    c_key = canonical_person_key(name)
    c_npc_id = contact.get("npc_id")

    # Role resolution
    role = ""
    try:
        binfo = json.loads(contact.get("basic_info_json") or "{}") if isinstance(contact.get("basic_info_json"), str) else (contact.get("basic_info") or {})
        role = binfo.get("role", "")
    except Exception:
        role = ""

    with _get_connection(conn) as c:
        # 1. Register contact in social_persons
        get_or_create_person(
            session_id,
            name,
            person_key=c_key,
            gender=contact.get("gender") or "",
            role=role,
            origin="contact",
            contact_npc_id=c_npc_id,
            conn=c,
        )

        # 2. Check if this person already has ties in this session
        existing = get_ties(session_id, c_key, active_only=False, conn=c)
        if existing:
            return

        # 3. Collect family names to exclude
        family_names: set[str] = set()
        hid = contact.get("household_id")
        if hid:
            hh_row = c.execute("SELECT * FROM households WHERE id = ?", (hid,)).fetchone()
            if hh_row:
                for field in ("father_json", "mother_json"):
                    try:
                        p_dict = json.loads(hh_row[field] or "{}")
                        if p_dict.get("name"):
                            family_names.add(p_dict["name"].lower().strip())
                    except Exception:
                        pass
                try:
                    s_list = json.loads(hh_row["narrative_siblings_json"] or "[]")
                    for s in s_list:
                        s_n = (s.get("name") if isinstance(s, dict) else str(s)).lower().strip()
                        if s_n:
                            family_names.add(s_n)
                except Exception:
                    pass

        # 4. Sinks exes from Intimacy Ledger
        ledger_rows = c.execute(
            """SELECT DISTINCT partner_name, partner_role FROM intimate_events
               WHERE session_id = ? AND character_id = ? AND event_origin = 'past_history'""",
            (session_id, c_npc_id or c_key),
        ).fetchall()
        for lr in ledger_rows:
            p_name = lr["partner_name"]
            if p_name and p_name.lower().strip() not in ("player", "you") and p_name.lower().strip() not in family_names:
                ex_key = canonical_person_key(p_name)
                get_or_create_person(
                    session_id,
                    p_name,
                    person_key=ex_key,
                    role=lr["partner_role"] or "Former Lover",
                    origin="procedural",
                    conn=c,
                )
                form_tie(session_id, c_key, ex_key, TIETYPE_DATING, closeness=50, origin="procedural", turn=0, materialize=False, conn=c)
                end_tie(session_id, c_key, ex_key, TIETYPE_DATING, turn=0, reason="past_relationship", materialize=False, conn=c)

        # 5. Background or Provided Romantic Partner
        provided_partner = None
        if isinstance(contact.get("relations"), dict):
            rom = contact["relations"].get("romance", {})
            provided_partner = rom.get("current_partner")

        is_explicitly_single = False
        if isinstance(contact.get("relations"), dict):
            rom = contact["relations"].get("romance", {})
            if rom.get("status") == "Single" and not provided_partner:
                is_explicitly_single = True

        if provided_partner and isinstance(provided_partner, dict) and provided_partner.get("name"):
            p_name = provided_partner["name"]
            p_role = provided_partner.get("role", "Partner")
            p_key = canonical_person_key(p_name)
            get_or_create_person(session_id, p_name, person_key=p_key, role=p_role, origin="procedural", conn=c)
            form_tie(session_id, c_key, p_key, TIETYPE_DATING, closeness=70, origin="procedural", turn=0, materialize=False, conn=c)
        elif not is_explicitly_single:
            # 15% taken roll - Decision 4
            is_taken = ((abs(hash_val) % 100) < 15)
            if is_taken:
                from mechanics.social.genealogy import get_deterministic_firstname, get_deterministic_surname
                import namegen
                p_gender = "female" if (contact.get("gender") == "male") else "male"
                p_first = get_deterministic_firstname(scenario, p_gender, hash_val * 47 + 13)
                p_last = get_deterministic_surname(scenario, hash_val * 31 + 29)
                p_role = namegen.generate_role(scenario, hash_val=hash_val * 19 + 7)
                partner_name = f"{p_first} {p_last}"
                partner_key = canonical_person_key(partner_name)
                get_or_create_person(session_id, partner_name, person_key=partner_key, gender=p_gender, role=p_role, origin="procedural", conn=c)
                form_tie(session_id, c_key, partner_key, TIETYPE_DATING, closeness=70, origin="procedural", turn=0, materialize=False, conn=c)

        # 6. Friends & Rivals (Decision 4)
        binfo = {}
        try:
            binfo = json.loads(contact.get("basic_info_json") or "{}") if isinstance(contact.get("basic_info_json"), str) else (contact.get("basic_info") or {})
        except Exception:
            pass
        my_club = binfo.get("club", "")
        my_grade = binfo.get("grade", "")

        cand_rows = c.execute(
            """SELECT name, gender, role, club, grade, npc_id, is_hydrated FROM school_directory
               WHERE session_id = ? AND name != ?""",
            (session_id, name),
        ).fetchall()
        candidates = [dict(r) for r in cand_rows if dict(r).get("name", "").lower().strip() not in family_names]

        matched_friends = []
        if my_club:
            matched_friends = [cd for cd in candidates if cd.get("club") == my_club]
        if not matched_friends and my_grade:
            matched_friends = [cd for cd in candidates if cd.get("grade") == my_grade]

        friend_count = 1 if ((abs(hash_val) % 100) < 65) else 2
        picked_friends = []
        for i in range(friend_count):
            if i < len(matched_friends):
                cand = matched_friends[i]
                f_name = cand["name"]
                f_key = canonical_person_key(f_name)
                get_or_create_person(
                    session_id,
                    f_name,
                    person_key=f_key,
                    gender=cand.get("gender") or "",
                    role=cand.get("role") or "",
                    origin="roster" if not cand.get("is_hydrated") else "contact",
                    contact_npc_id=cand.get("npc_id") if cand.get("is_hydrated") else None,
                    conn=c,
                )
                form_tie(session_id, c_key, f_key, TIETYPE_FRIEND, closeness=80 if i == 0 else 65, origin="procedural", turn=0, materialize=False, conn=c)
                picked_friends.append(f_name.lower().strip())
            else:
                from mechanics.social.genealogy import get_deterministic_firstname, get_deterministic_surname
                import namegen
                f_hash = hash_val * 83 + (i + 1) * 97
                f_gender = "female" if ((abs(f_hash) % 2) == 0) else "male"
                f_first = get_deterministic_firstname(scenario, f_gender, f_hash)
                f_last = get_deterministic_surname(scenario, f_hash * 3 + 7)
                f_role = namegen.generate_role(scenario, hash_val=f_hash)
                f_name = f"{f_first} {f_last}"
                f_key = canonical_person_key(f_name)
                get_or_create_person(session_id, f_name, person_key=f_key, gender=f_gender, role=f_role, origin="procedural", conn=c)
                form_tie(session_id, c_key, f_key, TIETYPE_FRIEND, closeness=80 if i == 0 else 65, origin="procedural", turn=0, materialize=False, conn=c)

        # Rival
        rival_cands = [cd for cd in candidates if cd.get("name", "").lower().strip() not in picked_friends]
        if rival_cands and my_club:
            diff_club_cands = [cd for cd in rival_cands if cd.get("club") and cd.get("club") != my_club]
            if diff_club_cands:
                rival_cands = diff_club_cands
        if rival_cands:
            r_cand = rival_cands[abs(hash_val * 101) % len(rival_cands)]
            r_name = r_cand["name"]
            r_key = canonical_person_key(r_name)
            get_or_create_person(
                session_id,
                r_name,
                person_key=r_key,
                gender=r_cand.get("gender") or "",
                role=r_cand.get("role") or "",
                origin="roster" if not r_cand.get("is_hydrated") else "contact",
                contact_npc_id=r_cand.get("npc_id") if r_cand.get("is_hydrated") else None,
                conn=c,
            )
            form_tie(session_id, c_key, r_key, TIETYPE_RIVAL, closeness=50, origin="procedural", turn=0, materialize=False, conn=c)
        else:
            from mechanics.social.genealogy import get_deterministic_firstname, get_deterministic_surname
            import namegen
            r_hash = hash_val * 101 + 53
            r_gender = contact.get("gender") or "female"
            r_first = get_deterministic_firstname(scenario, r_gender, r_hash)
            r_last = get_deterministic_surname(scenario, r_hash * 5 + 17)
            r_role = namegen.generate_role(scenario, hash_val=r_hash)
            r_name = f"{r_first} {r_last}"
            r_key = canonical_person_key(r_name)
            get_or_create_person(session_id, r_name, person_key=r_key, gender=r_gender, role=r_role, origin="procedural", conn=c)
            form_tie(session_id, c_key, r_key, TIETYPE_RIVAL, closeness=50, origin="procedural", turn=0, materialize=False, conn=c)

        # 7. Materialize
        if c_npc_id:
            materialize_and_save_relations(session_id, c_npc_id, conn=c)


