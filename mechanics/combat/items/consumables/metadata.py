from __future__ import annotations
import re
from typing import Dict, Any, Optional, List
import db

# -----------------------------------------------------------------------------
# PROCEDURAL TAXONOMY & EFFECT SCALING
# -----------------------------------------------------------------------------

POTION_PURPOSE_TAGS = ["health", "mana", "buff", "debuff", "cure", "throwable", "utility"]

POTION_EFFECT_TAGS = [
    "healing", "mana_restore", "attack_buff", "defense_buff", "resistance_buff", "evasion_buff", "charisma_buff",
    "cure_poison", "cure_bleed", "cure_burn", "cleanse_all", "explosive_fire", "corrosive_acid",
    "toxic_cloud", "paralyze", "sleep"
]

FOOD_TASTE_TAGS = [
    "savory", "sweet", "spicy", "seafood", "vegetarian",
    "comfort", "bakery", "meat", "crispy", "hearty", "luxury"
]

FOOD_EFFECT_TAGS = [
    "healing", "mana_restore", "attack_buff", "defense_buff", "resistance_buff", "charisma_buff", "cleanse_all", "morale_boost"
]

DRINK_TASTE_TAGS = [
    "caffeine", "tea", "coffee", "boba", "juice", "soda",
    "dairy", "alcohol", "smoothie", "infused_water",
    "citrus", "sweet", "bitter", "creamy", "refreshing",
    "spiced", "fizzy", "herbal", "chilled", "warm"
]

DRINK_EFFECT_TAGS = [
    "healing", "mana_restore", "attack_buff", "defense_buff", "resistance_buff", "evasion_buff", "charisma_buff", "cleanse_all", "morale_boost"
]

POTION_SCALING = {
    "healing": {3: 35, 2: 65, 1: 150},
    "mana_restore": {3: 20, 2: 45, 1: 80},
    "attack_buff": {3: 0.15, 2: 0.25, 1: 0.40},   # +15% / +25% / +40% ATK Multiplier
    "defense_buff": {3: 4, 2: 8, 1: 14},           # +4 / +8 / +14 Flat DT (Damage Threshold)
    "resistance_buff": {3: 0.10, 2: 0.20, 1: 0.35}, # +10% / +20% / +35% DR (Damage Resistance)
    "evasion_buff": {3: 8, 2: 15, 1: 22},          # +8% / +15% / +22% EVA
    "charisma_buff": {3: 2, 2: 4, 1: 6},
    "explosive_fire": {3: 35, 2: 60, 1: 100},
    "corrosive_acid": {3: 35, 2: 60, 1: 100},
}

FOOD_SCALING = {
    "healing": {3: 15, 2: 40, 1: 90},
    "mana_restore": {3: 10, 2: 25, 1: 50},
    "attack_buff": {3: 0.08, 2: 0.15, 1: 0.25},   # +8% / +15% / +25% ATK Multiplier
    "defense_buff": {3: 2, 2: 4, 1: 8},           # +2 / +4 / +8 Flat DT
    "resistance_buff": {3: 0.05, 2: 0.10, 1: 0.18}, # +5% / +10% / +18% DR
    "charisma_buff": {3: 1, 2: 3, 1: 6},
}

DRINK_SCALING = {
    "healing": {3: 10, 2: 25, 1: 60},             # Drinks heal moderately less HP than heavy food
    "mana_restore": {3: 18, 2: 38, 1: 75},        # Drinks restore substantially more MP (hydration/caffeine)
    "attack_buff": {3: 0.08, 2: 0.15, 1: 0.25},   # Alcohol/stimulant damage boosts
    "defense_buff": {3: 2, 2: 4, 1: 8},           # Warm tonics / fortified broths
    "resistance_buff": {3: 0.05, 2: 0.10, 1: 0.18},
    "evasion_buff": {3: 6, 2: 12, 1: 18},         # Agility & reflex sips
    "charisma_buff": {3: 2, 2: 4, 1: 6},          # Social drinks & teas enhance charm
}


def serialize_consumable_metadata(meta: Dict[str, Any]) -> str:
    """Serializes consumable metadata into [CONSUMABLE_JSON]{...} format."""
    import json
    return f"[CONSUMABLE_JSON]{json.dumps(meta, separators=(',', ':'))}"


