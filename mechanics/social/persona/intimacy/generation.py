from __future__ import annotations
from .constants import *
import json
import hashlib
import re
from typing import Dict, Any, List, Optional
from ..core import *

def generate_dynamic_turn_ons_and_spots(hash_val: int, race: str = "", dynamic: str = "") -> tuple[str, str]:
    """Dynamically generates separate Sensitive Spots (Physical) and Turn-Ons (Action)."""
    race_l = str(race or "").lower()
    dyn_l = str(dynamic or "").lower()

    # 1. Physical Spots Pool
    phys_pool = list(TURN_ON_PHYSICAL_HUMANOID_ITEMS)
    if any(kw in race_l for kw in ("fox", "beast", "wolf", "cat", "neko", "kitsune", "anthro", "rabbit", "bunny", "canine", "feline", "tanuki", "raccoon", "bear", "lion", "tiger", "cheetah", "fennec", "mouse", "rat", "rodent", "ferret", "badger", "weasel", "hybrid", "half_beast", "halfbeast", "demi_human", "beastkin")):
        phys_pool = [x for x in phys_pool if "earlobe" not in x.lower()]
        phys_pool = list(TURN_ON_MAMMALIAN_BEASTFOLK_ITEMS) + phys_pool
    if any(kw in race_l for kw in ("horn", "antler", "deer", "goat", "ram", "bull", "minotaur", "demon", "devil", "tiefling", "oni", "dragon", "drake", "qilin", "sheep", "satyr", "faun")):
        phys_pool = list(TURN_ON_HORNED_ITEMS) + phys_pool
    if any(kw in race_l for kw in ("wing", "avian", "bird", "harpy", "angel", "bat", "dragon", "pegasus", "gryphon", "griffin", "succubus", "seraph")):
        phys_pool = list(TURN_ON_WINGED_ITEMS) + phys_pool
    if any(kw in race_l for kw in ("scale", "scaly", "naga", "snake", "reptile", "dragon", "lizard", "mermaid", "siren", "aquatic", "fish")):
        phys_pool = list(TURN_ON_SCALY_AQUATIC_ITEMS) + phys_pool

    phys_count = 1 + ((hash_val // 13) % 2)  # 1 to 2
    chosen_phys = []
    for i in range(phys_count):
        idx = ((hash_val // (17 + i * 7)) + i * 5) % len(phys_pool)
        item = phys_pool.pop(idx % len(phys_pool))
        chosen_phys.append(f"{item} (Physical)")

    # 2. Action Triggers Pool
    act_count = 1 + ((hash_val // 29) % 2)  # 1 to 2
    act_pool = list(TURN_ON_ACTION_ITEMS)
    synergistic_turns = []
    if any(kw in dyn_l for kw in ("receptive", "surrender", "yielding", "submissive")):
        synergistic_turns = ["Being pinned gently", "Dominant whispers", "Hair stroking & gentle pulling", "Breath against sensitive skin"]
    elif any(kw in dyn_l for kw in ("dominant", "proactive")):
        synergistic_turns = ["Soft breathless moans", "Passionate urgency", "Gentle physical worship", "Playful teasing"]
    elif any(kw in dyn_l for kw in ("insatiable", "high-drive", "voracious")):
        synergistic_turns = ["Passionate urgency", "Breath against sensitive skin", "Sudden warm embraces", "Intimate eye contact"]
    elif any(kw in dyn_l for kw in ("switch", "brat")):
        synergistic_turns = ["Playful teasing", "Light nails along skin", "Gentle nibbling & biting", "Teasing kisses on collarbone"]
    elif any(kw in dyn_l for kw in ("service")):
        synergistic_turns = ["Gentle physical worship", "Intimate eye contact", "Slow undressing"]

    for st in reversed(synergistic_turns):
        if st in act_pool:
            act_pool.remove(st)
            act_pool.insert(0, st)

    chosen_act = []
    for i in range(act_count):
        if i == 0 and synergistic_turns and (((hash_val // 19) % 100) < 75):
            syn_idx = (hash_val // 31) % len(synergistic_turns)
            picked = synergistic_turns[syn_idx]
            if picked in act_pool:
                act_pool.remove(picked)
                chosen_act.append(f"{picked} (Action)")
                continue
        idx = ((hash_val // (31 + i * 11)) + i * 3) % len(act_pool)
        item = act_pool.pop(idx % len(act_pool))
        chosen_act.append(f"{item} (Action)")

    return ", ".join(chosen_phys), ", ".join(chosen_act)

def generate_dynamic_turn_ons(hash_val: int, race: str = "", dynamic: str = "") -> str:
    """Dynamically generates 1-2 Physical items and 1-2 Action items, tagged cleanly with (Physical) and (Action)."""
    phys, act = generate_dynamic_turn_ons_and_spots(hash_val, race=race, dynamic=dynamic)
    return ", ".join([p for p in (phys, act) if p])

def tag_turn_on_items(turn_ons_str: str, race: str = "") -> str:
    """Ensures each item in a turn-ons string is properly tagged as (Physical) or (Action)."""
    if not turn_ons_str or str(turn_ons_str).strip().lower() in ("none", "unknown", "n/a", ""):
        return ""
    items = [x.strip() for x in str(turn_ons_str).split(",") if x.strip()]
    tagged = []

    physical_cues = (
        "ear", "tail", "neck", "nape", "thigh", "waist", "collarbone", "spine", "back", "chest", "sternum",
        "breast", "horn", "antler", "wing", "feather", "scale", "rib", "foot", "feet", "palm", "wrist",
        "jawline", "throat", "belly", "stomach", "hip", "underbust", "flank", "arm", "knee", "navel",
        "shoulder", "crest", "fur", "paw", "joint", "root", "crown", "dorsal", "gill", "skin"
    )
    for it in items:
        if re.search(r'\(\s*action\s*\)', it, flags=re.I):
            c = re.sub(r'\s*\(\s*action\s*\)', '', it, flags=re.I).strip()
            tagged.append(f"{c} (Action)")
        elif re.search(r'\(\s*physical\s*\)', it, flags=re.I):
            c = re.sub(r'\s*\(\s*physical\s*\)', '', it, flags=re.I).strip()
            tagged.append(f"{c} (Physical)")
        else:
            c = it.strip()
            it_l = c.lower()
            if any(cue in it_l for cue in physical_cues):
                tagged.append(f"{c} (Physical)")
            else:
                tagged.append(f"{c} (Action)")
    return ", ".join(tagged)

def generate_dynamic_fetish(hash_val: int, race: str = "", dynamic: str = "", openness: str = "") -> str:
    """Generates exactly 1 fetish with a 25% roll chance, or 'None (Vanilla)' for 75%."""
    has_fetish = ((hash_val // 37) % 100) < 25
    if not has_fetish:
        return "None (Vanilla)"

    pool = list(FETISH_ITEMS)
    race_l = str(race or "").lower()
    dyn_l = str(dynamic or "").lower()

    if any(kw in race_l for kw in ("fox", "beast", "wolf", "cat", "neko", "kitsune", "anthro")):
        if "Petplay & ear/tail caressing" in pool:
            pool.remove("Petplay & ear/tail caressing")
            pool.insert(0, "Petplay & ear/tail caressing")

    synergistic_fets = []
    if any(kw in dyn_l for kw in ("receptive", "surrender", "yielding", "submissive")):
        synergistic_fets = ["Gentle dominance / submission", "Light silk restraints", "Praise kink & verbal validation", "Overstimulation & gentle edging"]
    elif any(kw in dyn_l for kw in ("dominant", "proactive")):
        synergistic_fets = ["Gentle dominance / submission", "Audio stimulation / dirty talk", "Biting & marking", "Collaring & leashes", "Impact play & gentle spanking"]
    elif any(kw in dyn_l for kw in ("insatiable", "high-drive", "voracious")):
        synergistic_fets = ["Overstimulation & gentle edging", "Aftercare obsession", "Public thrill & risk of being caught", "Biting & marking"]
    elif any(kw in dyn_l for kw in ("switch", "brat")):
        synergistic_fets = ["Costume / uniform roleplay", "Temperature play (ice & warmth)", "Biting & marking", "Mirror observation & exhibition"]
    elif any(kw in dyn_l for kw in ("service")):
        synergistic_fets = ["Massage oils & tactile worship", "Aftercare obsession", "Praise kink & verbal validation"]

    if synergistic_fets and (((hash_val // 27) % 100) < 75):
        syn_idx = (hash_val // 43) % len(synergistic_fets)
        return synergistic_fets[syn_idx]

    idx = (hash_val // 43) % len(pool)
    return pool[idx]

def generate_dynamic_turn_offs(hash_val: int, dynamic: str = "", openness: str = "", traits: List[str] = None) -> str:
    """Dynamically generates 1-2 character-appropriate Turn-Offs (mood-killers / aversions)."""
    dyn_l = str(dynamic or "").lower()
    open_l = str(openness or "").lower()
    traits_l = [str(t).lower() for t in (traits or [])]

    pool = list(TURN_OFF_ITEMS)
    favored = []

    if any(kw in dyn_l for kw in ("receptive", "surrender", "yielding", "submissive")):
        favored += ["Clumsy / careless rough handling", "Crude degradation & insults", "Overly aggressive biting or pinching"]
    elif any(kw in dyn_l for kw in ("dominant", "proactive")):
        favored += ["Unearned bossiness & arrogance", "Limp passivity & lack of effort"]
    elif any(kw in dyn_l for kw in ("service")):
        favored += ["Dead silence & emotional detachment", "Purely transactional feeling", "Mocking or laughing at vulnerability"]
    elif any(kw in dyn_l for kw in ("switch", "brat")):
        favored += ["Rushed impatience & entitlement", "Dead silence & emotional detachment", "Unearned bossiness & arrogance"]

    if "prude" in open_l or "modest" in open_l:
        favored += ["Crude degradation & insults", "Lack of discretion & careless exposure", "Poor hygiene & neglect", "Rushed impatience & entitlement"]
    elif "shameless" in open_l or "lewd" in open_l:
        favored += ["Limp passivity & lack of effort", "Smothering clinginess during intimacy", "Dead silence & emotional detachment"]
    else:
        favored += ["Poor hygiene & neglect", "Purely transactional feeling", "Rushed impatience & entitlement"]

    if any("noble" in t or "proud" in t or "knight" in t or "royal" in t for t in traits_l):
        favored += ["Unearned bossiness & arrogance", "Crude degradation & insults"]

    count = 1 + ((hash_val // 71) % 2)  # 1 to 2
    chosen = []
    for f in favored:
        if f in pool and len(chosen) < count:
            if ((hash_val // 79) % 100) < 70:
                chosen.append(f)
                pool.remove(f)

    while len(chosen) < count and pool:
        idx = (hash_val // (83 + len(chosen) * 13)) % len(pool)
        chosen.append(pool.pop(idx))

    return ", ".join(chosen)

def generate_dynamic_desires_and_turn_offs(hash_val: int, race: str = "", dynamic: str = "", openness: str = "moderate", traits: List[str] = None) -> tuple[str, str, str]:
    """Dynamically generates:
    1. Sensitive Spots (pure physical erogenous zones, 1-2 items)
    2. Desires & Kinks (sensory triggers + 25% kink roll, 1-3 items)
    3. Turn-Offs (mood-killers & aversions, 1-2 items)
    """
    phys_str, act_str = generate_dynamic_turn_ons_and_spots(hash_val, race=race, dynamic=dynamic)
    fetish_str = generate_dynamic_fetish(hash_val, race=race, dynamic=dynamic, openness=openness)

    desires_items = [x.strip() for x in act_str.split(",") if x.strip()]
    if fetish_str and fetish_str.lower() not in ("none", "none (vanilla)", "unknown", ""):
        if not any(fetish_str.lower() in d.lower() for d in desires_items):
            desires_items.append(fetish_str)

    desires_str = ", ".join(desires_items)
    turn_offs_str = generate_dynamic_turn_offs(hash_val, dynamic=dynamic, openness=openness, traits=traits)

    return phys_str, desires_str, turn_offs_str

def generate_dynamic_act_preferences(hash_val: int, dynamic: str = "", demeanor: str = "", openness: str = "") -> Dict[str, str]:
    """Dynamically generates 1-2 Likes and 1-2 Dislikes from strictly bedroom acts, positions, and pacing."""
    dyn_l = str(dynamic or "").lower()
    open_l = str(openness or "").lower()

    likes_count = 1 + ((hash_val // 47) % 2)  # 1 to 2
    dislikes_count = 1 + ((hash_val // 53) % 2)  # 1 to 2

    all_ids = [item["id"] for item in ACT_PREFERENCE_REGISTRY]
    name_map = {item["id"]: item["name"] for item in ACT_PREFERENCE_REGISTRY}

    # Dynamic/Openness Synergistic Liked suggestions
    favored_likes = []
    favored_dislikes = []

    if any(kw in dyn_l for kw in ("receptive", "surrender", "yielding", "submissive")):
        favored_likes += ["receiving_oral", "missionary", "slow_sensual", "spooning"]
        favored_dislikes += ["taking_charge", "rough_handling", "fast_urgent"]
    elif any(kw in dyn_l for kw in ("dominant", "proactive")):
        favored_likes += ["taking_charge", "cowgirl_riding", "from_behind", "fast_urgent"]
        favored_dislikes += ["spooning"]
    elif any(kw in dyn_l for kw in ("insatiable", "high-drive", "voracious")):
        favored_likes += ["swallowing", "cowgirl_riding", "fast_urgent", "prolonged_teasing"]
    elif any(kw in dyn_l for kw in ("service")):
        favored_likes += ["giving_oral", "slow_sensual", "swallowing"]

    if "prude" in open_l or "modest" in open_l:
        favored_likes += ["slow_sensual", "missionary", "spooning"]
        favored_dislikes += ["facial", "rough_handling", "fast_urgent"]
    elif "shameless" in open_l or "lewd" in open_l:
        favored_likes += ["swallowing", "facial", "cowgirl_riding", "from_behind"]

    # Select Likes
    chosen_likes_ids = []
    pool_likes = list(all_ids)
    for fl in favored_likes:
        if fl in pool_likes and len(chosen_likes_ids) < likes_count:
            if ((hash_val // 61) % 100) < 70:
                chosen_likes_ids.append(fl)
                pool_likes.remove(fl)

    while len(chosen_likes_ids) < likes_count and pool_likes:
        idx = ((hash_val // (67 + len(chosen_likes_ids) * 17)) + len(chosen_likes_ids) * 7) % len(pool_likes)
        chosen_likes_ids.append(pool_likes.pop(idx))

    # Select Dislikes (Must be disjoint from Likes)
    pool_dislikes = [item_id for item_id in all_ids if item_id not in chosen_likes_ids]
    chosen_dislikes_ids = []

    for fd in favored_dislikes:
        if fd in pool_dislikes and len(chosen_dislikes_ids) < dislikes_count:
            if ((hash_val // 71) % 100) < 70:
                chosen_dislikes_ids.append(fd)
                pool_dislikes.remove(fd)

    while len(chosen_dislikes_ids) < dislikes_count and pool_dislikes:
        idx = ((hash_val // (73 + len(chosen_dislikes_ids) * 19)) + len(chosen_dislikes_ids) * 5) % len(pool_dislikes)
        chosen_dislikes_ids.append(pool_dislikes.pop(idx))

    likes_str = ", ".join(name_map[i] for i in chosen_likes_ids)
    dislikes_str = ", ".join(name_map[i] for i in chosen_dislikes_ids)

    return {
        "likes": likes_str,
        "dislikes": dislikes_str,
        "act_likes": likes_str,
        "act_dislikes": dislikes_str
    }

def generate_dynamic_intimate_experience(hash_val: int, openness: str = "moderate", gender: str = "") -> Dict[str, str]:
    """
    Computes decoupled 4-track experience (Intercourse, Oral, Manual, Anal).
    Base experience chance is 15% across all 3, modified additively by openness tier.
    Enforces biological gender invariants for anal intimacy:
    - Females: can only receive anal or be inexperienced (never 'has_done_anal' or 'has_done_and_received_anal').
    - Males: can give anal to females, and can give or receive anal with males.
    """
    o_low = str(openness or "moderate").lower()
    mod = 0
    if "prude" in o_low or "modest" in o_low:
        mod = -5
    elif "shameless" in o_low or "lewd" in o_low:
        mod = 20
    elif "bold" in o_low or "uninhibited" in o_low:
        mod = 10
    else:
        mod = 0

    exp_rate = max(0, min(100, 15 + mod))

    # 1. Intercourse Track
    roll_intercourse = hash_val % 100
    intercourse_val = "non_virgin" if roll_intercourse < exp_rate else "virgin"

    # 2. Oral Intimacy Track
    roll_oral = (hash_val // 7) % 100
    if roll_oral < exp_rate:
        sub_oral = (hash_val // 11) % 100
        if sub_oral < 40:
            oral_val = "has_done_oral"
        elif sub_oral < 80:
            oral_val = "has_received_oral"
        else:
            oral_val = "has_done_and_received_oral"
    else:
        oral_val = "inexperienced"

    # 3. Manual Intimacy Track
    roll_manual = (hash_val // 13) % 100
    if roll_manual < exp_rate:
        sub_man = (hash_val // 17) % 100
        if sub_man < 40:
            manual_val = "has_done_manual"
        elif sub_man < 80:
            manual_val = "has_received_manual"
        else:
            manual_val = "has_done_and_received_manual"
    else:
        manual_val = "inexperienced"

    # 4. Anal Intimacy Track
    anal_rate = max(0, min(100, 8 + mod))
    roll_anal = (hash_val // 19) % 100
    if roll_anal < anal_rate:
        raw_g = str(gender or "").lower()
        is_female = any(kw in raw_g for kw in ("female", "woman", "girl", "lady", "she", "her"))
        if not is_female and raw_g:
            is_male = any(kw in raw_g for kw in ("male", "man", "boy", "lord", "he", "him", "his")) and not any(kw in raw_g for kw in ("female", "woman"))
            is_female = not is_male
        if is_female:
            # Biological invariant: Female characters can only receive anal intimacy, never give
            anal_val = "has_received_anal"
        else:
            sub_anal = (hash_val // 23) % 100
            if sub_anal < 40:
                anal_val = "has_done_anal"
            elif sub_anal < 80:
                anal_val = "has_received_anal"
            else:
                anal_val = "has_done_and_received_anal"
    else:
        anal_val = "inexperienced"

    return {
        "intercourse": intercourse_val,
        "oral": oral_val,
        "manual": manual_val,
        "anal": anal_val
    }

def generate_dynamic_intimate_attributes(hash_val: int, race: str = "", gender: str = "", dynamic: str = "", openness: str = "moderate", traits: List[str] = None) -> Dict[str, Any]:
    """Dynamically generates sensitive spots, desires & kinks, turn-offs, symmetrical act preferences, 4-track experience, and undergarments."""
    phys_str, desires_str, turn_offs_str = generate_dynamic_desires_and_turn_offs(hash_val, race=race, dynamic=dynamic, openness=openness, traits=traits)
    fetish_str = generate_dynamic_fetish(hash_val, race=race, dynamic=dynamic, openness=openness)
    act_prefs = generate_dynamic_act_preferences(hash_val, dynamic=dynamic, openness=openness)
    experience = generate_dynamic_intimate_experience(hash_val, openness=openness, gender=gender)
    undergarments = generate_procedural_undergarments(gender=gender, openness=openness, dynamic=dynamic, hash_val=hash_val)

    return {
        "sensitive_spots": phys_str,
        "turn_ons": desires_str,
        "turn_offs": turn_offs_str,
        "desires_and_kinks": desires_str,
        "combined_turn_ons": desires_str,
        "fetishes": fetish_str,
        "act_likes": act_prefs["likes"],
        "act_dislikes": act_prefs["dislikes"],
        "intercourse": experience["intercourse"],
        "oral": experience["oral"],
        "manual": experience["manual"],
        "anal": experience["anal"],
        "undergarments": undergarments
    }

def generate_intimate_synergy_tip(name: str, discovered: Dict[str, Any], info_level: int = 1) -> Dict[str, str]:
    """Generates an actionable intimate synergy helper tip based on discovered intimate traits."""
    spots = discovered.get("turn_ons") or discovered.get("sensitive_spots")
    likes = discovered.get("act_likes")
    fetish = discovered.get("fetishes")
    dynamic = discovered.get("dynamic")
    demeanor = discovered.get("demeanor")

    if spots or likes or fetish or dynamic or demeanor:
        trigger_parts = []
        if spots:
            clean_s = ", ".join([x.replace("(Physical)", "").replace("(Action)", "").strip() for x in str(spots).split(",") if x.strip()])
            trigger_parts.append(f"{clean_s.lower()}")
        if likes:
            trigger_parts.append(f"initiating {likes.lower()}")

        trigger_phrase = " or ".join(trigger_parts) if trigger_parts else "their intimate turn-ons"
        dyn_phrase = f"matches their {dynamic} dynamic" if dynamic else (f"appeals to their {demeanor} nature" if demeanor else "pleases them deeply")

        msg = (
            f"✨ **Active Synergy (+2 to +4 Bonus)**: Choices that target {name}'s {trigger_phrase} "
            f"directly {dyn_phrase}, granting a **+2 to +4 bonus** to check resolution during intimate and romantic scenes."
        )
        if fetish and fetish not in ("None", "None (Vanilla)"):
            msg += f" Indulging their kink (*{fetish}*) grants a massive affinity surge."
        turn_offs = discovered.get("turn_offs")
        if turn_offs and turn_offs not in ("None", "Unknown", ""):
            msg += f" ⚠️ **Turn-Off Warning**: Triggering their aversions (*{turn_offs}*) causes an immediate DC penalty (+5) and severe affinity loss."

        return {
            "name": "💡 Active Intimate Synergy & Modifiers",
            "value": msg
        }
    else:
        return {
            "name": "🔒 Intimate Synergy",
            "value": (
                f"*Synergy triggers are undiscovered. Reaching Level 3/3 Disclosure or unlocking intimate "
                f"encounters with {name} will reveal actions that grant a **+2 to +4 bonus** during intimate choices.*"
            )
        }

def generate_past_partner_role(scenario: str = "fantasy", hash_val: int = 0) -> str:
    """Dynamically rolls a setting-appropriate role for past partners from namegen_data.json."""
    try:
        from namegen import generate_role
        return generate_role(scenario=scenario, hash_val=hash_val)
    except Exception:
        return "Former Classmate"

def generate_past_partner_name(scenario: str = "fantasy", partner_gender: str = "male", hash_val: int = 0) -> str:
    """Dynamically generates a past partner name from namegen_data according to scenario and gender."""
    try:
        from namegen import _get_scenario_data
        data = _get_scenario_data(scenario, "person")
    except Exception:
        data = {}

    male_pool = data.get("male") or [
        "Julian", "Marcus", "Leon", "Adrian", "Lucas", "Darius", "Ethan", "Cyrus",
        "Alexander", "Cedric", "Damian", "Soren", "Felix", "Tristan", "Victor", "Gabriel"
    ]
    female_pool = data.get("female") or [
        "Elena", "Seraphina", "Cassandra", "Valerie", "Vivian", "Chloe", "Camilla", "Iris",
        "Morgan", "Hana", "Maya", "Lyra", "Giselle", "Natalia", "Astrid", "Evelyn"
    ]
    last_pool = data.get("last") or [
        "Vance", "Reed", "Drake", "Cross", "Sterling", "Thorne", "Cole", "Black",
        "Wright", "Finch", "Blackwood", "Mercer", "Ashwood", "Volkov", "Ward", "Hayes"
    ]

    is_female = ("female" in partner_gender.lower() or "woman" in partner_gender.lower() or "girl" in partner_gender.lower())
    pool = female_pool if is_female else male_pool

    first_idx = (hash_val * 37 + 11) % len(pool)
    first = pool[first_idx]

    surname_chance = data.get("surname_chance", 0.8)
    if last_pool and ((hash_val * 13 + 7) % 100) < int(surname_chance * 100):
        last_idx = (hash_val * 53 + 23) % len(last_pool)
        last = last_pool[last_idx]
        return f"{first} {last}"
    return first

def generate_past_intimate_history(
    hash_val: int = 0,
    race: str = "",
    gender: str = "",
    scenario: str = "fantasy",
    openness: str = "moderate",
    intercourse: str = "",
    oral: str = "",
    manual: str = "",
    anal: str = "",
    has_existing_partner: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Generates a structured past intimate history record with 4-tier scaling across
    Prude (1-2 partners, 1-3 times), Moderate (1-2 partners, 1-4 times),
    Bold (1-4 partners, 3-8 times), and Shameless (2-5 partners, 5-15+ times + affair chance).
    STRICT SAFEGUARD: If purely virgin and inexperienced across all tracks, returns None.
    """
    i_state = (intercourse or "virgin").strip().lower()
    o_state = (oral or "inexperienced").strip().lower()
    m_state = (manual or "inexperienced").strip().lower()
    a_state = (anal or "inexperienced").strip().lower()

    if i_state in ("virgin", "unknown", "") and o_state in ("inexperienced", "unknown", "none", "") and m_state in ("inexperienced", "unknown", "none", "") and a_state in ("inexperienced", "unknown", "none", ""):
        return None

    raw_g = str(gender or "").strip().lower()
    is_char_male = any(kw in raw_g for kw in ("male", "man", "boy", "lord", "he", "him", "his")) and not any(kw in raw_g for kw in ("female", "woman"))
    is_char_female = not is_char_male

    # Biological gender invariant for anal intimacy:
    # Female characters can only receive anal intimacy. They can never give / perform anal.
    if is_char_female and a_state in ("has_done_anal", "has_done_and_received_anal"):
        a_state = "has_received_anal"

    open_l = str(openness or "moderate").lower()

    # 4-Tier Past Partner Scaling
    if "prude" in open_l or "modest" in open_l:
        partner_count = 1 + ((hash_val // 19) % 2)  # 1 to 2
        base_enc_min, base_enc_max = 1, 3
    elif "shameless" in open_l or "lewd" in open_l:
        partner_count = 2 + ((hash_val // 19) % 4)  # 2 to 5
        base_enc_min, base_enc_max = 5, 15
    elif "bold" in open_l or "uninhibited" in open_l:
        partner_count = 1 + ((hash_val // 19) % 4)  # 1 to 4
        base_enc_min, base_enc_max = 3, 8
    else:
        partner_count = 1 + ((hash_val // 19) % 2)  # 1 to 2
        base_enc_min, base_enc_max = 1, 4

    is_shameless = "shameless" in open_l or "lewd" in open_l
    has_affair = is_shameless and (has_existing_partner or (((hash_val // 31) % 100) < 70 and partner_count >= 2))

    entries = []
    partners_data = []
    structured_events = []

    for p_idx in range(partner_count):
        p_hash = hash_val + p_idx * 79 + 17

        # Partner gender determination:
        # Females have male partners.
        # Males: if engaging in received anal (or mutual anal), the partner must be male (M/M).
        # Otherwise default partner is female.
        if is_char_female:
            partner_gender = "male"
        else:
            if a_state in ("has_received_anal", "has_done_and_received_anal"):
                partner_gender = "male"
            else:
                partner_gender = "female"

        partner_name = generate_past_partner_name(scenario=scenario, partner_gender=partner_gender, hash_val=p_hash)
        role = generate_past_partner_role(scenario=scenario, hash_val=p_hash)

        enc_range = max(1, base_enc_max - base_enc_min + 1)
        count = base_enc_min + (p_hash % enc_range)
        count_str = "1 time" if count == 1 else f"{count} times"

        is_this_affair = has_affair and p_idx >= 1
        role_label = f"{role}, Secret Affair" if is_this_affair else role

        has_intercourse = (i_state == "non_virgin") and (
            p_idx == 0 or (is_shameless and (p_hash % 2 == 0)) or (o_state == "inexperienced" and m_state == "inexperienced" and a_state == "inexperienced") or (p_hash % 2 == 0)
        )
        has_oral = (o_state != "inexperienced")
        has_manual = (m_state != "inexperienced")
        has_anal = (a_state != "inexperienced")

        ic_count = count
        ic_str = "1 time" if ic_count == 1 else f"{ic_count} times"

        o_count = base_enc_min + ((p_hash // 7) % enc_range)
        o_str = "1 time" if o_count == 1 else f"{o_count} times"

        m_count = base_enc_min + ((p_hash // 11) % enc_range)
        m_str = "1 time" if m_count == 1 else f"{m_count} times"

        a_count = base_enc_min + ((p_hash // 13) % enc_range)
        a_str = "1 time" if a_count == 1 else f"{a_count} times"

        oral_act = ""
        oral_participle = ""
        if has_oral:
            if o_state == "has_done_oral":
                oral_act = f"performed oral ({o_str})"
                oral_participle = f"performing oral ({o_str})"
            elif o_state == "has_received_oral":
                oral_act = f"received oral ({o_str})"
                oral_participle = f"receiving oral ({o_str})"
            else:
                oral_act = f"performed & received oral ({o_str})"
                oral_participle = f"performing & receiving oral ({o_str})"

        manual_act = ""
        manual_participle = ""
        if has_manual:
            if m_state == "has_done_manual":
                manual_act = f"manually stimulated partner ({m_str})"
                manual_participle = f"manually stimulating partner ({m_str})"
            elif m_state == "has_received_manual":
                manual_act = f"received manual stimulation ({m_str})"
                manual_participle = f"receiving manual stimulation ({m_str})"
            else:
                manual_act = f"mutual manual foreplay ({m_str})"
                manual_participle = f"engaging in mutual manual foreplay ({m_str})"

        anal_act = ""
        anal_participle = ""
        if has_anal:
            if is_char_female or a_state == "has_received_anal":
                anal_act = f"received anal ({a_str})"
                anal_participle = f"receiving anal ({a_str})"
            elif a_state == "has_done_anal":
                anal_act = f"performed anal ({a_str})"
                anal_participle = f"performing anal ({a_str})"
            else:
                anal_act = f"engaged in anal intimacy ({a_str})"
                anal_participle = f"engaging in anal intimacy ({a_str})"

        # Collect structured events for this partner
        if has_intercourse:
            structured_events.append({
                "act_type": "intercourse",
                "direction": "mutual",
                "count": ic_count,
                "partner_name": partner_name,
                "partner_role": role_label,
                "is_secret_affair": is_this_affair,
                "is_physical": True,
                "partner_gender": partner_gender,
                "turn_number": 0,
                "event_origin": "past_history"
            })
        if has_oral:
            o_dir = "give" if o_state == "has_done_oral" else ("receive" if o_state == "has_received_oral" else "mutual")
            structured_events.append({
                "act_type": "oral",
                "direction": o_dir,
                "count": o_count,
                "partner_name": partner_name,
                "partner_role": role_label,
                "is_secret_affair": is_this_affair,
                "is_physical": True,
                "partner_gender": partner_gender,
                "turn_number": 0,
                "event_origin": "past_history"
            })
        if has_manual:
            m_dir = "give" if m_state == "has_done_manual" else ("receive" if m_state == "has_received_manual" else "mutual")
            structured_events.append({
                "act_type": "manual",
                "direction": m_dir,
                "count": m_count,
                "partner_name": partner_name,
                "partner_role": role_label,
                "is_secret_affair": is_this_affair,
                "is_physical": True,
                "partner_gender": partner_gender,
                "turn_number": 0,
                "event_origin": "past_history"
            })
        if has_anal:
            if is_char_female:
                a_dir = "receive"
            elif a_state == "has_done_anal":
                a_dir = "give"
            elif a_state == "has_received_anal":
                a_dir = "receive"
            else:
                a_dir = "mutual"
            structured_events.append({
                "act_type": "anal",
                "direction": a_dir,
                "count": a_count,
                "partner_name": partner_name,
                "partner_role": role_label,
                "is_secret_affair": is_this_affair,
                "is_physical": True,
                "partner_gender": partner_gender,
                "turn_number": 0,
                "event_origin": "past_history"
            })

        # Multi-act synthesis
        if has_intercourse and has_oral and has_manual and has_anal:
            if is_this_affair:
                entry = f"Past History: Secret affair ({count_str}) by having intercourse ({ic_str}), {oral_participle}, {manual_participle} & {anal_participle} with '{partner_name}' ({role}) behind partner's back"
            elif ic_count == 1 and p_idx == 0:
                entry = f"Past History: Lost virginity & had intercourse (1 time), {oral_act}, {manual_act} and {anal_act} during a relationship with '{partner_name}' ({role})"
            else:
                entry = f"Past History: Had intercourse ({ic_str}), {oral_act}, {manual_act} & {anal_act} during a relationship with '{partner_name}' ({role})"
        elif has_intercourse and has_oral and has_anal:
            if is_this_affair:
                entry = f"Past History: Secret affair ({count_str}) by having intercourse ({ic_str}), {oral_participle} & {anal_participle} with '{partner_name}' ({role}) behind partner's back"
            elif ic_count == 1 and p_idx == 0:
                entry = f"Past History: Lost virginity & had intercourse (1 time), {oral_act} and {anal_act} during a relationship with '{partner_name}' ({role})"
            else:
                entry = f"Past History: Had intercourse ({ic_str}), {oral_act} & {anal_act} during a relationship with '{partner_name}' ({role})"
        elif has_intercourse and has_oral and has_manual:
            if is_this_affair:
                entry = f"Past History: Secret affair ({count_str}) by having intercourse ({ic_str}), {oral_participle} & {manual_participle} with '{partner_name}' ({role}) behind partner's back"
            elif ic_count == 1 and p_idx == 0:
                entry = f"Past History: Lost virginity & had intercourse (1 time), {oral_act} and {manual_act} during a relationship with '{partner_name}' ({role})"
            else:
                entry = f"Past History: Had intercourse ({ic_str}), {oral_act} & {manual_act} during a relationship with '{partner_name}' ({role})"
        elif has_intercourse and has_anal and has_manual:
            if is_this_affair:
                entry = f"Past History: Secret affair ({count_str}) by having intercourse ({ic_str}), {manual_participle} & {anal_participle} with '{partner_name}' ({role}) behind partner's back"
            elif ic_count == 1 and p_idx == 0:
                entry = f"Past History: Lost virginity & had intercourse (1 time), {manual_act} and {anal_act} during a relationship with '{partner_name}' ({role})"
            else:
                entry = f"Past History: Had intercourse ({ic_str}), {manual_act} & {anal_act} during a relationship with '{partner_name}' ({role})"
        elif has_intercourse and has_oral:
            if is_this_affair:
                entry = f"Past History: Secret affair ({count_str}) by having intercourse ({ic_str}) & {oral_participle} with '{partner_name}' ({role}) behind partner's back"
            elif ic_count == 1 and p_idx == 0:
                entry = f"Past History: Lost virginity & had intercourse (1 time) and {oral_act} during a relationship with '{partner_name}' ({role})"
            else:
                entry = f"Past History: Had intercourse ({ic_str}) & {oral_act} during a relationship with '{partner_name}' ({role})"
        elif has_intercourse and has_anal:
            if is_this_affair:
                entry = f"Past History: Secret affair ({count_str}) by having intercourse ({ic_str}) & {anal_participle} with '{partner_name}' ({role}) behind partner's back"
            elif ic_count == 1 and p_idx == 0:
                entry = f"Past History: Lost virginity & had intercourse (1 time) and {anal_act} during a relationship with '{partner_name}' ({role})"
            else:
                entry = f"Past History: Had intercourse ({ic_str}) & {anal_act} during a relationship with '{partner_name}' ({role})"
        elif has_intercourse and has_manual:
            if is_this_affair:
                entry = f"Past History: Secret affair ({count_str}) by having intercourse ({ic_str}) & {manual_participle} with '{partner_name}' ({role}) behind partner's back"
            elif ic_count == 1 and p_idx == 0:
                entry = f"Past History: Lost virginity & had intercourse (1 time) and {manual_act} during a relationship with '{partner_name}' ({role})"
            else:
                entry = f"Past History: Had intercourse ({ic_str}) & {manual_act} during a relationship with '{partner_name}' ({role})"
        elif has_intercourse:
            if is_this_affair:
                entry = f"Past History: Secret affair ({count_str}) by having intercourse ({ic_str}) with '{partner_name}' ({role}) behind partner's back"
            elif ic_count == 1 and p_idx == 0:
                entry = f"Past History: Lost virginity and had intercourse 1 time with '{partner_name}' ({role})"
            else:
                entry = f"Past History: Had intercourse {count_str} during a relationship with '{partner_name}' ({role})"
        elif has_oral and has_anal and has_manual:
            if is_this_affair:
                entry = f"Past History: Secret affair ({count_str}) through {oral_participle}, {manual_participle} & {anal_participle} with '{partner_name}' ({role}) behind partner's back"
            else:
                entry = f"Past History: Engaged in {oral_act}, {manual_act} & {anal_act} during a relationship with '{partner_name}' ({role})"
        elif has_oral and has_anal:
            if is_this_affair:
                entry = f"Past History: Secret affair ({count_str}) by {oral_participle} & {anal_participle} with '{partner_name}' ({role}) behind partner's back"
            else:
                entry = f"Past History: Engaged in {oral_act} & {anal_act} during a relationship with '{partner_name}' ({role})"
        elif has_oral and has_manual:
            if is_this_affair:
                entry = f"Past History: Secret affair ({count_str}) through {oral_participle} & {manual_participle} with '{partner_name}' ({role}) behind partner's back"
            else:
                entry = f"Past History: Engaged in {oral_act} & {manual_act} during a relationship with '{partner_name}' ({role})"
        elif has_anal and has_manual:
            if is_this_affair:
                entry = f"Past History: Secret affair ({count_str}) through {manual_participle} & {anal_participle} with '{partner_name}' ({role}) behind partner's back"
            else:
                entry = f"Past History: Engaged in {manual_act} & {anal_act} during a relationship with '{partner_name}' ({role})"
        elif has_oral:
            if o_state == "has_done_oral":
                if is_this_affair:
                    entry = f"Past History: Secret affair ({count_str}) by performing oral ({count_str}) with '{partner_name}' ({role}) behind partner's back"
                else:
                    entry = f"Past History: Performed oral {count_str} with '{partner_name}' ({role})"
            elif o_state == "has_received_oral":
                if is_this_affair:
                    entry = f"Past History: Secret affair ({count_str}) by receiving oral ({count_str}) from '{partner_name}' ({role}) behind partner's back"
                else:
                    entry = f"Past History: Received oral {count_str} from '{partner_name}' ({role})"
            else:
                if is_this_affair:
                    entry = f"Past History: Secret affair ({count_str}) through mutual oral intimacy ({count_str}) with '{partner_name}' ({role}) behind partner's back"
                else:
                    entry = f"Past History: Engaged in mutual oral intimacy ({count_str}) with '{partner_name}' ({role})"
        elif has_anal:
            if is_char_female or a_state == "has_received_anal":
                if is_this_affair:
                    entry = f"Past History: Secret affair ({count_str}) by receiving anal ({count_str}) from '{partner_name}' ({role}) behind partner's back"
                else:
                    entry = f"Past History: Received anal {count_str} from '{partner_name}' ({role})"
            elif a_state == "has_done_anal":
                if is_this_affair:
                    entry = f"Past History: Secret affair ({count_str}) by performing anal ({count_str}) with '{partner_name}' ({role}) behind partner's back"
                else:
                    entry = f"Past History: Performed anal {count_str} with '{partner_name}' ({role})"
            else:
                if is_this_affair:
                    entry = f"Past History: Secret affair ({count_str}) through anal intimacy ({count_str}) with '{partner_name}' ({role}) behind partner's back"
                else:
                    entry = f"Past History: Engaged in anal intimacy ({count_str}) with '{partner_name}' ({role})"
        elif has_manual:
            if is_this_affair:
                entry = f"Past History: Secret affair ({count_str}) through manual intimacy with '{partner_name}' ({role}) behind partner's back"
            elif m_state == "has_done_manual":
                entry = f"Past History: Manually stimulated '{partner_name}' ({role}) {count_str}"
            elif m_state == "has_received_manual":
                entry = f"Past History: Received manual stimulation from '{partner_name}' ({role}) {count_str}"
            else:
                entry = f"Past History: Mutual manual petting & foreplay ({count_str}) with '{partner_name}' ({role})"
        else:
            entry = f"Past History: Prior intimate encounter ({count_str}) with '{partner_name}' ({role})"

        entries.append(entry)
        partners_data.append({
            "partner_name": partner_name,
            "partner_role": role_label,
            "count": count,
            "is_affair": is_this_affair
        })

    return {
        "entry": "\n".join(entries),
        "entries": entries,
        "events": structured_events,
        "partner_count": partner_count,
        "partner_name": partners_data[0]["partner_name"] if partners_data else "",
        "partner_role": partners_data[0]["partner_role"] if partners_data else "",
        "act_type": i_state,
        "count": partners_data[0]["count"] if partners_data else 1,
        "partners": partners_data
    }


def persist_generated_past_history(
    session_id: int,
    character_id: str,
    history_dict: Optional[Dict[str, Any]],
    character_gender: str = "",
    conn: Optional[Any] = None
) -> int:
    """
    Inserts all events from a generated past history dict into intimate_events table.
    Guarantees no duplicate past events are created if they already exist for (session_id, character_id).
    """
    if not history_dict or not session_id or not character_id:
        return 0
    from .ledger import record_intimate_event, get_intimate_events
    existing = get_intimate_events(session_id, character_id, origin="past_history", conn=conn)
    if existing:
        return 0

    events = history_dict.get("events") or []
    inserted = 0
    for ev in events:
        record_intimate_event(
            session_id=session_id,
            character_id=character_id,
            partner_name=ev.get("partner_name", "Past Partner"),
            act_type=ev.get("act_type", "intercourse"),
            direction=ev.get("direction", "mutual"),
            partner_id=None,
            partner_role=ev.get("partner_role", "Former Classmate"),
            turn_number=0,
            event_origin="past_history",
            is_physical=bool(ev.get("is_physical", True)),
            count=ev.get("count", 1),
            climax_count=0,
            is_secret_affair=bool(ev.get("is_secret_affair", False)),
            narrative_summary=ev.get("narrative_summary", ""),
            character_gender=character_gender,
            partner_gender=ev.get("partner_gender", ""),
            is_reciprocal=False,
            conn=conn
        )
        inserted += 1
    return inserted

