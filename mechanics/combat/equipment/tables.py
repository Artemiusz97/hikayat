from __future__ import annotations
"""
Equipment tier definitions, archetype mappings, affix pools, and scenario vocabulary.
"""
import json
import random
import re
from typing import Dict, Any, List, Optional, Tuple

# -----------------------------------------------------------------------------
# 1. ARCHETYPES & ATTRIBUTE TAXONOMY
# -----------------------------------------------------------------------------
from mechanics.combat.items.weapons import WEAPON_ARCHETYPES
from mechanics.combat.items.armors import ARMOR_ARCHETYPES
from mechanics.combat.items.shields import SHIELD_ARCHETYPES
from mechanics.combat.items.accessories import ACCESSORY_ARCHETYPES
from mechanics.combat.items.headwear import HEADWEAR_ARCHETYPES
from mechanics.combat.items.gloves import GLOVE_ARCHETYPES
from mechanics.combat.items.shoes import SHOE_ARCHETYPES
from mechanics.combat.items.clothing import CLOTHING_TOPS, CLOTHING_BOTTOMS
from mechanics.combat.items.envelope import serialize_item

# -----------------------------------------------------------------------------
# 2. RARITY & TIER DEFINITIONS
# -----------------------------------------------------------------------------

TIER_NAMES = {
    3: "Standard",
    2: "Enchanted / Superior",
    1: "Legendary / Relic"
}

TIER_WEIGHTS = {
    3: 0.70,  # 70% Common / Standard
    2: 0.25,  # 25% Rare / Enchanted
    1: 0.05   # 5% Legendary / Masterwork
}

TIER_EMOJIS = {
    3: "⚪",
    2: "🔷",
    1: "👑"
}

# -----------------------------------------------------------------------------
# 3. PROCEDURAL AFFIX & MULTI-ATTRIBUTE GENERATION POOLS
# -----------------------------------------------------------------------------

