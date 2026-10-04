import db
import asyncio
import json
import time
from contextlib import contextmanager
import re
import sqlite3
from config import DB_PATH
import character_data as cd
from .core import *
from .core import _delete_session_records, _to_str, _is_suspicious_entity_text, _safe_int_db, _sanitize_npcs_list

_TRANSIENT_SUB_OBJ_KEYS = {
    "waypoints",
    "active_waypoint",
    "stage_label",
    "stage_index",
    "total_stages",
    "completed_stages",
}

def _normalize_loc_arrow(loc: str) -> str:
    if not loc:
        return ""
    return re.sub(r"\s*->\s*", " ➔ ", str(loc).strip())

def _clean_sub_objectives_for_storage(sub_objectives: list | str | None) -> str:
    if isinstance(sub_objectives, list):
        cleaned = []
        for so in sub_objectives:
            if isinstance(so, dict):
                cleaned.append({k: v for k, v in so.items() if k not in _TRANSIENT_SUB_OBJ_KEYS})
            else:
                cleaned.append(so)
        return json.dumps(cleaned)
    return sub_objectives or "[]"

def upsert_quest(session_id: int, quest_id: str, quest_type: str, title: str,
                 objective: str, progress: str = "", current_clues: str = "",
                 status: str = "Active", reward_xp: int = 100, reward_gold: int = 25,
                 reward_stat_points: int = 0, reward_item: str = "",
                 is_story_quest: int = 0, clues_required: int = 3,
                 quest_notes: str = None, sub_objectives: list | str = None) -> dict:
    now = time.time()
    sub_obj_str = _clean_sub_objectives_for_storage(sub_objectives)
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id, reward_claimed FROM quests WHERE session_id=? AND quest_id=?",
            (session_id, quest_id)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE quests SET
                   quest_type=?, title=?, objective=?, progress=?, current_clues=?,
                   status=?, reward_xp=?, reward_gold=?, reward_stat_points=?, reward_item=?,
                   is_story_quest=?, clues_required=?,
                   quest_notes=COALESCE(?, quest_notes),
                   sub_objectives_json=CASE WHEN ? != '[]' THEN ? ELSE sub_objectives_json END,
                   updated_at=?
                   WHERE id=?""",
                (quest_type or "Main Quest", title, objective, progress or "", current_clues or "",
                 status or "Active", reward_xp, reward_gold, reward_stat_points, reward_item or "",
                 is_story_quest, clues_required,
                 quest_notes, sub_obj_str, sub_obj_str, now, existing["id"])
            )
        else:
            conn.execute(
                """INSERT INTO quests
                   (session_id, quest_id, quest_type, title, objective, progress, current_clues,
                    status, reward_xp, reward_gold, reward_stat_points, reward_item,
                    is_story_quest, clues_required, reward_claimed, quest_notes,
                    sub_objectives_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,?,?,?)""",
                (session_id, quest_id, quest_type or "Main Quest", title, objective, progress or "",
                 current_clues or "", status or "Active", reward_xp, reward_gold, reward_stat_points,
                 reward_item or "", is_story_quest, clues_required, quest_notes or "",
                 sub_obj_str, now, now)
            )

    return get_quest_by_id(session_id, quest_id)

def _enrich_quest_dict(row) -> dict | None:
    if not row:
        return None
    d = dict(row)
    if d.get("sub_objectives_json"):
        try:
            raw_sos = json.loads(d["sub_objectives_json"])
            d["sub_objectives"] = [dict(so) if isinstance(so, dict) else so for so in (raw_sos or [])]
        except Exception:
            d["sub_objectives"] = []
    else:
        d["sub_objectives"] = []

    session_id = d.get("session_id")
    quest_id = d.get("quest_id")
    all_wps = []
    if session_id and quest_id:
        try:
            with get_conn() as conn:
                wp_rows = conn.execute(
                    """SELECT * FROM quest_waypoints
                       WHERE session_id=? AND quest_id=?
                       ORDER BY COALESCE(sub_obj_id, 0) ASC, stage_index ASC""",
                    (session_id, quest_id)
                ).fetchall()
                for wr in wp_rows:
                    w_dict = dict(wr)
                    if w_dict.get("target_location"):
                        w_dict["target_location"] = _normalize_loc_arrow(w_dict["target_location"])
                    all_wps.append(w_dict)
        except Exception:
            all_wps = []

    if d["sub_objectives"]:
        for idx, so in enumerate(d["sub_objectives"]):
            if not isinstance(so, dict):
                continue
            so_id = so.get("id", idx + 1)
            so_wps = [
                w for w in all_wps
                if w.get("sub_obj_id") is not None and _safe_int_db(w.get("sub_obj_id"), -1) == _safe_int_db(so_id, -2)
            ]
            if so_wps:
                active_wp = next((w for w in so_wps if w.get("status") == "active"), None)
                if not active_wp and not so.get("completed"):
                    active_wp = next((w for w in so_wps if w.get("status") == "locked"), so_wps[0])
                elif not active_wp and so.get("completed"):
                    active_wp = so_wps[-1]
                so["waypoints"] = so_wps
                so["active_waypoint"] = active_wp
                so["target_location"] = (active_wp.get("target_location") or "") if active_wp else _normalize_loc_arrow(so.get("target_location") or "")
                so["target_npc"] = (active_wp.get("target_npc") or "") if active_wp else (so.get("target_npc") or "")
                so["stage_label"] = (active_wp.get("stage_label") or "") if active_wp else ""
                so["stage_index"] = int(active_wp.get("stage_index", 1) or 1) if active_wp else 1
                so["total_stages"] = len(so_wps)
                so["completed_stages"] = sum(1 for w in so_wps if w.get("status") == "completed")
            elif so.get("target_location"):
                so["target_location"] = _normalize_loc_arrow(so["target_location"])

        all_so_done = all(isinstance(so, dict) and bool(so.get("completed")) for so in d["sub_objectives"])
        if all_so_done and d.get("status") == "Active":
            d["climax_ready"] = True

        active_so_wps = [
            so["active_waypoint"]
            for so in d["sub_objectives"]
            if isinstance(so, dict) and not so.get("completed") and so.get("active_waypoint")
        ]
        if all_wps:
            d["waypoints"] = all_wps
            d["active_waypoints"] = active_so_wps
            if active_so_wps:
                d["active_waypoint"] = active_so_wps[0]
                if not d.get("target_location"):
                    d["target_location"] = active_so_wps[0].get("target_location", "")
                if not d.get("target_npc"):
                    d["target_npc"] = active_so_wps[0].get("target_npc", "")
                if not d.get("stage_label"):
                    d["stage_label"] = active_so_wps[0].get("stage_label", "")
    elif all_wps:
        quest_wps = [w for w in all_wps if w.get("sub_obj_id") is None] or all_wps
        d["waypoints"] = quest_wps
        active_wp = next((w for w in quest_wps if w.get("status") == "active"), None)
        if not active_wp and d.get("status") != "Completed":
            active_wp = next((w for w in quest_wps if w.get("status") == "locked"), quest_wps[0])
        elif not active_wp and quest_wps:
            active_wp = quest_wps[-1]
        d["active_waypoint"] = active_wp
        d["active_waypoints"] = [active_wp] if active_wp and active_wp.get("status") == "active" else []
        if active_wp:
            d["target_location"] = active_wp.get("target_location") or _normalize_loc_arrow(d.get("target_location") or "")
            d["target_npc"] = active_wp.get("target_npc") or ""
            d["stage_label"] = active_wp.get("stage_label") or ""
        d["stages"] = [
            {
                "stage_index": int(w.get("stage_index", i + 1) or (i + 1)),
                "stage_label": w.get("stage_label", ""),
                "text": w.get("stage_label", ""),
                "target_location": w.get("target_location", ""),
                "target_npc": w.get("target_npc", ""),
                "completion_trigger": w.get("completion_trigger", "arrival"),
                "resource_target": int(w.get("resource_target", 0) or 0),
                "resource_collected": int(w.get("resource_collected", 0) or 0),
                "status": w.get("status", "locked"),
                "completed": w.get("status") == "completed",
            }
            for i, w in enumerate(quest_wps)
        ]

    return d

def get_active_story_quest(session_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM quests
               WHERE session_id=? AND (is_story_quest=1 OR quest_type='Story Quest' OR quest_type='Main Quest')
               AND status='Active' ORDER BY updated_at DESC""",
            (session_id,)
        ).fetchone()
    return _enrich_quest_dict(row)

