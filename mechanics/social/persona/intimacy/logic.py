from __future__ import annotations
from .constants import *
import hashlib
import re
from typing import Dict, Any, List, Optional
from ..core import *

def transition_intercourse_experience(current_state: str, action_type: str) -> str:
    """Transitions intercourse virginity track."""
    if action_type == "intercourse":
        return "non_virgin"
    return "non_virgin" if current_state == "non_virgin" else "virgin"

def transition_oral_experience(current_state: str, action_type: str) -> str:
    """Transitions oral intimacy track."""
    c = str(current_state or "inexperienced").strip().lower()
    act = str(action_type or "").strip().lower()
    if c == "has_done_and_received_oral" or act in ("has_done_and_received_oral", "oral_both"):
        return "has_done_and_received_oral"
    if (c == "has_done_oral" and act in ("oral_receive", "has_received_oral")) or (c == "has_received_oral" and act in ("oral_give", "has_done_oral")):
        return "has_done_and_received_oral"
    if act in ("oral_give", "has_done_oral"):
        return "has_done_and_received_oral" if c == "has_received_oral" else "has_done_oral"
    if act in ("oral_receive", "has_received_oral"):
        return "has_done_and_received_oral" if c == "has_done_oral" else "has_received_oral"
    return c if c in ("has_done_oral", "has_received_oral", "has_done_and_received_oral") else "inexperienced"

def transition_manual_experience(current_state: str, action_type: str) -> str:
    """Transitions manual intimacy track."""
    c = str(current_state or "inexperienced").strip().lower()
    act = str(action_type or "").strip().lower()
    if c == "has_done_and_received_manual" or act in ("has_done_and_received_manual", "manual_both"):
        return "has_done_and_received_manual"
    if (c == "has_done_manual" and act in ("manual_receive", "has_received_manual")) or (c == "has_received_manual" and act in ("manual_give", "has_done_manual")):
        return "has_done_and_received_manual"
    if act in ("manual_give", "has_done_manual"):
        return "has_done_and_received_manual" if c == "has_received_manual" else "has_done_manual"
    if act in ("manual_receive", "has_received_manual"):
        return "has_done_and_received_manual" if c == "has_done_manual" else "has_received_manual"
    return c if c in ("has_done_manual", "has_received_manual", "has_done_and_received_manual") else "inexperienced"

def transition_anal_experience(current_state: str, action_type: str, gender: str = "") -> str:
    """Transitions anal intimacy track while enforcing biological gender invariants."""
    c = str(current_state or "inexperienced").strip().lower()
    act = str(action_type or "").strip().lower()
    raw_g = str(gender or "").lower()
    is_female = is_female_gender(raw_g)
    if is_female:
        if act in ("anal_give", "has_done_anal"):
            return c if c in ("has_received_anal", "inexperienced") else "has_received_anal"
        if act in ("anal_receive", "has_received_anal", "anal", "has_done_and_received_anal", "anal_both"):
            return "has_received_anal"
        return c if c == "has_received_anal" else "inexperienced"
    if c == "has_done_and_received_anal" or act in ("has_done_and_received_anal", "anal_both"):
        return "has_done_and_received_anal"
    if (c == "has_done_anal" and act in ("anal_receive", "has_received_anal")) or (c == "has_received_anal" and act in ("anal_give", "has_done_anal")):
        return "has_done_and_received_anal"
    if act in ("anal_give", "has_done_anal"):
        return "has_done_and_received_anal" if c == "has_received_anal" else "has_done_anal"
    if act in ("anal_receive", "has_received_anal"):
        return "has_done_and_received_anal" if c == "has_done_anal" else "has_received_anal"
    if act == "anal":
        return "has_done_and_received_anal" if c in ("has_done_anal", "has_received_anal") else "has_received_anal"
    return c if c in ("has_done_anal", "has_received_anal", "has_done_and_received_anal") else "inexperienced"

def sanitize_sensitive_spots_for_species(sens_str: str, race: str = "", distinctive_features: str = "") -> str:
    """Validates and filters sensitive spot items to ensure they strictly conform to the character's biological anatomy."""
    if not sens_str:
        return ""
    
    race_l = str(race or "").lower().strip()
    feat_l = str(distinctive_features or "").lower().strip()
    combined_bio = f"{race_l} {feat_l}"
    
    is_horned = any(kw in combined_bio for kw in ("horn", "antler", "deer", "goat", "ram", "bull", "minotaur", "demon", "devil", "tiefling", "oni", "dragon", "drake", "qilin", "sheep", "satyr", "faun"))
    is_winged = any(kw in combined_bio for kw in ("wing", "avian", "bird", "harpy", "angel", "bat", "dragon", "pegasus", "gryphon", "griffin", "succubus", "seraph", "feather"))
    is_scaly_aquatic = any(kw in combined_bio for kw in ("scale", "scaly", "naga", "snake", "reptile", "dragon", "lizard", "mermaid", "siren", "aquatic", "fish", "fin", "gill"))
    is_beastfolk = any(kw in combined_bio for kw in ("fox", "beast", "wolf", "cat", "neko", "kitsune", "anthro", "rabbit", "bunny", "canine", "feline", "tanuki", "raccoon", "bear", "lion", "tiger", "cheetah", "fennec", "mouse", "rat", "rodent", "ferret", "badger", "weasel", "hybrid", "half_beast", "halfbeast", "demi_human", "beastkin"))

    items = [x.strip() for x in sens_str.split(",") if x.strip()]
    valid_items = []
    
    for item in items:
        item_l = item.lower()
        # 1. Horn/antler check: only permitted if character is biologically a horned/antlered species
        if ("horn" in item_l or "antler" in item_l) and not is_horned:
            continue
        # 2. Wing/feather check: only permitted if character is biologically a winged/feathered species
        if ("wing" in item_l or "flight joint" in item_l or "feather" in item_l) and not is_winged:
            continue
        # 3. Fin/gill/scale check: only permitted if character is aquatic/scaly
        if any(kw in item_l for kw in ("fin", "gill", "scale")) and not is_scaly_aquatic:
            continue
        # 4. Beastfolk earlobe check: Beastfolk have animal ears at the crown of their head, not human earlobes
        if is_beastfolk and "earlobe" in item_l:
            if "jawline" in item_l:
                item = "Tufted ear base & jawline fur"
            else:
                item = "Tufted ear base"
            
        valid_items.append(item)
        
    return ", ".join(valid_items)

PHYSICAL_ANATOMY_KEYWORDS = (
    "ear", "tail", "neck", "nape", "thigh", "waist", "collarbone", "spine", "back", "chest", "sternum",
    "breast", "horn", "antler", "wing", "feather", "scale", "rib", "foot", "feet", "palm", "wrist",
    "jawline", "throat", "belly", "stomach", "hip", "underbust", "flank", "arm", "knee", "navel",
    "shoulder", "crest", "fur", "paw", "joint", "root", "crown", "dorsal", "gill", "skin", "lip",
    "flesh", "body", "zone", "spot", "loins", "groin", "butt", "cheek", "erogenous"
)

ACTION_TRIGGER_KEYWORDS = (
    "whisper", "undress", "embrace", "kiss", "hold", "eye contact", "praise", "teas", "nibbl",
    "pin", "bite", "biting", "moan", "breath", "worship", "urgency", "restraint", "talking", "talk",
    "touch", "stroke", "pulling", "massage", "looking", "watching", "spank", "edging", "aftercare",
    "command", "submiss", "dominant", "lead", "yield", "beg", "roleplay", "flirt", "hand-holding"
)

