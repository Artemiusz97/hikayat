from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import db
import scenario_data

_CATALOG_PATH = Path(__file__).resolve().parents[3] / "data" / "anomalous_sites_catalog.json"

THEME_PARK_SITE_ID = "loc_theme_park"
THEME_PARK_EPICENTER_IDS: frozenset[str] = frozenset({
    "loc_tp_mirror_labyrinth",
    "loc_tp_midnight_carousel",
})
THEME_PARK_SUB_IDS: frozenset[str] = frozenset({
    "loc_tp_main_midway",
    "loc_tp_coaster_plaza",
    "loc_tp_ferris_wheel",
    "loc_tp_water_lagoon",
    "loc_tp_haunted_mansion",
    "loc_tp_mirror_labyrinth",
    "loc_tp_midnight_carousel",
})
AHS_PROTECTED_SUB_IDS: frozenset[str] = frozenset({
    "loc_delinquent_boiler_den",
})
SAFE_EXCLUSION_SITE_IDS: frozenset[str] = frozenset({
    "loc_hq_containment_sector",
    "loc_et_fox_torii_tunnel",
})


@lru_cache(maxsize=1)
def load_anomalous_sites_catalog() -> dict[str, Any]:
    """Load and cache the master anomalous sites catalog JSON."""
    raw = _CATALOG_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def _build_indexes() -> tuple[
    dict[str, dict[str, Any]],
    dict[str, str],
    list[tuple[str, str]],
    frozenset[str],
    frozenset[str],
    frozenset[str],
]:
    cat = load_anomalous_sites_catalog()
    sites_raw = cat.get("sites")
    sites: dict[str, dict[str, Any]] = {}
    sub_to_site: dict[str, str] = {}
    kw_pairs: list[tuple[str, str]] = []
    wild_ids: set[str] = set()
    hq_ids: set[str] = set()
    spatial_ids: set[str] = set()

    if isinstance(sites_raw, dict):
        for sid, spec in sites_raw.items():
            if not isinstance(spec, dict):
                continue
            sites[sid] = spec
            sub_to_site[sid.lower()] = sid
            for sub_id in spec.get("sub_ids") or ():
                sub_low = str(sub_id or "").strip().lower()
                if sub_low:
                    sub_to_site[sub_low] = sid

            stype = str(spec.get("site_type") or "")
            if stype in ("wild_facility", "embedded_wing"):
                wild_ids.add(sid)
            elif stype == "hostile_hq":
                hq_ids.add(sid)

            rule = spec.get("domain_rule")
            if isinstance(rule, dict) and int(rule.get("spatial_loop_dc") or 0) > 0:
                spatial_ids.add(sid)

            cname = str(spec.get("name") or "").strip().lower()
            if cname:
                kw_pairs.append((cname, sid))
            for kw in spec.get("name_keywords") or ():
                kw_low = str(kw or "").strip().lower()
                if kw_low:
                    kw_pairs.append((kw_low, sid))

    # Match longer keywords first so embedded wing names beat parent names.
    kw_pairs.sort(key=lambda item: len(item[0]), reverse=True)
    return (
        sites,
        sub_to_site,
        kw_pairs,
        frozenset(wild_ids),
        frozenset(hq_ids),
        frozenset(spatial_ids),
    )


def get_pacifiable_wild_site_ids() -> frozenset[str]:
    """Return the exact frozenset of all 36 pacifiable wild site IDs."""
    return _build_indexes()[3]


def get_hostile_hq_site_ids() -> frozenset[str]:
    """Return the frozenset of un-pacifiable hostile faction HQ site IDs."""
    return _build_indexes()[4]


def get_spatial_loop_site_ids() -> frozenset[str]:
    """Return all catalog site IDs whose Domain Rule includes a spatial exit loop."""
    return _build_indexes()[5]


PACIFIABLE_WILD_SITE_IDS: frozenset[str] = get_pacifiable_wild_site_ids()
HOSTILE_HQ_SITE_IDS: frozenset[str] = get_hostile_hq_site_ids()
SPATIAL_LOOP_SITE_IDS: frozenset[str] = get_spatial_loop_site_ids()


def parse_node_state(node: Mapping[str, Any] | None) -> dict[str, Any]:
    """Safely extract `state_json` as a dictionary from a world_nodes row."""
    if not isinstance(node, Mapping):
        return {}
    raw = node.get("state_json")
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def get_anomalous_site_spec(site_id: str) -> dict[str, Any] | None:
    """Return a catalog entry by exact `site_id` or child `sub_id`, else None."""
    key = str(site_id or "").strip().lower()
    if not key or key in AHS_PROTECTED_SUB_IDS or key in SAFE_EXCLUSION_SITE_IDS:
        return None
    sites, sub_to_site, _, _, _, _ = _build_indexes()
    canonical = sub_to_site.get(key)
    return sites.get(canonical) if canonical else None


