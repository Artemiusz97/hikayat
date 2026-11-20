from __future__ import annotations

import json
import time
from typing import Any, Iterable, Mapping

import db
from mechanics.world.anomalous_sites.catalog import (
    get_anomalous_site_spec,
    get_site_state_dict,
    mutate_anomalous_site_state,
    parse_node_state,
    resolve_anomalous_site,
)


def lazy_midnight_reknit_site(
    session_id: int,
    site_id: str,
    current_day: int,
    turn_number: int = 0,
    *,
    world_nodes: Iterable[Mapping[str, Any]] | None = None,
    persist_db: bool = True,
) -> dict[str, Any]:
    """
    Re-knit any un-pacified site puzzle whose `puzzle_day < current_day` at midnight (`00:00`),
    resetting `puzzle_step`, `instability`, `boss_forced`, and expired `jammed_until_day`
    while preserving `visited: True`.
    """
    spec = get_anomalous_site_spec(site_id)
    target_id = str(spec["site_id"] if spec else site_id or "").strip()
    if not session_id or not target_id:
        return {}

    st = get_site_state_dict(int(session_id), target_id, world_nodes=world_nodes)
    if st.get("pacified"):
        return st

    puzzle_day = int(st.get("puzzle_day") or 0)
    jammed_until = int(st.get("jammed_until_day") or 0)
    needs_reknit = (puzzle_day > 0 and int(current_day) > puzzle_day) and (
        int(st.get("puzzle_step") or 0) > 0
        or int(st.get("instability") or 0) > 0
        or bool(st.get("boss_forced"))
        or (jammed_until > 0 and int(current_day) >= jammed_until)
    )
    if not needs_reknit:
        return st

    updates = {
        "puzzle_step": 0,
        "instability": 0,
        "boss_forced": False,
        "jammed_until_day": 0 if int(current_day) >= jammed_until else jammed_until,
        "puzzle_day": int(current_day),
    }
    if persist_db:
        return mutate_anomalous_site_state(int(session_id), target_id, int(turn_number), updates, world_nodes=world_nodes)
    merged = dict(st)
    merged.update(updates)
    return merged


def collapse_anomalous_site_on_extraction(
    session_id: int,
    curr_node_id: str = "",
    curr_location: str = "",
    current_day: int = 1,
    turn_number: int = 0,
) -> dict[str, Any]:
    """
    On 0 HP Emergency Extraction out of an un-pacified site, reset partial puzzle progress
    and jam the site until the following day (`current_day + 1`).
    """
    if not session_id:
        return {}
    nodes = db.get_session_world_nodes(int(session_id)) or []
    spec = resolve_anomalous_site(node_id=curr_node_id, location_str=curr_location, session_nodes=nodes)
    if not spec or spec.get("site_type") not in ("wild_facility", "embedded_wing"):
        return {}
    site_id = str(spec["site_id"])
    st = get_site_state_dict(int(session_id), site_id, world_nodes=nodes)
    if st.get("pacified"):
        return st
    return mutate_anomalous_site_state(
        int(session_id),
        site_id,
        int(turn_number),
        {
            "puzzle_step": 0,
            "instability": 0,
            "boss_forced": False,
            "jammed_until_day": int(current_day) + 1,
            "puzzle_day": int(current_day),
        },
        world_nodes=nodes,
    )


