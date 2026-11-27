"""
mechanics/world/locations/folklore_veil.py
==========================================
Deterministic veil attunement, permission token checks, twilight perception gates,
2-minute Leyline Spirit Passage unlocking, and Sanctuary Non-Aggression Treaty
enforcement for the Hidden Kitsune Village and Hidden Orang Bunian Village.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import db
import scenario_data

log = logging.getLogger("hikayat.world.folklore_veil")

_CATALOG_CACHE: Optional[Dict[str, Any]] = None

FOLKLORE_VILLAGE_FACILITY_IDS: Tuple[str, str, str] = (
    "loc_hidden_kitsune_village",
    "loc_hidden_bunian_village",
    "loc_hidden_ghoul_village",
)

OUTER_THRESHOLD_NODE_IDS: Dict[str, str] = {
    "kitsune": "loc_et_fox_torii_tunnel",
    "bunian": "loc_bunian_threshold_glade",
    "ghoul": "sub_uc_black_font",
}

INNER_PLAZA_NODE_IDS: Dict[str, str] = {
    "kitsune": "sub_kitsune_inner_plaza",
    "bunian": "sub_bunian_inner_plaza",
    "ghoul": "sub_ghoul_inner_plaza",
}

ROYAL_PAVILION_NODE_IDS: Dict[str, str] = {
    "kitsune": "sub_kitsune_sovereign_pavilion",
    "bunian": "sub_bunian_royal_istana",
    "ghoul": "sub_ghoul_sovereign_manor",
}

VEILED_INNER_ROOM_IDS: Dict[str, Tuple[str, ...]] = {
    "kitsune": (
        "sub_kitsune_inner_plaza",
        "sub_kitsune_sovereign_pavilion",
        "sub_kitsune_spirit_apothecary",
        "sub_kitsune_leyline_shrine",
    ),
    "bunian": (
        "sub_bunian_inner_plaza",
        "sub_bunian_royal_istana",
        "sub_bunian_pusaka_hall",
        "sub_bunian_orchid_spring",
    ),
    "ghoul": (
        "sub_ghoul_inner_plaza",
        "sub_ghoul_sovereign_manor",
        "sub_ghoul_curio_morgue",
        "sub_ghoul_leyline_crypt",
    ),
}

PERMISSION_TOKEN_SLUGS: Dict[str, str] = {
    "kitsune": "fox-fire brass suzu bell",
    "bunian": "cempaka brass serunai",
    "ghoul": "bone-etched catacomb signet",
}


def load_folklore_villages_catalog() -> Dict[str, Any]:
    """Loads and caches data/folklore_villages_catalog.json."""
    global _CATALOG_CACHE
    if _CATALOG_CACHE is not None:
        return _CATALOG_CACHE
    catalog_path = Path(__file__).resolve().parents[3] / "data" / "folklore_villages_catalog.json"
    try:
        _CATALOG_CACHE = json.loads(catalog_path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Failed loading folklore_villages_catalog.json: %s", exc)
        _CATALOG_CACHE = {}
    return _CATALOG_CACHE


def is_folklore_permission_token_name(item_name: str) -> bool:
    """Returns True if item_name matches either veiled-village Permission Token."""
    clean = str(item_name or "").strip().lower()
    if not clean:
        return False
    return any(slug in clean for slug in PERMISSION_TOKEN_SLUGS.values())


def is_twilight_veil_thinning(current_minute: int) -> bool:
    """Returns True during dawn (05:00–06:30) or dusk (17:00–19:00) twilight windows."""
    safe_min = int(current_minute or 0) % 1440
    return (300 <= safe_min <= 390) or (1020 <= safe_min <= 1140)


def get_effective_veil_dc(session_id: int, village_key: str, current_minute: int) -> int:
    """Computes effective PER requirement (14 standard, 12 during twilight or active village festival)."""
    catalog = load_folklore_villages_catalog()
    v_meta = (catalog.get("villages") or {}).get(village_key) or {}
    base_dc = int(v_meta.get("veil_dc") or 14)
    twilight_dc = int(v_meta.get("twilight_veil_dc") or 12)
    if is_twilight_veil_thinning(current_minute):
        return twilight_dc
    if session_id:
        try:
            events = db.get_world_events(session_id) or []
            fest_id = "evt_kitsune_hundred_foxfires" if village_key == "kitsune" else "evt_bunian_malam_cempaka"
            for ev in events:
                ev_meta = ev.get("metadata") if isinstance(ev.get("metadata"), dict) else {}
                ev_str = f"{ev.get('event_key') or ''} {ev.get('template_key') or ''} {ev_meta.get('template_key') or ''} {ev.get('title') or ''}".lower()
                if fest_id in ev_str or ("fox-fire" in ev_str and village_key == "kitsune") or ("cempaka" in ev_str and village_key == "bunian"):
                    return twilight_dc
        except Exception:
            pass
    return base_dc


def resolve_folklore_village_for_node(
    session_id: int,
    node_id: str,
    node: Optional[Dict[str, Any]] = None,
    fac_node: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Returns (village_key, village_catalog_meta) if node_id belongs to Kitsune or Bunian village."""
    if not node_id:
        return None, None
    from .folklore_spirit_realm import infer_spirit_village_for_node

    nid = str(node_id).strip()
    catalog = load_folklore_villages_catalog()
    villages = catalog.get("villages") or {}

    vk_fast = infer_spirit_village_for_node(nid)
    if vk_fast in villages:
        return vk_fast, villages.get(vk_fast) or {}

    for candidate in (node, fac_node):
        if isinstance(candidate, dict):
            cid = str(candidate.get("node_id") or "")
            pid = str(candidate.get("parent_id") or "")
            vk_cand = infer_spirit_village_for_node(cid) or infer_spirit_village_for_node(pid)
            if vk_cand in villages:
                return vk_cand, villages.get(vk_cand) or {}
            raw_st = candidate.get("state_json")
            if raw_st:
                try:
                    parsed = json.loads(raw_st) if isinstance(raw_st, str) else raw_st
                    vk = parsed.get("veil_village_key") if isinstance(parsed, dict) else None
                    if vk in villages:
                        return str(vk), villages.get(vk) or {}
                except Exception:
                    pass

    if session_id:
        if db.is_descendant_of(session_id, nid, "zone_spirit_kitsune") or db.is_descendant_of(session_id, nid, "loc_hidden_kitsune_village"):
            return "kitsune", villages.get("kitsune") or {}
        if db.is_descendant_of(session_id, nid, "zone_spirit_bunian") or db.is_descendant_of(session_id, nid, "loc_hidden_bunian_village"):
            return "bunian", villages.get("bunian") or {}
        if db.is_descendant_of(session_id, nid, "zone_spirit_ghoul") or db.is_descendant_of(session_id, nid, "loc_hidden_ghoul_village") or nid == "sub_uc_black_font":
            return "ghoul", villages.get("ghoul") or {}
    return None, None