RANDOM_AFFIX_POOL: Dict[str, Dict[str, Any]] = {
    # Offensive Multiplier Affixes
    "atk_pct": {
        "type": "offensive", "stat": "atk_pct", "label": "ATK Power", "icon": "⚔️",
        "t3_range": (4, 8), "t2_range": (9, 15), "t1_range": (16, 25), "is_pct": True,
        "themes": ["defense", "agility", "arcane"]
    },
    "matk_pct": {
        "type": "offensive", "stat": "matk_pct", "label": "MATK Power", "icon": "🔮",
        "t3_range": (4, 8), "t2_range": (9, 15), "t1_range": (16, 25), "is_pct": True,
        "themes": ["arcane", "holy", "dark"]
    },
    "acc": {
        "type": "offensive", "stat": "acc", "label": "ACC", "icon": "🎯",
        "t3_range": (3, 6), "t2_range": (6, 10), "t1_range": (10, 16), "is_pct": True,
        "themes": ["agility", "arcane"]
    },
    "macc": {
        "type": "offensive", "stat": "macc", "label": "MACC", "icon": "💫",
        "t3_range": (3, 6), "t2_range": (6, 10), "t1_range": (10, 16), "is_pct": True,
        "themes": ["arcane", "holy"]
    },
    "crit": {
        "type": "offensive", "stat": "crit", "label": "CRIT", "icon": "🌟",
        "t3_range": (3, 5), "t2_range": (5, 9), "t1_range": (9, 15), "is_pct": True,
        "themes": ["agility", "dark"]
    },
    # Elemental Damage Conversion Affixes (converts % of player attack to element)
    "fire_convert": {
        "type": "offensive", "stat": "fire_convert", "label": "Fire Conversion", "icon": "🔥",
        "t3_range": (15, 20), "t2_range": (25, 35), "t1_range": (40, 50), "is_pct": True,
        "themes": ["fire"]
    },
    "shock_convert": {
        "type": "offensive", "stat": "shock_convert", "label": "Shock Conversion", "icon": "⚡",
        "t3_range": (15, 20), "t2_range": (25, 35), "t1_range": (40, 50), "is_pct": True,
        "themes": ["shock"]
    },
    "ice_convert": {
        "type": "offensive", "stat": "ice_convert", "label": "Frost Conversion", "icon": "❄️",
        "t3_range": (15, 20), "t2_range": (25, 35), "t1_range": (40, 50), "is_pct": True,
        "themes": ["ice"]
    },
    "poison_convert": {
        "type": "offensive", "stat": "poison_convert", "label": "Poison Conversion", "icon": "🧪",
        "t3_range": (15, 20), "t2_range": (25, 35), "t1_range": (40, 50), "is_pct": True,
        "themes": ["poison"]
    },
    "holy_convert": {
        "type": "offensive", "stat": "holy_convert", "label": "Holy Conversion", "icon": "✨",
        "t3_range": (15, 20), "t2_range": (25, 35), "t1_range": (40, 50), "is_pct": True,
        "themes": ["holy"]
    },
    "dark_convert": {
        "type": "offensive", "stat": "dark_convert", "label": "Dark Conversion", "icon": "🌑",
        "t3_range": (15, 20), "t2_range": (25, 35), "t1_range": (40, 50), "is_pct": True,
        "themes": ["dark"]
    },

    # Defensive & Damage Threshold (DT) Affixes
    "dt_bonus": {
        "type": "defensive", "stat": "dt_bonus", "label": "Hardened Plating", "icon": "🛡️",
        "t3_range": (2, 4), "t2_range": (5, 8), "t1_range": (9, 15), "is_pct": False,
        "themes": ["defense"]
    },
    "magic_dt": {
        "type": "defensive", "stat": "magic_dt", "label": "Arcane Warding", "icon": "🔮",
        "t3_range": (3, 5), "t2_range": (6, 10), "t1_range": (11, 18), "is_pct": False,
        "themes": ["arcane", "holy"]
    },
    "def": {
        "type": "defensive", "stat": "def", "label": "Armor Rating (DEF & DT)", "icon": "🛡️",
        "t3_range": (4, 8), "t2_range": (8, 14), "t1_range": (14, 22), "is_pct": False,
        "themes": ["defense"]
    },
    "mdef": {
        "type": "defensive", "stat": "mdef", "label": "Arcane Defense (MDEF & Magic DT)", "icon": "✨",
        "t3_range": (4, 8), "t2_range": (8, 14), "t1_range": (14, 22), "is_pct": False,
        "themes": ["arcane", "defense"]
    },
    "eva": {
        "type": "defensive", "stat": "eva", "label": "EVA", "icon": "💨",
        "t3_range": (3, 6), "t2_range": (6, 10), "t1_range": (10, 16), "is_pct": True,
        "themes": ["agility"]
    },
    "block_chance": {
        "type": "defensive", "stat": "block_chance", "label": "Block Rate", "icon": "🛡️",
        "t3_range": (4, 8), "t2_range": (8, 14), "t1_range": (14, 20), "is_pct": True,
        "themes": ["defense"]
    },

    # Damage Resistance (DR%) Affixes
    "physical_res": {
        "type": "resistance", "stat": "physical_res", "label": "Kinetic Dampening", "icon": "🪨",
        "t3_range": (6, 10), "t2_range": (11, 18), "t1_range": (19, 28), "is_pct": True,
        "themes": ["defense"]
    },
    "energy_res": {
        "type": "resistance", "stat": "energy_res", "label": "Energy Dissipation", "icon": "⚡",
        "t3_range": (10, 18), "t2_range": (18, 28), "t1_range": (28, 40), "is_pct": True,
        "themes": ["arcane", "shock"]
    },
    "fire_res": {
        "type": "resistance", "stat": "fire_res", "label": "Fire Res", "icon": "🔥",
        "t3_range": (10, 18), "t2_range": (18, 28), "t1_range": (28, 40), "is_pct": True,
        "themes": ["fire"]
    },
    "shock_res": {
        "type": "resistance", "stat": "shock_res", "label": "Shock Res", "icon": "⚡",
        "t3_range": (10, 18), "t2_range": (18, 28), "t1_range": (28, 40), "is_pct": True,
        "themes": ["shock"]
    },
    "ice_res": {
        "type": "resistance", "stat": "ice_res", "label": "Ice Res", "icon": "❄️",
        "t3_range": (10, 18), "t2_range": (18, 28), "t1_range": (28, 40), "is_pct": True,
        "themes": ["ice"]
    },
    "poison_res": {
        "type": "resistance", "stat": "poison_res", "label": "Poison Res", "icon": "🧪",
        "t3_range": (10, 18), "t2_range": (18, 28), "t1_range": (28, 40), "is_pct": True,
        "themes": ["poison"]
    },
    "holy_res": {
        "type": "resistance", "stat": "holy_res", "label": "Holy Res", "icon": "✨",
        "t3_range": (10, 18), "t2_range": (18, 28), "t1_range": (28, 40), "is_pct": True,
        "themes": ["holy"]
    },
    "dark_res": {
        "type": "resistance", "stat": "dark_res", "label": "Dark Res", "icon": "🌑",
        "t3_range": (10, 18), "t2_range": (18, 28), "t1_range": (28, 40), "is_pct": True,
        "themes": ["dark"]
    },
    "omni_res": {
        "type": "resistance", "stat": "omni_res", "label": "Omni Res", "icon": "🌈",
        "t3_range": (0, 0), "t2_range": (8, 14), "t1_range": (15, 25), "is_pct": True,
        "themes": ["arcane", "holy"]
    },

    # Ballistic & Projectile Armor Defense Affixes
    "ballistic_weave": {
        "type": "resistance", "stat": "ballistic_weave", "label": "Ballistic Weave", "icon": "🛡️",
        "t3_range": (6, 10), "t2_range": (10, 16), "t1_range": (16, 24), "is_pct": False,
        "themes": ["defense"]
    },
    "ceramic_insert": {
        "type": "resistance", "stat": "ceramic_insert", "label": "Ceramic Plating", "icon": "🪨",
        "t3_range": (6, 10), "t2_range": (10, 16), "t1_range": (16, 24), "is_pct": False,
        "themes": ["defense"]
    },
    "anti_puncture": {
        "type": "resistance", "stat": "anti_puncture", "label": "Anti-Puncture", "icon": "🗡️",
        "t3_range": (6, 10), "t2_range": (10, 14), "t1_range": (14, 20), "is_pct": False,
        "themes": ["defense"]
    },
    "ablative_coating": {
        "type": "resistance", "stat": "ablative_coating", "label": "Ablative Coating", "icon": "✨",
        "t3_range": (6, 10), "t2_range": (10, 16), "t1_range": (16, 24), "is_pct": False,
        "themes": ["arcane", "defense"]
    },

    # Vitals & Recovery Affixes
    "max_hp": {
        "type": "vitals", "stat": "max_hp", "label": "Max HP", "icon": "❤️",
        "t3_range": (10, 20), "t2_range": (20, 40), "t1_range": (40, 75), "is_pct": False,
        "themes": ["defense"]
    },
    "max_mp": {
        "type": "vitals", "stat": "max_mp", "label": "Max MP", "icon": "💙",
        "t3_range": (8, 15), "t2_range": (15, 30), "t1_range": (30, 60), "is_pct": False,
        "themes": ["arcane"]
    },
    "hp_regen": {
        "type": "vitals", "stat": "hp_regen", "label": "HP Regen", "icon": "💚",
        "t3_range": (1, 2), "t2_range": (2, 4), "t1_range": (4, 8), "is_pct": False,
        "themes": ["holy"]
    },
    "mp_regen": {
        "type": "vitals", "stat": "mp_regen", "label": "MP Regen", "icon": "💙",
        "t3_range": (1, 2), "t2_range": (2, 4), "t1_range": (4, 7), "is_pct": False,
        "themes": ["arcane"]
    }
}

