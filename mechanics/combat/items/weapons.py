from __future__ import annotations
import random
from typing import Dict, Any, Optional

from mechanics.combat.items.tags import derive_weapon_tags
from mechanics.combat.items.envelope import serialize_item

WEAPON_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "dagger": {
        "mass": "light", "handedness": "1H", "attack_types": ["thrust", "slash"],
        "default_damage": {"physical": 1.0}, "multiplier": 0.85, "crit_bonus": 12,
        "base_acc": 8, "base_eva": 4
    },
    "shortsword": {
        "mass": "light", "handedness": "1H", "attack_types": ["slash", "thrust"],
        "default_damage": {"physical": 1.0}, "multiplier": 1.00, "crit_bonus": 8,
        "base_acc": 6, "base_eva": 4
    },
    "wand": {
        "mass": "light", "handedness": "1H", "attack_types": ["magic_channel"],
        "default_damage": {"magical": 1.0}, "multiplier": 1.10, "crit_bonus": 2,
        "base_macc": 6, "base_eva": 2, "projectile_type": "energy_cell"
    },
    "pistol": {
        "mass": "light", "handedness": "1H", "attack_types": ["ranged"],
        "default_damage": {"ballistic": 1.0}, "multiplier": 1.00, "crit_bonus": 5,
        "base_acc": 6, "base_eva": 2, "projectile_type": "pistol_round"
    },
    "throwing": {
        "mass": "light", "handedness": "1H", "attack_types": ["ranged"],
        "default_damage": {"physical": 1.0}, "multiplier": 0.90, "crit_bonus": 8,
        "base_acc": 10, "base_eva": 4, "projectile_type": "arrow"
    },
    "sword": {
        "mass": "medium", "handedness": "Versatile", "attack_types": ["slash", "thrust"],
        "default_damage": {"physical": 1.0}, "multiplier": 1.25, "crit_bonus": 4,
        "base_acc": 4, "base_eva": 0
    },
    "axe": {
        "mass": "medium", "handedness": "Versatile", "attack_types": ["hack", "slash"],
        "default_damage": {"physical": 1.0}, "multiplier": 1.30, "crit_bonus": 4,
        "base_acc": 2, "base_eva": 0
    },
    "mace": {
        "mass": "medium", "handedness": "Versatile", "attack_types": ["blunt"],
        "default_damage": {"physical": 1.0}, "multiplier": 1.30, "crit_bonus": 2,
        "base_acc": 2, "base_eva": 0
    },
    "spear": {
        "mass": "medium", "handedness": "Versatile", "attack_types": ["thrust"],
        "default_damage": {"physical": 1.0}, "multiplier": 1.20, "crit_bonus": 4,
        "base_acc": 6, "base_eva": 0
    },
    "revolver": {
        "mass": "medium", "handedness": "1H", "attack_types": ["ranged"],
        "default_damage": {"ballistic": 1.0}, "multiplier": 1.25, "crit_bonus": 6,
        "base_acc": 4, "base_eva": 0, "projectile_type": "pistol_round"
    },
    "greatsword": {
        "mass": "heavy", "handedness": "2H", "attack_types": ["slash", "hack"],
        "default_damage": {"physical": 1.0}, "multiplier": 1.80, "crit_bonus": 2,
        "base_acc": 2, "base_eva": -4
    },
    "polearm": {
        "mass": "heavy", "handedness": "2H", "attack_types": ["thrust", "hack"],
        "default_damage": {"physical": 1.0}, "multiplier": 1.70, "crit_bonus": 2,
        "base_acc": 4, "base_eva": -2
    },
    "warhammer": {
        "mass": "heavy", "handedness": "2H", "attack_types": ["blunt"],
        "default_damage": {"physical": 1.0}, "multiplier": 1.90, "crit_bonus": 0,
        "base_acc": 0, "base_eva": -4
    },
    "staff": {
        "mass": "heavy", "handedness": "2H", "attack_types": ["blunt", "magic_channel"],
        "default_damage": {"magical": 1.0}, "multiplier": 1.15, "crit_bonus": 2,
        "base_macc": 6, "base_eva": 0
    },
    "bow": {
        "mass": "heavy", "handedness": "2H", "attack_types": ["ranged"],
        "default_damage": {"physical": 1.0}, "multiplier": 1.45, "crit_bonus": 4,
        "base_acc": 10, "base_eva": 0, "projectile_type": "arrow"
    },
    "crossbow": {
        "mass": "heavy", "handedness": "2H", "attack_types": ["ranged"],
        "default_damage": {"physical": 1.0}, "multiplier": 1.50, "crit_bonus": 4,
        "base_acc": 8, "base_eva": -2, "projectile_type": "bolt"
    },
    "rifle": {
        "mass": "heavy", "handedness": "2H", "attack_types": ["ranged"],
        "default_damage": {"ballistic": 1.0}, "multiplier": 1.55, "crit_bonus": 6,
        "base_acc": 8, "base_eva": -2, "projectile_type": "rifle_round"
    },
    "shotgun": {
        "mass": "heavy", "handedness": "2H", "attack_types": ["ranged", "blunt"],
        "default_damage": {"ballistic": 1.0}, "multiplier": 1.60, "crit_bonus": 0,
        "base_acc": -2, "base_eva": -4, "projectile_type": "scatter_shot"
    },
    "machinegun": {
        "mass": "heavy", "handedness": "2H", "attack_types": ["ranged", "aoe"],
        "default_damage": {"ballistic": 1.0}, "multiplier": 1.65, "crit_bonus": -2,
        "base_acc": -4, "base_eva": -6, "projectile_type": "high_caliber_round"
    },
    "explosive": {
        "mass": "heavy", "handedness": "2H", "attack_types": ["explosive", "aoe"],
        "default_damage": {"explosive": 1.0}, "multiplier": 1.80, "crit_bonus": -4,
        "base_acc": 0, "base_eva": -6, "projectile_type": "scatter_shot"
    },
    "musket": {
        "mass": "medium", "handedness": "2H",
        "attack_types": ["ranged", "thrust", "blunt"],
        "attack_profiles": {
            "ranged": {"multiplier": 1.55, "damage_type": "ballistic", "acc": 6},
            "thrust": {"multiplier": 1.20, "damage_type": "physical", "acc": 8},
            "blunt":  {"multiplier": 0.90, "damage_type": "physical", "acc": 2}
        },
        "default_damage": {"ballistic": 1.0}, "multiplier": 1.55, "crit_bonus": 4,
        "base_acc": 6, "base_eva": -2, "special_traits": ["bayonet_equipped", "hybrid_melee_ranged"],
        "projectile_type": "rifle_round"
    },
    "katana": {
        "mass": "medium", "handedness": "Versatile", "attack_types": ["slash", "thrust"],
        "default_damage": {"physical": 1.0}, "multiplier": 1.25, "crit_bonus": 8,
        "base_acc": 6, "base_eva": 2
    },
    "rapier": {
        "mass": "light", "handedness": "1H", "attack_types": ["thrust"],
        "default_damage": {"physical": 1.0}, "multiplier": 1.05, "crit_bonus": 8,
        "base_acc": 8, "base_eva": 4
    },
    "cleaver": {
        "mass": "medium", "handedness": "1H", "attack_types": ["hack", "slash"],
        "default_damage": {"physical": 1.0}, "multiplier": 1.20, "crit_bonus": 4,
        "base_acc": 2, "base_eva": 0
    },
    "baton": {
        "mass": "light", "handedness": "Versatile", "attack_types": ["blunt"],
        "default_damage": {"physical": 1.0}, "multiplier": 0.95, "crit_bonus": 2,
        "base_acc": 6, "base_eva": 2
    },
    "bat": {
        "mass": "medium", "handedness": "2H", "attack_types": ["blunt"],
        "default_damage": {"physical": 1.0}, "multiplier": 1.40, "crit_bonus": 4,
        "base_acc": 4, "base_eva": -2
    },
    "whip": {
        "mass": "light", "handedness": "1H", "attack_types": ["slash"],
        "default_damage": {"physical": 1.0}, "multiplier": 1.00, "crit_bonus": 10,
        "base_acc": 6, "base_eva": 4
    },
    "submachinegun": {
        "mass": "light", "handedness": "1H", "attack_types": ["ranged", "aoe"],
        "default_damage": {"ballistic": 1.0}, "multiplier": 1.15, "crit_bonus": -2,
        "base_acc": 2, "base_eva": 0, "projectile_type": "pistol_round"
    },
    "railgun": {
        "mass": "heavy", "handedness": "2H", "attack_types": ["ranged"],
        "default_damage": {"ballistic": 1.0}, "multiplier": 1.95, "crit_bonus": 10,
        "base_acc": 10, "base_eva": -6, "projectile_type": "high_caliber_round"
    },
    "flamethrower": {
        "mass": "heavy", "handedness": "2H", "attack_types": ["aoe"],
        "default_damage": {"fire": 1.0}, "multiplier": 1.50, "crit_bonus": -4,
        "base_acc": -2, "base_eva": -4, "projectile_type": "energy_cell"
    },
    "fist_weapon": {
        "mass": "light", "handedness": "1H", "attack_types": ["blunt", "slash"],
        "default_damage": {"physical": 1.0}, "multiplier": 0.85, "crit_bonus": 10,
        "base_acc": 8, "base_eva": 6
    },
    "improvised": {
        "mass": "light", "handedness": "1H", "attack_types": ["blunt"],
        "default_damage": {"physical": 1.0}, "multiplier": 0.70, "crit_bonus": 0,
        "base_acc": 2, "base_eva": 0
    }
}

