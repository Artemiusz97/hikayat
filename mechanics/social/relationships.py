from __future__ import annotations
"""
Modular Relationship Engine for Hikayat.

Handles -100 to +100 relationship score calculations, tier lookup across genres,
platonic vs romantic track branching, progressive trait disclosure, and skill check modifiers.
"""
import math
import re
from typing import Dict, Any, List

MIN_RELATIONSHIP = -100
MAX_RELATIONSHIP = 300

NON_PEER_HIGH_SCHOOL_ROLE_PATTERNS = [
    # Faculty / Administration / Honorifics
    r"\b(mr|mrs|ms|miss|dr|prof|madame)\.?\s+[a-z]+",
    r"\b(teacher|professor|instructor|sensei|educator|faculty|tutor)\b",
    r"\b(principal|vice\s+principal|headmaster|headmistress|dean|curator|trustee|school\s+board|inspector|superintendent|administrator)\b",
    # School Support & Facility Staff
    r"\b(nurse|school\s+nurse|counselor|guidance\s+counselor|advisor|librarian)\b",
    r"\b(janitor|custodian|groundskeeper|caretaker|security\s+guard|security\s+officer|campus\s+guard|school\s+guard|hall\s+monitor)\b",
    r"\b(lunch\s+lady|cafeteria\s+staff|cafeteria\s+worker|cook|chef)\b",
    r"\b(coach|athletic\s+director|warden|dorm\s+warden|dorm\s+mother)\b",
    # Family / Adult Elders
    r"\b(parent|mother|father|mom|dad|stepmother|stepfather|step-mom|step-dad|guardian|uncle|aunt|grandmother|grandfather|grandparent|elder|adult)\b",
    # Service / Commercial / Town Workers
    r"\b(clerk|cashier|store\s+clerk|convenience\s+store\s+clerk|shopkeeper|storekeeper|shop\s+assistant)\b",
    r"\b(barista|waiter|waitress|bartender|barkeep|vendor|peddler|merchant)\b",
    r"\b(driver|bus\s+driver|conductor|transit\s+worker|train\s+operator|chauffeur)\b",
    r"\b(police|police\s+officer|cop|detective|sheriff|officer|landlord|landlady|manager|boss)\b",
]

PEER_HIGH_SCHOOL_PATTERNS = [
    r"\b(student|classmate|schoolmate|underclassman|upperclassman|peer|roommate|dorm\s+mate)\b",
    r"\b(freshman|sophomore|junior|senior|1st-year|2nd-year|3rd-year|first-year|second-year|third-year)\b",
    r"\b(grade\s+9|grade\s+10|grade\s+11|grade\s+12|class\s+\d-[a-z])\b",
    r"\b(student\s+council|class\s+rep|class\s+representative|club\s+president|club\s+vice\s+president|club\s+member|club\s+leader)\b",
    r"\b(delinquent|cheerleader|valedictorian|salutatorian|transfer\s+student|exchange\s+student)\b",
]

_NON_PEER_HIGH_SCHOOL_RE = [re.compile(p, re.IGNORECASE) for p in NON_PEER_HIGH_SCHOOL_ROLE_PATTERNS]
_PEER_HIGH_SCHOOL_RE = [re.compile(p, re.IGNORECASE) for p in PEER_HIGH_SCHOOL_PATTERNS]


