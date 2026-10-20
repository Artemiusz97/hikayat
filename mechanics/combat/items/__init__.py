from mechanics.combat.items.weapons import (
    WEAPON_ARCHETYPES,
    NON_COMBAT_WEAPON_ARCHETYPES,
    normalize_weapon_scenario,
    generate_random_equipment as _gen_weapon,
    generate_starting_weapons,
    deduce_weapon_archetype,
    format_equipment_card as _fmt_weapon,
    THEME_AFFIXES,
    SCENARIO_AFFIXES,
    roll_tier
)

from mechanics.combat.items.armors import (
    ARMOR_ARCHETYPES,
    generate_random_equipment as _gen_armor,
    format_equipment_card as _fmt_armor,
    SCENARIO_ARMOR_AFFIXES,
    normalize_armor_scenario
)
from mechanics.combat.items.clothing import (
    CLOTHING_TOPS,
    CLOTHING_BOTTOMS,
    can_equip_armor_in_scenario,
    can_equip_item_in_scenario,
    generate_random_clothing as _gen_clothing,
    generate_random_clothing,
    format_clothing_card as _fmt_clothing,
    format_clothing_card,
    is_clothing_slot,
    SCENARIO_CLOTHING_AFFIXES,
    normalize_clothing_scenario
)
from mechanics.combat.items.shields import (
    SHIELD_ARCHETYPES,
    NON_COMBAT_SHIELD_ARCHETYPES,
    generate_random_equipment as _gen_shield,
    format_equipment_card as _fmt_shield,
    SCENARIO_SHIELD_AFFIXES,
    normalize_shield_scenario
)
from mechanics.combat.items.gloves import (
    GLOVE_ARCHETYPES,
    NON_COMBAT_GLOVE_ARCHETYPES,
    generate_random_equipment as _gen_gloves,
    format_equipment_card as _fmt_gloves,
    SCENARIO_GLOVES_AFFIXES,
    normalize_gloves_scenario
)
from mechanics.combat.items.shoes import (
    SHOE_ARCHETYPES,
    NON_COMBAT_SHOE_ARCHETYPES,
    generate_random_equipment as _gen_shoes,
    format_equipment_card as _fmt_shoes,
    SCENARIO_SHOES_AFFIXES,
    normalize_shoes_scenario
)
from mechanics.combat.items.headwear import (
    HEADWEAR_ARCHETYPES,
    NON_COMBAT_HEADWEAR_ARCHETYPES,
    generate_random_equipment as _gen_headwear,
    format_equipment_card as _fmt_headwear,
    SCENARIO_HEADWEAR_AFFIXES,
    normalize_headwear_scenario
)
from mechanics.combat.items.accessories import (
    ACCESSORY_ARCHETYPES,
    NON_COMBAT_ACCESSORY_ARCHETYPES,
    generate_random_equipment as _gen_acc,
    format_equipment_card as _fmt_acc,
    SCENARIO_ACCESSORY_AFFIXES,
    normalize_accessory_scenario
)
from mechanics.combat.items.consumables import (
    generate_procedural_potion, generate_procedural_food, generate_procedural_drink,
    parse_consumable_metadata, serialize_consumable_metadata,
    apply_item_to_target, parse_item_effect, parse_item_tier,
    classify_and_enrich_ad_hoc_item, create_digital_media_item,
    is_digital_item, parse_digital_item_metadata, is_giftable_item,
    is_key_item,
    evaluate_gift_reaction, POTION_SCALING, FOOD_SCALING, DRINK_SCALING,
    POTION_PURPOSE_TAGS, POTION_EFFECT_TAGS, FOOD_TASTE_TAGS, FOOD_EFFECT_TAGS,
    DRINK_TASTE_TAGS, DRINK_EFFECT_TAGS,
    serialize_digital_item_metadata, generate_potion_name, generate_food_name, generate_drink_name,
    normalize_consumable_scenario
)
from mechanics.combat.items.tags import (
    item_has_tag, get_flat_tag_list, derive_weapon_tags,
    derive_armor_tags, derive_clothing_tags, derive_consumable_tags,
    derive_spell_tags, is_narrative_item, make_narrative_metadata,
    HANDEDNESS, MASS, ATTACK_TYPES, DAMAGE_TYPES,
    ARMOR_CLASSES, CLOTHING_STYLES
)
from mechanics.combat.items.envelope import (
    serialize_item, parse_item, ITEM_PREFIX, is_item_json
)