def get_village_veil_status(
    session_id: int,
    village_key: str,
    session: Optional[dict] = None,
) -> Dict[str, Any]:
    """Returns normalized attunement & treaty status for 'kitsune', 'bunian', or 'ghoul'."""
    catalog = load_folklore_villages_catalog()
    v_meta = (catalog.get("villages") or {}).get(village_key) or {}
    fac_id = str(v_meta.get("village_id") or (
        "loc_hidden_kitsune_village"
        if village_key == "kitsune"
        else ("loc_hidden_bunian_village" if village_key == "bunian" else "loc_hidden_ghoul_village")
    ))
    plaza_id = INNER_PLAZA_NODE_IDS.get(village_key, "")
    fac_state = db.get_world_node_state(session_id, fac_id) if session_id else {}
    plaza_state = db.get_world_node_state(session_id, plaza_id) if (session_id and plaza_id) else {}
    staged_attuned = bool(
        isinstance(session, dict)
        and village_key in (session.get("_staged_attuned_villages") or [])
    )
    atonement_req = False if staged_attuned else bool(
        fac_state.get("veil_atonement_required") or plaza_state.get("veil_atonement_required")
    )
    attuned = bool(
        staged_attuned
        or (
            not atonement_req
            and (
                fac_state.get("veil_attuned")
                or fac_state.get("unlocked_permanent")
                or plaza_state.get("unlocked_permanent")
                or (plaza_state.get("discovered") is True and not plaza_state.get("is_hidden", True))
            )
        )
    )
    return {
        "village_key": village_key,
        "facility_id": fac_id,
        "attuned": attuned,
        "is_hidden": False if staged_attuned else bool(fac_state.get("is_hidden", not attuned)),
        "atonement_required": atonement_req,
        "unlocked_turn": int(fac_state.get("unlocked_turn") or plaza_state.get("unlocked_turn") or 0),
        "expelled_turn": int(fac_state.get("expelled_turn") or 0),
    }


def _collect_party_inventory_names(session_id: int, party: Optional[list] = None, session: Optional[dict] = None) -> str:
    """Collects lowercase item names from passed party objects and active session member DB inventories."""
    names: List[str] = []
    seen_uids: set[int] = set()
    for member in (party or []):
        c_obj = member[0] if isinstance(member, (tuple, list)) else member
        if isinstance(c_obj, dict):
            uid = int(c_obj.get("user_id") or 0)
            if uid:
                seen_uids.add(uid)
            for it in (c_obj.get("inventory") or []):
                nm = str(it.get("name") if isinstance(it, dict) else it).strip().lower()
                if nm:
                    names.append(nm)
    if session_id and not names:
        try:
            chars = db.get_session_characters(session_id) or []
            inv_map = db.get_inventories_for_characters(chars)
            for items in inv_map.values():
                for it in items:
                    nm = str(it.get("name") or "").strip().lower()
                    if nm:
                        names.append(nm)
        except Exception:
            pass
    elif isinstance(session, dict) and session.get("host_user_id") and int(session["host_user_id"]) not in seen_uids:
        try:
            for it in (db.get_inventory(int(session["host_user_id"])) or []):
                nm = str(it.get("name") or "").strip().lower()
                if nm:
                    names.append(nm)
        except Exception:
            pass
    return " | ".join(names)


def _has_village_companion_escort(session_id: int, village_key: str, active_companions: Optional[list] = None) -> Optional[str]:
    """Returns the escorting villager's name if a recruited companion from village_key is accompanying the player."""
    candidates: List[Dict[str, Any]] = []
    for c in (active_companions or []):
        if isinstance(c, dict):
            candidates.append(c)
    if session_id:
        try:
            candidates.extend(db.get_session_party_npcs(session_id) or [])
            candidates.extend(db.get_temporary_companions(session_id) or [])
        except Exception:
            pass
    if not candidates:
        return None

    contacts_by_name: Dict[str, Dict[str, Any]] = {}
    if session_id:
        try:
            for ct in (db.get_contacts(session_id) or []):
                if ct.get("name"):
                    contacts_by_name[str(ct["name"]).strip().lower()] = ct
        except Exception:
            pass

    for comp in candidates:
        c_name = str(comp.get("name") or "").strip()
        ct_row = contacts_by_name.get(c_name.lower(), {})
        ct_bi = ct_row.get("basic_info") if isinstance(ct_row.get("basic_info"), dict) else {}
        race = str(comp.get("race") or ct_row.get("race") or "").lower()
        v_tag = str(comp.get("folklore_village") or ct_bi.get("folklore_village") or (ct_row.get("personality_json") or "")).lower()
        if village_key == "kitsune" and ("kitsune" in race or "kitsune" in v_tag):
            return c_name or "Kitsune Companion"
        if village_key == "bunian" and ("orang_bunian" in race or "bunian" in race or "bunian" in v_tag):
            return c_name or "Bunian Companion"
        if village_key == "ghoul" and ("ghoul" in race or "ghoul" in v_tag):
            return c_name or "Al-Ghul Companion"
    return None


