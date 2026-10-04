from __future__ import annotations
"""
Modular Factions & Reputation Engine for Hikayat.

Handles -100 to +100 faction reputation tracking, tier lookups, social skill check modifiers,
symbiotic contact score integration, LLM prompt context formatting, procedural leadership
roster generation, promotion trial directives, and NPC affiliation probability by scenario.
"""
import random
import re
from typing import Dict, Any, List, Optional
from mechanics.world.locations.seeds import is_school_scenario

MIN_REPUTATION = -100
MAX_REPUTATION = 100

# ---------------------------------------------------------------- Reputation Tier Ladder
FACTION_TIERS: List[Dict[str, Any]] = [
    {"min": 81,  "max": 100, "name": "Exalted",      "tier_level":  5, "modifier":  2, "discount_pct": 15},
    {"min": 51,  "max":  80, "name": "Honored",      "tier_level":  4, "modifier":  2, "discount_pct": 10},
    {"min": 21,  "max":  50, "name": "Friendly",     "tier_level":  3, "modifier":  1, "discount_pct":  5},
    {"min":  1,  "max":  20, "name": "Liked",        "tier_level":  2, "modifier":  1, "discount_pct":  0},
    {"min": -10, "max":   0, "name": "Neutral",      "tier_level":  0, "modifier":  0, "discount_pct":  0},
    {"min": -30, "max": -11, "name": "Distrusted",   "tier_level": -1, "modifier": -1, "discount_pct":  0},
    {"min": -60, "max": -31, "name": "Adversary",    "tier_level": -2, "modifier": -1, "discount_pct":  0},
    {"min": -85, "max": -61, "name": "Hostile",      "tier_level": -3, "modifier": -2, "discount_pct":  0},
    {"min": -100,"max": -86, "name": "Hated Enemy",  "tier_level": -4, "modifier": -3, "discount_pct":  0},
]


def get_faction_tier(score: int) -> Dict[str, Any]:
    score = max(MIN_REPUTATION, min(MAX_REPUTATION, score))
    for t in FACTION_TIERS:
        if t["min"] <= score <= t["max"]:
            return t
    return FACTION_TIERS[4]  # Neutral fallback


def get_faction_modifier(score: int) -> int:
    return get_faction_tier(score)["modifier"]


def get_faction_discount(score: int) -> int:
    return get_faction_tier(score)["discount_pct"]


# ---------------------------------------------------------------- Rank Hierarchy Templates
FACTION_HIERARCHIES: Dict[str, List[Dict[str, Any]]] = {
    "council": [
        {"rank": 1, "title": "Council Representative",        "required_rep": 1,  "is_leader": False},
        {"rank": 2, "title": "Council Secretary",             "required_rep": 30, "is_leader": False},
        {"rank": 3, "title": "Student Council Vice President", "required_rep": 60, "is_leader": False},
        {"rank": 4, "title": "Student Council President",      "required_rep": 85, "is_leader": True},
    ],
    "discipline": [
        {"rank": 1, "title": "Disciplinary Liaison",          "required_rep": 1,  "is_leader": False},
        {"rank": 2, "title": "Discipline Officer",            "required_rep": 30, "is_leader": False},
        {"rank": 3, "title": "Committee Captain",             "required_rep": 60, "is_leader": False},
        {"rank": 4, "title": "Disciplinary Committee Head",   "required_rep": 85, "is_leader": True},
    ],
    "club": [
        {"rank": 1, "title": "Club Treasurer",                "required_rep": 1,  "is_leader": False},
        {"rank": 2, "title": "Club Secretary",                "required_rep": 30, "is_leader": False},
        {"rank": 3, "title": "Vice President",                "required_rep": 60, "is_leader": False},
        {"rank": 4, "title": "Club President",                "required_rep": 85, "is_leader": True},
    ],
    "delinquents": [
        {"rank": 1, "title": "Vanguard Captain",              "required_rep": 1,  "is_leader": False},
        {"rank": 2, "title": "Lead Enforcer",                 "required_rep": 30, "is_leader": False},
        {"rank": 3, "title": "Lieutenant",                    "required_rep": 60, "is_leader": False},
        {"rank": 4, "title": "Gang Boss",                     "required_rep": 85, "is_leader": True},
    ],
    "guild": [
        {"rank": 1, "title": "Field Captain",                 "required_rep": 1,  "is_leader": False},
        {"rank": 2, "title": "Guild Overseer",                "required_rep": 30, "is_leader": False},
        {"rank": 3, "title": "Senior Council Veteran",        "required_rep": 60, "is_leader": False},
        {"rank": 4, "title": "Guildmaster",                   "required_rep": 85, "is_leader": True},
    ],
    "order": [
        {"rank": 1, "title": "Knight Captain",                "required_rep": 1,  "is_leader": False},
        {"rank": 2, "title": "Knight Commander",              "required_rep": 30, "is_leader": False},
        {"rank": 3, "title": "High Paladin",                  "required_rep": 60, "is_leader": False},
        {"rank": 4, "title": "Grand Master",                  "required_rep": 85, "is_leader": True},
    ],
    "corpo": [
        {"rank": 1, "title": "Lead Project Coordinator",      "required_rep": 1,  "is_leader": False},
        {"rank": 2, "title": "Operations Manager",            "required_rep": 30, "is_leader": False},
        {"rank": 3, "title": "Senior Director",               "required_rep": 60, "is_leader": False},
        {"rank": 4, "title": "Division Executive",            "required_rep": 85, "is_leader": True},
    ],
    "syndicate": [
        {"rank": 1, "title": "Field Coordinator",             "required_rep": 1,  "is_leader": False},
        {"rank": 2, "title": "Lead Operative",                "required_rep": 30, "is_leader": False},
        {"rank": 3, "title": "Handler",                       "required_rep": 60, "is_leader": False},
        {"rank": 4, "title": "Syndicate Boss",                "required_rep": 85, "is_leader": True},
    ],
    "settlement": [
        {"rank": 1, "title": "Defense Warden",                "required_rep": 1,  "is_leader": False},
        {"rank": 2, "title": "Watch Captain",                 "required_rep": 30, "is_leader": False},
        {"rank": 3, "title": "Quartermaster",                 "required_rep": 60, "is_leader": False},
        {"rank": 4, "title": "Council Leader",                "required_rep": 85, "is_leader": True},
    ],
    "alchemy": [
        {"rank": 1, "title": "Apprentice Alchemist",          "required_rep": 1,  "is_leader": False},
        {"rank": 2, "title": "Journeyman Brewer",             "required_rep": 30, "is_leader": False},
        {"rank": 3, "title": "Master Alchemist",              "required_rep": 60, "is_leader": False},
        {"rank": 4, "title": "Grand Alchemical Magister",     "required_rep": 85, "is_leader": True},
    ],
    "academy": [
        {"rank": 1, "title": "Apprentice Scholar",            "required_rep": 1,  "is_leader": False},
        {"rank": 2, "title": "Journeyman Researcher",         "required_rep": 30, "is_leader": False},
        {"rank": 3, "title": "Senior Fellow",                 "required_rep": 60, "is_leader": False},
        {"rank": 4, "title": "Grand Rector",                  "required_rep": 85, "is_leader": True},
    ],
    "union": [
        {"rank": 1, "title": "Apprentice Machinist",          "required_rep": 1,  "is_leader": False},
        {"rank": 2, "title": "Shop Steward",                  "required_rep": 30, "is_leader": False},
        {"rank": 3, "title": "Chief Engineer",                "required_rep": 60, "is_leader": False},
        {"rank": 4, "title": "Union President",               "required_rep": 85, "is_leader": True},
    ],
    "fleet": [
        {"rank": 1, "title": "Flight Ensign",                 "required_rep": 1,  "is_leader": False},
        {"rank": 2, "title": "Lieutenant Commander",          "required_rep": 30, "is_leader": False},
        {"rank": 3, "title": "Airship Captain",               "required_rep": 60, "is_leader": False},
        {"rank": 4, "title": "Lord Admiral",                  "required_rep": 85, "is_leader": True},
    ],
    "merchant": [
        {"rank": 1, "title": "Caravan Agent",                 "required_rep": 1,  "is_leader": False},
        {"rank": 2, "title": "Trade Factor",                  "required_rep": 30, "is_leader": False},
        {"rank": 3, "title": "High Burgher",                  "required_rep": 60, "is_leader": False},
        {"rank": 4, "title": "Merchant Prince",               "required_rep": 85, "is_leader": True},
    ],
    "inquisition": [
        {"rank": 1, "title": "Initiate Inquisitor",           "required_rep": 1,  "is_leader": False},
        {"rank": 2, "title": "Witch Hunter",                  "required_rep": 30, "is_leader": False},
        {"rank": 3, "title": "High Inquisitor",               "required_rep": 60, "is_leader": False},
        {"rank": 4, "title": "Grand Inquisitor",              "required_rep": 85, "is_leader": True},
    ],
    "cult": [
        {"rank": 1, "title": "Acolyte",                       "required_rep": 1,  "is_leader": False},
        {"rank": 2, "title": "Adept",                         "required_rep": 30, "is_leader": False},
        {"rank": 3, "title": "Hierophant",                    "required_rep": 60, "is_leader": False},
        {"rank": 4, "title": "Cult Archon",                   "required_rep": 85, "is_leader": True},
    ],
    "scavenger": [
        {"rank": 1, "title": "Scrap Runner",                  "required_rep": 1,  "is_leader": False},
        {"rank": 2, "title": "Salvage Specialist",            "required_rep": 30, "is_leader": False},
        {"rank": 3, "title": "Wreckmaster",                   "required_rep": 60, "is_leader": False},
        {"rank": 4, "title": "Scrap Baron",                   "required_rep": 85, "is_leader": True},
    ],
    "default": [
        {"rank": 1, "title": "Chief Coordinator",             "required_rep": 1,  "is_leader": False},
        {"rank": 2, "title": "Executive Officer",             "required_rep": 30, "is_leader": False},
        {"rank": 3, "title": "Vice Director",                 "required_rep": 60, "is_leader": False},
        {"rank": 4, "title": "Director",                      "required_rep": 85, "is_leader": True},
    ],
}


