from __future__ import annotations
"""Realm discovery, legacy wrapping, dynamic realm spawning/pacification/collapse, and rollback."""

import uuid
from typing import Any, Mapping, Optional

import db

from .constants import (
    DEFAULT_REALM_RULES,
    DYNAMIC_REALM_TEMPLATES,
    _default_primary_realm_meta,
    _slugify_id,
)
from .hierarchy import (
    get_node_realm_id_in_memory,
    get_primary_realm_in_memory,
    get_realm_rules,
    parse_node_state_json,
)
from .vessels import _rewire_vessel_dock


def ensure_default_realm_wrapper(
    session_id: int,
    scenario_key: str = "",
    *,
    conn: Any = None,
) -> str:
    """
    Conservatively wraps orphan ZONE nodes (parent_id IS NULL) in legacy sessions
    under 1 default primary REALM node without altering active quests, waypoints, or current_node_id.
    """
    if not session_id:
        return ""
    if conn is None and db.is_in_readonly_uow():
        return ""

    def _run(c: Any) -> str:
        rows = db.get_session_world_nodes_tx(session_id, conn=c)
        if not rows:
            return ""
        existing_realms = [r for r in rows if str(r.get("node_type") or "").upper() == "REALM"]
        if existing_realms:
            for r in existing_realms:
                if get_realm_rules(r).get("is_primary_realm"):
                    return str(r["node_id"])
            return str(existing_realms[0]["node_id"])

        orphan_zones = [
            r for r in rows
            if str(r.get("node_type") or "").upper() == "ZONE" and not str(r.get("parent_id") or "").strip()
        ]
        if not orphan_zones:
            return ""

        eff_scen = str(scenario_key or "").strip()
        if not eff_scen:
            eff_scen = db.get_session_scenario_tx(session_id, conn=c)

        realm_id, realm_name = _default_primary_realm_meta(eff_scen)
        rules = dict(DEFAULT_REALM_RULES)
        rules.update({
            "realm_kind": "world",
            "is_primary_realm": True,
            "is_hidden": False,
            "discovered": True,
        })
        db.upsert_world_node_tx(
            session_id,
            realm_id,
            None,
            realm_name,
            "REALM",
            category="realm",
            privacy_level="public",
            is_enclosed=0,
            is_transit_hub=0,
            access_tier="open",
            atmosphere="",
            is_dynamic=0,
            state_json=rules,
            overwrite_on_conflict=False,
            conn=c,
        )
        db.reparent_orphan_zones_to_realm(session_id, realm_id, conn=c)
        return realm_id

    if conn is not None:
        return _run(conn)
    with db.UnitOfWork() as uow_conn:
        return _run(uow_conn)


def discover_realm(
    session_id: int,
    realm_id: str,
    turn_number: int = 1,
    *,
    conn: Any = None,
) -> bool:
    """Marks a hidden REALM node as discovered and reveals hidden portal entries targeting it."""
    if not session_id or not realm_id:
        return False
    if conn is None and db.is_in_readonly_uow():
        return False

    def _run(c: Any) -> bool:
        row = db.get_world_node_tx(session_id, realm_id, conn=c)
        if not row or str(row.get("node_type") or "").upper() != "REALM":
            return False
        st = parse_node_state_json(row)
        changed = False
        if st.get("is_hidden") or not st.get("discovered", True):
            if "started_hidden" not in st:
                st["started_hidden"] = bool(st.get("is_hidden"))
            st["is_hidden"] = False
            st["discovered"] = True
            st["discovered_turn"] = int(turn_number or 1)
            db.update_world_node_state_json(session_id, realm_id, st, conn=c)
            changed = True

        for pn in db.get_session_world_nodes_tx(session_id, conn=c):
            raw_s = pn.get("state_json")
            if not raw_s or (isinstance(raw_s, str) and "portals" not in raw_s):
                continue
            p_st = parse_node_state_json(pn)
            portals = p_st.get("portals")
            if not isinstance(portals, dict):
                continue
            p_dirty = False
            for p_meta in portals.values():
                if isinstance(p_meta, dict) and str(p_meta.get("target_realm_id") or "") == realm_id:
                    if p_meta.get("require_explicit_portal_unlock"):
                        continue
                    if p_meta.get("is_hidden_portal"):
                        if "started_hidden_portal" not in p_meta:
                            p_meta["started_hidden_portal"] = True
                        p_meta["is_hidden_portal"] = False
                        p_meta["discovered_turn"] = int(turn_number or 1)
                        p_dirty = True
            if p_dirty:
                p_st["portals"] = portals
                db.update_world_node_state_json(session_id, str(pn["node_id"]), p_st, conn=c)
                changed = True

        # v2 Veiled Spirit Realm fog-of-war: entering the Spirit Realm reveals Dusk Confluence
        # AND all 4 frontier biomes immediately; only the 3 enclaves remain hidden until discovered.
        if realm_id == "realm_veiled_spirit_world":
            from ..folklore_spirit_courts import SPIRIT_CROSSROADS_ZONE_ID, SPIRIT_FRONTIER_ZONE_IDS
            from ..folklore_spirit_realm import reveal_spirit_zone
            for z_auto in (SPIRIT_CROSSROADS_ZONE_ID, *SPIRIT_FRONTIER_ZONE_IDS):
                res_z = reveal_spirit_zone(session_id, z_auto, turn_number=int(turn_number or 1), conn=c)
                if int((res_z or {}).get("revealed_nodes") or 0) > 0:
                    changed = True
        return changed

    if conn is not None:
        return _run(conn)
    with db.UnitOfWork() as uow_conn:
        return _run(uow_conn)