def parse_consumable_metadata(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extracts structured consumable metadata if present."""
    import json
    effect = item.get("effect") or ""
    if isinstance(effect, str) and effect.startswith("[CONSUMABLE_JSON]"):
        try:
            raw_json = effect[len("[CONSUMABLE_JSON]"):]
            return json.loads(raw_json)
        except Exception:
            return None
    # Check direct dictionary properties
    if "purpose_tags" in item or "effect_tags" in item or "taste_tags" in item:
        return item
    return None


def serialize_digital_item_metadata(meta: Dict[str, Any]) -> str:
    """Serializes digital media metadata into [DIGITAL_JSON]{...} format."""
    import json
    return f"[DIGITAL_JSON]{json.dumps(meta, separators=(',', ':'))}"


def parse_digital_item_metadata(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extracts structured digital media metadata if present."""
    import json
    effect = item.get("effect") or ""
    if isinstance(effect, str) and effect.startswith("[DIGITAL_JSON]"):
        try:
            raw_json = effect[len("[DIGITAL_JSON]"):]
            return json.loads(raw_json)
        except Exception:
            return None
    if isinstance(item, dict) and item.get("media_type"):
        return item
    return None


def is_digital_item(item: Dict[str, Any]) -> bool:
    """Returns True if the item is a digital media collectible (photo, video, document)."""
    if not item or not isinstance(item, dict):
        return False
    effect = str(item.get("effect") or "")
    if effect.startswith("[DIGITAL_JSON]"):
        return True
    meta = parse_digital_item_metadata(item)
    if meta:
        return True
    item_type = (item.get("item_type") or "").lower()
    name = (item.get("name") or "").lower()
    if "digital" in item_type or item.get("slot_cost", 1) == 0:
        if any(w in name for w in ["photo", "selfie", "video", "snapshot", "clip", "recording"]):
            return True
    return False


def create_digital_media_item(
    user_id: int,
    contact_name: str,
    media_type: str,
    caption: str,
    subject: str = "",
    tags: Optional[List[str]] = None
) -> Optional[int]:
    """
    Creates a collectible digital photo or video in the player's inventory.
    media_type: 'photo', 'nsfw_photo', 'video', 'nsfw_video'
    Takes 0 inventory slots and is tagged as ['misc', 'digital'].
    """
    import time
    tag_list = list(tags or ["misc", "digital"])
    if "misc" not in tag_list:
        tag_list.append("misc")
    if "digital" not in tag_list:
        tag_list.append("digital")

    # Clean caption of enclosing brackets / headers
    caption_clean = caption.strip().lstrip("[").rstrip("]").strip()
    for prefix in [
        "Attached Intimate Video:", "Attached Video:",
        "Attached Intimate Photo:", "Attached Photo:",
        "Intimate Video:", "Video:", "Intimate Photo:", "Photo:"
    ]:
        if caption_clean.startswith(prefix):
            caption_clean = caption_clean[len(prefix):].strip()

    # Generate title
    subj_label = f" ({subject.strip()})" if subject and subject.strip() else ""
    if media_type in ("nsfw_video", "intimate_video"):
        item_name = f"🔞 Intimate Video: {contact_name}{subj_label}"
    elif media_type in ("video",):
        item_name = f"📹 Video: {contact_name}{subj_label}"
    elif media_type in ("nsfw_photo", "intimate_photo"):
        item_name = f"🔞 Intimate Photo: {contact_name}{subj_label}"
    else:
        item_name = f"📸 Photo: {contact_name}{subj_label}"

    meta = {
        "tags": tag_list,
        "media_type": media_type,
        "contact_name": contact_name,
        "caption": caption_clean,
        "timestamp": time.time()
    }
    effect_str = serialize_digital_item_metadata(meta)
    return db.add_item(user_id, item_name, item_type="Misc", effect=effect_str, slot_cost=0, force=True)


# -----------------------------------------------------------------------------
# DYNAMIC GENRE-BASED NAMING ENGINE
# -----------------------------------------------------------------------------

def normalize_consumable_scenario(genre: str) -> str:
    """Normalizes genre/scenario string to canonical consumable genre key."""
    try:
        from scenario_data import is_anomalous_incursions_scenario
        if is_anomalous_incursions_scenario(genre):
            return "anomalous_incursions"
    except Exception:
        pass
    scen = str(genre or "fantasy").lower().strip()
    if any(w in scen for w in ("anomalous_incursions", "urban_anomalies")):
        return "anomalous_incursions"
    if any(w in scen for w in ("steampunk", "clockwork", "victorian", "aether", "boiler")):
        return "steampunk"
    if any(w in scen for w in ("apocalypse", "apocalyptic", "wasteland", "fallout", "rad", "nuclear")):
        return "post_apocalyptic"
    if any(w in scen for w in ("dark_fantasy", "grim", "gothic", "eldritch", "curse", "blood", "horror")):
        return "dark_fantasy"
    if any(w in scen for w in ("cyber", "sci_fi", "scifi", "tech", "space", "future", "corporate")):
        return "cyberpunk"
    if any(w in scen for w in ("school", "drama", "modern", "slice", "academy")):
        return "high_school"
    return "fantasy"




def parse_item_tier(item: Dict[str, Any]) -> int:
    """
    Returns item tier (1: Legendary/Gourmet/Supreme, 2: Superior/Potent/Hearty, 3: Standard/Minor/Lesser).
    """
    # Direct tag check
    if isinstance(item, dict):
        if "tier" in item and isinstance(item["tier"], int) and item["tier"] in (1, 2, 3):
            return item["tier"]
        meta = parse_consumable_metadata(item)
        if meta and "tier" in meta:
            return meta["tier"]

    name = (item.get("name") or "").lower()
    desc = (item.get("description") or item.get("effect") or "").lower()
    combined = f"{name} {desc}"

    # Tier 1 indicators
    t1_keywords = [
        "supreme", "legendary", "mythic", "gourmet", "feast", "ambrosia", "immortality",
        "rebirth", "titan", "dragon", "primordial", "archmage", "divine", "relic", "masterwork",
        "celestial", "elixir of full restore", "music box", "designer outfit"
    ]
    if any(k in combined for k in t1_keywords) or "[tier 1]" in combined or "👑" in combined:
        return 1

    # Tier 2 indicators
    t2_keywords = [
        "potent", "greater", "superior", "hearty", "bento", "delicacy", "fine", "enchanted",
        "elixir of", "haste", "iron skin", "ogre strength", "restorative salve", "roast",
        "stew", "concoction", "silk scarf", "scented candle", "artisanal"
    ]
    if any(k in combined for k in t2_keywords) or "[tier 2]" in combined or "🔷" in combined:
        return 2

    # Default to Tier 3 (Standard / Minor)
    return 3


def is_key_item(item: Dict[str, Any]) -> bool:
    """
    Returns True if the item is a plot-critical Key Item, Quest item, quest-locked MacGuffin, or narrative artifact.
    """
    if not item or not isinstance(item, dict):
        return False
    if bool(item.get("is_quest_locked")):
        return True
    item_type = (item.get("item_type") or "").strip().lower()
    if item_type in ("key item", "quest", "quest item", "narrative artifact", "narrative"):
        return True
    effect = str(item.get("effect") or "").lower()
    if effect.startswith("important narrative item:") or "narrative artifact" in effect or '"is_key_item": true' in effect or '"is_key_item":true' in effect:
        return True
    return False


def is_giftable_item(item: Dict[str, Any]) -> bool:
    """
    Returns True if the item is suitable as a gift for an NPC or companion.
    """
    item_type = (item.get("item_type") or "").lower()
    name = (item.get("name") or "").lower()

    if item_type in (
        "gift", "food", "drink", "consumable", "accessory", "clothing",
        "top", "bottom", "outerwear", "lingerie", "shoes", "gloves", "head", "headwear", "item", "novelty"
    ):
        return True
    gift_keywords = [
        "parfait", "latte", "coffee", "tea", "boba", "cider", "ale", "wine", "soda", "ramune", "smoothie",
        "cake", "bento", "stew", "roast", "apple", "bread",
        "plushie", "charm", "keychain", "music box", "scarf", "ribbon", "perfume", "lingerie", "corset",
        "chocolate", "snack", "candy", "flower", "bouquet", "gift", "pendant", "ring", "amulet",
        "locket", "bracelet", "necklace", "watch", "hairpin", "blouse", "sweater", "cardigan", "dress", "skirt"
    ]
    return any(k in name for k in gift_keywords)


def parse_item_effect(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parses item metadata into structured gameplay values across 3 tiers.
    Reads explicit tags directly when present.
    """
    # 0. Check digital media items
    if is_digital_item(item):
        d_meta = parse_digital_item_metadata(item) or {}
        return {
            "tier": 3,
            "hp_restore": 0,
            "mp_restore": 0,
            "damage": 0,
            "cure_status": [],
            "inflict_status": [],
            "buffs": {},
            "category": "digital",
            "media_type": d_meta.get("media_type", "photo"),
            "caption": d_meta.get("caption", ""),
            "contact_name": d_meta.get("contact_name", "")
        }

    # 0.5 Check Key Items / Narrative Artifacts
    if is_key_item(item):
        return {
            "tier": 1,
            "hp_restore": 0,
            "mp_restore": 0,
            "damage": 0,
            "cure_status": [],
            "inflict_status": [],
            "buffs": {},
            "category": "key_item"
        }

    # 1. Check structured consumable metadata
    meta = parse_consumable_metadata(item)
    if meta:
        tier = meta.get("tier", 3)
        cat = "utility"
        if meta.get("damage", 0) > 0 or "throwable" in meta.get("purpose_tags", []):
            cat = "throwable"
        elif meta.get("buffs"):
            cat = "buff"
        elif meta.get("mp_restore", 0) > 0 and meta.get("hp_restore", 0) == 0:
            cat = "mana"
        elif meta.get("hp_restore", 0) > 0 or meta.get("cure_status"):
            cat = "healing"

        buffs_dict = dict(meta.get("buffs") or {})

        return {
            "tier": tier,
            "hp_restore": meta.get("hp_restore", 0),
            "mp_restore": meta.get("mp_restore", 0),
            "damage": meta.get("damage", 0),
            "cure_status": list(meta.get("cure_status") or []),
            "inflict_status": list(meta.get("inflict_status") or []),
            "buffs": buffs_dict,
            "category": cat
        }

    # 2. Minimal default fallback for unknown un-encoded items
    return {
        "tier": parse_item_tier(item),
        "hp_restore": 0,
        "mp_restore": 0,
        "damage": 0,
        "cure_status": [],
        "inflict_status": [],
        "buffs": {},
        "category": "utility"
    }


_HOSTILE_COVERT_KEYWORDS = (
    "sleep",
    "sleeping",
    "sedative",
    "tranquil",
    "poison",
    "toxin",
    "venom",
    "paralyz",
    "chloroform",
    "aphrodisiac",
    "love potion",
    "truth serum",
    "drugged",
    "spiked",
    "smoke bomb",
    "flashbang",
    "grenade",
    "acid flask",
    "firebomb",
)

_NARRATIVE_CONSUMABLE_KEYWORDS = (
    "tea",
    "coffee",
    "latte",
    "boba",
    "wine",
    "ale",
    "beer",
    "sake",
    "cider",
    "whiskey",
    "cocktail",
    "snack",
    "bento",
    "meal",
    "cake",
    "chocolate",
    "candy",
    "perfume",
    "incense",
    "aphrodisiac",
    "draught",
    "sedative",
    "sleeping",
    "love potion",
    "truth serum",
    "pheromone",
)

_NON_CONSUMABLE_TYPES = {
    "weapon",
    "armor",
    "shield",
    "accessory",
    "helmet",
    "head",
    "headwear",
    "boots",
    "shoes",
    "gloves",
    "ring",
    "amulet",
    "cloak",
    "clothing",
    "top",
    "bottom",
    "outerwear",
    "lingerie",
    "bra",
    "underwear",
    "misc",
    "gift",
    "novelty",
    "key item",
    "quest",
    "quest item",
    "narrative artifact",
    "narrative",
    "spellbook",
}

_CONSUMABLE_TYPES = {"potion", "consumable", "food", "drink", "remedy", "tonic", "scroll", "elixir"}


def is_hostile_or_covert_consumable(item: Dict[str, Any]) -> bool:
    """Returns True if using this consumable on an NPC is hostile, harmful, sedative, or covert."""
    if not item or not isinstance(item, dict):
        return False
    if bool(item.get("equipped")) or is_key_item(item) or is_digital_item(item):
        return False

    parsed = parse_item_effect(item)
    meta = parse_consumable_metadata(item) or {}
    purpose_tags = [str(p).lower() for p in (meta.get("purpose_tags") or [])]
    effect_tags = [str(e).lower() for e in (meta.get("effect_tags") or [])]

    if int(parsed.get("damage", 0) or 0) > 0:
        return True
    if parsed.get("inflict_status"):
        return True
    if "throwable" in purpose_tags or "debuff" in purpose_tags:
        return True
    if any(t in {"explosive_fire", "corrosive_acid", "toxic_cloud", "paralyze", "sleep"} for t in effect_tags):
        return True

    combined = f"{item.get('name', '')} {item.get('effect', '')} {item.get('description', '')}".lower()
    return any(kw in combined for kw in _HOSTILE_COVERT_KEYWORDS)


def classify_consumable_usage_mode(item: Dict[str, Any]) -> str:
    """
    Classifies an inventory item's out-of-combat consumable usage mode:
      - 'non_consumable': weapons, armor, key items, digital media, spellbooks, gifts
      - 'throwable': offensive/damage consumables (always consumes a turn / combat throw)
      - 'mechanical': pure HP/MP/cure/combat stat buffs (instant Quick Use on self/party)
      - 'narrative': social/story consumables with zero mechanical combat delta (always consumes a turn)
      - 'hybrid': both mechanical stats and narrative/social effects (prompts Quick Use vs Use in Story)
    """
    if not item or not isinstance(item, dict):
        return "non_consumable"

    item_type = str(item.get("item_type") or item.get("type") or "").strip().lower()
    name_low = str(item.get("name") or "").strip().lower()
    eff_raw = str(item.get("effect") or "").strip()
    eff_low = eff_raw.lower()

    if is_key_item(item) or is_digital_item(item):
        return "non_consumable"
    if (
        item_type == "spellbook"
        or eff_raw.startswith("[SPELLBOOK_JSON]")
        or any(name_low.startswith(p) for p in ("spellbook:", "grimoire:", "tome:", "datapad:", "schematic:"))
    ):
        return "non_consumable"
    if eff_raw.startswith(("[GEAR_JSON]", "[ITEM_JSON]")) and item_type not in _CONSUMABLE_TYPES:
        return "non_consumable"
    if item_type in _NON_CONSUMABLE_TYPES and item_type not in _CONSUMABLE_TYPES:
        # Fallback for misc items explicitly described as potions/tonics/elixirs
        if not any(kw in name_low for kw in ("potion", "elixir", "tonic", "draught", "remedy", "aphrodisiac", "sedative")):
            return "non_consumable"

    meta = parse_consumable_metadata(item) or {}
    parsed = parse_item_effect(item)
    purpose_tags = [str(p).lower() for p in (meta.get("purpose_tags") or [])]
    effect_tags = [str(e).lower() for e in (meta.get("effect_tags") or [])]
    taste_tags = [str(t).lower() for t in (meta.get("taste_tags") or [])]

    if (
        int(parsed.get("damage", 0) or 0) > 0
        or "throwable" in purpose_tags
        or any(t in {"explosive_fire", "corrosive_acid", "toxic_cloud"} for t in effect_tags)
    ):
        return "throwable"

    buffs = parsed.get("buffs") if isinstance(parsed.get("buffs"), dict) else {}
    mech_buff_keys = {"atk_pct", "dr", "dt", "eva", "atk", "def", "mdef", "matk", "str", "agi", "end", "per", "int", "luk"}
    has_mech = bool(
        int(parsed.get("hp_restore", 0) or 0) > 0
        or int(parsed.get("mp_restore", 0) or 0) > 0
        or bool(parsed.get("cure_status"))
        or any(k in buffs for k in mech_buff_keys)
    )
    if not has_mech and eff_raw and not eff_raw.startswith("["):
        if re.search(r"(?:heal|restor(?:e|es)|\+|cure)\w*\s*\d*\s*(?:hp|mp|health|mana|poison|bleed|burn)", eff_low):
            has_mech = True

    has_narrative = bool(
        taste_tags
        or item_type in {"food", "drink"}
        or "morale_boost" in effect_tags
        or "charisma_buff" in effect_tags
        or "cha" in buffs
        or "alcohol" in taste_tags
        or is_hostile_or_covert_consumable(item)
        or any(kw in f"{name_low} {eff_low}" for kw in _NARRATIVE_CONSUMABLE_KEYWORDS)
    )

    if not has_mech and not has_narrative:
        if item_type in _CONSUMABLE_TYPES or any(
            kw in name_low for kw in ("potion", "elixir", "tonic", "draught", "remedy", "snack", "bread", "ration", "tea", "perfume")
        ):
            return "narrative"
        return "non_consumable"

    if has_mech and has_narrative:
        return "hybrid"
    if has_mech:
        return "mechanical"
    return "narrative"


