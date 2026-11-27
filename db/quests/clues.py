"""Caseboard clue persistence, 20-clue tiered cap, verification, and deduction breakthrough shortcuts."""
from __future__ import annotations

import json
import re
import sqlite3
import time
from typing import Any, Optional

import db
from ..core import UnitOfWork, get_conn
from .core import append_quest_note_flag_in_db, get_session_quests
from .epilogue import advance_waypoint


def add_session_clue(
    session_id: int,
    title: str,
    lead_text: str,
    category: str = "physical",
    source_location: str = "",
    linked_npc: str = "",
    quest_id: str = "",
    chapter: int = 1,
    is_verified: int = 0,
    deduction_parents: list = None,
    turn_created: int | None = None,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    """Inserts a new structured evidence record into session_clues with deduplication check."""
    if not title or not lead_text:
        return 0
    clean_title = title.strip()[:100]
    clean_lead = lead_text.strip()
    clean_cat = category.strip().lower() if category else "physical"
    if clean_cat not in ("physical", "testimonial", "digital", "document", "deduction"):
        clean_cat = "physical"
    parents_json = json.dumps(deduction_parents) if isinstance(deduction_parents, list) else "[]"
    now = time.time()

    def _execute(c: sqlite3.Connection) -> int:
        nonlocal turn_created
        if turn_created is None:
            try:
                s_row = c.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
                turn_created = int(db.infer_session_turn(dict(s_row))) if s_row else 1
            except Exception:
                turn_created = 1

        rows = c.execute(
            "SELECT * FROM session_clues WHERE session_id=? ORDER BY created_at ASC, id ASC",
            (session_id,),
        ).fetchall()
        t_clean_low = clean_title.lower()
        l_clean_low = clean_lead.lower()
        for r in rows:
            r_title_low = str(r["title"]).lower()
            r_lead_low = str(r["lead_text"]).lower()
            if r_title_low == t_clean_low or r_lead_low == l_clean_low:
                return r["id"]
            if l_clean_low in r_lead_low or r_lead_low in l_clean_low:
                return r["id"]

        cur = c.execute(
            """INSERT INTO session_clues
               (session_id, quest_id, chapter, title, lead_text, category, source_location, linked_npc, is_verified, deduction_parents_json, turn_created, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                quest_id or "",
                chapter or 1,
                clean_title,
                clean_lead,
                clean_cat,
                source_location or "",
                linked_npc or "",
                int(is_verified),
                parents_json,
                int(turn_created or 1),
                now,
                now,
            ),
        )
        new_id = cur.lastrowid

        # D12 Smart Tiered 20-Clue Caseboard Cap
        try:
            all_rows = c.execute(
                "SELECT * FROM session_clues WHERE session_id=? ORDER BY created_at ASC, id ASC",
                (session_id,),
            ).fetchall()
            consumed_by_parent: set[int] = set()
            for r in all_rows:
                try:
                    for pid in json.loads(r["deduction_parents_json"] or "[]") or []:
                        consumed_by_parent.add(int(pid))
                except Exception:
                    pass

            active_unconsumed = []
            for r in all_rows:
                rd = dict(r)
                if rd.get("category") == "deduction":
                    continue
                if bool(rd.get("is_consumed")) or rd["id"] in consumed_by_parent:
                    continue
                active_unconsumed.append(rd)

            if len(active_unconsumed) > 20:
                sq_rows = c.execute(
                    "SELECT quest_id FROM quests WHERE session_id=? AND status='Active' AND is_story_quest=1",
                    (session_id,),
                ).fetchall()
                active_sq_ids = {str(sr["quest_id"]) for sr in sq_rows if sr["quest_id"]}
                cur_ch_val = int(chapter or 1)
                evictable = [
                    rd
                    for rd in active_unconsumed
                    if rd["id"] != new_id
                    and rd.get("category") != "deduction"
                    and str(rd.get("quest_id") or "") not in active_sq_ids
                ]
                evictable.sort(
                    key=lambda rd: (
                        0
                        if int(rd.get("chapter") or 1) < cur_ch_val
                        else (1 if not rd.get("quest_id") else 2),
                        float(rd.get("created_at") or 0.0),
                        int(rd["id"]),
                    )
                )
                overflow = len(active_unconsumed) - 20
                for target_rd in evictable[:overflow]:
                    c.execute(
                        "UPDATE session_clues SET is_consumed=1, updated_at=? WHERE id=?",
                        (now, target_rd["id"]),
                    )
        except sqlite3.OperationalError:
            pass

        return new_id

    if conn is not None:
        return _execute(conn)
    with get_conn() as local_conn:
        return _execute(local_conn)


def get_session_clues(
    session_id: int,
    chapter: int = None,
    linked_npc: str = None,
    category: str = None,
    is_verified: int = None,
) -> list[dict]:
    """Retrieves evidence records from session_clues with optional filters."""
    query = "SELECT * FROM session_clues WHERE session_id=?"
    params = [session_id]
    if chapter is not None:
        query += " AND chapter=?"
        params.append(chapter)
    if linked_npc:
        query += " AND (LOWER(linked_npc)=? OR LOWER(linked_npc) LIKE ?)"
        params.extend([linked_npc.strip().lower(), f"%{linked_npc.strip().lower()}%"])
    if category:
        query += " AND category=?"
        params.append(category.strip().lower())
    if is_verified is not None:
        query += " AND is_verified=?"
        params.append(int(is_verified))
    query += " ORDER BY is_verified DESC, id DESC"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        consumed_ids = set()
        for r in rows:
            try:
                parents = json.loads(r["deduction_parents_json"] or "[]")
                consumed_ids.update(parents)
            except Exception:
                pass

        results = []
        for r in rows:
            d = dict(r)
            try:
                d["deduction_parents"] = json.loads(d.get("deduction_parents_json") or "[]")
            except Exception:
                d["deduction_parents"] = []
            d["is_consumed"] = bool(d.get("is_consumed")) or (d["id"] in consumed_ids)
            results.append(d)
        return results


def get_session_clue_by_id(
    clue_id: int, conn: Optional[sqlite3.Connection] = None
) -> dict | None:
    """Fetches a single evidence record by ID."""

    def _execute(c: sqlite3.Connection):
        row = c.execute("SELECT * FROM session_clues WHERE id=?", (clue_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["deduction_parents"] = json.loads(d.get("deduction_parents_json") or "[]")
        except Exception:
            d["deduction_parents"] = []

        consumed = False
        all_parents_rows = c.execute(
            "SELECT deduction_parents_json FROM session_clues WHERE session_id=?",
            (d["session_id"],),
        ).fetchall()
        for pr in all_parents_rows:
            try:
                p_list = json.loads(pr[0] or "[]")
                if d["id"] in p_list:
                    consumed = True
                    break
            except Exception:
                pass
        d["is_consumed"] = bool(d.get("is_consumed")) or consumed
        return d

    if conn is not None:
        return _execute(conn)
    with get_conn() as local_conn:
        return _execute(local_conn)


def verify_session_clue(clue_id: int, conn: Optional[sqlite3.Connection] = None, session_id: Optional[int] = None) -> bool:
    """Marks an evidence record as verified."""
    def _execute(c: sqlite3.Connection) -> bool:
        if session_id is not None:
            cur = c.execute(
                "UPDATE session_clues SET is_verified=1, updated_at=? WHERE id=? AND session_id=?",
                (time.time(), clue_id, int(session_id)),
            )
        else:
            cur = c.execute(
                "UPDATE session_clues SET is_verified=1, updated_at=? WHERE id=?",
                (time.time(), clue_id),
            )
        return cur.rowcount > 0

    if conn is not None:
        return _execute(conn)
    with get_conn() as c:
        return _execute(c)


def apply_caseboard_breakthrough_to_quests(
    session_id: int,
    clue_ids: list[int],
    title: str,
    lead_text: str,
) -> dict:
    """Checks active quests and sub-objectives against a synthesized Caseboard deduction."""
    matched_qids = []
    advanced_qids = []

    clean_pids: list[int] = []
    for pid in clue_ids or []:
        try:
            clean_pids.append(int(pid))
        except (TypeError, ValueError):
            pass

    parent_qids: set[str] = set()
    parent_npcs: set[str] = set()

    combined_text = f"{title} {lead_text}".lower()
    text_words = set(re.findall(r"\b[a-z]{4,}\b", combined_text)) - {
        "this",
        "that",
        "with",
        "from",
        "have",
        "been",
        "were",
        "what",
        "some",
        "discovered",
        "evidence",
    }

    with UnitOfWork() as conn:
        if clean_pids:
            placeholders = ",".join("?" for _ in clean_pids)
            p_rows = conn.execute(
                f"SELECT quest_id, linked_npc FROM session_clues WHERE session_id=? AND id IN ({placeholders})",
                (session_id, *clean_pids),
            ).fetchall()
            for cr in p_rows:
                if cr["quest_id"] and str(cr["quest_id"]).strip():
                    parent_qids.add(str(cr["quest_id"]).strip())
                if cr["linked_npc"] and str(cr["linked_npc"]).strip():
                    parent_npcs.add(str(cr["linked_npc"]).strip().lower())

        active_quests = get_session_quests(session_id, status="Active") or []
        wps_by_key: dict[tuple[str, Any], list[dict]] = {}
        wp_all_rows = conn.execute(
            "SELECT * FROM quest_waypoints WHERE session_id=? ORDER BY stage_index ASC",
            (session_id,),
        ).fetchall()
        for wr in wp_all_rows:
            wd = dict(wr)
            wps_by_key.setdefault(
                (str(wd.get("quest_id") or ""), wd.get("sub_obj_id")), []
            ).append(wd)

        for q in active_quests:
            qid = q.get("quest_id", "")
            if not qid:
                continue
            all_wps = wps_by_key.get((qid, None), [])
            active_wp = next((w for w in all_wps if w.get("status") == "active"), None)

            is_match = False
            if qid in parent_qids:
                is_match = True
            elif parent_npcs and any(
                str(w.get("target_npc", "")).strip().lower() in parent_npcs for w in all_wps
            ):
                is_match = True
            elif parent_npcs and (
                str(q.get("client_npc", "")).strip().lower() in parent_npcs
                or str(q.get("target_npc", "")).strip().lower() in parent_npcs
            ):
                is_match = True
            elif q.get("blueprint_id") in ("INVESTIGATION", "SOCIAL_MANIPULATION") or q.get(
                "is_story_quest"
            ):
                q_text = f"{q.get('title', '')} {q.get('objective', '')}".lower()
                q_words = set(re.findall(r"\b[a-z]{4,}\b", q_text))
                if len(text_words & q_words) >= 1:
                    is_match = True

            if is_match:
                matched_qids.append(qid)
                append_quest_note_flag_in_db(session_id, qid, "caseboard_breakthrough", "1")

                if (
                    active_wp
                    and int(active_wp.get("stage_index", 1)) == 1
                    and len(all_wps) >= 2
                ):
                    advance_waypoint(session_id, qid, 1, None)
                    advanced_qids.append(qid)

                sub_objs = q.get("sub_objectives") or []
                if isinstance(sub_objs, list) and sub_objs:
                    for so in sub_objs:
                        if not isinstance(so, dict) or so.get("completed"):
                            continue
                        so_id = so.get("id")
                        if so_id is None:
                            continue
                        so_all_wps = wps_by_key.get((qid, so_id), [])
                        so_wp = next(
                            (w for w in so_all_wps if w.get("status") == "active"), None
                        )
                        if (
                            so_wp
                            and int(so_wp.get("stage_index", 1)) == 1
                            and len(so_all_wps) >= 2
                        ):
                            advance_waypoint(session_id, qid, 1, so_id)
                            if qid not in advanced_qids:
                                advanced_qids.append(qid)

    return {"matched_quest_ids": matched_qids, "advanced_quest_ids": advanced_qids}


def synthesize_deduction_clue(
    session_id: int,
    clue_ids: list[int],
    title: str,
    lead_text: str,
    chapter: int = 1,
    turn_created: int | None = None,
) -> int:
    """Creates a verified deduction breakthrough linking parent clues and applying quest breakthrough shortcuts."""
    clean_ids = list(dict.fromkeys(int(pid) for pid in (clue_ids or []) if pid is not None))
    with UnitOfWork() as conn:
        inherited_npc = ""
        inherited_qid = ""
        by_id: dict[int, sqlite3.Row] = {}
        if clean_ids:
            rows = conn.execute(
                "SELECT id, linked_npc, quest_id FROM session_clues "
                "WHERE session_id=? AND id IN (SELECT value FROM json_each(?))",
                (session_id, json.dumps(clean_ids)),
            ).fetchall()
            by_id = {int(r["id"]): r for r in rows}
        valid_ids = [pid for pid in clean_ids if pid in by_id]
        for pid in valid_ids:
            cl = by_id[pid]
            if not inherited_npc and cl["linked_npc"]:
                inherited_npc = str(cl["linked_npc"]).strip()
            if not inherited_qid and cl["quest_id"]:
                inherited_qid = str(cl["quest_id"]).strip()

        cid = add_session_clue(
            session_id=session_id,
            title=title,
            lead_text=lead_text,
            category="deduction",
            source_location="Mind Palace / Caseboard",
            linked_npc=inherited_npc,
            quest_id=inherited_qid,
            chapter=chapter,
            is_verified=1,
            deduction_parents=valid_ids,
            turn_created=turn_created,
            conn=conn,
        )
        if valid_ids:
            now_ts = time.time()
            valid_json = json.dumps(valid_ids)
            try:
                conn.execute(
                    "UPDATE session_clues SET is_verified=1, is_consumed=1, updated_at=? "
                    "WHERE session_id=? AND id IN (SELECT value FROM json_each(?))",
                    (now_ts, session_id, valid_json),
                )
            except sqlite3.OperationalError as exc:
                if "no such column" not in str(exc).lower():
                    raise
                conn.execute(
                    "UPDATE session_clues SET is_verified=1, updated_at=? "
                    "WHERE session_id=? AND id IN (SELECT value FROM json_each(?))",
                    (now_ts, session_id, valid_json),
                )

        apply_caseboard_breakthrough_to_quests(session_id, valid_ids, title, lead_text)
        return cid
