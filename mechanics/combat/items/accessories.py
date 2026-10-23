from __future__ import annotations
import copy
import random
from typing import Dict, Any, Optional

from mechanics.combat.items.envelope import serialize_item

ACCESSORY_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    # ── Arcane & Combat Jewelry (0 DT, Focus / Evasion / DR) ─────────────────
    "ring": {
        "slot": "Accessory 1",
        "base_matk": 6, "base_macc": 3, "matk_pct": 0.05,
        "base_dt": 0, "type_dt": {},
        "tags": {"social_flags": ["ornamental"], "stat_bonuses": ["matk", "macc", "matk_pct"]}
    },
    "amulet": {
        "slot": "Accessory 2",
        "base_dt": 0, "type_dt": {},
        "omni_res": 5,
        "base_eva": 2,
        "tags": {"social_flags": ["mystic"], "stat_bonuses": ["omni_res", "eva"]}
    },
    "talisman": {
        "slot": "Accessory 3",
        "base_dt": 0, "type_dt": {},
        "matk_pct": 0.04,
        "base_matk": 5,
        "holy_res": 5, "dark_res": 5,
        "tags": {"social_flags": ["arcane"], "stat_bonuses": ["matk_pct", "matk", "holy_res", "dark_res"]}
    },
    "bracelet": {
        "slot": "Accessory 4",
        "base_dt": 0, "type_dt": {},
        "physical_res": 4,
        "base_acc": 3,
        "tags": {"social_flags": ["fashionable"], "stat_bonuses": ["physical_res", "acc"]}
    },

    # ── Steampunk & Period Accessories ───────────────────────────────────────
    "pocket_watch": {
        "slot": "Accessory 1",
        "base_dt": 0, "type_dt": {},
        "base_per": 1, "base_acc": 2,
        "tags": {"social_flags": ["steampunk", "period", "precision", "clockwork"], "stat_bonuses": ["per", "acc"]}
    },
    "cravat_pin": {
        "slot": "Accessory 1",
        "base_dt": 0, "type_dt": {},
        "base_cha": 1,
        "tags": {"social_flags": ["period_formal", "dapper", "vintage"], "stat_bonuses": ["cha"]}
    },
    "chatelaine": {
        "slot": "Accessory 3",
        "base_dt": 0, "type_dt": {},
        "base_per": 1, "physical_res": 3,
        "tags": {"social_flags": ["period", "steampunk", "utility", "tools"], "stat_bonuses": ["per", "physical_res"]}
    },
    "monocle": {
        "slot": "Accessory 1",
        "base_dt": 0, "type_dt": {},
        "base_per": 1, "base_acc": 2,
        "tags": {"social_flags": ["period", "aristocratic", "optics"], "stat_bonuses": ["per", "acc"]}
    },

    # ── Modern & Chic Accessories ───────────────────────────────────────────
    "choker": {
        "slot": "Accessory 2",
        "base_dt": 0, "type_dt": {},
        "base_cha": 1, "base_eva": 2,
        "tags": {"social_flags": ["streetwear", "goth", "chic"], "stat_bonuses": ["cha", "eva"]}
    },
    "belt_buckle": {
        "slot": "Accessory 4",
        "base_dt": 0, "type_dt": {},
        "base_eva": 1, "physical_res": 3,
        "tags": {"social_flags": ["rugged", "fashion", "western"], "stat_bonuses": ["eva", "physical_res"]}
    },

    # ── Futuristic & Cyberpunk Accessories ──────────────────────────────────
    "neural_jack_plug": {
        "slot": "Accessory 3",
        "base_dt": 0, "type_dt": {},
        "base_matk": 4, "base_macc": 4, "shock_res": 5,
        "tags": {"social_flags": ["cyberware", "interface", "tech"], "stat_bonuses": ["matk", "macc", "shock_res"]}
    },
    "holo_badge": {
        "slot": "Accessory 2",
        "base_dt": 0, "type_dt": {},
        "base_cha": 1, "base_eva": 1,
        "tags": {"social_flags": ["hologram", "tech", "flamboyant"], "stat_bonuses": ["cha", "eva"]}
    },
    "data_cuff": {
        "slot": "Accessory 4",
        "base_dt": 0, "type_dt": {},
        "base_per": 1, "base_acc": 2, "energy_res": 4,
        "tags": {"social_flags": ["tech", "sensor", "wearable"], "stat_bonuses": ["per", "acc", "energy_res"]}
    }
}