def get_hierarchy(template: str) -> List[Dict[str, Any]]:
    """Return hierarchy tiers for the given template key, falling back to 'default'."""
    return FACTION_HIERARCHIES.get(template or "default", FACTION_HIERARCHIES["default"])


def get_rank_title(template: str, rank: int) -> str:
    """Return the title string for a given rank number in a hierarchy template."""
    for tier in get_hierarchy(template):
        if tier["rank"] == rank:
            return tier["title"]
    return "Chief Coordinator"


def get_eligible_rank(template: str, reputation_score: int) -> int:
    """Return the highest rank the player is eligible for based on reputation (ignoring membership)."""
    eligible = 0
    for tier in get_hierarchy(template):
        if reputation_score >= tier["required_rep"]:
            eligible = tier["rank"]
    return eligible


def guess_hierarchy_template(faction_name: str, scen_key: str = "") -> str:
    """Heuristically infer the best hierarchy template from faction name and scenario."""
    name_lower = (faction_name or "").lower()
    from scenario_data import has_tag

    # 1. School scenarios prioritize school club / student council structures
    if is_school_scenario(scen_key):
        if any(k in name_lower for k in ("council", "student council", "stuco", "student gov", "senate", "presidency")):
            return "council"
        if any(k in name_lower for k in ("disciplin", "disciplinary", "prefect", "monitor", "morals", "public safety")):
            return "discipline"
        delinquent_keywords = ("gang", "delinquent", "rebel", "rough", "biker", "street", "crew", "yanki", "hoodlum", "thug", "stormborn", "skulls", "brawler", "viper", "wolves")
        if any(k in name_lower for k in delinquent_keywords):
            return "delinquents"
        return "club"

    # 2. Specialized archetype keyword routing across all scenarios
    # Dedicated Alchemy / Apothecary
    alchemy_keywords = ("alchem", "apothecary", "distill", "potion", "transmutation", "philosopher", "elixir", "brewery", "herbalist", "crucible")
    if any(k in name_lower for k in alchemy_keywords):
        return "alchemy"

    # Dedicated Academy / Research Society
    academy_keywords = ("academy", "institute", "university", "research", "scholars", "conservatory", "faculty")
    if any(k in name_lower for k in academy_keywords):
        return "academy"

    # Inquisition / Witch Hunters
    inquisition_keywords = ("inquisit", "witch hunter", "witch-hunter", "purifier", "heretic hunter", "witch hunters", "witch-hunters", "purifiers")
    if any(k in name_lower for k in inquisition_keywords):
        return "inquisition"

    # Occult Cults / Eldritch Covens (check whole-word 'cult' to avoid substring matches in 'occult')
    cult_keywords = ("coven", "blood pact", "necroman", "eldritch", "harbinger", "dark ritual", "defilers", "blasphem", "occult pact")
    if re.search(r'\bcults?\b', name_lower) or any(k in name_lower for k in cult_keywords):
        return "cult"

    # Fleets / Aeronauts / Navies (airships, starships, naval flotillas)
    fleet_keywords = ("fleet", "navy", "aeronaut", "dirigible", "airship", "starship", "flotilla", "armada", "sky fleet", "orbital fleet", "corsair fleet", "navigators guild")
    if any(k in name_lower for k in fleet_keywords):
        return "fleet"

    # Merchant & Trade Consortiums
    merchant_keywords = ("merchant", "trading post", "caravan", "trade company", "trade league", "consortium", "bourse", "banking house", "commercial league", "trade guild", "coin league")
    if any(k in name_lower for k in merchant_keywords):
        return "merchant"

    # Industrial Labor Unions / Boilermakers / Machinists
    union_keywords = ("labor union", "trade union", "smelters", "steamfitter", "boilermaker", "machinist", "foundry worker", "metalworker", "miners union", "workers union", "industrial league", "locomotive union")
    if any(k in name_lower for k in union_keywords) or (("union" in name_lower or "league" in name_lower) and has_tag(scen_key, "steampunk")):
        return "union"

    # Scavengers & Wasteland Salvage
    scavenger_keywords = ("scavenger", "salvage", "scrapper", "junkers", "scrap crew", "waste reclaimers", "prospector", "rig miners")
    if any(k in name_lower for k in scavenger_keywords) or (any(k in name_lower for k in ("scrap", "junk", "salvage")) and has_tag(scen_key, "post_apocalypse")):
        return "scavenger"

    # 3. Scenario-specific archetype detection
    if has_tag(scen_key, "cyberpunk") or has_tag(scen_key, "space") or has_tag(scen_key, "sci_fi") or "cyber" in (scen_key or "").lower() or "sci_fi" in (scen_key or "").lower() or "space" in (scen_key or "").lower():
        corpo_keywords = ("corp", "corporation", "megacorp", "company", "industries", "security", "agency", "board", "technolog", "dynamics", "systems", "biotech")
        if any(k in name_lower for k in corpo_keywords):
            return "corpo"
        gang_keywords = ("gang", "reapers", "claws", "punks", "skulls", "rats", "brawlers", "vipers")
        if any(k in name_lower for k in gang_keywords):
            return "delinquents"

    if has_tag(scen_key, "post_apocalypse") or "apocalypse" in (scen_key or "").lower():
        if any(k in name_lower for k in ("raider", "gang", "marauder", "vulture", "hound", "warband")):
            return "delinquents"
        if any(k in name_lower for k in ("settlement", "haven", "bastion", "sanctuary", "vault", "council", "refuge", "colony")):
            return "settlement"

    # 4. General keyword checks
    if any(k in name_lower for k in ("student council", "stuco", "school council", "council")):
        return "council"
    if any(k in name_lower for k in ("discipline committee", "prefect committee", "disciplinary")):
        return "discipline"
    if any(k in name_lower for k in ("club", "student club", "society", "pact", "circle", "lovers")):
        return "club"
    if any(k in name_lower for k in ("corpo", "corporation", "megacorp")):
        return "corpo"
    if any(k in name_lower for k in ("syndicate", "mafia", "yakuza", "triad", "cartel", "union", "league")):
        return "syndicate"
    if any(k in name_lower for k in ("gang", "delinquent", "marauder", "brawlers", "ruffians")):
        return "delinquents"
    order_keywords = ("order", "brotherhood", "sisterhood", "temple", "church", "covenant", "inquisition", "knights", "paladin", "conclave", "archmages")
    if any(k in name_lower for k in order_keywords):
        return "order"

    # 5. Scenario fallbacks
    if has_tag(scen_key, "cyberpunk") or has_tag(scen_key, "space") or has_tag(scen_key, "sci_fi") or "cyber" in (scen_key or "").lower() or "sci_fi" in (scen_key or "").lower() or "space" in (scen_key or "").lower():
        return "syndicate"
    if has_tag(scen_key, "post_apocalypse") or "apocalypse" in (scen_key or "").lower():
        return "settlement"

    return "guild"


