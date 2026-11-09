"""
mechanics/world/locations/folklore_veil_lifecycle.py
====================================================
Turn-rollback hooks and idempotent Migration 49 schema/world-graph backfill for
Sacred Mountain Sanctuary & Onsen Quarter (`zone_eastern_sanctuary`), Wilderness
Forest Reserve (`zone_woods_reserve`), Hidden Kitsune Village, and Hidden Orang
Bunian Village.
"""
from __future__ import annotations

import json
from contextlib import nullcontext
from typing import Any, Dict, Optional

import db
import scenario_data

from .folklore_veil import (
    INNER_PLAZA_NODE_IDS,
    OUTER_THRESHOLD_NODE_IDS,
    ROYAL_PAVILION_NODE_IDS,
    VEILED_INNER_ROOM_IDS,
    load_folklore_villages_catalog,
)


def preview_sanctuary_treaty_violation(
    session_id: int,
    village_key: str,
    session: Optional[dict] = None,
) -> Dict[str, Any]:
    """Pure, non-mutating preview of Sanctuary Non-Aggression Pact expulsion for `persist_db=False` pre-turn staging."""
    if not session_id or village_key not in ("kitsune", "bunian"):
        return {"expelled": False}
    catalog = load_folklore_villages_catalog()
    v_meta = (catalog.get("villages") or {}).get(village_key) or {}
    fac_id = str(v_meta.get("village_id") or (
        "loc_hidden_kitsune_village" if village_key == "kitsune" else "loc_hidden_bunian_village"
    ))
    mundane_name = str(v_meta.get("mundane_name") or v_meta.get("outer_threshold_name") or fac_id)
    outer_id = OUTER_THRESHOLD_NODE_IDS[village_key]
    outer_name = str(v_meta.get("outer_threshold_name") or mundane_name)
    zone_node = db.get_world_node(session_id, str(v_meta.get("zone_id") or ""))
    zone_name = str((zone_node or {}).get("name") or v_meta.get("zone_name") or "")
    ejected_loc = f"{zone_name} ➔ {mundane_name} ➔ {outer_name}" if zone_name else f"{mundane_name} ➔ {outer_name}"
    if isinstance(session, dict):
        session["current_node_id"] = outer_id
        session["current_location"] = ejected_loc
        session["nearby_enemies"] = []
        session["leyline_spirit_passage_unlocked"] = False
    directive = (
        f"[STAGE DIRECTION — SANCTUARY TREATY VIOLATION & BANISHMENT]: "
        f"Violence and containment devices are forbidden within the ancient sanctuary pact. "
        f"Blinding {'azure foxfire and chiming shrine wards' if village_key == 'kitsune' else 'silver banyan mist and echoing serunai chords'} "
        f"surge around the party, sweeping them back outside to {outer_name} after half an hour of timeless disorientation. "
        f"The inner enclave's veil is sealed shut until a sacred offering of atonement is presented at the outer threshold."
    )
    return {
        "expelled": True,
        "staged": True,
        "village_key": village_key,
        "ejected_node_id": outer_id,
        "ejected_location": ejected_loc,
        "time_lost_minutes": 30,
        "prompt_directive": directive,
    }