def generate_random_equipment(scenario="fantasy", slot="Weapon", tier=None, archetype=None, name=None):
    if is_clothing_slot(slot):
        return _gen_clothing(scenario, slot, tier)
    elif slot == "Weapon":
        return _gen_weapon(scenario, slot, tier, archetype=archetype, name=name)
    elif slot in ("Head", "Headwear", "Helmet"):
        return _gen_headwear(scenario, "Head", tier, archetype=archetype)
    elif slot in ("Gloves", "Glove", "Hands", "Gauntlets"):
        return _gen_gloves(scenario, "Gloves", tier, archetype=archetype)
    elif slot in ("Shoes", "Boots", "Feet", "Footwear"):
        return _gen_shoes(scenario, "Shoes", tier, archetype=archetype)
    elif slot == "Armor" or slot in ("Top", "Bottom", "Body", "Chest"):
        if not can_equip_armor_in_scenario(scenario):
            clothing_slot = slot if slot in ("Top", "Bottom") else "Top"
            return _gen_clothing(scenario, clothing_slot, tier)
        return _gen_armor(scenario, slot if slot in ("Armor", "Top", "Bottom") else "Armor", tier, archetype=archetype)
    elif slot in ("Shield", "Offhand", "Off-hand"):
        return _gen_shield(scenario, "Shield", tier, archetype=archetype)
    elif slot.startswith("Accessory") or slot in ("Accessory", "Ring", "Amulet", "Necklace", "Trinket"):
        return _gen_acc(scenario, slot if slot.startswith("Accessory") else "Accessory 1", tier)
    else:
        return _gen_weapon(scenario, "Weapon", tier, archetype=archetype, name=name)