def infer_default_hq_location(faction_name: str, scen_key: str = "") -> str:
    """Infers an evocative default Headquarters location for a newly discovered faction."""
    from scenario_data import has_tag
    name_l = (faction_name or "").lower()

    # 1. First, inspect scenario seed data for matching primary locations (e.g. Alchemists' Guild -> Alchemists' Guild Hall)
    try:
        from mechanics.world.locations.seeds import get_scenario_seed_data
        seed_data = get_scenario_seed_data(scen_key)
        tokens = [w for w in re.split(r"\W+", name_l) if len(w) >= 4 and w not in ("guild", "hall", "order", "club", "association", "fellowship", "society")]
        for zone in seed_data.get("zones", []):
            for prim in zone.get("primary_locations", []):
                prim_name = prim.get("name", "")
                prim_low = prim_name.lower()
                if name_l in prim_low or prim_low in name_l:
                    return prim_name
                if tokens and all(t in prim_low for t in tokens):
                    return prim_name
    except Exception:
        pass
    
    if is_school_scenario(scen_key):
        if any(k in name_l for k in ("esport", "gaming", "game", "video game")): return "Esports Clubroom & Media Lab"
        if any(k in name_l for k in ("science", "robotics", "tech", "computer", "biology", "chemistry")): return "Science & Robotics Lab 2-A"
        if any(k in name_l for k in ("kendo", "martial", "judo", "karate", "budo", "boxing", "fencing", "wrestling")): return "Traditional Martial Arts Dojo"
        if re.search(r'\b(art|arts|manga|anime|drawing|painting|sculpture)\b', name_l): return "Art & Design Studio"
        if any(k in name_l for k in ("journalism", "newspaper", "press", "media")): return "Newspaper & Media Room"
        if any(k in name_l for k in ("music", "band", "orchestra", "choir", "vocal")): return "Music Wing Rehearsal Hall"
        if any(k in name_l for k in ("cooking", "culinary", "baking", "food")): return "Home Economics & Culinary Kitchen"
        if any(k in name_l for k in ("astronomy", "stargazing", "space")): return "Rooftop Astronomy Dome"
        if any(k in name_l for k in ("literature", "book", "reading", "poetry", "library")): return "Library Annex Reading Room"
        if any(k in name_l for k in ("swim", "aquatic", "water polo")): return "Indoor Aquatics Center"
        if any(k in name_l for k in ("track", "athletic", "field", "runner")): return "Athletics Pavilion & Track"
        if any(k in name_l for k in ("council", "stuco")): return "Student Council Office"
        if any(k in name_l for k in ("drama", "theater", "acting")): return "School Auditorium Stage"
        if any(k in name_l for k in ("occult", "mystery", "paranormal")): return "Old Storage Room 3-B"
        if any(k in name_l for k in ("gang", "delinquent", "rebel", "brawler", "skulls", "wolves")): return "Behind Gym Storage Sheds"
        return f"{faction_name.strip()} Clubroom"

    if has_tag(scen_key, "cyberpunk"):
        if any(k in name_l for k in ("corp", "industries", "systems", "biotech")): return f"{faction_name.strip()} Corporate Plaza Tower"
        if any(k in name_l for k in ("netrunner", "hacker", "cipher")): return f"{faction_name.strip()} Subnet Haven"
        return f"{faction_name.strip()} Neon Hideout"

    if any(k in name_l for k in ("fleet", "navy", "aeronaut", "dirigible", "airship", "starship", "flotilla", "armada")):
        if has_tag(scen_key, "steampunk"):
            return f"{faction_name.strip()} Aerodrome Gantry"
        return f"{faction_name.strip()} Command Bridge"

    if has_tag(scen_key, "space") or has_tag(scen_key, "sci_fi"):
        return f"{faction_name.strip()} Orbital Command Station"

    if any(k in name_l for k in ("inquisit", "witch hunter", "witch-hunter", "purifier", "heretic hunter")):
        return f"{faction_name.strip()} Iron Sanctum & Citadel"

    if re.search(r'\bcults?\b', name_l) or any(k in name_l for k in ("coven", "necroman", "eldritch", "harbinger", "blood pact")):
        return f"{faction_name.strip()} Hidden Catacomb & Altar"

    if any(k in name_l for k in ("union", "boilermaker", "steamfitter", "smelter", "foundry", "machinist")):
        return f"{faction_name.strip()} Foundry & Labor Hall"

    if any(k in name_l for k in ("merchant", "caravan", "trade", "consortium", "bourse", "banking")):
        return f"{faction_name.strip()} Grand Exchange & Trading Post"

    if any(k in name_l for k in ("scavenger", "salvage", "scrapper", "junk", "waste reclaimer")):
        return f"{faction_name.strip()} Scrapyard Depot & Workshop"

    if has_tag(scen_key, "post_apocalypse"):
        return f"{faction_name.strip()} Fortified Outpost"

    if any(k in name_l for k in ("alchem", "apothecary", "potion", "distill", "elixir", "crucible", "transmutation")):
        if has_tag(scen_key, "steampunk"):
            return f"{faction_name.strip()} Laboratory & Workshop"
        return f"{faction_name.strip()} Alchemical Sanctuary"

    if any(k in name_l for k in ("academy", "institute", "university", "research", "conservatory")):
        return f"{faction_name.strip()} Grand Hall"

    return f"{faction_name.strip()} Guildhall"


# ---------------------------------------------------------------- Procedural Leadership Roster Generator
def _random_npc_name(used: set, scen_key: str = "") -> str:
    """Generate a unique scenario-accurate NPC name not already in `used`."""
    import namegen
    for _ in range(50):
        name = namegen.generate_person_name(scen_key or "fantasy")
        if name not in used:
            return name
    return namegen.generate_person_name(scen_key or "fantasy")


def generate_procedural_leadership_roster(arg1: str, arg2: str = "",
                                          arg3: str = "") -> List[Dict[str, Any]]:
    """
    Lazily generate a full leadership roster with unique random NPC names for each rank tier.
    Accepts (template, scen_key), (faction_name, template, scen_key), or keyword arguments.
    Returns list ordered rank 4 (leader) down to rank 1 (entry).
    Each entry: {rank, title, name, is_player, is_vacant}
    """
    import scenario_data

    # Disambiguate arguments
    template = ""
    scen_key = ""
    faction_name = ""

    known_templates = set(FACTION_HIERARCHIES.keys())
    args = [a for a in (arg1, arg2, arg3) if a]

    for a in args:
        if a in known_templates and not template:
            template = a
        elif scenario_data.has_tag(a, "high_school") or scenario_data.has_tag(a, "cyberpunk") or a in scenario_data.load_scenarios():
            scen_key = a
        elif not faction_name:
            faction_name = a

    if not template:
        if faction_name:
            template = guess_hierarchy_template(faction_name, scen_key)
        else:
            template = "default"

    tiers = get_hierarchy(template)
    used_names: set = set()
    roster = []
    for tier in reversed(tiers):  # Build from highest rank first
        name = _random_npc_name(used_names, scen_key)
        used_names.add(name)
        roster.append({
            "rank": tier["rank"],
            "title": tier["title"],
            "name": name,
            "is_player": False,
            "is_vacant": False,
        })
    roster.sort(key=lambda x: x["rank"], reverse=True)
    return roster


def promote_player_in_roster(roster: List[Dict[str, Any]], player_name: str,
                              new_rank: int, template: str) -> List[Dict[str, Any]]:
    """
    Usurp the NPC at new_rank, place the player there, and shift the displaced NPC down.
    Returns the updated roster.
    """
    new_title = get_rank_title(template, new_rank)
    displaced_npc = None

    updated = []
    for entry in roster:
        if entry["rank"] == new_rank:
            displaced_npc = entry.get("name") if not entry.get("is_player") else None
            updated.append({
                "rank": new_rank,
                "title": new_title,
                "name": player_name,
                "is_player": True,
                "is_vacant": False,
            })
        else:
            updated.append(dict(entry))

    # Shift displaced NPC to rank - 1 if a slot exists and is held by an NPC
    if displaced_npc:
        lower_rank = new_rank - 1
        if lower_rank >= 1:
            for entry in updated:
                if entry["rank"] == lower_rank and not entry.get("is_player"):
                    entry["name"] = displaced_npc
                    break

    updated.sort(key=lambda x: x["rank"], reverse=True)
    return updated