def rollback_anomalous_sites_after_turn(
    session_id: int,
    target_turn: int,
    *,
    conn: Any = None,
) -> int:
    """
    Revert any anomalous site state mutations (`pacified`, `puzzle_step`, `instability`,
    `jammed_until_day`, `last_harvest_day`, `visited`) and Resonator/Milestone snapshots
    recorded after `target_turn`.
    """
    if not session_id:
        return 0
    t_num = int(target_turn)
    reverted = 0

    def _run(c: Any) -> int:
        count = 0
        rows = c.execute(
            "SELECT node_id, state_json FROM world_nodes WHERE session_id = ? AND state_json LIKE '%anomalous_site%'",
            (int(session_id),),
        ).fetchall()
        for r in rows:
            nid = str(r["node_id"] if isinstance(r, Mapping) or hasattr(r, "keys") else r[0])
            raw_st = r["state_json"] if isinstance(r, Mapping) or hasattr(r, "keys") else r[1]
            st = parse_node_state({"state_json": raw_st})
            cur_as = st.get("anomalous_site")
            prev_as = st.get("anomalous_site_prev")
            if isinstance(cur_as, dict) and int(cur_as.get("updated_turn") or 0) > t_num:
                if isinstance(prev_as, dict) and int(prev_as.get("updated_turn") or 0) <= t_num:
                    restored = dict(prev_as)
                    st["anomalous_site"] = restored
                elif isinstance(prev_as, dict) and prev_as:
                    restored = {k: v for k, v in prev_as.items() if k != "updated_turn"}
                    if restored:
                        st["anomalous_site"] = restored
                    else:
                        st.pop("anomalous_site", None)
                else:
                    st.pop("anomalous_site", None)
                st.pop("anomalous_site_prev", None)
                c.execute(
                    "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
                    (json.dumps(st), int(session_id), nid),
                )
                count += 1

        sess_row = c.execute("SELECT extra_json FROM sessions WHERE id = ?", (int(session_id),)).fetchone()
        if sess_row and sess_row[0]:
            try:
                ex = json.loads(sess_row[0]) if isinstance(sess_row[0], str) else dict(sess_row[0])
            except Exception:
                ex = {}
            if isinstance(ex, dict):
                ex_dirty = False
                if int(ex.get("resonator_charges_turn") or 0) > t_num:
                    prev_rc = ex.pop("resonator_charges_prev", None)
                    ex.pop("resonator_charges_turn", None)
                    if isinstance(prev_rc, dict):
                        ex["resonator_charges_day"] = int(prev_rc.get("day") or 0)
                        ex["resonator_charges_used"] = int(prev_rc.get("used") or 0)
                    else:
                        ex.pop("resonator_charges_day", None)
                        ex.pop("resonator_charges_used", None)
                    ex_dirty = True
                if int(ex.get("anomalous_milestones_turn") or 0) > t_num:
                    prev_ms = ex.pop("anomalous_milestones_prev", None)
                    ex.pop("anomalous_milestones_turn", None)
                    if isinstance(prev_ms, list):
                        ex["anomalous_milestones_claimed"] = list(prev_ms)
                    else:
                        ex.pop("anomalous_milestones_claimed", None)
                    ex_dirty = True
                if ex_dirty:
                    c.execute(
                        "UPDATE sessions SET extra_json = ? WHERE id = ?",
                        (json.dumps(ex), int(session_id)),
                    )
        return count

    if conn is not None:
        return _run(conn)
    with db.get_conn() as local_conn:
        reverted = _run(local_conn)
    return reverted


