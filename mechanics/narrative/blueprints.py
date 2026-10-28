"""
Hikayat - Mechanical Blueprint Registry & Item Matcher
Maps 55+ cross-genre narrative archetypes into 10 deterministic mechanical blueprints.
Handles item parsing, quantity tracking, equipped-item safety, and spatial whitelists.
"""
from __future__ import annotations

import re
from typing import Optional, Any

# -----------------------------------------------------------------------------
# 1. Ten Canonical Mechanical Blueprints
# -----------------------------------------------------------------------------
BLUEPRINT_DEFINITIONS = {
    "INVESTIGATION": {
        "id": "INVESTIGATION",
        "name": "Investigation & Sleuthing",
        "description": "Gather physical clues, interrogate witnesses, synthesize deduction breakthrough, and confront the truth.",
        "single_site_allowed": False,
        "default_triggers": ["arrival", "skill_check", "skill_check"],
    },
    "ACQUISITION": {
        "id": "ACQUISITION",
        "name": "Acquisition & Delivery",
        "description": "Locate, harvest, or craft required items, then deliver/turn them in to a named client NPC.",
        "single_site_allowed": False,
        "default_triggers": ["arrival", "skill_check", "skill_check"],
        "supports_inventory_pre_completion": True,
        "consumes_item_on_delivery": True,
    },
    "NEUTRALIZATION": {
        "id": "NEUTRALIZATION",
        "name": "Neutralization & Hunting",
        "description": "Track, corner, and eliminate, capture, or spare/fake-death a dangerous target.",
        "single_site_allowed": False,
        "default_triggers": ["arrival", "skill_check", "skill_check"],
    },
    "HEIST_INFILTRATION": {
        "id": "HEIST_INFILTRATION",
        "name": "Heist & Infiltration",
        "description": "Scout security perimeters, bypass physical/digital barriers, retrieve or plant payload, and exfiltrate.",
        "single_site_allowed": False,
        "default_triggers": ["arrival", "skill_check", "skill_check"],
    },
    "SOCIAL_MANIPULATION": {
        "id": "SOCIAL_MANIPULATION",
        "name": "Social Influence & Diplomacy",
        "description": "Discover leverage, navigate faction politics, persuade, blackmail, matchmake, or negotiate treaties.",
        "single_site_allowed": False,
        "default_triggers": ["arrival", "skill_check", "skill_check"],
    },
    "ESCORT_RESCUE": {
        "id": "ESCORT_RESCUE",
        "name": "Escort & Rescue",
        "description": "Locate trapped VIP or asset, break containment or overcome ambush, and escort safely to destination.",
        "single_site_allowed": False,
        "default_triggers": ["arrival", "skill_check", "skill_check"],
    },
    "CONTEST_RIVALRY": {
        "id": "CONTEST_RIVALRY",
        "name": "Contest & Rivalry",
        "description": "Prepare, scout opponent, qualify for arena or match, and face rival in decisive structured showdown.",
        "single_site_allowed": False,
        "default_triggers": ["arrival", "skill_check", "skill_check"],
    },
    "SITE_DEFENSE_RITUAL": {
        "id": "SITE_DEFENSE_RITUAL",
        "name": "Site Defense & Arcane Ritual",
        "description": "Prepare stationary defenses, repel waves of attackers or channel sealing runes, and stabilize the site.",
        "single_site_allowed": True,  # Stationary whitelist!
        "default_triggers": ["arrival", "skill_check", "skill_check"],
    },
    "EXPLORATION_HAZARD": {
        "id": "EXPLORATION_HAZARD",
        "name": "Hazard Exploration & Mapping",
        "description": "Trek into uncharted or contaminated anomalies, survey waypoints, survive environmental hazards, and map nodes.",
        "single_site_allowed": False,
        "default_triggers": ["arrival", "skill_check", "skill_check"],
    },
    "INTIMATE_ENCOUNTER": {
        "id": "INTIMATE_ENCOUNTER",
        "name": "Intimate Encounter & Courtship",
        "description": "Establish private secluded setting, overcome inhibitions or fulfill romantic/courtship desires, and resolve aftermath.",
        "single_site_allowed": False,
        "default_triggers": ["arrival", "skill_check", "skill_check"],
    },
}

