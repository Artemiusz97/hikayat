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
    has_sex_mem = any(any(k in str(m).lower() for k in INTERCOURSE_MEMORY_KEYWORDS) for m in mems)
    has_oral_give = any(any(k in str(m).lower() for k in ORAL_GIVE_MEMORY_KEYWORDS) for m in mems)
    has_oral_rec = any(any(k in str(m).lower() for k in ORAL_RECEIVE_MEMORY_KEYWORDS) for m in mems)
    has_manual_give = any(any(k in str(m).lower() for k in MANUAL_GIVE_MEMORY_KEYWORDS) for m in mems)
    has_manual_rec = any(any(k in str(m).lower() for k in MANUAL_RECEIVE_MEMORY_KEYWORDS) for m in mems)
    had_first_time = bool(app_dict.get("had_first_time_with_player"))

    pred_i = str(app_dict.get("predetermined_intercourse") or "").strip().lower()
    if pred_i in ("virgin", "non_virgin"):
        app_dict["predetermined_intercourse"] = pred_i

    # INVARIANT 1: Ground intercourse, oral, and manual experience in milestone memories for predetermined virgins
    cur_i = str(app_dict.get("intercourse_experience") or "virgin").strip().lower()
    cur_o = str(app_dict.get("oral_experience") or "inexperienced").strip().lower()
    cur_m = str(app_dict.get("manual_experience") or "inexperienced").strip().lower()

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
        else:
            if cur_o in ORAL_INTIMACY_STATES and cur_o != "inexperienced":
                app_dict["oral_experience"] = cur_o
            if cur_m in MANUAL_INTIMACY_STATES and cur_m != "inexperienced":
                app_dict["manual_experience"] = cur_m
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
    else:
        # Corrupted or missing predetermined_intercourse — infer from stored experience and memories
        # Clamp to valid state sets; never allow invalid strings to persist
        if cur_i not in ("virgin", "non_virgin"):
            cur_i = "non_virgin" if (has_sex_mem or cur_i == "non_virgin") else "virgin"
        app_dict["predetermined_intercourse"] = cur_i
        app_dict["intercourse_experience"] = "non_virgin" if (has_sex_mem or cur_i == "non_virgin") else "virgin"
        if cur_o not in ORAL_INTIMACY_STATES:
            app_dict["oral_experience"] = "inexperienced"
        if cur_m not in MANUAL_INTIMACY_STATES:
            app_dict["manual_experience"] = "inexperienced"
        # Apply memory ratchet
        if has_oral_give:
            app_dict["oral_experience"] = merge_oral_states(app_dict.get("oral_experience", "inexperienced"), "has_done_oral")
        if has_oral_rec:
            app_dict["oral_experience"] = merge_oral_states(app_dict.get("oral_experience", "inexperienced"), "has_received_oral")
        if has_manual_give:
            app_dict["manual_experience"] = merge_manual_states(app_dict.get("manual_experience", "inexperienced"), "has_done_manual")
        if has_manual_rec:
            app_dict["manual_experience"] = merge_manual_states(app_dict.get("manual_experience", "inexperienced"), "has_received_manual")

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

