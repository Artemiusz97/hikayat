"""
mechanics/world/locations/folklore_spirit_realm_lifecycle.py
==========================================================
Idempotent Migration 62 legacy save backfill (`backfill_folklore_spirit_realm_v52`)
and strict post-turn rollback (`rollback_spirit_realm_state_after_turn`) for
`realm_veiled_spirit_world`.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

import scenario_data

from .folklore_spirit_courts import (
    ALL_SPIRIT_GUEST_FACILITY_IDS,
    CHINATOWN_SHORTCUT_HUMAN_NODE,
    CHINATOWN_SHORTCUT_SPIRIT_NODE,
    SPIRIT_COURT_FACTIONS,
    SPIRIT_REALM_ID,
    _get_court_rep_sql,
    _mutate_spirit_realm_state,
    _parse_json_dict,
    _uow_ctx,
    get_spirit_realm_state,
)

log = logging.getLogger("hikayat.world.folklore_spirit_realm_lifecycle")


def _cleanup_legacy_threshold_edges(conn: Any, sid: int) -> None:
    """Removes obsolete pre-expansion direct doors & rewires human threshold zone pathways."""
    stale_pairs = (
        ("loc_hidden_kitsune_village", "loc_et_fox_torii_tunnel"),
        ("loc_hidden_bunian_village", "loc_bunian_threshold_glade"),
    )
    for a, b in stale_pairs:
        conn.execute(
            """DELETE FROM world_edges
               WHERE session_id = ?
                 AND ((from_node_id = ? AND to_node_id = ?) OR (from_node_id = ? AND to_node_id = ?))""",
            (sid, a, b, b, a),
        )
    # Remove any non-portal legacy doors connecting thresholds directly into plazas
    for thresh, plaza in (
        ("loc_et_fox_torii_tunnel", "sub_kitsune_inner_plaza"),
        ("loc_bunian_threshold_glade", "sub_bunian_inner_plaza"),
    ):
        conn.execute(
            """DELETE FROM world_edges
               WHERE session_id = ?
                 AND edge_type != 'leyline_spirit_passage'
                 AND ((from_node_id = ? AND to_node_id = ?) OR (from_node_id = ? AND to_node_id = ?))""",
            (sid, thresh, plaza, plaza, thresh),
        )
    # Rewire human-zone pathways that used to connect directly to loc_hidden_*_village
    for old_fac, new_thresh_fac in (
        ("loc_hidden_kitsune_village", "loc_kitsune_torii_approach"),
        ("loc_hidden_bunian_village", "loc_bunian_mist_glade"),
    ):
        rows = conn.execute(
            "SELECT id, from_node_id, to_node_id FROM world_edges WHERE session_id = ? AND (from_node_id = ? OR to_node_id = ?)",
            (sid, old_fac, old_fac),
        ).fetchall()
        for r in rows:
            eid = int(r["id"])
            u = str(r["from_node_id"])
            v = str(r["to_node_id"])
            if u.startswith("loc_") and v.startswith("loc_") and not (u.startswith("loc_spirit_") or v.startswith("loc_spirit_")):
                nu = new_thresh_fac if u == old_fac else u
                nv = new_thresh_fac if v == old_fac else v
                if nu == nv:
                    conn.execute("DELETE FROM world_edges WHERE id = ?", (eid,))
                    continue
                # Keep rewiring only for human-zone facilities (non-spirit-realm)
                other = nv if u == old_fac else nu
                o_row = conn.execute("SELECT parent_id FROM world_nodes WHERE session_id = ? AND node_id = ?", (sid, other)).fetchone()
                o_parent = str(o_row["parent_id"] or "") if o_row else ""
                if o_parent in ("zone_eastern_sanctuary", "zone_woods_reserve"):
                    dup = conn.execute(
                        """SELECT 1 FROM world_edges WHERE session_id = ? AND id != ?
                           AND ((from_node_id = ? AND to_node_id = ?) OR (from_node_id = ? AND to_node_id = ?)) LIMIT 1""",
                        (sid, eid, nu, nv, nv, nu),
                    ).fetchone()
                    if dup:
                        conn.execute("DELETE FROM world_edges WHERE id = ?", (eid,))
                    else:
                        conn.execute("UPDATE world_edges SET from_node_id = ?, to_node_id = ? WHERE id = ?", (nu, nv, eid))


def _refresh_reparented_session_locations(conn: Any, sid: int, node_ids: List[str], cur_nid: str) -> None:
    """Syncs `session_locations` rows and `sessions.current_location` via `conn` without extra UoWs or full-table scans."""
    from .realms import _format_tiered_location_in_memory

    rows = conn.execute(
        "SELECT node_id, parent_id, name, node_type, atmosphere, state_json FROM world_nodes WHERE session_id = ?",
        (sid,),
    ).fetchall()
    n_map: dict[str, dict[str, Any]] = {str(r["node_id"]): dict(r) for r in rows if r["node_id"]}
    now = time.time()
    for nid in node_ids:
        r = n_map.get(nid)
        if not r:
            continue
        fac_id = str(r.get("parent_id") or "")
        f_row = n_map.get(fac_id) if fac_id else None
        if not f_row:
            continue
        z_id = str(f_row.get("parent_id") or "")
        z_row = n_map.get(z_id) if z_id else None
        z_name = str(z_row.get("name") or "") if z_row else ""
        if z_name:
            conn.execute(
                """INSERT INTO session_locations (session_id, location_id, zone_name, primary_name, sub_name, atmosphere, is_dynamic, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                   ON CONFLICT(session_id, location_id) DO UPDATE SET
                   zone_name=excluded.zone_name, primary_name=excluded.primary_name, sub_name=excluded.sub_name,
                   atmosphere=CASE WHEN excluded.atmosphere != '' THEN excluded.atmosphere ELSE session_locations.atmosphere END""",
                (
                    sid,
                    nid,
                    z_name,
                    str(f_row.get("name") or fac_id),
                    str(r.get("name") or nid),
                    str(r.get("atmosphere") or ""),
                    now,
                ),
            )
    if cur_nid in node_ids or cur_nid.startswith(("sub_kitsune_", "sub_bunian_", "loc_hidden_")):
        fresh_loc = _format_tiered_location_in_memory(cur_nid, n_map)
        if fresh_loc:
            conn.execute("UPDATE sessions SET current_location = ? WHERE id = ?", (fresh_loc, sid))


def _list_sessions_for_backfill(conn: Any, session_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Loads session rows defensively across legacy pre-v52 schemas lacking scenario/current_node_id."""
    has_wn = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='world_nodes' LIMIT 1"
    ).fetchone()
    has_sess = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sessions' LIMIT 1"
    ).fetchone()
    if not has_wn or not has_sess:
        return []
    sess_cols = {
        (r["name"] if hasattr(r, "keys") else r[1])
        for r in conn.execute("PRAGMA table_info(sessions)").fetchall()
    }
    if "scenario" not in sess_cols:
        return []
    wn_cols = {
        (r["name"] if hasattr(r, "keys") else r[1])
        for r in conn.execute("PRAGMA table_info(world_nodes)").fetchall()
    }
    if not {"session_id", "node_id", "state_json"}.issubset(wn_cols):
        return []
    node_expr = "current_node_id" if "current_node_id" in sess_cols else "'' AS current_node_id"
    turn_expr = "turn_count" if "turn_count" in sess_cols else "0 AS turn_count"
    extra_expr = "extra_json" if "extra_json" in sess_cols else "'{}' AS extra_json"
    sql = f"SELECT id, scenario, {node_expr}, {turn_expr}, {extra_expr} FROM sessions"
    if session_id is not None:
        rows = conn.execute(sql + " WHERE id = ?", (int(session_id),)).fetchall()
    else:
        rows = conn.execute(sql).fetchall()
    return [
        {
            "id": int(r["id"] if hasattr(r, "keys") else r[0]),
            "scenario": str((r["scenario"] if hasattr(r, "keys") else r[1]) or ""),
            "current_node_id": str((r["current_node_id"] if hasattr(r, "keys") else r[2]) or ""),
            "turn_count": int((r["turn_count"] if hasattr(r, "keys") else r[3]) or 0),
            "extra_json": (r["extra_json"] if hasattr(r, "keys") else r[4]) or "{}",
        }
        for r in rows
    ]


