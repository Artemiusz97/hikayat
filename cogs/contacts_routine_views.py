"""Discord Progressive Schedule & Acquaintances presentation and O(1) context helpers.

Provides read-only batch context preloading, 5-block Weekday/Weekend routine
formatting for Discord embed field limits (<= 1024 chars), and Acquaintances
embeds parity-matched with the React Web SPA.
"""

from __future__ import annotations

import inspect
import json
import sqlite3
from typing import Any, Callable, Dict, List, Mapping, Optional, Set, Tuple

import discord

import db
from mechanics.social import relationship_graph as rg
from mechanics.social.relationships import (
    can_player_dm_contact,
    enrich_contact_dossier,
    get_relationship_tier,
    is_unlocked_contact,
    safe_get_contacts,
)
from mechanics.world.routine_disclosure import (
    ROUTINE_BLOCKS,
    apply_known_routine_to_contact,
    build_known_routine_payload,
)
from scenario_data import is_anomalous_incursions_scenario

_BLOCK_LABELS: Dict[str, str] = {
    "morning": "Morning",
    "lunch": "Lunch",
    "afternoon": "Afternoon",
    "evening": "Evening",
    "night": "Night",
}

_SHORT_BLOCK_LABELS: Dict[str, str] = {
    "morning": "AM",
    "lunch": "Lunch",
    "afternoon": "PM",
    "evening": "Eve",
    "night": "Night",
}

_DISCORD_EMBED_FIELD_MAX = 1024
_NON_TRIVIAL_PRELOAD_ERRORS = (sqlite3.Error, AttributeError, TypeError, ValueError)


def _format_day_section(
    header: str,
    slots: Mapping[str, Any],
    labels: Mapping[str, str],
    slot_cap: int = 80,
) -> str:
    """Format one Weekday or Weekend 5-block section."""
    lines = [f"**{header}**"]
    for block in ROUTINE_BLOCKS:
        raw = str(slots.get(block) or "???").strip() or "???"
        if len(raw) > slot_cap:
            raw = raw[: max(1, slot_cap - 3)].rstrip() + "..."
        lines.append(f"• {labels[block]}: {raw}")
    return "\n".join(lines)


def format_discord_known_routine_value(
    known_routine: Optional[Mapping[str, Any]],
    legacy_sched: str = "",
    *,
    include_weekend: bool = True,
) -> str:
    """Render a 5-block Weekday/Weekend known routine strictly within 1024 chars."""
    if isinstance(known_routine, Mapping) and (
        isinstance(known_routine.get("weekday"), Mapping)
        or isinstance(known_routine.get("weekend"), Mapping)
    ):
        weekday = known_routine.get("weekday")
        weekend = known_routine.get("weekend")
        weekday_map: Mapping[str, Any] = weekday if isinstance(weekday, Mapping) else {}
        weekend_map: Mapping[str, Any] = weekend if isinstance(weekend, Mapping) else {}

        override = known_routine.get("current_day_override")
        override_line = ""
        if isinstance(override, Mapping) and (
            known_routine.get("full_schedule_unlocked")
            or int(known_routine.get("discovered_count") or 0) > 0
        ):
            ov_lbl = str(override.get("label") or "").strip()
            if ov_lbl:
                override_line = f"\n📌 **Today:** {ov_lbl[:90]}"

        for labels, cap in (
            (_BLOCK_LABELS, 80),
            (_BLOCK_LABELS, 52),
            (_SHORT_BLOCK_LABELS, 36),
            (_SHORT_BLOCK_LABELS, 24),
        ):
            parts = [_format_day_section("Weekday", weekday_map, labels, slot_cap=cap)]
            if include_weekend:
                parts.append(_format_day_section("Weekend", weekend_map, labels, slot_cap=cap))
            candidate = "\n".join(parts) + override_line
            if len(candidate) <= _DISCORD_EMBED_FIELD_MAX:
                return candidate
            base_candidate = "\n".join(parts)
            if override_line and len(base_candidate) <= _DISCORD_EMBED_FIELD_MAX:
                return base_candidate

        fallback = _format_day_section("Weekday", weekday_map, _SHORT_BLOCK_LABELS, slot_cap=24)
        if len(fallback) <= _DISCORD_EMBED_FIELD_MAX:
            return fallback
        return fallback[: _DISCORD_EMBED_FIELD_MAX - 3].rstrip() + "..."

    cleaned = str(legacy_sched or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) > _DISCORD_EMBED_FIELD_MAX - 2:
        cleaned = cleaned[: _DISCORD_EMBED_FIELD_MAX - 5].rstrip() + "..."
    return f"`{cleaned}`"