def is_contact_eligible(
    name: str = "",
    role: str = "",
    description: str = "",
    scenario: str = "fantasy",
    disposition: str = "",
    session_id: int = 0
) -> bool:
    """
    Determines whether an NPC is eligible to be registered in the player's Contacts / Directory
    and accumulate relationship affinity.

    In High School / Non-Combat genres:
    - Fellow students, classmates, student council members, club members, delinquents,
      athletes, transfer students, and peer rivals ARE eligible.
    - Teachers, faculty, principals, parents, convenience store clerks, janitors, and
      adult authority / service workers are STORY-ONLY figures (stored in Lorebook/narrative,
      but never registered as Phone contacts or given affinity meters).
    """
    import namegen
    if namegen.is_collective_entity_name(name) or namegen.is_generic_role_name(name):
        return False

    import scenario_data
    is_hs = scenario_data.has_tag(scenario, "high_school")
    
    if is_hs:
        # If role and description are missing but session_id is provided, try looking up from session or lorebook
        grade = ""
        club = ""
        is_existing_contact = False
        if session_id:
            try:
                import db
                sess = db.get_session(session_id)
                if sess:
                    for n in (sess.get("current_npcs") or []):
                        if isinstance(n, dict) and str(n.get("name", "")).strip().lower() == str(name).strip().lower():
                            role = role or n.get("role", "")
                            description = description or n.get("description", "")
                            grade = grade or n.get("grade", "")
                            club = club or n.get("club", "")
                            break
                c = db.get_contact(session_id, name)
                if c:
                    is_existing_contact = True
                    b_inf = c.get("basic_info", {}) or {}
                    role = role or b_inf.get("role", "")
                    description = description or b_inf.get("description", "")
                    grade = grade or b_inf.get("grade", "")
                    club = club or b_inf.get("club", "")
                if not role and not description:
                    roster = db.get_school_roster(session_id)
                    for r_entry in (roster or []):
                        if str(r_entry.get("name", "")).strip().lower() == str(name).strip().lower():
                            role = role or r_entry.get("role", "")
                            description = description or r_entry.get("personality_summary", "")
                            grade = grade or r_entry.get("grade", "")
                            club = club or r_entry.get("club", "")
                            break
                if not role and not description:
                    lore = db.get_lorebook_entity(session_id, name)
                    if lore:
                        description = lore.get("description", "")
            except Exception:
                pass

        combined_text = f"{name} {role} {grade} {club} {description}".strip().lower()
        
        # 1. Check for adult/faculty/service markers
        has_non_peer_signal = any(rx.search(combined_text) for rx in _NON_PEER_HIGH_SCHOOL_RE)
        
        # 2. Check for explicit student peer markers
        has_peer_signal = any(rx.search(combined_text) for rx in _PEER_HIGH_SCHOOL_RE)

        if has_non_peer_signal:
            # Student Council / Class Rep / Club leaders are always recognized as peers
            if "student council" in combined_text or "class representative" in combined_text or "class rep" in combined_text:
                return True
            if has_peer_signal:
                # If adult authority keywords (teacher, principal, parent, clerk, nurse, janitor, mr./mrs.) are present, it's adult
                if any(t in combined_text for t in ("teacher", "professor", "principal", "parent", "mother", "father", "dad", "mom", "clerk", "cashier", "nurse", "janitor", "headmaster", "dean", "mr.", "mrs.", "dr.", "madame", "faculty")):
                    return False
                return True
            return False

        if has_peer_signal or is_existing_contact:
            return True

        # In High School Drama, any novel teenager / student archetype (e.g. "Goth Otaku", "Chess Prodigy", "Track Star", "Campus Streamer")
        # that has NO adult/faculty keywords defaults cleanly to True (Eligible Student Contemporary).
        return True

    return True

