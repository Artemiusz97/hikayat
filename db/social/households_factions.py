from __future__ import annotations

import db
import json
import sqlite3
import time
from ..core import (get_conn)

def create_household(
    session_id: int,
    household_key: str,
    surname: str,
    father: dict | None = None,
    mother: dict | None = None,
    narrative_siblings: list | None = None,
    residence_location: str = ""
) -> int:
    """Creates a new normalized household entity in SQLite, returning its ID."""
    now = time.time()
    father_json = json.dumps(father or {})
    mother_json = json.dumps(mother or {})
    narrative_siblings_json = json.dumps(narrative_siblings or [])
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM households WHERE session_id = ? AND household_key = ?",
            (session_id, household_key)
        ).fetchone()
        if existing:
            return existing["id"]

        try:
            cursor = conn.execute(
                """INSERT INTO households (
                    session_id, household_key, surname, father_json, mother_json,
                    narrative_siblings_json, residence_location, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, household_key, surname, father_json, mother_json,
                 narrative_siblings_json, residence_location or "", now, now)
            )
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            existing = conn.execute(
                "SELECT id FROM households WHERE session_id = ? AND household_key = ?",
                (session_id, household_key)
            ).fetchone()
            if existing:
                return existing["id"]
            raise

def _parse_household_row(row: sqlite3.Row | dict) -> dict:
    """Deserializes JSON columns of a raw households row into a dict."""
    d = dict(row)
    try:
        d["father"] = json.loads(d.get("father_json") or "{}")
    except Exception:
        d["father"] = {}
    try:
        d["mother"] = json.loads(d.get("mother_json") or "{}")
    except Exception:
        d["mother"] = {}
    try:
        d["narrative_siblings"] = json.loads(d.get("narrative_siblings_json") or "[]")
        if not isinstance(d["narrative_siblings"], list):
            d["narrative_siblings"] = []
    except Exception:
        d["narrative_siblings"] = []
    return d

def get_household_by_id(household_id: int) -> dict | None:
    """Retrieves a household by its primary key ID."""
    if not household_id:
        return None
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM households WHERE id = ?", (household_id,)).fetchone()
        if not row:
            return None
        return _parse_household_row(row)

def get_household_by_key(session_id: int, household_key: str) -> dict | None:
    """Retrieves a household by its session-unique key."""
    if not session_id or not household_key:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM households WHERE session_id = ? AND household_key = ?",
            (session_id, household_key)
        ).fetchone()
        if not row:
            return None
        return _parse_household_row(row)

def get_household_members(household_id: int) -> list[dict]:
    """Retrieves all contact records assigned to the specified household."""
    if not household_id:
        return []
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM contacts WHERE household_id = ? ORDER BY id ASC",
            (household_id,)
        ).fetchall()
        members = []
        for r in rows:
            d = dict(r)
            for jcol in ("basic_info_json", "relations_json", "appearance_json", "unlocked_traits_json", "preferences_json", "intimate_memories_json", "rel_history_json"):
                plain = jcol.replace("_json", "")
                try:
                    d[plain] = json.loads(d.get(jcol) or ("[]" if "json" in jcol and jcol in ("unlocked_traits_json", "preferences_json", "intimate_memories_json", "rel_history_json") else "{}"))
                except Exception:
                    d[plain] = [] if "[]" in jcol else {}
            members.append(d)
        return members

def assign_contact_household(
    session_id: int,
    contact_identifier: int | str,
    household_id: int,
    household_role: str | None = None,
) -> bool:
    """Assigns or re-links a contact to a household by contact ID or npc_id/name."""
    if not contact_identifier or not household_id:
        return False
    now = time.time()
    role_clean = str(household_role).strip().lower() if household_role else None
    with get_conn() as conn:
        if isinstance(contact_identifier, int) or (isinstance(contact_identifier, str) and str(contact_identifier).isdigit()):
            cursor = conn.execute(
                "UPDATE contacts SET household_id = ?, household_role = COALESCE(?, household_role, 'child'), updated_at = ? WHERE id = ? AND session_id = ?",
                (household_id, role_clean, now, int(contact_identifier), session_id)
            )
        else:
            clean_id = str(contact_identifier).strip().lower().replace(" ", "_")
            clean_name = str(contact_identifier).strip().lower()
            cursor = conn.execute(
                """UPDATE contacts SET household_id = ?, household_role = COALESCE(?, household_role, 'child'), updated_at = ?
                   WHERE session_id = ? AND (npc_id = ? OR lower(npc_id) = ? OR lower(name) = ?)""",
                (household_id, role_clean, now, session_id, clean_id, clean_id, clean_name)
            )
        return cursor.rowcount > 0

def _parse_faction_row(d: dict) -> dict:
    """Deserialize JSON columns of a raw factions row dict."""
    for col, default in (
        ("perks_json", "[]"),
        ("leadership_roster_json", "[]"),
        ("rival_faction_ids_json", "[]"),
        ("allied_faction_ids_json", "[]"),
    ):
        try:
            d[col.replace("_json", "")] = json.loads(d.get(col) or default)
        except Exception:
            d[col.replace("_json", "")] = []
    d.setdefault("hq_node_id", "")
    d.setdefault("hq_display_name", d.get("hq_location_id", ""))
    return d

def upsert_faction(session_id: int, name: str, delta_score: int = 0, notes: str = "",
                   perks: list = None, category: str = "", hq_location_id: str = "",
                   hierarchy_template: str = "", leadership_roster: list = None,
                   rival_faction_ids: list = None, allied_faction_ids: list = None,
                   hq_node_id: str = "") -> dict:
    name = (name or "").strip()
    if not name:
        return {}
    faction_id = name.lower().replace(" ", "_")
    now = time.time()
    perks_json = json.dumps(perks) if isinstance(perks, (list, tuple)) else (perks or "[]")
    roster_json = json.dumps(leadership_roster) if isinstance(leadership_roster, list) else None
    rivals_json = json.dumps(rival_faction_ids) if isinstance(rival_faction_ids, list) else None
    allies_json = json.dumps(allied_faction_ids) if isinstance(allied_faction_ids, list) else None

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT * FROM factions WHERE session_id=? AND faction_id=?",
            (session_id, faction_id)).fetchone()
        if existing:
            new_score = max(-100, min(100, existing["reputation_score"] + delta_score))
            # Preserve existing rich description if already present; only fill if previously empty
            final_notes = existing["notes"] if (existing["notes"] and existing["notes"].strip()) else (notes or "")
            conn.execute(
                """UPDATE factions SET reputation_score=?,
                                        perks_json=COALESCE(NULLIF(?, '[]'), perks_json),
                                        notes=?,
                                        category=COALESCE(NULLIF(?, ''), category),
                                        hq_location_id=COALESCE(NULLIF(?, ''), hq_location_id),
                                        hq_node_id=COALESCE(NULLIF(?, ''), hq_node_id),
                                        hierarchy_template=COALESCE(NULLIF(?, ''), hierarchy_template),
                                        leadership_roster_json=COALESCE(NULLIF(?, '[]'), leadership_roster_json),
                                        rival_faction_ids_json=COALESCE(NULLIF(?, '[]'), rival_faction_ids_json),
                                        allied_faction_ids_json=COALESCE(NULLIF(?, '[]'), allied_faction_ids_json),
                                        updated_at=? WHERE id=?""",
                (new_score, perks_json, final_notes,
                 category or "", hq_location_id or "", hq_node_id or "", hierarchy_template or "",
                 roster_json or "[]", rivals_json or "[]", allies_json or "[]",
                 now, existing["id"]))
            row = dict(existing)
            row["notes"] = final_notes
            row["reputation_score"] = new_score
            row["updated_at"] = now
            return db._parse_faction_row(row)
        else:
            initial_score = max(-100, min(100, delta_score))
            from mechanics.social.factions import guess_hierarchy_template
            cat = category or hierarchy_template or (guess_hierarchy_template(name) if name else "default")
            tmpl = hierarchy_template or category or cat
            cursor = conn.execute(
                """INSERT INTO factions (session_id, faction_id, name, reputation_score, perks_json, notes,
                                         category, hq_location_id, hq_node_id, hierarchy_template,
                                         leadership_roster_json, rival_faction_ids_json, allied_faction_ids_json,
                                         created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (session_id, faction_id, name, initial_score, perks_json, notes or "",
                 cat, hq_location_id or "", hq_node_id or "", tmpl,
                 roster_json or "[]", rivals_json or "[]", allies_json or "[]", now, now))
            row = {
                "id": cursor.lastrowid, "session_id": session_id, "faction_id": faction_id,
                "name": name, "reputation_score": initial_score, "perks": perks or [],
                "notes": notes, "category": cat, "hq_location_id": hq_location_id or "",
                "hierarchy_template": tmpl, "leadership_roster": leadership_roster or [],
                "rival_faction_ids": rival_faction_ids or [],
                "allied_faction_ids": allied_faction_ids or [],
                "created_at": now, "updated_at": now,
            }
            return row

def get_factions(session_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT f.*, COALESCE(NULLIF(w.name, ''), f.hq_location_id) AS hq_display_name
               FROM factions f
               LEFT JOIN world_nodes w ON w.session_id = f.session_id AND w.node_id = f.hq_node_id
               WHERE f.session_id=? ORDER BY f.updated_at DESC""",
            (session_id,)).fetchall()
    return [db._parse_faction_row(dict(r)) for r in rows]

def get_faction(session_id: int, faction_id_or_name: str) -> dict | None:
    fid = (faction_id_or_name or "").strip().lower().replace(" ", "_")
    with get_conn() as conn:
        r = conn.execute(
            """SELECT f.*, COALESCE(NULLIF(w.name, ''), f.hq_location_id) AS hq_display_name
               FROM factions f
               LEFT JOIN world_nodes w ON w.session_id = f.session_id AND w.node_id = f.hq_node_id
               WHERE f.session_id=? AND f.faction_id=?""",
            (session_id, fid)).fetchone()
    if not r:
        return None
    return db._parse_faction_row(dict(r))

_CORE_ROOM_TO_MAJOR_FAC_NODES: dict[str, tuple[str, ...]] = {
    "loc_student_council": ("loc_student_council_facility",),
    "sub_student_council": ("loc_student_council_facility",),
    "loc_auditorium_stage": ("loc_drama_club_facility",),
    "loc_gymnasium": ("bld_school_athletics", "loc_school_athletics"),
    "loc_nsfw_faction_hq": ("loc_nsfw_club_facility",),
}

_MAJOR_CLUB_FACILITY_TO_CORE_ROOM: dict[str, tuple[str, ...]] = {
    "student council office": ("executive council chamber", "loc_student_council", "sub_student_council"),
    "campus auditorium & drama theater": ("main auditorium stage", "loc_auditorium_stage"),
    "varsity athletic directorate & gymnasium": ("main gymnasium & varsity court", "main gymnasium", "loc_gymnasium"),
    "velvet basement salon": ("main velvet salon", "loc_nsfw_faction_hq"),
}

def get_faction_by_hq(session_id: int, location_id: str) -> dict | None:
    """
    Return the faction whose HQ is at the given location_id, or None.
    Resolves leaf room HQs (e.g. minor clubrooms inside parent wings) before
    facility-tier HQs, supports hq_node_id matching, and enforces strict core
    HQ chamber matching for 3-tier paths inside Major School Clubs.
    """
    if not location_id:
        return None
    with get_conn() as conn:
        loc_clean = str(location_id).strip().lower().replace("->", "➔")
        loc_parts = [p.strip() for p in loc_clean.split("➔") if p.strip()]
        if not loc_parts:
            return None

        # Fast path: exact match on hq_location_id or hq_node_id (including Core HQ room -> facility node)
        mapped_fac_nodes = _CORE_ROOM_TO_MAJOR_FAC_NODES.get(loc_clean, ())
        exact_targets = [loc_clean, *mapped_fac_nodes]
        placeholders = ",".join("?" for _ in exact_targets)
        r = conn.execute(
            f"SELECT * FROM factions WHERE session_id=? AND (LOWER(hq_location_id) IN ({placeholders}) OR LOWER(hq_node_id) IN ({placeholders}))",
            (session_id, *exact_targets, *exact_targets)).fetchone()
        if r:
            return db._parse_faction_row(dict(r))

        rows = conn.execute(
            "SELECT * FROM factions WHERE session_id=?",
            (session_id,)).fetchall()
        if not rows:
            return None

        parsed_rows = []
        for row in rows:
            hq_raw = (row["hq_location_id"] or "").strip()
            hq_nid = (row["hq_node_id"] or "").strip().lower()
            hq_clean = hq_raw.lower().replace("->", "➔")
            hq_parts = [p.strip() for p in hq_clean.split("➔") if p.strip()]
            parsed_rows.append((row, hq_clean, hq_parts, hq_nid))

        leaf_clean = loc_parts[-1]
        is_room_level = len(loc_parts) >= 3

        # Pass 1: Exact full match, hq_node_id match (full or leaf), or single-segment leaf-room HQ match
        for row, hq_clean, hq_parts, hq_nid in parsed_rows:
            if hq_clean and hq_clean == loc_clean:
                return db._parse_faction_row(dict(row))
            if hq_nid and (
                hq_nid == loc_clean
                or hq_nid in mapped_fac_nodes
                or hq_nid == leaf_clean
            ):
                return db._parse_faction_row(dict(row))
            if len(hq_parts) == 1:
                bare_hq = hq_parts[0]
                if len(bare_hq) >= 4 and (
                    bare_hq == leaf_clean
                    or (len(bare_hq) >= 5 and bare_hq in leaf_clean)
                    or (len(leaf_clean) >= 5 and leaf_clean in bare_hq)
                ):
                    return db._parse_faction_row(dict(row))

        # Pass 2: Strict Major School Club core chamber check on 3-tier paths
        # Prevents foyers, notice boards, quartermasters, or sibling facilities (e.g. Swimming Pool)
        # from falsely inheriting Major Club HQ status via loc_parts[1].
        if is_room_level:
            fac_clean = loc_parts[1]
            for maj_fac_key, allowed_core_leaves in _MAJOR_CLUB_FACILITY_TO_CORE_ROOM.items():
                if maj_fac_key in fac_clean or fac_clean == maj_fac_key:
                    if not any(core_k in leaf_clean for core_k in allowed_core_leaves):
                        return None
                    for row, hq_clean, hq_parts, hq_nid in parsed_rows:
                        if maj_fac_key in hq_clean or any(
                            nid_k and nid_k == hq_nid
                            for nid_k in ("loc_student_council_facility", "loc_drama_club_facility", "bld_school_athletics", "loc_school_athletics", "loc_nsfw_club_facility")
                            if maj_fac_key in (
                                "student council office" if "student_council" in nid_k
                                else "campus auditorium & drama theater" if "drama" in nid_k
                                else "varsity athletic directorate & gymnasium" if "athletics" in nid_k
                                else "velvet basement salon"
                            )
                        ):
                            return db._parse_faction_row(dict(row))
                    return None

        # Pass 3: Multi-tier HQs (e.g. Agency HQs) and Tier 2 Facility-level lookups
        for row, hq_clean, hq_parts, hq_nid in parsed_rows:
            if not hq_parts:
                continue
            if hq_nid and hq_nid in loc_parts[1:]:
                return db._parse_faction_row(dict(row))
            if len(hq_parts) > 1:
                if all(any(hq_seg == lp or (len(hq_seg) >= 4 and hq_seg in lp) for lp in loc_parts) for hq_seg in hq_parts):
                    return db._parse_faction_row(dict(row))
            else:
                bare_hq = hq_parts[0]
                if len(bare_hq) >= 4:
                    for i, lp in enumerate(loc_parts):
                        if i == 0 and len(loc_parts) > 1:
                            if bare_hq == lp:
                                return db._parse_faction_row(dict(row))
                        else:
                            if bare_hq == lp or (len(bare_hq) >= 5 and bare_hq in lp) or (len(lp) >= 5 and lp in bare_hq):
                                return db._parse_faction_row(dict(row))

    return None

def update_faction_leadership_roster(session_id: int, faction_id: str, roster: list) -> bool:
    """Persist an updated leadership roster list for a faction."""
    fid = (faction_id or "").strip().lower().replace(" ", "_")
    now = time.time()
    with get_conn() as conn:
        r = conn.execute(
            "UPDATE factions SET leadership_roster_json=?, updated_at=? WHERE session_id=? AND faction_id=?",
            (json.dumps(roster), now, session_id, fid))
        return r.rowcount > 0

def set_character_faction_membership(character_id: int, faction_id: str, rank: int, title: str) -> bool:
    """Set the pledged faction, rank, and title for a character."""
    params = ((faction_id or ""), max(0, int(rank)), (title or ""), character_id)
    with get_conn() as conn:
        r = conn.execute(
            "UPDATE characters SET joined_faction_id=?, faction_rank=?, faction_title=? WHERE id=?",
            params)
        if r.rowcount == 0:
            r = conn.execute(
                "UPDATE characters SET joined_faction_id=?, faction_rank=?, faction_title=? WHERE user_id=? AND is_active=1",
                params)
        return r.rowcount > 0
