"""
Hikayat - Bounty Board & Quest Archetypes Mechanics
Modular mechanic handling quest archetype taxonomies, icon mappings, bounty prompt schemas, and dynamic bounty generation.
"""

import logging
import uuid
import db
import scenario_data
from llm_client import call_llm_json

log = logging.getLogger("hikayat.bounty")


def _resolve_session_location(session_id: int, session: dict = None, scen_key: str = "fantasy") -> str:
    loc = (session.get("current_location") if isinstance(session, dict) else "") or ""
    if not loc and session_id:
        try:
            from mechanics.world.locations.formatting import get_discovered_primary_locations
            d_locs = get_discovered_primary_locations(session_id, scen_key)
            if d_locs:
                first_z = list(d_locs.keys())[0]
                loc = f"{first_z} ➔ {d_locs[first_z][0]}" if d_locs[first_z] else first_z
            if not loc:
                from mechanics.world.locations.seeding import get_default_tiered_location
                dz, dp, _ = get_default_tiered_location(scen_key, session_id=session_id)
                loc = f"{dz} ➔ {dp}"
        except Exception:
            pass
    return loc or ("Ashford Academy" if "school" in scen_key.lower() else "the Frontier")


# --------------------------------------------------------------------- Taxonomy of Quest Archetypes
ARCHETYPES_BY_SCENARIO = {
    "general": [
        "Infiltration", "Heist", "Sabotage", "Disruption", "Espionage", "Blackmail",
        "Rescue", "Escort", "Find Person", "Siege Defense", "Survival", "Resource Run",
        "Alchemy", "Crafting", "Gathering", "Arbitration", "Tribunal", "Arcane Ritual",
        "Sealing", "Cleansing", "Exorcism", "Assassination", "Honor Duel", "Monster Hunting",
        "Extermination", "Bounty Hunting"
    ],
    "modern": [
        "Gossip Control", "Election Campaigning", "Matchmaking", "Secret Admirer",
        "Club Showdown", "Campus Infiltration", "Exam Heist", "Academic Rescue",
        "Off-Campus Errand", "Urban Legend Dare", "Arcade Rivalry"
    ],
    "fantasy": [
        "Beast Taming", "Familiar Binding", "Rune Archaeology", "Dungeon Mapping",
        "Relic Discovery", "Rift Cleansing", "Holy Exorcism", "Honor Duel"
    ],
    "cyberpunk": [
        "Netrunning", "Data Extraction", "Tech Extraction", "Cyberware Heist",
        "Rogue AI Containment", "Derelict Salvage", "Void Recovery", "Override"
    ],
    "apocalypse": [
        "Signal Recovery", "Radio Tower Repair", "Toxic Zone Scavenge",
        "Radiation Run", "Convoy Pursuit", "Highway Interception"
    ],
    "nsfw": [
        "Seduction", "Allure", "Domination", "Subjugation", "Underground Brothel",
        "Courtesan Guild", "Aphrodisiac Run", "Lust Alchemy", "Paramour Courtship",
        "Harem Bond", "Bondage Escape", "Captive Rescue", "Masquerade Revelry", "Hedonist Intrigue"
    ],
    "anomalous_incursions": [
        "Eliminate Hostile Anomalous Entity",
        "Secure Non-Hostile Anomalous Entity",
        "Contain Anomalous Phenomenon",
        "Investigate Anomalous Phenomenon",
        "Find Missing Person (Spirited Away)",
        "Retrieve Altered Item / Cursed Relic",
        "Disrupt Cult Ritual / Clandestine Auction",
        "Spatial Distortion Mapping",
        "Cognitohazard & Urban Legend Suppression",
        "Quarantine Perimeter Defense",
        "Rogue Operative / Rival Hunter Interception",
        "High-Sensitivity Esper / Witness Escort",
    ],
}

# 12 Canonical Scenario Bounty Archetypes (mapping both snake_case keys and display labels)
ANOMALOUS_BOUNTY_ARCHETYPES: list[dict] = [
    {
        "key": "rogue_entity_termination",
        "label": "Eliminate Hostile Anomalous Entity",
        "icon": "👹",
        "blueprint_id": "NEUTRALIZATION",
        "title_prefix": "Termination Order",
        "default_objective": "Track down and eliminate the hostile anomalous entity threatening civilian infrastructure.",
        "req_item": "",
    },
    {
        "key": "non_hostile_entity_pacification",
        "label": "Secure Non-Hostile Anomalous Entity",
        "icon": "🛡️",
        "blueprint_id": "ESCORT_RESCUE",
        "title_prefix": "Live Containment",
        "default_objective": "Locate, pacify, and safely seal the non-hostile anomalous entity into a containment unit without lethal force.",
        "req_item": "",
    },
    {
        "key": "spatial_rift_sealing",
        "label": "Contain Anomalous Phenomenon",
        "icon": "🔮",
        "blueprint_id": "SITE_DEFENSE_RITUAL",
        "title_prefix": "Rift Stabilization",
        "default_objective": "Deploy resonance anchors and channel stabilization seals to collapse the active spatial phenomenon.",
        "req_item": "",
    },
    {
        "key": "temporal_loop_anchor",
        "label": "Investigate Anomalous Phenomenon",
        "icon": "🔍",
        "blueprint_id": "INVESTIGATION",
        "title_prefix": "Field Recon",
        "default_objective": "Investigate the localized temporal/sensory anomaly, collect resonance readings, and identify its origin.",
        "req_item": "",
    },
    {
        "key": "missing_agent_rescue",
        "label": "Find Missing Person (Spirited Away)",
        "icon": "🕵️",
        "blueprint_id": "ESCORT_RESCUE",
        "title_prefix": "Extraction Alert",
        "default_objective": "Breach the pocket threshold to locate and extract the missing person spirited away by an anomaly.",
        "req_item": "",
    },
    {
        "key": "cursed_relic_retrieval",
        "label": "Retrieve Altered Item / Cursed Relic",
        "icon": "💎",
        "blueprint_id": "ACQUISITION",
        "title_prefix": "Relic Recovery",
        "default_objective": "Secure the volatile Altered Item / Cursed Relic in a lead-lined case and deliver it to the vault.",
        "req_item": "Sealed Altered Relic",
    },
    {
        "key": "cult_ritual_disruption",
        "label": "Disrupt Cult Ritual / Clandestine Auction",
        "icon": "💥",
        "blueprint_id": "HEIST_INFILTRATION",
        "title_prefix": "Covert Raid",
        "default_objective": "Infiltrate the clandestine gathering, sabotage the occult ritual catalyst or black-market auction, and exfiltrate.",
        "req_item": "",
    },
    {
        "key": "sensory_anomaly_purge",
        "label": "Spatial Distortion Mapping",
        "icon": "🧭",
        "blueprint_id": "EXPLORATION_HAZARD",
        "title_prefix": "Cartography Sweep",
        "default_objective": "Navigate the non-Euclidean corridor hazards, deploy telemetry beacons, and map the shifting zone geometry.",
        "req_item": "",
    },
    {
        "key": "urban_legend_debunking",
        "label": "Cognitohazard & Urban Legend Suppression",
        "icon": "📻",
        "blueprint_id": "SOCIAL_MANIPULATION",
        "title_prefix": "Memetic Suppression",
        "default_objective": "Contain the spreading cognitohazard rumor, administer Class-A amnestics or counter-memes to witnesses, and scrub feeds.",
        "req_item": "",
    },
    {
        "key": "cognitohazard_quarantine",
        "label": "Quarantine Perimeter Defense",
        "icon": "🏰",
        "blueprint_id": "SITE_DEFENSE_RITUAL",
        "title_prefix": "Cordon Defense",
        "default_objective": "Fortify the municipal quarantine barricade and repel waves of manifesting entities until containment holds.",
        "req_item": "",
    },
    {
        "key": "syndicate_black_market_interception",
        "label": "Rogue Operative / Rival Hunter Interception",
        "icon": "⚔️",
        "blueprint_id": "CONTEST_RIVALRY",
        "title_prefix": "Hunter Interception",
        "default_objective": "Intercept the rogue operative or rival bounty hunter before they abscond with the anomalous target.",
        "req_item": "",
    },
    {
        "key": "anomalous_autopsy_escort",
        "label": "High-Sensitivity Esper / Witness Escort",
        "icon": "🛡️",
        "blueprint_id": "ESCORT_RESCUE",
        "title_prefix": "VIP Esper Escort",
        "default_objective": "Protect and escort the high-sensitivity Esper / forensic witness safely through hazardous sectors.",
        "req_item": "",
    },
]

# Faction Board Flavor Bias for Anomalous Incursions
ANOMALOUS_FACTION_BOARD_ARCHETYPE_WEIGHTS: dict[str, list[str]] = {
    "public_agency": [
        "Quarantine Perimeter Defense",
        "Contain Anomalous Phenomenon",
        "Retrieve Altered Item / Cursed Relic",
        "Investigate Anomalous Phenomenon",
        "Eliminate Hostile Anomalous Entity",
        "Cognitohazard & Urban Legend Suppression",
    ],
    "private_agency_1": [
        "Eliminate Hostile Anomalous Entity",
        "Secure Non-Hostile Anomalous Entity",
        "Rogue Operative / Rival Hunter Interception",
        "Disrupt Cult Ritual / Clandestine Auction",
        "High-Sensitivity Esper / Witness Escort",
        "Retrieve Altered Item / Cursed Relic",
    ],
    "private_agency_2": [
        "Rogue Operative / Rival Hunter Interception",
        "Eliminate Hostile Anomalous Entity",
        "Disrupt Cult Ritual / Clandestine Auction",
        "Secure Non-Hostile Anomalous Entity",
        "High-Sensitivity Esper / Witness Escort",
        "Spatial Distortion Mapping",
    ],
    "monastic_order": [
        "Contain Anomalous Phenomenon",
        "Retrieve Altered Item / Cursed Relic",
        "Find Missing Person (Spirited Away)",
        "Eliminate Hostile Anomalous Entity",
        "Disrupt Cult Ritual / Clandestine Auction",
        "Secure Non-Hostile Anomalous Entity",
    ],
    "freelance_app": [
        "Find Missing Person (Spirited Away)",
        "Investigate Anomalous Phenomenon",
        "Cognitohazard & Urban Legend Suppression",
        "Spatial Distortion Mapping",
        "Secure Non-Hostile Anomalous Entity",
        "High-Sensitivity Esper / Witness Escort",
    ],
}

# --------------------------------------------------------------------- Discord Quest Log Icon Mappings
QUEST_TYPE_ICONS = {
    # Anomalous Incursions Archetypes
    "eliminate hostile anomalous entity": "👹",
    "rogue_entity_termination": "👹",
    "secure non-hostile anomalous entity": "🛡️",
    "non_hostile_entity_pacification": "🛡️",
    "contain anomalous phenomenon": "🔮",
    "spatial_rift_sealing": "🔮",
    "investigate anomalous phenomenon": "🔍",
    "temporal_loop_anchor": "🔍",
    "find missing person (spirited away)": "🕵️",
    "spirited away": "🕵️",
    "missing_agent_rescue": "🕵️",
    "retrieve altered item / cursed relic": "💎",
    "retrieve altered item": "💎",
    "cursed_relic_retrieval": "💎",
    "disrupt cult ritual / clandestine auction": "💥",
    "cult_ritual_disruption": "💥",
    "spatial distortion mapping": "🧭",
    "sensory_anomaly_purge": "🧭",
    "cognitohazard & urban legend suppression": "📻",
    "urban_legend_debunking": "📻",
    "quarantine perimeter defense": "🏰",
    "cognitohazard_quarantine": "🏰",
    "rogue operative / rival hunter interception": "⚔️",
    "syndicate_black_market_interception": "⚔️",
    "high-sensitivity esper / witness escort": "🛡️",
    "anomalous_autopsy_escort": "🛡️",
    # General Archetypes
    "monster hunting": "👹",
    "extermination": "👹",
    "bounty hunting": "🎯",
    "gathering": "💎",
    "relic": "💎",
    "resource run": "🧪",
    "alchemy": "🧪",
    "crafting": "🧪",
    "rescue": "🛡️",
    "escort": "🛡️",
    "find person": "🛡️",
    "investigation": "🔍",
    "mystery": "🔍",
    "espionage": "📜",
    "blackmail": "📜",
    "infiltration": "🕵️",
    "heist": "🕵️",
    "theft": "🕵️",
    "diplomacy": "🤝",
    "faction": "🤝",
    "tribunal": "⚖️",
    "arbitration": "⚖️",
    "survival": "🏰",
    "defense": "🏰",
    "siege": "🏰",
    "ritual": "🔮",
    "sealing": "🔮",
    "cleansing": "🔮",
    "exorcism": "🛡️",
    "override": "⚡",
    "sabotage": "💥",
    "disruption": "💥",
    "assassination": "🗡️",
    "duel": "🗡️",
    
    # Modern / High School Drama Archetypes
    "gossip": "💬",
    "rumor": "💬",
    "campaigning": "🗳️",
    "election": "🗳️",
    "matchmaking": "💌",
    "secret admirer": "💌",
    "romance": "💌",
    "club": "🏆",
    "showdown": "🏆",
    "curfew": "🌙",
    "campus infiltration": "🌙",
    "exam": "📚",
    "academic": "📚",
    "off-campus": "🏙️",
    "errand": "📦",
    "urban legend": "👻",
    "dare": "⚡",
    "arcade": "🕹️",
    
    # Fantasy Archetypes
    "beast taming": "🐉",
    "familiar": "🐉",
    "archaeology": "🏛️",
    "dungeon": "🏛️",
    
    # Cyberpunk / Sci-Fi Archetypes
    "netrunning": "💻",
    "cyberware": "🔧",
    "tech extraction": "🔧",
    "rogue ai": "🤖",
    "derelict": "🛸",
    "salvage": "🛸",
    
    # Post-Apocalyptic Archetypes
    "signal": "📻",
    "radio": "📻",
    "toxic": "☣️",
    "radiation": "☣️",
    "convoy": "🏎️",
    
    # NSFW & Adult Archetypes
    "seduction": "💋",
    "allure": "💋",
    "domination": "⛓️",
    "subjugation": "⛓️",
    "brothel": "🈲",
    "courtesan": "🈲",
    "aphrodisiac": "🧪",
    "lust": "🧪",
    "courtship": "💘",
    "paramour": "💘",
    "harem": "💘",
    "bondage": "⛓️‍💥",
    "revelry": "🎭",
    "masquerade": "🎭",
}