def partition_sensitivities_and_turn_ons(sens_str: str, turn_str: str, race: str = "") -> tuple[str, str]:
    """
    Partitions raw sensitive spots and turn-ons into:
    1. Sensitive Spots: purely physical anatomical erogenous zones.
    2. Turn-Ons: erotic action triggers, behavioral cues, and psychological stimuli.

    Eliminates cross-duplication and removes action triggers from sensitive spots.
    """
    sens_raw = str(sens_str or "").strip()
    turn_raw = str(turn_str or "").strip()

    all_raw_items = []
    if sens_raw and sens_raw.lower() not in ("none", "none (vanilla)", "unknown", ""):
        all_raw_items.extend([x.strip() for x in sens_raw.split(",") if x.strip()])
    if turn_raw and turn_raw.lower() not in ("none", "none (vanilla)", "unknown", ""):
        all_raw_items.extend([x.strip() for x in turn_raw.split(",") if x.strip()])

    if not all_raw_items:
        return "", ""

    phys_items = []
    act_items = []
    seen = set()

    for item in all_raw_items:
        clean_item = item.strip()
        item_lower = clean_item.lower()
        if not clean_item or item_lower in ("none", "none (vanilla)", "unknown") or clean_item in seen:
            continue
        seen.add(clean_item)

        has_phys_tag = bool(re.search(r'\(\s*physical\s*\)', clean_item, flags=re.I))
        has_act_tag = bool(re.search(r'\(\s*action\s*\)', clean_item, flags=re.I))

        if has_phys_tag and not has_act_tag:
            phys_items.append(clean_item)
            continue
        elif has_act_tag and not has_phys_tag:
            act_items.append(clean_item)
            continue

        is_phys = any(k in item_lower for k in PHYSICAL_ANATOMY_KEYWORDS)
        is_act = any(k in item_lower for k in ACTION_TRIGGER_KEYWORDS)

        if is_phys and not is_act:
            clean_tagged = clean_item if "(physical)" in item_lower else f"{clean_item} (Physical)"
            phys_items.append(clean_tagged)
        elif is_act:
            clean_tagged = clean_item if "(action)" in item_lower else f"{clean_item} (Action)"
            act_items.append(clean_tagged)
        elif is_phys:
            clean_tagged = clean_item if "(physical)" in item_lower else f"{clean_item} (Physical)"
            phys_items.append(clean_tagged)
        else:
            if clean_item in sens_raw and clean_item not in turn_raw:
                phys_items.append(f"{clean_item} (Physical)")
            else:
                act_items.append(f"{clean_item} (Action)")

    return ", ".join(phys_items), ", ".join(act_items)

def enforce_intimacy_safeguard_invariants(app_dict: Dict[str, Any], gender: str = "") -> Dict[str, Any]:
    """
    Enforces the single-source-of-truth invariant across intimacy state fields:
    1. An NPC whose canon predetermined state is 'virgin' CANNOT have active experience (intercourse, oral, manual)
       unless verified by actual recorded player milestone memories or the 'had_first_time_with_player' flag.
    2. Composite 'virginity' is strictly synchronized as a derived reflection of active experience tracks.
    3. Biological invariant: Female characters can ONLY receive anal intimacy. They can NEVER have 'has_done_anal'
       or 'has_done_and_received_anal'. Any active anal experience for females is normalized to 'has_received_anal'.
    """
    if not isinstance(app_dict, dict):
        return app_dict

    raw_g = str(gender or app_dict.get("gender") or app_dict.get("sex") or "").strip().lower()
    if not raw_g:
        if app_dict.get("breast_size") and not app_dict.get("penis_size"):
            raw_g = "female"
        elif app_dict.get("penis_size") and not app_dict.get("breast_size"):
            raw_g = "male"
    is_female = is_female_gender(raw_g)

    mems = app_dict.get("intimate_memories") or []

    def _is_intercourse_mem(m_str: str) -> bool:
        low = m_str.lower()
        if not any(k in low for k in INTERCOURSE_MEMORY_KEYWORDS):
            return False
        if any(ak in low for ak in ("anal", "ass", "pegged", "pegging", "backdoor")):
            other_sex_kws = [k for k in INTERCOURSE_MEMORY_KEYWORDS if k != "penetrat"]
            return any(k in low for k in other_sex_kws)
        return True

    has_sex_mem = any(_is_intercourse_mem(str(m)) for m in mems)
    has_oral_give = any(any(k in str(m).lower() for k in ORAL_GIVE_MEMORY_KEYWORDS) for m in mems)
    has_oral_rec = any(any(k in str(m).lower() for k in ORAL_RECEIVE_MEMORY_KEYWORDS) for m in mems)
    has_manual_give = any(any(k in str(m).lower() for k in MANUAL_GIVE_MEMORY_KEYWORDS) for m in mems)
    has_manual_rec = any(any(k in str(m).lower() for k in MANUAL_RECEIVE_MEMORY_KEYWORDS) for m in mems)
    has_anal_give = False if is_female else any(any(k in str(m).lower() for k in ANAL_GIVE_MEMORY_KEYWORDS) for m in mems)
    has_anal_rec = any(any(k in str(m).lower() for k in ANAL_RECEIVE_MEMORY_KEYWORDS) for m in mems)
    had_first_time = bool(app_dict.get("had_first_time_with_player"))

    pred_i = str(app_dict.get("predetermined_intercourse") or app_dict.get("intercourse_experience") or "").strip().lower()
    if pred_i in ("virgin", "non_virgin"):
        app_dict["predetermined_intercourse"] = pred_i

    # INVARIANT 1: Ground intercourse, oral, manual, and anal experience in milestone memories for predetermined virgins
    cur_i = str(app_dict.get("intercourse_experience") or "virgin").strip().lower()
    cur_o = str(app_dict.get("oral_experience") or "inexperienced").strip().lower()
    cur_m = str(app_dict.get("manual_experience") or "inexperienced").strip().lower()
    cur_a = str(app_dict.get("anal_experience") or "inexperienced").strip().lower()

    if is_female and cur_a in ("has_done_anal", "has_done_and_received_anal"):
        cur_a = "has_received_anal"

    if pred_i == "virgin":
        if has_sex_mem:
            app_dict["intercourse_experience"] = "non_virgin"
            app_dict["had_first_time_with_player"] = True
        elif had_first_time and cur_i == "non_virgin":
            app_dict["intercourse_experience"] = "non_virgin"
        elif mems:
            # Recorded intimate milestones exist; intercourse is only non_virgin if verified by intercourse memory or had_first_time
            app_dict["intercourse_experience"] = "virgin"
        else:
            app_dict["intercourse_experience"] = "virgin"

        if mems:
            if has_oral_give and has_oral_rec:
                app_dict["oral_experience"] = "has_done_and_received_oral"
            elif has_oral_give:
                app_dict["oral_experience"] = merge_oral_states(cur_o, "has_done_oral")
            elif has_oral_rec:
                app_dict["oral_experience"] = merge_oral_states(cur_o, "has_received_oral")
            elif cur_o in ORAL_INTIMACY_STATES and cur_o != "inexperienced":
                app_dict["oral_experience"] = cur_o
            else:
                app_dict["oral_experience"] = "inexperienced"

            if has_manual_give and has_manual_rec:
                app_dict["manual_experience"] = "has_done_and_received_manual"
            elif has_manual_give:
                app_dict["manual_experience"] = merge_manual_states(cur_m, "has_done_manual")
            elif has_manual_rec:
                app_dict["manual_experience"] = merge_manual_states(cur_m, "has_received_manual")
            elif cur_m in MANUAL_INTIMACY_STATES and cur_m != "inexperienced":
                app_dict["manual_experience"] = cur_m
            else:
                app_dict["manual_experience"] = "inexperienced"

            if has_anal_give and has_anal_rec:
                app_dict["anal_experience"] = "has_done_and_received_anal"
            elif has_anal_give:
                app_dict["anal_experience"] = merge_anal_states(cur_a, "has_done_anal")
            elif has_anal_rec:
                app_dict["anal_experience"] = merge_anal_states(cur_a, "has_received_anal")
            elif cur_a in ANAL_INTIMACY_STATES and cur_a != "inexperienced":
                app_dict["anal_experience"] = cur_a
            else:
                app_dict["anal_experience"] = "inexperienced"
        else:
            if cur_o in ORAL_INTIMACY_STATES and cur_o != "inexperienced":
                app_dict["oral_experience"] = cur_o
            if cur_m in MANUAL_INTIMACY_STATES and cur_m != "inexperienced":
                app_dict["manual_experience"] = cur_m
            if cur_a in ANAL_INTIMACY_STATES and cur_a != "inexperienced":
                app_dict["anal_experience"] = cur_a
            else:
                app_dict["anal_experience"] = cur_a if cur_a in ANAL_INTIMACY_STATES else "inexperienced"
    elif pred_i == "non_virgin":
        app_dict["intercourse_experience"] = "non_virgin"
        if has_oral_give and has_oral_rec:
            app_dict["oral_experience"] = "has_done_and_received_oral"
        elif has_oral_give:
            app_dict["oral_experience"] = merge_oral_states(cur_o, "has_done_oral")
        elif has_oral_rec:
            app_dict["oral_experience"] = merge_oral_states(cur_o, "has_received_oral")

        if has_manual_give and has_manual_rec:
            app_dict["manual_experience"] = "has_done_and_received_manual"
        elif has_manual_give:
            app_dict["manual_experience"] = merge_manual_states(cur_m, "has_done_manual")
        elif has_manual_rec:
            app_dict["manual_experience"] = merge_manual_states(cur_m, "has_received_manual")

        if has_anal_give and has_anal_rec:
            app_dict["anal_experience"] = "has_done_and_received_anal"
        elif has_anal_give:
            app_dict["anal_experience"] = merge_anal_states(cur_a, "has_done_anal")
        elif has_anal_rec:
            app_dict["anal_experience"] = merge_anal_states(cur_a, "has_received_anal")
        elif cur_a in ANAL_INTIMACY_STATES:
            app_dict["anal_experience"] = cur_a
        else:
            app_dict["anal_experience"] = "inexperienced"
    else:
        # Corrupted or missing predetermined_intercourse — infer from stored experience and memories
        # Clamp to valid state sets; never allow invalid strings to persist
        if cur_i not in ("virgin", "non_virgin"):
            cur_i = "non_virgin" if (has_sex_mem or cur_i == "non_virgin") else "virgin"
        app_dict["predetermined_intercourse"] = cur_i
        app_dict["intercourse_experience"] = "non_virgin" if (has_sex_mem or cur_i == "non_virgin") else "virgin"
        app_dict["oral_experience"] = cur_o if cur_o in ORAL_INTIMACY_STATES else "inexperienced"
        app_dict["manual_experience"] = cur_m if cur_m in MANUAL_INTIMACY_STATES else "inexperienced"
        app_dict["anal_experience"] = cur_a if cur_a in ANAL_INTIMACY_STATES else "inexperienced"
        # Apply memory ratchet
        if has_oral_give:
            app_dict["oral_experience"] = merge_oral_states(app_dict.get("oral_experience", "inexperienced"), "has_done_oral")
        if has_oral_rec:
            app_dict["oral_experience"] = merge_oral_states(app_dict.get("oral_experience", "inexperienced"), "has_received_oral")
        if has_manual_give:
            app_dict["manual_experience"] = merge_manual_states(app_dict.get("manual_experience", "inexperienced"), "has_done_manual")
        if has_manual_rec:
            app_dict["manual_experience"] = merge_manual_states(app_dict.get("manual_experience", "inexperienced"), "has_received_manual")
        if has_anal_give:
            app_dict["anal_experience"] = merge_anal_states(app_dict.get("anal_experience", "inexperienced"), "has_done_anal")
        if has_anal_rec:
            app_dict["anal_experience"] = merge_anal_states(app_dict.get("anal_experience", "inexperienced"), "has_received_anal")

    if is_female:
        cur_a_res = str(app_dict.get("anal_experience") or "").strip().lower()
        if cur_a_res in ("has_done_anal", "has_done_and_received_anal"):
            app_dict["anal_experience"] = "has_received_anal"

    return app_dict