THEME_VOCABULARY: Dict[str, Dict[str, List[str]]] = {
    "fire": {
        "prefixes_t3": ["Cinder", "Warm", "Ember-Forged", "Smoldering"],
        "prefixes_t2": ["Flame-Forged", "Pyre-Bound", "Blazing", "Magma", "Molten"],
        "prefixes_t1": ["Sunfire", "Infernal", "Phoenix-Forged", "Dragon-Fire", "Hellfire"],
        "suffixes_t2": ["of Embers", "of the Flame", "of Ignition", "of Scorch"],
        "suffixes_t1": ["of the Inferno", "of the Sun-King", "of Cataclysmic Fire", "of the Dragon Core"]
    },
    "shock": {
        "prefixes_t3": ["Static", "Spark", "Charged", "Conducted"],
        "prefixes_t2": ["Storm-Wrought", "Thunderous", "Volt-Charged", "Crackling", "Lightning-Etched"],
        "prefixes_t1": ["Thunder God's", "Tempest-Born", "Supercharged", "Maelstrom", "Ion-Fused"],
        "suffixes_t2": ["of Sparks", "of Thunder", "of the Current", "of Jolt"],
        "suffixes_t1": ["of the Tempest", "of the Thunder God", "of Endless Lightning", "of the Storm Sovereign"]
    },
    "ice": {
        "prefixes_t3": ["Chilled", "Frost", "Cold-Iron", "Brisk"],
        "prefixes_t2": ["Frost-Bound", "Glacial", "Permafrost", "Winter-Touched", "Rime-Carved"],
        "prefixes_t1": ["Absolute-Zero", "Glacier-Heart", "Blizzard-Forged", "Cryo-Relic", "Epoch-Ice"],
        "suffixes_t2": ["of Frost", "of the Glacier", "of Winter", "of Rime"],
        "suffixes_t1": ["of the Eternal Winter", "of Absolute Zero", "of the Blizzard Lord", "of Frozen Epochs"]
    },
    "poison": {
        "prefixes_t3": ["Tainted", "Acidic", "Venom", "Corrosive"],
        "prefixes_t2": ["Venomous", "Toxic", "Serpent's", "Acid-Etched", "Viper-Scaled"],
        "prefixes_t1": ["Deathblight", "Plague-Bringer's", "Apex-Toxic", "Necro-Venom", "Miasmic"],
        "suffixes_t2": ["of Venom", "of the Viper", "of Corrosion", "of Decay"],
        "suffixes_t1": ["of the Black Serpent", "of Pestilence", "of Total Contagion", "of Deathblight"]
    },
    "holy": {
        "prefixes_t3": ["Blessed", "Bright", "Hallowed", "Pure"],
        "prefixes_t2": ["Radiant", "Consecrated", "Divine", "Sun-Blessed", "Luminous"],
        "prefixes_t1": ["Seraphic", "Archangel's", "Heavenly", "God-Touched", "Celestial"],
        "suffixes_t2": ["of Light", "of Dawn", "of the Seraph", "of Grace"],
        "suffixes_t1": ["of the Heavens", "of Eternal Dawn", "of Divine Judgement", "of the Sun Deity"]
    },
    "dark": {
        "prefixes_t3": ["Dusk", "Shaded", "Grim", "Shadow"],
        "prefixes_t2": ["Shadow-Forged", "Abyssal", "Void-Touched", "Nether", "Dread"],
        "prefixes_t1": ["Void-Singularity", "Eclipse-Forged", "Nether-Lord's", "Oblivion", "Doom-Wrought"],
        "suffixes_t2": ["of Shadows", "of the Void", "of Dusk", "of the Nether"],
        "suffixes_t1": ["of the Abyss", "of Eclipse", "of Nether Ruin", "of the World-Ender"]
    },
    "defense": {
        "prefixes_t3": ["Stout", "Sturdy", "Hardened", "Reinforced"],
        "prefixes_t2": ["Adamantine", "Bulwark", "Mountain-Hewn", "Ironclad", "Fortified"],
        "prefixes_t1": ["Titan-Forged", "Colossus", "Invulnerable", "Aegis-Bound", "Bastion"],
        "suffixes_t2": ["of Fortitude", "of the Guardian", "of the Mountain", "of Iron"],
        "suffixes_t1": ["of the Titan", "of Invulnerability", "of the Mountain King", "of Unyielding Bastion"]
    },
    "agility": {
        "prefixes_t3": ["Light", "Quick", "Nimble", "Fleet"],
        "prefixes_t2": ["Zephyr", "Feather-Light", "Wind-Carved", "Phantom", "Swiftwing"],
        "prefixes_t1": ["Temporal", "Sonic-Speed", "Mirage", "Shadow-Step", "Gale-Sovereign"],
        "suffixes_t2": ["of Swiftness", "of the Zephyr", "of the Duelist", "of Haste"],
        "suffixes_t1": ["of the Wind God", "of Instant Reflexes", "of the Phantom Lord", "of Temporal Grace"]
    },
    "arcane": {
        "prefixes_t3": ["Rune", "Focus", "Apprentice's", "Mystic"],
        "prefixes_t2": ["Runic", "Gilded", "Mithril", "Eldritch", "Sorcerer's"],
        "prefixes_t1": ["Astral", "Archmage's", "Cosmic", "Leyline-Master's", "Mythic"],
        "suffixes_t2": ["of Warding", "of Arcana", "of the Mystic", "of Focus"],
        "suffixes_t1": ["of Astral Ruin", "of the Archmage", "of Infinite Leylines", "of Immortality"]
    }
}