def get_quest_type_icon(quest_type: str) -> str:
    """Returns the thematic Discord emoji for a given quest archetype."""
    q_lower = (quest_type or "").lower()
    # Sort keys by length descending to match specific archetypes before generic sub-tokens (e.g. 'academic rescue' / 'academic' before 'rescue')
    for key in sorted(QUEST_TYPE_ICONS.keys(), key=len, reverse=True):
        if key in q_lower:
            return QUEST_TYPE_ICONS[key]
    return "📜"


def get_archetypes_for_scenario(scenario: str = None) -> list[str]:
    """Returns ONLY the relevant archetypes for the active session scenario, prioritized."""
    from scenario_data import has_tag, is_anomalous_incursions_scenario
    from mechanics.world.locations.seeds import is_school_scenario
    archetypes = []

    # 1. Primary Scenario Archetypes (highest priority)
    if is_anomalous_incursions_scenario(scenario):
        archetypes.extend(ARCHETYPES_BY_SCENARIO.get("anomalous_incursions", []))
    if is_school_scenario(scenario):
        archetypes.extend(ARCHETYPES_BY_SCENARIO.get("modern", []))
    if has_tag(scenario, "fantasy") or has_tag(scenario, "isekai") or has_tag(scenario, "isekai_fantasy") or has_tag(scenario, "grimdark") or has_tag(scenario, "dark_fantasy"):
        archetypes.extend(ARCHETYPES_BY_SCENARIO.get("fantasy", []))
    if has_tag(scenario, "cyberpunk") or has_tag(scenario, "space") or has_tag(scenario, "sci_fi") or has_tag(scenario, "steampunk"):
        archetypes.extend(ARCHETYPES_BY_SCENARIO.get("cyberpunk", []))
    if has_tag(scenario, "post_apocalypse"):
        archetypes.extend(ARCHETYPES_BY_SCENARIO.get("apocalypse", []))

    # 2. NSFW Archetypes if applicable
    if has_tag(scenario, "nsfw"):
        archetypes.extend(ARCHETYPES_BY_SCENARIO.get("nsfw", []))

    # 3. Compatible General Archetypes
    general_pool = ARCHETYPES_BY_SCENARIO.get("general", [])
    is_modern_school = is_school_scenario(scenario) or has_tag(scenario, "non_combat")
    if is_modern_school:
        excluded = {
            "Arcane Ritual", "Sealing", "Cleansing", "Exorcism", "Assassination",
            "Monster Hunting", "Extermination", "Siege Defense", "Alchemy", "Honor Duel",
            "Bounty Hunting"
        }
        compatible = [a for a in general_pool if a not in excluded]
        archetypes.extend(compatible)
    else:
        archetypes.extend(general_pool)

    # Deduplicate while strictly preserving priority order
    seen = set()
    result = []
    for a in archetypes:
        if a not in seen:
            seen.add(a)
            result.append(a)
    return result


def get_scenario_archetype_prompt_note(scenario: str = None) -> str:
    """Generates a clean system prompt instruction listing scenario-appropriate archetypes."""
    archetypes = get_archetypes_for_scenario(scenario)
    return f"Suggested scenario archetypes to use: {', '.join(archetypes)}."


# --------------------------------------------------------------------- Bounty Board Prompt & Schemas
BOUNTY_BOARD_SCHEMA = """{
  "bounties": [
    {
      "quest_type": "string, creative scenario-appropriate archetype",
      "title": "string, evocative max 50 chars title",
      "objective": "string, rich 1-2 sentence objective describing the goal and stakes",
      "client_npc": "string, full name of the quest-giver/client NPC",
      "client_location": "string, starting location of the client (Zone -> Primary Place)",
      "required_item": "string, specific target item or supplies to gather/deliver if applicable, or empty string",
      "reward_xp": integer 100-300,
      "reward_gold": integer 20-150,
      "reward_item": "string, thematic item/equipment/weapon name or empty string",
      "waypoints": [
        {
          "stage_index": 1,
          "stage_label": "string, specific 1-sentence task for this stage",
          "target_location": "string, Zone -> Primary Place format (use existing world locations if possible)",
          "target_npc": "string, NPC name to meet/contact, or empty string",
          "completion_trigger": "arrival OR skill_check",
          "resource_target": 0
        }
      ]
    }
  ]
}"""


def build_bounty_system_prompt(scenario: str = None) -> str:
    """Dynamically constructs a focused system prompt containing ONLY scenario-appropriate archetypes."""
    archetypes = get_archetypes_for_scenario(scenario)
    archetypes_str = ", ".join(archetypes)
    return (
        f"Generate 3 distinct bounty board postings tailored specifically to the given scenario and location.\n"
        f"Selected scenario archetypes to choose from: {archetypes_str}.\n"
        f"Keep objectives clear, engaging, and highly thematic.\n"
        f"CRITICAL DIVERSITY REQUIREMENT: Each bounty MUST have a DIFFERENT, UNIQUE quest_type chosen from the archetypes above. Do NOT repeat the same quest_type or archetype across the 3 postings!\n"
        f"CLIENT BINDING: Every bounty MUST specify a named `client_npc` (the quest-giver requesting the job) and their `client_location`.\n"
        f"REQUIRED ITEMS: For gathering, crafting, delivery, errand, or scavenging jobs, specify the exact item name in `required_item`.\n"
        f"Include reward_xp (100-300), reward_gold (20-150), and optional reward_item (equipment/weapons/consumables).\n"
        f"IMPORTANT: Each bounty MUST include a `waypoints` array (2-3 progressive stages) that tell the player WHERE to travel.\n"
        f"  - MULTI-LOCATION PROGRESSION: Bounties (except stationary siege/defense/ritual) MUST span 2 or 3 distinct locations across their stages!\n"
        f"  - Stage 1: Meet the quest-giver/client at Location A to receive details/item (`completion_trigger: 'arrival'`, specify `target_npc`).\n"
        f"  - Stage 2: Travel to target destination (Location B) to harvest/investigate/confront (`completion_trigger: 'skill_check'`).\n"
        f"  - Stage 3: Return to the client at Location A to turn in the item/report (`completion_trigger: 'skill_check'`).\n"
        f"  - target_location MUST use 'Zone -> Primary Place' format matching the session's world.\n"
        f"Respond with ONLY a single valid JSON object matching the schema exactly, no prose or code fences."
    )


def resolve_or_seed_bounty_client(
    session_id: int,
    session: dict = None,
    raw_bounty: dict = None,
    default_loc: str = "",
    index: int = 0
) -> tuple[str, str]:
    """Deterministically identifies or seeds a named client NPC and starting location for a bounty."""
    if raw_bounty is None:
        raw_bounty = {}
    if isinstance(session, str):
        scen_key = session
        try:
            import db
            session = db.get_session(session_id) or {}
        except Exception:
            session = {}
    elif session is None and session_id:
        try:
            import db
            session = db.get_session(session_id) or {}
        except Exception:
            session = {}
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"
    else:
        scen_key = session.get("scenario", "fantasy") if session else "fantasy"

    client_npc = str(raw_bounty.get("client_npc", "") or "").strip()
    if not client_npc:
        for wp in (raw_bounty.get("waypoints") or []):
            if isinstance(wp, dict) and wp.get("target_npc"):
                client_npc = str(wp["target_npc"]).strip()
                break

    if not default_loc:
        default_loc = _resolve_session_location(session_id, session, scen_key)
    client_loc = str(raw_bounty.get("client_location", "") or default_loc or "").strip()

    if client_npc:
        return client_npc, client_loc

    from mechanics.world.locations.seeds import is_school_scenario
    if is_school_scenario(scen_key) and session:
        try:
            from mechanics.social.school_roster import ensure_school_directory_exists
            from mechanics.world.schedules import is_campus_node_or_location
            roster = ensure_school_directory_exists(session)
            if roster:
                probe_loc = f"{client_loc} {raw_bounty.get('title', '')} {raw_bounty.get('description', '')}".lower()
                is_town_errand = (
                    any(k in probe_loc for k in (
                        "commercial", "convenience", "konbini", "cafe", "café", "arcade", "karaoke",
                        "commuter station", "transit", "koban", "kōban", "park", "seaside", "beach",
                        "pier", "lighthouse", "mountain", "delivery", "bus", "part-time", "shift"
                    ))
                    and not is_campus_node_or_location(location_str=client_loc, session_id=session_id, scen_key=scen_key)
                )
                if is_town_errand:
                    pool = [r for r in roster if r.get("grade") in ("Citizen", "Youth Peer")] or roster
                else:
                    pool = [r for r in roster if r.get("grade") not in ("Citizen", "Youth Peer")] or roster
                chosen = pool[(session_id + index) % len(pool)]
                return chosen.get("name", "Fellow Student"), chosen.get("primary_facility", default_loc)
        except Exception:
            pass

    if session_id:
        try:
            contacts = db.get_contacts(session_id)
            if contacts:
                cand = contacts[(session_id + index) % len(contacts)]
                name = cand.get("name") or cand.get("npc_name")
                if name:
                    return str(name), default_loc
        except Exception:
            pass

    try:
        import namegen
        gen_name = namegen.generate_person_name(scen_key)
        if gen_name:
            return gen_name, default_loc
    except Exception:
        pass

    return f"Client #{index + 1}", default_loc


def get_bounty_board_title_name(scen_key: str = None) -> tuple[str, str]:
    """Returns (title_name, emoji) for the Bounty Board Embed based on scenario."""
    from mechanics.world.locations import is_school_scenario
    if scenario_data.is_anomalous_incursions_scenario(scen_key):
        return ("Anomalous Containment & Freelance Dispatch", "📡")
    scen = str(scen_key or "").lower()
    if is_school_scenario(scen):
        return ("Campus Requests & Commissions", "📋")
    if "cyberpunk" in scen:
        return ("Fixer Job Terminal", "💾")
    if "sci_fi" in scen or "space" in scen:
        return ("Mercenary Comm Terminal", "📡")
    if "steampunk" in scen:
        return ("Dispatch Board & Gigs", "📻")
    if "apocalypse" in scen:
        return ("Wasteland Radio Dispatch", "📻")
    return ("Guild Bounty Board", "📋")


_ANOMALOUS_CONSOLIDATED_COMPLEX_IDS = {
    "loc_general_hospital",
    "loc_theme_park",
    "loc_eastern_temple",
    "loc_botanical_zoo",
}
_ANOMALOUS_SAFE_HQ_FACILITY_IDS = {
    "loc_agency_hq",
    "loc_private_hq_1",
    "loc_private_hq_2",
    "loc_player_house",
}