def _is_royal_chamber_welcomed(session_id: int, village_key: str, active_companions: Optional[list] = None) -> bool:
    """Checks whether the player has romantic standing or deep trust (>= 70) with the village Sovereign/Royal Heir."""
    if not session_id:
        return False
    if village_key == "ghoul":
        from .folklore_spirit_courts import is_ghoul_council_distrusted
        if is_ghoul_council_distrusted(session_id):
            return False
    contacts = db.get_contacts(session_id) or []
    for ct in contacts:
        race = str(ct.get("race") or "").lower()
        bi = ct.get("basic_info") if isinstance(ct.get("basic_info"), dict) else {}
        p_raw = ct.get("personality_json") or "{}"
        p_dict = json.loads(p_raw) if isinstance(p_raw, str) and p_raw.strip().startswith("{") else (p_raw if isinstance(p_raw, dict) else {})
        role = str(ct.get("role") or bi.get("role") or p_dict.get("role") or "").lower()
        is_sovereign = bool(bi.get("is_sovereign") or p_dict.get("is_sovereign"))
        is_royal_heir = bool(bi.get("is_royal_heir") or p_dict.get("is_royal_heir"))
        is_match = False
        if village_key == "kitsune" and ("kitsune" in race or bi.get("folklore_village") == "kitsune") and (is_sovereign or "sovereign" in role):
            is_match = True
        elif village_key == "bunian" and ("bunian" in race or bi.get("folklore_village") == "bunian") and (
            is_sovereign
            or is_royal_heir
            or "royal" in role
            or "puteri" in str(ct.get("name", "")).lower()
            or "putera" in str(ct.get("name", "")).lower()
        ):
            is_match = True
        elif village_key == "ghoul" and ("ghoul" in race or bi.get("folklore_village") == "ghoul") and (
            is_sovereign
            or is_royal_heir
            or "heir" in role
        ):
            is_match = True
        if is_match:
            score = int(ct.get("relationship_score") or 0)
            track = str(ct.get("track") or "").lower()
            if score >= 70 or track == "romantic":
                return True
            ct_name = str(ct.get("name") or "").strip().lower()
            for comp in (active_companions or []):
                if isinstance(comp, dict) and str(comp.get("name") or "").strip().lower() == ct_name and score >= 45:
                    return True
    return False


def attune_folklore_village(
    session_id: int,
    village_key: str,
    turn_number: Optional[int] = None,
    reason: str = "veil_attuned",
    *,
    reveal_human_portal: bool = True,
) -> Dict[str, Any]:
    """
    Permanently unmasks a veiled village for the session:
    - Marks facility and inner sub-locations discovered=True, is_hidden=False
    - Unlocks non-private village sub-locations permanently (preserving private royal chamber rules)
    - Reveals the Spirit Realm enclave via Approach A when triggered from a Human threshold
    - Enables direct World Map / Spirit-Waystation transit to the inner plaza (is_transit_hub=1)
    """
    if not session_id or village_key not in ("kitsune", "bunian", "ghoul"):
        return {}
    from .folklore_spirit_realm import (
        SPIRIT_ZONE_BY_VILLAGE,
        on_enter_village_from_human_threshold,
        on_enter_village_overland_from_spirit_realm,
    )

    eff_turn = int(turn_number if turn_number is not None else db.get_effective_session_turn(session_id))
    catalog = load_folklore_villages_catalog()
    v_meta = (catalog.get("villages") or {}).get(village_key) or {}
    fac_id = str(v_meta.get("village_id") or (
        "loc_hidden_kitsune_village"
        if village_key == "kitsune"
        else ("loc_hidden_bunian_village" if village_key == "bunian" else "loc_hidden_ghoul_village")
    ))
    fac_node = db.get_world_node(session_id, fac_id)
    in_spirit_zone = bool(fac_node and fac_node.get("parent_id") == SPIRIT_ZONE_BY_VILLAGE[village_key])
    true_name = str(
        (fac_node or {}).get("name")
        if in_spirit_zone and (fac_node or {}).get("name")
        else (v_meta.get("true_name") or fac_id)
    )
    mundane_name = str(v_meta.get("mundane_name") or "") if not in_spirit_zone else ""
    plaza_id = INNER_PLAZA_NODE_IDS[village_key]
    royal_id = ROYAL_PAVILION_NODE_IDS[village_key]

    cur_st = get_village_veil_status(session_id, village_key)
    prior_turn = int(cur_st.get("unlocked_turn") or 0)
    if cur_st.get("attuned") and not cur_st.get("atonement_required") and prior_turn > 0:
        eff_turn = min(prior_turn, eff_turn) if eff_turn > 0 else prior_turn

    fac_updates: Dict[str, Any] = {
        "veil_village_key": village_key,
        "veil_attuned": True,
        "is_hidden": False,
        "discovered": True,
        "unlocked_permanent": True,
        "veil_atonement_required": False,
        "unlocked_turn": eff_turn,
        "last_unlock_reason": reason,
        "true_name": true_name,
    }
    if mundane_name:
        fac_updates["mundane_name"] = mundane_name
    with db.UnitOfWork() as conn:
        db.update_world_node_state(session_id, fac_id, fac_updates)

        target_zone_id = SPIRIT_ZONE_BY_VILLAGE[village_key] if in_spirit_zone else str(v_meta.get("zone_id") or "")
        zone_node = db.get_world_node(session_id, target_zone_id)
        zone_name = str((zone_node or {}).get("name") or v_meta.get("zone_name") or "")

        for room_id in VEILED_INNER_ROOM_IDS[village_key]:
            is_royal = (room_id == royal_id)
            room_updates: Dict[str, Any] = {
                "veil_village_key": village_key,
                "is_hidden": False,
                "discovered": True,
                "veil_atonement_required": False,
                "unlocked_turn": eff_turn,
                "last_unlock_reason": reason,
            }
            if not is_royal:
                room_updates["unlocked_permanent"] = True
            db.update_world_node_state(session_id, room_id, room_updates)
            r_node = db.get_world_node(session_id, room_id)
            if r_node and zone_name:
                db.save_session_location(
                    session_id=session_id,
                    location_id=room_id,
                    zone_name=zone_name,
                    primary_name=true_name,
                    sub_name=str(r_node.get("name") or room_id),
                    atmosphere=str(r_node.get("atmosphere") or ""),
                    is_dynamic=0,
                )

        if in_spirit_zone:
            from .folklore_spirit_realm import SPIRIT_VILLAGE_PUBLIC_FACILITIES
            pub_facs = SPIRIT_VILLAGE_PUBLIC_FACILITIES.get(village_key, ())
            for extra_fid in pub_facs:
                db.update_world_node_state(
                    session_id,
                    extra_fid,
                    {
                        "veil_village_key": village_key,
                        "is_hidden": False,
                        "discovered": True,
                        "veil_atonement_required": False,
                        "unlocked_permanent": True,
                        "unlocked_turn": eff_turn,
                        "last_unlock_reason": reason,
                    },
                )
            if pub_facs:
                ph = ",".join("?" for _ in pub_facs)
                child_rows = conn.execute(
                    f"SELECT node_id FROM world_nodes WHERE session_id = ? AND parent_id IN ({ph}) AND node_type = 'ROOM'",
                    (session_id, *pub_facs),
                ).fetchall()
                for cr in child_rows:
                    c_nid = str(cr["node_id"] or "")
                    if c_nid and c_nid not in VEILED_INNER_ROOM_IDS[village_key]:
                        db.update_world_node_state(
                            session_id,
                            c_nid,
                            {
                                "veil_village_key": village_key,
                                "is_hidden": False,
                                "discovered": True,
                                "veil_atonement_required": False,
                                "unlocked_permanent": True,
                                "unlocked_turn": eff_turn,
                                "last_unlock_reason": reason,
                            },
                        )

        if not in_spirit_zone:
            conn.execute(
                "UPDATE world_nodes SET name = ? WHERE session_id = ? AND node_id = ?",
                (true_name, session_id, fac_id),
            )
            if mundane_name:
                conn.execute(
                    "UPDATE session_locations SET primary_name = ? WHERE session_id = ? AND primary_name = ?",
                    (true_name, session_id, mundane_name),
                )
        conn.execute(
            "UPDATE world_nodes SET is_transit_hub = 1 WHERE session_id = ? AND node_id = ?",
            (session_id, plaza_id),
        )
        if in_spirit_zone:
            if reveal_human_portal:
                on_enter_village_from_human_threshold(session_id, village_key, turn_number=eff_turn, conn=conn)
            else:
                on_enter_village_overland_from_spirit_realm(session_id, village_key, turn_number=eff_turn, conn=conn)
    return {"village_key": village_key, "facility_id": fac_id, "true_name": true_name, "unlocked_turn": eff_turn}