# Tier definitions for generic vs high school drama vs dark fantasy/sci-fi
TIER_LABELS: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
    "default": {
        "positive_platonic": [
            {"min": 250, "max": 300, "name": "Sworn Lifelong Ally", "tier_level": 5},
            {"min": 200, "max": 249, "name": "Confidant", "tier_level": 4},
            {"min": 150, "max": 199, "name": "Close Friend", "tier_level": 3},
            {"min": 100, "max": 149, "name": "Friend", "tier_level": 2},
            {"min": 50, "max": 99, "name": "Acquaintance", "tier_level": 1},
            {"min": 0, "max": 49, "name": "Stranger", "tier_level": 0},
        ],
        "positive_romantic": [
            {"min": 250, "max": 300, "name": "Soulmate / Eternal Bond", "tier_level": 5},
            {"min": 200, "max": 249, "name": "Devoted Lovers", "tier_level": 4},
            {"min": 150, "max": 199, "name": "Dating / Confessed Partners", "tier_level": 3},
            {"min": 100, "max": 149, "name": "Mutual Attraction / Crush", "tier_level": 2},
            {"min": 50, "max": 99, "name": "Acquaintance", "tier_level": 1},
            {"min": 0, "max": 49, "name": "Stranger", "tier_level": 0},
        ],
        "negative": [
            {"min": -10, "max": -1, "name": "Unfriendly", "tier_level": -1},
            {"min": -30, "max": -11, "name": "Distrusted", "tier_level": -2},
            {"min": -50, "max": -31, "name": "Adversary", "tier_level": -3},
            {"min": -70, "max": -51, "name": "Hostile", "tier_level": -4},
            {"min": -90, "max": -71, "name": "Bitter Nemesis", "tier_level": -5},
            {"min": -100, "max": -91, "name": "Mortal Foe", "tier_level": -6},
        ]
    },
    "high_school_drama": {
        "positive_platonic": [
            {"min": 250, "max": 300, "name": "Sworn Bestie", "tier_level": 5},
            {"min": 200, "max": 249, "name": "Inner Circle", "tier_level": 4},
            {"min": 150, "max": 199, "name": "Best Friend", "tier_level": 3},
            {"min": 100, "max": 149, "name": "Lunch Friend", "tier_level": 2},
            {"min": 50, "max": 99, "name": "Hallway Buddy", "tier_level": 1},
            {"min": 0, "max": 49, "name": "Stranger", "tier_level": 0},
        ],
        "positive_romantic": [
            {"min": 250, "max": 300, "name": "High School Sweethearts / Soulmate", "tier_level": 5},
            {"min": 200, "max": 249, "name": "Exclusive Romance", "tier_level": 4},
            {"min": 150, "max": 199, "name": "Dating / Partner", "tier_level": 3},
            {"min": 100, "max": 149, "name": "Big Crush", "tier_level": 2},
            {"min": 50, "max": 99, "name": "Hallway Buddy", "tier_level": 1},
            {"min": 0, "max": 49, "name": "Stranger", "tier_level": 0},
        ],
        "negative": [
            {"min": -10, "max": -1, "name": "Annoyance", "tier_level": -1},
            {"min": -30, "max": -11, "name": "Class Rival", "tier_level": -2},
            {"min": -50, "max": -31, "name": "Disliked", "tier_level": -3},
            {"min": -70, "max": -51, "name": "Bully / Hater", "tier_level": -4},
            {"min": -90, "max": -71, "name": "Bitter Nemesis", "tier_level": -5},
            {"min": -100, "max": -91, "name": "Arch-Enemy", "tier_level": -6},
        ]
    }
}


def clamp_score(score: int) -> int:
    """Ensure score stays strictly within [-100, 300]."""
    return max(MIN_RELATIONSHIP, min(MAX_RELATIONSHIP, int(score)))


def get_relationship_tier(score: int, track: str = "platonic", scenario: str = "default") -> Dict[str, Any]:
    """
    Get the tier object (name, level, range) for a given relationship score, track, and scenario.
    """
    score = clamp_score(score)
    labels = TIER_LABELS.get(scenario, TIER_LABELS["default"])
    
    if score >= 0:
        tier_list = labels["positive_romantic"] if track.lower() == "romantic" else labels["positive_platonic"]
        for tier in tier_list:
            if tier["min"] <= score <= tier["max"]:
                return tier
        return tier_list[-1]
    else:
        tier_list = labels["negative"]
        for tier in tier_list:
            if tier["min"] <= score <= tier["max"]:
                return tier
        return tier_list[-1]


def get_relationship_modifier(score: int) -> int:
    """
    Calculate skill check modifier based on relationship score.
    Formula: floor(score / 10), clamped between -10 and +10.
    e.g. +45 -> +4, +85 -> +8, +150 -> +10, -35 -> -4, -75 -> -8
    """
    score = clamp_score(score)
    raw = math.floor(score / 10)
    return max(-10, min(10, raw))


def get_unlocked_info_level(score: int) -> int:
    """
    Returns disclosure level (1 to 3) based on score magnitude.
    Level 1 (Score < 100 or -30..30): Surface details & visible anatomy (Stranger / Acquaintance)
    Level 2 (Score 100-199 or -31 to -70): Mannerisms & personality traits (Friend / Rival)
    Level 3 (Score 200+ or -71-): Preferences, deep secrets & full intimate profile (Confidant / Lover / Nemesis)
    """
    abs_score = abs(clamp_score(score))
    if score >= 0:
        if abs_score >= 200:
            return 3
        elif abs_score >= 100:
            return 2
        return 1
    else:
        if abs_score >= 71:
            return 3
        elif abs_score >= 31:
            return 2
        return 1


