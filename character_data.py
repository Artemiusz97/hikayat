"""
Static reference data: stats, classes, weapons, spells, and progression
constants. Tweak freely -- this is the "content" layer, separate from
engine logic.
"""

# ------------------------------------------------------------------ stats
# A SPECIAL-style seven-stat system. Each stat has both a narrative/GM-level
# effect (described here so it can be fed to the LLM as guidance) and, where
# practical, a concrete numeric hook implemented in code (see db.py /
# skill_check.py / game_engine.py for where each is actually wired in).
STATS = ["STR", "PER", "END", "CHA", "INT", "AGI", "LUK"]

STAT_NAMES = {
    "STR": "Strength", "PER": "Perception", "END": "Endurance",
    "CHA": "Charisma", "INT": "Intelligence", "AGI": "Agility", "LUK": "Luck",
}

STAT_EMOJI = {
    "STR": "💪", "PER": "👁️", "END": "🛡️", "CHA": "🗣️",
    "INT": "🧠", "AGI": "🏹", "LUK": "🍀", "ITEM": "🎒"
}

STAT_EFFECTS = {
    "STR": "Melee/unarmed damage, inventory capacity (+3 slots per point, base 30), "
           "and the success rate of Strength-based actions.",
    "PER": "Ranged weapon accuracy, chance to notice hidden details, and the "
           "success rate of Perception-based actions.",
    "END": "Total HP (base 200, +100/pt) and HP regen (+1/pt), total Mana (base 50, +25/pt) and Mana regen (+1/2 pts), and the "
           "success rate of Endurance-based actions.",
    "CHA": "Enemy morale in combat, success at talking your way out of "
           "trouble, and the success rate of Charisma-based actions.",
    "INT": "XP gained per action, magic proficiency, overall effectiveness "
           "against enemies, and the success rate of Intelligence-based actions.",
    "AGI": "How often enemies miss you, your attack rate/initiative, and the "
           "success rate of Agility-based actions.",
    "LUK": "Critical hit chance, chance of enemy mishaps, chance of finding "
           "extra loot, how far events swing (very good to very bad), and "
           "the success rate of Luck-based actions.",
}

# Point-buy: every stat starts at BASE_STAT_VALUE, and the player has
# POINT_BUY_POOL extra points to invest across the seven stats however they
# like. Going over the pool is a hard error -- no character gets created.
BASE_STAT_VALUE = 1
POINT_BUY_POOL = 5

# Hard ceiling on any single stat. Enforced at character creation (point-buy)
# and at level-up (spending a pending stat point) -- a stat can never be
# pushed past this value by any means.
MAX_STAT_VALUE = 10

import re
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
CLASS_TEMPLATES_PATH = DATA_DIR / "class_templates.json"
STARTING_WEAPONS_PATH = DATA_DIR / "starting_weapons.json"

_class_templates_cache: dict | None = None
_starting_weapons_cache: dict | None = None


def load_class_templates(*, reload: bool = False) -> dict[str, dict]:
    global _class_templates_cache
    if _class_templates_cache is not None and not reload:
        return _class_templates_cache

    if not CLASS_TEMPLATES_PATH.is_file():
        log.warning("class_templates.json not found at %s", CLASS_TEMPLATES_PATH)
        return {}

    try:
        data = json.loads(CLASS_TEMPLATES_PATH.read_text(encoding="utf-8"))
        _class_templates_cache = data
        return data
    except Exception as exc:
        log.error("Failed to load class_templates.json: %s", exc)
        return {}


def load_starting_weapons(*, reload: bool = False) -> dict[str, list[str]]:
    global _starting_weapons_cache
    if _starting_weapons_cache is not None and not reload:
        return _starting_weapons_cache

    if not STARTING_WEAPONS_PATH.is_file():
        log.warning("starting_weapons.json not found at %s", STARTING_WEAPONS_PATH)
        return {}

    try:
        data = json.loads(STARTING_WEAPONS_PATH.read_text(encoding="utf-8"))
        _starting_weapons_cache = data
        return data
    except Exception as exc:
        log.error("Failed to load starting_weapons.json: %s", exc)
        return {}


