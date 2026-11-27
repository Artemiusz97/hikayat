"""
mechanics/world/locations/folklore_spirit_realm.py
==================================================
Engine for the Hidden Veiled Spirit Realm (`realm_veiled_spirit_world`):
- Node/zone predicates (`is_node_in_spirit_realm`, `infer_spirit_village_for_node`,
  `is_node_in_sanctuary_pact_zone`, `is_node_in_crossroads_truce`)
- v2 Fog-of-war: entering the Spirit Realm immediately reveals `zone_spirit_crossroads`
  and all 4 frontier biomes (`zone_spirit_wilds`, `zone_spirit_peaks`, `zone_spirit_mire`,
  `zone_spirit_boneyard`), while keeping the 3 enclaves (`kitsune`, `bunian`, `ghoul`)
  hidden until individually discovered (via Human threshold or overland bypass + Back-Door Attunement).
- Chinatown 3rd Shortcut Rite (Spirit-side unsealing via 50g offering, PER 12, or Spirit Court rep >= 25)
- Dusk Confluence Neutral Truce ejection (+15m to `sub_wilds_ward_camp`)
- Re-exports Spirit Court / Guest-Cottage / Sparring (`folklore_spirit_courts.py`) and
  Migration/Rollback (`folklore_spirit_realm_lifecycle.py`) APIs for callers.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Mapping, Optional

import db

from .folklore_spirit_courts import (
    ALL_SPIRIT_GUEST_FACILITY_IDS,
    ALL_SPIRIT_GUEST_PROPERTY_IDS,
    CHINATOWN_OFFERING_GOLD,
    CHINATOWN_SHORTCUT_HUMAN_NODE,
    CHINATOWN_SHORTCUT_SPIRIT_NODE,
    CROSSROADS_TEA_FALLBACK_NODE_ID,
    SPIRIT_BONEYARD_ZONE_ID,
    SPIRIT_COURT_FACTIONS,
    SPIRIT_CROSSROADS_ZONE_ID,
    SPIRIT_FRONTIER_ZONE_IDS,
    SPIRIT_GUEST_COTTAGE_SPEC,
    SPIRIT_MIRE_ZONE_ID,
    SPIRIT_PEAKS_ZONE_ID,
    SPIRIT_REALM_ID,
    SPIRIT_SPARRING_ROOMS,
    SPIRIT_VILLAGE_BY_ZONE,
    SPIRIT_VILLAGE_KEYS,
    SPIRIT_VILLAGE_PUBLIC_FACILITIES,
    SPIRIT_WILDS_ZONE_ID,
    SPIRIT_ZONE_BY_VILLAGE,
    WILDS_SAFE_RESCUE_NODE_ID,
    _get_court_rep_sql,
    _mutate_spirit_realm_state,
    _parse_json_dict,
    _resolve_turn_num,
    _uow_ctx,
    adjust_spirit_court_reputation,
    build_spirit_court_diplomacy,
    build_spirit_court_leadership_roster,
    compute_spirit_court_starting_rep,
    ensure_spirit_court_faction_discovered,
    get_effective_village_standing,
    get_spirit_court_discount_multiplier,
    get_spirit_realm_state,
    is_ghoul_council_distrusted,
    maybe_grant_spirit_guest_cottage,
    resolve_spirit_sparring_drill,
    sync_spirit_court_leadership_and_diplomacy,
)

log = logging.getLogger("hikayat.world.folklore_spirit_realm")

_HUMAN_THRESHOLD_BY_VILLAGE: Dict[str, str] = {
    "kitsune": "loc_et_fox_torii_tunnel",
    "bunian": "loc_bunian_threshold_glade",
    "ghoul": "sub_uc_black_font",
}

_PLAZA_BY_VILLAGE: Dict[str, str] = {
    "kitsune": "sub_kitsune_inner_plaza",
    "bunian": "sub_bunian_inner_plaza",
    "ghoul": "sub_ghoul_inner_plaza",
}

_VILLAGE_HQ_BY_KEY: Dict[str, str] = {
    "kitsune": "loc_hidden_kitsune_village",
    "bunian": "loc_hidden_bunian_village",
    "ghoul": "loc_hidden_ghoul_village",
}


def is_node_in_spirit_realm(
    session_id: int,
    node_id: Optional[str],
    *,
    nodes_by_id: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> bool:
    """Returns True when `node_id` belongs to `realm_veiled_spirit_world`."""
    nid = str(node_id or "").strip()
    if not nid:
        return False
    if (
        nid == SPIRIT_REALM_ID
        or nid in SPIRIT_VILLAGE_BY_ZONE
        or nid == SPIRIT_CROSSROADS_ZONE_ID
        or nid in SPIRIT_FRONTIER_ZONE_IDS
    ):
        return True
    if nid.startswith((
        "sub_kitsune_", "loc_kitsune_foxfire", "loc_kitsune_mask", "loc_kitsune_scroll",
        "loc_kitsune_blade", "fac_kitsune_guest",
        "sub_bunian_", "loc_bunian_orchid", "loc_bunian_songket", "loc_bunian_silat",
        "loc_bunian_canopy", "fac_bunian_guest",
        "sub_ghoul_", "loc_ghoul_", "fac_ghoul_guest",
        "loc_crossroads_", "sub_crossroads_",
        "loc_wilds_", "sub_wilds_",
        "loc_peaks_", "sub_peaks_",
        "loc_mire_", "sub_mire_",
        "loc_boneyard_", "sub_boneyard_",
    )) or nid in ("loc_hidden_kitsune_village", "loc_hidden_bunian_village", "loc_hidden_ghoul_village"):
        return True
    if nodes_by_id is not None:
        from .realms import get_node_realm_id_in_memory
        return get_node_realm_id_in_memory(nid, nodes_by_id) == SPIRIT_REALM_ID
    if session_id:
        from .realms import get_node_realm_id
        return get_node_realm_id(int(session_id), nid) == SPIRIT_REALM_ID
    return False


def infer_spirit_village_for_node(
    node_id: Optional[str],
    *,
    nodes_by_id: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> str:
    """Returns 'kitsune', 'bunian', or 'ghoul' for village facilities/rooms and mundane thresholds, else ''."""
    nid = str(node_id or "").strip()
    if not nid:
        return ""
    if nid in SPIRIT_ZONE_BY_VILLAGE.values():
        return SPIRIT_VILLAGE_BY_ZONE[nid]
    if nid in SPIRIT_VILLAGE_PUBLIC_FACILITIES["kitsune"] or nid in (
        "loc_kitsune_torii_approach", "loc_et_fox_torii_tunnel",
        "fac_kitsune_guest_villa", "sub_kitsune_villa_engawa", "sub_kitsune_villa_sleeping_room",
    ) or nid.startswith("sub_kitsune_") or nid.startswith("loc_kitsune_"):
        return "kitsune"
    if nid in SPIRIT_VILLAGE_PUBLIC_FACILITIES["bunian"] or nid in (
        "loc_bunian_mist_glade", "loc_bunian_threshold_glade",
        "fac_bunian_guest_house", "sub_bunian_house_veranda", "sub_bunian_house_chamber",
    ) or nid.startswith("sub_bunian_") or nid.startswith("loc_bunian_"):
        return "bunian"
    if nid in SPIRIT_VILLAGE_PUBLIC_FACILITIES["ghoul"] or nid in (
        "sub_uc_black_font",
        "fac_ghoul_guest_manor", "sub_ghoul_suite_foyer", "sub_ghoul_suite_bedroom",
    ) or nid.startswith("sub_ghoul_") or nid.startswith("loc_ghoul_"):
        return "ghoul"
    if nodes_by_id:
        cur: Optional[str] = nid
        seen: set[str] = set()
        while cur and cur not in seen:
            seen.add(cur)
            if cur in SPIRIT_VILLAGE_BY_ZONE:
                return SPIRIT_VILLAGE_BY_ZONE[cur]
            row = nodes_by_id.get(cur)
            if not isinstance(row, Mapping):
                break
            st = _parse_json_dict(row.get("state_json"))
            vk = str(st.get("veil_village_key") or "").strip().lower()
            if vk in SPIRIT_VILLAGE_KEYS:
                return vk
            cur = str(row.get("parent_id") or "").strip() or None
    return ""


def is_node_in_sanctuary_pact_zone(
    node_id: Optional[str],
    *,
    nodes_by_id: Optional[Mapping[str, Mapping[str, Any]]] = None,
    action_intent: str = "",
    action_label: str = "",
) -> str:
    """
    Returns 'kitsune', 'bunian', or 'ghoul' if Sanctuary Non-Aggression Pact applies at `node_id`.
    Covers all 5 public facilities + rooms per village; exempts all 4 Frontier wilderness biomes,
    `zone_spirit_crossroads`, Human thresholds, and friendly sparring drills in Blade-Yard / Silat Courtyard / Ash-Pit.
    """
    nid = str(node_id or "").strip()
    if not nid or nid.startswith((
        "loc_wilds_", "sub_wilds_",
        "loc_peaks_", "sub_peaks_",
        "loc_mire_", "sub_mire_",
        "loc_boneyard_", "sub_boneyard_",
        "loc_crossroads_", "sub_crossroads_",
    )):
        return ""
    if nid == SPIRIT_CROSSROADS_ZONE_ID or nid in SPIRIT_FRONTIER_ZONE_IDS:
        return ""
    lbl = str(action_label or "").lower()
    _hostile_spar_verbs = (
        "kill", "slay", "murder", "execute", "assassinate",
        "slaughter", "contain", "capture", "ambush", "strangle", "poison",
    )
    if nid in SPIRIT_SPARRING_ROOMS and (
        action_intent == "spirit_spar_drill"
        or (
            any(tok in lbl for tok in ("spar", "drill", "practice", "form", "katana", "bokken", "silat", "stance", "brawl", "pack"))
            and not any(re.search(rf"\b{v}\b", lbl) for v in _hostile_spar_verbs)
        )
    ):
        return ""
    if nid in (
        "loc_kitsune_torii_approach", "loc_et_fox_torii_tunnel",
        "loc_bunian_mist_glade", "loc_bunian_threshold_glade",
        "loc_uc_ossuary_catacombs", "sub_uc_black_font",
    ):
        return ""
    vk = infer_spirit_village_for_node(nid, nodes_by_id=nodes_by_id)
    if vk in SPIRIT_VILLAGE_KEYS:
        return vk
    return ""


def is_node_in_crossroads_truce(
    node_id: Optional[str],
    *,
    nodes_by_id: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> bool:
    """Returns True if `node_id` lies inside Neutral Truce `zone_spirit_crossroads`."""
    nid = str(node_id or "").strip()
    if not nid:
        return False
    if nid == SPIRIT_CROSSROADS_ZONE_ID or nid.startswith(("loc_crossroads_", "sub_crossroads_")):
        return True
    if nodes_by_id and nid in nodes_by_id:
        p = str((nodes_by_id[nid] or {}).get("parent_id") or "")
        if p == SPIRIT_CROSSROADS_ZONE_ID or p.startswith("loc_crossroads_"):
            return True
    return False


def reveal_spirit_zone(
    session_id: int,
    zone_id: str,
    *,
    turn_number: Optional[int] = None,
    include_guest_cottage: bool = False,
    conn: Any = None,
) -> Dict[str, Any]:
    """
    Reveals a hidden Spirit Realm zone (`is_hidden=False, discovered=True`) and all of
    its public facilities & rooms, keeping Guest-Cottages hidden unless granted (`>= 70`).
    """
    if not session_id or not zone_id:
        return {"zone_id": zone_id, "revealed_nodes": 0}
    with _uow_ctx(conn) as c:
        eff_turn = _resolve_turn_num(c, session_id, turn_number)
        rows = c.execute(
            "SELECT node_id, parent_id, node_type, state_json FROM world_nodes WHERE session_id = ?",
            (int(session_id),),
        ).fetchall()
        by_id = {str(r["node_id"]): dict(r) for r in rows if r["node_id"]}
        if zone_id not in by_id:
            return {"zone_id": zone_id, "revealed_nodes": 0}

        owned_guest_facs = {
            str(r["facility_node_id"])
            for r in c.execute(
                "SELECT facility_node_id FROM player_properties WHERE session_id = ? AND is_starter = 0",
                (int(session_id),),
            ).fetchall()
        }

        target_ids: List[str] = [zone_id]
        fac_ids: List[str] = []
        for nid, node in by_id.items():
            if node.get("parent_id") == zone_id and str(node.get("node_type") or "").upper() == "FACILITY":
                if nid in ALL_SPIRIT_GUEST_FACILITY_IDS and not include_guest_cottage and nid not in owned_guest_facs:
                    continue
                fac_ids.append(nid)
                target_ids.append(nid)
        fac_set = set(fac_ids)
        for nid, node in by_id.items():
            if node.get("parent_id") in fac_set and str(node.get("node_type") or "").upper() == "ROOM":
                target_ids.append(nid)

        revealed = 0
        all_public = (
            SPIRIT_VILLAGE_PUBLIC_FACILITIES.get("kitsune", ())
            + SPIRIT_VILLAGE_PUBLIC_FACILITIES.get("bunian", ())
            + SPIRIT_VILLAGE_PUBLIC_FACILITIES.get("ghoul", ())
        )
        for nid in target_ids:
            st = _parse_json_dict(by_id[nid].get("state_json"))
            was_hidden = bool(st.get("is_hidden")) or not bool(st.get("discovered", True))
            if "started_hidden" not in st and bool(st.get("is_hidden")):
                st["started_hidden"] = True
            st["is_hidden"] = False
            st["discovered"] = True
            if not int(st.get("discovered_turn") or 0):
                st["discovered_turn"] = eff_turn
            if nid in all_public and not st.get("veil_atonement_required"):
                st["veil_attuned"] = True
                st["unlocked_permanent"] = True
                if not int(st.get("unlocked_turn") or 0):
                    st["unlocked_turn"] = eff_turn
            if was_hidden:
                revealed += 1
            c.execute(
                "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
                (json.dumps(st), int(session_id), nid),
            )
        return {"zone_id": zone_id, "revealed_nodes": revealed, "turn_number": eff_turn}


def _reveal_crossroads_and_frontiers_tx(
    session_id: int,
    eff_turn: int,
    c: Any,
) -> None:
    """Reveals Dusk Confluence AND all 4 Frontier wilderness zones upon first entry into the Spirit Realm."""
    for z_id in (SPIRIT_CROSSROADS_ZONE_ID, *SPIRIT_FRONTIER_ZONE_IDS):
        reveal_spirit_zone(int(session_id), z_id, turn_number=eff_turn, conn=c)


def reveal_portal_pair(
    session_id: int,
    node_a: str,
    node_b: str,
    *,
    unlock_edge: bool = False,
    turn_number: Optional[int] = None,
    conn: Any = None,
) -> bool:
    """Unhides the bidirectional portal metadata between `node_a` and `node_b`."""
    if not session_id or not node_a or not node_b:
        return False
    with _uow_ctx(conn) as c:
        eff_turn = _resolve_turn_num(c, session_id, turn_number)
        changed = False
        for src, dst in ((node_a, node_b), (node_b, node_a)):
            row = c.execute(
                "SELECT state_json FROM world_nodes WHERE session_id = ? AND node_id = ?",
                (int(session_id), src),
            ).fetchone()
            if not row:
                continue
            st = _parse_json_dict(row["state_json"])
            portals = dict(st.get("portals") or {}) if isinstance(st.get("portals"), dict) else {}
            entry = dict(portals.get(dst) or {})
            if entry:
                if "started_hidden_portal" not in entry and entry.get("is_hidden_portal"):
                    entry["started_hidden_portal"] = True
                entry["is_hidden_portal"] = False
                if not int(entry.get("portal_revealed_turn") or 0):
                    entry["portal_revealed_turn"] = eff_turn
                if unlock_edge:
                    entry["is_locked"] = False
                portals[dst] = entry
                st["portals"] = portals
                c.execute(
                    "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
                    (json.dumps(st), int(session_id), src),
                )
                changed = True
        if unlock_edge:
            c.execute(
                """UPDATE world_edges
                   SET is_locked = 0
                   WHERE session_id = ?
                     AND ((from_node_id = ? AND to_node_id = ?) OR (from_node_id = ? AND to_node_id = ?))""",
                (int(session_id), node_a, node_b, node_b, node_a),
            )
        return changed


def on_enter_village_from_human_threshold(
    session_id: int,
    village_key: str,
    *,
    turn_number: Optional[int] = None,
    conn: Any = None,
) -> Dict[str, Any]:
    """
    Entering Village A via its Human threshold reveals `realm_veiled_spirit_world`,
    Village A's 5 public facilities, `zone_spirit_crossroads`, all 4 Frontier zones
    (`zone_spirit_wilds`, `zone_spirit_peaks`, `zone_spirit_mire`, `zone_spirit_boneyard`),
    Village A's Human portal, and lazy-registers Village A's `spirit_court` faction without
    spoiling the other 2 hidden villages or Chinatown's shortcut.
    """
    if not session_id or village_key not in SPIRIT_VILLAGE_KEYS:
        return {}
    from .folklore_spirit_naming import ensure_session_spirit_procedural_names
    from .realms import discover_realm

    human_thresh = _HUMAN_THRESHOLD_BY_VILLAGE[village_key]
    spirit_plaza = _PLAZA_BY_VILLAGE[village_key]
    zone_id = SPIRIT_ZONE_BY_VILLAGE[village_key]

    with _uow_ctx(conn) as c:
        eff_turn = _resolve_turn_num(c, session_id, turn_number)
        ensure_session_spirit_procedural_names(int(session_id), persist_db=True, conn=c, sync_world_nodes=True)
        discover_realm(int(session_id), SPIRIT_REALM_ID, turn_number=eff_turn, conn=c)
        reveal_spirit_zone(int(session_id), zone_id, turn_number=eff_turn, conn=c)
        _reveal_crossroads_and_frontiers_tx(int(session_id), eff_turn, c)
        reveal_portal_pair(int(session_id), human_thresh, spirit_plaza, unlock_edge=True, turn_number=eff_turn, conn=c)
        c.execute(
            "UPDATE world_nodes SET is_transit_hub = 1 WHERE session_id = ? AND node_id = ?",
            (int(session_id), spirit_plaza),
        )
        court_fac = ensure_spirit_court_faction_discovered(int(session_id), village_key, turn_number=eff_turn, conn=c)
        cottage = maybe_grant_spirit_guest_cottage(int(session_id), village_key, turn_number=eff_turn, conn=c)
        _mutate_spirit_realm_state(
            c,
            session_id,
            lambda srs: srs.setdefault("villages_entered", {}).setdefault(village_key, eff_turn),
        )
        return {
            "realm_id": SPIRIT_REALM_ID,
            "zone_id": zone_id,
            "portal_revealed": (human_thresh, spirit_plaza),
            "spirit_court": court_fac,
            "guest_cottage": cottage,
        }


def on_visit_spirit_crossroads(
    session_id: int,
    *,
    turn_number: Optional[int] = None,
    conn: Any = None,
) -> Dict[str, Any]:
    """
    Reaching `zone_spirit_crossroads` reveals Dusk Confluence AND all 4 Frontier zones
    while leaving unvisited enclaves hidden until overland travel or Human threshold entry.
    """
    if not session_id:
        return {}
    from .folklore_spirit_naming import ensure_session_spirit_procedural_names
    from .realms import discover_realm

    with _uow_ctx(conn) as c:
        eff_turn = _resolve_turn_num(c, session_id, turn_number)
        ensure_session_spirit_procedural_names(int(session_id), persist_db=True, conn=c, sync_world_nodes=True)
        discover_realm(int(session_id), SPIRIT_REALM_ID, turn_number=eff_turn, conn=c)
        _reveal_crossroads_and_frontiers_tx(int(session_id), eff_turn, c)
        _mutate_spirit_realm_state(
            c,
            session_id,
            lambda srs: srs.setdefault("crossroads_visited_turn", eff_turn),
        )
        return {
            "crossroads_zone_id": SPIRIT_CROSSROADS_ZONE_ID,
            "wilds_zone_id": SPIRIT_WILDS_ZONE_ID,
            "frontier_zone_ids": list(SPIRIT_FRONTIER_ZONE_IDS),
            "turn_number": eff_turn,
        }


def on_enter_village_overland_from_spirit_realm(
    session_id: int,
    village_key: str,
    *,
    turn_number: Optional[int] = None,
    conn: Any = None,
) -> Dict[str, Any]:
    """
    Overland Bypass: Entering a Spirit Village from inside `realm_veiled_spirit_world`
    bypasses its human-world Token/PER gate, reveals its 5 public facilities on the Spirit Atlas,
    and lazy-registers its Spirit Court faction (without revealing its Human-side portal yet).
    """
    if not session_id or village_key not in SPIRIT_VILLAGE_KEYS:
        return {}
    zone_id = SPIRIT_ZONE_BY_VILLAGE[village_key]
    plaza_id = _PLAZA_BY_VILLAGE[village_key]
    with _uow_ctx(conn) as c:
        eff_turn = _resolve_turn_num(c, session_id, turn_number)
        reveal_spirit_zone(int(session_id), zone_id, turn_number=eff_turn, conn=c)
        c.execute(
            "UPDATE world_nodes SET is_transit_hub = 1 WHERE session_id = ? AND node_id = ?",
            (int(session_id), plaza_id),
        )
        court_fac = ensure_spirit_court_faction_discovered(int(session_id), village_key, turn_number=eff_turn, conn=c)
        cottage = maybe_grant_spirit_guest_cottage(int(session_id), village_key, turn_number=eff_turn, conn=c)
        _mutate_spirit_realm_state(
            c,
            session_id,
            lambda srs: srs.setdefault("overland_discovered", {}).setdefault(village_key, eff_turn),
        )
        return {
            "village_key": village_key,
            "zone_id": zone_id,
            "spirit_court": court_fac,
            "guest_cottage": cottage,
            "turn_number": eff_turn,
        }


def on_exit_village_to_human_threshold(
    session_id: int,
    village_key: str,
    *,
    turn_number: Optional[int] = None,
    conn: Any = None,
) -> Dict[str, Any]:
    """
    Back-Door Attunement: Stepping outward from a Spirit Village to its Human Threshold
    permanently attunes and reveals that village's Human-side portal.
    """
    if not session_id or village_key not in SPIRIT_VILLAGE_KEYS:
        return {}
    human_thresh = _HUMAN_THRESHOLD_BY_VILLAGE[village_key]
    spirit_plaza = _PLAZA_BY_VILLAGE[village_key]
    fac_id = _VILLAGE_HQ_BY_KEY[village_key]
    with _uow_ctx(conn) as c:
        eff_turn = _resolve_turn_num(c, session_id, turn_number)
        row = c.execute(
            "SELECT state_json FROM world_nodes WHERE session_id = ? AND node_id = ?",
            (int(session_id), fac_id),
        ).fetchone()
        fac_st = _parse_json_dict(row["state_json"] if row else "{}")
        if fac_st.get("veil_atonement_required"):
            return {"attuned": False, "reason": "veil_atonement_required"}
        revealed = reveal_portal_pair(int(session_id), human_thresh, spirit_plaza, unlock_edge=True, turn_number=eff_turn, conn=c)
        if not fac_st.get("veil_attuned"):
            fac_st["veil_attuned"] = True
            fac_st["unlocked_permanent"] = True
            if not int(fac_st.get("unlocked_turn") or 0):
                fac_st["unlocked_turn"] = eff_turn
            c.execute(
                "UPDATE world_nodes SET state_json = ? WHERE session_id = ? AND node_id = ?",
                (json.dumps(fac_st), int(session_id), fac_id),
            )
        _mutate_spirit_realm_state(
            c,
            session_id,
            lambda srs: srs.setdefault("backdoor_attuned", {}).setdefault(village_key, eff_turn),
        )
        return {
            "attuned": True,
            "portal_revealed": revealed,
            "village_key": village_key,
            "human_threshold": human_thresh,
            "turn_number": eff_turn,
        }


def is_chinatown_shortcut_unlocked(session_id: int, conn: Any = None) -> bool:
    if not session_id:
        return False
    ctx = _uow_ctx(conn) if conn is not None else db.get_conn()
    with ctx as c:
        row = c.execute(
            """SELECT is_locked FROM world_edges
               WHERE session_id = ?
                 AND ((from_node_id = ? AND to_node_id = ?) OR (from_node_id = ? AND to_node_id = ?))
               LIMIT 1""",
            (
                int(session_id),
                CHINATOWN_SHORTCUT_SPIRIT_NODE,
                CHINATOWN_SHORTCUT_HUMAN_NODE,
                CHINATOWN_SHORTCUT_HUMAN_NODE,
                CHINATOWN_SHORTCUT_SPIRIT_NODE,
            ),
        ).fetchone()
        return row is not None and int(row["is_locked"] or 0) == 0


def can_unseal_chinatown_shortcut(
    session_id: int,
    *,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Inspects which Spirit-side Chinatown unsealing paths (50g or waived by Drifting Lanterns, PER 12, Rep >= 25) are currently satisfied."""
    if not session_id:
        return {"unlocked": False, "can_gold": False, "can_per": False, "can_rep": False, "lantern_waiver_active": False}
    from mechanics.world.world_events.spirit_realm_events import is_ferryman_toll_waived

    sess = db.get_session(int(session_id)) or {}
    eff_uid = int(user_id or sess.get("host_user_id") or 0)
    char = db.get_character(eff_uid, session_id=int(session_id)) if eff_uid else None
    gold = int((char or {}).get("gold") or 0)
    waived = is_ferryman_toll_waived(int(session_id))
    req_gold = 0 if waived else CHINATOWN_OFFERING_GOLD
    max_court_rep = max(
        get_effective_village_standing(int(session_id), "kitsune", court_only=True),
        get_effective_village_standing(int(session_id), "bunian", court_only=True),
        get_effective_village_standing(int(session_id), "ghoul", court_only=True),
    )
    return {
        "unlocked": is_chinatown_shortcut_unlocked(int(session_id)),
        "gold": gold,
        "required_gold": req_gold,
        "can_gold": True if waived else (gold >= req_gold),
        "lantern_waiver_active": waived,
        "per_dc": 12,
        "max_court_rep": max_court_rep,
        "can_rep": max_court_rep >= 25,
    }


