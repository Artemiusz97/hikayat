from __future__ import annotations

import db
import json
import re
import sqlite3
import time
from ..core import (_restore_session_table_rows, get_conn)

def save_school_roster(session_id: int, roster: list[dict]) -> bool:
    """Saves or updates a pre-generated school directory roster for a session."""
    if not roster or not session_id:
        return False
    now = time.time()
    with get_conn() as conn:
        for char in roster:
            npc_id = str(char.get("npc_id") or char.get("name", "")).strip().lower().replace(" ", "_")
            if not npc_id:
                continue
            conn.execute(
                """INSERT INTO school_directory
                   (session_id, npc_id, name, gender, race, role, grade, club, clique, primary_facility, secondary_facility, sibling_name, personality_summary, is_hydrated, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(session_id, npc_id) DO UPDATE SET
                   name=excluded.name,
                   gender=COALESCE(NULLIF(excluded.gender, ''), school_directory.gender),
                   race=COALESCE(NULLIF(excluded.race, ''), school_directory.race),
                   role=excluded.role,
                   grade=excluded.grade,
                   club=excluded.club,
                   clique=excluded.clique,
                   primary_facility=excluded.primary_facility,
                   secondary_facility=excluded.secondary_facility,
                   sibling_name=excluded.sibling_name,
                   personality_summary=excluded.personality_summary""",
                (
                    session_id,
                    npc_id,
                    char.get("name", "").strip(),
                    char.get("gender", "").strip(),
                    char.get("race", "").strip(),
                    char.get("role", "").strip(),
                    char.get("grade", "Student").strip(),
                    char.get("club", "").strip(),
                    char.get("clique", "").strip(),
                    char.get("primary_facility", "").strip(),
                    char.get("secondary_facility", "").strip(),
                    char.get("sibling_name", "").strip(),
                    char.get("personality_summary", "").strip(),
                    int(bool(char.get("is_hydrated", 0))),
                    now
                )
            )
    return True