def remove_player_from_roster(roster: List[Dict[str, Any]], player_name: str,
                               template: str, scen_key: str = "") -> List[Dict[str, Any]]:
    """Remove the player from the roster and replace their slot with a new procedural NPC."""
    used = {e["name"] for e in roster if not e.get("is_player")}
    updated = []
    for entry in roster:
        if entry.get("is_player") and entry.get("name") == player_name:
            new_name = _random_npc_name(used, scen_key)
            used.add(new_name)
            updated.append({
                "rank": entry["rank"],
                "title": entry["title"],
                "name": new_name,
                "is_player": False,
                "is_vacant": False,
            })
        else:
            updated.append(dict(entry))
    updated.sort(key=lambda x: x["rank"], reverse=True)
    return updated


def get_incumbent_at_rank(roster: List[Dict[str, Any]], target_rank: int) -> Optional[str]:
    """Return the name of whoever currently holds target_rank, or None if vacant/player."""
    for entry in roster:
        if entry["rank"] == target_rank:
            return entry.get("name") if not entry.get("is_player") else None
    return None


# ---------------------------------------------------------------- Promotion Trial Directives
def get_promotion_trial_directive(current_rank: int, target_rank: int,
                                  incumbent_name: str, faction_name: str,
                                  template: str, scen_key: str) -> str:
    """Build the LLM system directive string for a promotion trial scene."""
    from scenario_data import has_tag
    target_title = get_rank_title(template, target_rank)
    is_top = any(t.get("is_leader") and t["rank"] == target_rank for t in get_hierarchy(template))
    inc = incumbent_name or "the current holder"

    if template in ("alchemy", "academy"):
        if is_top:
            trial_desc = (
                f"{inc} challenges the player to a Masterwork Symposium Defense. The player must synthesize "
                f"or defend an unprecedented alchemical formula or academic magnum opus before the senior council."
            )
            choices_note = (
                "Generate 3 choices: (1) precision distillation or formula proof [INT 9], "
                "(2) experimental catalyst discovery [PER 8], (3) symposium defense rhetoric [CHA 7]."
            )
        else:
            trial_desc = (
                f"{inc} (current {get_rank_title(template, current_rank + 1)}) challenges the player "
                f"to formulate a complex experimental elixir or solve an advanced scholarly treatise."
            )
            choices_note = (
                "Generate 3 choices: (1) rigorous analytical synthesis [INT 7], "
                "(2) rare reagent extraction [PER 7], (3) hazardous distillation endurance [END 6]."
            )
    elif template == "union":
        if is_top:
            trial_desc = (
                f"{inc} challenges the player to a Master Machining & Pressure Overhaul before the union delegates. "
                f"The player must repair a catastrophic steam boiler failure and win the assembly vote."
            )
            choices_note = (
                "Generate 3 choices: (1) thermodynamic schematic redesign [INT 9], "
                "(2) high-pressure manual valve overhaul [STR 8], (3) union floor rally speech [CHA 7]."
            )
        else:
            trial_desc = (
                f"{inc} (current {get_rank_title(template, current_rank + 1)}) demands the player "
                f"forge an intricate precision mechanism or resolve an industrial plant bottleneck."
            )
            choices_note = (
                "Generate 3 choices: (1) precision lathe machining [INT 7], "
                "(2) furnace heat endurance [END 7], (3) mechanical repair [STR 6]."
            )
    elif template == "fleet":
        if is_top:
            trial_desc = (
                f"{inc} challenges the player to a Flagship Tactical Simulation Drill. The player must navigate "
                f"a catastrophic fleet ambush and out-maneuver the incumbent's battle formation."
            )
            choices_note = (
                "Generate 3 choices: (1) tactical spatial navigation [INT 9], "
                "(2) precision evasive helm maneuvers [PER 8], (3) fleet-wide command presence [CHA 7]."
            )
        else:
            trial_desc = (
                f"{inc} (current {get_rank_title(template, current_rank + 1)}) challenges the player "
                f"to pilot a high-risk reconnaissance run through dangerous turbulence or hostile patrol grids."
            )
            choices_note = (
                "Generate 3 choices: (1) high-speed evasive piloting [AGI 7], "
                "(2) long-range sensor analysis [PER 7], (3) engine power rerouting [INT 6]."
            )
    elif template == "merchant":
        if is_top:
            trial_desc = (
                f"{inc} challenges the player to a High-Stakes Bourse Auction & Trade Monopoly Play. "
                f"The player must corner the market and negotiate dominant commercial terms before the merchant council."
            )
            choices_note = (
                "Generate 3 choices: (1) ruthless market rhetoric & bluff [CHA 9], "
                "(2) speculative arbitrage calculations [INT 8], (3) appraisal of hidden counterfeit assets [PER 7]."
            )
        else:
            trial_desc = (
                f"{inc} (current {get_rank_title(template, current_rank + 1)}) demands the player "
                f"secure a lucrative new trade contract or resolve an escalating tariff dispute."
            )
            choices_note = (
                "Generate 3 choices: (1) commercial persuasion [CHA 7], "
                "(2) ledger audit & fiscal analysis [INT 7], (3) cargo inspection [PER 6]."
            )
    elif template == "inquisition":
        if is_top:
            trial_desc = (
                f"{inc} convenes a High Inquisitorial Tribunal & Trial of Purity. The player must root out "
                f"a hidden heresy within the chapterhouse and withstand the sacred rite of unyielding conviction."
            )
            choices_note = (
                "Generate 3 choices: (1) canonical theological interrogation [INT 9], "
                "(2) uncovering hidden unholy marks [PER 8], (3) endurance against demonic psychic taint [END 7]."
            )
        else:
            trial_desc = (
                f"{inc} (current {get_rank_title(template, current_rank + 1)}) challenges the player "
                f"to track down a fugitive rogue occultist or cleanse an active defiled site."
            )
            choices_note = (
                "Generate 3 choices: (1) tracking occult residue [PER 7], "
                "(2) rite of banishment [INT 7], (3) combat purge of monstrosities [STR 7]."
            )
    elif template == "cult":
        if is_top:
            trial_desc = (
                f"{inc} challenges the player to a Forbidden Rite of Ascension before the dark entity. "
                f"The player must commune directly with the abyss and assert psychic dominance over the covenant."
            )
            choices_note = (
                "Generate 3 choices: (1) forbidden eldritch incantations [INT 9], "
                "(2) psychic will against eldritch madness [END 8], (3) commanding the lesser acolytes [CHA 7]."
            )
        else:
            trial_desc = (
                f"{inc} (current {get_rank_title(template, current_rank + 1)}) demands the player "
                f"harvest a sacred blood essence or decipher an ancient cursed tablet."
            )
            choices_note = (
                "Generate 3 choices: (1) occult cipher translation [INT 7], "
                "(2) shadow stealth infiltration [AGI 7], (3) relic attunement [PER 6]."
            )
    elif template == "scavenger":
        if is_top:
            trial_desc = (
                f"{inc} challenges the player to a High-Danger Salvage Run in a collapsing pre-war ruin or derelict core. "
                f"The player must extract a legendary intact power reactor before rival scavengers or lethal hazards."
            )
            choices_note = (
                "Generate 3 choices: (1) structural hazard appraisal [PER 9], "
                "(2) navigating lethal radiation debris [AGI 8], (3) prying loose heavy bulkhead salvage [STR 8]."
            )
        else:
            trial_desc = (
                f"{inc} (current {get_rank_title(template, current_rank + 1)}) challenges the player "
                f"to recover, diagnose, and field-repair a severely damaged piece of advanced machinery."
            )
            choices_note = (
                "Generate 3 choices: (1) scrap jury-rigging [INT 7], "
                "(2) component scavenging [PER 7], (3) heavy scrap hauling [STR 6]."
            )
    elif is_school_scenario(scen_key):
        if is_top:
            trial_desc = (
                f"{inc} refuses to step down without a fight. They challenge the player to a full "
                f"student-body election or public showcase debate in front of the entire school."
            )
            choices_note = (
                "Generate 3 choices: (1) rhetoric speech [CHA 9], "
                "(2) logic argument [INT 8], (3) improvised performance [PER 7]."
            )
        else:
            trial_desc = (
                f"{inc} (current {get_rank_title(template, current_rank + 1)}) challenges the player "
                f"to prove their competence by managing a campus emergency or event crisis."
            )
            choices_note = (
                "Generate 3 choices: (1) organizational task [INT 7], "
                "(2) social diplomacy [CHA 8], (3) creative solution [PER 6]."
            )
    elif has_tag(scen_key, "fantasy") or has_tag(scen_key, "grimdark") or has_tag(scen_key, "dark_fantasy") or has_tag(scen_key, "steampunk"):
        if is_top:
            trial_desc = (
                f"{inc} steps into the sacred arena for a formal honor sparring duel — non-lethal, "
                f"the loser yields at 0 HP. Set `sparring: true` in the combat entity."
            )
            choices_note = (
                "Generate 3 combat choices: (1) strength assault [STR 9], "
                "(2) agility counter [AGI 8], (3) tactical feint [INT 7]."
            )
        else:
            trial_desc = (
                f"{inc} demands the player complete a dangerous field test that previously stumped them."
            )
            choices_note = (
                "Generate 3 choices: (1) endurance [END 7], (2) perception [PER 7], (3) strength [STR 8]."
            )
    elif has_tag(scen_key, "cyberpunk") or has_tag(scen_key, "space") or has_tag(scen_key, "sci_fi"):
        if is_top:
            trial_desc = (
                f"{inc} refuses to relinquish authority. The player must outmaneuver them in a boardroom "
                f"power play using leverage, data, or allies to force a resignation."
            )
            choices_note = (
                "Generate 3 choices: (1) present data leverage [INT 9], "
                "(2) persuade stakeholders [CHA 8], (3) hack private files [AGI 8]."
            )
        else:
            trial_desc = (
                f"{inc} sets up a live field contract — the player must complete it faster and cleaner."
            )
            choices_note = (
                "Generate 3 choices: (1) netrunning [INT 7], (2) stealth [AGI 7], (3) social engineering [CHA 7]."
            )
    else:
        trial_desc = (
            f"{inc} issues a formal challenge to prove the player's merit for "
            f"the position of {target_title} in {faction_name}."
        )
        choices_note = (
            "Generate 3 distinct skill check choices across STR, CHA, and INT. "
            "All represent different approaches to prove worthiness for this promotion."
        )

    return (
        f"FACTION PROMOTION TRIAL DIRECTIVE:\n"
        f"- Player challenges for rank [{target_title}] in [{faction_name}].\n"
        f"- Incumbent: {inc} (current holder of rank {target_rank}).\n"
        f"- Trial: {trial_desc}\n"
        f"- {choices_note}\n"
        f"- On success: narrate {inc} conceding defeat and the promotion being formally granted. "
        f"Set `faction_promotion_result` to 'success' in JSON outcome.\n"
        f"- On failure: {inc} retains rank. Tell the player to train harder and return. "
        f"Set `faction_promotion_result` to 'failure'. No permanent rep penalty on failure."
    )