def _collect_anomalous_bounty_candidate_locations(session_id: int, scen_key: str) -> list[str]:
    """
    Collects candidate field locations for Anomalous Incursions bounties, expanding
    consolidated multi-wing complexes (`loc_general_hospital`, `loc_theme_park`,
    `loc_eastern_temple`, `loc_botanical_zoo`) to `Zone ➔ Complex ➔ Wing` while
    excluding safe Agency HQs and the player's residence.
    """
    candidates: list[str] = []
    if session_id:
        try:
            nodes = db.get_session_world_nodes(session_id) or []
            if nodes:
                node_map = {n["node_id"]: n for n in nodes}
                rooms_by_parent: dict[str, list[dict]] = {}
                for n in nodes:
                    if n.get("node_type") == "ROOM" and n.get("parent_id"):
                        rooms_by_parent.setdefault(str(n["parent_id"]), []).append(n)
                for n in nodes:
                    if n.get("node_type") != "FACILITY":
                        continue
                    nid = str(n.get("node_id") or "")
                    if nid in _ANOMALOUS_SAFE_HQ_FACILITY_IDS or nid.startswith("loc_hq_"):
                        continue
                    parent = node_map.get(n.get("parent_id"))
                    z_name = parent["name"] if parent else "Metropolitan Grid"
                    if nid in _ANOMALOUS_CONSOLIDATED_COMPLEX_IDS:
                        for w in rooms_by_parent.get(nid, []):
                            if w.get("name"):
                                candidates.append(f"{z_name} ➔ {n['name']} ➔ {w['name']}")
                    elif n.get("name"):
                        candidates.append(f"{z_name} ➔ {n['name']}")
        except Exception:
            pass
    if not candidates:
        try:
            from mechanics.world.locations import get_discovered_primary_locations
            zones_dict = get_discovered_primary_locations(session_id, scen_key) or {}
            for z, prims in zones_dict.items():
                for p in prims:
                    p_low = p.lower()
                    if "lobby" not in p_low and "bedroom" not in p_low and "hq" not in p_low:
                        candidates.append(f"{z} ➔ {p}")
        except Exception:
            pass
    return candidates


def _build_anomalous_fallback_bounties(
    session_id: int,
    board_key: str,
    default_loc: str,
    candidate_locations: list[str] | None = None,
    faction_name: str = "",
    seed_offset: int = 0,
) -> list[dict]:
    """Builds 3 deterministic scenario-specific bounties for Anomalous Incursions with faction flavor bias."""
    import namegen

    cand_locs = [c.replace(" -> ", " ➔ ") for c in (candidate_locations or []) if c]
    if not cand_locs:
        cand_locs = [default_loc or "Metropolitan Grid ➔ Civic Plaza"]

    preferred_labels = ANOMALOUS_FACTION_BOARD_ARCHETYPE_WEIGHTS.get(
        board_key, ANOMALOUS_FACTION_BOARD_ARCHETYPE_WEIGHTS["freelance_app"]
    )
    arch_by_label = {a["label"]: a for a in ANOMALOUS_BOUNTY_ARCHETYPES}

    from mechanics.world.locations import format_clean_location_prose
    results: list[dict] = []
    for i in range(3):
        lbl = preferred_labels[(int(session_id or 1) + seed_offset + i) % len(preferred_labels)]
        arch_meta = arch_by_label.get(lbl, ANOMALOUS_BOUNTY_ARCHETYPES[i % len(ANOMALOUS_BOUNTY_ARCHETYPES)])
        tgt_loc = cand_locs[(int(session_id or 1) + seed_offset + i * 2) % len(cand_locs)]
        sec_loc = cand_locs[(int(session_id or 1) + seed_offset + i * 2 + 1) % len(cand_locs)]
        tgt_prose = format_clean_location_prose(tgt_loc, include_zone=True, preposition="in")
        tgt_short = format_clean_location_prose(tgt_loc, include_zone=False)
        sec_short = format_clean_location_prose(sec_loc, include_zone=False)
        entity_name = namegen.generate_anomalous_entity_name(hash_val=int(session_id or 1) * 17 + seed_offset + i * 13)

        sponsor_prefix = f"[{faction_name}] " if faction_name and board_key != "freelance_app" else ""
        nh_temp = ""
        is_nh = "non-hostile" in lbl.lower()
        if is_nh:
            nh_temp = "timid" if ((int(session_id or 1) + seed_offset + i) % 2 == 0) else "volatile"
            temp_cue = (
                "Timid/elusive demeanor—startling it risks escape."
                if nh_temp == "timid"
                else "Volatile/territorial aura—provoking it risks combat."
            )
            title = f"{arch_meta['title_prefix']}: {entity_name}"[:58]
            obj = f"{sponsor_prefix}Contain '{entity_name}' alive at {tgt_prose}. {temp_cue}"[:200]
            stage_1_lbl = f"Arrive at {tgt_short} and observe '{entity_name}'s temperament"
            stage_2_lbl = f"Encounter and contain non-hostile entity '{entity_name}' alive at {sec_short}"
        elif "Entity" in lbl:
            title = f"{arch_meta['title_prefix']}: {entity_name}"[:58]
            obj = f"{sponsor_prefix}{arch_meta['default_objective']} Target manifestation '{entity_name}' sighted at {tgt_prose}."[:200]
            stage_1_lbl = f"Arrive at {tgt_short} and establish perimeter scan"
            stage_2_lbl = f"Execute containment protocol for '{title}' at {sec_short}"
        else:
            fac_short = tgt_short
            title = f"{arch_meta['title_prefix']} at {fac_short}"[:58]
            obj = f"{sponsor_prefix}{arch_meta['default_objective']} Active location: {tgt_prose}."[:200]
            stage_1_lbl = f"Arrive at {tgt_short} and establish perimeter scan"
            stage_2_lbl = f"Execute containment protocol for '{title}' at {sec_short}"

        entry_dict = {
            "quest_type": lbl,
            "title": title,
            "objective": obj,
            "required_item": arch_meta.get("req_item", ""),
            "reward_xp": 130 + (i * 20),
            "reward_gold": 65 + (i * 20),
            "reward_item": "Trauma Medkit" if i == 0 else ("Cognitive Stabilizer Ampoule" if i == 1 else ""),
            "faction_rep_reward": 10,
            "waypoints": [
                {"stage_index": 1, "stage_label": stage_1_lbl, "target_location": tgt_loc, "completion_trigger": "arrival"},
                {"stage_index": 2, "stage_label": stage_2_lbl, "target_location": sec_loc, "completion_trigger": "skill_check"},
            ],
        }
        if is_nh:
            entry_dict["non_hostile_temperament"] = nh_temp
            entry_dict["entity_name"] = entity_name
        results.append(entry_dict)
    return results


BOUNTY_BOARD_SYSTEM_PROMPT = build_bounty_system_prompt()


def _filter_general_bounties(rows: list[dict]) -> list[dict]:
    """Excludes Faction HQ internal bounties from Freelance/General notice boards."""
    return [
        q for q in (rows or [])
        if not str(q.get("quest_id") or "").startswith("FBNT-")
        and "faction:" not in str(q.get("quest_notes") or "")
    ]