def apply_sanctuary_treaty_violation(
    session_id: int,
    village_key: str,
    turn_number: Optional[int] = None,
    session: Optional[dict] = None,
    advance_clock: bool = True,
) -> Dict[str, Any]:
    """
    Enforces the Sanctuary Non-Aggression Pact when a player attacks villagers or attempts containment:
    - Ejects PC to the mundane outer threshold
    - Advances session clock by +30 minutes when `advance_clock=True`
    - Re-locks the village veil with veil_atonement_required=True and disables inner-plaza Fast Travel
    """
    if not session_id or village_key not in ("kitsune", "bunian"):
        return {"expelled": False}

    eff_turn = int(turn_number if turn_number is not None else db.get_effective_session_turn(session_id))
    preview = preview_sanctuary_treaty_violation(session_id, village_key, session=None)
    catalog = load_folklore_villages_catalog()
    v_meta = (catalog.get("villages") or {}).get(village_key) or {}
    fac_id = str(v_meta.get("village_id") or (
        "loc_hidden_kitsune_village" if village_key == "kitsune" else "loc_hidden_bunian_village"
    ))
    mundane_name = str(v_meta.get("mundane_name") or v_meta.get("outer_threshold_name") or fac_id)
    true_name = str(v_meta.get("true_name") or "")
    outer_id = preview["ejected_node_id"]
    ejected_loc = preview["ejected_location"]
    plaza_id = INNER_PLAZA_NODE_IDS[village_key]

    relock_state = {
        "veil_village_key": village_key,
        "veil_attuned": False,
        "is_hidden": True,
        "discovered": False,
        "unlocked_permanent": False,
        "unlocked_until_day": 0,
        "veil_atonement_required": True,
        "expelled_turn": eff_turn,
    }
    with db.UnitOfWork() as conn:
        db.update_world_node_state(session_id, fac_id, relock_state)
        for room_id in VEILED_INNER_ROOM_IDS[village_key]:
            db.update_world_node_state(session_id, room_id, relock_state)

        conn.execute(
            "UPDATE world_nodes SET name = ? WHERE session_id = ? AND node_id = ?",
            (mundane_name, session_id, fac_id),
        )
        conn.execute(
            "UPDATE world_nodes SET is_transit_hub = 0 WHERE session_id = ? AND node_id = ?",
            (session_id, plaza_id),
        )
        conn.execute(
            "UPDATE world_edges SET is_locked = 1 WHERE session_id = ? AND edge_type = 'leyline_spirit_passage'",
            (session_id,),
        )
        if true_name:
            conn.execute(
                "UPDATE session_locations SET primary_name = ? WHERE session_id = ? AND primary_name = ?",
                (mundane_name, session_id, true_name),
            )
        for inner_rid in VEILED_INNER_ROOM_IDS[village_key]:
            conn.execute(
                "DELETE FROM session_locations WHERE session_id = ? AND location_id = ?",
                (session_id, inner_rid),
            )

        c_day, c_min, c_awake = db.get_session_time(session_id)
        if advance_clock:
            total_min = int(c_min) + 30
            new_day = int(c_day) + (total_min // 1440)
            new_min = total_min % 1440
            db.update_session_time(session_id, new_day, new_min, c_awake)
        else:
            new_day, new_min = int(c_day), int(c_min)

        db.update_session(
            session_id,
            current_node_id=outer_id,
            current_location=ejected_loc,
            nearby_enemies=[],
            extra={"leyline_spirit_passage_unlocked": False},
        )

    if isinstance(session, dict):
        session["current_node_id"] = outer_id
        session["current_location"] = ejected_loc
        session["current_day"] = new_day
        session["current_minute"] = new_min
        session["nearby_enemies"] = []
        session["leyline_spirit_passage_unlocked"] = False

    return {
        "expelled": True,
        "village_key": village_key,
        "ejected_node_id": outer_id,
        "ejected_location": ejected_loc,
        "time_lost_minutes": 30,
        "new_day": new_day,
        "new_minute": new_min,
        "prompt_directive": preview["prompt_directive"],
    }


def rollback_folklore_veil_state_after_turn(
    session_id: int,
    turn_number: int,
    conn: Any = None,
) -> Dict[str, int]:
    """
    Reverts folklore village attunement, treaty expulsion, and Leyline Spirit Passage unlocks
    that occurred strictly after `turn_number` (`unlocked_turn > turn_number` or `expelled_turn > turn_number`).
    """
    if not session_id:
        return {"villages_reverted": 0, "leyline_reverted": 0}
    t_num = int(turn_number)
    catalog = load_folklore_villages_catalog()
    villages_meta = catalog.get("villages") or {}
    reverted_v = 0
    reverted_ley = 0

    ctx = nullcontext(conn) if conn is not None else db.get_conn()
    with ctx as c:
        for v_key in ("kitsune", "bunian"):
            v_meta = villages_meta.get(v_key) or {}
            fac_id = str(v_meta.get("village_id") or (
                "loc_hidden_kitsune_village" if v_key == "kitsune" else "loc_hidden_bunian_village"
            ))
            mundane_name = str(v_meta.get("mundane_name") or v_meta.get("outer_threshold_name") or fac_id)
            true_name = str(v_meta.get("true_name") or fac_id)
            plaza_id = INNER_PLAZA_NODE_IDS[v_key]
            row = c.execute(
                "SELECT state_json FROM world_nodes WHERE session_id = ? AND node_id = ?",
                (int(session_id), fac_id),
            ).fetchone()
            if not row:
                continue
            try:
                st = json.loads(row["state_json"] or "{}") if row["state_json"] else {}
            except Exception:
                st = {}
            if not isinstance(st, dict):
                st = {}

            unlocked_t = int(st.get("unlocked_turn") or 0)
            expelled_t = int(st.get("expelled_turn") or 0)

            if unlocked_t > t_num and not st.get("veil_atonement_required"):
                st.update({
                    "veil_attuned": False,
                    "is_hidden": True,
                    "discovered": False,
                    "unlocked_permanent": False,
                })
                st.pop("unlocked_turn", None)
                st.pop("last_unlock_reason", None)
                c.execute(
                    "UPDATE world_nodes SET name = ?, state_json = ? WHERE session_id = ? AND node_id = ?",
                    (mundane_name, json.dumps(st), int(session_id), fac_id),
                )
                c.execute(
                    "UPDATE world_nodes SET is_transit_hub = 0 WHERE session_id = ? AND node_id = ?",
                    (int(session_id), plaza_id),
                )
                for room_id in VEILED_INNER_ROOM_IDS[v_key]:
                    r_row = c.execute(
                        "SELECT state_json FROM world_nodes WHERE session_id = ? AND node_id = ?",
                        (int(session_id), room_id),
                    ).fetchone()
                    if r_row:
                        try:
                            rst = json.loads(r_row["state_json"] or "{}") if r_row["state_json"] else {}
                        except Exception:
                            rst = {}
                        if isinstance(rst, dict):
                            rst.update({"is_hidden": True, "discovered": False, "unlocked_permanent": False})
                            rst.pop("unlocked_turn", None)
                            c.execute(
                                "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
                                (json.dumps(rst), int(session_id), room_id),
                            )
                    c.execute(
                        "DELETE FROM session_locations WHERE session_id = ? AND location_id = ?",
                        (int(session_id), room_id),
                    )
                if true_name:
                    c.execute(
                        "UPDATE session_locations SET primary_name = ? WHERE session_id = ? AND primary_name = ?",
                        (mundane_name, int(session_id), true_name),
                    )
                reverted_v += 1
            elif expelled_t > t_num and st.get("veil_atonement_required"):
                st["veil_atonement_required"] = False
                st.pop("expelled_turn", None)
                if 0 < unlocked_t <= t_num:
                    st.update({"veil_attuned": True, "is_hidden": False, "discovered": True, "unlocked_permanent": True})
                    c.execute(
                        "UPDATE world_nodes SET name = ?, state_json = ? WHERE session_id = ? AND node_id = ?",
                        (true_name, json.dumps(st), int(session_id), fac_id),
                    )
                    c.execute(
                        "UPDATE world_nodes SET is_transit_hub = 1 WHERE session_id = ? AND node_id = ?",
                        (int(session_id), plaza_id),
                    )
                    zone_row = c.execute(
                        "SELECT name FROM world_nodes WHERE session_id = ? AND node_id = ?",
                        (int(session_id), str(v_meta.get("zone_id") or "")),
                    ).fetchone()
                    z_nm = str(zone_row["name"]) if zone_row and zone_row["name"] else str(v_meta.get("zone_name") or "")
                    for room_id in VEILED_INNER_ROOM_IDS[v_key]:
                        r_row = c.execute(
                            "SELECT name, atmosphere, state_json FROM world_nodes WHERE session_id = ? AND node_id = ?",
                            (int(session_id), room_id),
                        ).fetchone()
                        if r_row:
                            try:
                                rst = json.loads(r_row["state_json"] or "{}") if r_row["state_json"] else {}
                            except Exception:
                                rst = {}
                            if isinstance(rst, dict):
                                rst.update({"is_hidden": False, "discovered": True, "veil_atonement_required": False})
                                if room_id != ROYAL_PAVILION_NODE_IDS[v_key]:
                                    rst["unlocked_permanent"] = True
                                c.execute(
                                    "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
                                    (json.dumps(rst), int(session_id), room_id),
                                )
                            if z_nm:
                                c.execute(
                                    """INSERT OR REPLACE INTO session_locations
                                       (session_id, location_id, zone_name, primary_name, sub_name, atmosphere, is_dynamic, created_at)
                                       VALUES (?, ?, ?, ?, ?, ?, 0, COALESCE((SELECT created_at FROM session_locations WHERE session_id = ? AND location_id = ?), strftime('%s','now')))""",
                                    (int(session_id), room_id, z_nm, true_name, str(r_row["name"] or room_id), str(r_row["atmosphere"] or ""), int(session_id), room_id),
                                )
                    if mundane_name:
                        c.execute(
                            "UPDATE session_locations SET primary_name = ? WHERE session_id = ? AND primary_name = ?",
                            (true_name, int(session_id), mundane_name),
                        )
                else:
                    c.execute(
                        "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
                        (json.dumps(st), int(session_id), fac_id),
                    )
                reverted_v += 1

        s_row = c.execute("SELECT extra_json FROM sessions WHERE id = ?", (int(session_id),)).fetchone()
        if s_row and s_row["extra_json"]:
            try:
                ex = json.loads(s_row["extra_json"] or "{}")
            except Exception:
                ex = {}
            if isinstance(ex, dict) and int(ex.get("leyline_unlocked_turn") or 0) > t_num:
                ex["leyline_spirit_passage_unlocked"] = False
                ex.pop("leyline_unlocked_turn", None)
                ex.pop("leyline_unlock_reason", None)
                c.execute(
                    "UPDATE sessions SET extra_json = ? WHERE id = ?",
                    (json.dumps(ex, default=str), int(session_id)),
                )
                c.execute(
                    "UPDATE world_edges SET is_locked = 1 WHERE session_id = ? AND edge_type = 'leyline_spirit_passage'",
                    (int(session_id),),
                )
                reverted_ley = 1

        from mechanics.social.folklore_roster_lifecycle import rollback_folklore_roster_state_after_turn
        roster_rev = rollback_folklore_roster_state_after_turn(int(session_id), t_num, conn=c)

    return {
        "villages_reverted": reverted_v,
        "leyline_reverted": reverted_ley,
        **roster_rev,
    }


def backfill_zone_split_and_hidden_villages_v49(conn: Any, session_id: Optional[int] = None) -> int:
    """
    Idempotent Migration 49 backfill for existing Anomalous Incursions / High School / Urban Anomalies sessions:
    - Inserts `zone_eastern_sanctuary`, 2 Eastern attractions, and both veiled villages + inner rooms if missing
    - Reparents `loc_eastern_temple`, `fac_temple_residence`, `fac_onsen_villa`, and procedural Cypress/Cloister residences
      from `zone_woods_reserve` to `zone_eastern_sanctuary`
    - Reparents `loc_cult_sanctum_hq` -> `zone_undercity` and `loc_clandestine_syndicate_hq` -> `zone_industrial`
    - Updates `player_properties` and `session_locations` and wires district + locked `leyline_spirit_passage` edges
    """
    from .seeds import get_scenario_seed_data
    if session_id is not None:
        s_rows = conn.execute("SELECT id, scenario FROM sessions WHERE id = ?", (int(session_id),)).fetchall()
    else:
        s_rows = conn.execute("SELECT id, scenario FROM sessions").fetchall()
    migrated_sessions = 0
    sanctuary_zone_name = "Sacred Mountain Sanctuary & Onsen Quarter"
    woods_zone_name = "Wilderness Forest Reserve"

    for sr in s_rows:
        sid = int(sr["id"] if hasattr(sr, "__getitem__") else sr[0])
        scen = str((sr["scenario"] if hasattr(sr, "__getitem__") else sr[1]) or "")
        scen_low = scen.lower()
        if not (
            scenario_data.is_anomalous_incursions_scenario(scen)
            or scenario_data.is_anomalous_high_school_scenario(scen)
            or "urban_anomalies" in scen_low
        ):
            continue
        has_woods = conn.execute(
            "SELECT 1 FROM world_nodes WHERE session_id = ? AND node_id = 'zone_woods_reserve' LIMIT 1",
            (sid,),
        ).fetchone()
        if not has_woods:
            continue

        seed_data = get_scenario_seed_data(scen) or {}
        zones_by_id = {z.get("id"): z for z in (seed_data.get("zones") or []) if isinstance(z, dict) and z.get("id")}
        z_sanc = zones_by_id.get("zone_eastern_sanctuary") or {}
        z_woods = zones_by_id.get("zone_woods_reserve") or {}

        conn.execute(
            """INSERT OR IGNORE INTO world_nodes
               (session_id, node_id, parent_id, name, node_type, category, privacy_level, is_enclosed, is_transit_hub, access_tier, atmosphere, is_dynamic, state_json)
               VALUES (?, 'zone_eastern_sanctuary', NULL, ?, 'ZONE', 'sacred', 'public', 0, 1, 'open', ?, 0, NULL)""",
            (sid, str(z_sanc.get("name") or sanctuary_zone_name), str(z_sanc.get("atmosphere") or "")),
        )

        conn.execute(
            """UPDATE world_nodes
               SET parent_id = 'zone_eastern_sanctuary'
               WHERE session_id = ?
                 AND (
                     node_id IN ('loc_eastern_temple', 'fac_temple_residence', 'fac_onsen_villa')
                     OR (parent_id = 'zone_woods_reserve' AND node_id LIKE 'fac_npc_res_%' AND (LOWER(name) LIKE '%cypress villa%' OR LOWER(name) LIKE '%cloister%'))
                 )""",
            (sid,),
        )
        conn.execute(
            "UPDATE world_nodes SET parent_id = 'zone_undercity' WHERE session_id = ? AND node_id = 'loc_cult_sanctum_hq' AND parent_id = 'zone_woods_reserve'",
            (sid,),
        )
        conn.execute(
            "UPDATE world_nodes SET parent_id = 'zone_industrial' WHERE session_id = ? AND node_id = 'loc_clandestine_syndicate_hq' AND parent_id = 'zone_woods_reserve'",
            (sid,),
        )

        for z_id_target, z_obj, z_disp in (
            ("zone_eastern_sanctuary", z_sanc, str(z_sanc.get("name") or sanctuary_zone_name)),
            ("zone_woods_reserve", z_woods, str(z_woods.get("name") or woods_zone_name)),
        ):
            for prim in (z_obj.get("primary_locations") or []):
                p_id = str(prim.get("id") or "")
                if not p_id:
                    continue
                if z_id_target == "zone_woods_reserve" and p_id != "loc_hidden_bunian_village":
                    continue
                is_hid = bool(prim.get("is_hidden"))
                disp_p_name = str((prim.get("mundane_name") if is_hid else prim.get("name")) or prim.get("name") or p_id)
                p_meta = {
                    k: prim[k]
                    for k in ("privacy_level", "is_enclosed", "is_hidden", "discovered", "veil_village_key", "veil_token_item", "is_anomalous", "mundane_name")
                    if k in prim
                }
                if is_hid:
                    p_meta["true_name"] = str(prim.get("name") or disp_p_name)
                conn.execute(
                    """INSERT OR IGNORE INTO world_nodes
                       (session_id, node_id, parent_id, name, node_type, category, privacy_level, is_enclosed, is_transit_hub, access_tier, atmosphere, is_dynamic, state_json)
                       VALUES (?, ?, ?, ?, 'FACILITY', 'sacred', ?, ?, 0, ?, ?, 0, ?)""",
                    (
                        sid,
                        p_id,
                        z_id_target,
                        disp_p_name,
                        str(prim.get("privacy_level") or "public"),
                        int(bool(prim.get("is_enclosed", 0))),
                        str(prim.get("access_tier") or "open"),
                        str(prim.get("atmosphere") or z_obj.get("atmosphere") or ""),
                        json.dumps(p_meta) if p_meta else None,
                    ),
                )
                subs = prim.get("sub_locations") or []
                ent_id = None
                room_ids: list[str] = []
                for sub in subs:
                    s_id = str(sub.get("id") or "")
                    if not s_id:
                        continue
                    room_ids.append(s_id)
                    if sub.get("is_entrance") and not ent_id:
                        ent_id = s_id
                    s_meta = {
                        k: sub[k]
                        for k in ("privacy_level", "is_enclosed", "is_entrance", "is_hidden", "discovered", "veil_village_key", "veil_token_item", "is_anomalous")
                        if k in sub
                    }
                    if s_id == "loc_et_fox_torii_tunnel":
                        conn.execute(
                            "UPDATE world_nodes SET parent_id = 'loc_hidden_kitsune_village', state_json = COALESCE(state_json, ?) WHERE session_id = ? AND node_id = ?",
                            (json.dumps(s_meta), sid, s_id),
                        )
                    conn.execute(
                        """INSERT OR IGNORE INTO world_nodes
                           (session_id, node_id, parent_id, name, node_type, category, privacy_level, is_enclosed, is_transit_hub, access_tier, atmosphere, is_dynamic, state_json)
                           VALUES (?, ?, ?, ?, 'ROOM', 'sacred', ?, ?, 0, ?, ?, 0, ?)""",
                        (
                            sid,
                            s_id,
                            p_id,
                            str(sub.get("name") or s_id),
                            str(sub.get("privacy_level") or "public"),
                            int(bool(sub.get("is_enclosed", 0))),
                            str(sub.get("access_tier") or "open"),
                            str(z_obj.get("atmosphere") or ""),
                            json.dumps(s_meta) if s_meta else None,
                        ),
                    )
                    if not sub.get("is_hidden"):
                        conn.execute(
                            """INSERT OR IGNORE INTO session_locations
                               (session_id, location_id, zone_name, primary_name, sub_name, atmosphere, is_dynamic, created_at)
                               VALUES (?, ?, ?, ?, ?, ?, 0, strftime('%s','now'))""",
                            (sid, s_id, z_disp, disp_p_name, str(sub.get("name") or s_id), str(z_obj.get("atmosphere") or "")),
                        )
                if ent_id:
                    conn.execute(
                        """INSERT OR IGNORE INTO world_edges
                           (session_id, from_node_id, to_node_id, travel_minutes, is_locked, skill_check_type, skill_check_dc, edge_type, is_bidirectional)
                           VALUES (?, ?, ?, 1, 0, '', 0, 'door', 1)""",
                        (sid, p_id, ent_id),
                    )
                    for r_id in room_ids:
                        if r_id != ent_id:
                            conn.execute(
                                """INSERT OR IGNORE INTO world_edges
                                   (session_id, from_node_id, to_node_id, travel_minutes, is_locked, skill_check_type, skill_check_dc, edge_type, is_bidirectional)
                                   VALUES (?, ?, ?, 2, 0, '', 0, 'pathway', 1)""",
                                (sid, ent_id, r_id),
                            )

        conn.execute(
            """UPDATE player_properties
               SET zone_id = 'zone_eastern_sanctuary'
               WHERE session_id = ?
                 AND (property_id IN ('starter_temple_residence', 'prop_onsen_villa') OR facility_node_id IN ('fac_temple_residence', 'fac_onsen_villa'))""",
            (sid,),
        )
        conn.execute(
            """UPDATE session_locations
               SET zone_name = ?
               WHERE session_id = ?
                 AND (
                     location_id IN ('loc_et_torii_approach', 'loc_et_main_sanctuary', 'loc_et_omikuji_shop', 'loc_et_five_story_pagoda', 'loc_et_zen_tea_garden', 'loc_et_onsen_bathhouse', 'loc_et_weeping_statues', 'loc_et_fox_torii_tunnel',
                                     'sub_temple_res_courtyard', 'sub_temple_res_veranda', 'sub_temple_res_cell',
                                     'sub_villa_gatehouse', 'sub_villa_hearth_hall', 'sub_villa_hotspring_bath', 'sub_villa_tatami_suite')
                     OR LOWER(primary_name) LIKE '%eastern grand temple%'
                     OR LOWER(primary_name) LIKE '%outer cloister initiate quarters%'
                     OR LOWER(primary_name) LIKE '%cypress mountain onsen villa%'
                     OR LOWER(primary_name) LIKE '%mountain cypress villa%'
                 )""",
            (sanctuary_zone_name, sid),
        )
        conn.execute(
            """UPDATE session_locations
               SET primary_name = 'Thousand-Torii Fox Shrine Approach'
               WHERE session_id = ? AND location_id = 'loc_et_fox_torii_tunnel'""",
            (sid,),
        )

        for f_a, f_b, mins, etype, locked, sc_type, sc_dc in (
            ("loc_eastern_temple", "loc_es_lantern_tea_street", 5, "pathway", 0, "", 0),
            ("loc_es_lantern_tea_street", "loc_es_bamboo_footbath_bridge", 5, "pathway", 0, "", 0),
            ("loc_eastern_temple", "loc_hidden_kitsune_village", 5, "pathway", 0, "", 0),
            ("loc_eastern_temple", "fac_temple_residence", 5, "pathway", 0, "", 0),
            ("loc_eastern_temple", "fac_onsen_villa", 5, "pathway", 0, "", 0),
            ("loc_forest_trails", "loc_hidden_bunian_village", 5, "pathway", 0, "", 0),
            ("loc_eastern_temple", "loc_forest_trails", 15, "transit", 0, "", 0),
            ("sub_kitsune_inner_plaza", "sub_bunian_inner_plaza", 2, "leyline_spirit_passage", 1, "PER", 15),
            ("sub_kitsune_leyline_shrine", "sub_bunian_orchid_spring", 2, "leyline_spirit_passage", 1, "PER", 15),
        ):
            conn.execute(
                """INSERT OR IGNORE INTO world_edges
                   (session_id, from_node_id, to_node_id, travel_minutes, is_locked, skill_check_type, skill_check_dc, edge_type, is_bidirectional)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
                (sid, f_a, f_b, mins, locked, sc_type, sc_dc, etype),
            )
        migrated_sessions += 1

    return migrated_sessions
