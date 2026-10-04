from __future__ import annotations
import random
from typing import Dict, Any, Optional

from mechanics.combat.items.tags import derive_clothing_tags
from mechanics.combat.items.envelope import serialize_item

# -----------------------------------------------------------------------------
# CIVILIAN CLOTHING ARCHETYPES
# Standard clothing provides mild social vibes and at most +1 to SPECIAL stats
# (e.g. +1 CHA or +1 LUK), plus minor evasion (+1 to +3 EVA).
# -----------------------------------------------------------------------------

CLOTHING_TOPS = {
    "casual_shirt": {
        "style": "casual",
        "social_modifiers": {"cha": 1, "eva": 2, "luck": 0},
        "social_flags": ["comfortable"]
    },
    "blouse": {
        "style": "formal",
        "social_modifiers": {"cha": 1, "eva": 1, "luck": 0},
        "social_flags": ["elegant"]
    },
    "school_uniform_top": {
        "style": "academic_uniform",
        "social_modifiers": {"cha": 1, "eva": 1, "luck": 0},
        "social_flags": ["neat"]
    },
    "jacket": {
        "style": "streetwear",
        "social_modifiers": {"cha": 1, "eva": 2, "luck": 0},
        "social_flags": ["cool"]
    },
    "hoodie": {
        "style": "cozy",
        "social_modifiers": {"cha": 0, "eva": 3, "luck": 1},
        "social_flags": ["comfortable", "relaxed"]
    },
    "robe": {
        "style": "traditional",
        "social_modifiers": {"cha": 1, "eva": 0, "luck": 1},
        "social_flags": ["mystic"]
    },
    "tunic": {
        "style": "casual",
        "social_modifiers": {"cha": 1, "eva": 2, "luck": 0},
        "social_flags": ["simple"]
    }
}

CLOTHING_BOTTOMS = {
    "trousers": {
        "style": "formal",
        "social_modifiers": {"cha": 1, "eva": 1, "luck": 0},
        "social_flags": ["professional"]
    },
    "skirt": {
        "style": "casual",
        "social_modifiers": {"cha": 1, "eva": 2, "luck": 0},
        "social_flags": ["breezy"]
    },
    "shorts": {
        "style": "athletic",
        "social_modifiers": {"cha": 0, "eva": 3, "luck": 0},
        "social_flags": ["active"]
    },
    "slacks": {
        "style": "academic_uniform",
        "social_modifiers": {"cha": 1, "eva": 1, "luck": 0},
        "social_flags": ["neat"]
    },
    "jeans": {
        "style": "casual",
        "social_modifiers": {"cha": 0, "eva": 2, "luck": 1},
        "social_flags": ["durable"]
    }
}

# -----------------------------------------------------------------------------
# SCENARIO-SPECIFIC CLOTHING VOCABULARY & CUTS
# -----------------------------------------------------------------------------

