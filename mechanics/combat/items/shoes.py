from __future__ import annotations
import copy
import random
from typing import Dict, Any, Optional

from mechanics.combat.items.tags import derive_armor_tags
from mechanics.combat.items.envelope import serialize_item

SHOE_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    # ── Civilian & Light Footwear (0 DT, Evasion / Minor DR / Utility) ────────
    "light_sneakers": {
        "mass": "light", "handedness": "Versatile", "armor_type": "unarmored",
        "base_dt": 0,
        "type_dt": {},
        "base_eva": 4,
        "stat_modifiers": {"eva": 4},
        "protection_types": ["physical"],
        "special_traits": ["high_mobility", "light"]
    },
    "sandals": {
        "mass": "light", "handedness": "Versatile", "armor_type": "unarmored",
        "base_dt": 0,
        "type_dt": {},
        "base_eva": 3,
        "stat_modifiers": {"eva": 3, "heat_res": 10},
        "protection_types": ["physical"],
        "special_traits": ["ultralight", "unarmed"]
    },
    "stealth_boots": {
        "mass": "light", "handedness": "Versatile", "armor_type": "unarmored",
        "base_dt": 0,
        "type_dt": {},
        "base_eva": 3,
        "stat_modifiers": {"eva": 3},
        "protection_types": ["physical"],
        "special_traits": ["stealth", "silent_step", "light"]
    },
    "riding_boots": {
        "mass": "medium", "handedness": "Versatile", "armor_type": "unarmored",
        "base_dt": 0,
        "type_dt": {},
        "base_eva": 2,
        "stat_modifiers": {"eva": 2, "acc": 1, "physical_res": 3},
        "protection_types": ["physical"],
        "special_traits": ["versatile", "sturdy", "leather"]
    },
    "hazard_boots": {
        "mass": "medium", "handedness": "Versatile", "armor_type": "unarmored",
        "base_dt": 0,
        "type_dt": {},
        "base_eva": 0,
        "stat_modifiers": {"poison_res": 15, "acid_res": 15},
        "protection_types": ["energy", "magical"],
        "special_traits": ["hazmat", "environmental_isolation"]
    },
    "formal_shoes": {
        "mass": "light", "handedness": "Versatile", "armor_type": "unarmored",
        "base_dt": 0,
        "type_dt": {},
        "base_cha": 1, "base_eva": 1,
        "stat_modifiers": {"cha": 1, "eva": 1},
        "protection_types": ["social"],
        "special_traits": ["social", "civilian", "formal"]
    },
    "oxfords": {
        "mass": "light", "handedness": "Versatile", "armor_type": "unarmored",
        "base_dt": 0,
        "type_dt": {},
        "stat_modifiers": {"cha": 1, "eva": 1},
        "protection_types": ["social"],
        "special_traits": ["social", "civilian", "period_formal", "dapper"]
    },
    "spats_boots": {
        "mass": "medium", "handedness": "Versatile", "armor_type": "unarmored",
        "base_dt": 0,
        "type_dt": {},
        "stat_modifiers": {"cha": 1, "physical_res": 3},
        "protection_types": ["social"],
        "special_traits": ["social", "civilian", "steampunk", "period"]
    },
    "high_heels": {
        "mass": "light", "handedness": "Versatile", "armor_type": "unarmored",
        "base_dt": 0,
        "type_dt": {},
        "stat_modifiers": {"cha": 1, "eva": 1},
        "protection_types": ["social"],
        "special_traits": ["social", "civilian", "formal", "glamorous"]
    },
    "platform_boots": {
        "mass": "medium", "handedness": "Versatile", "armor_type": "unarmored",
        "base_dt": 0,
        "type_dt": {},
        "stat_modifiers": {"eva": 1, "physical_res": 4},
        "protection_types": ["physical"],
        "special_traits": ["streetwear", "rebel", "chunky"]
    },
    "mag_sneakers": {
        "mass": "light", "handedness": "Versatile", "armor_type": "unarmored",
        "base_dt": 0,
        "type_dt": {},
        "stat_modifiers": {"eva": 3, "energy_res": 4, "acc": 1},
        "protection_types": ["energy"],
        "special_traits": ["futuristic", "high_mobility", "magnetic"]
    },

    # ── Dedicated Combat Footwear (Provides DT) ──────────────────────────────
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
        "stat_modifiers": {"eva": -3, "knockdown_res": 25},
        "protection_types": ["physical", "ballistic"],
        "special_traits": ["heavy", "defensive"]
    }
}