def _infer_class_archetype_profile(char_class: str, class_description: str = "", scenario: str = "fantasy") -> dict:
    """Infers cohesive per-slot archetype choices from a character's class name and description.

    Returns a profile dict with optional keys for each equipment slot:
      head, armor, top_archetype, bottom_archetype, gloves, shoes, shield, accessory

    A value of ``None`` for "armor", "gloves", or "shield" means that slot is intentionally
    *empty* for this class (e.g. mages skip combat armor, monks skip gloves).
    A missing key means "roll freely from the scenario pool".

    Covers standard RPG archetypes, scenario-specific roles, and provides reasonable
    keyword-based heuristics for custom/wacky/joke professions.
    """
    import random as _rand
    cls = (str(char_class or "") + " " + str(class_description or "")).lower()
    scen = str(scenario or "fantasy").lower()

    def _has(*kws):
        return any(k in cls for k in kws)

    def _scen(*kws):
        return any(k in scen for k in kws)

    profile = {}

    # ── High School / Academic Scenarios ──────────────────────────────────
    if _scen("high_school", "school", "academy"):
        profile["armor"] = None
        profile["shield"] = None
        if _has("delinquent", "rebel"):
            profile["top_archetype"] = _rand.choice(["jacket", "casual_shirt", "school_uniform_top"])
            profile["bottom_archetype"] = _rand.choice(["trousers", "slacks"])
            profile["shoes"] = "light_sneakers"
            profile["gloves"] = _rand.choice(["fingerless_gloves", None])
        elif _has("athlete", "varsity", "runner", "sports", "gym"):
            profile["top_archetype"] = _rand.choice(["casual_shirt", "jacket", "hoodie"])
            profile["bottom_archetype"] = _rand.choice(["shorts", "sweatpants", "trousers"])
            profile["shoes"] = "light_sneakers"
            profile["gloves"] = None
        elif _has("bookworm", "honor", "student", "journalist", "organizer", "prodigy"):
            profile["top_archetype"] = _rand.choice(["blazer", "school_uniform_top", "waistcoat", "sweater"])
            profile["bottom_archetype"] = _rand.choice(["slacks", "trousers", "skirt"])
            profile["shoes"] = "formal_shoes"
            profile["gloves"] = None
        else:
            profile["top_archetype"] = _rand.choice(["school_uniform_top", "blazer", "sweater", "blouse", "casual_shirt"])
            profile["bottom_archetype"] = _rand.choice(["slacks", "trousers", "skirt"])
            profile["shoes"] = _rand.choice(["light_sneakers", "formal_shoes"])
            profile["gloves"] = None
        profile["accessory"] = _rand.choice(["ring", "bracelet", "amulet", None])
        return profile

    # ── 1. Heavy Fighter / Tank / Knight / Paladin ────────────────────────────
    if _has("paladin", "knight", "crusader", "guardian", "templar", "tank", "warden",
            "sentinel", "shieldbearer", "iron", "fortress"):
        profile["head"] = _rand.choice(["full_greathelm", "open_helm"])
        profile["armor"] = _rand.choice(["plate", "chainmail"])
        profile["top_archetype"] = "tunic"
        profile["bottom_archetype"] = "trousers"
        profile["gloves"] = "heavy_gauntlets"
        profile["shoes"] = "heavy_greaves"
        profile["shield"] = _rand.choice(["tower_shield", "heater_shield"])
        profile["accessory"] = _rand.choice(["amulet", "ring"])

    # ── 2. Mage / Wizard / Sorcerer / Archmage / Spellcaster ─────────────────
    elif _has("mage", "wizard", "sorcerer", "archmage", "spellcast", "warlock",
              "witch", "enchanter", "conjurer", "elementalist", "occultist",
              "necromancer", "lich", "spellblade"):
        profile["head"] = _rand.choice(["circlet", "cloth_hood"])
        profile["armor"] = None   # mages don't wear combat armor
        profile["top_archetype"] = "robe"
        profile["bottom_archetype"] = "skirt" if "female" in cls else "trousers"
        profile["gloves"] = _rand.choice(["arcane_gloves", "precision_gloves", None])
        profile["shoes"] = _rand.choice(["stealth_boots", "sandals"])
        profile["shield"] = None
        profile["accessory"] = _rand.choice(["amulet", "talisman"])

    # ── 3. Rogue / Assassin / Thief / Ninja / Spy ────────────────────────────
    elif _has("rogue", "assassin", "thief", "ninja", "shadowblade", "stalker",
              "infiltrator", "spy", "cutpurse", "pickpocket", "bandit",
              "shadow", "ghost", "phantom"):
        profile["head"] = "cloth_hood"
        profile["armor"] = _rand.choice(["leather", "clothes"])
        profile["top_archetype"] = _rand.choice(["jacket", "hoodie"])
        profile["bottom_archetype"] = "trousers"
        profile["gloves"] = "fingerless_gloves"
        profile["shoes"] = "stealth_boots"
        profile["shield"] = None
        profile["accessory"] = _rand.choice(["ring", "talisman"])

    # ── 4. Ranger / Hunter / Archer / Scout ──────────────────────────────────
    elif _has("ranger", "hunter", "archer", "scout", "tracker", "marksman",
              "sniper", "bowman", "huntress", "pathfinder", "forester"):
        profile["head"] = _rand.choice(["cap", "cloth_hood"])
        profile["armor"] = _rand.choice(["leather", "kevlar"])
        profile["top_archetype"] = _rand.choice(["jacket", "tunic"])
        profile["bottom_archetype"] = "trousers"
        profile["gloves"] = "leather_gloves"
        profile["shoes"] = _rand.choice(["combat_boots", "riding_boots"])
        profile["shield"] = None
        profile["accessory"] = _rand.choice(["ring", "amulet"])

    # ── 5. Brawler / Monk / Warrior / Berserker ──────────────────────────────
    elif _has("brawler", "monk", "fighter", "warrior", "berserker", "gladiator",
              "pugilist", "barbarian", "martial", "unarmed", "fist", "boxer",
              "wrestler", "bruiser"):
        profile["head"] = _rand.choice(["cloth_hood", "cap", "open_helm"])
        profile["armor"] = _rand.choice(["leather", "chainmail", "clothes"])
        profile["top_archetype"] = _rand.choice(["tunic", "jacket"])
        profile["bottom_archetype"] = _rand.choice(["trousers", "shorts"])
        profile["gloves"] = "cloth_wraps"
        profile["shoes"] = _rand.choice(["sandals", "combat_boots"])
        profile["shield"] = None
        profile["accessory"] = _rand.choice(["bracelet", "amulet"])

    # ── 6. Cleric / Priest / Healer / Druid / Shaman ─────────────────────────
    elif _has("cleric", "priest", "healer", "druid", "shaman", "oracle",
              "prophet", "divine", "holy", "blessed", "bishop", "cardinal"):
        profile["head"] = _rand.choice(["circlet", "formal_hat", "cloth_hood"])
        profile["armor"] = _rand.choice(["chainmail", "magic_robe", "clothes"])
        profile["top_archetype"] = _rand.choice(["robe", "tunic"])
        profile["bottom_archetype"] = "trousers"
        profile["gloves"] = _rand.choice(["precision_gloves", "arcane_gloves"])
        profile["shoes"] = _rand.choice(["sandals", "combat_boots"])
        profile["shield"] = _rand.choice(["heater_shield", None])
        profile["accessory"] = _rand.choice(["amulet", "talisman"])

    # ── 7. Bard / Performer / Entertainer / Jester ───────────────────────────
    elif _has("bard", "performer", "entertainer", "jester", "minstrel",
              "dancer", "singer", "musician", "actor", "comedian"):
        profile["head"] = _rand.choice(["formal_hat", "cap"])
        profile["armor"] = _rand.choice(["leather", "clothes"])
        profile["top_archetype"] = _rand.choice(["blouse", "jacket", "tunic"])
        profile["bottom_archetype"] = _rand.choice(["trousers", "skirt"])
        profile["gloves"] = _rand.choice(["formal_gloves", "fingerless_gloves"])
        profile["shoes"] = "formal_shoes"
        profile["shield"] = None
        profile["accessory"] = _rand.choice(["ring", "amulet"])

    # ── 8. Merchant / Noble / Diplomat ───────────────────────────────────────
    elif _has("merchant", "trader", "noble", "aristocrat", "diplomat", "clerk",
              "banker", "baron", "lord", "lady", "chancellor", "magistrate",
              "politician", "negotiator"):
        profile["head"] = _rand.choice(["formal_hat", "top_hat", "fascinator", "bonnet", "beret"])
        profile["armor"] = None
        profile["top_archetype"] = _rand.choice(["tailcoat", "waistcoat", "blazer", "blouse"])
        profile["bottom_archetype"] = _rand.choice(["slacks", "trousers", "breeches", "bustle_skirt"])
        profile["gloves"] = _rand.choice(["formal_gloves", "lace_mitts"])
        profile["shoes"] = _rand.choice(["oxfords", "high_heels", "formal_shoes"])
        profile["shield"] = None
        profile["accessory"] = _rand.choice(["pocket_watch", "monocle", "cravat_pin", "choker", "ring"])

    # ── 9. Sci-Fi / Tech / Cyborg / Netrunner ────────────────────────────────
    elif _scen("cyber", "sci_fi", "scifi", "space") or _has(
            "engineer", "netrunner", "cyborg", "techie", "hacker", "pilot",
            "drone", "mechanist", "roboticist", "astro"):
        profile["head"] = _rand.choice(["tech_visor", "ar_glasses", "gas_mask", "cap", "beanie"])
        profile["armor"] = _rand.choice(["kevlar", "ceramic", "leather"])
        profile["top_archetype"] = _rand.choice(["techwear_anorak", "holo_jacket", "bodysuit_top", "jacket", "hoodie"])
        profile["bottom_archetype"] = _rand.choice(["techwear_joggers", "syn_leather_pants", "cargo_pants", "trousers"])
        profile["gloves"] = _rand.choice(["tactical_touch_gloves", "haptic_gloves", "precision_gloves", "insulated_gloves"])
        profile["shoes"] = _rand.choice(["mag_sneakers", "combat_boots", "light_sneakers"])
        profile["shield"] = None
        profile["accessory"] = _rand.choice(["neural_jack_plug", "data_cuff", "holo_badge", "bracelet"])

    # ── 10. Alchemist / Artificer / Steampunk Inventor ───────────────────────
    elif _scen("steam", "steampunk") or _has(
            "alchemist", "artificer", "inventor", "tinkerer", "machinist",
            "clockwork", "aether", "chrono", "steam"):
        profile["head"] = _rand.choice(["tech_visor", "top_hat", "bowler_hat", "cap"])
        profile["armor"] = _rand.choice(["leather", "chainmail", "kevlar"])
        profile["top_archetype"] = _rand.choice(["waistcoat", "duster_coat", "jacket", "corset"])
        profile["bottom_archetype"] = _rand.choice(["breeches", "bustle_skirt", "trousers", "culottes"])
        profile["gloves"] = _rand.choice(["insulated_gloves", "leather_gloves", "lace_mitts"])
        profile["shoes"] = _rand.choice(["oxfords", "spats_boots", "combat_boots"])
        profile["shield"] = None
        profile["accessory"] = _rand.choice(["pocket_watch", "chatelaine", "cravat_pin", "monocle"])

    # ── 11. Post-Apocalyptic / Scavenger / Wasteland ─────────────────────────
    elif _scen("nuclear_post_apocalypse", "apocalypse", "wasteland") or _has(
            "scavenger", "raider", "mutant", "survivor", "wastelander", "drifter"):
        profile["head"] = _rand.choice(["cloth_hood", "gas_mask", "cap"])
        profile["armor"] = _rand.choice(["leather", "kevlar", "lamellar"])
        profile["top_archetype"] = _rand.choice(["jacket", "hoodie"])
        profile["bottom_archetype"] = "trousers"
        profile["gloves"] = _rand.choice(["fingerless_gloves", "leather_gloves"])
        profile["shoes"] = _rand.choice(["combat_boots", "hazard_boots"])
        profile["shield"] = None
        profile["accessory"] = _rand.choice(["talisman", "bracelet"])

    # ── 12. Pirate / Swashbuckler / Sailor ───────────────────────────────────
    elif _has("pirate", "sailor", "captain", "swashbuckler", "corsair",
              "buccaneer", "privateer", "sea", "naval"):
        profile["head"] = _rand.choice(["formal_hat", "cap", "cloth_hood"])
        profile["armor"] = _rand.choice(["leather", "chainmail"])
        profile["top_archetype"] = _rand.choice(["jacket", "tunic"])
        profile["bottom_archetype"] = "trousers"
        profile["gloves"] = _rand.choice(["fingerless_gloves", "leather_gloves"])
        profile["shoes"] = "riding_boots"
        profile["shield"] = _rand.choice(["buckler", None])
        profile["accessory"] = _rand.choice(["ring", "bracelet"])

    # ── 13. Academic / Scholar / Medical / Detective ─────────────────────────
    elif _has("scholar", "academic", "student", "researcher", "professor",
              "librarian", "scribe", "archivist", "intellectual", "doctor",
              "surgeon", "medic", "physician", "nurse", "detective",
              "investigator", "inspector", "lawyer", "attorney", "scientist"):
        profile["head"] = _rand.choice(["cap", "circlet", "formal_hat", "ar_glasses", None])
        profile["armor"] = None
        profile["top_archetype"] = _rand.choice(["school_uniform_top", "blouse", "jacket", "blazer", "duster_coat"])
        profile["bottom_archetype"] = _rand.choice(["slacks", "trousers"])
        profile["gloves"] = _rand.choice(["precision_gloves", "leather_gloves", None])
        profile["shoes"] = _rand.choice(["formal_shoes", "oxfords"])
        profile["shield"] = None
        profile["accessory"] = _rand.choice(["ring", "amulet", "pocket_watch", "monocle"])

    # ── 14. Culinary / Hospitality / Service / Domestic ──────────────────────
    elif _has("chef", "cook", "baker", "butcher", "brewer", "food", "culinary",
              "taco", "pizza", "ramen", "sushi", "barista", "butler", "maid",
              "waiter", "waitress", "bartender", "sommelier", "patissier"):
        profile["head"] = _rand.choice(["cap", "formal_hat", "beret", None])
        profile["armor"] = None
        profile["top_archetype"] = _rand.choice(["casual_shirt", "tunic", "waistcoat", "blouse"])
        profile["bottom_archetype"] = _rand.choice(["trousers", "slacks", "skirt"])
        profile["gloves"] = _rand.choice(["insulated_gloves", "formal_gloves", None])
        profile["shoes"] = _rand.choice(["combat_boots", "oxfords", "formal_shoes"])
        profile["shield"] = None
        profile["accessory"] = _rand.choice(["ring", "bracelet", "pocket_watch"])

    # ── 15. Athlete / Sports / Gym ────────────────────────────────────────────
    elif _has("athlete", "coach", "sport", "gym", "runner", "swimmer",
              "cyclist", "trainer", "jock", "varsity"):
        profile["head"] = "cap"
        profile["armor"] = None
        profile["top_archetype"] = _rand.choice(["casual_shirt", "hoodie", "jacket"])
        profile["bottom_archetype"] = _rand.choice(["shorts", "trousers"])
        profile["gloves"] = None
        profile["shoes"] = "light_sneakers"
        profile["shield"] = None
        profile["accessory"] = _rand.choice(["bracelet", "ring"])

    # ── 16. Artisan / Crafter / Laborer / Outdoors ───────────────────────────
    elif _has("blacksmith", "smith", "miner", "carpenter", "mason", "farmer",
              "rancher", "angler", "fisherman", "lumberjack", "gardener",
              "florist", "courier", "delivery", "driver", "janitor", "custodian"):
        profile["head"] = _rand.choice(["cap", "beanie", "cloth_hood"])
        profile["armor"] = _rand.choice(["leather", None])
        profile["top_archetype"] = _rand.choice(["jacket", "tunic", "casual_shirt"])
        profile["bottom_archetype"] = _rand.choice(["cargo_pants", "trousers"])
        profile["gloves"] = _rand.choice(["leather_gloves", "insulated_gloves", "fingerless_gloves"])
        profile["shoes"] = _rand.choice(["combat_boots", "hazard_boots", "light_sneakers"])
        profile["shield"] = None
        profile["accessory"] = _rand.choice(["bracelet", "talisman", "ring"])

    # ── 17. Casual / Streamer / Satirical / Wacky Custom Professions ─────────
    elif _has("streamer", "influencer", "youtuber", "gamer", "otaku", "neet",
              "couch", "potato", "slacker", "tourist", "vacation", "hobby",
              "idol", "celebrity", "clown", "mime", "mascot", "salaryman"):
        profile["head"] = _rand.choice(["beanie", "cap", "ar_glasses", None])
        profile["armor"] = None
        profile["top_archetype"] = _rand.choice(["hoodie", "casual_shirt", "jacket"])
        profile["bottom_archetype"] = _rand.choice(["sweatpants", "shorts", "trousers"])
        profile["gloves"] = _rand.choice(["fingerless_gloves", None])
        profile["shoes"] = _rand.choice(["light_sneakers", "sandals"])
        profile["shield"] = None
        profile["accessory"] = _rand.choice(["bracelet", "ring", "holo_badge"])

    # ── 18. Dark / Cursed / Undead / Horror ──────────────────────────────────
    elif _has("death", "undead", "vampire", "reaper", "cursed", "plague",
              "horror", "eldritch", "abyssal", "voidwalker", "doomgiver"):
        profile["head"] = _rand.choice(["cloth_hood", "full_greathelm"])
        profile["armor"] = _rand.choice(["leather", "chainmail", "magic_robe"])
        profile["top_archetype"] = _rand.choice(["hoodie", "robe", "jacket"])
        profile["bottom_archetype"] = "trousers"
        profile["gloves"] = _rand.choice(["fingerless_gloves", "cloth_wraps"])
        profile["shoes"] = _rand.choice(["stealth_boots", "combat_boots"])
        profile["shield"] = None
        profile["accessory"] = _rand.choice(["talisman", "amulet"])

    # ── Fallback: balanced mid-tier to avoid wild mismatches ─────────────────
    else:
        profile["head"] = _rand.choice(["cap", "cloth_hood", "open_helm"])
        profile["armor"] = _rand.choice(["leather", "chainmail", "clothes", None])
        profile["top_archetype"] = _rand.choice(["tunic", "jacket", "casual_shirt"])
        profile["bottom_archetype"] = _rand.choice(["trousers", "jeans"])
        profile["gloves"] = _rand.choice(["leather_gloves", "fingerless_gloves", None])
        profile["shoes"] = _rand.choice(["combat_boots", "riding_boots", "light_sneakers"])
        profile["shield"] = None
        profile["accessory"] = _rand.choice(["ring", "amulet", "bracelet"])

    return profile


