from __future__ import annotations
import random
from typing import Dict, Any, Optional

from mechanics.combat.items.tags import derive_armor_tags
from mechanics.combat.items.envelope import serialize_item

SHOE_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "light_sneakers": {
        "mass": "light", "handedness": "Versatile", "armor_type": "unarmored",
        "base_dt": 0,
        "type_dt": {"physical": 1},
        "base_eva": 4,
        "stat_modifiers": {"eva": 4, "speed": 2},
        "protection_types": ["physical"],
        "special_traits": ["high_mobility", "light"]
    },
    "sandals": {
        "mass": "light", "handedness": "Versatile", "armor_type": "unarmored",
        "base_dt": 0,
        "type_dt": {},
        "base_eva": 3,
        "stat_modifiers": {"eva": 3, "agility": 2, "heat_res": 10},
        "protection_types": ["physical"],
        "special_traits": ["ultralight", "unarmed"]
    },
    "combat_boots": {
        "mass": "medium", "handedness": "Versatile", "armor_type": "light",
        "base_dt": 3,
        "type_dt": {"slashing": 4, "stabbing": 4, "ballistic": 4, "blunt": 3},
        "base_eva": 1,
        "stat_modifiers": {"eva": 1, "stun_res": 15},
        "protection_types": ["physical", "ballistic"],
        "special_traits": ["balanced", "military", "all_terrain"]
    },
    "heavy_greaves": {
        "mass": "heavy", "handedness": "Versatile", "armor_type": "heavy",
        "base_dt": 7,
        "type_dt": {"physical": 10, "slashing": 10, "blunt": 8, "ballistic": 8},
        "base_eva": -3,
        "stat_modifiers": {"eva": -3, "speed": -1, "stomp_dmg": 4, "knockdown_res": 25},
        "protection_types": ["physical", "ballistic"],
        "special_traits": ["heavy", "stomp", "defensive"]
    },
    "stealth_boots": {
        "mass": "light", "handedness": "Versatile", "armor_type": "light",
        "base_dt": 1,
        "type_dt": {"slashing": 2, "physical": 1},
        "base_eva": 3,
        "stat_modifiers": {"eva": 3, "stealth": 4, "ambush_dmg": 10},
        "protection_types": ["physical"],
        "special_traits": ["stealth", "silent_step", "light"]
    },
    "riding_boots": {
        "mass": "medium", "handedness": "Versatile", "armor_type": "light",
        "base_dt": 2,
        "type_dt": {"slashing": 3, "stabbing": 3, "physical": 2},
        "base_eva": 2,
        "stat_modifiers": {"eva": 2, "acc": 1, "mounted_bonus": 2},
        "protection_types": ["physical"],
        "special_traits": ["versatile", "sturdy", "leather"]
    },
    "hazard_boots": {
        "mass": "medium", "handedness": "Versatile", "armor_type": "medium",
        "base_dt": 2,
        "type_dt": {"acid": 10, "shock": 10, "poison": 10, "fire": 8},
        "base_eva": 0,
        "stat_modifiers": {"hazard_res": 20, "trap_res": 15},
        "protection_types": ["energy", "magical"],
        "special_traits": ["hazmat", "environmental_isolation"]
    },
    "formal_shoes": {
        "mass": "light", "handedness": "Versatile", "armor_type": "unarmored",
        "base_dt": 0,
        "type_dt": {},
        "base_cha": 3, "base_eva": 1,
        "stat_modifiers": {"cha": 3, "luck": 1, "eva": 1},
        "protection_types": ["social"],
        "special_traits": ["social", "civilian", "formal"]
    }
}

NON_COMBAT_SHOE_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "light_sneakers": SHOE_ARCHETYPES["light_sneakers"],
    "sandals": SHOE_ARCHETYPES["sandals"],
    "stealth_boots": SHOE_ARCHETYPES["stealth_boots"],
    "riding_boots": SHOE_ARCHETYPES["riding_boots"],
    "hazard_boots": SHOE_ARCHETYPES["hazard_boots"],
    "formal_shoes": SHOE_ARCHETYPES["formal_shoes"]
}