TAG_TO_TEMPLATE_KEY = {
    "space": "sci_fi",
    "scifi": "sci_fi",
    "sci_fi": "sci_fi",
    "dark_fantasy": "dark_fantasy",
    "isekai": "isekai_fantasy",
    "isekai_fantasy": "isekai_fantasy",
    "highschool": "high_school_drama",
    "high_school": "high_school_drama",
    "high_school_drama": "high_school_drama",
    "slice_of_life": "slice_of_life",
    "postapoc": "nuclear_post_apocalypse",
    "post_apoc": "nuclear_post_apocalypse",
    "post_apocalypse": "nuclear_post_apocalypse",
    "nuclear_post_apocalypse": "nuclear_post_apocalypse",
    "cyberpunk": "cyberpunk",
    "steampunk": "steampunk",
    "fantasy": "fantasy",
    "urban_fantasy": "urban_fantasy",
    "modern": "urban_fantasy",
    "urban_anomalies": "anomalous_incursions",
    "anomalous_incursions": "anomalous_incursions",
    "nsfw_gore_anomalous_incursions": "anomalous_incursions",
    "furry_anomalous_incursions": "anomalous_incursions",
    "nsfw_furry_gore_anomalous_incursions": "anomalous_incursions",
}


def _resolve_template_scenario_key(scenario: str, target_dict: dict) -> str:
    if scenario in target_dict:
        return scenario
    mapped = TAG_TO_TEMPLATE_KEY.get(scenario)
    if mapped and mapped in target_dict:
        return mapped
    try:
        from scenario_data import get_scenario
        scen_info = get_scenario(scenario)
        base = scen_info.get("base_scenario")
        if base and base in target_dict:
            return base
        if base and TAG_TO_TEMPLATE_KEY.get(base) in target_dict:
            return TAG_TO_TEMPLATE_KEY[base]
        tags = scen_info.get("tags") or []
        for tag in tags:
            if tag in target_dict:
                return tag
            mapped_tag = TAG_TO_TEMPLATE_KEY.get(tag)
            if mapped_tag and mapped_tag in target_dict:
                return mapped_tag
    except Exception:
        pass
    return "fantasy"


def get_all_class_templates() -> dict[str, dict]:
    """Returns a merged dictionary of all class templates across all genres."""
    templates = load_class_templates()
    all_classes = {}
    for scen_key, class_dict in templates.items():
        if isinstance(class_dict, dict):
            all_classes.update(class_dict)
    try:
        from mechanics.combat.items.anomalous_gear import get_all_anomalous_faction_classes
        all_classes.update(get_all_anomalous_faction_classes())
    except Exception:
        pass
    return all_classes


def get_class_templates(scenario: str | None = None, starting_faction: str | None = None) -> dict[str, dict]:
    try:
        from scenario_data import is_anomalous_incursions_scenario
        if is_anomalous_incursions_scenario(scenario):
            from mechanics.combat.items.anomalous_gear import get_anomalous_faction_classes
            return get_anomalous_faction_classes(starting_faction or "public_agency")
    except Exception:
        pass
    templates = load_class_templates()
    if not scenario or scenario == "all":
        return get_all_class_templates()
    key = _resolve_template_scenario_key(scenario, templates)
    return templates.get(key, get_all_class_templates())


def get_all_starting_weapons() -> list[str]:
    """Returns a deduplicated list of all starting weapons across all genres."""
    weapons_dict = load_starting_weapons()
    all_weapons = []
    seen = set()
    for weapon_list in weapons_dict.values():
        if isinstance(weapon_list, list):
            for w in weapon_list:
                if w not in seen:
                    seen.add(w)
                    all_weapons.append(w)
    try:
        from mechanics.combat.items.anomalous_gear import ANOMALOUS_FACTION_WEAPONS
        for w_list in ANOMALOUS_FACTION_WEAPONS.values():
            for w in w_list:
                if w not in seen:
                    seen.add(w)
                    all_weapons.append(w)
    except Exception:
        pass
    return all_weapons or ["Runic Sword", "Arcane Staff", "Elven Bow", "Silver Dagger"]


def is_tailed_race(race: str) -> bool:
    r = str(race or "").strip().lower()
    if not r:
        return False
    if r in ("human", "elf", "dwarf", "gnome", "halfling", "orc", "half-elf", "android", "synth", "cyborg", "clone"):
        return False
    tailed_keywords = (
        "beast", "furry", "anthro", "hybrid", "tail", "cat", "dog", "wolf", "fox", "fennec",
        "kitsune", "tiger", "lion", "cheetah", "leopard", "felid", "feline", "canid", "canine",
        "rabbit", "bunny", "mouse", "rat", "dragon", "lizard", "reptil", "snake", "scaly"
    )
    return any(k in r for k in tailed_keywords)