def get_information_disclosure_penalty(current_score: int, target_info_level: int) -> int:
    """
    Returns the skill check penalty (negative integer or 0) when attempting to pry or inquire
    about information above the current relationship standing.
    - Level 1 Info (Surface & Appearance): 0 penalty (Accessible to all)
    - Level 2 Info (Mannerisms / Traits, req score 100+):
        Stranger (< 50): -4 penalty
        Acquaintance (50-99): -2 penalty
        Friend+ (>= 100): 0 penalty
    - Level 3 Info (Preferences / Intimate Profile / Deep Secrets, req score 200+):
        Stranger (< 50): -8 penalty (Heavily guarded against strangers)
        Acquaintance (50-99): -5 penalty
        Friendly / Close Friend (100-199): -3 penalty
        Confidant / Soulmate (200+): 0 penalty
    """
    abs_score = abs(clamp_score(current_score))
    if target_info_level <= 1:
        return 0
    elif target_info_level == 2:
        if abs_score < 50:
            return -4
        elif abs_score < 100:
            return -2
        return 0
    elif target_info_level >= 3:
        if abs_score < 50:
            return -8
        elif abs_score < 100:
            return -5
        elif abs_score < 200:
            return -3
        return 0
    return 0


def get_disclosure_check_requirement(base_req: int, current_score: int, target_info_level: int) -> int:
    """
    Calculates the modified requirement for an information-seeking skill check.
    Increases requirement if the player's relationship standing is insufficient.
    """
    penalty = get_information_disclosure_penalty(current_score, target_info_level)
    return max(2, min(15, base_req + abs(penalty)))


def format_progress_bar(score: int, width: int = 10) -> str:
    """
    Generate a text progress bar representing score from -100 to +300.
    Center is 0.
    e.g. [-100 [███████░░░] +300]
    """
    score = clamp_score(score)
    # Map -100..300 -> 0..width
    normalized = int(((score + 100) / 400) * width)
    normalized = max(0, min(width, normalized))
    bar = "█" * normalized + "░" * (width - normalized)
    sign = "+" if score > 0 else ""
    return f"[{bar}] {sign}{score}"


MARTIAL_ROLE_PATTERNS = [
    # Fantasy / Isekai
    r"\b(guard|town guard|city guard|gate guard|watchman|sentry|patrol|guard captain|soldier|knight|paladin|warrior|mercenary|sellsword|ranger|archer|scout|mage|wizard|sorcerer|sorceress|warlock|assassin|rogue|monk|berserker|templar|slayer|spellsword|duelist|commander|brawler)\b",
    # Sci-Fi / Space
    r"\b(marine|shock trooper|trooper|bounty hunter|security officer|enforcer|commando|gunslinger|pilot|fleet officer)\b",
    # Cyberpunk
    r"\b(street samurai|solo|netrunner|corporate enforcer|hitman|bodyguard|cyber-thug|bouncer|syndicate gunner|security drone)\b",
    # Steampunk
    r"\b(airship gunner|sky pirate|clockwork automaton guard|rifleman|brass sentinel|mechanical enforcer)\b",
    # Post-Apocalypse
    r"\b(raider|scavenger|wasteland warrior|gunner|mutant hunter|militia|survivalist)\b",
    # Explicit combat descriptions
    r"\b(combatant|fighter|veteran|swordsman|blademaster|sharpshooter|martial artist|armed with|weapons? drawn|battle-hardened|war hero)\b"
]

CIVILIAN_ROLE_PATTERNS = [
    # Commercial / Service
    r"\b(merchant|vendor|shopkeeper|innkeeper|barkeep|bartender|peddler|grocer|trader|blacksmith|armorer|apothecary|baker|butcher|tailor|jeweler)\b",
    # Domestic / Civic
    r"\b(villager|farmer|peasant|fisherman|dockworker|laborer|waiter|waitress|maid|butler|servant|cook|chef|clerk|cashier|accountant|librarian|desk scholar|scholar|researcher|scientist|doctor|nurse|janitor|custodian)\b",
    # Vulnerable / Non-combatant
    r"\b(child|boy|girl|elder|elderly|invalid|civilian|bystander|onlooker|citizen|customer|patron|passerby|pedestrian)\b",
]

