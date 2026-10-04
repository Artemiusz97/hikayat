from __future__ import annotations
import random
from typing import Dict, Any, Optional

from mechanics.combat.items.tags import derive_armor_tags
from mechanics.combat.items.envelope import serialize_item

HEADWEAR_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "cloth_hood": {
        "mass": "light", "handedness": "Versatile", "armor_type": "light",
        "base_dt": 1,
        "type_dt": {"slashing": 2, "physical": 1},
        "base_eva": 2,
        "stat_modifiers": {"eva": 2, "stealth": 3, "ambush_dmg": 5},
        "protection_types": ["physical"],
        "special_traits": ["stealth", "shadow", "light"]
    },
    "cap": {
        "mass": "light", "handedness": "Versatile", "armor_type": "unarmored",
        "base_dt": 0,
        "type_dt": {"physical": 1},
        "base_acc": 2,
        "stat_modifiers": {"per": 1, "acc": 2, "cha": 1},
        "protection_types": ["physical"],
        "special_traits": ["light", "scout", "keen_eye"]
    },
    "open_helm": {
        "mass": "medium", "handedness": "Versatile", "armor_type": "light",
        "base_dt": 3,
        "type_dt": {"slashing": 4, "stabbing": 4, "blunt": 3, "ballistic": 3},
        "base_eva": 0,
        "stat_modifiers": {"stun_res": 10},
        "protection_types": ["physical", "ballistic"],
        "special_traits": ["balanced", "military", "open_face"]
    },
    "full_greathelm": {
        "mass": "heavy", "handedness": "Versatile", "armor_type": "heavy",
        "base_dt": 7,
        "type_dt": {"physical": 10, "ballistic": 8, "slashing": 10, "blunt": 8},
        "base_eva": -2,
        "stat_modifiers": {"eva": -2, "per": -1, "stun_res": 25, "knockdown_res": 15},
        "protection_types": ["physical", "ballistic"],
        "special_traits": ["heavy", "enclosed", "defensive", "tank"]
    },
    "tech_visor": {
        "mass": "light", "handedness": "Versatile", "armor_type": "light",
        "base_dt": 1,
        "type_dt": {"energy": 4, "energy_cell": 4},
        "base_acc": 5,
        "stat_modifiers": {"acc": 5, "per": 2, "crit_bonus": 4, "blind_immune": 1},
        "protection_types": ["energy", "physical"],
        "special_traits": ["precision", "optics", "hud", "targeting"]
    },
    "gas_mask": {
        "mass": "medium", "handedness": "Versatile", "armor_type": "medium",
        "base_dt": 2,
        "type_dt": {"poison": 12, "acid": 10, "hazard": 12},
        "base_eva": 0,
        "stat_modifiers": {"gas_immune": 1, "hazard_res": 20, "poison_res": 15},
        "protection_types": ["energy", "magical"],
        "special_traits": ["hazmat", "respirator", "environmental_isolation"]
    },
    "circlet": {
        "mass": "light", "handedness": "Versatile", "armor_type": "light",
        "base_dt": 1,
        "type_dt": {"magical": 8, "holy": 6, "dark": 6},
        "base_matk": 4,
        "stat_modifiers": {"matk": 4, "int": 1, "spell_crit": 3, "mana_regen": 1},
        "protection_types": ["magical"],
        "special_traits": ["magical", "channeling", "focus", "mind"]
    },
    "formal_hat": {
        "mass": "light", "handedness": "Versatile", "armor_type": "unarmored",
        "base_dt": 0,
        "type_dt": {},
        "base_cha": 4,
        "stat_modifiers": {"cha": 4, "luck": 1, "etiquette": 3},
        "protection_types": ["social"],
        "special_traits": ["social", "civilian", "formal", "leadership"]
    }
}

NON_COMBAT_HEADWEAR_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "cloth_hood": HEADWEAR_ARCHETYPES["cloth_hood"],
    "cap": HEADWEAR_ARCHETYPES["cap"],
    "tech_visor": HEADWEAR_ARCHETYPES["tech_visor"],
    "circlet": HEADWEAR_ARCHETYPES["circlet"],
    "formal_hat": HEADWEAR_ARCHETYPES["formal_hat"]
}