def backfill_anomalous_locations_integrity_v57(conn: Any, session_id: int | None = None) -> int:
    """
    Migration v57: Idempotently backfills spatial graph & schedule repairs on existing SQLite sessions:
    1. Reparents loc_hilltop_shrine -> zone_woods_reserve (and updates world_edges + session_locations).
    2. Reparents loc_backstage_loft -> loc_drama_club_facility (and updates world_edges + session_locations).
    3. Keeps sub_hosp_isolation_cell_1309 under loc_general_hospital with parent_sub_id='loc_hosp_floor_13',
       strips is_discreet, and ensures an internal edge to loc_hosp_floor_13.
    4. Syncs canonical room renames (sub_old_storage_3b, loc_sealed_custodian_closet, sub_pier_ferris_wheel).
    5. Repairs category/privacy/access_tier/curfew drift on commercial, civic, and anomalous nodes.
    """
    sess_clause = " AND session_id = ?" if session_id is not None else ""
    params: tuple[Any, ...] = (int(session_id),) if session_id is not None else ()
    now_ts = time.time()
    updated = 0

    def _upsert_bidir_edge(sid: int, a: str, b: str, travel_min: int, edge_type: str) -> None:
        for src, dst in ((a, b), (b, a)):
            conn.execute(
                """INSERT INTO world_edges
                   (session_id, from_node_id, to_node_id, travel_minutes, edge_type, is_bidirectional, created_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?)
                   ON CONFLICT(session_id, from_node_id, to_node_id) DO UPDATE SET
                   travel_minutes = excluded.travel_minutes,
                   edge_type = excluded.edge_type,
                   is_bidirectional = 1""",
                (sid, src, dst, travel_min, edge_type, now_ts),
            )

    def _index_nodes(target_ids: tuple[str, ...]) -> dict[tuple[int, str], str]:
        ph = ",".join("?" for _ in target_ids)
        rows = conn.execute(
            f"SELECT session_id, node_id, name FROM world_nodes WHERE node_id IN ({ph}){sess_clause}",
            (*target_ids, *params),
        ).fetchall()
        return {
            (int(r["session_id"] if hasattr(r, "keys") else r[0]), str(r["node_id"] if hasattr(r, "keys") else r[1])): str(r["name"] if hasattr(r, "keys") else r[2])
            for r in rows
        }

    anchors = _index_nodes(("zone_woods_reserve", "loc_drama_club_facility", "loc_drama_foyer", "loc_general_hospital", "loc_hosp_floor_13"))

    # 1. Reparent loc_hilltop_shrine -> zone_woods_reserve & update edges
    shrine_rows = conn.execute(
        f"SELECT session_id, parent_id, name FROM world_nodes WHERE node_id = 'loc_hilltop_shrine'{sess_clause}",
        params,
    ).fetchall()
    for r in shrine_rows:
        sid = int(r["session_id"] if hasattr(r, "keys") else r[0])
        woods_name = anchors.get((sid, "zone_woods_reserve"))
        if not woods_name:
            continue
        c1 = conn.execute(
            "UPDATE world_nodes SET parent_id = 'zone_woods_reserve', category = 'wilderness', access_tier = 'open' "
            "WHERE session_id = ? AND node_id = 'loc_hilltop_shrine'",
            (sid,),
        )
        updated += c1.rowcount or 0
        conn.execute(
            "DELETE FROM world_edges WHERE session_id = ? AND "
            "((from_node_id = 'zone_suburbs' AND to_node_id = 'loc_hilltop_shrine') OR "
            "(from_node_id = 'loc_hilltop_shrine' AND to_node_id = 'zone_suburbs'))",
            (sid,),
        )
        _upsert_bidir_edge(sid, "zone_woods_reserve", "loc_hilltop_shrine", 5, "pathway")
        shrine_name = str(r["name"] if hasattr(r, "keys") else r[2])
        conn.execute(
            "UPDATE session_locations SET zone_name = ? WHERE session_id = ? AND primary_name = ?",
            (woods_name, sid, shrine_name),
        )

    # 2. Reparent loc_backstage_loft -> loc_drama_club_facility & update edges
    loft_rows = conn.execute(
        f"SELECT session_id, parent_id, name FROM world_nodes WHERE node_id = 'loc_backstage_loft'{sess_clause}",
        params,
    ).fetchall()
    for r in loft_rows:
        sid = int(r["session_id"] if hasattr(r, "keys") else r[0])
        drama_name = anchors.get((sid, "loc_drama_club_facility"))
        if not drama_name:
            continue
        c2 = conn.execute(
            "UPDATE world_nodes SET parent_id = 'loc_drama_club_facility' "
            "WHERE session_id = ? AND node_id = 'loc_backstage_loft'",
            (sid,),
        )
        updated += c2.rowcount or 0
        conn.execute(
            "DELETE FROM world_edges WHERE session_id = ? AND "
            "((from_node_id IN ('loc_school_clubs', 'bld_school_arts', 'sub_club_corridor', 'loc_clubroom_corridor') AND to_node_id = 'loc_backstage_loft') "
            "OR (from_node_id = 'loc_backstage_loft' AND to_node_id IN ('loc_school_clubs', 'bld_school_arts', 'sub_club_corridor', 'loc_clubroom_corridor')))",
            (sid,),
        )
        target_anchor = "loc_drama_foyer" if (sid, "loc_drama_foyer") in anchors else "loc_drama_club_facility"
        _upsert_bidir_edge(sid, target_anchor, "loc_backstage_loft", 1, "door")
        conn.execute(
            "UPDATE session_locations SET primary_name = ? WHERE session_id = ? AND location_id = 'loc_backstage_loft'",
            (drama_name, sid),
        )

    # 3. Clean sub_hosp_isolation_cell_1309 (parent_sub_id='loc_hosp_floor_13', strip is_discreet, connect to Floor 13)
    cell_rows = conn.execute(
        f"SELECT session_id, state_json FROM world_nodes WHERE node_id = 'sub_hosp_isolation_cell_1309'{sess_clause}",
        params,
    ).fetchall()
    for r in cell_rows:
        sid = int(r["session_id"] if hasattr(r, "keys") else r[0])
        st = parse_node_state({"state_json": r["state_json"] if hasattr(r, "keys") else r[1]})
        st.pop("is_discreet", None)
        st["parent_sub_id"] = "loc_hosp_floor_13"
        has_hosp = (sid, "loc_general_hospital") in anchors
        if has_hosp:
            conn.execute(
                "UPDATE world_nodes SET parent_id = 'loc_general_hospital', state_json = ? "
                "WHERE session_id = ? AND node_id = 'sub_hosp_isolation_cell_1309'",
                (json.dumps(st), sid),
            )
        else:
            conn.execute(
                "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = 'sub_hosp_isolation_cell_1309'",
                (json.dumps(st), sid),
            )
        if (sid, "loc_hosp_floor_13") in anchors:
            _upsert_bidir_edge(sid, "loc_hosp_floor_13", "sub_hosp_isolation_cell_1309", 1, "door")
        updated += 1

    # 4. Canonical room renames & legacy node/path alignment across world_nodes, session_locations,
    #    sessions, quest_waypoints, commitments_ledger, and school_directory
    sess_id_filter = " AND id = ?" if session_id is not None else ""

    def _sync_text_refs(old_txt: str, new_txt: str, target_nid: str = "") -> None:
        like_pat = f"%{old_txt}%"
        if target_nid:
            conn.execute(
                f"UPDATE sessions SET current_location = replace(current_location, ?, ?) "
                f"WHERE current_node_id = ? AND current_location LIKE ?{sess_id_filter}",
                (old_txt, new_txt, target_nid, like_pat, *params),
            )
            conn.execute(
                f"UPDATE quest_waypoints SET target_location = replace(target_location, ?, ?) "
                f"WHERE target_node_id = ? AND target_location LIKE ?{sess_clause}",
                (old_txt, new_txt, target_nid, like_pat, *params),
            )
            conn.execute(
                f"UPDATE commitments_ledger SET target_location = replace(target_location, ?, ?) "
                f"WHERE target_node_id = ? AND target_location LIKE ?{sess_clause}",
                (old_txt, new_txt, target_nid, like_pat, *params),
            )
        else:
            conn.execute(
                f"UPDATE sessions SET current_location = replace(current_location, ?, ?) "
                f"WHERE current_location LIKE ?{sess_id_filter}",
                (old_txt, new_txt, like_pat, *params),
            )
            conn.execute(
                f"UPDATE quest_waypoints SET target_location = replace(target_location, ?, ?) "
                f"WHERE target_location LIKE ?{sess_clause}",
                (old_txt, new_txt, like_pat, *params),
            )
            conn.execute(
                f"UPDATE commitments_ledger SET target_location = replace(target_location, ?, ?) "
                f"WHERE target_location LIKE ?{sess_clause}",
                (old_txt, new_txt, like_pat, *params),
            )
        conn.execute(
            f"UPDATE school_directory SET "
            f"primary_facility = replace(primary_facility, ?, ?), "
            f"secondary_facility = replace(secondary_facility, ?, ?) "
            f"WHERE (primary_facility LIKE ? OR secondary_facility LIKE ?){sess_clause}",
            (old_txt, new_txt, old_txt, new_txt, like_pat, like_pat, *params),
        )

    nid_remaps = (
        ("loc_auditorium", "loc_auditorium_stage"),
        ("loc_broadcast_room", "loc_broadcasting_room"),
        ("loc_art_studio", "loc_fine_arts_studio"),
        ("loc_backstage_prop_loft", "loc_backstage_loft"),
    )
    for old_nid, new_nid in nid_remaps:
        conn.execute(f"UPDATE sessions SET current_node_id = ? WHERE current_node_id = ?{sess_id_filter}", (new_nid, old_nid, *params))
        conn.execute(f"UPDATE quest_waypoints SET target_node_id = ? WHERE target_node_id = ?{sess_clause}", (new_nid, old_nid, *params))
        conn.execute(f"UPDATE commitments_ledger SET target_node_id = ? WHERE target_node_id = ?{sess_clause}", (new_nid, old_nid, *params))

    renames = [
        ("sub_old_storage_3b", "Dusty Annex Clockwork Archive"),
        ("loc_sealed_custodian_closet", "Sealed Boiler-Hall Supply Closet"),
        ("sub_pier_ferris_wheel", "Coastal Game Arcade & Harbor Boardwalk"),
    ]
    for nid, rname in renames:
        c = conn.execute(
            f"UPDATE world_nodes SET name = ? WHERE node_id = ?{sess_clause}",
            (rname, nid, *params),
        )
        updated += c.rowcount or 0
        conn.execute(
            f"UPDATE session_locations SET sub_name = ? WHERE location_id = ?{sess_clause}",
            (rname, nid, *params),
        )
        _sync_text_refs("Old Storage Room 3-B", rname, target_nid="sub_old_storage_3b") if nid == "sub_old_storage_3b" else None

    for old_txt, new_txt in (
        ("Sealed Classroom 3-B", "Dusty Annex Clockwork Archive"),
        ("Dusty Stage-Wing Storage Room", "Dusty Annex Clockwork Archive"),
        ("Abandoned Old Wing ➔ Old Storage Room 3-B", "Abandoned Old Campus Wing & Clock Tower ➔ Dusty Annex Clockwork Archive"),
        ("Abandoned Old Campus Wing ➔ Old Storage Room 3-B", "Abandoned Old Campus Wing & Clock Tower ➔ Dusty Annex Clockwork Archive"),
        ("Abandoned Old Wing ➔ Dusty Old Music Room", "Cultural Arts & Student Union ➔ Dusty Old Music Room"),
        ("Student Union & Cultural Arts Wing", "Cultural Arts & Student Union"),
    ):
        _sync_text_refs(old_txt, new_txt)

    s_extra_rows = conn.execute(
        f"SELECT id, extra_json FROM sessions WHERE (extra_json LIKE '%loc_old_storage_3b%' OR extra_json LIKE '%Sealed Classroom 3-B%' OR extra_json LIKE '%Dusty Old Music Room%'){sess_id_filter}",
        params,
    ).fetchall()
    for sr in s_extra_rows:
        s_id = int(sr["id"] if hasattr(sr, "keys") else sr[0])
        raw_ex = sr["extra_json"] if hasattr(sr, "keys") else sr[1]
        try:
            ex = json.loads(raw_ex or "{}")
        except Exception:
            continue
        changed = False
        for inc in ex.get("daily_incursions") or []:
            if not isinstance(inc, dict):
                continue
            if inc.get("node_id") == "loc_old_storage_3b" and "clockwork" in str(inc.get("facility_name") or "").lower():
                inc["node_id"] = "sub_old_storage_3b"
                changed = True
            for old_txt, new_txt in (
                ("Sealed Classroom 3-B", "Dusty Annex Clockwork Archive"),
                ("Abandoned Old Wing ➔ Dusty Old Music Room", "Cultural Arts & Student Union ➔ Dusty Old Music Room"),
            ):
                for k in ("facility_name", "location", "full_location"):
                    if isinstance(inc.get(k), str) and old_txt in inc[k]:
                        inc[k] = inc[k].replace(old_txt, new_txt)
                        changed = True
        if changed:
            conn.execute("UPDATE sessions SET extra_json = ? WHERE id = ?", (json.dumps(ex), s_id))

    # 5. Repair false residential / restricted / curfew drift on public, commercial & anomalous nodes
    tier_fixes = [
        ("zone_suburbs", "residential", "public", "open", None, None),
        ("loc_suburb_laundry", "commercial", "public", "open", None, None),
        ("sub_laundry_lounge", "commercial", "public", "open", None, None),
        ("sub_laundry_machines", "commercial", "public", "open", None, None),
        ("loc_ct_paper_opera", "civic", "public", "open", None, None),
        ("loc_crimson_auction_house", "commercial", "public", "open", None, None),
        ("loc_sky_vip_lounge", "commercial", "public", "open", None, None),
        ("loc_drydock_shipyard", "civic", "public", "open", None, None),
        ("loc_haunted_manor", "residential", "public", "open", None, None),
        ("sub_manor_gates", "residential", "public", "open", None, None),
        ("sub_manor_foyer", "residential", "public", "open", None, None),
        ("loc_liminal_residential", "residential", "public", "open", None, None),
        ("sub_residential_vestibule", "residential", "public", "open", None, None),
        ("sub_residential_corridor", "residential", "semi_private", "open", None, None),
        ("sub_room_404", "residential", "semi_private", "open", None, None),
        ("loc_cul_de_sac_9", "residential", "public", "open", None, None),
        ("sub_cul_de_sac_sign", "residential", "public", "open", None, None),
        ("sub_looping_asphalt", "residential", "public", "open", None, None),
        ("sub_hollow_model_home", "residential", "public", "open", None, None),
        ("sub_crisis_press_room", "civic", "public", "open", None, None),
        ("loc_endless_dept_store", "commercial", "public", "open", None, None),
        ("loc_static_cinema", "civic", "public", "open", None, None),
        ("loc_ct_blood_jade_vault", "civic", "public", "open", None, None),
    ]
    for nid, cat, priv, acc, c_start, c_end in tier_fixes:
        c = conn.execute(
            f"UPDATE world_nodes SET category = ?, privacy_level = ?, access_tier = ?, "
            f"curfew_start_min = ?, curfew_end_min = ? WHERE node_id = ?{sess_clause}",
            (cat, priv, acc, c_start, c_end, nid, *params),
        )
        updated += c.rowcount or 0

    return updated


