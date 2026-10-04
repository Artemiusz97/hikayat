from __future__ import annotations
import random
from typing import Dict, Any, Optional

from mechanics.combat.items.tags import derive_armor_tags
from mechanics.combat.items.envelope import serialize_item

GLOVE_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "cloth_wraps": {
        "mass": "light", "handedness": "Versatile", "armor_type": "unarmored",
        "base_dt": 0,
        "type_dt": {"physical": 1},
        "base_eva": 2, "base_acc": 1,
        "stat_modifiers": {"eva": 2, "acc": 1, "unarmed_dmg": 2},
        "protection_types": ["physical"],
        "special_traits": ["brawler", "unarmed", "dexterity"]
    },
    "fingerless_gloves": {
        "mass": "light", "handedness": "Versatile", "armor_type": "light",
        "base_dt": 1,
        "type_dt": {"slashing": 2, "physical": 1},
        "base_acc": 2, "base_eva": 1,
        "stat_modifiers": {"acc": 2, "eva": 1, "sleight_of_hand": 3, "lockpicking": 3},
        "protection_types": ["physical"],
        "special_traits": ["dexterity", "stealth", "street"]
    },
    "leather_gloves": {
        "mass": "light", "handedness": "Versatile", "armor_type": "light",
        "base_dt": 2,
        "type_dt": {"slashing": 3, "stabbing": 2, "physical": 2},
        "base_acc": 2, "base_eva": 0,
        "stat_modifiers": {"acc": 2, "crit_bonus": 2},
        "protection_types": ["physical"],
        "special_traits": ["balanced", "grip", "all_weather"]
    },
    "precision_gloves": {
        "mass": "light", "handedness": "Versatile", "armor_type": "light",
        "base_dt": 1,
        "type_dt": {"physical": 1},
        "base_acc": 5, "base_eva": 0,
        "stat_modifiers": {"acc": 5, "crit_bonus": 4, "cast_speed": 1},
        "protection_types": ["physical"],
        "special_traits": ["precision", "ranged", "somatic"]
    },
    "heavy_gauntlets": {
        "mass": "heavy", "handedness": "Versatile", "armor_type": "heavy",
        "base_dt": 6,
        "type_dt": {"physical": 8, "slashing": 8, "blunt": 6, "ballistic": 6},
        "base_acc": -1, "base_eva": -2,
        "stat_modifiers": {"acc": -1, "eva": -2, "unarmed_dmg": 4, "strike_dmg": 4},
        "protection_types": ["physical", "ballistic"],
        "special_traits": ["heavy", "blunt_punch", "defensive"]
    },
    "insulated_gloves": {
        "mass": "medium", "handedness": "Versatile", "armor_type": "medium",
        "base_dt": 2,
        "type_dt": {"shock": 10, "fire": 8, "acid": 10, "energy": 8},
        "base_eva": 0,
        "stat_modifiers": {"hazard_res": 20, "shock_res": 15},
        "protection_types": ["energy", "magical"],
        "special_traits": ["hazmat", "elemental_grounding"]
    },
    "arcane_gloves": {
        "mass": "light", "handedness": "Versatile", "armor_type": "light",
        "base_dt": 1,
        "type_dt": {"magical": 8, "holy": 6, "dark": 6},
        "base_matk": 4, "base_eva": 0,
        "stat_modifiers": {"matk": 4, "spell_crit": 3},
        "protection_types": ["magical"],
        "special_traits": ["magical", "channeling", "focus"]
    },
    "formal_gloves": {
        "mass": "light", "handedness": "Versatile", "armor_type": "unarmored",
        "base_dt": 0,
        "type_dt": {},
        "base_cha": 3, "base_eva": 0,
        "stat_modifiers": {"cha": 3, "etiquette": 2},
        "protection_types": ["social"],
        "special_traits": ["social", "civilian", "formal"]
    }
}

NON_COMBAT_GLOVE_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "cloth_wraps": GLOVE_ARCHETYPES["cloth_wraps"],
    "fingerless_gloves": GLOVE_ARCHETYPES["fingerless_gloves"],
    "leather_gloves": GLOVE_ARCHETYPES["leather_gloves"],
    "precision_gloves": GLOVE_ARCHETYPES["precision_gloves"],
    "formal_gloves": GLOVE_ARCHETYPES["formal_gloves"]
}

for arch, data in GLOVE_ARCHETYPES.items():
    data["tags"] = derive_armor_tags(
        armor_class=data["armor_type"],
        protection_types=data["protection_types"],
        special_traits=data.get("special_traits", [])
    )

