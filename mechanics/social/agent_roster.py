from __future__ import annotations
"""
44 Pre-Generated Special Agents Roster & Rank/Affinity Companion Recruitment
for the Anomalous Incursions scenario and its variants.

Generates and manages 44 persistent, named Special Agents across the 6 Fixed Factions:
- Public Anomaly Investigation Agency (`public_agency`): 12 Agents
- Private Agency #1 (`private_agency_1`): 6 Agents
- Private Agency #2 (`private_agency_2`): 6 Agents
- Eastern Exorcist Clan / Monastic Shrine Order (`monastic_order`): 8 Agents
- Occult Cult (`cult_faction`): 6 Operatives
- Clandestine Syndicate (`clandestine_faction`): 6 Operatives

Each Agent includes:
- Faction affiliation (`faction_id`, `faction_name`)
- Promotion Tier (`agent_tier`: 1..5) and Rank Title (`rank_title`)
- Faction-themed Class (`agent_class`)
- 5 Fixed Innate Special Abilities (`innate_abilities`: 4 tactical + 1 Signature Ultimate)
- Complete Persona, Appearance, Race, Sibling/Rival Web, and Daily Schedule
"""
import hashlib
import json
import random
from typing import Any, Dict, List, Optional, Tuple

import db
import namegen
import scenario_data


# ---------------------------------------------------------------------------
# Cultural Weighting for Procedural Roster Generation
# ---------------------------------------------------------------------------
MONASTIC_ORDER_CULTURE_WEIGHTS: Dict[str, float] = {
    "japanese": 0.35,
    "chinese": 0.20,
    "korean": 0.15,
    "malay": 0.05,
    "vietnamese": 0.05,
    "indian": 0.05,
    "english": 0.05,
    "american": 0.05,
    "german": 0.01,
    "french": 0.01,
    "polish": 0.01,
    "italian": 0.01,
    "spanish": 0.01,
}

# ---------------------------------------------------------------------------
# Agent Archetype & Faction Roster Blueprints (44 Total Agents)
# ---------------------------------------------------------------------------

PUBLIC_AGENCY_BLUEPRINTS: List[Dict[str, Any]] = [
    {
        "agent_tier": 5,
        "role": "Bureau Director of Containment",
        "agent_class": "Containment Specialist",
        "division": "Executive Command",
        "hq_room": "Executive & Tactical Dispatch Wing",
        "hq_node_id": "loc_hq_executive_dispatch",
        "city_hangout": "City Center ➔ Sunken Plaza Galleria ➔ Shattered Fountain Atrium",
        "hangout_node_id": "sub_plaza_fountain",
        "summary": "Iron-willed veteran who survived the first subway spatial collapse twenty years ago; carries the weight of every lost field operative.",
    },
    {
        "agent_tier": 4,
        "role": "Tactical Strike Division Captain",
        "agent_class": "Tactical Breacher",
        "division": "Rapid Containment Taskforce",
        "hq_room": "Psychometric Training & Calibration Range",
        "hq_node_id": "loc_hq_training_range",
        "city_hangout": "Downtown ➔ Late-Night Ramen & Izakaya Alley ➔ Open-Kitchen Broth & Counter Hall",
        "hangout_node_id": "sub_ramen_counter_hall",
        "summary": "No-nonsense breach commander who leads front-line containment entries and drills rookies until their reflexes are automatic.",
    },
    {
        "agent_tier": 4,
        "role": "Chief Psychic Resonance Researcher",
        "agent_class": "Psychic Resonance Investigator",
        "division": "Parapsychology & Telemetry Lab",
        "hq_room": "Medical & Psychic Cleansing Bay",
        "hq_node_id": "loc_hq_medical_bay",
        "city_hangout": "University & Parapsychology Campus ➔ Clocktower Archival Library & Rare Stacks ➔ Warded Iron Cage of Pre-Cataclysm Grimoires",
        "hangout_node_id": "sub_uni_forbidden_cage",
        "summary": "Brilliant parapsychologist who monitors citywide frequency spikes through custom neural telemetry headsets.",
    },
    {
        "agent_tier": 3,
        "role": "Senior Spatial Recon Investigator",
        "agent_class": "Psychic Resonance Investigator",
        "division": "Dimensional Cartography Unit",
        "hq_room": "Occult Forensics & Entity Research Division",
        "hq_node_id": "loc_hq_research_division",
        "city_hangout": "City Center ➔ Central Transit Terminal ➔ Lower Subway Platform",
        "hangout_node_id": "sub_transit_platform",
        "summary": "Maps non-Euclidean pocket corridors with chalk and laser rangefinders; never loses their sense of direction.",
    },
    {
        "agent_tier": 3,
        "role": "Senior Heavy Suppression Specialist",
        "agent_class": "Containment Specialist",
        "division": "Heavy Ordnance & Barriers",
        "hq_room": "Tactical Armory & Ordnance Depot",
        "hq_node_id": "loc_hq_tactical_armory",
        "city_hangout": "Industrial Zone ➔ Vulcan Heavy Steel Foundry ➔ Corrugated Iron Loading Bay",
        "hangout_node_id": "sub_foundry_loading",
        "summary": "Carries portable reality-grounding pylons like featherweight tripods and laughs off kinetic shockwaves.",
    },
    {
        "agent_tier": 3,
        "role": "Senior Cognitohazard Forensics Lead",
        "agent_class": "Occult Forensics Analyst",
        "division": "Memetic Countermeasures",
        "hq_room": "Subterranean Containment & Quarantine Sector",
        "hq_node_id": "loc_hq_containment_sector",
        "city_hangout": "City Center ➔ General Hospital & Medical Center ➔ Sub-Basement Morgue & Forensic Pathology",
        "hangout_node_id": "loc_hosp_morgue",
        "summary": "Wears polarized anti-memetic lenses and catalogs cursed broadcasts with surgical detachment.",
    },
    {
        "agent_tier": 2,
        "role": "Field Containment Operative",
        "agent_class": "Containment Specialist",
        "division": "Patrol Sector Alpha",
        "hq_room": "Main Lobby & Security Hub",
        "hq_node_id": "loc_hq_main_lobby",
        "city_hangout": "Suburban Residential District ➔ 24-Hour Corner Convenience Store ➔ Window Eat-In Counter Nook",
        "hangout_node_id": "sub_subkonbini_nook",
        "summary": "Dependable patrol agent who knows every back alley and transit shortcut across the metropolitan grid.",
    },
    {
        "agent_tier": 2,
        "role": "Field Ballistics & Relic Tech",
        "agent_class": "Tactical Breacher",
        "division": "Armory & Field Support",
        "hq_room": "Field Outfitter & Tailoring Quartermaster",
        "hq_node_id": "loc_hq_field_outfitter",
        "city_hangout": "Downtown ➔ 24-Hour Arcade & Billiards Hall ➔ Rhythm & Fighting Cabinet Aisles",
        "hangout_node_id": "sub_cabinet_aisles",
        "summary": "Customizes cold-iron ammunition and maintains field suppressors while blasting synthwave in the workshop.",
    },
    {
        "agent_tier": 2,
        "role": "Field Telemetry & Recon Agent",
        "agent_class": "Psychic Resonance Investigator",
        "division": "Signal Intelligence",
        "hq_room": "Bureau Canteen & Espresso Bar",
        "hq_node_id": "loc_hq_canteen_cafe",
        "city_hangout": "Seaside & Coastal Beach ➔ Boardwalk Pier & Amusement Strip ➔ End-of-Pier Fishing & Viewing Deck",
        "hangout_node_id": "sub_pier_observation",
        "summary": "Sensitive empath who hears anomalous radio whispers hours before instruments register a breach.",
    },
    {
        "agent_tier": 1,
        "role": "Probationary Containment Agent",
        "agent_class": "Containment Specialist",
        "division": "Field Intake Squad",
        "hq_room": "Operative Dormitories & Rest Quarters",
        "hq_node_id": "loc_hq_agent_dormitories",
        "city_hangout": "Suburban Residential District ➔ Neighborhood Park ➔ Duck Pond & Wooden Footbridge",
        "hangout_node_id": "sub_park_pond",
        "summary": "Recruited after surviving a suburban mirror-rift incident; eager to prove their mettle on official dispatches.",
    },
    {
        "agent_tier": 1,
        "role": "Probationary Forensic Aide",
        "agent_class": "Occult Forensics Analyst",
        "division": "Evidence & Vault Intake",
        "hq_room": "Main Lobby & Security Hub",
        "hq_node_id": "loc_hq_main_lobby",
        "city_hangout": "{session_school} ➔ Central Courtyard & Campus Cafeteria ➔ Shaded Vending Machine Pavilion",
        "hangout_node_id": "sub_vending_alcove",
        "summary": "Sharp-eyed rookie who meticulously tags altered objects and double-checks every containment seal.",
    },
    {
        "agent_tier": 1,
        "role": "Probationary Vanguard Scout",
        "agent_class": "Tactical Breacher",
        "division": "Field Intake Squad",
        "hq_room": "Tactical Armory & Ordnance Depot",
        "hq_node_id": "loc_hq_tactical_armory",
        "city_hangout": "{session_school} ➔ Main Gymnasium & Athletic Field ➔ Outdoor Running Track & Bleachers",
        "hangout_node_id": "sub_athletic_track",
        "summary": "Former urban parkour runner drafted into the Bureau after outrunning a spatial distortion hound.",
    },
]