def backfill_outlaw_faction_hqs_and_residences_v60(conn: Any, session_id: int | None = None) -> int:
    """
    Migration v60: Idempotently upgrades existing anomalous sessions and loaded save slots to
    the 10-wing Occult Cult & Clandestine Syndicate HQs and seeds missing outlaw starter
    safehouses (`fac_cult_residence`, `fac_syndicate_residence`) without overwriting existing
    `world_nodes.state_json["anomalous_site"]` payloads.
    """
    from mechanics.world.locations.seeds import (
        OUTLAW_HQ_EXTRA_WINGS,
        get_outlaw_starter_residence_seeds,
    )

    sess_filter = " AND id = ?" if session_id is not None else ""
    params: tuple[Any, ...] = (int(session_id),) if session_id is not None else ()
    now_ts = time.time()
    updated = 0

    def _upsert_bidir_edge(sid: int, a: str, b: str, travel_min: int, edge_type: str) -> None:
        for src, dst in ((a, b), (b, a)):
            conn.execute(
                """INSERT INTO world_edges
                   (session_id, from_node_id, to_node_id, travel_minutes, edge_type, is_bidirectional, created_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?)
                   ON CONFLICT(session_id, from_node_id, to_node_id) DO UPDATE SET
                   travel_minutes = excluded.travel_minutes,
                   edge_type = excluded.edge_type,
                   is_bidirectional = 1""",
                (sid, src, dst, travel_min, edge_type, now_ts),
            )

    sess_rows = conn.execute(
        f"SELECT id, scenario FROM sessions WHERE lower(COALESCE(scenario, '')) LIKE '%anomal%'{sess_filter}",
        params,
    ).fetchall()

    for sr in sess_rows:
        sid = int(sr["id"] if hasattr(sr, "keys") else sr[0])
        scen_key = str((sr["scenario"] if hasattr(sr, "keys") else sr[1]) or "anomalous_incursions")

        node_rows = conn.execute(
            "SELECT node_id, parent_id, name, node_type FROM world_nodes WHERE session_id = ?",
            (sid,),
        ).fetchall()
        node_map: dict[str, tuple[str, str, str]] = {
            str(nr["node_id"] if hasattr(nr, "keys") else nr[0]): (
                str((nr["parent_id"] if hasattr(nr, "keys") else nr[1]) or ""),
                str((nr["name"] if hasattr(nr, "keys") else nr[2]) or ""),
                str((nr["node_type"] if hasattr(nr, "keys") else nr[3]) or ""),
            )
            for nr in node_rows
        }

        # 1. Open threshold entrances and add missing 4+4 HQ wings
        for hq_id, ent_id in (
            ("loc_cult_sanctum_hq", "sub_cult_entrance"),
            ("loc_clandestine_syndicate_hq", "sub_synd_entrance"),
        ):
            if hq_id not in node_map:
                continue
            parent_zone_id, hq_name, _ = node_map[hq_id]
            zone_name = node_map.get(parent_zone_id, ("", "", ""))[1] or parent_zone_id
            c_open = conn.execute(
                "UPDATE world_nodes SET access_tier = 'open' "
                "WHERE session_id = ? AND node_id IN (?, ?) AND access_tier != 'open'",
                (sid, hq_id, ent_id),
            )
            updated += c_open.rowcount or 0

            anchor_id = ent_id if ent_id in node_map else hq_id
            for wing in OUTLAW_HQ_EXTRA_WINGS.get(hq_id, ()):
                wid = str(wing["id"])
                if wid in node_map:
                    continue
                wname = str(wing["name"])
                wstate = json.dumps({"props": list(wing.get("props") or ()), "is_anomalous": True})
                conn.execute(
                    """INSERT OR IGNORE INTO world_nodes
                       (session_id, node_id, parent_id, name, node_type, category, privacy_level,
                        is_enclosed, is_transit_hub, access_tier, curfew_start_min, curfew_end_min,
                        atmosphere, is_dynamic, state_json, created_at)
                       VALUES (?, ?, ?, ?, 'ROOM', 'civic', 'public', 1, 0, 'restricted', NULL, NULL, '', 0, ?, ?)""",
                    (sid, wid, hq_id, wname, wstate, now_ts),
                )
                conn.execute(
                    """INSERT OR IGNORE INTO session_locations
                       (session_id, location_id, zone_name, primary_name, sub_name, atmosphere, is_dynamic, state_json, created_at)
                       VALUES (?, ?, ?, ?, ?, '', 0, ?, ?)""",
                    (sid, wid, zone_name, hq_name, wname, wstate, now_ts),
                )
                _upsert_bidir_edge(sid, anchor_id, wid, 3, "hallway")
                node_map[wid] = (hq_id, wname, "ROOM")
                updated += 1

            interior_wids = sorted(
                nid
                for nid, (pid, _, _) in node_map.items()
                if pid == hq_id and nid not in (ent_id, anchor_id)
            )
            if interior_wids:
                existing_edges = {
                    (
                        str(er["from_node_id"] if hasattr(er, "keys") else er[0]),
                        str(er["to_node_id"] if hasattr(er, "keys") else er[1]),
                    )
                    for er in conn.execute(
                        "SELECT from_node_id, to_node_id FROM world_edges WHERE session_id = ?",
                        (sid,),
                    ).fetchall()
                }
                for idx_i in range(len(interior_wids)):
                    for idx_j in range(idx_i + 1, len(interior_wids)):
                        wa, wb = interior_wids[idx_i], interior_wids[idx_j]
                        if (wa, wb) not in existing_edges or (wb, wa) not in existing_edges:
                            _upsert_bidir_edge(sid, wa, wb, 3, "hallway")
                            updated += 1

        # 2. Seed missing starter safehouses (fac_cult_residence & fac_syndicate_residence)
        for zid, zname, fac in get_outlaw_starter_residence_seeds(scen_key):
            fid = str(fac.get("id") or "")
            if not fid or zid not in node_map or fid in node_map:
                continue
            fname = str(fac.get("name") or fid)
            zone_display = node_map[zid][1] or zname
            f_state = json.dumps({
                k: fac[k]
                for k in ("theme", "features", "sensory")
                if fac.get(k) is not None
            })
            conn.execute(
                """INSERT OR IGNORE INTO world_nodes
                   (session_id, node_id, parent_id, name, node_type, category, privacy_level,
                    is_enclosed, is_transit_hub, access_tier, curfew_start_min, curfew_end_min,
                    atmosphere, is_dynamic, state_json, created_at)
                   VALUES (?, ?, ?, ?, 'FACILITY', 'residential', ?, 1, 0, ?, NULL, NULL, ?, 0, ?, ?)""",
                (
                    sid,
                    fid,
                    zid,
                    fname,
                    str(fac.get("privacy_level") or "private"),
                    str(fac.get("access_tier") or "private"),
                    str(fac.get("sensory") or ""),
                    f_state,
                    now_ts,
                ),
            )
            _upsert_bidir_edge(sid, zid, fid, 3, "road")
            node_map[fid] = (zid, fname, "FACILITY")
            updated += 1

            subs = list(fac.get("sub_locations") or ())
            ent_sub = next((str(s["id"]) for s in subs if s.get("is_entrance")), "")
            if not ent_sub and subs:
                ent_sub = str(subs[0].get("id") or "")
            for sub in subs:
                sub_id = str(sub.get("id") or "")
                if not sub_id or sub_id in node_map:
                    continue
                sub_name = str(sub.get("name") or sub_id)
                sub_meta = {
                    k: sub[k]
                    for k in ("props", "sensory", "is_entrance", "is_private_intimate")
                    if sub.get(k) is not None
                }
                sub_state = json.dumps(sub_meta)
                sub_priv = str(sub.get("privacy_level") or ("public" if sub.get("is_entrance") else "private"))
                sub_acc = str(sub.get("access_tier") or fac.get("access_tier") or "private")
                conn.execute(
                    """INSERT OR IGNORE INTO world_nodes
                       (session_id, node_id, parent_id, name, node_type, category, privacy_level,
                        is_enclosed, is_transit_hub, access_tier, curfew_start_min, curfew_end_min,
                        atmosphere, is_dynamic, state_json, created_at)
                       VALUES (?, ?, ?, ?, 'ROOM', 'residential', ?, 1, 0, ?, NULL, NULL, ?, 0, ?, ?)""",
                    (
                        sid,
                        sub_id,
                        fid,
                        sub_name,
                        sub_priv,
                        sub_acc,
                        str(sub.get("sensory") or ""),
                        sub_state,
                        now_ts,
                    ),
                )
                conn.execute(
                    """INSERT OR IGNORE INTO session_locations
                       (session_id, location_id, zone_name, primary_name, sub_name, atmosphere, is_dynamic, state_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)""",
                    (sid, sub_id, zone_display, fname, sub_name, str(sub.get("sensory") or ""), sub_state, now_ts),
                )
                if sub_id == ent_sub:
                    _upsert_bidir_edge(sid, fid, sub_id, 1, "door")
                elif ent_sub:
                    _upsert_bidir_edge(sid, ent_sub, sub_id, 1, "door")
                node_map[sub_id] = (fid, sub_name, "ROOM")
                updated += 1

        # 3. Ensure active Cult/Syndicate sessions have their starter safehouse deed in player_properties
        sess_extra_row = conn.execute("SELECT extra_json FROM sessions WHERE id = ?", (sid,)).fetchone()
        raw_ex = (sess_extra_row["extra_json"] if hasattr(sess_extra_row, "keys") else sess_extra_row[0]) if sess_extra_row else ""
        f_arch = ""
        if isinstance(raw_ex, str) and raw_ex.strip():
            try:
                ex_obj = json.loads(raw_ex)
                afs = ex_obj.get("anomalous_faction_state") if isinstance(ex_obj, dict) else None
                if isinstance(afs, dict):
                    f_arch = str(afs.get("faction_archetype_key") or "").strip().lower()
            except Exception:
                f_arch = ""
        expected_res_fid = {
            "cult_faction": "fac_cult_residence",
            "clandestine_faction": "fac_syndicate_residence",
        }.get(f_arch, "")
        if expected_res_fid and expected_res_fid in node_map:
            has_prop = conn.execute(
                "SELECT 1 FROM player_properties WHERE session_id = ? AND facility_node_id = ? AND is_starter = 1 LIMIT 1",
                (sid, expected_res_fid),
            ).fetchone()
            if not has_prop:
                from db.properties import grant_or_relocate_starter_quarters
                grant_or_relocate_starter_quarters(sid, f_arch, conn=conn)
                updated += 1

    return updated