def _resolve_dynamic_template(template_id: str, scenario_key: str = "") -> Optional[dict[str, Any]]:
    tid = str(template_id or "").strip()
    if not tid:
        return None
    if scenario_key:
        try:
            from ..seeds import get_scenario_seed_data
            scen_data = get_scenario_seed_data(scenario_key)
            for tmpl in (scen_data.get("dynamic_realm_templates") or []):
                if isinstance(tmpl, Mapping) and str(tmpl.get("template_id") or tmpl.get("id") or "") == tid:
                    return dict(tmpl)
        except Exception:
            pass
    tmpl = DYNAMIC_REALM_TEMPLATES.get(tid)
    return dict(tmpl) if tmpl else None


def spawn_dynamic_realm(
    session_id: int,
    template_id: str,
    origin_node_id: str,
    turn_number: int = 1,
    *,
    scenario_key: str = "",
    custom_name: str = "",
    exit_mode_override: str = "",
    conn: Any = None,
) -> dict[str, Any]:
    """
    Deterministically spawns a dynamic pocket/rift REALM from a registered template
    (never unconstrained LLM realm generation). Tracks created_turn for rollback.
    """
    if not session_id or not origin_node_id:
        raise ValueError("session_id and origin_node_id are required to spawn a dynamic realm.")
    tmpl = _resolve_dynamic_template(template_id, scenario_key=scenario_key)
    if not tmpl:
        raise ValueError(f"Unknown dynamic realm template '{template_id}'.")

    suffix = uuid.uuid4().hex[:6]
    realm_id = f"realm_dyn_{_slugify_id(template_id)}_{suffix}"
    realm_name = str(custom_name or tmpl.get("name") or "Anomalous Dimension").strip()
    exit_mode = str(exit_mode_override or tmpl.get("exit_mode") or "open")

    def _run(c: Any) -> dict[str, Any]:
        all_rows = db.get_session_world_nodes_tx(session_id, conn=c)
        nodes_by_id = {str(r["node_id"]): dict(r) for r in all_rows if r.get("node_id")}
        origin_realm_id = get_node_realm_id_in_memory(origin_node_id, nodes_by_id)

        rules = dict(DEFAULT_REALM_RULES)
        rules.update({
            "realm_kind": str(tmpl.get("realm_kind") or "anomalous_dimension"),
            "is_primary_realm": False,
            "is_hidden": False,
            "discovered": True,
            "comms_isolated": bool(tmpl.get("comms_isolated", True)),
            "npc_spillover": bool(tmpl.get("npc_spillover", False)),
            "time_scale": float(tmpl.get("time_scale", 0.0)),
            "has_local_safe_hub": bool(tmpl.get("has_local_safe_hub", False)),
            "exit_mode": exit_mode,
            "is_ephemeral": bool(tmpl.get("is_ephemeral", True)),
            "ephemeral_origin_node_id": origin_node_id,
            "ephemeral_origin_realm_id": origin_realm_id,
            "template_id": str(template_id),
            "created_turn": int(turn_number or 1),
            "discovered_turn": int(turn_number or 1),
            "portal_icon": str(tmpl.get("portal_icon") or "🌀"),
        })

        db.upsert_world_node_tx(
            session_id,
            realm_id,
            None,
            realm_name,
            "REALM",
            category="realm",
            privacy_level="public",
            is_enclosed=0,
            is_transit_hub=0,
            access_tier="open",
            atmosphere="",
            is_dynamic=1,
            state_json=rules,
            overwrite_on_conflict=True,
            conn=c,
        )

        entry_node_id = ""
        created_room_ids: list[str] = []
        raw_subs = list(tmpl.get("sub_locations") or [])
        for idx, sub in enumerate(raw_subs):
            base_sid = str(sub.get("id") or f"sub_{idx}").strip()
            s_id = f"{base_sid}_{suffix}"
            s_name = str(sub.get("name") or f"Rift Chamber {idx + 1}")
            is_ent = 1 if (sub.get("is_entrance") or idx == 0) else 0
            if not entry_node_id and is_ent:
                entry_node_id = s_id
            s_state: dict[str, Any] = {
                "is_entrance": is_ent,
                "is_anomalous": True,
                "props": list(sub.get("props") or [])[:4],
            }
            if is_ent:
                s_state["portals"] = {
                    origin_node_id: {
                        "target_realm_id": origin_realm_id,
                        "label": "🌀 Return through Rift",
                        "icon": "🌀",
                        "is_hidden_portal": False,
                    }
                }
            s_atm = str(sub.get("sensory") or sub.get("atmosphere") or "")
            db.upsert_world_node_tx(
                session_id,
                s_id,
                realm_id,
                s_name,
                "ROOM",
                category="anomaly",
                privacy_level="public",
                is_enclosed=1,
                is_transit_hub=0,
                access_tier="open",
                atmosphere=s_atm,
                is_dynamic=1,
                state_json=s_state,
                overwrite_on_conflict=True,
                conn=c,
            )
            created_room_ids.append(s_id)

        for i in range(len(created_room_ids) - 1):
            u_r, v_r = created_room_ids[i], created_room_ids[i + 1]
            for a, b in ((u_r, v_r), (v_r, u_r)):
                db.upsert_world_edge_tx(
                    session_id,
                    a,
                    b,
                    travel_minutes=2,
                    edge_type="hallway",
                    is_bidirectional=1,
                    is_locked=0,
                    update_on_conflict=False,
                    conn=c,
                )

        if entry_node_id:
            return_locked = 1 if exit_mode == "lockdown_until_cleared" else 0
            edge_bidir = 0 if return_locked else 1
            db.upsert_world_edge_tx(
                session_id,
                origin_node_id,
                entry_node_id,
                travel_minutes=5,
                edge_type="dimensional_rift",
                is_bidirectional=edge_bidir,
                is_locked=0,
                update_on_conflict=True,
                conn=c,
            )
            db.upsert_world_edge_tx(
                session_id,
                entry_node_id,
                origin_node_id,
                travel_minutes=5,
                edge_type="dimensional_rift",
                is_bidirectional=edge_bidir,
                is_locked=return_locked,
                update_on_conflict=True,
                conn=c,
            )
            o_row = db.get_world_node_tx(session_id, origin_node_id, conn=c)
            if o_row:
                o_st = parse_node_state_json(o_row)
                o_portals = dict(o_st.get("portals") or {})
                o_portals[entry_node_id] = {
                    "target_realm_id": realm_id,
                    "label": f"🌀 Enter {realm_name}",
                    "icon": "🌀",
                    "is_hidden_portal": False,
                }
                o_st["portals"] = o_portals
                db.update_world_node_state_json(session_id, origin_node_id, o_st, conn=c)

        return {
            "realm_id": realm_id,
            "realm_name": realm_name,
            "entry_node_id": entry_node_id,
            "room_ids": created_room_ids,
            "exit_mode": exit_mode,
        }

    if conn is not None:
        return _run(conn)
    with db.UnitOfWork() as uow_conn:
        return _run(uow_conn)


