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


def roll_quality_tier() -> str:
    """Rolls an item quality tier: worn (15%), regular (60%), high_quality (20%), masterwork (5%)."""
    r = random.random()
    if r < 0.05:
        return "masterwork"
    elif r < 0.25:
        return "high_quality"
    elif r < 0.40:
        return "worn"
    return "regular"


def roll_enchantment_tier() -> str:
    """Rolls an enchantment tier: none (65%), tier_3 (20%), tier_2 (12%), tier_1 (3%)."""
    r = random.random()
    if r < 0.03:
        return "tier_1"
    elif r < 0.15:
        return "tier_2"
    elif r < 0.35:
        return "tier_3"
    return "none"


def parse_dual_axis_tiers(item_or_meta: Dict[str, Any]) -> Tuple[str, str, int]:
    """
    Extracts (quality_tier, enchantment_tier, legacy_tier) from an item or metadata dict.
    Backwards compatible: if dual-axis tiers are missing, deterministically derives them from legacy 'tier'.
    """
    if not item_or_meta or not isinstance(item_or_meta, dict):
        return ("regular", "none", 3)

    meta = item_or_meta.get("metadata") if isinstance(item_or_meta.get("metadata"), dict) else item_or_meta
    q_tier = meta.get("quality_tier")
    e_tier = meta.get("enchantment_tier")
    raw_tier = meta.get("tier")

    try:
        legacy_tier = int(raw_tier) if raw_tier is not None else 3
        if legacy_tier not in (1, 2, 3):
            legacy_tier = 3
    except (TypeError, ValueError):
        legacy_tier = 3

    if not q_tier or not e_tier:
        def_q, def_e = LEGACY_TIER_TO_DUAL_AXIS.get(legacy_tier, ("regular", "none"))
        q_tier = q_tier or def_q
        e_tier = e_tier or def_e

    q_str = str(q_tier).lower()
    e_str = str(e_tier).lower()
    derived_legacy = derive_legacy_tier(q_str, e_str)
    return (q_str, e_str, derived_legacy)


def normalize_dual_tier_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Ensures metadata has synchronized quality_tier, enchantment_tier, and tier."""
    if not isinstance(metadata, dict):
        return {}
    q_t, e_t, l_t = parse_dual_axis_tiers(metadata)
    metadata["quality_tier"] = q_t
    metadata["enchantment_tier"] = e_t
    metadata["tier"] = l_t
    q_name = QUALITY_NAMES.get(q_t, "Standard")
    e_name = ENCHANTMENT_NAMES.get(e_t, "Mundane")
    metadata["quality_name"] = q_name
    metadata["enchantment_name"] = e_name
    metadata["tier_name"] = f"{q_name} ({e_name})" if e_t != "none" else q_name
    return metadata



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

    from localization import TWO_HANDED_ARCHETYPES, TWO_HANDED_KEYWORDS

    if any(k in arch for k in TWO_HANDED_ARCHETYPES):
        return True
    if any(k in name_str for k in TWO_HANDED_KEYWORDS):
        return True
    return False


def build_equipment_effect_str(metadata: Dict[str, Any]) -> str:
    """Serializes structured equipment metadata into a JSON string for SQLite storage."""
    return f"[GEAR_JSON]{json.dumps(metadata)}"


def parse_equipment_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts structured gear metadata from an item dictionary, parsing JSON from
    the 'effect' string or falling back to intelligent archetype heuristics.
    Ensures dual-axis tiers (quality_tier, enchantment_tier) and legacy tier aggregate
    are always normalized and populated.
    """
    if not item or not isinstance(item, dict):
        return {}

    if "metadata" in item and isinstance(item["metadata"], dict):
        return normalize_dual_tier_metadata(item["metadata"])

    effect_raw = str(item.get("effect", "") or "")
    parsed = None
    for prefix in ("[ITEM_JSON]", "[GEAR_JSON]", "[SPELLBOOK_JSON]"):
        if effect_raw.startswith(prefix):
            try:
                parsed = json.loads(effect_raw[len(prefix):])
                break
            except Exception:
                pass

    if parsed is not None and isinstance(parsed, dict):
        return normalize_dual_tier_metadata(parsed)

    if "base_dt" in item or "multiplier" in item or "type_dt" in item:
        return normalize_dual_tier_metadata(dict(item))

    # Minimal default for unknown un-encoded items
    default_meta = {
        "name": item.get("name", "Unknown Item"),
        "item_type": item.get("item_type", "Item"),
        "archetype": "unknown",
        "tier": 3,
        "quality_tier": "regular",
        "enchantment_tier": "none",
        "base_dt": 0,
        "multiplier": 1.0,
        "stat_modifiers": {}
    }
    return normalize_dual_tier_metadata(default_meta)