# -----------------------------------------------------------------------------
# 2. Archetype Keyword Mapping (55+ Cross-Genre Archetypes)
# -----------------------------------------------------------------------------
ARCHETYPE_KEYWORD_TO_BLUEPRINT: dict[str, str] = {
    # ACQUISITION (Resource Run, Gathering, Alchemy, Crafting, Off-Campus Errand, Relic Discovery, Tech/Data Extraction, Scavenging, Salvage, Aphrodisiac Brewing, Supply)
    "resource run": "ACQUISITION",
    "gathering": "ACQUISITION",
    "alchemy": "ACQUISITION",
    "crafting": "ACQUISITION",
    "off-campus errand": "ACQUISITION",
    "errand": "ACQUISITION",
    "delivery": "ACQUISITION",
    "courier": "ACQUISITION",
    "relic discovery": "ACQUISITION",
    "tech extraction": "ACQUISITION",
    "data extraction": "ACQUISITION",
    "radiation scavenging": "ACQUISITION",
    "scavenging": "ACQUISITION",
    "salvage": "ACQUISITION",
    "aphrodisiac": "ACQUISITION",
    "supply": "ACQUISITION",
    "resource": "ACQUISITION",

    # NEUTRALIZATION (Assassination, Monster Hunting, Extermination, Bounty Hunting, Mutant Hunt, Elimination, Beast Hunt)
    "assassination": "NEUTRALIZATION",
    "monster hunting": "NEUTRALIZATION",
    "extermination": "NEUTRALIZATION",
    "bounty hunting": "NEUTRALIZATION",
    "mutant hunt": "NEUTRALIZATION",
    "beast hunt": "NEUTRALIZATION",
    "mutant": "NEUTRALIZATION",
    "elimination": "NEUTRALIZATION",
    "neutralization": "NEUTRALIZATION",
    "hunting": "NEUTRALIZATION",
    "hunt": "NEUTRALIZATION",
    "slay": "NEUTRALIZATION",

    # HEIST_INFILTRATION (Campus Infiltration, Infiltration, Exam Heist, Cyberware Heist, Heist, Sabotage, Disruption, Netrunning, Black Market)
    "campus infiltration": "HEIST_INFILTRATION",
    "infiltrate syndicate": "HEIST_INFILTRATION",
    "infiltration": "HEIST_INFILTRATION",
    "infiltrate": "HEIST_INFILTRATION",
    "exam heist": "HEIST_INFILTRATION",
    "cyberware heist": "HEIST_INFILTRATION",
    "heist": "HEIST_INFILTRATION",
    "sabotage": "HEIST_INFILTRATION",
    "disruption": "HEIST_INFILTRATION",
    "netrunning": "HEIST_INFILTRATION",
    "black market": "HEIST_INFILTRATION",
    "theft": "HEIST_INFILTRATION",
    "override": "HEIST_INFILTRATION",

    # SOCIAL_MANIPULATION (Gossip Control, Election Campaigning, Matchmaking, Secret Admirer, Espionage, Blackmail, Arbitration, Tribunal, Diplomacy, Trade Route)
    "gossip control": "SOCIAL_MANIPULATION",
    "gossip": "SOCIAL_MANIPULATION",
    "rumor": "SOCIAL_MANIPULATION",
    "election campaigning": "SOCIAL_MANIPULATION",
    "campaigning": "SOCIAL_MANIPULATION",
    "election": "SOCIAL_MANIPULATION",
    "matchmaking": "SOCIAL_MANIPULATION",
    "secret admirer": "SOCIAL_MANIPULATION",
    "espionage": "SOCIAL_MANIPULATION",
    "blackmail": "SOCIAL_MANIPULATION",
    "arbitration": "SOCIAL_MANIPULATION",
    "tribunal": "SOCIAL_MANIPULATION",
    "diplomacy": "SOCIAL_MANIPULATION",
    "trade route": "SOCIAL_MANIPULATION",
    "faction operation": "SOCIAL_MANIPULATION",

    # ESCORT_RESCUE (Academic Rescue, Convoy Escort, Find Person, Rescue, Escort, Beast Taming, Familiar Binding)
    "academic rescue": "ESCORT_RESCUE",
    "convoy escort": "ESCORT_RESCUE",
    "convoy": "ESCORT_RESCUE",
    "find person": "ESCORT_RESCUE",
    "rescue": "ESCORT_RESCUE",
    "escort": "ESCORT_RESCUE",
    "beast taming": "ESCORT_RESCUE",
    "familiar binding": "ESCORT_RESCUE",
    "familiar": "ESCORT_RESCUE",

    # CONTEST_RIVALRY (Honor Duel, Club Showdown, Arcade Rivalry, Duel)
    "honor duel": "CONTEST_RIVALRY",
    "duel": "CONTEST_RIVALRY",
    "club showdown": "CONTEST_RIVALRY",
    "club": "CONTEST_RIVALRY",
    "showdown": "CONTEST_RIVALRY",
    "arcade rivalry": "CONTEST_RIVALRY",
    "arcade": "CONTEST_RIVALRY",

    # SITE_DEFENSE_RITUAL (Siege Defense, Survival, Arcane Ritual, Sealing, Rift Cleansing, Cleansing, Holy Exorcism, Exorcism, Rogue AI Containment, Base Fortification, Safe Zone)
    "siege defense": "SITE_DEFENSE_RITUAL",
    "siege": "SITE_DEFENSE_RITUAL",
    "survival": "SITE_DEFENSE_RITUAL",
    "defense": "SITE_DEFENSE_RITUAL",
    "arcane ritual": "SITE_DEFENSE_RITUAL",
    "ritual": "SITE_DEFENSE_RITUAL",
    "sealing": "SITE_DEFENSE_RITUAL",
    "rift cleansing": "SITE_DEFENSE_RITUAL",
    "cleansing": "SITE_DEFENSE_RITUAL",
    "holy exorcism": "SITE_DEFENSE_RITUAL",
    "exorcism": "SITE_DEFENSE_RITUAL",
    "rogue ai containment": "SITE_DEFENSE_RITUAL",
    "rogue ai": "SITE_DEFENSE_RITUAL",
    "base fortification": "SITE_DEFENSE_RITUAL",
    "fortification": "SITE_DEFENSE_RITUAL",
    "safe zone": "SITE_DEFENSE_RITUAL",

    # EXPLORATION_HAZARD (Rune Archaeology, Dungeon Mapping, Derelict Boarding, Toxic Zone, Signal Triangulation, Urban Legend Dare)
    "rune archaeology": "EXPLORATION_HAZARD",
    "archaeology": "EXPLORATION_HAZARD",
    "dungeon mapping": "EXPLORATION_HAZARD",
    "dungeon": "EXPLORATION_HAZARD",
    "derelict boarding": "EXPLORATION_HAZARD",
    "derelict": "EXPLORATION_HAZARD",
    "toxic zone": "EXPLORATION_HAZARD",
    "toxic": "EXPLORATION_HAZARD",
    "radiation": "EXPLORATION_HAZARD",
    "signal triangulation": "EXPLORATION_HAZARD",
    "signal": "EXPLORATION_HAZARD",
    "radio": "EXPLORATION_HAZARD",
    "urban legend dare": "EXPLORATION_HAZARD",
    "urban legend": "EXPLORATION_HAZARD",
    "dare": "EXPLORATION_HAZARD",

    # INTIMATE_ENCOUNTER (NSFW archetypes)
    "seduction": "INTIMATE_ENCOUNTER",
    "allure": "INTIMATE_ENCOUNTER",
    "domination": "INTIMATE_ENCOUNTER",
    "subjugation": "INTIMATE_ENCOUNTER",
    "brothel": "INTIMATE_ENCOUNTER",
    "courtesan": "INTIMATE_ENCOUNTER",
    "lust": "INTIMATE_ENCOUNTER",
    "courtship": "INTIMATE_ENCOUNTER",
    "paramour": "INTIMATE_ENCOUNTER",
    "harem": "INTIMATE_ENCOUNTER",
    "bondage": "INTIMATE_ENCOUNTER",
    "revelry": "INTIMATE_ENCOUNTER",
    "masquerade": "INTIMATE_ENCOUNTER",

    # ANOMALOUS_INCURSIONS (12 Scenario Bounty & Story Archetypes)
    "eliminate hostile anomalous entity": "NEUTRALIZATION",
    "rogue_entity_termination": "NEUTRALIZATION",
    "apocalyptic boss confrontation": "NEUTRALIZATION",
    "secure non-hostile anomalous entity": "ESCORT_RESCUE",
    "non_hostile_entity_pacification": "ESCORT_RESCUE",
    "contain anomalous phenomenon": "SITE_DEFENSE_RITUAL",
    "spatial_rift_sealing": "SITE_DEFENSE_RITUAL",
    "sensory_anomaly_purge": "SITE_DEFENSE_RITUAL",
    "investigate anomalous phenomenon": "INVESTIGATION",
    "temporal_loop_anchor": "INVESTIGATION",
    "find missing person (spirited away)": "ESCORT_RESCUE",
    "spirited away": "ESCORT_RESCUE",
    "missing_agent_rescue": "ESCORT_RESCUE",
    "retrieve altered item / cursed relic": "ACQUISITION",
    "retrieve altered item": "ACQUISITION",
    "cursed relic": "ACQUISITION",
    "cursed_relic_retrieval": "ACQUISITION",
    "disrupt cult ritual / clandestine auction": "HEIST_INFILTRATION",
    "disrupt cult ritual": "HEIST_INFILTRATION",
    "clandestine auction": "HEIST_INFILTRATION",
    "cult_ritual_disruption": "HEIST_INFILTRATION",
    "syndicate_black_market_interception": "HEIST_INFILTRATION",
    "spatial distortion mapping": "EXPLORATION_HAZARD",
    "cognitohazard & urban legend suppression": "SOCIAL_MANIPULATION",
    "urban legend suppression": "SOCIAL_MANIPULATION",
    "urban_legend_debunking": "SOCIAL_MANIPULATION",
    "quarantine perimeter defense": "SITE_DEFENSE_RITUAL",
    "cognitohazard_quarantine": "SITE_DEFENSE_RITUAL",
    "rogue operative / rival hunter interception": "CONTEST_RIVALRY",
    "rogue operative": "CONTEST_RIVALRY",
    "rival hunter": "CONTEST_RIVALRY",
    "high-sensitivity esper / witness escort": "ESCORT_RESCUE",
    "esper escort": "ESCORT_RESCUE",
    "anomalous_autopsy_escort": "ESCORT_RESCUE",
}