PRIVATE_AGENCY_1_BLUEPRINTS: List[Dict[str, Any]] = [
    {
        "agent_tier": 5,
        "role": "Chief Executive & Tactical Director",
        "agent_class": "Corporate Strike Contractor",
        "division": "Executive Board",
        "hq_room": "Executive Contract & Tactical Dispatch Wing",
        "hq_node_id": "sub_priv1_dispatch",
        "city_hangout": "Sovereign Hills & Sky-Estates ➔ Sky-High Penthouse Lounge ➔ 80th-Floor Infinity Pool & Cocktail Deck",
        "hangout_node_id": "sub_sky_infinity_bar",
        "summary": "Treats anomaly neutralization as a high-margin defence portfolio; expects flawless execution and immaculate suits.",
    },
    {
        "agent_tier": 4,
        "role": "Lead Hazard Termination Commander",
        "agent_class": "Corporate Strike Contractor",
        "division": "Apex Strike Wing",
        "hq_room": "VR Tactical & Resonance Calibration Range",
        "hq_node_id": "sub_priv1_training",
        "city_hangout": "International Airport & Airfield ➔ First-Class Executive Sky-Lounge & Capsule Hotel ➔ Panoramic Tarmac-View Champagne Bar",
        "hangout_node_id": "sub_ap_runway_bar",
        "summary": "High-priced mercenary veteran who grades every anomalous entity by ammunition expenditure and hazard bonuses.",
    },
    {
        "agent_tier": 3,
        "role": "Senior Relic Acquisition Specialist",
        "agent_class": "Anomalous Relic Hunter",
        "division": "Asset Recovery",
        "hq_room": "Proprietary Relic R&D & Appraisal Division",
        "hq_node_id": "sub_priv1_research",
        "city_hangout": "Sovereign Hills & Sky-Estates ➔ The Crimson Masquerade Auction House ➔ Candlelit Amphitheater & Caged Stage",
        "hangout_node_id": "sub_auction_amphitheater",
        "summary": "Specializes in extracting high-tier altered artifacts from collapsing rifts before public containment teams arrive.",
    },
    {
        "agent_tier": 3,
        "role": "Senior Ballistic Resonance Sniper",
        "agent_class": "Corporate Strike Contractor",
        "division": "Overwatch Unit",
        "hq_room": "Syndicate Tactical Armory & Requisition Depot",
        "hq_node_id": "sub_priv1_armory",
        "city_hangout": "City Center ➔ Sunken Plaza Galleria ➔ Glass Skywalk Dining Terrace",
        "hangout_node_id": "sub_plaza_terrace",
        "summary": "Cool-headed sharpshooter who calculates wind shear and dimensional refraction across three city blocks.",
    },
    {
        "agent_tier": 2,
        "role": "Contract Combat Specialist",
        "agent_class": "Corporate Strike Contractor",
        "division": "Rapid Response",
        "hq_room": "Bespoke Ballistic Outfitter & Tailoring Atelier",
        "hq_node_id": "sub_priv1_outfitter",
        "city_hangout": "Downtown ➔ Neon Shopping Arcade & Mall ➔ Streetwear & Designer Apparel Boutique",
        "hangout_node_id": "sub_fashion_boutique",
        "summary": "Spends bounty payouts on bespoke kevlar tailoring and experimental elemental weapon mods.",
    },
    {
        "agent_tier": 1,
        "role": "Junior Contract Hunter",
        "agent_class": "Anomalous Relic Hunter",
        "division": "Field Acquisitions",
        "hq_room": "Corporate Security Lobby & Entrance",
        "hq_node_id": "sub_priv1_entrance",
        "city_hangout": "Downtown ➔ 24-Hour Arcade & Billiards Hall ➔ Upstairs Smoke-Hazy Billiards Lounge",
        "hangout_node_id": "sub_billiards_lounge",
        "summary": "Ambitious freelancer who signed an exclusive private retainer to pay off massive family medical debts.",
    },
]

PRIVATE_AGENCY_2_BLUEPRINTS: List[Dict[str, Any]] = [
    {
        "agent_tier": 5,
        "role": "Managing Partner & Chief Appraiser",
        "agent_class": "Anomalous Relic Hunter",
        "division": "Syndicate Partners",
        "hq_room": "Sub-Basement Corporate Containment & Quarantine Vault",
        "hq_node_id": "sub_priv2_vault",
        "city_hangout": "Sovereign Hills & Sky-Estates ➔ Elysium Private Country Club ➔ Members-Only Brandy & Cigar Parlour",
        "hangout_node_id": "sub_elysium_cigar_room",
        "summary": "Charismatic venture capitalist of the paranormal world who auctions neutralized anomaly cores to R&D conglomerates.",
    },
    {
        "agent_tier": 4,
        "role": "Field Operations Commander",
        "agent_class": "Corporate Strike Contractor",
        "division": "Containment Recovery",
        "hq_room": "Executive Contract & Tactical Dispatch Wing",
        "hq_node_id": "sub_priv2_dispatch",
        "city_hangout": "City Docks & Harbor ➔ Automated Container Pier 12 ➔ Towering Gantry Crane Operator Cab",
        "hangout_node_id": "sub_pier_gantry",
        "summary": "Pragmatic commander who favors heavy elemental weaponry and aggressive perimeter sweeps.",
    },
    {
        "agent_tier": 3,
        "role": "Senior Occult Appraiser & Tactician",
        "agent_class": "Occult Forensics Analyst",
        "division": "Relic Valuation Lab",
        "hq_room": "Proprietary Relic R&D & Appraisal Division",
        "hq_node_id": "sub_priv2_research",
        "city_hangout": "City Center ➔ Sanctuary Antiquities & Licensed Wards ➔ Appraisal Desk & Leyline Map Table",
        "hangout_node_id": "sub_curio_appraisal",
        "summary": "Can tell an authentic cursed relic from a mundane forgery by the metallic taste of the air around it.",
    },
    {
        "agent_tier": 3,
        "role": "Senior Close-Quarters Eliminator",
        "agent_class": "Tactical Breacher",
        "division": "Shock Extraction",
        "hq_room": "VR Tactical & Resonance Calibration Range",
        "hq_node_id": "sub_priv2_training",
        "city_hangout": "The Lower Wards & Tenements ➔ Underground Boxing & Fight Pit ➔ Chain-Link Ring & Betting Bleachers",
        "hangout_node_id": "sub_fight_cage",
        "summary": "Prefers high-frequency melee blades over firearms because blades never jam inside a magnetic anomaly.",
    },
    {
        "agent_tier": 2,
        "role": "Licensed Bounty Operative",
        "agent_class": "Anomalous Relic Hunter",
        "division": "Urban Hunting",
        "hq_room": "Skyline Executive Espresso Bar & Canteen",
        "hq_node_id": "sub_priv2_canteen",
        "city_hangout": "Downtown ➔ Basement Jazz & Cocktail Bar ➔ Main Cocktail Lounge & Quartet Stage",
        "hangout_node_id": "sub_jazz_lounge",
        "summary": "Tracks nocturnal anomalies through the entertainment district while maintaining a flashy socialite cover.",
    },
    {
        "agent_tier": 1,
        "role": "Associate Field Contractor",
        "agent_class": "Corporate Strike Contractor",
        "division": "Urban Hunting",
        "hq_room": "Executive Security Lobby & Entrance",
        "hq_node_id": "sub_priv2_entrance",
        "city_hangout": "Downtown ➔ Neon Shopping Arcade & Mall ➔ Neon Atrium Food Court",
        "hangout_node_id": "sub_food_court",
        "summary": "Constantly refreshes the bounty dispatch board looking for lucrative co-op contracts.",
    },
]

