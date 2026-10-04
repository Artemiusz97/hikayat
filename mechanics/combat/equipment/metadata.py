from __future__ import annotations
"""
Equipment metadata parsing, 2H detection, tier rolling, and JSON effect serialization.
"""
import json
import random
import re
from typing import Dict, Any, List, Optional, Tuple

from .tables import *

def roll_tier() -> int:
    """Rolls an item tier according to weighted chances (3: 70%, 2: 25%, 1: 5%)."""
    r = random.random()
    if r < TIER_WEIGHTS[1]:
        return 1
    elif r < TIER_WEIGHTS[1] + TIER_WEIGHTS[2]:
        return 2
    return 3


def is_two_handed(item: Any) -> bool:
    """Checks if an item, archetype, or item name represents a 2-handed weapon."""
    if not item:
        return False
    if isinstance(item, dict):
        # Check explicit metadata
        meta = parse_equipment_metadata(item)
        if meta.get("handedness") == "2H":
            return True
        if meta.get("handedness") in ("1H", "Versatile"):
            return False
        name_str = item.get("name", "").lower()
        arch = meta.get("archetype", "").lower()
    elif isinstance(item, str):
        name_str = item.lower()
        arch = name_str
    else:
        return False

    # Check against known 2H archetypes and keywords
    heavy_archetypes = [
        "greatsword", "polearm", "warhammer", "staff", "bow", "crossbow",
        "rifle", "shotgun", "machinegun", "explosive", "longsword", "halberd", "pike"
    ]
    if any(k in arch for k in heavy_archetypes):
        return True
    if any(k in name_str for k in ["greatsword", "halberd", "pike", "warhammer", "staff", "bow", "crossbow", "rifle", "shotgun", "machine gun", "cannon", "rocket", "two-handed", "2h"]):
        return True
    return False


def build_equipment_effect_str(metadata: Dict[str, Any]) -> str:
    """Serializes structured equipment metadata into a JSON string for SQLite storage."""
    return f"[GEAR_JSON]{json.dumps(metadata)}"


def parse_equipment_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts structured gear metadata from an item dictionary, parsing JSON from
    the 'effect' string or falling back to intelligent archetype heuristics.
    """
    if not item or not isinstance(item, dict):
        return {}

    if "metadata" in item and isinstance(item["metadata"], dict):
        return item["metadata"]

    effect_raw = str(item.get("effect", "") or "")
    if effect_raw.startswith("[ITEM_JSON]"):
        try:
            return json.loads(effect_raw[len("[ITEM_JSON]"):])
        except Exception:
            pass
    elif effect_raw.startswith("[GEAR_JSON]"):
        try:
            return json.loads(effect_raw[len("[GEAR_JSON]"):])
        except Exception:
            pass
    elif effect_raw.startswith("[SPELLBOOK_JSON]"):
        try:
            return json.loads(effect_raw[len("[SPELLBOOK_JSON]"):])
        except Exception:
            pass

    if "base_dt" in item or "multiplier" in item or "type_dt" in item:
        return item

    # Minimal default for unknown un-encoded items
    return {
        "name": item.get("name", "Unknown Item"),
        "item_type": item.get("item_type", "Item"),
        "archetype": "unknown",
        "tier": 3,
        "base_dt": 0,
        "multiplier": 1.0,
        "stat_modifiers": {}
    }