GENERIC_ITEM_STOPWORDS = {
    "item", "items", "box", "pack", "piece", "pieces", "bundle", "bundles",
    "rare", "fresh", "ancient", "secret", "stolen", "lost", "package",
    "supply", "supplies", "the", "some", "a", "an", "of", "sample", "samples"
}


# -----------------------------------------------------------------------------
# 3. Registry & Helper Functions
# -----------------------------------------------------------------------------
def get_blueprint_for_archetype(archetype: str, objective: str = "") -> str:
    """Deterministically maps any narrative archetype string to its canonical Blueprint ID."""
    arch_clean = (archetype or "").lower().strip()
    if arch_clean in BLUEPRINT_DEFINITIONS:
        return arch_clean

    # Longest keyword match first
    for kw in sorted(ARCHETYPE_KEYWORD_TO_BLUEPRINT.keys(), key=len, reverse=True):
        if kw in arch_clean:
            return ARCHETYPE_KEYWORD_TO_BLUEPRINT[kw]

    # Inspect objective verbs as fallback
    obj_clean = (objective or "").lower()
    if any(v in obj_clean for v in ("deliver", "gather", "collect", "fetch", "retrieve", "harvest", "craft")):
        return "ACQUISITION"
    if any(v in obj_clean for v in ("assassinate", "slay", "hunt", "eliminate", "execute", "target")):
        return "NEUTRALIZATION"
    if any(v in obj_clean for v in ("infiltrate", "breach", "steal", "hack", "bypass", "slip into")):
        return "HEIST_INFILTRATION"
    if any(v in obj_clean for v in ("defend", "protect", "ritual", "seal", "cleanse", "exorcise")):
        return "SITE_DEFENSE_RITUAL"
    if any(v in obj_clean for v in ("convince", "blackmail", "gossip", "persuade", "negotiate", "ally")):
        return "SOCIAL_MANIPULATION"
    if any(v in obj_clean for v in ("rescue", "escort", "save", "free", "extract person")):
        return "ESCORT_RESCUE"

    return "INVESTIGATION"


def is_single_location_allowed(archetype: str, blueprint_id: str = "") -> bool:
    """Returns True ONLY for whitelisted stationary archetypes/blueprints."""
    bp = blueprint_id or get_blueprint_for_archetype(archetype)
    if bp == "SITE_DEFENSE_RITUAL":
        return True
    arch_lower = (archetype or "").lower()
    return any(w in arch_lower for w in (
        "siege", "survival", "ritual", "sealing", "cleansing", "exorcism",
        "rogue ai", "fortification", "safe zone"
    ))


def infer_required_item_and_count_from_text(objective: str, title: str = "") -> tuple[str, int]:
    """
    Deterministically parses required item name and quantity count (1..99) from objective/title text.
    Handles 'Gather 3x Moonpetals', 'Collect 3 Wolf Pelts', 'Deliver the Sealed Love Letter', etc.
    """
    text = f"{title}. {objective}" if title else objective
    if not text:
        return "", 1

    # Pattern A: Quantity with 'x' or count followed by noun phrase
    # e.g., 'Gather 3x Moonpetals', 'Collect 3 Wolf Pelts', 'Retrieve 2 Encrypted Data Chips'
    m_qty = re.search(
        r'\b(?:gather|collect|retrieve|obtain|acquire|secure|find|harvest|craft|bring)\s+(\d+)\s*(?:x\s*)?([A-Za-z0-9\s\'-]{3,40}?)(?=\s+(?:from|for|in|at|to|before|and|\.|$|,))',
        text,
        re.IGNORECASE,
    )
    if m_qty:
        count = max(1, min(99, int(m_qty.group(1))))
        raw_name = m_qty.group(2).strip()
        raw_name = re.sub(r'^(?:the|a|an|some)\s+', '', raw_name, flags=re.IGNORECASE).strip()
        if len(raw_name) >= 3:
            return raw_name, count

    # Pattern B: Single target item phrase after key action verb
    # e.g., 'Deliver the Sealed Love Letter to Kaelen', 'Recover the Stolen Grimoire'
    m_item = re.search(
        r'\b(?:deliver|retrieve|obtain|acquire|secure|find|recover|hand over|bring)\s+(?:the\s+|a\s+|an\s+)?([A-Za-z0-9\s\'-]{3,40}?)(?=\s+(?:to|from|for|in|at|before|and|\.|$|,))',
        text,
        re.IGNORECASE,
    )
    if m_item:
        raw_name = m_item.group(1).strip()
        raw_name = re.sub(r'^(?:the|a|an|some)\s+', '', raw_name, flags=re.IGNORECASE).strip()
        if len(raw_name) >= 3 and raw_name.lower() not in GENERIC_ITEM_STOPWORDS:
            return raw_name, 1

    # Pattern C: Generic count like '3 Pelts' anywhere near harvest/gather
    m_num = re.search(r'\b(\d+)\s+([A-Za-z0-9\'-]{3,25})\b', text)
    if m_num and int(m_num.group(1)) > 1:
        cnt = int(m_num.group(1))
        item_word = m_num.group(2).strip()
        if item_word.lower() not in {"days", "hours", "minutes", "stages", "clues", "turns", "coins", "gold"}:
            return item_word, cnt

    return "", 1


def infer_required_item_from_text(objective: str, title: str = "") -> str:
    """Convenience wrapper returning just the required item name."""
    item, _ = infer_required_item_and_count_from_text(objective, title)
    return item