MONASTIC_ORDER_BLUEPRINTS: List[Dict[str, Any]] = [
    {
        "agent_tier": 5,
        "role": "Grand Abbot & High Purifier",
        "agent_class": "Shinto Shrine Exorcist",
        "division": "Inner Sanctum Council",
        "hq_room": "Five-Story Pagoda & Sacred Reliquary",
        "hq_node_id": "loc_et_five_story_pagoda",
        "city_hangout": "Woods & Mountain Reserve ➔ Eastern Grand Temple & Sanctuary ➔ Main Worship Hall & Incense Courtyard",
        "hangout_node_id": "loc_et_main_sanctuary",
        "summary": "Keeper of the twelve ancestral sealing bells; views modern urban anomalies as ancient karmic imbalances given concrete form.",
    },
    {
        "agent_tier": 4,
        "role": "Master of Barrier Wards",
        "agent_class": "Shinto Shrine Exorcist",
        "division": "Boundary Protection",
        "hq_room": "Five-Story Pagoda & Sacred Reliquary",
        "hq_node_id": "loc_et_five_story_pagoda",
        "city_hangout": "Woods & Mountain Reserve ➔ Eastern Grand Temple & Sanctuary ➔ Five-Story Pagoda & Sacred Reliquary",
        "hangout_node_id": "loc_et_five_story_pagoda",
        "summary": "Maintains the spiritual ley-line anchors that keep the city's oldest sealed entities slumbering beneath the mountain.",
    },
    {
        "agent_tier": 3,
        "role": "Senior Shikigami Summoner",
        "agent_class": "Shikigami Medium",
        "division": "Paper-Charm Vanguard",
        "hq_room": "Zen Rock Garden & Bamboo Tea House",
        "hq_node_id": "loc_et_zen_tea_garden",
        "city_hangout": "Woods & Mountain Reserve ➔ Eastern Grand Temple & Sanctuary ➔ Zen Rock Garden & Bamboo Tea House",
        "hangout_node_id": "loc_et_zen_tea_garden",
        "summary": "Folds origami crane and wolf familiars imbued with purifying flame to scout hazardous spatial rifts.",
    },
    {
        "agent_tier": 3,
        "role": "Senior Sacred Blade Exorcist",
        "agent_class": "Shinto Shrine Exorcist",
        "division": "Demon-Quelling Division",
        "hq_room": "Main Worship Hall & Incense Courtyard",
        "hq_node_id": "loc_et_main_sanctuary",
        "city_hangout": "Woods & Mountain Reserve ➔ Pine Forest Hiking Trails ➔ Misty Ravine Suspension Footbridge",
        "hangout_node_id": "sub_cedar_bridge",
        "summary": "Wields a sanctified ceremonial odachi that slices through incorporeal wraiths and dimensional tethers alike.",
    },
    {
        "agent_tier": 2,
        "role": "Shrine Purification Medium",
        "agent_class": "Shikigami Medium",
        "division": "Sanctuary Healing & Rites",
        "hq_room": "Sacred Mountain Hot Springs & Onsen Bathhouse",
        "hq_node_id": "loc_et_onsen_bathhouse",
        "city_hangout": "Woods & Mountain Reserve ➔ Eastern Grand Temple & Sanctuary ➔ Sacred Mountain Hot Springs & Onsen Bathhouse",
        "hangout_node_id": "loc_et_onsen_bathhouse",
        "summary": "Tends to spiritually contaminated agents with sacred incense and gentle chanting.",
    },
    {
        "agent_tier": 2,
        "role": "Wandering Ascetic Monk",
        "agent_class": "Shinto Shrine Exorcist",
        "division": "Urban Pilgrimage",
        "hq_room": "Grand Torii Gate & Omikuji Talisman Stand",
        "hq_node_id": "loc_et_torii_approach",
        "city_hangout": "Subterranean Under-City & Catacombs ➔ Pre-War Forgotten Subway Concourse ➔ Abandoned 1930s Brass Ticket Rotunda",
        "hangout_node_id": "sub_uc_brass_rotunda",
        "summary": "Patrols the city's subway tunnels in wooden geta sandals, banishing restless spectral echoes before dawn.",
    },
    {
        "agent_tier": 1,
        "role": "Novice Shrine Maiden / Acolyte",
        "agent_class": "Shikigami Medium",
        "division": "Talisman Inscription",
        "hq_room": "Grand Torii Gate & Omikuji Talisman Stand",
        "hq_node_id": "loc_et_torii_approach",
        "city_hangout": "{session_school} ➔ Main Academic Building & Classrooms ➔ School Rooftop",
        "hangout_node_id": "loc_school_rooftop",
        "summary": "Balances daytime academic studies with evening exorcism patrols and talisman calligraphy.",
    },
    {
        "agent_tier": 1,
        "role": "Novice Bell-Ringer & Guardian",
        "agent_class": "Shinto Shrine Exorcist",
        "division": "Outer Gate Watch",
        "hq_room": "Main Worship Hall & Incense Courtyard",
        "hq_node_id": "loc_et_main_sanctuary",
        "city_hangout": "Woods & Mountain Reserve ➔ Eastern Grand Temple & Sanctuary ➔ Grand Torii Gate & Omikuji Talisman Stand",
        "hangout_node_id": "loc_et_torii_approach",
        "summary": "Sweeps the stone steps at sunrise and guards the outer torii gates with a blessed wooden naginata.",
    },
]

OCCULT_CULT_BLUEPRINTS: List[Dict[str, Any]] = [
    {
        "agent_tier": 5,
        "role": "High Hierophant of the Rift",
        "agent_class": "Occult Ritualist",
        "division": "Inner Circle of Awakening",
        "hq_room": "Abyssal Conduit Inner Sanctum",
        "hq_node_id": "sub_cult_sanctum",
        "city_hangout": "Uptown District ➔ St. Jude's Historic Cathedral ➔ Stained-Glass Nave & Sanctuary Altar",
        "hangout_node_id": "sub_cathedral_nave",
        "summary": "Preaches that the approaching World-Ending Anomaly is not a disaster, but humanity's overdue metamorphosis.",
    },
    {
        "agent_tier": 4,
        "role": "Grand Cantor of Frequencies",
        "agent_class": "Occult Ritualist",
        "division": "Choir of Static",
        "hq_room": "Resonant Fracture Altar",
        "hq_node_id": "sub_cult_altar",
        "city_hangout": "Industrial Zone ➔ Subterranean Cold-War Bunker ➔ Dead-Frequency Numbers Station Chamber",
        "hangout_node_id": "sub_bunker_radio_room",
        "summary": "Transmits cognitohazardous hymns across pirate radio bands to weaken the city's dimensional barriers.",
    },
    {
        "agent_tier": 3,
        "role": "Senior Abyssal Conduit",
        "agent_class": "Abyssal Vessel",
        "division": "Living Reliquary",
        "hq_room": "Sacrificial Entity Holding Cells",
        "hq_node_id": "sub_cult_cells",
        "city_hangout": "Subterranean Under-City & Catacombs ➔ The Whispering Bone-Ossuary Catacombs Anomaly ➔ Sunken Still-Water Ossuary Rotunda",
        "hangout_node_id": "sub_uc_black_font",
        "summary": "Voluntarily hosts a parasitic shadow-entity beneath their coat, trading sanity for terrifying void resonance.",
    },
    {
        "agent_tier": 3,
        "role": "Senior Cryptic Archivist",
        "agent_class": "Occult Ritualist",
        "division": "Forbidden Texts",
        "hq_room": "Forbidden Apocrypha Reliquary",
        "hq_node_id": "sub_cult_reliquary",
        "city_hangout": "Uptown District ➔ Uptown Roastery & Rare Bookshop ➔ Leather-Armchair Rare Book Mezzanine",
        "hangout_node_id": "sub_roastery_mezzanine",
        "summary": "Collects rubbing transcripts of pre-human monoliths and trades covert intelligence with open-minded outsiders.",
    },
    {
        "agent_tier": 2,
        "role": "Veiled Acolyte Whisperer",
        "agent_class": "Abyssal Vessel",
        "division": "Street Proselytizers",
        "hq_room": "Acolyte Cloister & Chant Hall",
        "hq_node_id": "sub_cult_cloister",
        "city_hangout": "Seaside & Coastal Beach ➔ Theme Park & Amusement Resort ➔ The Infinite Hall of Mirrors Anomaly",
        "hangout_node_id": "loc_tp_mirror_labyrinth",
        "summary": "Disillusioned former university researcher drawn to the cult after witnessing an impossible miracle in a rift.",
    },
    {
        "agent_tier": 2,
        "role": "Penitent Rift-Watcher",
        "agent_class": "Occult Ritualist",
        "division": "Outer Watch",
        "hq_room": "Ward-Sealed Threshold Entrance",
        "hq_node_id": "sub_cult_entrance",
        "city_hangout": "Seaside & Coastal Beach ➔ Boardwalk Pier & Amusement Strip ➔ End-of-Pier Fishing & Viewing Deck",
        "hangout_node_id": "sub_pier_observation",
        "summary": "Doubts the Hierophant's most destructive edicts and secretly warns sympathetic agents before major civilian breaches.",
    },
]

CLANDESTINE_SYNDICATE_BLUEPRINTS: List[Dict[str, Any]] = [
    {
        "agent_tier": 5,
        "role": "The Shadow Broker & Overseer",
        "agent_class": "Black-Ops Relic Smuggler",
        "division": "Directorate Zero",
        "hq_room": "Directorate Black-Ledger Vault",
        "hq_node_id": "sub_synd_vault",
        "city_hangout": "Industrial Zone ➔ Subterranean Cold-War Bunker ➔ Abandoned Fallout Control Room",
        "hangout_node_id": "sub_bunker_command",
        "summary": "Operates from behind encrypted voice modulators, buying and selling anomalous weapons to the highest bidder.",
    },
    {
        "agent_tier": 4,
        "role": "Chief Wetwork & Erasure Handler",
        "agent_class": "Syndicate Cleaner",
        "division": "Black-Bag Operations",
        "hq_room": "Contraband Entity Auction Pens",
        "hq_node_id": "sub_synd_pens",
        "city_hangout": "City Docks & Harbor ➔ Blackanchor Drydock & Warehouses ➔ Fog-Shrouded Under-Pier Catwalk",
        "hangout_node_id": "sub_smuggler_pier",
        "summary": "Makes inconvenient witnesses and rogue containment leaks disappear without leaving a single forensic trace.",
    },
    {
        "agent_tier": 3,
        "role": "Senior Black-Market Quartermaster",
        "agent_class": "Black-Ops Relic Smuggler",
        "division": "Unlicensed Ordnance",
        "hq_room": "Black-Budget Brokerage Floor",
        "hq_node_id": "sub_synd_floor",
        "city_hangout": "The Lower Wards & Tenements ➔ Backstreet Pawn & Black Market ➔ Sub-Basement Contraband Relic Stalls",
        "hangout_node_id": "sub_black_market_bazaar",
        "summary": "Deals in prototype anomalous firearms stripped of Bureau serial numbers and tracking beacons.",
    },
    {
        "agent_tier": 3,
        "role": "Senior Signal Interceptor",
        "agent_class": "Occult Forensics Analyst",
        "division": "Wiretap & Counter-Intel",
        "hq_room": "Weaponized Cognitohazard Lab",
        "hq_node_id": "sub_synd_lab",
        "city_hangout": "International Airport & Airfield ➔ Air Traffic Control Tower & Radar Deck ➔ Atmospheric Resonance & Anomaly Doppler Array",
        "hangout_node_id": "sub_ap_weather_array",
        "summary": "Splices into Public Agency dispatch channels to ambush containment convoys or tip off favored freelancers.",
    },
    {
        "agent_tier": 2,
        "role": "Syndicate Relic Runner",
        "agent_class": "Black-Ops Relic Smuggler",
        "division": "Courier Network",
        "hq_room": "Mercenary Security Guardroom",
        "hq_node_id": "sub_synd_guardroom",
        "city_hangout": "Industrial Zone ➔ Derelict Rail Freight Yard ➔ Labyrinth of Rusted Freight Boxcars",
        "hangout_node_id": "sub_rail_boxcars",
        "summary": "Smuggles lead-lined containment briefcases across district checkpoints on a modified stealth motorcycle.",
    },
    {
        "agent_tier": 2,
        "role": "Covert Fixer & Informant",
        "agent_class": "Syndicate Cleaner",
        "division": "Street Intelligence",
        "hq_room": "Biometric Vault Door Entrance",
        "hq_node_id": "sub_synd_entrance",
        "city_hangout": "The Lower Wards & Tenements ➔ Red-Lantern Backstreet Lounge ➔ Dimly Lit Velvet Hookah & Drink Parlor",
        "hangout_node_id": "sub_red_lantern_parlor",
        "summary": "Pragmatic double-dealer who values survival over ideology and gladly sells Syndicate secrets to trusted allies.",
    },
]