def get_starting_weapons(scenario: str | None = None, starting_faction: str | None = None) -> list[str]:
    weapons = load_starting_weapons()
    if not scenario or scenario == "all":
        return get_all_starting_weapons()
    try:
        from scenario_data import is_non_combat_scenario, is_anomalous_incursions_scenario
        if is_non_combat_scenario(scenario):
            return []
        if is_anomalous_incursions_scenario(scenario):
            from mechanics.combat.items.anomalous_gear import get_anomalous_faction_weapons
            return get_anomalous_faction_weapons(starting_faction or "public_agency")
    except Exception:
        pass
    if scenario in weapons:
        return weapons[scenario]
    mapped = TAG_TO_TEMPLATE_KEY.get(scenario)
    if mapped and mapped in weapons:
        return weapons[mapped]
    try:
        from scenario_data import get_scenario
        scen_info = get_scenario(scenario)
        base = scen_info.get("base_scenario")
        if base and base in weapons:
            return weapons[base]
        if base and TAG_TO_TEMPLATE_KEY.get(base) in weapons:
            return weapons[TAG_TO_TEMPLATE_KEY[base]]
        tags = scen_info.get("tags") or []
        combined = []
        for tag in tags:
            if tag in weapons:
                combined.extend(weapons[tag])
            else:
                mapped_tag = TAG_TO_TEMPLATE_KEY.get(tag)
                if mapped_tag and mapped_tag in weapons:
                    combined.extend(weapons[mapped_tag])
        if combined:
            return list(dict.fromkeys(combined))
    except Exception:
        pass
    return weapons.get("fantasy", ["Runic Sword", "Arcane Staff", "Elven Bow", "Silver Dagger"])


def get_starter_gear_by_class(scenario: str = "fantasy", char_class: str = "", gender: str = "Male", race: str = "Human") -> dict:
    scen_classes = get_class_templates(scenario)
    class_info = scen_classes.get(char_class)
    if not class_info:
        try:
            from mechanics.combat.items.anomalous_gear import get_all_anomalous_faction_classes
            class_info = get_all_anomalous_faction_classes().get(char_class)
        except Exception:
            pass
    if not class_info:
        raw_templates = load_class_templates()
        key = _resolve_template_scenario_key(scenario, raw_templates)
        class_info = (raw_templates.get(scenario) or {}).get(char_class) or (raw_templates.get(key) or {}).get(char_class)
    if not class_info:
        # Fallback to fantasy if class not found in given scenario
        scen_classes = get_class_templates("fantasy")
        class_info = scen_classes.get(char_class, {})

    raw_gear = class_info.get("starter_gear", {})
    gear_map = {}
    is_male = str(gender or "").strip().lower() == "male"
    is_female = str(gender or "").strip().lower() == "female"
    has_tail = is_tailed_race(race)

    for slot, entry in raw_gear.items():
        if entry and isinstance(entry, list) and len(entry) >= 3:
            item_name = str(entry[0])
            item_desc = str(entry[1])
            cost = int(entry[2])

            # Handle slash alternatives like "Pencil Skirt / Smart Slacks" or "Pleated Plaid Skirt / Dark Trousers"
            if " / " in item_name:
                parts = [p.strip() for p in item_name.split(" / ")]
                if len(parts) == 2:
                    female_part, male_part = parts[0], parts[1]
                    if is_male:
                        item_name = male_part
                    elif is_female:
                        item_name = female_part
                    else:
                        item_name = male_part

            # Gender-specific adjustments
            if is_male:
                if "skirt" in item_name.lower():
                    if "enchanted robe" in item_name.lower():
                        item_name = "Enchanted Robe Trousers"
                    elif "ashen" in item_name.lower():
                        item_name = "Ashen Trousers"
                    elif "pleated" in item_name.lower():
                        item_name = "Pleated Uniform Slacks"
                    elif "pencil" in item_name.lower():
                        item_name = "Tailored Uniform Slacks"
                    else:
                        item_name = item_name.replace("Skirt", "Trousers").replace("skirt", "trousers")
                if "dress" in item_name.lower():
                    item_name = item_name.replace("Dress", "Tunic").replace("dress", "tunic")
            elif is_female:
                if "slacks" in item_name.lower() and "skirt" not in item_name.lower() and "trench" not in item_name.lower():
                    pass

            # Race-specific adjustments (tail-slots for tailed species, no tail-slots for tailless)
            if has_tail:
                if slot in ("Bottom", "Armor") and "tail" not in item_name.lower():
                    item_name = f"Tail-Slotted {item_name}"
            else:
                if "tail-slotted" in item_name.lower():
                    item_name = item_name.replace("Tail-Slotted ", "").replace("tail-slotted ", "").replace("Tail-slotted ", "")

            gear_map[slot] = (item_name, item_desc, cost)
        else:
            gear_map[slot] = None

    try:
        from scenario_data import is_non_combat_scenario
        if is_non_combat_scenario(scenario):
            gear_map["Weapon"] = None
            gear_map["Shield"] = None
            gear_map["Armor"] = None
    except Exception:
        pass

    return gear_map