def unseal_chinatown_shortcut(
    session_id: int,
    *,
    method: str = "gold",
    user_id: Optional[int] = None,
    per_roll: Optional[int] = None,
    turn_number: Optional[int] = None,
    from_node_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Unseals the Chinatown shortcut from `sub_crossroads_mist_wharf`:
    - Rejects attempts from Chinatown (`sub_ct_curio_stalls`) while sealed (`spirit_side_unlock_only`).
    - Supports `method`: `'gold'` (50g Ferryman offering, waived during Tide of Drifting Lanterns), `'per'` (`PER >= 12`), or `'reputation'` (Court Rep >= 25).
    """
    if not session_id:
        return {"ok": False, "reason": "invalid_session"}
    if is_chinatown_shortcut_unlocked(int(session_id)):
        return {"ok": True, "already_unlocked": True}
    if from_node_id == CHINATOWN_SHORTCUT_HUMAN_NODE:
        return {"ok": False, "reason": "spirit_side_unlock_only"}

    from mechanics.world.world_events.spirit_realm_events import is_ferryman_toll_waived

    clean_method = str(method or "gold").strip().lower()
    with db.UnitOfWork() as conn:
        srs_cur = get_spirit_realm_state(int(session_id), conn=conn)
        if is_chinatown_shortcut_unlocked(int(session_id), conn=conn) or bool(srs_cur.get("chinatown_shortcut_unlocked_turn")):
            return {"ok": True, "already_unlocked": True}
        waived = is_ferryman_toll_waived(int(session_id))
        eff_turn = _resolve_turn_num(conn, session_id, turn_number)
        s_row = conn.execute("SELECT host_user_id, character_id FROM sessions WHERE id = ?", (int(session_id),)).fetchone()
        eff_uid = int(user_id or (s_row["host_user_id"] if s_row else 0) or 0)
        gold_paid = 0
        buyer_cid = 0

        if clean_method == "gold":
            if not waived:
                char_row = None
                if eff_uid:
                    char_row = conn.execute(
                        "SELECT id, gold FROM characters WHERE user_id = ? ORDER BY active_session_id = ? DESC, is_active DESC, id DESC LIMIT 1",
                        (eff_uid, int(session_id)),
                    ).fetchone()
                elif s_row and s_row["character_id"]:
                    char_row = conn.execute("SELECT id, gold FROM characters WHERE id = ?", (int(s_row["character_id"]),)).fetchone()
                cur_gold = int(char_row["gold"] or 0) if char_row else 0
                if not char_row or cur_gold < CHINATOWN_OFFERING_GOLD:
                    return {"ok": False, "reason": "insufficient_gold", "gold": cur_gold, "required": CHINATOWN_OFFERING_GOLD}
                gold_paid = CHINATOWN_OFFERING_GOLD
                buyer_cid = int(char_row["id"])
                conn.execute("UPDATE characters SET gold = gold - ? WHERE id = ?", (gold_paid, buyer_cid))
        elif clean_method == "per":
            eff_per = int(per_roll or 0)
            if eff_per < 12:
                return {"ok": False, "reason": "per_check_failed", "roll": eff_per, "dc": 12}
        elif clean_method in ("reputation", "rep", "standing"):
            clean_method = "reputation"
            max_r = max(_get_court_rep_sql(conn, session_id, k) for k in SPIRIT_VILLAGE_KEYS)
            if max_r < 25:
                return {"ok": False, "reason": "insufficient_reputation", "max_rep": max_r, "required": 25}
        else:
            return {"ok": False, "reason": "unknown_method"}

        reveal_portal_pair(
            int(session_id),
            CHINATOWN_SHORTCUT_SPIRIT_NODE,
            CHINATOWN_SHORTCUT_HUMAN_NODE,
            unlock_edge=True,
            turn_number=eff_turn,
            conn=conn,
        )

        def _stamp(srs: Dict[str, Any]) -> None:
            srs["chinatown_shortcut_unlocked_turn"] = eff_turn
            srs["chinatown_shortcut_method"] = clean_method
            srs["chinatown_shortcut_gold_paid"] = gold_paid
            srs["chinatown_shortcut_buyer_cid"] = buyer_cid
            if waived and clean_method == "gold":
                srs["lantern_waiver_used"] = True

        _mutate_spirit_realm_state(conn, session_id, _stamp)
        return {
            "ok": True,
            "method": clean_method,
            "gold_paid": gold_paid,
            "lantern_waiver_used": bool(waived and clean_method == "gold"),
            "turn_number": eff_turn,
            "portal_pair": (CHINATOWN_SHORTCUT_SPIRIT_NODE, CHINATOWN_SHORTCUT_HUMAN_NODE),
        }


def resolve_crossroads_neutral_truce_ejection(
    session_id: int,
    *,
    turn_number: Optional[int] = None,
    advance_clock: bool = True,
) -> Dict[str, Any]:
    """
    Neutral Truce enforcement in `zone_spirit_crossroads`:
    Ejects hostile brawlers +15 minutes out to `sub_wilds_ward_camp` WITHOUT triggering any village banishment.
    """
    if not session_id:
        return {"expelled": False}
    with db.UnitOfWork() as conn:
        eff_turn = _resolve_turn_num(conn, session_id, turn_number)
        reveal_spirit_zone(int(session_id), SPIRIT_WILDS_ZONE_ID, turn_number=eff_turn, conn=conn)
        dest_loc = db.format_node_tiered_location(int(session_id), WILDS_SAFE_RESCUE_NODE_ID) or (
            "The Weeping Bleedwood — Untamed Spirit Wilds ➔ Joint Ward-Stone Perimeter Camp ➔ Joint Frontier Ward-Stone Triage Camp"
        )
        c_day, c_min, c_awake = db.get_session_time(int(session_id))
        if advance_clock:
            tot = int(c_min) + 15
            new_day = int(c_day) + (tot // 1440)
            new_min = tot % 1440
            db.update_session_time(int(session_id), new_day, new_min, c_awake)
        else:
            new_day, new_min = int(c_day), int(c_min)
        db.update_session(
            int(session_id),
            current_node_id=WILDS_SAFE_RESCUE_NODE_ID,
            current_location=dest_loc,
            nearby_enemies=[],
        )
    return {
        "expelled": True,
        "neutral_truce_ejection": True,
        "village_banished": False,
        "ejected_node_id": WILDS_SAFE_RESCUE_NODE_ID,
        "ejected_location": dest_loc,
        "time_lost_minutes": 15 if advance_clock else 0,
        "new_day": new_day,
        "new_minute": new_min,
        "prompt_directive": (
            "[STAGE DIRECTION — DUSK CONFLUENCE NEUTRAL TRUCE]: Market wardens dissolve the brawl beneath golden "
            "truce-lanterns before steel settles, escorting the party 15 minutes down the mist-path to "
            "the Joint Ward-Stone Perimeter Camp without invoking any Court's banishment."
        ),
    }


def get_folklore_portal_choices(
    session_id: int,
    curr_node_id: str,
    curr_realm_id: str,
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    seen_keys: set[tuple[str, str, str]],
) -> list[dict[str, Any]]:
    """
    Registered portal-choice provider for Folklore thresholds (Kitsune, Bunian, Ghoul),
    Spirit Crossroads Chinatown shortcut unsealing rites, village exits, and overland discovery trails.
    """
    from .realms.hierarchy import parse_node_state_json

    choices: list[dict[str, Any]] = []
    if curr_node_id in (
        "loc_et_fox_torii_tunnel",
        "loc_kitsune_torii_approach",
        "loc_bunian_threshold_glade",
        "loc_bunian_mist_glade",
        "sub_uc_black_font",
    ):
        from .folklore_veil import (
            PERMISSION_TOKEN_SLUGS,
            _has_village_companion_escort,
            get_effective_veil_dc,
            get_village_veil_status,
            is_twilight_veil_thinning,
        )

        if curr_node_id == "sub_uc_black_font":
            vk = "ghoul"
        elif "torii" in curr_node_id or "kitsune" in curr_node_id:
            vk = "kitsune"
        else:
            vk = "bunian"
        target_plaza = _PLAZA_BY_VILLAGE[vk]
        if ("portal_cross", target_plaza, SPIRIT_REALM_ID) not in seen_keys:
            v_st = get_village_veil_status(session_id, vk)
            if v_st.get("atonement_required"):
                if vk == "kitsune":
                    offering_lbl = "Present Sacred Aburaage & Cedar Incense Offering (100g) to appease the sanctuary guardians"
                elif vk == "bunian":
                    offering_lbl = "Present Bunga Rampai & Benzoin Kemeyan Offering (100g) to appease the sanctuary guardians"
                else:
                    offering_lbl = "Present Sealed Myrrh & Silver Ossuary Offering (100g) to appease the Blood-Truce guardians"
                choices.append({
                    "label": offering_lbl,
                    "stat": "NONE",
                    "requirement": 0,
                    "mp_cost": 0,
                    "intent": "movement",
                    "sub_intent": "portal_cross",
                    "target_node_id": target_plaza,
                    "target_realm_id": SPIRIT_REALM_ID,
                    "veil_village_key": vk,
                    "is_phase2_choice": True,
                    "_priority_slot": True,
                })
            elif not v_st.get("attuned"):
                sess = db.get_session(session_id) or {}
                eff_min = int(sess.get("current_minute") or 480)
                eff_dc = get_effective_veil_dc(session_id, vk, eff_min)
                twilight_hint = " (Twilight Veil Thinning)" if is_twilight_veil_thinning(eff_min) else ""
                chars = db.get_session_characters(session_id) or []
                inv_map = db.get_inventories_for_characters(chars) if chars else {}
                inv_str = " ".join(
                    str(it.get("name") or "").lower()
                    for items in inv_map.values()
                    for it in items
                )
                has_tok = PERMISSION_TOKEN_SLUGS.get(vk, "") in inv_str
                escort_name = _has_village_companion_escort(session_id, vk)
                if escort_name:
                    choices.append({
                        "label": f"⛩️ Walk through the parting spirit veil under {escort_name}'s escort",
                        "stat": "NONE",
                        "requirement": 0,
                        "mp_cost": 0,
                        "intent": "movement",
                        "sub_intent": "portal_cross",
                        "target_node_id": target_plaza,
                        "target_realm_id": SPIRIT_REALM_ID,
                        "veil_village_key": vk,
                        "is_phase2_choice": True,
                        "_priority_slot": True,
                    })
                if has_tok:
                    if vk == "kitsune":
                        tok_lbl = "⛩️ Chime the Fox-Fire Brass Suzu Bell beneath the vermilion torii"
                    elif vk == "bunian":
                        tok_lbl = "⛩️ Sound the Cempaka Brass Serunai beneath the banyan mist"
                    else:
                        tok_lbl = "🕯️ Press the Bone-Etched Catacomb Signet over the black ossuary font"
                    choices.append({
                        "label": tok_lbl,
                        "stat": "NONE",
                        "requirement": 0,
                        "mp_cost": 0,
                        "intent": "movement",
                        "sub_intent": "portal_cross",
                        "target_node_id": target_plaza,
                        "target_realm_id": SPIRIT_REALM_ID,
                        "veil_village_key": vk,
                        "is_phase2_choice": True,
                        "_priority_slot": True,
                    })
                if vk == "kitsune":
                    per_lbl = f"[PER] Study the shimmering amber haze between the vermilion torii{twilight_hint}"
                elif vk == "bunian":
                    per_lbl = f"[PER] Trace the strange silver mist wreathing the cempaka glade{twilight_hint}"
                else:
                    per_lbl = f"[PER] Read the cold still-water reflection rippling over the black ossuary font{twilight_hint}"
                choices.append({
                    "label": per_lbl,
                    "stat": "PER",
                    "requirement": eff_dc,
                    "mp_cost": 0,
                    "intent": "movement",
                    "sub_intent": "portal_cross",
                    "target_node_id": target_plaza,
                    "target_realm_id": SPIRIT_REALM_ID,
                    "veil_village_key": vk,
                    "is_phase2_choice": True,
                    "_priority_slot": True,
                })

    if curr_realm_id == SPIRIT_REALM_ID:
        if curr_node_id in (CHINATOWN_SHORTCUT_SPIRIT_NODE, "loc_crossroads_boundary_wharf"):
            ct_info = can_unseal_chinatown_shortcut(session_id)
            if not ct_info.get("unlocked"):
                if ct_info.get("can_gold"):
                    choices.append({
                        "label": "🏮 Offer 50g into the Ferryman's Brazier to unseal the Chinatown Curio Shortcut",
                        "stat": "NONE",
                        "requirement": 0,
                        "mp_cost": 0,
                        "intent": "movement",
                        "sub_intent": "unseal_chinatown_shortcut",
                        "unseal_method": "gold",
                        "target_node_id": CHINATOWN_SHORTCUT_SPIRIT_NODE,
                        "is_phase2_choice": True,
                    })
                if ct_info.get("can_rep"):
                    choices.append({
                        "label": "🏮 Invoke Spirit Court Favor (Rep >= 25) to unseal the Chinatown Curio Shortcut",
                        "stat": "NONE",
                        "requirement": 0,
                        "mp_cost": 0,
                        "intent": "movement",
                        "sub_intent": "unseal_chinatown_shortcut",
                        "unseal_method": "reputation",
                        "target_node_id": CHINATOWN_SHORTCUT_SPIRIT_NODE,
                        "is_phase2_choice": True,
                    })
                choices.append({
                    "label": "[PER] Part the Chinatown canal fog-shroud with keen Spirit Sight",
                    "stat": "PER",
                    "requirement": 12,
                    "mp_cost": 0,
                    "intent": "movement",
                    "sub_intent": "unseal_chinatown_shortcut",
                    "unseal_method": "per",
                    "target_node_id": CHINATOWN_SHORTCUT_SPIRIT_NODE,
                    "is_phase2_choice": True,
                })
        elif curr_node_id in ("sub_kitsune_inner_plaza", "sub_bunian_inner_plaza", "sub_ghoul_inner_plaza"):
            if curr_node_id == "sub_kitsune_inner_plaza":
                vk_exit = "kitsune"
                exit_lbl = "⛩️ Step out through the Torii Threshold to Mount Ryujin"
            elif curr_node_id == "sub_bunian_inner_plaza":
                vk_exit = "bunian"
                exit_lbl = "⛩️ Step out through the Banyan Mist Glade to the Reserve"
            else:
                vk_exit = "ghoul"
                exit_lbl = "🕯️ Surface through the Sunken Black Font into Undercity Catacombs"
            thresh_target = _HUMAN_THRESHOLD_BY_VILLAGE[vk_exit]
            if ("portal_cross", thresh_target, "realm_city_metro") not in seen_keys:
                choices.append({
                    "label": exit_lbl,
                    "stat": "NONE",
                    "requirement": 0,
                    "mp_cost": 0,
                    "intent": "movement",
                    "sub_intent": "portal_cross",
                    "target_node_id": thresh_target,
                    "target_realm_id": "realm_city_metro",
                    "veil_village_key": vk_exit,
                    "is_phase2_choice": True,
                })
        if curr_node_id == SPIRIT_CROSSROADS_ZONE_ID or curr_node_id.startswith(("loc_crossroads_", "sub_crossroads_")):
            for vk_trail, z_trail in SPIRIT_ZONE_BY_VILLAGE.items():
                z_node = nodes_by_id.get(z_trail) or db.get_world_node(session_id, z_trail) or {}
                z_st = parse_node_state_json(z_node)
                plaza_trail = _PLAZA_BY_VILLAGE[vk_trail]
                if z_st.get("is_hidden") or not z_st.get("discovered", True):
                    if vk_trail == "kitsune":
                        trail_lbl = "⛩️ Follow the lantern-strung Fox-Torii ridge trail into Sato-no-Inari (~10m)"
                    elif vk_trail == "bunian":
                        trail_lbl = "⛩️ Follow the mist-draped Cempaka river trail to Kampung Kayangan (~10m)"
                    else:
                        trail_lbl = "🕯️ Follow the weeping-cypress ash trail toward The Pale Ossuary (~10m)"
                    choices.append({
                        "label": trail_lbl,
                        "stat": "NONE",
                        "requirement": 0,
                        "mp_cost": 0,
                        "intent": "movement",
                        "sub_intent": "overland_spirit_trail",
                        "target_node_id": plaza_trail,
                        "veil_village_key": vk_trail,
                        "is_phase2_choice": True,
                    })

    return choices


from .folklore_spirit_realm_lifecycle import (  # noqa: E402
    backfill_folklore_spirit_realm_v52,
    backfill_folklore_spirit_realm_v64,
    rollback_spirit_realm_state_after_turn,
)

__all__ = [
    "SPIRIT_REALM_ID",
    "SPIRIT_ZONE_BY_VILLAGE",
    "SPIRIT_VILLAGE_BY_ZONE",
    "SPIRIT_VILLAGE_KEYS",
    "SPIRIT_CROSSROADS_ZONE_ID",
    "SPIRIT_WILDS_ZONE_ID",
    "SPIRIT_PEAKS_ZONE_ID",
    "SPIRIT_MIRE_ZONE_ID",
    "SPIRIT_BONEYARD_ZONE_ID",
    "SPIRIT_FRONTIER_ZONE_IDS",
    "SPIRIT_VILLAGE_PUBLIC_FACILITIES",
    "SPIRIT_GUEST_COTTAGE_SPEC",
    "SPIRIT_COURT_FACTIONS",
    "SPIRIT_SPARRING_ROOMS",
    "WILDS_SAFE_RESCUE_NODE_ID",
    "CROSSROADS_TEA_FALLBACK_NODE_ID",
    "CHINATOWN_SHORTCUT_SPIRIT_NODE",
    "CHINATOWN_SHORTCUT_HUMAN_NODE",
    "CHINATOWN_OFFERING_GOLD",
    "ALL_SPIRIT_GUEST_FACILITY_IDS",
    "ALL_SPIRIT_GUEST_PROPERTY_IDS",
    "get_spirit_realm_state",
    "is_node_in_spirit_realm",
    "infer_spirit_village_for_node",
    "is_node_in_sanctuary_pact_zone",
    "is_node_in_crossroads_truce",
    "reveal_spirit_zone",
    "reveal_portal_pair",
    "on_enter_village_from_human_threshold",
    "on_visit_spirit_crossroads",
    "on_enter_village_overland_from_spirit_realm",
    "on_exit_village_to_human_threshold",
    "is_chinatown_shortcut_unlocked",
    "can_unseal_chinatown_shortcut",
    "unseal_chinatown_shortcut",
    "compute_spirit_court_starting_rep",
    "ensure_spirit_court_faction_discovered",
    "build_spirit_court_leadership_roster",
    "build_spirit_court_diplomacy",
    "sync_spirit_court_leadership_and_diplomacy",
    "adjust_spirit_court_reputation",
    "is_ghoul_council_distrusted",
    "get_effective_village_standing",
    "get_spirit_court_discount_multiplier",
    "maybe_grant_spirit_guest_cottage",
    "resolve_spirit_sparring_drill",
    "resolve_crossroads_neutral_truce_ejection",
    "get_folklore_portal_choices",
    "backfill_folklore_spirit_realm_v52",
    "backfill_folklore_spirit_realm_v64",
    "rollback_spirit_realm_state_after_turn",
]
