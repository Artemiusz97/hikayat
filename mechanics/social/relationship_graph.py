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

def player_person_key(character_id: Any = None) -> str:
    """Returns the single session-scoped canonical person key for the player character."""
    return "player"


def is_player_person_key(key: Any) -> bool:
    """Checks if a person key refers to the player."""
    clean = str(key or "").strip().lower()
    return clean in ("player", "you") or clean.startswith("player:") or clean.startswith("player_")


def canonical_person_key(name: str, disambiguator: str = "") -> str:
    """Produces a clean canonical text key from a name."""
    if not disambiguator and is_player_person_key(name):
        return "player"
    clean = re.sub(r"[^a-z0-9]+", "_", (name or "").lower().strip()).strip("_")
    if disambiguator:
        d_clean = re.sub(r"[^a-z0-9]+", "_", str(disambiguator).lower().strip()).strip("_")
        if d_clean:
            clean = f"{clean}_{d_clean}"
    return clean or "unknown_person"


def _resolve_player_display_name(session_id: int, conn: sqlite3.Connection) -> str:
    """Resolves the player's actual character display name for a session."""
    try:
        sp = conn.execute(
            "SELECT display_name FROM social_persons WHERE session_id = ? AND person_key = 'player'",
            (session_id,),
        ).fetchone()
        if sp and sp["display_name"] and not is_player_person_key(sp["display_name"]):
            return str(sp["display_name"]).strip()
        row = conn.execute(
            """SELECT c.name FROM characters c
               JOIN sessions s ON (s.character_id = c.id OR c.active_session_id = s.id)
               WHERE s.id = ? LIMIT 1""",
            (session_id,),
        ).fetchone()
        if row and row["name"]:
            return str(row["name"]).strip()
        sm = conn.execute(
            """SELECT c.name FROM session_members m
               JOIN characters c ON c.user_id = m.user_id
               WHERE m.session_id = ? LIMIT 1""",
            (session_id,),
        ).fetchone()
        if sm and sm["name"]:
            return str(sm["name"]).strip()
    except Exception:
        pass
    return "Player"


