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
    session_id: int = 0,
    social_role_type: str = ""
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
    if isinstance(name, dict):
        d = name
        name = str(d.get("name", ""))
        role = role or str(d.get("role", ""))
        description = description or str(d.get("description", "") or d.get("notes", "") or d.get("background", ""))
        scenario = scenario if scenario != "fantasy" else str(d.get("scenario", scenario))
        disposition = disposition or str(d.get("disposition", ""))
        social_role_type = social_role_type or str(d.get("social_role_type", ""))

    import namegen
    if namegen.is_collective_entity_name(name) or namegen.is_generic_role_name(name):
        return False

    import scenario_data
    is_hs = scenario_data.has_tag(scenario, "high_school")
    
    if is_hs:
        # Priority 1: Deterministic Enum Check
        srt_clean = str(social_role_type or "").lower().strip()
        if srt_clean in ("faculty_staff", "adult_service", "family_relative", "parent"):
            return False
        if srt_clean in ("student_peer", "peer", "contemporary", "classmate"):
            return True

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
                            srt = n.get("social_role_type")
                            if srt:
                                srt_low = str(srt).lower().strip()
                                if srt_low in ("faculty_staff", "adult_service", "family_relative", "parent"):
                                    return False
                                if srt_low in ("student_peer", "peer", "contemporary"):
                                    return True
                            break
                c = db.get_contact(session_id, name)
                if c:
                    is_existing_contact = True
                    b_inf = c.get("basic_info", {}) or {}
                    role = role or b_inf.get("role", "")
                    description = description or b_inf.get("description", "")
                    grade = grade or b_inf.get("grade", "")
                    club = club or b_inf.get("club", "")
                    srt = b_inf.get("social_role_type")
                    if srt:
                        srt_low = str(srt).lower().strip()
                        if srt_low in ("faculty_staff", "adult_service", "family_relative", "parent"):
                            return False
                        if srt_low in ("student_peer", "peer", "contemporary"):
                            return True
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

        role_text = f"{name} {role} {grade} {club}".strip().lower()
        combined_text = f"{role_text} {description}".strip().lower()
        
        # 1. Check for adult/faculty/service markers
        has_non_peer_signal = any(rx.search(role_text) for rx in _NON_PEER_HIGH_SCHOOL_RE)
        
        # 2. Check for explicit student peer markers
        has_peer_signal = any(rx.search(role_text) for rx in _PEER_HIGH_SCHOOL_RE) or any(rx.search(combined_text) for rx in _PEER_HIGH_SCHOOL_RE)

        if has_non_peer_signal:
            # Student Council / Class Rep / Club leaders are always recognized as peers
            if "student council" in role_text or "class representative" in role_text or "class rep" in role_text:
                return True
            if has_peer_signal:
                # If adult authority keywords (teacher, principal, parent, clerk, nurse, janitor, mr./mrs.) are present in role, it's adult
                from game_engine.matching import matches_keyword_boundary
                if matches_keyword_boundary(role_text, ("teacher", "professor", "principal", "parent", "mother", "father", "dad", "mom", "clerk", "cashier", "nurse", "janitor", "headmaster", "dean", "mr.", "mrs.", "dr.", "madame", "faculty")):
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
                                     max_items: int = 4, only_present_or_mentioned: bool = False) -> str:
    """
    Format active session contacts into a clear, compact context prompt block for LLMs
    using a 3-tier priority filter (Scene NPCs > Mentioned NPCs > Top Standings).
    If only_present_or_mentioned is True, Tier 3 (unrelated absent contacts) is skipped.
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

    # Tier 3: Top highest/lowest relationship standings (only if not restricted to present/mentioned)
    if not only_present_or_mentioned:
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

    session_id = contact.get("session_id", 0)
    if session_id:
        try:
            import mechanics.social.relationship_graph as rg
            c_key = rg.canonical_person_key(contact.get("name", ""))
            partner = rg.get_current_partner(session_id, c_key)
            if partner:
                return False
        except Exception:
            pass

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


def is_unlocked_contact(contact: dict, party_names: set[str] = None) -> bool:
    """
    Determines whether a contact record is eligible to be displayed in the player's
    Contacts List (World Codex Contacts tab and Smartphone Line Messenger).
    
    Strict Rule: Only Friends (relationship_score >= 100), active party members,
    or explicitly added contacts (bypassing affinity via phone contact skillcheck) are included.
    Strangers and acquaintances remain in Lorebook / scene only.
    """
    if not contact or not isinstance(contact, dict):
        return False
    score = int(contact.get("relationship_score", 0) or 0)
    if score >= 100:
        return True
    c_name = (contact.get("name") or "").strip().lower()
    if party_names and c_name in party_names:
        return True
    b_info = contact.get("basic_info") or {}
    if isinstance(b_info, str):
        try:
            import json
            b_info = json.loads(b_info)
        except Exception:
            b_info = {}
    if b_info.get("contact_added") or b_info.get("is_contact") or contact.get("contact_added"):
        return True
    return False


def calculate_contact_exchange_dc(target_npc_data: dict, scenario: str = "default") -> int:
    """
    Calculates the skill check difficulty (DC) for asking a non-friend character for their
    phone number / contact info in modern scenarios with smartphone mechanics.
    
    Default base: 16 (very difficult check for random strangers).
    Modified by character traits and intimate openness:
    - Shameless / Flirty / Outgoing / Bold characters are more open to giving strangers their contact (-2 to -4 DC).
    - Shy / Reserved / Cautious / Tsundere / Guarded characters are more reluctant (+2 to +4 DC).
    - Intimate openness: 'shameless' / 'high' reduces DC (-2); 'chaste' / 'low' increases DC (+2).
    Clamped strictly between 11 and 20.
    """
    base_dc = 16
    if not target_npc_data or not isinstance(target_npc_data, dict):
        return base_dc

    traits = [str(t).lower() for t in (target_npc_data.get("traits") or target_npc_data.get("unlocked_traits") or [])]
    b_inf = target_npc_data.get("basic_info") or {}
    if isinstance(b_inf, str):
        try:
            import json
            b_inf = json.loads(b_inf)
        except Exception:
            b_inf = {}
    desc = str(target_npc_data.get("description") or b_inf.get("description", "")).lower()
    mannerisms = str(target_npc_data.get("mannerisms") or b_inf.get("mannerisms", "")).lower()
    app = target_npc_data.get("appearance") or {}
    if isinstance(app, str):
        try:
            import json
            app = json.loads(app)
        except Exception:
            app = {}

    all_text = " ".join(traits) + " " + desc + " " + mannerisms

    # Positive modifiers (open, shameless, extrovert, flirty, popular)
    open_keywords = ("shameless", "flirty", "outgoing", "extrovert", "popular", "bold", "daring", "charismatic", "playful", "teasing", "free-spirited")
    if any(k in all_text for k in open_keywords):
        base_dc -= 2
        # Strongly shameless / flirty gets extra reduction
        if any(k in all_text for k in ("shameless", "very flirty", "promiscuous", "wild")):
            base_dc -= 2

    # Negative modifiers (shy, guarded, reserved, tsundere, cautious)
    guarded_keywords = ("shy", "reserved", "cautious", "tsundere", "guarded", "introvert", "conservative", "strict", "disciplined", "aloof", "prickly", "distrustful")
    if any(k in all_text for k in guarded_keywords):
        base_dc += 2
        if any(k in all_text for k in ("tsundere", "deeply distrustful", "extremely shy", "paranoid")):
            base_dc += 2

    # Intimate openness modifier
    erotic_openness = str(app.get("erotic_openness") or app.get("openness") or "").lower()
    if any(k in erotic_openness for k in ("shameless", "high", "very open", "adventurous", "uninhibited")):
        base_dc -= 2
    elif any(k in erotic_openness for k in ("chaste", "low", "very guarded", "modest", "prude", "sheltered")):
        base_dc += 2

    demeanor = str(app.get("intimate_demeanor") or app.get("demeanor") or "").lower()
    if any(k in demeanor for k in ("forward", "teasing", "bold", "shameless")):
        base_dc -= 1
    elif any(k in demeanor for k in ("tsundere", "haughty", "guarded", "defensive", "cold")):
        base_dc += 2

    return max(11, min(20, base_dc))


def enrich_contact_dossier(
    c_raw: dict,
    session_id: int,
    scen_key: str,
    debug_reveal_all: bool = False,
    phys_st: dict | None = None,
) -> dict:
    """Shared deterministic NPC Contact Dossier enrichment for both Web Codex/Phone and Discord embeds."""
    import mechanics.social.persona
    import mechanics.social.genealogy
    from mechanics.social.persona import (
        infer_contact_gender,
        clean_attribute_list_string,
        enforce_intimacy_safeguard_invariants,
        is_romantic_milestone_str,
    )
    from mechanics.social.persona.intimacy.appearance import normalize_appearance
    from mechanics.social.persona.intimacy.formatting import format_intimate_profile_sections
    from scenario_data import is_nsfw_scenario

    c = dict(c_raw)
    score = int(c.get("relationship_score", 0) or 0)
    if debug_reveal_all:
        info_level = 3
    elif hasattr(mechanics.social.persona, "get_contact_info_level"):
        info_level = mechanics.social.persona.get_contact_info_level(c)
    else:
        info_level = get_unlocked_info_level(score)

    c_gender = infer_contact_gender(c) or str(c.get("gender") or (c.get("basic_info") or {}).get("gender") or "female")
    c_basic = c.get("basic_info") or {}
    c_race = str(c.get("race") or c_basic.get("race") or (c.get("appearance") or {}).get("race") or "")
    c_desc = c_basic.get("description", "")
    if isinstance(c_desc, dict):
        c_desc = " ".join(str(v) for v in c_desc.values() if v)
    c_traits = list(c.get("unlocked_traits", [])) or list(c.get("traits", []))
    c_role = str(c_basic.get("role") or c_basic.get("occupation") or c.get("role") or "")

    raw_prefs = c.get("preferences") or []
    if not c_traits or not raw_prefs:
        try:
            gen_traits, gen_prefs = mechanics.social.persona.split_traits_and_preferences(
                c_traits, raw_prefs,
                role=c_role, race=c_race or "human", seed_str=f"{c.get('name')}_{c_desc}"
            )
            if not c_traits:
                c_traits = gen_traits
                c["unlocked_traits"] = gen_traits
                c["traits"] = gen_traits
            if not raw_prefs:
                raw_prefs = gen_prefs
                c["preferences"] = gen_prefs
        except Exception:
            pass

    skill_modifier = get_relationship_modifier(score)
    dislikes = c.get("dislikes")
    clean_likes = None
    try:
        cat_likes, cat_dislikes = mechanics.social.persona.categorize_likes_and_dislikes(
            raw_prefs, traits=c_traits
        )
        if not dislikes and cat_dislikes:
            dislikes = cat_dislikes
        if cat_likes:
            clean_likes = cat_likes
    except Exception:
        pass

    if dislikes:
        dislike_set = {str(d).lower().strip() for d in dislikes}
        if clean_likes:
            c["preferences"] = [l for l in clean_likes if str(l).lower().strip() not in dislike_set]
        else:
            c["preferences"] = [p for p in raw_prefs if str(p).lower().strip() not in dislike_set]
    elif clean_likes:
        c["preferences"] = clean_likes

    # 1. Synchronize & format Relations, Romantic Standing, and Family Tree
    try:
        relations = mechanics.social.genealogy.ensure_contact_relations(
            c, session_id=session_id, scenario=scen_key
        )
    except Exception:
        relations = c.get("relations") if isinstance(c.get("relations"), dict) else {}

    try:
        disclosed_relations = mechanics.social.genealogy.format_relations_for_disclosure(
            relations, info_level=info_level, debug_reveal=debug_reveal_all
        )
    except Exception:
        disclosed_relations = {}

    c["relations"] = relations
    c["disclosed_relations"] = disclosed_relations
    if relations.get("household_id"):
        c["household_id"] = relations["household_id"]
    if relations.get("residence_location"):
        c["residence_location"] = relations["residence_location"]
    family_tree = relations.get("family") or c.get("family_tree") or []
    c["family_tree"] = family_tree

    raw_app = dict(c.get("appearance") or {})
    raw_app["intimate_memories"] = list(c.get("intimate_memories", []))
    c_name = str(c.get("name") or c_basic.get("name") or "").strip()
    app = normalize_appearance(
        raw_app,
        gender=c_gender,
        race=c_race or "human",
        scen_key=scen_key,
        desc=c_desc,
        traits=c_traits,
        role=c_role,
        name=c_name
    )
    app["intimate_memories"] = list(c.get("intimate_memories", []))
    app = enforce_intimacy_safeguard_invariants(app, gender=c_gender)

    i_exp_val = str(app.get("intercourse_experience") or app.get("virginity_intercourse") or "virgin").strip().lower()
    o_exp_val = str(app.get("oral_experience") or app.get("virginity_oral") or "inexperienced").strip().lower()
    m_exp_val = str(app.get("manual_experience") or app.get("virginity_manual") or "inexperienced").strip().lower()
    a_exp_val = str(app.get("anal_experience") or app.get("virginity_anal") or "inexperienced").strip().lower()

    had_first_time = bool(app.get("had_first_time_with_player")) and (i_exp_val == "non_virgin")
    past_history = c.get("past_intimate_history") or app.get("past_intimate_history") or app.get("past_intimate_entries")
    if not past_history and c.get("intimate_memories"):
        past_mems = [str(m).replace("Past History:", "").strip() for m in c.get("intimate_memories") if str(m).startswith("Past History:")]
        if past_mems:
            past_history = past_mems

    is_virgin_shared = False
    if isinstance(past_history, list) and past_history:
        is_virgin_shared = any("shared first time with you" in str(p) for p in past_history)
    elif isinstance(past_history, str):
        is_virgin_shared = "shared first time with you" in past_history

    has_oral_exp = o_exp_val in ("has_done_oral", "has_received_oral", "has_done_and_received_oral")
    has_anal_exp = a_exp_val in ("has_done_anal", "has_received_anal", "has_done_and_received_anal")
    past_str = " ".join(past_history) if isinstance(past_history, list) else str(past_history or "")
    im_mems = c.get("intimate_memories") or []
    im_str = " ".join(str(m) for m in im_mems)
    is_out_of_sync = bool(
        (past_history or im_mems)
        and not had_first_time
        and (
            (has_oral_exp and ("oral" not in past_str.lower() or "oral" not in im_str.lower()))
            or (has_anal_exp and ("anal" not in past_str.lower() or "anal" not in im_str.lower()))
        )
    )

    if had_first_time:
        past_history = ["Virgin (No prior intimate history before meeting you; shared first time with you)"]
    elif not past_history or is_out_of_sync or (is_virgin_shared and not had_first_time):
        try:
            name_str = str(c.get("name") or c.get("npc_id") or "npc").strip()
            import hashlib
            hash_val = int(hashlib.md5(f"{name_str}_past_history".encode("utf-8")).hexdigest(), 16)
            c_race_val = str(c.get("race") or app.get("race") or "")
            c_gender_val = str(c.get("gender") or app.get("gender") or "female")
            open_val = str(app.get("erotic_openness") or app.get("openness") or "moderate")
            pred_i = str(app.get("predetermined_intercourse") or "").strip().lower()

            if (i_exp_val in ("virgin", "inexperienced", "") or pred_i == "virgin") and o_exp_val in ("inexperienced", "unknown", "") and m_exp_val in ("inexperienced", "unknown", "") and a_exp_val in ("inexperienced", "unknown", ""):
                past_history = ["Virgin (No prior intimate history before meeting you)"]
            else:
                has_existing_partner = bool(
                    c.get("relations", {}).get("current_partner")
                    or (c.get("disclosed_relations") or {}).get("current_partner")
                )
                past_data = mechanics.social.persona.generate_past_intimate_history(
                    hash_val=hash_val,
                    race=c_race_val,
                    gender=c_gender_val,
                    scenario=scen_key,
                    openness=open_val,
                    intercourse=i_exp_val,
                    oral=o_exp_val,
                    manual=m_exp_val,
                    anal=a_exp_val,
                    has_existing_partner=has_existing_partner,
                )
                if past_data and past_data.get("entries"):
                    past_history = [str(e).replace("Past History:", "").strip() for e in past_data["entries"]]
                elif past_data and past_data.get("entry"):
                    past_history = [str(past_data["entry"]).replace("Past History:", "").strip()]
                else:
                    past_history = []

                if past_history:
                    try:
                        import db as _db
                        sess_id = c.get("session_id", 0)
                        char_id = c.get("character_id", 0)
                        npc_id = c.get("npc_id") or name_str

                        if is_out_of_sync and c.get("id"):
                            import json as _json
                            with _db.get_conn() as conn:
                                row = conn.execute("SELECT intimate_memories_json, appearance_json FROM contacts WHERE id = ?", (c.get("id"),)).fetchone()
                                if row:
                                    cur_mems = _json.loads(row[0] or "[]")
                                    cur_app = _json.loads(row[1] or "{}")
                                    clean_mems = [m for m in cur_mems if not str(m).startswith("Past History:")]
                                    new_mems = [f"Past History: {e}" for e in past_history] + clean_mems
                                    if "intimate_memories" in cur_app:
                                        cur_app["intimate_memories"] = new_mems
                                    if "shared_romantic_milestones" in cur_app:
                                        srm = [m for m in cur_app.get("shared_romantic_milestones", []) if not str(m).startswith("Past History:")]
                                        cur_app["shared_romantic_milestones"] = [f"Past History: {e}" for e in past_history] + srm
                                    conn.execute(
                                        "UPDATE contacts SET intimate_memories_json = ?, appearance_json = ? WHERE id = ?",
                                        (_json.dumps(new_mems), _json.dumps(cur_app), c.get("id"))
                                    )
                        else:
                            for ph_entry in past_history:
                                mem_str = f"Past History: {ph_entry}"
                                _db.upsert_contact(
                                    session_id=sess_id,
                                    character_id=char_id,
                                    npc_id=npc_id,
                                    name=name_str,
                                    new_memory=mem_str,
                                )
                    except Exception:
                        pass
        except Exception:
            past_history = []

    # 3. Enrich appearance & Intimate Dossier for Web Codex / Phone display
    intimate_unlocked = (info_level >= 3) or debug_reveal_all or c.get("intimate_revealed", False) or c.get("all_revealed", False) or app.get("intimate_revealed", False)
    i_rev = intimate_unlocked or debug_reveal_all or c.get("intercourse_revealed", False) or app.get("intercourse_revealed", False)
    o_rev = intimate_unlocked or debug_reveal_all or c.get("oral_revealed", False) or app.get("oral_revealed", False) or i_rev
    m_rev = intimate_unlocked or debug_reveal_all or c.get("manual_revealed", False) or app.get("manual_revealed", False) or i_rev

    revealed_flags = {
        "intimate_revealed": intimate_unlocked,
        "all_revealed": intimate_unlocked or debug_reveal_all,
        "mannerisms_revealed": intimate_unlocked or (info_level >= 1) or debug_reveal_all,
        "intercourse_revealed": i_rev,
        "oral_revealed": o_rev,
        "manual_revealed": m_rev,
        "demeanor_revealed": intimate_unlocked or debug_reveal_all or c.get("demeanor_revealed", False) or app.get("demeanor_revealed", False),
        "dynamic_revealed": intimate_unlocked or debug_reveal_all or c.get("dynamic_revealed", False) or app.get("dynamic_revealed", False),
        "openness_revealed": intimate_unlocked or debug_reveal_all or c.get("openness_revealed", False) or app.get("openness_revealed", False),
        "sensitive_spots_revealed": intimate_unlocked or debug_reveal_all or c.get("sensitive_spots_revealed", False) or app.get("sensitive_spots_revealed", False),
        "turn_ons_revealed": intimate_unlocked or debug_reveal_all or c.get("turn_ons_revealed", False) or app.get("turn_ons_revealed", False),
        "turn_offs_revealed": intimate_unlocked or debug_reveal_all or c.get("turn_offs_revealed", False) or app.get("turn_offs_revealed", False),
        "fetishes_revealed": intimate_unlocked or debug_reveal_all or c.get("fetishes_revealed", False) or app.get("fetishes_revealed", False),
        "underwear_revealed": intimate_unlocked or debug_reveal_all or c.get("underwear_revealed", False) or app.get("underwear_revealed", False),
        "act_preferences_revealed": intimate_unlocked or debug_reveal_all or c.get("act_preferences_revealed", False) or app.get("act_preferences_revealed", False),
    }

    prof = c.get("intimate_profile") if isinstance(c.get("intimate_profile"), dict) else {}
    prof_tracks = prof.get("tracks") if isinstance(prof.get("tracks"), dict) else {}

    try:
        intimate_sections = format_intimate_profile_sections(
            app,
            gender=c_gender,
            race=c_race or "human",
            scen_key=scen_key,
            info_level=info_level,
            revealed_flags=revealed_flags,
            intimate_profile=prof
        )
    except Exception:
        intimate_sections = {}
    c["intimate_sections"] = intimate_sections

    i_state = str(prof_tracks.get("intercourse") or app.get("intercourse_experience") or "virgin").strip().lower()
    exp_disp = ("Virgin" if i_state == "virgin" else "Non-Virgin") if i_rev else "Unknown"
    app["experience"] = exp_disp if i_rev else ""

    raw_g = str(c.get("gender") or app.get("gender") or "female").strip().lower()
    is_male = any(kw in raw_g for kw in ("male", "man", "boy", "lord", "he", "him", "his")) and not any(kw in raw_g for kw in ("female", "woman"))

    oral_state = str(prof_tracks.get("oral") or app.get("oral_experience") or "unknown").strip().lower()
    oral_map = {
        "inexperienced": "Inexperienced",
        "has_done_oral": "Has Performed",
        "has_received_oral": "Has Received",
        "has_done_and_received_oral": "Has Performed & Received"
    }
    oral_disp = "Unknown"
    if o_rev and oral_state != "unknown":
        oral_disp = oral_map.get(oral_state, "Inexperienced")

    manual_state = str(prof_tracks.get("manual") or app.get("manual_experience") or "unknown").strip().lower()
    man_map = {
        "inexperienced": "Inexperienced",
        "has_done_manual": "Has Given",
        "has_received_manual": "Has Received",
        "has_done_and_received_manual": "Has Given & Received"
    }
    man_disp = "Unknown"
    if m_rev and manual_state != "unknown":
        man_disp = man_map.get(manual_state, "Inexperienced")

    anal_state = str(prof_tracks.get("anal") or app.get("anal_experience") or "unknown").strip().lower()
    anal_map = {
        "inexperienced": "Inexperienced",
        "has_done_anal": "Has Given",
        "has_received_anal": "Has Received",
        "has_done_and_received_anal": "Has Given & Received"
    }
    a_rev = intimate_unlocked or debug_reveal_all or c.get("anal_revealed", False) or app.get("anal_revealed", False)
    anal_disp = "Unknown"
    if a_rev and anal_state != "unknown":
        anal_disp = anal_map.get(anal_state, "Inexperienced")

    if is_male:
        p_size = str(app.get("penis_size") or "average").title()
        p_size_disp = p_size if (intimate_unlocked or debug_reveal_all) else "Unknown"
        app["anatomy"] = f"Penis Size: {p_size_disp} • Intercourse: {exp_disp} • Oral: {oral_disp} • Manual: {man_disp} • Anal: {anal_disp}"
    else:
        b_size = str(app.get("breast_size") or "Modest B-Cup").title()
        b_size_disp = b_size
        app["anatomy"] = f"Breast Size: {b_size_disp} • Intercourse: {exp_disp} • Oral: {oral_disp} • Manual: {man_disp} • Anal: {anal_disp}"

    if isinstance(app.get("undergarments"), dict):
        under_d = app.get("undergarments")
        bra_str = under_d.get("bra", "")
        und_str = under_d.get("underwear", "")
        if bra_str and und_str:
            app["undergarments"] = f"Bra: {bra_str} • Underwear: {und_str}"
        elif bra_str:
            app["undergarments"] = f"Bra: {bra_str}"
        elif und_str:
            app["undergarments"] = f"Underwear: {und_str}"
    elif not app.get("undergarments") and (app.get("bra") or app.get("underwear")):
        bra_str = app.get("bra", "")
        und_str = app.get("underwear", "")
        if bra_str and und_str:
            app["undergarments"] = f"Bra: {bra_str} • Underwear: {und_str}"
        elif bra_str:
            app["undergarments"] = f"Bra: {bra_str}"
        elif und_str:
            app["undergarments"] = f"Underwear: {und_str}"

    t_rev = intimate_unlocked or debug_reveal_all or c.get("turn_ons_revealed", False) or app.get("turn_ons_revealed", False)
    if not t_rev:
        app["turn_ons"] = []
    else:
        t_cleaned = clean_attribute_list_string(app.get("turn_ons"))
        if t_cleaned:
            app["turn_ons"] = [t.strip() for t in t_cleaned.split(",") if t.strip() and t.strip().lower() not in ("none", "unknown")]

    s_rev = intimate_unlocked or debug_reveal_all or c.get("sensitive_spots_revealed", False) or app.get("sensitive_spots_revealed", False)
    if not s_rev:
        app["erogenous_zones"] = []
        app["sensitive_spots"] = ""
    else:
        s_cleaned = clean_attribute_list_string(app.get("sensitive_spots"))
        if s_cleaned:
            app["erogenous_zones"] = [s.strip() for s in s_cleaned.split(",") if s.strip() and s.strip().lower() not in ("none", "unknown")]
        elif not app.get("erogenous_zones") and app.get("sensitive_spots"):
            app["erogenous_zones"] = list(app.get("sensitive_spots"))

    f_rev = intimate_unlocked or debug_reveal_all or c.get("fetishes_revealed", False) or app.get("fetishes_revealed", False)
    if not f_rev:
        app["kinks"] = []
        app["fetishes"] = ""
    else:
        f_cleaned = clean_attribute_list_string(app.get("fetishes") or app.get("kinks"))
        if f_cleaned and f_cleaned.lower() not in ("none", "none (vanilla)", "unknown", ""):
            app["kinks"] = [f.strip() for f in f_cleaned.split(",") if f.strip() and f.strip().lower() not in ("none", "none (vanilla)", "unknown")]

    pref_rev = intimate_unlocked or debug_reveal_all or c.get("act_preferences_revealed", False) or app.get("act_preferences_revealed", False)
    if not pref_rev:
        app["favorite_acts"] = []
        app["act_likes"] = ""
        app["disliked_acts"] = []
        app["act_dislikes"] = ""
    else:
        likes_cleaned = clean_attribute_list_string(app.get("act_likes") or app.get("favorite_acts"))
        if likes_cleaned and likes_cleaned.lower() not in ("none", "unknown", ""):
            app["favorite_acts"] = [l.strip() for l in likes_cleaned.split(",") if l.strip() and l.strip().lower() not in ("none", "unknown")]

        dislikes_cleaned = clean_attribute_list_string(app.get("act_dislikes") or app.get("disliked_acts"))
        if dislikes_cleaned and dislikes_cleaned.lower() not in ("none", "unknown", ""):
            app["disliked_acts"] = [d.strip() for d in dislikes_cleaned.split(",") if d.strip() and d.strip().lower() not in ("none", "unknown")]

    c["appearance"] = app
    c["info_level"] = info_level
    c["skill_modifier"] = skill_modifier
    c["dislikes"] = dislikes or []
    c["debug_revealed"] = debug_reveal_all
    history_unlocked = intimate_unlocked or (info_level >= 2) or debug_reveal_all or c.get("history_revealed", False) or app.get("history_revealed", False)
    if history_unlocked:
        if isinstance(past_history, list):
            c["past_intimate_history"] = " • ".join(past_history)
            c["past_intimate_entries"] = past_history
        else:
            c["past_intimate_history"] = str(past_history or "")
            c["past_intimate_entries"] = [str(past_history)] if past_history else []
    else:
        c["past_intimate_history"] = ""
        c["past_intimate_entries"] = []

    raw_mems = list(c.get("intimate_memories") or app.get("intimate_memories") or [])
    c["shared_romantic_milestones"] = [
        m for m in raw_mems if not str(m).startswith("Past History:") and is_romantic_milestone_str(str(m))
    ]
    recent_mems = list(c.get("recent_memories") or c.get("rel_history") or app.get("recent_memories") or [])
    if not recent_mems:
        recent_mems = [
            m for m in raw_mems if not str(m).startswith("Past History:") and not is_romantic_milestone_str(str(m))
        ]
    c["is_nsfw"] = is_nsfw_scenario(scen_key)
    c["recent_memories"] = recent_mems

    try:
        from mechanics.social.physical_state import compute_clothing_summary_badge, _match_actor_key
        phys_actors = (phys_st.get("actors") or {}) if isinstance(phys_st, dict) else {}
        c_name_str = str(c.get("name") or "").strip()
        m_act_key = _match_actor_key(c_name_str, phys_actors) if c_name_str else ""
        n_act_data = phys_actors.get(m_act_key) or {}
        c["clothing_status"] = compute_clothing_summary_badge(n_act_data.get("clothing"), gender=c_gender)
    except Exception:
        c.setdefault("clothing_status", "Fully Clothed 👕")

    raw_effs = c.get("status_effects") or (c.get("basic_info") or {}).get("status_effects") or []
    if isinstance(raw_effs, list):
        c["status_effects"] = [
            str(s).strip()
            for s in raw_effs
            if str(s).strip() and str(s).strip().lower() not in ("[]", "{}", '""', "''", "none", "null")
        ]
    else:
        c["status_effects"] = []

    try:
        debug_rev_flags = {k: True for k in revealed_flags}
        debug_int_sections = format_intimate_profile_sections(
            app,
            gender=c_gender,
            race=c_race or "human",
            scen_key=scen_key,
            info_level=3,
            revealed_flags=debug_rev_flags
        )
    except Exception:
        debug_int_sections = {}

    try:
        debug_disclosed_rel = mechanics.social.genealogy.format_relations_for_disclosure(
            relations, info_level=3, debug_reveal=True
        )
    except Exception:
        debug_disclosed_rel = {}

    debug_app = dict(app)
    if is_male:
        p_sz = str(app.get("penis_size") or "average").title()
        debug_app["anatomy"] = f"Penis Size: {p_sz} • Intercourse: {exp_disp if exp_disp != 'Unknown' else ('Virgin' if i_state == 'virgin' else 'Non-Virgin')} • Oral: {oral_map.get(oral_state, 'Inexperienced')} • Manual: {man_map.get(manual_state, 'Inexperienced')}"
    else:
        b_sz = str(app.get("breast_size") or "Modest B-Cup").title()
        debug_app["anatomy"] = f"Breast Size: {b_sz} • Intercourse: {exp_disp if exp_disp != 'Unknown' else ('Virgin' if i_state == 'virgin' else 'Non-Virgin')} • Oral: {oral_map.get(oral_state, 'Inexperienced')} • Manual: {man_map.get(manual_state, 'Inexperienced')}"

    c["debug_profile"] = {
        "unlocked_traits": c.get("unlocked_traits") or [],
        "preferences": clean_likes or raw_prefs or [],
        "dislikes": dislikes or [],
        "family_tree": family_tree or [],
        "relations": relations or {},
        "disclosed_relations": debug_disclosed_rel or {},
        "intimate_sections": debug_int_sections or {},
        "appearance": debug_app,
        "past_intimate_history": " • ".join(past_history) if isinstance(past_history, list) else str(past_history or ""),
        "past_intimate_entries": past_history if isinstance(past_history, list) else ([str(past_history)] if past_history else []),
        "shared_romantic_milestones": c.get("shared_romantic_milestones") or [],
        "recent_memories": c.get("recent_memories") or [],
        "info_level": 3,
        "debug_revealed": True,
    }
    return c



