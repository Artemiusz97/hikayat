from __future__ import annotations
import random
from typing import Dict, Any, Optional

from mechanics.combat.items.tags import derive_armor_tags
from mechanics.combat.items.envelope import serialize_item

SHIELD_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "buckler": {
        "mass": "light", "handedness": "1H", "block_chance": 15,
        "base_dt": 4, "dt_contribution": 4,
        "type_dt": {"slashing": 6, "arrow": 4, "pistol_round": 2},
        "base_eva": 4
    },
    "heater_shield": {
        "mass": "medium", "handedness": "1H", "block_chance": 25,
        "base_dt": 8, "dt_contribution": 8,
        "type_dt": {"slashing": 10, "stabbing": 8, "arrow": 8, "bolt": 6, "pistol_round": 6},
        "base_eva": 0
    },
    "tower_shield": {
        "mass": "heavy", "handedness": "1H", "block_chance": 40,
        "base_dt": 14, "dt_contribution": 14,
        "type_dt": {"physical": 16, "ballistic": 18, "rifle_round": 16, "pistol_round": 18, "high_caliber_round": 8, "scatter_shot": 16, "arrow": 16, "bolt": 14},
        "base_eva": -6
    },
    "riot_shield": {
        "mass": "medium", "handedness": "1H", "block_chance": 30,
        "base_dt": 10, "dt_contribution": 10,
        "type_dt": {"ballistic": 14, "scatter_shot": 16, "blunt": 14, "pistol_round": 14, "slashing": 10},
        "base_eva": -2
    },
    "energy_shield": {
        "mass": "light", "handedness": "1H", "block_chance": 35,
        "base_dt": 6, "dt_contribution": 6,
        "type_dt": {"energy": 18, "energy_cell": 18, "magical": 14, "fire": 12, "shock": 12, "plasma": 14},
        "base_eva": 2
    }
}

NON_COMBAT_SHIELD_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "school_satchel": {
        "mass": "light", "handedness": "1H", "block_chance": 0,
        "base_dt": 0, "dt_contribution": 0, "type_dt": {},
        "base_eva": 1, "stat_modifiers": {"cha": 1, "bag_capacity": 5}
    },
    "canvas_backpack": {
        "mass": "light", "handedness": "1H", "block_chance": 0,
        "base_dt": 0, "dt_contribution": 0, "type_dt": {},
        "base_eva": 0, "stat_modifiers": {"cha": 1, "bag_capacity": 8}
    },
    "tote_bag": {
        "mass": "light", "handedness": "1H", "block_chance": 0,
        "base_dt": 0, "dt_contribution": 0, "type_dt": {},
        "base_eva": 1, "stat_modifiers": {"cha": 2}
    },
    "binder_folder": {
        "mass": "light", "handedness": "1H", "block_chance": 0,
        "base_dt": 0, "dt_contribution": 0, "type_dt": {},
        "base_eva": 0, "stat_modifiers": {"int": 1, "study": 2}
    }
}

for arch, data in SHIELD_ARCHETYPES.items():
    data["tags"] = derive_armor_tags(
        armor_class="shield",
        protection_types=["energy", "magical"] if "energy" in arch else ["physical", "ballistic"]
    )

for arch, data in NON_COMBAT_SHIELD_ARCHETYPES.items():
    data["tags"] = derive_armor_tags(
        armor_class="civilian_gear",
        protection_types=["social"],
        special_traits=["bag", "storage", "civilian"]
    )

