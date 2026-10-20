from __future__ import annotations
import random
from typing import Dict, Any, Optional

from mechanics.combat.items.tags import derive_clothing_tags
from mechanics.combat.items.envelope import serialize_item

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
    }
}

CLOTHING_BOTTOMS: Dict[str, Dict[str, Any]] = {
    # Existing core bottoms
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
            # Tops
            "casual_shirt": ["Graphic Tee", "Polo Shirt", "Button-Down Casual Shirt", "Flannel Shirt"],
            "blouse": ["Pressed Sailor Blouse", "Chiffon Blouse", "Ruffled Collar Shirt"],
            "school_uniform_top": ["School Blazer & Shirt", "Junior Sailor Top", "School Cardigan"],
            "jacket": ["Varsity Letterman Jacket", "Denim Jacket", "Tracksuit Zip-Up", "Bomber Jacket"],
            "hoodie": ["Oversized Pastel Hoodie", "Campus Logo Hoodie", "Cozy Fleece Pullover"],
            "robe": ["Dorm Bathrobe", "Occult Club Robe", "Festival Yukata"],
            "tunic": ["Art Club Smock", "Longline Tunic Shirt"],
            "waistcoat": ["Prep School Sweater Vest", "Uniform Plaid Waistcoat", "Argyle Knitted Vest"],
            "corset": ["Fashion Belt Bodice", "Gothic Lolita Underbust Stays", "Festival Ribbon Corset"],
            "tailcoat": ["Orchestra Conductor Tails", "Prom Formal Tuxedo Coat", "Drama Club Tailcoat"],
            "duster_coat": ["Longline Rainy-Day Trench", "Vintage Thrifted Duster", "Detective Club Overcoat"],
            "shawl": ["Schoolgirl Knit Capelet", "Winter Wool Shawl", "Pastel Shoulder Wrap"],
            "tank_top": ["Gym Class Tank Top", "Summer Ribbed Crop Top", "Track & Field Singlet"],
            "sweater": ["Cable-Knit School Cardigan", "Oversized Cream Pullover", "Pastel V-Neck Knit"],
            "leather_jacket": ["Rebel Biker Leather Jacket", "Thrifted Moto Jacket", "Rock Band Studded Jacket"],
            "blazer": ["Academy Crest Blazer", "Navy Prep Blazer", "Classic Navy Uniform Blazer"],
            "techwear_anorak": ["Rainy Day Windbreaker", "Hiking Club Anorak", "Urban Streetwear Pullover"],
            "bodysuit_top": ["Ballet Dance Leotard", "Swim Team Rashguard", "Gymnastics Compression Top"],
            "holo_jacket": ["Festival LED Windbreaker", "Cyber-Harajuku Glow Jacket", "Pop Idol Concert Coat"],
            # Bottoms
            "trousers": ["Chino Pants", "Pleated School Trousers", "Casual Khakis"],
            "skirt": ["Pleated Plaid Skirt", "Tennis Skirt", "Denim Mini Skirt", "A-Line School Skirt"],
            "shorts": ["Athletic Gym Shorts", "Denim Shorts", "Bicycle Shorts"],
            "slacks": ["Pressed Uniform Slacks", "Neat Dress Slacks"],
            "jeans": ["Skinny Blue Jeans", "Ripped Denim Jeans", "Straight-Leg Jeans"],
            "breeches": ["Equestrian Club Jodhpurs", "Retro Knickerbockers", "Costume Drama Breeches"],
            "bustle_skirt": ["Lolita Tiered Frill Skirt", "Festival Maid Costume Bustle", "Gothic Lolita Skirt"],
            "culottes": ["Pleated High-Waist Culottes", "Flowing Wide-Leg Pants", "Summer Linen Culottes"],
            "bloomers": ["Retro Gym Bloomers", "Lolita Lace Under-Shorts", "Cozy Pajama Bloomers"],
            "cargo_pants": ["Skater Baggy Cargo Pants", "Street-Style Pocket Pants", "Canvas Utility Chinos"],
            "sweatpants": ["Varsity Track Sweatpants", "Oversized Cotton Joggers", "Gym Fleece Sweats"],
            "leggings": ["Yoga Dance Tights", "Opaque School Tights", "Athletic Stretch Leggings"],
            "kilt": ["Punk Pleated Wrap Kilt", "School Tartan Kilt", "Festival Scottish Kilt"],
            "techwear_joggers": ["Street-Chic Buckled Joggers", "Harajuku Tech Pants", "Skater Utility Trousers"],
            "syn_leather_pants": ["Rock Club Faux-Leather Pants", "Moto Street Leathers", "Goth Skinny Leather Pants"]
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

def can_equip_item_in_scenario(item: Dict[str, Any], slot: str, scenario: str) -> tuple[bool, str]:
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

    # For Head, Gloves, Shoes: validate item archetype / metadata
    from mechanics.combat.equipment import parse_equipment_metadata
    meta = parse_equipment_metadata(item) if item else {}
    arch = meta.get("archetype", "")
    base_dt = meta.get("base_dt", 0)
    armor_type = meta.get("armor_type", "")

    if slot == "Head":
        from mechanics.combat.items.headwear import NON_COMBAT_HEADWEAR_ARCHETYPES
        if (arch and arch not in NON_COMBAT_HEADWEAR_ARCHETYPES) or base_dt > 0:
            return False, (
                "🚫 Combat helmets and tactical headgear cannot be equipped in a slice-of-life setting.\n"
                "Only civilian headwear (caps, hoods, formal hats, beanies, berets) can be worn here."
            )
    elif slot == "Gloves":
        from mechanics.combat.items.gloves import NON_COMBAT_GLOVE_ARCHETYPES
        if (arch and arch not in NON_COMBAT_GLOVE_ARCHETYPES) or armor_type == "heavy" or base_dt > 0:
            return False, (
                "🚫 Heavy combat gauntlets cannot be equipped in a slice-of-life setting.\n"
                "Only civilian or light gloves can be worn here."
            )
    elif slot == "Shoes":
        from mechanics.combat.items.shoes import NON_COMBAT_SHOE_ARCHETYPES
        if (arch and arch not in NON_COMBAT_SHOE_ARCHETYPES) or armor_type == "heavy" or base_dt > 0:
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
) -> Dict[str, Any]:
    item_tier = tier if tier in (1, 2, 3) else roll_tier()
    scen_key = normalize_clothing_scenario(scenario)
    affix_data = SCENARIO_CLOTHING_AFFIXES.get(scen_key, SCENARIO_CLOTHING_AFFIXES["fantasy"])
    is_male = str(gender or "").strip().lower() == "male"
    is_female = str(gender or "").strip().lower() == "female"
    has_tail = is_tailed_race(race)

    chosen_archetype = archetype
    if slot == "Top":
        if chosen_archetype not in CLOTHING_TOPS:
            if scen_key == "high_school":
                chosen_archetype = random.choice([
                    "school_uniform_top", "blazer", "sweater", "waistcoat", "blouse", "casual_shirt"
                ])
            else:
                chosen_archetype = random.choice(list(CLOTHING_TOPS.keys()))
        base_data = CLOTHING_TOPS[chosen_archetype]
    else:
        if chosen_archetype not in CLOTHING_BOTTOMS:
            if scen_key == "high_school":
                if is_female:
                    chosen_archetype = random.choice(["skirt", "slacks", "trousers"])
                else:
                    chosen_archetype = random.choice(["trousers", "slacks"])
            else:
                chosen_archetype = random.choice(list(CLOTHING_BOTTOMS.keys()))
                if is_male and chosen_archetype == "skirt":
                    chosen_archetype = random.choice(["trousers", "slacks"])
        elif is_male and chosen_archetype == "skirt":
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
    # Enchanted (Tier 2) and Masterwork (Tier 1) can grant slightly refined social/eva bonuses.
    mods = dict(base_data["social_modifiers"])
    tier_name = TIER_NAMES.get(item_tier, "Standard")
    prefixes = affix_data.get("prefixes", {})
    suffixes = affix_data.get("suffixes", {})

    if item_tier == 2:
        # Tier 2 (Enchanted): EVA +1 bonus
        mods["eva"] = mods.get("eva", 0) + 1
        p_list = prefixes.get(2, ["Enchanted"])
        pref = random.choice(p_list)
        s_list = suffixes.get(2, [])
        if s_list and random.random() < 0.60:
            name = f"{pref} {base_name} {random.choice(s_list)}"
        else:
            name = f"{pref} {base_name}"
    elif item_tier == 1:
        # Tier 1 (Masterwork): EVA +2 bonus; SPECIAL capped strictly at +1 (CHA / PER)
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
        # Tier 3 (Standard): ~40% chance of standard flavor prefix, otherwise clean base name
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

    metadata = {
        "name": name,
        "tier": item_tier,
        "tier_name": tier_name,
        "slot": slot,
        "item_type": "Clothing",
        "archetype": chosen_archetype,
        "base_dt": 0,
        "dt": 0,
        "type_dt": {},
        "social_modifiers": mods,
        "stat_modifiers": dict(mods),
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

    mods_parts = []
    # SPECIAL stats
    for k in ("cha", "per", "eva", "acc"):
        v = social_mods.get(k, 0)
        if v > 0:
            mods_parts.append(f"+{v} {k.upper()}")
        elif v < 0:
            mods_parts.append(f"{v} {k.upper()}")
    # Damage reduction percentages (DR%)
    res_tuples = (
        ("physical_res", "Phys DR"), ("energy_res", "Energy DR"), ("fire_res", "Fire DR"),
        ("ice_res", "Cold DR"), ("shock_res", "Shock DR"), ("poison_res", "Poison DR"),
        ("holy_res", "Holy DR"), ("dark_res", "Dark DR"), ("earth_res", "Earth DR"),
        ("water_res", "Water DR"), ("wind_res", "Wind DR")
    )
    for r_k, r_label in res_tuples:
        if social_mods.get(r_k, 0) > 0:
            mods_parts.append(f"+{social_mods[r_k]}% {r_label}")

    mods_str = ", ".join(mods_parts) or "None"

    lines = [
        f"**{name}** ({tier_name})",
        f"**Slot:** {metadata.get('slot', 'Clothing')} • **Style:** {style}",
        f"**Modifiers:** {mods_str}",
        f"**Vibe:** {social_flags}"
    ]
    return "\n".join(lines)