def merge_intercourse_states(existing_virg: str, incoming_virg: str) -> str:
    """Combines intercourse virginity states following a strictly progressive one-way ratchet."""
    e = str(existing_virg or "").strip().lower()
    i = str(incoming_virg or "").strip().lower()
    if e == "non_virgin" or i == "non_virgin":
        return "non_virgin"
    if i == "virgin":
        return e if e in INTERCOURSE_STATES else "virgin"
    if e == "virgin":
        return i if i in INTERCOURSE_STATES else "virgin"
    return i if i in INTERCOURSE_STATES else (e if e in INTERCOURSE_STATES else "virgin")

def merge_oral_states(existing_oral: str, incoming_oral: str) -> str:
    """Combines oral experience states following a strictly progressive one-way ratchet."""
    e = str(existing_oral or "").strip().lower()
    i = str(incoming_oral or "").strip().lower()
    if e == "has_done_and_received_oral" or i == "has_done_and_received_oral":
        return "has_done_and_received_oral"
    if (e == "has_done_oral" and i == "has_received_oral") or (e == "has_received_oral" and i == "has_done_oral"):
        return "has_done_and_received_oral"
    if e in ("has_done_oral", "has_received_oral"):
        if i in ("inexperienced", "unknown", "", "none"):
            return e
        return i
    if i in ("has_done_oral", "has_received_oral"):
        return i
    return e if e in ORAL_INTIMACY_STATES else "inexperienced"

def merge_manual_states(existing_manual: str, incoming_manual: str) -> str:
    """Combines manual intimacy experience states following a strictly progressive one-way ratchet."""
    e = str(existing_manual or "").strip().lower()
    i = str(incoming_manual or "").strip().lower()
    if e == "has_done_and_received_manual" or i == "has_done_and_received_manual":
        return "has_done_and_received_manual"
    if (e == "has_done_manual" and i == "has_received_manual") or (e == "has_received_manual" and i == "has_done_manual"):
        return "has_done_and_received_manual"
    if e in ("has_done_manual", "has_received_manual"):
        if i in ("inexperienced", "unknown", "", "none"):
            return e
        return i
    if i in ("has_done_manual", "has_received_manual"):
        return i
    return e if e in MANUAL_INTIMACY_STATES else "inexperienced"

def merge_anal_states(existing_anal: str, incoming_anal: str, gender: str = "") -> str:
    """Combines anal intimacy experience states following a strictly progressive one-way ratchet."""
    e = str(existing_anal or "").strip().lower()
    i = str(incoming_anal or "").strip().lower()
    raw_g = str(gender or "").lower()
    is_female = is_female_gender(raw_g)
    if is_female:
        if e in ("has_done_anal", "has_done_and_received_anal"):
            e = "has_received_anal"
        if i in ("has_done_anal", "has_done_and_received_anal"):
            i = "has_received_anal"
        if e == "has_received_anal" or i == "has_received_anal":
            return "has_received_anal"
        return "inexperienced"
    if e == "has_done_and_received_anal" or i == "has_done_and_received_anal":
        return "has_done_and_received_anal"
    if (e == "has_done_anal" and i == "has_received_anal") or (e == "has_received_anal" and i == "has_done_anal"):
        return "has_done_and_received_anal"
    if e in ("has_done_anal", "has_received_anal"):
        if i in ("inexperienced", "unknown", "", "none"):
            return e
        return i
    if i in ("has_done_anal", "has_received_anal"):
        return i
    return e if e in ANAL_INTIMACY_STATES else "inexperienced"

