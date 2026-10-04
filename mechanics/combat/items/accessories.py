from __future__ import annotations
import random
from typing import Dict, Any, Optional

from mechanics.combat.items.envelope import serialize_item

ACCESSORY_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "ring": {
        "slot": "Accessory 1",
        "base_matk": 8, "base_macc": 4, "matk_pct": 0.05,
        "tags": {"social_flags": ["ornamental"], "stat_bonuses": ["matk", "macc", "matk_pct"]}
    },
    "amulet": {
        "slot": "Accessory 2",
        "base_dt": 2,
        "type_dt": {"magical": 6, "holy": 4, "dark": 4},
        "omni_res": 6,
        "base_eva": 2,
        "tags": {"social_flags": ["mystic"], "stat_bonuses": ["base_dt", "magic_dt", "omni_res", "eva"]}
    },
    "talisman": {
        "slot": "Accessory 3",
        "base_dt": 1,
        "type_dt": {"magical": 4},
        "matk_pct": 0.04,
        "base_matk": 6, "tags": {"social_flags": ["arcane"], "stat_bonuses": ["matk_pct", "base_dt", "magic_dt"]}
    },
    "bracelet": {
        "slot": "Accessory 4",
        "base_dt": 2,
        "type_dt": {"slashing": 3, "stabbing": 3},
        "physical_res": 5,
        "base_acc": 4,
        "tags": {"social_flags": ["fashionable"], "stat_bonuses": ["base_dt", "physical_res", "acc"]}
    }
}

NON_COMBAT_ACCESSORY_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "school_ribbon": {
        "slot": "Accessory 1",
        "base_cha": 2, "base_eva": 1,
        "tags": {"social_flags": ["uniform", "neat"], "stat_bonuses": ["cha", "eva"]}
    },
    "enamel_badge": {
        "slot": "Accessory 2",
        "base_cha": 1, "base_luck": 1,
        "tags": {"social_flags": ["club", "student_council"], "stat_bonuses": ["cha", "luck"]}
    },
    "smartwatch": {
        "slot": "Accessory 3",
        "base_int": 2, "base_acc": 2,
        "tags": {"social_flags": ["tech", "modern"], "stat_bonuses": ["int", "acc"]}
    },
    "charm_keychain": {
        "slot": "Accessory 4",
        "base_luck": 2,
        "tags": {"social_flags": ["cute", "lucky"], "stat_bonuses": ["luck"]}
    },
    "earbuds": {
        "slot": "Accessory 1",
        "base_eva": 1, "base_cha": 1,
        "tags": {"social_flags": ["music", "chill"], "stat_bonuses": ["eva", "cha"]}
    }
}

