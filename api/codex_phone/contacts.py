from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from fastapi import APIRouter, Query, Request

import db
from db import adb
import mechanics.social.relationships
from ..security import verify_session_participant
from .common import (
    _get_contacts_ro,
    _infer_school_grade_badge,
    _verify_missing_session_codex_auth,
)

router = APIRouter()


def _index_npc_records(
    rows: list[dict[str, Any]] | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_key: dict[str, dict[str, Any]] = {}
    by_name_low: dict[str, dict[str, Any]] = {}
    for row in (rows or []):
        if not isinstance(row, dict):
            continue
        for raw_k in (row.get("npc_key"), row.get("npc_id"), row.get("name")):
            s_val = str(raw_k or "").strip()
            if not s_val:
                continue
            by_key.setdefault(s_val.lower(), row)
            canon_k = db.canon_social_npc_id(s_val)
            if canon_k:
                by_key.setdefault(canon_k, row)
        nm_low = str(row.get("name") or "").strip().lower()
        if nm_low:
            by_name_low.setdefault(nm_low, row)
    return by_key, by_name_low


def _extract_player_last_name(session_id: int, character_id: int) -> str:
    p_name = ""
    if character_id:
        try:
            char_row = db.get_character_by_id(int(character_id))
            p_name = str((char_row or {}).get("name") or "").strip()
        except (sqlite3.Error, AttributeError, TypeError, ValueError):
            p_name = ""
    if not p_name and session_id:
        try:
            sess_row = db.get_session(int(session_id))
            sess_cid = int((sess_row or {}).get("character_id") or 0)
            if sess_cid and sess_cid != character_id:
                char_row = db.get_character_by_id(sess_cid)
                p_name = str((char_row or {}).get("name") or "").strip()
        except (sqlite3.Error, AttributeError, TypeError, ValueError):
            p_name = ""
    parts = [p for p in p_name.split() if p]
    return parts[-1] if parts else ""


def _preload_fog_of_war_context(
    session_id: int,
    character_id: int,
    party_names: set[str] | None = None,
    lang: str = "en",
    preloaded_contacts: list[dict[str, Any]] | None = None,
    preloaded_party_npcs: list[dict[str, Any]] | None = None,
    scen_key: str = "",
    preloaded_session: dict[str, Any] | None = None,
    preloaded_player_char: dict[str, Any] | None = None,
    request_user_id: int = 0,
) -> dict:
    """Batch-loads dossier, roster, node, property, tie, and exemption context in O(1) queries."""
    import mechanics.social.relationship_graph as rg

    cid = int(character_id or 0)
    sid = int(session_id or 0)
    eff_session: dict[str, Any] | None = dict(preloaded_session) if isinstance(preloaded_session, dict) else None
    try:
        disc_by_npc = db.get_contact_dossier_discoveries_batch(sid, cid) if sid else {}
    except (sqlite3.Error, AttributeError, TypeError, ValueError):
        disc_by_npc = {}
    try:
        ex_sets = db.get_player_fow_exemption_sets(sid) if sid else {}
    except (sqlite3.Error, AttributeError, TypeError, ValueError):
        ex_sets = {}

    party_npc_keys = set((ex_sets or {}).get("party_npc_keys") or set()) | {
        db.canon_social_npc_id(n) for n in (party_names or set()) if str(n).strip()
    }
    kin_npc_keys = set((ex_sets or {}).get("kin_npc_keys") or set())
    romantic_npc_keys = set((ex_sets or {}).get("romantic_npc_keys") or set())

    nodes_by_id: dict[str, dict[str, Any]] = {}
    roster_rows: list[dict[str, Any]] = []
    primary_property: dict[str, Any] | None = None
    person_ties: list[dict[str, Any]] = []
    active_ties_by_person: dict[str, list[dict[str, Any]]] = {}
    active_events: list[dict[str, Any]] = []
    eff_contacts: list[dict[str, Any]] = list(preloaded_contacts or []) if preloaded_contacts is not None else []
    eff_party_npcs: list[dict[str, Any]] = list(preloaded_party_npcs or []) if preloaded_party_npcs is not None else []
    player_last_name = ""
    faction_state: dict[str, Any] | None = None
    anomalous_agent_roster: list[dict[str, Any]] | None = None

    if sid:
        try:
            raw_nodes = db.get_session_world_nodes(sid) or []
            nodes_by_id = {
                str(n["node_id"]): n
                for n in raw_nodes
                if isinstance(n, dict) and n.get("node_id")
            }
        except (sqlite3.Error, AttributeError, TypeError, ValueError):
            nodes_by_id = {}
        try:
            roster_rows = [
                r for r in (db.get_world_roster(sid, include_legacy_rosters=True) or []) if isinstance(r, dict)
            ]
        except (sqlite3.Error, AttributeError, TypeError, ValueError):
            roster_rows = []
        try:
            prop = db.get_primary_property(sid)
            primary_property = dict(prop) if isinstance(prop, dict) else None
        except (sqlite3.Error, AttributeError, TypeError, ValueError):
            primary_property = None
        try:
            t_rows = db.get_session_active_social_ties(sid)
            for tr in t_rows:
                td = dict(tr)
                pa = str(td.get("person_a_key") or "").strip().lower()
                pb = str(td.get("person_b_key") or "").strip().lower()
                if pa:
                    active_ties_by_person.setdefault(pa, []).append(td)
                if pb and pb != pa:
                    active_ties_by_person.setdefault(pb, []).append(td)
                if pa == "player" or pb == "player" or pa.startswith("player:") or pb.startswith("player:"):
                    person_ties.append(td)
        except (sqlite3.Error, AttributeError, TypeError, ValueError):
            active_ties_by_person = {}
            try:
                if hasattr(rg, "get_person_ties"):
                    person_ties = rg.get_person_ties(sid, "player") or []
                elif hasattr(rg, "get_ties"):
                    person_ties = rg.get_ties(sid, "player") or []
            except (sqlite3.Error, AttributeError, TypeError, ValueError):
                person_ties = []
        try:
            active_events = [
                ev for ev in (db.get_world_events(sid, entity_type="macro_event") or []) if isinstance(ev, dict)
            ]
        except (sqlite3.Error, AttributeError, TypeError, ValueError):
            active_events = []
        if preloaded_contacts is None:
            try:
                eff_contacts = (
                    mechanics.social.relationships.safe_get_contacts(
                        sid, cid or None, resolve_relations=False, ensure_scene=False
                    )
                    or []
                )
            except (sqlite3.Error, AttributeError, TypeError, ValueError):
                eff_contacts = []
        if preloaded_party_npcs is None:
            try:
                eff_party_npcs = db.get_session_party_npcs(sid) or []
            except (sqlite3.Error, AttributeError, TypeError, ValueError):
                eff_party_npcs = []
        if eff_session is None:
            try:
                s_row = db.get_session(sid)
                eff_session = dict(s_row) if isinstance(s_row, dict) else s_row
            except (sqlite3.Error, AttributeError, TypeError, ValueError):
                eff_session = None
        player_last_name = _extract_player_last_name(sid, cid)
        if eff_session is not None:
            raw_ar = eff_session.get("anomalous_agent_roster") or (
                eff_session.get("extra", {}).get("anomalous_agent_roster")
                if isinstance(eff_session.get("extra"), dict)
                else None
            )
            anomalous_agent_roster = [a for a in raw_ar if isinstance(a, dict)] if isinstance(raw_ar, list) else []
        if scen_key:
            try:
                from scenario_data import is_anomalous_incursions_scenario

                if is_anomalous_incursions_scenario(scen_key):
                    raw_af = (eff_session or {}).get("anomalous_faction_state") if isinstance(eff_session, dict) else None
                    if isinstance(raw_af, dict) and raw_af:
                        faction_state = dict(raw_af)
                    else:
                        st_fid = (
                            str((eff_session or {}).get("starting_faction_id") or "").strip().lower()
                            if isinstance(eff_session, dict)
                            else ""
                        )
                        faction_state = {"faction_archetype_key": st_fid} if st_fid else {}
            except (sqlite3.Error, AttributeError, TypeError, ValueError):
                faction_state = None

    roster_by_key, roster_by_name_low = _index_npc_records(roster_rows)
    contacts_by_key, contacts_by_name_low = _index_npc_records(eff_contacts)

    current_day: int | None = None
    current_minute: int | None = None
    if isinstance(eff_session, dict):
        if eff_session.get("current_day") is not None:
            current_day = int(eff_session.get("current_day") or 1)
        if eff_session.get("current_minute") is not None:
            current_minute = int(eff_session.get("current_minute"))
    elif sid:
        try:
            db_day, db_min, _ = db.get_session_time(sid)
            current_day = int(db_day or 1)
            current_minute = int(db_min) if db_min is not None else None
        except (sqlite3.Error, AttributeError, TypeError, ValueError):
            pass
    player_home_node_id = str(
        (primary_property or {}).get("node_id")
        or (eff_session.get("player_home_node_id") if isinstance(eff_session, dict) else "")
        or ""
    ).strip()

    eff_player_char: dict[str, Any] | None = dict(preloaded_player_char) if isinstance(preloaded_player_char, dict) else None
    if eff_player_char is None and (cid > 0 or sid > 0 or request_user_id or (isinstance(eff_session, dict) and eff_session.get("host_user_id"))):
        try:
            _pc_row = mechanics.social.relationships.resolve_session_player_character(
                session_id=sid,
                character_id=cid,
                user_id=int(request_user_id or 0),
                session=eff_session,
            )
            if isinstance(_pc_row, dict):
                eff_player_char = dict(_pc_row)
        except (sqlite3.Error, AttributeError, TypeError, ValueError):
            eff_player_char = None

    return {
        "character_id": cid,
        "lang": str(lang or "en"),
        "session": eff_session,
        "player_char": eff_player_char,
        "disc_by_npc": disc_by_npc,
        "party_npc_keys": party_npc_keys,
        "kin_npc_keys": kin_npc_keys,
        "romantic_npc_keys": romantic_npc_keys,
        "nodes_by_id": nodes_by_id,
        "roster_rows": roster_rows,
        "roster_by_key": roster_by_key,
        "roster_by_name_low": roster_by_name_low,
        "primary_property": primary_property,
        "contacts": eff_contacts,
        "contacts_by_key": contacts_by_key,
        "contacts_by_name_low": contacts_by_name_low,
        "person_ties": person_ties,
        "active_ties_by_person": active_ties_by_person,
        "active_events": active_events,
        "current_day": current_day,
        "current_minute": current_minute,
        "player_home_node_id": player_home_node_id,
        "player_last_name": player_last_name,
        "household_cache": {},
        "party_npcs": eff_party_npcs,
        "faction_state": faction_state,
        "anomalous_agent_roster": anomalous_agent_roster if sid else None,
        "preloaded": True,
    }


def _lookup_indexed_npc(
    fow_context: dict,
    by_key_field: str,
    by_name_field: str,
    c_in: dict,
) -> dict | None:
    by_key = fow_context.get(by_key_field) or {}
    by_name_low = fow_context.get(by_name_field) or {}
    for cand in (c_in.get("npc_key"), c_in.get("npc_id"), c_in.get("name")):
        s_val = str(cand or "").strip()
        if not s_val:
            continue
        hit = by_key.get(db.canon_social_npc_id(s_val)) or by_key.get(s_val.lower())
        if isinstance(hit, dict):
            return hit
    nm_low = str(c_in.get("name") or "").strip().lower()
    if nm_low and isinstance(by_name_low.get(nm_low), dict):
        return by_name_low[nm_low]
    return None


def _resolve_faction_affiliation(res: dict) -> str:
    """Returns the NPC's faction/agency affiliation, never echoing the school club as a faction."""
    b_inf = res.get("basic_info") if isinstance(res.get("basic_info"), dict) else {}
    if res.get("is_citizen") and not res.get("is_special_agent") and str(b_inf.get("club_role") or "").lower().startswith("club "):
        return ""
    club_low = str(res.get("club") or b_inf.get("club") or "").strip().lower()
    for cand in (
        res.get("faction_name"),
        b_inf.get("faction_name"),
        b_inf.get("faction"),
        res.get("faction"),
        b_inf.get("affiliation"),
        res.get("affiliation"),
    ):
        val = str(cand or "").strip()
        if val and val.lower() not in ("none", "unaffiliated", "unknown") and val.lower() != club_low:
            return val
    return ""


def _enrich_contact_record(
    c_raw: dict,
    session_id: int,
    scen_key: str,
    debug_reveal_all: bool,
    phys_st: dict | None = None,
    party_names: set[str] | None = None,
    fow_context: dict | None = None,
) -> dict:
    from mechanics.social.relationships import enrich_contact_dossier
    from mechanics.social.roster_tags import resolve_character_badges
    from mechanics.world.routine_disclosure import (
        apply_known_routine_to_contact,
        build_known_routine_payload,
    )

    c_in = dict(c_raw or {})
    preloaded_disc = None
    fow_lang = "en"
    fow_char_id = int(c_in.get("character_id") or 0)
    party_keys = None
    kin_keys = None
    rom_keys = None
    is_fow_preloaded = False
    preloaded_party_npcs = None
    preloaded_faction_state = None
    preloaded_agent_roster = None
    preloaded_session = None
    preloaded_player_char = None
    if isinstance(fow_context, dict):
        is_fow_preloaded = bool(fow_context.get("preloaded"))
        if fow_context.get("character_id") and not c_in.get("character_id"):
            fow_char_id = int(fow_context["character_id"])
            c_in["character_id"] = fow_char_id
        fow_lang = str(fow_context.get("lang") or "en")
        canon_nid = db.canon_social_npc_id(c_in.get("npc_id") or c_in.get("name") or "")
        canon_name = db.canon_social_npc_id(c_in.get("name") or "")
        disc_map = fow_context.get("disc_by_npc")
        if isinstance(disc_map, dict):
            preloaded_disc = disc_map.get(canon_nid)
            if preloaded_disc is None and canon_name:
                preloaded_disc = disc_map.get(canon_name)
            if preloaded_disc is None:
                preloaded_disc = []
        party_keys = fow_context.get("party_npc_keys")
        kin_keys = fow_context.get("kin_npc_keys")
        rom_keys = fow_context.get("romantic_npc_keys")
        preloaded_party_npcs = fow_context.get("party_npcs")
        preloaded_faction_state = fow_context.get("faction_state")
        preloaded_agent_roster = fow_context.get("anomalous_agent_roster")
        preloaded_session = fow_context.get("session")
        preloaded_player_char = fow_context.get("player_char")

    res = enrich_contact_dossier(
        c_in,
        session_id,
        scen_key,
        debug_reveal_all=debug_reveal_all,
        phys_st=phys_st,
        preloaded_discoveries=preloaded_disc,
        lang=fow_lang,
        party_npc_keys=party_keys,
        kin_npc_keys=kin_keys,
        romantic_npc_keys=rom_keys,
        read_only=is_fow_preloaded,
        preloaded_party_npcs=preloaded_party_npcs,
        preloaded_faction_state=preloaded_faction_state,
        preloaded_agent_roster=preloaded_agent_roster,
        preloaded_session=preloaded_session,
        player_char=preloaded_player_char,
    )
    if not res.get("grade"):
        b_inf = res.get("basic_info") or {}
        raw_g = b_inf.get("grade") if isinstance(b_inf, dict) else ""
        inferred = _infer_school_grade_badge(res.get("role") or "", raw_g, scen_key)
        if inferred:
            res["grade"] = inferred

    is_acq_row = str(c_in.get("tier_status") or "").strip().lower() == "acquaintance"
    c_badges = resolve_character_badges(
        res,
        scen_key=scen_key,
        party_names=party_names,
        is_contact=not is_acq_row,
        is_blocked=bool(res.get("is_blocked")),
    )
    res["standing"] = c_badges.standing
    res["age_group"] = c_badges.age_group
    res["badges"] = c_badges.badges
    res["is_student"] = c_badges.is_student
    res["is_faculty"] = c_badges.is_faculty
    res["is_staff"] = c_badges.is_staff
    res["is_citizen"] = c_badges.is_citizen
    res["is_merchant"] = c_badges.is_merchant
    res["is_special_agent"] = c_badges.is_special_agent

    if not res.get("is_student"):
        res["club"] = ""
        if isinstance(res.get("basic_info"), dict):
            res["basic_info"]["club"] = ""
        cur_r = str(res.get("role") or (res.get("basic_info") or {}).get("role") or "").strip()
        if cur_r.lower() in (
            "club member",
            "club officer",
            "club vice president",
            "club secretary",
            "club treasurer",
            "events coordinator",
        ):
            desc_str = str(res.get("description") or (res.get("basic_info") or {}).get("description") or "")
            m_p = re.search(r"\(([^)]{3,45})\)", desc_str)
            healed_role = (
                m_p.group(1).strip()
                if (m_p and not any(k in m_p.group(1).lower() for k in ("née", "nee", "formerly")))
                else "Citizen"
            )
            res["role"] = healed_role
            res["public_role"] = healed_role
            if isinstance(res.get("basic_info"), dict):
                res["basic_info"]["role"] = healed_role
                res["basic_info"]["public_role"] = healed_role
                res["basic_info"].pop("club_role", None)
                if res.get("is_citizen") and not res.get("is_special_agent"):
                    res["basic_info"].pop("faction", None)
                    res.pop("faction", None)

    res["faction_affiliation"] = _resolve_faction_affiliation(res)

    if is_fow_preloaded and isinstance(fow_context, dict):
        matched_roster = _lookup_indexed_npc(fow_context, "roster_by_key", "roster_by_name_low", c_in)
        matched_contact = _lookup_indexed_npc(fow_context, "contacts_by_key", "contacts_by_name_low", c_in)
        eff_contact_row = None if (is_acq_row and matched_contact is None) else (matched_contact or c_in)
        known_routine = build_known_routine_payload(
            res,
            session_id=session_id,
            scen_key=scen_key,
            lang=fow_lang,
            debug_reveal_all=debug_reveal_all,
            nodes_by_id=fow_context.get("nodes_by_id"),
            roster_row=matched_roster,
            contact_row=eff_contact_row,
            primary_property=fow_context.get("primary_property"),
            contacts=fow_context.get("contacts"),
            person_ties=fow_context.get("person_ties"),
            household_cache=fow_context.get("household_cache"),
            player_last_name=fow_context.get("player_last_name"),
            party_npc_keys=party_keys,
            kin_npc_keys=kin_keys,
            romantic_npc_keys=rom_keys,
            discovered_dossier_rows=preloaded_disc if preloaded_disc is not None else [],
            character_id=fow_char_id,
            preloaded=True,
            fow_schedule_revealed=bool(res.get("schedule_revealed")),
            current_day=fow_context.get("current_day"),
            current_minute=fow_context.get("current_minute"),
            active_ties_by_person=fow_context.get("active_ties_by_person"),
            roster_by_key=fow_context.get("roster_by_key"),
            active_events=fow_context.get("active_events") or (),
            player_home_node_id=str(fow_context.get("player_home_node_id") or ""),
        )
    else:
        known_routine = build_known_routine_payload(
            res,
            session_id=session_id,
            scen_key=scen_key,
            lang=fow_lang,
            debug_reveal_all=debug_reveal_all,
            roster_row=c_in if is_acq_row else None,
            contact_row=None if is_acq_row else c_in,
            party_npc_keys=party_keys,
            kin_npc_keys=kin_keys,
            romantic_npc_keys=rom_keys,
            discovered_dossier_rows=preloaded_disc,
            character_id=fow_char_id,
            fow_schedule_revealed=bool(res.get("schedule_revealed")),
        )

    apply_known_routine_to_contact(res, known_routine, lang=fow_lang)
    return res


def _build_acquaintance_input_dict(
    row: dict[str, Any],
    session_id: int,
    nodes_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    raw_basic = row.get("basic_info")
    if isinstance(raw_basic, str) and raw_basic.strip():
        try:
            raw_basic = json.loads(raw_basic)
        except (TypeError, ValueError):
            raw_basic = {}
    r_basic = dict(raw_basic) if isinstance(raw_basic, dict) else {}

    raw_app = row.get("appearance")
    if isinstance(raw_app, str) and raw_app.strip():
        try:
            raw_app = json.loads(raw_app)
        except (TypeError, ValueError):
            raw_app = {}
    r_app = dict(raw_app) if isinstance(raw_app, dict) else {}

    raw_traits = row.get("traits")
    if isinstance(raw_traits, str) and raw_traits.strip():
        try:
            raw_traits = json.loads(raw_traits)
        except (TypeError, ValueError):
            raw_traits = []
    traits_list = list(raw_traits) if isinstance(raw_traits, list) else []

    raw_slots = row.get("discovered_slots")
    if not raw_slots and isinstance(row.get("discovered_slots_json"), str) and row["discovered_slots_json"].strip():
        try:
            raw_slots = json.loads(row["discovered_slots_json"])
        except (TypeError, ValueError):
            raw_slots = {}
    slots_dict = dict(raw_slots) if isinstance(raw_slots, dict) else {}

    npc_id = str(row.get("npc_id") or row.get("npc_key") or db.canon_social_npc_id(row.get("name") or "")).strip()
    npc_key = str(row.get("npc_key") or db.canon_social_npc_id(npc_id or row.get("name") or "")).strip()
    score = int(row.get("affinity_score") or 0)
    work_nid = str(row.get("workplace_node_id") or r_basic.get("workplace_node_id") or "").strip()
    work_node = nodes_by_id.get(work_nid) if work_nid else None
    work_label = str(
        (work_node or {}).get("name")
        or r_basic.get("workplace_label")
        or r_basic.get("workplace")
        or r_basic.get("primary_facility")
        or ""
    ).strip()

    return {
        "id": f"acq_{npc_key or db.canon_social_npc_id(row.get('name') or 'npc')}",
        "session_id": session_id,
        "npc_id": npc_id,
        "npc_key": npc_key,
        "name": str(row.get("name") or r_basic.get("name") or "Unknown").strip(),
        "role": str(row.get("role") or r_basic.get("role") or "").strip(),
        "gender": str(row.get("gender") or r_basic.get("gender") or "").strip(),
        "race": str(row.get("race") or r_basic.get("race") or "human").strip(),
        "tier_status": "acquaintance",
        "origin": str(row.get("origin") or "").strip(),
        "affinity_score": score,
        "relationship_score": score,
        "first_met_turn": int(row.get("first_met_turn") or 0),
        "met_in_person": bool(row.get("met_in_person", 1)),
        "staff_status": str(row.get("staff_status") or "active").strip(),
        "workplace_node_id": work_nid,
        "workplace_label": work_label,
        "home_node_id": str(row.get("home_node_id") or "").strip(),
        "hangout_node_id": str(row.get("hangout_node_id") or "").strip(),
        "shift_profile": str(row.get("shift_profile") or "").strip(),
        "residence_unlocked": bool(row.get("residence_unlocked")),
        "discovered_slots": slots_dict,
        "has_contact_info": bool(r_basic.get("has_contact_info") is True),
        "basic_info": r_basic,
        "appearance": r_app,
        "traits": traits_list,
        "unlocked_traits": list(traits_list),
    }


def _collect_contact_identity_keys(rows: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for c in rows:
        if not isinstance(c, dict):
            continue
        for raw_k in (c.get("npc_key"), c.get("npc_id"), c.get("name")):
            s_val = str(raw_k or "").strip()
            if not s_val:
                continue
            keys.add(s_val.lower())
            canon_k = db.canon_social_npc_id(s_val)
            if canon_k:
                keys.add(canon_k)
    return keys


def _build_contacts_and_acquaintances_payload(
    session_id: int,
    char_id: int,
    scen_key: str,
    debug_reveal_all: bool,
    phys_st: dict | None,
    party_npcs: list[dict] | None,
    party_names: set[str],
    ui_lang: str,
    contacts: list[dict[str, Any]],
    unlocked_raw: list[dict[str, Any]],
    preloaded_session: dict[str, Any] | None = None,
    preloaded_player_char: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from mechanics.social.relationships import can_player_dm_contact, get_relationship_tier

    fow = _preload_fog_of_war_context(
        session_id,
        char_id,
        party_names,
        ui_lang,
        preloaded_contacts=contacts,
        preloaded_party_npcs=party_npcs,
        scen_key=scen_key,
        preloaded_session=preloaded_session,
        preloaded_player_char=preloaded_player_char,
    )
    enriched_contacts = [
        {
            **_enrich_contact_record(
                c,
                session_id,
                scen_key,
                debug_reveal_all,
                phys_st=phys_st,
                party_names=party_names,
                fow_context=fow,
            ),
            "can_dm": can_player_dm_contact(
                c,
                party_names=party_names,
                scenario=scen_key,
                preloaded_session=fow.get("session"),
                skip_session_lookup=True,
            ),
        }
        for c in unlocked_raw
    ]

    contact_keys = _collect_contact_identity_keys(list(contacts or []) + list(unlocked_raw or []))
    nodes_by_id = fow.get("nodes_by_id") or {}
    seen_acq_keys: set[str] = set()
    enriched_acquaintances: list[dict[str, Any]] = []

    for r in (fow.get("roster_rows") or []):
        if not isinstance(r, dict):
            continue
        if str(r.get("tier_status") or "").strip().lower() != "acquaintance":
            continue
        r_keys: set[str] = set()
        for raw_k in (r.get("npc_key"), r.get("npc_id"), r.get("name")):
            s_val = str(raw_k or "").strip()
            if not s_val:
                continue
            r_keys.add(s_val.lower())
            canon_k = db.canon_social_npc_id(s_val)
            if canon_k:
                r_keys.add(canon_k)
        if not r_keys or (r_keys & contact_keys) or (r_keys & seen_acq_keys):
            continue
        seen_acq_keys.update(r_keys)

        acq_in = _build_acquaintance_input_dict(r, session_id, nodes_by_id)
        acq_enriched = _enrich_contact_record(
            acq_in,
            session_id,
            scen_key,
            debug_reveal_all,
            phys_st=phys_st,
            party_names=party_names,
            fow_context=fow,
        )
        score = int(acq_in["affinity_score"])
        tier_obj = get_relationship_tier(
            score,
            track=str(acq_enriched.get("track") or "platonic"),
            scenario=scen_key,
        )
        acq_enriched["npc_id"] = str(acq_enriched.get("npc_id") or acq_in["npc_id"])
        acq_enriched["npc_key"] = acq_in["npc_key"]
        acq_enriched["tier_status"] = "acquaintance"
        acq_enriched["origin"] = acq_in["origin"]
        acq_enriched["affinity_score"] = score
        acq_enriched["relationship_score"] = score
        acq_enriched["relationship_tier"] = str(
            (tier_obj or {}).get("name") or acq_enriched.get("standing") or "Acquaintance"
        )
        acq_enriched["first_met_turn"] = acq_in["first_met_turn"]
        acq_enriched["staff_status"] = acq_in["staff_status"]
        acq_enriched["workplace_label"] = acq_in["workplace_label"]
        acq_enriched["can_dm"] = False
        enriched_acquaintances.append(acq_enriched)

    enriched_acquaintances.sort(
        key=lambda a: (
            -int(a.get("affinity_score") or 0),
            -int(a.get("first_met_turn") or 0),
            str(a.get("name") or "").lower(),
        )
    )
    return enriched_contacts, enriched_acquaintances


@router.get("/api/contacts/{session_id}")
async def get_contacts(session_id: int, user_id: int | None = Query(None), request: Request = None):
    """Fetches NPC contacts and met acquaintances with progressive routine disclosure."""
    user_id = user_id if isinstance(user_id, (int, str)) and not isinstance(user_id, bool) else None
    raw_sess = await adb(db.get_session, session_id)
    if raw_sess:
        await verify_session_participant(request, session_id, user_id, session=raw_sess)
    else:
        await _verify_missing_session_codex_auth(request, user_id)
    session = raw_sess or {}
    scen_key = session.get("scenario", "fantasy")
    phys_st = session.get("physical_state") if isinstance(session.get("physical_state"), dict) else None
    valid_uid = (
        user_id
        if isinstance(user_id, int)
        else (int(user_id) if isinstance(user_id, str) and user_id.isdigit() else None)
    )
    lookup_uid = valid_uid or session.get("host_user_id") or 0
    settings = await adb(db.get_settings, lookup_uid) if lookup_uid else {}
    debug_reveal_all = bool((settings or {}).get("debug_reveal_all_info", 0))
    from scenario_data import is_nsfw_scenario

    char_row = await adb(db.get_character, lookup_uid, session_id=session_id) if lookup_uid else None
    char_id = char_row.get("id", 0) if char_row else 0
    contacts = await _get_contacts_ro(session_id, char_id)
    if not contacts and lookup_uid and char_id != lookup_uid:
        contacts = await _get_contacts_ro(session_id, lookup_uid)
    from mechanics.social.relationships import collect_met_npc_names, is_unlocked_contact

    party_npcs = await adb(db.get_session_party_npcs, session_id)
    party_names = {str(p.get("name", "")).strip().lower() for p in (party_npcs or [])}
    met_names = collect_met_npc_names(session, party_npcs=party_npcs)

    unlocked_raw = [
        c
        for c in (contacts or [])
        if is_unlocked_contact(
            c,
            party_names,
            met_in_story_names=met_names,
            preloaded_session=session,
            skip_session_lookup=True,
        )
    ]
    ui_lang = str((settings or {}).get("ui_language") or "en")
    enriched_contacts, enriched_acquaintances = await adb(
        _build_contacts_and_acquaintances_payload,
        session_id,
        char_id,
        scen_key,
        debug_reveal_all,
        phys_st,
        party_npcs,
        party_names,
        ui_lang,
        contacts,
        unlocked_raw,
        preloaded_session=session,
        preloaded_player_char=char_row,
    )
    return {
        "contacts": enriched_contacts,
        "acquaintances": enriched_acquaintances,
        "is_nsfw": is_nsfw_scenario(scen_key),
        "scenario": scen_key,
    }