NON_COMBAT_WEAPON_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "fountain_pen": {
        "mass": "light", "handedness": "1H", "attack_types": ["utility", "stabbing"],
        "default_damage": {"physical": 1.0}, "multiplier": 0.75, "crit_bonus": 6,
        "base_acc": 3, "base_eva": 0
    },
    "mechanical_pencil": {
        "mass": "light", "handedness": "1H", "attack_types": ["utility", "stabbing"],
        "default_damage": {"physical": 1.0}, "multiplier": 0.70, "crit_bonus": 4,
        "base_acc": 2, "base_eva": 0
    },
    "wooden_ruler": {
        "mass": "light", "handedness": "1H", "attack_types": ["utility", "bludgeoning"],
        "default_damage": {"physical": 1.0}, "multiplier": 0.80, "crit_bonus": 2,
        "base_acc": 2, "base_eva": 1
    },
    "umbrella": {
        "mass": "light", "handedness": "1H", "attack_types": ["utility", "bludgeoning", "stabbing"],
        "default_damage": {"physical": 1.0}, "multiplier": 0.90, "crit_bonus": 4,
        "base_acc": 1, "base_eva": 2
    },
    "tennis_racket": {
        "mass": "light", "handedness": "1H", "attack_types": ["sports", "bludgeoning"],
        "default_damage": {"physical": 1.0}, "multiplier": 0.95, "crit_bonus": 6,
        "base_acc": 3, "base_eva": 2
    },
    "smart_stylus": {
        "mass": "light", "handedness": "1H", "attack_types": ["tech", "stabbing"],
        "default_damage": {"physical": 0.5, "energy": 0.5}, "multiplier": 0.75, "crit_bonus": 5,
        "base_acc": 4, "base_eva": 0
    },
    "acoustic_guitar": {
        "mass": "medium", "handedness": "2H", "attack_types": ["music", "bludgeoning"],
        "default_damage": {"physical": 1.0}, "multiplier": 1.10, "crit_bonus": 5,
        "base_acc": 0, "base_eva": -1
    },
    "lacrosse_stick": {
        "mass": "medium", "handedness": "2H", "attack_types": ["sports", "bludgeoning"],
        "default_damage": {"physical": 1.0}, "multiplier": 1.15, "crit_bonus": 4,
        "base_acc": 2, "base_eva": 0
    },
    "camera": {
        "mass": "light", "handedness": "1H", "attack_types": ["tech", "channeling"],
        "default_damage": {"energy": 1.0}, "multiplier": 0.70, "crit_bonus": 10,
        "base_acc": 4, "base_eva": 0
    },
    "sketchbook": {
        "mass": "light", "handedness": "1H", "attack_types": ["art", "bludgeoning"],
        "default_damage": {"physical": 1.0}, "multiplier": 0.70, "crit_bonus": 3,
        "base_acc": 1, "base_eva": 1
    }
}