def is_leyline_spirit_passage_unlocked(session_id: int, session: Optional[dict] = None) -> bool:
    """Returns True if the 2-minute Leyline Spirit Passage between the two enclaves is unlocked."""
    if isinstance(session, dict) and session.get("leyline_spirit_passage_unlocked"):
        return True
    if not session_id:
        return False
    sess = db.get_session(session_id)
    if isinstance(sess, dict) and sess.get("leyline_spirit_passage_unlocked"):
        return True
    with db.get_conn() as conn:
        row = conn.execute(
            """SELECT is_locked FROM world_edges
               WHERE session_id = ? AND edge_type = 'leyline_spirit_passage'
                 AND from_node_id IN ('sub_kitsune_inner_plaza', 'sub_bunian_inner_plaza', 'sub_kitsune_leyline_shrine', 'sub_bunian_orchid_spring')
                 AND to_node_id IN ('sub_kitsune_inner_plaza', 'sub_bunian_inner_plaza', 'sub_kitsune_leyline_shrine', 'sub_bunian_orchid_spring')
               LIMIT 1""",
            (session_id,),
        ).fetchone()
        if row is not None and int(row["is_locked"] or 0) == 0:
            return True
    return False


def unlock_leyline_spirit_passage(
    session_id: int,
    turn_number: Optional[int] = None,
    reason: str = "leyline_attuned",
) -> Dict[str, Any]:
    """Unlocks the bidirectional 2-minute Leyline Spirit Passage between Sato-no-Inari and Kampung Kayangan."""
    if not session_id:
        return {"unlocked": False}
    eff_turn = int(turn_number if turn_number is not None else db.get_effective_session_turn(session_id))
    with db.UnitOfWork() as conn:
        attune_folklore_village(session_id, "kitsune", turn_number=eff_turn, reason=reason)
        attune_folklore_village(session_id, "bunian", turn_number=eff_turn, reason=reason)

        cur = conn.execute(
            """UPDATE world_edges SET is_locked = 0, travel_minutes = 2
               WHERE session_id = ? AND edge_type = 'leyline_spirit_passage'
                 AND from_node_id IN ('sub_kitsune_inner_plaza', 'sub_bunian_inner_plaza', 'sub_kitsune_leyline_shrine', 'sub_bunian_orchid_spring')
                 AND to_node_id IN ('sub_kitsune_inner_plaza', 'sub_bunian_inner_plaza', 'sub_kitsune_leyline_shrine', 'sub_bunian_orchid_spring')""",
            (session_id,),
        )
        if cur.rowcount == 0:
            conn.execute(
                """INSERT OR REPLACE INTO world_edges
                   (session_id, from_node_id, to_node_id, travel_minutes, is_locked, skill_check_type, skill_check_dc, edge_type, is_bidirectional)
                   VALUES (?, 'sub_kitsune_inner_plaza', 'sub_bunian_inner_plaza', 2, 0, '', 0, 'leyline_spirit_passage', 1)""",
                (session_id,),
            )
            conn.execute(
                """INSERT OR REPLACE INTO world_edges
                   (session_id, from_node_id, to_node_id, travel_minutes, is_locked, skill_check_type, skill_check_dc, edge_type, is_bidirectional)
                   VALUES (?, 'sub_kitsune_leyline_shrine', 'sub_bunian_orchid_spring', 2, 0, '', 0, 'leyline_spirit_passage', 1)""",
                (session_id,),
            )

        db.update_session(
            session_id,
            extra={
                "leyline_spirit_passage_unlocked": True,
                "leyline_unlocked_turn": eff_turn,
                "leyline_unlock_reason": reason,
            },
        )
    return {"unlocked": True, "turn_number": eff_turn, "reason": reason}