SCENARIO_ACCESSORY_AFFIXES: Dict[str, Dict[str, Any]] = {
    "fantasy": {
        "archetype_names": {
            "ring": ["Mithril Signet Ring", "Band of Arcane Focus", "Gilded Ruby Ring"],
            "amulet": ["Moonstone Amulet", "Sun-Blessed Pendant", "Aegis Medallion"],
            "talisman": ["Runic Bone Talisman", "Star-Carved Talisman", "Enchanted Fetish"],
            "bracelet": ["Braided Silver Bangle", "Gilded Dragon Bracelet", "Iron Warded Torc"]
        },
        "prefixes_t3": ["Polished", "Silver", "Carved", "Gleaming", "Apprentice's", "Woven"],
        "prefixes_t2": ["Runic", "Gilded", "Mithril", "Moonlit", "Star-Forged", "Spell-Bound"],
        "prefixes_t1": ["Sunfire", "Dragon-Eye", "Celestial", "Abyssal-Core", "God-King's"],
        "suffixes_t2": ["of Focus", "of Warding", "of the Sage", "of Clear Sight", "of Fortune"],
        "suffixes_t1": ["of Archmage Dominion", "of Divine Grace", "of Eternal Dawn", "of Immortality"]
    },
    "steampunk": {
        "archetype_names": {
            "ring": ["Brass Gear-Ring", "Copper Wire Band", "Aether-Cavitating Ring"],
            "amulet": ["Chrono-Dial Locket", "Aetheric Pressure Gauge", "Miniature Galvanic Gyro"],
            "talisman": ["Perpetual-Motion Pendulum", "Clockwork Escapement Charm", "Voltaic Spark Token"],
            "bracelet": ["Riveted Copper Manacle-Band", "Interlocked Gear Bracelet", "Brass Piston Wristlet"]
        },
        "prefixes_t3": ["Brass-Rimmed", "Copper-Wired", "Machinist's", "Steam-Vented", "Rivet-Bound", "Standard"],
        "prefixes_t2": ["Galvanic", "Aether-Tuned", "Pneumatic", "Boiler-Forged", "Voltaic", "Clockwork-Laced"],
        "prefixes_t1": ["Perpetual-Motion", "Grand Victorian", "Tesla's Masterwork", "Dreadnought's", "Aether-Sovereign's"],
        "suffixes_t2": ["of the Piston", "of Valve Exhaust", "of Copper Induction", "of Cogwheel Precision"],
        "suffixes_t1": ["of Endless Pressure", "of the Brass Sovereign", "of Aetheric Synthesis", "of Chrono-Control"]
    },
    "cyberpunk": {
        "archetype_names": {
            "ring": ["Subdermal Micro-Transceiver Ring", "Biometric Smart-Ring", "Carbon-Weave Band"],
            "amulet": ["Neural Datajack Pendant", "Encrypted Memory Core Locket", "Holographic Dog-Tag"],
            "talisman": ["Overclocked ICE-Breaker Token", "Glitch-Matrix Charm", "Rogue AI Shard"],
            "bracelet": ["Smart-Link Sensory Cuff", "Haptic Feedback Wristband", "Biomonitor Bangle"]
        },
        "prefixes_t3": ["Street-Grade", "Mil-Spec", "Carbon-Weave", "Chrome", "Reinforced", "Standard-Issue"],
        "prefixes_t2": ["Overclocked", "Smart-Linked", "High-Frequency", "Sub-Dermal", "Nanite-Laced", "Thermal-Chambered"],
        "prefixes_t1": ["Arasaka Prototype", "Black-ICE", "Zero-Day", "Militech Apex", "Ghost-Protocol", "Hyper-Threaded"],
        "suffixes_t2": ["of Data-Siphon", "of System-Sync", "of the Netrunner", "of Ghost-Routing"],
        "suffixes_t1": ["of Cyber-Dominance", "of Impenetrable ICE", "of the Apex Syndicate", "of Omnipresence"]
    },
    "nuclear_post_apocalypse": {
        "archetype_names": {
            "ring": ["Bent Copper-Pipe Ring", "Scrap-Wire Coiled Ring", "Flattened Bullet Band"],
            "amulet": ["Geiger-Counter Needle Locket", "Lead-Cased Glow Capsule", "Mutant-Fang Necklace"],
            "talisman": ["Bottlecap Lucky Charm", "Radioactive Trinket", "Scavenged Relic Token"],
            "bracelet": ["Barbed-Wire Bangle", "Watch-Part Scrap Cuff", "Tire-Bead Wristlet"]
        },
        "prefixes_t3": ["Scrap-Metal", "Rusty", "Jury-Rigged", "Weathered", "Makeshift", "Spiked", "Lead-Lined"],
        "prefixes_t2": ["Rad-Hardened", "Bio-Toxic", "Reinforced-Steel", "Wasteland-Master", "Gamma-Tuned", "Spike-Studded"],
        "prefixes_t1": ["Doomsday", "Nuclear-Winter", "Alpha-Mutant", "Apex-Scavenger", "God-Corpse", "Irradiated"],
        "suffixes_t2": ["of the Scavenger", "of Rust & Ruin", "of the Raider", "of the Fallout Shelter"],
        "suffixes_t1": ["of Total Extinction", "of the Wasteland Nomad", "of the Radioactive Storm", "of Endless Survival"]
    },
    "sci_fi": {
        "archetype_names": {
            "ring": ["Grav-Stabilizer Ring", "Sub-Space Resonator Band", "Quantum-Entangled Ring"],
            "amulet": ["Tachyon Field Pendant", "Stellar Navigation Core", "Antimatter Containment Locket"],
            "talisman": ["Psionic Focusing Shard", "Nanite Swarm Beacon", "Hyper-Space Token"],
            "bracelet": ["Omni-Tool Hard-Light Cuff", "Phase-Shift Wrist-Emitter", "Inertial Damper Bangle"]
        },
        "prefixes_t3": ["Titanium", "Composite", "Field", "Standard-Issue", "Carbon-Alloy", "Ceramic"],
        "prefixes_t2": ["Overcharged", "Plasma-Infused", "Hyper-Coil", "Nanite-Lined", "Quantum-Phase", "Cryo-Cooled"],
        "prefixes_t1": ["Supernova", "Singularity", "Antimatter", "Chrono-Phase", "Omni-Core", "Dark-Energy"],
        "suffixes_t2": ["of the Vanguard", "of Vector-Sync", "of Phase-Shift", "of the Orbital Marine"],
        "suffixes_t1": ["of Stellar Superiority", "of the Singularity Core", "of Cosmic Synthesis", "of Absolute Zero"]
    },
    "dark_fantasy": {
        "archetype_names": {
            "ring": ["Bone-Carved Signet Ring", "Tarnished Black-Iron Band", "Vampiric Blood-Gem Ring"],
            "amulet": ["Marrow-Hungry Periapt", "Hex-Stitched Shrunken Head Pendant", "Weeping Eye Locket"],
            "talisman": ["Desolate Soul-Bound Effigy", "Grave-Soil Cloth Charm", "Torturer's Iron Nail"],
            "bracelet": ["Black-Thorn Torc", "Chained Vertebrae Cuff", "Blight-Marked Iron Bangle"]
        },
        "prefixes_t3": ["Blood-Stained", "Weathered", "Grim", "Jagged", "Ashen", "Roughspun", "Grave-Dug"],
        "prefixes_t2": ["Hex-Forged", "Cursed", "Grave-Tainted", "Sanguine", "Blight-Edged", "Bone-Carved", "Shadow-Veiled"],
        "prefixes_t1": ["Eldritch", "Abyssal-Vein", "Death-Lord's", "Cataclysmic", "Blood-Pact", "Marrow-Forged"],
        "suffixes_t2": ["of Torment", "of the Pale Moon", "of the Grave", "of Weeping Shadow", "of Hex-Binding"],
        "suffixes_t1": ["of Eternal Damnation", "of the Abyssal Void", "of Endless Agony", "of the Desolate Throne"]
    },
    "high_school": {
        "archetype_names": {
            "school_ribbon": ["Silk Uniform Ribbon", "Honor Student Blazer Tie", "Cheerleader Hair Ribbon"],
            "enamel_badge": ["Student Council Enamel Pin", "Science Club Merit Badge", "Festival Committee Pin"],
            "smartwatch": ["Modern Digital Smartwatch", "Fitness Tracker Wristband", "GPS Smart-Band"],
            "charm_keychain": ["Cute Mascot Keychain", "Anime Character Phone Charm", "Lucky Shinto Shrine Charm"],
            "earbuds": ["Wireless Bluetooth Earbuds", "Noise-Cancelling Earphones", "Sports Audio Buds"]
        },
        "prefixes_t3": ["Standard", "Student", "Clean", "Campus", "Everyday", "Casual", "School"],
        "prefixes_t2": ["Varsity", "Tailored", "Customized", "Honors", "Trendy", "Preppy", "Club-Captain's"],
        "prefixes_t1": ["Student Council President's", "Valedictorian's", "Championship", "Festival Champion's", "Campus Legend's"],
        "suffixes_t2": ["of the Study Group", "of Friendship", "of Style", "of Youth", "of the Honor Roll"],
        "suffixes_t1": ["of Everlasting Memories", "of the Grand Festival", "of Pure Romance", "of the Campus Legend"]
    }
}