NON_COMBAT_ACCESSORY_ARCHETYPES: Dict[str, Dict[str, Any]] = {
    "school_ribbon": {
        "slot": "Accessory 1",
        "base_cha": 1, "base_eva": 1,
        "base_dt": 0, "type_dt": {},
        "tags": {"social_flags": ["uniform", "neat"], "stat_bonuses": ["cha", "eva"]}
    },
    "enamel_badge": {
        "slot": "Accessory 2",
        "base_cha": 1, "base_eva": 1,
        "base_dt": 0, "type_dt": {},
        "tags": {"social_flags": ["club", "student_council"], "stat_bonuses": ["cha", "eva"]}
    },
    "smartwatch": {
        "slot": "Accessory 3",
        "base_acc": 3, "base_eva": 1,
        "base_dt": 0, "type_dt": {},
        "tags": {"social_flags": ["tech", "modern"], "stat_bonuses": ["acc", "eva"]}
    },
    "charm_keychain": {
        "slot": "Accessory 4",
        "base_cha": 1, "base_eva": 2,
        "base_dt": 0, "type_dt": {},
        "tags": {"social_flags": ["cute", "lucky"], "stat_bonuses": ["cha", "eva"]}
    },
    "earbuds": {
        "slot": "Accessory 1",
        "base_eva": 1, "base_cha": 1,
        "base_dt": 0, "type_dt": {},
        "tags": {"social_flags": ["music", "chill"], "stat_bonuses": ["eva", "cha"]}
    },
    # Period & modern additions to non-combat pool
    "pocket_watch": ACCESSORY_ARCHETYPES["pocket_watch"],
    "cravat_pin": ACCESSORY_ARCHETYPES["cravat_pin"],
    "chatelaine": ACCESSORY_ARCHETYPES["chatelaine"],
    "monocle": ACCESSORY_ARCHETYPES["monocle"],
    "choker": ACCESSORY_ARCHETYPES["choker"],
    "belt_buckle": ACCESSORY_ARCHETYPES["belt_buckle"],
    "holo_badge": ACCESSORY_ARCHETYPES["holo_badge"],
    "data_cuff": ACCESSORY_ARCHETYPES["data_cuff"]
}