SCENARIO_GLOVES_AFFIXES: Dict[str, Dict[str, Any]] = {
    "fantasy": {
        "archetype_names": {
            "cloth_wraps": ["Monk's Hand Wraps", "Brawler's Linen Wraps", "Ascetic Striking Bands"],
            "fingerless_gloves": ["Thief's Fingerless Mitts", "Rogue's Knuckle Guards", "Cutpurse Wraps"],
            "leather_gloves": ["Huntsman's Leather Gloves", "Reinforced Hide Bracers", "Tracker's Gloves"],
            "precision_gloves": ["Archer's Draw-Guards", "Scribe's Silk Bracers", "Falconer's Vambraces"],
            "heavy_gauntlets": ["Steel Plate Gauntlets", "Knight's Clenched Mitts", "Crusader's Iron Cestus"],
            "insulated_gloves": ["Runed Warding Gloves", "Alchemist's Asbestos Mitts", "Salamander-Hide Gloves"],
            "arcane_gloves": ["Silk Spellweaver Gloves", "Mage's Channeling Mitts", "Sorcerer's Weave Grips"],
            "formal_gloves": ["Silk Opera Gloves", "Noble Courtier Gloves", "Velvet Diplomat Mitts"]
        },
        "prefixes_t3": ["Stout", "Hardened", "Apprentice's", "Worn", "Linen", "Honed", "Field"],
        "prefixes_t2": ["Runic", "Gilded", "Mithril", "Moonlit", "Spell-Forged", "Drake-Scale", "Aegis-Woven"],
        "prefixes_t1": ["Sunfire", "Dragon-Forged", "Celestial", "Abyssal-Bound", "God-King's", "Archmage's"],
        "suffixes_t2": ["of Dexterity", "of the Duelist", "of Sparks", "of Iron Grip", "of the Guardian"],
        "suffixes_t1": ["of Eternal Mastery", "of the Dragon-Fist", "of Divine Aegis", "of the Grand Master"]
    },
    "steampunk": {
        "archetype_names": {
            "cloth_wraps": ["Machinist's Linen Tape", "Boiler Hand Wraps", "Stoker's Knuckle Bands"],
            "fingerless_gloves": ["Riveted Fingerless Gloves", "Lock-Picker's Brass Mitts", "Scrapper Grips"],
            "leather_gloves": ["Oilskin Pilot Gloves", "Reinforced Aeronaut Mitts", "Steam-Fitter's Gloves"],
            "precision_gloves": ["Watchmaker's Aether Mitts", "Fine Caliper Finger-Guards", "Engraver's Braces"],
            "heavy_gauntlets": ["Brass-Piston Power Cestus", "Hydraulic Steam Gauntlets", "Iron-Clad Crushing Fists"],
            "insulated_gloves": ["Vulcanized Galvanic Mitts", "Rubberized Arc-Shield Gloves", "Copper-Mesh Mitts"],
            "arcane_gloves": ["Aether-Conductive Thread Gloves", "Voltaic Induction Mitts", "Resonance Grips"],
            "formal_gloves": ["Velvet Victorian Gloves", "Gentleman's Kidskin Gloves", "High-Society Spats-Gloves"]
        },
        "prefixes_t3": ["Brass-Rimmed", "Copper-Wired", "Machinist's", "Steam-Vented", "Rivet-Bound", "Standard"],
        "prefixes_t2": ["Galvanic", "Aether-Tuned", "Pneumatic", "Boiler-Forged", "Voltaic", "Clockwork-Laced"],
        "prefixes_t1": ["Perpetual-Motion", "Grand Victorian", "Tesla's Masterwork", "Dreadnought's", "Aether-Sovereign's"],
        "suffixes_t2": ["of the Piston", "of Valve Exhaust", "of Copper Induction", "of Cogwheel Precision"],
        "suffixes_t1": ["of Endless Pressure", "of the Brass Sovereign", "of Aetheric Synthesis", "of the Iron Colossus"]
    },
    "cyberpunk": {
        "archetype_names": {
            "cloth_wraps": ["Wire-Reinforced Tape", "Street Brawler Wraps", "Carbon-Grip Strips"],
            "fingerless_gloves": ["Street Hacker Fingerless Mesh", "Deck-Jockey Knuckle Mitts", "Tactical Mesh Gloves"],
            "leather_gloves": ["Synthetic-Leather Tactical Gloves", "Carbon-Fiber Grip Gloves", "Enforcer Mitts"],
            "precision_gloves": ["Neural-Link Haptic Gloves", "Smart-Aim Micro-Solenoid Grips", "Cyber-Optic Mitts"],
            "heavy_gauntlets": ["Hydraulic Cyber-Fists", "Titanium Exoskeleton Gauntlets", "Heavy Enforcer Crushing Mitts"],
            "insulated_gloves": ["Hazmat Grounding Mitts", "Anti-EMP Rubberized Gloves", "Thermal-Siphon Mitts"],
            "arcane_gloves": ["Cyberdeck Datajack Gloves", "Overclocked Neural-Interface Mitts", "Grid-Runner Gloves"],
            "formal_gloves": ["Synthetic-Silk Corporate Gloves", "High-End Bio-Skin Mitts", "Executive Dress Gloves"]
        },
        "prefixes_t3": ["Street-Grade", "Mil-Spec", "Reinforced", "Chrome", "Carbon-Weave", "Standard-Issue"],
        "prefixes_t2": ["Overclocked", "Smart-Linked", "High-Frequency", "Sub-Dermal", "Neuro-Wired", "Monofilament"],
        "prefixes_t1": ["Arasaka Prototype", "Black-ICE", "Zero-Day", "Militech Apex", "Ghost-Protocol", "Hyper-Threaded"],
        "suffixes_t2": ["of Target-Acquisition", "of the Netrunner", "of Recoil-Dampening", "of the Phantom"],
        "suffixes_t1": ["of Cyber-Dominance", "of System Override", "of the Apex Syndicate", "of Total Lockdown"]
    },
    "nuclear_post_apocalypse": {
        "archetype_names": {
            "cloth_wraps": ["Dirty Burlap Hand Wraps", "Barbed-Wire Scavenger Wraps", "Ripped Canvas Bands"],
            "fingerless_gloves": ["Scavenger Knuckle Wraps", "Tire-Tread Fingerless Mitts", "Raider Spiked Half-Gloves"],
            "leather_gloves": ["Highwayman Hide Gloves", "Road-Warrior Cowhide Mitts", "Mutant-Leather Gloves"],
            "precision_gloves": ["Sharpshooter Finger Guards", "Varmint-Hunter Scav Gloves", "Sniper Hide Mitts"],
            "heavy_gauntlets": ["Rebar-Studded Iron Claws", "Welded Scrap-Metal Mitts", "Scrap-Plate Power Gauntlets"],
            "insulated_gloves": ["Lead-Lined Asbestos Mitts", "Rad-Shielded Rubber Gloves", "Hazmat Scrap Mitts"],
            "arcane_gloves": ["Glowing Rad-Touched Wraps", "Mutant-Bone Channeled Mitts", "Gamma-Siphon Grips"],
            "formal_gloves": ["Faded Pre-War Dress Gloves", "Moth-Eaten Silk Gloves", "Governor's Old White Gloves"]
        },
        "prefixes_t3": ["Scrap-Metal", "Rusty", "Jury-Rigged", "Weathered", "Makeshift", "Spiked", "Lead-Lined"],
        "prefixes_t2": ["Rad-Hardened", "Bio-Toxic", "Reinforced-Steel", "Wasteland-Master", "Gamma-Tuned", "Spike-Studded"],
        "prefixes_t1": ["Doomsday", "Nuclear-Winter", "Alpha-Mutant", "Apex-Scavenger", "God-Corpse", "Irradiated"],
        "suffixes_t2": ["of the Scavenger", "of Rust & Ruin", "of the Raider", "of the Fallout Bunker"],
        "suffixes_t1": ["of Total Extinction", "of the Wasteland Tyrant", "of the Radioactive Storm", "of Endless Survival"]
    },
    "sci_fi": {
        "archetype_names": {
            "cloth_wraps": ["Nanofiber Compression Wraps", "Zero-G Grip Straps", "Kinetic Striking Strips"],
            "fingerless_gloves": ["Pilot's Deck Fingerless Mitts", "Orbital Mechanic Gloves", "Console-Tech Half-Gloves"],
            "leather_gloves": ["Polymer Flight Gloves", "Composite Space-Trooper Gloves", "Armored Duty Gloves"],
            "precision_gloves": ["Smart-Grip Microsensor Gloves", "Surgical Nanite Grips", "Targeting-Matrix Vambraces"],
            "heavy_gauntlets": ["Kinetic Powered Exo-Gauntlets", "Hydraulic Servo-Fists", "Dreadnought Combat Grips"],
            "insulated_gloves": ["Thermal Dissipation Void Mitts", "Plasma-Shielded Hazmat Gloves", "Cryo-Insulated Mitts"],
            "arcane_gloves": ["Psionic Amplification Grips", "Tachyon Flux Gloves", "Quantum-Phase Emitter Mitts"],
            "formal_gloves": ["Diplomatic Fleet-White Gloves", "High-Officer Dress Gloves", "Velvet Emissary Mitts"]
        },
        "prefixes_t3": ["Titanium", "Composite", "Field", "Standard-Issue", "Carbon-Alloy", "Ceramic"],
        "prefixes_t2": ["Overcharged", "Plasma-Infused", "Hyper-Coil", "Nanite-Lined", "Quantum-Phase", "Cryo-Cooled"],
        "prefixes_t1": ["Supernova", "Singularity", "Antimatter", "Chrono-Phase", "Omni-Core", "Dark-Energy"],
        "suffixes_t2": ["of the Vanguard", "of Vector-Lock", "of Phase-Shift", "of the Orbital Marine"],
        "suffixes_t1": ["of Stellar Superiority", "of the Singularity Core", "of Cosmic Annihilation", "of Absolute Zero"]
    },
    "dark_fantasy": {
        "archetype_names": {
            "cloth_wraps": ["Blood-Soaked Bandages", "Penitent's Thorn Wraps", "Grave-Shrouded Hand Linens"],
            "fingerless_gloves": ["Assassin's Shadowed Half-Gloves", "Blight-Stitched Fingerless Mitts", "Grave-Robber Wraps"],
            "leather_gloves": ["Cursed Leather Gloves", "Executioner's Cowhide Mitts", "Inquisitor's Stiff Gloves"],
            "precision_gloves": ["Bleeding Needle Finger-Guards", "Mortician's Precision Wraps", "Hex-Weaver Bracers"],
            "heavy_gauntlets": ["Defiled Iron Gauntlets", "Torturer's Spiked Iron Fists", "Abyssal Carapace Mitts"],
            "insulated_gloves": ["Asbestos Ash-Warder Gloves", "Corpse-Fat Insulated Mitts", "Pyre-Watcher Gloves"],
            "arcane_gloves": ["Bone-Runed Fingerless Grips", "Hex-Tied Ritual Gloves", "Sanguine Conduit Wraps"],
            "formal_gloves": ["Funeral Silk Gloves", "Aristocrat's Mourning Gloves", "Pale Aristocrat Mitts"]
        },
        "prefixes_t3": ["Blood-Stained", "Weathered", "Grim", "Jagged", "Ashen", "Roughspun", "Grave-Dug"],
        "prefixes_t2": ["Hex-Forged", "Cursed", "Grave-Tainted", "Sanguine", "Blight-Edged", "Bone-Carved", "Shadow-Veiled"],
        "prefixes_t1": ["Eldritch", "Abyssal-Vein", "Death-Lord's", "Cataclysmic", "Blood-Pact", "Marrow-Forged"],
        "suffixes_t2": ["of Torment", "of the Pale Moon", "of the Grave", "of Weeping Shadow", "of Hex-Binding"],
        "suffixes_t1": ["of Eternal Damnation", "of the Abyssal Void", "of Endless Agony", "of the Desolate Throne"]
    },
    "high_school": {
        "archetype_names": {
            "cloth_wraps": ["Athletic Gym Tape", "Boxing Training Wraps", "Martial Arts Hand Straps"],
            "fingerless_gloves": ["Punk Fingerless Knit Gloves", "Bicycle Rider Half-Gloves", "Streetwear Knit Mitts"],
            "leather_gloves": ["Classic Winter Leather Gloves", "Driving Gloves", "Warm Wool-Lined Gloves"],
            "precision_gloves": ["Chemistry Lab Latex Gloves", "Art Club Drawing Half-Gloves", "Surgeon's Clean Grips"],
            "heavy_gauntlets": ["Kendo Protective Kote", "Heavy Hockey Goalie Gloves", "Baseball Catcher's Mitt"],
            "insulated_gloves": ["Heavy Duty Winter Mittens", "Rubber Cleaning Gloves", "Thick Snow Gloves"],
            "arcane_gloves": ["Anime Cosplay Finger-Guards", "Gaming Grip Gloves", "Stage Magician White Mitts"],
            "formal_gloves": ["Marching Band White Gloves", "Student Council Ceremony Gloves", "Formal Uniform Dress Gloves"]
        },
        "prefixes_t3": ["Standard", "Student", "Clean", "Campus", "Everyday", "Casual", "School"],
        "prefixes_t2": ["Varsity", "Tailored", "Customized", "Honors", "Trendy", "Preppy", "Club-Captain's"],
        "prefixes_t1": ["Student Council President's", "Valedictorian's", "Championship", "Festival Champion's", "Campus Legend's"],
        "suffixes_t2": ["of the Study Group", "of Friendship", "of Style", "of Youth", "of the Varsity Team"],
        "suffixes_t1": ["of Everlasting Memories", "of the Championship", "of Pure Dedication", "of the Grand Festival"]
    }
}