for arch, data in list(WEAPON_ARCHETYPES.items()) + list(NON_COMBAT_WEAPON_ARCHETYPES.items()):
    # Ensure attack_profiles exist for every archetype
    if "attack_profiles" not in data:
        base_dmg_type = list(data.get("default_damage", {"physical": 1.0}).keys())[0]
        base_mult = data.get("multiplier", 1.0)
        data["attack_profiles"] = {
            atk_type: {
                "multiplier": base_mult,
                "damage_type": base_dmg_type,
                "acc": data.get("base_acc", 0)
            }
            for atk_type in data.get("attack_types", ["slash"])
        }
    
    # Extract all distinct damage types across profiles
    profile_dmg_types = list({p["damage_type"] for p in data["attack_profiles"].values()})
    
    data["tags"] = derive_weapon_tags(
        archetype=arch,
        handedness=data["handedness"],
        mass=data["mass"],
        attack_types=data["attack_types"],
        damage_types=profile_dmg_types,
        special_traits=data.get("special_traits", []),
        projectile_type=data.get("projectile_type")
    )

THEME_AFFIXES: Dict[str, Dict[str, list[str]]] = {
    "fire": {
        "prefixes_t3": ["Cinder", "Warm", "Ember-Forged", "Smoldering"],
        "prefixes_t2": ["Flame-Forged", "Pyre-Bound", "Blazing", "Magma", "Molten"],
        "prefixes_t1": ["Sunfire", "Infernal", "Phoenix-Forged", "Dragon-Fire", "Hellfire"],
        "suffixes_t2": ["of Embers", "of the Flame", "of Ignition", "of Scorch"],
        "suffixes_t1": ["of the Inferno", "of the Sun-King", "of Cataclysmic Fire", "of the Dragon Core"]
    }
}