def infer_intimate_demeanor_from_traits(desc: Any = "", race: str = "human", gender: str = "female", traits: List[str] = None, role: str = "") -> str:
    """Infers an authentic intimate demeanor (voice, emotional tone, communication style) correlated to character traits, role, and description."""
    if isinstance(desc, dict):
        desc = " ".join(str(v) for v in desc.values() if v)
    combined = (str(desc or "") + " " + str(role or "") + " " + " ".join(str(t) for t in (traits or []))).lower()
    raw_g = str(gender or "female").strip().lower()
    is_male = any(kw in raw_g for kw in ("male", "man", "boy", "lord", "he", "him", "his")) and not any(kw in raw_g for kw in ("female", "woman"))

    # 1. Athletic, competitive, direct personalities
    if any(kw in combined for kw in ("athlete", "athletic", "track", "captain", "competitive", "warrior", "leader", "bold", "confident", "fighter", "swimmer", "runner", "martial")):
        return INTIMATE_DEMEANOR_MALE_TEMPLATES[4] if is_male else INTIMATE_DEMEANOR_FEMALE_TEMPLATES[4]

    # 2. Rogues, mischievous characters, kitsune, sly rivals
    if any(kw in combined for kw in ("teas", "rogue", "mischiev", "kitsune", "sly", "brat", "prank", "flirt", "playful", "cunning")):
        return INTIMATE_DEMEANOR_MALE_TEMPLATES[0] if is_male else INTIMATE_DEMEANOR_FEMALE_TEMPLATES[0]

    # 3. Passionate & Intense / Vocal (Passionate, artistic, uninhibited, fierce, dancer)
    if any(kw in combined for kw in ("passion", "intense", "fiery", "artistic", "uninhibited", "wild", "dancer", "expressive")):
        return INTIMATE_DEMEANOR_MALE_TEMPLATES[3] if is_male else INTIMATE_DEMEANOR_FEMALE_TEMPLATES[3]

    # 4. Poised & Sensually Confident (Scholars, nobles, mages, disciplined councilors)
    if any(kw in combined for kw in ("scholar", "mage", "noble", "disciplined", "composed", "president", "council", "intellectual", "calculating", "perfectionist", "mature", "dignified")):
        return INTIMATE_DEMEANOR_MALE_TEMPLATES[2] if is_male else INTIMATE_DEMEANOR_FEMALE_TEMPLATES[2]

    # 5. Gentle & Loving / Protective (Healers, kind, sweet, warm, nurturing)
    if any(kw in combined for kw in ("gentle", "nurtur", "healer", "kind", "caring", "soft", "sweet", "protective", "warm")):
        return INTIMATE_DEMEANOR_MALE_TEMPLATES[1] if is_male else INTIMATE_DEMEANOR_FEMALE_TEMPLATES[1]

    # 6. Flustered / Shy (Strictly reserved for characters with shy/timid/anxious traits)
    if any(kw in combined for kw in ("shy", "timid", "anxious", "nervous", "inexperienced", "bookworm", "flustered", "introvert", "sheltered")):
        return INTIMATE_DEMEANOR_MALE_TEMPLATES[5] if is_male else INTIMATE_DEMEANOR_FEMALE_TEMPLATES[5]

    # Hash-based procedural fallback evenly across templates
    seed_str = (str(desc or "") + "_" + str(race or "") + "_" + str(gender or "")).encode("utf-8")
    hash_val = int(hashlib.md5(seed_str).hexdigest(), 16) if seed_str else 0
    templates = INTIMATE_DEMEANOR_MALE_TEMPLATES if is_male else INTIMATE_DEMEANOR_FEMALE_TEMPLATES
    return templates[hash_val % len(templates)]