def get_starting_items(scenario: str = "fantasy", char_class: str = "", starting_faction: str = "") -> list:
    scen_classes = get_class_templates(scenario)
    class_info = scen_classes.get(char_class)
    if not class_info:
        try:
            from mechanics.combat.items.anomalous_gear import get_all_anomalous_faction_classes
            class_info = get_all_anomalous_faction_classes().get(char_class)
        except Exception:
            pass
    if not class_info:
        raw_templates = load_class_templates()
        key = _resolve_template_scenario_key(scenario, raw_templates)
        class_info = (raw_templates.get(scenario) or {}).get(char_class) or (raw_templates.get(key) or {}).get(char_class)
    if not class_info:
        scen_classes = get_class_templates("fantasy")
        class_info = scen_classes.get(char_class, {})

    try:
        from scenario_data import is_anomalous_incursions_scenario
        if is_anomalous_incursions_scenario(scenario):
            from mechanics.combat.items.anomalous_gear import get_anomalous_faction_starting_items
            anom_items = list(get_anomalous_faction_starting_items(scenario, starting_faction or "public_agency"))
            raw_items = class_info.get("starting_items", [])
            for entry in raw_items:
                if isinstance(entry, list) and len(entry) >= 4 and str(entry[1]).lower() in ("tool", "quest"):
                    anom_items.append((entry[0], entry[1], entry[2], int(entry[3])))
            return anom_items
    except Exception:
        pass

    raw_items = class_info.get("starting_items", [])
    items = []
    for entry in raw_items:
        if isinstance(entry, list) and len(entry) >= 4:
            items.append((entry[0], entry[1], entry[2], int(entry[3])))
    return items or CUSTOM_CLASS_STARTING_ITEMS



CUSTOM_CLASS_STARTING_ITEMS = [
    ("Traveler's Pack", "Quest", "A worn satchel with the basics for the road.", 1),
]

# ------------------------------------------------------------------- gender
# Standard options offered during character creation (see
# cogs/character.py's GenderSelectView); a player can also pick "Custom" to
# type their own free-text gender identity instead (CustomGenderModal).
# Purely a profile/flavor field -- like equipment, it has zero mechanical
# effect anywhere in the engine.
GENDER_OPTIONS = ["Male", "Female"]

# ------------------------------------------------------------------ equipment
# Exactly six independent equipment slots. Each slot holds at most one item;
# equipping a new item into an already-occupied slot automatically unequips
# whatever was there before (see db.equip_item) -- it stays in the inventory,
# just no longer equipped.
#
# EQUIPMENT IS NARRATIVE-ONLY: nothing here grants a stat, HP/MP, damage, or
# skill-check bonus -- there is no code anywhere in db.py/skill_check.py/
# game_engine.py that reads equipped gear to modify a number. Equipped items
# exist purely so the LLM narrator can describe actions/combat using the
# specific gear a character has (a "Steel Shield" gets raised to block
# instead of a generic dodge; a custom "Rusty Meat Cleaver" gets swung
# instead of a generic strike) -- see game_engine.SYSTEM_PROMPT's equipment
# rule for how that's enforced on the narration side.
EQUIPMENT_SLOTS = [
    "Head",         # 🪖 Headwear — helmets, hoods, visors, caps, hats, circlets
    "Armor",        # 🛡️ Dedicated combat body armor slot (Plate, Kevlar, Cuirass, Power Armor)
    "Top",          # 👕 Civilian clothing — shirts, blouses, jackets, uniforms, tunics
    "Bottom",       # 👖 Civilian clothing — trousers, skirts, shorts, slacks
    "Weapon",       # 🗡️ Main weapon
    "Shield",       # 🛡️ Off-hand defensive shield
    "Gloves",       # 🧤 Handwear
    "Shoes",        # 👢 Footwear
    "Accessory 1", "Accessory 2", "Accessory 3", "Accessory 4"
]

