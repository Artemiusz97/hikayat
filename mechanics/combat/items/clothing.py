from __future__ import annotations
import random
from typing import Dict, Any, Optional

from mechanics.combat.items.tags import derive_clothing_tags
from mechanics.combat.items.envelope import parse_item, serialize_item

# -----------------------------------------------------------------------------
# CIVILIAN CLOTHING ARCHETYPES
# Standard clothing provides mild social vibes, at most +1 to SPECIAL stats
# (strictly limited to CHA or PER), minor evasion (+1 to +3 EVA), and for
# heavier/durable fabrics, small DR% (physical/energy/elemental res).
# NON-ARMOR WEARABLES DO NOT GRANT DT (base_dt: 0, type_dt: {}).
# -----------------------------------------------------------------------------

CLOTHING_TOPS: Dict[str, Dict[str, Any]] = {
    # Existing core tops
    "casual_shirt": {
        "style": "casual",
        "social_modifiers": {"cha": 1, "eva": 2},
        "social_flags": ["comfortable"]
    },
    "blouse": {
        "style": "formal",
        "social_modifiers": {"cha": 1, "eva": 1},
        "social_flags": ["elegant"]
    },
    "school_uniform_top": {
        "style": "academic_uniform",
        "social_modifiers": {"cha": 1, "eva": 1},
        "social_flags": ["neat"]
    },
    "cardigan": {
        "style": "preppy",
        "social_modifiers": {"cha": 1, "eva": 1},
        "social_flags": ["comfortable", "academic"]
    },
    "school_vest": {
        "style": "academic_uniform",
        "social_modifiers": {"cha": 1, "eva": 1},
        "social_flags": ["neat", "academic"]
    },
    "jacket": {
        "style": "streetwear",
        "social_modifiers": {"cha": 1, "eva": 2},
        "social_flags": ["cool"]
    },
    "hoodie": {
        "style": "cozy",
        "social_modifiers": {"eva": 3},
        "social_flags": ["comfortable", "relaxed"]
    },
    "robe": {
        "style": "traditional",
        "social_modifiers": {"cha": 1},
        "social_flags": ["mystic"]
    },
    "tunic": {
        "style": "casual",
        "social_modifiers": {"cha": 1, "eva": 2},
        "social_flags": ["simple"]
    },

    # Steampunk & Period Tops
    "waistcoat": {
        "style": "period_formal",
        "social_modifiers": {"cha": 1},
        "social_flags": ["dapper", "tailored", "vintage"]
    },
    "corset": {
        "style": "period_couture",
        "social_modifiers": {"cha": 1, "eva": -1, "physical_res": 3},
        "social_flags": ["alluring", "structured", "imposing"]
    },
    "tailcoat": {
        "style": "period_formal",
        "social_modifiers": {"cha": 1},
        "social_flags": ["aristocratic", "regal", "ceremonial"]
    },
    "duster_coat": {
        "style": "outerwear",
        "social_modifiers": {"per": 1, "eva": 1, "physical_res": 4, "ice_res": 5},
        "social_flags": ["rugged", "mysterious", "weatherproof"]
    },
    "shawl": {
        "style": "period_casual",
        "social_modifiers": {"cha": 1, "eva": 2, "ice_res": 4},
        "social_flags": ["cozy", "graceful", "vintage"]
    },

    # Modern & Streetwear Tops
    "tank_top": {
        "style": "athletic",
        "social_modifiers": {"eva": 3},
        "social_flags": ["athletic", "breathable", "bold"]
    },
    "sweater": {
        "style": "cozy",
        "social_modifiers": {"cha": 1, "ice_res": 4},
        "social_flags": ["warm", "intellectual", "cozy"]
    },
    "leather_jacket": {
        "style": "streetwear",
        "social_modifiers": {"cha": 1, "physical_res": 5},
        "social_flags": ["rebellious", "tough", "cool"]
    },
    "blazer": {
        "style": "formal",
        "social_modifiers": {"cha": 1},
        "social_flags": ["professional", "authoritative"]
    },

    # Futuristic & Cyberpunk Tops
    "techwear_anorak": {
        "style": "techwear",
        "social_modifiers": {"eva": 2, "acc": 1, "energy_res": 3},
        "social_flags": ["waterproof", "tactical", "modular"]
    },
    "bodysuit_top": {
        "style": "futuristic",
        "social_modifiers": {"eva": 3},
        "social_flags": ["aerodynamic", "sleek", "ergonomic"]
    },
    "holo_jacket": {
        "style": "futuristic",
        "social_modifiers": {"cha": 1, "eva": 1, "energy_res": 4},
        "social_flags": ["luminous", "high_tech", "flamboyant"]
    },
    "cropped_uniform_top": {
        "style": "revealing",
        "social_modifiers": {"cha": 1, "eva": 2},
        "social_flags": ["provocative", "revealing", "rebellious"]
    },
    "unbuttoned_blouse": {
        "style": "revealing",
        "social_modifiers": {"cha": 1, "eva": 2},
        "social_flags": ["provocative", "revealing", "alluring"]
    }
}

CLOTHING_BOTTOMS: Dict[str, Dict[str, Any]] = {
    # Existing core bottoms
    "micro_pleated_skirt": {
        "style": "revealing",
        "social_modifiers": {"cha": 1, "eva": 2},
        "social_flags": ["provocative", "revealing", "short_hem"]
    },
    "trousers": {
        "style": "formal",
        "social_modifiers": {"cha": 1, "eva": 1},
        "social_flags": ["professional"]
    },
    "skirt": {
        "style": "casual",
        "social_modifiers": {"cha": 1, "eva": 2},
        "social_flags": ["breezy"]
    },
    "shorts": {
        "style": "athletic",
        "social_modifiers": {"eva": 3},
        "social_flags": ["active"]
    },
    "slacks": {
        "style": "academic_uniform",
        "social_modifiers": {"cha": 1, "eva": 1},
        "social_flags": ["neat"]
    },
    "jeans": {
        "style": "casual",
        "social_modifiers": {"eva": 2, "physical_res": 2},
        "social_flags": ["durable"]
    },

    # Steampunk & Period Bottoms
    "breeches": {
        "style": "period_formal",
        "social_modifiers": {"cha": 1, "eva": 2},
        "social_flags": ["vintage", "aristocratic", "riding"]
    },
    "bustle_skirt": {
        "style": "period_couture",
        "social_modifiers": {"cha": 1, "eva": -1, "physical_res": 3},
        "social_flags": ["magnificent", "voluminous", "stately"]
    },
    "culottes": {
        "style": "period_casual",
        "social_modifiers": {"cha": 1, "eva": 2},
        "social_flags": ["versatile", "breezy", "practical"]
    },
    "bloomers": {
        "style": "period_casual",
        "social_modifiers": {"eva": 2},
        "social_flags": ["comfortable", "whimsical", "historical"]
    },

    # Modern & Streetwear Bottoms
    "cargo_pants": {
        "style": "streetwear",
        "social_modifiers": {"per": 1, "eva": 1, "physical_res": 3},
        "social_flags": ["tactical", "multi_pocket", "rugged"]
    },
    "sweatpants": {
        "style": "athletic",
        "social_modifiers": {"eva": 3},
        "social_flags": ["relaxed", "comfortable", "flexible"]
    },
    "leggings": {
        "style": "athletic",
        "social_modifiers": {"eva": 3},
        "social_flags": ["streamlined", "flexible", "lightweight"]
    },
    "kilt": {
        "style": "traditional",
        "social_modifiers": {"cha": 1, "eva": 2},
        "social_flags": ["traditional", "breezy", "bold"]
    },

    # Futuristic & Cyberpunk Bottoms
    "techwear_joggers": {
        "style": "techwear",
        "social_modifiers": {"eva": 2, "acc": 1, "physical_res": 3},
        "social_flags": ["harness_strapped", "waterproof", "modular"]
    },
    "syn_leather_pants": {
        "style": "cyberpunk",
        "social_modifiers": {"cha": 1, "physical_res": 4},
        "social_flags": ["sleek", "edgy", "glossy"]
    }
}