def infer_intimate_demeanor_from_traits(desc: Any = "", race: str = "human", gender: str = "female", traits: List[str] = None, role: str = "") -> str:
    """Infers an authentic intimate demeanor (voice, emotional tone, communication style) correlated to character traits, role, and description.
    Uses a weighted probability distribution: characters fitting an archetype have a 25% chance of receiving their stereotypical demeanor,
    while the remaining 75% is evenly distributed across the other 5 demeanors (15% each) for organic character diversity.
    """
    if isinstance(desc, dict):
        desc = " ".join(str(v) for v in desc.values() if v)
    combined = (str(desc or "") + " " + str(role or "") + " " + " ".join(str(t) for t in (traits or []))).lower()
    raw_g = str(gender or "female").strip().lower()
    is_male = is_male_gender(raw_g)
    templates = INTIMATE_DEMEANOR_MALE_TEMPLATES if is_male else INTIMATE_DEMEANOR_FEMALE_TEMPLATES

    seed_str = (str(desc or "") + "_" + str(race or "") + "_" + str(gender or "") + "_" + " ".join(str(t) for t in (traits or [])) + "_" + str(role or "")).encode("utf-8")
    hash_val = int(hashlib.md5(seed_str).hexdigest(), 16) if seed_str else 0
    roll = hash_val % 100

    preferred_idx = None
    # 1. Athletic, competitive, direct personalities -> Blunt & Teasing (index 4)
    if any(kw in combined for kw in ("athlete", "athletic", "track", "captain", "competitive", "warrior", "leader", "bold", "confident", "fighter", "swimmer", "runner", "martial")):
        preferred_idx = 4
    # 2. Rogues, mischievous characters, kitsune, sly rivals -> Playful & Bantering (index 0)
    elif any(kw in combined for kw in ("teas", "rogue", "mischiev", "kitsune", "sly", "brat", "prank", "flirt", "playful", "cunning")):
        preferred_idx = 0
    # 3. Passionate & Intense / Vocal (Passionate, artistic, uninhibited, fierce, dancer) -> Passionate & Vocal (index 3)
    elif any(kw in combined for kw in ("passion", "intense", "fiery", "artistic", "uninhibited", "wild", "dancer", "expressive")):
        preferred_idx = 3
    # 4. Poised & Sensually Confident (Scholars, nobles, mages, disciplined councilors) -> Poised & Articulate (index 2)
    elif any(kw in combined for kw in ("scholar", "mage", "noble", "disciplined", "composed", "president", "council", "intellectual", "calculating", "perfectionist", "mature", "dignified")):
        preferred_idx = 2
    # 5. Gentle & Loving / Protective (Healers, kind, sweet, warm, nurturing) -> Soft & Deeply Affectionate (index 1)
    elif any(kw in combined for kw in ("gentle", "nurtur", "healer", "kind", "caring", "soft", "sweet", "protective", "warm")):
        preferred_idx = 1
    # 6. Flustered / Shy (Strictly reserved for characters with shy/timid/anxious traits) -> Hesitant & Flustered (index 5)
    elif any(kw in combined for kw in ("shy", "timid", "anxious", "nervous", "inexperienced", "bookworm", "flustered", "introvert", "sheltered")):
        preferred_idx = 5

    if preferred_idx is not None:
        # Archetypal stereotypical demeanor has a 25% probability weight
        if roll < 25:
            return templates[preferred_idx]
        # Remaining 75% is evenly distributed across the other 5 templates (15% each)
        other_indices = [i for i in range(len(templates)) if i != preferred_idx]
        rem_idx = (roll - 25) % len(other_indices)
        return templates[other_indices[rem_idx]]

    # Hash-based procedural fallback evenly across templates when no archetype keywords match
    return templates[hash_val % len(templates)]

def infer_intimate_dynamic_from_traits(desc: Any = "", race: str = "human", gender: str = "female", traits: List[str] = None, role: str = "") -> str:
    """
    Infers an intimate dynamic (proactivity, power balance, drive) for a character.
    Balances daytime trait context with diverse contrast ('gap moe' opportunities capped at 25%).
    """
    seed_str = (str(desc or "") + "_" + str(race or "") + "_" + str(gender or "") + "_" + " ".join(str(t) for t in (traits or [])) + "_" + str(role or "")).encode("utf-8")
    hash_val = int(hashlib.md5(seed_str).hexdigest(), 16) if seed_str else 0
    roll = hash_val % 100
    combined = (str(desc or "") + " " + str(role or "") + " " + " ".join(str(t) for t in (traits or []))).lower()

    # 1. Leaders / Competitive / Athletic (45% Dominant, 25% Receptive gap moe, 20% Switch, 10% High-Drive)
    if any(kw in combined for kw in ("athlete", "athletic", "track", "captain", "competitive", "leader", "warrior", "fighter", "runner")):
        if roll < 25:
            return INTIMATE_DYNAMIC_TEMPLATES[2]  # Eagerly Receptive / Surrenders Control (25% Gap Moe)
        elif roll < 70:
            return INTIMATE_DYNAMIC_TEMPLATES[0]  # Boldly Proactive & Dominant (45%)
        elif roll < 90:
            return INTIMATE_DYNAMIC_TEMPLATES[1]  # Playful Switch / Teasing Brat (20%)
        else:
            return INTIMATE_DYNAMIC_TEMPLATES[3]  # Insatiable / Hidden High-Drive (10%)

    # 2. Healers / Nurturing / Shrine Maidens / Demure (40% Gentle Yielding, 25% Service, 25% High-Drive gap moe, 10% Switch)
    if any(kw in combined for kw in ("healer", "nurtur", "kind", "shrine", "priest", "pure", "innocent", "sweet", "caring")):
        if roll < 25:
            return INTIMATE_DYNAMIC_TEMPLATES[3]  # Insatiable / Hidden High-Drive (25% Gap Moe)
        elif roll < 65:
            return INTIMATE_DYNAMIC_TEMPLATES[4]  # Gentle & Yielding (40%)
        elif roll < 90:
            return INTIMATE_DYNAMIC_TEMPLATES[5]  # Attentive Service-Oriented (25%)
        else:
            return INTIMATE_DYNAMIC_TEMPLATES[1]  # Playful Switch / Teasing Brat (10%)

    # 3. Scholars / Disciplined / Council Presidents (45% Dominant, 25% Receptive gap moe, 20% Switch, 10% Service)
    if any(kw in combined for kw in ("scholar", "mage", "council", "president", "disciplined", "intellectual", "composed", "strict")):
        if roll < 25:
            return INTIMATE_DYNAMIC_TEMPLATES[2]  # Eagerly Receptive / Surrenders Control (25% Gap Moe)
        elif roll < 70:
            return INTIMATE_DYNAMIC_TEMPLATES[0]  # Boldly Proactive & Dominant (45%)
        elif roll < 90:
            return INTIMATE_DYNAMIC_TEMPLATES[1]  # Playful Switch (20%)
        else:
            return INTIMATE_DYNAMIC_TEMPLATES[5]  # Attentive Service-Oriented (10%)

    # 4. Rogues / Sly / Kitsune / Mischievous (50% Playful Switch, 25% Dominant, 25% Receptive)
    if any(kw in combined for kw in ("rogue", "kitsune", "mischiev", "sly", "brat", "flirt", "prank")):
        if roll < 50:
            return INTIMATE_DYNAMIC_TEMPLATES[1]  # Playful Switch / Teasing Brat (50%)
        elif roll < 75:
            return INTIMATE_DYNAMIC_TEMPLATES[0]  # Boldly Proactive & Dominant (25%)
        else:
            return INTIMATE_DYNAMIC_TEMPLATES[2]  # Eagerly Receptive / Surrenders Control (25%)

    # 5. General distribution fallback
    return INTIMATE_DYNAMIC_TEMPLATES[hash_val % len(INTIMATE_DYNAMIC_TEMPLATES)]