def _extract_meaningful_tokens(name: str) -> set[str]:
    """Tokenizes and extracts stems (length >= 3) omitting generic stopwords."""
    tokens = set()
    for w in re.findall(r'[a-zA-Z]{3,}', name.lower()):
        if w in GENERIC_ITEM_STOPWORDS:
            continue
        tokens.add(w)
        # Suffix stripping
        for suf in ("ings", "ing", "tions", "tion", "ments", "ment", "ies", "es", "ed", "s"):
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                tokens.add(w[:-len(suf)])
                break
    return tokens


def find_matching_inventory_items_for_quest(
    required_item: str,
    inventory_items: list[dict],
    exclude_equipped: bool = True,
) -> list[dict]:
    """
    Finds all inventory items matching required_item while strictly protecting equipped items.
    Returns list of matching item dicts from inventory_items.
    """
    if not required_item or not inventory_items:
        return []

    req_clean = required_item.strip().lower()
    req_tokens = _extract_meaningful_tokens(req_clean)
    matches = []

    for item in inventory_items:
        if not isinstance(item, dict):
            continue
        if exclude_equipped and bool(item.get("equipped")):
            continue

        item_name = str(item.get("name", "")).strip().lower()
        if not item_name:
            continue

        # Pass 1: Exact case-insensitive match or direct substring
        if req_clean == item_name or req_clean in item_name or item_name in req_clean:
            matches.append(item)
            continue

        # Pass 2: Token overlap on meaningful root words
        item_tokens = _extract_meaningful_tokens(item_name)
        overlap = req_tokens & item_tokens
        if overlap and any(len(t) >= 4 for t in overlap):
            matches.append(item)

    return matches


def match_inventory_item_for_quest(
    required_item: str,
    inventory_items: list[dict],
    exclude_equipped: bool = True,
) -> dict | None:
    """Returns the first matching unequipped inventory item dict or None."""
    matched = find_matching_inventory_items_for_quest(required_item, inventory_items, exclude_equipped=exclude_equipped)
    return matched[0] if matched else None


# -----------------------------------------------------------------------------
# 4. Multi-Approach Choice Registry & Classification Helpers (Phase 2)
# -----------------------------------------------------------------------------

APPROACH_KEYWORDS: dict[str, tuple[str, ...]] = {
    "spare_deceive": (
        "spare", "fake", "disappear", "warn", "mercy", "pretend", "forge", "staged", "stage",
        "alibi", "let go", "convince to flee", "vanish", "fake death", "spare & fake death",
        "fabricate compromise", "forged proof"
    ),
    "counter_offer": (
        "counter-offer", "counter offer", "double-cross", "betray", "accept bribe",
        "switch sides", "take their deal", "sell out", "accept counter-offer", "side deal"
    ),
    "buyout_bribe": (
        "buyout", "buy", "purchase", "bribe", "pay off", "pay ", "buyout / bribe",
        "toll", "coin", "gold"
    ),
    "stealth_guile": (
        "sneak", "steal", "pickpocket", "infiltrate", "bypass", "hack", "slip", "shadow",
        "covert", "quietly", "evade", "distraction", "stealth & infiltration", "diversion & stealth"
    ),
    "direct": (
        "kill", "defeat", "strike", "execute", "eliminate", "seize", "capture", "force",
        "smash", "confront", "interrogate", "search", "investigate", "attack", "slay"
    ),
}


def classify_choice_approach(label: str) -> str:
    """Classifies a choice label into one of Hikayat's canonical quest approaches."""
    lbl = (label or "").lower()
    if not lbl:
        return "direct"

    # Explicit approach bracket tags take absolute priority
    if "[persuade]" in lbl:
        return "nh_persuade"
    if "[calm]" in lbl:
        return "nh_calm"
    if "[outwit]" in lbl:
        return "nh_outwit"
    if "[use environment]" in lbl:
        return "nh_environment"
    if "[breakthrough leverage]" in lbl or "breakthrough leverage" in lbl:
        return "breakthrough_leverage"
    if "[companion assist" in lbl or "companion assist" in lbl:
        return "companion_assist"
    if "[spare & fake death]" in lbl or "[spare" in lbl or "fake death" in lbl or "forged proof" in lbl:
        return "spare_deceive"
    if "[accept counter-offer]" in lbl or "counter-offer" in lbl or "counter offer" in lbl:
        return "counter_offer"
    if "[buyout / bribe" in lbl or "[buyout" in lbl or "[bribe" in lbl:
        return "buyout_bribe"
    if "[stealth" in lbl or "[diversion" in lbl:
        return "stealth_guile"

    # Keyword check in descending specificity order
    for app in ("counter_offer", "spare_deceive", "buyout_bribe", "stealth_guile"):
        if any(kw in lbl for kw in APPROACH_KEYWORDS.get(app, ())):
            return app

    return "direct"


def calculate_quest_buyout_cost(quest: dict | None) -> int:
    """Calculates deterministic buyout/bribe gold cost (50% of quest reward_gold, min 15g)."""
    reward = int(((quest or {}).get("reward_gold") or 30))
    return max(15, int(reward * 0.5))