def generate_starter_equipment_loadout(
    scenario: str = "fantasy",
    char_class: str = "",
    gender: str = "Male",
    race: str = "Human",
    weapon_name: str = "",
    tier: int = 3,
    archetype_profile: dict | None = None,
) -> dict:
    """Generates a complete starting equipment loadout based on the new equipment generation system.

    When *archetype_profile* is provided (a dict from _infer_class_archetype_profile or
    converted from an LLM-generated loadout), each slot respects the requested archetypes
    so the full set is thematically cohesive.  Without it, a profile is automatically
    inferred from char_class and scenario.

    Returns a dict mapping slot -> item_dict, where each item_dict is a full item structure
    with name, item_type, slot, effect ([ITEM_JSON]), metadata, and slot_cost.
    """
    import random
    loadout = {}
    is_male = str(gender or "").strip().lower() == "male"
    is_tailless = str(race or "").strip().lower() in ("human", "elf", "dwarf", "gnome", "halfling", "orc", "half-elf")

    # Resolve archetype profile (auto-infer if not supplied)
    if archetype_profile is None:
        archetype_profile = _infer_class_archetype_profile(char_class, "", scenario)

    from scenario_data import is_non_combat_scenario
    from character_data import is_tailed_race
    is_non_combat = is_non_combat_scenario(scenario)
    has_tail = is_tailed_race(race)

    # 1. Weapon
    is_2h = False
    if is_non_combat and not weapon_name:
        # Non-combat: omit starting weapon slot unless explicitly named
        pass
    else:
        if weapon_name:
            weapon = _gen_weapon(scenario, "Weapon", tier=tier, name=weapon_name)
        else:
            weapon = _gen_weapon(scenario, "Weapon", tier=tier)
        loadout["Weapon"] = weapon
        w_meta = weapon.get("metadata", {})
        is_2h = w_meta.get("handedness") == "2H"

    # 2. Combat Body Armor (for combat-eligible scenarios only)
    can_wear_combat_armor = can_equip_armor_in_scenario(scenario)
    if can_wear_combat_armor:
        armor_arch = archetype_profile.get("armor", "UNSET")
        if armor_arch == "UNSET":
            # Profile has no opinion — default to generating some armor
            loadout["Armor"] = _gen_armor(scenario, "Armor", tier=tier)
        elif armor_arch is not None:
            # Profile specifies an archetype
            loadout["Armor"] = _gen_armor(scenario, "Armor", tier=tier,
                                          archetype=armor_arch)
        # else: armor_arch is explicitly None → skip slot (mages, civilians, etc.)

    # 3. Civilian Top & Bottom
    top_arch = archetype_profile.get("top_archetype")
    bottom_arch = archetype_profile.get("bottom_archetype")

    # Generate top, re-roll up to 5 times to match inferred archetype
    top = _gen_clothing(scenario, "Top", tier=tier, archetype=top_arch, gender=gender, race=race)
    if top_arch:
        for _ in range(5):
            if top.get("metadata", {}).get("archetype") == top_arch:
                break
            top = _gen_clothing(scenario, "Top", tier=tier, archetype=top_arch, gender=gender, race=race)

    # Generate bottom, re-roll up to 5 times to match inferred archetype
    bottom = _gen_clothing(scenario, "Bottom", tier=tier, archetype=bottom_arch, gender=gender, race=race)
    if bottom_arch:
        for _ in range(5):
            if bottom.get("metadata", {}).get("archetype") == bottom_arch:
                break
            bottom = _gen_clothing(scenario, "Bottom", tier=tier, archetype=bottom_arch, gender=gender, race=race)

    # Guard against skirts on male characters
    if is_male:
        b_meta = bottom.get("metadata", {})
        if b_meta.get("archetype") == "skirt" or "skirt" in bottom.get("name", "").lower():
            for _ in range(10):
                bottom = _gen_clothing(scenario, "Bottom", tier=tier, archetype="trousers", gender=gender, race=race)
                if bottom.get("metadata", {}).get("archetype") != "skirt" and "skirt" not in bottom.get("name", "").lower():
                    break

    loadout["Top"] = top
    loadout["Bottom"] = bottom

    # 4. Headwear
    head_arch = archetype_profile.get("head")
    loadout["Head"] = _gen_headwear(scenario, "Head", tier=tier,
                                    archetype=head_arch if head_arch else None)

    # 5. Gloves — explicit None in profile means bare-handed class
    glove_arch = archetype_profile.get("gloves", "UNSET")
    if glove_arch == "UNSET":
        loadout["Gloves"] = _gen_gloves(scenario, "Gloves", tier=tier)
    elif glove_arch is not None:
        loadout["Gloves"] = _gen_gloves(scenario, "Gloves", tier=tier, archetype=glove_arch)
    # else: None → skip (bare-handed)

    # 6. Shoes / Footwear
    shoe_arch = archetype_profile.get("shoes")
    loadout["Shoes"] = _gen_shoes(scenario, "Shoes", tier=tier,
                                  archetype=shoe_arch if shoe_arch else None)

    # 7. Shield — only for 1H weapons in combat scenarios
    shield_arch = archetype_profile.get("shield", "UNSET")
    if not is_2h and can_wear_combat_armor:
        if shield_arch == "UNSET":
            # No profile opinion — fall back to keyword heuristic
            cls_lower = (char_class or "").lower()
            shield_likely = any(k in cls_lower for k in (
                "paladin", "knight", "warrior", "guardian", "fighter", "cleric", "crusader"
            ))
            if shield_likely and random.random() < 0.65:
                loadout["Shield"] = _gen_shield(scenario, "Shield", tier=tier)
        elif shield_arch is not None:
            # Profile specifies a shield archetype
            loadout["Shield"] = _gen_shield(scenario, "Shield", tier=tier,
                                            archetype=shield_arch)
        # else: None → skip shield

    # 8. Accessories (Accessory 1 guaranteed, Accessory 2 optional)
    loadout["Accessory 1"] = _gen_acc(scenario, "Accessory 1", tier=tier)
    if random.random() < 0.50:
        loadout["Accessory 2"] = _gen_acc(scenario, "Accessory 2", tier=tier)

    # Race-specific adjustments (tail-slots for tailed species, no tail-slots for tailless)
    if has_tail:
        for slot, item in loadout.items():
            if slot in ("Bottom", "Armor") and "tail" not in item.get("name", "").lower():
                item["name"] = f"Tail-Slotted {item['name']}"
                if "metadata" in item and isinstance(item["metadata"], dict):
                    item["metadata"]["name"] = item["name"]
                    flags = item["metadata"].setdefault("social_flags", [])
                    if "tail_slotted" not in flags:
                        flags.append("tail_slotted")
                    item["effect"] = serialize_item(item["metadata"])
    else:
        for slot, item in loadout.items():
            if "tail-slotted" in item.get("name", "").lower():
                item["name"] = item["name"].replace("Tail-Slotted ", "").replace("tail-slotted ", "").replace("Tail-slotted ", "")
                if "metadata" in item and isinstance(item["metadata"], dict):
                    item["metadata"]["name"] = item["name"]
                    item["effect"] = serialize_item(item["metadata"])

    if is_non_combat:
        for slot, item in loadout.items():
            if isinstance(item, dict) and "metadata" in item and isinstance(item["metadata"], dict):
                item["metadata"] = make_narrative_metadata(item["metadata"])
                item["effect"] = serialize_item(item["metadata"])

    return loadout


