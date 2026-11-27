"""mechanics/combat/post_combat.py

Post-combat recovery, companion XP/vitality scaling, round threat decay,
DoT-kill boss telegraph pruning, and end-of-combat session cleanup.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

import db
import scenario_data

from .loadouts import (
    build_combatant_stat_sheet,
    compute_companion_vitals,
    reset_combatant_cooldowns,
)

logger = logging.getLogger(__name__)


def decay_round_threat(
    threat_ledger: Dict[str, Any],
    downed_actor_ids: Set[str],
) -> None:
    """Applies 25% exponential round decay to threat scores and instantly drops downed actors to zero threat."""
    matrix = threat_ledger.get("threat_matrix", threat_ledger)
    if isinstance(matrix, dict):
        for eid in list(matrix.keys()):
            if not isinstance(matrix[eid], dict):
                continue
            for aid in list(matrix[eid].keys()):
                if aid in downed_actor_ids:
                    matrix[eid][aid] = 0.0
                else:
                    matrix[eid][aid] = round(matrix[eid][aid] * 0.75, 2)

    taunts = threat_ledger.get("sticky_taunts")
    if isinstance(taunts, dict):
        for eid in list(taunts.keys()):
            t_info = taunts[eid]
            if isinstance(t_info, dict):
                rem = int(t_info.get("remaining_turns", 1)) - 1
                if rem <= 0 or str(t_info.get("target_id")) in downed_actor_ids:
                    taunts.pop(eid, None)
                else:
                    t_info["remaining_turns"] = rem


def cleanup_anomalous_combat_session_state(session: Dict[str, Any]) -> None:
    """Purges autonomous constructs, summons, resonance pips, and vanished stealth states when combat ends."""
    if not isinstance(session, dict):
        return
    session["_active_constructs"] = []
    session.pop("_construct_initialized_this_combat", None)
    session["player_resonance_pips"] = {}
    session["combat_threat_ledger"] = {}
    session["combat_boss_telegraph"] = {}
    session["current_npcs"] = [
        n for n in session.get("current_npcs", [])
        if not (isinstance(n, dict) and (n.get("is_summon") or n.get("is_autonomous_construct")))
    ]
    for group_key in ("party_npcs", "current_npcs"):
        for npc in (session.get(group_key) or []):
            if isinstance(npc, dict):
                reset_combatant_cooldowns(npc)
    try:
        from mechanics.stealth.core import clear_all_combat_vanished
        clear_all_combat_vanished(session)
    except Exception:
        pass


def prune_dead_combat_state(
    session: Dict[str, Any],
    surviving_enemies: List[Dict[str, Any]],
    llm_outcome: Optional[Dict[str, Any]] = None,
) -> None:
    """Prunes dead enemies (including post-turn DoT kills) from boss telegraphs and threat ledgers, or resets all on victory."""
    if not isinstance(session, dict):
        return
    live_keys: Set[str] = set()
    for e in (surviving_enemies or []):
        if isinstance(e, dict) and int(e.get("hp", 0) or 0) > 0:
            for k in ("id", "name"):
                v = e.get(k)
                if v:
                    live_keys.add(str(v))

    if not live_keys:
        cleanup_anomalous_combat_session_state(session)
        if isinstance(llm_outcome, dict):
            llm_outcome["combat_boss_telegraph"] = {}
            llm_outcome["combat_threat_ledger"] = {}
        return

    raw_telegraph = session.get("combat_boss_telegraph")
    if isinstance(raw_telegraph, dict):
        for eid in list(raw_telegraph.keys()):
            if str(eid) not in live_keys:
                raw_telegraph.pop(eid, None)
        session["combat_boss_telegraph"] = raw_telegraph
        if isinstance(llm_outcome, dict):
            llm_outcome["combat_boss_telegraph"] = raw_telegraph

    raw_ledger = session.get("combat_threat_ledger")
    if isinstance(raw_ledger, dict):
        matrix = raw_ledger.get("threat_matrix", raw_ledger)
        if isinstance(matrix, dict):
            for eid in list(matrix.keys()):
                if eid == "sticky_taunts" or eid == "threat_matrix" or eid == "current_aggro_targets":
                    continue
                if str(eid) not in live_keys and isinstance(matrix[eid], dict):
                    matrix.pop(eid, None)
        sticky = raw_ledger.get("sticky_taunts")
        if isinstance(sticky, dict):
            for eid in list(sticky.keys()):
                if str(eid) not in live_keys:
                    sticky.pop(eid, None)
        session["combat_threat_ledger"] = raw_ledger
        if isinstance(llm_outcome, dict):
            llm_outcome["combat_threat_ledger"] = raw_ledger


def finalize_post_combat_state(
    session: Dict[str, Any],
    llm_outcome: Dict[str, Any],
    enemies: List[Dict[str, Any]],
    party: Optional[List[Any]],
    total_xp_gain: int,
    dead_enemies: List[Any],
    dead_enemy_dicts_rec: List[Dict[str, Any]],
    *,
    persist_db: bool = True,
) -> None:
    """Handles post-turn companion auto-revive, party defeat extraction/recovery, companion scaling, and threat decay."""
    session_id = session.get("id", 0) if session else 0
    party_npcs = db.get_session_party_npcs(session_id) if session_id else []
    staged_pc_ops: Dict[str, Any] = {}
    status_effects_by_uid: Dict[int, List[str]] = {}

    if not enemies and (party_npcs or (party and len(party) > 1)):
        for co in llm_outcome.get("character_outcomes", []):
            if isinstance(co, dict):
                p_char = next((char for char, _ in (party or []) if char.get("name", "").lower() == co.get("name", "").lower()), None)
                if p_char:
                    p_hp = int(p_char.get("hp") if p_char.get("hp") is not None else 10)
                    projected_hp = p_hp + int(co.get("hp_change", 0) or 0)
                    if projected_hp <= 0:
                        co["hp_change"] = 1 - p_hp
                        co["status_effects"] = ["Exhausted / Recovering"]
                        llm_outcome["_combat_resolved_notice"] = (str(llm_outcome.get("_combat_resolved_notice", "")) + "\n🩹 Your companion tended to your wounds — revived with **1 HP**!").strip()

    if enemies and party:
        all_downed = True
        for p_entry in party:
            char = p_entry[0] if isinstance(p_entry, (tuple, list)) and len(p_entry) > 0 else (p_entry if isinstance(p_entry, dict) else {})
            c_name = char.get("name", "").lower()
            matching_co = next((co for co in llm_outcome.get("character_outcomes", []) if isinstance(co, dict) and co.get("name", "").lower() == c_name), None)
            c_hp = int(char.get("hp") if char.get("hp") is not None else 10)
            c_proj_hp = c_hp + (int(matching_co.get("hp_change", 0) or 0) if matching_co else 0)
            if c_proj_hp > 0:
                all_downed = False
                break
        if all_downed and party_npcs:
            for npc in party_npcs:
                if int(npc.get("hp") or 0) > 0:
                    all_downed = False
                    break

        is_anom_defeat = bool(isinstance(session, dict) and scenario_data.is_anomalous_incursions_scenario(session.get("scenario", "")))
        _realm_ext_info: dict = {}
        _collapse_realm_id = ""
        _nmap_post: dict = {}
        if all_downed and session_id and not is_anom_defeat:
            try:
                from mechanics.world.locations.realms import (
                    _format_tiered_location_in_memory,
                    collapse_dynamic_realm,
                    get_node_realm_id_in_memory,
                    get_primary_realm_in_memory,
                    get_realm_rules,
                    is_node_or_realm_hidden_in_memory,
                    parse_node_state_json,
                )
                _nodes_pre = db.get_session_world_nodes(session_id) or []
                _nmap_pre = {str(n["node_id"]): n for n in _nodes_pre if n.get("node_id")}
                _ext_curr_nid = str(session.get("current_node_id") or "").strip()
                if not _ext_curr_nid and session.get("current_location"):
                    _ext_curr_nid = db.resolve_node_id_from_location(session_id, session["current_location"]) or ""
                _ext_curr_rid = get_node_realm_id_in_memory(_ext_curr_nid, _nmap_pre) if _ext_curr_nid else ""
                _ext_r_node = _nmap_pre.get(_ext_curr_rid) if _ext_curr_rid else None
                _ext_r_rules = get_realm_rules(_ext_r_node) if _ext_r_node else {}
                if (
                    _ext_curr_rid
                    and not _ext_r_rules.get("is_primary_realm")
                    and (not _ext_r_rules.get("has_local_safe_hub", True) or _ext_r_rules.get("is_ephemeral"))
                ):
                    _dest_ext_nid = str(_ext_r_rules.get("ephemeral_origin_node_id") or "").strip()
                    if _ext_r_rules.get("is_ephemeral") and not _ext_r_rules.get("pacified"):
                        _collapse_realm_id = _ext_curr_rid
                        if persist_db:
                            collapse_dynamic_realm(session_id, _ext_curr_rid)
                        else:
                            staged_pc_ops["collapse_realm_id"] = _ext_curr_rid
                    _nmap_post = {
                        nid: nd for nid, nd in _nmap_pre.items()
                        if not _collapse_realm_id or (nid != _collapse_realm_id and get_node_realm_id_in_memory(nid, _nmap_pre) != _collapse_realm_id)
                    }
                    if not _dest_ext_nid or _dest_ext_nid not in _nmap_post:
                        _prim_r = get_primary_realm_in_memory(_nmap_post)
                        _prim_rid = str((_prim_r or {}).get("node_id") or "")
                        _desig_fac = next(
                            (
                                (nid, nd) for nid, nd in _nmap_post.items()
                                if (not _prim_rid or get_node_realm_id_in_memory(nid, _nmap_post) == _prim_rid)
                                and parse_node_state_json(nd).get("safe_sanctuary_exempt")
                                and not is_node_or_realm_hidden_in_memory(nid, _nmap_post)
                            ),
                            None,
                        )
                        if _desig_fac:
                            _desig_id, _desig_node = _desig_fac
                            if str(_desig_node.get("node_type") or "").upper() == "FACILITY":
                                _desig_room = next(
                                    (
                                        nid for nid, nd in _nmap_post.items()
                                        if str(nd.get("parent_id") or "") == _desig_id
                                        and str(nd.get("node_type") or "").upper() == "ROOM"
                                        and not is_node_or_realm_hidden_in_memory(nid, _nmap_post)
                                    ),
                                    "",
                                )
                                _dest_ext_nid = _desig_room or _desig_id
                            else:
                                _dest_ext_nid = _desig_id
                        else:
                            _safe_cats = {"sanctuary", "residential", "medical", "hub", "inn", "tavern"}
                            _prim_rooms = [
                                (nid, nd)
                                for nid, nd in _nmap_post.items()
                                if str(nd.get("node_type") or "").upper() == "ROOM"
                                and (not _prim_rid or get_node_realm_id_in_memory(nid, _nmap_post) == _prim_rid)
                                and not is_node_or_realm_hidden_in_memory(nid, _nmap_post)
                            ]
                            _safe_pick = next(
                                (
                                    nid for nid, nd in _prim_rooms
                                    if int(nd.get("is_transit_hub") or 0) == 1
                                    or str(nd.get("category") or "").lower() in _safe_cats
                                    or int((_nmap_post.get(str(nd.get("parent_id") or "")) or {}).get("is_transit_hub") or 0) == 1
                                    or str((_nmap_post.get(str(nd.get("parent_id") or "")) or {}).get("category") or "").lower() in _safe_cats
                                ),
                                _prim_rooms[0][0] if _prim_rooms else "",
                            )
                            _dest_ext_nid = _safe_pick
                    _dest_ext_loc = (
                        _format_tiered_location_in_memory(_dest_ext_nid, _nmap_post)
                        if _dest_ext_nid
                        else (session.get("current_location") or "Primary Safe Haven")
                    )
                    _realm_ext_info = {
                        "node_id": _dest_ext_nid,
                        "location": _dest_ext_loc,
                        "from_realm": (_ext_r_node or {}).get("name") or "the hostile realm",
                    }
            except (NameError, UnboundLocalError, ImportError, TypeError):
                raise
            except Exception:
                _realm_ext_info = {}

        if all_downed and _realm_ext_info:
            session["nearby_enemies"] = []
            llm_outcome["nearby_enemies"] = []
            cleanup_anomalous_combat_session_state(session)
            llm_outcome["combat_threat_ledger"] = {}
            llm_outcome["combat_boss_telegraph"] = {}
            if _realm_ext_info.get("location"):
                session["current_location"] = _realm_ext_info["location"]
                llm_outcome["location"] = _realm_ext_info["location"]
            if _realm_ext_info.get("node_id"):
                session["current_node_id"] = _realm_ext_info["node_id"]
                llm_outcome["current_node_id"] = _realm_ext_info["node_id"]
            session["focal_point"] = ""
            llm_outcome["focal_point"] = ""
            from mechanics.world.locations.realms import get_node_realm_in_memory, get_realm_rules
            _dest_ext_r = (
                get_node_realm_in_memory(str(_realm_ext_info["node_id"]), _nmap_post)
                if _realm_ext_info.get("node_id") and _nmap_post
                else None
            )
            _clear_waiting = not bool(get_realm_rules(_dest_ext_r).get("restrict_companions")) if _dest_ext_r else True
            if _clear_waiting:
                session["waiting_outside_companions"] = []
            llm_outcome["_realm_extracted"] = True
            for p_entry in party:
                char = p_entry[0] if isinstance(p_entry, (tuple, list)) and len(p_entry) > 0 else (p_entry if isinstance(p_entry, dict) else {})
                uid = char.get("user_id")
                max_hp = int(char.get("max_hp") or 30)
                revive_hp = max(1, max_hp // 2)
                cur_hp = int(char.get("hp") or 0)
                matching_co = next((co for co in llm_outcome.get("character_outcomes", []) if isinstance(co, dict) and co.get("name", "").lower() == char.get("name", "").lower()), None)
                if matching_co:
                    matching_co["hp_change"] = revive_hp - cur_hp
                    matching_co["status_effects"] = ["Extracted / Recovering"]
                else:
                    llm_outcome.setdefault("character_outcomes", []).append({
                        "name": char.get("name", "Traveler"),
                        "hp_change": revive_hp - cur_hp,
                        "mp_change": 0,
                        "gold_change": 0,
                        "status_effects": ["Extracted / Recovering"],
                    })
                if uid:
                    status_effects_by_uid[int(uid)] = ["Extracted / Recovering"]
            updated_npcs: list = []
            if party_npcs:
                for c in party_npcs:
                    c["hp"] = max(1, c.get("max_hp", 20) // 2)
                    c["status_effects"] = ["Extracted / Recovering"]
                    updated_npcs.append(c)
                session["current_npcs"] = updated_npcs
            if persist_db:
                with db.UnitOfWork():
                    if _realm_ext_info.get("node_id") and _realm_ext_info.get("location"):
                        upd_kw: dict[str, Any] = {
                            "current_node_id": str(_realm_ext_info["node_id"]),
                            "current_location": str(_realm_ext_info["location"]),
                            "focal_point": "",
                            "nearby_enemies": [],
                        }
                        if _clear_waiting:
                            upd_kw["extra"] = {"waiting_outside_companions": []}
                        db.update_session(session_id, **upd_kw)
                    for _se_uid, _se_vals in status_effects_by_uid.items():
                        db.set_status_effects(_se_uid, _se_vals)
                    if party_npcs:
                        db.set_session_party_npcs(session_id, updated_npcs)
            else:
                if _realm_ext_info.get("node_id") and _realm_ext_info.get("location"):
                    staged_pc_ops["rescue_node_id"] = str(_realm_ext_info["node_id"])
                    staged_pc_ops["rescue_location"] = str(_realm_ext_info["location"])
                    staged_pc_ops["clear_focal_point"] = True
                    if _clear_waiting:
                        staged_pc_ops["clear_waiting_outside_companions"] = True
                if status_effects_by_uid:
                    staged_pc_ops["status_effects_by_uid"] = status_effects_by_uid
                if party_npcs:
                    staged_pc_ops["party_npcs"] = updated_npcs
            llm_outcome["_party_defeated_notice"] = (
                f"⚠️ **Emergency Extraction!** After collapsing inside {_realm_ext_info['from_realm']}, "
                f"the threshold expelled your party back to **{_realm_ext_info['location']}**."
            )
            llm_outcome["next_choices"] = [
                {"label": "Catch your breath and inspect your wounds", "stat": "END", "requirement": 4, "mp_cost": 0},
                {"label": "Check your gear and take stock of the extraction point", "stat": "PER", "requirement": 4, "mp_cost": 0},
                {"label": "Regroup with companions before planning your next move", "stat": "CHA", "requirement": 4, "mp_cost": 0},
            ]
            llm_outcome["choices"] = llm_outcome["next_choices"]
        elif all_downed and is_anom_defeat:
            session["nearby_enemies"] = []
            llm_outcome["nearby_enemies"] = []
            cleanup_anomalous_combat_session_state(session)
            llm_outcome["combat_threat_ledger"] = {}
            llm_outcome["combat_boss_telegraph"] = {}
            lead_char = party[0][0] if (party and party[0] and isinstance(party[0][0], dict)) else {}
            lead_uid = lead_char.get("user_id") or (session.get("host_user_id") if isinstance(session, dict) else 0)
            _anom_nid = str(session.get("current_node_id") or "").strip()
            _anom_rid = ""
            _anom_rrules: dict[str, Any] = {}
            _anom_tscale = 1.0
            collapse_dynamic_realm = None
            try:
                from mechanics.world.locations.realms import (
                    collapse_dynamic_realm as _collapse_dyn,
                    get_node_realm_id,
                    get_realm_rules,
                )
                collapse_dynamic_realm = _collapse_dyn
                _anom_rid = get_node_realm_id(int(session_id or 0), _anom_nid) if (_anom_nid and session_id) else ""
                if _anom_rid:
                    _anom_rnode = db.get_world_node(int(session_id), _anom_rid)
                    _anom_rrules = get_realm_rules(_anom_rnode)
                    _anom_tscale = float(_anom_rrules.get("time_scale", 1.0))
            except Exception:
                _anom_rid = ""
                _anom_rrules = {}

            if (
                (_anom_rid == "realm_veiled_spirit_world")
                or (_anom_rid and _anom_rrules and not _anom_rrules.get("is_ephemeral") and not _anom_rrules.get("is_primary_realm") and _anom_rrules.get("has_local_safe_hub"))
                or _anom_nid.startswith((
                    "zone_spirit_", "sub_wilds_", "loc_wilds_",
                    "sub_peaks_", "loc_peaks_", "sub_mire_", "loc_mire_",
                    "sub_boneyard_", "loc_boneyard_",
                ))
            ):
                # Spirit Warden Rescue inside any of the 4 Spirit Frontier biomes: extract to Joint Ward-Stone Perimeter Camp (0g fee)
                rescue_nid = "sub_wilds_ward_camp"
                if session_id and not db.get_world_node(int(session_id), rescue_nid):
                    rescue_nid = "sub_crossroads_tea_hall"
                rescue_loc = (
                    db.format_node_tiered_location(int(session_id), rescue_nid)
                    if session_id
                    else ""
                ) or "The Weeping Bleedwood — Untamed Spirit Wilds ➔ Joint Ward-Stone Perimeter Camp ➔ Joint Frontier Ward-Stone Triage Camp"
                rescue_delta = (
                    0
                    if _anom_tscale <= 0.0
                    else (max(1, int(round(30 * _anom_tscale))) if _anom_tscale != 1.0 else 30)
                )
                if session_id:
                    c_day, c_min, c_awake = db.get_session_time(int(session_id))
                    tot_min = int(c_min) + rescue_delta
                    new_day = int(c_day) + (tot_min // 1440)
                    new_min = tot_min % 1440
                    session["current_day"] = new_day
                    session["current_minute"] = new_min
                session["current_location"] = rescue_loc
                session["current_node_id"] = rescue_nid
                llm_outcome["location"] = rescue_loc
                llm_outcome["current_node_id"] = rescue_nid
                llm_outcome["_spirit_warden_rescued"] = True
                llm_outcome["_anomalous_extracted"] = False
                llm_outcome["_authorized_gold_spend"] = 0

                for (char, _) in party:
                    uid = char.get("user_id")
                    max_hp = int(char.get("max_hp") or 30)
                    max_mp = int(char.get("max_mp") or 15)
                    revive_hp = max(1, max_hp // 2)
                    revive_mp = max(1, max_mp // 2)
                    cur_hp = int(char.get("hp") or 0)
                    cur_mp = int(char.get("mp") or 0)
                    matching_co = next(
                        (
                            co for co in llm_outcome.get("character_outcomes", [])
                            if isinstance(co, dict) and co.get("name", "").lower() == char.get("name", "").lower()
                        ),
                        None,
                    )
                    if matching_co:
                        matching_co["hp_change"] = revive_hp - cur_hp
                        matching_co["mp_change"] = max(0, revive_mp - cur_mp)
                        matching_co["status_effects"] = ["Recovering / Warden-Tended"]
                    else:
                        llm_outcome.setdefault("character_outcomes", []).append({
                            "name": char.get("name", "Operative"),
                            "hp_change": revive_hp - cur_hp,
                            "mp_change": max(0, revive_mp - cur_mp),
                            "gold_change": 0,
                            "status_effects": ["Recovering / Warden-Tended"],
                        })
                    if uid:
                        status_effects_by_uid[int(uid)] = ["Recovering / Warden-Tended"]

                updated_npcs = []
                if party_npcs:
                    for c in party_npcs:
                        c["hp"] = max(1, c.get("max_hp", 20) // 2)
                        c["status_effects"] = ["Recovering / Warden-Tended"]
                        updated_npcs.append(c)
                    session["current_npcs"] = updated_npcs

                if session_id and persist_db:
                    with db.UnitOfWork():
                        c_day, c_min, c_awake = db.get_session_time(int(session_id))
                        tot_min = int(c_min) + rescue_delta
                        new_day = int(c_day) + (tot_min // 1440)
                        new_min = tot_min % 1440
                        db.update_session_time(int(session_id), new_day, new_min, c_awake)
                        db.update_session(
                            int(session_id),
                            current_node_id=rescue_nid,
                            current_location=rescue_loc,
                            nearby_enemies=[],
                        )
                        for _se_uid, _se_vals in status_effects_by_uid.items():
                            db.set_status_effects(_se_uid, _se_vals)
                        if party_npcs:
                            db.set_session_party_npcs(session_id, updated_npcs)
                elif session_id:
                    staged_pc_ops["rescue_time_delta"] = rescue_delta
                    staged_pc_ops["rescue_node_id"] = rescue_nid
                    staged_pc_ops["rescue_location"] = rescue_loc
                    if status_effects_by_uid:
                        staged_pc_ops["status_effects_by_uid"] = status_effects_by_uid
                    if party_npcs:
                        staged_pc_ops["party_npcs"] = updated_npcs

                llm_outcome["_party_defeated_notice"] = (
                    "Joint Frontier Spirit Wardens dragged your fallen party out of the Spirit Frontier depths behind blazing "
                    "banishment flares to the Joint Ward-Stone Perimeter Camp, tending your wounds beside the brazier at no charge."
                )
                llm_outcome["next_choices"] = [
                    {"label": "Rest beside the ward-stone brazier and recover your breath", "stat": "END", "requirement": 4, "mp_cost": 0},
                    {"label": "Ask Frontier Ward-Captain about Bleedwood threat patterns", "stat": "PER", "requirement": 4, "mp_cost": 0},
                    {"label": "Walk back toward the Dusk Confluence River Tea-Pavilion", "stat": "CHA", "requirement": 4, "mp_cost": 0},
                ]
                llm_outcome["choices"] = llm_outcome["next_choices"]
            else:
                if _anom_rid and _anom_rrules.get("is_ephemeral") and not _anom_rrules.get("pacified"):
                    llm_outcome["_realm_extracted"] = True
                    if persist_db and callable(collapse_dynamic_realm):
                        try:
                            collapse_dynamic_realm(int(session_id), _anom_rid)
                        except Exception:
                            pass
                    else:
                        staged_pc_ops["collapse_realm_id"] = _anom_rid
                if persist_db:
                    try:
                        from mechanics.world.anomalous_sites import collapse_anomalous_site_on_extraction
                        collapse_anomalous_site_on_extraction(
                            int(session_id or 0),
                            str(session.get("current_node_id") or ""),
                            str(session.get("current_location") or ""),
                            int(session.get("current_day", 1) or 1),
                            len(session.get("history") or []) + 1,
                        )
                    except Exception:
                        pass
                else:
                    staged_pc_ops["collapse_anomalous_site"] = {
                        "node_id": str(session.get("current_node_id") or ""),
                        "location": str(session.get("current_location") or ""),
                        "day": int(session.get("current_day", 1) or 1),
                        "turn": len(session.get("history") or []) + 1,
                    }
                from mechanics.world.anomalous_events import resolve_anomalous_emergency_extraction
                ext = resolve_anomalous_emergency_extraction(int(session_id or 0), int(lead_uid or 0), apply_vitals_to_db=False)
                session["current_location"] = ext["destination_location"]
                session["current_node_id"] = ext["destination_node_id"]
                session["current_day"] = ext.get("new_day", session.get("current_day", 1))
                session["current_minute"] = ext.get("new_minute", session.get("current_minute", 480))
                llm_outcome["location"] = ext["destination_location"]
                llm_outcome["current_node_id"] = ext["destination_node_id"]
                llm_outcome["_anomalous_extracted"] = True
                llm_outcome["_authorized_gold_spend"] = int(ext.get("fee_paid", 0) or 0)

                for idx_p, (char, _) in enumerate(party):
                    uid = char.get("user_id")
                    max_hp = int(char.get("max_hp") or 30)
                    max_mp = int(char.get("max_mp") or 15)
                    revive_hp = max(1, max_hp // 2)
                    revive_mp = max(1, max_mp // 2)
                    cur_hp = int(char.get("hp") or 0)
                    cur_mp = int(char.get("mp") or 0)
                    fee_delta = -int(ext.get("fee_paid", 0)) if idx_p == 0 else 0
                    matching_co = next((co for co in llm_outcome.get("character_outcomes", []) if isinstance(co, dict) and co.get("name", "").lower() == char.get("name", "").lower()), None)
                    if matching_co:
                        matching_co["hp_change"] = revive_hp - cur_hp
                        matching_co["mp_change"] = max(0, revive_mp - cur_mp)
                        matching_co["gold_change"] = matching_co.get("gold_change", 0) + fee_delta
                        matching_co["status_effects"] = ["Stabilized / Triage Recovery"]
                    else:
                        llm_outcome.setdefault("character_outcomes", []).append({
                            "name": char.get("name", "Operative"),
                            "hp_change": revive_hp - cur_hp,
                            "mp_change": max(0, revive_mp - cur_mp),
                            "gold_change": fee_delta,
                            "status_effects": ["Stabilized / Triage Recovery"],
                        })
                    if uid:
                        status_effects_by_uid[int(uid)] = ["Stabilized / Triage Recovery"]

                updated_npcs = []
                if party_npcs:
                    for c in party_npcs:
                        c["hp"] = max(1, c.get("max_hp", 20) // 2)
                        c["status_effects"] = ["Stabilized / Triage Recovery"]
                        updated_npcs.append(c)
                    session["current_npcs"] = updated_npcs

                if session_id and persist_db:
                    with db.UnitOfWork():
                        for _se_uid, _se_vals in status_effects_by_uid.items():
                            db.set_status_effects(_se_uid, _se_vals)
                        if party_npcs:
                            db.set_session_party_npcs(session_id, updated_npcs)
                elif session_id:
                    if status_effects_by_uid:
                        staged_pc_ops["status_effects_by_uid"] = status_effects_by_uid
                    if party_npcs:
                        staged_pc_ops["party_npcs"] = updated_npcs

                llm_outcome["_party_defeated_notice"] = ext["narrative"]
                llm_outcome["next_choices"] = [
                    {"label": "Check medical telemetry and stabilize your psychic resonance", "stat": "END", "requirement": 4, "mp_cost": 0},
                    {"label": "Review field logs and inspect your tactical loadout", "stat": "PER", "requirement": 4, "mp_cost": 0},
                    {"label": "Debrief with triage staff before redeploying to the breach", "stat": "CHA", "requirement": 4, "mp_cost": 0},
                ]
                llm_outcome["choices"] = llm_outcome["next_choices"]
        elif all_downed:
            is_climax = any(
                e.get("is_boss") or e.get("tier_rank", 1) >= 5 or (isinstance(session, dict) and session.get("is_climax_encounter"))
                for e in (session.get("nearby_enemies") or session.get("_pre_combat_enemies") or [])
            )
            if is_climax:
                session["status"] = "finished"
                llm_outcome["is_game_over"] = True
                llm_outcome["_party_defeated_notice"] = "💀 **The Party Has Fallen!** Slain in climax battle."
                llm_outcome["next_choices"] = []
                llm_outcome["choices"] = []
            else:
                session["nearby_enemies"] = []
                llm_outcome["nearby_enemies"] = []
                cleanup_anomalous_combat_session_state(session)
                llm_outcome["combat_threat_ledger"] = {}
                llm_outcome["combat_boss_telegraph"] = {}

                for p_entry in party:
                    char = p_entry[0] if isinstance(p_entry, (tuple, list)) and len(p_entry) > 0 else (p_entry if isinstance(p_entry, dict) else {})
                    uid = char.get("user_id")
                    max_hp = int(char.get("max_hp") or 30)
                    revive_hp = max(1, max_hp // 2)
                    cur_hp = int(char.get("hp") or 0)
                    matching_co = next((co for co in llm_outcome.get("character_outcomes", []) if isinstance(co, dict) and co.get("name", "").lower() == char.get("name", "").lower()), None)
                    if matching_co:
                        matching_co["hp_change"] = revive_hp - cur_hp
                        matching_co["status_effects"] = ["Exhausted / Recovering"]
                    else:
                        llm_outcome.setdefault("character_outcomes", []).append({
                            "name": char.get("name", "Hero"),
                            "hp_change": revive_hp - cur_hp,
                            "mp_change": 0,
                            "gold_change": 0,
                            "status_effects": ["Exhausted / Recovering"],
                        })
                    if uid:
                        status_effects_by_uid[int(uid)] = ["Exhausted / Recovering"]

                updated_npcs = []
                if party_npcs:
                    for c in party_npcs:
                        c["hp"] = max(1, c.get("max_hp", 20) // 2)
                        c["status_effects"] = ["Exhausted / Recovering"]
                        updated_npcs.append(c)
                    session["current_npcs"] = updated_npcs

                if session_id and persist_db:
                    with db.UnitOfWork():
                        for _se_uid, _se_vals in status_effects_by_uid.items():
                            db.set_status_effects(_se_uid, _se_vals)
                        if party_npcs:
                            db.set_session_party_npcs(session_id, updated_npcs)
                elif session_id:
                    if status_effects_by_uid:
                        staged_pc_ops["status_effects_by_uid"] = status_effects_by_uid
                    if party_npcs:
                        staged_pc_ops["party_npcs"] = updated_npcs

                llm_outcome["_party_defeated_notice"] = "💀 **Party Defeated!** You were overwhelmed and fell in battle, but were recovered to safety. You awaken stabilized, nursing your injuries."
                llm_outcome["next_choices"] = [
                    {"label": "Rest and recuperate from your injuries", "stat": "END", "requirement": 4, "mp_cost": 0},
                    {"label": "Assess your surroundings and check equipment", "stat": "PER", "requirement": 4, "mp_cost": 0},
                    {"label": "Consult with companions about what happened", "stat": "CHA", "requirement": 4, "mp_cost": 0},
                ]
                llm_outcome["choices"] = llm_outcome["next_choices"]

    if staged_pc_ops and isinstance(llm_outcome, dict):
        llm_outcome["_staged_post_combat_ops"] = staged_pc_ops

    if not enemies and total_xp_gain > 0 and party_npcs and party and party[0]:
        scen_lvl = session.get("scenario", "fantasy") if isinstance(session, dict) else "fantasy"
        is_anom_lvl = bool(isinstance(session, dict) and scenario_data.is_anomalous_incursions_scenario(scen_lvl))
        p_lvl = party[0][0].get("level", 1)
        updated_npcs = []
        for c in party_npcs:
            c_lvl = max(c.get("level", 1), p_lvl)
            c["level"] = c_lvl
            if is_anom_lvl and c.get("anomalous_npc_tag") == "special_agent":
                from mechanics.social.anomalous_npc_tags import compute_special_agent_combat_stats
                scaled_st = compute_special_agent_combat_stats(
                    agent_tier=int(c.get("agent_tier", 1) or 1),
                    player_level=c_lvl,
                    agent_class=str(c.get("agent_class") or ""),
                    faction_id=str(c.get("faction_id") or ""),
                    is_party_companion=True,
                    seed_str=f"{session_id}:{str(c.get('name') or '').lower()}",
                )
                c["max_hp"] = scaled_st["max_hp"]
                c["max_mp"] = scaled_st["max_mp"]
                c["stats"] = scaled_st["stats"]
            else:
                if not isinstance(c.get("stats"), dict) or not c.get("stats"):
                    c["stats"] = build_combatant_stat_sheet(c_lvl, c.get("archetype", "Companion"), role_tier="companion")
                is_civ = str(c.get("anomalous_npc_tag") or "").strip().lower() == "civilian"
                c_max_hp, c_max_mp = compute_companion_vitals(c_lvl, c.get("stats"), is_civilian=is_civ)
                c["max_hp"] = c_max_hp
                c["max_mp"] = c_max_mp
            reset_combatant_cooldowns(c)
            c["hp"] = min(c.get("hp", c["max_hp"]), c["max_hp"])
            c["mp"] = min(c.get("mp", c["max_mp"]), c["max_mp"])
            updated_npcs.append(c)
        if isinstance(session, dict):
            session["party_npcs"] = updated_npcs
        llm_outcome["party_npcs"] = updated_npcs
        db.set_session_party_npcs(session_id, updated_npcs)

    try:
        if not enemies:
            session["combat_threat_ledger"] = {}
            session["combat_boss_telegraph"] = {}
            llm_outcome["combat_threat_ledger"] = {}
            llm_outcome["combat_boss_telegraph"] = {}
            for p_comp in (party_npcs or []):
                if isinstance(p_comp, dict):
                    reset_combatant_cooldowns(p_comp)
            if session_id and party_npcs and total_xp_gain <= 0:
                session["party_npcs"] = party_npcs
                llm_outcome["party_npcs"] = party_npcs
                db.set_session_party_npcs(session_id, party_npcs)
            cleanup_anomalous_combat_session_state(session)
        else:
            dead_eids: Set[str] = set()
            for d in (dead_enemies or []):
                if isinstance(d, dict):
                    for k in ("id", "name"):
                        v = d.get(k)
                        if v:
                            dead_eids.add(str(v))
                elif d:
                    dead_eids.add(str(d))
            for d in (dead_enemy_dicts_rec or []):
                if isinstance(d, dict):
                    for k in ("id", "name"):
                        v = d.get(k)
                        if v:
                            dead_eids.add(str(v))

            raw_telegraph = session.get("combat_boss_telegraph")
            if isinstance(raw_telegraph, dict):
                for eid in list(raw_telegraph.keys()):
                    if eid in dead_eids:
                        raw_telegraph.pop(eid, None)
                session["combat_boss_telegraph"] = raw_telegraph
                llm_outcome["combat_boss_telegraph"] = raw_telegraph

            raw_ledger = session.get("combat_threat_ledger")
            if isinstance(raw_ledger, dict):
                matrix = raw_ledger.get("threat_matrix", raw_ledger)
                if isinstance(matrix, dict):
                    for eid in list(matrix.keys()):
                        if eid in dead_eids:
                            matrix.pop(eid, None)
                sticky = raw_ledger.get("sticky_taunts")
                if isinstance(sticky, dict):
                    for eid in list(sticky.keys()):
                        if eid in dead_eids:
                            sticky.pop(eid, None)

                downed_ids: Set[str] = set()

                def _cand_actor_keys(a: Dict[str, Any]) -> Set[str]:
                    keys: Set[str] = set()
                    for k in ("name", "id", "user_id", "npc_id"):
                        val = a.get(k)
                        if val is not None:
                            s_val = str(val).strip()
                            if s_val and s_val.lower() != "none":
                                keys.add(s_val)
                    return keys

                for p in (party or []):
                    p_obj = p[0] if isinstance(p, (tuple, list)) else p
                    if isinstance(p_obj, dict):
                        p_hp = p_obj.get("hp")
                        if p_hp is not None and int(p_hp) <= 0:
                            downed_ids.update(_cand_actor_keys(p_obj))
                for npc in (session.get("party_npcs") or []):
                    if isinstance(npc, dict):
                        n_hp = npc.get("hp")
                        if n_hp is not None and int(n_hp) <= 0:
                            downed_ids.update(_cand_actor_keys(npc))
                for comp in (session.get("temporary_companions") or []):
                    if isinstance(comp, dict):
                        c_hp = comp.get("hp")
                        if c_hp is not None and int(c_hp) <= 0:
                            downed_ids.update(_cand_actor_keys(comp))
                decay_round_threat(raw_ledger, downed_ids)
                session["combat_threat_ledger"] = raw_ledger
                llm_outcome["combat_threat_ledger"] = raw_ledger
    except Exception as _th_err:
        logger.debug("Threat decay failed: %s", _th_err)