# ---------------------------------------------------------------- NPC Affiliation
def get_npc_affiliation_chance(scen_key: str) -> float:
    """Return probability (0.0-1.0) that a newly generated NPC belongs to a faction."""
    from scenario_data import has_tag
    if is_school_scenario(scen_key):
        return 0.75
    return 0.40


def should_npc_have_faction(scen_key: str) -> bool:
    """Roll against faction affiliation probability for a newly generated NPC."""
    return random.random() < get_npc_affiliation_chance(scen_key)


# ---------------------------------------------------------------- Social Modifiers
def get_player_faction_social_modifier(player_faction_id: str, npc_faction_id: str,
                                       player_rep_score: int, is_rival: bool = False) -> int:
    """
    Return the social check modifier when interacting with an NPC based on faction alignment.
    Same faction: +2 | Rival faction: -2 to -3 | Unrelated: 0
    """
    if not player_faction_id or not npc_faction_id:
        return 0
    pid = (player_faction_id or "").strip().lower()
    nid = (npc_faction_id or "").strip().lower()
    if pid == nid:
        return 2
    if is_rival:
        tier_level = get_faction_tier(player_rep_score)["tier_level"]
        return -3 if tier_level <= -3 else -2
    return 0


# ---------------------------------------------------------------- Perks Evaluation
def get_active_perks(faction: Dict[str, Any], player_rank: int, reputation_score: int) -> List[str]:
    """Return list of active perk strings based on the player's rank and reputation score."""
    if player_rank == 0:
        return []
    perks = []
    tier = get_faction_tier(reputation_score)
    tier_level = tier["tier_level"]
    discount = tier["discount_pct"]
    if discount > 0:
        perks.append(f"Quartermaster Discount: {discount}% off faction shop")
    if tier_level >= 2:
        perks.append("Safehouse Rest: Free HP/MP recovery at HQ (0 ambush risk)")
    if tier_level >= 3:
        perks.append("Social Advantage: +2 to skill checks with fellow members")
    if player_rank >= 3 and tier_level >= 4:
        perks.append("Call Reinforcements: Summon faction patrol in combat (1x per session)")
    return perks