def get_session_quests(session_id: int, status: str = None) -> list[dict]:
    with get_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM quests WHERE session_id=? AND status=? ORDER BY updated_at DESC",
                (session_id, status)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM quests WHERE session_id=? ORDER BY updated_at DESC",
                (session_id,)
            ).fetchall()
    return [_enrich_quest_dict(r) for r in rows if r]

get_quests = get_session_quests

def get_quest_by_id(session_id: int, quest_id: str) -> dict | None:

    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM quests WHERE session_id=? AND quest_id=?",
            (session_id, quest_id)
        ).fetchone()
    return _enrich_quest_dict(row)

def update_session_campaign_goals(session_id: int, goals: list):
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET campaign_end_goals_json=?, updated_at=? WHERE id=?",
            (json.dumps(goals), time.time(), session_id)
        )

def get_session_campaign_goals(session_id: int) -> list:
    session = db.get_session(session_id)
    if not session or not session.get("campaign_end_goals_json"):
        return []
    try:
        val = json.loads(session["campaign_end_goals_json"])
        return val if isinstance(val, list) else []
    except Exception:
        return []

def set_session_chapter(session_id: int, chapter: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE sessions SET current_chapter=?, updated_at=? WHERE id=?",
            (chapter, time.time(), session_id)
        )

