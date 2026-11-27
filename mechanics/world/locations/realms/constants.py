from __future__ import annotations
"""Static constants, default rules, template catalog loader, and ID helpers for REALM boundaries."""

import json
import os
import re
from typing import Any

PORTAL_EDGE_TYPES: frozenset[str] = frozenset({
    "planar_portal",
    "dimensional_rift",
    "ftl_jump",
    "shuttle_route",
    "leyline_spirit_passage",
})

DEFAULT_REALM_RULES: dict[str, Any] = {
    "realm_kind": "world",
    "is_primary_realm": False,
    "is_hidden": False,
    "discovered": True,
    "comms_isolated": False,
    "npc_spillover": False,
    "time_scale": 1.0,
    "has_local_safe_hub": True,
    "exit_mode": "open",
    "is_ephemeral": False,
    "is_mobile_vessel": False,
    "bridge_node_id": "",
    "airlock_node_id": "",
    "docked_realm_id": "",
    "docked_node_id": "",
    "docked_realm_id_prev": "",
    "docked_node_id_prev": "",
    "docked_turn": 0,
    "dock_node_id": "",
    "ephemeral_origin_node_id": "",
    "ephemeral_origin_realm_id": "",
    "template_id": "",
    "pacified": False,
    "pacified_turn": 0,
    "created_turn": 0,
    "discovered_turn": 0,
    "started_hidden": False,
    "restrict_companions": False,
    "portal_icon": "",
}

_DYNAMIC_TEMPLATES_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "..",
        "data",
        "dynamic_realm_templates.json",
    )
)


def _load_dynamic_realm_templates() -> dict[str, dict[str, Any]]:
    try:
        if os.path.isfile(_DYNAMIC_TEMPLATES_PATH):
            with open(_DYNAMIC_TEMPLATES_PATH, "r", encoding="utf-8") as fh:
                parsed = json.load(fh)
            if isinstance(parsed, dict):
                return {
                    str(k): dict(v)
                    for k, v in parsed.items()
                    if isinstance(v, dict)
                }
    except Exception:
        pass
    return {}


DYNAMIC_REALM_TEMPLATES: dict[str, dict[str, Any]] = _load_dynamic_realm_templates()


def _slugify_id(text: str) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", str(text or "").lower()).strip()
    return re.sub(r"[-\s]+", "_", cleaned) or "realm"


def _default_primary_realm_meta(scenario_key: str) -> tuple[str, str]:
    scen = str(scenario_key or "world").strip().lower()
    slug = _slugify_id(scen or "world")
    if "anomalous" in scen or "urban_anomalies" in scen or "urban_fantasy" in scen:
        return (f"realm_{slug}_city", "Metropolitan District")
    if "sci_fi" in scen or "space" in scen:
        return ("realm_scifi_station", "Central Orbital Sector")
    if "high_school" in scen or "slice_of_life" in scen:
        return (f"realm_{slug}_primary", "Local World")
    return (f"realm_{slug}_primary", "Mortal World")
