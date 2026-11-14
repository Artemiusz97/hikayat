"""
Residential fog-of-war abstraction and atomic concrete home-node unlocking.
Unknown NPC homes route to `SHARED_ABSTRACT_RESIDENCE_NODE` until unlocked via
invitation, Friend-tier affinity (>= 100), quest lead, tailing, household cohabitation,
or active spare-key access.
"""
from __future__ import annotations

import re
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple

import db

SHARED_ABSTRACT_RESIDENCE_NODE = "zone_residential_abstract"
RESIDENCE_UNLOCK_REASONS: FrozenSet[str] = frozenset({
    "invite",
    "friend_tier",
    "quest_lead",
    "tailed",
    "cohabitant",
    "family",
})

_FRIEND_TIER_MIN_SCORE = 100
_UNLOCK_REL_TIERS: FrozenSet[str] = frozenset({
    "friend",
    "lunch_friend",
    "mutual_attraction",
    "close_friend",
    "best_friend",
    "confidant",
    "lover",
    "partner",
    "spouse",
    "family",
})
_EXPLICIT_HH_ROLES: FrozenSet[str] = frozenset({
    "spouse",
    "partner",
    "parent",
    "child",
    "sibling",
    "guardian",
    "cohabitant",
    "roommate",
})


def _slugify_res(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text or "").strip().lower()).strip("_")