ARMOR_PIERCING_AFFIXES: Dict[str, float] = {
    # 25% DT penetration
    "thermal-chambered": 0.25,
    "valve rupture": 0.25,
    "pressurized": 0.25,
    "spike-studded": 0.25,
    "piercing": 0.25,
    # 35% DT penetration
    "blight-edged": 0.35,
    "high-frequency": 0.35,
    # 40% DT penetration
    "monomolecular": 0.40,
    "mono-wire": 0.40,
    "monowire": 0.40,
    "hyper-coil": 0.40,
    # 55% DT penetration
    "vibro-edged": 0.55,
    "vibro": 0.55,
    "quantum-phase": 0.55,
    "god-slayer": 0.55,
    # 75% DT penetration (Strict 75% Maximum Ceiling)
    "phase-shifted": 0.75,
    "phase-shift": 0.75,
    "star-forged": 0.75,
    "void-touched": 0.75,
    "antimatter": 0.75,
    "singularity": 0.75,
    "zero-day": 0.75,
}

SCENARIO_AFFIXES: Dict[str, Dict[str, list[str]]] = {
    "fantasy": {
        "prefixes_t3": ["Iron", "Steel", "Hardened", "Honed", "Stout", "Sturdy", "Apprentice's"],
        "prefixes_t2": ["Runic", "Gilded", "Obsidian", "Mithril", "Flame-Forged", "Frost-Bound", "Storm-Wrought", "Vibro-Edged"],
        "prefixes_t1": ["Sunfire", "Dragon-Forged", "Void-Touched", "Star-Forged", "Celestial", "Abyssal", "God-King's", "Aegis-Bound"],
        "suffixes_t2": ["of Sparks", "of Frost", "of the Guardian", "of Swiftness", "of Piercing", "of Warding"],
        "suffixes_t1": ["of the Dragon Slayer", "of the World-Ender", "of Eternal Dawn", "of Astral Ruin", "of Immortality"]
    },
    "steampunk": {
        "prefixes_t3": ["Brass-Plated", "Copper", "Clockwork", "Steam-Vented", "Rivet-Bound", "Machinist's", "Standard"],
        "prefixes_t2": ["Pneumatic", "Galvanic", "Aether-Tuned", "Boiler-Forged", "Voltaic", "Pressurized", "Gilded-Gear"],
        "prefixes_t1": ["Perpetual-Motion", "Grand Victorian", "Master Artificer's", "Aether-Sovereign's", "Dreadnought's", "Tesla's Masterwork"],
        "suffixes_t2": ["of the Piston", "of Steam Exhaust", "of Galvanic Induction", "of Copper Coils", "of Valve Rupture"],
        "suffixes_t1": ["of Clockwork Ruin", "of the Brass Core", "of Endless Pressure", "of the High Boiler", "of Aetheric Resonance"]
    },
    "cyberpunk": {
        "prefixes_t3": ["Street-Grade", "Mil-Spec", "Chrome", "Tungsten", "Carbon-Weave", "Reinforced", "Standard-Issue"],
        "prefixes_t2": ["Overclocked", "Smart-Linked", "Thermal-Chambered", "Monomolecular", "Neuro-Wired", "Sub-Dermal", "High-Frequency"],
        "prefixes_t1": ["Arasaka Prototype", "Kiroshi Masterwork", "Black-ICE", "Ghost-Protocol", "Zero-Day", "Militech Apex", "Hyper-Threaded"],
        "suffixes_t2": ["of the Phantom", "of Recoil-Bypass", "of Target-Lock", "of the Mercenary", "of the Street Runner"],
        "suffixes_t1": ["of Cyber-Dominance", "of Neural Decapitation", "of the High-Roller", "of System Overload", "of Total Wipe"]
    },
    "nuclear_post_apocalypse": {
        "prefixes_t3": ["Scrap-Metal", "Rusty", "Spiked", "Jury-Rigged", "Makeshift", "Lead-Lined", "Weathered"],
        "prefixes_t2": ["Rad-Hardened", "Bio-Toxic", "Reinforced-Steel", "Wasteland-Master", "Fuel-Injected", "Gamma-Tuned", "Spike-Studded"],
        "prefixes_t1": ["Doomsday", "Nuclear-Winter", "Alpha-Mutant", "Apex-Scavenger", "Titan-Forged", "Irradiated", "God-Corpse"],
        "suffixes_t2": ["of the Scavenger", "of the Raider", "of Rust & Ruin", "of the Wasteland", "of the Fallout Shelter"],
        "suffixes_t1": ["of Total Extinction", "of the Apocalypse Sovereign", "of the Radioactive Storm", "of Endless Ruin"]
    },
    "sci_fi": {
        "prefixes_t3": ["Titanium", "Standard-Issue", "Composite", "Field", "Carbon-Alloy", "Ceramic"],
        "prefixes_t2": ["Overcharged", "Plasma-Infused", "Hyper-Coil", "Nanite-Lined", "Cryo-Cooled", "Quantum-Phase", "Graviton"],
        "prefixes_t1": ["Supernova", "Antimatter", "Dark-Energy", "Singularity", "Omni-Core", "Chrono-Phase", "Tachyon"],
        "suffixes_t2": ["of Havoc", "of Overdrive", "of the Vanguard", "of Phase-Shift", "of the Sentinel", "of Target Vector"],
        "suffixes_t1": ["of the Dreadnought", "of Absolute Zero", "of Stellar Annihilation", "of the Singularity Core", "of Orbital Ruin"]
    },
    "dark_fantasy": {
        "prefixes_t3": ["Weathered", "Blood-Stained", "Grim", "Jagged", "Ashen", "Roughspun", "Grave-Dug"],
        "prefixes_t2": ["Hex-Forged", "Cursed", "Grave-Tainted", "Sanguine", "Blight-Edged", "Bone-Carved", "Shadow-Veiled"],
        "prefixes_t1": ["Eldritch", "Abyssal-Vein", "Death-Lord's", "God-Slayer's", "Cataclysmic", "Blood-Pact", "Marrow-Forged"],
        "suffixes_t2": ["of Torment", "of the Grave", "of the Pale Moon", "of Weeping Shadow", "of the Hex-Binder"],
        "suffixes_t1": ["of Eternal Damnation", "of the Abyssal Void", "of Endless Agony", "of the Desolate Throne"]
    },
    "high_school": {
        "prefixes_t3": ["Standard", "Student", "Classroom", "Campus", "Clean", "Everyday", "Casual"],
        "prefixes_t2": ["Tailored", "Designer", "Honors", "Varsity", "Vintage", "Preppy", "Trendy", "Customized"],
        "prefixes_t1": ["Student Council President's", "Valedictorian's", "Festival Champion's", "Custom-Tailored", "Prizewinning", "Campus Legend's"],
        "suffixes_t2": ["of the Honor Roll", "of Youth", "of the Study Group", "of Style", "of Friendship", "of Victory"],
        "suffixes_t1": ["of Everlasting Memories", "of the Grand Festival", "of Pure Romance", "of the Campus Legend", "of the Championship"]
    }
}

