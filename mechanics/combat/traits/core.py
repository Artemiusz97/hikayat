from __future__ import annotations
"""
Trait evaluation algorithms, DC modifiers, behavioral prompt formatting, and NPC assignment.
"""
import hashlib
import re
from typing import Dict, Any, List, Optional, Tuple, Set

from .data import (
    TRAIT_REGISTRY,
    GROUNDED_FOOD_LIKES,
    GROUNDED_FOOD_DISLIKES,
    GROUNDED_DRINK_LIKES,
    GROUNDED_DRINK_DISLIKES,
    GROUNDED_GIFT_LIKES,
    GROUNDED_GIFT_DISLIKES,
    SOCIAL_STANCES_LIKES,
    SOCIAL_STANCES_DISLIKES,
    BEHAVIORAL_LIKES,
    BEHAVIORAL_DISLIKES,
)

def get_social_stance_badge(stance_text: str, is_dislike: bool = False) -> str:
    """Returns the custom, tailored badge for any behavioral stance."""
    s_low = str(stance_text or "").lower()

    if not is_dislike:
        # 1. Exact label match first
        for s_data in SOCIAL_STANCES_LIKES.values():
            if s_data["label"].lower() in s_low or s_low in s_data["label"].lower() or s_data["id"] == s_low:
                return s_data["badge"]
        # 2. Word-boundary trigger match
        for s_data in SOCIAL_STANCES_LIKES.values():
            if any(re.search(r'\b' + re.escape(tr) + r'\b', s_low) for tr in s_data["triggers"]):
                return s_data["badge"]
        return "+2 Affinity on matching dialogue actions"
    else:
        # 1. Exact label match first
        for s_data in SOCIAL_STANCES_DISLIKES.values():
            if s_data["label"].lower() in s_low or s_low in s_data["label"].lower() or s_data["id"] == s_low:
                return s_data["badge"]
        # 2. Word-boundary trigger match
        for s_data in SOCIAL_STANCES_DISLIKES.values():
            if any(re.search(r'\b' + re.escape(tr) + r'\b', s_low) for tr in s_data["triggers"]):
                return s_data["badge"]
        return "-3 Penalty on opposing or dismissive dialogue"


def is_gift_item(text: str) -> bool:
    """Checks if a preference string represents a tangible physical gift item (food, drink, craft, shop item)
    rather than an abstract behavioral preference (e.g. Attention, Validation, Control, Honesty)."""
    if not text or not isinstance(text, str):
        return False
    t_clean = re.sub(r'^(likes|dislikes|prefers|loves|enjoys|hates|fears)\s+', '', text.strip(), flags=re.IGNORECASE).strip()
    t_low = t_clean.lower()

    # 1. Exact match against known grounded foods, drinks & gifts
    known_physical_items = {
        item.lower().replace("dislikes ", "").replace("likes ", "").strip()
        for item in (GROUNDED_FOOD_LIKES + GROUNDED_DRINK_LIKES + GROUNDED_GIFT_LIKES + GROUNDED_FOOD_DISLIKES + GROUNDED_DRINK_DISLIKES + GROUNDED_GIFT_DISLIKES)
    }
    if t_low in known_physical_items:
        return True

    # 2. Abstract behavioral keywords that must NEVER be classified as gifts
    abstract_keywords = {
        "attention", "control", "independence", "logistics", "validation", "feedback",
        "precision", "work", "execution", "behavior", "dishonesty", "honesty", "soldering",
        "interruptions", "focusing", "slacking", "praise", "teasing", "listening", "planning",
        "curiosity", "surprises", "composure", "wit", "punctuality", "quiet", "training",
        "loyalty", "notes", "order", "discipline", "etiquette", "commanded", "flattery",
        "underestimated", "prying", "inquisitiveness", "carelessness", "arrogance", "bragging",
        "commitments", "drama", "sloppiness", "excuses", "files", "yelling", "chaos",
        "unpreparedness", "tactics", "bullies", "power outages", "being", "slacking off"
    }
    if any(ak in t_low for ak in abstract_keywords):
        return False

    # 3. Tangible physical item keywords
    physical_item_keywords = {
        "coffee", "latte", "tea", "boba", "cider", "ale", "wine", "beer", "mead", "soda", "ramune",
        "smoothie", "espresso", "juice", "cordial", "fizz",
        "cake", "tart", "roll", "melon pan", "pan", "bento",
        "sandwich", "drink", "parfait", "chocolate", "pastry", "pastries", "pie",
        "cookie", "cookies", "snack", "snacks", "food", "dessert", "desserts", "candy",
        "pen", "stationery", "keychain", "plush", "pendant", "amulet", "music box", "candle",
        "record", "sketchbook", "novelty", "novelties", "perfume", "accessories", "accessory",
        "knick-knacks", "plushie", "badge", "figurine", "scarf", "ribbon", "box", "set"
    }
    return any(pk in t_low for pk in physical_item_keywords)