SCENARIO_CLOTHING_AFFIXES: Dict[str, Dict[str, Any]] = {
    "fantasy": {
        "archetype_names": {
            "casual_shirt": ["Spun-Linen Shirt", "Peasant Undershirt", "Traveler's Blouse", "Linen Shirt"],
            "blouse": ["Embroidered Silk Blouse", "Courtly Chemise", "Lace Bodice", "Silk Blouse"],
            "school_uniform_top": ["Magic Academy Vestment", "Novice Scholar Shirt", "Apprentice Robelet"],
            "jacket": ["Leather Jerkin", "Embroidered Doublet", "Traveler's Mantle", "Hunter's Vest"],
            "hoodie": ["Traveler's Cloak-Hood", "Wayfarer's Cowl", "Forester's Poncho"],
            "robe": ["Mystic Silk Robes", "Sorcerer's Cassock", "Apprentice Frock", "Woolen Robe"],
            "tunic": ["Embroidered Tunic", "Woolen Tunic", "Peasant Smock", "Linen Tunic"],
            "trousers": ["Traveler's Breeches", "Linen Hose", "Leather-Trimmed Trousers"],
            "skirt": ["Layered Wool Skirt", "Embroidered Peasant Skirt", "Maiden's Long Skirt"],
            "shorts": ["Riding Breeches", "Short Trousers", "Linen Knickers"],
            "slacks": ["Courtier's Slacks", "Gilded Hose", "Formal Trousers"],
            "jeans": ["Roughspun Canvas Breeches", "Toughhide Trousers", "Sturdy Work Pants"]
        },
        "prefixes": {
            3: ["Simple", "Spun-Linen", "Peasant", "Traveler's", "Sturdy", "Homestead", "Neat"],
            2: ["Enchanted", "Rune-Embroidered", "Gilded-Silk", "Mithril-Threaded", "Elven-Woven"],
            1: ["Masterwork", "Archon-Weave", "Celestial-Silk", "Ancient Royalty's", "Mythic"]
        }
    },
    "steampunk": {
        "archetype_names": {
            "casual_shirt": ["Work Shirt", "Cravat Shirt", "Linen Workshirt", "Collared Shirt"],
            "blouse": ["Corseted Blouse", "Lace-Trimmed Blouse", "High-Collar Blouse"],
            "school_uniform_top": ["Academy Vestment", "Apprentice Waistcoat", "Scholastic Smock"],
            "jacket": ["Tweed Jacket", "Brass-Buttoned Waistcoat", "Tailored Tailcoat", "Aviator Jacket"],
            "hoodie": ["Cowl Smock", "Grease-Monkey Shawl", "Boiler Cowl"],
            "robe": ["Alchemical Smock", "Aether-Weaver Robe", "Gentleman's Dressing Gown"],
            "tunic": ["Machinist Smock", "Brass-Trimmed Tunic", "Mechanic Vest"],
            "trousers": ["Pinstripe Trousers", "Pleated Slacks", "Woolen Trousers"],
            "skirt": ["Bustle Skirt", "Pleated Tweed Skirt", "A-Line Long Skirt"],
            "shorts": ["Aviator Knickers", "Mechanic Shorts", "Work Bermudas"],
            "slacks": ["Tailored Pinstripe Slacks", "Victorian Dress Slacks"],
            "jeans": ["Heavy Denim Dungarees", "Reinforced Canvas Trousers", "Oilcloth Pants"]
        },
        "prefixes": {
            3: ["Tweed", "Brass-Trimmed", "Copper-Lined", "Oilcloth", "Starch-Pressed", "Woolen", "Canvas"],
            2: ["Aether-Insulated", "Galvanic-Threaded", "Gilded-Brocade", "Pneumatic-Tailored", "Velvet-Lined"],
            1: ["Grand Victorian", "Master Artificer's", "Aether-Sovereign's", "Royal Academy", "Dreadnought-Loom"]
        }
    },
    "cyberpunk": {
        "archetype_names": {
            "casual_shirt": ["Compression Tee", "Mesh Undershirt", "Tech Tee", "Holo-Tee"],
            "blouse": ["Corporate Silk Shirt", "Sleek Bodysuit Top", "Synthetic Chiffon Blouse"],
            "school_uniform_top": ["MegaCorp Academy Top", "Prep Tech-Vest", "Corporate Cadet Shirt"],
            "jacket": ["Tech-Wear Bomber", "LED Windbreaker", "Holographic Duster", "Synth-Leather Jacket"],
            "hoodie": ["Oversized Tech-Hoodie", "Cowl Pullover", "Netrunner Shadow-Hoodie"],
            "robe": ["Monolithic Kimono", "Holo-Draped Haori", "Augment Technician Smock"],
            "tunic": ["Combat Undershirt", "Nanite Mesh Tunic", "Utility Vest"],
            "trousers": ["Cargo Joggers", "Tech-Wear Trousers", "Tactical Chinos"],
            "skirt": ["Pleated Cyber-Skirt", "Holo-Fringe Skirt", "Neoprene Mini-Skirt"],
            "shorts": ["Synthetic Track Shorts", "Cargo Utility Shorts"],
            "slacks": ["Corporate Slacks", "Carbon-Weave Slacks", "Militech Tailored Pants"],
            "jeans": ["Acid-Wash Cyber-Denims", "Reinforced Biker Jeans", "Distressed Street Jeans"]
        },
        "prefixes": {
            3: ["Street-Grade", "Neo-Chic", "Carbon-Weave", "Synth-Leather", "Cargo", "Mesh", "Polymer"],
            2: ["Smart-Woven", "Holographic", "Thermal-Regulated", "Nanite-Laced", "EMP-Shielded", "Sub-Dermal"],
            1: ["Arasaka Executive", "High-Roller", "Black-ICE Woven", "Zero-Day Tailored", "Ghost-Protocol"]
        }
    },
    "dark_fantasy": {
        "archetype_names": {
            "casual_shirt": ["Roughspun Shirt", "Scavenger Flannel", "Patched Linen Top", "Burlap Shirt"],
            "blouse": ["Mourner's Blouse", "Frayed Silk Shirt", "Weathered Chemise"],
            "school_uniform_top": ["Disheveled Cadet Top", "Frayed Uniform Vest", "Old-World School Top"],
            "jacket": ["Wasteland Duster", "Spiked Leather Vest", "Tattered Trenchcoat", "Scavenger Coat"],
            "hoodie": ["Scrap Cowl Hoodie", "Ragged Ash-Hood", "Survivor Poncho"],
            "robe": ["Cursed Cultist Robe", "Plague-Doc Smock", "Grave-Shrouded Cowl"],
            "tunic": ["Burlap Tunic", "Flesh-Stitched Surcoat", "Rough-Linen Smock"],
            "trousers": ["Scavenged Dungarees", "Patched Canvas Trousers", "Ash-Stained Slacks"],
            "skirt": ["Tattered Rag Skirt", "Frayed Peasant Skirt", "Scrap-Hem Skirt"],
            "shorts": ["Cut-Off Scavenger Shorts", "Rough Burlap Shorts"],
            "slacks": ["Stained Mortuary Slacks", "Worn-Out Formal Pants"],
            "jeans": ["Rad-Bleached Denims", "Scrap-Patched Jeans", "Heavy Grease Jeans"]
        },
        "prefixes": {
            3: ["Weathered", "Tattered", "Patched", "Roughspun", "Frayed", "Ash-Stained", "Scavenged"],
            2: ["Lead-Lined", "Hex-Stitched", "Blood-Dyed", "Rad-Hardened", "Bone-Adorned", "Marrow-Treated"],
            1: ["Doomsday Relic", "Grave-Lord's", "Apex Scavenger's", "Abyssal-Woven", "Doomsday Heirloom"]
        }
    },
    "high_school": {
        "archetype_names": {
            "casual_shirt": ["Graphic Tee", "Polo Shirt", "Button-Down Casual Shirt", "Flannel Shirt"],
            "blouse": ["Pressed Sailor Blouse", "Chiffon Blouse", "Ruffled Collar Shirt"],
            "school_uniform_top": ["School Blazer & Shirt", "Junior Sailor Top", "School Cardigan"],
            "jacket": ["Varsity Letterman Jacket", "Denim Jacket", "Tracksuit Zip-Up", "Bomber Jacket"],
            "hoodie": ["Oversized Pastel Hoodie", "Campus Logo Hoodie", "Cozy Fleece Pullover"],
            "robe": ["Dorm Bathrobe", "Occult Club Robe", "Festival Yukata"],
            "tunic": ["Art Club Smock", "Longline Tunic Shirt"],
            "trousers": ["Chino Pants", "Pleated School Trousers", "Casual Khakis"],
            "skirt": ["Pleated Plaid Skirt", "Tennis Skirt", "Denim Mini Skirt", "A-Line School Skirt"],
            "shorts": ["Athletic Gym Shorts", "Denim Shorts", "Bicycle Shorts"],
            "slacks": ["Pressed Uniform Slacks", "Neat Dress Slacks"],
            "jeans": ["Skinny Blue Jeans", "Ripped Denim Jeans", "Straight-Leg Jeans"]
        },
        "prefixes": {
            3: ["Clean", "Campus", "Everyday", "Neat", "Casual", "Standard-Issue", "Comfy"],
            2: ["Tailored", "Designer", "Varsity-Star", "Boutique", "Charming", "Preppy"],
            1: ["Student Council President's", "Custom-Tailored", "Festival Champion's", "Prizewinning", "Heirloom"]
        }
    }
}