def pacify_dynamic_realm(
    session_id: int,
    realm_id: str,
    turn_number: int = 1,
    *,
    conn: Any = None,
) -> bool:
    """Marks a realm as pacified and unlocks any locked return portal edges out of it."""
    if not session_id or not realm_id:
        return False

    def _run(c: Any) -> bool:
        row = db.get_world_node_tx(session_id, realm_id, conn=c)
        if not row or str(row.get("node_type") or "").upper() != "REALM":
            return False
        st = parse_node_state_json(row)
        st["pacified"] = True
        st["pacified_turn"] = int(turn_number or 1)
        db.update_world_node_state_json(session_id, realm_id, st, conn=c)

        all_rows = db.get_session_world_nodes_tx(session_id, conn=c)
        n_map = {str(r["node_id"]): r for r in all_rows if r.get("node_id")}
        realm_member_ids = [nid for nid in n_map if get_node_realm_id_in_memory(nid, n_map) == realm_id]
        if realm_member_ids:
            db.unlock_realm_edges_by_types(
                session_id,
                realm_member_ids,
                ("dimensional_rift", "planar_portal", "leyline_spirit_passage"),
                lock_return_only=False,
                conn=c,
            )
        return True

    if conn is not None:
        return _run(conn)
    with db.UnitOfWork() as uow_conn:
        return _run(uow_conn)


