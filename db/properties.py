from __future__ import annotations

"""
Normalized persistence, atomic deed purchases, starter quarters relocation,
spare-key management, turn rollback, and inventory capacity calculation for
player properties (`player_properties` table).
"""

import json
import re
import sqlite3
import time
from contextlib import nullcontext
from typing import Any

import character_data as cd
from mechanics.world.locations.realty_catalog import (
    SPARE_KEY_MIN_AFFINITY,
    STARTER_QUARTERS_MAP,
    compute_property_slot_bonus,
    is_anomalous_realty_scenario,
    resolve_realty_entry,
    resolve_starter_quarters_spec,
)

from .core import UnitOfWork, get_conn


def _conn_ctx(conn: sqlite3.Connection | None):
    return nullcontext(conn) if conn is not None else get_conn()


def _uow_ctx(conn: sqlite3.Connection | None):
    return nullcontext(conn) if conn is not None else UnitOfWork()


def _parse_property_row(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    d = dict(row)
    raw_keys = d.get("spare_keys_json") or "{}"
    try:
        parsed_keys = json.loads(raw_keys) if isinstance(raw_keys, str) else dict(raw_keys)
    except Exception:
        parsed_keys = {}
    if not isinstance(parsed_keys, dict):
        parsed_keys = {}
    d["spare_keys"] = {str(k): int(v or 0) for k, v in parsed_keys.items() if str(k).strip()}
    d["is_primary"] = int(bool(d.get("is_primary")))
    d["is_starter"] = int(bool(d.get("is_starter")))
    d["tier"] = int(d.get("tier") or 0)
    d["price_paid"] = int(d.get("price_paid") or 0)
    d["purchased_turn"] = int(d.get("purchased_turn") or 0)
    d["purchased_day"] = int(d.get("purchased_day") or 1)
    return d


def _set_facility_unlock_state(
    conn: sqlite3.Connection,
    session_id: int,
    facility_node_id: str,
    unlocked: bool,
    marker_key: str = "deed_owned",
) -> None:
    if not session_id or not facility_node_id:
        return
    rows = conn.execute(
        "SELECT node_id, state_json FROM world_nodes WHERE session_id = ? AND (node_id = ? OR parent_id = ?)",
        (int(session_id), facility_node_id, facility_node_id),
    ).fetchall()
    for r in rows:
        nid = r["node_id"]
        try:
            st = json.loads(r["state_json"] or "{}")
            if not isinstance(st, dict):
                st = {}
        except Exception:
            st = {}
        if unlocked:
            st["unlocked_permanent"] = True
            st[marker_key] = True
        else:
            st.pop(marker_key, None)
            if not st.get("deed_owned") and not st.get("starter_unlocked"):
                st.pop("unlocked_permanent", None)
        conn.execute(
            "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
            (json.dumps(st), int(session_id), nid),
        )
    if unlocked:
        conn.execute(
            """UPDATE world_edges
               SET is_locked = 0
               WHERE session_id = ?
                 AND (
                     from_node_id = ?
                     OR to_node_id = ?
                     OR from_node_id IN (SELECT node_id FROM world_nodes WHERE session_id = ? AND parent_id = ?)
                     OR to_node_id IN (SELECT node_id FROM world_nodes WHERE session_id = ? AND parent_id = ?)
                 )""",
            (
                int(session_id),
                facility_node_id,
                facility_node_id,
                int(session_id),
                facility_node_id,
                int(session_id),
                facility_node_id,
            ),
        )


def _session_dict_from_conn(conn: sqlite3.Connection, session_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM sessions WHERE id = ?", (int(session_id),)).fetchone()
    if not row:
        return {}
    d = dict(row)
    raw_extra = d.get("extra_json") or "{}"
    try:
        extra = json.loads(raw_extra) if isinstance(raw_extra, str) else dict(raw_extra)
        if isinstance(extra, dict):
            for k, v in extra.items():
                if k not in d:
                    d[k] = v
    except Exception:
        pass
    try:
        from .dossiers import hydrate_session_anomaly_records
        hydrate_session_anomaly_records(int(session_id), d, conn=conn)
    except Exception:
        pass
    return d


def get_player_properties(
    session_id: int,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Returns all starter and purchased property records for a session, ordered primary-first then tier-desc."""
    if not session_id:
        return []
    with _conn_ctx(conn) as c:
        rows = c.execute(
            """SELECT * FROM player_properties
               WHERE session_id = ?
               ORDER BY is_primary DESC, is_starter ASC, tier DESC, id ASC""",
            (int(session_id),),
        ).fetchall()
    return [_parse_property_row(r) for r in rows]


def get_primary_property(
    session_id: int,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    """Returns the player's active Primary Home record (falling back to highest tier or starter if unset)."""
    props = get_player_properties(session_id, conn=conn)
    if not props:
        return None
    for p in props:
        if p.get("is_primary"):
            return p
    return props[0]


def grant_or_relocate_starter_quarters(
    session_id: int,
    faction_key: str = "",
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    """
    Assigns or relocates the player's free faction-specific starter quarters (`is_starter=1`).
    - Revokes lock access on any previous starter quarters facility (unless also owned via a permanent deed,
      or `loc_player_house` for a Student Operative whose parents still live there).
    - Preserves all permanently purchased deeds (`is_starter=0`).
    """
    if not session_id:
        return {}
    now = time.time()
    with _uow_ctx(conn) as c:
        sess = _session_dict_from_conn(c, int(session_id))
        if sess and not is_anomalous_realty_scenario(str(sess.get("scenario") or "")):
            return {}
        spec = resolve_starter_quarters_spec(faction_key, session_or_id=sess or session_id)
        is_student = False
        try:
            from mechanics.social.origin_mode import is_student_operative
            is_student = bool(is_student_operative(sess)) if sess else (str(faction_key or "").strip().lower() == "student_freelancer")
        except Exception:
            is_student = str(faction_key or "").strip().lower() == "student_freelancer"

        old_starters = c.execute(
            "SELECT * FROM player_properties WHERE session_id = ? AND is_starter = 1",
            (int(session_id),),
        ).fetchall()
        permanent_facs = {
            r["facility_node_id"]
            for r in c.execute(
                "SELECT facility_node_id FROM player_properties WHERE session_id = ? AND is_starter = 0",
                (int(session_id),),
            ).fetchall()
        }
        was_primary = False
        for old_r in old_starters:
            old_fac = old_r["facility_node_id"]
            if int(old_r["is_primary"] or 0) == 1:
                was_primary = True
            if old_fac != spec["facility_node_id"]:
                keep_parents_house = is_student and old_fac == "loc_player_house"
                if old_fac not in permanent_facs and not keep_parents_house:
                    _set_facility_unlock_state(c, int(session_id), old_fac, unlocked=False, marker_key="starter_unlocked")
            if old_r["property_id"] != spec["property_id"]:
                c.execute("DELETE FROM player_properties WHERE id = ?", (old_r["id"],))

        has_any_primary = bool(
            c.execute(
                "SELECT 1 FROM player_properties WHERE session_id = ? AND is_primary = 1 AND property_id != ?",
                (int(session_id), spec["property_id"]),
            ).fetchone()
        )
        make_primary = 1 if (was_primary or not has_any_primary) else 0
        if make_primary:
            c.execute("UPDATE player_properties SET is_primary = 0 WHERE session_id = ?", (int(session_id),))

        t_num = int(sess.get("turn_count") or 0)
        c_day = int(sess.get("current_day") or 1)
        c.execute(
            """INSERT INTO player_properties (
                   session_id, property_id, facility_node_id, zone_id, tier,
                   price_paid, is_primary, is_starter, spare_keys_json,
                   purchased_turn, purchased_day, created_at, updated_at
               ) VALUES (?, ?, ?, ?, 0, 0, ?, 1, '{}', ?, ?, ?, ?)
               ON CONFLICT(session_id, property_id) DO UPDATE SET
                   facility_node_id = excluded.facility_node_id,
                   zone_id = excluded.zone_id,
                   is_primary = CASE WHEN excluded.is_primary = 1 THEN 1 ELSE player_properties.is_primary END,
                   is_starter = 1,
                   updated_at = excluded.updated_at""",
            (
                int(session_id),
                spec["property_id"],
                spec["facility_node_id"],
                spec["zone_id"],
                make_primary,
                t_num,
                c_day,
                now,
                now,
            ),
        )
        _set_facility_unlock_state(c, int(session_id), spec["facility_node_id"], unlocked=True, marker_key="starter_unlocked")
        if is_student:
            # Student Operative always keeps doorstep/family access to Parents' House
            _set_facility_unlock_state(c, int(session_id), "loc_player_house", unlocked=True, marker_key="starter_unlocked")

        saved = c.execute(
            "SELECT * FROM player_properties WHERE session_id = ? AND property_id = ?",
            (int(session_id), spec["property_id"]),
        ).fetchone()
        return _parse_property_row(saved) if saved else {}


def atomic_purchase_property(
    session_id: int,
    user_id: int,
    property_id: str,
    set_primary: bool | None = None,
    turn_number: int | None = None,
) -> dict[str, Any]:
    """
    Atomically validates gold & property catalog entry, deducts character gold,
    inserts a permanent deed (`is_starter=0`), unlocks all facility nodes/edges,
    and promotes the first purchased deed (or explicit `set_primary=True`) to Primary Home.
    """
    if not session_id:
        return {"ok": False, "reason": "invalid_session"}
    now = time.time()
    with UnitOfWork() as conn:
        sess = _session_dict_from_conn(conn, int(session_id))
        if not sess:
            return {"ok": False, "reason": "session_not_found"}
        if not is_anomalous_realty_scenario(str(sess.get("scenario") or "")):
            return {"ok": False, "reason": "unsupported_scenario"}

        entry = resolve_realty_entry(property_id, session_or_id=sess)
        if not entry:
            return {"ok": False, "reason": "unknown_property"}

        existing = conn.execute(
            "SELECT * FROM player_properties WHERE session_id = ? AND property_id = ? AND is_starter = 0",
            (int(session_id), entry["property_id"]),
        ).fetchone()
        if existing:
            return {
                "ok": False,
                "reason": "already_owned",
                "property": _parse_property_row(existing),
            }

        char_row = conn.execute(
            """SELECT * FROM characters
               WHERE user_id = ?
               ORDER BY
                   CASE
                       WHEN id = ? THEN 0
                       WHEN active_session_id = ? THEN 1
                       WHEN is_active = 1 THEN 2
                       ELSE 3
                   END ASC,
                   id DESC
               LIMIT 1""",
            (int(user_id), sess.get("character_id") or -1, int(session_id)),
        ).fetchone()
        if not char_row and sess.get("character_id"):
            char_row = conn.execute("SELECT * FROM characters WHERE id = ?", (int(sess["character_id"]),)).fetchone()
        if not char_row:
            return {"ok": False, "reason": "character_not_found"}

        cur_gold = int(char_row["gold"] or 0)
        price = int(entry["price"])
        if cur_gold < price:
            return {
                "ok": False,
                "reason": "insufficient_gold",
                "gold": cur_gold,
                "price": price,
            }

        new_gold = cur_gold - price
        conn.execute(
            "UPDATE characters SET gold = ? WHERE id = ?",
            (new_gold, int(char_row["id"])),
        )

        owned_deeds_cnt = conn.execute(
            "SELECT COUNT(*) AS cnt FROM player_properties WHERE session_id = ? AND is_starter = 0",
            (int(session_id),),
        ).fetchone()["cnt"]
        promote_primary = bool(set_primary) if set_primary is not None else (int(owned_deeds_cnt or 0) == 0)
        if promote_primary:
            conn.execute("UPDATE player_properties SET is_primary = 0 WHERE session_id = ?", (int(session_id),))

        t_num = int(turn_number) if turn_number is not None else int(sess.get("turn_count") or 0)
        c_day = int(sess.get("current_day") or 1)
        conn.execute(
            """INSERT INTO player_properties (
                   session_id, property_id, facility_node_id, zone_id, tier,
                   price_paid, is_primary, is_starter, spare_keys_json,
                   purchased_turn, purchased_day, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, '{}', ?, ?, ?, ?)""",
            (
                int(session_id),
                entry["property_id"],
                entry["facility_node_id"],
                entry["zone_id"],
                int(entry["tier"]),
                price,
                1 if promote_primary else 0,
                t_num,
                c_day,
                now,
                now,
            ),
        )
        _set_facility_unlock_state(conn, int(session_id), entry["facility_node_id"], unlocked=True, marker_key="deed_owned")

        saved = conn.execute(
            "SELECT * FROM player_properties WHERE session_id = ? AND property_id = ?",
            (int(session_id), entry["property_id"]),
        ).fetchone()
        new_cap = get_character_inventory_capacity(
            int(char_row["user_id"]),
            char=dict(char_row),
            session_id=int(session_id),
            conn=conn,
        )
        return {
            "ok": True,
            "property": _parse_property_row(saved) if saved else {},
            "catalog_entry": entry,
            "character_id": int(char_row["id"]),
            "gold": new_gold,
            "new_gold": new_gold,
            "price_paid": price,
            "max_inventory_slots": new_cap,
        }


def set_primary_property(session_id: int, property_id: str) -> dict[str, Any]:
    """Sets an owned deed or active starter quarters as the player's Primary Home."""
    if not session_id or not property_id:
        return {"ok": False, "reason": "invalid_request"}
    now = time.time()
    with UnitOfWork() as conn:
        target = conn.execute(
            "SELECT * FROM player_properties WHERE session_id = ? AND property_id = ?",
            (int(session_id), str(property_id).strip()),
        ).fetchone()
        if not target:
            return {"ok": False, "reason": "not_owned"}
        conn.execute(
            "UPDATE player_properties SET is_primary = 0, updated_at = ? WHERE session_id = ?",
            (now, int(session_id)),
        )
        conn.execute(
            "UPDATE player_properties SET is_primary = 1, updated_at = ? WHERE id = ?",
            (now, int(target["id"])),
        )
        updated = conn.execute("SELECT * FROM player_properties WHERE id = ?", (int(target["id"]),)).fetchone()
        return {"ok": True, "property": _parse_property_row(updated)}


def _is_npc_eligible_for_spare_key(conn: sqlite3.Connection, session_id: int, npc_ref: str) -> tuple[bool, str, str]:
    """Returns (eligible, canonical_npc_id, reason_or_name)."""
    clean_ref = str(npc_ref or "").strip()
    if not clean_ref:
        return False, "", "missing_npc"
    rows = conn.execute(
        "SELECT * FROM contacts WHERE session_id = ?",
        (int(session_id),),
    ).fetchall()
    matched = None
    for r in rows:
        if str(r["npc_id"] or "").strip().lower() == clean_ref.lower() or str(r["name"] or "").strip().lower() == clean_ref.lower():
            matched = dict(r)
            break
    if not matched:
        return False, "", "contact_not_found"

    canonical_id = str(matched.get("npc_id") or matched.get("name") or clean_ref).strip()
    b_info: dict[str, Any] = {}
    try:
        parsed_b = json.loads(matched.get("basic_info_json") or "{}")
        if isinstance(parsed_b, dict):
            b_info = parsed_b
    except Exception:
        b_info = {}
    if (
        matched.get("is_deceased")
        or b_info.get("is_deceased")
        or b_info.get("deceased")
        or str(b_info.get("status") or "").strip().lower() == "deceased"
    ):
        return False, "", "contact_deceased"

    if str(matched.get("race") or b_info.get("race") or "").strip().lower() == "kitsune:myobu_fox":
        return False, canonical_id, "beast_form_disallowed"

    rel_score = int(matched.get("relationship_score") or 0)
    track = str(matched.get("track") or "").strip().lower()
    is_romantic = track in ("romantic", "lover", "partner", "spouse", "married", "dating", "fiance", "fiancee")

    if not is_romantic and b_info:
        r_stat = str(b_info.get("romantic_status") or b_info.get("relationship_status") or "").strip().lower()
        if r_stat in ("dating", "romantic", "lover", "partner", "engaged", "married", "spouse", "boyfriend", "girlfriend"):
            is_romantic = True

    if not is_romantic:
        person_row = conn.execute(
            "SELECT person_key FROM social_persons WHERE session_id = ? AND (LOWER(contact_npc_id) = LOWER(?) OR LOWER(display_name) = LOWER(?)) LIMIT 1",
            (int(session_id), canonical_id, str(matched.get("name") or "")),
        ).fetchone()
        if person_row:
            pk = person_row["person_key"]
            tie_row = conn.execute(
                """SELECT 1 FROM social_ties
                   WHERE session_id = ?
                     AND status = 'active'
                     AND LOWER(tie_type) IN ('romantic', 'dating', 'partner', 'lover', 'engaged', 'married', 'spouse')
                     AND ((person_a_key = 'player' AND person_b_key = ?) OR (person_b_key = 'player' AND person_a_key = ?))
                   LIMIT 1""",
                (int(session_id), pk, pk),
            ).fetchone()
            if tie_row:
                is_romantic = True

    if rel_score < SPARE_KEY_MIN_AFFINITY and not is_romantic:
        return False, canonical_id, "insufficient_affinity"
    return True, canonical_id, str(matched.get("name") or canonical_id)


def grant_property_spare_key(session_id: int, property_id: str, npc_id: str) -> dict[str, Any]:
    """
    Grants a Spare Key for a permanently purchased deed (`is_starter == 0`) to a trusted/romantic NPC.
    Starter quarters explicitly disallow spare keys.
    """
    if not session_id or not property_id or not npc_id:
        return {"ok": False, "reason": "invalid_request"}
    prop_clean = str(property_id).strip()
    if any(v["property_id"] == prop_clean for v in STARTER_QUARTERS_MAP.values()):
        return {"ok": False, "reason": "starter_quarters_disallowed"}

    now = time.time()
    with UnitOfWork() as conn:
        row = conn.execute(
            "SELECT * FROM player_properties WHERE session_id = ? AND property_id = ?",
            (int(session_id), prop_clean),
        ).fetchone()
        if not row:
            return {"ok": False, "reason": "not_owned"}
        if int(row["is_starter"] or 0) == 1:
            return {"ok": False, "reason": "starter_quarters_disallowed"}

        eligible, canonical_npc_id, label_or_err = _is_npc_eligible_for_spare_key(conn, int(session_id), npc_id)
        if not eligible:
            return {"ok": False, "reason": label_or_err}

        sess = _session_dict_from_conn(conn, int(session_id))
        t_num = int(sess.get("turn_count") or 0)
        parsed = _parse_property_row(row)
        keys_map = dict(parsed["spare_keys"])
        keys_map[canonical_npc_id] = t_num
        conn.execute(
            "UPDATE player_properties SET spare_keys_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(keys_map), now, int(row["id"])),
        )
        updated = conn.execute("SELECT * FROM player_properties WHERE id = ?", (int(row["id"]),)).fetchone()
        return {
            "ok": True,
            "npc_id": canonical_npc_id,
            "npc_name": label_or_err,
            "property": _parse_property_row(updated),
        }


def revoke_property_spare_key(session_id: int, property_id: str, npc_id: str) -> dict[str, Any]:
    """Revokes an NPC's Spare Key on an owned property."""
    if not session_id or not property_id or not npc_id:
        return {"ok": False, "reason": "invalid_request"}
    now = time.time()
    with UnitOfWork() as conn:
        row = conn.execute(
            "SELECT * FROM player_properties WHERE session_id = ? AND property_id = ?",
            (int(session_id), str(property_id).strip()),
        ).fetchone()
        if not row:
            return {"ok": False, "reason": "not_owned"}
        parsed = _parse_property_row(row)
        clean_target = str(npc_id).strip().lower()
        slug_target = re.sub(r"[-\s]+", "_", re.sub(r"[^\w\s-]", "", clean_target)).strip("_")
        aliases = {x for x in (clean_target, slug_target) if x}
        c_rows = conn.execute("SELECT npc_id, name FROM contacts WHERE session_id = ?", (int(session_id),)).fetchall()
        for cr in c_rows:
            cid_l = str(cr["npc_id"] or "").strip().lower()
            cnm_l = str(cr["name"] or "").strip().lower()
            cslug = re.sub(r"[-\s]+", "_", re.sub(r"[^\w\s-]", "", cnm_l)).strip("_")
            c_set = {x for x in (cid_l, cnm_l, cslug) if x}
            if aliases & c_set:
                aliases.update(c_set)
        keys_map = {
            k: v for k, v in parsed["spare_keys"].items()
            if k.strip().lower() not in aliases
        }
        conn.execute(
            "UPDATE player_properties SET spare_keys_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(keys_map), now, int(row["id"])),
        )
        updated = conn.execute("SELECT * FROM player_properties WHERE id = ?", (int(row["id"]),)).fetchone()
        return {"ok": True, "property": _parse_property_row(updated)}


def rollback_player_properties_after_turn(
    session_id: int,
    turn_number: int,
    conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    """
    Rolls back `player_properties` mutations that occurred strictly after `turn_number`:
    1. Deletes permanently purchased deeds (`is_starter=0`) with `purchased_turn > turn_number` and
       clears `deed_owned` / `unlocked_permanent` in `world_nodes.state_json`.
    2. Prunes `spare_keys_json` entries where `turn_granted > turn_number`.
    3. Self-heals `is_primary = 1` onto the remaining highest-tier or starter home if primary was deleted.
    """
    if not session_id:
        return {"properties_deleted": 0, "spare_keys_pruned": 0}
    t_num = int(turn_number)
    now = time.time()
    deleted_cnt = 0
    pruned_keys = 0

    with _uow_ctx(conn) as c:
        to_revert = c.execute(
            "SELECT id, facility_node_id FROM player_properties WHERE session_id = ? AND is_starter = 0 AND purchased_turn > ?",
            (int(session_id), t_num),
        ).fetchall()
        for r in to_revert:
            c.execute("DELETE FROM player_properties WHERE id = ?", (int(r["id"]),))
            _set_facility_unlock_state(c, int(session_id), r["facility_node_id"], unlocked=False, marker_key="deed_owned")
            deleted_cnt += 1

        remaining = c.execute(
            "SELECT * FROM player_properties WHERE session_id = ? ORDER BY is_primary DESC, tier DESC, is_starter ASC, id ASC",
            (int(session_id),),
        ).fetchall()
        has_primary = False
        for r in remaining:
            parsed = _parse_property_row(r)
            if parsed["is_primary"]:
                has_primary = True
            orig_keys = parsed["spare_keys"]
            kept_keys = {k: v for k, v in orig_keys.items() if int(v) <= t_num}
            if len(kept_keys) != len(orig_keys):
                pruned_keys += len(orig_keys) - len(kept_keys)
                c.execute(
                    "UPDATE player_properties SET spare_keys_json = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(kept_keys), now, int(r["id"])),
                )

        if remaining and not has_primary:
            c.execute(
                "UPDATE player_properties SET is_primary = 1, updated_at = ? WHERE id = ?",
                (now, int(remaining[0]["id"])),
            )

    return {"properties_deleted": deleted_cnt, "spare_keys_pruned": pruned_keys}


def get_character_inventory_capacity(
    user_id: int,
    char: dict[str, Any] | None = None,
    session_id: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> int:
    """
    Computes total inventory slot capacity for `user_id` (`30 + STR*3 + property_slot_bonus`),
    resolving `active_session_id` automatically when `session_id` is omitted.
    """
    with _conn_ctx(conn) as c:
        if char is None:
            row = c.execute(
                "SELECT * FROM characters WHERE user_id = ? ORDER BY is_active DESC, id DESC LIMIT 1",
                (int(user_id),),
            ).fetchone()
            char = dict(row) if row else None
        if not char:
            return cd.inventory_capacity(1, bonus_slots=0)

        strength = int(char.get("str_", 1) or 1)
        sid = session_id or char.get("active_session_id")
        if sid and not session_id:
            st_row = c.execute("SELECT status FROM sessions WHERE id = ?", (int(sid),)).fetchone()
            if not st_row or st_row["status"] not in ("active", "waiting"):
                sid = None
        if not sid:
            char_id = char.get("id")
            sess_row = c.execute(
                """SELECT s.id
                   FROM sessions s
                   LEFT JOIN session_members sm ON sm.session_id = s.id
                   WHERE s.status IN ('active', 'waiting')
                     AND (s.character_id = ? OR sm.user_id = ? OR s.host_user_id = ?)
                   ORDER BY
                       CASE WHEN s.character_id = ? THEN 0 ELSE 1 END ASC,
                       s.updated_at DESC,
                       s.id DESC
                   LIMIT 1""",
                (char_id or -1, int(user_id), int(user_id), char_id or -1),
            ).fetchone()
            if sess_row:
                sid = int(sess_row["id"])

        bonus = 0
        if sid:
            try:
                t_rows = c.execute(
                    "SELECT tier FROM player_properties WHERE session_id = ? AND is_starter = 0",
                    (int(sid),),
                ).fetchall()
                tiers = [int(r["tier"] or 0) for r in t_rows if int(r["tier"] or 0) > 0]
                bonus = compute_property_slot_bonus(tiers)
            except sqlite3.OperationalError:
                bonus = 0

        return cd.inventory_capacity(strength, bonus_slots=bonus)


__all__ = [
    "atomic_purchase_property",
    "get_character_inventory_capacity",
    "get_player_properties",
    "get_primary_property",
    "grant_or_relocate_starter_quarters",
    "grant_property_spare_key",
    "revoke_property_spare_key",
    "rollback_player_properties_after_turn",
    "set_primary_property",
]
