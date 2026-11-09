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

FOLKLORE_VILLAGE_FACILITY_IDS: Tuple[str, str] = (
    "loc_hidden_kitsune_village",
    "loc_hidden_bunian_village",
)

OUTER_THRESHOLD_NODE_IDS: Dict[str, str] = {
    "kitsune": "loc_et_fox_torii_tunnel",
    "bunian": "loc_bunian_threshold_glade",
}

INNER_PLAZA_NODE_IDS: Dict[str, str] = {
    "kitsune": "sub_kitsune_inner_plaza",
    "bunian": "sub_bunian_inner_plaza",
}

ROYAL_PAVILION_NODE_IDS: Dict[str, str] = {
    "kitsune": "sub_kitsune_sovereign_pavilion",
    "bunian": "sub_bunian_royal_istana",
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
}

PERMISSION_TOKEN_SLUGS: Dict[str, str] = {
    "kitsune": "fox-fire brass suzu bell",
    "bunian": "cempaka brass serunai",
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
    nid = str(node_id).strip()
    catalog = load_folklore_villages_catalog()
    villages = catalog.get("villages") or {}

    if nid == "loc_hidden_kitsune_village" or nid == "loc_et_fox_torii_tunnel" or nid in VEILED_INNER_ROOM_IDS["kitsune"]:
        return "kitsune", villages.get("kitsune") or {}
    if nid == "loc_hidden_bunian_village" or nid == "loc_bunian_threshold_glade" or nid in VEILED_INNER_ROOM_IDS["bunian"]:
        return "bunian", villages.get("bunian") or {}

    for candidate in (node, fac_node):
        if isinstance(candidate, dict):
            cid = str(candidate.get("node_id") or "")
            pid = str(candidate.get("parent_id") or "")
            if "kitsune" in cid or pid == "loc_hidden_kitsune_village":
                return "kitsune", villages.get("kitsune") or {}
            if "bunian" in cid or pid == "loc_hidden_bunian_village":
                return "bunian", villages.get("bunian") or {}
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
        if db.is_descendant_of(session_id, nid, "loc_hidden_kitsune_village"):
            return "kitsune", villages.get("kitsune") or {}
        if db.is_descendant_of(session_id, nid, "loc_hidden_bunian_village"):
            return "bunian", villages.get("bunian") or {}
    return None, None


def get_village_veil_status(
    session_id: int,
    village_key: str,
    session: Optional[dict] = None,
) -> Dict[str, Any]:
    """Returns normalized attunement & treaty status for 'kitsune' or 'bunian'."""
    catalog = load_folklore_villages_catalog()
    v_meta = (catalog.get("villages") or {}).get(village_key) or {}
    fac_id = str(v_meta.get("village_id") or (
        "loc_hidden_kitsune_village" if village_key == "kitsune" else "loc_hidden_bunian_village"
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
    return None


def _is_royal_chamber_welcomed(session_id: int, village_key: str, active_companions: Optional[list] = None) -> bool:
    """Checks whether the player has romantic standing or deep trust (>= 70) with the village Sovereign/Royal Heir."""
    if not session_id:
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
) -> Dict[str, Any]:
    """
    Permanently unmasks a veiled village for the session:
    - Marks facility and inner sub-locations discovered=True, is_hidden=False
    - Unlocks non-private village sub-locations permanently (preserving private royal chamber rules)
    - Promotes the village facility display name from mundane threshold to true enclave name
    - Enables direct World Map / Spirit-Waystation transit to the inner plaza (is_transit_hub=1)
    """
    if not session_id or village_key not in ("kitsune", "bunian"):
        return {}
    eff_turn = int(turn_number if turn_number is not None else db.get_effective_session_turn(session_id))
    catalog = load_folklore_villages_catalog()
    v_meta = (catalog.get("villages") or {}).get(village_key) or {}
    fac_id = str(v_meta.get("village_id") or (
        "loc_hidden_kitsune_village" if village_key == "kitsune" else "loc_hidden_bunian_village"
    ))
    true_name = str(v_meta.get("true_name") or fac_id)
    mundane_name = str(v_meta.get("mundane_name") or "")
    plaza_id = INNER_PLAZA_NODE_IDS[village_key]
    royal_id = ROYAL_PAVILION_NODE_IDS[village_key]

    cur_st = get_village_veil_status(session_id, village_key)
    prior_turn = int(cur_st.get("unlocked_turn") or 0)
    if cur_st.get("attuned") and not cur_st.get("atonement_required") and prior_turn > 0:
        eff_turn = min(prior_turn, eff_turn) if eff_turn > 0 else prior_turn

    fac_updates = {
        "veil_village_key": village_key,
        "veil_attuned": True,
        "is_hidden": False,
        "discovered": True,
        "unlocked_permanent": True,
        "veil_atonement_required": False,
        "unlocked_turn": eff_turn,
        "last_unlock_reason": reason,
        "mundane_name": mundane_name,
        "true_name": true_name,
    }
    with db.UnitOfWork() as conn:
        db.update_world_node_state(session_id, fac_id, fac_updates)

        zone_node = db.get_world_node(session_id, str(v_meta.get("zone_id") or ""))
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

        conn.execute(
            "UPDATE world_nodes SET name = ? WHERE session_id = ? AND node_id = ?",
            (true_name, session_id, fac_id),
        )
        conn.execute(
            "UPDATE world_nodes SET is_transit_hub = 1 WHERE session_id = ? AND node_id = ?",
            (session_id, plaza_id),
        )
        if mundane_name:
            conn.execute(
                "UPDATE session_locations SET primary_name = ? WHERE session_id = ? AND primary_name = ?",
                (true_name, session_id, mundane_name),
            )
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
            "SELECT is_locked FROM world_edges WHERE session_id = ? AND edge_type = 'leyline_spirit_passage' LIMIT 1",
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
    attune_folklore_village(session_id, "kitsune", turn_number=eff_turn, reason=reason)
    attune_folklore_village(session_id, "bunian", turn_number=eff_turn, reason=reason)

    with db.get_conn() as conn:
        cur = conn.execute(
            "UPDATE world_edges SET is_locked = 0, travel_minutes = 2 WHERE session_id = ? AND edge_type = 'leyline_spirit_passage'",
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

    # 1. Sanctuary Treaty Atonement Lock (blocks inner rooms and handles atonement at outer threshold)
    wants_atonement = any(k in act_label for k in ("atonement", "sacred aburaage", "bunga rampai", "present sacred offering"))
    if status["atonement_required"]:
        if wants_atonement and avail_gold >= atonement_cost:
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
                return _with_staged({
                    "gated": False,
                    "unlocked_by": "treaty_atonement_offering",
                    "prompt_directive": (
                        f"[STAGE DIRECTION — SANCTUARY VEIL APPEASED]: Your humble {atonement_label} is accepted by the unseen guardians; "
                        f"the sealed {'foxfire' if village_key == 'kitsune' else 'cempaka-scented mist'} veil parts once more."
                    ),
                })
        elif target_node_id != outer_id:
            choices = []
            if avail_gold >= atonement_cost:
                choices.append(Phase2Choice(f"Present {atonement_label} to appease the sanctuary guardians", stat="NONE", requirement=0))
            choices.append(Phase2Choice(f"Remain at {outer_name}", stat="NONE", requirement=0))
            return {
                "gated": True,
                "node_id": outer_id,
                "facility_node_id": fac_id,
                "node_name": outer_name,
                "reason_code": "sanctuary_treaty_atonement",
                "reason_label": "Sanctuary Veil Sealed — Atonement Offering Required",
                "focal_point": f"At {outer_name} (Sealed Sanctuary Veil)",
                "prompt_directive": (
                    f"[STAGE DIRECTION — SEALED FOLKLORE VEIL]: Because the Sanctuary Non-Aggression Pact was broken, "
                    f"the hidden path beyond {outer_name} remains sealed behind impenetrable spirit wards until a respectful offering of atonement is made."
                ),
                "barrier_choices": choices,
            }

    # Check dual-token / PER Leyline Spirit Passage opportunistically once no treaty lock is active
    ley_res_mid = maybe_evaluate_leyline_passage(session_id, session=session, actions=actions, party=party, persist_db=persist_db)
    if ley_res_mid and ley_res_mid.get("unlocked") and not persist_db:
        staged_ops["unlock_leyline_reason"] = str(ley_res_mid.get("reason") or "leyline_attuned")

    # 2. Mundane Outer Threshold (always accessible to walk into; auto-attunes if holding token, escorted, or passing PER)
    eff_dc = get_effective_veil_dc(session_id, village_key, current_minute)
    if target_node_id == outer_id or (target_node_id == fac_id and not status["attuned"] and not has_token and not escort_name and not per_roll_passed):
        if not status["atonement_required"] and not status["attuned"] and (has_token or escort_name or per_roll_passed):
            unlock_reason = "permission_token" if has_token else ("village_companion_escort" if escort_name else "veil_perception")
            if persist_db:
                attune_folklore_village(session_id, village_key, reason=unlock_reason)
            else:
                _record_in_memory_attunement()
                staged_ops["attune_village"] = {"village_key": village_key, "reason": unlock_reason}
            return _with_staged({
                "gated": False,
                "unlocked_by": unlock_reason,
                "prompt_directive": (
                    f"[STAGE DIRECTION — FOLKLORE VEIL PARTED]: At {outer_name}, "
                    f"{'the clear chime of the consecrated shrine bell' if (has_token and village_key == 'kitsune') else ('the resonant cempaka-scented reed flute' if has_token else (f'{escort_name} guiding your step' if escort_name else 'your heightened perception catching the seam in the illusion'))} "
                    f"parts the mundane mirage, revealing the true path into {v_meta.get('true_name')}!"
                ),
            })
        if not status["attuned"]:
            return _with_staged({
                "gated": False,
                "mundane_veil_active": True,
                "veil_dc": eff_dc,
                "prompt_directive": (
                    f"[STAGE DIRECTION — MUNDANE THRESHOLD MIRAGE]: To ordinary sight, {outer_name} appears only as a tranquil "
                    f"{'mountain fox-shrine corridor' if village_key == 'kitsune' else 'mist-draped banyan and bamboo clearing'}, "
                    f"though subtle spiritual ripples hint that something ancient lies veiled just out of view."
                ),
            })
        return _with_staged({"gated": False})

    # 3. Inner Village Nodes (require attunement via Token, Companion Escort, or Rolled PER Check — NEVER mundane 'key')
    if not status["attuned"]:
        if has_token or escort_name or per_roll_passed:
            unlock_reason = "permission_token" if has_token else ("village_companion_escort" if escort_name else "veil_perception")
            if persist_db:
                attune_folklore_village(session_id, village_key, reason=unlock_reason)
            else:
                _record_in_memory_attunement()
                staged_ops["attune_village"] = {"village_key": village_key, "reason": unlock_reason}
            status = get_village_veil_status(session_id, village_key, session=session)
        else:
            twilight_hint = " (Twilight Veil Thinning)" if is_twilight_veil_thinning(current_minute) else ""
            barrier_choices = [
                Phase2Choice(
                    f"[PER] Focus your senses on the shimmering {'torii foxfire' if village_key == 'kitsune' else 'banyan mist'} seam{twilight_hint}",
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
                    f"{'vermilion torii gates and drifting incense' if village_key == 'kitsune' else 'curtains of banyan roots and white cempaka mist'}. "
                    f"Without {token_name}, a villager's guidance, or keen spiritual perception, the hidden enclave remains unseen."
                ),
                "barrier_choices": barrier_choices,
            }

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
    return 1.0


from .folklore_veil_lifecycle import (  # noqa: E402
    apply_sanctuary_treaty_violation,
    backfill_zone_split_and_hidden_villages_v49,
    preview_sanctuary_treaty_violation,
    rollback_folklore_veil_state_after_turn,
)