def normalize_weapon_scenario(scenario: str) -> str:
    """Normalizes scenario string to canonical weapon affix key."""
    scen = str(scenario or "fantasy").lower().strip()
    if any(w in scen for w in ("steampunk", "clockwork", "victorian", "aether", "boiler")):
        return "steampunk"
    if any(w in scen for w in ("cyberpunk", "cyber", "hacker", "techie", "netrunner")):
        return "cyberpunk"
    if any(w in scen for w in ("apocalypse", "apocalyptic", "wasteland", "fallout", "rad", "nuclear", "postapoc")):
        return "nuclear_post_apocalypse"
    if any(w in scen for w in ("sci_fi", "scifi", "space", "future", "marine", "star")):
        return "sci_fi"
    if any(w in scen for w in ("dark_fantasy", "grim", "gothic", "eldritch", "curse", "blood", "horror", "grave")):
        return "dark_fantasy"
    if any(w in scen for w in ("school", "drama", "modern", "slice", "academy", "non_combat")):
        return "high_school"
    return "fantasy"

def roll_tier() -> int:
    r = random.random()
    if r < 0.05: return 1
    if r < 0.30: return 2
    return 3

def deduce_weapon_archetype(name: str, pool_dict: Dict[str, Any] | None = None) -> str:
    """Deduces the most suitable weapon archetype key from a weapon name."""
    if not name:
        return "sword"
    name_lower = name.lower()
    
    # Priority keyword mapping: longer / more specific matches first
    checks = [
        (["greatsword", "claymore", "zweihander"], "greatsword"),
        (["shortsword", "gladius"], "shortsword"),
        (["baseball bat", "wooden bat", "spiked bat"], "bat"),
        (["kendo sword", "bokken", "shinai"], "katana"),
        (["submachinegun", "smg", "machine pistol"], "submachinegun"),
        (["pipe rifle", "sniper rifle", "hunting rifle", "carbine", "rifle"], "rifle"),
        (["shotgun", "scattergun"], "shotgun"),
        (["revolver", "six-shooter", "derringer"], "revolver"),
        (["fountain pen"], "fountain_pen"),
        (["mechanical pencil"], "mechanical_pencil"),
        (["wooden ruler"], "wooden_ruler"),
        (["tennis racket"], "tennis_racket"),
        (["smart stylus"], "smart_stylus"),
        (["acoustic guitar"], "acoustic_guitar"),
        (["lacrosse stick"], "lacrosse_stick"),
        (["heavy camera", "camera"], "camera"),
        (["textbook", "sketchbook"], "sketchbook"),
        (["pepper spray"], "improvised"),
        (["candelabra"], "improvised"),
        (["lead-pipe", "lead pipe", "pipe baton"], "baton"),
        (["sledgehammer", "heavy spanner", "spanner", "wrench"], "warhammer"),
        (["kunai set", "kunai", "throwing knife", "shuriken"], "throwing"),
        (["plasma torch", "utility cutter", "stun projector"], "pistol"),
        (["bayoneted musket", "musket"], "musket"),
        (["harpoon", "steam harpoon"], "spear"),
        (["railgun"], "railgun"),
        (["flamethrower"], "flamethrower"),
        (["machinegun", "minigun"], "machinegun"),
        (["polearm", "halberd", "glaive", "lance", "pike"], "polearm"),
        (["warhammer", "hammer"], "warhammer"),
        (["crossbow"], "crossbow"),
        (["katana", "nodachi", "wakizashi", "tanto"], "katana"),
        (["rapier", "estoc", "epee", "foil"], "rapier"),
        (["cleaver"], "cleaver"),
        (["baton", "nightstick", "truncheon"], "baton"),
        (["whip"], "whip"),
        (["fist", "knuckle", "claws", "cestus"], "fist_weapon"),
        (["dagger", "stiletto", "knife", "dirk"], "dagger"),
        (["spear", "javelin"], "spear"),
        (["mace", "morningstar", "club", "flail"], "mace"),
        (["staff", "rod", "stave"], "staff"),
        (["wand"], "wand"),
        (["bow", "shortbow", "longbow"], "bow"),
        (["pistol", "blaster", "handgun", "sidearm"], "pistol"),
        (["axe", "hatchet", "tomahawk", "chopper"], "axe"),
        (["sword", "blade", "longsword", "scimitar", "saber", "broadsword"], "sword"),
        (["umbrella", "parasol"], "umbrella"),
        (["pen"], "fountain_pen"),
        (["pencil"], "mechanical_pencil"),
        (["ruler"], "wooden_ruler"),
        (["bat"], "bat"),
    ]
    for keywords, arch_key in checks:
        if any(k in name_lower for k in keywords):
            if pool_dict is None or arch_key in pool_dict:
                return arch_key
            
    # Check if any archetype key is substring
    if pool_dict:
        for k in pool_dict:
            if k in name_lower or k.replace("_", " ") in name_lower:
                return k
        return list(pool_dict.keys())[0]
    return "sword"

