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
import logging
import random
from typing import Any, Dict, List, Optional, Tuple

import db
import namegen
import scenario_data

log = logging.getLogger(__name__)


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
        "role": "Chief Executive & Containment Portfolio Director",
        "agent_class": "Executive Containment Agent",
        "division": "Executive Board",
        "hq_room": "Global Contracts & Telemetry Floor",
        "hq_node_id": "sub_priv1_dispatch",
        "city_hangout": "Sovereign Hills & Sky-Estates ➔ Sky-High Penthouse Lounge ➔ 80th-Floor Infinity Pool & Cocktail Deck",
        "hangout_node_id": "sub_sky_infinity_bar",
        "summary": "Treats metropolitan anomaly neutralization as a blue-chip defense portfolio; directs high-floor asset acquisitions in bespoke Obsidian tailoring.",
    },
    {
        "agent_tier": 4,
        "role": "Operations Director & Strike Commander",
        "agent_class": "Asset Recovery Operator",
        "division": "Special Recovery Wing",
        "hq_room": "Simulated Breach & Ballistics Calibration Deck",
        "hq_node_id": "sub_priv1_training",
        "city_hangout": "International Airport & Airfield ➔ First-Class Executive Sky-Lounge & Capsule Hotel ➔ Panoramic Tarmac-View Champagne Bar",
        "hangout_node_id": "sub_ap_runway_bar",
        "summary": "Precision assault commander who drills squads on smart-linked VX-4 carbines and grades every breach against strict quarterly SLA benchmarks.",
    },
    {
        "agent_tier": 3,
        "role": "Lead Applied Ordnance Architect",
        "agent_class": "Applied Ordnance Specialist",
        "division": "Applied Anomalous Sciences",
        "hq_room": "Applied Anomalous Sciences & Cleanroom Lab",
        "hq_node_id": "sub_priv1_research",
        "city_hangout": "Sovereign Hills & Sky-Estates ➔ The Crimson Masquerade Auction House ➔ Candlelit Amphitheater & Caged Stage",
        "hangout_node_id": "sub_auction_amphitheater",
        "summary": "Calibrates PC-12 directed-pulse emitters in the tower cleanroom and secures volatile anomaly cores for high-margin defense patents.",
    },
    {
        "agent_tier": 3,
        "role": "Senior Skyline Overwatch Marksman",
        "agent_class": "Overwatch Telemetry Specialist",
        "division": "Orbital Overwatch Unit",
        "hq_room": "Special Ordnance & Requisition Vault",
        "hq_node_id": "sub_priv1_armory",
        "city_hangout": "City Center ➔ Sunken Plaza Galleria ➔ Glass Skywalk Dining Terrace",
        "hangout_node_id": "sub_plaza_terrace",
        "summary": "Unflappable high-altitude sharpshooter networked into orbital OptiLink feeds, calculating spatial refraction across three city blocks.",
    },
    {
        "agent_tier": 2,
        "role": "Senior Loss-Prevention Breacher",
        "agent_class": "Heavy Loss-Prevention Vanguard",
        "division": "Vault & Asset Security",
        "hq_room": "Ballistic Tailoring & Exo-Weave Atelier",
        "hq_node_id": "sub_priv1_outfitter",
        "city_hangout": "Downtown ➔ Neon Shopping Arcade & Mall ➔ Streetwear & Designer Apparel Boutique",
        "hangout_node_id": "sub_fashion_boutique",
        "summary": "Anchors high-risk containment cordons in Meridian exo-weave plate behind a Titan-series alloy shield.",
    },
    {
        "agent_tier": 1,
        "role": "Associate Portfolio Operative",
        "agent_class": "Asset Recovery Operator",
        "division": "Client Retainer Intake",
        "hq_room": "Atrium Concierge & Biometric Turnstiles",
        "hq_node_id": "sub_priv1_entrance",
        "city_hangout": "Downtown ➔ 24-Hour Arcade & Billiards Hall ➔ Upstairs Smoke-Hazy Billiards Lounge",
        "hangout_node_id": "sub_billiards_lounge",
        "summary": "Fast-track lateral hire under ironclad non-disclosure covenants, chasing high-tier containment commissions toward partner equity.",
    },
]