def get_session_chapter(session_id: int) -> int:
    session = db.get_session(session_id)
    if not session:
        return 1
    return session.get("current_chapter", 1) or 1

def update_quest_status(session_id: int, quest_id: str, status: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE quests SET status=?, updated_at=? WHERE session_id=? AND quest_id=?",
            (status, time.time(), session_id, quest_id)
        )

def claim_quest_reward(session_id: int, quest_id: str, party_user_ids: list[int]) -> dict:
    quest = get_quest_by_id(session_id, quest_id)
    if not quest or quest.get("reward_claimed"):
        return {"already_claimed": True}

    rxp = quest.get("reward_xp", 100)
    rgold = quest.get("reward_gold", 25)
    ritem = quest.get("reward_item") or ""

    levels_gained_by_user = {}
    for uid in party_user_ids:
        lvl_ups = db.add_xp(uid, rxp)
        if lvl_ups:
            levels_gained_by_user[uid] = lvl_ups

        db.apply_hp_mp_delta(uid, 0, 0, rgold)

        if ritem:
            db.add_item(uid, ritem, "Quest", "Quest Reward", 1)

    faction_rep_gained = 0
    notes = quest.get("quest_notes") or ""
    if notes.startswith("faction:"):
        try:
            parts = notes.split("|")
            faction_id = parts[0].split(":")[1] if len(parts) > 0 and ":" in parts[0] else ""
            for p in parts:
                if p.startswith("rep_reward:"):
                    faction_rep_gained = int(p.split(":")[1])
            if faction_id and faction_rep_gained > 0:
                db.upsert_faction(session_id, faction_id, delta_score=faction_rep_gained, notes="Faction bounty completed")
        except Exception:
            pass
    with get_conn() as conn:
        conn.execute(
            "UPDATE quests SET reward_claimed=1, status='Completed', updated_at=? WHERE session_id=? AND quest_id=?",
            (time.time(), session_id, quest_id)
        )

    return {
        "claimed": True,
        "title": quest["title"],
        "quest_type": quest["quest_type"],
        "is_story_quest": bool(quest.get("is_story_quest") or quest.get("quest_type") in ("Story Quest", "Main Quest")),
        "xp": rxp,
        "gold": rgold,
        "item": ritem,
        "levels_gained": levels_gained_by_user
    }

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
    deduction_parents: list = None
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

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, lead_text FROM session_clues WHERE session_id=?",
            (session_id,)
        ).fetchall()
        t_clean_low = clean_title.lower()
        l_clean_low = clean_lead.lower()
        for r in rows:
            r_title_low = str(r["title"]).lower()
            r_lead_low = str(r["lead_text"]).lower()
            if r_title_low == t_clean_low or r_lead_low == l_clean_low:
                return r["id"]
            if clean_lead in r_lead_low or r_lead_low in clean_lead:
                return r["id"]

        cur = conn.execute(
            """INSERT INTO session_clues
               (session_id, quest_id, chapter, title, lead_text, category, source_location, linked_npc, is_verified, deduction_parents_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, quest_id or "", chapter or 1, clean_title, clean_lead, clean_cat, source_location or "", linked_npc or "", int(is_verified), parents_json, now, now)
        )
        return cur.lastrowid

def get_session_clues(
    session_id: int,
    chapter: int = None,
    linked_npc: str = None,
    category: str = None,
    is_verified: int = None
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
            d["is_consumed"] = d["id"] in consumed_ids
            results.append(d)
        return results

def get_session_clue_by_id(clue_id: int) -> dict | None:
    """Fetches a single evidence record by ID."""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM session_clues WHERE id=?", (clue_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["deduction_parents"] = json.loads(d.get("deduction_parents_json") or "[]")
        except Exception:
            d["deduction_parents"] = []
            
        # Check if this clue was consumed by any other deduction
        consumed = False
        all_parents_rows = conn.execute("SELECT deduction_parents_json FROM session_clues WHERE session_id=?", (d["session_id"],)).fetchall()
        for pr in all_parents_rows:
            try:
                p_list = json.loads(pr[0] or "[]")
                if d["id"] in p_list:
                    consumed = True
                    break
            except Exception:
                pass
        d["is_consumed"] = consumed
        return d

def verify_session_clue(clue_id: int) -> bool:
    """Marks an evidence record as verified."""
    with get_conn() as conn:
        cur = conn.execute("UPDATE session_clues SET is_verified=1, updated_at=? WHERE id=?", (time.time(), clue_id))
        return cur.rowcount > 0

def delete_session_clue(clue_id: int) -> bool:
    """Deletes an evidence record by ID."""
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM session_clues WHERE id=?", (clue_id,))
        return cur.rowcount > 0

def synthesize_deduction_clue(
    session_id: int,
    clue_ids: list[int],
    title: str,
    lead_text: str,
    chapter: int = 1
) -> int:
    """Creates a verified deduction breakthrough linking parent clues."""
    cid = add_session_clue(
        session_id=session_id,
        title=title,
        lead_text=lead_text,
        category="deduction",
        source_location="Mind Palace / Caseboard",
        linked_npc="",
        chapter=chapter,
        is_verified=1,
        deduction_parents=clue_ids
    )
    for parent_id in clue_ids:
        verify_session_clue(parent_id)
    return cid

def save_quest_waypoints(session_id: int, quest_id: str, waypoints: list, sub_obj_id: int | None = None):
    """Bulk upsert waypoints for a quest or sub-objective.
    Stage 1 starts as 'active', all others start as 'locked'.
    sub_obj_id=None means the waypoints belong to the whole quest (bounties).
    sub_obj_id=N means they belong to Story Quest sub-objective N.
    """
    if not waypoints:
        return
    now = time.time()
    with get_conn() as conn:
        # Clear existing waypoints for this quest+sub_obj combo first
        if sub_obj_id is None:
            conn.execute(
                "DELETE FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL",
                (session_id, quest_id)
            )
        else:
            conn.execute(
                "DELETE FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id=?",
                (session_id, quest_id, sub_obj_id)
            )
        for i, wp in enumerate(waypoints):
            if not isinstance(wp, dict):
                continue
            stage_idx = int(wp.get("stage_index", i + 1))
            status = "active" if stage_idx == 1 else "locked"
            conn.execute(
                """INSERT OR REPLACE INTO quest_waypoints
                   (session_id, quest_id, sub_obj_id, stage_index, stage_label,
                    target_location, target_npc, completion_trigger,
                    resource_target, resource_collected, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id, quest_id, sub_obj_id, stage_idx,
                    str(wp.get("stage_label", ""))[:200],
                    str(wp.get("target_location", ""))[:200],
                    str(wp.get("target_npc", "") or "")[:100],
                    str(wp.get("completion_trigger", "arrival")),
                    int(wp.get("resource_target", 0)),
                    0,  # resource_collected always starts at 0
                    status, now, now
                )
            )