def normalize_accessory_scenario(scenario: str) -> str:
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

def generate_random_equipment(scenario: str = "fantasy", slot: str = "Accessory 1", tier: Optional[int] = None) -> Dict[str, Any]:
    item_tier = tier if tier in (1, 2, 3) else roll_tier()
    scen_key = normalize_accessory_scenario(scenario)
    
    try:
        from scenario_data import is_non_combat_scenario
        is_non_combat = is_non_combat_scenario(scenario) or scen_key == "high_school"
    except Exception:
        is_non_combat = scen_key == "high_school"
        
    pool_dict = NON_COMBAT_ACCESSORY_ARCHETYPES if is_non_combat else ACCESSORY_ARCHETYPES
    
    # Check if any archetypes match the requested slot
    matching_archs = [a for a, d in pool_dict.items() if d.get("slot") == slot]
    if matching_archs:
        archetype = random.choice(matching_archs)
    else:
        archetype = random.choice(list(pool_dict.keys()))
        
    base_data = pool_dict[archetype]
    actual_slot = slot if slot.startswith("Accessory") else base_data.get("slot", "Accessory 1")
    
    tier_mult = 1.0 if item_tier == 3 else (1.20 if item_tier == 2 else 1.45)
    base_dt = int(round(base_data.get("base_dt", 0) * tier_mult))
    type_dt = {k: int(round(v * tier_mult)) for k, v in base_data.get("type_dt", {}).items()}

    stat_mods: Dict[str, Any] = {}
    for k, v in base_data.items():
        if k in ("slot", "tags", "type_dt"):
            continue
        if k == "base_dt":
            stat_mods["base_dt"] = base_dt
        elif k.startswith("base_"):
            stat_mods[k.replace("base_", "")] = int(round(v * tier_mult))
        elif isinstance(v, (int, float)):
            stat_mods[k] = round(v * tier_mult, 2) if isinstance(v, float) else int(round(v * tier_mult))

    scen_affixes = SCENARIO_ACCESSORY_AFFIXES.get(scen_key, SCENARIO_ACCESSORY_AFFIXES["fantasy"])
    genre_names = scen_affixes.get("archetype_names", {}).get(archetype, [archetype.replace("_", " ").title()])
    base_name = random.choice(genre_names)
    
    prefix_pool = scen_affixes.get(f"prefixes_t{item_tier}", ["Fine"])
    suffix_pool = scen_affixes.get(f"suffixes_t{item_tier}", ["of Focus"])
    
    prefix = random.choice(prefix_pool)
    if item_tier == 3:
        name = f"{prefix} {base_name}"
    else:
        suffix = random.choice(suffix_pool)
        name = f"{prefix} {base_name} {suffix}"
        
    metadata = {
        "name": name,
        "tier": item_tier,
        "slot": actual_slot,
        "item_type": "Accessory",
        "archetype": archetype,
        "base_dt": base_dt,
        "type_dt": type_dt,
        "tags": base_data["tags"],
        "stat_modifiers": stat_mods
    }
    
    return {
        "name": name,
        "item_type": "Accessory",
        "slot": actual_slot,
        "effect": serialize_item(metadata),
        "metadata": metadata,
        "slot_cost": 1
    }

def format_equipment_card(metadata: Dict[str, Any]) -> str:
    tier = metadata.get("tier", 3)
    name = metadata.get("name", "Accessory")
    slot = metadata.get("slot", "Accessory")
    arch = metadata.get("archetype", "accessory").replace("_", " ").title()
    base_dt = metadata.get("base_dt", 0)
    stats = metadata.get("stat_modifiers", {})
    
    stat_parts = []
    if base_dt > 0:
        stat_parts.append(f"🛡️ DT +{base_dt}")
    for k, v in stats.items():
        if k in ("base_dt",):
            continue
        if k.endswith("_pct"):
            stat_parts.append(f"{k.replace('_pct', '').upper()} +{int(round(v * 100))}%")
        elif k.endswith("_res"):
            stat_parts.append(f"{k.replace('_res', '').title()} DR +{v}%")
        else:
            stat_parts.append(f"{k.upper()} +{v}")
            
    stat_str = " • ".join(stat_parts) if stat_parts else "Minor passive focus"
    
    lines = [
        f"**{name}** (Tier {tier})",
        f"**Slot:** {slot} • **Archetype:** {arch}",
        f"**Modifiers:** {stat_str}"
    ]
    return "\n".join(lines)