def format_discord_known_wardrobe_value(
    known_wardrobe: Optional[Mapping[str, Any]],
    *,
    lang: str = "en",
) -> str:
    """Format Fog-of-War masked wardrobe dossier rows within Discord's 1024-char field limit."""
    if not isinstance(known_wardrobe, Mapping):
        return ""
    try:
        from mechanics.social.locales import get_wardrobe_labels

        lbl = get_wardrobe_labels(lang)
    except Exception:
        lbl = {
            "currently_wearing": "Currently Wearing",
            "duty": "Main / Duty",
            "casual": "Casual",
            "sleepwear": "Sleepwear",
            "gifted": "Gifted",
        }

    lines: List[str] = []
    cw = known_wardrobe.get("currently_wearing")
    if known_wardrobe.get("is_colocated") and isinstance(cw, Mapping) and cw.get("summary"):
        lines.append(f"• ✨ **{lbl['currently_wearing']}**: {str(cw['summary'])[:180]}")

    presets = known_wardrobe.get("presets") or {}
    for pkey in ("duty", "casual", "sleepwear"):
        entry = presets.get(pkey)
        if not isinstance(entry, Mapping):
            continue
        p_label = lbl.get(pkey, pkey.title())
        gift_tag = f" *(🎁 {lbl['gifted']})*" if entry.get("has_gift") else ""
        if entry.get("known") and entry.get("summary") and entry.get("summary") != "???":
            lines.append(f"• **{p_label}**: {str(entry['summary'])[:160]}{gift_tag}")
        else:
            lines.append(f"• **{p_label}**: `???`")

    kits = known_wardrobe.get("activity_kits") or {}
    for k_name, k_entry in kits.items():
        if isinstance(k_entry, Mapping) and k_entry.get("known") and k_entry.get("summary"):
            pretty_k = str(k_name).replace("activity:", "").replace("_", " ").title()
            lines.append(f"• **{pretty_k}**: {str(k_entry['summary'])[:120]}")

    out = "\n".join(lines)
    if len(out) > _DISCORD_EMBED_FIELD_MAX:
        out = out[: _DISCORD_EMBED_FIELD_MAX - 3].rstrip() + "..."
    return out


def _parse_json_list(raw: Any) -> List[str]:
    """Parse list or JSON array safely into non-empty strings."""
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    return []


def _extract_last_name(full_name: str) -> str:
    """Return multi-word surname if present."""
    parts = str(full_name or "").strip().split()
    return parts[-1] if len(parts) > 1 else ""