def get_active_waypoint(session_id: int, quest_id: str, sub_obj_id: int | None = None) -> dict | None:
    """Returns the first 'active' waypoint for this quest/sub-objective, or None."""
    with get_conn() as conn:
        if sub_obj_id is None:
            row = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND status='active'
                   ORDER BY stage_index ASC LIMIT 1""",
                (session_id, quest_id)
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND status='active'
                   ORDER BY stage_index ASC LIMIT 1""",
                (session_id, quest_id, sub_obj_id)
            ).fetchone()
        return dict(row) if row else None

def get_quest_waypoints(session_id: int, quest_id: str, sub_obj_id: int | None = None) -> list[dict]:
    """Returns all waypoints for this quest/sub-objective ordered by stage_index ASC."""
    with get_conn() as conn:
        if sub_obj_id is None:
            rows = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL
                   ORDER BY stage_index ASC""",
                (session_id, quest_id)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id=?
                   ORDER BY stage_index ASC""",
                (session_id, quest_id, sub_obj_id)
            ).fetchall()
        return [dict(r) for r in rows if r]

def advance_waypoint(session_id: int, quest_id: str, stage_index: int, sub_obj_id: int | None = None) -> dict | None:
    """Marks the given stage as 'completed', unlocks the next 'locked' stage to 'active'.
    Returns the newly-unlocked waypoint dict, or None if no more stages remain (quest chain done).
    """
    now = time.time()
    with get_conn() as conn:
        if sub_obj_id is None:
            conn.execute(
                "UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND stage_index=?",
                (now, session_id, quest_id, stage_index)
            )
            next_row = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND status='locked'
                   ORDER BY stage_index ASC LIMIT 1""",
                (session_id, quest_id)
            ).fetchone()
            if next_row:
                conn.execute(
                    "UPDATE quest_waypoints SET status='active', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND stage_index=?",
                    (now, session_id, quest_id, next_row["stage_index"])
                )
            tot_row = conn.execute(
                "SELECT COUNT(*) as c FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL",
                (session_id, quest_id)
            ).fetchone()
            don_row = conn.execute(
                "SELECT COUNT(*) as c FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND status='completed'",
                (session_id, quest_id)
            ).fetchone()
            tot = tot_row["c"] if tot_row else 0
            don = don_row["c"] if don_row else 0
            if tot > 0:
                conn.execute(
                    "UPDATE quests SET progress=?, updated_at=? WHERE session_id=? AND quest_id=?",
                    (f"{don}/{tot} Milestones", now, session_id, quest_id)
                )
        else:
            conn.execute(
                "UPDATE quest_waypoints SET status='completed', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND stage_index=?",
                (now, session_id, quest_id, sub_obj_id, stage_index)
            )
            next_row = conn.execute(
                """SELECT * FROM quest_waypoints
                   WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND status='locked'
                   ORDER BY stage_index ASC LIMIT 1""",
                (session_id, quest_id, sub_obj_id)
            ).fetchone()
            if next_row:
                conn.execute(
                    "UPDATE quest_waypoints SET status='active', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND stage_index=?",
                    (now, session_id, quest_id, sub_obj_id, next_row["stage_index"])
                )
        return dict(next_row) if next_row else None

def update_waypoint_resource_progress(session_id: int, quest_id: str, stage_index: int, delta: int, sub_obj_id: int | None = None) -> dict:
    """Increment resource_collected for a gathering waypoint.
    Returns {collected, target, complete} after update.
    """
    now = time.time()
    with get_conn() as conn:
        if sub_obj_id is None:
            conn.execute(
                "UPDATE quest_waypoints SET resource_collected=MAX(0, resource_collected+?), updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND stage_index=?",
                (delta, now, session_id, quest_id, stage_index)
            )
            row = conn.execute(
                "SELECT resource_collected, resource_target FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id IS NULL AND stage_index=?",
                (session_id, quest_id, stage_index)
            ).fetchone()
        else:
            conn.execute(
                "UPDATE quest_waypoints SET resource_collected=MAX(0, resource_collected+?), updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND stage_index=?",
                (delta, now, session_id, quest_id, sub_obj_id, stage_index)
            )
            row = conn.execute(
                "SELECT resource_collected, resource_target FROM quest_waypoints WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND stage_index=?",
                (session_id, quest_id, sub_obj_id, stage_index)
            ).fetchone()
        if row:
            collected = row["resource_collected"]
            target = row["resource_target"]
            return {"collected": collected, "target": target, "complete": target > 0 and collected >= target}
        return {"collected": 0, "target": 0, "complete": False}

def get_all_session_active_waypoints(session_id: int) -> list[dict]:
    """Returns all 'active' waypoints across all quests in a session.
    Used by the location UI to show quest markers on the travel menu.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT qw.*, q.title as quest_title, q.quest_type, q.is_story_quest, q.sub_objectives_json
               FROM quest_waypoints qw
               JOIN quests q ON qw.session_id = q.session_id AND qw.quest_id = q.quest_id
               WHERE qw.session_id=? AND qw.status='active' AND q.status='Active'
               ORDER BY qw.quest_id, qw.sub_obj_id, qw.stage_index""",
            (session_id,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            so_json = d.get("sub_objectives_json")
            sub_id = d.get("sub_obj_id")
            if so_json and sub_id is not None:
                try:
                    sos = json.loads(so_json) if isinstance(so_json, str) else so_json
                    if isinstance(sos, list):
                        if any(isinstance(s, dict) and int(s.get("id", -1)) == int(sub_id) and s.get("completed") for s in sos):
                            continue
                except Exception:
                    pass
            result.append(d)
        return result

def mark_sub_objective_completed_in_quest(session_id: int, quest_id: str, sub_obj_id: int):
    """Directly marks a Story Quest sub-objective as completed=True in sub_objectives_json.
    Called by the waypoint engine when all waypoint stages for that sub-obj are done.
    This is deterministic Python — no LLM JSON required.
    """
    quest = get_quest_by_id(session_id, quest_id)
    if not quest:
        return
    sub_objs = quest.get("sub_objectives") or []
    changed = False
    for so in sub_objs:
        if isinstance(so, dict) and int(so.get("id", -1)) == int(sub_obj_id):
            if not so.get("completed"):
                so["completed"] = True
                changed = True
            break
    if changed:
        now = time.time()
        with get_conn() as conn:
            conn.execute(
                "UPDATE quests SET sub_objectives_json=?, updated_at=? WHERE session_id=? AND quest_id=?",
                (_clean_sub_objectives_for_storage(sub_objs), now, session_id, quest_id)
            )
            # Unlock stage 1 of the next sub-objective (sub_obj_id + 1)
            conn.execute(
                "UPDATE quest_waypoints SET status='active', updated_at=? WHERE session_id=? AND quest_id=? AND sub_obj_id=? AND stage_index=1 AND status='locked'",
                (now, session_id, quest_id, int(sub_obj_id) + 1)
            )