NON_COMBAT_SHOE_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "light_sneakers": SHOE_ARCHETYPES["light_sneakers"],
    "sandals": SHOE_ARCHETYPES["sandals"],
    "stealth_boots": SHOE_ARCHETYPES["stealth_boots"],
    "riding_boots": SHOE_ARCHETYPES["riding_boots"],
    "hazard_boots": SHOE_ARCHETYPES["hazard_boots"],
    "formal_shoes": SHOE_ARCHETYPES["formal_shoes"],
    "oxfords": SHOE_ARCHETYPES["oxfords"],
    "spats_boots": SHOE_ARCHETYPES["spats_boots"],
    "high_heels": SHOE_ARCHETYPES["high_heels"],
    "platform_boots": SHOE_ARCHETYPES["platform_boots"],
    "mag_sneakers": SHOE_ARCHETYPES["mag_sneakers"]
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
            "formal_shoes": ["Embroidered Court Slippers", "Noble Velvet Slippers", "Gilded Court Shoes"],
            "oxfords": ["Noble Brogue Shoes", "Guildmaster's Stitched Oxfords", "Courtier's Buckled Shoes"],
            "spats_boots": ["Fur-Trimmed Riding Boots", "High-Collar Leather Spats-Boots", "Cavalier Gaiters"],
            "high_heels": ["Gilded Court Slippers", "Court Lady's High Pumps", "Princess Velvet Slippers"],
            "platform_boots": ["Heavy Forest Stompers", "Mountain Climber Thick Soles", "Brawler's Cuffed Boots"],
            "mag_sneakers": ["Wind-Step Enchanted Shoes", "Feather-Fall Soft Boots", "Zephyr Runners"]
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
            "formal_shoes": ["Polished Spats & Oxford Brogues", "Victorian Patent Oxfords", "Gilded Gentleman Shoes"],
            "oxfords": ["Savile Row Wingtip Brogues", "Polished Victorian Oxfords", "Detective's Sturdy Brogues"],
            "spats_boots": ["Buttoned Victorian Spats Boots", "Brass-Buckled Gaiter Boots", "Aeronaut Spats Treads"],
            "high_heels": ["Victorian Lace-Up Court Heels", "Edwardian Satin Pumps", "Grand Dame Spats-Heels"],
            "platform_boots": ["Clogger Platform Boots", "Boiler-Tender Heavy Sole Boots", "Gothic Spat Platforms"],
            "mag_sneakers": ["Clockwork Spring Shoes", "Pneumatic Bellows Runners", "Voltaic Coil Creepers"]
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
            "formal_shoes": ["Neon-Lined Corporate Loafers", "High-Gloss Executive Oxfords", "Cyber-Silk Dress Heels"],
            "oxfords": ["Smart-Leather Executive Brogues", "Carbon-Sole Tuxedo Oxfords", "Corpo Minimalist Brogues"],
            "spats_boots": ["Neo-Victorian Cyber Spats", "Chrome-Buckled Gaiter Boots", "Netrunner Spat-Kicks"],
            "high_heels": ["Stiletto Carbon-Fiber Heels", "Holo-Heels with Neon Spike", "Executive Patent Stilettos"],
            "platform_boots": ["Chunky Cyber-Goth Platforms", "Riot-Sole Street Platforms", "Industrial Creeper Boots"],
            "mag_sneakers": ["Zero-G Hover-Sneakers", "Magnetic Friction Kicks", "Pneumatic Spring High-Tops"]
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
            "formal_shoes": ["Scuffed Pre-War Dress Oxfords", "Dusty Corporate Loafers", "Old World Shiny Shoes"],
            "oxfords": ["Pre-War Scuffed Brogues", "Survivor's Patched Oxfords", "Bunker Formal Shoes"],
            "spats_boots": ["Canvas Dust Gaiter Boots", "Scrap-Leather Spats Boots", "Highway Spats Treads"],
            "high_heels": ["Pre-War Broken High Heels", "Scavenged Stiletto Pumps", "Vault Formal Heels"],
            "platform_boots": ["Tire-Laminated Platform Stompers", "Heavy Scrap Platform Boots", "Raider Chunky Boots"],
            "mag_sneakers": ["Salvaged Mag-Tread Shoes", "Pre-War Kinetic Jump Shoes", "Scav Hover-Kicks"]
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
            "formal_shoes": ["Diplomatic Fleet Dress Shoes", "High-Gloss Officer Brogues", "Nano-Fabric Loafers"],
            "oxfords": ["Fleet Admiral Dress Brogues", "Command Bridge Oxfords", "Synthetic Dress Brogues"],
            "spats_boots": ["Pressurized Space Gaiters", "Orbital Envoy Spats Boots", "Officer High Spats"],
            "high_heels": ["Zero-G Magnetic Heels", "Diplomatic Reception Pumps", "Hard-Light Stiletto Heels"],
            "platform_boots": ["Gravity-Compensated Platforms", "EVA Heavy Treads", "Station Industrial Platforms"],
            "mag_sneakers": ["Magnetic Deck Shoes", "Zero-G Vector Hover-Kicks", "Inertia-Lock Sneakers"]
        },
        "prefixes_t3": ["Titanium", "Composite", "Field", "Standard-Issue", "Carbon-Alloy", "Ceramic"],
        "prefixes_t2": ["Overcharged", "Plasma-Infused", "Hyper-Coil", "Nanite-Lined", "Quantum-Phase", "Cryo-Cooled"],
        "prefixes_t1": ["Supernova", "Singularity", "Antimatter", "Chrono-Phase", "Omni-Core", "Dark-Energy"],
        "suffixes_t2": ["of the Vanguard", "of Vector-Sync", "of Phase-Shift", "of the Orbital Marine"],
        "suffixes_t1": ["of Stellar Superiority", "of the Singularity Core", "of Cosmic Annihilation", "of Absolute Zero"]
    },
    "dark_fantasy": {
        "archetype_names": {
            "light_sneakers": ["Tomb-Stalker Slippers", "Soft-Step Ash Shoes", "Catacomb Runners"],
            "sandals": ["Ascetic Rags & Straps", "Monastery Penitent Sandals", "Blighted Leather Sliders"],
            "combat_boots": ["Grave-Watcher Stout Boots", "Inquisitor's Iron-Tipped Boots", "Executioner's Boots"],
            "heavy_greaves": ["Defiled Black-Plate Greaves", "Torturer's Spiked Sabatons", "Abyssal Iron Greaves"],
            "stealth_boots": ["Shadow-Stitched Funeral Slippers", "Night-Stalker Moccasins", "Ghost-Step Muffled Boots"],
            "riding_boots": ["Highwayman Black Boots", "Inquisitor's Stiff Riding Boots", "Blood-Stained Cavalier Boots"],
            "hazard_boots": ["Caustic Pyre-Warder Boots", "Corpse-Mire Boots", "Morgue Rubber Treads"],
            "formal_shoes": ["Mourning Velvet Slippers", "Funeral Director Oxfords", "Aristocrat's Black Pumps"],
            "oxfords": ["Mourning Black Brogues", "Inquisitor's Stitched Oxfords", "Catacomb Notary Shoes"],
            "spats_boots": ["Gothic Funeral Spats Boots", "Black Leather Spat Gaiters", "Grave-Digger Spats"],
            "high_heels": ["Vampiric Black Velvet Heels", "Mourning Veil Stilettos", "Blood-Stained Silk Pumps"],
            "platform_boots": ["Catacomb Iron-Sole Platforms", "Gothic Chunky Funeral Boots", "Torturer's Thick Soles"],
            "mag_sneakers": ["Shadow-Phase Soft Shoes", "Grave-Floating Slippers", "Wraith-Step Footwraps"]
        },
        "prefixes_t3": ["Blood-Stained", "Weathered", "Grim", "Jagged", "Ashen", "Roughspun", "Grave-Dug"],
        "prefixes_t2": ["Hex-Forged", "Cursed", "Grave-Tainted", "Sanguine", "Blight-Edged", "Bone-Carved", "Shadow-Veiled"],
        "prefixes_t1": ["Eldritch", "Abyssal-Vein", "Death-Lord's", "Cataclysmic", "Blood-Pact", "Marrow-Forged"],
        "suffixes_t2": ["of Torment", "of the Pale Moon", "of the Grave", "of Weeping Shadow", "of Hex-Binding"],
        "suffixes_t1": ["of Eternal Damnation", "of the Abyssal Void", "of Endless Agony", "of the Desolate Throne"]
    },
    "high_school": {
        "archetype_names": {
            "light_sneakers": ["Canvas School Sneakers", "Varsity Running Shoes", "Retro High-Tops"],
            "sandals": ["Beach Day Flip-Flops", "Fashion Buckled Sandals", "Poolside Slides"],
            "combat_boots": ["Rebel Combat Boots", "Thrifted Leather Stompers", "Rainy Day Work Boots"],
            "heavy_greaves": ["Hockey Protective Shin Guards", "Kendo Sune-Ate", "Catcher's Leg Guards"],
            "stealth_boots": ["Indoor Felt Slippers", "Silent Gym Moccasins", "Track & Field Soft Soles"],
            "riding_boots": ["Equestrian Club Riding Boots", "Winter Knee-High Leather Boots", "Rainy Riding Boots"],
            "hazard_boots": ["Chemistry Lab Safety Boots", "Yellow Rubber Rain Boots", "Heavy Snow Cleats"],
            "formal_shoes": ["Polished Uniform Penny Loafers", "Formal Ceremony Dress Shoes", "Academy Buckled Shoes"],
            "oxfords": ["Classic School Penny Loafers", "Prep Wingtip Oxfords", "Uniform Black Brogues"],
            "spats_boots": ["Retro Spats Ankle Boots", "Fashion Gaiter Boots", "Costume Drama Spats"],
            "high_heels": ["School Dance Kitten Heels", "Prom Night Stiletto Pumps", "Chic Platform Heels"],
            "platform_boots": ["Harajuku Platform Boots", "Goth Streetwear Platforms", "Chunky Skater Boots"],
            "mag_sneakers": ["Light-Up LED Kicks", "Roller-Wheel Skate Sneakers", "Air-Cushioned Runners"]
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
    
    # Non-armor shoes strictly keep base_dt = 0
    base_dt = int(round(base_data["base_dt"] * tier_mult)) if base_data["base_dt"] > 0 else 0
    type_dt = {k: int(round(v * tier_mult)) for k, v in base_data.get("type_dt", {}).items()} if base_dt > 0 else {}
    
    stat_mods: Dict[str, Any] = {}
    for k, v in base_data.get("stat_modifiers", {}).items():
        if isinstance(v, float):
            stat_mods[k] = round(v * tier_mult, 2)
        elif isinstance(v, int):
            scaled = int(round(v * tier_mult))
            # SPECIAL stats strictly capped at +1 maximum
            if k in ("cha", "per") and scaled > 1:
                scaled = 1
            stat_mods[k] = scaled
        else:
            stat_mods[k] = v
            
    if base_dt > 0:
        stat_mods["base_dt"] = base_dt

    scen_affixes = SCENARIO_SHOES_AFFIXES.get(scen_key, SCENARIO_SHOES_AFFIXES["fantasy"])
    genre_names = scen_affixes.get("archetype_names", {}).get(arch, [arch.replace("_", " ").title()])
    base_name = random.choice(genre_names)
    
    prefix_pool = scen_affixes.get(f"prefixes_t{item_tier}", ["Fine"])
    suffix_pool = scen_affixes.get(f"suffixes_t{item_tier}", ["of Swiftness"])
    
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
        "tags": copy.deepcopy(base_data["tags"]),
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
        
    stat_line = " | ".join(stat_parts) if stat_parts else "Standard Shoes"
    type_dt_str = ", ".join(f"{k.title()}: {v}" for k, v in type_dt.items() if v > 0) or "None"
    
    lines = [
        f"**{name}** (Tier {tier} Footwear — {arch})",
        f"• **Utility & Mobility**: {stat_line}",
        f"• **Type Resistances**: {type_dt_str}"
    ]
    return "\n".join(lines)