SCENARIO_AFFIXES: Dict[str, Dict[str, List[str]]] = {
    "fantasy": {
        "prefixes_t3": ["Iron", "Steel", "Hardened", "Honed", "Stout", "Sturdy", "Apprentice's"],
        "prefixes_t2": ["Runic", "Gilded", "Obsidian", "Mithril", "Flame-Forged", "Frost-Bound", "Storm-Wrought"],
        "prefixes_t1": ["Sunfire", "Dragon-Forged", "Void-Touched", "Celestial", "Abyssal", "God-King's", "Aegis-Bound"],
        "suffixes_t2": ["of Sparks", "of Frost", "of the Guardian", "of Swiftness", "of Piercing", "of Warding"],
        "suffixes_t1": ["of the Dragon Slayer", "of the World-Ender", "of Eternal Dawn", "of Astral Ruin", "of Immortality"]
    },
    "scifi": {
        "prefixes_t3": ["Titanium", "Standard-Issue", "Composite", "Field", "Carbon", "Alloy"],
        "prefixes_t2": ["Overcharged", "Plasma-Infused", "Hyper-Coil", "Nanite-Lined", "Cryo-Cooled", "Quantum"],
        "prefixes_t1": ["Supernova", "Antimatter", "Dark-Energy", "Singularity", "Omni-Core", "Chrono-Phase"],
        "suffixes_t2": ["of Havoc", "of Overdrive", "of the Vanguard", "of Phase-Shift", "of the Sentinel"],
        "suffixes_t1": ["of the Dreadnought", "of Absolute Zero", "of Stellar Annihilation", "of the Singularity"]
    },
    "cyberpunk": {
        "prefixes_t3": ["Militech", "Street-Grade", "Chrome", "Reinforced", "Tungsten", "Cyber"],
        "prefixes_t2": ["Overclocked", "Smart-Linked", "Thermal-Chambered", "Neuro-Wired", "Sub-Dermal"],
        "prefixes_t1": ["Arasaka Prototype", "Black-ICE", "Kiroshi Masterwork", "Ghost-Protocol", "Zero-Day"],
        "suffixes_t2": ["of the Phantom", "of the Mercenary", "of Recoil-Bypass", "of Target-Lock"],
        "suffixes_t1": ["of Cyber-Dominance", "of the High-Roller", "of Neural Decapitation"]
    },
    "postapoc": {
        "prefixes_t3": ["Scrap-Metal", "Rusty", "Spiked", "Jury-Rigged", "Makeshift", "Lead-Lined"],
        "prefixes_t2": ["Rad-Hardened", "Bio-Toxic", "Reinforced-Steel", "Wasteland-Master", "Fuel-Injected"],
        "prefixes_t1": ["Doomsday", "Nuclear-Winter", "Alpha-Mutant", "Apex-Scavenger", "Titan-Forged"],
        "suffixes_t2": ["of the Scavenger", "of the Raider", "of Rust & Ruin", "of the Wasteland"],
        "suffixes_t1": ["of Total Extinction", "of the Apocalypse Sovereign", "of the Radioactive Storm"]
    },
    "high_school": {
        "prefixes_t3": ["Standard", "Student", "Classroom", "Campus", "Clean", "Everyday", "Casual"],
        "prefixes_t2": ["Tailored", "Designer", "Honors", "Varsity", "Vintage", "Preppy", "Trendy"],
        "prefixes_t1": ["Student Council President's", "Valedictorian's", "Festival Champion's", "Custom-Tailored", "Prizewinning"],
        "suffixes_t2": ["of the Honor Roll", "of Youth", "of the Study Group", "of Style", "of Friendship"],
        "suffixes_t1": ["of Everlasting Memories", "of the Grand Festival", "of Pure Romance", "of the Campus Legend"]
    },
    "slice_of_life": {
        "prefixes_t3": ["Cozy", "Comfy", "Pastel", "Handmade", "Simple", "Favorite"],
        "prefixes_t2": ["Artisanal", "Boutique", "Charming", "Warm", "Sentimental", "Aesthetic"],
        "prefixes_t1": ["Heirloom", "Beloved", "Prizewinning", "Heartwarming", "Iconic"],
        "suffixes_t2": ["of Cozy Days", "of the Neighborhood", "of Sunny Afternoons", "of Heartfelt Bonds"],
        "suffixes_t1": ["of Cherished Moments", "of Endless Spring", "of True Harmony"]
    },
    "non_combat": {
        "prefixes_t3": ["Standard", "Casual", "Everyday", "Neat", "Simple"],
        "prefixes_t2": ["Stylish", "Bespoke", "Polished", "Trendy", "Elegant"],
        "prefixes_t1": ["Masterpiece", "Signature", "Iconic", "Prestige", "Exquisite"],
        "suffixes_t2": ["of Personal Flair", "of Elegance", "of Leisure", "of Everyday Joy"],
        "suffixes_t1": ["of Perfection", "of Unforgettable Memories", "of Peerless Charm"]
    }
}