TIER_NAMES = {
    3: "Standard",
    2: "Enchanted",
    1: "Masterwork"
}

def is_clothing_slot(slot: str) -> bool:
    return slot in ("Top", "Bottom")

def can_equip_armor_in_scenario(scenario: str) -> bool:
    from scenario_data import is_non_combat_scenario
    return not is_non_combat_scenario(scenario)

def can_equip_item_in_scenario(item: Dict[str, Any], slot: str, scenario: str) -> tuple[bool, str]:
    """
    Validates whether an item can be equipped in the specified slot under the given scenario.
    In non-combat scenarios (Slice of Life / High School Drama):
    - Combat body armor ('Armor') and shields ('Shield') are strictly prohibited.
    - Combat headwear, heavy gauntlets, and combat boots/greaves are strictly prohibited.
    Returns (is_allowed: bool, rejection_message: str).
    """
    from scenario_data import is_non_combat_scenario
    if not is_non_combat_scenario(scenario):
        return True, ""

    if slot in ("Armor", "Shield"):
        return False, (
            "🚫 Combat armor cannot be equipped in a slice-of-life setting.\n"
            "Only civilian clothing (`Top`/`Bottom`) and accessories can be worn here."
        )

    # For Head, Gloves, Shoes: validate item archetype / metadata
    from mechanics.combat.equipment import parse_equipment_metadata
    meta = parse_equipment_metadata(item) if item else {}
    arch = meta.get("archetype", "")
    base_dt = meta.get("base_dt", 0)
    armor_type = meta.get("armor_type", "")

    if slot == "Head":
        from mechanics.combat.items.headwear import NON_COMBAT_HEADWEAR_ARCHETYPES
        if (arch and arch not in NON_COMBAT_HEADWEAR_ARCHETYPES) or base_dt > 0:
            return False, (
                "🚫 Combat helmets and tactical headgear cannot be equipped in a slice-of-life setting.\n"
                "Only civilian headwear (caps, hoods, formal hats) can be worn here."
            )
    elif slot == "Gloves":
        from mechanics.combat.items.gloves import NON_COMBAT_GLOVE_ARCHETYPES
        if (arch and arch not in NON_COMBAT_GLOVE_ARCHETYPES) or armor_type == "heavy" or base_dt > 2:
            return False, (
                "🚫 Heavy combat gauntlets cannot be equipped in a slice-of-life setting.\n"
                "Only civilian or light gloves can be worn here."
            )
    elif slot == "Shoes":
        from mechanics.combat.items.shoes import NON_COMBAT_SHOE_ARCHETYPES
        if (arch and arch not in NON_COMBAT_SHOE_ARCHETYPES) or armor_type == "heavy" or base_dt > 2:
            return False, (
                "🚫 Combat boots and heavy greaves cannot be equipped in a slice-of-life setting.\n"
                "Only civilian footwear (sneakers, sandals, formal shoes) can be worn here."
            )

    return True, ""