# -----------------------------------------------------------------------------
# CORE REGISTRY FUNCTIONS
# -----------------------------------------------------------------------------

def get_trait(trait_name: str) -> Optional[Dict[str, Any]]:
    """Retrieves trait definition by ID or label, supporting aliases."""
    if not trait_name or not isinstance(trait_name, str):
        return None
    key = trait_name.strip().lower()
    if key in TRAIT_REGISTRY:
        return TRAIT_REGISTRY[key]
    # Check labels
    for t in TRAIT_REGISTRY.values():
        if t["label"].lower() == key:
            return t
    return None


def normalize_traits(raw_traits: list) -> List[str]:
    """Normalizes an incoming list of trait strings to canonical capitalized labels, pruning any mutually incompatible traits."""
    if not isinstance(raw_traits, list):
        return ["Diligent", "Warm"]
    out = []
    forbidden: Set[str] = set()
    for item in raw_traits:
        if not isinstance(item, str) or not item.strip():
            continue
        item_clean = item.strip()
        t_def = get_trait(item_clean)
        if t_def and t_def["id"] not in forbidden:
            out.append(t_def["label"])
            forbidden.add(t_def["id"])
            forbidden.update(t_def.get("incompatible_with", set()))
        elif not t_def and len(item_clean.split()) <= 4:
            cap = item_clean.title()
            if cap not in out:
                out.append(cap)
    if not out:
        return ["Diligent", "Warm"]
    return out[:3]


def assign_npc_traits(seed_str: str, count: int = 3, role: str = "", race: str = "") -> List[str]:
    """
    Deterministically assigns 2-3 compatible traits based on NPC seed, role, and race.
    Strictly prunes incompatible traits to guarantee zero contradictory combinations.
    """
    combined = (str(seed_str or "") + "_" + str(role or "") + "_" + str(race or "")).lower()
    hash_val = int(hashlib.md5(combined.encode("utf-8")).hexdigest(), 16) if combined else 42

    # Weight selection based on role if keywords match
    priority_traits = []
    role_low = str(role or "").lower()
    if any(k in role_low for k in ["council", "president", "secretary", "captain", "lead", "officer"]):
        priority_traits.extend(["diligent", "proud", "ambitious", "perfectionist"])
    elif any(k in role_low for k in ["athlete", "sports", "track", "gym", "swim"]):
        priority_traits.extend(["competitive", "spirited", "warm", "diligent"])
    elif any(k in role_low for k in ["tech", "science", "robot", "engineer", "tinker", "inventor"]):
        priority_traits.extend(["scholarly", "diligent", "eccentric", "perfectionist"])
    elif any(k in role_low for k in ["delinquent", "rebel", "gang", "street"]):
        priority_traits.extend(["delinquent", "blunt", "proud", "mischievous"])
    elif any(k in role_low for k in ["artist", "music", "idol", "drama", "actor"]):
        priority_traits.extend(["flirtatious", "playful", "eccentric", "warm"])

    all_keys = list(TRAIT_REGISTRY.keys())
    # Deterministic shuffle
    candidates = []
    for pt in priority_traits:
        if pt in TRAIT_REGISTRY and pt not in candidates:
            candidates.append(pt)
    
    for i in range(len(all_keys)):
        idx = (hash_val + i * 7) % len(all_keys)
        k = all_keys[idx]
        if k not in candidates:
            candidates.append(k)

    chosen: List[str] = []
    forbidden: Set[str] = set()

    for cand_id in candidates:
        if cand_id in forbidden:
            continue
        t_data = TRAIT_REGISTRY[cand_id]
        chosen.append(t_data["label"])
        forbidden.add(cand_id)
        forbidden.update(t_data.get("incompatible_with", set()))
        if len(chosen) >= max(2, min(count, 3)):
            break

    return chosen