def build_stage_contrasting_approaches(
    blueprint_id: str,
    stage_index: int,
    total_stages: int,
    stage_label: str = "",
    target_npc: str = "",
    required_item: str = "",
    reward_gold: int = 30,
    player_gold: int = 0,
    is_story_quest: bool = False,
    stealth_warranted: bool = True,
) -> list[dict]:
    """
    Returns contrasting approach descriptor dicts for active resolution stages (Stage >= 2 or single-stage action).
    Each dict contains: approach, label, stat, requirement_offset, gold_cost, intent.
    """
    approaches: list[dict] = []
    bp = blueprint_id or ""
    lbl_lower = (stage_label or "").lower()

    # 1. NEUTRALIZATION or CONTEST_RIVALRY: Confrontation Stage (Stage 2 or active target confrontation)
    if bp in ("NEUTRALIZATION", "CONTEST_RIVALRY") or any(w in lbl_lower for w in ("confront", "eliminate", "slay", "assassinate", "defeat")):
        target_disp = target_npc or "the target"
        approaches.append({
            "approach": "spare_deceive",
            "label": f"[Spare & Fake Death] Convince {target_disp} to vanish and forge proof of elimination",
            "stat": "CHA",
            "requirement_offset": 0,
            "gold_cost": 0,
            "intent": "dialogue_init" if target_npc else "general_action",
        })
        # Betrayal counter-offer is only valid for non-story bounties
        if not is_story_quest:
            approaches.append({
                "approach": "counter_offer",
                "label": f"[Accept Counter-Offer] Strike a secret deal with {target_disp} and betray your client for 1.5x Gold",
                "stat": "FREE",
                "requirement_offset": 0,
                "gold_cost": 0,
                "intent": "dialogue_init" if target_npc else "general_action",
            })

    # 2. ACQUISITION, HEIST_INFILTRATION, SOCIAL_MANIPULATION: Intermediate or retrieval stage
    elif bp in ("ACQUISITION", "HEIST_INFILTRATION", "SOCIAL_MANIPULATION") or any(w in lbl_lower for w in ("retrieve", "infiltrate", "obtain", "gather", "secure", "evidence", "records")):
        buyout_cost = max(15, int((reward_gold or 30) * 0.5))
        obj_disp = required_item or "the objective"
        if player_gold >= buyout_cost:
            approaches.append({
                "approach": "buyout_bribe",
                "label": f"[Buyout / Bribe: {buyout_cost}g] Pay {buyout_cost} Gold to secure {obj_disp} without risk",
                "stat": "FREE",
                "requirement_offset": 0,
                "gold_cost": buyout_cost,
                "intent": "general_action",
            })
        if bp in ("HEIST_INFILTRATION", "ACQUISITION"):
            if stealth_warranted or bp == "HEIST_INFILTRATION":
                approaches.append({
                    "approach": "stealth_guile",
                    "label": f"[Stealth & Infiltration] Slip past the sentries and secure {obj_disp} unnoticed",
                    "stat": "AGI",
                    "requirement_offset": 0,
                    "gold_cost": 0,
                    "intent": "investigate_clue",
                })
            else:
                approaches.append({
                    "approach": "direct",
                    "label": f"[Careful Inquiry] Check local records and ask around discreetly to secure {obj_disp}",
                    "stat": "PER",
                    "requirement_offset": 0,
                    "gold_cost": 0,
                    "intent": "investigate_clue",
                })
        elif bp == "SOCIAL_MANIPULATION":
            approaches.append({
                "approach": "spare_deceive",
                "label": f"[Fabricate Compromise] Forge an alibi or alternative report without exposing secrets",
                "stat": "INT",
                "requirement_offset": 0,
                "gold_cost": 0,
                "intent": "dialogue_init",
            })

    # 3. ESCORT_RESCUE: Extraction / passage stage
    elif bp == "ESCORT_RESCUE" or any(w in lbl_lower for w in ("escort", "extract", "rescue", "guide")):
        buyout_cost = max(15, int((reward_gold or 30) * 0.5))
        if player_gold >= buyout_cost:
            approaches.append({
                "approach": "buyout_bribe",
                "label": f"[Buyout / Bribe: {buyout_cost}g] Bribe sentries or toll keepers with {buyout_cost} Gold for safe passage",
                "stat": "FREE",
                "requirement_offset": 0,
                "gold_cost": buyout_cost,
                "intent": "general_action",
            })
        elif stealth_warranted:
            approaches.append({
                "approach": "stealth_guile",
                "label": "[Diversion & Stealth] Create a distraction to slip past the perimeter unnoticed",
                "stat": "AGI",
                "requirement_offset": 0,
                "gold_cost": 0,
                "intent": "investigate_clue",
            })
        else:
            approaches.append({
                "approach": "direct",
                "label": "[Calm Guidance] Guide them calmly through a clear route and talk past any obstacles",
                "stat": "CHA",
                "requirement_offset": 0,
                "gold_cost": 0,
                "intent": "general_action",
            })

    # 4. EXPLORATION_HAZARD or generic fallback
    else:
        if stealth_warranted:
            approaches.append({
                "approach": "stealth_guile",
                "label": "[Careful Bypass] Navigate the hazards using stealth and careful footing",
                "stat": "AGI",
                "requirement_offset": 0,
                "gold_cost": 0,
                "intent": "investigate_clue",
            })
        else:
            approaches.append({
                "approach": "direct",
                "label": "[Methodical Survey] Carefully examine the surroundings and proceed step by step",
                "stat": "PER",
                "requirement_offset": 0,
                "gold_cost": 0,
                "intent": "investigate_clue",
            })

    return approaches


# -----------------------------------------------------------------------------
# 7. Phase 3: Temporal Windows, Wait Calculations & Soft Deadlines
# -----------------------------------------------------------------------------
PHASE_START_MINUTES: dict[str, int] = {
    "Early Morning": 300,   # 05:00
    "Morning": 480,         # 08:00
    "Lunch": 720,           # 12:00
    "Afternoon": 780,       # 13:00
    "Extracurricular": 900, # 15:00
    "Evening": 1020,        # 17:00
    "Night": 1200,          # 20:00
    "Midnight": 0,          # 00:00
}

PURE_TIME_LOCKED_KEYWORDS = (
    "ghost",
    "apparition",
    "phantom",
    "haunt",
    "midnight ritual",
    "eclipse",
    "moonlit ritual",
    "after-hours meeting",
    "secret rendezvous",
    "curfew bell",
    "midnight meeting",
)


def infer_valid_time_phases_for_stage(
    blueprint_id: str,
    archetype: str = "",
    stage_index: int = 1,
    total_stages: int = 3,
    stage_label: str = "",
    scen_key: str = "fantasy",
) -> list[str]:
    """
    Infers valid time-of-day phases for a quest stage based on explicit temporal keywords.
    Stage 1 (scouting/arrival) and final Client Turn-In stage return [] (governed by Off-Duty Guard).
    """
    if stage_index <= 1 or (total_stages >= 3 and stage_index >= total_stages):
        return []
    combined = f"{archetype or ''} {stage_label or ''}".lower()
    if any(k in combined for k in ("midnight", "dead of night", "witching hour")):
        return ["Midnight"]
    if any(k in combined for k in ("night raid", "under cover of night", "at night", "after hours", "after-hours", "nocturnal", "moonlight", "curfew", "ghost", "apparition")):
        return ["Night", "Midnight"]
    if any(k in combined for k in ("at dawn", "early morning", "sunrise")):
        return ["Early Morning", "Morning"]
    if "high_school" in (scen_key or "").lower() and any(k in combined for k in ("after school", "extracurricular", "club activity", "club practice")):
        return ["Afternoon", "Evening"]
    return []


def is_purely_time_locked_stage(stage_label: str, objective: str = "") -> bool:
    """
    Returns True if the stage represents a purely time-bound phenomenon or appointment
    (e.g. midnight ghost, eclipse, scheduled secret rendezvous) that cannot be brute-forced early with +3 DC.
    """
    combined = f"{stage_label or ''} {objective or ''}".lower()
    return any(k in combined for k in PURE_TIME_LOCKED_KEYWORDS)