def generate_random_equipment(
    scenario: str = "fantasy",
    slot: str = "Weapon",
    tier: Optional[int] = None,
    archetype: Optional[str] = None,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    item_tier = tier if tier in (1, 2, 3) else roll_tier()
    scen_key = normalize_weapon_scenario(scenario)
    
    # Check if scenario is non-combat / slice-of-life
    try:
        from scenario_data import is_non_combat_scenario
        use_non_combat = is_non_combat_scenario(scenario) or scen_key == "high_school"
    except Exception:
        use_non_combat = scen_key == "high_school"
        
    pool_dict = NON_COMBAT_WEAPON_ARCHETYPES if use_non_combat else WEAPON_ARCHETYPES
    
    if archetype and archetype in pool_dict:
        arch = archetype
    elif name:
        arch = deduce_weapon_archetype(name, pool_dict)
    else:
        arch = random.choice(list(pool_dict.keys()))
        
    base_data = pool_dict[arch]
    
    scen_affixes = SCENARIO_AFFIXES.get(scen_key, SCENARIO_AFFIXES["fantasy"])
    
    if name:
        item_name = str(name).strip()
    else:
        prefix_pool = scen_affixes.get(f"prefixes_t{item_tier}", ["Fine"])
        suffix_pool = scen_affixes.get(f"suffixes_t{item_tier}", ["of Power"])
        base_name = arch.replace("_", " ").title()
        if item_tier == 3:
            item_name = f"{random.choice(prefix_pool)} {base_name}"
        else:
            item_name = f"{random.choice(prefix_pool)} {base_name} {random.choice(suffix_pool)}"
        
    stat_mods: Dict[str, Any] = {}
    tags_dict = dict(base_data["tags"])
    
    # Check for armor piercing affixes
    name_lower = item_name.lower()
    ap_val = 0.0
    for affix_key, val in ARMOR_PIERCING_AFFIXES.items():
        if affix_key in name_lower:
            ap_val = max(ap_val, val)
    ap_val = min(0.75, ap_val)  # Strict 75% ceiling
    if ap_val > 0:
        stat_mods["armor_penetration"] = ap_val
        if "special_traits" not in tags_dict:
            tags_dict["special_traits"] = []
        if "armor_piercing" not in tags_dict["special_traits"]:
            tags_dict["special_traits"].append("armor_piercing")

    metadata = {
        "name": item_name,
        "tier": item_tier,
        "slot": "Weapon",
        "item_type": "Weapon",
        "archetype": arch,
        "mass": base_data.get("mass", "medium"),
        "handedness": base_data.get("handedness", "1H"),
        "multiplier": base_data["multiplier"],
        "crit_bonus": base_data.get("crit_bonus", 0),
        "attack_types": list(base_data["attack_types"]),
        "attack_profiles": dict(base_data.get("attack_profiles", {})),
        "damage_types": dict(base_data["default_damage"]),
        "tags": tags_dict,
        "stat_modifiers": stat_mods
    }
    if ap_val > 0:
        metadata["armor_penetration"] = ap_val
    if "projectile_type" in base_data:
        metadata["projectile_type"] = base_data["projectile_type"]
    
    return {
        "name": item_name,
        "item_type": "Weapon",
        "slot": "Weapon",
        "effect": serialize_item(metadata),
        "metadata": metadata,
        "slot_cost": 1
    }

def generate_starting_weapons(scenario: str = "fantasy", count: int = 6) -> List[Dict[str, Any]]:
    """Generates procedural starting weapons using the new weapon generation system."""
    return [generate_random_equipment(scenario=scenario, slot="Weapon", tier=3) for _ in range(count)]

def format_equipment_card(metadata: Dict[str, Any]) -> str:
    tier = metadata.get("tier", 3)
    name = metadata.get("name", "Weapon")
    arch = metadata.get("archetype", "weapon").replace("_", " ").title()
    mult = metadata.get("multiplier", 1.0)
    crit = metadata.get("crit_bonus", 0)
    hand = metadata.get("handedness", "1H")
    mass = metadata.get("mass", "medium").title()
    
    profiles = metadata.get("attack_profiles", {})
    if profiles and len(profiles) > 1:
        prof_parts = [
            f"{atype.title()}: {p['multiplier']}x ({p['damage_type'].title()})"
            for atype, p in profiles.items()
        ]
        modes_str = " • ".join(prof_parts)
    else:
        atk_types = ", ".join(t.title() for t in metadata.get("attack_types", []))
        modes_str = f"{mult}x ({atk_types})"
    
    lines = [
        f"**{name}** (Tier {tier})",
        f"**Slot:** Weapon • **Archetype:** {arch}",
        f"**Mass:** {mass} • **Handedness:** {hand}"
    ]
    if "projectile_type" in metadata:
        lines.append(f"**Ammo/Projectile:** {metadata['projectile_type'].replace('_', ' ').title()}")
    lines.extend([
        f"**Attack Modes:** {modes_str}",
        f"**Crit Bonus:** +{crit}%"
    ])
    if metadata.get("armor_penetration"):
        ap_pct = int(round(metadata["armor_penetration"] * 100))
        lines.append(f"🎯 **Armor Piercing:** Ignores {ap_pct}% of Target DT")
    if hand == "2H":
        lines.append("⚠️ *Two-Handed: Cannot be used with a shield.*")
    elif hand == "Versatile":
        lines.append("🔄 *Versatile: +15% Damage Multiplier & +4% Crit when two-handed (no shield).*")
    return "\n".join(lines)