def format_equipment_card(metadata: dict) -> str:
    if is_narrative_item(metadata):
        item_name = metadata.get("name", "Equipment")
        item_type = metadata.get("item_type", "Equipment")
        slot = metadata.get("slot", "")
        tier = metadata.get("tier", 3)
        arch = metadata.get("archetype", "").replace("_", " ").title()
        hand = metadata.get("handedness", "1H")
        lines = [
            f"**{item_name}** (Tier {tier})",
            f"**Slot:** {slot} • **Type:** {item_type} ({arch})",
            f"🏷️ **Category:** Narrative Equipment (Cosmetic / Roleplay)",
            f"📖 **Usage:** Flavor, Story & Social Actions (No Combat Stats)"
        ]
        if hand == "2H":
            lines.append("⚠️ *Two-Handed: Held with both hands.*")
        tags = get_flat_tag_list(metadata)
        if tags:
            tag_badges = " ".join(f"`#{t}`" for t in tags[:6])
            lines.append(f"🏷️ **Tags:** {tag_badges}")
        soc = metadata.get("social_modifiers", {})
        if soc:
            soc_parts = [f"`{val:+d} {stat.upper()}`" for stat, val in soc.items() if val]
            if soc_parts:
                lines.append(f"✨ **Social Presence:** {' '.join(soc_parts)}")
        return "\n".join(lines)

    item_type = metadata.get("item_type", "")
    slot = metadata.get("slot", "")
    arch = metadata.get("archetype", "")

    if item_type == "Clothing" or arch in CLOTHING_TOPS or arch in CLOTHING_BOTTOMS:
        return _fmt_clothing(metadata)
    elif item_type == "Weapon" or slot == "Weapon" or arch in WEAPON_ARCHETYPES or arch in NON_COMBAT_WEAPON_ARCHETYPES:
        return _fmt_weapon(metadata)
    elif item_type == "Headwear" or slot == "Head" or arch in HEADWEAR_ARCHETYPES or arch in NON_COMBAT_HEADWEAR_ARCHETYPES:
        return _fmt_headwear(metadata)
    elif item_type == "Gloves" or slot == "Gloves" or arch in GLOVE_ARCHETYPES:
        return _fmt_gloves(metadata)
    elif item_type == "Shoes" or slot == "Shoes" or arch in SHOE_ARCHETYPES:
        return _fmt_shoes(metadata)
    elif item_type == "Armor" or slot == "Armor" or arch in ARMOR_ARCHETYPES:
        return _fmt_armor(metadata)
    elif item_type == "Shield" or slot == "Shield" or arch in SHIELD_ARCHETYPES or arch in NON_COMBAT_SHIELD_ARCHETYPES:
        return _fmt_shield(metadata)
    elif item_type == "Accessory" or slot.startswith("Accessory") or arch in ACCESSORY_ARCHETYPES or arch in NON_COMBAT_ACCESSORY_ARCHETYPES:
        return _fmt_acc(metadata)
    elif is_clothing_slot(slot):
        return _fmt_clothing(metadata)
    elif slot in ("Head",):
        return _fmt_headwear(metadata)
    elif slot in ("Gloves",):
        return _fmt_gloves(metadata)
    elif slot in ("Shoes",):
        return _fmt_shoes(metadata)
    elif slot in ("Armor", "Top"):
        return _fmt_armor(metadata)
    else:
        return _fmt_weapon(metadata)

def enrich_equipment_item(item: dict, scenario: str = "fantasy") -> dict:
    from mechanics.combat.equipment import enrich_equipment_item as _enrich
    return _enrich(item, scenario)