def backfill_folklore_spirit_realm_v52(conn: Any, session_id: Optional[int] = None) -> int:
    """
    Idempotent Migration 62 (`folklore_spirit_realm_v52`) backfill for pre-expansion
    anomalous saves and legacy loaded slots:
    - Preserves `folklore_veil_state` (attuned/atonement/leyline) and PC location
    - Reparents `loc_hidden_kitsune_village` -> `zone_spirit_kitsune`, `loc_hidden_bunian_village` -> `zone_spirit_bunian`
    - Cleans up stale pre-expansion threshold edges & refreshes `current_location`
    - Creates `realm_veiled_spirit_world`, all 4 Spirit zones, 18 facilities + rooms, human thresholds, and portals
    - Retroactively applies Approach A visibility & Spirit Courts if legacy save already attuned a village
    """
    from .folklore_spirit_realm import on_enter_village_from_human_threshold
    from .seeds import get_scenario_seed_data

    s_rows = _list_sessions_for_backfill(conn, session_id=session_id)

    migrated = 0
    for sr in s_rows:
        sid = int(sr["id"])
        scen = str(sr["scenario"] or "")
        if not (
            scenario_data.is_anomalous_incursions_scenario(scen)
            or scenario_data.is_anomalous_high_school_scenario(scen)
            or "urban_anomalies" in scen.lower()
        ):
            continue
        has_woods = conn.execute(
            "SELECT 1 FROM world_nodes WHERE session_id = ? AND node_id = 'zone_woods_reserve' LIMIT 1",
            (sid,),
        ).fetchone()
        if not has_woods:
            continue
        already = conn.execute(
            "SELECT 1 FROM world_nodes WHERE session_id = ? AND node_id = ? LIMIT 1",
            (sid, SPIRIT_REALM_ID),
        ).fetchone()
        has_torii_fac = conn.execute(
            "SELECT 1 FROM world_nodes WHERE session_id = ? AND node_id = 'loc_kitsune_torii_approach' LIMIT 1",
            (sid,),
        ).fetchone()
        has_kitsune_inner = conn.execute(
            "SELECT 1 FROM world_nodes WHERE session_id = ? AND node_id = 'loc_hidden_kitsune_village' LIMIT 1",
            (sid,),
        ).fetchone()
        has_bunian_inner = conn.execute(
            "SELECT 1 FROM world_nodes WHERE session_id = ? AND node_id = 'loc_hidden_bunian_village' LIMIT 1",
            (sid,),
        ).fetchone()
        has_ghoul_zone = conn.execute(
            "SELECT 1 FROM world_nodes WHERE session_id = ? AND node_id = 'zone_spirit_ghoul' LIMIT 1",
            (sid,),
        ).fetchone()
        has_boneyard_zone = conn.execute(
            "SELECT 1 FROM world_nodes WHERE session_id = ? AND node_id = 'zone_spirit_boneyard' LIMIT 1",
            (sid,),
        ).fetchone()
        has_kitsune_alley = conn.execute(
            "SELECT 1 FROM world_nodes WHERE session_id = ? AND node_id = 'sub_crossroads_kitsune_alley' LIMIT 1",
            (sid,),
        ).fetchone()
        if (
            already
            and has_torii_fac
            and has_kitsune_inner
            and has_bunian_inner
            and has_ghoul_zone
            and has_boneyard_zone
            and has_kitsune_alley
        ):
            continue

        seed_data = get_scenario_seed_data(scen) or {}
        spirit_realm_seed = next(
            (r for r in (seed_data.get("realms") or []) if isinstance(r, dict) and r.get("id") == SPIRIT_REALM_ID),
            None,
        )
        if not spirit_realm_seed:
            continue

        pre_attuned: Dict[str, bool] = {}
        pre_banished: Dict[str, bool] = {}
        for vk, fid in (("kitsune", "loc_hidden_kitsune_village"), ("bunian", "loc_hidden_bunian_village")):
            f_row = conn.execute(
                "SELECT state_json FROM world_nodes WHERE session_id = ? AND node_id = ?",
                (sid, fid),
            ).fetchone()
            fst = _parse_json_dict(f_row["state_json"] if f_row else "{}")
            pre_banished[vk] = bool(fst.get("veil_atonement_required"))
            pre_attuned[vk] = bool(
                not pre_banished[vk]
                and (fst.get("veil_attuned") or fst.get("unlocked_permanent") or (fst.get("discovered") is True and not fst.get("is_hidden", True)))
            )

        now = time.time()
        zones_by_id = {z["id"]: z for z in (seed_data.get("zones") or []) if isinstance(z, dict) and z.get("id")}
        for zid, fid, tid in (
            ("zone_eastern_sanctuary", "loc_kitsune_torii_approach", "loc_et_fox_torii_tunnel"),
            ("zone_woods_reserve", "loc_bunian_mist_glade", "loc_bunian_threshold_glade"),
        ):
            z_obj = zones_by_id.get(zid) or {}
            prim = next((p for p in (z_obj.get("primary_locations") or []) if p.get("id") == fid), None)
            if prim:
                f_atm = json.dumps({
                    "theme": prim.get("theme", ""),
                    "features": prim.get("features", ""),
                    "sensory": prim.get("sensory", ""),
                })
                f_meta = {k: prim[k] for k in ("veil_village_key", "veil_token_item") if k in prim}
                conn.execute(
                    """INSERT OR IGNORE INTO world_nodes
                       (session_id, node_id, parent_id, name, node_type, category, privacy_level,
                        is_enclosed, is_transit_hub, access_tier, atmosphere, is_dynamic, state_json, created_at)
                       VALUES (?, ?, ?, ?, 'FACILITY', 'civic', 'public', 0, 0, 'open', ?, 0, ?, ?)""",
                    (sid, fid, zid, prim["name"], f_atm, json.dumps(f_meta), now),
                )
                conn.execute(
                    "UPDATE world_nodes SET parent_id = ? WHERE session_id = ? AND node_id = ?",
                    (fid, sid, tid),
                )
                conn.execute(
                    """INSERT OR IGNORE INTO world_edges
                       (session_id, from_node_id, to_node_id, travel_minutes, is_locked, skill_check_type, skill_check_dc, edge_type, is_bidirectional)
                       VALUES (?, ?, ?, 1, 0, '', 0, 'door', 1)""",
                    (sid, fid, tid),
                )

        _cleanup_legacy_threshold_edges(conn, sid)

        r_rules = {
            "realm_kind": "spirit_world",
            "is_primary_realm": False,
            "is_hidden": True,
            "discovered": False,
            "started_hidden": True,
            "comms_isolated": True,
            "npc_spillover": False,
            "restrict_companions": False,
            "has_local_safe_hub": True,
            "time_scale": 0.5,
            "exit_mode": "open",
            "portal_icon": "⛩️",
        }
        conn.execute(
            """INSERT OR IGNORE INTO world_nodes
               (session_id, node_id, parent_id, name, node_type, category, privacy_level,
                is_enclosed, is_transit_hub, access_tier, atmosphere, is_dynamic, state_json, created_at)
               VALUES (?, ?, NULL, ?, 'REALM', 'realm', 'public', 0, 0, 'open', '', 0, ?, ?)""",
            (sid, SPIRIT_REALM_ID, str(spirit_realm_seed.get("name") or "The Veiled Spirit Realm"), json.dumps(r_rules), now),
        )

        for z in spirit_realm_seed.get("zones") or []:
            z_id = str(z["id"])
            z_atm = json.dumps({"theme": z.get("theme", ""), "features": z.get("features", ""), "sensory": z.get("sensory", "")})
            z_st = {k: z[k] for k in ("is_hidden", "discovered", "is_frontier", "is_hub", "veil_village_key") if k in z}
            z_st["started_hidden"] = True
            conn.execute(
                """INSERT OR IGNORE INTO world_nodes
                   (session_id, node_id, parent_id, name, node_type, category, privacy_level,
                    is_enclosed, is_transit_hub, access_tier, atmosphere, is_dynamic, state_json, created_at)
                   VALUES (?, ?, ?, ?, 'ZONE', 'civic', 'public', 0, ?, 'open', ?, 0, ?, ?)""",
                (sid, z_id, SPIRIT_REALM_ID, z["name"], 1 if z.get("is_hub") else 0, z_atm, json.dumps(z_st), now),
            )
            fac_ids_in_z: List[str] = []
            for p in z.get("primary_locations") or []:
                p_id = str(p["id"])
                fac_ids_in_z.append(p_id)
                p_atm = json.dumps({"theme": p.get("theme", ""), "features": p.get("features", ""), "sensory": p.get("sensory", "")})
                p_st = {
                    k: p[k]
                    for k in ("is_hidden", "discovered", "veil_village_key", "veil_token_item", "is_anomalous", "privacy_level")
                    if k in p
                }
                p_st["started_hidden"] = True
                if p_id in ("loc_hidden_kitsune_village", "loc_hidden_bunian_village"):
                    conn.execute(
                        "UPDATE world_nodes SET parent_id = ?, name = ?, atmosphere = ? WHERE session_id = ? AND node_id = ?",
                        (z_id, p["name"], p_atm, sid, p_id),
                    )
                conn.execute(
                    """INSERT OR IGNORE INTO world_nodes
                       (session_id, node_id, parent_id, name, node_type, category, privacy_level,
                        is_enclosed, is_transit_hub, access_tier, atmosphere, is_dynamic, state_json, created_at)
                       VALUES (?, ?, ?, ?, 'FACILITY', 'civic', ?, 0, 0, ?, ?, 0, ?, ?)""",
                    (
                        sid, p_id, z_id, p["name"],
                        str(p.get("privacy_level") or "public"),
                        str(p.get("access_tier") or "open"),
                        p_atm, json.dumps(p_st), now,
                    ),
                )
                ent_id = None
                rm_ids: List[str] = []
                for sub in p.get("sub_locations") or []:
                    s_id = str(sub["id"])
                    rm_ids.append(s_id)
                    if sub.get("is_entrance") and not ent_id:
                        ent_id = s_id
                    s_st = {
                        k: sub[k]
                        for k in (
                            "privacy_level", "is_discreet", "is_private_intimate", "is_enclosed",
                            "is_entrance", "is_hidden", "discovered", "veil_village_key",
                            "veil_token_item", "is_anomalous", "is_transit_hub", "has_bounty_board",
                        )
                        if k in sub
                    }
                    s_st["started_hidden"] = True
                    if s_id in ("sub_kitsune_inner_plaza", "sub_bunian_inner_plaza"):
                        conn.execute(
                            "UPDATE world_nodes SET parent_id = ? WHERE session_id = ? AND node_id = ?",
                            (p_id, sid, s_id),
                        )
                    conn.execute(
                        """INSERT OR IGNORE INTO world_nodes
                           (session_id, node_id, parent_id, name, node_type, category, privacy_level,
                            is_enclosed, is_transit_hub, access_tier, atmosphere, is_dynamic, state_json, created_at)
                           VALUES (?, ?, ?, ?, 'ROOM', 'civic', ?, ?, ?, ?, ?, 0, ?, ?)""",
                        (
                            sid, s_id, p_id, sub["name"],
                            str(sub.get("privacy_level") or "public"),
                            int(bool(sub.get("is_enclosed", 1))),
                            int(bool(sub.get("is_transit_hub", 0))),
                            str(sub.get("access_tier") or "open"),
                            str(sub.get("sensory") or ""),
                            json.dumps(s_st), now,
                        ),
                    )
                if ent_id:
                    conn.execute(
                        """INSERT OR IGNORE INTO world_edges
                           (session_id, from_node_id, to_node_id, travel_minutes, is_locked, skill_check_type, skill_check_dc, edge_type, is_bidirectional)
                           VALUES (?, ?, ?, 1, 0, '', 0, 'door', 1)""",
                        (sid, p_id, ent_id),
                    )
                    for r_id in rm_ids:
                        if r_id != ent_id:
                            conn.execute(
                                """INSERT OR IGNORE INTO world_edges
                                   (session_id, from_node_id, to_node_id, travel_minutes, is_locked, skill_check_type, skill_check_dc, edge_type, is_bidirectional)
                                   VALUES (?, ?, ?, 2, 0, '', 0, 'door', 1)""",
                                (sid, ent_id, r_id),
                            )
            for idx_a in range(len(fac_ids_in_z)):
                for idx_b in range(idx_a + 1, len(fac_ids_in_z)):
                    if idx_b == idx_a + 1 or idx_a == 0:
                        conn.execute(
                            """INSERT OR IGNORE INTO world_edges
                               (session_id, from_node_id, to_node_id, travel_minutes, is_locked, skill_check_type, skill_check_dc, edge_type, is_bidirectional)
                               VALUES (?, ?, ?, 5, 0, '', 0, 'pathway', 1)""",
                            (sid, fac_ids_in_z[idx_a], fac_ids_in_z[idx_b]),
                        )

        existing_nids = {
            str(r["node_id"])
            for r in conn.execute("SELECT node_id FROM world_nodes WHERE session_id = ?", (sid,)).fetchall()
            if r["node_id"]
        }
        for u_nid, v_nid, mins, etype, locked, sc_t, sc_dc in (
            ("loc_hidden_kitsune_village", "loc_crossroads_night_market", 10, "pathway", 0, "", 0),
            ("loc_hidden_bunian_village", "loc_crossroads_night_market", 10, "pathway", 0, "", 0),
            ("loc_hidden_ghoul_village", "loc_crossroads_night_market", 10, "pathway", 0, "", 0),
            ("loc_crossroads_night_market", "loc_wilds_ward_outpost", 8, "pathway", 0, "", 0),
            ("loc_crossroads_night_market", "loc_peaks_split_torii", 8, "pathway", 0, "", 0),
            ("loc_crossroads_night_market", "loc_mire_bell_bog", 8, "pathway", 0, "", 0),
            ("loc_crossroads_night_market", "loc_boneyard_barrow_moor", 8, "pathway", 0, "", 0),
            ("loc_peaks_split_torii", "loc_wilds_ward_outpost", 10, "pathway", 0, "", 0),
            ("loc_wilds_ward_outpost", "loc_mire_bell_bog", 10, "pathway", 0, "", 0),
            ("loc_mire_bell_bog", "loc_boneyard_barrow_moor", 10, "pathway", 0, "", 0),
            ("loc_boneyard_barrow_moor", "loc_peaks_split_torii", 10, "pathway", 0, "", 0),
            ("loc_hidden_kitsune_village", "loc_peaks_split_torii", 9, "pathway", 0, "", 0),
            ("loc_hidden_bunian_village", "loc_mire_bell_bog", 9, "pathway", 0, "", 0),
            ("loc_hidden_ghoul_village", "loc_boneyard_barrow_moor", 9, "pathway", 0, "", 0),
            ("sub_kitsune_inner_plaza", "sub_bunian_inner_plaza", 2, "leyline_spirit_passage", 1, "PER", 15),
            ("sub_kitsune_leyline_shrine", "sub_bunian_orchid_spring", 2, "leyline_spirit_passage", 1, "PER", 15),
        ):
            if u_nid not in existing_nids or v_nid not in existing_nids:
                continue
            conn.execute(
                """INSERT OR IGNORE INTO world_edges
                   (session_id, from_node_id, to_node_id, travel_minutes, is_locked, skill_check_type, skill_check_dc, edge_type, is_bidirectional)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (sid, u_nid, v_nid, mins, locked, sc_t, sc_dc, etype),
            )
        for p_spec in seed_data.get("realm_portals") or []:
            if p_spec.get("edge_type") != "leyline_spirit_passage":
                continue
            u_nid = str(p_spec["from_node_id"])
            v_nid = str(p_spec["to_node_id"])
            if u_nid not in existing_nids or v_nid not in existing_nids:
                continue
            is_lk = int(p_spec.get("is_locked") or 0)
            conn.execute(
                """INSERT OR IGNORE INTO world_edges
                   (session_id, from_node_id, to_node_id, travel_minutes, is_locked, skill_check_type, skill_check_dc, edge_type, is_bidirectional)
                   VALUES (?, ?, ?, ?, ?, '', 0, 'leyline_spirit_passage', 1)""",
                (sid, u_nid, v_nid, int(p_spec.get("travel_minutes") or 2), is_lk),
            )
            u_r = "realm_city_metro" if u_nid in ("loc_et_fox_torii_tunnel", "loc_bunian_threshold_glade", "sub_uc_black_font") else SPIRIT_REALM_ID
            v_r = "realm_city_metro" if v_nid == CHINATOWN_SHORTCUT_HUMAN_NODE else SPIRIT_REALM_ID
            for src, dst, t_rid, lbl_key in ((u_nid, v_nid, v_r, "label"), (v_nid, u_nid, u_r, "return_label")):
                r_n = conn.execute("SELECT state_json FROM world_nodes WHERE session_id = ? AND node_id = ?", (sid, src)).fetchone()
                nst = _parse_json_dict(r_n["state_json"] if r_n else "{}")
                p_map = dict(nst.get("portals") or {})
                p_entry: Dict[str, Any] = {
                    "target_realm_id": t_rid,
                    "label": str(p_spec.get(lbl_key) or p_spec.get("label") or ""),
                    "icon": str(p_spec.get("icon") or "⛩️"),
                    "is_hidden_portal": True,
                    "started_hidden_portal": True,
                    "visible_when_target_hidden": False,
                    "is_locked": bool(is_lk),
                    "require_explicit_portal_unlock": True,
                }
                if p_spec.get("veil_village_key"):
                    p_entry["veil_village_key"] = p_spec["veil_village_key"]
                if p_spec.get("spirit_side_unlock_only"):
                    p_entry["spirit_side_unlock_only"] = True
                p_map[dst] = p_entry
                nst["portals"] = p_map
                conn.execute(
                    "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
                    (json.dumps(nst), sid, src),
                )

        from .folklore_spirit_naming import ensure_session_spirit_procedural_names
        ensure_session_spirit_procedural_names(
            sid,
            persist_db=True,
            conn=conn,
            sync_world_nodes=True,
            preserve_discovered_names=True,
        )
        cur_nid = str(sr["current_node_id"] or "")
        for vk in ("kitsune", "bunian", "ghoul"):
            in_v = (
                (vk == "kitsune" and cur_nid.startswith("sub_kitsune_"))
                or (vk == "bunian" and cur_nid.startswith("sub_bunian_"))
                or (vk == "ghoul" and cur_nid.startswith("sub_ghoul_"))
            )
            if pre_attuned.get(vk) or in_v:
                on_enter_village_from_human_threshold(sid, vk, turn_number=1, conn=conn)

        _refresh_reparented_session_locations(
            conn,
            sid,
            [
                "loc_et_fox_torii_tunnel",
                "loc_bunian_threshold_glade",
                "sub_kitsune_inner_plaza",
                "sub_kitsune_sovereign_pavilion",
                "sub_kitsune_spirit_apothecary",
                "sub_kitsune_leyline_shrine",
                "sub_bunian_inner_plaza",
                "sub_bunian_royal_istana",
                "sub_bunian_pusaka_hall",
                "sub_bunian_orchid_spring",
                "sub_ghoul_inner_plaza",
                "sub_ghoul_sovereign_manor",
                "sub_ghoul_curio_morgue",
                "sub_ghoul_leyline_crypt",
            ],
            cur_nid,
        )
        migrated += 1

    return migrated


def _insert_seed_facility_with_rooms(
    conn: Any,
    sid: int,
    parent_zone_id: str,
    fac_obj: Dict[str, Any],
    *,
    reveal_public: bool = False,
    now: float,
) -> int:
    """Inserts a seed facility + rooms + interior doors if missing, returning node insert count."""
    changed = 0
    f_id = str(fac_obj["id"])
    f_atm = json.dumps({
        "theme": fac_obj.get("theme", ""),
        "features": fac_obj.get("features", ""),
        "sensory": fac_obj.get("sensory", ""),
    })
    f_st = {
        k: fac_obj[k]
        for k in ("is_hidden", "discovered", "veil_village_key", "veil_token_item", "is_anomalous", "privacy_level")
        if k in fac_obj
    }
    f_st["started_hidden"] = bool(fac_obj.get("is_hidden", True))
    if reveal_public and str(fac_obj.get("access_tier") or "open").lower() != "private":
        f_st["is_hidden"] = False
        f_st["discovered"] = True
    cur = conn.execute(
        """INSERT OR IGNORE INTO world_nodes
           (session_id, node_id, parent_id, name, node_type, category, privacy_level,
            is_enclosed, is_transit_hub, access_tier, atmosphere, is_dynamic, state_json, created_at)
           VALUES (?, ?, ?, ?, 'FACILITY', 'civic', ?, 0, 0, ?, ?, 0, ?, ?)""",
        (
            sid,
            f_id,
            parent_zone_id,
            str(fac_obj["name"]),
            str(fac_obj.get("privacy_level") or "public"),
            str(fac_obj.get("access_tier") or "open"),
            f_atm,
            json.dumps(f_st),
            now,
        ),
    )
    changed += int(cur.rowcount or 0)
    ent_id = None
    rm_ids: List[str] = []
    for sub in fac_obj.get("sub_locations") or []:
        s_id = str(sub["id"])
        rm_ids.append(s_id)
        if sub.get("is_entrance") and not ent_id:
            ent_id = s_id
        s_st = {
            k: sub[k]
            for k in (
                "privacy_level", "is_discreet", "is_private_intimate", "is_enclosed",
                "is_entrance", "is_hidden", "discovered", "veil_village_key",
                "veil_token_item", "is_anomalous", "is_transit_hub", "has_bounty_board",
            )
            if k in sub
        }
        s_st["started_hidden"] = bool(sub.get("is_hidden", True))
        if reveal_public and str(sub.get("access_tier") or fac_obj.get("access_tier") or "open").lower() != "private":
            s_st["is_hidden"] = False
            s_st["discovered"] = True
        r_cur = conn.execute(
            """INSERT OR IGNORE INTO world_nodes
               (session_id, node_id, parent_id, name, node_type, category, privacy_level,
                is_enclosed, is_transit_hub, access_tier, atmosphere, is_dynamic, state_json, created_at)
               VALUES (?, ?, ?, ?, 'ROOM', 'civic', ?, ?, ?, ?, ?, 0, ?, ?)""",
            (
                sid,
                s_id,
                f_id,
                str(sub["name"]),
                str(sub.get("privacy_level") or "public"),
                int(bool(sub.get("is_enclosed", 1))),
                int(bool(sub.get("is_transit_hub", 0))),
                str(sub.get("access_tier") or "open"),
                str(sub.get("sensory") or ""),
                json.dumps(s_st),
                now,
            ),
        )
        changed += int(r_cur.rowcount or 0)
    if ent_id:
        conn.execute(
            """INSERT OR IGNORE INTO world_edges
               (session_id, from_node_id, to_node_id, travel_minutes, is_locked, skill_check_type, skill_check_dc, edge_type, is_bidirectional)
               VALUES (?, ?, ?, 1, 0, '', 0, 'door', 1)""",
            (sid, f_id, ent_id),
        )
        for r_id in rm_ids:
            if r_id != ent_id:
                conn.execute(
                    """INSERT OR IGNORE INTO world_edges
                       (session_id, from_node_id, to_node_id, travel_minutes, is_locked, skill_check_type, skill_check_dc, edge_type, is_bidirectional)
                       VALUES (?, ?, ?, 2, 0, '', 0, 'door', 1)""",
                    (sid, ent_id, r_id),
                )
    return changed


def backfill_folklore_spirit_realm_v64(
    conn: Any,
    session_id: Optional[int] = None,
    *,
    naming_seed_session_id: Optional[int] = None,
) -> int:
    """
    Idempotent Migration 64 (`folklore_spirit_realm_expansion_v64`) legacy save backfill:
    - Runs v52 structural backfill if missing any Spirit Realm nodes/zones/wings
    - Backfills Undercity `loc_uc_ossuary_catacombs` / `sub_uc_black_font` + Ghoul Crypt portal
    - Initializes procedural court/zone names while preserving already-discovered pre-v64 names
    - Reveals 3 frontier biomes (`peaks`, `mire`, `boneyard`) & Bazaar Silk/Curio wings for
      saves that already entered `realm_veiled_spirit_world` (keeping `zone_spirit_ghoul` hidden)
    - Upgrades `folklore_villager_roster` with Ghoul & Crossroads cast + hydrates court leadership rosters
    Returns count of sessions mutated (strictly 0 on repeat runs).
    """
    from .folklore_spirit_courts import (
        SPIRIT_BONEYARD_ZONE_ID,
        SPIRIT_MIRE_ZONE_ID,
        SPIRIT_PEAKS_ZONE_ID,
        sync_spirit_court_leadership_and_diplomacy,
    )
    from .folklore_spirit_naming import ensure_session_spirit_procedural_names
    from .seeds import get_scenario_seed_data

    migrated = backfill_folklore_spirit_realm_v52(conn, session_id=session_id)

    s_rows = _list_sessions_for_backfill(conn, session_id=session_id)

    now = time.time()
    for sr in s_rows:
        sid = int(sr["id"])
        scen = str(sr["scenario"] or "")
        if not (
            scenario_data.is_anomalous_incursions_scenario(scen)
            or scenario_data.is_anomalous_high_school_scenario(scen)
            or "urban_anomalies" in scen.lower()
        ):
            continue
        has_woods = conn.execute(
            "SELECT 1 FROM world_nodes WHERE session_id = ? AND node_id = 'zone_woods_reserve' LIMIT 1",
            (sid,),
        ).fetchone()
        if not has_woods:
            continue

        sr_ex = _parse_json_dict(sr["extra_json"])
        sr_srs = sr_ex.get("spirit_realm_state") if isinstance(sr_ex.get("spirit_realm_state"), dict) else {}
        if (
            sr_srs.get("v64_backfilled")
            and isinstance(sr_srs.get("procedural_names"), dict)
            and len(sr_srs.get("procedural_names") or {}) >= 3
        ):
            _v64_sentinels = (
                "zone_spirit_ghoul",
                SPIRIT_PEAKS_ZONE_ID,
                SPIRIT_MIRE_ZONE_ID,
                SPIRIT_BONEYARD_ZONE_ID,
                "loc_uc_ossuary_catacombs",
                "sub_crossroads_kitsune_alley",
                "sub_crossroads_bunian_arcade",
                "sub_crossroads_curio_arcade",
            )
            _present_cnt = conn.execute(
                "SELECT COUNT(DISTINCT node_id) FROM world_nodes WHERE session_id = ? AND node_id IN (?, ?, ?, ?, ?, ?, ?, ?)",
                (sid, *_v64_sentinels),
            ).fetchone()[0]
            if int(_present_cnt or 0) == len(_v64_sentinels):
                continue

        sid_changed = False
        seed_data = get_scenario_seed_data(scen) or {}
        spirit_realm_seed = next(
            (r for r in (seed_data.get("realms") or []) if isinstance(r, dict) and r.get("id") == SPIRIT_REALM_ID),
            None,
        )

        # 1. Ensure Undercity `loc_uc_ossuary_catacombs` / `sub_uc_black_font` & Ghoul threshold portal exist
        has_uc_zone = conn.execute(
            "SELECT 1 FROM world_nodes WHERE session_id = ? AND node_id = 'zone_undercity' LIMIT 1",
            (sid,),
        ).fetchone()
        has_black_font = conn.execute(
            "SELECT 1 FROM world_nodes WHERE session_id = ? AND node_id = 'sub_uc_black_font' LIMIT 1",
            (sid,),
        ).fetchone()
        if has_uc_zone and not has_black_font:
            uc_zone = next((z for z in (seed_data.get("zones") or []) if z.get("id") == "zone_undercity"), None)
            cat_fac = next(
                (p for p in (uc_zone or {}).get("primary_locations") or [] if p.get("id") == "loc_uc_ossuary_catacombs"),
                None,
            )
            if cat_fac and _insert_seed_facility_with_rooms(conn, sid, "zone_undercity", cat_fac, reveal_public=True, now=now) > 0:
                sid_changed = True
                for p_spec in seed_data.get("realm_portals") or []:
                    if p_spec.get("veil_village_key") != "ghoul":
                        continue
                    u_n = str(p_spec["from_node_id"])
                    v_n = str(p_spec["to_node_id"])
                    conn.execute(
                        """INSERT OR IGNORE INTO world_edges
                           (session_id, from_node_id, to_node_id, travel_minutes, is_locked, skill_check_type, skill_check_dc, edge_type, is_bidirectional)
                           VALUES (?, ?, ?, ?, 0, '', 0, 'leyline_spirit_passage', 1)""",
                        (sid, u_n, v_n, int(p_spec.get("travel_minutes") or 2)),
                    )
                    for src, dst, t_r, lk in ((u_n, v_n, SPIRIT_REALM_ID, "label"), (v_n, u_n, "realm_city_metro", "return_label")):
                        rn = conn.execute("SELECT state_json FROM world_nodes WHERE session_id = ? AND node_id = ?", (sid, src)).fetchone()
                        if rn:
                            pst = _parse_json_dict(rn["state_json"])
                            pmap = dict(pst.get("portals") or {})
                            if dst not in pmap:
                                pmap[dst] = {
                                    "target_realm_id": t_r,
                                    "label": str(p_spec.get(lk) or p_spec.get("label") or ""),
                                    "icon": str(p_spec.get("icon") or "🕯️"),
                                    "is_hidden_portal": True,
                                    "started_hidden_portal": True,
                                    "visible_when_target_hidden": False,
                                    "is_locked": False,
                                    "require_explicit_portal_unlock": True,
                                    "veil_village_key": "ghoul",
                                }
                                pst["portals"] = pmap
                                conn.execute(
                                    "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
                                    (json.dumps(pst), sid, src),
                                )

        # 2. Ensure missing v2 Spirit Realm zones / Bazaar wings exist even on partial saves
        if spirit_realm_seed:
            x_row = conn.execute(
                "SELECT state_json FROM world_nodes WHERE session_id = ? AND node_id = 'zone_spirit_crossroads' LIMIT 1",
                (sid,),
            ).fetchone()
            cr_hidden = True if not x_row else bool(_parse_json_dict(x_row["state_json"]).get("is_hidden", True))
            srs_now = get_spirit_realm_state(sid, conn=conn)
            entered_realm = bool(srs_now.get("crossroads_visited_turn") or srs_now.get("villages_entered") or not cr_hidden)
            for wing_id in ("sub_crossroads_kitsune_alley", "sub_crossroads_bunian_arcade", "sub_crossroads_curio_arcade"):
                w_exists = conn.execute(
                    "SELECT 1 FROM world_nodes WHERE session_id = ? AND node_id = ? LIMIT 1",
                    (sid, wing_id),
                ).fetchone()
                if not w_exists:
                    cr_z = next((z for z in (spirit_realm_seed.get("zones") or []) if z.get("id") == "zone_spirit_crossroads"), None)
                    mkt_fac = next((p for p in (cr_z or {}).get("primary_locations") or [] if p.get("id") == "loc_crossroads_night_market"), None)
                    if mkt_fac and _insert_seed_facility_with_rooms(conn, sid, "zone_spirit_crossroads", mkt_fac, reveal_public=entered_realm, now=now) > 0:
                        sid_changed = True
            for f_zid in (SPIRIT_PEAKS_ZONE_ID, SPIRIT_MIRE_ZONE_ID, SPIRIT_BONEYARD_ZONE_ID):
                fz_exists = conn.execute(
                    "SELECT 1 FROM world_nodes WHERE session_id = ? AND node_id = ? LIMIT 1",
                    (sid, f_zid),
                ).fetchone()
                if not fz_exists:
                    z_obj = next((z for z in (spirit_realm_seed.get("zones") or []) if z.get("id") == f_zid), None)
                    if z_obj:
                        z_atm = json.dumps({"theme": z_obj.get("theme", ""), "features": z_obj.get("features", ""), "sensory": z_obj.get("sensory", "")})
                        z_st = {k: z_obj[k] for k in ("is_hidden", "discovered", "is_frontier", "is_hub") if k in z_obj}
                        z_st["started_hidden"] = True
                        if entered_realm:
                            z_st["is_hidden"] = False
                            z_st["discovered"] = True
                        conn.execute(
                            """INSERT OR IGNORE INTO world_nodes
                               (session_id, node_id, parent_id, name, node_type, category, privacy_level,
                                is_enclosed, is_transit_hub, access_tier, atmosphere, is_dynamic, state_json, created_at)
                               VALUES (?, ?, ?, ?, 'ZONE', 'civic', 'public', 0, 0, 'open', ?, 0, ?, ?)""",
                            (sid, f_zid, SPIRIT_REALM_ID, str(z_obj["name"]), z_atm, json.dumps(z_st), now),
                        )
                        for pf in z_obj.get("primary_locations") or []:
                            _insert_seed_facility_with_rooms(conn, sid, f_zid, pf, reveal_public=entered_realm, now=now)
                        sid_changed = True

        # 3. Procedural court & zone naming (capture already-discovered pre-v64 names without overwriting)
        ex_row = conn.execute("SELECT extra_json FROM sessions WHERE id = ?", (sid,)).fetchone()
        raw_ex = _parse_json_dict(ex_row["extra_json"] if ex_row else "{}")
        srs = dict(raw_ex.get("spirit_realm_state") or {})
        proc_existing = srs.get("procedural_names")
        if not isinstance(proc_existing, dict) or len(proc_existing) < 3:
            ensure_session_spirit_procedural_names(
                sid,
                persist_db=True,
                conn=conn,
                sync_world_nodes=True,
                preserve_discovered_names=True,
                naming_seed_session_id=naming_seed_session_id if (session_id is not None and int(sid) == int(session_id)) else None,
            )
            sid_changed = True

        # 4. If player has already entered Spirit Realm, reveal 3 frontiers & 2 Bazaar wings (keep Ghoul hidden unless discovered)
        x_row2 = conn.execute(
            "SELECT state_json FROM world_nodes WHERE session_id = ? AND node_id = 'zone_spirit_crossroads' LIMIT 1",
            (sid,),
        ).fetchone()
        cr_open = bool(x_row2 and not _parse_json_dict(x_row2["state_json"]).get("is_hidden", True))
        if srs.get("crossroads_visited_turn") or srs.get("villages_entered") or cr_open:
            reveal_nids: List[str] = ["sub_crossroads_kitsune_alley", "sub_crossroads_bunian_arcade", "sub_crossroads_curio_arcade"]
            for fz in (SPIRIT_PEAKS_ZONE_ID, SPIRIT_MIRE_ZONE_ID, SPIRIT_BONEYARD_ZONE_ID):
                reveal_nids.append(fz)
                fac_rows = conn.execute(
                    "SELECT node_id FROM world_nodes WHERE session_id = ? AND parent_id = ? AND node_type = 'FACILITY'",
                    (sid, fz),
                ).fetchall()
                for fr in fac_rows:
                    f_nid = str(fr["node_id"])
                    reveal_nids.append(f_nid)
                    rm_rows = conn.execute(
                        "SELECT node_id FROM world_nodes WHERE session_id = ? AND parent_id = ? AND node_type = 'ROOM'",
                        (sid, f_nid),
                    ).fetchall()
                    for rr in rm_rows:
                        reveal_nids.append(str(rr["node_id"]))
            for r_nid in reveal_nids:
                rn = conn.execute(
                    "SELECT state_json, access_tier FROM world_nodes WHERE session_id = ? AND node_id = ?",
                    (sid, r_nid),
                ).fetchone()
                if rn and str(rn["access_tier"] or "open").lower() != "private":
                    rst = _parse_json_dict(rn["state_json"])
                    if rst.get("is_hidden", True) or not rst.get("discovered"):
                        rst["is_hidden"] = False
                        rst["discovered"] = True
                        conn.execute(
                            "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
                            (json.dumps(rst), sid, r_nid),
                        )
                        sid_changed = True

        # 5. Backfill Ghoul + Crossroads villagers in `folklore_villager_roster` without clobbering hydrated/befriended state
        ex_row2 = conn.execute("SELECT extra_json FROM sessions WHERE id = ?", (sid,)).fetchone()
        raw_ex2 = _parse_json_dict(ex_row2["extra_json"] if ex_row2 else "{}")
        cur_roster = raw_ex2.get("folklore_villager_roster")
        has_ghoul_roster = isinstance(cur_roster, list) and any(
            isinstance(e, dict) and e.get("folklore_village") == "ghoul" for e in cur_roster
        )
        if not has_ghoul_roster:
            from mechanics.social.folklore_roster import ensure_folklore_villager_roster
            ensure_folklore_villager_roster(sid, scen_key=scen, persist_db=True, conn=conn)
            sid_changed = True

        # 6. Hydrate leadership rosters & diplomacy links on any already-discovered spirit_court factions
        for vk_c, f_spec in SPIRIT_COURT_FACTIONS.items():
            frow = conn.execute(
                "SELECT leadership_roster_json, rival_faction_ids_json FROM factions WHERE session_id = ? AND faction_id = ?",
                (sid, f_spec["faction_id"]),
            ).fetchone()
            if frow:
                raw_lr = str(frow["leadership_roster_json"] or "").strip()
                raw_rv = str(frow["rival_faction_ids_json"] or "").strip()
                if raw_lr in ("", "[]", "null") or raw_rv in ("", "[]", "null"):
                    sync_spirit_court_leadership_and_diplomacy(sid, vk_c, conn=conn)
                    sid_changed = True

        # 7. Stamp sentinel idempotently
        if not srs.get("v64_backfilled"):
            _mutate_spirit_realm_state(conn, sid, lambda d: d.__setitem__("v64_backfilled", True))
            sid_changed = True

        if sid_changed:
            migrated += 1

    return migrated


def rollback_spirit_realm_state_after_turn(
    session_id: int,
    turn_number: int,
    conn: Any = None,
) -> Dict[str, int]:
    """
    Reverts Spirit Realm mutations strictly after `turn_number`:
    - Re-hides `ZONE`/`FACILITY`/`ROOM` nodes in `realm_veiled_spirit_world` with `discovered_turn > turn_number`
    - Preserves `sub_crossroads_tea_hall` `is_transit_hub=1` while resetting only village inner plazas' dynamic `is_transit_hub`
    - Re-hides portals with `portal_revealed_turn > turn_number` & re-locks Chinatown shortcut (+ refunds gold)
    - Deletes `spirit_court` factions with `discovered_turn > turn_number` & reverts `rep_ledger` deltas
    """
    from .folklore_spirit_realm import is_node_in_spirit_realm

    counts = {
        "spirit_nodes_rehidden": 0,
        "spirit_portals_rehidden": 0,
        "spirit_courts_deleted": 0,
        "spirit_rep_reverted": 0,
        "ghoul_tolls_refunded": 0,
        "cottages_reverted": 0,
        "commissions_reverted": 0,
    }
    if not session_id:
        return counts
    t_num = int(turn_number)

    with _uow_ctx(conn) as c:
        srs = get_spirit_realm_state(int(session_id), conn=c)

        all_nodes = c.execute(
            "SELECT node_id, parent_id, node_type, state_json FROM world_nodes WHERE session_id = ?",
            (int(session_id),),
        ).fetchall()
        nodes_map = {str(r["node_id"]): dict(r) for r in all_nodes if r["node_id"]}
        for nid, n in nodes_map.items():
            if not is_node_in_spirit_realm(int(session_id), nid, nodes_by_id=nodes_map) or nid == SPIRIT_REALM_ID:
                continue
            st = _parse_json_dict(n.get("state_json"))
            disc_t = int(st.get("discovered_turn") or 0)
            unlk_t = int(st.get("unlocked_turn") or 0)
            should_relock = bool(nid in ALL_SPIRIT_GUEST_FACILITY_IDS and unlk_t > t_num)
            should_rehide = bool(
                (disc_t > t_num or (should_relock and (disc_t == 0 or disc_t > t_num)))
                and st.get("started_hidden", True)
            )
            if should_rehide or should_relock:
                if should_rehide:
                    st["is_hidden"] = True
                    st["discovered"] = False
                    st.pop("discovered_turn", None)
                if should_relock or unlk_t > t_num:
                    st["unlocked_permanent"] = False
                    st.pop("unlocked_turn", None)
                    st.pop("deed_owned", None)
                    st.pop("granted_by_standing", None)
                if should_rehide and nid in ("sub_kitsune_inner_plaza", "sub_bunian_inner_plaza", "sub_ghoul_inner_plaza"):
                    c.execute(
                        "UPDATE world_nodes SET state_json = ?, is_transit_hub = 0 WHERE session_id = ? AND node_id = ?",
                        (json.dumps(st), int(session_id), nid),
                    )
                else:
                    c.execute(
                        "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
                        (json.dumps(st), int(session_id), nid),
                    )
                counts["spirit_nodes_rehidden"] += 1

        p_rows = c.execute(
            "SELECT node_id, state_json FROM world_nodes WHERE session_id = ? AND state_json LIKE '%portal_revealed_turn%'",
            (int(session_id),),
        ).fetchall()
        for pr in p_rows:
            pst = _parse_json_dict(pr["state_json"])
            portals = pst.get("portals")
            if not isinstance(portals, dict):
                continue
            dirty = False
            for dst_k, p_meta in portals.items():
                if isinstance(p_meta, dict) and int(p_meta.get("portal_revealed_turn") or 0) > t_num:
                    p_meta["is_hidden_portal"] = True
                    p_meta.pop("portal_revealed_turn", None)
                    if p_meta.get("spirit_side_unlock_only"):
                        p_meta["is_locked"] = True
                    dirty = True
                    counts["spirit_portals_rehidden"] += 1
            if dirty:
                pst["portals"] = portals
                c.execute(
                    "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
                    (json.dumps(pst), int(session_id), pr["node_id"]),
                )

        if int(srs.get("chinatown_shortcut_unlocked_turn") or 0) > t_num:
            c.execute(
                """UPDATE world_edges
                   SET is_locked = 1
                   WHERE session_id = ?
                     AND ((from_node_id = ? AND to_node_id = ?) OR (from_node_id = ? AND to_node_id = ?))""",
                (
                    int(session_id),
                    CHINATOWN_SHORTCUT_SPIRIT_NODE,
                    CHINATOWN_SHORTCUT_HUMAN_NODE,
                    CHINATOWN_SHORTCUT_HUMAN_NODE,
                    CHINATOWN_SHORTCUT_SPIRIT_NODE,
                ),
            )
            for src_n, dst_n in (
                (CHINATOWN_SHORTCUT_SPIRIT_NODE, CHINATOWN_SHORTCUT_HUMAN_NODE),
                (CHINATOWN_SHORTCUT_HUMAN_NODE, CHINATOWN_SHORTCUT_SPIRIT_NODE),
            ):
                sc_row = c.execute(
                    "SELECT state_json FROM world_nodes WHERE session_id = ? AND node_id = ?",
                    (int(session_id), src_n),
                ).fetchone()
                if sc_row:
                    sc_st = _parse_json_dict(sc_row["state_json"])
                    sc_portals = sc_st.get("portals")
                    if isinstance(sc_portals, dict) and isinstance(sc_portals.get(dst_n), dict):
                        sc_portals[dst_n]["is_locked"] = True
                        sc_st["portals"] = sc_portals
                        c.execute(
                            "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
                            (json.dumps(sc_st), int(session_id), src_n),
                        )
            refund_g = int(srs.get("chinatown_shortcut_gold_paid") or 0)
            buyer_cid = int(srs.get("chinatown_shortcut_buyer_cid") or 0)
            if refund_g > 0 and buyer_cid:
                c.execute("UPDATE characters SET gold = gold + ? WHERE id = ?", (refund_g, buyer_cid))

        if int(srs.get("ghoul_plaza_clearance_turn") or 0) > t_num:
            g_refund = int(srs.get("ghoul_plaza_toll_gold_paid") or 0)
            g_payer = int(srs.get("ghoul_plaza_toll_payer_cid") or 0)
            if g_refund > 0 and g_payer:
                c.execute("UPDATE characters SET gold = gold + ? WHERE id = ?", (g_refund, g_payer))
                counts["ghoul_tolls_refunded"] += 1

        from .folklore_spirit_courts import SPIRIT_GUEST_COTTAGE_SPEC
        granted_map = dict(srs.get("granted_cottages") or {})
        for c_vk, c_turn in granted_map.items():
            if int(c_turn or 0) > t_num:
                c_spec = SPIRIT_GUEST_COTTAGE_SPEC.get(c_vk)
                if c_spec:
                    c.execute(
                        "DELETE FROM player_properties WHERE session_id = ? AND property_id = ?",
                        (int(session_id), c_spec["property_id"]),
                    )
                    for g_nid in (c_spec["facility_node_id"], *c_spec["room_ids"]):
                        gr = c.execute(
                            "SELECT state_json FROM world_nodes WHERE session_id = ? AND node_id = ?",
                            (int(session_id), g_nid),
                        ).fetchone()
                        if gr:
                            gst = _parse_json_dict(gr["state_json"])
                            g_disc_t = int(gst.get("discovered_turn") or 0)
                            if (g_disc_t == 0 or g_disc_t > t_num) and gst.get("started_hidden", True):
                                gst["is_hidden"] = True
                                gst["discovered"] = False
                                gst.pop("discovered_turn", None)
                            gst["unlocked_permanent"] = False
                            gst.pop("unlocked_turn", None)
                            gst.pop("deed_owned", None)
                            gst.pop("granted_by_standing", None)
                            c.execute(
                                "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
                                (json.dumps(gst), int(session_id), g_nid),
                            )
                    counts["cottages_reverted"] += 1

        # Revert Spirit Court commissions created or accepted strictly after `turn_number`
        sc_rows = c.execute(
            "SELECT quest_id, quest_notes FROM quests WHERE session_id = ? AND (quest_id LIKE 'SPC-%' OR quest_id LIKE 'EVT-SPC-%')",
            (int(session_id),),
        ).fetchall()
        import re as _rb_re
        for scr in sc_rows:
            sqid = str(scr["quest_id"] or "")
            snote = str(scr["quest_notes"] or "")
            m_ct = _rb_re.search(r"created_turn\s*:\s*(\d+)", snote)
            if m_ct and int(m_ct.group(1)) > t_num:
                c.execute("DELETE FROM quest_waypoints WHERE session_id = ? AND quest_id = ?", (int(session_id), sqid))
                c.execute("DELETE FROM quest_dossiers WHERE session_id = ? AND quest_id = ?", (int(session_id), sqid))
                c.execute("DELETE FROM quests WHERE session_id = ? AND quest_id = ?", (int(session_id), sqid))
                counts["commissions_reverted"] += 1

        acc_map = dict(srs.get("accepted_spirit_commissions") or {})
        for a_qid, a_turn in acc_map.items():
            if int(a_turn or 0) > t_num:
                upd_q = c.execute(
                    "UPDATE quests SET status = 'Available' WHERE session_id = ? AND quest_id = ? AND status IN ('Active', 'In Progress', 'Completed', 'Failed')",
                    (int(session_id), a_qid),
                )
                if upd_q.rowcount:
                    counts["commissions_reverted"] += 1

        rep_ledger = list(srs.get("rep_ledger") or [])
        kept_ledger = [
            entry for entry in rep_ledger
            if isinstance(entry, dict) and int(entry.get("turn") or 0) <= t_num
        ]
        for entry in reversed(rep_ledger):
            if not isinstance(entry, dict):
                continue
            if int(entry.get("turn") or 0) > t_num:
                vk = str(entry.get("village_key") or "")
                spec = SPIRIT_COURT_FACTIONS.get(vk)
                if spec:
                    if "prev_score" in entry and entry.get("prev_score") is not None:
                        new_r = max(-100, min(100, int(entry["prev_score"])))
                    else:
                        cur_r = _get_court_rep_sql(c, int(session_id), vk)
                        new_r = max(-100, min(100, cur_r - int(entry.get("delta") or 0)))
                    c.execute(
                        "UPDATE factions SET reputation_score = ? WHERE session_id = ? AND faction_id = ?",
                        (new_r, int(session_id), spec["faction_id"]),
                    )
                    counts["spirit_rep_reverted"] += 1

        heat_ledger = list(srs.get("agency_heat_ledger") or [])
        kept_heat_ledger = [
            entry for entry in heat_ledger
            if isinstance(entry, dict) and int(entry.get("turn") or 0) <= t_num
        ]
        for entry in reversed(heat_ledger):
            if not isinstance(entry, dict):
                continue
            if int(entry.get("turn") or 0) > t_num:
                h_fid = str(entry.get("faction_id") or "").strip()
                h_delta = int(entry.get("delta") or 0)
                has_prev = "prev_score" in entry and entry.get("prev_score") is not None
                if h_fid and (h_delta or has_prev):
                    f_row = c.execute(
                        "SELECT reputation_score FROM factions WHERE session_id = ? AND faction_id = ?",
                        (int(session_id), h_fid),
                    ).fetchone()
                    if f_row is not None:
                        if has_prev:
                            new_pa = max(-100, min(100, int(entry["prev_score"])))
                        else:
                            cur_pa = int(f_row["reputation_score"] or 0)
                            new_pa = max(-100, min(100, cur_pa - h_delta))
                        c.execute(
                            "UPDATE factions SET reputation_score = ? WHERE session_id = ? AND faction_id = ?",
                            (new_pa, int(session_id), h_fid),
                        )
                        counts["spirit_rep_reverted"] += 1

        courts = dict(srs.get("spirit_courts") or {})
        for vk in list(courts.keys()):
            c_info = courts.get(vk) or {}
            if int(c_info.get("discovered_turn") or 0) > t_num:
                fid = str(c_info.get("faction_id") or (SPIRIT_COURT_FACTIONS.get(vk) or {}).get("faction_id") or "")
                if fid:
                    c.execute("DELETE FROM factions WHERE session_id = ? AND faction_id = ?", (int(session_id), fid))
                    counts["spirit_courts_deleted"] += 1
                courts.pop(vk, None)

        if srs:
            def _prune(d: Dict[str, Any]) -> None:
                d["spirit_courts"] = courts
                d["rep_ledger"] = kept_ledger
                d["agency_heat_ledger"] = kept_heat_ledger
                for map_k in ("villages_entered", "overland_discovered", "backdoor_attuned", "granted_cottages"):
                    sub_m = dict(d.get(map_k) or {})
                    d[map_k] = {k: v for k, v in sub_m.items() if int(v or 0) <= t_num}
                if int(d.get("crossroads_visited_turn") or 0) > t_num:
                    d.pop("crossroads_visited_turn", None)
                if int(d.get("chinatown_shortcut_unlocked_turn") or 0) > t_num:
                    for k in (
                        "chinatown_shortcut_unlocked_turn",
                        "chinatown_shortcut_method",
                        "chinatown_shortcut_gold_paid",
                        "chinatown_shortcut_buyer_cid",
                        "lantern_waiver_used",
                    ):
                        d.pop(k, None)
                buff = d.get("active_sparring_buff")
                if isinstance(buff, dict) and int(buff.get("granted_turn") or 0) > t_num:
                    d.pop("active_sparring_buff", None)
                if int(d.get("ghoul_plaza_clearance_turn") or 0) > t_num:
                    prev_day = int(d.get("prev_ghoul_plaza_clearance_day") or 0)
                    if prev_day > 0:
                        d["ghoul_plaza_clearance_day"] = prev_day
                    else:
                        d.pop("ghoul_plaza_clearance_day", None)
                    for gk in (
                        "prev_ghoul_plaza_clearance_day",
                        "ghoul_plaza_clearance_turn",
                        "ghoul_plaza_toll_gold_paid",
                        "ghoul_plaza_toll_payer_cid",
                    ):
                        d.pop(gk, None)
                acc_sc = dict(d.get("accepted_spirit_commissions") or {})
                if acc_sc:
                    d["accepted_spirit_commissions"] = {k: v for k, v in acc_sc.items() if int(v or 0) <= t_num}

            _mutate_spirit_realm_state(c, int(session_id), _prune)

    return counts


__all__ = [
    "backfill_folklore_spirit_realm_v52",
    "backfill_folklore_spirit_realm_v64",
    "rollback_spirit_realm_state_after_turn",
]