def infer_intimate_dynamic_from_traits(desc: Any = "", race: str = "human", gender: str = "female", traits: List[str] = None, role: str = "") -> str:
    """
    Infers an intimate dynamic (proactivity, power balance, drive) for a character.
    Balances daytime trait context with diverse contrast ('gap moe' opportunities).
    """
    seed_str = (str(desc or "") + "_" + str(race or "") + "_" + str(gender or "") + "_" + " ".join(str(t) for t in (traits or [])) + "_" + str(role or "")).encode("utf-8")
    hash_val = int(hashlib.md5(seed_str).hexdigest(), 16) if seed_str else 0
    roll = hash_val % 100
    combined = (str(desc or "") + " " + str(role or "") + " " + " ".join(str(t) for t in (traits or []))).lower()

    # 1. Leaders / Competitive / Athletic (40% Receptive gap moe, 30% Dominant, 20% Switch, 10% High-Drive)
    if any(kw in combined for kw in ("athlete", "athletic", "track", "captain", "competitive", "leader", "warrior", "fighter", "runner")):
        if roll < 40:
            return INTIMATE_DYNAMIC_TEMPLATES[2]  # Eagerly Receptive / Surrenders Control (Craves partner taking charge)
        elif roll < 70:
            return INTIMATE_DYNAMIC_TEMPLATES[0]  # Boldly Proactive & Dominant
        elif roll < 90:
            return INTIMATE_DYNAMIC_TEMPLATES[1]  # Playful Switch / Teasing Brat
        else:
            return INTIMATE_DYNAMIC_TEMPLATES[3]  # Insatiable / Hidden High-Drive

    # 2. Healers / Nurturing / Shrine Maidens / Demure (35% High-Drive gap moe, 35% Gentle Yielding, 15% Service, 15% Switch)
    if any(kw in combined for kw in ("healer", "nurtur", "kind", "shrine", "priest", "pure", "innocent", "sweet", "caring")):
        if roll < 35:
            return INTIMATE_DYNAMIC_TEMPLATES[3]  # Insatiable / Hidden High-Drive (The gap moe)
        elif roll < 70:
            return INTIMATE_DYNAMIC_TEMPLATES[4]  # Gentle & Yielding
        elif roll < 85:
            return INTIMATE_DYNAMIC_TEMPLATES[5]  # Attentive Service-Oriented
        else:
            return INTIMATE_DYNAMIC_TEMPLATES[1]  # Playful Switch / Teasing Brat

    # 3. Scholars / Disciplined / Council Presidents (35% Service/Surrender gap moe, 35% Poised Dominant, 20% Switch, 10% High-Drive)
    if any(kw in combined for kw in ("scholar", "mage", "council", "president", "disciplined", "intellectual", "composed", "strict")):
        if roll < 35:
            return INTIMATE_DYNAMIC_TEMPLATES[2]  # Eagerly Receptive / Surrenders Control
        elif roll < 70:
            return INTIMATE_DYNAMIC_TEMPLATES[0]  # Boldly Proactive & Dominant
        elif roll < 90:
            return INTIMATE_DYNAMIC_TEMPLATES[1]  # Playful Switch
        else:
            return INTIMATE_DYNAMIC_TEMPLATES[3]  # Insatiable / Hidden High-Drive

    # 4. Rogues / Sly / Kitsune / Mischievous (50% Playful Switch, 25% Dominant, 25% Receptive)
    if any(kw in combined for kw in ("rogue", "kitsune", "mischiev", "sly", "brat", "flirt", "prank")):
        if roll < 50:
            return INTIMATE_DYNAMIC_TEMPLATES[1]  # Playful Switch / Teasing Brat
        elif roll < 75:
            return INTIMATE_DYNAMIC_TEMPLATES[0]  # Boldly Proactive & Dominant
        else:
            return INTIMATE_DYNAMIC_TEMPLATES[2]  # Eagerly Receptive / Surrenders Control

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

def calculate_intimate_action_dc_modifier(label: str, app_dict: Dict[str, Any]) -> int:
    """
    Calculates combined DC modifier for intimate choices based on Turn-Ons, Act Preferences, and Erotic Openness.
    - Targeting Turn-Ons: -2 to -3 DC bonus
    - Initiating Liked Acts: -2 DC bonus
    - Initiating Disliked Acts: +2 to +3 DC penalty
    - Erotic Openness: Prude (+3), Shameless (-3), Bold (-2)
    """
    if not isinstance(app_dict, dict):
        return 0
    lbl = str(label or "").lower()
    mod = 0

    # 1. Turn-ons Check
    turn_ons = str(app_dict.get("turn_ons") or app_dict.get("sensitive_spots") or "").lower()
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

    # 2. Act Preferences Check
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

    # 3. Erotic Openness Check for intimate interactions
    if any(k in lbl for k in ("intimate", "kiss", "undress", "touch", "suggestive", "flirt", "seduce", "bed", "naked", "strip", "embrace", "oral", "intercourse", "climax", "caress")):
        op_val = str(app_dict.get("erotic_openness") or app_dict.get("openness") or "").lower()
        if "prude" in op_val or "modest" in op_val:
            mod += 3
        elif "shameless" in op_val or "lewd" in op_val:
            mod -= 3
        elif "bold" in op_val or "uninhibited" in op_val:
            mod -= 2

    return mod