def resolve_anomalous_site(
    node_id: str = "",
    parent_id: str = "",
    location_str: str = "",
    curr_node: Mapping[str, Any] | None = None,
    session_nodes: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """
    Resolve an anomalous site catalog entry cleanly from node IDs, parent IDs,
    or procedural epithet location strings.
    """
    eff_nid = str(node_id or (curr_node.get("node_id") if isinstance(curr_node, Mapping) else "") or "").strip().lower()
    eff_pid = str(parent_id or (curr_node.get("parent_id") if isinstance(curr_node, Mapping) else "") or "").strip().lower()

    if eff_nid in SAFE_EXCLUSION_SITE_IDS or eff_nid in AHS_PROTECTED_SUB_IDS:
        return None
    if isinstance(curr_node, Mapping):
        st = parse_node_state(curr_node)
        if st.get("is_minor_club_hq") or (st.get("is_faction_hq") and eff_nid == "loc_delinquent_boiler_den"):
            return None

    sites, sub_to_site, kw_pairs, _, _, _ = _build_indexes()

    # 1. Exact node_id match (highest priority: works for embedded wings & wild rooms)
    if eff_nid and eff_nid in sub_to_site:
        return sites.get(sub_to_site[eff_nid])

    # 2. Parent facility match ONLY when parent itself is a standalone anomalous site or Theme Park / HQ
    if eff_pid and eff_pid in sites:
        parent_spec = sites[eff_pid]
        if parent_spec.get("site_type") != "embedded_wing":
            return parent_spec

    # 3. Inspect provided world_nodes if location_str matches a seeded node with procedural epithet
    loc_low = str(location_str or "").strip().lower()
    if loc_low and session_nodes:
        # Sort longest node names first to prevent partial prefix collisions
        for wn in session_nodes:
            if not isinstance(wn, Mapping):
                continue
            wnid = str(wn.get("node_id") or "").strip().lower()
            wpid = str(wn.get("parent_id") or "").strip().lower()
            wname = str(wn.get("name") or "").strip().lower()
            if not wname or wname not in loc_low:
                continue
            if wnid in SAFE_EXCLUSION_SITE_IDS or wnid in AHS_PROTECTED_SUB_IDS:
                return None
            if wnid in sub_to_site:
                return sites.get(sub_to_site[wnid])
            if wpid in sites and sites[wpid].get("site_type") != "embedded_wing":
                return sites[wpid]

    # 4. Safe exclusions check in location string before fallback keyword matching
    if any(ex in loc_low for ex in ("containment & quarantine sector", "fox-spirit torii", "thousand-torii fox")):
        return None

    if loc_low:
        for kw, sid in kw_pairs:
            if kw in loc_low:
                return sites.get(sid)

    return None


def is_site_dormant_by_schedule(
    spec: Mapping[str, Any] | None,
    scen_key: str = "",
    current_minute: int = 720,
    node_id: str = "",
) -> bool:
    """
    Return True when an anomalous site is in its harmless public/daytime schedule phase:
    - Theme Park (`loc_theme_park`): dormant 08:00–21:59 (`480 <= tod < 1320`).
    - Campus Anomalies (`loc_abandoned_school_wing`, `loc_13th_stairwell`) in
      `anomalous_high_school`: dormant 06:00–19:59 (`360 <= tod < 1200`).
    """
    if not isinstance(spec, Mapping):
        return False
    _ = node_id
    tod = int(current_minute or 0) % 1440
    sid = str(spec.get("site_id") or "")
    if sid == THEME_PARK_SITE_ID:
        return 480 <= tod < 1320
    if bool(spec.get("ahs_night_only")) and scenario_data.is_anomalous_high_school_scenario(scen_key):
        return 360 <= tod < 1200
    return False


def get_site_state_dict(
    session_id: int,
    site_id: str,
    world_nodes: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Return merged persistent `anomalous_site` metadata from `world_nodes.state_json`
    for `site_id` (checking the canonical site node and its direct child rooms).
    """
    spec = get_anomalous_site_spec(site_id)
    target_site_id = str(spec.get("site_id") if spec else site_id or "").strip()
    if not session_id or not target_site_id:
        return {}

    nodes = list(world_nodes) if world_nodes is not None else (db.get_session_world_nodes(int(session_id)) or [])
    candidate_ids = {target_site_id}
    if spec:
        candidate_ids.update(str(s) for s in (spec.get("sub_ids") or ()))

    merged: dict[str, Any] = {}
    # Read child rows first, then let canonical site node override/complete
    child_states: list[dict[str, Any]] = []
    primary_state: dict[str, Any] = {}
    for n in nodes:
        if not isinstance(n, Mapping):
            continue
        nid = str(n.get("node_id") or "").strip()
        if nid not in candidate_ids:
            continue
        st = parse_node_state(n)
        site_st = st.get("anomalous_site")
        if isinstance(site_st, dict):
            if nid == target_site_id:
                primary_state = dict(site_st)
            else:
                child_states.append(dict(site_st))

    for cs in child_states:
        for k, v in cs.items():
            if k not in merged or (k == "pacified" and v):
                merged[k] = v
    for k, v in primary_state.items():
        if k == "pacified":
            merged[k] = bool(merged.get("pacified") or v)
        else:
            merged[k] = v
    return merged


def is_site_pacified(
    session_id: int,
    site_id: str = "",
    location_name: str = "",
    node_id: str = "",
    world_nodes: Iterable[Mapping[str, Any]] | None = None,
) -> bool:
    """Return True if a pacifiable wild site has been stabilized in this session."""
    if not session_id:
        return False
    nodes = list(world_nodes) if world_nodes is not None else (db.get_session_world_nodes(int(session_id)) or [])
    spec = resolve_anomalous_site(
        node_id=node_id or site_id,
        location_str=location_name,
        session_nodes=nodes,
    )
    if not spec or spec.get("site_type") in ("theme_park_night", "hostile_hq"):
        return False
    st = get_site_state_dict(int(session_id), str(spec["site_id"]), world_nodes=nodes)
    return bool(st.get("pacified"))


def is_spatial_loop_site(
    site_or_id: str | Mapping[str, Any],
    node_id: str = "",
) -> bool:
    """Return True if the resolved site/room actively imposes a Spatial-Loop exit check."""
    if isinstance(site_or_id, Mapping):
        spec: Mapping[str, Any] | None = site_or_id
    else:
        spec = get_anomalous_site_spec(str(site_or_id or ""))
    if not spec:
        return False
    rule = spec.get("domain_rule")
    if not isinstance(rule, Mapping) or int(rule.get("spatial_loop_dc") or 0) <= 0:
        return False
    scoped_subs = rule.get("spatial_loop_sub_ids")
    if scoped_subs and node_id:
        return str(node_id).strip().lower() in {str(x).lower() for x in scoped_subs}
    return True


def is_theme_park_witching_peak(current_minute: int = 720) -> bool:
    """Return True during Theme Park Witching Peak (`00:00–02:59`, `0 <= tod < 180`)."""
    tod = int(current_minute or 0) % 1440
    return 0 <= tod < 180


def is_theme_park_night_shift(current_minute: int = 720) -> bool:
    """Return True during Theme Park Nightly Anomalous Shift (`22:00–07:59`)."""
    tod = int(current_minute or 0) % 1440
    return tod >= 1320 or tod < 480


def mutate_anomalous_site_state(
    session_id: int,
    site_id: str,
    turn_number: int,
    updates: Mapping[str, Any],
    world_nodes: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Atomically update `world_nodes.state_json["anomalous_site"]` for `site_id`,
    recording a single-turn rollback snapshot in `anomalous_site_prev` stamped
    with `updated_turn` so `rollback_anomalous_sites_after_turn()` reverts cleanly.
    """
    spec = get_anomalous_site_spec(site_id)
    target_site_id = str(spec["site_id"] if spec else site_id or "").strip()
    if not session_id or not target_site_id:
        return {}

    prev_site = get_site_state_dict(int(session_id), target_site_id, world_nodes=world_nodes)
    cur_raw = db.get_world_node_state(int(session_id), target_site_id) or {}
    existing_prev = cur_raw.get("anomalous_site_prev")
    # Preserve pre-turn snapshot within the same turn if multiple mutations occur
    if not isinstance(existing_prev, dict) or int(existing_prev.get("updated_turn") or -1) < int(turn_number):
        snapshot_prev = dict(prev_site)
        snapshot_prev["updated_turn"] = int(turn_number)
    else:
        snapshot_prev = dict(existing_prev)

    new_site = dict(prev_site)
    new_site.update(dict(updates or {}))
    new_site["updated_turn"] = int(turn_number)

    db.update_world_node_state(
        int(session_id),
        target_site_id,
        {
            "is_anomalous": True,
            "anomalous_site": new_site,
            "anomalous_site_prev": snapshot_prev,
        },
    )
    return new_site


def get_site_crowd_stillness_text(
    location_str: str = "",
    scen_key: str = "anomalous_incursions",
    current_minute: int = 720,
    node_id: str = "",
) -> str:
    """
    Return haunting quarantine stillness prose when inside an active anomalous site,
    or empty string if mundane crowd flavor should apply (e.g. daytime Theme Park or safe venue).
    """
    if not scenario_data.is_anomalous_incursions_scenario(scen_key):
        return ""
    spec = resolve_anomalous_site(node_id=node_id, location_str=location_str)
    if not spec:
        return ""
    if is_site_dormant_by_schedule(spec, scen_key=scen_key, current_minute=current_minute, node_id=node_id):
        return ""
    return str(spec.get("crowd_stillness_prose") or "").strip()