for arch, data in SHOE_ARCHETYPES.items():
    data["tags"] = derive_armor_tags(
        armor_class=data["armor_type"],
        protection_types=data["protection_types"],
        special_traits=data.get("special_traits", [])
    )

SCENARIO_SHOES_AFFIXES: Dict[str, Dict[str, Any]] = {
    "fantasy": {
        "archetype_names": {
            "light_sneakers": ["Stalker's Soft-Shoes", "Runner's Moccasins", "Woodland Stride Shoes"],
            "sandals": ["Straw Waraji", "Ascetic Leather Sandals", "Monk's Strapped Sandals"],
            "combat_boots": ["Reinforced Leather Boots", "Mercenary's Marching Boots", "Iron-Tipped Boots"],
            "heavy_greaves": ["Plate Sabatons & Greaves", "Crusader's Steel Stompers", "Knight's Greaves"],
            "stealth_boots": ["Shadow-Stitched Soft Moccasins", "Night-Stalker Slippers", "Rogue's Silent Boots"],
            "riding_boots": ["Cuffed Cavalier Boots", "High Huntsman Boots", "Noble Leather Riding Boots"],
            "hazard_boots": ["Salamander-Scale Mud Boots", "Dwarf-Forge Smelter Boots", "Caustic-Tread Boots"],
            "formal_shoes": ["Embroidered Court Slippers", "Noble Velvet Slippers", "Gilded Court Shoes"]
        },
        "prefixes_t3": ["Sturdy", "Hardened", "Field", "Apprentice's", "Worn", "Reinforced", "Traveler's"],
        "prefixes_t2": ["Runic", "Gilded", "Mithril", "Moonlit", "Wind-Walker", "Drake-Hide", "Aegis-Forged"],
        "prefixes_t1": ["Sunfire", "Dragon-Forged", "Celestial", "Storm-God's", "God-King's", "Void-Tread"],
        "suffixes_t2": ["of Swiftness", "of the Agile Wind", "of Sure-Footing", "of the Guardian", "of Silent Step"],
        "suffixes_t1": ["of the Hurricane", "of the Astral Traveler", "of Eternal Stride", "of the Unshakable Titan"]
    },
    "steampunk": {
        "archetype_names": {
            "light_sneakers": ["Deckhand Canvas Creepers", "Machinist's Runner Shoes", "Aeronaut Creepers"],
            "sandals": ["Riveted Leather Sandals", "Boiler-Room Strapped Sandals", "Deck Sliders"],
            "combat_boots": ["Iron-Cleated Trench Boots", "Steel-Toe Work Boots", "Aeronaut Flight Boots"],
            "heavy_greaves": ["Pneumatic Steam-Stompers", "Brass-Piston Iron Greaves", "Hydraulic Sabatons"],
            "stealth_boots": ["Felt-Padded Nightstalker Boots", "Muffled Velvet Creepers", "Infiltrator Ankle Boots"],
            "riding_boots": ["Spurred Highwayman Boots", "Victorian Coachman Boots", "Long Leather Rider Boots"],
            "hazard_boots": ["Vulcanized Caustic Boots", "Acid-Proof Rubber Treads", "Boiler Hazmat Boots"],
            "formal_shoes": ["Polished Spats & Oxford Brogues", "Victorian Patent Oxfords", "Gilded Gentleman Shoes"]
        },
        "prefixes_t3": ["Brass-Rimmed", "Copper-Cleated", "Machinist's", "Steam-Vented", "Rivet-Bound", "Standard"],
        "prefixes_t2": ["Galvanic", "Aether-Tuned", "Pneumatic", "Boiler-Forged", "Voltaic", "Clockwork-Sprung"],
        "prefixes_t1": ["Perpetual-Motion", "Grand Victorian", "Tesla's Masterwork", "Dreadnought's", "Aether-Sovereign's"],
        "suffixes_t2": ["of the Piston", "of Steam Momentum", "of Clockwork Speed", "of Valve Exhaust"],
        "suffixes_t1": ["of Endless Propulsion", "of the Brass Behemoth", "of Aetheric Levitation", "of the Iron Leviathan"]
    },
    "cyberpunk": {
        "archetype_names": {
            "light_sneakers": ["Mag-Pulse High-Tops", "Street Runner Sneakers", "Neon Kinetic Kicks"],
            "sandals": ["Composite Strap Slides", "Cyber-Deck Sliders", "Futuristic Street Sandals"],
            "combat_boots": ["Armored Urban Combat Boots", "Carbon-Reinforced Enforcer Boots", "Mil-Spec Treads"],
            "heavy_greaves": ["Titanium Exoskeleton Shin-Guards", "Hydraulic Stomp Greaves", "Heavy Cyber-Leg Treads"],
            "stealth_boots": ["Sound-Dampening Nanotech Soles", "Ghost-Step Cyber-Slippers", "Infiltration Stealth Kicks"],
            "riding_boots": ["Biker Carbon Riding Boots", "Highway Patrol Leather Treads", "Cyber-Drifter Boots"],
            "hazard_boots": ["Anti-Corrosive Hazmat Treads", "Thermal Grounding Boots", "Bio-Resistant Boots"],
            "formal_shoes": ["Neon-Lined Corporate Loafers", "High-Gloss Executive Oxfords", "Cyber-Silk Dress Heels"]
        },
        "prefixes_t3": ["Street-Grade", "Mil-Spec", "Carbon-Weave", "Chrome", "Reinforced", "Standard-Issue"],
        "prefixes_t2": ["Overclocked", "Smart-Linked", "High-Frequency", "Sub-Dermal", "Nanite-Laced", "Kinetic-Spring"],
        "prefixes_t1": ["Arasaka Prototype", "Black-ICE", "Zero-Day", "Militech Apex", "Ghost-Protocol", "Hyper-Threaded"],
        "suffixes_t2": ["of the Phantom", "of Traction-Lock", "of the Netrunner", "of Recoil-Absorption"],
        "suffixes_t1": ["of Cyber-Dominance", "of Flawless Momentum", "of the Apex Syndicate", "of Total Evasion"]
    },
    "nuclear_post_apocalypse": {
        "archetype_names": {
            "light_sneakers": ["Treadless Scav Runner Shoes", "Worn Scav Sneakers", "Duct-Taped Running Shoes"],
            "sandals": ["Tire-Rubber Strapped Sandals", "Scrap-Leather Footwraps", "Wasteland Sand-Sliders"],
            "combat_boots": ["Tire-Tread Trench Boots", "Steel-Toe Highway Boots", "Raider Combat Treads"],
            "heavy_greaves": ["Welded Scrap-Metal Greaves", "Rebar-Armored Iron Boots", "Scrap-Plate Leg Guards"],
            "stealth_boots": ["Muffled Burlap Footwraps", "Silent Scav Hide Slippers", "Padded Rag Boots"],
            "riding_boots": ["Duster Cowhide Boots", "Wasteland Drifter Boots", "Road-Warrior Riding Leather"],
            "hazard_boots": ["Lead-Lined Mud Boots", "Rad-Shielded Hazmat Treads", "Rubber Fallout Boots"],
            "formal_shoes": ["Scuffed Pre-War Dress Oxfords", "Dusty Corporate Loafers", "Old World Shiny Shoes"]
        },
        "prefixes_t3": ["Scrap-Metal", "Rusty", "Jury-Rigged", "Weathered", "Makeshift", "Spiked", "Lead-Lined"],
        "prefixes_t2": ["Rad-Hardened", "Bio-Toxic", "Reinforced-Steel", "Wasteland-Master", "Gamma-Tuned", "Spike-Studded"],
        "prefixes_t1": ["Doomsday", "Nuclear-Winter", "Alpha-Mutant", "Apex-Scavenger", "God-Corpse", "Irradiated"],
        "suffixes_t2": ["of the Scavenger", "of Rust & Ruin", "of the Raider", "of the Fallout Shelter"],
        "suffixes_t1": ["of Total Extinction", "of the Wasteland Nomad", "of the Radioactive Storm", "of Endless Survival"]
    },
    "sci_fi": {
        "archetype_names": {
            "light_sneakers": ["Zero-G Kinetic Runners", "Mag-Grip Space Sneakers", "Vector Kinetic Kicks"],
            "sandals": ["Thermal Deck Slides", "Zero-G Strapped Slippers", "Hydro-Polymer Slides"],
            "combat_boots": ["Grav-Anchor Jump Boots", "Composite Space-Marine Treads", "Tactical Deck Boots"],
            "heavy_greaves": ["Powered Kinetic Greaves", "Exoskeleton Heavy Leg Rigs", "Titan Dreadnought Sabatons"],
            "stealth_boots": ["Optical-Camouflage Soft Soles", "Nanite Acoustic-Absorbers", "Infiltration Void Boots"],
            "riding_boots": ["Pilot's High Flight Boots", "Orbital Patrol Leather Treads", "Exo-Vehicle Boots"],
            "hazard_boots": ["Mag-Lock Void Boots", "Thermal Radiation Stompers", "Cryo-Insulated Deck Boots"],
            "formal_shoes": ["Diplomatic Fleet Dress Shoes", "High-Gloss Officer Brogues", "Nano-Fabric Loafers"]
        },
        "prefixes_t3": ["Titanium", "Composite", "Field", "Standard-Issue", "Carbon-Alloy", "Ceramic"],
        "prefixes_t2": ["Overcharged", "Plasma-Infused", "Hyper-Coil", "Nanite-Lined", "Quantum-Phase", "Cryo-Cooled"],
        "prefixes_t1": ["Supernova", "Singularity", "Antimatter", "Chrono-Phase", "Omni-Core", "Dark-Energy"],
        "suffixes_t2": ["of the Vanguard", "of Vector Acceleration", "of Phase-Shift", "of the Orbital Marine"],
        "suffixes_t1": ["of Stellar Superiority", "of the Singularity Core", "of Warp-Drive Momentum", "of Absolute Zero"]
    },
    "dark_fantasy": {
        "archetype_names": {
            "light_sneakers": ["Grave-Stalker Soft Slippers", "Prowler Soft-Shoes", "Carrion Soft-Moccasins"],
            "sandals": ["Penitent's Thorn Sandals", "Pilgrim Strapped Linens", "Ash-Walker Sandals"],
            "combat_boots": ["Inquisitor Knee-High Boots", "Iron-Plated Marsh Boots", "Torturer's Stiff Boots"],
            "heavy_greaves": ["Defiled Tomb Greaves", "Grave-Knight Steel Sabatons", "Abyssal Bone Sabatons"],
            "stealth_boots": ["Ghost-Leather Slippers", "Shadow-Stitched Assassin Boots", "Wraith-Sole Moccasins"],
            "riding_boots": ["Black-Rider Knee Boots", "Inquisitor Riding Leather", "Executioner's Boots"],
            "hazard_boots": ["Blight-Warder Peat Boots", "Corpse-Mud Stompers", "Mire-Crawl Boots"],
            "formal_shoes": ["Aristocrat's Mourning Brogues", "Pale Courtier Slippers", "Velvet Funeral Shoes"]
        },
        "prefixes_t3": ["Blood-Stained", "Weathered", "Grim", "Jagged", "Ashen", "Roughspun", "Grave-Dug"],
        "prefixes_t2": ["Hex-Forged", "Cursed", "Grave-Tainted", "Sanguine", "Blight-Edged", "Bone-Carved", "Shadow-Veiled"],
        "prefixes_t1": ["Eldritch", "Abyssal-Vein", "Death-Lord's", "Cataclysmic", "Blood-Pact", "Marrow-Forged"],
        "suffixes_t2": ["of Torment", "of the Pale Moon", "of the Grave", "of Weeping Shadow", "of the Hex-Step"],
        "suffixes_t1": ["of Eternal Damnation", "of the Abyssal Void", "of Endless Agony", "of the Desolate Throne"]
    },
    "high_school": {
        "archetype_names": {
            "light_sneakers": ["Classic Canvas Sneakers", "Varsity Track Running Shoes", "Retro Low-Tops"],
            "sandals": ["Summer Beach Slides", "Pool Shower Sandals", "Casual Cork Sandals"],
            "combat_boots": ["Doc Marten Style Boots", "Heavy Combat-Style Ankle Boots", "Hiking Boots"],
            "heavy_greaves": ["Kendo Protective Shin-Guards", "Hockey Goalie Leg Pads", "Catcher's Shin Protectors"],
            "stealth_boots": ["Indoor Felt Slippers", "Soft Hallway Moccasins", "Silent Rubber-Soled Kicks"],
            "riding_boots": ["Equestrian Riding Boots", "Fashionable Knee-High Leather Boots", "Rain Riding Boots"],
            "hazard_boots": ["Yellow Rubber Rain Boots", "Heavy Gardening Mud Boots", "Industrial Shop Work Boots"],
            "formal_shoes": ["Polished School Loafers", "Formal Uniform Oxford Shoes", "Black Patent Brogues"]
        },
        "prefixes_t3": ["Standard", "Student", "Clean", "Campus", "Everyday", "Casual", "School"],
        "prefixes_t2": ["Varsity", "Tailored", "Customized", "Honors", "Trendy", "Preppy", "Club-Captain's"],
        "prefixes_t1": ["Student Council President's", "Valedictorian's", "Championship", "Festival Champion's", "Campus Legend's"],
        "suffixes_t2": ["of the Study Group", "of Friendship", "of Style", "of Youth", "of the Track Team"],
        "suffixes_t1": ["of Everlasting Memories", "of the Championship", "of Pure Dedication", "of the Grand Festival"]
    }
}