def resolve_npc_id_for_person(
    session_id: int,
    person_key_or_id: str,
    conn: Optional[sqlite3.Connection] = None,
) -> Optional[str]:
    """Resolves contacts.npc_id reliably across slug variations (hyphens, apostrophes, accents)."""
    raw = str(person_key_or_id or "").strip()
    if not raw or is_player_person_key(raw):
        return None
    p_key = canonical_person_key(raw)
    with _get_connection(conn) as c:
        p_row = c.execute(
            "SELECT contact_npc_id FROM social_persons WHERE session_id = ? AND person_key = ?",
            (session_id, p_key),
        ).fetchone()
        if p_row and p_row["contact_npc_id"]:
            return str(p_row["contact_npc_id"])
        c_direct = c.execute(
            "SELECT npc_id FROM contacts WHERE session_id = ? AND (npc_id = ? OR lower(name) = ?)",
            (session_id, raw.lower().replace(" ", "_"), raw.lower()),
        ).fetchone()
        if c_direct and c_direct["npc_id"]:
            link_person_to_contact(session_id, p_key, c_direct["npc_id"], conn=c)
            return str(c_direct["npc_id"])
        all_c = c.execute(
            "SELECT npc_id, name FROM contacts WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        for cr in all_c:
            if canonical_person_key(cr["npc_id"]) == p_key or canonical_person_key(cr["name"]) == p_key:
                link_person_to_contact(session_id, p_key, cr["npc_id"], conn=c)
                return str(cr["npc_id"])
    return None


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
    a_norm = "player" if is_player_person_key(a) else canonical_person_key(a)
    b_norm = "player" if is_player_person_key(b) else canonical_person_key(b)
    if a_norm == b_norm:
        raise ValueError(f"Cannot form tie between a person and themselves ({a_norm})")

    is_directed = 1 if tie_type in DIRECTED_TYPES else 0
    a_canon, b_canon = canonical_pair(a_norm, b_norm, is_directed=bool(is_directed))
    now = time.time()
    closeness_clamped = max(0, min(100, int(closeness)))
    meta_json = json.dumps(metadata or {})

    with _get_connection(conn) as c:
        # Ensure both nodes exist in registry without stripping colons or clobbering display names
        for endpoint_key, raw_arg in ((a_canon, a), (b_canon, b)):
            if endpoint_key == "player":
                p_disp = _resolve_player_display_name(session_id, c)
                get_or_create_person(session_id, p_disp, person_key="player", origin="player", conn=c)
            else:
                disp_hint = raw_arg if (raw_arg and " " in str(raw_arg)) else endpoint_key.replace("_", " ").title()
                get_or_create_person(session_id, disp_hint, person_key=endpoint_key, conn=c)

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
                        end_tie(session_id, a_canon, partner_a["person_key"], partner_a["tie_type"], turn=turn, reason=reason, materialize=materialize, conn=c)
                    if conflict_b:
                        reason = "left_for_player" if is_player_involved else "left_for_partner"
                        end_tie(session_id, b_canon, partner_b["person_key"], partner_b["tie_type"], turn=turn, reason=reason, materialize=materialize, conn=c)
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
    Respects directed tie orientation even when the player is an endpoint.
    """
    now = time.time()
    a_norm = "player" if is_player_person_key(a) else canonical_person_key(a)
    b_norm = "player" if is_player_person_key(b) else canonical_person_key(b)

    with _get_connection(conn) as c:
        if tie_type:
            is_directed = bool(tie_type in DIRECTED_TYPES)
            a_canon, b_canon = canonical_pair(a_norm, b_norm, is_directed=is_directed)
            cur = c.execute(
                """UPDATE social_ties
                   SET status = 'ended', ended_turn = ?, end_reason = ?, updated_at = ?
                   WHERE session_id = ? AND person_a_key = ? AND person_b_key = ? AND tie_type = ? AND status = 'active'""",
                (turn, reason, now, session_id, a_canon, b_canon, tie_type),
            )
        else:
            cur = c.execute(
                """UPDATE social_ties
                   SET status = 'ended', ended_turn = ?, end_reason = ?, updated_at = ?
                   WHERE session_id = ? AND ((person_a_key = ? AND person_b_key = ?) OR (person_a_key = ? AND person_b_key = ?))
                     AND status = 'active'""",
                (turn, reason, now, session_id, a_norm, b_norm, b_norm, a_norm),
            )

        changed = cur.rowcount > 0
        if changed and materialize:
            _materialize_endpoints(session_id, a_norm, b_norm, conn=c)
        return changed


def end_all_romantic_ties(
    session_id: int,
    a: str,
    b: str,
    *,
    turn: int = 0,
    reason: str = "breakup",
    materialize: bool = True,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    """Ends all active romantic ties (dating, engaged, married, affair) between a and b."""
    now = time.time()
    a_norm = "player" if is_player_person_key(a) else canonical_person_key(a)
    b_norm = "player" if is_player_person_key(b) else canonical_person_key(b)
    a_canon, b_canon = canonical_pair(a_norm, b_norm, is_directed=False)
    with _get_connection(conn) as c:
        cur = c.execute(
            """UPDATE social_ties
               SET status = 'ended', ended_turn = ?, end_reason = ?, updated_at = ?
               WHERE session_id = ? AND person_a_key = ? AND person_b_key = ?
                 AND tie_type IN ('dating', 'engaged', 'married', 'affair') AND status = 'active'""",
            (turn, reason, now, session_id, a_canon, b_canon),
        )
        cnt = cur.rowcount
        if cnt > 0 and materialize:
            _materialize_endpoints(session_id, a_norm, b_norm, conn=c)
        return cnt


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
    """Adjusts closeness on an active tie, clamped between 0 and 100. Respects directed tie orientation."""
    if isinstance(tie_type, (int, float)):
        delta = int(tie_type)
        tie_type = None

    a_norm = "player" if is_player_person_key(a) else canonical_person_key(a)
    b_norm = "player" if is_player_person_key(b) else canonical_person_key(b)

    with _get_connection(conn) as c:
        if tie_type:
            is_dir = bool(tie_type in DIRECTED_TYPES)
            a_canon, b_canon = canonical_pair(a_norm, b_norm, is_directed=is_dir)
            row = c.execute(
                """SELECT id, closeness FROM social_ties
                   WHERE session_id = ? AND person_a_key = ? AND person_b_key = ? AND tie_type = ? AND status = 'active'""",
                (session_id, a_canon, b_canon, tie_type),
            ).fetchone()
        else:
            row = c.execute(
                """SELECT id, closeness FROM social_ties
                   WHERE session_id = ? AND ((person_a_key = ? AND person_b_key = ?) OR (person_a_key = ? AND person_b_key = ?))
                     AND status = 'active'
                   ORDER BY updated_at DESC LIMIT 1""",
                (session_id, a_norm, b_norm, b_norm, a_norm),
            ).fetchone()

        if not row:
            return 50
        new_val = max(0, min(100, int(row["closeness"]) + int(delta)))
        c.execute(
            "UPDATE social_ties SET closeness = ?, updated_at = ? WHERE id = ?",
            (new_val, time.time(), row["id"]),
        )
        if materialize:
            _materialize_endpoints(session_id, a_norm, b_norm, conn=c)
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
    target_key = "player" if is_player_person_key(person_key) else canonical_person_key(person_key)
    with _get_connection(conn) as c:
        query = [
            "SELECT t.*, pa.display_name AS a_name, pa.role AS a_role, pa.gender AS a_gender, pa.contact_npc_id AS a_contact,",
            "pb.display_name AS b_name, pb.role AS b_role, pb.gender AS b_gender, pb.contact_npc_id AS b_contact",
            "FROM social_ties t",
            "LEFT JOIN social_persons pa ON pa.session_id = t.session_id AND pa.person_key = t.person_a_key",
            "LEFT JOIN social_persons pb ON pb.session_id = t.session_id AND pb.person_key = t.person_b_key",
            "WHERE t.session_id = ? AND (t.person_a_key = ? OR t.person_b_key = ?)",
        ]
        params: list[Any] = [session_id, target_key, target_key]

        if active_only:
            query.append("AND t.status = 'active'")
        if types:
            placeholders = ",".join("?" for _ in types)
            query.append(f"AND t.tie_type IN ({placeholders})")
            params.extend(list(types))

        query.append("ORDER BY t.updated_at DESC")
        rows = c.execute(" ".join(query), params).fetchall()
        player_disp: Optional[str] = None

        results = []
        for r in rows:
            d = dict(r)
            a_is_target = (d["person_a_key"] == target_key)
            if a_is_target:
                other_k = d["person_b_key"]
                if is_player_person_key(other_k):
                    if player_disp is None:
                        player_disp = _resolve_player_display_name(session_id, c)
                    other_disp = player_disp
                else:
                    other_disp = d.get("b_name") or other_k
                d["other_person_key"] = other_k
                d["other_display_name"] = other_disp
                d["other_role"] = d.get("b_role") or ""
                d["other_gender"] = d.get("b_gender") or ""
                d["other_contact_id"] = d.get("b_contact")
                d["direction"] = "outbound" if d["is_directed"] else "mutual"
            else:
                other_k = d["person_a_key"]
                if is_player_person_key(other_k):
                    if player_disp is None:
                        player_disp = _resolve_player_display_name(session_id, c)
                    other_disp = player_disp
                else:
                    other_disp = d.get("a_name") or other_k
                d["other_person_key"] = other_k
                d["other_display_name"] = other_disp
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
    target_key = "player" if is_player_person_key(person_key) else canonical_person_key(person_key)
    with _get_connection(conn) as c:
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
        rows = c.execute(query, (session_id, target_key, target_key)).fetchall()
        player_disp: Optional[str] = None
        exes = []
        for r in rows:
            is_a = (r["person_a_key"] == target_key)
            other_key = r["person_b_key"] if is_a else r["person_a_key"]
            if is_player_person_key(other_key):
                if player_disp is None:
                    player_disp = _resolve_player_display_name(session_id, c)
                other_name = player_disp
            else:
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
    Rebuilds the relations_json projection from the normalized graph + household data.
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
                from mechanics.social.genealogy import build_family_tree_for_member, _hydrate_household_entity
                hh_row = c.execute("SELECT * FROM households WHERE id = ?", (hid,)).fetchone()
                if hh_row:
                    s_row = c.execute("SELECT scenario FROM sessions WHERE id = ?", (session_id,)).fetchone()
                    scen = str(s_row["scenario"] or "fantasy") if s_row else "fantasy"
                    residence = hh_row["residence_location"] or ""
                    hh_dict = dict(hh_row)
                    hh_dict["father"] = hh_dict.get("father_json", "{}")
                    hh_dict["mother"] = hh_dict.get("mother_json", "{}")
                    hh_dict["narrative_siblings"] = hh_dict.get("narrative_siblings_json", "[]")
                    hydrated_hh = _hydrate_household_entity(hh_dict, c_dict, scen, conn=c)
                    family_tree = build_family_tree_for_member(hydrated_hh, name, member_role=c_dict.get("household_role"))
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

        # 3. Friends (use active connection c!)
        plat_ties = get_ties(session_id, person_key, active_only=True, types=PLATONIC_TYPES, conn=c)
        friends = []
        for t in plat_ties:
            try:
                t_meta = json.loads(t.get("metadata_json") or "{}")
            except Exception:
                t_meta = {}
            closeness_out = t_meta.get("closeness_label") if t_meta.get("closeness_label") else t["closeness"]
            friends.append({
                "name": t["other_display_name"],
                "role": t["other_role"],
                "closeness": closeness_out,
                "closeness_score": t["closeness"],
                "is_contactable": bool(t["other_contact_id"]),
                "npc_id": t["other_contact_id"],
                "person_key": t["other_person_key"],
            })

        # 4. Rivals (use active connection c!)
        antag_ties = get_ties(session_id, person_key, active_only=True, types=ANTAGONISTIC_TYPES, conn=c)
        rivals = []
        for t in antag_ties:
            try:
                t_meta = json.loads(t.get("metadata_json") or "{}")
            except Exception:
                t_meta = {}
            rival_label = t_meta.get("rival_type") or t["tie_type"].capitalize()
            rivals.append({
                "name": t["other_display_name"],
                "role": t["other_role"],
                "type": rival_label,
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
    Also synchronizes contacts.track if romantically linked to (or broken up with) the player.
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

        curr = mat.get("romance", {}).get("current_partner")
        sec = mat.get("romance", {}).get("secret_partner")
        exes = mat.get("romance", {}).get("ex_partners") or []
        player_primary = bool(curr and is_player_person_key(curr.get("person_key", "")))
        player_secret = bool(sec and is_player_person_key(sec.get("person_key", "")))
        player_ex = any(is_player_person_key(ex.get("person_key", "")) for ex in exes)

        track_update = ""
        if player_primary:
            track_update = ", track = 'romantic'"
        elif contact_row["track"] == "romantic" and not player_secret and player_ex:
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
            npc_id = resolve_npc_id_for_person(session_id, k, conn=c)
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

        # 2. Check if this person's non-player social circle is already seeded in this session
        existing = get_ties(session_id, c_key, active_only=False, conn=c)
        has_friend_or_rival_ties = any(
            not is_player_person_key(t.get("other_person_key", ""))
            and t.get("tie_type") in (PLATONIC_TYPES | ANTAGONISTIC_TYPES)
            for t in existing
        )
        if has_friend_or_rival_ties:
            return
        player_rom = any(
            is_player_person_key(t.get("other_person_key", ""))
            and t.get("tie_type") in ROMANTIC_TYPES
            and t.get("status") == "active"
            for t in existing
        )
        is_initial_romantic_track = str(contact.get("track") or "").strip().lower() == "romantic"

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

        # 4. Sinks exes from Intimacy Ledger (insert directly as ended so pre-seeded active partners are preserved)
        existing_partner = get_current_partner(session_id, c_key, conn=c)
        ledger_rows = c.execute(
            """SELECT DISTINCT partner_name, partner_role FROM intimate_events
               WHERE session_id = ? AND character_id = ? AND event_origin = 'past_history'""",
            (session_id, c_npc_id or c_key),
        ).fetchall()
        now_ex_ts = time.time()
        for lr in ledger_rows:
            p_name = lr["partner_name"]
            if p_name and p_name.lower().strip() not in ("player", "you") and p_name.lower().strip() not in family_names:
                ex_key = canonical_person_key(p_name)
                if existing_partner and existing_partner.get("person_key") == ex_key:
                    continue
                get_or_create_person(
                    session_id,
                    p_name,
                    person_key=ex_key,
                    role=lr["partner_role"] or "Former Lover",
                    origin="procedural",
                    conn=c,
                )
                ex_a, ex_b = canonical_pair(c_key, ex_key, is_directed=False)
                already_ex = c.execute(
                    """SELECT id FROM social_ties
                       WHERE session_id = ? AND person_a_key = ? AND person_b_key = ?
                         AND tie_type = ? AND status = 'ended'""",
                    (session_id, ex_a, ex_b, TIETYPE_DATING),
                ).fetchone()
                if not already_ex:
                    c.execute(
                        """INSERT INTO social_ties
                           (session_id, person_a_key, person_b_key, tie_type, is_directed, status,
                            closeness, visibility, origin, started_turn, ended_turn, end_reason,
                            metadata_json, created_at, updated_at)
                           VALUES (?, ?, ?, ?, 0, 'ended', 50, 'public', 'procedural', 0, 0, 'past_relationship', '{}', ?, ?)""",
                        (session_id, ex_a, ex_b, TIETYPE_DATING, now_ex_ts, now_ex_ts),
                    )

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

        if existing_partner and not is_player_person_key(existing_partner.get("person_key")):
            if player_rom or is_initial_romantic_track:
                end_tie(
                    session_id,
                    c_key,
                    existing_partner["person_key"],
                    existing_partner.get("tie_type") or TIETYPE_DATING,
                    turn=0,
                    reason="left_for_player",
                    materialize=False,
                    conn=c,
                )
        elif provided_partner and isinstance(provided_partner, dict) and provided_partner.get("name"):
            p_name = provided_partner["name"]
            p_role = provided_partner.get("role", "Partner")
            if not is_player_person_key(p_name):
                p_key = canonical_person_key(p_name)
                get_or_create_person(session_id, p_name, person_key=p_key, role=p_role, origin="procedural", conn=c)
                form_tie(session_id, c_key, p_key, TIETYPE_DATING, closeness=70, origin="procedural", turn=0, materialize=False, conn=c)
                if player_rom:
                    end_tie(session_id, c_key, p_key, TIETYPE_DATING, turn=0, reason="left_for_player", materialize=False, conn=c)
        elif not is_explicitly_single and not player_rom and not is_initial_romantic_track:
            # Openness-scaled taken roll - Decision 4
            rg_app = contact.get("appearance") or {}
            if isinstance(rg_app, str):
                try:
                    import json
                    rg_app = json.loads(rg_app)
                except Exception:
                    rg_app = {}
            rg_binfo = contact.get("basic_info") or {}
            if isinstance(rg_binfo, str):
                try:
                    import json
                    rg_binfo = json.loads(rg_binfo)
                except Exception:
                    rg_binfo = {}
            rg_open = str(
                rg_app.get("erotic_openness")
                or rg_app.get("openness")
                or contact.get("openness")
                or rg_binfo.get("openness")
                or "moderate"
            ).lower()
            if "prude" in rg_open or "modest" in rg_open or "chaste" in rg_open:
                taken_rate = 8
            elif "shameless" in rg_open or "lewd" in rg_open:
                taken_rate = 35
            elif "bold" in rg_open or "uninhibited" in rg_open:
                taken_rate = 25
            else:
                taken_rate = 15
            is_taken = ((abs(hash_val) % 100) < taken_rate)
            if is_taken:
                from mechanics.social.genealogy import generate_deterministic_full_name
                import namegen
                p_gender = "female" if (contact.get("gender") == "male") else "male"
                partner_name = generate_deterministic_full_name(scenario, p_gender, hash_val * 47 + 13)
                p_role = namegen.generate_role(scenario, hash_val=hash_val * 19 + 7)
                partner_key = canonical_person_key(partner_name)
                get_or_create_person(session_id, partner_name, person_key=partner_key, gender=p_gender, role=p_role, origin="procedural", conn=c)
                form_tie(session_id, c_key, partner_key, TIETYPE_DATING, closeness=70, origin="procedural", turn=0, materialize=False, conn=c)

        if is_initial_romantic_track and not player_rom and not get_current_partner(session_id, c_key, conn=c):
            p_disp = _resolve_player_display_name(session_id, c)
            get_or_create_person(session_id, p_disp, person_key="player", origin="player", conn=c)
            init_close = max(60, int(contact.get("relationship_score") or 60))
            form_tie(session_id, c_key, "player", TIETYPE_DATING, closeness=init_close, origin="initial_track", turn=0, supersede=True, materialize=False, conn=c)

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
                from mechanics.social.genealogy import generate_deterministic_full_name
                import namegen
                f_hash = hash_val * 83 + (i + 1) * 97
                f_gender = "female" if ((abs(f_hash) % 2) == 0) else "male"
                f_name = generate_deterministic_full_name(scenario, f_gender, f_hash)
                f_role = namegen.generate_role(scenario, hash_val=f_hash)
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
            from mechanics.social.genealogy import generate_deterministic_full_name
            import namegen
            r_hash = hash_val * 101 + 53
            r_gender = contact.get("gender") or "female"
            r_name = generate_deterministic_full_name(scenario, r_gender, r_hash)
            r_role = namegen.generate_role(scenario, hash_val=r_hash)
            r_key = canonical_person_key(r_name)
            get_or_create_person(session_id, r_name, person_key=r_key, gender=r_gender, role=r_role, origin="procedural", conn=c)
            form_tie(session_id, c_key, r_key, TIETYPE_RIVAL, closeness=50, origin="procedural", turn=0, materialize=False, conn=c)

        # 7. Materialize
        if c_npc_id:
            materialize_and_save_relations(session_id, c_npc_id, conn=c)


def get_canonical_peer_couples(
    session_id: int,
    *,
    active_only: bool = True,
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    """
    Returns canonical peer couples seeded in `social_ties` (`origin = 'canonical_couple'`),
    enriched with both partners' display names, roles, genders, and contact IDs.
    """
    if not session_id:
        return []
    with _get_connection(conn) as c:
        sql = [
            "SELECT t.*, pa.display_name AS a_name, pa.role AS a_role, pa.gender AS a_gender, pa.contact_npc_id AS a_contact,",
            "pb.display_name AS b_name, pb.role AS b_role, pb.gender AS b_gender, pb.contact_npc_id AS b_contact",
            "FROM social_ties t",
            "LEFT JOIN social_persons pa ON pa.session_id = t.session_id AND pa.person_key = t.person_a_key",
            "LEFT JOIN social_persons pb ON pb.session_id = t.session_id AND pb.person_key = t.person_b_key",
            "WHERE t.session_id = ? AND t.origin = 'canonical_couple' AND t.tie_type = ?",
        ]
        params: list[Any] = [session_id, TIETYPE_DATING]
        if active_only:
            sql.append("AND t.status = 'active'")
        sql.append("ORDER BY t.id ASC")
        rows = c.execute(" ".join(sql), params).fetchall()
        couples: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            couples.append({
                "id": d.get("id"),
                "person_a_key": d["person_a_key"],
                "person_a_name": d.get("a_name") or d["person_a_key"],
                "person_a_role": d.get("a_role") or "",
                "person_a_gender": d.get("a_gender") or "",
                "person_a_contact_id": d.get("a_contact"),
                "person_b_key": d["person_b_key"],
                "person_b_name": d.get("b_name") or d["person_b_key"],
                "person_b_role": d.get("b_role") or "",
                "person_b_gender": d.get("b_gender") or "",
                "person_b_contact_id": d.get("b_contact"),
                "closeness": d.get("closeness", 75),
                "status": d.get("status", "active"),
            })
        return couples


def ensure_canonical_peer_couples(
    session_id: int,
    scen_key: str = "high_school_drama",
    count: int = 5,
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    """
    Deterministically seeds `count` (default 5) canonical `TIETYPE_DATING` peer couples
    among pregenerated Campus & Youth Peer characters (~85% of the student body stays single).
    Idempotent per session: once seeded, even if a couple later breaks up (status='ended'),
    they are not re-seeded.
    """
    if not session_id or count <= 0:
        return []
    import hashlib
    import namegen

    with _get_connection(conn) as c:
        existing_any = get_canonical_peer_couples(session_id, active_only=False, conn=c)
        if existing_any:
            return [cp for cp in existing_any if cp.get("status") == "active"]

        peer_rows = c.execute(
            """SELECT npc_id, name, gender, role, grade, club, sibling_name, is_hydrated
               FROM school_directory
               WHERE session_id = ?
                 AND grade IN ('Freshman', 'Sophomore', 'Junior', 'Senior', 'Youth Peer')
               ORDER BY id ASC""",
            (session_id,),
        ).fetchall()
        if len(peer_rows) < 2:
            return []

        # Exclude any peer already dating someone or on the player's romantic track
        taken_keys: Set[str] = set()
        active_rom_rows = c.execute(
            """SELECT person_a_key, person_b_key FROM social_ties
               WHERE session_id = ? AND status = 'active'
                 AND tie_type IN ('dating', 'engaged', 'married')""",
            (session_id,),
        ).fetchall()
        for rr in active_rom_rows:
            taken_keys.add(rr["person_a_key"])
            taken_keys.add(rr["person_b_key"])

        contact_map: Dict[str, Dict[str, Any]] = {}
        c_rows = c.execute(
            "SELECT npc_id, name, track FROM contacts WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        for cr in c_rows:
            cd = dict(cr)
            ck = canonical_person_key(cd.get("name") or cd.get("npc_id") or "")
            contact_map[ck] = cd
            if str(cd.get("track") or "").strip().lower() == "romantic":
                taken_keys.add(ck)

        pool: List[Dict[str, Any]] = []
        for pr in peer_rows:
            pd = dict(pr)
            pk = canonical_person_key(pd.get("name") or "")
            if not pk or pk in taken_keys or is_player_person_key(pk):
                continue
            pd["_pkey"] = pk
            _, raw_sur = namegen.extract_first_and_last_name(pd.get("name") or "")
            pd["_base_sur"] = namegen.normalize_base_surname(raw_sur).lower()
            pool.append(pd)

        # Deterministic sort seeded by session_id so every run with the same session_id picks identical couples
        def _det_rank(entry: Dict[str, Any], salt: str = "a") -> int:
            h = hashlib.md5(f"canon_couple:{session_id}:{salt}:{entry['_pkey']}".encode("utf-8")).hexdigest()
            return int(h[:8], 16)

        ordered = sorted(pool, key=lambda x: _det_rank(x, "lead"))
        grade_num = {"Freshman": 1, "Sophomore": 2, "Junior": 3, "Senior": 4, "Youth Peer": 3}

        used_keys: Set[str] = set()
        formed_count = 0

        for idx_a, cand_a in enumerate(ordered):
            if formed_count >= count:
                break
            ka = cand_a["_pkey"]
            if ka in used_keys:
                continue

            ga = grade_num.get(str(cand_a.get("grade") or ""), 3)
            sib_a = str(cand_a.get("sibling_name") or "").strip().lower()
            sur_a = cand_a["_base_sur"]
            gen_a = str(cand_a.get("gender") or "").lower()

            best_b: Optional[Dict[str, Any]] = None
            best_score: Tuple[int, int] = (-999, 0)

            for cand_b in ordered[idx_a + 1:]:
                kb = cand_b["_pkey"]
                if kb in used_keys or kb == ka:
                    continue
                name_b_low = str(cand_b.get("name") or "").strip().lower()
                sib_b = str(cand_b.get("sibling_name") or "").strip().lower()
                name_a_low = str(cand_a.get("name") or "").strip().lower()
                if sib_a and sib_a == name_b_low:
                    continue
                if sib_b and sib_b == name_a_low:
                    continue
                if sur_a and cand_b["_base_sur"] and sur_a == cand_b["_base_sur"]:
                    continue

                gb = grade_num.get(str(cand_b.get("grade") or ""), 3)
                grade_gap = abs(ga - gb)
                if grade_gap > 1:
                    continue

                gen_b = str(cand_b.get("gender") or "").lower()
                # Mostly mixed-gender couples with ~20% same-gender variety
                want_same_gender = (formed_count == 4)
                gender_fit = (1 if (gen_a == gen_b) == want_same_gender else 0)
                same_grade_fit = 2 if grade_gap == 0 else 1
                tie_break = -(_det_rank(cand_b, f"match_{ka}") % 10000)
                cand_score = (gender_fit * 4 + same_grade_fit, tie_break)
                if cand_score > best_score:
                    # Also verify incest guard if contacts exist
                    if is_incestuous(session_id, ka, kb, conn=c):
                        continue
                    best_score = cand_score
                    best_b = cand_b

            if not best_b:
                continue

            kb = best_b["_pkey"]
            for member in (cand_a, best_b):
                mk = member["_pkey"]
                c_info = contact_map.get(mk)
                c_id = c_info["npc_id"] if c_info else (member.get("npc_id") if member.get("is_hydrated") else None)
                get_or_create_person(
                    session_id,
                    member["name"],
                    person_key=mk,
                    gender=member.get("gender") or "",
                    role=member.get("role") or "",
                    origin="contact" if c_id else "roster",
                    contact_npc_id=c_id,
                    conn=c,
                )

            tie_res = form_tie(
                session_id,
                ka,
                kb,
                TIETYPE_DATING,
                closeness=75,
                origin="canonical_couple",
                turn=0,
                materialize=True,
                conn=c,
            )
            if tie_res is not None:
                used_keys.add(ka)
                used_keys.add(kb)
                formed_count += 1

        return get_canonical_peer_couples(session_id, active_only=True, conn=c)



