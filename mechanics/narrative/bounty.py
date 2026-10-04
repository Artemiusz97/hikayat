"""
Hikayat - Bounty Board & Quest Archetypes Mechanics
Modular mechanic handling quest archetype taxonomies, icon mappings, bounty prompt schemas, and dynamic bounty generation.
"""

import logging
import uuid
import db
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
        f"Include reward_xp (100-300), reward_gold (20-150), and optional reward_item (equipment/weapons/consumables).\n"
        f"IMPORTANT: Each bounty MUST include a `waypoints` array (2-3 progressive stages) that tell the player WHERE to travel.\n"
        f"  - MULTI-LOCATION PROGRESSION: Bounties (especially delivery, secret admirer, courier, matchmaking, academic rescue, escort, infiltration) can and SHOULD span 2 or 3 distinct locations across their stages!\n"
        f"  - Stage 1: Meet the quest-giver/client at their starting location (Location A) to receive the task/item (`completion_trigger: 'arrival'` or `'skill_check'`, specify `target_npc`).\n"
        f"  - Stage 2: Travel to the target destination (Location B) to deliver the item, confront the target, investigate, or tutor (`completion_trigger: 'skill_check'`).\n"
        f"  - Stage 3: Return to the quest-giver at Location A or finalize at Location B/C to confirm completion (`completion_trigger: 'skill_check'`).\n"
        f"  - target_location MUST use 'Zone -> Primary Place' format matching the session's world.\n"
        f"Respond with ONLY a single valid JSON object matching the schema exactly, no prose or code fences."
    )


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


async def generate_bounty_board(session: dict, force_refresh: bool = False) -> list[dict]:
    """Generates 3 dynamic bounty board postings for a session using LLM JSON completion."""
    from game_engine import _scenario_block, is_nsfw_scenario
    session_id = session["id"]
    if not force_refresh:
        existing = db.get_session_quests(session_id, status="Available")
        if len(existing) >= 3:
            return existing
    else:
        # Clear stale unaccepted general bounties upon refresh so new ones replace them cleanly
        with db.get_conn() as conn:
            conn.execute(
                "DELETE FROM quests WHERE session_id=? AND status='Available' AND (quest_id LIKE 'BNT-%' OR quest_notes IS NULL OR quest_notes NOT LIKE 'faction:%')",
                (session_id,)
            )
            conn.commit()

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

    result = await call_llm_json(system_prompt, user_prompt, temperature=0.8,
                                  is_nsfw=is_nsfw_scenario(scen_key), use_utility=True)
    bounties_raw = result.get("bounties", []) or []

    for b in bounties_raw:
        if not isinstance(b, dict) or not b.get("title"):
            continue
        b_id = f"BNT-{uuid.uuid4().hex[:8].upper()}"
        db.upsert_quest(
            session_id=session_id,
            quest_id=b_id,
            quest_type=str(b.get("quest_type", "Side Bounty")),
            title=str(b.get("title"))[:60],
            objective=str(b.get("objective", "Complete the bounty task."))[:200],
            progress="0/1 Target Sighted",
            current_clues="",
            status="Available",
            reward_xp=int(b.get("reward_xp", 120)),
            reward_gold=int(b.get("reward_gold", 35)),
            reward_stat_points=0,
            reward_item=str(b.get("reward_item", "") or "")[:60],
        )

        # Persist waypoints for this bounty
        from mechanics.world.waypoints import ensure_multi_stage_waypoints
        raw_waypoints = b.get("waypoints") or []
        sec_loc = candidate_locations[1] if len(candidate_locations) > 1 else ""
        tert_loc = candidate_locations[2] if len(candidate_locations) > 2 else ""
        validated_wps = ensure_multi_stage_waypoints(
            raw_waypoints,
            default_loc=loc,
            archetype=b.get("quest_type", "default"),
            secondary_loc=sec_loc,
            tertiary_loc=tert_loc
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
    "Each bounty MUST include a `faction_rep_reward` integer (5-20) in addition to gold/XP.\n"
    "Include a `waypoints` array (2-3 stages) with 'Zone -> Primary Place' target_location.\n"
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

    result = await call_llm_json(FACTION_BOUNTY_SYSTEM_PROMPT, user_prompt, temperature=0.8,
                                  is_nsfw=is_nsfw_scenario(scen_key), use_utility=True)
    bounties_raw = result.get("bounties", []) or []

    for b in bounties_raw:
        if not isinstance(b, dict) or not b.get("title"):
            continue
        b_id = f"FBNT-{uuid.uuid4().hex[:8].upper()}"
        faction_rep_reward = max(5, min(20, int(b.get("faction_rep_reward", 10))))
        db.upsert_quest(
            session_id=session_id,
            quest_id=b_id,
            quest_type=str(b.get("quest_type", "Faction Bounty")),
            title=str(b.get("title"))[:60],
            objective=str(b.get("objective", "Complete the faction task."))[:200],
            progress="0/1 Target Sighted",
            current_clues="",
            status="Available",
            reward_xp=max(60, min(250, int(b.get("reward_xp", 120)))),
            reward_gold=max(5, min(120, int(b.get("reward_gold", 30)))),
            reward_stat_points=0,
            reward_item=str(b.get("reward_item", "") or "")[:60],
            quest_notes=f"faction:{faction_id}|rep_reward:{faction_rep_reward}",
        )
        from mechanics.world.waypoints import ensure_multi_stage_waypoints
        raw_waypoints = b.get("waypoints") or []
        validated_wps = ensure_multi_stage_waypoints(
            raw_waypoints,
            default_loc=loc,
            archetype=b.get("quest_type", "default")
        )
        if validated_wps:
            from mechanics.world.locations import parse_tiered_location
            for wp in validated_wps:
                raw_tgt = wp.get("target_location", "")
                if raw_tgt:
                    z_norm, p_norm, _ = parse_tiered_location(raw_tgt, scen_key, session_id=session_id)
                    wp["target_location"] = f"{z_norm} -> {p_norm}"
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

