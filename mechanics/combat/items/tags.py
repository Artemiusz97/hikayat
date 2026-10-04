from __future__ import annotations
from typing import Dict, Any, List, Optional

HANDEDNESS = ["1H", "2H", "Versatile"]
MASS = ["light", "medium", "heavy"]
ATTACK_TYPES = ["slashing", "stabbing", "bludgeoning", "cleaving", "ranged", "channeling", "aoe"]
DAMAGE_TYPES = ["physical", "fire", "shock", "ice", "poison", "holy", "dark", "ballistic", "energy", "explosive", "acid", "magical"]
ARMOR_CLASSES = ["unarmored", "light", "medium", "heavy", "power_armor"]
CLOTHING_STYLES = ["casual", "formal", "academic_uniform", "athletic", "cozy", "traditional", "streetwear", "luxury"]

def item_has_tag(item: dict, facet: str, value: str) -> bool:
    """Checks if the item's tags dict has the given value for the given facet."""
    tags = item.get("tags", {})
    if isinstance(tags, dict):
        facet_values = tags.get(facet, [])
        if isinstance(facet_values, list):
            return value in facet_values
        elif isinstance(facet_values, str):
            return value == facet_values
    elif isinstance(tags, list):
        return value in tags
    return False

def get_flat_tag_list(item: dict) -> list[str]:
    """Flattens all tag values from the tags dict into a list."""
    tags = item.get("tags", {})
    if isinstance(tags, list):
        return tags
    flat = []
    if isinstance(tags, dict):
        for facet_vals in tags.values():
            if isinstance(facet_vals, list):
                flat.extend(facet_vals)
            elif isinstance(facet_vals, str):
                flat.append(facet_vals)
    return flat

PROJECTILE_TYPES = ["arrow", "bolt", "pistol_round", "rifle_round", "high_caliber_round", "scatter_shot", "energy_cell"]

def derive_weapon_tags(
    archetype: str,
    handedness: str,
    mass: str,
    attack_types: list[str],
    damage_types: list[str],
    special_traits: Optional[list[str]] = None,
    projectile_type: Optional[str] = None
) -> dict:
    tags = {
        "archetype": archetype,
        "handedness": handedness,
        "mass": mass,
        "attack_types": attack_types,
        "damage_types": damage_types,
        "special_traits": special_traits or []
    }
    if projectile_type:
        tags["projectile_type"] = projectile_type
    return tags

def derive_armor_tags(armor_class: str, protection_types: list[str], resistances: Optional[list[str]] = None, special_traits: Optional[list[str]] = None) -> dict:
    return {
        "armor_class": armor_class,
        "protection_types": protection_types,
        "resistances": resistances or [],
        "special_traits": special_traits or []
    }

def derive_clothing_tags(style: str, social_vibe: Optional[list[str]] = None, comfort: Optional[str] = None) -> dict:
    return {
        "style": style,
        "social_vibe": social_vibe or [],
        "comfort": comfort or "normal"
    }

def derive_consumable_tags(consumable_type: str, delivery: str, purpose: list[str], effects: list[str], taste: Optional[list[str]] = None, social_flags: Optional[list[str]] = None) -> dict:
    return {
        "consumable_type": consumable_type,
        "delivery": delivery,
        "purpose": purpose,
        "effects": effects,
        "taste": taste or [],
        "social_flags": social_flags or []
    }

def derive_spell_tags(discipline: str, school: str, element: str, shape: str, target_type: str, tier: int, status_infliction: Optional[list[str]] = None) -> dict:
    return {
        "discipline": discipline,
        "school": school,
        "element": element,
        "shape": shape,
        "target_type": target_type,
        "tier": str(tier),
        "status_infliction": status_infliction or []
    }
