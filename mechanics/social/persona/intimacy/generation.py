from __future__ import annotations
from .constants import *
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

def _openness_tier(openness: str) -> str:
    o = str(openness or "").strip().lower()
    if any(k in o for k in ("prude", "modest", "chaste", "guarded")):
        return "prude"
    if any(k in o for k in ("shameless", "lewd", "pervert", "hedonist")):
        return "shameless"
    if any(k in o for k in ("bold", "uninhibited")):
        return "bold"
    return "moderate"


def _is_female_gender(gender: str) -> bool:
    return is_female_gender(gender)


_TURN_OFF_GENERIC_WORDS = frozenset({
    "during", "intimacy", "feeling", "careless", "handling", "overly",
    "lack", "purely", "without", "their", "against", "play",
})


def _turn_off_matches_key(to_name: str, to_lower: str) -> bool:
    if not to_name or not to_lower:
        return False
    tn_l = to_name.lower()
    if tn_l in to_lower:
        return True
    dist_words = [
        w for w in re.split(r'[\s/&,\-]+', tn_l)
        if len(w) >= 4 and w not in _TURN_OFF_GENERIC_WORDS
    ]
    if not dist_words:
        return False
    return any(re.search(r'\b' + re.escape(w) + r'\b', to_lower) for w in dist_words)


def _act_tokens_to_ids(raw_acts: Any) -> set[str]:
    if not raw_acts:
        return set()
    if isinstance(raw_acts, (list, tuple, set)):
        parts = [str(p or "").strip().lower() for p in raw_acts if str(p or "").strip()]
    else:
        parts = [p.strip().lower() for p in str(raw_acts).split(",") if p.strip()]
    out: set[str] = set()
    for p in parts:
        for item in ACT_PREFERENCE_REGISTRY:
            if p == item["id"] or p == item["name"].lower() or item["name"].lower() in p or item["id"] in p:
                out.add(item["id"])
    return out