PRIVATE_AGENCY_2_BLUEPRINTS: List[Dict[str, Any]] = [
    {
        "agent_tier": 5,
        "role": "Principal & Founding Case Partner",
        "agent_class": "Private Case Investigator",
        "division": "Partner Management",
        "hq_room": "Partner Case Room & Dispatch Bullpen",
        "hq_node_id": "sub_priv2_dispatch",
        "city_hangout": "City Center ➔ Sunken Plaza Galleria ➔ Glass Skywalk Dining Terrace",
        "hangout_node_id": "sub_plaza_terrace",
        "summary": "Former municipal inspector who founded an independent partner-owned firm; vets sensitive private retainers over single-origin pour-over coffee.",
    },
    {
        "agent_tier": 4,
        "role": "Managing Partner & Master Gunsmith",
        "agent_class": "Close-Quarters Entry Specialist",
        "division": "Tactical Entry & Armory",
        "hq_room": "Vaulted Armory & Gunsmithing Bench",
        "hq_node_id": "sub_priv2_armory",
        "city_hangout": "City Docks & Harbor ➔ Automated Container Pier 12 ➔ Towering Gantry Crane Operator Cab",
        "hangout_node_id": "sub_pier_gantry",
        "summary": "Seasoned entry tactician and master gunsmith who hand-fits match barrels, tritium sights, and cold-iron loads for every specialist on the roster.",
    },
    {
        "agent_tier": 3,
        "role": "Senior Ward & Forensics Specialist",
        "agent_class": "Field Ward & Countermeasure Tech",
        "division": "Anomalous Forensics",
        "hq_room": "Anomalous Forensics & Ward Calibration Lab",
        "hq_node_id": "sub_priv2_research",
        "city_hangout": "City Center ➔ Sanctuary Antiquities & Licensed Wards ➔ Appraisal Desk & Leyline Map Table",
        "hangout_node_id": "sub_curio_appraisal",
        "summary": "Bench-calibrates dual-channel Hume readers and machines braided copper grounding spikes with watchmaker precision.",
    },
    {
        "agent_tier": 3,
        "role": "Senior Protective Escort Specialist",
        "agent_class": "Containment Escort Vanguard",
        "division": "Protective Operations",
        "hq_room": "Sound-Baffled Basement Firing Lane",
        "hq_node_id": "sub_priv2_training",
        "city_hangout": "Downtown ➔ Late-Night Ramen & Izakaya Alley ➔ Open-Kitchen Broth & Counter Hall",
        "hangout_node_id": "sub_ramen_counter_hall",
        "summary": "Steady close-protection veteran who holds subterranean breach thresholds behind a cold-iron-edged polycarbonate shield.",
    },
    {
        "agent_tier": 2,
        "role": "Licensed Retainer Investigator",
        "agent_class": "Licensed Field Specialist",
        "division": "Private Client Cases",
        "hq_room": "Timber-Beam Lounge & Pour-Over Kitchenette",
        "hq_node_id": "sub_priv2_canteen",
        "city_hangout": "Downtown ➔ Basement Jazz & Cocktail Bar ➔ Main Cocktail Lounge & Quartet Stage",
        "hangout_node_id": "sub_jazz_lounge",
        "summary": "Discreet field investigator in a tailored wool trenchcoat resolving delicate neighborhood and estate anomalies before headlines break.",
    },
    {
        "agent_tier": 1,
        "role": "Associate Investigator & Intake Liaison",
        "agent_class": "Private Case Investigator",
        "division": "Client Intake & Recon",
        "hq_room": "Brick-Front Vestibule & Security Reception",
        "hq_node_id": "sub_priv2_entrance",
        "city_hangout": "University & Parapsychology Campus ➔ Clocktower Archival Library & Rare Stacks ➔ Warded Iron Cage of Pre-Cataclysm Grimoires",
        "hangout_node_id": "sub_uni_forbidden_cage",
        "summary": "Sharp university parapsychology graduate managing client intake, silver-halide evidence logs, and preliminary recon sweeps.",
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
        "city_hangout": "Sacred Mountain Sanctuary & Onsen Quarter ➔ Eastern Grand Temple & Sanctuary ➔ Main Worship Hall & Incense Courtyard",
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
        "city_hangout": "Sacred Mountain Sanctuary & Onsen Quarter ➔ Eastern Grand Temple & Sanctuary ➔ Five-Story Pagoda & Sacred Reliquary",
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
        "city_hangout": "Sacred Mountain Sanctuary & Onsen Quarter ➔ Eastern Grand Temple & Sanctuary ➔ Zen Rock Garden & Bamboo Tea House",
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
        "city_hangout": "Wilderness Forest Reserve ➔ Pine Forest Hiking Trails ➔ Misty Ravine Suspension Footbridge",
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
        "city_hangout": "Sacred Mountain Sanctuary & Onsen Quarter ➔ Eastern Grand Temple & Sanctuary ➔ Sacred Mountain Hot Springs & Onsen Bathhouse",
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
        "city_hangout": "Sacred Mountain Sanctuary & Onsen Quarter ➔ Eastern Grand Temple & Sanctuary ➔ Grand Torii Gate & Omikuji Talisman Stand",
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


FACTION_ATTRIBUTE_WEIGHT_POOLS: Dict[str, Tuple[str, ...]] = {
    "monastic_order": ("aether", "wind", "water", "aether", "wind", "water", "ice", "fire"),
    "cult_faction": ("aether", "bio", "fire", "aether", "bio", "fire"),
    "public_agency": ("physical", "electric", "fire", "earth", "ice", "water", "wind", "aether", "bio"),
    "private_agency_1": ("electric", "aether", "ice", "physical", "fire", "earth"),
    "private_agency_2": ("physical", "fire", "earth", "wind", "electric", "bio"),
    "clandestine_faction": ("bio", "physical", "electric", "aether", "ice", "wind"),
    "freelancer": ("physical", "electric", "wind", "fire", "aether", "ice", "water", "earth", "bio"),
}

# ---------------------------------------------------------------------------
# 16 Pre-Generated Student Special Agent Blueprints for Anomalous High School
# - 4 per grade (Freshman, Sophomore, Junior, Senior)
# - 8 Independent Club Freelancers (1 per school club)
# - 8 Junior Agency-Affiliated Student Operatives (2 per major agency)
# ---------------------------------------------------------------------------
STUDENT_SPECIAL_AGENT_BLUEPRINTS: List[Dict[str, Any]] = [
    # --- 8 Independent Club Freelancer Student Operatives ---
    {
        "agent_tier": 3,
        "grade": "Senior",
        "role": "Honor-Roll Student & Freelance Operative",
        "agent_class": "Honor Roll Student",
        "faction_id": "freelancer",
        "club": "Student Council",
        "clique": "Academics",
        "primary_node_id": "loc_senior_class",
        "secondary_node_id": "loc_student_council",
        "city_hangout": "{session_school} ➔ Student Union & Cultural Arts Wing ➔ Student Council Office",
        "summary": "Immaculate student council honor student who reviews budget spreadsheets by day and takes high-risk Public Agency containment bounties after the 15:00 bell.",
    },
    {
        "agent_tier": 2,
        "grade": "Junior",
        "role": "Varsity Track Regular & Rift Runner",
        "agent_class": "Athletic Regular",
        "faction_id": "freelancer",
        "club": "Athletic Directorate",
        "clique": "Athletes",
        "primary_node_id": "loc_junior_class",
        "secondary_node_id": "loc_martial_arts_dojo",
        "city_hangout": "{session_school} ➔ Main Gymnasium & Athletic Complex ➔ Martial Arts Dojo",
        "summary": "Varsity athlete who hides a live-steel wakizashi in a taped-up shinai bag and uses after-school cardio runs to patrol suburban rift perimeters.",
    },
    {
        "agent_tier": 2,
        "grade": "Sophomore",
        "role": "Stagehand Regular & Illusion Breaker",
        "agent_class": "Class Sharpshooter",
        "faction_id": "freelancer",
        "club": "Drama & Theater Union",
        "clique": "Theater",
        "primary_node_id": "loc_sophomore_class",
        "secondary_node_id": "loc_auditorium",
        "city_hangout": "{session_school} ➔ Student Union & Cultural Arts Wing ➔ Auditorium Stage",
        "summary": "Unassuming backstage lighting tech who packs a folding takedown carbine in a violin case and hunts mirror-rift entities for freelance tuition money.",
    },
    {
        "agent_tier": 2,
        "grade": "Junior",
        "role": "Robotics Lab Regular & Coil Tech",
        "agent_class": "After-School Tinkerer",
        "faction_id": "freelancer",
        "club": "Science & Robotics Club",
        "clique": "Gamers",
        "primary_node_id": "loc_junior_class",
        "secondary_node_id": "loc_science_lab",
        "city_hangout": "{session_school} ➔ Main Academic Building & Classrooms ➔ Chemistry & Science Lab",
        "summary": "Solders custom EMF dampeners and gauss capacitors behind the chemistry fume hoods whenever the faculty advisor steps out.",
    },
    {
        "agent_tier": 3,
        "grade": "Senior",
        "role": "Library Archivist & Ward Scribe",
        "agent_class": "Quiet Bookworm",
        "faction_id": "freelancer",
        "club": "Occult & Folklore Society",
        "clique": "Loner",
        "primary_node_id": "loc_senior_class",
        "secondary_node_id": "loc_old_storage_3b",
        "city_hangout": "{session_school} ➔ Abandoned Old Campus Wing ➔ Old Storage Room 3-B",
        "summary": "Soft-spoken folklore archivist who keeps a consecrated silver athame tucked between pre-war town registries and catalogs campus spatial anomalies.",
    },
    {
        "agent_tier": 2,
        "grade": "Sophomore",
        "role": "Back-Row Truant & Alley Breacher",
        "agent_class": "Back-Row Rebel",
        "faction_id": "freelancer",
        "club": "Campus Delinquents",
        "clique": "Rebels",
        "primary_node_id": "loc_sophomore_class",
        "secondary_node_id": "sub_custodian_boiler_locker",
        "city_hangout": "{session_school} ➔ Abandoned Old Campus Wing ➔ Custodian's Boiler-Room Locker",
        "summary": "Sleeps through morning lectures with a scarred leather jacket over their shoulders, then clears tenement crawlers with a sawed-off scattergun at dusk.",
    },
    {
        "agent_tier": 1,
        "grade": "Freshman",
        "role": "Campus Radio Aide & Signal Spotter",
        "agent_class": "Honor Roll Student",
        "faction_id": "freelancer",
        "club": "Journalism & Media",
        "clique": "Media",
        "primary_node_id": "loc_freshman_class",
        "secondary_node_id": "loc_broadcast_room",
        "city_hangout": "{session_school} ➔ Student Union & Cultural Arts Wing ➔ Campus Broadcast & Newspaper Room",
        "summary": "First-year broadcast technician who triangulates cognitohazard numbers stations on the school radio array and sells coordinates to Public Agency dispatch.",
    },
    {
        "agent_tier": 1,
        "grade": "Freshman",
        "role": "Sketchbook Regular & Resonance Spotter",
        "agent_class": "Quiet Bookworm",
        "faction_id": "freelancer",
        "club": "Fine Arts Guild",
        "clique": "Artists",
        "primary_node_id": "loc_freshman_class",
        "secondary_node_id": "loc_art_studio",
        "city_hangout": "{session_school} ➔ Student Union & Cultural Arts Wing ➔ Art Studio",
        "summary": "Charcoal-stained freshman whose automatic sketches accurately predict dimensional fracture lines hours before instruments register a spike.",
    },
    # --- 8 Junior Agency-Affiliated Student Operatives ---
    {
        "agent_tier": 2,
        "grade": "Senior",
        "role": "Bureau Youth Cadet & Campus Liaison",
        "agent_class": "Honor Roll Student",
        "faction_id": "public_agency",
        "club": "Student Council",
        "clique": "Academics",
        "primary_node_id": "loc_senior_class",
        "secondary_node_id": "loc_hq_training_range",
        "city_hangout": "Public Anomaly Investigation Agency HQ ➔ Psychometric Training & Calibration Range",
        "summary": "Senior honor student holding a provisional Bureau youth badge; monitors academy resonance levels during class and reports to HQ after 15:00.",
    },
    {
        "agent_tier": 1,
        "grade": "Sophomore",
        "role": "Bureau Junior Field Scout",
        "agent_class": "Athletic Regular",
        "faction_id": "public_agency",
        "club": "Athletic Directorate",
        "clique": "Athletes",
        "primary_node_id": "loc_sophomore_class",
        "secondary_node_id": "loc_hq_main_lobby",
        "city_hangout": "Public Anomaly Investigation Agency HQ ➔ Main Lobby & Security Hub",
        "summary": "Sophomore sprinter recruited into the Bureau's youth auxiliary after surviving a commuter-train distortion incident.",
    },
    {
        "agent_tier": 2,
        "grade": "Senior",
        "role": "Sponsored Telemetry Scholar",
        "agent_class": "After-School Tinkerer",
        "faction_id": "private_agency_1",
        "club": "Science & Robotics Club",
        "clique": "Academics",
        "primary_node_id": "loc_senior_class",
        "secondary_node_id": "sub_priv1_training",
        "city_hangout": "{session_school} ➔ Main Academic Building & Classrooms ➔ Chemistry & Science Lab",
        "summary": "Top-ranked honors fellow on a conglomerate fellowship who benchmarks OptiLink smart-visors and gauss coil links during evening containment sweeps.",
    },
    {
        "agent_tier": 1,
        "grade": "Freshman",
        "role": "Junior Ballistics & Telemetry Fellow",
        "agent_class": "Class Sharpshooter",
        "faction_id": "private_agency_1",
        "club": "Journalism & Media",
        "clique": "Popular",
        "primary_node_id": "loc_freshman_class",
        "secondary_node_id": "sub_priv1_entrance",
        "city_hangout": "{session_school} ➔ Student Commons & Campus Cafeteria ➔ Central Courtyard",
        "summary": "Poised academy sharpshooter under executive non-disclosure covenants who syncs orbital ballistic feeds between afternoon classes.",
    },
    {
        "agent_tier": 2,
        "grade": "Junior",
        "role": "Apprentice Case Investigator",
        "agent_class": "Honor Roll Student",
        "faction_id": "private_agency_2",
        "club": "Journalism & Media",
        "clique": "Academics",
        "primary_node_id": "loc_junior_class",
        "secondary_node_id": "sub_priv2_dispatch",
        "city_hangout": "{session_school} ➔ Main Academic Building & Classrooms ➔ School Rooftop",
        "summary": "Observant campus journalist apprenticing under the firm's founding partners after school, cataloging silver-halide anomaly evidence and witness statements.",
    },
    {
        "agent_tier": 1,
        "grade": "Freshman",
        "role": "Apprentice Ward & Calibration Tech",
        "agent_class": "After-School Tinkerer",
        "faction_id": "private_agency_2",
        "club": "Science & Robotics Club",
        "clique": "Academics",
        "primary_node_id": "loc_freshman_class",
        "secondary_node_id": "sub_priv2_research",
        "city_hangout": "{session_school} ➔ Student Commons & Campus Cafeteria ➔ Shaded Vending Machine Pavilion",
        "summary": "Methodical robotics prodigy mentored in the firm's forensics lab, machining copper grounding spikes and calibrating handheld Hume readers.",
    },
    {
        "agent_tier": 2,
        "grade": "Junior",
        "role": "Shrine Heir & High School Exorcist",
        "agent_class": "Quiet Bookworm",
        "faction_id": "monastic_order",
        "club": "Occult & Folklore Society",
        "clique": "Loner",
        "primary_node_id": "loc_junior_class",
        "secondary_node_id": "loc_et_torii_approach",
        "city_hangout": "Sacred Mountain Sanctuary & Onsen Quarter ➔ Eastern Grand Temple & Sanctuary ➔ Grand Torii Gate & Omikuji Talisman Stand",
        "summary": "Heir to a mountain exorcist lineage who attends high school in a standard uniform while carrying ancestral sealing talismans in their bookbag.",
    },
    {
        "agent_tier": 1,
        "grade": "Sophomore",
        "role": "Novice Shrine Sword-Acolyte",
        "agent_class": "Athletic Regular",
        "faction_id": "monastic_order",
        "club": "Fine Arts Guild",
        "clique": "Artists",
        "primary_node_id": "loc_sophomore_class",
        "secondary_node_id": "loc_et_zen_tea_garden",
        "city_hangout": "{session_school} ➔ Student Union & Cultural Arts Wing ➔ Botanical Glasshouse & Garden",
        "summary": "Disciplined sophomore calligraphy student who practices sacred blade forms at dawn and wards campus stairwells after dusk.",
    },
]


def _resolve_agent_3axis_for_faction(
    faction_id: str,
    local_idx: int,
    agent_class: str,
    role: str,
    seed_str: str,
) -> Tuple[str, str, str]:
    import hashlib
    from mechanics.combat.spells.awakened_kits import (
        ABILITY_MEDIUMS,
        ANOMALOUS_ATTRIBUTES,
        COMBAT_ARCHETYPES,
        derive_default_3axis,
    )

    h = int(hashlib.md5(seed_str.encode("utf-8")).hexdigest()[:8], 16)
    f_hash = int(hashlib.md5(faction_id.encode("utf-8")).hexdigest()[:8], 16)
    pool = FACTION_ATTRIBUTE_WEIGHT_POOLS.get(faction_id, ANOMALOUS_ATTRIBUTES)
    attr = pool[(local_idx + (h % len(pool))) % len(pool)]

    _, def_arch, def_med = derive_default_3axis(agent_class, role, seed=seed_str)
    if local_idx < len(COMBAT_ARCHETYPES):
        arch = COMBAT_ARCHETYPES[(local_idx + (f_hash % len(COMBAT_ARCHETYPES))) % len(COMBAT_ARCHETYPES)]
    else:
        arch = def_arch if def_arch in COMBAT_ARCHETYPES else COMBAT_ARCHETYPES[h % len(COMBAT_ARCHETYPES)]

    med = def_med if def_med in ABILITY_MEDIUMS else ABILITY_MEDIUMS[(h // 7) % len(ABILITY_MEDIUMS)]
    return attr, arch, med


def _upgrade_legacy_agent_roster_3axis(
    roster: List[Dict[str, Any]],
    session_id: int = 0,
) -> Tuple[List[Dict[str, Any]], bool]:
    from mechanics.combat.spells.awakened_kits import (
        ABILITY_MEDIUMS,
        ANOMALOUS_ATTRIBUTES,
        COMBAT_ARCHETYPES,
        build_awakened_kit_ids,
    )

    modified = False
    faction_counters: Dict[str, int] = {}
    for ag in roster:
        if not isinstance(ag, dict):
            continue
        fid = str(ag.get("faction_id") or "public_agency").strip()
        local_idx = faction_counters.get(fid, 0)
        faction_counters[fid] = local_idx + 1

        cur_attr = ag.get("attribute")
        cur_arch = ag.get("combat_archetype")
        cur_med = ag.get("ability_medium")
        cur_abs = ag.get("innate_abilities") or []
        valid_abs = len(cur_abs) == 5 and all(isinstance(x, str) and x.startswith("awk_") for x in cur_abs)
        if (
            cur_attr in ANOMALOUS_ATTRIBUTES
            and cur_arch in COMBAT_ARCHETYPES
            and cur_med in ABILITY_MEDIUMS
            and valid_abs
        ):
            continue

        npc_id = str(ag.get("npc_id") or ag.get("name") or f"agent_{local_idx}")
        agent_class = str(ag.get("agent_class") or "Operative")
        role = str(ag.get("role") or "")
        attr, arch, med = _resolve_agent_3axis_for_faction(
            fid,
            local_idx,
            agent_class,
            role,
            seed_str=f"{session_id}:{npc_id}:{agent_class}",
        )
        ag["attribute"] = attr
        ag["combat_archetype"] = arch
        ag["ability_medium"] = med
        ag["innate_abilities"] = build_awakened_kit_ids(attr, arch, med)
        modified = True
    return roster, modified


def generate_anomalous_special_agents_roster(
    session_id: int,
    scen_key: str = "anomalous_incursions",
    factions: Optional[List[Dict[str, Any]]] = None,
    player_gender: str = "",
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
    from scenario_data import should_skew_female_npcs

    if not player_gender and session_id:
        try:
            player_gender = db.get_session_player_gender(session_id)
        except Exception:
            player_gender = ""
    skew_female = should_skew_female_npcs(scen_key, player_gender)

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
            if skew_female:
                gender = "female" if (global_idx % 3 != 2) else "male"
            else:
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
            from mechanics.combat.spells.awakened_kits import build_awakened_kit_ids
            ag_attr, ag_arch, ag_med = _resolve_agent_3axis_for_faction(
                faction_id,
                local_idx,
                agent_class,
                bp.get("role", ""),
                seed_str=f"{session_id}:{npc_id}:{agent_class}",
            )
            innate_abilities = build_awakened_kit_ids(ag_attr, ag_arch, ag_med)

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
                "private_agency_1": f"Tailored Obsidian ballisticweave coat bearing serialized {faction_name} clearance insignia",
                "private_agency_2": f"Weatherproof waxed-canvas tactical coat over a fitted Kevlar vest with engraved {faction_name} partner credentials",
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
                "attribute": ag_attr,
                "combat_archetype": ag_arch,
                "ability_medium": ag_med,
                "innate_abilities": innate_abilities,
                "appearance": appearance,
                "age_group": "adult",
                "standing": f"Tier {agent_tier} ({rank_title})",
                "social_role_type": "special_agent",
                "is_special_agent": True,
                "is_student_agent": False,
                "anomalous_npc_tag": "special_agent",
                "is_hydrated": 0,
            })
            try:
                from mechanics.world.locations.residences import resolve_agent_residence_blueprint
                _bp = resolve_agent_residence_blueprint(session_id, roster[-1], scen_key=scen_key)
                roster[-1]["residence_node_id"] = _bp["bedroom_node_id"]
                roster[-1]["residence_facility_id"] = _bp["facility_node_id"]
                roster[-1]["residence_location"] = _bp["residence_display"]
            except Exception:
                pass
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


def generate_student_special_agents_roster(
    session_id: int,
    scen_key: str = "anomalous_high_school",
    factions: Optional[List[Dict[str, Any]]] = None,
    player_gender: str = "",
    used_names: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Deterministically generates the 16 Dedicated Student Special Agents for
    `anomalous_high_school` and its variants:
    - 4 per grade (`Freshman`, `Sophomore`, `Junior`, `Senior`)
    - 8 Independent Club Freelancers (`faction_id="freelancer"`, 1 per school club)
    - 8 Junior Agency-Affiliated Student Operatives (`2 per major agency`)
    """
    from mechanics.social.factions import ANOMALOUS_PROMOTION_TIERS, infer_anomalous_faction_archetype
    from mechanics.combat.spells.awakened_kits import build_awakened_kit_ids
    from mechanics.social.races import normalize_race
    from mechanics.social.persona import normalize_appearance
    from scenario_data import should_skew_female_npcs

    if not player_gender and session_id:
        try:
            player_gender = db.get_session_player_gender(session_id)
        except Exception:
            player_gender = ""
    skew_female = should_skew_female_npcs(scen_key, player_gender)

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

    try:
        from mechanics.world.locations import get_session_school_name, format_node_hierarchy, resolve_session_location_tokens
        school_name = get_session_school_name(session_id, scen_key) or "Westlake High School"
    except Exception:
        school_name = "Westlake High School"
        format_node_hierarchy = None
        resolve_session_location_tokens = None

    seed_base = int(session_id or 101) * 131 + 709
    seen_names: set[str] = set(used_names) if used_names else set()
    student_agents: List[Dict[str, Any]] = []

    grade_room_names = {
        "Freshman": f"{school_name} ➔ Main Academic Building & Classrooms ➔ Freshman Classroom 1-A",
        "Sophomore": f"{school_name} ➔ Main Academic Building & Classrooms ➔ Sophomore Classroom 2-A",
        "Junior": f"{school_name} ➔ Main Academic Building & Classrooms ➔ Junior Classroom 3-B",
        "Senior": f"{school_name} ➔ Main Academic Building & Classrooms ➔ Senior Classroom 4-A",
    }

    for idx, bp in enumerate(STUDENT_SPECIAL_AGENT_BLUEPRINTS):
        if skew_female:
            gender = "female" if (idx % 3 != 2) else "male"
        else:
            gender = "female" if (idx % 2 == 0) else "male"

        faction_id = str(bp.get("faction_id") or "freelancer").strip()
        grade = str(bp.get("grade") or "Sophomore").strip()
        agent_tier = int(bp.get("agent_tier", 1))
        tier_meta = next((t for t in ANOMALOUS_PROMOTION_TIERS if t["tier"] == agent_tier), ANOMALOUS_PROMOTION_TIERS[0])
        rank_title = tier_meta["title"]

        if faction_id == "freelancer":
            faction_name = "Independent Student Operative"
        else:
            fac_info = fac_map.get(faction_id, {})
            faction_name = str(fac_info.get("name") or faction_id.replace("_", " ").title())

        culture_weights = MONASTIC_ORDER_CULTURE_WEIGHTS if faction_id == "monastic_order" else None
        full_name = ""
        for attempt in range(35):
            item_seed = seed_base + idx * 67 + attempt * 113
            cand = namegen.generate_person_name(
                scen_key,
                gender=gender,
                culture_weights=culture_weights,
                seed=item_seed,
            )
            if cand and cand.lower() not in seen_names:
                full_name = cand
                seen_names.add(cand.lower())
                if used_names is not None:
                    used_names.add(cand.lower())
                break
        if not full_name:
            full_name = f"Student Operative {idx + 1}"
            seen_names.add(full_name.lower())
            if used_names is not None:
                used_names.add(full_name.lower())

        npc_id = full_name.lower().replace(" ", "_").replace(".", "")
        char_race = normalize_race("", scen_key, seed=f"{session_id}:student_agent:{npc_id}")

        drive = AGENT_DRIVES[(seed_base + idx * 7) % len(AGENT_DRIVES)]
        friction = AGENT_FRICTIONS[(seed_base + idx * 11 + 3) % len(AGENT_FRICTIONS)]
        quirk = AGENT_QUIRKS[(seed_base + idx * 13 + 5) % len(AGENT_QUIRKS)]

        agent_class = str(bp.get("agent_class") or "Honor Roll Student")
        ag_attr, ag_arch, ag_med = _resolve_agent_3axis_for_faction(
            faction_id,
            idx,
            agent_class,
            bp.get("role", ""),
            seed_str=f"{session_id}:student_agent:{npc_id}:{agent_class}",
        )
        innate_abilities = build_awakened_kit_ids(ag_attr, ag_arch, ag_med)

        prim_nid = str(bp.get("primary_node_id") or "loc_sophomore_class").strip()
        sec_nid = str(bp.get("secondary_node_id") or "loc_courtyard").strip()
        primary_facility = grade_room_names.get(grade, f"{school_name} ➔ Main Academic Building & Classrooms ➔ Sophomore Classroom 2-A")
        secondary_facility = str(bp.get("city_hangout") or "").replace("{session_school}", school_name)
        try:
            if resolve_session_location_tokens:
                secondary_facility = resolve_session_location_tokens(session_id or 0, secondary_facility, scen_key)
            if session_id and format_node_hierarchy:
                if prim_nid:
                    fmt_p = format_node_hierarchy(session_id, prim_nid)
                    if fmt_p and not fmt_p.startswith(("loc_", "zone_", "sub_")):
                        primary_facility = fmt_p
                if sec_nid:
                    fmt_s = format_node_hierarchy(session_id, sec_nid)
                    if fmt_s and not fmt_s.startswith(("loc_", "zone_", "sub_")):
                        secondary_facility = fmt_s
        except Exception:
            pass

        club_name = str(bp.get("club") or "Student Council").strip()
        personality_summary = (
            f"{bp['summary']} ({grade} at {school_name} | {club_name} | {faction_name} — {rank_title}, Tier {agent_tier}). "
            f"Drive: {drive} Flaw: {friction} Mannerism: {quirk}"
        )

        appearance = normalize_appearance(
            {"outfit_style": f"Tailored {school_name} student blazer uniform with concealed tactical holster harness"},
            gender=gender,
            race=char_race,
            scen_key=scen_key,
            desc=bp["summary"],
        )

        student_agents.append({
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
            "division": club_name,
            "grade": grade,
            "student_grade": grade,
            "standing": grade,
            "age_group": "teen",
            "social_role_type": "student_peer",
            "club": club_name,
            "clique": bp.get("clique", "Academics"),
            "primary_facility": primary_facility,
            "secondary_facility": secondary_facility,
            "primary_node_id": prim_nid,
            "secondary_node_id": sec_nid,
            "sibling_name": "",
            "personality_summary": personality_summary,
            "mannerisms": quirk,
            "speech_style": "Youthful student cadence sharpened by field-operative situational awareness.",
            "attribute": ag_attr,
            "combat_archetype": ag_arch,
            "ability_medium": ag_med,
            "innate_abilities": innate_abilities,
            "appearance": appearance,
            "is_special_agent": True,
            "is_student_agent": True,
            "is_student_operative": True,
            "anomalous_npc_tag": "special_agent",
            "is_hydrated": 0,
        })
        try:
            from mechanics.world.locations.residences import resolve_agent_residence_blueprint
            _sbp = resolve_agent_residence_blueprint(session_id, student_agents[-1], scen_key=scen_key)
            student_agents[-1]["residence_node_id"] = _sbp["bedroom_node_id"]
            student_agents[-1]["residence_facility_id"] = _sbp["facility_node_id"]
            student_agents[-1]["residence_location"] = _sbp["residence_display"]
        except Exception:
            pass

    return student_agents


def _build_merged_anomalous_high_school_directory(
    session_id: int,
    scen_key: str,
    agent_roster: List[Dict[str, Any]],
    player_gender: str = "",
) -> List[Dict[str, Any]]:
    """
    Merges the Civilian Campus & Town Directory (`generate_campus_directory`) with the 60 Special Agents
    (44 Adult Special Agents + 16 Student Special Agents) for `anomalous_high_school`.
    Ensures civilian records carry explicit `age_group` ("adult" vs "teen"), `standing`, and `anomalous_npc_tag="civilian"`.
    """
    from mechanics.social.school_roster import generate_campus_directory
    civilians = generate_campus_directory(session_id, scen_key=scen_key, player_gender=player_gender)
    agent_names_low = {str(a.get("name") or "").strip().lower() for a in agent_roster}
    agent_ids_low = {str(a.get("npc_id") or "").strip().lower() for a in agent_roster}

    merged: List[Dict[str, Any]] = []
    for idx, civ in enumerate(civilians):
        item = dict(civ)
        c_name = str(item.get("name") or "").strip()
        c_id = str(item.get("npc_id") or "").strip().lower()
        if c_name.lower() in agent_names_low or c_id in agent_ids_low:
            for attempt in range(25):
                alt_name = namegen.generate_person_name(
                    scen_key, gender=item.get("gender", "female"), seed=int(session_id or 1) * 173 + idx * 43 + attempt * 71
                )
                if item.get("grade") == "Faculty":
                    prefix = c_name.split()[0] if "." in c_name.split()[0] or c_name.split()[0] in ("Coach", "Nurse", "Dean", "Principal", "Chef", "Madame") else "Ms."
                    alt_name = f"{prefix} {alt_name}"
                alt_id = alt_name.lower().replace(" ", "_").replace(".", "")
                if alt_name.lower() not in agent_names_low and alt_id not in agent_ids_low:
                    item["name"] = alt_name
                    item["npc_id"] = alt_id
                    break
        grade_str = str(item.get("grade") or "Student").strip()
        is_adult_civ = grade_str in ("Faculty", "Citizen")
        item["age_group"] = "adult" if is_adult_civ else "teen"
        item["standing"] = grade_str
        item["is_special_agent"] = False
        item["is_student_agent"] = False
        item["anomalous_npc_tag"] = "civilian"
        merged.append(item)

    merged.extend(agent_roster)
    return merged


def ensure_anomalous_agent_roster(session_id: int | dict | str | None, scen_key: str = "", player_gender: str = "") -> List[Dict[str, Any]]:
    """
    Ensures the Special Agents roster is generated and synced into:
    1. `session['extra']['anomalous_agent_roster']` (44 agents in `anomalous_incursions`; 60 in `anomalous_high_school`)
    2. `school_directory` (44 agents in `anomalous_incursions`; 148+ merged Civilians + Special Agents in `anomalous_high_school`)
    3. `factions` table (`leadership_roster` and `members` for each of the 6 Fixed Factions)
    4. `lorebook` (`entity_type='person'`) for faction leaders and same-faction colleagues
    """
    if not session_id:
        return []

    if isinstance(session_id, dict):
        sess = session_id
        session_id_val = sess.get("id")
    else:
        try:
            session_id_val = int(session_id)
        except (ValueError, TypeError):
            return []
        sess = db.get_session(session_id_val) or {}

    if not session_id_val:
        return []

    session_id = session_id_val
    if not scen_key:
        scen_key = str(sess.get("scenario") or "anomalous_incursions")
    if not scenario_data.is_anomalous_incursions_scenario(scen_key):
        return []

    is_hybrid_hs = scenario_data.is_anomalous_high_school_scenario(scen_key)
    expected_agent_count = 60 if is_hybrid_hs else 44

    existing_roster = sess.get("anomalous_agent_roster") or (
        sess.get("extra", {}).get("anomalous_agent_roster") if isinstance(sess.get("extra"), dict) else None
    )
    if isinstance(existing_roster, list) and len(existing_roster) == expected_agent_count:
        existing_roster, was_upgraded = _upgrade_legacy_agent_roster_3axis(existing_roster, session_id=session_id)
        if not any("has_entity_contract" in ag for ag in existing_roster if isinstance(ag, dict)):
            try:
                from mechanics.pacts.resolver import assign_special_agent_contracts
                existing_roster = assign_special_agent_contracts(session_id, existing_roster, scen_key=scen_key)
                was_upgraded = True
            except Exception as _pact_seed_err:
                log.debug("Legacy agent roster pact upgrade skipped: %s", _pact_seed_err)
        if was_upgraded:
            db.update_session(session_id, extra={"anomalous_agent_roster": existing_roster})
        if is_hybrid_hs:
            try:
                cur_dir = db.get_school_roster(session_id) or []
                if len(cur_dir) < 140:
                    merged_dir = _build_merged_anomalous_high_school_directory(
                        session_id, scen_key, existing_roster, player_gender=player_gender
                    )
                    db.save_school_roster(session_id, merged_dir)
            except Exception:
                pass
        elif was_upgraded:
            try:
                db.save_school_roster(session_id, existing_roster)
            except Exception:
                pass
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
    roster = generate_anomalous_special_agents_roster(session_id, scen_key=scen_key, factions=factions, player_gender=player_gender)
    if is_hybrid_hs:
        used_names = {str(a.get("name") or "").strip().lower() for a in roster}
        student_agents = generate_student_special_agents_roster(
            session_id,
            scen_key=scen_key,
            factions=factions,
            player_gender=player_gender,
            used_names=used_names,
        )
        roster.extend(student_agents)

    try:
        from mechanics.pacts.resolver import assign_special_agent_contracts
        roster = assign_special_agent_contracts(session_id, roster, scen_key=scen_key)
    except Exception as _pact_err:
        log.debug("Special agent contract seeding skipped: %s", _pact_err)

    # 1. Persist in session extra
    db.update_session(session_id, extra={"anomalous_agent_roster": roster})

    # 2. Save in school_directory table for facility-based ambient presence & directory lookup
    try:
        if is_hybrid_hs:
            merged_dir = _build_merged_anomalous_high_school_directory(
                session_id, scen_key, roster, player_gender=player_gender
            )
            db.save_school_roster(session_id, merged_dir)
        else:
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
                "attribute": ag.get("attribute"),
                "combat_archetype": ag.get("combat_archetype"),
                "ability_medium": ag.get("ability_medium"),
                "has_entity_contract": bool(ag.get("has_entity_contract")),
                "pact_id": ag.get("pact_id", ""),
                "pact_name": ag.get("pact_name", ""),
                "pact_tier": int(ag.get("pact_tier") or 0),
                "pact_spell_id": ag.get("pact_spell_id", ""),
                "pact_tell": ag.get("pact_tell", ""),
                "innate_abilities": ability_names,
                "is_player": False,
                "is_vacant": False,
            })

        try:
            db.upsert_faction(
                session_id=session_id,
                name=f_name,
                leadership_roster=leadership_roster,
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
                        "SELECT 1 FROM phone_messages WHERE session_id=? AND (LOWER(contact_npc_id)=? OR LOWER(contact_npc_id)=?) LIMIT 1",
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
                    "attribute": ag.get("attribute"),
                    "combat_archetype": ag.get("combat_archetype"),
                    "ability_medium": ag.get("ability_medium"),
                    "faction": ag["faction_name"],
                    "faction_id": ag["faction_id"],
                    "division": ag["division"],
                    "primary_facility": ag["primary_facility"],
                    "secondary_facility": ag["secondary_facility"],
                    "primary_node_id": ag.get("primary_node_id", ""),
                    "secondary_node_id": ag.get("secondary_node_id", ""),
                    "is_special_agent": True,
                    "is_student_agent": bool(ag.get("is_student_agent")),
                    "age_group": ag.get("age_group", "adult"),
                    "residence_node_id": ag.get("residence_node_id", ""),
                    "residence_facility_id": ag.get("residence_facility_id", ""),
                    "residence_location": ag.get("residence_location", ""),
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
        TAG_FOLKLORE_VILLAGER,
        TAG_SPECIAL_AGENT,
        classify_anomalous_npc_tag,
        hydrate_anomalous_npc_profile,
    )
    npc_tag = classify_anomalous_npc_tag(matched_contact, session_id=sess_id, scen_key=scen_key)
    if (
        npc_tag == "anomaly_entity"
        or matched_contact.get("is_anomalous_entity")
        or str(matched_contact.get("npc_type") or "").lower() == "anomaly"
    ):
        return {
            "allowed": False,
            "cost": 0,
            "anomalous_npc_tag": "anomaly_entity",
            "is_anomaly_blocked": True,
            "reason": f"{npc_name} is an Anomalous Entity and cannot be recruited as a human party companion.",
        }
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

    if npc_tag == TAG_FOLKLORE_VILLAGER:
        if affinity_score >= 20 or basic_info.get("contact_added"):
            return {
                "allowed": True,
                "cost": 0,
                "anomalous_npc_tag": TAG_FOLKLORE_VILLAGER,
                "is_special_agent": False,
                "is_folklore_villager": True,
                "is_beast_companion": bool(hydrated.get("is_beast_companion")),
                "folklore_village": hydrated.get("folklore_village", ""),
                "agent_tier": hydrated["agent_tier"],
                "rank_title": hydrated["rank_title"],
                "agent_class": hydrated["agent_class"],
                "faction_id": hydrated["faction_id"],
                "faction_name": hydrated["faction_name"],
                "innate_abilities": hydrated["innate_abilities"],
                "spells": hydrated["innate_abilities"],
                "hp": hydrated["hp"],
                "max_hp": hydrated["max_hp"],
                "mp": hydrated["mp"],
                "max_mp": hydrated["max_mp"],
                "level": hydrated["level"],
                "stats": hydrated["stats"],
                "weapon_profile": hydrated["weapon_profile"],
                "reason": f"Befriended sanctuary ally {npc_name} agreed to accompany you beyond the veil (0G).",
            }
        return {
            "allowed": False,
            "cost": 0,
            "anomalous_npc_tag": TAG_FOLKLORE_VILLAGER,
            "reason": f"{npc_name} wishes to build deeper mutual trust before stepping beyond the sanctuary veil with you (Affinity {affinity_score}/20).",
        }

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

    # Schedule-Aware Companion Gate for Anomalous High School (Weekdays 08:00-15:00)
    if scenario_data.is_anomalous_high_school_scenario(scen_key):
        from mechanics.social.origin_mode import is_school_hours, is_student_operative
        from mechanics.world.world_schedule import is_campus_node_or_location
        curr_day = int(session.get("current_day") or 1)
        curr_min = int(session.get("current_minute") or 480)
        if sess_id and ("current_day" not in session or "current_minute" not in session):
            try:
                curr_day, curr_min, _ = db.get_session_time(sess_id)
            except Exception:
                pass
        if is_school_hours(curr_day, curr_min):
            loc_str = str(session.get("location") or "")
            node_id = str(session.get("current_node_id") or "")
            is_on_campus = is_campus_node_or_location(
                location_str=loc_str, node_id=node_id, session_id=sess_id, scen_key=scen_key
            )
            active_campus_rift = None
            try:
                from mechanics.world.anomalous_events import get_active_incursion_at_location
                active_campus_rift = get_active_incursion_at_location(sess_id, loc_str or "zone_school_campus")
            except Exception:
                active_campus_rift = None

            is_student_ag = bool(
                (special_agent or {}).get("is_student_agent")
                or basic_info.get("is_student_agent")
                or matched_contact.get("is_student_agent")
                or str((special_agent or {}).get("age_group") or basic_info.get("age_group") or matched_contact.get("age_group") or "").lower() == "teen"
                or str((special_agent or {}).get("grade") or basic_info.get("grade") or matched_contact.get("grade") or "") in ("Freshman", "Sophomore", "Junior", "Senior")
            )
            if not active_campus_rift:
                if is_student_ag and not is_on_campus:
                    return {
                        "allowed": False,
                        "cost": 0,
                        "anomalous_npc_tag": TAG_SPECIAL_AGENT,
                        "is_school_hours_blocked": True,
                        "reason": (
                            f"{npc_name} is attending classes on campus until 15:00. "
                            f"Student Operatives can only deploy off-campus after 15:00 dismissal or during an active Campus Anomaly breach."
                        ),
                    }
                if not is_student_ag and is_on_campus and is_student_operative(session):
                    return {
                        "allowed": False,
                        "cost": 0,
                        "anomalous_npc_tag": TAG_SPECIAL_AGENT,
                        "is_school_hours_blocked": True,
                        "reason": (
                            f"Adult Operative {npc_name} waits off-campus during weekday lecture hours (08:00–15:00) "
                            f"unless an active Campus Anomaly breach is underway."
                        ),
                    }

        # Same School Club Camaraderie: Student PC recruiting a Student Special Agent in the same joined club
        agent_club = str((special_agent or {}).get("club") or basic_info.get("club") or matched_contact.get("club") or "").strip()
        player_club = str(session.get("joined_faction") or "").strip()
        if not player_club and session.get("id"):
            try:
                from mechanics.social.factions import get_anomalous_faction_state
                fac_state = get_anomalous_faction_state(int(session["id"]), int(session.get("user_id", 0)))
                player_club = str(fac_state.get("joined_club_name") or "").strip()
            except Exception:
                player_club = ""
        if agent_club and player_club and agent_club.lower() == player_club.lower() and affinity_score >= 40:
            return {
                "allowed": True,
                "cost": 0,
                "reason": f"Clubmate & fellow Student Operative {npc_name} ({agent_club}) joined your squad for 0G.",
                **base_companion_payload,
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

    # Check if there is an active Daily Anomaly Breach here for field responder convergence
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

    # Field Breach Convergence: 45% chance a field operative responds to an active Daily Anomaly Breach site
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

