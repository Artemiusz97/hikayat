from __future__ import annotations

import json
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