def _resolve_residence_lookup_records(
    session_id: Optional[int],
    npc: Optional[Mapping[str, Any] | str],
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Resolves caller NPC dict alongside world_roster and contact DB rows."""
    npc_dict: Dict[str, Any] = dict(npc) if isinstance(npc, Mapping) else {}
    basic = npc_dict.get("basic_info") if isinstance(npc_dict.get("basic_info"), Mapping) else {}
    lookup_key = (
        str(npc).strip()
        if isinstance(npc, str)
        else str(
            npc_dict.get("npc_key")
            or npc_dict.get("npc_id")
            or npc_dict.get("name")
            or basic.get("name")
            or ""
        ).strip()
    )

    db_row: Optional[Dict[str, Any]] = None
    contact_row: Optional[Dict[str, Any]] = None
    if session_id is not None and lookup_key:
        try:
            db_row = db.get_world_roster_npc(int(session_id), lookup_key, include_legacy_rosters=False)
        except Exception:
            db_row = None
        try:
            contact_row = db.get_contact(int(session_id), lookup_key)
        except Exception:
            contact_row = None
        if not npc_dict:
            if isinstance(db_row, dict):
                npc_dict = dict(db_row)
            elif isinstance(contact_row, dict):
                npc_dict = dict(contact_row)
    return npc_dict, db_row, contact_row


def _parse_int_score(raw: Any) -> Optional[int]:
    if raw is None or raw == "" or isinstance(raw, bool):
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def _is_player_household_cohabitant(
    sess_id: Optional[int],
    contact_row: Optional[Dict[str, Any]],
    db_row: Optional[Dict[str, Any]],
) -> bool:
    """Checks contact/household cohabitation safely without trusting raw SQL household_role defaults."""
    c_rel = contact_row.get("relations") if isinstance(contact_row, Mapping) and isinstance(contact_row.get("relations"), Mapping) else {}
    if c_rel.get("cohabiting_family") is True:
        return True
    db_rel = db_row.get("relations") if isinstance(db_row, Mapping) and isinstance(db_row.get("relations"), Mapping) else {}
    if db_rel.get("cohabiting_family") is True:
        return True

    if sess_id is None or not isinstance(contact_row, Mapping):
        return False
    hh_id = contact_row.get("household_id")
    if not hh_id:
        return False
    try:
        hh = db.get_household_by_id(int(hh_id))
        if not isinstance(hh, Mapping):
            return False
        hh_key = str(hh.get("household_key") or "").strip().lower()
        if hh_key.startswith("player"):
            return True
        session_row = db.get_session(int(sess_id)) if hasattr(db, "get_session") else None
        char_id = int((session_row or {}).get("character_id") or 0)
        if char_id and hasattr(db, "get_character_by_id"):
            p_char = db.get_character_by_id(char_id)
            p_name = str((p_char or {}).get("name") or "").strip()
            p_parts = p_name.split()
            hh_surname = str(hh.get("surname") or "").strip().lower()
            if hh_surname and p_parts and p_parts[-1].lower() == hh_surname:
                return True
    except Exception:
        pass
    return False


def can_materialize_npc_residence(
    session_id: Optional[int] | Mapping[str, Any],
    npc: Optional[Mapping[str, Any] | str | int] = None,
    reason: str = "",
) -> bool:
    """
    Returns True if an NPC's private residence is unlocked or eligible for concrete
    world-node materialization rather than collapsing to the abstract residential district.
    """
    if isinstance(session_id, Mapping):
        npc_obj: Optional[Mapping[str, Any] | str] = session_id
        sess_id: Optional[int] = int(npc) if isinstance(npc, int) else None
    else:
        sess_id = int(session_id) if session_id is not None else None
        npc_obj = npc if isinstance(npc, (Mapping, str)) else None

    clean_reason = str(reason or "").strip().lower()
    if clean_reason in RESIDENCE_UNLOCK_REASONS:
        return True

    npc_dict, db_row, contact_row = _resolve_residence_lookup_records(sess_id, npc_obj)
    if not npc_dict and not db_row and not contact_row:
        return False

    basic = npc_dict.get("basic_info") if isinstance(npc_dict.get("basic_info"), Mapping) else {}
    db_basic = db_row.get("basic_info") if isinstance(db_row, Mapping) and isinstance(db_row.get("basic_info"), Mapping) else {}
    c_basic = contact_row.get("basic_info") if isinstance(contact_row, Mapping) and isinstance(contact_row.get("basic_info"), Mapping) else {}

    # 1. Explicit persisted unlock flag: DB truth is authoritative over stale caller dicts after rollback
    if db_row is not None:
        if bool(db_row.get("residence_unlocked")):
            return True
    elif contact_row is not None and "residence_unlocked" in c_basic:
        if bool(c_basic.get("residence_unlocked")):
            return True
    else:
        if bool(npc_dict.get("residence_unlocked") or basic.get("residence_unlocked")):
            return True

    # 2. Cohabiting partner / explicit household cohabitant / family
    for src in (npc_dict, basic, db_row or {}, db_basic, c_basic):
        if isinstance(src, Mapping) and (src.get("cohabiting") or src.get("cohabiting_family")):
            return True
    if _is_player_household_cohabitant(sess_id, contact_row, db_row):
        return True
    for src in (npc_dict, basic, db_row or {}, db_basic, c_basic):
        if isinstance(src, Mapping):
            hh_role = str(src.get("household_role") or "").strip().lower()
            if hh_role in _EXPLICIT_HH_ROLES:
                return True

    # 3. Romantic partner / Friend-tier relationship (>= 100) without early break masking DB scores
    for src in (db_row or {}, db_basic, c_basic, npc_dict, basic):
        if isinstance(src, Mapping) and (src.get("is_romantic") or src.get("romantic_partner")):
            return True
        if isinstance(src, Mapping):
            tier_norm = str(src.get("relationship_tier") or "").strip().lower().replace(" ", "_")
            if tier_norm in _UNLOCK_REL_TIERS or tier_norm.startswith("mutual_attraction"):
                return True

    all_scores: List[int] = []
    for raw_score in (
        (db_row or {}).get("affinity_score"),
        (contact_row or {}).get("relationship_score"),
        npc_dict.get("affinity_score"),
        npc_dict.get("relationship_score"),
        basic.get("affinity_score"),
    ):
        parsed = _parse_int_score(raw_score)
        if parsed is not None:
            all_scores.append(parsed)
    if all_scores and max(all_scores) >= _FRIEND_TIER_MIN_SCORE:
        return True

    # 4. Active spare-key holder against the player's primary property
    if sess_id is not None and npc_dict:
        try:
            from .residences import is_npc_active_spare_key_holder

            primary_prop = db.get_primary_property(sess_id)
            spare_keys = primary_prop.get("spare_keys") if isinstance(primary_prop, Mapping) else None
            if spare_keys and is_npc_active_spare_key_holder(sess_id, npc_dict, spare_keys):
                return True
        except Exception:
            pass

    return False


def unlock_npc_residence_node(
    session_id: int,
    npc_key_or_name: str,
    unlock_reason: str = "",
    turn_number: int = 1,
    scen_key: str = "",
    reason: Optional[str] = None,
) -> str:
    """
    Atomically materializes a canonical private FACILITY + ROOM node for an NPC
    and records residence_unlocked=True in world_roster + matching contacts with
    full turn-snapshot rollback parity. Returns the concrete home ROOM node ID.
    """
    from .residences import ensure_npc_residence_materialized, is_adult_special_agent_contact

    sess_id = int(session_id)
    key_str = str(npc_key_or_name or "").strip()
    if not key_str:
        return ""
    eff_reason = str(unlock_reason or reason or "invite").strip().lower() or "invite"
    eff_scen = str(scen_key or "fantasy").strip() or "fantasy"
    t_num = max(1, int(turn_number or 1))

    db_row = db.get_world_roster_npc(sess_id, key_str, include_legacy_rosters=False)
    any_row = db_row or db.get_world_roster_npc(sess_id, key_str, include_legacy_rosters=True)
    contact_row = db.get_contact(sess_id, key_str)

    npc_name = str(
        (any_row or {}).get("name")
        or (contact_row or {}).get("name")
        or key_str.replace("_", " ").title()
    ).strip()
    slug = _slugify_res(npc_name or key_str) or _slugify_res(key_str) or "resident"

    npc_payload: Dict[str, Any] = {}
    if isinstance(any_row, dict):
        npc_payload.update(any_row)
    elif isinstance(contact_row, dict):
        npc_payload.update(contact_row)
    else:
        npc_payload["name"] = npc_name
        npc_payload["npc_id"] = key_str

    with db.UnitOfWork() as conn:
        existing_nodes = {n["node_id"]: n for n in db.get_session_world_nodes(sess_id)}
        candidate_home = str((db_row or {}).get("home_node_id") or "").strip()
        existing_home_node = existing_nodes.get(candidate_home) if candidate_home else None
        if (
            candidate_home
            and candidate_home != SHARED_ABSTRACT_RESIDENCE_NODE
            and existing_home_node is not None
            and str(existing_home_node.get("node_type") or "").upper() == "ROOM"
        ):
            home_nid = candidate_home
        else:
            home_nid = ""
            if is_adult_special_agent_contact(npc_payload) or bool(npc_payload.get("is_student_agent")):
                try:
                    sa_sub_id, _ = ensure_npc_residence_materialized(sess_id, npc_payload, scen_key=eff_scen)
                    if sa_sub_id and sa_sub_id != SHARED_ABSTRACT_RESIDENCE_NODE:
                        home_nid = sa_sub_id
                except Exception:
                    home_nid = ""

            if not home_nid:
                res_zone = next(
                    (
                        n
                        for n in existing_nodes.values()
                        if str(n.get("node_type") or "").upper() == "ZONE"
                        and str(n.get("category") or "").lower() == "residential"
                        and n.get("node_id") != SHARED_ABSTRACT_RESIDENCE_NODE
                    ),
                    None,
                ) or next(
                    (
                        n
                        for n in existing_nodes.values()
                        if str(n.get("node_type") or "").upper() == "ZONE"
                        and n.get("node_id") != SHARED_ABSTRACT_RESIDENCE_NODE
                    ),
                    None,
                )

                zone_id: Optional[str] = str(res_zone["node_id"]) if res_zone else None
                zone_name = str(res_zone.get("name") or "Residential District") if res_zone else "Residential District"
                fac_id = f"fac_npc_res_{slug}"
                fac_name = f"{npc_name}'s Residence"
                home_nid = f"sub_npc_res_{slug}"
                sub_name = f"{npc_name}'s Quarters"

                if fac_id not in existing_nodes:
                    db.save_world_node(
                        session_id=sess_id,
                        node_id=fac_id,
                        parent_id=zone_id,
                        name=fac_name,
                        node_type="FACILITY",
                        category="residential",
                        privacy_level="private",
                        is_enclosed=1,
                        is_transit_hub=0,
                        access_tier="private",
                        is_dynamic=1,
                        state_json={
                            "privacy_level": "private",
                            "owner_npc_id": key_str,
                            "owner_npc_name": npc_name,
                        },
                    )
                    if zone_id:
                        db.save_world_edge(
                            session_id=sess_id,
                            from_node_id=zone_id,
                            to_node_id=fac_id,
                            travel_minutes=2,
                            edge_type="door",
                            is_bidirectional=1,
                        )
                        sibling_facs = [
                            n["node_id"]
                            for n in existing_nodes.values()
                            if n.get("node_type") == "FACILITY"
                            and n.get("parent_id") == zone_id
                            and n["node_id"] != fac_id
                        ]
                        for sf_id in sibling_facs[:2]:
                            db.save_world_edge(
                                session_id=sess_id,
                                from_node_id=fac_id,
                                to_node_id=sf_id,
                                travel_minutes=5,
                                edge_type="pathway",
                                is_bidirectional=1,
                            )

                db.save_world_node(
                    session_id=sess_id,
                    node_id=home_nid,
                    parent_id=fac_id,
                    name=sub_name,
                    node_type="ROOM",
                    category="residential",
                    privacy_level="private",
                    is_enclosed=1,
                    is_transit_hub=0,
                    access_tier="private",
                    is_dynamic=1,
                    state_json={
                        "privacy_level": "private",
                        "is_private_intimate": True,
                        "owner_npc_id": key_str,
                        "owner_npc_name": npc_name,
                    },
                )
                db.save_world_edge(
                    session_id=sess_id,
                    from_node_id=fac_id,
                    to_node_id=home_nid,
                    travel_minutes=1,
                    edge_type="door",
                    is_bidirectional=1,
                )
                db.save_session_location(
                    sess_id,
                    home_nid,
                    zone_name,
                    fac_name,
                    sub_name,
                    atmosphere="quiet private quarters",
                    is_dynamic=1,
                )

        updated = db.set_world_roster_residence_unlocked(
            sess_id,
            key_str,
            eff_reason,
            home_node_id=home_nid,
            turn_number=t_num,
            conn=conn,
        )
        if updated is None:
            seed_data: Dict[str, Any] = {
                "npc_key": str((contact_row or {}).get("npc_id") or key_str),
                "name": npc_name,
                "origin": "legacy_adapter",
                "tier_status": "promoted",
                "affinity_score": int((contact_row or {}).get("relationship_score") or 0),
                "residence_unlocked": False,
                "home_node_id": "",
            }
            if isinstance(contact_row, dict):
                c_basic = contact_row.get("basic_info")
                if isinstance(c_basic, Mapping):
                    seed_data["basic_info"] = dict(c_basic)
                if contact_row.get("role"):
                    seed_data["role"] = str(contact_row["role"])
            db.upsert_world_roster_npc(sess_id, seed_data, turn_number=0, conn=conn)
            db.set_world_roster_residence_unlocked(
                sess_id,
                key_str,
                eff_reason,
                home_node_id=home_nid,
                turn_number=t_num,
                conn=conn,
            )

    return home_nid