def infer_erotic_openness_from_traits(desc: Any = "", race: str = "human", gender: str = "female", traits: List[str] = None, role: str = "") -> str:
    """
    Infers an Erotic Openness tier for a character (modesty, boundary, media eagerness).
    Tiers:
    - 'prude': Prude / Modest (~25% baseline)
    - 'moderate': Reserved / Moderate (~45% baseline)
    - 'bold': Bold / Uninhibited (~20% baseline)
    - 'shameless': Shameless / Lewd (~10% baseline)
    """
    seed_str = (str(desc or "") + "_" + str(race or "") + "_" + str(gender or "") + "_" + " ".join(str(t) for t in (traits or [])) + "_" + str(role or "")).encode("utf-8")
    hash_val = int(hashlib.md5(seed_str).hexdigest(), 16) if seed_str else 0
    roll = hash_val % 100
    combined = (str(desc or "") + " " + str(role or "") + " " + " ".join(str(t) for t in (traits or []))).lower()

    # Gap-moe roll (~15% chance to invert expectations)
    is_gap_moe = (hash_val // 100) % 100 < 15

    # 1. Modest / Guarded / Religious / Diligent
    if any(kw in combined for kw in ("diligent", "guarded", "scholarly", "hesitant", "gentle", "priest", "nun", "shrine", "pure", "innocent", "modest", "disciplined")):
        if is_gap_moe:
            return "shameless" if roll < 35 else "bold"
        else:
            if roll < 55:
                return "prude"
            elif roll < 90:
                return "moderate"
            else:
                return "bold"

    # 2. Flirtatious / Mischievous / Delinquent / Hedonistic / Succubus
    if any(kw in combined for kw in ("flirt", "mischiev", "delinquent", "succubus", "demon", "seduct", "brat", "gyaru")):
        if is_gap_moe:
            return "prude"
        else:
            if roll < 35:
                return "shameless"
            elif roll < 75:
                return "bold"
            else:
                return "moderate"

    # 3. Standard general distribution baseline (~25% prude, ~45% moderate, ~20% bold, ~10% shameless)
    if roll < 25:
        return "prude"
    elif roll < 70:
        return "moderate"
    elif roll < 90:
        return "bold"
    else:
        return "shameless"

_ROMANTIC_COMFORT_TRACKS = (
    "romantic", "romance", "dating", "lover", "lovers", "partner", "spouse", "engaged", "crush",
)


def normalize_openness_tier(
    raw: Any,
    *,
    numeric_fallback: bool = True,
    default: str = "moderate",
) -> str:
    """Normalizes string labels, legacy full descriptions, aliases, and numeric 0-100 openness into a canonical tier."""
    if raw is None or isinstance(raw, bool):
        return default
    if numeric_fallback and isinstance(raw, (int, float)):
        num = float(raw)
        if num < 35:
            return "prude"
        if num < 65:
            return "moderate"
        if num < 85:
            return "bold"
        return "shameless"

    s = str(raw or "").strip().lower()
    if not s:
        return default
    if numeric_fallback and re.fullmatch(r"\d+(?:\.\d+)?", s):
        num = float(s)
        if num < 35:
            return "prude"
        if num < 65:
            return "moderate"
        if num < 85:
            return "bold"
        return "shameless"

    if any(k in s for k in ("shameless", "lewd", "hedonist", "nympho", "lascivious", "pervert")):
        return "shameless"
    if any(k in s for k in ("bold", "uninhibited", "sex-positive", "openly flirt", "adventurous", "very open")):
        return "bold"
    if any(k in s for k in ("prude", "modest", "prudish", "chaste", "strictly romance", "sheltered", "very guarded")):
        return "prude"
    if any(k in s for k in ("moderate", "reserved", "balanced", "natural pacing")):
        return "moderate"
    return default


def get_erotic_openness_label(tier_or_text: Any) -> str:
    """Returns the canonical descriptive template string for an Erotic Openness tier."""
    tier = normalize_openness_tier(tier_or_text)
    return EROTIC_OPENNESS_TEMPLATES.get(tier, EROTIC_OPENNESS_TEMPLATES["moderate"])


def compute_with_you_comfort(
    openness_raw: Any,
    *,
    relationship_score: int = 0,
    relationship_track: str = "platonic",
    shared_intimate_count: int = 0,
    is_hostile: bool = False,
    for_dm_or_inquiry: bool = False,
    contrast_archetype: str = "",
    bluff_crack_active: bool = False,
) -> Dict[str, Any]:
    """Derives live With-You Comfort ('guarded' -> 'warming_up' -> 'trusting_private') without DB migrations."""
    tier = normalize_openness_tier(openness_raw)
    try:
        score = int(relationship_score or 0)
    except (TypeError, ValueError):
        score = 0
    track = str(relationship_track or "platonic").strip().lower()
    is_romantic = any(tok in track for tok in _ROMANTIC_COMFORT_TRACKS)
    shared = max(0, int(shared_intimate_count or 0))

    if is_hostile or score < COMFORT_LIVE_STANDING_FLOOR:
        stage = "guarded"
    elif (is_romantic and score >= COMFORT_TRUSTING_SCORE and shared >= 1) or (shared >= COMFORT_TRUSTING_MILESTONES_ONLY):
        stage = "trusting_private"
    elif (is_romantic and score >= (COMFORT_WARMING_UP_DM_SCORE if for_dm_or_inquiry else COMFORT_WARMING_UP_SCORE)) or (
        shared >= 1 and (is_romantic or tier != "prude")
    ):
        stage = "warming_up"
    else:
        stage = "guarded"

    badge_key = ""
    badge_label = ""
    show_badge = False
    if tier in ("prude", "moderate") or (contrast_archetype == "all_talk_tease" and bluff_crack_active):
        if stage == "warming_up":
            badge_key = "warming_up"
            badge_label = "Warming Up With You"
            show_badge = True
        elif stage == "trusting_private":
            badge_key = "trusting_private"
            badge_label = "Trusting in Private"
            show_badge = True
    else:
        if stage == "trusting_private" and is_romantic and score >= COMFORT_TRUSTING_SCORE and shared >= 1:
            badge_key = "deeply_bonded"
            badge_label = "Deeply Bonded"
            show_badge = True

    return {
        "tier": tier,
        "stage": stage,
        "show_badge": show_badge,
        "badge_key": badge_key,
        "badge_label": badge_label,
        "is_romantic": is_romantic,
        "shared_intimate_count": shared,
        "score": score,
    }


def resolve_openness_contrast(
    openness_raw: Any,
    demeanor_raw: Any = "",
    dynamic_raw: Any = "",
    *,
    intercourse_experience: str = "",
    shared_intimate_count: int = 0,
    comfort_stage: str = "guarded",
    started_virgin: Optional[bool] = None,
) -> Dict[str, Any]:
    """Derives natural Gap-Moe contrast archetypes ('hidden_fire' or 'all_talk_tease') with zero generation bias."""
    tier = normalize_openness_tier(openness_raw)
    dem_low = str(demeanor_raw or "").lower()
    dyn_low = str(dynamic_raw or "").lower()
    shared = max(0, int(shared_intimate_count or 0))
    exp_low = str(intercourse_experience or "").strip().lower()
    is_virgin = exp_low == "virgin"

    if (
        tier == "prude"
        and any(k in dyn_low for k in ("insatiable", "high-drive", "dominant", "proactive", "service", "devoted"))
    ) or (
        tier == "moderate" and any(k in dyn_low for k in ("insatiable", "high-drive"))
    ):
        return {
            "archetype": "hidden_fire",
            "label": "Hidden Fire",
            "mechanical_active": comfort_stage in ("warming_up", "trusting_private"),
            "bluff_crack_active": False,
            "graduated": False,
            "tier": tier,
        }

    if tier in ("bold", "shameless") and (
        any(k in dem_low for k in ("hesitant", "flustered", "shy", "stammer"))
        or any(k in dyn_low for k in ("gentle", "yielding"))
    ):
        if started_virgin is False:
            bluff_crack = False
            graduated = False
        elif started_virgin is True:
            bluff_crack = shared < ALL_TALK_TEASE_GRADUATION_MILESTONES
            graduated = not bluff_crack
        else:
            bluff_crack = is_virgin
            graduated = False
        return {
            "archetype": "all_talk_tease",
            "label": "All-Talk Tease",
            "mechanical_active": bluff_crack,
            "bluff_crack_active": bluff_crack,
            "graduated": graduated,
            "tier": tier,
        }

    return {
        "archetype": "",
        "label": "",
        "mechanical_active": False,
        "bluff_crack_active": False,
        "graduated": False,
        "tier": tier,
    }

def is_turn_off_triggered(label_or_text: str, turn_offs_str: str, act_likes_str: str = "") -> bool:
    """
    Evaluates whether an action choice, dialogue, or description triggers an NPC's Turn-Off.
    Checks both direct phrase matching and the TURN_OFF_DETECTION_REGISTRY keywords using word boundaries.
    """
    if not label_or_text or not turn_offs_str:
        return False
    lbl = str(label_or_text).lower()
    t_offs = str(turn_offs_str).lower()
    if t_offs in ("none", "unknown", ""):
        return False

    # If the action explicitly matches an NPC's liked acts or kinks, do not trigger a turn-off
    if act_likes_str and str(act_likes_str).lower() not in ("none", "unknown", ""):
        likes_low = str(act_likes_str).lower()
        for lk in [p.strip() for p in likes_low.split(",") if p.strip()]:
            lk_clean = re.sub(r'\(.*?\)', '', lk).strip()
            if lk_clean and len(lk_clean) >= 4 and lk_clean in lbl:
                return False

    for reg_item in TURN_OFF_DETECTION_REGISTRY:
        reg_name = reg_item["name"].lower()
        reg_id = reg_item["id"].lower()
        reg_words = [w for w in reg_name.split() if len(w) >= 5 and w not in ("during", "intimacy")]
        if reg_name in t_offs or reg_id in t_offs or (reg_words and any(w in t_offs for w in reg_words)):
            for kw in reg_item["keywords"]:
                if " " in kw:
                    if kw in lbl:
                        return True
                else:
                    if re.search(r'\b' + re.escape(kw) + r'\b', lbl):
                        return True

    # Fallback to direct significant word matching
    for phrase in [p.strip() for p in t_offs.split(",") if p.strip()]:
        sig_words = [w for w in phrase.split() if len(w) >= 4 and w not in ("during", "intimacy", "with", "that")]
        if sig_words:
            matched_count = sum(1 for w in sig_words if re.search(r'\b' + re.escape(w) + r'\b', lbl))
            if (len(sig_words) == 1 and matched_count == 1) or (len(sig_words) >= 2 and matched_count >= 2):
                return True

    return False

def _coerce_items_list(raw: Any) -> List[str]:
    if not raw:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(x).strip() for x in raw if str(x).strip()]
    return [x.strip() for x in str(raw).split(",") if x.strip()]