def evaluate_waypoint_time_window(
    current_minute: int,
    valid_time_phases: list[str] | None,
) -> dict:
    """
    Evaluates whether current_minute falls within valid_time_phases.
    Returns:
      {
        "is_valid": bool,
        "current_phase": str,
        "target_phase": str,
        "target_minute": int,
        "wait_minutes": int,
        "target_clock": str,
      }
    """
    from mechanics.system.time_engine import get_time_of_day_phase, format_clock
    safe_min = int(current_minute or 0) % 1440
    curr_phase, _, _ = get_time_of_day_phase(safe_min)

    phases = [str(p).strip() for p in (valid_time_phases or []) if str(p).strip()]
    if not phases:
        return {
            "is_valid": True,
            "current_phase": curr_phase,
            "target_phase": curr_phase,
            "target_minute": safe_min,
            "wait_minutes": 0,
            "target_clock": format_clock(safe_min),
        }

    norm_phases = [p.lower() for p in phases]
    is_valid = curr_phase.lower() in norm_phases
    if not is_valid:
        if "night" in norm_phases and (safe_min >= 1200 or safe_min < 300):
            is_valid = True
        elif "afternoon" in norm_phases and (720 <= safe_min <= 1019):
            is_valid = True
        elif "extracurricular" in norm_phases and (900 <= safe_min <= 1199):
            is_valid = True
        elif "lunch" in norm_phases and (720 <= safe_min <= 779):
            is_valid = True

    if is_valid:
        return {
            "is_valid": True,
            "current_phase": curr_phase,
            "target_phase": curr_phase,
            "target_minute": safe_min,
            "wait_minutes": 0,
            "target_clock": format_clock(safe_min),
        }

    # Find the nearest upcoming phase start minute
    best_phase = phases[0]
    best_wait = 1440
    best_target_min = PHASE_START_MINUTES.get(best_phase, 1200)
    for p in phases:
        p_start = next((v for k, v in PHASE_START_MINUTES.items() if k.lower() == p.lower()), 1200)
        wait = (p_start - safe_min) % 1440
        if wait == 0:
            wait = 1440
        if wait < best_wait:
            best_wait = wait
            best_phase = p
            best_target_min = p_start

    return {
        "is_valid": False,
        "current_phase": curr_phase,
        "target_phase": best_phase,
        "target_minute": best_target_min,
        "wait_minutes": best_wait,
        "target_clock": format_clock(best_target_min),
    }


def roll_quest_deadline(
    blueprint_id: str = "",
    quest_type: str = "",
    title: str = "",
    objective: str = "",
    current_day: int = 1,
    current_minute: int = 480,
    is_story_quest: bool = False,
    seed_str: str = "",
) -> tuple[int | None, int | None]:
    """
    Deterministically assigns a generous 5-to-7 day deadline to ~45% of side/faction bounties
    (prioritizing urgent keywords and blueprints). Story quests never receive a deadline.
    """
    import hashlib
    if is_story_quest or "story" in (quest_type or "").lower() or "main" in (quest_type or "").lower():
        return (None, None)

    combined = f"{quest_type or ''} {title or ''} {objective or ''}".lower()
    urgent_kw = ("urgent", "timed", "immediate", "convoy", "escaping", "flees", "courier", "ransom", "before", "deadline", "emergency")
    has_urgent_kw = any(k in combined for k in urgent_kw)

    digest_input = f"{blueprint_id}:{quest_type}:{title}:{seed_str}".encode("utf-8")
    h_val = int(hashlib.md5(digest_input).hexdigest()[:8], 16)

    should_have_deadline = False
    if has_urgent_kw:
        should_have_deadline = True
    elif blueprint_id in ("ESCORT_RESCUE", "NEUTRALIZATION", "HEIST_INFILTRATION"):
        should_have_deadline = (h_val % 100) < 60
    else:
        should_have_deadline = (h_val % 100) < 35

    if not should_have_deadline:
        return (None, None)

    days_offset = 5 + (h_val % 3)  # 5, 6, or 7 days
    base_day = max(1, int(current_day or 1))
    return (base_day + days_offset, 1200)


# -----------------------------------------------------------------------------
# 5. Phase 4 Cross-System Helpers: Notes Flags, Companion Assist & Comms
# -----------------------------------------------------------------------------

def has_quest_note_flag(quest_notes: str | None, flag_key: str) -> bool:
    """Checks if a pipe-delimited or key:value flag is present in quest_notes."""
    if not quest_notes or not flag_key:
        return False
    notes_str = str(quest_notes)
    tokens = [t.strip().lower() for t in re.split(r'[|\n,]+', notes_str) if t.strip()]
    f_key = flag_key.strip().lower()
    for tok in tokens:
        if tok == f_key or tok.startswith(f"{f_key}:"):
            return True
    return False


def append_quest_note_flag(quest_notes: str | None, flag_key: str, flag_val: str = "1") -> str:
    """Appends or updates a flag in quest_notes (e.g. caseboard_breakthrough:1)."""
    f_key = (flag_key or "").strip().lower()
    if not f_key:
        return str(quest_notes or "")
    new_flag = f"{f_key}:{flag_val}" if flag_val is not None else f_key
    if not quest_notes:
        return new_flag
    notes_str = str(quest_notes).strip()
    tokens = [t.strip() for t in re.split(r'[|\n,]+', notes_str) if t.strip()]
    filtered = [t for t in tokens if not (t.lower() == f_key or t.lower().startswith(f"{f_key}:"))]
    filtered.append(new_flag)
    return "|".join(filtered)


COMPANION_ROLE_KEYWORDS_BY_BLUEPRINT = {
    "HEIST_INFILTRATION": (
        "rogue", "thief", "assassin", "ninja", "netrunner", "hacker", "scout",
        "shadow", "smuggler", "stealth", "track", "student council"
    ),
    "INVESTIGATION": (
        "detective", "scholar", "mage", "wizard", "investigator", "journalist",
        "media", "newspaper", "occult", "student council", "archivist", "inspector"
    ),
    "SOCIAL_MANIPULATION": (
        "bard", "diplomat", "noble", "courtesan", "idol", "student council",
        "president", "socialite", "journalist", "gossip", "drama"
    ),
    "NEUTRALIZATION": (
        "warrior", "knight", "paladin", "mercenary", "fighter", "ranger",
        "bounty", "hunter", "varsity", "martial", "dojo", "berserker", "vanguard"
    ),
    "DEFENSE_SURVIVAL": (
        "guardian", "knight", "paladin", "cleric", "healer", "medic",
        "warrior", "defender", "vanguard", "varsity"
    ),
    "ARCANE_CONTAINMENT": (
        "mage", "wizard", "cleric", "priest", "shrine", "occult", "warlock",
        "sorcerer", "alchemist", "witch", "exorcist"
    ),
    "ACQUISITION": (
        "alchemist", "herbalist", "merchant", "scavenger", "ranger",
        "crafter", "botanist", "science", "cook", "quartermaster"
    ),
    "ESCORT_RESCUE": (
        "paladin", "knight", "ranger", "medic", "healer", "scout",
        "guardian", "prefect", "student council"
    ),
    "CONTEST_RIVALRY": (
        "duelist", "champion", "varsity", "captain", "athlete", "gamer",
        "arcade", "fighter", "bard"
    ),
    "EXPLORATION_HAZARD": (
        "ranger", "explorer", "scout", "archaeologist", "navigator",
        "survivor", "mechanic", "occult"
    ),
}