def _build_acquaintance_workplace(
    row: Mapping[str, Any],
    nodes_by_id: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> str:
    """Resolve readable workplace/role subtitle for an acquaintance card."""
    raw_basic = row.get("basic_info") if isinstance(row.get("basic_info"), Mapping) else {}
    work_nid = str(row.get("workplace_node_id") or raw_basic.get("workplace_node_id") or "").strip()
    node_name = ""
    if work_nid and isinstance(nodes_by_id, Mapping):
        w_node = nodes_by_id.get(work_nid)
        if isinstance(w_node, Mapping):
            node_name = str(w_node.get("name") or "").strip()
    work_name = str(
        node_name or row.get("work_node_name") or row.get("workplace_label") or ""
    ).strip()
    role = str(row.get("job_title") or row.get("role") or raw_basic.get("role") or "").strip()
    if role and work_name and work_name.lower() not in role.lower():
        return f"{role} ({work_name})"
    return role or work_name


def _resolve_aff(row: Mapping[str, Any]) -> int:
    """Resolve acquaintance/contact affinity without dropping explicit 0 values."""
    for key in ("affinity_score", "relationship_score", "affection", "affinity"):
        val = row.get(key)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                continue
    return 0


def _index_contacts_and_roster(
    contacts: List[dict],
    roster_rows: List[dict],
) -> Tuple[Dict[str, dict], Dict[str, dict], Dict[str, dict], Dict[str, dict]]:
    """Build canonical key and name lookup maps without extra DB calls."""
    contacts_by_key: Dict[str, dict] = {}
    contacts_by_name: Dict[str, dict] = {}
    for contact in contacts:
        if not isinstance(contact, Mapping):
            continue
        c_dict = dict(contact)
        ck = db.canon_social_npc_id(c_dict.get("npc_id") or c_dict.get("npc_key") or c_dict.get("name") or "")
        cn = db.canon_social_npc_id(c_dict.get("name") or "")
        if ck:
            contacts_by_key[ck] = c_dict
        if cn:
            contacts_by_name[cn] = c_dict

    roster_by_key: Dict[str, dict] = {}
    roster_by_name: Dict[str, dict] = {}
    for row in roster_rows:
        if not isinstance(row, Mapping):
            continue
        r_dict = dict(row)
        rk = db.canon_social_npc_id(r_dict.get("npc_id") or r_dict.get("npc_key") or r_dict.get("name") or "")
        rn = db.canon_social_npc_id(r_dict.get("name") or "")
        if rk:
            roster_by_key[rk] = r_dict
        if rn:
            roster_by_name[rn] = r_dict

    return contacts_by_key, contacts_by_name, roster_by_key, roster_by_name


def preload_discord_social_context(
    session_id: int,
    character_id: int,
    scenario_key: str,
    *,
    user_id: int = 0,
    preloaded_contacts: Optional[List[dict]] = None,
    preloaded_party_npcs: Optional[List[dict]] = None,
    preloaded_session: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Preload all session social/world state in O(1) batch SQLite reads."""
    sid = int(session_id or 0)
    cid = int(character_id or 0)
    scen = str(scenario_key or "fantasy")
    session_row: Optional[dict] = dict(preloaded_session) if isinstance(preloaded_session, Mapping) else None

    reveal_debug = False
    ui_lang = "en"
    player_last_name = ""
    if user_id:
        try:
            user_settings = db.get_settings(user_id) or {}
            reveal_debug = bool(user_settings.get("debug_reveal_all_info"))
            ui_lang = str(user_settings.get("ui_language") or "en")
        except _NON_TRIVIAL_PRELOAD_ERRORS:
            reveal_debug = False
            ui_lang = "en"
        try:
            char_row = db.get_character(user_id) or {}
            if not cid and char_row.get("id"):
                cid = int(char_row["id"])
            player_last_name = _extract_last_name(str(char_row.get("name") or ""))
        except _NON_TRIVIAL_PRELOAD_ERRORS:
            player_last_name = ""

    contacts: List[dict] = (
        list(preloaded_contacts)
        if preloaded_contacts is not None
        else (safe_get_contacts(sid, cid or None, resolve_relations=False, ensure_scene=False) if sid else [])
    )

    roster_rows: List[dict] = []
    nodes_by_id: Dict[str, dict] = {}
    primary_property: Optional[dict] = None
    person_ties: List[dict] = []
    active_ties_by_person: Dict[str, List[dict]] = {}
    active_events: List[dict] = []
    party_npcs: List[dict] = []
    discoveries_by_npc: Dict[str, List[dict]] = {}
    party_npc_keys: Set[str] = set()
    kin_npc_keys: Set[str] = set()
    romantic_npc_keys: Set[str] = set()
    faction_state: Optional[dict] = None

    if sid:
        try:
            roster_rows = list(db.get_world_roster(sid, include_legacy_rosters=True) or [])
        except _NON_TRIVIAL_PRELOAD_ERRORS:
            roster_rows = []
        try:
            for node in db.get_session_world_nodes(sid) or []:
                if isinstance(node, Mapping) and str(node.get("node_id") or "").strip():
                    nodes_by_id[str(node["node_id"])] = dict(node)
        except _NON_TRIVIAL_PRELOAD_ERRORS:
            nodes_by_id = {}
        try:
            primary_property = db.get_primary_property(sid)
        except _NON_TRIVIAL_PRELOAD_ERRORS:
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
        except _NON_TRIVIAL_PRELOAD_ERRORS:
            active_ties_by_person = {}
            try:
                if hasattr(rg, "get_person_ties"):
                    person_ties = list(rg.get_person_ties(sid, "player") or [])
                elif hasattr(rg, "get_ties"):
                    person_ties = list(rg.get_ties(sid, "player") or [])
            except _NON_TRIVIAL_PRELOAD_ERRORS:
                person_ties = []
        try:
            active_events = [
                dict(ev) for ev in (db.get_world_events(sid, entity_type="macro_event") or [])
                if isinstance(ev, Mapping)
            ]
        except _NON_TRIVIAL_PRELOAD_ERRORS:
            active_events = []
        try:
            if preloaded_party_npcs is not None:
                party_npcs = list(preloaded_party_npcs)
            else:
                party_npcs = list(db.get_session_party_npcs(sid) or [])
        except _NON_TRIVIAL_PRELOAD_ERRORS:
            party_npcs = []
        try:
            discoveries_by_npc = dict(db.get_contact_dossier_discoveries_batch(sid, cid) or {})
        except _NON_TRIVIAL_PRELOAD_ERRORS:
            discoveries_by_npc = {}
        try:
            ex_sets = db.get_player_fow_exemption_sets(sid) or {}
            if isinstance(ex_sets, Mapping):
                party_npc_keys = set(ex_sets.get("party_npc_keys") or set())
                kin_npc_keys = set(ex_sets.get("kin_npc_keys") or set())
                romantic_npc_keys = set(ex_sets.get("romantic_npc_keys") or set())
            elif isinstance(ex_sets, (tuple, list)) and len(ex_sets) >= 3:
                party_npc_keys = set(ex_sets[0] or set())
                kin_npc_keys = set(ex_sets[1] or set())
                romantic_npc_keys = set(ex_sets[2] or set())
        except _NON_TRIVIAL_PRELOAD_ERRORS:
            party_npc_keys, kin_npc_keys, romantic_npc_keys = set(), set(), set()
        if session_row is None:
            try:
                raw_sess = db.get_session(sid)
                session_row = dict(raw_sess) if isinstance(raw_sess, Mapping) else None
            except _NON_TRIVIAL_PRELOAD_ERRORS:
                session_row = None
        try:
            if is_anomalous_incursions_scenario(scen):
                raw_af = (session_row or {}).get("anomalous_faction_state") if isinstance(session_row, Mapping) else None
                if isinstance(raw_af, Mapping) and raw_af:
                    faction_state = dict(raw_af)
                else:
                    st_fid = str((session_row or {}).get("starting_faction_id") or "").strip().lower() if isinstance(session_row, Mapping) else ""
                    faction_state = {"faction_archetype_key": st_fid} if st_fid else {}
        except _NON_TRIVIAL_PRELOAD_ERRORS:
            faction_state = None

    anomalous_agent_roster: Optional[List[dict]] = None
    if session_row is not None:
        raw_ar = session_row.get("anomalous_agent_roster") or (
            session_row.get("extra", {}).get("anomalous_agent_roster")
            if isinstance(session_row.get("extra"), Mapping)
            else None
        )
        anomalous_agent_roster = [a for a in raw_ar if isinstance(a, dict)] if isinstance(raw_ar, list) else []

    c_by_key, c_by_name, r_by_key, r_by_name = _index_contacts_and_roster(contacts, roster_rows)
    party_names = {
        str(p.get("name") or "").strip().lower()
        for p in party_npcs
        if isinstance(p, Mapping) and p.get("name")
    }

    current_day: Optional[int] = None
    current_minute: Optional[int] = None
    if isinstance(session_row, Mapping):
        if session_row.get("current_day") is not None:
            current_day = int(session_row.get("current_day") or 1)
        if session_row.get("current_minute") is not None:
            current_minute = int(session_row.get("current_minute"))
    elif sid:
        try:
            db_day, db_min, _ = db.get_session_time(sid)
            current_day = int(db_day or 1)
            current_minute = int(db_min) if db_min is not None else None
        except _NON_TRIVIAL_PRELOAD_ERRORS:
            pass
    player_home_node_id = str(
        (primary_property or {}).get("node_id")
        or (session_row.get("player_home_node_id") if isinstance(session_row, Mapping) else "")
        or ""
    ).strip()

    return {
        "session_id": sid,
        "character_id": cid,
        "scenario_key": scen,
        "session": session_row,
        "reveal_debug": reveal_debug,
        "ui_lang": ui_lang,
        "player_last_name": player_last_name,
        "contacts": contacts,
        "roster_rows": roster_rows,
        "nodes_by_id": nodes_by_id,
        "primary_property": primary_property,
        "person_ties": person_ties,
        "active_ties_by_person": active_ties_by_person,
        "active_events": active_events,
        "current_day": current_day,
        "current_minute": current_minute,
        "player_home_node_id": player_home_node_id,
        "party_npcs": party_npcs,
        "party_names": party_names,
        "discoveries_by_npc": discoveries_by_npc,
        "party_npc_keys": party_npc_keys,
        "kin_npc_keys": kin_npc_keys,
        "romantic_npc_keys": romantic_npc_keys,
        "faction_state": faction_state,
        "anomalous_agent_roster": anomalous_agent_roster,
        "household_cache": {},
        "contacts_by_key": c_by_key,
        "contacts_by_name": c_by_name,
        "roster_by_key": r_by_key,
        "roster_by_name": r_by_name,
    }


def _discoveries_for_npc(
    discoveries_by_npc: Mapping[str, List[dict]],
    npc_key: str,
    npc_name: str,
) -> List[dict]:
    """Lookup preloaded dossier discovery rows by canonical key or name."""
    seen_ids: Set[int] = set()
    rows: List[dict] = []
    for candidate in (
        str(npc_key or "").strip().lower(),
        str(npc_name or "").strip().lower(),
        db.canon_social_npc_id(npc_key),
        db.canon_social_npc_id(npc_name),
    ):
        if not candidate:
            continue
        for item in discoveries_by_npc.get(candidate) or ():
            row_id = item.get("id")
            if row_id is not None:
                int_id = int(row_id)
                if int_id in seen_ids:
                    continue
                seen_ids.add(int_id)
            rows.append(dict(item))
    return rows


def enrich_discord_npc_with_routine(
    npc: Mapping[str, Any],
    fow_context: Mapping[str, Any],
    *,
    is_acquaintance: bool = False,
) -> dict:
    """Enrich a Contact or read-only Acquaintance using preloaded O(1) context."""
    sid = int(fow_context.get("session_id") or 0)
    cid = int(fow_context.get("character_id") or 0)
    scen = str(fow_context.get("scenario_key") or "fantasy")
    ui_lang = str(fow_context.get("ui_lang") or "en")
    reveal_debug = bool(fow_context.get("reveal_debug"))

    npc_in = dict(npc)
    if cid and not npc_in.get("character_id"):
        npc_in["character_id"] = cid
    if sid and not npc_in.get("session_id"):
        npc_in["session_id"] = sid

    ck = db.canon_social_npc_id(npc_in.get("npc_id") or npc_in.get("npc_key") or npc_in.get("name") or "")
    cn = db.canon_social_npc_id(npc_in.get("name") or "")
    disc_rows = _discoveries_for_npc(
        fow_context.get("discoveries_by_npc") or {},
        str(npc_in.get("npc_id") or npc_in.get("npc_key") or ""),
        str(npc_in.get("name") or ""),
    )

    enriched = enrich_contact_dossier(
        npc_in,
        sid,
        scen,
        debug_reveal_all=reveal_debug,
        phys_st=(fow_context.get("session") or {}).get("physical_state") if isinstance(fow_context.get("session"), Mapping) else None,
        preloaded_discoveries=disc_rows,
        lang=ui_lang,
        party_npc_keys=fow_context.get("party_npc_keys"),
        kin_npc_keys=fow_context.get("kin_npc_keys"),
        romantic_npc_keys=fow_context.get("romantic_npc_keys"),
        read_only=True,
        preloaded_party_npcs=fow_context.get("party_npcs"),
        preloaded_faction_state=fow_context.get("faction_state"),
        preloaded_agent_roster=fow_context.get("anomalous_agent_roster"),
        preloaded_session=fow_context.get("session"),
    )

    roster_row = (
        (fow_context.get("roster_by_key") or {}).get(ck)
        or (fow_context.get("roster_by_name") or {}).get(cn)
    )
    contact_row = (
        None
        if is_acquaintance
        else (
            (fow_context.get("contacts_by_key") or {}).get(ck)
            or (fow_context.get("contacts_by_name") or {}).get(cn)
            or npc_in
        )
    )

    routine = build_known_routine_payload(
        enriched,
        session_id=sid,
        scen_key=scen,
        lang=ui_lang,
        debug_reveal_all=reveal_debug,
        nodes_by_id=fow_context.get("nodes_by_id"),
        roster_row=roster_row,
        contact_row=contact_row,
        primary_property=fow_context.get("primary_property"),
        contacts=fow_context.get("contacts"),
        person_ties=fow_context.get("person_ties"),
        household_cache=fow_context.get("household_cache"),
        player_last_name=fow_context.get("player_last_name"),
        party_npc_keys=fow_context.get("party_npc_keys"),
        kin_npc_keys=fow_context.get("kin_npc_keys"),
        romantic_npc_keys=fow_context.get("romantic_npc_keys"),
        discovered_dossier_rows=disc_rows,
        character_id=cid,
        preloaded=True,
        fow_schedule_revealed=bool(enriched.get("schedule_revealed")),
        current_day=fow_context.get("current_day"),
        current_minute=fow_context.get("current_minute"),
        active_ties_by_person=fow_context.get("active_ties_by_person"),
        roster_by_key=fow_context.get("roster_by_key"),
        active_events=fow_context.get("active_events") or (),
        player_home_node_id=str(fow_context.get("player_home_node_id") or ""),
    )
    apply_known_routine_to_contact(enriched, routine, lang=ui_lang)
    enriched["ui_lang"] = ui_lang

    party_names = fow_context.get("party_names") or set()
    if is_acquaintance:
        enriched["can_dm"] = False
        enriched["is_acquaintance"] = True
        enriched["tier_status"] = "acquaintance"
    else:
        enriched["can_dm"] = can_player_dm_contact(
            enriched,
            party_names,
            scenario=scen,
            preloaded_session=fow_context.get("session"),
            skip_session_lookup=True,
        )

    return enriched


def load_discord_contacts_and_acquaintances(
    session_id: int,
    character_id: int,
    scenario_key: str,
    *,
    user_id: int = 0,
    party_names: Optional[Set[str]] = None,
    party_npcs: Optional[List[dict]] = None,
    filter_unlocked_fn: Optional[Callable[..., List[dict]]] = None,
    preloaded_session: Optional[Mapping[str, Any]] = None,
) -> Tuple[List[dict], List[dict], Dict[str, Any]]:
    """Load and enrich Contacts + read-only deduplicated Acquaintances in O(1)."""
    fow_context = preload_discord_social_context(
        session_id,
        character_id,
        scenario_key,
        user_id=user_id,
        preloaded_party_npcs=party_npcs,
        preloaded_session=preloaded_session,
    )
    eff_party_names = party_names if party_names is not None else set(fow_context.get("party_names") or ())
    fow_context["party_names"] = eff_party_names

    raw_contacts = list(fow_context.get("contacts") or [])
    eff_session = fow_context.get("session")
    if filter_unlocked_fn is not None:
        try:
            sig_params = inspect.signature(filter_unlocked_fn).parameters
        except (TypeError, ValueError):
            sig_params = {}
        if "preloaded_session" in sig_params and "skip_session_lookup" in sig_params:
            unlocked_raw = list(
                filter_unlocked_fn(
                    raw_contacts,
                    eff_party_names,
                    scenario_key,
                    preloaded_session=eff_session,
                    skip_session_lookup=True,
                )
            )
        else:
            unlocked_raw = list(filter_unlocked_fn(raw_contacts, eff_party_names, scenario_key))
    else:
        unlocked_raw = [
            c
            for c in raw_contacts
            if is_unlocked_contact(
                c,
                eff_party_names,
                preloaded_session=eff_session,
                skip_session_lookup=True,
            )
        ]

    enriched_contacts = [
        enrich_discord_npc_with_routine(c, fow_context, is_acquaintance=False)
        for c in unlocked_raw
    ]

    excluded_keys: Set[str] = set()
    excluded_names: Set[str] = set()
    for c in raw_contacts:
        ck = db.canon_social_npc_id(c.get("npc_id") or c.get("npc_key") or c.get("name") or "")
        cn = db.canon_social_npc_id(c.get("name") or "")
        if ck:
            excluded_keys.add(ck)
        if cn:
            excluded_names.add(cn)

    nodes_by_id = fow_context.get("nodes_by_id") or {}
    seen_acq_keys: Set[str] = set()
    acquaintances: List[dict] = []
    for row in fow_context.get("roster_rows") or []:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("tier_status") or "").strip().lower() != "acquaintance":
            continue
        npc_name = str(row.get("name") or "").strip()
        npc_key = db.canon_social_npc_id(row.get("npc_id") or row.get("npc_key") or npc_name)
        canon_name = db.canon_social_npc_id(npc_name)
        if not npc_name or not npc_key:
            continue
        if npc_key in excluded_keys or (canon_name and canon_name in excluded_names):
            continue
        if npc_key in seen_acq_keys:
            continue
        seen_acq_keys.add(npc_key)

        workplace_label = _build_acquaintance_workplace(row, nodes_by_id=nodes_by_id)
        affinity = _resolve_aff(row)
        first_met_turn = int(row.get("first_met_turn") or 0)
        raw_basic = row.get("basic_info") if isinstance(row.get("basic_info"), Mapping) else {}
        acq_seed = {
            "id": f"acq_{npc_key}",
            "session_id": int(session_id or 0),
            "character_id": int(fow_context.get("character_id") or 0),
            "npc_id": str(row.get("npc_id") or npc_key),
            "npc_key": npc_key,
            "name": npc_name,
            "role": str(row.get("job_title") or row.get("role") or workplace_label or "Acquaintance"),
            "workplace_label": workplace_label,
            "origin": str(row.get("origin") or "Unknown"),
            "affinity_score": affinity,
            "relationship_score": affinity,
            "affection": affinity,
            "affinity": affinity,
            "first_met_turn": first_met_turn,
            "known_status": str(row.get("staff_status") or row.get("status") or "Active"),
            "tier_status": "acquaintance",
            "is_acquaintance": True,
            "can_dm": False,
            "basic_info": dict(raw_basic),
            "appearance": dict(row.get("appearance") or {}) if isinstance(row.get("appearance"), Mapping) else {},
            "traits": list(row.get("traits") or []) if isinstance(row.get("traits"), list) else [],
            "promotion_hint": "Ask for their number or connect via PeerPulse to add as a Contact.",
        }
        enriched_acq = enrich_discord_npc_with_routine(acq_seed, fow_context, is_acquaintance=True)
        enriched_acq["id"] = f"acq_{npc_key}"
        enriched_acq["workplace_label"] = workplace_label
        enriched_acq["origin"] = acq_seed["origin"]
        enriched_acq["affinity_score"] = affinity
        enriched_acq["relationship_score"] = affinity
        enriched_acq["first_met_turn"] = first_met_turn
        enriched_acq["promotion_hint"] = acq_seed["promotion_hint"]
        enriched_acq["can_dm"] = False
        enriched_acq["is_acquaintance"] = True
        enriched_acq["tier_status"] = "acquaintance"
        acquaintances.append(enriched_acq)

    acquaintances.sort(
        key=lambda a: (
            -_resolve_aff(a),
            -int(a.get("first_met_turn") or 0),
            str(a.get("name") or "").lower(),
        )
    )
    return enriched_contacts, acquaintances, fow_context


def build_acquaintances_list_embed(
    acquaintances: List[dict],
    scenario_key: str,
    char_name: str,
) -> discord.Embed:
    """Build the Discord embed listing read-only Acquaintances."""
    if not acquaintances:
        embed = discord.Embed(
            title=f"👥 {char_name}'s Acquaintances (0)",
            description=(
                "No casual acquaintances spotted yet.\n"
                "People you meet briefly or spot around town appear here until "
                "you exchange contact info or connect via PeerPulse."
            ),
            color=0x64748B,
        )
        embed.set_footer(text="Acquaintances are read-only until promoted to Contacts.")
        return embed

    lines: List[str] = []
    for acq in acquaintances[:25]:
        name = str(acq.get("name") or "Unknown")
        workplace = str(acq.get("workplace_label") or acq.get("role") or "Acquaintance")
        aff = _resolve_aff(acq)
        tier_info = get_relationship_tier(aff, track="platonic", scenario=scenario_key or "default")
        tier_name = str((tier_info or {}).get("name") or "Acquaintance")
        lines.append(f"• **{name}** — *{workplace}* | {tier_name} ({aff:+d}) | 🔒 DM Locked")

    extra = f"\n*...and {len(acquaintances) - 25} more*" if len(acquaintances) > 25 else ""
    embed = discord.Embed(
        title=f"👥 {char_name}'s Acquaintances ({len(acquaintances)})",
        description="\n".join(lines) + extra,
        color=0x64748B,
    )
    embed.set_footer(text="Select an acquaintance below to inspect their profile & known routine.")
    return embed


def build_acquaintance_detail_embed(
    acquaintance: Mapping[str, Any],
    scenario_key: str,
    char_name: str,
    reveal_debug: bool = False,
) -> discord.Embed:
    """Build the Discord detail embed for a single read-only Acquaintance."""
    name = str(acquaintance.get("name") or "Unknown")
    workplace = str(acquaintance.get("workplace_label") or acquaintance.get("role") or "Acquaintance")
    origin = str(acquaintance.get("origin") or "Unknown")
    aff = _resolve_aff(acquaintance)
    tier_info = get_relationship_tier(aff, track="platonic", scenario=scenario_key or "default")
    tier_name = str((tier_info or {}).get("name") or "Acquaintance")

    embed = discord.Embed(
        title=f"👥 {name} (Acquaintance)",
        description=f"*{workplace}*\nOrigin: `{origin}` | Standing: **{tier_name}** (`{aff:+d}`)",
        color=0x64748B,
    )

    if not acquaintance.get("can_dm"):
        hint = str(
            acquaintance.get("promotion_hint")
            or "Ask for number in person or connect via PeerPulse."
        )
        embed.add_field(
            name="🔒 DM Locked",
            value=f"Ask for number in person or connect via PeerPulse.\n_{hint}_",
            inline=False,
        )

    traits = _parse_json_list(
        acquaintance.get("unlocked_traits")
        if acquaintance.get("unlocked_traits") is not None
        else acquaintance.get("personality_traits")
    )
    likes = _parse_json_list(
        acquaintance.get("preferences")
        if acquaintance.get("preferences") is not None
        else acquaintance.get("likes")
    )
    dislikes = _parse_json_list(acquaintance.get("dislikes"))
    traits_str = ", ".join(traits[:3]) if traits else "???"
    likes_str = ", ".join(likes[:3]) if likes else "???"
    dislikes_str = ", ".join(dislikes[:3]) if dislikes else "???"

    embed.add_field(
        name="📋 Observed Profile",
        value=f"**Traits:** {traits_str}\n**Likes:** {likes_str}\n**Dislikes:** {dislikes_str}",
        inline=False,
    )

    routine_val = format_discord_known_routine_value(
        acquaintance.get("known_routine"),
        str(acquaintance.get("known_schedule") or ""),
    )
    if routine_val:
        embed.add_field(
            name="🕒 Schedule & Routine",
            value=routine_val,
            inline=False,
        )

    wardrobe_val = format_discord_known_wardrobe_value(
        acquaintance.get("known_wardrobe"),
        lang=str(acquaintance.get("ui_lang") or "en"),
    )
    if wardrobe_val:
        embed.add_field(
            name="👔 Known Wardrobe",
            value=wardrobe_val,
            inline=False,
        )

    footer = f"{char_name}'s Acquaintances (Read-Only)"
    if reveal_debug:
        footer += " | Debug Reveal ON"
    embed.set_footer(text=footer)
    return embed