SCENARIO_ACCESSORY_AFFIXES: Dict[str, Dict[str, Any]] = {
    "fantasy": {
        "archetype_names": {
            "ring": ["Mithril Signet Ring", "Band of Arcane Focus", "Gilded Ruby Ring"],
            "amulet": ["Moonstone Amulet", "Sun-Blessed Pendant", "Aegis Medallion"],
            "talisman": ["Runic Bone Talisman", "Star-Carved Talisman", "Enchanted Fetish"],
            "bracelet": ["Braided Silver Bangle", "Gilded Dragon Bracelet", "Iron Warded Torc"],
            "pocket_watch": ["Gilded Sun-Dial Pocket Locket", "Silver Moon-Phase Chronometer", "Astrologer's Pocket Sphere"],
            "cravat_pin": ["Elven Leaf Brooch", "Silver Falcon Crest Pin", "Sapphire Courtier Brooch"],
            "chatelaine": ["Healer's Charm Belt-Chain", "Scholar's Key Ring Clasp", "Alchemist's Vial Chain"],
            "monocle": ["Gem-Cut Reading Monocle", "Sage's Discerning Lens", "Court Scribe's Eyepiece"],
            "choker": ["Velvet Ribbon Choker", "Silver Filigree Torc", "Faerie Bell Choker"],
            "belt_buckle": ["Carved Dragon Horn Clasp", "Dwarven Brass Buckle", "Silver Griffin Belt-Plate"],
            "neural_jack_plug": ["Attuned Leyline Shard", "Spiritual Focus Crystal", "Mana-Threaded Conduit Charm"],
            "holo_badge": ["Illusionist's Mirage Crest", "Glimmering Faerie Brooch", "Starlight Pin"],
            "data_cuff": ["Runic Vambrace Bangle", "Enchanted Bracer of Clarity", "Sorcerer's Star-Cuff"],
            "school_ribbon": ["Academy Novice Ribbon", "Apprentice Crest Tie", "Spun-Linen Bow"],
            "enamel_badge": ["Mage Guild Enamel Pin", "Royal Library Badge", "Heraldic Crest Pin"],
            "smartwatch": ["Chronocrystal Wristlet", "Water-Clock Miniature Bangle", "Alchemical Compass Watch"],
            "charm_keychain": ["Lucky Pixie Trinket", "Carved Wooden Talisman Charm", "Silver Bell Keychain"],
            "earbuds": ["Enchanted Whispering Conch", "Attuned Sound-Pearl Studs", "Minstrel's Harmonic Beads"]
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
            "bracelet": ["Riveted Copper Manacle-Band", "Interlocked Gear Bracelet", "Brass Piston Wristlet"],
            "pocket_watch": ["Brass Chronometer Pocket Watch", "Tourbillon Escapement Fob", "Galvanic Stop-Clock"],
            "cravat_pin": ["Clockwork Cameo Brooch", "Ruby-Eyed Brass Owl Pin", "Steam-Guardsman Stickpin"],
            "chatelaine": ["Artificer's Tool Chatelaine", "Victorian Silver Chatelaine", "Apothecary's Vial Chain"],
            "monocle": ["Magnifying Brass Monocle", "Aether-Tuned Scrying Loupe", "Baron's Gilded Monocle"],
            "choker": ["Black Velvet Cameo Choker", "Clockwork Cogwheel Choker", "Brass Rivet Lace Collar"],
            "belt_buckle": ["Brass Cogwheel Belt Clasp", "Steam-Pressure Gauge Buckle", "Machinist Belt Plate"],
            "neural_jack_plug": ["Galvanic Contact Plug", "Telegraph Key Charm", "Aetheric Induction Jack"],
            "holo_badge": ["Phosphor Glow Pin", "Galvanic Arc Badge", "Steam-Gauge Miniature Brooch"],
            "data_cuff": ["Wrist-Mounted Barometer Cuff", "Galvanic Telegraph Wristlet", "Pneumatic Dial Vambrace"],
            "school_ribbon": ["Academy Steam-Cadet Ribbon", "Apprentice Cravat", "Guild Merit Bow"],
            "enamel_badge": ["Steam-Guild Brass Pin", "Royal Patent Office Badge", "Artificer League Medallion"],
            "smartwatch": ["Miniature Chronograph Wrist-Dial", "Galvanic Pulse Watch", "Clockwork Wrist Meter"],
            "charm_keychain": ["Miniature Gear Train Charm", "Brass Spanner Keychain", "Boiler Pressure Key Charm"],
            "earbuds": ["Acoustic Copper Ear-Tubes", "Galvanic Speaking Receiver", "Machinist Acoustic Buds"]
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
            "bracelet": ["Smart-Link Sensory Cuff", "Haptic Feedback Wristband", "Biomonitor Bangle"],
            "pocket_watch": ["Holo-Digital Pocket Chronometer", "Encrypted Datapad Pocket FOB", "Quantum Timestamp Locket"],
            "cravat_pin": ["Corpo Tie Clip with Fiber-Optic Tip", "Gold-Plated Syndicate Lapel Pin", "Chromed Cyber-Brooch"],
            "chatelaine": ["Netrunner Cable Chatelaine", "Hardware Hacker Utility Lanyard", "Data-Dongle Belt Chain"],
            "monocle": ["Kiroshi Optical Monocle", "Targeting Reticle Smart-Glass", "HUD Data-Loupe"],
            "choker": ["Electroluminescent LED Choker", "Spiked Cyber-Collar", "Optic-Fiber Choker"],
            "belt_buckle": ["LED Matrix Belt Buckle", "EMP-Shielded Titanium Buckle", "Carbon-Fiber Clasp"],
            "neural_jack_plug": ["Gold-Plated Neuro-Port Dongle", "ICE-Breaker Jack Charm", "Custom Netrunner Shunt"],
            "holo_badge": ["Corporate Identity Holo-Tag", "Glitch-Neon Street Badge", "Animated Holo-Pin"],
            "data_cuff": ["Tactical Forearm Cyberdeck Cuff", "Biomonitor Smart-Cuff", "Sub-Dermal Link Wristband"],
            "school_ribbon": ["MegaCorp Academy Ribbon", "Synth-Silk Uniform Bow", "Prep Tech-Tie"],
            "enamel_badge": ["Arasaka Merit Pin", "Militech Cadet Badge", "Netrunner Guild Pin"],
            "smartwatch": ["Neural-Sync Smartwatch", "Mil-Spec Biomonitor Watch", "Holographic Chrono-Band"],
            "charm_keychain": ["Pixel-Art Anime Charm", "Glitched RAM Stick Keychain", "LED Neon Mascot Tag"],
            "earbuds": ["Bone-Conduction Cyber-Buds", "Noise-Cancelling Sub-Bass Pods", "Encrypted Comms Ear-Pieces"]
        },
        "prefixes_t3": ["Street-Grade", "Mil-Spec", "Carbon-Weave", "Chrome", "Reinforced", "Standard-Issue"],
        "prefixes_t2": ["Overclocked", "Smart-Linked", "High-Frequency", "Sub-Dermal", "Nanite-Laced", "Thermal-Chambered"],
        "prefixes_t1": ["Arasaka Prototype", "Black-ICE", "Zero-Day", "Militech Apex", "Ghost-Protocol", "Hyper-Threaded"],
        "suffixes_t2": ["of Data-Siphon", "of System-Sync", "of the Netrunner", "of Ghost-Routing"],
        "suffixes_t1": ["of Cyber-Dominance", "of Impenetrable ICE", "of the Apex Syndicate", "of Omnipresence"]
    },
    "sci_fi": {
        "archetype_names": {
            "ring": ["Grav-Stabilizer Ring", "Sub-Space Resonator Band", "Quantum-Entangled Ring"],
            "amulet": ["Tachyon Field Pendant", "Stellar Navigation Core", "Antimatter Containment Locket"],
            "talisman": ["Psionic Focusing Shard", "Nanite Swarm Beacon", "Hyper-Space Token"],
            "bracelet": ["Omni-Tool Hard-Light Cuff", "Phase-Shift Wrist-Emitter", "Inertial Damper Bangle"],
            "pocket_watch": ["Relativistic Chronometer", "Sub-Space Timekeeper Locket", "Tachyon Frequency Fob"],
            "cravat_pin": ["Fleet Service Lapel Pin", "Diplomatic Envoy Insignia", "Hard-Light Collar Crest"],
            "chatelaine": ["Zero-G Tether Lanyard", "Engineer Field-Sensor Chain", "EVA Tool Clasp"],
            "monocle": ["Stellar Navigation Monocle", "Sub-Orbital Scanning Loupe", "Atmospheric Analyzer Lens"],
            "choker": ["Pressure-Compensating Neck Seal", "Thermal Polar Neck Band", "Bio-Telemetry Choker"],
            "belt_buckle": ["Magnetic-Lock Belt Buckle", "Personal Shield Anchor Clasp", "G-Force Restraint Buckle"],
            "neural_jack_plug": ["Sub-Dermal Quantum Key", "Positronic Core Jack", "Biometric Access Shunt"],
            "holo_badge": ["Planetary Envoy Holo-Crest", "Fleet Officer ID Beacon", "Photonic Diplomatic Badge"],
            "data_cuff": ["Omni-Tool Wrist Sleeve", "Atmosphere Sensor Wristlet", "Starfleet Nav-Cuff"],
            "school_ribbon": ["Space Academy Honor Ribbon", "Cadet Uniform Cravat", "Orbital Division Bow"],
            "enamel_badge": ["Federation Explorer Badge", "Astro-Science Merit Pin", "Starfleet Wings Pin"],
            "smartwatch": ["Chronospatial Wrist Chronometer", "Planetary Condition Monitor", "Pulse-Sensor Comm-Watch"],
            "charm_keychain": ["Holographic Planetoid Keychain", "Starship Model Charm", "Quantum Dice Keychain"],
            "earbuds": ["Sub-Space Audio Receivers", "Zero-G Bone Conduction Buds", "Universal Translator Ear-Pods"]
        },
        "prefixes_t3": ["Titanium", "Composite", "Field", "Standard-Issue", "Carbon-Alloy", "Ceramic"],
        "prefixes_t2": ["Overcharged", "Plasma-Infused", "Hyper-Coil", "Nanite-Lined", "Quantum-Phase", "Cryo-Cooled"],
        "prefixes_t1": ["Supernova", "Singularity", "Antimatter", "Chrono-Phase", "Omni-Core", "Dark-Energy"],
        "suffixes_t2": ["of the Vanguard", "of Vector-Sync", "of Phase-Shift", "of the Orbital Marine"],
        "suffixes_t1": ["of Stellar Superiority", "of the Singularity Core", "of Cosmic Synthesis", "of Absolute Zero"]
    },
    "nuclear_post_apocalypse": {
        "archetype_names": {
            "ring": ["Bent Copper-Pipe Ring", "Scrap-Wire Coiled Ring", "Flattened Bullet Band"],
            "amulet": ["Geiger-Counter Needle Locket", "Lead-Cased Glow Capsule", "Mutant-Fang Necklace"],
            "talisman": ["Bottlecap Lucky Charm", "Radioactive Trinket", "Scavenged Relic Token"],
            "bracelet": ["Barbed-Wire Bangle", "Watch-Part Scrap Cuff", "Tire-Bead Wristlet"],
            "pocket_watch": ["Stopped Pre-War Pocket Watch", "Scrap-Cased Chronometer", "Bullet-Dented Fob"],
            "cravat_pin": ["Twisted Wire Tie Pin", "Bone-Splinter Brooch", "Rifle-Primer Lapel Pin"],
            "chatelaine": ["Scavenger Lockpick Chain", "Survivor's Can-Opener Belt Clasp", "Pouch Lanyard"],
            "monocle": ["Cracked Watch-Glass Monocle", "Welder's Eyepiece Lens", "Scrap Scrying Glass"],
            "choker": ["Recycled Fan-Belt Choker", "Barbed-Wire Neck Band", "Scrap-Linen Collar"],
            "belt_buckle": ["Recycled License-Plate Buckle", "Road-Sign Sheet Metal Buckle", "Heavy Brass Engine Clasp"],
            "neural_jack_plug": ["Corroded Old-World Circuit Plug", "Severed Wiring Trinket", "Capacitor Charm"],
            "holo_badge": ["Flickering Pre-War Security Pin", "Cracked Solar Badge", "Glow-In-Dark Rad Charm"],
            "data_cuff": ["Jury-Rigged Pip-Cuff", "Geiger-Counter Wristlet", "Scrap Copper Sensor Band"],
            "school_ribbon": ["Tattered Pre-War Uniform Tie", "Faded Merit Ribbon", "Scavenged Silk Bow"],
            "enamel_badge": ["Rusted Pre-War School Badge", "Bunker Access Pin", "Old-World Flag Pin"],
            "smartwatch": ["Cracked Pre-War Fitness Tracker", "Bunker Radiation Watch", "Scavenged Digital Chrono"],
            "charm_keychain": ["Faded Toy Mascot Keychain", "Mutant Tooth Keychain", "Pre-War Keychain Ring"],
            "earbuds": ["Taped Wire Surplus Earphones", "Cracked Radio Ear-Bud", "Makeshift Antenna Earpiece"]
        },
        "prefixes_t3": ["Scrap-Metal", "Rusty", "Jury-Rigged", "Weathered", "Makeshift", "Spiked", "Lead-Lined"],
        "prefixes_t2": ["Rad-Hardened", "Bio-Toxic", "Reinforced-Steel", "Wasteland-Master", "Gamma-Tuned", "Spike-Studded"],
        "prefixes_t1": ["Doomsday", "Nuclear-Winter", "Alpha-Mutant", "Apex-Scavenger", "God-Corpse", "Irradiated"],
        "suffixes_t2": ["of the Scavenger", "of Rust & Ruin", "of the Raider", "of the Fallout Shelter"],
        "suffixes_t1": ["of Total Extinction", "of the Wasteland Nomad", "of the Radioactive Storm", "of Endless Survival"]
    },
    "dark_fantasy": {
        "archetype_names": {
            "ring": ["Bone-Carved Signet Ring", "Tarnished Black-Iron Band", "Vampiric Blood-Gem Ring"],
            "amulet": ["Marrow-Hungry Periapt", "Hex-Stitched Shrunken Head Pendant", "Weeping Eye Locket"],
            "talisman": ["Desolate Soul-Bound Effigy", "Grave-Soil Cloth Charm", "Torturer's Iron Nail"],
            "bracelet": ["Black-Thorn Torc", "Chained Vertebrae Cuff", "Blight-Marked Iron Bangle"],
            "pocket_watch": ["Undertaker's Blackened Stop-Watch", "Coffin-Shaped Pocket Clock", "Grave-Chrono Locket"],
            "cravat_pin": ["Raven-Claw Cravat Pin", "Bloodstone Mourning Brooch", "Gothic Cameo Stickpin"],
            "chatelaine": ["Torturer's Key Chatelaine", "Grave-Digger's Bone-Ring Chain", "Inquisitor's Instrument Chain"],
            "monocle": ["Corpse-Eye Magnifier", "Hex-Weaver's Smoky Monocle", "Sanguine Glass Eyepiece"],
            "choker": ["Black Velvet Funeral Choker", "Iron-Studded Blood Collar", "Bone-Laced Choker"],
            "belt_buckle": ["Gargoyle-Head Belt Clasp", "Wrought-Iron Skulled Buckle", "Cursed Black-Plate Clasp"],
            "neural_jack_plug": ["Soul-Syphon Bone Needle", "Cursed Blood-Vial Pendant", "Grave-Soil Fetish Token"],
            "holo_badge": ["Ghost-Flame Mourning Crest", "Phantom Light Cameo", "Will-O'-Wisp Brooch"],
            "data_cuff": ["Catacomb Bone Wristlet", "Inquisitor's Iron Bracer-Band", "Cursed Shroud Cuff"],
            "school_ribbon": ["Mourning Velvet Ribbon", "Frayed Cadet Black Bow", "Catacomb Apprentice Tie"],
            "enamel_badge": ["Inquisition Seal Pin", "Order of the Bleeding Heart Badge", "Desolate Crest Brooch"],
            "smartwatch": ["Water-Clock Wrist Reliquary", "Astrological Hourglass Band", "Tarnished Chrono-Dial"],
            "charm_keychain": ["Carved Bone Skull Trinket", "Dried Nightshade Bell Charm", "Tomb-Gate Iron Key"],
            "earbuds": ["Whispering Skull Studs", "Curse-Dampening Wax Ear-Conchs", "Grave-Quiet Ear Studs"]
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
            "earbuds": ["Wireless Bluetooth Earbuds", "Noise-Cancelling Earphones", "Sports Audio Buds"],
            "pocket_watch": ["Heirloom Brass Pocket Watch", "Retro Rail-Timekeeper Fob", "Grandfather's Gold Pocket Watch"],
            "cravat_pin": ["Prep School Lapel Pin", "Designer Tie Bar", "Club Captain Collar Pin"],
            "chatelaine": ["Student ID Lanyard & Key-Clip", "Locker Key Waist-Chain", "Pencil-Case Belt Lanyard"],
            "monocle": ["Reading Magnifier Lens", "Retro Costume Monocle", "Drama Club Eyepiece"],
            "choker": ["Velvet Heart Choker", "Tattoo Ribbon Choker", "Goth Fashion Collar"],
            "belt_buckle": ["Engraved Western Belt Buckle", "Designer Chrome Buckle", "Vintage Skate Belt Clasp"],
            "neural_jack_plug": ["USB-C Audio Dongle Keychain", "Flash Drive Tech Charm", "RGB Gaming Dongle Token"],
            "holo_badge": ["Pop Idol Concert LED Badge", "Festival Glow Pin", "Anime Hologram Pin"],
            "data_cuff": ["Sports Silicone Wristband", "LED Runner Slap-Band", "Festival Fabric Wrist-Cuff"]
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
    
    # Non-armor accessories strictly have base_dt = 0 and type_dt = {}
    base_dt = 0
    type_dt = {}

    stat_mods: Dict[str, Any] = {}
    for k, v in base_data.items():
        if k in ("slot", "tags", "type_dt", "base_dt"):
            continue
        if k.startswith("base_"):
            raw_key = k.replace("base_", "")
            # Filter out prohibited SPECIAL stats
            if raw_key in ("int", "luck", "str", "end", "agi"):
                continue
            scaled = int(round(v * tier_mult))
            # SPECIAL stats strictly capped at +1 maximum per design rule
            if raw_key in ("cha", "per") and scaled > 1:
                scaled = 1
            stat_mods[raw_key] = scaled
        elif isinstance(v, (int, float)):
            # Filter out prohibited SPECIAL stats
            if k in ("int", "luck", "str", "end", "agi"):
                continue
            scaled = round(v * tier_mult, 2) if isinstance(v, float) else int(round(v * tier_mult))
            if k in ("cha", "per") and scaled > 1:
                scaled = 1
            stat_mods[k] = scaled

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
        "tags": copy.deepcopy(base_data["tags"]),
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