def match_sensitive_spots(action_text: str, spots: Any) -> List[str]:
    """Matches physical sensitive spots in action text with word boundaries, supporting short 3-letter words (ear, hip, rib, jaw, lip, paw, fin)."""
    low = str(action_text or "").lower()
    if not low or not spots:
        return []
    stop_words = {"physical", "action", "base", "line", "slow", "firm", "soft", "with", "from", "skin", "side", "sides", "back", "area"}
    matched: List[str] = []
    for raw_spot in _coerce_items_list(spots):
        s_clean = re.sub(r'\([^)]*\)', '', raw_spot.lower()).strip()
        if not s_clean or s_clean in ("none", "unknown"):
            continue
        if re.search(r'\b' + re.escape(s_clean) + r'\b', low):
            matched.append(raw_spot)
            continue
        core_words = [
            w for w in re.split(r'[\s/&\-]+', s_clean)
            if (len(w) >= 4 or w in SHORT_ANATOMY_SPOT_WORDS) and w not in stop_words
        ]
        # Avoid 'boobs' matching 'Breasts' while supporting singular/plural for explicit anatomy words
        hit = False
        for w in core_words:
            stem = w[:-1] if (w.endswith("s") and len(w) >= 4 and not w.endswith("ss")) else w
            if re.search(r'\b' + re.escape(w) + r'\b', low) or (
                stem != w and re.search(r'\b' + re.escape(stem) + r'\b', low)
            ):
                hit = True
                break
        if hit:
            matched.append(raw_spot)
    return matched


def match_desires_and_kinks(action_text: str, desires: Any, fetishes: Any = "") -> tuple[List[str], List[str]]:
    """Matches active desires and active kinks independently from DESIRE_AND_KINK_REGISTRY and custom triggers."""
    low = str(action_text or "").lower()
    if not low:
        return [], []
    desire_items = [re.sub(r'\([^)]*\)', '', x).strip() for x in _coerce_items_list(desires)]
    desire_items = [x for x in desire_items if x and x.lower() not in ("none", "unknown", "none (vanilla)")]
    fetish_items = [re.sub(r'\([^)]*\)', '', x).strip() for x in _coerce_items_list(fetishes)]
    fetish_items = [x for x in fetish_items if x and x.lower() not in ("none", "unknown", "none (vanilla)")]

    desire_blob = " , ".join(x.lower() for x in desire_items)
    fetish_blob = " , ".join(x.lower() for x in fetish_items)

    matched_desires: List[str] = []
    matched_kinks: List[str] = []
    matched_reg_names: set[str] = set()

    for reg in DESIRE_AND_KINK_REGISTRY:
        rname_l = reg["name"].lower()
        rkind = reg["kind"]
        in_fetish = rname_l in fetish_blob or (reg["id"] in fetish_blob)
        in_desire = rname_l in desire_blob or (reg["id"] in desire_blob)
        if not in_fetish and not in_desire:
            continue
        kw_hit = False
        for kw in reg["keywords"]:
            if " " in kw:
                if kw in low:
                    kw_hit = True
                    break
            elif re.search(r'\b' + re.escape(kw) + r'\w*\b', low):
                kw_hit = True
                break
        if not kw_hit:
            continue
        matched_reg_names.add(rname_l)
        if in_fetish or rkind == "kink":
            if reg["name"] not in matched_kinks:
                matched_kinks.append(reg["name"])
        else:
            if reg["name"] not in matched_desires:
                matched_desires.append(reg["name"])

    for raw_k in fetish_items:
        kl = raw_k.lower()
        if any(kl == mk.lower() or kl in mk.lower() for mk in matched_kinks):
            continue
        sig_w = [w for w in re.split(r'[\s/&\-]+', kl) if len(w) >= 4]
        if sig_w and all(re.search(r'\b' + re.escape(w) + r'\b', low) for w in sig_w):
            matched_kinks.append(raw_k)

    for raw_d in desire_items:
        dl = raw_d.lower()
        if dl in matched_reg_names or any(dl == mk.lower() for mk in matched_kinks):
            continue
        sig_w = [w for w in re.split(r'[\s/&\-]+', dl) if len(w) >= 4]
        sig_stems = [
            w[:-1] if (w.endswith("s") and len(w) >= 4 and not w.endswith("ss")) else w
            for w in sig_w
        ]
        if (
            dl in low
            or (len(sig_w) >= 2 and all(re.search(r'\b' + re.escape(st) + r'\w*\b', low) for st in sig_stems))
            or (len(sig_w) == 1 and re.search(r'\b' + re.escape(sig_stems[0]) + r'\w*\b', low))
        ):
            if any(dl == mk.lower() or mk.lower() in dl for mk in fetish_items):
                if raw_d not in matched_kinks:
                    matched_kinks.append(raw_d)
            elif raw_d not in matched_desires:
                matched_desires.append(raw_d)

    return matched_desires, matched_kinks


def match_act_preferences(
    action_text: str,
    act_likes: Any,
    act_dislikes: Any,
    sub_intent: str = "",
    act_type: str = "",
) -> tuple[List[str], List[str]]:
    """Matches all 15 ACT_PREFERENCE_REGISTRY items in Likes/Dislikes with NPC perspective awareness."""
    low = str(action_text or "").lower()
    sub_l = str(sub_intent or "").strip().lower()
    type_l = str(act_type or "").strip().lower()

    # Translate player-centric sub_intent/act_type to the NPC's experienced act_ids
    perspective_ids: set[str] = set()
    eff_act = sub_l or type_l
    if eff_act == "oral_give":
        perspective_ids.add("receiving_oral")
    elif eff_act == "oral_receive":
        perspective_ids.add("giving_oral")
    elif eff_act == "oral_mutual":
        perspective_ids.update({"giving_oral", "receiving_oral"})
    elif eff_act in ("anal_give",):
        perspective_ids.add("receiving_anal")
    elif eff_act in ("anal_receive",):
        perspective_ids.add("giving_anal")

    # Prevent opposite-direction keyword misfire when direction is explicitly known
    blocked_dir_ids: set[str] = set()
    if eff_act == "oral_give":
        blocked_dir_ids.add("giving_oral")
    elif eff_act == "oral_receive":
        blocked_dir_ids.add("receiving_oral")
    elif eff_act == "anal_give":
        blocked_dir_ids.add("giving_anal")
    elif eff_act == "anal_receive":
        blocked_dir_ids.add("receiving_anal")

    likes_str = ", ".join(_coerce_items_list(act_likes)).lower()
    dislikes_str = ", ".join(_coerce_items_list(act_dislikes)).lower()

    def _has_pref(pref_item: Dict[str, Any], blob: str) -> bool:
        if not blob:
            return False
        iname = pref_item["name"].lower()
        iid = pref_item["id"].lower()
        if iname in blob or iid in blob:
            return True
        return any(
            p.strip() and (p.strip() in iname or iname in p.strip())
            for p in blob.split(",")
        )

    matched_likes: List[str] = []
    matched_dislikes: List[str] = []

    for item in ACT_PREFERENCE_REGISTRY:
        aid = item["id"]
        if aid in blocked_dir_ids:
            continue
        is_hit = aid in perspective_ids
        if not is_hit and low:
            is_hit = any(
                (kw in low) if " " in kw else bool(re.search(r'\b' + re.escape(kw) + r'\b', low))
                for kw in item["keywords"]
            )
        if not is_hit:
            continue
        if _has_pref(item, likes_str) and item["name"] not in matched_likes:
            matched_likes.append(item["name"])
        if _has_pref(item, dislikes_str) and item["name"] not in matched_dislikes:
            matched_dislikes.append(item["name"])

    return matched_likes, matched_dislikes