def collapse_dynamic_realm(
    session_id: int,
    realm_id: str,
    *,
    conn: Any = None,
) -> dict[str, Any]:
    """Removes a dynamic realm, all its descendant nodes, incident edges, and portal metadata."""
    if not session_id or not realm_id:
        return {"deleted_nodes": 0, "deleted_edges": 0}

    def _run(c: Any) -> dict[str, Any]:
        all_rows = db.get_session_world_nodes_tx(session_id, conn=c)
        n_map = {str(r["node_id"]): r for r in all_rows if r.get("node_id")}
        if realm_id not in n_map:
            return {"deleted_nodes": 0, "deleted_edges": 0}
        to_delete = [nid for nid in n_map if nid == realm_id or get_node_realm_id_in_memory(nid, n_map) == realm_id]
        if not to_delete:
            return {"deleted_nodes": 0, "deleted_edges": 0}
        return db.delete_realm_nodes_and_edges(session_id, to_delete, realm_id, conn=c)

    if conn is not None:
        return _run(conn)
    with db.UnitOfWork() as uow_conn:
        return _run(uow_conn)


def rollback_realm_state_after_turn(
    session_id: int,
    turn_number: int,
    *,
    conn: Any = None,
) -> dict[str, int]:
    """
    Reverts realm mutations committed after `turn_number`:
      1. Deletes dynamic realms with created_turn > turn_number (and heals dangling player location)
      2. Re-hides realms with discovered_turn > turn_number (if started_hidden)
      3. Reverts pacified_turn > turn_number (re-locking lockdown return edges incl. leyline_spirit_passage)
      4. Reverts mobile vessel docking where docked_turn > turn_number (unwinding multi-jump dock_history)
    """
    counts = {
        "realms_deleted": 0,
        "realms_rehidden": 0,
        "realms_unpacified": 0,
        "vessels_reverted": 0,
    }
    if not session_id:
        return counts
    t_num = int(turn_number)

    def _run(c: Any) -> dict[str, int]:
        from .vessels import _undock_vessel_cleanly

        all_rows = db.get_session_world_nodes_tx(session_id, conn=c)
        realm_rows = [r for r in all_rows if str(r.get("node_type") or "").upper() == "REALM"]
        collapse_origins: list[str] = []
        collapsed_rids: set[str] = set()

        # Pass 1: Delete dynamic realms created after t_num (both ephemeral and non-ephemeral templates)
        for r in realm_rows:
            rid = str(r["node_id"])
            st = parse_node_state_json(r)
            created_t = int(st.get("created_turn") or 0)
            is_dynamic_realm = bool(st.get("is_ephemeral") or st.get("template_id") or int(r.get("is_dynamic") or 0) == 1)
            if is_dynamic_realm and created_t > t_num:
                orig_nid = str(st.get("ephemeral_origin_node_id") or "").strip()
                if orig_nid:
                    collapse_origins.append(orig_nid)
                collapse_dynamic_realm(session_id, rid, conn=c)
                collapsed_rids.add(rid)
                counts["realms_deleted"] += 1

        # Pass 2: Re-hide, unpacify, and revert mobile vessels against surviving nodes
        surviving_rows = db.get_session_world_nodes_tx(session_id, conn=c)
        surviving_map = {str(nr["node_id"]): dict(nr) for nr in surviving_rows if nr.get("node_id")}
        surviving_realms = [nr for nr in surviving_rows if str(nr.get("node_type") or "").upper() == "REALM"]

        for r in surviving_realms:
            rid = str(r["node_id"])
            if rid in collapsed_rids:
                continue
            st = parse_node_state_json(r)
            dirty = False
            disc_t = int(st.get("discovered_turn") or 0)
            if disc_t > t_num and st.get("started_hidden"):
                st["is_hidden"] = True
                st["discovered"] = False
                st["discovered_turn"] = 0
                dirty = True
                counts["realms_rehidden"] += 1

            pac_t = int(st.get("pacified_turn") or 0)
            if pac_t > t_num and st.get("pacified"):
                st["pacified"] = False
                st["pacified_turn"] = 0
                dirty = True
                counts["realms_unpacified"] += 1
                if st.get("exit_mode") == "lockdown_until_cleared":
                    member_ids = [
                        nid for nid in surviving_map if get_node_realm_id_in_memory(nid, surviving_map) == rid
                    ]
                    if member_ids:
                        db.unlock_realm_edges_by_types(
                            session_id,
                            member_ids,
                            ("dimensional_rift", "planar_portal", "leyline_spirit_passage"),
                            lock_return_only=True,
                            conn=c,
                        )

            dock_hist = [dict(h) for h in (st.get("dock_history") or []) if isinstance(h, dict)]
            after_hist = [h for h in dock_hist if int(h.get("turn") or 0) > t_num]
            dock_t = int(st.get("docked_turn") or 0)
            if st.get("is_mobile_vessel") and (after_hist or dock_t > t_num):
                if dirty:
                    db.update_world_node_state_json(session_id, rid, st, conn=c)
                    dirty = False
                kept_hist = [h for h in dock_hist if int(h.get("turn") or 0) <= t_num]
                if after_hist:
                    earliest_reverted = min(after_hist, key=lambda h: int(h.get("turn") or 0))
                    prev_r = str(earliest_reverted.get("prev_realm_id") or "").strip()
                    prev_n = str(earliest_reverted.get("prev_node_id") or "").strip()
                else:
                    prev_r = str(st.get("docked_realm_id_prev") or "").strip()
                    prev_n = str(st.get("docked_node_id_prev") or "").strip()

                target_valid = bool(prev_r and prev_n and prev_r in surviving_map and prev_n in surviving_map)
                if not target_valid:
                    prim_realm = get_primary_realm_in_memory(surviving_map)
                    prim_rules = get_realm_rules(prim_realm) if prim_realm else {}
                    prim_dock = str(prim_rules.get("dock_node_id") or "").strip()
                    prim_rid = str((prim_realm or {}).get("node_id") or "").strip()
                    if prim_rid and prim_dock and prim_dock in surviving_map and prim_rid != rid:
                        prev_r, prev_n = prim_rid, prim_dock
                        target_valid = True

                if target_valid:
                    _rewire_vessel_dock(c, session_id, rid, prev_r, prev_n, 0)
                    v_fresh = db.get_world_node_tx(session_id, rid, conn=c)
                    if v_fresh:
                        vst = parse_node_state_json(v_fresh)
                        vst["dock_history"] = kept_hist
                        if kept_hist:
                            last_kept = kept_hist[-1]
                            vst["docked_turn"] = int(last_kept.get("turn") or 0)
                            vst["docked_realm_id_prev"] = str(last_kept.get("prev_realm_id") or "")
                            vst["docked_node_id_prev"] = str(last_kept.get("prev_node_id") or "")
                        else:
                            vst["docked_turn"] = 0
                            vst["docked_realm_id_prev"] = ""
                            vst["docked_node_id_prev"] = ""
                        db.update_world_node_state_json(session_id, rid, vst, conn=c)
                else:
                    _undock_vessel_cleanly(c, session_id, rid, kept_hist)
                counts["vessels_reverted"] += 1
                continue

            if dirty:
                db.update_world_node_state_json(session_id, rid, st, conn=c)

        if counts["realms_deleted"] > 0:
            db.fix_dangling_session_node_after_collapse(session_id, collapse_origins, conn=c)

        for pr in db.get_session_world_nodes_tx(session_id, conn=c):
            raw_ps = pr.get("state_json")
            if not raw_ps or (isinstance(raw_ps, str) and "started_hidden_portal" not in raw_ps):
                continue
            pst = parse_node_state_json(pr)
            portals = pst.get("portals")
            if not isinstance(portals, dict):
                continue
            p_dirty = False
            for p_meta in portals.values():
                if isinstance(p_meta, dict) and p_meta.get("started_hidden_portal") and int(p_meta.get("discovered_turn") or 0) > t_num:
                    p_meta["is_hidden_portal"] = True
                    p_meta["discovered_turn"] = 0
                    p_dirty = True
            if p_dirty:
                pst["portals"] = portals
                db.update_world_node_state_json(session_id, str(pr["node_id"]), pst, conn=c)
        return counts

    if conn is not None:
        return _run(conn)
    with db.UnitOfWork() as uow_conn:
        return _run(uow_conn)
