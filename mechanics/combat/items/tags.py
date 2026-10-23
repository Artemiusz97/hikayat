from __future__ import annotations
from typing import Dict, Any, List, Optional
import copy

HANDEDNESS = ["1H", "2H", "Versatile"]
MASS = ["light", "medium", "heavy"]
ATTACK_TYPES = ["slashing", "stabbing", "bludgeoning", "cleaving", "ranged", "channeling", "aoe"]
DAMAGE_TYPES = ["physical", "fire", "shock", "ice", "poison", "holy", "dark", "ballistic", "energy", "explosive", "acid", "magical", "earth", "water", "wind"]
ARMOR_CLASSES = ["unarmored", "light", "medium", "heavy", "power_armor"]
CLOTHING_STYLES = [
    "casual", "formal", "academic_uniform", "athletic", "cozy", "traditional",
    "streetwear", "luxury", "period_formal", "period_couture", "period_casual",
    "outerwear", "techwear", "futuristic", "cyberpunk"
]

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


NARRATIVE_TAG_SYNONYMS = {"narrative", "non-combat", "non_combat", "cosmetic"}


def is_narrative_item(item_or_meta: dict | None) -> bool:
    """Returns True if the item or item metadata is tagged as a narrative / non-combat prop."""
    if not isinstance(item_or_meta, dict):
        return False
    if item_or_meta.get("is_narrative") is True or item_or_meta.get("is_cosmetic") is True:
        return True
    meta = item_or_meta.get("metadata")
    if isinstance(meta, dict):
        if meta.get("is_narrative") is True or meta.get("is_cosmetic") is True:
            return True
        flat_meta_tags = [str(t).lower() for t in get_flat_tag_list(meta)]
        if any(t in NARRATIVE_TAG_SYNONYMS for t in flat_meta_tags):
            return True

    flat = [str(t).lower() for t in get_flat_tag_list(item_or_meta)]
    if any(t in NARRATIVE_TAG_SYNONYMS for t in flat):
        return True

    effect = item_or_meta.get("effect")
    if isinstance(effect, str):
        low_eff = effect.lower()
        if "\"is_narrative\": true" in low_eff or "\"is_cosmetic\": true" in low_eff or "\"narrative\"" in low_eff:
            return True
    return False


def make_narrative_metadata(metadata: dict) -> dict:
    """Normalizes item metadata for a narrative prop, ensuring is_narrative=True,
    tagging it with 'narrative', and stripping all combat math / damage bonuses.
    """
    if not isinstance(metadata, dict):
        return metadata
    m = copy.deepcopy(metadata)
    m["is_narrative"] = True
    m["multiplier"] = 1.0
    m["crit_bonus"] = 0
    m["armor_penetration"] = 0.0
    m["stat_modifiers"] = {}
    m["attack_profiles"] = {}
    m["damage_types"] = {"physical": 1.0}
    m["block_chance"] = 0
    m["base_dt"] = 0
    m["base_dr"] = 0.0
    m["base_eva"] = 0

    tags = m.get("tags")
    if isinstance(tags, dict):
        tags_copy = copy.deepcopy(tags)
        traits = list(tags_copy.get("special_traits", []))
        if "narrative" not in traits:
            traits.append("narrative")
        tags_copy["special_traits"] = traits
        m["tags"] = tags_copy
    elif isinstance(tags, list):
        tag_list = list(tags)
        if "narrative" not in tag_list:
            tag_list.append("narrative")
        m["tags"] = tag_list
    else:
        m["tags"] = ["narrative"]
    return m


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