def maybe_evaluate_leyline_passage(
    session_id: int,
    session: Optional[dict] = None,
    actions: Optional[list] = None,
    party: Optional[list] = None,
    turn_number: Optional[int] = None,
    persist_db: bool = True,
) -> Optional[Dict[str, Any]]:
    """Checks if holding both Permission Tokens or passing a PER >= 15 check at a Leyline Shrine unlocks the shortcut."""
    if not session_id or is_leyline_spirit_passage_unlocked(session_id, session=session):
        return None
    if (
        get_village_veil_status(session_id, "kitsune", session=session).get("atonement_required")
        or get_village_veil_status(session_id, "bunian", session=session).get("atonement_required")
    ):
        return None

    inv_str = _collect_party_inventory_names(session_id, party=party, session=session)
    has_both_tokens = (
        PERMISSION_TOKEN_SLUGS["kitsune"] in inv_str
        and PERMISSION_TOKEN_SLUGS["bunian"] in inv_str
    )
    if has_both_tokens:
        if not persist_db:
            return {"unlocked": True, "staged": True, "reason": "dual_permission_tokens"}
        return unlock_leyline_spirit_passage(session_id, turn_number=turn_number, reason="dual_permission_tokens")

    first_action = actions[0] if (actions and isinstance(actions[0], dict)) else {}
    act_label = str(first_action.get("label") or "").lower()
    act_stat = str(first_action.get("stat") or "").upper().strip()
    chk = first_action.get("check")
    chk_tier = ""
    if isinstance(chk, dict):
        chk_tier = str(chk.get("tier") or "").lower()
    elif chk is not None:
        chk_tier = str(getattr(chk, "tier", "") or "").lower()

    curr_nid = str((session or {}).get("current_node_id") or "")
    on_leyline_node = curr_nid in (
        "sub_kitsune_leyline_shrine",
        "sub_bunian_orchid_spring",
        "sub_kitsune_inner_plaza",
        "sub_bunian_inner_plaza",
    )
    if on_leyline_node and act_stat == "PER" and any(k in act_label for k in ("leyline", "spirit arch", "spirit passage", "attune")):
        if chk_tier in ("critical_success", "crit_success", "success", "partial_success"):
            if not persist_db:
                return {"unlocked": True, "staged": True, "reason": "leyline_perception_attunement"}
            return unlock_leyline_spirit_passage(session_id, turn_number=turn_number, reason="leyline_perception_attunement")
    return None