async def generate_bounty_board(session: dict | int, force_refresh: bool = False) -> list[dict]:
    """Generates 3 dynamic bounty board postings for a session using LLM JSON completion."""
    from game_engine import _scenario_block, is_nsfw_scenario
    if isinstance(session, (int, str)):
        session_id = int(session)
        session = db.get_session(session_id) or {"id": session_id}
    else:
        session_id = session["id"]

    if not force_refresh:
        existing = _filter_general_bounties(db.get_session_quests(session_id, status="Available"))
        if len(existing) >= 3:
            return existing
    else:
        # Clear stale unaccepted general bounties upon refresh so new ones replace them cleanly
        with db.get_conn() as conn:
            conn.execute(
                "DELETE FROM quests WHERE session_id=? AND status='Available' AND (quest_id LIKE 'BNT-%' AND quest_id NOT LIKE 'BNT-FLW-%') AND quest_id NOT LIKE 'COMM-%' AND (quest_notes IS NULL OR (quest_notes NOT LIKE 'faction:%' AND quest_notes NOT LIKE '%commission:%' AND quest_notes NOT LIKE '%followup_to:%'))",
                (session_id,)
            )
            conn.commit()
        try:
            build_consequence_followup_bounty(session_id, session=session)
        except Exception:
            pass


    scen_block = _scenario_block(session)
    loc = session.get("current_location", "the local hub")
    scen_key = session.get("scenario")

    system_prompt = build_bounty_system_prompt(scen_key)

    school_hints = ""
    from mechanics.world.locations import is_school_scenario
    if is_school_scenario(scen_key):
        from mechanics.social.school_roster import ensure_school_directory_exists
        roster = ensure_school_directory_exists(session)
        if roster:
            seniors = [c for c in roster if c.get("grade") == "Senior"]
            juniors = [c for c in roster if c.get("grade") == "Junior"]
            under = [c for c in roster if c.get("grade") in ("Sophomore", "Freshman")]
            faculty = [c for c in roster if c.get("grade") == "Faculty"]

            sample = []
            if seniors: sample.append(seniors[(session_id + 1) % len(seniors)])
            if juniors: sample.append(juniors[(session_id + 2) % len(juniors)])
            if under: sample.append(under[(session_id + 3) % len(under)])
            if faculty: sample.append(faculty[(session_id + 4) % len(faculty)])

            student_lines = [
                f"- {c['name']} [{c.get('grade')}] ({c.get('role')} | Club: {c.get('club')}) — Stationed at: {c.get('primary_facility')}"
                for c in sample
            ]
            school_hints = (
                "\nCAMPUS DIRECTORY & GRADE HIERARCHY COMMISSIONS:\n"
                "You MUST ground these 3 campus requests in the school's actual student directory and grade dynamics:\n"
                + "\n".join(student_lines) + "\n"
                "- Ensure requests reflect grade dynamics across diverse aspects of campus life: e.g. an Upperclassman (Senior) delegating council/varsity responsibilities or club leadership, a Junior classmate requesting club showdown support, gossip investigation, or study pacts, an Underclassman (Freshman/Sophomore) asking for guidance or protection from upperclassmen, or a Faculty teacher offering extra credit or disciplinary tasks.\n"
                "- Each request MUST use a DIFFERENT scenario archetype (e.g. Gossip Control, Club Showdown, Exam Heist, Secret Admirer, Academic Rescue, Matchmaking, Campus Infiltration) — do NOT make all 3 requests the same archetype!\n"
                "- MULTI-LOCATION CAMPUS TRAVEL: Use real school facilities to create multi-stage journeys across facilities! For example: Meet Student A at Classroom 3-B (Stage 1) -> Deliver secret note to Senior B at Student Council Office (Stage 2) -> Return to Classroom 3-B to report back (Stage 3).\n"
            )

    loc_hints = ""
    candidate_locations = []
    from mechanics.world.locations import get_discovered_primary_locations, get_session_school_name
    zones_dict = get_discovered_primary_locations(session_id, scen_key)
    if scenario_data.is_anomalous_incursions_scenario(scen_key):
        candidate_locations = _collect_anomalous_bounty_candidate_locations(session_id, scen_key)
    if not candidate_locations:
        for z, prims in zones_dict.items():
            for p in prims:
                candidate_locations.append(f"{z} -> {p}")

    if is_school_scenario(scen_key):
        school_zone = get_session_school_name(session_id, scen_key) if session_id else "Westlake Academy"
        athletics_zone = next((z for z in zones_dict if any(w in z.lower() for w in ["athletics", "grounds", "sports"])), "School Grounds & Athletics")
        commons_zone = next((z for z in zones_dict if any(w in z.lower() for w in ["commons", "plaza", "dining"])), "Student Commons & Central Plaza")
        arts_zone = next((z for z in zones_dict if any(w in z.lower() for w in ["cultural arts", "student union", "arts & union"])), "Cultural Arts & Student Union")
        abandoned_zone = next((z for z in zones_dict if any(w in z.lower() for w in ["abandoned", "old campus", "clock tower"])), "Abandoned Old Campus Building")

        # 1. Academic Wing
        academic_facilities = [
            f for f in zones_dict.get(school_zone, ["Homeroom Classroom", "School Library", "Chemistry & Science Lab", "School Rooftop", "Entrance Foyer & Shoe Lockers"])
            if f not in ("Science Wing", "Administration Wing", "Academic Wing", "East Wing")
        ]
        # 2. Athletics Complex
        athletics_facilities = zones_dict.get(athletics_zone, ["Main Gymnasium", "Athletic Field", "Swimming Pool Facility", "Martial Arts Dojo", "Behind Gym Storage Sheds"])
        # 3. Student Commons & Dining
        commons_facilities = zones_dict.get(commons_zone, ["Central Courtyard", "Campus Dining Hall & Cafeteria", "Vending Machine Pavilion", "Botanical Glasshouse"])
        # 4. Cultural Arts & Student Union
        arts_facilities = zones_dict.get(arts_zone, ["Student Council Office", "School Auditorium Stage", "Music Wing Rehearsal Hall", "Fine Arts Studio", "Campus Media & Broadcasting Room", "Student Clubroom Corridor"])
        # 5. Abandoned Old Campus
        abandoned_facilities = zones_dict.get(abandoned_zone, ["Decaying Clock Tower", "Old Storage Room 3-B", "Derelict Old Gymnasium", "Boarded Old Infirmary"])

        # 6. Commercial hangout & shopping spots
        commercial_zone = next((z for z in zones_dict if any(w in z.lower() for w in ["commercial", "strip", "market", "shops", "district"])), "Komorebi Commercial Strip")
        commercial_places = zones_dict.get(commercial_zone, ["Café Monolith", "Chrono-Quest Arcade", "Convenience Store", "Karaoke Lounge", "Vintage Bookstore"])

        # 7. Town / residential & parks
        residential_zone = next((z for z in zones_dict if any(w in z.lower() for w in ["residential", "town", "neighborhood"])), "Sakura Hill Residential Town")
        residential_places = [p for p in zones_dict.get(residential_zone, ["Greenwood Gardens"]) if "room" not in p.lower() and "house" not in p.lower()]
        if not residential_places:
            residential_places = ["Greenwood Gardens"]

        # 8. Off-campus nature & outings
        mystery_places = []
        for z, prims in zones_dict.items():
            if z not in (school_zone, athletics_zone, commons_zone, arts_zone, abandoned_zone, commercial_zone, residential_zone) and not any(w in z.lower() for w in ["anderson", "bedroom"]):
                for p in prims[:2]:
                    mystery_places.append(f"'{z} ➔ {p}'")
        if not mystery_places:
            mystery_places = [
                f"'Minami Coastal Pier & Bay ➔ Sandy Beach & Coastline'",
                f"'Mount Tsukimi Recreational Park ➔ Mountain Lake Pier'"
            ]

        academic_str = ", ".join(f"'{school_zone} ➔ {f}'" for f in academic_facilities[:6])
        athletics_str = ", ".join(f"'{athletics_zone} ➔ {f}'" for f in athletics_facilities[:5])
        commons_str = ", ".join(f"'{commons_zone} ➔ {f}'" for f in commons_facilities[:4])
        arts_str = ", ".join(f"'{arts_zone} ➔ {f}'" for f in arts_facilities[:5])
        abandoned_str = ", ".join(f"'{abandoned_zone} ➔ {f}'" for f in abandoned_facilities[:4])
        commercial_str = ", ".join(f"'{commercial_zone} ➔ {f}'" for f in commercial_places[:5])
        residential_str = ", ".join(f"'{residential_zone} ➔ {f}'" for f in residential_places[:3])
        mystery_str = ", ".join(mystery_places[:4])

        school_hints += (
            f"\nVALID REGIONAL DESTINATIONS FOR WAYPOINTS:\n"
            f"- School Campus (Academic Wing): {academic_str}\n"
            f"- School Grounds & Athletics Complex: {athletics_str}\n"
            f"- Student Commons & Campus Dining: {commons_str}\n"
            f"- Cultural Arts & Student Union: {arts_str}\n"
            f"- Abandoned Old Campus Building: {abandoned_str}\n"
            f"- Town & Commercial Hangouts: {commercial_str}\n"
            f"- Residential & Parks: {residential_str}\n"
            f"- Off-Campus Nature & Outings: {mystery_str}\n\n"
            f"APPROPRIATE NARRATIVE REASONS & OBJECTIVES FOR TARGETING WIDER AREAS:\n"
            f"Bounty requests MUST NOT be restricted to classrooms — student life extends across the entire district! Ground student requests with believable motivations:\n"
            f"1. Commercial Hangouts (Café, Arcade, Convenience Store, Karaoke, Bookstore):\n"
            f"   - Study Fuel & Sugar Runs: Buying specialty matcha lattes or pastries from Café Monolith to power an all-night cram session or appease a stressed student council member.\n"
            f"   - Arcade Rivalries & Favors: Helping an unconfident classmate win a rare crane machine plushie for their crush, or challenging a rival school's gaming champ at Chrono-Quest Arcade.\n"
            f"   - Supply Runs & Festival Prep: Running to the Convenience Store or Bookstore to buy emergency poster markers, snacks, or reference books for club activities.\n"
            f"   - Discretion & Gossip: Holding secret meetups in a Karaoke Lounge booth or café corner to trade sensitive rumors away from teachers and disciplinary prefects.\n"
            f"2. Athletics & Outdoor Grounds:\n"
            f"   - Varsity Scouting & Equipment: Infiltrating the opposing team's practice at the Main Gymnasium, retrieving a forgotten playbook from the field bleachers, or pool training bets.\n"
            f"   - Courtyard Meetups: Meeting discreetly under the cherry tree in the Central Courtyard for notes, lunch pacts, or confidential club recruitment.\n"
            f"3. Residential Town & Parks:\n"
            f"   - Park Study & Confessions: Meeting at the Greenwood Gardens gazebo/benches for tranquil tutoring or heartfelt confessions away from campus gossip.\n"
            f"   - Off-Campus Errands: Returning a classmate's lost notebook, jacket, or study notes to their neighborhood after school.\n"
            f"4. Off-Campus Mystery, Dares & Outings:\n"
            f"   - Occult Club Dares: Investigating an urban legend or retrieving an old relic from the Abandoned Old Campus Building on a dare.\n"
            f"   - Nature & Biology Projects: Collecting water/sand samples at Minami Coastal Beach or cataloging flora on Mount Tsukimi.\n\n"
            f"- STRICT RULE: 'target_location' MUST use 'Zone ➔ Primary Place' format (or 'Zone -> Primary Place') from the valid regional destinations above.\n"
            f"- STRICTLY FORBIDDEN: NEVER invent intermediate wings like 'Administration Wing'! Always use '{school_zone} ➔ Student Council Office', NOT '{school_zone} ➔ Administration Wing ➔ Student Council Office'.\n"
        )
    elif candidate_locations:
        loc_hints = "\nAvailable Regional Locations for Waypoints:\n" + "\n".join(f"- {l}" for l in candidate_locations[:8]) + "\n"

    is_anom = scenario_data.is_anomalous_incursions_scenario(scen_key)
    anom_hints = ""
    if is_anom:
        pref_archs = ", ".join(ANOMALOUS_FACTION_BOARD_ARCHETYPE_WEIGHTS["freelance_app"])
        anom_hints = (
            f"\nFREELANCE ANOMALY DISPATCH APP RULES:\n"
            f"- Prioritize civilian & freelance containment commissions from these archetypes: {pref_archs}.\n"
            f"- NEVER use numeric threat grades (e.g. never say 'Grade-4').\n"
        )

    user_prompt = (
        f"{scen_block}\n"
        f"Location: {loc}\n"
        f"{school_hints}\n"
        f"{anom_hints}\n"
        f"{loc_hints}\n"
        f"Generate 3 dynamic bounties for the local notice board.\n"
        f"Respond with JSON matching exactly this schema:\n{BOUNTY_BOARD_SCHEMA}"
    )

    _is_llm_mocked = hasattr(call_llm_json, "_mock_name")
    if _is_llm_mocked:
        result = await call_llm_json(system_prompt, user_prompt, temperature=0.8,
                                      is_nsfw=scenario_data.uses_nsfw_model(scen_key), use_utility=True)
        bounties_raw = result.get("bounties", []) or []
    else:
        bounties_raw = []

    if not bounties_raw:
        if is_anom:
            bounties_raw = _build_anomalous_fallback_bounties(
                session_id=session_id,
                board_key="freelance_app",
                default_loc=loc,
                candidate_locations=candidate_locations,
            )
        elif is_school_scenario(scen_key):
            bounties_raw = [
                {
                    "quest_type": "Academic Rescue",
                    "title": "Study Notes Delivery",
                    "objective": "Deliver cram-session biology notes to a classmate before fifth period.",
                    "reward_xp": 120,
                    "reward_gold": 30,
                    "reward_item": "Study Highlighter",
                    "waypoints": [
                        {"stage_index": 1, "stage_label": "Pick up notes from homeroom desk", "target_location": loc, "completion_trigger": "arrival"}
                    ]
                },
                {
                    "quest_type": "Campus Errand",
                    "title": "Cafeteria Snack Courier",
                    "objective": "Rush to grab seasonal matcha pastries and drinks for the student council.",
                    "reward_xp": 100,
                    "reward_gold": 25,
                    "reward_item": "Matcha Snack Box",
                    "waypoints": [
                        {"stage_index": 1, "stage_label": "Secure order at the dining pavilion", "target_location": loc, "completion_trigger": "arrival"}
                    ]
                },
                {
                    "quest_type": "Gossip Control",
                    "title": "Lost Archive Key",
                    "objective": "Inquire quietly near the courtyard to recover a misplaced clubroom key.",
                    "reward_xp": 140,
                    "reward_gold": 40,
                    "reward_item": "Club Token",
                    "waypoints": [
                        {"stage_index": 1, "stage_label": "Search the courtyard benches", "target_location": loc, "completion_trigger": "skill_check"}
                    ]
                }
            ]
        else:
            bounties_raw = [
                {
                    "quest_type": "Courier Commission",
                    "title": "Urgent Supply Courier",
                    "objective": "Deliver essential medical supplies to the nearby outpost depot.",
                    "reward_xp": 120,
                    "reward_gold": 35,
                    "reward_item": "Courier Canteen",
                    "waypoints": [
                        {"stage_index": 1, "stage_label": "Deliver package safely", "target_location": loc, "completion_trigger": "arrival"}
                    ]
                },
                {
                    "quest_type": "Perimeter Patrol",
                    "title": "District Scout Task",
                    "objective": "Survey the local sector boundaries for signs of anomalous interference.",
                    "reward_xp": 130,
                    "reward_gold": 40,
                    "reward_item": "Scout Scope",
                    "waypoints": [
                        {"stage_index": 1, "stage_label": "Patrol checkpoint", "target_location": loc, "completion_trigger": "skill_check"}
                    ]
                },
                {
                    "quest_type": "Contract Gig",
                    "title": "Discreet Information Drop",
                    "objective": "Leave an encoded tracking slate at the designated dead-drop receptacle.",
                    "reward_xp": 150,
                    "reward_gold": 45,
                    "reward_item": "",
                    "waypoints": [
                        {"stage_index": 1, "stage_label": "Deposit slate into container", "target_location": loc, "completion_trigger": "arrival"}
                    ]
                }
            ]

    from mechanics.world.locations import clean_narrative_location_arrows
    for idx, b in enumerate(bounties_raw):
        if not isinstance(b, dict) or not b.get("title"):
            continue
        b_id = f"BNT-{uuid.uuid4().hex[:8].upper()}"
        q_type = str(b.get("quest_type", "Side Bounty"))
        obj_text = clean_narrative_location_arrows(str(b.get("objective", "Complete the bounty task.")))[:200]
        title_text = clean_narrative_location_arrows(str(b.get("title")))[:60]

        from mechanics.narrative.blueprints import get_blueprint_for_archetype, infer_required_item_and_count_from_text, roll_quest_deadline
        blueprint_id = get_blueprint_for_archetype(q_type, obj_text)
        client_npc, client_loc = resolve_or_seed_bounty_client(session_id, session, b, loc, index=idx)
        if client_loc:
            from mechanics.world.locations import parse_tiered_location
            z_c, p_c, _ = parse_tiered_location(client_loc, scen_key, session_id=session_id)
            client_loc = f"{z_c} ➔ {p_c}"

        req_item = str(b.get("required_item", "") or "").strip()
        req_count = 1
        if not req_item and blueprint_id == "ACQUISITION":
            req_item, req_count = infer_required_item_and_count_from_text(obj_text, title_text)
        elif req_item:
            _, inf_cnt = infer_required_item_and_count_from_text(obj_text, title_text)
            if inf_cnt > 1:
                req_count = inf_cnt

        d_day, d_min = roll_quest_deadline(
            blueprint_id=blueprint_id,
            quest_type=q_type,
            title=title_text,
            objective=obj_text,
            current_day=int(session.get("current_day") or 1) if session else 1,
            current_minute=int(session.get("current_minute") or 480) if session else 480,
            is_story_quest=False,
            seed_str=b_id,
        )

        q_notes_gen = "board_source:freelance_app" if is_anom else ""
        if is_anom and ("non-hostile" in str(q_type or "").lower() or b.get("non_hostile_temperament")):
            from mechanics.world.anomalous_events import get_non_hostile_entity_temperament, extract_non_hostile_entity_name
            nh_t = str(b.get("non_hostile_temperament") or get_non_hostile_entity_temperament(seed_key=b_id))
            nh_e = str(b.get("entity_name") or extract_non_hostile_entity_name({"title": title_text, "objective": obj_text}))
            q_notes_gen = f"{q_notes_gen}|non_hostile_temperament:{nh_t}|entity_name:{nh_e}"

        db.upsert_quest(
            session_id=session_id,
            quest_id=b_id,
            quest_type=q_type,
            title=title_text,
            objective=obj_text,
            progress=f"0/{req_count} {req_item} Collected" if (blueprint_id == "ACQUISITION" and req_item) else "0/1 Target Sighted",
            current_clues="",
            status="Available",
            reward_xp=int(b.get("reward_xp", 120)),
            reward_gold=int(b.get("reward_gold", 35)),
            reward_stat_points=0,
            reward_item=str(b.get("reward_item", "") or "")[:60],
            quest_notes=q_notes_gen,
            blueprint_id=blueprint_id,
            client_npc=client_npc,
            client_location=client_loc,
            required_item=req_item,
            required_item_count=req_count,
            deadline_day=d_day,
            deadline_minute=d_min,
        )

        # Persist waypoints for this bounty
        from mechanics.world.waypoints import ensure_multi_stage_waypoints
        raw_waypoints = b.get("waypoints") or []
        sec_loc = candidate_locations[1] if len(candidate_locations) > 1 else ""
        tert_loc = candidate_locations[2] if len(candidate_locations) > 2 else ""
        validated_wps = ensure_multi_stage_waypoints(
            raw_waypoints,
            default_loc=loc,
            archetype=q_type,
            secondary_loc=sec_loc,
            tertiary_loc=tert_loc,
            session_id=session_id,
            scen_key=scen_key,
            client_npc=client_npc,
            client_location=client_loc,
            required_item=req_item,
        )
        if validated_wps:
            from mechanics.world.locations import parse_tiered_location, clean_narrative_location_arrows
            for wp in validated_wps:
                if wp.get("stage_label"):
                    wp["stage_label"] = clean_narrative_location_arrows(wp["stage_label"])
                raw_tgt = wp.get("target_location", "")
                if raw_tgt:
                    raw_parts = [x.strip() for x in raw_tgt.replace("->", "➔").split("➔") if x.strip()]
                    z_norm, p_norm, s_norm = parse_tiered_location(raw_tgt, scen_key, session_id=session_id)
                    if s_norm and len(raw_parts) >= 3:
                        wp["target_location"] = f"{z_norm} ➔ {p_norm} ➔ {s_norm}"
                    else:
                        wp["target_location"] = f"{z_norm} ➔ {p_norm}"
            db.save_quest_waypoints(session_id=session_id, quest_id=b_id, waypoints=validated_wps, sub_obj_id=None)

    return _filter_general_bounties(db.get_session_quests(session_id, status="Available"))