for arch, data in HEADWEAR_ARCHETYPES.items():
    data["tags"] = derive_armor_tags(
        armor_class=data["armor_type"],
        protection_types=data["protection_types"],
        special_traits=data.get("special_traits", [])
    )

SCENARIO_HEADWEAR_AFFIXES: Dict[str, Dict[str, Any]] = {
    "fantasy": {
        "archetype_names": {
            "cloth_hood": ["Shadow-Stitched Cowl", "Ranger's Camo Hood", "Traveler's Woolen Hood"],
            "cap": ["Hunter's Feathered Cap", "Forester's Green Cap", "Apprentice's Scholar Cap"],
            "open_helm": ["Chainmail Coif & Nasal Helm", "Soldier's Sallet", "Iron Guardsman Helm"],
            "full_greathelm": ["Crusader's Steel Greathelm", "Knight's Visored Armet", "Gilded Dragon Helm"],
            "tech_visor": ["Hawkeye Monocle", "Archer's Focusing Lorgnette", "Gem-Cut Scrying Lens"],
            "gas_mask": ["Plague Doctor's Beaked Mask", "Alchemist's Filter Hood", "Asbestos Ash Mask"],
            "circlet": ["Mithril Arcane Circlet", "Runed Crownlet of Power", "Wizard's Pointed Hat"],
            "formal_hat": ["Gilded Sovereign Crown", "Noble Velvet Cap", "Courtier's Plumed Hat"]
        },
        "prefixes_t3": ["Iron", "Steel", "Stout", "Hardened", "Honed", "Apprentice's", "Sturdy"],
        "prefixes_t2": ["Runic", "Gilded", "Mithril", "Moonlit", "Spell-Forged", "Aegis-Bound"],
        "prefixes_t1": ["Sunfire", "Dragon-Forged", "Celestial", "Abyssal-Bound", "God-King's"],
        "suffixes_t2": ["of Clarity", "of the Guardian", "of Vision", "of Iron Will", "of Fortitude"],
        "suffixes_t1": ["of the Dragon Slayer", "of Divine Aegis", "of the Unshakable Crown", "of Absolute Mastery"]
    },
    "steampunk": {
        "archetype_names": {
            "cloth_hood": ["Aeronaut's Oilskin Hood", "Smog-Cowl", "Machinist's Canvas Cowl"],
            "cap": ["Newsboy Tweed Cap", "Machinist's Flat Cap", "Officer's Peaked Cap"],
            "open_helm": ["Riveted Copper Half-Helm", "Steam-Stoker Skullcap", "Boiler-Tender's Hardhat"],
            "full_greathelm": ["Brass-Piston Diving Greathelm", "Dreadnought Iron Visor", "Clockwork Heavy Casque"],
            "tech_visor": ["Multi-Lens Brass Goggles", "Aether-Spectrum Visor", "Galvanic Arc-Spectacles"],
            "gas_mask": ["Brass Filter Cannister Mask", "Mine-Shaft Respirator", "Steam-Vented Chem-Mask"],
            "circlet": ["Aether-Tuned Galvanic Diadem", "Clockwork Resonator Band", "Voltaic Induction Crown"],
            "formal_hat": ["Silk Top Hat with Clockwork Buckle", "Victorian Bowler Hat", "Aristocrat's Gilded Topper"]
        },
        "prefixes_t3": ["Brass-Rimmed", "Copper-Wired", "Machinist's", "Steam-Vented", "Rivet-Bound", "Standard"],
        "prefixes_t2": ["Galvanic", "Aether-Tuned", "Pneumatic", "Boiler-Forged", "Voltaic", "Clockwork-Laced"],
        "prefixes_t1": ["Perpetual-Motion", "Grand Victorian", "Tesla's Masterwork", "Dreadnought's", "Aether-Sovereign's"],
        "suffixes_t2": ["of the Piston", "of Steam Exhaust", "of Copper Induction", "of Cogwheel Precision"],
        "suffixes_t1": ["of Endless Pressure", "of the Brass Sovereign", "of Aetheric Synthesis", "of Chrono-Dominance"]
    },
    "cyberpunk": {
        "archetype_names": {
            "cloth_hood": ["Optical-Camo Stealth Hood", "Street Runner Cowl", "Carbon-Mesh Hoodie"],
            "cap": ["Tactical Ballistic Cap", "Street Punk Snapback", "Netrunner Mesh Cap"],
            "open_helm": ["SWAT Carbon Half-Helmet", "Enforcer Riot Cap", "Tactical Combat Shell"],
            "full_greathelm": ["Militech Heavy Assault Helmet", "Titanium Enforcer Helm", "Shock-Troop Sealed Visor"],
            "tech_visor": ["Kiroshi Neural HUD Visor", "Smart-Link Targeting Optics", "Cyber-Eye Monocle"],
            "gas_mask": ["Anti-Smog Street Respirator", "Mil-Spec Tactical Gas Mask", "Hazmat Bio-Filter Mask"],
            "circlet": ["Neural-Interface Brain-Wreath", "Cyberdeck Headband", "Datajack Synapse-Crown"],
            "formal_hat": ["Executive Fedora with Neon Band", "Corpo High-Roller Hat", "Holo-Matrix Crown"]
        },
        "prefixes_t3": ["Street-Grade", "Mil-Spec", "Carbon-Weave", "Chrome", "Reinforced", "Standard-Issue"],
        "prefixes_t2": ["Overclocked", "Smart-Linked", "High-Frequency", "Sub-Dermal", "Nanite-Laced", "Thermal-Chambered"],
        "prefixes_t1": ["Arasaka Prototype", "Black-ICE", "Zero-Day", "Militech Apex", "Ghost-Protocol", "Hyper-Threaded"],
        "suffixes_t2": ["of Target-Acquisition", "of the Netrunner", "of Recoil-Dampening", "of the Phantom"],
        "suffixes_t1": ["of Cyber-Dominance", "of System Override", "of the Apex Syndicate", "of Total Lockdown"]
    },
    "nuclear_post_apocalypse": {
        "archetype_names": {
            "cloth_hood": ["Tattered Burlap Rad-Hood", "Scavenger Dust Cowl", "Mutant-Hide Hood"],
            "cap": ["Faded Pre-War Baseball Cap", "Scav Patrol Cap", "Trucker Mesh Cap"],
            "open_helm": ["Spiked Hardhat", "Welded Hubcap Skullguard", "Cracked Riot Half-Helm"],
            "full_greathelm": ["Welded Iron Bucket Helm", "Lead-Lined Raider Greathelm", "Scrap-Plate Welding Mask"],
            "tech_visor": ["Cracked Aviator Goggles", "Jury-Rigged Scav Visor", "One-Eyed Scrap Monocle"],
            "gas_mask": ["Military Surplus Gas Mask", "Canister Rad-Respirator", "Hose-Fed Fallout Mask"],
            "circlet": ["Glowing Rad-Crystal Headband", "Mutant Mind-Coil", "Barbed-Wire Crown"],
            "formal_hat": ["Pre-War Governor's Top Hat", "Scav King's Bottlecap Crown", "Faded Cowboy Stetson"]
        },
        "prefixes_t3": ["Scrap-Metal", "Rusty", "Jury-Rigged", "Weathered", "Makeshift", "Spiked", "Lead-Lined"],
        "prefixes_t2": ["Rad-Hardened", "Bio-Toxic", "Reinforced-Steel", "Wasteland-Master", "Gamma-Tuned", "Spike-Studded"],
        "prefixes_t1": ["Doomsday", "Nuclear-Winter", "Alpha-Mutant", "Apex-Scavenger", "God-Corpse", "Irradiated"],
        "suffixes_t2": ["of the Scavenger", "of Rust & Ruin", "of the Raider", "of the Fallout Shelter"],
        "suffixes_t1": ["of Total Extinction", "of the Wasteland Tyrant", "of the Radioactive Storm", "of Endless Survival"]
    },
    "sci_fi": {
        "archetype_names": {
            "cloth_hood": ["Void-Cloth Thermal Hood", "Recon Nano-Cowl", "Zero-G Infiltration Hood"],
            "cap": ["Fleet Officer Duty Cap", "Flight Deck Patrol Cap", "Star-Marine Garrison Cap"],
            "open_helm": ["Marine Open Combat Helmet", "Titanium Skull-Cap", "Colony Security Helmet"],
            "full_greathelm": ["Orbital Drop Heavy Helmet", "Powered Armor Sealed Casque", "Dreadnought Titan Helm"],
            "tech_visor": ["Holographic Tactical HUD", "Quantum Targeting Visor", "Target-Vector Optics"],
            "gas_mask": ["Sealed Void-Breathing Mask", "Atmospheric Filter Rig", "Hazard Plasma Mask"],
            "circlet": ["Psionic Resonance Diadem", "Tachyon Neural-Crown", "Quantum Wave Transmitter"],
            "formal_hat": ["Admiral's Gold-Trimmed Visor Cap", "Fleet Sovereign Coronet", "Diplomatic Bicorne"]
        },
        "prefixes_t3": ["Titanium", "Composite", "Field", "Standard-Issue", "Carbon-Alloy", "Ceramic"],
        "prefixes_t2": ["Overcharged", "Plasma-Infused", "Hyper-Coil", "Nanite-Lined", "Quantum-Phase", "Cryo-Cooled"],
        "prefixes_t1": ["Supernova", "Singularity", "Antimatter", "Chrono-Phase", "Omni-Core", "Dark-Energy"],
        "suffixes_t2": ["of the Vanguard", "of Phase-Shift", "of the Orbital Marine", "of Vector-Lock"],
        "suffixes_t1": ["of Stellar Superiority", "of the Singularity Core", "of Cosmic Annihilation", "of Absolute Zero"]
    },
    "dark_fantasy": {
        "archetype_names": {
            "cloth_hood": ["Penitent's Blighted Veil", "Grave-Shrouded Cowl", "Executioner's Leather Hood"],
            "cap": ["Inquisitor's Peaked Cap", "Grave-Robber's Wool Cap", "Plague-Watcher's Cap"],
            "open_helm": ["Black-Iron Coif", "Torturer's Iron Skullcap", "Graveyard Soldier Helm"],
            "full_greathelm": ["Defiled Tomb-Knight Greathelm", "Abyssal Horned Helm", "Iron Maiden Casque"],
            "tech_visor": ["Oculus of Hex-Sight", "Weeping Eye Monocle", "Blood-Glass Scrying Lens"],
            "gas_mask": ["Corpse-Ash Death Mask", "Bone-Carved Ash-Filter", "Sanguine Muzzle"],
            "circlet": ["Crown of Bone Thorns", "Blood-Gem Diadem", "Hex-Weaver's Silver Band"],
            "formal_hat": ["Desolate King's Iron Crown", "Funeral Veil & Mourning Hat", "Inquisitor's Wide-Brimmed Hat"]
        },
        "prefixes_t3": ["Blood-Stained", "Weathered", "Grim", "Jagged", "Ashen", "Roughspun", "Grave-Dug"],
        "prefixes_t2": ["Hex-Forged", "Cursed", "Grave-Tainted", "Sanguine", "Blight-Edged", "Bone-Carved", "Shadow-Veiled"],
        "prefixes_t1": ["Eldritch", "Abyssal-Vein", "Death-Lord's", "Cataclysmic", "Blood-Pact", "Marrow-Forged"],
        "suffixes_t2": ["of Torment", "of the Pale Moon", "of the Grave", "of Weeping Shadow", "of Hex-Binding"],
        "suffixes_t1": ["of Eternal Damnation", "of the Abyssal Void", "of Endless Agony", "of the Desolate Throne"]
    },
    "high_school": {
        "archetype_names": {
            "cloth_hood": ["Casual Pullover Hood", "Rain Poncho Hood", "Streetwear Beanie"],
            "cap": ["School Uniform Cap", "Varsity Baseball Cap", "Student Newsboy Cap"],
            "open_helm": ["Bicycle Safety Helmet", "Skateboard Half-Shell", "Batting Helmet"],
            "full_greathelm": ["Motorcycle Full-Face Helmet", "Hockey Goalie Mask", "Kendo Men (Head Protector)"],
            "tech_visor": ["Designer Reading Glasses", "Trendy Sunglasses", "Computer Screen Glasses"],
            "gas_mask": ["Science Lab Safety Respirator", "Allergy Pollen Face Mask", "Art Club Paint Mask"],
            "circlet": ["Cute Ribbon Headband", "Athletic Gym Sweatband", "Cat-Ears Cosplay Headband"],
            "formal_hat": ["Student Council President's Cap", "Festival Flower Crown", "Graduation Cap"]
        },
        "prefixes_t3": ["Standard", "Student", "Clean", "Campus", "Everyday", "Casual", "School"],
        "prefixes_t2": ["Varsity", "Tailored", "Customized", "Honors", "Trendy", "Preppy", "Club-Captain's"],
        "prefixes_t1": ["Student Council President's", "Valedictorian's", "Championship", "Festival Champion's", "Campus Legend's"],
        "suffixes_t2": ["of the Study Group", "of Friendship", "of Style", "of Youth", "of the Honor Roll"],
        "suffixes_t1": ["of Everlasting Memories", "of the Grand Festival", "of Pure Dedication", "of the Campus Legend"]
    }
}