EQUIPMENT_SLOT_EMOJI = {
    "Head": "🪖",
    "Armor": "🥋",
    "Top": "👕", "Bottom": "👖",
    "Weapon": "🗡️", "Shield": "🛡️",
    "Gloves": "🧤", "Shoes": "👢",
    "Accessory 1": "💍", "Accessory 2": "📿",
    "Accessory 3": "💍", "Accessory 4": "📿",
}

DEFAULT_EQUIP_SLOT_FOR_ITEM_TYPE = {
    "Head": "Head",
    "Helmet": "Head",
    "Headwear": "Head",
    "Weapon": "Weapon",
    "Armor": "Armor",      # Combat armor → Armor slot
    "Clothing": "Top",     # Civilian clothing → Top slot
    "Shield": "Shield",
    "Gloves": "Gloves",
    "Shoes": "Shoes",
    "Accessory": "Accessory 1",
}


def get_item_icon(name: str, item_type: str = "", effect: str = "", slot: str = "") -> str:
    from game_engine.matching import matches_keyword
    from localization import ICON_KEYWORDS

    name_lower = (name or "").lower()
    type_lower = (item_type or "").lower()
    effect_lower = (effect or "").lower()
    slot_str = str(slot or "")

    # 0. Digital Media Items (Photos, Videos, Selfies)
    if "intimate video" in name_lower or ("video" in name_lower and ("nsfw" in name_lower or "intimate" in name_lower or "nsfw" in effect_lower or "intimate" in effect_lower)):
        return "🔞"
    if "intimate photo" in name_lower or ("photo" in name_lower and ("nsfw" in name_lower or "intimate" in name_lower or "nsfw" in effect_lower or "intimate" in effect_lower)):
        return "🔞"
    if matches_keyword(name_lower, ICON_KEYWORDS["digital_video"]) or ("[digital_json]" in effect_lower and "video" in effect_lower):
        return "📹"
    if matches_keyword(name_lower, ICON_KEYWORDS["digital_photo"]) or ("[digital_json]" in effect_lower and "photo" in effect_lower):
        return "📸"
    if "digital" in type_lower or "[digital_json]" in effect_lower:
        return "💾"

    # 1. Accessories (Rings, Amulets, Bracelets, Necklaces, etc.)
    if "accessory" in slot_str.lower() or matches_keyword(name_lower, ICON_KEYWORDS["accessories"]) or "accessory" in type_lower:
        if matches_keyword(name_lower, ICON_KEYWORDS["amulet"]):
            return "📿"
        return "💍"

    # 2. Specific Name Keywords (Weapons, Tools, Gear)
    if matches_keyword(name_lower, ICON_KEYWORDS["phone"]):
        return "📱"
    if matches_keyword(name_lower, ICON_KEYWORDS["backpack"]):
        return "🎒"
    if matches_keyword(name_lower, ICON_KEYWORDS["wand"]):
        return "🪄"
    if matches_keyword(name_lower, ICON_KEYWORDS["grimoire"]):
        return "📖"
    if matches_keyword(name_lower, ICON_KEYWORDS["bow"]):
        return "🏹"
    if matches_keyword(name_lower, ICON_KEYWORDS["gun"]):
        return "🔫"
    if matches_keyword(name_lower, ICON_KEYWORDS["dagger"]):
        return "🗡️"
    if matches_keyword(name_lower, ICON_KEYWORDS["axe"]):
        return "🪓"
    if matches_keyword(name_lower, ICON_KEYWORDS["hammer"]):
        return "🔨"
    if matches_keyword(name_lower, ICON_KEYWORDS["spear"]):
        return "🔱"
    if matches_keyword(name_lower, ICON_KEYWORDS["whip"]):
        return "🦯"
    if matches_keyword(name_lower, ICON_KEYWORDS["sword"]):
        return "⚔️"

    # 3. Clothing / Armor / Headwear Name Keywords
    if matches_keyword(name_lower, ICON_KEYWORDS["crown"]):
        return "👑"
    if matches_keyword(name_lower, ICON_KEYWORDS["glasses"]):
        return "👓"
    if matches_keyword(name_lower, ICON_KEYWORDS["top_hat"]):
        return "🎩"
    if matches_keyword(name_lower, ICON_KEYWORDS["helm"]):
        return "🪖"
    if matches_keyword(name_lower, ICON_KEYWORDS["cap"]):
        return "🧢"
    if matches_keyword(name_lower, ICON_KEYWORDS["boots"]):
        return "👢"
    if matches_keyword(name_lower, ICON_KEYWORDS["gloves"]):
        return "🧤"
    if matches_keyword(name_lower, ICON_KEYWORDS["pants"]):
        return "👖"
    if matches_keyword(name_lower, ICON_KEYWORDS["armor"]):
        return "👕"
    if matches_keyword(name_lower, ICON_KEYWORDS["shield"]):
        return "🛡️"

    # 4. Equipment Slot / Type Fallbacks
    if slot_str == "Weapon" or matches_keyword(type_lower, ICON_KEYWORDS["slot_weapon"]):
        return "⚔️"
    if slot_str == "Shield" or matches_keyword(type_lower, ICON_KEYWORDS["slot_shield"]):
        return "🛡️"
    if slot_str == "Head" or matches_keyword(type_lower, ICON_KEYWORDS["slot_head"]):
        return "🪖"
    if slot_str == "Bottom" or matches_keyword(type_lower, ICON_KEYWORDS["slot_bottom"]):
        return "👖"
    if slot_str == "Gloves" or matches_keyword(type_lower, ICON_KEYWORDS["slot_gloves"]):
        return "🧤"
    if slot_str == "Shoes" or matches_keyword(type_lower, ICON_KEYWORDS["slot_shoes"]):
        return "👢"
    if slot_str == "Top" or matches_keyword(type_lower, ICON_KEYWORDS["slot_top"]):
        return "👕"
    if matches_keyword(type_lower, ICON_KEYWORDS["slot_armor"]):
        return "👕"

    # 5. Consumables & Quest Items
    if matches_keyword(name_lower, ICON_KEYWORDS["boba"]):
        return "🧋"
    if matches_keyword(name_lower, ICON_KEYWORDS["coffee"]):
        return "☕"
    if matches_keyword(name_lower, ICON_KEYWORDS["tea"]):
        return "🍵"
    if matches_keyword(name_lower, ICON_KEYWORDS["wine"]):
        return "🍷"
    if matches_keyword(name_lower, ICON_KEYWORDS["beer"]):
        return "🍺"
    if matches_keyword(name_lower, ICON_KEYWORDS["drink"]) or matches_keyword(type_lower, ICON_KEYWORDS["drink"]):
        return "🥤"
    if matches_keyword(name_lower, ICON_KEYWORDS["food"]) or matches_keyword(type_lower, ICON_KEYWORDS["food"]):
        return "🍱"
    if matches_keyword(name_lower, ICON_KEYWORDS["health"]) or matches_keyword(effect_lower, ICON_KEYWORDS["health"]):
        return "❤️"
    if matches_keyword(name_lower, ICON_KEYWORDS["mana"]):
        return "💙"
    if matches_keyword(type_lower, ICON_KEYWORDS["potion"]) or matches_keyword(name_lower, ICON_KEYWORDS["potion"]):
        return "🧪"
    if matches_keyword(type_lower, ICON_KEYWORDS["quest"]) or matches_keyword(name_lower, ICON_KEYWORDS["quest"]):
        return "📜"

    return "📦"