def generate_dynamic_fetish(
    hash_val: int,
    race: str = "",
    dynamic: str = "",
    openness: str = "",
    turn_offs: str = "",
) -> str:
    """Generates at most 1 fetish scaled by openness tier, filtered for Turn-Off conflicts."""
    tier = _openness_tier(openness)
    chance_pct = int(round(OPENNESS_FETISH_CHANCE.get(tier, 0.22) * 100))
    roll = (abs(int(hash_val or 0)) // 37) % 100
    if roll >= chance_pct:
        return "None (Vanilla)"

    blocked_fets: set[str] = set()
    to_l = str(turn_offs or "").lower()
    if to_l:
        for to_name, f_set in TURN_OFF_VS_FETISH_CONFLICTS.items():
            if _turn_off_matches_key(to_name, to_l):
                blocked_fets.update(f_set)

    if tier == "prude":
        pool = [f for f in SOFT_ROMANTIC_FETISH_ITEMS if f not in blocked_fets]
    elif tier == "moderate":
        pool = [f for f in FETISH_ITEMS if f not in MODERATE_EXCLUDED_FETISH_ITEMS and f not in blocked_fets]
    else:
        pool = [f for f in FETISH_ITEMS if f not in blocked_fets]

    if not pool:
        return "None (Vanilla)"

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
    elif "service" in dyn_l:
        synergistic_fets = ["Massage oils & tactile worship", "Aftercare obsession", "Praise kink & verbal validation"]

    eligible_syn = [f for f in synergistic_fets if f in pool]
    if eligible_syn and (((abs(int(hash_val or 0)) // 27) % 100) < 75):
        syn_idx = (abs(int(hash_val or 0)) // 43) % len(eligible_syn)
        return eligible_syn[syn_idx]

    idx = (abs(int(hash_val or 0)) // 43) % len(pool)
    return pool[idx]


def generate_dynamic_turn_offs(
    hash_val: int,
    dynamic: str = "",
    openness: str = "",
    traits: List[str] = None,
    fetishes: str = "",
    act_likes: str = "",
) -> str:
    """Dynamically generates 1-2 character-appropriate Turn-Offs (mood-killers / aversions), avoiding direct self-contradictions."""
    dyn_l = str(dynamic or "").lower()
    open_l = str(openness or "").lower()
    traits_l = [str(t).lower() for t in (traits or [])]

    blocked_turn_offs: set[str] = set()
    fet_l = str(fetishes or "").lower()
    if fet_l and fet_l not in ("none", "none (vanilla)", "unknown"):
        for to_name, f_set in TURN_OFF_VS_FETISH_CONFLICTS.items():
            if any(f.lower() in fet_l for f in f_set):
                blocked_turn_offs.add(to_name)
    liked_ids = _act_tokens_to_ids(act_likes)
    if liked_ids:
        for to_name, a_set in TURN_OFF_VS_ACT_LIKE_CONFLICTS.items():
            if liked_ids & a_set:
                blocked_turn_offs.add(to_name)

    pool = [item for item in TURN_OFF_ITEMS if item not in blocked_turn_offs] or list(TURN_OFF_ITEMS)
    favored = []

    if any(kw in dyn_l for kw in ("receptive", "surrender", "yielding", "submissive")):
        favored += ["Clumsy / careless rough handling", "Crude degradation & insults", "Overly aggressive biting or pinching"]
    elif any(kw in dyn_l for kw in ("dominant", "proactive")):
        favored += ["Unearned bossiness & arrogance", "Limp passivity & lack of effort"]
    elif "service" in dyn_l:
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

    count = 1 + ((abs(int(hash_val or 0)) // 71) % 2)  # 1 to 2
    chosen = []
    for f in favored:
        if f in pool and len(chosen) < count:
            if ((abs(int(hash_val or 0)) // 79) % 100) < 70:
                chosen.append(f)
                pool.remove(f)

    while len(chosen) < count and pool:
        idx = (abs(int(hash_val or 0)) // (83 + len(chosen) * 13)) % len(pool)
        chosen.append(pool.pop(idx))

    return ", ".join(chosen)


def generate_dynamic_desires_and_turn_offs(
    hash_val: int,
    race: str = "",
    dynamic: str = "",
    openness: str = "moderate",
    traits: List[str] = None,
    fetish_override: Optional[str] = None,
    turn_offs_override: Optional[str] = None,
) -> tuple[str, str, str]:
    """Dynamically generates Sensitive Spots, Desires & Kinks, and Turn-Offs cleanly without duplicate fetish rolls."""
    phys_str, act_str = generate_dynamic_turn_ons_and_spots(hash_val, race=race, dynamic=dynamic)
    turn_offs_str = (
        turn_offs_override
        if turn_offs_override is not None
        else generate_dynamic_turn_offs(hash_val, dynamic=dynamic, openness=openness, traits=traits)
    )
    fetish_str = (
        fetish_override
        if fetish_override is not None
        else generate_dynamic_fetish(hash_val, race=race, dynamic=dynamic, openness=openness, turn_offs=turn_offs_str)
    )

    desires_items = [x.strip() for x in act_str.split(",") if x.strip()]
    if fetish_str and fetish_str.lower() not in ("none", "none (vanilla)", "unknown", ""):
        if not any(fetish_str.lower() in d.lower() for d in desires_items):
            desires_items.append(fetish_str)

    desires_str = ", ".join(desires_items)
    return phys_str, desires_str, turn_offs_str


def generate_dynamic_act_preferences(
    hash_val: int,
    dynamic: str = "",
    demeanor: str = "",
    openness: str = "",
    gender: str = "",
    is_virgin: Optional[bool] = None,
    turn_offs: str = "",
) -> Dict[str, str]:
    """Dynamically generates 1-2 Likes and 1-2 Dislikes enforcing biological gender, prude-virgin, Turn-Off, and mutual-exclusion guards."""
    dyn_l = str(dynamic or "").lower()
    open_l = str(openness or "").lower()
    o_tier = _openness_tier(openness)
    is_female = _is_female_gender(gender)

    likes_count = 1 + ((abs(int(hash_val or 0)) // 47) % 2)  # 1 to 2
    dislikes_count = 1 + ((abs(int(hash_val or 0)) // 53) % 2)  # 1 to 2

    all_ids = [item["id"] for item in ACT_PREFERENCE_REGISTRY]
    if is_female:
        all_ids = [aid for aid in all_ids if aid not in FEMALE_EXCLUDED_ACT_IDS]
    name_map = {item["id"]: item["name"] for item in ACT_PREFERENCE_REGISTRY}

    excluded_like_ids: set[str] = set()
    if is_virgin and o_tier == "prude":
        excluded_like_ids.update(PRUDE_VIRGIN_EXCLUDED_ACT_IDS)

    to_l = str(turn_offs or "").lower()
    if to_l:
        for to_name, conflict_ids in TURN_OFF_VS_ACT_LIKE_CONFLICTS.items():
            if _turn_off_matches_key(to_name, to_l):
                excluded_like_ids.update(conflict_ids)

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
    elif "service" in dyn_l:
        favored_likes += ["giving_oral", "slow_sensual", "swallowing"]

    if "prude" in open_l or "modest" in open_l:
        favored_likes += ["slow_sensual", "missionary", "spooning"]
        favored_dislikes += ["facial", "rough_handling", "fast_urgent"]
    elif "shameless" in open_l or "lewd" in open_l:
        favored_likes += ["swallowing", "facial", "cowgirl_riding", "from_behind"]

    # Select Likes
    chosen_likes_ids: List[str] = []
    pool_likes = [aid for aid in all_ids if aid not in excluded_like_ids]

    def _add_like(act_id: str) -> None:
        chosen_likes_ids.append(act_id)
        if act_id in pool_likes:
            pool_likes.remove(act_id)
        for a, b in MUTUALLY_EXCLUSIVE_ACT_LIKE_PAIRS:
            partner = b if act_id == a else (a if act_id == b else None)
            if partner and partner in pool_likes:
                pool_likes.remove(partner)

    for fl in favored_likes:
        if fl in pool_likes and len(chosen_likes_ids) < likes_count:
            if ((abs(int(hash_val or 0)) // 61) % 100) < 70:
                _add_like(fl)

    while len(chosen_likes_ids) < likes_count and pool_likes:
        idx = ((abs(int(hash_val or 0)) // (67 + len(chosen_likes_ids) * 17)) + len(chosen_likes_ids) * 7) % len(pool_likes)
        _add_like(pool_likes[idx])

    # Select Dislikes (Must be disjoint from Likes)
    pool_dislikes = [item_id for item_id in all_ids if item_id not in chosen_likes_ids]
    chosen_dislikes_ids: List[str] = []

    for fd in favored_dislikes:
        if fd in pool_dislikes and len(chosen_dislikes_ids) < dislikes_count:
            if ((abs(int(hash_val or 0)) // 71) % 100) < 70:
                chosen_dislikes_ids.append(fd)
                pool_dislikes.remove(fd)

    while len(chosen_dislikes_ids) < dislikes_count and pool_dislikes:
        idx = ((abs(int(hash_val or 0)) // (73 + len(chosen_dislikes_ids) * 19)) + len(chosen_dislikes_ids) * 5) % len(pool_dislikes)
        chosen_dislikes_ids.append(pool_dislikes.pop(idx))

    likes_str = ", ".join(name_map[i] for i in chosen_likes_ids)
    dislikes_str = ", ".join(name_map[i] for i in chosen_dislikes_ids)

    return {
        "likes": likes_str,
        "dislikes": dislikes_str,
        "act_likes": likes_str,
        "act_dislikes": dislikes_str,
    }


def generate_dynamic_intimate_experience(
    hash_val: int,
    openness: str = "moderate",
    gender: str = "",
    *,
    act_likes: Any = "",
    act_dislikes: Any = "",
    turn_offs: str = "",
    dynamic: str = "",
    intercourse_override: str = "",
) -> Dict[str, str]:
    """
    Computes decoupled 4-track experience (Intercourse, Oral, Manual, Anal),
    correlating track odds and give/receive directions with liked/disliked acts, turn-offs, and dynamic
    while preserving biological invariants and openness scaling.
    """
    o_low = str(openness or "moderate").lower()
    if "prude" in o_low or "modest" in o_low or "chaste" in o_low:
        exp_rate = 10  # 90% virgin
        anal_rate = 3
    elif "shameless" in o_low or "lewd" in o_low:
        exp_rate = 40  # 60% virgin
        anal_rate = 20
    elif "bold" in o_low or "uninhibited" in o_low:
        exp_rate = 30  # 70% virgin
        anal_rate = 12
    else:  # moderate
        exp_rate = 20  # 80% virgin
        anal_rate = 7

    # 1. Intercourse Track (preserves exact openness scaling roll)
    if intercourse_override in ("virgin", "non_virgin"):
        intercourse_val = intercourse_override
    else:
        roll_intercourse = hash_val % 100
        intercourse_val = "non_virgin" if roll_intercourse < exp_rate else "virgin"

    is_non_virgin = intercourse_val == "non_virgin"
    liked_ids = _act_tokens_to_ids(act_likes)
    disliked_ids = _act_tokens_to_ids(act_dislikes)
    to_l = str(turn_offs or "").lower()
    dyn_l = str(dynamic or "").lower()
    is_service = "service" in dyn_l
    is_female = _is_female_gender(gender)

    # 2. Oral Intimacy Track
    likes_oral_give = bool(liked_ids & {"giving_oral", "swallowing"})
    likes_oral_rec = bool(liked_ids & {"receiving_oral", "facial"})
    dislikes_oral = bool(disliked_ids & {"giving_oral", "receiving_oral"}) and not (likes_oral_give or likes_oral_rec)

    if is_non_virgin:
        oral_rate = max(exp_rate + 25, 45)
        if likes_oral_give or likes_oral_rec or is_service:
            oral_rate = 82
        elif dislikes_oral:
            oral_rate = max(5, exp_rate // 3)
    else:
        oral_rate = exp_rate
        if likes_oral_give or likes_oral_rec:
            oral_rate = min(55, exp_rate + 18)
        elif dislikes_oral:
            oral_rate = max(2, exp_rate // 3)

    roll_oral = (hash_val // 7) % 100
    if roll_oral < oral_rate:
        sub_oral = (hash_val // 11) % 100
        if (likes_oral_give or is_service) and not likes_oral_rec:
            oral_val = "has_done_and_received_oral" if sub_oral >= 70 else "has_done_oral"
        elif likes_oral_rec and not likes_oral_give:
            oral_val = "has_done_and_received_oral" if sub_oral >= 70 else "has_received_oral"
        elif sub_oral < 40:
            oral_val = "has_done_oral"
        elif sub_oral < 80:
            oral_val = "has_received_oral"
        else:
            oral_val = "has_done_and_received_oral"
    else:
        oral_val = "inexperienced"

    # 3. Manual Intimacy Track
    if is_non_virgin:
        manual_rate = max(exp_rate + 30, 52)
        if is_service or "prolonged_teasing" in liked_ids:
            manual_rate = 85
    else:
        manual_rate = exp_rate
        if "prolonged_teasing" in liked_ids:
            manual_rate = min(55, exp_rate + 15)

    roll_manual = (hash_val // 13) % 100
    if roll_manual < manual_rate:
        sub_man = (hash_val // 17) % 100
        if is_service:
            manual_val = "has_done_and_received_manual" if sub_man >= 65 else "has_done_manual"
        elif sub_man < 40:
            manual_val = "has_done_manual"
        elif sub_man < 80:
            manual_val = "has_received_manual"
        else:
            manual_val = "has_done_and_received_manual"
    else:
        manual_val = "inexperienced"

    # 4. Anal Intimacy Track
    anal_aversion = ("anal" in to_l) or ("backdoor" in to_l)
    likes_anal_give = ("giving_anal" in liked_ids) and not is_female
    likes_anal_rec = "receiving_anal" in liked_ids
    dislikes_anal = bool(disliked_ids & {"giving_anal", "receiving_anal"}) and not (likes_anal_give or likes_anal_rec)

    if anal_aversion or dislikes_anal:
        eff_anal_rate = 0
    elif likes_anal_give or likes_anal_rec:
        eff_anal_rate = 60 if is_non_virgin else (0 if _openness_tier(openness) == "prude" else max(anal_rate + 12, 18))
    elif is_non_virgin:
        eff_anal_rate = anal_rate + 8
    else:
        eff_anal_rate = anal_rate

    roll_anal = (hash_val // 19) % 100
    if roll_anal < eff_anal_rate:
        if is_female:
            anal_val = "has_received_anal"
        elif likes_anal_give and not likes_anal_rec:
            sub_anal = (hash_val // 23) % 100
            anal_val = "has_done_and_received_anal" if sub_anal >= 75 else "has_done_anal"
        elif likes_anal_rec and not likes_anal_give:
            sub_anal = (hash_val // 23) % 100
            anal_val = "has_done_and_received_anal" if sub_anal >= 75 else "has_received_anal"
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
        "anal": anal_val,
    }


def normalize_body_preferences(
    raw_likes: Any = None,
    raw_dislikes: Any = None,
) -> tuple[List[str], List[str]]:
    """Normalizes BB/Ass body preferences into canonical keys, enforcing at most 1 preference per axis across likes and dislikes."""
    valid_keys = set(BODY_PREFERENCE_KEYS)
    alias_map = {
        "smaller_bb": "smaller_bb",
        "small_bb": "smaller_bb",
        "likes_smaller_bb": "smaller_bb",
        "dislikes_smaller_bb": "smaller_bb",
        "bigger_bb": "bigger_bb",
        "big_bb": "bigger_bb",
        "large_bb": "bigger_bb",
        "likes_bigger_bb": "bigger_bb",
        "dislikes_bigger_bb": "bigger_bb",
        "smaller_ass": "smaller_ass",
        "small_ass": "smaller_ass",
        "smaller_rear": "smaller_ass",
        "likes_smaller_ass": "smaller_ass",
        "dislikes_smaller_ass": "smaller_ass",
        "bigger_ass": "bigger_ass",
        "big_ass": "bigger_ass",
        "large_ass": "bigger_ass",
        "bigger_rear": "bigger_ass",
        "likes_bigger_ass": "bigger_ass",
        "dislikes_bigger_ass": "bigger_ass",
        "taller_partner": "taller_partner",
        "taller": "taller_partner",
        "tall_partner": "taller_partner",
        "likes_taller": "taller_partner",
        "likes_taller_partner": "taller_partner",
        "dislikes_taller": "taller_partner",
        "dislikes_taller_partner": "taller_partner",
        "shorter_partner": "shorter_partner",
        "shorter": "shorter_partner",
        "short_partner": "shorter_partner",
        "likes_shorter": "shorter_partner",
        "likes_shorter_partner": "shorter_partner",
        "dislikes_shorter": "shorter_partner",
        "dislikes_shorter_partner": "shorter_partner",
    }

    def _coerce_items(raw: Any) -> List[str]:
        if raw is None:
            return []
        if isinstance(raw, str):
            parts = [p.strip().lower().replace(" ", "_") for p in raw.split(",") if p.strip()]
        elif isinstance(raw, (list, tuple, set)):
            parts = [str(p or "").strip().lower().replace(" ", "_") for p in raw if str(p or "").strip()]
        else:
            return []
        out: List[str] = []
        for p in parts:
            canon = alias_map.get(p, p)
            if canon in valid_keys and canon not in out:
                out.append(canon)
        return out

    seen_bb = False
    seen_ass = False
    seen_height = False
    clean_likes: List[str] = []
    clean_dislikes: List[str] = []

    for item in _coerce_items(raw_likes):
        if item.endswith("_bb"):
            if seen_bb:
                continue
            seen_bb = True
        elif item.endswith("_ass"):
            if seen_ass:
                continue
            seen_ass = True
        elif item in ("taller_partner", "shorter_partner"):
            if seen_height:
                continue
            seen_height = True
        clean_likes.append(item)

    for item in _coerce_items(raw_dislikes):
        if item.endswith("_bb"):
            if seen_bb:
                continue
            seen_bb = True
        elif item.endswith("_ass"):
            if seen_ass:
                continue
            seen_ass = True
        elif item in ("taller_partner", "shorter_partner"):
            if seen_height:
                continue
            seen_height = True
        clean_dislikes.append(item)

    return clean_likes, clean_dislikes


def generate_dynamic_height_preference(
    hash_val: int,
    gender: str = "",
    stature: str = "average",
    race: str = "",
) -> Dict[str, List[str]]:
    """Deterministically rolls a gender-skewed relative height preference (~50% neutral) with extreme-tier suppression.

    - Female: 32% likes taller_partner, 6% likes shorter_partner, 10% dislikes shorter_partner, 2% dislikes taller_partner.
    - Male:   32% likes shorter_partner, 6% likes taller_partner, 10% dislikes taller_partner, 2% dislikes shorter_partner.
    - Non-binary / Neutral: 19% likes taller_partner, 19% likes shorter_partner, 6% dislikes taller_partner, 6% dislikes shorter_partner.
    - Towering NPCs never roll taller_partner prefs; Miniature NPCs never roll shorter_partner prefs.
    - Feral kitsune:myobu_fox returns empty lists.
    """
    from .appearance import is_feral_rear_excluded, normalize_stature_tier

    if is_feral_rear_excluded(race):
        return {"body_likes": [], "body_dislikes": []}

    g_low = str(gender or "").strip().lower()
    is_male = is_male_gender(g_low)
    is_fem = is_female_gender(g_low)

    h_abs = abs(int(hash_val or 0))
    roll = (((h_abs * 3266489917 + 47) & 0xFFFFFFFF) >> 8) % 100
    likes: List[str] = []
    dislikes: List[str] = []

    if is_fem:
        if roll < 32:
            likes.append("taller_partner")
        elif roll < 38:
            likes.append("shorter_partner")
        elif roll < 48:
            dislikes.append("shorter_partner")
        elif roll < 50:
            dislikes.append("taller_partner")
    elif is_male:
        if roll < 32:
            likes.append("shorter_partner")
        elif roll < 38:
            likes.append("taller_partner")
        elif roll < 48:
            dislikes.append("taller_partner")
        elif roll < 50:
            dislikes.append("shorter_partner")
    else:
        if roll < 19:
            likes.append("taller_partner")
        elif roll < 38:
            likes.append("shorter_partner")
        elif roll < 44:
            dislikes.append("taller_partner")
        elif roll < 50:
            dislikes.append("shorter_partner")

    norm_stat = normalize_stature_tier(str(stature or "average"))
    if norm_stat == "towering":
        likes = [k for k in likes if k != "taller_partner"]
        dislikes = [k for k in dislikes if k != "taller_partner"]
    elif norm_stat == "miniature":
        likes = [k for k in likes if k != "shorter_partner"]
        dislikes = [k for k in dislikes if k != "shorter_partner"]

    return {"body_likes": likes, "body_dislikes": dislikes}


def generate_dynamic_body_preferences(
    hash_val: int,
    *,
    gender: str = "",
    stature: str = "average",
    race: str = "",
    include_height: bool = False,
) -> Dict[str, List[str]]:
    """Deterministically rolls BB & Ass size preferences per NPC (~60% neutral, ~28% like, ~12% dislike per axis), optionally including relative height."""
    h_abs = abs(int(hash_val or 0))
    likes: List[str] = []
    dislikes: List[str] = []

    bb_roll = (((h_abs * 2654435761 + 17) & 0xFFFFFFFF) >> 8) % 100
    if bb_roll < 14:
        likes.append("smaller_bb")
    elif bb_roll < 28:
        likes.append("bigger_bb")
    elif bb_roll < 34:
        dislikes.append("smaller_bb")
    elif bb_roll < 40:
        dislikes.append("bigger_bb")

    ass_roll = (((h_abs * 2246822519 + 31) & 0xFFFFFFFF) >> 8) % 100
    if ass_roll < 14:
        likes.append("smaller_ass")
    elif ass_roll < 28:
        likes.append("bigger_ass")
    elif ass_roll < 34:
        dislikes.append("smaller_ass")
    elif ass_roll < 40:
        dislikes.append("bigger_ass")

    if include_height:
        h_prefs = generate_dynamic_height_preference(hash_val, gender=gender, stature=stature, race=race)
        likes.extend(h_prefs["body_likes"])
        dislikes.extend(h_prefs["body_dislikes"])

    return {"body_likes": likes, "body_dislikes": dislikes}


def generate_dynamic_intimate_attributes(hash_val: int, race: str = "", gender: str = "", dynamic: str = "", openness: str = "moderate", traits: List[str] = None) -> Dict[str, Any]:
    """Dynamically generates coherent sensitive spots, desires & kinks, turn-offs, symmetrical act preferences, 4-track experience, body preferences, and undergarments."""
    o_low = str(openness or "moderate").lower()
    if "prude" in o_low or "modest" in o_low or "chaste" in o_low:
        exp_rate = 10
    elif "shameless" in o_low or "lewd" in o_low:
        exp_rate = 40
    elif "bold" in o_low or "uninhibited" in o_low:
        exp_rate = 30
    else:
        exp_rate = 20
    intercourse_val = "non_virgin" if (abs(int(hash_val or 0)) % 100) < exp_rate else "virgin"

    turn_offs_str = generate_dynamic_turn_offs(hash_val, dynamic=dynamic, openness=openness, traits=traits)
    fetish_str = generate_dynamic_fetish(hash_val, race=race, dynamic=dynamic, openness=openness, turn_offs=turn_offs_str)
    act_prefs = generate_dynamic_act_preferences(
        hash_val,
        dynamic=dynamic,
        openness=openness,
        gender=gender,
        is_virgin=(intercourse_val == "virgin"),
        turn_offs=turn_offs_str,
    )
    phys_str, desires_str, turn_offs_str = generate_dynamic_desires_and_turn_offs(
        hash_val,
        race=race,
        dynamic=dynamic,
        openness=openness,
        traits=traits,
        fetish_override=fetish_str,
        turn_offs_override=turn_offs_str,
    )
    experience = generate_dynamic_intimate_experience(
        hash_val,
        openness=openness,
        gender=gender,
        act_likes=act_prefs["likes"],
        act_dislikes=act_prefs["dislikes"],
        turn_offs=turn_offs_str,
        dynamic=dynamic,
        intercourse_override=intercourse_val,
    )
    undergarments = generate_procedural_undergarments(gender=gender, openness=openness, dynamic=dynamic, hash_val=hash_val)
    body_prefs = generate_dynamic_body_preferences(hash_val)

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
        "undergarments": undergarments,
        "body_likes": body_prefs["body_likes"],
        "body_dislikes": body_prefs["body_dislikes"],
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
    """Dynamically generates a past partner name from namegen according to scenario, gender, and cultural rules."""
    try:
        import namegen
        return namegen.generate_person_name(scenario=scenario, gender=partner_gender, seed=hash_val if hash_val else None)
    except Exception:
        is_female = ("female" in partner_gender.lower() or "woman" in partner_gender.lower() or "girl" in partner_gender.lower())
        return "Elena Vance" if is_female else "Julian Vance" 

def compute_past_history_seed(name: str, race: str = "", session_seed: str = "") -> str:
    """Computes canonical deterministic seed string for past intimate history & ex-partner generation."""
    name_str = str(name or "npc").strip() or "npc"
    race_str = str(race or "human").strip() or "human"
    sess_str = str(session_seed if session_seed not in (None, "") else 0)
    return f"{name_str}_{race_str}_{sess_str}"


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
    has_existing_partner: bool = False,
    act_likes: Any = "",
    preferred_ex_partners: Optional[List[Dict[str, Any]]] = None,
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
    is_char_male = is_male_gender(raw_g)
    is_char_female = is_female_gender(raw_g)

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

        if preferred_ex_partners and p_idx < len(preferred_ex_partners) and isinstance(preferred_ex_partners[p_idx], dict):
            pref_p = preferred_ex_partners[p_idx]
            partner_name = str(pref_p.get("name") or "").strip() or generate_past_partner_name(scenario=scenario, partner_gender=partner_gender, hash_val=p_hash)
            role = str(pref_p.get("role") or "").strip() or generate_past_partner_role(scenario=scenario, hash_val=p_hash)
        else:
            partner_name = generate_past_partner_name(scenario=scenario, partner_gender=partner_gender, hash_val=p_hash)
            role = generate_past_partner_role(scenario=scenario, hash_val=p_hash)

        enc_range = max(1, base_enc_max - base_enc_min + 1)
        count = base_enc_min + (p_hash % enc_range)
        count_str = "1 time" if count == 1 else f"{count} times"

        is_this_affair = has_affair and p_idx >= 1
        role_label = f"{role}, Secret Affair" if is_this_affair else role

        liked_ids_ph = _act_tokens_to_ids(act_likes)
        has_intercourse = (i_state == "non_virgin") and (
            p_idx == 0 or (is_shameless and (p_hash % 2 == 0)) or (o_state == "inexperienced" and m_state == "inexperienced" and a_state == "inexperienced") or (p_hash % 2 == 0)
        )
        oral_favored_ph = bool(liked_ids_ph & {"giving_oral", "receiving_oral", "swallowing", "facial"})
        anal_favored_ph = bool(liked_ids_ph & {"giving_anal", "receiving_anal"})
        has_oral = (o_state != "inexperienced") and (
            p_idx == 0 or partner_count <= 2 or oral_favored_ph or ((p_hash // 3) % 100) < 75
        )
        has_manual = (m_state != "inexperienced") and (
            p_idx == 0 or partner_count <= 2 or ((p_hash // 5) % 100) < 75
        )
        has_anal = (a_state != "inexperienced") and (
            p_idx == 0 or partner_count <= 2 or anal_favored_ph or ((p_hash // 7) % 100) < 60
        )

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