def evaluate_companion_assist_for_blueprint(
    companion: dict,
    blueprint_id: str,
    stage_label: str = "",
) -> dict:
    """
    Evaluates whether an active companion's role/class/traits match the quest blueprint.
    If matched, grants FREE Auto-Success (0 DC). Otherwise grants a -3 DC reduction.
    """
    comp_name = str(companion.get("name") or "Companion").strip()
    raw_info = companion.get("basic_info") if isinstance(companion.get("basic_info"), dict) else {}
    role_text = " ".join([
        str(companion.get("role") or ""),
        str(companion.get("char_class") or ""),
        str(companion.get("club") or ""),
        str(companion.get("occupation") or ""),
        str(raw_info.get("role") or ""),
        str(raw_info.get("occupation") or ""),
        " ".join(str(t) for t in (companion.get("unlocked_traits") or raw_info.get("traits") or [])),
    ]).lower()

    keywords = COMPANION_ROLE_KEYWORDS_BY_BLUEPRINT.get(blueprint_id, ())
    matched_kw = next((kw for kw in keywords if kw in role_text), None)

    if matched_kw:
        matched_label = companion.get("role") or companion.get("char_class") or matched_kw.title()
        return {
            "companion_name": comp_name,
            "is_role_match": True,
            "matched_role_label": str(matched_label).title(),
            "stat": "FREE",
            "dc_mod": 0,
        }
    else:
        return {
            "companion_name": comp_name,
            "is_role_match": False,
            "matched_role_label": str(companion.get("role") or "Ally").title(),
            "stat": None,
            "dc_mod": -3,
        }


def format_quest_comms_message(
    scen_key: str,
    sender_name: str,
    msg_type: str,
    quest_title: str,
    target_npc: str = "",
    target_loc: str = "",
) -> tuple[str, str]:
    """
    Formats a scenario-appropriate incoming Phone DM / Guild Courier message.
    Returns: (channel_prefix, message_body)
    """
    from mechanics.system.time_engine import is_modern_setting
    is_modern = is_modern_setting(scen_key) or "school" in str(scen_key).lower()
    channel_prefix = "📱 [SMS / DM]" if is_modern else "🦅 [Guild Courier]"

    if msg_type == "stage2_target_plea":
        if is_modern:
            body = f"Hey... I know you're looking for me regarding '{quest_title}'. Please, don't rush into this! Meet me alone so we can talk this through."
        else:
            body = f"I know the bounty hunter approaches for '{quest_title}'. Hold your steel! Let us parley in secret before blood is spilled."
    elif msg_type == "deadline_24h_warning":
        if is_modern:
            body = f"Urgent reminder on '{quest_title}': Less than 24 hours remain before the deadline expires! Wrap this up ASAP."
        else:
            body = f"Hear this dispatch on '{quest_title}': The sands have nearly run out. A rival mercenary company is poised to seize the claim if you do not finish before sundown!"
    elif msg_type == "contact_commission":
        if is_modern:
            body = f"Hey! I need a discreet personal favor that I can only trust you with: '{quest_title}'. Check the details when you can!"
        else:
            body = f"A trusted courier brings word: I have a delicate matter of consequence ('{quest_title}') that requires your discreet talents."
    else:  # stage2_client_intel default
        loc_str = f" at {target_loc}" if target_loc else ""
        tgt_str = f"{target_npc}" if target_npc else "the target"
        if is_modern:
            body = f"Update on '{quest_title}': Scouts just confirmed sightings of {tgt_str}{loc_str}. Watch your step out there!"
        else:
            body = f"Fresh intelligence on '{quest_title}': Informants confirm {tgt_str} is sighted{loc_str}. Strike swiftly and maintain your guard."

    return channel_prefix, body


# -----------------------------------------------------------------------------
# 8. Anomalous Incursions: 11-Chapter Cataclysm + Epilogue & World-Ending Anomaly
# -----------------------------------------------------------------------------

def get_max_campaign_chapters(scen_key: str = "fantasy") -> int:
    """
    Returns the total number of campaign chapters for the scenario:
    - Anomalous Incursions (and its 3 variants): 11 Chapters (Ch 1-10 Cataclysm + Ch 11 Epilogue/Resolution)
    - All other scenarios: 10 Chapters
    """
    import scenario_data
    if scenario_data.is_anomalous_incursions_scenario(scen_key):
        return 11
    return 10


def ensure_world_ending_anomaly_blueprint(
    session_id: int,
    session: dict | None = None,
) -> dict:
    """
    Deterministically rolls and persists the session's World-Ending Anomaly Antagonist profile
    in `session["world_ending_anomaly"]` (and `extra_json`).
    """
    import db
    import namegen

    if session is None and session_id:
        session = db.get_session(session_id) or {}
    elif session is None:
        session = {}

    existing = session.get("world_ending_anomaly")
    if isinstance(existing, dict) and existing.get("name"):
        return existing

    seed_val = int(session_id or 1)
    profile = namegen.generate_world_ending_anomaly_profile(hash_val=seed_val)
    session["world_ending_anomaly"] = profile
    if session_id:
        try:
            db.update_session(session_id, extra={"world_ending_anomaly": profile})
        except Exception:
            pass
    return profile