# ---------------------------------------------------------------- Faction Bounty Board
FACTION_BOUNTY_SCHEMA = """{
  "bounties": [
    {
      "quest_type": "string, creative faction-appropriate archetype",
      "title": "string, evocative max 50 chars title",
      "objective": "string, rich 1-2 sentence objective tied to faction goals",
      "client_npc": "string, full name of the faction officer or liaison requesting the mission",
      "client_location": "string, faction HQ or outpost location (Zone -> Primary Place)",
      "required_item": "string, specific supply, relic, or cipher item to gather/deliver if applicable, or empty string",
      "reward_xp": integer 80-200,
      "reward_gold": integer 10-80,
      "reward_item": "string, faction-themed item/equipment or empty string",
      "faction_rep_reward": integer 5-20,
      "waypoints": [
        {
          "stage_index": 1,
          "stage_label": "string, specific 1-sentence task for this stage",
          "target_location": "string, Zone -> Primary Place format",
          "target_npc": "string, NPC name to meet/contact, or empty string",
          "completion_trigger": "arrival OR skill_check",
          "resource_target": 0
        }
      ]
    }
  ]
}"""

FACTION_BOUNTY_SYSTEM_PROMPT = (
    "Generate 3 faction-exclusive bounty board postings for the given faction.\n"
    "Bounties MUST be strongly tied to the faction's identity, goals, and rivalries.\n"
    "Every bounty MUST specify a named `client_npc` (the faction officer/liaison) and `client_location`.\n"
    "For supply, delivery, or scavenging tasks, specify the exact item in `required_item`.\n"
    "Each bounty MUST include a `faction_rep_reward` integer (5-20) in addition to gold/XP.\n"
    "Include a `waypoints` array (2-3 stages) with 'Zone -> Primary Place' target_location spanning distinct sites.\n"
    "Respond with ONLY a single valid JSON object matching the schema exactly, no prose or code fences."
)


async def generate_faction_bounty_board(session: dict, faction: dict,
                                         force_refresh: bool = False) -> list[dict]:
    """
    Generate 3 faction-exclusive bounty board postings rewarding both gold/XP and faction reputation.
    """
    from game_engine import _scenario_block, call_llm_json, is_nsfw_scenario
    session_id = session["id"]
    faction_id = faction.get("faction_id", "")
    faction_name = faction.get("name", "Faction")

    if not force_refresh:
        # Check for cached faction bounties (stored with quest_notes matching faction_id)
        existing = [
            q for q in db.get_session_quests(session_id, status="Available")
            if q.get("quest_notes", "").startswith(f"faction:{faction_id}")
        ]
        if len(existing) >= 3:
            return existing
    else:
        # Clear stale unaccepted faction bounties for this faction upon refresh
        with db.get_conn() as conn:
            conn.execute(
                "DELETE FROM quests WHERE session_id=? AND status='Available' AND quest_notes LIKE ?",
                (session_id, f"faction:{faction_id}%")
            )
            conn.commit()

    scen_block = _scenario_block(session)
    loc = faction.get("hq_location_id") or session.get("current_location", "the faction HQ")
    scen_key = session.get("scenario")

    is_anom = scenario_data.is_anomalous_incursions_scenario(scen_key)
    f_arch = ""
    anom_fac_hints = ""
    candidate_locations = []
    if is_anom:
        from mechanics.social.factions import infer_anomalous_faction_archetype, ANOMALOUS_DISTRUSTED_ARCHETYPES
        f_arch = infer_anomalous_faction_archetype(faction)
        if f_arch in ANOMALOUS_DISTRUSTED_ARCHETYPES:
            # Cult and Clandestine Syndicate are distrusted/unlicensed and do not host operable public bounty boards
            return []
        candidate_locations = _collect_anomalous_bounty_candidate_locations(session_id, scen_key)
        pref_archs = ", ".join(ANOMALOUS_FACTION_BOARD_ARCHETYPE_WEIGHTS.get(f_arch, ANOMALOUS_FACTION_BOARD_ARCHETYPE_WEIGHTS["public_agency"]))
        anom_fac_hints = (
            f"ANOMALOUS FACTION BOARD ARCHETYPE BIAS ({f_arch}):\n"
            f"- Prioritize these archetypes for {faction_name}: {pref_archs}.\n"
            f"- NEVER use numeric threat grades (e.g. never say 'Grade-4').\n\n"
        )

    user_prompt = (
        f"{scen_block}\n"
        f"Faction: {faction_name} (Category: {faction.get('category', 'guild')})\n"
        f"Faction HQ: {loc}\n"
        f"Faction Reputation: {faction.get('reputation_score', 0):+d}\n\n"
        f"{anom_fac_hints}"
        f"Generate 3 exclusive faction bounties for the {faction_name} notice board.\n"
        f"Respond with JSON matching exactly this schema:\n{FACTION_BOUNTY_SCHEMA}"
    )

    _is_llm_mocked = hasattr(call_llm_json, "_mock_name")
    from mechanics.world.locations import format_clean_location_prose, clean_narrative_location_arrows
    loc_short = format_clean_location_prose(loc, include_zone=False)
    loc_prose = format_clean_location_prose(loc, include_zone=True, preposition="in")
    if _is_llm_mocked:
        result = await call_llm_json(FACTION_BOUNTY_SYSTEM_PROMPT, user_prompt, temperature=0.8,
                                      is_nsfw=scenario_data.uses_nsfw_model(scen_key), use_utility=True)
        bounties_raw = result.get("bounties", []) or []
    elif is_anom:
        bounties_raw = _build_anomalous_fallback_bounties(
            session_id=session_id,
            board_key=f_arch or "public_agency",
            default_loc=loc,
            candidate_locations=candidate_locations,
            faction_name=faction_name,
            seed_offset=sum(ord(c) for c in str(faction_id or faction_name)),
        )
    else:
        bounties_raw = [
            {
                "quest_type": "Faction Operation",
                "title": f"Patrol for {faction_name}",
                "objective": f"Conduct reconnaissance around the outskirts for {faction_name}.",
                "client_npc": f"{faction_name} Vanguard",
                "client_location": loc,
                "reward_xp": 120,
                "reward_gold": 40,
                "reward_item": "Faction Commendation",
                "faction_rep_reward": 10,
                "waypoints": [
                    {"stage_index": 1, "stage_label": f"Report to {faction_name} Vanguard", "target_location": loc, "completion_trigger": "arrival"}
                ]
            },
            {
                "quest_type": "Faction Supply",
                "title": f"Resource Delivery to {faction_name}",
                "objective": f"Secure and deliver critical supplies to {faction_name} headquarters.",
                "client_npc": f"{faction_name} Quartermaster",
                "client_location": loc,
                "required_item": "Supply Ration",
                "reward_xp": 100,
                "reward_gold": 35,
                "reward_item": "Supply Ration",
                "faction_rep_reward": 10,
                "waypoints": [
                    {"stage_index": 1, "stage_label": f"Deliver supplies to {loc_short}", "target_location": loc, "completion_trigger": "arrival"}
                ]
            },
            {
                "quest_type": "Faction Subterfuge",
                "title": f"Intelligence Gathering for {faction_name}",
                "objective": f"Investigate rival movements near {loc_prose}.",
                "client_npc": f"{faction_name} Spymaster",
                "client_location": loc,
                "reward_xp": 150,
                "reward_gold": 50,
                "reward_item": "Ciphered Scroll",
                "faction_rep_reward": 15,
                "waypoints": [
                    {"stage_index": 1, "stage_label": f"Scout area near {loc_short}", "target_location": loc, "completion_trigger": "arrival"}
                ]
            }
        ]

    for idx, b in enumerate(bounties_raw):
        if not isinstance(b, dict) or not b.get("title"):
            continue
        b_id = f"FBNT-{uuid.uuid4().hex[:8].upper()}"
        q_type = str(b.get("quest_type", "Faction Bounty"))
        obj_text = clean_narrative_location_arrows(str(b.get("objective", "Complete the faction task.")))[:200]
        title_text = clean_narrative_location_arrows(str(b.get("title")))[:60]
        faction_rep_reward = max(5, min(20, int(b.get("faction_rep_reward", 10))))

        from mechanics.narrative.blueprints import get_blueprint_for_archetype, infer_required_item_and_count_from_text
        blueprint_id = get_blueprint_for_archetype(q_type, obj_text)
        client_npc, client_loc = resolve_or_seed_bounty_client(session_id, session, b, loc, index=idx)
        if client_loc:
            from mechanics.world.locations import parse_tiered_location
            z_c, p_c, _ = parse_tiered_location(client_loc, scen_key, session_id=session_id)
            client_loc = f"{z_c} ➔ {p_c}"

        req_item = str(b.get("required_item", "") or "").strip()
        req_count = 1
        if not req_item and blueprint_id == "ACQUISITION":
            req_item, req_count = infer_required_item_and_count_from_text(obj_text, title_text)
        elif req_item:
            _, inf_cnt = infer_required_item_and_count_from_text(obj_text, title_text)
            if inf_cnt > 1:
                req_count = inf_cnt

        from mechanics.narrative.blueprints import roll_quest_deadline
        d_day, d_min = roll_quest_deadline(
            blueprint_id=blueprint_id,
            quest_type=q_type,
            title=title_text,
            objective=obj_text,
            current_day=int(session.get("current_day") or 1) if session else 1,
            current_minute=int(session.get("current_minute") or 480) if session else 480,
            is_story_quest=False,
            seed_str=b_id,
        )

        q_notes = f"faction:{faction_id}|board_source:{f_arch}|rep_reward:{faction_rep_reward}" if (is_anom and f_arch) else f"faction:{faction_id}|rep_reward:{faction_rep_reward}"
        if is_anom and ("non-hostile" in str(q_type or "").lower() or b.get("non_hostile_temperament")):
            from mechanics.world.anomalous_events import get_non_hostile_entity_temperament, extract_non_hostile_entity_name
            nh_t = str(b.get("non_hostile_temperament") or get_non_hostile_entity_temperament(seed_key=b_id))
            nh_e = str(b.get("entity_name") or extract_non_hostile_entity_name({"title": title_text, "objective": obj_text}))
            q_notes = f"{q_notes}|non_hostile_temperament:{nh_t}|entity_name:{nh_e}"
        db.upsert_quest(
            session_id=session_id,
            quest_id=b_id,
            quest_type=q_type,
            title=title_text,
            objective=obj_text,
            progress=f"0/{req_count} {req_item} Collected" if (blueprint_id == "ACQUISITION" and req_item) else "0/1 Target Sighted",
            current_clues="",
            status="Available",
            reward_xp=max(60, min(250, int(b.get("reward_xp", 120)))),
            reward_gold=max(5, min(120, int(b.get("reward_gold", 30)))),
            reward_stat_points=0,
            reward_item=str(b.get("reward_item", "") or "")[:60],
            quest_notes=q_notes,
            blueprint_id=blueprint_id,
            client_npc=client_npc,
            client_location=client_loc,
            required_item=req_item,
            required_item_count=req_count,
            deadline_day=d_day,
            deadline_minute=d_min,
        )
        from mechanics.world.waypoints import ensure_multi_stage_waypoints
        raw_waypoints = b.get("waypoints") or []
        validated_wps = ensure_multi_stage_waypoints(
            raw_waypoints,
            default_loc=loc,
            archetype=q_type,
            session_id=session_id,
            scen_key=scen_key,
            client_npc=client_npc,
            client_location=client_loc,
            required_item=req_item,
        )
        if validated_wps:
            from mechanics.world.locations import parse_tiered_location, clean_narrative_location_arrows
            for wp in validated_wps:
                if wp.get("stage_label"):
                    wp["stage_label"] = clean_narrative_location_arrows(wp["stage_label"])
                raw_tgt = wp.get("target_location", "")
                if raw_tgt:
                    raw_parts = [x.strip() for x in raw_tgt.replace("->", "➔").split("➔") if x.strip()]
                    z_norm, p_norm, s_norm = parse_tiered_location(raw_tgt, scen_key, session_id=session_id)
                    if s_norm and len(raw_parts) >= 3:
                        wp["target_location"] = f"{z_norm} ➔ {p_norm} ➔ {s_norm}"
                    else:
                        wp["target_location"] = f"{z_norm} ➔ {p_norm}"
            db.save_quest_waypoints(session_id=session_id, quest_id=b_id,
                                    waypoints=validated_wps, sub_obj_id=None)

    return [
        q for q in db.get_session_quests(session_id, status="Available")
        if q.get("quest_notes", "").startswith(f"faction:{faction_id}")
    ]