def normalize_headwear_scenario(scenario: str) -> str:
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
    slot: str = "Head",
    tier: Optional[int] = None,
    archetype: Optional[str] = None
) -> Dict[str, Any]:
    item_tier = tier if tier in (1, 2, 3) else roll_tier()
    scen_key = normalize_headwear_scenario(scenario)
    
    try:
        from scenario_data import is_non_combat_scenario
        is_non_combat = is_non_combat_scenario(scenario) or scen_key == "high_school"
    except Exception:
        is_non_combat = scen_key == "high_school"
        
    pool_dict = NON_COMBAT_HEADWEAR_ARCHETYPES if is_non_combat else HEADWEAR_ARCHETYPES
    
    if archetype and archetype in pool_dict:
        arch = archetype
    elif archetype and archetype in HEADWEAR_ARCHETYPES and not is_non_combat:
        arch = archetype
    else:
        arch = random.choice(list(pool_dict.keys()))
        
    base_data = HEADWEAR_ARCHETYPES[arch]
    tier_mult = 1.0 if item_tier == 3 else (1.20 if item_tier == 2 else 1.45)
    
    base_dt = int(round(base_data["base_dt"] * tier_mult))
    type_dt = {k: int(round(v * tier_mult)) for k, v in base_data.get("type_dt", {}).items()}
    
    stat_mods: Dict[str, Any] = {}
    for k, v in base_data.get("stat_modifiers", {}).items():
        if isinstance(v, float):
            stat_mods[k] = round(v * tier_mult, 2)
        elif isinstance(v, int):
            scaled = int(round(v * tier_mult))
            if k == "per" and scaled < 0:
                scaled = max(-1, scaled)  # Sensory penalty on enclosed helmets is strictly capped at -1 PER
            stat_mods[k] = scaled
        else:
            stat_mods[k] = v
            
    if base_dt > 0:
        stat_mods["base_dt"] = base_dt

    scen_affixes = SCENARIO_HEADWEAR_AFFIXES.get(scen_key, SCENARIO_HEADWEAR_AFFIXES["fantasy"])
    genre_names = scen_affixes.get("archetype_names", {}).get(arch, [arch.replace("_", " ").title()])
    base_name = random.choice(genre_names)
    
    prefix_pool = scen_affixes.get(f"prefixes_t{item_tier}", ["Fine"])
    suffix_pool = scen_affixes.get(f"suffixes_t{item_tier}", ["of Vision"])
    
    prefix = random.choice(prefix_pool)
    if item_tier == 3:
        name = f"{prefix} {base_name}"
    else:
        suffix = random.choice(suffix_pool)
        name = f"{prefix} {base_name} {suffix}"
        
    metadata = {
        "name": name,
        "tier": item_tier,
        "slot": "Head",
        "item_type": "Headwear",
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
        "item_type": "Headwear",
        "slot": "Head",
        "effect": serialize_item(metadata),
        "metadata": metadata,
        "slot_cost": 1
    }

def format_equipment_card(metadata: Dict[str, Any]) -> str:
    tier = metadata.get("tier", 3)
    name = metadata.get("name", "Headwear")
    arch = metadata.get("archetype", "headwear").replace("_", " ").title()
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
        
    stat_line = " | ".join(stat_parts) if stat_parts else "Standard Headwear"
    
    type_dt_str = ", ".join(f"{k.title()}: {v}" for k, v in type_dt.items() if v > 0) or "None"
    
    lines = [
        f"**{name}** (Tier {tier} Headwear — {arch})",
        f"• **Protection & Utility**: {stat_line}",
        f"• **Type Resistances**: {type_dt_str}"
    ]
    return "\n".join(lines)