def generate_anomalous_campaign_blueprint(
    session_id: int,
    session: dict | None = None,
) -> dict:
    """
    Generates the structured 11-Chapter Campaign Blueprint for Anomalous Incursions,
    mapping each chapter to its narrative phase, overarching archetype, and 3 scenario sub-objective archetypes.
    """
    anomaly = ensure_world_ending_anomaly_blueprint(session_id, session=session)
    entity_name = anomaly.get("name", "The Non-Euclidean Convergence")
    entity_title = anomaly.get("title", "Sovereign of the Folded Horizon")
    omen = anomaly.get("foreshadow_sign") or anomaly.get("omen_signature") or "geometric distortions and bleeding static"
    cult_goal = anomaly.get("cult_goal", "awaken the World-Ending Anomaly across the metropolitan grid")
    syndicate_goal = anomaly.get("syndicate_goal", "traffic uncatalogued resonance catalysts on the black market")
    harbinger_name = anomaly.get("harbinger_name", "The Convergence Harbinger")

    chapters = {
        1: {
            "chapter": 1,
            "phase": "inciting_foreshadowing",
            "title_template": "Chapter #1: First Breach & The Silent Omen",
            "archetype": "Inciting Containment & Foreshadowing",
            "sub_archetypes": [
                "Investigate Anomalous Phenomenon",
                "Contain Anomalous Phenomenon",
                "Eliminate Hostile Anomalous Entity",
            ],
            "pacing_directive": (
                f"CHAPTER 1 (INCITING CONTAINMENT & FORESHADOWING): "
                f"Conclude the chapter with an eerie resonance spike ({omen}) foreshadowing the distant awakening of {entity_name} ({entity_title})."
            ),
        },
        2: {
            "chapter": 2,
            "phase": "mystery_unraveling",
            "title_template": "Chapter #2: Whispers in the Reliquary",
            "archetype": "Investigate Anomalous Phenomenon",
            "sub_archetypes": [
                "Investigate Anomalous Phenomenon",
                "Retrieve Altered Item / Cursed Relic",
                "Cognitohazard & Urban Legend Suppression",
            ],
            "pacing_directive": f"CHAPTER 2 (UNRAVELING THE MYSTERY): Trace altered relics bearing the signature of {entity_name}.",
        },
        3: {
            "chapter": 3,
            "phase": "mystery_unraveling",
            "title_template": "Chapter #3: Spirited Beyond the Threshold",
            "archetype": "Find Missing Person (Spirited Away)",
            "sub_archetypes": [
                "Spatial Distortion Mapping",
                "Find Missing Person (Spirited Away)",
                "Secure Non-Hostile Anomalous Entity",
            ],
            "pacing_directive": f"CHAPTER 3 (UNRAVELING THE MYSTERY): Map expanding spatial rifts and rescue civilians spirited into pocket folds linked to {entity_name}.",
        },
        4: {
            "chapter": 4,
            "phase": "mystery_unraveling",
            "title_template": "Chapter #4: Black-Market Resonance",
            "archetype": "Disrupt Cult Ritual / Clandestine Auction",
            "sub_archetypes": [
                "Investigate Anomalous Phenomenon",
                "Disrupt Cult Ritual / Clandestine Auction",
                "Retrieve Altered Item / Cursed Relic",
            ],
            "pacing_directive": f"CHAPTER 4 (UNRAVELING THE MYSTERY): Expose Clandestine Syndicate trafficking ({syndicate_goal}) feeding {entity_name}.",
        },
        5: {
            "chapter": 5,
            "phase": "mystery_unraveling",
            "title_template": "Chapter #5: Choir of the Occult Conduit",
            "archetype": "Disrupt Cult Ritual / Clandestine Auction",
            "sub_archetypes": [
                "Cognitohazard & Urban Legend Suppression",
                "Disrupt Cult Ritual / Clandestine Auction",
                "Eliminate Hostile Anomalous Entity",
            ],
            "pacing_directive": f"CHAPTER 5 (MID-CAMPAIGN REVELATION): Uncover the Occult Cult's ritual network seeking to {cult_goal} for {entity_name}.",
        },
        6: {
            "chapter": 6,
            "phase": "mystery_unraveling",
            "title_template": "Chapter #6: The Convergence Blueprint",
            "archetype": "Spatial Distortion Mapping",
            "sub_archetypes": [
                "Spatial Distortion Mapping",
                "High-Sensitivity Esper / Witness Escort",
                "Contain Anomalous Phenomenon",
            ],
            "pacing_directive": f"CHAPTER 6 (FINAL BUILDUP): Escort a high-sensitivity Esper witness and decode the exact coordinates where {entity_name} will breach reality.",
        },
        7: {
            "chapter": 7,
            "phase": "active_escalation",
            "title_template": f"Chapter #7: Harbingers of {entity_name}",
            "archetype": "Quarantine Perimeter Defense",
            "sub_archetypes": [
                "Quarantine Perimeter Defense",
                "Eliminate Hostile Anomalous Entity",
                "High-Sensitivity Esper / Witness Escort",
            ],
            "pacing_directive": f"CHAPTER 7 (ACTIVE ESCALATION): {entity_name} begins actively causing city-wide chaos and manifesting {harbinger_name} across district perimeters!",
        },
        8: {
            "chapter": 8,
            "phase": "active_escalation",
            "title_template": "Chapter #8: Shattered Cordons & Rogue Operatives",
            "archetype": "Rogue Operative / Rival Hunter Interception",
            "sub_archetypes": [
                "Rogue Operative / Rival Hunter Interception",
                "Disrupt Cult Ritual / Clandestine Auction",
                "Quarantine Perimeter Defense",
            ],
            "pacing_directive": f"CHAPTER 8 (ACTIVE ESCALATION): Intercept compromised operatives and cult saboteurs tearing down containment wards for {entity_name}.",
        },
        9: {
            "chapter": 9,
            "phase": "active_escalation",
            "title_template": "Chapter #9: Eve of the Cataclysm",
            "archetype": "Contain Anomalous Phenomenon",
            "sub_archetypes": [
                "Retrieve Altered Item / Cursed Relic",
                "Contain Anomalous Phenomenon",
                "Eliminate Hostile Anomalous Entity",
            ],
            "pacing_directive": f"CHAPTER 9 (PENULTIMATE ESCALATION): The sky fractures with {omen}. Secure the final containment anchors and slay {harbinger_name} before {entity_name} manifests.",
        },
        10: {
            "chapter": 10,
            "phase": "cataclysm_climax",
            "title_template": f"Chapter #10: Cataclysm — {entity_name}",
            "archetype": "Apocalyptic Boss Confrontation",
            "sub_archetypes": [
                "Spatial Distortion Mapping",
                "Contain Anomalous Phenomenon",
                "Apocalyptic Boss Confrontation",
            ],
            "pacing_directive": (
                f"CHAPTER 10 (CLIMAX — WORLD-ENDING BOSS BATTLE): Breach the non-Euclidean epicenter, sever the convergence anchors, "
                f"and engage {entity_name} ({entity_title}) in an apocalyptic multi-phase final boss confrontation!"
            ),
        },
        11: {
            "chapter": 11,
            "phase": "resolution_epilogue",
            "title_template": "Chapter #11: Aftermath & Commendation of the Watch",
            "archetype": "Post-Crisis Resolution & Epilogue",
            "sub_archetypes": [
                "Contain Anomalous Phenomenon",
                "Cognitohazard & Urban Legend Suppression",
                "Investigate Anomalous Phenomenon",
            ],
            "pacing_directive": (
                f"CHAPTER 11 (RESOLUTION & EPILOGUE): Following the defeat of {entity_name}, stabilize the city's remaining residual rifts, "
                f"debrief with Faction Leadership & Special Agent companions, and receive your post-crisis commendation. "
                f"Upon completion, present the Post-Game Epilogue choice: [🏁 Conclude Campaign (Archive Chronicle)] or [♾️ Continue in Endless Containment Mode]."
            ),
        },
    }

    return {
        "world_ending_anomaly": anomaly,
        "max_chapters": 11,
        "chapters": chapters,
    }



