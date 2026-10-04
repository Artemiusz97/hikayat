from __future__ import annotations
import random
from typing import Dict, Any, Optional

from mechanics.combat.items.tags import derive_armor_tags
from mechanics.combat.items.envelope import serialize_item

ARMOR_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    # ── Civilian / Unarmored ─────────────────────────────────────────────────
    "clothes": {
        "armor_type": "unarmored", "protection_types": ["physical"],
        "base_dt": 0,
        "type_dt": {
            # No meaningful physical DT; minimal magic shielding
            "magical": 1, "holy": 1, "dark": 0,
            "fire": 0, "shock": 0, "ice": 0, "poison": 0
        },
        "base_eva": 6
    },

    # ── Arcane / Caster ──────────────────────────────────────────────────────
    "magic_robe": {
        "armor_type": "light", "protection_types": ["magical", "energy"],
        "base_dt": 2,
        "type_dt": {
            # Robes are woven with wards — excellent vs spells, weak vs blades
            "magical": 16, "holy": 14, "dark": 14,
            "fire": 12, "shock": 12, "ice": 12, "poison": 10, "acid": 10,
            "energy": 14, "energy_cell": 14,
            "physical": 1
        },
        "base_eva": 4
    },

    # ── Light Physical ───────────────────────────────────────────────────────
    "leather": {
        "armor_type": "light", "protection_types": ["physical"],
        "base_dt": 6,
        "type_dt": {
            "slashing": 8, "stabbing": 6, "ballistic": 4,
            "arrow": 8, "pistol_round": 4, "rifle_round": 2,
            # Low magical protection
            "magical": 3, "fire": 2, "shock": 2, "ice": 3,
            "poison": 2, "holy": 2, "dark": 2
        },
        "base_eva": 4
    },

    # ── Modern Light Ballistic ───────────────────────────────────────────────
    "kevlar": {
        "armor_type": "light", "protection_types": ["ballistic"],
        "base_dt": 10,
        "type_dt": {
            "ballistic": 22, "pistol_round": 24, "scatter_shot": 20,
            "slashing": 12, "rifle_round": 8, "arrow": 6, "fire": 2,
            # Kevlar offers minimal arcane protection
            "magical": 2, "shock": 4, "ice": 2, "holy": 2, "dark": 2
        },
        "base_eva": 2
    },

    # ── Medium Physical ──────────────────────────────────────────────────────
    "chainmail": {
        "armor_type": "medium", "protection_types": ["physical"],
        "base_dt": 12,
        "type_dt": {
            "slashing": 18, "stabbing": 10, "physical": 14,
            "arrow": 12, "bolt": 8, "pistol_round": 6, "rifle_round": 2,
            # Metal conducts — good vs physical magic, weak vs shock
            "magical": 6, "holy": 5, "dark": 5,
            "fire": 4, "shock": 0, "ice": 6, "poison": 4
        },
        "base_eva": 0,
        "stat_modifiers": {"shock_res": -15}
    },

    "lamellar": {
        "armor_type": "medium", "protection_types": ["physical"],
        "base_dt": 14,
        "type_dt": {
            "slashing": 20, "stabbing": 14, "blunt": 8,
            "arrow": 16, "bolt": 10, "pistol_round": 8, "rifle_round": 4,
            # Lamellar plates are lacquered — moderate fire resistance
            "magical": 7, "holy": 6, "dark": 6,
            "fire": 6, "shock": 0, "ice": 8, "poison": 5
        },
        "base_eva": -2,
        "stat_modifiers": {"shock_res": -15}
    },

    # ── Modern Medium Ballistic+Energy ───────────────────────────────────────
    "ceramic": {
        "armor_type": "medium", "protection_types": ["ballistic", "energy"],
        "base_dt": 16,
        "type_dt": {
            "ballistic": 26, "rifle_round": 26, "pistol_round": 26,
            "energy_cell": 20, "scatter_shot": 22, "high_caliber_round": 10,
            "energy": 20, "slashing": 14,
            # Ceramic inserts have some magical and fire resistance
            "magical": 8, "fire": 10, "shock": 8, "ice": 6,
            "holy": 6, "dark": 6, "poison": 4
        },
        "base_eva": -2
    },

    # ── Heavy Physical ───────────────────────────────────────────────────────
    "plate": {
        "armor_type": "heavy", "protection_types": ["physical"],
        "base_dt": 22,
        "type_dt": {
            "physical": 28, "slashing": 32, "stabbing": 20, "blunt": 14,
            "arrow": 24, "bolt": 18, "pistol_round": 22, "rifle_round": 14,
            "energy_cell": 4, "shock": 0,
            # Steel plate is heavy — poor elemental insulation
            "magical": 8, "holy": 10, "dark": 6,
            "fire": 4, "ice": 12, "poison": 6, "acid": 2
        },
        "base_eva": -6,
        "stat_modifiers": {"shock_res": -15}
    },

    # ── Heavy Physical+Ballistic ─────────────────────────────────────────────
    "composite": {
        "armor_type": "heavy", "protection_types": ["physical", "ballistic", "explosive"],
        "base_dt": 24,
        "type_dt": {
            "physical": 26, "ballistic": 28, "rifle_round": 28,
            "pistol_round": 30, "high_caliber_round": 16, "scatter_shot": 26,
            "explosive": 22, "shock": 0,
            # Composite layering adds moderate elemental resistance
            "magical": 10, "fire": 8, "shock": 0, "ice": 10,
            "holy": 8, "dark": 8, "poison": 6, "energy": 12
        },
        "base_eva": -6
    },

    # ── Power Armor ──────────────────────────────────────────────────────────
    "power_armor": {
        "armor_type": "power_armor",
        "protection_types": ["physical", "ballistic", "energy", "explosive"],
        "base_dt": 32,
        "type_dt": {
            "physical": 36, "ballistic": 40, "rifle_round": 36,
            "pistol_round": 40, "high_caliber_round": 28,
            "energy_cell": 30, "energy": 30, "explosive": 35,
            # Powered suits have integrated EM shielding and hazmat layers
            "magical": 16, "fire": 18, "shock": 10, "ice": 14,
            "holy": 12, "dark": 12, "poison": 20, "acid": 16
        },
        "base_eva": -8
    }
}

