"""
mechanics/world/routine_disclosure.py

Progressive Schedule Disclosure & Residential Fog-of-War formatting for
world_roster / contacts NPCs across Web API, React SPA, and Discord embeds.

Rules:
- Affinity < 40 (and not Fog-of-War exempted or schedule-discovered): only
  individually observed/discovered slots (`discovered_slots`) are disclosed;
  every unvisited slot across Weekday & Weekend renders as `"???"`.
- Affinity >= 40 (or exempt / schedule-discovered): full 5-block Weekday &
  Weekend anchor/scheduled routine unlocks, automatically skipping non-proprietor
  rest days so workers still show their regular shift workplace.
- Affinity < 100 and residence not otherwise unlocked (`residence_unlocked=False`):
  private residential blocks ALWAYS mask to the localized residential fog label
  (`"Residential Area (Unknown)"`). Concrete residence names unlock only when
  `can_materialize_npc_residence(...)` (or `debug_reveal_all`) permits.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

import db
from mechanics.social import locales
from mechanics.social.consequences import is_contact_exempt_from_fog_of_war
from mechanics.world.anchor_schedule import (
    is_npc_on_active_shift,
    resolve_anchor_schedule_nodes,
)
from mechanics.world.locations.residence_fog import (
    SHARED_ABSTRACT_RESIDENCE_NODE,
    can_materialize_npc_residence,
)
from mechanics.world.npc_schedule import get_npc_schedule, get_npc_schedule_node_ids

ROUTINE_BLOCKS: Tuple[str, ...] = ("morning", "lunch", "afternoon", "evening", "night")

BLOCK_MINUTES: Dict[str, int] = {
    "morning": 540,
    "lunch": 750,
    "afternoon": 900,
    "evening": 1080,
    "night": 1320,
}

RESIDENTIAL_FOG_LABELS: Dict[str, str] = {
    "en": "Residential Area (Unknown)",
    "pl": "Dzielnica Mieszkalna (Nieznana)",
    "ms": "Kawasan Kediaman (Tidak Diketahui)",
    "zh": "住宅区（未知）",
    "de": "Wohnviertel (Unbekannt)",
}

_SUMMARY_DAY_LABELS: Dict[str, Tuple[str, str]] = {
    "en": ("Weekday", "Weekend"),
    "pl": ("Dni robocze", "Weekend"),
    "ms": ("Hari Bekerja", "Hujung Minggu"),
    "zh": ("工作日", "周末"),
    "de": ("Wochentag", "Wochenende"),
}

_SUMMARY_BLOCK_LABELS: Dict[str, Dict[str, str]] = {
    "en": {"morning": "Morning", "lunch": "Lunch", "afternoon": "Afternoon", "evening": "Evening", "night": "Night"},
    "pl": {"morning": "Rano", "lunch": "Południe", "afternoon": "Popołudnie", "evening": "Wieczór", "night": "Noc"},
    "ms": {"morning": "Pagi", "lunch": "Tengah Hari", "afternoon": "Petang", "evening": "Senja", "night": "Malam"},
    "zh": {"morning": "清晨", "lunch": "午间", "afternoon": "午后", "evening": "傍晚", "night": "夜间"},
    "de": {"morning": "Morgen", "lunch": "Mittag", "afternoon": "Nachmittag", "evening": "Abend", "night": "Nacht"},
}

_INTERNAL_RES_PREFIXES: Tuple[str, ...] = ("sub_npc_res_", "fac_npc_res_", "npc_res_")
_LEGACY_BLOCK_FALLBACKS: Dict[str, Tuple[str, ...]] = {
    "morning": ("morning", "commute"),
    "lunch": ("lunch",),
    "afternoon": ("afternoon", "class_afternoon"),
    "evening": ("evening", "extracurricular"),
    "night": ("night",),
}
_PRIVATE_HOME_TEXT_RE = re.compile(
    r"(?:\b(?:at home|private home|private residence|dormitory room|private quarters|unknown address|residential (?:district|neighborhood|area))\b|^\s*home\s*$|npc_res_|zone_residential_abstract)",
    re.IGNORECASE,
)
_PUBLIC_VENUE_GUARD_RE = re.compile(
    r"\b(?:home\s+goods|homemade|homestead\s+inn|market|cafe|tavern|park|street|plaza|square|shop|store|library|academy|campus|guild|clinic|office)\b",
    re.IGNORECASE,
)


def get_residential_fog_label(lang: str = "en") -> str:
    """Returns the localized residential fog-of-war placeholder string."""
    norm = locales.normalize_social_lang(lang)
    return RESIDENTIAL_FOG_LABELS.get(norm, RESIDENTIAL_FOG_LABELS["en"])


def _parse_mapping_field(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _parse_score_int(raw: Any) -> Optional[int]:
    if raw is None or raw == "" or isinstance(raw, bool):
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def _is_residential_node_id(node_id: Any, real_home: str = "", workplace_node_id: str = "") -> bool:
    nid = str(node_id or "").strip()
    if not nid:
        return False
    low = nid.lower()
    if nid == SHARED_ABSTRACT_RESIDENCE_NODE:
        return True
    if any(low.startswith(p) for p in _INTERNAL_RES_PREFIXES) or "npc_res_" in low:
        return True
    if real_home and nid == real_home and nid != workplace_node_id:
        return True
    if low in ("fac_agency_residence", "fac_temple_residence") and nid != workplace_node_id:
        return True
    if (low.endswith("_apartment") or low.endswith("_quarters") or low.endswith("_dormitories") or low.endswith("_residence")) and nid != workplace_node_id:
        return True
    return False


def _is_residential_label(label: Any, *, fog_labels: Optional[set[str]] = None) -> bool:
    text = str(label or "").strip()
    if not text:
        return False
    if fog_labels and text in fog_labels:
        return True
    low = text.lower()
    if "unknown address" in low or "residential area (unknown)" in low or "residential district" in low or "residential neighborhood" in low:
        return True
    if _PUBLIC_VENUE_GUARD_RE.search(low) and not _PRIVATE_HOME_TEXT_RE.search(low):
        return False
    return bool(_PRIVATE_HOME_TEXT_RE.search(low))


def _humanize_node_id(node_id: str, npc_name: str = "", *, lang: str = "en") -> str:
    raw = str(node_id or "").strip()
    if not raw:
        return ""
    if raw == SHARED_ABSTRACT_RESIDENCE_NODE:
        return get_residential_fog_label(lang)
    for pref in ("sub_npc_res_", "fac_npc_res_", "npc_res_"):
        if raw.lower().startswith(pref):
            slug = raw[len(pref):].replace("_", " ").strip()
            if npc_name:
                return f"{npc_name}'s Residence"
            return f"{slug.title()} Residence" if slug else "Private Residence"
    for pref in ("sub_", "fac_", "loc_"):
        if raw.lower().startswith(pref):
            raw = raw[len(pref):]
            break
    cleaned = raw.replace("_", " ").strip()
    return cleaned.title() if cleaned else ""


def _resolve_node_label(
    node_or_label: Any,
    *,
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    residence_unlocked: bool,
    real_home: str,
    workplace_node_id: str,
    npc_name: str,
    lang: str,
) -> str:
    raw = str(node_or_label or "").strip()
    if not raw:
        return ""
    fog_label = get_residential_fog_label(lang)
    all_fog_labels = set(RESIDENTIAL_FOG_LABELS.values())

    if raw in all_fog_labels:
        if residence_unlocked and real_home and real_home != SHARED_ABSTRACT_RESIDENCE_NODE:
            node = nodes_by_id.get(real_home)
            if isinstance(node, Mapping) and node.get("name"):
                return str(node.get("name")).strip()
            return _humanize_node_id(real_home, npc_name=npc_name, lang=lang)
        return fog_label

    node = nodes_by_id.get(raw) if isinstance(nodes_by_id, Mapping) else None
    is_res_node = _is_residential_node_id(raw, real_home=real_home, workplace_node_id=workplace_node_id)
    if isinstance(node, Mapping):
        meta = node.get("metadata") if isinstance(node.get("metadata"), Mapping) else {}
        if str(node.get("node_type") or "").strip().upper() == "RESIDENCE" or bool(meta.get("is_npc_residence")):
            if raw != workplace_node_id:
                is_res_node = True

    if not residence_unlocked:
        real_home_node = nodes_by_id.get(real_home) if (real_home and isinstance(nodes_by_id, Mapping)) else None
        real_home_name = str(real_home_node.get("name") or "").strip().lower() if isinstance(real_home_node, Mapping) else ""
        if is_res_node or (real_home_name and raw.lower() == real_home_name) or _is_residential_label(raw, fog_labels=all_fog_labels):
            return fog_label

    if isinstance(node, Mapping):
        node_name = str(node.get("name") or "").strip()
        if node_name:
            if not residence_unlocked and _is_residential_label(node_name, fog_labels=all_fog_labels):
                return fog_label
            return node_name

    # If unlocked and node was abstract/synthetic residential while real_home exists in nodes_by_id, prefer real title.
    if residence_unlocked and real_home and real_home != SHARED_ABSTRACT_RESIDENCE_NODE and is_res_node:
        home_node = nodes_by_id.get(real_home) if isinstance(nodes_by_id, Mapping) else None
        if isinstance(home_node, Mapping) and home_node.get("name"):
            return str(home_node.get("name")).strip()
        return _humanize_node_id(real_home, npc_name=npc_name, lang=lang)

    if any(raw.lower().startswith(p) for p in ("sub_", "fac_", "loc_", "npc_res_", "zone_")):
        human = _humanize_node_id(raw, npc_name=npc_name, lang=lang)
        if not residence_unlocked and _is_residential_label(human, fog_labels=all_fog_labels):
            return fog_label
        return human

    if not residence_unlocked and _is_residential_label(raw, fog_labels=all_fog_labels):
        return fog_label
    return raw


def _pick_representative_day(
    probe: Mapping[str, Any],
    candidate_days: Tuple[int, ...],
    scen_key: str,
) -> int:
    """Picks the first non-rest active shift day from candidates to avoid Day-1 rest-day artifacts."""
    probe_minutes = (540, 750, 900, 1080, 1320, 60)
    for day in candidate_days:
        for minute in probe_minutes:
            on_shift, _ = is_npc_on_active_shift(
                probe,
                current_minute=minute,
                current_day=day,
                scen_key=scen_key,
                session_id=None,
            )
            if on_shift:
                return day
    return candidate_days[0]


def _extract_discovered_slots(
    npc: Mapping[str, Any],
    roster_row: Optional[Mapping[str, Any]],
    contact_row: Optional[Mapping[str, Any]],
) -> Dict[str, Dict[str, str]]:
    merged: Dict[str, Dict[str, str]] = {"weekday": {}, "weekend": {}}
    sources: List[Mapping[str, Any]] = []
    if roster_row is None and contact_row is None:
        sources.append(npc)
    else:
        if isinstance(contact_row, Mapping):
            sources.append(contact_row)
        if isinstance(roster_row, Mapping):
            sources.append(roster_row)
        if isinstance(npc, Mapping) and (npc.get("discovered_slots") or npc.get("discovered_slots_json")):
            sources.append(npc)

    for src in sources:
        src_basic = _parse_mapping_field(src.get("basic_info"))
        candidates = (
            _parse_mapping_field(src_basic.get("discovered_slots")),
            _parse_mapping_field(src.get("discovered_slots")),
            _parse_mapping_field(src.get("discovered_slots_json")),
        )
        for cand in candidates:
            for dk in ("weekday", "weekend"):
                dk_map = cand.get(dk)
                if not isinstance(dk_map, Mapping):
                    continue
                for bk, loc_val in dk_map.items():
                    loc_str = str(loc_val or "").strip()
                    if loc_str:
                        merged[dk][str(bk).strip()] = loc_str
    return merged


def _build_probe_dict(
    npc: Mapping[str, Any],
    roster_row: Optional[Mapping[str, Any]],
    contact_row: Optional[Mapping[str, Any]],
    *,
    residence_unlocked: bool,
    real_home: str,
) -> Dict[str, Any]:
    probe: Dict[str, Any] = {}
    if isinstance(contact_row, Mapping):
        probe.update(contact_row)
    if isinstance(npc, Mapping):
        probe.update(npc)
    if isinstance(roster_row, Mapping):
        for k, v in roster_row.items():
            if v is not None and v != "":
                probe[k] = v

    merged_basic: Dict[str, Any] = {}
    for src in (contact_row, npc, roster_row):
        if isinstance(src, Mapping):
            merged_basic.update(_parse_mapping_field(src.get("basic_info")))

    probe["basic_info"] = merged_basic
    probe["_roster_premerged"] = True
    probe["_db_hydrated"] = True
    probe["residence_unlocked"] = bool(residence_unlocked)
    merged_basic["residence_unlocked"] = bool(residence_unlocked)

    if residence_unlocked and real_home:
        probe["home_node_id"] = real_home
        merged_basic["home_node_id"] = real_home
    else:
        probe["home_node_id"] = SHARED_ABSTRACT_RESIDENCE_NODE
        merged_basic["home_node_id"] = SHARED_ABSTRACT_RESIDENCE_NODE
        for secret_key in ("residence_location", "home_location"):
            probe.pop(secret_key, None)
            merged_basic.pop(secret_key, None)
    return probe


def _resolve_full_day_blocks(
    probe: Dict[str, Any],
    *,
    candidate_days: Tuple[int, ...],
    scen_key: str,
    nodes_by_id: Mapping[str, Mapping[str, Any]],
    residence_unlocked: bool,
    real_home: str,
    workplace_node_id: str,
    npc_name: str,
    lang: str,
) -> Dict[str, str]:
    chosen_day = _pick_representative_day(probe, candidate_days, scen_key)
    anchor_nodes = resolve_anchor_schedule_nodes(
        probe,
        current_day=chosen_day,
        scen_key=scen_key,
        session_id=None,
        current_minute=None,
    )
    node_sched = anchor_nodes
    text_sched: Dict[str, str] = {}
    if node_sched is None:
        node_sched = get_npc_schedule_node_ids(
            probe,
            scen_key=scen_key,
            current_day=chosen_day,
            current_minute=None,
            session_id=None,
        )
        text_sched = get_npc_schedule(
            dict(probe),
            scen_key=scen_key,
            session_id=None,
            current_day=chosen_day,
            current_minute=None,
        )

    out: Dict[str, str] = {}
    masked_slot = locales.get_masked_placeholder("slot", lang=lang)
    for block in ROUTINE_BLOCKS:
        raw_nid = ""
        for cand_key in _LEGACY_BLOCK_FALLBACKS.get(block, (block,)):
            val = str((node_sched or {}).get(cand_key) or "").strip()
            if val:
                raw_nid = val
                break
        if raw_nid:
            resolved = _resolve_node_label(
                raw_nid,
                nodes_by_id=nodes_by_id,
                residence_unlocked=residence_unlocked,
                real_home=real_home,
                workplace_node_id=workplace_node_id,
                npc_name=npc_name,
                lang=lang,
            )
            if resolved:
                out[block] = resolved
                continue
        raw_txt = ""
        for cand_key in _LEGACY_BLOCK_FALLBACKS.get(block, (block,)):
            val = str((text_sched or {}).get(cand_key) or "").strip()
            if val:
                raw_txt = val
                break
        resolved_txt = _resolve_node_label(
            raw_txt,
            nodes_by_id=nodes_by_id,
            residence_unlocked=residence_unlocked,
            real_home=real_home,
            workplace_node_id=workplace_node_id,
            npc_name=npc_name,
            lang=lang,
        )
        out[block] = resolved_txt or masked_slot
    return out


def _has_closed_world_anchor_schedule(
    npc_map: Mapping[str, Any],
    npc_basic: Mapping[str, Any],
    eff_roster: Optional[Mapping[str, Any]],
    r_basic: Mapping[str, Any],
) -> bool:
    """Returns True when an NPC uses closed-world anchor scheduling rather than legacy free-text schedules."""
    if eff_roster is not None:
        r_origin = str(eff_roster.get("origin") or "").strip().lower()
        if r_origin not in ("", "legacy_adapter"):
            return True
        if bool(r_basic.get("use_anchor_schedule") or eff_roster.get("use_anchor_schedule")):
            return True
        for k in ("workplace_node_id", "home_node_id", "hangout_node_id", "roaming_route"):
            if eff_roster.get(k) or r_basic.get(k):
                return True
    if bool(npc_basic.get("use_anchor_schedule") or npc_map.get("use_anchor_schedule")):
        return True
    for k in ("workplace_node_id", "home_node_id", "hangout_node_id", "roaming_route"):
        if npc_map.get(k) or npc_basic.get(k):
            return True
    return False


def build_known_routine_payload(
    npc: Mapping[str, Any],
    *,
    session_id: int | None = None,
    scen_key: str = "fantasy",
    lang: str = "en",
    debug_reveal_all: bool = False,
    nodes_by_id: Mapping[str, Mapping[str, Any]] | None = None,
    roster_row: Mapping[str, Any] | None = None,
    contact_row: Mapping[str, Any] | None = None,
    primary_property: Mapping[str, Any] | None = None,
    contacts: list[dict[str, Any]] | None = None,
    person_ties: list[Mapping[str, Any]] | None = None,
    household_cache: dict[int, Any] | None = None,
    player_last_name: str | None = None,
    party_npc_keys: set[str] | None = None,
    kin_npc_keys: set[str] | None = None,
    romantic_npc_keys: set[str] | None = None,
    discovered_dossier_rows: list[Mapping[str, Any]] | None = None,
    character_id: int = 0,
    preloaded: bool = False,
    fow_schedule_revealed: Optional[bool] = None,
) -> dict[str, Any]:
    """
    Computes an NPC's progressive 5-block Weekday/Weekend routine payload with
    deterministic Affinity >= 40 full-routine gating, slot-level `"???"` masking,
    and Affinity >= 100 / unlocked residential Fog-of-War protection.
    """
    eff_lang = locales.normalize_social_lang(lang)
    masked_slot = locales.get_masked_placeholder("slot", lang=eff_lang)
    npc_map: Mapping[str, Any] = npc if isinstance(npc, Mapping) else {}
    npc_basic = _parse_mapping_field(npc_map.get("basic_info"))
    npc_name = str(npc_map.get("name") or npc_basic.get("name") or "").strip()
    lookup_key = str(
        npc_map.get("npc_key")
        or npc_map.get("npc_id")
        or npc_name
        or npc_basic.get("npc_id")
        or ""
    ).strip()

    sid = int(session_id) if session_id else None
    eff_nodes: Mapping[str, Mapping[str, Any]] = nodes_by_id if isinstance(nodes_by_id, Mapping) else {}
    eff_roster: Optional[Mapping[str, Any]] = dict(roster_row) if isinstance(roster_row, Mapping) and len(roster_row) > 0 else None
    eff_contact: Optional[Mapping[str, Any]] = dict(contact_row) if isinstance(contact_row, Mapping) and len(contact_row) > 0 else None
    eff_disc: Optional[List[Mapping[str, Any]]] = list(discovered_dossier_rows) if discovered_dossier_rows is not None else None

    if sid and not preloaded:
        if roster_row is None and lookup_key:
            fetched_roster = db.get_world_roster_npc(sid, lookup_key, include_legacy_rosters=True)
            if isinstance(fetched_roster, Mapping):
                eff_roster = dict(fetched_roster)
        if nodes_by_id is None:
            raw_nodes = db.get_session_world_nodes(sid) or []
            eff_nodes = {str(n["node_id"]): n for n in raw_nodes if isinstance(n, Mapping) and n.get("node_id")}
        if eff_disc is None and lookup_key:
            eff_disc = db.get_contact_dossier_discoveries(sid, int(character_id or 0), lookup_key)

    r_basic = _parse_mapping_field((eff_roster or {}).get("basic_info"))
    c_basic = _parse_mapping_field((eff_contact or {}).get("basic_info"))

    # Authoritative affinity: inspect DB truth first, take max when both exist.
    db_scores: List[int] = []
    if eff_roster is not None:
        s_r = _parse_score_int(eff_roster.get("affinity_score"))
        if s_r is not None:
            db_scores.append(s_r)
    if eff_contact is not None:
        s_c = _parse_score_int(eff_contact.get("relationship_score"))
        if s_c is not None:
            db_scores.append(s_c)
    if db_scores:
        affinity = max(db_scores)
    else:
        fallback_scores = [
            _parse_score_int(npc_map.get("affinity_score")),
            _parse_score_int(npc_map.get("relationship_score")),
            _parse_score_int(npc_basic.get("affinity_score")),
        ]
        valid_fb = [s for s in fallback_scores if s is not None]
        affinity = max(valid_fb) if valid_fb else 0

    exempt_probe: Dict[str, Any] = dict(npc_map)
    if eff_contact:
        exempt_probe.update(eff_contact)
    exempt_probe["basic_info"] = {**c_basic, **npc_basic, **r_basic}
    exempt_probe["relationship_score"] = affinity
    if not exempt_probe.get("npc_id") and eff_roster and eff_roster.get("npc_id"):
        exempt_probe["npc_id"] = eff_roster["npc_id"]
    if not exempt_probe.get("name") and npc_name:
        exempt_probe["name"] = npc_name

    has_all_exemption_sets = (
        party_npc_keys is not None and kin_npc_keys is not None and romantic_npc_keys is not None
    )
    exempt_basic, _ = is_contact_exempt_from_fog_of_war(
        exempt_probe,
        session_id=None if (has_all_exemption_sets or preloaded) else sid,
        party_npc_keys=party_npc_keys,
        kin_npc_keys=kin_npc_keys,
        romantic_npc_keys=romantic_npc_keys,
    )

    has_anchor_schedule = _has_closed_world_anchor_schedule(npc_map, npc_basic, eff_roster, r_basic)

    schedule_wildcard = False
    for d_row in (eff_disc or []):
        if isinstance(d_row, Mapping) and str(d_row.get("fact_category") or "").strip().lower() == "schedule":
            schedule_wildcard = True
            break

    if has_anchor_schedule:
        full_schedule_unlocked = bool(
            debug_reveal_all or affinity >= 40 or exempt_basic or schedule_wildcard or bool(fow_schedule_revealed)
        )
    elif fow_schedule_revealed is not None:
        full_schedule_unlocked = bool(
            debug_reveal_all or exempt_basic or schedule_wildcard or fow_schedule_revealed
        )
    elif sid is not None:
        full_schedule_unlocked = bool(debug_reveal_all or exempt_basic or schedule_wildcard)
    else:
        full_schedule_unlocked = bool(debug_reveal_all or affinity >= 40 or exempt_basic or schedule_wildcard)

    if debug_reveal_all:
        residence_unlocked = True
    elif preloaded:
        residence_unlocked = bool(
            can_materialize_npc_residence(
                sid,
                exempt_probe,
                roster_row=eff_roster,
                contact_row=eff_contact,
                primary_property=primary_property,
                contacts=contacts if contacts is not None else [],
                person_ties=person_ties if person_ties is not None else [],
                household_cache=household_cache,
                player_last_name=player_last_name if player_last_name is not None else "",
            )
        )
    else:
        res_kwargs: Dict[str, Any] = {}
        if roster_row is not None or eff_roster is not None:
            res_kwargs["roster_row"] = eff_roster
        if contact_row is not None or eff_contact is not None:
            res_kwargs["contact_row"] = eff_contact
        if primary_property is not None:
            res_kwargs["primary_property"] = primary_property
        if contacts is not None:
            res_kwargs["contacts"] = contacts
        if person_ties is not None:
            res_kwargs["person_ties"] = person_ties
        if household_cache is not None:
            res_kwargs["household_cache"] = household_cache
        if player_last_name is not None:
            res_kwargs["player_last_name"] = player_last_name
        residence_unlocked = bool(can_materialize_npc_residence(sid, exempt_probe, **res_kwargs))

    real_home = ""
    for cand_home in (
        (eff_roster or {}).get("home_node_id"),
        r_basic.get("home_node_id"),
        (eff_contact or {}).get("home_node_id"),
        c_basic.get("home_node_id"),
        npc_map.get("home_node_id"),
        npc_basic.get("home_node_id"),
    ):
        val = str(cand_home or "").strip()
        if val and val != SHARED_ABSTRACT_RESIDENCE_NODE:
            real_home = val
            break

    workplace_node_id = str(
        (eff_roster or {}).get("workplace_node_id")
        or r_basic.get("workplace_node_id")
        or npc_map.get("workplace_node_id")
        or npc_basic.get("workplace_node_id")
        or ""
    ).strip()

    raw_shift = str(
        (eff_roster or {}).get("shift_profile")
        or r_basic.get("shift_profile")
        or c_basic.get("shift_profile")
        or npc_map.get("shift_profile")
        or npc_basic.get("shift_profile")
        or ""
    ).strip().lower()
    if raw_shift == "roaming":
        raw_shift = "roaming_merchant"

    if full_schedule_unlocked:
        probe = _build_probe_dict(
            npc_map,
            eff_roster,
            eff_contact,
            residence_unlocked=residence_unlocked,
            real_home=real_home,
        )
        eff_npc_name = str(probe.get("name") or npc_name).strip()
        weekday_blocks = _resolve_full_day_blocks(
            probe,
            candidate_days=(1, 2, 3, 4, 5),
            scen_key=scen_key,
            nodes_by_id=eff_nodes,
            residence_unlocked=residence_unlocked,
            real_home=real_home,
            workplace_node_id=workplace_node_id,
            npc_name=eff_npc_name,
            lang=eff_lang,
        )
        weekend_blocks = _resolve_full_day_blocks(
            probe,
            candidate_days=(6, 7),
            scen_key=scen_key,
            nodes_by_id=eff_nodes,
            residence_unlocked=residence_unlocked,
            real_home=real_home,
            workplace_node_id=workplace_node_id,
            npc_name=eff_npc_name,
            lang=eff_lang,
        )
    else:
        discovered_slots = _extract_discovered_slots(npc_map, eff_roster, eff_contact)
        weekday_blocks = {}
        weekend_blocks = {}
        for dk, target in (("weekday", weekday_blocks), ("weekend", weekend_blocks)):
            slot_map = discovered_slots.get(dk) or {}
            for block in ROUTINE_BLOCKS:
                raw_val = ""
                for cand_key in _LEGACY_BLOCK_FALLBACKS.get(block, (block,)):
                    v = str(slot_map.get(cand_key) or "").strip()
                    if v:
                        raw_val = v
                        break
                if raw_val:
                    resolved = _resolve_node_label(
                        raw_val,
                        nodes_by_id=eff_nodes,
                        residence_unlocked=residence_unlocked,
                        real_home=real_home,
                        workplace_node_id=workplace_node_id,
                        npc_name=npc_name,
                        lang=eff_lang,
                    )
                    target[block] = resolved or masked_slot
                else:
                    target[block] = masked_slot

    discovered_count = sum(
        1
        for dk_map in (weekday_blocks, weekend_blocks)
        for block in ROUTINE_BLOCKS
        if str(dk_map.get(block) or "").strip() not in ("", masked_slot, "???")
    )

    return {
        "weekday": weekday_blocks,
        "weekend": weekend_blocks,
        "full_schedule_unlocked": full_schedule_unlocked,
        "has_anchor_schedule": has_anchor_schedule,
        "residence_unlocked": residence_unlocked,
        "discovered_count": discovered_count,
        "shift_profile": raw_shift,
    }


def format_known_routine_summary(routine: Mapping[str, Any], *, lang: str = "en") -> str:
    """
    Produces a deterministic localized summary of a `known_routine` payload
    without leaking raw internal node IDs or unrevealed residences.
    """
    eff_lang = locales.normalize_social_lang(lang)
    masked_slot = locales.get_masked_placeholder("slot", lang=eff_lang)
    if not isinstance(routine, Mapping):
        return locales.get_masked_placeholder("schedule", lang=eff_lang)

    weekday = routine.get("weekday") if isinstance(routine.get("weekday"), Mapping) else {}
    weekend = routine.get("weekend") if isinstance(routine.get("weekend"), Mapping) else {}
    res_unlocked = bool(routine.get("residence_unlocked"))
    fog_label = get_residential_fog_label(eff_lang)
    all_fog_labels = set(RESIDENTIAL_FOG_LABELS.values())

    def _clean_cell(val: Any) -> str:
        s = str(val or "").strip()
        if not s:
            return masked_slot
        low = s.lower()
        if s == SHARED_ABSTRACT_RESIDENCE_NODE or any(low.startswith(p) for p in _INTERNAL_RES_PREFIXES):
            return fog_label if not res_unlocked else _humanize_node_id(s, lang=eff_lang)
        if not res_unlocked and _is_residential_label(s, fog_labels=all_fog_labels):
            return fog_label
        return s

    has_any = any(
        _clean_cell(dk_map.get(b)) not in ("", masked_slot, "???")
        for dk_map in (weekday, weekend)
        for b in ROUTINE_BLOCKS
    )
    if not has_any and not routine.get("full_schedule_unlocked"):
        return locales.get_masked_placeholder("schedule", lang=eff_lang)

    wd_title, we_title = _SUMMARY_DAY_LABELS.get(eff_lang, _SUMMARY_DAY_LABELS["en"])
    blk_labels = _SUMMARY_BLOCK_LABELS.get(eff_lang, _SUMMARY_BLOCK_LABELS["en"])
    lines: List[str] = []
    for title, dk_map in ((wd_title, weekday), (we_title, weekend)):
        parts = [f"{blk_labels[b]}: {_clean_cell(dk_map.get(b))}" for b in ROUTINE_BLOCKS]
        lines.append(f"{title}: " + " | ".join(parts))
    return "\n".join(lines)


def apply_known_routine_to_contact(
    contact: Dict[str, Any],
    known_routine: Mapping[str, Any],
    *,
    lang: str = "en",
) -> Dict[str, Any]:
    """Attaches `known_routine` and syncs schedule fields while preserving revealed legacy text."""
    eff_lang = locales.normalize_social_lang(lang)
    masked_sched = locales.get_masked_placeholder("schedule", lang=eff_lang)
    routine_dict = dict(known_routine) if isinstance(known_routine, Mapping) else {}
    contact["known_routine"] = routine_dict
    routine_summary = format_known_routine_summary(routine_dict, lang=eff_lang)
    has_anchor = bool(routine_dict.get("has_anchor_schedule"))

    def _has_authored(val: Any) -> bool:
        s = str(val or "").strip()
        return bool(s and s != masked_sched and "???" not in s)

    b_cur = contact.get("basic_info") if isinstance(contact.get("basic_info"), dict) else {}

    if has_anchor:
        if routine_dict.get("full_schedule_unlocked"):
            contact["schedule_revealed"] = True
            contact["known_schedule"] = routine_summary
            if "schedule_summary" in contact or contact.get("schedule_summary") is not None:
                contact["schedule_summary"] = routine_summary
        else:
            contact["schedule_revealed"] = False
            eff_val = routine_summary if int(routine_dict.get("discovered_count") or 0) > 0 else masked_sched
            contact["known_schedule"] = eff_val
            if "schedule_summary" in contact or contact.get("schedule_summary") is not None:
                contact["schedule_summary"] = eff_val
    else:
        if routine_dict.get("full_schedule_unlocked") or contact.get("schedule_revealed"):
            authored = next(
                (
                    str(c_val).strip()
                    for c_val in (
                        contact.get("known_schedule"),
                        contact.get("schedule_summary"),
                        b_cur.get("known_schedule"),
                        b_cur.get("schedule_summary"),
                    )
                    if _has_authored(c_val)
                ),
                "",
            )
            contact["schedule_revealed"] = True
            if authored:
                if not _has_authored(contact.get("known_schedule")):
                    contact["known_schedule"] = authored
                if (
                    "schedule_summary" in contact or contact.get("schedule_summary") is not None
                ) and not _has_authored(contact.get("schedule_summary")):
                    contact["schedule_summary"] = authored
            else:
                contact["known_schedule"] = routine_summary
                if "schedule_summary" in contact or contact.get("schedule_summary") is not None:
                    contact["schedule_summary"] = routine_summary
        else:
            contact["schedule_revealed"] = False
            eff_val = routine_summary if int(routine_dict.get("discovered_count") or 0) > 0 else masked_sched
            contact["known_schedule"] = eff_val
            if "schedule_summary" in contact or contact.get("schedule_summary") is not None:
                contact["schedule_summary"] = eff_val

    if isinstance(contact.get("basic_info"), dict) and (
        "known_schedule" in contact["basic_info"] or "schedule_summary" in contact["basic_info"]
    ):
        contact["basic_info"] = dict(contact["basic_info"])
        if has_anchor or not contact["schedule_revealed"]:
            if "known_schedule" in contact["basic_info"]:
                contact["basic_info"]["known_schedule"] = contact["known_schedule"]
            if "schedule_summary" in contact["basic_info"]:
                contact["basic_info"]["schedule_summary"] = (
                    contact.get("schedule_summary")
                    if ("schedule_summary" in contact and contact["schedule_summary"] is not None)
                    else contact["known_schedule"]
                )
        else:
            if "known_schedule" in contact["basic_info"] and not _has_authored(contact["basic_info"]["known_schedule"]):
                contact["basic_info"]["known_schedule"] = contact["known_schedule"]
            if "schedule_summary" in contact["basic_info"] and not _has_authored(contact["basic_info"]["schedule_summary"]):
                contact["basic_info"]["schedule_summary"] = contact.get("schedule_summary") or contact["known_schedule"]

    return contact