def format_item_with_icon(name: str, item_type: str = "", effect: str = "", slot: str = "") -> str:
    icon = get_item_icon(name, item_type, effect, slot)
    return f"{icon} {name}"

WEAPON_CLASSES = {
    "Light": "PER/AGI-scaled: daggers, shortswords, bows.",
    "Heavy": "STR-scaled: greatswords, warhammers, halberds. High risk/reward.",
    "Magical Implement": "INT-scaled: staves, wands, grimoires. Reduces spell MP cost.",
}

SPELL_SCHOOLS = {
    "Evocation": {"stat": "INT", "flavor": "Destructive elemental magic: Fireball, Lightning Bolt."},
    "Restoration": {"stat": "END", "flavor": "Healing and protection: Mend Wounds, Magic Shield."},
    "Illusion": {"stat": "CHA", "flavor": "Mind and environment manipulation: Invisibility, Charm."},
}

STARTING_GOLD = 15

# ------------------------------------------------------------- progression
MAX_LEVEL = 50

# XP awarded per action outcome tier, before the Intelligence multiplier.
# Under Fail-Forward, failure and catastrophe provide meaningful experience
# as characters learn from friction and adversity.
XP_REWARDS = {
    "crit_success": 25,
    "success": 18,
    "fail": 10,
    "crit_fail": 15,
}
XP_PER_LEVEL = 100          # xp needed to go from level N to N+1 is N * XP_PER_LEVEL