for arch, data in ARMOR_ARCHETYPES.items():
    data["tags"] = derive_armor_tags(
        armor_class=data["armor_type"],
        protection_types=data["protection_types"]
    )

SCENARIO_ARMOR_AFFIXES: Dict[str, Dict[str, Any]] = {
    "fantasy": {
        "archetype_names": {
            "clothes": ["Traveler's Tunic", "Linen Garments", "Commoner's Attire"],
            "magic_robe": ["Silk Mystic Robes", "Sorcerer's Weave Robe", "Apprentice's Spell-Robe"],
            "leather": ["Hardened Leather Jerkin", "Ranger's Cuirass", "Huntsman's Tunic"],
            "kevlar": ["Reinforced Gambeson", "Layered Padded Armor", "Armored Doublet"],
            "chainmail": ["Riveted Chainmail Hauberk", "Iron Link Shirt", "Steel Chain Vest"],
            "lamellar": ["Lacquered Lamellar Cuirass", "Scale-Mail Hauberk", "Banded Iron Armor"],
            "ceramic": ["Mithril-Inlaid Cuirass", "Runed Dwarven Breastplate", "Adamantine-Laced Armor"],
            "plate": ["Knight's Full Plate", "Crusader's Steel Breastplate", "Gilded Field Plate"],
            "composite": ["Dragon-Bone Carapace", "Enchanted Dragon-Scale Cuirass", "Adamantine Citadel Armor"],
            "power_armor": ["Titan's Golem Armor", "Runed Aegis War-Harness", "Ancient God-Forged Exosuit"]
        },
        "prefixes_t3": ["Iron", "Steel", "Stout", "Hardened", "Field", "Apprentice's", "Sturdy"],
        "prefixes_t2": ["Runic", "Gilded", "Mithril", "Moonlit", "Spell-Forged", "Drake-Scale", "Aegis-Bound"],
        "prefixes_t1": ["Sunfire", "Dragon-Forged", "Celestial", "Abyssal-Bound", "God-King's", "Archmage's"],
        "suffixes_t2": ["of Warding", "of the Guardian", "of Iron Will", "of Fortitude", "of the Aegis"],
        "suffixes_t1": ["of the Dragon Slayer", "of Divine Aegis", "of the Immortal Bastion", "of Absolute Defense"]
    },
    "steampunk": {
        "archetype_names": {
            "clothes": ["Machinist's Workwear", "Victorian Tweed Suit", "Stoker's Overalls"],
            "magic_robe": ["Aether-Insulated Greatcoat", "Alchemist's Rubberized Smock", "Philosopher's Robe"],
            "leather": ["Riveted Pilot Leather Coat", "Aeronaut's Oilskin Vest", "Boiler-Tender's Hide Vest"],
            "kevlar": ["Padded Ballistic Waistcoat", "Reinforced Canvas Flak-Vest", "Machinist's Chest-Guard"],
            "chainmail": ["Brass-Ring Mail Hauberk", "Copper-Linked Mesh Vest", "Interlocked Gear-Mesh"],
            "lamellar": ["Riveted Brass Scale-Armor", "Layered Copper Lamellar", "Artificer's Plate-Vest"],
            "ceramic": ["Pressure-Molded Ceramic Vest", "Asbestos Heat-Plate Cuirass", "Galvanic Arc-Deflector"],
            "plate": ["Boiler-Forged Iron Cuirass", "Riveted Brass Breastplate", "Steam-Vented Field Plate"],
            "composite": ["Galvanic Heavy Carapace", "Reinforced Clockwork Iron-Shell", "Voltaic Dreadnought Rig"],
            "power_armor": ["Steam-Powered Exosuit", "Hydraulic Piston War-Frame", "Dreadnought Steam-Armor"]
        },
        "prefixes_t3": ["Brass-Plated", "Copper-Wired", "Machinist's", "Steam-Vented", "Rivet-Bound", "Standard"],
        "prefixes_t2": ["Galvanic", "Aether-Tuned", "Pneumatic", "Boiler-Forged", "Voltaic", "Clockwork-Laced"],
        "prefixes_t1": ["Perpetual-Motion", "Grand Victorian", "Tesla's Masterwork", "Dreadnought's", "Aether-Sovereign's"],
        "suffixes_t2": ["of the Piston", "of Steam Exhaust", "of Copper Induction", "of Cogwheel Resilience"],
        "suffixes_t1": ["of Endless Pressure", "of the Brass Sovereign", "of Aetheric Synthesis", "of the Iron Colossus"]
    },
    "cyberpunk": {
        "archetype_names": {
            "clothes": ["Streetwear Jacket & Pants", "Casual Holo-Fiber Attire", "Club Runner Synth-Wear"],
            "magic_robe": ["Netrunner Thermal-Dissipation Duster", "Holo-Weave Stealth Cloak", "Cryo-Fiber Coat"],
            "leather": ["Synthetic Leather Biker Vest", "Reinforced Punk Leather Jacket", "Carbon-Grip Cuirass"],
            "kevlar": ["Subdermal Ballistic Weave", "Mil-Spec Kevlar Vest", "Tactical SWAT Flak Jacket"],
            "chainmail": ["Flex-Steel Interlocked Mesh", "Micro-Chainmail Undersuit", "Kevlar-Chain Hybrid"],
            "lamellar": ["Segmented Polymer Plates", "Aramid Scaled Tac-Armor", "Modular Riot-Plate Vest"],
            "ceramic": ["Ceramic Insert Tactical Carrier", "Hard-Light Dispersion Vest", "Impact-Reactive Armor"],
            "plate": ["Titanium Heavy Enforcer Plate", "Corporate Security Tactical Armor", "Shock-Troop Chestplate"],
            "composite": ["Subdermal Nano-Weave Chassis", "Reinforced Polymer Exoshell", "Black-Market Combat Shell"],
            "power_armor": ["Militech Powered Combat Rig", "Arasaka Heavy War-Exoskeleton", "Heavy Cyber-Frame Armor"]
        },
        "prefixes_t3": ["Street-Grade", "Mil-Spec", "Carbon-Weave", "Chrome", "Reinforced", "Standard-Issue"],
        "prefixes_t2": ["Overclocked", "Smart-Linked", "High-Frequency", "Sub-Dermal", "Nanite-Laced", "Thermal-Chambered"],
        "prefixes_t1": ["Arasaka Prototype", "Black-ICE", "Zero-Day", "Militech Apex", "Ghost-Protocol", "Hyper-Threaded"],
        "suffixes_t2": ["of Ballistic Dampening", "of the Netrunner", "of Recoil-Absorption", "of the Street Phantom"],
        "suffixes_t1": ["of Cyber-Dominance", "of Impenetrable ICE", "of the Apex Syndicate", "of Total Defense"]
    },
    "nuclear_post_apocalypse": {
        "archetype_names": {
            "clothes": ["Tattered Rags & Burlap", "Scavenger's Dirty Tunic", "Worn Wanderer Clothes"],
            "magic_robe": ["Rad-Priest Glowing Shroud", "Mutant-Cultist Mantle", "Lead-Threaded Cowl"],
            "leather": ["Road-Warrior Duster", "Hardened Brahmin-Hide Vest", "Scavenger Leathers"],
            "kevlar": ["Jury-Rigged Flak Vest", "Tire-Rubber Fragment Jacket", "Scrap-Lined Riot Vest"],
            "chainmail": ["Barbed-Wire Chain Shirt", "Bicycle-Chain Mesh Hauberk", "Rusted Ring-Mail"],
            "lamellar": ["License-Plate Lamellar Armor", "Road-Sign Scale Cuirass", "Flattened Tin-Plate Vest"],
            "ceramic": ["Toilet-Porcelain Blast Plate", "Rad-Hardened Ceramic Carrier", "Crushed Tile Blast Vest"],
            "plate": ["Welded Scrap-Iron Breastplate", "Oil-Drum Heavy Cuirass", "Car-Bumper Steel Plate"],
            "composite": ["Rad-Hardened Scrap-Plate Rig", "Double-Hull Heavy Armor", "Highway Raider Bastion Armor"],
            "power_armor": ["Salvaged T-Series Power Armor", "Scrap-Metal Hydraulic War-Suit", "Irradiated Colossus Exosuit"]
        },
        "prefixes_t3": ["Scrap-Metal", "Rusty", "Jury-Rigged", "Weathered", "Makeshift", "Spiked", "Lead-Lined"],
        "prefixes_t2": ["Rad-Hardened", "Bio-Toxic", "Reinforced-Steel", "Wasteland-Master", "Gamma-Tuned", "Spike-Studded"],
        "prefixes_t1": ["Doomsday", "Nuclear-Winter", "Alpha-Mutant", "Apex-Scavenger", "God-Corpse", "Irradiated"],
        "suffixes_t2": ["of the Scavenger", "of Rust & Ruin", "of the Raider", "of the Fallout Shelter"],
        "suffixes_t1": ["of Total Extinction", "of the Wasteland Tyrant", "of the Radioactive Storm", "of Endless Survival"]
    },
    "sci_fi": {
        "archetype_names": {
            "clothes": ["Fleet Duty Uniform", "Civilian Utility Jumpsuit", "Colony Casual Garb"],
            "magic_robe": ["Psionic Resonance Robes", "Energy-Weave Field Shroud", "Cryo-Insulated Void Cloak"],
            "leather": ["Polymer Flight Suit", "Synthetic Hazard Vest", "Explorer's Flex-Armor"],
            "kevlar": ["Aramid Ballistic Flak Vest", "Light Void-Encounter Suit", "Deck-Crew Blast Vest"],
            "chainmail": ["Carbon-Nanotube Mesh Undersuit", "Interlocked Titanium Micro-Mail", "Flex-Alloy Mesh"],
            "lamellar": ["Segmented Ceramic Carapace", "Modular Composite Plate Vest", "Vanguard Kinetic Ribs"],
            "ceramic": ["Ablative Ceramic Space-Armor", "Nanite-Coated Blast Carrier", "Energy-Dispersal Plate"],
            "plate": ["Titanium-Alloy Battle Cuirass", "Heavy Marine Chestplate", "Orbital Drop Breastplate"],
            "composite": ["Kinetic Dispersion Void Carapace", "Multi-Phase Composite Battlesuit", "Quantum-Lattice Shell"],
            "power_armor": ["Dreadnought Powered Exosuit", "Orbital Heavy Assault Armor", "Nova-Class Siege Armor"]
        },
        "prefixes_t3": ["Titanium", "Composite", "Field", "Standard-Issue", "Carbon-Alloy", "Ceramic"],
        "prefixes_t2": ["Overcharged", "Plasma-Infused", "Hyper-Coil", "Nanite-Lined", "Quantum-Phase", "Cryo-Cooled"],
        "prefixes_t1": ["Supernova", "Singularity", "Antimatter", "Chrono-Phase", "Omni-Core", "Dark-Energy"],
        "suffixes_t2": ["of the Vanguard", "of Phase-Shift", "of the Orbital Marine", "of Deflection"],
        "suffixes_t1": ["of Stellar Superiority", "of the Singularity Core", "of Cosmic Fortification", "of Absolute Zero"]
    },
    "dark_fantasy": {
        "archetype_names": {
            "clothes": ["Tattered Grave-Clothes", "Mourning Weeds", "Peasant's Bloodied Linens"],
            "magic_robe": ["Blood-Stitched Shroud", "Necromancer's Velvet Cassock", "Hex-Weaver Cowl"],
            "leather": ["Cursed Executioner's Leathers", "Grave-Robber's Stitched Jerkin", "Flesh-Bound Tunic"],
            "kevlar": ["Thickened Padded Gambeson", "Iron-Stitched Heavy Doublet", "Martyr's Quilted Vest"],
            "chainmail": ["Black-Iron Hauberk", "Torturer's Rusted Ringmail", "Graveyard Chain Shirt"],
            "lamellar": ["Blight-Forged Scale Mail", "Bone-Splint Lamellar Cuirass", "Sanguine Scale Vest"],
            "ceramic": ["Hex-Infused Stone Carapace", "Catacomb Marble Breastplate", "Ossuary Relic Plate"],
            "plate": ["Grave-Knight Black Plate", "Defiled Steel Breastplate", "Inquisitor's Iron Maiden Plate"],
            "composite": ["Cursed Bone-Plate Carapace", "Marrow-Forged Dread Armor", "Abyssal Chimera Hide Armor"],
            "power_armor": ["Possessed Relic Colossus Armor", "Blood-Pact Iron Automaton Frame", "Eldritch Tomb Carapace"]
        },
        "prefixes_t3": ["Blood-Stained", "Weathered", "Grim", "Jagged", "Ashen", "Roughspun", "Grave-Dug"],
        "prefixes_t2": ["Hex-Forged", "Cursed", "Grave-Tainted", "Sanguine", "Blight-Edged", "Bone-Carved", "Shadow-Veiled"],
        "prefixes_t1": ["Eldritch", "Abyssal-Vein", "Death-Lord's", "Cataclysmic", "Blood-Pact", "Marrow-Forged"],
        "suffixes_t2": ["of Torment", "of the Pale Moon", "of the Grave", "of Weeping Shadow", "of Hex-Binding"],
        "suffixes_t1": ["of Eternal Damnation", "of the Abyssal Void", "of Endless Agony", "of the Desolate Bastion"]
    },
    "high_school": {
        "archetype_names": {
            "clothes": ["Clean School Uniform Top", "Casual Hooded Jacket", "PE Cotton T-Shirt"],
            "magic_robe": ["Science Club Hazmat Lab Coat", "Drama Club Velvet Cloak", "Art Smock"],
            "leather": ["Trendy Leather Bomber Jacket", "Motorcycle Club Leather Vest", "Vintage Riding Jacket"],
            "kevlar": ["Varsity Quilted Down Vest", "Heavy Padded Winter Parka", "Security Staff Padded Vest"],
            "chainmail": ["Chain-Link Fashion Corset", "Costume Prop Chainmail", "Heavy Metal Studded Vest"],
            "lamellar": ["Kendo Protective Do (Chest Armor)", "Fencing Padded Plastron", "Hockey Chest Protector"],
            "ceramic": ["Baseball Catcher's Chest Protector", "Motocross Armored Vest", "Football Shoulder Pads"],
            "plate": ["Stage Prop Knight Breastplate", "Museum Display Steel Cuirass", "Heavy Riot Police Vest"],
            "composite": ["Reinforced Extreme-Sports Rig", "High-Impact Motorcycle Armor", "Bodyguard Ballistic Vest"],
            "power_armor": ["Robotics Club Robotic Exoskeleton", "Mascot Mechanical Heavy Suit", "Stage Tech Powered Frame"]
        },
        "prefixes_t3": ["Standard", "Student", "Clean", "Campus", "Everyday", "Casual", "School"],
        "prefixes_t2": ["Varsity", "Tailored", "Customized", "Honors", "Trendy", "Preppy", "Club-Captain's"],
        "prefixes_t1": ["Student Council President's", "Valedictorian's", "Championship", "Festival Champion's", "Campus Legend's"],
        "suffixes_t2": ["of the Study Group", "of Friendship", "of Style", "of Youth", "of the Varsity Team"],
        "suffixes_t1": ["of Everlasting Memories", "of the Championship", "of Pure Dedication", "of the Grand Festival"]
    }
}