def evaluate_folklore_veil_gate(
    session_id: int,
    target_node_id: str,
    node: Dict[str, Any],
    fac_node: Optional[Dict[str, Any]],
    session: Optional[dict],
    actions: Optional[list] = None,
    party: Optional[list] = None,
    active_companions: Optional[list] = None,
    current_minute: int = 480,
    persist_db: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Evaluates veil access for Hidden Kitsune Village and Hidden Bunian Village BEFORE generic key regexes.
    Returns None if target_node_id is unrelated to folklore villages; otherwise returns an access_gate result dict.
    """
    from .access_gate import Phase2Choice

    village_key, v_meta = resolve_folklore_village_for_node(session_id, target_node_id, node=node, fac_node=fac_node)
    if not village_key or not v_meta:
        return None

    scen_key = str((session or {}).get("scenario") or "")
    if scen_key and not scenario_data.is_anomalous_incursions_scenario(scen_key) and "urban_anomalies" not in scen_key.lower():
        return None

    outer_id = OUTER_THRESHOLD_NODE_IDS[village_key]
    outer_name = str(v_meta.get("outer_threshold_name") or node.get("name") or outer_id)
    fac_id = str(v_meta.get("village_id") or "")
    royal_id = ROYAL_PAVILION_NODE_IDS[village_key]
    plaza_id = INNER_PLAZA_NODE_IDS[village_key]
    token_name = str(v_meta.get("permission_token_name") or "")
    token_slug = PERMISSION_TOKEN_SLUGS[village_key]
    atonement_cost = int(v_meta.get("atonement_cost_gold") or 100)
    atonement_label = str(v_meta.get("atonement_offering_label") or "Sacred Atonement Offering")

    status = get_village_veil_status(session_id, village_key, session=session)
    inv_str = _collect_party_inventory_names(session_id, party=party, session=session)
    has_token = token_slug in inv_str
    escort_name = _has_village_companion_escort(session_id, village_key, active_companions=active_companions)

    first_action = actions[0] if (actions and isinstance(actions[0], dict)) else {}
    act_label = " ".join(str(a.get("label", "") if isinstance(a, dict) else a) for a in (actions or [])).lower()
    act_stat = str(first_action.get("stat") or "").upper().strip()
    chk = first_action.get("check")
    chk_tier = ""
    if isinstance(chk, dict):
        chk_tier = str(chk.get("tier") or "").lower()
    elif chk is not None:
        chk_tier = str(getattr(chk, "tier", "") or "").lower()
    per_roll_passed = bool(
        act_stat == "PER"
        and chk_tier in ("critical_success", "crit_success", "success", "partial_success")
    )

    # Helper to find player character & gold for atonement offering
    char_obj = None
    for member in (party or []):
        cand = member[0] if isinstance(member, (tuple, list)) else member
        if isinstance(cand, dict) and (cand.get("user_id") or cand.get("gold") is not None):
            char_obj = cand
            break
    user_id = int((char_obj or {}).get("user_id") or ((session or {}).get("host_user_id") or (session or {}).get("host_id") or 0))
    db_char = db.get_character(user_id) if user_id else None
    avail_gold = int((char_obj.get("gold") if (char_obj and char_obj.get("gold") is not None) else (db_char or {}).get("gold")) or 0)

    staged_ops: Dict[str, Any] = {}

    def _record_in_memory_attunement() -> None:
        if isinstance(session, dict):
            cur_list = list(session.get("_staged_attuned_villages") or [])
            if village_key not in cur_list:
                cur_list.append(village_key)
            session["_staged_attuned_villages"] = cur_list

    def _with_staged(payload: Dict[str, Any]) -> Dict[str, Any]:
        if staged_ops and not persist_db:
            payload["staged_folklore_ops"] = dict(staged_ops)
        return payload

    # 1. Sanctuary Treaty Atonement Lock (blocks inner rooms from all directions & handles atonement at threshold/Crossroads)
    curr_nid_for_gate = str((session or {}).get("current_node_id") or "").strip()
    from .folklore_spirit_realm import (
        ALL_SPIRIT_GUEST_FACILITY_IDS,
        SPIRIT_GUEST_COTTAGE_SPEC,
        is_node_in_crossroads_truce,
        is_node_in_spirit_realm,
    )
    is_at_crossroads_border = is_node_in_crossroads_truce(curr_nid_for_gate)
    wants_atonement = any(k in act_label for k in ("atonement", "sacred aburaage", "bunga rampai", "black myrrh", "cypress incense", "present sacred offering"))
    if status["atonement_required"]:
        if wants_atonement and avail_gold >= atonement_cost and (target_node_id == outer_id or curr_nid_for_gate == outer_id or is_at_crossroads_border):
            if isinstance(char_obj, dict):
                char_obj["gold"] = max(0, avail_gold - atonement_cost)
            if persist_db:
                if user_id and db_char:
                    db.apply_hp_mp_delta(user_id, gold_delta=-atonement_cost)
                attune_folklore_village(session_id, village_key, reason="treaty_atonement_offering")
                maybe_evaluate_leyline_passage(session_id, session=session, actions=actions, party=party, persist_db=True)
                status = get_village_veil_status(session_id, village_key, session=session)
            else:
                _record_in_memory_attunement()
                staged_ops["atonement_payment"] = {
                    "user_id": user_id,
                    "cost": atonement_cost,
                    "village_key": village_key,
                }
                staged_ops["attune_village"] = {
                    "village_key": village_key,
                    "reason": "treaty_atonement_offering",
                }
                ley_res = maybe_evaluate_leyline_passage(session_id, session=session, actions=actions, party=party, persist_db=False)
                if ley_res and ley_res.get("unlocked"):
                    staged_ops["unlock_leyline_reason"] = str(ley_res.get("reason") or "leyline_attuned")
                status = get_village_veil_status(session_id, village_key, session=session)
            if target_node_id == outer_id:
                veil_fx = (
                    "foxfire"
                    if village_key == "kitsune"
                    else ("cempaka-scented mist" if village_key == "bunian" else "silver cypress incense")
                )
                return _with_staged({
                    "gated": False,
                    "unlocked_by": "treaty_atonement_offering",
                    "prompt_directive": (
                        f"[STAGE DIRECTION — SANCTUARY VEIL APPEASED]: Your humble {atonement_label} is accepted by the unseen guardians; "
                        f"the sealed {veil_fx} veil parts once more."
                    ),
                })
        elif target_node_id != outer_id:
            in_spirit = is_node_in_spirit_realm(session_id, curr_nid_for_gate) or is_at_crossroads_border
            fallback_nid = "sub_crossroads_tea_hall" if in_spirit else outer_id
            fallback_fac = "loc_crossroads_tea_house" if in_spirit else fac_id
            fallback_name = "The Two-Moons River Tea-Pavilion" if in_spirit else outer_name
            choices = []
            if avail_gold >= atonement_cost:
                choices.append(Phase2Choice(f"Present {atonement_label} to appease the sanctuary guardians", stat="NONE", requirement=0))
            choices.append(Phase2Choice(f"Retreat toward {fallback_name}" if in_spirit else f"Remain at {outer_name}", stat="NONE", requirement=0))
            return {
                "gated": True,
                "node_id": fallback_nid,
                "facility_node_id": fallback_fac,
                "node_name": fallback_name,
                "reason_code": "sanctuary_treaty_atonement",
                "reason_label": "Sanctuary Veil Sealed — Atonement Offering Required",
                "focal_point": f"At {fallback_name} (Sealed Sanctuary Veil)",
                "prompt_directive": (
                    f"[STAGE DIRECTION — SEALED FOLKLORE VEIL]: Because the Sanctuary Non-Aggression Pact was broken, "
                    f"the hidden enclave remains sealed behind impenetrable spirit wards from every approach until a respectful offering of atonement is made."
                ),
                "barrier_choices": choices,
            }

    # Check dual-token / PER Leyline Spirit Passage opportunistically once no treaty lock is active
    ley_res_mid = maybe_evaluate_leyline_passage(session_id, session=session, actions=actions, party=party, persist_db=persist_db)
    if ley_res_mid and ley_res_mid.get("unlocked") and not persist_db:
        staged_ops["unlock_leyline_reason"] = str(ley_res_mid.get("reason") or "leyline_attuned")

    # 2. Mundane Outer Threshold Facility / Room (always accessible to walk into; auto-attunes if holding token, escorted, or passing PER)
    eff_dc = get_effective_veil_dc(session_id, village_key, current_minute)
    outer_fac_id = (
        "loc_kitsune_torii_approach"
        if village_key == "kitsune"
        else ("loc_bunian_mist_glade" if village_key == "bunian" else "sub_uc_black_font")
    )
    if target_node_id in (outer_id, outer_fac_id) or (target_node_id == fac_id and not status["attuned"] and not has_token and not escort_name and not per_roll_passed and not is_node_in_spirit_realm(session_id, curr_nid_for_gate)):
        if not status["atonement_required"] and not status["attuned"] and (has_token or escort_name or per_roll_passed):
            unlock_reason = "permission_token" if has_token else ("village_companion_escort" if escort_name else "veil_perception")
            if persist_db:
                attune_folklore_village(session_id, village_key, reason=unlock_reason)
            else:
                _record_in_memory_attunement()
                staged_ops["attune_village"] = {"village_key": village_key, "reason": unlock_reason}
            tok_cue = (
                "the clear chime of the consecrated shrine bell"
                if village_key == "kitsune"
                else (
                    "the resonant cempaka-scented reed flute"
                    if village_key == "bunian"
                    else "the cold silver weight of the bone-etched catacomb signet against the black water"
                )
            )
            return _with_staged({
                "gated": False,
                "unlocked_by": unlock_reason,
                "prompt_directive": (
                    f"[STAGE DIRECTION — FOLKLORE VEIL PARTED]: At {outer_name}, "
                    f"{tok_cue if has_token else (f'{escort_name} guiding your step' if escort_name else 'your heightened perception catching the seam in the illusion')} "
                    f"parts the mundane mirage, revealing the true path into {v_meta.get('true_name')}!"
                ),
            })
        if not status["attuned"]:
            mirage_desc = (
                "mountain fox-shrine corridor"
                if village_key == "kitsune"
                else (
                    "mist-draped banyan and bamboo clearing"
                    if village_key == "bunian"
                    else "still subterranean stone basin of ink-dark catacomb water"
                )
            )
            return _with_staged({
                "gated": False,
                "mundane_veil_active": True,
                "veil_dc": eff_dc,
                "prompt_directive": (
                    f"[STAGE DIRECTION — MUNDANE THRESHOLD MIRAGE]: To ordinary sight, {outer_name} appears only as a tranquil "
                    f"{mirage_desc}, "
                    f"though subtle spiritual ripples hint that something ancient lies veiled just out of view."
                ),
            })
        return _with_staged({"gated": False})

    # 3. Inner Village Nodes (Overland bypass from inside Spirit Realm, OR Token / Escort / PER from Human Realm — NEVER mundane 'key')
    from_spirit_overland = bool(
        is_node_in_spirit_realm(session_id, curr_nid_for_gate)
        and curr_nid_for_gate
    )
    if not status["attuned"]:
        if from_spirit_overland:
            if persist_db:
                attune_folklore_village(
                    session_id,
                    village_key,
                    reason="spirit_realm_overland",
                    reveal_human_portal=False,
                )
            else:
                _record_in_memory_attunement()
                staged_ops["attune_village"] = {
                    "village_key": village_key,
                    "reason": "spirit_realm_overland",
                    "reveal_human_portal": False,
                }
            status = get_village_veil_status(session_id, village_key, session=session)
        elif has_token or escort_name or per_roll_passed:
            unlock_reason = "permission_token" if has_token else ("village_companion_escort" if escort_name else "veil_perception")
            if persist_db:
                attune_folklore_village(session_id, village_key, reason=unlock_reason)
            else:
                _record_in_memory_attunement()
                staged_ops["attune_village"] = {"village_key": village_key, "reason": unlock_reason}
            status = get_village_veil_status(session_id, village_key, session=session)
        else:
            twilight_hint = " (Twilight Veil Thinning)" if is_twilight_veil_thinning(current_minute) else ""
            seam_label = (
                "torii foxfire"
                if village_key == "kitsune"
                else ("banyan mist" if village_key == "bunian" else "black-water catacomb reflection")
            )
            loop_label = (
                "vermilion torii gates and drifting incense"
                if village_key == "kitsune"
                else (
                    "curtains of banyan roots and white cempaka mist"
                    if village_key == "bunian"
                    else "echoing slate colonnades and motionless ink-black water"
                )
            )
            barrier_choices = [
                Phase2Choice(
                    f"[PER] Focus your senses on the shimmering {seam_label} seam{twilight_hint}",
                    stat="PER",
                    requirement=eff_dc,
                ),
                Phase2Choice(f"Step back to {outer_name}", stat="NONE", requirement=0),
            ]
            return {
                "gated": True,
                "node_id": outer_id,
                "facility_node_id": fac_id,
                "node_name": outer_name,
                "reason_code": "folklore_veil_unattuned",
                "reason_label": f"Illusion Veil Unattuned{twilight_hint} — Requires {token_name}, Escort, or Keen Perception",
                "focal_point": f"At {outer_name} (Before the Illusion Veil)",
                "prompt_directive": (
                    f"[STAGE DIRECTION — HIDDEN FOLKLORE VEIL]: Every step past {outer_name} loops gently back through "
                    f"{loop_label}. "
                    f"Without {token_name}, a villager's guidance, or keen spiritual perception, the hidden enclave remains unseen."
                ),
                "barrier_choices": barrier_choices,
            }

    # 3a. Al-Ghul Pale Ossuary Distrusted Sentinel Check (35g toll or CHA/INT/STR nerve check at Plaza; private chambers stay gated until Neutral 0+)
    if village_key == "ghoul":
        from mechanics.social.folklore_ghoul import (
            GHOUL_SENTINEL_TOLL_GOLD,
            evaluate_ghoul_sentinel_gate,
            resolve_ghoul_sentinel_clearance,
        )
        eff_day_g = int((session or {}).get("current_day") or 1)
        sent_res = evaluate_ghoul_sentinel_gate(session_id, target_node_id, current_day=eff_day_g)
        if sent_res.get("distrusted"):
            wants_toll = any(k in act_label for k in ("toll", "35g", "pay sentinel", "pay outsider"))
            nerve_stat_ok = act_stat in ("CHA", "INT", "STR") and chk_tier in ("critical_success", "crit_success", "success", "partial_success")
            nerve_label_ok = any(k in act_label for k in ("nerve", "sentinel", "hold your gaze", "gaze", "ossuary", "argument", "challenge"))
            if (wants_toll or (nerve_stat_ok and nerve_label_ok)) and target_node_id in (plaza_id, fac_id, "loc_hidden_ghoul_village", "sub_ghoul_curio_morgue", "sub_ghoul_wake_lounge", "sub_ghoul_prep_gallery", "sub_ghoul_sparring_pit", "sub_ghoul_ledger_hall"):
                c_method = "toll" if wants_toll else "nerve"
                if c_method == "toll" and avail_gold < GHOUL_SENTINEL_TOLL_GOLD:
                    sent_res["gated"] = True
                elif persist_db:
                    cl_res = resolve_ghoul_sentinel_clearance(
                        session_id,
                        method=c_method,
                        stat=act_stat or "CHA",
                        user_id=user_id or None,
                        roll_override=12 if c_method == "nerve" else None,
                    )
                    if cl_res.get("ok"):
                        sent_res = evaluate_ghoul_sentinel_gate(session_id, target_node_id, current_day=eff_day_g)
                else:
                    staged_ops["ghoul_sentinel_clearance"] = {
                        "method": c_method,
                        "stat": act_stat or "CHA",
                        "user_id": user_id,
                    }
                    if not sent_res.get("requires_neutral_rep"):
                        sent_res["gated"] = False
            if sent_res.get("gated"):
                plaza_name = str(v_meta.get("inner_plaza_name") or plaza_id)
                b_choices = [
                    Phase2Choice(f"Pay the {GHOUL_SENTINEL_TOLL_GOLD}g Outsider Toll to the Ossuary Sentinels", stat="NONE", requirement=0),
                    Phase2Choice("[CHA] Hold the sentinels' gaze with cool Ossuary poise", stat="CHA", requirement=11),
                    Phase2Choice(f"Step back to {plaza_name}", stat="NONE", requirement=0),
                ]
                if sent_res.get("requires_neutral_rep"):
                    b_choices = [Phase2Choice(f"Speak respectfully in {plaza_name} to earn Neutral standing (0+)", stat="NONE", requirement=0)]
                return _with_staged({
                    "gated": True,
                    "node_id": plaza_id if target_node_id != plaza_id else outer_id,
                    "facility_node_id": fac_id,
                    "node_name": str(node.get("name") or target_node_id),
                    "reason_code": str(sent_res.get("reason") or "ghoul_sentinel_gate"),
                    "reason_label": "Pale Ossuary Sentinel Gate (Distrusted Standing < 0)",
                    "focal_point": f"Before the Ashen Cypress Sentinels at {plaza_name}",
                    "prompt_directive": (
                        f"[STAGE DIRECTION — PALE OSSUARY SENTINELS]: {sent_res.get('message', '')} "
                        "The cold-eyed Al-Ghul sentinels do not attack on sight; they wait in composed silence for gold, steady nerve, or earned standing."
                    ),
                    "barrier_choices": b_choices,
                })

    # 3b. Spirit Court Guest-Cottage Check (must be earned at >= 70 standing)
    guest_spec = SPIRIT_GUEST_COTTAGE_SPEC.get(village_key) or {}
    if target_node_id in ALL_SPIRIT_GUEST_FACILITY_IDS or target_node_id in (guest_spec.get("room_ids") or ()):
        owned_props = db.get_player_properties(int(session_id)) if session_id else []
        is_cottage_owned = any(p.get("property_id") == guest_spec.get("property_id") for p in owned_props)
        if not is_cottage_owned:
            plaza_name = str(v_meta.get("inner_plaza_name") or plaza_id)
            return _with_staged({
                "gated": True,
                "node_id": plaza_id,
                "facility_node_id": str(guest_spec.get("facility_node_id") or fac_id),
                "node_name": str(guest_spec.get("name") or target_node_id),
                "reason_code": "spirit_guest_cottage_locked",
                "reason_label": "Private Court Guest-Cottage (Court Standing >= 70 Required)",
                "focal_point": f"Outside {guest_spec.get('name')} at {plaza_name}",
                "prompt_directive": (
                    f"[STAGE DIRECTION — HONOREES-ONLY GUEST COTTAGE]: The carved timber doorway of "
                    f"{guest_spec.get('name')} is reserved exclusively for deeply honored friends of the court."
                ),
                "barrier_choices": [Phase2Choice(f"Return to {plaza_name}", stat="NONE", requirement=0)],
            })

    # 4. Private Sovereign / Royal Heir Chamber Check (even after village attunement, Turn-1 platonic +20 cannot barge in!)
    if target_node_id == royal_id:
        if _is_royal_chamber_welcomed(session_id, village_key, active_companions=active_companions):
            return _with_staged({"gated": False, "unlocked_by": "sovereign_trust"})
        plaza_name = str(v_meta.get("inner_plaza_name") or plaza_id)
        royal_name = str(v_meta.get("royal_pavilion_name") or royal_id)
        return _with_staged({
            "gated": True,
            "node_id": plaza_id,
            "facility_node_id": fac_id,
            "node_name": royal_name,
            "reason_code": "royal_pavilion_private",
            "reason_label": "Private Sovereign Sanctum (Deep Trust or Courtship Required)",
            "focal_point": f"Outside {royal_name} at {plaza_name}",
            "prompt_directive": (
                f"[STAGE DIRECTION — PRIVATE ROYAL PAVILION]: Courteous sanctuary attendants bow before the silk-screened threshold of "
                f"{royal_name}; only cherished confidants or beloved partners of the sovereign household may enter the private inner chambers."
            ),
            "barrier_choices": [
                Phase2Choice(f"Converse respectfully in {plaza_name}", stat="NONE", requirement=0),
            ],
        })

    return _with_staged({"gated": False, "unlocked_by": "folklore_veil_attuned"})


def get_folklore_sanctuary_rest_multiplier(
    session_id: int,
    node_id: str,
    active_companions: Optional[list] = None,
) -> float:
    """
    Returns 1.5 when resting inside a Sovereign/Royal Pavilion (`sub_bunian_royal_istana` or
    `sub_kitsune_sovereign_pavilion`) while welcomed (trust >= 70 or romantic courtship), else 1.0.
    """
    nid = str(node_id or "").strip()
    if nid == "sub_kitsune_sovereign_pavilion":
        return 1.5 if _is_royal_chamber_welcomed(session_id, "kitsune", active_companions=active_companions) else 1.0
    if nid == "sub_bunian_royal_istana":
        return 1.5 if _is_royal_chamber_welcomed(session_id, "bunian", active_companions=active_companions) else 1.0
    if nid == "sub_ghoul_sovereign_manor":
        return 1.5 if _is_royal_chamber_welcomed(session_id, "ghoul", active_companions=active_companions) else 1.0
    return 1.0


from .folklore_veil_lifecycle import (  # noqa: E402
    apply_sanctuary_treaty_violation,  # static-check: ignore[unused-import]
    backfill_zone_split_and_hidden_villages_v49,  # static-check: ignore[unused-import]
    preview_sanctuary_treaty_violation,  # static-check: ignore[unused-import]
    rollback_folklore_veil_state_after_turn,  # static-check: ignore[unused-import]
)