AGENT_DRIVES: List[str] = [
    "Searching for a missing partner who vanished inside a non-Euclidean subway rift three years ago.",
    "Determined to prevent a citywide anomalous cataclysm without sacrificing innocent civilians to cold bureaucracy.",
    "Secretly suppressing a creeping anomalous resonance mark on their own collarbone that grows warm near rifts.",
    "Amassing enough hazard pay and promotion standing to expose high-level corruption within the city's containment council.",
    "Driven by an obsessive scientific curiosity to decode the true origin of the World-Ending Anomaly.",
    "Protecting a younger sibling who lives in the residential suburbs from ever learning the truth about night incursions.",
    "Seeking redemption after a botched containment operation in the industrial zone cost their former squad their lives.",
    "Trying to prove that human tactical ingenuity and resolve can overcome even reality-warping horrors.",
]

AGENT_FRICTIONS: List[str] = [
    "Suffers from chronic insomnia after prolonged exposure to psychic static, masking exhaustion with dark humor.",
    "Deeply distrustful of authority figures who issue orders from behind reinforced command bunkers.",
    "Recklessly volunteers for point-man breach duty whenever civilian hostages are trapped inside a distortion zone.",
    "Keeps everyone at arm's length out of fear of losing another squadmate to a sudden cognitohazard.",
    "Compulsively checks pocket Geiger-resonance meters and reflective surfaces before entering any room.",
    "Blunt and brutally honest during mission debriefings, rubbing career bureaucrats the wrong way.",
]

AGENT_QUIRKS: List[str] = [
    "Constantly flips a tarnished cold-iron coin across their knuckles while analyzing anomaly telemetry.",
    "Drinks bitter black coffee from a dented titanium thermos and speaks in clipped, deadpan sentences.",
    "Adjusts polarized anti-memetic sunglasses even indoors and taps their boot heel in three-beat rhythms.",
    "Carries a pocket notebook filled with hand-drawn sketches of every anomalous entity they have survived.",
    "Smells faintly of ozone and temple sandalwood; pauses to listen to ambient air vents before speaking.",
    "Wears fingerless tactical gloves year-round and traces protective sigils on doorframes out of habit.",
]


