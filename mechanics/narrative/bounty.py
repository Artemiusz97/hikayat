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
    ]
}

# --------------------------------------------------------------------- Discord Quest Log Icon Mappings
QUEST_TYPE_ICONS = {
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
    from scenario_data import has_tag
    from mechanics.world.locations.seeds import is_school_scenario
    archetypes = []

    # 1. Primary Scenario Archetypes (highest priority)
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
    default_loc: str = "the central area",
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

    client_loc = str(raw_bounty.get("client_location", "") or default_loc or "").strip()

    if client_npc:
        return client_npc, client_loc

    from mechanics.world.locations.seeds import is_school_scenario
    if is_school_scenario(scen_key) and session:
        try:
            from mechanics.social.school_roster import ensure_school_directory_exists
            roster = ensure_school_directory_exists(session)
            if roster:
                chosen = roster[(session_id + index) % len(roster)]
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


BOUNTY_BOARD_SYSTEM_PROMPT = build_bounty_system_prompt()


async def generate_bounty_board(session: dict | int, force_refresh: bool = False) -> list[dict]:
    """Generates 3 dynamic bounty board postings for a session using LLM JSON completion."""
    from game_engine import _scenario_block, is_nsfw_scenario
    if isinstance(session, (int, str)):
        session_id = int(session)
        session = db.get_session(session_id) or {"id": session_id}
    else:
        session_id = session["id"]
    if not force_refresh:
        existing = db.get_session_quests(session_id, status="Available")
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

    user_prompt = (
        f"{scen_block}\n"
        f"Location: {loc}\n"
        f"{school_hints}\n"
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
        if is_school_scenario(scen_key):
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

    for idx, b in enumerate(bounties_raw):
        if not isinstance(b, dict) or not b.get("title"):
            continue
        b_id = f"BNT-{uuid.uuid4().hex[:8].upper()}"
        q_type = str(b.get("quest_type", "Side Bounty"))
        obj_text = str(b.get("objective", "Complete the bounty task."))[:200]
        title_text = str(b.get("title"))[:60]

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
            from mechanics.world.locations import parse_tiered_location
            for wp in validated_wps:
                raw_tgt = wp.get("target_location", "")
                if raw_tgt:
                    z_norm, p_norm, _ = parse_tiered_location(raw_tgt, scen_key, session_id=session_id)
                    wp["target_location"] = f"{z_norm} ➔ {p_norm}"
            db.save_quest_waypoints(session_id=session_id, quest_id=b_id, waypoints=validated_wps, sub_obj_id=None)

    return db.get_session_quests(session_id, status="Available")


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

    user_prompt = (
        f"{scen_block}\n"
        f"Faction: {faction_name} (Category: {faction.get('category', 'guild')})\n"
        f"Faction HQ: {loc}\n"
        f"Faction Reputation: {faction.get('reputation_score', 0):+d}\n\n"
        f"Generate 3 exclusive faction bounties for the {faction_name} notice board.\n"
        f"Respond with JSON matching exactly this schema:\n{FACTION_BOUNTY_SCHEMA}"
    )

    _is_llm_mocked = hasattr(call_llm_json, "_mock_name")
    if _is_llm_mocked:
        result = await call_llm_json(FACTION_BOUNTY_SYSTEM_PROMPT, user_prompt, temperature=0.8,
                                      is_nsfw=scenario_data.uses_nsfw_model(scen_key), use_utility=True)
        bounties_raw = result.get("bounties", []) or []
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
                    {"stage_index": 1, "stage_label": f"Deliver supplies to {loc}", "target_location": loc, "completion_trigger": "arrival"}
                ]
            },
            {
                "quest_type": "Faction Subterfuge",
                "title": f"Intelligence Gathering for {faction_name}",
                "objective": f"Investigate rival movements near {loc}.",
                "client_npc": f"{faction_name} Spymaster",
                "client_location": loc,
                "reward_xp": 150,
                "reward_gold": 50,
                "reward_item": "Ciphered Scroll",
                "faction_rep_reward": 15,
                "waypoints": [
                    {"stage_index": 1, "stage_label": f"Scout area near {loc}", "target_location": loc, "completion_trigger": "arrival"}
                ]
            }
        ]

    for idx, b in enumerate(bounties_raw):
        if not isinstance(b, dict) or not b.get("title"):
            continue
        b_id = f"FBNT-{uuid.uuid4().hex[:8].upper()}"
        q_type = str(b.get("quest_type", "Faction Bounty"))
        obj_text = str(b.get("objective", "Complete the faction task."))[:200]
        title_text = str(b.get("title"))[:60]
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
            quest_notes=f"faction:{faction_id}|rep_reward:{faction_rep_reward}",
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
            from mechanics.world.locations import parse_tiered_location
            for wp in validated_wps:
                raw_tgt = wp.get("target_location", "")
                if raw_tgt:
                    z_norm, p_norm, _ = parse_tiered_location(raw_tgt, scen_key, session_id=session_id)
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
    cur_loc = session.get("current_location") or "the central area"

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
    from mechanics.world.locations import get_discovered_primary_locations
    zones_dict = get_discovered_primary_locations(session_id, scen_key) or {}
    discovered_locs = [f"{z} ➔ {p}" for z, prims in zones_dict.items() for p in prims] if isinstance(zones_dict, dict) else list(zones_dict)
    alt_locs = [dl for dl in discovered_locs if dl.strip().lower() != cur_loc.strip().lower()]
    sec_loc = alt_locs[0] if alt_locs else cur_loc
    ter_loc = alt_locs[1] if len(alt_locs) >= 2 else sec_loc

    raw_wps = [
        {"stage_index": 1, "stage_label": f"Investigate rumors of {new_target} at {cur_loc}", "target_location": cur_loc, "completion_trigger": "arrival"},
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
    cur_loc = session.get("current_location") or "the central area"

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
    from mechanics.world.locations import get_discovered_primary_locations
    zones_dict = get_discovered_primary_locations(session_id, scen_key) or {}
    discovered_locs = [f"{z} ➔ {p}" for z, prims in zones_dict.items() for p in prims] if isinstance(zones_dict, dict) else list(zones_dict)
    alt_locs = [dl for dl in discovered_locs if dl.strip().lower() != c_loc.strip().lower()]
    sec_loc = alt_locs[0] if alt_locs else c_loc
    ter_loc = alt_locs[1] if len(alt_locs) >= 2 else sec_loc

    raw_wps = [
        {"stage_index": 1, "stage_label": f"Meet with {c_name} at {c_loc} to discuss the matter", "target_location": c_loc, "target_npc": c_name, "completion_trigger": "arrival"},
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
    cur_loc = session.get("current_location") or "the central area"

    avail = db.get_session_quests(session_id, status="Available") or []
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

    fallback_templates = [
        {
            "blueprint_id": "ACQUISITION",
            "quest_type": "Resource Scavenge",
            "title": "Stockpile Scavenge",
            "objective": f"Gather vital supplies and materials from {sec_loc} for the local guild stockpile.",
            "reward_xp": 120,
            "reward_gold": 35,
            "req_item": "Supply Crate",
            "stages": [
                {"stage_index": 1, "stage_label": f"Scout the perimeter of {cur_loc} for supply leads", "target_location": cur_loc, "completion_trigger": "arrival"},
                {"stage_index": 2, "stage_label": f"Collect the Supply Crate at {sec_loc}", "target_location": sec_loc, "completion_trigger": "skill_check"},
            ]
        },
        {
            "blueprint_id": "INVESTIGATION",
            "quest_type": "Perimeter Patrol",
            "title": "Perimeter Security Sweep",
            "objective": f"Conduct a reconnaissance sweep around {sec_loc} to assess recent disturbances.",
            "reward_xp": 130,
            "reward_gold": 40,
            "req_item": "",
            "stages": [
                {"stage_index": 1, "stage_label": f"Patrol the boundaries of {cur_loc}", "target_location": cur_loc, "completion_trigger": "arrival"},
                {"stage_index": 2, "stage_label": f"Examine physical clues and inspect the perimeter at {sec_loc}", "target_location": sec_loc, "completion_trigger": "skill_check"},
            ]
        },
        {
            "blueprint_id": "NEUTRALIZATION",
            "quest_type": "Bounty Hunting",
            "title": "Rogue Marauder Bounty",
            "objective": f"A hostile marauder is reported roaming near {ter_loc}. Track and subdue them.",
            "reward_xp": 150,
            "reward_gold": 45,
            "req_item": "",
            "stages": [
                {"stage_index": 1, "stage_label": f"Track the marauder's trail from {cur_loc}", "target_location": cur_loc, "completion_trigger": "arrival"},
                {"stage_index": 2, "stage_label": f"Confront the marauder at {ter_loc} and neutralize the threat", "target_location": ter_loc, "completion_trigger": "skill_check"},
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

    return db.get_session_quests(session_id, status="Available")