def normalize_armor_scenario(scenario: str) -> str:
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

def generate_random_equipment(scenario: str = "fantasy", slot: str = "Armor", tier: Optional[int] = None, archetype: Optional[str] = None) -> Dict[str, Any]:
    item_tier = tier if tier in (1, 2, 3) else roll_tier()
    scen_key = normalize_armor_scenario(scenario)
    
    archetype = archetype if archetype in ARMOR_ARCHETYPES else random.choice(list(ARMOR_ARCHETYPES.keys()))
    base_data = ARMOR_ARCHETYPES[archetype]
    
    tier_mult = 1.0 if item_tier == 3 else (1.20 if item_tier == 2 else 1.45)
    base_dt = int(round(base_data["base_dt"] * tier_mult))
    type_dt = {k: int(round(v * tier_mult)) for k, v in base_data.get("type_dt", {}).items()}

    scen_affixes = SCENARIO_ARMOR_AFFIXES.get(scen_key, SCENARIO_ARMOR_AFFIXES["fantasy"])
    genre_names = scen_affixes.get("archetype_names", {}).get(archetype, [archetype.replace("_", " ").title()])
    base_name = random.choice(genre_names)
    
    prefix_pool = scen_affixes.get(f"prefixes_t{item_tier}", ["Stout"])
    suffix_pool = scen_affixes.get(f"suffixes_t{item_tier}", ["of Defense"])
    
    prefix = random.choice(prefix_pool)
    if item_tier == 3:
        name = f"{prefix} {base_name}"
    else:
        suffix = random.choice(suffix_pool)
        name = f"{prefix} {base_name} {suffix}"
        
    stat_mods: Dict[str, Any] = {"base_dt": base_dt} if base_dt > 0 else {}
    if "base_eva" in base_data:
        stat_mods["eva"] = base_data["base_eva"]
    for k, v in base_data.get("stat_modifiers", {}).items():
        stat_mods[k] = v

    metadata = {
        "name": name,
        "tier": item_tier,
        "slot": slot or "Armor",
        "item_type": "Armor",
        "archetype": archetype,
        "base_dt": base_dt,
        "type_dt": type_dt,
        "base_eva": base_data.get("base_eva", 0),
        "tags": base_data["tags"],
        "stat_modifiers": stat_mods
    }
    
    return {
        "name": name,
        "item_type": "Armor",
        "slot": slot or "Armor",
        "effect": serialize_item(metadata),
        "metadata": metadata,
        "slot_cost": 1
    }

def format_equipment_card(metadata: Dict[str, Any]) -> str:
    tier = metadata.get("tier", 3)
    name = metadata.get("name", "Armor")
    arch = metadata.get("archetype", "armor").replace("_", " ").title()
    base_dt = metadata.get("base_dt", 0)
    type_dt = metadata.get("type_dt", {})
    base_eva = metadata.get("base_eva", metadata.get("stat_modifiers", {}).get("eva", 0))
    
    type_dt_str = ", ".join(f"{k.title()}: {v}" for k, v in type_dt.items()) or "None"
    
    eva_str = f" • **EVA Mod:** {base_eva:+d}%" if base_eva != 0 else ""
    lines = [
        f"**{name}** (Tier {tier})",
        f"**Slot:** Armor • **Archetype:** {arch}{eva_str}",
        f"**Base DT:** {base_dt}",
        f"**Type DT:** {type_dt_str}"
    ]
    return "\n".join(lines)