_MARTIAL_RE = [re.compile(p, re.IGNORECASE) for p in MARTIAL_ROLE_PATTERNS]
_CIVILIAN_RE = [re.compile(p, re.IGNORECASE) for p in CIVILIAN_ROLE_PATTERNS]


def is_martial_npc(entity: dict | str, scenario: str = "fantasy") -> bool:
    """
    Determines deterministically whether an NPC is a martial combatant or a civilian bystander.
    Evaluates role, occupation, and description against genre combat archetypes.
    """
    import scenario_data
    if scenario_data.has_tag(scenario, "non_combat") or scenario.lower() in ("high_school", "high_school_drama"):
        return False

    if isinstance(entity, str):
        combined = entity.lower()
    elif isinstance(entity, dict):
        role = str(entity.get("role") or entity.get("occupation") or "")
        desc = str(entity.get("description") or "")
        name = str(entity.get("name") or "")
        combined = f"{name} {role} {desc}".lower()
    else:
        return False

    # 1. Hard Civilian Blacklist
    if any(rx.search(combined) for rx in _CIVILIAN_RE):
        # Exception: explicit veteran / combatant overrides civilian trade (e.g. "retired vanguard soldier")
        if any(w in combined for w in ("veteran", "retired soldier", "retired knight", "former mercenary", "battle-hardened", "armed with")):
            return True
        return False

    # 2. Martial Archetype Match
    if any(rx.search(combined) for rx in _MARTIAL_RE):
        return True

    return False


def safe_clamp_delta(val: Any, min_val: int = -10, max_val: int = 10) -> int:
    """Safely converts input value to int and clamps it within [min_val, max_val]."""
    try:
        val_int = int(val)
    except (ValueError, TypeError):
        val_int = 0
    return max(min_val, min(max_val, val_int))


def reconcile_action_affinity_delta(
    raw_delta: Any,
    action: dict | None = None,
    is_target: bool = True,
    overall_check_success: bool = True,
    is_hostile: bool = False
) -> int:
    """
    Grounds raw LLM delta_score into deterministic bounds based on check tier, action intent, and target role.
    Prevents LLM hallucinations (such as -7 on successful skill checks) from corrupting NPC standings.

    Deterministic Rules:
    1. Bystanders (is_target=False):
       - Uninvolved NPCs who were not addressed or interacted with cannot receive negative affinity deltas.
       - Bounds: [0, 2], default: 0. Any negative LLM delta is dropped to 0.
    2. Hostile Actions (is_hostile=True, e.g. attacks, insults, crimes):
       - Bounds: [-10, -1], default: -3. Positive LLM deltas are converted to negative penalties.
    3. Social / Conversational / Friendly Actions (is_hostile=False, is_target=True):
       - Check tier dictates the deterministic baseline and acceptable range:
         * Critical Success: bounds [+3, +6], default +4.
         * Success: bounds [+1, +4], default +2.
         * Partial Success: bounds [0, +2], default +1.
         * Free / Ambient Action (no check): bounds [0, +3], default +1.
         * Failure: bounds [-2, 0], default -1.
         * Critical Failure: bounds [-4, -1], default -2.
       - If overall_check_success is True, affinity delta is strictly non-negative (>= 1 for targeted NPC).
    """
    try:
        val = int(raw_delta)
    except (ValueError, TypeError):
        val = None

    # 1. Bystander protection: uninvolved NPCs never lose affinity from the player talking to someone else
    if not is_target:
        if val is None or val < 0:
            return 0
        return min(10, val)

    # 2. Hostile action handling
    if is_hostile:
        if val is None or val >= 0:
            return -3
        return max(-10, min(-1, val))

    # 3. Check tier evaluation for friendly / social action
    check_obj = action.get("check") if isinstance(action, dict) else None
    tier = ""
    if check_obj:
        if isinstance(check_obj, dict):
            tier = str(check_obj.get("tier") or "").lower().strip()
        else:
            tier = str(getattr(check_obj, "tier", "") or "").lower().strip()

    if tier in ("crit_success", "critical_success"):
        min_b, max_b, def_d = 3, 10, 4
    elif tier in ("success",):
        min_b, max_b, def_d = 1, 10, 2
    elif tier in ("partial_success", "mixed_success"):
        min_b, max_b, def_d = 0, 5, 1
    elif not check_obj or tier in ("none", "free", ""):
        # Free / ambient conversational action without a d20 check:
        # Allows natural positive reactions (likes) and negative reactions (dislikes/offense)
        min_b, max_b, def_d = -5, 10, 1
        if val is not None and val < 0:
            def_d = max(-5, val)
    elif tier in ("crit_fail", "critical_failure"):
        min_b, max_b, def_d = -10, -1, -2
    else:  # fail / failure
        min_b, max_b, def_d = -5, 0, -1

    # If a specific skill check was rolled and succeeded on a non-hostile action, enforce minimum positive delta
    if check_obj and tier in ("crit_success", "critical_success", "success", "partial_success", "mixed_success"):
        if overall_check_success and min_b <= 0:
            min_b = 1
            max_b = 10
            def_d = max(def_d, 1)

    if val is None:
        return def_d

    # If raw_delta has the opposite valence of what check tier mandates (e.g. LLM hallucinated -7 on success)
    if min_b > 0 and val <= 0:
        return def_d
    if max_b < 0 and val >= 0:
        return def_d

    return max(min_b, min(max_b, val))