def get_school_roster(session_id: int) -> list[dict]:
    """Returns the full school directory roster for a session."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM school_directory WHERE session_id=? ORDER BY id ASC",
            (session_id,)
        ).fetchall()
        return [dict(r) for r in rows]

def get_anomalous_agent_roster(session_id: int) -> list[dict]:
    """Returns the anomalous special agents roster for a session if present."""
    if not session_id:
        return []
    sess = db.get_session(session_id)
    if not sess:
        return []
    roster = sess.get("anomalous_agent_roster")
    if not isinstance(roster, list) and isinstance(sess.get("extra"), dict):
        roster = sess["extra"].get("anomalous_agent_roster")
    return list(roster) if isinstance(roster, list) else []

def get_school_characters_by_facility(session_id: int, location_str: str, limit: int = 3, allow_off_campus: bool = False) -> list[dict]:
    """
    Returns characters stationed at or frequenting the specified facility/room.
    Matches against primary_facility, secondary_facility, or location leaf tokens.
    If allow_off_campus is True, also permits matching recognized town youth hangout nodes
    during extracurricular or weekend hours.
    """
    if not location_str or not session_id:
        return []

    loc_clean = str(location_str).strip()
    loc_parts = [p.strip() for p in re.split(r'➔|->|>|→', loc_clean) if p.strip()]
    leaf = loc_parts[-1] if loc_parts else loc_clean
    primary_place = loc_parts[1] if len(loc_parts) > 1 else leaf

    parsed = None
    is_campus = True
    try:
        from mechanics.world.locations import (
            parse_tiered_location,
            get_session_school_name,
            get_session_athletics_complex_name,
            get_session_student_commons_name,
            get_session_cultural_arts_name,
            get_session_abandoned_campus_name,
            is_school_scenario
        )
        sess = db.get_session(session_id)
        scen = sess.get("scenario", "high_school_drama") if sess else "high_school_drama"
        if is_school_scenario(scen):
            campus_zones = [
                get_session_school_name(session_id, scen),
                get_session_athletics_complex_name(session_id, scen),
                get_session_student_commons_name(session_id, scen),
                get_session_cultural_arts_name(session_id, scen),
                get_session_abandoned_campus_name(session_id, scen)
            ]
            parsed = parse_tiered_location(loc_clean, scen, session_id=session_id)
            loc_zone = parsed[0] if parsed else (loc_parts[0] if loc_parts else "")
            is_campus = any(cz and (cz.lower() in loc_zone.lower() or loc_zone.lower() in cz.lower()) for cz in campus_zones) or any(k in loc_zone.lower() for k in ("academy", "school", "athletics", "commons", "annex", "old campus"))
            if not is_campus and not allow_off_campus:
                return []
    except Exception:
        pass

    if not is_campus and allow_off_campus:
        is_youth_hangout = any(k in loc_clean.lower() for k in (
            "arcade", "game center", "velvet mug", "cafe", "coffee", "park", "pier",
            "beach", "convenience store", "karaoke", "lookout", "lake"
        ))
        if not is_youth_hangout:
            return []
        with get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM school_directory
                   WHERE session_id=? AND lower(grade) != 'faculty' AND lower(role) NOT LIKE '%teacher%' AND lower(role) NOT LIKE '%staff%'
                   ORDER BY is_hydrated ASC, id ASC LIMIT ?""",
                (session_id, limit)
            ).fetchall()
            return [dict(r) for r in rows]

    cand_places = []
    if parsed and parsed[2] and parsed[2] not in ("Main Area", ""):
        cand_places.append(parsed[2])
    cand_places.append(leaf)
    if primary_place != leaf and "athletics" not in primary_place.lower() and "commons" not in primary_place.lower() and "student union" not in primary_place.lower():
        cand_places.append(primary_place)
    if parsed and parsed[1] and parsed[1] not in ("Main Area", "") and "athletics" not in parsed[1].lower() and "commons" not in parsed[1].lower() and "student union" not in parsed[1].lower():
        cand_places.append(parsed[1])

    if any(k in leaf.lower() for k in ("classroom", "homeroom", "class ")) and "empty" not in leaf.lower():
        try:
            from mechanics.world.locations import get_session_classroom_name
            c_name = get_session_classroom_name(session_id, scen if 'scen' in locals() else "high_school_drama")
            if c_name:
                cand_places.append(c_name)
        except Exception:
            pass
        cand_places.append("Homeroom")

    for w in re.findall(r'[A-Za-z]+', leaf):
        if len(w) >= 4 and w.lower() not in ('room', 'wing', 'area', 'main', 'hall', 'spot', 'booth', 'floor', 'desk', 'court'):
            if w.lower() == 'classroom' and 'empty' not in leaf.lower():
                continue
            cand_places.append(w)
    for w in re.findall(r'[A-Za-z]+', primary_place):
        if len(w) >= 3 and w.lower() not in ('room', 'wing', 'area', 'main', 'hall', 'spot', 'booth', 'floor', 'desk', 'court', 'and', 'the'):
            cand_places.append(w)

    with get_conn() as conn:
        for cp in cand_places:
            if not cp or len(cp) < 3:
                continue
            kw_match = ""
            for tok in re.findall(r'[A-Za-z]+', cp):
                if len(tok) >= 4 and tok.lower() not in ('room', 'wing', 'area', 'main', 'hall', 'spot', 'booth', 'floor', 'desk', 'court', 'and', 'the'):
                    kw_match = tok.lower()
                    break

            rows = conn.execute(
                """SELECT * FROM school_directory
                   WHERE session_id=? AND (
                       primary_facility = ? OR
                       primary_facility LIKE ? OR
                       secondary_facility = ? OR
                       secondary_facility LIKE ?
                   )
                   ORDER BY 
                       CASE 
                           WHEN ? != '' AND lower(role) LIKE '%' || ? || '%' THEN 0 
                           WHEN lower(role) LIKE '%teacher%' OR lower(role) LIKE '%faculty%' OR lower(role) LIKE '%coach%' OR lower(role) LIKE '%nurse%' OR lower(role) LIKE '%librarian%' OR lower(role) LIKE '%instructor%' THEN 1 
                           ELSE 2 
                       END ASC,
                       is_hydrated ASC, id ASC LIMIT ?""",
                (session_id, cp, f"%{cp}%", cp, f"%{cp}%", kw_match, kw_match, limit)
            ).fetchall()
            if rows:
                return [dict(r) for r in rows]

        return []