SCENARIO_SHIELD_AFFIXES: Dict[str, Dict[str, Any]] = {
    "fantasy": {
        "archetype_names": {
            "buckler": ["Duelist's Iron Buckler", "Target Shield", "Round Parry Shield"],
            "heater_shield": ["Knight's Crested Heater", "Armored Heraldic Shield", "Crusader's Heater"],
            "tower_shield": ["Towering Aegis Pavise", "Citadel Wall Shield", "Iron Bastion Shield"],
            "riot_shield": ["Reinforced Iron Pavise", "Infantry Wall Guard", "Phalanx Shield"],
            "energy_shield": ["Runic Arcane Barrier", "Sun-Blessed Aegis", "Prismatic Shield"]
        },
        "prefixes_t3": ["Iron", "Steel", "Stout", "Hardened", "Honed", "Apprentice's", "Sturdy"],
        "prefixes_t2": ["Runic", "Gilded", "Mithril", "Moonlit", "Spell-Forged", "Aegis-Bound"],
        "prefixes_t1": ["Sunfire", "Dragon-Forged", "Celestial", "Abyssal-Bound", "God-King's"],
        "suffixes_t2": ["of Warding", "of the Guardian", "of Deflection", "of Fortitude", "of the Bastion"],
        "suffixes_t1": ["of the Dragon Slayer", "of Divine Aegis", "of the Unbroken Fortress", "of Absolute Protection"]
    },
    "steampunk": {
        "archetype_names": {
            "buckler": ["Brass-Rimmed Parrying Buckler", "Clockwork Deflector Disc", "Rivet-Bound Roundel"],
            "heater_shield": ["Boiler-Plate Heater Shield", "Riveted Brass Pavise", "Aeronaut's Deflection Shield"],
            "tower_shield": ["Steam-Vented Bulkhead Shield", "Hydraulic Pressure Barricade", "Ironclad Siege Mantlet"],
            "riot_shield": ["Copper-Reinforced Trench Barrier", "Machinist's Blast Pavise", "Stoker's Iron Shutter"],
            "energy_shield": ["Galvanic Arc-Deflector", "Voltaic Induction Barrier", "Aether-Charged Repulsor"]
        },
        "prefixes_t3": ["Brass-Rimmed", "Copper-Wired", "Machinist's", "Steam-Vented", "Rivet-Bound", "Standard"],
        "prefixes_t2": ["Galvanic", "Aether-Tuned", "Pneumatic", "Boiler-Forged", "Voltaic", "Clockwork-Laced"],
        "prefixes_t1": ["Perpetual-Motion", "Grand Victorian", "Tesla's Masterwork", "Dreadnought's", "Aether-Sovereign's"],
        "suffixes_t2": ["of the Piston", "of Steam Exhaust", "of Copper Induction", "of Cogwheel Deflection"],
        "suffixes_t1": ["of Endless Pressure", "of the Brass Sovereign", "of Aetheric Synthesis", "of the Iron Leviathan"]
    },
    "cyberpunk": {
        "archetype_names": {
            "buckler": ["Tactical Wrist-Mounted Buckler", "Micro-Barrier Kinetic Disc", "Chrome Parry Disc"],
            "heater_shield": ["Ballistic Polymer Shield", "Enforcer Tactical Wedge", "Armored Wedge Barrier"],
            "tower_shield": ["Heavy SWAT Mobile Barricade", "Titanium Enforcer Wall", "Breaching Mantlet"],
            "riot_shield": ["Polycarbonate Tactical Riot Shield", "Mil-Spec Blast Shield", "Crowd-Control Barrier"],
            "energy_shield": ["Hard-Light Holographic Aegis", "Overclocked Kinetic Barrier", "Nano-Grid Deflector"]
        },
        "prefixes_t3": ["Street-Grade", "Mil-Spec", "Carbon-Weave", "Chrome", "Reinforced", "Standard-Issue"],
        "prefixes_t2": ["Overclocked", "Smart-Linked", "High-Frequency", "Sub-Dermal", "Nanite-Laced", "Thermal-Chambered"],
        "prefixes_t1": ["Arasaka Prototype", "Black-ICE", "Zero-Day", "Militech Apex", "Ghost-Protocol", "Hyper-Threaded"],
        "suffixes_t2": ["of Kinetic Dampening", "of Recoil-Absorption", "of the Netrunner", "of Target-Lock"],
        "suffixes_t1": ["of Cyber-Dominance", "of Impenetrable ICE", "of the Apex Syndicate", "of Total Defense"]
    },
    "nuclear_post_apocalypse": {
        "archetype_names": {
            "buckler": ["Hubcap Parrying Buckler", "Saucepan Lid Buckler", "Spiked Trash-Can Lid"],
            "heater_shield": ["Welded Stop-Sign Shield", "Car-Hood Angled Shield", "Scrap-Metal Wedge"],
            "tower_shield": ["Welded Car-Door Tower Shield", "Corrugated Tin Barricade", "Heavy Oil-Drum Mantlet"],
            "riot_shield": ["Reinforced Highway Sign Shield", "Barbed-Wire Riot Board", "Tire-Tread Fragment Shield"],
            "energy_shield": ["Sparking Rad-Siphon Barrier", "Mutant-Core Glowing Aegis", "Tesla Scrap-Coil Field"]
        },
        "prefixes_t3": ["Scrap-Metal", "Rusty", "Jury-Rigged", "Weathered", "Makeshift", "Spiked", "Lead-Lined"],
        "prefixes_t2": ["Rad-Hardened", "Bio-Toxic", "Reinforced-Steel", "Wasteland-Master", "Gamma-Tuned", "Spike-Studded"],
        "prefixes_t1": ["Doomsday", "Nuclear-Winter", "Alpha-Mutant", "Apex-Scavenger", "God-Corpse", "Irradiated"],
        "suffixes_t2": ["of the Scavenger", "of Rust & Ruin", "of the Raider", "of the Fallout Shelter"],
        "suffixes_t1": ["of Total Extinction", "of the Wasteland Tyrant", "of the Radioactive Storm", "of Endless Survival"]
    },
    "sci_fi": {
        "archetype_names": {
            "buckler": ["Mag-Pulse Kinetic Buckler", "Sub-Compact Deflector Disc", "Nano-Alloy Wrist Disc"],
            "heater_shield": ["Composite Tactical Aegis", "Vanguard Kinetic Wedge", "Polymer Fleet Shield"],
            "tower_shield": ["Deployable Heavy Drop-Barrier", "Titanium Dreadnought Mantlet", "Orbital Marine Wall"],
            "riot_shield": ["Transparent Nanite Riot Shield", "Plasma Dispersion Guard", "Colony Security Barrier"],
            "energy_shield": ["Plasma-Field Deflector", "Quantum-Phase Barrier Shield", "Tachyon Repulsor Aegis"]
        },
        "prefixes_t3": ["Titanium", "Composite", "Field", "Standard-Issue", "Carbon-Alloy", "Ceramic"],
        "prefixes_t2": ["Overcharged", "Plasma-Infused", "Hyper-Coil", "Nanite-Lined", "Quantum-Phase", "Cryo-Cooled"],
        "prefixes_t1": ["Supernova", "Singularity", "Antimatter", "Chrono-Phase", "Omni-Core", "Dark-Energy"],
        "suffixes_t2": ["of the Vanguard", "of Phase-Shift", "of the Orbital Marine", "of Deflection"],
        "suffixes_t1": ["of Stellar Superiority", "of the Singularity Core", "of Cosmic Fortification", "of Absolute Zero"]
    },
    "dark_fantasy": {
        "archetype_names": {
            "buckler": ["Skull-Faced Iron Buckler", "Grave-Robber's Target", "Bloodied Round Shield"],
            "heater_shield": ["Cursed Black-Iron Heater", "Defiled Tombstone Shield", "Inquisitor's Iron Cross Shield"],
            "tower_shield": ["Crypt-Door Tower Shield", "Abyssal Great-Pavise", "Bone-Lined Sanguine Wall"],
            "riot_shield": ["Torturer's Spiked Iron Shutter", "Blighted Wooden Pavise", "Blackened Executioner Guard"],
            "energy_shield": ["Eldritch Hex-Ward Barrier", "Soul-Drain Spectral Aegis", "Abyssal Shroud Deflector"]
        },
        "prefixes_t3": ["Blood-Stained", "Weathered", "Grim", "Jagged", "Ashen", "Roughspun", "Grave-Dug"],
        "prefixes_t2": ["Hex-Forged", "Cursed", "Grave-Tainted", "Sanguine", "Blight-Edged", "Bone-Carved", "Shadow-Veiled"],
        "prefixes_t1": ["Eldritch", "Abyssal-Vein", "Death-Lord's", "Cataclysmic", "Blood-Pact", "Marrow-Forged"],
        "suffixes_t2": ["of Torment", "of the Pale Moon", "of the Grave", "of Weeping Shadow", "of Hex-Binding"],
        "suffixes_t1": ["of Eternal Damnation", "of the Abyssal Void", "of Endless Agony", "of the Desolate Bastion"]
    },
    "high_school": {
        "archetype_names": {
            "school_satchel": ["Leather School Satchel", "Classic Briefcase Satchel", "Vintage Student Satchel"],
            "canvas_backpack": ["Canvas Student Backpack", "Varsity Daypack", "Reinforced Bookbag"],
            "tote_bag": ["Cotton Library Tote Bag", "Pastel Shoulder Tote", "Art Club Canvas Tote"],
            "binder_folder": ["Hardcover Ring Binder", "Student Council File Portfolio", "Organized Study Binder"]
        },
        "prefixes_t3": ["Standard", "Student", "Clean", "Campus", "Everyday", "Casual", "School"],
        "prefixes_t2": ["Varsity", "Tailored", "Customized", "Honors", "Trendy", "Preppy", "Club-Captain's"],
        "prefixes_t1": ["Student Council President's", "Valedictorian's", "Championship", "Festival Champion's", "Campus Legend's"],
        "suffixes_t2": ["of the Study Group", "of Friendship", "of Style", "of Youth", "of the Honor Roll"],
        "suffixes_t1": ["of Everlasting Memories", "of the Grand Festival", "of Pure Dedication", "of the Campus Legend"]
    }
}