def evaluate_environmental_turn_offs(
    turn_offs: Any,
    *,
    player_is_bloodied: bool = False,
    has_bystanders: bool = False,
    intent_category: str = "",
    is_active_intimacy: bool = False,
    action_text: str = "",
) -> List[str]:
    """Evaluates context-strict environmental turn-offs:
    - 'Poor hygiene & neglect' when bloodied on physical romantic/intimate advances (not combat, casual chat, or healing/tending).
    - 'Lack of discretion & careless exposure' when bystanders are present on overt intimate/erotic acts (not subtle flirting/hand-holding).
    """
    t_str = ", ".join(_coerce_items_list(turn_offs)).lower()
    if not t_str or t_str in ("none", "unknown"):
        return []
    lbl = str(action_text or "").lower()
    icat = str(intent_category or "").strip().lower()

    if icat in ("combat", "combat_attack", "combat_spell", "combat_flee", "exploration", "lore_query"):
        return []

    is_healing_or_care = any(
        kw in lbl for kw in ("bandage", "heal", "tend", "treat wound", "first aid", "cleanse", "wash", "medicine", "potion", "ointment")
    )
    is_physical_advance = bool(
        is_active_intimacy
        or icat in ("intimate_act", "affection_touch")
        or any(kw in lbl for kw in ("kiss", "caress", "embrace", "cuddle", "undress", "strip", "touch", "stroke", "make love", "seduce", "intimate", "fondle", "nipple", "breast", "oral", "intercourse"))
    )
    is_subtle_only = (
        not is_active_intimacy
        and icat in ("chat", "casual", "flirt", "friendly")
        and any(kw in lbl for kw in ("hand-holding", "hold hands", "lace fingers", "flirt", "smile", "compliment", "chat", "talk", "banter"))
        and not any(kw in lbl for kw in ("undress", "strip", "fuck", "oral", "intercourse", "naked", "clit", "cock", "pussy", "fondle", "grope", "make love", "make out", "pin against"))
    )
    is_overt_erotic = bool(
        is_active_intimacy
        or (icat == "intimate_act" and not is_subtle_only)
        or (
            not is_subtle_only
            and any(kw in lbl for kw in ("undress", "strip", "naked", "nude", "oral", "intercourse", "penetrat", "fuck", "fondle", "grope", "make love", "make out", "squeeze breast", "squeeze ass", "finger"))
        )
    )

    triggered: List[str] = []
    if player_is_bloodied and ("hygiene" in t_str or "neglect" in t_str):
        if is_physical_advance and not is_healing_or_care:
            triggered.append("Poor hygiene & neglect")
    if has_bystanders and ("discretion" in t_str or "exposure" in t_str):
        if is_overt_erotic:
            triggered.append("Lack of discretion & careless exposure")
    return triggered


def calculate_intimate_action_dc_modifier(
    label: str,
    app_dict: Dict[str, Any],
    *,
    player_appearance: Optional[Dict[str, Any]] = None,
    partner_excitement: int = 0,
    player_is_bloodied: bool = False,
    has_bystanders: bool = False,
    intent_category: str = "",
    is_active_intimacy: bool = False,
    sub_intent: str = "",
    act_type: str = "",
    relationship_score: int = 0,
    relationship_track: str = "platonic",
    shared_intimate_count: int = 0,
    is_hostile: bool = False,
) -> int:
    """
    Calculates combined DC modifier for intimate choices based on Turn-Offs, Desires & Kinks, Sensitive Spots,
    Act Preferences, Erotic Openness + With-You Comfort + Contrast, and PP Entry Pacing
    (capping positive preference/turn-off penalties at +6).
    """
    if not isinstance(app_dict, dict):
        return 0
    lbl = str(label or "").lower()
    pref_penalty = 0
    pref_bonus = 0
    misc_mod = 0

    # 1. Turn-Offs Check (Action text + Context-Strict Environmental)
    turn_offs = str(app_dict.get("turn_offs") or "").lower()
    act_likes = str(app_dict.get("act_likes") or "").lower()
    env_offs = evaluate_environmental_turn_offs(
        turn_offs,
        player_is_bloodied=player_is_bloodied,
        has_bystanders=has_bystanders,
        intent_category=intent_category,
        is_active_intimacy=is_active_intimacy,
        action_text=lbl,
    )
    if (turn_offs and is_turn_off_triggered(lbl, turn_offs, act_likes or str(app_dict.get("desires_and_kinks") or ""))) or env_offs:
        pref_penalty += 5

    # 2. Sensitive Spots, Desires & Active Kinks Check (independent checks, no shadowing)
    matched_spots = match_sensitive_spots(lbl, app_dict.get("sensitive_spots"))
    matched_desires, matched_kinks = match_desires_and_kinks(
        lbl,
        app_dict.get("desires_and_kinks") or app_dict.get("turn_ons"),
        app_dict.get("fetishes"),
    )
    if matched_spots or matched_desires or matched_kinks:
        pref_bonus -= 2

    # 3. Act Preferences Check (all 15 acts, perspective-aware)
    liked_acts, disliked_acts = match_act_preferences(
        lbl,
        act_likes,
        app_dict.get("act_dislikes"),
        sub_intent=sub_intent,
        act_type=act_type,
    )
    if liked_acts:
        pref_bonus -= 2
    if disliked_acts:
        pref_penalty += 3

    # Cap combined positive preference & turn-off DC penalty at MAX_PREFERENCE_DC_PENALTY (+6)
    capped_penalty = min(MAX_PREFERENCE_DC_PENALTY, pref_penalty)

    # 4. Erotic Openness, With-You Comfort & Gap-Moe Contrast Check for intimate interactions
    if any(k in lbl for k in ("intimate", "kiss", "undress", "touch", "suggestive", "flirt", "seduce", "bed", "naked", "strip", "embrace", "oral", "intercourse", "climax", "caress", "penetrat", "anal", "thrust", "tease", "banter")):
        raw_op = app_dict.get("erotic_openness") or app_dict.get("openness") or "moderate"
        op_tier = normalize_openness_tier(raw_op)
        dem_raw = app_dict.get("intimate_demeanor") or app_dict.get("demeanor") or ""
        dyn_raw = app_dict.get("intimate_dynamic") or app_dict.get("dynamic") or ""
        ic_exp = str(app_dict.get("intercourse_experience") or app_dict.get("predetermined_intercourse") or "").strip().lower()
        pre_comfort = compute_with_you_comfort(
            op_tier,
            relationship_score=relationship_score,
            relationship_track=relationship_track,
            shared_intimate_count=shared_intimate_count,
            is_hostile=is_hostile,
        )
        contrast = resolve_openness_contrast(
            op_tier,
            dem_raw,
            dyn_raw,
            intercourse_experience=ic_exp,
            shared_intimate_count=shared_intimate_count,
            comfort_stage=pre_comfort["stage"],
        )
        comfort = compute_with_you_comfort(
            op_tier,
            relationship_score=relationship_score,
            relationship_track=relationship_track,
            shared_intimate_count=shared_intimate_count,
            is_hostile=is_hostile,
            contrast_archetype=contrast["archetype"],
            bluff_crack_active=contrast["bluff_crack_active"],
        )

        is_verbal_banter_only = any(k in lbl for k in ("flirt", "tease", "banter", "innuendo", "joke", "compliment")) and not any(
            k in lbl for k in ("undress", "strip", "naked", "bed", "oral", "intercourse", "penetrat", "climax", "thrust", "inside", "anal")
        )
        is_explicit_physical = bool(
            is_active_intimacy
            or any(k in lbl for k in ("undress", "strip", "naked", "bed", "oral", "intercourse", "penetrat", "climax", "thrust", "inside", "anal", "touch", "caress", "intimate"))
        ) and not is_verbal_banter_only
        is_gentle_pace = any(
            k in lbl for k in ("gentle", "gently", "slow", "slowly", "tender", "tenderly", "reassur", "softly", "patient", "warm up")
        )
        is_rushed_pace = any(
            k in lbl for k in ("rush", "hurry", "force", "slam", "shove", "straight inside", "all at once", "skip foreplay", "impatient", "grab", "pin")
        )

        if op_tier == "prude":
            if has_bystanders:
                misc_mod += 3
            elif comfort["stage"] == "trusting_private":
                misc_mod += 0
            elif comfort["stage"] == "warming_up":
                misc_mod += 1
            else:
                misc_mod += 3
        elif op_tier == "shameless":
            if contrast["archetype"] == "all_talk_tease" and contrast["bluff_crack_active"] and is_explicit_physical:
                is_heavy_esc = is_rushed_pace or any(k in lbl for k in ("undress", "strip", "naked", "oral", "intercourse", "penetrat", "thrust", "inside", "anal"))
                if is_rushed_pace or (is_heavy_esc and not is_gentle_pace):
                    misc_mod += 2
                elif is_gentle_pace:
                    misc_mod -= 1
            else:
                misc_mod -= 3
        elif op_tier == "bold":
            if contrast["archetype"] == "all_talk_tease" and contrast["bluff_crack_active"] and is_explicit_physical:
                is_heavy_esc = is_rushed_pace or any(k in lbl for k in ("undress", "strip", "naked", "oral", "intercourse", "penetrat", "thrust", "inside", "anal"))
                if is_rushed_pace or (is_heavy_esc and not is_gentle_pace):
                    misc_mod += 2
                elif is_gentle_pace:
                    misc_mod -= 1
            else:
                misc_mod -= 2

    # 5. PP Size Entry Pacing Check
    p_app = player_appearance if isinstance(player_appearance, dict) else {}
    raw_pp = str(p_app.get("penis_size") or "").strip()
    if not raw_pp and not any(k in lbl for k in ("enter her", "inside her", "take her", "claim her", "thrust into her")):
        raw_pp = str(app_dict.get("penis_size") or "").strip()

    if raw_pp and raw_pp.lower() not in ("none", "unknown", "n/a", "null", "false", "0"):
        from .appearance import classify_asset_size_tier
        pp_tier = classify_asset_size_tier(raw_pp, "male")
        is_anal_entry = any(kw in lbl for kw in ANAL_KEYWORDS) or any(
            kw in lbl for kw in ("anally", "in her ass", "in his ass", "anal entry", "rear entry")
        )
        is_pen_entry = (
            any(kw in lbl for kw in INTERCOURSE_KEYWORDS)
            or any(
                kw in lbl
                for kw in (
                    "penetrat", "enter her", "enter him", "slip inside", "push inside",
                    "slide inside", "thrust inside", "thrust into", "claim her", "claim him",
                    "take her", "take him", "ride him", "straddle his", "sink inside",
                )
            )
        )
        if is_anal_entry or is_pen_entry:
            is_gentle = any(
                kw in lbl
                for kw in (
                    "gentle", "gently", "slow", "slowly", "tender", "tenderly",
                    "ease", "careful", "carefully", "patient", "softly", "gradual",
                    "prep", "prepare", "relax", "warm up",
                )
            )
            is_explicit_rush = any(
                kw in lbl
                for kw in (
                    "rush", "hurry", "force", "slam", "shove", "straight inside",
                    "all at once", "to the hilt", "ram", "skip foreplay", "impatient",
                )
            )
            partner_intercourse = str(app_dict.get("intercourse_experience") or app_dict.get("intercourse") or "").strip().lower()
            partner_anal = str(app_dict.get("anal_experience") or app_dict.get("anal") or "").strip().lower()
            is_virgin = partner_intercourse == "virgin"
            is_anal_inexp = partner_anal in ("", "inexperienced")

            if pp_tier == "huge":
                if int(partner_excitement or 0) < HUGE_PP_ENTRY_EXCITEMENT_THRESHOLD:
                    if (is_anal_entry and is_anal_inexp) or (is_pen_entry and is_virgin and (is_explicit_rush or not is_gentle)):
                        misc_mod += 2
            elif pp_tier in ("flat", "small"):
                if is_gentle or any(kw in lbl for kw in ("reassur", "stretch", "easy", "calm")):
                    misc_mod -= 1

    return capped_penalty + pref_bonus + misc_mod


