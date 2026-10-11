from __future__ import annotations
from .constants import *
import json
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

def transition_anal_experience(current_state: str, action_type: str) -> str:
    """Transitions anal intimacy track."""
    c = str(current_state or "inexperienced").strip().lower()
    act = str(action_type or "").strip().lower()
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
    if sens_raw and sens_raw.lower() not in ("none", "unknown", ""):
        all_raw_items.extend([x.strip() for x in sens_raw.split(",") if x.strip()])
    if turn_raw and turn_raw.lower() not in ("none", "unknown", ""):
        all_raw_items.extend([x.strip() for x in turn_raw.split(",") if x.strip()])

    if not all_raw_items:
        return "", ""

    phys_items = []
    act_items = []
    seen = set()

    for item in all_raw_items:
        clean_item = item.strip()
        item_lower = clean_item.lower()
        if not clean_item or item_lower in ("none", "unknown") or clean_item in seen:
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

def enforce_intimacy_safeguard_invariants(app_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enforces the single-source-of-truth invariant across intimacy state fields:
    1. An NPC whose canon predetermined state is 'virgin' CANNOT have active experience (intercourse, oral, manual)
       unless verified by actual recorded player milestone memories or the 'had_first_time_with_player' flag.
    2. Composite 'virginity' is strictly synchronized as a derived reflection of active experience tracks.
    """
    if not isinstance(app_dict, dict):
        return app_dict

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
    has_anal_give = any(any(k in str(m).lower() for k in ANAL_GIVE_MEMORY_KEYWORDS) for m in mems)
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

def merge_anal_states(existing_anal: str, incoming_anal: str) -> str:
    """Combines anal intimacy experience states following a strictly progressive one-way ratchet."""
    e = str(existing_anal or "").strip().lower()
    i = str(incoming_anal or "").strip().lower()
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
    is_male = any(kw in raw_g for kw in ("male", "man", "boy", "lord", "he", "him", "his")) and not any(kw in raw_g for kw in ("female", "woman"))
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

def get_erotic_openness_label(tier_or_text: str) -> str:
    """Returns the canonical descriptive template string for an Erotic Openness tier."""
    raw = str(tier_or_text or "").strip().lower()
    if any(k in raw for k in ("prude", "modest", "guarded")):
        return EROTIC_OPENNESS_TEMPLATES["prude"]
    elif any(k in raw for k in ("shameless", "lewd", "pervert", "hedonist")):
        return EROTIC_OPENNESS_TEMPLATES["shameless"]
    elif any(k in raw for k in ("bold", "uninhibited", "open")):
        return EROTIC_OPENNESS_TEMPLATES["bold"]
    return EROTIC_OPENNESS_TEMPLATES["moderate"]

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

def calculate_intimate_action_dc_modifier(label: str, app_dict: Dict[str, Any]) -> int:
    """
    Calculates combined DC modifier for intimate choices based on Turn-Offs, Turn-Ons, Act Preferences, and Erotic Openness.
    - Triggering Turn-Offs: +5 DC penalty
    - Targeting Desires / Turn-Ons: -2 DC bonus
    - Initiating Liked Acts: -2 DC bonus
    - Initiating Disliked Acts: +3 DC penalty
    - Erotic Openness: Prude (+3), Shameless (-3), Bold (-2)
    """
    if not isinstance(app_dict, dict):
        return 0
    lbl = str(label or "").lower()
    mod = 0

    # 1. Turn-Offs Check (High difficulty spike when triggering a partner's ick)
    turn_offs = str(app_dict.get("turn_offs") or "").lower()
    act_likes = str(app_dict.get("act_likes") or app_dict.get("desires_and_kinks") or "").lower()
    if turn_offs and is_turn_off_triggered(lbl, turn_offs, act_likes):
        mod += 5

    # 2. Turn-Ons / Desires Check
    turn_ons = str(app_dict.get("turn_ons") or app_dict.get("sensitive_spots") or app_dict.get("desires_and_kinks") or "").lower()
    if turn_ons and turn_ons not in ("none", "unknown"):
        # Split into raw trigger keywords
        triggers = [t.replace("(physical)", "").replace("(action)", "").strip() for t in turn_ons.split(",") if t.strip()]
        for trig in triggers:
            if not trig or len(trig) < 4:
                continue
            sig_words = [w for w in trig.split() if len(w) >= 4]
            if trig in lbl or (len(sig_words) >= 2 and all(w in lbl for w in sig_words)):
                mod -= 2
                break

    # 3. Act Preferences Check
    act_likes = str(app_dict.get("act_likes") or "").lower()
    act_dislikes = str(app_dict.get("act_dislikes") or "").lower()

    for item in ACT_PREFERENCE_REGISTRY:
        item_kws = item["keywords"]
        is_mentioned = any(kw in lbl for kw in item_kws)
        if is_mentioned:
            item_name_l = item["name"].lower()
            is_liked = (item_name_l in act_likes) or (item["id"] in act_likes) or any(p.strip() and (p.strip() in item_name_l or item_name_l in p.strip()) for p in act_likes.split(","))
            is_disliked = (item_name_l in act_dislikes) or (item["id"] in act_dislikes) or any(p.strip() and (p.strip() in item_name_l or item_name_l in p.strip()) for p in act_dislikes.split(","))
            if is_liked:
                mod -= 2
            if is_disliked:
                mod += 3

    # 4. Erotic Openness Check for intimate interactions
    if any(k in lbl for k in ("intimate", "kiss", "undress", "touch", "suggestive", "flirt", "seduce", "bed", "naked", "strip", "embrace", "oral", "intercourse", "climax", "caress")):
        op_val = str(app_dict.get("erotic_openness") or app_dict.get("openness") or "").lower()
        if "prude" in op_val or "modest" in op_val:
            mod += 3
        elif "shameless" in op_val or "lewd" in op_val:
            mod -= 3
        elif "bold" in op_val or "uninhibited" in op_val:
            mod -= 2

    return mod