def format_llm_relationship_context(contacts: List[Dict[str, Any]], scenario: str = "default",
                                     scene_npcs: List[Dict[str, Any]] = None, history_text: str = "",
                                     max_items: int = 4) -> str:
    """
    Format active session contacts into a clear, compact context prompt block for LLMs
    using a 3-tier priority filter (Scene NPCs > Mentioned NPCs > Top Standings).
    """
    if not contacts:
        return ""

    scene_npc_names = set()
    if scene_npcs:
        for npc in scene_npcs:
            if isinstance(npc, dict) and npc.get("name"):
                scene_npc_names.add(npc["name"].lower().strip())

    history_lower = (history_text or "").lower()

    prioritized = []
    seen = set()

    # Tier 1: NPCs present in the scene
    for c in contacts:
        c_name = c.get("name", "").lower().strip()
        if c_name and c_name in scene_npc_names and c_name not in seen:
            prioritized.append(c)
            seen.add(c_name)

    # Tier 2: Mentioned in recent history/action
    for c in contacts:
        c_name = c.get("name", "").lower().strip()
        if c_name and c_name in history_lower and c_name not in seen:
            prioritized.append(c)
            seen.add(c_name)

    # Tier 3: Top highest/lowest relationship standings
    sorted_contacts = sorted(contacts, key=lambda x: abs(x.get("relationship_score", 0)), reverse=True)
    for c in sorted_contacts:
        c_name = c.get("name", "").lower().strip()
        if c_name and c_name not in seen and len(prioritized) < max_items:
            prioritized.append(c)
            seen.add(c_name)

    if not prioritized:
        return ""

    entries = []
    for c in prioritized[:max_items]:
        score = c.get("relationship_score", 0)
        track = c.get("track", "platonic")
        tier = get_relationship_tier(score, track, scenario)
        name = c.get("name", "Unknown NPC")
        sign = "+" if score > 0 else ""
        entries.append(f"{name} [{tier['name']}|{sign}{score}]")

    return "NPC STANDINGS: " + "; ".join(entries)


# ==============================================================================
# 3-LAYER ROMANTIC INTENT ENGINE & CONFESSION ELIGIBILITY
# ==============================================================================

from mechanics.narrative.intent import (
    classify_action_intent,
    IntentCategory,
    is_romantic_confession_intent as _is_romantic_confession_intent,
    ROMANTIC_CONFESSION_FRAMES,
    NON_ROMANTIC_QUALIFIER_RE,
    ROMANCE_NEGATION_GUARD_RE,
    THIRD_PARTY_GOSSIP_RE,
)