def evaluate_height_preference(
    player_appearance: Optional[Dict[str, Any]],
    npc_appearance: Optional[Dict[str, Any]],
    *,
    npc_gender: str = "",
    npc_race: str = "",
    npc_name: str = "",
    player_race: str = "",
) -> Dict[str, Any]:
    """Evaluate relative height preference (taller_partner / shorter_partner) for romance DCs and excitement scaling."""
    neutral = {"dc_mod": 0, "excitement_mult": 1.0, "triggered_pref": None, "diff": 0}
    p_app = player_appearance if isinstance(player_appearance, dict) else {}
    n_app = npc_appearance if isinstance(npc_appearance, dict) else {}
    if not p_app and not n_app:
        return neutral

    from .appearance import is_feral_rear_excluded, normalize_stature_tier
    from .generation import generate_dynamic_height_preference, normalize_body_preferences

    if is_feral_rear_excluded(player_race) or is_feral_rear_excluded(npc_race):
        return neutral

    raw_p_stat = str(p_app.get("stature") or p_app.get("height") or "average").strip()
    raw_n_stat = str(n_app.get("stature") or n_app.get("height") or "average").strip()
    p_rank = STATURE_RANK_MAP.get(normalize_stature_tier(raw_p_stat), 4)
    n_rank = STATURE_RANK_MAP.get(normalize_stature_tier(raw_n_stat), 4)
    diff = p_rank - n_rank
    if diff == 0:
        return neutral

    npc_likes, npc_dislikes = normalize_body_preferences(
        n_app.get("body_likes"),
        n_app.get("body_dislikes"),
    )
    has_height_pref = any(k in HEIGHT_PREFERENCE_KEYS for k in (npc_likes + npc_dislikes))
    if not has_height_pref and not n_app.get("height_pref_seeded") and n_app:
        seed_str = f"{n_app.get('desc', '')}_{npc_race}_{npc_name}".encode("utf-8")
        h_val = int(hashlib.md5(seed_str).hexdigest(), 16)
        seeded = generate_dynamic_height_preference(
            h_val,
            gender=npc_gender,
            stature=normalize_stature_tier(raw_n_stat),
            race=npc_race,
        )
        npc_likes = list(npc_likes) + list(seeded.get("body_likes") or [])
        npc_dislikes = list(npc_dislikes) + list(seeded.get("body_dislikes") or [])

    rel_key = "taller_partner" if diff > 0 else "shorter_partner"
    gap = abs(diff)
    dc_mod = 0
    mult = 1.0
    sentiment = ""

    if rel_key in npc_likes:
        dc_mod = HEIGHT_PREF_STRONG_LIKE_DC if gap >= 2 else HEIGHT_PREF_MOD_LIKE_DC
        mult = HEIGHT_PREF_STRONG_LIKE_MULT if gap >= 2 else HEIGHT_PREF_MOD_LIKE_MULT
        sentiment = "like"
    elif rel_key in npc_dislikes:
        dc_mod = HEIGHT_PREF_DISLIKE_DC
        mult = HEIGHT_PREF_STRONG_DISLIKE_MULT if gap >= 2 else HEIGHT_PREF_MOD_DISLIKE_MULT
        sentiment = "dislike"

    if not sentiment:
        return {"dc_mod": 0, "excitement_mult": 1.0, "triggered_pref": None, "diff": diff}

    triggered = {
        "npc_name": str(npc_name or "").strip(),
        "fact_category": "body_pref",
        "fact_key": f"body_pref:{rel_key}",
        "fact_value": rel_key,
        "sentiment": sentiment,
        "part": "height",
        "gap": gap,
    }
    return {
        "dc_mod": dc_mod,
        "excitement_mult": mult,
        "triggered_pref": triggered,
        "diff": diff,
    }


def calculate_height_preference_dc_modifier(
    player_appearance: Optional[Dict[str, Any]],
    npc_appearance: Optional[Dict[str, Any]],
    *,
    npc_gender: str = "",
    npc_race: str = "",
    npc_name: str = "",
    player_race: str = "",
) -> int:
    """Return the romantic/flirt DC modifier (-2, -1, 0, or +1) from relative partner height preferences."""
    return int(
        evaluate_height_preference(
            player_appearance,
            npc_appearance,
            npc_gender=npc_gender,
            npc_race=npc_race,
            npc_name=npc_name,
            player_race=player_race,
        ).get("dc_mod", 0)
    )