def normalize_gloves_scenario(scenario: str) -> str:
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

def generate_random_equipment(
    scenario: str = "fantasy",
    slot: str = "Gloves",
    tier: Optional[int] = None,
    archetype: Optional[str] = None
) -> Dict[str, Any]:
    item_tier = tier if tier in (1, 2, 3) else roll_tier()
    scen_key = normalize_gloves_scenario(scenario)
    
    try:
        from scenario_data import is_non_combat_scenario
        is_non_combat = is_non_combat_scenario(scenario) or scen_key == "high_school"
    except Exception:
        is_non_combat = scen_key == "high_school"
        
    pool_dict = NON_COMBAT_GLOVE_ARCHETYPES if is_non_combat else GLOVE_ARCHETYPES
    
    if archetype and archetype in pool_dict:
        arch = archetype
    elif archetype and archetype in GLOVE_ARCHETYPES and not is_non_combat:
        arch = archetype
    else:
        arch = random.choice(list(pool_dict.keys()))
        
    base_data = GLOVE_ARCHETYPES[arch]
    tier_mult = 1.0 if item_tier == 3 else (1.20 if item_tier == 2 else 1.45)
    
    base_dt = int(round(base_data["base_dt"] * tier_mult))
    type_dt = {k: int(round(v * tier_mult)) for k, v in base_data.get("type_dt", {}).items()}
    
    stat_mods: Dict[str, Any] = {}
    for k, v in base_data.get("stat_modifiers", {}).items():
        if isinstance(v, float):
            stat_mods[k] = round(v * tier_mult, 2)
        elif isinstance(v, int):
            scaled = int(round(v * tier_mult))
            stat_mods[k] = scaled
        else:
            stat_mods[k] = v
            
    if base_dt > 0:
        stat_mods["base_dt"] = base_dt

    scen_affixes = SCENARIO_GLOVES_AFFIXES.get(scen_key, SCENARIO_GLOVES_AFFIXES["fantasy"])
    genre_names = scen_affixes.get("archetype_names", {}).get(arch, [arch.replace("_", " ").title()])
    base_name = random.choice(genre_names)
    
    prefix_pool = scen_affixes.get(f"prefixes_t{item_tier}", ["Fine"])
    suffix_pool = scen_affixes.get(f"suffixes_t{item_tier}", ["of Grip"])
    
    prefix = random.choice(prefix_pool)
    if item_tier == 3:
        name = f"{prefix} {base_name}"
    else:
        suffix = random.choice(suffix_pool)
        name = f"{prefix} {base_name} {suffix}"
        
    metadata = {
        "name": name,
        "tier": item_tier,
        "slot": "Gloves",
        "item_type": "Gloves",
        "archetype": arch,
        "mass": base_data.get("mass", "light"),
        "handedness": base_data.get("handedness", "Versatile"),
        "base_dt": base_dt,
        "type_dt": type_dt,
        "tags": base_data["tags"],
        "stat_modifiers": stat_mods
    }
    
    return {
        "name": name,
        "item_type": "Gloves",
        "slot": "Gloves",
        "effect": serialize_item(metadata),
        "metadata": metadata,
        "slot_cost": 1
    }

def format_equipment_card(metadata: Dict[str, Any]) -> str:
    tier = metadata.get("tier", 3)
    name = metadata.get("name", "Gloves")
    arch = metadata.get("archetype", "gloves").replace("_", " ").title()
    base_dt = metadata.get("base_dt", 0)
    stats = metadata.get("stat_modifiers", {})
    type_dt = metadata.get("type_dt", {})
    
    stat_parts = []
    if base_dt > 0:
        stat_parts.append(f"🛡️ DT +{base_dt}")
    for k, v in stats.items():
        if k in ("base_dt",): continue
        prefix = "+" if isinstance(v, (int, float)) and v > 0 else ""
        label = k.replace("_", " ").title()
        stat_parts.append(f"{label}: {prefix}{v}")
        
    stat_line = " | ".join(stat_parts) if stat_parts else "Standard Grip"
    
    type_dt_str = ", ".join(f"{k.title()}: {v}" for k, v in type_dt.items() if v > 0) or "None"
    
    lines = [
        f"**{name}** (Tier {tier} Handwear — {arch})",
        f"• **Protection**: {stat_line}",
        f"• **Type Resistances**: {type_dt_str}"
    ]
    return "\n".join(lines)