NON_COMBAT_WEAPON_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "fountain_pen": {"name": "Fountain Pen", "mass": "light", "handedness": "1H", "attack_types": ["utility"]},
    "mechanical_pencil": {"name": "Mechanical Pencil", "mass": "light", "handedness": "1H", "attack_types": ["utility"]},
    "wooden_ruler": {"name": "Wooden Ruler", "mass": "light", "handedness": "1H", "attack_types": ["utility"]},
    "umbrella": {"name": "Vinyl Umbrella", "mass": "light", "handedness": "1H", "attack_types": ["utility"]},
    "tennis_racket": {"name": "Tennis Racket", "mass": "light", "handedness": "1H", "attack_types": ["sports"]},
    "smart_stylus": {"name": "Digital Stylus", "mass": "light", "handedness": "1H", "attack_types": ["tech"]},
    "acoustic_guitar": {"name": "Acoustic Guitar", "mass": "medium", "handedness": "2H", "attack_types": ["music"]},
    "sketchbook": {"name": "Hardcover Sketchbook", "mass": "light", "handedness": "1H", "attack_types": ["art"]}
}

NON_COMBAT_ARMOR_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "school_blazer": {"name": "School Blazer", "armor_type": "clothing", "protection_types": ["style"]},
    "cardigan": {"name": "Knitted Cardigan", "armor_type": "clothing", "protection_types": ["warmth"]},
    "sailor_uniform": {"name": "Sailor Uniform Top", "armor_type": "clothing", "protection_types": ["style"]},
    "pleated_skirt": {"name": "Pleated Uniform Skirt", "armor_type": "clothing", "protection_types": ["style"]},
    "uniform_slacks": {"name": "Pressed Uniform Slacks", "armor_type": "clothing", "protection_types": ["style"]},
    "hoodie": {"name": "Casual Streetwear Hoodie", "armor_type": "clothing", "protection_types": ["comfort"]},
    "tracksuit": {"name": "PE Athletic Tracksuit", "armor_type": "clothing", "protection_types": ["athletic"]}
}

NON_COMBAT_SHIELD_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "school_satchel": {"name": "Leather School Satchel", "mass": "light", "handedness": "1H", "block_chance": 0},
    "canvas_backpack": {"name": "Canvas Student Backpack", "mass": "light", "handedness": "1H", "block_chance": 0},
    "tote_bag": {"name": "Cotton Tote Bag", "mass": "light", "handedness": "1H", "block_chance": 0},
    "binder_folder": {"name": "Hardcover Ring Binder", "mass": "light", "handedness": "1H", "block_chance": 0}
}

NON_COMBAT_ACCESSORY_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "school_ribbon": {"slot": "Accessory 1", "name": "Silk Uniform Ribbon"},
    "enamel_badge": {"slot": "Accessory 2", "name": "Student Council Enamel Pin"},
    "smartwatch": {"slot": "Accessory 3", "name": "Modern Smartwatch"},
    "charm_keychain": {"slot": "Accessory 4", "name": "Cute Mascot Keychain"},
    "earbuds": {"slot": "Accessory 1", "name": "Wireless Earbuds"}
}

# -----------------------------------------------------------------------------
# 4. METADATA PARSING, SERIALIZATION & CARD FORMATTING
# -----------------------------------------------------------------------------