def is_romantic_confession_intent(text: str) -> bool:
    """
    Evaluates whether an action text or narrative represents a romantic confession / relationship agreement.
    Delegates to the centralized mechanics.narrative.intent engine.
    """
    return _is_romantic_confession_intent(text)


def is_gender_and_orientation_compatible(char_gender: str, npc_gender: str, npc_preferences: list = None) -> bool:
    """
    Evaluates basic romantic compatibility between character gender and NPC gender/preferences.
    Supports hetero, same-sex (lesbian/gay), bi/pan, and open configurations.
    """
    c_gen = str(char_gender or "").lower().strip()
    n_gen = str(npc_gender or "").lower().strip()
    prefs = [str(p).lower() for p in (npc_preferences or [])]

    # If preferences explicitly specify orientation
    if any("straight" in p or "hetero" in p for p in prefs):
        if c_gen and n_gen and c_gen == n_gen:
            return False
    if any("lesbian" in p for p in prefs):
        if c_gen != "female":
            return False
    if any("gay" in p for p in prefs):
        if c_gen != "male":
            return False

    # Default: open/compatible
    return True


def can_trigger_romantic_confession(
    session_id: int,
    character_id: int,
    npc_name: str,
    scenario: str = "high_school_drama"
) -> bool:
    """
    Evaluates whether the dedicated Romance Confession Milestone Choice should appear for an NPC:
    1. High Affinity Threshold: Score >= 100 (Tier 3 Friend/Crush - Romance Route Unlocks)
    2. Social Track: Currently 'platonic'
    3. Peer Eligibility: Student contemporary / peer (not teacher, store clerk, parent)
    4. Gender & Orientation Compatibility: True
    5. Cooldown: Confession cooldown == 0
    """
    if not session_id or not npc_name:
        return False

    import db
    # 1. Cooldown check
    if db.get_confession_cooldown(session_id, npc_name) > 0:
        return False

    # 2. Peer eligibility check
    if not is_contact_eligible(npc_name, scenario=scenario, session_id=session_id):
        return False

    # 3. Contact lookup
    contact = db.get_contact(session_id, npc_name, character_id)
    if not contact:
        return False

    # 4. Affinity threshold check (>= 100: Friend / Crush tier unlocks romance route)
    score = contact.get("relationship_score", 0)
    if score < 100:
        return False

    # 5. Track & Romance Status Check: Must currently be platonic and not already romantically involved
    track = str(contact.get("track", "platonic")).lower().strip()
    if track == "romantic":
        return False

    relations = contact.get("relations") or {}
    romance = relations.get("romance") or {}
    rom_status = str(romance.get("status") or "").lower().strip()
    if rom_status in ("in a relationship", "dating", "married", "engaged", "lovers", "partnered"):
        return False

    current_partner = romance.get("current_partner")
    if current_partner and isinstance(current_partner, dict) and current_partner.get("name"):
        return False

    mems = contact.get("intimate_memories", [])
    if any("start a relationship" in str(m).lower() or "confessed feelings" in str(m).lower() or "agreed to date" in str(m).lower() for m in mems):
        return False

    # 6. Gender & Orientation compatibility
    char = (db.get_character_by_id(character_id) or db.get_character(character_id)) if character_id else None
    char_gen = char.get("gender", "") if char else ""
    npc_gen = contact.get("gender", "")
    npc_prefs = contact.get("preferences", [])
    if not is_gender_and_orientation_compatible(char_gen, npc_gen, npc_prefs):
        return False

    return True


def get_recruitment_cost(affinity: int, level: int = 1) -> int:
    """
    Calculates the gold cost to recruit an NPC into the party in combat scenarios.
    - Affinity >= 100 (Friend+): 0 gold (joins out of loyalty).
    - Affinity = 50 (Acquaintance): 50% of base mercenary contract cost.
    - Affinity <= 0 (Stranger): Full base mercenary contract cost.
    Formula: Base Cost * max(0, 1 - Affinity / 100)
    Base cost scales moderately with party level: 200 + max(1, level) * 50
    """
    if affinity >= 100:
        return 0
    base_cost = 200 + max(1, level) * 50
    affinity_factor = max(0.0, 1.0 - (max(0, affinity) / 100.0))
    return int(base_cost * affinity_factor)