SCHOOL_EXCLUSIVE_ARCHETYPES: frozenset[str] = frozenset({
    "school_uniform_top",
    "cropped_uniform_top",
    "school_vest",
    "micro_pleated_skirt",
    "cardigan",
    "unbuttoned_blouse",
})

NON_SCHOOL_CLOTHING_TOPS: tuple[str, ...] = tuple(
    k for k in CLOTHING_TOPS.keys() if k not in SCHOOL_EXCLUSIVE_ARCHETYPES
)

NON_SCHOOL_CLOTHING_BOTTOMS: tuple[str, ...] = tuple(
    k for k in CLOTHING_BOTTOMS.keys() if k not in SCHOOL_EXCLUSIVE_ARCHETYPES
)

# -----------------------------------------------------------------------------
# SCENARIO-SPECIFIC CLOTHING VOCABULARY & CUTS
# -----------------------------------------------------------------------------

SCENARIO_CLOTHING_AFFIXES: Dict[str, Dict[str, Any]] = {
    "fantasy": {
        "archetype_names": {
            # Tops
            "casual_shirt": ["Spun-Linen Shirt", "Peasant Undershirt", "Traveler's Blouse", "Linen Shirt"],
            "blouse": ["Embroidered Silk Blouse", "Courtly Chemise", "Lace Bodice", "Silk Blouse"],
            "school_uniform_top": ["Magic Academy Vestment", "Novice Scholar Shirt", "Apprentice Robelet"],
            "jacket": ["Leather Jerkin", "Embroidered Doublet", "Traveler's Mantle", "Hunter's Vest"],
            "hoodie": ["Traveler's Cloak-Hood", "Wayfarer's Cowl", "Forester's Poncho"],
            "robe": ["Mystic Silk Robes", "Sorcerer's Cassock", "Apprentice Frock", "Woolen Robe"],
            "tunic": ["Embroidered Tunic", "Woolen Tunic", "Peasant Smock", "Linen Tunic"],
            "waistcoat": ["Embroidered Velvet Vest", "Courtier's Waistcoat", "Noble Brocade Vest"],
            "corset": ["Lace-Up Maiden's Bodice", "Embroidered Velvet Stays", "Huntswoman's Leather Corset"],
            "tailcoat": ["Court Archduke's Doublet", "Grand Master's Frock Coat", "Royal Chamberlain Coat"],
            "duster_coat": ["Ranger's Weathered Duster", "Wayfarer's Heavy Mantle", "Warden's Travel Coat"],
            "shawl": ["Woolen Hearth-Shawl", "Elven-Woven Shoulder Wrap", "Silk Maiden's Mantilla"],
            "tank_top": ["Gladiator's Linen Undershirt", "Acrobat's Boddice Wrap", "Training Vest"],
            "sweater": ["Chunky Woolen Knit", "Highland Knitted Pullover", "Monastery Spun Sweater"],
            "leather_jacket": ["Reinforced Hide Jerkin", "Brawler's Studded Vest", "Grizzled Tracker's Coat"],
            "blazer": ["Guildmaster's Pressed Coat", "Chancellor's Trimmed Doublet", "Academy Master's Jacket"],
            "techwear_anorak": ["Enchanted Weather-Cloak", "Wind-Strider Poncho", "Runed Travel Anorak"],
            "bodysuit_top": ["Acrobat's Silk Leotard", "Shadow-Weave Undersuit", "Elven Skin-Tunic"],
            "holo_jacket": ["Glimmer-Silk Starlight Coat", "Prismatic Mirage Mantle", "Fey-Weave Glamour Robe"],
            # Bottoms
            "trousers": ["Traveler's Breeches", "Linen Hose", "Leather-Trimmed Trousers"],
            "skirt": ["Layered Wool Skirt", "Embroidered Peasant Skirt", "Maiden's Long Skirt"],
            "shorts": ["Riding Breeches", "Short Trousers", "Linen Knickers"],
            "slacks": ["Courtier's Slacks", "Gilded Hose", "Formal Trousers"],
            "jeans": ["Roughspun Canvas Breeches", "Toughhide Trousers", "Sturdy Work Pants"],
            "breeches": ["High-Waisted Riding Breeches", "Noble Velvet Court Breeches", "Cavalier Hose"],
            "bustle_skirt": ["Embroidered Royal Ballgown Skirt", "Tiered Velvet Crinoline", "Courtier's Brocade Skirt"],
            "culottes": ["Swashbuckler Split-Skirt", "Falconer's Divided Skirt", "Riding Culottes"],
            "bloomers": ["Lace-Trimmed Under-Bloomers", "Apprentice's Ruffled Pantaloons", "Homestead Bloomers"],
            "cargo_pants": ["Tracker's Pouch-Breeches", "Forager's Canvas Pants", "Wayfarer's Utility Hose"],
            "sweatpants": ["Monastery Drawstring Pants", "Fleece Rest-Hose", "Homestead Cozy Trousers"],
            "leggings": ["Silk Dance Tights", "Hunter's Deerskin Leggings", "Fey-Woven Hose"],
            "kilt": ["Highland Tartan Great Kilt", "Clansman's Pleated Kilt", "Warden's Belted Plaid"],
            "techwear_joggers": ["Scout's Buckled Canvas Pants", "Ranger's Multi-Strap Breeches", "Wind-Weave Trousers"],
            "syn_leather_pants": ["Fitted Beast-Hide Trousers", "Shadow-Thief Leather Pants", "Dark-Stalker Leathers"]
        },
        "prefixes": {
            3: ["Simple", "Spun-Linen", "Peasant", "Traveler's", "Sturdy", "Homestead", "Neat"],
            2: ["Enchanted", "Rune-Embroidered", "Gilded-Silk", "Mithril-Threaded", "Elven-Woven"],
            1: ["Masterwork", "Archon-Weave", "Celestial-Silk", "Ancient Royalty's", "Mythic"]
        },
        "suffixes": {
            2: ["of Elegance", "of the Court", "of Grace", "of Subtle Charms", "of the Woodland"],
            1: ["of the Archon", "of Royal Lineage", "of the Silver Dawn", "of Peerless Splendor"]
        }
    },
    "steampunk": {
        "archetype_names": {
            # Tops
            "casual_shirt": ["Work Shirt", "Cravat Shirt", "Linen Workshirt", "Collared Shirt"],
            "blouse": ["Corseted Blouse", "Lace-Trimmed Blouse", "High-Collar Blouse"],
            "school_uniform_top": ["Academy Vestment", "Apprentice Waistcoat", "Scholastic Smock"],
            "jacket": ["Tweed Jacket", "Brass-Buttoned Waistcoat", "Tailored Tailcoat", "Aviator Jacket"],
            "hoodie": ["Cowl Smock", "Grease-Monkey Shawl", "Boiler Cowl"],
            "robe": ["Alchemical Smock", "Aether-Weaver Robe", "Gentleman's Dressing Gown"],
            "tunic": ["Machinist Smock", "Brass-Trimmed Tunic", "Mechanic Vest"],
            "waistcoat": ["Brass-Buttoned Brocade Waistcoat", "Clockmaker's Doublet Vest", "Artificer's Damask Waistcoat"],
            "corset": ["Steel-Boned Leather Corset", "Riveted Copper Underbust Corset", "Clockwork Gear-Bodice"],
            "tailcoat": ["Victorian Silk Morning Coat", "Gentleman's Formal Tailcoat", "Baron's Double-Breasted Tailcoat"],
            "duster_coat": ["Aeronaut's Oilcloth Duster", "Steam-Train Stoker Greatcoat", "Inspector's Heavy Trenchcoat"],
            "shawl": ["Crocheted Smog-Shawl", "Victorian Woolen Wrap", "Lace Mantilla Capelet"],
            "tank_top": ["Boiler-Stoker Ribbed Undershirt", "Pugilist's Athletic Singlet", "Machinist Sleeveless Shirt"],
            "sweater": ["Cable-Knit Harbor Pullover", "Woolen Boiler-Tender Sweater", "High-Neck Smog Cardigan"],
            "leather_jacket": ["Aviator's Distressed Leather Bomber", "Riveted Aeronaut Vest", "Machinist Hide Coat"],
            "blazer": ["Steam-Guild Crest Blazer", "Patent Office Inspector Blazer", "Savile Row Pinstripe Blazer"],
            "techwear_anorak": ["Pneumatic-Vented Smock", "Vulcanized Rubber Raincoat", "Aetheric Bellows Pullover"],
            "bodysuit_top": ["Galvanic Insulated Under-Jumpsuit", "Aeronaut Flight Leotard", "Diver's Compression Top"],
            "holo_jacket": ["Aetheric Prismatic Greatcoat", "Voltaic Coil Trim Jacket", "Fluorescent Phosphor Vest"],
            # Bottoms
            "trousers": ["Pinstripe Trousers", "Pleated Slacks", "Woolen Trousers"],
            "skirt": ["Bustle Skirt", "Pleated Tweed Skirt", "A-Line Long Skirt"],
            "shorts": ["Aviator Knickers", "Mechanic Shorts", "Work Bermudas"],
            "slacks": ["Tailored Pinstripe Slacks", "Victorian Dress Slacks"],
            "jeans": ["Heavy Denim Dungarees", "Reinforced Canvas Trousers", "Oilcloth Pants"],
            "breeches": ["Victorian Riding Breeches", "Aeronaut High-Waist Jodhpurs", "Gentleman's Velvet Breeches"],
            "bustle_skirt": ["Steel-Caged Brocade Bustle Skirt", "Tiered Lace Victorian Crinoline", "Gothic Velvet Bustle"],
            "culottes": ["Velocipede Bicycling Culottes", "Split-Skirts for Aeronautics", "Pleated Canvas Culottes"],
            "bloomers": ["Ruffled Lace Pantaloons", "Victorian Gymnasium Bloomers", "Silk Under-Linen Bloomers"],
            "cargo_pants": ["Machinist Pouch-Pants", "Boiler-Room Utility Trousers", "Artificer Multi-Pocket Chinos"],
            "sweatpants": ["Stoker's Drawstring Lounge Pants", "Woolen Training Joggers", "Loom-Spun Hearth Pants"],
            "leggings": ["Galvanic Thermal Leggings", "Ribbed Woolen Tights", "Aeronaut Flight Under-Tights"],
            "kilt": ["Brass-Pinned Pleated Kilt", "Highland Artificer Tartan Kilt", "Heavy Tweed Belted Plaid"],
            "techwear_joggers": ["Harness-Rigged Clockwork Joggers", "Aether-Insulated Utility Pants", "Brass-Grommet Cargo Pants"],
            "syn_leather_pants": ["Oiled Hide Steampunk Leathers", "Riveted Biker Pants", "Boiler-Treated Leather Trousers"]
        },
        "prefixes": {
            3: ["Tweed", "Brass-Trimmed", "Copper-Lined", "Oilcloth", "Starch-Pressed", "Woolen", "Canvas"],
            2: ["Aether-Insulated", "Galvanic-Threaded", "Gilded-Brocade", "Pneumatic-Tailored", "Velvet-Lined"],
            1: ["Grand Victorian", "Master Artificer's", "Aether-Sovereign's", "Royal Academy", "Dreadnought-Loom"]
        },
        "suffixes": {
            2: ["of High Society", "of the Clockwork Guild", "of Steam & Velvet", "of the Aeronaut"],
            1: ["of the Grand Victorian Era", "of the Artificer Sovereign", "of the Imperial Gentry", "of the High Boiler"]
        }
    },
    "cyberpunk": {
        "archetype_names": {
            # Tops
            "casual_shirt": ["Compression Tee", "Mesh Undershirt", "Tech Tee", "Holo-Tee"],
            "blouse": ["Corporate Silk Shirt", "Sleek Bodysuit Top", "Synthetic Chiffon Blouse"],
            "school_uniform_top": ["MegaCorp Academy Top", "Prep Tech-Vest", "Corporate Cadet Shirt"],
            "jacket": ["Tech-Wear Bomber", "LED Windbreaker", "Holographic Duster", "Synth-Leather Jacket"],
            "hoodie": ["Oversized Tech-Hoodie", "Cowl Pullover", "Netrunner Shadow-Hoodie"],
            "robe": ["Monolithic Kimono", "Holo-Draped Haori", "Augment Technician Smock"],
            "tunic": ["Combat Undershirt", "Nanite Mesh Tunic", "Utility Vest"],
            "waistcoat": ["Kevlar-Lined Formal Vest", "Smart-Fiber Holo-Vest", "Corporate Executive Waistcoat"],
            "corset": ["Carbon-Ribbed Exoskeleton Corset", "Neon Underbust Synth-Corset", "Sub-Dermal Rig Bodice"],
            "tailcoat": ["Neo-Victorian Cyber Tailcoat", "Executive Evening Tux Coat", "Syndicate High-Collar Tails"],
            "duster_coat": ["Netrunner Longcoat", "Optic-Camo Trenchcoat", "Militech Heavy Weather Duster"],
            "shawl": ["Thermal-Weave Shoulder Wrap", "Reflective Cyber-Shawl", "Holo-Fringe Capelet"],
            "tank_top": ["Mesh Cyber-Tank", "Ribbed Crop Workout Top", "Netrunner Cooling Undershirt"],
            "sweater": ["Distressed Glitch-Knit Sweater", "Sub-Zero Thermal Pullover", "Oversized Cyber-Cardigan"],
            "leather_jacket": ["Armored Moto Biker Jacket", "Spiked Synth-Leather Jacket", "Rockstar Studded Bomber"],
            "blazer": ["Arasaka Tailored Cyber-Blazer", "Militech Monofilament Suit Jacket", "Corporate Slit Blazer"],
            "techwear_anorak": ["Molle-Strapped Carbon Anorak", "Waterproof Cyberdeck Pullover", "Ghost-Runner Shell Jacket"],
            "bodysuit_top": ["Nanite Compression Rashguard", "Sub-Dermal Biometric Top", "Reflective Street Bodysuit"],
            "holo_jacket": ["Neon-Piped Holographic Duster", "Photonic Glitch Bomber", "Prismatic LED Party Jacket"],
            # Bottoms
            "trousers": ["Cargo Joggers", "Tech-Wear Trousers", "Tactical Chinos"],
            "skirt": ["Pleated Cyber-Skirt", "Holo-Fringe Skirt", "Neoprene Mini-Skirt"],
            "shorts": ["Synthetic Track Shorts", "Cargo Utility Shorts", "Bicycle Tech-Shorts"],
            "slacks": ["Corporate Slacks", "Carbon-Weave Slacks", "Militech Tailored Pants"],
            "jeans": ["Acid-Wash Cyber-Denims", "Reinforced Biker Jeans", "Distressed Street Jeans"],
            "breeches": ["Cyber-Cavalry Fitted Pants", "High-Tech Equestrian Trousers", "Tactical Jodhpurs"],
            "bustle_skirt": ["Neon-Piped Cyber-Bustle", "Carbon-Ribbed Tiered Skirt", "Gothic-Lolita Cyber-Skirt"],
            "culottes": ["Wide-Leg Cyber-Culottes", "Pleated Tech-Wear Split Skirt", "Asymmetrical Flow Trousers"],
            "bloomers": ["Goth-Tech Ruffled Shorts", "Cyber-Harajuku Bloomers", "Padded Gym Bloomers"],
            "cargo_pants": ["Baggy Skater Cargo Pants", "Tactical Molle Leg-Rig Pants", "Netrunner Multi-Pouch Chinos"],
            "sweatpants": ["Tapered Cyber Joggers", "Oversized Street Track Pants", "Fleece Tech Sweatpants"],
            "leggings": ["Sub-Dermal Circuit Leggings", "Compression Run-Tights", "High-Gloss Neoprene Leggings"],
            "kilt": ["Punk Utility Buckled Kilt", "Cyber-Samurai Pleated Wrap", "Tactical Molle Kilt"],
            "techwear_joggers": ["Strapped Cyber-Cargo Joggers", "Magnetic-Buckled Ankle Pants", "Waterproof Shell Joggers"],
            "syn_leather_pants": ["Mirror-Finish Synth Trousers", "Skin-Tight Biker Leathers", "Chrome-Riveted Moto Pants"]
        },
        "prefixes": {
            3: ["Street-Grade", "Neo-Chic", "Carbon-Weave", "Synth-Leather", "Cargo", "Mesh", "Polymer"],
            2: ["Smart-Woven", "Holographic", "Thermal-Regulated", "Nanite-Laced", "EMP-Shielded", "Sub-Dermal"],
            1: ["Arasaka Executive", "High-Roller", "Black-ICE Woven", "Zero-Day Tailored", "Ghost-Protocol"]
        },
        "suffixes": {
            2: ["of the Street Runner", "of Neon Nights", "of the Nightclub", "of Sub-Dermal Flair"],
            1: ["of the High-Roller", "of Cyber-Dominance", "of the Sprawl Elite", "of the Black Market Syndicate"]
        }
    },
    "sci_fi": {
        "archetype_names": {
            # Tops
            "casual_shirt": ["Thermal Undershirt", "Crew Duty Shirt", "Synthetic Poly-Tee", "Fleet Casual Top"],
            "blouse": ["Diplomatic Envoy Blouse", "Officer's Silk Tunic", "Starch-Pressed Federation Shirt"],
            "school_uniform_top": ["Space Academy Cadet Top", "Orbital Cadet Jacket", "Starfleet Junior Uniform"],
            "jacket": ["Zero-G Flight Jacket", "Station Security Shell", "Solar-Sailor Windbreaker"],
            "hoodie": ["Habitation Pod Pullover", "Astro-Tech Fleece Hoodie", "Orbital Lounge Cowl"],
            "robe": ["Consular Velvet Robe", "Stellar Navigator Shroud", "Cryo-Attendant Gown"],
            "tunic": ["Engine Room Smock", "Bio-Lab Smock", "Colonial Pioneer Tunic"],
            "waistcoat": ["Ambassadorial Brocade Vest", "Naval Formal Waistcoat", "Starlight Officer Vest"],
            "corset": ["Pressure-Compensating Bodice", "G-Force Support Stays", "Sub-Orbital Formal Corset"],
            "tailcoat": ["Interstellar Gala Tailcoat", "Fleet Admiral's Ceremonial Coat", "First Contact Evening Tails"],
            "duster_coat": ["Off-World Dust Duster", "Deep-Space Drifter Trench", "Atmospheric Re-entry Coat"],
            "shawl": ["Thermal-Fleece Shoulder Shawl", "Solar-Reflective Wrap", "Cryo-Recovery Capelet"],
            "tank_top": ["Zero-G Gym Singlet", "Pressurized Workout Tank", "Crew Athletic Undershirt"],
            "sweater": ["Merino Space-Wool Sweater", "Sub-Orbital High-Neck Knit", "Quarters Comfy Cardigan"],
            "leather_jacket": ["Spacer Hide Flight Jacket", "Meteor-Salvager Bomber", "Corsair Heavy Leather Vest"],
            "blazer": ["Planetary Governor Blazer", "Starfleet Officer Blazer", "Trade Federation Dress Jacket"],
            "techwear_anorak": ["Atmospheric Hazard Anorak", "EVA Tethered Windbreaker", "Solar-Flare Shield Pullover"],
            "bodysuit_top": ["Sub-Orbital Compression Undersuit", "Nanite Bio-Telemetry Top", "Zero-G Pilot Leotard"],
            "holo_jacket": ["Photonic Prismatic Flight Jacket", "Chromashift Aurora Duster", "Hard-Light Accent Coat"],
            # Bottoms
            "trousers": ["Duty Uniform Trousers", "Fleet Creased Slacks", "Orbital Chinos"],
            "skirt": ["Federation Pleated Skirt", "Diplomatic A-Line Skirt", "Zero-G Magnetized Skirt"],
            "shorts": ["Station Athletic Shorts", "Pioneer Bermudas", "Habitat Rest Shorts"],
            "slacks": ["Starch-Pressed Deck Slacks", "Command Bridge Dress Slacks", "Colonial Officer Trousers"],
            "jeans": ["Heavy Work-Bay Canvas Pants", "Asteroid Miner Denims", "Reinforced Spacer Trousers"],
            "breeches": ["Space-Cavalry Jodhpurs", "Officer Riding Breeches", "Cadet High-Waist Pants"],
            "bustle_skirt": ["Grand Orbital Gala Bustle", "Tiered Fiber-Optic Crinoline", "Ambassadorial Stately Skirt"],
            "culottes": ["Zero-G Wide Split-Skirt", "Bridge Officer Culottes", "Airflow Station Culottes"],
            "bloomers": ["Bio-Habitat Lounge Bloomers", "Pressurized Ruffled Liners", "Quarters Cozy Bloomers"],
            "cargo_pants": ["Asteroid Miner Pouch Cargoes", "Drop-Ship Crew Pants", "Engineer Multi-Tool Pants"],
            "sweatpants": ["Habitat Lounge Joggers", "Fleet Athletic Sweatpants", "Off-Duty Fleece Pants"],
            "leggings": ["G-Force Anti-Blackout Leggings", "Thermal Deck Tights", "Seamless Space Tights"],
            "kilt": ["Clan MacStar Tartan Kilt", "Ceremonial Orbital Kilt", "Planetary Guard Plaid"],
            "techwear_joggers": ["Magnetic-Seam Cargo Joggers", "Pressurized Flight Trousers", "Atmospheric Drop Joggers"],
            "syn_leather_pants": ["Pressurized Synthetic Hide Pants", "Biker Spacer Leathers", "Smuggler Gloss Pants"]
        },
        "prefixes": {
            3: ["Standard-Issue", "Station-Grade", "Fleet-Spec", "Pressurized", "Thermal", "Polymer"],
            2: ["Quantum-Threaded", "Zero-G Woven", "Photonic", "Solar-Insulated", "Bio-Attuned"],
            1: ["Admiral's", "Stellar Sovereignty", "First-Contact", "Omega-Class", "Celestial-Loom"]
        },
        "suffixes": {
            2: ["of the Fleet Vanguard", "of the Colony", "of Zero-Gravity", "of Diplomatic Grace"],
            1: ["of Stellar Eminence", "of the Galactic Council", "of the Starborne Hegemony", "of Absolute Zero"]
        }
    },
    "nuclear_post_apocalypse": {
        "archetype_names": {
            # Tops
            "casual_shirt": ["Rad-Bleached Flannel", "Scavenger Scrap Shirt", "Burlap Undershirt", "Tattered Workshirt"],
            "blouse": ["Frayed Silk Chemise", "Weathered Lace Shirt", "Scavenged Satin Top"],
            "school_uniform_top": ["Pre-War Uniform Top", "Torn Cadet Vest", "Faded Campus Shirt"],
            "jacket": ["Spiked Scavenger Jacket", "Tire-Tread Reinforced Vest", "Wasteland Drifter Coat"],
            "hoodie": ["Scrap-Quilted Cowl", "Ash-Hood Poncho", "Rad-Storm Pullover"],
            "robe": ["Wasteland Cultist Robe", "Plague Shroud", "Mutant Hermit Garb"],
            "tunic": ["Burlap Smock", "Rough Hide Tunic", "Scrap-Stitched Top"],
            "waistcoat": ["Lead-Lined Scavenger Vest", "Pouch-Stitched Scrap Waistcoat", "Pre-War Tux Vest"],
            "corset": ["Bone-Ribbed Leather Bodice", "Scrap-Metal Boned Stays", "Raider Underbust Corset"],
            "tailcoat": ["Pre-War Baron's Tattered Tailcoat", "Grave-Lord's Frock Coat", "Charred Formal Tails"],
            "duster_coat": ["Rad-Wasteland Heavy Duster", "Highwayman Trenchcoat", "Scrap-Hide Longcoat"],
            "shawl": ["Ash-Covered Woolen Shawl", "Scrap-Blanket Poncho", "Tattered Burlap Wrap"],
            "tank_top": ["Scavenger Ribbed Crop Tank", "Dust-Stained Sleeveless Tee", "Pit-Fighter Undershirt"],
            "sweater": ["Moth-Eaten Heavy Knit", "Rad-Shelter Wool Pullover", "Frayed Cardigan"],
            "leather_jacket": ["Spiked Biker Scavenger Leather", "Road-Warrior Armored Jacket", "Distressed Rawhide Coat"],
            "blazer": ["Pre-War Mayor's Moth-Eaten Blazer", "Scavenged Pinstripe Coat", "Bunker Executive Jacket"],
            "techwear_anorak": ["Hazmat-Torn Storm Anorak", "Scavenged NBC Poncho", "Lead-Threaded Windbreaker"],
            "bodysuit_top": ["Old-World Pilot Compression Suit", "Vault-Dweller Under-Jumpsuit", "Rad-Treated Leotard"],
            "holo_jacket": ["Flickering Pre-War Holo-Jacket", "Glitch-Neon Scrap Duster", "Glow-In-The-Dark Rad Coat"],
            # Bottoms
            "trousers": ["Scavenged Dungarees", "Patched Canvas Trousers", "Ash-Stained Slacks"],
            "skirt": ["Tattered Rag Skirt", "Frayed Burlap Skirt", "Scrap-Hem Skirt"],
            "shorts": ["Cut-Off Scavenger Shorts", "Rough Burlap Shorts", "Torn Khaki Cutoffs"],
            "slacks": ["Stained Pre-War Slacks", "Worn-Out Formal Pants", "Patched Bunker Chinos"],
            "jeans": ["Rad-Bleached Denims", "Scrap-Patched Jeans", "Heavy Grease Pants"],
            "breeches": ["Old-World Riding Jodhpurs", "Scrap-Leather Breeches", "Reinforced Drifter Hose"],
            "bustle_skirt": ["Torn Victorian Lace Bustle", "Scrap-Metal Caged Skirt", "Wasteland Opera Skirt"],
            "culottes": ["Divided Scrap-Canvas Skirt", "Wasteland Riding Culottes", "Burlap Wide Pants"],
            "bloomers": ["Scrap-Linen Ruffled Bloomers", "Pre-War Gym Pantaloons", "Patched Cozy Liners"],
            "cargo_pants": ["Pouch-Lined Survivor Cargos", "Raider Multi-Pocket Pants", "Lead-Pocket Trousers"],
            "sweatpants": ["Ash-Stained Lounge Joggers", "Scavenger Fleece Pants", "Old-World Gym Sweats"],
            "leggings": ["Torn Thermal Tights", "Scrap-Woven Under-Tights", "Deerskin Scrap Leggings"],
            "kilt": ["Tattered Clan Tartan Kilt", "Spiked Raider Scrap Kilt", "Canvas Pleated Wrap"],
            "techwear_joggers": ["Lead-Lined Scavenger Joggers", "Strapped Gas-Mask Pants", "Vault Tactical Cargoes"],
            "syn_leather_pants": ["Grease-Treated Road Leathers", "Spiked Biker Pants", "Rough-Hide Scavenger Leathers"]
        },
        "prefixes": {
            3: ["Weathered", "Tattered", "Patched", "Roughspun", "Frayed", "Ash-Stained", "Scavenged"],
            2: ["Lead-Lined", "Rad-Hardened", "Bone-Adorned", "Scrap-Reinforced", "Spike-Studded"],
            1: ["Doomsday Relic", "Apex Scavenger's", "Wasteland Sovereign's", "Doomsday Heirloom", "Bunker-Heir's"]
        },
        "suffixes": {
            2: ["of the Wasteland Wanderer", "of the Road Warrior", "of the Oasis", "of Scavenger Pride"],
            1: ["of the Last Sovereign", "of the Nuclear Winter", "of the Undying Nomad", "of the Eternal Horizon"]
        }
    },
    "dark_fantasy": {
        "archetype_names": {
            # Tops
            "casual_shirt": ["Roughspun Shirt", "Scavenger Flannel", "Patched Linen Top", "Burlap Shirt"],
            "blouse": ["Mourner's Blouse", "Frayed Silk Shirt", "Weathered Chemise"],
            "school_uniform_top": ["Disheveled Cadet Top", "Frayed Uniform Vest", "Old-World School Top"],
            "jacket": ["Wasteland Duster", "Spiked Leather Vest", "Tattered Trenchcoat", "Scavenger Coat"],
            "hoodie": ["Scrap Cowl Hoodie", "Ragged Ash-Hood", "Survivor Poncho"],
            "robe": ["Cursed Cultist Robe", "Plague-Doc Smock", "Grave-Shrouded Cowl"],
            "tunic": ["Burlap Tunic", "Flesh-Stitched Surcoat", "Rough-Linen Smock"],
            "waistcoat": ["Mourning Velvet Waistcoat", "Inquisitor's Brocade Vest", "Gothic Damask Vest"],
            "corset": ["Gothic Bone-Stiffened Corset", "Vampiric Lace-Up Stays", "Black Velvet Mourning Bodice"],
            "tailcoat": ["Grave-Digger's Tailcoat", "Vampire Lord's Frock Coat", "Undertaker's Morning Coat"],
            "duster_coat": ["Plague Hunter's Heavy Duster", "Inquisitor's Greatcoat", "Graveyard Stalker Trench"],
            "shawl": ["Widow's Mourning Veil Shawl", "Black Woolen Shroud", "Tattered Raven-Feather Capelet"],
            "tank_top": ["Flagellant's Linen Wrap", "Pit-Brawler Undershirt", "Scourged Chest Band"],
            "sweater": ["Heavy Charcoal Knit", "Morgue-Keeper Woolen Pullover", "Gothic Knitted Shroud"],
            "leather_jacket": ["Beast-Hunter Leather Coat", "Blood-Stained Jerkin", "Grim Inquisitor Leathers"],
            "blazer": ["Gothic Magistrate Coat", "Occultist's Formal Blazer", "Dark-Chancellor Doublet"],
            "techwear_anorak": ["Alchemical Oilskin Smock", "Witch-Hunter Weather Cloak", "Blight-Shield Anorak"],
            "bodysuit_top": ["Cursed Flesh-Weave Leotard", "Night-Stalker Silk Undersuit", "Catacomb Diver Wrap"],
            "holo_jacket": ["Ghost-Light Shrouded Coat", "Will-O'-Wisp Luminescent Mantle", "Phantom Silk Duster"],
            # Bottoms
            "trousers": ["Scavenged Dungarees", "Patched Canvas Trousers", "Ash-Stained Slacks"],
            "skirt": ["Tattered Rag Skirt", "Frayed Peasant Skirt", "Scrap-Hem Skirt"],
            "shorts": ["Cut-Off Scavenger Shorts", "Rough Burlap Shorts"],
            "slacks": ["Stained Mortuary Slacks", "Worn-Out Formal Pants"],
            "jeans": ["Rad-Bleached Denims", "Scrap-Patched Jeans", "Heavy Grease Jeans"],
            "breeches": ["Inquisitor's Riding Breeches", "Mourning Velvet Hose", "Grave-Stalker Breeches"],
            "bustle_skirt": ["Tiered Black Lace Bustle", "Gothic Funeral Crinoline", "Vampiric Brocade Skirt"],
            "culottes": ["Occultist Divided Skirt", "Gothic Riding Culottes", "Dark Velvet Split-Skirt"],
            "bloomers": ["Widow's Ruffled Pantaloons", "Gothic Lace Bloomers", "Apprentice Shroud Bloomers"],
            "cargo_pants": ["Grave-Robber Pouch Pants", "Plague Doctor Utility Chinos", "Inquisitor Field Trousers"],
            "sweatpants": ["Penitent's Drawstring Pants", "Damp Crypt Fleece Joggers", "Lounge Shroud Trousers"],
            "leggings": ["Spider-Silk Black Tights", "Charcoal Weave Leggings", "Catacomb Stalker Hose"],
            "kilt": ["Blackwatch Tartan Kilt", "Gothic Buckled Plaid", "Mourning Belted Kilt"],
            "techwear_joggers": ["Witch-Hunter Multi-Strap Pants", "Alchemical Bellows Trousers", "Night-Crawl Cargoes"],
            "syn_leather_pants": ["Grave-Treated Hide Pants", "Blackened Beast-Skin Leathers", "Night-Blade Fitted Leathers"]
        },
        "prefixes": {
            3: ["Grim", "Blood-Stained", "Ashen", "Roughspun", "Grave-Dug", "Threadbare", "Charcoal"],
            2: ["Hex-Stitched", "Cursed-Silk", "Sanguine-Threaded", "Grave-Tainted", "Bone-Adorned", "Shadow-Veiled"],
            1: ["Eldritch", "Abyssal-Weave", "Death-Lord's", "Cataclysmic", "Blood-Pact", "Marrow-Forged"]
        },
        "suffixes": {
            2: ["of Mourning", "of the Catacombs", "of the Pale Moon", "of Weeping Shadow"],
            1: ["of the Desolate Throne", "of Eternal Requiem", "of the Grave Lord", "of Black Velvet"]
        }
    },
    "high_school": {
        "archetype_names": {
            # Tops (Whitelisted School & Athletic Garments - Zero Casualwear)
            "cardigan": ["School Knit Cardigan", "Academy Uniform Cardigan", "Pressed Student Cardigan", "Woolen School Cardigan"],
            "school_vest": ["Prep School Sweater Vest", "Uniform Plaid Waistcoat", "Academic Argyle Vest", "School V-Neck Vest"],
            "casual_shirt": ["Collared School Shirt", "Polo Uniform Shirt", "Button-Down Academy Shirt", "Pressed Uniform Polo"],
            "blouse": ["Pressed Sailor Blouse", "Chiffon School Blouse", "Ruffled Collar School Shirt", "Peter Pan Collar Uniform Blouse"],
            "school_uniform_top": ["School Blazer & Shirt", "Junior Sailor Uniform Top", "School Cardigan Uniform", "Academy Uniform Shirt"],
            "jacket": ["Varsity Letterman Jacket", "PE Tracksuit Jacket", "School Athletic Windbreaker", "School Sports Training Jacket"],
            "hoodie": ["School Fleece Pullover", "Campus Track Hoodie"],
            "robe": ["Graduation Robe", "Occult Club Smock"],
            "tunic": ["Art Club Smock", "Uniform Tunic Vest"],
            "waistcoat": ["Prep School Sweater Vest", "Uniform Plaid Waistcoat", "Academic Argyle Vest"],
            "corset": ["Gothic Academy Waist Cincher", "Uniform Bodice Vest"],
            "tailcoat": ["Orchestra Conductor Blazer", "Prom Tuxedo Blazer"],
            "duster_coat": ["Campus Trenchcoat", "School Raincoat"],
            "shawl": ["School Knit Shawl", "Uniform Shoulder Wrap"],
            "tank_top": ["Gym Class Uniform Tank", "PE Track Singlet", "School Athletic Singlet"],
            "sweater": ["Cable-Knit School Cardigan", "School V-Neck Uniform Sweater", "Academy Knit Pullover", "Uniform Vest & Cardigan"],
            "leather_jacket": ["Varsity Leather-Sleeve Jacket", "Club Leader Jacket"],
            "blazer": ["Academy Crest Blazer", "Navy Uniform Blazer", "Classic School Blazer", "Tailored Prep Blazer"],
            "techwear_anorak": ["School Athletic Windbreaker", "Campus Rain Anorak"],
            "bodysuit_top": ["Ballet Dance Leotard", "Swim Team Uniform Rashguard"],
            "holo_jacket": ["Science Club Safety Smock", "School Lab Jacket"],
            "cropped_uniform_top": ["Cropped Uniform Shirt", "Cropped Sailor Top", "Shortened Uniform Cardigan"],
            "unbuttoned_blouse": ["Unbuttoned Uniform Blouse", "Plunging Uniform Shirt", "Open-Collar School Top"],
            # Bottoms (Whitelisted School & Athletic Garments)
            "trousers": ["Pleated School Trousers", "School Uniform Trousers", "Navy Uniform Pants"],
            "skirt": ["Pleated Plaid Skirt", "A-Line School Uniform Skirt", "Classic Navy Pleated Skirt", "School Sailor Skirt"],
            "shorts": ["PE Athletic Shorts", "Track Gym Shorts", "School Training Shorts"],
            "slacks": ["Pressed Uniform Slacks", "Neat School Slacks", "Tailored School Slacks"],
            "jeans": ["Navy Uniform Slacks", "Tailored Campus Chinos"],
            "breeches": ["Academy Equestrian Breeches", "Formal Uniform Trousers"],
            "bustle_skirt": ["Formal Academy Pleated Skirt", "Uniform Pleated Long Skirt"],
            "culottes": ["School Uniform Culottes", "Academy Pleated Divided Skirt"],
            "bloomers": ["School PE Gym Bloomers", "Academy Athletic Shorts"],
            "cargo_pants": ["PE Uniform Utility Pants", "Campus Track Pants"],
            "sweatpants": ["PE Track Pants", "School Athletic Sweatpants", "Varsity Warm-Up Pants"],
            "leggings": ["School Uniform Opaque Tights", "PE Athletic Leggings"],
            "kilt": ["Academy Tartan Pleated Wrap", "School Tartan Uniform Kilt"],
            "techwear_joggers": ["School Track Trousers", "PE Utility Joggers"],
            "syn_leather_pants": ["Formal Uniform Slacks", "Tailored Academy Trousers"],
            "micro_pleated_skirt": ["Micro Pleated Plaid Skirt", "High-Slit Uniform Skirt", "Mini Sailor Skirt"]
        },
        "prefixes": {
            3: ["Clean", "Campus", "Everyday", "Neat", "Casual", "Standard-Issue", "Comfy"],
            2: ["Tailored", "Designer", "Varsity-Star", "Boutique", "Charming", "Preppy"],
            1: ["Class Valedictorian's", "Custom-Tailored", "Festival Champion's", "Prizewinning", "Heirloom"]
        },
        "suffixes": {
            2: ["of Youth", "of Style", "of the Honor Society", "of Friendship", "of Campus Trend"],
            1: ["of Everlasting Memories", "of Campus Royalty", "of the Grand Festival", "of the Valedictorian"]
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

def can_equip_item_in_scenario(item: Any, slot: str, scenario: str) -> tuple[bool, str]:
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

    if isinstance(item, (tuple, list)):
        item_dict: Dict[str, Any] = {
            "name": str(item[0]) if len(item) > 0 else "",
            "effect": str(item[1]) if len(item) > 1 else "",
            "item_type": slot,
        }
    elif isinstance(item, dict):
        item_dict = item
    else:
        item_dict = {"name": str(item or ""), "effect": "", "item_type": slot}

    # For Head, Gloves, Shoes: validate item archetype / metadata
    from mechanics.combat.equipment import parse_equipment_metadata
    meta = parse_equipment_metadata(item_dict) if item_dict else {}
    arch = str(meta.get("archetype") or "").strip().lower()
    base_dt = meta.get("base_dt", 0) or 0
    armor_type = str(meta.get("armor_type") or "").strip().lower()
    item_name = str(item_dict.get("name") or meta.get("name") or "").strip().lower()

    if slot == "Head":
        from mechanics.combat.items.headwear import NON_COMBAT_HEADWEAR_ARCHETYPES
        if arch and arch not in ("", "unknown"):
            is_combat = (arch not in NON_COMBAT_HEADWEAR_ARCHETYPES) or base_dt > 0 or armor_type in ("medium", "heavy")
        else:
            combat_head_keywords = (
                "helm", "greathelm", "sallet", "bascinet", "armet", "kabuto",
                "tactical visor", "gas mask", "combat helmet", "ballistic", "faceplate", "coif", "war helm",
            )
            is_combat = base_dt > 0 or armor_type in ("medium", "heavy") or any(k in item_name for k in combat_head_keywords)
        if is_combat:
            return False, (
                "🚫 Combat helmets and tactical headgear cannot be equipped in a slice-of-life setting.\n"
                "Only civilian headwear (caps, hoods, formal hats, beanies, berets) can be worn here."
            )
    elif slot == "Gloves":
        from mechanics.combat.items.gloves import NON_COMBAT_GLOVE_ARCHETYPES
        if arch and arch not in ("", "unknown"):
            is_combat = (arch not in NON_COMBAT_GLOVE_ARCHETYPES) or armor_type == "heavy" or base_dt > 0
        else:
            combat_glove_keywords = (
                "gauntlet", "cestus", "plated glove", "armored glove",
                "steel mitt", "iron cestus", "power fist", "spiked glove",
            )
            is_combat = base_dt > 0 or armor_type == "heavy" or any(k in item_name for k in combat_glove_keywords)
        if is_combat:
            return False, (
                "🚫 Heavy combat gauntlets cannot be equipped in a slice-of-life setting.\n"
                "Only civilian or light gloves can be worn here."
            )
    elif slot == "Shoes":
        from mechanics.combat.items.shoes import NON_COMBAT_SHOE_ARCHETYPES
        if arch and arch not in ("", "unknown"):
            is_combat = (arch not in NON_COMBAT_SHOE_ARCHETYPES) or armor_type == "heavy" or base_dt > 0
        else:
            combat_shoe_keywords = (
                "sabaton", "greave", "combat boot", "war boot", "iron boot", "steel boot",
                "spiked boot", "plated boot", "armored boot", "tactical boot", "trench boot",
                "steel-toe", "steel toe", "steel-cap", "steel-plated", "iron-tip", "iron-toed",
                "magnetic boot", "grav-anchor", "combat high-top",
            )
            is_combat = base_dt > 0 or armor_type == "heavy" or any(k in item_name for k in combat_shoe_keywords)
        if is_combat:
            return False, (
                "🚫 Combat boots and heavy greaves cannot be equipped in a slice-of-life setting.\n"
                "Only civilian footwear (sneakers, sandals, formal shoes, oxfords) can be worn here."
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
    elif any(w in scen for w in ("sci_fi", "scifi", "space")):
        return "sci_fi"
    elif any(w in scen for w in ("cyber", "hacker", "tech")):
        return "cyberpunk"
    elif any(w in scen for w in ("nuclear_post_apocalypse", "apocalypse", "postapoc", "wasteland")):
        return "nuclear_post_apocalypse"
    elif any(w in scen for w in ("dark_fantasy", "grimdark", "curse", "blood", "horror", "grave")):
        return "dark_fantasy"
    elif any(w in scen for w in ("high_school", "slice_of_life", "non_combat")):
        return "high_school"
    return "fantasy"

def is_tailed_race(race: str) -> bool:
    r = str(race or "").strip().lower()
    if not r:
        return False
    if r in ("human", "elf", "dwarf", "gnome", "halfling", "orc", "half-elf", "android", "synth", "cyborg", "clone"):
        return False
    tailed_keywords = (
        "beast", "furry", "anthro", "hybrid", "tail", "cat", "dog", "wolf", "fox", "fennec",
        "kitsune", "tiger", "lion", "cheetah", "leopard", "felid", "feline", "canid", "canine",
        "rabbit", "bunny", "mouse", "rat", "dragon", "lizard", "reptil", "snake", "scaly"
    )
    return any(k in r for k in tailed_keywords)


def generate_random_clothing(
    scenario: str = "fantasy",
    slot: str = "Top",
    tier: Optional[int] = None,
    archetype: Optional[str] = None,
    gender: Optional[str] = None,
    race: Optional[str] = None,
    allow_revealing: bool = False,
    quality_tier: Optional[str] = None,
    enchantment_tier: Optional[str] = None,
    is_faculty: bool = False,
    is_nsfw: bool = False,
) -> Dict[str, Any]:
    from mechanics.combat.equipment.tables import (
        LEGACY_TIER_TO_DUAL_AXIS,
        derive_legacy_tier,
        QUALITY_AFFINITY_BONUS,
        QUALITY_NAMES,
        ENCHANTMENT_NAMES,
    )
    from mechanics.combat.equipment.metadata import (
        roll_quality_tier,
        roll_enchantment_tier,
    )

    scen_key = normalize_clothing_scenario(scenario)
    affix_data = SCENARIO_CLOTHING_AFFIXES.get(scen_key, SCENARIO_CLOTHING_AFFIXES["fantasy"])
    is_male = str(gender or "").strip().lower() == "male"
    is_female = str(gender or "").strip().lower() == "female"
    has_tail = is_tailed_race(race)

    if tier in (1, 2, 3) and (not quality_tier or not enchantment_tier):
        def_q, def_e = LEGACY_TIER_TO_DUAL_AXIS.get(tier, ("regular", "none"))
        q_tier = quality_tier or def_q
        e_tier = enchantment_tier or def_e
    else:
        q_tier = quality_tier or roll_quality_tier()
        e_tier = enchantment_tier or ("none" if scen_key == "high_school" else roll_enchantment_tier())

    item_tier = tier if tier in (1, 2, 3) else derive_legacy_tier(q_tier, e_tier)

    chosen_archetype = archetype
    if slot == "Top":
        if chosen_archetype not in CLOTHING_TOPS or (scen_key != "high_school" and chosen_archetype in SCHOOL_EXCLUSIVE_ARCHETYPES):
            if scen_key == "high_school":
                if is_faculty:
                    chosen_archetype = random.choice(["blazer", "school_vest", "cardigan"]) if is_male else random.choice(["blazer", "blouse", "cardigan"])
                elif (is_nsfw or allow_revealing) and random.random() < 0.40 and not is_male:
                    chosen_archetype = random.choice(["cropped_uniform_top", "unbuttoned_blouse"])
                else:
                    chosen_archetype = random.choice([
                        "school_uniform_top", "blazer", "sweater", "waistcoat", "blouse", "cardigan", "school_vest"
                    ])
            else:
                chosen_archetype = random.choice(NON_SCHOOL_CLOTHING_TOPS)
        base_data = CLOTHING_TOPS[chosen_archetype]
    else:
        if chosen_archetype not in CLOTHING_BOTTOMS or (scen_key != "high_school" and chosen_archetype in SCHOOL_EXCLUSIVE_ARCHETYPES):
            if scen_key == "high_school":
                if is_faculty:
                    chosen_archetype = random.choice(["trousers", "slacks"]) if is_male else random.choice(["slacks", "skirt"])
                elif (is_nsfw or allow_revealing) and random.random() < 0.40 and is_female:
                    chosen_archetype = "micro_pleated_skirt"
                elif is_female:
                    chosen_archetype = random.choice(["skirt", "slacks", "trousers"])
                else:
                    chosen_archetype = random.choice(["trousers", "slacks"])
            else:
                chosen_archetype = random.choice(NON_SCHOOL_CLOTHING_BOTTOMS)
                if is_male and chosen_archetype in ("skirt", "micro_pleated_skirt"):
                    chosen_archetype = random.choice(["trousers", "slacks"])
        elif is_male and chosen_archetype in ("skirt", "micro_pleated_skirt"):
            chosen_archetype = "trousers"
        base_data = CLOTHING_BOTTOMS[chosen_archetype]

    # Resolve genre-specific base garment name
    genre_names = affix_data.get("archetype_names", {}).get(chosen_archetype)
    if genre_names:
        base_name = random.choice(genre_names)
    else:
        base_name = chosen_archetype.replace('_', ' ').title()

    # Calculate modifiers: standard regular clothes give at most +1 to SPECIAL stats (strictly CHA or PER).
    # NON-ARMOR WEARABLES DO NOT GRANT DT (base_dt: 0, type_dt: {}).
    mods = dict(base_data["social_modifiers"])
    tier_name = TIER_NAMES.get(item_tier, "Standard")
    prefixes = affix_data.get("prefixes", {})
    suffixes = affix_data.get("suffixes", {})

    if item_tier == 2:
        mods["eva"] = mods.get("eva", 0) + 1
        if "cha" in mods and mods["cha"] > 0:
            mods["cha"] = 1
        if "per" in mods and mods["per"] > 0:
            mods["per"] = 1
        p_list = prefixes.get(2, ["Tailored"])
        pref = random.choice(p_list)
        s_list = suffixes.get(2, [])
        if s_list and random.random() < 0.60:
            name = f"{pref} {base_name} {random.choice(s_list)}"
        else:
            name = f"{pref} {base_name}"
    elif item_tier == 1:
        mods["eva"] = mods.get("eva", 0) + 2
        if "cha" in mods and mods["cha"] > 0:
            mods["cha"] = 1
        if "per" in mods and mods["per"] > 0:
            mods["per"] = 1
        p_list = prefixes.get(1, ["Masterwork"])
        pref = random.choice(p_list)
        s_list = suffixes.get(1, [])
        if s_list and random.random() < 0.75:
            name = f"{pref} {base_name} {random.choice(s_list)}"
        else:
            name = f"{pref} {base_name}"
    else:
        if "cha" in mods and mods["cha"] > 1:
            mods["cha"] = 1
        if "per" in mods and mods["per"] > 1:
            mods["per"] = 1
        if random.random() < 0.40 and 3 in prefixes and prefixes[3]:
            pref = random.choice(prefixes[3])
            name = f"{pref} {base_name}"
        else:
            name = base_name

    # Gender adjustments
    if is_male and "skirt" in name.lower():
        name = name.replace("Skirt", "Trousers").replace("skirt", "trousers")

    # Race adjustments: accommodate tails for bottom items
    social_flags = list(base_data["social_flags"])
    if slot != "Top":
        if has_tail:
            if "tail" not in name.lower():
                name = f"Tail-Slotted {name}"
            if "tail_slotted" not in social_flags:
                social_flags.append("tail_slotted")
        else:
            if "tail-slotted" in name.lower():
                name = name.replace("Tail-Slotted ", "").replace("tail-slotted ", "").replace("Tail-slotted ", "")

    social_affinity_bonus = QUALITY_AFFINITY_BONUS.get(q_tier, 0)
    if item_tier == 1 and social_affinity_bonus < 4:
        social_affinity_bonus = 4
    elif item_tier == 2 and social_affinity_bonus < 2:
        social_affinity_bonus = 2

    metadata = {
        "name": name,
        "tier": item_tier,
        "quality_tier": q_tier,
        "enchantment_tier": e_tier,
        "quality_name": QUALITY_NAMES.get(q_tier, "Standard"),
        "enchantment_name": ENCHANTMENT_NAMES.get(e_tier, "Mundane"),
        "tier_name": tier_name,
        "slot": slot,
        "item_type": "Clothing",
        "archetype": chosen_archetype,
        "base_dt": 0,
        "dt": 0,
        "type_dt": {},
        "social_modifiers": mods,
        "stat_modifiers": dict(mods),
        "social_affinity_bonus": social_affinity_bonus,
        "social_flags": social_flags,
        "tags": derive_clothing_tags(style=base_data["style"], social_vibe=social_flags)
    }

    return {
        "name": name,
        "item_type": "Clothing",
        "slot": slot,
        "effect": serialize_item(metadata),
        "metadata": metadata,
        "slot_cost": 1
    }

def get_equipped_clothing_affinity_bonus(inventory: list | None) -> tuple[int, str]:
    """
    Returns (affinity_bonus, item_name) from the highest-tier equipped civilian garment/accessory.
    - Tier 3 Standard: +0 affinity
    - Tier 2 Stylish / Brand: +2 affinity
    - Tier 1 Luxury / Haute Couture: +4 affinity
    """
    if not isinstance(inventory, list) or not inventory:
        return 0, ""
    best_bonus = 0
    best_name = ""
    fashion_types = {"clothing", "top", "bottom", "accessory", "lingerie", "outerwear", "shoes"}
    for inv_item in inventory:
        if not isinstance(inv_item, dict):
            continue
        is_eq = bool(inv_item.get("equipped") or inv_item.get("is_equipped")) or bool(
            inv_item.get("slot")
            and str(inv_item.get("slot")).strip()
            in ("Top", "Bottom", "Outerwear", "Shoes", "Accessory 1", "Accessory 2", "Lingerie")
            and inv_item.get("equipped") is not False
            and inv_item.get("is_equipped") is not False
            and ("equipped" in inv_item or "is_equipped" in inv_item)
        )
        if not is_eq:
            continue
        meta = inv_item.get("metadata") if isinstance(inv_item.get("metadata"), dict) else None
        if not meta and inv_item.get("effect"):
            try:
                meta = parse_item(str(inv_item.get("effect") or ""))
            except Exception:
                meta = None
        bonus = 0
        if isinstance(meta, dict) and meta.get("social_affinity_bonus") is not None:
            try:
                bonus = int(meta.get("social_affinity_bonus") or 0)
            except (TypeError, ValueError):
                bonus = 0
        else:
            itype = str(inv_item.get("item_type") or (meta or {}).get("item_type") or "").strip().lower()
            if itype in fashion_types:
                t_val = int((meta or {}).get("tier") or inv_item.get("tier") or 3)
                if t_val == 1:
                    bonus = 4
                elif t_val == 2:
                    bonus = 2
        if bonus > best_bonus:
            best_bonus = min(4, bonus)
            best_name = str(inv_item.get("name") or (meta or {}).get("name") or "Stylish Outfit")
    return best_bonus, best_name


def format_clothing_card(metadata: Dict[str, Any]) -> str:
    name = metadata.get("name", "Clothing")
    tier_name = metadata.get("tier_name", "Standard")
    tags = metadata.get("tags")
    if isinstance(tags, dict):
        style = str(tags.get("style") or metadata.get("style") or "casual").title()
    else:
        style = str(metadata.get("style") or "casual").title()
    social_mods = metadata.get("social_modifiers") or metadata.get("stat_modifiers") or {}
    social_flags = ", ".join(metadata.get("social_flags", []))
    aff_bonus = int(metadata.get("social_affinity_bonus") or 0)

    mods_parts = []
    # SPECIAL stats
    for k in ("cha", "per", "eva", "acc"):
        v_num = float(social_mods.get(k) or 0)
        if v_num > 0:
            v_disp = int(v_num) if v_num.is_integer() else v_num
            mods_parts.append(f"+{v_disp} {k.upper()}")
        elif v_num < 0:
            v_disp = int(v_num) if v_num.is_integer() else v_num
            mods_parts.append(f"{v_disp} {k.upper()}")
    # Damage reduction percentages (DR%)
    res_tuples = (
        ("physical_res", "Phys DR"), ("energy_res", "Energy DR"), ("fire_res", "Fire DR"),
        ("ice_res", "Cold DR"), ("shock_res", "Shock DR"), ("poison_res", "Poison DR"),
        ("holy_res", "Holy DR"), ("dark_res", "Dark DR"), ("earth_res", "Earth DR"),
        ("water_res", "Water DR"), ("wind_res", "Wind DR")
    )
    for r_k, r_label in res_tuples:
        r_val = float(social_mods.get(r_k) or 0)
        if r_val > 0:
            r_disp = int(r_val) if r_val.is_integer() else r_val
            mods_parts.append(f"+{r_disp}% {r_label}")

    mods_str = ", ".join(mods_parts) or "None"

    lines = [
        f"**{name}** ({tier_name})",
        f"**Slot:** {metadata.get('slot', 'Clothing')} • **Style:** {style}",
        f"**Modifiers:** {mods_str}",
    ]
    if aff_bonus > 0:
        lines.append(f"**Social Impression:** +{aff_bonus} Affinity")
    lines.append(f"**Vibe:** {social_flags}")
    return "\n".join(lines)