def roll_tier() -> int:
    r = random.random()
    if r < 0.05: return 1
    if r < 0.30: return 2
    return 3

def normalize_clothing_scenario(scenario: str) -> str:
    """Normalizes scenario string to canonical clothing genre key."""
    scen = str(scenario or "fantasy").lower().strip()
    if any(w in scen for w in ("steampunk", "clockwork", "victorian")):
        return "steampunk"
    elif any(w in scen for w in ("scifi", "sci_fi", "space", "cyber", "hacker", "tech")):
        return "cyberpunk"
    elif any(w in scen for w in ("dark_fantasy", "nuclear_post_apocalypse", "postapoc", "wasteland", "grimdark")):
        return "dark_fantasy"
    elif any(w in scen for w in ("high_school", "slice_of_life", "non_combat")):
        return "high_school"
    return "fantasy"

def generate_random_clothing(scenario: str = "fantasy", slot: str = "Top", tier: Optional[int] = None) -> Dict[str, Any]:
    item_tier = tier if tier in (1, 2, 3) else roll_tier()
    scen_key = normalize_clothing_scenario(scenario)
    affix_data = SCENARIO_CLOTHING_AFFIXES.get(scen_key, SCENARIO_CLOTHING_AFFIXES["fantasy"])

    if slot == "Top":
        archetype = random.choice(list(CLOTHING_TOPS.keys()))
        base_data = CLOTHING_TOPS[archetype]
    else:
        archetype = random.choice(list(CLOTHING_BOTTOMS.keys()))
        base_data = CLOTHING_BOTTOMS[archetype]

    # Resolve genre-specific base garment name
    genre_names = affix_data.get("archetype_names", {}).get(archetype)
    if genre_names:
        base_name = random.choice(genre_names)
    else:
        base_name = archetype.replace('_', ' ').title()

    # Calculate modifiers: standard regular clothes give at most +1 to SPECIAL stats.
    # Enchanted (Tier 2) and Masterwork (Tier 1) can grant slightly refined social/eva bonuses.
    mods = dict(base_data["social_modifiers"])
    tier_name = TIER_NAMES.get(item_tier, "Standard")
    prefixes = affix_data.get("prefixes", {})

    if item_tier == 2:
        # Tier 2 (Enchanted): EVA +1 bonus or secondary +1 stat
        mods["eva"] = mods.get("eva", 0) + 1
        p_list = prefixes.get(2, ["Enchanted"])
        pref = random.choice(p_list)
        name = f"{pref} {base_name}"
    elif item_tier == 1:
        # Tier 1 (Masterwork): EVA +2 bonus, +1 LUK or +1 CHA
        mods["eva"] = mods.get("eva", 0) + 2
        mods["cha"] = min(2, mods.get("cha", 0) + 1)
        p_list = prefixes.get(1, ["Masterwork"])
        pref = random.choice(p_list)
        name = f"{pref} {base_name}"
    else:
        # Tier 3 (Standard): ~40% chance of standard flavor prefix, otherwise clean base name
        if random.random() < 0.40 and 3 in prefixes and prefixes[3]:
            pref = random.choice(prefixes[3])
            name = f"{pref} {base_name}"
        else:
            name = base_name

    metadata = {
        "name": name,
        "tier": item_tier,
        "tier_name": tier_name,
        "slot": slot,
        "item_type": "Clothing",
        "archetype": archetype,
        "dt": 0,
        "social_modifiers": mods,
        "social_flags": list(base_data["social_flags"]),
        "tags": derive_clothing_tags(style=base_data["style"], social_vibe=base_data["social_flags"])
    }

    return {
        "name": name,
        "item_type": "Clothing",
        "slot": slot,
        "effect": serialize_item(metadata),
        "metadata": metadata,
        "slot_cost": 1
    }

def format_clothing_card(metadata: Dict[str, Any]) -> str:
    name = metadata.get("name", "Clothing")
    tier_name = metadata.get("tier_name", "Standard")
    tags = metadata.get("tags")
    if isinstance(tags, dict):
        style = str(tags.get("style") or metadata.get("style") or "casual").title()
    else:
        style = str(metadata.get("style") or "casual").title()
    social_mods = metadata.get("social_modifiers", {})
    social_flags = ", ".join(metadata.get("social_flags", []))

    mods_str = ", ".join(f"+{v} {k.upper()}" for k, v in social_mods.items() if v > 0) or "None"

    lines = [
        f"**{name}** ({tier_name})",
        f"**Slot:** {metadata.get('slot', 'Clothing')} • **Style:** {style}",
        f"**Social Modifiers:** {mods_str}",
        f"**Vibe:** {social_flags}"
    ]
    return "\n".join(lines)