def mark_school_character_hydrated(session_id: int, npc_id: str) -> bool:
    """Marks a character in the school directory as hydrated (active in contacts)."""
    clean_id = str(npc_id).strip().lower().replace(" ", "_")
    with get_conn() as conn:
        conn.execute(
            "UPDATE school_directory SET is_hydrated=1 WHERE session_id=? AND npc_id=?",
            (session_id, clean_id)
        )
    return True

def get_school_directory_batch(session_id: int) -> dict[str, dict]:
    """Fetch all school_directory entries for a session keyed by lowercase name in 1 query."""
    if not session_id:
        return {}
    result: dict[str, dict] = {}
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT name, gender, race, role, grade, club FROM school_directory WHERE session_id = ?",
            (int(session_id),),
        ).fetchall()
        for r in rows:
            if r["name"]:
                result[str(r["name"]).strip().lower()] = dict(r)
    return result

def _ensure_actor_physical_turn_snapshots_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS actor_physical_turn_snapshots (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id          INTEGER NOT NULL,
            turn_number         INTEGER NOT NULL,
            states_json         TEXT NOT NULL DEFAULT '[]',
            garments_json       TEXT NOT NULL DEFAULT '[]',
            room_meta_json      TEXT NOT NULL DEFAULT '{}',
            updated_at          REAL NOT NULL,
            UNIQUE(session_id, turn_number)
        )"""
    )
    cols = {
        (r["name"] if isinstance(r, sqlite3.Row) else r[1])
        for r in conn.execute("PRAGMA table_info(actor_physical_turn_snapshots)").fetchall()
    }
    if "room_meta_json" not in cols:
        conn.execute("ALTER TABLE actor_physical_turn_snapshots ADD COLUMN room_meta_json TEXT NOT NULL DEFAULT '{}'")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_phys_turn_snap_sess_turn ON actor_physical_turn_snapshots(session_id, turn_number)"
    )

def snapshot_session_physical_state_for_turn(
    session_id: int,
    turn_number: int,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Captures an exact per-turn snapshot of actor_physical_states, actor_garments, and room_meta_json for deterministic rollback."""
    if not session_id:
        return
    sid = int(session_id)
    t_num = int(turn_number)

    def _run(c: sqlite3.Connection) -> None:
        s_rows = c.execute(
            "SELECT * FROM actor_physical_states WHERE session_id = ? ORDER BY id ASC",
            (sid,),
        ).fetchall()
        states = [{k: v for k, v in dict(r).items() if k not in ("id", "session_id")} for r in s_rows]

        g_rows = c.execute(
            "SELECT * FROM actor_garments WHERE session_id = ? ORDER BY id ASC",
            (sid,),
        ).fetchall()
        garments = [{k: v for k, v in dict(r).items() if k not in ("id", "session_id")} for r in g_rows]

        room_meta: dict = {}
        try:
            p_row = c.execute("SELECT physical_state_json FROM sessions WHERE id = ?", (sid,)).fetchone()
            if p_row and p_row["physical_state_json"]:
                parsed = json.loads(p_row["physical_state_json"])
                if isinstance(parsed, dict):
                    room_meta = {k: v for k, v in parsed.items() if k != "actors"}
        except Exception:
            room_meta = {}

        now = time.time()
        sql = """INSERT INTO actor_physical_turn_snapshots
                 (session_id, turn_number, states_json, garments_json, room_meta_json, updated_at)
                 VALUES (?, ?, ?, ?, ?, ?)
                 ON CONFLICT(session_id, turn_number) DO UPDATE SET
                     states_json = excluded.states_json,
                     garments_json = excluded.garments_json,
                     room_meta_json = excluded.room_meta_json,
                     updated_at = excluded.updated_at"""
        params = (
            sid,
            t_num,
            json.dumps(states, default=str),
            json.dumps(garments, default=str),
            json.dumps(room_meta, default=str),
            now,
        )
        try:
            c.execute(sql, params)
        except sqlite3.OperationalError as exc:
            err_low = str(exc).lower()
            if "no such table: actor_physical_turn_snapshots" in err_low or "no such column: room_meta_json" in err_low:
                _ensure_actor_physical_turn_snapshots_table(c)
                c.execute(sql, params)
            else:
                raise

    if conn is not None:
        _run(conn)
    else:
        with get_conn() as c:
            _run(c)