def normalize_shoes_scenario(scenario: str) -> str:
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
    slot: str = "Shoes",
    tier: Optional[int] = None,
    archetype: Optional[str] = None
) -> Dict[str, Any]:
    item_tier = tier if tier in (1, 2, 3) else roll_tier()
    scen_key = normalize_shoes_scenario(scenario)
    
    try:
        from scenario_data import is_non_combat_scenario
        is_non_combat = is_non_combat_scenario(scenario) or scen_key == "high_school"
    except Exception:
        is_non_combat = scen_key == "high_school"
        
    pool_dict = NON_COMBAT_SHOE_ARCHETYPES if is_non_combat else SHOE_ARCHETYPES
    
    if archetype and archetype in pool_dict:
        arch = archetype
    elif archetype and archetype in SHOE_ARCHETYPES and not is_non_combat:
        arch = archetype
    else:
        arch = random.choice(list(pool_dict.keys()))
        
    base_data = SHOE_ARCHETYPES[arch]
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

    scen_affixes = SCENARIO_SHOES_AFFIXES.get(scen_key, SCENARIO_SHOES_AFFIXES["fantasy"])
    genre_names = scen_affixes.get("archetype_names", {}).get(arch, [arch.replace("_", " ").title()])
    base_name = random.choice(genre_names)
    
    prefix_pool = scen_affixes.get(f"prefixes_t{item_tier}", ["Fine"])
    suffix_pool = scen_affixes.get(f"suffixes_t{item_tier}", ["of Stride"])
    
    prefix = random.choice(prefix_pool)
    if item_tier == 3:
        name = f"{prefix} {base_name}"
    else:
        suffix = random.choice(suffix_pool)
        name = f"{prefix} {base_name} {suffix}"
        
    metadata = {
        "name": name,
        "tier": item_tier,
        "slot": "Shoes",
        "item_type": "Shoes",
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
        "item_type": "Shoes",
        "slot": "Shoes",
        "effect": serialize_item(metadata),
        "metadata": metadata,
        "slot_cost": 1
    }

def format_equipment_card(metadata: Dict[str, Any]) -> str:
    tier = metadata.get("tier", 3)
    name = metadata.get("name", "Shoes")
    arch = metadata.get("archetype", "shoes").replace("_", " ").title()
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
        
    stat_line = " | ".join(stat_parts) if stat_parts else "Standard Mobility"
    
    type_dt_str = ", ".join(f"{k.title()}: {v}" for k, v in type_dt.items() if v > 0) or "None"
    
    lines = [
        f"**{name}** (Tier {tier} Footwear — {arch})",
        f"• **Mobility & Protection**: {stat_line}",
        f"• **Type Resistances**: {type_dt_str}"
    ]
    return "\n".join(lines)