def assign_npc_preferences(
    seed_str: str,
    traits: List[str] = None,
    role: str = "",
    race: str = ""
) -> Tuple[List[str], List[str]]:
    """
    Deterministically assigns 3 Grounded Likes and 3 Grounded Dislikes:
    - Likes: 1 Food/Drink + 1 Gift Item + 1 Behavioral Stance
    - Dislikes: 1 Food/Gift Dislike + 2 Behavioral Dislikes
    """
    combined = (str(seed_str or "") + "_" + str(role or "") + "_" + str(race or "") + "_" + " ".join(str(t) for t in (traits or []))).lower()
    hash_val = int(hashlib.md5(combined.encode("utf-8")).hexdigest(), 16) if combined else 101

    # 1. Liked Food or Drink (1 item, alternating based on hash)
    if hash_val % 2 == 0:
        consumable_like = GROUNDED_DRINK_LIKES[hash_val % len(GROUNDED_DRINK_LIKES)]
    else:
        consumable_like = GROUNDED_FOOD_LIKES[hash_val % len(GROUNDED_FOOD_LIKES)]
    
    # 2. Liked Gift (1 item)
    gift_like = GROUNDED_GIFT_LIKES[(hash_val // 3) % len(GROUNDED_GIFT_LIKES)]

    # 3. Liked Behavioral Stance (1 item, matching traits if possible)
    behavioral_candidates = list(BEHAVIORAL_LIKES)
    if traits:
        for t_label in traits:
            t_def = get_trait(t_label)
            if t_def:
                if t_def["id"] in ("diligent", "scholarly", "methodical", "perceptive"):
                    behavioral_candidates.insert(0, "Favors Intellectual & Tactical Depth")
                elif t_def["id"] in ("playful", "mischievous"):
                    behavioral_candidates.insert(0, "Favors Playful Wit & Teasing")
                elif t_def["id"] in ("warm", "gentle", "anxious"):
                    behavioral_candidates.insert(0, "Favors Emotional Empathy & Sincerity")
                elif t_def["id"] in ("blunt", "stoic", "honorable"):
                    behavioral_candidates.insert(0, "Favors Direct Candor & Honesty")
                elif t_def["id"] in ("ambitious", "strategic", "commanding"):
                    behavioral_candidates.insert(0, "Favors Strategic Initiative & Drive")
                elif t_def["id"] in ("proud", "appreciative"):
                    behavioral_candidates.insert(0, "Favors Sincere Gratitude & Validation")
                elif t_def["id"] in ("flirtatious",):
                    behavioral_candidates.insert(0, "Favors Playful Flirtation & Romantic Charm")
                elif t_def["id"] in ("devoted", "protective"):
                    behavioral_candidates.insert(0, "Favors Courageous Solidarity & Defense")
    
    behavior_like = behavioral_candidates[(hash_val // 7) % len(behavioral_candidates)]

    likes = [f"Likes {consumable_like}", f"Likes {gift_like}", behavior_like]

    # 4. Disliked Food, Drink or Gift (1 item)
    all_disliked_items = GROUNDED_FOOD_DISLIKES + GROUNDED_DRINK_DISLIKES + GROUNDED_GIFT_DISLIKES
    disliked_item = all_disliked_items[(hash_val // 11) % len(all_disliked_items)]

    # 5. Disliked Behavioral Stances (2 items)
    disliked_behaviors = list(BEHAVIORAL_DISLIKES)
    if traits:
        for t_label in traits:
            t_def = get_trait(t_label)
            if t_def:
                if t_def["id"] in ("proud", "delinquent"):
                    disliked_behaviors.insert(0, "Resents Condescension & Belittling")
                    disliked_behaviors.insert(1, "Resists Micromanagement & Forceful Orders")
                elif t_def["id"] in ("blunt", "stoic", "honorable"):
                    disliked_behaviors.insert(0, "Disdains Dishonesty & Deceit")
                    disliked_behaviors.insert(1, "Rejects Sycophancy & Obsequious Flattery")
                elif t_def["id"] in ("guarded", "hesitant", "anxious"):
                    disliked_behaviors.insert(0, "Aversion to Invasive Prying & Boundary Pushing")
                elif t_def["id"] in ("diligent", "perfectionist", "methodical"):
                    disliked_behaviors.insert(0, "Intolerant of Slacking & Flakiness")
                elif t_def["id"] in ("gentle", "protective"):
                    disliked_behaviors.insert(0, "Repulsed by Bullying & Cruelty")

    b_dislike1 = disliked_behaviors[(hash_val // 13) % len(disliked_behaviors)]
    b_dislike2 = disliked_behaviors[(hash_val // 17 + 1) % len(disliked_behaviors)]
    if b_dislike2 == b_dislike1:
        b_dislike2 = disliked_behaviors[(hash_val // 17 + 2) % len(disliked_behaviors)]

    dislikes = [disliked_item, b_dislike1, b_dislike2]

    return likes[:3], dislikes[:3]


def generate_trait_anchored_mannerisms(
    traits: List[str],
    race: str = "human",
    seed_str: str = ""
) -> List[str]:
    """
    Synthesizes 2-3 distinct mannerisms by combining:
    1. Signature physical habits from assigned traits.
    2. Biological race mannerisms (tail swish, ear twitches, posture).
    """
    combined = (str(seed_str or "") + "_" + str(race or "") + "_" + " ".join(str(t) for t in (traits or []))).lower()
    hash_val = int(hashlib.md5(combined.encode("utf-8")).hexdigest(), 16) if combined else 99

    mannerisms: List[str] = []

    # 1. Trait mannerism
    for t_name in traits:
        t_def = get_trait(t_name)
        if t_def and t_def.get("mannerisms"):
            m_list = t_def["mannerisms"]
            chosen_m = m_list[hash_val % len(m_list)]
            if chosen_m not in mannerisms:
                mannerisms.append(chosen_m)
            if len(mannerisms) >= 2:
                break

    # 2. Race mannerism
    race_low = str(race or "").lower()
    if any(k in race_low for k in ["fox", "kitsune", "vulpine"]):
        fox_quirks = [
            "Fluffy fox tail swishes in rhythmic, expressive beats while speaking",
            "Fox ears twitch forward alertly to catch subtle changes in tone",
            "Smirks with a sly, playful tilt of the head"
        ]
        chosen_r = fox_quirks[hash_val % len(fox_quirks)]
        if chosen_r not in mannerisms:
            mannerisms.append(chosen_r)
    elif any(k in race_low for k in ["cat", "neko", "feline"]):
        cat_quirks = [
            "Cat ears tilt back slightly when assessing unexpected remarks",
            "Tail tip flicks with subtle, calculating curiosity",
            "Stretches shoulders with graceful, feline fluidity"
        ]
        chosen_r = cat_quirks[hash_val % len(cat_quirks)]
        if chosen_r not in mannerisms:
            mannerisms.append(chosen_r)
    elif any(k in race_low for k in ["wolf", "lupine", "canine"]):
        wolf_quirks = [
            "Wolf ears prick upward with sharp, direct attentiveness",
            "Maintains a bold, unwavering stare while squaring shoulders",
            "Tail wags with controlled, measured poise when pleased"
        ]
        chosen_r = wolf_quirks[hash_val % len(wolf_quirks)]
        if chosen_r not in mannerisms:
            mannerisms.append(chosen_r)
    elif any(k in race_low for k in ["dragon", "draconic"]):
        dragon_quirks = [
            "Draconic tail sways with heavy, regal authority",
            "Exhales a warm, measured breath while maintaining proud posture",
            "Gold-flecked eyes narrow with sharp, predatory focus"
        ]
        chosen_r = dragon_quirks[hash_val % len(dragon_quirks)]
        if chosen_r not in mannerisms:
            mannerisms.append(chosen_r)
    elif any(k in race_low for k in ["elf", "elven"]):
        elf_quirks = [
            "Long elven ears tilt with refined, aristocratic attentiveness",
            "Maintains pristine, effortless posture with fingers loosely clasped",
            "Speaks with poised, melodic cadence"
        ]
        chosen_r = elf_quirks[hash_val % len(elf_quirks)]
        if chosen_r not in mannerisms:
            mannerisms.append(chosen_r)

    # Fallback if still under 2
    if len(mannerisms) < 2:
        general_quirks = [
            "Maintains engaged, thoughtful eye contact while listening",
            "Gestures naturally with open hands when explaining points",
            "Offers an authentic, grounded smile during pleasant exchanges"
        ]
        for g in general_quirks:
            if g not in mannerisms:
                mannerisms.append(g)
            if len(mannerisms) >= 2:
                break

    return mannerisms[:3]


def format_trait_behavioral_prompt(traits: List[str], partner_name: str = "the character") -> str:
    """
    Synthesizes active traits into clear, actionable behavioral rules for LLM prompt injection.
    """
    if not traits:
        return ""

    speech_rules = []
    body_rules = []
    badge_summaries = []

    for t_name in traits:
        t_def = get_trait(t_name)
        if not t_def:
            continue
        badge_summaries.append(f"{t_def['label']} ({t_def['badge']})")
        speech_rules.append(f"• {t_def['label']} Voice: {t_def['speech_style']}")
        for m in t_def.get("mannerisms", [])[:2]:
            if m not in body_rules:
                body_rules.append(m)

    if not speech_rules:
        return ""

    lines = [
        f"- 🎭 CHARACTER TRAITS & BEHAVIORAL ANCHORS (Talking to {partner_name}):",
        f"  * Active Traits: {', '.join(badge_summaries)}",
        f"  * Dialogue Voice & Speech Mandates:",
    ]
    for sr in speech_rules:
        lines.append(f"    {sr}")
    
    if body_rules:
        lines.append(f"  * Physical Body Language Mandates: Weave their established physical mannerisms naturally into dialogue tags (e.g. {'; '.join(body_rules[:2])}).")

    return "\n".join(lines) + "\n"


def get_combined_dc_modifiers(traits: List[str]) -> Dict[str, int]:
    """Combines skill check DC modifiers across all active traits for an NPC."""
    mods = {"STR": 0, "AGI": 0, "END": 0, "INT": 0, "PER": 0, "CHA": 0, "LUK": 0}
    for t_name in traits:
        t_def = get_trait(t_name)
        if t_def and "dc_modifiers" in t_def:
            for stat, delta in t_def["dc_modifiers"].items():
                if stat in mods:
                    mods[stat] += delta
    return mods


def _matches_trigger_word(trigger: str, text: str) -> bool:
    if not trigger or not text:
        return False
    tr = trigger.strip()
    return bool(re.search(r'\b' + re.escape(tr) + r'\b', text, re.IGNORECASE))


def evaluate_trait_and_preference_impact(
    action_label: str,
    traits: List[str],
    preferences: List[str],
    base_delta: int = 2
) -> Tuple[int, List[str]]:
    """
    Evaluates player's chosen action against NPC's active traits & preferences.
    Returns (modified_affinity_delta, list_of_reasons).
    NOTE: Likes & Dislikes affect ONLY affinity gain/loss.
    """
    if not action_label or not isinstance(action_label, str):
        return base_delta, []

    act_low = action_label.lower()
    delta = base_delta
    notes: List[str] = []

    # 1. Evaluate Behavioral Likes
    for pref in (preferences or []):
        p_clean = str(pref).strip()
        p_low = p_clean.lower()
        if is_gift_item(p_clean):
            continue

        for s_id, s_data in SOCIAL_STANCES_LIKES.items():
            if s_data["label"].lower() in p_low or s_id in p_low:
                if any(_matches_trigger_word(tr, act_low) for tr in s_data["triggers"]):
                    delta += s_data["bonus"]
                    notes.append(f"{s_data['label']} (+{s_data['bonus']})")
                    break

    # 2. Evaluate Behavioral Dislikes
    for pref in (preferences or []):
        p_clean = str(pref).strip()
        p_low = p_clean.lower()
        if is_gift_item(p_clean):
            continue

        for s_id, s_data in SOCIAL_STANCES_DISLIKES.items():
            if s_data["label"].lower() in p_low or s_id in p_low:
                if any(_matches_trigger_word(tr, act_low) for tr in s_data["triggers"]):
                    delta += s_data["penalty"]
                    notes.append(f"{s_data['label']} ({s_data['penalty']})")
                    break

    # 3. Evaluate Physical Gift Preferences (Food, Drink, Gifts)
    for pref in (preferences or []):
        p_clean = str(pref).strip()
        if is_gift_item(p_clean):
            p_core = re.sub(r'^(likes|dislikes|prefers|loves|enjoys|hates|fears)\s+', '', p_clean, flags=re.IGNORECASE).strip().lower()
            is_dislike_pref = any(p_clean.lower().startswith(kw) for kw in ("dislikes", "hates", "fears"))
            if p_core and (p_core in act_low or _matches_trigger_word(p_core, act_low)):
                if is_dislike_pref:
                    delta -= 3
                    notes.append(f"Dislikes gift: {p_core} (-3)")
                else:
                    delta += 3
                    notes.append(f"Loves gift: {p_core} (+3)")
                break

    # 4. Apply Trait Multipliers when action resonated with character profile
    gain_mult = 1.0
    loss_mult = 1.0
    for t_name in (traits or []):
        t_def = get_trait(t_name)
        if t_def:
            gain_mult *= t_def.get("affinity_gain_mult", 1.0)
            loss_mult *= t_def.get("affinity_loss_mult", 1.0)

    if notes:
        if delta > 0:
            delta = max(1, round(delta * gain_mult))
        elif delta < 0:
            delta = min(-1, round(delta * loss_mult))

    return delta, notes