def generate_anomalous_special_agents_roster(
    session_id: int,
    scen_key: str = "anomalous_incursions",
    factions: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Deterministically generates the 44 Named Special Agents across the 6 Fixed Factions:
    - 12 Public Agency (`public_agency`)
    - 6 Private Agency #1 (`private_agency_1`)
    - 6 Private Agency #2 (`private_agency_2`)
    - 8 Monastic Shrine Order (`monastic_order`)
    - 6 Occult Cult (`cult_faction`)
    - 6 Clandestine Syndicate (`clandestine_faction`)
    """
    from mechanics.social.factions import ANOMALOUS_PROMOTION_TIERS, infer_anomalous_faction_archetype
    from mechanics.combat.spells.kits import get_anomalous_starting_innate_abilities
    from mechanics.social.races import normalize_race
    from mechanics.social.persona import normalize_appearance

    # Resolve faction names from DB or starter generator
    fac_map: Dict[str, Dict[str, Any]] = {}
    if not factions and session_id:
        try:
            factions = db.get_factions(session_id) or []
        except Exception:
            factions = []
    if not factions:
        factions = namegen.get_scenario_starter_factions(scen_key, hash_val=int(session_id or 1))

    for f in (factions or []):
        arch = str(f.get("faction_archetype_key") or infer_anomalous_faction_archetype(f) or f.get("faction_id") or "").strip()
        if arch:
            fac_map[arch] = f

    faction_groups = [
        ("public_agency", PUBLIC_AGENCY_BLUEPRINTS),
        ("private_agency_1", PRIVATE_AGENCY_1_BLUEPRINTS),
        ("private_agency_2", PRIVATE_AGENCY_2_BLUEPRINTS),
        ("monastic_order", MONASTIC_ORDER_BLUEPRINTS),
        ("cult_faction", OCCULT_CULT_BLUEPRINTS),
        ("clandestine_faction", CLANDESTINE_SYNDICATE_BLUEPRINTS),
    ]

    seed_base = int(session_id or 101) * 97 + 31
    used_names: set[str] = set()
    roster: List[Dict[str, Any]] = []

    # Pre-roll 4 shared family surnames for cross-faction sibling drama
    sibling_surnames: List[str] = []
    for s_idx in range(4):
        for attempt in range(25):
            sample = namegen.generate_person_name(scen_key, gender="female", seed=seed_base + s_idx * 41 + attempt * 13)
            _, last = namegen.extract_first_and_last_name(sample)
            clean_last = namegen.normalize_base_surname(last)
            if clean_last and len(clean_last) >= 3 and clean_last.lower() not in [x.lower() for x in sibling_surnames]:
                sibling_surnames.append(clean_last)
                break
        if len(sibling_surnames) <= s_idx:
            sibling_surnames.append(["Vance", "Kurosawa", "Mercer", "Thorne"][s_idx])

    global_idx = 0
    for faction_id, blueprints in faction_groups:
        fac_info = fac_map.get(faction_id, {})
        faction_name = str(fac_info.get("name") or faction_id.replace("_", " ").title())
        raw_hq = str(fac_info.get("hq_location_id") or fac_info.get("hq_location") or "").strip()
        hq_location = ""
        if raw_hq and session_id:
            try:
                from mechanics.world.locations import format_node_hierarchy
                resolved_hq = format_node_hierarchy(session_id, raw_hq)
                if resolved_hq and not resolved_hq.startswith("loc_") and not resolved_hq.startswith("zone_"):
                    parts_hq = [p.strip() for p in resolved_hq.split("➔")]
                    hq_location = " ➔ ".join(parts_hq[:2]) if len(parts_hq) >= 2 else resolved_hq
            except Exception:
                pass
        if not hq_location:
            hq_location = raw_hq if (raw_hq and not raw_hq.startswith(("loc_", "zone_", "sub_"))) else faction_name

        for local_idx, bp in enumerate(blueprints):
            gender = "female" if (global_idx % 2 == 0) else "male"
            agent_tier = int(bp.get("agent_tier", 1))
            tier_meta = next((t for t in ANOMALOUS_PROMOTION_TIERS if t["tier"] == agent_tier), ANOMALOUS_PROMOTION_TIERS[0])
            rank_title = tier_meta["title"]

            # Assign shared sibling surname to specific cross-faction pairs:
            # Pair 0: Public Agency idx 3 <-> Private Agency 1 idx 2
            # Pair 1: Public Agency idx 6 <-> Cult Faction idx 4
            # Pair 2: Private Agency 2 idx 3 <-> Clandestine Faction idx 4
            # Pair 3: Monastic Order idx 2 <-> Public Agency idx 8
            forced_surname = ""
            if (faction_id == "public_agency" and local_idx == 3) or (faction_id == "private_agency_1" and local_idx == 2):
                forced_surname = sibling_surnames[0]
            elif (faction_id == "public_agency" and local_idx == 6) or (faction_id == "cult_faction" and local_idx == 4):
                forced_surname = sibling_surnames[1]
            elif (faction_id == "private_agency_2" and local_idx == 3) or (faction_id == "clandestine_faction" and local_idx == 4):
                forced_surname = sibling_surnames[2]
            elif (faction_id == "monastic_order" and local_idx == 2) or (faction_id == "public_agency" and local_idx == 8):
                forced_surname = sibling_surnames[3]

            culture_weights = None
            if faction_id == "monastic_order":
                culture_weights = MONASTIC_ORDER_CULTURE_WEIGHTS

            full_name = ""
            for attempt in range(30):
                item_seed = seed_base + global_idx * 53 + attempt * 109
                if forced_surname:
                    fam_pat = None if forced_surname.lower() in namegen._INDONESIAN_NON_PATRONYMIC_SURNAMES else (sum(ord(ch) for ch in f"{session_id}:{forced_surname.lower()}") % 2 == 0)
                    cand = namegen.generate_person_name_with_surname(
                        forced_surname,
                        scen_key,
                        gender=gender,
                        cross_culture_chance=0.10,
                        culture_weights=culture_weights,
                        seed=item_seed,
                        use_patronymic=fam_pat,
                    )
                else:
                    cand = namegen.generate_person_name(
                        scen_key,
                        gender=gender,
                        culture_weights=culture_weights,
                        seed=item_seed,
                    )
                if cand and cand.lower() not in used_names:
                    full_name = cand
                    used_names.add(cand.lower())
                    break
            if not full_name:
                full_name = f"Agent {forced_surname or 'Vanguard'} {global_idx + 1}"
                used_names.add(full_name.lower())

            npc_id = full_name.lower().replace(" ", "_").replace(".", "")
            char_race = normalize_race("", scen_key, seed=f"{session_id}:agent:{ forced_surname.lower() if forced_surname else npc_id }")

            drive = AGENT_DRIVES[(seed_base + global_idx * 7) % len(AGENT_DRIVES)]
            friction = AGENT_FRICTIONS[(seed_base + global_idx * 11 + 3) % len(AGENT_FRICTIONS)]
            quirk = AGENT_QUIRKS[(seed_base + global_idx * 13 + 5) % len(AGENT_QUIRKS)]

            agent_class = bp["agent_class"]
            innate_abilities = get_anomalous_starting_innate_abilities(
                agent_class,
                scenario=scen_key,
                class_description=bp.get("role", ""),
                seed=f"{session_id}:{npc_id}:{agent_class}",
            )

            hq_node_id = str(bp.get("hq_node_id") or "").strip()
            hangout_node_id = str(bp.get("hangout_node_id") or "").strip()
            primary_facility = f"{hq_location} ➔ {bp['hq_room']}"
            raw_hangout = bp["city_hangout"]
            try:
                from mechanics.world.locations import resolve_session_location_tokens, format_node_hierarchy
                raw_hangout = resolve_session_location_tokens(session_id or 0, raw_hangout, scen_key)
                if session_id:
                    if hq_node_id:
                        fmt_p = format_node_hierarchy(session_id, hq_node_id)
                        if fmt_p and not fmt_p.startswith(("loc_", "zone_", "sub_")):
                            primary_facility = fmt_p
                    resolved_h_nid = hangout_node_id or db.resolve_node_id_from_location(session_id, raw_hangout) or ""
                    if resolved_h_nid:
                        fmt_h = format_node_hierarchy(session_id, resolved_h_nid)
                        if fmt_h and not fmt_h.startswith(("loc_", "zone_", "sub_")):
                            raw_hangout = fmt_h
                        if not hangout_node_id:
                            hangout_node_id = resolved_h_nid
            except Exception:
                pass
            secondary_facility = raw_hangout
            personality_summary = (
                f"{bp['summary']} ({faction_name} — {rank_title}, Tier {agent_tier}). "
                f"Drive: {drive} Flaw: {friction} Mannerism: {quirk}"
            )

            outfit_by_faction = {
                "public_agency": f"Standard-issue {faction_name} dark charcoal field trenchcoat with a silver containment badge",
                "private_agency_1": f"Bespoke ballistic executive suit bearing the {faction_name} crest",
                "private_agency_2": f"Tactical urban harness over designer streetwear with {faction_name} insignia",
                "monastic_order": f"Traditional purified hakama and haori layered with braided warding cords of the {faction_name}",
                "cult_faction": "Dark hooded urban overcoat lined with geometric occult stitching",
                "clandestine_faction": "Matte-black covert operator jacket with concealed relic holsters",
            }
            appearance = normalize_appearance(
                {"outfit_style": outfit_by_faction.get(faction_id, "Modern tactical field attire")},
                gender=gender,
                race=char_race,
                scen_key=scen_key,
                desc=bp["summary"],
            )

            roster.append({
                "session_id": session_id,
                "npc_id": npc_id,
                "name": full_name,
                "gender": gender,
                "race": char_race,
                "role": bp["role"],
                "agent_class": agent_class,
                "agent_tier": agent_tier,
                "promotion_tier": agent_tier,
                "rank_title": rank_title,
                "faction_id": faction_id,
                "faction_archetype_key": faction_id,
                "faction_name": faction_name,
                "division": bp["division"],
                "grade": f"Tier {agent_tier} ({rank_title})",
                "club": faction_name,
                "clique": bp["division"],
                "primary_facility": primary_facility,
                "secondary_facility": secondary_facility,
                "primary_node_id": hq_node_id,
                "secondary_node_id": hangout_node_id,
                "sibling_name": "",
                "personality_summary": personality_summary,
                "mannerisms": quirk,
                "speech_style": "Crisp, professional field vernacular with dry urban wit.",
                "innate_abilities": innate_abilities,
                "appearance": appearance,
                "is_special_agent": True,
                "anomalous_npc_tag": "special_agent",
                "is_hydrated": 0,
            })
            global_idx += 1

    # Wire the 4 cross-faction sibling pairs
    # Offsets:
    # public_agency: 0..11 (12)
    # private_agency_1: 12..17 (6)
    # private_agency_2: 18..23 (6)
    # monastic_order: 24..31 (8)
    # cult_faction: 32..37 (6)
    # clandestine_faction: 38..43 (6)
    cross_sibling_pairs = [
        (3, 14),   # Public Agency idx 3 <-> Private Agency 1 idx 2
        (6, 36),   # Public Agency idx 6 <-> Cult Faction idx 4
        (21, 42),  # Private Agency 2 idx 3 <-> Clandestine Faction idx 4
        (26, 8),   # Monastic Order idx 2 <-> Public Agency idx 8
    ]
    for idx_a, idx_b in cross_sibling_pairs:
        if idx_a < len(roster) and idx_b < len(roster):
            a, b = roster[idx_a], roster[idx_b]
            a["sibling_name"] = b["name"]
            b["sibling_name"] = a["name"]
            a["race"] = b["race"]
            a["personality_summary"] += f" Family: Estranged sibling of {b['name']} ({b['faction_name']})."
            b["personality_summary"] += f" Family: Estranged sibling of {a['name']} ({a['faction_name']})."

    return roster


def ensure_anomalous_agent_roster(session_id: int, scen_key: str = "") -> List[Dict[str, Any]]:
    """
    Ensures the 44 Special Agents are generated and synced into:
    1. `session['extra']['anomalous_agent_roster']`
    2. `school_directory` (for fast facility ambient lookup and codex directory fallback)
    3. `factions` table (`leadership_roster` and `members` for each of the 6 Fixed Factions)
    4. `lorebook` (`entity_type='person'`) for faction leaders and same-faction colleagues
    """
    if not session_id:
        return []

    sess = db.get_session(session_id) or {}
    if not scen_key:
        scen_key = str(sess.get("scenario") or "anomalous_incursions")
    if not scenario_data.is_anomalous_incursions_scenario(scen_key):
        return []

    existing_roster = sess.get("anomalous_agent_roster") or (
        sess.get("extra", {}).get("anomalous_agent_roster") if isinstance(sess.get("extra"), dict) else None
    )
    if isinstance(existing_roster, list) and len(existing_roster) == 44:
        prune_unmet_preseeded_special_agents(session_id)
        return existing_roster

    try:
        from mechanics.world.locations.graph_seeder import ensure_session_spatial_graph_seeded
        ensure_session_spatial_graph_seeded(session_id, scen_key)
    except Exception:
        pass

    from mechanics.social.factions import get_anomalous_faction_state, infer_anomalous_faction_archetype
    fac_state = get_anomalous_faction_state(session_id)
    player_faction_arch = str(fac_state.get("faction_archetype_key") or "public_agency").strip()

    factions = db.get_factions(session_id) or []
    roster = generate_anomalous_special_agents_roster(session_id, scen_key=scen_key, factions=factions)

    # 1. Persist in session extra
    db.update_session(session_id, extra={"anomalous_agent_roster": roster})

    # 2. Save in school_directory table for facility-based ambient presence & directory lookup
    try:
        db.save_school_roster(session_id, roster)
    except Exception:
        pass

    # 3. Sync each faction's leadership_roster and members list with its real Special Agents
    player_faction_id = player_faction_arch
    by_faction: Dict[str, List[Dict[str, Any]]] = {}
    for ag in roster:
        by_faction.setdefault(ag["faction_id"], []).append(ag)

    for fac in factions:
        fid = str(fac.get("faction_id") or "").strip()
        f_arch = str(fac.get("faction_archetype_key") or infer_anomalous_faction_archetype(fac) or fid).strip()
        f_name = str(fac.get("name") or "").strip()
        fac_agents = by_faction.get(f_arch, []) or by_faction.get(fid, [])
        if not fac_agents and f_name:
            for k_id, k_list in by_faction.items():
                if k_list and k_list[0].get("faction_name", "").lower() == f_name.lower():
                    fac_agents = k_list
                    break
        if not fac_agents:
            continue

        # Sort highest tier first
        fac_agents_sorted = sorted(fac_agents, key=lambda x: int(x.get("agent_tier", 1)), reverse=True)
        leadership_roster = []
        members_list = []
        from mechanics.combat.spells.registry import get_spell
        for ag in fac_agents_sorted:
            ability_names = []
            for s in (ag.get("innate_abilities") or []):
                if isinstance(s, dict) and s.get("name"):
                    ability_names.append(s["name"])
                elif isinstance(s, str):
                    sp_meta = get_spell(s)
                    ability_names.append(sp_meta["name"] if sp_meta and sp_meta.get("name") else s)
            leadership_roster.append({
                "rank": int(ag["agent_tier"]),
                "title": f"{ag['rank_title']} — {ag['role']}",
                "name": ag["name"],
                "agent_class": ag["agent_class"],
                "agent_tier": int(ag["agent_tier"]),
                "innate_abilities": ability_names,
                "is_player": False,
                "is_vacant": False,
            })
            members_list.append(ag["name"])

        leader_name = fac_agents_sorted[0]["name"] if fac_agents_sorted else ""
        try:
            db.upsert_faction(
                session_id=session_id,
                name=f_name,
                leader=leader_name,
                members=members_list,
                leadership_roster=leadership_roster,
                faction_id=fid,
            )
        except Exception:
            pass

    # 4. Upsert all 44 Special Agents into lorebook as background world reference only.
    # Never pre-populate unmet colleagues into contacts; characters only appear in Known Characters / Contacts once met or connected.
    for ag in roster:
        try:
            db.upsert_lorebook_entity(
                session_id=session_id,
                entity_type="person",
                name=ag["name"],
                description=ag["personality_summary"],
                disposition="friendly" if ag["faction_id"] == player_faction_id else ("cautious" if ag["faction_id"] in ("cult_faction", "clandestine_faction") else "neutral"),
                faction=ag["faction_name"],
                traits=[ag["role"], ag["agent_class"], f"Tier {ag['agent_tier']} {ag['rank_title']}"],
                motivation=ag["division"],
                mannerisms=ag["mannerisms"],
                race=ag["race"],
                appearance=ag["appearance"],
                gender=ag["gender"],
            )
        except Exception:
            pass

    prune_unmet_preseeded_special_agents(session_id)
    return roster


def prune_unmet_preseeded_special_agents(session_id: int) -> int:
    """
    Heals legacy pre-seeded Anomalous Incursions colleague rows in `contacts`:
    1. Deletes unmet 0-affinity pre-seeded Special Agent rows (ignoring auto-generated Past History lore)
       if the player has never met them in-scene, built affinity, or messaged them.
    2. Strips stale pre-seeded `contact_added` / `is_contact` flags from met `< 100` Special Agents
       who lack explicit provenance (`exchanged_contact`, `added_via_peerpulse`, `unlocked_via_friendship`)
       so they remain in `Known Characters` without polluting `Contacts` or `Messenger`.
    """
    if not session_id:
        return 0
    healed = 0
    try:
        sess = db.get_session(session_id) or {}
        scen_key = str(sess.get("scenario") or "")
        if not scenario_data.is_anomalous_incursions_scenario(scen_key):
            return 0
        from mechanics.social.relationships import (
            collect_met_npc_names,
            is_unmet_preseeded_special_agent,
        )
        party_npcs = db.get_session_party_npcs(session_id) or []
        party_names = {
            str(p.get("name", "")).strip().lower()
            for p in party_npcs
            if isinstance(p, dict) and p.get("name")
        }
        met_names = collect_met_npc_names(sess, party_npcs=party_npcs)

        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM contacts WHERE session_id=?",
                (session_id,),
            ).fetchall()
            ids_to_delete: List[int] = []
            updates_to_heal: List[Tuple[str, int]] = []
            for r in rows:
                d = dict(r)
                try:
                    b_info = json.loads(d.get("basic_info_json") or "{}")
                except Exception:
                    b_info = {}
                if not isinstance(b_info, dict):
                    continue
                is_agent = bool(
                    b_info.get("is_special_agent")
                    or b_info.get("anomalous_npc_tag") == "special_agent"
                )
                if not is_agent:
                    continue
                d["basic_info"] = b_info
                d["recent_memories"] = d.get("recent_memories_json") or ""
                d["intimate_memories"] = d.get("intimate_memories_json") or ""
                d["rel_history"] = d.get("rel_history_json") or ""
                score = int(d.get("relationship_score", 0) or 0)

                npc_id_low = str(d.get("npc_id") or "").strip().lower()
                name_low = str(d.get("name") or "").strip().lower()
                has_msg = False
                try:
                    msg_row = conn.execute(
                        "SELECT 1 FROM phone_messages WHERE session_id=? AND (LOWER(npc_id)=? OR LOWER(npc_id)=?) LIMIT 1",
                        (session_id, npc_id_low, name_low),
                    ).fetchone()
                    has_msg = bool(msg_row)
                except Exception:
                    has_msg = False

                if (
                    b_info.get("contact_added")
                    and is_unmet_preseeded_special_agent(d, met_in_story_names=met_names, party_names=party_names)
                    and not has_msg
                    and d.get("id") is not None
                ):
                    ids_to_delete.append(int(d["id"]))
                    continue

                # Heal met < 100 Special Agents with stale pre-seeded contact_added lacking explicit provenance
                has_explicit_unlock = bool(
                    score >= 100
                    or b_info.get("exchanged_contact")
                    or b_info.get("added_via_peerpulse")
                    or b_info.get("unlocked_via_friendship")
                )
                if not has_explicit_unlock and (b_info.get("contact_added") or b_info.get("is_contact")) and d.get("id") is not None:
                    b_clean = dict(b_info)
                    b_clean.pop("contact_added", None)
                    b_clean.pop("is_contact", None)
                    updates_to_heal.append((json.dumps(b_clean), int(d["id"])))

            for cid in ids_to_delete:
                conn.execute("DELETE FROM contacts WHERE id=?", (cid,))
                healed += 1
            for new_b_json, cid in updates_to_heal:
                conn.execute("UPDATE contacts SET basic_info_json=? WHERE id=?", (new_b_json, cid))
                healed += 1
    except Exception:
        pass
    return healed


def hydrate_faction_colleagues_to_contacts(session_id: int, faction_archetype_key: str, scen_key: str = "") -> int:
    """
    Ensures the Special Agents roster exists and syncs faction metadata ONLY onto colleagues
    whom the player has already met/registered in contacts (never pre-adding unmet strangers).
    """
    if not session_id or not faction_archetype_key or faction_archetype_key == "freelancer":
        return 0
    roster = ensure_anomalous_agent_roster(session_id, scen_key=scen_key)
    existing_contacts = db.get_contacts(session_id, resolve_relations=False, ensure_scene=False) or []
    existing_by_name = {
        str(c.get("name") or "").strip().lower(): c
        for c in existing_contacts
        if c.get("name")
    }
    count = 0
    for ag in roster:
        if ag.get("faction_id") == faction_archetype_key:
            matched_c = existing_by_name.get(str(ag.get("name") or "").strip().lower())
            if not matched_c:
                continue
            try:
                cur_binfo = dict(matched_c.get("basic_info") or {})
                cur_binfo.update({
                    "role": f"{ag['rank_title']} ({ag['role']})",
                    "occupation": ag["role"],
                    "agent_class": ag["agent_class"],
                    "agent_tier": ag["agent_tier"],
                    "rank_title": ag["rank_title"],
                    "faction": ag["faction_name"],
                    "faction_id": ag["faction_id"],
                    "division": ag["division"],
                    "primary_facility": ag["primary_facility"],
                    "secondary_facility": ag["secondary_facility"],
                    "primary_node_id": ag.get("primary_node_id", ""),
                    "secondary_node_id": ag.get("secondary_node_id", ""),
                    "is_special_agent": True,
                    "anomalous_npc_tag": "special_agent",
                })
                db.upsert_contact(
                    session_id=session_id,
                    character_id=int(matched_c.get("character_id", 0) or 0),
                    npc_id=matched_c.get("npc_id") or ag["npc_id"],
                    name=ag["name"],
                    delta_score=0,
                    race=ag["race"],
                    gender=ag["gender"],
                    appearance=ag["appearance"],
                    basic_info=cur_binfo,
                    track=matched_c.get("track", "platonic"),
                )
                count += 1
            except Exception:
                pass
    return count


def find_special_agent_by_name(session_id: int, npc_name: str, scen_key: str = "") -> Optional[Dict[str, Any]]:
    """Finds a pre-generated Special Agent by name or npc_id."""
    if not session_id or not npc_name:
        return None
    roster = ensure_anomalous_agent_roster(session_id, scen_key=scen_key)
    target = npc_name.strip().lower()
    target_id = target.replace(" ", "_").replace(".", "")
    for ag in roster:
        if ag.get("name", "").strip().lower() == target or ag.get("npc_id", "").strip().lower() == target_id:
            return ag
    return None


def evaluate_anomalous_companion_recruitment(
    session: Dict[str, Any],
    user_id: int,
    matched_contact: Dict[str, Any],
    affinity_score: int,
    char_level: int = 1,
) -> Dict[str, Any]:
    """
    Evaluates the Rank & Affinity Companion Recruitment Matrix for Anomalous Incursions:
    - Same-Faction Agent with `agent_tier <= player_tier`:
      `0G` Free Immediate Requisition (even at 0 affinity).
    - Same-Faction Senior Agent (`agent_tier > player_tier`):
      Requires Friend / Trusted Affinity (`affinity_score >= 100`) to join for `0G`.
    - Friendly Cross-Faction Agent (`public_agency`, `private_agency_1`, `private_agency_2`, `monastic_order`):
      - `affinity_score >= 100`: `0G` Free Joint-Op Companion.
      - `60 <= affinity_score < 100`: Paid Joint-Op Retainer (`get_recruitment_cost`).
      - `affinity_score < 60`: Requires at least Friendly standing (`60+` Affinity) for cross-agency joint operations.
    - Distrusted Faction Operative (`cult_faction`, `clandestine_faction`):
      - If player belongs to that same faction and `agent_tier <= player_tier`: `0G` Free Requisition.
      - Otherwise requires Close Friend / Covert Defector standing (`affinity_score >= 150`).
    """
    from mechanics.social.relationships import get_recruitment_cost

    sess_id = int(session.get("id") or 0)
    scen_key = str(session.get("scenario") or "anomalous_incursions")
    from mechanics.social.factions import get_anomalous_faction_state
    fac_state = get_anomalous_faction_state(sess_id, user_id=user_id) if sess_id else (session.get("anomalous_faction_state") or {})

    player_faction_id = str(fac_state.get("faction_archetype_key") or "public_agency").strip()
    player_tier = int(fac_state.get("promotion_tier", 1) or 1)

    npc_name = str(matched_contact.get("name") or "Operative").strip()
    basic_info = matched_contact.get("basic_info") if isinstance(matched_contact.get("basic_info"), dict) else {}

    if basic_info.get("deceased") or matched_contact.get("deceased") or matched_contact.get("is_dead"):
        return {
            "allowed": False,
            "cost": 0,
            "anomalous_npc_tag": "civilian",
            "reason": f"{npc_name} is deceased and cannot be recruited.",
        }

    from mechanics.social.anomalous_npc_tags import (
        TAG_CIVILIAN,
        TAG_SPECIAL_AGENT,
        classify_anomalous_npc_tag,
        hydrate_anomalous_npc_profile,
    )
    npc_tag = classify_anomalous_npc_tag(matched_contact, session_id=sess_id, scen_key=scen_key)
    if npc_tag == TAG_CIVILIAN:
        return {
            "allowed": False,
            "cost": 0,
            "anomalous_npc_tag": TAG_CIVILIAN,
            "is_civilian_blocked": True,
            "reason": (
                f"{npc_name} is a Civilian without awakened mana reserves or barrier protection. "
                f"Civilians can remain personal Contacts, but cannot be recruited into field combat parties."
            ),
        }

    hydrated = hydrate_anomalous_npc_profile(
        matched_contact,
        session_id=sess_id,
        scen_key=scen_key,
        player_level=char_level,
        is_party_companion=True,
    )

    special_agent = find_special_agent_by_name(sess_id, npc_name, scen_key=scen_key)
    agent_faction_id = str(
        (special_agent or {}).get("faction_id")
        or hydrated.get("faction_id")
        or basic_info.get("faction_id")
        or ""
    ).strip()
    agent_tier = int(
        (special_agent or {}).get("agent_tier")
        or hydrated.get("agent_tier")
        or basic_info.get("agent_tier")
        or 1
    )
    agent_rank_title = str(
        (special_agent or {}).get("rank_title")
        or hydrated.get("rank_title")
        or basic_info.get("rank_title")
        or f"Tier {agent_tier} Operative"
    )
    agent_faction_name = str(
        (special_agent or {}).get("faction_name")
        or hydrated.get("faction_name")
        or basic_info.get("faction")
        or agent_faction_id.replace("_", " ").title()
    )
    innate_abilities = list(
        (special_agent or {}).get("innate_abilities")
        or hydrated.get("innate_abilities")
        or basic_info.get("innate_abilities")
        or []
    )
    agent_class = str(
        (special_agent or {}).get("agent_class")
        or hydrated.get("agent_class")
        or basic_info.get("agent_class")
        or basic_info.get("role")
        or "Special Agent"
    )

    base_companion_payload = {
        "anomalous_npc_tag": TAG_SPECIAL_AGENT,
        "is_special_agent": True,
        "agent_tier": agent_tier,
        "rank_title": agent_rank_title,
        "agent_class": agent_class,
        "faction_id": agent_faction_id,
        "faction_name": agent_faction_name,
        "innate_abilities": innate_abilities,
        "hp": hydrated["hp"],
        "max_hp": hydrated["max_hp"],
        "mp": hydrated["mp"],
        "max_mp": hydrated["max_mp"],
        "level": hydrated["level"],
        "stats": hydrated["stats"],
        "weapon_profile": hydrated["weapon_profile"],
    }

    # Case 0: Independent / Freelance Special Agent (can be hired for cash OR recruited via Friend 100+ affinity)
    if agent_faction_id in ("", "freelancer"):
        if affinity_score >= 100:
            return {
                "allowed": True,
                "cost": 0,
                "reason": f"Independent Special Agent {npc_name} joined your squad for 0G (Friend standing: {affinity_score} Affinity).",
                **base_companion_payload,
            }
        if affinity_score >= 0:
            rec_cost = get_recruitment_cost(affinity_score, level=max(char_level, agent_tier))
            return {
                "allowed": True,
                "cost": rec_cost,
                "reason": f"Freelance field retainer contract with Special Agent {npc_name} ({rec_cost}G).",
                **base_companion_payload,
            }
        return {
            "allowed": False,
            "cost": 0,
            "anomalous_npc_tag": TAG_SPECIAL_AGENT,
            "reason": f"{npc_name} distrusts you (Affinity {affinity_score} < 0) and refuses a freelance field contract.",
        }

    # Case 1: Same Faction Colleague
    if player_faction_id and player_faction_id != "freelancer" and agent_faction_id == player_faction_id:
        if agent_tier <= player_tier:
            return {
                "allowed": True,
                "cost": 0,
                "reason": f"Requisitioned same-faction colleague ({agent_rank_title}, Tier {agent_tier} <= your Tier {player_tier}) for 0G.",
                **base_companion_payload,
            }
        # Senior agent in same faction (agent_tier > player_tier)
        if affinity_score >= 100:
            return {
                "allowed": True,
                "cost": 0,
                "reason": f"Senior colleague {npc_name} (Tier {agent_tier}) joined via personal trust (Affinity {affinity_score} >= 100).",
                **base_companion_payload,
            }
        return {
            "allowed": False,
            "cost": 0,
            "anomalous_npc_tag": TAG_SPECIAL_AGENT,
            "reason": (
                f"{npc_name} outranks you within {agent_faction_name} (Tier {agent_tier} {agent_rank_title} vs your Tier {player_tier}). "
                f"Earn Promotion Tier {agent_tier} to requisition them by rank, or reach Friend standing (100 Affinity; currently {affinity_score})."
            ),
        }

    # Case 2: Distrusted Faction Operative (Cult or Clandestine Syndicate)
    if agent_faction_id in ("cult_faction", "clandestine_faction"):
        if affinity_score >= 150:
            return {
                "allowed": True,
                "cost": 0,
                "reason": f"Covert ally {npc_name} ({agent_faction_name}) joined your squad through deep personal loyalty (Affinity {affinity_score} >= 150).",
                **base_companion_payload,
            }
        return {
            "allowed": False,
            "cost": 0,
            "anomalous_npc_tag": TAG_SPECIAL_AGENT,
            "reason": (
                f"{npc_name} belongs to {agent_faction_name} (Distrusted Organization). "
                f"Recruiting a covert operative from a distrusted faction requires Close Friend / Defector standing (150 Affinity; currently {affinity_score}) or membership in their organization."
            ),
        }

    # Case 3: Friendly Cross-Faction Special Agent
    if affinity_score >= 100:
        return {
            "allowed": True,
            "cost": 0,
            "reason": f"Cross-agency ally {npc_name} joined for 0G (Friend standing: {affinity_score} Affinity).",
            **base_companion_payload,
        }
    if affinity_score >= 60:
        rec_cost = get_recruitment_cost(affinity_score, level=char_level)
        return {
            "allowed": True,
            "cost": rec_cost,
            "reason": f"Joint-operation retainer with {npc_name} ({agent_faction_name}).",
            **base_companion_payload,
        }

    return {
        "allowed": False,
        "cost": 0,
        "anomalous_npc_tag": TAG_SPECIAL_AGENT,
        "reason": (
            f"{npc_name} ({agent_faction_name or 'Independent'}) requires at least Friendly standing (60 Affinity for paid joint-op retainer, "
            f"or 100 Affinity for free recruitment; currently {affinity_score})."
        ),
    }


def generate_agent_schedule_activity(
    agent: Dict[str, Any],
    phase: str,
    is_imminent: bool,
    next_phase: str,
    location_str: str,
    current_minute: int = 480,
    active_incursion: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generates an evocative, faction- and schedule-grounded activity snippet for Special Agent prompt injection.
    """
    loc_low = str(location_str or "").lower()
    fac_id = str(agent.get("faction_id") or "").lower()
    role_low = str(agent.get("role") or "").lower()
    safe_min = int(current_minute or 480) % 1440

    if active_incursion and not active_incursion.get("resolved"):
        ent_name = str(active_incursion.get("entity_name") or "anomalous signature")
        if fac_id in ("cult_faction", "clandestine_faction"):
            return f"Observing the {ent_name} perimeter from the shadows while recording resonance telemetry"
        if fac_id == "monastic_order":
            return f"Tracing paper-talisman boundary wards around the {ent_name} distortion perimeter"
        return f"Establishing a field containment cordon and scanning residual readings around {ent_name}"

    if any(k in loc_low for k in ("theme park", "amusement resort", "mirror", "carousel")) and (safe_min >= 1320 or safe_min < 480):
        if fac_id == "cult_faction":
            return "Listening reverently to the reversed calliope static inside the nighttime Anomalous Shift"
        return "Sweeping the warped carnival midway with a cold-iron resonance meter during the 22:00 Anomalous Shift"

    if is_imminent:
        if next_phase == "lunch":
            return "Wrapping up morning anomaly telemetry logs before heading out for midday rations"
        if next_phase == "afternoon":
            return "Checking encrypted dispatch alerts on phone before returning to afternoon duty"
        if next_phase == "evening":
            if fac_id in ("cult_faction", "clandestine_faction"):
                return "Checking covert dead-drop coordinates ahead of nocturnal operations"
            return "Signing off daytime containment logs and stowing field gear for off-duty evening hours"
        if next_phase == "night":
            if fac_id in ("cult_faction", "clandestine_faction"):
                return "Donning covert nocturnal gear as citywide rift frequencies spike after dusk"
            return "Handing over sector patrol keys to the incoming night-watch shift"

    if fac_id == "monastic_order":
        if any(k in loc_low for k in ("pagoda", "worship", "torii", "temple")):
            return "Inscribing purifying vermilion seals and tending sacred ward-braziers"
        if "onsen" in loc_low or "tea" in loc_low:
            return "Steeping ceremonial bamboo tea while centering spiritual aura between exorcism patrols"
        if "subway" in loc_low or "under-city" in loc_low:
            return "Patrolling the echoing subterranean concourse with blessed paper shikigami charms"

    if fac_id == "cult_faction":
        if any(k in loc_low for k in ("sanctum", "altar", "cloister", "reliquary", "cells")):
            return "Cataloging rift-harmonic frequencies beneath low candlelight in the hidden sanctum"
        return "Blending discreetly into the urban crowd while monitoring subtle ley-line tremors"

    if fac_id == "clandestine_faction":
        if any(k in loc_low for k in ("brokerage", "black-ledger", "auction", "guardroom", "cognitohazard")):
            return "Verifying encrypted syndicate ledgers and stripped containment serial plates"
        return "Keeping a quiet watch on the entrance while exchanging coded messages on a burner handset"

    if any(k in loc_low for k in ("dispatch", "executive", "contract")):
        return "Reviewing live metropolitan rift-spike maps and coordinating squad deployments"
    if any(k in loc_low for k in ("armory", "outfitter", "ordnance")):
        return "Calibrating cold-iron suppressors and inspecting warded ballistic field rigs"
    if any(k in loc_low for k in ("research", "forensics", "medical", "detox")):
        return "Running spectral frequency diagnostics on sealed containment samples"
    if any(k in loc_low for k in ("training", "calibration")):
        return "Running live-fire breach drills and psychic dampening reflex tests"
    if any(k in loc_low for k in ("canteen", "espresso", "ramen", "food", "roastery", "konbini", "convenience")):
        return "Drinking strong black coffee off-shift while skimming dispatch briefings"
    if any(k in loc_low for k in ("jazz", "lounge", "billiards", "arcade", "cigar", "parlor")):
        return "Unwinding off-duty while keeping one ear tuned to encrypted agency comms"

    return "Monitoring handheld anomaly resonance readings while on metropolitan station duty"


def get_anomalous_facility_ambient_agents(
    session_id: int,
    current_location: str,
    limit: int = 2,
    current_day: Optional[int] = None,
    current_minute: Optional[int] = None,
    active_npc_names: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Returns up to `limit` Special Agents scheduled at (or converging on an active incursion at)
    `current_location` for the current day and minute in `anomalous_incursions` scenarios.
    """
    if not session_id or not current_location:
        return []

    sess = db.get_session(session_id) or {}
    scen_key = str(sess.get("scenario") or "anomalous_incursions")
    if not scenario_data.is_anomalous_incursions_scenario(scen_key):
        return []

    safe_day = int(current_day) if current_day is not None else int(sess.get("current_day") or 1)
    safe_min = int(current_minute) if current_minute is not None else int(sess.get("current_minute") or 480)
    safe_active = {str(n).lower().strip() for n in active_npc_names if n} if active_npc_names else set()

    if isinstance(sess.get("party"), list):
        for pm in sess["party"]:
            if isinstance(pm, dict) and pm.get("name"):
                safe_active.add(str(pm["name"]).lower().strip())

    roster = ensure_anomalous_agent_roster(session_id, scen_key=scen_key)
    if not roster:
        return []

    from mechanics.world.schedules import (
        get_detailed_npc_time_phase,
        is_schedule_transition_imminent,
        get_npc_scheduled_node_id,
        get_npc_scheduled_location,
    )
    from mechanics.world.waypoints import check_location_matches_waypoint

    phase = get_detailed_npc_time_phase(safe_min, current_day=safe_day, scen_key=scen_key)
    is_imminent, _, next_block, _ = is_schedule_transition_imminent(
        safe_min, window_minutes=15, current_day=safe_day, scen_key=scen_key
    )
    curr_node_id = sess.get("current_node_id") or db.resolve_node_id_from_location(session_id, current_location)
    if curr_node_id and current_location:
        resolved_loc_nid = db.resolve_node_id_from_location(session_id, current_location)
        if resolved_loc_nid:
            curr_node_id = resolved_loc_nid

    eligible: List[Dict[str, Any]] = []
    for ag in roster:
        ag_name = str(ag.get("name") or "").strip()
        ag_id = str(ag.get("npc_id") or "").strip().lower()
        if not ag_name or ag_name.lower() in safe_active or ag_id in safe_active:
            continue

        sched_nid = get_npc_scheduled_node_id(
            ag, current_minute=safe_min, scen_key=scen_key, current_day=safe_day, session_id=session_id
        )
        matched = False
        if sched_nid and curr_node_id:
            matched = (
                sched_nid == curr_node_id
                or db.is_descendant_of(session_id, curr_node_id, sched_nid)
                or db.is_descendant_of(session_id, sched_nid, curr_node_id)
            )
        if not matched:
            sched_loc = get_npc_scheduled_location(
                ag, current_minute=safe_min, scen_key=scen_key, session_id=session_id, current_day=safe_day
            )
            if sched_loc:
                matched = check_location_matches_waypoint(
                    current_location, sched_loc, session_id=session_id, current_node_id=curr_node_id
                )
        if matched:
            eligible.append(ag)

    # Check if there is an active Daily Anomalous Incursion here for field responder convergence
    active_inc = None
    try:
        from mechanics.world.anomalous_events import get_active_incursion_at_location
        active_inc = get_active_incursion_at_location(session_id, current_location)
    except Exception:
        active_inc = None

    from mechanics.social.factions import get_anomalous_faction_state
    fac_state = get_anomalous_faction_state(session_id)
    player_fac = str(fac_state.get("faction_archetype_key") or "public_agency")
    contacts = db.get_contacts(session_id) or []
    contact_scores = {
        str(c.get("name") or "").strip().lower(): int(c.get("relationship_score") or c.get("affinity") or 0)
        for c in contacts if isinstance(c, dict) and c.get("name")
    }

    def _score_agent(cand: Dict[str, Any]) -> int:
        sc = 0
        nm_low = str(cand.get("name") or "").strip().lower()
        if cand.get("faction_id") == player_fac:
            sc += 300
        aff = contact_scores.get(nm_low, 0)
        if aff >= 40:
            sc += 250
        sib_low = str(cand.get("sibling_name") or "").strip().lower()
        if sib_low and (sib_low in safe_active or contact_scores.get(sib_low, 0) >= 40):
            sc += 200
        rot = int(hashlib.md5(f"{session_id}_{nm_low}_{safe_day}_{phase}".encode("utf-8")).hexdigest(), 16) % 100
        return sc + rot

    scored = sorted(eligible, key=_score_agent, reverse=True)
    selected = list(scored[:limit])

    # Field Incursion Convergence: 45% chance a field operative responds to an active Daily Incursion site
    if active_inc and len(selected) < limit:
        conv_roll = int(hashlib.md5(f"inc_{session_id}_{safe_day}_{current_location}".encode("utf-8")).hexdigest(), 16) % 100
        if conv_roll < 45:
            is_night_shift = (safe_min >= 1200 or safe_min < 420)
            valid_factions = (
                ("public_agency", "monastic_order", "cult_faction", "clandestine_faction")
                if is_night_shift
                else ("public_agency", "private_agency_1", "private_agency_2", "monastic_order")
            )
            sel_names = {str(x.get("name") or "").lower() for x in selected}
            pool = [
                a for a in roster
                if a.get("faction_id") in valid_factions
                and int(a.get("agent_tier", 1)) <= 3
                and str(a.get("name") or "").lower() not in safe_active
                and str(a.get("name") or "").lower() not in sel_names
            ]
            if pool:
                pick_idx = int(hashlib.md5(f"pick_{session_id}_{safe_day}_{safe_min}".encode("utf-8")).hexdigest(), 16) % len(pool)
                selected.append(pool[pick_idx])

    results: List[Dict[str, Any]] = []
    for ag in selected[:limit]:
        item = dict(ag)
        item["activity"] = generate_agent_schedule_activity(
            item,
            phase=phase,
            is_imminent=is_imminent,
            next_phase=next_block,
            location_str=current_location,
            current_minute=safe_min,
            active_incursion=active_inc,
        )
        results.append(item)
    return results


# Backwards-compatible aliases
ensure_anomalous_agent_roster_seeded = ensure_anomalous_agent_roster