def xp_multiplier(intelligence: int) -> float:
    """Higher INT means you learn faster from everything you do."""
    return 1.0 + 0.06 * intelligence


# NOTE: stats may ONLY increase via a pending stat point earned from leveling
# up (see db.add_xp / db.spend_stat_point). There is intentionally no passive
# "use a stat and it trains up on its own" mechanic -- one used to exist here
# (TRAINING_GAIN_ON_SUCCESS/FAILURE + training_threshold(), consumed from
# cogs/adventure.py) and has been removed so leveling is the single source of
# stat growth.


# ------------------------------------------------------------- derived stats
def derive_hp(endurance: int) -> int:
    return 200 + endurance * 100


def derive_mp(endurance: int) -> int:
    return 50 + endurance * 25


calculate_max_hp = derive_hp
calculate_max_mp = derive_mp


def hp_regen(endurance: int) -> int:
    return max(1, endurance)


def mp_regen(endurance: int) -> int:
    return max(1, endurance // 2)


def inventory_capacity(strength: int) -> int:
    return 30 + strength * 3


def crit_chances(luck: int) -> tuple[float, float]:
    """Returns (crit_success_pct, crit_fail_pct), both flat chances applied
    on top of the normal skill-vs-requirement roll. Luck raises the ceiling
    and lowers the floor."""
    crit_success = min(15.0, 3.0 + luck * 0.6)
    crit_fail = max(0.5, 3.0 - luck * 0.4)
    return crit_success, crit_fail


def derive_combat_attributes(
    str_: int = 1, per_: int = 1, end_: int = 1,
    cha: int = 1, int_: int = 1, agi: int = 1, luk: int = 1
) -> dict:
    """Computes base combat attributes directly from individual SPECIAL values."""
    from mechanics.social.attributes import calculate_combat_attributes
    return calculate_combat_attributes({
        "str_": str_, "per_": per_, "end_": end_,
        "cha": cha, "int_": int_, "agi": agi, "luk": luk
    })


def calculate_combat_attributes(character: dict, equipped_items: list | None = None, scenario: str | None = None) -> dict:
    """Convenience alias delegating to mechanics.social.attributes.calculate_combat_attributes."""
    from mechanics.social.attributes import calculate_combat_attributes as _calc
    return _calc(character, equipped_items, scenario=scenario)


def generate_equipment(scenario: str = "fantasy", slot: str = "Weapon", tier: int | None = None, archetype: str | None = None, name: str | None = None) -> dict:
    """Convenience alias delegating to mechanics.combat.items.generate_random_equipment."""
    from mechanics.combat.items import generate_random_equipment
    return generate_random_equipment(scenario, slot, tier, archetype=archetype, name=name)


def generate_starting_weapons(scenario: str = "fantasy", count: int = 6) -> list[dict]:
    """Generates procedural starting weapons using the new weapon generation system."""
    from mechanics.combat.items.weapons import generate_starting_weapons as _gen_w
    return _gen_w(scenario=scenario, count=count)


def generate_starter_equipment_loadout(
    scenario: str = "fantasy",
    char_class: str = "",
    gender: str = "Male",
    race: str = "Human",
    weapon_name: str = "",
    tier: int = 3,
    starting_faction: str = "",
) -> dict:
    """Convenience alias delegating to mechanics.combat.items.generate_starter_equipment_loadout."""
    from mechanics.combat.items import generate_starter_equipment_loadout as _gen_loadout
    return _gen_loadout(
        scenario=scenario,
        char_class=char_class,
        gender=gender,
        race=race,
        weapon_name=weapon_name,
        tier=tier,
        starting_faction=starting_faction,
    )


def format_equipment_card(metadata: dict) -> str:
    """Convenience alias delegating to mechanics.combat.items.format_equipment_card."""
    from mechanics.combat.items import format_equipment_card as _fmt
    return _fmt(metadata)


def parse_equipment_metadata(item: dict) -> dict:
    """Convenience alias delegating to mechanics.combat.equipment.parse_equipment_metadata."""
    from mechanics.combat.equipment import parse_equipment_metadata as _parse
    return _parse(item)


def reconcile_character_outcomes(char: dict, outcome: dict, is_non_combat: bool = False, allow_mp_loss: bool = True, allow_gold_loss: bool = True) -> dict:
    """Deterministically validates and bounds HP/MP/Gold deltas and status effects reported by LLM or engine."""
    max_hp = char.get("max_hp", derive_hp(char.get("end_", 1)))
    max_mp = char.get("max_mp", derive_mp(char.get("end_", 1)))
    
    current_hp = char.get("hp", max_hp)
    current_mp = char.get("mp", max_mp)
    current_gold = char.get("gold", 0)

    hp_change = int(outcome.get("hp_change", 0) or 0)
    if is_non_combat and hp_change < 0:
        hp_change = 0
    mp_change = int(outcome.get("mp_change", 0) or 0)
    if is_non_combat and not allow_mp_loss and mp_change < 0:
        mp_change = 0
    gold_change = int(outcome.get("gold_change", 0) or 0)
    if is_non_combat and not allow_gold_loss and gold_change < 0:
        gold_change = 0

    new_hp = max(0, min(max_hp, current_hp + hp_change))
    new_mp = max(0, min(max_mp, current_mp + mp_change))
    new_gold = max(0, current_gold + gold_change)

    return {
        "new_hp": new_hp,
        "new_mp": new_mp,
        "new_gold": new_gold,
        "actual_hp_delta": hp_change if hp_change < 0 else (new_hp - current_hp),
        "actual_mp_delta": mp_change if mp_change < 0 else (new_mp - current_mp),
        "actual_gold_delta": new_gold - current_gold,
    }


ATTENDANCE_STATUS_TAGS = {
    "present", "absent", "nearby", "here", "away", "in scene", "on stage",
    "active partner", "bystander", "none", "null", "unknown"
}

def sanitize_status_effects(effects: list, max_words: int = 3, max_count: int = 4) -> list[str]:
    """Filters out bloated narrative status-effect logs and caps the list length.

    Valid status effects are short RPG condition tags of 1-3 words (e.g. 'Bleeding',
    'Stunned', 'Frightened', 'Shoulder laceration'). Anything longer is treated as
    a narrative action log and discarded.

    Args:
        effects:   Raw list returned by the LLM.
        max_words: Maximum number of words allowed in a single status tag (default 3).
        max_count: Maximum number of active status effects to keep (default 4).
    """
    if not isinstance(effects, list):
        return []
    cleaned = []
    for eff in effects:
        if not isinstance(eff, str):
            continue
        s = eff.strip()
        if not s:
            continue
        # Reject entries that end in a period (sentence) or contain a comma (list)
        if s.endswith('.') or ',' in s or s in ("[]", "{}", '""', "''"):
            continue
        # Reject non-condition attendance or scene-presence tags
        if s.lower() in ATTENDANCE_STATUS_TAGS:
            continue
        # Reject entries with more than max_words words (ignoring [N turns] or [N min] duration brackets)
        base_s = re.sub(r"\s*\[\d+\s*(?:turns?|min)\]", "", s, flags=re.IGNORECASE).strip()
        if len(base_s.split()) > max_words:
            continue
        # Deduplicate (case-insensitive)
        if s.lower() not in (c.lower() for c in cleaned):
            cleaned.append(s)
    return cleaned[:max_count]