def rollback_actor_physical_state_after_turn(
    session_id: int,
    turn_number: int,
    conn: sqlite3.Connection | None = None,
) -> dict:
    """Restores actor_physical_states, actor_garments, and sessions.physical_state_json to the latest snapshot <= turn_number and prunes future snapshots."""
    if not session_id:
        return {"physical_actors_restored": 0, "garments_restored": 0}
    sid = int(session_id)
    t_num = int(turn_number)

    def _run(c: sqlite3.Connection) -> dict:
        def _select_and_prune():
            sr = c.execute(
                """SELECT turn_number, states_json, garments_json, room_meta_json
                   FROM actor_physical_turn_snapshots
                   WHERE session_id = ? AND turn_number <= ?
                   ORDER BY turn_number DESC
                   LIMIT 1""",
                (sid, t_num),
            ).fetchone()
            dc = c.execute(
                "DELETE FROM actor_physical_turn_snapshots WHERE session_id = ? AND turn_number > ?",
                (sid, t_num),
            )
            return sr, int(dc.rowcount or 0)

        try:
            snap_row, pruned_future = _select_and_prune()
        except sqlite3.OperationalError as exc:
            err_low = str(exc).lower()
            if "no such table: actor_physical_turn_snapshots" in err_low:
                return {"physical_actors_restored": 0, "garments_restored": 0}
            if "no such column: room_meta_json" in err_low:
                _ensure_actor_physical_turn_snapshots_table(c)
                snap_row, pruned_future = _select_and_prune()
            else:
                raise

        if snap_row is None:
            if pruned_future > 0:
                c.execute("DELETE FROM actor_physical_states WHERE session_id = ?", (sid,))
                c.execute("DELETE FROM actor_garments WHERE session_id = ?", (sid,))
                c.execute("UPDATE sessions SET physical_state_json = '{}' WHERE id = ?", (sid,))
            else:
                try:
                    p_row = c.execute("SELECT physical_state_json FROM sessions WHERE id = ?", (sid,)).fetchone()
                    if p_row and p_row["physical_state_json"]:
                        parsed = json.loads(p_row["physical_state_json"])
                        if isinstance(parsed, dict) and "actors" in parsed:
                            cleaned = {k: v for k, v in parsed.items() if k != "actors"}
                            c.execute(
                                "UPDATE sessions SET physical_state_json = ? WHERE id = ?",
                                (json.dumps(cleaned, default=str), sid),
                            )
                except Exception:
                    pass
            return {"physical_actors_restored": 0, "garments_restored": 0}

        try:
            states = json.loads(snap_row["states_json"] or "[]")
        except Exception:
            states = []
        try:
            garments = json.loads(snap_row["garments_json"] or "[]")
        except Exception:
            garments = []
        try:
            raw_room_meta = snap_row["room_meta_json"] if "room_meta_json" in snap_row.keys() else "{}"
            room_meta = json.loads(raw_room_meta or "{}")
            if not isinstance(room_meta, dict):
                room_meta = {}
            else:
                room_meta = {k: v for k, v in room_meta.items() if k != "actors"}
        except Exception:
            room_meta = {}

        c.execute("DELETE FROM actor_physical_states WHERE session_id = ?", (sid,))
        c.execute("DELETE FROM actor_garments WHERE session_id = ?", (sid,))
        c.execute(
            "UPDATE sessions SET physical_state_json = ? WHERE id = ?",
            (json.dumps(room_meta, default=str), sid),
        )

        restored_states = _restore_session_table_rows(c, "actor_physical_states", sid, states)
        restored_garments = _restore_session_table_rows(c, "actor_garments", sid, garments)

        return {
            "physical_actors_restored": restored_states,
            "garments_restored": restored_garments,
        }

    if conn is not None:
        return _run(conn)
    with get_conn() as c:
        return _run(c)