def get_faction_rep_reward_from_quest(quest: dict) -> int:
    """Extract the faction reputation reward embedded in quest_notes."""
    notes = quest.get("quest_notes") or ""
    try:
        for part in notes.split("|"):
            if part.startswith("rep_reward:"):
                return int(part.split(":")[1])
    except Exception:
        pass
    return 0


# -----------------------------------------------------------------------------
# Phase 4 Consequence Follow-Ups, Commissions & Board Replenishment
# -----------------------------------------------------------------------------

def build_consequence_followup_bounty(session_id: int, session: dict = None) -> dict | None:
    """
    Checks completed or failed quests for consequential narrative fallout (spared target,
    betrayed client, or failed strikes) and synthesizes a dedicated follow-up bounty.
    Tags the parent quest with 'followup_spawned:1'.
    """
    import re
    import db
    from mechanics.narrative.blueprints import has_quest_note_flag, roll_quest_deadline
    from db.quests import append_quest_note_flag_in_db
    if not session_id:
        return None
    
    if session is None:
        session = db.get_session(session_id) or {"id": session_id}
    scen_key = session.get("scenario") or "fantasy"
    curr_day = int(session.get("current_day") or 1)
    curr_min = int(session.get("current_minute") or 480)
    cur_loc = _resolve_session_location(session_id, session, scen_key)

    all_quests = db.get_session_quests(session_id) or []
    candidate_q = None
    followup_type = None

    for q in all_quests:
        qid = q.get("quest_id", "")
        if not qid:
            continue
        q_notes = str(q.get("quest_notes") or "")
        if has_quest_note_flag(q_notes, "followup_spawned"):
            continue
        status = q.get("status", "")
        res_app = str(q.get("resolution_approach") or "").lower()
        prog = str(q.get("progress") or "").lower()

        if status == "Completed" and ("spared" in res_app or "spared" in prog):
            candidate_q = q
            followup_type = "spared"
            break
        elif status == "Failed" and ("betray" in res_app or "betray" in prog):
            candidate_q = q
            followup_type = "betrayed"
            break
        elif status == "Failed" and ("strikes" in res_app or "escaped" in prog or "failed" in prog):
            candidate_q = q
            followup_type = "escaped"
            break

    if not candidate_q or not followup_type:
        return None

    parent_qid = candidate_q.get("quest_id")
    target_npc = candidate_q.get("target_npc") or ""
    if not target_npc:
        q_wps = db.get_quest_waypoints(session_id, parent_qid, None) or []
        for w in q_wps:
            if w.get("target_npc"):
                target_npc = w["target_npc"]
                break
    if not target_npc:
        m = re.search(r'\b(?!Eliminate|Defeat|Capture|Track|Find|Slay|Hunt|Confront|Investigate|Search|Deliver|Protect)([A-Z][a-z]+)\b', candidate_q.get("title", ""))
        target_npc = m.group(1) if m else "the Target"
    client_npc = candidate_q.get("client_npc") or "the Client"
    parent_title = candidate_q.get("title", "Contract")

    b_id = f"BNT-FLW-{uuid.uuid4().hex[:6].upper()}"

    if followup_type == "spared":
        title = f"Consequence: Inquiries on {target_npc}"[:60]
        q_type = "Investigation"
        bp_id = "INVESTIGATION"
        obj_text = f"Inquiries are spreading regarding the sudden disappearance of {target_npc} after '{parent_title}'. Ensure your deception remains concealed."[:200]
        new_client = client_npc
        new_target = "Informant"
    elif followup_type == "betrayed":
        title = f"Retribution: {client_npc}'s Vengeance"[:60]
        q_type = "Rivalry"
        bp_id = "CONTEST_RIVALRY"
        obj_text = f"{client_npc} has dispatched enforcers to retaliate for your breach of contract on '{parent_title}'. Neutralize the threat before they strike."[:200]
        new_client = "Underworld Fixer"
        new_target = f"{client_npc}'s Enforcer"
    else:  # escaped
        title = f"Second Chance: Track {target_npc}"[:60]
        q_type = "Bounty Hunting"
        bp_id = "NEUTRALIZATION"
        obj_text = f"Fresh sightings of {target_npc} from '{parent_title}' have surfaced. Track them down and finish the botched contract."[:200]
        new_client = client_npc
        new_target = target_npc

    d_day, d_min = roll_quest_deadline(
        blueprint_id=bp_id,
        quest_type=q_type,
        title=title,
        objective=obj_text,
        current_day=curr_day,
        current_minute=curr_min,
        is_story_quest=False,
        seed_str=b_id,
    )

    q_notes = f"followup_to:{parent_qid}"
    db.upsert_quest(
        session_id=session_id,
        quest_id=b_id,
        quest_type=q_type,
        title=title,
        objective=obj_text,
        progress="0/1 Target Located",
        current_clues="",
        status="Available",
        reward_xp=150,
        reward_gold=45,
        blueprint_id=bp_id,
        client_npc=new_client,
        client_location=cur_loc,
        deadline_day=d_day,
        deadline_minute=d_min,
        quest_notes=q_notes,
    )

    # Waypoints: 2 stages (Stage 1 arrival/investigate, Stage 2 confront/resolve)
    from mechanics.world.waypoints import ensure_multi_stage_waypoints
    from mechanics.world.locations import get_discovered_primary_locations, format_clean_location_prose
    zones_dict = get_discovered_primary_locations(session_id, scen_key) or {}
    discovered_locs = [f"{z} ➔ {p}" for z, prims in zones_dict.items() for p in prims] if isinstance(zones_dict, dict) else list(zones_dict)
    alt_locs = [dl for dl in discovered_locs if dl.strip().lower() != cur_loc.strip().lower()]
    sec_loc = alt_locs[0] if alt_locs else cur_loc
    ter_loc = alt_locs[1] if len(alt_locs) >= 2 else sec_loc
    cur_loc_short = format_clean_location_prose(cur_loc, include_zone=False)

    raw_wps = [
        {"stage_index": 1, "stage_label": f"Investigate rumors of {new_target} at {cur_loc_short}", "target_location": cur_loc, "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": f"Confront {new_target} and settle the matter", "target_location": sec_loc, "target_npc": new_target, "completion_trigger": "skill_check"},
    ]
    wps = ensure_multi_stage_waypoints(
        raw_wps,
        default_loc=cur_loc,
        archetype=q_type,
        session_id=session_id,
        scen_key=scen_key,
        secondary_loc=sec_loc,
        tertiary_loc=ter_loc,
        client_npc=new_client,
        client_location=cur_loc,
    )
    if wps:
        db.save_quest_waypoints(session_id, b_id, wps, sub_obj_id=None)

    # Mark parent quest
    append_quest_note_flag_in_db(session_id, parent_qid, "followup_spawned", "1")

    return db.get_quest_by_id(session_id, b_id)


def seed_contact_commission_if_eligible(session_id: int, session: dict = None) -> dict | None:
    """
    Checks for high-affinity contacts (relationship_score >= 25) without an active or prior commission.
    Seeds a bespoke high-paying Personal Commission ('COMM-...') and dispatches an incoming comms DM.
    """
    import db
    from mechanics.narrative.blueprints import roll_quest_deadline
    if not session_id:
        return None

    if session is None:
        session = db.get_session(session_id) or {"id": session_id}
    scen_key = session.get("scenario") or "fantasy"
    curr_day = int(session.get("current_day") or 1)
    curr_min = int(session.get("current_minute") or 480)
    cur_loc = _resolve_session_location(session_id, session, scen_key)

    existing_quests = db.get_session_quests(session_id) or []
    # Cap active/available personal commissions to 1 at a time
    for q in existing_quests:
        if q.get("status") in ("Available", "Active") and (
            str(q.get("quest_id", "")).startswith("COMM-") or "commission:1" in str(q.get("quest_notes") or "")
        ):
            return None

    # Exclude contacts who currently have an active/available quest OR already issued a COMM- commission previously
    excluded_client_names = set()
    for q in existing_quests:
        c_nm = str(q.get("client_npc", "")).strip().lower()
        if not c_nm:
            continue
        if q.get("status") in ("Available", "Active"):
            excluded_client_names.add(c_nm)
        elif str(q.get("quest_id", "")).startswith("COMM-") or "commission:1" in str(q.get("quest_notes") or ""):
            excluded_client_names.add(c_nm)

    contacts = db.get_contacts(session_id) or []
    eligible_contact = None
    for c in contacts:
        if not isinstance(c, dict):
            continue
        c_name = str(c.get("name") or "").strip()
        if not c_name:
            continue
        score = int(c.get("relationship_score") or 0)
        if score >= 25 and c_name.lower() not in excluded_client_names:
            eligible_contact = c
            break

    if not eligible_contact:
        return None

    c_name = eligible_contact.get("name")
    b_info = eligible_contact.get("basic_info") if isinstance(eligible_contact.get("basic_info"), dict) else {}
    c_loc = (
        eligible_contact.get("location")
        or eligible_contact.get("primary_facility")
        or b_info.get("location")
        or b_info.get("primary_facility")
        or cur_loc
    )

    comm_id = f"COMM-{uuid.uuid4().hex[:6].upper()}"
    title = f"Discreet Favor: {c_name}'s Request"[:60]
    q_type = "Personal Commission"
    bp_id = "SOCIAL_MANIPULATION"
    obj_text = f"{c_name} reached out privately seeking your assistance with a delicate personal matter."[:200]

    d_day, d_min = roll_quest_deadline(
        blueprint_id=bp_id,
        quest_type=q_type,
        title=title,
        objective=obj_text,
        current_day=curr_day,
        current_minute=curr_min,
        is_story_quest=False,
        seed_str=comm_id,
    )

    q_notes = "commission:1"
    db.upsert_quest(
        session_id=session_id,
        quest_id=comm_id,
        quest_type=q_type,
        title=title,
        objective=obj_text,
        progress="0/1 Request Addressed",
        current_clues="",
        status="Available",
        reward_xp=180,
        reward_gold=60,  # 1.5x payout
        blueprint_id=bp_id,
        client_npc=c_name,
        client_location=c_loc,
        deadline_day=d_day,
        deadline_minute=d_min,
        quest_notes=q_notes,
    )

    from mechanics.world.waypoints import ensure_multi_stage_waypoints
    from mechanics.world.locations import get_discovered_primary_locations, format_clean_location_prose
    zones_dict = get_discovered_primary_locations(session_id, scen_key) or {}
    discovered_locs = [f"{z} ➔ {p}" for z, prims in zones_dict.items() for p in prims] if isinstance(zones_dict, dict) else list(zones_dict)
    alt_locs = [dl for dl in discovered_locs if dl.strip().lower() != c_loc.strip().lower()]
    sec_loc = alt_locs[0] if alt_locs else c_loc
    ter_loc = alt_locs[1] if len(alt_locs) >= 2 else sec_loc
    c_loc_short = format_clean_location_prose(c_loc, include_zone=False)

    raw_wps = [
        {"stage_index": 1, "stage_label": f"Meet with {c_name} at {c_loc_short} to discuss the matter", "target_location": c_loc, "target_npc": c_name, "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": f"Resolve the confidential matter for {c_name}", "target_location": sec_loc, "completion_trigger": "skill_check"},
    ]
    wps = ensure_multi_stage_waypoints(
        raw_wps,
        default_loc=c_loc,
        archetype=q_type,
        session_id=session_id,
        scen_key=scen_key,
        secondary_loc=sec_loc,
        tertiary_loc=ter_loc,
        client_npc=c_name,
        client_location=c_loc,
    )
    if wps:
        db.save_quest_waypoints(session_id, comm_id, wps, sub_obj_id=None)

    # Phase 4 Comms: Send incoming Phone DM / Courier dispatch
    try:
        from game_engine.quests import send_quest_comms_message
        send_quest_comms_message(
            session_id=session_id,
            sender_npc_id=c_name,
            msg_type="contact_commission",
            quest_title=title,
            scen_key=scen_key,
        )
    except Exception:
        pass

    return db.get_quest_by_id(session_id, comm_id)