def normalize_shield_scenario(scenario: str) -> str:
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

def generate_random_equipment(scenario: str = "fantasy", slot: str = "Shield", tier: Optional[int] = None, archetype: Optional[str] = None) -> Dict[str, Any]:
    item_tier = tier if tier in (1, 2, 3) else roll_tier()
    scen_key = normalize_shield_scenario(scenario)
    
    try:
        from scenario_data import is_non_combat_scenario
        is_non_combat = is_non_combat_scenario(scenario) or scen_key == "high_school"
    except Exception:
        is_non_combat = scen_key == "high_school"
        
    pool_dict = NON_COMBAT_SHIELD_ARCHETYPES if is_non_combat else SHIELD_ARCHETYPES
    
    if archetype and archetype in pool_dict:
        arch = archetype
    elif archetype and archetype in SHIELD_ARCHETYPES and not is_non_combat:
        arch = archetype
    else:
        arch = random.choice(list(pool_dict.keys()))
        
    base_data = pool_dict[arch]
    tier_mult = 1.0 if item_tier == 3 else (1.20 if item_tier == 2 else 1.45)
    
    base_dt = int(round(base_data.get("base_dt", 0) * tier_mult))
    type_dt = {k: int(round(v * tier_mult)) for k, v in base_data.get("type_dt", {}).items()}
    block_chance = base_data.get("block_chance", 0)
    if block_chance > 0:
        block_chance += (5 if item_tier == 2 else (10 if item_tier == 1 else 0))

    scen_affixes = SCENARIO_SHIELD_AFFIXES.get(scen_key, SCENARIO_SHIELD_AFFIXES["fantasy"])
    genre_names = scen_affixes.get("archetype_names", {}).get(arch, [arch.replace("_", " ").title()])
    base_name = random.choice(genre_names)
    
    prefix_pool = scen_affixes.get(f"prefixes_t{item_tier}", ["Stout"])
    suffix_pool = scen_affixes.get(f"suffixes_t{item_tier}", ["of Defense"])
    
    prefix = random.choice(prefix_pool)
    if item_tier == 3:
        name = f"{prefix} {base_name}"
    else:
        suffix = random.choice(suffix_pool)
        name = f"{prefix} {base_name} {suffix}"
        
    stat_mods: Dict[str, Any] = {}
    for k, v in base_data.get("stat_modifiers", {}).items():
        if isinstance(v, (int, float)):
            stat_mods[k] = round(v * tier_mult, 2) if isinstance(v, float) else int(round(v * tier_mult))
        else:
            stat_mods[k] = v
    if base_dt > 0:
        stat_mods["base_dt"] = base_dt
    if "base_eva" in base_data and "eva" not in stat_mods:
        stat_mods["eva"] = base_data["base_eva"]
        
    metadata = {
        "name": name,
        "tier": item_tier,
        "slot": "Shield",
        "item_type": "Shield",
        "archetype": arch,
        "mass": base_data["mass"],
        "handedness": base_data["handedness"],
        "block_chance": block_chance,
        "base_dt": base_dt,
        "dt_contribution": base_dt,
        "base_eva": base_data.get("base_eva", 0),
        "type_dt": type_dt,
        "tags": base_data["tags"],
        "stat_modifiers": stat_mods
    }
    
    return {
        "name": name,
        "item_type": "Shield",
        "slot": "Shield",
        "effect": serialize_item(metadata),
        "metadata": metadata,
        "slot_cost": 1
    }

def format_equipment_card(metadata: Dict[str, Any]) -> str:
    tier = metadata.get("tier", 3)
    name = metadata.get("name", "Shield")
    arch = metadata.get("archetype", "shield").replace("_", " ").title()
    base_dt = metadata.get("base_dt", metadata.get("dt_contribution", 0))
    block = metadata.get("block_chance", 0)
    type_dt = metadata.get("type_dt", {})
    base_eva = metadata.get("base_eva", metadata.get("stat_modifiers", {}).get("eva", 0))
    
    type_dt_str = ", ".join(f"{k.title()}: {v}" for k, v in type_dt.items()) or "None"
    eva_str = f" • **EVA Mod:** {base_eva:+d}%" if base_eva != 0 else ""
    
    lines = [
        f"**{name}** (Tier {tier})",
        f"**Slot:** Shield • **Archetype:** {arch}{eva_str}",
        f"**Block Chance:** {block}% • **Base DT:** {base_dt}",
        f"**Type DT:** {type_dt_str}"
    ]
    return "\n".join(lines)