# ---------------------------------------------------------------- Combat Reinforcement Generator
def generate_faction_patrol(faction: Dict[str, Any], avg_party_level: int,
                             scen_key: str) -> List[Dict[str, Any]]:
    """
    Generate 1-2 scaled faction patrol NPCs for injection into current_npcs as friendly allies.
    """
    from scenario_data import has_tag
    cat = faction.get("category", "guild")
    name = faction.get("name", "Faction")
    level = max(1, avg_party_level)
    hp = 20 + level * 8
    mp = 10 + level * 4

    if has_tag(scen_key, "cyberpunk") or has_tag(scen_key, "space") or has_tag(scen_key, "sci_fi"):
        patrol_names = [f"{name} Strike Operative", f"{name} Tactical Unit"]
        stats = {"STR": 5, "PER": 7, "END": 5, "CHA": 4, "INT": 6, "AGI": 8, "LUK": 5}
    elif is_school_scenario(scen_key):
        patrol_names = [f"{name} Senior Member", f"{name} Enforcer"]
        stats = {"STR": 6, "PER": 5, "END": 6, "CHA": 5, "INT": 5, "AGI": 5, "LUK": 5}
    elif cat == "delinquents":
        patrol_names = [f"{name} Brawler", f"{name} Muscle"]
        stats = {"STR": 8, "PER": 4, "END": 7, "CHA": 3, "INT": 4, "AGI": 5, "LUK": 4}
    else:
        patrol_names = [f"{name} Veteran", f"{name} Enforcer"]
        stats = {"STR": 7, "PER": 5, "END": 6, "CHA": 4, "INT": 5, "AGI": 6, "LUK": 5}

    scaled = {k: min(12, v + level // 3) for k, v in stats.items()}
    patrols = []
    for patrol_name in patrol_names[:2]:
        patrols.append({
            "name": patrol_name,
            "level": level,
            "hp": hp,
            "max_hp": hp,
            "mp": mp,
            "max_mp": mp,
            "stats": scaled,
            "status_effects": [],
            "faction_patrol": True,
        })
    return patrols


# ---------------------------------------------------------------- Discord UI Views
import discord

class FactionHQView(discord.ui.View):
    def __init__(self, cog, session_id: int, member_ids: list, faction: dict):
        super().__init__(timeout=1800)
        self.cog = cog
        self.session_id = session_id
        self.member_ids = member_ids
        self.faction = faction
        self.build_buttons(None)

    def _in_party(self, user_id: int) -> bool:
        return user_id in self.member_ids

    def build_buttons(self, user_id: int = None):
        self.clear_items()
        
        # If user_id is provided, customize view for them (for ephemeral responses)
        # If not, provide generic buttons and check inside callback
        btn = discord.ui.Button(label="Apply to Join", style=discord.ButtonStyle.success, emoji="📝")
        btn.callback = self._on_apply
        self.add_item(btn)
        
        # Member features
        btn = discord.ui.Button(label="Rest at HQ", style=discord.ButtonStyle.primary, emoji="🏕️")
        btn.callback = self._on_rest
        self.add_item(btn)
        
        btn = discord.ui.Button(label="Quartermaster", style=discord.ButtonStyle.success, emoji="🛍️")
        btn.callback = self._on_quartermaster
        self.add_item(btn)
            
        btn = discord.ui.Button(label="Bounty Board", style=discord.ButtonStyle.secondary, emoji="📋")
        btn.callback = self._on_bounty
        self.add_item(btn)
            
        btn = discord.ui.Button(label="Promotion Trial", style=discord.ButtonStyle.danger, emoji="⚔️")
        btn.callback = self._on_promotion
        self.add_item(btn)
                
        leave = discord.ui.Button(label="Leave HQ", style=discord.ButtonStyle.secondary, emoji="🚪")
        leave.callback = self._on_leave
        self.add_item(leave)

    async def _on_apply(self, interaction: discord.Interaction):
        if not self._in_party(interaction.user.id):
            await interaction.response.send_message("You're not in this session.", ephemeral=True)
            return
        await self.cog.faction_apply(interaction, self.session_id, interaction.user.id, self.faction)

    async def _on_rest(self, interaction: discord.Interaction):
        if not self._in_party(interaction.user.id):
            return
        await self.cog.faction_rest(interaction, self.session_id, interaction.user.id, self.faction)

    async def _on_quartermaster(self, interaction: discord.Interaction):
        if not self._in_party(interaction.user.id):
            return
        await self.cog.faction_quartermaster(interaction, self.session_id, interaction.user.id, self.faction)

    async def _on_bounty(self, interaction: discord.Interaction):
        if not self._in_party(interaction.user.id):
            return
        await self.cog.faction_bounty(interaction, self.session_id, interaction.user.id, self.faction)

    async def _on_promotion(self, interaction: discord.Interaction):
        if not self._in_party(interaction.user.id):
            return
        await self.cog.faction_promotion(interaction, self.session_id, interaction.user.id, self.faction)

    async def _on_leave(self, interaction: discord.Interaction):
        if not self._in_party(interaction.user.id):
            return
        await self.cog.faction_leave(interaction, self.session_id, interaction.user.id)

# ---------------------------------------------------------------- LLM Context Formatting
def format_llm_faction_context(factions: List[Dict[str, Any]], max_items: int = 6,
                                player_faction_id: str = "", player_rank: int = 0,
                                player_title: str = "") -> str:
    if not factions:
        return ""

    # Build a name lookup for compact rival display
    fac_name_map = {f.get("faction_id", ""): f.get("name", "") for f in factions}

    entries = []
    for f in factions[:max_items]:
        score = f.get("reputation_score", 0)
        tier = get_faction_tier(score)
        fname = f.get("name", "Unknown Faction")
        fid = f.get("faction_id", "")

        membership_str = ""
        if player_faction_id and fid == player_faction_id and player_rank > 0:
            title = player_title or get_rank_title(f.get("hierarchy_template", "default"), player_rank)
            membership_str = f"|MEMBER:{title}"

        # Embed Rank-4 (top leader) and key officers globally — prevents LLM hallucination of leaders
        leader_str = ""
        officers_str = ""
        roster = f.get("leadership_roster") or []
        rank4_members = [r for r in roster if r.get("rank") == 4 and r.get("name") and not r.get("is_player")]
        if rank4_members:
            leader_str = f"|Leader:{rank4_members[0]['name']}"
        sub_officers = [
            f"{r['name']} ({r.get('title', 'Officer')})"
            for r in roster
            if r.get("rank") in (3, 2) and r.get("name") and not r.get("is_player") and not r.get("is_vacant")
        ]
        if sub_officers:
            officers_str = "|Officers:" + ", ".join(sub_officers[:2])

        # Embed rival faction names compactly (up to 2) for diplomatic grounding
        rival_ids = f.get("rival_faction_ids") or []
        rival_names = [fac_name_map[r] for r in rival_ids[:2] if r in fac_name_map and fac_name_map[r]]
        rival_str = ("|Rivals:" + ",".join(rival_names)) if rival_names else ""

        entries.append(f"{fname} [{tier['name']}|{score:+d}{membership_str}{leader_str}{officers_str}{rival_str}]")

    return "FACTIONS: " + "; ".join(entries)


def format_llm_player_faction_block(faction: Dict[str, Any], player_rank: int,
                                    player_title: str) -> str:
    """Format a compact block about the player's pledged faction for injection into GM prompt."""
    if not faction or player_rank == 0:
        return ""
    fname = faction.get("name", "Unknown")
    score = faction.get("reputation_score", 0)
    tier = get_faction_tier(score)
    hq = faction.get("hq_location_id", "")
    hq_str = f" | HQ: {hq}" if hq else ""
    return (
        f"PLAYER FACTION MEMBERSHIP: {fname} [{tier['name']}|{score:+d}] "
        f"Rank {player_rank}: {player_title}{hq_str}"
    )


# ---------------------------------------------------------------- Session Seeding
def _role_leadership_rank_weight(role_str: str) -> int:
    """Returns a leadership priority weight (0-4) based on a character's role title."""
    r_low = str(role_str or "").lower().replace("-", " ").strip()
    if not r_low:
        return 0
    if "vice president" in r_low or r_low.endswith(" vp") or "deputy" in r_low:
        return 3
    if any(w in r_low for w in ("president", "director", "chief editor", "captain", "senior lead", "boss", "founder")):
        return 4
    if any(w in r_low for w in ("lead", "treasurer", "secretary", "investigator", "enforcer")):
        return 2
    if any(w in r_low for w in ("representative", "columnist", "painter", "assistant", "guard", "sprinter", "runner", "sketch artist", "clarinetist")):
        return 1
    return 0


def _match_school_roster_to_faction(faction_name: str, school_roster: list[dict], template: str) -> list[dict]:
    tiers = get_hierarchy(template)
    fac_lower = faction_name.lower()

    # Exclude Faculty from student clubs, councils, and gangs unless explicitly a faculty faction
    is_faculty_faction = any(k in fac_lower for k in ("faculty", "staff", "teacher", "administration", "board"))
    pool = [
        c for c in school_roster
        if (str(c.get("grade", "")).strip().lower() == "faculty") == is_faculty_faction
    ]
    if not pool:
        pool = [c for c in school_roster if str(c.get("grade", "")).strip().lower() != "faculty"]

    primary_matched = []
    secondary_matched = []

    if "council" in fac_lower or "student" in fac_lower:
        for c in pool:
            r_low = str(c.get("role", "")).lower()
            club = str(c.get("club", ""))
            if club == "Student Council" or re.search(r"\bcouncil\b|\bclass representative\b|\bhallway monitor\b", r_low):
                primary_matched.append(c)
    elif "drama" in fac_lower or "theater" in fac_lower or "theatre" in fac_lower or re.search(r"\barts?\b", fac_lower):
        for c in pool:
            r_low = str(c.get("role", "")).lower()
            club = str(c.get("club", ""))
            # Strictly exclude Martial Arts / Athletic Directorate from Drama & Arts clubs
            if club == "Athletic Directorate" or "martial art" in r_low:
                continue
            if club in ("Arts & Drama Society", "Drama Club") or re.search(r"\b(drama|theater|theatre|stage|acting)\b", r_low):
                primary_matched.append(c)
            elif club in ("Fine Arts Guild", "Arts & Music Wing") or re.search(r"\b(sketch artist|clarinetist|musician|choir)\b", r_low):
                secondary_matched.append(c)
    elif "occult" in fac_lower or "mystery" in fac_lower or "paranormal" in fac_lower:
        for c in pool:
            r_low = str(c.get("role", "")).lower()
            club = str(c.get("club", ""))
            if club == "Occult & Mystery Club" or re.search(r"\b(occult|mystery|tarot|paranormal)\b", r_low):
                primary_matched.append(c)
            elif club in ("Literature & Book Circle", "Library Archives", "Astronomy & Physics Circle") or re.search(r"\b(bookworm|library|astronomer)\b", r_low):
                secondary_matched.append(c)
    elif template == "delinquents" or any(w in fac_lower for w in ("delinquent", "rebel", "wildcat", "brawler", "gang", "blazer")):
        for c in pool:
            r_low = str(c.get("role", "")).lower()
            clique = str(c.get("clique", ""))
            fac_str = str(c.get("primary_facility", "")).lower()
            if clique in ("Rebels", "Slackers") or re.search(r"\b(delinquent|rebel|slacker)\b", r_low):
                primary_matched.append(c)
            elif "brawler" in fac_str or "rooftop" in fac_str:
                secondary_matched.append(c)
    elif "athletic" in fac_lower or "varsity" in fac_lower or "sports" in fac_lower:
        for c in pool:
            r_low = str(c.get("role", "")).lower()
            club = str(c.get("club", ""))
            if club == "Athletic Directorate" or re.search(r"\b(varsity|captain|sprinter|swim|basketball|runner|track|martial arts)\b", r_low):
                primary_matched.append(c)
    elif "journalism" in fac_lower or "newspaper" in fac_lower or "media" in fac_lower:
        for c in pool:
            r_low = str(c.get("role", "")).lower()
            club = str(c.get("club", ""))
            if club == "Journalism & Media" or re.search(r"\b(editor|columnist|reporter|broadcast)\b", r_low):
                primary_matched.append(c)
    elif "science" in fac_lower or "robotics" in fac_lower:
        for c in pool:
            r_low = str(c.get("role", "")).lower()
            club = str(c.get("club", ""))
            if club == "Science & Robotics Club" or re.search(r"\b(robotics|science|chemistry|lab assistant)\b", r_low):
                primary_matched.append(c)

    if not primary_matched and not secondary_matched:
        return []

    grade_weight = {"Faculty": 5, "Senior": 4, "Junior": 3, "Sophomore": 2, "Freshman": 1}
    primary_sorted = sorted(
        primary_matched,
        key=lambda x: (_role_leadership_rank_weight(x.get("role", "")), grade_weight.get(x.get("grade"), 0)),
        reverse=True,
    )
    secondary_sorted = sorted(
        secondary_matched,
        key=lambda x: (_role_leadership_rank_weight(x.get("role", "")), grade_weight.get(x.get("grade"), 0)),
        reverse=True,
    )
    matched_sorted = primary_sorted + [c for c in secondary_sorted if c not in primary_sorted]

    roster = []
    used_indices = 0
    used_names = {str(c.get("name", "")).strip() for c in school_roster if c.get("name")}
    for tier in reversed(tiers):
        if used_indices < len(matched_sorted):
            char = matched_sorted[used_indices]
            roster.append({
                "rank": tier["rank"],
                "title": tier["title"],
                "name": char["name"],
                "is_player": False,
                "is_vacant": False
            })
            used_indices += 1
        else:
            gen_name = _random_npc_name(used_names, "high_school_drama")
            used_names.add(gen_name)
            roster.append({
                "rank": tier["rank"],
                "title": tier["title"],
                "name": gen_name,
                "is_player": False,
                "is_vacant": False
            })
    roster.sort(key=lambda x: x["rank"], reverse=True)
    return roster


def sync_faction_rosters_with_contacts(session_id: int) -> list[dict]:
    """
    Synchronizes faction leadership rosters with established character contacts and school_directory.
    1. Self-heals student faction rosters that mistakenly contain Faculty or mismatched clubs.
    2. Places established contacts with matching faction/club titles into their canonical rank,
       cascading displaced non-contact officers down by one rank instead of deleting them.
    3. Preserves rich narrative descriptions and dispositions in lorebook while keeping
       generic officer descriptions up to date.
    4. Bidirectionally syncs faction officers into school_directory in school scenarios.
    """
    import db
    from mechanics.world.locations import is_school_scenario

    factions = db.get_factions(session_id)
    if not factions:
        return []

    sess = db.get_session(session_id)
    scen_key = sess.get("scenario", "fantasy") if sess else "fantasy"
    is_school = is_school_scenario(scen_key)

    contacts = db.get_contacts(session_id) or []
    school_roster = db.get_school_roster(session_id) if is_school else []
    dir_by_name = {str(r.get("name", "")).strip().lower(): r for r in (school_roster or []) if r.get("name")}

    existing_lore_persons = {}
    try:
        lb = db.get_lorebook(session_id) or {}
        for p in lb.get("person", []):
            if p.get("name"):
                existing_lore_persons[str(p["name"]).strip().lower()] = p
    except Exception:
        pass

    generic_desc_re = re.compile(r"^[A-Za-z0-9 &'\-]{2,40} of [A-Za-z0-9 &'\-]{2,45}\.$", re.IGNORECASE)

    def _normalize_title(t: str) -> str:
        t_clean = str(t or "").lower().replace("-", " ")
        for prefix in ("student council", "council", "club", "disciplinary"):
            t_clean = t_clean.replace(prefix, "")
        t_clean = t_clean.replace("&", " ").strip()
        return " ".join(t_clean.split())

    def _clubs_match(fac_low: str, club_low: str) -> bool:
        if not fac_low or not club_low:
            return False
        if fac_low in club_low or club_low in fac_low:
            return True
        if "drama" in fac_low and any(w in club_low for w in ("drama", "theater", "theatre")):
            return True
        if "council" in fac_low and "council" in club_low:
            return True
        if "occult" in fac_low and ("occult" in club_low or "mystery" in club_low):
            return True
        return False

    updated_any = False
    new_dir_entries = []

    for f in factions:
        roster = list(f.get("leadership_roster") or [])
        if not roster:
            continue

        fac_name_orig = f.get("name", "")
        fac_name = fac_name_orig.lower()
        roster_modified = False
        displaced_off_roster = set()

        # 1. Self-heal student faction rosters if they contain Faculty or wrong-club entries (e.g. Martial Arts in Drama Club)
        if is_school and school_roster:
            is_fac_faction = any(k in fac_name for k in ("faculty", "staff", "teacher", "administration", "board"))
            if not is_fac_faction:
                has_invalid_member = False
                for r_entry in roster:
                    m_name_low = str(r_entry.get("name", "")).strip().lower()
                    dir_entry = dir_by_name.get(m_name_low)
                    if dir_entry:
                        if str(dir_entry.get("grade", "")).strip().lower() == "faculty":
                            has_invalid_member = True
                            displaced_off_roster.add(m_name_low)
                        elif ("drama" in fac_name or "theater" in fac_name) and (
                            dir_entry.get("club") == "Athletic Directorate" or "martial art" in str(dir_entry.get("role", "")).lower()
                        ):
                            has_invalid_member = True
                            displaced_off_roster.add(m_name_low)
                        elif ("occult" in fac_name or "mystery" in fac_name) and (
                            dir_entry.get("clique") == "Rebels" or "delinquent" in str(dir_entry.get("role", "")).lower()
                        ):
                            has_invalid_member = True
                            displaced_off_roster.add(m_name_low)
                if has_invalid_member:
                    rebuilt = _match_school_roster_to_faction(fac_name_orig, school_roster, f.get("hierarchy_template", "club"))
                    if rebuilt and len(rebuilt) == len(roster):
                        roster = rebuilt
                        roster_modified = True

        # 2. Match contacts to ranks in this faction
        contact_by_rank: dict[int, dict] = {}
        for r_entry in roster:
            r_title = r_entry.get("title", "").strip().lower()
            r_rank = r_entry.get("rank", 1)
            if not r_title or r_entry.get("is_player"):
                continue

            for c in contacts:
                c_name = c.get("name", "").strip()
                if not c_name:
                    continue
                b = c.get("basic_info") or {}
                c_role = str(b.get("role") or c.get("role") or "").strip().lower()
                c_club_role = str(b.get("club_role") or "").strip().lower()
                c_club = str(b.get("club") or b.get("faction") or b.get("faction_affiliation") or c.get("faction") or "").strip().lower()

                if (not c_role or c_role in ("student", "companion", "resident", "contact", "none")) and not c_club_role:
                    continue

                # Ensure contact's club/faction actually belongs to this faction before matching titles
                faction_matches = _clubs_match(fac_name, c_club) or (fac_name in c_role)
                if not faction_matches and any(w in fac_name for w in ("council", "disciplinary")):
                    faction_matches = any(w in c_role for w in ("council", "disciplinary")) or any(w in c_club for w in ("council", "disciplinary"))
                if not faction_matches:
                    continue

                is_match = False
                role_candidates = [c_role] if c_role else []
                if c_club_role and (not c_role or ("vice" in c_role) == ("vice" in c_club_role)):
                    role_candidates.append(c_club_role)

                for cand_role in role_candidates:
                    if not cand_role:
                        continue
                    if cand_role.replace("-", " ") == r_title.replace("-", " "):
                        is_match = True
                        break
                    norm_cand = _normalize_title(cand_role)
                    norm_r = _normalize_title(r_title)
                    if norm_cand and norm_cand == norm_r:
                        is_match = True
                        break

                if is_match:
                    contact_by_rank[r_rank] = c
                    break

        # 3. Apply contact assignments and cascade displaced officers down by one rank
        if contact_by_rank:
            roster.sort(key=lambda x: x.get("rank", 0), reverse=True)
            contact_names_low = {c["name"].strip().lower() for c in contact_by_rank.values() if c.get("name")}
            assigned_names_low = set()
            carry_over_name = None

            for r_entry in roster:
                if r_entry.get("is_player"):
                    if r_entry.get("name"):
                        assigned_names_low.add(r_entry["name"].strip().lower())
                    continue

                r_rank = r_entry.get("rank", 1)
                old_name = str(r_entry.get("name") or "").strip()
                old_low = old_name.lower()

                if r_rank in contact_by_rank:
                    new_name = contact_by_rank[r_rank]["name"].strip()
                    new_low = new_name.lower()
                    if old_name and old_low != new_low and old_low not in contact_names_low and old_low not in assigned_names_low and carry_over_name is None:
                        carry_over_name = old_name
                    if old_name != new_name:
                        r_entry["name"] = new_name
                        r_entry["is_vacant"] = False
                        roster_modified = True
                    assigned_names_low.add(new_low)
                else:
                    if carry_over_name and carry_over_name.lower() not in assigned_names_low and carry_over_name.lower() not in contact_names_low:
                        next_carry = old_name if (old_name and old_low not in assigned_names_low and old_low not in contact_names_low) else None
                        if r_entry.get("name") != carry_over_name:
                            r_entry["name"] = carry_over_name
                            r_entry["is_vacant"] = False
                            roster_modified = True
                        assigned_names_low.add(carry_over_name.lower())
                        carry_over_name = next_carry
                    else:
                        if old_low:
                            assigned_names_low.add(old_low)

            if carry_over_name and carry_over_name.lower() not in assigned_names_low:
                displaced_off_roster.add(carry_over_name.lower())

        if roster_modified:
            f["leadership_roster"] = roster
            db.update_faction_leadership_roster(session_id, f["faction_id"], roster)
            updated_any = True

        # 4. Sync roster members with lorebook (preserving rich narrative descriptions) and school_directory
        for r_entry in roster:
            m_name = str(r_entry.get("name") or "").strip()
            if not m_name or r_entry.get("is_vacant") or r_entry.get("is_player"):
                continue
            m_low = m_name.lower()
            r_title = r_entry.get("title", "Member")
            generic_desc = f"{r_title} of {fac_name_orig}."

            existing_lb = existing_lore_persons.get(m_low)
            should_update_lb = False
            desc_to_write = ""
            disp_to_write = "neutral"

            if not existing_lb:
                should_update_lb = True
                desc_to_write = generic_desc
            else:
                cur_lb_desc = str(existing_lb.get("description") or "").strip()
                cur_lb_disp = str(existing_lb.get("disposition") or "neutral").strip() or "neutral"
                cur_lb_fac = str(existing_lb.get("faction") or "").strip()
                disp_to_write = cur_lb_disp
                if not cur_lb_desc or generic_desc_re.match(cur_lb_desc):
                    if cur_lb_desc != generic_desc or cur_lb_fac != fac_name_orig:
                        should_update_lb = True
                        desc_to_write = generic_desc
                elif cur_lb_fac != fac_name_orig:
                    should_update_lb = True
                    desc_to_write = ""  # Preserves existing rich description via COALESCE(NULLIF(?, ''), description)

            if roster_modified or should_update_lb:
                try:
                    db.upsert_lorebook_entity(
                        session_id=session_id,
                        entity_type="person",
                        name=m_name,
                        description=desc_to_write,
                        disposition=disp_to_write,
                        faction=fac_name_orig
                    )
                except Exception:
                    pass

            # Bidirectional sync to school_directory if a contact officer isn't in school_directory yet
            if is_school and m_low not in dir_by_name:
                matched_c = contact_by_rank.get(r_entry.get("rank", 0))
                b_info = (matched_c.get("basic_info") or {}) if matched_c else {}
                c_grade = str(b_info.get("grade") or ("Senior" if r_entry.get("rank", 1) >= 3 else "Junior")).strip()
                c_role_str = str(b_info.get("role") or r_title).strip()
                c_fac_loc = str(b_info.get("location") or f.get("hq_location_id") or "").strip()
                c_desc_str = str(b_info.get("description") or generic_desc).strip()
                new_rec = {
                    "session_id": session_id,
                    "npc_id": m_low.replace(" ", "_"),
                    "name": m_name,
                    "role": c_role_str,
                    "grade": c_grade,
                    "club": fac_name_orig,
                    "clique": str(b_info.get("clique") or fac_name_orig),
                    "primary_facility": c_fac_loc,
                    "secondary_facility": "",
                    "sibling_name": str(b_info.get("sibling_name") or ""),
                    "personality_summary": c_desc_str,
                    "is_hydrated": 1,
                }
                new_dir_entries.append(new_rec)
                dir_by_name[m_low] = new_rec

        # Clean up stale generic lorebook descriptions for anyone displaced off the 4-tier roster
        for disp_low in displaced_off_roster:
            existing_lb = existing_lore_persons.get(disp_low)
            if existing_lb:
                cur_lb_desc = str(existing_lb.get("description") or "").strip()
                if generic_desc_re.match(cur_lb_desc):
                    dir_entry = dir_by_name.get(disp_low)
                    if dir_entry:
                        new_d = f"{dir_entry.get('role', 'Student')} ({dir_entry.get('grade', 'Student')})."
                        new_fac = dir_entry.get("club", "")
                        try:
                            with db.get_conn() as conn:
                                conn.execute(
                                    "UPDATE lorebook SET description=?, faction=? WHERE session_id=? AND LOWER(name)=?",
                                    (new_d, new_fac, session_id, disp_low)
                                )
                        except Exception:
                            pass

    if new_dir_entries:
        try:
            db.save_school_roster(session_id, new_dir_entries)
        except Exception:
            pass

    if updated_any:
        return db.get_factions(session_id)
    return factions


def ensure_starter_factions(session_id: int, scenario_key: str = "fantasy") -> list[dict]:
    """
    Ensures pre-discovered starter factions exist in SQLite for the session.
    If no factions are recorded yet for this session, populates the scenario's
    starter factions, generates 4-tier procedural NPC leadership rosters with
    proper personal names, and saves them into SQLite.
    Also seeds named roster members into the lorebook so the LLM knows their
    canonical full names before the player meets them in-game.
    """
    import db
    import namegen
    import scenario_data
    from mechanics.world.locations import is_school_scenario

    existing = db.get_factions(session_id)
    if existing:
        return sync_faction_rosters_with_contacts(session_id)

    scen_key = scenario_key or "fantasy"
    is_nsfw = scenario_data.is_nsfw_scenario(scen_key)
    starters = namegen.get_scenario_starter_factions(scen_key, is_nsfw=is_nsfw)

    school_roster = []
    if is_school_scenario(scen_key):
        from mechanics.social.school_roster import ensure_school_directory_exists
        school_roster = ensure_school_directory_exists({"id": session_id, "scenario": scen_key})

    for fac in starters:
        name = fac["name"]
        template = fac.get("hierarchy_template", "guild")
        category = fac.get("category", "guild")
        hq = fac.get("hq_location_id", "")
        notes = fac.get("notes", "")

        roster = []
        if school_roster:
            roster = _match_school_roster_to_faction(name, school_roster, template)

        if not roster:
            roster = generate_procedural_leadership_roster(template, scen_key)

        db.upsert_faction(
            session_id=session_id,
            name=name,
            delta_score=0,
            category=category,
            hq_location_id=hq,
            notes=notes,
            hierarchy_template=template,
            leadership_roster=roster
        )

        # Seed named roster members into the lorebook so the LLM knows their
        # canonical full names before the player physically meets them.
        for member in roster:
            if member.get("is_vacant") or not member.get("name"):
                continue
            member_name = member["name"]
            member_title = member.get("title", "")
            description = f"{member_title} of {name}." if member_title else f"Member of {name}."
            from mechanics.social.races import normalize_race
            if member.get("race"):
                member_race = normalize_race(member["race"], scen_key=scen_key, seed=member_name)
            else:
                fallback_race = normalize_race("", scen_key=scen_key, seed=member_name)
                member_race = fallback_race if fallback_race != "human" else ""
            try:
                db.upsert_lorebook_entity(
                    session_id=session_id,
                    entity_type="person",
                    name=member_name,
                    description=description,
                    disposition="neutral",
                    faction=name,
                    traits=[],
                    motivation="",
                    mannerisms="",
                    race=member_race,
                    appearance={},
                )
            except Exception:
                pass

    return sync_faction_rosters_with_contacts(session_id)


ensure_session_factions_seeded = ensure_starter_factions