def replenish_daily_bounties_deterministic(
    session_id: int, session: dict = None, force: bool = False
) -> list[dict]:
    """
    Deterministically replenishes the session's Available bounty board postings up to 3:
    1. Checks for Consequence Follow-Up Bounties ('BNT-FLW-...').
    2. Checks for Contact Personal Commissions ('COMM-...').
    3. Fills remaining slots with deterministic blueprint templates without blocking LLM calls.
    """
    import db
    from mechanics.narrative.blueprints import roll_quest_deadline
    if not session_id:
        return []

    if session is None:
        session = db.get_session(session_id) or {"id": session_id}
    scen_key = session.get("scenario") or "fantasy"
    curr_day = int(session.get("current_day") or 1)
    curr_min = int(session.get("current_minute") or 480)
    cur_loc = _resolve_session_location(session_id, session, scen_key)

    avail = _filter_general_bounties(db.get_session_quests(session_id, status="Available") or [])
    if len(avail) >= 3 and not force:
        return avail

    # 1. Consequence Follow-Up
    if len(avail) < 3:
        flw = build_consequence_followup_bounty(session_id, session=session)
        if flw:
            avail.append(flw)

    # 2. Contact Commission
    if len(avail) < 3:
        comm = seed_contact_commission_if_eligible(session_id, session=session)
        if comm:
            avail.append(comm)

    # 3. Deterministic Templates if still < 3
    from mechanics.world.locations import get_discovered_primary_locations
    zones_dict = get_discovered_primary_locations(session_id, scen_key) or {}
    discovered_locs = [f"{z} ➔ {p}" for z, prims in zones_dict.items() for p in prims] if isinstance(zones_dict, dict) else list(zones_dict)
    alt_locs = [dl for dl in discovered_locs if dl.strip().lower() != cur_loc.strip().lower()]
    sec_loc = alt_locs[0] if alt_locs else cur_loc
    ter_loc = alt_locs[1] if len(alt_locs) >= 2 else sec_loc

    if scenario_data.is_anomalous_incursions_scenario(scen_key):
        from mechanics.narrative.blueprints import get_blueprint_for_archetype
        anom_loc_pool = _collect_anomalous_bounty_candidate_locations(session_id, scen_key)
        anom_alt = [dl for dl in anom_loc_pool if dl.strip().lower() != cur_loc.strip().lower()] or alt_locs or [cur_loc]
        anom_cands = _build_anomalous_fallback_bounties(
            session_id=session_id,
            board_key="freelance_app",
            default_loc=cur_loc,
            candidate_locations=anom_alt,
            seed_offset=curr_day * 7,
        )
        fallback_templates = [
            {
                "blueprint_id": get_blueprint_for_archetype(ac["quest_type"]),
                "quest_type": ac["quest_type"],
                "title": ac["title"],
                "objective": ac["objective"],
                "reward_xp": ac["reward_xp"],
                "reward_gold": ac["reward_gold"],
                "req_item": ac.get("required_item", ""),
                "stages": ac["waypoints"],
            }
            for ac in anom_cands
        ]
    else:
        from mechanics.world.locations import format_clean_location_prose
        cur_short = format_clean_location_prose(cur_loc, include_zone=False)
        sec_prose = format_clean_location_prose(sec_loc, include_zone=True, preposition="in")
        sec_short = format_clean_location_prose(sec_loc, include_zone=False)
        ter_prose = format_clean_location_prose(ter_loc, include_zone=True, preposition="in")
        ter_short = format_clean_location_prose(ter_loc, include_zone=False)
        fallback_templates = [
            {
                "blueprint_id": "ACQUISITION",
                "quest_type": "Resource Scavenge",
                "title": "Stockpile Scavenge",
                "objective": f"Gather vital supplies and materials from {sec_prose} for the local guild stockpile.",
                "reward_xp": 120,
                "reward_gold": 35,
                "req_item": "Supply Crate",
                "stages": [
                    {"stage_index": 1, "stage_label": f"Scout the perimeter of {cur_short} for supply leads", "target_location": cur_loc, "completion_trigger": "arrival"},
                    {"stage_index": 2, "stage_label": f"Collect the Supply Crate at {sec_short}", "target_location": sec_loc, "completion_trigger": "skill_check"},
                ]
            },
            {
                "blueprint_id": "INVESTIGATION",
                "quest_type": "Perimeter Patrol",
                "title": "Perimeter Security Sweep",
                "objective": f"Conduct a reconnaissance sweep around {sec_prose} to assess recent disturbances.",
                "reward_xp": 130,
                "reward_gold": 40,
                "req_item": "",
                "stages": [
                    {"stage_index": 1, "stage_label": f"Patrol the boundaries of {cur_short}", "target_location": cur_loc, "completion_trigger": "arrival"},
                    {"stage_index": 2, "stage_label": f"Examine physical clues and inspect the perimeter at {sec_short}", "target_location": sec_loc, "completion_trigger": "skill_check"},
                ]
            },
            {
                "blueprint_id": "NEUTRALIZATION",
                "quest_type": "Bounty Hunting",
                "title": "Rogue Marauder Bounty",
                "objective": f"A hostile marauder is reported roaming near {ter_prose}. Track and subdue them.",
                "reward_xp": 150,
                "reward_gold": 45,
                "req_item": "",
                "stages": [
                    {"stage_index": 1, "stage_label": f"Track the marauder's trail from {cur_short}", "target_location": cur_loc, "completion_trigger": "arrival"},
                    {"stage_index": 2, "stage_label": f"Confront the marauder at {ter_short} and neutralize the threat", "target_location": ter_loc, "completion_trigger": "skill_check"},
                ]
            },
        ]

    from mechanics.world.waypoints import ensure_multi_stage_waypoints

    t_idx = 0
    while len(avail) < 3 and t_idx < len(fallback_templates):
        tmpl = fallback_templates[t_idx]
        t_idx += 1
        b_id = f"BNT-{uuid.uuid4().hex[:8].upper()}"
        client_name, client_loc = resolve_or_seed_bounty_client(
            session_id,
            session,
            {"quest_type": tmpl["quest_type"]},
            cur_loc,
            index=t_idx,
        )

        d_day, d_min = roll_quest_deadline(
            blueprint_id=tmpl["blueprint_id"],
            quest_type=tmpl["quest_type"],
            title=tmpl["title"],
            objective=tmpl["objective"],
            current_day=curr_day,
            current_minute=curr_min,
            is_story_quest=False,
            seed_str=b_id,
        )
        db.upsert_quest(
            session_id=session_id,
            quest_id=b_id,
            quest_type=tmpl["quest_type"],
            title=tmpl["title"],
            objective=tmpl["objective"],
            progress="0/1 In Progress",
            current_clues="",
            status="Available",
            reward_xp=tmpl["reward_xp"],
            reward_gold=tmpl["reward_gold"],
            quest_notes="board_source:freelance_app" if scenario_data.is_anomalous_incursions_scenario(scen_key) else "",
            blueprint_id=tmpl["blueprint_id"],
            client_npc=client_name,
            client_location=client_loc,
            required_item=tmpl["req_item"],
            required_item_count=1 if tmpl["req_item"] else 0,
            deadline_day=d_day,
            deadline_minute=d_min,
        )
        raw_wps = [dict(s) for s in tmpl["stages"]]
        wps = ensure_multi_stage_waypoints(
            raw_wps,
            default_loc=cur_loc,
            archetype=tmpl["quest_type"],
            session_id=session_id,
            scen_key=scen_key,
            secondary_loc=sec_loc,
            tertiary_loc=ter_loc,
            client_npc=client_name,
            client_location=client_loc,
            required_item=tmpl["req_item"],
        )
        if wps:
            db.save_quest_waypoints(session_id, b_id, wps, sub_obj_id=None)

        new_q = db.get_quest_by_id(session_id, b_id)
        if new_q:
            avail.append(new_q)

    return _filter_general_bounties(db.get_session_quests(session_id, status="Available"))


# -----------------------------------------------------------------------------
# Anomalous Incursions: Mandatory Daily Bounty, Eligibility Matrix & Loot Rules
# -----------------------------------------------------------------------------

def parse_anomalous_quest_board_source(quest: dict, session_id: int | None = None) -> str:
    """
    Infers the originating board/source of a quest in Anomalous Incursions:
    - `'story_quest'` for Main Story Quests (`is_story_quest == 1`)
    - `'public_agency'`, `'private_agency_1'`, `'private_agency_2'`, `'monastic_order'`,
      `'cult_faction'`, `'clandestine_faction'`, or `'freelance_app'`.
    """
    if not quest:
        return "freelance_app"
    if quest.get("is_story_quest") or quest.get("quest_type") in ("Story Quest", "Main Quest"):
        return "story_quest"

    notes = str(quest.get("quest_notes") or "")
    faction_id = ""
    for part in notes.replace("\n", "|").split("|"):
        p = part.strip()
        if p.startswith("board_source:"):
            return p.split(":", 1)[1].strip().lower()
        if p.startswith("faction:"):
            faction_id = p.split(":", 1)[1].strip()

    if faction_id and session_id:
        try:
            from mechanics.social.factions import infer_anomalous_faction_archetype
            fac = db.get_faction(session_id, faction_id)
            if fac:
                return infer_anomalous_faction_archetype(fac)
        except Exception:
            pass

    q_id = str(quest.get("quest_id") or "").upper()
    if q_id.startswith("MAND-"):
        if session_id:
            try:
                from mechanics.social.factions import get_anomalous_faction_state
                st = get_anomalous_faction_state(session_id)
                return str(st.get("faction_archetype_key") or "public_agency")
            except Exception:
                pass
        return "public_agency"
    return "freelance_app"


def dispatch_anomalous_mandatory_daily_bounty(
    session_id: int,
    current_day: int,
    faction_archetype_key: str,
    faction_name: str = "",
    scen_key: str = "anomalous_incursions",
) -> dict | None:
    """
    Automatically generates and inserts the player's Mandatory Daily Bounty (`status='Active'`)
    for `current_day` when affiliated with `public_agency`, `private_agency_1`, `private_agency_2`,
    or `monastic_order`. Freelancers (`freelancer`) receive no mandatory daily bounty.
    """
    if not scenario_data.is_anomalous_incursions_scenario(scen_key):
        return None
    arch = str(faction_archetype_key or "").strip().lower()
    if not arch or arch == "freelancer":
        return None

    day_num = max(1, int(current_day or 1))
    prefix = f"MAND-D{day_num}-"

    all_quests = db.get_session_quests(session_id) or []
    for q in all_quests:
        qid = str(q.get("quest_id") or "")
        if qid.startswith(prefix) and q.get("status") in ("Active", "Completed"):
            return {
                "quest_id": qid,
                "title": q.get("title", ""),
                "quest_type": q.get("quest_type", ""),
                "objective": q.get("objective", ""),
                "location": q.get("client_location", "") or "Metropolitan Grid",
                "deadline_day": day_num,
            }
        # Mark any uncompleted mandatory bounties from earlier days as Failed
        notes = str(q.get("quest_notes") or "")
        if ("mandatory_daily:1" in notes or qid.startswith("MAND-D")) and not qid.startswith(prefix) and q.get("status") == "Active":
            try:
                db.update_quest_status(session_id, qid, "Failed")
            except Exception:
                pass

    # Candidate city locations (outside safe Agency HQs / Player House, with consolidated complex wings expanded)
    candidate_locations = _collect_anomalous_bounty_candidate_locations(session_id, scen_key)
    if not candidate_locations:
        candidate_locations = ["Metropolitan Grid ➔ Central Transit Station", "Downtown Commercial District ➔ Neon Arcade Plaza"]

    import namegen
    from mechanics.narrative.blueprints import get_blueprint_for_archetype
    from mechanics.world.waypoints import ensure_multi_stage_waypoints
    from mechanics.social.factions import get_anomalous_faction_state, save_anomalous_faction_state

    preferred = ANOMALOUS_FACTION_BOARD_ARCHETYPE_WEIGHTS.get(arch, ANOMALOUS_FACTION_BOARD_ARCHETYPE_WEIGHTS["public_agency"])
    arch_by_label = {a["label"]: a for a in ANOMALOUS_BOUNTY_ARCHETYPES}
    seed_idx = int(session_id or 1) * 31 + day_num * 17
    chosen_label = preferred[seed_idx % len(preferred)]
    meta = arch_by_label.get(chosen_label, ANOMALOUS_BOUNTY_ARCHETYPES[0])

    from mechanics.world.locations import format_clean_location_prose
    target_loc = candidate_locations[seed_idx % len(candidate_locations)]
    sec_loc = candidate_locations[(seed_idx + 3) % len(candidate_locations)]
    target_prose = format_clean_location_prose(target_loc, include_zone=True, preposition="in")
    target_short = format_clean_location_prose(target_loc, include_zone=False)
    entity_name = namegen.generate_anomalous_entity_name(hash_val=seed_idx)

    fac_label = faction_name or "Command Dispatch"
    q_id = f"{prefix}{uuid.uuid4().hex[:6].upper()}"
    is_nh_mand = "non-hostile" in chosen_label.lower()
    nh_mand_temp = ""
    if is_nh_mand:
        from mechanics.world.anomalous_events import get_non_hostile_entity_temperament
        nh_mand_temp = get_non_hostile_entity_temperament(seed_key=q_id)
        mand_cue = (
            "Timid/elusive—startling risks escape."
            if nh_mand_temp == "timid"
            else "Volatile/territorial—provoking risks combat."
        )
        objective = (
            f"[MANDATORY DAILY DISPATCH — {fac_label}] Contain '{entity_name}' alive at {target_prose} before 24:00. {mand_cue}"
        )[:200]
    else:
        objective = (
            f"[MANDATORY DAILY DISPATCH — {fac_label}] {meta['default_objective']} "
            f"Respond to '{entity_name}' at {target_prose} before 24:00 today."
        )[:200]
    title = f"[Mandatory] {meta['title_prefix']}: {entity_name}"[:58]
    blueprint_id = get_blueprint_for_archetype(chosen_label, objective)
    req_item = meta.get("req_item", "")

    fac_state = get_anomalous_faction_state(session_id)
    fac_id = str(fac_state.get("joined_faction_id") or arch)
    q_notes = f"mandatory_daily:1|faction:{fac_id}|board_source:{arch}|rep_reward:15"
    if is_nh_mand:
        q_notes = f"{q_notes}|non_hostile_temperament:{nh_mand_temp}|entity_name:{entity_name}"

    # Base gold (confiscated automatically at claim time for Public Agency / Monastic Order)
    base_gold = 95 if arch in ("private_agency_1", "private_agency_2") else 75

    db.upsert_quest(
        session_id=session_id,
        quest_id=q_id,
        quest_type=chosen_label,
        title=title,
        objective=objective,
        progress=f"0/1 {req_item} Collected" if (blueprint_id == "ACQUISITION" and req_item) else "0/1 Target Sighted",
        current_clues="",
        status="Active",
        reward_xp=160,
        reward_gold=base_gold,
        reward_stat_points=0,
        reward_item="Trauma Medkit" if arch in ("private_agency_1", "private_agency_2", "monastic_order") else "",
        quest_notes=q_notes,
        blueprint_id=blueprint_id,
        client_npc=f"{fac_label} Dispatch Officer",
        client_location=target_loc,
        required_item=req_item,
        required_item_count=1 if req_item else 0,
        deadline_day=day_num,
        deadline_minute=1439,
    )

    stage_2_mand_lbl = (
        f"Encounter and contain non-hostile entity '{entity_name}' alive"
        if is_nh_mand
        else f"Resolve mandatory containment directive for '{entity_name}'"
    )
    raw_wps = [
        {"stage_index": 1, "stage_label": f"Deploy to {target_short} and verify anomaly readings", "target_location": target_loc, "completion_trigger": "arrival"},
        {"stage_index": 2, "stage_label": stage_2_mand_lbl, "target_location": sec_loc, "completion_trigger": "skill_check"},
    ]
    wps = ensure_multi_stage_waypoints(
        raw_wps,
        default_loc=target_loc,
        archetype=chosen_label,
        secondary_loc=sec_loc,
        session_id=session_id,
        scen_key=scen_key,
        client_npc=f"{fac_label} Dispatch Officer",
        client_location=target_loc,
        required_item=req_item,
    )
    if wps:
        db.save_quest_waypoints(session_id=session_id, quest_id=q_id, waypoints=wps, sub_obj_id=None)

    if fac_state:
        fac_state["mandatory_bounty_id"] = q_id
        fac_state["mandatory_bounty_completed_today"] = False
        fac_state["mandatory_bounty_penalized_today"] = False
        save_anomalous_faction_state(session_id, fac_state)

    return {
        "quest_id": q_id,
        "title": title,
        "quest_type": chosen_label,
        "objective": objective,
        "location": target_loc,
        "deadline_day": day_num,
    }


def evaluate_anomalous_bounty_eligibility(
    session_id: int,
    user_id: int | None,
    quest: dict,
) -> dict:
    """
    Evaluates whether the player's current Anomalous Incursions Faction Affiliation permits
    accepting `quest`, enforcing the strict Faction Bounty Eligibility Matrix:
    - `public_agency`: Public Agency + Smartphone Freelance App ONLY. Blocked from Private Agencies & Monastic Order.
    - `private_agency_1`: Own Private #1 + Public Agency (Contract Work) + Freelance App. Blocked from Rival Private #2 & Monastic Order.
    - `private_agency_2`: Own Private #2 + Public Agency (Contract Work) + Freelance App. Blocked from Rival Private #1 & Monastic Order.
    - `monastic_order`: Own Monastic Order + Public Agency (Contract Work) + Freelance App. Blocked from Private Agencies #1 & #2.
    - `freelancer`: Public Agency (Contract Work) + Freelance App. Blocked from internal Private Agency & Monastic Order boards.
    - All Operatives: Blocked from `cult_faction` and `clandestine_faction` boards.
    """
    from mechanics.social.factions import get_anomalous_faction_state

    fac_state = get_anomalous_faction_state(session_id, user_id=user_id)
    player_arch = str(fac_state.get("faction_archetype_key") or "public_agency")
    board_src = parse_anomalous_quest_board_source(quest, session_id=session_id)

    if board_src in ("cult_faction", "clandestine_faction"):
        return {
            "allowed": False,
            "player_faction": player_arch,
            "board_source": board_src,
            "is_contract_work": False,
            "reason": "Unlicensed occult cult and clandestine syndicate contracts are strictly off-limits.",
        }

    allowed_map: dict[str, set[str]] = {
        "public_agency": {"public_agency", "freelance_app", "story_quest"},
        "private_agency_1": {"private_agency_1", "public_agency", "freelance_app", "story_quest"},
        "private_agency_2": {"private_agency_2", "public_agency", "freelance_app", "story_quest"},
        "monastic_order": {"monastic_order", "public_agency", "freelance_app", "story_quest"},
        "freelancer": {"public_agency", "freelance_app", "story_quest"},
    }
    allowed_set = allowed_map.get(player_arch, {"public_agency", "freelance_app", "story_quest"})
    is_allowed = board_src in allowed_set
    is_contract = is_allowed and board_src == "public_agency" and player_arch != "public_agency"

    if is_allowed:
        return {
            "allowed": True,
            "player_faction": player_arch,
            "board_source": board_src,
            "is_contract_work": is_contract,
            "reason": "Contract work authorized." if is_contract else "Authorized.",
        }

    if player_arch == "public_agency":
        reason = "As a state-salaried Public Agency operative, jurisdiction law prohibits accepting bounties from Private Agencies or the Monastic Shrine Order (Freelance App commissions remain permitted)."
    elif player_arch in ("private_agency_1", "private_agency_2"):
        if board_src in ("private_agency_1", "private_agency_2"):
            reason = "Corporate non-compete clauses prohibit accepting bounties from a rival Private Agency!"
        else:
            reason = "Private Agency operatives are not permitted to accept internal Monastic Shrine Order rites."
    elif player_arch == "monastic_order":
        reason = "Monastic Shrine Order vows prohibit accepting commercial contracts from Private Agencies (Public Agency contract work & Freelance App commissions are permitted)."
    else:
        reason = "Independent Freelancers lack security clearance for internal Private Agency or Monastic Shrine boards (Public Agency contract work & Freelance App commissions are open)."

    return {
        "allowed": False,
        "player_faction": player_arch,
        "board_source": board_src,
        "is_contract_work": False,
        "reason": reason,
    }


def should_confiscate_anomalous_combat_loot(
    session_id: int,
    session: dict | None = None,
    user_id: int | None = None,
    defeated_enemies: list | None = None,
) -> bool:
    """
    Determines whether combat gold & fallen-anomaly loot must be confiscated under the
    Public Agency Taxpayer Mandate in Anomalous Incursions:
    - Returns `True` ONLY when:
      1. Scenario is `Anomalous Incursions` (or variant), AND
      2. Player belongs to `public_agency`, AND
      3. Combat is NOT a Daily Anomalous Incursion or Random Encounter, AND
      4. Player is engaged on an Active Public Agency Bounty (`board_source == 'public_agency'` or `mandatory_daily:1`)
         or Main Story Quest (`is_story_quest == 1`), rather than a Freelance App commission.
    - Private Agencies, Monastic Shrine Order, and Freelancers ALWAYS return `False` (keep 100% combat spoils).
    """
    if session is None and session_id:
        session = db.get_session(session_id) or {}
    elif session is None:
        session = {}

    scen_key = str(session.get("scenario") or "fantasy")
    if not scenario_data.is_anomalous_incursions_scenario(scen_key):
        return False

    from mechanics.social.factions import get_anomalous_faction_state
    fac_state = get_anomalous_faction_state(session_id, user_id=user_id)
    if str(fac_state.get("faction_archetype_key") or "") != "public_agency":
        return False

    # 1. Check if combat came from a Daily Incursion or Random Encounter (player keeps loot!)
    for e in (defeated_enemies or []):
        if isinstance(e, dict) and (e.get("incursion_id") or e.get("is_random_encounter")):
            return False
    try:
        from mechanics.world.anomalous_events import get_active_incursion_at_location
        if get_active_incursion_at_location(session_id, session.get("current_location", ""), session.get("current_node_id", "")):
            return False
    except Exception:
        pass

    # Explicit override flag on session if set
    explicit_src = str(session.get("_active_combat_quest_source") or "").strip().lower()
    if explicit_src == "freelance_app":
        return False
    if explicit_src in ("public_agency", "story_quest"):
        return True

    # 2. Inspect active quests and waypoints relative to current location
    active_quests = db.get_session_quests(session_id, status="Active") or []
    raw_cur_loc = str(session.get("current_location") or "")
    cur_loc = raw_cur_loc.lower()
    cur_leaf = cur_loc.split("➔")[-1].strip() if "➔" in cur_loc else cur_loc
    cur_primary = ""
    try:
        from mechanics.world.locations import parse_tiered_location
        _, p_loc, _ = parse_tiered_location(raw_cur_loc, scen_key, session_id=session_id)
        cur_primary = str(p_loc or "").strip().lower()
    except Exception:
        parts_loc = [p.strip() for p in cur_loc.split("➔") if p.strip()]
        if len(parts_loc) >= 2:
            cur_primary = parts_loc[1]

    has_matching_freelance = False
    has_matching_public_or_story = False
    has_any_public_or_story = False
    has_any_freelance = False

    for q in active_quests:
        src = parse_anomalous_quest_board_source(q, session_id=session_id)
        qid = q.get("quest_id", "")
        wps = db.get_quest_waypoints(session_id, qid) if qid else []
        wp_match = any(
            (cur_primary and cur_primary in str(wp.get("target_location") or "").lower())
            or (cur_leaf and cur_leaf in str(wp.get("target_location") or "").lower())
            for wp in (wps or [])
        )
        if src == "freelance_app":
            has_any_freelance = True
            if wp_match:
                has_matching_freelance = True
        elif src in ("public_agency", "story_quest"):
            has_any_public_or_story = True
            if wp_match:
                has_matching_public_or_story = True

    if has_matching_freelance and not has_matching_public_or_story:
        return False
    if has_matching_public_or_story:
        return True
    if has_any_freelance and not has_any_public_or_story:
        return False
    return has_any_public_or_story



